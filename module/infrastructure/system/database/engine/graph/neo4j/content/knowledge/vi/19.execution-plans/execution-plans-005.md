# Nhận diện quét dữ liệu, tìm bằng chỉ mục và mở rộng quan hệ trong kế hoạch thực thi Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc kết quả `EXPLAIN` và `PROFILE` để biết Cypher đang lấy dữ liệu từ đâu, theo cách nào và tốn chi phí ở bước nào.
- Nhận diện ba nhóm thao tác thường gặp trong kế hoạch thực thi: **quét dữ liệu (scan)**, **tìm bằng chỉ mục (index seek/scan)** và **mở rộng quan hệ (expand)**.
- Phân biệt `AllNodesScan`, `NodeByLabelScan`, `NodeIndexSeek`, `NodeUniqueIndexSeek`, `Expand(All)` và `Expand(Into)` ở mức ứng dụng.
- Sử dụng số hàng thực tế, ước lượng số hàng và `DB Hits` để tìm nguyên nhân truy vấn chậm, thay vì chỉ nhìn tên toán tử.
- Cải thiện hướng tìm kiếm trong property graph: chọn điểm xuất phát có độ chọn lọc cao, dùng index đúng thuộc tính và kiểm soát độ sâu đường đi.

Chương **Kế hoạch thực thi** thuộc module **DATABASE_ENGINE_GRAPH_NEO4J**. Với mô hình **property graph**, Neo4j lưu dữ liệu dưới dạng node, relationship và các thuộc tính. Cypher mô tả **mẫu dữ liệu cần tìm**, còn *query planner* quyết định cách lấy các node, duyệt cạnh và ghép kết quả để thực thi mẫu đó. Khả năng đọc kế hoạch giúp bạn hiểu vì sao một truy vấn quan hệ hoặc đường đi chạy nhanh hay chậm.

> Ví dụ và tên toán tử dưới đây theo ngữ nghĩa Cypher/Neo4j 5.x thông dụng. Tên toán tử, hình thức hiển thị, tùy chọn runtime và lựa chọn của planner có thể khác giữa các phiên bản Neo4j, dữ liệu, cấu hình và thống kê. Luôn kiểm tra kế hoạch thực tế trên hệ thống đang dùng.

## 1. Từ câu Cypher đến kế hoạch thực thi

Giả sử hệ thống bán hàng có ba loại node và hai loại relationship:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, email"] -->|PLACED| O["Order<br/>orderId, status"]
    O -->|CONTAINS| P["Product<br/>sku, name"]
~~~

Câu truy vấn nghiệp vụ:

~~~cypher
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId AS orderId;
~~~

Để thực thi, Neo4j có thể:

1. Tìm node khách hàng có `customerId` được yêu cầu.
2. Duyệt các relationship `PLACED` xuất phát từ khách hàng đó.
3. Kiểm tra node đích có label `Order` và trạng thái `PAID`.
4. Trả về `orderId`.

Nếu có index/constraint trên `Customer.customerId`, bước đầu có thể là **index seek**. Nếu không, kế hoạch có thể cần **scan label Customer** rồi lọc mã khách hàng. Nếu planner thấy bắt đầu từ tập `Order` đã trả tiền có chi phí thấp hơn, nó có thể chọn hướng khác. Thứ tự xuất hiện trong mẫu `MATCH` **không phải cam kết về thứ tự thực thi**.

~~~mermaid
flowchart TB
    Q["MATCH + WHERE + RETURN"] --> P["Query planner chọn kế hoạch"]
    P --> S["Tìm phần tử khởi đầu<br/>Scan hoặc Index Seek"]
    S --> E["Duyệt relationship<br/>Expand"]
    E --> F["Lọc, ghép, sắp xếp, trả kết quả"]
~~~

## 2. Cách xem EXPLAIN và PROFILE

### EXPLAIN: dự kiến, chưa chạy truy vấn

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId;
~~~

`EXPLAIN` lập kế hoạch nhưng **không thực thi phần truy vấn chính**. Nó phù hợp để kiểm tra truy vấn trước khi chạy trên tập dữ liệu lớn, hoặc trước một truy vấn ghi có thể gây thay đổi dữ liệu. Bạn nhận được các toán tử, thứ tự phụ thuộc và **Estimated Rows** (số hàng dự kiến, khi giao diện hỗ trợ).

