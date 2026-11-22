# Giới hạn chia sẻ hook và lý do kiểm tra cục bộ không thay thế chính sách máy chủ

Git hooks là các chương trình được Git gọi tại những thời điểm nhất định, chẳng hạn trước khi tạo commit, trước khi push hoặc sau khi nhận thay đổi. Nhóm có thể dùng hook để chạy formatter, kiểm tra lỗi cơ bản, xác minh thông điệp commit hoặc thực hiện tác vụ tự động. Tuy nhiên, hook được cài trong clone của từng người không tự động được chia sẻ khi push và clone repository.

Vì vậy, một hook local rất hữu ích để phản hồi sớm, nhưng không thể là nơi duy nhất đặt quy tắc bắt buộc của nhóm. Người dùng có thể chưa cài hook, dùng cấu hình khác hoặc bỏ qua một số hook. Các quy tắc cần được áp dụng nhất quán phải được kiểm tra ở máy chủ nhận push, trong CI và/hoặc bằng chính sách bảo vệ nhánh của nền tảng.

Bài này giải thích hook được lưu ở đâu, cách chia sẻ mã hook trong repository, cách cài đặt cho từng clone, các giới hạn có thể bỏ qua và cách chuyển những quy tắc quan trọng sang cơ chế kiểm soát tập trung.

Sau bài này, bạn có thể:

- Phân biệt hook local với hook phía máy chủ.
- Giải thích vì sao thư mục .git/hooks không được push lên remote.
- Chia sẻ script hook bằng thư mục được quản lý trong repository.
- Cấu hình core.hooksPath và kiểm tra hook đang được dùng.
- Nhận biết các cách bỏ qua hook và giới hạn của chúng.
- Chọn nơi thực thi phù hợp cho kiểm tra tiện ích và chính sách bắt buộc.
- Kết hợp hook, CI và bảo vệ nhánh để tạo quy trình đáng tin cậy.

## 1. Git hook hoạt động như thế nào?

Hook là chương trình hoặc script có tên tương ứng với một sự kiện Git. Git tìm hook trong thư mục hooks của repository hoặc đường dẫn được cấu hình bởi core.hooksPath. Khi sự kiện xảy ra, Git chạy hook tương ứng và truyền một số đối số hoặc dữ liệu qua standard input tùy loại hook.

Một số hook thường gặp:

| Hook | Thời điểm | Mục đích thường dùng |
| --- | --- | --- |
| pre-commit | Trước khi tạo commit | Chạy lint, formatter check hoặc kiểm tra nhanh. |
| prepare-commit-msg | Sau khi Git tạo nội dung nháp thông điệp commit | Chuẩn bị hoặc bổ sung thông điệp. |
| commit-msg | Sau khi người dùng nhập thông điệp, trước khi commit được tạo | Kiểm tra định dạng thông điệp commit. |
| post-commit | Sau khi commit thành công | Ghi log hoặc thông báo local. |
| pre-push | Trước khi Git bắt đầu gửi refs lên remote | Chạy kiểm tra trước khi push. |
| post-checkout | Sau khi checkout hoặc switch | Cập nhật môi trường local. |
| post-merge | Sau khi merge thành công | Cài đặt hoặc đồng bộ thành phần cần thiết. |
| pre-rebase | Trước khi rebase bắt đầu | Ngăn rebase trong những trường hợp không được phép ở local. |

Hook có thể làm Git dừng thao tác nếu hook đó hỗ trợ từ chối và script trả mã thoát khác 0. Các hook dạng thông báo sau sự kiện, như post-commit, không thể quay ngược một commit đã được tạo chỉ bằng cách trả mã lỗi.

Một hook thường là executable script. Trên hệ thống Unix, quyền thực thi phải được thiết lập. Trên Windows, Git for Windows thường chạy hook shell qua môi trường Git Bash; cần dùng shebang và cú pháp tương thích, hoặc gọi chương trình có sẵn trong môi trường của nhóm.

## 2. Vì sao .git/hooks không được chia sẻ qua remote?

Khi khởi tạo repository, Git thường tạo thư mục .git/hooks chứa các file ví dụ như pre-commit.sample hoặc commit-msg.sample. Các file có đuôi .sample chỉ là tài liệu minh họa; Git không tự chạy chúng như hook đang bật.

Hook thực tế thường được đặt trong .git/hooks và thư mục .git là dữ liệu quản trị local của clone. Nó không thuộc cây tệp được commit trong branch. Do đó:

