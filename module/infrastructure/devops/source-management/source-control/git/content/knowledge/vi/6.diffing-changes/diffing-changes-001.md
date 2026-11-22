# So sánh thư mục làm việc với chỉ mục bằng git diff

## Mục tiêu

Trong Git, bạn có thể chỉnh sửa file nhiều lần trước khi tạo commit. Một phần thay đổi có thể đã được đưa vào staging area, trong khi phần khác vẫn còn ở working tree. Lệnh `git diff` giúp xem chính xác hai vùng này khác nhau ở đâu.

Bài học tập trung vào phép so sánh giữa **working tree và index**:

~~~bash
git diff
~~~

Đây là lệnh dùng để xem các thay đổi trong file đã được Git theo dõi nhưng chưa được stage. Sau bài học, bạn có thể:

- Phân biệt working tree, index và commit hiện tại (`HEAD`).
- Hiểu chính xác `git diff` đang so sánh hai trạng thái nào.
- Đọc các dòng thêm, xóa và vùng thay đổi (hunk) trong diff.
- Chỉ xem thay đổi của một file hoặc một nhóm đường dẫn.
- Nhận biết file staged, unstaged và untracked.
- Stage hoặc bỏ stage thay đổi có chọn lọc.
- Kiểm tra whitespace, file nhị phân, đổi mode và các trường hợp diff đặc biệt.
- Dùng diff để xác minh nội dung sẽ đi vào commit tiếp theo.

## Ba trạng thái cần phân biệt

Khi làm việc với Git, một file có thể được xem qua ba trạng thái quan trọng:

1. **HEAD:** snapshot của commit hiện tại trên branch đang checkout.
2. **Index (staging area):** snapshot được chuẩn bị cho commit tiếp theo.
3. **Working tree:** nội dung file thực tế trong thư mục làm việc.

Luồng thay đổi thông thường:

~~~text
              HEAD
        snapshot của commit
                 |
                 | git diff --cached
                 v
               Index
          staging area
                 |
                 | git diff
                 v
            Working tree
          file đang chỉnh sửa
~~~

Hai phép so sánh liên quan trực tiếp:

- `git diff`: so sánh index với working tree.
- `git diff --cached`: so sánh HEAD với index.

Nếu muốn xem tổng thay đổi của file được theo dõi so với commit hiện tại:

~~~bash
git diff HEAD
~~~

Lệnh này so sánh HEAD với working tree, do đó bao gồm cả thay đổi đã stage và chưa stage. File untracked vẫn không tự động xuất hiện trong diff này.

### Index không phải là một thư mục khác

Index là cấu trúc dữ liệu Git dùng để lưu nội dung và metadata của các đường dẫn đã được chọn cho commit kế tiếp. Nó thường được lưu trong file `.git/index`, nhưng bạn không nên sửa trực tiếp file này.

Khi chạy:

~~~bash
git add src/PaymentService.java
~~~

Git cập nhật index bằng nội dung hiện tại của file tại thời điểm stage. Nếu sau đó bạn tiếp tục sửa `PaymentService.java`, working tree sẽ khác index. `git diff` sẽ hiển thị phần sửa mới đó.

Vì vậy, staging area không đơn giản là danh sách tên file. Với một file đã stage, index giữ phiên bản nội dung cụ thể được chuẩn bị để commit.

## git diff so sánh working tree với index

Giả sử `README.md` trong commit hiện tại có nội dung:

~~~text
Project: Payment Service
Status: active
Owner: Platform Team
~~~

Bạn sửa dòng Status thành `Status: in development`, nhưng chưa stage:

~~~text
Project: Payment Service
Status: in development
Owner: Platform Team
~~~

Chạy:

~~~bash
git diff
~~~

Git hiển thị phần khác nhau giữa phiên bản đang có trong index và phiên bản file trong working tree. Vì index vẫn chứa nội dung từ commit hiện tại, kết quả có thể như sau:

~~~diff
diff --git a/README.md b/README.md
index 3a7b1c2..8d4e5f6 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,3 @@
 Project: Payment Service
-Status: active
+Status: in development
 Owner: Platform Team
~~~

Đọc kết quả:

- Dòng bắt đầu bằng `-` là dòng có trong index nhưng không còn trong working tree.
- Dòng bắt đầu bằng `+` là dòng có trong working tree nhưng không có trong index.
- Dòng bắt đầu bằng dấu cách là dòng ngữ cảnh không đổi.
- `--- a/README.md` và `+++ b/README.md` cho biết hai phía đang được so sánh.
- `@@ -1,3 +1,3 @@` cho biết vị trí và phạm vi dòng trong hai phiên bản.

Trong ví dụ này, file có thay đổi chưa stage. Chưa có commit nào được tạo và index vẫn giữ phiên bản cũ.

### Tại sao Git không so sánh trực tiếp với remote?

`git diff` không mặc định truy cập remote. Nó so sánh trạng thái local: index và working tree. Nếu remote có commit mới, điều đó không làm thay đổi phép so sánh này.

Để xem thay đổi giữa hai commit hoặc hai branch, cần chỉ rõ hai mốc so sánh, ví dụ:

~~~bash
git diff main origin/main
~~~

Đó là một mục đích khác với việc xem thay đổi chưa stage trong working tree.

## Đọc cấu trúc unified diff

Một diff thường có các phần:

~~~diff
diff --git a/src/PaymentService.java b/src/PaymentService.java
index 4a12abc..7b34def 100644
--- a/src/PaymentService.java
+++ b/src/PaymentService.java
@@ -10,6 +10,8 @@ public class PaymentService {
     public void validate() {
-        checkAmount();
+        checkAmount();
+        checkCurrency();
+        checkAccountStatus();
     }
 }
~~~

### Dòng tiêu đề file

`diff --git a/... b/...` cho biết Git đang trình bày thay đổi của đường dẫn nào. Ký hiệu `a` và `b` là hai phía của phép so sánh, không phải tên thư mục thật.

### Dòng index

`index <old>..<new> <mode>` thường hiển thị object ID rút gọn của blob ở hai phía và mode file. Khi file được sửa nội dung, blob ID thường thay đổi.

### Dòng --- và +++

- `---` mô tả phía cũ (index).
- `+++` mô tả phía mới (working tree).

Trong diff của một file mới được nhận diện bằng intent-to-add, hoặc trong những dạng diff khác, một phía có thể được biểu diễn bằng `/dev/null`. Hãy đọc cả ngữ cảnh thay vì suy luận mọi trường hợp chỉ từ một dòng tiêu đề.

### Dòng hunk @@

Ví dụ:

~~~text
@@ -10,6 +10,8 @@
~~~

Phần `-10,6` chỉ vị trí bắt đầu và số dòng của vùng cũ. Phần `+10,8` chỉ vị trí bắt đầu và số dòng của vùng mới. Các hunk giúp bạn tập trung vào từng khu vực thay đổi thay vì đọc lại toàn bộ file.

### Dấu +, - và dấu cách

| Ký hiệu | Ý nghĩa |
|---|---|
| `+` | Dòng được thêm ở phía working tree |
| `-` | Dòng bị xóa khỏi phiên bản trong index |
| Dấu cách | Dòng ngữ cảnh giữ nguyên |
| `\ No newline at end of file` | Một phía của file không có newline cuối file |

Đừng nhầm dấu `+` trong diff với thao tác stage. Diff chỉ mô tả sự khác nhau; để đưa nội dung vào index, bạn vẫn cần `git add` hoặc thao tác stage tương đương trong GUI.

## Quan sát thay đổi trước và sau khi stage

Đây là chuỗi thao tác quan trọng nhất để hiểu `git diff`.

### Bước 1: Sửa một file

Giả sử bạn chỉnh `src/PaymentService.java`. Xem thay đổi chưa stage:

~~~bash
git diff -- src/PaymentService.java
~~~

Kết quả cho biết working tree khác index ở đâu.

### Bước 2: Stage thay đổi hiện tại

~~~bash
git add src/PaymentService.java
~~~

Sau khi stage, index được cập nhật theo nội dung file tại thời điểm chạy lệnh. Vì working tree và index đang giống nhau, lệnh:

~~~bash
git diff -- src/PaymentService.java
~~~

