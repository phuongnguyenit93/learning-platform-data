# Pagination ownership filter — Lọc quyền sở hữu khi phân trang

## 1. Phân trang phải diễn ra trong tập dữ liệu được phép

Trong chương **Pagination Security** của Business Logic Security, pagination ownership filter là việc giới hạn tập đối tượng theo quyền sở hữu hoặc quan hệ được cấp quyền của người gọi, rồi mới xác định trang dữ liệu sẽ trả về.

Một endpoint trả mười dòng mỗi lần không tự nhiên an toàn hơn endpoint trả toàn bộ danh sách. Nếu thiếu điều kiện quyền, người gọi có thể lần lượt duyệt các trang để thu thập đơn của người khác. Nếu nội dung được lọc nhưng `totalElements` vẫn đếm toàn bộ hệ thống, API vẫn có thể làm lộ thông tin ngoài phạm vi.

Trong module này, mục tiêu là bảo vệ các quy tắc nghiệp vụ: ai được thấy đơn nào, ai có quyền thao tác trên đơn đó, điều kiện nào phải được kiểm tra khi gửi duyệt hoặc thay đổi giá. Danh sách phân trang là một đường truy cập đối tượng cần được bảo vệ như API chi tiết; nó không phải một lớp hiển thị nằm ngoài hệ thống phân quyền.

Sau bài học, người học có thể:

- Định nghĩa tập dữ liệu được phép trước khi áp dụng phân trang.
- Phát hiện lỗi lọc quyền sau `LIMIT`/`OFFSET` và lỗi đếm sai phạm vi.
- Viết truy vấn Spring Data JPA có cùng điều kiện quyền cho nội dung và count.
- Bảo vệ đường tiếp tục bằng cursor, cache và truy vấn tải chi tiết.
- Kiểm thử tính riêng tư lẫn khả năng duyệt đủ danh sách hợp lệ.

## 2. Ownership là chính sách nghiệp vụ, không chỉ một field từ client

### 2.1. Xác định đúng quan hệ sở hữu

Một đơn hàng có thể có `createdBy`, `ownerId`, `accountId` và `tenantId`. Chúng không nhất thiết có cùng ý nghĩa:

| Thuộc tính | Ý nghĩa có thể có | Điều không được suy ra tự động |
| --- | --- | --- |
| `createdBy` | Người tạo bản ghi | Luôn là người còn quyền xem sau khi bàn giao |
| `ownerId` | Người chịu trách nhiệm hiện hành | Có quyền thực hiện mọi thao tác |
| `accountId` | Tài khoản doanh nghiệp liên quan | Mọi thành viên tenant đều được xem |
| `tenantId` | Ranh giới tổ chức | Đủ để thay thế kiểm tra quyền trong tenant |

Bài sử dụng một hợp đồng đơn giản cho `/me/orders`: người gọi đang hoạt động trong tenant T chỉ được liệt kê đơn chưa bị xóa mềm mà `ownerId` là chính mình trong T. Danh tính và tenant lấy từ ngữ cảnh đã xác thực phía server.

Đây là chính sách minh họa, không phải yêu cầu mọi hệ thống phải chỉ cho chủ sở hữu đọc. Nếu có chia sẻ, phân công duyệt hoặc quyền quản lý, hãy mô hình hóa chúng thành các nhánh quyền rõ ràng. Không thay bằng một field `showAll=true` mà client tự bật.

### 2.2. Phân biệt quyền đọc và quyền thực hiện lệnh

Người được xem một đơn chưa chắc được sửa giá, gửi duyệt hoặc phê duyệt. Danh sách “đơn có thể xem” không được dùng trực tiếp làm tập “đơn có thể duyệt”. Khi người dùng chọn ID từ một trang rồi gửi lệnh, server vẫn kiểm tra lại action, đối tượng, tenant, trạng thái và phiên bản tại thời điểm ghi.

[OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) nhấn mạnh việc kiểm tra quyền thực hiện hành động trên đối tượng khi ứng dụng sử dụng ID từ client. Với danh sách, cần áp dụng cùng tư duy cho những đối tượng mà truy vấn có thể trả ra, thay vì chỉ bảo vệ API lấy một ID.

## 3. Ví dụ: vì sao lọc sau khi lấy trang là sai?

Giả sử các đơn được sắp theo thời điểm tạo giảm dần. ID ngắn dưới đây chỉ dùng minh họa thứ tự:

| Thứ tự | ID | Tenant | Owner | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | O-100 | A | Lan | PENDING |
| 2 | O-099 | B | Đức | PENDING |
| 3 | O-098 | A | Minh | PENDING |
| 4 | O-097 | A | Lan | DRAFT |
| 5 | O-096 | B | Đức | DRAFT |
| 6 | O-095 | A | Lan | PENDING |
| 7 | O-094 | A | Minh | PENDING |
| 8 | O-093 | A | Lan | DRAFT |

Lan thuộc tenant A. Với kích thước trang bằng 2 và không lọc trạng thái, hợp đồng `/me/orders` phải cho Lan:

```text
Trang 0: O-100, O-097
Trang 1: O-095, O-093
Tổng số phần tử được phép: 4
```

Cách làm sai:

```java
Page<Order> rawPage = repository.findAll(pageable);
List<Order> visible = rawPage.getContent().stream()
    .filter(order -> order.ownerId().equals(actor.id()))
    .toList();
```

Trang toàn cục đầu tiên chỉ chứa O-100 và O-099, nên sau lọc chỉ còn O-100. Trang tiếp theo có thể thiếu hoặc rỗng dù Lan vẫn còn đơn ở phía sau. Nếu giữ metadata của `rawPage`, tổng có thể là 8, làm lộ số lượng của người khác. Đoạn mã còn không kiểm tra tenant.

Đổi thành lọc cả tenant và owner sau khi lấy một trang vẫn không khôi phục được ngữ nghĩa phân trang mong muốn. Vấn đề là `OFFSET` đang đếm trong một tập rộng hơn tập người gọi được phép duyệt.

Quy tắc cần giữ là:

```text
Tập hợp lệ = điều kiện tenant
             AND điều kiện quyền đối tượng
             AND bộ lọc nghiệp vụ được phép của client

Trang = một đoạn trong thứ tự ổn định của tập hợp lệ
```

“Lọc trước phân trang” nói về ngữ nghĩa của kết quả, không ép database phải đánh giá từng biểu thức theo đúng một thứ tự vật lý. Query planner vẫn có thể chọn kế hoạch thực thi tương đương.

## 4. Đặt phạm vi quyền trong truy vấn

### 4.1. Truy vấn cho hợp đồng chỉ xem đơn của mình

Ví dụ SQL dùng tham số bind:

```sql
SELECT o.id, o.reference, o.status, o.created_at
FROM purchase_order o
WHERE o.tenant_id = :trusted_tenant_id
  AND o.owner_id = :trusted_actor_id
  AND o.deleted = false
  AND (:requested_status IS NULL OR o.status = :requested_status)
ORDER BY o.created_at DESC, o.id DESC
LIMIT :page_size
OFFSET :offset;
```

`trusted_tenant_id` và `trusted_actor_id` do server xác định. `requested_status` là bộ lọc bổ sung, không được thay thế hoặc gỡ bỏ điều kiện quyền. Các tham số kích thước và offset cũng phải được xác thực trước khi gửi xuống database.

Đơn không có owner không tự trở thành đơn công khai. Với hợp đồng này, nó không thuộc danh sách của người gọi. Nếu nghiệp vụ cần tài nguyên công khai hoặc hàng đợi chưa phân công, cần endpoint/chính sách tương ứng.

### 4.2. Bộ lọc của client chỉ được thu hẹp phạm vi được phép

Một query builder nên giữ hai phần riêng về trách nhiệm:

```text
securityPredicate = tenant AND permissionForCurrentActor
businessPredicate = status AND timeRange AND allowedSearchTerms
finalPredicate = securityPredicate AND businessPredicate
```

Không xây `finalPredicate` bằng cách để client cung cấp biểu thức có thể ghi đè `ownerId` hoặc nối `OR` ra ngoài phạm vi bảo mật.

Ví dụ có lỗi:

```sql
WHERE o.tenant_id = :tenant_id
  AND o.owner_id = :actor_id
   OR o.status = :status;
```

Điều kiện trạng thái có thể mở rộng kết quả ra ngoài cả owner lẫn tenant. Dấu ngoặc phải phản ánh đúng ý nghĩa chính sách, không chỉ làm câu SQL trông dễ đọc hơn.

### 4.3. Khi cho phép chia sẻ hoặc phân công

Nếu chính sách cho phép chủ sở hữu hoặc người được cấp quyền đọc, biểu thức có thể có dạng:

```sql
WHERE o.tenant_id = :tenant_id
  AND o.deleted = false
  AND (
    o.owner_id = :actor_id
    OR EXISTS (
      SELECT 1
      FROM order_read_grant g
      WHERE g.tenant_id = o.tenant_id
        AND g.order_id = o.id
        AND g.actor_id = :actor_id
        AND g.revoked = false
    )
  )
```

