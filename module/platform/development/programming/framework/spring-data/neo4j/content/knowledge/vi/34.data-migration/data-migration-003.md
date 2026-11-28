# Tạo constraint và index trước khi nạp dữ liệu lớn

Khi nạp một lượng lớn node và relationship vào Neo4j, schema cần được chuẩn bị để bảo vệ tính duy nhất của dữ liệu và giúp các truy vấn tìm node theo khóa nghiệp vụ hoạt động hiệu quả. Constraint và index có vai trò khác nhau: constraint bảo đảm quy tắc dữ liệu, còn index giúp tìm kiếm nhanh hơn. Với luồng nạp dữ liệu tăng dần dùng `MERGE`, nên tạo constraint định danh và các index cần cho bước tra cứu trước khi nạp. Với lần import ban đầu rất lớn, không có yêu cầu tra cứu trong lúc nạp, có thể tạo index phụ sau import để tăng tốc ghi. Quyết định thứ tự phải dựa trên cách nạp và yêu cầu toàn vẹn dữ liệu.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ sử dụng `Person`, `Movie` và `ACTED_IN` để thiết kế khóa nghiệp vụ, tạo uniqueness constraint, chọn range/text/full-text index và kiểm tra trạng thái schema trước khi chạy migration.

## 1. Phân biệt constraint và index

Constraint và index đều thuộc schema của Neo4j nhưng giải quyết hai vấn đề khác nhau:

| Thành phần | Mục tiêu | Ví dụ |
|---|---|---|
| Uniqueness constraint | Không cho phép hai node có cùng giá trị khóa trong phạm vi label/property | `Person.personId` phải duy nhất |
| Existence constraint | Bắt buộc node hoặc relationship có property | `Person.name` không được thiếu |
| Node key constraint | Kết hợp tồn tại và duy nhất cho một hoặc nhiều property | Cặp `(tenantId, personId)` phải có và duy nhất |
| Range index | Tăng tốc equality, range, prefix và một số truy vấn/sắp xếp theo property | Tìm `Person` theo `personId`, `born` |
| Text index | Tối ưu một số phép tìm chuỗi như `CONTAINS`, `ENDS WITH` | Tìm tên chứa một đoạn văn bản |
| Full-text index | Tìm kiếm văn bản theo analyzer và điểm liên quan | Tìm phim theo tiêu đề/mô tả |

Constraint bảo vệ dữ liệu ngay cả khi nhiều ứng dụng hoặc transaction cùng ghi vào database. Index không tự bảo đảm uniqueness hay tính hợp lệ của dữ liệu. Ngược lại, index có thể tồn tại mà không có constraint nếu chỉ cần tăng tốc truy vấn.

## 2. Xác định khóa nghiệp vụ trước khi import

Không nên dựa vào ID nội bộ do Neo4j sinh ra làm khóa liên kết từ file nguồn hoặc hệ thống bên ngoài. Hãy xác định một khóa nghiệp vụ ổn định cho từng loại node:

- `Person.personId`: ID người trong hệ thống nguồn.
- `Movie.movieId`: ID phim trong hệ thống nguồn.
- `Document.documentId`: ID tài liệu nếu cần mở rộng mô hình.

