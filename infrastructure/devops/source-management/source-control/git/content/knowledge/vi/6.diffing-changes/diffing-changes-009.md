# Kiểm tra khoảng trắng lỗi bằng git diff --check

Khoảng trắng thừa thường không làm chương trình chạy sai ngay lập tức, nhưng chúng tạo nhiễu trong diff, khiến review khó hơn và có thể vi phạm quy ước của dự án. Những lỗi thường gặp gồm dấu cách hoặc tab ở cuối dòng, dòng trống thừa ở cuối file và dấu cách đặt trước tab trong phần thụt lề.

Git cung cấp **git diff --check** để phát hiện các lỗi whitespace được cấu hình trong phần thay đổi. Lệnh này hữu ích trước khi commit, trước khi tạo patch và trong CI. Nó giúp tìm lỗi sớm mà không cần đọc từng dòng diff bằng mắt.

## 1. Phạm vi kiểm tra

Không có đối số, **git diff --check** so sánh working tree với index, tức chủ yếu kiểm tra thay đổi chưa stage:

~~~sh
git diff --check
~~~

Để kiểm tra nội dung đã stage so với HEAD:

~~~sh
git diff --cached --check
~~~

Để kiểm tra trạng thái cuối cùng của file tracked so với commit hiện tại, gồm cả phần staged và phần sửa thêm sau khi stage:

~~~sh
git diff HEAD --check
~~~

Ba lệnh này có phạm vi khác nhau. Chỉ chạy lệnh mặc định có thể bỏ sót lỗi đã nằm trong staging area.

Lệnh không quét mọi file trong thư mục. File không thay đổi, file untracked và file ignored không nằm trong diff thông thường. Nội dung đã commit cần được kiểm tra bằng revision cụ thể.

## 2. Những lỗi thường gặp

| Loại lỗi | Ví dụ minh họa | Ý nghĩa |
|---|---|---|
| Trailing whitespace | **const n = 1;··** | Dấu cách hoặc tab ở cuối dòng |
| Tab cuối dòng | **return result;→** | Tab xuất hiện sau nội dung |
| Blank at EOF | Nhiều dòng trống sau nội dung cuối | Dòng trống thừa ở cuối file |
| Space before tab | **··→target:** | Dấu cách đứng trước tab trong phần thụt lề |
| Conflict marker | **<<<<<<< HEAD** | Dấu đánh dấu conflict còn sót trong phần thêm mới |

Trong bảng, dấu chấm biểu thị dấu cách và mũi tên biểu thị tab; đó là ký hiệu giải thích, không phải ký tự cần nhập vào file.

Ví dụ output:

~~~text
src/config.yml:27: trailing whitespace.
+  timeout: 30··
Makefile:8: space before tab in indent.
+ 	$(CC) $(FLAGS) -o app main.c
~~~

Thông báo cho biết file, số dòng và loại lỗi. Dấu cộng thể hiện dòng mới trong diff. Hãy mở đúng dòng trong editor, bật hiển thị whitespace nếu cần, sửa ký tự thừa rồi chạy lại lệnh.

### 2.1. Trailing whitespace

Trailing whitespace là dấu cách hoặc tab xuất hiện sau ký tự nội dung cuối cùng trên dòng. Lỗi này thường phát sinh khi nhấn Space sau dấu chấm phẩy, copy nội dung từ tài liệu hoặc editor giữ khoảng trắng cuối dòng.

~~~text
// Không nên: có dấu cách ở cuối dòng
const enabled = true;··

// Nên
const enabled = true;
~~~

Editor có thể tự xóa trailing whitespace khi lưu. Sau khi bật tùy chọn, hãy xem diff vì thao tác lưu có thể sửa nhiều dòng cũ ngoài dự kiến.

### 2.2. Blank line ở cuối file

Quy tắc blank-at-eof nhận diện dòng trống thừa ở cuối file. Không nhầm nó với newline kết thúc file: file văn bản thông thường nên có một newline cuối cùng; bản thân newline đó không phải lỗi blank-at-eof.

### 2.3. Space trước tab trong indent

Một số định dạng, đặc biệt Makefile, dùng tab để bắt đầu recipe. Dấu cách xuất hiện trước tab có thể làm thụt lề sai hoặc không nhất quán.

~~~text
··→$(CC) -o app main.c
~~~

