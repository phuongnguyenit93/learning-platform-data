# Xung đột phiên bản, vi phạm ràng buộc và số hàng cập nhật bằng không

Trong Spring Data Relational R2DBC, một thao tác ghi có thể thất bại vì nhiều nguyên nhân khác nhau. Ba tình huống thường bị nhầm lẫn là vi phạm ràng buộc dữ liệu, xung đột phiên bản khi nhiều transaction cùng sửa một entity và câu UPDATE/DELETE không tác động đến row nào.

Chúng có biểu hiện gần giống nhau ở tầng API — request không ghi được dữ liệu — nhưng ý nghĩa và cách xử lý khác nhau:

- **Constraint violation**: dữ liệu được gửi lên vi phạm quy tắc do database bảo vệ, chẳng hạn unique, foreign key, NOT NULL hoặc CHECK.
- **Optimistic locking conflict**: entity đã được một transaction khác thay đổi kể từ lúc transaction hiện tại đọc nó; giá trị version không còn khớp.
- **Zero rows updated/deleted**: câu DML không tìm thấy row phù hợp hoặc không làm thay đổi row theo semantics của database/driver. Cần biết API và câu SQL nào được dùng trước khi kết luận nguyên nhân.

Không nên gom tất cả thành lỗi 500 chung, retry mù hoặc cấp thêm quyền. Hãy phân loại theo SQLSTATE/vendor code, exception Spring, câu SQL, điều kiện WHERE, version và transaction context.

## 1. Ba nhóm lỗi khác nhau

| Nhóm | Điều gì xảy ra? | Ví dụ | Cách xử lý thường gặp |
|---|---|---|---|
| Vi phạm constraint | Database từ chối dữ liệu không hợp lệ | Email trùng, FK không tồn tại, CHECK thất bại | Trả lỗi nghiệp vụ phù hợp, sửa dữ liệu hoặc luồng ghi |
| Optimistic locking | Version hiện tại không khớp version entity đã đọc | Hai request cùng sửa một đơn hàng | Báo conflict, đọc lại và áp dụng lại nghiệp vụ nếu an toàn |
| Zero rows affected | DML không tác động row nào | ID không tồn tại, WHERE lọc sai, version cũ | Phân biệt not found, stale state, filter mismatch hoặc semantics row count |

Một thao tác có thể gặp nhiều lớp bảo vệ cùng lúc. Ví dụ UPDATE có điều kiện version có thể ảnh hưởng 0 row vì version đã cũ; một INSERT khác có thể bị unique constraint từ chối. Hai trường hợp cần cách xử lý khác nhau.

## 2. Constraint là gì?

Constraint là quy tắc toàn vẹn được khai báo ở database. Nó bảo vệ dữ liệu bất kể thao tác đến từ Spring Data R2DBC, SQL trực tiếp, batch job hay một service khác.

Các loại phổ biến:

- PRIMARY KEY: mỗi row có định danh duy nhất.
- UNIQUE: một giá trị hoặc tổ hợp cột không được trùng.
- FOREIGN KEY: giá trị tham chiếu phải tồn tại ở bảng được tham chiếu.
- NOT NULL: cột bắt buộc có giá trị.
- CHECK: giá trị phải thỏa biểu thức điều kiện.
- EXCLUSION hoặc constraint đặc thù: ngăn các giá trị/row xung đột theo quy tắc của hệ quản trị.

Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    credit_limit DECIMAL(18, 2) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_credit_limit
        CHECK (credit_limit >= 0)
);
~~~

Constraint là lớp bảo vệ cuối cùng cho invariant dữ liệu. Kiểm tra trước ở Java vẫn hữu ích để đưa ra thông báo thân thiện, nhưng không thay thế constraint vì hai request đồng thời có thể vượt qua bước kiểm tra trước khi một request ghi dữ liệu.

## 3. Unique constraint và duplicate key

Giả sử hệ thống yêu cầu email khách hàng duy nhất:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
~~~

Hai request đồng thời có thể cùng kiểm tra email chưa tồn tại:

~~~text
Request A: SELECT email -> không có
Request B: SELECT email -> không có
Request A: INSERT email -> thành công
Request B: INSERT email -> unique violation
~~~

Vì vậy, mẫu SELECT trước rồi INSERT không bảo đảm tính duy nhất. Database phải có unique constraint để xử lý cạnh tranh ở tầng lưu trữ.

### Xử lý duplicate một cách đúng đắn

- Nếu email trùng là lỗi nghiệp vụ, chuyển thành lỗi kiểu EmailAlreadyRegistered.
- Nếu thao tác phải idempotent, xác định bản ghi hiện có có cùng ý nghĩa với request hay không.
- Nếu muốn cập nhật khi trùng, dùng upsert có chủ đích theo dialect database.
- Không tự động xóa bản ghi cũ hoặc ghi đè dữ liệu của người khác chỉ để làm request thành công.

Không phải mọi unique violation đều là duplicate theo cùng một ý nghĩa. Một bảng có thể có nhiều unique constraint, chẳng hạn email, mã external và số chứng từ. Cần biết constraint nào bị vi phạm để ánh xạ sang lỗi nghiệp vụ phù hợp.

## 4. Foreign key violation

