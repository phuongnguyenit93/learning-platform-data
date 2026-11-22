# Vì sao xung đột xuất hiện và giới hạn của hợp nhất tự động

Khi nhiều người cùng thay đổi một lịch sử Git, Git có thể ghép các thay đổi độc lập lại với nhau. Nhưng nếu các thay đổi cạnh tranh nhau hoặc cần hiểu ý nghĩa của chương trình, Git không thể tự quyết định kết quả đúng. Hiểu được lúc nào Git tự hợp nhất và lúc nào cần con người xem xét giúp bạn xử lý xung đột có chủ đích, giữ được thay đổi cần thiết và tránh làm mất công việc của người khác.

## 1. Hợp nhất tự động hoạt động như thế nào?

Git thường hợp nhất bằng cách so sánh ba phiên bản của nội dung:

- **Base**: phiên bản chung gần nhất mà hai nhánh cùng xuất phát.
- **Ours**: phiên bản ở nhánh hiện tại, tức nhánh bạn đang đứng khi thực hiện merge.
- **Theirs**: phiên bản ở nhánh được đưa vào.

Đây là phép hợp nhất ba chiều (*three-way merge*). Git không đơn giản chọn một file làm chuẩn rồi chép file còn lại lên. Git xem mỗi nhánh đã thay đổi gì so với base, sau đó cố gắng kết hợp hai tập thay đổi.

Ví dụ, base có nội dung:

```java
int timeout = 30;
boolean enabled = true;
```

Nhánh hiện tại đổi dòng đầu thành `int timeout = 60;`, còn nhánh kia đổi dòng thứ hai thành `boolean enabled = false;`. Hai thay đổi nằm ở những vùng độc lập, vì vậy Git có thể tạo kết quả gồm cả hai:

```java
int timeout = 60;
boolean enabled = false;
```

Hợp nhất tự động thành công chỉ có nghĩa Git tìm được cách kết hợp thay đổi theo quy tắc của nó. Điều đó chưa chứng minh kết quả đúng về nghiệp vụ hoặc chạy đúng.

## 2. Vì sao xung đột xuất hiện?

Xung đột xảy ra khi Git không thể tự xác định một kết quả hợp nhất duy nhất, an toàn theo quy tắc hợp nhất đang dùng. Một số tình huống thường gặp:

### 2.1. Hai nhánh sửa cùng một vùng

Giả sử base chứa:

```java
int retryCount = 3;
```

Nhánh hiện tại đổi thành `int retryCount = 5;`, trong khi nhánh được hợp nhất đổi thành `int retryCount = 8;`. Cả hai cùng thay đổi một dòng theo hai cách khác nhau. Git không biết giá trị nào phản ánh yêu cầu cuối cùng nên đánh dấu xung đột.

### 2.2. Một nhánh sửa, nhánh kia xóa

Nếu một nhánh chỉnh sửa một file nhưng nhánh còn lại xóa file đó, Git không thể tự suy ra ý định: file đã lỗi thời cần xóa, hay thay đổi mới cần được giữ lại? Đây là dạng xung đột sửa/xóa (*modify/delete*).

### 2.3. Hai nhánh cùng tạo một đường dẫn

Hai nhánh cùng thêm một file có cùng đường dẫn nhưng nội dung khác nhau có thể tạo xung đột thêm/thêm (*add/add*). Git không thể tự chọn nội dung nào là phiên bản mong muốn.

### 2.4. Đổi tên, di chuyển hoặc thay đổi cấu trúc file

Một nhánh đổi tên hoặc di chuyển file trong khi nhánh kia sửa file cũ, hoặc cả hai nhánh đổi tên theo những hướng khác nhau. Git có thể nhận diện một số thao tác đổi tên, nhưng việc ghép các thay đổi liên quan vẫn có thể mơ hồ. Kết quả phụ thuộc vào nội dung, cấu trúc và khả năng nhận diện đổi tên của Git.

### 2.5. Xung đột ở mức cấu trúc hoặc loại đối tượng

Xung đột cũng có thể liên quan đến file nhị phân, quyền thực thi, liên kết tượng trưng hoặc submodule. Các trường hợp này không nhất thiết có thể biểu diễn bằng các dấu đánh dấu xung đột trong văn bản. Cần xem trạng thái index và thông báo của Git để biết loại xung đột cụ thể.

## 3. Dấu đánh dấu xung đột trong file văn bản

Với xung đột nội dung văn bản thông thường, Git có thể ghi các dấu phân cách vào file:

```text
<<<<<<< HEAD
int retryCount = 5;
=======
int retryCount = 8;
>>>>>>> feature/retry-policy
```

- `<<<<<<<` mở phần thay đổi ở phía hiện tại.
- `=======` phân cách hai phía.
- `>>>>>>>` đóng phần thay đổi từ nhánh được hợp nhất.

