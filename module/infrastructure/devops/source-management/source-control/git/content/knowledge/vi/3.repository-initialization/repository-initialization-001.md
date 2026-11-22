# Tạo kho mã bằng git init và xác định thư mục gốc

Git quản lý lịch sử dự án trong một **repository** (kho mã). Khi bắt đầu một dự án mới, bạn có thể tạo repository ngay trong thư mục làm việc bằng `git init`. Lệnh này thiết lập vùng dữ liệu nội bộ để Git lưu object, refs và cấu hình; các tệp dự án hiện có vẫn nằm trong working tree và chưa tự động được đưa vào lịch sử.

Sau khi khởi tạo, cần biết chính xác đâu là **thư mục gốc của working tree** và đâu là **thư mục Git quản lý dữ liệu nội bộ**. Hai vị trí này thường liên quan đến nhau nhưng không phải lúc nào cũng cùng một dạng: repository thông thường có thư mục `.git` bên trong project root, còn linked worktree hoặc submodule có thể dùng file `.git` trỏ đến Git directory ở vị trí khác.

## 1. Repository và working tree

Một repository Git thông thường có hai phần:

- **Working tree:** các thư mục và tệp dự án mà bạn trực tiếp đọc, sửa và chạy.
- **Git directory:** vùng dữ liệu nội bộ chứa object database, refs, cấu hình, index và các metadata khác.

Ví dụ cấu trúc đơn giản:

```text
sample-app/
├── .git/              <- Git directory
│   ├── HEAD
│   ├── config
│   ├── objects/
│   ├── refs/
│   └── hooks/
├── src/               <- working tree
├── README.md
└── package.json
```

Khi chạy `git init` trong `sample-app`, Git tạo vùng dữ liệu quản lý tại `.git`. Lệnh không tự tạo commit đầu tiên, không tự stage các tệp và không tải lịch sử từ máy chủ. Bạn vẫn cần chọn tệp, đưa vào index và commit theo quy trình riêng.

## 2. Khởi tạo repository trong thư mục hiện tại

Tạo thư mục dự án và chuyển vào đó:

```bash
mkdir sample-app
cd sample-app
```

Khởi tạo repository:

```bash
git init
```

Git thường hiển thị thông báo cho biết repository đã được khởi tạo và đường dẫn Git directory. Sau đó kiểm tra:

```bash
git status
git rev-parse --show-toplevel
git rev-parse --git-dir
```

`git status` thường báo đang ở nhánh chưa có commit (unborn branch) và có thể liệt kê các tệp chưa được theo dõi nếu thư mục đã chứa nội dung. `git rev-parse --show-toplevel` in ra đường dẫn tuyệt đối của working tree root. `git rev-parse --git-dir` in ra đường dẫn Git directory, có thể là đường dẫn tương đối tùy ngữ cảnh.

Nếu thư mục đã có sẵn mã nguồn, bạn không cần tạo thư mục mới. Chỉ cần chuyển đến đúng thư mục dự án rồi chạy `git init` tại đó.

## 3. Khởi tạo repository trong một thư mục đích

Bạn cũng có thể truyền đường dẫn thư mục trực tiếp cho `git init`:

```bash
git init sample-app
```

Lệnh khởi tạo repository tại `sample-app`; Git tạo thư mục đích nếu cần. Nếu muốn chỉ định nhánh ban đầu:

```bash
git init --initial-branch=main sample-app
```

Hoặc dùng dạng ngắn `-b`:

```bash
git init -b main sample-app
```

Sau đó vào dự án và kiểm tra:

```bash
cd sample-app
git status
git branch --show-current
```

Tên nhánh ban đầu chỉ là tên nhánh được Git chuẩn bị cho repository mới. Nhánh này chưa có commit cho đến khi bạn tạo commit đầu tiên.

## 4. Chọn tên nhánh mặc định

Nếu thường xuyên tạo repository mới và muốn dùng `main` làm tên nhánh mặc định, cấu hình:

```bash
git config --global init.defaultBranch main
```

Kiểm tra giá trị:

```bash
git config --show-origin --get init.defaultBranch
```

Sau đó, khi chạy `git init` mà không chỉ định `-b` hoặc `--initial-branch`, Git sử dụng tên nhánh mặc định đã cấu hình nếu có. Tùy chọn chỉ định nhánh ngay trên dòng lệnh có hiệu lực cho lần khởi tạo đó.

