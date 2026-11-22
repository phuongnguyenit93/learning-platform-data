# Delete theo thực thể hoặc điều kiện

Trong Spring Data R2DBC, thao tác xóa dữ liệu có thể bắt đầu từ một entity đã được tải, từ định danh của entity hoặc từ một điều kiện truy vấn. Lựa chọn cách xóa ảnh hưởng tới số lần truy cập database, khả năng kiểm tra phiên bản dữ liệu, số hàng bị tác động và cách ứng dụng xử lý quan hệ khóa ngoại.

Nếu đã có entity và muốn xóa đúng entity đó, có thể dùng `ReactiveCrudRepository.delete(entity)` hoặc `R2dbcEntityTemplate.delete(entity)`. Nếu chỉ có ID, `deleteById(id)` tránh phải tải entity trước. Nếu muốn xóa nhiều hàng theo điều kiện, `R2dbcEntityTemplate` với `Query`/`Criteria` hoặc một câu SQL `DELETE` qua `DatabaseClient` thường phù hợp hơn việc tải tất cả entity rồi xóa từng cái.

Điều quan trọng là hiểu rõ khác biệt giữa xóa một entity và xóa theo điều kiện. Xóa theo entity có thể sử dụng thông tin định danh và trường phiên bản để kiểm soát optimistic locking. Xóa hàng loạt theo điều kiện thường được thực hiện trực tiếp ở database, không tải từng entity lên ứng dụng và không áp dụng kiểm tra phiên bản riêng cho từng hàng.

## 1. Ba cách xác định dữ liệu cần xóa

Một thao tác delete thường xác định hàng cần xóa theo một trong ba cách:

| Cách xác định | API thường dùng | Khi phù hợp |
|---|---|---|
| Entity đã có | `repository.delete(entity)` hoặc `template.delete(entity)` | Đã tải entity, cần xóa đúng đối tượng đó và có thể cần kiểm tra `@Version` |
| Định danh | `repository.deleteById(id)` | Chỉ có ID, không cần đọc dữ liệu trước khi xóa |
| Điều kiện | `template.delete(Type.class).matching(query).all()` hoặc SQL `DELETE` | Xóa nhiều hàng theo tiêu chí, không cần materialize từng entity |

Ví dụ một bảng `person` có thể có các entity như sau:

```java
@Table("person")
public record Person(
    @Id Long id,
    String firstname,
    String lastname,
    String status,
    @Version Long version
) {}
```

Trong ví dụ này, `id` là định danh và `version` dùng cho optimistic locking. Tùy schema và quy tắc nghiệp vụ, một ứng dụng có thể xóa theo ID, theo entity đã tải hoặc xóa tất cả người dùng có trạng thái nhất định.

## 2. Xóa theo entity bằng ReactiveCrudRepository

