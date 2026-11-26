# Token lookup index cho nhãn và loại quan hệ trong Neo4j

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích **token lookup index** giúp Neo4j tìm node theo **label** và relationship theo **type** như thế nào.
- Phân biệt lookup index với property index, uniqueness constraint và các loại index phục vụ truy vấn thuộc tính.
- Kiểm tra, tạo lại khi cần và quan sát việc sử dụng lookup index bằng Cypher cùng kế hoạch thực thi.
- Nhận biết những tình huống lookup index hữu ích, những trường hợp nó không đủ, và các lưu ý khi vận hành đồ thị lớn.

Bài thuộc chương **Chỉ mục tra cứu** của module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j lưu dữ liệu dưới dạng *property graph*: node có nhãn (*label*), relationship có loại (*type*), cả hai có thể chứa thuộc tính. Khi học Cypher, nhiều câu truy vấn bắt đầu bằng việc tìm các node mang nhãn nhất định hoặc các cạnh thuộc một loại nhất định. **Token lookup index** được thiết kế cho bước tìm kiếm cấu trúc này.

## 1. Vì sao cần lookup theo nhãn và loại quan hệ?

Giả sử một hệ thống thương mại điện tử chứa hàng triệu node thuộc các nhãn `Customer`, `Order`, `Product` và nhiều loại quan hệ như `PLACED`, `CONTAINS`, `VIEWED`:

~~~cypher
MATCH (c:Customer)
RETURN c.customerId
LIMIT 20;
~~~

Câu truy vấn cần tìm các node có **nhãn `Customer`**. Nó không tìm theo `customerId` cụ thể và cũng không yêu cầu giá trị thuộc tính nào khác. Ví dụ khác:

~~~cypher
MATCH (c)-[r:PLACED]->(o)
RETURN r
LIMIT 20;
~~~

Câu truy vấn thứ hai yêu cầu các relationship có **type `PLACED`**. Khi không có đầu mút đã được xác định trước, database cần cách tìm các relationship thuộc type đó.

Token lookup index giúp Neo4j tìm nhóm phần tử đồ thị theo token cấu trúc:

| Đối tượng | Token được lập chỉ mục | Ví dụ truy vấn |
| --- | --- | --- |
| Node | Label | `MATCH (n:Customer) RETURN n` |
| Relationship | Relationship type | `MATCH ()-[r:PLACED]->() RETURN r` |

Một node có thể mang **nhiều nhãn**, ví dụ `(n:Customer:Premium)`; nó có thể xuất hiện khi tra cứu theo từng nhãn phù hợp. Mỗi relationship có **một type**, chẳng hạn `PLACED`.

Về mặt ý tưởng, lookup index giống một bảng tra cứu từ **token → các phần tử có token đó**. Neo4j quản lý cơ chế lưu trữ và truy vấn nội bộ; ứng dụng không cần tự tạo danh sách ID node cho từng label hay ID cạnh cho từng type.

~~~mermaid
flowchart LR
    Q["Cypher: MATCH (n:Customer)"] --> L["Tra cứu token label Customer"]
    L --> N["Các node mang label Customer"]
    R["Cypher: MATCH ()-[r:PLACED]->()"] --> T["Tra cứu token type PLACED"]
    T --> E["Các relationship thuộc type PLACED"]
~~~

Điều quan trọng: lookup index trả lời **“phần tử nào thuộc nhãn/loại này?”**. Nó không trả lời trực tiếp **“khách hàng nào có email cụ thể?”**.

## 2. Hai nhóm token lookup index

### 2.1. Node label lookup index

Node lookup index phục vụ việc truy cập node theo label, ví dụ:

~~~cypher
MATCH (p:Person)
RETURN p.name
LIMIT 10;

MATCH (p:Person:Employee)
RETURN p.employeeId;
~~~

Ở truy vấn hai nhãn, hệ quản trị có thể dùng thông tin lookup của một nhãn rồi kiểm tra nhãn còn lại, hoặc lựa chọn kế hoạch khác theo thống kê. Lookup index không có nghĩa là tồn tại một chỉ mục tổng hợp riêng cho mọi tổ hợp label.

### 2.2. Relationship type lookup index

Relationship lookup index giúp tìm các relationship theo type:

~~~cypher
MATCH ()-[r:WORKS_AT]->()
RETURN r
LIMIT 10;

