# Gọi APOC: cài đặt, quyền thực thi và dữ liệu trả về

APOC (Awesome Procedures on Cypher) là thư viện mở rộng Neo4j với các procedure và function hỗ trợ xử lý graph, metadata, đường đi, chuyển đổi dữ liệu và tích hợp. Spring Data Neo4j (SDN) gọi APOC thông qua Cypher giống như gọi procedure khác: dùng `CALL`, chọn các cột bằng `YIELD`, rồi `RETURN` dữ liệu cần dùng. Ứng dụng không cần một thư viện APOC riêng trong classpath Java; APOC phải được cài và bật trên chính Neo4j DBMS mà SDN kết nối tới.

Trong module `SPRING_DATA_NEO4J`, APOC bổ sung khả năng cho repository và `Neo4jClient` khi Cypher cơ bản chưa đủ thuận tiện. Để gọi thành công, cần kiểm tra đúng phiên bản plugin, cấu hình procedure được load và unrestricted khi cần, quyền của database user, cũng như kiểu dữ liệu procedure trả về. Hãy chỉ bật procedure cần thiết và ánh xạ kết quả vào projection hoặc DTO phù hợp.

## 1. APOC Core và APOC Extended

Từ Neo4j 5, APOC được tách thành hai phần:

| Thành phần | Nội dung | Mức hỗ trợ và cài đặt |
|---|---|---|
| APOC Core | Nhóm procedure/function phổ biến, được Neo4j duy trì và hỗ trợ chính thức | Có sẵn trên Neo4j Aura; cài được qua Neo4j Desktop hoặc plugin trên server/Docker |
| APOC Extended | Procedure/function có dependency ngoài hoặc tính thử nghiệm, do cộng đồng duy trì | Cài riêng JAR tương thích; không được Neo4j product team hỗ trợ chính thức |

APOC Extended không bao gồm APOC Core. Nếu ứng dụng cần procedure từ cả hai phần, phải cài cả hai plugin phù hợp với phiên bản Neo4j đang chạy. Không dùng tên APOC Full trong tài liệu Neo4j mới để suy ra cách cài hiện tại; cách đóng gói trước Neo4j 5 khác với mô hình Core/Extended hiện nay.

Trước khi cài, hãy kiểm tra procedure cần dùng nằm trong Core hay Extended. Nhiều chức năng cũ của APOC đã có tương đương trong Cypher; khi Cypher cung cấp đầy đủ chức năng, nên ưu tiên Cypher vì một số APOC procedure/function tương ứng đã bị deprecated và có thể bị loại bỏ trong phiên bản tương lai.

## 2. Cài APOC theo môi trường Neo4j

APOC chạy trong Neo4j DBMS, không chạy bên trong ứng dụng Spring. Vì vậy, cài đặt phải thực hiện ở máy chủ/container/database service mà `spring.neo4j.uri` trỏ tới.

### Neo4j Desktop

Với database local trong Neo4j Desktop:

1. Tạo hoặc chọn database cần sử dụng.
2. Mở màn hình **Manage** của database.
3. Chọn tab **Plugins**.
4. Tìm APOC và nhấn **Install**.
5. Chờ Desktop báo đã cài đặt thành công; khởi động lại database nếu Desktop yêu cầu.

Plugin APOC trong tab Plugins của Desktop là APOC Core. Không giả định thao tác này đã cài APOC Extended.

### Neo4j Server cài trực tiếp

Với Neo4j Server:

1. Xác định phiên bản Neo4j đang chạy.
2. Tải JAR APOC Core tương thích với release series của Neo4j từ trang release chính thức.
3. Đặt JAR vào thư mục `$NEO4J_HOME/plugins`.
4. Kiểm tra cấu hình load/unrestricted nếu procedure yêu cầu.
5. Khởi động lại Neo4j để plugin được nạp.

Ví dụ vị trí file:

```text
$NEO4J_HOME/
  labs/
  plugins/
    apoc-<compatible-version>-core.jar
  conf/
    neo4j.conf
```

Một số bản phân phối Neo4j đặt JAR APOC Core trong `$NEO4J_HOME/labs`; có thể chuyển JAR tương thích từ `labs` sang `plugins` rồi restart. Với server production, nên quản lý JAR như một artifact triển khai có version rõ ràng thay vì tải tự động mỗi lần khởi động.

APOC dựa vào API nội bộ của Neo4j nên cần dùng bản tương thích. Hãy đối chiếu compatibility matrix hoặc release notes; không lấy ngẫu nhiên JAR mới nhất rồi đặt vào server cũ. Với quy ước release hiện hành, phần version Neo4j của APOC phải khớp release series Neo4j tương ứng; patch number có thể khác theo ma trận tương thích.

### Docker cho môi trường phát triển

Neo4j Docker image hỗ trợ biến môi trường `NEO4J_PLUGINS` để tải plugin khi container khởi động. Ví dụ sau cài APOC Core:

```bash
docker run --name neo4j-apoc \
  --publish=7474:7474 --publish=7687:7687 \
  --env NEO4J_AUTH=neo4j/change-this-password \
  --env 'NEO4J_PLUGINS=["apoc"]' \
  neo4j:<neo4j-version>
```

Thay `<neo4j-version>` bằng tag image cụ thể và dùng mật khẩu phù hợp với môi trường. Cách tải plugin runtime qua `NEO4J_PLUGINS` phù hợp để dựng nhanh môi trường phát triển hoặc thử nghiệm. Với production, nên tải JAR tương thích trước, quản lý checksum/artifact và mount thư mục plugin đã chuẩn bị vào container:

```bash
docker run --name neo4j-apoc \
  --publish=7474:7474 --publish=7687:7687 \
  --volume="$PWD/plugins:/plugins" \
  --volume="$PWD/data:/data" \
  --env NEO4J_AUTH=neo4j/change-this-password \
  neo4j:<neo4j-version>
```

Ví dụ này giả định thư mục `plugins` trên host đã chứa JAR APOC phù hợp. Cấu hình `neo4j.conf` có thể được mount hoặc chuyển thành environment variable theo quy tắc đặt tên của Neo4j Docker image.

### Neo4j Aura

APOC Core có sẵn trên Neo4j AuraDB/AuraDS, nên thường không cần tự cài JAR. Tuy nhiên, không phải mọi procedure đều được phép chạy trên mọi môi trường managed. Một số procedure bị hạn chế vì yêu cầu quyền truy cập hệ thống, file hoặc API nội bộ. APOC Extended không mặc nhiên có mặt trên Aura; kiểm tra danh sách tính năng được hỗ trợ của dịch vụ trước khi thiết kế phụ thuộc vào procedure cụ thể.

## 3. Xác minh APOC đã được cài và load

Sau khi cài plugin và restart Neo4j, kiểm tra từ Neo4j Browser hoặc Cypher Shell:

```cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name STARTS WITH 'apoc.'
RETURN name, signature
ORDER BY name;
```

Query này liệt kê các procedure APOC đã được load vào DBMS và signature của chúng. Nếu cần kiểm tra một procedure cụ thể:

```cypher
SHOW PROCEDURES
YIELD name, signature
WHERE name = 'apoc.meta.stats'
RETURN name, signature;
```

Nếu kết quả không có dòng nào, procedure chưa được load, không có trong plugin/version đang cài, hoặc bị giới hạn bởi allowlist. Nếu có dòng nhưng gọi vẫn bị từ chối, hãy kiểm tra `unrestricted`, quyền database user và giới hạn của môi trường managed.

Có thể xác minh bằng cách gọi procedure đơn giản trong môi trường thử nghiệm:

```cypher
CALL apoc.meta.stats()
YIELD nodeCount, relCount
RETURN nodeCount, relCount;
```

