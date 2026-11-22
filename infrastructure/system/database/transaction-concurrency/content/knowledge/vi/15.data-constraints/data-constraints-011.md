# Chuyển lỗi ràng buộc thành kết quả nghiệp vụ rõ ràng

Database dùng các ràng buộc toàn vẹn (integrity constraints) để ngăn dữ liệu không hợp lệ được lưu vào hệ thống. Khi một câu INSERT, UPDATE hoặc DELETE vi phạm ràng buộc, database từ chối thao tác và trả lỗi. Ở tầng ứng dụng, lỗi kỹ thuật này cần được chuyển thành một kết quả nghiệp vụ mà người dùng hoặc hệ thống gọi API có thể hiểu và xử lý.

Ví dụ:

- Email đã được tài khoản khác sử dụng có thể trở thành kết quả **EMAIL_ALREADY_REGISTERED**.
- Mã đơn hàng đã tồn tại có thể trở thành **ORDER_ALREADY_EXISTS** hoặc kết quả idempotent trả về đơn hàng đã tạo, tùy hợp đồng API.
- Số lượng đặt vượt số lượng còn lại có thể trở thành **INSUFFICIENT_STOCK**.
- Một lịch đặt phòng trùng khung giờ có thể trở thành **TIME_SLOT_UNAVAILABLE**.
- Xóa khách hàng đang được đơn hàng tham chiếu có thể trở thành **CUSTOMER_HAS_ORDERS**.

Việc chuyển đổi cần dựa trên loại lỗi, tên constraint, thao tác nghiệp vụ và trạng thái transaction. Không nên trả nguyên thông báo SQL cho người dùng, cũng không nên gom mọi lỗi thành “dữ liệu không hợp lệ”. Một ứng dụng cần giữ được thông tin đủ để xử lý đúng, đồng thời không để lộ tên bảng, cấu trúc schema, câu SQL hoặc dữ liệu nội bộ không cần thiết.

## 1. Tại sao cần lớp chuyển đổi lỗi?

Một constraint thường được đặt tên và thực thi ở database. Nó bảo vệ dữ liệu ngay cả khi có nhiều request chạy đồng thời, khi một batch job ghi dữ liệu hoặc khi một service khác bỏ qua validation ở ứng dụng.

Ví dụ, ứng dụng kiểm tra email trước khi đăng ký:

~~~sql
SELECT user_id
FROM users
WHERE email = 'alice@example.com';
~~~

Nếu không có kết quả, ứng dụng cho phép tiếp tục. Nhưng hai request có thể cùng kiểm tra trước khi một trong hai kịp INSERT:

~~~text
Request A                         Request B
---------                         ---------
SELECT email                      SELECT email
Không tìm thấy                    Không tìm thấy
INSERT email                      INSERT email
COMMIT                            Chờ hoặc thực hiện INSERT
                                  UNIQUE violation
~~~

Kiểm tra ở ứng dụng giúp phản hồi sớm trong trường hợp thông thường, nhưng không thể bảo vệ tính duy nhất trước cạnh tranh đồng thời. UNIQUE constraint trong database mới là lớp bảo vệ cuối cùng.

Vì vậy, ứng dụng cần xử lý cả hai đường:

1. Validation trước khi ghi để phản hồi sớm và dễ hiểu.
2. Bắt lỗi constraint từ database để xử lý đúng khi có cạnh tranh hoặc đường ghi khác.

Lớp chuyển đổi lỗi thường nằm ở ranh giới persistence/service hoặc exception handler của API. Nó biến chi tiết phụ thuộc database thành mã lỗi nghiệp vụ ổn định.

~~~text
HTTP request / UI action
        |
        v
Application validation
        |
        +-- Không hợp lệ --> Business result / validation response
        |
        v
Application service
        |
        v
Database transaction
        |
        +-- Ghi thành công --> Commit --> Success result
        |
        +-- Constraint error
                 |
                 v
        Persistence error translator
                 |
                 v
        Business error code
                 |
                 v
        API response / UI message
~~~

## 2. Constraint nào thường cần ánh xạ?

Không phải mọi constraint đều tương ứng với một thông báo cho người dùng. Cần xem quy tắc dữ liệu đó có ý nghĩa gì trong nghiệp vụ.

| Loại constraint | Ví dụ dữ liệu | Kết quả nghiệp vụ có thể dùng |
|---|---|---|
| UNIQUE | Email, username hoặc mã đơn hàng bị trùng | EMAIL_ALREADY_REGISTERED, USERNAME_TAKEN, ORDER_ALREADY_EXISTS |
| PRIMARY KEY | ID đã tồn tại | RESOURCE_ALREADY_EXISTS hoặc xử lý idempotent nếu cùng một yêu cầu |
| FOREIGN KEY | Chi tiết đơn hàng tham chiếu đơn hàng không tồn tại | ORDER_NOT_FOUND hoặc INVALID_REFERENCE |
| FOREIGN KEY khi xóa | Khách hàng vẫn được đơn hàng tham chiếu | CUSTOMER_HAS_ORDERS, RESOURCE_IN_USE |
| CHECK | Số lượng âm, ngày kết thúc trước ngày bắt đầu | INVALID_QUANTITY, INVALID_DATE_RANGE |
| NOT NULL | Thiếu giá trị bắt buộc | REQUIRED_FIELD_MISSING |
| EXCLUSION | Hai lịch đặt phòng trùng khoảng thời gian | TIME_SLOT_UNAVAILABLE |
| Constraint trạng thái | Một giá trị không thuộc tập trạng thái được phép, nếu được bảo vệ bằng CHECK | INVALID_STATUS_TRANSITION hoặc INVALID_STATUS |

