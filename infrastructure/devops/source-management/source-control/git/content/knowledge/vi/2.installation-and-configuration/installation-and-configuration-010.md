# Biến môi trường, đường dẫn Git và thứ tự ưu tiên cấu hình

Một máy có thể cài nhiều bản Git, mở repository từ nhiều terminal và dùng cấu hình khác nhau cho từng dự án. Khi đó, lệnh git chạy được nhưng có thể dùng nhầm executable, đọc nhầm repository hoặc lấy giá trị cấu hình không như mong đợi. Nguyên nhân thường nằm ở PATH, biến môi trường của tiến trình và thứ tự ưu tiên các file cấu hình Git.

Trong chương **Cài đặt và cấu hình** của module **SOURCE_CONTROL_GIT**, bài học này giúp bạn phân biệt ba lớp thường bị nhầm lẫn: shell tìm chương trình Git qua PATH; các biến môi trường GIT_* điều khiển hành vi của tiến trình Git; và git config cung cấp thiết lập theo từng phạm vi. Bạn sẽ biết cách kiểm tra lệnh Git thực sự đang chạy, tìm nguồn của một giá trị cấu hình, xử lý xung đột giữa các scope và thiết lập biến môi trường an toàn trên Windows, Linux hoặc macOS.

Sau bài học, bạn có thể:

- Giải thích PATH quyết định executable Git nào được shell gọi.
- Kiểm tra vị trí và phiên bản Git đang chạy.
- Phân biệt biến môi trường của hệ điều hành với thiết lập trong git config.
- Nhận diện các biến GIT_* thường ảnh hưởng đến repository, index, object database và xác thực remote.
- Giải thích thứ tự ưu tiên system, global, local, worktree và command.
- Truy tìm file cấu hình tạo ra một giá trị bằng git config --show-origin và --show-scope.
- Thiết lập, kiểm tra và gỡ biến môi trường trong PowerShell hoặc shell kiểu Unix.
- Chẩn đoán tình huống terminal, IDE và CI sử dụng cấu hình khác nhau.

## 1. Ba lớp cấu hình cần phân biệt

Khi chạy lệnh Git, nhiều lớp có thể cùng ảnh hưởng đến kết quả:

1. **Đường dẫn chương trình (PATH)**: shell tìm file thực thi git ở đâu và chọn bản nào nếu có nhiều bản.
2. **Biến môi trường**: tiến trình Git nhận các giá trị từ shell hoặc hệ điều hành. Một số biến thay đổi cách Git tìm repository, index, object database, cấu hình hoặc kết nối remote.
3. **Git config**: các file cấu hình lưu thiết lập như user.name, user.email, core.editor, pull.rebase và remote.<name>.url.

Có thể hình dung luồng thực thi:

~~~text
Terminal / IDE / CI
        |
        | PATH: chọn executable
        v
      git.exe / git
        |
        | Environment: GIT_DIR, GIT_INDEX_FILE, ...
        | Git config: system -> global -> local -> worktree -> command
        v
 Repository và thao tác Git
~~~

Ba lớp này có quan hệ với nhau nhưng không phải một bảng ưu tiên duy nhất. PATH chọn chương trình trước khi Git chạy. Biến môi trường có thể điều khiển một hành vi cụ thể. Git config có quy tắc hợp nhất giá trị theo scope. Vì vậy, khi một thiết lập có vẻ không đúng, hãy xác định đúng lớp đang gây ảnh hưởng thay vì chỉ thay đổi một file cấu hình.

## 2. PATH quyết định lệnh Git nào được chạy

PATH là danh sách thư mục mà shell tìm kiếm khi bạn nhập tên một chương trình. Nếu máy có nhiều bản Git, ví dụ Git for Windows, bản Git đi kèm một IDE hoặc một bản cài qua package manager, thứ tự thư mục trong PATH có thể quyết định bản nào được gọi.

Trên Windows, kiểm tra bằng PowerShell:

~~~powershell
Get-Command git -All
where.exe git
~~~

Get-Command hiển thị các lệnh có tên git mà PowerShell tìm thấy, bao gồm cả alias hoặc function nếu có. where.exe liệt kê các executable git được tìm thấy trên PATH. Nếu có nhiều kết quả, hãy kiểm tra thứ tự và vị trí trước khi kết luận bản nào đang được sử dụng.

Lấy đường dẫn của lệnh được PowerShell chọn:

~~~powershell
(Get-Command git).Source
git --version
~~~

Trên Linux hoặc macOS:

~~~bash
type -a git
command -v git
git --version
~~~

type -a có thể liệt kê các định nghĩa và vị trí lệnh trùng tên; command -v cho biết lệnh được shell phân giải. Nếu shell có cache đường dẫn chương trình, mở terminal mới hoặc làm mới cache theo shell khi vừa thay đổi PATH.

Một số bản Git có thể báo khác nhau về phiên bản, tính năng hoặc helper đi kèm. Nếu IDE và terminal cho kết quả khác, hãy kiểm tra executable path của cả hai môi trường.

### git --exec-path không phải đường dẫn git.exe

Lệnh:

~~~bash
git --exec-path
~~~

trả về thư mục chứa các chương trình hỗ trợ nội bộ mà Git gọi trong quá trình thực thi, chẳng hạn một số helper. Nó không nhất thiết là vị trí của executable git được shell chạy. Để tìm executable, dùng Get-Command/where.exe trên Windows hoặc type/command trên Unix-like.

## 3. Kiểm tra và chỉnh PATH trên Windows

Git for Windows thường cung cấp git.exe trong một thư mục như:

- C:\Program Files\Git\cmd
- C:\Program Files\Git\bin

Đường dẫn thực tế phụ thuộc vị trí cài đặt. Một số công cụ có thể đặt Git ở thư mục riêng hoặc cung cấp Git tích hợp.

Để kiểm tra PATH hiện tại trong PowerShell:

~~~powershell
$env:Path -split ';'
~~~

Nếu muốn thử một thư mục Git trong phiên PowerShell hiện tại, có thể thêm nó vào đầu PATH của tiến trình:

~~~powershell
$gitBin = 'C:\Program Files\Git\cmd'
$env:Path = "$gitBin;$env:Path"
Get-Command git
git --version
~~~

Thay đường dẫn ví dụ bằng thư mục thực tế có git.exe. Thay đổi này chỉ có hiệu lực trong tiến trình PowerShell hiện tại và các tiến trình con được mở từ nó; mở terminal mới sẽ không tự kế thừa thay đổi đó.

Để thay đổi lâu dài, dùng giao diện Environment Variables của Windows:

1. Mở phần chỉnh sửa biến môi trường của tài khoản hoặc hệ thống.
2. Chọn biến Path ở đúng phạm vi.
3. Thêm thư mục chứa executable Git vào danh sách.
4. Đặt thứ tự phù hợp nếu có nhiều bản Git.
5. Mở terminal mới và xác minh bằng Get-Command git -All, where.exe git và git --version.

Biến User Path chỉ ảnh hưởng người dùng hiện tại; System Path ảnh hưởng rộng hơn và thường cần quyền quản trị. Chỉ thêm thư mục tin cậy do bộ cài Git cung cấp. Tránh thay thế toàn bộ PATH bằng một chuỗi ngắn vì có thể làm các chương trình khác không còn được tìm thấy.

Không nên dùng setx PATH với giá trị được ghép tùy tiện. Trên một số môi trường, cách này có thể làm mất mục PATH hiện có hoặc gặp giới hạn độ dài. Giao diện Environment Variables giúp xem và chỉnh từng mục rõ ràng hơn.

## 4. PATH trên Linux và macOS

Trong shell kiểu Unix, PATH thường là danh sách thư mục phân cách bằng dấu hai chấm. Kiểm tra:

~~~bash
printf '%s\n' "$PATH"
type -a git
command -v git
~~~

Để thêm một thư mục vào đầu PATH trong phiên hiện tại:

~~~bash
export PATH="/opt/git/bin:$PATH"
~~~

Để thiết lập lâu dài, đặt lệnh export trong file khởi tạo phù hợp với shell và loại phiên đăng nhập, ví dụ ~/.bashrc, ~/.bash_profile hoặc ~/.zshrc. Không phải mọi terminal đều đọc cùng một file; hãy xác định shell bằng:

~~~bash
echo "$SHELL"
ps -p $$ -o comm=
~~~

Sau khi sửa file cấu hình shell, nạp lại file tương ứng hoặc mở terminal mới rồi xác minh lại vị trí Git. Trên macOS, PATH còn có thể được thiết lập bởi shell startup files, package manager hoặc môi trường IDE.

## 5. Biến môi trường được truyền cho tiến trình như thế nào?

Biến môi trường là các cặp tên và giá trị mà một tiến trình nhận từ môi trường đã khởi chạy nó. Khi một terminal mở chương trình Git, Git nhận các biến môi trường được terminal cung cấp. Tiến trình con thường kế thừa môi trường của tiến trình cha.

Điều này giải thích vì sao:

- Git chạy trong terminal có thể hoạt động khác Git chạy trong IDE.
- Một terminal mới có thể không nhận biến vừa đặt trong terminal cũ.
- CI runner có thể có HOME, PATH hoặc GIT_* khác máy lập trình viên.
- Script chạy qua một shell khác có thể không đọc cùng file khởi tạo.

### PowerShell: đặt biến trong phiên hiện tại

~~~powershell
$env:GIT_TERMINAL_PROMPT = '0'
git fetch
~~~

Xem giá trị:

~~~powershell
$env:GIT_TERMINAL_PROMPT
~~~

Gỡ biến khỏi phiên hiện tại:

~~~powershell
Remove-Item Env:GIT_TERMINAL_PROMPT
~~~

### PowerShell: lưu biến ở phạm vi người dùng

~~~powershell
[Environment]::SetEnvironmentVariable('MY_TOOL_MODE', 'review', 'User')
~~~

Giá trị được lưu cho các tiến trình đăng nhập sau của người dùng. Terminal hoặc IDE đang mở thường không tự nhận giá trị mới; hãy mở tiến trình mới để kiểm tra. Có thể xóa biến đã lưu:

~~~powershell
[Environment]::SetEnvironmentVariable('MY_TOOL_MODE', $null, 'User')
~~~

### Bash hoặc Zsh: đặt và gỡ biến

~~~bash
export GIT_TERMINAL_PROMPT=0
printf '%s\n' "$GIT_TERMINAL_PROMPT"
unset GIT_TERMINAL_PROMPT
~~~

export đặt biến cho shell và các tiến trình con. unset gỡ biến khỏi môi trường shell hiện tại. Muốn lưu lâu dài, đặt export trong file khởi tạo shell thích hợp.

Không đặt biến nhạy cảm trong file được commit vào repository. Với token hoặc thông tin xác thực, dùng credential manager, secret store của CI hoặc cơ chế bảo mật phù hợp.

## 6. Các biến GIT_* thường gặp

Git có nhiều biến môi trường. Không cần ghi nhớ tất cả; quan trọng là nhận diện những biến có thể làm Git thao tác trên repository hoặc dữ liệu khác với dự kiến.