Nếu dự án yêu cầu recipe bắt đầu bằng tab, xóa dấu cách đứng trước tab.

### 2.4. Conflict marker

Khi giải quyết merge hoặc rebase conflict, có thể vô tình để lại:

~~~text
<<<<<<< HEAD
current implementation
=======
incoming implementation
>>>>>>> feature/new-flow
~~~

**git diff --check** có thể cảnh báo conflict marker được thêm trong diff. Tuy nhiên, hãy kiểm tra thêm git status và đọc lại logic sau khi merge; lệnh này không thay thế việc review conflict.

## 3. Kiểm tra staged và unstaged

Khi đang sửa file, chạy:

~~~sh
git status --short
git diff --check
~~~

Trước khi commit, chạy:

~~~sh
git diff --cached --check
git diff --cached
~~~

Nếu file đã stage rồi lại được sửa tiếp, status có thể hiển thị MM. Khi đó index giữ phiên bản đã stage, còn working tree có thêm phần sửa mới. Kiểm tra riêng hai phần:

~~~sh
git diff --check
git diff --cached --check
git diff HEAD --check
~~~

Nếu bạn sửa file nhưng không stage lại, index vẫn giữ nội dung cũ. Hãy stage lại file rồi kiểm tra staged diff lần nữa để chắc chắn commit sẽ chứa nội dung đã sửa.

## 4. Hiểu mã thoát và dùng trong script

Khi không phát hiện vấn đề, lệnh thường không in nội dung và trả mã thoát 0. Khi phát hiện whitespace error hoặc conflict marker trong diff, Git in chẩn đoán và trả mã khác 0.

~~~sh
git diff --check
result=$?
if [ "$result" -ne 0 ]; then
    echo "Whitespace check failed"
    exit "$result"
fi
~~~

Trong pipeline, nên để lệnh kiểm tra trả lỗi trực tiếp cho bước CI thay vì bỏ qua mã thoát. Không nối **|| true** vào lệnh này nếu mục tiêu là chặn commit có whitespace error.

## 5. Cấu hình core.whitespace

Git sử dụng core.whitespace để xác định loại khoảng trắng được xem là lỗi. Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| blank-at-eol | Dấu cách hoặc tab ở cuối dòng |
| blank-at-eof | Dòng trống thừa ở cuối file |
| space-before-tab | Dấu cách trước tab trong phần thụt lề |
| indent-with-non-tab | Thụt lề bằng dấu cách trong trường hợp quy tắc yêu cầu tab |
| tab-in-indent | Tab xuất hiện trong phần thụt lề |
| cr-at-eol | Xem CR ở cuối dòng là một phần của line ending |
| tabwidth=n | Độ rộng tab dùng khi kiểm tra một số quy tắc thụt lề |

Mặc định phổ biến bật blank-at-eol, blank-at-eof và space-before-tab. Các quy tắc khác có thể được bật theo tiêu chuẩn của dự án.

Xem cấu hình:

~~~sh
git config --show-origin --get core.whitespace
git config --local --get core.whitespace
git config --global --get core.whitespace
~~~

Nếu không có giá trị, Git dùng mặc định tích hợp. Có thể thử cấu hình tạm thời mà không lưu:

~~~sh
git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab diff --check
~~~

Nếu nhóm thống nhất cấu hình local:

~~~sh
git config --local core.whitespace blank-at-eol,blank-at-eof,space-before-tab
~~~

Cấu hình local nằm trong .git/config và không tự chia sẻ cho mọi thành viên. Nếu cần quy tắc chung, hãy ghi rõ trong tài liệu dự án hoặc thiết lập qua công cụ onboarding/CI. Không tắt quy tắc chỉ để một commit vượt qua kiểm tra.

## 6. Line ending CRLF và LF

Trên Windows, file có thể dùng CRLF; trên Linux và macOS thường dùng LF. Git có thể chuẩn hóa line ending qua .gitattributes và core.autocrlf.

~~~sh
git config --show-origin --get core.autocrlf
git check-attr text eol -- path/to/file
~~~

Ví dụ quy tắc của dự án:

~~~text
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
~~~

Sau khi thay đổi line ending, xem git diff để phát hiện chuyển đổi hàng loạt không mong muốn. Nếu Git báo CR ở cuối dòng, xác định file có chủ đích dùng CRLF hay không. cr-at-eol thay đổi cách Git diễn giải CR cuối dòng; không dùng nó để che một thay đổi line-ending ngoài ý muốn.

