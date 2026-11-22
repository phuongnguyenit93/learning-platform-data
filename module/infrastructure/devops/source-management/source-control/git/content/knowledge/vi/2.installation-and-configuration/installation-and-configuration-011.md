# Thiết lập terminal, màu hiển thị và cách đọc thông báo lỗi

Terminal là nơi bạn nhập lệnh Git, xem trạng thái repository và đọc kết quả của từng thao tác. Một terminal được cấu hình phù hợp giúp lệnh dễ đọc, tên file tiếng Việt hiển thị đúng, diff có màu và thông báo lỗi không bị trôi khỏi màn hình. Khi Git báo lỗi, điều quan trọng là đọc đủ thông tin để xác định lệnh thất bại ở bước nào trước khi chọn cách xử lý.

Bài này tập trung vào môi trường terminal/shell, cách cấu hình màu và pager, cách hiển thị tên file có ký tự Unicode, cùng phương pháp phân tích các thông báo lỗi Git thường gặp. Những cấu hình được trình bày có thể đặt ở phạm vi global cho tài khoản hoặc local cho một repository.

## 1. Phân biệt terminal, shell và Git

Ba thành phần thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

- **Terminal emulator** là ứng dụng hiển thị cửa sổ dòng lệnh, nhận bàn phím và hiển thị văn bản, màu ANSI. Ví dụ: Windows Terminal, Terminal trên macOS hoặc ứng dụng Terminal của Linux.
- **Shell** là chương trình đọc và thực thi lệnh bạn nhập. Ví dụ: PowerShell, Git Bash, Bash hoặc Zsh.
- **Git** là chương trình được shell gọi để thao tác repository.

Một số lựa chọn phổ biến:

| Hệ điều hành | Terminal có thể dùng | Shell thường gặp |
|---|---|---|
| Windows | Windows Terminal, terminal tích hợp trong IDE | PowerShell, Git Bash |
| macOS | Terminal, iTerm2 | Zsh, Bash |
| Linux | GNOME Terminal, Konsole và các terminal khác | Bash, Zsh |

Các lệnh Git cơ bản giống nhau giữa những shell này. Tuy nhiên, cú pháp điều hướng thư mục, biến môi trường và dấu nháy có thể khác nhau. Ví dụ, PowerShell dùng `Get-Location` để xem thư mục hiện tại, trong khi Bash/Zsh thường dùng `pwd`.

Trước khi chạy lệnh, hãy bảo đảm terminal đang đứng trong repository dự định thao tác. Có thể kiểm tra:

```bash
git --version
git rev-parse --show-toplevel
git status
```

- `git --version` xác nhận Git đã được cài và có thể chạy từ shell hiện tại.
- `git rev-parse --show-toplevel` in ra thư mục gốc của repository.
- `git status` cho biết branch hiện tại và các thay đổi trong working tree/index.

Nếu lệnh thứ hai báo không phải repository, hãy chuyển tới thư mục dự án trước khi chạy các lệnh Git cần repository.

## 2. Chọn terminal dễ đọc và hỗ trợ Unicode

Terminal nên dùng font monospace có đủ ký tự bạn thường làm việc, hỗ trợ UTF-8 và hiển thị màu ANSI. Những điều này đặc biệt hữu ích khi repository có tên file hoặc thông điệp commit bằng tiếng Việt.

Trên Windows, bạn có thể dùng Windows Terminal với PowerShell hoặc Git Bash. Git Bash thường thuận tiện nếu bạn muốn dùng các lệnh kiểu Unix như `pwd`, `ls`, `grep` và pager `less`. PowerShell tích hợp tốt với Windows và vẫn chạy Git CLI bình thường.

Trên macOS và Linux, Terminal mặc định cùng Bash/Zsh thường đã hỗ trợ UTF-8. Nếu ký tự tiếng Việt bị hiển thị thành ô vuông hoặc dấu hỏi, kiểm tra encoding/locale và font của terminal. Đổi font hoặc encoding terminal không làm thay đổi nội dung được lưu trong repository.

Git có tùy chọn `core.quotepath` để điều khiển cách hiển thị tên đường dẫn chứa ký tự ngoài ASCII. Đặt:

```bash
git config --global core.quotepath false
```

Git sẽ hiển thị tên file Unicode trực tiếp thay vì dùng dạng escape cho các ký tự ngoài ASCII trong một số đầu ra. Cấu hình này chỉ ảnh hưởng cách Git trích dẫn đường dẫn khi hiển thị; nó không chuyển đổi encoding của file và cũng không thay thế cấu hình UTF-8 của terminal.

