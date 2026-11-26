# Đánh giá index và chi phí sắp xếp trên store thực tế

Trong chương **Sắp xếp** của Spring Data Commons (`SPRING_DATA_COMMONS`), `Sort` biểu đạt thứ tự mà ứng dụng cần. Nó không tự tạo index, chọn execution plan hoặc bảo đảm truy vấn chỉ đọc đúng số bản ghi được trả về.

Muốn đánh giá hiệu năng, cần đi từ hợp đồng repository xuống truy vấn thật của module, sau đó quan sát kế hoạch và số liệu tại store. Bài này dùng PostgreSQL và MongoDB làm hai ví dụ cụ thể; cú pháp index và công cụ đo của chúng không phải API dùng chung cho mọi Spring Data module.

## 1. Đánh giá cả truy vấn, không chỉ tên thuộc tính sort

Một truy vấn cần được nhìn qua ít nhất năm thành phần:

| Thành phần | Câu hỏi |
| --- | --- |
| Điều kiện lọc | Những thuộc tính nào được so sánh bằng, theo khoảng hoặc bằng biểu thức? |
| Thứ tự | Sort theo thuộc tính nào, theo thứ tự ưu tiên và hướng nào? |
| Giới hạn và vị trí | Lấy bao nhiêu phần tử, ở đầu hay tại một offset sâu? |
| Dữ liệu trả về | Lấy toàn bộ entity/document hay chỉ một số trường? |
| Phân bố dữ liệu | Có bao nhiêu bản ghi khớp, và giá trị lọc phân bố đều hay lệch mạnh? |

Một index trên riêng `createdAt` có thể cung cấp thứ tự theo thời gian nhưng vẫn phải đi qua nhiều bản ghi của tenant khác để tìm đủ kết quả.

Ngược lại, một index lọc tenant hiệu quả chưa chắc trả dữ liệu theo thứ tự thời gian mong muốn.

Vì vậy, câu hỏi cần trả lời là:

> Với điều kiện và kích thước kết quả này, store đã đọc bao nhiêu dữ liệu, sort bao nhiêu dữ liệu và tốn những tài nguyên nào?

## 2. Bắt đầu từ một hợp đồng repository cụ thể

Giả sử `Ticket` có các thuộc tính:

| Thuộc tính Java | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất. |
| `tenantId` | `String` | Tổ chức sở hữu ticket. |
| `status` | `TicketStatus` | Trạng thái, ví dụ OPEN. |
| `createdAt` | `Instant` | Thời điểm tạo. |
| `title` | `String` | Nội dung ngắn cần hiển thị. |

Trong ví dụ, ID và thời điểm tạo không null, mapping và kết nối đã được cấu hình đúng theo module.

```java
import java.util.List;

import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;

public interface TicketRepository extends CrudRepository<Ticket, Long> {

    List<Ticket> findByTenantIdAndStatus(
        String tenantId,
        TicketStatus status,
        Pageable pageable
    );
}
```

Phía gọi:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Sort newestFirst = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<Ticket> tickets = repository.findByTenantIdAndStatus(
    "ACME",
    TicketStatus.OPEN,
    PageRequest.of(0, 50, newestFirst)
);
```

Với một mapping SQL giả định, truy vấn dữ liệu có thể tương đương về ngữ nghĩa:

```sql
SELECT id, tenant_id, status, created_at, title
FROM ticket
WHERE tenant_id = 'ACME'
  AND status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Đây là SQL minh họa, không phải lời khẳng định mọi module sẽ sinh đúng chuỗi đó. Khi đo thực tế, cần lấy câu lệnh và giá trị tham số mà ứng dụng thực sự sử dụng, gồm cả join, conversion và các điều kiện bổ sung nếu có.

## 3. Index ghép cần phù hợp với điều kiện lọc và thứ tự

Với query PostgreSQL ở trên, một ứng viên B-tree để đánh giá là:

