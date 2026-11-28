# Phân trang reactive bằng Cypher và phép đếm riêng khi cần

Khi truy vấn graph trả về nhiều kết quả, ứng dụng reactive cần giới hạn số hàng được đọc cho mỗi lần gọi. Với Spring Data Neo4j (SDN), có thể viết Cypher dùng `ORDER BY`, `SKIP` và `LIMIT`, nhận nội dung dưới dạng `Flux<T>`, rồi kết hợp một truy vấn đếm riêng nếu giao diện cần tổng số phần tử. Cách làm này giữ luồng xử lý reactive từ database tới service và cho phép kiểm soát chính xác cách phân trang trên graph.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ dùng `Person`, `Movie` và `ACTED_IN` để phân trang người theo điều kiện phim, đếm đúng số node gốc sau khi traversal có thể tạo nhiều hàng, và lựa chọn giữa `Page`, `Slice` cùng keyset pagination.

## 1. Phân trang reactive gồm những phần nào?

Một trang dữ liệu có thể bao gồm hai loại thông tin:

- **Content:** các entity hoặc DTO trong phạm vi trang hiện tại.
- **Metadata:** số trang, kích thước trang, offset, có trang tiếp theo hay không và tổng số kết quả.

Với truy vấn reactive, phần content thường được phát dưới dạng `Flux<T>`. Nếu cần đóng gói kết quả thành một trang có metadata, service có thể thu thập đúng số hàng của một trang rồi bọc danh sách đó trong `PageImpl<T>` hoặc `SliceImpl<T>`, trả về dưới dạng `Mono<Page<T>>` hoặc `Mono<Slice<T>>`.

| Kiểu kết quả | Nội dung | Metadata |
|---|---|---|
| `Flux<T>` | Phát từng phần tử theo reactive streams | Không có số trang hay tổng số |
| `Mono<List<T>>` | Một danh sách đã thu thập | Chỉ có content |
| `Mono<Slice<T>>` | Content của trang | Có `hasNext`, không có tổng số |
| `Mono<Page<T>>` | Content của trang | Có `totalElements`, `totalPages` và thông tin trang |

`Page` và `Slice` là kiểu bao kết quả đồng bộ của Spring Data Commons; đặt chúng bên trong `Mono` giúp phương thức service vẫn giữ hợp đồng reactive. `ReactiveNeo4jOperations` cung cấp `findAll(...)` trả `Flux<T>` và `count(...)` trả `Mono<Long>`, phù hợp để ghép hai truy vấn mà không cần chặn luồng bằng `block()`.

## 2. Vì sao cần viết Cypher phân trang tường minh?

Trong một truy vấn graph, một node có thể xuất hiện trên nhiều hàng trung gian khi `MATCH` qua relationship. Nếu mục tiêu là phân trang các node `Person`, ta phải loại bản sao của `Person` trước khi áp dụng `SKIP` và `LIMIT`.