Tên lỗi cần diễn đạt ý nghĩa của nghiệp vụ, không phụ thuộc tên constraint vật lý. Ví dụ, database có constraint tên uq_users_email, nhưng API có thể công bố mã EMAIL_ALREADY_REGISTERED. Nếu đổi tên bảng hoặc constraint trong migration, hợp đồng API vẫn giữ nguyên.

Một số quy tắc không thể biểu diễn bằng một constraint đơn giản. Ví dụ “mỗi lớp học phải có ít nhất một giảng viên đang hoạt động” liên quan đến nhiều dòng hoặc nhiều bảng. Quy tắc này có thể cần SERIALIZABLE, khóa một dòng điều phối, trigger hoặc thiết kế dữ liệu khác. Nếu database trả serialization failure, ứng dụng không nên ánh xạ nó thành một constraint violation chỉ vì kết quả cuối cùng liên quan đến một quy tắc nghiệp vụ.

## 3. Đặt tên constraint có chủ đích

Tên constraint giúp ứng dụng hoặc người vận hành xác định chính xác quy tắc nào đã thất bại. Tên mặc định do database sinh có thể khó đọc hoặc khác nhau giữa môi trường. Nên đặt tên rõ ràng, ổn định và có quy ước.

Ví dụ:

~~~sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    username VARCHAR(80) NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT uq_users_username UNIQUE (username)
);
~~~

Bảng orders:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    CONSTRAINT ck_orders_total_non_negative
        CHECK (total_amount >= 0),
    CONSTRAINT ck_orders_status
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED'))
);
~~~

Một quy ước dễ quản lý:

- UNIQUE: uq_<table>_<columns>.
- FOREIGN KEY: fk_<table>_<referenced_table>.
- CHECK: ck_<table>_<business_rule>.
- EXCLUSION: ex_<table>_<business_rule>.
- PRIMARY KEY: pk_<table>, nếu hệ thống cần đặt tên tường minh.

Tên constraint không nên chứa thông tin nhạy cảm hoặc chi tiết triển khai không cần thiết. Tránh dùng tên chung như constraint_1, uk_01 hoặc check_value vì khó ánh xạ và khó điều tra.

Tên cần ổn định qua các migration. Nếu ứng dụng ánh xạ theo tên constraint, việc đổi tên phải được quản lý như thay đổi tương thích giữa schema và code.

## 4. Chuyển lỗi kỹ thuật thành mã lỗi nghiệp vụ

API nên trả một mã lỗi có ý nghĩa ổn định, cùng thông tin ngắn gọn và có thể hành động. Ví dụ:

~~~json
{
  "code": "EMAIL_ALREADY_REGISTERED",
  "message": "Email này đã được sử dụng.",
  "field": "email"
}
~~~

Một response khác cho tồn kho:

~~~json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "Số lượng sản phẩm còn lại không đủ.",
  "field": "quantity"
}
~~~

Mã lỗi có thể được dùng bởi frontend để chọn thông báo, chuyển focus đến trường cần sửa hoặc hiển thị hành động tiếp theo. Message có thể được dịch theo ngôn ngữ giao diện, trong khi code vẫn ổn định để client xử lý.

Một mô hình lỗi ứng dụng có thể gồm:

~~~text
BusinessError
    code: EMAIL_ALREADY_REGISTERED
    category: CONFLICT
    field: email
    messageKey: user.email.alreadyRegistered
    retryable: false
~~~

Không nhất thiết mọi API đều cần đủ các trường này. Điều quan trọng là phân biệt:

- **Code:** định danh lỗi ổn định, dùng cho logic máy.
- **Message:** nội dung có thể hiển thị cho người dùng.
- **Field/resource:** đối tượng nghiệp vụ liên quan nếu có.
- **Retryability:** có nên thử lại tự động hay không.
- **Correlation ID:** mã tra cứu log khi cần hỗ trợ, không phải chi tiết database.

Không trả SQLSTATE, vendor error code, tên bảng, tên index, câu SQL hoặc stack trace như nội dung công khai của API. Các thông tin đó thuộc log kỹ thuật có kiểm soát.

## 5. Phân loại lỗi bằng SQLSTATE hoặc vendor error code

Tên exception ở tầng ứng dụng thường chưa đủ để xác định lỗi. Driver và framework có thể bọc lỗi database trong các exception chung. Nên lấy mã lỗi gốc và tên constraint nếu driver cung cấp.

Một số SQLSTATE thường gặp trong PostgreSQL:

| SQLSTATE | Ý nghĩa | Hướng ánh xạ |
|---|---|---|
| 23502 | NOT NULL violation | REQUIRED_FIELD_MISSING hoặc lỗi dữ liệu nội bộ |
| 23503 | FOREIGN KEY violation | RESOURCE_NOT_FOUND hoặc RESOURCE_IN_USE tùy thao tác |
| 23505 | UNIQUE violation | EMAIL_ALREADY_REGISTERED, USERNAME_TAKEN, RESOURCE_ALREADY_EXISTS |
| 23514 | CHECK violation | INVALID_VALUE hoặc lỗi bất biến nội bộ |
| 23P01 | EXCLUSION violation | TIME_SLOT_UNAVAILABLE hoặc RESOURCE_CONFLICT |
| 40001 | Serialization failure | Retry toàn bộ transaction; không coi là constraint violation |
| 40P01 | Deadlock detected | Retry có giới hạn và theo dõi deadlock; không trả thành lỗi nhập liệu |

Nhóm SQLSTATE 23 biểu thị integrity constraint violation. Mã 40001 và 40P01 thuộc nhóm lỗi transaction/concurrency khác.