```sql
CREATE INDEX idx_ticket_tenant_status_created_id
ON ticket (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Lý do xem xét ứng viên này:

1. Query cố định tenant bằng một giá trị.
2. Query cố định trạng thái bằng một giá trị.
3. Trong nhóm đó, cần thời điểm giảm dần rồi ID giảm dần.
4. Chỉ cần một số kết quả đầu tiên.

Index có thể tạo cơ hội tìm đúng nhóm rồi đọc theo thứ tự, thay vì lấy toàn bộ tập khớp rồi sort riêng.

PostgreSQL có thể dùng index phù hợp để cung cấp ORDER BY, đặc biệt có lợi với LIMIT nhỏ. Planner vẫn cân nhắc phương án scan và sort theo chi phí. Xem [PostgreSQL — Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).

### Cùng index nhưng query khác cần được đánh giá lại

| Biến thể | Điểm cần xem xét |
| --- | --- |
| Tenant và status đều cố định, sort createdAt DESC, id DESC | Phù hợp với cấu trúc ứng viên đã nêu. |
| Chỉ cố định tenant, sort toàn bộ theo createdAt | Status chưa cố định tạo các nhóm trung gian; không tự suy ra đã đáp ứng thứ tự toàn cục. |
| Cố định tenant/status, sort createdAt DESC, id ASC | Hướng của tiêu chí ID thay đổi, cần xem lại khả năng cung cấp thứ tự. |
| Cố định tenant/status, sort title | Ứng viên ban đầu không được thiết kế cho thứ tự title. |
| Cố định tenant/status, thêm điều kiện khác | Điều kiện bổ sung có thể làm store đọc rồi loại nhiều bản ghi hơn. |

Trong PostgreSQL, index B-tree nhiều cột có thể được sử dụng trong nhiều dạng điều kiện, nhưng mức hiệu quả phụ thuộc các cột dẫn đầu, ràng buộc và tối ưu của phiên bản. Không dùng quy tắc tuyệt đối “thiếu cột đầu thì index không bao giờ được dùng”. Xem [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html).

### Đảo chiều không đáp ứng mọi tổ hợp hướng

Sau khi các cột equality đã được cố định, đọc ngược một thứ tự `createdAt DESC, id DESC` tương ứng với việc đảo cả hai hướng.

Nó không tự tạo `createdAt DESC, id ASC`. Với tổ hợp hướng hỗn hợp, cần kiểm tra cấu trúc index và plan của chính query đó.

## 4. Đọc EXPLAIN và EXPLAIN ANALYZE trong PostgreSQL

Để quan sát kế hoạch mà planner chọn:

```sql
EXPLAIN
SELECT id, tenant_id, status, created_at, title
FROM ticket
WHERE tenant_id = 'ACME'
  AND status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Để có số liệu thực thi của SELECT, dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, tenant_id, status, created_at, title
FROM ticket
WHERE tenant_id = 'ACME'
  AND status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

`ANALYZE` ở lệnh EXPLAIN này thực thi SELECT để lấy số liệu; nó không chỉ hiển thị dự đoán.

Hai hình dạng có thể gặp dưới đây là **sơ đồ minh họa**, không phải kết quả benchmark đã đo.

Phương án đọc rồi sort:

```text
Limit
  -> Sort
       Sort Key: created_at DESC, id DESC
       -> Seq Scan on ticket
            Filter: tenant_id và status
```

Phương án đọc theo index phù hợp:

```text
Limit
  -> Index Scan using idx_ticket_tenant_status_created_id
       Index Cond: tenant_id và status
```

Không có node Sort riêng có thể là một tín hiệu tốt cho mục tiêu này, nhưng vẫn phải xem lượng dữ liệu index scan đi qua.

Những thông tin cần đọc cùng nhau:

| Thông tin | Cách sử dụng |
| --- | --- |
| Estimated rows và actual rows | Đối chiếu dự đoán với lượng dữ liệu thực tế. |
| Loops | Đọc cùng số hàng và thời gian của node; không bỏ qua việc node chạy nhiều lần. |
| Index Cond và Filter | Phân biệt điều kiện dùng để truy cập index với phần còn phải lọc. |
| Rows Removed by Filter | Nhận diện lượng công việc đọc rồi loại. |
| Sort Method, Memory hoặc Disk | Xem sort diễn ra trong bộ nhớ hay có dùng đĩa. |
| Buffers | Xem hoạt động truy cập buffer và mức đọc dữ liệu. |
| Execution Time | Đo thời gian thực thi phía server trong ngữ cảnh lần đo. |