| Biến | Tác dụng khái quát | Khi nào cần chú ý |
| --- | --- | --- |
| GIT_DIR | Chỉ định đường dẫn Git directory thay cho cơ chế tìm repository thông thường | Lệnh bất ngờ chạy trên metadata của repository khác |
| GIT_WORK_TREE | Chỉ định working tree tương ứng với Git directory | Git dùng nhầm thư mục source |
| GIT_COMMON_DIR | Chỉ định common Git directory trong một số cấu trúc repository/worktree | Điều tra linked worktree hoặc metadata chung |
| GIT_INDEX_FILE | Chọn file index thay cho index mặc định | Status hoặc commit không phản ánh staging area bạn đang nhìn |
| GIT_OBJECT_DIRECTORY | Chỉ định thư mục object database chính | Git không tìm thấy object ở nơi mong đợi |
| GIT_ALTERNATE_OBJECT_DIRECTORIES | Bổ sung các object directory để tìm object | Repository dùng object store chia sẻ |
| GIT_CEILING_DIRECTORIES | Giới hạn nơi Git dừng tìm repository cha | Lệnh trong thư mục lồng nhau không tìm repository như dự kiến |
| HOME | Ảnh hưởng thư mục home mà Git và công cụ liên quan sử dụng | Global config hoặc SSH key được tìm ở vị trí khác dự kiến |
| XDG_CONFIG_HOME | Có thể thay đổi vị trí file cấu hình theo chuẩn XDG | Global config nằm trong thư mục cấu hình XDG |
| GIT_CONFIG_GLOBAL | Chọn file cấu hình global thay thế | Giá trị --global không nằm trong file quen thuộc |
| GIT_CONFIG_SYSTEM | Chọn file cấu hình system thay thế | Cấu hình system khác môi trường chuẩn |
| GIT_CONFIG_NOSYSTEM | Bỏ qua file cấu hình system khi được bật | Kết quả khác do system config |
| GIT_EXEC_PATH | Chỉ định thư mục chứa helper nội bộ của Git | Git không tìm thấy hoặc dùng nhầm helper |
| GIT_SSH hoặc GIT_SSH_COMMAND | Chọn chương trình/lệnh SSH để kết nối remote | Lỗi xác thực hoặc dùng nhầm khóa SSH |
| GIT_TERMINAL_PROMPT | Điều khiển việc Git có hỏi thông tin trong terminal hay không | CI không tương tác bị treo hoặc không thể hỏi mật khẩu |
| GIT_TRACE | Bật trace để chẩn đoán hoạt động Git | Điều tra lệnh gọi helper hoặc tiến trình con |

Một số biến nâng cao chỉ nên đặt khi có mục đích cụ thể. Ví dụ, GIT_DIR và GIT_WORK_TREE có thể khiến lệnh git chạy trong thư mục hiện tại nhưng thao tác lên repository ở nơi khác. GIT_INDEX_FILE có thể làm git status và git commit sử dụng một staging area khác. Nếu thấy hành vi bất thường, hãy kiểm tra các biến này trước khi sửa repository.

Xem các biến môi trường liên quan trong PowerShell:

~~~powershell
Get-ChildItem Env:GIT*
~~~

Trong Bash/Zsh:

~~~bash
env | grep '^GIT_'
~~~

Khi chia sẻ output để chẩn đoán, hãy loại bỏ token, đường dẫn riêng tư hoặc thông tin xác thực trước khi gửi.

## 7. Phân biệt biến môi trường với git config

Không phải mọi thiết lập Git đều là biến môi trường. Ví dụ:

| Mục tiêu | Cơ chế thường dùng |
| --- | --- |
| Chọn executable Git | PATH của shell/hệ điều hành |
| Đặt tên và email mặc định cho commit | git config user.name và user.email |
| Chọn editor mặc định | git config core.editor hoặc biến editor tương ứng của môi trường |
| Chỉ định Git directory | GIT_DIR hoặc tùy chọn -C để chọn thư mục làm việc |
| Chọn index khác | GIT_INDEX_FILE |
| Chọn SSH command | GIT_SSH_COMMAND hoặc cấu hình SSH |
| Chọn cách pull tích hợp | git config pull.rebase hoặc pull.ff |
| Chọn file cấu hình global | GIT_CONFIG_GLOBAL |

