# Cấu hình riêng theo thư mục bằng include và includeIf

Một máy có thể làm việc với nhiều repository thuộc các tổ chức hoặc mục đích khác nhau. Bạn có thể cần dùng danh tính commit công việc trong các repository ở thư mục công ty, danh tính cá nhân trong các repository riêng, hoặc một nhóm thiết lập chỉ dành cho một dự án. Git hỗ trợ tách cấu hình thành nhiều file và tự động nạp chúng bằng `include` hoặc `includeIf`. Nhờ vậy, bạn có thể tổ chức cấu hình theo vị trí repository, nhánh đang checkout hoặc URL remote mà không phải sửa `user.name`, `user.email` và các tùy chọn khác mỗi lần chuyển dự án.

## 1. Git đọc cấu hình từ nhiều cấp

Git có thể lấy cấu hình từ nhiều file và nguồn khác nhau. Các cấp phổ biến, từ ưu tiên thấp lên cao, gồm:

| Cấp cấu hình | Phạm vi | Ví dụ vị trí hoặc cách đặt |
|---|---|---|
| System | Toàn bộ người dùng trên máy | File `gitconfig` trong thư mục cài đặt Git |
| Global | Người dùng hiện tại, áp dụng cho nhiều repository | `~/.gitconfig` hoặc `$XDG_CONFIG_HOME/git/config` |
| Local | Một repository và các worktree liên quan theo cấu hình mặc định | `$GIT_DIR/config` hoặc common config |
| Worktree | Một worktree cụ thể khi bật `extensions.worktreeConfig` | File `config.worktree` |
| Command | Một lần chạy lệnh cụ thể | `git -c key=value ...` hoặc biến môi trường cấu hình được hỗ trợ |

Giá trị ở cấp có ưu tiên cao hơn thường ghi đè giá trị cùng khóa ở cấp thấp hơn. Với một khóa đơn trị như `user.email`, Git thường dùng giá trị cuối cùng có hiệu lực. Một số khóa cho phép nhiều giá trị, ví dụ các quy tắc URL `insteadOf`, nên cần xem toàn bộ giá trị thay vì giả định chỉ có một.

Kiểm tra cấu hình cùng nguồn và cấp của nó:

```bash
git config --list --show-origin --show-scope
```

Kết quả giúp biết một giá trị đến từ file nào và thuộc cấp nào. Khi nghi ngờ cấu hình bị ghi đè, đây là lệnh nên chạy trước khi sửa file.

## 2. Tách cấu hình thành file bằng `include`

`include.path` yêu cầu Git đọc thêm một file cấu hình tại vị trí khai báo. Các mục trong file được include được xem như xuất hiện ngay tại vị trí của dòng include trong file cha.

Ví dụ, trong `~/.gitconfig`:

```ini
[include]
    path = ~/.gitconfig-common
```

File `~/.gitconfig-common` có thể chứa thiết lập dùng chung:

```ini
[init]
    defaultBranch = main
[pull]
    ff = only
[core]
    editor = code --wait
```

Khi Git đọc global config, nội dung file `.gitconfig-common` cũng được nạp ở cấp global. Bạn có thể đặt các thiết lập liên quan vào những file riêng, chẳng hạn một file cho editor, một file cho signing hoặc một file cho alias.

### 2.1. Đường dẫn của file được include

Giá trị `path` có thể là đường dẫn tuyệt đối hoặc tương đối:

- Đường dẫn bắt đầu bằng `~/` được mở rộng theo thư mục home của người dùng.
- Đường dẫn tương đối được tính từ thư mục chứa file cấu hình đang khai báo include.
- Đường dẫn có khoảng trắng cần được đặt trong giá trị cấu hình phù hợp; trong file INI, không cần shell quote nhưng cần bảo đảm toàn bộ đường dẫn nằm trên cùng một giá trị.

Ví dụ file cấu hình nằm trong thư mục home có thể dùng:

```ini
[include]
    path = config/git/aliases.ini
```

Git sẽ tìm file tương đối với thư mục chứa file cấu hình đó. Vì vậy, khi di chuyển file cấu hình cha sang vị trí khác, hãy kiểm tra lại các đường dẫn tương đối.

Trên Windows, Git chấp nhận dấu gạch chéo xuôi trong đường dẫn cấu hình, ví dụ:

```ini
[include]
    path = C:/Users/Alice/.gitconfig-common
```

Nếu tên thư mục có khoảng trắng, đặt toàn bộ đường dẫn sau `path =` làm một giá trị, ví dụ `C:/Users/Alice/Work Settings/git.ini`.

### 2.2. Include lồng nhau

Một file được include có thể tiếp tục include file khác. Điều này cho phép tổ chức cấu hình theo nhóm:

```ini
# ~/.gitconfig
[include]
    path = ~/.config/git/base.ini
```

```ini
# ~/.config/git/base.ini
[include]
    path = aliases.ini
[core]
    autocrlf = input
```

Các file include lồng nhau được đọc theo vị trí khai báo. Tránh tạo vòng lặp, ví dụ file A include B trong khi B lại include A. Cấu trúc vòng lặp khiến cấu hình khó hiểu và Git có thể dừng việc đọc khi phát hiện include lặp hoặc vượt giới hạn.

## 3. Dùng `includeIf` để nạp cấu hình có điều kiện

`includeIf` chỉ nạp file khi điều kiện được chỉ định thỏa mãn. Cú pháp tổng quát:

```ini
[includeIf "<condition>:<pattern>"]
    path = <config-file>
```

Git hỗ trợ một số loại điều kiện, trong đó thường dùng nhất là `gitdir`, `onbranch` và `hasconfig:remote.*.url`. Khả năng cụ thể phụ thuộc phiên bản Git; nếu lệnh không nhận diện điều kiện, hãy kiểm tra phiên bản Git đang cài và tài liệu tương ứng.

## 4. Chọn cấu hình theo thư mục repository bằng `gitdir`

Điều kiện `gitdir` kiểm tra đường dẫn tới thư mục Git (`$GIT_DIR`) của repository hiện tại. Đây là lựa chọn phổ biến để áp dụng danh tính hoặc thiết lập riêng cho các repository nằm dưới một thư mục nhất định.

Ví dụ trong `~/.gitconfig`:

```ini
[includeIf "gitdir:~/src/work/"]
    path = ~/.gitconfig-work

[includeIf "gitdir:~/src/personal/"]
    path = ~/.gitconfig-personal
```

File `~/.gitconfig-work`:

```ini
[user]
    name = Work Contributor
    email = work@example.invalid
[commit]
    gpgsign = true
```

File `~/.gitconfig-personal`:

```ini
[user]
    name = Personal Contributor
    email = personal@example.invalid
```

Khi Git hoạt động trong repository có thư mục Git nằm dưới `~/src/work/`, file công việc được include. Repository nằm dưới `~/src/personal/` nhận cấu hình cá nhân.

### 4.1. Pattern của `gitdir`

Pattern được so khớp với đường dẫn Git directory, không phải trực tiếp với đường dẫn file đang sửa. Một số quy tắc đáng chú ý:

- Pattern bắt đầu bằng `~/` được mở rộng theo home directory.
- Pattern bắt đầu bằng `./` được tính tương đối với file cấu hình chứa điều kiện.
- `*` khớp trong một phần đường dẫn; `**/` có thể khớp qua nhiều cấp thư mục.
- Pattern kết thúc bằng `/` được Git mở rộng để khớp các thư mục con bên dưới.
- `gitdir` phân biệt chữ hoa/chữ thường trên các hệ thống mà phép so khớp có phân biệt; dùng `gitdir/i` nếu muốn so khớp không phân biệt hoa thường.

Ví dụ cấu hình cho thư mục công việc trên Windows:

```ini
[includeIf "gitdir/i:C:/Users/Alice/Source/Work/"]
    path = C:/Users/Alice/.gitconfig-work
```

`gitdir/i` giúp pattern hoạt động ổn định hơn khi chữ hoa/thường trong đường dẫn thay đổi. Dùng dấu `/` trong pattern để tránh nhầm lẫn với ký tự escape của file cấu hình.

### 4.2. Chú ý khi dùng linked worktree

Với linked worktree, file `.git` trong thư mục làm việc là file trỏ tới metadata riêng của worktree. Giá trị `$GIT_DIR` thường nằm dưới thư mục quản trị chung của repository, ví dụ `.git/worktrees/<id>`, chứ không nằm dưới đường dẫn của thư mục worktree mà bạn nhìn thấy.

