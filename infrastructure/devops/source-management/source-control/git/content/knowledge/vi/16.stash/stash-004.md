# Chỉ lưu một phần thay đổi với --patch, --staged và --keep-index

Trong quá trình phát triển, có lúc bạn đang làm dở nhiều việc nhưng chỉ cần tạm cất một phần để chuyển sang xử lý nhiệm vụ khác. Ví dụ, bạn đã sửa xong một phần và staging để chuẩn bị commit, nhưng vẫn còn vài dòng thử nghiệm chưa hoàn chỉnh. Hoặc bạn chỉ muốn cất riêng một số đoạn trong cùng một tệp mà không ảnh hưởng đến những đoạn còn lại.

Lệnh `git stash` có thể lưu tạm thay đổi để working tree trở nên phù hợp với công việc tiếp theo. Ngoài cách cất toàn bộ thay đổi, Git còn hỗ trợ chọn một phần bằng `--patch`, chỉ cất nội dung đã staging bằng `--staged`, hoặc giữ phần đã staging trong working tree trong khi cất phần chưa staging bằng `--keep-index`.

Ba tùy chọn này giải quyết những nhu cầu khác nhau. Hiểu rõ chúng giúp bạn chuyển ngữ cảnh làm việc mà không làm mất phần việc đang dang dở hoặc vô tình đưa nội dung không liên quan vào commit.

## 1. Ôn lại working tree và staging area

Trước khi dùng stash một phần, cần phân biệt nội dung trong working tree và index.

| Khu vực | Nội dung | Lệnh kiểm tra |
| --- | --- | --- |
| HEAD | Commit hiện tại của nhánh | `git log --oneline -5` |
| Index (staging area) | Nội dung đã chọn để đưa vào commit tiếp theo | `git diff --cached` |
| Working tree | Nội dung tệp hiện có trên đĩa | `git diff` |

Ví dụ, bạn sửa hai tệp:

- `src/PaymentService.java`: đã staging phần kiểm tra dữ liệu đầu vào.
- `docs/payment-flow.md`: đang sửa dở nhưng chưa staging.

Kiểm tra:

~~~bash
git status
git diff --cached
git diff
~~~

`git diff --cached` hiển thị phần khác biệt giữa index và HEAD. `git diff` hiển thị phần khác biệt giữa working tree và index. Một tệp có thể đồng thời chứa cả thay đổi staged và unstaged nếu bạn tiếp tục chỉnh sửa sau khi chạy `git add`.

Khi muốn tạm cất một phần, cần xác định chính xác phần nào sẽ được lưu vào stash và phần nào phải tiếp tục nằm trong working tree.

## 2. Cú pháp cơ bản của stash

Cú pháp thông dụng:

~~~bash
git stash push -m "Mo ta cong viec"
~~~

Lệnh này lưu các thay đổi tracked đang có trong index và working tree vào một stash entry, rồi đưa chúng ra khỏi working tree theo hành vi mặc định.

Xem danh sách stash:

~~~bash
git stash list
~~~

Xem nội dung stash mới nhất:

~~~bash
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
~~~

Mỗi stash entry có thể được tham chiếu bằng tên như `stash@{0}`, `stash@{1}`. `stash@{0}` là entry mới nhất. Khi tạo stash mới, chỉ số các entry cũ có thể thay đổi.

Mặc định, stash không bao gồm tệp chưa được Git theo dõi. Nếu cần cất cả các tệp đó, dùng `-u` hoặc `--include-untracked`. Tùy chọn `-a` hoặc `--all` còn bao gồm cả tệp bị ignore. Hãy cân nhắc kỹ trước khi đưa tệp cấu hình hoặc dữ liệu cục bộ vào stash.

## 3. Chọn từng phần thay đổi với --patch

### 3.1. --patch hoạt động như thế nào?

Tùy chọn `--patch` cho phép chọn từng hunk (đoạn thay đổi) để đưa vào stash:

~~~bash
git stash push --patch -m "Tam cat mot phan thay doi"
~~~

Git mở chế độ tương tác và lần lượt hỏi bạn muốn cất từng hunk hay không. Bạn có thể quyết định giữ hunk nào trong stash và để hunk nào tiếp tục ở working tree.

Một số phím thường dùng trong màn hình tương tác:

| Phím | Ý nghĩa |
| --- | --- |
| `y` | Cất hunk hiện tại |
| `n` | Không cất hunk hiện tại |
| `s` | Chia hunk thành các phần nhỏ hơn nếu có thể |
| `e` | Chỉnh sửa patch thủ công trước khi áp dụng |
| `q` | Thoát chế độ tương tác |
| `?` | Xem trợ giúp các lựa chọn |

