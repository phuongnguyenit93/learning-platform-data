# Các cấp cấu hình: system, global, local, worktree và tham số -c

## Vì sao Git có nhiều cấp cấu hình?

Git có nhiều thiết lập ảnh hưởng đến cách làm việc: tên và email ghi vào commit, trình soạn thảo, cách hiển thị màu, quy tắc pull, line ending, credential helper, hook và nhiều tùy chọn khác. Nếu mọi thiết lập chỉ nằm trong một file, sẽ khó dùng chung một số quy tắc cho mọi repository nhưng vẫn tùy chỉnh riêng cho từng dự án hoặc từng working tree.

Git giải quyết vấn đề này bằng nhiều **cấp cấu hình** (configuration scopes). Mỗi cấp có phạm vi áp dụng khác nhau:

- **system:** áp dụng cho mọi người dùng trên máy.
- **global:** áp dụng cho người dùng hiện tại, thường dùng chung giữa các repository của người đó.
- **local:** áp dụng cho một repository.
- **worktree:** áp dụng riêng cho một working tree khi repository bật cơ chế worktree config.
- **command:** áp dụng cho một lần gọi Git thông qua tùy chọn -c hoặc cơ chế cấu hình command tương ứng.

Thứ tự ưu tiên thông thường từ thấp tới cao:

~~~text
system
   ↓
global
   ↓
local
   ↓
worktree
   ↓
command (-c)
~~~

Khi cùng một khóa cấu hình đơn trị được đặt ở nhiều cấp, giá trị ở cấp ưu tiên cao hơn thường được dùng. Ví dụ, user.email trong local có thể ghi đè giá trị global khi commit trong repository đó. Tham số -c có ưu tiên cao hơn các file cấu hình và chỉ ảnh hưởng tới lệnh được gọi.

Không phải mọi khóa đều là đơn trị. Một số khóa cho phép nhiều giá trị, chẳng hạn nhiều remote.*.fetch hoặc credential.helper. Với những khóa này, các giá trị có thể được cộng dồn hoặc được chương trình gọi Git xử lý theo quy tắc riêng. Vì vậy, không nên mặc định rằng giá trị ở cấp cao hơn luôn xóa hết các giá trị cấp thấp hơn.

## Xem Git đang đọc cấu hình từ đâu

Trước khi sửa cấu hình, hãy xem các giá trị hiện tại và nguồn của chúng:

~~~bash
git config --list --show-origin --show-scope
~~~

Kết quả có thể có dạng:

~~~text
system  file:C:/Program Files/Git/etc/gitconfig  core.autocrlf=false
global  file:C:/Users/dev/.gitconfig             user.name=Developer
global  file:C:/Users/dev/.gitconfig             init.defaultbranch=main
local   file:.git/config                         user.email=work@example.invalid
command command line:                            color.ui=always
~~~

Đây là ví dụ minh họa; đường dẫn, tên khóa và giá trị thực tế phụ thuộc máy và repository.

- --show-origin cho biết file hoặc nguồn cung cấp giá trị.
- --show-scope cho biết cấp cấu hình.
- --list liệt kê các giá trị Git đang đọc.

Nếu phiên bản Git chưa hỗ trợ một tùy chọn, có thể dùng riêng --show-origin hoặc --list để kiểm tra. Nên chạy lệnh từ bên trong repository khi muốn xem cả cấu hình local và worktree.

### Xem một khóa cụ thể

Để xem giá trị hiệu lực của một khóa:

~~~bash
git config --get user.name
git config --get user.email
git config --get core.autocrlf
~~~

Nếu khóa chưa được thiết lập, lệnh --get có thể không in kết quả và trả mã thoát khác 0. Điều đó không nhất thiết là repository bị lỗi.

Với khóa có nhiều giá trị, dùng --get-all:

~~~bash
git config --get-all credential.helper
git config --get-all remote.origin.fetch
~~~

Để lọc các khóa theo biểu thức:

~~~bash
git config --get-regexp '^user\.'
~~~

Lệnh này hữu ích khi kiểm tra nhóm thiết lập liên quan tới danh tính commit.

### Xem riêng từng cấp

Có thể liệt kê từng cấp bằng các tùy chọn tương ứng:

~~~bash
git config --system --list
git config --global --list
git config --local --list
~~~

Trong repository đã bật worktree config:

~~~bash
git config --worktree --list
~~~

Lệnh --system có thể cần quyền đọc phù hợp tùy cách cài Git. Không cần chạy tất cả các cấp mỗi lần; hãy chọn phạm vi cần điều tra.