### PROFILE: chạy thật và đo

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
WHERE o.status = 'PAID'
RETURN o.orderId;
~~~

`PROFILE` **thực thi truy vấn** và bổ sung thông tin đo như `Rows`, `DB Hits`, thời gian và thông số runtime (tùy phiên bản/giao diện). Nó hữu ích khi phân tích truy vấn chậm, nhưng cần nhớ:

- `PROFILE CREATE ...`, `PROFILE SET ...` hoặc `PROFILE DELETE ...` **thực sự ghi dữ liệu**; không dùng tùy tiện trên production.
- Tham số, lượng dữ liệu, cache và mức tải ảnh hưởng số đo; so sánh các lần thử trong điều kiện càng tương đồng càng tốt.
- `LIMIT` có thể giúp tránh trả về quá nhiều hàng, nhưng không bảo đảm mọi toán tử trước đó đều xử lý ít dữ liệu. Chẳng hạn `ORDER BY` hoặc phép tổng hợp có thể cần đọc rất nhiều hàng trước khi lấy `LIMIT`.

### Đọc kế hoạch theo luồng dữ liệu

Nhiều giao diện hiển thị kế hoạch dạng cây, trong đó toán tử **đầu vào** thường ở phía dưới và truyền hàng kết quả lên toán tử **cha**. Ví dụ *minh họa* (không phải một kế hoạch đo thực tế):

~~~text
ProduceResults
└─ Projection (o.orderId)
   └─ Filter (o.status = 'PAID')
      └─ Expand(All) ((c)-[:PLACED]->(o))
         └─ NodeUniqueIndexSeek (c:Customer(customerId = $customerId))
~~~

Đọc từ dưới lên: tìm một `Customer` bằng chỉ mục → mở rộng quan hệ đến các `Order` → lọc trạng thái → chiếu trường cần trả về. Đây là **một kế hoạch khả dĩ**; planner có thể đổi hướng hoặc chèn các toán tử khác khi thống kê, index và runtime thay đổi.

## 3. Nhóm 1: Quét dữ liệu (scan)

**Scan** là quá trình lấy một tập phần tử đồ thị theo phạm vi tương đối rộng, thường dựa trên toàn bộ node, label hoặc relationship type. Scan không mặc nhiên xấu; nó có thể là cách nhanh nhất khi dữ liệu nhỏ hoặc truy vấn cần đọc phần lớn phần tử.

| Toán tử thường gặp | Ý nghĩa | Truy vấn gợi ý |
| --- | --- | --- |
| `AllNodesScan` | Duyệt tập node trong database | `MATCH (n) RETURN n` |
| `NodeByLabelScan` | Lấy node mang một label | `MATCH (c:Customer) RETURN c` |
| `DirectedRelationshipTypeScan` | Tìm các relationship thuộc type với hướng xác định | `MATCH ()-[r:PLACED]->() RETURN r` |
| `UndirectedRelationshipTypeScan` | Tra cứu relationship theo type trong mẫu không định hướng | `MATCH ()-[r:PLACED]-() RETURN r` |

Tùy phiên bản Neo4j, các toán tử scan label/type có thể sử dụng **token lookup index**. Vì vậy, từ `NodeByLabelScan` **không thể kết luận** rằng database không dùng bất kỳ index nào. Nó chỉ cho thấy kế hoạch đang tiếp cận tập node qua *label*, chứ chưa tìm node bằng một **giá trị thuộc tính** cụ thể.

### 3.1. AllNodesScan: bắt đầu từ tất cả node

~~~cypher
EXPLAIN
MATCH (n)
WHERE n.active = true
RETURN n;
~~~

Nếu không có label, điểm khởi đầu có thể là `AllNodesScan`, tiếp theo là `Filter` theo `active`. Khi đồ thị có hàng chục triệu node, việc quét mọi node để tìm một số ít phần tử thường rất tốn kém.

Nếu nghiệp vụ chỉ quan tâm khách hàng, cung cấp label sẽ giúp thu hẹp tập xét:

