# Phân biệt áp dụng bản vá bằng git apply và git am

Khi cần chuyển thay đổi giữa hai repository hoặc hai máy không dùng chung một remote, Git có thể đóng gói phần thay đổi thành patch. Patch là dữ liệu mô tả những dòng được thêm, sửa hoặc xóa trong các file. Người nhận có thể dùng git apply để áp dụng nội dung thay đổi vào working tree hoặc index, hoặc dùng git am để áp dụng các bản vá dạng email và tạo commit tương ứng.

Hai lệnh có vẻ gần giống nhau nhưng phục vụ hai mục tiêu khác nhau. git apply tập trung vào việc áp dụng diff; nó không tự tạo commit. git am đọc thông điệp patch theo định dạng mail, áp dụng từng patch và tạo commit, đồng thời giữ thông tin tác giả và thông điệp được đóng gói trong patch. Chọn đúng lệnh giúp bạn giữ được lịch sử cần thiết và kiểm soát chính xác thay đổi sẽ đi vào repository.

Sau bài này, bạn có thể:

- Phân biệt patch diff thông thường với patch dạng email.
- Chọn git apply khi chỉ cần áp dụng nội dung thay đổi.
- Chọn git am khi muốn nhập một hoặc nhiều commit từ patch mail.
- Kiểm tra patch trước khi áp dụng.
- Hiểu tác động của các tùy chọn --index, --cached và --3way.
- Xử lý xung đột khi áp dụng patch hoặc khi chạy git am.
- Tạo patch bằng git diff và git format-patch.
- Chọn quy trình phù hợp khi chia sẻ thay đổi mà không push trực tiếp.

## 1. Patch là gì?

Patch là bản mô tả chênh lệch giữa hai trạng thái nội dung. Với file văn bản, patch thường chứa tên file, vùng ngữ cảnh và các dòng được thêm hoặc xóa. Git có thể tạo patch từ thay đổi trong working tree, từ staging area hoặc từ commit.

Ví dụ diff đơn giản:

~~~diff
diff --git a/src/Search.java b/src/Search.java
index 1234567..89abcde 100644
--- a/src/Search.java
+++ b/src/Search.java
@@ -10,7 +10,7 @@ public class Search {
-    return query;
+    return normalize(query);
 }
~~~

Các dòng bắt đầu bằng dấu trừ là nội dung cũ bị xóa; dòng bắt đầu bằng dấu cộng là nội dung mới được thêm. Các dòng ngữ cảnh giúp Git tìm đúng vị trí để áp dụng thay đổi.

Patch có thể được chuyển qua email, chat, file đính kèm hoặc một thư mục chia sẻ. Người nhận không nhất thiết phải có remote chung, nhưng cần có phiên bản mã nguồn phù hợp để patch áp dụng được.

## 2. Khác biệt cốt lõi giữa git apply và git am

| Tiêu chí | git apply | git am |
| --- | --- | --- |
| Đầu vào thường gặp | Diff/patch file | Patch dạng email hoặc mbox, thường do git format-patch tạo |
| Mục tiêu | Thay đổi working tree hoặc index | Áp dụng patch và tạo commit |
| Tạo commit | Không | Có, thường mỗi mail patch tạo một commit |
| Giữ tác giả và thông điệp commit | Không có metadata commit để giữ trong diff thông thường | Có thể giữ author, author date và thông điệp từ patch mail |
| Người tạo commit mới | Người dùng tự commit sau khi apply | Người chạy git am là committer |
| Xử lý một loạt thay đổi | Áp dụng diff, sau đó tự stage/commit | Xử lý chuỗi patch theo thứ tự |
| Khi có xung đột | Dừng lệnh; người dùng tự xử lý nội dung và commit | Tạm dừng chuỗi mail patch; giải quyết rồi continue, skip hoặc abort |

Hãy nhớ:

- git apply đưa thay đổi vào cây làm việc hoặc index, tùy tùy chọn.
- git am nhập một chuỗi thay đổi có thông tin commit và tạo commit mới trong repository hiện tại.

Một patch do git diff tạo ra thường chỉ mô tả nội dung. Một patch do git format-patch tạo ra còn đóng gói thông tin tác giả, thông điệp commit và các header mail cần thiết để git am tái tạo commit.