## Cấp system: cấu hình dùng chung trên máy

Cấu hình system áp dụng cho tất cả người dùng sử dụng bản cài Git trên máy. Vị trí file tùy nền tảng và cách cài đặt; trên Windows thường nằm trong thư mục cấu hình của bản cài Git, còn trên Unix-like thường nằm ở vị trí cấu hình system của Git.

Cấp này phù hợp với các quy tắc do quản trị viên máy hoặc môi trường phát triển quản lý, ví dụ:

- Cấu hình proxy chung.
- Một số thiết lập bảo mật hoặc hành vi mặc định.
- Credential helper được tổ chức cài đặt và quản lý ở cấp máy.
- Các quy tắc chung cho máy build hoặc máy phát triển dùng chung.

Đọc cấu hình system:

~~~bash
git config --system --list --show-origin
~~~

Đặt một giá trị system cần quyền ghi vào file cấu hình của bản cài Git:

~~~bash
git config --system core.autocrlf false
~~~

Ví dụ này chỉ minh họa cú pháp. Không thay đổi thiết lập system trên máy công ty hoặc máy dùng chung nếu không có quyền và chưa hiểu ảnh hưởng tới những người dùng khác.

Xóa một khóa system:

~~~bash
git config --system --unset core.autocrlf
~~~

Nếu khóa có nhiều giá trị, kiểm tra bằng --get-all và chỉ dùng --unset-all khi thật sự muốn xóa toàn bộ giá trị của khóa đó.

## Cấp global: cấu hình cho người dùng hiện tại

Cấu hình global thường được dùng để thiết lập danh tính commit và thói quen cá nhân trên nhiều repository.

Một số thiết lập phổ biến:

~~~bash
# Danh tính ghi vào commit
git config --global user.name "Developer Name"
git config --global user.email "dev@example.invalid"

# Nhánh mặc định khi khởi tạo repository mới
git config --global init.defaultBranch main

# Trình soạn thảo mặc định
git config --global core.editor "code --wait"
~~~

Địa chỉ example.invalid chỉ là địa chỉ mẫu, không dùng làm email thật. Hãy thay bằng tên và email được tổ chức hoặc nền tảng Git yêu cầu.

Kiểm tra giá trị global:

~~~bash
git config --global --get user.name
git config --global --get user.email
git config --global --list --show-origin
~~~

Cấu hình global phù hợp khi bạn muốn cùng một danh tính hoặc thiết lập trên hầu hết repository của mình. Nếu dùng nhiều danh tính, chẳng hạn repository cá nhân và repository công ty, có thể đặt giá trị riêng ở local hoặc worktree để ghi đè global.

### Danh tính commit không phải thông tin đăng nhập

user.name và user.email xác định thông tin tác giả/committer được ghi vào metadata của commit. Chúng không cấp quyền push, không xác thực tài khoản GitHub/GitLab và không thay thế SSH key hoặc credential manager.

Nếu commit hiển thị sai tên hoặc email, hãy kiểm tra cấu hình hiệu lực trước khi tạo commit tiếp theo. Thay đổi cấu hình không tự sửa metadata của những commit đã tạo.

Có thể yêu cầu Git không tự suy đoán danh tính khi chưa cấu hình:

~~~bash
git config --global user.useConfigOnly true
~~~

Thiết lập này khiến Git yêu cầu user.name và user.email được cấu hình rõ ràng thay vì dựa vào giá trị tự suy ra trong một số trường hợp. Chỉ bật nếu bạn đã thiết lập danh tính phù hợp cho các repository sẽ sử dụng.

### Xóa hoặc thay đổi cấu hình global

Thay giá trị:

~~~bash
git config --global user.email "new-address@example.invalid"
~~~

Xóa khóa đơn trị:

~~~bash
git config --global --unset user.email
~~~

Mở file global bằng trình soạn thảo:

~~~bash
git config --global --edit
~~~

Sau khi sửa, kiểm tra lại:

~~~bash
git config --global --get user.email
git config --show-origin --get user.email
~~~

Lệnh --unset phù hợp với khóa đơn trị. Với khóa nhiều giá trị, hãy kiểm tra toàn bộ trước khi xóa; --unset-all sẽ loại bỏ mọi giá trị khớp của khóa đó.

## Cấp local: cấu hình riêng cho repository

Cấu hình local được lưu trong cấu hình của repository, thường là file .git/config. Nó áp dụng cho repository đó và có thể ghi đè thiết lập global.