Foreign key bảo đảm row con tham chiếu đến row cha tồn tại:

~~~sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_id) REFERENCES product(id)
);
~~~

Các tình huống gây lỗi:

- Insert order_line với order_id không tồn tại.
- Insert dòng tham chiếu product đã bị xóa.
- Xóa orders đang được order_line tham chiếu khi FK không cho phép.
- Thay đổi khóa cha khiến tham chiếu con không còn hợp lệ.

Không nên chỉ bắt mọi foreign key error rồi trả “Order not found”. Có thể lỗi đến từ product, tenant, category hoặc một bảng tham chiếu khác.

### Kiểm tra trước và race condition

Ứng dụng có thể kiểm tra order tồn tại trước khi insert order_line để cải thiện trải nghiệm. Tuy nhiên, row cha vẫn có thể bị xóa giữa SELECT và INSERT. Foreign key là bảo vệ cuối cùng.

Nếu nghiệp vụ yêu cầu bảo đảm cha còn tồn tại trong cả chuỗi thao tác, hãy thiết kế transaction và locking/isolation phù hợp. Không giả định một SELECT thông thường sẽ ngăn transaction khác xóa row.

## 5. NOT NULL và CHECK violation

NOT NULL:

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET NOT NULL;
~~~

Lỗi xuất hiện khi INSERT hoặc UPDATE cố ghi NULL vào cột bắt buộc. Trong R2DBC, cần phân biệt Java null, bindNull và việc bỏ qua một thuộc tính khi mapping entity. Database cuối cùng vẫn kiểm tra constraint.

CHECK:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_quantity
CHECK (quantity >= 0);
~~~

Lỗi xảy ra nếu thao tác làm quantity âm. Đây là cách bảo vệ invariant ở database, ngay cả khi có nhiều service cùng ghi bảng inventory.

Không chỉ dựa vào validation ở controller. Các thao tác background, import hoặc SQL trực tiếp có thể bỏ qua controller.

## 6. Exception được ánh xạ trong Spring và R2DBC

R2DBC driver phát lỗi theo SPI, thường là một dạng R2dbcException có thông tin như message, SQLSTATE và error code của vendor. Spring có thể dịch lỗi database sang hệ exception của Spring DAO.

Các exception thường gặp ở tầng Spring:

| Exception | Ý nghĩa khái quát |
|---|---|
| DataIntegrityViolationException | Vi phạm tính toàn vẹn dữ liệu |
| DuplicateKeyException | Xung đột khóa duy nhất/duplicate key được nhận diện |
| OptimisticLockingFailureException | Cập nhật/xóa versioned entity không còn khớp |
| TransientDataAccessException | Lỗi được phân loại là tạm thời theo translator |
| DataAccessException | Nhóm exception truy cập dữ liệu tổng quát |

Không phải mọi driver hoặc mọi database đều ánh xạ một lỗi cụ thể thành đúng cùng subclass. Một unique violation có thể được nhận diện thành DuplicateKeyException ở một cấu hình, nhưng có thể chỉ xuất hiện dưới DataIntegrityViolationException hoặc exception khác ở cấu hình khác.

Vì vậy, code nghiệp vụ nên xử lý các abstraction Spring đã được xác nhận trên driver mục tiêu, đồng thời giữ log nội bộ về SQLSTATE/vendor code để chẩn đoán.

### Đọc SQLSTATE và vendor error code

R2DBC SPI exception có thể cung cấp:

- getSqlState(): SQLSTATE nếu driver có thông tin.
- getErrorCode(): mã lỗi riêng của vendor nếu có.
- getMessage(): thông báo lỗi từ driver/database.
- getCause(): nguyên nhân bên dưới nếu được cung cấp.

Không giả định mọi driver đều điền đủ các trường. Hãy kiểm tra exception chain thay vì chỉ đọc exception ngoài cùng.

## 7. Một số mã lỗi thường gặp theo database

Các mã dưới đây là ví dụ phổ biến, không phải danh sách đầy đủ. Phiên bản database, driver và cách translator có thể ảnh hưởng exception cuối cùng.

| Hệ quản trị | Duplicate/unique | Foreign key | NOT NULL / CHECK |
|---|---|---|---|
| PostgreSQL | SQLSTATE 23505 | 23503 | 23502 / 23514 |
| MySQL | Error 1062 | 1452 khi insert/update row con; 1451 khi xóa/sửa row cha bị tham chiếu | 1048; CHECK thường có mã riêng theo phiên bản |
| SQL Server | 2601 hoặc 2627 | 547 | 515 cho NULL; 547 có thể áp dụng CHECK/FK |
| Oracle | ORA-00001 | ORA-02291 hoặc ORA-02292 | ORA-01400; ORA-02290 |
| SQLite | Constraint error code theo loại constraint | Foreign key constraint failed | NOT NULL/CHECK constraint failed |

Không nên hard-code một mã vendor vào toàn bộ domain service nếu ứng dụng hỗ trợ nhiều database. Đặt việc nhận diện vendor-specific ở tầng adapter/error translator.

## 8. Constraint name giúp phân loại lỗi

Khi có nhiều unique/FK constraint, constraint name có giá trị chẩn đoán:

~~~sql
CONSTRAINT uq_customer_email UNIQUE (email),
CONSTRAINT uq_customer_external_id UNIQUE (external_id),
CONSTRAINT fk_customer_tenant
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
~~~

Tên constraint rõ ràng giúp log và migration dễ hiểu hơn tên tự sinh như uk_9k3....

Tuy nhiên, không phải driver nào cũng cung cấp constraint name qua một API portable. Có thể cần parse message/vendor metadata ở adapter riêng, nhưng không nên parse message tự do trong domain logic nếu có lựa chọn tốt hơn.

Không gửi nguyên constraint name, SQL, table name nội bộ hoặc error message database cho client cuối. Ánh xạ thành lỗi nghiệp vụ và giữ chi tiết kỹ thuật trong log có kiểm soát.

## 9. Optimistic locking là gì?

Optimistic locking (khóa lạc quan) giả định xung đột ghi không xảy ra thường xuyên. Thay vì khóa row trong suốt thời gian người dùng chỉnh sửa, ứng dụng lưu một version và kiểm tra version đó khi cập nhật.

Ví dụ:

~~~text
Database:
id = 10, quantity = 20, version = 4

Request A đọc version 4
Request B đọc version 4

Request A cập nhật:
WHERE id = 10 AND version = 4
SET quantity = 18, version = 5
=> 1 row được cập nhật

Request B cập nhật:
WHERE id = 10 AND version = 4
SET quantity = 15, version = 5
=> 0 row khớp vì version hiện tại đã là 5
=> optimistic locking conflict
~~~

Request B không nên ghi đè thay đổi của A một cách âm thầm. Nó phải đọc trạng thái mới và quyết định nghiệp vụ có thể áp dụng lại hay cần yêu cầu người dùng xử lý conflict.

## 10. Dùng @Version trong Spring Data Relational

Spring Data Relational cung cấp annotation org.springframework.data.annotation.Version:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer quantity;

    @Version
    private Long version;
}
~~~

Khi insert entity mới, Spring Data khởi tạo version theo quy tắc của kiểu version được hỗ trợ. Với kiểu số, giá trị ban đầu thường là 0. Khi update entity đã tồn tại, version được tăng và được đưa vào điều kiện WHERE.

SQL về mặt ý nghĩa:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = :newVersion
WHERE id = :id
  AND version = :oldVersion;
~~~

Đây là hình dạng minh họa; câu SQL thực tế do Spring Data và dialect tạo ra.

Nếu không có row nào khớp ID và version, thao tác trên versioned entity phát sinh OptimisticLockingFailureException. Điều đó báo rằng entity không còn ở version mà caller đã đọc.

### Version phải được quản lý nhất quán

- Cột version phải tồn tại trong schema với kiểu tương thích.
- Không tự tăng version trong code trước khi gọi save nếu Spring Data đang quản lý nó.
- Không để một luồng ghi khác sửa row mà bỏ qua quy ước version nếu ứng dụng dựa vào optimistic locking.
- Dùng entity được trả về sau save vì version mới có thể được ghi lại vào instance đó.
- Với entity bất biến, dùng instance kết quả do Spring Data tạo/trả về thay vì tiếp tục giữ version cũ.

Không nhầm @Version với một cột nghiệp vụ như revisionLabel. Version phục vụ phát hiện xung đột lưu trữ; revision nghiệp vụ có thể có quy tắc riêng.

## 11. Cách dùng version trong luồng repository

Một luồng đọc rồi sửa:

~~~java
public Mono<Inventory> changeQuantity(
        Long inventoryId,
        int newQuantity) {

    return inventoryRepository.findById(inventoryId)
        .switchIfEmpty(Mono.error(
            new InventoryNotFoundException(inventoryId)
        ))
        .flatMap(inventory -> {
            inventory.setQuantity(newQuantity);
            return inventoryRepository.save(inventory);
        });
}
~~~

Nếu một request khác đã lưu version mới sau khi findById, lệnh save của request hiện tại sẽ phát optimistic locking exception.

Nếu cần dùng kết quả sau khi save:

~~~java
return inventoryRepository.save(inventory)
    .map(saved -> {
        // saved có version mới sau update
        return saved;
    });
~~~

Không giả định object đầu vào luôn được cập nhật tại chỗ, đặc biệt khi entity immutable hoặc mapping sử dụng wither/copy.

## 12. Optimistic locking trên UPDATE và DELETE

Với versioned entity, Spring Data có thể dùng ID và version để bảo đảm thao tác UPDATE/DELETE chỉ tác động entity ở version mà caller đang giữ.

Ví dụ delete một entity đã đọc:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
    .flatMap(repository::delete);
~~~

Nếu entity bị thay đổi trước khi delete, version không còn khớp và thao tác delete versioned có thể phát optimistic locking failure.

Khác biệt quan trọng:

- delete(entity) có entity và version để kiểm tra.
- deleteById(id) chỉ có ID; nó không mang version mà caller đã đọc để so sánh.

Nếu nghiệp vụ yêu cầu xóa có kiểm tra version, hãy dùng thao tác nhận entity/version hoặc viết custom conditional DELETE. Không dùng deleteById rồi giả định đã có optimistic concurrency control.

## 13. @Version không phải pessimistic lock

