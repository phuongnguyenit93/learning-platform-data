# Khác biệt giữa nội dung trong chỉ mục và lần sửa mới nhất trên đĩa

Trong Git, một file có thể đồng thời có ba phiên bản khác nhau: phiên bản đã commit trong HEAD, phiên bản đã đưa vào staging area (index) và phiên bản mới nhất đang nằm trên đĩa trong working tree. Khi bạn sửa file sau khi chạy git add, index vẫn giữ snapshot đã stage trước đó, còn working tree chứa lần sửa mới hơn. Vì vậy, một file có thể vừa có thay đổi đã stage vừa có thay đổi chưa stage.

Trong chương **Tệp và chỉ mục** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào cách nhận biết và kiểm tra sự khác nhau giữa index với working tree. Bạn sẽ hiểu git diff đang so sánh hai phía nào, đọc trạng thái hai cột của git status, xem chính xác nội dung đã stage và chọn cách stage hoặc bỏ stage mà không làm mất phần chỉnh sửa cần giữ.

Sau bài học, bạn có thể:

- Phân biệt HEAD, index và working tree.
- Giải thích vì sao sửa file sau git add không tự cập nhật staging area.
- Dùng git diff, git diff --cached và git diff HEAD đúng mục đích.
- Đọc hai cột trạng thái trong git status --short.
- Xem nội dung blob đang nằm trong index và object ID tương ứng.
- Stage toàn bộ file hoặc chỉ một phần bằng git add -p.
- Bỏ stage mà vẫn giữ nội dung trong working tree.
- Nhận biết file chưa được theo dõi và các entry index đang xung đột.
- Kiểm tra khác biệt do line ending hoặc bộ lọc nội dung của Git.

## 1. Ba nơi chứa trạng thái của một file

Git không lấy trực tiếp mọi nội dung trên đĩa để tạo commit. Git sử dụng index làm snapshot chuẩn bị cho commit tiếp theo.

| Nơi lưu | Nội dung | Vai trò |
| --- | --- | --- |
| HEAD | Snapshot của commit hiện tại | Phiên bản đã commit gần nhất trên branch hoặc commit đang checkout |
| Index (staging area) | Snapshot được chọn cho commit kế tiếp | Chứa nội dung đã stage bằng git add hoặc thao tác tương đương |
| Working tree | File thực tế trong thư mục dự án | Nơi bạn mở, tạo, sửa và xóa file |

Có thể hình dung luồng dữ liệu:

~~~text
                git add
Working tree  ------------>  Index  ------------>  HEAD
   file trên đĩa                staged snapshot       commit
                                      git commit

git diff:          so sánh Index với Working tree
git diff --cached: so sánh HEAD với Index
git diff HEAD:     so sánh HEAD với Working tree
~~~

HEAD là mốc commit hiện tại. Index là bản chụp các thay đổi bạn đã chọn để đưa vào commit. Working tree có thể tiếp tục thay đổi sau khi stage. Git giữ ba trạng thái này riêng biệt để bạn có thể chuẩn bị một commit trong khi vẫn tiếp tục chỉnh sửa file.

Index không phải một thư mục chứa bản sao đầy đủ của mọi file. Nó là một cấu trúc dữ liệu ghi nhận đường dẫn, file mode, object ID và một số metadata cần thiết. Nội dung file đã stage được lưu thành blob trong object database; index tham chiếu đến blob đó.

## 2. Vì sao file có thể vừa staged vừa modified?

Giả sử file src/app.js ban đầu có nội dung:

~~~javascript
function greet(name) {
  return "Hello " + name;
}
~~~

Bạn sửa file rồi stage:

~~~bash
git add src/app.js
~~~

Tại thời điểm này, index chứa snapshot sau lần sửa thứ nhất. Sau đó bạn tiếp tục sửa file trên đĩa:

~~~javascript
function greet(name) {
  if (!name) return "Hello guest";
  return "Hello " + name;
}
~~~

Lúc này:

- HEAD vẫn chứa phiên bản cũ trong commit.
- Index chứa phiên bản đã stage trước đó.
- Working tree chứa phiên bản mới hơn với dòng kiểm tra name.

