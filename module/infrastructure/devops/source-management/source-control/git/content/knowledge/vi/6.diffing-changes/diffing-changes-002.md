# So sánh chỉ mục với HEAD bằng git diff --staged

Trước khi tạo commit, bạn cần biết chính xác những thay đổi nào đã được đưa vào staging area. Lệnh `git diff --staged` cho biết phần khác biệt giữa index và commit hiện tại (HEAD). Đây là bước review quan trọng: nó cho thấy snapshot mà commit tiếp theo sẽ ghi nhận đối với các file đã stage.

Lệnh này thường được dùng sau `git add` hoặc `git add -p`. Bạn có thể kiểm tra từng dòng đã chọn, phát hiện file stage nhầm, xem thống kê, kiểm tra lỗi whitespace và xuất patch để chia sẻ. Hiểu đúng chiều so sánh cũng giúp bạn không nhầm nội dung đã stage với phần sửa tiếp trong working tree.

Sau bài này, bạn có thể:

- Giải thích chính xác `git diff --staged` so sánh hai vùng nào.
- Phân biệt staged diff, unstaged diff và diff tổng thể so với HEAD.
- Giới hạn diff theo file hoặc thư mục.
- Đọc unified diff và nhận biết dòng thêm, xóa, ngữ cảnh, mode và rename.
- Dùng thống kê và các tùy chọn kiểm tra trước commit.
- Xem thay đổi theo từ, kiểm tra whitespace và xuất patch.
- Kết hợp diff với staging chọn lọc để tạo commit đúng phạm vi.

## 1. HEAD, index và working tree

Git có ba trạng thái cần phân biệt khi review thay đổi:

- **HEAD** thường trỏ tới commit hiện tại, tức snapshot gần nhất trên branch đang checkout.
- **Index** (staging area) chứa phiên bản file đã được chọn cho commit tiếp theo.
- **Working tree** là nội dung file hiện có trên đĩa mà bạn đang chỉnh sửa.

Luồng thường gặp:

~~~text
                 git add
Working tree ----------------> Index
     |                           |
     | git diff                  | git diff --staged
     v                           v
  Index                         HEAD
                                  ^
                                  |
                               git commit
~~~

Ba phép so sánh tương ứng:

| Lệnh | So sánh | Câu hỏi |
| --- | --- | --- |
| `git diff` | Working tree với index | Tôi đã sửa thêm gì nhưng chưa stage? |
| `git diff --staged` | Index với HEAD | Những gì đã stage sẽ đi vào commit là gì? |
| `git diff HEAD` | Working tree với HEAD | Tổng thay đổi tracked hiện tại so với commit gần nhất là gì? |

Thứ tự hai phía trong phép so sánh ảnh hưởng đến hướng của diff. Với `git diff --staged`, Git hiển thị cách index khác với HEAD: dòng thêm là nội dung có trong index nhưng chưa có trong HEAD; dòng xóa là nội dung có trong HEAD nhưng không còn trong index.

## 2. Chạy git diff --staged

Lệnh cơ bản:

~~~bash
git diff --staged
~~~

`--staged` là tên dễ đọc của tùy chọn `--cached`. Hai lệnh sau tương đương:

~~~bash
git diff --staged
git diff --cached
~~~

Nếu không chỉ định commit để so sánh, Git dùng HEAD làm mốc. Nói cách khác, lệnh cho thấy snapshot trong index sẽ thay đổi thế nào so với commit hiện tại.

Ví dụ, sau khi stage một thay đổi:

~~~bash
git add src/Search.java
git diff --staged
~~~

Git in phần diff của `src/Search.java` giữa nội dung đã stage và phiên bản trong HEAD. Nếu file có sửa đổi tiếp sau khi stage, các sửa đổi tiếp đó chưa xuất hiện trong lệnh này; chúng thuộc phép so sánh `git diff`.

`git diff --staged` chỉ xem các đường dẫn được Git theo dõi trong index. File untracked không tự xuất hiện trong diff. Muốn đưa file mới vào staged diff, trước hết phải stage file bằng `git add`.

## 3. Ví dụ: một file có cả thay đổi staged và unstaged

Giả sử `src/Search.java` ban đầu trả về kết quả trực tiếp. Bạn sửa file để chuẩn hóa query, rồi stage:

~~~bash
git add src/Search.java
~~~

Sau đó bạn tiếp tục sửa file để xử lý thêm giá trị null nhưng chưa stage lần hai.

