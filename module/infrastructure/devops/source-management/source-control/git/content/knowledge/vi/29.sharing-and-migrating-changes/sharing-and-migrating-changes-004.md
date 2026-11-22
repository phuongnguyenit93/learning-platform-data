# Kiểm tra bản vá trước khi áp dụng và xử lý lỗi ngữ cảnh

Patch là cách trao đổi thay đổi mà không cần gửi toàn bộ repository. Một file patch thường chứa các dòng bị xóa, được thêm và một phần ngữ cảnh để Git tìm đúng vị trí cần sửa. Khi code ở máy nhận đã thay đổi, patch có thể không còn khớp với nội dung ban đầu. Áp dụng ngay mà không kiểm tra có thể tạo ra thay đổi dở dang, bỏ sót hunk hoặc làm khó việc xác định nguyên nhân.

Trong chương **Trao đổi và di chuyển** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách đọc patch, kiểm tra khả năng áp dụng trước khi thay đổi working tree, chẩn đoán lỗi ngữ cảnh và chọn cách xử lý phù hợp. Bạn sẽ phân biệt git apply với git am, biết khi nào dùng three-way merge, khi nào cần xử lý file .rej và cách xác minh kết quả sau khi patch được áp dụng.

Sau bài học, bạn có thể:

- Đọc cấu trúc unified diff và hiểu vai trò của các dòng ngữ cảnh.
- Kiểm tra patch bằng git apply --check trước khi áp dụng.
- Xem thống kê, đường dẫn và metadata mà patch sẽ thay đổi.
- Chẩn đoán lỗi do sai base, file đã thay đổi, path prefix, whitespace hoặc patch đã được áp dụng.
- Dùng --3way khi patch có thông tin blob cần thiết và object gốc có sẵn.
- Hiểu rủi ro của --reject và cách xử lý file .rej.
- Phân biệt git apply với git am khi nhận patch từ git format-patch.
- Kiểm tra diff, index và trạng thái repository sau khi áp dụng.

## 1. Patch chứa những gì?

Một patch văn bản thường dùng định dạng unified diff. Nó mô tả sự khác nhau giữa phiên bản cũ và phiên bản mới của file.

Ví dụ:

~~~diff
diff --git a/src/greeting.js b/src/greeting.js
index 1a2b3c4..5d6e7f8 100644
--- a/src/greeting.js
+++ b/src/greeting.js
@@ -10,4 +10,5 @@
 function greeting(name) {
-  return "Hello " + name;
+  if (!name) return "Hello guest";
+  return "Hello " + name;
 }
~~~

Các thành phần:

- **diff --git**: đường dẫn file ở phiên bản cũ và mới.
- **index**: object ID của blob cũ và mới cùng file mode; thông tin này có thể giúp áp dụng three-way merge.
- **---**: file cũ.
- **+++**: file mới.
- **@@**: chỉ vị trí và số dòng của hunk trong hai phiên bản.
- Dòng bắt đầu bằng dấu cách: ngữ cảnh, phải khớp với nội dung hiện tại.
- Dòng bắt đầu bằng dấu trừ: nội dung bị xóa.
- Dòng bắt đầu bằng dấu cộng: nội dung được thêm.

Một hunk có thể có nhiều dòng ngữ cảnh ở trước và sau phần thay đổi. Git dùng chúng để tìm vị trí áp dụng thay đổi, thay vì chỉ dựa vào số dòng ghi trong header. Khi các dòng ngữ cảnh đã thay đổi, Git có thể báo patch không áp dụng được.

Patch cũng có thể chứa thay đổi tên file, quyền thực thi, file mới, file bị xóa hoặc nội dung nhị phân. Vì vậy, đừng chỉ đọc phần dòng cộng/trừ; hãy xem cả header và metadata của patch.

## 2. Phân biệt git apply và git am

Hai lệnh thường được dùng để nhận patch nhưng có mục tiêu khác nhau.