`apoc.meta.stats()` trả metadata từ transactional database statistics. Nó hữu ích cho quan sát tổng quan graph, nhưng không nên dùng thay cho phép đếm nghiệp vụ chính xác hoặc báo cáo tài chính. Procedure này cũng không được hỗ trợ trong parallel runtime và bị restricted trên Neo4j on-premise nếu chưa được cấu hình unrestricted.

## 4. Allowlist và unrestricted là hai cấu hình khác nhau

Neo4j có hai setting liên quan tới việc nạp và chạy procedure/function mở rộng:

| Setting | Tác dụng | Mặc định |
|---|---|---|
| `dbms.security.procedures.allowlist` | Chọn procedure/function nào được load vào DBMS | `*` (load tất cả procedure/function phù hợp trong plugin) |
| `dbms.security.procedures.unrestricted` | Cho phép procedure/function được truy cập các API nội bộ bị hạn chế | Rỗng |

`allowlist` quyết định procedure có được load hay không. `unrestricted` quyết định procedure đã load có được dùng những API nội bộ mà Neo4j mặc định hạn chế hay không. Bật một setting không thay thế setting còn lại.

Ví dụ chỉ load và unrestricted đúng procedure dùng trong bài:

```properties
dbms.security.procedures.allowlist=apoc.meta.stats
dbms.security.procedures.unrestricted=apoc.meta.stats
```

`apoc.meta.stats` cần unrestricted trên Neo4j on-premise. Nếu ứng dụng cần thêm APOC procedure/function, thêm đúng tên hoặc package cần thiết vào allowlist. Tránh cấu hình rộng như `apoc.*` hoặc `*` trong production chỉ để một câu query chạy được.

Với Docker, tên environment variable tương ứng có thể viết như sau:

```bash
--env NEO4J_dbms_security_procedures_allowlist='apoc.meta.stats' \
--env NEO4J_dbms_security_procedures_unrestricted='apoc.meta.stats'
```

Nếu allowlist đã được cấu hình cho plugin khác, hãy hợp nhất danh sách thay vì ghi đè và vô tình bỏ những procedure hợp lệ đang được workload khác sử dụng.

## 5. Quyền thực thi procedure và quyền trên graph

Procedure có thể đọc hoặc ghi graph, gọi dịch vụ ngoài, đọc file hoặc dùng API nội bộ. Cài plugin thành công không có nghĩa mọi database user đều có thể thực hiện mọi thao tác mà procedure cung cấp.

Cần phân biệt các lớp kiểm soát:

1. **Plugin availability:** JAR đã được cài và Neo4j đã load procedure.
2. **Procedure configuration:** allowlist cho phép load; unrestricted cho phép dùng API nội bộ nếu procedure yêu cầu.
3. **Procedure execution privilege:** database user/role được phép gọi procedure.
4. **Graph privileges:** các thao tác đọc/ghi bên trong procedure vẫn chịu quy tắc quyền tương ứng, trừ khi procedure được chạy theo cơ chế elevated privilege được cấp rõ ràng.
5. **Operating-system/network access:** quyền file, URL và hệ thống bên ngoài vẫn phụ thuộc cấu hình Neo4j và môi trường triển khai.

Trong Neo4j Enterprise, quyền thực thi procedure có thể quản lý theo role. Ví dụ cấp quyền chạy đúng procedure cho role `reporting`:

```cypher
GRANT EXECUTE PROCEDURE apoc.meta.stats
ON DBMS TO reporting;
```

Lệnh này chỉ cấp quyền thực thi procedure. Nó không tự cấp quyền đọc/ghi graph và không tự bật unrestricted. Nếu procedure thực hiện thao tác graph, role vẫn cần các quyền graph tương ứng. `EXECUTE BOOSTED PROCEDURE` là quyền riêng cho trường hợp cần chạy procedure với quyền nâng cao; không cấp quyền này rộng rãi và không xem nó như cách sửa mọi lỗi permission.

