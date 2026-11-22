# Phân loại DataAccessException và lỗi được dịch từ MongoDB driver

Trong ứng dụng **Spring Data MongoDB**, một thao tác `MongoTemplate`, repository hoặc `ReactiveMongoTemplate` có thể thất bại vì nhiều nguyên nhân: trùng khóa duy nhất, mất kết nối, tài khoản thiếu quyền, truy vấn không hợp lệ, xung đột cập nhật hoặc lỗi giao dịch. Các nguyên nhân này đòi hỏi cách xử lý khác nhau. Nếu chỉ bắt `Exception` rồi thử lại hoặc trả chung HTTP 500, hệ thống có thể gửi yêu cầu lặp, che giấu lỗi lập trình và khiến việc chẩn đoán production khó khăn.

Spring cung cấp hệ thống ngoại lệ truy cập dữ liệu **`DataAccessException`** nhằm diễn đạt loại lỗi tương đối độc lập với công nghệ lưu trữ. Spring Data MongoDB sử dụng cơ chế **dịch ngoại lệ** (*exception translation*) để chuyển nhiều lỗi của MongoDB Java driver thành các loại `DataAccessException` phù hợp. Bài này trình bày cách nhận diện lỗi, lựa chọn phương án xử lý, ghi log và kiểm thử trong bối cảnh kết nối, ánh xạ document, truy vấn, index, transaction và reactive access.

## 1. Một lỗi có thể đi qua nhiều lớp

Xét tình huống đăng ký người dùng bằng email, trong đó collection `customers` có unique index trên `email`. Một thao tác `insert` dùng email đã tồn tại có thể đi qua các lớp sau:

~~~mermaid
flowchart TD
    A[Service gọi MongoTemplate.insert] --> B[Spring Data MongoDB]
    B --> C[MongoDB Java driver]
    C --> D[(MongoDB server)]
    D --> E[Server trả duplicate key, mã 11000]
    E --> F[Driver tạo MongoWriteException hoặc loại liên quan]
    F --> G[MongoExceptionTranslator / Spring Data]
    G --> H[DuplicateKeyException]
    H --> I[Service xử lý theo quy tắc nghiệp vụ]
~~~

Ba lớp cần phân biệt:

1. **Lỗi tại MongoDB server**: mã lỗi, tên lỗi, thông điệp, thông tin thao tác thất bại và nhãn lỗi trong những trường hợp được hỗ trợ.
2. **Ngoại lệ MongoDB Java driver**: thường thuộc họ `com.mongodb.MongoException`, ví dụ `MongoWriteException`, `MongoCommandException`, `MongoTimeoutException`, `MongoSocketException` hoặc `MongoBulkWriteException`.
3. **Ngoại lệ do Spring biểu diễn**: thường là một lớp thuộc `org.springframework.dao.DataAccessException`, ví dụ `DuplicateKeyException`, `DataIntegrityViolationException` hoặc `DataAccessResourceFailureException`.

`DataAccessException` là **unchecked exception**, nên mã nghiệp vụ có thể xử lý những loại lỗi cụ thể mà không phụ thuộc trực tiếp vào mọi lớp ngoại lệ của MongoDB driver. Tuy nhiên, quá trình dịch **không phải ánh xạ một-một**: nhiều lỗi driver có thể trở thành cùng một loại Spring, một lỗi có thể không có loại Spring chuyên biệt, và đường gọi sử dụng driver trực tiếp có thể lộ ra ngoại lệ gốc.

## 2. Cơ chế dịch ngoại lệ của Spring Data MongoDB

Spring Data MongoDB có thành phần `MongoExceptionTranslator`, thực hiện hợp đồng `PersistenceExceptionTranslator`. Khi sử dụng các API Spring Data như `MongoTemplate` hoặc repository, nhiều lỗi từ driver sẽ được chuyển thành kiểu thuộc hệ thống ngoại lệ truy cập dữ liệu của Spring. Đường thực thi reactive cũng cung cấp cơ chế chuyển lỗi tương ứng thông qua luồng `onError`.

Annotation `@Repository` có thể tham gia cơ chế dịch ngoại lệ dựa trên proxy của Spring đối với những loại exception mà hệ thống translator hỗ trợ. Nhưng **không phải cứ gắn `@Repository` là mọi `RuntimeException` đều biến thành `DataAccessException`**. Mã tự gọi trực tiếp MongoDB Java driver, thư viện bên ngoài hoặc một callback tùy chỉnh cần được kiểm tra riêng để biết ngoại lệ thực tế nổi lên ở biên gọi nào.

