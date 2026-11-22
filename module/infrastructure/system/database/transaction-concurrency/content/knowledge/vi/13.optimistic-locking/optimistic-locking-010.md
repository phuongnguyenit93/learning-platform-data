# Chọn khóa lạc quan hay bi quan theo mức tranh chấp

Khi nhiều giao dịch có thể cùng thay đổi một dữ liệu, ứng dụng cần một cơ chế bảo vệ để tránh ghi đè kết quả hoặc đưa dữ liệu vào trạng thái không hợp lệ. Hai chiến lược thường dùng là **khóa lạc quan** (*optimistic locking*) và **khóa bi quan** (*pessimistic locking*).

Khóa lạc quan giả định xung đột không thường xuyên. Giao dịch đọc dữ liệu và xử lý trước, sau đó kiểm tra dữ liệu vẫn chưa bị thay đổi khi ghi. Nếu phát hiện phiên bản đã đổi, giao dịch thất bại và ứng dụng quyết định đọc lại, tính toán lại hoặc báo xung đột.

Khóa bi quan giả định xung đột có khả năng xảy ra và cần được điều phối trước khi cập nhật. Giao dịch lấy khóa trên tài nguyên trước khi đọc hoặc sửa; giao dịch khác cần khóa xung đột phải chờ, bị từ chối hoặc bỏ qua tùy chính sách.

Việc chọn chiến lược nên dựa trên **mức tranh chấp thực tế**, thời gian giao dịch, chi phí chờ, chi phí retry, yêu cầu phản hồi và khả năng phục hồi của nghiệp vụ. Không có một chiến lược luôn tốt hơn trong mọi hệ thống.

## 1. Hai chiến lược bảo vệ cập nhật

### Khóa lạc quan: kiểm tra khi ghi

Một cách triển khai phổ biến là thêm cột phiên bản (`version`) vào bảng. Khi đọc, ứng dụng lấy cả dữ liệu và phiên bản. Khi cập nhật, câu lệnh chỉ thành công nếu phiên bản trong cơ sở dữ liệu vẫn bằng phiên bản đã đọc. Nếu một giao dịch khác đã cập nhật trước, điều kiện không còn đúng và câu lệnh không sửa hàng nào.

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

```sql
-- Ứng dụng đọc dữ liệu và ghi nhớ version = 12
SELECT balance, version
FROM account
WHERE id = 10;

-- Khi cập nhật, chỉ ghi nếu version vẫn là 12
UPDATE account
SET balance = 900.00,
    version = version + 1
WHERE id = 10
  AND version = 12;
```

Nếu câu `UPDATE` ảnh hưởng đúng một hàng, cập nhật đã thành công. Nếu ảnh hưởng không hàng nào, dữ liệu đã thay đổi hoặc hàng không còn tồn tại; ứng dụng cần phân biệt hai trường hợp nếu nghiệp vụ yêu cầu. Trường hợp phiên bản không khớp thường được gọi là *optimistic lock conflict*.

Điểm quan trọng là kiểm tra phiên bản và ghi dữ liệu nằm trong **cùng một câu lệnh cập nhật có điều kiện**. Nếu ứng dụng chỉ đọc `version`, so sánh trong bộ nhớ rồi chạy một câu `UPDATE` không có điều kiện phiên bản, một giao dịch khác vẫn có thể cập nhật chen vào giữa bước kiểm tra và bước ghi.

Khóa lạc quan không có nghĩa cơ sở dữ liệu hoàn toàn không dùng khóa. Khi thực hiện câu `UPDATE`, hệ quản trị vẫn cần điều phối quyền ghi trên hàng và có thể khiến giao dịch khác chờ. Khác biệt chính là ứng dụng không chủ động giữ khóa từ lúc đọc trong suốt quá trình xử lý; xung đột được phát hiện bằng điều kiện phiên bản tại thời điểm ghi.

### Khóa bi quan: lấy quyền truy cập trước khi xử lý

Khóa bi quan thường dùng khóa hàng hoặc tài nguyên tương đương để ngăn giao dịch khác thực hiện thao tác xung đột trong lúc giao dịch hiện tại xử lý.

```sql
BEGIN;

SELECT balance
FROM account
WHERE id = 10
FOR UPDATE;

-- Tính toán và cập nhật trong cùng transaction
UPDATE account
SET balance = balance - 100.00
WHERE id = 10;

COMMIT;
```

