# Distinct, OrderBy, First và Top theo khả năng của phiên bản

Spring Data Neo4j cho phép tạo nhiều truy vấn repository từ tên phương thức. Ngoài phần điều kiện sau `By`, tên phương thức còn có thể mô tả cách loại bỏ kết quả trùng, thứ tự sắp xếp và số lượng kết quả tối đa. Bốn từ khóa `Distinct`, `OrderBy`, `First` và `Top` giúp diễn đạt những yêu cầu thường gặp mà không cần viết Cypher cho từng trường hợp.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung vào xây dựng tầng dữ liệu đồ thị qua node entity, relationship, repository và Cypher. Ví dụ dùng `Person`, `Movie` và relationship `ACTED_IN` để tìm người theo phim đã tham gia, sắp xếp phim theo năm phát hành và lấy một số kết quả đứng đầu.

Các từ khóa này được Spring Data Commons phân tích theo quy tắc tên phương thức, nhưng khả năng thực thi cụ thể phụ thuộc store và phiên bản Spring Data Neo4j (SDN) mà ứng dụng đang dùng. Tài liệu tham khảo ổn định hiện hành của SDN 8.1.x mô tả `Distinct`, `OrderBy`, `First` và `Top`; khi dự án dùng phiên bản khác, hãy đối chiếu đúng tài liệu của phiên bản đó và kiểm thử repository lúc khởi động. [Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html) · [Repository Query Keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)

## 1. Cấu trúc tên phương thức derived query

Một tên phương thức truy vấn thường có hai phần:

```text
find [phần mô tả và từ khóa ở subject] By [điều kiện lọc] [sắp xếp]
```

Ví dụ:

```java
List<Movie> findByReleasedGreaterThanOrderByReleasedDescTitleAsc(Integer year);
```

Có thể đọc tên này theo thứ tự:

1. `find`: phương thức truy vấn và trả về kết quả.
2. `ByReleasedGreaterThan`: chỉ lấy phim có `released` lớn hơn tham số `year`.
3. `OrderByReleasedDescTitleAsc`: sắp xếp năm phát hành giảm dần, sau đó tiêu đề tăng dần.

`By` đầu tiên phân chia phần subject và predicate. `Distinct`, `First` hoặc `Top` có thể xuất hiện trong phần subject trước `By`; `OrderBy` theo sau điều kiện để khai báo thứ tự tĩnh. Tên property trong phương thức dựa trên property của mô hình Java và đường dẫn property mà Spring Data nhận diện, không phải tên biến Cypher tùy ý.

## 2. Distinct: chỉ trả về kết quả duy nhất

`Distinct` yêu cầu truy vấn trả về các kết quả duy nhất. Từ khóa này hữu ích khi một truy vấn duyệt qua relationship có thể tạo nhiều dòng cho cùng node gốc.

Ví dụ, một người có thể tham gia nhiều phim. Khi truy vấn theo đường đi từ `Person` qua `actedIn` đến `Movie`, cùng một `Person` có thể xuất hiện nhiều lần nếu có nhiều relationship khớp điều kiện.

```java
@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(type = "ACTED_IN", direction = Direction.OUTGOING)
    private List<Movie> actedIn = new ArrayList<>();
}
```

Repository có thể khai báo:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    List<Person> findDistinctByActedInTitle(String title);
}
```

`ActedInTitle` mô tả đường dẫn property `actedIn.title`. `Distinct` yêu cầu kết quả `Person` không lặp lại khi nhiều đường đi khớp cùng một người.

Một số dạng tên khác cũng có thể dùng:

```java
List<Person> findDistinctPeopleByNameContaining(String fragment);