Do đó, điều kiện `gitdir:~/src/work/` có thể không khớp một linked worktree chỉ vì thư mục làm việc của nó nằm dưới `~/src/work/`; Git đang so khớp đường dẫn Git directory. Nếu cần cấu hình dựa trên nhánh đang checkout, xem điều kiện `onbranch`. Nếu cần phân biệt linked worktree theo vị trí vật lý, hãy xác minh giá trị thực tế bằng:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git rev-parse --git-common-dir
```

Không giả định thư mục worktree và Git directory luôn có cùng đường dẫn cha.

## 5. Chọn cấu hình theo branch bằng `onbranch`

Điều kiện `onbranch` kiểm tra tên branch đang checkout. Nó hữu ích khi bạn muốn bật một số thiết lập trong một nhóm nhánh, bất kể repository nằm ở thư mục nào.

Ví dụ:

```ini
[includeIf "onbranch:release/"]
    path = ~/.gitconfig-release

[includeIf "onbranch:feature/experiment"]
    path = ~/.gitconfig-experiment
```

Với branch `release/2.0`, file `~/.gitconfig-release` được include. Với branch `feature/experiment`, file cấu hình thứ hai được include.

Pattern kết thúc bằng `/` được hiểu là khớp các branch có tiền tố tương ứng. `onbranch` phụ thuộc branch hiện tại; khi ở detached HEAD, điều kiện theo branch không khớp như khi đang checkout một branch có tên.

Một số cấu hình có thể phù hợp theo branch, ví dụ bật signing cho nhánh release hoặc đặt một alias/thiết lập dành riêng cho quy trình phát hành. Tuy nhiên, `user.name` và `user.email` thường nên được gắn với danh tính hoặc repository, không nên thay đổi tùy tiện chỉ vì chuyển sang một branch khác.

## 6. Chọn cấu hình theo URL remote bằng `hasconfig`

Git hỗ trợ điều kiện `hasconfig:remote.*.url:<pattern>` để include file nếu một URL remote trong cấu hình hiện tại khớp pattern. Điều này hữu ích khi repository được clone ở nhiều vị trí khác nhau nhưng vẫn thuộc cùng một máy chủ hoặc tổ chức.

Ví dụ:

```ini
[includeIf "hasconfig:remote.*.url:https://github.com/acme/**"]
    path = ~/.gitconfig-acme
```

Khi một remote URL khớp `https://github.com/acme/**`, Git nạp file `~/.gitconfig-acme`. Pattern URL hỗ trợ cú pháp glob; hãy kiểm tra URL thực tế bằng `git remote -v` trước khi xây dựng điều kiện.

Điều kiện này có quy tắc đặc biệt để tránh vòng lặp khi Git phải đọc URL nhằm quyết định include: file được include bởi `hasconfig:remote.*.url` không được định nghĩa thêm remote URL. Hãy để các khai báo `[remote "..."]` ở cấu hình thông thường và chỉ đặt những thiết lập cần điều kiện trong file được include.

`hasconfig` có ở các phiên bản Git mới hơn. Nếu đang dùng Git cũ, dùng `gitdir` hoặc cấu hình global/local rõ ràng thay thế.

## 7. Kết hợp nhiều điều kiện

Bạn có thể khai báo nhiều `includeIf` trong cùng file. Mỗi điều kiện được đánh giá riêng; các file tương ứng có thể cùng được nạp nếu nhiều điều kiện thỏa mãn.

Ví dụ:

```ini
[includeIf "gitdir:~/src/work/"]
    path = ~/.gitconfig-work

[includeIf "onbranch:release/"]
    path = ~/.gitconfig-release
```

Khi đang làm việc trong repository dưới `~/src/work/` và checkout branch `release/2.0`, cả hai file có thể được include. Nếu hai file cùng đặt `user.email`, giá trị có hiệu lực phụ thuộc thứ tự đọc và cấp cấu hình; hãy xem `git config --show-origin --show-scope --get-all user.email` để biết các giá trị đến từ đâu.

Không nên tạo quá nhiều điều kiện chồng lấn cho cùng một khóa. Nếu một giá trị bị thay đổi ngoài ý muốn, hãy thu hẹp pattern hoặc gom thiết lập về một file duy nhất có trách nhiệm rõ ràng.

## 8. Include không tạo ra một cấp cấu hình mới

