# Chọn nội dung kết hợp đúng ý nghĩa thay vì chỉ bỏ dấu xung đột

Khi Git dừng vì xung đột, việc xóa các dòng `<<<<<<<`, `=======` và `>>>>>>>` chỉ làm file hết dấu đánh dấu. Nó chưa bảo đảm chương trình giữ được mục đích của cả hai thay đổi. Một kết quả hợp nhất tốt phải phản ánh đúng yêu cầu, quy tắc nghiệp vụ và hợp đồng giữa các phần của hệ thống. Bài học này hướng dẫn cách đọc các phía của xung đột, suy luận kết quả cần có và kiểm chứng kết quả trước khi tiếp tục merge hoặc rebase.

## 1. Giải quyết xung đột là quyết định về ý nghĩa

Git có thể chỉ ra hai đoạn nội dung không thể tự ghép theo quy tắc của nó. Git không biết vì sao người viết thay đổi đoạn mã, điều kiện nghiệp vụ nào cần được bảo toàn hoặc hai thay đổi có phụ thuộc nhau hay không.

Ví dụ, một nhánh tăng số lần thử lại vì dịch vụ bên ngoài thường chập chờn. Nhánh khác giảm số lần thử lại vì thao tác thanh toán có thể tạo giao dịch trùng. Nếu chỉ chọn một phía, bạn có thể làm mất mục đích của nhánh kia. Kết quả đúng có thể cần phân biệt thao tác có thể thử lại an toàn với thao tác không thể thử lại, thay vì chọn một con số.

Vì vậy, hãy coi vùng xung đột là câu hỏi cần trả lời:

- Mỗi phía đang cố giải quyết vấn đề gì?
- Quy tắc hoặc điều kiện nào phải luôn đúng sau khi kết hợp?
- Hai thay đổi độc lập, bổ sung cho nhau hay mâu thuẫn về yêu cầu?
- Kết quả cuối cùng phải thể hiện hành vi nào, kể cả khi nội dung không giống nguyên văn phía nào?

Một file hết dấu xung đột chỉ là điều kiện để Git tiếp tục. Chất lượng của quyết định phải được đánh giá bằng ý nghĩa và hành vi của kết quả.

## 2. Đọc đúng ba phiên bản trước khi sửa

Trong một xung đột nội dung thông thường, hãy xem ba phiên bản Git lưu trong index:

| Phiên bản | Ý nghĩa khi merge thông thường |
|---|---|
| Base (stage 1) | Nội dung chung trước khi hai nhánh thay đổi |
| Ours (stage 2) | Nội dung của nhánh hiện tại |
| Theirs (stage 3) | Nội dung từ nhánh đang được hợp nhất vào |

Giả sử Git hiển thị:

```text
<<<<<<< HEAD
int maxAttempts = 5;
=======
int maxAttempts = 2;
>>>>>>> feature/safe-retry
```

Đừng vội chọn `5` hoặc `2`. Trước tiên, xem dòng gốc và lịch sử thay đổi để hiểu lý do hai nhánh đưa ra hai giá trị. Có thể dùng:

```bash
git status
git diff --cc -- path/to/RetryPolicy.java
git show :1:path/to/RetryPolicy.java
git show :2:path/to/RetryPolicy.java
git show :3:path/to/RetryPolicy.java
```

`git diff --cc` hiển thị khác biệt kết hợp của vùng xung đột. Các lệnh `git show :1:`, `:2:` và `:3:` đọc lần lượt base, ours và theirs từ index. Thay đường dẫn ví dụ bằng file thực tế. Một số dạng xung đột không có đủ cả ba stage; chẳng hạn file được thêm mới hoặc bị xóa có thể thiếu phiên bản tương ứng.

Có thể dùng các lựa chọn xem nhanh sau để so sánh working tree với từng stage:

```bash
git diff --base -- path/to/file
git diff --ours -- path/to/file
git diff --theirs -- path/to/file
```

Nếu bật kiểu hiển thị `diff3` hoặc `zdiff3`, Git đưa thêm phần base vào vùng đánh dấu, thường có dạng:

```text
<<<<<<< HEAD
int maxAttempts = 5;
||||||| parent of ...
int maxAttempts = 3;
=======
int maxAttempts = 2;
>>>>>>> feature/safe-retry
```

Phần base giúp thấy rõ mỗi phía đã thay đổi từ giá trị ban đầu như thế nào. Nó đặc biệt hữu ích khi hai đoạn hiện tại khác nhau nhưng lý do thay đổi chưa rõ.