Git không tự stage lần sửa thứ hai. Index chỉ thay đổi khi bạn thực hiện thao tác cập nhật staging area, chẳng hạn git add, git add -p hoặc một lệnh Git tương ứng.

Đây là trạng thái bình thường, không phải lỗi. Nó cho phép bạn stage một phần thay đổi, tiếp tục chỉnh sửa phần khác và tạo commit chỉ chứa những gì đã chọn.

## 3. Ba lệnh diff quan trọng nhất

### git diff: Index so với Working tree

~~~bash
git diff
~~~

Lệnh này hiển thị thay đổi chưa stage: nội dung trong working tree khác nội dung đang có trong index. Nếu bạn đã sửa file sau lần git add gần nhất, phần sửa mới thường xuất hiện ở đây.

### git diff --cached: HEAD so với Index

~~~bash
git diff --cached
~~~

--cached tương đương --staged. Lệnh hiển thị thay đổi đã stage và sẽ được đưa vào commit kế tiếp nếu bạn commit ngay lúc này.

### git diff HEAD: HEAD so với Working tree

~~~bash
git diff HEAD
~~~

Lệnh này so sánh snapshot commit hiện tại với nội dung tracked trong working tree. Nó cho thấy tổng thay đổi trên đĩa so với HEAD, bao gồm phần đã stage và phần chưa stage. Nó không đưa nội dung file untracked vào diff thông thường.

Tóm tắt:

| Lệnh | So sánh | Câu hỏi được trả lời |
| --- | --- | --- |
| git diff | Index ↔ Working tree | Tôi đã sửa gì sau lần stage gần nhất? |
| git diff --cached | HEAD ↔ Index | Tôi đã chọn những gì cho commit tiếp theo? |
| git diff HEAD | HEAD ↔ Working tree | Trên đĩa hiện khác commit hiện tại những gì? |

Ví dụ kiểm tra riêng một file:

~~~bash
git diff -- src/app.js
git diff --cached -- src/app.js
git diff HEAD -- src/app.js
~~~

Dấu -- phân tách tùy chọn/revision với đường dẫn. Nó đặc biệt hữu ích khi tên file có thể giống tên branch hoặc bắt đầu bằng dấu gạch ngang.

## 4. Đọc ví dụ diff khi file có hai lớp thay đổi

Giả sử commit HEAD có:

~~~javascript
const timeout = 1000;
connect(timeout);
~~~

Bạn đổi timeout thành 2000 rồi stage:

~~~bash
git add src/config.js
~~~

Sau đó bạn sửa tiếp lời gọi connect:

~~~javascript
const timeout = 2000;
connect(timeout, { retry: true });
~~~

Kết quả:

**git diff --cached** hiển thị phần đã stage:

~~~diff
-const timeout = 1000;
+const timeout = 2000;
 connect(timeout);
~~~

**git diff** hiển thị phần sửa thêm sau khi stage:

~~~diff
 const timeout = 2000;
-connect(timeout);
+connect(timeout, { retry: true });
~~~

**git diff HEAD** hiển thị tổng thay đổi so với commit:

~~~diff
-const timeout = 1000;
+const timeout = 2000;
-connect(timeout);
+connect(timeout, { retry: true });
~~~

Nếu bạn chạy git commit ngay, Git tạo commit từ nội dung trong index. Phần retry: true chưa được stage nên không nằm trong commit đó.

## 5. Đọc hai cột trạng thái của git status --short

Chạy:

~~~bash
git status --short
~~~

Mỗi dòng thường có hai ký tự trạng thái trước đường dẫn:

~~~text
XY path
~~~

- Cột **X** mô tả trạng thái của index so với HEAD.
- Cột **Y** mô tả trạng thái của working tree so với index.

Ví dụ:

~~~text
 M src/app.js
M  src/config.js
MM src/service.js
A  src/new-file.js
AM src/another-file.js
?? notes.txt
~~~

Ý nghĩa:

| Trạng thái | Cột X | Cột Y | Diễn giải |
| --- | --- | --- | --- |
| X trống, Y=M | Không đổi so với HEAD | Đã sửa so với index | Chỉ có thay đổi chưa stage |
| X=M, Y trống | Đã sửa so với HEAD | Không đổi so với index | Có thay đổi đã stage |
| X=M, Y=M | Đã sửa so với HEAD | Sửa tiếp sau khi stage | Vừa staged vừa modified |
| X=A, Y trống | File mới đã được stage | Không đổi so với index | File mới sẽ được thêm vào commit |
| X=A, Y=M | File mới đã stage | File tiếp tục bị sửa | Commit lấy snapshot đã stage, không lấy lần sửa mới nhất |
| X=?, Y=? | Chưa có trong index | Chưa được Git theo dõi | File untracked |

Các trạng thái khác có thể gồm D (deleted), R (renamed), C (copied) hoặc U (unmerged). Với file xóa:

- X=D: xóa đã stage.
- Y=D: file bị xóa trên đĩa nhưng index vẫn có nội dung.

Không đọc trạng thái hai cột như một ký hiệu duy nhất. Với MM, ký tự đầu và ký tự thứ hai trả lời hai câu hỏi khác nhau.

### Xem trạng thái dạng đầy đủ

~~~bash
git status
~~~

Output dạng đầy đủ thường chia thành các nhóm:

- Changes to be committed: thay đổi trong index.
- Changes not staged for commit: thay đổi working tree chưa stage.
- Untracked files: file chưa được theo dõi.

Nếu cần máy đọc output ổn định, dùng porcelain:

~~~bash
git status --porcelain=v1
~~~

Porcelain là định dạng dành cho script. Không nên viết script dựa vào câu chữ mô tả trạng thái vốn có thể thay đổi theo phiên bản hoặc ngôn ngữ.

## 6. Xem chính xác nội dung đang nằm trong index

Khi file trên đĩa đã sửa thêm, mở file bằng editor chỉ cho bạn thấy working tree. Để xem phiên bản đang được stage, dùng:

~~~bash
git show :src/app.js
~~~

Cú pháp :path lấy nội dung từ index. Nó hữu ích khi cần xác nhận commit kế tiếp sẽ chứa gì.

Xem entry và object ID trong index:

~~~bash
git ls-files --stage -- src/app.js
~~~

Output có dạng:

~~~text
100644 1a2b3c4d... 0    src/app.js
~~~

Các trường gồm:

- File mode, ví dụ 100644 cho file thường hoặc 100755 cho file có quyền thực thi.
- Object ID của blob được index tham chiếu.
- Stage number.
- Đường dẫn.

Trong trạng thái bình thường, stage number là 0. Có thể dùng object ID để xem loại object:

~~~bash
git cat-file -t 1a2b3c4d
git cat-file -p 1a2b3c4d
~~~

Object ID trong ví dụ chỉ minh họa; hãy thay bằng ID thực tế từ output.

Nếu muốn xem nội dung file trong commit HEAD:

~~~bash
git show HEAD:src/app.js
~~~

Ba cách nhìn:

| Lệnh | Phiên bản được xem |
| --- | --- |
| Mở file trong editor | Working tree |
| git show :src/app.js | Index |
| git show HEAD:src/app.js | Commit HEAD |

## 7. git add chụp snapshot tại thời điểm chạy

git add không đánh dấu file theo kiểu “mọi thay đổi trong tương lai đều tự staged”. Lệnh này cập nhật index bằng nội dung hiện tại của đường dẫn tại thời điểm chạy.

Ví dụ:

~~~bash
git add src/app.js
git diff --cached -- src/app.js
~~~

Sau đó bạn sửa file lần nữa:

~~~bash
# Mở editor và tiếp tục sửa src/app.js
git diff -- src/app.js
~~~

Phần sửa mới xuất hiện trong git diff vì index vẫn giữ snapshot trước đó.

Để đưa lần sửa mới nhất vào index:

~~~bash
git add src/app.js
~~~

Lúc này git diff -- src/app.js thường không còn hiển thị khác biệt nếu không có chỉnh sửa mới nào khác.

### git add -A và git add -u