thường không in ra nội dung nào.

Nhưng thay đổi vẫn đang chờ commit. Kiểm tra phần staged bằng:

~~~bash
git diff --cached -- src/PaymentService.java
~~~

Lệnh này so sánh index với HEAD. Nội dung vừa stage sẽ xuất hiện ở đây.

### Bước 3: Sửa tiếp file sau khi stage

Giả sử bạn thêm một điều kiện kiểm tra khác vào cùng file nhưng chưa chạy `git add` lần nữa.

Bây giờ file có hai phiên bản khác nhau:

- Index: chứa thay đổi đã stage ở bước 2.
- Working tree: chứa cả thay đổi đã stage và phần sửa mới ở bước 3.

Chạy cả hai lệnh:

~~~bash
git diff -- src/PaymentService.java
git diff --cached -- src/PaymentService.java
~~~

Lệnh đầu chỉ hiển thị phần sửa sau lần stage gần nhất. Lệnh thứ hai hiển thị phần đã stage so với HEAD.

Có thể kiểm tra tổng thay đổi so với commit hiện tại:

~~~bash
git diff HEAD -- src/PaymentService.java
~~~

Lệnh này bao gồm cả phần staged và unstaged của file được theo dõi.

### Bảng tổng hợp

| Trạng thái file | `git diff` | `git diff --cached` | `git diff HEAD` |
|---|---|---|---|
| Chỉ sửa, chưa stage | Hiển thị thay đổi | Không hiển thị | Hiển thị thay đổi |
| Đã stage, working tree không sửa thêm | Không hiển thị | Hiển thị thay đổi | Hiển thị thay đổi |
| Đã stage rồi sửa tiếp | Hiển thị phần sửa thêm | Hiển thị phần đã stage | Hiển thị tổng thay đổi |
| Không có thay đổi | Không hiển thị | Không hiển thị | Không hiển thị |

Bảng này áp dụng cho file được Git theo dõi. File untracked cần được xử lý riêng.

## File untracked có xuất hiện trong git diff không?

Mặc định, không. `git diff` so sánh những đường dẫn mà Git có thể đối chiếu giữa index và working tree. Một file mới chưa được theo dõi chưa có entry bình thường trong index, nên `git diff` không hiển thị nội dung của nó.

Ví dụ:

~~~bash
git status --short
~~~

Kết quả:

~~~text
 M README.md
?? notes.txt
~~~

- `README.md` đã được Git theo dõi và có thay đổi.
- `notes.txt` là file untracked.

`git diff` sẽ hiển thị thay đổi của `README.md`, nhưng không hiển thị nội dung mới của `notes.txt`.

Để bắt đầu theo dõi file mới:

~~~bash
git add notes.txt
~~~

Sau khi stage, file mới được đưa vào index. Khi đó:

~~~bash
git diff --cached -- notes.txt
~~~

hiển thị nội dung sẽ được thêm vào commit tiếp theo.

### Dùng intent-to-add để xem diff của file mới mà chưa stage nội dung

Nếu muốn Git nhận diện đường dẫn mới để hiển thị diff nhưng chưa đưa toàn bộ nội dung vào staging area, có thể dùng:

~~~bash
git add -N notes.txt
git diff -- notes.txt
git diff --cached -- notes.txt
~~~

`git add -N` (intent-to-add) tạo một entry đặc biệt trong index để Git biết đường dẫn sẽ được thêm. Nội dung file vẫn được xem là thay đổi chưa stage; `git diff` có thể hiển thị nội dung mới so với file rỗng. Đây không tương đương với `git add notes.txt` thông thường.

Nếu muốn bỏ entry intent-to-add, có thể dùng:

~~~bash
git restore --staged -- notes.txt
~~~

Sau đó `notes.txt` lại trở thành file untracked. Nếu muốn stage nội dung thực sự, chạy `git add notes.txt`.

## So sánh một file hoặc một nhóm đường dẫn

Không cần xem diff của toàn repository. Bạn có thể chỉ định đường dẫn sau dấu `--`:

~~~bash
git diff -- README.md
git diff -- src/PaymentService.java
git diff -- src/
~~~

