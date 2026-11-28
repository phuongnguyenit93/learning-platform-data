# Chỉ mục tổng hợp và thứ tự property trong điều kiện

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích composite range index và tình huống nên sử dụng trong Neo4j.
- Tạo chỉ mục tổng hợp cho node hoặc relationship bằng Cypher.
- Phân biệt thứ tự property khai báo trong index với thứ tự các điều kiện `AND` trong `WHERE`.
- Chọn thứ tự property phù hợp với các phép so sánh bằng, `IN`, range và prefix.
- Nhận biết vì sao một composite index không được sử dụng khi truy vấn thiếu predicate trên một property đã lập chỉ mục.
- Kiểm tra query plan bằng `EXPLAIN`, `PROFILE` và quản lý index trong quy trình triển khai Spring Data Neo4j (SDN).

## 1. Vì sao cần chỉ mục tổng hợp?

Một ứng dụng Spring Data Neo4j có thể thường xuyên tìm node theo nhiều điều kiện cùng lúc. Ví dụ, trang quản trị người dùng cần tìm những người thuộc một tenant, có trạng thái hoạt động và được tạo sau một thời điểm nhất định:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

Nếu chỉ có index riêng trên `tenantId`, Neo4j có thể dùng index đó để tìm một tập ứng viên rồi kiểm tra tiếp `status` và `createdAt`. Nếu workload thường xuyên lọc đồng thời cả ba property, một composite index có thể giúp Neo4j giải quyết nhiều predicate ngay tại bước truy xuất index.

Composite index là range index được tạo trên nhiều property của cùng một label node hoặc relationship type. Ví dụ:

```cypher
CREATE INDEX person_tenant_status_created_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Index này lưu tổ hợp giá trị theo thứ tự `tenantId`, `status`, `createdAt`. Thứ tự đó ảnh hưởng đến cách query planner sử dụng index để giải quyết các predicate. Hai index chứa cùng tập property nhưng khai báo theo thứ tự khác nhau có thể tạo ra query plan khác nhau.

Composite index phù hợp khi ứng dụng có một nhóm truy vấn thường xuyên lọc theo cùng tổ hợp property. Nó không phải lựa chọn mặc định cho mọi entity hoặc mọi tổ hợp điều kiện.

## 2. Tạo composite range index cho node và relationship

Trong Neo4j hiện đại, composite index được tạo bằng Cypher. Nếu không ghi rõ loại index trong lệnh `CREATE INDEX`, Neo4j tạo range index:

```cypher
CREATE INDEX person_tenant_status_created_idx
IF NOT EXISTS
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Chỉ mục được áp dụng cho node có label `Person` và chứa đủ cả ba property `tenantId`, `status`, `createdAt`. Node thiếu bất kỳ property nào trong ba property này sẽ không có entry trong composite index.

Có thể tạo composite index cho property trên relationship:

```cypher
CREATE INDEX membership_tenant_status_since_idx
IF NOT EXISTS
FOR ()-[r:MEMBER_OF]-()
ON (r.tenantId, r.status, r.since)
```

Chỉ relationship có type `MEMBER_OF` và có đủ các property đã khai báo mới được đưa vào index.

Một số điểm cần nhớ:

- Composite index hiện tại là composite **range index**.
- Text index và point index là các loại index đơn property; không tạo composite text hoặc composite point index theo cú pháp trên.
- Tên index phải duy nhất trong phạm vi index và constraint.
- Có thể dùng `IF NOT EXISTS` để tránh lỗi khi index cùng tên hoặc cùng schema đã tồn tại.
- Index mới tạo có thể ở trạng thái `POPULATING`; query planner chỉ sử dụng được khi index ở trạng thái `ONLINE`.

## 3. Thứ tự property trong index khác thứ tự predicate trong WHERE

Đây là điểm quan trọng nhất của bài học.

Khi tạo index:

```cypher
CREATE INDEX person_lookup_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

thứ tự key của index là:

1. `tenantId`
2. `status`
3. `createdAt`

Nhưng thứ tự các biểu thức trong `WHERE` không phải cách điều khiển thứ tự truy cập index. Hai câu sau diễn đạt cùng tập điều kiện:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

```cypher
MATCH (p:Person)
WHERE p.createdAt >= $from
  AND p.status = $status
  AND p.tenantId = $tenantId
