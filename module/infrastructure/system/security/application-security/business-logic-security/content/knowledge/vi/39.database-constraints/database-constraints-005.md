# Constraint error translation

## 1. Vì sao lỗi constraint cần được dịch sang ngôn ngữ nghiệp vụ?

Database constraint là lớp bảo vệ cuối cho nhiều bất biến nghiệp vụ: không tạo trùng một ý định hoàn tiền, không tham chiếu đơn hàng của tenant khác, không lưu số tiền âm hoặc không vượt giới hạn dữ liệu đã định nghĩa.

Khi constraint chặn một thao tác, ứng dụng nhận lỗi kỹ thuật từ driver hoặc framework. Nếu trả nguyên lỗi đó cho client, hệ thống có thể làm lộ tên bảng, tên cột, câu SQL, giá trị khóa hoặc sự tồn tại của dữ liệu mà người gọi không có quyền biết. Nếu gom mọi lỗi thành một thông báo chung không có phân loại, client lại không biết cần sửa request, đọc kết quả cũ hay chờ và thử lại.

**Constraint error translation** là việc diễn giải một lỗi ràng buộc đã nhận diện trong ngữ cảnh thao tác, rồi chuyển nó thành kết quả nghiệp vụ hoặc lỗi hệ thống phù hợp. Việc dịch lỗi không làm constraint biến mất và không thay thế yêu cầu rollback.

Trong bảo mật logic nghiệp vụ, lớp dịch lỗi cần giữ các mục tiêu:

- Không biến một yêu cầu bị database từ chối thành thành công giả.
- Không để retry vượt ràng buộc hoặc tạo thêm tác dụng.
- Không tiết lộ dữ liệu chéo tenant hay ngoài quyền theo đối tượng.
- Không che lỗi lập trình bằng cách đổ mọi lỗi toàn vẹn cho người dùng.
- Giữ mã lỗi công khai ổn định khi cấu trúc database thay đổi.

## 2. Phân biệt ba loại kết quả

Một lỗi database không tự xác định được người dùng có sai hay không. Cần phân biệt:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Từ chối nghiệp vụ đã dự kiến | Hai request đồng thời xác nhận cùng một ý định chỉ được thực hiện một lần | Trả xung đột hoặc xử lý idempotency theo bằng chứng |
| Lỗi toàn vẹn ngoài dự kiến | Server quên gán `tenant_id`, hoặc ghi trạng thái nội bộ không hợp lệ | Hủy thao tác, báo lỗi hệ thống an toàn và điều tra |
| Lỗi không thuộc constraint | Deadlock, mất kết nối, timeout hoặc chưa rõ kết quả commit | Áp dụng chính sách transaction và phục hồi tương ứng |

Ví dụ một lỗi `NOT NULL` trên trường `amount_minor` có thể do client thiếu dữ liệu nếu hợp đồng đầu vào cho phép đi đến đó, nhưng cũng có thể do lỗi mapping của server. Một lỗi cùng loại trên `created_by_actor_id` do server phải tự gán thường là lỗi nội bộ.

Không ánh xạ toàn bộ nhóm “integrity violation” thành HTTP 400. Phân loại sai có thể làm hệ thống bỏ qua cảnh báo về dữ liệu hỏng hoặc khiến client liên tục gửi lại một lệnh không thể thành công.

## 3. Nguồn thông tin để nhận diện lỗi

Ưu tiên metadata có cấu trúc từ driver hoặc framework:

```text
database/dialect đã cấu hình
SQLSTATE hoặc mã lỗi của hệ quản trị
tên constraint được driver cung cấp
tên bảng/cột nếu có và phù hợp để dùng nội bộ
ngữ cảnh thao tác do server xác định
giai đoạn lỗi: statement, flush hoặc commit
```

Không nhận tên thao tác, tên constraint hoặc loại database từ request client để quyết định cách dịch. Các giá trị này phải đến từ đường thực thi và cấu hình đáng tin cậy.

### 3.1. Ví dụ SQLSTATE trong PostgreSQL

| SQLSTATE | Ý nghĩa | Có đủ để suy ra lỗi nghiệp vụ không? |
|---|---|---|
| `23505` | Vi phạm tính duy nhất | Chưa; cần biết định danh nào trùng và ở thao tác nào |
| `23503` | Vi phạm khóa ngoại | Chưa; có thể là tham chiếu không hợp lệ, cuộc đua hoặc lỗi nội bộ |
| `23502` | Vi phạm `NOT NULL` | Chưa; cần xác định trường nào và ai chịu trách nhiệm cấp giá trị |
| `23514` | Vi phạm `CHECK` | Chưa; cần biết bất biến cụ thể và ngữ cảnh thay đổi |
| `23P01` | Vi phạm exclusion constraint | Chưa; có thể là xung đột khoảng thời gian hoặc một quy tắc khác |
| `40001` | Serialization failure | Không phải lỗi constraint; xem chính sách retry transaction |
| `40P01` | Deadlock detected | Không phải lỗi constraint; cần xử lý transaction bị hủy và đồng thời |

