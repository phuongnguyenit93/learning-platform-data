# fetch, one, first, all và quy ước số lượng kết quả

`Neo4jClient` cung cấp API fluent để gửi Cypher, bind tham số và lấy kết quả. Sau khi khai báo truy vấn, ứng dụng chọn cách kết thúc bằng `fetch().one()`, `fetch().first()`, `fetch().all()` hoặc `run()`. Mỗi lựa chọn thể hiện kỳ vọng khác nhau về số record mà truy vấn trả về.

Chọn đúng terminal operation giúp code thể hiện rõ hợp đồng dữ liệu: cần đúng một kết quả, lấy một kết quả đầu tiên, lấy toàn bộ danh sách hay chỉ thực thi lệnh mà không đọc record. Đặc biệt, `one()` kiểm tra cardinality và báo lỗi nếu có nhiều hơn một record; `first()` chấp nhận nhiều record nhưng chỉ trả record đầu tiên.

## 1. Luồng gọi Neo4jClient

Một truy vấn imperative thường có các bước:

1. Gọi `neo4jClient.query(...)` để khai báo Cypher.
2. Bind các named parameter bằng `.bind(value).to("name")`.
3. Chọn kiểu kết quả bằng `fetch()` hoặc `fetchAs(...)`.
4. Chọn cách lấy kết quả bằng `one()`, `first()`, `all()` hoặc dùng `run()` nếu không cần record.

Ví dụ tối giản:

```java
Optional<Map<String, Object>> result = neo4jClient
        .query("MATCH (p:Person {email: $email}) RETURN p.name AS name")
        .bind(email).to("email")
        .fetch()
        .one();
```

`fetch()` ánh xạ mỗi record thành `Map<String, Object>`, trong đó key là alias trong mệnh đề `RETURN`. `one()` là bước thực thi và lấy kết quả theo quy ước một record. Với imperative `Neo4jClient`, kết quả được trả về ngay dưới dạng `Optional` hoặc `Collection`.

## 2. fetch(): lấy record dưới dạng Map

`fetch()` là lựa chọn đơn giản khi không cần map trực tiếp sang một class Java riêng. Mỗi record trở thành một map có key tương ứng với các biểu thức được trả về:

```java
Collection<Map<String, Object>> people = neo4jClient
        .query("""
            MATCH (p:Person)
            RETURN p.personId AS personId,
                   p.name AS name,
                   p.active AS active
            ORDER BY p.name
            """)
        .fetch()
        .all();
```

Map có các key `personId`, `name` và `active`. Alias trong `RETURN` là một phần của hợp đồng giữa Cypher và Java; nếu đổi alias, code đọc map cũng cần đổi theo.

Đọc một field từ map:

```java
Optional<Map<String, Object>> person = neo4jClient
        .query("MATCH (p:Person {personId: $id}) RETURN p.name AS name")
        .bind(personId).to("id")
        .fetch()
        .one();

String name = person
        .map(row -> (String) row.get("name"))
        .orElse(null);
```

Giá trị trong map là kiểu Java được Neo4j Driver chuyển đổi từ giá trị trong record. Hãy kiểm tra kiểu dữ liệu và khả năng null trước khi ép kiểu trong các truy vấn có `OPTIONAL MATCH` hoặc property tùy chọn.

## 3. one(): kỳ vọng tối đa một record

`one()` phù hợp khi truy vấn được thiết kế để trả về không quá một record, ví dụ tìm theo một khóa duy nhất hoặc tính một giá trị tổng hợp. Kết quả imperative là `Optional<T>`:

```java
Optional<Map<String, Object>> person = neo4jClient
        .query("""
            MATCH (p:Person {personId: $personId})
            RETURN p.personId AS personId, p.name AS name
            """)
        .bind(personId).to("personId")
        .fetch()
        .one();
```

Quy ước của `one()`:

- Không có record: trả về `Optional.empty()`.
- Có đúng một record: trả về `Optional.of(record)`.
- Có nhiều hơn một record: ném lỗi kích thước kết quả, thường được biểu diễn qua `IncorrectResultSizeDataAccessException`.

Vì vậy, `one()` không có nghĩa là “lấy đại một record”. Nó kiểm tra rằng kết quả truy vấn phù hợp với kỳ vọng một record. Đây là lựa chọn hữu ích để phát hiện truy vấn tưởng là duy nhất nhưng thực tế khớp nhiều node hoặc relationship.

