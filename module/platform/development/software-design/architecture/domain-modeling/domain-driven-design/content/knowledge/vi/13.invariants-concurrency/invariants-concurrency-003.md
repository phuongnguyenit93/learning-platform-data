# Cạnh tranh cập nhật và các tình huống lost update

Trong một hệ thống có nhiều người dùng hoặc tiến trình cùng hoạt động, hai yêu cầu có thể đọc và thay đổi cùng một dữ liệu gần như đồng thời. Mỗi yêu cầu có thể hợp lệ khi xét riêng, nhưng kết quả kết hợp lại có thể làm mất một thay đổi hoặc phá vỡ quy tắc nghiệp vụ. Hiện tượng này thường xuất hiện khi hệ thống thực hiện chuỗi đọc, tính toán rồi ghi mà không kiểm soát việc dữ liệu đã bị thay đổi bởi một giao dịch khác.

Một ví dụ điển hình là **lost update (mất cập nhật)**: hai giao dịch cùng đọc một giá trị cũ, mỗi giao dịch tính ra một giá trị mới, sau đó giao dịch ghi sau ghi đè kết quả của giao dịch ghi trước. Hệ thống vẫn có thể trả về thành công cho cả hai yêu cầu, nhưng một thay đổi đã biến mất.

Trong Domain-Driven Design (DDD), cạnh tranh cập nhật liên quan trực tiếp đến invariant, aggregate và consistency boundary. Aggregate root có trách nhiệm bảo vệ quy tắc của aggregate, nhưng việc nhiều giao dịch cùng thay đổi một aggregate vẫn cần cơ chế concurrency control ở tầng persistence hoặc database. Bài học này giải thích lost update, các dạng bất thường khi truy cập đồng thời và cách lựa chọn chiến lược bảo vệ dữ liệu.

## 1. Cạnh tranh cập nhật là gì?

**Cạnh tranh cập nhật (concurrent update)** xảy ra khi nhiều giao dịch hoặc tiến trình cùng đọc, kiểm tra hoặc thay đổi một phần dữ liệu có liên quan trong khoảng thời gian chồng lấn. Các giao dịch có thể chạy trên nhiều thread, nhiều instance ứng dụng hoặc nhiều máy chủ. Vì vậy, chỉ dùng `synchronized` trong một JVM không đủ để bảo vệ dữ liệu được nhiều instance cùng truy cập.

Ví dụ, một kho chỉ còn 1 sản phẩm. Hai khách hàng gần như đồng thời đặt mỗi người 1 sản phẩm. Cả hai yêu cầu cùng đọc số lượng còn lại là 1 và kết luận rằng có thể đặt hàng. Nếu không có cơ chế phối hợp, hệ thống có thể xác nhận hai đơn trong khi chỉ có một sản phẩm.

Một ví dụ khác là số dư tài khoản. Số dư ban đầu là 1.000.000 VND. Hai giao dịch độc lập cùng rút 100.000 VND. Nếu cả hai cùng đọc số dư ban đầu và ghi số dư mới là 900.000 VND, hệ thống chỉ phản ánh một lần rút dù đã chấp nhận hai giao dịch.

Vấn đề không nằm ở việc các request đến cùng thời điểm một cách tuyệt đối. Chỉ cần khoảng thời gian đọc và ghi của chúng chồng lấn, một giao dịch có thể dùng dữ liệu đã cũ khi quyết định ghi.

## 2. Lost update: một thay đổi bị ghi đè

Lost update thường xảy ra với thao tác read-modify-write: đọc giá trị hiện tại, tính giá trị mới trong ứng dụng rồi ghi lại toàn bộ giá trị mới.

Giả sử số lượng tồn kho ban đầu là 10. Hai giao dịch A và B đều muốn giảm số lượng đi 1.

| Thời điểm | Giao dịch A | Giao dịch B | Giá trị trong database |
| --- | --- | --- | ---: |
| 1 | Đọc số lượng = 10 | | 10 |
| 2 | | Đọc số lượng = 10 | 10 |
| 3 | Tính số lượng mới = 9 | | 10 |
| 4 | | Tính số lượng mới = 9 | 10 |
| 5 | Ghi số lượng = 9 | | 9 |
| 6 | | Ghi số lượng = 9 | 9 |

Kết quả cuối cùng là 9, trong khi hai lần giảm lẽ ra phải đưa số lượng về 8. Lần ghi của B đã ghi đè kết quả mà A vừa lưu.

```text
Ban đầu: quantity = 10

Transaction A                 Transaction B
-------------                 -------------
READ 10                       READ 10
CALCULATE 9                   CALCULATE 9
WRITE 9                       WRITE 9
       \                       /
        +---- final = 9 ------+

Kết quả mong đợi nếu cả hai lần giảm được ghi nhận: 8
```

