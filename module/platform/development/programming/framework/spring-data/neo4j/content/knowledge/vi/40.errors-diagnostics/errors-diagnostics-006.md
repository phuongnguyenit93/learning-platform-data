# Không có kết quả, nhiều kết quả hoặc record thiếu dữ liệu để ánh xạ

Khi một truy vấn Spring Data Neo4j (SDN) không trả về dữ liệu như mong đợi, cần phân biệt ba tình huống: Cypher không tạo ra record nào, Cypher tạo nhiều record trong khi Java chỉ chấp nhận một kết quả, hoặc record có tồn tại nhưng thiếu cột hay giá trị để mapper tạo object. Ba tình huống này có nguyên nhân và cách sửa khác nhau.

Một lỗi thường gặp là nhìn thấy `null` rồi kết luận truy vấn không tìm thấy node. Trong Neo4j, một record có thể tồn tại nhưng một property hoặc một phần của `OPTIONAL MATCH` có giá trị `null`. Ngược lại, một truy vấn có thể trả nhiều hàng do một node nối với nhiều relationship, dù ứng dụng chỉ muốn một object. Muốn chẩn đoán đúng, hãy kiểm tra số record, tên cột trả về, kiểu dữ liệu và nullability trước khi thay đổi repository hoặc DTO.

## 1. Phân biệt cardinality và dữ liệu trong record

Kết quả Cypher là một luồng record. Mỗi record có một tập cột (keys) và giá trị tương ứng. Không có record, có một record chứa `null`, và có nhiều record là ba trạng thái khác nhau:

| Tình huống | Ví dụ | Ý nghĩa |
|---|---|---|
| Không có record | `MATCH (p:Person {personId: $id}) RETURN p` không tìm thấy Person | Không có hàng dữ liệu nào đi đến `RETURN` |
| Có record, cột có giá trị null | Person tồn tại nhưng không có `email`; hoặc `OPTIONAL MATCH` không tìm thấy Company | Record vẫn tồn tại, một field có giá trị `null` |
| Có nhiều record | Một Person có ba relationship `WORKS_AT` hoặc query match ba đường đi | Một truy vấn tạo ra ba hàng kết quả |
| Có record nhưng thiếu cột | Query trả `p.name AS fullName` trong khi mapper đọc `name` | Hợp đồng giữa Cypher và mapper không khớp |
| Có cột nhưng sai kiểu | `RETURN p.age AS age` trả số nhưng mapper gọi `asString()` | Cột tồn tại nhưng không chuyển được sang kiểu Java yêu cầu |

Trước khi debug code Java, chạy đúng Cypher cùng tham số trong Neo4j Browser hoặc công cụ truy vấn để xác nhận số hàng và tên cột. Đừng chỉ kiểm tra node có tồn tại bằng một query khác, vì query ứng dụng có thể có thêm `MATCH`, `WHERE`, relationship pattern hoặc `WITH` làm thay đổi cardinality.

## 2. Vì sao MATCH có thể trả về không record?

Các clause Cypher truyền kết quả trung gian từ clause này sang clause tiếp theo. Nếu một `MATCH` không tìm được pattern bắt buộc, nó không truyền hàng nào sang clause tiếp theo. Vì vậy `RETURN` phía sau không được thực thi với dữ liệu đầu vào nào.

Ví dụ:

```cypher
MATCH (p:Person {personId: $personId})
MATCH (p)-[:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       c.name AS companyName;
```

Query chỉ trả hàng khi cả Person và relationship `WORKS_AT` cùng Company đều tồn tại. Nếu Person tồn tại nhưng chưa có công ty, kết quả vẫn là zero records.

Kiểm tra từng bước bằng cách tạm thời giảm pattern:

```cypher
MATCH (p:Person {personId: $personId})
RETURN p.personId AS personId,
       p.name AS name;
```

Nếu query này trả một hàng, tiếp tục thêm relationship pattern để xác định clause nào loại bỏ dữ liệu. Có thể dùng `count(*)` để kiểm tra số hàng sau từng phần của query.

