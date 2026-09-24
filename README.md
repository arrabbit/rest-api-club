# rest-api-club
REST API for campus clubs offering activities such as pottery workshops,  board game nights, and photography walks. The service manages events and lets existing participants register  or cancel bookings.

## Code & Documentation Standards
- **File Headers**: Each .py and .hs file must contain a header comment including a summary of the file's purpose, authors, and date
- **Function Documentation**: Every function must have an appropriate docstring (Python) or Haddock comment (Haskell) containing the function's purpose, any input parameters, and return value.
- **Inline Comments**Inline comments must be included to explain any confusing or tricky logic.
- **Modularity**: Individual functions should have a single purpose and should be kept under 25–30 lines whenever possible to maintain code abstraction and improve readability.
- **Coding Style**: Variables and functions must be in snake_case. Classes should be in PascalCase.

## Git Repo Policy
- All development must be done in each group member's respective branch (ex. ARR, DL, JS, JM)
- Upon the completion of a milestone, the code should be pushed to main to preserve the working version
- When merging an individual branch into main, the following requirements must be met:
  - The code being merged must be functional and improve on the existing main code
  - The group must be notified of the merge
  - The branch being merged to main must not include any compiled files or caches (e.g., __pycache__, .pyc, .o, .hi)
  - The .gitignore must be respected
- If an individual’s branch becomes obsolete, their branch should be deleted and re-created to copy the most current working version in main, or whichever branch the group decides is appropriate
