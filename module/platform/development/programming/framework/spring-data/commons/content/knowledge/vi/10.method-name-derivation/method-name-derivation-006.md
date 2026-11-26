# And, Or và giới hạn diễn đạt nhóm điều kiện

Trong chương **Suy diễn tên phương thức** của Spring Data Commons (`SPRING_DATA_COMMONS`), `And` và `Or` cho phép kết hợp nhiều điều kiện trong tên query method. Khi hai từ khóa cùng xuất hiện, thứ tự nhóm điều kiện quyết định những bản ghi nào được chọn.

Bài này tập trung vào cách đọc cấu trúc Boolean của derived query, giới hạn đặt nhóm trong tên và cách chuyển sang một cơ chế truy vấn phù hợp khi biểu thức trở nên phức tạp. Commons cung cấp phần phân tích cùng abstraction repository; module kho dữ liệu quyết định cách thực thi và những toán tử được hỗ trợ.

## 1. And và Or kết hợp các điều kiện như thế nào?

Giả sử mỗi ký hiệu `A`, `B`, `C` là một điều kiện đã được xác định rõ.

| Cách kết hợp | Ý nghĩa |
| --- | --- |
| `A AND B` | Cả A và B đều phải đúng. |
| `A OR B` | Ít nhất một điều kiện đúng; cả hai cùng đúng vẫn thỏa. |
| `A AND B AND C` | Cả ba điều kiện đều phải đúng. |
| `A OR B OR C` | Có ít nhất một trong ba điều kiện đúng. |

`Or` không có nghĩa “thử nhánh thứ nhất, không có dữ liệu thì mới chạy nhánh thứ hai”. Nó kết hợp các điều kiện trong truy vấn, không mô tả một chiến lược fallback giữa hai lần gọi repository.

Ví dụ:

```java
List<Ticket> findByStatusAndPriority(
    TicketStatus status,
    TicketPriority priority
);
```

yêu cầu đồng thời khớp trạng thái và độ ưu tiên.

Còn:

```java
List<Ticket> findByStatusOrPriority(
    TicketStatus status,
    TicketPriority priority
);
```

chấp nhận ticket khớp trạng thái, khớp độ ưu tiên hoặc khớp cả hai.

Dạng thứ hai thường có tập kết quả rộng hơn với cùng dữ liệu và cùng giá trị so sánh. Việc đổi `And` thành `Or` là thay đổi nghiệp vụ, không phải thay đổi cách viết tên cho dễ đọc.

## 2. Quy tắc nhóm: And kết hợp chặt hơn Or

Trong cơ chế phân tích `PartTree`, phần điều kiện được chia thành các nhánh `Or`; trong mỗi nhánh, các phần được nối bằng `And`. Có thể hình dung cấu trúc tổng quát:

```text
(nhánh AND thứ nhất)
OR
(nhánh AND thứ hai)
OR
...
```

Vì vậy:

```text
AAndBOrC
```

được hiểu là:

```text
(A AND B) OR C
```

Còn:

```text
AOrBAndC
```

được hiểu là:

```text
A OR (B AND C)
```

Việc parser tách nhánh `Or` trước không có nghĩa `Or` có độ ưu tiên kết hợp cao hơn. Nó tạo những nhánh ở tầng ngoài, còn `And` nối các điều kiện bên trong từng nhánh. Cấu trúc này được thể hiện trong [mã nguồn PartTree của Spring Data Commons](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/query/parser/PartTree.java).

Một bảng đọc nhanh, trong đó A, B, C, D chỉ là ký hiệu điều kiện:

| Mẫu tên trong predicate | Cấu trúc điều kiện |
| --- | --- |
| `AAndBOrC` | `(A AND B) OR C` |
| `AOrBAndC` | `A OR (B AND C)` |
| `AAndBOrCAndD` | `(A AND B) OR (C AND D)` |
| `AOrBOrCAndD` | `A OR B OR (C AND D)` |

Các mẫu ký hiệu không phải tên method để sao chép nguyên vào repository. Method thực tế phải dùng các biểu thức thuộc tính tồn tại trong domain model.

Cũng không nên suy ra thứ tự đánh giá vật lý từ thứ tự chữ trong tên. Đây là ngữ nghĩa kết hợp điều kiện; kho dữ liệu có thể chọn kế hoạch thực thi khác.

## 3. Ví dụ dễ đọc nhầm: điều kiện tenant chỉ nằm ở một nhánh

Giả sử `Ticket` đã được ánh xạ theo module và có các thuộc tính:

| Thuộc tính | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh ticket. |
| `tenantId` | `String` | Tổ chức sở hữu ticket. |
| `status` | `TicketStatus` | Ví dụ `OPEN`, `CLOSED`. |
| `priority` | `TicketPriority` | Ví dụ `LOW`, `HIGH`. |

Yêu cầu nghiệp vụ:

> Trong tenant đang xét, lấy ticket đang mở hoặc có độ ưu tiên cao.

Đặt:

```text
A = tenantId khớp tenant đang xét
B = status khớp OPEN
C = priority khớp HIGH

Yêu cầu: A AND (B OR C)
```

Một tên dễ được viết theo câu tiếng Việt:

```java
List<Ticket> findByTenantIdAndStatusOrPriority(
    String tenantId,
    TicketStatus status,
    TicketPriority priority
);
```

Nhưng phép tách thực tế là:

```text
Nhánh 1: TenantId AND Status
Nhánh 2: Priority

Toàn bộ: (TenantId AND Status) OR Priority
```

Nhánh thứ hai không chứa điều kiện tenant. Khi truyền `HIGH`, ticket có ưu tiên cao thuộc tenant khác cũng có thể thỏa truy vấn.

Đây là lỗi hợp đồng truy vấn có thể tồn tại dù repository khởi tạo thành công: tên hợp lệ và các thuộc tính đều tồn tại, nhưng biểu thức khác yêu cầu nghiệp vụ.

### Dữ liệu phản ví dụ

Với tenant cần tìm là `ACME`:

| id | tenantId | status | priority | Yêu cầu đúng | Tên method ở trên |
| --- | --- | --- | --- | --- | --- |
| 101 | ACME | OPEN | LOW | Chọn. | Chọn. |
| 102 | ACME | CLOSED | HIGH | Chọn. | Chọn. |
| 103 | ACME | CLOSED | LOW | Loại. | Loại. |
| 104 | OTHER | CLOSED | HIGH | Loại. | Chọn sai. |
| 105 | OTHER | OPEN | LOW | Loại. | Loại. |
| 106 | ACME | OPEN | HIGH | Chọn. | Chọn. |

Ticket 104 là dữ liệu phân biệt hai biểu thức:

```text
A = false, B = false, C = true

A AND (B OR C)  = false
(A AND B) OR C  = true
```

Nếu chỉ thử dữ liệu của tenant ACME, rất dễ không nhận ra sai lệch này.

## 4. Không có cú pháp ngoặc tùy ý trong derived method name

Tên query method không cung cấp dấu ngoặc Boolean để người viết chọn cách nhóm bất kỳ.

Không thể viết một tên Java như:

```text
findByTenantIdAnd(StatusOrPriority)
```

để biểu đạt ngoặc của biểu thức. Đây cũng không phải một tên phương thức Java hợp lệ.

Các biến thể thêm từ mô tả như `Group`, `Grouped`, `With` không tự tạo nhóm. Đặt một từ trong phần chủ thể trước `By` cũng không làm thay đổi cấu trúc điều kiện sau `By`.

Dấu gạch dưới trong property expression có vai trò hỗ trợ phân giải đường dẫn thuộc tính; nó không phải dấu ngoặc cho `And` và `Or`. Không dùng tên kiểu:

```text
findByTenantIdAnd_StatusOrPriority
```

rồi kỳ vọng điều kiện trở thành `TenantId AND (Status OR Priority)`.

Tương tự, `Distinct`, `Top`, `First` hoặc `OrderBy` không thay đổi độ ưu tiên kết hợp Boolean. Chúng có trách nhiệm khác trong truy vấn.

## 5. Viết lại bằng phép phân phối khi biểu thức còn nhỏ

Có thể biến đổi yêu cầu:

```text
A AND (B OR C)
```

thành:

```text
(A AND B) OR (A AND C)
```

Trong ví dụ, đặt điều kiện tenant ở cả hai nhánh:

```java
List<Ticket> findByTenantIdAndStatusOrTenantIdAndPriority(
    String tenantForStatus,
    TicketStatus status,
    String tenantForPriority,
    TicketPriority priority
);
```

Cấu trúc lúc này là:

```text
(tenantId = tenantForStatus AND status = status)
OR
(tenantId = tenantForPriority AND priority = priority)
```

Phía gọi phải truyền cùng một tenant cho hai vị trí:

```java
List<Ticket> tickets =
    repository.findByTenantIdAndStatusOrTenantIdAndPriority(
        "ACME",
        TicketStatus.OPEN,
        "ACME",
        TicketPriority.HIGH
    );
```

