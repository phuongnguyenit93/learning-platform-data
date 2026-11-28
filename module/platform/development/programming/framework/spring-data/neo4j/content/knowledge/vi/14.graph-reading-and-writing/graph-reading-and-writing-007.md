# Tải đồ thị theo quan hệ đã ánh xạ và nguy cơ đọc quá nhiều dữ liệu

Trong Spring Data Neo4j, một entity có thể chứa nhiều quan hệ được ánh xạ bằng `@Relationship`. Khi đọc entity, ứng dụng thường muốn lấy cả những node liên quan để hiển thị hoặc xử lý nghiệp vụ. Tuy nhiên, một node có thể kết nối với rất nhiều node khác, và các node đó lại tiếp tục có quan hệ riêng. Nếu tải quá sâu hoặc quá rộng, một thao tác tưởng như chỉ đọc một entity có thể kéo theo một phần rất lớn của đồ thị.

Vì vậy, thiết kế truy vấn đọc cần xác định rõ **cần tải node gốc nào, những relationship nào và đi sâu đến mức nào**. Spring Data Neo4j hỗ trợ ánh xạ dữ liệu theo mô hình entity; Cypher cho phép kiểm soát pattern được truy vấn; projection giúp chỉ trả về dữ liệu màn hình hoặc nghiệp vụ thực sự cần.

## 1. Entity graph được hình thành từ các quan hệ đã ánh xạ

Giả sử ứng dụng quản lý người và phim. Một người có thể tham gia nhiều phim, còn một phim có thể có nhiều người tham gia:

```text
(Person)-[:ACTED_IN]->(Movie)
```

Entity đơn giản có thể được khai báo như sau:

```java
@Node("Person")
public class Person {
    @Id
    private String personId;

    private String name;

    @Relationship(type = "ACTED_IN", direction = Relationship.Direction.OUTGOING)
    private List<Movie> movies = new ArrayList<>();
}

@Node("Movie")
public class Movie {
    @Id
    private String movieId;

    private String title;
}
```

`Person.movies` mô tả các node `Movie` được nối từ node `Person` qua relationship `ACTED_IN`. Khi Spring Data Neo4j ánh xạ một `Person`, quan hệ này là một phần của mô hình entity và có thể được nạp theo truy vấn đọc.

Giả sử mỗi phim còn được nối đến nhiều thể loại, và mỗi thể loại có nhiều phim:

```text
(Person)-[:ACTED_IN]->(Movie)-[:IN_CATEGORY]->(Category)
```

Nếu cần đọc cả người, phim và thể loại, dữ liệu cần lấy đã rộng hơn một cấp quan hệ. Nếu tiếp tục đi từ `Category` sang các phim khác rồi đến những người tham gia các phim đó, phạm vi có thể tăng rất nhanh.

## 2. Độ sâu tải và phạm vi dữ liệu

Độ sâu (depth) mô tả số bước relationship được đi từ node gốc khi nạp một entity graph. Ví dụ với chuỗi `Person → Movie → Category`:

| Độ sâu | Phạm vi minh họa |
|---|---|
| `0` | Chỉ node `Person` gốc |
| `1` | `Person` và các `Movie` nối trực tiếp |
| `2` | Thêm các `Category` nối với `Movie` |
| `3` | Có thể tiếp tục lấy các quan hệ tiếp theo từ `Category` |

Độ sâu thực tế còn phụ thuộc vào các quan hệ được khai báo trong entity, API đọc, truy vấn Cypher và phiên bản Spring Data Neo4j đang dùng. Không nên giả định mọi phương thức repository đều tải toàn bộ đồ thị hoặc mọi truy vấn tùy chỉnh đều tự mở rộng quan hệ theo cùng một quy tắc.

Với `Neo4jTemplate`, có thể chỉ định độ sâu khi đọc entity bằng API có tham số depth, ví dụ:

```java
Optional<Person> person = neo4jTemplate.findById(
    personId,
    Person.class,
    1
);
```

Ở đây, depth `1` yêu cầu tải node gốc cùng một cấp quan hệ theo mapping. Khi cần phạm vi khác, có thể chọn depth phù hợp với use case. Hãy kiểm tra API của phiên bản Spring Data Neo4j trong dự án để chọn overload tương ứng; cách cấu hình độ sâu có thể khác giữa các thế hệ thư viện.

Không nên tăng depth chỉ để “chắc chắn có đủ dữ liệu”. Mỗi cấp quan hệ có thể làm số node và relationship cần xử lý tăng lên đáng kể.

## 3. Vì sao tải quá nhiều dữ liệu nguy hiểm?

Một node có thể có nhiều quan hệ đi ra hoặc đi vào. Nếu trung bình mỗi node có `b` quan hệ phù hợp và truy vấn đi sâu `d` cấp, số phần tử có thể tăng theo cấp số nhân gần đúng:

\[
1 + b + b^2 + \dots + b^d
\]

Ví dụ, nếu mỗi người có 20 phim, mỗi phim có 8 thể loại hoặc liên kết bổ sung, việc mở rộng thêm nhiều cấp có thể tạo ra hàng nghìn phần tử trung gian. Đồ thị thực tế còn có thể có chu trình và nhiều đường đi cùng đến một node, khiến kết quả trung gian lớn hơn dự kiến.

Tải quá nhiều dữ liệu có thể dẫn đến:

- **Tăng thời gian truy vấn:** Neo4j phải duyệt nhiều relationship và tạo nhiều kết quả.
- **Tốn bộ nhớ:** Driver, mapper và ứng dụng phải xử lý nhiều node, relationship và object Java.
- **Tăng lưu lượng mạng:** dữ liệu không cần thiết vẫn được truyền từ Neo4j về ứng dụng.
- **Tăng chi phí ánh xạ:** Spring Data Neo4j phải chuyển dữ liệu đồ thị thành object graph và quản lý định danh các entity.
- **Tăng nguy cơ vòng tham chiếu trong tầng ứng dụng:** entity có thể tham chiếu qua lại, khiến serialize JSON hoặc log object đệ quy nếu không kiểm soát.
- **Khó phân trang:** khi join nhiều quan hệ, giới hạn số dòng có thể cắt dữ liệu quan hệ hoặc làm số node gốc trong một trang không như mong đợi.

Mục tiêu của một truy vấn đọc tốt không phải là lấy được đồ thị lớn nhất có thể, mà là lấy đúng phần đồ thị cần cho một thao tác cụ thể.

## 4. Dùng repository cho thao tác đọc thông thường

Repository phù hợp với thao tác đọc entity theo ID hoặc theo thuộc tính. Ví dụ:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {
    Optional<Person> findByPersonId(String personId);
}
```

Service có thể dùng repository để lấy entity theo mapping đã khai báo. Nếu màn hình chỉ cần tên người và tên phim, cần cân nhắc liệu việc tải toàn bộ entity graph có cần thiết hay không. Với một thao tác chỉ hiển thị thông tin tóm tắt, projection có thể giảm đáng kể lượng dữ liệu đọc.

Repository là lựa chọn tự nhiên khi nghiệp vụ cần làm việc với entity và các quan hệ của nó. Nhưng nếu use case yêu cầu một hình dạng dữ liệu rất cụ thể, hoặc cần giới hạn rõ các relationship được đọc, hãy cân nhắc `@Query` với Cypher tường minh.

## 5. Kiểm soát graph shape bằng @Query

Với truy vấn Cypher tùy chỉnh, pattern `MATCH` và `OPTIONAL MATCH` xác định phần đồ thị được tìm. Khi ánh xạ kết quả thành entity có quan hệ, truy vấn cần trả về các node và relationship cần thiết để Spring Data Neo4j dựng entity graph.

Ví dụ đọc một người cùng các phim đã tham gia:

```java
@Query("""
    MATCH (p:Person {personId: $personId})
    OPTIONAL MATCH (p)-[r:ACTED_IN]->(m:Movie)
    RETURN p, collect(r), collect(m)
    """)