Quản lý execute privilege chi tiết theo role là tính năng RBAC của Neo4j Enterprise. Community Edition không có cùng bộ quyền execute theo role; procedure vẫn hoạt động theo quyền database user mà phiên bản/edition hỗ trợ. Dù dùng edition nào, hãy dùng tài khoản ứng dụng với quyền tối thiểu cần thiết và tránh chạy ứng dụng bằng tài khoản quản trị.

## 6. Procedure và function của APOC khác nhau thế nào?

APOC cung cấp cả procedure và function. Cú pháp gọi khác nhau:

| Loại | Cú pháp Cypher | Cách dùng |
|---|---|---|
| Procedure | `CALL apoc.package.name(...) YIELD ...` | Thực hiện một tác vụ và có thể trả về một hoặc nhiều record |
| Function | `RETURN apoc.package.name(...)` hoặc dùng trong biểu thức | Trả về một giá trị để kết hợp trong biểu thức Cypher |

Ví dụ procedure:

```cypher
CALL apoc.meta.stats()
YIELD nodeCount, relCount
RETURN nodeCount, relCount;
```

Ví dụ function:

```cypher
RETURN apoc.coll.toSet([1, 2, 2, 3]) AS uniqueValues;
```

Không dùng `CALL` để gọi function và cũng không đặt procedure trực tiếp vào biểu thức `RETURN`. Hãy xem signature trong `SHOW PROCEDURES` hoặc tài liệu APOC để biết tên, tham số đầu vào và cột đầu ra chính xác.

## 7. CALL, YIELD và RETURN: kiểm soát dữ liệu trả về

Procedure có thể trả nhiều cột. `YIELD` chọn những cột mà query cần sử dụng; `RETURN` quyết định dữ liệu cuối cùng gửi về client.

```cypher
CALL apoc.meta.stats()
YIELD nodeCount, relCount, labels
RETURN nodeCount, relCount, labels;
```

Các phần của câu lệnh:

- `CALL apoc.meta.stats()` gọi procedure không có tham số.
- `YIELD nodeCount, relCount, labels` chỉ nhận ba trường đầu ra.
- `RETURN ...` xác định record mà ứng dụng sẽ đọc.

Có thể đổi tên cột khi trả về:

```cypher
CALL apoc.meta.stats()
YIELD nodeCount, relCount
RETURN nodeCount AS totalNodes,
       relCount AS totalRelationships;
```

Có thể lọc hoặc xử lý các dòng procedure trả về bằng `WHERE`, `WITH`, `ORDER BY`, `LIMIT` như các record Cypher khác:

```cypher
CALL apoc.meta.stats()
YIELD labels
UNWIND keys(labels) AS label
RETURN label, labels[label] AS nodeCount
ORDER BY nodeCount DESC;
```

Ở đây `labels` là map từ label sang số node; `keys(labels)` tạo danh sách key, `UNWIND` biến mỗi key thành một row. Ứng dụng nhận các row có hai cột `label` và `nodeCount`.

Không nên mặc định `YIELD *` trong code ứng dụng lâu dài. Procedure có thể bổ sung cột ở phiên bản sau; chọn rõ cột cần dùng giúp hợp đồng kết quả ổn định hơn và tránh lấy dữ liệu không cần thiết.

## 8. Truyền tham số an toàn cho APOC

Procedure nhận tham số theo signature của nó. Khi gọi qua SDN, bind tham số như Cypher bình thường:

```cypher
CALL apoc.path.expandConfig($startNode, $config)
YIELD path
RETURN path;
```

`$startNode` và `$config` là tham số query. Không nối chuỗi từ request người dùng để tạo tên procedure, tên label hoặc một đoạn Cypher động. Parameter chỉ thay thế giá trị; nó không thay thế được tên procedure hay cấu trúc câu lệnh. Nếu cần chọn một procedure trong số các lựa chọn được hỗ trợ, hãy dùng allowlist ở tầng ứng dụng để ánh xạ lựa chọn sang câu Cypher cố định.

