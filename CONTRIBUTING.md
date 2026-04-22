# 🤝 Contributing to Web Scraper Platform

Thank you for considering contributing to this project!

## 🐛 Reporting Bugs

- Use the Bug Report template in `.github/ISSUE_TEMPLATE/bug_report.md`
- Include as much detail as possible:
- - Operating system and version
- - Docker version
- - Steps to reproduce the bug
- - Expected vs actual behavior
- - Relevant logs from `docker logs`

## 💡 Suggesting Features

- Use the Feature Request template in `.github/ISSUE_TEMPLATE/feature_request.md`
- Clearly describe:
- - What the feature does
- - What problem it solves
- - How you envision using it
- - Any alternatives you've considered

## 🛠️ Development Setup

- Fork and clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/scraper.git
cd scraper
```

- Configure environment
```bash
cp .env.example .env
nano .env
```

- Start the development stack
```bash
docker compose up -d
```

- Verify services are running
```bash
docker compose ps
```

## 📥 Submitting Pull Requests

- Create a feature branch
```bash
git checkout -b feature/amazing-feature
```

- Make your changes and commit
```bash
git add .
git commit -m "Add amazing feature"
```

- Push to your fork
```bash
git push origin feature/amazing-feature
```

- Open a Pull Request on GitHub

## ✅ Code Standards

- Python: Follow PEP 8 style guide
- JavaScript/React: Use the provided ESLint configuration
- Comments: Document complex logic and public functions
- Testing: Add tests for new features when possible
- Commits: Use clear, descriptive commit messages

## 🐳 Docker Conventions

- Keep images as small as possible
- Use multi-stage builds when appropriate
- Follow Dockerfile best practices
- Test builds with `docker compose build`

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## ❓ Questions?

Feel free to open an issue or start a discussion on GitHub.

Thank you for helping improve this project! 🚀