## 3. Dùng git diff để tạo patch cho git apply

Giả sử bạn đã sửa một file nhưng chưa stage. Tạo patch từ thay đổi trong working tree:

~~~bash
git diff > search-fix.patch
~~~

Patch này chứa thay đổi chưa stage. Nếu thay đổi đã nằm trong staging area, dùng:

~~~bash
git diff --cached > search-fix.patch
~~~

Nếu muốn tạo patch từ toàn bộ thay đổi tracked trong working tree và staging area so với HEAD, có thể dùng:

~~~bash
git diff HEAD > all-changes.patch
~~~

Patch văn bản mặc định không thể biểu diễn đầy đủ nội dung nhị phân. Khi cần bao gồm thay đổi binary, tạo patch với:

~~~bash
git diff --binary HEAD > all-changes.patch
~~~

Tùy chọn --binary thêm dữ liệu cần thiết để Git áp dụng thay đổi binary. Người nhận vẫn cần dùng Git apply để xử lý patch đó.

Patch từ git diff không tự mang theo author, commit message hoặc cấu trúc commit. Nó chỉ mô tả thay đổi nội dung so với trạng thái cơ sở.

## 4. Kiểm tra patch trước khi áp dụng

Trước khi thay đổi working tree, hãy xem patch:

~~~bash
git apply --stat search-fix.patch
git apply --summary search-fix.patch
git apply --check search-fix.patch
~~~

- --stat hiển thị thống kê file và số dòng thay đổi.
- --summary hiển thị thông tin tổng quan như tạo, xóa, đổi tên hoặc mode file nếu patch có dữ liệu đó.
- --check kiểm tra khả năng áp dụng patch mà không thực sự thay đổi file.

Kiểm tra patch bằng mắt cũng quan trọng. Patch có thể sửa nhầm file, chứa thay đổi ngoài phạm vi hoặc được tạo từ phiên bản mã nguồn không phù hợp.

Nếu patch đến từ nguồn chưa tin cậy, hãy đọc toàn bộ nội dung và kiểm tra đường dẫn file trước khi áp dụng. Patch có thể thêm script hoặc mã thực thi; việc áp dụng patch không tự chạy mã đó, nhưng commit hoặc chạy build sau này có thể thực thi nội dung vừa thêm.

## 5. Áp dụng patch bằng git apply

Khi patch đã được kiểm tra, áp dụng:

~~~bash
git apply search-fix.patch
~~~

Theo mặc định, git apply cập nhật working tree, không tự stage thay đổi và không tạo commit. Kiểm tra:

~~~bash
git status --short
git diff
~~~

Sau khi kiểm tra nội dung, bạn có thể stage và commit theo quy trình bình thường:

~~~bash
git add src/Search.java
git diff --cached
git commit -m "Normalize search query"
~~~

Điều này hữu ích khi bạn chỉ muốn nhận phần nội dung của thay đổi và tự quyết định cách commit, thông điệp commit hoặc cách kết hợp với công việc khác.

### Áp dụng trực tiếp vào staging index bằng --cached

Nếu muốn patch chỉ cập nhật index mà không sửa working tree:

~~~bash
git apply --cached search-fix.patch
~~~

Sau đó kiểm tra phần đã stage:

~~~bash
git diff --cached
git status --short
~~~

Tùy chọn --cached chỉ tác động tới index. Nội dung trong working tree không được cập nhật theo patch, nên file có thể khác với phiên bản đã stage. Đây là hành vi có chủ đích khi bạn muốn chuẩn bị snapshot commit mà vẫn giữ working tree ở trạng thái riêng.

### Cập nhật cả working tree và index bằng --index

~~~bash
git apply --index search-fix.patch
~~~

Tùy chọn --index yêu cầu Git cập nhật cả index và working tree. Với các đường dẫn bị ảnh hưởng, trạng thái index và working tree ban đầu phải khớp nhau; nếu chúng đã khác nhau, lệnh có thể từ chối để tránh làm mất trạng thái đang stage riêng.

So sánh:

| Lệnh | Working tree | Index |
| --- | --- | --- |
| git apply patch | Được cập nhật | Không đổi |
| git apply --cached patch | Không đổi | Được cập nhật |
| git apply --index patch | Được cập nhật | Được cập nhật |