Ví dụ tìm những người từng tham gia phim phát hành từ năm 2000:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
WITH DISTINCT p
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP $skip
LIMIT $limit;
```

`WITH DISTINCT p` đảm bảo một người chỉ chiếm một vị trí trong tập kết quả trước khi phân trang. Nếu bỏ `DISTINCT`, một người tham gia ba phim phù hợp có thể xuất hiện ba lần và chiếm ba vị trí của cùng một trang.

Các tham số `$skip` và `$limit` được bind từ code. Với trang thứ nhất kích thước 20, `skip = 0`, `limit = 20`; trang thứ hai có `skip = 20`, `limit = 20`.

## 3. Thứ tự ổn định là điều kiện bắt buộc

Neo4j không bảo đảm thứ tự của các hàng nếu truy vấn không có `ORDER BY`. Khi phân trang, cần sắp xếp bằng một hoặc nhiều property có ý nghĩa nghiệp vụ, và nên thêm khóa phụ duy nhất để phá hòa.

```cypher
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP $skip
LIMIT $limit;
```

Trong ví dụ, nhiều người có thể trùng `name`; `personId` duy nhất giúp xác định thứ tự giữa những người đó. Chỉ sắp xếp theo tên có thể khiến các node cùng tên đổi vị trí giữa các lần truy vấn.

Nếu thứ tự cần do người dùng chọn, không nối trực tiếp tên property hoặc `ASC`/`DESC` từ request vào Cypher. Hãy ánh xạ lựa chọn qua whitelist trong ứng dụng, rồi chỉ ghép identifier đã được kiểm soát. Giá trị lọc, offset và limit vẫn nên truyền bằng named parameter.

## 4. Phân trang entity bằng ReactiveNeo4jOperations

`ReactiveNeo4jOperations` cung cấp các overload:

- `findAll(cypher, parameters, domainType)` trả `Flux<T>`.
- `count(cypher, parameters)` trả `Mono<Long>`.

Vì vậy, có thể inject abstraction này vào service và dùng Cypher riêng cho phần content lẫn phần count:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.core.ReactiveNeo4jOperations;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import reactor.core.publisher.Mono;

@Service
public class PersonPagingService {

    private static final String PAGE_QUERY = """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE m.released >= $fromYear
        WITH DISTINCT p
        RETURN p
        ORDER BY p.name ASC, p.personId ASC
        SKIP $skip
        LIMIT $limit
        """;

    private static final String COUNT_QUERY = """
        MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
        WHERE m.released >= $fromYear
        RETURN count(DISTINCT p)
        """;

    private final ReactiveNeo4jOperations neo4j;

    public PersonPagingService(ReactiveNeo4jOperations neo4j) {
        this.neo4j = neo4j;
    }

    @Transactional(readOnly = true)
    public Mono<Page<Person>> findPeopleWithRecentCredits(
            int fromYear,
            Pageable pageable) {

        if (pageable == null || pageable.isUnpaged()) {
            return Mono.error(new IllegalArgumentException(
                "A paged Pageable is required"
            ));
        }

        Map<String, Object> pageParameters = Map.of(
            "fromYear", fromYear,
            "skip", pageable.getOffset(),
            "limit", pageable.getPageSize()
        );

        Map<String, Object> countParameters = Map.of(
            "fromYear", fromYear
        );

        Mono<List<Person>> content = neo4j
            .findAll(PAGE_QUERY, pageParameters, Person.class)
            .collectList();

        Mono<Long> total = neo4j.count(COUNT_QUERY, countParameters);

        return content.flatMap(items ->
            total.map(totalElements ->
                new PageImpl<>(items, pageable, totalElements)
            )
        );
    }
}
```

Trong ví dụ:

1. `findAll(...)` thực thi Cypher lấy đúng phần content và ánh xạ node `p` thành `Person`.
2. `collectList()` chỉ thu thập tối đa `pageSize` entity, vì Cypher đã có `LIMIT`.
3. `count(...)` thực thi truy vấn riêng, trả về một `Mono<Long>`.
4. `flatMap` đợi content hoàn tất rồi mới thực thi count, sau đó tạo `PageImpl`.
5. `@Transactional(readOnly = true)` đặt hai thao tác đọc trong transaction reactive nếu ứng dụng đã cấu hình `ReactiveNeo4jTransactionManager`.

Việc nối tuần tự qua `flatMap` giúp tránh phát hai statement đồng thời trên cùng reactive transaction. Phương thức vẫn trả `Mono<Page<Person>>`; không gọi `subscribe()` hoặc `block()` bên trong service.

Ở ví dụ này, `Person` là entity `@Node("Person")` có các property `name` và `personId`. Query custom phải trả node `p` để SDN ánh xạ thành entity; nếu chỉ trả `p.name`, kết quả là scalar chứ không phải `Person`.

Khi gọi service, có thể tạo `Pageable` bằng `PageRequest.of(pageNumber, pageSize)`. Trong ví dụ, `ORDER BY` đã được cố định trong Cypher; `Pageable.getSort()` không tự động được chèn vào câu query do `ReactiveNeo4jOperations.findAll(...)` thực thi. Nếu cần sort động, hãy chuyển các lựa chọn sort hợp lệ qua whitelist và tạo phần `ORDER BY` từ những identifier đã kiểm soát. Có thể truyền `Sort.unsorted()` trong `PageRequest` để làm rõ rằng thứ tự do Cypher quyết định.

## 5. count query phải đếm đúng tập kết quả logic

Truy vấn content và truy vấn count phải đại diện cho cùng một tập kết quả. Những điều kiện làm thay đổi tập entity phải được giữ tương ứng ở cả hai câu Cypher:

- Cùng label và relationship pattern.
- Cùng predicate `WHERE`.
- Cùng điều kiện tenant, trạng thái, quyền truy cập hoặc thời gian.
- Cùng semantics về node gốc duy nhất hoặc nhóm kết quả.