Cost của planner không phải số mili giây. Chi phí node cha cũng bao gồm phần công việc của node con; không cộng mọi cost trong cây như các khoản độc lập. Xem [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).

Thời gian server cũng không bao gồm toàn bộ thời gian service, mapping entity, truyền dữ liệu và xử lý ở client.

## 5. LIMIT nhỏ không bảo đảm lượng công việc nhỏ

Với `LIMIT 50`, store chỉ phải trả tối đa 50 hàng, nhưng có thể phải xét rất nhiều hàng để xác định 50 hàng đúng thứ tự.

### Sort sau khi lọc

Nếu không đọc được theo thứ tự từ index, query có thể cần:

```text
Đọc dữ liệu
  -> giữ các hàng khớp điều kiện
  -> xác định các hàng đứng đầu theo thứ tự
  -> trả tối đa 50 hàng
```

Một thuật toán top-N có thể giảm lượng dữ liệu cần giữ so với sort toàn bộ, nhưng vẫn có thể phải xét toàn bộ đầu vào liên quan.

Nếu sort phải dùng dữ liệu tạm trên đĩa, chi phí I/O có thể tăng. Khi thấy dấu hiệu này, cần xem lượng đầu vào, độ rộng hàng và index trước khi chỉ nghĩ tới tăng bộ nhớ.

### Đọc theo thứ tự từ index

Index phù hợp có thể cho phép dừng sớm khi đã lấy đủ kết quả. Tuy nhiên, những yếu tố như điều kiện lọc bổ sung hoặc truy cập dữ liệu bảng vẫn ảnh hưởng số bước thực tế.

Do đó, không đặt kỳ vọng rằng mọi plan dùng index với LIMIT 50 đều chỉ xét chính xác 50 entry.

### Offset sâu

Với PostgreSQL:

```sql
ORDER BY created_at DESC, id DESC
LIMIT 50 OFFSET 100000;
```

phần bị bỏ qua vẫn phải được tính trong server. Một index cung cấp thứ tự không tự xóa chi phí đi qua vị trí offset sâu. Xem [PostgreSQL — LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).

Nếu use case chủ yếu đi tiếp theo thứ tự, có thể cân nhắc range/keyset/scrolling được module hỗ trợ. Khi đổi cơ chế, phải giữ đủ các khóa sort, cách xử lý null và hợp đồng điều hướng.

## 6. Biểu thức, collation và null ordering phải được tính vào index

Tên Java `displayName` có thể được module chuyển thành cột hoặc field vật lý khác. Nếu query áp dụng ignoreCase bằng `lower(display_name)`, index trên giá trị thô `display_name` không tự được xem là tương đương với index trên biểu thức đó.

Ví dụ PostgreSQL riêng cho một bảng customer:

```sql
SELECT id, display_name
FROM customer
WHERE region = 'SOUTH'
ORDER BY lower(display_name) ASC NULLS LAST,
         id ASC;
```

Một ứng viên để đánh giá:

```sql
CREATE INDEX idx_customer_region_lower_name_id
ON customer (
    region,
    lower(display_name) ASC NULLS LAST,
    id ASC
);
```

Index biểu thức giúp lưu kết quả biểu thức cần truy cập, nhưng cũng có chi phí duy trì biểu thức khi dữ liệu được ghi. Xem [PostgreSQL — Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).

Khi so khớp query với index, cần xem:

- Biểu thức thực tế là lower, upper hay một biểu thức khác.
- Collation có tương thích không.
- Hướng từng khóa và vị trí null có phù hợp không.
- Kiểu dữ liệu hoặc phép conversion có làm thay đổi biểu thức không.

Không thiết kế index chỉ từ đối tượng Sort rồi bỏ qua query đã được module chuyển đổi.