Lúc này:

~~~bash
git diff --staged
git diff
git status --short
~~~

- `git diff --staged` hiển thị thay đổi đã được stage ở lần `git add` trước.
- `git diff` hiển thị phần chỉnh sửa mới trong working tree so với index.
- `git status --short` có thể hiển thị `MM` ở file đó: cột thứ nhất là thay đổi trong index, cột thứ hai là thay đổi trong working tree.

Nếu tạo commit ngay, Git ghi phiên bản trong index. Phần sửa null chưa stage vẫn ở working tree sau commit. Đây là lý do cần đọc cả staged diff lẫn unstaged diff trước khi commit khi bạn đã chỉnh sửa tiếp sau khi stage.

## 4. Chỉ định commit khác làm mốc so sánh

Có thể truyền một commit hoặc ref sau tùy chọn:

~~~bash
git diff --staged HEAD
git diff --staged origin/main
git diff --staged abc1234
~~~

Nếu bỏ đối số, Git mặc định dùng HEAD. Nếu chỉ định `origin/main`, Git so sánh index với remote-tracking branch local đó. Lệnh không tự fetch remote; ref chỉ phản ánh dữ liệu mà repository đang có.

Điều này hữu ích khi bạn muốn xem snapshot đã stage khác gì so với một branch cơ sở trước khi tạo commit hoặc khi chuẩn bị nội dung để chuyển sang nhánh khác.

Nếu repository chưa có commit đầu tiên, HEAD chưa phân giải thành commit. Git có thể trình bày các entry đã stage như những file mới so với cây rỗng. Trường hợp này thường gặp ngay sau khi khởi tạo repository và stage nội dung đầu tiên.

## 5. Giới hạn diff theo file hoặc thư mục

Nếu chỉ muốn review một file:

~~~bash
git diff --staged -- src/Search.java
~~~

Hoặc giới hạn theo thư mục:

~~~bash
git diff --staged -- src/
~~~

Dấu `--` tách tùy chọn khỏi pathspec. Nên dùng dấu phân cách này để tên file không bị hiểu nhầm là option. Có thể truyền nhiều pathspec:

~~~bash
git diff --staged -- src/Search.java README.md
~~~

Pathspec cho phép dùng mẫu theo cú pháp Git. Khi viết script, cần quote mẫu theo shell hiện tại để shell không tự mở rộng glob trước khi Git nhận được.

Lưu ý: nếu file chưa được stage hoặc không có entry phù hợp trong index, nó không xuất hiện trong staged diff chỉ vì bạn truyền đường dẫn. Dùng `git status` hoặc `git ls-files` để xác nhận file có trong index.

## 6. Đọc unified diff

Một đoạn diff điển hình:

~~~diff
diff --git a/src/Search.java b/src/Search.java
index 12ab345..67cd890 100644
--- a/src/Search.java
+++ b/src/Search.java
@@ -10,7 +10,7 @@ public class Search {
-    return query;
+    return normalize(query);
 }
~~~

Ý nghĩa các thành phần:

- `diff --git` chỉ ra đường dẫn phía cũ và phía mới.
- `index` hiển thị OID cũ và mới cùng file mode.
- `---` là file phía cũ; `+++` là file phía mới.
- Dòng bắt đầu bằng `@@` là header của một hunk, cho biết vị trí và phạm vi dòng.
- Dòng bắt đầu bằng dấu cách là ngữ cảnh, tồn tại ở cả hai phía.
- Dòng bắt đầu bằng `-` có trong phiên bản cũ nhưng bị loại khỏi phiên bản mới.
- Dòng bắt đầu bằng `+` được thêm vào phiên bản mới.

Header hunk như `@@ -10,7 +10,7 @@` mô tả vùng dòng được hiển thị ở hai phía. Số dòng và số lượng có thể khác nhau nếu thay đổi thêm hoặc xóa dòng.

Diff là mô tả thay đổi nội dung, không phải bản sao nguyên trạng của file. Dòng ngữ cảnh được đưa vào để giúp người review hiểu vị trí thay đổi và giúp patch có cơ sở áp dụng.

## 7. Xem thống kê thay vì toàn bộ nội dung

Khi staged diff lớn, bạn có thể xem tổng quan trước:

~~~bash
# Số dòng thêm/xóa theo file
git diff --staged --stat

# Một dòng tổng kết
git diff --staged --shortstat