`SELECT ... FOR UPDATE` là cú pháp phổ biến trong PostgreSQL, MySQL InnoDB và một số hệ quản trị khác, nhưng chi tiết khóa và phạm vi ảnh hưởng phụ thuộc sản phẩm. Khi T1 giữ khóa, giao dịch khác muốn cập nhật cùng hàng phải chờ hoặc thất bại theo chính sách timeout/NOWAIT. Sau khi T1 commit hoặc rollback, khóa được giải phóng.

Khóa bi quan phù hợp khi giao dịch có khả năng gặp xung đột cao và việc để nhiều giao dịch cùng xử lý rồi thất bại ở cuối sẽ tốn kém. Đổi lại, giao dịch phải giữ khóa trong thời gian xử lý và có thể làm giao dịch khác chờ.

## 2. Mức tranh chấp ảnh hưởng đến chi phí ra sao?

Hãy hình dung một hàng tồn kho có nhiều người cùng mua sản phẩm. Nếu chỉ thỉnh thoảng hai người cùng mua đúng lúc, khóa lạc quan có thể cho phần lớn giao dịch hoàn tất mà không cần chờ khóa từ lúc đọc. Một số ít giao dịch phát hiện phiên bản thay đổi và phải thử lại hoặc báo hết hàng.

Nếu hàng tồn kho là một sản phẩm rất phổ biến và có hàng trăm yêu cầu cập nhật đồng thời, nhiều giao dịch có thể cùng đọc một phiên bản. Sau đó, chỉ một số giao dịch có thể cập nhật phiên bản đó; những giao dịch còn lại thất bại và phải đọc lại, tính toán lại. Công việc bị lặp có thể tạo thêm tải cho ứng dụng và cơ sở dữ liệu.

Khóa bi quan trên hàng nóng sẽ điều phối các giao dịch trước khi chúng đọc và cập nhật. Các giao dịch lần lượt xử lý theo thứ tự được cấp khóa. Điều này có thể tránh nhiều lần tính toán rồi thất bại, nhưng hàng nóng trở thành hàng đợi và giới hạn tốc độ xử lý theo thời gian giữ khóa.

| Đặc điểm tải | Khóa lạc quan thường có lợi | Khóa bi quan thường có lợi |
|---|---|---|
| Xác suất hai giao dịch cùng sửa một hàng | Thấp | Cao |
| Thời gian xử lý trước khi ghi | Ngắn hoặc có thể tính lại rẻ | Dài hoặc tính lại rất tốn kém |
| Chi phí khi xung đột | Có thể retry hoặc báo xung đột | Chờ khóa trong thời gian có thể dự đoán |
| Số lượng yêu cầu trên một hàng nóng | Ít hoặc phân tán trên nhiều hàng | Tập trung cao trên cùng hàng |
| Nhu cầu phản hồi khi dữ liệu đổi | Chấp nhận báo conflict và xử lý lại | Cần giữ quyền cập nhật trong lúc quyết định |
| Khả năng tự động retry | Cao, thao tác có thể lặp an toàn | Vẫn cần xử lý deadlock/timeout nhưng ít tính lại do stale version |

Đây là xu hướng, không phải quy luật tuyệt đối. Một giao dịch bi quan vẫn có thể gặp deadlock hoặc timeout. Một hệ thống lạc quan vẫn có thể hoạt động tốt ở tải ghi cao nếu cập nhật được phân vùng, có thao tác nguyên tử hoặc xung đột thực tế thấp trên từng hàng.

## 3. Ví dụ: khóa lạc quan với cột version

Giả sử số dư tài khoản ban đầu là 1.000 và `version = 5`. T1 và T2 cùng đọc dữ liệu này.

```text
T1 đọc: balance = 1.000, version = 5
T2 đọc: balance = 1.000, version = 5

T1 cập nhật WHERE version = 5
  -> thành công, balance = 900, version = 6

T2 cập nhật WHERE version = 5
  -> không có hàng nào được cập nhật
  -> phát hiện xung đột phiên bản
```

T2 không được phép ghi giá trị tính từ phiên bản cũ đè lên kết quả của T1. Ứng dụng có thể đọc lại hàng, đánh giá nghiệp vụ với số dư mới rồi quyết định có tiếp tục hay không.

Ví dụ xử lý ở tầng ứng dụng:

```text
Đọc hàng và version
       |
Tính thay đổi trong bộ nhớ
       |
UPDATE ... WHERE id = ? AND version = ?
       |
       +-- affected rows = 1 --> thành công
       |
       +-- affected rows = 0 --> xung đột hoặc hàng không tồn tại
                                  |
                                  +-- đọc lại và đánh giá lại
                                  +-- hoặc trả lỗi conflict
```

Không nên retry vô hạn. Nếu hàng liên tục bị cập nhật, một request có thể liên tục thua cuộc và tiêu tốn tài nguyên. Cần giới hạn số lần thử, dùng backoff phù hợp và trả lỗi xung đột khi không thể hoàn tất trong ngân sách thời gian.

### Version phải thay đổi trong mọi đường ghi

Chiến lược optimistic locking chỉ hiệu quả khi mọi thao tác có thể làm thay đổi dữ liệu đều cập nhật cột phiên bản. Nếu một câu SQL, batch job hoặc công cụ quản trị sửa `balance` nhưng không tăng `version`, giao dịch khác có thể không phát hiện dữ liệu đã đổi.

Có thể cập nhật nhiều trường cùng lúc:

```sql
UPDATE product
SET price = 120.00,
    quantity = 8,
    version = version + 1
WHERE id = 25
  AND version = 14;
```

Nếu cập nhật không thành công, ứng dụng cần đọc lại cả dữ liệu lẫn version. Không dùng version cũ để lặp lại cùng một câu lệnh, vì điều kiện sẽ tiếp tục không khớp.

## 4. Ví dụ: khóa bi quan với SELECT FOR UPDATE

Khóa bi quan thích hợp khi quyết định cập nhật cần dựa trên dữ liệu hiện hành và ứng dụng muốn ngăn giao dịch khác thay đổi hàng trong lúc quyết định đó được thực hiện.

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 25
FOR UPDATE;

-- Ứng dụng kiểm tra quantity sau khi đã lấy khóa.
-- Nếu đủ hàng thì mới trừ số lượng.

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 25
  AND quantity >= 2;

COMMIT;
```

Nếu hai giao dịch cùng muốn trừ hàng, giao dịch thứ hai phải chờ khóa hoặc nhận lỗi theo chính sách đã cấu hình. Sau khi giao dịch thứ nhất commit, giao dịch thứ hai tiếp tục và phải đánh giá trạng thái mới theo ngữ nghĩa đọc của hệ quản trị.

Điều kiện `quantity >= 2` trong câu `UPDATE` vẫn hữu ích như một lớp bảo vệ bổ sung. Nếu thao tác cập nhật không ảnh hưởng hàng nào, ứng dụng cần rollback hoặc xử lý kết quả không đủ hàng. Không nên chỉ dựa vào giá trị đã đọc mà bỏ qua điều kiện bảo vệ ở bước ghi.

## 5. Chi phí cần so sánh

Để lựa chọn đúng, hãy so sánh tổng chi phí của cả hai chiến lược, không chỉ thời gian của một câu SQL.

### Chi phí của khóa lạc quan

- Đọc và giữ giá trị version trong ứng dụng.
- Thêm điều kiện phiên bản vào câu lệnh ghi và kiểm tra số hàng bị ảnh hưởng.
- Tính toán có thể bị lặp nếu xung đột xảy ra sau một quá trình xử lý dài.
- Retry có thể tạo thêm tải đọc/ghi khi nhiều giao dịch cùng tranh chấp.
- Ứng dụng phải xử lý trạng thái conflict và đảm bảo thao tác lặp an toàn.

### Chi phí của khóa bi quan

- Giao dịch có thể phải chờ trước khi bắt đầu xử lý dữ liệu.
- Khóa được giữ trong thời gian transaction, làm giảm khả năng đồng thời trên tài nguyên nóng.
- Giao dịch giữ khóa lâu có thể làm tăng độ trễ và tạo hàng đợi.
- Khóa nhiều tài nguyên theo thứ tự khác nhau có thể gây deadlock.
- Cần cấu hình timeout, quan sát lock wait và xử lý lỗi deadlock/timeout.

### Đánh giá tổng chi phí

Một mô hình suy nghĩ đơn giản:

```text
Chi phí lạc quan ≈ chi phí đọc/kiểm tra
                  + xác suất xung đột × chi phí retry

Chi phí bi quan ≈ chi phí lấy khóa
                 + thời gian chờ do giao dịch khác giữ khóa
                 + chi phí quản lý deadlock/timeout
