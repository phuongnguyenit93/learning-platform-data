# Thiết kế điều kiện phiên bản khi cập nhật hàng loạt cần kiểm soát xung đột

Trong ứng dụng dùng JPA, một thao tác như “duyệt đồng loạt 500 đơn hàng” thường được thực hiện bằng câu lệnh `UPDATE` thay vì tải 500 entity rồi gọi `save` từng cái. Cách này giảm số lần đọc/ghi và chi phí quản lý entity, nhưng đồng thời đặt ra vấn đề: **làm sao bảo đảm chỉ cập nhật những hàng vẫn ở đúng phiên bản mà người gọi đã xem hoặc đã xác nhận?**

Câu trả lời là thiết kế thao tác theo nguyên tắc *compare-and-set* (CAS): mỗi hàng chỉ được sửa khi khóa định danh, phiên bản kỳ vọng và các điều kiện nghiệp vụ vẫn khớp. Khi sửa thành công, tăng phiên bản; trước khi commit, đối chiếu kết quả cập nhật với tập hàng được yêu cầu.

## 1. Vì sao `@Version` chưa đủ cho bulk update?

Với entity được quản lý trong persistence context, JPA hỗ trợ optimistic locking thông qua `@Version`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Version
    private Long version;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    // Constructor, getter và phương thức nghiệp vụ được lược bỏ.
}

enum OrderStatus {
    PENDING, APPROVED, CANCELLED
}
~~~

Khi cập nhật một `PurchaseOrder` đang được JPA quản lý và flush, provider có cơ chế kiểm tra phiên bản, phát hiện cập nhật cạnh tranh và tăng phiên bản phù hợp với optimistic locking.

Tuy nhiên, một lệnh JPQL bulk update như:

~~~jpql
update PurchaseOrder o
   set o.status = :newStatus
 where o.id in :ids
~~~

được thực thi trực tiếp ở cơ sở dữ liệu. Theo ngữ nghĩa JPA, **bulk update không tự thực hiện kiểm tra optimistic locking hoặc tăng trường phiên bản theo cách cập nhật managed entity thông thường**. Lệnh cũng bỏ qua vòng đời cập nhật từng entity; các entity đã nạp trong persistence context có thể giữ dữ liệu cũ.

Vì vậy, chỉ đặt `@Version` trên entity rồi chạy câu lệnh trên **không ngăn được lost update**. Cần đưa điều kiện phiên bản và phép tăng phiên bản trực tiếp vào câu lệnh bulk update.

## 2. Xác định hợp đồng xung đột trước khi viết truy vấn

Giả sử một yêu cầu chuyển ba đơn hàng từ `PENDING` sang `APPROVED` dựa trên dữ liệu mà người dùng đã xem:

| ID | Phiên bản người gọi kỳ vọng | Phiên bản hiện tại trong DB | Trạng thái hiện tại |
|---|---:|---:|---|
| 101 | 7 | 7 | PENDING |
| 102 | 7 | 8 | PENDING |
| 103 | 7 | 7 | PENDING |

Đơn 102 đã bị giao dịch khác thay đổi kể từ lần đọc. Nếu chỉ lọc theo ID và trạng thái, đơn 102 vẫn có thể bị ghi đè. Điều kiện `version = 7` sẽ loại đơn này khỏi tập cập nhật.

Với yêu cầu **tất cả hoặc không cập nhật gì (all-or-nothing)**, cần thống nhất bốn quy tắc:

1. Mỗi ID trong yêu cầu có đúng một phiên bản kỳ vọng; không nhận ID trùng nhau.
2. Chỉ cập nhật hàng thỏa **ID + phiên bản kỳ vọng + điều kiện nghiệp vụ**.
3. Mỗi lần cập nhật thành công phải làm phiên bản thay đổi, thường là `version = version + 1` với version kiểu số.
4. Nếu số hàng thực sự sửa khác số ID kỳ vọng, coi yêu cầu thất bại và **rollback toàn bộ transaction**, kể cả các hàng đã được câu lệnh sửa tạm thời.