### Dùng OPTIONAL MATCH khi relationship không bắt buộc

Nếu Person vẫn phải xuất hiện ngay cả khi chưa có Company, dùng `OPTIONAL MATCH`:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
RETURN p.personId AS personId,
       p.name AS name,
       c.name AS companyName;
```

Khi Person tồn tại nhưng không có Company, query trả một record; `personId` và `name` có giá trị, `companyName` là `null`. Khi Person không tồn tại, query vẫn không trả record vì `MATCH` đầu tiên là bắt buộc.

`OPTIONAL MATCH` là lựa chọn tương tự outer join: phần pattern không khớp được biểu diễn bằng `null`, giúp các hàng từ phần bắt buộc tiếp tục đi qua pipeline.

### Đặt WHERE đúng vị trí với OPTIONAL MATCH

`WHERE` đặt ngay sau `OPTIONAL MATCH` là một phần điều kiện của pattern tùy chọn:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
WHERE c.active = true
RETURN p.personId AS personId,
       c.name AS companyName;
```

Nếu không có Company active, Person vẫn được trả về với `companyName = null`. Nếu chuyển điều kiện sang một `WITH` sau đó, hàng null có thể bị loại:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:WORKS_AT]->(c:Company)
WITH p, c
WHERE c.active = true
RETURN p.personId AS personId,
       c.name AS companyName;
```

Trong query thứ hai, `c.active = true` không đúng khi `c` là null; hàng bị loại và kết quả trở thành zero records. Khi chẩn đoán một kết quả rỗng bất ngờ, kiểm tra cả vị trí của `WHERE`.

## 3. Phân biệt không có record với property null

Neo4j cho phép node và relationship không có cùng một tập property. Trả về một property không tồn tại sẽ tạo giá trị `null` trong record:

```cypher
MATCH (p:Person {personId: $personId})
RETURN p.personId AS personId,
       p.email AS email;
```

Nếu Person có tồn tại nhưng chưa có property `email`, query vẫn trả một record và `email` là `null`. Property không tồn tại không làm mất cả record.

Trong Cypher, `null` biểu diễn giá trị thiếu hoặc chưa biết. Dùng `IS NULL` và `IS NOT NULL` để kiểm tra; không dùng `= null` hoặc `<> null` vì các phép so sánh đó cho ra `null`, không phải boolean như mong muốn:

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p.personId AS personId;
```

Có thể dùng `coalesce()` để chọn giá trị mặc định:

```cypher
MATCH (p:Person {personId: $personId})
RETURN p.personId AS personId,
       coalesce(p.email, 'CHUA_CAP_NHAT') AS email;
```

Chỉ dùng fallback khi nghiệp vụ chấp nhận thay thế giá trị thiếu. Nếu cần phân biệt email chưa nhập với email đã được đặt thành chuỗi mặc định, hãy trả thêm cờ hoặc giữ `null` trong kết quả.

Lưu ý: Neo4j không lưu property có giá trị null. Gán `null` cho property bằng `SET` sẽ xóa property đó. Do đó, property không tồn tại và property có giá trị null được biểu diễn như cùng một trạng thái khi đọc từ graph.

## 4. Vì sao một node có thể tạo nhiều record?

Một node có thể khớp nhiều relationship hoặc nhiều đường đi. Mỗi tổ hợp pattern phù hợp có thể tạo một hàng kết quả.

Ví dụ:

```cypher
MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person)
RETURN p.personId AS personId,
       friend.personId AS friendId;
```

Nếu Person có bốn người quen, query trả bốn record. Nếu repository khai báo phương thức trả về `Optional<Person>` hoặc `Person`, nhưng custom query trả nhiều record, SDN sẽ báo `IncorrectResultSizeDataAccessException` vì hợp đồng Java yêu cầu tối đa một kết quả.

Đây không nhất thiết là dữ liệu trùng. Nó có thể là cardinality đúng của graph nhưng không phù hợp kiểu trả về của method.

### Dùng DISTINCT khi thực sự muốn loại record trùng

