# Đọc Cypher sinh tự động để xác minh đúng ý nghĩa nghiệp vụ

Spring Data Neo4j (SDN) cho phép viết truy vấn bằng tên phương thức repository, chẳng hạn `findByStatusAndReleaseYearGreaterThanEqual`. Spring Data phân tích tên phương thức, tạo Cypher và ánh xạ kết quả về entity hoặc projection. Cách viết này ngắn gọn, nhưng tên phương thức chỉ thể hiện ý định ở mức Java. Để chắc chắn truy vấn thực hiện đúng quy tắc nghiệp vụ, cần biết cách đọc Cypher được sinh ra và đối chiếu từng phần với dữ liệu thực tế.

Việc kiểm tra không dừng ở câu `MATCH` và `WHERE`. Hãy xem cả tham số được bind, hướng relationship, điều kiện `null`, thứ tự sắp xếp, giới hạn kết quả và cấu trúc `RETURN` mà SDN cần để ánh xạ entity. Sau đó xác minh bằng integration test và kế hoạch thực thi khi truy vấn cần tối ưu.

## 1. Từ tên phương thức đến Cypher

Giả sử ứng dụng quản lý phim với entity:

```java
@Node("Movie")
public class Movie {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    private String status;

    private Integer releaseYear;

    private Integer rating;
}
```

Repository khai báo truy vấn:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    List<Movie> findByStatusAndReleaseYearGreaterThanEqualOrderByReleaseYearAscTitleAsc(
            String status,
            Integer year);
}
```

Đọc tên phương thức theo các phần:

| Phần tên | Ý nghĩa |
|---|---|
| `findBy` | Tìm entity phù hợp |
| `Status` | Property `status` |
| `And` | Kết hợp hai điều kiện bằng logic AND |
| `ReleaseYear` | Property `releaseYear` |
| `GreaterThanEqual` | Giá trị lớn hơn hoặc bằng tham số |
| `OrderByReleaseYearAscTitleAsc` | Sắp xếp tăng dần theo năm rồi theo tiêu đề |

Ý nghĩa nghiệp vụ dự kiến là: lấy các phim có trạng thái bằng giá trị truyền vào, có năm phát hành từ năm chỉ định trở đi, sau đó sắp xếp theo năm và tiêu đề tăng dần.

Cypher minh họa về logic có thể tương đương như sau:

```cypher
MATCH (movie:Movie)
WHERE movie.status = $status
  AND movie.releaseYear >= $year
RETURN movie
ORDER BY movie.releaseYear ASC, movie.title ASC;
```

Đây là cách diễn đạt logic để đọc và đối chiếu, không phải cam kết chuỗi Cypher chính xác mà mọi phiên bản SDN sẽ phát ra. Truy vấn thực tế có thể chứa alias, biểu thức chiếu property, ID kỹ thuật hoặc phần mở rộng để ánh xạ entity và relationship. Khi xác minh, hãy xem câu truy vấn thực tế từ đúng phiên bản ứng dụng đang chạy.

## 2. Vì sao phải đọc Cypher được sinh ra?

Một tên phương thức có thể trông hợp lý nhưng vẫn không phản ánh đầy đủ ý định nghiệp vụ. Một số lỗi chỉ xuất hiện khi xem truy vấn hoặc kết quả trên dữ liệu đại diện:

- Dùng `GreaterThan` trong khi quy tắc cần bao gồm cả giá trị tại ngưỡng.
- Dùng `Not` nhưng quên rằng property không tồn tại không thỏa phép so sánh khác.
- Truy vấn qua relationship theo sai hướng hoặc sai type.
- Kết hợp `And` và `Or` với nhóm điều kiện khác dự kiến.
- Sắp xếp trước khi phân trang theo tiêu chí không ổn định.
- Trả về dữ liệu không đủ để ánh xạ entity hoặc trả quá nhiều dữ liệu không cần thiết.
- Điều kiện lọc đúng nhưng kế hoạch thực thi quét quá nhiều node hoặc relationship.

Đọc Cypher giúp chuyển câu hỏi từ “tên phương thức có vẻ đúng” thành “database đang tìm pattern nào, áp dụng điều kiện nào và trả dữ liệu gì?”.

## 3. Bật log để quan sát truy vấn

Trong môi trường phát triển, có thể tăng mức log của package Spring Data Neo4j để quan sát hoạt động mapping và truy vấn. Ví dụ cấu hình Spring Boot:

```yaml
logging:
  level:
    org.springframework.data.neo4j: DEBUG
    org.neo4j.driver: INFO
