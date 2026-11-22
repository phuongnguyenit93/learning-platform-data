# Tổ chức hook dùng chung bằng core.hooksPath

## Vì sao cần tổ chức hook dùng chung?

Git hook là chương trình được Git gọi tự động tại những thời điểm nhất định trong quy trình làm việc, chẳng hạn trước khi commit, sau khi checkout hoặc trước khi push. Hook có thể kiểm tra định dạng, chạy test, xác thực thông điệp commit, kiểm tra thay đổi staged hoặc thực hiện tác vụ tự động khác.

Mặc định, Git tìm hook trong thư mục hooks của repository, thường là .git/hooks. Các file mẫu ở đó thường có đuôi .sample và chưa được thực thi. Thư mục này nằm trong vùng dữ liệu Git của bản clone, không phải nội dung được commit cùng mã nguồn. Vì vậy, hook tự tạo trong .git/hooks thường chỉ tồn tại trên máy người cài đặt.

Khi một nhóm muốn mọi thành viên dùng cùng bộ hook, có thể đặt script trong một thư mục được quản lý bằng Git, ví dụ .githooks/, rồi cấu hình core.hooksPath để Git tìm hook tại đó.

Cách tổ chức này giúp:

- Lưu script hook cùng lịch sử repository để mọi người review và cập nhật.
- Dùng cùng quy tắc kiểm tra trước commit hoặc push.
- Giảm việc mỗi thành viên phải tự chép script vào .git/hooks.
- Quản lý phiên bản hook bằng commit và pull request.
- Tách script hook của dự án khỏi hook cá nhân dùng trên nhiều repository.

Điều cần hiểu rõ là core.hooksPath chỉ chỉ định thư mục Git sẽ tìm hook. Nó không tự tải, cài đặt hoặc thực thi script trong repository khi clone. Mỗi bản clone cần được cấu hình để sử dụng thư mục hook của dự án.

## Git tìm hook ở đâu?

Nếu không cấu hình core.hooksPath, Git dùng thư mục hooks mặc định bên trong Git directory của repository, thường là .git/hooks.

Kiểm tra đường dẫn Git directory:

~~~bash
git rev-parse --git-dir
~~~

Nếu muốn xem đường dẫn gốc của repository:

~~~bash
git rev-parse --show-toplevel
~~~

Khi cấu hình core.hooksPath, Git tìm hook trong thư mục được chỉ định thay cho thư mục hooks mặc định. Ví dụ:

~~~bash
git config --local core.hooksPath .githooks
~~~

Nếu repository có cấu trúc:

~~~text
inventory-app/
├── .git/
├── .githooks/
│   ├── pre-commit
│   ├── commit-msg
│   └── pre-push
├── src/
└── README.md
~~~

Git sẽ tìm các file có tên chính xác như pre-commit, commit-msg và pre-push trong .githooks/.

Tên file hook phải trùng tên hook mà Git gọi. Không đặt đuôi .sh nếu muốn Git tự tìm hook theo tên chuẩn. Ví dụ file .githooks/pre-commit.sh sẽ không được Git tự động nhận là hook pre-commit; tên cần dùng là .githooks/pre-commit.

### core.hooksPath thay thế thư mục mặc định

Khi core.hooksPath được đặt, Git dùng thư mục đó thay cho thư mục hooks mặc định. Git không tự kết hợp hai thư mục.

Điều này có nghĩa:

- Hook nằm trong .git/hooks có thể không còn được gọi.
- Hook nằm trong thư mục core.hooksPath mới sẽ được Git tìm theo tên chuẩn.
- Nếu muốn giữ cả hook cá nhân và hook dự án, cần tổ chức một cơ chế gọi nối tiếp hoặc hợp nhất logic.

Không giả định rằng đặt core.hooksPath sẽ bổ sung thêm một thư mục tìm kiếm thứ hai.

## Tạo thư mục hook được quản lý bằng Git

Trong thư mục gốc repository, tạo .githooks:

~~~bash
mkdir -p .githooks
~~~

Trên PowerShell có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force .githooks
~~~

Sau đó tạo các file hook cần thiết. Ví dụ:

~~~text
.githooks/
├── pre-commit
├── commit-msg
└── pre-push
~~~

Chỉ thêm các hook thực sự phục vụ quy trình dự án. Mỗi hook nên có một trách nhiệm rõ ràng, thông báo lỗi dễ hiểu và thời gian chạy phù hợp với thời điểm được gọi.

Một repository có thể chỉ cần pre-commit để kiểm tra whitespace và format; không nhất thiết phải cài tất cả hook Git hỗ trợ.

### Đặt script hook vào repository

Ví dụ một hook pre-commit đơn giản:

~~~sh
#!/bin/sh
set -eu

echo "Checking staged changes..."

if ! git diff --cached --check; then
    echo "Commit stopped: fix whitespace errors in staged changes."
    exit 1
fi

echo "Staged changes passed the whitespace check."
~~~

Hook này kiểm tra phần thay đổi đã stage. Nếu có lỗi whitespace được Git phát hiện, script trả mã khác 0 và Git dừng thao tác commit.

Dùng git diff --cached thay cho git diff vì mục tiêu của pre-commit thường là kiểm tra chính xác nội dung sắp được ghi vào commit. Nếu chỉ chạy git diff, script có thể bỏ qua phần đã stage.

Ví dụ commit-msg kiểm tra quy ước thông điệp:

~~~sh
#!/bin/sh
set -eu

message_file=$1

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]./_-]+\))?: .+' "$message_file"; then
    echo "Commit message must follow: type(scope): description"
    exit 1
fi
~~~

Git truyền đường dẫn file thông điệp commit vào tham số đầu tiên của hook commit-msg. Script đọc file đó và trả mã khác 0 nếu thông điệp không đạt quy ước.

Ví dụ pre-push tối giản:

~~~sh
#!/bin/sh
set -eu

echo "Running checks before push..."
./gradlew test
~~~

Ví dụ này giả định repository có Gradle Wrapper và môi trường chạy hook có thể thực thi lệnh đó. Nếu dự án dùng Maven, Node.js hoặc công cụ khác, hãy thay bằng lệnh phù hợp. Không đưa một lệnh test cụ thể vào hook dùng chung nếu thành viên không có runtime hoặc dependency cần thiết.

Các script trên là ví dụ minh họa. Khi triển khai thật, hãy xác định shell, runtime, đường dẫn công cụ và hệ điều hành được hỗ trợ.

## Cấu hình core.hooksPath cho repository

Sau khi thư mục .githooks đã có các script, cấu hình local của repository:

~~~bash
git config --local core.hooksPath .githooks
~~~

Kiểm tra giá trị:

~~~bash
git config --local --get core.hooksPath
git config --show-origin --show-scope --get core.hooksPath
~~~

Thiết lập local được lưu trong cấu hình của bản clone hiện tại, thường là .git/config. File .git/config không được commit cùng repository, vì vậy thành viên khác sẽ không tự nhận được thiết lập này khi pull.

Để tránh phụ thuộc vào thư mục làm việc hiện tại hoặc cách Git gọi hook, có thể cấu hình đường dẫn tuyệt đối được tính từ repository root.

Ví dụ Bash:

~~~bash
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

Ví dụ PowerShell:

~~~powershell
$repoRoot = git rev-parse --show-toplevel
$hooksPath = Join-Path $repoRoot ".githooks"
git config --local core.hooksPath $hooksPath
~~~

Git chấp nhận đường dẫn tương đối hoặc tuyệt đối. Với đường dẫn tương đối, Git diễn giải theo thư mục làm việc của hook; hầu hết hook của repository non-bare chạy từ thư mục gốc working tree, nhưng có khác biệt giữa loại hook và ngữ cảnh repository. Dùng đường dẫn tuyệt đối trong script setup giúp tránh nhầm lẫn này.

