# Project Development Guidelines

## Language and Internationalization

Follow an English-first, Chinese-supported design in all future development work. The conventions below distinguish language requirements from planned application features.

1. **Code and file naming.** Use English for all code, variable names, function names, class names, filenames, and code comments.
2. **README files.** Write `README.md` in English and `README_CN.md` in Simplified Chinese. Include a link to the other version in each file.
3. **GitHub and Git.** Use English for the GitHub repository name, its description, and all Git commit messages.
4. **Mock business data.** Use English for field names, hospital names, exception types, and status values.
5. **Technical documentation.** Use English as the primary language for architecture documents, API documentation, and test reports.
6. **Product requirements.** Provide both English and Simplified Chinese versions of each product requirements document (PRD).
7. **Streamlit language support.** Use English as the default application language. When language switching is implemented, support English and Simplified Chinese and allow for adding Traditional Chinese later.
8. **UI text.** Manage UI strings in centralized language resources. Keep localized strings out of business logic.
9. **AI-generated output.** When language selection is supported, generate AI analysis reports and natural-language answers in the user's selected language. Language selection must leave financial calculation logic and source data unchanged.
10. **Developer communication.** Use Chinese in day-to-day Codex conversations with the user, work reports, and technical explanations.
11. **Documentation accuracy.** Document the project's actual implementation status. Label planned features as planned until they are implemented.
