# Khóa bi quan bằng SQL và phạm vi hỗ trợ của cơ sở dữ liệu

Khóa bi quan (pessimistic locking) là cách điều phối các transaction đồng thời bằng cách khóa bản ghi mà một transaction sắp đọc hoặc thay đổi. Transaction khác muốn cập nhật hoặc lấy khóa xung đột trên cùng dữ liệu phải chờ, nhận lỗi ngay hoặc bỏ qua hàng đang bị khóa, tùy cú pháp và chính sách của database.

Trong Spring Data R2DBC, khóa bi quan thường được yêu cầu bằng SQL đặc thù của hệ quản trị, chẳng hạn `SELECT ... FOR UPDATE`. Spring Data gửi câu lệnh qua driver R2DBC; database quyết định loại khóa, phạm vi khóa và thời điểm giải phóng. Để khóa bảo vệ một chuỗi thao tác đọc rồi ghi, câu lệnh lấy khóa và các thao tác tiếp theo phải nằm trong cùng reactive transaction.

## 1. Khóa bi quan giải quyết vấn đề gì?

Giả sử kho hàng còn 1 sản phẩm. Hai request cùng lúc muốn đặt mua một sản phẩm:

1. Transaction A đọc số lượng còn lại là 1.
2. Transaction B cũng đọc số lượng còn lại là 1.
3. A giảm số lượng xuống 0 và tạo đơn hàng.
4. B cũng giảm số lượng dựa trên giá trị cũ và tạo thêm đơn hàng.

Nếu không có cơ chế phối hợp phù hợp, hệ thống có thể bán vượt số lượng cho phép hoặc ghi đè dữ liệu của nhau.

Khóa bi quan cho phép transaction A khóa hàng inventory trước khi đọc/kiểm tra. Transaction B khi yêu cầu khóa cùng hàng phải chờ A commit/rollback hoặc xử lý theo chính sách như NOWAIT/SKIP LOCKED. Sau khi A hoàn tất, B đọc trạng thái mới và quyết định có thể tiếp tục hay không.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Database
    participant B as Transaction B
    A->>DB: SELECT inventory FOR UPDATE
    DB-->>A: Row locked, quantity = 1
    B->>DB: SELECT same row FOR UPDATE
    Note over B,DB: B waits for conflicting lock
    A->>DB: UPDATE quantity = 0
    A->>DB: COMMIT
    DB-->>B: Lock granted
    B->>DB: Read current quantity = 0
    DB-->>B: Insufficient stock
    B->>DB: ROLLBACK
~~~

Khóa bi quan hữu ích khi xung đột có khả năng cao, thao tác cần đọc rồi quyết định ghi dựa trên trạng thái hiện tại, hoặc nghiệp vụ yêu cầu một transaction giữ quyền thao tác trên hàng trong suốt một đoạn xử lý ngắn.

## 2. SELECT FOR UPDATE

Nhiều hệ quản trị quan hệ hỗ trợ cú pháp tương tự:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

`FOR UPDATE` yêu cầu database lấy khóa ghi trên các hàng được chọn. Transaction khác muốn cập nhật hoặc lấy khóa xung đột trên cùng hàng sẽ phải chờ hoặc xử lý theo tùy chọn khác.

Điểm cần nhớ:

- Khóa được áp dụng cho các hàng thực sự được truy vấn và khóa theo quy tắc của database.
- Khóa thường được giữ đến khi transaction commit hoặc rollback.
- Một truy vấn SELECT bình thường có thể vẫn đọc được dữ liệu tùy MVCC và database; khóa bi quan không nhất thiết chặn mọi lượt đọc.
- Nếu không có hàng nào khớp điều kiện, không có hàng dữ liệu tương ứng để khóa.
- Cú pháp và phạm vi khóa khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server, Oracle và các hệ quản trị khác.

Không nên coi `FOR UPDATE` là cú pháp SQL portable tuyệt đối. Hãy kiểm tra tài liệu và chạy integration test trên database thực tế của ứng dụng.

## 3. Vì sao phải nằm trong transaction?

Mục tiêu phổ biến của khóa bi quan là giữ quyền khóa trong lúc ứng dụng đọc, kiểm tra và cập nhật dữ liệu. Nếu câu SELECT chạy ở autocommit mode, transaction ngầm có thể kết thúc ngay sau câu lệnh; khóa khi đó được giải phóng trước khi ứng dụng chạy câu UPDATE tiếp theo.

