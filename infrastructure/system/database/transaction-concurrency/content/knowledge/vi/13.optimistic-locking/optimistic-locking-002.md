# Cột version và câu lệnh UPDATE có điều kiện

Khóa lạc quan (optimistic locking) là cách phát hiện xung đột cập nhật bằng cách kiểm tra dữ liệu có còn ở phiên bản mà transaction đã đọc hay không. Thay vì khóa dòng ngay từ lúc đọc và giữ lock trong suốt quá trình xử lý, ứng dụng đọc dữ liệu cùng một **version**, thực hiện tính toán, rồi gửi một câu UPDATE có điều kiện. Database chỉ chấp nhận thay đổi nếu version trong database vẫn khớp với version mà ứng dụng đã đọc.

Hai thành phần cốt lõi là:

- **Cột version:** một giá trị thay đổi sau mỗi lần cập nhật thành công, thường là số nguyên tăng dần.
- **UPDATE có điều kiện:** chỉ cập nhật khi khóa định danh và version vẫn đúng với dữ liệu đã đọc.

Nếu một transaction khác đã cập nhật dòng trước đó, version đã thay đổi. UPDATE của transaction đến sau không còn khớp điều kiện và không cập nhật dòng nào. Ứng dụng nhận biết xung đột qua số dòng bị ảnh hưởng, sau đó đọc lại dữ liệu, hợp nhất thay đổi hoặc báo người dùng.

Cách làm này phù hợp với dữ liệu có nhiều lần đọc nhưng tương đối ít xung đột ghi, chẳng hạn chỉnh sửa hồ sơ, tài liệu, cấu hình hoặc đơn hàng. Nó không loại bỏ lock nội bộ của database; nó thay đổi thời điểm và cách ứng dụng phát hiện xung đột.

## 1. Vấn đề lost update khi không kiểm tra version

Giả sử một sản phẩm có số lượng tồn kho là 10. Hai request cùng đọc số lượng này:

- Request A đọc 10 và muốn giảm 2.
- Request B đọc 10 và muốn giảm 3.

Nếu mỗi request tính toán ở ứng dụng rồi ghi giá trị tuyệt đối mà không kiểm tra dữ liệu có thay đổi hay chưa, có thể xảy ra:

~~~text
Request A                         Request B
---------                         ---------
Đọc quantity = 10                 Đọc quantity = 10
Tính 10 - 2 = 8                   Tính 10 - 3 = 7
UPDATE quantity = 8
                                  UPDATE quantity = 7
                                  COMMIT
COMMIT
~~~

Nếu A ghi 8 rồi B ghi 7, kết quả cuối cùng là 7. Thay đổi của A đã bị ghi đè. Hệ thống mất một phần cập nhật dù cả hai request đều đã đọc một giá trị hợp lệ.

Đây là **lost update**. Vấn đề không nằm ở việc câu UPDATE không nguyên tử; mỗi câu UPDATE riêng lẻ vẫn có thể nguyên tử. Vấn đề là giá trị mới đã được tính dựa trên một phiên bản cũ mà ứng dụng không xác minh lại khi ghi.

Nếu nghiệp vụ là giảm tồn kho 2 rồi giảm tiếp 3, kết quả mong muốn có thể là 5. Nhưng cách ghi giá trị tuyệt đối dựa trên cùng một lần đọc đã khiến một cập nhật bị mất.

## 2. Thêm cột version vào bảng

Một bảng có thể lưu version như sau:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Mỗi dòng bắt đầu với version, ví dụ 0. Khi ứng dụng đọc sản phẩm, nó lấy cả dữ liệu và version:

~~~sql
SELECT product_id, product_name, available_quantity, version
FROM products
WHERE product_id = 42;
~~~

Kết quả minh họa:

| product_id | product_name | available_quantity | version |
|---:|---|---:|---:|
| 42 | Keyboard | 10 | 7 |

Ứng dụng giữ version 7 cùng dữ liệu mà nó vừa đọc. Khi chuẩn bị ghi, ứng dụng phải nói với database rằng chỉ cập nhật nếu version vẫn là 7.

Cột version thường có các đặc điểm:

- Được khai báo NOT NULL để mọi dòng đều có token phiên bản hợp lệ.
- Có giá trị ban đầu, thường là 0 hoặc 1.
- Được tăng sau mỗi lần cập nhật thành công.
- Được thay đổi trong cùng câu UPDATE với dữ liệu nghiệp vụ.
- Không được lấy giá trị mới bằng cách chỉ tin vào dữ liệu client gửi lên; ứng dụng cần dùng version đã đọc và kiểm tra tại database.