Điểm nguy hiểm là cả hai giao dịch có thể kết thúc mà không có lỗi kỹ thuật. Nếu ứng dụng không kiểm tra xung đột, log có thể cho thấy hai request thành công trong khi dữ liệu cuối cùng chỉ chứa một thay đổi.

### 2.1. Lost update không chỉ xảy ra với phép cộng trừ

Hiện tượng này có thể xảy ra với nhiều loại dữ liệu:

- Hai nhân viên sửa cùng hồ sơ khách hàng, người lưu sau ghi đè địa chỉ hoặc số điện thoại người trước vừa cập nhật.
- Hai tiến trình cập nhật trạng thái đơn hàng dựa trên cùng một trạng thái cũ.
- Hai giao dịch điều chỉnh hạn mức hoặc số dư tài khoản.
- Một tác vụ nền cập nhật toàn bộ bản ghi từ snapshot cũ, làm mất trường vừa được cập nhật bởi request khác.
- Hai người cùng chỉnh sửa nội dung tài liệu hoặc cấu hình.

Không phải mọi lần ghi đè đều là lost update. Nếu nghiệp vụ quy định rõ “giá trị mới nhất được ưu tiên”, ghi sau có thể là hành vi mong muốn. Lost update là vấn đề khi một thay đổi đáng lẽ phải được bảo toàn nhưng bị mất do thiếu kiểm soát cạnh tranh.

## 3. Phân biệt lost update với các bất thường đồng thời khác

Lost update là một dạng vấn đề concurrency, nhưng không phải dạng duy nhất. Nhận diện đúng hiện tượng giúp chọn cơ chế bảo vệ phù hợp.

| Hiện tượng | Mô tả | Ví dụ |
| --- | --- | --- |
| Lost update | Một lần ghi dựa trên dữ liệu cũ ghi đè thay đổi của giao dịch khác | Hai lần giảm tồn kho cùng đọc 10 rồi đều ghi 9 |
| Dirty read | Một giao dịch đọc dữ liệu chưa commit của giao dịch khác | B đọc số dư do A cập nhật, sau đó A rollback |
| Non-repeatable read | Cùng một truy vấn đọc một hàng nhiều lần nhưng thấy giá trị khác do giao dịch khác đã commit | A đọc trạng thái đơn là `PENDING`, B đổi thành `CONFIRMED`, A đọc lại thấy `CONFIRMED` |
| Phantom read | Cùng một điều kiện truy vấn trả về tập hàng khác nhau giữa các lần đọc | A đếm các đơn đang chờ, B thêm đơn mới, A đếm lại thấy số lượng tăng |
| Write skew | Các giao dịch đọc cùng một tập dữ liệu rồi ghi những hàng khác nhau, khiến invariant chung bị vi phạm | Hai bác sĩ cùng thấy người kia đang trực nên mỗi người tự rời ca, kết quả không còn ai trực |

Các hệ quản trị cơ sở dữ liệu và mức isolation có thể xử lý những bất thường này khác nhau. Không nên suy ra rằng chọn một mức isolation có tên giống nhau sẽ tạo cùng hành vi trên mọi database. Cần kiểm tra tài liệu của hệ quản trị đang sử dụng và kiểm thử với lịch giao dịch thực tế.

## 4. Vì sao kiểm tra invariant trong domain model vẫn chưa đủ?

Giả sử aggregate `InventoryItem` có phương thức:

```java
public void reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
    if (available < quantity) {
        throw new InsufficientStockException();
    }
    available -= quantity;
}
```

Phương thức này bảo vệ invariant trong một lần thực thi trên trạng thái mà aggregate đang giữ. Tuy nhiên, hai request có thể tải hai instance từ cùng một phiên bản database. Mỗi instance đều thấy `available = 1`; cả hai lần gọi `reserve(1)` đều thành công trong bộ nhớ. Nếu repository lưu mà không phát hiện một instance đã cũ, cả hai có thể ghi `available = 0`.

Vì vậy cần phân biệt:

- **Domain invariant:** quy tắc nghiệp vụ mà aggregate phải bảo vệ, chẳng hạn số lượng khả dụng không được âm.
- **Concurrency control:** cơ chế phát hiện hoặc ngăn các giao dịch cạnh tranh khiến trạng thái lưu trữ vi phạm quy tắc.
- **Transaction boundary:** phạm vi các thay đổi được commit hoặc rollback cùng nhau.

Aggregate root cung cấp cổng thay đổi và kiểm tra quy tắc. Database hoặc persistence adapter cần bảo đảm thay đổi đó không được ghi đè bởi một giao dịch cạnh tranh mà không có phát hiện xung đột.