| Lệnh | Đầu vào thường gặp | Kết quả |
| --- | --- | --- |
| git apply | Patch diff như file tạo từ git diff | Áp dụng nội dung thay đổi lên working tree hoặc index; không tự tạo commit |
| git am | Mailbox patch tạo từ git format-patch | Áp dụng từng patch và tạo commit, giữ thông tin tác giả, thời gian, thông điệp commit |

Nếu nhận một file .patch chứa diff thuần, git apply thường phù hợp. Nếu nhận file .patch hoặc .mbox từ git format-patch và muốn giữ metadata commit, dùng git am.

Ví dụ tạo diff thuần:

~~~bash
git diff main..feature/login > login.patch
~~~

Áp dụng:

~~~bash
git apply login.patch
~~~

Ví dụ tạo mailbox patch:

~~~bash
git format-patch -1 <commit>
~~~

Áp dụng và tạo commit:

~~~bash
git am 0001-feature-change.patch
~~~

git apply không tái tạo author, ngày và commit message từ mailbox. Nếu cần giữ những thông tin đó, đừng thay git am bằng git apply.

## 3. Chuẩn bị trước khi kiểm tra patch

Trước khi áp dụng patch từ người khác, hãy xác định repository, branch và trạng thái file.

~~~bash
git rev-parse --show-toplevel
git status -sb
git branch --show-current
git log -1 --oneline --decorate
~~~

Các bước cần làm:

1. Xác nhận đang ở đúng repository và đúng thư mục làm việc.
2. Kiểm tra branch hiện tại có phải nền mà patch được tạo ra hay không.
3. Kiểm tra thay đổi chưa commit trong working tree và index.
4. Sao lưu hoặc commit các thay đổi đang làm nếu cần giữ.
5. Xác định patch có phải diff thuần hay mailbox patch.
6. Đọc tên file và phạm vi thay đổi trong patch trước khi áp dụng.

Nếu working tree đang có thay đổi, patch có thể đụng đến cùng file hoặc cùng dòng. Không dùng reset --hard chỉ để làm sạch trạng thái trước khi thử patch. Hãy giữ lại thay đổi hiện tại bằng commit, stash hoặc bản sao phù hợp.

Nên chạy lệnh từ root repository để đường dẫn trong patch dễ dự đoán. Nếu chạy từ thư mục con, Git có thể áp dụng patch theo phạm vi working directory hiện tại; hãy xác nhận path trước khi thao tác.

## 4. Kiểm tra patch mà chưa thay đổi file

Lệnh quan trọng nhất là:

~~~bash
git apply --check change.patch
~~~

--check yêu cầu Git kiểm tra xem patch có áp dụng được hay không mà không sửa working tree hoặc index. Nếu lệnh thành công, patch có thể áp dụng theo điều kiện hiện tại. Nếu thất bại, Git thường chỉ ra file và hunk không khớp.

Có thể yêu cầu output chi tiết hơn:

~~~bash
git apply --check --verbose change.patch
~~~

Kiểm tra thống kê trước khi áp dụng:

~~~bash
git apply --stat change.patch
git apply --numstat change.patch
git apply --summary change.patch
~~~

- --stat hiển thị số dòng thay đổi theo file.
- --numstat hiển thị số dòng thêm, xóa theo định dạng phù hợp cho script.
- --summary hiển thị thông tin như file mới, file bị xóa, đổi tên hoặc thay đổi mode.

Các lệnh thống kê giúp phát hiện patch tác động đến nhiều file hoặc đường dẫn bất ngờ. Chúng không thay thế --check; một patch có thống kê hợp lệ vẫn có thể không khớp với working tree hiện tại.

## 5. Áp dụng patch sau khi kiểm tra

Nếu --check thành công, áp dụng patch:

~~~bash
git apply change.patch
~~~

Theo mặc định, git apply thay đổi working tree và không tự stage nội dung vào index. Kiểm tra:

~~~bash
git status --short
git diff --check
git diff
~~~

git diff --check tìm một số lỗi whitespace trong thay đổi hiện tại, ví dụ khoảng trắng ở cuối dòng. Nó không kiểm tra khả năng áp dụng patch; việc đó do git apply --check đảm nhiệm.

Sau khi review, stage các file cần thiết:

~~~bash
git add -- src/greeting.js
git diff --cached
~~~

Chỉ commit khi nội dung đã được review và test phù hợp.

### Áp dụng đồng thời vào index và working tree

Nếu muốn Git cập nhật cả index lẫn working tree:

~~~bash
git apply --index change.patch
~~~

--index yêu cầu index và working tree của các đường dẫn bị tác động phải khớp nhau, rồi áp dụng thay đổi vào cả hai. Nếu chúng đã khác nhau, Git có thể từ chối.

Có thể kiểm tra trước với:

~~~bash
git apply --check --index change.patch
~~~

### Chỉ áp dụng vào index

~~~bash
git apply --cached change.patch
~~~

--cached áp dụng patch vào index mà không sửa working tree. Cách này hữu ích trong một số workflow tạo staging area có kiểm soát, nhưng cần hiểu rằng index và working tree sau đó có thể khác nhau. Kiểm tra bằng:

~~~bash
git diff --cached
git diff
git status --short
~~~

## 6. Hiểu lỗi ngữ cảnh

Lỗi ngữ cảnh xảy ra khi Git không tìm thấy đoạn nội dung phù hợp để áp dụng một hunk. Ví dụ:

~~~text
error: patch failed: src/greeting.js:10
error: src/greeting.js: patch does not apply
~~~

Thông báo này không nhất thiết có nghĩa patch bị hỏng. Nó có thể được tạo từ một phiên bản code khác với phiên bản hiện tại.

Các nguyên nhân phổ biến:

| Nguyên nhân | Dấu hiệu | Hướng kiểm tra |
| --- | --- | --- |
| Sai base commit | Nhiều hunk không khớp, file đã thay đổi đáng kể | So sánh commit nền và lịch sử file |
| File đã được sửa | Chỉ một số hunk trong file thất bại | Đọc dòng ngữ cảnh hiện tại và diff |
| Patch đã áp dụng một phần hoặc toàn bộ | Một số đoạn cũ không còn tồn tại | Thử kiểm tra ngược và so sánh nội dung |
| Sai path prefix | Git báo không tìm thấy file hoặc không áp dụng đúng đường dẫn | Xem header và điều chỉnh -p |
| Khác biệt whitespace | Chữ giống nhau nhưng khoảng trắng hoặc tab khác | So sánh whitespace và cân nhắc tùy chọn ignore |
| Line ending khác nhau | File có CRLF/LF hoặc line ending hỗn hợp | Kiểm tra trạng thái EOL và bytes của file |
| Patch bị cắt hoặc sửa sai | Header hunk và số dòng không khớp, thiếu đoạn kết | Kiểm tra file patch và nguồn gửi |
| File đã đổi tên hoặc di chuyển | Patch tham chiếu đường dẫn cũ | Xác định đường dẫn mới và tạo patch theo base hiện tại |

Không nên lập tức ép Git bỏ qua whitespace hoặc dùng --reject. Trước tiên cần biết nguyên nhân, vì hai lựa chọn đó có thể che giấu một patch được tạo từ nền sai.

## 7. Chẩn đoán base commit và nội dung file

Patch thường được tạo giữa hai trạng thái của một file. Nếu máy nhận đang ở commit khác, các dòng ngữ cảnh có thể không còn giống.

### Xem patch muốn thay đổi file nào

~~~bash
git apply --stat change.patch
git apply --summary change.patch
~~~

Đọc các header diff --git, --- và +++ để xác định tên file cũ/mới. Sau đó xem nội dung hiện tại:

~~~bash
git diff -- src/greeting.js
git log --oneline --follow -- src/greeting.js
~~~

Nếu biết commit nền mà người tạo patch sử dụng:

~~~bash
git show <base-commit>:src/greeting.js
~~~

So sánh phiên bản nền với file hiện tại để xác định thay đổi nào đã làm ngữ cảnh lệch.

### Xác định patch đã được áp dụng chưa

Có thể thử kiểm tra ngược:

~~~bash
git apply --reverse --check change.patch
~~~

Nếu kiểm tra ngược thành công, đó là dấu hiệu nội dung patch có thể đã hiện diện trong working tree. Đây không phải bằng chứng tuyệt đối rằng toàn bộ patch đã được áp dụng đúng; hãy so sánh diff và lịch sử trước khi kết luận.

Nếu patch đã áp dụng một phần, kiểm tra từng file và từng hunk. Không chạy lại toàn bộ patch một cách mù quáng vì có thể tạo thêm lỗi hoặc thay đổi trùng lặp.

## 8. Kiểm tra và sửa path prefix

Patch thường chứa đường dẫn như:

~~~text
diff --git a/src/greeting.js b/src/greeting.js
--- a/src/greeting.js
+++ b/src/greeting.js
~~~

Git apply thường bỏ một thành phần đường dẫn đầu tiên theo mặc định, nên a/ và b/ trở thành src/greeting.js.

Tùy chọn -p<n> điều khiển số thành phần đường dẫn bị loại bỏ:

~~~bash
git apply --check -p1 change.patch
git apply --check -p0 change.patch
~~~

- -p1 bỏ thành phần đầu tiên, ví dụ a/.
- -p0 giữ nguyên đường dẫn trong patch.
- -p2 bỏ hai thành phần đầu tiên.

Nếu patch không có prefix a/ và b/, thử xác định đúng số thành phần cần bỏ bằng cách đọc header, không chọn ngẫu nhiên.

Có thể thêm thư mục đích sau khi loại prefix:

~~~bash
git apply --check --directory=vendor/library change.patch
~~~

--directory thêm đường dẫn vào đầu đường dẫn file sau khi xử lý -p. Ví dụ này áp dụng đường dẫn patch bên dưới vendor/library. Kiểm tra --stat và --check trước để chắc chắn không ghi nhầm vị trí.

## 9. Xử lý khác biệt whitespace

Một patch có thể không khớp vì các dòng ngữ cảnh khác nhau ở dấu cách hoặc tab. Git có các tùy chọn nới lỏng việc so khớp whitespace trong dòng ngữ cảnh:

~~~bash
git apply --check --ignore-space-change change.patch
git apply --check --ignore-whitespace change.patch
~~~

Hai tùy chọn này giúp Git bỏ qua một số khác biệt whitespace trong các dòng ngữ cảnh khi tìm vị trí áp dụng. Chúng không có nghĩa là mọi whitespace trong các dòng mới được tự động loại bỏ. Hãy kiểm tra nội dung sau khi áp dụng.

### Whitespace trong dòng được thêm

Tùy chọn --whitespace điều khiển cách xử lý whitespace error trong các dòng được patch thêm hoặc sửa:

~~~bash
git apply --whitespace=warn change.patch
git apply --whitespace=fix change.patch
git apply --whitespace=error change.patch
~~~

- warn: cảnh báo về whitespace error.
- fix: cố gắng sửa whitespace error trong phần được thêm.
- error: báo lỗi khi gặp whitespace error.
- error-all: giống error nhưng hiển thị tất cả whitespace error được phát hiện thay vì chỉ báo lỗi đầu tiên.
- nowarn: không hiển thị cảnh báo whitespace.

Giá trị mặc định còn có thể chịu ảnh hưởng của core.whitespace. Whitespace error thường bao gồm trailing whitespace hoặc khoảng trắng trước tab trong một số ngữ cảnh. Không dùng fix nếu whitespace đó có ý nghĩa với định dạng hoặc dữ liệu của dự án.