Dấu `--` phân tách tùy chọn Git với pathspec. Cách viết này hữu ích khi tên file có thể trùng với tên một tùy chọn hoặc bắt đầu bằng dấu gạch ngang.

Có thể xem nhiều đường dẫn:

~~~bash
git diff -- README.md src/PaymentService.java
~~~

Chỉ xem thống kê thay đổi:

~~~bash
git diff --stat
git diff --stat -- src/
~~~

Chỉ liệt kê tên file:

~~~bash
git diff --name-only
~~~

Liệt kê tên file cùng trạng thái thay đổi:

~~~bash
git diff --name-status
~~~

Một số trạng thái thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `M` | Modified |
| `A` | Added |
| `D` | Deleted |
| `R` | Renamed (khi Git nhận diện được rename) |
| `C` | Copied (khi bật và thỏa điều kiện phát hiện copy) |

Với `git diff` mặc định, file mới chưa stage vẫn là untracked và không xuất hiện. Trạng thái `A` thường hữu ích hơn khi xem diff của index so với HEAD bằng `git diff --cached`.

## Xem thay đổi theo từng dòng hoặc từ ngữ

Khi thay đổi nhỏ trong một dòng dài, diff theo dòng có thể khó đọc. Có thể dùng word diff:

~~~bash
git diff --word-diff
~~~

Hoặc tô màu từ thay đổi:

~~~bash
git diff --color-words
~~~

Giới hạn số dòng ngữ cảnh:

~~~bash
git diff -U1
~~~

Mặc định Git thường hiển thị một số dòng ngữ cảnh trước và sau hunk. Tùy chọn `-U1` giảm xuống một dòng; `-U0` chỉ hiển thị vùng thay đổi, phù hợp khi cần xem nhanh nhưng có thể làm mất bối cảnh.

Word diff hữu ích với Markdown, JSON hoặc dòng cấu hình dài. Với code, hãy luôn đọc đủ bối cảnh để hiểu thay đổi có ảnh hưởng tới logic xung quanh hay không.

## Kiểm tra whitespace và định dạng dòng

Diff có thể giúp phát hiện lỗi khoảng trắng vô tình:

~~~bash
git diff --check
~~~

Lệnh này kiểm tra thay đổi chưa stage để tìm các lỗi whitespace phổ biến như trailing whitespace hoặc whitespace trước tab trong một số ngữ cảnh. Nó không thay thế formatter hoặc linter của dự án.

Kiểm tra phần đã stage:

~~~bash
git diff --cached --check
~~~

Nếu cần xem khác biệt do khoảng trắng:

~~~bash
git diff --ignore-space-change
git diff --ignore-all-space
git diff --ignore-space-at-eol
~~~

Các tùy chọn này chỉ thay đổi cách Git đánh giá/hiển thị khác biệt whitespace trong diff. Chúng không sửa file. Dùng cẩn thận vì có thể che giấu thay đổi có ý nghĩa trong file nhạy với khoảng trắng, chẳng hạn Makefile, YAML hoặc file định dạng đặc thù.

## Khi file bị xóa, đổi mode hoặc di chuyển

### File bị xóa

Nếu xóa một file đã được theo dõi khỏi working tree nhưng chưa stage, `git diff` sẽ hiển thị các dòng bị xóa:

~~~bash
git diff -- src/LegacyPayment.java
~~~

Sau khi stage thao tác xóa:

~~~bash
git add -u
git diff --cached --stat
~~~

Lúc này thay đổi chuyển sang phần staged và không còn xuất hiện trong `git diff` mặc định.

### File đổi executable bit hoặc mode

Git theo dõi một số mode của file. Nếu quyền executable thay đổi và filesystem/Git được cấu hình nhận diện thay đổi đó, diff có thể hiển thị mode khác dù nội dung không đổi.

Ví dụ output:

~~~diff
old mode 100644
new mode 100755
~~~

- `100644`: file thường không executable.
- `100755`: file thường executable.

Kiểm tra cấu hình theo dõi mode:

~~~bash
git config --get core.filemode
~~~

