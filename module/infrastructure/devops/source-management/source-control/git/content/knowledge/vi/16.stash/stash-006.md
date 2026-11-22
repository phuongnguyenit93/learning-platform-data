# Khôi phục trạng thái chỉ mục bằng `stash apply --index`

Khi đang làm việc, ta có thể vừa stage một phần thay đổi để chuẩn bị commit, vừa tiếp tục chỉnh sửa những phần khác trong working tree. Nếu cần chuyển sang xử lý việc khẩn cấp hoặc đổi nhánh, `git stash` có thể cất tạm trạng thái hiện tại. Khi quay lại, tùy chọn `--index` giúp khôi phục cả trạng thái đã stage trong staging area, bên cạnh nội dung working tree.

Điểm cần phân biệt là **nội dung file** và **trạng thái của nội dung trong index**. Một file có thể chứa phần đã stage và phần chỉnh sửa mới chưa stage. Khi chỉ chạy `git stash apply`, Git áp dụng lại thay đổi nhưng không cố khôi phục chính xác trạng thái staging ban đầu. Với `git stash apply --index`, Git cố gắng phục hồi cả hai phần để những gì đã stage trước đó tiếp tục nằm trong index, còn phần chưa stage vẫn ở working tree.

Trong dịch vụ quản lý mã nguồn Git, hiểu rõ index rất quan trọng vì commit chỉ ghi nhận nội dung đã stage. Khôi phục đúng trạng thái index giúp tiếp tục công việc mà không vô tình đưa phần chưa hoàn tất vào commit hoặc phải stage lại thủ công từng thay đổi.

## 1. Phân biệt HEAD, index và working tree

Trước khi dùng `--index`, cần hiểu ba vùng trạng thái chính trong một repository:

| Vùng | Vai trò | Lệnh xem thay đổi |
| --- | --- | --- |
| `HEAD` | Commit hiện tại của nhánh đang đứng | `git show --stat HEAD` |
| Index (staging area) | Nội dung sẽ được đưa vào commit tiếp theo | `git diff --cached` |
| Working tree | Nội dung file hiện có trong thư mục làm việc | `git diff` |

Ví dụ, ta sửa `PaymentService.java`, stage một phần thay đổi rồi tiếp tục sửa phần còn lại:

```bash
# Sửa lần đầu, sau đó đưa phần này vào index
git add src/main/java/example/PaymentService.java

# Tiếp tục chỉnh sửa file sau khi đã stage
# Phần sửa mới nằm trong working tree, chưa được stage

git status --short
git diff --cached
git diff
```

Trong kết quả `git status --short`, hai cột trạng thái thể hiện hai vùng khác nhau:

```text
MM src/main/java/example/PaymentService.java
```

Ký tự thứ nhất `M` cho biết nội dung trong index khác `HEAD`; ký tự thứ hai `M` cho biết working tree khác index. Như vậy, file đang có cả thay đổi đã stage và thay đổi chưa stage. Đây là trạng thái mà `git stash apply --index` cần khôi phục chính xác.

Nếu chỉ thấy:

```text
M  src/main/java/example/PaymentService.java
```

thì thay đổi đang nằm trong index và working tree hiện khớp với index. Nếu thấy:

```text
 M src/main/java/example/PaymentService.java
```

thì file có thay đổi chưa stage so với index.

## 2. Stash lưu những gì?

Lệnh cơ bản:

```bash
git stash push -m "WIP: payment validation"
```

Git lưu tạm các thay đổi tracked trong index và working tree rồi đưa working tree về trạng thái sạch theo commit hiện tại. Thông điệp sau `-m` giúp nhận diện mục đích của stash trong danh sách.

Theo mặc định, file chưa được Git theo dõi (untracked) không được đưa vào stash. Nếu cần cất cả file untracked, dùng `-u` hoặc `--include-untracked`; nếu cần cất cả file bị ignore, dùng `-a` hoặc `--all`:

```bash
git stash push -u -m "WIP including new test files"
git stash push -a -m "WIP including ignored build output"
```

Chỉ dùng `-a` khi thật sự muốn cất các file ignored, vì chúng có thể bao gồm cấu hình local, cache hoặc dữ liệu sinh tự động. Tùy chọn `--index` khi apply quyết định việc khôi phục trạng thái staging; nó không thay đổi quy tắc chọn file được lưu vào stash.