Nếu nhiều đường đi đưa cùng một node vào kết quả và ứng dụng chỉ cần node duy nhất:

```cypher
MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person)
RETURN DISTINCT friend.personId AS friendId,
                friend.name AS friendName
ORDER BY friendId;
```

`DISTINCT` áp dụng lên toàn bộ tập biểu thức được `RETURN`. Nếu hai record có cùng `friendId` nhưng `friendName` khác nhau, chúng vẫn là hai record khác nhau. Hãy chọn đúng cột cần phân biệt.

Nếu cần một Person duy nhất và không cần thông tin relationship, có thể trả root node:

```cypher
MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person)
RETURN DISTINCT friend;
```

### Gom nhiều hàng thành một record bằng collect

Nếu mục tiêu là một Person cùng danh sách bạn bè, dùng aggregation:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
RETURN p.personId AS personId,
       p.name AS name,
       collect(DISTINCT friend.personId) AS friendIds,
       count(DISTINCT friend) AS friendCount;
```

Khi Person tồn tại nhưng không có bạn bè, aggregation vẫn trả một record: `friendIds` là list rỗng và `friendCount` là 0. Nếu Person không tồn tại, `MATCH` bắt buộc vẫn trả zero records.

Không dùng `first()` hoặc `LIMIT 1` để che giấu nhiều kết quả khi nghiệp vụ thật sự cần tất cả bạn bè. Hãy chọn một trong ba cách theo yêu cầu: trả collection, loại trùng có chủ ý hoặc gom thành một record.

## 5. Nhiều MATCH có thể nhân số hàng ngoài dự kiến

Khi một Person có nhiều bạn bè và nhiều sở thích, hai pattern độc lập có thể tạo tích Descartes giữa các kết quả. Ví dụ:

```cypher
MATCH (p:Person {personId: $personId})-[:KNOWS]->(friend:Person)
MATCH (p)-[:LIKES]->(topic:Topic)
RETURN p.personId AS personId,
       count(friend) AS friendCount,
       count(topic) AS topicCount;
```

Nếu có 3 bạn bè và 4 topic, phần trung gian có thể chứa 12 hàng. `count(friend)` và `count(topic)` có thể đều ra 12 thay vì 3 và 4.

Với query đơn giản, dùng `count(DISTINCT ...)`:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
OPTIONAL MATCH (p)-[:LIKES]->(topic:Topic)
RETURN p.personId AS personId,
       count(DISTINCT friend) AS friendCount,
       count(DISTINCT topic) AS topicCount;
```

Khi mỗi nhánh có logic phức tạp, dùng subquery để tính riêng từng thống kê rồi ghép lại:

```cypher
MATCH (p:Person {personId: $personId})
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
    RETURN count(DISTINCT friend) AS friendCount
}
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:LIKES]->(topic:Topic)
    RETURN count(DISTINCT topic) AS topicCount
}
RETURN p.personId AS personId,
       friendCount,
       topicCount;
```

Hai subquery trả một hàng tổng hợp cho mỗi `p`, nhờ đó tránh nhân số hàng giữa các nhánh. Đây là cách tốt khi cần nhiều thống kê độc lập từ cùng một root node.

## 6. Chọn kiểu trả về repository theo số kết quả

Kiểu trả về của repository là một phần hợp đồng cardinality. Chọn kiểu dựa trên số kết quả mà query được phép trả:

| Kiểu trả về | Không có record | Một record | Nhiều record |
|---|---|---|---|
| `Person` hoặc DTO đơn `T` | Trả `null` | Trả object | `IncorrectResultSizeDataAccessException` |
| `Optional<Person>` | `Optional.empty()` | `Optional.of(...)` | `IncorrectResultSizeDataAccessException` |
| `List<Person>` / `Collection<Person>` | Collection rỗng | Collection một phần tử | Collection chứa tất cả |
| Reactive `Mono<Person>` | `Mono.empty()` | Phát một object | `IncorrectResultSizeDataAccessException` |
| Reactive `Flux<Person>` | `Flux.empty()` | Phát một object | Phát nhiều object |