Với bộ dữ liệu ở trên, kết quả mong đợi gồm 101, 102 và 106.

### Tại sao cần lặp cả đối số?

Derived query có hai lần xuất hiện của phép so sánh `TenantId`. Với các phép so sánh bằng trong chữ ký này, mỗi lần xuất hiện tiêu thụ một giá trị nghiệp vụ.

| Vị trí đối số | Phần điều kiện nhận giá trị |
| --- | --- |
| 1 | Tenant của nhánh trạng thái. |
| 2 | Trạng thái của nhánh thứ nhất. |
| 3 | Tenant của nhánh độ ưu tiên. |
| 4 | Độ ưu tiên của nhánh thứ hai. |

Tên biến Java giúp người đọc hiểu vai trò; nó không làm framework tự dùng lại đối số thứ nhất cho một lần xuất hiện khác của cùng thuộc tính.

Nếu truyền hai tenant khác nhau, method sẽ diễn đạt hai nhánh theo hai tenant khác nhau. Đó không còn là yêu cầu ban đầu.

### Bọc lời gọi để giữ bất biến tại một chỗ

Một default method có thể giữ việc lặp giá trị trong repository:

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    List<Ticket> findByTenantIdAndStatusOrTenantIdAndPriority(
        String tenantForStatus,
        TicketStatus status,
        String tenantForPriority,
        TicketPriority priority
    );

    default List<Ticket> findForTenant(
        String tenantId,
        TicketStatus status,
        TicketPriority priority
    ) {
        return findByTenantIdAndStatusOrTenantIdAndPriority(
            tenantId,
            status,
            tenantId,
            priority
        );
    }
}
```

`findForTenant` có thân triển khai, nên không cần tên của nó diễn đạt một derived query. Phần suy diễn vẫn nằm ở method trừu tượng được gọi bên trong.

Cách bọc này tránh lặp đối số ở mọi nơi gọi; nó không tạo thêm khả năng đặt ngoặc cho parser.

## 6. Khi phép phân phối làm tên phình lớn

Không phải biểu thức nào cũng nên được chuyển thành một tên dài.

Ví dụ:

```text
(A OR B) AND (C OR D)
```

có thể phân phối thành:

```text
(A AND C)
OR
(A AND D)
OR
(B AND C)
OR
(B AND D)
```

Dạng ký hiệu tương ứng là:

```text
AAndCOrAAndDOrBAndCOrBAndD
```

Chỉ hai nhóm lựa chọn đã tạo bốn nhánh. Thêm nhiều nhóm có thể làm số nhánh tăng nhanh, kéo theo việc lặp điều kiện và đối số.

Cần cân nhắc chuyển cơ chế truy vấn khi:

- Một điều kiện chung phải lặp lại trong nhiều nhánh.
- Có nhiều nhóm lựa chọn hoặc bộ lọc bật, tắt theo đầu vào.
- Người đọc cần dựng lại biểu thức trên giấy để hiểu tên.
- Việc thêm một điều kiện đòi hỏi sửa nhiều đoạn giống nhau.
- Có nguy cơ truyền giá trị khác nhau cho những đối số vốn phải giống nhau.

Phân phối là một lựa chọn biểu đạt logic, không phải bảo đảm về hiệu năng. Hai cách biểu diễn tương đương cần được đánh giá theo cách module và kho dữ liệu thực thi.

## 7. Dùng declared query để thể hiện nhóm rõ ràng

Với Spring Data JPA, JPQL có thể biểu đạt trực tiếp dấu ngoặc. Ví dụ dưới đây **riêng cho module JPA**, giả sử `Ticket` là tên entity và các thuộc tính đã được mapping đúng:

```java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface TicketJpaRepository
        extends JpaRepository<Ticket, Long>,
                JpaSpecificationExecutor<Ticket> {

    @Query(
        "select t from Ticket t "
        + "where t.tenantId = :tenantId "
        + "and (t.status = :status or t.priority = :priority)"
    )
    List<Ticket> findForTenant(
        @Param("tenantId") String tenantId,
        @Param("status") TicketStatus status,
        @Param("priority") TicketPriority priority
    );
}
```

Ở đây:

- Nhóm `status OR priority` được viết bằng ngoặc trong JPQL.
- Điều kiện tenant bao ngoài toàn bộ nhóm.
- Tenant chỉ có một named parameter và một vị trí trong chữ ký.
- Tên `findForTenant` không cần mã hóa cấu trúc Boolean trong trường hợp declared query này được chọn.

Ví dụ giả định query lookup strategy cho phép sử dụng khai báo `@Query`. Không áp dụng cách đọc tên derived query để thay cho nội dung JPQL có hiệu lực. Cơ chế khai báo của JPA được trình bày trong [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html).

Không đem annotation JPA sang một module khác rồi kỳ vọng có cùng ngôn ngữ truy vấn. Nếu dùng MongoDB hay một store khác, cần chọn declared query hoặc API tiêu chí tương ứng của module đó.

## 8. Dùng Specification cho các nhóm cần ghép động

Repository JPA ở phần trước đã mở rộng `JpaSpecificationExecutor<Ticket>`. Có thể xây từng điều kiện rồi ghép thành cây rõ ràng:

```java
import org.springframework.data.jpa.domain.Specification;