Lưu ý: --ignore-space-change và --ignore-whitespace điều chỉnh cách khớp dòng ngữ cảnh; --whitespace điều khiển cách phát hiện hoặc sửa lỗi whitespace trong nội dung patch. Đây là hai nhóm chức năng khác nhau.

## 10. Khi nào dùng --3way?

Nếu patch không áp dụng trực tiếp do file đã thay đổi, Git có thể thử three-way merge:

~~~bash
git apply --3way change.patch
~~~

Git cần patch ghi lại object ID của blob gốc và cần blob đó có sẵn trong object database. Nếu đủ thông tin, Git có thể dùng phiên bản base, phiên bản hiện tại và phiên bản được patch đề xuất để hợp nhất.

--3way hàm ý --index. Vì vậy, Git cập nhật index cùng working tree và có thể để lại các entry chưa merge nếu phát sinh xung đột. Không xem việc lệnh trả mã khác 0 là không có gì thay đổi; kiểm tra trạng thái ngay sau đó.

~~~bash
git status
git ls-files -u
git diff
~~~

Nếu có conflict:

1. Mở file và xác định vùng xung đột.
2. So sánh base, ours và theirs nếu cần.
3. Sửa nội dung thành kết quả mong muốn.
4. Stage file đã giải quyết bằng git add.
5. Kiểm tra git diff --cached và chạy test.

Khác với git am, git apply --3way không có lệnh --continue để kết thúc một chuỗi áp dụng. Sau khi giải quyết, bạn tự stage và commit nếu workflow cần commit.

### Tạo patch có đủ thông tin cho three-way

Khi tạo diff để chia sẻ, có thể giữ đầy đủ blob ID và binary data:

~~~bash
git diff --full-index --binary base..topic > change.patch
~~~

--full-index ghi đầy đủ object ID của blob trong header index; --binary tạo dữ liệu cần thiết cho thay đổi nhị phân. Người nhận vẫn cần có blob base trong object database để three-way merge hoạt động.

Nếu chỉ có patch dạng văn bản được chỉnh sửa thủ công và không còn object gốc, Git có thể không đủ thông tin để thực hiện three-way. Khi đó cần lấy đúng base hoặc xử lý thủ công.

## 11. Khi nào dùng --reject?

Theo mặc định, git apply xử lý patch theo hướng nguyên tử: nếu một phần không áp dụng được, Git không áp dụng các phần khác của patch. Tùy chọn --reject thay đổi hành vi:

~~~bash
git apply --reject change.patch
~~~

Git áp dụng các hunk khớp được và ghi các hunk bị từ chối vào file .rej tương ứng. Điều này hữu ích khi bạn chủ động muốn lấy các phần độc lập có thể áp dụng và tự xử lý phần còn lại.

Tuy nhiên, kết quả có thể là một thay đổi một phần. Sau khi chạy:

~~~bash
git status --short
git diff
~~~

Tìm các file .rej và đọc từng hunk:

~~~text
src/greeting.js.rej
~~~

Mở file .rej, đối chiếu với nội dung hiện tại, rồi chỉnh sửa thủ công. Sau khi giải quyết, xóa file .rej đã xử lý và kiểm tra diff. Không stage hoặc commit khi còn hunk bị bỏ sót.

Không kết hợp --reject với --3way; đây là hai chiến lược xử lý thất bại khác nhau. Dùng --3way khi có blob base để Git thử hợp nhất; dùng --reject khi chủ động chấp nhận áp dụng một phần và tự xử lý hunk còn lại.

## 12. Patch đã bị chỉnh sửa hoặc hỏng định dạng

Nếu patch được sửa thủ công, số dòng trong header hunk có thể không còn đúng. Ví dụ:

~~~diff
@@ -10,4 +10,5 @@
~~~