Nội dung sau `<<<<<<<` thường là `HEAD` khi đang merge. Tên nhánh ở cuối thường giúp nhận biết phía còn lại. Khi dùng rebase, cách Git trình bày “ours” và “theirs” có thể khiến người mới nhầm lẫn: trong lúc rebase, `ours` thường là nhánh đích đang được dựng lại, còn `theirs` là commit đang được áp dụng. Hãy đọc trạng thái thao tác và nội dung thực tế thay vì chỉ dựa vào tên nhãn.

Nếu bật kiểu hiển thị `diff3` hoặc `zdiff3`, vùng xung đột có thể có thêm phần base, thường được mở đầu bằng `|||||||`. Phần này cho biết nội dung gốc trước khi hai phía thay đổi, rất hữu ích để hiểu vì sao hai thay đổi không tương thích.

Các dấu trên chỉ là chỉ dẫn để người xử lý xem xét. Không nên xóa chúng một cách máy móc hoặc chọn toàn bộ một phía khi chưa hiểu thay đổi của hai bên.

## 4. Kiểm tra trạng thái trước khi giải quyết

Khi Git báo xung đột, trước hết hãy xác định thao tác nào đang dừng và những đường dẫn nào chưa được giải quyết:

```bash
git status
git diff --name-only --diff-filter=U
git diff
```

`git status` cho biết đang trong merge, rebase hay một thao tác liên quan khác, đồng thời liệt kê các đường dẫn chưa hợp nhất. `git diff --name-only --diff-filter=U` liệt kê những file vẫn còn trạng thái unmerged. `git diff` hiển thị khác biệt để hỗ trợ xem xét.

Để xem các phiên bản đang được lưu trong index, dùng:

```bash
git ls-files -u
```

Trong một xung đột nội dung thông thường, index có thể chứa ba stage:

| Stage | Ý nghĩa |
|---|---|
| 1 | Phiên bản base chung |
| 2 | Phiên bản ours |
| 3 | Phiên bản theirs |

Có thể xem từng phiên bản của một file bằng:

```bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
```

Thay `path/to/file` bằng đường dẫn thực tế. Không phải mọi loại xung đột đều có đủ cả ba stage; chẳng hạn file được thêm mới hoặc bị xóa có thể thiếu một stage. Với xung đột file nhị phân hoặc xung đột cấu trúc, hãy dựa vào thông tin trong `git status` và `git ls-files -u` để xác định những phiên bản thực sự tồn tại.

## 5. Quy trình giải quyết xung đột có kiểm soát

1. **Xác định mục tiêu của thao tác.** Kiểm tra bạn đang merge nhánh nào, rebase commit nào hoặc đang áp dụng thay đổi theo cách nào. Đọc `git status` trước khi sửa.
2. **Hiểu cả hai phía và base.** Xem vùng xung đột, lịch sử liên quan và phiên bản ở các stage nếu cần. Tìm hiểu lý do mỗi thay đổi được tạo ra; hỏi người sở hữu thay đổi khi ý định chưa rõ.
3. **Tạo kết quả kết hợp có chủ đích.** Sửa nội dung để đáp ứng yêu cầu của cả hai phía. Có trường hợp cần giữ một phía, kết hợp hai phía, viết lại đoạn mã hoặc giữ việc xóa file; quyết định phải dựa trên mục đích thực tế.
4. **Đánh dấu file đã giải quyết.** Sau khi chỉnh sửa và xóa hết các dấu xung đột còn sót, dùng `git add path/to/file` để đưa kết quả vào index. Nếu quyết định xóa file, dùng `git rm path/to/file`.
5. **Kiểm tra lại kết quả.** Chạy `git status`, xem diff đã staged bằng `git diff --cached`, tìm các dấu `<<<<<<<`, `=======`, `>>>>>>>` còn sót và chạy kiểm tra phù hợp như test hoặc build của dự án.
6. **Tiếp tục hoặc hủy thao tác theo trạng thái.** Khi merge đã giải quyết xong, dùng `git merge --continue` (hoặc hoàn tất commit merge theo hướng dẫn Git). Khi rebase đã giải quyết xong, dùng `git rebase --continue`. Nếu cần quay lại trạng thái trước thao tác, có thể dùng `git merge --abort` hoặc `git rebase --abort` tương ứng, sau khi hiểu ảnh hưởng tới thay đổi đang có.

Ví dụ kiểm tra sau khi sửa một file:

```bash
git add src/main/java/RetryPolicy.java
git status
git diff --cached -- src/main/java/RetryPolicy.java
```

`git add` trong quy trình này vừa đánh dấu đường dẫn đã giải quyết, vừa cập nhật nội dung đã chọn vào index. Nếu tiếp tục sửa file sau đó, cần stage lại để index chứa đúng phiên bản cuối cùng.

## 6. Giới hạn của hợp nhất tự động

Git chủ yếu xử lý khác biệt ở mức nội dung và cấu trúc mà nó có thể nhận diện. Nó không hiểu đầy đủ ý nghĩa của chương trình, quy tắc nghiệp vụ hay ý định của người viết. Vì vậy có những tình huống Git hợp nhất thành công nhưng sản phẩm vẫn sai:

- Một nhánh đổi tên hàm, nhánh kia thêm lời gọi ở vị trí khác; kết quả ghép được nhưng lời gọi có thể không còn đúng.
- Một nhánh đổi đơn vị từ giây sang mili giây, nhánh kia thay đổi giá trị số; văn bản có thể ghép sạch nhưng phép tính sai hệ số.
- Hai nhánh thay đổi riêng từng file cấu hình hoặc mã nguồn; kết quả cuối cùng có thể vi phạm ràng buộc giữa các file.
- Một thay đổi cập nhật API, thay đổi kia vẫn dùng hợp đồng cũ; không có vùng văn bản nào chồng lấn nhưng chương trình có thể không tương thích.
- Một file sinh tự động hoặc file nhị phân có định dạng riêng; Git không thể hiểu nội dung nghiệp vụ để tạo ra phiên bản kết hợp đúng.

Ngoài ra, kết quả hợp nhất phụ thuộc vào base mà Git xác định, chiến lược merge, driver được cấu hình và thuộc tính của đường dẫn. Các driver tùy chỉnh có thể thay đổi cách xử lý một số loại file, nhưng cũng không thể bảo đảm tính đúng đắn về nghiệp vụ.

Do đó, cần phân biệt hai khái niệm:

| Khái niệm | Điều nó xác nhận | Điều nó không xác nhận |
|---|---|---|
| Hợp nhất tự động thành công | Git tạo được kết quả theo quy tắc hợp nhất | Mã nguồn đúng, test đạt hoặc yêu cầu nghiệp vụ được đáp ứng |
| Xung đột đã được đánh dấu là giải quyết | Người dùng đã cập nhật index để Git có thể tiếp tục | Nội dung đã được review kỹ hoặc không còn lỗi logic |

## 7. Những cách xử lý dễ gây mất thay đổi

- **Chọn “Accept Current” hoặc “Accept Incoming” cho toàn bộ file mà không đọc nội dung.** Cách này có thể loại bỏ một phần công việc hợp lệ của phía còn lại.
- **Xóa dấu xung đột nhưng để lại cả hai đoạn mã không tương thích.** File có thể biên dịch nhưng logic vẫn sai hoặc xử lý một trường hợp hai lần.
- **Dùng `git checkout --ours` hoặc `git checkout --theirs` theo thói quen.** Các lệnh này thay nội dung working tree của đường dẫn bằng một phía; cần hiểu ý nghĩa ours/theirs trong đúng thao tác hiện tại trước khi dùng. Với file đã xóa hoặc các dạng xung đột đặc biệt, hành vi và phiên bản sẵn có cần được kiểm tra cẩn thận.
- **Stage file quá sớm.** Nếu chỉnh sửa tiếp sau khi stage, index có thể vẫn giữ phiên bản cũ; hãy stage lại và kiểm tra `git diff --cached`.
- **Cho rằng hết dấu xung đột là đã xong.** Cần kiểm tra diff, trạng thái repository và chạy test phù hợp trước khi tiếp tục.

## 8. Ví dụ thực hành: hợp nhất chính sách retry

Giả sử base có cấu hình:

```java
class RetryPolicy {
    int maxAttempts = 3;
    int delaySeconds = 2;
}
```

Nhánh `feature/retry-limit` tăng `maxAttempts` lên `5`. Nhánh `feature/retry-delay` tăng `delaySeconds` lên `4`. Vì hai thay đổi nằm ở hai dòng độc lập, Git thường có thể hợp nhất tự động. Tuy vậy, bạn vẫn cần xem diff và chạy test để xác nhận chính sách mới phù hợp.

Trong tình huống khác, cả hai nhánh cùng đổi `maxAttempts`: một bên đặt thành `5`, bên kia đặt thành `8`. Git có thể báo xung đột vì không có đủ thông tin để chọn giá trị. Người giải quyết cần kiểm tra yêu cầu hoặc trao đổi với người thực hiện hai thay đổi. Nếu yêu cầu cuối cùng là tối đa `8` lần nhưng phải giữ thêm điều kiện giới hạn theo môi trường, kết quả có thể cần viết lại logic thay vì chọn nguyên một phía.

Sau khi sửa, ví dụ:

```java
class RetryPolicy {
    int maxAttempts = 8;
    int delaySeconds = 4;
}
```

Stage file, xem diff đã stage và chạy test của `RetryPolicy` trước khi tiếp tục thao tác merge hoặc rebase.

## 9. Ghi nhớ

Xung đột là tín hiệu cho biết Git cần thêm thông tin để hoàn tất việc kết hợp thay đổi. Hãy dùng base, hai phiên bản nhánh và mục đích của từng thay đổi để đưa ra quyết định. Sau khi giải quyết, kiểm tra cả nội dung lẫn hành vi của chương trình; chỉ khi kết quả đã được xác minh mới tiếp tục hoàn tất merge hoặc rebase.