List<Person> findPeopleDistinctByNameContaining(String fragment);
```

Các từ như `People` trong subject có thể chỉ mang tính mô tả; `Distinct` mới là từ khóa thay đổi cách truy vấn. Hãy ưu tiên tên dễ đọc và thống nhất quy ước đặt tên trong nhóm.

### 2.1. Distinct không phải uniqueness constraint

`Distinct` chỉ ảnh hưởng đến kết quả của truy vấn. Nó không:

- Tạo uniqueness constraint trong Neo4j.
- Ngăn ứng dụng tạo hai node có cùng `name`.
- Thay thế `count(DISTINCT ...)` trong một truy vấn tổng hợp Cypher tùy chỉnh.
- Có nghĩa là chỉ trả về một giá trị property duy nhất nếu kiểu kết quả repository là entity.

Nếu cần bảo đảm mỗi `Person` có `personId` duy nhất, hãy tạo constraint ở Neo4j. Nếu cần trả về danh sách tên duy nhất hoặc một projection tùy chỉnh, hãy kiểm tra kiểu projection được hỗ trợ hoặc viết Cypher bằng `@Query`.

### 2.2. Distinct khi kết hợp First hoặc Top

Spring Data hỗ trợ kết hợp từ khóa giới hạn với `Distinct` cho store hỗ trợ distinct query. Ví dụ:

```java
List<Person> findDistinctTop5ByActedInTitleOrderByNameAsc(String title);
```

Ý định là lấy tối đa năm `Person` duy nhất có tham gia phim theo tiêu đề, sắp xếp tên tăng dần. Vì khả năng distinct là đặc điểm cần xác nhận theo store và phiên bản, hãy kiểm tra method được tạo truy vấn đúng trong dự án SDN cụ thể. Nếu không hỗ trợ hoặc kết quả cần định nghĩa khác, dùng `@Query` với `RETURN DISTINCT` tường minh.

## 3. OrderBy: sắp xếp tĩnh trong tên phương thức

`OrderBy` khai báo thứ tự cố định cho một derived query. Cú pháp cơ bản:

```text
OrderBy<Property>Asc
OrderBy<Property>Desc
```

Có thể kết hợp nhiều tiêu chí:

```java
List<Movie> findByReleasedGreaterThanOrderByReleasedDescTitleAsc(Integer year);
```

Truy vấn lọc phim có năm phát hành lớn hơn `year`, sau đó:

1. Sắp xếp `released` giảm dần (`Desc`) để phim mới hơn đứng trước.
2. Nếu cùng năm phát hành, sắp xếp `title` tăng dần (`Asc`) để có thứ tự phụ ổn định.

Repository ví dụ:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    List<Movie> findByReleasedGreaterThanOrderByReleasedDescTitleAsc(Integer year);

    List<Movie> findByTitleContainingOrderByReleasedDesc(String fragment);
}
```

Nếu không ghi `Asc` hoặc `Desc`, không nên dựa vào thứ tự ngầm định. Hãy chỉ định hướng sắp xếp để tên phương thức thể hiện rõ yêu cầu.

### 3.1. Nhiều tiêu chí sắp xếp

Thứ tự được áp dụng từ trái sang phải. Ví dụ:

```java
List<Movie> findByReleasedGreaterThanOrderByReleasedDescTitleAscMovieIdAsc(
        Integer year);
```

Thứ tự ưu tiên là `released DESC`, tiếp theo `title ASC`, rồi `movieId ASC`. Tiêu chí phụ hữu ích khi nhiều bản ghi có cùng giá trị ở tiêu chí chính, nhất là khi truy vấn còn giới hạn số kết quả.

Tên method có thể dài nếu có nhiều tiêu chí. Nếu quy tắc sắp xếp thay đổi theo màn hình hoặc tham số request, dùng `Sort` thay vì tạo nhiều method gần giống nhau.

## 4. First và Top: giới hạn số kết quả

`First` và `Top` có thể dùng thay thế cho nhau để giới hạn kết quả. Có thể thêm số ngay sau từ khóa để xác định số lượng tối đa. Nếu không ghi số, giới hạn mặc định là một kết quả.