MATCH (a)-[r:PURCHASED]->(b)
RETURN a, r, b
LIMIT 10;
~~~

Trong ví dụ trên, truy vấn thứ hai có thể tận dụng lookup theo `PURCHASED` khi phải tìm relationship từ type. Tuy nhiên, nếu trước đó đã tìm được node đầu mút rất chọn lọc, Neo4j cũng có thể **mở rộng quan hệ từ node đó** (*expand*) và lọc type. Phương án thực thi phụ thuộc kế hoạch do query planner chọn.

**Không nhầm lẫn:** Lookup theo type `PURCHASED` là tra cứu *type của relationship*, không phải tìm một chuỗi ký tự bên trong thuộc tính của relationship.

## 3. Tạo và kiểm tra lookup index bằng Cypher

### 3.1. Kiểm tra những index sẵn có

Trong các phiên bản Neo4j 5.x hiện đại, một database mới thông thường đã có **node label lookup index** và **relationship type lookup index** do hệ thống tạo sẵn. Vì vậy, bước đầu tiên là kiểm tra thay vì tạo thêm theo thói quen.

~~~cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state
RETURN name, entityType, state
ORDER BY entityType;
~~~

Kết quả điển hình có một hàng `NODE` và một hàng `RELATIONSHIP`, với `state` là `ONLINE` khi chỉ mục sẵn sàng phục vụ truy vấn. **Tên index do Neo4j cấp có thể khác nhau giữa các database**; không giả định tên cố định khi viết script vận hành.

Cũng có thể xem index cùng các nhóm khác:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, state
WHERE type = 'LOOKUP'
RETURN name, type, entityType, state;
~~~

Nếu index đang được tạo, trạng thái có thể đang trong quá trình xây dựng; chỉ nên coi nó sẵn sàng khi trạng thái thích hợp, thường là `ONLINE`.

### 3.2. Tạo node label lookup index

Khi cần tạo lại index đã bị xóa hoặc đang khởi tạo một database không có index tương ứng:

~~~cypher
CREATE LOOKUP INDEX node_label_lookup_index IF NOT EXISTS
FOR (n)
ON EACH labels(n);
~~~

Phân tích cú pháp:

- `CREATE LOOKUP INDEX` chỉ rõ loại index là **lookup**.
- `node_label_lookup_index` là tên index do người vận hành đặt.
- `IF NOT EXISTS` tránh lỗi tạo lại trong trường hợp đã có index phù hợp hoặc tên bị chiếm theo quy tắc của Neo4j; sau đó vẫn cần kiểm tra schema thực tế.
- `FOR (n) ON EACH labels(n)` xác định chỉ mục trên **token nhãn** của các node. Đây không phải một nhãn được chỉ định cụ thể.

### 3.3. Tạo relationship type lookup index

~~~cypher
CREATE LOOKUP INDEX relationship_type_lookup_index IF NOT EXISTS
FOR ()-[r]-()
ON EACH type(r);
~~~

Phần `FOR ()-[r]-()` chỉ ra relationship; `ON EACH type(r)` lấy **token loại quan hệ**. Index này phục vụ nhiều type của relationship trong cùng database, không phải một index riêng cho type `PLACED` hay `WORKS_AT`.

**Phạm vi và giới hạn:** Neo4j hỗ trợ một lookup index cho node và một lookup index cho relationship trong mỗi database. Không tạo một lookup index thứ hai chỉ để dành riêng cho nhãn `Customer` hay loại quan hệ `PLACED`. Nếu chỉ mục tương ứng đã tồn tại, việc dùng `IF NOT EXISTS` không tạo thêm chỉ mục thứ hai. Hãy dùng `SHOW LOOKUP INDEXES` để xác nhận sau DDL.

### 3.4. Xóa index trong vận hành

Nếu buộc phải xóa một lookup index, phải lấy **đúng tên hiện có** từ `SHOW LOOKUP INDEXES`:

~~~cypher
// Chỉ là ví dụ: dùng tên index thật trên database cần thao tác.
DROP INDEX node_label_lookup_index IF EXISTS;
~~~

Xóa lookup index có thể làm những câu tìm kiếm label/type tốn chi phí hơn; không coi việc xóa là một tối ưu thường quy. Trên database đang phục vụ ứng dụng, cần đánh giá tác động, quyền quản trị schema và phương án khôi phục trước khi thao tác.

