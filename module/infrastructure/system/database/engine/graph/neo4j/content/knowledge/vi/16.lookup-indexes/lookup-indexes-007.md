# Chỉ mục ghép và thứ tự thuộc tính theo mẫu truy vấn trong Neo4j

Trong **Neo4j**, một truy vấn có thể lọc node hoặc relationship bằng nhiều thuộc tính: ví dụ tìm ticket thuộc một khách hàng, đang mở và được tạo trong một khoảng thời gian. Khi truy vấn kiểu này chạy thường xuyên trên hàng triệu thực thể, **chỉ mục ghép (composite index)** có thể giúp giảm dữ liệu phải đọc. Tuy nhiên, đặt các thuộc tính theo thứ tự nào trong chỉ mục là một quyết định thiết kế: cùng một tập thuộc tính nhưng thứ tự khác nhau có thể phục vụ các mẫu `WHERE` và `ORDER BY` khác nhau.

Bài học thuộc chương **Chỉ mục tra cứu**, trong phạm vi mô hình **property graph**, truy vấn **Cypher** và tối ưu truy vấn Neo4j. Ta sẽ phân tích cách chọn thứ tự thuộc tính, tự tạo dữ liệu và chỉ mục, xem kế hoạch thực thi, rồi cân nhắc chi phí duy trì chỉ mục trong ứng dụng dùng **Neo4j Java Driver** hoặc **Spring Data Neo4j**.

## 1. Phân biệt lookup index với chỉ mục ghép trên thuộc tính

Trong Neo4j, cần phân biệt hai khái niệm dễ bị gọi chung là “chỉ mục tra cứu”:

| Loại chỉ mục | Khóa tra cứu | Ví dụ mục đích |
| --- | --- | --- |
| **Token lookup index** | Nhãn node hoặc loại relationship | Tìm các node `:Ticket` hoặc relationship `:ASSIGNED_TO` |
| **Property range index** | Một hoặc nhiều **thuộc tính** của node/relationship | Lọc `t.tenantId`, `t.status`, `t.createdAt` |
| **Composite range index** | Một chuỗi thuộc tính có **thứ tự xác định** | Lọc kết hợp `(tenantId, status, createdAt)` |

**Lookup index không chứa các giá trị `tenantId`, `status` hay `createdAt`.** Trong bài này, “chỉ mục ghép” chủ yếu là **composite RANGE index** trên property, được tạo với `CREATE RANGE INDEX`. Không nên nhầm nó với `CREATE LOOKUP INDEX` dùng cho nhãn và loại quan hệ.

Ví dụ chỉ mục ghép trên node:

```cypher
CREATE RANGE INDEX ticket_tenant_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.status, t.createdAt);
```

Các thuộc tính `tenantId`, `status` và `createdAt` tạo thành một chuỗi khóa theo đúng thứ tự được khai báo. Khi đọc kế hoạch thực thi, ta cần xem Neo4j có tận dụng được chuỗi khóa đó để tìm và/hoặc sắp xếp kết quả hay không.

> **Phạm vi:** Cách chọn chỉ mục ở đây tập trung vào `RANGE` index cho điều kiện bằng, so sánh khoảng và sắp xếp. Truy vấn toàn văn (full-text), chuỗi cần phân tích ngôn ngữ, hoặc dữ liệu địa lý có thể cần loại chỉ mục và cách tối ưu khác.

## 2. Bắt đầu từ mẫu truy vấn, không bắt đầu từ danh sách thuộc tính

Giả sử một hệ thống hỗ trợ có node:

```text
(:Ticket {
  ticketId: "TK-001",
  tenantId: "ACME",
  status: "OPEN",
  createdAt: datetime("2026-11-03T08:00:00Z"),
  priority: 2
})
```

Ứng dụng có các nhu cầu sau:

- **Q1:** Trong tenant `ACME`, lấy ticket `OPEN` của tháng 11, mới nhất trước, tối đa 20 ticket.
- **Q2:** Trong tenant `ACME`, lấy mọi ticket của tháng 11, không lọc `status`.
- **Q3:** Tìm mọi ticket `OPEN` trên các tenant theo khoảng ngày, phục vụ đội vận hành toàn hệ thống.
- **Q4:** Tra cứu một ticket duy nhất bằng `ticketId`.

Chúng đều dùng dữ liệu `Ticket`, nhưng không nhất thiết được tối ưu bằng **một** chỉ mục ghép.