Tùy phiên bản Git và tình huống, danh sách lựa chọn có thể khác. Hãy đọc phần hướng dẫn hiển thị ngay trong terminal trước khi nhập.

Sau khi hoàn tất, các hunk được chọn được lưu vào stash và được loại khỏi working tree. Các hunk không chọn vẫn còn lại.

### 3.2. Ví dụ chọn một số hunk trong cùng tệp

Giả sử bạn đang sửa `src/PaymentService.java` với ba thay đổi, và cả ba hunk hiện đều chưa được staging:

1. Thêm kiểm tra mã thanh toán rỗng — đã hoàn chỉnh.
2. Thử nghiệm một cách ghi log mới — chưa hoàn chỉnh.
3. Điều chỉnh tên biến — chưa quyết định.

Bạn cần tạm cất riêng phần ghi log để tiếp tục xử lý nhiệm vụ khác. Chạy:

~~~bash
git stash push --patch -m "Tam cat phan thu nghiem ghi log"
~~~

Khi Git hỏi từng hunk:

- Chọn `n` với phần kiểm tra mã thanh toán để giữ lại trong working tree.
- Chọn `y` với phần ghi log để đưa vào stash.
- Chọn `n` với phần đổi tên biến nếu muốn giữ nó ở working tree.

Sau đó kiểm tra:

~~~bash
git status
git diff
git stash list
git stash show -p 'stash@{0}'
~~~

Kết quả mong đợi là hunk ghi log nằm trong stash, còn các hunk không chọn vẫn còn trong working tree. Đừng chỉ dựa vào thông báo thành công; hãy xem diff để xác nhận đúng nội dung đã được cất.

### 3.3. --patch mặc định giữ index

`git stash push --patch` ngầm bật `--keep-index`. Điều đó có nghĩa trạng thái index được giữ lại trong khi các hunk được chọn được lưu tạm. Nếu cần hành vi không giữ index, có thể dùng `--no-keep-index` để ghi đè mặc định này:

~~~bash
git stash push --patch --no-keep-index -m "Tam cat mot phan"
~~~

Với người mới, nên dùng mặc định trước và kiểm tra `git status`, `git diff --cached` cùng `git diff` sau thao tác. Chỉ dùng `--no-keep-index` khi đã hiểu rõ cách thay đổi staged và unstaged sẽ được xử lý.

### 3.4. Chọn hunk từ phần đã staging

Có thể kết hợp `--patch` với `--staged` để tương tác chọn phần trong những thay đổi đã staging:

~~~bash
git stash push --staged --patch -m "Tam cat mot phan da staging"
~~~

Cách này hữu ích khi bạn đã staging nhiều thay đổi nhưng chỉ muốn tạm cất một số hunk. Hãy đọc từng lựa chọn trong màn hình tương tác và kiểm tra lại index sau khi hoàn tất.

## 4. Chỉ cất các thay đổi đã staging với --staged

### 4.1. --staged làm gì?

Tùy chọn `--staged` chỉ đưa những thay đổi đã có trong index vào stash:

~~~bash
git stash push --staged -m "Tam cat phan da staging"
~~~

Các thay đổi chưa staging trong working tree được giữ lại. Tùy chọn này phù hợp khi bạn đã chọn một phần nội dung để chuẩn bị commit nhưng muốn tạm cất chính phần đó, ví dụ để chuyển sang xử lý một việc khẩn cấp.

`--staged` có từ Git 2.35. Nếu phiên bản Git của bạn không nhận tùy chọn này, hãy kiểm tra:

~~~bash
git --version
git stash push -h
~~~

Với phiên bản cũ, có thể dùng các cách khác như stash theo pathspec hoặc tạm staging/chuyển nội dung theo quy trình phù hợp.

### 4.2. Ví dụ: cất phần đã staging, giữ phần chưa staging

Giả sử bạn sửa cùng một tệp:

- Phần A: sửa điều kiện kiểm tra thanh toán và đã chạy `git add`.
- Phần B: thêm log chẩn đoán nhưng chưa muốn commit.

Kiểm tra trước:

~~~bash
git status
git diff --cached
git diff
~~~

Chỉ cất phần staged:

~~~bash
git stash push --staged -m "Tam cat phan validation da staging"
~~~

Sau đó kiểm tra:

~~~bash
git status
git diff
git diff --cached
git stash show -p 'stash@{0}'
~~~