Local phù hợp khi một dự án có yêu cầu riêng, ví dụ:

- Email công việc khác email cá nhân.
- Quy tắc pull hoặc merge của nhóm.
- Remote và URL riêng của repository.
- Thiết lập diff, merge tool hoặc hook path của dự án.

Ví dụ đặt danh tính riêng cho repository hiện tại:

~~~bash
git config --local user.name "Work Developer"
git config --local user.email "work@example.invalid"
~~~

Đặt quy tắc pull riêng cho dự án:

~~~bash
git config --local pull.rebase true
~~~

Ví dụ trên yêu cầu git pull ưu tiên rebase theo cấu hình; chỉ đặt khi phù hợp với quy ước cộng tác của nhóm.

Kiểm tra:

~~~bash
git config --local --list --show-origin
git config --get user.name
git config --show-origin --get user.email
~~~

Lệnh git config --get cuối cùng đọc giá trị hiệu lực theo các cấp, trong khi --local --list chỉ liệt kê cấu hình local.

### Thiết lập local có ảnh hưởng tới các thành viên khác không?

File .git/config không được commit như một tệp thông thường trong repository. Vì vậy, thiết lập local thường chỉ áp dụng trên bản clone của bạn. Thành viên khác không tự nhận được giá trị đó khi pull hoặc clone.

Nếu muốn chia sẻ quy tắc dự án, cân nhắc tài liệu hướng dẫn, .gitattributes, cấu hình build hoặc cơ chế được repository hỗ trợ. Không đưa thông tin xác thực cá nhân vào cấu hình được chia sẻ.

Mở file local:

~~~bash
git config --local --edit
~~~

Xóa một giá trị local:

~~~bash
git config --local --unset pull.rebase
~~~

Sau khi xóa local, giá trị global hoặc system có thể trở thành giá trị hiệu lực. Do đó, hãy kiểm tra lại bằng git config --show-origin --get <key> thay vì cho rằng khóa đã hoàn toàn không còn giá trị.

## Cấp worktree: cấu hình riêng cho từng working tree

Một repository có thể có nhiều working tree được quản lý bằng git worktree. Các working tree dùng chung lịch sử và object database, nhưng có thể cần một số thiết lập riêng cho từng thư mục làm việc.

Mặc định, cấu hình local trong .git/config được chia sẻ giữa các worktree của cùng repository. Để lưu cấu hình riêng cho từng worktree, Git hỗ trợ worktree config thông qua extension extensions.worktreeConfig.

Kiểm tra extension:

~~~bash
git config --local --get extensions.worktreeConfig
~~~

Khi extension đã được bật, Git có thể đọc và ghi cấu hình worktree bằng tùy chọn --worktree. Ví dụ đặt email riêng cho working tree hiện tại:

~~~bash
git config --worktree user.email "feature-team@example.invalid"
~~~

Kiểm tra:

~~~bash
git config --worktree --list --show-origin
git config --show-origin --get user.email
~~~

Lệnh --get không chỉ định scope sẽ trả về giá trị hiệu lực; --show-origin giúp xác định giá trị đó đến từ file nào.

### Bật worktree config

Trong một repository mà bạn quản lý, có thể bật extension bằng:

~~~bash
git config --local extensions.worktreeConfig true
~~~

Sau khi bật, Git sử dụng file cấu hình riêng cho mỗi worktree bên cạnh cấu hình chung. Trước khi bật trên repository đang có nhiều worktree, hãy đọc hướng dẫn Git tương ứng với phiên bản đang dùng và kiểm tra các thiết lập vốn chỉ có ý nghĩa cho từng working tree. Một số cấu hình liên quan đến đường dẫn và trạng thái checkout cần được đặt đúng nơi để các worktree không ảnh hưởng lẫn nhau.

Không bật extension tùy tiện trên repository dùng chung khi chưa kiểm tra cách nhóm đang quản lý worktree. Việc bật extension thay đổi cách Git đọc cấu hình cho repository đó.

### Khi nào nên dùng worktree scope?

Ví dụ, bạn có hai working tree:

- ../app-main để xử lý lỗi trên nhánh main.
- ../app-feature để phát triển tính năng.

Nếu mỗi working tree cần email commit khác nhau, có thể cấu hình danh tính riêng bằng worktree scope sau khi extension được bật. Cấu hình ở một working tree không tự ghi đè cấu hình của working tree còn lại.

Đây là phạm vi cấu hình hữu ích khi làm nhiều công việc song song trong cùng một repository. Nếu không dùng nhiều worktree hoặc không cần thiết lập riêng, global và local thường đã đủ.

