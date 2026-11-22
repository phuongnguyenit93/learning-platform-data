# So sánh hai commit, hai nhánh và một đường dẫn cụ thể

Khi review một thay đổi, bạn thường cần trả lời ba câu hỏi: hai commit khác nhau ở nội dung nào, nhánh feature đã thêm gì kể từ khi tách khỏi nhánh chính và một file cụ thể đã thay đổi ra sao. Lệnh **git diff** giúp trả lời các câu hỏi đó bằng cách so sánh snapshot (tree) hoặc so sánh index với working tree.

Điều quan trọng là chọn đúng hai đầu so sánh. `git diff A B` so sánh snapshot của A với B; `git diff A...B` so sánh merge base của A và B với B. Hai cách này trả lời hai câu hỏi khác nhau. Khi chỉ quan tâm một file hoặc thư mục, đặt pathspec sau dấu `--` để giới hạn phạm vi.

## 1. git diff so sánh điều gì?

Git lưu snapshot của dự án trong tree object. Mỗi commit trỏ tới một tree mô tả cấu trúc thư mục và nội dung file tại thời điểm commit.

`git diff` so sánh hai trạng thái để hiển thị phần khác biệt. Nó không so sánh thông điệp commit, tác giả hay thời gian tạo commit; những thông tin đó thuộc metadata lịch sử và được xem bằng các lệnh như `git log` hoặc `git show`.

Ví dụ, hai commit có thể khác nhau ở:

- Nội dung một hoặc nhiều file.
- File được thêm, xóa hoặc đổi tên.
- Bit executable của file.
- Symbolic link hoặc gitlink của submodule.
- Cấu trúc đường dẫn trong tree.

Sơ đồ đơn giản:

```text
Commit A                         Commit B
   |                                |
   v                                v
 Tree A                           Tree B
   |                                |
 README.md: "v1"                 README.md: "v2"
 src/App.java                    src/App.java
 src/Old.java                    src/New.java
   \                                /
    +--------- git diff -----------+
                  |
                  v
       Patch mô tả A -> B
```

Hướng so sánh có ý nghĩa: patch của `git diff A B` mô tả cách biến nội dung ở A thành nội dung ở B. Đổi thứ tự hai đầu so sánh sẽ đảo chiều thay đổi.

## 2. So sánh hai commit bằng OID hoặc tên tham chiếu

Cú pháp cơ bản:

```bash
git diff <commit-A> <commit-B>
```

Ví dụ:

```bash
git diff a1b2c3d e4f5a6b
```

Git so sánh tree của hai commit và in diff. Bạn có thể dùng OID đầy đủ hoặc tên tham chiếu được Git phân giải thành commit như `HEAD`, branch, tag hay biểu thức revision.

Một số ví dụ:

```bash
git diff HEAD~1 HEAD
git diff v1.2.0 v1.3.0
git diff main release/2.x
```

- `HEAD~1` là commit cha thứ nhất của HEAD.
- `v1.2.0` và `v1.3.0` có thể là tag trỏ tới commit hoặc tag object được phân giải về đối tượng đích.
- `main` và `release/2.x` là các tên branch nếu chúng tồn tại trong repository.

Để xem thay đổi do một commit thông thường tạo ra so với commit cha:

```bash
git diff <commit>^ <commit>
```

Hoặc dùng:

```bash
git show <commit>
```

`git show` thường hiển thị metadata commit và diff đi kèm. `git diff` tập trung vào khác biệt giữa hai snapshot.

Với root commit không có parent, không thể dùng `<commit>^`. Có thể xem snapshot ban đầu bằng:

```bash
git show --root <root-commit>
```

## 3. Phân biệt A..B và A...B trong git diff

Đây là điểm rất dễ nhầm khi so sánh branch.

Với `git diff`:

- `git diff A B` so sánh trực tiếp tree của A và tree của B.
- `git diff A..B` có cùng ý nghĩa với `git diff A B`.
- `git diff A...B` so sánh tree tại merge base của A và B với tree của B.

Điều này khác cách `git log` dùng revision range. Trong `git log`, `A..B` thường chọn tập commit reachable từ B nhưng không reachable từ A. Với `git diff`, hai chấm không chọn một tập commit để xuất; nó chỉ là cách viết khác của phép so sánh hai đầu.

### Ví dụ hai branch đã phân kỳ