RETURN p
```

Việc đổi vị trí các predicate `AND` trong câu lệnh không thay đổi thứ tự property đã được định nghĩa trong index. Cypher planner phân tích các điều kiện và quyết định cách dùng index dựa trên schema, loại predicate, thống kê và chi phí ước lượng.

Vì vậy, khi muốn cải thiện cách composite index giải quyết điều kiện, cần xem lại thứ tự property trong lệnh tạo index và hình dạng predicate. Chỉ đổi thứ tự viết các biểu thức trong `WHERE` không thay thế được việc thiết kế lại index.

## 4. Quy tắc sử dụng predicate với composite index

Composite range index hỗ trợ các nhóm predicate như:

| Loại predicate | Ví dụ |
| --- | --- |
| Equality | `p.status = $status` |
| List membership | `p.status IN $statuses` |
| Existence | `p.status IS NOT NULL` |
| Range | `p.createdAt >= $from` |
| Prefix | `p.name STARTS WITH $prefix` |

Tuy nhiên, khả năng giải quyết predicate phụ thuộc vào thứ tự property trong index.

Các quy tắc chính:

1. Nếu truy vấn có equality hoặc list membership, các predicate này cần tương ứng với những property đứng đầu trong thứ tự index.
2. Một truy vấn dùng composite index có thể có tối đa một predicate range hoặc prefix được giải quyết theo kiểu range/prefix seek.
3. Có thể có nhiều predicate existence.
4. Các predicate nằm sau predicate range, prefix hoặc existence sẽ được planner xử lý như existence check; điều kiện so sánh cụ thể có thể được áp dụng thêm bằng `Filter`.
5. Suffix và substring search như `ENDS WITH`, `CONTAINS` không được giải quyết hiệu quả như equality seek trong composite range index. Với tìm kiếm chuỗi dạng này, text index đơn property có thể phù hợp hơn.

Composite index chỉ được sử dụng khi truy vấn lọc trên **tất cả property được khai báo trong index**. Nếu query chỉ lọc một phần các property, index tổng hợp đó không đáp ứng truy vấn; hãy cân nhắc index riêng hoặc một composite index khác đúng với workload.

## 5. Đặt equality trước range

Một quy tắc thiết kế hữu ích là đưa các property thường được lọc bằng equality hoặc `IN` lên trước, sau đó đặt property có range hoặc prefix ở phía sau.

Ví dụ index:

```cypher
CREATE INDEX person_tenant_status_created_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Query:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

Cấu trúc predicate tương ứng:

| Property | Predicate | Vai trò trong index |
| --- | --- | --- |
| `tenantId` | Equality | Điều kiện equality đầu tiên |
| `status` | Equality | Điều kiện equality tiếp theo |
| `createdAt` | Range | Điều kiện range sau các equality |

Cách tổ chức này cho phép index sử dụng hai equality predicate trước khi áp dụng range trên `createdAt`.

Nếu tạo index theo thứ tự:

```cypher
CREATE INDEX person_created_tenant_status_idx
FOR (p:Person)
ON (p.createdAt, p.tenantId, p.status)
```

thì predicate range trên `createdAt` xuất hiện trước các equality predicate. Những predicate phía sau range có thể chỉ được xử lý như existence check và filter. Index vẫn có thể tham gia truy vấn, nhưng không giải quyết các equality phía sau hiệu quả như thứ tự equality trước range.

Không có quy tắc rằng mọi index đều phải đặt thời gian cuối cùng. Hãy dựa trên các truy vấn thực tế và loại predicate thường dùng. Nếu truy vấn thường xuyên tìm theo tenant, trạng thái rồi khoảng thời gian, thứ tự `tenantId, status, createdAt` là một ứng viên hợp lý.

## 6. Ví dụ property order ảnh hưởng đến prefix search