Mẫu Q1 tiêu biểu:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId,
       t.status AS status,
       t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Các phần của truy vấn mang ý nghĩa khác nhau:

| Biểu thức | Kiểu điều kiện | Vai trò |
| --- | --- | --- |
| `t.tenantId = 'ACME'` | **Equality** | Thu hẹp theo một tenant |
| `t.status = 'OPEN'` | **Equality** | Thu hẹp tiếp theo trạng thái |
| `t.createdAt >= ... AND < ...` | **Range** | Lấy khoảng thời gian |
| `ORDER BY t.createdAt DESC` | **Ordering** | Ưu tiên ticket mới |
| `LIMIT 20` | Giới hạn kết quả | Chỉ cần một số lượng nhỏ sau khi lọc/sắp xếp |

Từ mẫu này, chỉ mục `(tenantId, status, createdAt)` là **ứng viên tốt**: hai thuộc tính lọc bằng đứng trước, thuộc tính lọc khoảng và sắp xếp đứng sau.

## 3. Quy tắc chọn thứ tự: equality trước, range/sort sau

Một quy tắc thực hành hữu ích khi thiết kế composite range index là:

1. Đưa các thuộc tính thường được so sánh **bằng** (`=`) vào phần đầu.
2. Đặt thuộc tính thường được so sánh **khoảng** (`<`, `<=`, `>`, `>=`) sau nhóm equality.
3. Cân nhắc `ORDER BY`: nếu sắp xếp theo thuộc tính ngay sau tiền tố equality và kiểu kế hoạch phù hợp, Neo4j **có thể** tận dụng thứ tự của index thay vì sắp xếp nhiều bản ghi.
4. Luôn kiểm chứng bằng `EXPLAIN` và `PROFILE`; đây là **quy tắc thiết kế**, không phải bảo đảm planner sẽ chọn index cho mọi kích thước dữ liệu hoặc mọi phiên bản Neo4j.

Hình dung thứ tự khóa chỉ mục `(tenantId, status, createdAt)` như các nhóm lồng nhau:

```text
tenantId
├── ACME
│   ├── CLOSED
│   │   └── createdAt: ...
│   └── OPEN
│       ├── createdAt: 2026-11-03
│       ├── createdAt: 2026-11-20
│       └── createdAt: 2026-11-25
└── BETA
    └── OPEN
        └── createdAt: ...
```

Khi cả `tenantId` và `status` đã biết, các giá trị `createdAt` liên quan nằm trong vùng khóa tập trung. Khi **bỏ điều kiện `status`**, dữ liệu của cùng tenant còn được chia theo status; chỉ mục này không nhất thiết đem lại tìm kiếm theo khoảng thời gian hoặc thứ tự thời gian tốt như chỉ mục `(tenantId, createdAt)`.

### So sánh ba thứ tự trên cùng một tập thuộc tính

| Thứ tự index | Với Q1 (tenant =, status =, createdAt range) | Với Q2 (tenant =, createdAt range) |
| --- | --- | --- |
| `(tenantId, status, createdAt)` | Ứng viên phù hợp: equality trước range | Có khoảng trống `status` trước `createdAt` |
| `(tenantId, createdAt, status)` | Có thể khoanh theo tenant và khoảng ngày; `status` nằm sau range | Ứng viên phù hợp cho Q2 |
| `(createdAt, tenantId, status)` | Dẫn đầu bằng khoảng thời gian, có thể phải xét nhiều tenant hơn | Chỉ đáng cân nhắc nếu truy vấn theo thời gian trên nhiều tenant là chính |

**Không có một thứ tự tối ưu cho mọi truy vấn.** Thiết kế dựa trên truy vấn nào chạy nhiều, số lượng dữ liệu mỗi tenant/status, độ rộng khoảng thời gian và yêu cầu sắp xếp.

### “Tiền tố bên trái” nên được hiểu thế nào?

Với chỉ mục `(A, B, C)`, mẫu điều kiện bắt đầu từ `A`, rồi `B`, rồi `C` thường có lợi thế. Ví dụ:

- `A = ... AND B = ... AND C >= ...`: có điều kiện liên tục trên cả ba trường, rất phù hợp với `(A, B, C)`.
- `A = ... AND B = ...`: có một tiền tố liên tục; cách tận dụng phụ thuộc loại index và kế hoạch thực thi.
- `A = ... AND C >= ...`: thiếu `B`; không nên mặc định rằng index sẽ tìm kiếm hiệu quả trực tiếp theo `C`.
- `B = ... AND C >= ...`: thiếu thuộc tính đứng đầu `A`; không nên coi `(A, B, C)` là thay thế mặc nhiên cho `(B, C)`.

Neo4j có thể chọn **index seek**, **index scan**, lọc bổ sung hoặc quét nhãn, tùy phiên bản, loại predicate, thống kê và độ chọn lọc. Vì vậy, dùng “tiền tố bên trái” như **nguyên tắc phân tích**, không suy diễn rằng mọi truy vấn không khớp tiền tố đều tuyệt đối không thể dùng index.

## 4. Ví dụ chạy được: dữ liệu, chỉ mục, truy vấn

Các lệnh trong phần này dành cho **cơ sở dữ liệu thực hành**, có thể chạy lần lượt trong Neo4j Browser hoặc Cypher shell.

### 4.1. Tạo constraint và sáu ticket mẫu

Constraint dưới đây bảo đảm `ticketId` duy nhất. Đây là quy tắc toàn vẹn dữ liệu; chỉ mục phục vụ lọc nhiều thuộc tính sẽ được tạo riêng ở bước sau.

```cypher
CREATE CONSTRAINT ticket_id_unique IF NOT EXISTS
FOR (t:Ticket)
REQUIRE t.ticketId IS UNIQUE;
```

```cypher
UNWIND [
  {id: 'TK-001', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-03T08:00:00Z', priority: 2},
  {id: 'TK-002', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-20T10:00:00Z', priority: 1},
  {id: 'TK-003', tenant: 'ACME', state: 'CLOSED',
   at: '2026-11-15T11:00:00Z', priority: 3},
  {id: 'TK-004', tenant: 'ACME', state: 'OPEN',
   at: '2026-10-22T09:00:00Z', priority: 2},
  {id: 'TK-005', tenant: 'BETA', state: 'OPEN',
   at: '2026-11-24T07:00:00Z', priority: 1},
  {id: 'TK-006', tenant: 'ACME', state: 'OPEN',
   at: '2026-11-25T13:00:00Z', priority: 3}
] AS row
MERGE (t:Ticket {ticketId: row.id})
SET t.tenantId = row.tenant,
    t.status = row.state,
    t.createdAt = datetime(row.at),
    t.priority = row.priority;
```

Điểm cần nhớ: `createdAt` là giá trị **temporal `datetime`**, không phải chuỗi tùy ý. Khi lọc khoảng thời gian, giá trị so sánh phải có kiểu tương thích. Việc lưu/so sánh thời gian nên nhất quán về múi giờ.

### 4.2. Tạo index cho Q1

```cypher
CREATE RANGE INDEX ticket_tenant_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.status, t.createdAt);
```

Kiểm tra index đã được tạo và hoàn tất xây dựng:

```cypher
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, state
WHERE name = 'ticket_tenant_status_created'
RETURN name, type, labelsOrTypes, properties, state;
```

Chỉ nên đánh giá kế hoạch sử dụng index sau khi trạng thái là `ONLINE`. Trên dữ liệu có sẵn nhiều bản ghi, quá trình đưa index vào trạng thái `ONLINE` có thể cần thời gian.

### 4.3. Chạy Q1: tenant + status + khoảng ngày

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId, t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Kết quả logic mong đợi của dữ liệu mẫu:

| ticketId | createdAt (UTC) |
| --- | --- |
| `TK-006` | `2026-11-25T13:00:00Z` |
| `TK-002` | `2026-11-20T10:00:00Z` |
| `TK-001` | `2026-11-03T08:00:00Z` |

`TK-003` không khớp `OPEN`, `TK-004` nằm ngoài tháng 11 và `TK-005` thuộc tenant khác. Chỉ mục giúp **tăng tốc tìm kiếm**, nhưng **không thay đổi tập kết quả đúng về mặt logic**.

### 4.4. Chạy Q2: tenant + khoảng ngày, không có status

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId AS ticketId,
       t.status AS status,
       t.createdAt AS createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Q2 trả về cả ticket `CLOSED`, vì vậy một index riêng là ứng viên đáng đánh giá nếu Q2 thường xuyên và dữ liệu lớn:

```cypher
CREATE RANGE INDEX ticket_tenant_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.tenantId, t.createdAt);
```

So sánh hai index:

```text
(tenantId, status, createdAt)  -> phù hợp Q1
(tenantId,         createdAt)  -> phù hợp Q2
```

Nếu **chỉ** có chỉ mục ba trường, trình tối ưu có thể dùng phần thông tin phù hợp của nó, nhưng `status` nằm giữa `tenantId` và `createdAt` có thể khiến phần điều kiện khoảng và sắp xếp kém thuận lợi. Điều này phải được đo trên tập dữ liệu thực tế.

### 4.5. Chạy Q3: status + khoảng ngày, không có tenant

```cypher
MATCH (t:Ticket)
WHERE t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
RETURN t.ticketId AS ticketId, t.tenantId AS tenantId
ORDER BY t.createdAt DESC
LIMIT 20;
```

Nếu Q3 là luồng truy vấn quan trọng, có thể **cân nhắc**:

```cypher
CREATE RANGE INDEX ticket_status_created IF NOT EXISTS
FOR (t:Ticket)
ON (t.status, t.createdAt);
```

Không cần tạo mọi index nêu ra chỉ vì chúng có cú pháp hợp lệ. Mỗi index bổ sung chiếm dung lượng và gây chi phí bảo trì khi ghi. Chỉ duy trì những index đã chứng minh có giá trị với tải thực tế.

## 5. Thứ tự giữa các thuộc tính equality có quan trọng không?

Với Q1, cả hai chỉ mục dưới đây đều đặt **hai điều kiện bằng** trước **điều kiện khoảng**:

```text
(tenantId, status, createdAt)
(status, tenantId, createdAt)
```

Nếu một câu truy vấn luôn ràng buộc `tenantId = ...` **và** `status = ...`, cả hai là **ứng viên hợp lý**; không nên tuyên bố thứ tự nào luôn nhanh hơn mà chưa xem thống kê và kế hoạch.

Tuy nhiên, trên toàn bộ hệ thống:

- Truy vấn chỉ lọc **tenant** sẽ phù hợp hơn với một index bắt đầu bằng `tenantId`.
- Truy vấn chỉ lọc **status** sẽ phù hợp hơn với một index bắt đầu bằng `status`.
- `status` thường chỉ có vài giá trị như `OPEN`/`CLOSED`, còn `tenantId` có thể có rất nhiều giá trị; độ chọn lọc của từng điều kiện phụ thuộc vào phân bố dữ liệu.
- Mật độ và phân bố dữ liệu có thể thay đổi theo thời gian; cần đo trên dữ liệu đại diện, không chỉ dựa vào trực giác “trường nhiều giá trị nhất phải đứng đầu”.

Nên chọn thứ tự equality theo **tổ hợp truy vấn thường gặp**, khả năng tái sử dụng tiền tố và hiệu quả được quan sát, thay vì áp dụng một quy tắc cố định cho mọi mô hình.

## 6. Thứ tự chỉ mục và `ORDER BY`

Bên cạnh điều kiện `WHERE`, nhiều màn hình danh sách còn yêu cầu:

```cypher
ORDER BY t.createdAt DESC
LIMIT 20
```

Với chỉ mục `(tenantId, status, createdAt)` và cả `tenantId`, `status` đều được cố định bằng equality, các khóa theo `createdAt` có thể phù hợp cho việc lấy ticket mới nhất. Nếu planner hỗ trợ sử dụng thứ tự index cho trường hợp này, truy vấn có thể tránh một phép sắp xếp tốn kém.

Nhưng trường hợp sau **khác**:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
RETURN t.ticketId, t.status, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Nếu chỉ có index `(tenantId, status, createdAt)`, các ticket của `ACME` được nhóm theo `status` trước rồi mới theo `createdAt`. Toàn bộ tập ticket của tenant đó **không** mặc nhiên có thứ tự thời gian toàn cục. Với truy vấn này, `(tenantId, createdAt)` là ứng viên tự nhiên hơn.

**Điểm kiểm chứng:** Không suy ra truy vấn đã tránh sắp xếp chỉ từ việc có index. Hãy xem kế hoạch có toán tử `Sort`/`Top` hay không, có xuất hiện `Ordered by` trong các toán tử sử dụng index hay không (tùy phiên bản/công cụ), và lượng bản ghi thực tế đi qua từng bước. `LIMIT` không tự động biến một truy vấn thành nhanh nếu trước đó phải quét hoặc sắp xếp quá nhiều kết quả.

