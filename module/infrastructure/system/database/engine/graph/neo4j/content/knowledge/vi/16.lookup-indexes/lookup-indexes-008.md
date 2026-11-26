# Tạo, xem trạng thái, chờ sẵn sàng và xóa chỉ mục tra cứu trong Neo4j

## 1. Chỉ mục tra cứu dùng để làm gì?

Trong **property graph** của Neo4j, mỗi node có thể mang một hoặc nhiều *label* và mỗi relationship có một *type*. Khi truy vấn Cypher tìm node theo label hoặc relationship theo type, hệ thống có thể sử dụng **lookup index** để xác định những phần tử có token phù hợp.

Hai loại lookup index chính:

| Phạm vi | Thành phần được tra cứu | Truy vấn thường gặp | Cú pháp khai báo chỉ mục |
| --- | --- | --- | --- |
| Node | Các label gắn với node, như `:Person`, `:Order` | `MATCH (p:Person) RETURN p` | `FOR (n) ON EACH labels(n)` |
| Relationship | Loại quan hệ, như `:FOLLOWS`, `:PURCHASED` | `MATCH ()-[r:PURCHASED]->() RETURN r` | `FOR ()-[r]-() ON EACH type(r)` |

Lookup index còn được gọi là **token lookup index**. Mỗi lookup index cho node bao phủ **các label của toàn bộ node trong database**, còn mỗi lookup index cho relationship bao phủ **các type của toàn bộ relationship**. Vì thế, không tạo một lookup index riêng cho `:Person` rồi thêm một lookup index riêng cho `:Order`.

Điểm cần phân biệt:

- Lookup index tìm theo **label** hoặc **relationship type**; không phải index cho property như `email`, `name`, `createdAt`.
- Để lọc theo `p.email = $email` hoặc so sánh phạm vi ngày tháng, cần cân nhắc *range index* hoặc constraint hỗ trợ property, tùy truy vấn.
- Một lookup index ở trạng thái `ONLINE` có thể được query planner lựa chọn; việc chỉ mục tồn tại **không bảo đảm mọi truy vấn đều dùng nó**. Muốn biết kế hoạch thực tế, dùng `EXPLAIN` hoặc `PROFILE`.

Ví dụ graph gồm các node `(:Person {id: 1})`, `(:Product {id: 20})` và quan hệ `[:BOUGHT]`. Lookup index cho node giúp tìm các node mang `:Person` hoặc `:Product`; lookup index cho relationship giúp tìm quan hệ `:BOUGHT`. Nó không trực tiếp tối ưu điều kiện `p.id = 1`.

## 2. Kiểm tra trước khi tạo: rất có thể index đã tồn tại

Trong nhiều phiên bản/cấu hình Neo4j hiện đại, **database mới đã có sẵn lookup index mặc định** cho node label và relationship type. Tên index mặc định có thể do Neo4j sinh, thay đổi theo database và không nên đoán từ ví dụ.

Trước khi chạy lệnh DDL, hãy xác nhận:

1. Đang kết nối đúng database (đặc biệt nếu có nhiều database trong cùng DBMS).
2. Tài khoản có quyền xem schema và quyền tạo/xóa index khi thực hiện các bước đó.
3. Index tra cứu nào đã có, tên thực tế, loại thực thể và trạng thái của chúng.
4. Phiên bản Neo4j hỗ trợ cú pháp `CREATE LOOKUP INDEX`, `SHOW LOOKUP INDEXES` và các thủ tục chờ tương ứng. Các lệnh bên dưới sử dụng cú pháp Neo4j 5.x và các bản hiện hành tương thích; môi trường cũ hơn cần đối chiếu tài liệu đúng phiên bản.

Chạy:

```cypher
SHOW LOOKUP INDEXES;
```

Hoặc chỉ lấy những cột quan trọng:

```cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent
ORDER BY entityType, name;
```

Ví dụ kết quả minh họa (tên index do mỗi hệ thống quyết định):

| name | entityType | state | populationPercent |
| --- | --- | --- | --- |
| `index_node_labels` | `NODE` | `ONLINE` | `100.0` |
| `index_rel_types` | `RELATIONSHIP` | `ONLINE` | `100.0` |

Nếu đã có cả hai chỉ mục và đều `ONLINE`, thường **không cần tạo thêm**. Tránh viết script dựa vào một tên mặc định cố định; lấy `name` từ kết quả `SHOW` khi cần chờ hoặc xóa đúng index.