Phần đã staging được lưu vào stash. Phần chưa staging tiếp tục nằm trong working tree để bạn có thể chỉnh sửa hoặc commit theo mục đích khác. Nếu một tệp có cả nội dung staged và unstaged, hãy kiểm tra riêng `git diff --cached` và `git diff` sau lệnh để xác nhận hai phần được giữ đúng như mong muốn.

Khi khôi phục stash, có thể cần dùng `--index` để phục hồi trạng thái staging ban đầu. Xem phần khôi phục bên dưới.

### 4.3. Phân biệt --staged với --keep-index

Hai tùy chọn này thường bị nhầm vì đều liên quan đến index, nhưng mục đích ngược nhau:

- `--staged`: cất phần đã staging vào stash; phần chưa staging được giữ lại.
- `--keep-index`: giữ phần đã staging tại chỗ; cất phần chưa staging vào stash.

Hãy xác định phần nào cần tạm cất trước khi chọn tùy chọn. Nếu chọn nhầm, nội dung vẫn có thể nằm trong stash hoặc working tree nhưng không ở đúng trạng thái bạn mong đợi.

## 5. Giữ phần đã staging với --keep-index

### 5.1. --keep-index làm gì?

Tùy chọn `--keep-index` giữ các thay đổi đã staging trong index và working tree, đồng thời stash các thay đổi chưa staging:

~~~bash
git stash push --keep-index -m "Tam cat phan chua staging"
~~~

Đây là cách phổ biến khi bạn muốn kiểm thử riêng phần đã staging trước khi commit. Các thay đổi chưa staging được cất đi để không ảnh hưởng đến lần chạy kiểm thử.

Nếu cùng một tệp có cả thay đổi staged và unstaged, `--keep-index` giữ phiên bản đã staging trong index và working tree; phần chênh lệch chưa staging được cất vào stash. Sau lệnh, `git diff --cached` cho biết phần sẽ được commit, còn `git diff` giúp xác nhận không còn phần sửa chưa staging ngoài dự kiến.

Ví dụ:

1. Sửa nhiều phần trong dự án.
2. Stage đúng các tệp hoặc hunk muốn commit.
3. Stash phần chưa staging với `--keep-index`.
4. Chạy test trên trạng thái còn lại.
5. Khôi phục stash để tiếp tục phần việc chưa hoàn chỉnh.

### 5.2. Ví dụ kiểm thử phần đã staging

Giả sử bạn đang làm hai việc:

- Sửa logic xác thực thanh toán và đã staging.
- Thêm log để điều tra lỗi, chưa staging.

Xem trạng thái:

~~~bash
git status
git diff --cached
git diff
~~~

Cất phần chưa staging nhưng giữ phần đã staging:

~~~bash
git stash push --keep-index -m "Tam cat log dang thu nghiem"
~~~

Giờ working tree còn phần đã staging. Chạy test:

~~~bash
./gradlew test
~~~

Lệnh test chỉ là ví dụ cho dự án Gradle; hãy dùng lệnh kiểm thử phù hợp với repository thực tế.

Nếu test thành công, bạn có thể commit phần đã staging:

~~~bash
git commit -m "Validate payment request"
~~~

Sau đó khôi phục phần việc đang cất:

~~~bash
git stash pop
~~~

Nếu test thất bại, bạn vẫn có thể sửa phần đã staging hoặc xem lại diff. Stash của phần chưa staging vẫn được lưu riêng để khôi phục sau.

### 5.3. --keep-index không phải là commit

`--keep-index` không tạo commit và cũng không làm cho phần staged trở thành một phiên bản đã chia sẻ. Nó chỉ giữ nội dung trong index và working tree để bạn tiếp tục làm việc hoặc kiểm thử.

Nếu muốn lưu lại mốc lịch sử, hãy tạo commit sau khi kiểm tra. Stash là nơi cất tạm, không thay thế commit có thông điệp và lịch sử rõ ràng.

## 6. So sánh ba tùy chọn

| Tùy chọn | Phần được cất | Phần được giữ lại | Cách chọn |
| --- | --- | --- | --- |
| `--patch` | Các hunk được chọn tương tác | Hunk không chọn; index được giữ mặc định | Chọn từng đoạn thay đổi |
| `--staged` | Nội dung đã staging | Nội dung chưa staging trong working tree | Cất phần đã chọn để commit |
| `--keep-index` | Nội dung chưa staging | Nội dung đã staging trong index và working tree | Giữ phần chuẩn bị commit để kiểm thử |

Một cách ghi nhớ:

- Muốn tự chọn từng đoạn: dùng `--patch`.
- Muốn cất phần đã staging: dùng `--staged`.
- Muốn giữ phần đã staging và cất phần còn lại: dùng `--keep-index`.