```

Mức logger và nội dung log cụ thể có thể khác theo phiên bản SDN, Neo4j Java Driver và cấu hình logging. Nếu chưa thấy câu Cypher, hãy kiểm tra tài liệu logging của đúng phiên bản đang dùng và logger của thành phần thực thi truy vấn. Chỉ tăng lên `TRACE` trong thời gian ngắn khi cần chẩn đoán sâu.

Quy trình quan sát nên thực hiện trong môi trường local hoặc integration test:

1. Bật mức log cần thiết.
2. Khởi động ứng dụng với một database thử nghiệm.
3. Gọi đúng phương thức repository cần kiểm tra.
4. Tìm log tương ứng với lần thực thi đó.
5. Ghi lại câu Cypher và các tham số cần thiết để đối chiếu.
6. Tắt log chi tiết sau khi hoàn tất.

Không bật log tham số nhạy cảm trong production nếu chưa có chính sách bảo vệ log. Truy vấn có thể chứa email, tên, token hoặc dữ liệu nghiệp vụ riêng tư. Khi chia sẻ log để review, hãy che dữ liệu cá nhân và thông tin xác thực.

### Phân biệt câu truy vấn và tham số

Cypher được sinh thường dùng tham số thay vì ghép giá trị trực tiếp vào chuỗi. Ví dụ:

```cypher
MATCH (m:Movie)
WHERE m.status = $status
  AND m.releaseYear >= $year
RETURN m;
```

Các giá trị thực tế được bind riêng:

```text
status = "PUBLISHED"
year = 2020
```

Khi đọc log, hãy xác minh cả hai phần. Một câu Cypher đúng nhưng bind nhầm tham số hoặc bind sai kiểu vẫn có thể cho kết quả sai. Việc truyền tham số cũng giúp tránh ghép input người dùng trực tiếp vào Cypher.

## 4. Đọc từng phần trong Cypher

Khi mở log, có thể phân tích truy vấn theo thứ tự sau:

```cypher
MATCH (m:Movie)
WHERE m.status = $status
  AND m.releaseYear >= $year