| Tên method | Giới hạn |
|---|---:|
| `findFirstByTitle(String title)` | 1 |
| `findTopByTitle(String title)` | 1 |
| `findFirst5ByTitle(String title)` | 5 |
| `findTop10ByTitle(String title)` | 10 |

Ví dụ tìm một phim mới nhất trong số các phim có cùng tiêu đề:

```java
Optional<Movie> findFirstByTitleOrderByReleasedDesc(String title);
```

Vì có `OrderByReleasedDesc`, phim phát hành gần nhất được chọn. Dùng `Optional<Movie>` thể hiện rõ trường hợp không tìm thấy kết quả.

Ví dụ lấy ba phim mới nhất sau một năm nhất định:

```java
List<Movie> findTop3ByReleasedGreaterThanOrderByReleasedDescTitleAsc(
        Integer year);
```

`Top3` giới hạn tối đa ba kết quả; `OrderBy` quyết định ba kết quả nào đứng đầu.

### 4.1. Vì sao First/Top nên đi cùng OrderBy?

Nếu dùng:

```java
Optional<Movie> findFirstByTitle(String title);
```

thì method giới hạn kết quả còn một, nhưng không mô tả phim nào cần được chọn nếu có nhiều phim cùng tiêu đề. Không nên dựa vào thứ tự tự nhiên của node trong Neo4j.

Nếu nghiệp vụ muốn phim mới nhất, viết:

```java
Optional<Movie> findFirstByTitleOrderByReleasedDescMovieIdAsc(String title);
```

`released DESC` chọn năm mới nhất; `movieId ASC` làm tiêu chí phụ khi nhiều phim có cùng năm. Quy tắc này giúp kết quả có tính xác định hơn.

## 5. Kết hợp Distinct, OrderBy, First và Top

Các từ khóa có thể kết hợp trong cùng method subject và predicate nếu store hỗ trợ các tính năng tương ứng:

```java
List<Person> findDistinctTop5ByActedInTitleOrderByNameAsc(String title);
```

Có thể diễn giải:

- `find`: truy vấn danh sách.
- `Distinct`: loại bỏ kết quả Person trùng.
- `Top5`: tối đa năm kết quả.
- `ByActedInTitle`: lọc qua relationship `actedIn` tới property `title` của Movie.
- `OrderByNameAsc`: sắp xếp tên tăng dần.

Để chọn đúng năm người theo tên, thứ tự sắp xếp cần được xác định rõ. Nếu chỉ viết `Top5` mà không có `OrderBy`, tập kết quả được giới hạn nhưng thứ tự lựa chọn không được bảo đảm theo yêu cầu nghiệp vụ.

## 6. Phân biệt OrderBy tĩnh với Sort động

`OrderBy` ghi cố định tiêu chí sắp xếp trong tên method. `Sort` cho phép caller truyền thứ tự lúc gọi:

```java
List<Movie> findByReleasedGreaterThan(Integer year, Sort sort);
```

Service có thể gọi:

```java
List<Movie> newestFirst = movieRepository.findByReleasedGreaterThan(
        2000,
        Sort.by(
                Sort.Order.desc("released"),
                Sort.Order.asc("title")
        )
);
```

Chọn `OrderBy` khi thứ tự là quy tắc cố định của truy vấn. Chọn `Sort` khi nhiều màn hình hoặc use case cần sắp xếp khác nhau. Tên property trong `Sort` cần khớp property Java được mapping.

Không truyền đồng thời `Sort` và `Pageable` vào cùng method vì `Pageable` đã bao gồm thông tin sắp xếp. Các kiểu tham số đặc biệt cũng có quy tắc kết hợp riêng theo phiên bản Spring Data.

## 7. Kết hợp First/Top với Pageable và Limit