~~~cypher
EXPLAIN
MATCH (c:Customer)
WHERE c.active = true
RETURN c;
~~~

Kế hoạch có thể dùng `NodeByLabelScan`, sau đó lọc `active`, hoặc một property index nếu có và được planner đánh giá là phù hợp.

### 3.2. NodeByLabelScan: quét tập có label

~~~cypher
EXPLAIN
MATCH (o:Order)
RETURN o.orderId
LIMIT 20;
~~~

Trong truy vấn chỉ cần lấy một số `Order` bất kỳ, quét theo label có thể hợp lý. Nếu thêm điều kiện chọn lọc cao như `o.orderId = $id`, index trên `orderId` có thể giúp tránh quét qua nhiều order không liên quan.

### 3.3. Scan relationship type

~~~cypher
EXPLAIN
MATCH ()-[r:PLACED]->()
RETURN r
LIMIT 20;
~~~

Khi chưa biết node đầu mút và chỉ biết type, planner có thể tìm các relationship `PLACED` trực tiếp bằng token lookup index. Không nhầm toán tử này với `Expand(All)`: **relationship type scan bắt đầu từ tập cạnh có type phù hợp**, còn **expand bắt đầu từ node đã được tìm** để lấy các cạnh kề.

### Khi nào scan có thể là lựa chọn đúng?

- Cần trả về phần lớn node của một label, ví dụ tác vụ thống kê hoặc xuất dữ liệu.
- Label chỉ có vài chục node; chi phí tìm bằng index riêng có thể không đem lại lợi ích đáng kể.
- Không có predicate trên thuộc tính đủ chọn lọc, hoặc không có index hỗ trợ predicate đó.
- Query planner cân nhắc dữ liệu, chi phí và thống kê rồi chọn scan.

Vì vậy, đánh giá scan bằng **quy mô dữ liệu được đọc và số hàng thực tế**, thay vì gắn nhãn “scan luôn chậm”.

## 4. Nhóm 2: Tìm bằng chỉ mục (index seek)

**Index seek** dùng cấu trúc chỉ mục để tìm những phần tử phù hợp với điều kiện trên thuộc tính. Nó thường hiệu quả khi chỉ một phần nhỏ dữ liệu thỏa predicate.

Giả sử ứng dụng thường xuyên tìm `Customer` theo `customerId` và `email`:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE RANGE INDEX customer_email_range IF NOT EXISTS
FOR (c:Customer)
ON (c.email);
~~~

Hai lệnh trên dành cho Neo4j có hỗ trợ cú pháp DDL tương ứng. Constraint duy nhất vừa bảo vệ định danh `customerId`, vừa có chỉ mục hỗ trợ truy vấn theo khóa. Range index giúp tìm theo `email` nhưng **không** tự bảo đảm email duy nhất.

Kiểm tra index đã tồn tại và sẵn sàng:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

Hãy chú ý `state`, nhãn và thuộc tính của index thay vì chỉ nhìn tên. Index cần đạt trạng thái phục vụ truy vấn, thông thường là `ONLINE`, trước khi dùng để đánh giá kết quả.

### 4.1. NodeIndexSeek và NodeUniqueIndexSeek

~~~cypher
EXPLAIN
MATCH (c:Customer {email: $email})
RETURN c.customerId;
~~~

Với index trên `Customer.email`, planner có thể chọn toán tử như `NodeIndexSeek`. Có thể có **nhiều** khách hàng dùng cùng email, trừ khi schema có constraint riêng bảo vệ tính duy nhất.

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
RETURN c.email;
~~~

Với uniqueness constraint trên `Customer.customerId`, một kế hoạch có thể sử dụng `NodeUniqueIndexSeek`. Điều kiện này nhận diện **tối đa một node** theo khóa đã được ràng buộc, giúp thu hẹp số hàng truyền sang các bước sau.

Đặt cạnh nhau:

| Toán tử | Điều kiện thường dẫn đến toán tử | Hàm ý khi đọc kế hoạch |
| --- | --- | --- |
| `NodeIndexSeek` | Có index thuộc tính, predicate phù hợp như phép bằng | Tra cứu các khóa thỏa điều kiện; có thể trả nhiều node |
| `NodeUniqueIndexSeek` | Predicate sử dụng index hậu thuẫn uniqueness constraint | Tra cứu theo giá trị khóa đã được đảm bảo duy nhất |
| `NodeIndexScan` | Đọc các entry trong property index theo điều kiện phù hợp, chẳng hạn kiểm tra thuộc tính tồn tại | Vẫn đi qua nhiều entry của index; không đồng nghĩa seek một giá trị |
| `NodeByLabelScan` | Lấy node mang label và có thể lọc thuộc tính sau đó | Không được xem là property index seek |

Các loại index khác, toán tử cho phạm vi và tên toán tử cụ thể tùy phiên bản. Ví dụ range index còn có thể hỗ trợ điều kiện khoảng giá trị (`<`, `>`, `>=`, `<=`) nếu biểu thức thuộc loại dữ liệu và hình dạng truy vấn được hỗ trợ.

### 4.2. Một index có thể thay đổi cách bắt đầu duyệt đồ thị

So sánh hai truy vấn cùng mục tiêu:

~~~cypher
// Không có bộ lọc theo khóa; có thể phải duyệt nhiều khách hàng.
EXPLAIN
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN o.orderId;

// Bộ lọc theo khóa xác định một khách hàng.
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

Truy vấn thứ hai có khả năng dùng index để tìm `c` rồi mới mở rộng quan hệ. Nhưng điều này không bảo đảm toàn bộ truy vấn rẻ: một khách hàng có hàng triệu đơn hàng vẫn có thể khiến bước mở rộng trở nên tốn kém.

### 4.3. Property index khác token lookup index

- **Token lookup index** hỗ trợ tìm node bằng **label** và relationship bằng **type**, có thể phục vụ các thao tác scan tương ứng.
- **Property index** hỗ trợ tìm theo **giá trị thuộc tính** dưới label/type phù hợp.
- **Uniqueness constraint** bảo vệ toàn vẹn giá trị khóa và có index hỗ trợ tương ứng.

Tra cứu `:Order` khác với tra cứu `Order.orderId = 'O-42'`. Việc có sẵn node-label lookup index **không** thay thế index trên `orderId`.

### 4.4. Index seek trên relationship

Neo4j hiện đại cũng hỗ trợ index thuộc tính của relationship. Ví dụ:

~~~cypher
CREATE RANGE INDEX transfer_amount_range IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
ON (r.amount);

EXPLAIN
MATCH ()-[r:TRANSFERRED]->()
WHERE r.amount > $minimumAmount
RETURN r;
~~~

Kế hoạch có thể dùng toán tử relationship property index seek khi điều kiện phù hợp và index có lợi về chi phí. Nếu chưa có index hoặc việc lọc theo `amount` không chọn lọc, planner có thể dùng relationship type scan rồi lọc. Điều này khác với mở rộng từ một tài khoản đã biết.

## 5. Nhóm 3: Mở rộng quan hệ (expand)

**Expand** là thao tác bắt đầu từ một node hoặc tập node **đã được tìm**, sau đó đi qua relationship phù hợp để nhận các node/relationship kế tiếp. Đây là điểm đặc trưng của truy vấn đồ thị và đường đi bằng Cypher.

### 5.1. Expand(All): từ node đã biết đến hàng xóm

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
~~~

Một chuỗi toán tử thường gặp:

~~~text
NodeUniqueIndexSeek (tìm Customer theo customerId)
    ↓
Expand(All) (tìm những Order qua quan hệ PLACED)
    ↓
Projection / ProduceResults
~~~

Ở `Expand(All)`, mỗi node đầu vào có thể tạo **nhiều hàng đầu ra**: một hàng cho mỗi quan hệ/đích khớp. Nếu một khách hàng có 10.000 đơn hàng, bước mở rộng có thể tạo xấp xỉ 10.000 hàng từ một hàng khách hàng, trước các bộ lọc tiếp theo. Số hàng và `DB Hits` của expand thường là chỉ báo quan trọng khi truy vấn có lượng quan hệ rất lớn.

Tên `All` trong `Expand(All)` ám chỉ cách toán tử lấy **các hàng xóm phù hợp**, **không có nghĩa quét toàn bộ database** như `AllNodesScan`.