- git add -A cập nhật index cho các file mới, file sửa và file xóa trong phạm vi áp dụng.
- git add -u cập nhật các file đã được theo dõi, gồm sửa và xóa; không thêm file untracked mới.
- git add <path> chỉ cập nhật đường dẫn được chỉ định.

Trước khi dùng git add -A ở repository lớn, hãy kiểm tra git status để biết những file mới nào sẽ được đưa vào index.

## 8. Stage một phần bằng git add -p

Khi một file có nhiều thay đổi không liên quan, bạn có thể chỉ stage một số hunk:

~~~bash
git add -p src/app.js
~~~

Git hiển thị từng hunk và hỏi cách xử lý. Các lựa chọn thường gặp:

| Phím | Ý nghĩa |
| --- | --- |
| y | Stage hunk hiện tại |
| n | Bỏ qua hunk hiện tại |
| q | Dừng, không xử lý các hunk còn lại |
| a | Stage hunk hiện tại và các hunk còn lại của file |
| d | Bỏ qua hunk hiện tại và các hunk còn lại của file |
| s | Chia hunk hiện tại thành các hunk nhỏ hơn nếu có thể |
| e | Chỉnh sửa patch của hunk trước khi stage |
| ? | Hiển thị trợ giúp |

Sau khi chọn một phần:

~~~bash
git diff --cached
git diff
git status --short
~~~

Bạn có thể thấy cùng một file xuất hiện ở cả phần staged và unstaged. Đây là cách tạo commit nhỏ, tập trung, dù các thay đổi nằm trong cùng một file.

Nếu hunk chứa cả thay đổi cần commit và thay đổi chưa sẵn sàng, thử s trước để tách nhỏ. Chỉ dùng e khi hiểu unified diff; sửa patch sai có thể khiến hunk không hợp lệ hoặc stage nhầm nội dung.

## 9. Bỏ stage mà vẫn giữ chỉnh sửa trên đĩa

Nếu stage nhầm file hoặc hunk, bạn có thể đưa index về nội dung của HEAD mà không thay đổi working tree:

~~~bash
git restore --staged src/app.js
~~~

Sau lệnh này:

- Index của src/app.js trở lại phiên bản trong HEAD.
- Nội dung sửa trên đĩa vẫn được giữ.
- Thay đổi sẽ xuất hiện trong git diff thay vì git diff --cached.

Đây là thao tác thường dùng khi cần chọn lại phần sẽ commit.

Lệnh tương đương theo cách dùng cũ:

~~~bash
git reset HEAD -- src/app.js
~~~

Trong trường hợp chỉ định path, git reset cập nhật index về HEAD và không di chuyển branch.

### Bỏ stage một phần

Bạn có thể dùng patch mode để chọn hunk cần đưa index về phiên bản khác:

~~~bash
git restore --staged -p src/app.js
~~~

Xem từng hunk và quyết định phần nào bỏ khỏi staging area. Sau đó kiểm tra cả hai diff.

## 10. Cẩn thận giữa bỏ stage và bỏ chỉnh sửa trên đĩa

Hai lệnh sau có tác dụng khác nhau:

~~~bash
git restore --staged src/app.js
git restore --worktree src/app.js
~~~

- --staged cập nhật index, giữ working tree.
- --worktree cập nhật file trên đĩa từ index, có thể loại bỏ phần sửa chưa stage.

Nếu chạy git restore --worktree src/app.js khi index có snapshot đã stage, nội dung trên đĩa sẽ được thay bằng snapshot trong index. Mọi chỉnh sửa chưa stage của file đó có thể mất.

Trước khi dùng lệnh tác động đến working tree, xem:

~~~bash
git status --short
git diff -- src/app.js
git diff --cached -- src/app.js
~~~

Nếu cần bỏ cả thay đổi đã stage và chưa stage, thao tác đó có thể làm mất toàn bộ chỉnh sửa kể từ HEAD. Chỉ thực hiện khi đã xác nhận nội dung không cần giữ hoặc đã có bản sao/commit an toàn.

Không dùng git reset --hard chỉ để sửa một trạng thái staged/unstaged khi chưa hiểu file nào sẽ bị ảnh hưởng.