Cần phân biệt: số hàng cập nhật ít hơn mong đợi chứng minh **một hoặc nhiều tiền điều kiện không thỏa**; nguyên nhân có thể là phiên bản cũ, trạng thái sai hoặc ID không tồn tại. Không thể suy ra chính xác ID nào xung đột từ một con số tổng.

## 3. Một bulk update khi mọi hàng có cùng phiên bản kỳ vọng

Với yêu cầu đồng nhất `expectedVersion = 7`, truy vấn JPQL có thể viết:

~~~jpql
update PurchaseOrder o
   set o.status = :newStatus,
       o.version = o.version + 1
 where o.id in :ids
   and o.version = :expectedVersion
   and o.status = :expectedStatus
~~~

Từng thành phần có mục đích riêng:

| Thành phần | Ý nghĩa |
|---|---|
| `o.id in :ids` | Chỉ tác động đúng tập ID được người gọi yêu cầu. |
| `o.version = :expectedVersion` | Khóa lạc quan: từ chối hàng đã đổi phiên bản. |
| `o.status = :expectedStatus` | Bảo vệ quy tắc chuyển trạng thái; một đơn bị hủy không thể vô tình được duyệt. |
| `o.version = o.version + 1` | Làm mọi yêu cầu dùng phiên bản cũ trở nên không còn hợp lệ sau lần sửa thành công. |
| Giá trị trả về của `executeUpdate()` | Số hàng bị cập nhật, dùng kiểm tra toàn bộ tập yêu cầu có được chấp nhận hay không. |

Ví dụ bằng SQL tương đương về ý tưởng:

~~~sql
UPDATE purchase_orders
   SET status = 'APPROVED',
       version = version + 1
 WHERE id IN (101, 102, 103)
   AND version = 7
   AND status = 'PENDING';
~~~

Với dữ liệu ở mục trước, lệnh chỉ sửa ID 101 và 103, trả về số hàng bị ảnh hưởng là 2. Nếu yêu cầu đòi đủ 3 hàng, application phải phát hiện `2 != 3` và rollback; không được mặc nhiên commit hai hàng đã sửa.

### Ví dụ triển khai với Spring Data JPA

`@Modifying` và `@Query` sau đây là tiện ích của **Spring Data JPA**, còn cú pháp `UPDATE` là JPQL:

~~~java
import java.util.Collection;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update PurchaseOrder o
           set o.status = :toStatus,
               o.version = o.version + 1
         where o.id in :ids
           and o.status = :fromStatus
           and o.version = :expectedVersion
        """)
    int changeStatusAtVersion(
            @Param("ids") Collection<Long> ids,
            @Param("fromStatus") OrderStatus fromStatus,
            @Param("toStatus") OrderStatus toStatus,
            @Param("expectedVersion") long expectedVersion);
}
~~~

Dịch vụ xác nhận số hàng cập nhật **trong cùng transaction**:

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderBatchService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderBatchService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void approveAllAtVersion(
            Collection<Long> requestedIds, long expectedVersion) {

        if (requestedIds == null || requestedIds.isEmpty()
                || requestedIds.contains(null)) {
            throw new IllegalArgumentException("Danh sách ID không hợp lệ");
        }

        Set<Long> ids = new LinkedHashSet<>(requestedIds);
        if (ids.size() != requestedIds.size()) {
            throw new IllegalArgumentException("ID bị lặp trong yêu cầu");
        }

        int changed = repository.changeStatusAtVersion(
                ids,
                OrderStatus.PENDING,
                OrderStatus.APPROVED,
                expectedVersion);

        if (changed != ids.size()) {
            throw new BatchPreconditionFailedException(
                    "Chỉ cập nhật được " + changed + "/" + ids.size()
                    + " hàng; yêu cầu bị hủy");
        }
    }
}

class BatchPreconditionFailedException extends RuntimeException {
    BatchPreconditionFailedException(String message) {
        super(message);
    }
}
~~~

Vì exception là `RuntimeException`, cấu hình `@Transactional` mặc định của Spring đánh dấu rollback. Phương thức có `@Transactional` phải được gọi qua cơ chế proxy/transaction management đang có hiệu lực; nếu gọi nội bộ theo cách bỏ qua proxy, cần bảo đảm vẫn có transaction bao ngoài. Nếu hệ thống xử lý exception bên trong transaction mà không ném ra ngoài, phải chủ động đánh dấu rollback để tránh commit phần đã cập nhật.

**Giới hạn áp dụng:** ví dụ một câu JPQL với `expectedVersion` duy nhất chỉ đúng khi *mọi ID đều có cùng phiên bản kỳ vọng*. Không thể dùng một phiên bản “đại diện” cho danh sách có version khác nhau.

## 4. Nhiều hàng, mỗi hàng có phiên bản kỳ vọng riêng

Trong thực tế, danh sách thường có dạng:

~~~text
(id=101, expectedVersion=7)
(id=102, expectedVersion=4)
(id=103, expectedVersion=11)
~~~

Điều kiện phải bảo toàn **cặp (ID, phiên bản)**. Truy vấn sai sau đây không đạt yêu cầu:

~~~sql
WHERE id IN (101, 102, 103)
  AND version IN (7, 4, 11)
~~~

Vì nó cho phép ghép chéo: ID 101 có version 4 cũng được chấp nhận, dù người gọi yêu cầu version 7 cho ID 101. Tương tự, không được dùng `MAX(expectedVersion)` hoặc một phiên bản chung tùy chọn.

### Cách A — Cập nhật có điều kiện từng ID trong một transaction

Cách đơn giản và dễ duy trì cho lô nhỏ hoặc vừa là dùng một lệnh có điều kiện cho mỗi cặp:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
    update PurchaseOrder o
       set o.status = :toStatus,
           o.version = o.version + 1
     where o.id = :id
       and o.version = :expectedVersion
       and o.status = :fromStatus
    """)