Một số mã phổ biến khác:

| Database | Mã lỗi | Ý nghĩa |
|---|---:|---|
| MySQL/InnoDB | 1062 | Duplicate key |
| MySQL/InnoDB | 1451 | Không thể xóa/cập nhật bản ghi cha do bản ghi con tham chiếu |
| MySQL/InnoDB | 1452 | Không thể thêm/cập nhật bản ghi con do khóa ngoại không hợp lệ |
| SQL Server | 2601, 2627 | Duplicate key hoặc unique constraint |
| SQL Server | 547 | Vi phạm CHECK hoặc FOREIGN KEY |
| Oracle | ORA-00001 | Unique constraint violation |
| Oracle | ORA-02290 | Check constraint violation |
| Oracle | ORA-02291 | Parent key không tồn tại khi kiểm tra foreign key |
| Oracle | ORA-02292 | Parent key vẫn được bản ghi con tham chiếu |

Mã lỗi là dữ liệu kỹ thuật phụ thuộc sản phẩm. Cần kiểm tra đúng driver, phiên bản và exception chain trong ứng dụng thực tế. Không nên suy luận chỉ từ thông điệp tiếng Anh vì message có thể thay đổi theo phiên bản hoặc ngôn ngữ.

## 6. Ánh xạ theo constraint name thay vì dò message

Một lỗi UNIQUE có thể xảy ra trên email, username, mã đơn hàng hoặc khóa idempotency. Nếu chỉ kiểm tra SQLSTATE 23505 rồi trả EMAIL_ALREADY_REGISTERED cho mọi trường hợp, ứng dụng sẽ trả sai khi username hoặc order code bị trùng.

Vì vậy, cần kết hợp loại lỗi với constraint cụ thể:

~~~text
SQLSTATE = 23505
    |
    +-- constraint = uq_users_email
    |       -> EMAIL_ALREADY_REGISTERED
    |
    +-- constraint = uq_users_username
    |       -> USERNAME_TAKEN
    |
    +-- constraint = uq_orders_external_reference
            -> ORDER_REFERENCE_ALREADY_USED
~~~

Tương tự, FOREIGN KEY violation có thể có hai ý nghĩa khác nhau:

- Khi INSERT một order với customer_id không tồn tại, đó có thể là CUSTOMER_NOT_FOUND.
- Khi DELETE customer đang được order tham chiếu, đó có thể là CUSTOMER_HAS_ORDERS hoặc RESOURCE_IN_USE.

Chỉ biết SQLSTATE 23503 chưa đủ để chọn kết quả nghiệp vụ. Cần biết câu lệnh đang thực hiện và constraint nào bị vi phạm.

### 6.1. Không phân loại bằng cách tìm chuỗi trong message

Một cách làm mong manh là:

~~~java
if (exception.getMessage().contains("email")) {
    return EMAIL_ALREADY_REGISTERED;
}
~~~

Cách này dễ hỏng vì:

- Message thay đổi theo database hoặc phiên bản driver.
- Message có thể được dịch hoặc định dạng khác.
- Tên cột có thể xuất hiện trong nhiều loại lỗi.
- Nội dung message có thể chứa giá trị dữ liệu do người dùng nhập.
- Framework có thể bọc exception và thay đổi message ở lớp ngoài.

Nên dùng SQLSTATE/vendor code và metadata có cấu trúc như constraint name. Nếu driver không cung cấp constraint name một cách ổn định, có thể cần một lớp adapter riêng cho database đó hoặc thiết kế câu lệnh/flow để phân biệt rõ hơn.

### 6.2. Ví dụ với PostgreSQL

PostgreSQL driver JDBC cung cấp thông tin lỗi chi tiết qua PSQLException và ServerErrorMessage. Có thể lấy SQLSTATE và constraint name từ exception gốc:

~~~java
catch (PSQLException ex) {
    String sqlState = ex.getSQLState();
    ServerErrorMessage detail = ex.getServerErrorMessage();

    String constraintName =
        detail == null ? null : detail.getConstraint();

    // Dùng sqlState và constraintName để ánh xạ.
}
~~~

Ví dụ ánh xạ:

~~~java
BusinessError translatePostgresError(PSQLException ex) {
    String state = ex.getSQLState();
    ServerErrorMessage detail = ex.getServerErrorMessage();
    String constraint = detail == null ? null : detail.getConstraint();

    if ("23505".equals(state)) {
        return switch (constraint == null ? "" : constraint) {
            case "uq_users_email" ->
                BusinessError.emailAlreadyRegistered();
            case "uq_users_username" ->
                BusinessError.usernameTaken();
            case "uq_orders_external_reference" ->
                BusinessError.orderReferenceAlreadyUsed();
            default ->
                BusinessError.resourceConflict();
        };
    }

    if ("23503".equals(state)) {
        return switch (constraint == null ? "" : constraint) {
            case "fk_orders_customer" ->
                BusinessError.customerReferenceInvalid();
            default ->
                BusinessError.relatedResourceConflict();
        };
    }

    if ("23514".equals(state)) {
        return BusinessError.invalidBusinessValue();
    }

    return null;
}
~~~

Đây là ví dụ minh họa cho PostgreSQL JDBC. Ứng dụng cần giữ một danh sách constraint được quản lý cùng schema migration và không để logic dịch lỗi rải rác trong từng controller.

Không phải mọi database driver đều có API lấy constraint name giống PostgreSQL. Với MySQL, SQL Server hoặc Oracle, cần đọc vendor-specific error code và metadata theo driver tương ứng.

## 7. Ánh xạ theo thao tác nghiệp vụ và chiều của quan hệ