## 11. Commit lấy nội dung từ index

Khi chạy:

~~~bash
git commit -m "fix: handle empty name"
~~~

Git tạo commit từ snapshot trong index, không lấy toàn bộ nội dung mới nhất trên đĩa.

Nếu một file đang ở trạng thái MM:

- Phần X là thay đổi đã stage so với HEAD.
- Phần Y là chỉnh sửa thêm trên đĩa so với index.
- Commit chỉ ghi phần X.
- Phần Y tiếp tục nằm trong working tree sau commit.

Kiểm tra sau commit:

~~~bash
git status --short
git show --stat --oneline HEAD
git diff
~~~

Nếu còn thay đổi chưa stage, chúng vẫn hiển thị trong git diff. Đây là hành vi mong đợi.

### git commit -a có tự stage mọi file không?

Không. -a tự stage thay đổi và xóa của các file đã được theo dõi trước khi tạo commit. Nó không tự thêm file untracked mới. Cũng như mọi cách commit khác, nội dung được lấy từ index sau bước tự stage đó.

~~~bash
git commit -am "fix: update tracked config"
~~~

Hãy cẩn thận nếu file đang có cả phần staged và unstaged: -a có thể đưa các thay đổi của file tracked vào index trước khi commit, làm commit chứa nhiều nội dung hơn phần bạn đã stage ban đầu. Nếu cần kiểm soát chính xác, review diff và dùng git commit thông thường.

## 12. File untracked không xuất hiện trong git diff thông thường

Một file mới chưa được stage thường có trạng thái ??:

~~~text
?? notes.txt
~~~

Lệnh git diff và git diff HEAD mặc định không hiển thị nội dung file untracked vì file đó chưa có entry trong index. git status vẫn liệt kê nó.

Để đưa file vào index:

~~~bash
git add notes.txt
git diff --cached -- notes.txt
~~~

Nếu muốn xem nội dung file mới dưới dạng diff trước khi stage, có thể so sánh với một file rỗng bằng git diff --no-index:

~~~bash
git diff --no-index -- /dev/null notes.txt
~~~

Trên Windows, /dev/null không tồn tại theo cách này trong mọi shell; dùng cơ chế null device tương ứng hoặc mở file để review. Cách đơn giản và nhất quán trong Git workflow là xem file, rồi git add và kiểm tra git diff --cached.

Một lựa chọn khác là đánh dấu intent-to-add:

~~~bash
git add -N notes.txt
git diff -- notes.txt
~~~

-N (intent-to-add) tạo entry tạm trong index để Git có thể trình bày diff của file mới mà chưa stage toàn bộ nội dung như một lần git add thông thường. Trạng thái này có thể xuất hiện khác với file đã stage hoàn chỉnh; hãy kiểm tra status và diff trước khi commit.

## 13. Index khi có merge conflict

Trong lúc merge hoặc rebase có xung đột, một đường dẫn có thể có nhiều entry trong index thay vì một entry stage 0.

Kiểm tra:

~~~bash
git status
git ls-files -u
~~~

Các stage thường gặp:

| Stage | Ý nghĩa trong merge conflict |
| --- | --- |
| 1 | Phiên bản base chung |
| 2 | Phiên bản ours |
| 3 | Phiên bản theirs |

Xem object ID và mode của từng phiên bản:

~~~bash
git ls-files --stage -- src/app.js
~~~

Sau khi chỉnh sửa file thành kết quả mong muốn, chạy:

~~~bash
git add src/app.js
git ls-files --stage -- src/app.js
~~~

git add thay các entry xung đột bằng một entry stage 0 đại diện cho kết quả đã giải quyết. Sau đó kiểm tra git status và tiếp tục merge/rebase theo lệnh Git đang chờ.

Không nhầm stage 1/2/3 của index với cột X/Y trong git status --short. Stage number mô tả nhiều phiên bản của một file đang conflict; X/Y mô tả trạng thái giữa HEAD, index và working tree.

## 14. Git xác định file trên đĩa đã thay đổi như thế nào?