### Stash giữ lại thông tin index như thế nào?

Về mặt cấu trúc, một stash thông thường ghi nhận trạng thái working tree và có tham chiếu tới snapshot index riêng. Sơ đồ dưới đây chỉ minh họa hai snapshot, không biểu diễn thứ tự parent của các commit:

```text
                 W  snapshot working tree
                / \
HEAD (H) ------    I  snapshot index
```

Về cấu trúc commit, `W` có hai parent: parent thứ nhất là `H`, parent thứ hai là `I`; commit `I` cũng có `H` làm parent. `H` là commit `HEAD` tại thời điểm tạo stash; `I` ghi lại trạng thái đã stage; `W` ghi lại trạng thái working tree. Điều quan trọng khi sử dụng là stash có đủ thông tin để Git cố gắng phục hồi phần staged riêng với phần unstaged.

Kiểm tra stash đã lưu:

```bash
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
```

`stash@{0}` là stash mới nhất; `stash@{1}` là mục kế tiếp, v.v. Dùng dấu nháy đơn quanh tên tham chiếu giúp câu lệnh hoạt động ổn định trong PowerShell, nơi cú pháp `@{...}` có ý nghĩa riêng.

## 3. Khôi phục bằng `git stash apply --index`

Sau khi đã stash, có thể chuyển sang nhánh khác hoặc xử lý công việc khác. Khi quay lại đúng nhánh và muốn khôi phục cả trạng thái index lẫn working tree, chạy:

```bash
git stash apply --index 'stash@{0}'
```

Nếu không truyền tên stash, Git mặc định áp dụng stash mới nhất:

```bash
git stash apply --index
```

`--index` yêu cầu Git cố gắng khôi phục cả trạng thái staging đã được lưu trong stash. Sau khi áp dụng thành công:

- Phần thay đổi đã stage trước khi stash sẽ trở lại index.
- Phần thay đổi chưa stage trước khi stash sẽ trở lại working tree.
- Nội dung file phản ánh trạng thái làm việc trước khi stash, trong phạm vi các thay đổi có thể áp dụng sạch lên `HEAD` hiện tại.

Kiểm tra trạng thái sau khi apply:

```bash
git status --short
git diff --cached
git diff
```

`git diff --cached` cho biết phần được khôi phục trong index; `git diff` cho biết phần còn lại trong working tree. Không chỉ nhìn nội dung file rồi kết luận đã khôi phục đúng: hai phần staged và unstaged có thể cùng nằm trong một file, nên cần kiểm tra cả hai lệnh diff.

### So sánh `apply` thông thường và `apply --index`

Giả sử trước khi stash, file có một phần sửa đã stage và một phần sửa chưa stage:

| Thao tác | Nội dung file sau khi áp dụng | Trạng thái index |
| --- | --- | --- |
| `git stash apply` | Cố gắng khôi phục thay đổi trong stash | Không cố phục hồi trạng thái staging ban đầu; thay đổi thường được đưa về dạng chưa stage |
| `git stash apply --index` | Cố gắng khôi phục thay đổi trong stash | Cố gắng khôi phục cả phần đã stage và phần chưa stage như lúc tạo stash |

Ví dụ:

```bash
git stash apply 'stash@{0}'
```

Lệnh này áp dụng thay đổi nhưng không yêu cầu khôi phục trạng thái index. Nếu cần tiếp tục đúng cách chia phần staged/unstaged ban đầu, dùng `--index` ngay từ đầu hoặc stage lại thủ công sau khi xem diff.

## 4. Quy trình đầy đủ: stage một phần, stash rồi khôi phục index

Thực hiện trên một repository thử nghiệm hoặc nhánh cá nhân để quan sát kết quả.

### Bước 1: Tạo cả thay đổi staged và unstaged

Sửa một file tracked, sau đó stage phần thay đổi đầu tiên:

```bash
git add src/main/java/example/PaymentService.java
```

Tiếp tục sửa file hoặc một file khác nhưng chưa stage phần mới. Kiểm tra:

```bash
git status --short
git diff --cached
git diff
```

Lưu ý: nếu muốn cùng một file có cả thay đổi staged và unstaged, hãy chỉnh sửa file, stage trạng thái đầu tiên, rồi tiếp tục chỉnh sửa file lần nữa. Không chạy `git add` lần thứ hai trước khi tạo stash nếu mục tiêu là giữ riêng hai lớp thay đổi.