Không ghi đường dẫn tuyệt đối của máy cá nhân vào file được commit. Hãy để script setup tính đường dẫn tại từng bản clone và ghi vào cấu hình local.

## Cấp quyền thực thi cho hook

Git chỉ chạy hook nếu file hook có thể thực thi theo môi trường. Trên Linux và macOS, cần đặt executable bit:

~~~bash
chmod +x .githooks/pre-commit
chmod +x .githooks/commit-msg
chmod +x .githooks/pre-push
~~~

Stage thay đổi mode file để Git lưu lại executable bit:

~~~bash
git add .githooks
git ls-files --stage -- .githooks
~~~

Một file thực thi thường có mode 100755; file thông thường có mode 100644.

Trên Windows, hành vi phụ thuộc Git for Windows, shell và môi trường thực thi. Git Bash thường cung cấp shell để chạy script POSIX; hãy kiểm tra hook thực tế trên phiên bản Git for Windows mà nhóm hỗ trợ. Có thể đặt mode executable trong index bằng:

~~~bash
git add .githooks/pre-commit
git update-index --chmod=+x .githooks/pre-commit
git ls-files --stage -- .githooks/pre-commit
~~~

Nếu file đã stage trước khi thay đổi mode, kiểm tra lại git ls-files --stage và stage lại khi cần.

### Dùng line ending phù hợp

Script shell nên dùng LF để tránh lỗi như /bin/sh^M khi chạy trong môi trường POSIX. Có thể quy định trong .gitattributes:

~~~gitattributes
.githooks/* text eol=lf
~~~

Quy tắc này giúp Git checkout các hook trong thư mục .githooks với line ending LF. Nếu repository có script Windows riêng, hãy đặt attributes phù hợp cho từng loại file.

Không chuyển đổi line ending hàng loạt trong lúc chỉ muốn thêm hook. Hãy kiểm tra diff và attributes của đúng file.

## Chia sẻ hook cho thành viên mới

Vì core.hooksPath được cấu hình ở local, cần có một bước onboarding để mỗi thành viên bật hook sau khi clone.

Một quy trình phổ biến:

1. Clone repository.
2. Đọc hướng dẫn về hook và kiểm tra script trong .githooks.
3. Chạy script setup của dự án hoặc lệnh git config local.
4. Kiểm tra core.hooksPath và quyền thực thi.
5. Tạo một commit thử trong nhánh cá nhân hoặc chạy lệnh test hook phù hợp.

Có thể ghi lệnh cài đặt vào tài liệu onboarding:

~~~bash
git config --local core.hooksPath .githooks
~~~

Hoặc cung cấp script setup để tự tính đường dẫn:

~~~sh
#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"

echo "Git hooks are configured from $repo_root/.githooks"
~~~

Ví dụ này có thể lưu trong scripts/setup-hooks.sh. Thành viên chạy một lần sau khi clone:

~~~bash
sh scripts/setup-hooks.sh
~~~

Script setup cần được review giống mọi script khác trong repository. Git clone không tự chạy script setup và cũng không tự cấu hình core.hooksPath từ file được commit.

### Vì sao Git không tự bật hook từ repository vừa clone?

Hook là chương trình có thể chạy lệnh tùy ý trên máy người dùng. Nếu clone repository bất kỳ tự động kích hoạt script hook do repository đó cung cấp, mã độc có thể chạy trong quá trình commit hoặc push sau đó.

Vì vậy, Git không tự cài các hook được commit trong thư mục dự án. Người dùng cần chủ động cấu hình core.hooksPath sau khi kiểm tra và tin cậy nội dung script.

Đây là ranh giới bảo mật quan trọng: review hook trước khi bật, đặc biệt với repository bên ngoài tổ chức.

## Dùng core.hooksPath ở global và local

Có thể cấu hình core.hooksPath ở nhiều scope.

### Cấu hình global cho hook cá nhân

Nếu muốn dùng một bộ hook cá nhân trên nhiều repository, tạo thư mục bên ngoài các repository, ví dụ:

~~~text
~/.config/git/hooks/
├── pre-commit
└── post-checkout
~~~

Cấu hình global:

~~~bash
git config --global core.hooksPath ~/.config/git/hooks
~~~

Thiết lập này áp dụng cho các repository của người dùng hiện tại, trừ khi có cấu hình cấp cao hơn ghi đè.

Cách này phù hợp với hook cá nhân như nhắc nhở, kiểm tra công cụ cục bộ hoặc tác vụ tiện ích. Không nên đưa quy tắc bắt buộc của dự án vào thư mục cá nhân không được quản lý chung.

### Cấu hình local cho hook dự án

Trong repository cần dùng hook dự án:

~~~bash
git config --local core.hooksPath .githooks
~~~

Local có ưu tiên cao hơn global đối với khóa đơn trị core.hooksPath. Vì vậy, repository có thể sử dụng bộ hook của dự án thay cho bộ hook cá nhân.

### Hai thư mục hook không tự động được kết hợp

Nếu global trỏ tới thư mục hook cá nhân và local trỏ tới .githooks của dự án, Git sử dụng giá trị local. Nó không tự tìm hook ở cả hai nơi.

Nếu nhóm cần cả hook chung của tổ chức và hook riêng của dự án, có thể:

- Tạo một hook dispatcher trong thư mục được chọn và gọi các script con theo thứ tự.
- Đặt hook chung thành thư viện/script được hook dự án gọi.
- Dùng một công cụ quản lý hook có khả năng kết hợp cấu hình và tài liệu rõ ràng.

Dispatcher cần kiểm tra lỗi và trả mã thoát phù hợp. Nếu một hook con thất bại, dispatcher phải truyền thất bại về cho Git khi mục tiêu là chặn thao tác.

Không dùng hai cấu hình core.hooksPath với kỳ vọng Git tự merge nội dung của hai thư mục.

## Chọn hook phù hợp với từng giai đoạn

Git có nhiều loại hook. Một số hook phổ biến:

| Hook | Thời điểm | Mục đích thường dùng |
|---|---|---|
| pre-commit | Trước khi tạo commit | Lint, format check, kiểm tra staged diff |
| prepare-commit-msg | Sau khi Git tạo nội dung ban đầu, trước khi mở editor | Chuẩn bị hoặc bổ sung thông điệp |
| commit-msg | Sau khi người dùng nhập message, trước khi commit | Kiểm tra quy ước commit message |
| post-commit | Sau khi commit hoàn tất | Thông báo hoặc tác vụ phụ |
| pre-push | Trước khi push ref lên remote | Chạy test hoặc kiểm tra điều kiện chia sẻ |
| pre-rebase | Trước khi bắt đầu rebase | Ngăn rebase trong một số trường hợp |
| post-checkout | Sau khi checkout hoặc switch | Cập nhật công cụ phụ thuộc vào nhánh |
| post-merge | Sau khi merge hoàn tất | Cập nhật dependency hoặc thông báo |

Hook có thể nhận tham số và dữ liệu qua stdin tùy loại. Trước khi viết script, đọc tài liệu của đúng hook để hiểu hợp đồng gọi.

Ví dụ, pre-push nhận tên remote và URL qua tham số, còn danh sách ref được gửi qua stdin. Script cần đọc đúng định dạng nếu muốn kiểm tra nhánh hoặc commit được push. Không giả định mọi hook đều nhận cùng tham số.

### Chọn kiểm tra nhanh cho pre-commit

Pre-commit thường chạy mỗi lần tạo commit, vì vậy nên ưu tiên kiểm tra nhanh trên nội dung staged. Các tác vụ dài như toàn bộ integration test có thể làm giảm tốc độ phát triển nếu chạy cho mọi commit.

Có thể chia kiểm tra:

- pre-commit: whitespace, format, lint nhanh, secret scan trên staged files.
- commit-msg: quy ước thông điệp và mã issue.
- pre-push: unit test hoặc kiểm tra rộng hơn.
- CI: toàn bộ test, integration test và kiểm tra môi trường.

Cách phân chia này giúp người phát triển nhận phản hồi sớm mà không phải chờ toàn bộ pipeline trước mỗi commit.

## Thiết kế hook dễ bảo trì

Một bộ hook dùng chung nên có các đặc điểm:

- **Rõ mục tiêu:** mỗi hook giải quyết một quy tắc có thể giải thích.
- **Có thể lặp lại:** chạy nhiều lần không tạo ra thay đổi không mong muốn.
- **Thông báo dễ hiểu:** nêu file hoặc điều kiện cần sửa.
- **Tốc độ phù hợp:** tránh chạy tác vụ nặng ở mọi commit nếu có thể chuyển sang pre-push hoặc CI.
- **Ít phụ thuộc:** dùng công cụ có trong môi trường nhóm hoặc kiểm tra trước khi chạy.
- **Tương thích nền tảng:** thống nhất shell, runtime và line ending được hỗ trợ.
- **Không làm lộ dữ liệu:** không in token, password hoặc nội dung bí mật.
- **Dễ kiểm thử:** có thể chạy script độc lập hoặc kích hoạt hook trong repository thử nghiệm.

Tránh để hook tự động sửa hàng loạt file mà không thông báo. Nếu hook formatter thay đổi nội dung, hãy yêu cầu người dùng xem diff và stage lại thay đổi sau khi đã xác nhận.

Hook nên kết thúc với mã 0 khi kiểm tra đạt. Với hook chặn thao tác, trả mã khác 0 khi điều kiện không đạt và in hướng dẫn khắc phục. Các hook hậu sự kiện như post-commit chạy sau khi thao tác đã hoàn tất; chúng không thể dùng để hủy commit vừa tạo.

## Kiểm tra và gỡ lỗi hook

Nếu hook không chạy, kiểm tra theo thứ tự:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
git rev-parse --show-toplevel
git status
git ls-files --stage -- .githooks
~~~

Xác nhận:

1. core.hooksPath đang trỏ đúng thư mục.
2. File hook có tên chính xác, ví dụ pre-commit.
3. File tồn tại trong thư mục được cấu hình.
4. File có quyền thực thi theo môi trường.
5. Shebang trỏ tới shell có sẵn.
6. Line ending và encoding phù hợp.
7. Script không phụ thuộc biến môi trường hoặc tool chưa được cài.
8. Hook đang được gọi bởi đúng thao tác Git.

Có thể chạy trực tiếp script từ shell để kiểm tra cú pháp và lệnh bên trong, nhưng cần nhớ môi trường và tham số có thể khác khi Git gọi hook. Đối với hook có tham số hoặc stdin, hãy thử bằng repository tạm và mô phỏng đúng dữ liệu đầu vào.

Một số phiên bản Git hỗ trợ lệnh kiểm tra hook:

~~~bash
git hook run pre-commit
~~~

Nếu phiên bản Git không có lệnh này, hãy kích hoạt thao tác tương ứng trong repository thử nghiệm hoặc chạy script trực tiếp với dữ liệu mẫu.

### Kiểm tra hook đang dùng có phải thư mục mặc định không

Khi core.hooksPath đã được đặt, hook trong .git/hooks có thể không được gọi. Nếu hook cũ ngừng hoạt động sau khi cấu hình .githooks, kiểm tra xem script đó có cần được chuyển hoặc gọi từ bộ hook mới không.

Có thể xóa cấu hình local để trở lại thư mục mặc định:

~~~bash
git config --local --unset core.hooksPath
~~~

Nếu global vẫn đặt core.hooksPath, Git sẽ dùng giá trị global. Nếu không có giá trị ở cấp khác, Git quay lại thư mục hooks mặc định.

Để bỏ cấu hình global:

~~~bash
git config --global --unset core.hooksPath
~~~

Luôn kiểm tra giá trị hiệu lực sau khi gỡ:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
~~~

## Xử lý hook bị bỏ qua hoặc không được thực thi

Một số lệnh hỗ trợ tùy chọn bỏ qua hook nhất định, ví dụ:

~~~bash
git -c core.hooksPath=/dev/null commit -m "Temporary local commit"
~~~

Hoặc:

~~~bash
git commit --no-verify
git push --no-verify
~~~

Tùy chọn --no-verify bỏ qua một số hook có thể chặn thao tác như pre-commit, commit-msg hoặc pre-push tùy lệnh. Không phải tất cả hook đều bị bỏ qua bởi tùy chọn này; ví dụ prepare-commit-msg không bị bỏ qua theo cách đó.

Việc bỏ qua hook có thể hữu ích khi xử lý tình huống khẩn cấp đã được nhóm chấp thuận, nhưng không nên dùng thường xuyên để né quy tắc chất lượng. Nếu một quy tắc bắt buộc, cần thực thi thêm ở CI hoặc server.

Đường dẫn /dev/null là cách vô hiệu hóa hook thường dùng trên môi trường Unix-like. Với Windows, cần kiểm tra cách Git for Windows xử lý đường dẫn đặc biệt trước khi dùng trong script hoặc hướng dẫn dùng chung.

## Hook phía client không thay thế kiểm tra phía server

Hook được cấu hình bằng core.hooksPath chạy trên máy người dùng. Người dùng có thể chưa cài hook, dùng một cấu hình khác hoặc bỏ qua một số hook. Vì vậy, hook client phù hợp để phản hồi sớm và giúp tuân thủ quy ước, nhưng không phải ranh giới bảo vệ duy nhất.

Nếu một chính sách cần được áp dụng cho mọi thay đổi, hãy kiểm tra ở nơi có thể thực thi tập trung:

- CI chạy trên pull request.
- Branch protection hoặc merge checks.
- Server-side hooks như pre-receive hoặc update nếu nền tảng cho phép.
- Quy trình review và phê duyệt.

Ví dụ, secret scanning trước commit giúp phát hiện sớm trên máy phát triển. CI hoặc công cụ kiểm soát ở server vẫn cần kiểm tra để tránh trường hợp hook bị bỏ qua hoặc không được cài.

## Quy trình mẫu triển khai hook dùng chung

Giả sử nhóm muốn mọi commit đều kiểm tra whitespace và mọi thông điệp commit theo định dạng type(scope): description.

### Bước 1: Tạo thư mục và hook

~~~bash
mkdir -p .githooks
~~~

Tạo file .githooks/pre-commit:

~~~sh
#!/bin/sh
set -eu

git diff --cached --check
~~~

Tạo file .githooks/commit-msg:

~~~sh
#!/bin/sh
set -eu

message_file=$1
if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]./_-]+\))?: .+' "$message_file"; then
    echo "Use: type(scope): description"
    exit 1
fi
~~~

### Bước 2: Bảo đảm file thực thi và line ending

Trên Linux/macOS hoặc Git Bash:

~~~bash
chmod +x .githooks/pre-commit .githooks/commit-msg
~~~

Có thể thêm quy tắc trong .gitattributes:

~~~gitattributes
.githooks/* text eol=lf
~~~

Stage và kiểm tra mode:

~~~bash
git add .githooks .gitattributes
git ls-files --stage -- .githooks
~~~

### Bước 3: Cấu hình core.hooksPath

~~~bash
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

Kiểm tra:

~~~bash
git config --show-origin --show-scope --get core.hooksPath
~~~

### Bước 4: Thử hook

Tạo thay đổi staged và thử commit với thông điệp hợp lệ:

~~~bash
git add src/example.txt
git commit -m "docs(readme): update setup instructions"
~~~

Thử một thông điệp không hợp lệ trong repository thử nghiệm:

~~~bash
git commit -m "update stuff"
~~~

Hook commit-msg cần từ chối thông điệp không đạt quy ước. Nếu commit bị từ chối, sửa thông điệp và thử lại.

### Bước 5: Chia sẻ và hướng dẫn cài đặt

Commit các file .githooks và .gitattributes vào repository. Cập nhật hướng dẫn onboarding của dự án để thành viên mới chạy lệnh cấu hình local sau khi clone.

Không commit .git/config hoặc đường dẫn tuyệt đối riêng của máy. Mỗi người tự cấu hình core.hooksPath trong bản clone của mình thông qua script setup hoặc hướng dẫn đã review.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hook trong .githooks không chạy | Chưa cấu hình core.hooksPath | Đặt cấu hình local và kiểm tra origin |
| Hook trong .git/hooks ngừng chạy | core.hooksPath đã thay thế thư mục mặc định | Chuyển logic cần giữ vào thư mục mới hoặc dispatcher |
| Hook không được tìm thấy | Tên file có đuôi hoặc sai tên chuẩn | Dùng đúng tên như pre-commit, commit-msg |
| Hook bị bỏ qua trên Linux/macOS | Thiếu executable bit | chmod +x và kiểm tra mode 100755 |
| Hook lỗi /bin/sh^M | File dùng CRLF | Chuẩn hóa script shell về LF |
| Hook chạy trên máy này nhưng lỗi máy khác | Thiếu shell/runtime hoặc lệnh phụ thuộc | Chuẩn hóa môi trường và kiểm tra tool trước khi chạy |
| Hook chạy quá lâu | Đặt toàn bộ test nặng ở pre-commit | Chuyển test rộng sang pre-push hoặc CI |
| Thành viên clone nhưng không có hook | Git không tự kích hoạt script từ repository | Cung cấp bước setup và hướng dẫn rõ ràng |
| Hook cá nhân biến mất khi bật hook dự án | Local core.hooksPath ghi đè global | Dùng dispatcher hoặc gọi hook chung từ hook dự án |
| Quy tắc vẫn bị vi phạm dù đã có hook | Người dùng bỏ qua hoặc chưa cài hook | Bổ sung kiểm tra bắt buộc ở CI/server |

## Checklist khi tổ chức hook dùng chung

- [ ] Hook được lưu trong thư mục được quản lý bằng Git, ví dụ .githooks/.
- [ ] Tên file trùng tên hook Git hỗ trợ.
- [ ] Script có shebang, line ending và quyền thực thi phù hợp.
- [ ] core.hooksPath được cấu hình đúng cho từng bản clone.
- [ ] Thành viên mới có hướng dẫn hoặc script setup.
- [ ] Script được review trước khi bật và có thông báo lỗi dễ hiểu.
- [ ] Hook chỉ chạy kiểm tra phù hợp với thời điểm gọi.
- [ ] Các hook dùng chung tương thích hệ điều hành và toolchain nhóm.
- [ ] Hook không in hoặc lưu secret.
- [ ] Có kiểm tra ở CI/server cho các quy tắc bắt buộc.
- [ ] Đã xác định cách kết hợp hook dự án với hook cá nhân nếu cần.
- [ ] Đã thử hook trong repository kiểm tra trước khi áp dụng rộng rãi.

## Ghi nhớ

core.hooksPath cho phép Git tìm hook trong một thư mục do bạn chọn thay cho .git/hooks. Nhóm có thể lưu script trong .githooks/ để review và version control, sau đó hướng dẫn từng bản clone cấu hình core.hooksPath ở local. Git không tự bật hook khi clone và không kết hợp nhiều thư mục hook; một cấu hình local có thể ghi đè cấu hình global. Hãy đặt đúng tên file, quyền thực thi và line ending, thiết kế script nhanh và dễ hiểu, kiểm tra bảo mật trước khi bật, đồng thời dùng CI hoặc server-side checks cho những quy tắc cần áp dụng bắt buộc.