Với các procedure có khả năng tải URL hoặc đọc file, phải kiểm tra nguồn dữ liệu và cấu hình quyền truy cập tương ứng. Không cho người dùng cuối tự cung cấp URL/file path tùy ý rồi chuyển thẳng vào procedure; điều đó có thể tạo nguy cơ SSRF, đọc file nhạy cảm hoặc lộ dữ liệu.

## 9. Gọi APOC từ repository bằng @Query

Nếu kết quả procedure có thể ánh xạ ổn định vào projection/DTO, có thể khai báo custom query trong repository. Ví dụ projection chỉ nhận hai số liệu:

Entity:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String id;
}
```

Projection:

```java
public interface GraphCounts {
    long getNodeCount();
    long getRelCount();
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;

public interface GraphInspectionRepository
        extends Neo4jRepository<Person, String> {

    @Query("""
        CALL apoc.meta.stats()
        YIELD nodeCount, relCount
        RETURN nodeCount, relCount
        """)
    GraphCounts readGraphCounts();
}
```

Query trả về các cột có tên tương ứng với getter của projection. Kết quả này là dữ liệu thống kê, không phải một node entity `@Node`; không khai báo nó như entity graph chỉ để nhận các scalar.

Nếu procedure trả map lồng nhau, kiểu dữ liệu phức tạp hoặc một cấu trúc không khớp domain model, dùng `Neo4jClient` để tự ánh xạ record thành DTO. Đây là lựa chọn linh hoạt hơn khi cần kiểm soát rõ cách đọc từng cột.

## 10. Gọi APOC bằng Neo4jClient và ánh xạ DTO

`Neo4jClient` tích hợp với transaction management của Spring, có API bind parameter và cho phép truy cập từng record cùng Neo4j type system. Ví dụ dưới đây đọc số node, relationship và số node theo label từ `apoc.meta.stats()`.

DTO:

```java
import java.util.Map;

public record GraphStats(
    long nodeCount,
    long relationshipCount,
    Map<String, Long> nodesByLabel
) {
}
```

Service:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class GraphInspectionService {

    private final Neo4jClient neo4jClient;

    public GraphInspectionService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(readOnly = true)
    public Optional<GraphStats> readStats() {
        return neo4jClient.query("""
                CALL apoc.meta.stats()
                YIELD nodeCount, relCount, labels
                RETURN nodeCount, relCount, labels
                """)
            .fetchAs(GraphStats.class)
            .mappedBy((typeSystem, record) -> new GraphStats(
                record.get("nodeCount").asLong(),
                record.get("relCount").asLong(),
                record.get("labels").asMap(value -> value.asLong())
            ))
            .one();
    }
}
```

`fetchAs(GraphStats.class)` khai báo kiểu kết quả mong muốn; `mappedBy` chuyển từng record thành DTO. `labels` được trả về dưới dạng map, nên mapper chuyển mỗi Neo4j `Value` thành `long`. Procedure này thường trả một record; `.one()` biểu diễn kết quả dưới dạng `Optional` để code vẫn xử lý rõ trường hợp không có record.

Không cần ánh xạ `GraphStats` thành node hoặc lưu nó bằng repository. Đây là read model chỉ phục vụ kết quả procedure. Nếu procedure trả nhiều record, dùng `.all()`; nếu chỉ cần một scalar, có thể map sang `Long`, `String` hoặc kiểu tương ứng.

`Neo4jClient` tuân theo transaction Spring đang hoạt động. Nếu gọi procedure ghi dữ liệu trong service, hãy dùng transaction boundary phù hợp và bảo đảm database user có quyền ghi. `readOnly = true` trong ví dụ chỉ phù hợp vì `apoc.meta.stats()` là thao tác đọc metadata.

## 11. Hiểu cấu trúc dữ liệu procedure trả về

Một procedure có thể trả scalar, map, list, node, relationship hoặc path. Hãy đọc signature và tài liệu để biết chính xác kiểu từng cột.

Ví dụ output của `apoc.meta.stats()` gồm:

| Cột | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| `labelCount` | Integer | Số label phân biệt trong thống kê |
| `relTypeCount` | Integer | Số relationship type phân biệt |
| `propertyKeyCount` | Integer | Số property key |
| `nodeCount` | Integer | Tổng số node theo transactional statistics |
| `relCount` | Integer | Tổng số relationship theo transactional statistics |
| `labels` | Map | Map label sang số lượng node |
| `relTypes` | Map | Metadata pattern của relationship type theo label đầu/cuối |
| `relTypesCount` | Map | Map relationship type sang số lượng |
| `stats` | Map | Tập hợp các trường thống kê trên |

Không giả định mọi procedure trả một record hoặc một kiểu dữ liệu đơn giản. Một số procedure có thể trả nhiều row, mỗi row có cấu trúc riêng. Nếu query trả node/relationship, hãy quyết định ứng dụng cần entity graph hay chỉ cần dữ liệu hiển thị. Nếu chỉ cần tên, type hoặc count, trả scalar/map thay vì trả cả graph không cần thiết.

Với query dùng để ánh xạ entity qua SDN, nhớ rằng framework làm việc theo record. Nếu một root node xuất hiện ở nhiều record do `MATCH` relationship, hãy `collect()` các node/relationship liên quan để tạo một record cho mỗi root entity khi cần hydrate graph đầy đủ. Với kết quả phân tích hoặc thống kê APOC, DTO thường phù hợp hơn entity mapping.

## 12. Kiểm soát chi phí và tác động của APOC

APOC cung cấp nhiều tiện ích, nhưng không phải procedure nào cũng có cùng chi phí hoặc cùng phạm vi tác động.

- Kiểm tra procedure có quét graph, đọc metadata toàn database hay thực hiện I/O ngoài hay không.
- Giới hạn đầu ra bằng `YIELD` và `RETURN` các trường cần thiết.
- Tránh gọi procedure nặng trên mỗi request nếu có thể cache hoặc chạy theo lịch.
- Không chạy procedure bị đánh dấu không an toàn với parallel runtime trong parallel runtime.
- Với procedure ghi, kiểm tra transaction boundary, khả năng retry và idempotency.
- Với procedure đọc/ghi file hoặc URL, cấu hình nguồn được phép và quyền hệ điều hành rõ ràng.
- Ưu tiên Cypher native khi đã có chức năng tương đương và đủ đáp ứng yêu cầu.

`apoc.meta.stats()` đọc transactional database statistics và bị đánh dấu không an toàn cho chạy đồng thời bằng parallel runtime. Dùng nó cho kiểm tra metadata/tổng quan, không dùng làm nguồn duy nhất cho chỉ số nghiệp vụ cần độ chính xác và nhất quán theo quy tắc riêng.

## 13. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| `There is no procedure with the name ...` | APOC chưa cài, chưa load hoặc procedure không có trong phần Core/Extended đang dùng | Kiểm tra JAR, phiên bản, restart và `SHOW PROCEDURES` |
| Procedure có trong `SHOW PROCEDURES` nhưng gọi bị từ chối | Procedure bị restricted hoặc thiếu quyền execute | Kiểm tra `dbms.security.procedures.unrestricted` và execute privilege phù hợp |
| Procedure không xuất hiện sau khi cấu hình allowlist | Tên procedure/package chưa nằm trong allowlist | Bổ sung đúng procedure cần dùng và restart Neo4j |
| Docker chạy được ở dev nhưng không ổn định ở production | Dùng cơ chế tải plugin runtime thay vì artifact được quản lý | Pin JAR tương thích, mount plugin và quản lý version |
| APOC JAR không tương thích Neo4j | Dùng sai release series | Chọn bản theo compatibility matrix và xem log khởi động |
| `YIELD` báo không có cột | Dùng sai tên cột hoặc procedure khác version | Xem signature bằng `SHOW PROCEDURES` và docs đúng phiên bản |
| SDN không ánh xạ được kết quả thành entity | Procedure trả scalar/map hoặc nhiều record không đúng entity mapping | Dùng projection hoặc `Neo4jClient` với DTO mapper |
| `Neo4jClient.one()` không có kết quả | Procedure/query không phát record hoặc điều kiện lọc loại hết row | Kiểm tra query trong Browser và xử lý `Optional.empty()` |
| Procedure ghi thất bại dù đã được execute | User thiếu graph write privilege hoặc transaction không phù hợp | Cấp đúng quyền graph và kiểm tra transaction boundary |
| Procedure đọc URL/file ngoài ý muốn | Quyền tải dữ liệu hoặc nguồn chưa được giới hạn | Hạn chế URL/file, tắt chức năng không dùng và áp dụng least privilege |
| Procedure chạy chậm hoặc gây tải cao | Quét graph, xử lý lượng dữ liệu lớn hoặc gọi quá thường xuyên | Giới hạn phạm vi, batch/caching hợp lý và đo query plan/runtime |

Khi debug, kiểm tra theo thứ tự: procedure có trong `SHOW PROCEDURES` không; signature có đúng với query không; allowlist có load nó không; procedure có yêu cầu unrestricted không; user có quyền execute và quyền graph phù hợp không; cuối cùng mới kiểm tra cách SDN ánh xạ kết quả.

## 14. Tự kiểm tra

1. APOC Core và APOC Extended khác nhau về nội dung và mức hỗ trợ như thế nào?
2. Vì sao cài APOC trên Neo4j server thay vì thêm dependency vào ứng dụng Spring?
3. Cách cài APOC Core trên Neo4j Desktop, server và Docker khác nhau ra sao?
4. `dbms.security.procedures.allowlist` khác `dbms.security.procedures.unrestricted` ở điểm nào?
5. Vì sao `apoc.meta.stats()` cần unrestricted trên Neo4j on-premise?
6. `GRANT EXECUTE PROCEDURE` trong Neo4j Enterprise cấp quyền gì và có thay thế graph privilege không?
7. `CALL`, `YIELD` và `RETURN` phối hợp như thế nào khi gọi một APOC procedure?
8. Vì sao không nên dùng `YIELD *` trong query ứng dụng lâu dài?
9. Khi nào nên dùng repository projection và khi nào nên dùng `Neo4jClient` để map DTO?
10. Vì sao procedure có thể trả kết quả thống kê nhưng không nên dùng các giá trị đó thay cho chỉ số nghiệp vụ chính xác?

APOC được cài và cấu hình tại Neo4j DBMS; SDN gọi nó bằng Cypher `CALL` như các procedure khác. Hãy chọn đúng Core/Extended và phiên bản tương thích, chỉ load/unrestrict procedure thực sự cần, cấp quyền execute và graph tối thiểu, sau đó dùng `YIELD`/`RETURN` để định hình dữ liệu. Khi kết quả là metadata hoặc DTO, `Neo4jClient` cho phép bind và ánh xạ từng record rõ ràng trong transaction Spring.

## Tài liệu tham khảo

- [APOC Core — Installation](https://neo4j.com/docs/apoc/current/installation/)
- [APOC Core — Security Guidelines](https://neo4j.com/docs/apoc/current/security-guidelines/)
- [APOC Core — `apoc.meta.stats`](https://neo4j.com/docs/apoc/current/overview/apoc.meta/apoc.meta.stats/)
- [APOC — Core and Extended overview](https://neo4j.com/labs/apoc/)
- [Neo4j Operations Manual — Configure plugins](https://neo4j.com/docs/operations-manual/current/configuration/plugins/)
- [Neo4j Operations Manual — Procedure and function privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-execute-permissions/)
- [Spring Data Neo4j 8.2 — FAQ: custom queries and custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j 8.2 — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