Ví dụ entity SDN:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String personId;
    private String name;
    private Integer born;
}
```

Ở ví dụ này `id` là ID nội bộ Neo4j được SDN quản lý, còn `personId` là khóa nghiệp vụ được dùng để import, đồng bộ và tra cứu từ hệ thống khác. Nếu muốn SDN dùng khóa nghiệp vụ làm ID mapping, cần thiết kế kiểu `@Id` tương ứng; dù chọn cách nào, quy tắc duy nhất ở database vẫn cần được bảo vệ bằng constraint.

Trước khi tạo constraint, hãy thống nhất quy tắc chuẩn hóa khóa: có phân biệt hoa thường không, có trim khoảng trắng không, có cho phép chuỗi rỗng không, và ID có duy nhất toàn hệ thống hay chỉ trong một tenant. Hai giá trị `P-100` và `p-100` là khác nhau trong so sánh chuỗi thông thường; nếu nghiệp vụ xem chúng là một, hãy chuẩn hóa trước khi ghi.

## 3. Kiểm tra dữ liệu hiện có trước khi tạo constraint

Tạo uniqueness constraint trên dữ liệu đã tồn tại có thể thất bại nếu có giá trị trùng. Hãy kiểm tra duplicate trước:

```cypher
MATCH (p:Person)
WHERE p.personId IS NOT NULL
WITH p.personId AS personId, count(*) AS occurrences
WHERE occurrences > 1
RETURN personId, occurrences
ORDER BY occurrences DESC, personId ASC;
```

Kiểm tra node chưa có khóa:

```cypher
MATCH (p:Person)
WHERE p.personId IS NULL OR trim(p.personId) = ''
RETURN count(p) AS peopleWithoutValidId;
```

Làm tương tự cho `Movie.movieId`:

```cypher
MATCH (m:Movie)
WHERE m.movieId IS NOT NULL
WITH m.movieId AS movieId, count(*) AS occurrences
WHERE occurrences > 1
RETURN movieId, occurrences
ORDER BY occurrences DESC, movieId ASC;
```

Uniqueness constraint chỉ kiểm tra tính duy nhất của các giá trị property tồn tại. Nó không tự bắt buộc mọi node mang label đó phải có property. Nếu `personId` bắt buộc phải có, cần kiểm tra dữ liệu thiếu và dùng thêm existence/node key constraint nếu phiên bản và edition Neo4j hỗ trợ, hoặc bảo đảm bằng validation ở luồng ghi.

Không tự động xóa duplicate theo một truy vấn chung chung. Trước khi hợp nhất, cần xác định node nào là bản ghi chuẩn, cách chuyển relationship sang node chuẩn, cách xử lý property xung đột và lịch sử audit. Chạy bước làm sạch trên bản sao hoặc staging database trước khi áp dụng vào dữ liệu chính.

## 4. Tạo uniqueness constraint cho khóa node

Với Neo4j 5, cú pháp tạo uniqueness constraint cho `Person.personId`:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Tạo constraint tương ứng cho phim:

```cypher
CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.movieId IS UNIQUE;
```

Constraint đảm bảo hai node cùng label không thể có cùng giá trị của property được chỉ định. Khi ứng dụng chạy nhiều import worker hoặc nhiều request đồng thời, database vẫn là nơi cuối cùng bảo vệ tính duy nhất.

`IF NOT EXISTS` giúp script có thể chạy lại mà không tạo một constraint trùng lặp. Nó không sửa định nghĩa constraint cũ để khớp với ý định mới. Sau khi chạy migration, vẫn cần dùng `SHOW CONSTRAINTS` để kiểm tra tên, loại constraint, label và property thực tế.

### 4.1. Constraint kết hợp nhiều property

Nếu khóa chỉ duy nhất trong phạm vi tenant, có thể dùng composite uniqueness constraint:

```cypher
CREATE CONSTRAINT person_tenant_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.personId) IS UNIQUE;
```

Khi đó, cùng một `personId` có thể xuất hiện ở tenant khác nhau, nhưng cặp `(tenantId, personId)` không được trùng. Hãy bảo đảm mọi truy vấn `MERGE` dùng đủ các property cấu thành khóa.

### 4.2. Existence và node key constraint

Nếu cần bắt buộc property tồn tại, Neo4j có existence constraint. Ví dụ:

```cypher
CREATE CONSTRAINT person_name_required IF NOT EXISTS
FOR (p:Person)
REQUIRE p.name IS NOT NULL;
```

Node key constraint kết hợp existence và uniqueness:

```cypher
CREATE CONSTRAINT person_key IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS NODE KEY;
```

Các constraint dạng existence và key phụ thuộc edition/phiên bản Neo4j; node key và property existence thường yêu cầu Enterprise. Kiểm tra ma trận tính năng của database đích trước khi đưa chúng vào migration. Nếu edition không hỗ trợ, vẫn có thể dùng uniqueness constraint cùng validation ở tầng ứng dụng hoặc bước kiểm tra dữ liệu trước import.

## 5. Constraint uniqueness có index đi kèm

Neo4j tạo backing range index cho uniqueness constraint. Vì vậy, sau khi đã tạo:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

không cần tạo thêm một range index riêng trên đúng label/property `Person.personId` chỉ để tìm theo ID. Index do constraint sở hữu vừa hỗ trợ kiểm tra uniqueness vừa hỗ trợ tra cứu.

Nếu tạo thêm index trùng schema với backing index của constraint, Neo4j có thể từ chối hoặc cảnh báo do index tương ứng đã tồn tại. Hãy kiểm tra `SHOW INDEXES` trước khi thêm index phụ.

## 6. Chọn loại index theo predicate Cypher

Không nên tạo index cho mọi property. Chọn index dựa trên các query thật sự được dùng trong import và ứng dụng:

| Kiểu truy vấn | Index nên xem xét | Ví dụ predicate |
|---|---|---|
| Tìm bằng chính xác | Range | `p.personId = $id` |
| Lọc theo khoảng | Range | `m.released >= $year` |
| Tìm danh sách giá trị | Range | `p.status IN $statuses` |
| Tìm theo tiền tố | Range | `p.name STARTS WITH $prefix` |
| Tìm chuỗi chứa/kết thúc | Text | `p.name CONTAINS $fragment` |
| Tìm kiếm toàn văn nhiều trường, có điểm liên quan | Full-text | `db.index.fulltext.queryNodes(...)` |
| Lọc theo nhiều property thường đi cùng nhau | Composite range | `p.tenantId = $tenant AND p.status = $status` |

Khả năng dùng index cụ thể còn phụ thuộc phiên bản Neo4j, biểu thức Cypher, kiểu dữ liệu và độ chọn lọc. Dùng `EXPLAIN` để xem planner có chọn index mong muốn hay không; dùng `PROFILE` trên môi trường an toàn để đo số hàng và database hits thực tế.

## 7. Tạo range index cho property dùng để lọc

Ví dụ ứng dụng thường lọc người theo năm sinh:

```cypher
CREATE RANGE INDEX person_born_idx IF NOT EXISTS
FOR (p:Person)
ON (p.born);
```

Và lọc phim theo năm phát hành:

```cypher
CREATE RANGE INDEX movie_released_idx IF NOT EXISTS
FOR (m:Movie)
ON (m.released);
```

Range index thường phù hợp với equality, range, `IN`, prefix và các truy vấn sắp xếp/đọc theo property mà planner hỗ trợ. Đừng tạo index cho `name`, `born`, `status`, `country`, `email` chỉ vì chúng tồn tại trên entity. Hãy xác định endpoint hoặc migration nào thực sự lọc theo từng property.

## 8. Composite index cho truy vấn nhiều điều kiện

Nếu truy vấn thường xuyên lọc theo tenant và trạng thái:

```cypher
MATCH (p:Person)
WHERE p.tenantId = $tenantId
  AND p.status = $status
