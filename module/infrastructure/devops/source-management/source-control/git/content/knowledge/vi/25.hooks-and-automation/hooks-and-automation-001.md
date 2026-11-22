# Hook phía máy người dùng và hook phía máy chủ

Git hooks là các chương trình được Git gọi tự động tại những thời điểm nhất định trong vòng đời thao tác Git. Chúng có thể kiểm tra nội dung trước khi tạo commit, xác thực thông điệp commit, chạy test trước khi push, ghi nhận hoạt động sau merge hoặc kiểm tra các ref trước khi máy chủ chấp nhận push.

Git chia hook thành hai nhóm theo nơi chúng chạy:

- **Client-side hooks:** chạy trên máy của người phát triển, trong repository local.
- **Server-side hooks:** chạy trên máy chủ Git khi máy chủ nhận hoặc xử lý thay đổi.

Hai nhóm có thể hỗ trợ cùng một quy trình, nhưng khác nhau về quyền kiểm soát và độ tin cậy. Client hook giúp phản hồi sớm và cải thiện trải nghiệm làm việc. Server hook giúp áp dụng chính sách tập trung cho mọi người gửi thay đổi tới repository. Với quy tắc bắt buộc như bảo vệ branch chính, quyền phát hành hoặc kiểm tra chính sách, cần thực thi ở phía máy chủ hoặc nền tảng quản lý repository.

## 1. Git hook là gì?

Hook là một script hoặc chương trình có tên trùng với một sự kiện mà Git hỗ trợ. Khi sự kiện xảy ra, Git tìm hook tương ứng và gọi nó. Hook có thể đọc tham số, nhận dữ liệu qua standard input, kiểm tra trạng thái repository, gọi công cụ bên ngoài hoặc từ chối thao tác bằng mã thoát khác 0 nếu loại hook đó cho phép.

Ví dụ:

- **pre-commit** chạy trước khi Git tạo commit.
- **commit-msg** kiểm tra file chứa thông điệp commit.
- **pre-push** chạy trước khi Git gửi ref lên remote.
- **pre-receive** chạy trên server khi nhận một lần push.
- **post-receive** chạy sau khi server cập nhật các ref thành công.

Hook không phải một commit và không tự động trở thành một phần của lịch sử dự án. Hook là mã thực thi được cấu hình trong repository hoặc môi trường server.

### 1.1. Hook giúp tự động hóa điều gì?

Các mục tiêu thường gặp:

- Kiểm tra whitespace, format và lint trước commit.
- Kiểm tra cấu trúc thông điệp commit.
- Chạy test nhanh trước khi push.
- Ngăn cập nhật ref không được phép trên server.
- Ghi log, gửi thông báo hoặc đưa yêu cầu triển khai vào hàng đợi sau khi nhận push.
- Đồng bộ quy trình kiểm tra với chính sách của nhóm.

Hook phù hợp với công việc có điểm kích hoạt rõ ràng và kết quả có thể tự động xác định. Với kiểm tra lâu, phụ thuộc nhiều dịch vụ hoặc cần tài nguyên lớn, nên cân nhắc CI thay vì khiến thao tác commit hoặc push mất quá nhiều thời gian.

## 2. Vòng đời hook phía máy người dùng và máy chủ

Một thay đổi điển hình có thể trải qua các bước:

~~~text
Máy người phát triển                         Máy chủ Git

Sửa file
   |
   v
git add
   |
   v
pre-commit
   |
   v
commit-msg
   |
   v
Tạo commit
   |
   v
pre-push
   |
   +---------------------------------------> pre-receive
                                               |
                                               v
                                           update (từng ref)
                                               |
                                               v
                                         Cập nhật refs
                                               |
                                               v
                                           post-receive
                                               |
                                               v
                                      Thông báo / hàng đợi CI-CD
~~~

Sơ đồ là luồng khái quát. Tùy thao tác, Git có thể gọi các hook khác nhau; không phải mọi thao tác đều đi qua tất cả các hook trong sơ đồ.

Client hook có thể phát hiện vấn đề ngay trước khi thay đổi được chia sẻ. Server hook kiểm tra lại ở nơi nhận push. CI thường tiếp tục kiểm tra sau khi thay đổi đã được nhận hoặc sau khi pull request được tạo.