Lưu ý: cấu hình `init.defaultBranch` ảnh hưởng repository được khởi tạo mới. Nó không tự đổi tên nhánh hiện tại của repository đã tồn tại. Để đổi tên nhánh local hiện tại, dùng lệnh riêng như `git branch -m main` và cập nhật remote theo quy trình của dự án nếu nhánh đã được chia sẻ.

## 5. Điều gì được tạo trong `.git`?

Trong repository thông thường, `.git` là thư mục điều khiển của Git. Một số thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| `HEAD` | Cho biết checkout hiện tại; thường là symbolic ref đến nhánh đang làm việc |
| `config` | Cấu hình riêng của repository |
| `objects/` | Object database chứa blob, tree, commit, tag và packfile |
| `refs/` | Các ref như nhánh và tag ở dạng loose ref |
| `hooks/` | Vị trí mặc định cho các hook của repository |
| `index` | Staging area, lưu trạng thái sẽ được dùng cho commit tiếp theo |
| `logs/` | Reflog nếu được bật cho các ref tương ứng |
| `info/` | Một số cấu hình local, ví dụ `exclude` |

Không phải tất cả thành phần đều phải xuất hiện ngay sau `git init`. Ví dụ, index có thể được tạo khi bạn bắt đầu stage tệp; refs của nhánh có thể chưa có commit để trỏ đến; reflog và packfile phụ thuộc thao tác tiếp theo.

Thông thường, không chỉnh sửa trực tiếp các file nội bộ trong `.git`. Hãy dùng lệnh Git để thay đổi cấu hình, index, refs và lịch sử nhằm giữ đúng các kiểm tra và quy tắc nội bộ.

## 6. Xác định thư mục gốc khi đang ở thư mục con

Bạn không cần phải đứng đúng thư mục gốc mới chạy được lệnh Git. Git tìm repository từ thư mục hiện tại và các thư mục cha. Ví dụ:

```text
sample-app/              <- repository root
├── .git/
├── src/
│   └── services/
│       └── auth/
│           └── token.js  <- terminal đang đứng ở đây
└── README.md
```

Nếu terminal đang ở `src/services/auth`, các lệnh sau vẫn làm việc với repository `sample-app`:

```bash
git status
git rev-parse --show-toplevel
git rev-parse --show-prefix
git rev-parse --show-cdup
```

Ý nghĩa:

- `--show-toplevel`: in đường dẫn tuyệt đối đến working tree root.
- `--show-prefix`: in đường dẫn tương đối từ root đến thư mục hiện tại, thường có dấu `/` ở cuối; tại root, kết quả rỗng.
- `--show-cdup`: in chuỗi `../` cần đi lên để đến root; tại root, kết quả rỗng.

Các lệnh này giúp script xác định đường dẫn dự án mà không phải đoán dựa trên tên thư mục hiện tại hoặc vị trí terminal.

## 7. Phân biệt working tree root và Git directory

Để xem hai vị trí riêng biệt:

```bash
# Root của working tree
git rev-parse --show-toplevel

# Git directory được dùng bởi repository hiện tại
git rev-parse --git-dir

# Đường dẫn tuyệt đối đến Git directory
git rev-parse --absolute-git-dir

# Common Git directory, hữu ích với linked worktree
git rev-parse --git-common-dir
```

Với repository thông thường, `--show-toplevel` thường là thư mục chứa `.git`, còn `--absolute-git-dir` là đường dẫn đến `.git`. Với linked worktree, Git directory riêng của worktree có thể nằm trong thư mục quản lý worktree, trong khi common Git directory chứa dữ liệu dùng chung. Vì vậy, không nên tự ghép chuỗi `root + ".git"` để suy ra Git directory.

Bạn cũng có thể chủ động đặt Git directory ở vị trí khác khi khởi tạo bằng `--separate-git-dir`:

```bash
git init --separate-git-dir=/srv/git/sample-app.git /work/sample-app
```

Trong ví dụ, `/work/sample-app` là working tree, còn `/srv/git/sample-app.git` là Git directory. Git tạo một file `.git` trong working tree để trỏ đến Git directory bên ngoài. Vì vậy, `.git` trong project có thể là file văn bản chứ không phải thư mục. Kiểm tra bằng các lệnh của Git:

```bash
git -C /work/sample-app rev-parse --show-toplevel
git -C /work/sample-app rev-parse --absolute-git-dir
```

Không xóa hoặc di chuyển riêng file `.git` đó mà không cập nhật liên kết đến Git directory; nếu cần di chuyển repository, hãy dùng quy trình hỗ trợ và xác minh lại cả hai đường dẫn.