`ReactiveCrudRepository` cung cấp `delete(T entity)` trả về `Mono<Void>`. Ứng dụng truyền entity cần xóa:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {
}
```

```java
@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    public Mono<Void> delete(Person person) {
        return repository.delete(person);
    }
}
```

Thao tác này phù hợp khi entity đã được tải và tầng nghiệp vụ cần áp dụng quy tắc trước khi xóa. Ví dụ, service có thể kiểm tra trạng thái tài khoản, quyền của người gọi hoặc điều kiện nghiệp vụ rồi mới gọi `delete`.

Lệnh xóa entity dựa trên định danh của entity; không nên hiểu rằng Spring Data so sánh tất cả thuộc tính Java với các cột để tìm hàng cần xóa. Nếu entity có `@Version`, giá trị phiên bản cũng có thể được dùng trong điều kiện xóa để phát hiện dữ liệu đã thay đổi kể từ khi entity được đọc.

`Mono<Void>` biểu diễn việc thao tác hoàn tất hoặc phát lỗi. Nó không trả về số hàng bị xóa. Nếu nghiệp vụ cần biết có hàng nào thực sự bị tác động, có thể dùng API trả số hàng như `R2dbcEntityTemplate` hoặc `DatabaseClient`.

### Xóa entity sau khi tải

```java
public Mono<Void> deletePerson(Long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(new PersonNotFoundException(id)))
        .flatMap(repository::delete);
}
```

Luồng này thực hiện hai thao tác: đọc entity rồi xóa. Nó hữu ích khi cần kiểm tra trạng thái hoặc quyền dựa trên dữ liệu hiện tại. Nếu chỉ cần xóa theo ID và không cần kiểm tra entity, có thể gọi trực tiếp `deleteById(id)` để tránh một truy vấn `SELECT`.

Lưu ý rằng giữa bước đọc và bước xóa, một transaction khác có thể thay đổi hoặc xóa hàng. Nếu entity có `@Version`, optimistic locking giúp phát hiện một số trường hợp cập nhật cạnh tranh. Nếu cần bảo vệ nhiều bước nghiệp vụ, hãy đặt chúng trong một transaction phù hợp và thiết kế điều kiện cập nhật/xóa rõ ràng.

## 3. Xóa theo ID

Khi chỉ có ID, `deleteById` là lựa chọn đơn giản:

```java
public Mono<Void> deletePerson(Long id) {
    return repository.deleteById(id);
}
```

`deleteById` không yêu cầu tải entity trước. Đây là cách phù hợp cho thao tác xóa đơn giản khi ID đã được xác thực và không cần kiểm tra dữ liệu hiện tại.

Vì phương thức trả `Mono<Void>`, ứng dụng không thể suy ra từ giá trị phát ra rằng có đúng một hàng đã bị xóa. Nếu cần phân biệt “đã xóa” với “không tìm thấy”, hãy dùng một câu delete trả số hàng bị tác động hoặc thực hiện một luồng đọc/xóa theo quy tắc nghiệp vụ. Cần cân nhắc race condition nếu tách việc kiểm tra tồn tại và xóa thành hai thao tác.

Với nhiều ID, `ReactiveCrudRepository` có các phương thức như `deleteAllById(...)` tùy phiên bản API. Có thể dùng chúng khi muốn xóa theo một tập ID. Nếu cần số lượng hàng bị tác động, điều kiện bổ sung hoặc SQL đặc thù, dùng `DatabaseClient` hoặc template để nhận kết quả phù hợp.

## 4. Xóa entity bằng R2dbcEntityTemplate

`R2dbcEntityTemplate` cung cấp API thao tác entity ở mức Spring Data. Có thể xóa một entity đã có:

```java
public Mono<Void> delete(Person person) {
    return template.delete(person);
}
```

Template sử dụng mapping metadata để xác định bảng và các cột định danh của entity. Cách này hữu ích khi lớp truy cập dữ liệu đã dùng `R2dbcEntityTemplate` thay vì Repository, hoặc khi muốn kết hợp các thao tác insert/select/update/delete trong cùng một abstraction.

Khi entity có trường `@Version`, cần giữ giá trị phiên bản đúng với lần đọc gần nhất. Nếu một luồng khác đã cập nhật hàng và tăng version, thao tác xóa với entity cũ có thể thất bại bằng lỗi optimistic locking. Ứng dụng nên xử lý lỗi này như một xung đột dữ liệu, ví dụ yêu cầu người dùng tải lại thông tin hoặc áp dụng lại thao tác theo quy tắc nghiệp vụ.

## 5. Xóa theo điều kiện bằng Query và Criteria

Khi muốn xóa tất cả hàng thỏa một điều kiện, không cần tải từng entity. `R2dbcEntityTemplate` cho phép tạo điều kiện bằng `Criteria` và truyền vào `Query`:

```java
public Mono<Long> deleteInactivePeople() {
    Query query = Query.query(
        Criteria.where("status").is("INACTIVE")
    );

    return template.delete(Person.class)
        .matching(query)
        .all();
}
```

Trong ví dụ này:

1. `Person.class` xác định loại entity và bảng cần xóa.
2. `Criteria.where("status").is("INACTIVE")` tạo điều kiện theo thuộc tính entity.
3. `Query.query(...)` đóng gói điều kiện thành truy vấn.
4. `matching(query)` áp dụng điều kiện cho thao tác delete.
5. `all()` thực hiện xóa tất cả hàng phù hợp và trả `Mono<Long>` biểu diễn số hàng bị tác động.

Tên thuộc tính trong Criteria thường là tên thuộc tính Java của entity. Mapping context chuyển nó sang cột tương ứng theo annotation hoặc naming strategy. Cần dùng đúng kiểu giá trị và kiểu thuộc tính để driver bind dữ liệu chính xác.

### Kết hợp nhiều điều kiện

Ví dụ chỉ xóa tài khoản không hoạt động trong một khoảng thời gian:

```java
public Mono<Long> deleteExpiredAccounts(Instant cutoff) {
    Criteria criteria = Criteria.where("status").is("INACTIVE")
        .and("lastLoginAt").lessThan(cutoff);

    return template.delete(Account.class)
        .matching(Query.query(criteria))
        .all();
}
```

Điều kiện kết hợp giúp giới hạn phạm vi xóa. Trước khi chạy thao tác destructive, cần xác định chính xác tập hàng sẽ bị tác động. Có thể chạy một truy vấn `SELECT` với cùng điều kiện trong môi trường phát triển hoặc vận hành để kiểm tra phạm vi, sau đó mới thực hiện delete.

### Điều kiện OR

Khi cần xóa theo nhiều nhánh điều kiện, có thể kết hợp `Criteria` theo API của phiên bản Spring Data đang dùng. Ví dụ về ý tưởng:

```java
Criteria criteria = Criteria.where("status").is("CLOSED")
    .or("status").is("CANCELLED");