Với ví dụ tìm `Person` qua `ACTED_IN`, câu count đúng là:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
RETURN count(DISTINCT p);
```

Không dùng `count(*)` nếu mục tiêu là số người duy nhất. `count(*)` đếm hàng trung gian; `count(p)` cũng đếm giá trị `p` trên từng hàng và có thể đếm lặp cùng node. `count(DISTINCT p)` đếm mỗi node Person một lần.

Ví dụ có ba người, trong đó người A tham gia ba phim, người B tham gia một phim và người C tham gia một phim. Truy vấn `MATCH` tạo năm hàng nhưng chỉ có ba người. Nội dung trang cần chứa ba người duy nhất và count query phải trả `3`.

## 6. Nếu Page chứa DTO nhóm, hãy đếm số nhóm

Không phải trang nào cũng đại diện một node gốc. Nếu truy vấn trả một dòng cho mỗi phim cùng số diễn viên, `Page<MovieSummary>` đại diện các nhóm theo `Movie`, do đó count query phải đếm số phim duy nhất.

Truy vấn content:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
WITH m, count(DISTINCT p) AS actorCount
RETURN m.movieId AS movieId,
       m.title AS title,
       m.released AS released,
       actorCount
ORDER BY released DESC, movieId ASC
SKIP $skip
LIMIT $limit;
```

Count query:

```cypher
MATCH (:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
RETURN count(DISTINCT m);
```

`count(*)` trên các relationship đầu vào sẽ đếm số credit, không phải số nhóm/phim. Với nhóm phức tạp được xác định bởi nhiều property, hãy đếm các tổ hợp nhóm duy nhất. Ví dụ:

```cypher
CALL {
    MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
    WHERE m.released >= $fromYear
    RETURN DISTINCT p.personId AS personId,
                    m.released AS releaseYear
}
RETURN count(*) AS totalGroups;
```

Truy vấn này đếm số tổ hợp `(personId, releaseYear)` duy nhất. Phần subquery phải mô tả đúng tập nhóm mà query content trả về.

## 7. Kết hợp content và count bằng reactive chain

Một cách viết tổng quát hơn là tách hai publisher thành biến rồi ghép tuần tự:

```java
Mono<List<Person>> content = neo4j
    .findAll(PAGE_QUERY, pageParameters, Person.class)
    .collectList();

Mono<Long> total = neo4j.count(COUNT_QUERY, countParameters);

return content.flatMap(items ->
    total.map(totalElements ->
        new PageImpl<>(items, pageable, totalElements)
    )
);
```

Không dùng `.block()` để lấy kết quả count trước khi tạo `Page`. `block()` phá vỡ luồng reactive và có thể chặn event-loop thread. Cũng không cần gọi `.subscribe()` thủ công; caller, WebFlux hoặc test sẽ subscribe publisher.

Có thể dùng `Mono.zip(content, total)` nếu hai truy vấn độc lập và không nằm trong cùng reactive transaction. Khi cả hai cùng tham gia một transaction, nối tuần tự thường dễ kiểm soát hơn vì tránh chạy hai query đồng thời trên cùng transaction/session.

## 8. Dùng Slice khi không cần tổng số

Nếu giao diện chỉ cần biết còn dữ liệu để tải tiếp hay không, không cần thực thi count query. Hãy yêu cầu `pageSize + 1` hàng:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
WITH DISTINCT p
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP $skip
LIMIT $limit;
```

Code tạo `Slice<Person>`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;

import reactor.core.publisher.Mono;

public Mono<Slice<Person>> findPeopleSlice(
        int fromYear,
        Pageable pageable) {

    int pageSize = pageable.getPageSize();

    Map<String, Object> parameters = Map.of(
        "fromYear", fromYear,
        "skip", pageable.getOffset(),
        "limit", pageSize + 1
    );

    return neo4j.findAll(PAGE_QUERY, parameters, Person.class)
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > pageSize;
            List<Person> content = hasNext
                ? new ArrayList<>(rows.subList(0, pageSize))
                : rows;

            return new SliceImpl<>(content, pageable, hasNext);
        });
}
```

Nếu truy vấn trả về nhiều hơn `pageSize` hàng, hàng thừa chỉ dùng để xác định `hasNext`; nó không được đưa vào content. Cách này tránh count query và phù hợp với nút “Tải thêm” hoặc infinite scrolling.

Không cần dùng `PageImpl` nếu giao diện không hiển thị tổng số trang. Count query có thể tốn kém khi graph lớn hoặc predicate đi qua nhiều relationship.

## 9. Chọn Page, Slice hay Flux