### Bước 2: Cất trạng thái

```bash
git stash push -m "WIP: separate staged and unstaged changes"
```

Sau khi lệnh thành công, kiểm tra:

```bash
git status -sb
git stash list
```

Working tree tracked thường trở về sạch. Nếu còn file untracked, hãy nhớ rằng mặc định stash không bao gồm chúng; nếu cần, phải tạo stash có `-u` hoặc lưu riêng.

### Bước 3: Làm việc khác rồi quay lại nhánh ban đầu

Có thể chuyển nhánh và xử lý một việc khác:

```bash
git switch main
# thực hiện công việc khác và commit nếu cần
git switch feature/payment
```

Trước khi apply, kiểm tra nhánh hiện tại và trạng thái repository:

```bash
git branch --show-current
git status -sb
```

Để khôi phục chính xác hơn, nên áp dụng stash trên nhánh và nền commit tương ứng với lúc stash được tạo, với working tree sạch. Nếu nhánh đã thay đổi đáng kể, Git có thể gặp xung đột hoặc không thể phục hồi index như cũ.

### Bước 4: Áp dụng stash kèm trạng thái index

```bash
git stash apply --index 'stash@{0}'
```

Nếu thành công, kiểm tra hai vùng riêng:

```bash
git status --short
git diff --cached
git diff
```

So sánh kết quả với trạng thái trước khi stash. Phần đã stage phải nằm trong index; phần chưa stage phải nằm trong working tree.

### Bước 5: Chỉ xóa stash sau khi xác minh

`git stash apply` giữ nguyên stash trong danh sách, kể cả khi áp dụng thành công. Điều này cho phép ta kiểm tra hoặc áp dụng lại nếu cần. Sau khi đã xác minh nội dung và trạng thái index, nếu chắc chắn không cần bản lưu nữa, có thể xóa mục cụ thể:

```bash
git stash drop 'stash@{0}'
```

Không nên xóa stash ngay sau khi apply mà chưa kiểm tra kết quả. Nếu còn nghi ngờ hoặc đang chờ review, cứ giữ stash để có điểm khôi phục.

## 5. Dùng `git stash pop --index`

`pop` kết hợp áp dụng stash và xóa stash khỏi danh sách khi việc áp dụng thành công:

```bash
git stash pop --index 'stash@{0}'
```

Khác với `apply`, `pop` hướng tới việc dùng stash một lần. Nếu áp dụng thành công, Git xóa mục stash tương ứng. Nếu phát sinh xung đột hoặc thao tác không hoàn tất, Git giữ stash lại để ta có thể xử lý và thử lại.

Nên chọn:

- `git stash apply --index` khi muốn giữ bản stash cho đến khi tự kiểm tra và quyết định xóa.
- `git stash pop --index` khi đã sẵn sàng áp dụng và bỏ stash sau khi thành công.

Trong quy trình cần kiểm soát trạng thái index, `apply --index` thường dễ kiểm tra hơn vì bản lưu vẫn còn nguyên trong danh sách sau khi áp dụng.

## 6. Vì sao `--index` có thể không khôi phục được?

`--index` yêu cầu Git phục hồi hai lớp trạng thái, nên có những tình huống không thể áp dụng tự động.

### Nhánh hiện tại đã thay đổi cùng nội dung

Nếu file trên nhánh hiện tại đã được sửa sau khi tạo stash, patch trong stash có thể xung đột với thay đổi mới. Git có thể không áp dụng được một phần hoặc toàn bộ patch.

### Trạng thái index hiện tại không tương thích

Index có thể chứa thay đổi khác, hoặc đang ở trạng thái unmerged do một thao tác giải quyết xung đột trước đó. Trong tình huống này, Git không thể dễ dàng tái lập snapshot index cũ. Trước khi apply, kiểm tra `git status` và hoàn tất hoặc lưu riêng công việc đang có.

### Một file có cả staged và unstaged edits

Đây là tình huống hợp lệ và thường là lý do ta cần `--index`, nhưng cũng là trường hợp dễ phát sinh xung đột khi nội dung trên nhánh đích đã thay đổi. Git phải khôi phục phần đã stage và phần chưa stage theo đúng thứ tự; nếu các patch không còn áp dụng được, thao tác có thể dừng.

