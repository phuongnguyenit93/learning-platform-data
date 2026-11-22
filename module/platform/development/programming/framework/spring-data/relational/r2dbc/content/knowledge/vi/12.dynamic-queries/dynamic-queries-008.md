# Xóa theo điều kiện và kiểm soát phạm vi tác động

Xóa dữ liệu theo điều kiện là thao tác có tác động trực tiếp đến tính toàn vẹn và khả năng khôi phục dữ liệu. Trong Spring Data R2DBC, ứng dụng có thể xóa theo ID bằng repository, dùng `R2dbcEntityTemplate` với `Query` và `Criteria`, hoặc viết câu lệnh `DELETE` tường minh bằng `@Modifying` hay `DatabaseClient`.

Khi điều kiện xóa được tạo động từ bộ lọc của request, điều quan trọng là kiểm soát phạm vi dữ liệu mà câu lệnh có thể tác động. Một bộ lọc tùy chọn bị bỏ qua, một danh sách ID rỗng hoặc một điều kiện tenant không được thêm vào có thể biến thao tác dự kiến xóa vài bản ghi thành thao tác xóa hàng loạt. Vì vậy, hãy thiết kế điều kiện bắt buộc, bind giá trị an toàn, kiểm tra số hàng bị ảnh hưởng và tổ chức transaction phù hợp.

## 1. Các cách xóa dữ liệu trong Spring Data R2DBC

Chọn API theo phạm vi và độ phức tạp của thao tác:

| Cách thực hiện | Khi phù hợp | Lưu ý về phạm vi |
|---|---|---|
| `deleteById(id)` | Xóa một bản ghi đã xác định bằng khóa chính | ID phải thuộc phạm vi người dùng được phép thao tác. |
| `deleteAllById(ids)` | Xóa một tập ID đã được xác định | Kiểm tra danh sách rỗng, số lượng và quyền sở hữu của các ID. |
| `R2dbcEntityTemplate.delete(query, Entity.class)` | Xóa theo `Criteria` có thể được xây dựng động | Dùng mapping metadata của entity và trả về số hàng bị xóa. |
| `@Modifying @Query` | Câu lệnh SQL cố định, rõ ràng và có điều kiện cụ thể | Tự kiểm soát `WHERE`, tên bảng/cột và tham số. |
| `DatabaseClient` | SQL động có số lượng điều kiện thay đổi theo request | Chỉ ghép các đoạn SQL cố định trong code; bind tất cả giá trị đầu vào. |

`deleteAll()` có phạm vi toàn bộ dữ liệu của repository. Chỉ dùng thao tác này khi nghiệp vụ thực sự yêu cầu xóa toàn bộ trong một ngữ cảnh được kiểm soát, chẳng hạn dữ liệu test hoặc một quy trình quản trị chuyên biệt. Không dùng nó làm mặc định cho endpoint nhận bộ lọc từ người dùng.

## 2. Xóa theo điều kiện bằng R2dbcEntityTemplate

`R2dbcEntityTemplate` cho phép tạo `Query` từ `Criteria` và thực hiện thao tác xóa theo entity. Cách này hữu ích khi điều kiện được ghép từ các thuộc tính đã biết trong code và muốn Spring Data xử lý mapping tên bảng/cột.

Ví dụ, xóa các đơn hàng cũ thuộc một tenant và có trạng thái đã hoàn tất:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import reactor.core.publisher.Mono;