**Chú ý khi rebase:** cách Git gán `ours` và `theirs` dễ gây nhầm. Trong quá trình rebase, `ours` thường là trạng thái của nhánh đích (*upstream/onto*) mà các commit đang được áp dụng lên; `theirs` là commit từ nhánh đang được rebase ở bước hiện tại. Hãy xác nhận thao tác trong `git status` và đọc nội dung các stage; đừng suy luận chỉ từ tên nhánh hoặc nút “Current/Incoming” trong công cụ.

## 3. Quy trình chọn kết quả theo ý nghĩa

### Bước 1: Xác định mục tiêu của từng thay đổi

Đọc thông báo commit, nội dung thay đổi liên quan và ngữ cảnh của file. Tìm hiểu vấn đề mà mỗi nhánh định giải quyết. Tên nhánh hoặc tên commit có thể gợi ý, nhưng cần kiểm tra mã và yêu cầu thực tế.

Nếu ý định chưa thể xác định từ lịch sử, trao đổi với người tạo thay đổi hoặc người phụ trách nghiệp vụ. Không tự suy ra quy tắc quan trọng chỉ từ con số hay tên biến.

### Bước 2: Xác định điều kiện phải được giữ đúng

Viết ra các điều kiện mà kết quả cần thỏa mãn. Ví dụ:

- Một giao dịch thanh toán không được thực hiện lặp ngoài ý muốn.
- Tổng thời gian xử lý phải nằm trong giới hạn SLA.
- Mọi nơi gọi hàm phải dùng đúng hợp đồng mới.
- Dữ liệu cũ vẫn phải đọc được trong giai đoạn chuyển đổi.
- Cấu hình môi trường không được làm lộ bí mật hoặc ghi đè giá trị bắt buộc.

Điều kiện này là tiêu chí để chọn nội dung. Nếu hai yêu cầu thực sự mâu thuẫn, cần làm rõ quyết định sản phẩm hoặc nghiệp vụ trước khi kết luận.

### Bước 3: Xác định quan hệ giữa hai thay đổi

| Quan hệ | Cách suy nghĩ khi kết hợp |
|---|---|
| Hai thay đổi độc lập | Giữ cả hai nếu chúng không phá vỡ điều kiện chung |
| Hai thay đổi bổ sung | Kết hợp hành vi của cả hai, kể cả khi cần sắp xếp lại mã |
| Hai thay đổi cùng chỉnh một quy tắc | Dựa trên yêu cầu có hiệu lực và các điều kiện phải giữ đúng |
| Một thay đổi thay thế thiết kế cũ | Chuyển phần logic còn cần thiết sang thiết kế mới rồi bỏ phần cũ |
| Một bên xóa, bên kia sửa | Xác định file hoặc chức năng còn được sử dụng trước khi giữ hay xóa |

### Bước 4: Tạo kết quả rõ ràng

Sửa vùng xung đột thành nội dung hoàn chỉnh. Có thể giữ nguyên một phía, kết hợp hai phía, viết lại đoạn mã hoặc chuyển logic sang vị trí khác. Không bắt buộc kết quả phải giống nguyên văn một trong hai phiên bản.

Khi viết lại, giữ cho tên hàm, kiểu dữ liệu, điều kiện, thứ tự xử lý và thông báo lỗi nhất quán với hợp đồng xung quanh. Kiểm tra các import, lời gọi hàm, cấu hình và file liên quan vì xung đột ở một dòng có thể phản ánh thay đổi rộng hơn.

### Bước 5: Kiểm chứng trước khi tiếp tục

Đọc lại toàn bộ file sau khi sửa, kiểm tra các nhánh điều kiện và trường hợp biên. Sau đó xem diff, chạy kiểm tra phù hợp và xác nhận không còn dấu xung đột. Chỉ stage kết quả sau khi đã hiểu nội dung mình chuẩn bị đưa vào index.

## 4. Ví dụ: kết hợp hai chính sách thử lại

Giả sử phiên bản base có:

```java
public Result submit(Payment payment) {
    return gateway.send(payment);
}
```

Nhánh `feature/retry-network` bổ sung thử lại khi mạng tạm thời lỗi. Nhánh `feature/payment-safety` yêu cầu không gửi lại một khoản thanh toán nếu không biết lần gửi trước đã được xử lý hay chưa. Hai nhánh có thể cùng chỉnh đoạn xử lý lỗi và tạo xung đột.

Một cách xử lý sai là chọn toàn bộ nhánh retry vì nó có thêm khả năng phục hồi. Cách đó có thể gửi cùng một khoản thanh toán nhiều lần. Chọn toàn bộ nhánh safety cũng có thể bỏ mất khả năng phục hồi với lỗi chắc chắn chưa gửi yêu cầu.