Ví dụ repository:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    Optional<Person> findByPersonId(String personId);

    List<Person> findAllByName(String name);
}
```

`findByPersonId` với kiểu trả về `Optional<Person>` thể hiện kỳ vọng một người tối đa. Nếu `personId` là business key, nên có uniqueness constraint tương ứng để bảo vệ dữ liệu ở database. `findAllByName` thể hiện rõ tên có thể trùng và method chấp nhận nhiều kết quả.

Với reactive repository, chọn `Mono<T>` cho zero-or-one và `Flux<T>` cho zero-to-many. Không dùng `Mono<T>` chỉ vì caller muốn một object nếu query thực tế có thể trả nhiều; hãy sửa query hoặc dùng `Flux`/collection.

## 7. Neo4jClient: one(), first() và all()

`Neo4jClient` cung cấp ba cách lấy record sau khi định nghĩa mapping:

DTO dùng trong ví dụ:

```java
public record PersonNameView(String personId, String name) {
}
```

```java
var fetch = neo4jClient.query("""
        MATCH (p:Person {personId: $personId})
        RETURN p.personId AS personId,
               p.name AS name
        """)
        .bind(personId).to("personId")
        .fetchAs(PersonNameView.class)
        .mappedBy((typeSystem, record) -> new PersonNameView(
                record.get("personId").asString(),
                record.get("name").asString()));
```

Sau đó chọn cách đọc:

```java
Optional<PersonNameView> optional = fetch.one();
Optional<PersonNameView> first = fetch.first();
Collection<PersonNameView> all = fetch.all();
```

Mỗi terminal method thực thi việc fetch theo cardinality tương ứng; khi thử cả ba trong một test, mỗi lời gọi sẽ chạy query để quan sát hành vi riêng.

- `one()` trả `Optional` chứa đúng một record hoặc empty nếu không có record; nếu có hơn một record thì ném exception.
- `first()` chỉ lấy record đầu tiên; nếu không có record thì trả empty. Nếu query có thể trả nhiều hàng, hãy dùng `ORDER BY` để xác định thứ tự hoặc `LIMIT 1` nếu nghiệp vụ thực sự chỉ cần một hàng.
- `all()` lấy tất cả record thành collection; phù hợp khi cardinality là zero-to-many và kết quả đủ nhỏ để materialize.

`first()` không phải cách sửa lỗi cardinality. Nếu query đáng lẽ chỉ có một người nhưng trả nhiều người vì thiếu uniqueness constraint hoặc điều kiện `WHERE`, lấy record đầu tiên sẽ che giấu lỗi dữ liệu. Chỉ dùng khi việc chọn một kết quả đầu tiên là quy tắc nghiệp vụ rõ ràng.

Với `ReactiveNeo4jClient`, các method tương ứng trả `Mono<T>` cho `one()`/`first()` và `Flux<T>` cho `all()`:

```java
Mono<PersonNameView> one = reactiveNeo4jClient.query(CYPHER)
        .bind(personId).to("personId")
        .fetchAs(PersonNameView.class)
        .mappedBy((typeSystem, record) -> new PersonNameView(
                record.get("personId").asString(),
                record.get("name").asString()))
        .one();

Flux<PersonNameView> many = reactiveNeo4jClient.query(CYPHER)
        .bind(personId).to("personId")
        .fetchAs(PersonNameView.class)
        .mappedBy((typeSystem, record) -> new PersonNameView(
                record.get("personId").asString(),
                record.get("name").asString()))
        .all();
```

Reactive query chỉ thực thi khi publisher được subscribe. Hãy xử lý `Mono.empty()` bằng `switchIfEmpty(...)` khi nghiệp vụ cần phản hồi cụ thể cho trường hợp không tìm thấy.

## 8. Record thiếu cột khác với cột có giá trị null

Trong custom mapping, mapper nhận `Record` từ Neo4j Java Driver. Cần phân biệt:

- Cột không có trong record: alias Cypher không đúng hoặc query không `RETURN` field đó. `record.containsKey("name")` trả false; gọi `record.get("name")` sẽ không thể đọc cột như mong muốn.
- Cột có trong record nhưng giá trị null: key tồn tại, `record.get("name").isNull()` trả true.
- Cột có giá trị nhưng sai kiểu: key tồn tại và không null, nhưng `asString()`, `asLong()` hoặc converter không thể chuyển kiểu đó.

Ví dụ mapper phòng vệ:

```java
import org.neo4j.driver.Record;
import org.neo4j.driver.Value;