Cùng một loại constraint có thể biểu thị những tình huống khác nhau tùy thao tác. Cần kết hợp constraint với hành động đang thực hiện.

### 7.1. UNIQUE khi tạo mới

Khi đăng ký user, UNIQUE email bị vi phạm thường có nghĩa email đã được sử dụng:

~~~text
POST /users
    |
    +-- INSERT users
    |
    +-- uq_users_email violation
             |
             v
      EMAIL_ALREADY_REGISTERED
~~~

API có thể trả 409 Conflict nếu request xung đột với tài nguyên hiện có. Nếu email được coi là dữ liệu đầu vào không hợp lệ theo hợp đồng API, một số hệ thống có thể dùng 422. Điều quan trọng là API phải nhất quán và tài liệu hóa rõ ràng.

### 7.2. UNIQUE khi cập nhật

Khi người dùng đổi email, cùng constraint có thể tạo kết quả khác:

- Nếu email mới thuộc user khác, trả EMAIL_ALREADY_REGISTERED.
- Nếu email không đổi và bản ghi vẫn là chính user đó, UPDATE bình thường không vi phạm UNIQUE.
- Nếu request đồng thời đổi email đến cùng một địa chỉ, một request thành công và request còn lại nhận conflict.

Nếu hệ thống dùng soft delete, cần xác định email của user đã xóa có được phép tái sử dụng không. Một UNIQUE constraint trên email toàn bảng có thể tiếp tục giữ email của bản ghi soft-deleted. Nếu chỉ user đang hoạt động phải duy nhất, có thể cần partial/filtered unique index tùy database. Quy tắc này phải thống nhất giữa validation, schema và thông báo nghiệp vụ.

### 7.3. FOREIGN KEY khi tạo bản ghi con

Ví dụ tạo order cho customer:

~~~sql
INSERT INTO orders (order_id, customer_id, status)
VALUES (1001, 9999, 'PENDING');
~~~

Nếu customer_id = 9999 không tồn tại, database có thể trả FOREIGN KEY violation. Ứng dụng có thể trả CUSTOMER_NOT_FOUND.

Tuy nhiên, nếu customer vừa bị xóa bởi transaction khác, lỗi có thể phản ánh một race condition. Ứng dụng có thể đọc lại để xác nhận customer không còn tồn tại và trả cùng kết quả nghiệp vụ. Nếu quy tắc yêu cầu customer phải được giữ trong suốt quy trình, cần bảo vệ bằng transaction và lock phù hợp.

### 7.4. FOREIGN KEY khi xóa bản ghi cha

Nếu customer đang được orders tham chiếu, DELETE customer có thể bị từ chối. Đây không phải CUSTOMER_NOT_FOUND mà là RESOURCE_IN_USE hoặc CUSTOMER_HAS_ORDERS.

Ứng dụng có thể:

- Từ chối xóa và yêu cầu xử lý các đơn hàng liên quan.
- Chuyển customer sang trạng thái inactive thay vì xóa vật lý.
- Dùng ON DELETE CASCADE nếu quy tắc nghiệp vụ thật sự yêu cầu xóa dữ liệu con cùng lúc.
- Dùng ON DELETE SET NULL nếu quan hệ cho phép mất tham chiếu.

Không nên tự động chuyển mọi FOREIGN KEY violation thành NOT_FOUND. Hãy phân biệt lỗi tham chiếu đầu vào với lỗi xóa tài nguyên đang được sử dụng.

### 7.5. CHECK khi cập nhật trạng thái

Ví dụ CHECK constraint chỉ cho phép một số trạng thái:

~~~sql
CONSTRAINT ck_orders_status
CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED', 'COMPLETED'))
~~~

Nếu ứng dụng gửi trạng thái PAID nhưng schema chưa cho phép, database trả CHECK violation. Có hai khả năng:

- Request người dùng không hợp lệ theo nghiệp vụ.
- Code mới đã triển khai nhưng migration chưa cập nhật constraint, đây là lỗi triển khai hoặc không tương thích schema.

Không nên mặc định trả INVALID_STATUS cho người dùng trong mọi trường hợp. Nếu giá trị hợp lệ theo nghiệp vụ nhưng schema chưa được nâng cấp, đó là lỗi vận hành cần cảnh báo và xử lý ở phía hệ thống.

## 8. Xử lý đúng trạng thái transaction sau constraint violation

Một lỗi constraint có thể làm transaction không thể tiếp tục. Cách xử lý phụ thuộc database và transaction manager.

### 8.1. PostgreSQL đánh dấu transaction failed

Trong PostgreSQL, sau khi một statement lỗi bên trong transaction, transaction thường chuyển sang trạng thái failed. Những statement tiếp theo sẽ bị từ chối cho đến khi transaction được rollback hoặc rollback về một savepoint được tạo trước lỗi.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO users (user_id, email)
VALUES (1001, 'alice@example.com');

-- Giả sử email đã tồn tại và INSERT gây unique_violation.

SELECT COUNT(*) FROM users;
-- Transaction đang ở trạng thái failed nên câu SELECT này cũng thất bại.

ROLLBACK;
~~~

Không nên bắt exception rồi tiếp tục chạy câu SQL khác trong cùng transaction như thể không có lỗi.

Nếu cần phục hồi một phần trong PostgreSQL, có thể dùng SAVEPOINT:

~~~sql
BEGIN;

SAVEPOINT before_optional_insert;

INSERT INTO optional_settings (user_id, setting_key, setting_value)
VALUES (1001, 'theme', 'dark');

-- Nếu INSERT vi phạm constraint:
ROLLBACK TO SAVEPOINT before_optional_insert;