## 3. Client-side hooks

Client-side hooks chạy trong repository local của người dùng. Chúng thường được dùng để cải thiện chất lượng thay đổi trước khi commit hoặc push.

### 3.1. Hook liên quan đến commit

| Hook | Thời điểm chạy | Mục đích |
|---|---|---|
| pre-commit | Trước khi tạo commit | Kiểm tra nội dung đã stage, chạy lint hoặc test nhanh |
| prepare-commit-msg | Sau khi Git tạo nội dung ban đầu cho message, trước khi mở editor | Tự chuẩn bị hoặc chỉnh nội dung message |
| commit-msg | Sau khi người dùng nhập message, trước khi tạo commit | Kiểm tra hoặc từ chối message |
| pre-merge-commit | Sau khi merge thành công, trước khi tạo merge commit | Kiểm tra trước khi hoàn tất merge commit |
| post-commit | Sau khi commit được tạo | Thông báo hoặc ghi nhận sự kiện |

pre-commit và commit-msg có thể từ chối commit bằng cách trả mã thoát khác 0. post-commit chạy sau khi commit đã được tạo nên không thể dùng để hủy commit đó.

prepare-commit-msg nhận đường dẫn file message và một số thông tin về nguồn tạo message. Hook này có thể sửa nội dung file. Nó không bị bỏ qua bởi tùy chọn git commit --no-verify; điều này khác với pre-commit và commit-msg.

### 3.2. Hook liên quan đến apply patch và email

Git có các hook phục vụ quy trình gửi patch qua email hoặc áp dụng patch:

- applypatch-msg: kiểm tra thông điệp khi áp dụng patch bằng git am.
- pre-applypatch: chạy trước khi patch được áp dụng thành commit.
- post-applypatch: chạy sau khi patch đã được áp dụng.
- sendemail-validate: xác thực nội dung trước khi gửi patch bằng git send-email.

Các hook này hữu ích trong dự án sử dụng quy trình patch-based. Với nhóm làm việc qua pull request, chúng có thể ít được dùng hơn.

### 3.3. Hook liên quan đến branch và đồng bộ

| Hook | Thời điểm chạy | Mục đích |
|---|---|---|
| pre-rebase | Trước khi bắt đầu rebase | Ngăn rebase nếu branch hoặc trạng thái không đáp ứng chính sách |
| post-checkout | Sau khi checkout branch hoặc commit | Cập nhật môi trường local, nhắc cài dependency |
| post-merge | Sau khi merge hoàn tất | Cập nhật file sinh tự động hoặc nhắc đồng bộ môi trường |
| pre-push | Trước khi gửi ref lên remote | Chạy test hoặc kiểm tra trước khi chia sẻ |
| post-rewrite | Sau các thao tác viết lại lịch sử như amend hoặc rebase | Ghi nhận ánh xạ commit cũ và mới |

Một số hook có thể chạy trong nhiều tình huống khác nhau. Ví dụ, post-checkout nhận mã commit trước, mã commit mới và một cờ cho biết thao tác có phải checkout branch hay không.

pre-push nhận tên remote và địa chỉ remote qua tham số, đồng thời nhận danh sách ref được đẩy qua standard input. Hook có thể từ chối push bằng mã thoát khác 0.

## 4. Server-side hooks

Server-side hooks chạy trên máy chủ Git. Với repository Git tự quản lý, hook thường nằm trong thư mục hooks của repository bare hoặc repository nhận push. Chúng được gọi bởi tiến trình xử lý nhận dữ liệu Git, thường là receive-pack.

Các hook phía server quan trọng:

| Hook | Thời điểm chạy | Phạm vi |
|---|---|---|
| pre-receive | Một lần cho toàn bộ lần push, trước khi cập nhật ref | Có thể từ chối toàn bộ lần push |
| update | Một lần cho mỗi ref được cập nhật | Có thể từ chối riêng từng ref |
| post-receive | Sau khi các ref được cập nhật thành công | Thông báo hoặc kích hoạt quy trình tiếp theo |
| post-update | Sau khi cập nhật ref thành công | Nhận danh sách tên ref đã cập nhật |
| push-to-checkout | Khi push cập nhật branch đang được checkout trong repository có working tree và bật receive.denyCurrentBranch=updateInstead | Điều phối checkout working tree phía nhận |