private static String requiredString(Record record, String key) {
    if (!record.containsKey(key)) {
        throw new IllegalStateException(
                "Cypher result is missing required column: " + key);
    }

    Value value = record.get(key);
    if (value.isNull()) {
        throw new IllegalStateException(
                "Required column is null: " + key);
    }

    return value.asString();
}

private static String nullableString(Record record, String key) {
    if (!record.containsKey(key)) {
        throw new IllegalStateException(
                "Cypher result is missing expected column: " + key);
    }

    return record.get(key).asString(null);
}
```

`requiredString` báo lỗi riêng khi cột không có hoặc giá trị null; nếu giá trị không phải string, Driver sẽ báo lỗi chuyển đổi kiểu. `nullableString` cho phép cột có giá trị null nhưng vẫn coi alias bị thiếu là lỗi hợp đồng query.

Không nên trả `null` cho mọi trường hợp mapper gặp lỗi. Làm như vậy khiến alias bị viết sai, dữ liệu bị thiếu và type mismatch trông giống nhau, khó truy tìm nguyên nhân.

## 9. Alias trong RETURN là hợp đồng với mapper

Cypher cho phép đổi tên cột bằng `AS`. Mapper phải đọc đúng tên alias, bao gồm cách viết hoa/thường.

Query:

```cypher
MATCH (p:Person {personId: $personId})
RETURN p.personId AS personId,
       p.name AS displayName;
```

Mapper phải đọc `displayName`:

```java
PersonNameView summary = new PersonNameView(
        record.get("personId").asString(),
        record.get("displayName").asString());
```

Nếu mapper vẫn đọc `name`, record không có key đó. Cách sửa là thống nhất alias và mapper; không cần đổi dữ liệu graph.

Nên dùng alias rõ ràng cho mọi biểu thức trong custom query:

```cypher
RETURN p.personId AS personId,
       p.name AS name,
       count(DISTINCT friend) AS friendCount;
```

Tránh dựa vào tên biểu thức tự sinh như `p.name`, `count(friend)` hoặc `properties(p)` trong DTO. Không dùng `RETURN *` cho contract API ổn định vì việc thêm biến vào query có thể làm thay đổi record shape.

## 10. Xử lý kiểu dữ liệu không khớp

Neo4j Java Driver bọc mỗi giá trị trong `Value`. Mapper cần chuyển theo kiểu Cypher thực tế:

| Kiểu Cypher | Cách đọc thường dùng |
|---|---|
| `STRING` | `asString()` |
| `INTEGER` | `asLong()` hoặc `asInt()` nếu không mất độ chính xác |
| `FLOAT` | `asDouble()` |
| `BOOLEAN` | `asBoolean()` |
| `LIST` | `asList(...)` |
| `MAP` | `asMap(...)` hoặc map từng field |
| `DATE`, `LOCAL DATETIME`, `ZONED DATETIME` | Dùng converter/type tương ứng của Driver và SDN |

Ví dụ nếu `age` được lưu là số nguyên:

```cypher
MATCH (p:Person {personId: $personId})
RETURN p.personId AS personId,
       p.age AS age;