-- Transaction có thể tiếp tục từ savepoint.
UPDATE users
SET last_seen_at = CURRENT_TIMESTAMP
WHERE user_id = 1001;

COMMIT;
~~~

Savepoint chỉ phù hợp khi nghiệp vụ cho phép bỏ qua phần thao tác tùy chọn và tiếp tục phần còn lại. Không nên dùng savepoint để che giấu một lỗi làm cho trạng thái nghiệp vụ không còn hợp lệ.

### 8.2. Framework có thể đánh dấu rollback-only

Trong ứng dụng dùng transaction manager, exception có thể khiến transaction bị đánh dấu rollback-only. Dù code bắt exception bên trong method, lúc commit transaction vẫn có thể thất bại hoặc framework ném lỗi unexpected rollback.

Ví dụ không nên làm:

~~~java
@Transactional
public void registerUser(String email) {
    try {
        repository.save(new User(email));
        repository.flush();
    } catch (DataIntegrityViolationException ex) {
        // Sai: nuốt lỗi rồi tiếp tục như transaction vẫn hợp lệ.
    }

    auditRepository.save(new AuditRecord("REGISTER_ATTEMPT"));
}
~~~

Tùy database và framework, transaction có thể đã bị hủy hoặc đánh dấu rollback-only. Việc tiếp tục sử dụng persistence context cũng có thể dẫn đến kết quả không mong muốn.

Cách đơn giản hơn là để exception đi ra khỏi transaction boundary, sau đó chuyển thành business result ở lớp bên ngoài:

~~~java
public RegistrationResult register(String email) {
    try {
        registrationTransaction.createUser(email);
        return RegistrationResult.created();
    } catch (EmailAlreadyRegisteredException ex) {
        return RegistrationResult.emailAlreadyRegistered();
    }
}
~~~

Trong đó registrationTransaction là một bean hoặc thành phần có transaction boundary riêng. Lớp gọi bắt exception sau khi transaction đã rollback hoặc kết thúc.

Một phương án khác là kiểm tra trước để phản hồi nhanh, nhưng vẫn phải giữ khả năng bắt UNIQUE violation vì request đồng thời có thể vượt qua kiểm tra cùng lúc.

## 9. Constraint có thể được kiểm tra tại COMMIT

Không phải constraint nào cũng được kiểm tra ngay khi câu INSERT hoặc UPDATE chạy. Một số database hỗ trợ deferred constraint, nghĩa là trì hoãn kiểm tra đến cuối transaction.

PostgreSQL cho phép khai báo một số constraint là DEFERRABLE:

~~~sql
CREATE TABLE account_transfers (
    transfer_id BIGINT PRIMARY KEY,
    source_account_id BIGINT NOT NULL,
    destination_account_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_transfer_positive_amount
        CHECK (amount > 0)
);
~~~

Ví dụ trên dùng CHECK để minh họa ràng buộc giá trị; trong PostgreSQL, CHECK và NOT NULL không thể được khai báo DEFERRABLE. Các loại constraint có thể trì hoãn gồm UNIQUE, PRIMARY KEY, FOREIGN KEY và EXCLUSION khi được khai báo DEFERRABLE.

Ví dụ UNIQUE DEFERRABLE:

~~~sql
CREATE TABLE account_aliases (
    alias_id BIGINT PRIMARY KEY,
    alias_name TEXT NOT NULL,
    CONSTRAINT uq_account_alias_name
        UNIQUE (alias_name)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Với constraint được trì hoãn, hai thao tác trung gian có thể tạm thời tạo trạng thái trùng trong transaction nhưng trạng thái cuối cùng phải hợp lệ tại thời điểm kiểm tra. Nếu cuối transaction vẫn vi phạm, lỗi xuất hiện khi COMMIT.

Điều này ảnh hưởng đến vị trí bắt exception:

- Bắt lỗi ngay quanh repository.save() có thể không bắt được lỗi nếu provider chưa flush.
- Lỗi có thể xuất hiện ở flush hoặc khi transaction manager commit.
- Exception handler cần nằm ngoài transaction boundary để nhận được lỗi commit.
- Log nên ghi nhận bước cuối transaction, không giả định mọi constraint error đều xảy ra tại câu INSERT/UPDATE.

Với JPA, có thể gọi flush để yêu cầu provider gửi SQL sớm hơn, giúp phát hiện một số lỗi trước khi method hoàn tất. Tuy nhiên, deferred constraint vẫn có thể chỉ được kiểm tra tại commit.

## 10. Ánh xạ trong Java và Spring

Spring cung cấp lớp exception translation cho nhiều lỗi persistence. Ví dụ, một số lỗi integrity có thể được bọc thành DataIntegrityViolationException. Đây là abstraction hữu ích để service không phụ thuộc trực tiếp vào JDBC exception của mọi database.

Tuy nhiên, DataIntegrityViolationException là nhóm rộng. Nó có thể đại diện cho UNIQUE, FOREIGN KEY, CHECK, NOT NULL hoặc lỗi toàn vẹn khác. Muốn trả kết quả cụ thể, cần xem exception gốc và metadata database.

Một thiết kế có thể chia thành ba lớp:

~~~text
Repository / JDBC
    |
    +-- Database exception
            |
            v
Persistence error translator
    |
    +-- SQLSTATE / vendor code
    +-- Constraint name
            |
            v
Application service
    |
    +-- Business error code
            |
            v
REST exception handler
    |
    +-- HTTP status + response body
~~~

Ví dụ kiểu lỗi ứng dụng:

~~~java
public enum BusinessErrorCode {
    EMAIL_ALREADY_REGISTERED,
    USERNAME_TAKEN,
    CUSTOMER_NOT_FOUND,
    CUSTOMER_HAS_ORDERS,
    INSUFFICIENT_STOCK,
    TIME_SLOT_UNAVAILABLE,
    RESOURCE_CONFLICT,
    INVALID_BUSINESS_STATE
}
~~~

Lớp exception:

~~~java
public class BusinessException extends RuntimeException {
    private final BusinessErrorCode code;

    public BusinessException(BusinessErrorCode code) {
        super(code.name());
        this.code = code;
    }

    public BusinessErrorCode getCode() {
        return code;
    }
}
~~~

Translator có thể nhận DataIntegrityViolationException, tìm exception gốc và trả BusinessException phù hợp. Cách lấy vendor code và constraint name phải dựa trên driver thực tế; không nên giả định mọi exception đều có cùng cấu trúc.

~~~java
public BusinessException translate(DataIntegrityViolationException ex) {
    DatabaseErrorInfo info = databaseErrorInspector.inspect(ex);

    if (info.isUniqueViolation()
            && "uq_users_email".equals(info.constraintName())) {
        return new BusinessException(
            BusinessErrorCode.EMAIL_ALREADY_REGISTERED
        );
    }

    if (info.isForeignKeyViolation()
            && "fk_orders_customer".equals(info.constraintName())) {
        return new BusinessException(
            BusinessErrorCode.CUSTOMER_NOT_FOUND
        );
    }

    return new BusinessException(
        BusinessErrorCode.RESOURCE_CONFLICT
    );
}
~~~

DatabaseErrorInspector là adapter do ứng dụng triển khai theo driver, không phải API chuẩn có sẵn trong Spring. Nó có trách nhiệm đọc SQLSTATE, vendor code và constraint name từ exception chain.

### 10.1. Đặt exception handler ở ranh giới HTTP

Với Spring MVC, có thể dùng @RestControllerAdvice để chuyển business exception thành response:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiError> handleBusinessException(
            BusinessException ex) {

        ApiError body = new ApiError(
            ex.getCode().name(),
            messageFor(ex.getCode())
        );

        return ResponseEntity
            .status(httpStatusFor(ex.getCode()))
            .body(body);
    }
}
~~~