## 7. Chọn đúng revision để kiểm tra

| Mục tiêu | Lệnh |
|---|---|
| Thay đổi chưa stage | git diff --check |
| Thay đổi đã stage | git diff --cached --check |
| Tổng thay đổi tracked so với HEAD | git diff HEAD --check |
| Một file cụ thể | git diff --check -- path/to/file |
| Một commit so với cha | git diff --check HEAD^ HEAD |
| Nội dung của một commit | git show --check --format=oneline HEAD |
| Branch so với điểm phân kỳ | git diff --check main...feature/report |
| Hai revision cụ thể | git diff --check <base> <target> |

### 7.1. Kiểm tra commit vừa tạo

~~~sh
git show --check --format=oneline HEAD
git diff --check HEAD^ HEAD
~~~

Với merge commit có nhiều cha, chọn rõ parent cần so sánh, ví dụ HEAD^1. Đừng giả định parent đầu tiên luôn là mốc nghiệp vụ phù hợp.

### 7.2. Kiểm tra branch trước pull request

~~~sh
git fetch origin
git diff --check origin/main...HEAD
~~~

Ba dấu chấm trong git diff so sánh tip hiện tại với merge-base của hai revision. Đây thường là phạm vi phù hợp để kiểm tra phần thay đổi được đề xuất trong pull request. Thay origin/main bằng base branch thực tế và fetch trước nếu remote-tracking ref đã cũ.

### 7.3. Kiểm tra file untracked

File untracked không nằm trong diff thông thường. Nếu cần kiểm tra một file mới trước khi stage:

~~~sh
git add -N path/to/new-file
git diff --check -- path/to/new-file
~~~

git add -N tạo mục intent-to-add để Git hiển thị nội dung file trong diff, nhưng chưa stage toàn bộ nội dung như git add thông thường. Kiểm tra status sau thao tác và stage đúng cách khi đã sẵn sàng.

## 8. Tích hợp vào workflow

### 8.1. Trước khi commit

~~~sh
git status -sb
git diff --check
git diff --cached --check
git diff --cached
git commit -m "fix: normalize whitespace"
~~~

Chạy cả kiểm tra unstaged và staged để phát hiện lỗi ở hai lớp. Nếu chỉ commit nội dung đã stage, kiểm tra staged là bước quan trọng nhất.

### 8.2. Dùng pre-commit hook

Có thể đặt script trong .git/hooks/pre-commit:

~~~sh
#!/bin/sh

git diff --cached --check
status=$?

if [ "$status" -ne 0 ]; then
    echo "Commit bị chặn: hãy sửa whitespace error trong staged changes." >&2
    exit "$status"
fi

exit 0
~~~

Hook chạy trước khi tạo commit. Nếu kiểm tra thất bại, Git hủy commit để người dùng sửa nội dung. File hook cần có quyền thực thi trên hệ thống hỗ trợ. Hook trong .git/hooks thường không được commit và chia sẻ tự động; nhóm cần cài đặt hook qua công cụ quản lý hoặc kiểm tra lại trong CI.

### 8.3. Kiểm tra trong CI

Trong pipeline pull request, xác định base commit đáng tin cậy rồi chạy:

~~~sh
git diff --check "$BASE_SHA" HEAD
~~~

BASE_SHA cần là commit base đã được fetch và xác minh. Dùng biến được quote. Nếu base không tồn tại trong clone nông, pipeline cần fetch thêm lịch sử trước khi so sánh.

Khi lệnh trả mã khác 0, đánh dấu job thất bại và hiển thị đường dẫn/dòng lỗi để người phát triển sửa. Không biến lỗi thành cảnh báo không chặn nếu quy ước dự án yêu cầu diff sạch.

### 8.4. Không thay thế formatter hoặc linter

**git diff --check** chỉ kiểm tra một số lỗi whitespace trong phần diff. Nó không thay thế formatter như Prettier, Black hoặc gofmt; linter; kiểm tra độ dài dòng; kiểm tra encoding; hay unit test. Một file có thể vượt qua lệnh này nhưng vẫn sai định dạng hoặc sai logic.

## 9. Quy trình thực hành hoàn chỉnh

Giả sử bạn vừa sửa một file Java và chuẩn bị tạo commit.

**Bước 1 — xem trạng thái**