Nếu chỉ muốn áp dụng cho một repository:

```bash
git config --local core.quotepath false
```

Kiểm tra giá trị và nơi khai báo:

```bash
git config --show-origin --get core.quotepath
```

Trên các phiên bản Windows/console cũ, code page có thể ảnh hưởng cách hiển thị. Trong Command Prompt có thể kiểm tra bằng `chcp`; nếu cần UTF-8, có thể thử `chcp 65001` trong cửa sổ hiện tại. Đây là thiết lập của phiên console, không phải cấu hình repository. Windows Terminal và các shell hiện đại thường xử lý Unicode tốt hơn nếu ứng dụng, font và môi trường đều hỗ trợ UTF-8.

## 3. Bật màu cho đầu ra Git

Màu giúp phân biệt trạng thái file, nhánh, dòng thêm/xóa trong diff và các phần của lịch sử. Git có cấu hình tổng quát `color.ui`:

```bash
git config --global color.ui auto
```

Các giá trị thường dùng:

| Giá trị | Hành vi |
|---|---|
| `auto` | Dùng màu khi đầu ra hướng tới terminal hỗ trợ màu; thường là lựa chọn phù hợp |
| `always` | Luôn thêm mã màu, kể cả khi đầu ra được chuyển tiếp hoặc ghi vào file |
| `never` | Tắt màu |

`auto` là lựa chọn tốt cho hầu hết môi trường tương tác. Nếu dùng `always`, mã điều khiển màu có thể xuất hiện trong file log hoặc làm công cụ tiếp theo khó phân tích đầu ra. Nếu muốn tắt màu cho một lần chạy, dùng:

```bash
git -c color.ui=never status
```

Tùy chọn `-c` chỉ áp dụng cấu hình cho lệnh đó, không ghi thay đổi vào file config.

Một số nhóm lệnh có cấu hình màu riêng:

| Cấu hình | Đầu ra được điều khiển |
|---|---|
| `color.branch` | Danh sách branch |
| `color.status` | Kết quả `git status` |
| `color.diff` | Diff |
| `color.grep` | Kết quả tìm kiếm bằng `git grep` |
| `color.interactive` | Các menu tương tác của Git |

Có thể kiểm tra các cấu hình màu hiện tại:

```bash
git config --show-origin --get-regexp '^color\.'
```

Nếu không có cấu hình riêng, Git dùng mặc định và giá trị tổng quát của `color.ui`.

## 4. Tùy chỉnh màu cho diff và status

Bạn có thể đặt màu riêng cho các thành phần của diff. Ví dụ:

```bash
git config --global color.diff.meta "bold blue"
git config --global color.diff.frag "cyan"
git config --global color.diff.old "red"
git config --global color.diff.new "green"
git config --global color.status.untracked "yellow"
```

Các thuộc tính thường dùng:

- `color.diff.meta`: dòng metadata của diff, ví dụ `diff --git`, `index`, `---`, `+++`.
- `color.diff.frag`: dòng tiêu đề hunk bắt đầu bằng `@@`.
- `color.diff.old`: dòng bị xóa.
- `color.diff.new`: dòng được thêm.
- `color.status.untracked`: file chưa được theo dõi trong status.