nhưng phần nội dung sau header lại có số dòng khác với các count khai báo. Có thể thử:

~~~bash
git apply --check --recount change.patch
~~~

--recount yêu cầu Git tính lại số dòng của hunk thay vì tin hoàn toàn vào số lượng ghi trong header. Tùy chọn này chỉ giúp xử lý sai lệch count; nó không sửa nội dung patch bị thiếu hoặc ngữ cảnh không đúng.

Nếu patch bị cắt, thiếu dòng, sai encoding hoặc mất phần dữ liệu nhị phân, hãy lấy lại file gốc từ người gửi hoặc tạo lại patch. Không nên dùng --recount để che giấu một file patch bị hỏng.

## 13. Xử lý patch dạng mailbox bằng git am

Khi nhận patch từ git format-patch, git am là công cụ phù hợp vì nó tái tạo commit từ thông tin trong email patch.

Áp dụng một patch:

~~~bash
git am 0001-fix-login.patch
~~~

Nếu patch không khớp nhưng có đủ blob base, thử:

~~~bash
git am --3way 0001-fix-login.patch
~~~

Nếu xảy ra conflict, xem patch đang được xử lý:

~~~bash
git am --show-current-patch=diff
git status
git ls-files -u
~~~

Giải quyết conflict trong file, sau đó stage:

~~~bash
git add -- src/login.js
git am --continue
~~~

Các lệnh điều khiển chuỗi am:

| Lệnh | Tác dụng |
| --- | --- |
| git am --continue | Tiếp tục sau khi đã giải quyết và stage conflict |
| git am --skip | Bỏ qua patch hiện tại và chuyển sang patch kế tiếp |
| git am --abort | Hủy toàn bộ phiên am đang diễn ra và quay về trạng thái trước khi bắt đầu phiên đó |
| git am --show-current-patch=diff | Hiển thị diff của patch hiện tại đang được xử lý |

Khác với git apply, git am duy trì trạng thái của chuỗi commit đang được áp dụng. Vì vậy, sau khi giải quyết conflict, dùng --continue; nếu bỏ một patch, dùng --skip; nếu muốn dừng toàn bộ chuỗi, dùng --abort.

## 14. Quy trình hoàn chỉnh khi nhận patch không khớp

Giả sử bạn nhận change.patch nhưng git apply --check báo một hunk của src/greeting.js không áp dụng được.

### Bước 1: bảo vệ công việc hiện tại

~~~bash
git status -sb
git diff
git diff --cached
~~~

Lưu các thay đổi chưa commit cần giữ trước khi thử lại. Không xóa working tree chỉ để làm patch áp dụng được.

### Bước 2: đọc phạm vi và header patch

~~~bash
git apply --stat change.patch
git apply --summary change.patch
~~~

Xác định file, đổi tên, mode và phạm vi thay đổi. Mở patch để đọc các dòng ngữ cảnh xung quanh hunk bị lỗi.

### Bước 3: kiểm tra base và file hiện tại

~~~bash
git log --oneline --follow -- src/greeting.js
git diff -- src/greeting.js
~~~

Nếu người gửi cung cấp base commit, xem file tại base:

~~~bash
git show <base-commit>:src/greeting.js
~~~

So sánh nội dung hiện tại với các dòng ngữ cảnh trong patch. Xác định file đã được sửa, đổi tên hay patch đã áp dụng trước đó.

### Bước 4: kiểm tra path và whitespace

~~~bash
git apply --check -p1 change.patch
git apply --check -p0 change.patch
git apply --check --ignore-space-change change.patch
~~~

Chỉ thử tùy chọn phù hợp với bằng chứng từ patch header và nội dung file. Không dùng tất cả tùy chọn cùng lúc để “thử cho chạy” vì sẽ khó biết nguyên nhân thật.

### Bước 5: chọn chiến lược

