# Ánh xạ kết quả thuật toán thành DTO thay vì entity dùng để lưu

Truy vấn chuyên biệt thường trả về dữ liệu được tính toán ngay trong lúc đọc graph: điểm PageRank, độ tương đồng, số lượng láng giềng, thứ hạng, khoảng cách hoặc đường đi. Những giá trị này mô tả kết quả của một phép tính, không nhất thiết là thuộc tính bền vững của node hay relationship. Trong Spring Data Neo4j (SDN), nên ánh xạ chúng thành DTO dành cho đọc thay vì cố biến toàn bộ kết quả thành entity `@Node` để lưu.

DTO giúp biểu diễn đúng hình dạng kết quả mà use case cần, giới hạn số field trả về và tránh đưa một object chỉ được hydrate một phần vào luồng ghi. Với thuật toán Neo4j Graph Data Science (GDS), chế độ `stream` trả các hàng kết quả có thể ánh xạ trực tiếp thành DTO bằng `Neo4jClient.fetchAs(...).mappedBy(...)`.

## 1. Kết quả thuật toán không đồng nghĩa với entity

Một entity `@Node` mô tả dữ liệu có danh tính và vòng đời trong graph. Ví dụ `Person` có `personId`, `name` và các relationship như `FOLLOWS`. Một kết quả thuật toán PageRank lại có thể chỉ gồm `personId`, `name` và `score`.

Hai loại dữ liệu có mục đích khác nhau:

| Dữ liệu | Mục đích | Kiểu Java phù hợp |
|---|---|---|
| Person được lưu trong graph | Đại diện node và các relationship được mapping | Entity `@Node` |
| Điểm PageRank tại thời điểm truy vấn | Hiển thị thứ hạng hoặc dùng để xếp hạng | `PersonRankDto` |
| Điểm tương đồng giữa hai người | Hiển thị gợi ý kết nối | `SimilarityDto` |
| Đường đi ngắn nhất giữa hai điểm | Hiển thị tuyến đường và tổng chi phí | `PathResultDto` |
| Thống kê số node, số cạnh hoặc percentile | Hiển thị báo cáo tổng hợp | DTO thống kê |

Nếu kết quả chỉ dùng để trả API, hiển thị hoặc tính toán tiếp ở tầng ứng dụng, DTO là read model tự nhiên. DTO không cần `@Node`, `@Id`, `@Relationship` và không nên được truyền vào repository `save()`.

### Vì sao không hydrate entity rồi trả về?

Một entity được SDN hydrate từ custom query có thể chỉ chứa một phần property hoặc relationship. Nếu sau đó ứng dụng sửa entity này rồi lưu lại, SDN có thể xem phần graph chưa được hydrate là dữ liệu không có và xóa hoặc ghi đè relationship ngoài ý muốn.

Kết quả thuật toán còn có thể chứa field không thuộc graph như `score`, `rank`, `similarity` hoặc `totalCost`. Việc thêm những field này vào entity chỉ để nhận kết quả sẽ trộn dữ liệu tính toán tạm thời với mô hình persistence.

Hãy giữ ranh giới rõ ràng:

- Entity biểu diễn dữ liệu graph cần đọc/ghi.
- DTO biểu diễn kết quả truy vấn hoặc thuật toán dành cho một use case.
- Mapper chuyển dữ liệu từ record Neo4j sang DTO.
- Nếu kết quả thuật toán cần lưu lâu dài, hãy chủ động ghi nó thành property hoặc relationship bằng quy trình phù hợp rồi đọc lại theo mô hình đã thiết kế.

## 2. Chọn đúng execution mode của GDS

Neo4j Graph Data Science cung cấp các execution mode khác nhau. Chọn mode trước khi thiết kế DTO:

| Mode | Kết quả | Có ghi dữ liệu không? | Use case thường gặp |
|---|---|---|---|
| `stream` | Các hàng kết quả của thuật toán | Không ghi graph | Trả điểm, thứ hạng hoặc đường đi thành DTO |
| `stats` | Một hàng thống kê tổng hợp | Không | Lấy số lượng và phân phối kết quả |
| `mutate` | Thống kê; kết quả được thêm vào graph trong bộ nhớ | Không ghi về database | Dùng kết quả thuật toán tiếp theo trong cùng projected graph |
| `write` | Thống kê; kết quả được ghi về Neo4j | Có | Lưu điểm hoặc relationship để nhiều truy vấn sau sử dụng |