Giả sử lịch sử:

```text
             F1 --- F2   feature
            /
A --- B --- C --- D      main
```

Hai branch có chung tổ tiên là `C`. `main` đi tiếp tới `D`, còn `feature` có `F1` và `F2`.

So sánh snapshot hiện tại của hai branch:

```bash
git diff main feature
```

Lệnh này hiển thị mọi khác biệt giữa tip của `main` và tip của `feature`. Patch có hướng từ `main` sang `feature`, nên có thể bao gồm cả nội dung đã thay đổi riêng trên `main`.

Nếu muốn xem riêng phần thay đổi mà `feature` đưa vào kể từ điểm phân nhánh:

```bash
git diff main...feature
```

Lệnh này tương đương với so sánh merge base của `main` và `feature` với `feature`. Nó cho thấy thay đổi ở phía feature kể từ khi hai nhánh tách nhau.

Để xem thay đổi phía main kể từ điểm phân nhánh:

```bash
git diff feature...main
```

Ba lệnh trả lời ba câu hỏi khác nhau. Không nên dùng chúng thay thế nhau mà không xác định mục tiêu review.

### Xem merge base trực tiếp

Có thể tìm commit chung gần nhất mà Git chọn làm merge base:

```bash
git merge-base main feature
```

Sau đó so sánh rõ ràng:

```bash
git diff <merge-base-oid> feature
```

Cách này hữu ích khi bạn muốn ghi lại chính xác base được dùng trong review hoặc cần kiểm tra vì sao kết quả diff ba chấm có phạm vi như vậy.

Nếu lịch sử có nhiều merge base tốt nhất, `git merge-base` mặc định có thể chỉ in một kết quả. Với tình huống lịch sử phức tạp, hãy kiểm tra graph và merge base thay vì giả định luôn chỉ có một điểm chung.

## 4. So sánh branch local và remote-tracking branch

Tên branch local có thể chưa phản ánh trạng thái mới nhất trên server. Trước khi review branch với remote, cập nhật remote-tracking refs:

```bash
git fetch origin
```

Sau đó so sánh:

```bash
git diff main origin/main
git diff origin/main...feature/login
```

- Lệnh đầu so sánh snapshot local `main` với snapshot mới nhất đã fetch của `origin/main`.
- Lệnh thứ hai xem phần thay đổi của `feature/login` kể từ merge base với `origin/main`.

Có thể xem danh sách commit riêng biệt trước khi xem diff:

```bash
git log --oneline --left-right --graph origin/main...feature/login
```

`git log` và `git diff` bổ sung cho nhau: log cho biết commit nào khác nhau, diff cho biết nội dung snapshot khác nhau ở đâu.

Nếu remote không tên `origin` hoặc branch chính không tên `main`, thay bằng remote và branch thực tế của dự án.

## 5. So sánh một đường dẫn cụ thể giữa hai commit

Thêm dấu `--` rồi ghi đường dẫn cần giới hạn:

```bash
git diff <commit-A> <commit-B> -- src/App.java
```

Ví dụ:

```bash
git diff main feature/login -- src/auth/Authenticator.java
```

Git chỉ hiển thị khác biệt của đường dẫn đó giữa hai snapshot. Nếu file không tồn tại ở một phía, diff có thể hiển thị toàn bộ nội dung như file được thêm hoặc bị xóa.

Có thể giới hạn cả thư mục:

```bash
git diff main feature/login -- src/auth/
```

Pathspec thư mục thường bao gồm các đường dẫn con. Cách này hữu ích khi review một package hoặc module riêng mà không cần đọc toàn bộ diff.

Đường dẫn tương đối trong pathspec được hiểu từ thư mục làm việc hiện tại. Nếu bạn chạy Git từ một thư mục con, hãy ghi path tương ứng từ vị trí đó hoặc chuyển về root repository trước khi so sánh để tránh lọc nhầm phạm vi.

### Vì sao cần dấu --?

Dấu `--` phân tách revision và tùy chọn ở phía trước với pathspec ở phía sau. Nó tránh việc Git hiểu nhầm tên file thành tên branch hoặc revision.

Ví dụ:

```bash
git diff main feature/login -- README.md
git diff main feature/login -- -notes.txt
```