### 5.2. Expand(Into): kiểm tra liên kết giữa hai node đã biết

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MATCH (c)-[:PLACED]->(o)
RETURN c.customerId, o.orderId;
~~~

Nếu planner đã ràng buộc được **cả `c` và `o`** trước khi kiểm tra cạnh, nó có thể dùng `Expand(Into)`: kiểm tra có quan hệ phù hợp giữa hai node đã biết, thay vì mở rộng từ một node để phát hiện node mới. Đây là **khả năng có thể xảy ra**, không phải cam kết của cú pháp. Khi optimizer chọn đường truy cập khác, toán tử thực tế cũng khác.

Lưu ý: `Expand(Into)` không đảm bảo chỉ trả một hàng. Nếu tồn tại nhiều relationship `PLACED` giữa cùng hai node, Cypher có thể trả nhiều hàng cho những quan hệ khác nhau. Cần khóa định danh/constraint hoặc mô hình dữ liệu phù hợp nếu nghiệp vụ yêu cầu chỉ có một liên kết.

### 5.3. Mở rộng nhiều bước và bùng nổ đường đi

~~~cypher
EXPLAIN
MATCH (a:Person {personId: $personId})-[:KNOWS*1..3]->(b:Person)
RETURN DISTINCT b.personId;
~~~

Truy vấn duyệt quan hệ `KNOWS` từ một đến ba bước. Tùy phiên bản và cách lập kế hoạch, bạn có thể gặp toán tử dạng `VarLengthExpand(All)`, `VarLengthExpand(Into)` hoặc toán tử duyệt đường đi khác. Khi độ phân nhánh trung bình là `d`, số khả năng mở rộng có thể tăng nhanh theo độ sâu, gần mức `d + d² + d³` trong một mô hình đơn giản chưa loại trùng. Đây **không phải công thức đo chi phí chính xác**: dữ liệu có chu trình, các node lặp và điều kiện lọc làm thay đổi số đường đi thực tế.

Để giới hạn chi phí:

1. Bắt đầu từ node chọn lọc bằng khóa/index.
2. Giới hạn độ sâu hợp lý, ví dụ `*1..3` thay vì không giới hạn.
3. Chỉ định loại và hướng relationship cần thiết.
4. Giảm tập kết quả khi có thể; hiểu rằng `DISTINCT` xử lý trùng sau khi một phần công việc mở rộng đã xảy ra.
5. Kiểm tra số hàng ở mỗi bước trong `PROFILE` để phát hiện bùng nổ trung gian.

### 5.4. Relationship type scan khác expand ra sao?

~~~cypher
// Chưa biết node nguồn: có thể quét type.
MATCH ()-[r:PLACED]->()
RETURN r;

// Đã biết node nguồn: có thể mở rộng quan hệ từ node đó.
MATCH (c:Customer {customerId: $id})-[r:PLACED]->(o)
RETURN r, o;
~~~

Ở ví dụ đầu, quyền truy cập tốt thường là tìm các relationship `PLACED` trong database. Ở ví dụ sau, tìm `c` trước rồi duyệt **cạnh kề `c`** có thể tốt hơn nhiều nếu khách hàng có ít đơn so với tổng số quan hệ `PLACED`.

## 6. Phân biệt ba nhóm toán tử trong một kế hoạch

Hãy đặt câu hỏi theo thứ tự:

| Bước cần tìm hiểu | Dấu hiệu trong kế hoạch | Câu hỏi chẩn đoán |
| --- | --- | --- |
| **Điểm xuất phát** | `AllNodesScan`, `NodeByLabelScan`, `NodeIndexSeek`, `NodeUniqueIndexSeek` | Có đang quét quá nhiều node chỉ để tìm vài phần tử không? |
| **Lấy quan hệ** | `DirectedRelationshipTypeScan`, `Expand(All)`, `Expand(Into)` | Có điểm neo đã biết không? Độ phân nhánh mỗi node là bao nhiêu? |
| **Mở rộng nhiều bước** | `VarLengthExpand` hoặc toán tử duyệt đường đi tương ứng | Độ sâu, số hàng trung gian và điều kiện chặn có hợp lý không? |
| **Lọc/ghép dữ liệu** | `Filter`, `NodeHashJoin`, `CartesianProduct` và toán tử khác | Lọc diễn ra sớm hay sau khi đã sinh rất nhiều hàng? |
| **Trả kết quả** | `Projection`, `Sort`, `Distinct`, `ProduceResults` | Có sắp xếp/loại trùng trên tập trung gian quá lớn không? |