RETURN m
ORDER BY m.releaseYear ASC, m.title ASC
SKIP $skip
LIMIT $limit;
```

| Thành phần | Câu hỏi cần kiểm tra |
|---|---|
| `MATCH` | Có tìm đúng label và pattern node/relationship không? |
| `WHERE` | Có đúng property, toán tử và cách nhóm điều kiện không? |
| Tham số | Có bind đúng giá trị, kiểu và thứ tự không? |
| `RETURN` | Có trả về node, relationship hoặc projection đúng với kiểu kết quả không? |
| `ORDER BY` | Có sắp xếp theo đúng thứ tự và chiều tăng/giảm không? |
| `SKIP`, `LIMIT` | Có phân trang đúng và có thứ tự ổn định không? |

Không phải derived query nào cũng sinh đủ tất cả các mệnh đề trên. Ví dụ, truy vấn không yêu cầu phân trang sẽ không nhất thiết có `SKIP` hoặc `LIMIT`.

### Kiểm tra MATCH và label

Nếu repository tìm `Movie`, hãy xác nhận pattern sử dụng đúng label. Một lỗi phổ biến là entity dùng label khác với dữ liệu đang lưu, hoặc dữ liệu cũ có label chưa được chuẩn hóa. Khi `MATCH` không tìm được node, hãy kiểm tra label trước khi kết luận điều kiện `WHERE` sai.

Nếu truy vấn có relationship, đọc đầy đủ pattern:

```cypher
MATCH (a:Actor)-[:ACTED_IN]->(m:Movie)
```

Pattern trên chỉ đi theo chiều từ `Actor` tới `Movie`. Nếu nghiệp vụ cần tìm phim từ một diễn viên qua relationship lưu theo chiều ngược, phải kiểm tra hướng trong Cypher được sinh và mapping `@Relationship(direction = ...)` của entity.

### Kiểm tra WHERE và biên so sánh

Đối chiếu toán tử với ngôn ngữ nghiệp vụ:

| Yêu cầu | Cypher cần thấy |
|---|---|
| Lớn hơn 8 | `rating > 8` |
| Từ 8 trở lên | `rating >= 8` |
| Nhỏ hơn 5 | `rating < 5` |
| Không vượt quá 5 | `rating <= 5` |
| Từ năm 2018 đến hết năm 2022 | `year >= 2018 AND year <= 2022` |

Hãy thử dữ liệu đúng tại biên. Nếu chỉ kiểm tra các giá trị nằm xa biên, test có thể không phát hiện nhầm lẫn giữa `>` và `>=`.

### Kiểm tra RETURN và mapping

Repository trả về `Movie` cần có kết quả phù hợp để SDN ánh xạ entity. Khi dùng projection, các alias trong `RETURN` cần phù hợp với tên property hoặc accessor của projection. Với truy vấn có relationship, hãy xác minh dữ liệu cần thiết cho mapping có nằm trong kết quả hay không.

Không nên kết luận rằng truy vấn trả về một node thì mọi relationship của node đó đều được tải. Cấu trúc dữ liệu trả về và mapping của SDN quyết định object graph được tạo. Nếu chỉ cần vài trường để hiển thị, projection thường phù hợp hơn việc tải entity graph lớn.

## 5. Xác minh ngữ nghĩa của các toán tử

Tên phương thức chỉ là cú pháp khai báo. Điều quan trọng là Cypher và kết quả thực tế có khớp quy tắc nghiệp vụ hay không.

### Bằng và khác

```java
List<Movie> findByStatus(String status);

List<Movie> findByStatusNot(String status);
```

Phương thức thứ nhất kiểm tra giá trị bằng. Phương thức thứ hai kiểm tra giá trị khác. Trong Cypher, so sánh với property không tồn tại hoặc `null` không cho kết quả `true`. Vì vậy, truy vấn `status <> $status` không tự động lấy cả node không có `status`.

Nếu nghiệp vụ yêu cầu “mọi phim chưa được đánh dấu ARCHIVED, kể cả phim chưa có status”, điều kiện phải diễn đạt cả hai trường hợp, ví dụ:

```cypher
MATCH (m:Movie)
WHERE m.status IS NULL OR m.status <> $status
RETURN m;
```

Hãy kiểm tra trường hợp thiếu property riêng biệt với trường hợp property có chuỗi rỗng. Hai trạng thái này không nhất thiết có cùng ý nghĩa.

### Khoảng giá trị

`Between` thường biểu đạt khoảng bao gồm hai biên. Khi xem Cypher, xác minh cả cận dưới và cận trên đều được áp dụng đúng toán tử. Với thời gian, khoảng nửa mở thường hữu ích:

```cypher
WHERE event.createdAt >= $fromInclusive
  AND event.createdAt < $toExclusive
```

Ví dụ lọc tháng 3: cận dưới là đầu ngày 1 tháng 3, cận trên là đầu ngày 1 tháng 4. Cách này tránh phải tự tạo thời điểm cuối ngày và không bỏ sót giá trị có độ chính xác cao hơn.

### And và Or

Tên phương thức có cả `And` và `Or` có thể khó đọc. Hãy xem Cypher để biết các điều kiện được nhóm như thế nào. Ví dụ, hai ý nghĩa sau khác nhau:

```cypher
WHERE m.status = $status
  AND (m.releaseYear >= $year OR m.rating >= $rating)