public Mono<Long> deleteCompletedOrders(
        UUID tenantId, Instant createdBefore) {

    if (tenantId == null || createdBefore == null) {
        return Mono.error(new IllegalArgumentException(
            "tenantId and createdBefore are required"));
    }

    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("status").is("COMPLETED")
            .and("created_at").lessThan(createdBefore)
    );

    return template.delete(query, PurchaseOrder.class);
}
```

Điều kiện gồm ba phần:

- `tenant_id` giới hạn dữ liệu trong tenant hiện tại.
- `status` giới hạn nhóm đơn hàng có thể xóa.
- `created_at` giới hạn thời gian, tránh xóa các đơn hàng mới.

`template.delete(...)` trả về `Mono<Long>` biểu diễn số hàng bị xóa. Giá trị này hữu ích cho log, audit và phản hồi kết quả nghiệp vụ. Nếu số hàng bằng 0, không có hàng nào thỏa điều kiện tại thời điểm câu lệnh thực thi; điều đó có thể có nghĩa dữ liệu không tồn tại, đã được xử lý trước đó hoặc không thuộc phạm vi được phép.

Tên cột trong `Criteria` phải khớp với metadata mapping và schema của ứng dụng. Với tên cột được ánh xạ qua `@Column` hoặc naming strategy, hãy xác nhận cách Spring Data diễn giải thuộc tính trong phiên bản đang dùng.

## 3. Xây dựng điều kiện động từ bộ lọc tùy chọn

Một API tìm kiếm có thể cho phép người dùng chọn trạng thái, khoảng thời gian hoặc loại dữ liệu. Với thao tác xóa, không nên để mọi điều kiện đều tùy chọn mà không có quy tắc tối thiểu. Nếu tất cả bộ lọc đều vắng mặt, câu lệnh có thể xóa mọi bản ghi trong bảng hoặc trong một tenant.

Ví dụ, một quy trình dọn dữ liệu yêu cầu tenant và thời điểm giới hạn; trạng thái là điều kiện bổ sung tùy chọn:

```java
public Mono<Integer> deleteOldOrders(
        UUID tenantId,
        Instant createdBefore,
        String status) {

    if (tenantId == null || createdBefore == null) {
        return Mono.error(new IllegalArgumentException(
            "A tenant and cutoff time are required"));
    }

    StringBuilder sql = new StringBuilder(
        "DELETE FROM purchase_order " +
        "WHERE tenant_id = :tenantId " +
        "AND created_at < :createdBefore");

    DatabaseClient.GenericExecuteSpec spec = databaseClient
        .sql(sql.toString())
        .bind("tenantId", tenantId)
        .bind("createdBefore", createdBefore);

    if (status != null && !status.isBlank()) {
        sql.append(" AND status = :status");
        spec = databaseClient.sql(sql.toString())
            .bind("tenantId", tenantId)
            .bind("createdBefore", createdBefore)
            .bind("status", status);
    }

    return spec.fetch().rowsUpdated();
}
```

Ví dụ này dùng hai điều kiện bắt buộc để giới hạn phạm vi. `status` chỉ bổ sung một predicate. Các giá trị được bind qua named parameter, vì vậy chuỗi đầu vào không được nối trực tiếp vào SQL.

Khi có nhiều bộ lọc tùy chọn, có thể gom phần dựng SQL và bind parameter vào một helper để tránh lặp code. Các tên cột, toán tử và đoạn SQL phải đến từ danh sách cho phép trong code. Không thể bind tên bảng hoặc tên cột như một giá trị SQL; tuyệt đối không ghép trực tiếp tên cột do client gửi vào câu lệnh.

### 3.1 Tránh điều kiện xóa rỗng

Các tình huống cần từ chối hoặc xử lý riêng:

- Thiếu tenant/user scope bắt buộc.
- Không có bộ lọc nào trong khi nghiệp vụ yêu cầu xóa có giới hạn.
- Danh sách ID rỗng nhưng code lại chuyển thành thao tác `deleteAll()`.
- Khoảng thời gian không hợp lệ, ví dụ ngày bắt đầu lớn hơn ngày kết thúc.
- Bộ lọc chứa giá trị ngoài danh sách trạng thái hoặc loại được phép.
- Request yêu cầu xóa số lượng vượt quá hạn mức cho một lần thao tác.

Đừng dựa vào một điều kiện kiểu `(:status IS NULL OR status = :status)` như biện pháp bảo vệ duy nhất. Khi `status` null, predicate đó trở thành đúng cho mọi hàng còn lại. Ngoài ra, bind `NULL` trong một số biểu thức SQL có thể cần kiểu tham số tường minh. Dựng predicate chỉ khi có filter và xác thực điều kiện bắt buộc sẽ dễ kiểm soát hơn.

## 4. Dùng @Modifying cho câu lệnh DELETE cố định

Khi điều kiện SQL ổn định, có thể khai báo truy vấn xóa trực tiếp trên repository:

```java
import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        DELETE FROM purchase_order
        WHERE tenant_id = :tenantId
          AND status = :status
          AND created_at < :createdBefore
        """)
    Mono<Integer> deleteOldOrders(
        @Param("tenantId") UUID tenantId,
        @Param("status") String status,
        @Param("createdBefore") Instant createdBefore
    );
}
```

`@Modifying` đánh dấu truy vấn là thao tác thay đổi dữ liệu. Giá trị trả về dạng số cho biết số hàng được database báo đã cập nhật/xóa. Tên và kiểu trả về cụ thể cần khớp với API Spring Data R2DBC của phiên bản dự án.

SQL trong `@Query` phải dùng đúng tên bảng/cột vật lý. Khác với `R2dbcEntityTemplate` dùng metadata entity, truy vấn SQL tường minh khiến người viết chịu trách nhiệm về schema, alias, dialect và tham số. Không đưa nội dung SQL từ request vào annotation hoặc nối chuỗi tùy tiện.

## 5. Xóa theo danh sách ID

Nếu ứng dụng đã xác định chính xác các ID cần xóa, dùng `deleteAllById` hoặc điều kiện `IN` phù hợp. Cần kiểm tra danh sách trước khi gọi:

```java
public Mono<Void> deleteSelectedOrders(
        UUID tenantId, Collection<Long> requestedIds) {

    if (tenantId == null || requestedIds == null || requestedIds.isEmpty()) {
        return Mono.error(new IllegalArgumentException(
            "Tenant and at least one order ID are required"));
    }

    if (requestedIds.size() > 200) {
        return Mono.error(new IllegalArgumentException(
            "Too many IDs in one request"));
    }

    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("id").in(requestedIds)
    );

    return template.delete(query, PurchaseOrder.class).then();
}
```

Điều kiện tenant vẫn cần xuất hiện dù client gửi danh sách ID. Không được giả định ID là bí mật hoặc người dùng chỉ có thể gửi ID thuộc quyền của họ. Nếu dùng `deleteAllById`, repository chỉ nhận ID và không tự biết quy tắc tenant của ứng dụng; khi đó cần xác thực quyền sở hữu trước hoặc dùng truy vấn có tenant predicate như ví dụ.

Danh sách rỗng cần được xử lý rõ. Không chuyển danh sách rỗng thành `deleteAll()`, cũng không dựa vào cách database xử lý `IN ()` vì cú pháp này khác nhau giữa hệ quản trị.

## 6. Giới hạn số hàng và xóa theo từng lô

Một câu lệnh xóa có thể tác động đến rất nhiều hàng, giữ lock lâu, tạo nhiều log và gây tải lớn cho database. Với dữ liệu lớn, nên chia thành các lô có kích thước giới hạn.

Một cách làm là chọn trước một tập ID theo điều kiện và giới hạn số lượng, sau đó xóa đúng các ID vừa chọn trong cùng phạm vi tenant:

```java
public Mono<Long> deleteOneBatch(
        UUID tenantId, Instant createdBefore) {

    Query selection = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("created_at").lessThan(createdBefore)
    ).sort(Sort.by("id")).limit(500);

    return template.select(selection, PurchaseOrder.class)
        .map(PurchaseOrder::getId)
        .collectList()
        .flatMap(ids -> {
            if (ids.isEmpty()) {
                return Mono.just(0L);
            }

            Query deletion = Query.query(
                Criteria.where("tenant_id").is(tenantId)
                    .and("id").in(ids)
                    .and("created_at").lessThan(createdBefore)
            );

            return template.delete(deletion, PurchaseOrder.class);
        });
}
```

Trong ví dụ, mỗi lần gọi chỉ xử lý tối đa 500 ID. Có thể gọi lại theo lịch hoặc điều phối theo lô cho đến khi không còn ID phù hợp. Predicate thời gian và tenant được kiểm tra lại trong câu lệnh xóa để hạn chế việc xóa bản ghi đã thay đổi sau khi được chọn.

Nếu có nhiều worker cùng dọn dữ liệu, cần thiết kế cách phân chia công việc để chúng không liên tục chọn cùng một tập ID. Tùy database, có thể dùng cơ chế claim/lock hoặc trạng thái xử lý riêng. `SELECT` rồi `DELETE` là hai thao tác; nếu cần bảo đảm chặt chẽ trước cập nhật đồng thời, hãy chọn isolation/locking phù hợp và kiểm tra khả năng của database. Không giả định `LIMIT` trên truy vấn chọn sẽ tự giới hạn một câu `DELETE` độc lập.

## 7. Kiểm tra phạm vi trước khi xóa

Với thao tác có tác động lớn, có thể thực hiện bước preview bằng `COUNT` hoặc truy vấn ID để cho biết số bản ghi dự kiến bị ảnh hưởng:

```java
Query query = Query.query(
    Criteria.where("tenant_id").is(tenantId)
        .and("status").is("EXPIRED")
        .and("created_at").lessThan(cutoff)
);

Mono<Long> affectedCount = template.count(query, PurchaseOrder.class);
```

Có thể dùng số lượng này để yêu cầu xác nhận khi vượt ngưỡng, ghi audit hoặc quyết định chạy theo batch. Tuy nhiên, `COUNT` và `DELETE` là hai câu lệnh khác nhau. Dữ liệu có thể thay đổi giữa hai thời điểm; vì vậy số lượng preview không phải cam kết chính xác về số hàng sẽ bị xóa.

Nếu cần giới hạn cứng số hàng, chọn ID theo lô có giới hạn rồi xóa đúng tập ID đó. Nếu cần thao tác kiểm tra và xóa như một đơn vị nhất quán, dùng transaction và cơ chế khóa/isolation phù hợp với database. Ngay cả khi ở trong transaction, mức isolation mặc định có thể không ngăn mọi thay đổi đồng thời hoặc phantom row.

## 8. Transaction và tính nhất quán

Một thao tác xóa có thể kéo theo nhiều thay đổi: xóa các dòng con, ghi audit, cập nhật trạng thái công việc hoặc phát sự kiện sau khi commit. Nếu các thay đổi database phải cùng thành công hoặc thất bại, hãy đặt chúng trong reactive transaction.

Ví dụ với service trả về `Mono`:

```java
@Transactional
public Mono<Long> deleteExpiredOrders(UUID tenantId, Instant cutoff) {
    Query query = Query.query(
        Criteria.where("tenant_id").is(tenantId)
            .and("created_at").lessThan(cutoff)
    );

    return template.delete(query, PurchaseOrder.class)
        .flatMap(deleted -> auditRepository
            .recordDeletion(tenantId, "EXPIRED_ORDERS", deleted)
            .thenReturn(deleted));
}
```

Trong ứng dụng reactive, transaction context được truyền qua reactive chain. Phương thức phải trả về publisher để Spring quản lý transaction; không gọi `block()` bên trong luồng này. Cấu hình cần có reactive transaction manager tương ứng với `ConnectionFactory`, và các thao tác phải sử dụng hạ tầng kết nối tham gia cùng transaction.

Nếu audit được ghi ra hệ thống ngoài database, transaction database không thể tự bảo đảm thao tác bên ngoài cùng commit/rollback. Với sự kiện cần phát sau commit, cân nhắc outbox pattern hoặc cơ chế đồng bộ phù hợp. Không phát thông báo “đã xóa” trước khi transaction commit thành công.

## 9. Quan hệ khóa ngoại, aggregate và cascade

Xóa một hàng có thể bị ràng buộc bởi khóa ngoại hoặc ảnh hưởng đến các hàng liên quan. Cần xác định rõ cách xử lý trước khi chạy câu lệnh:

- **RESTRICT/NO ACTION:** database từ chối xóa hàng cha nếu còn hàng con tham chiếu.
- **ON DELETE CASCADE:** database tự xóa hàng con theo ràng buộc khóa ngoại.
- **SET NULL:** database đặt khóa ngoại ở hàng con thành `NULL`, nếu schema cho phép.
- **Xóa tường minh:** ứng dụng xóa các hàng liên quan theo thứ tự trong transaction.

Không mặc định Spring Data R2DBC sẽ duyệt toàn bộ object graph và thực hiện cascade giống ORM truyền thống. Hành vi xóa thực tế phụ thuộc câu lệnh được phát ra, mapping aggregate và constraint ở database. Với `@MappedCollection`, cần hiểu cách Spring Data quản lý các thành phần thuộc aggregate khi lưu hoặc xóa root; với các aggregate độc lập, cần xử lý theo quy tắc nghiệp vụ riêng.

Trước khi xóa dữ liệu cha, kiểm tra các quan hệ có thể còn dữ liệu con, lịch sử giao dịch, tài liệu hoặc dữ liệu cần lưu trữ theo chính sách retention. Không dùng cascade ở database nếu nghiệp vụ yêu cầu giữ lại bản ghi lịch sử hoặc cần audit riêng cho từng loại dữ liệu.

## 10. Hard delete, soft delete và lưu vết

**Hard delete** loại bỏ hàng khỏi bảng. Cách này phù hợp khi dữ liệu hết thời hạn lưu trữ, là dữ liệu tạm hoặc phải được xóa theo chính sách. Cần xem xét backup, log, bản sao đọc, cache và hệ thống downstream vì việc xóa khỏi một bảng không tự xóa mọi bản sao dữ liệu.

**Soft delete** giữ hàng nhưng đánh dấu không còn hoạt động, ví dụ `deleted_at` hoặc `active = false`:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET deleted_at = :deletedAt
    WHERE tenant_id = :tenantId
      AND id = :id
      AND deleted_at IS NULL
    """)