## 5. Optimistic concurrency: phát hiện xung đột khi lưu

**Optimistic concurrency control (kiểm soát đồng thời lạc quan)** giả định xung đột không xảy ra quá thường xuyên. Giao dịch có thể đọc và xử lý dữ liệu mà không khóa lâu, nhưng khi ghi phải xác nhận dữ liệu vẫn ở phiên bản mà nó đã đọc.

Một cách triển khai phổ biến là thêm trường `version` vào aggregate hoặc bản ghi. Mỗi lần cập nhật thành công, version tăng lên. Khi lưu, repository chỉ cập nhật nếu version hiện tại trong database vẫn bằng version đã đọc.

### 5.1. Minh họa bằng version

Giả sử bản ghi tồn kho có `available = 10` và `version = 4`.

| Thời điểm | Giao dịch A | Giao dịch B |
| --- | --- | --- |
| 1 | Đọc `available=10, version=4` | |
| 2 | | Đọc `available=10, version=4` |
| 3 | Tính `available=9` | Tính `available=9` |
| 4 | Cập nhật với điều kiện `version=4`, tăng version lên 5 | |
| 5 | Thành công | Cập nhật với điều kiện `version=4` |
| 6 | | Không có hàng nào được cập nhật: xung đột |

Giao dịch B không được phép âm thầm ghi đè kết quả A. Ứng dụng có thể tải lại trạng thái mới, đánh giá lại yêu cầu và thử lại hoặc trả về lỗi xung đột để người gọi quyết định.

### 5.2. SQL dùng version

```sql
UPDATE inventory_item
SET available = :new_available,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Ứng dụng phải kiểm tra số hàng được cập nhật:

- `1`: cập nhật thành công; version đã khớp.
- `0`: bản ghi không tồn tại hoặc version đã thay đổi; cần phân biệt hai trường hợp nếu nghiệp vụ cần.

Điều kiện version khiến thao tác ghi trở thành một phép kiểm tra và cập nhật nguyên tử ở database. Nó không yêu cầu khóa pessimistic trong suốt thời gian ứng dụng tính toán.

### 5.3. JPA `@Version`

Với JPA, có thể khai báo trường version để provider tự thêm điều kiện kiểm tra khi cập nhật:

```java
@Entity
public class InventoryItemEntity {
    @Id
    private UUID id;

    private int available;

    @Version
    private long version;
}
```

Khi hai transaction cùng tải version 4, transaction lưu trước sẽ tăng version. Transaction lưu sau với version cũ sẽ gặp optimistic locking failure, thường được thể hiện qua `OptimisticLockException` hoặc exception được Spring chuyển đổi tương ứng.

Không nên tự tăng trường `version` trong domain model nếu JPA đã quản lý nó bằng `@Version`. Cần xác định rõ version là chi tiết persistence hay là một phần của hợp đồng concurrency ở application layer.

### 5.4. Xử lý xung đột và retry

Khi phát hiện xung đột, không nên chỉ lặp lại câu lệnh ghi với cùng dữ liệu cũ. Cần:

1. Rollback transaction hiện tại.
2. Tải lại aggregate mới nhất trong một transaction mới.
3. Kiểm tra lại command và invariant trên trạng thái mới.
4. Thực hiện lại hành vi nếu vẫn hợp lệ.
5. Nếu điều kiện không còn thỏa, trả kết quả nghiệp vụ phù hợp.

Ví dụ, hai khách cùng mua sản phẩm cuối cùng. Request thua cuộc cần tải lại tồn kho, thấy số lượng bằng 0 và nhận kết quả hết hàng; không được tự động áp dụng phép giảm trên dữ liệu cũ.

Retry cần có giới hạn và backoff phù hợp để tránh tạo vòng lặp khi hệ thống đang quá tải. Với thao tác có tác dụng phụ bên ngoài, phải thiết kế idempotency hoặc tách tác dụng phụ khỏi transaction retry để không gửi thanh toán hay thông báo nhiều lần.

## 6. Pessimistic concurrency: khóa trước khi thay đổi

**Pessimistic concurrency control (kiểm soát đồng thời bi quan)** giả định xung đột có khả năng xảy ra và khóa dữ liệu để các giao dịch khác phải chờ hoặc không thể thay đổi cùng vùng dữ liệu trong thời gian khóa.

Với database quan hệ, một cách phổ biến là dùng `SELECT ... FOR UPDATE` trong transaction:

```sql
BEGIN;

SELECT available
FROM inventory_item
WHERE id = :id
FOR UPDATE;

-- Ứng dụng kiểm tra số lượng và thực hiện cập nhật.
UPDATE inventory_item
SET available = available - :quantity
WHERE id = :id;