Ví dụ giả lập sau chỉ dùng để **minh họa cách nhận diện luồng**, không phải output chính xác của Neo4j:

~~~text
ProduceResults
└─ Projection
   └─ Filter (Order.status = 'PAID')
      └─ Expand(All) [:PLACED]
         └─ NodeUniqueIndexSeek :Customer(customerId)
~~~

Điểm khởi đầu đã tối ưu nhờ index, nhưng nếu `Filter` loại tới 99,9% các order **sau** khi đã mở rộng hàng triệu quan hệ, chi phí vẫn có thể lớn. Khi đó cần đo xem bắt đầu từ `Order.status` hoặc thay đổi cách mô hình/truy vấn có tốt hơn không. Không thể kết luận chỉ từ cây giả lập; phải xem độ chọn lọc thực tế.

## 7. Đọc số đo trong PROFILE để tìm nút thắt

Trong bảng kế hoạch thực thi Neo4j Browser hoặc công cụ tương ứng, các cột có thể gồm:

| Thông số | Cách hiểu | Dấu hiệu cần chú ý |
| --- | --- | --- |
| **Estimated Rows** | Số hàng planner ước lượng trước khi chạy | Sai lệch lớn với `Rows` có thể dẫn đến lựa chọn join/điểm xuất phát kém |
| **Rows** | Số hàng thực sự đi qua toán tử trong lần chạy | Một hàng đầu vào expand thành hàng trăm nghìn hàng |
| **DB Hits** | Các lần chạm tới dữ liệu lưu trữ ở mức bộ máy truy vấn | Rất nhiều hits ở scan/expand là điểm cần điều tra |
| **Page Cache Hits/Misses** | Tương tác với bộ đệm trang, nếu được báo cáo | Misses cao có thể tăng I/O vật lý |
| **Time / Memory** | Thời gian và tài nguyên, tùy runtime/giao diện | `Sort`, `Eager` hoặc join cần giữ nhiều dữ liệu |

Đừng hiểu **DB Hits = số lần đọc đĩa**: một DB Hit có thể được phục vụ từ cache. Không được suy thời gian thực thi chỉ từ một con số DB Hits, cũng không so sánh các môi trường có dữ liệu, cache hoặc tải khác nhau mà không kiểm soát điều kiện.

### Những dấu hiệu thường gặp

- `AllNodesScan` đọc hàng triệu node nhưng chỉ vài node qua `Filter`: thiếu label, predicate hoặc property index phù hợp.
- `NodeByLabelScan` trả rất nhiều hàng và lọc `email` còn vài hàng: cân nhắc index trên `email` nếu truy vấn phổ biến.
- `NodeIndexSeek` trả rất ít hàng nhưng `Expand(All)` phình lên hàng triệu hàng: vấn đề nằm ở **fan-out quan hệ**.
- Có `CartesianProduct` trên hai tập lớn không có ràng buộc: số cặp có thể tăng theo **tích** số hàng hai nhánh.
- `Sort` hoặc `Distinct` nhận tập trung gian rất lớn: kiểm tra khả năng lọc sớm, thứ tự trả về, index hỗ trợ và tính cần thiết của các phép xử lý.

Một truy vấn có scan không đồng nghĩa chậm; một truy vấn có index seek cũng không đồng nghĩa nhanh. **Tập hàng trung gian** mới là yếu tố cần đánh giá xuyên suốt kế hoạch.

## 8. Bài thực hành với một mô hình nhỏ

Giả sử bạn có quyền chạy Cypher trên database thực hành. Tạo cấu trúc dữ liệu tối thiểu:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;

MERGE (c:Customer {customerId: 'C-001'})
SET c.email = 'c001@example.org'
MERGE (o1:Order {orderId: 'O-001'})
SET o1.status = 'PAID'
MERGE (o2:Order {orderId: 'O-002'})
SET o2.status = 'PENDING'
MERGE (c)-[:PLACED]->(o1)
MERGE (c)-[:PLACED]->(o2);
~~~