Ví dụ, đặt danh tính commit mặc định:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

Đây là thiết lập trong Git config. Git cũng có các biến như GIT_AUTHOR_NAME, GIT_AUTHOR_EMAIL, GIT_COMMITTER_NAME và GIT_COMMITTER_EMAIL để ghi đè thông tin tác giả hoặc người tạo commit trong một tiến trình cụ thể. Chúng không phải là cách tốt để thay thế cấu hình danh tính thường ngày.

Kiểm tra danh tính cấu hình:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Nếu commit có author hoặc committer khác với giá trị bạn thấy trong config, hãy kiểm tra các biến GIT_AUTHOR_* và GIT_COMMITTER_* trong môi trường đang chạy lệnh.

## 8. Thứ tự ưu tiên Git config

Git đọc cấu hình từ nhiều scope. Khi cùng một key có nhiều giá trị, giá trị ở scope ưu tiên cao hơn thường được dùng cho các thao tác đọc một giá trị đơn.

Thứ tự ưu tiên từ thấp đến cao:

~~~text
System
   |
   v
Global
   |
   v
Local (repository)
   |
   v
Worktree
   |
   v
Command
~~~

| Scope | Phạm vi | Cách đặt thường dùng |
| --- | --- | --- |
| system | Toàn máy hoặc bản cài Git | git config --system |
| global | Người dùng hiện tại | git config --global |
| local | Repository hiện tại | git config --local |
| worktree | Worktree cụ thể khi bật worktree config | git config --worktree |
| command | Một lần gọi Git | git -c key=value ... |

Ví dụ cùng một key pull.rebase có thể được đặt:

~~~bash
git config --global pull.rebase false
git config --local pull.rebase true
git -c pull.rebase false pull
~~~

Trong repository đó, giá trị local ghi đè global. Riêng lần gọi git -c, giá trị command được ưu tiên cao hơn cấu hình đã lưu và chỉ ảnh hưởng lệnh đó.

Thứ tự trên áp dụng cho các giá trị cấu hình cùng key có thể hợp nhất theo scope. Một số key là multi-valued hoặc có quy tắc riêng; đừng giả định mọi key đều chỉ có một giá trị. Khi cần biết chính xác, xem tất cả nguồn và đọc tài liệu của key cụ thể.

## 9. Các file cấu hình nằm ở đâu?

Các vị trí thường gặp:

| Scope | Vị trí phổ biến | Ghi chú |
| --- | --- | --- |
| system | /etc/gitconfig trên Unix-like; file system config trong thư mục cài Git trên Windows | Có thể bị quản trị máy quản lý |
| global | ~/.gitconfig hoặc $XDG_CONFIG_HOME/git/config | Gắn với tài khoản người dùng |
| local | .git/config hoặc common Git directory tương ứng | Chỉ áp dụng repository |
| worktree | config.worktree trong Git directory của worktree | Chỉ dùng khi bật extensions.worktreeConfig |

Đường dẫn thực tế phụ thuộc hệ điều hành, HOME, XDG_CONFIG_HOME, vị trí cài Git và cấu trúc repository. Với linked worktree, local config thường dùng chung theo repository; worktree config cho phép một số thiết lập khác nhau giữa các worktree.

Kiểm tra file cấu hình và scope đang cung cấp giá trị:

~~~bash
git config --list --show-origin --show-scope
~~~

Nếu phiên bản Git chưa hỗ trợ --show-scope, dùng:

~~~bash
git config --list --show-origin
~~~

Các tham số này cho biết mỗi giá trị đến từ file nào và, trên phiên bản hỗ trợ, scope tương ứng. Đây là cách nhanh để tìm lý do vì sao một thiết lập global bị ghi đè bởi repository local hoặc worktree.

### Cấu hình worktree

Trong repository dùng linked worktree, có thể bật cấu hình riêng cho từng worktree:

~~~bash
git config extensions.worktreeConfig true
~~~