- Nếu patch được tạo từ base cũ nhưng blob base còn trong repository, thử --3way.
- Nếu patch chỉ lệch whitespace ở dòng ngữ cảnh và nội dung logic vẫn phù hợp, cân nhắc --ignore-space-change hoặc --ignore-whitespace.
- Nếu một số hunk độc lập có thể áp dụng và bạn chấp nhận xử lý thủ công phần còn lại, dùng --reject.
- Nếu patch đã áp dụng, không áp dụng lại; xác minh bằng reverse check và diff.
- Nếu patch thiếu hoặc sai nội dung, yêu cầu tạo lại từ base phù hợp.

### Bước 6: review và xác minh

~~~bash
git status --short
git diff --check
git diff
~~~

Nếu áp dụng vào index hoặc dùng three-way:

~~~bash
git diff --cached
git ls-files -u
~~~

Đảm bảo không còn conflict hoặc file .rej chưa xử lý. Chạy test phù hợp và stage đúng file trước khi commit.

## 15. Kiểm tra patch có thay đổi file nhị phân, mode hoặc đường dẫn nhạy cảm

Patch không chỉ chứa sửa đổi văn bản. Nó có thể:

- Thêm hoặc xóa file.
- Đổi tên hoặc sao chép file.
- Thay đổi file mode, ví dụ bật/tắt quyền thực thi.
- Chứa binary patch.
- Thay đổi file cấu hình, script hoặc workflow tự động hóa.

Trước khi áp dụng patch không rõ nguồn, kiểm tra --stat và --summary, rồi đọc header từng file. Chú ý đường dẫn nằm ngoài phạm vi dự án, file cấu hình bảo mật, script chạy trong CI và các file được thực thi tự động.

Git apply có bảo vệ đường dẫn không an toàn theo mặc định. Không bật --unsafe-paths chỉ để làm patch áp dụng được nếu chưa kiểm tra nguồn và mọi đường dẫn đích. Không chạy thao tác áp dụng patch với quyền quản trị cao hơn mức cần thiết.

Với binary patch, patch cần chứa dữ liệu nhị phân tương ứng, thường được tạo bằng git diff --binary. Một patch văn bản không có nội dung binary không thể tái tạo chính xác thay đổi file nhị phân.

## 16. Tạo patch dễ áp dụng hơn

Người gửi có thể giảm lỗi ngữ cảnh bằng cách tạo patch từ base phù hợp và giữ metadata cần thiết.

### Tạo diff giữa hai commit

~~~bash
git diff --full-index --binary <base>..<topic> > change.patch
~~~

Patch thể hiện thay đổi từ base đến topic. Người nhận nên có base tương ứng hoặc có đủ object cần thiết cho three-way merge.

### Tạo mailbox patch giữ commit metadata

~~~bash
git format-patch -o ../outgoing-patches <base>..<topic>
~~~

Mỗi commit trong khoảng được tạo thành một file patch riêng. Người nhận dùng git am để giữ author, thời gian và commit message.

### Kiểm tra patch trước khi gửi

~~~bash
git diff --check <base>..<topic>
git diff --stat <base>..<topic>
~~~

Kiểm tra whitespace và phạm vi thay đổi trước khi chia sẻ. Ghi rõ base commit hoặc branch mà patch được tạo từ, các dependency cần có và thứ tự áp dụng nếu patch gồm nhiều phần.

Không tạo patch từ một working tree lẫn nhiều thay đổi không liên quan nếu người nhận cần áp dụng độc lập. Tách patch theo mục đích giúp review, thử nghiệm và xử lý conflict dễ hơn.

## 17. Những nhầm lẫn thường gặp

### git apply --check thành công có nghĩa patch đã an toàn?

Không. Nó chỉ xác nhận patch có thể áp dụng trong trạng thái hiện tại. Bạn vẫn phải review đường dẫn, nội dung, file mode và tác động của thay đổi.