- Push branch không gửi hook trong .git/hooks lên remote.
- Clone repository không tự nhận hook local của người đã push.
- Mỗi clone có thể có hook và cấu hình khác nhau.
- Cài đặt hook ở máy này không có nghĩa máy khác đã cài cùng hook.

Kiểm tra thư mục Git và hook path hiện tại:

~~~bash
git rev-parse --git-dir
git config --show-origin --get core.hooksPath
~~~

Nếu core.hooksPath chưa được cấu hình, Git dùng thư mục hooks mặc định bên trong Git directory. Nếu lệnh cấu hình không trả kết quả, điều đó thường có nghĩa chưa có giá trị core.hooksPath được thiết lập.

Không nên cố commit toàn bộ .git/hooks. Thay vào đó, lưu script hook trong một thư mục bình thường thuộc repository, rồi hướng dẫn mỗi clone cấu hình Git để sử dụng thư mục đó.

## 3. Chia sẻ mã hook trong repository

Một quy ước phổ biến là đặt các hook dùng chung trong .githooks/:

~~~text
product/
|-- .git/
|-- .githooks/
|   |-- pre-commit
|   |-- commit-msg
|   +-- pre-push
|-- scripts/
|   |-- lint.sh
|   +-- check-commit-message.sh
|-- src/
+-- README.md
~~~

Thư mục .githooks là thư mục bình thường nên có thể được Git theo dõi và chia sẻ. Script trong đó cần được review như mã nguồn khác: kiểm tra nội dung, quyền thực thi, dependency và hành vi khi thất bại.

Ví dụ hook pre-commit:

~~~sh
#!/bin/sh
set -eu

echo "Running local checks before commit..."
./scripts/lint.sh
~~~

Ví dụ hook commit-msg nhận đường dẫn file thông điệp commit làm đối số đầu tiên:

~~~sh
#!/bin/sh
set -eu

message_file="$1"

if ! grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([a-z0-9-]+\))?: .+' "$message_file"; then
    echo "Commit message must follow the team format."
    echo "Example: feat(search): add filtering"
    exit 1
fi
~~~

Đây là ví dụ minh họa một quy ước commit message. Nếu dự án dùng quy ước khác, hãy điều chỉnh regex và thông báo lỗi. Hook cần trả mã 0 khi hợp lệ và mã khác 0 khi muốn ngăn commit.

Không nên nhồi toàn bộ logic kiểm tra vào hook. Tách phần dùng chung thành script trong scripts/ để CI có thể gọi lại cùng lệnh. Như vậy local hook và CI kiểm tra cùng một quy tắc, tránh hai bản logic dần khác nhau.

## 4. Cấu hình core.hooksPath cho mỗi clone

Sau khi repository có thư mục .githooks, người dùng có thể cấu hình clone hiện tại:

~~~bash
git config --local core.hooksPath .githooks
~~~

--local lưu cấu hình vào .git/config của clone hiện tại. Giá trị này không được chia sẻ qua commit. Mỗi clone mới cần chạy bước cài đặt tương ứng.

Kiểm tra:

~~~bash
git config --show-origin --get core.hooksPath
git config --local --get core.hooksPath
~~~

Nếu muốn bỏ cấu hình riêng và quay lại đường dẫn hooks mặc định:

~~~bash
git config --local --unset core.hooksPath
~~~

Khi core.hooksPath được cấu hình, Git tìm hook trong đường dẫn đó thay cho thư mục mặc định. Vì thế, cần bảo đảm thư mục có đủ hook mà nhóm muốn bật. Một thư mục hooksPath trống hoặc sai đường dẫn có thể khiến các hook local trước đó không còn được chạy.

### Script cài đặt cho thành viên mới

Repository có thể cung cấp một script cài đặt đơn giản:

~~~sh
#!/bin/sh
set -eu

git config --local core.hooksPath .githooks
echo "Git hooks are configured for this clone."
~~~

Lưu script, ví dụ scripts/install-hooks.sh, rồi hướng dẫn thành viên chạy một lần sau khi clone:

~~~bash
sh scripts/install-hooks.sh
~~~

Script cài đặt chỉ thay đổi cấu hình local của repository đang đứng. Cần đọc và review script trước khi chạy vì nó thay đổi cách Git thực thi chương trình trên máy.

Một dự án cũng có thể dùng công cụ quản lý hook như pre-commit, Husky hoặc Lefthook. Những công cụ này giúp cài đặt và điều phối hook, nhưng không thay đổi nguyên tắc nền tảng: cấu hình và chương trình chạy trên máy thành viên vẫn cần được cài đặt, và kiểm tra local vẫn có thể bị bỏ qua.