Sau khi bật extension, Git có thể lưu một số cấu hình riêng trong config.worktree. Ví dụ, đặt editor riêng cho worktree hiện tại:

~~~bash
git config --worktree core.editor "code --wait"
git config --worktree --get core.editor
~~~

Lệnh chỉ ảnh hưởng worktree hiện tại. Hãy hiểu cấu trúc repository trước khi bật extension trên repository đang được dùng bởi nhiều công cụ hoặc phiên bản Git khác nhau; một số thiết lập vốn thuộc riêng từng worktree cần được rà soát khi chuyển đổi cấu hình. Worktree config là cơ chế cấu hình Git, không phải biến môi trường.

## 10. Kiểm tra một giá trị và nguồn cấu hình

Để xem một key cụ thể cùng nguồn:

~~~bash
git config --show-origin --get core.editor
git config --show-origin --get pull.rebase
git config --show-origin --get user.email
~~~

Nếu key có nhiều giá trị, dùng:

~~~bash
git config --show-origin --get-all remote.origin.fetch
~~~

Để tìm tất cả key liên quan:

~~~bash
git config --show-origin --show-scope --get-regexp '^(core|pull|user)\.'
~~~

Khi nghi ngờ biến môi trường làm thay đổi hành vi, kiểm tra đồng thời:

~~~powershell
Get-ChildItem Env:GIT*
git config --list --show-origin --show-scope
git status -sb
git rev-parse --show-toplevel
~~~

Các lệnh này trả lời bốn câu hỏi khác nhau:

- Có biến GIT_* nào đang được truyền vào tiến trình?
- Git đang đọc những cấu hình nào và từ scope nào?
- Working tree và branch hiện tại đang ở trạng thái nào?
- Git đang nhận diện thư mục gốc repository nào?

Trên Bash/Zsh, thay lệnh đầu bằng env | grep '^GIT_'.

## 11. Dùng git -c cho một lần chạy

Khi cần thử một thiết lập mà không muốn sửa file config, dùng tùy chọn -c:

~~~bash
git -c core.pager=cat log --oneline -10
git -c pull.rebase=true pull
git -c advice.detachedHead=false switch --detach <commit>
~~~

Thiết lập sau -c chỉ có hiệu lực trong lần gọi Git đó. Nó hữu ích để kiểm tra một giả thuyết hoặc chạy một thao tác đặc biệt trong CI.

Nếu cần cung cấp giá trị cấu hình qua biến môi trường mà không ghi trực tiếp giá trị nhạy cảm vào command line, Git hỗ trợ tùy chọn --config-env ở các phiên bản có tính năng này. Hãy kiểm tra git --version và tài liệu phiên bản đang dùng trước khi đưa vào script.

Không nên đặt global config chỉ để thử một lần. Thay đổi global có thể ảnh hưởng tất cả repository của người dùng và khiến lỗi khó tái hiện ở môi trường khác.

## 12. Các tình huống chẩn đoán thường gặp

### Terminal và IDE chạy hai bản Git khác nhau

Triệu chứng: lệnh git --version trong terminal khác phiên bản mà IDE báo, hoặc một bên có helper còn bên kia không.

Kiểm tra:

~~~powershell
Get-Command git -All
where.exe git
git --version
~~~

Sau đó kiểm tra đường dẫn Git trong phần cài đặt của IDE. Chọn một bản Git phù hợp và thống nhất cho terminal, IDE, script và CI nếu dự án yêu cầu cùng hành vi.

### Một repository có user.email khác repository khác

Triệu chứng: commit trong dự án A dùng email công ty, dự án B dùng email cá nhân.

Kiểm tra:

~~~bash
git config --show-origin --get user.email
git config --show-origin --get user.name
~~~

Có thể global config cung cấp danh tính mặc định còn local config ghi đè riêng cho một repository. Đây là hành vi hợp lệ nếu được chủ động cấu hình.

### Git thao tác trên repository khác