```

Đọc bằng:

```java
long age = record.get("age").asLong();
```

Nếu property có thể thiếu, kiểm tra null trước hoặc dùng overload có giá trị mặc định:

```java
long age = record.get("age").asLong(-1L);
```

Chỉ dùng `-1` nếu đó là sentinel được nghiệp vụ chấp nhận. Nếu cần phân biệt không có tuổi với tuổi bằng 0, dùng `Long` nullable thay vì primitive `long`.

Không chuyển mọi giá trị thành `toString()` để né lỗi kiểu. Ví dụ số `42` thành chuỗi `"42"` có thể làm API mất hợp đồng kiểu và khiến lỗi dữ liệu bị che khuất.

## 11. Một query hoàn chỉnh xử lý cả zero, optional field và cardinality

Giả sử API cần trả một bản tóm tắt Person gồm `personId`, `name`, danh sách tên công ty và số bạn bè. Một Person có thể chưa có công ty hoặc chưa có bạn bè. Query cần trả đúng một record nếu Person tồn tại:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:WORKS_AT]->(company:Company)
WITH p, collect(DISTINCT company.name) AS companyNames
OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
RETURN p.personId AS personId,
       p.name AS name,
       companyNames AS companyNames,
       count(DISTINCT friend) AS friendCount;
```

DTO:

```java
import java.util.List;

public record PersonSummary(
        String personId,
        String name,
        List<String> companyNames,
        long friendCount) {
}
```

Mapper minh họa:

```java
import java.util.List;
import java.util.Optional;

import org.neo4j.driver.Record;
import org.neo4j.driver.Value;
import org.springframework.data.neo4j.core.Neo4jClient;

private static final String PERSON_SUMMARY_QUERY = """
        MATCH (p:Person {personId: $personId})
        OPTIONAL MATCH (p)-[:WORKS_AT]->(company:Company)
        WITH p, collect(DISTINCT company.name) AS companyNames
        OPTIONAL MATCH (p)-[:KNOWS]->(friend:Person)
        RETURN p.personId AS personId,
               p.name AS name,
               companyNames AS companyNames,
               count(DISTINCT friend) AS friendCount
        """;

public Optional<PersonSummary> findSummary(String personId) {
    return neo4jClient.query(PERSON_SUMMARY_QUERY)
            .bind(personId).to("personId")
            .fetchAs(PersonSummary.class)
            .mappedBy((typeSystem, record) -> {
                String id = requiredString(record, "personId");
                String name = requiredString(record, "name");
                Value companyNamesValue = record.get("companyNames");

                List<String> companyNames = companyNamesValue.isNull()
                        ? List.of()
                        : companyNamesValue.asList(Value::asString);

                long friendCount = record.get("friendCount").asLong();
                return new PersonSummary(id, name, companyNames, friendCount);
            })
            .one();
}
```

Method trên trả `Optional.empty()` nếu Person không tồn tại. Nếu Person tồn tại nhưng không có Company hoặc Friend, nó vẫn trả một DTO với `companyNames` rỗng và `friendCount = 0`. Nếu query vô tình tạo nhiều record cho cùng Person, `one()` báo lỗi thay vì âm thầm chọn một hàng.

Trong code thực tế, hãy kiểm tra `companyNames` và `friendCount` có key trước khi đọc như ở mục trước, hoặc bảo đảm query luôn trả các alias đó. Đây là các cột bắt buộc của hợp đồng DTO dù collection có thể rỗng.

## 12. Chẩn đoán theo thứ tự

Khi kết quả không đúng, làm theo trình tự sau:

1. **Chạy query trực tiếp:** dùng đúng tham số ứng dụng đã bind và đếm số record.
2. **Kiểm tra pattern bắt buộc:** xác định `MATCH` nào có thể loại hết hàng; thay bằng `OPTIONAL MATCH` nếu pattern thực sự tùy chọn.
3. **Kiểm tra WHERE:** xác nhận điều kiện thuộc `MATCH` nào và có đang loại hàng null ngoài ý muốn không.
4. **Kiểm tra fan-out:** đếm số relationship/path khớp; kiểm tra có nhiều hàng do nhiều cạnh hay nhiều nhánh MATCH không.
5. **Kiểm tra alias:** đối chiếu `RETURN ... AS ...` với `record.keys()` hoặc `record.containsKey(...)`.
6. **Kiểm tra null:** dùng `IS NULL`, `IS NOT NULL` trong Cypher và `Value.isNull()` trong Java.
7. **Kiểm tra kiểu:** đối chiếu kiểu Cypher với `asString()`, `asLong()`, `asDouble()` hoặc converter.
8. **Kiểm tra kiểu trả về:** `Optional`/`Mono` cho zero-or-one; `List`/`Flux` cho zero-to-many.
9. **Kiểm tra uniqueness:** nếu nghiệp vụ yêu cầu một node, xác minh khóa có uniqueness constraint và query dùng đúng khóa.
10. **Viết integration test:** bao phủ zero, one, many, optional null và alias/type mismatch để lỗi không quay lại.