Version không nhất thiết là thời gian. Một số nguyên tăng dần thường dễ so sánh và không phụ thuộc đồng hồ giữa các máy. Có thể dùng UUID hoặc token khác nếu thiết kế cần, nhưng cần bảo đảm mỗi lần thay đổi phải tạo ra một token mới không bị tái sử dụng theo cách gây bỏ sót xung đột.

## 3. UPDATE có điều kiện: kiểm tra version ngay lúc ghi

Giả sử ứng dụng đã đọc dòng sản phẩm với version 7. Nó muốn giảm số lượng từ 10 xuống 8. Câu UPDATE có điều kiện là:

~~~sql
UPDATE products
SET available_quantity = 8,
    version = version + 1
WHERE product_id = 42
  AND version = 7;
~~~

Có hai kết quả:

- **Một dòng được cập nhật:** dòng vẫn có version 7 tại thời điểm database thực hiện điều kiện. Cập nhật thành công và version tăng lên 8.
- **Không có dòng nào được cập nhật:** sản phẩm không tồn tại hoặc version không còn là 7. Ứng dụng phải xác định đây là xung đột hay trường hợp không tìm thấy dữ liệu theo quy tắc API.

Sau khi A cập nhật thành công:

| product_id | available_quantity | version |
|---:|---:|---:|
| 42 | 8 | 8 |

Request B vẫn giữ version 7. Nếu B thực hiện:

~~~sql
UPDATE products
SET available_quantity = 7,
    version = version + 1
WHERE product_id = 42
  AND version = 7;
~~~

Database không tìm thấy dòng thỏa cả hai điều kiện vì version hiện tại là 8. Số dòng được cập nhật bằng 0. B không ghi đè thay đổi của A.

Điểm quyết định là **điều kiện kiểm tra version và thay đổi dữ liệu nằm trong cùng một câu lệnh UPDATE**. Không nên tách thành SELECT version rồi UPDATE không có điều kiện, vì transaction khác vẫn có thể cập nhật giữa hai câu lệnh.

## 4. Cách hai transaction cạnh tranh được phát hiện

Luồng xử lý có thể mô tả như sau:

~~~text
Database: quantity = 10, version = 7
              |
       +------+------+
       |             |
       v             v
   Request A      Request B
   đọc version 7  đọc version 7
       |             |
   tính quantity  tính quantity
   thành 8         thành 7
       |             |
       v             v
   UPDATE ...      UPDATE ...
   WHERE version=7 WHERE version=7
       |             |
       v             v
   Cập nhật 1 dòng  Không khớp
   version = 8      affected rows = 0
       |             |
       v             v
   Thành công       Conflict
                     |
                     v
              Đọc lại hoặc báo lỗi
~~~

Cả hai request đều có thể đọc cùng một version. Database quyết định request nào cập nhật trước. Khi một UPDATE đã tăng version, các UPDATE còn lại dựa trên version cũ sẽ không còn khớp.

Trong database quan hệ, câu UPDATE vẫn cần các cơ chế đồng bộ ghi nội bộ. Một engine có thể lấy row lock trong thời gian thực hiện UPDATE để điều phối hai câu lệnh ghi cạnh tranh. Vì vậy, optimistic locking không có nghĩa là database không dùng lock. Ý nghĩa của “lạc quan” nằm ở chỗ ứng dụng không chủ động giữ lock từ lúc đọc trong suốt quá trình xử lý; xung đột được phát hiện tại thời điểm ghi.

## 5. Đặt version và điều kiện nghiệp vụ cùng một UPDATE

Version bảo vệ việc cập nhật dựa trên dữ liệu đã đọc. Nó không thay thế các điều kiện nghiệp vụ. Câu UPDATE có thể kiểm tra đồng thời:

- Định danh dòng.
- Version mà ứng dụng đã đọc.
- Trạng thái nghiệp vụ cho phép cập nhật.
- Điều kiện về số lượng, số dư hoặc giới hạn.

Ví dụ giảm tồn kho chỉ khi dòng chưa thay đổi và số lượng vẫn đủ:

~~~sql
UPDATE products
SET available_quantity = available_quantity - 2,
    version = version + 1
WHERE product_id = 42
  AND version = 7
  AND available_quantity >= 2;
~~~

