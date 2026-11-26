# Phân biệt chỉ mục với ràng buộc và chỉ mục phục vụ ràng buộc

## 1. Bối cảnh: cùng có “index”, nhưng hai mục đích khác nhau

Neo4j lưu dữ liệu theo **property graph** gồm node, relationship, label, relationship type và property. Khi làm việc với đồ thị lớn, hai nhu cầu thường đi cùng nhau:

- **Tìm nhanh:** tra cứu một `Book` theo `isbn`, tìm những `Customer` có `email` nhất định, hoặc duyệt node theo label.
- **Giữ dữ liệu đúng:** không cho hai cuốn sách có cùng `isbn`, yêu cầu một mã phải tồn tại, hoặc bảo đảm kiểu dữ liệu của thuộc tính.

**Index (chỉ mục)** chủ yếu tạo đường truy cập để truy vấn tìm dữ liệu hiệu quả hơn. **Constraint (ràng buộc)** định nghĩa quy tắc hợp lệ mà Neo4j kiểm tra khi tạo hoặc thay đổi dữ liệu. Một số constraint cần **index do chính constraint sở hữu** để kiểm tra quy tắc nhanh chóng. Vì thế, thấy một index trong `SHOW INDEXES` chưa đủ để kết luận nó do người vận hành tạo độc lập hay được tạo bởi constraint.