## 5. Hook local có thể bị bỏ qua

Hook local là cơ chế hỗ trợ quy trình, không phải ranh giới bảo mật. Có nhiều lý do khiến nó không chạy hoặc không ngăn được thao tác:

- Thành viên chưa chạy script cài đặt hook.
- core.hooksPath trỏ tới một thư mục khác.
- File hook không tồn tại hoặc không có quyền thực thi.
- Môi trường local thiếu runtime hoặc dependency mà hook yêu cầu.
- Người dùng chủ động dùng tùy chọn bỏ qua hook được Git hỗ trợ.
- Người dùng thay đổi hoặc xóa hook trong clone của họ.

Một số tùy chọn bỏ qua cụ thể:

~~~bash
# Bỏ qua pre-commit và commit-msg cho lần commit này
git commit --no-verify -m "temporary commit"

# Bỏ qua pre-push cho lần push này
git push --no-verify origin feature/search
~~~

--no-verify không tắt mọi loại hook. Với git commit, tùy chọn này bỏ qua pre-commit và commit-msg; hook prepare-commit-msg không bị bỏ qua theo cách đó. Với git push, nó bỏ qua pre-push. Hành vi cụ thể phụ thuộc lệnh và loại hook; không nên suy rộng thành một công tắc vô hiệu hóa toàn bộ hook.

Ngoài ra, cấu hình local có thể được thay đổi, script có thể bị sửa, hoặc người dùng có thể chạy Git từ môi trường không có hook. Vì vậy, kết quả “hook local đã pass” chỉ chứng minh lần kiểm tra đó đã chạy thành công trong môi trường đó.

Không dùng hook local làm nơi duy nhất để kiểm tra điều kiện bắt buộc như cấm push trực tiếp vào nhánh chính, yêu cầu review hoặc ngăn secret đi vào lịch sử. Các điều kiện đó cần được thực thi ở nơi người dùng không thể tự sửa trong clone của họ.

## 6. Hook phía máy chủ thực thi ở đâu?

Git hỗ trợ server-side hooks trong repository nhận push. Chúng được cấu hình trên máy chủ hoặc môi trường quản lý repository, không nằm trong clone của từng contributor.

Một số hook quan trọng:

| Hook | Thời điểm | Khả năng |
| --- | --- | --- |
| pre-receive | Một lần trước khi cập nhật các refs nhận được trong push | Kiểm tra toàn bộ cập nhật; trả mã khác 0 sẽ từ chối push. |
| update | Cho từng ref sắp được cập nhật | Có thể chấp nhận hoặc từ chối riêng từng ref. |
| post-receive | Sau khi refs được cập nhật thành công | Gửi thông báo, kích hoạt triển khai hoặc ghi nhận sự kiện; không thể từ chối cập nhật đã hoàn tất. |

Hook pre-receive nhận danh sách cập nhật qua standard input. Mỗi dòng chứa mã object cũ, mã object mới và tên ref. Hook có thể dùng thông tin đó để kiểm tra chính sách, chẳng hạn cấm xóa branch release hoặc yêu cầu commit có chữ ký.

Hook update được gọi riêng cho từng ref và nhận tên ref cùng mã object cũ/mới qua đối số. Nó hữu ích khi quyết định có cho phép cập nhật một branch hoặc tag cụ thể hay không.

Hook post-receive chạy sau khi cập nhật refs. Nó phù hợp để thông báo, cập nhật hệ thống theo dõi hoặc kích hoạt pipeline. Nếu cần từ chối push, logic phải chạy trước khi refs được cập nhật, ví dụ trong pre-receive hoặc update.

Các server-side hooks này cần được cài đặt và quản trị bởi người có quyền trên máy chủ. Người dùng clone repository không thể thay đổi hook ở repository nhận push bằng cách sửa .githooks của họ.

## 7. Nền tảng Git hosting có thể cung cấp chính sách tập trung

Không phải nhóm nào cũng quản trị máy chủ Git trực tiếp. Trên GitHub, GitLab, Bitbucket hoặc dịch vụ tương tự, quản trị viên thường cấu hình chính sách ở cấp repository hoặc project:

- Protected branches hoặc branch rules.
- Yêu cầu pull request/merge request trước khi tích hợp.
- Yêu cầu số lượng approval tối thiểu.
- Required status checks từ CI.
- Hạn chế force push hoặc xóa branch.
- Yêu cầu commit ký số hoặc quy tắc kiểm tra phù hợp với nền tảng.