return template.delete(Order.class)
    .matching(Query.query(criteria))
    .all();
```

API ghép Criteria có thể khác theo phiên bản; hãy đối chiếu tài liệu của release train trong dự án. Với điều kiện phức tạp, SQL tường minh qua `DatabaseClient` thường dễ kiểm tra hơn.

## 6. Xóa theo điều kiện bằng câu SQL với DatabaseClient

Khi cần cú pháp database-specific, điều kiện phức tạp hoặc muốn kiểm soát rõ câu lệnh, có thể dùng `DatabaseClient`:

```java
public Mono<Long> deleteOrdersBefore(Instant cutoff) {
    return databaseClient.sql("""
            DELETE FROM purchase_order
            WHERE status = :status
              AND created_at < :cutoff
            """)
        .bind("status", "CANCELLED")
        .bind("cutoff", cutoff)
        .fetch()
        .rowsUpdated();
}
```

`rowsUpdated()` trả số hàng bị tác động dưới dạng publisher. Cách này phù hợp khi cần ghi rõ SQL, dùng cú pháp riêng của hệ quản trị hoặc xóa từ bảng không được ánh xạ thành entity.

Luôn dùng bind parameter cho giá trị đầu vào. Không ghép trực tiếp chuỗi do người dùng cung cấp vào câu SQL. Bind parameter bảo vệ giá trị, nhưng không thể thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu phải chọn cột động, hãy ánh xạ lựa chọn qua allow-list cố định trong code.

### Dùng PostgreSQL DELETE RETURNING

PostgreSQL hỗ trợ `RETURNING`, cho phép lấy dữ liệu của các hàng vừa bị xóa:

```java
public Flux<Long> deleteAndReturnIds(String status) {
    return databaseClient.sql("""
            DELETE FROM purchase_order
            WHERE status = :status
            RETURNING id
            """)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
}
```

Đây là cú pháp riêng của PostgreSQL, không phải SQL portable cho mọi hệ quản trị. Nếu cần thông tin hàng đã xóa, hãy kiểm tra tính năng tương đương của database đang dùng. Không nên thực hiện một `SELECT` sau khi xóa để đoán các ID đã bị xóa, vì dữ liệu có thể thay đổi giữa hai thao tác.

## 7. Derived delete query và @Query

Spring Data hỗ trợ query method cho nhiều thao tác đọc và một số thao tác sửa/xóa. Với derived delete method hoặc `@Query` có `@Modifying`, cần xác nhận khả năng và kiểu trả về được hỗ trợ trong đúng phiên bản Spring Data R2DBC của dự án.

Ví dụ một phương thức xóa theo tên:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Mono<Long> deleteByStatus(String status);
}
```

Nếu release train đang dùng hỗ trợ derived delete query với kiểu trả về số lượng, phương thức này có thể diễn tả rõ ý định xóa theo thuộc tính. Nếu không hỗ trợ hoặc cần kiểm soát SQL chính xác, dùng `@Modifying` với `@Query` hoặc `DatabaseClient`.