```

Đây không phải công thức định lượng chính xác; nó nhắc rằng lựa chọn phụ thuộc cả xác suất xung đột và giá phải trả khi xung đột xảy ra. Nếu xử lý trước khi ghi rất tốn kém, ngay cả xác suất xung đột vừa phải cũng có thể khiến retry trở nên đắt. Nếu giao dịch giữ khóa lâu, khóa bi quan có thể tạo hàng đợi lớn dù số lần retry giảm.

## 6. Chọn theo kiểu tải công việc

### Tải đọc nhiều, cập nhật phân tán

Ví dụ: hồ sơ người dùng, cấu hình, thông tin sản phẩm ít được sửa nhưng được đọc thường xuyên. Nhiều request có thể đọc cùng một hàng, nhưng hiếm khi hai request cùng cập nhật nó.

Khóa lạc quan thường là lựa chọn phù hợp. Phần lớn cập nhật hoàn tất với version hiện tại; khi có xung đột hiếm, ứng dụng có thể thông báo hoặc tải lại dữ liệu để người dùng xác nhận.

### Tải ghi có xung đột thấp

Ví dụ: các giao dịch cập nhật những đơn hàng khác nhau hoặc các bản ghi thuộc những khách hàng khác nhau. Tổng số giao dịch có thể lớn nhưng xác suất hai giao dịch cùng sửa một hàng thấp.

Khóa lạc quan thường giúp tránh giữ khóa sớm trên từng bản ghi. Điều quan trọng là mỗi thao tác phải kiểm tra version và có cách xử lý khi cập nhật không thành công.

### Một hàng nóng được cập nhật liên tục

Ví dụ: một bản ghi biểu diễn trạng thái duy nhất của sự kiện, một hạn mức dùng chung hoặc một sản phẩm có lượng mua rất lớn. Nhiều giao dịch thường xuyên tranh chấp cùng hàng.

Khóa bi quan có thể phù hợp nếu mỗi giao dịch cần đọc trạng thái mới nhất rồi đưa ra quyết định có điều kiện. Nó làm cho việc tranh quyền xảy ra trước khi tính toán và giảm số lần tính toán dựa trên version đã cũ. Tuy nhiên, nếu thời gian giữ khóa dài, hàng này sẽ trở thành nút thắt. Khi đó cần xem xét phân vùng dữ liệu, bộ đếm theo shard, cập nhật nguyên tử hoặc thiết kế lại mô hình nghiệp vụ.

### Tính toán dài hoặc có tương tác người dùng

Ví dụ: người dùng mở biểu mẫu, chỉnh sửa trong vài phút rồi lưu. Không nên giữ transaction và khóa bi quan suốt thời gian người dùng thao tác. Khóa lạc quan với version phù hợp hơn: khi lưu, hệ thống kiểm tra dữ liệu có bị thay đổi từ lúc tải biểu mẫu hay không. Nếu có, hiển thị xung đột và cho người dùng tải lại hoặc hợp nhất thay đổi.

### Quyết định cần bảo vệ tức thời

Ví dụ: trừ số lượng hàng còn lại, đặt chỗ cuối cùng hoặc chuyển một công việc từ `READY` sang `PROCESSING`. Nếu quyết định cần dựa trên trạng thái mới nhất và không thể để hai giao dịch cùng nhận một quyền, khóa bi quan hoặc câu lệnh cập nhật nguyên tử có điều kiện thường phù hợp.

## 7. Không phải mọi cập nhật đều cần một trong hai mẫu khóa

Với thao tác đơn giản, một câu lệnh cập nhật nguyên tử có điều kiện có thể bảo vệ bất biến trực tiếp mà không cần ứng dụng đọc trước rồi mới ghi.

Ví dụ trừ số lượng tồn kho:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 25
  AND quantity >= 2;
```

Nếu số hàng bị cập nhật là 1, thao tác trừ hàng thành công. Nếu là 0, sản phẩm không tồn tại hoặc số lượng không đủ; ứng dụng có thể truy vấn thêm nếu cần phân biệt. Cơ sở dữ liệu điều phối cập nhật nguyên tử trên hàng.

Mẫu này thường tốt hơn việc đọc số lượng vào ứng dụng, tính giá trị mới rồi ghi lại một giá trị tuyệt đối. Tuy nhiên, nếu nghiệp vụ cần đọc nhiều hàng hoặc phối hợp nhiều bước, vẫn cần transaction và cơ chế bảo vệ phù hợp.