Giả sử giao diện tìm người theo tenant, tên bắt đầu bằng một prefix và trạng thái:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.name STARTS WITH $prefix
  AND p.status = $status
RETURN p
```

Index thứ nhất:

```cypher
CREATE INDEX person_tenant_name_status_idx
FOR (p:Person)
ON (p.tenantId, p.name, p.status)
```

Với thứ tự này:

- `tenantId` được giải quyết bằng equality.
- `name` được giải quyết bằng prefix search.
- `status` nằm sau prefix nên được xử lý như existence check và điều kiện so sánh được áp dụng bằng filter.

Nếu workload thường xuyên lọc tenant và status bằng equality trước khi prefix tên, có thể cân nhắc thứ tự:

```cypher
CREATE INDEX person_tenant_status_name_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.name)
```

Lúc này:

- `tenantId` là equality đầu tiên.
- `status` là equality tiếp theo.
- `name` là prefix search ở cuối.

Index thứ hai phù hợp hơn với hình dạng predicate này vì các equality được giải quyết trước prefix search.

Hai index chứa cùng ba property nhưng thứ tự khác nhau. Không nên tạo cả hai theo thói quen; hãy kiểm tra workload và query plan để xác định có cần duy trì cả hai hay không.

## 7. Composite index cần predicate trên tất cả property

Giả sử có index:

```cypher
CREATE INDEX person_tenant_status_created_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Query có đủ ba predicate:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

Query này có thể sử dụng composite index.