Nếu đường dẫn bắt đầu bằng dấu gạch ngang, dấu `--` giúp Git nhận diện nó là pathspec. Nếu tên file chứa ký tự glob hoặc ký tự đặc biệt, có thể quote theo shell và dùng pathspec literal:

```bash
git diff main feature/login -- ':(literal)src/[legacy].java'
```

`:(literal)` yêu cầu Git coi phần còn lại là đường dẫn nguyên văn, không diễn giải các ký tự như pattern. Cú pháp quote còn phụ thuộc shell; trên PowerShell, Bash và CMD quy tắc truyền đối số có thể khác nhau.

## 6. So sánh một file với working tree hiện tại

Không phải lúc nào hai đầu so sánh cũng là commit. Nếu chỉ truyền một commit và pathspec, Git so sánh snapshot của commit đó với working tree hiện tại:

```bash
git diff HEAD -- src/App.java
git diff main -- README.md
```

Lệnh đầu cho thấy file `src/App.java` hiện tại khác `HEAD` ra sao, bao gồm thay đổi đã stage và chưa stage. Lệnh thứ hai so sánh `README.md` trong branch `main` với file tương ứng ở working tree hiện tại.

Nếu muốn xem file trong một commit cụ thể mà không so sánh working tree:

```bash
git show <commit>:src/App.java
```

Biểu thức `<commit>:<path>` lấy nội dung blob ở đường dẫn đó trong tree của commit. Lệnh này hiển thị nội dung file, không tạo diff.

## 7. Hiểu đúng ba vùng HEAD, index và working tree

Trong công việc hằng ngày, `git diff` thường được dùng để kiểm tra thay đổi ở ba vùng:

```text
             git diff --cached
      HEAD ----------------------> Index
        \                            |
         \                           | git diff
          \                          v
           --------------------> Working tree
                  git diff HEAD
```

Các lệnh:

| Lệnh | So sánh | Câu hỏi |
|---|---|---|
| `git diff` | Index với working tree | Sau khi stage, tôi còn sửa gì chưa stage? |
| `git diff --cached` hoặc `--staged` | HEAD với index | Tôi đang chuẩn bị commit những gì? |
| `git diff HEAD` | HEAD với working tree | Tổng thể file tracked hiện khác commit hiện tại ra sao? |

Ví dụ:

```bash
git add src/App.java
# Tiếp tục sửa README.md sau khi stage
git diff
git diff --cached
git diff HEAD
```

- `git diff` hiển thị phần sửa mới của `README.md` chưa stage.
- `git diff --cached` hiển thị thay đổi của `src/App.java` đã stage.
- `git diff HEAD` hiển thị cả thay đổi staged và unstaged của các file tracked.

Nếu muốn xem thay đổi staged của riêng một file:

```bash
git diff --cached -- src/App.java
```

Nếu muốn xem thay đổi chưa stage của riêng một file:

```bash
git diff -- src/App.java
```

Những lệnh này giúp review chính xác nội dung sẽ được commit. `git status` chỉ tóm tắt trạng thái; `git diff` cho biết nội dung cụ thể.

## 8. Đọc đầu ra diff

Một unified diff thường có cấu trúc:

```diff
diff --git a/src/App.java b/src/App.java
index 1234567..89abcde 100644
--- a/src/App.java
+++ b/src/App.java
@@ -10,5 +10,6 @@
 public class App {
-    System.out.println("Hello");
+    System.out.println("Hello Git");
+    validateConfig();
 }
```

Các phần chính:

- `diff --git`: bắt đầu phần diff của một đường dẫn.
- `index`: OID blob cũ và mới cùng mode.
- `--- a/...`: phía trước thay đổi.
- `+++ b/...`: phía sau thay đổi.
- `@@ -10,5 +10,6 @@`: vị trí và số dòng của đoạn diff (hunk).
- Dòng bắt đầu bằng dấu cách là context, dấu `-` là nội dung bị bỏ, dấu `+` là nội dung được thêm.

Unified diff thường hiển thị một số dòng context quanh thay đổi. Tăng hoặc giảm số dòng context:

```bash
git diff --unified=0 main...feature/login
git diff -U10 main...feature/login
```

`-U0` chỉ hiển thị dòng thay đổi, còn `-U10` hiển thị 10 dòng context mỗi phía. Context nhiều giúp hiểu logic xung quanh; context ít giúp patch ngắn hơn.

## 9. Chọn dạng output phù hợp khi review hoặc viết script