int changeOneAtVersion(
        @Param("id") long id,
        @Param("expectedVersion") long expectedVersion,
        @Param("fromStatus") OrderStatus fromStatus,
        @Param("toStatus") OrderStatus toStatus);
~~~

Định nghĩa đầu vào như `record ExpectedRow(Long id, long expectedVersion) {}` (Java 17+). Sau khi xác thực danh sách không rỗng, không có ID/null trùng lặp, dịch vụ có thể thực hiện:

~~~java
@Transactional
public void approveAll(List<ExpectedRow> targets) {
    for (ExpectedRow target : targets) {
        int changed = repository.changeOneAtVersion(
                target.id(),
                target.expectedVersion(),
                OrderStatus.PENDING,
                OrderStatus.APPROVED);

        if (changed != 1) {
            throw new BatchPreconditionFailedException(
                    "Tiền điều kiện không còn đúng cho ID " + target.id());
        }
    }
}
~~~

Ở đây `repository` là repository đã khai báo `changeOneAtVersion`; dịch vụ sử dụng cùng transaction cho toàn bộ vòng lặp. Cặp ID/version của từng hàng được giữ nguyên. Nếu lệnh thứ ba thất bại, exception khiến cả hai cập nhật trước bị rollback.

Đổi lại, cách này gửi nhiều lệnh `UPDATE` và, trong cấu hình minh họa, còn flush/clear persistence context sau từng lệnh. Khi lượng hàng lớn, cần cân nhắc JDBC batching hoặc một câu SQL chuyên biệt thay vì dựa vào vòng lặp JPQL.

### Cách B — Gửi bảng các cặp kỳ vọng xuống database

Đối với lô lớn, có thể truyền các cặp `(id, expected_version)` bằng bảng tạm, cấu trúc dữ liệu hỗ trợ của database hoặc bảng đầu vào theo lô, rồi join đúng **cả hai cột** trong một lệnh cập nhật. Ví dụ dưới đây dùng cú pháp **PostgreSQL**, không phải JPQL chuẩn:

~~~sql
WITH expected(id, expected_version) AS (
    VALUES (101, 7), (102, 4), (103, 11)
),
changed AS (
    UPDATE purchase_orders AS o
       SET status = 'APPROVED',
           version = o.version + 1
      FROM expected AS e
     WHERE o.id = e.id
       AND o.version = e.expected_version
       AND o.status = 'PENDING'
    RETURNING o.id
)
SELECT id FROM changed;
~~~