Có thể xem lookup index trong danh sách mọi loại index bằng:

```cypher
SHOW INDEXES
YIELD name, type, entityType, state, populationPercent
WHERE type = 'LOOKUP'
RETURN name, entityType, state, populationPercent
ORDER BY entityType, name;
```

Khi điều tra tổng quan hiệu năng, `SHOW INDEXES` còn cho thấy các chỉ mục property khác như range, text, point, full-text hoặc vector (tùy phiên bản). Không nhầm chúng với lookup index.

## 3. Tạo lookup index bằng Cypher

### 3.1. Tạo chỉ mục tra cứu label của node

```cypher
CREATE LOOKUP INDEX app_node_label_lookup IF NOT EXISTS
FOR (n)
ON EACH labels(n);
```

Ý nghĩa từng phần:

- `CREATE LOOKUP INDEX`: khai báo chỉ mục tra cứu token.
- `app_node_label_lookup`: tên index chủ động đặt, giúp vận hành và theo dõi. Tên cần duy nhất trong schema cùng database.
- `IF NOT EXISTS`: giúp lệnh có thể chạy lại khi index phù hợp hoặc index trùng tên đã tồn tại; nếu lệnh bỏ qua thao tác, **phải xem lại schema** để biết đối tượng nào thực sự đang có.
- `FOR (n) ON EACH labels(n)`: định nghĩa lookup index trên **các label của node**, không phải một property của `n`.

Nếu database đã có một lookup index node label mặc định với tên khác, Neo4j không tạo một bản sao thứ hai cho cùng phạm vi. Lệnh có `IF NOT EXISTS` có thể không tạo gì; điều đó **không có nghĩa** index `app_node_label_lookup` đã xuất hiện. Luôn kiểm tra `SHOW LOOKUP INDEXES` sau lệnh.

### 3.2. Tạo chỉ mục tra cứu type của relationship

```cypher
CREATE LOOKUP INDEX app_relationship_type_lookup IF NOT EXISTS
FOR ()-[r]-()
ON EACH type(r);
```

Cú pháp `FOR ()-[r]-()` biểu diễn mẫu relationship được lập chỉ mục; `ON EACH type(r)` chỉ ra token type. **Không dùng** `labels(r)` cho relationship, vì label thuộc node; relationship có type.

Đây cũng là lookup index cho **toàn bộ relationship type**, không phải một index chỉ cho `:FOLLOWS`. Nếu index loại này đã tồn tại thì không thể tạo một lookup index khác trùng phạm vi.

### 3.3. Vì sao `IF NOT EXISTS` chưa đủ để xác nhận thành công?

Một lệnh tạo index cần đạt hai điều kiện độc lập:

1. **Schema đúng:** Neo4j có lookup index cho `NODE` hoặc `RELATIONSHIP` như mong đợi.
2. **Sẵn sàng dùng:** index có trạng thái `ONLINE`.

`IF NOT EXISTS` chủ yếu xử lý tình huống lệnh DDL được chạy lặp hoặc tên/schema đã có. Nó không tự xác minh index với tên đề xuất được tạo mới, không bảo đảm mọi index đang `ONLINE`, và không thay cho quy trình quan sát trạng thái sau tạo.

Lưu ý thêm: Cypher không cho phép tạo đồng thời nhiều lookup index cùng loại thực thể. Nếu muốn đổi tên index do Neo4j tạo sẵn, hãy đánh giá yêu cầu thực tế, quyền và rủi ro vận hành; tránh xóa index mặc định chỉ để đổi tên cho đẹp.

## 4. Xem trạng thái và tiến độ xây dựng index

Ngay sau khi tạo, Neo4j có thể cần thời gian để xây dựng/populate index từ dữ liệu hiện có. Lệnh `CREATE` hoàn thành không nhất thiết đồng nghĩa đã sẵn sàng phục vụ mọi truy vấn.

```cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent
ORDER BY name;
```

Đọc các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `name` | Tên index thật dùng để tham chiếu bằng `db.awaitIndex` hoặc `DROP INDEX` |
| `entityType` | `NODE` hoặc `RELATIONSHIP` |
| `state` | Trạng thái vòng đời của index |
| `populationPercent` | Phần trăm tiến trình population theo thông tin Neo4j công bố |

Các trạng thái quan trọng:

| State | Diễn giải | Hành động phù hợp |
| --- | --- | --- |
| `POPULATING` | Đang xây dựng index | Chờ hoàn thành; kiểm tra lại tiến độ và tài nguyên nếu kéo dài bất thường |
| `ONLINE` | Đã xây dựng và sẵn sàng được truy vấn sử dụng | Có thể tiếp tục bước triển khai phụ thuộc vào index |
| `FAILED` | Quá trình xây dựng hoặc duy trì index thất bại | Kiểm tra chi tiết lỗi, log Neo4j, cấu hình và tài nguyên trước khi sửa hoặc tạo lại |

Thông thường, khi `state = 'ONLINE'`, `populationPercent` đạt `100.0`. Đừng suy ra index đã sẵn sàng chỉ vì tiến độ gần 100%; **ưu tiên kiểm tra `state = 'ONLINE'`**.

Nếu cần lọc riêng index còn đang xây dựng:

```cypher
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
WHERE state <> 'ONLINE'
RETURN name, entityType, state, populationPercent
ORDER BY name;
```

Kết quả rỗng ở đây nghĩa là không có lookup index nào nằm ngoài `ONLINE` **trong tập index mà lệnh trả về**. Nó không chứng minh cả hai loại lookup index đều tồn tại; phải kiểm tra đủ `NODE` và `RELATIONSHIP` ở truy vấn trước.

## 5. Chờ index sẵn sàng trước khi sử dụng

Không nên viết vòng lặp liên tục gọi `SHOW` quá nhanh. Neo4j cung cấp thủ tục chờ index chuyển sang trạng thái `ONLINE`.

### 5.1. Chờ một index theo tên thực tế

Ví dụ khi `SHOW LOOKUP INDEXES` cho thấy một index mang tên `app_node_label_lookup`:

```cypher
CALL db.awaitIndex('app_node_label_lookup', 300);
```

Trong ví dụ trên, `300` là thời gian chờ tối đa tính bằng **giây**. Nếu index không thể sẵn sàng trong thời hạn, thủ tục sẽ báo lỗi/thời gian chờ vượt hạn; ứng dụng hoặc migration không nên bỏ qua lỗi đó rồi xem như index đã `ONLINE`.

**Lưu ý về tên:** khi `CREATE ... IF NOT EXISTS` bị bỏ qua vì Neo4j đã có lookup index cùng phạm vi nhưng tên khác, lời gọi `db.awaitIndex('app_node_label_lookup', 300)` sẽ không tìm thấy index tên ấy. Hãy đọc `SHOW LOOKUP INDEXES` trước và thay chuỗi trên bằng tên **thực tế** của index cần chờ.

### 5.2. Chờ mọi index trong database

```cypher
CALL db.awaitIndexes(300);
```

Lệnh này phù hợp với giai đoạn khởi tạo database hoặc kiểm tra sau migration schema, khi ứng dụng cần **toàn bộ** index sẵn sàng. Với database lớn có nhiều range/full-text/vector index đang được xây dựng, đây có thể là lựa chọn chờ lâu hơn nhiều so với chờ một lookup index riêng lẻ.

Một trình tự thao tác rõ ràng:

```cypher
// 1. Kiểm tra tên, phạm vi, trạng thái hiện có.
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent;
```

```cypher
// 2. Chỉ tạo khi thực sự cần; tên có thể không được tạo do IF NOT EXISTS.
CREATE LOOKUP INDEX app_node_label_lookup IF NOT EXISTS
FOR (n) ON EACH labels(n);
```

```cypher
// 3. Chờ mọi index hoặc chọn đúng tên từ SHOW ở bước 1/2.
CALL db.awaitIndexes(300);
```

```cypher
// 4. Xác nhận đã ONLINE và đủ các loại index cần thiết.
SHOW LOOKUP INDEXES
YIELD name, entityType, state, populationPercent
RETURN name, entityType, state, populationPercent
ORDER BY entityType;
```

Chạy các đoạn trên thành các câu lệnh **riêng biệt**, bảo đảm câu lệnh tạo schema đã hoàn tất trước khi gọi thủ tục chờ. Việc chờ và kiểm tra thuộc khâu quản lý schema; nó không thay thế transaction và xác minh dữ liệu khi ứng dụng cập nhật node/relationship.

### 5.3. Xử lý khi chờ thất bại

Nếu `db.awaitIndex`/`db.awaitIndexes` báo timeout hoặc index chuyển `FAILED`:

1. Chạy lại `SHOW LOOKUP INDEXES` để lấy đúng `name` và `state`, xác nhận index còn tồn tại và không chọn nhầm database.
2. Đọc chi tiết chẩn đoán schema hoặc log phía Neo4j; kiểm tra dung lượng đĩa, bộ nhớ, lỗi storage và trạng thái các thành viên cluster nếu có.
3. Xác định lỗi nhất thời hay lỗi cần can thiệp. Chỉ quyết định tạo lại sau khi đánh giá tác động đến truy vấn thực tế.
4. Với một pipeline triển khai, đánh dấu migration/khởi tạo **chưa thành công**; tránh thông báo ứng dụng đã có index sẵn sàng khi `state` chưa `ONLINE`.

Không đặt timeout vô hạn cho hệ thống không có cơ chế giám sát. Tăng timeout có thể hợp lý với dữ liệu lớn, nhưng không giải quyết được index bị `FAILED`.

## 6. Xóa lookup index theo tên

Neo4j dùng **tên index**, không dùng biểu thức `labels(n)` hoặc `type(r)`, để chỉ ra index phải xóa:

```cypher
DROP INDEX app_node_label_lookup IF EXISTS;
```

Với relationship lookup index:

```cypher
DROP INDEX app_relationship_type_lookup IF EXISTS;
```

`IF EXISTS` khiến lệnh không báo lỗi nếu **tên** không tồn tại. Đây không phải thao tác tìm rồi xóa mọi index cùng loại. Nếu trước đó `CREATE ... IF NOT EXISTS` không tạo index với tên `app_node_label_lookup` vì đã có index mặc định tên khác, lệnh `DROP INDEX app_node_label_lookup IF EXISTS` cũng không xóa index mặc định đó.

Quy trình an toàn:

1. `SHOW LOOKUP INDEXES`; lưu lại **tên thực tế**, `entityType` và `state` của index cần thao tác.
2. Xác nhận môi trường, kế hoạch thay thế và ảnh hưởng hiệu năng. Lookup index có thể là đường truy cập quan trọng của nhiều truy vấn theo label/type.
3. Chạy `DROP INDEX <ten-index> IF EXISTS` với tên đã kiểm tra; không đoán tên hoặc vô tình xóa index mặc định.
4. Chạy lại `SHOW LOOKUP INDEXES` để chắc chắn index đích đã biến mất. Nếu cần, tạo lại theo các bước ở mục 3–5.

Việc xóa lookup index **không xóa node, relationship hay property**. Nhưng nó thay đổi lựa chọn truy cập dữ liệu của query planner, có thể làm các truy vấn tìm kiếm theo label/type chậm hơn. Trong môi trường production, quản lý thao tác này như một schema migration có kế hoạch và đánh giá hiệu năng.

## 7. Minh họa từ truy vấn đến kế hoạch thực thi

Giả sử ứng dụng có node `Person`, `Product` và quan hệ `BOUGHT`:

```cypher
CREATE (:Person {personId: 'p-01', name: 'Lan'});
CREATE (:Product {productId: 'sku-01', name: 'Sổ tay'});
```

Thêm relationship để kiểm tra:

```cypher
MATCH (p:Person {personId: 'p-01'})
MATCH (x:Product {productId: 'sku-01'})
MERGE (p)-[:BOUGHT]->(x);
```

Các truy vấn theo token:

```cypher
MATCH (p:Person)
RETURN p.name;
```

```cypher
MATCH ()-[r:BOUGHT]->()
RETURN type(r) AS relationshipType, count(r) AS total;
```

Để quan sát cách Neo4j lập kế hoạch:

```cypher
EXPLAIN
MATCH (p:Person)
RETURN p.name;
```

```cypher
EXPLAIN
MATCH ()-[r:BOUGHT]->()
RETURN count(r);
```

Tùy phiên bản, thống kê dữ liệu và cost planner, kế hoạch có thể dùng toán tử quét theo label/type (chẳng hạn `NodeByLabelScan` hoặc toán tử quét relationship theo type). Không nên kết luận kế hoạch dùng một index cụ thể chỉ từ tên toán tử; hãy kết hợp `SHOW LOOKUP INDEXES` với phần chi tiết của `EXPLAIN`/`PROFILE` và đặc điểm truy vấn.