## 4. Chạy thử trên một đồ thị nhỏ

Giả sử tạo dữ liệu nhân viên và công ty:

~~~cypher
MERGE (p:Person {personId: 'P-001'})
SET p.name = 'An'
MERGE (c:Company {companyId: 'C-001'})
SET c.name = 'GraphLab'
MERGE (p)-[:WORKS_AT]->(c);
~~~

Ví dụ dùng `MERGE` để dễ chạy lại khi học, nhưng lưu ý `MERGE` không thay thế **uniqueness constraint** khi có nhiều transaction ghi đồng thời. Với dữ liệu thật, cần thiết kế business key và constraint phù hợp.

Truy vấn node theo label:

~~~cypher
MATCH (p:Person)
RETURN p.personId AS id, p.name AS name;
~~~

Truy vấn relationship theo type:

~~~cypher
MATCH (p)-[r:WORKS_AT]->(c)
RETURN p.name AS person, type(r) AS relation, c.name AS company;
~~~

Trong cả hai truy vấn, `Person` và `WORKS_AT` là **token**; `personId`, `name`, `companyId` là **thuộc tính**.

### Dùng EXPLAIN và PROFILE

`EXPLAIN` cho biết kế hoạch mà Neo4j dự kiến dùng mà không chạy truy vấn. `PROFILE` thực sự chạy truy vấn và hiển thị số hàng, lượt truy cập lưu trữ (*DB Hits*) cùng các toán tử thực thi:

~~~cypher
EXPLAIN
MATCH (p:Person)
RETURN p.personId
LIMIT 10;

PROFILE
MATCH ()-[r:WORKS_AT]->()
RETURN r
LIMIT 10;
~~~

Trong kế hoạch, bạn có thể gặp toán tử như `NodeByLabelScan` (tìm node theo label), `DirectedRelationshipTypeScan` hoặc `UndirectedRelationshipTypeScan` (quét relationship theo type), tùy hướng mẫu và phiên bản Neo4j. Đó là những biểu hiện liên quan đến truy cập theo label/type. **Đừng chỉ suy luận từ tên toán tử:** hãy xem toàn bộ kế hoạch, index đang `ONLINE`, cardinality và DB Hits.

Cũng không nên chọn các truy vấn như `MATCH (n:Person) RETURN count(n)` làm bằng chứng bắt buộc rằng lookup index được dùng: Neo4j có thể tối ưu phép đếm bằng cơ chế riêng, chẳng hạn count store.

## 5. Token lookup index khác property index ở đâu?

Đây là điểm cốt lõi của thiết kế index trong property graph.

~~~cypher
// Có label; điều kiện thuộc tính email có giá trị cụ thể.
MATCH (c:Customer)
WHERE c.email = $email
RETURN c;
~~~

Lookup index giúp tiếp cận nhóm node mang label `Customer`, nhưng **không lập chỉ mục giá trị `email`**. Nếu nhóm này rất lớn, việc lọc từng node sẽ không hiệu quả. Khi truy vấn thường xuyên tìm theo email, cân nhắc thêm property index:

~~~cypher
CREATE RANGE INDEX customer_email_range IF NOT EXISTS
FOR (c:Customer)
ON (c.email);
~~~

Lúc này query planner có thể chọn property index để tìm node theo giá trị `email` khi chi phí phù hợp. Không có đảm bảo rằng mọi truy vấn có `WHERE` đều sử dụng index; planner xét điều kiện, thống kê và các cách đi qua đồ thị.

| Loại | Lập chỉ mục | Truy vấn điển hình | Không thay thế cho |
| --- | --- | --- | --- |
| **Node token lookup** | Label của node | `MATCH (n:Customer)` | Tìm theo `email`, `age`, `createdAt` |
| **Relationship token lookup** | Type của relationship | `MATCH ()-[r:PLACED]->()` | Tìm cạnh theo `orderTime`, `amount` |
| **Range property index** | Giá trị thuộc tính của node hoặc relationship | `c.email = $email`, khoảng giá trị phù hợp | Tra cứu mọi label/type ở cấp database |
| **Text/full-text index** | Nội dung văn bản theo khả năng và cú pháp từng loại | Tiền tố/chuỗi; tìm kiếm văn bản | Tra cứu token label/type |
| **Uniqueness constraint** | Quy tắc không cho khóa dữ liệu trùng; thường có index hỗ trợ | Danh tính `customerId` duy nhất | Tra cứu toàn bộ một label hoặc type |