## 7. Dùng `EXPLAIN` và `PROFILE` để kiểm chứng

Hai truy vấn giống nhau về logic có thể có kế hoạch thực thi khác nhau theo dữ liệu và chỉ mục hiện có.

- `EXPLAIN`: **lập kế hoạch** nhưng không chạy truy vấn; dùng để xem Neo4j dự kiến truy cập dữ liệu ra sao.
- `PROFILE`: **chạy truy vấn thực tế** và bổ sung số bản ghi, số lần truy cập dữ liệu (chẳng hạn `DB Hits`) để đánh giá kế hoạch.
- Với phép đo hiệu năng, chạy trên dữ liệu đại diện, đối chiếu nhiều lần và cân nhắc ảnh hưởng cache; đừng kết luận từ bộ mẫu sáu node.

Bắt đầu bằng:

```cypher
EXPLAIN
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Sau đó có thể thay `EXPLAIN` bằng `PROFILE` để thu số liệu thực thi:

```cypher
PROFILE
MATCH (t:Ticket)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
  AND t.createdAt < datetime('2026-12-01T00:00:00Z')
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Khi đọc plan, đặt các câu hỏi:

1. Neo4j dùng `NodeIndexSeek`, `NodeIndexScan` hay `NodeByLabelScan` (tên toán tử có thể khác theo phiên bản)?
2. Index nào thực sự được chọn? Những thuộc tính nào tham gia vào phép tìm kiếm, những thuộc tính nào còn phải lọc bằng `Filter`?
3. `ORDER BY` được thỏa mãn nhờ thứ tự của index hay phải qua `Sort`/`Top`?
4. Số hàng đầu vào/đầu ra, `DB Hits` và thời gian phản hồi có giảm trên **dữ liệu đại diện** không?
5. Chi phí tạo và cập nhật index có tương xứng với số truy vấn đọc được cải thiện không?

Một kế hoạch **không sử dụng index trên sáu node** không chứng minh index sai. Với dữ liệu nhỏ, quét nhãn có thể rẻ hơn. Ngược lại, thấy tên một `NodeIndexSeek` cũng chưa đủ chứng minh truy vấn được tối ưu tốt nếu sau đó nó vẫn phải lọc/sắp xếp lượng dữ liệu lớn.

### Khi nào nên thử `USING INDEX`?

Cypher có index hint để định hướng planner trong một số trường hợp:

```cypher
MATCH (t:Ticket)
USING INDEX t:Ticket(tenantId, status, createdAt)
WHERE t.tenantId = 'ACME'
  AND t.status = 'OPEN'
  AND t.createdAt >= datetime('2026-11-01T00:00:00Z')
RETURN t.ticketId, t.createdAt;
```

Chỉ dùng hint khi đã biết index tồn tại, loại truy vấn phù hợp, và kế hoạch tự động thực sự chưa hiệu quả. Hint **không thay thế** việc chọn cấu trúc index đúng hay đo `PROFILE`; nó còn có thể làm kế hoạch khó thích nghi khi thống kê và phiên bản Neo4j thay đổi.

## 8. Các tình huống dễ chọn sai chỉ mục

### 8.1. Lọc bằng hàm trên thuộc tính

Ví dụ:

```cypher
WHERE date(t.createdAt) = date('2026-11-25')
```

Biểu thức áp hàm lên `t.createdAt` có thể khiến planner khó tận dụng trực tiếp điều kiện khoảng trên property đã được index. Khi lưu `createdAt` dưới dạng `datetime`, nên cân nhắc biến điều kiện ngày thành một khoảng:

```cypher
WHERE t.createdAt >= datetime('2026-11-25T00:00:00Z')
  AND t.createdAt < datetime('2026-11-26T00:00:00Z')
```

Khoảng thời gian phải được xây dựng theo **múi giờ nghiệp vụ** đúng; ví dụ trên diễn tả ngày UTC, không mặc định là ngày địa phương.

### 8.2. Chỉ một số property có giá trị

Composite property index phụ thuộc vào việc có dữ liệu cho các thuộc tính được đánh chỉ mục. Với node thiếu `status` hoặc `createdAt`, không được kỳ vọng index ba trường đáp ứng mọi điều kiện tra cứu như index riêng của `tenantId`. Cần xem tính bắt buộc của dữ liệu và mẫu `IS NULL`/`IS NOT NULL` thực tế trước khi quyết định.