# Dạng số liệu phù hợp để xử lý bằng script
git diff --staged --numstat
~~~

Ví dụ output của `--stat`:

~~~text
 src/Search.java | 8 ++++----
 README.md       | 4 ++++
 2 files changed, 7 insertions(+), 5 deletions(-)
~~~

`--numstat` thường cho mỗi file số dòng thêm, số dòng xóa và đường dẫn. Với file binary, số liệu dòng có thể hiển thị dấu gạch ngang thay vì số dòng.

Liệt kê tên file:

~~~bash
git diff --staged --name-only
~~~

Liệt kê tên file kèm trạng thái:

~~~bash
git diff --staged --name-status
~~~

Một số mã trạng thái thường thấy là `A` (thêm), `M` (sửa), `D` (xóa), `R` (rename) và `C` (copy) khi Git nhận diện được các trường hợp đó.

Git suy luận rename/copy dựa trên mức độ tương đồng nội dung khi tạo diff; rename không được lưu như một thao tác rename riêng trong commit tree. Vì thế kết quả nhận diện có thể phụ thuộc ngưỡng và tùy chọn rename detection.

## 8. Kiểm tra whitespace trước commit

Một số lỗi khoảng trắng dễ bị bỏ qua khi review:

- Khoảng trắng ở cuối dòng.
- Dòng mới bị thiếu ở cuối file.
- Dòng chứa khoảng trắng chỉ có whitespace.

Dùng:

~~~bash
git diff --staged --check
~~~

Lệnh kiểm tra các lỗi whitespace mà Git nhận diện trong thay đổi staged. Nó không in diff thông thường; thay vào đó có thể báo vị trí có vấn đề. Lệnh trả mã thoát khác 0 khi phát hiện lỗi whitespace.

Có thể kết hợp với quy trình review:

~~~bash
git diff --staged --check
git diff --staged
~~~

`--check` không thay thế formatter, linter hoặc quy tắc định dạng của dự án. Nó chỉ phát hiện một số loại lỗi whitespace. Hãy chạy công cụ chất lượng phù hợp nếu repository có quy định riêng.

## 9. Xem thay đổi theo từ thay vì theo dòng

Với tài liệu hoặc dòng văn bản dài, diff theo dòng có thể làm khó nhận ra một từ được sửa. Dùng:

~~~bash
git diff --staged --word-diff
~~~

Hoặc chọn cách đánh dấu từ:

~~~bash
git diff --staged --word-diff=color
~~~

Word diff giúp nhận diện từ hoặc đoạn ký tự được thêm/xóa trong cùng một dòng. Cách phân tách từ phụ thuộc cấu hình và nội dung; nó hữu ích để review văn bản, nhưng với code có cấu trúc phức tạp, diff theo dòng thường vẫn dễ hiểu hơn.

Có thể dùng regex để xác định đơn vị so sánh:

~~~bash
git diff --staged --word-diff-regex='[[:alnum:]_]+'
~~~

Ví dụ này coi chuỗi chữ/số và dấu gạch dưới là đơn vị từ. Chọn regex phù hợp với ngôn ngữ hoặc định dạng đang review.

## 10. Điều chỉnh lượng ngữ cảnh

Unified diff mặc định hiển thị một số dòng ngữ cảnh quanh thay đổi. Muốn tăng hoặc giảm số dòng:

~~~bash
# Hiển thị 5 dòng ngữ cảnh
git diff --staged -U5

# Chỉ hiển thị dòng thay đổi, không có ngữ cảnh
git diff --staged -U0
~~~

Nhiều dòng ngữ cảnh giúp hiểu luồng code, nhưng output dài hơn. Không có ngữ cảnh giúp tập trung vào thay đổi, nhưng có thể khiến người review khó xác định vị trí hoặc ý nghĩa.

Khi review logic, thường nên giữ ngữ cảnh mặc định hoặc tăng thêm. Khi xuất dữ liệu máy đọc hoặc so sánh chính xác vùng thay đổi, có thể giảm ngữ cảnh nếu công cụ tiêu thụ patch cho phép.

## 11. Thay đổi file mode, rename và binary

Không phải mọi thay đổi đều là thêm/xóa dòng:

- File có thể chuyển giữa mode executable và non-executable.
- File có thể bị xóa hoặc thêm.
- Git có thể nhận diện một cặp xóa/thêm là rename dựa trên độ tương đồng.
- File binary có thể không tạo ra unified text diff đọc được.