Optimistic locking không giữ khóa row trong suốt thời gian người dùng chỉnh sửa. Nó phát hiện xung đột tại thời điểm ghi.

Pessimistic locking thường dùng database lock như SELECT ... FOR UPDATE, nhưng khả năng và API hỗ trợ phụ thuộc database, driver và Spring Data R2DBC. Không nên giả định mọi repository method có annotation lock kiểu JPA đều hoạt động tương đương.

Chọn optimistic locking khi:

- Xung đột tương đối hiếm.
- Transaction ngắn.
- Có thể yêu cầu caller đọc lại và xử lý conflict.
- Không muốn giữ row lock trong thời gian xử lý dài.

Chọn cơ chế khóa khác khi nghiệp vụ cần tuần tự hóa thao tác và database/driver hỗ trợ phù hợp. Không mở transaction lâu trong lúc chờ người dùng xác nhận trên UI.

## 14. Xử lý OptimisticLockingFailureException

Không nên chuyển mọi optimistic locking failure thành lỗi server chung. Đây thường là xung đột trạng thái có thể biểu diễn thành HTTP 409 Conflict hoặc một lỗi nghiệp vụ tương đương.

Ví dụ:

~~~java
return inventoryRepository.save(inventory)
    .onErrorMap(
        OptimisticLockingFailureException.class,
        error -> new InventoryConflictException(inventory.getId())
    );
~~~

Ở tầng HTTP, ánh xạ conflict sang response phù hợp:

~~~json
{
  "code": "INVENTORY_VERSION_CONFLICT",
  "message": "Dữ liệu đã thay đổi. Hãy tải lại trước khi lưu."
}
~~~

Response không cần tiết lộ SQL, version nội bộ hoặc exception message của database.

Nếu API dùng HTTP ETag/If-Match, version có thể được biểu diễn thành entity tag. Khi client gửi If-Match cũ, server có thể trả 412 Precondition Failed theo hợp đồng API. Chọn 409 hoặc 412 nhất quán với semantics endpoint.

## 15. Khi nào được retry optimistic conflict?

Retry mù cùng entity cũ không giải quyết conflict:

~~~text
Lần 1: version 4 không còn khớp
Retry cùng version 4: vẫn không khớp
Retry lần nữa: vẫn không khớp
~~~

Muốn retry, phải đọc lại state mới và tính lại thay đổi dựa trên nghiệp vụ:

1. Đọc row hiện tại và version mới.
2. Kiểm tra thay đổi của transaction khác có làm yêu cầu hiện tại mất hiệu lực không.
3. Tính lại kết quả từ state mới.
4. Lưu bằng version vừa đọc.
5. Giới hạn số lần retry và dùng backoff nếu phù hợp.

Ví dụ tăng counter có thể áp dụng lại phép cộng nếu nghiệp vụ cho phép. Nhưng thao tác “đặt quantity thành 5” có thể không được tự động áp dụng lại nếu người khác vừa sửa số lượng vì lý do nghiệp vụ.

Không retry mọi OptimisticLockingFailureException vô điều kiện. Với nhiều request cạnh tranh, retry có thể tạo vòng lặp xung đột và tăng tải database.

## 16. Atomic update để tránh read-modify-write

Một số nghiệp vụ có thể được biểu diễn thành một câu UPDATE nguyên tử thay vì đọc entity, sửa trong Java rồi save:

~~~sql
UPDATE inventory
SET quantity = quantity - :amount
WHERE id = :id
  AND quantity >= :amount;
~~~

Database kiểm tra điều kiện và cập nhật trong cùng statement. Cách này tránh cửa sổ race giữa SELECT và UPDATE cho invariant quantity không âm.

Nếu cần version:

~~~sql
UPDATE inventory
SET quantity = quantity - :amount,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND quantity >= :amount;
~~~

Số row được cập nhật bằng 1 nghĩa là điều kiện phù hợp đã được áp dụng. Số 0 có thể do ID không tồn tại, version không khớp hoặc quantity không đủ. Một mình row count chưa phân biệt được ba nguyên nhân.

Để phân loại chính xác, có thể:

- Dùng câu SQL/RETURNING phù hợp database để trả kết quả.
- Thực hiện một truy vấn kiểm tra tiếp trong transaction theo semantics phù hợp.
- Trả một lỗi tổng quát “không thể áp dụng thay đổi” nếu API không cần phân biệt.

Không chạy SELECT kiểm tra rồi kết luận tuyệt đối nếu trạng thái có thể thay đổi đồng thời sau SELECT.

## 17. Số hàng cập nhật bằng không nghĩa là gì?

Với DML:

~~~sql
UPDATE orders
SET status = :status
WHERE id = :id;
~~~

Số row được cập nhật bằng 0 có thể có nhiều nguyên nhân:

1. Không tồn tại row có ID đó.
2. Row tồn tại nhưng điều kiện WHERE khác không khớp.
3. Tenant hoặc ownership filter loại row khỏi phạm vi.
4. Version trong WHERE không còn khớp.
5. Row đã bị xóa bởi transaction khác.
6. Driver/database báo row count theo semantics “row thực sự thay đổi” và giá trị mới bằng giá trị cũ.
7. Trigger, view hoặc loại DML đặc thù ảnh hưởng số row được báo.