Mono<Integer> markDeleted(
    UUID tenantId,
    Long id,
    Instant deletedAt
);
```

Soft delete cần quy ước nhất quán cho mọi truy vấn đọc, unique constraint, báo cáo và tác vụ dọn dữ liệu. Nếu repository không tự động lọc `deleted_at`, truy vấn thông thường vẫn có thể trả về hàng đã đánh dấu xóa. Cần đưa điều kiện này vào query hoặc xây dựng abstraction dùng chung.

Với cả hard delete và soft delete, nên lưu thông tin audit cần thiết như actor, thời điểm, lý do, request/correlation ID và phạm vi tác động. Không lưu dữ liệu nhạy cảm không cần thiết vào log. Audit nên được ghi trong transaction khi cần bảo đảm cùng trạng thái với thao tác database.

## 11. Kiểm soát quyền và chống xóa nhầm

Điều kiện xóa phải được xác định ở server từ danh tính và quyền đã xác thực. Không tin `tenantId`, `ownerId` hoặc phạm vi dữ liệu do client tự gửi nếu server có thể lấy chúng từ security context. Nếu request có ID, server vẫn phải kiểm tra ID đó thuộc phạm vi của người gọi.

Một số nguyên tắc hữu ích:

1. Luôn đưa điều kiện tenant/owner vào câu lệnh khi dữ liệu được phân vùng theo tenant hoặc người dùng.
2. Yêu cầu ít nhất một predicate giới hạn bổ sung cho các thao tác xóa hàng loạt.
3. Chỉ cho phép các trường lọc và toán tử nằm trong allowlist của ứng dụng.
4. Bind giá trị thay vì nối chuỗi SQL từ input.
5. Giới hạn số ID và số hàng mỗi batch.
6. Có preview/count hoặc bước xác nhận cho thao tác quản trị có phạm vi lớn.
7. Ghi audit actor, lý do và số hàng thực tế bị ảnh hưởng.
8. Cân nhắc soft delete hoặc quy trình phục hồi nếu nghiệp vụ cần khả năng khôi phục.

Không thể bảo vệ thao tác chỉ bằng cách ẩn nút xóa trên giao diện. Quyền phải được kiểm tra tại service/API và điều kiện phạm vi phải nằm trong truy vấn database.

## 12. Xóa có điều kiện theo phiên bản để tránh ghi đè đồng thời

Nếu entity dùng optimistic locking với trường `@Version`, thao tác cập nhật qua cơ chế entity có thể kiểm tra phiên bản. Với câu lệnh `DELETE` viết tay, không nên giả định framework tự thêm điều kiện version vào SQL tùy chỉnh.

Khi cần bảo đảm chỉ xóa bản ghi chưa bị thay đổi kể từ lúc người dùng đọc, có thể thêm version vào predicate:

```sql
DELETE FROM purchase_order
WHERE tenant_id = :tenantId
  AND id = :id
  AND version = :expectedVersion