Optional<Person> findPersonWithMovies(@Param("personId") String personId);
```

Truy vấn này:

1. Tìm node `Person` theo `personId`.
2. Dùng `OPTIONAL MATCH` để vẫn giữ người đó nếu chưa có phim nào.
3. Trả node gốc, các relationship `ACTED_IN` và các node `Movie` để mapper có dữ liệu dựng collection `movies`.

Nếu chỉ trả về `p` mà không trả các relationship và node đích cần ánh xạ, collection quan hệ có thể không được dựng như mong muốn. Với custom query, cần bảo đảm mọi phần tử cần thiết cho mapping đều nằm trong kết quả trả về.

Khi có nhiều nhánh quan hệ, cần kiểm soát số dòng trung gian. Có thể gom dữ liệu từng nhánh bằng `collect()` hoặc tách thành các truy vấn nhỏ để tránh phép nhân số dòng do ghép nhiều collection trong cùng một pattern.

### MATCH và OPTIONAL MATCH

`MATCH` yêu cầu pattern phải tồn tại. Nếu người chưa tham gia phim nào, truy vấn:

```cypher
MATCH (p:Person {personId: $personId})-[:ACTED_IN]->(m:Movie)
RETURN p, m
```

sẽ không trả về người đó. Dùng `OPTIONAL MATCH` nếu quan hệ là tùy chọn và vẫn muốn giữ node gốc:

```cypher
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[r:ACTED_IN]->(m:Movie)
RETURN p, collect(r), collect(m)
```

`collect()` bỏ qua giá trị `null`, nên trường hợp không có relationship sẽ tạo collection rỗng cho phần kết quả được gom. Cách này giúp giữ node gốc và biểu diễn quan hệ tùy chọn.

## 6. Dùng projection khi không cần entity graph đầy đủ

Nếu màn hình chỉ cần dữ liệu tóm tắt, không nên tải entity graph rồi bỏ phần lớn dữ liệu. Có thể định nghĩa projection để trả về các trường cần thiết:

```java
public interface PersonMovieSummary {
    String getPersonName();
    List<String> getMovieTitles();
}
```

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {personId: $personId})
        OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Movie)
        RETURN p.name AS personName,
               collect(m.title) AS movieTitles
        """)
    Optional<PersonMovieSummary> findSummary(
        @Param("personId") String personId
    );
}
```

Projection trên chỉ trả tên người và danh sách tiêu đề phim. Nó không yêu cầu ứng dụng dựng toàn bộ các object `Movie` với mọi property hoặc quan hệ tiếp theo.

Alias trong `RETURN` cần tương ứng với tên getter của projection. Với kiểu projection phức tạp hoặc kết quả nhiều tầng, cần kiểm tra quy tắc mapping của phiên bản SDN đang dùng; nếu cần kiểm soát chuyển đổi rõ ràng, có thể dùng DTO và `Neo4jClient`.

Projection phù hợp cho:

- Màn hình danh sách và thẻ tóm tắt.
- Báo cáo tổng hợp hoặc thống kê.
- API chỉ công khai một tập trường giới hạn.
- Tác vụ kiểm tra điều kiện không cần tải entity đầy đủ.

## 7. Tránh nhân số dòng khi tải nhiều collection

Giả sử một người có nhiều phim và nhiều kỹ năng:

```text
(Person)-[:ACTED_IN]->(Movie)
(Person)-[:HAS_SKILL]->(Skill)
```

Truy vấn sau ghép cả hai nhánh:

```cypher
MATCH (p:Person {personId: $personId})-[:ACTED_IN]->(m:Movie)
MATCH (p)-[:HAS_SKILL]->(s:Skill)
RETURN p, m, s
```