### Dùng one() với phép tổng hợp

Truy vấn `count()` không có `GROUP BY` thường trả về một record kể cả khi không có node nào khớp:

```java
long count = neo4jClient
        .query("MATCH (p:Person {city: $city}) RETURN count(p) AS total")
        .bind(city).to("city")
        .fetchAs(Long.class)
        .mappedBy((typeSystem, record) -> record.get("total").asLong())
        .one()
        .orElse(0L);
```

Ở đây, `count(p)` trả về một giá trị số, ví dụ `0`, nên `one()` phù hợp. Cần phân biệt “không có record” với “có một record mang giá trị 0”: chúng là hai tình huống khác nhau.

Không thêm `LIMIT 1` chỉ để làm cho `one()` không báo lỗi khi truy vấn lẽ ra phải duy nhất. Làm như vậy che mất dữ liệu trùng hoặc điều kiện `MATCH` chưa đủ chặt. Nếu nghiệp vụ yêu cầu một node duy nhất, hãy bảo vệ khóa bằng uniqueness constraint và giữ `one()` để kiểm tra cardinality.

## 4. first(): lấy record đầu tiên nếu có

`first()` phù hợp khi truy vấn có thể trả về nhiều record nhưng use case chỉ cần một record đầu tiên. Kết quả imperative cũng là `Optional<T>`:

```java
Optional<Map<String, Object>> newestOrder = neo4jClient
        .query("""
            MATCH (o:PurchaseOrder {customerId: $customerId})
            RETURN o.orderId AS orderId,
                   o.createdAt AS createdAt
            ORDER BY o.createdAt DESC, o.orderId ASC
            """)
        .bind(customerId).to("customerId")
        .fetch()
        .first();
```

Quy ước của `first()`:

- Không có record: trả về `Optional.empty()`.
- Có một hoặc nhiều record: trả về record đầu tiên.
- Các record còn lại không được đưa vào kết quả trả về.

Hãy dùng `ORDER BY` khi “đầu tiên” có ý nghĩa nghiệp vụ như mới nhất, rẻ nhất hoặc ưu tiên cao nhất. Nếu không có thứ tự rõ ràng, Neo4j không bảo đảm record nào sẽ đứng đầu giữa các lần thực thi.

Khi muốn giới hạn số record được tạo và trả từ phía truy vấn, có thể thêm `LIMIT 1`:

```cypher
MATCH (o:PurchaseOrder {customerId: $customerId})
RETURN o.orderId AS orderId, o.createdAt AS createdAt
ORDER BY o.createdAt DESC, o.orderId ASC
LIMIT 1
```

`first()` chọn record đầu tiên của kết quả; `LIMIT 1` giới hạn tập kết quả ngay trong Cypher. Với truy vấn có thể tạo rất nhiều record, giới hạn trong Cypher giúp thể hiện rõ phạm vi kết quả mong muốn và hỗ trợ kiểm soát công việc database.

## 5. all(): lấy toàn bộ record

`all()` dùng khi ứng dụng thực sự cần toàn bộ kết quả của truy vấn:

```java
Collection<Map<String, Object>> activePeople = neo4jClient
        .query("""
            MATCH (p:Person {active: true})
            RETURN p.personId AS personId, p.name AS name
            ORDER BY p.name
            """)
        .fetch()
        .all();
```

Với imperative client, `all()` trả về `Collection<T>`. Collection chứa tất cả record do truy vấn trả về. Nếu kết quả lớn, việc giữ toàn bộ collection trong bộ nhớ có thể làm tăng heap và thời gian xử lý.

Để kiểm soát số lượng, hãy cân nhắc:

1. Lọc bằng điều kiện có tính chọn lọc.
2. Chỉ `RETURN` các field cần thiết.
3. Dùng `ORDER BY` cùng `SKIP`/`LIMIT` hoặc chiến lược phân trang phù hợp.
4. Xử lý theo từng lô thay vì gom toàn bộ graph vào một collection lớn.
5. Đo thời gian và lượng dữ liệu thực tế bằng `PROFILE` cùng metric ứng dụng.

Không dùng `all()` chỉ vì muốn “đọc cho chắc”. Nếu use case cần đúng một kết quả, dùng `one()`; nếu chỉ cần kết quả đứng đầu, dùng `first()`.

## 6. So sánh one(), first() và all()

