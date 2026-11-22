# Theo dõi lịch sử tệp đổi tên bằng git log --follow

Trong quá trình phát triển, một tệp có thể được đổi tên hoặc chuyển sang thư mục khác nhiều lần. Nếu chỉ chạy `git log -- <đường-dẫn-hiện-tại>`, bạn có thể chỉ thấy phần lịch sử kể từ khi tệp mang tên hiện tại. Git có tùy chọn `--follow` để tiếp tục lần theo lịch sử của một tệp qua các lần đổi tên được nhận diện.

Lệnh thường dùng là:

```bash
git log --follow -- <path/to/file>
```

Git không lưu một sự kiện “rename” riêng trong commit. Mỗi commit lưu snapshot của cây thư mục; khi hiển thị diff, Git suy luận việc đổi tên bằng cách so sánh nội dung tệp bị xóa và tệp được thêm. Vì vậy, `--follow` là cơ chế phát hiện dựa trên độ tương đồng, không phải một bản ghi tên tệp tuyệt đối. Bài học này giải thích cách đọc kết quả, điều chỉnh ngưỡng phát hiện và xử lý các trường hợp lịch sử phức tạp.

## 1. Vì sao cần theo dõi lịch sử qua đổi tên?

Giả sử một tệp bắt đầu ở `src/LegacyPayment.java`, sau đó được đổi tên thành `src/PaymentService.java` và tiếp tục được chỉnh sửa. Nếu chỉ truy vấn tên mới, việc xem lịch sử có thể không thể hiện đầy đủ các commit trước khi đổi tên.

Ví dụ lịch sử:

```text
commit A: tạo src/LegacyPayment.java
commit B: sửa logic thanh toán
commit C: đổi tên LegacyPayment.java thành PaymentService.java
commit D: thêm xử lý retry vào PaymentService.java
```

Khi đang đứng ở phiên bản hiện tại, bạn muốn xem cả commit A, B, C và D. `git log --follow` yêu cầu Git tiếp tục tìm lịch sử của tệp qua lần đổi tên được nhận diện, để các commit cũ vẫn có thể xuất hiện trong kết quả.

Điều này hữu ích khi:

- Tìm nguyên nhân một lỗi đã tồn tại trước khi tệp được đổi tên.
- Xác định ai đã thêm một đoạn logic từ thời tệp còn tên cũ.
- Review thay đổi lớn sau khi mã nguồn được chuyển thư mục.
- Kiểm tra quá trình tái cấu trúc và giữ được ngữ cảnh lịch sử.
- Chuẩn bị sửa hoặc xóa một API cũ nhưng cần hiểu lịch sử trước đó.

## 2. Git nhận diện rename như thế nào?

Git lưu các snapshot theo commit. Trong tree của một commit, Git ghi tên đường dẫn và OID của object; commit không chứa một trường riêng nói rằng “đường dẫn A đã đổi thành đường dẫn B”.

Khi so sánh hai commit, Git có thể nhận diện một cặp thay đổi:

- Một đường dẫn cũ biến mất (*delete*).
- Một đường dẫn mới xuất hiện (*add*).
- Nội dung của hai tệp đủ giống nhau theo ngưỡng phát hiện rename.

Nếu mức tương đồng đạt ngưỡng, Git trình bày cặp thay đổi đó là rename. Ví dụ:

```text
R100    src/LegacyPayment.java    src/PaymentService.java
```

`R100` có nghĩa Git nhận diện rename với mức tương đồng 100%. Nếu tệp được đổi tên và chỉnh sửa cùng lúc, kết quả có thể là `R85`, `R72` hoặc một mức khác.

Đây là kết quả suy luận từ nội dung và diff. Hai tệp độc lập nhưng có nội dung giống nhau cũng có thể được Git xem là rename nếu ngữ cảnh so sánh phù hợp. Ngược lại, một tệp được đổi tên nhưng thay đổi quá nhiều có thể không được nhận diện.

## 3. Xem lịch sử tệp bằng git log --follow

Để xem lịch sử của tệp hiện tại qua các lần đổi tên:

```bash
git log --follow -- src/PaymentService.java
```