```

```cypher
WHERE (m.status = $status AND m.releaseYear >= $year)
   OR m.rating >= $rating
```

Truy vấn đầu yêu cầu status luôn khớp. Truy vấn thứ hai có thể lấy cả phim không khớp status nếu rating đạt điều kiện. Nếu biểu thức nghiệp vụ cần nhóm rõ ràng, `@Query` thường dễ review hơn một tên phương thức rất dài.

## 6. Xác minh truy vấn có relationship

Derived query có thể tham chiếu property của đối tượng liên quan nếu mô hình và quy tắc đặt tên cho phép. Khi truy vấn qua relationship, cần kiểm tra:

- Label của node nguồn và node đích.
- Relationship type.
- Hướng relationship.
- Property được lọc nằm trên node nào.
- Một node nguồn có thể khớp nhiều đường đi hay không.
- Kết quả có bị nhân bản do nhiều đường đi cùng thỏa điều kiện hay không.

Ví dụ nghiệp vụ: tìm phim có ít nhất một diễn viên tên An. Logic Cypher minh họa:

```cypher
MATCH (m:Movie)<-[:ACTED_IN]-(a:Actor)
WHERE a.name = $actorName
RETURN DISTINCT m;
```

`DISTINCT` quan trọng nếu một phim có nhiều relationship phù hợp với điều kiện. Khi đọc truy vấn được sinh, kiểm tra xem kết quả có cần loại trùng theo node phim hay nghiệp vụ muốn một hàng cho mỗi credit. Không thêm `DISTINCT` một cách máy móc vì nó có thể làm mất ý nghĩa của các bản ghi relationship riêng biệt.

Nếu phương thức repository trả về `List<Movie>`, hãy kiểm thử trường hợp cùng một phim được nối tới nhiều node hoặc nhiều relationship thỏa điều kiện. Xác nhận số phần tử và ý nghĩa mỗi phần tử đúng với hợp đồng API.

## 7. Đọc ORDER BY và phân trang

Sắp xếp là một phần của ngữ nghĩa nghiệp vụ, đặc biệt khi kết hợp phân trang. Ví dụ:

```java
Page<Movie> findByStatus(String status, Pageable pageable);
```

Khi gọi với `PageRequest`, kiểm tra truy vấn có sắp xếp theo đúng property, chiều và giới hạn hay không. Nếu dữ liệu có nhiều node cùng giá trị sắp xếp, nên thêm tiêu chí phụ ổn định như ID để giảm hiện tượng bản ghi thay đổi vị trí giữa các trang:

```java
PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("releaseYear"), Sort.Order.asc("id")));
```

Đọc phần `ORDER BY`, `SKIP` và `LIMIT` trong Cypher. Xác nhận offset của trang thứ hai là đúng và kích thước trang không vượt quá yêu cầu. Với dữ liệu thay đổi liên tục, offset pagination vẫn có thể dịch chuyển kết quả giữa các lần gọi; nếu cần duyệt tập dữ liệu rất lớn và ổn định, cân nhắc keyset/seek pagination bằng điều kiện trên khóa sắp xếp.

## 8. Từ Cypher đến kế hoạch thực thi: EXPLAIN và PROFILE

Cypher đúng về logic chưa chắc chạy hiệu quả. Khi cần tối ưu, sao chép câu truy vấn đã quan sát được, giữ nguyên cấu trúc và thay tham số bằng giá trị thử nghiệm phù hợp. Sau đó dùng `EXPLAIN` hoặc `PROFILE` trong Neo4j Browser, cypher-shell hoặc công cụ quản trị tương ứng.

```cypher
EXPLAIN
MATCH (m:Movie)
WHERE m.status = $status
  AND m.releaseYear >= $year