Thử lần lượt:

~~~cypher
// A. Truy cập theo label; không có predicate thuộc tính.
EXPLAIN
MATCH (c:Customer)
RETURN c.customerId;

// B. Truy cập theo ID được bảo vệ bởi uniqueness constraint.
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})
RETURN c.email;

// C. Tìm khách hàng theo ID rồi đi qua quan hệ PLACED.
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})-[:PLACED]->(o:Order)
RETURN o.orderId;

// D. Chỉ biết loại relationship, không có node khởi đầu.
EXPLAIN
MATCH ()-[r:PLACED]->()
RETURN r;
~~~

**Dự đoán rồi kiểm tra**:

| Truy vấn | Toán tử ứng viên | Vì sao? |
| --- | --- | --- |
| A | `NodeByLabelScan` | Lấy node theo label `Customer` |
| B | `NodeUniqueIndexSeek` | Tìm theo khóa có uniqueness constraint |
| C | `NodeUniqueIndexSeek` + `Expand(All)` | Lấy một khách hàng trước, rồi lấy các đơn liên quan |
| D | `DirectedRelationshipTypeScan` | Bắt đầu từ type `PLACED` khi chưa biết node đầu mút |

Đây là các **ứng viên**, không phải lời cam kết planner phải sinh đúng toán tử ấy. Với dữ liệu ít, planner có thể lựa chọn khác. Nếu muốn xem số liệu đo, đổi `EXPLAIN` sang `PROFILE` cho các truy vấn chỉ đọc và quan sát Rows/DB Hits.

### Thực hành nhận diện Expand(Into)

~~~cypher
EXPLAIN
MATCH (c:Customer {customerId: 'C-001'})
MATCH (o:Order {orderId: 'O-001'})
MATCH (c)-[:PLACED]->(o)
RETURN c.customerId, o.orderId;
~~~

Nếu hai index giúp planner tìm hai node đầu mút trước, bạn có thể thấy `Expand(Into)`. Nếu không thấy, hãy giải thích **kế hoạch thực tế đã chọn điểm xuất phát nào**, thay vì cố gắng biến truy vấn thành một mẫu có sẵn.

## 9. Quy trình tối ưu khi phát hiện scan hoặc expand quá tốn kém

1. **Ghi nhận truy vấn gốc và tham số thực tế.** Tham số khác nhau có thể dẫn tới độ chọn lọc rất khác.
2. **Chạy `EXPLAIN`** để xác định điểm khởi đầu và chuỗi phụ thuộc giữa scan, index seek và expand.
3. **Chạy `PROFILE` an toàn** với dữ liệu đại diện để xem chênh lệch Estimated Rows/Rows, DB Hits và điểm phình số hàng.
4. **Kiểm tra schema index/constraint.** Nếu thường xuyên tìm theo `Customer.customerId`, bảo đảm có index phù hợp và đang `ONLINE`.
5. **Cung cấp predicate chính xác, đủ chọn lọc.** Dùng label, relationship type và khóa nghiệp vụ ở điểm bắt đầu; tránh lọc muộn sau khi mở rộng quá nhiều cạnh.
6. **Giới hạn độ sâu/độ rộng duyệt khi nghiệp vụ cho phép.** Truy vấn nhiều bước hoặc nhiều nhánh quan hệ có thể tăng cực nhanh.
7. **Đo lại cùng kịch bản.** So sánh thời gian, Rows, DB Hits, bộ nhớ và kết quả nghiệp vụ; không tối ưu chỉ để đổi tên toán tử.

### Có nên dùng index hint?

Cypher cho phép đưa gợi ý planner trong những trường hợp cần kiểm soát chiến lược truy cập:

~~~cypher
EXPLAIN
MATCH (c:Customer)
USING INDEX c:Customer(customerId)
WHERE c.customerId = $customerId
RETURN c;
~~~

Index hint có thể hữu ích khi bạn đã có bằng chứng planner chọn chiến lược kém do thống kê hoặc đặc điểm dữ liệu. Nhưng hint **không tạo index**, không thay thế index phù hợp và có thể trở nên bất lợi khi tập dữ liệu thay đổi. Ưu tiên đo lường và xác nhận nguyên nhân trước khi ép lựa chọn bằng hint.