RETURN p;
```

có thể xem xét composite range index:

```cypher
CREATE RANGE INDEX person_tenant_status_idx IF NOT EXISTS
FOR (p:Person)
ON (p.tenantId, p.status);
```

Thứ tự property trong composite index quan trọng. Hãy thiết kế theo các predicate thường dùng, đặc biệt property đầu tiên và cách query ràng buộc các property. Composite index không đồng nghĩa với việc mọi tổ hợp predicate đều được tối ưu như nhau. Dùng `EXPLAIN`/`PROFILE` với truy vấn đại diện để xác minh.

Nếu chỉ tìm theo `status` mà không có `tenantId`, composite index bắt đầu bằng `tenantId` có thể không phải lựa chọn phù hợp. Khi workload thực sự cần cả hai dạng query, cân nhắc index riêng thay vì tạo một index quá rộng.

## 9. Text index và full-text index không giống nhau

Text index phù hợp với các phép so khớp chuỗi như `CONTAINS` và `ENDS WITH` trong những trường hợp planner có thể sử dụng index:

```cypher
CREATE TEXT INDEX person_name_text_idx IF NOT EXISTS
FOR (p:Person)
ON (p.name);
```

Query:

```cypher
MATCH (p:Person)
WHERE p.name CONTAINS $fragment
RETURN p.personId AS personId, p.name AS name;
```

Full-text index phù hợp với tìm kiếm văn bản theo token/analyzer và điểm liên quan, có thể lập chỉ mục nhiều property:

```cypher
CREATE FULLTEXT INDEX movie_search IF NOT EXISTS
FOR (m:Movie)
ON EACH [m.title, m.description];
```

Truy vấn full-text qua procedure:

```cypher
CALL db.index.fulltext.queryNodes('movie_search', $searchTerm)
YIELD node, score
RETURN node AS movie, score
ORDER BY score DESC;
```

Full-text index không tự được planner dùng thay cho mọi predicate `CONTAINS`. Ứng dụng phải gọi procedure full-text tương ứng. Chọn analyzer và cách token hóa theo ngôn ngữ dữ liệu; với tiếng Việt, cần thử nghiệm cách xử lý dấu, từ ghép và tokenization trên dữ liệu thật.

Khả năng sử dụng full-text index và một số loại constraint phụ thuộc edition, phiên bản và môi trường Neo4j. Trước khi đưa lệnh DDL vào migration, hãy xác minh tính năng được hỗ trợ trên database đích; không suy ra khả năng chỉ từ việc Cypher parser chấp nhận cú pháp ở một môi trường khác.

## 10. Index cho relationship property

Trong graph có relationship chứa thuộc tính như vai diễn hoặc mã credit:

```cypher
(p:Person)-[r:ACTED_IN {creditId: 'C-001', role: 'Neo'}]->(m:Movie)
```

nếu truy vấn thường xuyên tìm theo property của relationship, có thể xem xét relationship range index (tùy phiên bản và khả năng của database):

```cypher
CREATE RANGE INDEX acting_credit_id_idx IF NOT EXISTS
FOR ()-[r:ACTED_IN]-()
ON (r.creditId);
```

Index relationship property có thể hỗ trợ truy vấn bắt đầu từ relationship type và lọc theo property. Tuy nhiên, nếu query luôn bắt đầu từ một node `Person` đã được tìm nhanh bằng `personId`, index trên `creditId` có thể không đem lại lợi ích. Hãy dựa vào query plan và số lượng relationship thực tế để quyết định.

## 11. Tạo constraint/index trước hay sau bulk import?

Không có một thứ tự tối ưu cho mọi kiểu nạp. Điểm cần cân bằng là tính toàn vẹn dữ liệu và tốc độ ghi:

| Kiểu nạp | Schema nên có trước khi nạp | Index phụ nên tạo khi nào? | Lý do |
|---|---|---|---|
| Đồng bộ tăng dần bằng `MERGE` | Uniqueness constraint trên khóa nghiệp vụ; index phục vụ lookup | Trước nếu query trong quá trình nạp cần dùng | `MERGE` tìm node theo khóa và constraint ngăn duplicate |
| Import nhiều batch bằng `LOAD CSV`/driver | Constraint nếu cần từ chối khóa trùng ngay trong lúc ghi | Trước cho các lookup lặp lại; sau cho index chỉ phục vụ đọc | Index được duy trì trên mỗi lần ghi, có chi phí |
| Full import ban đầu vào database trống, không cần query giữa chừng | Có thể chưa tạo index phụ; cần validation nguồn hoặc staging để giữ uniqueness | Thường tạo sau import để giảm chi phí duy trì index trên từng row | Index được build một lần trên tập dữ liệu đã nạp |
| Nạp dữ liệu trong khi hệ thống đang phục vụ request | Constraint bảo vệ khóa và index phục vụ query production | Lập kế hoạch trước khi import | Tránh làm chậm query trực tuyến hoặc làm mất tính duy nhất |

### 11.1. Khi nên tạo constraint trước

Tạo uniqueness constraint trước khi nạp nếu:

- Import dùng `MERGE` để tìm node theo business key.
- Có nhiều worker hoặc request ghi đồng thời.
- Không được phép tạo duplicate dù import thất bại giữa chừng.
- Các bước tiếp theo cần tra cứu node đã nạp theo khóa.
- Database đã có dữ liệu và cần xác nhận khóa hiện hữu hợp lệ trước khi tiếp tục.

Ví dụ:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;

CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.movieId IS UNIQUE;
```