Specification<Ticket> sameTenant =
    (root, query, cb) ->
        cb.equal(root.get("tenantId"), tenantId);

Specification<Ticket> requestedStatus =
    (root, query, cb) ->
        cb.equal(root.get("status"), status);

Specification<Ticket> requestedPriority =
    (root, query, cb) ->
        cb.equal(root.get("priority"), priority);

Specification<Ticket> criteria =
    sameTenant.and(requestedStatus.or(requestedPriority));

List<Ticket> tickets = repository.findAll(criteria);
```

Trong đoạn mã, `tenantId`, `status`, `priority` là các giá trị đầu vào của service; `repository` là `TicketJpaRepository`.

Cặp ngoặc của lời gọi:

```java
sameTenant.and(requestedStatus.or(requestedPriority))
```

thể hiện cấu trúc muốn giữ:

```text
sameTenant AND (requestedStatus OR requestedPriority)
```

Đây là việc kết hợp đối tượng `Specification`, không phải nhúng dấu ngoặc vào tên phương thức. `Specification` và `JpaSpecificationExecutor` là khả năng của Spring Data JPA. Xem [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html).

Với API ghép điều kiện, cần phân biệt hai biểu thức:

```java
sameTenant.and(requestedStatus.or(requestedPriority))
```

và:

```java
sameTenant.and(requestedStatus).or(requestedPriority)
```

Biểu thức thứ hai vẫn là `(sameTenant AND requestedStatus) OR requestedPriority`. Chuyển sang API khác chỉ hữu ích khi cây điều kiện được xây đúng.

## 9. Query by Example không thay thế mọi nhóm Boolean

Trong phạm vi Commons, Query by Example là một lựa chọn cho nhiều bộ lọc theo probe và matcher. Tuy nhiên, không nên xem nó như một cách tự động giải quyết mọi hạn chế của tên method.

`ExampleMatcher.matchingAll()` yêu cầu các điều kiện được đưa vào cùng khớp. `matchingAny()` cho phép khớp một trong các điều kiện. Chỉ đổi giữa hai chế độ đó không tạo ra nhóm hỗn hợp:

```text
tenantId khớp
AND
(status khớp OR priority khớp)
```

Nếu dùng `matchingAny()` cho cả ba thuộc tính, điều kiện tenant cũng trở thành một lựa chọn ngang hàng, khác yêu cầu nghiệp vụ.

Tài liệu Commons nêu QBE không hỗ trợ các ràng buộc thuộc tính được nhóm theo kiểu Boolean lồng nhau. Xem [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html).

Khi chọn công cụ, cần xét đồng thời dạng nhóm cần biểu đạt và khả năng của store: derived query, declared query, Specification của JPA hoặc API tiêu chí phù hợp với module.

## 10. Null và bộ lọc tùy chọn không tự sửa cấu trúc nhóm

Các ví dụ ở bài dùng tenant, trạng thái và độ ưu tiên đã được xác định. Không nên truyền `null` để ngầm yêu cầu “bỏ điều kiện này” nếu hợp đồng truy vấn chưa quy định như vậy.

Ví dụ, chữ ký:

```java
List<Ticket> findByTenantIdAndStatusOrPriority(
    String tenantId,
    TicketStatus status,
    TicketPriority priority
);
```

vẫn có cấu trúc `(tenant AND status) OR priority` khi một đối số là null. Ý nghĩa so sánh null phụ thuộc loại truy vấn và module; nó không biến cây điều kiện thành `tenant AND (status OR priority)`.

Nếu status là bộ lọc tùy chọn, cần định nghĩa yêu cầu trước:

- Không truyền status thì bỏ riêng nhánh status?
- Không truyền status thì không lọc cả nhóm status/priority?
- Không truyền cả hai thì lấy mọi ticket của tenant hay từ chối yêu cầu?

Các lựa chọn đó tạo những biểu thức khác nhau. Một API xây tiêu chí động có thể biểu đạt chúng rõ hơn một tập method dài, nhưng service vẫn phải xác định chính sách.

Khi kho dữ liệu có ngữ nghĩa riêng cho giá trị null, cũng cần xét ngữ nghĩa của từng điều kiện nguyên tử. Bảng Boolean hai giá trị trong bài dùng để chỉ ra sai nhóm với dữ liệu không null, không thay thế quy tắc null của store.

## 11. Phân trang, sắp xếp và ghép hai lời gọi không thay thế nhóm đúng

Một query method có thể nhận `Pageable` hoặc `Sort`, hoặc khai báo sắp xếp tĩnh bằng `OrderBy`. Những phần đó không thay đổi tập điều kiện Boolean.

Ví dụ, thêm `Pageable` vào một query có cấu trúc sai chỉ phân trang tập kết quả của cấu trúc sai. Nó không bổ sung tenant vào một nhánh đang thiếu tenant.

Tương tự, `Top10` giới hạn kết quả của truy vấn được tạo; nó không có nghĩa tự áp giới hạn riêng cho từng nhánh `Or`.

### Vì sao không mặc nhiên chạy hai query rồi nối List?

Có thể nghĩ tới hai lời gọi:

```text
Query 1: tenant = ACME AND status = OPEN
Query 2: tenant = ACME AND priority = HIGH
```

rồi ghép kết quả ở Java. Nhưng để thay thế một query nhóm, cần giải quyết thêm:

- Ticket 106 thỏa cả hai query nên có thể xuất hiện hai lần trong danh sách ghép.
- Sort riêng hai danh sách rồi nối không tạo ra thứ tự chung đúng.
- Lấy một trang từ mỗi query rồi nối không tương đương lấy một trang của toàn bộ tập kết quả.
- Hai lần đọc có thể quan sát dữ liệu tại những thời điểm khác nhau.
- Tổng số và tín hiệu còn kết quả phải phản ánh tập kết hợp, không chỉ cộng cơ học.

Vì vậy, ghép hai danh sách không phải một phép thay thế mặc định cho nhóm Boolean trong repository. Nếu ứng dụng chủ động chọn cách ghép nhiều nguồn, cần thiết kế hợp đồng tổng hợp riêng.

## 12. Thực hành đối chiếu biểu thức và tên

Trước tiên hãy viết biểu thức nghiệp vụ có ngoặc, sau đó đọc tên method theo các nhánh `Or`.

Với:

```text
A = tenantId khớp
B = status khớp
C = priority khớp
```

hãy so sánh:

| Predicate của method | Biểu thức |
| --- | --- |
| `TenantIdAndStatusOrPriority` | `(A AND B) OR C`. |
| `TenantIdOrStatusAndPriority` | `A OR (B AND C)`. |
| `TenantIdAndStatusOrTenantIdAndPriority` | `(A AND B) OR (A AND C)`, khi hai tenant được truyền cùng giá trị. |
| `TenantIdAndStatusAndPriority` | `A AND B AND C`. |

Trong bộ dữ liệu của bài:

- Yêu cầu `A AND (B OR C)` chọn 101, 102, 106.
- Predicate `TenantIdAndStatusOrPriority` chọn thêm ticket 104.
- Predicate dùng `And` cho cả ba điều kiện chọn 106 vì yêu cầu vừa OPEN vừa HIGH trong ACME.

Khi kiểm chứng một yêu cầu có nhóm, nên có dữ liệu đại diện cho:

1. Khớp điều kiện chung và chỉ nhánh thứ nhất.
2. Khớp điều kiện chung và chỉ nhánh thứ hai.
3. Khớp điều kiện chung và cả hai nhánh.
4. Khớp điều kiện chung nhưng không nhánh nào.
5. Không khớp điều kiện chung nhưng vẫn khớp một nhánh.

Trường hợp thứ năm làm lộ rõ việc đặt thiếu điều kiện chung ở một nhánh `Or`. Với ví dụ này, đó chính là ticket 104 thuộc tenant OTHER nhưng có ưu tiên HIGH.

Một method name ngắn có thể phù hợp cho nhóm đơn giản. Khi phải lặp nhiều điều kiện hoặc khó đối chiếu tên với biểu thức có ngoặc, hãy chọn cơ chế truy vấn thể hiện cây điều kiện trực tiếp và được module hỗ trợ.