Do đó, zero rows không đồng nghĩa trong mọi trường hợp với “record not found”.

## 18. Phân biệt matched rows và changed rows

Một số database/driver có thể phân biệt:

- Rows matched: số row thỏa WHERE.
- Rows changed/affected: số row có giá trị thực sự thay đổi.

Ví dụ:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 10;
~~~

Nếu row 10 đã có status ACTIVE, database/driver có thể báo số row khác nhau tùy semantics và cấu hình. MySQL có khác biệt liên quan đến CLIENT_FOUND_ROWS; các database/driver khác cũng có quy tắc row count riêng.

Đối với thao tác versioned entity, Spring Data tăng version khi update nên thao tác thành công có một thay đổi version thực tế. Điều này giúp optimistic locking không phụ thuộc vào việc giá trị nghiệp vụ có thay đổi hay không.

Với custom SQL không tăng version, hãy hiểu chính xác ý nghĩa rowsUpdated trên database/driver đang dùng trước khi dùng số 0 làm điều kiện not found.

## 19. DatabaseClient và rowsUpdated

Một custom update qua DatabaseClient có thể đọc số row được báo:

~~~java
Mono<Integer> rowsUpdated = databaseClient.sql(
        "UPDATE orders " +
        "SET status = :status " +
        "WHERE id = :id AND tenant_id = :tenantId"
    )
    .bind("status", status)
    .bind("id", id)
    .bind("tenantId", tenantId)
    .fetch()
    .rowsUpdated();
~~~

API Spring DatabaseClient có thể biểu diễn row count dưới kiểu số nguyên theo phiên bản framework. Ở tầng R2DBC SPI, Result.getRowsUpdated() phát Publisher của số lượng row theo contract SPI. Kiểu trả về cụ thể cần được đối chiếu với API đang dùng.

Kiểm tra số row:

~~~java
return rowsUpdated.flatMap(count -> {
    if (count == 1) {
        return Mono.empty();
    }
    if (count == 0) {
        return Mono.error(new OrderNotUpdatedException(id));
    }
    return Mono.error(new UnexpectedUpdateCountException(count));
});
~~~

Đây là chính sách phù hợp khi hợp đồng thao tác yêu cầu đúng một row và database/driver có semantics row count phù hợp. Nếu update không đổi giá trị có thể trả 0 trên database mục tiêu, cần điều chỉnh SQL hoặc phân loại riêng.

Nếu update có thể tác động nhiều row, đừng ép count phải bằng 1. Hãy xác định giới hạn và semantics đúng với nghiệp vụ.

## 20. Zero rows trong UPDATE có version

Với versioned entity, Spring Data dùng version trong điều kiện cập nhật. Nếu version không khớp hoặc row không tồn tại, không có row nào được cập nhật và Spring Data báo optimistic locking failure.

Về mặt ý nghĩa:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

Một kết quả 0 ở đây biểu thị thao tác không thể áp dụng cho version mà entity đang giữ. Nguyên nhân có thể là stale version hoặc row đã biến mất; muốn phân biệt cần thêm thông tin.

Không bắt OptimisticLockingFailureException rồi chuyển thành success chỉ vì client không cần biết chi tiết. Nếu update là bắt buộc, caller phải nhận được kết quả conflict/not found phù hợp.

## 21. Zero rows trong UPDATE không version

Nếu entity không có @Version hoặc custom SQL không kiểm tra version:

~~~sql
UPDATE orders
SET status = :status
WHERE id = :id;
~~~

Nếu count là 0:

- Có thể ID không tồn tại.
- Có thể row bị xóa.
- Có thể câu WHERE có thêm filter không khớp.
- Có thể không có giá trị nào thực sự thay đổi theo semantics driver.

Spring Data không thể suy ra ý nghĩa nghiệp vụ từ một câu SQL tùy chỉnh nếu ứng dụng không cung cấp thêm điều kiện.

Nếu cần phân biệt not found và no-op, có thể đọc trạng thái trước, hoặc dùng SQL trả về row phù hợp với database. Hãy xác định transaction/isolation vì trạng thái vẫn có thể thay đổi giữa hai statement.

## 22. Zero rows trong DELETE

Ví dụ:

~~~sql
DELETE FROM orders
WHERE id = :id
  AND tenant_id = :tenantId;
~~~

Số 0 có thể có nghĩa:

- ID không tồn tại.
- Row thuộc tenant khác.
- Row đã bị xóa.
- Điều kiện bổ sung không khớp.

Đối với API bảo mật, có thể cố ý trả cùng một kết quả not found cho ID không tồn tại và ID thuộc tenant khác để tránh tiết lộ sự tồn tại của dữ liệu ngoài phạm vi.

Nếu dùng versioned delete(entity), version có thể tham gia điều kiện và stale version được phát hiện. deleteById(id) không mang version đã đọc nên không thể bảo đảm cùng semantics optimistic delete.

## 23. Constraint violation trong reactive transaction

Khi một câu INSERT/UPDATE vi phạm constraint bên trong transaction, database có thể đánh dấu transaction ở trạng thái lỗi. Nếu lỗi được truyền ra khỏi reactive chain, transaction manager có thể rollback transaction theo quy tắc.