### Stash được tạo trên nền commit khác

Stash được tạo từ một `HEAD` cụ thể. Nếu áp dụng lên nhánh đã thay đổi cấu trúc file, đổi tên file hoặc chỉnh sửa cùng khu vực, Git phải hòa giải các khác biệt. Có thể cần quay về nhánh gốc, cập nhật nền phù hợp hoặc giải quyết xung đột thủ công.

### Stash không chứa file cần khôi phục

File untracked hoặc ignored không được đưa vào stash mặc định. `--index` không thể khôi phục nội dung chưa từng được lưu trong stash. Kiểm tra cách tạo stash và dùng `-u` hoặc `-a` cho lần lưu tiếp theo nếu cần.

## 7. Xử lý khi `stash apply --index` gặp xung đột

Khi áp dụng stash bị xung đột, trước tiên đọc trạng thái:

```bash
git status
```

Git sẽ liệt kê file chưa hòa giải. Mở từng file, chọn nội dung đúng, xóa dấu phân cách conflict nếu có rồi stage kết quả:

```bash
git add src/main/java/example/PaymentService.java
```

Sau khi stage file đã giải quyết, kiểm tra lại:

```bash
git status --short
git diff --cached
git diff
```

Không có lệnh `git stash apply --continue` như một phiên rebase. Khi apply dừng, ta xử lý trạng thái file và index trực tiếp. Stash gốc vẫn còn trong danh sách, vì vậy không cần tạo lại stash để giữ bản lưu.

Nếu cần hủy một lần apply đang dở, Git không cung cấp lệnh `git stash apply --abort` tương tự rebase. Cách xử lý phụ thuộc trạng thái trước khi apply. Nếu trước đó working tree sạch và chưa tạo thêm công việc, có thể khôi phục các file bị tác động bằng cách phù hợp sau khi kiểm tra kỹ. Tránh chạy `git reset --hard` hoặc `git clean` theo thói quen vì chúng có thể xóa các thay đổi chưa được lưu. Khi có dữ liệu quan trọng, hãy tạo bản sao hoặc stash trạng thái hiện tại trước khi thực hiện thao tác khôi phục.

Sau khi giải quyết xong, xác minh phần staged/unstaged. Nếu cần thử lại từ stash ban đầu, có thể quay về trạng thái an toàn rồi chạy lại `git stash apply --index` với đúng stash.

## 8. Kiểm tra chính xác trạng thái index sau khi khôi phục

Để xác nhận khôi phục đúng, không chỉ xem `git status` tổng quát. Hãy dùng cả hai lệnh diff:

```bash
# Những gì đã stage so với HEAD
git diff --cached

# Những gì chưa stage so với index
git diff
```

Nếu muốn xem tên file và trạng thái ngắn:

```bash
git status --short
```

Nếu cần so sánh chính xác với snapshot trước stash, có thể xem nội dung stash:

```bash
git stash show -p 'stash@{0}'
```

Lệnh này cho thấy thay đổi trong stash so với nền của nó. Để hiểu riêng trạng thái index, cần xem commit index của stash hoặc dùng các lệnh Git plumbing phù hợp; trong công việc hằng ngày, việc đối chiếu `git diff --cached`, `git diff` và trạng thái trước khi stash thường đủ để xác nhận.

Một checklist ngắn sau khi apply:

1. Đúng nhánh đã nhận stash.
2. Không có file conflict chưa giải quyết.
3. Các thay đổi vốn đã stage xuất hiện trong `git diff --cached`.
4. Các thay đổi vốn chưa stage xuất hiện trong `git diff`.
5. File untracked/ignored cần thiết đã được lưu bằng cách phù hợp.
6. Stash gốc vẫn còn cho đến khi xác nhận không cần nữa.

## 9. Một số lệnh stash liên quan

| Lệnh | Công dụng |
| --- | --- |
| `git stash push -m "message"` | Lưu thay đổi tracked trong index và working tree với mô tả |
| `git stash push -u -m "message"` | Lưu thêm file untracked |
| `git stash push -a -m "message"` | Lưu cả file ignored |
| `git stash list` | Liệt kê các stash hiện có |
| `git stash show -p 'stash@{0}'` | Xem patch của một stash |
| `git stash apply --index 'stash@{0}'` | Áp dụng stash và cố gắng khôi phục trạng thái index |
| `git stash pop --index 'stash@{0}'` | Áp dụng stash kèm index và xóa mục stash nếu thành công |
| `git stash drop 'stash@{0}'` | Xóa một mục stash cụ thể |
| `git stash clear` | Xóa tất cả stash trong repository |