Các hàm messageFor và httpStatusFor là logic của ứng dụng. Ví dụ:

| Business code | HTTP status thường dùng | Ý nghĩa |
|---|---:|---|
| EMAIL_ALREADY_REGISTERED | 409 | Tài nguyên xung đột với trạng thái hiện có |
| CUSTOMER_NOT_FOUND | 404 | Tài nguyên tham chiếu không tồn tại |
| CUSTOMER_HAS_ORDERS | 409 | Không thể xóa vì còn quan hệ nghiệp vụ |
| INSUFFICIENT_STOCK | 409 hoặc 422 theo API contract | Yêu cầu không thể thực hiện với trạng thái tồn kho hiện tại |
| INVALID_QUANTITY | 400 hoặc 422 | Giá trị đầu vào không hợp lệ |
| RESOURCE_CONFLICT | 409 | Xung đột chung không được phân loại cụ thể |

HTTP status cần tuân theo API contract. Không có một ánh xạ duy nhất đúng cho mọi sản phẩm. Điều quan trọng là response nhất quán, có mã lỗi ổn định và không tiết lộ chi tiết nội bộ.

## 11. Khi nào nên kiểm tra trước và khi nào để database bắt lỗi?

Validation trước khi ghi và constraint database có vai trò bổ sung cho nhau.

| Cách kiểm tra | Mục đích | Giới hạn |
|---|---|---|
| Validation request | Bắt thiếu trường, định dạng sai, giá trị không hợp lệ trước khi gọi database | Không bảo vệ được cạnh tranh đồng thời |
| SELECT kiểm tra trước | Cho thông báo nhanh, kiểm tra tài nguyên hiện có | Có race condition giữa SELECT và INSERT/UPDATE |
| Constraint database | Bảo vệ tính toàn vẹn tại thời điểm ghi | Cần dịch lỗi kỹ thuật thành kết quả nghiệp vụ |
| UPDATE có điều kiện | Kiểm tra điều kiện và thay đổi trong một thao tác nguyên tử | Cần phân biệt affected rows = 0 theo ngữ cảnh |
| Locking/isolation | Bảo vệ quy tắc phụ thuộc nhiều thao tác hoặc nhiều dòng | Có thể gây chờ, deadlock hoặc serialization failure |

Ví dụ với email:

~~~text
Request
  |
  v
Validate format
  |
  v
Optional SELECT email exists?
  |
  +-- Có --> EMAIL_ALREADY_REGISTERED
  |
  +-- Không
       |
       v
     INSERT
       |
       +-- Success --> Created
       |
       +-- UNIQUE violation --> EMAIL_ALREADY_REGISTERED
~~~

SELECT trước giúp phản hồi nhanh trong trường hợp email đã tồn tại. UNIQUE constraint xử lý trường hợp một request khác đăng ký cùng email ngay sau lần kiểm tra.

Với tồn kho, thay vì SELECT rồi UPDATE không điều kiện, nên dùng UPDATE có điều kiện và kiểm tra số dòng:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :requested
WHERE product_id = :productId
  AND available_quantity >= :requested;
~~~

Nếu affected rows bằng 0, ứng dụng có thể đọc lại để phân biệt sản phẩm không tồn tại với số lượng không đủ. Nếu chỉ cần trả “không thể giữ số lượng này”, không nhất thiết phải thực hiện thêm truy vấn.

## 12. Phân biệt constraint violation với lỗi concurrency