Các mã trên là ví dụ cho PostgreSQL. Hệ quản trị khác có thể dùng mã vendor, cấu trúc exception hoặc chi tiết khác. Không áp dụng bảng này cho mọi driver mà không có adapter phù hợp.

Nhóm SQLSTATE giúp phân loại rộng nhưng không thay thế danh mục constraint cụ thể. Một vi phạm unique trên khóa idempotency và một vi phạm unique trên định danh người dùng có hành vi công khai khác nhau.

### 3.2. Không phân tích chuỗi thông báo như hợp đồng chính

Mẫu dễ hỏng:

```java
if (exception.getMessage().contains("duplicate key")) {
    return conflict("Already exists");
}
```

Thông báo có thể thay đổi theo phiên bản, ngôn ngữ, lớp bọc hoặc chứa giá trị dữ liệu. Việc tìm chuỗi cũng có thể nhầm lỗi ở một bước khác với lỗi mà handler dự kiến.

Nếu không lấy được metadata đáng tin cậy, dùng nhánh lỗi hệ thống an toàn và ghi nhận để điều tra, thay vì đoán kết quả nghiệp vụ từ một đoạn message.

## 4. Đặt tên constraint theo hợp đồng nội bộ rõ ràng

Tên constraint có chủ đích giúp ứng dụng nhận diện bất biến ổn định hơn so với tên tự sinh không được quản lý.

Ví dụ schema PostgreSQL rút gọn:

```sql
CREATE TABLE orders (
    tenant_id       UUID   NOT NULL,
    order_id        UUID   NOT NULL,
    paid_minor      BIGINT NOT NULL,
    refunded_minor  BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT pk_orders
        PRIMARY KEY (tenant_id, order_id),

    CONSTRAINT ck_orders_paid_nonnegative
        CHECK (paid_minor >= 0),

    CONSTRAINT ck_orders_refunded_within_paid
        CHECK (refunded_minor >= 0 AND refunded_minor <= paid_minor)
);

CREATE TABLE refunds (
    refund_id         UUID   NOT NULL,
    tenant_id         UUID   NOT NULL,
    order_id          UUID   NOT NULL,
    refund_intent_id  UUID   NOT NULL,
    amount_minor      BIGINT NOT NULL,

    CONSTRAINT pk_refunds
        PRIMARY KEY (refund_id),

    CONSTRAINT uq_refunds_tenant_intent
        UNIQUE (tenant_id, refund_intent_id),

    CONSTRAINT fk_refunds_tenant_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, order_id),

    CONSTRAINT ck_refunds_amount_positive
        CHECK (amount_minor > 0)
);
```

Đây là ví dụ phục vụ nhận diện lỗi, chưa phải mô hình hoàn tiền đầy đủ. Bảng còn cần những dữ liệu và quy tắc phù hợp như loại tiền, phê duyệt, trạng thái ý định, liên kết giao dịch và kiểm soát tổng tiền hoàn.

Khóa ngoại tổng hợp ràng buộc đơn hàng thuộc đúng tenant ghi trên bản ghi refund. Nó không tự chứng minh người gọi có quyền trên đơn đó; `tenant_id` vẫn phải đến từ ngữ cảnh đáng tin cậy và quyền theo đối tượng phải được kiểm tra.

Ràng buộc trên `refunded_minor` kiểm soát giá trị của dòng orders, không tự chứng minh nó bằng tổng các refund ở bảng khác. Muốn bảo vệ quan hệ tổng đó cần thiết kế transaction, cập nhật và đối soát tương ứng.

`CHECK` trong SQL thường không từ chối một biểu thức chỉ cho kết quả unknown do `NULL`. Vì vậy, các trường bắt buộc trong ví dụ có `NOT NULL` riêng, không dựa vào điều kiện `> 0` để thay thế.

## 5. Ánh xạ theo constraint và ngữ cảnh thao tác

Một danh mục dịch lỗi nên kết hợp ít nhất tên constraint, loại lỗi và thao tác server đang thực hiện.

| Constraint hoặc nhóm | Ngữ cảnh đã xác nhận | Ý nghĩa có thể công khai |
|---|---|---|
| `uq_refunds_tenant_intent` | Tạo refund cho một ý định mà người gọi được phép thao tác | Ý định đã có kết quả hoặc đang xung đột; cần kiểm tra luồng idempotency |
| `fk_refunds_tenant_order` | Đơn hàng không còn khả dụng trong phạm vi thao tác hợp lệ | Đối tượng không khả dụng hoặc trạng thái đã thay đổi, theo chính sách tiết lộ |
| `ck_orders_refunded_within_paid` | Một phép tăng tổng tiền đã được xác định là nhánh kiểm tra giới hạn | Xung đột giới hạn hoàn tiền, nếu nguyên nhân đúng với quy tắc dự kiến |
| `ck_refunds_amount_positive` | Server đã chuẩn hóa số tiền nhưng vẫn ghi số không hợp lệ | Có thể là lỗi triển khai cần điều tra, không mặc định lỗi client |
| Constraint không có trong danh mục | Bất kỳ | Lỗi hệ thống an toàn; không đoán và không lộ cấu trúc database |