Git hiển thị các commit liên quan đến đường dẫn, đồng thời thử tiếp tục lịch sử qua các lần rename được phát hiện. Mặc định, kết quả có thể gồm mã commit, tác giả, ngày và thông điệp commit tùy định dạng log đang cấu hình.

Muốn hiển thị gọn:

```bash
git log --follow --oneline -- src/PaymentService.java
```

Muốn giới hạn số commit gần nhất:

```bash
git log --follow --oneline -10 -- src/PaymentService.java
```

Muốn xem lịch sử trên một branch cụ thể:

```bash
git log main --follow -- src/PaymentService.java
```

Chỉ định branch giúp kết quả dễ hiểu hơn khi repository có nhiều nhánh cùng đổi tên hoặc phát triển các phiên bản tệp khác nhau. Nếu dùng `--all`, Git có thể hiển thị lịch sử từ nhiều ref; hãy đọc nhãn branch và đồ thị cẩn thận.

**Lưu ý:** `--follow` chỉ hỗ trợ theo dõi một đường dẫn tệp tại một thời điểm. Không dùng nó để theo dõi đồng thời nhiều tệp hoặc toàn bộ lịch sử của một thư mục đã đổi tên.

## 4. Hiển thị đường dẫn cũ và mới bằng --name-status

Chỉ xem commit message có thể chưa đủ để biết Git đã nhận diện lần đổi tên nào. Thêm `--name-status` để hiển thị trạng thái và các đường dẫn:

```bash
git log --follow --name-status -- src/PaymentService.java
```

Ví dụ kết quả rút gọn:

```text
commit d4e5f6a
Author: Developer
Date:   2026-05-12

    refactor: rename payment service

R100    src/LegacyPayment.java    src/PaymentService.java

commit a1b2c3d

    fix: handle empty order

M       src/LegacyPayment.java
```

Ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `A` | Tệp được thêm |
| `M` | Tệp được sửa |
| `D` | Tệp bị xóa |
| `Rnnn` | Rename được phát hiện; `nnn` là phần trăm tương đồng |
| `Cnnn` | Copy được phát hiện trong chế độ phát hiện copy |
| `T` | Loại đối tượng hoặc mode thay đổi |

Khi Git nhận diện rename, `--name-status` hiển thị cả đường dẫn nguồn và đích. Điều này giúp bạn lần ra tên cũ để kiểm tra commit trước khi đổi tên.

Có thể kết hợp định dạng commit ngắn và ngày:

```bash
git log --follow --name-status --format="%h %ad %s" --date=short -- src/PaymentService.java
```

Kết quả giúp đọc nhanh commit nào thay đổi tệp và commit nào thực hiện rename. Nếu muốn xem kích thước thay đổi thay vì mã trạng thái:

```bash
git log --follow --stat -- src/PaymentService.java
```

## 5. Xem chi tiết commit thực hiện rename

Sau khi tìm được commit có trạng thái `Rnnn`, xem commit đó:

```bash
git show --summary --find-renames <commit>
```

Ví dụ output có thể chứa:

```text
 rename src/LegacyPayment.java => src/PaymentService.java (100%)
```

Để xem trạng thái đường dẫn của commit so với parent:

```bash
git diff-tree --no-commit-id -r -M --name-status <commit>^ <commit>
```

`-M` bật phát hiện rename trong phép so sánh. Với commit merge, cần xác định parent muốn so sánh vì merge có thể có nhiều parent. Cú pháp `<commit>^` mặc định chỉ parent thứ nhất.

Bạn cũng có thể xem nội dung trước và sau rename bằng `git show`:

```bash
# Nội dung đường dẫn cũ ở parent trước commit rename.
git show <commit>^:src/LegacyPayment.java

# Nội dung đường dẫn mới trong commit rename.
git show <commit>:src/PaymentService.java
```

Hai lệnh này hữu ích khi muốn xác nhận tệp có thực sự được di chuyển gần như nguyên vẹn hay được đổi tên cùng một lần tái cấu trúc lớn.

## 6. Điều chỉnh ngưỡng phát hiện bằng -M

Git dùng ngưỡng tương đồng để quyết định một cặp delete/add có phải rename hay không. Với `-M` hoặc `--find-renames`, có thể chỉ định ngưỡng phần trăm.