Với yêu cầu ánh xạ kết quả thành DTO mà không thay đổi graph, `stream` thường là lựa chọn phù hợp. Ví dụ PageRank stream trả `nodeId` và `score`; Cypher có thể bổ sung các property cần thiết rồi trả một record phẳng.

Nếu ứng dụng cần đọc lại score nhiều lần mà không chạy thuật toán mỗi request, cân nhắc `write` để lưu score vào property của node. Khi đó kết quả đã trở thành dữ liệu graph và có thể được truy vấn theo mô hình persistence. `mutate` chỉ thay đổi projected graph trong bộ nhớ; nó không tự ghi kết quả về database.

GDS là thư viện/procedure cần được cài đặt và cấu hình trên Neo4j. Các ví dụ dưới đây giả định graph projection `socialGraph` đã tồn tại và có các node `Person` với property `personId` ổn định cùng `name`.

## 3. Dùng GDS stream và trả các scalar có ý nghĩa nghiệp vụ

PageRank trả về `nodeId` và `score`. `nodeId` là định danh nội bộ của node trong Neo4j, không phải khóa nghiệp vụ phù hợp để lưu vào API hoặc DTO lâu dài. Dùng `gds.util.asNode(nodeId)` để lấy node tương ứng, sau đó trả `personId` và các field cần thiết.

```cypher
CALL gds.pageRank.stream($graphName)
YIELD nodeId, score
WITH gds.util.asNode(nodeId) AS person, score
WHERE person IS NOT NULL
  AND person.personId IS NOT NULL
RETURN person.personId AS personId,
       person.name AS name,
       score AS score
ORDER BY score DESC, personId ASC
LIMIT $limit;
```

Truy vấn thực hiện các bước:

1. Gọi thuật toán PageRank ở mode `stream` trên graph đã project.
2. Nhận `nodeId` và `score` từ GDS.
3. Chuyển `nodeId` về node bằng `gds.util.asNode()`.
4. Loại kết quả không còn node hoặc thiếu business ID.
5. Chỉ trả ba cột cần cho read model.
6. Sắp xếp ổn định theo score giảm dần và `personId` tăng dần.
7. Giới hạn số kết quả ở database bằng `$limit`.

Alias trong `RETURN` là hợp đồng giữa Cypher và mapper Java. Nếu đổi `personId` thành `id`, mapper cũng phải đổi theo.

### Vì sao không trả nodeId trực tiếp?

Internal node ID chỉ có ý nghĩa trong database và vòng đời của node. Khi node bị xóa hoặc database được thay đổi, không nên dùng giá trị này như một business key trong DTO, URL hoặc dữ liệu tích hợp giữa các hệ thống. Trả `personId` giúp consumer có một định danh ổn định theo miền nghiệp vụ.

`gds.util.asNode()` có thể trả `null` nếu node tương ứng không còn tồn tại trong database. Điều kiện `WHERE person IS NOT NULL` bảo vệ các phép truy cập property phía sau. Nếu thuật toán sử dụng một graph projection cũ, cần xem xét thời điểm projection được tạo và chính sách refresh graph.

## 4. Thiết kế DTO riêng cho kết quả thuật toán

DTO chỉ chứa các field mà use case cần:

```java
public record PersonRankDto(
        String personId,
        String name,
        double score) {
}
```

Đây là một read model:

- Không có `@Node` vì nó không đại diện node cần persistence.
- Không có `@Id` vì khóa của DTO chỉ là dữ liệu kết quả.
- Không có relationship collection vì truy vấn chỉ trả score và thông tin nhận diện.
- Không cần đưa toàn bộ thuộc tính của `Person` vào DTO.