Tên constraint không tự cung cấp đầy đủ nguyên nhân. Ví dụ `ck_orders_refunded_within_paid` có thể bị vi phạm vì tăng quá giới hạn, nhưng cũng có thể vì một đường code ghi số âm hoặc giảm `paid_minor` sai. Chỉ dịch thành lỗi giới hạn khi ngữ cảnh đủ để chứng minh đó là nhánh hợp lệ đã dự kiến.

Không suy ra quyền xem một đối tượng từ việc lỗi khóa ngoại nhắc đến nó. Handler chỉ được dùng thông tin trong phạm vi mà người gọi đã được phép nhận.

### 5.1. Kiểm tra trước không loại bỏ lỗi đồng thời

Ứng dụng có thể kiểm tra “chưa có refund cho ý định này”, nhưng request khác có thể ghi trước khi transaction hiện tại insert. Constraint vẫn cần thiết để quyết định cuối.

Kiểm tra đầu vào sớm giúp trả lỗi rõ và giảm chi phí. Dịch lỗi constraint xử lý lớp bảo vệ còn lại, đặc biệt là cuộc đua và các đường ghi khác. Hai lớp bổ trợ nhau, không thay thế nhau.

## 6. Hợp đồng lỗi công khai ổn định

Một lỗi nghiệp vụ có thể có mã ổn định và thông điệp an toàn:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "REFUND_INTENT_CONFLICT",
  "message": "Không thể thực hiện yêu cầu ở trạng thái hiện tại.",
  "request_id": "request-73"
}
```

Response không chứa SQLSTATE, tên bảng, tên constraint, câu SQL, giá trị khóa gây trùng hoặc stack trace. `request_id` hỗ trợ đối chiếu nội bộ nhưng không được trở thành khóa cho phép người ngoài đọc log.

Mã lỗi công khai nên thể hiện ý nghĩa nghiệp vụ, ví dụ `REFUND_LIMIT_EXCEEDED` hoặc `RESOURCE_NOT_AVAILABLE`, không gắn trực tiếp với tên `ck_...` hoặc tên lớp exception.

### 6.1. Chọn HTTP status theo nghĩa nghiệp vụ

| Kết quả đã phân loại | Hướng ánh xạ có thể dùng |
|---|---|
| Request sai định dạng | `400 Bad Request` |
| Nội dung không đáp ứng quy tắc đầu vào/nghiệp vụ theo hợp đồng API | `422 Unprocessable Content` hoặc mã đã thống nhất |
| Xung đột với trạng thái hiện tại hoặc định danh đã được dùng | `409 Conflict` |
| Đối tượng không khả dụng theo chính sách không tiết lộ | `404 Not Found` hoặc cách biểu diễn đã thống nhất |
| Lỗi toàn vẹn ngoài dự kiến | `500 Internal Server Error` với nội dung an toàn |
| Hạ tầng tạm thời không khả dụng | Mã tạm thời phù hợp, chẳng hạn `503`, cùng chính sách retry riêng |

Đây là lựa chọn thiết kế, không phải phép ánh xạ một-một từ SQLSTATE sang HTTP. Một vi phạm unique ở luồng đăng ký công khai có thể cần phản hồi tránh xác nhận tài khoản đã tồn tại, thay vì trả thông báo chi tiết như màn hình quản trị có quyền.

Chỉ khai báo khả năng retry khi biết client nên thử lại hành động nào. Với xung đột do ý định đã thực hiện, gửi key mới để “thử lại” có thể tạo rủi ro nghiệp vụ chứ không phải cách phục hồi.

## 7. Ranh giới transaction phải kết thúc đúng trước khi phục hồi

Một lỗi constraint có thể xảy ra ở câu SQL, khi ORM flush hoặc khi commit đối với ràng buộc được kiểm tra muộn. Không chỉ bao try/catch quanh `repository.save()` rồi cho rằng đã bắt mọi lỗi.

Trong PostgreSQL, sau nhiều loại lỗi statement, transaction chuyển sang trạng thái lỗi. Cần rollback toàn bộ hoặc rollback về savepoint hợp lệ đã tạo trước lỗi để tiếp tục theo ngữ nghĩa được hỗ trợ.

Mẫu nguy hiểm:

```text
BEGIN
  INSERT refund → unique violation
  bắt exception
  SELECT refund cũ trong chính transaction đang lỗi
  trả thành công