COMMIT;
```

Giao dịch khác muốn khóa cùng hàng phải chờ cho đến khi transaction hiện tại commit hoặc rollback. Sau khi có quyền tiếp tục, giao dịch sau cần đọc trạng thái phù hợp với semantics của database và kiểm tra lại điều kiện.

### 6.1. Khi nào nên dùng pessimistic locking?

Có thể cân nhắc khi:

- Xung đột cập nhật xảy ra thường xuyên.
- Chi phí retry cao hoặc thao tác khó thực hiện lại.
- Một tài nguyên có tính tranh chấp cao và cần tuần tự hóa thao tác.
- Nghiệp vụ yêu cầu khóa một hàng hoặc tập dữ liệu trong một transaction ngắn.

### 6.2. Chi phí và rủi ro

Khóa làm giảm khả năng xử lý song song. Nếu transaction giữ khóa quá lâu, các request khác phải chờ, throughput giảm và timeout tăng. Khóa nhiều hàng theo thứ tự khác nhau có thể gây deadlock. Hệ thống cần xử lý deadlock bằng cách rollback và thử lại có kiểm soát khi phù hợp.

Không giữ khóa database trong lúc gọi API bên ngoài hoặc chờ người dùng nhập dữ liệu. Transaction nên ngắn và chỉ bao gồm những thao tác database cần thiết.

## 7. Cập nhật nguyên tử bằng một câu lệnh có điều kiện

Một số lost update có thể tránh bằng cách chuyển phép tính vào database để thực hiện như một thao tác nguyên tử. Thay vì đọc số lượng, trừ ở Java rồi ghi giá trị mới, ứng dụng có thể yêu cầu database giảm trực tiếp nếu điều kiện còn đủ hàng.

```sql
UPDATE inventory_item
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
```

Sau câu lệnh, kiểm tra số hàng được cập nhật:

- `1`: đã giữ được số lượng yêu cầu.
- `0`: không tìm thấy mặt hàng hoặc số lượng không đủ; có thể truy vấn thêm để phân biệt nếu cần.

Database thực hiện điều kiện và cập nhật trên cùng thao tác, do đó hai request không thể cùng tiêu thụ một đơn vị tồn kho cuối cùng bằng cách đọc cùng giá trị cũ rồi ghi đè.

### 7.1. Ưu điểm và giới hạn

Ưu điểm của conditional update là thao tác ngắn, giảm round trip và không cần tải toàn bộ aggregate nếu quy tắc có thể biểu diễn an toàn trong một câu lệnh.

Tuy nhiên, không nên đẩy mọi domain behavior vào SQL. Nếu hành vi cần kiểm tra nhiều invariant, phát domain event, cập nhật các object nội bộ hoặc áp dụng chính sách phức tạp, nhóm vẫn cần mô hình miền và transaction phù hợp. Conditional update phù hợp với những thao tác có điều kiện rõ và có thể bảo vệ nguyên tử ở database.

## 8. Isolation level và vai trò của database

Transaction isolation xác định mức độ một giao dịch được cô lập khỏi những thay đổi của giao dịch khác. Các hệ quản trị thường cung cấp các mức như `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`, nhưng semantics cụ thể và cơ chế triển khai có thể khác nhau.

| Isolation level | Ý nghĩa khái quát | Điều cần lưu ý |
| --- | --- | --- |
| Read Uncommitted | Có thể cho phép đọc dữ liệu chưa commit | Có nguy cơ dirty read; ít phù hợp với nghiệp vụ cần độ tin cậy cao |
| Read Committed | Chỉ đọc dữ liệu đã commit | Không tự động ngăn mọi lost update hoặc write skew trên mọi hệ quản trị |
| Repeatable Read | Giữ kết quả đọc ổn định theo semantics của database | Cách xử lý phantom và lost update phụ thuộc hệ quản trị, có thể dùng snapshot hoặc khóa |
| Serializable | Kết quả tương đương một thứ tự thực thi tuần tự | Có thể phát sinh serialization failure; ứng dụng cần xử lý retry |

Không nên coi isolation level là giải pháp duy nhất cho mọi invariant. Ví dụ, một invariant nghiệp vụ có thể liên quan đến nhiều aggregate hoặc nhiều hệ thống; transaction của một database không thể tự bảo vệ quy tắc xuyên qua cổng thanh toán bên ngoài.

Nhóm cần hiểu semantics của database đang sử dụng, dùng ràng buộc database khi phù hợp và kiểm thử lịch giao dịch cạnh tranh. Isolation level cao hơn thường có chi phí về khóa, retry hoặc khả năng xử lý song song.

## 9. Write skew: mỗi giao dịch hợp lệ nhưng kết quả chung sai

Lost update thường ghi đè cùng một hàng. **Write skew** là tình huống tinh vi hơn: hai giao dịch đọc cùng một tập dữ liệu, mỗi giao dịch ghi một hàng khác nhau, nên không nhất thiết có xung đột ghi trên cùng một hàng. Tuy nhiên, kết quả kết hợp lại vi phạm một invariant chung.

Ví dụ, một bệnh viện yêu cầu luôn có ít nhất một bác sĩ trực. Hiện có hai bác sĩ A và B đang trực. Hai giao dịch cùng đọc trạng thái và thấy có hai người trực:

- Giao dịch A kiểm tra thấy B vẫn trực, nên cho phép A rời ca và cập nhật `A.on_call = false`.
- Giao dịch B kiểm tra thấy A vẫn trực, nên cho phép B rời ca và cập nhật `B.on_call = false`.

Hai giao dịch ghi hai hàng khác nhau. Nếu isolation và thiết kế không phát hiện xung đột trên invariant chung, cả hai có thể commit và kết quả là không còn bác sĩ nào trực.

```text
Initial state: A.on_call = true, B.on_call = true