Nếu một dòng được cập nhật, cả version và điều kiện tồn kho đều thỏa. Nếu không có dòng nào được cập nhật, có thể xảy ra một trong các trường hợp:

- Sản phẩm không tồn tại.
- Version đã thay đổi.
- Số lượng hiện tại không còn đủ.
- Trạng thái sản phẩm không cho phép cập nhật, nếu câu lệnh có thêm điều kiện trạng thái.

Ứng dụng có thể đọc lại dòng để phân biệt các trường hợp nếu cần trả thông báo cụ thể. Không nên thực hiện một SELECT kiểm tra rồi giả định dữ liệu sẽ giữ nguyên đến lần ghi sau; nếu cần quyết định cập nhật, hãy đưa điều kiện quyết định vào chính UPDATE.

Ví dụ chuyển trạng thái đơn hàng:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = 1001
  AND version = 4
  AND status = 'PENDING';
~~~

Câu lệnh chỉ xác nhận đơn hàng nếu nó vẫn ở version 4 và trạng thái PENDING. Nếu một request khác đã hủy đơn hàng hoặc xác nhận trước đó, câu UPDATE không cập nhật dòng. Điều kiện status bảo vệ quy tắc chuyển trạng thái; điều kiện version phát hiện dữ liệu đã thay đổi kể từ lần đọc.

## 6. Vì sao phải tăng version trong cùng UPDATE?

Một lỗi triển khai phổ biến là kiểm tra version nhưng quên tăng version:

~~~sql
-- Không đủ: version không đổi sau cập nhật.
UPDATE documents
SET title = 'New title'
WHERE document_id = 42
  AND version = 7;
~~~

Nếu version vẫn là 7, một request khác cũng đang giữ version 7 có thể tiếp tục thỏa điều kiện ở lần cập nhật tiếp theo. Cơ chế phát hiện xung đột mất tác dụng.

Cần cập nhật version cùng dữ liệu:

~~~sql
UPDATE documents
SET title = 'New title',
    version = version + 1
WHERE document_id = 42
  AND version = 7;
~~~

Khi database thực hiện câu lệnh thành công, version chuyển từ 7 sang 8 trong cùng thao tác. Không nên tăng version bằng một UPDATE riêng sau khi cập nhật dữ liệu, vì giữa hai câu lệnh có thể có transaction khác chen vào hoặc một lỗi khiến dữ liệu và version không còn đồng bộ.

Cũng cần bảo đảm mọi đường ghi có thể thay đổi dữ liệu được quản lý version đều tuân theo quy tắc này. Nếu một batch job, câu SQL thủ công hoặc service khác cập nhật dữ liệu nhưng không tăng version, request đang giữ version cũ có thể không phát hiện được thay đổi đó.

## 7. Kiểm tra số dòng bị ảnh hưởng

Ứng dụng cần đọc số dòng được cập nhật từ JDBC, ORM hoặc driver database. Với một khóa chính duy nhất, kết quả thông thường là:

- **1:** cập nhật thành công.
- **0:** không có dòng khớp điều kiện.
- **Lớn hơn 1:** cần xem lại điều kiện hoặc giả định về tính duy nhất; với primary key đúng, kết quả này không nên xảy ra.

Ví dụ JDBC:

~~~java
String sql = """
    UPDATE products
    SET available_quantity = ?,
        version = version + 1
    WHERE product_id = ?
      AND version = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setInt(1, newQuantity);
    statement.setLong(2, productId);
    statement.setLong(3, expectedVersion);

    int affectedRows = statement.executeUpdate();

    if (affectedRows == 1) {
        // Cập nhật thành công.
    } else if (affectedRows == 0) {
        // Không tìm thấy dòng hoặc version đã thay đổi.
        // Đọc lại nếu cần phân loại chi tiết.
    } else {
        throw new IllegalStateException("Unexpected affected row count");
    }
}
~~~

Đoạn mã chỉ minh họa việc kiểm tra kết quả UPDATE. Transaction boundary, commit/rollback và ánh xạ exception cần được quản lý ở lớp phù hợp của ứng dụng.

Với UPDATE có tăng version, mỗi lần thành công đều thay đổi ít nhất cột version. Điều này giúp tránh một số khác biệt giữa driver về việc báo số dòng được khớp với số dòng có giá trị thực sự thay đổi. Dù vậy, cần hiểu hợp đồng affected-row count của driver đang dùng.

Không nên chỉ kiểm tra câu lệnh không ném exception. Một UPDATE ảnh hưởng 0 dòng thường là một kết quả hợp lệ ở cấp SQL, nhưng có ý nghĩa xung đột ở cấp nghiệp vụ.

## 8. Quy trình xử lý khi version không khớp

Khi affected rows bằng 0, ứng dụng cần chọn chính sách theo loại use case.

### 8.1. Đọc lại và thử hợp nhất

Với một biểu mẫu chỉnh sửa tài liệu, có thể đọc lại bản mới nhất và so sánh các trường:

1. Người dùng đã đọc version 7.
2. Một người khác lưu version 8.
3. Request đầu tiên gửi thay đổi dựa trên version 7.
4. UPDATE không khớp, trả 0 dòng.
5. Ứng dụng đọc version 8 và hiển thị khác biệt để người dùng chọn cách xử lý.

Không nên tự động ghi đè version 8 bằng dữ liệu cũ nếu nghiệp vụ cần bảo toàn thay đổi của người khác. Có thể hợp nhất các trường không xung đột hoặc yêu cầu người dùng chỉnh sửa lại.

### 8.2. Retry toàn bộ thao tác khi nghiệp vụ cho phép

Một số thao tác có thể đọc lại, tính lại và thử cập nhật với version mới. Ví dụ tăng một bộ đếm thêm 1 có thể được biểu diễn trực tiếp bằng phép cộng trong SQL. Khi đó không cần lấy giá trị tuyệt đối từ lần đọc cũ:

~~~sql
UPDATE counters
SET counter_value = counter_value + 1,
    version = version + 1
WHERE counter_id = 42;
~~~

Câu lệnh này thực hiện phép tăng trên giá trị hiện hành tại database và vẫn tăng version. Nếu cần điều kiện giới hạn, có thể thêm điều kiện vào WHERE.

Với thao tác phức tạp dựa trên nhiều giá trị đã đọc, retry phải đọc lại toàn bộ trạng thái và tính lại quyết định. Không được chỉ thay expectedVersion thành version mới nhưng giữ nguyên kết quả tính từ dữ liệu cũ, vì như vậy có thể hợp thức hóa một quyết định không còn đúng.

### 8.3. Trả xung đột cho client

Với API chỉnh sửa tài nguyên, ứng dụng có thể trả HTTP 409 Conflict hoặc một response xung đột được quy định trong API contract. Response nên giúp client hiểu tài nguyên đã thay đổi và cung cấp thông tin cần thiết để tải lại.

Một số API dùng ETag/If-Match để biểu diễn cùng ý tưởng ở giao thức HTTP:

- Server trả ETag tương ứng với phiên bản tài nguyên.
- Client gửi ETag trong header If-Match khi cập nhật.
- Server chỉ cập nhật nếu ETag vẫn khớp.
- Nếu không khớp, server trả 412 Precondition Failed theo ngữ nghĩa HTTP.

ETag có thể được tạo từ version hoặc một representation token khác. Cần bảo đảm ETag thay đổi khi representation liên quan thay đổi và không dùng token yếu khi yêu cầu so sánh mạnh.

## 9. Cột version trong ORM, đặc biệt là JPA

Trong ứng dụng Java dùng JPA, có thể khai báo optimistic locking bằng annotation @Version:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long productId;

    private String productName;

    private Integer availableQuantity;

    @Version
    private Long version;
}
~~~

Khi entity được đọc, persistence provider ghi nhớ version. Khi flush hoặc commit thay đổi, provider thường tạo UPDATE có điều kiện tương đương:

~~~sql
UPDATE products
SET product_name = ?,
    available_quantity = ?,
    version = ?
WHERE product_id = ?
  AND version = ?;
~~~

Nếu không có dòng nào được cập nhật do version đã thay đổi, provider báo lỗi optimistic locking, thường được thể hiện qua OptimisticLockException hoặc exception được framework bọc lại. Chi tiết thời điểm phát hiện phụ thuộc flush, commit và provider.

Một số điểm cần lưu ý:

- Trường @Version phải được provider quản lý; ứng dụng không tự tăng version tùy tiện khi dùng cơ chế này.
- Không nên gán lại version từ request body vào entity đã được quản lý rồi kỳ vọng provider tự bảo vệ mọi thứ.
- Cần xử lý exception ở ranh giới transaction phù hợp; transaction đã bị đánh dấu rollback-only thì không nên tiếp tục dùng nó.
- Với DTO, có thể gửi version mà client đã đọc và dùng nó làm điều kiện cập nhật ở service hoặc repository.
- Native SQL hoặc bulk update có thể đi qua đường thực thi không tự động áp dụng cơ chế @Version giống cập nhật entity thông thường. Khi dùng các đường ghi đó, cần tự bảo đảm version được kiểm tra và tăng đúng cách, đồng thời làm mới hoặc clear persistence context nếu cần.

Ví dụ service với entity được quản lý:

~~~java
@Transactional
public void renameProduct(Long id, String newName) {
    Product product = repository.findById(id)
        .orElseThrow(() -> new NotFoundException("Product not found"));

    product.setProductName(newName);
    // Persistence provider kiểm tra và cập nhật @Version khi flush/commit.
}
~~~

Nếu hai transaction cùng đọc entity version 7, transaction commit trước sẽ chuyển version lên 8. Transaction còn lại khi flush sẽ không cập nhật được dòng với version 7 và nhận optimistic locking exception.

## 10. Version số nguyên, timestamp và token khác

Có nhiều cách biểu diễn version, nhưng cần xem cách nào phát hiện thay đổi đáng tin cậy.

| Loại version | Ưu điểm | Hạn chế |
|---|---|---|
| Số nguyên tăng dần | Dễ so sánh, không phụ thuộc đồng hồ, thay đổi rõ ràng | Cần bảo đảm mọi đường ghi đều tăng version; cần cân nhắc giới hạn kiểu dữ liệu trong vòng đời hệ thống |
| Timestamp | Dễ liên hệ với thời điểm cập nhật, có thể dùng làm token | Độ chính xác có thể không đủ; hai cập nhật gần nhau có thể có cùng timestamp; đồng hồ và cách làm tròn có thể khác nhau |
| UUID/token ngẫu nhiên | Mỗi lần cập nhật có thể tạo token mới, không cần thứ tự | Không biểu thị thứ tự phiên bản; cần sinh token mới mỗi lần và lưu/so sánh nhất quán |
| Hash nội dung | Có thể phát hiện representation thay đổi | Tốn công tính toán; cần xác định chính xác trường nào thuộc representation và xử lý dữ liệu chuẩn hóa |

Số nguyên tăng dần là lựa chọn đơn giản và phổ biến cho optimistic locking trong database quan hệ. Timestamp có thể phù hợp cho ETag hoặc cache validator, nhưng không nên dùng timestamp có độ chính xác thấp làm version duy nhất nếu có khả năng nhiều cập nhật xảy ra trong cùng một đơn vị thời gian.

Version là token đồng bộ hóa, không nhất thiết là số lần người dùng chỉnh sửa. Một transaction có thể cập nhật nhiều trường nhưng chỉ tăng version một lần. Quy tắc quan trọng là mọi thay đổi có thể làm mất hiệu lực dữ liệu mà client đã đọc phải làm token thay đổi.

## 11. Phạm vi bảo vệ của version và các giới hạn

Version theo từng dòng bảo vệ các cập nhật cạnh tranh trên chính dòng đó. Nó không tự động bảo vệ mọi bất biến liên quan đến nhiều dòng hoặc nhiều bảng.

Ví dụ, quy tắc là tổng số chỗ đã đặt không vượt quá sức chứa của một lớp học. Nếu mỗi request chỉ cập nhật một dòng booking khác nhau, version của từng booking có thể không phát hiện được hai request cùng vượt giới hạn tổng. Cần bảo vệ tài nguyên chung hoặc dùng một phép cập nhật nguyên tử trên dòng quota:

~~~sql
UPDATE class_capacity
SET reserved_count = reserved_count + 1,
    version = version + 1
WHERE class_id = 100
  AND reserved_count < capacity;
~~~

Nếu một dòng được cập nhật, một chỗ đã được giữ. Nếu 0 dòng, lớp có thể hết chỗ hoặc không tồn tại. Cần xử lý reservation và việc hủy/hoàn chỗ trong cùng mô hình nghiệp vụ.

Các giới hạn khác:

- **Version bị bỏ qua ở một đường ghi:** một batch job hoặc script cập nhật dữ liệu mà không tăng version có thể làm request khác không phát hiện thay đổi.
- **Cập nhật nhiều dòng:** mỗi dòng cần token phù hợp, hoặc cần một cơ chế bảo vệ ở cấp aggregate nếu bất biến trải qua nhiều dòng.
- **Transaction có side effect ngoài database:** rollback hoặc optimistic conflict không hoàn tác email, thanh toán hay HTTP request đã thực hiện. Nên tách side effect bằng Outbox và idempotency.
- **Retry quá nhiều:** nếu xung đột thường xuyên, retry liên tục làm tăng tải và độ trễ. Cần xem lại mức tranh chấp, thiết kế dữ liệu hoặc dùng pessimistic locking cho vùng nóng.
- **Version không được trả về client:** nếu client chỉnh sửa dựa trên dữ liệu cũ mà không gửi token phiên bản, server không thể thực hiện kiểm tra optimistic locking đúng với bản client đã đọc.

Optimistic locking đặc biệt phù hợp khi xung đột tương đối hiếm. Nếu nhiều transaction liên tục cập nhật cùng một dòng nóng, xung đột và retry có thể trở thành chi phí đáng kể. Khi đó có thể cần phân vùng dữ liệu, cập nhật nguyên tử, gom thao tác hoặc cân nhắc khóa bi quan.

## 12. Khi nào dùng UPDATE có điều kiện và khi nào dùng version?

Hai kỹ thuật có quan hệ gần nhau nhưng không hoàn toàn giống nhau.

- **UPDATE có điều kiện** là kỹ thuật SQL rộng: chỉ cập nhật khi các điều kiện trong WHERE thỏa. Điều kiện có thể là version, trạng thái, số lượng, số dư hoặc quyền sở hữu.
- **Optimistic locking bằng version** là một trường hợp cụ thể: dùng token phiên bản đã đọc để phát hiện một thay đổi cạnh tranh kể từ thời điểm đọc.

Ví dụ chỉ kiểm tra điều kiện nghiệp vụ:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Ví dụ kiểm tra version:

~~~sql
UPDATE documents
SET title = 'Updated title',
    version = version + 1
WHERE document_id = 42
  AND version = 7;
~~~

Ví dụ kết hợp cả hai:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 2,
    version = version + 1
WHERE product_id = 42
  AND version = 7
  AND available_quantity >= 2
  AND status = 'ACTIVE';
~~~

Câu lệnh kết hợp yêu cầu cả dữ liệu chưa bị thay đổi kể từ lần đọc, sản phẩm còn đủ số lượng và trạng thái vẫn ACTIVE. Khi affected rows bằng 0, ứng dụng có thể đọc lại để xác định điều kiện nào không còn đúng.

## 13. Checklist thiết kế

Khi thêm optimistic locking vào một bảng hoặc API, cần xác định:

1. Dòng nào là đơn vị cạnh tranh cần bảo vệ: một row hay một aggregate gồm nhiều row?
2. Cột version được khởi tạo thế nào và kiểu dữ liệu có phù hợp không?
3. Mọi đường cập nhật có làm version thay đổi hay không?
4. UPDATE có kiểm tra đúng version mà client hoặc transaction đã đọc không?
5. Ứng dụng có kiểm tra affected-row count và phân biệt conflict với not-found không?
6. Khi conflict, nghiệp vụ cần đọc lại, hợp nhất thay đổi, retry hay trả lỗi cho client?
7. Có side effect bên ngoài nào cần tách khỏi transaction không?
8. Xung đột có hiếm đủ để optimistic locking hiệu quả không?
9. API có truyền version hoặc ETag để client gửi lại khi cập nhật không?
10. Các bulk/native update và tác vụ nền có tuân thủ cùng quy tắc version không?

## Kết luận

Cột version và câu UPDATE có điều kiện tạo thành cơ chế optimistic locking đơn giản nhưng hữu ích. Ứng dụng đọc dữ liệu cùng version, tính toán mà không cần giữ row lock trong suốt thời gian xử lý, rồi cập nhật chỉ khi version vẫn khớp. Việc tăng version trong cùng câu UPDATE giúp lần ghi tiếp theo nhận ra dữ liệu đã thay đổi.

Khi affected rows bằng 0, ứng dụng phải xử lý xung đột theo nghiệp vụ: đọc lại và hợp nhất, tính toán lại, hoặc trả conflict cho client. Điều kiện nghiệp vụ như số lượng còn đủ hay trạng thái cho phép có thể được đưa vào cùng WHERE để database kiểm tra nguyên tử. Version bảo vệ thay đổi cạnh tranh trên phạm vi token đại diện; với bất biến nhiều dòng hoặc dữ liệu nóng, cần thêm constraint, cập nhật nguyên tử, isolation phù hợp hoặc một chiến lược khóa khác.