`git stash clear` có phạm vi rộng và có thể khiến các thay đổi chỉ còn được giữ trong stash khó phục hồi. Không dùng lệnh này để dọn dẹp khi chưa xác nhận các mục đều không còn cần thiết.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `git stash apply` luôn khôi phục phần đã stage | Muốn Git cố gắng khôi phục index, cần dùng `--index` |
| `--index` chỉ khôi phục nội dung file | Nó yêu cầu khôi phục cả trạng thái index đã lưu, ngoài working tree |
| Apply thành công sẽ xóa stash | `apply` giữ stash; `pop` mới xóa mục khi áp dụng thành công |
| Stash mặc định chứa mọi file mới | File untracked cần `-u`; file ignored cần `-a` |
| `--index` bảo đảm khôi phục thành công trong mọi trường hợp | Đây là nỗ lực phục hồi index; conflict hoặc trạng thái index hiện tại có thể khiến thao tác thất bại |
| Chỉ cần xem `git status` là đủ | Nên kiểm tra cả `git diff --cached` và `git diff` để phân biệt hai vùng |
| Có thể dùng `git stash apply --abort` | Không có tùy chọn này; apply không có quy trình abort riêng như rebase |

## 11. Thực hành

Thực hiện trên repository thử nghiệm:

1. Tạo hoặc sửa một file tracked, sau đó stage một phần thay đổi.
2. Tiếp tục sửa file để tạo thêm phần chưa stage; dùng `git status --short`, `git diff --cached` và `git diff` để xác nhận hai phần tách biệt.
3. Chạy `git stash push -m "test staged and unstaged"`.
4. Xác nhận working tree sạch và stash xuất hiện trong `git stash list`.
5. Quay lại đúng nhánh và chạy `git stash apply --index 'stash@{0}'`.
6. Dùng `git status --short`, `git diff --cached` và `git diff` để xác nhận phần staged và unstaged đã trở lại đúng vùng.
7. Sau khi trạng thái đã được khôi phục, stash lại lần nữa với thông điệp khác rồi thử `git stash apply` không có `--index` để so sánh trạng thái staging.
8. Sau khi xác minh, xóa đúng các stash thử nghiệm bằng `git stash drop 'stash@{0}'` theo thứ tự mới nhất trước; giữ lại các stash khác nếu có.
9. Thử thêm file untracked và quan sát khác biệt giữa `git stash push` và `git stash push -u`.

Sau thực hành, hãy giải thích vì sao cùng một file có thể có đồng thời staged và unstaged changes, vì sao `--index` cần thiết khi muốn phục hồi cách chia phần đó, và vì sao nên dùng `apply` trước khi quyết định xóa stash.

## 12. Tự kiểm tra kiến thức

1. Index khác working tree ở điểm nào?
2. Khi một file có cả staged và unstaged changes, `git status --short` thường hiển thị trạng thái như thế nào?
3. `git stash push` lưu những loại thay đổi nào theo mặc định?
4. `git stash apply` khác `git stash apply --index` như thế nào?
5. Vì sao `--index` có thể thất bại khi nhánh hiện tại đã thay đổi cùng file?
6. Sau khi apply thành công, dùng lệnh nào để xem phần staged và phần unstaged riêng biệt?
7. `git stash pop --index` khác `git stash apply --index` ở vòng đời stash ra sao?
8. Nếu apply gặp conflict, vì sao không thể dùng `git stash apply --abort`?
9. Cần dùng tùy chọn nào để lưu file untracked hoặc ignored?
10. Khi nào nên drop stash đã áp dụng?

## Kết luận

`git stash apply --index` giúp khôi phục thay đổi đã cất tạm và yêu cầu Git phục hồi cả trạng thái staging ban đầu. Sau khi áp dụng, hãy kiểm tra `git diff --cached` và `git diff` để xác nhận phần đã stage và chưa stage nằm đúng vùng. Vì việc phục hồi index có thể gặp xung đột khi nhánh hoặc file đã thay đổi, nên giữ stash cho tới khi xác minh hoàn tất; chỉ drop khi chắc chắn không còn cần bản lưu.