Một số lỗi concurrency có thể xuất hiện trong cùng quy trình nghiệp vụ, nhưng không nên ánh xạ tất cả thành constraint violation.

| Lỗi kỹ thuật | Ý nghĩa | Hướng xử lý |
|---|---|---|
| UNIQUE violation | Giá trị trùng với một bản ghi hiện có | Trả kết quả trùng hoặc xử lý idempotent |
| CHECK violation | Giá trị không thỏa điều kiện | Từ chối giá trị hoặc điều tra lỗi bất biến |
| FOREIGN KEY violation | Tham chiếu không hợp lệ hoặc bản ghi đang được tham chiếu | Phân biệt not-found với resource-in-use |
| Serialization failure | Lịch thực thi không đáp ứng isolation guarantee | Retry toàn bộ transaction |
| Deadlock victim | Transaction bị chọn làm nạn nhân trong chu trình chờ | Retry có giới hạn và điều tra thứ tự lock |
| Lock timeout | Chờ lock vượt thời gian cho phép | Xác định blocker, cân nhắc retry hoặc báo đang bận |
| Optimistic locking conflict | Version đã thay đổi kể từ lần đọc | Đọc lại, hợp nhất hoặc trả conflict |
| Connection/timeout error | Không xác định chắc thao tác đã commit hay chưa | Kiểm tra kết quả và dùng idempotency khi retry |

Ví dụ, nếu database trả SQLSTATE 40001, không nên trả EMAIL_ALREADY_REGISTERED chỉ vì transaction đang chạy luồng đăng ký. Đây là lỗi serialization; transaction cần được retry. Sau khi retry, nếu email thực sự đã tồn tại, lần thực thi mới có thể nhận UNIQUE violation và trả EMAIL_ALREADY_REGISTERED.

Tương tự, deadlock không phải lỗi nhập liệu. Không nên yêu cầu người dùng đổi email hoặc sửa biểu mẫu khi database chỉ hủy transaction vì tranh chấp khóa.

## 13. Idempotency và request lặp

Một duplicate key đôi khi là dấu hiệu request đã được xử lý trước đó. Ví dụ client gửi POST tạo đơn hàng, server đã commit nhưng response bị mất. Client retry cùng yêu cầu và gặp UNIQUE violation trên external_request_id.

Nếu API hỗ trợ idempotency, ứng dụng nên tra cứu kết quả theo idempotency key và trả lại kết quả của lần xử lý đầu tiên, thay vì luôn báo lỗi trùng.

~~~text
Request đầu
    |
    +-- Idempotency-Key = req-abc
    |
    +-- Tạo order 1001
    |
    +-- COMMIT
    |
    +-- Response bị mất


Request retry với cùng key
    |
    +-- Idempotency-Key = req-abc
    |
    +-- Tìm thấy request đã xử lý
    |
    +-- Trả lại kết quả order 1001
~~~

Cần phân biệt:

- Cùng idempotency key và cùng nội dung request: thường trả lại kết quả đã lưu.
- Cùng key nhưng payload khác: từ chối vì key được tái sử dụng sai mục đích.
- Key mới nhưng email hoặc business key đã tồn tại: có thể là xung đột nghiệp vụ thật.

Không nên bắt mọi UNIQUE violation rồi trả success. Chỉ trả lại kết quả cũ khi xác định được đúng request đã xử lý và dữ liệu response có thể được khôi phục theo hợp đồng idempotency.

## 14. Ghi log và quan sát mà không làm lộ chi tiết nội bộ

Khi constraint bị vi phạm, ứng dụng cần đủ thông tin để điều tra và theo dõi tần suất. Nhưng response công khai không nên chứa message database hoặc dữ liệu nhạy cảm.

Log nội bộ có thể ghi:

- Business operation và tên use case.
- Business error code sau khi ánh xạ.
- SQLSTATE hoặc vendor error code.
- Constraint name nếu driver cung cấp.
- Database product/version nếu cần điều tra tương thích.
- Transaction attempt, isolation level và correlation ID.
- Resource ID đã được che hoặc mã hóa theo chính sách dữ liệu.

Ví dụ log có cấu trúc:

~~~json
{
  "event": "database_constraint_rejected",
  "operation": "register_user",
  "businessCode": "EMAIL_ALREADY_REGISTERED",
  "sqlState": "23505",
  "constraint": "uq_users_email",
  "correlationId": "req-7f91",
  "transactionAttempt": 1
}
~~~

Không nên ghi raw SQL parameter hoặc toàn bộ exception message nếu nó chứa email, số tài khoản, token hay dữ liệu cá nhân. Cần giới hạn quyền truy cập log và thời gian lưu theo chính sách vận hành.

Response cho client chỉ cần thông tin đã được thiết kế:

~~~json
{
  "code": "EMAIL_ALREADY_REGISTERED",
  "message": "Email này đã được sử dụng.",
  "field": "email",
  "correlationId": "req-7f91"
}
~~~

Correlation ID cho phép bộ phận hỗ trợ tìm log nội bộ mà không phải gửi thông tin database cho người dùng.

Cũng nên theo dõi metric theo nhóm lỗi:

- Số lần UNIQUE violation theo constraint.
- Số lần CHECK hoặc FOREIGN KEY violation.
- Tỷ lệ lỗi trên tổng số request.
- Số lần serialization retry và số lần retry hết giới hạn.
- Số lỗi constraint bất ngờ sau deployment hoặc migration.

Nếu một CHECK constraint bắt đầu thất bại hàng loạt sau khi phát hành phiên bản mới, có thể code và schema đang không tương thích. Không nên xem mọi constraint violation là lỗi người dùng.