Không nên kết hợp nhiều tùy chọn chỉ vì muốn “stash một phần”. Hãy xác định mục tiêu và dùng tổ hợp được Git hỗ trợ. `--staged` có thể kết hợp với `--patch`; `--patch` mặc định ngụ ý `--keep-index`, và có thể ghi đè bằng `--no-keep-index`.

## 7. Chỉ cất thay đổi của một số tệp với pathspec

Ngoài chọn theo hunk, Git cho phép giới hạn stash theo đường dẫn:

~~~bash
git stash push -m "Tam cat tai lieu thanh toan" -- docs/payment-flow.md
~~~

Lệnh chỉ cất thay đổi thuộc `docs/payment-flow.md`. Các tệp khác không nằm trong pathspec tiếp tục ở working tree.

Có thể chỉ định nhiều đường dẫn:

~~~bash
git stash push -m "Tam cat hai tep" -- src/PaymentService.java docs/payment-flow.md
~~~

Pathspec có thể kết hợp với `--patch` để giới hạn những tệp được hỏi tương tác:

~~~bash
git stash push --patch -m "Chon mot phan trong tep" -- src/PaymentService.java
~~~

Hãy dùng dấu `--` trước pathspec để phân biệt rõ tùy chọn và tên tệp, đặc biệt khi tên đường dẫn có thể bắt đầu bằng dấu gạch ngang.

## 8. Xem và khôi phục stash một phần

### 8.1. Liệt kê và kiểm tra nội dung

~~~bash
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'
~~~

`git stash show -p` hiển thị diff của stash để bạn xác nhận nội dung được cất. Nếu có nhiều stash, hãy chọn đúng entry theo thông điệp và thời điểm tạo, không mặc định rằng `stash@{0}` luôn là công việc bạn cần khôi phục.

### 8.2. Khôi phục bằng apply

~~~bash
git stash apply 'stash@{0}'
~~~

`apply` áp dụng thay đổi từ stash vào working tree nhưng giữ entry trong danh sách. Đây là lựa chọn phù hợp khi bạn muốn kiểm tra kết quả trước khi quyết định xóa stash.

Để thử khôi phục cả trạng thái index đã lưu:

~~~bash
git stash apply --index 'stash@{0}'
~~~

Tùy chọn `--index` yêu cầu Git cố gắng phục hồi cả trạng thái staging. Nếu có xung đột hoặc thay đổi hiện tại không tương thích, thao tác có thể không hoàn tất như mong muốn. Kiểm tra `git status` và diff sau khi áp dụng.

### 8.3. Khôi phục bằng pop

~~~bash
git stash pop 'stash@{0}'
~~~

`pop` áp dụng stash và xóa entry khỏi danh sách nếu áp dụng thành công. Nếu xảy ra xung đột, stash thường được giữ lại để bạn có thể tiếp tục xử lý và thử lại.

Không nên dùng `pop` khi chưa chắc entry nào đang được chọn hoặc khi bạn muốn giữ bản stash để đối chiếu. Khi cần an toàn, dùng `apply`, kiểm tra kết quả, rồi mới `drop`.

### 8.4. Xóa stash sau khi xác nhận

Xem danh sách:

~~~bash
git stash list
~~~

Xóa một entry cụ thể:

~~~bash
git stash drop 'stash@{0}'
~~~

Lệnh này xóa tham chiếu đến stash entry được chỉ định. Chỉ chạy sau khi bạn chắc chắn thay đổi đã được khôi phục hoặc không còn cần thiết. Tránh dùng `git stash clear` theo thói quen vì nó xóa toàn bộ danh sách stash.

## 9. Xử lý xung đột khi áp dụng stash

Stash được tạo ở một trạng thái repository trước đó. Nếu bạn đã sửa cùng các dòng trên nhánh hiện tại, khi áp dụng stash Git có thể không tự kết hợp được.

Quy trình xử lý:

1. Xem trạng thái bằng `git status`.
2. Mở các tệp conflict và chọn nội dung đúng.
3. Stage tệp đã giải quyết bằng `git add`.
4. Chạy test và kiểm tra diff.
5. Giữ hoặc xóa stash theo kết quả áp dụng.

Ví dụ:

~~~bash
git stash apply 'stash@{0}'
git status
~~~

Nếu có xung đột, giải quyết từng tệp rồi kiểm tra:

~~~bash
git diff
git diff --cached
git status
~~~

Nếu đã dùng `apply`, entry vẫn còn trong danh sách. Nếu dùng `pop` và có conflict, Git thường giữ entry để bạn không mất bản lưu tạm.