Một lỗi “tùy chọn sort chưa được hỗ trợ” cũng khác với một query hợp lệ nhưng chậm. Nếu module chưa chuyển được hint, thêm index không sửa được thiếu hụt ở bước tạo query.

## 7. Covering index và partial index cần điều kiện phù hợp

Các phương án dưới đây là những ứng viên riêng để cân nhắc theo workload, không phải yêu cầu tạo tất cả cùng lúc.

### Covering và index-only scan

Query trả toàn bộ entity có thể cần nhiều cột ngoài khóa lọc/sort. Trong PostgreSQL, một covering index có thể bổ sung payload bằng `INCLUDE`, chẳng hạn title nếu đó là trường cần đọc thường xuyên.

Tuy nhiên:

- Những cột query cần phải có trong index để có khả năng đáp ứng bằng index-only scan.
- Việc tránh đọc heap còn phụ thuộc visibility map.
- Tên node `Index Only Scan` không đồng nghĩa số heap fetch luôn bằng không.
- Payload rộng làm index lớn hơn và tăng chi phí duy trì.

Xem [PostgreSQL — Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html).

Projection phù hợp có thể giảm dữ liệu cần lấy và mapping. Cần xem danh sách cột thật sự được query, thay vì chỉ suy từ tên DTO hoặc interface projection.

### Partial index cho một tập dữ liệu được truy vấn nhiều

Nếu workload chủ yếu đọc ticket OPEN, có thể đánh giá ứng viên:

```sql
CREATE INDEX idx_ticket_open_tenant_created_id
ON ticket (
    tenant_id,
    created_at DESC,
    id DESC
)
WHERE status = 'OPEN';
```

Ứng viên chỉ chứa phần dữ liệu thỏa predicate. Để dùng được, planner phải nhận ra điều kiện query bao hàm predicate của index.

Điểm quan trọng với repository là query thường được tham số hóa. Một plan với trạng thái là tham số chưa biết có thể không chứng minh được rằng query luôn thỏa `status = 'OPEN'`.

Vì vậy, hãy kiểm tra dạng truy vấn và hành vi prepared plan giống ứng dụng, không chỉ một bản SQL đã thay mọi tham số bằng literal. Xem [PostgreSQL — Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).

Nếu tỷ lệ ticket OPEN hoặc dạng truy vấn thay đổi mạnh, lợi ích của ứng viên này cũng cần được đánh giá lại.

## 8. Một ví dụ tương ứng trên MongoDB

Giả sử collection `ticket` dùng field `tenantId`, `status`, `createdAt`, và định danh vật lý `_id`. Trạng thái trong ví dụ được lưu dưới dạng chuỗi.

Ứng viên compound index:

```javascript
db.ticket.createIndex({
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
});
```

Query để quan sát:

```javascript
db.ticket.find({
    tenantId: "ACME",
    status: "OPEN"
})
.sort({
    createdAt: -1,
    _id: -1
})
.limit(50)
.explain("executionStats");
```

Tên field trong câu lệnh store cần khớp mapping thực tế. Không mặc định một thuộc tính Java tên `id` cũng được lưu thành field vật lý tên `id`.

MongoDB có thể sử dụng compound index để cung cấp thứ tự nếu các khóa và điều kiện tương thích; với một tập khóa sort nằm sau các khóa prefix, cần xét các điều kiện equality trên prefix. Xem [MongoDB — Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/).

### Dùng ESR như một hướng đánh giá

Equality–Sort–Range là một guideline khi sắp khóa index. Nếu ưu tiên tránh sort riêng, phần Sort thường được xét trước Range; với điều kiện range rất chọn lọc, một phương án khác có thể có lợi hơn.

Không dùng guideline như một chứng minh rằng một index sẽ tối ưu trong mọi phân bố dữ liệu. Xem [MongoDB — ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/).

### Đọc số liệu executionStats

| Trường hoặc dấu hiệu | Ý nghĩa cần xem |
| --- | --- |
| `nReturned` | Số document được trả về. |
| `totalKeysExamined` | Số entry index được xét. |
| `totalDocsExamined` | Số lượt xét document, không phải chỉ số document được trả. |
| Stage scan | Store đang đọc collection, index hay một dạng truy cập khác. |
| Stage sort | Có còn bước sort riêng hoặc dấu hiệu spill tương ứng không. |