Không nhầm --cached của git apply với git apply thông thường. Hãy chọn theo nơi bạn muốn patch xuất hiện.

## 6. Một số tùy chọn hữu ích của git apply

### Kiểm tra và đảo ngược patch

Kiểm tra patch mà không áp dụng:

~~~bash
git apply --check search-fix.patch
~~~

Nếu cần hoàn tác đúng patch vừa áp dụng, có thể dùng:

~~~bash
git apply --reverse search-fix.patch
~~~

--reverse đảo chiều thay đổi được mô tả trong patch. Lệnh chỉ thành công nếu nội dung hiện tại khớp với trạng thái mà patch mong đợi. Không dùng nó như một lệnh hoàn tác chung cho mọi thay đổi; kiểm tra diff và trạng thái trước.

### Điều chỉnh đường dẫn bằng -p

Patch thường chứa đường dẫn như a/src/Search.java và b/src/Search.java. Mặc định git apply loại bỏ một thành phần đường dẫn đầu tiên. Tùy chọn -p<n> thay đổi số thành phần bị bỏ:

~~~bash
git apply -p1 search-fix.patch
git apply -p2 search-fix.patch
~~~

Nếu patch được tạo từ thư mục khác hoặc cấu trúc repository đích khác, -p có thể giúp ánh xạ đúng đường dẫn. Dùng --directory để thêm một tiền tố thư mục vào đường dẫn sau khi đã bỏ các thành phần đầu:

~~~bash
git apply --directory=vendor/shared search-fix.patch
~~~

Trước khi áp dụng với -p hoặc --directory, dùng --stat hoặc đọc patch để xác nhận đường dẫn đích.

### Xử lý khoảng trắng

Patch có thể chứa khác biệt về khoảng trắng cuối dòng. Tùy chọn --whitespace điều khiển cách Git xử lý:

~~~bash
git apply --whitespace=warn search-fix.patch
git apply --whitespace=fix search-fix.patch
~~~

- warn cảnh báo về lỗi whitespace.
- fix cố gắng sửa các lỗi whitespace được Git nhận diện khi áp dụng.

Tùy chọn này không thay thế formatter hoặc quy tắc định dạng của dự án. Nếu whitespace có ý nghĩa trong file hoặc patch được tạo bởi công cụ khác, hãy kiểm tra kết quả sau khi áp dụng.

### Áp dụng phần thành công và ghi phần bị từ chối

~~~bash
git apply --reject search-fix.patch
~~~

Với tùy chọn --reject, Git cố áp dụng các hunk có thể áp dụng và ghi những hunk không khớp vào file .rej. Bạn phải mở các file .rej, xử lý thủ công phần bị từ chối và kiểm tra diff sau đó. Tùy chọn này không thể kết hợp với --3way.

## 7. Áp dụng patch bằng cơ chế three-way

Patch được tạo từ diff có thể ghi OID của blob cũ và blob mới. Nếu object nền tương ứng có sẵn trong repository, Git có thể dùng nội dung blob để thực hiện three-way merge thay vì chỉ tìm đoạn ngữ cảnh giống hệt.

Với git apply:

~~~bash
git apply --3way search-fix.patch
~~~

--3way yêu cầu Git thử áp dụng patch bằng cách hợp nhất ba phía khi có đủ thông tin object. Tùy chọn này ngụ ý cập nhật index, trừ khi dùng chế độ --cached theo cách được Git hỗ trợ. Nếu có xung đột, các đường dẫn có thể rơi vào trạng thái unmerged.

Kiểm tra:

~~~bash
git status --short
git diff
git diff --cached
~~~

Mở file xung đột, tìm các marker, chỉnh sửa thành nội dung mong muốn rồi stage:

~~~bash
git add src/Search.java
git diff --cached
~~~

git apply không tạo commit sau khi giải quyết xung đột. Bạn tự kiểm tra, stage các file cần thiết và commit theo quy trình.

Three-way chỉ có thể hoạt động khi patch có đủ thông tin nhận diện blob nền và các object cần thiết có thể truy cập local. Nếu patch chỉ chứa diff rút gọn hoặc repository thiếu object nền, Git có thể không thực hiện được merge ba phía.