| Nhu cầu | Kiểu trả về nên cân nhắc | Truy vấn database |
|---|---|---|
| Hiển thị tổng số phần tử và tổng số trang | `Mono<Page<T>>` | Một query content và một query count |
| Chỉ cần biết có trang kế tiếp | `Mono<Slice<T>>` | Một query lấy `pageSize + 1` hàng |
| Xử lý luồng dữ liệu mà không cần metadata trang | `Flux<T>` | Một query có filter/limit phù hợp |
| Chỉ cần danh sách nhỏ trong một lần gọi | `Mono<List<T>>` | Một query có `LIMIT` |

Không nên luôn dùng `Page` cho mọi endpoint. Nếu người dùng chỉ tải tiếp từng phần, `Slice` thường đủ và tránh được chi phí count.

## 10. Phân trang offset và chi phí của SKIP

Offset pagination dùng `SKIP` để bỏ qua các hàng trước vị trí cần lấy. Cách này dễ ánh xạ từ `Pageable.getOffset()`, nhưng càng đi tới trang sâu, database càng phải xử lý nhiều hàng trước khi trả phần content.

Ví dụ:

```cypher
MATCH (p:Person)
RETURN p
ORDER BY p.name ASC, p.personId ASC
SKIP 50000
LIMIT 20;
```

Ngay cả khi chỉ trả 20 hàng, Neo4j vẫn cần xác định và bỏ qua 50.000 hàng trước đó theo thứ tự yêu cầu. Với offset lớn, thời gian truy vấn có thể tăng đáng kể.

Offset pagination phù hợp với danh sách có số trang vừa phải và cho phép người dùng nhảy trực tiếp tới một trang. Với dữ liệu rất lớn hoặc luồng tải tiếp liên tục, hãy cân nhắc keyset pagination.

## 11. Keyset pagination theo khóa sắp xếp

Keyset pagination dùng giá trị của phần tử cuối cùng trong trang trước làm cursor. Thay vì bỏ qua N hàng, query tiếp theo tìm các node đứng sau cursor theo cùng thứ tự.

Ví dụ sắp xếp theo `name`, sau đó `personId`:

```cypher
MATCH (p:Person)
WHERE $lastName IS NULL
   OR p.name > $lastName
   OR (p.name = $lastName AND p.personId > $lastPersonId)
RETURN p
ORDER BY p.name ASC, p.personId ASC
LIMIT $limit;
```

Ở trang đầu, `lastName` và `lastPersonId` là `null`. Ở trang tiếp theo, truyền hai giá trị từ node cuối cùng của trang trước. Khóa cursor phải bao gồm đầy đủ các tiêu chí sắp xếp để xác định một vị trí duy nhất.

Keyset pagination có các đặc điểm:

- Không phải quét bỏ toàn bộ các hàng trước offset.
- Ít bị xáo trộn bởi việc thêm node đứng trước cursor so với offset pagination.
- Không thuận tiện để nhảy trực tiếp tới trang số 100.
- Thường không cung cấp `totalPages`; nếu cần tổng số, vẫn phải chạy count query riêng.
- Nếu property sắp xếp của node thay đổi trong khi người dùng chuyển trang, node có thể di chuyển qua cursor và gây lặp hoặc bỏ sót.

Với sort key phức tạp hoặc nhiều chiều, cursor cần chứa mọi giá trị sort key và khóa phụ duy nhất.

## 12. Bảo đảm count và content dùng cùng điều kiện

Một lỗi thường gặp là query content lọc theo năm phát hành nhưng query count quên điều kiện đó:

```cypher
// Content
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
WITH DISTINCT p
RETURN p
ORDER BY p.name, p.personId
SKIP $skip LIMIT $limit;

// Sai: count đang đếm mọi Person có ACTED_IN.
MATCH (p:Person)-[:ACTED_IN]->(:Movie)
RETURN count(DISTINCT p);
```