Không phải lúc nào cũng cần toàn bộ patch. Git cung cấp các chế độ tóm tắt:

| Tùy chọn | Kết quả |
|---|---|
| `--stat` | Bảng thống kê số file và số dòng thêm/xóa |
| `--shortstat` | Một dòng thống kê tổng |
| `--numstat` | Số dòng thêm/xóa theo từng file |
| `--name-only` | Chỉ in tên đường dẫn thay đổi |
| `--name-status` | In trạng thái file như thêm, sửa, xóa, rename |
| `--summary` | Tóm tắt create/delete mode, rename và một số thay đổi metadata |
| `--check` | Kiểm tra lỗi whitespace như trailing whitespace |
| `--word-diff` | Hiển thị thay đổi ở mức từ |
| `--color-moved` | Làm nổi bật các dòng được di chuyển trong diff |

Ví dụ xem tổng quan branch feature:

```bash
git diff --stat main...feature/login
git diff --name-status main...feature/login
git diff --numstat main...feature/login
```

Nếu chỉ cần biết những file nào thay đổi:

```bash
git diff --name-only main...feature/login
```

Nếu cần kiểm tra whitespace trước khi commit:

```bash
git diff --check
git diff --cached --check
```

`--check` hữu ích để phát hiện trailing whitespace hoặc dấu cách không mong muốn. Nó không thay thế formatter hoặc linter của dự án.

### Dùng word diff khi thay đổi nằm trong một dòng dài

Nếu một dòng JSON, tài liệu hoặc câu văn dài chỉ thay một vài từ, diff theo dòng có thể đánh dấu cả dòng là xóa và thêm. Dùng:

```bash
git diff --word-diff
```

Có thể chọn cách đánh dấu:

```bash
git diff --word-diff=plain
git diff --word-diff=color
```

Word diff hữu ích khi review văn bản, nhưng ranh giới từ phụ thuộc cách Git phân tách token. Với mã nguồn, hãy xem cả diff theo dòng để hiểu thay đổi cấu trúc.

## 10. Phát hiện rename và copy

Git không lưu một thao tác rename riêng như metadata bắt buộc trong commit. Khi so sánh hai tree, Git suy luận rename dựa trên độ tương đồng nội dung.

Mặc định, Git diff thường bật rename detection trong các trường hợp phù hợp. Có thể yêu cầu rõ:

```bash
git diff -M main feature/login
```

`-M` bật phát hiện rename. Có thể đặt ngưỡng tương đồng, ví dụ:

```bash
git diff -M90% main feature/login
```

Ngưỡng cao yêu cầu nội dung file cũ và mới giống nhau nhiều hơn để được nhận diện là rename. Có thể bật phát hiện copy:

```bash
git diff -C main feature/login
```

Theo mặc định, copy detection thường chỉ xét các file nguồn đã bị sửa hoặc xóa. Nếu cần tìm file được copy từ một file nguồn vẫn không thay đổi, dùng `--find-copies-harder`; thao tác này tốn thêm công sức vì Git phải xét nhiều file hơn:

```bash
git diff --find-copies-harder -C main feature/login
```

Nếu muốn xem thay đổi dưới dạng xóa và thêm thay vì rename:

```bash
git diff --no-renames main feature/login
```

Kết quả rename/copy là suy luận từ nội dung và ngưỡng phát hiện, không phải bằng chứng duy nhất về ý định của người sửa. Khi review, hãy xem diff thực tế của file mới để xác nhận nội dung được chuyển có đúng không.

## 11. So sánh file khi có thay đổi nhị phân hoặc submodule

Với file văn bản, Git thường hiển thị diff theo dòng. Với file nhị phân, Git thường chỉ báo rằng hai file khác nhau vì không thể trình bày nội dung theo dòng có ý nghĩa.

Có thể xem thống kê:

```bash
git diff --stat <commit-A> <commit-B> -- assets/
```

Nếu cần tạo patch có thể mang dữ liệu nhị phân, dùng `--binary` khi xuất diff:

```bash
git diff --binary <commit-A> <commit-B> > changes.patch
```

Đối với submodule, superproject lưu gitlink trỏ tới commit của repository con. Diff có thể cho biết OID gitlink thay đổi; để xem log commit con giữa hai mốc, dùng:

```bash
git diff --submodule=log <commit-A> <commit-B> -- libs/shared-utils
```