Danh sách `RETURNING` cho biết cụ thể ID nào đã sửa. Ứng dụng so sánh **tập ID trả về** với **tập ID đầu vào** và rollback nếu không khớp (với chính transaction thực hiện câu lệnh). Trong mã thật, truyền giá trị bằng tham số/bảng tạm; không nối trực tiếp dữ liệu người dùng vào chuỗi SQL. Nếu database/driver không hỗ trợ `RETURNING`, có thể dùng số hàng cập nhật và truy vấn chẩn đoán phù hợp với hệ quản trị đang dùng.

Một hướng khác là `JdbcTemplate.batchUpdate` với câu `UPDATE ... WHERE id = ? AND version = ?`. Các driver JDBC có thể báo `Statement.SUCCESS_NO_INFO` thay vì số hàng chính xác cho từng phần tử; nếu hợp đồng yêu cầu chứng minh từng hàng đã thành công, phải xử lý trường hợp này thay vì xem nó tương đương với `1`.

## 5. Diễn biến khi hai transaction cùng sửa một hàng

Giả sử ID 101 bắt đầu ở version 7:

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| T1 | Nhận yêu cầu kỳ vọng version 7 | Nhận yêu cầu kỳ vọng version 7 |
| T2 | `UPDATE ... WHERE version = 7` thành công; version thành 8 | Chưa ghi |
| T3 | Commit | Thực thi `UPDATE ... WHERE version = 7` sau khi có thể tiếp tục ghi |
| T4 | Hoàn tất | Điều kiện không còn khớp, kết quả cập nhật bằng 0; báo xung đột |

Database dùng cơ chế đồng bộ ghi/khóa hàng để quyết định tính hợp lệ của cập nhật đồng thời; chi tiết chờ và lỗi tùy isolation level, hệ quản trị và thời điểm giao dịch. Điều kiện phiên bản nằm ngay trong **câu lệnh ghi** mới là chốt an toàn. Mô hình đọc version trước rồi chạy một `UPDATE` không có điều kiện version vẫn có khoảng hở giữa đọc và ghi.

Khi nhận kết quả xung đột, tầng API có thể trả `409 Conflict` hoặc `412 Precondition Failed` nếu đang dùng giao thức điều kiện như `If-Match`. Nên trả về thông tin đủ để người gọi tải lại dữ liệu và quyết định thao tác mới; tránh tự động đọc version mới rồi ghi đè theo phiên bản mới mà chưa đánh giá lại ý định nghiệp vụ.

## 6. Persistence context, transaction và phạm vi nhất quán

**Dữ liệu đã nạp vào EntityManager có thể bị cũ.** Bulk JPQL không đồng bộ lại state của các managed entity trong persistence context. Nếu một `PurchaseOrder` đã được load trước lệnh, việc đọc lại cùng entity từ persistence context có thể vẫn thấy version/status trước khi cập nhật.

Trong Spring Data JPA, `@Modifying(flushAutomatically = true, clearAutomatically = true)` yêu cầu flush trước và clear persistence context sau câu lệnh. Điều này giúp tránh giữ state cũ, nhưng `clear` làm **mọi** entity đang managed trở thành detached, còn `flush` có thể đẩy các thay đổi khác đang chờ xuống database. Vì vậy cần chú ý ranh giới transaction và những entity khác đang được xử lý. Trong JPA thuần, xem xét gọi `flush()`, `clear()` hoặc `refresh()` đúng thời điểm khi dùng `EntityManager.createQuery(...).executeUpdate()`.

**Tất cả hoặc không cập nhật gì cần một transaction bao quanh toàn bộ công việc.** Việc nhận số hàng cập nhật thiếu nhưng vẫn commit sẽ dẫn đến cập nhật một phần. Ngược lại, nếu nghiệp vụ cho phép “cập nhật phần nào thành công, phần nào báo lỗi”, hãy thiết kế một hợp đồng *partial success* riêng, theo dõi từng ID và xác định rõ ranh giới transaction của từng phần.