Ví dụ:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(saved -> orderLineRepository.saveAll(lines).then())
);
~~~

Nếu một thao tác trong chain phát lỗi, lỗi đi ra ngoài transaction boundary và transaction được rollback.

### Không nuốt lỗi constraint trong cùng transaction

Không nên:

~~~java
return transactionalOperator.transactional(
    repository.save(entity)
        .onErrorResume(DataIntegrityViolationException.class,
            error -> Mono.empty())
        .then(repository.save(otherEntity))
);
~~~

Ở một số database, đặc biệt PostgreSQL, statement lỗi có thể làm transaction ở trạng thái aborted cho đến khi rollback. Nuốt exception ở reactive chain không tự khôi phục transaction. Câu lệnh tiếp theo có thể thất bại vì transaction vẫn lỗi.

Nếu lỗi là một phần nghiệp vụ có thể bỏ qua, hãy thiết kế transaction boundary riêng, dùng savepoint khi database/driver hỗ trợ và hiểu rõ semantics. Không chỉ chuyển lỗi thành Mono.empty().

## 24. Phân biệt lỗi có thể retry và không nên retry

| Loại lỗi | Retry cùng request ngay? | Hướng xử lý |
|---|---|---|
| Unique violation do business key trùng | Thường không | Xác định duplicate, idempotency hoặc upsert |
| Foreign key violation | Thường không | Kiểm tra dữ liệu tham chiếu và thứ tự ghi |
| NOT NULL/CHECK violation | Không | Sửa input hoặc logic |
| Optimistic locking conflict | Không retry entity cũ | Đọc lại và áp dụng lại nghiệp vụ có giới hạn |
| Deadlock | Có thể retry transaction toàn bộ | Retry có backoff và giới hạn |
| Serialization failure | Có thể retry transaction toàn bộ | Chạy lại toàn bộ logic transaction |
| Connection reset/timeout | Tùy thời điểm và tính idempotent | Xác định commit outcome trước khi retry |
| Zero rows | Không tự retry | Phân loại not found, stale state hoặc predicate mismatch |

Retry chỉ an toàn khi biết thao tác trước đó đã commit hay chưa và thao tác có idempotent hay không. Với lỗi mạng sau khi gửi COMMIT, client có thể không biết database đã commit hay chưa.

## 25. Idempotency khi client gửi lại request

Nếu client timeout rồi gửi lại lệnh tạo đơn hàng, unique constraint trên idempotency key có thể ngăn tạo đơn trùng:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_idempotency_key
UNIQUE (idempotency_key);
~~~

Request đầu tiên tạo đơn. Request lặp dùng cùng idempotency key:

- Nếu payload tương đương, trả lại kết quả đã lưu.
- Nếu payload khác, trả lỗi conflict.
- Không tạo đơn thứ hai chỉ vì client không nhận được response đầu.

Idempotency key cần được ràng buộc với actor/tenant và có thời hạn/lifecycle theo nghiệp vụ. Không dùng một key toàn cục có thể va chạm giữa khách hàng khác nhau nếu phạm vi uniqueness cần theo tenant.

## 26. Upsert không thay thế xử lý conflict một cách mù quáng

Upsert hữu ích khi nghiệp vụ thật sự là “tạo nếu chưa có, nếu có thì cập nhật theo quy tắc”. Nó không phải cách chung để bỏ qua mọi duplicate.

Trước khi dùng upsert:

- Xác định conflict target.
- Bảo đảm unique constraint tương ứng.
- Quy định cột nào được cập nhật.
- Xác định có được phép ghi đè dữ liệu hiện tại không.
- Xử lý generated ID và version.
- Kiểm thử concurrency trên đúng database.

Nếu entity dùng optimistic locking, một câu upsert custom có thể bỏ qua version check nếu không đưa version vào SQL. Khi đó, nó có thể phá vỡ quy tắc concurrency mà các repository method khác đang dựa vào.

## 27. Tách exception translation khỏi domain logic

Một cấu trúc có thể dùng:

~~~text
R2DBC driver exception
        |
        v
Spring DataAccessException / OptimisticLockingFailureException
        |
        v
Persistence adapter
        |
        v
Domain exception
        |
        v
Application/API error mapping
~~~

Persistence adapter là nơi biết database, constraint name hoặc vendor code. Domain layer nên nhận lỗi có ý nghĩa nghiệp vụ như:

- CustomerEmailAlreadyExists.
- ReferencedProductNotFound.
- InventoryConflict.
- OrderNotFound.
- OrderStateChanged.

Không đưa SQLSTATE hoặc mã lỗi PostgreSQL vào domain model nếu ứng dụng cần hỗ trợ nhiều database. Có thể giữ mã kỹ thuật trong log/telemetry.

### Ví dụ ánh xạ exception

~~~java
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(
            DuplicateKeyException.class,
            error -> new CustomerEmailAlreadyExists()
        );
}
~~~

Ví dụ này chỉ đúng khi persistence adapter đã xác nhận lỗi DuplicateKeyException tương ứng với constraint email trong schema đang dùng. Nếu bảng có nhiều unique key, cần cách phân loại chính xác hơn thay vì ánh xạ mọi duplicate sang lỗi email.