Ví dụ câu SQL xóa tùy chỉnh:

```java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Modifying
    @Query("DELETE FROM person WHERE status = :status")
    Mono<Integer> deleteByStatusUsingSql(String status);
}
```

Kiểu trả về và annotation cần khớp với API của phiên bản đang dùng. Hãy kiểm tra tài liệu chính thức, dependency tree và integration test thay vì sao chép ví dụ từ một release train khác. Với SQL tùy chỉnh, cần kiểm tra tên bảng/cột, bind parameter và dialect của database.

## 8. Delete theo entity và delete theo điều kiện khác nhau thế nào?

| Tiêu chí | Delete theo entity | Delete theo điều kiện |
|---|---|---|
| Đối tượng đầu vào | Một entity đã có | Query/Criteria hoặc SQL condition |
| Số hàng thường tác động | Một hàng theo định danh | Một hoặc nhiều hàng |
| Có cần tải entity trước? | Có thể đã có entity; nếu tải để kiểm tra thì có thêm SELECT | Không cần tải từng entity |
| Optimistic locking | Có thể kiểm tra `@Version` của entity | Không kiểm tra version riêng cho từng hàng theo cách delete entity |
| Lifecycle callback theo entity | Có thể chạy theo luồng thao tác entity của framework | Thường không có callback cho từng entity vì không materialize entity |
| Kết quả | Thường `Mono<Void>` | Template/DatabaseClient có thể trả số hàng bị tác động |
| Phù hợp | Xóa một đối tượng sau khi kiểm tra nghiệp vụ | Cleanup, xóa theo trạng thái, thời gian hoặc tập điều kiện |

Bulk delete theo điều kiện thường hiệu quả hơn khi số lượng hàng lớn vì database thực hiện thao tác trực tiếp. Tuy nhiên, ứng dụng phải tự cân nhắc các quy tắc cần áp dụng cho từng entity, chẳng hạn kiểm tra version, ghi audit theo từng bản ghi hoặc phát domain event riêng cho mỗi hàng.

Nếu cần chạy nghiệp vụ cho từng entity trước khi xóa, có thể truy vấn các entity phù hợp rồi xử lý từng entity. Cách này tốn tài nguyên và số lần truy cập hơn nhưng cho phép thực hiện logic theo từng đối tượng. Với số lượng lớn, nên cân nhắc xử lý theo batch hoặc thiết kế quy trình cleanup riêng.

## 9. Optimistic locking khi xóa entity

Spring Data Relational hỗ trợ optimistic locking thông qua `@Version`. Khi entity có version, framework sử dụng giá trị version để phát hiện một transaction khác đã thay đổi entity sau lần đọc trước đó.

Ví dụ:

```java
@Table("document")
public record Document(
    @Id Long id,
    String title,
    @Version Long version
) {}
```

Giả sử hai request cùng đọc document với `version = 4`. Request A cập nhật document và database chuyển version thành 5. Request B vẫn giữ entity cũ với version 4 rồi gọi `delete(entity)`. Điều kiện xóa có thể bao gồm cả ID và version; vì hàng hiện tại không còn version 4, thao tác không xóa được và framework báo lỗi optimistic locking.

Đây là hành vi hữu ích khi nghiệp vụ yêu cầu không xóa một entity đã bị người khác thay đổi mà người dùng chưa biết. Tầng service có thể chuyển lỗi thành phản hồi xung đột, yêu cầu tải lại dữ liệu hoặc cho phép người dùng xác nhận lại.

Bulk delete theo điều kiện không tải từng entity để kiểm tra `@Version`. Nếu cần chỉ xóa hàng ở một version cụ thể, hãy đưa điều kiện version vào Query/SQL:

```sql
DELETE FROM document
WHERE id = :id
  AND version = :expectedVersion;
```

Sau đó kiểm tra số hàng bị tác động. Nếu kết quả bằng 0, hàng không tồn tại hoặc version đã thay đổi. Ứng dụng có thể truy vấn bổ sung nếu cần phân biệt hai tình huống, nhưng phải cân nhắc race condition giữa các thao tác.

## 10. Quan hệ khóa ngoại và cascade delete