Bài này thuộc chương **Chỉ mục tra cứu** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`; tập trung vào mối quan hệ giữa lookup index, các index trên property và schema constraint. Ví dụ dùng cú pháp `CREATE … INDEX`, `CREATE CONSTRAINT … FOR … REQUIRE` của Neo4j 5 trở lên. Với bản Neo4j cũ hơn, cần kiểm tra phiên bản vì cú pháp quản lý schema có thể khác.

**Kết quả mong đợi:** sau bài học, bạn xác định được index nào là index độc lập, index nào thuộc về constraint, constraint nào không có index kèm theo; tự kiểm tra bằng `SHOW INDEXES` và `SHOW CONSTRAINTS`; đồng thời lựa chọn đúng giữa yêu cầu hiệu năng và yêu cầu toàn vẹn dữ liệu.

## 2. Ba khái niệm cần phân biệt

| Đối tượng | Chức năng chính | Tạo bằng | Khi dữ liệu vi phạm quy tắc? | Ai quản lý vòng đời? |
|---|---|---|---|---|
| **Index độc lập trên property** | Cung cấp đường truy cập nhanh cho các điều kiện lọc/truy vấn phù hợp | `CREATE RANGE/TEXT/POINT INDEX`, v.v. | Không tự chặn giá trị trùng, thiếu hay sai kiểu | Quản trị viên tạo/xóa bằng `CREATE INDEX` / `DROP INDEX` |
| **Token lookup index** | Tra cứu node theo **label** hoặc relationship theo **type** | Thường có sẵn khi tạo database; có thể tạo lại bằng `CREATE LOOKUP INDEX` | Không áp quy tắc unique, existence hay type cho property | Database duy trì; không nên xóa tùy tiện |
| **Constraint** | Bắt buộc dữ liệu tuân thủ quy tắc nghiệp vụ | `CREATE CONSTRAINT` | Lệnh ghi vi phạm bị từ chối | Quản trị viên tạo/xóa bằng `CREATE CONSTRAINT` / `DROP CONSTRAINT` |
| **Backing index (index phục vụ constraint)** | Hỗ trợ kiểm tra `UNIQUE`/`KEY` và có thể giúp truy vấn property | Được Neo4j tạo **tự động cùng constraint** | Chính **constraint** quyết định lệnh ghi có hợp lệ hay không | Gắn với constraint; xóa constraint sẽ xóa backing index |

> **Chú ý thuật ngữ:** “lookup index” theo nghĩa chính thức của Neo4j là **token lookup index** (chỉ mục cho nhãn/loại quan hệ). “Backing index” là **chỉ mục thuộc sở hữu của ràng buộc**. Hai tên gọi không đồng nghĩa, dù cả hai đều là index.

Có thể hình dung các mối liên hệ:

~~~mermaid
flowchart TD
    A["Truy vấn Cypher"] --> B["Bộ lập kế hoạch truy vấn"]
    B --> C["Lookup index: label/type"]
    B --> D["Index trên property: RANGE/TEXT/POINT"]
    B --> E["Backing RANGE index"]
    F["Lệnh ghi CREATE/SET/MERGE"] --> G["Constraint UNIQUE/KEY"]
    G --> E
    G --> H["Chấp nhận hoặc từ chối dữ liệu"]
~~~

Bộ lập kế hoạch của Neo4j **có thể** dùng index phù hợp để đọc dữ liệu; việc index tồn tại không bảo đảm mọi truy vấn sẽ dùng index đó. Ngược lại, ràng buộc được thực thi khi dữ liệu bị thay đổi, bất kể kế hoạch truy vấn đọc cụ thể.

## 3. Lookup index: tra cứu label và relationship type

Một database Neo4j mới thường có sẵn **hai token lookup index**: một cho label của node và một cho type của relationship. Kiểm tra bằng:

~~~cypher
SHOW LOOKUP INDEXES;
~~~

Nếu phiên bản hoặc công cụ quản trị dùng danh sách index chung, có thể xem bằng:

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, owningConstraint
WHERE type = 'LOOKUP'
RETURN name, type, entityType, owningConstraint
ORDER BY entityType;
~~~

Bạn thường thấy một dòng `entityType = 'NODE'` và một dòng `entityType = 'RELATIONSHIP'`; `type = 'LOOKUP'`, còn `owningConstraint` là `null`. Tên index có thể do hệ thống tạo tự động, vì vậy không nên kiểm tra dựa vào một tên cố định.

Hai ví dụ truy vấn được token lookup index hỗ trợ về điều kiện nhãn hoặc loại quan hệ:

~~~cypher
MATCH (b:Book)
RETURN count(b) AS soSach;
~~~

~~~cypher
MATCH ()-[r:BOUGHT]->()
RETURN count(r) AS soQuanHeMua;
~~~

Lookup index **không chứa cặp property–value** để giải quyết trực tiếp điều kiện như `b.isbn = 'B-001'`. Để tra cứu property hiệu quả, cần xem các loại index trên property, chẳng hạn `RANGE`, hoặc backing index tự sinh từ `UNIQUE`/`KEY`.

Khi thật sự cần tạo lại lookup index từng bị xóa, cú pháp tham khảo là:

~~~cypher
CREATE LOOKUP INDEX idx_labels IF NOT EXISTS
FOR (n) ON EACH labels(n);
~~~

~~~cypher
CREATE LOOKUP INDEX idx_rel_types IF NOT EXISTS
FOR ()-[r]-() ON EACH type(r);
~~~

**Không chạy hai lệnh trên như bước thiết lập bắt buộc.** Neo4j chỉ cho phép một lookup index cho label node và một cho type relationship tại một thời điểm; mặc định chúng đã tồn tại. Xóa lookup index có thể làm nhiều truy vấn suy giảm hiệu năng.

## 4. Index trên property: tăng tốc tìm kiếm, không áp tính duy nhất

Xét hệ thống thư viện có node `(:Book {isbn, title})`. Nếu cần tìm sách theo `title`, có thể tạo một **RANGE index độc lập**:

~~~cypher
CREATE RANGE INDEX qa002_book_title IF NOT EXISTS
FOR (b:QA002Book) ON (b.title);
~~~

Lệnh này tạo index chứa các giá trị `title` của node có label `QA002Book`. Khi một truy vấn phù hợp lọc theo `title`, bộ lập kế hoạch có thể chọn index này làm đường truy cập.

Index **không ngăn** hai node có cùng `title`, cũng **không buộc** mọi node phải có `title`. Đây là điểm khác biệt căn bản với constraint.

Các loại performance index trên property thường gặp:

| Loại | Phù hợp với | Điều cần nhớ |
|---|---|---|
| `RANGE` | Bằng nhau, so sánh khoảng, nhiều trường hợp lọc và sắp xếp property | Là loại index thường dùng và là loại backing index của `UNIQUE`/`KEY` |
| `TEXT` | Một số điều kiện trên chuỗi, nổi bật là `CONTAINS`, `ENDS WITH` | Không phải constraint bảo đảm chuỗi hợp lệ |
| `POINT` | Tìm theo tọa độ/khoảng cách hoặc vùng không gian | Không ràng buộc tính hợp lệ nghiệp vụ của địa điểm |
| `LOOKUP` | Chỉ label node / type relationship | Không giải quyết điều kiện lọc giá trị property |

Ngoài ra, Neo4j có full-text và vector index phục vụ tìm kiếm theo mức độ phù hợp; đây cũng **không phải** ràng buộc toàn vẹn dữ liệu. Bài này tập trung vào các index hiệu năng và index do constraint sở hữu.

## 5. UNIQUE constraint: tự sinh RANGE index phục vụ ràng buộc

Nếu nghiệp vụ yêu cầu **không có hai node `QA002Book` cùng giá trị `isbn`**, hãy tạo constraint:

~~~cypher
CREATE CONSTRAINT qa002_book_isbn_unique IF NOT EXISTS
FOR (b:QA002Book)
REQUIRE b.isbn IS UNIQUE;
~~~

Neo4j thực hiện **cả hai việc**:

1. Đăng ký quy tắc rằng các giá trị `isbn` đã tồn tại ở node `QA002Book` không được trùng nhau.
2. Tạo tự động một **RANGE backing index** cho cặp label–property `(:QA002Book {isbn})`. Index này có tên trùng với constraint trong cú pháp quản lý schema hiện hành.

Index phục vụ việc phát hiện vi phạm nhanh hơn và cũng có thể được bộ lập kế hoạch dùng để tra cứu `isbn`. Tuy vậy, **chỉ constraint mới thể hiện cam kết toàn vẹn dữ liệu**. Tạo một index RANGE độc lập trên `isbn` không mang lại quy tắc không trùng.

### UNIQUE không đồng nghĩa với bắt buộc có property

`IS UNIQUE` chỉ so sánh các node **có giá trị property tương ứng**. Với constraint trên `isbn`:

- `(:QA002Book {isbn: 'B-001'})` và `(:QA002Book {isbn: 'B-002'})` cùng tồn tại hợp lệ.
- Thêm `(:QA002Book {isbn: 'B-001'})` thứ hai bị từ chối do trùng.
- Một node `(:QA002Book {title: 'Bản thảo'})` **thiếu `isbn` vẫn hợp lệ** dưới riêng constraint `IS UNIQUE`.

Muốn yêu cầu property phải tồn tại, phải bổ sung **property existence constraint** hoặc dùng **key constraint** thích hợp (xem mục 7). Đừng hiểu tên “unique” thành “khóa chính bắt buộc” như một số hệ quản trị quan hệ.

## 6. Thực hành: nhìn thấy index độc lập và backing index

Ví dụ dùng label `QA002Book` và tên schema bắt đầu bằng `qa002_` để tách biệt khỏi dữ liệu khác. **Chạy trên database thực hành**, không dùng database sản xuất. Thực hiện từng câu lệnh Cypher riêng.

### Bước 1 — Đưa fixture về trạng thái ban đầu

Nếu đã thực hành bài này trước đó, xóa các đối tượng thử nghiệm theo thứ tự:

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa002_book_title IF EXISTS;
~~~

~~~cypher
MATCH (b:QA002Book)
DETACH DELETE b;
~~~

Các lệnh chỉ nhắm đến tên constraint, index và label của bài học; vẫn cần bảo đảm không có dữ liệu thực sử dụng các tên đó trong database của bạn.

### Bước 2 — Tạo dữ liệu chuẩn

~~~cypher
CREATE
  (:QA002Book {isbn: 'B-001', title: 'Đồ thị căn bản'}),
  (:QA002Book {isbn: 'B-002', title: 'Cypher nâng cao'}),
  (:QA002Book {title: 'Bản thảo'});
~~~

Bộ dữ liệu có **3 node**: hai node có `isbn` khác nhau và một node chưa có `isbn`.

~~~cypher
MATCH (b:QA002Book)
RETURN count(b) AS totalBooks,
       count(b.isbn) AS booksWithIsbn;
~~~

Kết quả mong đợi: `totalBooks = 3` và `booksWithIsbn = 2`.

### Bước 3 — Tạo hai đối tượng schema

Tạo index độc lập cho `title`:

~~~cypher
CREATE RANGE INDEX qa002_book_title IF NOT EXISTS
FOR (b:QA002Book) ON (b.title);
~~~

Tạo constraint duy nhất cho `isbn` (sẽ tự tạo backing index):

~~~cypher
CREATE CONSTRAINT qa002_book_isbn_unique IF NOT EXISTS
FOR (b:QA002Book)
REQUIRE b.isbn IS UNIQUE;
~~~

Cả hai lệnh đều hợp lệ trên ba node hiện tại. Vì constraint chỉ kiểm tra giá trị `isbn` đã có, node `Bản thảo` không gây lỗi.

### Bước 4 — Quan sát quyền sở hữu trong SHOW INDEXES

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes,
      properties, owningConstraint, state
WHERE name IN ['qa002_book_title', 'qa002_book_isbn_unique']
RETURN name, type, entityType, labelsOrTypes,
       properties, owningConstraint, state
ORDER BY name;
~~~

Đáp án phần định danh và sở hữu (trạng thái `state` có thể tạm thời là `POPULATING` trước khi trở thành `ONLINE`):

| name | type | entityType | labelsOrTypes | properties | owningConstraint |
|---|---|---|---|---|---|
| `qa002_book_isbn_unique` | `RANGE` | `NODE` | `['QA002Book']` | `['isbn']` | `qa002_book_isbn_unique` |
| `qa002_book_title` | `RANGE` | `NODE` | `['QA002Book']` | `['title']` | `null` |

Diễn giải:

- Cả hai đều là `RANGE` index, nhưng chỉ index trên `isbn` có `owningConstraint` khác `null`.
- Index trên `title` là **độc lập**. Nó không được constraint nào sở hữu.
- Index trên `isbn` thuộc constraint có cùng tên. Bạn quản lý vòng đời của nó thông qua constraint.

Có thể lọc nhanh **tất cả các index phục vụ constraint** trong database bằng:

~~~cypher
SHOW INDEXES
YIELD name, type, owningConstraint
WHERE owningConstraint IS NOT NULL
RETURN name, type, owningConstraint
ORDER BY name;
~~~

Đây là cách dựa vào metadata chính thức, phù hợp hơn việc suy luận từ tên index.

### Bước 5 — Xác nhận từ phía constraint

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties, ownedIndex
WHERE name = 'qa002_book_isbn_unique'
RETURN name, type, labelsOrTypes, properties, ownedIndex;
~~~

Kết quả mong đợi:

| name | type | labelsOrTypes | properties | ownedIndex |
|---|---|---|---|---|
| `qa002_book_isbn_unique` | `NODE_PROPERTY_UNIQUENESS` | `['QA002Book']` | `['isbn']` | `qa002_book_isbn_unique` |

So sánh hai góc nhìn:

- `SHOW INDEXES` cho biết **index này thuộc constraint nào** qua `owningConstraint`.
- `SHOW CONSTRAINTS` cho biết **constraint này sở hữu index nào** qua `ownedIndex`.

### Bước 6 — Thử đọc và kiểm chứng việc chặn dữ liệu trùng

Truy vấn đọc:

~~~cypher
MATCH (b:QA002Book)
WHERE b.isbn = 'B-001'
RETURN b.isbn AS isbn, b.title AS title;
~~~

Đáp án: đúng một node có `isbn = 'B-001'` và `title = 'Đồ thị căn bản'`.

Có thể xem kế hoạch thực thi bằng cách thêm `EXPLAIN` hoặc `PROFILE`:

~~~cypher
EXPLAIN
MATCH (b:QA002Book)
WHERE b.isbn = 'B-001'
RETURN b.title;
~~~

Khi backing index `ONLINE`, bộ lập kế hoạch có thể sử dụng đường truy cập index thích hợp (ví dụ thao tác seek trên index duy nhất). Tên toán tử và quyết định chọn index có thể khác theo phiên bản, thống kê và câu truy vấn; không nên xem một toán tử cố định là tiêu chí đánh giá tính đúng đắn của constraint.

**Thử cố ý vi phạm** (lệnh dưới đây được kỳ vọng **thất bại**):

~~~cypher
CREATE (:QA002Book {isbn: 'B-001', title: 'Bản sao không hợp lệ'});
~~~

Neo4j từ chối tạo node vì giá trị `isbn` trùng với node hiện có. Số node vẫn là **3**.

Nếu thay bằng node chỉ có `title` mà không có `isbn`, riêng constraint `IS UNIQUE` không ngăn việc tạo node đó. Đây là lý do cần phân biệt tính duy nhất và tính bắt buộc tồn tại.

## 7. Constraint nào có backing index, constraint nào không?

Không phải mọi constraint đều sinh index. Trong schema constraint thông dụng của Neo4j:

| Loại constraint | Quy tắc bảo đảm | Có RANGE backing index? | Ghi chú |
|---|---|---|---|
| **Property uniqueness**: `IS UNIQUE` | Các giá trị property/tổ hợp property đã có phải khác nhau | **Có** | Property thiếu vẫn có thể được chấp nhận |
| **Key constraint**: `IS NODE KEY` hoặc `IS RELATIONSHIP KEY` | Property/tổ hợp property **phải tồn tại** và **duy nhất** | **Có** | Cần Neo4j Enterprise Edition |
| **Property existence**: `IS NOT NULL` | Property phải tồn tại | **Không** | Cần Enterprise Edition |
| **Property type** | Giá trị phải có kiểu được khai báo | **Không** | Cần Enterprise Edition |

**Ví dụ key constraint** trên một label riêng, tránh xung đột với `UNIQUE` của fixture:

~~~cypher
// Neo4j Enterprise Edition: ví dụ minh họa, không cần chạy cho fixture trên.
CREATE CONSTRAINT qa002_tenant_book_key IF NOT EXISTS
FOR (b:QA002TenantBook)
REQUIRE (b.tenantId, b.isbn) IS NODE KEY;
~~~

Ở đây, mỗi `QA002TenantBook` phải có **cả** `tenantId` và `isbn`, đồng thời **cặp giá trị** phải duy nhất. Một giá trị `isbn` có thể lặp ở các tenant khác nhau, miễn là cặp `(tenantId, isbn)` khác nhau. Constraint tạo backing **composite RANGE index** trên hai property.

**Ví dụ property existence constraint** (cũng thuộc Enterprise Edition):

~~~cypher
// Ví dụ minh họa trên label khác để không ảnh hưởng fixture QA002Book.
CREATE CONSTRAINT qa002_required_isbn IF NOT EXISTS
FOR (b:QA002RequiredBook)
REQUIRE b.isbn IS NOT NULL;
~~~

Constraint này bảo đảm `isbn` hiện diện nhưng **không** tự kiểm tra giá trị có trùng hay không, và **không** tạo backing index. Nếu chạy `SHOW CONSTRAINTS`, cột `ownedIndex` của constraint loại existence sẽ là `null`.

Lưu ý: nếu áp `IS NOT NULL` trực tiếp cho `QA002Book` trong fixture mục 6, thao tác tạo constraint sẽ thất bại do node `Bản thảo` thiếu `isbn`. Neo4j phải kiểm tra dữ liệu đã tồn tại trước khi kích hoạt constraint mới.

### Còn quan hệ relationship thì sao?

Neo4j cũng hỗ trợ property uniqueness và các constraint thích hợp trên relationship. Ví dụ cú pháp:

~~~cypher
CREATE CONSTRAINT qa002_transfer_external_id_unique IF NOT EXISTS
FOR ()-[r:QA002_TRANSFER]-()
REQUIRE r.externalId IS UNIQUE;
~~~

Constraint này tạo backing RANGE index cho property `externalId` trên relationship type `QA002_TRANSFER`, tương tự cơ chế của node uniqueness. Hỗ trợ relationship uniqueness có từ Neo4j 5.7; khi làm việc với phiên bản cũ hơn cần kiểm tra khả năng hỗ trợ.

## 8. Vòng đời: xóa index thường khác xóa backing index

Một điểm dễ gây lỗi khi bảo trì hệ thống:

- Với **index độc lập**, xóa trực tiếp bằng `DROP INDEX ten_index`. Constraint khác không bị xóa theo.
- Với **backing index**, index đang thuộc sở hữu của constraint nên không thể xóa riêng như một index độc lập. Muốn bỏ constraint, dùng `DROP CONSTRAINT ten_constraint`; khi đó Neo4j cũng **xóa backing index**.
- Nếu ứng dụng vẫn cần tra cứu property sau khi bỏ constraint, quản trị viên phải **chủ động tạo index độc lập** phù hợp. Việc bỏ constraint cũng làm mất kiểm tra tính duy nhất/key tương ứng.

Ví dụ lệnh sau **không phải cách hợp lệ** để xóa index đang phục vụ constraint:

~~~cypher
// Được kỳ vọng bị từ chối: index do constraint sở hữu.
DROP INDEX qa002_book_isbn_unique;
~~~

Còn lệnh dưới đây bỏ chính constraint (chỉ chạy ở bước dọn dữ liệu):

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique;
~~~

Khi bỏ constraint `qa002_book_isbn_unique`, backing index cùng tên cũng biến mất khỏi `SHOW INDEXES`. Trong khi đó index độc lập `qa002_book_title` vẫn tồn tại cho đến khi được xóa riêng.

**Không nên tạo thêm RANGE index độc lập với cùng label/type và cùng danh sách property khi backing RANGE index đã tồn tại.** Neo4j ngăn tạo index tương đương trên cùng schema. Nếu dùng `IF NOT EXISTS`, việc tạo index có thể không có tác dụng và trả thông báo tùy kiểu xung đột; nó không biến backing index thành một index độc lập.

## 9. Cách chọn thiết kế cho một yêu cầu nghiệp vụ

| Nhu cầu | Giải pháp phù hợp | Lý do |
|---|---|---|
| Chỉ tìm sách nhanh theo `title`, cho phép trùng tên | Index trên `title` (ví dụ RANGE/TEXT tùy điều kiện lọc) | Hiệu năng tìm kiếm, không ép dữ liệu duy nhất |
| Mỗi sách có `isbn` khác nhau, nhưng bản thảo có thể chưa có mã | `IS UNIQUE` trên `isbn` | Ràng buộc không trùng; backing index được tạo tự động |
| Mỗi sách bắt buộc có `isbn` và không được trùng | `IS NODE KEY`, hoặc cân nhắc kết hợp uniqueness + existence theo edition/thiết kế | Đảm bảo đồng thời tồn tại và duy nhất |
| Mọi đơn hàng phải có `createdAt` nhưng thời điểm có thể trùng | Property existence constraint (Enterprise Edition) | Không cần uniqueness; constraint này không sinh backing index |
| Lọc nhiều node theo label, duyệt relationship theo type | Token lookup index mặc định | Hỗ trợ chọn tập node/relationship theo token |
| Truy vấn theo `customerId` đã có uniqueness constraint | Kiểm tra backing RANGE index đang `ONLINE` trước khi thêm index cùng schema | Tránh tạo index thừa hoặc xung đột |
| Xóa uniqueness nhưng vẫn cần lọc nhanh theo `isbn` | Xóa constraint theo kế hoạch, sau đó tạo RANGE index độc lập thích hợp | Index phục vụ constraint không còn sau khi constraint bị xóa |

**Nguyên tắc:** chọn **constraint vì quy tắc dữ liệu**, chọn **index độc lập vì mẫu truy vấn**. Backing index là kết quả kỹ thuật đi kèm một số constraint, không thay thế vai trò của constraint.

## 10. Những hiểu lầm thường gặp và cách kiểm chứng

**Hiểu lầm 1: “Đã tạo index nên dữ liệu không thể trùng.”**

Sai. Tạo một `RANGE INDEX` chỉ chuẩn bị đường truy cập nhanh. Để chặn trùng giá trị trong cùng label/type, cần constraint `IS UNIQUE` hoặc `KEY` phù hợp.

**Hiểu lầm 2: “SHOW INDEXES thấy RANGE index nghĩa là người quản trị tạo riêng.”**

Sai. Backing index của `UNIQUE` và `KEY` cũng là `RANGE`. Kiểm tra `owningConstraint`, rồi đối chiếu `ownedIndex` của `SHOW CONSTRAINTS`.

**Hiểu lầm 3: “UNIQUE tự đảm bảo trường bắt buộc.”**

Sai. `UNIQUE` có thể cho phép node/relationship thiếu property được ràng buộc. Kết hợp quy tắc tồn tại hoặc dùng key constraint khi nghiệp vụ yêu cầu.

**Hiểu lầm 4: “Mọi constraint đều tạo index.”**

Sai. Property existence và property type constraint không tạo RANGE backing index. Vì vậy, `ownedIndex = null` có thể hoàn toàn bình thường.

**Hiểu lầm 5: “Có thể xóa index phía sau constraint để giảm dung lượng mà vẫn giữ constraint.”**

Sai. Backing index gắn với constraint. Xóa constraint sẽ xóa backing index và đồng thời bỏ quy tắc toàn vẹn dữ liệu. Phải đánh giá hậu quả với dữ liệu và truy vấn trước khi thay đổi schema.

**Hiểu lầm 6: “Index đã có thì EXPLAIN chắc chắn hiển thị IndexSeek.”**

Không đúng trong mọi trường hợp. Bộ lập kế hoạch chọn chiến lược dựa trên câu truy vấn và dữ liệu. Để kiểm chứng schema, xem `SHOW INDEXES`, `SHOW CONSTRAINTS` và trạng thái `ONLINE`; để đánh giá hiệu năng, xem `EXPLAIN` / `PROFILE` với dữ liệu đại diện.

## 11. Bài tập tự kiểm tra

1. **Phân loại:** `SHOW INDEXES` hiển thị hai RANGE index cho `(:Customer {email})` và `(:Customer {city})`; cột `owningConstraint` lần lượt là `customer_email_unique` và `null`. Hỏi index nào gắn với quy tắc dữ liệu?  
   **Đáp án:** index trên `email` thuộc constraint `customer_email_unique`; index trên `city` độc lập, không tự đảm bảo tính hợp lệ của `city`.

2. **Dự đoán:** trên fixture mục 6, chạy `CREATE (:QA002Book {isbn: 'B-001'})` và sau đó đếm số sách. Kết quả?  
   **Đáp án:** lệnh `CREATE` bị từ chối vì trùng `isbn`; số node `QA002Book` giữ nguyên bằng **3**.

3. **Phân biệt unique và key:** yêu cầu “mọi node `Customer` phải có `customerId` và không được có hai node trùng mã”. Chỉ `IS UNIQUE` có đủ không?  
   **Đáp án:** không; cần kiểm tra **cả tồn tại lẫn duy nhất**, ví dụ `IS NODE KEY` trong Enterprise Edition hoặc hai loại constraint phù hợp.

4. **Tác động DROP:** nếu xóa constraint `qa002_book_isbn_unique`, điều gì xảy ra với index cùng tên và index `qa002_book_title`?  
   **Đáp án:** backing index cùng tên bị xóa theo constraint; index độc lập `qa002_book_title` vẫn tồn tại.

5. **Tự viết lệnh:** hiển thị tên, loại và constraint sở hữu của mọi index phục vụ constraint.  
   **Gợi ý:** dùng `SHOW INDEXES YIELD name, type, owningConstraint WHERE owningConstraint IS NOT NULL RETURN ...`.

## 12. Dọn bài thực hành

Nếu chưa xóa constraint ở mục 8, chạy các câu lệnh riêng biệt:

~~~cypher
DROP CONSTRAINT qa002_book_isbn_unique IF EXISTS;
~~~

~~~cypher
DROP INDEX qa002_book_title IF EXISTS;
~~~

~~~cypher
MATCH (b:QA002Book)
DETACH DELETE b;
~~~

Sau đó kiểm tra:

~~~cypher
SHOW INDEXES
YIELD name
WHERE name IN ['qa002_book_title', 'qa002_book_isbn_unique']
RETURN name;
~~~

Kết quả mong đợi là **0 dòng** cho hai tên thử nghiệm. Hai token lookup index mặc định của database không bị tác động.

## 13. Tài liệu tra cứu chính thức

- [Neo4j — Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/): phân loại RANGE, TEXT, POINT, LOOKUP và cách planner sử dụng.
- [Neo4j — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/): cú pháp tạo index, hỗ trợ tra cứu label/type, xử lý xung đột với constraint.
- [Neo4j — Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/): đặc biệt mục *Constraints and backing indexes*.
- [Neo4j — Show indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/) và [Show constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/): các cột `owningConstraint`, `ownedIndex` và trạng thái index.

Khi vận hành Neo4j thực tế, luôn lưu lại định nghĩa schema và kiểm tra edition/phiên bản trước khi dùng constraint mới. Sự khác biệt nền tảng cần ghi nhớ: **index giúp tìm; constraint bảo đảm tính đúng; backing index là index Neo4j tạo và quản lý để hỗ trợ constraint duy nhất hoặc khóa**.