Một điểm quan trọng: file được include không có cấp ưu tiên riêng. Nó được đọc như một phần của file cấu hình đang include nó.

Ví dụ, `~/.gitconfig` ở cấp global include `~/.gitconfig-work`. Các giá trị trong file work cũng được xem là giá trị global. Chúng không trở thành local chỉ vì file được include có tên riêng hoặc nằm trong một thư mục khác.

Tương tự, nếu `.git/config` của repository include một file khác, các giá trị trong file đó được đọc ở cấp local. Nếu cấu hình worktree được bật và file `config.worktree` include một file, các giá trị được đọc trong ngữ cảnh worktree.

Thứ tự include cũng có ý nghĩa. Nội dung file được include xuất hiện tại vị trí khai báo trong quá trình đọc. Nếu cùng một khóa đơn trị được đặt nhiều lần ở cùng cấp, giá trị được đọc sau thường có hiệu lực. Cấp cấu hình cao hơn vẫn có thể ghi đè giá trị từ cấp thấp hơn.

## 9. Tạo cấu hình danh tính theo thư mục một cách thực tế

Một cách tổ chức đơn giản là giữ global config làm file điều phối và tách danh tính thành hai file:

`~/.gitconfig`:

```ini
[user]
    name = Default Contributor
    email = default@example.invalid

[includeIf "gitdir:~/src/company/"]
    path = ~/.gitconfig-company

[includeIf "gitdir:~/src/oss/"]
    path = ~/.gitconfig-oss
```

`~/.gitconfig-company`:

```ini
[user]
    name = Company Contributor
    email = company@example.invalid
```

`~/.gitconfig-oss`:

```ini
[user]
    name = Open Source Contributor
    email = oss@example.invalid
```

Với cấu trúc này, repository trong `~/src/company/` dùng danh tính công việc; repository trong `~/src/oss/` dùng danh tính đóng góp mã nguồn mở; repository ở vị trí khác dùng danh tính mặc định.

Sau khi tạo file, hãy xác nhận đường dẫn Git directory thực tế của repository có khớp pattern không. Một repository có thể được clone ở vị trí khác, dùng linked worktree hoặc có `.git` file trỏ tới thư mục quản trị khác. Không dựa vào đường dẫn hiển thị trong File Explorer mà bỏ qua `$GIT_DIR`.

## 10. Kiểm tra file cấu hình và nguồn giá trị

Các lệnh sau giúp chẩn đoán cấu hình sau khi thêm include:

```bash
git config --list --show-origin --show-scope
git config --show-origin --show-scope --get user.name
git config --show-origin --show-scope --get user.email
git config --show-origin --show-scope --get-all user.email
```

- `--list` hiển thị các mục cấu hình đang có hiệu lực.
- `--show-origin` hiển thị file hoặc nguồn tạo ra giá trị.
- `--show-scope` hiển thị cấp cấu hình như system, global, local, worktree hoặc command.
- `--get-all` liệt kê mọi giá trị của khóa có thể xuất hiện nhiều lần.

Nếu một file include không được nạp, kiểm tra:

1. File cấu hình cha có đúng cú pháp INI và đúng tên section không.
2. Đường dẫn sau `path` có tồn tại và được tính từ đúng vị trí không.
3. Điều kiện `gitdir`, `onbranch` hoặc URL có khớp trạng thái thực tế không.
4. Phiên bản Git có hỗ trợ loại điều kiện đang dùng không.
5. Một file cấu hình ở cấp cao hơn có đang ghi đè giá trị vừa include không.

Để xem vị trí hiện tại và branch:

```bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git branch --show-current
git remote -v
```

Đối chiếu kết quả với pattern điều kiện. `git branch --show-current` trả về rỗng khi HEAD detached; khi đó điều kiện `onbranch` không được kích hoạt như lúc checkout branch thông thường.

## 11. Chỉnh sửa cấu hình đúng cấp

Bạn có thể mở global config bằng:

```bash
git config --global --edit
```

Mở cấu hình local của repository hiện tại:

```bash
git config --local --edit
```

Đặt một giá trị qua lệnh thay vì sửa file trực tiếp:

```bash
git config --global user.name "Default Contributor"
git config --global user.email "default@example.invalid"
```

Nếu muốn thêm một include vào global config:

```bash
git config --global include.path ~/.gitconfig-common
```