## 8. Có thể kết hợp khóa lạc quan và bi quan

Hai chiến lược không loại trừ nhau ở cấp toàn hệ thống. Một ứng dụng có thể chọn cơ chế khác nhau cho từng loại dữ liệu hoặc từng thao tác:

- Dùng version cho hồ sơ người dùng được chỉnh sửa không thường xuyên.
- Dùng `SELECT FOR UPDATE` cho hàng tồn kho có tranh chấp cao và cần kiểm tra rồi cập nhật trong cùng transaction.
- Dùng cập nhật nguyên tử có điều kiện cho bộ đếm hoặc hạn mức đơn giản.
- Dùng `SERIALIZABLE` và retry cho một số nghiệp vụ có bất biến nhiều hàng khó bảo vệ bằng khóa cục bộ.

Ngay cả trong cùng một transaction, có thể dùng khóa bi quan cho một hàng nóng và version check cho các dữ liệu khác. Cần tránh tạo ra thứ tự lấy khóa không nhất quán giữa các luồng, vì điều đó có thể làm tăng nguy cơ deadlock.

## 9. Retry an toàn và tác động phụ bên ngoài

Khóa lạc quan thường cần retry khi version không khớp. Khóa bi quan cũng có thể cần retry sau deadlock hoặc timeout. Trong cả hai trường hợp, retry phải chạy lại **toàn bộ đơn vị nghiệp vụ** nếu quyết định phụ thuộc vào dữ liệu đã đọc trước đó.

Không nên đặt tác động bên ngoài không thể đảo ngược bên trong một vòng retry. Ví dụ, nếu transaction gửi email, trừ tiền qua cổng thanh toán hoặc gọi API bên ngoài rồi sau đó bị rollback, lần retry có thể gửi hoặc thực hiện tác động đó lần thứ hai.

Một cách thiết kế phổ biến là chỉ thực hiện thay đổi cơ sở dữ liệu trong transaction, ghi một sự kiện vào bảng outbox cùng transaction, rồi worker riêng gửi sự kiện sau khi commit. Worker cần xử lý idempotency để một sự kiện được gửi lại không tạo ra tác động trùng lặp.

Ví dụ luồng:

```text
BEGIN
  kiểm tra và cập nhật dữ liệu
  ghi outbox event với id duy nhất
COMMIT
       |
       v
Worker đọc outbox
  gửi thông báo với idempotency key
  đánh dấu event đã xử lý
```

Nếu transaction bị conflict và rollback, outbox event cũng bị rollback. Nếu transaction commit nhưng worker bị gián đoạn, worker có thể gửi lại theo chính sách idempotency.

## 10. Đo mức tranh chấp trước khi quyết định

Không nên chỉ dựa vào tổng số transaction mỗi giây. Một hệ thống có hàng nghìn transaction mỗi giây nhưng mỗi transaction sửa một hàng khác nhau có thể có mức tranh chấp thấp. Một hệ thống có ít transaction hơn nhưng tất cả cùng cập nhật một hàng có thể có mức tranh chấp rất cao.

Hãy quan sát theo **tài nguyên hoặc nhóm dữ liệu**:

- Tỷ lệ cập nhật thất bại do version không khớp.
- Số lần retry trung bình và phân bố số lần retry trên mỗi thao tác.
- Thời gian chờ khóa trung vị, p95 và p99.
- Số transaction bị deadlock hoặc lock timeout.
- Thời gian transaction giữ khóa và các câu lệnh có thời gian thực thi dài.
- Những hàng hoặc khóa chỉ mục xuất hiện thường xuyên trong báo cáo lock wait.
- Tỷ lệ cập nhật thành công trên mỗi lần thử và lượng công việc tính toán bị bỏ đi do conflict.

Đối với optimistic locking, tỷ lệ conflict có thể tính theo:

\[
\text{Conflict rate} =
\frac{\text{Số lần cập nhật thất bại do version mismatch}}
{\text{Tổng số lần cập nhật có kiểm tra version}}
\times 100\%
\]

Chỉ số này cần được đọc cùng chi phí retry. Một conflict rate thấp nhưng mỗi lần retry rất đắt vẫn có thể gây ảnh hưởng lớn. Ngược lại, một số conflict nhẹ với thao tác tính lại nhanh có thể chấp nhận được.