Repository bare thường là lựa chọn phù hợp cho server nhận push vì nó không có working tree đang được sử dụng như một bản làm việc thông thường.

### 4.1. pre-receive: kiểm tra toàn bộ lần push

pre-receive chạy một lần khi server nhận push. Git truyền qua standard input một dòng cho mỗi ref update:

~~~text
<old-object-id> <new-object-id> <ref-name>
~~~

Trong đó:

- old-object-id: object hiện tại của ref trên server.
- new-object-id: object mà người push muốn cập nhật tới.
- ref-name: tên đầy đủ của ref, ví dụ refs/heads/main hoặc refs/tags/v1.2.0.

Với ref mới, giá trị cũ là object ID toàn số 0. Với thao tác xóa ref, giá trị mới là object ID toàn số 0.

Nếu pre-receive trả mã thoát khác 0, toàn bộ lần push bị từ chối. Đây là nơi phù hợp để kiểm tra một chính sách cần áp dụng đồng nhất cho tất cả ref trong cùng lần push.

Ví dụ skeleton chỉ cho phép cập nhật các branch có tên bắt đầu bằng feature/ trong một repository thử nghiệm:

~~~sh
#!/bin/sh

while read old_oid new_oid ref_name
do
    case "$ref_name" in
        refs/heads/feature/*)
            ;;
        *)
            echo "Chỉ cho phép cập nhật branch feature/* trong repository thử nghiệm." >&2
            exit 1
            ;;
    esac
done

exit 0
~~~

Đây chỉ là minh họa cho cách đọc danh sách ref và từ chối lần push. Chính sách thực tế phải phù hợp với cách nhóm tích hợp thay đổi. Nếu nền tảng tạo merge commit bằng một cơ chế riêng, hãy kiểm tra cách nền tảng tương tác với hook trước khi áp dụng quy tắc.

### 4.2. update: kiểm tra từng ref

Hook update được gọi riêng cho từng ref. Nó nhận ba tham số:

~~~text
<ref-name> <old-object-id> <new-object-id>
~~~

Ví dụ skeleton từ chối cập nhật một branch được bảo vệ:

~~~sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

if [ "$ref_name" = "refs/heads/main" ]; then
    echo "Branch main cần được cập nhật qua quy trình review." >&2
    exit 1
fi

exit 0
~~~

Nếu update trả mã khác 0, ref tương ứng bị từ chối. Những ref khác trong cùng lần push vẫn có thể được cập nhật nếu các kiểm tra còn lại thành công. Đây là khác biệt quan trọng so với pre-receive, vốn có thể từ chối toàn bộ lần push.

### 4.3. post-receive: xử lý sau khi ref đã cập nhật

post-receive chạy sau khi server cập nhật các ref thành công. Nó nhận danh sách old object, new object và ref name qua standard input tương tự pre-receive.

Hook này phù hợp để:

- Gửi thông báo về commit mới.
- Ghi nhận sự kiện phát hành.
- Đưa công việc build hoặc deploy vào hàng đợi.
- Cập nhật hệ thống theo dõi thay đổi.

post-receive không thể từ chối lần push vì các ref đã được cập nhật. Nếu công việc tiếp theo thất bại, cần báo lỗi hoặc tạo tác vụ xử lý riêng; không thể dùng mã thoát của hook để hoàn tác push đã thành công.

Không nên chạy một quy trình deploy kéo dài trực tiếp trong post-receive nếu điều đó làm tiến trình nhận push bị giữ quá lâu. Tốt hơn là ghi sự kiện vào hàng đợi hoặc gọi một dịch vụ điều phối có timeout và cơ chế retry rõ ràng.

## 5. Cài đặt client hook trong repository local

### 5.1. Tìm thư mục hooks mặc định

Trong repository, chạy:

~~~sh
git rev-parse --git-path hooks
~~~

Lệnh trả về đường dẫn thư mục hooks bên trong Git directory. Thông thường, các hook mẫu nằm trong thư mục này với hậu tố .sample. Nếu đã cấu hình core.hooksPath, Git dùng thư mục được cấu hình thay cho thư mục mặc định; hãy kiểm tra giá trị đó khi chẩn đoán.

Ví dụ:

~~~text
pre-commit.sample
commit-msg.sample
pre-push.sample
~~~

Git không tự chạy file có hậu tố .sample. Muốn cài hook, tạo hoặc đổi tên thành đúng tên hook, ví dụ pre-commit, rồi bảo đảm file có quyền thực thi trên hệ điều hành hỗ trợ permission đó.

### 5.2. Tạo hook đầu tiên

Tạo file pre-commit trong thư mục hooks:

~~~sh
#!/bin/sh
set -eu

echo "Kiểm tra whitespace trong phần đã stage..."
git diff --cached --check
~~~

Hook này kiểm tra phần nội dung đã stage trước khi commit. Nếu git diff --cached --check phát hiện lỗi whitespace, lệnh trả mã khác 0 và commit bị dừng.

Trên Linux hoặc macOS, cấp quyền thực thi:

~~~sh
chmod +x .git/hooks/pre-commit
~~~

Đường dẫn .git/hooks trong ví dụ là vị trí mặc định của repository thông thường. Nếu Git dùng core.hooksPath hoặc git directory khác, hãy dùng đường dẫn từ git rev-parse --git-path hooks.

### 5.3. Kiểm tra hook có chạy không

Tạo một thay đổi thử nghiệm, stage rồi commit:

~~~sh
git add README.md
git commit -m "docs: update readme"
~~~

Quan sát thông báo của hook. Nếu hook trả mã khác 0, Git sẽ không tạo commit. Nếu không thấy hook chạy, kiểm tra:

- Tên file phải đúng tên hook, không có .sample.
- File có quyền thực thi.
- Hook nằm trong thư mục mà Git đang dùng.
- Shebang trỏ tới interpreter tồn tại.
- Cấu hình core.hooksPath có đang trỏ sang thư mục khác hay không.

## 6. Dùng core.hooksPath để quản lý hook trong repository

Mặc định, hook nằm trong Git directory nội bộ và không được commit như mã nguồn thông thường. Để lưu script hook trong repository, nhóm có thể đặt chúng trong một thư mục được theo dõi, ví dụ .githooks.

Cấu trúc:

~~~text
store-app/
├── .githooks/
│   ├── pre-commit
│   ├── commit-msg
│   └── pre-push
├── .gitignore
└── src/
~~~

Một số hook, đặc biệt hook liên quan đến push, có thể chạy từ Git directory thay vì working tree. Để cùng một thư mục hook được tìm thấy trong mọi ngữ cảnh, nên cấu hình đường dẫn tuyệt đối:

~~~sh
repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
~~~

Lệnh này lưu đường dẫn tuyệt đối vào cấu hình local của repository hiện tại. Cấu hình .git/config không được chia sẻ qua clone, nên nhóm cần cung cấp bước setup rõ ràng.

Trên Windows, cách chạy script và quyền thực thi phụ thuộc Git for Windows, shell và cấu hình core.filemode. Hãy dùng interpreter có sẵn trong môi trường nhóm và thử hook trên các hệ điều hành được hỗ trợ.

### 6.1. Đánh dấu file hook có thể thực thi

Với repository dùng hệ thống file hỗ trợ executable bit:

~~~sh
chmod +x .githooks/pre-commit
git add .githooks/pre-commit
git ls-files --stage .githooks/pre-commit
~~~

Git thường ghi mode 100755 cho file executable và 100644 cho file thông thường. Kiểm tra mode giúp tránh tình huống hook được commit nhưng không chạy được trên máy Linux/macOS.

### 6.2. Cài đặt hook sau khi clone

Vì cấu hình local không được clone cùng repository, nhóm có thể cung cấp script setup:

~~~sh
#!/bin/sh
set -eu

repo_root=$(git rev-parse --show-toplevel)
git config --local core.hooksPath "$repo_root/.githooks"
echo "Đã cấu hình Git hooks cho repository này."
~~~

Người dùng chạy script sau khi đã kiểm tra nội dung và hiểu những hook sẽ được kích hoạt. Không nên tự động chạy mã hook từ repository không tin cậy mà không review, vì hook có thể thực thi lệnh với quyền của người dùng.

## 7. Ví dụ hook phía client

### 7.1. pre-commit kiểm tra nội dung đã stage

File .githooks/pre-commit:

~~~sh
#!/bin/sh
set -eu

git diff --cached --check
~~~

Hook này chỉ kiểm tra nội dung staged. Nếu file đã sửa nhưng chưa stage, nội dung đó không thuộc phạm vi kiểm tra của git diff --cached.

Nếu muốn chạy formatter hoặc linter cho đúng các file staged, cần xác định danh sách file và gọi công cụ phù hợp. Tránh chạy formatter trên toàn repository rồi vô tình sửa các file không thuộc commit hiện tại.

### 7.2. commit-msg kiểm tra quy ước message

File .githooks/commit-msg:

~~~sh
#!/bin/sh
set -eu

message_file=$1

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([[:alnum:]_.-]+\))?: .+' "$message_file"; then
    echo "Commit message phải theo dạng type(scope): subject." >&2
    echo "Ví dụ: feat(auth): add refresh token support" >&2
    exit 1
fi
~~~

Hook nhận đường dẫn file message qua tham số đầu tiên. Nếu nội dung không khớp quy ước, hook trả mã 1 và commit bị từ chối.

Regex trong ví dụ là một quy ước đơn giản. Nếu dự án có quy tắc phức tạp hơn, hãy dùng một validator thống nhất trong local hook và CI để tránh hai nơi diễn giải khác nhau.

### 7.3. pre-push chạy kiểm tra trước khi chia sẻ

File .githooks/pre-push:

~~~sh
#!/bin/sh
set -eu

echo "Chạy test trước khi push..."
npm test
~~~

Nếu npm test thất bại, push bị dừng. Ví dụ này phù hợp với repository Node.js; dự án dùng công cụ khác cần thay bằng lệnh test tương ứng.

pre-push có thể chạy một lần cho một thao tác push có nhiều ref. Nếu cần kiểm tra riêng từng ref, hook có thể đọc danh sách ref từ standard input. Tránh giả định hook chỉ chạy khi push một branch.

### 7.4. post-merge cập nhật môi trường local

Hook post-merge có thể nhắc người dùng cài dependency sau khi merge:

~~~sh
#!/bin/sh
echo "Nếu dependency thay đổi, hãy chạy lệnh cài đặt theo hướng dẫn dự án."
~~~

Hook này chỉ chạy sau khi merge hoàn tất. Nó không thể hủy merge nếu lệnh trong hook thất bại. Với thao tác cần bắt buộc, nên đặt kiểm tra ở bước khác có khả năng từ chối trước khi hoàn tất hoặc đưa vào CI.

## 8. Hook nào có thể từ chối thao tác?

Không phải mọi hook đều có cùng quyền kiểm soát. Cần phân biệt hook chạy trước và hook chạy sau sự kiện.

| Hook | Có thể ngăn thao tác chính? | Ghi chú |
|---|---|---|
| pre-commit | Có | Mã thoát khác 0 ngăn tạo commit |
| prepare-commit-msg | Có thể làm lệnh thất bại nếu hook lỗi | Dùng để chuẩn bị message; không bị --no-verify bỏ qua |
| commit-msg | Có | Mã thoát khác 0 ngăn tạo commit |
| pre-merge-commit | Có | Có thể ngăn tạo merge commit |
| post-commit | Không | Commit đã được tạo |
| pre-rebase | Có | Có thể từ chối bắt đầu rebase |
| pre-push | Có | Mã thoát khác 0 ngăn push từ client |
| pre-receive | Có | Có thể từ chối toàn bộ lần push ở server |
| update | Có | Có thể từ chối một ref cụ thể |
| post-receive | Không | Ref đã được cập nhật |
| post-update | Không | Chạy sau khi ref đã cập nhật |

Khi thiết kế quy trình, đặt kiểm tra có quyền từ chối ở đúng thời điểm. Không dùng hook hậu sự kiện để cố ngăn một thao tác đã hoàn tất.

## 9. Client hook và server hook khác nhau ra sao?

| Tiêu chí | Client-side hook | Server-side hook |
|---|---|---|
| Nơi chạy | Máy người phát triển | Máy chủ nhận hoặc quản lý repository |
| Ai quản lý? | Người dùng hoặc script setup của nhóm | Quản trị viên server hoặc nền tảng |
| Thời điểm | Trước/sau commit, checkout, rebase, push... | Trước/sau khi server nhận và cập nhật ref |
| Mục đích chính | Phản hồi sớm, hỗ trợ thao tác local | Áp dụng chính sách tập trung |
| Có thể bị người dùng bỏ qua? | Một số hook có thể bị bỏ qua hoặc bị tắt | Không thể bỏ qua bằng tùy chọn --no-verify của client |
| Có được clone tự động? | Không, thư mục hooks và cấu hình local không được chia sẻ mặc định | Không, được cài trên server |
| Ví dụ | lint trước commit, test trước push | bảo vệ branch, kiểm tra ref, ghi nhận push |

Client hook có thể giúp người dùng tránh gửi thay đổi lỗi, nhưng không nên là lớp kiểm soát duy nhất cho chính sách quan trọng. Người dùng có thể không cài hook hoặc bỏ qua một số hook. Server hook hoặc branch protection mới là nơi thực thi chính sách tập trung.

## 10. Có thể bỏ qua hook không?

Một số lệnh Git hỗ trợ tùy chọn bỏ qua hook phía client:

~~~sh
git commit --no-verify
git push --no-verify
~~~

git commit --no-verify bỏ qua các hook pre-commit và commit-msg. Nó không bỏ qua prepare-commit-msg.

git push --no-verify bỏ qua hook pre-push phía client. Các hook phía server vẫn chạy khi server nhận push.

Ngoài ra, người dùng có thể cấu hình core.hooksPath trỏ tới một thư mục khác hoặc không có hook. Vì vậy:

- Dùng client hook cho phản hồi nhanh và tiện ích.
- Dùng CI để kiểm tra thay đổi trong môi trường được kiểm soát.
- Dùng server hook hoặc chính sách bảo vệ branch để thực thi quy tắc bắt buộc.

Không nên lạm dụng --no-verify. Nếu cần bỏ qua hook do lỗi môi trường hoặc trường hợp khẩn cấp, hãy ghi rõ lý do và thực hiện các kiểm tra thay thế theo quy trình nhóm.

## 11. Hook không tự được chia sẻ qua clone hoặc push

Thư mục hooks mặc định nằm trong Git directory, thường là .git/hooks. Thư mục .git không phải nội dung được commit như mã nguồn thông thường. Khi người khác clone repository, các hook mẫu có thể xuất hiện nhưng không tự được cài đặt để chạy.

Điều này có nghĩa:

- Commit một file .githooks/pre-commit không tự làm hook chạy trên máy đồng đội.
- Push repository không tự cài server hook trên remote.
- Cấu hình core.hooksPath local không tự đi theo clone.
- Mỗi người cần thực hiện bước setup hoặc dùng công cụ quản lý hook đã thống nhất.

Một số dự án dùng framework như pre-commit, Husky hoặc Lefthook để quản lý cài đặt và chạy hook. Các công cụ này là lớp tiện ích bên trên cơ chế Git hooks; nhóm vẫn cần hiểu hook được cài ở đâu và kiểm tra nào đang thực sự chạy.

Với server do tổ chức quản lý, hook cần được cài và bảo trì trên server. Nếu dùng dịch vụ Git hosting, khả năng cài custom server hook phụ thuộc gói dịch vụ và quyền quản trị. Có thể cần dùng branch protection, required status checks hoặc quy tắc merge của nền tảng thay thế.

## 12. Thiết kế hook đáng tin cậy

Một hook tốt cần nhanh, rõ ràng và có kết quả ổn định.

### 12.1. Giữ hook ngắn và tập trung

Mỗi hook nên có một mục tiêu chính. Ví dụ:

- pre-commit: kiểm tra whitespace và lint nhanh.
- commit-msg: xác thực cấu trúc message.
- pre-push: chạy test phù hợp trước khi chia sẻ.
- pre-receive: kiểm tra chính sách ref ở server.
- post-receive: đưa sự kiện vào hàng đợi.

Nếu một hook thực hiện quá nhiều công việc, khó biết bước nào làm commit hoặc push thất bại. Có thể tách script thành các chương trình nhỏ và gọi chúng từ hook.

### 12.2. Thông báo lỗi phải chỉ ra cách sửa

Thông báo như "hook failed" không giúp người dùng giải quyết vấn đề. Nên cho biết:

- Kiểm tra nào thất bại.
- File hoặc commit liên quan.
- Lệnh để chạy lại kiểm tra.
- Cách sửa hoặc tài liệu cần đọc.

Ví dụ:

~~~sh
echo "Commit message không đúng quy ước." >&2
echo "Dùng: feat(scope): mô tả thay đổi" >&2
exit 1
~~~

### 12.3. Tránh phụ thuộc môi trường không ổn định

Hook có thể chạy trên nhiều hệ điều hành và shell. Tránh giả định:

- Một đường dẫn tuyệt đối chỉ tồn tại trên máy tác giả.
- Một runtime hoặc phiên bản package manager đã có sẵn.
- Mạng luôn hoạt động.
- Dịch vụ bên ngoài luôn phản hồi nhanh.
- Mọi người dùng cùng shell.

Nếu cần dependency, hãy kiểm tra rõ và thông báo cách cài. Dùng timeout cho tác vụ có nguy cơ chờ vô hạn. Với kiểm tra nặng hoặc cần dịch vụ, CI thường phù hợp hơn.

### 12.4. Giữ nguyên trạng thái staging

pre-commit nên kiểm tra đúng phần nội dung đã stage. Nếu hook tự format file trong working tree, nó có thể làm cho nội dung working tree khác với nội dung trong index. Khi đó commit được tạo có thể không chứa kết quả mà người dùng vừa nhìn thấy.

Nếu hook sửa file, cần có quy trình stage lại hoặc dùng công cụ chỉ xử lý nội dung staged. Luôn giải thích rõ hook có tự thay đổi file hay chỉ kiểm tra.

### 12.5. Bảo vệ dữ liệu và quyền thực thi

Hook là chương trình thực thi với quyền của tài khoản đang chạy Git. Một hook độc hại có thể đọc file, gọi mạng hoặc chạy lệnh hệ thống trong phạm vi quyền đó.

Do vậy:

- Review hook như review mã nguồn thông thường.
- Không chạy hook từ repository không tin cậy mà chưa kiểm tra.
- Không ghi token hoặc mật khẩu vào script hook.
- Không in bí mật ra terminal hoặc log.
- Giới hạn quyền của tài khoản server chạy hook.
- Kiểm tra đầu vào từ tên ref, commit message và dữ liệu standard input trước khi sử dụng trong shell.
- Tránh ghép chuỗi đầu vào trực tiếp vào lệnh shell mà không xử lý đúng.

## 13. Tổ chức kiểm tra giữa hook, CI và chính sách server

Không nên đưa toàn bộ kiểm tra vào một hook duy nhất. Mỗi lớp có vai trò riêng:

| Lớp | Kiểm tra phù hợp | Lợi ích |
|---|---|---|
| pre-commit | whitespace, format nhanh, lint phần staged | Phản hồi ngay trên máy người dùng |
| commit-msg | cấu trúc message, mã ticket | Giữ lịch sử commit nhất quán |
| pre-push | unit test nhanh, kiểm tra branch local | Phát hiện lỗi trước khi gửi |
| CI | build sạch, test đầy đủ, security scan | Môi trường nhất quán, có log và kết quả tập trung |
| Server hook / branch protection | quyền cập nhật ref, required review, required checks | Áp dụng chính sách cho mọi contributor |
| post-receive | thông báo, đưa build/deploy vào hàng đợi | Kích hoạt quy trình sau khi nhận thay đổi |

Ví dụ, nhóm có thể chạy lint nhanh ở pre-commit, chạy unit test chọn lọc ở pre-push, chạy toàn bộ test và security scan trong CI, rồi yêu cầu CI thành công và có review trước khi merge vào main.

Kiểm tra nên có một nguồn định nghĩa đáng tin cậy. Nếu local hook và CI dùng hai bộ quy tắc khác nhau, người phát triển có thể thấy hook pass nhưng CI fail. Hãy chia sẻ script kiểm tra dùng chung khi phù hợp.

## 14. Ví dụ luồng triển khai chính sách

Giả sử nhóm muốn:

- Kiểm tra whitespace trước commit.
- Bắt buộc commit message theo quy ước.
- Chạy test trước push.
- Ngăn push trực tiếp vào branch main trên server.
- Kích hoạt CI sau khi server nhận branch.

Một cách tổ chức:

1. Lưu các script pre-commit, commit-msg và pre-push trong .githooks.
2. Cung cấp script setup để cấu hình core.hooksPath.
3. Cài pre-receive hoặc cấu hình branch protection trên server để bảo vệ main.
4. Cấu hình CI chạy khi branch được push hoặc pull request được cập nhật.
5. Dùng post-receive để gửi sự kiện vào hàng đợi hoặc thông báo cho hệ thống CI nếu kiến trúc yêu cầu.
6. Yêu cầu review và CI thành công trước khi merge.

Luồng này cho phản hồi sớm ở máy người dùng và có kiểm tra tập trung ở nơi lưu trữ. Nếu người dùng bỏ qua client hook, server và CI vẫn áp dụng các điều kiện bắt buộc.

## 15. Checklist triển khai Git hooks

**Chọn vị trí và loại hook**

- [ ] Xác định sự kiện cần kiểm tra hoặc tự động hóa.
- [ ] Chọn client hook hay server hook theo nơi cần thực thi.
- [ ] Phân biệt hook có thể từ chối thao tác và hook chạy sau sự kiện.
- [ ] Đưa chính sách bắt buộc lên server hoặc nền tảng quản lý repository.

**Cài đặt**

- [ ] Kiểm tra thư mục hook bằng git rev-parse --git-path hooks.
- [ ] Đặt tên file đúng với tên hook, bỏ hậu tố .sample.
- [ ] Bảo đảm interpreter và quyền thực thi phù hợp.
- [ ] Nếu dùng .githooks, cấu hình core.hooksPath và cung cấp bước setup.
- [ ] Thử trên các hệ điều hành và shell mà nhóm hỗ trợ.

**Vận hành**

- [ ] Hook chạy đủ nhanh và có timeout khi cần.
- [ ] Thông báo lỗi chỉ rõ nguyên nhân và cách sửa.
- [ ] Không làm thay đổi nội dung staged ngoài dự kiến.
- [ ] Không ghi hoặc làm lộ bí mật.
- [ ] Có log và cách xử lý lỗi cho server hook.
- [ ] CI kiểm tra lại các điều kiện quan trọng.

**Bảo trì**

- [ ] Review thay đổi hook như mã nguồn.
- [ ] Kiểm tra tương thích khi nâng phiên bản Git hoặc runtime.
- [ ] Loại bỏ hook không còn được dùng.
- [ ] Tài liệu hóa cách cài đặt, kiểm tra và bỏ qua trong trường hợp được phép.

## 16. Kết luận

Client-side hooks và server-side hooks cùng giúp tự động hóa quy trình Git nhưng phục vụ hai vai trò khác nhau. Hook phía client chạy gần người phát triển, giúp phát hiện lỗi sớm trước commit hoặc push. Hook phía server chạy ở nơi nhận thay đổi, giúp thực thi chính sách tập trung và xử lý sự kiện sau khi ref được cập nhật.

Hãy dùng client hook cho phản hồi nhanh, CI cho kiểm tra nhất quán và server hook hoặc branch protection cho quy tắc bắt buộc. Quản lý hook như mã thực thi cần review, cài đặt rõ ràng và thông báo dễ hiểu. Cách phân chia này giúp tự động hóa hữu ích mà vẫn giữ được khả năng kiểm soát và truy vết của quy trình cộng tác.