Ví dụ dùng ngưỡng mặc định hoặc 50%:

```bash
git log --follow -M50% --name-status -- src/PaymentService.java
```

Nếu tệp đã thay đổi nhiều trong cùng commit rename, thử ngưỡng thấp hơn:

```bash
git log --follow -M30% --name-status -- src/PaymentService.java
```

Nếu muốn yêu cầu tệp phải rất giống nhau:

```bash
git log --follow -M90% --name-status -- src/PaymentService.java
```

Ý nghĩa thực tế:

- **Ngưỡng thấp:** Git dễ nhận diện rename dù nội dung đã thay đổi nhiều; đổi lại, có thể ghép nhầm hai tệp độc lập.
- **Ngưỡng cao:** Git chỉ nhận diện khi nội dung rất giống; đổi lại, có thể bỏ sót rename thật nếu tệp được sửa nhiều.
- **Ngưỡng mặc định:** thường là 50% khi dùng phát hiện rename mà không chỉ định giá trị.

Hãy thử vài ngưỡng và đối chiếu với nội dung thực tế. Không có một ngưỡng đúng cho mọi repository; tệp mã nguồn, tài liệu, file sinh tự động và tệp có cấu trúc lớn có thể có đặc điểm khác nhau.

## 7. Theo dõi qua nhiều lần đổi tên

Một tệp có thể đổi tên nhiều lần:

```text
src/LegacyPayment.java
        |
        | rename
        v
src/PaymentService.java
        |
        | move
        v
services/payment/PaymentService.java
```

Nếu Git nhận diện được các lần đổi tên liên tiếp, `--follow` có thể lần từ đường dẫn hiện tại về những tên cũ hơn:

```bash
git log --follow --name-status -- services/payment/PaymentService.java
```

Để rà soát đường dẫn cũ và các commit chuyển đổi:

```bash
git log --follow --name-status --format="%h %s" -- services/payment/PaymentService.java
```

Khi thấy một dòng `Rnnn`, ghi lại hai đường dẫn và commit tương ứng. Có thể mở từng commit bằng `git show` để kiểm tra thay đổi. Nếu một lần đổi tên không được nhận diện, thử `-M` với ngưỡng phù hợp và kiểm tra diff giữa parent và commit.

Nếu tệp được chia thành nhiều tệp mới, hoặc nhiều tệp được hợp nhất thành một, lịch sử không còn là chuỗi rename một-một. `--follow` có thể không mô tả đầy đủ quan hệ nguồn gốc. Khi đó, cần truy tìm các commit chuyển đổi bằng `git log`, `git grep`, `git blame` và xem nội dung các parent.

## 8. Phân biệt rename và copy

Rename có nghĩa một đường dẫn cũ được thay bằng đường dẫn mới trong phép so sánh. Copy có nghĩa một đường dẫn mới được tạo từ nội dung tương tự trong khi tệp nguồn vẫn tồn tại.

`--follow` tập trung theo dõi lịch sử của một đường dẫn qua rename. Nó không phải công cụ tổng quát để lần theo mọi bản sao của nội dung.

Để xem copy detection trong diff/log, có thể dùng:

```bash
git log --find-copies --find-copies-harder --name-status -- src/NewHandler.java
```

`--find-copies-harder` yêu cầu Git xét cả các tệp không thay đổi làm nguồn copy, có thể tốn tài nguyên hơn trong repository lớn. Copy detection chỉ giúp hiển thị quan hệ copy trong diff; nó không làm cho file mới có cùng lịch sử commit với file nguồn.

Nếu cần tìm nguồn của một đoạn code đã được sao chép, có thể tìm nội dung hoặc chuỗi đặc trưng trong lịch sử:

```bash
git log --all -S"calculateTotal" --oneline -- '*.java'
git log --all -G"calculateTotal\(" --oneline -- '*.java'
```

`-S` tìm commit làm thay đổi số lần xuất hiện của chuỗi; `-G` tìm diff có dòng khớp biểu thức. Hai tùy chọn này bổ trợ cho việc lần theo nguồn gốc nội dung, nhưng không thay thế rename detection.