Nhưng query chỉ có:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
RETURN p
```

không có predicate trên `createdAt`, nên composite index ba property không thể được sử dụng theo quy tắc composite index hiện tại.

Nếu hai query đều là workload quan trọng, có thể cần một index khác:

```cypher
CREATE INDEX person_tenant_status_idx
FOR (p:Person)
ON (p.tenantId, p.status)
```

Khi thiết kế, hãy lập danh sách các mẫu truy vấn chính:

| Mẫu truy vấn | Index có thể phù hợp |
| --- | --- |
| Tenant + status + khoảng thời gian | `(tenantId, status, createdAt)` |
| Tenant + status | `(tenantId, status)` |
| Chỉ tìm theo email | `(email)` hoặc unique constraint nếu email phải duy nhất |
| Tenant + prefix tên + status equality | Cân nhắc `(tenantId, status, name)` |

Không cần tạo index cho mọi tổ hợp có thể xuất hiện. Chọn các mẫu truy vấn có tần suất và chi phí đủ lớn để biện minh cho dung lượng index và chi phí cập nhật.

## 8. Áp dụng composite index trong Spring Data Neo4j

SDN không cần chỉ định index trong repository method. Khi repository sinh Cypher từ derived query hoặc khi ứng dụng viết custom Cypher bằng `@Query`, Neo4j query planner tự chọn index phù hợp.

Giả sử entity `Person` đã được ánh xạ bằng `@Node("Person")`, có các property `tenantId`, `status`, `createdAt` và ID kiểu `String`. Repository có thể khai báo custom query như sau:

```java
import java.time.ZonedDateTime;
import java.util.Collection;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)
        WHERE p.tenantId = $tenantId
          AND p.status = $status
          AND p.createdAt >= $from
        RETURN p
        ORDER BY p.createdAt DESC
        """)
    Collection<Person> findRecentByTenantAndStatus(
        @Param("tenantId") String tenantId,
        @Param("status") String status,
        @Param("from") ZonedDateTime from
    );
}
```

Index tương ứng có thể được tạo bằng migration:

```cypher
CREATE INDEX person_tenant_status_created_idx
IF NOT EXISTS
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Repository chỉ mô tả truy vấn nghiệp vụ. Index là schema object do Neo4j quản lý; query planner tự quyết định có sử dụng index hay không. Không thêm hint hoặc giả định rằng chỉ cần tồn tại index là mọi truy vấn đều dùng nó.

### 8.1. Quản lý index bằng migration

Các annotation `@Index` và `@CompositeIndex` thuộc mô hình Neo4j-OGM cũ đã bị loại bỏ khỏi Spring Data Neo4j hiện đại. Không nên dùng lại các ví dụ cũ đó trong SDN hiện nay.

SDN khuyến nghị quản lý schema bằng migration có kiểm soát, ví dụ Neo4j Migrations. Migration lưu lịch sử thay đổi schema và cho phép triển khai index nhất quán giữa môi trường phát triển, kiểm thử và production.

Ví dụ nội dung một migration Cypher:

```cypher
CREATE INDEX person_tenant_status_created_idx
IF NOT EXISTS
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Không nên để mỗi lần ứng dụng khởi động tùy ý tạo hoặc xóa index theo entity scan. Index là thành phần schema cần được version hóa và triển khai theo kế hoạch.

## 9. Composite uniqueness constraint khác composite index

Composite range index phục vụ truy vấn. Nó không tự đảm bảo tổ hợp property là duy nhất.

Nếu nghiệp vụ yêu cầu mỗi tenant không được có hai người cùng email, hãy tạo composite uniqueness constraint:

```cypher
CREATE CONSTRAINT person_tenant_email_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.email) IS UNIQUE
```

Constraint này đảm bảo không có hai node `Person` có cùng tổ hợp `tenantId` và `email`. Neo4j tạo index hỗ trợ constraint; không cần tạo một composite range index trùng schema chỉ để tìm kiếm cùng tổ hợp đó.

Phân biệt:

| Thành phần | Mục đích |
| --- | --- |
| Composite range index | Tăng tốc truy vấn theo nhiều property |
| Composite uniqueness constraint | Đảm bảo tổ hợp property không bị trùng |
| `@Id` trong entity SDN | Xác định định danh entity theo mapping |
| `@Version` | Hỗ trợ optimistic locking, không phải index |

Không dùng index như cơ chế bảo đảm tính duy nhất. Nếu tính duy nhất là yêu cầu dữ liệu, hãy khai báo constraint.

## 10. Kiểm tra index đã được tạo và sẵn sàng

Sau khi migration chạy, kiểm tra index:

```cypher
SHOW INDEXES
```

Các thông tin quan trọng gồm:

- `name`: tên index.
- `type`: loại index, ví dụ `RANGE`.
- `entityType`: index áp dụng cho node hay relationship.
- `labelsOrTypes`: label hoặc relationship type.
- `properties`: danh sách property theo đúng thứ tự khai báo.
- `state`: trạng thái hiện tại của index.

Index mới có thể ở trạng thái `POPULATING`. Trong lúc đó query planner chưa thể sử dụng index. Chờ trạng thái chuyển sang `ONLINE` trước khi đánh giá hiệu quả truy vấn.

Có thể lọc index theo loại:

```cypher
SHOW RANGE INDEXES
```

Nếu index không xuất hiện, hãy kiểm tra migration đã chạy trên đúng database và đúng môi trường hay chưa. Nếu index ở trạng thái lỗi, cần xem thông tin lỗi trong kết quả quản trị index và xử lý nguyên nhân trước khi đánh giá query plan.

## 11. Dùng EXPLAIN và PROFILE để kiểm chứng

Không thể kết luận index được dùng chỉ vì nó tồn tại. Hãy xem query plan.

`EXPLAIN` yêu cầu Neo4j lập kế hoạch nhưng không thực thi truy vấn:

```cypher
EXPLAIN
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

`PROFILE` thực thi truy vấn và thu thập số liệu thực tế:

```cypher
PROFILE
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
  AND p.createdAt >= $from
RETURN p
```

Trong execution plan, chú ý:

- `NodeIndexSeek`: planner truy xuất node bằng index.
- `NodeIndexScan`: planner quét các entry của index.
- `Filter`: điều kiện được kiểm tra sau bước truy xuất trước đó.
- `Rows`: số dòng đi qua từng operator.
- `DB Hits`: số lần truy cập dữ liệu của operator.
- `Estimated Rows`: số dòng planner dự đoán.

Với composite index, phần mô tả của `NodeIndexSeek` cho biết property nào được dùng làm equality, range, prefix hoặc existence predicate. Nếu một điều kiện xuất hiện ở `Filter`, điều đó có thể cho thấy index chỉ giải quyết một phần điều kiện và phần còn lại được kiểm tra sau.

Khi dùng `PROFILE`, hãy lưu ý câu lệnh thực sự chạy. Chỉ dùng ví dụ đọc dữ liệu trong môi trường có thể thực thi an toàn; không PROFILE một truy vấn ghi hoặc xóa ngoài ý muốn.

## 12. Những lưu ý về null và dữ liệu thiếu property

Neo4j index không lưu giá trị `null`. Với composite index, node hoặc relationship phải có đủ tất cả property đã khai báo mới được đưa vào index.

Ví dụ index:

```cypher
CREATE INDEX person_tenant_status_created_idx
FOR (p:Person)
ON (p.tenantId, p.status, p.createdAt)
```

Node có `tenantId` và `status` nhưng chưa có `createdAt` sẽ không có entry trong index này.

Điều này có ảnh hưởng đến cả truy vấn và dữ liệu:

- Nếu truy vấn yêu cầu `p.createdAt >= $from`, node không có `createdAt` vốn không thỏa điều kiện range.
- Nếu nghiệp vụ kỳ vọng mọi Person đều có `createdAt`, cần bảo đảm dữ liệu được ghi đầy đủ.
- Nếu property chỉ có ở một phần node, composite index có thể không phù hợp với query cần bao phủ các node thiếu property đó.
- Predicate `IS NOT NULL` có thể giúp planner chứng minh rằng property có tồn tại, nhưng không thay thế việc thiết kế dữ liệu đúng.

Không nên thêm property giả chỉ để ép index hoạt động nếu điều đó làm sai ý nghĩa domain. Hãy quyết định rõ property nào bắt buộc và property nào tùy chọn.

## 13. Chọn thứ tự property theo workload

Một quy trình thực tế để thiết kế composite index:

1. Thu thập các truy vấn thường xuyên và có chi phí đáng kể.
2. Ghi lại label hoặc relationship type và toàn bộ property được dùng để lọc.
3. Phân loại từng predicate: equality, `IN`, range, prefix, existence, suffix hoặc substring.
4. Đưa các equality/`IN` phù hợp lên đầu index.
5. Đặt predicate range hoặc prefix ở vị trí tiếp theo; tránh kỳ vọng các predicate sau đó vẫn được giải quyết như equality.
6. Xác nhận truy vấn có predicate trên tất cả property của composite index.
7. Tạo index bằng migration.
8. Chờ index ở trạng thái `ONLINE`.
9. Chạy `EXPLAIN` và `PROFILE` với dữ liệu đại diện.
10. So sánh số dòng, DB Hits, operator và thời gian trước/sau khi tạo index.

Độ chọn lọc của property cũng quan trọng. Một equality predicate trên property có ít giá trị phân biệt có thể loại ít node hơn một predicate có độ chọn lọc cao. Hãy kiểm tra query plan trên dữ liệu gần với production thay vì chọn thứ tự chỉ dựa vào tên property.

## 14. Tránh over-indexing

Mỗi index bổ sung dung lượng lưu trữ và chi phí duy trì khi dữ liệu được tạo, sửa hoặc xóa. Tạo index cho mọi tổ hợp property có thể làm chậm write workload và tăng thời gian migration.

Một số nguyên tắc:

- Ưu tiên index phục vụ truy vấn có tần suất cao hoặc chi phí lớn.
- Tránh tạo composite index chỉ vì entity có nhiều field.
- Không tạo index trùng schema với index-backed constraint.
- Xem lại các index ít được đọc hoặc không còn query nào sử dụng.
- Kiểm tra chi phí cập nhật index khi workload ghi lớn.
- Dùng `SHOW INDEXES` và các số liệu theo dõi để phát hiện index dư thừa.
- Đánh giá lại index khi query pattern hoặc mô hình dữ liệu thay đổi.

Index tốt là index phục vụ workload cụ thể với chi phí hợp lý, không phải index có nhiều property nhất.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đổi thứ tự predicate trong `WHERE` nhưng query plan không đổi | Thứ tự biểu thức `AND` không điều khiển thứ tự key trong index | Xem lại thứ tự property khi tạo index |
| Tạo index ba property nhưng query chỉ lọc hai property | Composite index yêu cầu predicate trên tất cả property đã index | Tạo index phù hợp với query pattern hai property |
| Đặt range trước equality trong index | Predicate phía sau range có thể thành existence + filter | Ưu tiên equality/`IN` trước range hoặc prefix |
| Đặt prefix trước equality | Các predicate sau prefix có thể chỉ được kiểm tra bằng filter | Cân nhắc đặt equality trước prefix |
| Tạo hai index cùng property nhưng khác thứ tự mà không đo đạc | Tăng chi phí lưu trữ và ghi | Chỉ giữ index phục vụ workload đã xác minh |
| Node thiếu một property của index | Node không được đưa vào composite index | Kiểm tra tính đầy đủ của dữ liệu |
| Nghĩ composite index đảm bảo uniqueness | Index chỉ phục vụ truy vấn | Dùng composite uniqueness constraint |
| Dùng annotation `@CompositeIndex` cũ của Neo4j-OGM | Annotation đã bị loại bỏ khỏi SDN hiện đại | Quản lý index bằng Cypher migration |
| Index vừa tạo nhưng chưa dùng được | Index vẫn ở trạng thái `POPULATING` | Chờ trạng thái `ONLINE` |
| Chỉ nhìn thấy index nên kết luận query nhanh | Planner có thể chọn plan khác hoặc dùng filter sau index | Kiểm tra `EXPLAIN` và `PROFILE` |
| Tạo index cho mọi tổ hợp property | Over-indexing làm tăng chi phí ghi và lưu trữ | Ưu tiên query workload quan trọng |

## 16. Câu hỏi tự kiểm tra

1. Composite range index khác single-property range index ở điểm nào?
2. Vì sao thứ tự property trong lệnh tạo index ảnh hưởng đến query plan?
3. Đổi thứ tự các predicate `AND` trong `WHERE` có thay đổi thứ tự key của index không?
4. Vì sao equality và `IN` thường nên đứng trước range hoặc prefix?
5. Một composite index có thể giải quyết bao nhiêu predicate range hoặc prefix?
6. Điều gì xảy ra với predicate nằm sau range hoặc prefix?
7. Vì sao query cần predicate trên tất cả property của composite index?
8. Node thiếu một property trong index có được đưa vào index không?
9. Khi nào nên dùng composite uniqueness constraint thay cho composite index?
10. SDN hiện đại quản lý composite index bằng annotation hay migration?
11. `EXPLAIN` và `PROFILE` khác nhau như thế nào?
12. Làm thế nào nhận biết query plan đang dùng `NodeIndexSeek` và có điều kiện còn lại bị `Filter` xử lý?
13. Vì sao không nên tạo quá nhiều composite index?

## Tài liệu tham khảo

- [Neo4j Cypher Manual – The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j Cypher Manual – Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Operations Manual – Index configuration](https://neo4j.com/docs/operations-manual/current/performance/index-configuration/)
- [Spring Data Neo4j – Migration off Neo4j-OGM schema annotations](https://docs.spring.io/spring-data/data-neo4j/docs/7.1.x/reference/html/)

## Kết luận

Composite index là range index trên nhiều property của cùng node label hoặc relationship type. Nó hữu ích khi các truy vấn thường xuyên lọc theo cùng một tổ hợp property. Thứ tự property được khai báo trong index ảnh hưởng trực tiếp đến cách Neo4j planner giải quyết predicate; thứ tự viết các biểu thức `AND` trong `WHERE` không thay đổi thứ tự key của index.

Khi thiết kế, hãy đặt equality hoặc `IN` ở các key đầu, sau đó cân nhắc range hoặc prefix. Composite index cần predicate trên tất cả property đã khai báo; node hoặc relationship thiếu một property sẽ không có entry trong index. Dùng `EXPLAIN` và `PROFILE` để xác nhận query plan, quản lý schema bằng migration trong ứng dụng SDN hiện đại và chỉ giữ các index phục vụ workload đã đo đạc.