Ví dụ các import thường gặp:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
~~~

Không nên dựa vào **chỉ tên class** để khẳng định một driver exception sẽ luôn được dịch thành một class Spring cụ thể trên mọi phiên bản. Cần xem phiên bản Spring Data MongoDB, MongoDB Java driver, loại thao tác và chuỗi `cause` trong log/test thực tế.

## 3. Phân loại theo ý nghĩa và hành động xử lý

Bảng sau là **hướng chẩn đoán phổ biến**, không phải quy tắc ánh xạ cứng áp dụng cho mọi lỗi và phiên bản:

| Nhóm | Loại ngoại lệ thường gặp | Ý nghĩa | Hành động ban đầu |
| --- | --- | --- | --- |
| Vi phạm ràng buộc duy nhất | `DuplicateKeyException` | Trùng `_id` hoặc giá trị của unique index; MongoDB thường báo mã `11000` | Kiểm tra khóa bị trùng, trả lỗi nghiệp vụ hoặc xử lý idempotency; không retry vô điều kiện |
| Vi phạm toàn vẹn dữ liệu | `DataIntegrityViolationException` | Thao tác ghi vi phạm một ràng buộc hoặc quy tắc dữ liệu được translator nhận diện | Đọc nguyên nhân thực tế và quy tắc schema/index; sửa dữ liệu hoặc luồng ghi |
| Xung đột khóa phiên bản | `OptimisticLockingFailureException` | Spring Data phát hiện cập nhật với `@Version` không còn hợp lệ | Đọc lại trạng thái, quyết định xử lý xung đột; có thể báo `409 Conflict` cho API thích hợp |
| Không truy cập được tài nguyên | `DataAccessResourceFailureException` hoặc ngoại lệ driver liên quan | MongoDB không sẵn sàng, lỗi kết nối/chọn server hoặc tài nguyên cần thiết không truy cập được | Kiểm tra topology, mạng, pool, timeout, health; retry có giới hạn nếu an toàn |
| Hết thời gian | `QueryTimeoutException` hoặc ngoại lệ MongoDB driver tương ứng | Truy vấn/hoạt động vượt giới hạn thời gian ở một tầng | Xác định timeout ở server, driver hay ứng dụng; xem `explain`, tải và tính an toàn trước khi retry |
| Sai API hoặc tham số | `InvalidDataAccessApiUsageException` | Dùng API sai hợp đồng, tham số không hợp lệ hoặc lỗi cấu hình tầng truy cập | Sửa code, kiểm tra kiểu dữ liệu và mapping; thường không retry |
| Thiếu quyền | `PermissionDeniedDataAccessException` hoặc `MongoSecurityException`/`MongoCommandException` | Không được xác thực hoặc không có quyền thực hiện command | Xác minh cấu hình user, roles, database và cơ chế xác thực |
| Lỗi chưa phân loại rõ | Một `DataAccessException` tổng quát hoặc ngoại lệ MongoDB driver gốc | Translator chưa có kiểu chuyên biệt, hoặc lỗi đi qua đường gọi khác | Xem cause, mã lỗi, nhãn, command và bối cảnh; tránh kết luận chỉ từ lớp bọc |

Lưu ý sự khác biệt giữa **loại ngoại lệ** và **chính sách thử lại**. Một `DataAccessResourceFailureException` có thể do sự cố thoáng qua, nhưng việc lặp lại thao tác ghi sau khi mất kết nối vẫn có thể nguy hiểm nếu không xác định được lần ghi đầu đã thành công hay chưa. Ngược lại, `DuplicateKeyException` thường không tự hết dù có retry.

### Một số lớp gốc phía driver cần nhận diện