Trên một số filesystem, thay đổi permission có thể không được Git phát hiện như mong đợi. Không nên dựa vào mode hiển thị trên một hệ điều hành để suy luận tuyệt đối về quyền trên hệ điều hành khác.

### File được đổi tên

Git lưu snapshot và tree entry, không lưu một thao tác rename riêng trong commit. Nếu đổi tên file trong working tree mà chưa stage đường dẫn mới, file cũ có thể được xem là đã xóa và file mới là untracked. Vì file mới chưa được theo dõi, `git diff` mặc định có thể chỉ hiển thị phần xóa của file cũ.

Dùng `git status` để xem cả hai đường dẫn. Sau khi stage thay đổi:

~~~bash
git add -A
git diff --cached --summary
git diff --cached --find-renames
~~~

Git có thể suy luận rename từ độ tương đồng nội dung khi trình bày diff. Kết quả nhận diện rename là heuristic; nó không chứng minh trong commit có một thao tác rename riêng.

## File nhị phân và bộ lọc nội dung

Với file nhị phân như ảnh, PDF hoặc archive, Git thường không hiển thị diff theo từng dòng. Bạn có thể thấy thông báo tương tự:

~~~text
Binary files a/assets/logo.png and b/assets/logo.png differ
~~~

Tùy chọn `--text` buộc Git coi nội dung là text để thử tạo diff:

~~~bash
git diff --text -- assets/data.bin
~~~

Không nên dùng `--text` mặc định cho file nhị phân lớn hoặc dữ liệu không phải văn bản; kết quả có thể khó đọc và không có ý nghĩa.

Git attributes và clean/smudge filters cũng có thể ảnh hưởng cách nội dung được chuẩn hóa khi đưa vào index hoặc hiển thị diff. Ví dụ, một file có thể được chuẩn hóa line ending hoặc áp dụng text conversion. Khi diff có vẻ khác với byte thô trên đĩa, kiểm tra:

~~~bash
git check-attr -a -- path/to/file
git config --show-origin --get core.autocrlf
~~~

Không thay đổi cấu hình line ending chỉ để làm diff trông sạch hơn khi chưa hiểu quy ước `.gitattributes` của dự án.

## Các lựa chọn hữu ích của git diff

| Lệnh | Mục đích |
|---|---|
| `git diff` | Working tree so với index |
| `git diff --cached` | Index so với HEAD |
| `git diff --staged` | Alias của `--cached` |
| `git diff HEAD` | Working tree so với HEAD, gồm staged và unstaged |
| `git diff -- path` | Chỉ xem một đường dẫn |
| `git diff --stat` | Thống kê số dòng/file thay đổi |
| `git diff --name-only` | Chỉ in tên file |
| `git diff --name-status` | In tên file và trạng thái |
| `git diff --check` | Kiểm tra whitespace lỗi trong phần diff |
| `git diff -U0` | Không hiển thị dòng ngữ cảnh |
| `git diff --word-diff` | Hiển thị khác biệt theo từ |
| `git diff --ignore-space-change` | Bỏ qua thay đổi số lượng whitespace khi so sánh |
| `git diff --no-ext-diff` | Không dùng external diff driver |
| `git diff --binary` | Tạo diff có thể áp dụng cho thay đổi nhị phân khi dùng trong patch |

Các tùy chọn có thể kết hợp, ví dụ:

~~~bash
git diff --stat -- src/
git diff --cached --name-status
git diff -U0 -- README.md
git diff --check
~~~

### Mã thoát của git diff

Trong script, có thể cần biết diff có thay đổi hay không:

~~~bash
git diff --quiet
~~~

Thông thường:

- Mã thoát `0`: không có khác biệt.
- Mã thoát `1`: có khác biệt.
- Mã thoát lớn hơn `1`: có lỗi khi thực hiện.

Tùy chọn `--exit-code` cũng làm lệnh trả mã thoát khác 0 khi có diff. Điều này hữu ích trong automation, nhưng cần phân biệt “có thay đổi” với “lệnh gặp lỗi”.

Ví dụ trong shell POSIX:

~~~bash
if git diff --quiet; then
  echo "No unstaged changes"