Với nhiều include cùng section, dùng `--add` để thêm thay vì thay giá trị đã có:

```bash
git config --global --add include.path ~/.gitconfig-aliases
```

Các điều kiện `includeIf` thường dễ đọc và dễ review hơn khi khai báo trực tiếp trong file INI. Nếu dùng `git config` để đặt khóa có dấu chấm trong tên section, hãy bảo đảm cú pháp section và tên khóa được truyền đúng; kiểm tra lại bằng `git config --list --show-origin` sau khi ghi.

## 12. Những lỗi thường gặp và cách tránh

- **Dùng `gitdir` để so khớp đường dẫn working tree.** Điều kiện này so khớp `$GIT_DIR`; với linked worktree, đường dẫn đó thường nằm dưới thư mục quản trị chung.
- **Quên dấu `/` ở cuối pattern thư mục.** Pattern kết thúc bằng `/` có hành vi khớp đệ quy thuận tiện; nếu bỏ dấu này, pattern có thể không khớp các cấp con như mong muốn.
- **Đặt file include tương đối nhưng tính sai thư mục gốc.** Đường dẫn tương đối được tính từ file cấu hình chứa directive.
- **Cho rằng file được include có cấp ưu tiên riêng.** Nó kế thừa scope của file cha; giá trị vẫn có thể bị ghi đè bởi cấp cao hơn.
- **Tạo nhiều include cùng sửa một khóa mà không kiểm tra thứ tự.** Dùng `--show-origin`, `--show-scope` và `--get-all` để tìm nguồn.
- **Dùng `onbranch` khi HEAD detached.** Không có tên branch hiện tại để điều kiện khớp.
- **Định nghĩa remote URL trong file include có điều kiện `hasconfig`.** Quy tắc này có thể gây lỗi hoặc vòng lặp; remote URL nên được khai báo ở cấu hình thông thường.
- **Dùng tính năng mới trên Git cũ.** Kiểm tra `git --version` và tài liệu theo phiên bản trước khi phụ thuộc vào `onbranch` hoặc `hasconfig`.
- **Đưa thông tin bí mật vào file cấu hình được chia sẻ.** Không lưu token, mật khẩu hoặc private key trong file global/local được commit hay chia sẻ ngoài phạm vi cần thiết.

## 13. Quy trình thiết lập và xác minh

Khi cần cấu hình riêng theo thư mục repository:

1. Xác định thư mục chứa các repository và lấy `$GIT_DIR` thực tế bằng `git rev-parse --git-dir`.
2. Chọn khóa cần tách, thường là `user.name`, `user.email`, signing hoặc một số alias/thiết lập cá nhân.
3. Tạo file cấu hình riêng với các section cần thiết.
4. Thêm `includeIf "gitdir:<pattern>"` vào global config và trỏ `path` tới file riêng.
5. Mở repository thuộc phạm vi để kiểm tra `git config --list --show-origin --show-scope`.
6. Kiểm tra các repository ngoài phạm vi để bảo đảm cấu hình mặc định vẫn được dùng.
7. Nếu dùng linked worktree, kiểm tra `$GIT_DIR` của từng worktree trước khi kết luận pattern đã đúng.
8. Ghi lại quy tắc trong tài liệu nhóm nếu nó ảnh hưởng tới cách tạo commit hoặc phát hành.

Ví dụ xác minh danh tính đang dùng:

```bash
git config --show-origin --show-scope --get user.name
git config --show-origin --show-scope --get user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Hai lệnh `git var` cho biết danh tính tác giả và người tạo commit mà Git sẽ dùng tại repository hiện tại. Chúng hữu ích để xác nhận cấu hình include đã tạo ra đúng danh tính trước khi commit.

## 14. Ghi nhớ

`include` tách cấu hình thành các file dễ quản lý; `includeIf` chỉ nạp file khi repository, branch hoặc remote thỏa điều kiện. Với cấu hình theo thư mục, `gitdir` so khớp đường dẫn Git directory, nên cần kiểm tra `$GIT_DIR` thực tế, đặc biệt trong linked worktree. File được include kế thừa cấp cấu hình của file cha và vẫn chịu thứ tự ưu tiên system, global, local, worktree, command. Dùng `git config --show-origin --show-scope` để biết chính xác giá trị đang đến từ đâu trước khi chỉnh sửa.