Count query đúng phải giữ predicate:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= $fromYear
RETURN count(DISTINCT p);
```

Nếu query content có thêm điều kiện quyền truy cập, tenant hoặc trạng thái, count query cũng phải giữ cùng điều kiện. Nếu không, `totalElements` có thể lớn hơn hoặc nhỏ hơn số entity thực sự được phép hiển thị.

Không đưa `SKIP`, `LIMIT` hoặc `ORDER BY` của trang vào count query. Count phải đo toàn bộ tập kết quả logic trước khi giới hạn trang.

## 13. Count và content trong reactive transaction

Có thể đặt phương thức trả `Mono<Page<T>>` trong `@Transactional(readOnly = true)` để các query tham gia reactive transaction:

```java
@Transactional(readOnly = true)
public Mono<Page<Person>> findPeopleWithRecentCredits(
        int fromYear,
        Pageable pageable) {
    // Query content, sau đó query count và tạo PageImpl.
}
```

Ứng dụng phải cấu hình `ReactiveNeo4jTransactionManager`; client/template và transaction manager phải dùng cùng Driver cùng database selection. Publisher cần được trả về caller để Spring quản lý transaction qua Reactor context.

Một transaction giúp hai query thuộc cùng một đơn vị giao dịch, nhưng isolation mặc định của Neo4j là `READ_COMMITTED`. Vì vậy, nếu transaction khác ghi dữ liệu đồng thời, query content và count chạy ở hai thời điểm khác nhau vẫn có thể quan sát các trạng thái đã commit khác nhau. `Page` có thể tạm thời chứa content và total không khớp tuyệt đối trong thời gian có ghi đồng thời.

Nếu nghiệp vụ cần một ảnh chụp dữ liệu nhất quán cho nhiều lần đọc, cần thiết kế kiểm soát đồng thời phù hợp ở tầng graph. Không giả định chỉ thêm `@Transactional(readOnly = true)` là tạo snapshot isolation.

## 14. Kiểm thử bằng dữ liệu có relationship nhân dòng

Hãy tạo graph trong đó một người tham gia nhiều phim:

```cypher
CREATE
  (a:Person {personId: 'P-A', name: 'Person A'}),
  (b:Person {personId: 'P-B', name: 'Person B'}),
  (c:Person {personId: 'P-C', name: 'Person C'}),
  (m1:Movie {movieId: 'M-1', released: 2001}),
  (m2:Movie {movieId: 'M-2', released: 2002}),
  (m3:Movie {movieId: 'M-3', released: 2003}),
  (a)-[:ACTED_IN]->(m1),
  (a)-[:ACTED_IN]->(m2),
  (a)-[:ACTED_IN]->(m3),
  (b)-[:ACTED_IN]->(m1),
  (c)-[:ACTED_IN]->(m2);
```

So sánh số hàng và số node duy nhất:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE m.released >= 2000
RETURN count(*) AS matchedRows,
       count(p) AS personValues,
       count(DISTINCT p) AS uniquePeople;
```

Kết quả kỳ vọng:

| Giá trị | Kết quả |
|---|---:|
| `matchedRows` | 5 |
| `personValues` | 5 |
| `uniquePeople` | 3 |

Với `Page<Person>` kích thước 2:

- Trang đầu có hai người duy nhất.
- Trang thứ hai có một người duy nhất.
- `totalElements` của cả hai trang bằng 3.
- `totalPages` bằng 2.
- Không có người nào xuất hiện lặp giữa hai trang.

Với `Slice<Person>` kích thước 2, query lấy tối đa ba hàng. Trang đầu trả hai người và `hasNext = true`; trang thứ hai trả một người và `hasNext = false`.

## 15. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ dùng `LIMIT` mà không có `SKIP` | Mọi request đều lấy trang đầu | Bind offset từ `Pageable.getOffset()` |
| Không có `ORDER BY` | Thứ tự hàng không được bảo đảm | Sắp xếp rõ ràng trước `SKIP`/`LIMIT` |
| Chỉ sort theo property không duy nhất | Các hàng bằng giá trị sort có thể đổi vị trí | Thêm khóa phụ duy nhất |
| Phân trang trước khi `DISTINCT` node gốc | Một node chiếm nhiều vị trí và trang thiếu entity duy nhất | `WITH DISTINCT root` trước `ORDER BY`, `SKIP`, `LIMIT` |
| Dùng `count(*)` cho Page entity | Đếm hàng trung gian thay vì entity gốc | Dùng `count(DISTINCT root)` |
| Count query bỏ predicate của content query | `totalElements` không khớp tập kết quả | Giữ cùng điều kiện lọc ở cả hai query |
| Count query chứa `SKIP`/`LIMIT` | Tổng số chỉ phản ánh một phần trang | Đếm toàn bộ tập kết quả logic |
| Dùng `Page` dù chỉ cần nút tải tiếp | Phát sinh count query không cần thiết | Dùng `Slice` với `pageSize + 1` |
| Dùng `collectList()` trước khi giới hạn ở Cypher | Có thể tải toàn bộ graph vào bộ nhớ | Đặt `LIMIT` ở database trước khi thu thập |
| Dùng offset rất lớn | Query phải bỏ qua nhiều hàng | Cân nhắc keyset pagination |
| Gọi `.block()` để tạo Page | Chặn luồng reactive | Ghép content và count bằng `flatMap`/`zip` |
| Dùng `Mono.zip` cho nhiều query trên cùng transaction mà không kiểm tra driver | Có thể phát sinh truy vấn đồng thời trên cùng transaction/session | Nối tuần tự bằng `flatMap` khi dùng chung transaction |
| Ghép sort field từ request vào Cypher | Rủi ro injection hoặc lỗi cú pháp | Dùng whitelist cho identifier; bind giá trị |