Spring Data R2DBC không tự thực hiện cascade remove theo object graph như một số ORM. Khi xóa một entity cha, việc các hàng con có bị xóa hay không phụ thuộc schema database và logic ứng dụng.

Ví dụ foreign key có thể được khai báo:

```sql
CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(id)
        ON DELETE CASCADE
);
```

Với `ON DELETE CASCADE`, database tự xóa các dòng `order_line` khi hàng `purchase_order` tương ứng bị xóa. Đây là cascade ở cấp database, được thực thi bởi foreign key, không phải do Spring Data đi qua từng entity con.

Các lựa chọn thường gặp:

- `ON DELETE CASCADE`: xóa hàng con khi hàng cha bị xóa. Phù hợp khi dữ liệu con không có ý nghĩa độc lập ngoài cha.
- `ON DELETE RESTRICT` hoặc hành vi mặc định tương đương: từ chối xóa cha khi còn hàng con tham chiếu. Phù hợp khi cần bảo vệ lịch sử hoặc dữ liệu tham chiếu.
- `ON DELETE SET NULL`: đặt khóa ngoại ở hàng con thành null nếu quan hệ cho phép null và dữ liệu con vẫn có ý nghĩa độc lập.

Không nên dùng cascade chỉ để làm cho lệnh delete chạy được. Với dữ liệu giao dịch, lịch sử tài chính hoặc dữ liệu cần audit, xóa dây chuyền có thể phá hủy thông tin quan trọng. Có thể dùng trạng thái hủy, lưu trữ hoặc soft delete thay vì xóa vật lý.

## 11. Xóa nhiều bảng trong một transaction reactive

Nếu không dùng cascade ở database và một nghiệp vụ phải xóa nhiều bảng, hãy đặt các thao tác trong một transaction để tránh trạng thái dở dang.

Ví dụ xóa các dòng hàng rồi xóa đơn hàng:

```java
@Service
public class OrderDeletionService {

    private final DatabaseClient databaseClient;

    public OrderDeletionService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Transactional
    public Mono<Void> deleteOrder(Long orderId) {
        Mono<Long> deleteLines = databaseClient.sql("""
                DELETE FROM order_line
                WHERE order_id = :orderId
                """)
            .bind("orderId", orderId)
            .fetch()
            .rowsUpdated();

        Mono<Long> deleteOrder = databaseClient.sql("""
                DELETE FROM purchase_order
                WHERE id = :orderId
                """)
            .bind("orderId", orderId)
            .fetch()
            .rowsUpdated();

        return deleteLines.then(deleteOrder).then();
    }
}
```

Ví dụ minh họa thứ tự xóa con trước cha. `@Transactional` cần được xử lý bởi reactive transaction manager dùng cùng `ConnectionFactory` với `DatabaseClient`. Các publisher được trả về trong cùng chuỗi để Spring quản lý transaction. Không gọi `subscribe()` bên trong phương thức vì điều đó tạo subscription độc lập và có thể khiến thao tác thoát khỏi transaction.

Nếu database đã cấu hình `ON DELETE CASCADE`, có thể chỉ cần xóa hàng cha và để database xóa hàng con. Chọn một cách có chủ đích để tránh vừa xóa thủ công vừa dựa vào cascade không cần thiết.

## 12. Soft delete và xóa vật lý

Không phải nghiệp vụ nào cũng nên xóa hàng khỏi database. **Soft delete** đánh dấu hàng đã bị xóa về mặt nghiệp vụ nhưng vẫn giữ dữ liệu vật lý, ví dụ:

```sql
ALTER TABLE person
    ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE NULL;
```

Khi xóa:

```sql
UPDATE person
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND deleted_at IS NULL;
```

Khi đọc dữ liệu đang hoạt động, truy vấn thêm điều kiện `deleted_at IS NULL`. Có thể dùng `status = 'DELETED'` hoặc một cờ boolean nếu phù hợp với mô hình miền.

Spring Data R2DBC không tự biến mọi lệnh delete thành soft delete chỉ vì entity có trường `deletedAt`. Ứng dụng cần triển khai thao tác cập nhật, query filter và quy tắc khôi phục rõ ràng. Có thể đóng gói hành vi này trong service hoặc lớp truy cập dữ liệu để tránh quên điều kiện lọc.