## 28. Chẩn đoán một lỗi trong production

Khi nhận được lỗi ghi dữ liệu:

1. Xác định operation là INSERT, UPDATE, DELETE hay repository save.
2. Xác định entity có @Version không.
3. Ghi nhận ID, tenant scope và expected version nếu được phép.
4. Ghi SQL fingerprint hoặc SQL đã che dữ liệu nhạy cảm.
5. Ghi loại bind parameter, không ghi secret hoặc dữ liệu nhạy cảm nguyên văn.
6. Lấy exception chain, SQLSTATE và vendor error code.
7. Xác định constraint name nếu database/driver cung cấp.
8. Xem rowsUpdated hoặc row count nếu thao tác custom DML.
9. Kiểm tra transaction có đang hoạt động và có bị đánh dấu rollback-only/aborted không.
10. Kiểm tra migration/schema có đúng phiên bản không.
11. Đối chiếu log request và concurrent operation có thể đã sửa/xóa row.
12. Reproduce bằng đúng database version và R2DBC driver trong môi trường test.

Không ghi toàn bộ SQL có bind value nhạy cảm vào log production. Dùng correlation ID, query fingerprint và dữ liệu đã che.

## 29. Phân tích optimistic conflict với hai transaction

Một integration test có thể mô phỏng hai reader:

~~~text
T1: SELECT inventory -> version 7
T2: SELECT inventory -> version 7
T1: UPDATE WHERE id=? AND version=7 -> version 8
T1: COMMIT
T2: UPDATE WHERE id=? AND version=7 -> 0 row
T2: OptimisticLockingFailureException
~~~

Test cần dùng hai transaction/connection độc lập để thật sự mô phỏng cạnh tranh. Gọi hai lần save tuần tự trên cùng một entity trong một transaction không chứng minh được optimistic locking hoạt động đúng khi có concurrent writer.

Sau conflict:

- T2 không được âm thầm ghi đè T1.
- T2 có thể đọc lại version 8.
- Nghiệp vụ quyết định có thể áp dụng thay đổi của T2 lên state mới không.
- Nếu không thể tự hòa giải, trả conflict cho caller.

## 30. Kiểm thử constraint violation

Integration test nên kiểm tra:

- Insert duplicate unique key.
- Insert row có FK không tồn tại.
- Xóa parent đang được tham chiếu.
- Ghi NULL vào cột NOT NULL.
- Ghi giá trị vi phạm CHECK.
- Xác nhận exception class/SQLSTATE được driver mục tiêu trả về.
- Xác nhận transaction rollback khi lỗi được truyền ra ngoài boundary.
- Xác nhận lỗi được ánh xạ thành domain/API response phù hợp.

Không chỉ mock DuplicateKeyException. Mock không chứng minh database constraint thực sự được khai báo hoặc driver dịch lỗi đúng.

## 31. Kiểm thử rowsUpdated bằng không

Tạo các trường hợp riêng:

1. UPDATE ID không tồn tại.
2. UPDATE ID có tồn tại nhưng tenant không khớp.
3. UPDATE với version cũ.
4. UPDATE đặt lại cùng giá trị.
5. DELETE ID không tồn tại.
6. DELETE với version cũ.
7. UPDATE có trigger hoặc view nếu ứng dụng dùng loại object đó.

Ghi nhận số row và exception cho đúng database/driver. Đặc biệt kiểm tra semantics matched-versus-changed rows nếu API dựa vào row count để trả not found.

## 32. Version trong entity bất biến

Với entity immutable hoặc Java record, không nên giả định Spring Data cập nhật version trên object đầu vào:

~~~java
@Table("inventory")
public record Inventory(
    @Id Long id,
    Integer quantity,
    @Version Long version
) {
}
~~~

Khi save:

~~~java
return inventoryRepository.save(inventory)
    .flatMap(saved -> {
        // Dùng saved.version() cho thao tác tiếp theo
        return continueWith(saved);
    });
~~~

Dùng entity được trả về để có ID/version do persistence layer cập nhật. Cơ chế tạo instance mới phụ thuộc mapping và entity model; hãy kiểm tra với phiên bản Spring Data đang dùng.

## 33. Version và cập nhật ngoài Spring Data

Nếu một service khác cập nhật bảng mà không tăng version, Spring Data có thể không phát hiện được thay đổi đó:

~~~sql
UPDATE inventory
SET quantity = 100
WHERE id = 10;
~~~

Nếu câu SQL này không tăng version, entity đang giữ version cũ vẫn có thể khớp điều kiện version của Spring Data và ghi đè dữ liệu vừa thay đổi.

Mọi writer cần tuân thủ cùng quy ước version:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = version + 1
WHERE id = :id;
~~~

Nếu không thể kiểm soát tất cả writer, cân nhắc trigger quản lý version, stored procedure hoặc một cơ chế concurrency thống nhất. Tránh để cả ứng dụng và trigger cùng tăng version hai lần.

## 34. Constraint và transaction nhiều bước

Giả sử tạo order và order_line:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(savedOrder ->
            saveLines(savedOrder.getId(), lines)
                .thenReturn(savedOrder)
        )
);
~~~