**Phân biệt `EXPLAIN` và `PROFILE`:** `EXPLAIN` chỉ dựng kế hoạch mà không thực thi; `PROFILE` thực thi thật, báo thêm rows và DbHits. Với câu lệnh ghi, `PROFILE` có thể làm thay đổi graph, nên không dùng để thăm dò trên dữ liệu quan trọng một cách tùy tiện.

Khi truy vấn có điều kiện property:

```cypher
MATCH (p:Person {personId: 'p-01'})
RETURN p.name;
```

Lookup index giúp nhận diện label `:Person`, nhưng không lập chỉ mục riêng cho giá trị `personId`. Một range index trên `:Person(personId)` hoặc uniqueness constraint có thể phù hợp hơn khi dữ liệu lớn và truy vấn thường xuyên tìm đúng mã:

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Đó là **property constraint/index**, khác về mục đích và cú pháp so với lookup index. Việc lựa chọn cần căn cứ truy vấn và kế hoạch thực thi, không phải tạo mọi loại index một cách máy móc.

## 8. Tích hợp Java Driver và Spring Data Neo4j

Ứng dụng Java thường nên quản lý schema trước khi nhận lưu lượng nghiệp vụ: một migration khởi tạo index, chờ `ONLINE`, sau đó mới mở các chức năng phụ thuộc vào hiệu năng truy vấn. Ví dụ với **Neo4j Java Driver** (chạy trên Neo4j 5.x tương thích):

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class VerifyLookupIndexes {
    public static void main(String[] args) {
        try (
            Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me")
            );
            Session session = driver.session(
                SessionConfig.forDatabase("neo4j")
            )
        ) {
            session.run("""
                CREATE LOOKUP INDEX app_node_label_lookup IF NOT EXISTS
                FOR (n) ON EACH labels(n)
                """).consume();

            session.run("""
                CREATE LOOKUP INDEX app_relationship_type_lookup IF NOT EXISTS
                FOR ()-[r]-() ON EACH type(r)
                """).consume();

            // Thực hiện sau khi các lệnh DDL đã hoàn tất.
            session.run("CALL db.awaitIndexes(300)").consume();

            var indexes = session.run("""
                SHOW LOOKUP INDEXES
                YIELD name, entityType, state
                RETURN name, entityType, state
                """).list();

            boolean hasNode = false;
            boolean hasRelationship = false;
            for (Record row : indexes) {
                String entityType = row.get("entityType").asString();
                String state = row.get("state").asString();
                String name = row.get("name").asString();
                System.out.printf("%s: %s -> %s%n", name, entityType, state);

                if (!"ONLINE".equals(state)) {
                    throw new IllegalStateException(
                        "Index chưa sẵn sàng: " + name
                    );
                }
                if ("NODE".equals(entityType)) hasNode = true;
                if ("RELATIONSHIP".equals(entityType)) hasRelationship = true;
            }

            if (!hasNode || !hasRelationship) {
                throw new IllegalStateException(
                    "Thiếu lookup index cho NODE hoặc RELATIONSHIP"
                );
            }
        }
    }
}
```

Các ý chính:

- `session.run(...).consume()` tiêu thụ result stream của lệnh, bảo đảm giao dịch auto-commit được hoàn tất trước khi chuyển sang câu lệnh tiếp theo trong ví dụ.
- `IF NOT EXISTS` cho phép migration chạy lại nhưng **không bảo đảm hai tên index tự đặt sẽ tồn tại**. Vì vậy ví dụ kiểm tra theo `entityType` và `state`, không khẳng định theo tên đề xuất.
- `db.awaitIndexes(300)` chờ mọi index của database. Nếu chỉ muốn chờ một index, lấy đúng tên từ `SHOW LOOKUP INDEXES` và gọi `db.awaitIndex`.
- Tạo/xóa schema cần quyền phù hợp. Trong hệ thống thật, dùng cấu hình/secret manager cho thông tin xác thực; đừng đặt mật khẩu thật trong mã nguồn.

Với **Spring Data Neo4j**, repository và `Neo4jClient` phục vụ thao tác graph nghiệp vụ. Quản lý lookup index thường phù hợp hơn ở bước migration hoặc thành phần khởi tạo riêng (đặc biệt khi nhiều instance ứng dụng cùng khởi động). Repository `save(...)` không tạo lookup index dành cho mọi label/type theo mỗi lần lưu entity. Dù dùng Spring hay Java Driver trực tiếp, trạng thái index vẫn nên được quan sát qua Cypher và chỉ công bố khởi tạo thành công khi các index yêu cầu đã `ONLINE`.

## 9. Các lỗi và nhầm lẫn hay gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Tạo với `IF NOT EXISTS` không báo lỗi nhưng không thấy tên mới | Đã có lookup index cùng phạm vi, mang tên khác | Dùng `SHOW LOOKUP INDEXES` xác định index thực tế và trạng thái |
| Tạo không có `IF NOT EXISTS` báo trùng schema | Lookup index cùng `NODE` hoặc `RELATIONSHIP` đã có | Giữ index hiện có; không cố tạo bản sao cùng loại |
| `db.awaitIndex` báo không tìm thấy tên | Lấy nhầm tên, sai database hoặc lệnh tạo bị bỏ qua | Xem `name` thực từ `SHOW LOOKUP INDEXES` |
| Index ở `POPULATING` lâu | Khối lượng dữ liệu lớn hoặc tài nguyên/storage gặp vấn đề | Theo dõi tiến độ, log, tài nguyên và timeout hợp lý |
| `db.awaitIndexes` timeout dù lookup index đã `ONLINE` | Một index loại khác trong database chưa `ONLINE` | `SHOW INDEXES` để kiểm tra toàn bộ; chờ đúng lookup index nếu phù hợp |
| Index ở `FAILED` | Lỗi trong quá trình population/duy trì | Kiểm tra chẩn đoán, log và tài nguyên; lập kế hoạch khắc phục |
| `DROP INDEX ... IF EXISTS` chạy nhưng lookup index còn đó | Tên được xóa không phải tên index hiện có | Lấy đúng tên trong `SHOW LOOKUP INDEXES` |
| Sau khi xóa index, truy vấn theo label/type chậm | Query planner mất đường truy cập theo token | Đánh giá kế hoạch; khôi phục lookup index nếu cần |
| Có lookup index `ONLINE` nhưng lọc `email` vẫn chậm | Lookup index không index giá trị property `email` | Xem `EXPLAIN`; cân nhắc range/text index hoặc constraint phù hợp |
| `SHOW LOOKUP INDEXES` không chạy trong hệ thống rất cũ | Khác phiên bản Cypher hoặc quyền schema | Đối chiếu tài liệu Neo4j đúng phiên bản và quyền của tài khoản |

## 10. Bài thực hành

Thực hiện trên **database thử nghiệm**, nơi việc thay đổi schema được cho phép:

1. Chạy `SHOW LOOKUP INDEXES`. Ghi lại tên, `entityType`, `state` và `populationPercent`. Xác định có đủ hai phạm vi `NODE` và `RELATIONSHIP` chưa.
2. Chạy hai lệnh `CREATE LOOKUP INDEX ... IF NOT EXISTS` trong mục 3. Chạy lại các lệnh đó. Giải thích vì sao không sinh thêm các lookup index trùng phạm vi.
3. Chạy `CALL db.awaitIndexes(300)`, rồi kiểm tra lại `SHOW LOOKUP INDEXES`. Nếu index không `ONLINE`, mô tả các bước chẩn đoán cần làm.
4. Tạo node `:Person`, `:Product` và quan hệ `:BOUGHT`. Dùng `EXPLAIN` với truy vấn theo label và type; so sánh với truy vấn lọc theo `personId`.
5. Chỉ trong database thử nghiệm có kế hoạch khôi phục, chọn **đúng tên thực tế** của một lookup index, chạy `DROP INDEX <ten-index> IF EXISTS`, xác nhận chỉ mục biến mất, tạo lại và chờ `ONLINE`.

**Tiêu chí hoàn thành:** người học phân biệt được lookup index với property index, tạo được cú pháp đúng cho node và relationship, xác nhận trạng thái bằng `SHOW LOOKUP INDEXES`, sử dụng `db.awaitIndex`/`db.awaitIndexes` hợp lý, và xóa/khôi phục theo **tên thực tế** mà không làm mất dữ liệu graph.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Managing indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/managing-indexes/): cú pháp tạo, liệt kê và xóa các loại index, trong đó có lookup index.
- [Neo4j Cypher Manual — Search-performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/search-performance-indexes/): mục đích và các loại chỉ mục phục vụ tìm kiếm.
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/): sử dụng `EXPLAIN`, `PROFILE` và đọc kế hoạch thực thi.
- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): tự động commit, quản lý transaction và cách ứng dụng thực thi Cypher.