Soft delete có một số hệ quả:

- Unique constraint có thể cần điều chỉnh nếu muốn cho phép tạo lại bản ghi với cùng mã sau khi bản ghi cũ bị xóa mềm. PostgreSQL có thể dùng partial unique index; database khác có cơ chế khác.
- Các truy vấn đọc phải nhất quán trong việc loại bỏ hàng đã xóa mềm.
- Cần quy định ai được xem dữ liệu đã xóa, khi nào có thể khôi phục và khi nào phải xóa vật lý.
- Dữ liệu cá nhân hoặc dữ liệu có thời hạn lưu trữ cần tuân theo chính sách xóa và retention của hệ thống.

## 13. Xử lý kết quả và lỗi khi xóa

Khi dùng template hoặc `DatabaseClient`, số hàng bị tác động giúp service phân biệt các kết quả:

```java
public Mono<Void> deletePerson(Long id) {
    return template.delete(Person.class)
        .matching(Query.query(Criteria.where("id").is(id)))
        .all()
        .flatMap(deleted -> deleted == 1
            ? Mono.empty()
            : Mono.error(new PersonNotFoundException(id)));
}
```

Ví dụ này giả định ID là duy nhất và muốn báo lỗi nếu không có hàng nào bị xóa. Nếu hệ thống coi delete là idempotent, có thể chấp nhận `deleted == 0` như một kết quả thành công. Quyết định phụ thuộc hợp đồng API: DELETE có thể trả thành công khi tài nguyên đã không còn tồn tại, hoặc trả 404 nếu nghiệp vụ yêu cầu xác nhận tài nguyên tồn tại.

Các lỗi thường gặp:

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Foreign key constraint violation | Hàng khác vẫn tham chiếu tới hàng định xóa | Xóa dữ liệu con đúng thứ tự, cấu hình cascade phù hợp hoặc từ chối thao tác theo nghiệp vụ |
| Optimistic locking failure | Entity có version cũ so với database | Tải lại entity và xử lý xung đột theo nghiệp vụ |
| Không có hàng bị tác động | ID không tồn tại hoặc điều kiện không khớp | Quyết định trả 404, bỏ qua hay báo kết quả không thay đổi |
| Unique/constraint hoặc lỗi database khác | Trigger, constraint hoặc dữ liệu không đáp ứng quy tắc | Phân loại lỗi và ánh xạ thành lỗi nghiệp vụ phù hợp |
| Timeout hoặc mất kết nối | Database chậm hoặc kết nối bị gián đoạn | Ghi log, kiểm tra trạng thái thao tác và chỉ retry khi an toàn |

Không nên tự động retry một lệnh delete khi không rõ database đã commit hay chưa. Nếu phản hồi bị mất sau khi server thực thi delete, lần retry có thể tác động 0 hàng. Điều này có thể chấp nhận với thao tác idempotent, nhưng cần phù hợp hợp đồng API và transaction.

## 14. Kết hợp điều kiện động an toàn

Một tác vụ cleanup có thể nhận nhiều tiêu chí như trạng thái, thời điểm và tenant. Không nên xây dựng SQL bằng cách nối chuỗi đầu vào. Với `R2dbcEntityTemplate`, hãy tạo Criteria từ các giá trị đã xác thực:

```java
public Mono<Long> deleteByStatusAndTenant(
        String status,
        Long tenantId,
        Instant before) {

    Criteria criteria = Criteria.where("tenantId").is(tenantId)
        .and("status").is(status)
        .and("createdAt").lessThan(before);

    return template.delete(AuditRecord.class)
        .matching(Query.query(criteria))
        .all();
}
```

Nếu filter là tùy chọn, chỉ thêm điều kiện khi có giá trị. Cần kiểm tra trường hợp tất cả filter đều vắng mặt: một query không có điều kiện có thể xóa toàn bộ bảng. Với thao tác cleanup diện rộng, nên yêu cầu một phạm vi bắt buộc như tenant, khoảng thời gian hoặc trạng thái cho phép.