else
  result=$?
  if [ "$result" -eq 1 ]; then
    echo "Unstaged changes exist"
  else
    echo "git diff failed"
    exit "$result"
  fi
fi
~~~

Nếu dùng PowerShell, kiểm tra `$LASTEXITCODE` ngay sau khi chạy Git; `$?` phản ánh trạng thái câu lệnh PowerShell gần nhất và không thay thế đầy đủ mã thoát của chương trình native trong mọi tình huống.

## Quy trình review trước khi commit

Một quy trình có thể dùng hằng ngày:

~~~bash
# 1. Xem tất cả trạng thái file
git status --short

# 2. Xem thay đổi chưa stage
git diff

# 3. Chọn nội dung cần đưa vào commit
git add src/PaymentService.java

# 4. Xem chính xác nội dung đã stage
git diff --cached

# 5. Kiểm tra phần còn chưa stage
git diff

# 6. Kiểm tra whitespace của phần staged
git diff --cached --check

# 7. Xem thống kê commit dự kiến
git diff --cached --stat
~~~

Trước khi commit, hãy đảm bảo:

- Nội dung trong `git diff --cached` đúng với mục tiêu commit.
- Những thay đổi chưa muốn commit vẫn nằm trong `git diff`.
- Không có file nhạy cảm hoặc artifact không mong muốn được stage.
- File untracked đã được xem xét; Git không tự thêm chúng vào commit.
- Các file bị xóa hoặc đổi mode là thay đổi có chủ đích.

Sau khi commit, `git diff --cached` thường rỗng vì index đã khớp với HEAD mới. `git diff` cũng rỗng nếu working tree không còn sửa thêm.

## Thực hành: quan sát index và working tree cùng lúc

Bài tập sau tạo một repository nhỏ để bạn tự kiểm chứng các phép so sánh.

### Bước 1: Tạo repository thử nghiệm

~~~bash
mkdir diff-working-index-lab
cd diff-working-index-lab
git init
git config user.name "Git Learner"
git config user.email "learner@example.test"
~~~

Tạo file `README.md` với nội dung:

~~~text
Payment service
Status: draft
Owner: Platform
~~~

Sau đó commit:

~~~bash
git add README.md
git commit -m "docs: add initial payment readme"
~~~

### Bước 2: Sửa file nhưng chưa stage

Đổi `Status: draft` thành `Status: in review`.

Chạy:

~~~bash
git status --short
git diff
git diff --cached
git diff HEAD
~~~

Kết quả mong đợi:

- `git diff` hiển thị dòng Status thay đổi.
- `git diff --cached` rỗng.
- `git diff HEAD` hiển thị thay đổi.
- `git status` báo file modified chưa stage.

### Bước 3: Stage rồi sửa tiếp

Stage thay đổi hiện tại:

~~~bash
git add README.md
~~~

Sau đó đổi dòng Owner từ `Platform` thành `Developer Experience` mà chưa stage lại.

Chạy:

~~~bash
git diff
git diff --cached
git diff HEAD
~~~

Kết quả mong đợi:

- `git diff` chỉ hiển thị thay đổi Owner mới.
- `git diff --cached` hiển thị thay đổi Status đã stage.
- `git diff HEAD` hiển thị cả thay đổi Status và Owner.

Đây là tình huống chứng minh index giữ snapshot riêng tại thời điểm stage.

### Bước 4: Stage phần còn lại và review

~~~bash
git add README.md
git diff
git diff --cached
git diff --cached --check
git diff --cached --stat
~~~

Kết quả mong đợi: `git diff` rỗng và toàn bộ thay đổi nằm trong `git diff --cached`.

### Bước 5: Tạo file mới và quan sát untracked

Tạo `notes.txt` nhưng chưa stage:

~~~bash
git status --short
git diff
~~~

`notes.txt` xuất hiện trong `git status` với trạng thái untracked, nhưng nội dung không xuất hiện trong `git diff` mặc định.

Stage file:

~~~bash
git add notes.txt
git diff --cached -- notes.txt
~~~

Bây giờ nội dung file mới được hiển thị như phần sẽ được thêm vào commit.

### Bước 6: Bỏ stage mà giữ nội dung file

~~~bash
git restore --staged -- notes.txt
git status --short
~~~