Nếu API cần thứ hạng, có thể bổ sung `rank` bằng Cypher `row_number()` hoặc tính ở tầng ứng dụng sau khi đã có thứ tự ổn định. Nếu chỉ trả top N, nên giới hạn bằng `ORDER BY` và `LIMIT` ngay trong Cypher để giảm số record truyền qua Bolt.

## 5. Ánh xạ bằng Neo4jClient.fetchAs(...).mappedBy(...)

`Neo4jClient` phù hợp với custom query có kết quả không phải domain entity. API `fetchAs(Target.class).mappedBy(...)` cho phép đọc từng `Record` và tự tạo DTO. `Neo4jClient` vẫn tham gia transaction management của Spring, đồng thời cung cấp parameter binding và Neo4j type system cho mapper.

```java
import java.util.Collection;

import org.neo4j.driver.Value;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class PersonRankingReader {

    private static final String TOP_RANKED_PEOPLE = """
            CALL gds.pageRank.stream($graphName)
            YIELD nodeId, score
            WITH gds.util.asNode(nodeId) AS person, score
            WHERE person IS NOT NULL
              AND person.personId IS NOT NULL
            RETURN person.personId AS personId,
                   person.name AS name,
                   score AS score
            ORDER BY score DESC, personId ASC
            LIMIT $limit
            """;

    private final Neo4jClient neo4jClient;

    public PersonRankingReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(readOnly = true)
    public Collection<PersonRankDto> topRanked(String graphName, int limit) {
        if (graphName == null || graphName.isBlank()) {
            throw new IllegalArgumentException("graphName is required");
        }
        if (limit <= 0) {
            throw new IllegalArgumentException("limit must be positive");
        }

        return neo4jClient.query(TOP_RANKED_PEOPLE)
                .bind(graphName).to("graphName")
                .bind(limit).to("limit")
                .fetchAs(PersonRankDto.class)
                .mappedBy((typeSystem, record) -> {
                    Value nameValue = record.get("name");
                    String name = nameValue.isNull()
                            ? null
                            : nameValue.asString();

                    return new PersonRankDto(
                            record.get("personId").asString(),
                            name,
                            record.get("score").asDouble());
                })
                .all();
    }
}
```

`typeSystem` được cung cấp trong mapper khi cần chuyển đổi kiểu Neo4j đặc thù. Ví dụ này chỉ cần đọc các scalar nên không sử dụng tham số đó. `Value.isNull()` được kiểm tra trước khi gọi `asString()` để xử lý trường hợp `name` không có giá trị.

Các điểm cần giữ nhất quán:

- `Cypher.parameter`/parameter name và `.bind(...).to(...)` phải khớp nhau.
- Alias `personId`, `name`, `score` phải khớp với các key đọc từ `Record`.
- Kiểu dữ liệu Cypher trả về phải phù hợp với cách đọc `asString()` hoặc `asDouble()`.
- Kiểm tra null trước khi chuyển đổi các field tùy chọn.
- Dùng `all()` khi thực sự cần collection; với kết quả lớn, giới hạn hoặc phân trang trước khi materialize.

## 6. Khi nào dùng DTO projection trực tiếp từ repository?

SDN hỗ trợ DTO-based projection cho repository query. Cách này thuận tiện khi custom query trả về node domain cùng một vài thuộc tính tính toán bổ sung.

Giả sử repository quản lý entity `Person`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;
}
```

DTO projection có các field của entity và thêm `score`:

```java
public class PersonRankView {

    private String personId;
    private String name;
    private Double score;

    protected PersonRankView() {
    }

    public String getPersonId() { return personId; }
    public String getName() { return name; }
    public Double getScore() { return score; }

    public void setPersonId(String personId) { this.personId = personId; }
    public void setName(String name) { this.name = name; }
    public void setScore(Double score) { this.score = score; }
}
```

Repository có thể trả projection:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        CALL gds.pageRank.stream($graphName)
        YIELD nodeId, score
        WITH gds.util.asNode(nodeId) AS person, score
        WHERE person IS NOT NULL
        RETURN person, score AS score
        ORDER BY score DESC
        LIMIT $limit
        """)
    List<PersonRankView> findTopRanked(
            @Param("graphName") String graphName,
            @Param("limit") int limit);
}
```