| Phương thức | Số record kỳ vọng | Kiểu trả về imperative | Hành vi khi có nhiều record |
|---|---|---|---|
| `one()` | Không quá một record | `Optional<T>` | Ném lỗi kích thước kết quả |
| `first()` | Một record đầu tiên nếu có | `Optional<T>` | Chỉ trả record đầu tiên |
| `all()` | Không giới hạn số record theo hợp đồng | `Collection<T>` | Trả tất cả record |

Ví dụ nếu cùng một truy vấn trả về 3 người:

- `one()` báo lỗi vì có nhiều hơn một record.
- `first()` trả về người ở dòng đầu tiên của kết quả.
- `all()` trả về cả 3 người.

Nếu truy vấn không trả về record nào, `one()` và `first()` đều trả `Optional.empty()`, còn `all()` trả collection rỗng.

## 7. fetchAs(): ánh xạ mỗi record thành kiểu Java

Khi không muốn xử lý `Map<String, Object>`, dùng `fetchAs(Target.class)` rồi cung cấp mapper bằng `mappedBy(...)`:

```java
public record PersonSummary(String personId, String name, Boolean active) {
}
```

```java
Optional<PersonSummary> person = neo4jClient
        .query("""
            MATCH (p:Person {personId: $personId})
            RETURN p.personId AS personId,
                   p.name AS name,
                   p.active AS active
            """)
        .bind(personId).to("personId")
        .fetchAs(PersonSummary.class)
        .mappedBy((typeSystem, record) -> {
            var activeValue = record.get("active");
            Boolean active = activeValue.isNull()
                    ? null
                    : activeValue.asBoolean();

            return new PersonSummary(
                    record.get("personId").asString(),
                    record.get("name").asString(),
                    active);
        })
        .one();
```

Mapper được gọi cho từng record. Sau khi xác định kiểu Java, vẫn phải chọn terminal operation phù hợp: `one()`, `first()` hoặc `all()`. `fetchAs()` quyết định cách ánh xạ record; nó không quyết định số record cần lấy.

## 8. run(): thực thi khi không cần record

Nếu Cypher chỉ ghi hoặc xóa dữ liệu và không có mệnh đề `RETURN`, dùng `run()` thay vì `fetch()`:

```java
import org.neo4j.driver.summary.ResultSummary;

ResultSummary summary = neo4jClient
        .query("""
            MATCH (p:Person {personId: $personId})
            SET p.active = false,
                p.updatedAt = datetime()
            """)
        .bind(personId).to("personId")
        .run();

long nodesCreated = summary.counters().nodesCreated();
long propertiesSet = summary.counters().propertiesSet();
```

`run()` thực thi truy vấn và trả `ResultSummary` của Neo4j Driver, bao gồm các counter như số node hoặc relationship tạo/xóa và số property được đặt. Nó phù hợp khi không cần ánh xạ record. Nếu truy vấn có `RETURN` và cần đọc kết quả, hãy dùng `fetch()` hoặc `fetchAs(...)`.

## 9. Quy tắc chọn terminal operation

Trước khi kết thúc một truy vấn Neo4jClient, hãy xác định hợp đồng số lượng:

| Câu hỏi của use case | Lựa chọn |
|---|---|
| Truy vấn phải trả về tối đa một record và cần phát hiện dữ liệu trùng? | `one()` |
| Có thể có nhiều record nhưng chỉ cần record đầu theo thứ tự nghiệp vụ? | `first()` và `ORDER BY` |
| Cần toàn bộ record phù hợp? | `all()` |
| Chỉ cần chạy lệnh ghi và xem summary counter? | `run()` |

Ví dụ tìm sản phẩm theo SKU duy nhất nên dùng `one()` và có uniqueness constraint cho SKU. Truy vấn lấy đơn hàng mới nhất của khách hàng nên dùng `first()` với thứ tự giảm dần theo thời gian và tiêu chí phụ ổn định. Truy vấn xuất danh sách sản phẩm trong một phạm vi nên dùng `all()` hoặc phân trang theo lô. Lệnh cập nhật trạng thái không trả record nên dùng `run()`.

## 10. Imperative và Reactive Neo4jClient

SDN có hai client riêng:

- `Neo4jClient` cho luồng imperative.
- `ReactiveNeo4jClient` cho luồng reactive.