Thực hiện đo trong tải đại diện cho giờ cao điểm và các đợt batch. Nếu chuyển từ optimistic sang pessimistic, theo dõi lock wait và thông lượng sau thay đổi. Nếu chuyển theo chiều ngược lại, theo dõi conflict rate, số lần retry và tỷ lệ request không hoàn tất.

## 11. Quy trình lựa chọn

Có thể dùng các câu hỏi sau để quyết định:

1. **Có nhiều giao dịch thực sự sửa cùng một tài nguyên không?** Nếu không, optimistic locking thường đơn giản và hiệu quả.
2. **Nếu hai giao dịch cùng sửa, chi phí tính toán lại có lớn không?** Nếu lớn và xung đột phổ biến, cân nhắc khóa bi quan để điều phối sớm.
3. **Transaction giữ khóa trong bao lâu?** Nếu phải giữ khóa qua thao tác chậm hoặc tương tác người dùng, tránh khóa bi quan trong khoảng thời gian đó.
4. **Có thể diễn đạt nghiệp vụ thành một câu lệnh cập nhật nguyên tử có điều kiện không?** Nếu có, đây có thể là lựa chọn gọn và an toàn hơn.
5. **Có thể retry toàn bộ nghiệp vụ an toàn không?** Nếu không, cần thiết kế lại ranh giới transaction và các tác động phụ trước khi chọn optimistic locking.
6. **Xung đột tập trung ở một hàng nóng hay phân tán trên nhiều hàng?** Hàng nóng có thể cần điều phối bi quan, phân vùng hoặc mô hình dữ liệu khác.
7. **Dữ liệu có bất biến nhiều hàng không?** Nếu có, version trên từng hàng có thể chưa đủ; cần guard row, aggregate, constraint hoặc mức `SERIALIZABLE` phù hợp.

| Kết quả phân tích | Hướng lựa chọn ban đầu |
|---|---|
| Xung đột hiếm, thao tác tính lại rẻ | Optimistic locking |
| Xung đột thường xuyên trên cùng hàng, cần quyết định theo trạng thái hiện hành | Pessimistic locking hoặc cập nhật nguyên tử có điều kiện |
| Người dùng chỉnh sửa lâu rồi mới lưu | Optimistic locking và xử lý conflict ở giao diện |
| Một hàng nóng, thời gian giữ khóa dài | Xem xét phân vùng, atomic update hoặc thiết kế lại trước khi tăng khóa bi quan |
| Bất biến phụ thuộc nhiều hàng | Guard/aggregate hoặc SERIALIZABLE; version đơn lẻ có thể không đủ |

## 12. Những điểm cần nhớ

- Khóa lạc quan phát hiện xung đột tại thời điểm ghi, thường bằng cột version và câu `UPDATE` có điều kiện.
- Khóa bi quan lấy quyền truy cập trước khi đọc hoặc cập nhật, khiến giao dịch xung đột phải chờ hoặc thất bại.
- Mức tranh chấp nên được đo trên từng hàng hoặc nhóm dữ liệu, không chỉ nhìn tổng lưu lượng của hệ thống.
- Xung đột hiếm và retry rẻ thường phù hợp với optimistic locking.
- Xung đột thường xuyên, tính toán lại đắt và quyết định cần dựa trên trạng thái hiện hành có thể phù hợp với pessimistic locking.
- Khóa bi quan có chi phí hàng đợi, lock wait và deadlock; khóa lạc quan có chi phí conflict, retry và công việc bị lặp.
- Cập nhật nguyên tử có điều kiện có thể bảo vệ các quy tắc đơn giản mà không cần đọc trước rồi ghi sau.
- Retry cần chạy lại toàn bộ logic phụ thuộc dữ liệu và phải kiểm soát tác động phụ bên ngoài bằng idempotency hoặc outbox.
- Một hệ thống có thể kết hợp nhiều chiến lược theo loại dữ liệu và đặc điểm tải.

Hãy chọn chiến lược sau khi hiểu nơi xảy ra tranh chấp, thời gian giữ tài nguyên và giá phải trả khi một giao dịch phải thử lại. Optimistic locking phù hợp khi phần lớn cập nhật độc lập; pessimistic locking phù hợp khi cần điều phối trước các giao dịch thường xuyên tranh cùng tài nguyên. Đo tải thực tế và kiểm tra lại sau khi triển khai để lựa chọn tiếp tục phù hợp với hành vi của hệ thống.