Triệu chứng: chạy git status trong thư mục tưởng là dự án A nhưng Git hiển thị branch của dự án B.

Kiểm tra:

~~~powershell
Get-ChildItem Env:GIT_DIR,Env:GIT_WORK_TREE
git rev-parse --show-toplevel
git rev-parse --git-dir
~~~

Nếu GIT_DIR hoặc GIT_WORK_TREE được đặt từ terminal, script hoặc IDE, chúng có thể thay đổi repository Git sử dụng. Xóa biến không mong muốn khỏi tiến trình rồi kiểm tra lại.

### Staging area dường như không khớp

Triệu chứng: git status hoặc git commit không phản ánh những gì bạn nghĩ đã stage.

Kiểm tra:

~~~powershell
$env:GIT_INDEX_FILE
git rev-parse --git-path index
git status
~~~

GIT_INDEX_FILE có thể chỉ đến một index thay thế. Nếu biến được đặt ngoài ý muốn, gỡ nó rồi chạy lại status. Không xóa file index thay thế trước khi xác định nó có chứa thay đổi cần giữ hay không.

### CI không thể hỏi thông tin xác thực

Triệu chứng: lệnh fetch/push chạy trong CI thất bại vì không thể mở prompt.

GIT_TERMINAL_PROMPT=0 yêu cầu Git không hỏi thông tin trong terminal. Đây có thể là thiết lập có chủ ý của CI để thất bại nhanh khi thiếu credential. Cách xử lý đúng là cấu hình credential/SSH token trong secret store và cung cấp cho job theo cơ chế bảo mật, không bật prompt tương tác trong một runner không có người dùng.

## 13. Quy trình thiết lập nhất quán cho một máy phát triển

Có thể kiểm tra và thiết lập theo thứ tự sau:

### Bước 1: xác nhận executable

~~~powershell
Get-Command git -All
where.exe git
git --version
~~~

Chọn bản Git phù hợp và đảm bảo terminal mới gọi đúng executable.

### Bước 2: kiểm tra biến môi trường

~~~powershell
Get-ChildItem Env:GIT*
~~~

Gỡ các biến GIT_DIR, GIT_WORK_TREE hoặc GIT_INDEX_FILE nếu chúng còn sót từ script cũ và không còn chủ đích sử dụng.

### Bước 3: kiểm tra cấu hình hiện tại

~~~bash
git config --list --show-origin --show-scope
~~~

Đọc nguồn của user.name, user.email, core.editor, core.autocrlf, pull.rebase và các thiết lập quan trọng khác.

### Bước 4: đặt danh tính ở đúng phạm vi

Nếu một danh tính dùng cho mọi repository:

~~~bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
~~~

Nếu dự án cần danh tính khác, đặt local trong repository đó:

~~~bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@company.example"
~~~

### Bước 5: xác minh lại

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
git status -sb
~~~

Xác nhận giá trị hiệu lực và nguồn cung cấp. Nếu IDE hoặc CI có môi trường riêng, lặp lại kiểm tra trong chính môi trường đó.

## 14. Nguyên tắc an toàn khi dùng biến môi trường và config

- Không thêm thư mục không tin cậy vào đầu PATH. Một executable giả mạo có thể được gọi trước Git thật.
- Không đặt token, mật khẩu hoặc private key trong repository hoặc file cấu hình được commit.
- Không đặt GIT_DIR, GIT_WORK_TREE hoặc GIT_INDEX_FILE ở cấp người dùng nếu không có nhu cầu rõ ràng; chúng có thể làm lệnh Git chạy trên sai dữ liệu.
- Dùng --global cho mặc định cá nhân và --local cho quy tắc riêng của dự án.
- Dùng -c khi chỉ cần thay đổi cho một lệnh.
- Dùng --show-origin và --show-scope để xác định nguồn trước khi ghi đè một giá trị.
- Khi thay PATH hoặc biến môi trường lâu dài, mở tiến trình mới để xác minh.
- Trong CI, khai báo biến trong phạm vi job và dùng secret store cho thông tin nhạy cảm.