### 8.3. Dùng một index quá rộng cho mọi truy vấn

Index `(tenantId, status, createdAt, priority, ownerId)` nghe có vẻ “đầy đủ”, nhưng không đương nhiên phục vụ hiệu quả truy vấn chỉ lọc `priority` hoặc chỉ sắp xếp `createdAt`. Thêm thuộc tính làm tăng dữ liệu index, chi phí cập nhật và có thể khiến truy vấn thiếu tiền tố không khai thác được phần cần thiết.

### 8.4. Tạo quá nhiều index gần trùng nhau

Mỗi lần sửa `status`, `createdAt` hoặc `tenantId` trên một node `Ticket`, những index liên quan có thể phải cập nhật. Mọi index cũng tiêu thụ tài nguyên lưu trữ và thời gian quản trị. Với hệ thống ghi nhiều, cần theo dõi **chi phí ghi**, không chỉ tốc độ đọc.

### 8.5. Dùng sai loại index

Composite range index trên property không phải giải pháp mặc định cho mọi bài toán:

- Tra cứu **nhãn node** / **loại relationship**: lookup index.
- Lọc, so sánh khoảng, có thứ tự với nhiều property: cân nhắc range index.
- Tìm kiếm văn bản tự do: cân nhắc full-text index hoặc loại index văn bản phù hợp theo kiểu predicate.
- Tìm kiếm không gian với tọa độ: cân nhắc point index.

### 8.6. Nghĩ rằng index xác định tính đúng của dữ liệu

Index giúp **truy cập nhanh**; constraint giúp **ràng buộc dữ liệu**, chẳng hạn `ticketId` duy nhất. Chọn index không thay thế việc kiểm soát kiểu dữ liệu, tenant isolation, hướng relationship hay xác thực tham số nghiệp vụ.

## 9. Vận dụng cho relationship và ứng dụng Java

Property graph có thể lưu thuộc tính ngay trên relationship. Cú pháp composite range index cho relationship tương tự node index:

```cypher
CREATE RANGE INDEX road_region_class IF NOT EXISTS
FOR ()-[r:ROAD]-()
ON (r.region, r.roadClass);
```

Index này là ứng viên cho truy vấn tìm `ROAD` theo khu vực và phân loại đường, **không** tự động tối ưu bài toán tìm đường ngắn nhất qua nhiều relationship. Truy vấn đường đi còn phụ thuộc cấu trúc graph và thuật toán traversal.

Trong **Neo4j Java Driver** hoặc **Spring Data Neo4j**, nên truyền `tenantId`, `status` và mốc thời gian bằng **tham số** thay vì nối chuỗi Cypher từ đầu vào người dùng. Ví dụ câu lệnh dành cho phía ứng dụng:

```cypher
MATCH (t:Ticket)
WHERE t.tenantId = $tenantId
  AND t.status = $status
  AND t.createdAt >= $from
  AND t.createdAt < $to
RETURN t.ticketId, t.createdAt
ORDER BY t.createdAt DESC
LIMIT 20;
```

Các tham số `$from`/`$to` cần được bind bằng kiểu temporal tương thích với `createdAt`. Các giá trị dữ liệu thay đổi theo yêu cầu người dùng; cấu trúc index và điều kiện lọc chủ đạo vẫn nên được thiết kế theo **những mẫu truy vấn ổn định** của ứng dụng.

## 10. Bảng quyết định nhanh cho các mẫu truy vấn

| Mẫu Cypher thường xuyên | Index nên đánh giá | Lý do |
| --- | --- | --- |
| `tenantId = x AND status = y AND createdAt BETWEEN ...` | `(tenantId, status, createdAt)` | Hai equality trước khoảng thời gian |
| `tenantId = x AND createdAt >= ...` | `(tenantId, createdAt)` | Không có `status` chen giữa |
| `status = y AND createdAt >= ...` | `(status, createdAt)` | Phục vụ truy vấn không có tenant |
| `tenantId = x ORDER BY createdAt DESC LIMIT k` | `(tenantId, createdAt)` | Có cơ hội tận dụng thứ tự theo ngày trong một tenant |
| `ticketId = id` | Constraint/index phù hợp trên `ticketId` | Tra cứu điểm theo định danh duy nhất |
| `createdAt >= ...` trên tất cả tenant | `(createdAt)` | Không cần tiền tố tenant/status |