RETURN m;
```

`EXPLAIN` lập kế hoạch thực thi nhưng không chạy truy vấn. `PROFILE` thực thi truy vấn và cung cấp số liệu thực tế như số hàng qua từng operator, số lần truy cập dữ liệu và lượng công việc. Vì `PROFILE` thực sự chạy truy vấn, hãy cẩn trọng với câu lệnh ghi và dữ liệu production; ưu tiên dùng trên môi trường thử nghiệm hoặc với truy vấn đọc.

Khi đọc kế hoạch, chú ý:

- `NodeIndexSeek` hoặc operator tìm kiếm qua index cho điều kiện chọn lọc.
- `NodeByLabelScan` có thể hợp lý với tập dữ liệu nhỏ, nhưng cần xem xét nếu label có rất nhiều node.
- Số hàng tăng mạnh sau `Expand` có thể cho thấy truy vấn đi qua quá nhiều relationship.
- `Filter` loại nhiều hàng sau khi đã đọc dữ liệu có thể gợi ý cần index hoặc thay đổi điểm bắt đầu truy vấn.
- `Sort` trên tập kết quả lớn có thể tốn tài nguyên.
- Chênh lệch lớn giữa số hàng ước tính và thực tế có thể ảnh hưởng lựa chọn kế hoạch.

Không đánh giá hiệu năng chỉ dựa trên thời gian một lần chạy. Dùng dữ liệu gần quy mô thực, lặp lại phép đo và kiểm tra index/constraint phù hợp. `PROFILE` có overhead đo đạc, vì vậy số liệu của nó không nhất thiết bằng latency mà ứng dụng quan sát trong điều kiện production.

## 9. Viết integration test để khóa ngữ nghĩa

Log cho biết câu truy vấn được sinh, nhưng integration test mới xác nhận kết quả phù hợp với quy tắc nghiệp vụ trên dữ liệu cụ thể. Test nên tạo dữ liệu có trường hợp đúng, sai, thiếu property và nằm đúng biên.

Ví dụ kiểm tra truy vấn phim phát hành từ năm 2020 trở đi:

```java
@DataNeo4jTest
class MovieRepositoryTest {

    @Autowired
    MovieRepository movieRepository;