Trong DTO projection, các thuộc tính của domain type được dùng để populate phần entity của DTO; thuộc tính bổ sung như `score` được lấy từ record trả về. Tên thuộc tính/alias bổ sung phải khớp chính xác. Các kiểu đơn giản và persistent entity được hỗ trợ; collection của chúng có thể dùng, còn Map không phải kiểu bổ sung được hỗ trợ theo cơ chế projection này.

Với kết quả thuần thuật toán gồm nhiều scalar hoặc cấu trúc tùy chỉnh, `Neo4jClient` thường rõ ràng hơn vì mapper quyết định trực tiếp từng field. DTO projection qua repository phù hợp khi kết quả vẫn gắn với một root entity và chỉ thêm một số field tính toán.

## 7. Chọn giữa repository projection và Neo4jClient

| Tiêu chí | Repository DTO projection | `Neo4jClient` custom mapping |
|---|---|---|
| Kết quả gắn với root entity | Phù hợp | Có thể làm được nhưng phải tự map |
| Kết quả là các scalar thuật toán độc lập | Có giới hạn theo quy tắc projection | Rất phù hợp |
| Cần kiểm soát conversion từng field | Ít trực tiếp hơn | Chủ động qua `mappedBy` |
| Kết quả có cấu trúc tùy biến | Bị giới hạn bởi kiểu projection | Có thể tự xây DTO hoặc collection |
| Query cần parameter binding fluent | Dùng `@Query` và `@Param` | Có `.bind(...).to(...)` |
| Cần fragment repository tái sử dụng | Có thể khai báo method projection | Có thể đóng gói custom fragment dùng `Neo4jClient` |

Không cần tạo một entity chỉ để có nơi đặt kết quả. Chọn abstraction dựa trên hình dạng kết quả và mục đích của object ở tầng ứng dụng.

## 8. Ánh xạ kết quả khác kiểu: điểm, thống kê và danh sách ID

Không phải thuật toán nào cũng trả một node và một score. Một số thuật toán trả cặp node cùng điểm tương đồng; một số trả component ID; một số trả danh sách ID của node trên đường đi.

Ví dụ DTO cho kết quả tương đồng:

```java
public record PersonSimilarityDto(
        String sourcePersonId,
        String targetPersonId,
        double similarity) {
}
```

Cypher cần chuyển cả hai internal ID về node rồi trả business key:

```cypher
CALL gds.nodeSimilarity.stream($graphName)
YIELD node1, node2, similarity
WITH gds.util.asNode(node1) AS source,
     gds.util.asNode(node2) AS target,
     similarity
WHERE source IS NOT NULL
  AND target IS NOT NULL
RETURN source.personId AS sourcePersonId,
       target.personId AS targetPersonId,
       similarity AS similarity
ORDER BY similarity DESC, sourcePersonId, targetPersonId
LIMIT $limit;
```

Khi viết mapper, ánh xạ từng alias về field tương ứng. Không đưa toàn bộ node vào DTO nếu màn hình chỉ cần ID và score; tránh truyền các property không cần thiết qua network.

Với thuật toán trả danh sách node ID, có thể dùng `gds.util.asNodes(nodeIds)` rồi biến thành list business ID trong Cypher. Hãy kiểm tra node có thể không còn tồn tại và xử lý giá trị null phù hợp. Với kết quả đường đi, DTO có thể chứa `List<String>` business ID và tổng chi phí thay vì lưu một `Path` hoặc graph entity đầy đủ.

## 9. Kiểm soát kích thước kết quả và hiệu năng

Kết quả `stream` có thể rất lớn, đôi khi cùng bậc với số node trong projected graph. Không nên gọi `all()` cho toàn bộ kết quả nếu API chỉ cần top 20 hoặc một trang nhỏ.

Các nguyên tắc:

1. Chỉ `RETURN` field cần thiết cho DTO.
2. Dùng `ORDER BY` và `LIMIT` trong Cypher cho use case top N.
3. Dùng stable tie-breaker như business ID để thứ tự ổn định khi score bằng nhau.
4. Dùng pagination/streaming phù hợp khi kết quả lớn; không materialize toàn bộ graph vào heap chỉ để trả một API.
5. Chọn graph projection và cấu hình thuật toán phù hợp; DTO mapping không làm thuật toán rẻ hơn nếu GDS vẫn phải tính trên toàn graph.
6. Đo thời gian chạy procedure, số record, dữ liệu trả về và heap phía ứng dụng.