Kết quả phụ thuộc repository con có các commit cần thiết trong local hay không. Nếu chưa có, fetch submodule/repository con theo quy trình của dự án trước khi phân tích sâu.

## 12. Merge commit và so sánh với từng parent

Merge commit có nhiều parent nên câu hỏi “merge đã thêm gì?” cần xác định parent làm mốc so sánh.

Xem danh sách parent:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

So sánh kết quả merge với parent thứ nhất:

```bash
git diff <merge-commit>^1 <merge-commit>
```

So sánh với parent thứ hai:

```bash
git diff <merge-commit>^2 <merge-commit>
```

Hai diff có thể rất khác nhau vì mỗi parent đại diện cho một nhánh trước khi hợp nhất. Nếu muốn hiểu merge đã đưa thay đổi từ nhánh thứ hai vào nhánh thứ nhất ra sao, thường xem diff với parent thứ nhất, đồng thời đọc graph và kiểm tra conflict resolution.

Không nên chỉ xem một diff rồi kết luận toàn bộ merge; merge commit có thể chứa quyết định giải quyết conflict và các thay đổi phát sinh trong quá trình hợp nhất.

## 13. Kiểm tra khác biệt trong script bằng exit code

Mặc định `git diff` in patch và thường trả mã thoát 0 ngay cả khi có khác biệt. Nếu script cần kiểm tra hai trạng thái có khác nhau hay không, dùng `--exit-code` hoặc `--quiet`.

Ví dụ:

```bash
if git diff --quiet main...feature/login; then
  echo "Không có khác biệt"
else
  echo "Có khác biệt hoặc lệnh diff gặp lỗi"
fi
```

`--quiet` không in diff. Mã thoát 0 có nghĩa không có khác biệt; mã thoát 1 có nghĩa có khác biệt. Mã khác có thể biểu thị lỗi, vì vậy script nghiêm túc nên phân biệt mã 1 với lỗi thực thi.

Cách xử lý tường minh trong Bash:

```bash
git diff --quiet main...feature/login
rc=$?

case "$rc" in
  0) echo "Không có khác biệt" ;;
  1) echo "Có khác biệt" ;;
  *) echo "Không thể so sánh" >&2; exit "$rc" ;;
esac
```

Nếu shell bật `set -e`, lệnh trả mã 1 có thể làm script dừng trước khi đọc `$?`. Hãy đặt lệnh trong điều kiện `if` hoặc xử lý mã thoát theo cấu trúc shell phù hợp.

Nếu muốn in diff nhưng vẫn dùng exit code:

```bash
git diff --exit-code main...feature/login
```

Lệnh trả mã 1 khi có khác biệt. Đây là hành vi có ích trong CI, nhưng hãy cấu hình job để hiểu rằng mã 1 ở đây là “có diff”, không nhất thiết là lỗi Git.

## 14. Tránh làm sai kết quả khi bỏ qua whitespace

Git cho phép bỏ qua một số khác biệt whitespace:

```bash
git diff -w main feature/login
git diff --ignore-space-at-eol main feature/login
```

`-w` bỏ qua khác biệt về whitespace khi so sánh nội dung; `--ignore-space-at-eol` bỏ qua whitespace ở cuối dòng.

Những tùy chọn này có thể giúp review một thay đổi chỉ định dạng, nhưng cũng có thể che khác biệt có ý nghĩa trong một số file. Ví dụ, khoảng trắng có thể ảnh hưởng Makefile, YAML, Python hoặc chuỗi literal. Không dùng diff bỏ qua whitespace làm bằng chứng duy nhất rằng hai phiên bản tương đương.

Có thể đổi thuật toán diff để dễ đọc các thay đổi đã di chuyển hoặc tái cấu trúc:

```bash
git diff --patience main...feature/login
git diff --histogram main...feature/login
```

Các thuật toán này thay đổi cách Git ghép các dòng context/hunk, không thay đổi nội dung hai tree đang được so sánh.

## 15. Quy trình review một branch feature

Giả sử bạn cần review `feature/login` trước khi hợp nhất vào `main`.

**Bước 1: Fetch thông tin mới nhất.**

```bash
git fetch origin
```

**Bước 2: Xác định commit và merge base.**

```bash
git log --oneline --left-right --graph origin/main...feature/login
git merge-base origin/main feature/login
```