Sau đó có thể dùng `MERGE` theo business key trong từng batch. Constraint giúp database từ chối dữ liệu vi phạm uniqueness thay vì để duplicate lọt qua.

### 11.2. Khi nên tạo index phụ sau full import

Trong một lần full import lớn, nếu mỗi row được ghi bằng `CREATE` hoặc công cụ import chuyên dụng và không cần truy vấn dữ liệu vừa nạp để xử lý row kế tiếp, việc duy trì nhiều index trong suốt quá trình import có thể làm giảm throughput. Khi đó có thể:

1. Kiểm tra file nguồn và tính duy nhất của khóa trước import.
2. Nạp dữ liệu theo batch hoặc công cụ full import phù hợp.
3. Tạo index phụ sau khi dữ liệu đã vào database.
4. Chờ index population hoàn tất.
5. Kiểm tra query plan trước khi mở workload production.

Nếu phải bảo đảm uniqueness trong database ngay trong quá trình import, hãy tạo uniqueness constraint trước và chấp nhận chi phí kiểm tra/index maintenance. Không đánh đổi tính toàn vẹn chỉ để tăng tốc nạp.

### 11.3. Phân biệt constraint với index phụ khi lập kế hoạch

Một uniqueness constraint có backing range index. Do đó, quyết định tạo constraint trước cũng đồng thời tạo index phục vụ lookup khóa đó. Index phụ cho `name`, `born`, `released`, `status` có thể để sau nếu không được dùng trong quá trình import.