Dùng:

~~~bash
git diff --staged --summary
git diff --staged --raw
~~~

`--summary` hiển thị thông tin tổng quan như create, delete, mode change hoặc rename khi được nhận diện. `--raw` hiển thị thông tin ở dạng thấp hơn, gồm mode và OID.

Nếu cần xuất patch có dữ liệu binary:

~~~bash
git diff --staged --binary > staged-changes.patch
~~~

Patch này có thể được áp dụng bằng Git ở repository khác nếu trạng thái cơ sở phù hợp. Đừng chỉ nhìn diff văn bản rồi kết luận không có thay đổi binary; hãy kiểm tra thống kê và trạng thái file.

## 12. Diff không bao gồm file untracked

Một file mới chưa được stage không thuộc index, vì vậy không xuất hiện trong:

~~~bash
git diff --staged
~~~

Ngay cả `git diff HEAD` cũng không tự thêm nội dung file untracked vào output. Trước tiên, bạn cần quyết định file đó có thuộc commit hay không.

Ví dụ:

~~~bash
# Xem file mới chưa được theo dõi
git status --short

# Stage file nếu muốn đưa vào commit
git add docs/new-guide.md

# Xem nội dung file mới đã stage
git diff --staged -- docs/new-guide.md
~~~

Nếu chỉ muốn xem nội dung file mới mà chưa stage, hãy mở file hoặc dùng công cụ diff ngoài Git. Có thể dùng `git diff --no-index` để so sánh hai file hoặc file với một nội dung khác, nhưng đó là phép so sánh riêng, không phải staged diff của repository.

## 13. Dùng exit code trong script

Khi tích hợp diff vào script, có thể dùng `--exit-code`:

~~~bash
git diff --staged --exit-code
~~~

Exit code:

- `0` nếu không có khác biệt.
- `1` nếu có khác biệt.
- Giá trị lớn hơn 1 thường biểu thị lỗi thực thi hoặc lỗi khác.

Nếu chỉ cần kiểm tra có diff hay không mà không cần in nội dung:

~~~bash
git diff --staged --quiet
~~~

`--quiet` không in output và ngụ ý hành vi exit-code. Script cần phân biệt “có khác biệt” với “lệnh bị lỗi”; không nên coi mọi mã khác 0 là cùng một trạng thái.

Ví dụ shell:

~~~bash
if git diff --staged --quiet; then
    echo "No staged changes."
else
    result=$?
    if [ "$result" -eq 1 ]; then
        echo "Staged changes are present."
    else
        echo "git diff failed with exit code $result."
        exit "$result"
    fi
fi
~~~

Trong script phức tạp, hãy kiểm tra lỗi repository, pathspec và quyền truy cập riêng; exit code giúp phân biệt không có thay đổi với trường hợp lệnh không thể hoàn tất.

## 14. Kết hợp staged diff với staging chọn lọc

Bạn không nhất thiết phải stage toàn bộ file. `git add -p` cho phép chọn từng hunk:

~~~bash
git add -p src/Search.java
~~~

Sau đó review phần đã chọn:

~~~bash
git diff --staged
git diff
~~~

Nếu staged diff chứa thay đổi không thuộc commit hiện tại, bạn có thể bỏ stage file hoặc hunk rồi chọn lại:

~~~bash
# Bỏ stage toàn bộ file nhưng giữ nguyên working tree
git restore --staged src/Search.java
~~~

Sau đó chọn lại hunk bằng `git add -p` và kiểm tra staged diff lần nữa.

Với Git cũ hơn không hỗ trợ `git restore`, có thể dùng:

~~~bash
git reset HEAD -- src/Search.java
~~~

Lệnh này cập nhật index về HEAD cho path được chọn, giữ thay đổi trong working tree. Hãy hiểu trạng thái hiện tại trước khi dùng, nhất là khi index đã có nội dung stage mà bạn muốn giữ.

## 15. Quy trình review trước khi commit

Một quy trình an toàn:

~~~bash
# 1. Xem tổng quan
git status

# 2. Xem thay đổi đã stage
git diff --staged

# 3. Kiểm tra whitespace trong phần sẽ commit
git diff --staged --check

# 4. Xem file và thống kê
git diff --staged --name-status
git diff --staged --stat

# 5. Xem thay đổi còn chưa stage
git diff

# 6. Tạo commit sau khi xác nhận phạm vi
git commit
~~~