## 8. git am dùng patch dạng email như thế nào?

git am được thiết kế để áp dụng các thông điệp email chứa patch, thường được tạo bằng git format-patch. Một patch mail có phần header email, thông điệp commit và phần diff. Nhờ đó, Git có thể tạo commit với metadata tác giả được đóng gói.

Ví dụ tạo patch cho commit hiện tại:

~~~bash
git format-patch -1 HEAD
~~~

Lệnh tạo file dạng:

~~~text
0001-normalize-search-query.patch
~~~

Chuyển file này sang repository nhận patch. Ở branch đích, kiểm tra trạng thái sạch và chạy:

~~~bash
git am 0001-normalize-search-query.patch
~~~

Git đọc nội dung mail patch, áp dụng thay đổi và tạo commit. Commit mới thường giữ author, author date và commit message từ patch. Người chạy git am trở thành committer, và commit hash mới được tạo vì commit được gắn với parent hiện tại cùng metadata commit mới.

### Nhập một loạt commit

Nếu muốn gửi một loạt commit chưa có trên nhánh đích, dùng git format-patch với một khoảng commit:

~~~bash
git format-patch -o ../patches origin/main..HEAD
~~~

Khoảng origin/main..HEAD chọn các commit có thể đi tới từ HEAD nhưng không có trong origin/main. Các patch được đánh số để thể hiện thứ tự.

Ở repository nhận, áp dụng lần lượt các patch theo thứ tự được tạo:

~~~bash
git am ../patches/0001-first-change.patch ../patches/0002-second-change.patch
~~~

Thay tên file bằng các file thực tế trong thư mục patch. Nếu chỉ có một file mbox chứa nhiều thông điệp, có thể truyền file mbox đó cho git am.

Không dùng git am với một diff thuần được tạo bởi git diff rồi kỳ vọng Git tái tạo tác giả và commit message. Với diff thuần, hãy dùng git apply. Nếu muốn bảo toàn cấu trúc commit, hãy tạo patch bằng git format-patch.

## 9. git am và metadata commit

Một patch mail do git format-patch tạo thường chứa:

- From: tác giả của commit gốc.
- Date: thời điểm tác giả tạo commit.
- Subject: thông điệp commit, thường có tiền tố [PATCH].
- Nội dung mô tả commit.
- Diff của commit.

git am sử dụng thông tin đó để tạo commit mới. Người chạy lệnh trở thành committer. Mã commit mới thường khác mã commit gốc vì parent, committer hoặc một phần metadata có thể khác.

Nếu cần thêm dòng Signed-off-by cho người nhập patch:

~~~bash
git am --signoff 0001-normalize-search-query.patch
~~~

Tùy chọn này thêm sign-off vào thông điệp commit được tạo. Sign-off là xác nhận theo quy trình dự án, không tự động tương đương với chữ ký mật mã của commit.

Nếu muốn giữ tiền tố [PATCH] trong subject thay vì để Git xử lý theo quy tắc mặc định:

~~~bash
git am --keep 0001-normalize-search-query.patch
~~~

Chỉ dùng tùy chọn này khi quy trình của nhóm cần giữ nguyên tiền tố subject.

## 10. Three-way merge với git am

Khi patch mail không áp dụng sạch do code ở nhánh đích đã thay đổi, có thể yêu cầu Git thử three-way:

~~~bash
git am --3way 0001-normalize-search-query.patch
~~~

Git dùng thông tin blob trong patch và object có sẵn để thử hợp nhất thay đổi. Nếu phát sinh xung đột, git am tạm dừng chuỗi patch và giữ trạng thái xử lý hiện tại.

Xem patch đang được áp dụng:

~~~bash
git am --show-current-patch=diff
~~~

Kiểm tra file xung đột:

~~~bash
git status --short
~~~

Mở file, giải quyết marker xung đột, sau đó stage kết quả:

~~~bash
git add src/Search.java
~~~

Tiếp tục chuỗi patch:

~~~bash
git am --continue
~~~

Nếu còn patch tiếp theo, Git tiếp tục xử lý theo thứ tự. Nếu patch hiện tại không còn cần thiết, có thể bỏ qua:

~~~bash
git am --skip
~~~

Nếu muốn hủy toàn bộ phiên git am đang dở và trở về trạng thái trước khi bắt đầu:

~~~bash
git am --abort
~~~

--continue yêu cầu hoàn tất patch đang dở sau khi đã giải quyết và stage; --skip bỏ patch hiện tại; --abort hủy toàn bộ chuỗi đang xử lý. Hãy đọc trạng thái và patch hiện tại trước khi chọn.

## 11. Xử lý lỗi khi git apply không áp dụng được

Nếu git apply báo lỗi như patch failed hoặc không tìm thấy file, nguyên nhân thường là:

- Repository đích không ở phiên bản cơ sở mà patch được tạo ra.
- File đã bị đổi tên hoặc di chuyển.
- Nội dung vùng ngữ cảnh đã thay đổi.
- Patch bị thiếu dòng, hỏng encoding hoặc bị mail client thay đổi khoảng trắng.
- Đường dẫn trong patch không tương ứng với cấu trúc repository hiện tại.

Quy trình kiểm tra:

~~~bash
git status --short --branch
git apply --stat search-fix.patch
git apply --check search-fix.patch
~~~

Nếu patch không áp dụng được, xác định branch và commit cơ sở mà người gửi đã dùng. Có thể checkout đúng base trong một worktree riêng, hoặc thử --3way nếu patch có blob IDs và object nền tồn tại. Tránh áp dụng nhiều lần một patch lên working tree đã bị thay đổi một phần.

Nếu dùng --reject, kiểm tra mọi file .rej và so sánh với file gốc. Không bỏ qua hunk bị từ chối chỉ vì lệnh đã áp dụng được các phần còn lại.

## 12. Xử lý lỗi khi git am bị dừng

Khi git am thất bại do xung đột hoặc patch không áp dụng được:

1. Chạy git status --short để xác định file đang xung đột.
2. Dùng git am --show-current-patch=diff để xem patch hiện tại.
3. Kiểm tra các thay đổi trong working tree và index.
4. Giải quyết xung đột, stage file bằng git add.
5. Chạy git am --continue để tạo commit và tiếp tục chuỗi.

Nếu patch không cần thiết hoặc không thể áp dụng trong nhánh này, cân nhắc --skip sau khi xác nhận. Nếu muốn bỏ toàn bộ quá trình nhập patch, dùng --abort.

Không xóa thủ công thư mục trạng thái Git trong lúc am đang chạy. Hãy dùng các lệnh continue, skip hoặc abort để Git đóng phiên làm việc đúng cách.

## 13. Chọn công cụ theo mục tiêu

| Nhu cầu | Công cụ phù hợp | Kết quả |
| --- | --- | --- |
| Chỉ chuyển phần nội dung thay đổi | git diff và git apply | Working tree hoặc index thay đổi; không có commit tự động |
| Stage patch mà không sửa working tree | git apply --cached | Index được cập nhật |
| Áp dụng patch có thể cần three-way | git apply --3way | Thay đổi được áp dụng hoặc để lại xung đột cần xử lý |
| Chuyển một commit cùng tác giả và message | git format-patch và git am | Commit mới được tạo từ patch mail |
| Chuyển một chuỗi commit | git format-patch range và git am | Chuỗi commit được tái tạo theo thứ tự |
| Nhập patch mail và thêm sign-off | git am --signoff | Commit mới có dòng Signed-off-by |

Nếu bạn chỉ cần nội dung và muốn tự viết một commit mới, apply thường đơn giản hơn. Nếu muốn chuyển lịch sử commit qua email hoặc file patch, format-patch kết hợp am phù hợp hơn.

## 14. Quy trình thực hành: chuyển thay đổi không kèm commit

Người gửi tạo patch từ thay đổi đã stage:

~~~bash
git diff --cached --binary > search-change.patch
~~~

Chuyển file patch cho người nhận. Người nhận chạy:

~~~bash
# Kiểm tra trạng thái repository
git status --short --branch

# Xem thống kê và kiểm tra khả năng áp dụng
git apply --stat search-change.patch
git apply --check search-change.patch

# Áp dụng vào working tree
git apply search-change.patch