### git diff --check có giống git apply --check?

Không. git apply --check kiểm tra patch có thể áp dụng mà không sửa file. git diff --check kiểm tra một diff hiện có về một số lỗi whitespace.

### git apply tự tạo commit?

Không. Nó áp dụng thay đổi lên working tree hoặc index. Muốn tạo commit, bạn cần stage và chạy git commit.

### --3way luôn giải quyết được lỗi ngữ cảnh?

Không. Git cần patch ghi nhận blob ID gốc và blob đó phải có trong object database. Nếu thiếu base hoặc thay đổi xung đột quá phức tạp, bạn vẫn phải giải quyết thủ công hoặc lấy lại patch đúng base.

### --reject có giữ nguyên toàn bộ repository nếu một hunk thất bại?

Không. Nó cố gắng áp dụng các phần khớp được và ghi phần bị từ chối vào file .rej. Kết quả có thể là thay đổi một phần; phải review và xử lý từng file.

### git apply và git am có thể thay thế nhau?

Không hoàn toàn. git apply phù hợp với diff thuần và không tạo commit. git am xử lý mailbox patch, tạo commit và giữ metadata của người gửi.

### Patch không áp dụng được thì cứ tăng số dòng context?

Không. Nhiều context hơn có thể làm patch khó áp dụng hơn khi code đã thay đổi, dù tăng context khi tạo patch thường giúp xác định đúng vị trí và phát hiện lệch nền. Cách đúng là xác định base và nội dung khác biệt, rồi tạo lại hoặc hợp nhất có chủ đích.

## 18. Tự kiểm tra

Bạn nhận change.patch từ một đồng nghiệp. Lệnh git apply --check báo lỗi ở hai hunk trong src/api.js. File hiện tại đã có một commit sửa tên hàm; patch được tạo từ commit trước đó. Header patch có dòng index chứa blob ID cũ và mới. Repository của bạn còn blob base.

Hãy trả lời:

1. Lệnh nào kiểm tra patch mà chưa sửa file?
2. Vì sao patch có thể không khớp dù nội dung thay đổi vẫn hợp lý?
3. Lệnh nào có thể thử three-way merge dựa trên blob base?
4. Sau khi --3way tạo conflict, bạn kiểm tra và giải quyết bằng những lệnh nào?
5. --reject khác --3way ở cách xử lý hunk thất bại ra sao?
6. Nếu file patch là mailbox từ git format-patch và cần giữ author/commit message, dùng lệnh nào?
7. Vì sao cần review diff và chạy test sau khi patch áp dụng thành công?

**Gợi ý:** Dùng git apply --check change.patch để kiểm tra trước. Hunk có thể lệch vì file hiện tại đã thay đổi so với base. Dùng git apply --3way change.patch nếu patch có blob ID và object base còn sẵn. Kiểm tra git status, git ls-files -u, sửa conflict, git add rồi review diff. --reject áp dụng phần khớp và tạo .rej cho phần lỗi; --3way thử hợp nhất bằng base và có thể để conflict trong index. Với mailbox patch, dùng git am hoặc git am --3way. Cuối cùng cần xác minh nội dung, đường dẫn, whitespace và hành vi thực tế.

## Kết luận

Hãy đọc patch và kiểm tra phạm vi trước khi áp dụng. git apply --check xác nhận khả năng áp dụng mà không sửa file; sau đó mới dùng git apply và review diff. Khi lỗi ngữ cảnh, hãy kiểm tra base commit, nội dung file, path prefix, whitespace và khả năng patch đã được áp dụng. Dùng --3way khi có blob base để Git thử hợp nhất, hoặc --reject khi chủ động chấp nhận áp dụng một phần và xử lý file .rej. Với mailbox từ git format-patch, dùng git am để giữ metadata commit. Dù cách áp dụng nào thành công, vẫn cần kiểm tra trạng thái, diff, conflict, whitespace và test trước khi commit.