Transaction A                 Transaction B
-------------                 -------------
Read A=true, B=true           Read A=true, B=true
Set A=false                   Set B=false
Write row A                   Write row B
Commit                        Commit

Final state: A=false, B=false  -> invariant violated
```

### 9.1. Vì sao version trên từng aggregate có thể chưa đủ?

Nếu A và B là hai aggregate riêng, optimistic version của aggregate A chỉ phát hiện một giao dịch khác cùng sửa A. Tương tự với B. Hai giao dịch sửa hai aggregate khác nhau nên không có version nào xung đột, dù invariant “ít nhất một người trực” liên quan đến cả hai.

Đây là dấu hiệu invariant có thể đang nằm ngoài ranh giới aggregate hiện tại hoặc cần một cơ chế phối hợp mạnh hơn.

### 9.2. Các cách xử lý

Tùy nghiệp vụ, có thể:

- Gom thông tin quyết định vào một aggregate hoặc một bản ghi điều phối có cùng invariant.
- Khóa một hàng đại diện cho lịch trực trước khi kiểm tra và cập nhật.
- Dùng transaction `SERIALIZABLE` và xử lý serialization failure.
- Dùng constraint hoặc cấu trúc dữ liệu được database bảo vệ nếu có thể biểu diễn invariant.
- Thiết kế một quy trình điều phối duy nhất để cấp quyền thay đổi trạng thái.

Không phải lúc nào cũng nên gom các bác sĩ thành một aggregate lớn. Cần cân nhắc tần suất thay đổi, phạm vi nghiệp vụ và cách tổ chức lịch trực. Điều quan trọng là nhận diện invariant chung và chọn cơ chế bảo vệ nó một cách rõ ràng.

## 10. Aggregate boundary và concurrency control trong DDD

Aggregate xác định ranh giới nhất quán logic. Khi một command thay đổi aggregate, root kiểm tra invariant và repository lưu thay đổi. Tuy nhiên, để bảo vệ invariant trước nhiều request đồng thời, hệ thống cần phối hợp ba phần:

1. **Domain model:** xác định invariant và chỉ cung cấp hành vi hợp lệ.
2. **Application/repository:** xác định transaction, tải aggregate, lưu và diễn giải xung đột.
3. **Database hoặc cơ chế lưu trữ:** thực hiện atomic update, version check, lock hoặc isolation phù hợp.

Một luồng điển hình:

```text
Command
   |
   v
Application Service
   |
   v
Repository loads Aggregate + Version
   |
   v
Aggregate Root checks invariant
   |
   v
Repository saves with version/lock condition
   |
   +---- success ----> Commit
   |
   +---- conflict ---> Rollback / reload / retry or reject