`LIMIT` giới hạn số record được trả về nhưng không nhất thiết làm cho thuật toán chỉ tính trên đúng số node đó. PageRank vẫn có thể phải chạy trên toàn bộ graph projection trước khi Cypher chọn top N. Nếu cần giảm chi phí tính toán, hãy xem xét phạm vi projection, cấu hình thuật toán hoặc cách lưu kết quả dùng lại.

## 10. Không lưu nhầm DTO hoặc entity hydrate một phần

DTO là object đọc. Không truyền `PersonRankDto` hoặc `PersonRankView` vào `personRepository.save(...)`. Nó không đại diện cho node hoàn chỉnh và score có thể thay đổi sau mỗi lần chạy thuật toán.

Tương tự, không trả entity `Person` được hydrate một phần từ custom query rồi dùng lại như aggregate đầy đủ để lưu. SDN xem entity mapping là mô hình dữ liệu cần được đồng bộ; các relationship không được query hydrate có thể bị ảnh hưởng khi lưu.

Nếu yêu cầu nghiệp vụ thay đổi và score cần được lưu lâu dài:

1. Chọn property đích rõ ràng, ví dụ `pageRankScore`.
2. Chạy GDS ở mode `write` hoặc ghi kết quả bằng Cypher theo khóa ổn định.
3. Quản lý thời điểm tính, phiên bản thuật toán và cấu hình nếu cần audit.
4. Đọc lại bằng entity hoặc projection phù hợp với mục tiêu sử dụng.

Không dùng `stream` rồi tự động lưu từng DTO trở lại node nếu chưa xác định rõ tính nhất quán, transaction, phiên bản kết quả và tác động khi thuật toán chạy lại.

## 11. Kiểm thử mapping DTO