Nếu người đó có 10 phim và 6 kỹ năng, kết quả trung gian có thể có 60 dòng do mỗi phim kết hợp với mỗi kỹ năng. Nếu tiếp tục gom dữ liệu không đúng cách, danh sách phim và kỹ năng có thể bị lặp.

Có thể gom riêng hai nhánh bằng các subquery:

```cypher
MATCH (p:Person {personId: $personId})
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Movie)
    RETURN collect(DISTINCT m.title) AS movieTitles
}
CALL {
    WITH p
    OPTIONAL MATCH (p)-[:HAS_SKILL]->(s:Skill)
    RETURN collect(DISTINCT s.name) AS skillNames
}
RETURN p.name AS personName, movieTitles, skillNames
```

Mỗi subquery tổng hợp một nhánh riêng, giảm việc nhân chéo giữa các collection. Cú pháp subquery phụ thuộc phiên bản Neo4j; hãy kiểm tra khả năng hỗ trợ của server đang triển khai. Với trường hợp đơn giản, có thể dùng nhiều truy vấn riêng hoặc `Neo4jClient` để ghép DTO trong service.

## 8. Phân trang node gốc trước khi mở rộng quan hệ

Phân trang trực tiếp trên kết quả đã join nhiều relationship có thể làm trang chứa ít node gốc hơn dự kiến hoặc cắt mất một phần quan hệ của node cuối cùng. Ví dụ, `LIMIT 20` sau khi nối `Person` với `Movie` giới hạn 20 dòng kết quả, không nhất thiết là 20 người.

Một chiến lược dễ kiểm soát là phân trang danh sách ID node gốc trước:

```cypher
MATCH (p:Person)
WHERE p.active = true
RETURN p.personId AS personId
ORDER BY p.name, p.personId
SKIP $skip
LIMIT $pageSize
```

Sau đó tải quan hệ cho đúng tập ID vừa lấy:

```cypher
MATCH (p:Person)
WHERE p.personId IN $personIds
OPTIONAL MATCH (p)-[r:ACTED_IN]->(m:Movie)
RETURN p, collect(r), collect(m)
ORDER BY p.name
```

Trong ứng dụng, có thể thực hiện bước đầu bằng repository trả về danh sách `personId`, rồi bước thứ hai bằng repository hoặc `Neo4jClient` trả về graph/projection tương ứng. Nếu cần giữ đúng thứ tự của trang đầu, hãy mang thứ tự ID theo danh sách hoặc sắp xếp lại kết quả trong ứng dụng theo thứ tự ban đầu.

Với dữ liệu thay đổi liên tục giữa hai truy vấn, cần cân nhắc transaction và tính nhất quán của trang. Nếu hai truy vấn không chạy trong cùng snapshot phù hợp, một node có thể bị cập nhật hoặc xóa giữa lúc lấy ID và lúc tải graph.

## 9. Giới hạn độ rộng và độ sâu của Cypher

Không nên truy vấn toàn bộ đồ thị khi chỉ cần một vùng nhỏ. Tránh pattern không giới hạn như:

```cypher
MATCH path = (p:Person)-[*]-(n)
WHERE p.personId = $personId
RETURN path
```

`[*]` không giới hạn độ dài có thể mở rộng qua rất nhiều đường đi. Nếu nghiệp vụ chỉ cần tối đa ba bước, hãy giới hạn độ dài:

```cypher
MATCH path = (p:Person)-[*1..3]-(n)
WHERE p.personId = $personId
RETURN path
LIMIT 100
```

Giới hạn độ dài vẫn có thể tạo nhiều đường đi, vì vậy cần thêm label, relationship type, hướng và điều kiện lọc phù hợp. `LIMIT` giới hạn số dòng trả về, nhưng không bảo đảm Neo4j chỉ phải duyệt đúng số lượng node đó trong mọi kế hoạch thực thi.

Nên:

- Chỉ truy vấn label và relationship type cần thiết.
- Chỉ mở rộng theo hướng có ý nghĩa nghiệp vụ khi có thể.
- Giới hạn độ dài path thay vì duyệt không giới hạn.
- Dùng điều kiện trên property có index phù hợp để xác định node gốc.
- Tránh trả về `path` hoặc node đầy đủ nếu chỉ cần vài property.
- Dùng `EXPLAIN` và `PROFILE` với dữ liệu gần thực tế để đánh giá số hàng, operator và chi phí thực thi.

## 10. Kiểm tra số liệu và chất lượng graph read

Khi một API đọc chậm, hãy xác định phần nào gây tốn kém: tìm node gốc, mở rộng relationship, tạo kết quả trung gian, truyền dữ liệu hay ánh xạ object. Có thể bắt đầu bằng cách đo truy vấn ở Neo4j:

```cypher
PROFILE
MATCH (p:Person {personId: $personId})
OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Movie)
RETURN p, collect(m)
```

Đánh giá:

- Số node và relationship được duyệt.
- Số dòng trung gian trước bước tổng hợp.
- Index có được sử dụng để tìm node gốc hay không.
- Có phép mở rộng nào không cần thiết không.
- Kích thước kết quả trả về so với dữ liệu màn hình thực sự sử dụng.

Ở tầng Java, theo dõi thời gian truy vấn, số phần tử trong collection, kích thước response và thời gian serialize. Một truy vấn Neo4j nhanh vẫn có thể tạo response lớn và chậm ở bước chuyển object thành JSON.

Không nên dùng một depth cố định cho mọi use case chỉ vì thuận tiện. Màn hình chi tiết có thể cần một số quan hệ; màn hình danh sách có thể chỉ cần projection; tác vụ phân tích có thể cần aggregation thay vì tải entity graph.

## 11. Lựa chọn API theo mục tiêu đọc

| Mục tiêu | Cách tiếp cận | Lý do |
|---|---|---|
| Đọc entity và quan hệ cần cho nghiệp vụ | Repository hoặc `Neo4jTemplate` | Dùng mapping entity đã khai báo và chọn depth phù hợp. |
| Kiểm soát rõ các node/relationship được lấy | `@Query` với Cypher | Pattern truy vấn xác định graph shape. |
| Trả dữ liệu tóm tắt | Interface projection hoặc DTO | Chỉ lấy các trường cần thiết. |
| Tính toán hoặc tổng hợp dữ liệu | Cypher aggregation, `Neo4jClient` | Đẩy phép lọc/tổng hợp xuống database và tránh tải object không cần. |
| Đọc graph lớn theo trang | Phân trang ID gốc rồi tải phần quan hệ cần thiết | Tránh giới hạn dòng join làm cắt node gốc. |
| Duyệt mạng lưới nhiều bước | Cypher có giới hạn độ dài và điều kiện rõ | Kiểm soát phạm vi traversal. |

## 12. Ghi nhớ

Spring Data Neo4j ánh xạ node và các relationship được khai báo trong entity thành object graph. Khi đọc, hãy xác định độ sâu và phạm vi quan hệ cần thiết; `Neo4jTemplate` cung cấp API cho phép chỉ định depth trong những thao tác đọc phù hợp. Với truy vấn tùy chỉnh, Cypher quyết định graph shape và cần trả về node cùng relationship mà mapper cần để dựng entity.

Tải sâu hoặc rộng không cần thiết có thể làm tăng số node, relationship, dòng trung gian, bộ nhớ, lưu lượng mạng và thời gian ánh xạ. Hãy dùng projection cho màn hình tóm tắt, gom riêng các nhánh collection, phân trang node gốc trước khi mở rộng quan hệ và giới hạn path. Đo bằng `EXPLAIN`/`PROFILE` cùng số liệu ở tầng ứng dụng để chọn phạm vi đọc phù hợp cho từng use case.