## 15. Những nhầm lẫn thường gặp

### PATH có phải là một thiết lập trong git config?

Không. PATH thuộc môi trường shell/hệ điều hành và quyết định executable nào được chạy. Git config chỉ được đọc sau khi một chương trình Git đã được khởi chạy.

### git --exec-path cho biết git.exe nằm ở đâu?

Không. Nó cho biết thư mục helper nội bộ của Git. Dùng Get-Command, where.exe hoặc type -a để tìm executable.

### GIT_DIR có giống git config core.worktree không?

Không. GIT_DIR là biến môi trường có thể ghi đè cách Git xác định Git directory cho tiến trình. core.worktree là một key cấu hình có mục đích liên quan đến working tree. Không dùng thay thế lẫn nhau nếu chưa hiểu repository layout.

### Global luôn thắng local vì áp dụng cho mọi repository?

Không. Local có ưu tiên cao hơn global trong cùng key thông thường. Một cấu hình local có thể ghi đè giá trị global chỉ trong repository đó.

### Đặt biến môi trường trong PowerShell có lưu sau khi đóng terminal?

Không nếu chỉ dùng $env:NAME = value. Cách đó chỉ đặt trong tiến trình hiện tại và các tiến trình con. Muốn lưu cho phiên đăng nhập sau, dùng Environment Variables hoặc SetEnvironmentVariable ở phạm vi User/System.

### Mọi biến GIT_* đều là một phần của Git config?

Không. Chúng là biến môi trường có tác dụng riêng. Một số biến điều khiển vị trí repository, index, object store hoặc helper; một số biến có thể cung cấp giá trị cấu hình. Hãy tra cứu đúng biến thay vì áp dụng thứ tự scope của git config cho tất cả.

## 16. Tự kiểm tra

Một máy Windows có hai bản Git. Trong PowerShell, git --version báo 2.x; IDE lại báo 1.x. Trong repository hiện tại, user.email không giống giá trị global. Một script CI chạy fetch nhưng không thể mở prompt.

Hãy trả lời:

1. Lệnh nào cho biết tất cả vị trí Git mà PowerShell có thể tìm thấy?
2. Vì sao IDE có thể chạy bản Git khác terminal?
3. Lệnh nào xác định file cấu hình cung cấp user.email?
4. Nếu local config ghi đè global, scope nào có ưu tiên cao hơn?
5. Biến nào có thể khiến Git dùng một index khác?
6. Biến nào có thể tắt prompt tương tác trong CI?
7. Vì sao không nên lưu token trong PATH hoặc file config được commit?

**Gợi ý:** Dùng Get-Command git -All và where.exe git để tìm các executable; IDE có thể được cấu hình đường dẫn riêng. Dùng git config --show-origin --get user.email để tìm nguồn. Local ưu tiên cao hơn global. GIT_INDEX_FILE chọn index thay thế; GIT_TERMINAL_PROMPT=0 tắt prompt terminal. Token cần được lưu trong secret store hoặc credential manager, không đặt trong nội dung có thể chia sẻ.

## Kết luận

Khi Git có hành vi khác nhau giữa terminal, IDE và CI, hãy kiểm tra theo thứ tự: executable được chọn qua PATH, biến môi trường mà tiến trình nhận, rồi các giá trị git config cùng scope và nguồn. PATH quyết định chương trình nào chạy; GIT_* có thể thay đổi repository, index, object store hoặc helper; còn Git config hợp nhất thiết lập theo system, global, local, worktree và command. Dùng Get-Command/where.exe, env, git config --show-origin và --show-scope để tìm nguyên nhân trước khi chỉnh. Thiết lập đúng phạm vi giúp môi trường phát triển nhất quán và tránh thay đổi ngoài ý muốn ở repository khác.