## 16. Checklist triển khai phân trang reactive

- Xác định trang đại diện entity gốc hay nhóm DTO.
- Viết query content có `ORDER BY`, `SKIP` và `LIMIT`.
- Thêm khóa phụ duy nhất vào thứ tự sắp xếp.
- Nếu `MATCH` qua relationship có thể nhân dòng, khử trùng lặp root trước khi phân trang.
- Viết count query riêng nếu cần tổng số chính xác.
- Đảm bảo count đếm đúng entity gốc hoặc số nhóm kết quả.
- Giữ nguyên predicate, tenant và điều kiện quyền truy cập trong count query.
- Không đưa offset/limit vào count query.
- Dùng `PageImpl` khi cần tổng số; dùng `SliceImpl` với `pageSize + 1` khi chỉ cần `hasNext`.
- Giữ dữ liệu dưới dạng `Flux`/`Mono` xuyên suốt, không gọi `subscribe()` hoặc `block()` trong service.
- Nếu content và count cùng transaction, cân nhắc nối tuần tự các truy vấn.
- Kiểm thử với graph có một node liên kết nhiều node khác.
- Đánh giá keyset pagination nếu offset tăng lớn.
- Dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra hiệu năng trên graph đại diện.

## 17. Bài tập thực hành

1. Viết Cypher phân trang `Person` bằng `SKIP` và `LIMIT`, sắp xếp theo `name` và `personId`.
2. Viết service trả `Mono<Page<Person>>` bằng `ReactiveNeo4jOperations.findAll(...)` và `count(...)`.
3. Tạo graph có một người tham gia ba phim; so sánh `count(*)` với `count(DISTINCT p)`.
4. Bỏ `WITH DISTINCT p` khỏi query content và quan sát một người xuất hiện nhiều lần trong trang.
5. Viết count query có cùng predicate `m.released >= $fromYear` với content query.
6. Tạo `Slice<Person>` bằng cách truy vấn `pageSize + 1` hàng và tính `hasNext`.
7. Tạo `Page<MovieSummary>` có một dòng cho mỗi phim; viết count query đếm số phim duy nhất.
8. Viết query keyset theo `(name, personId)` và dùng node cuối trang trước làm cursor.
9. So sánh thời gian offset ở trang đầu với một offset lớn trên dữ liệu đủ lớn.
10. Chạy content query và count query trong `@Transactional(readOnly = true)`; giải thích giới hạn của `READ_COMMITTED` khi có ghi đồng thời.
11. Dùng `StepVerifier` kiểm tra content, total, totalPages và trường hợp trang cuối rỗng.
12. Dùng `EXPLAIN`/`PROFILE` để xem tác động của index và `ORDER BY` đối với truy vấn phân trang.

Khi hoàn thành, bạn cần biết cách giữ content ở dạng reactive, viết Cypher phân trang tường minh và ghép một phép đếm riêng chỉ khi cần metadata tổng số. Điều quan trọng nhất là count query phải đếm đúng tập entity hoặc nhóm logic mà trang đại diện, còn query content phải loại bản sao graph trước khi áp dụng offset và limit.

## Tài liệu tham khảo

- [Spring Data Neo4j — ReactiveNeo4jOperations API 8.1.x](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jOperations.html)
- [Spring Data Neo4j — ReactiveNeo4jTemplate API 8.1.x](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveNeo4jTemplate.html)
- [Spring Data Neo4j — ReactiveNeo4jRepository API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/ReactiveNeo4jRepository.html)
- [Spring Data Commons — Page and Slice query results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Neo4j Cypher Manual — SKIP](https://neo4j.com/docs/cypher-manual/current/clauses/skip/)
- [Neo4j Cypher Manual — LIMIT](https://neo4j.com/docs/cypher-manual/current/clauses/limit/)
- [Neo4j Cypher Manual — ORDER BY](https://neo4j.com/docs/cypher-manual/current/clauses/order-by/)