Từ SDN 8.1.x, tài liệu query methods mô tả các tham số `Pageable`, `Sort` và `Limit`. `Top` có thể kết hợp với `Pageable`: `Top` đặt giới hạn tổng thể, còn `Pageable` có thể giới hạn thêm phạm vi trang. Không kết hợp `Pageable` với `Limit` vì cả hai đều mang thông tin giới hạn; `First`/`Top` cũng không trộn với tham số `Limit` trong cùng method.

Ví dụ:

```java
Page<Movie> queryTop20ByReleasedGreaterThan(
        Integer year,
        Pageable pageable);
```

`Top20` giới hạn tập kết quả tối đa 20; `Pageable` chọn trang trong phạm vi đó. Nếu chỉ cần duyệt trang tiếp theo và không cần tổng số trang, `Slice<Movie>` có thể phù hợp hơn `Page<Movie>` vì `Page` có thể cần thêm count query để tính tổng số kết quả.

Nếu phiên bản SDN của dự án chưa hỗ trợ tham số `Limit`, hoặc API hiện tại khác với tài liệu mới, hãy dùng cú pháp `First`/`Top` và `Pageable` được phiên bản đó công bố. Không sao chép một method signature từ tài liệu mới vào dự án cũ mà chưa kiểm tra dependency.

## 8. Cách đọc và kiểm tra tên method

Khi tên method dài, hãy phân tích từng phần trước khi viết code:

```java
List<Movie> findTop3ByReleasedGreaterThanOrderByReleasedDescTitleAsc(
        Integer year);
```

| Phần | Ý nghĩa |
|---|---|
| `find` | Truy vấn entity |
| `Top3` | Giới hạn tối đa ba kết quả |
| `By` | Bắt đầu phần điều kiện |
| `ReleasedGreaterThan` | `released > year` |
| `OrderByReleasedDesc` | Năm phát hành giảm dần |
| `TitleAsc` | Tiêu đề tăng dần khi năm bằng nhau |

Spring Data phân tích method khi repository infrastructure khởi tạo. Property path không hợp lệ hoặc cú pháp không được hỗ trợ có thể khiến application context thất bại ngay lúc startup. Vì vậy, hãy tạo repository method từng bước và kiểm tra lỗi khởi động thay vì chờ đến khi request đầu tiên chạy.

## 9. Khi nào nên dùng @Query thay cho derived query?

Derived query phù hợp khi điều kiện lọc, thứ tự và giới hạn có thể diễn đạt rõ bằng property của entity. Nên chuyển sang `@Query` hoặc `Neo4jClient` khi:

- Câu truy vấn cần nhiều nhánh `MATCH`, `OPTIONAL MATCH` hoặc pattern graph phức tạp.
- Cần aggregation, `collect`, `count(DISTINCT ...)` hoặc projection tùy chỉnh.
- Cần điều khiển chính xác vị trí `DISTINCT`, `ORDER BY`, `SKIP`, `LIMIT` trong Cypher.
- Cần truy vấn một relationship có property riêng hoặc nhiều bước `WITH`.
- Tên method trở nên dài, khó đọc hoặc phụ thuộc vào hành vi parser khó nhận biết.

Ví dụ truy vấn Cypher tường minh:

```java
@Query("""
    MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
    WHERE m.title = $title
    RETURN DISTINCT p
    ORDER BY p.name ASC
    LIMIT 5
    """)
List<Person> findTopFiveDistinctActorsForMovie(String title);
```