```

### 10.1. Một command thường thay đổi một aggregate

Thiết kế DDD thường hướng đến một transaction ghi cho một aggregate. Điều này giúp invariant có ranh giới rõ và giảm xung đột giữa các thao tác không liên quan.

Nếu một use case cần thay đổi nhiều aggregate, nhóm nên xem xét liệu có thể chia thành các bước, dùng domain event hoặc saga, và chấp nhận eventual consistency hay không. Nếu nghiệp vụ yêu cầu một invariant tức thời xuyên nhiều aggregate, cần một cơ chế bảo vệ rõ ràng như transaction có isolation phù hợp, khóa điều phối hoặc tái thiết kế mô hình.

### 10.2. Version là chi tiết kỹ thuật hay dữ liệu miền?

Trong nhiều hệ thống, version chỉ phục vụ optimistic locking và thuộc persistence/application layer. Nó không cần xuất hiện trong ngôn ngữ nghiệp vụ.

Tuy nhiên, một số API công khai có thể dùng version hoặc ETag để client gửi điều kiện cập nhật, ví dụ `If-Match`. Khi đó version trở thành một phần của hợp đồng kỹ thuật ở ranh giới, nhưng vẫn không nhất thiết là thuộc tính nghiệp vụ của entity.

## 11. Chọn chiến lược phù hợp

Không có một cơ chế concurrency duy nhất tốt nhất cho mọi trường hợp. Lựa chọn phụ thuộc vào tần suất xung đột, thời gian transaction, mức độ phức tạp của invariant và khả năng retry.

| Chiến lược | Cách hoạt động | Phù hợp khi | Chi phí hoặc giới hạn |
| --- | --- | --- | --- |
| Optimistic locking/version | Kiểm tra version khi lưu, từ chối bản ghi cũ | Xung đột tương đối hiếm, transaction ngắn | Cần xử lý conflict và retry |
| Pessimistic locking | Khóa dữ liệu trong transaction | Xung đột cao, cần tuần tự hóa thao tác | Chờ khóa, deadlock, giảm throughput |
| Atomic conditional update | Kiểm tra điều kiện và cập nhật trong một câu lệnh | Quy tắc đơn giản có thể biểu diễn tại database | Logic phức tạp khó đặt hoàn toàn trong SQL |
| Unique/check constraint | Database từ chối trạng thái vi phạm ràng buộc | Invariant có thể biểu diễn bằng constraint | Không diễn đạt được mọi quy tắc liên đối tượng |
| Serializable transaction | Database bảo đảm kết quả tương đương tuần tự | Invariant phụ thuộc nhiều hàng trong một database | Có thể abort và cần retry; chi phí cao hơn |
| Coordination record/aggregate | Tuần tự hóa quyết định qua một điểm chung | Nhiều đối tượng chia sẻ một invariant | Có thể tạo điểm nóng và cần thiết kế throughput |

Trong thực tế, có thể kết hợp các chiến lược. Ví dụ, dùng optimistic locking cho aggregate, unique constraint cho mã nghiệp vụ, conditional update cho số lượng tồn kho và idempotency key cho request từ đối tác.

## 12. Idempotency, retry và xử lý command trùng

Retry là cách thường dùng để xử lý optimistic conflict hoặc lỗi tạm thời. Tuy nhiên, retry có thể khiến cùng một yêu cầu được thực hiện nhiều lần. Cần phân biệt:

- **Concurrency control** bảo vệ dữ liệu khi nhiều thao tác cạnh tranh.
- **Idempotency** bảo đảm việc gửi lại cùng một yêu cầu không tạo thêm tác dụng phụ ngoài dự kiến.
- **Deduplication** nhận diện và loại bỏ thông điệp hoặc command trùng theo một khóa hoặc chính sách.

Ba cơ chế này bổ trợ nhau nhưng không thay thế nhau. Version check không tự ngăn một webhook được xử lý hai lần ở hai transaction tuần tự. Idempotency key cũng không tự ngăn hai command khác nhau cùng tiêu thụ sản phẩm cuối cùng.

Ví dụ, API đặt hàng nhận header `Idempotency-Key`. Hệ thống lưu khóa cùng kết quả xử lý. Nếu client gửi lại cùng khóa sau timeout, hệ thống trả lại kết quả đã ghi nhận thay vì tạo thêm đơn. Trong khi đó, aggregate tồn kho vẫn cần concurrency control để hai khách khác nhau không cùng đặt một sản phẩm cuối cùng.

## 13. Cách kiểm thử lost update và concurrency

Kiểm thử concurrency cần tạo ra sự chồng lấn có chủ đích giữa các giao dịch. Chỉ gọi tuần tự hai lần thường không tái hiện được race condition.

### 13.1. Xác định invariant trước

Ví dụ:

- Số lượng tồn kho không bao giờ âm.
- Một mã hợp đồng chỉ được cấp cho một hợp đồng trong phạm vi quy định.
- Số dư tài khoản không được thấp hơn hạn mức cho phép.
- Luôn có ít nhất một người trực trong một ca.
- Một đơn không thể vừa được hủy vừa được xác nhận theo hai luồng cạnh tranh.

### 13.2. Tạo hai transaction chạy đồng thời

Dùng hai connection hoặc hai transaction độc lập. Có thể sử dụng barrier hoặc latch trong kiểm thử để bảo đảm cả hai transaction đã đọc cùng phiên bản trước khi tiếp tục ghi.

Kịch bản kiểm thử lost update:

1. Tạo tồn kho ban đầu bằng 1.
2. Khởi chạy hai transaction, mỗi transaction yêu cầu giữ 1 sản phẩm.
3. Điều phối để cả hai cùng đọc trạng thái trước khi ghi nếu đang kiểm tra optimistic/pessimistic behavior.
4. Cho hai transaction tiếp tục.
5. Xác nhận chỉ một transaction thành công.
6. Xác nhận số lượng tồn kho cuối cùng bằng 0, không âm và chỉ có một reservation hợp lệ.

### 13.3. Kiểm thử cả kết quả và tác dụng phụ

Không chỉ kiểm tra giá trị database. Cần xác nhận:

- Có bao nhiêu command được chấp nhận?
- Có bao nhiêu domain event hoặc integration event được ghi nhận?
- Có giao dịch thanh toán hoặc thông báo nào bị gửi trùng không?
- Request thua cuộc nhận lỗi xung đột hay kết quả hết hàng?
- Retry có tải lại dữ liệu và kiểm tra lại invariant không?

### 13.4. Dùng đúng database khi kiểm thử

Hành vi lock và isolation có thể khác giữa H2, PostgreSQL, MySQL, SQL Server hoặc các hệ quản trị khác. Nếu ứng dụng chạy trên một database cụ thể, nên có integration test trên đúng hệ quản trị hoặc một môi trường tương đương để kiểm chứng semantics quan trọng.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Cho rằng kiểm tra invariant trong Java đủ để chống concurrency | Hai instance cũ có thể cùng vượt qua kiểm tra rồi ghi đè nhau | Kết hợp domain rule với version, lock hoặc atomic update |
| Chỉ dùng `synchronized` trong ứng dụng nhiều instance | Mỗi JVM có khóa riêng, không bảo vệ database dùng chung | Dùng cơ chế concurrency ở database hoặc distributed coordination phù hợp |
| Ghi toàn bộ object từ snapshot cũ | Thay đổi của request khác bị mất | Dùng optimistic version hoặc cập nhật nguyên tử có điều kiện |
| Retry với cùng dữ liệu cũ | Xung đột lặp lại hoặc ghi sai trạng thái | Rollback, tải lại và thực thi lại command trên dữ liệu mới |
| Giữ pessimistic lock trong lúc gọi API ngoài | Khóa lâu, timeout và deadlock | Giữ transaction ngắn; điều phối lời gọi ngoài bằng workflow |
| Cho rằng `READ COMMITTED` luôn ngăn lost update | Hành vi khác nhau theo database và câu lệnh | Kiểm tra semantics thực tế, dùng version hoặc atomic update khi cần |
| Chỉ version từng aggregate dù invariant nằm trên nhiều aggregate | Write skew vẫn có thể xảy ra | Bảo vệ invariant chung bằng constraint, lock, serializable hoặc ranh giới phù hợp |
| Nhầm idempotency với concurrency control | Request trùng được xử lý an toàn nhưng hai request khác nhau vẫn tranh chấp | Dùng mỗi cơ chế cho đúng loại vấn đề |
| Chỉ kiểm thử tuần tự | Race condition không được phát hiện | Tạo test với transaction và connection chạy đồng thời |
| Bỏ qua tác dụng phụ khi retry | Thanh toán, email hoặc message có thể bị gửi nhiều lần | Dùng idempotency, outbox và tách tác dụng phụ khỏi transaction retry |

## 15. Quy trình xử lý cạnh tranh cập nhật

Khi phát hiện dữ liệu bị mất hoặc invariant bị vi phạm trong môi trường có nhiều request, nhóm có thể phân tích theo trình tự sau.

### Bước 1: Xác định invariant bị ảnh hưởng

Mô tả trạng thái nào phải luôn đúng và thao tác nào có thể làm thay đổi trạng thái đó. Phân biệt lỗi dữ liệu với hành vi nghiệp vụ được cho phép.

### Bước 2: Thu thập lịch giao dịch

Ghi lại thứ tự đọc, tính toán, khóa, ghi và commit của các transaction. Tìm xem chúng đọc cùng version hay cùng tập dữ liệu không, có ghi cùng hàng không và có tác dụng phụ bên ngoài không.

### Bước 3: Xác định phạm vi invariant

Kiểm tra invariant nằm trong một aggregate, nhiều aggregate trong cùng database hay xuyên qua nhiều hệ thống. Phạm vi này quyết định cơ chế concurrency có thể áp dụng.

### Bước 4: Chọn cơ chế bảo vệ

Chọn optimistic version, pessimistic lock, atomic conditional update, constraint hoặc serializable transaction dựa trên tần suất xung đột và yêu cầu nghiệp vụ. Không thêm khóa nếu một câu lệnh nguyên tử đơn giản đã đủ.

### Bước 5: Xác định cách xử lý conflict

Quyết định khi xung đột thì tự retry, yêu cầu người dùng tải lại, từ chối command hay chạy một quy trình nghiệp vụ khác. Retry phải thực hiện trên trạng thái mới và có giới hạn.

### Bước 6: Bảo vệ tác dụng phụ

Nếu command gửi payment, email hoặc message, xác định cách ngăn thực hiện trùng khi retry. Cân nhắc idempotency key, outbox, inbox hoặc đối soát tùy kiến trúc.

### Bước 7: Kiểm thử bằng transaction đồng thời

Tạo lịch giao dịch tái hiện lỗi, chạy trên database mục tiêu và xác nhận invariant, kết quả command cùng các tác dụng phụ đều đúng.

### Bước 8: Theo dõi sau triển khai

Theo dõi tỷ lệ optimistic conflict, lock wait, deadlock, retry, lỗi constraint và thời gian xử lý. Các chỉ số này giúp nhận ra aggregate quá nóng hoặc ranh giới cần điều chỉnh.

## 16. Nguyên tắc thực hành

Khi thiết kế và vận hành hệ thống có nhiều cập nhật đồng thời, nhóm nên nhớ:

- **Bắt đầu từ invariant.** Xác định điều gì không được phép xảy ra trước khi chọn công nghệ khóa.
- **Nhận diện read-modify-write.** Chuỗi đọc, tính toán và ghi thường là nơi dễ xuất hiện lost update.
- **Không chỉ dựa vào kiểm tra trong bộ nhớ.** Trạng thái có thể đã thay đổi ở transaction khác trước khi lưu.
- **Dùng optimistic locking khi xung đột ít.** Version giúp phát hiện bản ghi cũ và cho phép xử lý lại trên trạng thái mới.
- **Dùng pessimistic locking khi cần tuần tự hóa.** Giữ transaction ngắn và quản lý deadlock.
- **Dùng atomic conditional update cho quy tắc đơn giản.** Kiểm tra điều kiện và cập nhật trong cùng thao tác database.
- **Hiểu isolation của database thực tế.** Không suy đoán semantics chỉ từ tên mức isolation.
- **Nhận diện write skew.** Version trên từng aggregate có thể không bảo vệ invariant chung giữa nhiều aggregate.
- **Tách concurrency control khỏi idempotency.** Một cơ chế bảo vệ cập nhật cạnh tranh, cơ chế kia bảo vệ việc gửi lại cùng yêu cầu.
- **Thiết kế retry có kiểm soát.** Rollback, tải lại, kiểm tra lại quy tắc và không lặp tác dụng phụ.
- **Kiểm thử bằng transaction đồng thời.** Tái hiện lịch đọc/ghi thực tế trên database mục tiêu.

Lost update là hậu quả của việc một giao dịch ghi dựa trên trạng thái cũ mà không phát hiện thay đổi đã xảy ra. Trong DDD, aggregate và invariant xác định điều gì cần được bảo vệ; optimistic locking, pessimistic locking, atomic update, constraint và isolation cung cấp cơ chế thực thi việc bảo vệ đó. Khi phạm vi invariant, chiến lược concurrency và cách xử lý xung đột được thiết kế cùng nhau, hệ thống có thể duy trì tính đúng đắn ngay cả khi nhiều người dùng và tiến trình cập nhật đồng thời.

## 17. Câu hỏi tự kiểm tra

1. Lost update là gì? Hãy mô tả một lịch giao dịch khiến hai lần giảm tồn kho chỉ được ghi nhận thành một lần.
2. Vì sao một phương thức aggregate kiểm tra `available >= quantity` vẫn chưa đủ để ngăn hai request cùng giữ sản phẩm cuối cùng?
3. Phân biệt lost update, dirty read, non-repeatable read, phantom read và write skew.
4. Optimistic locking dùng version để phát hiện xung đột như thế nào?
5. Khi optimistic conflict xảy ra, vì sao cần rollback và tải lại aggregate trước khi retry?
6. Pessimistic locking phù hợp trong tình huống nào và có những chi phí gì?
7. Conditional update trong SQL bảo vệ thao tác giảm tồn kho như thế nào?
8. Vì sao không nên giả định `READ COMMITTED` ngăn mọi lost update trên tất cả database?
9. Write skew có thể xảy ra như thế nào khi hai transaction sửa hai aggregate khác nhau?
10. Vì sao version riêng của từng aggregate có thể không bảo vệ invariant nằm trên nhiều aggregate?
11. Phân biệt concurrency control với idempotency và deduplication.
12. Hãy thiết kế một bài kiểm thử hai transaction cùng cập nhật tài nguyên cuối cùng, nêu invariant, cơ chế bảo vệ và kết quả mong đợi.