Đây là chính sách khác với `/me/orders` chỉ xem đơn sở hữu trong ví dụ chính. Nếu grant có thời hạn, loại action hoặc điều kiện trạng thái, truy vấn phải biểu diễn đủ những điều kiện đó.

`EXISTS` giúp một đơn không bị nhân thành nhiều dòng khi có nhiều grant phù hợp. Nếu dùng join, cần bảo đảm kết quả và count đều đếm đúng đơn, không đếm số quan hệ cấp quyền. Việc thêm `DISTINCT` một cách tùy tiện vào riêng truy vấn nội dung có thể vẫn để count sai.

## 5. Count, hasNext và metadata cũng thuộc phạm vi quyền

### 5.1. Count phải đếm cùng tập hợp lệ

Với hợp đồng ví dụ, count tương ứng là:

```sql
SELECT COUNT(*)
FROM purchase_order o
WHERE o.tenant_id = :trusted_tenant_id
  AND o.owner_id = :trusted_actor_id
  AND o.deleted = false
  AND (:requested_status IS NULL OR o.status = :requested_status);
```

Nếu Lan lọc PENDING, kết quả phải là 2 trong fixture trên. Không dùng count toàn tenant hoặc toàn bảng rồi gắn vào một trang đã lọc owner.

Các phần dễ bị quên gồm `totalPages`, tổng theo trạng thái, facet tìm kiếm, số mục bị ẩn, tổng tiền và liên kết trang cuối. Trong hợp đồng chỉ liệt kê đơn sở hữu, chúng cũng phải được tính trên phạm vi được phép. Một quyền riêng cho báo cáo tổng hợp, nếu có, cần được thiết kế và thể hiện rõ, không vô tình xuất hiện qua metadata của danh sách cá nhân.

### 5.2. Có thể bỏ exact count, nhưng không bỏ kiểm soát quyền

Nếu giao diện chỉ cần biết có trang sau hay không, có thể lấy tối đa `size + 1` dòng từ **tập hợp lệ**. Trả tối đa `size` dòng và dùng dòng dư để xác định `hasNext`.

Không lấy thêm một dòng bất kỳ từ tập toàn cục rồi dùng sự tồn tại của nó để báo còn dữ liệu. Điều đó vừa có thể làm lộ đối tượng ngoài phạm vi, vừa khiến người gọi tiếp tục tới những trang không có dữ liệu được phép.