Không sửa bằng cách thêm `LIMIT 1` trước khi xác định nhiều record là hợp lệ hay bất thường. Nếu dữ liệu sai, cần sửa constraint hoặc logic query. Nếu nhiều record là đúng, hãy đổi kiểu trả về hoặc gom dữ liệu.

## 13. Kiểm thử các trường hợp biên

Integration test nên có fixture cho ít nhất năm trường hợp:

| Fixture | Kết quả mong đợi |
|---|---|
| Không có Person theo ID | `Optional.empty()` hoặc `Mono.empty()` |
| Có Person, không có Company | Một record, `companyNames` rỗng |
| Có Person, nhiều Friend | Một summary với `friendCount` chính xác hoặc nhiều record nếu query trả từng Friend |
| Query trả cùng root qua nhiều relationship | `DISTINCT` hoặc aggregation cho đúng cardinality đã thiết kế |
| Alias bắt buộc bị thiếu | Test mapping thất bại rõ ràng với tên cột thiếu |
| Property tùy chọn không tồn tại | Record tồn tại, field nullable/default theo hợp đồng |
| Property có kiểu sai | Mapping thất bại thay vì âm thầm chuyển chuỗi |

Ví dụ test repository cardinality:

```java
@Test
void returnsEmptyWhenPersonDoesNotExist() {
    assertThat(personRepository.findByPersonId("missing-id"))
            .isEmpty();
}

@Test
void returnsAllPeopleWhenNameIsNotUnique() {
    List<Person> people = personRepository.findAllByName("Alex");

    assertThat(people).hasSize(2);
}
```

Ví dụ test `Neo4jClient` phát hiện nhiều record:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.dao.IncorrectResultSizeDataAccessException;