Index lưu object ID của nội dung đã stage cùng metadata file như mode và thông tin thống kê. Git có thể dùng metadata như thời gian sửa đổi và kích thước để phát hiện nhanh file có khả năng đã thay đổi. Khi cần, Git đọc nội dung và tính toán để xác định khác biệt.

Điều này giúp Git không phải đọc và hash lại mọi file trong repository ở mọi lần chạy status. Tuy nhiên, metadata hệ thống file có thể bị ảnh hưởng bởi công cụ đồng bộ, timestamp độ phân giải thấp hoặc thao tác ngoài Git. Nếu nghi ngờ trạng thái không được làm mới:

~~~bash
git update-index --refresh
git status
~~~

--refresh yêu cầu Git làm mới thông tin thống kê của các entry index dựa trên working tree; nó không có nghĩa là stage nội dung file mới. Nếu file thực sự thay đổi, trạng thái modified vẫn được phát hiện và bạn vẫn cần git add để cập nhật nội dung trong index.

Không dùng git update-index --assume-unchanged hoặc --skip-worktree chỉ để che giấu thay đổi khi chưa hiểu mục đích. Các cờ này ảnh hưởng cách Git kiểm tra working tree và có thể khiến người dùng hiểu sai trạng thái file.

## 15. Line ending và bộ lọc có thể làm nội dung index khác bytes trên đĩa

Git có thể áp dụng clean/smudge filters hoặc chuẩn hóa line ending theo .gitattributes và cấu hình. Vì vậy, nội dung blob được stage trong index có thể không có byte giống hệt file trên đĩa, dù Git đang xem đó là cùng nội dung logic theo quy tắc chuyển đổi.

Ví dụ, repository chuẩn hóa text thành LF trong object database, trong khi working tree trên Windows dùng CRLF. Khi đó:

- File trên đĩa có thể dùng CRLF.
- Nội dung đã stage/commit có thể được chuẩn hóa thành LF.
- git diff thường trình bày khác biệt theo quy tắc chuyển đổi mà Git áp dụng.

Nếu diff xuất hiện hàng loạt sau khi đổi máy hoặc editor, kiểm tra:

~~~bash
git ls-files --eol -- src/app.js
git check-attr text eol -- src/app.js
git config --show-origin --get core.autocrlf
~~~

Đừng kết luận index sai chỉ vì byte line ending trên đĩa khác với blob đã stage. Hãy kiểm tra attributes và quy tắc clean/smudge của repository.

## 16. Quy trình thực tế: stage một phần rồi sửa tiếp file

Giả sử bạn đang sửa src/payment.js với hai thay đổi:

1. Sửa lỗi tính tổng tiền, đã sẵn sàng commit.
2. Thêm log chẩn đoán, cần kiểm tra thêm trước khi commit.

### Bước 1: xem trạng thái ban đầu

~~~bash
git status --short
git diff -- src/payment.js
~~~

### Bước 2: stage phần sửa lỗi

~~~bash
git add -p src/payment.js
~~~

Chọn y cho hunk sửa lỗi và n cho hunk log. Nếu Git gộp cả hai vào một hunk, dùng s để tách nhỏ nếu có thể hoặc e để chỉnh patch một cách cẩn thận.

### Bước 3: xác nhận phần đã stage

~~~bash
git diff --cached -- src/payment.js
git diff -- src/payment.js
git status --short
~~~

Đảm bảo diff --cached chỉ chứa sửa lỗi tính tổng tiền. Phần log còn lại phải nằm trong git diff.

### Bước 4: commit phần đã chọn

~~~bash
git commit -m "fix(payment): calculate total correctly"
~~~

### Bước 5: kiểm tra phần còn lại

~~~bash
git status --short
git diff
~~~

Phần log chưa stage vẫn còn trong working tree sau commit. Bạn có thể tiếp tục chỉnh sửa, stage và commit trong một commit riêng khi đã sẵn sàng.