    @Test
    void findsPublishedMoviesFromInclusiveYear() {
        movieRepository.saveAll(List.of(
                new Movie("Old", "PUBLISHED", 2019),
                new Movie("At boundary", "PUBLISHED", 2020),
                new Movie("New", "PUBLISHED", 2024),
                new Movie("Draft", "DRAFT", 2024)
        ));

        List<Movie> result = movieRepository
                .findByStatusAndReleaseYearGreaterThanEqualOrderByReleaseYearAscTitleAsc(
                        "PUBLISHED", 2020);

        assertThat(result)
                .extracting(Movie::getTitle)
                .containsExactly("At boundary", "New");
    }
}
```

Ví dụ lược bỏ constructor và getter của `Movie`; `@DataNeo4jTest` cần được cấu hình với Neo4j test instance hoặc Testcontainers. Dữ liệu ở đúng biên năm 2020 giúp phát hiện nhầm lẫn giữa `>` và `>=`. Phim `DRAFT` xác minh điều kiện status, còn thứ tự kết quả xác minh `OrderBy`.

Với truy vấn có `Not`, hãy thêm node thiếu property. Với truy vấn thời gian, tạo dữ liệu ở đúng đầu kỳ, ngay trước cận trên và đúng cận trên. Với relationship, tạo nhiều đường đi cùng khớp để kiểm tra kết quả trùng. Test không nên chỉ kiểm tra số lượng; hãy xác nhận ID hoặc nội dung từng kết quả.

## 10. Quy trình review một derived query

Khi review một phương thức repository, thực hiện theo trình tự:

1. **Viết lại yêu cầu bằng ngôn ngữ nghiệp vụ.** Xác định đối tượng, điều kiện bắt buộc, điều kiện tùy chọn, biên và thứ tự.
2. **Đọc tên phương thức.** Tách property, toán tử, `And`/`Or`, sắp xếp và phân trang.
3. **Quan sát Cypher thực tế.** Bật log trong môi trường phát triển và gọi đúng phương thức.
4. **Kiểm tra tham số.** Xác nhận tên, giá trị, kiểu dữ liệu và thứ tự bind.
5. **Đối chiếu pattern.** Xác nhận label, relationship type, hướng và property được truy vấn.
6. **Kiểm tra kết quả.** Xem `RETURN`, mapping entity/projection, loại trùng, sắp xếp và giới hạn.
7. **Khóa ngữ nghĩa bằng integration test.** Bao gồm dữ liệu ở biên và trường hợp thiếu property.
8. **Đánh giá kế hoạch khi cần.** Dùng `EXPLAIN`/`PROFILE`, index và dữ liệu đại diện để tìm điểm tốn kém.
9. **Chọn abstraction phù hợp.** Giữ derived query khi tên ngắn và rõ; chuyển sang `@Query` nếu logic khó diễn đạt hoặc cần kiểm soát Cypher.

## 11. Những lỗi thường gặp khi đọc Cypher sinh tự động

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đọc tên phương thức mà không kiểm tra query | Không phát hiện pattern hoặc điều kiện ngoài dự kiến | Quan sát Cypher thực tế trên phiên bản đang chạy |
| Chỉ đọc Cypher mà bỏ qua tham số | Truy vấn đúng nhưng kết quả sai do bind nhầm | Kiểm tra cả giá trị và kiểu tham số |
| Không thử giá trị đúng tại biên | Nhầm `>` với `>=` hoặc khoảng bao gồm/loại trừ biên | Tạo test cho giá trị bằng cận dưới và cận trên |
| Nghĩ `Not` bao gồm property thiếu | Bỏ sót ngữ nghĩa `null` của Cypher | Xử lý `IS NULL` tường minh nếu cần |
| Không xem hướng relationship | Không tìm thấy node hoặc tìm sai đường đi | Đối chiếu `MATCH` với mô hình và direction |
| Bỏ qua `DISTINCT` và số đường đi | Có thể trả nhiều kết quả cho cùng node | Xác định đơn vị kết quả là node hay relationship |
| Chỉ kiểm tra `RETURN` có node | Entity hoặc projection có thể thiếu dữ liệu cần ánh xạ | Xác nhận cấu trúc trả về phù hợp kiểu kết quả |
| Dùng `PROFILE` tùy tiện trên truy vấn ghi production | Thực thi thay đổi dữ liệu ngoài ý muốn | Dùng môi trường thử nghiệm hoặc truy vấn đọc |
| Chia sẻ log chứa dữ liệu thật | Lộ thông tin cá nhân hoặc dữ liệu nhạy cảm | Che tham số và giới hạn log chi tiết |

## 12. Tự kiểm tra

1. Vì sao Cypher minh họa từ tên phương thức không nhất thiết giống hoàn toàn chuỗi query SDN sinh ra?
2. Khi xem log, vì sao cần kiểm tra cả câu Cypher lẫn tham số được bind?
3. Làm thế nào xác nhận `GreaterThanEqual` được sinh thành điều kiện bao gồm cận?
4. Vì sao `status <> $status` không bao gồm node thiếu property `status`?
5. Khi truy vấn qua relationship, cần xác minh những thành phần nào trong `MATCH`?
6. Khi nào `DISTINCT` là cần thiết và khi nào nó có thể làm mất ý nghĩa kết quả?
7. Khác biệt giữa `EXPLAIN` và `PROFILE` là gì?
8. Integration test nên có những dữ liệu nào để xác minh một derived query có điều kiện khoảng?

Khi có thể đọc Cypher được sinh và đối chiếu từng điều kiện với yêu cầu nghiệp vụ, người học sẽ review derived query có căn cứ, phát hiện lỗi về biên, `null`, relationship và mapping, đồng thời biết khi nào cần tối ưu hoặc chuyển sang Cypher tường minh trong Spring Data Neo4j.