`BETWEEN` trong bảng là ký hiệu minh họa khoảng giá trị; khi viết Cypher thực tế, dùng điều kiện so sánh `>=` và `<` như các ví dụ trước.

Đây là **danh sách ứng viên để đánh giá**, không phải chỉ dẫn tạo tất cả index. Ưu tiên query quan trọng, đo `PROFILE`, xem read/write workload, rồi giữ tập index nhỏ nhất đáp ứng mục tiêu hiệu năng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một index `(tenantId, status, createdAt)` đang phục vụ tốt truy vấn tìm ticket `OPEN` trong một tenant. Sản phẩm bổ sung màn hình “tất cả trạng thái, mới nhất trước”. Vì sao nên đánh giá thêm `(tenantId, createdAt)`?

<details>
<summary>Đáp án gợi ý</summary>

Vì màn hình mới không ràng buộc `status`. Chỉ mục ba trường nhóm kết quả theo `status` trước `createdAt`, nên không cung cấp mặc nhiên thứ tự `createdAt` toàn cục của một tenant. Chỉ mục hai trường phù hợp hơn với tiền tố equality `tenantId` và mục tiêu sắp xếp theo ngày.

</details>

**Câu 2.** Với truy vấn `WHERE tenantId = x AND status = y AND createdAt >= start`, có thể khẳng định `(tenantId, status, createdAt)` luôn nhanh hơn `(status, tenantId, createdAt)` không?

<details>
<summary>Đáp án gợi ý</summary>

Không. Cả hai đặt equality trước range và có thể là ứng viên tốt. Quyết định còn phụ thuộc các truy vấn khác chỉ lọc một trong hai trường, phân bố dữ liệu, thống kê và kế hoạch `EXPLAIN`/`PROFILE`.

</details>

**Câu 3.** Index `ticket_tenant_status_created` ở trạng thái `ONLINE` nhưng `PROFILE` vẫn cho thấy quét nhãn. Điều này nhất thiết là lỗi không?

<details>
<summary>Đáp án gợi ý</summary>

Không. Planner có thể thấy quét nhãn rẻ hơn trên dữ liệu rất nhỏ hoặc khi điều kiện lọc không đủ chọn lọc. Hãy kiểm tra kiểu predicate, kích thước và phân bố dữ liệu, thống kê cùng chi phí thực thi trước khi thay index hay ép dùng index hint.

</details>

**Câu 4.** Nếu truy vấn lọc tháng 11 bằng `date(t.createdAt) = date('2026-11-25')`, nên cân nhắc viết lại ra sao?

<details>
<summary>Đáp án gợi ý</summary>

Chuyển thành khoảng ngày trên thuộc tính nguyên gốc, ví dụ `t.createdAt >= datetime('2026-11-25T00:00:00Z') AND t.createdAt < datetime('2026-11-26T00:00:00Z')` khi quy ước ngày theo UTC. Cách này thể hiện điều kiện range trực tiếp lên property, giúp planner có cơ hội tận dụng range index hiệu quả hơn.

</details>

## Ghi nhớ

- **Chỉ mục ghép là một chuỗi thuộc tính có thứ tự**; thứ tự này nên phản ánh các mẫu `WHERE` và `ORDER BY` quan trọng nhất.
- Với truy vấn lọc bằng và lọc khoảng, **equality trước, range/sort sau** là điểm khởi đầu hữu ích.
- **Bỏ một thuộc tính ở giữa tiền tố** có thể làm chỉ mục kém phù hợp cho truy vấn; một index ba trường không tự động thay thế mọi index hai trường.
- **Lookup index** cho nhãn/loại relationship khác với **composite range index** trên property.
- Chỉ đánh giá tốc độ bằng **`EXPLAIN`/`PROFILE` trên dữ liệu đại diện**; cân bằng hiệu quả đọc với chi phí lưu trữ và cập nhật index.

### Tài liệu tham khảo

- [Neo4j Cypher Manual — Indexes for search performance](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/overview/)
- [Neo4j Cypher Manual — Indexes and query performance](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/using-indexes/)
- [Neo4j Cypher Manual — Query tuning (EXPLAIN, PROFILE)](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/)