~~~sh
git status -sb
~~~

**Bước 2 — kiểm tra phần chưa stage**

~~~sh
git diff --check
git diff
~~~

Sửa lỗi được báo trong editor rồi chạy lại lệnh.

**Bước 3 — stage file**

~~~sh
git add src/report/ReportService.java
~~~

**Bước 4 — kiểm tra phần đã stage**

~~~sh
git diff --cached --check
git diff --cached
~~~

**Bước 5 — commit**

~~~sh
git commit -m "fix(report): clean whitespace in report service"
~~~

**Bước 6 — kiểm tra commit mới**

~~~sh
git show --check --format=oneline HEAD
git status -sb
~~~

Kết quả mong đợi: không có whitespace error trong phần thay đổi được kiểm tra, commit được tạo thành công và working tree không còn thay đổi ngoài dự kiến.

## 10. Lỗi thường gặp

**Lệnh không báo lỗi nhưng file vẫn có khoảng trắng thừa.**

- File có thể chưa nằm trong diff, đang untracked hoặc bị ignore.
- Chạy git status --short và kiểm tra đúng phạm vi.
- Với file untracked, cân nhắc git add -N để đưa nội dung vào diff.

**Chỉ chạy git diff --check và bỏ sót staged changes.**

- Chạy thêm git diff --cached --check.
- Hoặc dùng git diff HEAD --check để kiểm tra tổng thay đổi tracked so với HEAD.

**Git báo space before tab in indent.**

- Bật hiển thị tab và space trong editor.
- Xóa dấu cách trước tab ở đầu dòng.
- Kiểm tra quy tắc thụt lề của định dạng file, nhất là Makefile.

**Git báo trailing whitespace.**

- Xóa space hoặc tab ở cuối dòng.
- Bật tùy chọn trim trailing whitespace trong editor nếu phù hợp.
- Xem diff sau khi lưu để tránh sửa hàng loạt dòng không liên quan.

**CI thất bại nhưng máy local không thất bại.**

- Kiểm tra CI đang so sánh đúng base SHA hay không.
- So sánh phiên bản Git và cấu hình core.whitespace.
- Kiểm tra line ending và .gitattributes.
- Xác minh CI đang kiểm tra đúng revision.

**Muốn bỏ qua lỗi bằng cấu hình.**

- Xác định lý do quy tắc không phù hợp với file.
- Thống nhất thay đổi trong nhóm.
- Chỉ thay đổi cấu hình ở phạm vi hẹp.
- Không tắt toàn bộ whitespace check chỉ để một commit vượt qua.

## 11. Checklist kiểm tra whitespace

**Trước khi stage**

- [ ] Chạy git diff --check.
- [ ] Sửa trailing spaces và tab cuối dòng.
- [ ] Kiểm tra dòng trống thừa ở cuối file.
- [ ] Kiểm tra space trước tab trong phần thụt lề.
- [ ] Xem lại các dòng thay đổi sau khi sửa.

**Trước khi commit**

- [ ] Chạy git diff --cached --check.
- [ ] Xem git diff --cached để xác nhận nội dung sẽ commit.
- [ ] Nếu có sửa đổi sau khi stage, stage lại file.
- [ ] Chạy lại kiểm tra sau khi stage.

**Trước khi gửi patch hoặc pull request**

- [ ] Chọn đúng base và target revision.
- [ ] Chạy git diff --check <base> <target> hoặc cú pháp ba chấm phù hợp.
- [ ] Fetch base mới nhất nếu cần.
- [ ] Kiểm tra file untracked nếu chúng thuộc phạm vi bàn giao.
- [ ] Bảo đảm CI dùng cùng quy tắc whitespace với dự án.

## 12. Kết luận

**git diff --check** là bước kiểm tra nhanh để phát hiện whitespace error và conflict marker được đưa vào trong phần thay đổi. Hãy nhớ phạm vi mặc định chỉ so sánh working tree với index; dùng --cached để kiểm tra staged changes và chọn revision rõ ràng khi kiểm tra commit hoặc branch.

Lệnh không tự sửa file và không quét toàn bộ nội dung repository. Hãy sửa tại nguồn, stage lại nếu cần, chạy kiểm tra lần nữa rồi xem diff. Khi được tích hợp vào pre-commit và CI, nó giúp giữ diff gọn, dễ review và nhất quán giữa các thành viên.