Trước khi viết kết quả, cần xác định gateway có hỗ trợ idempotency key và phân biệt được lỗi xảy ra trước hay sau khi yêu cầu được chấp nhận hay không. Nếu hợp đồng cho phép thử lại an toàn bằng idempotency key, kết quả có thể được tổ chức như sau:

```java
public Result submit(Payment payment) {
    String idempotencyKey = payment.id();
    return retryPolicy.execute(() ->
        gateway.send(payment, idempotencyKey)
    );
}
```

Đoạn mã minh họa này chỉ phù hợp nếu `gateway.send` thực sự hỗ trợ idempotency key và máy chủ bảo đảm các yêu cầu lặp cùng khóa không tạo giao dịch mới. Nếu không có bảo đảm đó, không thể kết luận rằng thêm vòng retry là an toàn; cần thiết kế cơ chế truy vấn trạng thái hoặc đối soát trước khi gửi lại.

Các kiểm tra nên bao gồm ít nhất:

- Lỗi xảy ra trước khi gateway nhận yêu cầu.
- Gateway đã xử lý nhưng phản hồi bị mất trên đường truyền.
- Yêu cầu lặp lại với cùng idempotency key.
- Idempotency key bị dùng lại cho nội dung thanh toán khác.
- Hết số lần thử hoặc vượt thời gian xử lý cho phép.

Điểm quyết định nằm ở hợp đồng của hệ thống thanh toán. Git không thể suy ra hợp đồng đó từ hai đoạn mã.

## 5. Ví dụ: chuyển logic khi một nhánh đổi tên API

Base có phương thức:

```java
public Money calculateFee(Order order) {
    return feeCalculator.calculate(order);
}
```

Một nhánh đổi tên phương thức thành `calculateShippingFee` để làm rõ phạm vi. Nhánh còn lại thêm quy tắc giảm phí cho khách hàng thành viên vào phương thức cũ. Nếu chỉ chấp nhận phiên bản đổi tên, quy tắc giảm phí bị mất. Nếu chỉ chấp nhận phiên bản thêm giảm phí, thiết kế tên mới bị mất.

Kết quả có ý nghĩa có thể chuyển quy tắc giảm phí sang phương thức mới:

```java
public Money calculateShippingFee(Order order) {
    Money baseFee = feeCalculator.calculate(order);
    return memberDiscount.apply(order.customer(), baseFee);
}
```

Sau đó cần tìm mọi nơi gọi `calculateFee`, cập nhật theo hợp đồng mới hoặc duy trì một phương thức tương thích trong giai đoạn chuyển đổi nếu các module khác vẫn phụ thuộc vào API cũ. Cũng cần xác nhận `memberDiscount` đúng là giảm phí vận chuyển, không phải giảm tổng tiền đơn hàng hoặc một loại phí khác.

Có thể dùng tìm kiếm trong repository để rà soát lời gọi và định nghĩa liên quan, rồi chạy compile/test của các module phụ thuộc. Một file đã hết dấu xung đột không bảo đảm các lời gọi ở file khác đã được cập nhật.

## 6. Ví dụ: quyết định khi một bên xóa, một bên sửa

Giả sử nhánh A xóa `LegacyTokenValidator.java` vì hệ thống đã chuyển sang `TokenValidator`. Nhánh B sửa `LegacyTokenValidator.java` để bổ sung kiểm tra thời hạn token. Git có thể báo xung đột sửa/xóa.

Không nên khôi phục file chỉ vì nhánh B có thay đổi mới, cũng không nên xóa ngay chỉ vì nhánh A đã bỏ nó. Hãy xác minh:

1. Mọi nơi sử dụng đã chuyển sang `TokenValidator` chưa?
2. Quy tắc kiểm tra thời hạn ở nhánh B đã có trong validator mới chưa?
3. Có dữ liệu, cấu hình hoặc module nào vẫn cần API cũ không?
4. Có cần adapter tạm thời để tương thích ngược không?

Nếu validator mới chưa có quy tắc thời hạn, hãy chuyển quy tắc đó sang validator mới rồi giữ quyết định xóa file cũ. Nếu còn client phụ thuộc API cũ, cần giữ adapter hoặc lập kế hoạch chuyển đổi rõ ràng. Kết quả đúng có thể là xóa file cũ nhưng vẫn bảo toàn hành vi mà thay đổi của nhánh B mang lại.

## 7. Dùng công cụ giải quyết xung đột đúng cách

Các IDE và công cụ như merge editor thường chia màn hình thành phiên bản hiện tại, phiên bản được đưa vào và kết quả cuối cùng. Chúng giúp chọn từng khối hoặc chỉnh trực tiếp kết quả, nhưng nhãn “Accept Current”, “Accept Incoming” hay “Accept Both” chỉ là thao tác trên nội dung. Người giải quyết vẫn phải xác nhận ý nghĩa của kết quả.