Ví dụ không đủ để bảo vệ chuỗi thao tác:

~~~java
// Chỉ gọi một truy vấn khóa rồi kết thúc transaction/autocommit.
return inventoryRepository.findForUpdate(id)
        .flatMap(inventory -> inventoryRepository.save(decrease(inventory)));
~~~

Nếu hai thao tác không được thực thi trong cùng transaction, khóa từ câu SELECT có thể đã được giải phóng trước câu UPDATE.

Hãy bao toàn bộ pipeline bằng reactive transaction:

~~~java
@Transactional
public Mono<Inventory> reserve(Long id, int quantity) {
    return inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(inventory -> {
                if (inventory.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                Inventory changed = new Inventory(
                        inventory.id(),
                        inventory.available() - quantity
                );
                return inventoryRepository.save(changed);
            });
}
~~~

Với phương thức trả về `Mono` hoặc `Flux`, Spring sử dụng reactive transaction management khi có `ReactiveTransactionManager` phù hợp. Phương thức cần được gọi qua Spring proxy để `@Transactional` có hiệu lực; self-invocation trong cùng bean có thể bỏ qua proxy.

Có thể dùng `TransactionalOperator` để xác định ranh giới tường minh:

~~~java
public Mono<Inventory> reserve(Long id, int quantity) {
    Mono<Inventory> work = inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(inventory -> {
                if (inventory.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                return inventoryRepository.save(new Inventory(
                        inventory.id(),
                        inventory.available() - quantity
                ));
            });

    return transactionalOperator.transactional(work);
}
~~~

Transaction manager, repository và DatabaseClient phải sử dụng cùng `ConnectionFactory` phù hợp. Spring gắn tài nguyên transaction vào Reactor Context để các thao tác reactive trong cùng pipeline dùng kết nối thuộc transaction đó.

## 4. Khai báo truy vấn khóa trong Spring Data R2DBC

Có thể khai báo SQL trực tiếp trong repository bằng `@Query`:

~~~java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Query("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
    Mono<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

Đây là ví dụ theo cú pháp PostgreSQL và một số hệ quản trị hỗ trợ `FOR UPDATE`. Spring Data ánh xạ hàng trả về thành Inventory; driver/database thực thi phần khóa của SQL.

Spring Data R2DBC không nên được hiểu như một ORM có thể tự động khóa toàn bộ quan hệ entity. Ứng dụng phải thể hiện rõ hàng nào cần khóa bằng câu SQL và bảo đảm truy vấn nằm trong transaction. Không giả định một annotation kiểu JPA `@Lock` sẽ tự chuyển thành cú pháp tương thích cho mọi R2DBC driver và database.

Nếu cần SQL có tùy chọn như `NOWAIT`, `SKIP LOCKED` hoặc khóa một alias trong JOIN, dùng câu SQL tường minh và kiểm tra dialect của database.

## 5. Dùng DatabaseClient để điều khiển SQL khóa

`DatabaseClient` phù hợp khi câu truy vấn cần tham số động, JOIN hoặc cú pháp khóa cụ thể:

~~~java
public Mono<Inventory> lockInventory(Long id) {
    return databaseClient.sql("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
            .bind("id", id)
            .map((row, metadata) -> new Inventory(
                    row.get("id", Long.class),
                    row.get("available", Integer.class)
            ))
            .one();
}
~~~

Phương thức này chỉ tạo publisher. Câu SQL chạy khi publisher được subscribe. Để khóa được giữ trong lúc kiểm tra và ghi, caller phải bao cả `lockInventory(...)` lẫn câu UPDATE tiếp theo trong cùng transaction.

Không gọi `block()` để lấy hàng đã khóa rồi tiếp tục ở một luồng imperative khác; không tự `subscribe()` bên trong service. Những cách đó có thể tách truy vấn khỏi Reactor Context và transaction đang quản lý.

## 6. Ví dụ cập nhật tồn kho bằng khóa bi quan

Giả sử bảng:

~~~sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
~~~

Repository khóa hàng:

~~~java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Query("""
            SELECT id, available
            FROM inventory
            WHERE id = :id
            FOR UPDATE
            """)
    Mono<Inventory> findForUpdate(@Param("id") Long id);
}
~~~

Service:

~~~java
@Transactional
public Mono<Inventory> reserve(Long id, int quantity) {
    if (quantity <= 0) {
        return Mono.error(
                new IllegalArgumentException("Quantity must be positive")
        );
    }

    return inventoryRepository.findForUpdate(id)
            .switchIfEmpty(Mono.error(
                    new InventoryNotFoundException(id)
            ))
            .flatMap(current -> {
                if (current.available() < quantity) {
                    return Mono.error(
                            new InsufficientStockException(id)
                    );
                }

                return inventoryRepository.save(new Inventory(
                        current.id(),
                        current.available() - quantity
                ));
            });
}
~~~

Transaction giữ khóa từ lúc SELECT FOR UPDATE đến khi thao tác save và các bước khác trong transaction hoàn tất. Nếu số lượng không đủ và publisher phát lỗi, transaction được rollback và khóa được giải phóng khi rollback hoàn tất.

Ví dụ giả định entity Inventory và repository mapping đúng với schema. Nếu entity có `@Version`, cần kết hợp hiểu biết về optimistic locking; khóa bi quan và version có thể cùng tồn tại nhưng phục vụ hai cơ chế kiểm soát khác nhau.

## 7. Một câu UPDATE có điều kiện có thể thay thế khóa tường minh

Không phải mọi bài toán cạnh tranh đều cần SELECT FOR UPDATE. Với thao tác đơn giản như trừ tồn kho, một câu UPDATE nguyên tử có điều kiện thường ngắn hơn:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE id = :id
  AND available >= :quantity;
~~~

Repository:

~~~java
@Modifying
@Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE id = :id
          AND available >= :quantity
        """)
Mono<Integer> reserveIfAvailable(
        @Param("id") Long id,
        @Param("quantity") int quantity
);
~~~

Database thực hiện câu lệnh như một thao tác nguyên tử. Nếu hàng tồn tại và đủ số lượng, một hàng được cập nhật; nếu không, số hàng bị tác động bằng 0. Các transaction cạnh tranh trên cùng hàng được database điều phối bằng cơ chế khóa nội bộ của lệnh UPDATE.

Cách này phù hợp khi điều kiện nghiệp vụ có thể thể hiện trong một câu lệnh. Khóa bi quan tường minh hữu ích hơn khi phải đọc nhiều trường, thực hiện một số kiểm tra hoặc cập nhật nhiều bảng dựa trên trạng thái đã khóa.

Không nên dùng SELECT FOR UPDATE chỉ vì muốn “an toàn hơn” nếu một câu UPDATE có điều kiện đã biểu đạt đầy đủ quy tắc. Ít thao tác và transaction ngắn thường dễ mở rộng hơn.

## 8. Các mức khóa trong PostgreSQL

PostgreSQL hỗ trợ nhiều chế độ khóa hàng:

| Cú pháp | Ý nghĩa tổng quát |
| --- | --- |
| `FOR UPDATE` | Khóa mạnh cho thao tác cập nhật/xóa hàng |
| `FOR NO KEY UPDATE` | Khóa cập nhật nhẹ hơn khi không thay đổi khóa tham chiếu |
| `FOR SHARE` | Khóa chia sẻ, xung đột với một số thao tác ghi/khóa |
| `FOR KEY SHARE` | Bảo vệ khóa hàng khỏi thay đổi/xóa theo các quy tắc khóa của PostgreSQL |

Thông thường, `FOR UPDATE` là lựa chọn dễ hiểu nhất khi transaction sắp thay đổi hàng đã đọc. Các chế độ nhẹ hơn có thể tăng concurrency nhưng cần hiểu ma trận xung đột khóa của PostgreSQL.

Có thể giới hạn bảng bị khóa trong truy vấn JOIN bằng `OF`:

~~~sql
SELECT i.id, i.available, p.name
FROM inventory i
JOIN product p ON p.id = i.product_id
WHERE i.id = :id
FOR UPDATE OF i;
~~~

Trong PostgreSQL, `OF i` chỉ định khóa hàng của alias inventory. Nếu bỏ `OF`, các hàng từ những bảng phù hợp trong truy vấn có thể cũng bị khóa theo quy tắc của câu lệnh. Hãy chỉ khóa những hàng cần thiết để giảm tranh chấp.

## 9. NOWAIT và SKIP LOCKED trong PostgreSQL

### NOWAIT

`NOWAIT` yêu cầu database không chờ khi hàng cần khóa đang bị transaction khác giữ khóa xung đột:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE NOWAIT;
~~~

Nếu không lấy được khóa ngay, database trả lỗi khóa đang bận thay vì đợi. Ứng dụng có thể chuyển lỗi thành phản hồi “đang được xử lý” hoặc retry có backoff nếu nghiệp vụ cho phép.

### SKIP LOCKED

`SKIP LOCKED` bỏ qua những hàng đang bị khóa xung đột:

~~~sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
~~~

Đây là cách thường dùng cho nhiều worker cùng lấy công việc từ một hàng đợi database. Worker thứ hai không phải chờ những hàng worker thứ nhất đã khóa; nó lấy các hàng READY khác.

`SKIP LOCKED` tạo một góc nhìn không đầy đủ về dữ liệu: hàng đang bị khóa bị bỏ qua, không có nghĩa chúng không tồn tại. Không dùng nó cho màn hình cần danh sách đầy đủ hoặc truy vấn báo cáo nhất quán.

Khi dùng để nhận việc, worker cần cập nhật trạng thái hàng đã khóa thành RUNNING hoặc gán owner trước khi commit. Nếu chỉ SELECT rồi commit, khóa được giải phóng và worker khác có thể chọn lại cùng công việc.

## 10. Mẫu lấy việc từ hàng đợi bằng SKIP LOCKED

Ví dụ PostgreSQL:

~~~sql
SELECT id, payload
FROM job
WHERE status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
~~~

Trong cùng transaction, cập nhật các hàng vừa lấy:

~~~sql
UPDATE job
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP,
    worker_id = :workerId
WHERE id = :id;
~~~

Service có thể nối thao tác:

~~~java
@Transactional
public Flux<Job> claimJobs(String workerId) {
    return jobRepository.findReadyForUpdateSkipLocked()
            .flatMap(job -> jobRepository.markRunning(
                    job.id(),
                    workerId
            ).thenReturn(job));
}
~~~

Đoạn code minh họa yêu cầu hai repository query cùng tham gia một reactive transaction. Trong thực tế, nên trả về dữ liệu đã được cập nhật hoặc có bước xác nhận kết quả update, và thiết kế batch claim theo số lượng giới hạn.

Sau khi transaction commit, các hàng đã đổi trạng thái RUNNING nên worker khác không còn chọn chúng theo điều kiện READY. Cần có cơ chế lease/timeout hoặc phục hồi job bị worker chết bỏ dở; khóa database không thay thế cơ chế quản lý vòng đời công việc dài hạn.

## 11. Hỗ trợ và cú pháp trong các hệ quản trị khác nhau

Khóa bi quan không có một cú pháp SQL duy nhất được mọi database hỗ trợ giống nhau. Bảng sau tóm tắt những mẫu thường gặp; phiên bản, storage engine và isolation level có thể ảnh hưởng hành vi.

| Database | Cú pháp phổ biến | Lưu ý |
| --- | --- | --- |
| PostgreSQL | `SELECT ... FOR UPDATE`, `NOWAIT`, `SKIP LOCKED` | Khóa hàng theo MVCC; có các chế độ khóa và `FOR UPDATE OF alias` |
| MySQL / InnoDB | `SELECT ... FOR UPDATE`, `FOR SHARE` | Khóa phụ thuộc index, isolation và next-key/gap locking |
| SQL Server | `WITH (UPDLOCK, ...)` | Dùng table hints; không dùng cú pháp PostgreSQL FOR UPDATE |
| Oracle | `SELECT ... FOR UPDATE`, `NOWAIT`, `WAIT n`, `SKIP LOCKED` | Hỗ trợ các tùy chọn chờ khóa theo cú pháp Oracle |
| SQLite | Không có SELECT FOR UPDATE theo mô hình row lock thông thường | Cơ chế khóa ở mức database/file và transaction khác biệt |

R2DBC driver không tự làm cho database hỗ trợ một cú pháp mà server không có. Driver truyền SQL và chuyển kết quả/lỗi qua SPI; cú pháp khóa phải phù hợp hệ quản trị và phiên bản đang chạy.

## 12. MySQL và InnoDB

Với InnoDB, có thể khóa hàng bằng:

~~~sql
SELECT id, available
FROM inventory
WHERE id = ?
FOR UPDATE;
~~~

Một transaction khác muốn cập nhật hoặc lấy khóa xung đột trên cùng hàng sẽ phải chờ. Khóa được giữ đến khi transaction kết thúc.

MySQL 8.0 hỗ trợ các tùy chọn thường dùng:

- `NOWAIT`: trả lỗi ngay nếu khóa không thể lấy tức thời.
- `SKIP LOCKED`: bỏ qua hàng đang bị khóa, phù hợp với worker queue.
- `FOR SHARE`: lấy khóa chia sẻ; các phiên bản cũ có thể dùng cú pháp `LOCK IN SHARE MODE`.

InnoDB có thể sử dụng record lock, gap lock hoặc next-key lock tùy truy vấn, index và isolation level. Với điều kiện range ở mức `REPEATABLE READ`, phạm vi khóa có thể bao gồm khoảng trống giữa các index record để ngăn phantom insert theo semantics của InnoDB.

Một truy vấn tìm theo khóa chính duy nhất thường có phạm vi khóa hẹp hơn truy vấn range thiếu index. Vì vậy, index không chỉ ảnh hưởng tốc độ; nó còn ảnh hưởng số hàng/khoảng dữ liệu bị khóa và khả năng cạnh tranh.

Hãy kiểm tra engine thực tế là InnoDB. Các engine khác của MySQL có thể có hành vi transaction và khóa khác.

## 13. SQL Server

SQL Server sử dụng table hints để yêu cầu chiến lược khóa:

~~~sql
SELECT id, available
FROM inventory WITH (UPDLOCK, ROWLOCK)
WHERE id = @id;
~~~

- `UPDLOCK` yêu cầu lấy update lock khi đọc và giữ khóa đến khi transaction kết thúc theo quy tắc transaction.
- `ROWLOCK` gợi ý sử dụng khóa mức hàng, nhưng SQL Server không bảo đảm luôn giữ đúng granularities được yêu cầu.
- `HOLDLOCK` có semantics tương đương SERIALIZABLE cho tham chiếu bảng đó trong phạm vi câu lệnh/transaction theo tài liệu SQL Server.
- `READPAST` có thể bỏ qua một số hàng đang bị khóa, thường dùng cho queue pattern; cần hiểu giới hạn theo isolation, loại khóa và cấu hình như READ_COMMITTED_SNAPSHOT.

Ví dụ không thể thay nguyên văn `FOR UPDATE` của PostgreSQL bằng SQL Server. Hãy dùng cú pháp hint phù hợp và kiểm thử với isolation level của ứng dụng.

## 14. Oracle

Oracle hỗ trợ:

~~~sql
SELECT id, available
FROM inventory
WHERE id = :id
FOR UPDATE;
~~~

Các lựa chọn chờ khóa phổ biến:

- `NOWAIT`: không chờ khóa; trả lỗi nếu hàng đang bị khóa.
- `WAIT n`: chờ tối đa số giây chỉ định.
- `SKIP LOCKED`: bỏ qua hàng đang bị khóa.

Ví dụ:

~~~sql
SELECT id, payload
FROM job
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

Oracle cũng có các quy tắc riêng về khóa khi dùng JOIN, view, phân trang và truy vấn con. Kiểm tra tài liệu đúng phiên bản Oracle trước khi áp dụng mẫu SQL trong hệ thống thật.

## 15. Phạm vi khóa: hàng, trang, bảng và khoảng khóa

Tên `FOR UPDATE` thường gợi ý khóa hàng, nhưng phạm vi thực tế phụ thuộc database và execution plan:

- **Row/record lock:** khóa các hàng được truy vấn.
- **Page lock:** khóa một trang dữ liệu hoặc index page.
- **Table lock:** khóa toàn bảng hoặc mức bảng trong một số thao tác.
- **Gap/next-key lock:** khóa khoảng trống trong index để hạn chế insert vào khoảng đó.
- **Predicate/range protection:** ngăn transaction khác tạo hàng làm thay đổi kết quả của một điều kiện theo isolation semantics.

PostgreSQL dùng MVCC và row-level lock cho các hàng được khóa; nó vẫn có table-level lock đi kèm câu lệnh. InnoDB có gap/next-key locking trong một số trường hợp. SQL Server có thể nâng cấp (lock escalation) từ row/page lên table lock khi cần.

Do đó, không nên giả định một câu lệnh chỉ khóa đúng một hàng nếu điều kiện WHERE có thể khớp nhiều hàng hoặc truy vấn dùng range. Hãy xem execution plan, index và tài liệu của database.

## 16. Index ảnh hưởng phạm vi và thời gian giữ khóa

Ví dụ:

~~~sql
SELECT id, status
FROM job
WHERE status = 'READY'
ORDER BY created_at
FOR UPDATE;
~~~

Nếu không có index phù hợp, database có thể phải quét nhiều hàng để tìm những hàng READY. Tùy engine, điều này có thể làm tăng công việc và phạm vi khóa hoặc thời gian giữ khóa.

Một index có thể phù hợp:

~~~sql
CREATE INDEX idx_job_status_created_id
    ON job(status, created_at, id);
~~~

Index cần được chọn dựa trên execution plan và workload thực tế. Index giúp truy vấn tìm hàng nhanh hơn nhưng cũng tăng chi phí insert/update/delete và dung lượng lưu trữ.

## 17. Isolation level và khóa bi quan

Isolation level và explicit lock có liên quan nhưng không giống nhau:

- Isolation level xác định các hiện tượng đọc/ghi mà database cho phép giữa các transaction.
- Explicit pessimistic lock yêu cầu khóa cụ thể trên hàng hoặc tài nguyên.
- Database có thể dùng khóa nội bộ dù ứng dụng không viết `FOR UPDATE`, ví dụ khi chạy UPDATE.
- Một mức isolation cao không có nghĩa mọi hàng đọc đều được khóa theo cách ứng dụng mong muốn.

Với PostgreSQL, `READ COMMITTED` thường là mặc định; `SELECT FOR UPDATE` khóa hàng và nếu phải chờ transaction khác cập nhật hàng, nó tiếp tục xử lý phiên bản mới phù hợp sau khi transaction kia hoàn tất theo semantics PostgreSQL.

Với InnoDB, `REPEATABLE READ` thường là mặc định; range query có thể tạo next-key lock. Hành vi thay đổi nếu dùng `READ COMMITTED` hoặc truy vấn đi qua index khác.

Hãy chọn isolation theo yêu cầu nhất quán tổng thể và dùng explicit lock khi cần bảo vệ một hàng trong một quy trình cụ thể. Không dùng isolation SERIALIZABLE như giải pháp thay thế máy móc cho mọi truy vấn khóa.

## 18. NOWAIT, timeout và xử lý lỗi

Khi một transaction khác giữ khóa, request lấy khóa có thể chờ. Nếu chờ quá lâu, hệ thống tiêu tốn connection, giữ request và có thể làm hàng đợi tăng lên.

Các lựa chọn:

- Dùng `NOWAIT` khi muốn thất bại ngay nếu hàng bận.
- Dùng `WAIT n` hoặc lock timeout nếu database hỗ trợ.
- Cấu hình lock wait timeout phù hợp ở cấp session/transaction/database nếu cần.
- Giới hạn thời gian toàn bộ request và thời gian transaction.
- Ghi nhận lock wait, timeout và deadlock để tìm điểm nóng.

Lỗi lock timeout hoặc deadlock thường được truyền qua publisher dưới dạng lỗi driver/database. Ứng dụng có thể chuyển thành lỗi nghiệp vụ có thể retry, nhưng chỉ retry khi thao tác an toàn và có giới hạn.

Không nên retry ngay lập tức không giới hạn. Nhiều request cùng retry có thể làm tình trạng tranh chấp nghiêm trọng hơn. Dùng backoff, jitter và tổng deadline của request.

## 19. Deadlock và thứ tự lấy khóa

Deadlock xảy ra khi các transaction giữ khóa mà transaction kia cần, tạo thành chu trình chờ.

Ví dụ:

1. A khóa hàng 1.
2. B khóa hàng 2.
3. A chờ hàng 2.
4. B chờ hàng 1.

Database phát hiện chu trình và chọn một transaction làm deadlock victim để rollback. Ứng dụng cần xử lý lỗi và có thể retry transaction bị hủy nếu nghiệp vụ cho phép.

Một biện pháp giảm deadlock là lấy khóa theo cùng thứ tự ở mọi luồng:

~~~sql
SELECT id, balance
FROM account
WHERE id IN (:firstId, :secondId)
ORDER BY id
FOR UPDATE;
~~~

Ví dụ cần khóa hai tài khoản theo ID tăng dần. Khi mọi transaction tuân theo cùng thứ tự, khả năng tạo chu trình chờ giảm. Cú pháp bind collection và cách khóa khi dùng IN cần được kiểm tra theo driver/database; với danh sách động, có thể truy vấn theo từng ID đã sắp xếp trong cùng transaction.

Các biện pháp khác:

- Giữ transaction ngắn.
- Chỉ khóa hàng thực sự cần thiết.
- Tạo index phù hợp để tránh quét rộng.
- Không gọi dịch vụ ngoài khi đang giữ khóa.
- Không thực hiện thao tác người dùng tương tác lâu trong transaction.

## 20. Không giữ khóa khi gọi hệ thống bên ngoài

Một anti-pattern là:

~~~java
return transactionalOperator.transactional(
        inventoryRepository.findForUpdate(id)
                .flatMap(inventory ->
                        paymentClient.authorize(order)
                                .then(inventoryRepository.save(
                                        decrease(inventory)
                                ))
                )
);
~~~

Transaction giữ khóa trong lúc chờ network call thanh toán. Nếu dịch vụ ngoài chậm, khóa và connection bị giữ lâu; nếu thanh toán thành công nhưng database rollback, hai hệ thống có thể không đồng bộ.

Thiết kế tốt hơn thường là:

1. Thực hiện thao tác database ngắn trong transaction.
2. Ghi trạng thái hoặc outbox event.
3. Commit transaction để giải phóng khóa.
4. Gọi hệ thống ngoài sau commit qua tiến trình phù hợp.
5. Dùng idempotency và quy trình bù trừ khi cần.

Nếu nghiệp vụ đòi hỏi quy trình phân tán, cân nhắc saga hoặc transactional outbox thay vì giữ row lock trong toàn bộ thời gian giao tiếp từ xa.

## 21. Khóa bi quan và khóa lạc quan

| Tiêu chí | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Cơ chế | Khóa tài nguyên trước khi thay đổi | Kiểm tra dữ liệu chưa đổi khi ghi |
| Cách thường dùng | `SELECT FOR UPDATE`, locking hints | Cột version và điều kiện version |
| Khi xung đột | Transaction khác chờ, bỏ qua hoặc lỗi | Update thất bại khi version không còn khớp |
| Chi phí | Giữ khóa và connection trong transaction | Có thể phải xử lý/retry xung đột |
| Phù hợp | Xung đột thường xuyên, đoạn đọc-sửa cần độc quyền | Xung đột ít, không muốn giữ khóa khi đọc |

Ví dụ optimistic locking:

~~~sql
UPDATE inventory
SET available = :newAvailable,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số hàng cập nhật bằng 0, có thể có transaction khác đã thay đổi hàng. Cách này không giữ khóa từ lúc đọc ban đầu đến lúc ghi, nhưng vẫn dựa vào tính nguyên tử của UPDATE.

Có thể kết hợp hai cơ chế khi nghiệp vụ cần, nhưng cần tránh làm phức tạp không cần thiết. Chọn một chiến lược dựa trên mức tranh chấp, độ dài transaction và cách xử lý xung đột.

## 22. Kiểm thử khóa bi quan với hai transaction

Unit test đơn thuần không chứng minh database thật giữ khóa đúng cách. Cần integration test với database và driver mục tiêu:

1. Tạo một hàng dữ liệu dùng chung.
2. Transaction A bắt đầu và chạy SELECT FOR UPDATE.
3. Giữ transaction A mở trong lúc chưa commit.
4. Transaction B thử khóa cùng hàng.
5. Xác nhận B chờ, nhận NOWAIT error hoặc bỏ qua hàng với SKIP LOCKED theo kịch bản.
6. Cho A commit/rollback.
7. Xác nhận B tiếp tục hoặc nhận trạng thái đúng.

Có thể dùng `StepVerifier`, hai publisher độc lập và các tín hiệu điều phối trong test. Cần tránh dùng sleep dài không ổn định; ưu tiên latch/barrier hoặc cơ chế đồng bộ test có deadline rõ ràng.

Các tình huống nên kiểm thử:

- Khóa hàng theo ID duy nhất.
- Hai transaction cùng cập nhật một hàng.
- NOWAIT khi hàng đang bị khóa.
- SKIP LOCKED khi nhiều worker lấy job.
- Rollback giải phóng khóa.
- Deadlock hoặc lock timeout.
- Hành vi cancellation.
- Phạm vi khóa của JOIN hoặc range query nếu nghiệp vụ phụ thuộc vào đó.

Chạy test trên cùng engine/version với production. Embedded database có thể không hỗ trợ cùng cú pháp hoặc semantics khóa.

## 23. Các lỗi thường gặp

1. **Dùng SELECT FOR UPDATE ngoài transaction.** Khóa có thể được giải phóng ngay sau câu SELECT/autocommit.
2. **Chỉ khóa khi đọc nhưng update ở transaction khác.** Khóa không bảo vệ chuỗi thao tác nếu không cùng transaction.
3. **Cho rằng mọi SELECT đều bị chặn.** MVCC và loại khóa quyết định reader nào bị ảnh hưởng.
4. **Dùng cú pháp PostgreSQL trên SQL Server hoặc SQLite.** Khóa bi quan không portable tuyệt đối.
5. **Giả định R2DBC driver tự tạo lock.** SQL/database quyết định cơ chế; driver chỉ truyền lệnh và kết quả.
6. **Không kiểm tra cùng ConnectionFactory.** Repository có thể không tham gia transaction mà operator quản lý.
7. **Giữ khóa trong lúc gọi HTTP.** Transaction kéo dài, connection bị giữ và deadlock dễ xảy ra hơn.
8. **Khóa quá nhiều hàng.** Điều kiện thiếu index hoặc quá rộng làm tăng contention.
9. **Bỏ qua lock timeout và deadlock.** Request có thể chờ lâu hoặc thất bại không được xử lý.
10. **Dùng SKIP LOCKED cho danh sách cần đầy đủ.** Kết quả có thể thiếu hàng đang bị khóa.
11. **Chỉ dùng kiểm tra ở Java để tránh ghi trùng.** Cần constraint và transaction để bảo vệ cạnh tranh.
12. **Dùng pessimistic lock cho một UPDATE đơn giản.** Một câu UPDATE có điều kiện có thể đã đủ và hiệu quả hơn.

## Quy tắc lựa chọn nhanh

- Dùng `SELECT ... FOR UPDATE` khi cần đọc rồi kiểm tra/cập nhật cùng hàng trong một transaction.
- Dùng `@Transactional` reactive hoặc `TransactionalOperator` để giữ lock qua toàn bộ pipeline.
- Dùng `NOWAIT` khi không muốn chờ hàng đang bận và có thể xử lý lỗi ngay.
- Dùng `SKIP LOCKED` cho worker queue hoặc công việc chia sẻ, không dùng cho truy vấn cần đầy đủ dữ liệu.
- Dùng `DatabaseClient` hoặc `@Query` để viết cú pháp khóa đúng dialect.
- Kiểm tra database, phiên bản, engine, isolation level, index và driver.
- Khóa ít hàng nhất có thể, lấy khóa theo thứ tự nhất quán và giữ transaction ngắn.
- Dùng một câu UPDATE có điều kiện nếu quy tắc nghiệp vụ có thể được biểu đạt nguyên tử trong SQL.
- Kiểm thử bằng nhiều transaction đồng thời trên database mục tiêu.

Khóa bi quan bằng SQL cho phép transaction giữ quyền thao tác trên những hàng cần bảo vệ, nhưng hiệu quả phụ thuộc vào transaction boundary và cách database triển khai khóa. Trong Spring Data R2DBC, hãy viết truy vấn khóa tường minh, bao cả chuỗi đọc-sửa bằng reactive transaction và dùng cùng ConnectionFactory. Cú pháp như FOR UPDATE, NOWAIT và SKIP LOCKED khác nhau giữa các hệ quản trị; phạm vi khóa còn phụ thuộc index, isolation level và execution plan. Giữ transaction ngắn, tránh lời gọi từ xa trong lúc khóa và kiểm thử trên database thực tế để kiểm soát concurrency an toàn.