## Cấp command: ghi đè tạm bằng tham số -c

Tùy chọn -c truyền cấu hình cho một lần gọi Git. Cú pháp:

~~~bash
git -c <key>=<value> <command>
~~~

Ví dụ buộc lệnh status luôn hiển thị màu:

~~~bash
git -c color.ui=always status
~~~

Hoặc dùng danh tính khác cho đúng một commit:

~~~bash
git -c user.name="Release Bot" -c user.email="release-bot@example.invalid" commit -m "Prepare release"
~~~

Các giá trị truyền qua -c có độ ưu tiên cao hơn các file cấu hình system, global, local và worktree trong lần gọi đó. Sau khi lệnh kết thúc, giá trị không được ghi vào các file cấu hình lâu dài.

Có thể dùng -c để thử một thiết lập trước khi quyết định lưu vào global hoặc local:

~~~bash
git -c pull.rebase=true pull
~~~

Lệnh trên chạy pull với pull.rebase=true cho lần gọi đó. Nó không thay đổi pull.rebase trong .gitconfig hoặc .git/config.

### Truyền nhiều tham số -c

Có thể đặt nhiều cặp khóa/giá trị trong cùng lệnh:

~~~bash
git -c color.ui=always -c core.pager=cat log --oneline
~~~

Nếu giá trị có dấu cách, đặt trong dấu nháy theo quy tắc của shell đang sử dụng. Ví dụ PowerShell, Bash và CMD có một số khác biệt về cách xử lý dấu nháy; hãy kiểm tra lệnh được truyền đúng như mong muốn.

-c hữu ích cho script, automation, kiểm thử và thao tác một lần. Không nên dùng nó thay cho cấu hình global/local nếu thiết lập cần áp dụng ổn định cho nhiều lệnh.

## Cách xác định giá trị hiệu lực và tìm nguyên nhân cấu hình bị ghi đè

Khi một lệnh Git hoạt động khác mong đợi, đừng vội sửa file cấu hình. Trước tiên, xác định khóa nào đang có hiệu lực và giá trị đến từ đâu.

Ví dụ user.email không đúng:

~~~bash
git config --show-origin --show-scope --get-all user.email
git config --get user.email
~~~

Nếu có nhiều giá trị, xem toàn bộ danh sách và xác định khóa đó có phải loại multi-valued hay không. Với khóa đơn trị, giá trị ở cấp ưu tiên cao hơn thường thắng. Với khóa nhiều giá trị, Git hoặc chương trình sử dụng khóa có thể xử lý nhiều giá trị theo cách riêng.

Ví dụ core.autocrlf được đặt ở global nhưng local ghi đè:

~~~bash
git config --global core.autocrlf false
git config --local core.autocrlf true
~~~

Khi chạy trong repository đó, local thường có ưu tiên cao hơn global. Xác định nguồn thực tế:

~~~bash
git config --show-origin --show-scope --get-all core.autocrlf
git config --get core.autocrlf
~~~

Nếu xóa giá trị local:

~~~bash
git config --local --unset core.autocrlf
~~~

Giá trị global sẽ trở thành giá trị hiệu lực nếu không có cấp cao hơn ghi đè. Đây là lý do sau khi gỡ cấu hình ở một cấp, cần kiểm tra lại toàn bộ chuỗi ưu tiên.

### Kiểm tra cấu hình được include

Git cho phép một file cấu hình nạp file khác bằng include.path. Có thể dùng includeIf để chỉ nạp file khi điều kiện về đường dẫn repository hoặc nhánh phù hợp.

Ví dụ:

~~~ini
[includeIf "gitdir:~/work/"]
    path = ~/.gitconfig-work
~~~

Khi repository nằm dưới thư mục phù hợp, Git có thể nạp thêm thiết lập từ file được chỉ định. Điều này hữu ích khi bạn có nhiều nhóm repository và muốn dùng danh tính hoặc quy tắc khác nhau.

Xem nguồn thực tế bằng:

~~~bash
git config --list --show-origin --show-scope
~~~

Nếu một giá trị xuất hiện từ file include, hãy kiểm tra cả file gốc chứa chỉ thị include và file được nạp. Đừng sửa nhầm file global chính khi giá trị thực tế đến từ một file điều kiện.

## Cấu hình có nhiều giá trị

Không phải khóa nào cũng chỉ có một giá trị. Một số khóa được phép lặp lại nhiều lần. Ví dụ, remote có thể có nhiều refspec fetch:

~~~bash
git config --get-all remote.origin.fetch
~~~

--add thêm một giá trị mà không thay thế các giá trị đã có:

~~~bash
git config --local --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"
~~~

--replace-all thay thế các giá trị khớp bằng giá trị mới:

~~~bash
git config --local --replace-all remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
~~~

--unset-all xóa mọi giá trị của khóa:

~~~bash
git config --local --unset-all remote.origin.fetch
~~~

Các ví dụ trên tác động trực tiếp tới cách fetch remote. Chỉ sử dụng khi hiểu rõ refspec hiện có và mục tiêu cấu hình. Với khóa nhiều giá trị, hãy xem --get-all trước khi sửa để tránh vô tình xóa một phần thiết lập cần thiết.

## Kiểm tra kiểu dữ liệu và cú pháp giá trị

Git hỗ trợ đọc cấu hình theo kiểu dữ liệu để tránh diễn giải sai giá trị.

Ví dụ đọc boolean:

~~~bash
git config --type=bool --get pull.rebase
~~~

Đọc số nguyên:

~~~bash
git config --type=int --get gc.auto
~~~

Đọc giá trị dạng path:

~~~bash
git config --type=path --get core.excludesfile
~~~

Giá trị boolean thường chấp nhận các dạng như true, false, yes, no, on, off, 1 và 0 theo quy tắc Git. Dùng --type=bool để Git chuyển đổi và báo lỗi nếu giá trị không hợp lệ.

Không phải khóa nào cũng có kiểu đơn giản. Hãy tham khảo tài liệu của khóa cụ thể nếu giá trị là đường dẫn, thời hạn, URL hay cấu trúc đặc biệt.

## Chỉnh sửa file cấu hình trực tiếp

Có thể dùng --edit để mở file cấu hình ở cấp mong muốn:

~~~bash
git config --system --edit
git config --global --edit
git config --local --edit
~~~

Worktree config có thể chỉnh sửa khi extension đã bật:

~~~bash
git config --worktree --edit
~~~

Cấu hình Git sử dụng cú pháp dạng INI. Ví dụ:

~~~ini
[user]
    name = Developer Name
    email = dev@example.invalid

[init]
    defaultBranch = main

[pull]
    rebase = true
~~~

Sau khi sửa file trực tiếp, kiểm tra lại cú pháp và giá trị:

~~~bash
git config --list --show-origin --show-scope
git config --get user.name
git config --type=bool --get pull.rebase
~~~

Ưu tiên dùng git config để thêm, thay hoặc xóa khóa thông thường. Sửa trực tiếp file hữu ích khi cần xem cấu trúc section, comment hoặc điều chỉnh nhiều khóa cùng lúc. Hãy tránh chỉnh sửa đồng thời file cấu hình từ nhiều tiến trình Git.

## Bảo vệ thông tin nhạy cảm trong cấu hình

Một số thiết lập có thể chứa hoặc tham chiếu tới thông tin nhạy cảm, ví dụ:

- URL remote có nhúng username hoặc token.
- HTTP extra header dùng để xác thực.
- Đường dẫn tới file credential hoặc private key.
- Tham số của credential helper.
- Đường dẫn nội bộ hoặc thông tin máy chủ công ty.

Không đưa token, password hoặc private key trực tiếp vào lệnh git config nếu chúng có thể bị lưu trong shell history, log hoặc file cấu hình không phù hợp. Ưu tiên credential manager hoặc cơ chế cấp phát bí mật được tổ chức hỗ trợ.

Khi chia sẻ kết quả git config --list, kiểm tra và che thông tin nhạy cảm trước. Dùng --show-origin để xác định nguồn cấu hình nhưng không công khai giá trị xác thực.

## Quy trình thực hành: thiết lập danh tính theo repository

Giả sử bạn dùng email cá nhân cho repository riêng nhưng cần email công ty cho repository công việc.

Đầu tiên đặt danh tính mặc định ở global:

~~~bash
git config --global user.name "Developer Name"
git config --global user.email "personal@example.invalid"
~~~

Đi vào repository công việc và đặt danh tính local:

~~~bash
cd path/to/company-project
git config --local user.name "Work Developer"
git config --local user.email "work@example.invalid"
~~~

Kiểm tra nguồn và giá trị hiệu lực:

~~~bash
git config --show-origin --show-scope --get-all user.name
git config --show-origin --show-scope --get-all user.email
git config --get user.name
git config --get user.email
~~~