```

Việc đọc tiếp có thể thất bại; ngay cả khi một lớp khác cho phép quan sát dữ liệu, transaction chung có thể đã rollback-only. Không coi bắt exception là khôi phục được transaction.

Thiết kế an toàn thường là:

1. Để transaction manager hoặc mã JDBC kết thúc transaction thất bại đúng cách.
2. Phân loại lỗi bằng metadata và ngữ cảnh được giữ lại.
3. Nếu cần phục hồi bằng cách đọc kết quả cũ, dùng transaction/ngữ cảnh mới phù hợp.
4. Kiểm tra quyền và so khớp đầy đủ trước khi trả kết quả.

Khi database xác nhận lỗi constraint khiến transaction không commit được, đó là bằng chứng khác với mất kết nối lúc commit. Không gộp một lỗi mạng chưa rõ kết quả vào nhánh “constraint đã từ chối”.

## 8. Kiến trúc lớp dịch lỗi trong Java

Một cách tổ chức là tách ba trách nhiệm:

```text
Driver/framework exception
    → adapter trích xuất metadata kỹ thuật
    → classifier theo thao tác và danh mục bất biến
    → handler trả lỗi nghiệp vụ, phục hồi có điều kiện hoặc lỗi hệ thống
```

Adapter phụ thuộc driver/framework. Classifier dùng mã nghiệp vụ và ngữ cảnh tin cậy. Tầng HTTP chỉ nhận kết quả đã được phân loại, không tự tìm chữ “duplicate” trong message.

Mã giả Java:

```java
record DbFailure(
    String sqlState,
    String constraintName,
    String schemaName,
    String tableName,
    String columnName
) {}