**Bước 3: Xem phạm vi thay đổi mà feature đưa vào.**

```bash
git diff --stat origin/main...feature/login
git diff --name-status origin/main...feature/login
```

**Bước 4: Đọc diff của từng khu vực quan trọng.**

```bash
git diff origin/main...feature/login -- src/auth/
git diff origin/main...feature/login -- tests/
git diff origin/main...feature/login -- README.md
```

**Bước 5: Kiểm tra whitespace và xác minh test.**

```bash
git diff --check origin/main...feature/login
```

Chạy test bằng lệnh của dự án và kiểm tra kết quả CI. Diff giúp review nội dung thay đổi; nó không chứng minh logic đã đúng hoặc test đã chạy thành công.

**Bước 6: Nếu cần xem khác biệt giữa hai tip hiện tại**, dùng:

```bash
git diff origin/main feature/login
```

Đây là phép so sánh snapshot cuối của hai branch, hữu ích khi muốn biết toàn bộ trạng thái của chúng khác nhau thế nào. Nó khác với phạm vi thay đổi riêng của feature kể từ merge base.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `git diff A..B` cho kết quả không như `git log A..B` | Hai lệnh có semantics revision khác nhau | Với diff, `A..B` tương đương so sánh A với B |
| `git diff main feature` hiển thị cả thay đổi riêng của main | Đang so sánh hai tip snapshot | Dùng `git diff main...feature` nếu muốn xem phía feature từ merge base |
| Diff ba chấm không hiển thị thay đổi phía main | Ba chấm so merge base với đầu thứ hai | Đảo thứ tự thành `git diff feature...main` |
| File cụ thể không được tìm thấy | Pathspec sai hoặc Git hiểu tên thành revision | Dùng dấu `--`, kiểm tra đường dẫn và quote theo shell |
| Diff không hiển thị commit mới | Diff so sánh tree, không liệt kê commit | Dùng `git log` để xem commit; dùng `git diff` để xem nội dung snapshot |
| Không thấy thay đổi local đã stage | Đang dùng `git diff` mặc định | Dùng `git diff --cached` hoặc `git diff HEAD` |
| Rename hiện thành delete/add | Rename detection không nhận ra đủ độ tương đồng | Thử `-M`, kiểm tra ngưỡng hoặc xem nội dung hai file |
| File nhị phân chỉ báo khác nhau | Git không thể trình bày diff theo dòng | Dùng `--stat` hoặc `--binary` khi cần patch |
| Script coi có diff là lỗi Git | Không phân biệt exit code 1 với mã lỗi | Xử lý riêng mã 0, 1 và các mã khác |
| Diff bỏ qua khác biệt quan trọng | Dùng `-w` hoặc tùy chọn ignore whitespace | Xem lại diff đầy đủ, đặc biệt với file nhạy whitespace |

## 17. Checklist trước khi kết luận hai phiên bản khác nhau

- [ ] Đã xác định hai commit/ref thực sự muốn so sánh.
- [ ] Đã fetch remote nếu dùng remote-tracking branch.
- [ ] Đã chọn so sánh tip-to-tip hay merge-base-to-branch.
- [ ] Đã phân biệt semantics của `A..B` và `A...B` trong `git diff`.
- [ ] Đã dùng `--` trước pathspec.
- [ ] Đã kiểm tra riêng file hoặc thư mục quan trọng.
- [ ] Đã xem staged và unstaged changes nếu đang review working tree.
- [ ] Đã đọc diff đầy đủ trước khi dùng tùy chọn bỏ qua whitespace.
- [ ] Đã hiểu exit code nếu diff được gọi từ script hoặc CI.
- [ ] Đã kiểm tra merge parent nếu đang review merge commit.

## Kết luận

Dùng `git diff A B` để so sánh trực tiếp hai snapshot; `git diff A..B` có cùng ý nghĩa đó. Dùng `git diff A...B` để so sánh merge base của A và B với B, thường phù hợp khi review phần thay đổi của một branch kể từ lúc tách nhánh. Thêm `-- path` để giới hạn một file hoặc thư mục, dùng `--cached` để xem nội dung đã stage và chọn `--stat`, `--name-status`, `--check` hoặc `--word-diff` theo mục tiêu. Trước khi kết luận, hãy xác định rõ hai đầu so sánh và hướng patch mà Git đang hiển thị.