Tạo một commit thử trong nhánh công việc nếu phù hợp với quy trình, sau đó kiểm tra metadata:

~~~bash
git log -1 --format=fuller
~~~

Các trường Author và Commit sẽ cho biết tên/email được ghi vào commit. Việc thay đổi cấu hình sau đó chỉ ảnh hưởng commit mới, không tự sửa commit cũ.

## Quy trình thực hành: thử cấu hình tạm bằng -c

Giả sử muốn kiểm tra xem pull theo rebase có phù hợp với một repository trước khi lưu thiết lập lâu dài.

Xem cấu hình hiện tại:

~~~bash
git config --show-origin --show-scope --get-all pull.rebase
~~~

Thử một lần:

~~~bash
git -c pull.rebase=true pull
~~~

Nếu kết quả đúng với quy trình của nhóm, có thể cân nhắc lưu ở local:

~~~bash
git config --local pull.rebase true
~~~

Kiểm tra lại:

~~~bash
git config --show-origin --get pull.rebase
~~~

Nếu không muốn giữ thiết lập, chỉ cần không ghi nó vào file cấu hình. Nếu đã lưu local và muốn bỏ:

~~~bash
git config --local --unset pull.rebase
~~~

Sau khi bỏ, kiểm tra xem global hoặc system có giá trị khác sẽ trở thành giá trị hiệu lực hay không.

## Những lỗi thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đã đặt global nhưng Git vẫn dùng giá trị khác | Local, worktree hoặc command có ưu tiên cao hơn | Dùng --show-origin --show-scope --get-all để tìm nguồn |
| git config --local báo không ở trong repository | Đang chạy ngoài repository hoặc sai thư mục | Chuyển vào repository cần cấu hình |
| git config --worktree không hoạt động | Chưa bật extensions.worktreeConfig hoặc đang ở ngữ cảnh không hỗ trợ | Kiểm tra extension và trạng thái repository |
| Xóa khóa nhưng Git vẫn trả về giá trị | Khóa còn ở cấp khác hoặc file include | Xem toàn bộ nguồn và scope |
| git config --get chỉ in một giá trị | Khóa có nhiều giá trị | Dùng --get-all |
| Đổi user.name nhưng commit cũ vẫn hiển thị tên cũ | Metadata commit đã được ghi trước đó | Kiểm tra commit mới; muốn sửa commit cũ cần thao tác viết lại lịch sử phù hợp |
| -c không được giữ cho lệnh sau | -c chỉ áp dụng lần gọi hiện tại | Dùng git config --global, --local hoặc --worktree nếu cần lưu |
| Lệnh cấu hình trả lỗi quyền truy cập | Không có quyền ghi file system hoặc file được bảo vệ | Dùng scope phù hợp hoặc nhờ quản trị viên |
| Giá trị boolean không hợp lệ | Cú pháp hoặc giá trị cấu hình sai | Kiểm tra bằng git config --type=bool --get <key> |

## Thói quen quản lý cấu hình an toàn

- Đặt ở global những thiết lập cá nhân muốn dùng chung giữa các repository.
- Đặt ở local những quy tắc chỉ dành cho một repository.
- Chỉ dùng worktree scope khi đã bật và hiểu cơ chế worktree config.
- Dùng -c để thử nghiệm hoặc ghi đè cho một lệnh.
- Dùng --show-origin và --show-scope trước khi sửa một giá trị khó truy tìm.
- Dùng --get-all với khóa có thể chứa nhiều giá trị.
- Kiểm tra giá trị hiệu lực sau khi thêm, sửa hoặc xóa.
- Không lưu secret trong file cấu hình hoặc log không an toàn.
- Ghi lại quy tắc dự án trong tài liệu hoặc cấu hình được quản lý chung khi các thành viên cần dùng giống nhau.

## Ghi nhớ

Git đọc cấu hình từ nhiều cấp: system cho máy, global cho người dùng, local cho repository, worktree cho từng working tree khi extension được bật và command cho một lần gọi qua -c. Cấp ưu tiên cao hơn thường ghi đè giá trị đơn trị ở cấp thấp hơn, nhưng khóa nhiều giá trị có thể được cộng dồn. Dùng git config --list --show-origin --show-scope để tìm nguồn, --get hoặc --get-all để đọc, --global/--local/--worktree để ghi đúng phạm vi và -c để thử một cấu hình tạm thời. Luôn xác minh giá trị hiệu lực sau khi thay đổi và bảo vệ thông tin xác thực khỏi file cấu hình hoặc log bị chia sẻ.