Translation classify(DbFailure failure, TrustedWriteContext context) {
    if (!context.matchesExpectedRelation(
            failure.schemaName(), failure.tableName())) {
        return Translation.unexpectedIntegrityFailure();
    }

    if ("23505".equals(failure.sqlState())
            && "uq_refunds_tenant_intent".equals(failure.constraintName())
            && context.operation() == Operation.CREATE_REFUND) {
        return Translation.requireExistingIntentResolution();
    }

    if ("23514".equals(failure.sqlState())
            && "ck_orders_refunded_within_paid".equals(failure.constraintName())
            && context.isKnownPositiveRefundIncrement()) {
        return Translation.domainConflict("REFUND_LIMIT_EXCEEDED");
    }

    return Translation.unexpectedIntegrityFailure();
}
```

Đây là mã giả cho adapter PostgreSQL và hai nhánh đã biết. `isKnownPositiveRefundIncrement` phải phản ánh đường ghi được kiểm soát thật, không phải cờ client gửi hoặc một phép đoán từ exception.

`requireExistingIntentResolution` chưa phải thành công và cũng chưa trả tài nguyên cũ. Nó yêu cầu một bước phục hồi có quyền, sau khi transaction lỗi đã kết thúc.

### 8.1. Exception có thể bị bọc nhiều lớp

JDBC, ORM và Spring có thể bọc lỗi gốc trong những exception khác nhau. Một exception tổng quát về tính toàn vẹn không đủ để phân biệt unique, foreign key hoặc check.

Adapter cần xử lý chuỗi cause và các thông tin bổ sung mà driver hỗ trợ, có giới hạn và tránh vòng lặp. Với batch, cũng cần biết lỗi có thể liên quan đến statement nào; không gán lỗi của một dòng cho tất cả các dòng còn lại khi chưa có bằng chứng.

Metadata không phải lúc nào cũng có tên constraint. Ví dụ lỗi bắt buộc không null có thể được nhận diện bằng bảng/cột thay vì một tên ràng buộc riêng. Chỉ dùng những trường đó qua danh mục nội bộ cho phép; không trả tên cột kỹ thuật ra API một cách tự động.

Nếu adapter không nhận diện được lỗi, quay về nhánh an toàn và quan sát được. Không lặng lẽ mặc định một vi phạm không biết tên thành một lỗi nghiệp vụ thường gặp.

## 9. Unique violation không tự đồng nghĩa với idempotency thành công

Giả sử hai request tạo refund cho cùng `refund_intent_id`. Một request thành công, request còn lại gặp `uq_refunds_tenant_intent`.

Để trả kết quả cũ như một lần phát lại hợp lệ, cần kiểm tra:

- Cùng tenant và đúng phạm vi ý định.
- Người gọi hiện tại được quyền nhận kết quả.
- Nội dung có ý nghĩa khớp: đối tượng, số tiền, loại tiền, phiên bản và những điều kiện được hợp đồng quy định.
- Bản ghi đã có thực sự đại diện cho kết quả phù hợp, không phải một trạng thái chưa xác định hoặc từ chối khác.
- Không có việc bỏ qua phê duyệt bằng cách mượn kết quả của một request khác.

Cùng một idempotency key nhưng khác fingerprint phải bị từ chối theo hợp đồng. Không dùng lỗi unique làm lý do trả thành công cho payload mới.

Với mô hình nhận quyền idempotency, `INSERT ... ON CONFLICT DO NOTHING` có thể giúp tránh ném lỗi ở nhánh xung đột dự kiến. Nhưng vẫn cần đọc đúng bản ghi, so fingerprint và xử lý trạng thái. Không đọc thấy một dòng sau xung đột cũng không tự cấp quyền thực thi.

Các khóa unique chỉ đúng trong phạm vi đã thiết kế. Nếu key chỉ unique trong một tenant, truy vấn phục hồi thiếu tenant có thể đọc nhầm dữ liệu. Nếu hai người dùng dùng hai key khác nhau cho cùng một ý định, ràng buộc nghiệp vụ vẫn phải ngăn tác dụng lặp khi cần.

## 10. Foreign key violation: không biến database thành công cụ dò dữ liệu

Một lỗi khóa ngoại có thể xảy ra vì đối tượng không tồn tại, đã bị xóa đồng thời, thuộc tenant khác hoặc do server truyền sai định danh. Những trường hợp này không có cùng nguyên nhân và không nên lộ toàn bộ khác biệt cho mọi người gọi.

Ví dụ `fk_refunds_tenant_order` từ chối bộ `(tenant_id, order_id)` không khớp. Handler không được tiếp tục tra cứu đơn hàng trên mọi tenant rồi trả “đơn này thuộc tenant B”. Phản hồi phải theo chính sách không tiết lộ và phạm vi người gọi được phép biết.

Nếu người gọi có quyền hợp lệ và đối tượng vừa bị xóa trong một cuộc đua, API có thể trả đối tượng không khả dụng hoặc xung đột theo hợp đồng. Nếu tham chiếu phải luôn được server tạo đúng mà vẫn lỗi, cần xem đây là lỗi nội bộ thay vì yêu cầu client sửa một định danh họ không kiểm soát.

### 10.1. Quan hệ phụ thuộc bất đồng bộ

Consumer có thể nhận một sự kiện phụ thuộc trước khi bản ghi liên quan xuất hiện ở nguồn nội bộ. Khi đó một lỗi khóa ngoại có thể cần cơ chế chờ hoặc xử lý lại có giới hạn.

Chính sách này phải xác định loại quan hệ và nguồn sự kiện được phép. Không retry vô hạn mọi lỗi khóa ngoại: một tham chiếu sai tenant hoặc không bao giờ được tạo sẽ làm hàng đợi bị nghẽn và không trở nên hợp lệ sau nhiều lần thử.

Không tắt constraint hoặc tạo bản ghi cha giả để “cho chạy qua”. Việc đó có thể phá quyền sở hữu, state machine và khả năng đối soát.

## 11. CHECK và NOT NULL: bảo vệ dữ liệu, không đổ lỗi tùy tiện

Validation đầu vào nên từ chối sớm dữ liệu sai như số tiền không dương hoặc loại tiền không được hỗ trợ. Constraint bảo vệ database trước cuộc đua, lỗi code và những đường ghi khác.

Khi constraint vẫn báo lỗi, cần biết nguồn giá trị:

| Trường hợp | Cách diễn giải |
|---|---|
| Client gửi giá trị sai đã được xác định rõ bởi hợp đồng | Có thể trả lỗi validation phù hợp, không lộ tên cột kỹ thuật |
| Server tự tính một giá trị trái bất biến | Lỗi hệ thống hoặc lỗi đồng thời cần phân tích, không mặc định lỗi client |
| Cập nhật tổng bị từ chối do giới hạn đã thay đổi | Có thể trả xung đột nếu đó là nhánh nghiệp vụ được dự kiến |
| Trường server bắt buộc gán bị null | Thường là lỗi mapping/ngữ cảnh nội bộ cần điều tra |

Không đọc phần chi tiết “failing row contains ...” rồi trả lại cho client. Nó có thể chứa nhiều trường hơn dữ liệu client đã gửi, bao gồm thông tin nội bộ hoặc dữ liệu từ đối tượng khác.

### 11.1. Bảo vệ cả đơn vị nghiệp vụ khi có lỗi

Nếu một transaction đã cập nhật tổng tiền rồi insert refund vi phạm check, cần hủy những thay đổi phải nguyên tử cùng refund đó. Dịch lỗi thành một object lỗi không tự làm transaction rollback.

Chỉ dùng savepoint và partial success khi hợp đồng nghiệp vụ cho phép. Ví dụ một import có thể chấp nhận từng dòng độc lập theo thiết kế, nhưng không được bỏ một bước ghi sổ bắt buộc rồi commit phần tăng tổng tiền hoàn.

Với batch, phản hồi từng dòng phải dựa trên kết quả thực tế của transaction hoặc savepoint tương ứng. Không đánh dấu các dòng trước là thành công nếu toàn bộ batch cuối cùng đã rollback.

## 12. Bắt lỗi ở flush và commit trong ứng dụng Java

ORM có thể trì hoãn SQL đến lúc flush hoặc commit. Method gọi `save()` thành công không chứng minh database đã chấp nhận dữ liệu.

```text
Controller gọi service transactional
  → service thay đổi entity
  → service trả giá trị
  → interceptor flush/commit
  → constraint violation xuất hiện