Cây plan và tên/vị trí chi tiết có thể khác theo query engine và phiên bản. `explain` cũng có cách xử lý plan cache riêng, nên thời gian explain không phải bản sao tuyệt đối của mọi lần gọi ứng dụng. Xem [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).

Chỉ thấy `IXSCAN` chưa đủ để kết luận tốt. Nếu số keys/documents được xét rất lớn so với kết quả cần lấy, vẫn còn công việc cần phân tích.

## 9. Tính cả chi phí ngoài query dữ liệu

Một endpoint hiển thị 50 phần tử có thể phát sinh nhiều công việc hơn một SELECT hoặc một find.

### Page và truy vấn đếm

`Page<T>` có hợp đồng tổng số phần tử, nên có thể cần thêm truy vấn đếm. Query đếm có mục tiêu khác với query ORDER BY/LIMIT và có thể có plan khác.

Khi đo, tách:

```text
Thời gian query dữ liệu.
Thời gian lấy tổng số, nếu được thực hiện.
Thời gian mapping và xử lý phía ứng dụng.
```

`Slice<T>` không yêu cầu tổng số như Page và có thể phù hợp khi giao diện chỉ cần biết còn phần tiếp theo. Đổi kiểu kết quả cần dựa trên hợp đồng sản phẩm, không chỉ dựa trên mong muốn làm một số đo nhỏ hơn.

### Join, projection và tải dữ liệu liên quan

Sort theo một đường dẫn lồng nhau có thể tạo thêm join hoặc công việc khác theo module. Số hàng trung gian sau join có thể lớn hơn số entity cuối cùng.

Query nhanh tại store nhưng service chậm còn có thể liên quan đến:

- Lấy nhiều cột hoặc document quá rộng.
- Mapping nhiều đối tượng.
- Các lần tải quan hệ hoặc query bổ sung.
- Truyền dữ liệu và serialization.

Không quy toàn bộ độ trễ cho node Sort nếu số liệu không chỉ ra điều đó.

## 10. Index có chi phí ghi và bảo trì

Một index giúp đọc tốt hơn vẫn làm tăng dữ liệu phải duy trì.

| Chi phí | Cách đánh giá trong workload |
| --- | --- |
| Dung lượng | Kích thước index và phần dữ liệu bị lặp lại. |
| Insert/update/delete | Thông lượng và độ trễ ghi trước/sau khi có index. |
| Cache | Những phần index/dữ liệu nào còn thường trú trong bộ nhớ. |
| Bảo trì | Công việc thống kê, dọn dẹp hoặc xây lại theo store và vận hành. |
| Tính chuyên biệt | Bao nhiêu query thật sự hưởng lợi từ index đó. |

Với ứng viên chứa status, thay đổi trạng thái là một phần workload cần đo. Với partial index OPEN, thay đổi vào hoặc ra khỏi tập OPEN cũng ảnh hưởng việc duy trì index.

Một covering index có payload lớn không miễn phí. Một tập index cho mọi tổ hợp sort có thể làm chi phí ghi tăng nhanh.

Nên ưu tiên các kiểu truy vấn quan trọng và thường gặp, đồng thời xem các index có chức năng chồng lấp. Không kết luận một index thừa chỉ vì hai tên cột nhìn gần giống nhau; hướng sort, predicate, collation và payload có thể khác.

## 11. Thiết kế phép so sánh có thể giải thích được

Một quy trình đánh giá hữu ích gồm:

1. **Chốt workload:** điều kiện, tham số, hướng sort, page size, offset và dữ liệu trả về.
2. **Ghi nhận baseline:** plan, số dữ liệu được xét, sort, thời gian query và thời gian ứng dụng.
3. **Đề xuất một thay đổi có lý do:** index ghép, biểu thức, projection hoặc cơ chế phân trang.
4. **So sánh trên dữ liệu tương ứng:** giữ nguyên điều kiện cần so sánh, chỉ rõ cache và mức đồng thời.
5. **Đo cả đọc và ghi:** tránh chuyển một nút thắt sang phần khác mà không ghi nhận.
6. **Kiểm tra tính đúng:** thứ tự, điều kiện và kết quả phân trang phải giữ hợp đồng.
7. **Ghi lại phạm vi kết luận:** phiên bản store/module, loại query và phân bố dữ liệu đã thử.