Spring Data phân biệt `Page`, có metadata tổng, và `Slice`, chủ yếu phục vụ việc biết còn phần tiếp theo. Xem [Spring Data JPA — Paging, Iterating Large Results, Sorting & Limiting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html#repositories.special-parameters). Dù chọn kiểu nào, predicate quyền vẫn phải đúng.

### 5.3. Tính nhất quán dữ liệu khác với tính nhất quán chính sách

Nội dung và count có thể được lấy bằng hai câu query. Khi dữ liệu thay đổi đồng thời, tổng có thể lệch nhẹ với nội dung dù cả hai đều áp dụng đúng cùng policy.

Ví dụ PostgreSQL ở Read Committed có thể dùng snapshot khác nhau cho các câu lệnh trong cùng transaction. Đây là đặc tính cần xét khi xác định hợp đồng phản hồi, theo [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html).

Nếu yêu cầu count khớp chính xác với trang tại cùng snapshot, cần thiết kế transaction/isolation hoặc query phù hợp. `@Transactional(readOnly = true)` không tự biến mọi cấu hình thành một snapshot thống nhất. Ngược lại, việc count thiếu điều kiện owner là lỗi quyền và không thể giải thích bằng dữ liệu thay đổi đồng thời.

## 6. Minh họa Java với Spring Data JPA

Ví dụ dưới sử dụng Java có hỗ trợ record và text block. Entity `PurchaseOrder` có các thuộc tính `tenantId`, `ownerId`, `deleted`, `status`, `createdAt`, `id` và `reference`. Các kiểu domain, xác thực và exception cần được hiện thực theo ứng dụng.

DTO chỉ chứa các field được phép hiển thị:

```java
package com.example.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderSummary(
    UUID id,
    String reference,
    OrderStatus status,
    Instant createdAt
) {}
```

Repository truy vấn cả dữ liệu và count trong cùng phạm vi:

```java
public interface OwnedOrderQuery extends Repository<PurchaseOrder, UUID> {
    @Query(
        value = """
            select new com.example.orders.OrderSummary(
                o.id, o.reference, o.status, o.createdAt)
            from PurchaseOrder o
            where o.tenantId = :tenantId
              and o.ownerId = :actorId
              and o.deleted = false
              and (:state is null or o.status = :state)
            """,
        countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.tenantId = :tenantId
              and o.ownerId = :actorId
              and o.deleted = false
              and (:state is null or o.status = :state)
            """
    )
    Page<OrderSummary> findOwned(
        @Param("tenantId") UUID tenantId,
        @Param("actorId") UUID actorId,
        @Param("state") OrderStatus state,
        Pageable pageable
    );
}
```

Spring Data JPA hỗ trợ khai báo truy vấn bằng `@Query`, bao gồm việc cung cấp query đếm cho phân trang. Tài liệu chính thức nằm tại [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html).

Service tạo phạm vi và giới hạn phân trang phía server:

```java
@Service
public class MyOrderService {
    private final CurrentActor currentActor;
    private final OwnedOrderQuery queries;

    public MyOrderService(CurrentActor currentActor, OwnedOrderQuery queries) {
        this.currentActor = currentActor;
        this.queries = queries;
    }

    @Transactional(readOnly = true)
    public Page<OrderSummary> list(OrderStatus state, int page, int size) {
        Actor actor = currentActor.requireActiveTenantActor();
        actor.requireCapability("ORDER_LIST_OWN");

        if (page < 0 || page > 1_000 || size < 1 || size > 100) {
            throw new InvalidPaginationException();
        }

        Pageable safePage = PageRequest.of(
            page,
            size,
            Sort.by(Sort.Direction.DESC, "createdAt", "id")
        );
        return queries.findOwned(actor.tenantId(), actor.id(), state, safePage);
    }
}
```

Những điểm cần giữ khi áp dụng ví dụ:

- Service không nhận `actorId` hoặc `tenantId` tự do từ query string để thay cho danh tính đã xác thực.
- `requireActiveTenantActor` phải xác minh tài khoản và quyền hoạt động trong tenant đang chọn. Thiếu context phải bị từ chối, không chuyển sang truy vấn không có predicate quyền.
- Giới hạn số trang và kích thước ở đây là lựa chọn minh họa. Ứng dụng cần chọn mức phù hợp với chi phí truy vấn và UX.
- Sort được server cố định. Nếu cho client chọn sort, ánh xạ từ một tập field được phép; không nối biểu thức SQL hoặc cho truy cập field nhạy cảm tùy ý.
- Repository là thành phần nội bộ của service; không tự xuất trực tiếp thành endpoint bỏ qua bước tạo context tin cậy.
- Projection giúp tránh serialize entity với quan hệ lazy hoặc field nhạy cảm không cần thiết. Quyền đọc một hàng không tự cho phép đọc mọi field của hàng đó.
- Không thay `Pageable` đã kiểm tra bằng `Pageable.unpaged()` khi parse lỗi. Lỗi input cần có kết quả rõ ràng, không mở rộng lượng dữ liệu trả về.

Nếu chính sách được mở rộng thành owner hoặc người được chia sẻ, phải sửa đồng bộ predicate nội dung, count và mọi đường tải chi tiết. Nên tập trung cách xây phạm vi trong một thành phần có thể kiểm thử để giảm nguy cơ chúng lệch nhau.

## 7. Thứ tự ổn định, offset và cursor

### 7.1. Thêm khóa phân xử khi giá trị sort trùng

`ORDER BY created_at DESC` chưa xác định duy nhất thứ tự nếu nhiều đơn có cùng thời điểm tạo. Thêm khóa duy nhất như `id` làm tie-breaker:

```sql
ORDER BY o.created_at DESC, o.id DESC
```

PostgreSQL lưu ý rằng `LIMIT`/`OFFSET` cần thứ tự có thể dự đoán và offset lớn có thể tốn công xử lý các dòng bị bỏ qua. Xem [PostgreSQL — LIMIT and OFFSET](https://www.postgresql.org/docs/18/queries-limit.html).

Thứ tự ổn định giúp kiểm thử tính đầy đủ và tránh trùng do tie, nhưng không tự bảo vệ ownership. Một truy vấn sắp xếp rất ổn định vẫn có thể trả dữ liệu của người khác nếu thiếu predicate quyền.

### 7.2. Keyset vẫn phải áp dụng ownership trên mỗi request

Với cặp khóa `created_at` và `id` đều không null, cùng chiều giảm dần, phần điều kiện tiếp tục có thể là:

```sql
AND (
  o.created_at < :last_created_at
  OR (o.created_at = :last_created_at AND o.id < :last_id)
)
ORDER BY o.created_at DESC, o.id DESC
LIMIT :size_plus_one;
```

Đoạn này được nối bằng `AND` vào truy vấn đã có tenant, owner và bộ lọc nghiệp vụ. Không dùng cursor để đi thẳng vào một truy vấn toàn bảng thiếu quyền.

Nếu có dòng dư, cursor tiếp theo trỏ từ dòng cuối **được trả cho client**, không lấy dòng dư làm mốc rồi vô tình bỏ qua nó. Với kiểu dữ liệu, null hoặc chiều sort khác, biểu thức so sánh cũng phải thay tương ứng.

Trong hợp đồng bài này, `totalElements`, nếu có, là tổng của tập được phép sau bộ lọc nghiệp vụ, không phải số còn lại sau mốc cursor. Cần định nghĩa rõ sự khác biệt này để không gắn một count sai ý nghĩa vào response.

### 7.3. Token tiếp tục không phải giấy cấp quyền

Google AIP-158 mô tả page token chỉ dùng chỉ vị trí tiếp tục, không cấp quyền truy cập tài nguyên; request có token vẫn phải được xét quyền. Xem [AIP-158 — Pagination](https://google.aip.dev/158).

Trong thiết kế của ứng dụng, token hoặc bản ghi cursor phía server nên ràng buộc với những yếu tố cần giữ cố định, chẳng hạn:

```text
endpoint / loại danh sách
tenant và actor hoặc phạm vi truy cập tương ứng
bộ lọc đã chuẩn hóa và cách sort
mốc tiếp tục
phiên bản định dạng token và thời hạn
policy epoch nếu cơ chế thu hồi sử dụng nó
```

Đây là lựa chọn thiết kế để ngăn dùng nhầm cursor giữa các ngữ cảnh, không phải tuyên bố mọi API phải có đúng các field này.

Token có thể là một tham chiếu ngẫu nhiên tới trạng thái phía server hoặc một cấu trúc được bảo vệ bằng cơ chế mật mã đã được thư viện triển khai. Base64 đơn thuần không chống sửa và không che nội dung. Chữ ký/MAC bảo vệ tính toàn vẹn nhưng không làm payload bí mật; tránh đưa thông tin nhạy cảm vào phần client có thể đọc.

Dù token hợp lệ, câu query tiếp theo vẫn áp dụng quyền hiện hành theo hợp đồng. Không nhận `ownerId` trong token rồi dùng nó thay actor hiện tại mà không đối chiếu. Token của Lan không được biến request của Minh thành request mang quyền của Lan.

## 8. Quyền sở hữu thay đổi giữa các trang

Giả sử Lan đọc trang đầu rồi một đơn chưa đọc được bàn giao sang Minh. Ở mô hình danh sách theo quyền hiện hành, request trang sau không được trả đơn đó cho Lan chỉ vì cursor được tạo trước khi bàn giao.

Có ba vấn đề cần tách biệt:

| Vấn đề | Ví dụ | Cách định nghĩa hợp đồng |
| --- | --- | --- |
| Quyền thay đổi | Đơn đổi owner hoặc grant bị thu hồi | Xét quyền hiện hành hoặc cơ chế snapshot quyền được thiết kế rõ |
| Tập dữ liệu thay đổi | Có đơn mới, xóa đơn cũ | Cho phép dịch chuyển trang hoặc cung cấp snapshot dữ liệu |
| Khóa sort thay đổi | Cập nhật một field đang dùng làm mốc | Chọn khóa ổn định hoặc chấp nhận/quản lý trùng, thiếu theo hợp đồng |

Keyset giảm một số vấn đề dịch chuyển do offset, nhưng không tự tạo snapshot bất biến cho cả lần duyệt. Ngược lại, snapshot danh sách ID không mặc nhiên đóng băng quyền đọc các ID đó vĩnh viễn.

Nếu sản phẩm cần xuất báo cáo tại một thời điểm, phải xác định riêng quyền tạo snapshot, quyền tải nội dung và cách xử lý thu hồi quyền. Không giữ một transaction database mở xuyên nhiều thao tác của người dùng chỉ để có danh sách đứng yên mà không xét chi phí và vòng đời.

Dữ liệu đã được người dùng tải hợp lệ trước khi thu hồi không thể được “thu hồi khỏi bộ nhớ” chỉ bằng thay cursor. Điều cần bảo vệ là các phản hồi và lần truy cập mới theo chính sách của hệ thống.

## 9. Đừng để cache, truy vấn phụ và quan hệ làm mất phạm vi

### 9.1. Cache trang theo đúng ngữ cảnh

Cache chỉ dùng key như `orders:page:0` hoặc `tenant:A:page:0` có thể phục vụ trang của Lan cho Minh. Key phải phản ánh những yếu tố làm thay đổi tập được phép và bản chiếu trả về: tenant, actor/phạm vi quyền, bộ lọc, sort, vị trí trang và phiên bản policy cần thiết.

Chọn actor trong key vẫn chưa giải quyết việc quyền của chính actor đó vừa bị thu hồi. Cần cơ chế vô hiệu hóa, phiên bản hóa hoặc xét lại quyền theo yêu cầu của hệ thống. Một TTL còn hiệu lực không tự cho phép tiếp tục trả dữ liệu sau thời điểm thu hồi mà sản phẩm cam kết.

Kiểm tra cả cache nội bộ và cache ở gateway nếu có. Không chỉ thử đường cache miss, vì lỗi phổ biến xuất hiện ở lần đọc sau khi một actor khác đã làm nóng cache.

### 9.2. Phân trang ID rồi tải entity phải giữ quyền

Một số hệ thống lấy trang ID trước rồi query chi tiết bằng `WHERE id IN (...)`. Tập ID đã chọn cần là tập hợp lệ, và bước tải chi tiết phải giữ phạm vi cùng chính sách tương ứng.

Điều này đặc biệt quan trọng khi quyền có thể đổi giữa hai bước hoặc nguồn ID là search index cập nhật chậm. Đừng coi ID đến từ index/cache là bằng chứng quyền. Nếu bước cuối loại bớt đối tượng do quyền vừa đổi, phải xử lý metadata và khả năng tiếp tục theo hợp đồng, không lộ số lượng hoặc thông tin bị ẩn.

Với policy chỉ có thể xét ở dịch vụ ngoài, có thể phải quét ứng viên theo từng đợt rồi lấy đủ đối tượng hợp lệ. Thiết kế đó cần ngân sách quét, cursor tiến triển và ngữ nghĩa metadata riêng. Không lấy một trang ứng viên, lọc trong Java rồi giả vờ đó là một trang đầy đủ của tập được phép.

### 9.3. Quan hệ con và đường dẫn cha vẫn cần kiểm tra

Với `/accounts/{accountId}/orders`, cần kiểm tra quyền đối với account ở đường dẫn và ràng buộc đơn thuộc đúng account đó, trong tenant được phép. Field `accountId` không được gỡ bỏ điều kiện tenant hoặc membership.

Khi serialize dòng đơn, các dữ liệu liên quan như ghi chú nội bộ, báo giá nhà cung cấp hoặc tài khoản thanh toán cũng cần chính sách đọc tương ứng. Lọc owner của bảng đơn không tự cấp quyền đọc mọi quan hệ được join hoặc fetch.

### 9.4. Row-level security là lớp hỗ trợ

Nếu dùng PostgreSQL RLS, kiểm tra role của kết nối thực tế và policy áp dụng. Owner của bảng, superuser hoặc role có quyền bỏ qua RLS có thể làm kết quả khác mong đợi; tài liệu mô tả các trường hợp này tại [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).

Nếu truyền tenant/actor qua trạng thái kết nối, phải quản lý vòng đời đúng khi connection pool tái sử dụng kết nối. Không để ngữ cảnh của request trước còn ảnh hưởng request sau. RLS cũng không thay thế thiết kế cache hay quyết định quyền của API ghi.

## 10. Hiệu năng không được đổi lấy việc bỏ lọc quyền

Một truy vấn có index phù hợp thường giúp việc áp dụng ownership trước pagination rẻ hơn. Với hợp đồng owner-only và sort như trên, có thể cân nhắc index theo tenant, owner, thời điểm và ID; điều kiện xóa mềm cũng ảnh hưởng lựa chọn index.

Ví dụ PostgreSQL để minh họa hướng thiết kế:

```sql
CREATE INDEX ix_order_owned_page
ON purchase_order (tenant_id, owner_id, created_at DESC, id DESC)
WHERE deleted = false;
```

Index cần được đánh giá theo dữ liệu, bộ lọc và kế hoạch truy vấn thật. Nó không phải một policy phân quyền: câu SQL thiếu owner vẫn thiếu bảo vệ dù index có owner.

Những giới hạn vận hành cần đặt gồm kích thước trang, offset tối đa nếu dùng offset, các sort/filter được hỗ trợ, thời gian truy vấn và mức sử dụng theo actor/tenant. Exact count trên một tập lớn có thể tốn chi phí; có thể chọn `Slice` hoặc cursor mà vẫn giữ đúng phạm vi.

Đừng xử lý query chậm bằng cách bỏ predicate quyền, chuyển sang `findAll()` rồi lọc một phần trong bộ nhớ, hoặc cho `size=0` mang nghĩa “trả toàn bộ” mà không có hợp đồng và quyền riêng.

## 11. Kiểm thử ownership qua toàn bộ lần duyệt

### 11.1. Oracle phải độc lập với truy vấn đang kiểm tra

Dùng fixture có ít nhất hai tenant, hai owner trong cùng tenant, dữ liệu xen kẽ theo sort, nhiều bản ghi trùng thời điểm tạo và nhiều trạng thái. Tập ID đúng phải được biết từ dữ liệu fixture, không tính bằng chính hàm policy/query đang cần kiểm thử.

Với dữ liệu tĩnh của ví dụ, oracle của Lan là:

```text
Không lọc trạng thái:
  tập ID = {O-100, O-097, O-095, O-093}
  totalElements = 4
  size = 2 → hai trang có dữ liệu, không có ID trùng

Lọc PENDING:
  tập ID = {O-100, O-095}
  totalElements = 2
```

Chỉ kiểm tra “mọi dòng hiện có đều thuộc Lan” là chưa đủ. Một implementation trả mảng rỗng cho mọi request cũng thỏa assertion đó. Phải kiểm tra cả tính đầy đủ của tập được phép trong điều kiện dữ liệu tĩnh.

### 11.2. Khung test duyệt hết các trang

Ví dụ cấu trúc JUnit/AssertJ; `client` và `fixture` là test harness cần tự hiện thực với ứng dụng thật:

```java
@Test
void traversesExactlyTheOwnedOrders() {
    Fixture fx = fixture.interleavedOwnersAndTenants();
    Set<UUID> expected = fx.lanOwnedOrderIds();
    Set<UUID> seen = new HashSet<>();
    int pageNumber = 0;
    OrderPage page;

    do {
        page = client.listMyOrders(fx.lanSession(), pageNumber, 2);
        assertThat(page.totalElements()).isEqualTo(expected.size());
        assertThat(page.items()).hasSizeLessThanOrEqualTo(2);

        for (OrderSummary row : page.items()) {
            assertThat(expected).contains(row.id());
            assertThat(seen.add(row.id())).isTrue();
        }
        pageNumber++;
        assertThat(pageNumber).isLessThan(10);
    } while (page.hasNext());

    assertThat(seen).containsExactlyInAnyOrderElementsOf(expected);
}
```

Giới hạn vòng lặp giúp test phát hiện `hasNext` sai hoặc cursor không tiến triển. Với fixture đã xác định, thêm assertion cho thứ tự và kích thước từng trang mong đợi để bắt lỗi trang thiếu do post-filter.

Harness phải đi qua xác thực, service và persistence thật phù hợp mục tiêu. Mock repository trả sẵn đúng dữ liệu không chứng minh query ownership đúng. Các record `Fixture` và `OrderPage` chỉ là kiểu minh họa; không phải API sẵn có của JUnit hoặc Spring.

### 11.3. Ma trận tấn công và hồi quy

| Ca | Cách thay đổi yêu cầu hoặc dữ liệu | Oracle |
| --- | --- | --- |
| Đổi owner | Gửi `ownerId` của Minh vào API cá nhân | Không mở rộng sang đơn Minh; xử lý field ngoài hợp đồng rõ ràng |
| Đổi tenant | Chọn tenant mà Lan không phải thành viên | Bị từ chối, không fallback sang truy vấn rộng |
| Tenant và owner xen kẽ | Đặt dòng bị cấm ở đầu, giữa, cuối trang toàn cục | Các trang của tập hợp lệ vẫn đầy đủ |
| Lọc trạng thái | PENDING, DRAFT, không truyền state | Nội dung, tổng và hasNext cùng phạm vi |
| Metadata | Thêm nhiều đơn của tenant khác | Nội dung và metadata cá nhân không tiết lộ thay đổi đó |
| Ties | Nhiều đơn có cùng createdAt | Thứ tự ổn định, không trùng hoặc mất dòng trên fixture tĩnh |
| Đổi cursor | Dùng token của Lan cho Minh | Không nhận dữ liệu theo quyền Lan |
| Sửa token | Đổi mốc, bộ lọc hoặc payload token | Xử lý token sai theo hợp đồng; không bỏ predicate quyền |
| Thu hồi quyền | Đổi owner sau trang đầu rồi gọi tiếp | Không trả đối tượng ngoài quyền hiện hành của mô hình đã chọn |
| Cache hit | Lan đọc rồi Minh gọi cùng URL | Không nhận trang hoặc metadata của Lan |
| Tải chi tiết hai bước | Đổi quyền giữa lấy ID và hydrate | Không lộ field của đối tượng đã mất quyền theo hợp đồng |
| Tham số biên | Page âm, size quá lớn, sort không hỗ trợ | Bị giới hạn/từ chối, không chuyển thành unpaged |
| Quan hệ được chia sẻ | Hai grant hợp lệ cho cùng đơn | Một đơn không bị nhân thành hai item hoặc hai lượt count |
| Trạng thái đọc | Duyệt mọi trang và thử lại GET | Không gửi duyệt, chốt giá, giữ kho hoặc phát lệnh nghiệp vụ |

Với ca metadata, so sánh những thành phần có nghĩa trong hợp đồng: ID trả về, tổng và việc có trang sau. Không so bằng tuyệt đối hai chuỗi token nếu token có nonce hoặc thời gian phát hành khác nhau. Không kết luận đã loại bỏ mọi kênh suy luận về thời gian chỉ từ một ca thêm dữ liệu ngoài tenant.

Với ca thu hồi quyền hoặc race, điều phối điểm thay đổi bằng test harness có kiểm soát. Các assertion về tổng chính xác và không thiếu dòng phải chạy trên fixture tĩnh hoặc snapshot đúng hợp đồng; đừng trộn chúng với test dữ liệu đang thay đổi mà không xác định điểm quan sát.

## 12. Liên hệ với các lệnh nghiệp vụ phía sau danh sách

Giả sử giao diện hiển thị nút “Duyệt tất cả kết quả” sau khi lọc danh sách. Những điều kiện sau vẫn cần được bảo vệ:

1. Danh sách để xem có thể rộng hơn phạm vi được duyệt.
2. Quyền và trạng thái có thể đổi sau khi trang được tải.
3. Cursor chỉ mô tả vị trí đọc, không phải một manifest cấp quyền ghi.
4. Client có thể tự thêm ID chưa từng xuất hiện trong giao diện.
5. Giá, người duyệt và phiên bản hiện hành phải được xác định hoặc kiểm tra lại tại lệnh ghi.

Nếu server tạo selection manifest cho thao tác hàng loạt, manifest cần gắn actor, tenant, action và tập lựa chọn có ý nghĩa. Khi thực thi, áp dụng lại policy theo mô hình quyền đã chọn và bảo vệ invariant của từng đối tượng/toàn nhóm. Không dùng câu query phân trang cá nhân làm bằng chứng duy nhất rằng một lệnh phê duyệt đã được cấp quyền.

## 13. Bài tập thực hành

Một hệ thống có đoạn xử lý:

```text
1. Nhận ownerId, page và size từ query string.
2. Gọi findAll(pageable).
3. Lọc nội dung theo ownerId trong Java.
4. Giữ totalElements của kết quả ban đầu.
5. Cache bằng key tenantId + page + size.
6. Khi có cursor, bỏ bước xét quyền vì token do server tạo.
```

Hãy thiết kế lại cho hợp đồng “người dùng chỉ xem đơn đang thuộc mình trong tenant đang hoạt động”:

- Xác định nguồn tin cậy của actor và tenant, cùng cách xử lý ownerId do client gửi.
- Viết predicate dùng chung về ý nghĩa cho nội dung và count, có bộ lọc trạng thái tùy chọn.
- Chọn sort có thứ tự duy nhất và giới hạn page/size phù hợp.
- Thiết kế key cache và cơ chế phản ứng khi đổi owner hoặc thu hồi quyền.
- Thiết kế cursor không thay thế authorization và không lộ dữ liệu nhạy cảm.
- Tạo fixture xen kẽ để chứng minh không có dữ liệu trái phép, không thiếu dữ liệu hợp lệ và không lộ tổng ngoài phạm vi.

Một ownership filter đúng giữ cho nội dung, metadata và mọi đường tiếp tục đều hoạt động trong tập đối tượng được cấp quyền, đồng thời không biến kết quả đọc thành quyền thực hiện lệnh nghiệp vụ.