Kiểm thử cần xác nhận cả truy vấn lẫn hợp đồng alias/kiểu dữ liệu:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PersonRankingReaderTest {

    @Autowired
    PersonRankingReader reader;

    @Test
    void mapsAlgorithmRowsToReadDto() {
        Collection<PersonRankDto> results = reader.topRanked("socialGraph", 10);

        assertThat(results).isNotEmpty();
        assertThat(results).allSatisfy(result -> {
            assertThat(result.personId()).isNotBlank();
            assertThat(result.score()).isGreaterThanOrEqualTo(0.0);
        });
    }
}
```

Đây là integration test cần graph projection `socialGraph` và dữ liệu test được tạo trước. Nếu GDS không có trong môi trường test, có thể kiểm thử mapper độc lập bằng fixture `Record` hoặc kiểm thử custom query với một query Cypher trả cùng alias và kiểu dữ liệu.

Các trường hợp nên kiểm tra thêm:

- `personId` bị thiếu: query loại bỏ node hoặc mapper từ chối dữ liệu.
- `name` null: DTO nhận null theo hợp đồng đã chọn.
- `score` không phải numeric: test phải thất bại để phát hiện schema kết quả sai.
- Hai node có cùng score: thứ tự vẫn ổn định nhờ tie-breaker.
- `limit` bằng 0 hoặc âm: tầng ứng dụng từ chối trước khi gửi query.
- Node trong projection không còn trong database: `gds.util.asNode()` trả null và query xử lý an toàn.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ánh xạ kết quả thuật toán thành entity `@Node` | Trộn dữ liệu tính toán với mô hình persistence | Tạo DTO riêng cho read model |
| Dùng `nodeId` làm business ID | ID nội bộ không phù hợp để lưu lâu dài hoặc đưa ra API | Chuyển sang khóa nghiệp vụ bằng `gds.util.asNode()` |
| Không dùng `gds.util.asNode()` khi cần thuộc tính node | DTO chỉ có internal ID và score | Chuyển ID về node rồi trả scalar cần thiết |
| Alias Cypher khác key mapper | Đọc sai field hoặc lỗi mapping | Giữ alias và DTO constructor đồng bộ |
| Gọi `asString()` trên giá trị null | Lỗi chuyển đổi runtime | Kiểm tra `Value.isNull()` trước |
| Dùng DTO projection nhưng thiếu alias của field bổ sung | SDN không tìm thấy dữ liệu để populate DTO | Trả đúng tên property trong record |
| Dùng Map làm field bổ sung của DTO projection | Không phù hợp giới hạn kiểu projection | Dùng scalar/collection được hỗ trợ hoặc `Neo4jClient` mapper |
| Lưu entity hydrate một phần | Có thể xóa hoặc ghi đè relationship chưa tải | Dùng DTO cho truy vấn đọc hoặc hydrate đầy đủ trước khi ghi |
| Gọi `all()` cho toàn bộ graph | Tốn bộ nhớ và tăng network transfer | Lọc, `ORDER BY`, `LIMIT` hoặc phân trang |
| Nghĩ `LIMIT` làm PageRank chỉ tính top N node | Đánh giá thấp chi phí thuật toán | Tối ưu graph projection và execution mode |
| Dùng GDS `stream` khi cần lưu score lâu dài | Mỗi lần đọc phải chạy lại thuật toán | Cân nhắc `write` và quản lý property kết quả |

## 13. Bài tập thực hành

Giả sử graph `socialGraph` chứa các node `Person` có `personId` và `name`:

1. Chạy `gds.pageRank.stream('socialGraph')` và quan sát các cột `nodeId`, `score`.
2. Dùng `gds.util.asNode(nodeId)` để trả `personId` và `name` thay cho internal ID.
3. Tạo `PersonRankDto` bằng Java record, không gắn annotation persistence.
4. Dùng `Neo4jClient.fetchAs(PersonRankDto.class).mappedBy(...)` để ánh xạ từng record.
5. Bind `graphName` và `limit` thành named parameters.
6. Kiểm tra trường hợp `name` null và `person` không còn tồn tại.
7. Thêm tie-breaker vào `ORDER BY` để thứ tự ổn định.
8. So sánh DTO projection qua repository khi query trả node root cùng score bổ sung.
9. Chạy cùng thuật toán ở mode `write` trong môi trường thử nghiệm và so sánh với `stream`; giải thích khi nào score nên trở thành property của node.
10. Viết integration test xác nhận mapper trả đúng DTO và không cần gọi `save()` cho kết quả đọc.

Sau bài tập, hãy giải thích được vì sao kết quả thuật toán là read model, cách ánh xạ `nodeId` thành business ID, khác biệt giữa repository DTO projection và `Neo4jClient`, cũng như khi nào nên dùng GDS `stream` hay `write`.

## Kết luận

Kết quả thuật toán như PageRank, similarity hoặc shortest path thường là dữ liệu phục vụ một use case đọc, không phải entity cần lưu. Dùng GDS `stream` để trả các hàng kết quả, chuyển internal node ID thành business ID trong Cypher và ánh xạ bằng `Neo4jClient.fetchAs(...).mappedBy(...)` thành DTO. Dùng repository DTO projection khi kết quả vẫn gắn với root entity và chỉ bổ sung một số field tính toán. Giữ DTO tách khỏi persistence entity, kiểm soát alias và kiểu dữ liệu, giới hạn kết quả ngay trong Cypher và chỉ ghi score về graph khi nghiệp vụ thực sự cần lưu trữ.

## Tài liệu tham khảo

- [Spring Data Neo4j – Custom queries and custom mappings](https://docs.spring.io/spring-data/neo4j/reference/faq.html#custom-queries)
- [Spring Data Neo4j – Projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Neo4j Graph Data Science – Running algorithms](https://neo4j.com/docs/graph-data-science/current/common-usage/running-algos/)
- [Neo4j Graph Data Science – Utility functions](https://neo4j.com/docs/graph-data-science/current/management-ops/utility-functions/)
- [Neo4j Graph Data Science – PageRank](https://neo4j.com/docs/graph-data-science/current/algorithms/page-rank/)