# Kiểm tra thay đổi
git diff
git status --short

# Stage và tạo commit theo quy trình local
git add src/Search.java
git diff --cached
git commit -m "Apply search improvement"
~~~

Người nhận tự chọn nội dung commit và metadata của commit mới. Patch không mang theo commit gốc.

## 15. Quy trình thực hành: chuyển commit và giữ metadata tác giả

Người gửi có một commit đã hoàn tất:

~~~bash
git format-patch -1 HEAD
~~~

Chuyển file patch sang người nhận. Người nhận chuyển sang branch đích và kiểm tra:

~~~bash
git status --short --branch
git log --oneline -n 5
~~~

Sau khi xác nhận working tree sạch và branch đúng:

~~~bash
git am 0001-normalize-search-query.patch
~~~

Kiểm tra commit mới:

~~~bash
git log -1 --format=fuller
git show --stat --oneline HEAD
~~~

Output fuller cho phép xem Author, AuthorDate, Commit và CommitDate. Bạn có thể so sánh metadata với commit gốc mà người gửi cung cấp.

Nếu patch được tạo từ nhiều commit, dùng git format-patch với range và áp dụng toàn bộ file theo thứ tự. Sau khi nhập, kiểm tra git log để xác nhận số lượng, thứ tự và nội dung commit.

## 16. Những lỗi thường gặp

### Dùng git apply nhưng không thấy commit mới

Đây là hành vi đúng. git apply chỉ thay đổi working tree hoặc index. Hãy stage và commit thủ công nếu muốn tạo commit.

### Dùng git am với patch tạo bởi git diff

Diff thuần không chứa đầy đủ thông tin mail commit. Dùng git apply để áp dụng diff, hoặc yêu cầu người gửi tạo patch bằng git format-patch nếu cần giữ metadata commit.

### git apply báo patch không khớp

Kiểm tra base version, đường dẫn và context. Dùng --check trước, xem patch, cân nhắc --3way khi object nền có sẵn.

### git am dừng ở giữa chuỗi patch

Kiểm tra file xung đột và patch hiện tại. Giải quyết rồi git add và git am --continue; dùng --skip hoặc --abort theo quyết định.

### Commit sau git am có hash khác commit gốc

Điều này bình thường. Commit mới có thể có parent và committer khác. Git giữ thông tin tác giả và message nhưng tạo object commit mới trong lịch sử đích.

### Áp dụng patch nhiều lần

Patch thường chỉ áp dụng được khi nội dung cơ sở phù hợp. Chạy --check và kiểm tra git status trước mỗi lần. Nếu đã áp dụng một phần, đừng chạy lại toàn bộ patch mà chưa xác định trạng thái từng file.

### Dùng --reject nhưng quên file .rej

Các hunk bị từ chối được ghi vào file .rej. Mở và xử lý tất cả các file này, sau đó kiểm tra diff trước khi commit.

## 17. Ghi nhớ

- Patch mô tả khác biệt; patch diff thông thường không phải một commit.
- git apply áp dụng diff vào working tree theo mặc định và không tự tạo commit.
- git apply --cached chỉ cập nhật index; --index cập nhật cả index và working tree.
- git apply --check giúp kiểm tra patch trước khi thay đổi file; --3way có thể dùng blob IDs và object nền để hợp nhất.
- git am đọc patch dạng email/mbox và tạo commit mới, thường giữ author, author date và thông điệp commit.
- git format-patch là cách thông dụng để xuất commit thành patch mail cho git am.
- Khi git am có xung đột, giải quyết và stage file rồi dùng --continue; dùng --skip hoặc --abort khi cần.
- Commit do git am tạo thường có hash khác commit gốc vì parent hoặc committer metadata khác.
- Chọn apply khi cần nội dung; chọn format-patch/am khi cần chuyển commit cùng metadata.

git apply và git am đều giúp chuyển thay đổi mà không cần push trực tiếp giữa hai repository, nhưng kết quả chúng tạo ra khác nhau. Hiểu ranh giới giữa nội dung diff và metadata commit giúp bạn chọn đúng công cụ, xử lý xung đột có kiểm soát và giữ lịch sử phù hợp với cách nhóm cộng tác.