Một constraint như:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

phục vụ **toàn vẹn danh tính khách hàng** và có index hỗ trợ kiểm tra/tra cứu khóa. Nó không phải token lookup index. Ngược lại, lookup index **không ngăn** hai node `Customer` có cùng `customerId`.

### Khi truy vấn có nhiều điều kiện

~~~cypher
MATCH (c:Customer)-[r:PLACED]->(o:Order)
WHERE c.customerId = $customerId
  AND o.status = 'PAID'
RETURN o.orderId, r;
~~~

Một kế hoạch hợp lý có thể bắt đầu từ index theo `Customer.customerId`, rồi **expand** qua quan hệ `PLACED` và lọc `Order.status`. Neo4j không nhất thiết phải dùng lookup index cho `Customer`, `Order` hay `PLACED` trong trường hợp này. Mục tiêu là **kế hoạch hiệu quả**, không phải ép mọi query sử dụng token lookup index.

## 6. Những hiểu lầm thường gặp

### “Mỗi label cần một lookup index”

Không. Một node lookup index bao phủ các token label của database. Cú pháp `ON EACH labels(n)` không chọn riêng `:Person` hoặc `:Product`.

### “Có lookup index thì truy vấn theo thuộc tính sẽ nhanh”

Chưa đủ. Lookup index đưa bạn tới các phần tử mang label/type; phép lọc `WHERE c.email = ...` vẫn cần kế hoạch phù hợp và thường hưởng lợi từ property index hay constraint trên khóa tra cứu.

### “Relationship type lookup index là index cho mọi phép duyệt cạnh”

Không. Khi đã có node bắt đầu, Neo4j có thể duyệt relationship kề node và kiểm tra type mà không cần quét tất cả relationship của type tương ứng. Các truy vấn đường đi nhiều bước như:

~~~cypher
MATCH (a:Person {personId: $personId})-[:KNOWS*1..3]->(b:Person)
RETURN DISTINCT b;
~~~

còn phụ thuộc mạnh vào độ phân nhánh, độ sâu và số đường đi. Lookup index không giải quyết toàn bộ chi phí duyệt đồ thị.

### “Thêm hoặc xóa nhãn không liên quan đến lookup index”

Lookup index phản ánh nhãn và loại quan hệ của dữ liệu hiện tại. Khi thêm/bỏ label của node hoặc tạo/xóa relationship, hệ thống cần duy trì cấu trúc tra cứu tương ứng. Đây là một phần chi phí ghi, đổi lại truy vấn tra cứu theo token được hỗ trợ.

### “Tạo lookup index giúp tránh node/relationship trùng”

Không. Ngăn trùng dữ liệu nghiệp vụ đòi hỏi **khóa định danh**, `MERGE` phù hợp, constraint và xử lý đồng thời. Lookup index không đảm bảo rằng mỗi label chỉ có một node hay mỗi type chỉ có một relationship.

### “Viết WHERE labels(n) hoặc type(r) là chắc chắn dùng lookup index”

Không thể kết luận như vậy. Một mẫu Cypher thể hiện rõ label/type tĩnh, như `(n:Customer)` hoặc `[r:PLACED]`, giúp planner nhận diện điều kiện cấu trúc. Các biểu thức động hoặc phép lọc bằng hàm có thể dẫn đến kế hoạch khác tùy phiên bản Neo4j. Luôn kiểm tra `EXPLAIN`/`PROFILE`, đặc biệt khi dùng label/type được xây dựng từ đầu vào lúc chạy.

## 7. Quan sát và vận hành lookup index

Khi một truy vấn theo label/type bất ngờ chậm, kiểm tra theo trình tự:

1. **Schema hiện tại:** chạy `SHOW LOOKUP INDEXES` để xem đúng hai nhóm `NODE` và `RELATIONSHIP`, cùng trạng thái của chúng.
2. **Hình dạng truy vấn:** xác định truy vấn đang chọn label/type hay lọc phần lớn theo thuộc tính; nhiều trường hợp cần range index hoặc constraint trên thuộc tính.
3. **Kế hoạch thực thi:** chạy `EXPLAIN` trước, và `PROFILE` trên truy vấn có thể thực thi an toàn để xem toán tử, DB Hits và lượng hàng.
4. **Độ chọn lọc:** label `Event` có thể chứa gần như toàn bộ dữ liệu nên dù có lookup index, duyệt rất nhiều node vẫn tốn tài nguyên.
5. **Điểm xuất phát của traversal:** nếu có khóa node đầu mút, thử thiết kế truy vấn đi từ node chọn lọc trước khi mở rộng quan hệ.
6. **Tác động ghi:** với khối lượng tạo/xóa node, thay đổi label hay tạo/xóa relationship lớn, cân nhắc chi phí duy trì index trong bài toán vận hành tổng thể.