Nếu chỉ muốn chạy lệnh trong một thư mục cụ thể mà không đổi vị trí terminal, dùng `git -C`:

```bash
git -C /path/to/sample-app rev-parse --show-toplevel
git -C /path/to/sample-app status
```

Trên Windows, thay đường dẫn bằng đường dẫn hợp lệ của môi trường đang dùng, ví dụ `C:/Projects/sample-app` trong Git Bash hoặc `C:\Projects\sample-app` trong PowerShell.

## 8. Kiểm tra có đang ở trong working tree hay không

Trong script hoặc khi chẩn đoán, có thể kiểm tra trạng thái repository:

```bash
git rev-parse --is-inside-work-tree
git rev-parse --is-bare-repository
```

Kết quả thường là `true` hoặc `false`:

| Lệnh | `true` có nghĩa |
|---|---|
| `--is-inside-work-tree` | Lệnh đang chạy trong một working tree |
| `--is-bare-repository` | Repository hiện tại là bare repository |

Nếu lệnh `git rev-parse --show-toplevel` báo lỗi, bạn có thể đang ở ngoài repository hoặc trong một bare repository không có working tree. Hãy kiểm tra `--is-bare-repository` và đường dẫn hiện tại trước khi chạy các lệnh yêu cầu working tree.

Một cách kiểm tra gọn trong shell:

```bash
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Đang ở trong working tree"
    git rev-parse --show-toplevel
else
    echo "Không ở trong working tree"
fi
```

Ví dụ trên phù hợp để phát hiện ngữ cảnh. Với script production, hãy xử lý cả trường hợp lệnh Git không tồn tại, repository bị lỗi hoặc quyền truy cập không đủ.

## 9. Bare repository và repository có working tree

Thông thường, `git init` tạo repository có working tree. Bạn cũng có thể tạo **bare repository**:

```bash
git init --bare sample-app.git
```

Bare repository chứa dữ liệu Git nhưng không có working tree để bạn trực tiếp sửa tệp. Nó thường được dùng làm repository trung tâm trên máy chủ hoặc nơi nhận push.

So sánh:

| Đặc điểm | Repository thông thường | Bare repository |
|---|---|---|
| Working tree | Có | Không |
| Git directory | Thường là `.git` trong project root | Chính thư mục repository, ví dụ `sample-app.git` |
| `git rev-parse --is-bare-repository` | `false` | `true` |
| `git rev-parse --show-toplevel` | Trả về working tree root | Không có working tree root để trả về |
| Sử dụng phổ biến | Phát triển và sửa mã nguồn | Chia sẻ repository, nhận push, lưu trữ trung tâm |

Không chạy các lệnh thao tác working tree như `git add` hoặc chỉnh sửa tệp dự án trực tiếp trong bare repository. Hãy clone bare repository ra một working copy để phát triển.

## 10. Reinitialize một repository đã tồn tại

Nếu chạy `git init` trong một repository đã được khởi tạo, Git thường báo repository đã tồn tại và giữ lại dữ liệu hiện có. Việc chạy lại `git init` có thể cập nhật một số cấu hình hoặc template theo tùy chọn, nhưng không phải lệnh xóa lịch sử hay tạo lại repository từ đầu.

```bash
git init
```

Không dùng `git init` như cách sửa một repository bị hỏng khi chưa hiểu nguyên nhân. Nếu `.git` bị thiếu, bị thay đổi hoặc repository dùng linked worktree, cần xác định đúng Git directory và tình trạng object database trước khi can thiệp.

## 11. Tránh khởi tạo nhầm repository lồng nhau

Git tìm repository bằng cách đi từ thư mục hiện tại lên các thư mục cha để tìm metadata Git. Nếu bạn vô tình chạy `git init` bên trong một thư mục con của repository hiện có, bạn có thể tạo một repository lồng nhau:

```text
workspace/
├── .git/               <- repository cha
├── src/
└── tools/
    └── helper/         <- vô tình chạy git init ở đây
        └── .git/       <- repository lồng nhau
```

Khi đó, các lệnh Git chạy trong `tools/helper` sẽ làm việc với repository lồng nhau. Từ góc nhìn repository cha, thư mục con này có thể bị xem như một repository nhúng; khi thêm nó, Git có thể cảnh báo về embedded repository.

Trước khi khởi tạo, kiểm tra vị trí hiện tại và repository mà Git đang nhận diện:

```bash
pwd
git rev-parse --show-toplevel
git rev-parse --show-prefix
```