@Test
void oneFailsWhenQueryReturnsMoreThanOneRecord() {
    assertThatThrownBy(() -> neo4jClient.query("""
            UNWIND [1, 2] AS value
            RETURN value AS value
            """)
            .fetchAs(Long.class)
            .mappedBy((typeSystem, record) -> record.get("value").asLong())
            .one())
            .isInstanceOf(IncorrectResultSizeDataAccessException.class);
}
```

Đây là ví dụ kiểm tra cardinality của `Neo4jClient.one()`. Khi viết test theo phiên bản SDN cụ thể, xác nhận exception được translate bởi lớp Spring đang gọi; nếu test trực tiếp một API Driver thuần, exception có thể là loại khác.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `MATCH` cho relationship tùy chọn | Person biến mất khi không có relationship | Dùng `OPTIONAL MATCH` |
| Đặt `WHERE` sau `WITH` làm loại hàng null | Query trả zero record ngoài ý muốn | Đặt điều kiện vào đúng `OPTIONAL MATCH` hoặc xử lý null rõ ràng |
| Dùng `Optional<T>` cho query trả nhiều hàng | `IncorrectResultSizeDataAccessException` | Trả `List<T>`/`Flux<T>` hoặc gom kết quả |
| Dùng `first()` để che nhiều record | Chọn kết quả tùy ý, che lỗi cardinality | Xác định quy tắc, thêm `ORDER BY`/`LIMIT` hoặc sửa query |
| Không phân biệt zero record và field null | Xử lý nghiệp vụ sai | Kiểm tra `Optional`/`Mono` và `Value.isNull()` riêng biệt |
| Mapper đọc alias không tồn tại | Lỗi đọc record hoặc mapping | Đồng bộ `RETURN AS` với key mapper |
| Mapper gọi `asString()` cho số | Lỗi chuyển đổi kiểu | Dùng accessor đúng kiểu hoặc sửa Cypher projection |
| Dùng `coalesce()` cho mọi field null | Che mất trạng thái dữ liệu thiếu | Chỉ dùng fallback khi nghiệp vụ định nghĩa rõ |
| Hai nhánh MATCH nhân số hàng | Count bị phóng đại và duplicate record | Dùng `count(DISTINCT ...)` hoặc subquery riêng |
| Query dùng `RETURN *` | Contract kết quả thay đổi khi query được mở rộng | Liệt kê alias tường minh |
| Chỉ test happy path có đủ relationship | Không phát hiện optional pattern hoặc property null | Test zero, many và missing-property fixtures |

## 15. Bài tập thực hành

Xây dựng API tóm tắt Person:

1. Tạo Person có `personId` duy nhất và property `name`.
2. Tạo một Person chưa có Company, một Person có một Company và một Person có hai Company.
3. Viết query `MATCH` bắt buộc cho Person và `OPTIONAL MATCH` cho Company.
4. Trả `companyNames` bằng `collect(DISTINCT ...)` để mỗi Person chỉ tạo một record.
5. Thêm `KNOWS` và kiểm tra `count(DISTINCT friend)` khi không có bạn bè và khi có nhiều bạn bè.
6. Viết repository method trả `Optional<Person>` và thử query cố ý tạo nhiều record để quan sát exception.
7. Viết method khác trả `List<Person>` hoặc `Flux<Person>` cho truy vấn zero-to-many.
8. Dùng `Neo4jClient.one()`, `first()` và `all()` với query có zero, one và many records.
9. Đổi alias `name` thành `displayName` nhưng giữ mapper cũ; quan sát lỗi rồi sửa hợp đồng.
10. Xóa property tùy chọn trong fixture và xác nhận mapper xử lý null đúng cách.
11. Thử trả `p.age` dưới kiểu số rồi cố đọc bằng `asString()` để hiểu type mismatch.
12. Viết integration test cho từng cardinality và trường hợp thiếu dữ liệu.

Sau bài tập, hãy giải thích được khác biệt giữa zero records và record có null, vì sao nhiều relationship tạo nhiều hàng, khi nào dùng `OPTIONAL MATCH`, cách chọn kiểu trả về và cách kiểm tra alias/type trong mapper.

## Kết luận

Kết quả rỗng, nhiều kết quả và record thiếu dữ liệu là ba vấn đề khác nhau. `MATCH` có thể loại hết hàng; `OPTIONAL MATCH` giữ hàng với phần thiếu là null. Một node nối nhiều relationship có thể tạo nhiều record; dùng collection, `DISTINCT` hoặc aggregation theo đúng mục tiêu. Chọn `Optional`/`Mono` cho zero-or-one và `List`/`Flux` cho zero-to-many. Với `Neo4jClient`, `one()`, `first()` và `all()` có semantics khác nhau. Trong mapper, kiểm tra key, null và kiểu dữ liệu riêng biệt; alias trong `RETURN` phải khớp với key Java đọc. Integration test cần bao phủ zero, one, many và property tùy chọn để lỗi được phát hiện trước khi lên production.

## Tài liệu tham khảo

- [Spring Data Neo4j – Repository Query Return Types](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-return-types-reference.html)
- [Spring Data Neo4j – Neo4jClient.RunnableSpec API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.RunnableSpec.html)
- [Spring Data Neo4j – Neo4jClient.RecordFetchSpec API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/core/Neo4jClient.RecordFetchSpec.html)
- [Neo4j Cypher Manual – OPTIONAL MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/)
- [Neo4j Cypher Manual – RETURN](https://neo4j.com/docs/cypher-manual/current/clauses/return/)
- [Neo4j Cypher Manual – Working with null](https://neo4j.com/docs/cypher-manual/current/values-and-types/working-with-null/)
- [Neo4j Java Driver – Value API](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/Value.html)