## 15. Kiểm thử việc ánh xạ lỗi

Kiểm thử chỉ mock repository ném một exception chung có thể xác nhận service trả đúng mã lỗi, nhưng không chứng minh database thật sự trả đúng SQLSTATE và constraint name mà translator mong đợi.

Nên có các lớp kiểm thử phù hợp:

### 15.1. Unit test cho translator

Dùng các exception hoặc database error info đã dựng để kiểm tra:

- SQLSTATE 23505 cùng uq_users_email ánh xạ EMAIL_ALREADY_REGISTERED.
- SQLSTATE 23505 cùng uq_users_username ánh xạ USERNAME_TAKEN.
- SQLSTATE 23503 với FK khi INSERT được phân loại khác FK khi DELETE nếu ứng dụng cần phân biệt.
- Mã lỗi không nhận diện được chuyển thành lỗi conflict chung hoặc lỗi persistence nội bộ.
- Serialization failure không bị ánh xạ thành constraint violation.

Unit test giúp bảo vệ quy tắc ánh xạ khỏi thay đổi vô ý.

### 15.2. Integration test với database thật hoặc container tương thích

Kiểm tra các trường hợp:

1. Tạo user với email mới thì thành công.
2. Tạo user với email đã tồn tại thì database trả unique violation và API trả EMAIL_ALREADY_REGISTERED.
3. Tạo order với customer không tồn tại thì trả CUSTOMER_NOT_FOUND.
4. Xóa customer đang được order tham chiếu thì trả CUSTOMER_HAS_ORDERS nếu schema dùng RESTRICT/NO ACTION.
5. Ghi số lượng âm thì CHECK violation được ánh xạ đúng.
6. Hai request đồng thời đăng ký cùng email: chỉ một request tạo bản ghi, request còn lại nhận kết quả trùng.
7. Constraint deferred chỉ thất bại tại COMMIT vẫn được exception handler chuyển đúng.

Các test cạnh tranh cần chạy với hai connection/transaction riêng và điều phối thời điểm thực thi. Một test tuần tự không tái hiện được race condition.

### 15.3. Kiểm tra transaction boundary

Đặc biệt cần kiểm tra exception xuất hiện ở đâu:

- Ngay khi execute INSERT/UPDATE.
- Khi ORM flush.
- Khi commit transaction.
- Khi transaction manager hoàn tất method.

Test nên xác nhận rằng lỗi được bắt ở đúng lớp và transaction đã rollback. Không nên chỉ kiểm tra body response mà bỏ qua trạng thái database sau lỗi.

## 16. Quy tắc thiết kế để tránh ánh xạ sai

Một lớp chuyển đổi lỗi đáng tin cậy nên tuân theo các nguyên tắc:

1. Dùng mã lỗi database có cấu trúc, không dò chuỗi message.
2. Kết hợp SQLSTATE/vendor code với constraint name và loại thao tác.
3. Đặt tên constraint rõ ràng và quản lý tên cùng migration.
4. Dùng mã nghiệp vụ ổn định, không để API phụ thuộc tên constraint hoặc SQLSTATE.
5. Chỉ công khai thông tin cần cho client; giữ chi tiết database trong log nội bộ.
6. Phân biệt lỗi người dùng, xung đột tài nguyên, lỗi concurrency và lỗi vận hành.
7. Bắt lỗi ở ngoài transaction boundary khi cần để transaction kết thúc đúng cách.
8. Nhớ rằng lỗi có thể xuất hiện ở flush hoặc COMMIT, không chỉ tại repository.save().
9. Không retry constraint violation với cùng dữ liệu.
10. Không coi duplicate key luôn là lỗi; kiểm tra idempotency và request identity trước khi quyết định.
11. Kiểm thử cả trường hợp cạnh tranh đồng thời và deferred constraint.
12. Theo dõi tần suất lỗi để phát hiện code/schema mismatch sau deployment.

Một số lỗi constraint là kết quả bình thường của cạnh tranh, chẳng hạn hai người cùng đăng ký một email. Một số lỗi khác có thể chỉ ra bug, chẳng hạn ứng dụng liên tục ghi số lượng âm dù đã có validation. Chính sách cần phân biệt những trường hợp này để log, metric và phản hồi phù hợp.

## Kết luận

Chuyển lỗi ràng buộc thành kết quả nghiệp vụ rõ ràng là trách nhiệm của lớp ứng dụng nằm giữa database và API. Database bảo vệ tính toàn vẹn bằng constraint; ứng dụng đọc SQLSTATE hoặc vendor error code cùng constraint name, kết hợp thao tác đang thực hiện để tạo mã lỗi nghiệp vụ ổn định như EMAIL_ALREADY_REGISTERED, CUSTOMER_NOT_FOUND hoặc RESOURCE_IN_USE.

Validation trước khi ghi giúp phản hồi sớm, nhưng constraint vẫn cần thiết để xử lý cạnh tranh đồng thời. Khi lỗi xuất hiện, ứng dụng phải để transaction rollback đúng cách, bắt lỗi ở ranh giới phù hợp và không retry nguyên trạng một dữ liệu vẫn vi phạm quy tắc. Các lỗi concurrency như serialization failure, deadlock hoặc lock timeout cần chính sách riêng; chúng không phải lỗi constraint chỉ vì xảy ra trong cùng một use case.

Một thiết kế tốt giữ chi tiết database trong log có kiểm soát, trả response dễ hiểu cho client, kiểm thử cả đường lỗi tại COMMIT và các request cạnh tranh, đồng thời duy trì hợp đồng mã lỗi ổn định khi schema hoặc database engine thay đổi.