Các nhóm tham số nên đại diện cho dữ liệu lệch:

| Nhóm | Mục đích |
| --- | --- |
| Tenant có nhiều ticket OPEN | Kiểm tra tập khớp lớn. |
| Tenant có ít ticket OPEN | Kiểm tra truy vấn chọn lọc. |
| Trạng thái phổ biến và hiếm | Quan sát ảnh hưởng của phân bố dữ liệu. |
| Trang đầu và offset sâu | Phân biệt hiệu quả của limit với chi phí đi tới vị trí. |
| Điều kiện không có kết quả | Kiểm tra lượng công việc khi không thể dừng sớm nhờ đủ kết quả. |
| Truy vấn có sort khác hoặc biểu thức | Xác định giới hạn của index đang đề xuất. |

Đo nhiều lượt và phân biệt cache lạnh/ấm thay vì kết luận từ một lần chạy. Khi có nhiều request đồng thời, cần xem độ trễ phân vị phù hợp và mức tài nguyên, không chỉ giá trị trung bình của một query đơn lẻ.

Nếu estimated rows lệch lớn so với actual rows, xem lại thống kê và phân bố dữ liệu trước khi ép planner dùng một index như cách sửa mặc định.

## 12. Những kết luận dễ sai

| Kết luận vội | Cách đọc bằng chứng đầy đủ hơn |
| --- | --- |
| Có index trên field sort nên query chắc nhanh. | Cần xét filter, thứ tự khóa, hướng, biểu thức và lượng dữ liệu đọc. |
| Plan dùng index nên đã tối ưu. | Xem cả keys/rows examined, filter, heap fetch và độ trễ. |
| Có node Sort nghĩa là plan sai. | Scan rồi sort có thể rẻ hơn với một tập dữ liệu hoặc tỷ lệ khớp cụ thể. |
| LIMIT 50 nghĩa là chỉ đọc 50 bản ghi. | Store có thể phải xét nhiều đầu vào để chọn được 50 kết quả. |
| Sort trong Java sau khi lấy trang là tương đương. | Chỉ sắp lại phần đã lấy, không sửa thứ tự của toàn bộ tập. |
| SQL literal nhanh nên repository tham số hóa cũng giống hệt. | Cần kiểm tra cách lập plan và tham số thực tế. |
| Một index cải thiện đọc thì nên giữ bất kể workload. | Cần cân đối chi phí ghi, dung lượng và mức sử dụng. |

## 13. Thực hành đánh giá ứng viên index

Với query ticket của bài, hãy xem ba ứng viên mang tính khái niệm:

```text
A: created_at DESC, id DESC

B: tenant_id, status, created_at DESC, id DESC

C: tenant_id, status
```

Dự đoán trước khi xem plan:

- A có thể cung cấp thứ tự nhưng phải xét điều kiện tenant/status trong quá trình tìm kết quả.
- B được thiết kế cho hai điều kiện equality rồi thứ tự của query chính.
- C hỗ trợ tìm nhóm khớp nhưng chưa trực tiếp cung cấp thứ tự thời gian/ID cần lấy.

Sau đó kiểm tra trên store phù hợp:

1. Query nào còn bước sort riêng?
2. Mỗi phương án xét bao nhiêu hàng hoặc key trước khi trả kết quả?
3. Tenant nhỏ và tenant lớn có cùng plan không?
4. Offset sâu làm thay đổi mức công việc thế nào?
5. Tác động tới ghi và dung lượng có tương xứng lợi ích đọc không?

Không cần chốt trước rằng B luôn thắng. Kết quả đánh giá phải gắn với truy vấn thật, phân bố dữ liệu và bằng chứng thực thi, đồng thời giữ đúng hợp đồng Sort mà ứng dụng đã công bố.