Trong `@Query`, ta kiểm soát trực tiếp Cypher được gửi tới Neo4j. Cần bảo đảm phần `RETURN` tương thích với kiểu kết quả Java và các biến được tham số hóa đúng cách.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng `Top` hoặc `First` mà không có `OrderBy` | Kết quả được giới hạn nhưng không xác định theo thứ tự nghiệp vụ | Thêm tiêu chí sắp xếp và tiêu chí phụ khi cần |
| Nhầm `Distinct` với uniqueness constraint | Vẫn có thể tạo node trùng property trong database | Tạo constraint riêng cho ID/property nghiệp vụ |
| Dùng tên property database thay cho property Java | Parser không tìm thấy property path | Dùng tên property trong entity và mapping metadata |
| Viết sai đường dẫn relationship | Method không được parse hoặc truy vấn sai | Đối chiếu field relationship và property của node đích |
| Dùng `First` với return type không phù hợp | Khó biểu diễn trường hợp không có kết quả | Dùng entity đơn, `Optional<T>` hoặc collection theo nhu cầu |
| Kết hợp `Pageable` và `Sort` | Tham số đặc biệt xung đột | Đặt `Sort` trong `Pageable` |
| Kết hợp `Pageable` và `Limit` | Hai tham số cùng giới hạn kết quả | Chọn một cơ chế giới hạn phù hợp |
| Giả định mọi phiên bản đều hỗ trợ cùng cú pháp | Repository có thể lỗi khi khởi tạo | Đối chiếu tài liệu đúng phiên bản và kiểm thử startup |
| Dùng derived query cho graph traversal quá phức tạp | Method name khó bảo trì, khó kiểm soát Cypher | Dùng `@Query` hoặc `Neo4jClient` |

## 11. Checklist trước khi sử dụng

- Kiểm tra phiên bản Spring Data Neo4j thực tế được resolve trong dự án.
- Xác nhận `Distinct`, `OrderBy`, `First` và `Top` nằm trong khả năng của phiên bản/store.
- Dùng đúng tên property Java và đường dẫn relationship đã mapping.
- Thêm `OrderBy` rõ ràng khi dùng `First` hoặc `Top`.
- Thêm tiêu chí phụ để kết quả ổn định khi giá trị sắp xếp chính bằng nhau.
- Chọn return type phù hợp: `Optional<T>`, `T` hoặc `List<T>`.
- Không nhầm `Distinct` với uniqueness constraint ở database.
- Không kết hợp các tham số đặc biệt bị loại trừ như `Pageable` với `Sort` riêng hoặc `Limit`.
- Kiểm tra repository được tạo thành công khi application context khởi động.
- Dùng `@Query` khi cần kiểm soát Cypher chi tiết hơn.

## 12. Bài tập thực hành

1. Viết `findDistinctByActedInTitle(String title)` để tìm danh sách người duy nhất tham gia một phim.
2. Viết `findByReleasedGreaterThanOrderByReleasedDescTitleAsc(Integer year)` để sắp xếp phim theo năm và tiêu đề.
3. Viết `findFirstByTitleOrderByReleasedDesc(String title)` trả về `Optional<Movie>` và giải thích phim nào được chọn.
4. Viết `findTop3ByReleasedGreaterThanOrderByReleasedDescTitleAsc(Integer year)` để lấy ba phim mới nhất.
5. Kết hợp `Distinct` và `Top` cho truy vấn người theo đường dẫn relationship; kiểm tra method trên đúng phiên bản SDN.
6. Thay `OrderBy` tĩnh bằng tham số `Sort` để cho phép caller chọn thứ tự.
7. Tạo truy vấn `@Query` có `RETURN DISTINCT`, `ORDER BY` và `LIMIT`; so sánh độ rõ ràng với derived query.
8. Cố ý viết sai tên property trong method, quan sát lỗi khi repository khởi tạo và sửa lại.

Khi hoàn thành, bạn cần phân tích được subject và predicate của tên method, hiểu `Distinct` loại bỏ kết quả trùng, `OrderBy` xác định thứ tự và `First`/`Top` giới hạn số dòng trả về. Quan trọng hơn, bạn biết đối chiếu khả năng của phiên bản SDN đang dùng để chọn derived query phù hợp hoặc chuyển sang Cypher tường minh khi cần kiểm soát sâu hơn.

## Tài liệu tham khảo

- [Spring Data Neo4j — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j — Repository Query Keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)
- [Spring Data Neo4j 7.5 — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/7.5/repositories/query-methods-details.html)