Git hỗ trợ các màu cơ bản như `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `black` và thuộc tính như `bold`, `dim`, `ul`, `reverse`. Có thể kết hợp nhiều thuộc tính trong một giá trị, chẳng hạn `"bold yellow"`.

Kiểm tra kết quả:

```bash
git status
git diff
git diff --cached
git log --oneline --decorate --graph -10
```

Nếu màu không xuất hiện, kiểm tra terminal có hỗ trợ ANSI không, cấu hình `color.ui` có đang là `never` không và lệnh có đang được pipe/redirect hay không. Một số terminal, pager hoặc ứng dụng trung gian có thể tắt hoặc không hiển thị mã màu.

Không nên dựa hoàn toàn vào đỏ và xanh lá để phân biệt thay đổi nếu bạn hoặc người review gặp khó khăn khi phân biệt hai màu. Có thể kết hợp màu với độ đậm, ký hiệu và nội dung dấu `+`/`-` vốn có trong diff.

## 5. Hiểu pager khi Git hiển thị nhiều dòng

Một số lệnh như `git log`, `git diff` hoặc `git show` có thể tạo ra đầu ra dài. Git thường chuyển đầu ra qua pager để bạn đọc từng màn hình thay vì đẩy toàn bộ văn bản ra terminal.

Pager mặc định thường là `less`. Một số phím hữu ích khi đang xem:

| Phím | Tác dụng |
|---|---|
| `Space` hoặc `PageDown` | Sang màn hình tiếp theo |
| `b` hoặc `PageUp` | Quay lại màn hình trước |
| `/` rồi nhập từ khóa | Tìm trong đầu ra |
| `n` | Tới kết quả tìm tiếp theo |
| `N` | Quay lại kết quả trước |
| `g` | Về đầu |
| `G` | Tới cuối |
| `q` | Thoát pager |

Nếu pager không hiển thị màu, cấu hình phổ biến với `less` là:

```bash
git config --global core.pager "less -FRX"
```

Ý nghĩa các tùy chọn:

- `-F`: thoát ngay nếu nội dung vừa trong một màn hình.
- `-R`: cho phép hiển thị các chuỗi điều khiển màu ANSI.
- `-X`: không xóa màn hình terminal khi pager thoát.

Lệnh này chỉ phù hợp khi shell tìm được chương trình `less`. Git Bash thường đi kèm các công cụ Unix; trên môi trường khác, hãy kiểm tra `less` đã cài và có trong PATH chưa. Nếu cấu hình pager làm đầu ra khó đọc, có thể bỏ cấu hình riêng để Git dùng mặc định:

```bash
git config --global --unset core.pager
```

Bạn cũng có thể bỏ qua pager cho một lệnh:

```bash
git --no-pager log --oneline -20
git --no-pager diff
```

Để xem pager đang được cấu hình từ đâu:

```bash
git config --show-origin --get core.pager
```

Nếu đầu ra được chuyển vào file hoặc pipe, hãy cân nhắc dùng `--no-pager` và điều khiển màu riêng cho phù hợp với công cụ nhận dữ liệu.

## 6. Xem và quản lý cấu hình terminal của Git

Git đọc cấu hình từ nhiều phạm vi. Những phạm vi thường gặp:

| Phạm vi | Cách đặt | Phạm vi ảnh hưởng |
|---|---|---|
| System | `git config --system` | Người dùng của máy, thường cần quyền quản trị |
| Global | `git config --global` | Tài khoản người dùng hiện tại |
| Local | `git config --local` | Repository hiện tại |
| Command | `git -c key=value ...` | Một lệnh duy nhất |

Cấu hình ở phạm vi cụ thể hơn thường ghi đè giá trị ở phạm vi rộng hơn. Ví dụ, `color.ui=false` ở local có thể tắt màu trong một repository dù global đang bật `auto`.

Xem các giá trị và nguồn cấu hình:

```bash
git config --show-origin --list
```

Tìm riêng các cài đặt liên quan đến terminal:

```bash
git config --show-origin --get-regexp '^(color\.|core\.pager|core\.quotepath)'
```

Chỉnh sửa file cấu hình global bằng:

```bash
git config --global --edit
```

Chỉnh sửa cấu hình riêng của repository hiện tại:

```bash
git config --local --edit
```

Nếu một thiết lập không có hiệu lực như mong muốn, dùng `--show-origin` để biết file nào đã cung cấp giá trị. Điều này giúp phát hiện cấu hình local đang ghi đè global hoặc một file cấu hình khác đang được đọc.

Một số lệnh xem cấu hình có thể hiển thị thông tin nhạy cảm nếu bạn lưu token hoặc thông tin xác thực sai chỗ. Trước khi chia sẻ đầu ra `git config --list`, hãy xem lại và che thông tin bí mật.

## 7. Cách đọc một thông báo lỗi Git

Thông báo lỗi Git thường có một hoặc nhiều phần:

1. **Lệnh bạn vừa chạy:** xác định chính xác thao tác nào thất bại.
2. **Đối tượng liên quan:** tên file, branch, commit, remote hoặc đường dẫn Git đang xử lý.
3. **Nguyên nhân trực tiếp:** ví dụ không tìm thấy path, không có quyền hoặc cập nhật bị từ chối.
4. **Gợi ý của Git:** một số lỗi có dòng `hint:` đề xuất cách tiếp tục.
5. **Mã thoát:** chương trình trả mã khác 0 khi lệnh thất bại; script có thể dùng mã này để quyết định bước tiếp theo.

Khi đọc lỗi, đừng chỉ nhìn dòng cuối cùng. Đọc từ dòng đầu tới cuối để tìm đối tượng được nhắc tới và xem Git có đưa ra gợi ý hay không. Sau đó kiểm tra trạng thái repository trước khi chạy lệnh sửa.

Một trình tự chẩn đoán cơ bản:

```bash
git status
git branch --show-current
git rev-parse --show-toplevel
git log --oneline --decorate -5
```

Không phải lệnh nào cũng cần chạy cả bốn. Chọn lệnh phù hợp với thông báo lỗi: lỗi đường dẫn thì kiểm tra path và thư mục hiện tại; lỗi push thì kiểm tra branch, remote và lịch sử; lỗi checkout thì kiểm tra trạng thái working tree.

## 8. Các thông báo lỗi thường gặp và cách xử lý

### `fatal: not a git repository`

Ví dụ:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Git không tìm thấy repository ở thư mục hiện tại hoặc các thư mục cha. Bạn có thể đang đứng ngoài dự án, trong một thư mục con không thuộc repository hoặc đã mở nhầm terminal.

Kiểm tra thư mục hiện tại:

```bash
pwd
git rev-parse --show-toplevel
```

Trong PowerShell, dùng `Get-Location` thay cho `pwd` nếu muốn xem đối tượng đường dẫn theo kiểu PowerShell. Chuyển tới thư mục dự án rồi chạy lại lệnh.

### `pathspec ... did not match any files`

Ví dụ:

```text
error: pathspec 'src/App.java' did not match any file(s) known to git
```

Git không tìm thấy đường dẫn hoặc tên ref phù hợp với pathspec trong ngữ cảnh lệnh. Nguyên nhân có thể là sai chính tả, sai chữ hoa/thường, đang đứng ở thư mục con khiến đường dẫn tương đối khác dự kiến, hoặc file chưa được theo dõi.

Kiểm tra:

```bash
git status --short
git ls-files -- src/App.java
```

Nếu là branch/ref, dùng `git branch --list` hoặc `git tag --list` để xác nhận tên thực tế. Đừng thêm dấu nháy hoặc sửa tên ngẫu nhiên trước khi kiểm tra đường dẫn và ngữ cảnh lệnh.

### `src refspec ... does not match any`

Ví dụ:

```text
error: src refspec main does not match any
error: failed to push some refs to 'origin'
```

Git không tìm thấy ref nguồn `main` trong repository local. Có thể branch hiện tại có tên khác, branch chưa được tạo hoặc repository chưa có commit nào.

Kiểm tra:

```bash
git branch --show-current
git branch --list
git log -1 --oneline
```

Nếu repository mới chưa có commit, hãy tạo commit đầu tiên sau khi stage nội dung cần thiết. Nếu branch có tên khác, push đúng ref nguồn và ref đích thay vì giả định tên luôn là `main`.

### `rejected ... non-fast-forward`

Ví dụ:

```text
! [rejected]        main -> main (non-fast-forward)
error: failed to push some refs
hint: Updates were rejected because the tip of your current branch is behind
```

Remote có commit mà lịch sử local chưa chứa, nên Git từ chối cập nhật có thể làm mất lịch sử remote. Fetch và xem hai phía trước:

```bash
git fetch origin
git log --oneline --left-right --graph HEAD...origin/main
```

Thay `origin/main` bằng remote-tracking branch đúng. Sau khi hiểu các commit khác nhau, tích hợp thay đổi bằng merge hoặc rebase theo quy ước nhóm, giải quyết conflict nếu có, rồi push lại. Không dùng `--force` chỉ để bỏ qua thông báo non-fast-forward.

### `Permission denied (publickey)`

Ví dụ:

```text
git@host.example: Permission denied (publickey).
fatal: Could not read from remote repository.
```

Remote đang dùng SSH nhưng máy hiện tại chưa xác thực được bằng khóa phù hợp, hoặc tài khoản không có quyền truy cập repository.

Kiểm tra URL remote:

```bash
git remote -v
```

Xác nhận bạn đang dùng đúng tài khoản, khóa SSH đã được thêm vào dịch vụ lưu trữ mã nguồn và SSH agent đang nạp khóa cần thiết. Lệnh kiểm tra kết nối SSH phụ thuộc máy chủ; ví dụ với dịch vụ dùng hostname `host.example`:

```bash
ssh -T git@host.example
```

Thay hostname bằng máy chủ thực tế. Không gửi private key hoặc nội dung bí mật của agent cho người khác.

### `detected dubious ownership`

Git có thể từ chối làm việc với repository nếu phát hiện thư mục thuộc quyền sở hữu khác với người dùng đang chạy Git. Điều này thường gặp khi repository được tạo bằng tài khoản khác, chạy trong môi trường dùng chung hoặc sau khi thay đổi quyền sở hữu.

Trước tiên, xác minh đường dẫn và chủ sở hữu repository. Chỉ khi bạn tin cậy repository đó mới thêm đúng đường dẫn vào danh sách an toàn:

```bash
git config --global --add safe.directory "/path/to/trusted/repository"
```

Thay đường dẫn bằng đường dẫn thực tế. Không thêm wildcard để tin cậy mọi repository một cách rộng rãi và không dùng cấu hình này để che giấu một vấn đề quyền sở hữu chưa được hiểu rõ.

### Cảnh báo line ending

Ví dụ:

```text
warning: LF will be replaced by CRLF the next time Git touches it
```

Đây là cảnh báo về chuyển đổi line ending, không nhất thiết là lỗi khiến lệnh thất bại. Kiểm tra thuộc tính và cấu hình:

```bash
git check-attr text eol -- path/to/file
git ls-files --eol -- path/to/file
git config --show-origin --get core.autocrlf
```

Đối chiếu kết quả với quy ước `.gitattributes` của dự án. Không thay đổi hàng loạt cấu hình line ending chỉ để loại bỏ cảnh báo nếu chưa biết ảnh hưởng tới các thành viên khác.

## 9. Phân biệt lỗi, cảnh báo và gợi ý

Không phải mọi dòng có từ `error`, `warning` hoặc `hint` đều có cùng ý nghĩa:

| Loại thông báo | Ý nghĩa thường gặp | Cách phản ứng |
|---|---|---|
| `fatal:` | Git không thể tiếp tục thao tác | Đọc nguyên nhân và kiểm tra trạng thái trước khi sửa |
| `error:` | Một bước hoặc đối tượng không hợp lệ | Kiểm tra tên file, ref, option và ngữ cảnh |
| `warning:` | Có vấn đề cần chú ý nhưng lệnh có thể vẫn hoàn thành | Xác minh ảnh hưởng, không mặc định thao tác đã thất bại |
| `hint:` | Gợi ý từ Git về nguyên nhân hoặc hướng xử lý | Đọc cùng các dòng lỗi; đánh giá xem gợi ý có phù hợp với repository không |

Mã thoát cũng hữu ích khi dùng Git trong script:

```bash
git status
echo $?
```

Trong Bash/Zsh, `$?` là mã thoát của lệnh vừa chạy; giá trị `0` thường biểu thị thành công, khác `0` biểu thị có lỗi hoặc điều kiện đặc biệt. Trong PowerShell, dùng biến tự động `$LASTEXITCODE` để đọc mã thoát của chương trình native như Git. Không dùng cùng cú pháp biến giữa các shell nếu muốn script chạy trên nhiều môi trường.

## 10. Checklist khi terminal hiển thị khó đọc hoặc Git báo lỗi

Khi đầu ra có màu không đúng, ký tự lỗi hoặc thông báo khó hiểu, hãy kiểm tra lần lượt:

1. Terminal đang dùng có hỗ trợ màu ANSI và font có đủ ký tự không?
2. Shell đang đứng ở đúng repository chưa? Dùng `git rev-parse --show-toplevel`.
3. Cấu hình màu có bị ghi đè ở local/global không? Dùng `git config --show-origin --get-regexp '^color\.'`.
4. Pager có hoạt động đúng không? Thử `git --no-pager log --oneline -10`.
5. Tên file Unicode có được hiển thị đúng không? Kiểm tra `core.quotepath` và encoding terminal.
6. Thông báo lỗi nhắc tới file, branch, commit hay remote nào? Xác minh đúng đối tượng đó.
7. Lệnh có thất bại thật hay chỉ đưa ra cảnh báo? Kiểm tra nội dung đầu ra và mã thoát.
8. Trước khi chạy lệnh sửa, đã hiểu trạng thái working tree và index chưa? Dùng `git status`.

Khi cần nhờ người khác hỗ trợ, hãy gửi lệnh đã chạy, toàn bộ thông báo lỗi liên quan và kết quả `git status`. Che token, mật khẩu, private key, URL có thông tin xác thực và dữ liệu nhạy cảm trước khi chia sẻ.

## Kết luận

Dùng terminal emulator và shell phù hợp với hệ điều hành, bảo đảm UTF-8 và hỗ trợ ANSI, bật `color.ui=auto`, rồi tùy chỉnh pager khi cần đọc đầu ra dài. Dùng `core.quotepath=false` nếu muốn tên file Unicode hiển thị trực tiếp. Khi gặp lỗi, đọc toàn bộ thông báo, xác định file/ref/remote liên quan và kiểm tra trạng thái repository trước khi hành động. Cấu hình có thể được truy vết bằng `git config --show-origin`, giúp tìm ra nguồn đang ghi đè thiết lập mong muốn.
