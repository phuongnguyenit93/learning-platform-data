# Truy vấn cập nhật hoặc xóa bằng @Modifying

## 1. Vì sao cần @Modifying?

Spring Data R2DBC cho phép khai báo câu SQL trực tiếp trên repository bằng `@Query`. Với truy vấn đọc, Spring Data thực thi SQL rồi ánh xạ các hàng kết quả thành entity hoặc projection. Nhưng với câu lệnh `UPDATE` hoặc `DELETE`, mục tiêu chính là thay đổi dữ liệu trong database; ứng dụng thường cần biết thao tác hoàn tất và có bao nhiêu hàng bị ảnh hưởng.

Annotation `@Modifying` đánh dấu một phương thức repository dùng câu query có tác dụng thay đổi dữ liệu. Nó cho Spring Data biết cần thực thi câu lệnh theo nhánh modifying query, thay vì xử lý kết quả như truy vấn đọc entity thông thường.

Các trường hợp thường dùng:

- Cập nhật trạng thái nhiều bản ghi theo điều kiện.
- Điều chỉnh một vài cột mà không cần tải entity về rồi gọi `save`.
- Xóa vật lý các bản ghi thỏa điều kiện.
- Thực hiện soft delete bằng cách cập nhật cờ hoặc thời điểm xóa.
- Chạy một câu lệnh SQL cụ thể mà derived query không diễn đạt được.

`@Modifying` thường đi cùng `@Query` trên repository reactive. Câu SQL được thực thi khi publisher được subscribe, và kết quả thường là số hàng bị ảnh hưởng hoặc một tín hiệu hoàn tất không có giá trị.

## 2. Cấu trúc một phương thức @Modifying

Ví dụ repository cập nhật trạng thái task:

```java
import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface TaskRepository
        extends ReactiveCrudRepository<Task, Long> {

    @Modifying
    @Query("UPDATE task SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(
            @Param("id") Long id,
            @Param("status") String status);
}
```

Các thành phần:

- `@Query` chứa câu SQL mà repository sẽ thực thi.
- `@Modifying` cho biết câu query thay đổi dữ liệu.
- `@Param` liên kết tham số method với named parameter trong SQL.
- `Mono<Integer>` phát ra số hàng được báo cáo là đã bị ảnh hưởng, sau đó hoàn tất.

Tên bảng và tên cột trong `@Query` là tên SQL thực tế trong schema. Mapping metadata của entity không tự đổi tên bảng/cột trong một câu SQL viết tường minh. Nếu bảng là `task_item` hoặc cột là `task_status`, câu query phải dùng đúng tên đó.

Không dùng `@Modifying` cho một truy vấn `SELECT` thông thường. Với truy vấn đọc, bỏ annotation và khai báo kiểu trả về entity/projection phù hợp.

## 3. Cập nhật dữ liệu bằng @Modifying

Giả sử bảng `customer` có các cột `id`, `email_address`, `status` và `updated_at`. Có thể cập nhật trạng thái của một customer bằng:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    @Modifying
    @Query("UPDATE customer SET status = :status WHERE id = :id")
    Mono<Integer> updateStatus(
            @Param("id") Long id,
            @Param("status") String status);
}
```

Sử dụng trong service:

```java
public Mono<String> changeStatus(Long id, String status) {
    return customerRepository.updateStatus(id, status)
            .map(rows -> rows == 0
                    ? "No customer was updated"
                    : "Updated " + rows + " customer(s)");
}
```

Nếu `id` tồn tại và câu lệnh cập nhật tác động một hàng, publisher thường phát `1`. Nếu không có hàng phù hợp, nó có thể phát `0`. Nếu câu SQL lỗi, publisher kết thúc bằng error signal thay vì phát số hàng.

Số hàng được trả về là kết quả do database/driver báo cáo. Cách database định nghĩa “rows affected” có thể khác nhau, chẳng hạn có hệ quản trị báo số hàng khớp điều kiện, có hệ quản trị có thể phân biệt số hàng thực sự thay đổi. Nếu câu lệnh gán lại cùng giá trị cũ, hãy kiểm tra semantics của hệ quản trị và driver thay vì suy luận rằng kết quả nhất định bằng 0 hoặc 1.

### 3.1. Cập nhật nhiều hàng

Một câu lệnh có thể cập nhật nhiều bản ghi theo điều kiện:

```java
@Modifying
@Query("UPDATE task SET status = :target WHERE status = :source")
Mono<Integer> moveTasksToStatus(
        @Param("source") String source,
        @Param("target") String target);