## 17. Các lệnh chẩn đoán nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem thay đổi chưa stage | git diff |
| Xem thay đổi đã stage | git diff --cached |
| Xem tổng thay đổi so với HEAD | git diff HEAD |
| Xem trạng thái ngắn hai cột | git status --short |
| Xem snapshot của file trong index | git show :path/to/file |
| Xem snapshot của file trong HEAD | git show HEAD:path/to/file |
| Xem OID và stage của index entry | git ls-files --stage -- path/to/file |
| Liệt kê entry đang conflict | git ls-files -u |
| Stage lại nội dung hiện tại | git add -- path/to/file |
| Bỏ stage, giữ file trên đĩa | git restore --staged -- path/to/file |
| Stage từng hunk | git add -p -- path/to/file |
| Kiểm tra whitespace trong diff | git diff --check |

Khi cần review một file cụ thể, nên dùng đường dẫn sau dấu -- để tránh Git hiểu nhầm tên file là revision hoặc tùy chọn.

## 18. Những nhầm lẫn thường gặp

### git add xong thì mọi lần sửa tiếp theo tự được stage?

Không. git add chụp nội dung tại thời điểm chạy. Lần sửa sau đó nằm trong working tree cho đến khi stage lại.

### git diff hiển thị mọi thay đổi so với commit?

Không. git diff mặc định so sánh index với working tree. Muốn so sánh với commit hiện tại, dùng git diff HEAD.

### git diff --cached hiển thị nội dung mới nhất trên đĩa?

Không. Nó hiển thị nội dung trong index so với HEAD. Nếu file đã sửa sau lần stage, phần mới hơn nằm trong git diff.

### Commit lấy file từ working tree?

Commit lấy snapshot từ index. Chỉnh sửa chưa stage không được đưa vào commit thông thường.

### File untracked sẽ xuất hiện trong git diff?

Không. git status liệt kê file untracked. Muốn đưa nó vào diff staged, cần git add; có thể dùng git add -N để xem intent-to-add.

### Bỏ stage có làm mất thay đổi trên đĩa?

git restore --staged chỉ cập nhật index và giữ working tree. git restore --worktree có thể ghi đè thay đổi chưa stage bằng nội dung index, nên cần kiểm tra trước.

### MM trong git status có phải hai file khác nhau?

Không. Đó là một file có thay đổi ở cả hai lớp: index khác HEAD và working tree khác index.

## 19. Tự kiểm tra

Bạn sửa src/service.js, chạy git add, rồi tiếp tục sửa file. Lệnh git status --short hiển thị:

~~~text
MM src/service.js
~~~

Hãy trả lời:

1. Cột X và Y mô tả những so sánh nào?
2. git diff hiển thị phần thay đổi nào?
3. git diff --cached hiển thị phần nào?
4. Nếu chạy git commit ngay, nội dung nào được đưa vào commit?
5. Lệnh nào xem chính xác nội dung src/service.js đang nằm trong index?
6. Lệnh nào đưa file khỏi staging area nhưng giữ thay đổi trên đĩa?
7. Nếu muốn stage lại toàn bộ nội dung hiện tại, dùng lệnh nào?

**Gợi ý:** X là index so với HEAD; Y là working tree so với index. git diff hiển thị phần sửa sau lần stage gần nhất; git diff --cached hiển thị phần đã stage so với HEAD. Commit lấy nội dung index. Dùng git show :src/service.js để xem snapshot staged. Dùng git restore --staged src/service.js để bỏ stage mà giữ working tree. Dùng git add src/service.js để stage lại nội dung hiện tại.

## Kết luận

HEAD, index và working tree là ba trạng thái riêng biệt của file. git add cập nhật snapshot trong index tại thời điểm chạy; mọi chỉnh sửa sau đó vẫn nằm trên đĩa cho đến khi stage lại. Dùng git diff để xem thay đổi chưa stage, git diff --cached để xem nội dung chuẩn bị commit và git diff HEAD để xem tổng khác biệt so với commit hiện tại. Đọc hai cột X/Y của git status --short, kiểm tra nội dung staged bằng git show :path và bỏ stage bằng git restore --staged khi cần giữ file trên đĩa. Hiểu đúng ba lớp trạng thái giúp bạn tạo commit có chủ đích, tránh đưa nhầm thay đổi vào lịch sử và không làm mất phần việc chưa hoàn tất.