Nếu một order_line vi phạm FK hoặc CHECK, lỗi đi ra ngoài transaction boundary thì cả order và các line đã ghi trong transaction đó được rollback.

Nếu code bắt lỗi và tiếp tục transaction, cần hiểu database có cho phép tiếp tục sau statement failure không. PostgreSQL thường đánh dấu transaction aborted sau constraint error cho đến khi rollback transaction hoặc rollback về savepoint phù hợp.

Không tạo response “order created” trước khi transaction commit thành công. Trong reactive chain, hãy để kết quả được phát sau khi transaction operator hoàn tất.

## 35. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| SELECT trước rồi INSERT để tránh duplicate | Race condition vẫn xảy ra | Dùng unique constraint và xử lý duplicate |
| Bắt mọi DataIntegrityViolationException thành duplicate email | Trả sai lỗi khi FK/CHECK/NOT NULL vi phạm | Phân loại constraint cụ thể ở adapter |
| Bỏ constraint vì ứng dụng đã validate | Writer khác có thể làm hỏng invariant | Giữ constraint ở database |
| Không khai báo @Version nhưng kỳ vọng tự phát hiện lost update | Request sau có thể ghi đè request trước | Dùng version hoặc atomic conditional update |
| Retry entity cũ sau optimistic conflict | Version vẫn cũ, conflict lặp lại | Đọc lại và tính lại nghiệp vụ |
| Bỏ qua exception của repository save | Caller tưởng dữ liệu đã được lưu | Truyền lỗi hoặc ánh xạ thành domain error |
| Nhầm zero rows với not found | Bỏ sót stale version hoặc filter mismatch | Xét WHERE, version và row-count semantics |
| Giả định rowsUpdated luôn là changed rows | No-op update bị phân loại sai | Kiểm thử driver/database cụ thể |
| Dùng deleteById khi cần kiểm tra version | Không có expected version để so sánh | Delete entity hoặc custom conditional DELETE |
| Nuốt constraint error trong transaction | Transaction có thể vẫn aborted | Để lỗi đi ra hoặc dùng savepoint đúng cách |
| Custom upsert bỏ qua version | Ghi đè thay đổi concurrent | Thiết kế conflict/version semantics rõ ràng |
| Một writer không tăng version | Optimistic locking bị vô hiệu một phần | Chuẩn hóa mọi đường ghi |
| Retry lỗi mạng mà không biết commit outcome | Tạo dữ liệu trùng hoặc lặp side effect | Dùng idempotency key và xác định commit outcome |
| Log raw SQL và bind values | Rò rỉ dữ liệu nhạy cảm | Log fingerprint và tham số đã che |

## 36. Quy trình xử lý lỗi ghi dữ liệu

Khi một lệnh ghi thất bại, có thể đi theo thứ tự:

1. Lấy exception chain và phân loại lỗi ở tầng Spring/R2DBC.
2. Nếu là integrity violation, xác định constraint và giá trị nghiệp vụ liên quan.
3. Nếu là optimistic locking failure, xác định expected/current version và quyết định hòa giải hay trả conflict.
4. Nếu row count bằng 0, kiểm tra câu WHERE, tenant scope, version và semantics row count của driver.
5. Kiểm tra transaction rollback và các thao tác trước đó trong cùng chain.
6. Chỉ retry khi lỗi được xác định là transient hoặc nghiệp vụ cho phép re-read/reapply.
7. Ánh xạ thành domain/API error ổn định.
8. Ghi telemetry đủ để điều tra mà không lộ dữ liệu.

## 37. Ghi nhớ

- Constraint violation là database từ chối dữ liệu vi phạm PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL, CHECK hoặc quy tắc tương tự.
- Kiểm tra trước trong Java không thay thế constraint vì vẫn có race condition.
- Spring có thể dịch lỗi R2DBC thành DataIntegrityViolationException, DuplicateKeyException hoặc exception khác; mapping tùy driver/database.
- SQLSTATE và vendor error code hữu ích để phân loại lỗi, nhưng không nên đưa mã vendor vào domain model.
- @Version cho phép Spring Data Relational phát hiện update/delete trên entity đã bị thay đổi kể từ lúc đọc.
- Dùng entity được trả về sau save để nhận version mới, nhất là với entity immutable.
- Retry optimistic conflict phải đọc lại và tính lại nghiệp vụ; không retry cùng entity/version cũ.
- delete(entity) có thể kiểm tra version; deleteById không mang expected version của entity đã đọc.
- Zero rows có thể là ID không tồn tại, predicate không khớp, tenant scope, stale version hoặc semantics matched/changed rows.
- Đừng coi rowsUpdated = 0 là not found một cách phổ quát; kiểm tra database và driver.
- Atomic conditional UPDATE giúp bảo vệ invariant mà không cần read-modify-write ở ứng dụng.
- Constraint error trong transaction phải được xử lý theo semantics rollback của database; không nuốt lỗi rồi tiếp tục mù quáng.
- Upsert custom phải tôn trọng unique constraint và optimistic version nếu nghiệp vụ dựa vào version.
- Dùng idempotency key khi client có thể retry sau timeout không rõ commit outcome.
- Integration test cần dùng đúng database/R2DBC driver và mô phỏng hai transaction độc lập để kiểm tra concurrency.