Một số lưu ý:

- **Accept Current:** phù hợp khi yêu cầu đã xác nhận rằng nội dung phía hiện tại là kết quả cần giữ cho vùng đó.
- **Accept Incoming:** phù hợp khi thay đổi phía được đưa vào đã thay thế đúng logic cũ và không làm mất yêu cầu còn hiệu lực.
- **Accept Both:** chỉ hữu ích khi hai phần có thể cùng tồn tại. Ghép hai đoạn liên tiếp có thể tạo mã trùng, sai thứ tự hoặc thực thi cùng hành động hai lần.
- **Chỉnh sửa thủ công:** thường cần thiết khi phải kết hợp điều kiện, đổi cấu trúc hoặc chuyển logic sang API mới.

Nếu dùng công cụ dòng lệnh hoặc IDE để lấy nguyên một phía, hãy nhớ thao tác đó có thể ghi đè nội dung đang sửa trong working tree. Chỉ thực hiện sau khi đã xem các phiên bản và hiểu rõ nội dung sẽ bị thay thế.

## 8. Kiểm tra kết quả trước khi đánh dấu đã giải quyết

Sau khi chỉnh sửa, thực hiện các kiểm tra phù hợp với loại thay đổi:

```bash
git diff -- path/to/file
git diff --check
git status
```

Đọc diff để xác nhận kết quả có đủ logic từ các thay đổi cần giữ. `git diff --check` phát hiện một số lỗi khoảng trắng trong diff; nó không chứng minh mã đúng và cũng không thay thế việc tìm dấu xung đột.

Có thể tìm các dấu đánh dấu còn sót trong file đang xử lý bằng tìm kiếm văn bản, ví dụ:

```bash
rg -n '^(<<<<<<<|=======|>>>>>>>)' path/to/file
```

Lệnh tìm kiếm có thể khớp các dòng phân cách hợp lệ trong một số định dạng tài liệu; hãy đọc kết quả thay vì xóa tự động. Sau đó chạy test đơn vị cho logic vừa sửa, test tích hợp cho hợp đồng giữa các module và build phù hợp với phạm vi thay đổi.

Khi kết quả đã được xác minh, đánh dấu đường dẫn đã giải quyết:

```bash
git add path/to/file
git diff --cached -- path/to/file
git status
```

`git add` đưa phiên bản working tree vào index và đánh dấu đường dẫn không còn trạng thái unmerged. Git không kiểm tra nội dung có còn dấu xung đột hay không; vì vậy, một file vẫn chứa marker có thể được stage như thể đã giải quyết. Hãy đọc diff đã stage trước khi tiếp tục.

Khi tất cả đường dẫn đã được giải quyết và kiểm tra đạt, tiếp tục thao tác đang dừng:

```bash
git merge --continue
```

Hoặc, nếu đang rebase:

```bash
git rebase --continue
```

Chỉ dùng lệnh tương ứng với trạng thái Git hiện tại. Nếu còn xung đột ở commit tiếp theo trong rebase, tiếp tục quy trình xem xét và kiểm chứng cho commit đó.

## 9. Danh sách tự kiểm tra

Trước khi kết luận một xung đột đã được giải quyết đúng, hãy tự trả lời:

- Tôi hiểu mục đích của thay đổi ở cả hai phía chưa?
- Tôi đã xem base hoặc lịch sử để biết nội dung gốc chưa?
- Kết quả có giữ các quy tắc nghiệp vụ và hợp đồng đang có hiệu lực không?
- Tôi đã rà soát các nơi gọi hàm, cấu hình, dữ liệu và module phụ thuộc chưa?
- Các trường hợp lỗi, biên và tình huống lặp đã được cân nhắc chưa?
- Tôi đã xem lại diff, tìm marker còn sót và chạy test phù hợp chưa?
- Nội dung trong index có đúng là phiên bản cuối cùng tôi muốn đưa vào merge hoặc rebase không?

## 10. Ghi nhớ

Đừng đánh giá kết quả bằng việc các dấu xung đột đã biến mất. Hãy đọc base và cả hai phía, xác định mục đích cùng điều kiện cần bảo toàn, rồi tạo ra hành vi phù hợp với hợp đồng của hệ thống. Có lúc cần chọn một phía, có lúc cần kết hợp hoặc viết lại cả hai. Chỉ đánh dấu đã giải quyết sau khi đã kiểm tra nội dung, các phụ thuộc và hành vi của kết quả.