Ví dụ một truy vấn cần cân nhắc chiến lược:

~~~cypher
MATCH (e:Event)
WHERE e.occurredAt >= datetime($fromTime)
RETURN e
ORDER BY e.occurredAt DESC
LIMIT 100;
~~~

Lookup index theo label `Event` không tự hỗ trợ lọc khoảng thời gian hay sắp xếp theo `occurredAt`. Nếu truy vấn này xuất hiện thường xuyên với số lượng event lớn, hãy đánh giá property range index:

~~~cypher
CREATE RANGE INDEX event_time_range IF NOT EXISTS
FOR (e:Event)
ON (e.occurredAt);
~~~

Sự khác biệt trong kế hoạch trước và sau khi thêm property index cần được đo bằng dữ liệu đại diện; không suy ra tốc độ chỉ từ việc DDL thành công.

## 8. Bài thực hành tự kiểm tra

**Bối cảnh:** Đồ thị quản lý trường học gồm node `Student`, `Course` và relationship `ENROLLED_IN`. Hãy dự đoán loại index nào phù hợp với từng truy vấn:

~~~cypher
// A. Lấy một nhóm sinh viên để hiển thị.
MATCH (s:Student) RETURN s LIMIT 10;

// B. Tìm sinh viên theo mã duy nhất.
MATCH (s:Student {studentId: $id}) RETURN s;

// C. Tìm các mối quan hệ ghi danh theo type.
MATCH ()-[r:ENROLLED_IN]->() RETURN r LIMIT 10;

// D. Tìm học phần theo mã.
MATCH (c:Course) WHERE c.code = $code RETURN c;
~~~

**Gợi ý giải thích:**

- **A:** node label lookup index có thể giúp tìm tập node `Student`.
- **B:** property index hoặc uniqueness constraint trên `Student.studentId` thường thích hợp hơn khi tìm theo ID.
- **C:** relationship type lookup index có thể giúp tìm các quan hệ `ENROLLED_IN` khi chưa biết node đầu mút.
- **D:** property index hoặc uniqueness constraint trên `Course.code` phù hợp nếu thường xuyên tra cứu theo mã học phần.

Để kiểm tra trên database thật, chạy `SHOW LOOKUP INDEXES`, sau đó dùng `EXPLAIN` hoặc `PROFILE` cho A–D và so sánh toán tử thực thi. Quan sát liệu planner bắt đầu từ token, property index, count store hoặc một node cụ thể rồi mở rộng quan hệ.

## 9. Checklist ghi nhớ

- Token lookup index chỉ lập chỉ mục **label của node** và **type của relationship**.
- Neo4j hiện đại thường đã tạo sẵn **một node lookup index** và **một relationship lookup index** cho database mới; kiểm tra trước khi thêm DDL.
- Cú pháp node là `ON EACH labels(n)`; cú pháp relationship là `ON EACH type(r)`.
- `SHOW LOOKUP INDEXES` giúp kiểm tra tên, đối tượng và trạng thái của index.
- `EXPLAIN` và `PROFILE` giúp hiểu cách planner thực sự truy cập dữ liệu.
- Với tìm kiếm theo **giá trị thuộc tính**, cần cân nhắc index hoặc constraint thích hợp khác.
- Lookup index giúp truy cập phần tử đồ thị; **không đảm bảo tính duy nhất** và **không thay thế tối ưu truy vấn đường đi**.

**Kết luận:** Token lookup index là lớp hỗ trợ truy cập cấu trúc cơ bản trong Neo4j: tìm node theo nhãn và relationship theo loại. Khi biết nó hoạt động ở mức **token** chứ không phải **giá trị thuộc tính**, bạn sẽ thiết kế Cypher và schema index đúng mục đích, đồng thời đọc kế hoạch thực thi có cơ sở hơn.