| Driver exception | Tình huống cần điều tra |
| --- | --- |
| `MongoWriteException` | Một thao tác ghi đơn lẻ bị server từ chối; kiểm tra mã lỗi, write error, unique index hoặc validator |
| `MongoBulkWriteException` | Thao tác bulk có lỗi ở một hay nhiều mục; có thể đã có **một phần ghi thành công** khi không nằm trong giao dịch bao trùm |
| `MongoCommandException` | Command thất bại, ví dụ thiếu quyền hoặc tùy chọn không được hỗ trợ |
| `MongoWriteConcernException` | Ghi không đáp ứng được yêu cầu xác nhận write concern; cần xác minh trạng thái thực tế |
| `MongoTimeoutException` | Không chọn được server hoặc thao tác timeout theo loại/lớp cụ thể; xem cấu hình timeout, topology và tải |
| `MongoSocketException` | Sự cố giao tiếp mạng qua socket; có thể phát sinh trước hoặc sau khi server xử lý yêu cầu |
| `MongoSecurityException` | Sự cố xác thực, thông tin đăng nhập hoặc cơ chế bảo mật |

Đọc cả **class + error code + error labels + cause + thao tác đang chạy**, vì mỗi thành phần giải thích một khía cạnh khác nhau.

## 4. `DuplicateKeyException`: lỗi ràng buộc hay yêu cầu lặp?

Ví dụ ứng dụng có collection `customers` và yêu cầu email phải duy nhất:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {
    @Id
    private String id;

    @Indexed(unique = true)
    private String email;

    private String displayName;

    // Constructors, getters và setters được lược bỏ.
}
~~~

`@Indexed(unique = true)` mô tả ý định tạo unique index. Trong dự án thực tế phải **xác minh index thật sự đã tồn tại** trên MongoDB. Các phiên bản Spring Data MongoDB hiện đại không mặc định tự tạo index chỉ vì có annotation; cần cấu hình hoặc tạo index qua cơ chế triển khai riêng. Nếu không có unique index ở database, hai lệnh ghi có thể vẫn cùng thành công.

Ví dụ service xử lý `DuplicateKeyException` tại biên nghiệp vụ:

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final MongoTemplate template;

    public CustomerRegistrationService(MongoTemplate template) {
        this.template = template;
    }

    public Customer register(Customer customer) {
        try {
            return template.insert(customer);
        } catch (DuplicateKeyException ex) {
            throw new CustomerAlreadyExistsException(
                "Không thể đăng ký vì khóa định danh đã tồn tại", ex);
        }
    }
}

class CustomerAlreadyExistsException extends RuntimeException {
    CustomerAlreadyExistsException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Mã ví dụ đơn giản hóa chính sách nghiệp vụ. **Không được mặc định** mọi `DuplicateKeyException` ở `customers` đều là email bị trùng: lỗi có thể do `_id` hoặc một unique index khác. Nếu cần trả thông báo “email đã được sử dụng”, hãy xác định ràng buộc liên quan bằng cấu trúc index và thông tin lỗi tin cậy; không chỉ đoán từ tên service.

Trên môi trường chẩn đoán, có thể kiểm tra index và thao tác đã gây lỗi:

~~~javascript
db.customers.getIndexes();
db.customers.findOne({ email: "test@example.com" });
~~~

Lỗi thường chứa **mã `11000`** (`E11000 duplicate key error`) khi server phát hiện vi phạm unique index. Không viết logic nghiệp vụ dựa vào việc phân tích chuỗi `E11000` hoặc cắt tên index từ thông điệp: nội dung thông điệp có thể thay đổi, chứa giá trị nhạy cảm và không phải API ổn định. Dựa vào exception type/code ở tầng thích hợp và dữ liệu nghiệp vụ đã biết.

**Đừng giải quyết bằng cách “kiểm tra trước rồi insert” đơn thuần:** giữa lần `find` và `insert`, request khác vẫn có thể ghi cùng khóa. Unique index mới là biên bảo đảm tính duy nhất; code cần xử lý xung đột khi hai luồng cạnh tranh.

## 5. `DataIntegrityViolationException` và lỗi dữ liệu không hợp lệ

`DataIntegrityViolationException` là ngoại lệ tổng quát cho một số vi phạm toàn vẹn dữ liệu. `DuplicateKeyException` là một kiểu cụ thể hơn trong hệ phân cấp Spring DAO. Vì vậy, nếu cần phân biệt cả hai, bắt loại cụ thể trước:

~~~java
try {
    template.insert(customer);
} catch (DuplicateKeyException ex) {
    // Xử lý khóa trùng theo quy tắc nghiệp vụ.
    throw ex;
} catch (DataIntegrityViolationException ex) {
    // Điều tra ràng buộc toàn vẹn khác nếu translator phân loại được.
    throw ex;
}
~~~

MongoDB hỗ trợ validation rule cho collection, unique index, kiểm tra kiểu/giá trị và nhiều ràng buộc khác ở tầng ứng dụng. Tuy nhiên **không có cam kết** rằng mọi lỗi validator từ MongoDB sẽ luôn trở thành `DataIntegrityViolationException` ở mọi phiên bản Spring Data. Một lỗi có thể là `MongoWriteException`, `MongoCommandException` hoặc một ngoại lệ Spring ít chuyên biệt hơn. Phải kiểm tra code, cause và nguồn thao tác.

Với validation bị từ chối, cần xem document có tuân thủ JSON Schema/validator, kiểu BSON (`Date`, số, chuỗi, `ObjectId`), chính sách nullable và mapping `@Field` hay không. Không retry lặp lại cùng payload nếu đầu vào không thay đổi; sửa dữ liệu hoặc code tạo dữ liệu mới là giải pháp đúng.

## 6. `OptimisticLockingFailureException` và cập nhật cạnh tranh

Spring Data MongoDB hỗ trợ **optimistic locking** bằng trường `@Version`. Giả sử hai request cùng đọc một document `ProductStock` có `version = 7`. Request A lưu trước và làm version tăng. Request B vẫn cố lưu document với version cũ; khi điều kiện version không khớp, Spring Data có thể ném `OptimisticLockingFailureException`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("product_stock")
public class ProductStock {
    @Id
    private String id;