## 12. Ví dụ luồng nạp theo batch với LOAD CSV

Giả sử có file `people.csv` với cột `personId`, `name`, `born`. Sau khi tạo uniqueness constraint, có thể import theo batch:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///people.csv' AS row
CALL {
    WITH row
    WITH row
    WHERE row.personId IS NOT NULL AND trim(row.personId) <> ''
    MERGE (p:Person {personId: trim(row.personId)})
    SET p.name = row.name,
        p.born = toInteger(row.born)
} IN TRANSACTIONS OF 1000 ROWS;
```

`IN TRANSACTIONS` chia dữ liệu thành các transaction nhỏ để tránh giữ một transaction khổng lồ. Câu lệnh này phải được chạy trong implicit transaction; không bọc nó trong transaction tường minh do driver hoặc `@Transactional` mở.

Constraint giúp bảo vệ khóa trong trường hợp file có dòng trùng hoặc nhiều tiến trình import cùng chạy. Tuy nhiên, ví dụ trên bỏ qua dòng có `personId` rỗng; trong migration thật, cần ghi nhận số dòng bị loại và báo lỗi dữ liệu nguồn thay vì âm thầm bỏ qua.

Nếu hai dòng trong CSV có cùng `personId`, `MERGE` sẽ tìm và dùng lại cùng node `Person`; uniqueness constraint không báo lỗi chỉ vì khóa xuất hiện lặp trong file. Nếu hai dòng có giá trị `name` khác nhau, lệnh `SET` có thể khiến dòng xử lý sau ghi đè giá trị trước. Vì vậy vẫn cần kiểm tra duplicate ở nguồn và định nghĩa quy tắc hợp nhất. Constraint sẽ từ chối trường hợp một thao tác tạo node mới bằng `CREATE` vi phạm uniqueness, hoặc các thao tác ghi cạnh tranh cố tạo giá trị trùng.

Nếu cần liên kết `Person` với `Movie`, hãy tạo hai node bằng khóa duy nhất trước, sau đó tạo relationship:

```cypher
LOAD CSV WITH HEADERS FROM 'file:///credits.csv' AS row
CALL {
    WITH row
    MATCH (p:Person {personId: trim(row.personId)})
    MATCH (m:Movie {movieId: trim(row.movieId)})
    MERGE (p)-[:ACTED_IN {creditId: row.creditId}]->(m)
} IN TRANSACTIONS OF 1000 ROWS;
```

Trước khi chạy, phải xác minh mỗi `personId` và `movieId` trong file credit đều tồn tại hoặc có quy trình nạp node tương ứng. Nếu `creditId` là định danh duy nhất của relationship, cần thiết kế cơ chế chống trùng cho credit theo khả năng constraint/index của phiên bản Neo4j; không giả định `MERGE` một pattern chưa đủ khóa sẽ giải quyết mọi trường hợp trùng.

## 13. Chờ index ONLINE trước khi đánh giá query

Sau khi tạo index, Neo4j có thể cần thời gian population. Kiểm tra trạng thái:

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties,
      state, populationPercent
RETURN name, type, entityType, labelsOrTypes, properties,
       state, populationPercent
ORDER BY name;
```

Index ở trạng thái `POPULATING` chưa sẵn sàng để planner sử dụng như index đã hoàn tất. Chỉ đánh giá hiệu năng sau khi index liên quan chuyển sang `ONLINE`.

Kiểm tra constraint:

```cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

Không chỉ kiểm tra rằng câu `CREATE ... IF NOT EXISTS` chạy không lỗi. Hãy xác nhận đúng constraint/index đang tồn tại trên database đích và đúng property cần dùng.

## 14. Xác minh index có được query planner sử dụng

Dùng `EXPLAIN` để xem kế hoạch mà không thực thi query:

```cypher
EXPLAIN
MATCH (p:Person {personId: $personId})
RETURN p;
```

Trong plan, tìm operator dạng `NodeUniqueIndexSeek` hoặc `NodeIndexSeek` tương ứng. Nếu planner vẫn chọn label scan, hãy kiểm tra:

- Index đã ở trạng thái `ONLINE` chưa.
- Predicate có tương thích với loại index không.
- Query có dùng đúng label và property không.
- Thống kê database có cập nhật và index có đủ chọn lọc không.
- Có chuyển đổi kiểu dữ liệu hoặc hàm bọc property khiến index không được sử dụng không.

`PROFILE` thực thi query để thu thập số liệu thực tế như rows và database hits. Không dùng `PROFILE` cho câu query ghi/xóa nguy hiểm trên production chỉ để quan sát; chạy trên dữ liệu test hoặc dùng `EXPLAIN` trước.

## 15. Quản lý schema migration có thể chạy lại

Constraint và index là schema database, không chỉ là annotation trong entity Java. SDN mapping `@Node`, `@Relationship` không tự thay thế migration tạo constraint/index trong Neo4j.

Một migration schema nên:

- Có tên rõ ràng và được quản lý phiên bản cùng code.
- Nhắm đúng database, label, relationship type và property.
- Dùng `IF NOT EXISTS` khi thao tác có thể chạy lại an toàn.
- Kiểm tra định nghĩa hiện có trước khi giả định migration đã hoàn tất.
- Không xóa rồi tạo lại index/constraint tùy tiện trên database production.
- Có bước kiểm tra duplicate và missing property trước constraint.
- Có kế hoạch rollback hoặc phục hồi dữ liệu nếu schema không thể tự đảo ngược an toàn.

Ví dụ file migration có thể chứa các câu lệnh tạo constraint và index theo từng giai đoạn. Trước khi triển khai, chạy thử trên database staging có lượng dữ liệu gần với production để đo thời gian population và tác động tới workload.

## 16. Lưu ý vận hành khi schema lớn

- Tạo index/constraint cần quyền quản lý schema phù hợp; user chỉ có quyền đọc/ghi dữ liệu có thể không được phép chạy DDL.
- Index chiếm dung lượng lưu trữ và bộ nhớ page cache; số index càng nhiều thì chi phí duy trì càng cao.
- Tạo index trên database đang phục vụ tải lớn có thể tiêu thụ CPU, I/O và tài nguyên trong giai đoạn population.
- Unique constraint cần xác minh dữ liệu hiện tại; duplicate có thể làm quá trình tạo constraint thất bại.
- `IF NOT EXISTS` không thay thế kiểm tra schema drift.
- Constraint/index thuộc database cụ thể; tạo ở database mặc định không có nghĩa database tenant khác cũng có schema đó.
- Với cluster, theo dõi trạng thái schema và index trên database đích trước khi chuyển traffic.

## 17. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tạo uniqueness constraint khi đã có duplicate | Dữ liệu hiện tại vi phạm quy tắc | Chạy query tìm duplicate, hợp nhất dữ liệu rồi tạo constraint |
| Nghĩ uniqueness constraint bắt buộc property tồn tại | Constraint duy nhất bỏ qua node không có property | Dùng existence/node key constraint nếu hỗ trợ hoặc validate khi ghi |
| Tạo index trùng với backing index của constraint | Constraint đã sở hữu range index cho property | Kiểm tra `SHOW INDEXES` và không tạo index dư thừa |
| Tạo index cho mọi property | Tăng dung lượng và chi phí ghi không cần thiết | Dựa vào workload và `PROFILE` để chọn index |
| Nạp dữ liệu `MERGE` trước khi có index khóa | Mỗi batch có thể phải tìm node tốn kém và thiếu bảo vệ uniqueness | Tạo uniqueness constraint cho business key trước |
| Tạo mọi index phụ trước full import | Mỗi lần ghi phải duy trì nhiều index | Cân nhắc tạo index phụ sau import nếu không cần lookup trong lúc nạp |
| Dùng `IF NOT EXISTS` và nghĩ schema tự được sửa | Lệnh không reconcile định nghĩa cũ | Kiểm tra schema hiện tại và viết migration thay đổi rõ ràng |
| Query vẫn scan dù index tồn tại | Index chưa ONLINE hoặc predicate không phù hợp | Kiểm tra trạng thái và `EXPLAIN` |
| Dùng full-text index nhưng query `CONTAINS` trực tiếp | Full-text index được truy vấn qua procedure | Gọi `db.index.fulltext.queryNodes` |
| Bọc `LOAD CSV ... IN TRANSACTIONS` trong transaction ngoài | Subquery transactional cần implicit transaction | Chạy câu import như implicit transaction |
| Import bỏ qua dòng thiếu ID mà không báo | Dữ liệu nguồn không đầy đủ nhưng migration vẫn báo thành công | Đếm và xuất lỗi dòng bị loại, xử lý trước khi cutover |

## 18. Checklist trước khi nạp dữ liệu lớn

- Chốt khóa nghiệp vụ ổn định cho từng label.
- Chuẩn hóa cách viết và so sánh khóa trước khi import.
- Kiểm tra duplicate và missing key trong dữ liệu hiện có/nguồn.
- Quyết định constraint nào phải bảo vệ ngay trong lúc import.
- Tạo uniqueness constraint trước nếu dùng `MERGE` hoặc có ghi đồng thời theo khóa.
- Nhớ constraint uniqueness đã có backing range index.
- Chỉ tạo index phụ trước import nếu bước nạp hoặc workload trực tuyến cần dùng chúng.
- Cân nhắc tạo index phụ sau full import để giảm chi phí ghi.
- Chọn range, text, full-text hoặc composite index theo predicate thực tế.
- Xác minh edition/phiên bản Neo4j hỗ trợ loại constraint/index cần dùng.
- Chạy migration trên đúng database và kiểm tra `SHOW CONSTRAINTS`, `SHOW INDEXES`.
- Chờ index `ONLINE` trước khi đánh giá query plan.
- Dùng `EXPLAIN`/`PROFILE` với dữ liệu đại diện và query an toàn.
- Import theo batch, ghi nhận dòng lỗi và có thể chạy lại có kiểm soát.
- Kiểm tra uniqueness và relationship sau import.

## 19. Bài tập thực hành

1. Tạo uniqueness constraint cho `Person.personId` và `Movie.movieId`.
2. Viết query tìm duplicate và node thiếu `personId` trước khi tạo constraint.
3. Tạo composite uniqueness constraint cho `(tenantId, personId)` và viết `MERGE` dùng đủ hai property.
4. Tạo range index cho `Movie.released` và dùng `EXPLAIN` xác nhận truy vấn lọc theo năm.
5. Tạo text index cho `Person.name` và kiểm tra query `CONTAINS` có dùng index phù hợp.
6. Tạo full-text index cho `Movie.title` và `Movie.description`; truy vấn qua `db.index.fulltext.queryNodes`.
7. Tạo composite index cho `(tenantId, status)` và so sánh query plan khi lọc đủ hai property với khi chỉ lọc `status`.
8. Nạp file `people.csv` theo batch bằng `LOAD CSV ... IN TRANSACTIONS`; thử ID trùng với `MERGE` để quan sát hai dòng dùng cùng node và thử `CREATE` để xác nhận uniqueness constraint từ chối node trùng.
9. Chạy full import trên database thử nghiệm với index phụ được tạo trước và sau import; so sánh thời gian nạp và thời gian population.
10. Dùng `SHOW INDEXES` để theo dõi `POPULATING` tới `ONLINE`.
11. Viết migration idempotent bằng `IF NOT EXISTS`, sau đó kiểm tra schema bằng `SHOW CONSTRAINTS` và `SHOW INDEXES`.
12. Chạy `PROFILE` cho truy vấn đọc theo khóa nghiệp vụ và giải thích operator cùng database hits.

Khi hoàn thành, bạn cần biết constraint bảo vệ quy tắc dữ liệu còn index phục vụ truy vấn; uniqueness constraint còn cung cấp backing range index. Hãy tạo constraint trước khi nạp nếu cần bảo vệ khóa và hỗ trợ `MERGE`, nhưng cân nhắc để index phụ sau full import khi ưu tiên tốc độ ghi. Mọi quyết định nên được xác minh bằng trạng thái schema và query plan trên dữ liệu gần với production.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Indexes for search performance](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/)
- [Neo4j Cypher Manual — SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/list-indexes/)
- [Neo4j Cypher Manual — LOAD CSV](https://neo4j.com/docs/cypher-manual/current/clauses/load-csv/)
- [Neo4j Operations Manual — Import data](https://neo4j.com/docs/operations-manual/current/import/)
- [Spring Data Neo4j — Schema and indexes FAQ](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