## 9. Theo dõi lịch sử sau khi xóa tệp

Nếu tệp đã bị xóa khỏi phiên bản hiện tại, bạn vẫn có thể truy vấn lịch sử bằng đường dẫn đã biết:

```bash
git log --follow --name-status -- src/OldPayment.java
```

Commit xóa sẽ xuất hiện dưới trạng thái `D`; các commit trước đó có thể tiếp tục được hiển thị nếu Git nhận diện được rename trong lịch sử cũ.

Muốn xem nội dung tệp ở commit trước khi bị xóa:

```bash
git show <commit-before-delete>:src/OldPayment.java
```

Hoặc xem nội dung tại một commit cụ thể:

```bash
git show <commit>:<path-at-that-commit>
```

Đường dẫn phải là tên được lưu trong tree của commit đó. Tên tệp hiện tại không nhất thiết tồn tại trong mọi commit cũ.

## 10. Phạm vi và giới hạn của --follow

`--follow` rất hữu ích, nhưng có một số giới hạn quan trọng:

- **Chỉ một đường dẫn:** `--follow` chỉ làm việc với một tệp tại một thời điểm; không dùng cho nhiều pathspec.
- **Không theo dõi thư mục như một object:** Git lưu tree và file path; thư mục không có một danh tính rename riêng để theo dõi.
- **Phát hiện dựa trên độ tương đồng:** đổi tên kèm tái cấu trúc lớn có thể không đạt ngưỡng.
- **Không phải copy lineage:** bản sao mới không tự động kế thừa lịch sử của tệp nguồn.
- **Merge phức tạp:** khi đổi tên xảy ra trên nhiều nhánh hoặc trong merge commit, cần kiểm tra từng parent và đồ thị thay vì chỉ dựa vào một dòng log.
- **Lịch sử được giới hạn theo ref:** lệnh mặc định đọc lịch sử reachable từ `HEAD`; muốn xem branch khác, chỉ định ref rõ ràng.

Đặc biệt, không nên dùng `--first-parent` nếu mục tiêu là xem mọi commit trên các nhánh phụ. Tùy chọn này chỉ đi theo parent thứ nhất và có thể ẩn phần lịch sử được tạo ở nhánh được merge vào.

## 11. Xử lý khi Git không nhận diện được rename

Nếu kết quả chỉ hiển thị `A` và `D` thay vì `Rnnn`, hãy kiểm tra theo thứ tự:

1. Xác nhận đúng branch/ref và đúng đường dẫn hiện tại.
2. Xem diff của commit nghi ngờ với `git show --summary --find-renames <commit>`.
3. Thử ngưỡng thấp hơn bằng `git log --follow -M30% --name-status -- <path>`.
4. Kiểm tra file cũ và mới có thực sự cùng nguồn gốc hay chỉ có nội dung tương tự.
5. Nếu có nhiều tệp mới hoặc tệp cũ, xem xét copy detection hoặc tìm nội dung bằng `-S`/`-G`.
6. Nếu có merge, kiểm tra từng parent của merge commit và các branch liên quan.

Đừng hạ ngưỡng quá thấp chỉ để ép Git hiển thị `R`. Một kết quả rename sai có thể dẫn bạn đến lịch sử của tệp khác. Cần xác minh bằng nội dung, commit và ngữ cảnh thay đổi.

## 12. Ví dụ quy trình điều tra một lỗi trong tệp đã đổi tên

Giả sử lỗi xử lý thanh toán xuất hiện trong `services/payment/PaymentService.java`, nhưng nhóm nghi ngờ logic đã tồn tại từ thời tệp còn tên `LegacyPayment.java`.

### Bước 1: xem toàn bộ lịch sử theo đường dẫn hiện tại

```bash
git log --follow --oneline -- services/payment/PaymentService.java
```

### Bước 2: xem các lần rename

```bash
git log --follow --name-status --format="%h %ad %s" --date=short -- services/payment/PaymentService.java
```

Tìm các dòng `Rnnn` để biết tên cũ và commit đổi tên.

### Bước 3: mở commit nghi ngờ