    @Version
    private Long version;

    private int availableQuantity;

    // Constructors, getters và setters được lược bỏ.
}
~~~

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as MongoDB
    A->>DB: Đọc stock version=7
    B->>DB: Đọc stock version=7
    A->>DB: Lưu với điều kiện version=7
    DB-->>A: Thành công, version=8
    B->>DB: Lưu với điều kiện version=7
    DB-->>B: Không khớp phiên bản
    B-->>B: OptimisticLockingFailureException
~~~

Các điểm quan trọng:

- Cần sử dụng thao tác Spring Data có hỗ trợ `@Version` trong đúng ngữ cảnh. Nếu cập nhật bằng driver trực tiếp hoặc câu lệnh tùy chỉnh không đưa version vào điều kiện, cơ chế bảo vệ có thể bị bỏ qua.
- Sử dụng **acknowledged write concern** để xác định được thao tác không sửa document nào; nếu không nhận được xác nhận ghi, không thể dựa vào số document sửa để phát hiện xung đột đầy đủ.
- Xung đột là kết quả của cập nhật cạnh tranh, **không phải** mất kết nối. Có thể đọc lại và áp dụng lại lệnh nếu nghiệp vụ cho phép; không retry việc lấy object cũ rồi `save` lại liên tục.
- Khi một API dùng optimistic locking để chống lost update, phản hồi `409 Conflict` là lựa chọn thường gặp; ứng dụng cần quyết định có hiển thị trạng thái mới cho người dùng hay không.

Ví dụ tồn kho phải xem xét cả tính nguyên tử của phép giảm số lượng. Với quy tắc “chỉ trừ khi còn đủ hàng”, một lệnh `update` có điều kiện tại database có thể thích hợp hơn thao tác đọc–tính–ghi, và vẫn cần xử lý trường hợp không có document nào được cập nhật.

## 7. Mất kết nối, timeout và các trạng thái kết quả không chắc chắn

Lỗi socket hoặc chọn server thường khác hẳn lỗi duplicate key. Chúng có thể diễn ra ở các thời điểm khác nhau:

1. **Trước khi gửi request**: chẳng hạn client không tìm được server phù hợp. Có thể chưa có thao tác ghi nào xảy ra.
2. **Trong khi gửi hoặc đợi phản hồi**: client có thể không biết server đã thực thi thao tác hay chưa.
3. **Sau khi server xử lý**: kết nối đứt trước khi client nhận xác nhận, khiến trạng thái đối với client không chắc chắn.

Lỗi thường liên quan `MongoSocketException`, `MongoTimeoutException`, các exception về chọn server và đôi khi được Spring biểu diễn bằng `DataAccessResourceFailureException`. `MongoExecutionTimeoutException` có thể xuất hiện nếu truy vấn vượt giới hạn thời gian thực thi phía server; tình huống này cần chẩn đoán khác với việc không thiết lập được kết nối.

Khi lỗi liên quan kết nối hoặc timeout, hãy kiểm tra MongoDB URI (không ghi lộ mật khẩu), DNS, TLS, replica set/shard topology, quyền kết nối, pool, `serverSelectionTimeout`, `connectTimeout`, `socketTimeout`/cấu hình timeout áp dụng, giới hạn thực thi như `maxTimeMS`, tải CPU/I/O và các câu lệnh đang chạy.

**Không được suy ra “ghi thất bại chắc chắn” chỉ từ timeout phía client.** Nếu yêu cầu tạo đơn hàng bị mất phản hồi, việc tự động gửi lại cùng lệnh có thể tạo đơn thứ hai khi lệnh đầu đã commit. Hãy dùng khóa idempotency hoặc định danh ổn định, unique index và cơ chế truy vấn đối soát trạng thái trước khi quyết định ghi lại.

Driver MongoDB có cơ chế retryable reads/writes và quy tắc riêng tùy cấu hình, topology và loại thao tác. Retry tự xây dựng ở Spring phải tính cả khả năng driver **đã retry**. Với các lệnh không idempotent hoặc có tác dụng phụ ngoài MongoDB, retry nhiều lớp có thể tăng nguy cơ gây kết quả trùng.

## 8. Lỗi giao dịch: phân biệt retry toàn giao dịch và retry commit

Giao dịch MongoDB có thể gặp xung đột, lỗi mạng hoặc trạng thái commit không chắc chắn. Một số ngoại lệ driver mang **error label** để người gọi quyết định chiến lược phục hồi. Hai nhãn quan trọng:

| Nhãn MongoDB | Ý nghĩa vận hành | Cách xử lý định hướng |
| --- | --- | --- |
| `TransientTransactionError` | Giao dịch gặp lỗi có thể thoáng qua trước khi commit hoàn tất | Cân nhắc chạy lại **toàn bộ giao dịch** từ đầu với dữ liệu phù hợp và giới hạn số lần |
| `UnknownTransactionCommitResult` | Client không chắc kết quả commit đã được xác nhận thế nào | Dùng quy trình **retry commit**, không tự động chạy lại toàn bộ nghiệp vụ như giao dịch mới |

Trường hợp `UnknownTransactionCommitResult` rất nhạy cảm: một commit có thể đã thành công dù client chưa nhận được xác nhận. Gọi lại API tạo đơn hàng từ đầu là hành động khác với gọi lại `commitTransaction` trong cùng quy trình xử lý giao dịch.

Nếu dùng `MongoTransactionManager` và `@Transactional` trong Spring Data MongoDB, cần hiểu rõ cơ chế kết thúc transaction và ranh giới retry. Không đặt `@Retryable` cho toàn bộ method một cách máy móc, đặc biệt khi method còn gửi email, gọi cổng thanh toán hoặc phát event trước khi commit. Những tác dụng phụ bên ngoài database nên được phối hợp bằng thiết kế như **transactional outbox** và idempotent consumer khi thích hợp.

Các error label có thể bị che bởi lớp ngoại lệ Spring nếu chỉ nhìn exception bên ngoài. Khi cần chẩn đoán, đọc chuỗi `cause` và tìm `MongoException`, nhưng vẫn phải tuân thủ hợp đồng xử lý transaction của framework đang dùng.

## 9. Lựa chọn retry dựa trên nguyên nhân và tính idempotent

| Tình huống | Retry ngay? | Điều kiện/giải pháp phù hợp |
| --- | --- | --- |
| `DuplicateKeyException` | Thường **không** | Xử lý xung đột theo unique index; nếu là request lặp hợp lệ, trả kết quả cũ theo idempotency key |
| Validation/schema không hợp lệ | **Không** | Sửa dữ liệu, mapping hoặc lệnh ghi |
| `OptimisticLockingFailureException` | **Có điều kiện** | Đọc trạng thái mới và đánh giá lại quy tắc, giới hạn số lần |
| Mất kết nối trước read | **Có điều kiện** | Retry với backoff/jitter khi dịch vụ có thể phục hồi, có timeout/budget |
| Timeout trong write | **Chưa thể kết luận** | Kiểm tra kết quả đã ghi, idempotency, retryable-write semantics và giới hạn số lần |
| `TransientTransactionError` | **Có điều kiện** | Retry toàn bộ transaction theo hướng dẫn driver/framework; tránh tác dụng phụ lặp |
| `UnknownTransactionCommitResult` | **Không retry nghiệp vụ từ đầu** | Xử lý retry commit theo hợp đồng giao dịch và đối soát trạng thái |
| Thiếu quyền/credential sai | **Không** | Sửa user, role, secret, cấu hình xác thực |
| Invalid API usage | **Không** | Sửa truy vấn, tham số, mapping hoặc code |

Một retry policy đúng cần có **giới hạn tổng thời gian**, tối đa số lần, exponential backoff/jitter, quan sát số lần retry và kiểm soát áp lực lên hệ thống đang lỗi. Không dùng `retryWhen(Retry.indefinitely())` cho một luồng ghi nghiệp vụ.

## 10. Phân tích `cause` và thông tin lỗi mà không khóa chặt vào thông điệp

Khi Spring ném `DataAccessException`, lớp bao ngoài diễn đạt **loại lỗi**; `getCause()` có thể giữ nguyên ngoại lệ của driver, từ đó cung cấp mã lỗi và error labels. Một helper nhỏ để chẩn đoán:

~~~java
import com.mongodb.MongoException;

public final class MongoErrorDetails {
    private MongoErrorDetails() {}