Tên tính năng và phạm vi cưỡng chế khác nhau giữa nhà cung cấp, gói dịch vụ và loại repository. Cần cấu hình theo tài liệu nền tảng đang dùng.

Ví dụ, nếu nhóm không cho phép cập nhật trực tiếp main, chính sách bảo vệ nhánh cần được bật trên nền tảng hoặc máy chủ. Một hook pre-push trong clone của contributor có thể nhắc họ không push vào main, nhưng người dùng có thể bỏ qua hook hoặc dùng clone không cài hook.

Required status checks cũng có ý nghĩa khác với việc một hook local chạy thành công. Nền tảng chỉ cho phép merge khi các job CI được chỉ định đã báo trạng thái đạt yêu cầu. Nếu cần bảo vệ cả push trực tiếp, hãy cấu hình thêm quyền push và quy tắc bảo vệ nhánh phù hợp; chỉ yêu cầu CI trên pull request có thể chưa bao phủ mọi đường cập nhật.

## 8. Phân chia kiểm tra local, CI và server policy

Chọn vị trí thực thi dựa trên mục tiêu và mức độ bắt buộc:

| Kiểm tra | Local hook | CI | Server/platform policy |
| --- | --- | --- | --- |
| Format file khi commit | Phù hợp để phản hồi nhanh | Có thể xác minh lại | Thường không cần chính sách riêng nếu CI đã bắt buộc |
| Lint và unit test | Có thể chạy tập nhỏ | Chạy đầy đủ, nhất quán | Bắt buộc status check nếu phải pass trước merge |
| Định dạng commit message | Có thể nhắc và kiểm tra sớm | Có thể kiểm tra lịch sử/PR | Server hook có thể từ chối commit/push theo chính sách |
| Không push trực tiếp vào main | Chỉ nhắc nhở | Không phải nơi duy nhất để chặn push | Protected branch hoặc server hook |
| Yêu cầu review | Không thể tự xác minh đầy đủ | Có thể kiểm tra trạng thái review qua API tùy hệ thống | Quy tắc pull/merge request của nền tảng |
| Ngăn cập nhật ref bị cấm | Không đáng tin cậy | Có thể phát hiện sau khi push | pre-receive, update hoặc quyền bảo vệ ref |

Một mô hình thường hiệu quả:

1. Local hook chạy kiểm tra nhanh để phát hiện lỗi ngay trước commit hoặc push.
2. CI chạy lại kiểm tra trong môi trường sạch, có phiên bản tool và dependency được kiểm soát.
3. Nền tảng yêu cầu các status check, review và quy tắc branch trước khi merge.
4. Máy chủ Git dùng receive hooks nếu nhóm quản trị server và cần từ chối push ở cấp ref.

Không nên chỉ chạy kiểm tra trong local hook rồi xem đó là bằng chứng chính sách đã được đáp ứng. CI và server policy phải tự thực thi các điều kiện cần thiết.

## 9. Ví dụ: chia sẻ hook kiểm tra commit nhưng vẫn xác minh trong CI

Giả sử nhóm thống nhất commit message phải có loại thay đổi như feat, fix hoặc docs. Repository chứa:

~~~text
.githooks/
+-- commit-msg
scripts/
+-- check-commit-message.sh
~~~

Script kiểm tra dùng chung:

~~~sh
#!/bin/sh
set -eu

message_file="$1"

grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([a-z0-9-]+\))?: .+' "$message_file"
~~~

Hook gọi script:

~~~sh
#!/bin/sh
set -eu

./scripts/check-commit-message.sh "$1" || {
    echo "Invalid commit message format."
    exit 1
}
~~~

Thành viên cài hook:

~~~bash
git config --local core.hooksPath .githooks
~~~

CI cũng gọi cùng script trên commit message hoặc các commit thuộc phạm vi pull request. Cách trích xuất danh sách commit và thông điệp cần kiểm tra phụ thuộc hệ thống CI, nhưng logic quy tắc chỉ nằm ở một script dùng chung.

Ngay cả khi contributor dùng git commit --no-verify, CI vẫn có thể phát hiện thông điệp không hợp lệ và status check bắt buộc sẽ ngăn merge. Nếu chính sách cần từ chối cả push vào repository trung tâm, có thể triển khai receive hook hoặc tính năng tương ứng của nền tảng.

## 10. Cài hook an toàn và bảo trì theo phiên bản

Vì hook có thể chạy lệnh trên máy người dùng, việc chia sẻ hook cũng là chia sẻ mã có khả năng thực thi. Nhóm nên:

- Review script như mã nguồn có thể thực thi, đặc biệt khi thay đổi lệnh shell.
- Dùng đường dẫn tương đối rõ ràng và tránh phụ thuộc vào thư mục làm việc bất ngờ.
- Kiểm tra dependency trước khi chạy; thông báo cách cài đặt nếu thiếu.
- Giữ thời gian chạy local hợp lý để không làm chậm mọi commit.
- Không in token, mật khẩu hoặc dữ liệu nhạy cảm ra log.
- Đảm bảo lỗi được truyền bằng mã thoát khác 0 khi cần ngăn thao tác.
- Ghi rõ cách cài, cập nhật và gỡ cấu hình hook trong tài liệu dự án.

Nếu repository đổi nội dung .githooks, các clone đã cấu hình core.hooksPath sẽ dùng file mới sau khi pull commit chứa thay đổi. Tuy nhiên, nếu thành viên chưa cấu hình hookPath, họ vẫn không tự động chạy các hook trong .githooks.

Script cài đặt có thể được cập nhật để kiểm tra cấu hình hiện tại:

~~~sh
#!/bin/sh
set -eu

git config --local core.hooksPath .githooks
echo "Configured hooksPath: $(git config --local --get core.hooksPath)"
~~~

Để gỡ cấu hình:

~~~bash
git config --local --unset core.hooksPath
~~~

Lệnh này không xóa thư mục .githooks trong working tree; nó chỉ bỏ cấu hình local để Git quay về hook path mặc định. Nếu nhóm dùng một công cụ quản lý hook, hãy làm theo cơ chế cài/gỡ của công cụ đó.

## 11. Những hiểu lầm thường gặp

### Commit thư mục .githooks là mọi người tự chạy hook

Không đúng. Commit chỉ chia sẻ script. Mỗi clone cần cấu hình core.hooksPath hoặc cài công cụ quản lý hook để Git gọi script đó.

### Push hook local lên remote sẽ cài hook cho máy chủ

Không đúng. .git/hooks là thư mục quản trị local và không được push. Server-side hooks phải được cài trên repository nhận push hoặc cấu hình qua nền tảng.

### --no-verify bỏ qua tất cả hook

Không đúng. Tùy chọn này chỉ bỏ qua các hook được tài liệu của lệnh chỉ định, chẳng hạn pre-commit, commit-msg với git commit và pre-push với git push.

### Hook local pass nghĩa là chính sách đã được đảm bảo

Không đúng. Hook có thể chưa được cài, bị thay đổi hoặc bị bỏ qua. Chính sách bắt buộc phải được kiểm tra lại trong CI hoặc thực thi ở server/platform.

### post-receive có thể từ chối push

Không đúng. Hook này chạy sau khi refs đã được cập nhật. Dùng pre-receive hoặc update nếu cần từ chối trước khi cập nhật.

### CI thay thế hoàn toàn protected branch

Không nhất thiết. CI tạo kết quả kiểm tra, còn nền tảng cần được cấu hình để yêu cầu kết quả đó trước khi merge. Quyền push trực tiếp và quyền force push cũng cần được kiểm soát riêng.

## 12. Ghi nhớ

- Hook local chạy trong clone của từng người; thư mục .git/hooks không được chia sẻ qua push/clone.
- Có thể chia sẻ script trong .githooks và cấu hình từng clone bằng git config --local core.hooksPath .githooks.
- core.hooksPath là cấu hình local, vì vậy clone mới cần bước cài đặt.
- --no-verify chỉ bỏ qua một số hook cụ thể; không phải công tắc tắt mọi hook.
- Client-side hooks phù hợp để phản hồi nhanh và hỗ trợ thói quen làm việc.
- Server-side hooks như pre-receive và update có thể từ chối cập nhật refs; post-receive phù hợp cho thông báo và tác vụ sau push.
- CI cần được cấu hình thành required status check nếu kết quả phải được đáp ứng trước khi merge.
- Protected branches và chính sách nền tảng thực thi review, quyền push, force push và các điều kiện tích hợp.
- Những quy tắc bắt buộc không được chỉ dựa vào hook local; hãy thực thi chúng ở nơi contributor không thể tự thay đổi.

Hook local giúp phát hiện lỗi sớm và giảm vòng phản hồi, còn CI và chính sách máy chủ tạo ra điểm kiểm tra nhất quán cho cả nhóm. Khi chia sẻ mã hook nhưng đặt điều kiện bắt buộc ở phía nhận push hoặc nền tảng, quy trình vừa thuận tiện cho người phát triển vừa có thể được kiểm soát tập trung.