```

Nếu số hàng bị xóa bằng 0, bản ghi có thể không tồn tại, không thuộc tenant hoặc version đã thay đổi. Service cần quyết định cách trả lỗi phù hợp, tránh tiết lộ dữ liệu của tenant khác qua thông báo chi tiết.

Đây là kiểm soát cạnh tranh ở mức câu lệnh. Nếu thao tác cần kiểm tra nhiều điều kiện nghiệp vụ rồi mới xóa, hãy đánh giá transaction, isolation và lock để tránh khoảng thời gian giữa kiểm tra và xóa bị một transaction khác thay đổi dữ liệu.

## 13. Một quy trình xóa an toàn

Một service xóa theo điều kiện có thể triển khai theo trình tự:

1. Xác thực người gọi và xác định tenant/owner từ security context.
2. Kiểm tra input, bao gồm ID, thời gian, trạng thái và danh sách điều kiện được phép.
3. Bắt buộc có predicate giới hạn phạm vi; từ chối request nếu thiếu điều kiện tối thiểu.
4. Tạo `Criteria` hoặc SQL với các đoạn cố định và bind tất cả giá trị.
5. Với thao tác lớn, preview số lượng hoặc chọn ID theo batch có giới hạn.
6. Thực hiện delete trong reactive transaction khi cần phối hợp nhiều thay đổi database.
7. Đọc số hàng bị ảnh hưởng và ghi audit sau khi thao tác thành công.
8. Phát sự kiện sau commit hoặc dùng outbox nếu cần đồng bộ hệ thống khác.
9. Theo dõi thời gian thực thi, số hàng bị xóa, lỗi constraint và số lần thao tác vượt ngưỡng.

Ví dụ, khi dọn đơn hàng hết hạn, predicate `tenant_id = ... AND created_at < ...` xác định phạm vi chính; trạng thái có thể thu hẹp thêm. Khi xóa theo ID, tenant predicate vẫn được giữ. Khi dữ liệu lớn, chọn ID theo batch và xóa lại bằng cả ID lẫn điều kiện phạm vi. Các lớp bảo vệ này giúp câu lệnh xóa phản ánh đúng ý định nghiệp vụ và giảm nguy cơ tác động ngoài dự kiến.