    public static MongoException findMongoCause(Throwable error) {
        for (Throwable current = error; current != null;
             current = current.getCause()) {
            if (current instanceof MongoException mongo) {
                return mongo;
            }
        }
        return null;
    }
}
~~~

Ứng dụng có thể dùng helper để ghi **metadata an toàn**:

~~~java
import com.mongodb.MongoException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;

public class MongoErrorReporter {
    private static final Logger log = LoggerFactory.getLogger(MongoErrorReporter.class);

    public void report(String operation, DataAccessException error) {
        MongoException driverError = MongoErrorDetails.findMongoCause(error);
        if (driverError == null) {
            log.warn("mongo operation={} springType={}",
                operation, error.getClass().getSimpleName());
            return;
        }

        log.warn("mongo operation={} springType={} driverType={} code={} "
                + "transientTx={} unknownCommit={}",
            operation,
            error.getClass().getSimpleName(),
            driverError.getClass().getSimpleName(),
            driverError.getCode(),
            driverError.hasErrorLabel("TransientTransactionError"),
            driverError.hasErrorLabel("UnknownTransactionCommitResult"));
    }
}
~~~

Đoạn mã trên mang tính **chẩn đoán**; `MongoException.getCode()` có thể không phải mã server hữu ích đối với lỗi ở tầng kết nối. Với bulk write, thông tin ở các `writeErrors` cần được xử lý riêng. Trong production, log thêm `requestId`/`traceId`, collection, tên operation, độ trễ, trạng thái retry và môi trường MongoDB (không lộ thông tin bí mật).

Không log nguyên MongoDB connection string chứa credential, payload có dữ liệu cá nhân, toàn bộ document hoặc `error.getMessage()` một cách vô điều kiện: một số thông điệp lỗi có thể mang tên field và giá trị dữ liệu nhạy cảm. Không dựa vào regex đọc message để định tuyến lỗi; ưu tiên kiểu ngoại lệ, mã lỗi có cấu trúc và dữ liệu hợp đồng nghiệp vụ.

## 11. Xử lý ngoại lệ trong ứng dụng blocking và reactive

### Với `MongoTemplate` hoặc repository đồng bộ

Nên đặt xử lý ở tầng phù hợp:

- **Repository / data access**: thực hiện thao tác dữ liệu, để ngoại lệ tiếp tục lên nếu không thể xử lý có ý nghĩa.
- **Service**: chuyển xung đột dữ liệu thành quyết định nghiệp vụ; ví dụ email đã tồn tại hoặc version bị xung đột.
- **API boundary**: ánh xạ lỗi nghiệp vụ sang phản hồi HTTP ổn định, không lộ stack trace hay thông điệp cơ sở dữ liệu.
- **Observability**: ghi type, code, trace ID, độ trễ và trạng thái retry để chẩn đoán.

`catch (DataAccessException ex)` là điểm cuối cùng để ghi nhận thất bại truy cập dữ liệu nói chung. Nếu đã bắt một loại cụ thể (`DuplicateKeyException`), đặt `catch` đó **trước** `DataAccessException`; thứ tự ngược lại khiến nhánh cụ thể không thể bắt được.

Mọi lỗi truy cập dữ liệu không nên bị chuyển thành cùng một HTTP 500. Ví dụ `DuplicateKeyException` gắn với quy tắc duy nhất đã xác định có thể dẫn đến `409 Conflict`, trong khi hệ thống MongoDB không sẵn sàng có thể dẫn đến phản hồi tạm thời `503 Service Unavailable` kèm chính sách retry phía client. Quy ước phản hồi thực tế cần thống nhất với API contract và trạng thái thao tác ghi.

### Với `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository`

Ngoại lệ trong reactive pipeline thường được truyền qua tín hiệu **`onError`** sau khi subscribe. `try/catch` bao quanh việc tạo `Mono` hoặc `Flux` không bắt được phần lớn lỗi xảy ra khi MongoDB thực thi về sau. Có thể dùng `onErrorMap`, `onErrorResume` và `retryWhen` với bộ lọc lỗi phù hợp.

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public class ReactiveCustomerRegistrationService {
    private final ReactiveMongoTemplate template;

    public ReactiveCustomerRegistrationService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Customer> register(Customer customer) {
        return template.insert(customer)
            .onErrorMap(DuplicateKeyException.class,
                ex -> new CustomerAlreadyExistsException(
                    "Không thể đăng ký vì khóa định danh đã tồn tại", ex));
    }
}
~~~

Trong pipeline ở trên, `onErrorMap` đổi kiểu lỗi để tầng API hiểu, **không tự chạy lại thao tác**. Một `retryWhen(...)` chỉ nên được thêm sau khi xác định tình huống có thể retry và thao tác có tính idempotent; cần cân nhắc cả việc resubscribe có thể làm lặp lại toàn bộ thao tác ghi.

## 12. Bulk write, transaction và thao tác nhiều document

Bulk write có thể thành công một phần rồi mới gặp lỗi. Với bulk **unordered**, driver có thể tiếp tục những phần tử khác dù một phần tử thất bại; với **ordered**, thông thường dừng ở lỗi đầu tiên nhưng các lệnh trước đó đã thực thi có thể đã được ghi. Khi không có transaction bao trùm, không thể coi cả batch là thành công hoặc thất bại nguyên khối.

Ví dụ giả định job import 1.000 customer, trong đó 12 email trùng unique index. Nếu nhận lỗi bulk mà retry toàn bộ 1.000 bản ghi bằng `insert` không kiểm soát, các bản ghi đã thành công trước đó sẽ tiếp tục gây duplicate key. Cần kiểm tra từng lỗi, đối soát những record đã ghi và tổ chức retry theo idempotent key hoặc chia nhỏ batch.

Khi dùng transaction, một lỗi giữa các bước có thể khiến transaction bị abort; tuy nhiên vẫn phải phân biệt **rollback của transaction** với các side effect bên ngoài (email, webhook, broker) vốn không được MongoDB tự rollback. Nếu cần chuyển trạng thái nghiệp vụ rồi phát sự kiện, cân nhắc lưu outbox trong cùng transaction và cho publisher gửi sau commit.

## 13. Quy trình chẩn đoán từ lỗi production

Thực hiện theo thứ tự nhằm tránh thử sai trên hệ thống đang có tải:

1. **Ghi nhận ngữ cảnh:** thao tác `insert`/`save`/`update`/`find`/`aggregate`/`bulkWrite`, collection, environment, version ứng dụng, thời điểm và trace ID.
2. **Xác định loại exception ngoài cùng và nguyên nhân gốc:** `DataAccessException` gì, `cause` có `MongoException` không, có code/label gì.
3. **Phân loại triệu chứng:** integrity, optimistic conflict, permission, connectivity, timeout, transaction hay lỗi lập trình.
4. **Xác minh sự kiện thực tế:** kiểm tra document/index/trạng thái transaction hoặc kết quả ghi bằng truy vấn đối soát an toàn, nhất là khi gặp timeout.
5. **Kiểm tra điều kiện hệ thống:** replica set/shard health, TLS/DNS, pool, slow query, `explain("executionStats")`, write concern và tải thực tế khi liên quan.
6. **Đưa ra hành động có giới hạn:** trả lỗi nghiệp vụ, sửa dữ liệu, retry có backoff, fail-fast, cách ly bản ghi lỗi hoặc phục hồi transaction theo error label.
7. **Giám sát sau xử lý:** tần suất theo exception type/code, tỷ lệ retry, độ trễ MongoDB, pool wait, errors theo collection và chất lượng dữ liệu.

### Ví dụ chẩn đoán nhanh

| Hiện tượng | Dấu hiệu cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Hai request cùng đăng ký email | `DuplicateKeyException`, unique index trên `email`, mã 11000 | Xử lý xung đột; bảo đảm unique index có thật và thông điệp nghiệp vụ chính xác |
| Ghi tồn kho đồng thời làm mất update | `@Version`, `OptimisticLockingFailureException` hoặc cập nhật thiếu điều kiện | Áp dụng compare-and-set/atomic update, xử lý xung đột khi version cũ |
| Mọi truy vấn đôi lúc timeout | Lỗi pool/server selection, DNS, CPU/I/O, kết nối, slow query | Phân biệt lỗi hạ tầng và câu truy vấn chậm; không retry dồn dập |
| Job bulk import dừng giữa chừng | `MongoBulkWriteException`, write errors và kết quả phần đã ghi | Đối soát từng record, chia batch, thiết kế retry idempotent |
| Giao dịch trả lỗi khi commit | Nhãn `UnknownTransactionCommitResult` | Theo quy trình commit retry, không thực thi lại nghiệp vụ như lần mới |
| Truy vấn được phép ở dev nhưng lỗi ở prod | User/role, authentication DB, command code | Sửa quyền và cấu hình triển khai; không che lỗi bằng retry |

## 14. Kiểm thử chiến lược phân loại lỗi

Không cần giả lập mọi cấu trúc nội bộ của `MongoExceptionTranslator`; hãy kiểm tra **hành vi quan sát được** ở các biên dữ liệu và nghiệp vụ. Với kiểm thử tích hợp, dùng MongoDB thực trong môi trường kiểm thử phù hợp (chẳng hạn Testcontainers). Các bài kiểm thử transaction cần cấu hình MongoDB dạng replica set hoặc sharded cluster có hỗ trợ transaction.

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Hai document có cùng khóa unique | MongoDB từ chối lệnh thứ hai; biên Spring nhận loại lỗi được kỳ vọng trong phiên bản đang chạy |
| Cùng thao tác qua `MongoTemplate` và driver trực tiếp | Ghi nhận sự khác nhau về exception type và `cause` nếu có |
| Save entity stale `@Version` | Không ghi đè document mới; trả lỗi xung đột đúng hợp đồng |
| Mất kết nối hoặc hết server selection timeout | Hệ thống báo lỗi hạ tầng, retry giới hạn và không tạo vòng lặp vô hạn |
| Ghi đã thành công nhưng client mất phản hồi | Idempotency/reconciliation không tạo thêm tác dụng phụ |
| Bulk write gồm record hợp lệ và trùng key | Kiểm tra số đã ghi, bản ghi lỗi và khả năng chạy lại an toàn |
| Reactive insert bị duplicate key | `onErrorMap` biến thành lỗi nghiệp vụ khi subscribe; không phát thêm document |
| Một transaction có lỗi giữa chừng | Không coi side effect ngoài database là đã rollback; xử lý nhãn lỗi đúng chính sách |

Nên bổ sung kiểm tra log để chắc chắn không phát tán email, token, mật khẩu, chuỗi kết nối hay nguyên document. Khi nâng phiên bản Spring Data MongoDB hoặc driver, chạy lại test phân loại ngoại lệ vì chi tiết ánh xạ và cause có thể thay đổi.

## 15. Nguyên tắc ghi nhớ

`DataAccessException` giúp mã Spring biểu diễn **loại lỗi truy cập dữ liệu**, còn `MongoException` và các thông tin như **error code** hoặc **error label** có thể giải thích sâu hơn nguyên nhân ở driver/server. Cần xem cả hai khi chẩn đoán; không dựa vào một chuỗi thông báo hoặc giả định mọi lỗi sẽ được dịch giống nhau trên mọi phiên bản.

Với **Spring Data MongoDB**, hãy xử lý `DuplicateKeyException` theo quy tắc duy nhất/idempotency, `OptimisticLockingFailureException` theo điều kiện cập nhật cạnh tranh, lỗi kết nối và timeout theo tình trạng hệ thống và mức độ chắc chắn của thao tác ghi, lỗi transaction theo nhãn tương ứng. **Chọn cách phục hồi dựa trên tính đúng đắn của dữ liệu và hành vi nghiệp vụ**, sau đó mới quyết định retry, trả lỗi hay đối soát.