### Một sai lầm về phép nối dữ liệu

~~~cypher
// Hai tập chưa có ràng buộc; có thể gây tích Descartes.
MATCH (c:Customer), (o:Order)
RETURN c.customerId, o.orderId;
~~~

Nếu có 100.000 khách hàng và 1.000.000 đơn hàng, tập cặp có thể lớn tới 100 tỷ hàng trước khi giới hạn hoặc lọc phù hợp. Với nghiệp vụ tìm đơn của khách hàng, biểu diễn chính xác cạnh đồ thị:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.customerId = $customerId
RETURN o.orderId;
~~~

Điều này cho planner thông tin về mối liên hệ cần duyệt, đồng thời tránh sinh các cặp không liên quan.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** `NodeByLabelScan` chứng minh database không có index nào hay không?

**Trả lời:** Không. Toán tử quét theo label có thể được hỗ trợ bằng **token lookup index**. Nó khác với việc tìm theo giá trị thuộc tính qua property index.

**Câu 2.** Một `NodeUniqueIndexSeek` trả một node, nhưng truy vấn vẫn chậm. Bạn xem bước nào tiếp theo?

**Trả lời:** Xem `Expand(All)` hoặc phép ghép/lọc tiếp theo có tạo quá nhiều hàng hay không, nhất là khi node có rất nhiều relationship. Kiểm tra Rows, DB Hits và các toán tử `Sort`, `Distinct`, join.

**Câu 3.** Khi nào `Expand(Into)` là ứng viên phù hợp?

**Trả lời:** Khi cả hai đầu mút đã được ràng buộc và kế hoạch cần kiểm tra có relationship thích hợp giữa chúng; planner có thể chọn cách khác nếu chi phí hợp lý hơn.

**Câu 4.** Có nên thêm property index cho mọi thuộc tính để không còn scan?

**Trả lời:** Không. Index tiêu tốn dung lượng và chi phí duy trì khi ghi; một số truy vấn cần quét phần lớn dữ liệu hoặc bắt đầu từ node khác. Chỉ tạo index theo nhu cầu truy vấn và kết quả đo.

**Câu 5.** `PROFILE` của một lệnh xóa có an toàn trên production chỉ vì bạn đang “xem kế hoạch” không?

**Trả lời:** Không. `PROFILE` **chạy thật** cả lệnh xóa; dùng `EXPLAIN` để xem kế hoạch mà không thực thi.

## 11. Checklist ghi nhớ

- **Scan**: lấy nhiều node hoặc relationship theo phạm vi rộng; đọc `AllNodesScan`, `NodeByLabelScan`, relationship type scan.
- **Index seek**: truy cập phần tử theo giá trị thuộc tính có index hỗ trợ; đọc `NodeIndexSeek` và `NodeUniqueIndexSeek`.
- **Expand**: bắt đầu từ node đã biết và đi qua relationship; `Expand(All)` lấy hàng xóm, `Expand(Into)` kiểm tra kết nối giữa hai node đã ràng buộc.
- **Điểm xuất phát tốt** thường là tập nhỏ và có predicate chọn lọc cao, nhưng planner có thể chọn hướng khác theo chi phí.
- **Rows, Estimated Rows, DB Hits, cache và bộ nhớ** cần được đọc cùng nhau; chỉ riêng tên toán tử không nói hết hiệu năng.
- **`EXPLAIN` chỉ lập kế hoạch**, **`PROFILE` thực thi truy vấn**; cẩn thận với truy vấn ghi.
- **Token lookup index khác property index**; index giúp tìm đúng điểm neo, nhưng không tự giải quyết fan-out, đường đi nhiều bước, join hoặc sort lớn.

**Kết luận:** Đọc kế hoạch thực thi Neo4j là theo dõi dòng dữ liệu từ **scan/index seek** đến **expand** rồi tới **lọc/ghép/trả kết quả**. Khi nhận diện được toán tử khởi đầu và nơi số hàng trung gian tăng mạnh, bạn có thể tối ưu Cypher và schema bằng bằng chứng thực tế thay vì phỏng đoán.