File quay lại trạng thái untracked và nội dung vẫn còn trong working tree. Bỏ stage không đồng nghĩa xóa file.

Nếu muốn đưa file trở lại trạng thái staged, chạy `git add notes.txt`.

## Phân biệt các lệnh khôi phục liên quan tới diff

Các lệnh sau có tác động khác nhau:

~~~bash
# Bỏ stage nhưng giữ nội dung trong working tree
git restore --staged -- README.md

# Khôi phục working tree theo nội dung trong index
git restore --worktree -- README.md

# Khôi phục cả index và working tree theo HEAD
git restore --source=HEAD --staged --worktree -- README.md
~~~

Lưu ý:

- `git restore --staged` chuyển index về trạng thái của nguồn mặc định (thường là HEAD), còn file working tree vẫn giữ nội dung hiện tại.
- `git restore --worktree` ghi đè thay đổi chưa stage bằng nội dung trong index.
- Lệnh cuối có thể làm mất cả thay đổi staged lẫn unstaged của file được chỉ định.

Trước khi dùng lệnh khôi phục có thể ghi đè dữ liệu, hãy xem diff và sao lưu phần cần giữ. Không dùng `git restore` chỉ để làm cho `git diff` rỗng khi chưa xác định nội dung nào cần giữ.

## Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| `git diff` so sánh working tree với commit HEAD | Mặc định nó so sánh working tree với index |
| Stage file làm thay đổi commit hiện tại | Stage chỉ cập nhật index, chưa tạo commit |
| `git diff` hiển thị mọi file mới | File untracked không xuất hiện mặc định |
| `git diff` rỗng nghĩa là repository sạch | Có thể vẫn có staged hoặc untracked file |
| `git diff --cached` là diff của working tree | Nó so sánh index với HEAD |
| Sửa file sau khi stage sẽ tự cập nhật index | Phần sửa sau đó vẫn unstaged cho tới khi stage lại |
| Dòng `+` nghĩa là đã stage | Nó chỉ mô tả dòng có ở phía mới của phép so sánh |
| Git lưu thao tác rename riêng | Git lưu snapshot và suy luận rename khi trình bày diff |
| Bỏ stage là xóa thay đổi | `git restore --staged` giữ nội dung working tree |
| Bỏ qua whitespace luôn an toàn | Có thể che giấu thay đổi có ý nghĩa trong một số định dạng |

## Checklist khi review diff

- [ ] Đã chạy `git status --short` để phân biệt modified, staged và untracked.
- [ ] Đã xem `git diff` để kiểm tra thay đổi chưa stage.
- [ ] Đã xem `git diff --cached` để kiểm tra nội dung sẽ được commit.
- [ ] Đã dùng `git diff HEAD` khi cần xem tổng thay đổi của file được theo dõi.
- [ ] Đã kiểm tra file mới và hiểu rằng untracked không xuất hiện trong diff mặc định.
- [ ] Đã xem từng hunk nếu chỉ stage một phần file.
- [ ] Đã kiểm tra whitespace và mode nếu có thay đổi bất thường.
- [ ] Đã xác nhận không có file nhạy cảm hoặc artifact ngoài ý muốn trong index.
- [ ] Đã sao lưu hoặc xác định rõ dữ liệu trước khi dùng lệnh restore có thể ghi đè.
- [ ] Đã xác nhận index chứa đúng snapshot mong muốn trước khi commit.

## Ghi nhớ

`git diff` mặc định so sánh working tree với index, vì vậy nó hiển thị những thay đổi đã có trong file được theo dõi nhưng chưa stage. `git diff --cached` so sánh index với HEAD để cho biết nội dung đã chọn cho commit tiếp theo. `git diff HEAD` so sánh working tree với commit hiện tại và cho thấy tổng thay đổi staged cùng unstaged của các đường dẫn được theo dõi. File untracked không xuất hiện trong diff mặc định; hãy dùng `git status` để nhận diện và stage chúng khi cần. Trước mỗi commit, kiểm tra cả `git diff` lẫn `git diff --cached` để biết phần nào còn ở working tree và phần nào thực sự nằm trong index.