```

Nếu try/catch chỉ ở bên trong service và lỗi phát sinh sau khi method trả về, nhánh bắt lỗi đó không bao phủ được thời điểm commit. Ranh giới xử lý cần bao quanh lời gọi transaction thực tế hoặc dùng cơ chế xử lý exception phù hợp của framework sau khi transaction manager đã kết thúc.

Flush tường minh có thể giúp phát hiện một số lỗi sớm, nhưng không thay thế commit và không bảo đảm mọi constraint được kiểm tra ở đó. Constraint kiểm tra muộn có thể chỉ thất bại khi kết thúc transaction.

### 12.1. Quy tắc exception của framework vẫn quan trọng

Nếu bắt lỗi persistence rồi đổi thành checked exception, phải bảo đảm quy tắc rollback vẫn đúng với transaction manager và cấu hình đang dùng. Không giả định mọi exception mới đều hủy transaction.

Nếu transaction đã rollback-only, bắt exception rồi trả response thành công không xóa được trạng thái đó. Lỗi có thể xuất hiện khi outer kết thúc, chẳng hạn một thông báo rollback ngoài dự kiến theo cơ chế framework.

Một thiết kế rõ ràng là để lớp thực thi transaction trả kết quả chỉ sau commit, còn tầng dịch lỗi xử lý failure đã được gắn ngữ cảnh. Các hành động phục hồi có đọc database được thực hiện sau khi transaction cũ đã kết thúc đúng cách.

### 12.2. Không tạo tác dụng bên ngoài trước khi biết kết quả

Gửi email thành công, phát event trực tiếp hoặc gọi API thanh toán trước commit có thể tạo tác dụng dù constraint sau đó làm database rollback.

Khi cần phát sự kiện bền vững sau thay đổi, có thể ghi outbox trong cùng transaction. Worker gửi lại theo cơ chế chống lặp của đường phát. Dịch lỗi constraint không hoàn tác một email hoặc giao dịch ngoài database đã xảy ra.

## 13. Chính sách retry theo loại lỗi

| Loại lỗi đã xác định | Retry tự động có phù hợp không? | Điều kiện cần giữ |
|---|---|---|
| Unique của cùng ý định/idempotency | Thường cần tra cứu kết quả hoặc trả xung đột, không chạy mới mù quáng | Cùng scope, fingerprint và quyền hiện tại |
| Check đầu vào không hợp lệ | Không thử lại nguyên request với cùng dữ liệu để mong kết quả khác | Sửa nội dung theo hợp đồng, vẫn giữ quy tắc ý định |
| Foreign key sai hoặc ngoài phạm vi | Không retry tùy tiện | Phân loại nguyên nhân và quyền trước |
| Phụ thuộc bất đồng bộ được phép đến trễ | Có thể chờ và xử lý lại có giới hạn | Chỉ cho quan hệ/nguồn đã được định nghĩa |
| Deadlock hoặc serialization failure xác nhận transaction bị hủy | Có thể thử lại toàn bộ transaction | Không có tác dụng ngoài phạm vi chưa được chống lặp; kiểm tra lại dữ liệu |
| Mất kết nối hoặc chưa rõ commit | Không kết luận chưa có tác dụng | Tra cứu operation, đối soát và giữ định danh ổn định |
| Constraint lạ hoặc lỗi mapping nội bộ | Không tự mở rộng điều kiện để cho request qua | Hủy an toàn và điều tra |

Không nhét mọi exception database vào một annotation retry chung. Mỗi lần thử có thể lại đi qua gọi dịch vụ ngoài hoặc tiêu thụ tài nguyên, và một lỗi dữ liệu không trở thành lỗi tạm thời chỉ vì được thử nhiều lần.

Nếu retry transaction được phép, bắt đầu transaction mới từ ranh giới đúng, đọc lại dữ liệu và kiểm tra quyền/phê duyệt theo chính sách. Giới hạn số lần thử, thời gian tổng và dùng backoff phù hợp; không ngủ trong một transaction đang giữ khóa.

Client mất kết nối không chứng minh server đã hủy. Key mới không phải cách sửa chung cho một response lỗi. Các hướng dẫn công khai phải giúp client giữ đúng danh tính ý định khi tra cứu hoặc retry.

## 14. Bảo mật thông tin trong response và telemetry

### 14.1. Tránh oracle về sự tồn tại của dữ liệu

Các phản hồi như “email đã tồn tại”, “mã đơn này thuộc khách hàng khác” hoặc “tên tài khoản quản trị đã được dùng” có thể hỗ trợ dò dữ liệu nếu công khai không đúng ngữ cảnh.

Kiểm tra quyền trước khi thực hiện thay đổi và áp dụng chính sách phản hồi nhất quán. Lớp dịch lỗi là lớp phòng vệ bổ sung, không phải chỗ dùng thông tin lỗi database để xác định quyền mà lẽ ra phải kiểm tra trước.

Trong một giao diện quản trị được cấp quyền, thông tin chi tiết hơn có thể phù hợp. Cần phân biệt quyền đó bằng ngữ cảnh server, không bằng một cờ `debug=true` hoặc `isAdmin` do client gửi.

### 14.2. Nội bộ cũng cần tối thiểu hóa dữ liệu

Log có cấu trúc có thể ghi:

```json
{
  "event": "persistence_write_rejected",
  "operation": "CREATE_REFUND",
  "sql_state": "23505",
  "constraint": "uq_refunds_tenant_intent",
  "classification": "EXISTING_INTENT_RESOLUTION_REQUIRED",
  "request_id": "request-73"
}
```

Không thêm nguyên SQL, bind parameters, failing row, token hoặc payload thanh toán vào log theo mặc định. Ghi cả stack trace của exception database cũng có thể kéo theo message chứa dữ liệu; cần chính sách lọc và quyền đọc log phù hợp.

Nếu ghi `transaction_outcome`, chỉ dùng giá trị đã có bằng chứng. Phát hiện lỗi statement không tự chứng minh mọi tác dụng ngoài transaction đã được hoàn tác.

Metric nên dùng các nhóm hữu hạn như thao tác, loại lỗi và mã phân loại đã biết. Không dùng message, key, user ID hoặc tên constraint tùy ý chưa chuẩn hóa làm nhãn có số lượng giá trị không giới hạn.

## 15. Quản lý danh mục dịch lỗi qua migration

Constraint là hợp đồng nội bộ giữa database và ứng dụng. Đổi tên, tách bảng hoặc thay cơ chế ràng buộc có thể làm lớp dịch lỗi mất khả năng nhận diện nếu triển khai không đồng bộ.

Một danh mục có thể ghi:

```text
dialect và phạm vi schema/bảng
tên constraint hoặc metadata thay thế được cho phép
nhóm thao tác/đường ghi
mã nghiệp vụ ổn định
điều kiện để phân loại là lỗi dự kiến
chính sách phục hồi hoặc retry
chủ sở hữu bất biến
```

Tên constraint có thể trùng ở những bảng hoặc schema khác nhau theo quy tắc của hệ quản trị. Vì vậy không mặc định tên đơn lẻ là định danh toàn cục. Kết hợp metadata relation và đường ghi tin cậy khi cần, như guard trong ví dụ Java.

Khi đổi tên constraint trong triển khai nhiều phiên bản, có thể cần hỗ trợ cả tên cũ và mới trong một giai đoạn chuyển tiếp, rồi loại bỏ ánh xạ cũ sau khi chắc chắn không còn node hoặc schema cũ liên quan.

Mã lỗi công khai không cần đổi chỉ vì tên constraint đổi. Nếu ý nghĩa bất biến thay đổi, phải đánh giá lại hành vi nghiệp vụ thay vì giữ mapping cũ một cách máy móc.

Không dùng wildcard quá rộng như “mọi constraint bắt đầu bằng `uq_` đều là `ALREADY_EXISTS`”. Một unique mới có thể bảo vệ một quy tắc hoàn toàn khác, và việc biến nó thành lỗi thường gặp sẽ che lỗi triển khai.

## 16. Kiểm thử lớp dịch lỗi

### 16.1. Kiểm thử nhận diện trên hệ quản trị thực tế

Mock một exception có chuỗi “duplicate” chỉ kiểm tra mẫu chuỗi đã giả định. Với những nhánh quan trọng, cần xác minh metadata và lớp bọc thực tế mà driver/framework cung cấp khi vi phạm constraint.

Kiểm tra unique, foreign key, check, not-null và những loại constraint thật sự được sử dụng. Nếu lỗi không có tên constraint, xác nhận adapter không tự đoán một mapping không có căn cứ.

Các test nên tập trung vào ràng buộc có ảnh hưởng nghiệp vụ và ranh giới dịch lỗi, không lặp lại mọi câu SQL chỉ để chứng minh database có tính năng constraint.

### 16.2. Kiểm thử rollback và thời điểm lỗi

Gây lỗi sau khi một thay đổi bắt buộc khác đã được thực hiện, rồi đọc database bằng connection/ngữ cảnh độc lập sau khi transaction kết thúc. Xác nhận không còn dữ liệu một phần trái bất biến.

Thử lỗi tại statement, flush và commit khi mô hình có ràng buộc kiểm tra muộn. Kiểm tra cả trường hợp exception bị bọc hoặc được chuyển loại và quy tắc rollback của framework.

Không chỉ dùng một test luôn tự rollback ở cuối rồi kết luận production có cùng hành vi. Cần biết test nào thật sự quan sát commit và exception ở ranh giới transaction thực tế.

### 16.3. Kiểm thử đồng thời và idempotency

Gửi hai request cùng ý định qua connection độc lập. Xác nhận chỉ có số tác dụng nghiệp vụ cho phép, request còn lại nhận kết quả hoặc xung đột đúng hợp đồng.

Sau đó giữ key nhưng đổi amount/currency, đổi tenant, đổi chủ thể hoặc đối tượng. Không được trả kết quả cũ ngoài quyền hoặc đánh dấu thành công cho payload khác.

Với unique violation cần đọc lại, xác nhận việc tra cứu diễn ra sau khi transaction lỗi đã kết thúc và dùng đúng phạm vi. Không chỉ kiểm tra mã HTTP.

### 16.4. Kiểm thử nội dung lỗi công khai

Response không được chứa tên bảng/cột/constraint, SQL, giá trị khóa, stack trace hoặc thông tin xác nhận dữ liệu ngoài quyền.

Thử constraint không biết tên, metadata thiếu, lỗi ở bảng khác có tên constraint giống nhau và tên đã đổi trong migration. Kỳ vọng là phân loại đúng hoặc fallback an toàn, không biến lỗi lạ thành thành công.

Kiểm tra cả log/trace của đường lỗi: response sạch không có nghĩa dữ liệu nhạy cảm không bị đẩy vào telemetry.

## 17. Quan sát và xử lý lỗi ngoài dự kiến

Theo dõi tỷ lệ lỗi theo nhóm constraint đã biết, thao tác, kết quả phục hồi và số lỗi không nhận diện được. Một đợt tăng unique violation có thể do client dùng lại ý định sai, tải đồng thời hoặc thay đổi triển khai; cần ngữ cảnh để phân biệt.

Lỗi check/not-null ngoài dự kiến tăng sau khi triển khai có thể chỉ ra lỗi mapping hoặc một đường ghi không tuân thủ bất biến. Không sửa bằng cách bỏ constraint hoặc nới classifier để trả lỗi client cho dễ vận hành.

Quy trình điều tra nên xác định:

1. Thao tác và transaction nào đã thất bại, có tác dụng ngoài database không.
2. SQLSTATE và metadata nào đã được nhận diện, có đúng relation/constraint không.
3. Phần dữ liệu nào do client gửi và phần nào do server tự tạo.
4. Constraint đang chặn một cuộc đua hợp lệ hay bộc lộ lỗi triển khai.
5. Có cần đọc kết quả cũ, đối soát hoặc sửa code/dữ liệu theo quy trình hay không.
6. Mã lỗi công khai và log có tiết lộ dữ liệu không cần thiết không.

Nếu có lỗi dịch, điều chỉnh danh mục cùng kiểm tra hồi quy cho tình huống cụ thể. Giữ constraint bảo vệ bất biến trong khi xử lý nguyên nhân; thay đổi chính sách nghiệp vụ phải là một quyết định có chủ đích.

## 18. Câu hỏi tự kiểm tra

1. Một lỗi constraint được nhận diện bằng metadata nào, có phụ thuộc message không?
2. Cùng SQLSTATE có thể mang những ý nghĩa nghiệp vụ khác nhau ở đâu?
3. Constraint, schema/bảng và đường ghi đã được ghép đúng chưa?
4. Exception có thể xuất hiện ở statement, flush hay commit, và ai kết thúc transaction lỗi?
5. Unique violation cần trả xung đột hay đọc kết quả cũ, dựa trên bằng chứng nào?
6. Response hoặc log có thể lộ giá trị khóa, dữ liệu chéo tenant hoặc sự tồn tại của tài khoản không?
7. Lỗi nào được retry, lỗi nào cần sửa request và lỗi nào phải điều tra nội bộ?
8. Khi migration đổi tên constraint, mã lỗi công khai và khả năng bảo vệ bất biến có còn ổn định không?

Constraint error translation cần giữ nguyên quyết định bảo vệ của database, diễn giải đúng trong ngữ cảnh nghiệp vụ và kết thúc transaction theo đúng ngữ nghĩa. Một lớp dịch lỗi tốt giúp client nhận hướng xử lý ổn định, đồng thời không biến vi phạm bất biến, lỗi quyền hoặc kết quả chưa xác định thành thành công hay thông tin bị tiết lộ ngoài ý muốn.