Hai client có từ vựng API tương tự nhưng không tương thích kiểu với nhau. Với imperative client, `one()` và `first()` trả `Optional<T>`, còn `all()` trả `Collection<T>`. Với reactive client, các thao tác tương ứng trả publisher như `Mono<T>` hoặc `Flux<T>`.

Reactive query chỉ thực thi khi publisher được subscribe. Vì vậy, tạo một `Flux` hoặc `Mono` chưa đồng nghĩa truy vấn đã chạy. Publisher cũng không nên được subscribe nhiều lần tùy tiện nếu luồng nghiệp vụ yêu cầu một lần thực thi.

Không trộn imperative `Neo4jClient` với reactive repository/client trong cùng một luồng chỉ bằng cách đổi kiểu trả về. Hãy chọn mô hình đồng bộ hoặc reactive nhất quán với stack ứng dụng và transaction manager đang sử dụng.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `one()` cho truy vấn có thể trả nhiều dòng | Ném lỗi kích thước kết quả | Dùng `all()` hoặc `first()` theo yêu cầu nghiệp vụ |
| Dùng `first()` mà không có `ORDER BY` | Record đầu tiên không ổn định | Đặt thứ tự rõ ràng và thêm tiêu chí phụ khi cần |
| Thêm `LIMIT 1` để che lỗi dữ liệu trùng của `one()` | Không phát hiện vi phạm uniqueness | Giữ `one()` và bảo vệ khóa bằng constraint |
| Dùng `all()` cho tập kết quả rất lớn | Tốn bộ nhớ ứng dụng | Lọc, giới hạn hoặc xử lý theo lô |
| Dùng `fetch()` cho lệnh không trả record | Không thể hiện đúng mục đích thực thi | Dùng `run()` và đọc `ResultSummary` |
| Nhầm `fetchAs()` với giới hạn số dòng | Vẫn có thể nhận nhiều record | Chọn thêm `one()`, `first()` hoặc `all()` |
| Đọc alias không tồn tại trong Map/Record | Lỗi hoặc nhận giá trị null ngoài dự kiến | Đồng bộ alias trong `RETURN` với code mapping |
| Gọi `asBoolean()` hoặc `asLong()` khi value null | Lỗi chuyển đổi runtime | Kiểm tra `Value.isNull()` trước |
| Nghĩ reactive query chạy ngay khi tạo publisher | Không thấy thao tác database xảy ra | Subscribe đúng một lần ở điểm tiêu thụ publisher |

## 12. Bài tập thực hành

Tạo một số node `Person`:

```cypher
CREATE
  (:Person {personId: 'P-01', name: 'Lan', city: 'Da Nang', active: true}),
  (:Person {personId: 'P-02', name: 'Minh', city: 'Da Nang', active: true}),
  (:Person {personId: 'P-03', name: 'Hoa', city: 'Hue', active: false});
```

Thực hiện các yêu cầu:

1. Dùng `fetch().one()` tìm một người theo `personId` và kiểm tra trường hợp không tìm thấy.
2. Bỏ điều kiện định danh để truy vấn có nhiều record; quan sát lỗi khi dùng `one()`.
3. Dùng `fetch().first()` với `ORDER BY name` để lấy người đầu tiên theo tên.
4. Dùng `fetch().all()` để lấy toàn bộ người đang active và đếm số phần tử trong collection.
5. Dùng `fetchAs(PersonSummary.class).mappedBy(...)` để ánh xạ record thành DTO.
6. Chạy một truy vấn `SET` không có `RETURN` bằng `run()` và đọc `ResultSummary.counters()`.
7. So sánh kết quả khi truy vấn không có record, có một record và có nhiều record.

Sau bài tập, hãy giải thích được vì sao `one()` phát hiện kết quả trùng, vì sao `first()` cần thứ tự xác định, khi nào `all()` có thể tốn bộ nhớ và khi nào nên dùng `run()`.

## Kết luận

Với imperative `Neo4jClient`, `fetch()` lấy record dưới dạng map, còn `fetchAs(...).mappedBy(...)` cho phép ánh xạ từng record sang kiểu Java. `one()` yêu cầu không quá một record và báo lỗi khi có nhiều hơn một; `first()` trả record đầu tiên nếu có; `all()` trả toàn bộ record; `run()` thực thi lệnh không cần record và trả summary. Hãy chọn terminal operation theo hợp đồng số lượng của use case, dùng `ORDER BY` khi cần record đầu tiên có ý nghĩa xác định và giới hạn dữ liệu khi lấy collection lớn.
