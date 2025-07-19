#!/usr/bin/env python3
"""
Script d'installation pour les fonctionnalités personnalisées
Automatise l'intégration des fonctionnalités dans le code de base
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple


class CustomFeaturesInstaller:
    """Installeur pour les fonctionnalités personnalisées"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.custom_features_dir = project_root / "custom_features"
        self.backup_dir = project_root / "backup_before_custom_features"
        
    def install(self) -> bool:
        """Installe les fonctionnalités personnalisées"""
        print("🚀 Installation des fonctionnalités personnalisées...")
        
        try:
            # 1. Vérifier la structure
            if not self._check_structure():
                return False
            
            # 2. Créer une sauvegarde
            if not self._create_backup():
                return False
            
            # 3. Appliquer les modifications
            if not self._apply_modifications():
                return False
            
            # 4. Vérifier l'installation
            if not self._verify_installation():
                return False
            
            print("✅ Installation réussie !")
            print("📝 Consultez custom_features/README.md pour plus d'informations")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de l'installation : {e}")
            return False
    
    def uninstall(self) -> bool:
        """Désinstalle les fonctionnalités personnalisées"""
        print("🔄 Désinstallation des fonctionnalités personnalisées...")
        
        try:
            # Restaurer les fichiers de sauvegarde
            if self.backup_dir.exists():
                self._restore_backup()
                print("✅ Désinstallation réussie !")
                return True
            else:
                print("⚠️  Aucune sauvegarde trouvée")
                return False
                
        except Exception as e:
            print(f"❌ Erreur lors de la désinstallation : {e}")
            return False
    
    def _check_structure(self) -> bool:
        """Vérifie la structure du projet"""
        print("📋 Vérification de la structure...")
        
        required_files = [
            "ui/generation.py",
            "persistence.py", 
            "ui/settings.py",
            "settings.py"
        ]
        
        for file_path in required_files:
            if not (self.project_root / file_path).exists():
                print(f"❌ Fichier manquant : {file_path}")
                return False
        
        if not self.custom_features_dir.exists():
            print(f"❌ Dossier custom_features manquant")
            return False
        
        print("✅ Structure vérifiée")
        return True
    
    def _create_backup(self) -> bool:
        """Crée une sauvegarde des fichiers modifiés"""
        print("💾 Création de la sauvegarde...")
        
        try:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            
            self.backup_dir.mkdir()
            
            files_to_backup = [
                "ui/generation.py",
                "persistence.py",
                "ui/settings.py"
            ]
            
            for file_path in files_to_backup:
                src = self.project_root / file_path
                dst = self.backup_dir / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            
            print("✅ Sauvegarde créée")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde : {e}")
            return False
    
    def _apply_modifications(self) -> bool:
        """Applique les modifications aux fichiers"""
        print("🔧 Application des modifications...")
        
        modifications = [
            self._modify_generation_py,
            self._modify_persistence_py,
            self._modify_settings_py
        ]
        
        for modification in modifications:
            if not modification():
                return False
        
        print("✅ Modifications appliquées")
        return True
    
    def _modify_generation_py(self) -> bool:
        """Modifie ui/generation.py pour intégrer le panneau de métadonnées"""
        file_path = self.project_root / "ui/generation.py"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remplacer l'import de MetadataWidget
            if "class MetadataWidget(QWidget):" in content:
                # Supprimer la classe MetadataWidget existante
                start = content.find("class MetadataWidget(QWidget):")
                end = content.find("\n\n", start)
                if end == -1:
                    end = len(content)
                
                content = content[:start] + content[end:]
                
                # Ajouter l'import personnalisé
                import_line = "from ..custom_features import MetadataPanel\n"
                content = content.replace(
                    "from ..ui.theme import theme",
                    "from ..ui.theme import theme\n" + import_line
                )
                
                # Remplacer l'instanciation
                content = content.replace(
                    "self.metadata_widget = MetadataWidget(self)",
                    "self.metadata_widget = MetadataPanel(self)"
                )
                
                # Ajouter la connexion du paramètre de visibilité
                visibility_code = '''
        # Connecter le paramètre pour afficher/masquer l'interface des métadonnées
        from ..settings import settings
        self._metadata_visibility_connection = settings.changed.connect(self._update_metadata_visibility)
        self._update_metadata_visibility()
'''
                
                if "self._update_metadata_visibility()" not in content:
                    # Trouver où ajouter le code
                    insert_pos = content.find("self.update_generate_button()")
                    if insert_pos != -1:
                        content = content[:insert_pos] + visibility_code + content[insert_pos:]
                
                # Ajouter la méthode _update_metadata_visibility
                if "_update_metadata_visibility" not in content:
                    method_code = '''
    def _update_metadata_visibility(self):
        """Met à jour la visibilité de l'interface des métadonnées selon le paramètre"""
        from ..settings import settings
        self.metadata_widget.setVisible(settings.show_metadata_interface)
'''
                    
                    # Ajouter à la fin de la classe GenerationWidget
                    class_end = content.rfind("class GenerationWidget")
                    if class_end != -1:
                        # Trouver la fin de la classe
                        brace_count = 0
                        pos = class_end
                        while pos < len(content):
                            if content[pos] == '{':
                                brace_count += 1
                            elif content[pos] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    content = content[:pos] + method_code + content[pos:]
                                    break
                            pos += 1
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ ui/generation.py modifié")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de la modification de generation.py : {e}")
            return False
    
    def _modify_persistence_py(self) -> bool:
        """Modifie persistence.py pour intégrer la sauvegarde automatique"""
        file_path = self.project_root / "persistence.py"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ajouter l'import
            import_line = "from .custom_features import auto_save_job_images\n"
            content = content.replace(
                "from .settings import settings",
                "from .settings import settings\n" + import_line
            )
            
            # Ajouter l'appel de sauvegarde automatique
            if "auto_save_job_images" not in content:
                # Trouver la méthode _save_results
                method_start = content.find("def _save_results(self, job: Job):")
                if method_start != -1:
                    # Trouver la fin de la méthode
                    brace_count = 0
                    pos = method_start
                    while pos < len(content):
                        if content[pos] == '{':
                            brace_count += 1
                        elif content[pos] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Ajouter l'appel avant la fin
                                auto_save_code = '''
            # Auto-save generated images if enabled
            if settings.auto_save_generated:
                auto_save_job_images(self._model, job)
'''
                                content = content[:pos] + auto_save_code + content[pos:]
                                break
                        pos += 1
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ persistence.py modifié")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de la modification de persistence.py : {e}")
            return False
    
    def _modify_settings_py(self) -> bool:
        """Modifie ui/settings.py pour ajouter les onglets personnalisés"""
        file_path = self.project_root / "ui/settings.py"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ajouter l'import
            import_line = "from ..custom_features import custom_integration\n"
            content = content.replace(
                "from .settings_widgets import",
                "from .settings_widgets import\n" + import_line
            )
            
            # Ajouter les onglets dans SettingsDialog.__init__
            if "custom_integration" not in content:
                # Trouver la fin de __init__
                init_start = content.find("def __init__(self, server: Server):")
                if init_start != -1:
                    # Trouver la fin de la méthode
                    brace_count = 0
                    pos = init_start
                    while pos < len(content):
                        if content[pos] == '{':
                            brace_count += 1
                        elif content[pos] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                # Ajouter les onglets avant la fin
                                tabs_code = '''
        # Ajouter les onglets personnalisés
        auto_save_widget = custom_integration.get_auto_save_settings_widget()
        self.add_tab("Sauvegarde automatique", auto_save_widget)
        
        metadata_widget = custom_integration.get_metadata_settings_widget()
        self.add_tab("Métadonnées", metadata_widget)
'''
                                content = content[:pos] + tabs_code + content[pos:]
                                break
                        pos += 1
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print("✅ ui/settings.py modifié")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de la modification de settings.py : {e}")
            return False
    
    def _verify_installation(self) -> bool:
        """Vérifie que l'installation s'est bien passée"""
        print("🔍 Vérification de l'installation...")
        
        # Vérifier que les imports fonctionnent
        try:
            sys.path.insert(0, str(self.project_root))
            from custom_features import MetadataPanel, AutoSaveManager, custom_integration
            print("✅ Imports des fonctionnalités personnalisées OK")
            return True
        except ImportError as e:
            print(f"❌ Erreur d'import : {e}")
            return False
    
    def _restore_backup(self) -> bool:
        """Restaure les fichiers de sauvegarde"""
        try:
            files_to_restore = [
                "ui/generation.py",
                "persistence.py",
                "ui/settings.py"
            ]
            
            for file_path in files_to_restore:
                src = self.backup_dir / file_path
                dst = self.project_root / file_path
                if src.exists():
                    shutil.copy2(src, dst)
            
            # Supprimer la sauvegarde
            shutil.rmtree(self.backup_dir)
            
            print("✅ Fichiers restaurés")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors de la restauration : {e}")
            return False


def main():
    """Fonction principale du script d'installation"""
    if len(sys.argv) < 2:
        print("Usage: python install.py <install|uninstall> [project_root]")
        sys.exit(1)
    
    command = sys.argv[1]
    project_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    
    installer = CustomFeaturesInstaller(project_root)
    
    if command == "install":
        success = installer.install()
        sys.exit(0 if success else 1)
    elif command == "uninstall":
        success = installer.uninstall()
        sys.exit(0 if success else 1)
    else:
        print("Commandes disponibles : install, uninstall")
        sys.exit(1)


if __name__ == "__main__":
    main() 