```bash
git show --summary --find-renames <rename-commit>
git show <rename-commit>^:src/LegacyPayment.java
git show <rename-commit>:services/payment/PaymentService.java
```

### Bước 4: tìm thay đổi đã đưa lỗi vào

Sau khi xác định đường dẫn cũ, tìm commit sửa logic:

```bash
git log --follow -p -- services/payment/PaymentService.java
```

`-p` hiển thị patch của các commit. Có thể giới hạn phạm vi thời gian hoặc số commit để log dễ đọc:

```bash
git log --follow -p --since="2025-01-01" -- services/payment/PaymentService.java
```

### Bước 5: xác minh dòng code qua các phiên bản

Khi đã tìm được commit liên quan, dùng `git show <commit>` hoặc `git blame` trên đường dẫn ở đúng thời điểm để hiểu ai đã thay đổi logic và thay đổi đó được tích hợp qua branch nào.

Kết hợp lịch sử rename với patch và ngữ cảnh commit sẽ cho câu trả lời đáng tin cậy hơn việc chỉ nhìn tên tệp hiện tại.

## 13. Lệnh thường dùng

| Mục tiêu | Lệnh |
|---|---|
| Lịch sử qua rename | `git log --follow -- path/to/file` |
| Lịch sử gọn | `git log --follow --oneline -- path/to/file` |
| Hiện đường dẫn và trạng thái | `git log --follow --name-status -- path/to/file` |
| Hiện thống kê thay đổi | `git log --follow --stat -- path/to/file` |
| Hiện patch từng commit | `git log --follow -p -- path/to/file` |
| Điều chỉnh ngưỡng rename | `git log --follow -M30% -- path/to/file` |
| Xem commit rename | `git show --summary --find-renames <commit>` |
| Xem trạng thái path của commit | `git diff-tree --no-commit-id -r -M --name-status <parent> <commit>` |
| Xem nội dung trước/sau rename | `git show <commit>^:<old-path>` và `git show <commit>:<new-path>` |
| Tìm nội dung đã thay đổi | `git log -S"text" --all -- pathspec` hoặc `git log -G"regex" --all -- pathspec` |

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Git lưu một bản ghi rename riêng trong commit | Git lưu snapshot; rename được suy luận khi so sánh tree |
| `git log --follow` theo dõi mọi tệp trong thư mục | Nó chỉ hỗ trợ một đường dẫn tệp tại một thời điểm |
| Rename luôn được nhận diện 100% | Git dựa trên độ tương đồng và có thể bỏ sót khi nội dung thay đổi nhiều |
| `R100` nghĩa là Git có metadata rename chính xác | Đây là kết quả phát hiện với mức tương đồng 100% trong phép so sánh |
| Hạ ngưỡng rename luôn tốt hơn | Ngưỡng thấp có thể tạo nhận diện sai giữa các tệp độc lập |
| `--follow` tìm được mọi bản copy | Nó tập trung theo dõi rename; copy detection là cơ chế riêng |
| Lịch sử của file mới bắt đầu từ lúc đổi tên | Nếu rename được nhận diện, `--follow` có thể hiển thị các commit trước tên hiện tại |
| Không thấy commit cũ nghĩa là lịch sử đã mất | Có thể do sai ref/path, rename không được nhận diện hoặc lịch sử bị giới hạn |

## 15. Ghi nhớ

Để theo dõi lịch sử một tệp qua đổi tên, bắt đầu bằng:

```bash
git log --follow --name-status -- path/to/current-file
```

Git suy luận rename từ snapshot và mức tương đồng nội dung, không dựa vào metadata rename riêng. Dùng `-M` để điều chỉnh ngưỡng, `--name-status` để xem đường dẫn cũ/mới, `--stat` hoặc `-p` để xem mức độ thay đổi và `git show --summary --find-renames` để kiểm tra commit đổi tên.

`--follow` chỉ áp dụng cho một tệp và không theo dõi copy hoặc thư mục như một đơn vị. Khi rename không được nhận diện, kiểm tra ref, path, ngưỡng tương đồng, commit và từng parent của merge. Luôn xác minh kết quả bằng nội dung thực tế trước khi kết luận lịch sử của tệp.