Nếu cần tên cột hoặc sort động trong SQL, dùng allow-list cố định. Không đưa trực tiếp tên cột do người dùng gửi vào câu lệnh. Ngoài ra, cần xác thực quyền truy cập trên phạm vi dữ liệu trước khi thực hiện delete; bind parameter chỉ bảo vệ cấu trúc SQL, không thay thế kiểm tra authorization.

## 15. Lưu ý về hiệu năng khi xóa số lượng lớn

Xóa hàng loạt có thể tạo tải đáng kể cho database. Một lệnh delete tác động hàng triệu bản ghi có thể giữ lock lâu, tạo nhiều log, làm tăng replication lag và khiến các transaction khác phải chờ.

Một số chiến lược thường dùng:

- Xóa theo từng khoảng thời gian hoặc theo khóa để giới hạn số hàng mỗi batch.
- Bảo đảm index hỗ trợ điều kiện `WHERE`; nếu không, database có thể phải quét toàn bảng.
- Chạy cleanup ở thời điểm tải thấp và giới hạn concurrency.
- Theo dõi lock, transaction duration, WAL/redo log và replication lag theo hệ quản trị.
- Dùng partitioning và drop/detach partition cho dữ liệu hết hạn nếu workload phù hợp và database hỗ trợ.
- Với bảng audit lớn, cân nhắc retention policy và quy trình archive trước khi xóa vật lý.

Không nên gom một công việc cleanup rất lớn vào một transaction kéo dài nếu có thể chia thành các batch độc lập. Ngược lại, nếu các hàng phải được xóa như một đơn vị nghiệp vụ không thể tách, cần giữ transaction và thiết kế giới hạn tải phù hợp.

## 16. Chọn cách xóa theo yêu cầu

| Yêu cầu | Cách nên cân nhắc |
|---|---|
| Đã có entity, cần kiểm tra trạng thái hoặc version trước khi xóa | `repository.delete(entity)` hoặc `template.delete(entity)` |
| Chỉ có ID và không cần đọc entity | `repository.deleteById(id)` |
| Xóa một tập hàng theo thuộc tính entity | `template.delete(Type.class).matching(Query).all()` |
| Xóa theo SQL đặc thù hoặc cần `RETURNING` | `DatabaseClient` |
| Cần API Repository theo tên điều kiện | Derived delete query nếu phiên bản hỗ trợ; xác minh return type |
| Cần kiểm soát SQL trong Repository | `@Modifying` + `@Query` nếu phiên bản hỗ trợ |
| Cần giữ lịch sử thay vì xóa dữ liệu vật lý | Soft delete bằng thao tác update và query filter |
| Xóa hàng con khi xóa hàng cha | Foreign key `ON DELETE CASCADE` nếu phù hợp chính sách dữ liệu |

## 17. Quy trình triển khai một thao tác delete

Trước khi viết code, hãy xác định:

1. **Phạm vi:** xóa đúng một entity, theo ID, hay xóa nhiều hàng theo điều kiện?
2. **Quy tắc nghiệp vụ:** có cần kiểm tra trạng thái, quyền sở hữu, version hoặc chính sách retention không?
3. **Quan hệ:** foreign key nào đang tham chiếu tới hàng này? Dùng cascade, xóa con trước hay từ chối xóa?
4. **Kết quả:** API cần trả `204`, `404`, số hàng bị xóa hay danh sách ID đã xóa?
5. **Tính nguyên tử:** nhiều thao tác có phải nằm trong cùng reactive transaction không?
6. **Khối lượng:** số hàng dự kiến là bao nhiêu? Có cần batch, partition hoặc lịch cleanup không?
7. **Kiểm thử:** có test cho entity tồn tại/không tồn tại, version cũ, foreign key, điều kiện rỗng và concurrent delete không?

Với xóa theo entity, hãy ưu tiên kiểm tra nghiệp vụ và optimistic locking khi cần bảo vệ dữ liệu đã được người dùng đọc. Với xóa theo điều kiện, hãy thiết kế Criteria/SQL chặt chẽ, kiểm tra phạm vi hàng bị tác động và hiểu rằng thao tác bulk không đi qua từng entity. Kết hợp đúng API với transaction, constraint database và quy tắc xử lý lỗi giúp thao tác delete trong Spring Data R2DBC an toàn, dễ dự đoán và phù hợp với quy mô dữ liệu.