Khi stash có phần staged và bạn muốn giữ lại trạng thái đó, cân nhắc `git stash apply --index`. Nếu chỉ cần lấy nội dung về working tree và sẽ tự staging lại, dùng `apply` thông thường rồi kiểm tra cẩn thận.

## 10. Các giới hạn cần nhớ

- **Stash là lưu tạm trong repository local:** nó không tự gửi lên remote và không thay thế backup hoặc commit.
- **Tệp chưa được theo dõi không được lưu mặc định:** dùng `-u` nếu muốn đưa chúng vào stash; `-a` bao gồm cả tệp ignored.
- **Patch chỉ chọn được thay đổi Git nhận diện:** tệp nhị phân hoặc tệp chưa được theo dõi không phù hợp với việc chọn hunk văn bản thông thường.
- **Các tùy chọn có thể ảnh hưởng trạng thái index:** luôn kiểm tra `git status`, `git diff` và `git diff --cached` sau khi stash.
- **Áp dụng stash có thể gây conflict:** stash không đảm bảo có thể áp dụng sạch trên mọi nhánh.
- **Stash mới làm thay đổi thứ tự tham chiếu:** entry `stash@{0}` có thể đổi sau mỗi lần tạo hoặc xóa stash.
- **Không nên dùng stash làm nơi lưu công việc dài hạn:** nếu một phần công việc đã hoàn chỉnh và có ý nghĩa độc lập, hãy tạo commit trên nhánh phù hợp.

## 11. Ví dụ tổng hợp: giữ phần staged để kiểm thử, cất phần còn lại

Bạn đang sửa một tính năng thanh toán và có ba nhóm thay đổi:

- Sửa kiểm tra số tiền — đã staging.
- Bổ sung test cho trường hợp biên — đã staging.
- Thử nghiệm log — chưa staging.

Bạn muốn chạy test chỉ với phần đã staging, sau đó tiếp tục phần log.

**Bước 1 — Kiểm tra thay đổi**

~~~bash
git status
git diff --cached
git diff
~~~

**Bước 2 — Cất phần chưa staging**

~~~bash
git stash push --keep-index -m "Tam cat log thanh toan"
~~~

**Bước 3 — Kiểm tra trạng thái còn lại**

~~~bash
git status
git diff --cached
git diff
~~~

Index vẫn chứa phần sửa số tiền và test. Phần log đã được cất.

**Bước 4 — Chạy test trên phần đã staging**

~~~bash
./gradlew test
~~~

Nếu test thành công, tạo commit:

~~~bash
git commit -m "Validate payment amount"
~~~

**Bước 5 — Khôi phục phần log**

~~~bash
git stash list
git stash pop
~~~

Kiểm tra lại:

~~~bash
git status
git diff
~~~

Phần log được đưa trở lại working tree để tiếp tục chỉnh sửa. Nếu không còn cần thiết, bạn có thể bỏ phần đó theo quy trình phù hợp sau khi xác nhận nội dung.

## 12. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Chọn hunk để stash | `git stash push --patch -m "message"` |
| Chỉ stash thay đổi staged | `git stash push --staged -m "message"` |
| Giữ staged, stash unstaged | `git stash push --keep-index -m "message"` |
| Chọn hunk trong phần staged | `git stash push --staged --patch -m "message"` |
| Stash một số đường dẫn | `git stash push -m "message" -- path/to/file` |
| Xem danh sách stash | `git stash list` |
| Xem diff của stash | `git stash show -p 'stash@{0}'` |
| Áp dụng và giữ stash | `git stash apply 'stash@{0}'` |
| Áp dụng cả trạng thái index | `git stash apply --index 'stash@{0}'` |
| Áp dụng rồi xóa nếu thành công | `git stash pop 'stash@{0}'` |
| Xóa một stash | `git stash drop 'stash@{0}'` |

## 13. Tổng kết

`git stash --patch`, `--staged` và `--keep-index` cho phép bạn kiểm soát chính xác hơn phần thay đổi được cất tạm. `--patch` dùng để chọn từng hunk, `--staged` cất phần đã staging, còn `--keep-index` giữ phần đã staging tại chỗ và cất phần chưa staging.

Trước và sau mỗi thao tác, hãy kiểm tra `git status`, `git diff` và `git diff --cached`. Khi khôi phục, chọn đúng stash entry, cân nhắc `apply` hay `pop`, và dùng `--index` nếu cần phục hồi trạng thái staging. Cách làm này giúp bạn chuyển công việc linh hoạt, giữ được phần đang hoàn thiện và tránh trộn các thay đổi không liên quan vào cùng một commit.