Trước khi commit, tự kiểm tra:

- Có file nào bị stage nhầm không?
- Có file cần thiết nào còn untracked hoặc chưa stage không?
- Có phần sửa tiếp nào nằm trong working tree nhưng chưa được đưa vào index không?
- Có thay đổi xóa, đổi mode hoặc rename nào dễ bị bỏ sót không?
- Có whitespace error nào cần sửa không?
- Thông điệp commit có mô tả đúng staged diff không?

Nếu commit cần chỉ chứa một phần thay đổi, hãy quay lại staging chọn lọc thay vì commit một snapshot rộng hơn dự kiến.

## 16. Xuất staged diff thành patch

Để chia sẻ các thay đổi đã stage dưới dạng patch:

~~~bash
git diff --staged > staged-changes.patch
~~~

Nếu có file binary:

~~~bash
git diff --staged --binary > staged-changes.patch
~~~

Patch được tạo từ staged diff mô tả phần khác biệt giữa index và HEAD. Nó không tạo commit và không tự chứa đầy đủ metadata commit như author, committer hoặc thông điệp. Nếu cần chuyển commit cùng metadata, hãy tìm hiểu `git format-patch` và `git am`.

Người nhận cần có trạng thái cơ sở phù hợp để áp dụng patch. Có thể kiểm tra trước bằng `git apply --check staged-changes.patch` rồi mới áp dụng bằng `git apply`.

## 17. Những lỗi thường gặp

### Chạy git diff --staged nhưng không thấy file vừa sửa

File có thể chưa được stage, hoặc thay đổi mới nằm trong working tree sau lần stage trước. Dùng `git status` và `git diff` để kiểm tra.

### Nghĩ git diff --staged hiển thị mọi thay đổi chưa commit

Không đúng. Lệnh chỉ so sánh index với HEAD. Thay đổi chưa stage cần xem bằng `git diff`; tổng thay đổi tracked so với HEAD có thể xem bằng `git diff HEAD`.

### File untracked không xuất hiện trong diff

Đó là hành vi bình thường. Stage file bằng `git add` nếu muốn nó thuộc commit.

### Stage file rồi sửa tiếp nhưng tưởng commit sẽ chứa mọi thay đổi

Commit lấy snapshot từ index. Phần sửa sau lần stage cuối không tự động đi vào commit. Hãy đọc cả `git diff --staged` và `git diff`.

### Dùng --stat rồi cho rằng đã review nội dung

Thống kê chỉ cho biết số file và số dòng thay đổi. Hãy mở full diff cho các thay đổi cần review logic.

### Dùng --check rồi cho rằng code đã đúng

`--check` chỉ kiểm tra một số lỗi whitespace. Nó không chạy test, compiler, formatter hoặc linter.

### Nhầm rename detection là thao tác rename được lưu trong commit

Git lưu snapshot tree. Rename thường được suy luận khi hiển thị diff dựa trên mức độ tương đồng giữa file cũ và mới.

## 18. Ghi nhớ

- `git diff --staged` và `git diff --cached` là hai cách gọi tương đương.
- Mặc định, staged diff so sánh index với HEAD.
- `git diff` so sánh working tree với index; `git diff HEAD` so sánh working tree với HEAD.
- Commit tiếp theo lấy snapshot từ index, không lấy trực tiếp mọi nội dung đang có trên đĩa.
- Dùng pathspec để giới hạn file, `--stat` hoặc `--name-status` để xem tổng quan, và full diff để review nội dung.
- Dùng `--check` để phát hiện một số lỗi whitespace trước commit.
- Dùng `--word-diff` cho văn bản dài, `-U<n>` để điều chỉnh ngữ cảnh.
- File untracked không xuất hiện trong staged diff cho tới khi được stage.
- Dùng `--exit-code` hoặc `--quiet` trong script và phân biệt exit code có diff với lỗi thực thi.
- Review cả staged và unstaged diff trước khi commit nếu đã chỉnh sửa file sau khi stage.

`git diff --staged` là bước kiểm tra trực tiếp snapshot đã chuẩn bị trong index so với HEAD. Khi kết hợp nó với `git status`, `git diff` và các tùy chọn thống kê/kiểm tra, bạn có thể xác nhận commit chỉ chứa những thay đổi dự định, phát hiện phần còn thiếu hoặc stage nhầm, và tạo lịch sử Git dễ review hơn.