**Version từng hàng không bảo vệ mọi bất biến liên hàng.** Ví dụ quy định “tổng số tiền được duyệt trong ngày không vượt hạn mức” có thể bị vi phạm dù hai giao dịch sửa hai hàng khác nhau, mỗi hàng đều vượt qua CAS của riêng nó. Với bất biến loại này, cần thiết kế thêm ràng buộc database, khóa thích hợp, cập nhật có điều kiện trên hàng tổng hợp hoặc isolation mạnh hơn tùy bài toán.

## 7. Những lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Cách xử lý |
|---|---|---|
| Có `@Version` nhưng bulk update chỉ lọc ID | Bulk update bỏ qua kiểm tra phiên bản tự động | Đưa version vào `WHERE`, tăng version trong `SET` |
| Lọc `id IN (...)` và `version IN (...)` riêng rẽ | Ghép sai cặp ID/version | Ràng buộc theo từng cặp hoặc join bảng các cặp |
| Chỉ tăng version nhưng không lọc version cũ | Vẫn có thể ghi đè yêu cầu dùng dữ liệu cũ | Dùng đồng thời `WHERE version = expected` và `SET version = version + 1` |
| Có lọc version nhưng không tăng version | Yêu cầu cũ có thể tiếp tục khớp sau cập nhật | Tăng version trong cùng câu `UPDATE` |
| Chấp nhận `changed < requested` rồi commit | Lô bị cập nhật một phần ngoài ý muốn | So sánh count/tập ID và rollback trong cùng transaction |
| Nhận ID trùng hoặc yêu cầu rỗng nhưng vẫn tính count | Kiểm tra count có thể sai hoặc `IN ()` không khả chuyển | Xác thực đầu vào, từ chối hoặc chuẩn hóa ID trước khi ghi |
| Đọc entity ngay sau bulk update mà không đồng bộ context | Đọc thấy state cũ trong bộ nhớ | Clear/refresh có chủ đích hoặc dùng transaction phù hợp |
| Tự động retry bằng version mới | Có thể ghi đè quyết định của người khác | Trả xung đột, tải lại và đánh giá lại yêu cầu |

## 8. Ví dụ kỳ vọng và cách chọn giải pháp

Xét yêu cầu ba ID 101, 102, 103:

- **Cả ba khớp ID/version/trạng thái:** cập nhật đủ ba hàng, mỗi version tăng một; commit thành công.
- **Một hàng đã đổi version:** chỉ có hai hàng khớp; nếu chế độ all-or-nothing, so sánh kết quả và rollback cả ba.
- **Một ID không tồn tại hoặc trạng thái không cho phép:** cũng là thất bại tiền điều kiện; không được giả định tất cả lỗi count đều do xung đột version.
- **Hai yêu cầu đồng thời cho cùng ID/version:** tối đa một yêu cầu được chấp nhận theo điều kiện version cũ trong lịch sử cập nhật đã commit; yêu cầu còn lại gặp kết quả không khớp hoặc lỗi đồng thời tương ứng và cần được xử lý.
- **Yêu cầu gửi lại sau khi đã thành công:** version cũ sẽ không còn khớp. Nếu API cần bảo đảm retry idempotent sau mất phản hồi, thiết kế thêm idempotency key/nhật ký thao tác, không bỏ kiểm tra version.

Lựa chọn triển khai phụ thuộc hình dạng dữ liệu: dùng **một JPQL bulk update** khi mọi hàng có cùng phiên bản kỳ vọng và cùng điều kiện chuyển trạng thái; dùng **cập nhật theo từng cặp ID/version trong một transaction** cho lô vừa phải; với lô lớn và version riêng, cân nhắc **JDBC batch có kiểm tra kết quả từng hàng** hoặc **SQL join bảng kỳ vọng và trả về ID đã cập nhật**.

Điều kiện quyết định luôn nằm tại lúc ghi: `WHERE id = ... AND version = expectedVersion` (cộng điều kiện nghiệp vụ), và phiên bản phải được tăng ngay trong cùng thao tác. Kết quả cập nhật sau đó quyết định commit hay rollback theo hợp đồng của cả lô.