Trên PowerShell, dùng `Get-Location` để xem thư mục hiện tại:

```powershell
Get-Location
git rev-parse --show-toplevel
```

Nếu mục tiêu là thêm một dự án con độc lập vào dự án cha, hãy quyết định rõ có nên dùng submodule hay không. Không tạo repository lồng nhau chỉ vì muốn Git bỏ qua một số tệp; `.gitignore` là cơ chế phù hợp cho mục đích đó.

## 12. Quy trình khởi tạo repository mới

Một quy trình cơ bản cho dự án mới:

```bash
# 1. Tạo thư mục dự án và vào đúng vị trí
mkdir sample-app
cd sample-app

# 2. Khởi tạo repository với nhánh main
git init --initial-branch=main

# 3. Xác nhận repository root và trạng thái
git rev-parse --show-toplevel
git rev-parse --is-inside-work-tree
git status

# 4. Tạo nội dung ban đầu
printf "# Sample App\n" > README.md

# 5. Stage và kiểm tra
git add README.md
git status --short
git diff --cached

# 6. Tạo commit đầu tiên
git commit -m "Initial commit"
```

Sau commit đầu tiên, kiểm tra nhánh và lịch sử:

```bash
git branch --show-current
git log --oneline --decorate -1
git status
```

Lúc này repository đã có commit đầu tiên. Nếu cần chia sẻ với remote, cấu hình remote và push theo quy trình riêng:

```bash
git remote add origin <repository-url>
git push -u origin main
```

`git init` chỉ tạo repository local. Remote, xác thực và quyền push là các bước độc lập.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `git init` tự đưa toàn bộ tệp vào commit | Không. Nó khởi tạo Git directory; bạn vẫn phải stage và commit. |
| `git init` tải lịch sử từ GitHub hoặc máy chủ | Không. Muốn lấy repository có sẵn, dùng `git clone`. |
| Thư mục gốc luôn là nơi terminal đang đứng | Không. Git tìm repository từ thư mục hiện tại lên thư mục cha; dùng `--show-toplevel` để xác định root. |
| Git directory luôn là thư mục `.git` nằm trong project | Không. Linked worktree, submodule hoặc `--separate-git-dir` có thể dùng Git directory ở vị trí khác. |
| `git init` chạy lần hai sẽ xóa lịch sử cũ | Thông thường không. Git nhận diện repository đã tồn tại và giữ lại dữ liệu hiện có. |
| Bare repository có thể sửa mã nguồn trực tiếp | Bare repository không có working tree; hãy clone ra một working copy để phát triển. |
| `init.defaultBranch` đổi tên nhánh của mọi repository hiện tại | Không. Nó đặt tên nhánh ban đầu cho repository mới. |
| Chạy `git init` trong thư mục con luôn dùng repository cha | Nếu thư mục con có Git metadata riêng, Git sẽ nhận repository lồng nhau ở đó. |

## 14. Tự kiểm tra

1. **Lệnh nào khởi tạo repository Git trong thư mục hiện tại?**
   - `git init`.
2. **Lệnh nào khởi tạo repository với nhánh ban đầu là `main`?**
   - `git init --initial-branch=main` hoặc `git init -b main`.
3. **Lệnh nào in ra thư mục gốc của working tree?**
   - `git rev-parse --show-toplevel`.
4. **Lệnh nào cho biết Git directory thực tế?**
   - `git rev-parse --absolute-git-dir`.
5. **`git init` có tự tạo commit đầu tiên không?**
   - Không. Cần stage tệp và chạy `git commit`.
6. **Bare repository khác repository thông thường ở điểm nào?**
   - Bare repository không có working tree và thường dùng làm nơi chia sẻ/nhận push.
7. **Vì sao cần kiểm tra root trước khi chạy `git init`?**
   - Để tránh vô tình tạo repository lồng nhau ở thư mục con của một dự án đã có Git.

## Kết luận

`git init` tạo repository Git local trong thư mục được chỉ định; nó không tự stage tệp, tạo commit hay kết nối remote. Dùng `--initial-branch` hoặc `init.defaultBranch` để chọn nhánh ban đầu. Khi cần xác định vị trí, `git rev-parse --show-toplevel` trả về working tree root còn `--absolute-git-dir` cho biết Git directory thực tế. Phân biệt hai vị trí này, nhận biết bare repository và kiểm tra thư mục hiện tại trước khi khởi tạo sẽ giúp tránh tạo nhầm repository lồng nhau.