```

Phương thức này không tải từng `Task` về Java. Database thực hiện một câu UPDATE theo điều kiện và trả thông tin số hàng bị ảnh hưởng. Đây là cách phù hợp khi thay đổi cùng một cột theo một quy tắc đơn giản trên nhiều hàng.

Ví dụ service:

```java
public Mono<Integer> archiveCompletedTasks() {
    return taskRepository.moveTasksToStatus("COMPLETED", "ARCHIVED");
}
```

Với câu lệnh bulk update, cần bảo đảm điều kiện `WHERE` đủ chặt. Một lỗi thiếu điều kiện có thể cập nhật toàn bộ bảng. Nếu câu lệnh có phạm vi rộng, hãy cân nhắc kiểm tra trước trên môi trường test/staging và ghi nhận số hàng bị ảnh hưởng trong log nghiệp vụ.

## 4. Xóa dữ liệu bằng @Modifying

Có thể khai báo câu DELETE tùy chỉnh:

```java
public interface TaskRepository
        extends ReactiveCrudRepository<Task, Long> {

    @Modifying
    @Query("DELETE FROM task WHERE status = :status")
    Mono<Integer> deleteByStatus(@Param("status") String status);
}
```

Sử dụng:

```java
Mono<Integer> deleted = taskRepository.deleteByStatus("ARCHIVED");
```

Kết quả cho biết số hàng được database/driver báo cáo là bị ảnh hưởng. Phương thức này hữu ích cho việc dọn dữ liệu theo điều kiện hoặc xóa các bản ghi hết hạn.

### 4.1. Xóa theo ID

Nếu chỉ cần xóa theo ID, `ReactiveCrudRepository` đã cung cấp `deleteById(id)`:

```java
Mono<Void> deleteById(Long id);
```

Phương thức CRUD này trả `Mono<Void>` và không cung cấp số hàng bị xóa. Nếu nghiệp vụ cần số hàng ảnh hưởng, một query method `@Modifying` có thể phù hợp:

```java
@Modifying
@Query("DELETE FROM task WHERE id = :id")
Mono<Integer> deleteAndReport(@Param("id") Long id);
```

### 4.2. Xóa theo điều kiện và khóa ngoại

Khi xóa một hàng được các bảng khác tham chiếu, database có thể:

- Cho phép xóa nếu không có hàng tham chiếu.
- Từ chối do foreign key constraint.
- Xóa hàng con theo `ON DELETE CASCADE`.
- Cập nhật khóa ngoại theo hành vi như `SET NULL`, nếu schema đã cấu hình.

`@Modifying` không tự xử lý quan hệ cascade ở mức object graph như một ORM có persistence context. Database áp dụng constraint và hành vi được định nghĩa trong schema. Hãy thiết kế foreign key và thứ tự thao tác phù hợp với mô hình dữ liệu.

## 5. Kiểu trả về và ý nghĩa kết quả

Đối với modifying query reactive, thường chọn một trong hai kiểu kết quả:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `Mono<Integer>` | Phát số hàng bị ảnh hưởng theo kết quả thực thi, sau đó hoàn tất |
| `Mono<Void>` | Chỉ quan tâm thao tác hoàn tất bình thường hay kết thúc bằng lỗi |

Ví dụ khi cần số hàng:

```java
@Modifying
@Query("UPDATE customer SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(Long id, String status);
```

Ví dụ khi không cần số hàng:

```java
@Modifying
@Query("DELETE FROM audit_log WHERE created_at < :cutoff")
Mono<Void> deleteOldAuditLogs(OffsetDateTime cutoff);
```

Hãy kiểm tra kiểu trả về được hỗ trợ trong phiên bản Spring Data R2DBC của dự án. Với các modifying query reactive, dùng wrapper reactive phù hợp thay vì khai báo một giá trị đồng bộ rồi mong repository thực thi ngay.

`Mono<Integer>` có thể phát `0` mà vẫn hoàn tất bình thường. Điều này khác với `Mono.empty()`: một modifying query có kiểu số thường trả số hàng, còn empty có nghĩa publisher không phát phần tử. Nếu cần biết chính xác thao tác có tác động dữ liệu hay không, hãy kiểm tra giá trị số được phát ra.

Với `Mono<Void>`, không thể suy ra số hàng bị ảnh hưởng. Publisher hoàn tất chỉ xác nhận câu lệnh không phát lỗi theo hợp đồng thực thi.

## 6. So sánh @Modifying với derived delete query

Spring Data có thể suy ra thao tác xóa từ tên method, ví dụ:

```java
Mono<Void> deleteByStatus(String status);
```

Phương thức derived delete được Spring Data nhận diện dựa trên tên method. Không cần `@Query` hoặc `@Modifying` nếu chỉ cần hành vi mà query derivation hỗ trợ.

Trong khi đó:

```java
@Modifying
@Query("DELETE FROM task WHERE status = :status")
Mono<Integer> deleteAndCountByStatus(@Param("status") String status);
```

cho phép viết SQL tường minh và chọn kiểu kết quả phù hợp với API modifying query. Cách này hữu ích khi cần điều kiện SQL đặc thù, biểu thức database riêng hoặc số hàng ảnh hưởng.

Chọn theo tình huống:

| Tình huống | Lựa chọn |
| --- | --- |
| Xóa theo một thuộc tính đơn giản được query derivation hỗ trợ | Derived `deleteBy...` |
| Xóa theo SQL cụ thể hoặc biểu thức đặc thù | `@Query` + `@Modifying` |
| Cập nhật một/vài cột theo SQL tường minh | `@Query` + `@Modifying` |
| Cần trả số hàng bị ảnh hưởng với SQL tự viết | `@Query` + `@Modifying` với kiểu số được hỗ trợ |
| Cần tải entity, kiểm tra invariant rồi thay đổi | `findBy...` + domain method + `save` |

## 7. Bind tham số an toàn

Named parameter giúp câu SQL dễ đọc và tránh nối dữ liệu đầu vào trực tiếp vào câu lệnh:

```java
@Modifying
@Query("UPDATE customer SET status = :status WHERE email_address = :email")
Mono<Integer> updateByEmail(
        @Param("email") String email,
        @Param("status") String status);
```

Spring Data R2DBC bind giá trị tham số thông qua cơ chế của driver. Không viết:

```java
// Không an toàn: dữ liệu đầu vào bị ghép trực tiếp vào SQL
String sql = "UPDATE customer SET status = '" + status + "' WHERE email_address = '" + email + "'";
```

Ghép chuỗi như trên có thể tạo SQL injection và lỗi cú pháp khi giá trị chứa dấu nháy. Hãy dùng named parameter và `@Param`.

### 7.1. Không thể bind tên bảng hoặc tên cột như giá trị

Parameter binding dành cho giá trị dữ liệu, không thay thế identifier SQL. Ví dụ, `SET :column = :value` không có nghĩa `:column` sẽ được parse thành tên cột. Nếu cần chọn cột động, hãy dùng danh sách identifier được whitelist trong code và xây dựng câu SQL từ các lựa chọn đã kiểm soát; không lấy tên bảng/cột trực tiếp từ request.

### 7.2. Tham số null

Nếu một tham số có thể là `null`, cần xác định câu SQL có ý nghĩa gì. Điều kiện `column = NULL` không tương đương `column IS NULL` trong SQL ba giá trị logic. Nếu cần cập nhật cột thành NULL, bind null vào phần SET có thể phù hợp nếu schema cho phép. Nếu cần lọc các hàng có cột NULL, hãy dùng điều kiện `IS NULL` tường minh hoặc thiết kế các nhánh query phù hợp.

Không nên giả định mọi phiên bản driver có thể suy luận kiểu cho tham số null trong mọi ngữ cảnh. Khi cần, dùng API bind có khai báo kiểu hoặc câu SQL riêng theo cách được driver hỗ trợ.

## 8. Cập nhật nhiều cột và biểu thức SQL

Một modifying query có thể cập nhật nhiều cột:

```java
@Modifying
@Query("""
    UPDATE customer
    SET status = :status,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = :id
    """)
Mono<Integer> changeStatus(
        @Param("id") Long id,
        @Param("status") String status);
```

Trong ví dụ, `updated_at` được gán bằng thời gian của database. Không cần truyền giá trị từ Java nếu database là nguồn có thẩm quyền cho thời điểm cập nhật.

Có thể dùng biểu thức số học trong UPDATE:

```java
@Modifying
@Query("UPDATE inventory SET available = available - :quantity WHERE product_id = :productId AND available >= :quantity")
Mono<Integer> reserveInventory(
        @Param("productId") Long productId,
        @Param("quantity") Integer quantity);
```

Đây là một câu lệnh có điều kiện giúp cập nhật số lượng theo thao tác nguyên tử ở database. Nếu không đủ tồn kho, điều kiện `available >= :quantity` không khớp và số hàng bị ảnh hưởng có thể là `0`. Cách này tránh mẫu “đọc số lượng, trừ trong Java, rồi ghi lại” vốn dễ gặp race condition khi có nhiều request đồng thời.

Service có thể diễn giải kết quả:

```java
public Mono<Void> reserve(Long productId, int quantity) {
    return inventoryRepository.reserveInventory(productId, quantity)
            .flatMap(rows -> rows == 1
                    ? Mono.empty()
                    : Mono.error(new InsufficientInventoryException(productId)));
}
```

Ví dụ giả định `product_id` là duy nhất nên tối đa một hàng được cập nhật. Nếu một câu lệnh có thể cập nhật nhiều hàng, điều kiện kiểm tra cần phù hợp với số lượng mong đợi và mô hình dữ liệu.

## 9. Bulk update và domain model

`@Modifying` thực thi SQL trực tiếp trên các hàng phù hợp. Spring Data không tải từng entity lên để gọi domain method của chúng. Điều này tạo khác biệt quan trọng giữa bulk update và cách đọc-sửa-lưu entity.

Ví dụ bulk update:

```java
@Modifying
@Query("UPDATE purchase_order SET status = 'EXPIRED' WHERE status = 'PENDING' AND expires_at < :now")
Mono<Integer> expireOrders(@Param("now") OffsetDateTime now);
```

Truy vấn trên có thể hiệu quả khi cần chuyển trạng thái cho nhiều đơn hàng theo một điều kiện đơn giản. Nhưng nó bỏ qua các phương thức domain như `order.expire()` và những invariant chỉ được kiểm tra trong aggregate root.

Nếu việc chuyển trạng thái phụ thuộc nhiều điều kiện nghiệp vụ, phát domain event riêng cho từng đơn hàng hoặc phải cập nhật nhiều object trong aggregate, hãy cân nhắc tải aggregate, gọi domain method và lưu qua repository. Nếu cần bulk operation, phải thể hiện các invariant cần bảo vệ ngay trong điều kiện SQL/constraint hoặc một quy trình riêng.

### 9.1. Không tự động chạy entity lifecycle như save

Một modifying query không tương đương với `findById` rồi `save`. Vì Spring Data không materialize từng entity:

- Domain method của entity không được gọi.
- Các object Java đang nằm trong bộ nhớ không tự đổi theo dữ liệu mới.
- Optimistic locking của entity không tự động được áp dụng như khi lưu entity có `@Version`.
- Các callback/auditing gắn với quá trình lưu entity không nên được giả định là chạy cho từng hàng bị bulk update.

Nếu cần cập nhật `updated_at`, `version`, audit column hoặc phát sự kiện domain, hãy đưa các thay đổi đó vào SQL hoặc quy trình ứng dụng một cách tường minh.

### 9.2. Optimistic locking với modifying query

Giả sử bảng có cột `version`. Khi tự viết UPDATE, cần tự thêm điều kiện version và tăng version nếu muốn bảo vệ cập nhật đồng thời:

```java
@Modifying
@Query("""
    UPDATE customer
    SET name = :name,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
    """)
Mono<Integer> renameIfVersionMatches(
        @Param("id") Long id,
        @Param("name") String name,
        @Param("expectedVersion") Long expectedVersion);
```

Nếu kết quả là `1`, câu lệnh đã khớp ID và version. Nếu là `0`, bản ghi có thể không tồn tại hoặc version đã thay đổi. Nếu cần phân biệt hai trường hợp, phải truy vấn thêm hoặc thiết kế kết quả SQL cụ thể.

Không nên chỉ thêm `version = version + 1` mà quên điều kiện `version = :expectedVersion`; nếu không, nhiều request vẫn có thể lần lượt ghi đè nhau.

## 10. Soft delete bằng @Modifying

Soft delete giữ lại hàng trong database nhưng đánh dấu không còn hoạt động. Ví dụ bảng có `deleted_at`:

```sql
ALTER TABLE customer ADD COLUMN deleted_at TIMESTAMPTZ NULL;
```

Repository:

```java
@Modifying
@Query("UPDATE customer SET deleted_at = CURRENT_TIMESTAMP WHERE id = :id AND deleted_at IS NULL")
Mono<Integer> softDelete(@Param("id") Long id);
```

Điều kiện `deleted_at IS NULL` khiến thao tác lặp lại không tiếp tục đánh dấu một bản ghi đã xóa. Tùy database, kết quả số hàng khi chạy lại có thể phụ thuộc semantics rows affected, nhưng điều kiện vẫn bảo đảm chỉ những hàng chưa xóa mới khớp.

Các truy vấn đọc cần lọc `deleted_at IS NULL` nếu muốn ẩn bản ghi đã xóa. Có thể đặt điều kiện trong derived query, `@Query`, custom repository hoặc một read model phù hợp. `@Modifying` không tự thêm bộ lọc soft delete vào những query khác.

Soft delete cũng ảnh hưởng tới unique constraint. Ví dụ email cần duy nhất trong số customer đang hoạt động có thể cần partial unique index nếu database hỗ trợ, hoặc một chiến lược uniqueness khác. Không chỉ thêm `deleted_at` rồi giả định dữ liệu đã xóa có thể được tạo lại với cùng email.

## 11. Transaction với modifying query

Một câu UPDATE/DELETE đơn lẻ thường được database thực thi theo cơ chế transaction/autocommit của connection nếu không có transaction được quản lý bên ngoài. Khi một use case cần nhiều câu lệnh thay đổi dữ liệu thành một đơn vị nguyên tử, hãy xác định transaction reactive ở application service.

Ví dụ:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Void> cancelOrder(Long id) {
        return orderRepository.markCancelled(id)
                .flatMap(rows -> {
                    if (rows == 0) {
                        return Mono.error(new OrderNotFoundException(id));
                    }

                    return auditRepository.recordCancellation(id);
                });
    }
}
```

Ví dụ giả định `markCancelled` và `recordCancellation` tham gia cùng một reactive transaction manager và connection. Nếu thao tác thứ hai lỗi, transaction có thể rollback thay đổi đầu tiên. Nếu audit được ghi ở hệ thống khác, transaction R2DBC không bao phủ hệ thống đó.

### 11.1. Cần transaction manager phù hợp

Spring Data R2DBC dùng `R2dbcTransactionManager` hoặc transaction manager reactive tương ứng với `ConnectionFactory`. `@Transactional` phải được áp dụng trong ngữ cảnh Spring quản lý và publisher phải được trả về để interceptor theo dõi lifecycle.

Không gọi `subscribe()` độc lập bên trong phương thức transaction rồi trả về một publisher khác. Subscription riêng có thể chạy ngoài transaction context. Hãy nối các publisher bằng `flatMap`, `then` hoặc toán tử phù hợp.

### 11.2. Transaction không thay thế điều kiện WHERE

Transaction giúp các thay đổi tham gia cùng đơn vị commit/rollback, nhưng không làm câu UPDATE tự động đúng. Một câu lệnh thiếu điều kiện WHERE vẫn có thể cập nhật toàn bộ bảng trong transaction rồi commit thành công.

Hãy xác định rõ phạm vi hàng cần tác động, constraint và locking cần thiết. Transaction không thay thế optimistic locking hoặc kiểm tra quyền truy cập.

## 12. Câu lệnh có RETURNING và dữ liệu trả về

Một số database, như PostgreSQL, hỗ trợ `UPDATE ... RETURNING` hoặc `DELETE ... RETURNING` để trả lại hàng đã thay đổi:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 10
RETURNING id, status;
```

Tuy nhiên, `@Modifying` được thiết kế để thực thi modifying query và lấy kết quả dạng số hàng ảnh hưởng hoặc tín hiệu hoàn tất; không nên giả định nó sẽ ánh xạ các hàng `RETURNING` thành entity như một truy vấn đọc.

Nếu cần nhận entity sau UPDATE/DELETE, hãy dùng `DatabaseClient` để tiêu thụ result rows hoặc một custom repository implementation phù hợp:

```java
public Mono<Customer> activateCustomer(DatabaseClient databaseClient, Long id) {
    return databaseClient.sql("""
            UPDATE customer
            SET status = 'ACTIVE'
            WHERE id = :id
            RETURNING id, name, email_address, status
            """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)))
            .one();
}
```

Ví dụ dùng cú pháp PostgreSQL `RETURNING` và giả định constructor tương ứng. Với database khác, dùng cơ chế trả generated/changed rows được driver hỗ trợ hoặc thực hiện truy vấn đọc sau khi cập nhật.

## 13. @Modifying và DatabaseClient khác nhau thế nào?

Hai API đều có thể thực thi SQL thay đổi dữ liệu, nhưng ở mức trừu tượng khác nhau:

| Tiêu chí | Repository `@Modifying` | `DatabaseClient` |
| --- | --- | --- |
| Vị trí sử dụng | Method của repository | Persistence adapter, repository custom hoặc service phù hợp |
| Khai báo SQL | `@Query` trên method | Gọi `sql(...)` trong code |
| Bind tham số | Method parameters và `@Param` | `.bind(...)` |
| Kết quả phổ biến | Số hàng hoặc `Mono<Void>` theo kiểu được hỗ trợ | Có thể lấy `rowsUpdated()` hoặc map result rows |
| Mapping entity | Không tải entity cho modifying query | Có thể tự map hàng nếu câu lệnh trả result |
| Mức linh hoạt | Phù hợp câu SQL gọn, cố định | Linh hoạt hơn cho SQL động có kiểm soát, RETURNING và custom mapping |

Chọn `@Modifying` khi câu lệnh ngắn, ổn định và kết quả số hàng/hoàn tất là đủ. Chọn `DatabaseClient` hoặc custom repository khi cần trả các hàng thay đổi, xây dựng câu lệnh phức tạp, dùng API driver đặc thù hoặc điều khiển mapping chi tiết.

## 14. Derived update và modifying query

Spring Data R2DBC hỗ trợ derived query cho một số thao tác như delete, nhưng không nên mặc định mọi câu UPDATE đều có thể được tạo từ tên method theo cách mong muốn. Khi cần cập nhật một tập cột cụ thể theo SQL, `@Query` kết hợp `@Modifying` là cách tường minh.

Ví dụ:

```java
@Modifying
@Query("UPDATE task SET completed = TRUE WHERE due_at < :now AND completed = FALSE")
Mono<Integer> completeOverdueTasks(@Param("now") OffsetDateTime now);
```

Method name `completeOverdueTasks` thể hiện ý định nghiệp vụ, còn SQL cho biết chính xác cách cập nhật. Không phải mọi điều kiện đều nên nhồi vào tên method dài; khi query phức tạp, `@Query` giúp người đọc nhìn thấy câu lệnh thật.

## 15. Lỗi thường gặp khi dùng @Modifying

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| UPDATE chạy nhưng entity không đổi trong Java | Modifying query chỉ thay đổi database, không cập nhật object đang giữ trong bộ nhớ | Đọc lại entity hoặc dùng kết quả RETURNING qua DatabaseClient |
| Method không được xử lý như modifying query | Thiếu `@Modifying` trên method dùng `@Query` | Thêm annotation đúng package Spring Data R2DBC |
| Query SELECT báo lỗi hoặc kết quả sai | Dùng nhầm `@Modifying` cho truy vấn đọc | Bỏ `@Modifying` và khai báo kiểu trả về entity/projection |
| Không nhận được số hàng | Method trả `Mono<Void>` | Dùng kiểu số reactive được phiên bản hỗ trợ |
| Câu UPDATE thay đổi quá nhiều hàng | Điều kiện WHERE thiếu hoặc không đủ chặt | Kiểm tra điều kiện, chạy thử trên dữ liệu test và xem rows affected |
| Bind parameter không hoạt động | Tên `@Param` không khớp named marker hoặc sai kiểu | Đồng bộ tên tham số và kiểu Java/SQL |
| SQL injection | Nối dữ liệu đầu vào vào chuỗi SQL | Dùng bind parameter; whitelist identifier nếu cần dynamic SQL |
| Version không tăng hoặc không phát hiện conflict | Bulk UPDATE không tự áp dụng optimistic locking entity | Thêm điều kiện version và tăng version tường minh |
| Audit timestamp không được cập nhật | Bulk query bỏ qua callback/entity auditing | Gán cột audit ngay trong SQL hoặc dùng luồng load-mutate-save |
| Xóa thất bại do foreign key | Hàng đang được bảng khác tham chiếu | Xác định thứ tự xóa hoặc hành vi FK phù hợp |
| Transaction không bao trùm mọi thao tác | Một publisher bị subscribe riêng hoặc dùng transaction manager khác | Nối publisher và kiểm tra cùng transaction context/ConnectionFactory |

## 16. Kiểm thử modifying query

Với repository reactive, có thể dùng `StepVerifier` để kiểm tra số hàng được phát:

```java
StepVerifier.create(customerRepository.updateStatus(10L, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();
```

Kiểm tra không có hàng phù hợp:

```java
StepVerifier.create(customerRepository.updateStatus(-1L, "ACTIVE"))
        .expectNext(0)
        .verifyComplete();
```

Với phương thức trả `Mono<Void>`:

```java
StepVerifier.create(taskRepository.deleteOldAuditLogs(cutoff))
        .verifyComplete();
```

Không dùng `expectNext` cho `Mono<Void>` vì publisher không phát phần tử. Nếu SQL lỗi, `verifyComplete()` sẽ thất bại do publisher kết thúc bằng error signal.

### 16.1. Kiểm tra dữ liệu sau khi cập nhật

Kiểm thử nên xác nhận cả kết quả số hàng và trạng thái dữ liệu:

```java
StepVerifier.create(customerRepository.updateStatus(customerId, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();

StepVerifier.create(customerRepository.findById(customerId))
        .assertNext(customer -> assertEquals("ACTIVE", customer.getStatus()))
        .verifyComplete();
```

Các ví dụ giả định fixture đã tạo customer trước đó. Nên chạy integration test với đúng database và driver vì cú pháp SQL, kiểu dữ liệu, rows affected và transaction behavior có thể phụ thuộc hệ quản trị.

### 16.2. Kiểm thử transaction rollback

Nếu một use case thực hiện modifying query rồi thực hiện thao tác thứ hai có thể thất bại, hãy kiểm tra transaction có rollback thay đổi đầu tiên hay không. Bài test cần chạy qua Spring transaction manager thực tế và tiêu thụ publisher được trả về; không tách subscription bằng `subscribe()` trong test.

## 17. Chọn giữa modifying query và load-mutate-save

Không phải mọi thao tác cập nhật đều nên viết bằng `@Modifying`. Hai cách có mục đích khác nhau:

| Tình huống | Cách phù hợp |
| --- | --- |
| Đổi một cột theo điều kiện đơn giản trên nhiều hàng | `@Modifying` |
| Đánh dấu hàng hết hạn theo một mốc thời gian | `@Modifying` nếu không cần hành vi riêng từng entity |
| Cộng/trừ số lượng có điều kiện nguyên tử | `@Modifying` với điều kiện trong SQL hoặc câu lệnh DatabaseClient |
| Thay đổi aggregate có nhiều invariant | Load entity, gọi domain method, `save` |
| Cần optimistic locking tự động của entity | Load-mutate-save với `@Version` |
| Cần phát domain event cho từng aggregate | Load-mutate-save hoặc quy trình event riêng |
| Cần trả về entity sau UPDATE | `DatabaseClient` với RETURNING hoặc truy vấn lại |
| Cần cập nhật hàng loạt và ghi audit tổng hợp | `@Modifying` kết hợp audit rõ ràng |

Bulk update thường giảm số lần round-trip và tránh mapping entity, nhưng bỏ qua hành vi domain của từng object. Load-mutate-save thể hiện rõ quy tắc domain và có thể tận dụng optimistic locking, nhưng cần đọc rồi ghi từng aggregate và có thể tốn tài nguyên hơn.

## 18. Quy trình xây dựng một modifying query an toàn

Khi thêm một phương thức cập nhật hoặc xóa bằng `@Modifying`, hãy xác định:

1. Câu SQL thực sự là UPDATE hay DELETE, và database mục tiêu có hỗ trợ cú pháp đó không?
2. Method có `@Query` và `@Modifying` đúng package hay chưa?
3. Named parameter trong SQL có khớp `@Param` và kiểu dữ liệu không?
4. Điều kiện WHERE có giới hạn đúng tập hàng cần thay đổi không?
5. Caller cần số hàng bị ảnh hưởng (`Mono<Integer>`) hay chỉ cần tín hiệu hoàn tất (`Mono<Void>`)?
6. Bulk update có bỏ qua invariant, auditing, version hoặc domain event nào không?
7. Thao tác có cần tham gia transaction reactive với các câu lệnh khác không?
8. Nếu cần hàng trả về, có nên dùng `DatabaseClient` thay cho modifying query không?
9. Integration test đã xác nhận số hàng, dữ liệu sau thay đổi, lỗi constraint và rollback chưa?

`@Modifying` là cách khai báo rõ ràng cho các câu UPDATE/DELETE viết bằng `@Query` trong repository Spring Data R2DBC. Nó giúp database thực hiện thay đổi trực tiếp và trả về thông tin số hàng bị ảnh hưởng hoặc tín hiệu hoàn tất. Khi dùng, cần kiểm soát điều kiện SQL, bind tham số, transaction và những quy tắc domain mà bulk operation không tự thực thi. Nếu use case cần entity sau thay đổi hoặc cần bảo vệ invariant của aggregate, hãy chọn `DatabaseClient` hoặc luồng load-mutate-save phù hợp.
