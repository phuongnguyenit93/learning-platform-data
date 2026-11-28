# So sánh bằng, khác, khoảng giá trị và mốc thời gian

Spring Data Neo4j (SDN) cho phép khai báo truy vấn từ tên phương thức repository. Thay vì viết Cypher cho mọi điều kiện đơn giản, ta đặt tên phương thức theo property và toán tử cần dùng. Spring Data phân tích tên đó, tạo truy vấn phù hợp với Neo4j và ánh xạ kết quả thành entity hoặc projection.

Bài học này tập trung vào các phép so sánh thường gặp: bằng, khác, lớn hơn, lớn hơn hoặc bằng, nhỏ hơn, nhỏ hơn hoặc bằng, nằm trong khoảng và so sánh ngày giờ. Nắm được quy tắc đặt tên giúp viết repository dễ đọc, đồng thời biết khi nào truy vấn suy diễn đủ dùng và khi nào nên chuyển sang `@Query` để kiểm soát Cypher chi tiết hơn.

## 1. Cấu trúc cơ bản của derived query

Một derived query thường có cấu trúc:

```text
findBy + Property + Operator
```

Ví dụ:

```java
List<Movie> findByTitle(String title);
List<Movie> findByReleaseYearGreaterThan(Integer year);
```

`findBy` cho biết repository cần tìm entity. `Title` và `ReleaseYear` là property trong entity Java. `GreaterThan` là toán tử được Spring Data nhận diện từ tên phương thức.

Giả sử entity phim có các property sau:

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

    private LocalDate releaseDate;

    private LocalDateTime createdAt;
}
```

Repository có thể kế thừa `Neo4jRepository`:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {
}
```

Các ví dụ tiếp theo sử dụng entity và repository này. Constructor, getter và setter được lược bỏ để tập trung vào cách đặt tên truy vấn.

## 2. So sánh bằng

Khi không chỉ định toán tử, Spring Data mặc định so sánh bằng. Có thể viết `findByTitle`, `findByTitleIs` hoặc `findByTitleEquals`:

```java
List<Movie> findByTitle(String title);

List<Movie> findByTitleIs(String title);

List<Movie> findByTitleEquals(String title);
```

Các tên trên đều biểu đạt điều kiện bằng trên property `title`. Với chuỗi, phép so sánh mặc định phân biệt chữ hoa và chữ thường. Nếu cần bỏ qua khác biệt hoa thường, dùng `IgnoreCase`:

```java
List<Movie> findByTitleIgnoreCase(String title);
```

Với property số hoặc trạng thái, cách đặt tên tương tự:

```java
List<Movie> findByStatus(String status);

List<Movie> findByReleaseYear(Integer releaseYear);
```

Ví dụ tương đương về ý nghĩa trong Cypher:

```cypher
MATCH (m:Movie)
WHERE m.title = $title
RETURN m;
```

Tên property trong derived query phải khớp với property Java mà SDN ánh xạ. Nếu field Java dùng `releaseYear` còn property Neo4j được đổi tên bằng `@Property("release_year")`, phương thức vẫn dùng `findByReleaseYear` vì parser dựa trên mô hình Java.

Nếu property được kỳ vọng duy nhất, hãy bảo đảm quy tắc duy nhất ở database bằng constraint phù hợp. Không nên dùng kiểu trả về `Optional<Movie>` chỉ vì dự đoán có một kết quả; chỉ dùng `Optional` khi nghiệp vụ và dữ liệu bảo đảm tối đa một entity.

## 3. So sánh khác

Dùng `Not` để tìm các entity có giá trị khác tham số:

```java
List<Movie> findByStatusNot(String status);

List<Movie> findByReleaseYearNot(Integer releaseYear);
```

Ví dụ truy vấn Cypher tương đương về ý nghĩa:

```cypher
MATCH (m:Movie)
WHERE m.status <> $status
RETURN m;
```

Trong Cypher, so sánh với `null` tạo ra giá trị không xác định (`null`), không phải `true`. Vì vậy, `status <> 'ARCHIVED'` không tự động bao gồm node không có property `status`. Nếu nghiệp vụ muốn xử lý property rỗng, hãy diễn đạt rõ điều kiện bằng `IsNull` hoặc `IsNotNull` thay vì trông chờ `Not` bao gồm các giá trị thiếu.

```java
List<Movie> findByStatusIsNull();

List<Movie> findByStatusIsNotNull();
```

Các tên `findByStatusNull()` và `findByStatusNotNull()` cũng là dạng từ khóa thường dùng trong Spring Data. Trong codebase, nên chọn một cách viết thống nhất để người đọc dễ nhận diện.

## 4. So sánh lớn hơn và nhỏ hơn

Với kiểu dữ liệu có thứ tự như số, ngày và thời gian, có thể dùng các toán tử sau:

| Từ khóa | Ý nghĩa | Toán tử Cypher tương ứng |
|---|---|---|
| `GreaterThan` / `IsGreaterThan` | Lớn hơn | `>` |
| `GreaterThanEqual` / `IsGreaterThanEqual` | Lớn hơn hoặc bằng | `>=` |
| `LessThan` / `IsLessThan` | Nhỏ hơn | `<` |
| `LessThanEqual` / `IsLessThanEqual` | Nhỏ hơn hoặc bằng | `<=` |

Ví dụ lọc phim có điểm đánh giá lớn hơn 8:

```java
List<Movie> findByRatingGreaterThan(Integer rating);
```

Lọc phim phát hành từ năm 2020 trở đi:

```java
List<Movie> findByReleaseYearGreaterThanEqual(Integer year);
```

Lọc phim có điểm nhỏ hơn 5:

```java
List<Movie> findByRatingLessThan(Integer rating);
```

Lọc phim có năm phát hành không vượt quá 2010:

```java
List<Movie> findByReleaseYearLessThanEqual(Integer year);
```

Khi gọi phương thức, truyền giá trị làm biên so sánh:

```java
List<Movie> highlyRated = movieRepository.findByRatingGreaterThan(8);
List<Movie> recentMovies = movieRepository.findByReleaseYearGreaterThanEqual(2020);
```

Đọc tên phương thức từ trái sang phải: property nào được kiểm tra, toán tử nào áp dụng và tham số nào làm giá trị so sánh. Dùng `GreaterThanEqual` khi cần lấy cả giá trị đúng bằng biên; dùng `GreaterThan` khi chỉ lấy giá trị lớn hơn.

## 5. Lọc trong một khoảng với Between

`Between` dùng hai tham số để tìm giá trị nằm trong một khoảng:

```java
List<Movie> findByReleaseYearBetween(Integer fromYear, Integer toYear);

List<Movie> findByRatingBetween(Integer minRating, Integer maxRating);
```

Ví dụ:

```java
List<Movie> movies = movieRepository.findByReleaseYearBetween(2015, 2022);
```

Về ý nghĩa, khoảng `Between` bao gồm cả hai biên, tương đương điều kiện lớn hơn hoặc bằng giá trị đầu và nhỏ hơn hoặc bằng giá trị cuối:

```cypher
MATCH (m:Movie)
WHERE m.releaseYear >= $fromYear
  AND m.releaseYear <= $toYear
RETURN m;
```

Thứ tự tham số rất quan trọng: tham số thứ nhất là cận dưới, tham số thứ hai là cận trên. Ứng dụng nên kiểm tra `fromYear <= toYear` trước khi gọi repository để tránh đầu vào sai nghiệp vụ.

Có thể kết hợp nhiều điều kiện bằng `And`:

```java
List<Movie> findByReleaseYearBetweenAndRatingGreaterThanEqual(
        Integer fromYear,
        Integer toYear,
        Integer minRating);
```

Phương thức này tìm phim trong khoảng năm phát hành và có rating tối thiểu bằng `minRating`. Tên phương thức dài dần khi số điều kiện tăng; nếu truy vấn trở nên khó đọc hoặc có nhiều nhánh logic, cân nhắc `@Query` với Cypher tường minh.

## 6. So sánh ngày và thời gian

Neo4j hỗ trợ kiểu temporal như `DATE`, `LOCAL DATETIME` và `ZONED DATETIME`. SDN ánh xạ các kiểu Java tương ứng để repository có thể so sánh trên property ngày giờ. Chọn kiểu theo ý nghĩa nghiệp vụ:

- `LocalDate`: ngày lịch, không có giờ và múi giờ, phù hợp với ngày phát hành hoặc ngày sinh.
- `LocalDateTime`: ngày giờ địa phương, không chứa múi giờ; phù hợp khi nghiệp vụ thực sự dùng giờ địa phương.
- `Instant` hoặc kiểu có offset/zone phù hợp: thời điểm tuyệt đối cần so sánh nhất quán giữa nhiều múi giờ.

### Before và After

Với property `releaseDate` kiểu `LocalDate`, có thể tìm phim phát hành trước hoặc sau một ngày:

```java
List<Movie> findByReleaseDateBefore(LocalDate date);

List<Movie> findByReleaseDateAfter(LocalDate date);
```

`Before` biểu đạt nhỏ hơn mốc ngày, `After` biểu đạt lớn hơn mốc ngày. Nếu cần bao gồm chính ngày đó, dùng `LessThanEqual` hoặc `GreaterThanEqual`:

```java
List<Movie> findByReleaseDateLessThanEqual(LocalDate date);

List<Movie> findByReleaseDateGreaterThanEqual(LocalDate date);
```

### Between với ngày giờ

Với `createdAt` kiểu `LocalDateTime`, có thể lọc bản ghi trong một khoảng:

```java
List<Movie> findByCreatedAtBetween(
        LocalDateTime from,
        LocalDateTime to);
```

Ví dụ gọi:

```java
LocalDateTime from = LocalDateTime.of(2026, 1, 1, 0, 0);
LocalDateTime to = LocalDateTime.of(2026, 2, 1, 0, 0);

List<Movie> createdInJanuary = movieRepository.findByCreatedAtBetween(from, to);
```

Khi lọc các sự kiện theo tháng hoặc ngày, khoảng nửa mở `[from, to)` thường dễ dùng hơn: lấy thời điểm lớn hơn hoặc bằng đầu kỳ và nhỏ hơn đầu kỳ tiếp theo. Cách này tránh phải tạo mốc cuối ngày như `23:59:59.999...` và không bỏ sót dữ liệu có độ chính xác thời gian cao hơn.

```java
List<Movie> findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        LocalDateTime fromInclusive,
        LocalDateTime toExclusive);
```

Ví dụ lọc tháng 1 năm 2026:

```java
List<Movie> january = movieRepository
        .findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
                LocalDateTime.of(2026, 1, 1, 0, 0),
                LocalDateTime.of(2026, 2, 1, 0, 0));
```

Nếu dữ liệu biểu diễn thời điểm toàn cầu, hãy thống nhất lưu và truy vấn cùng một quy ước múi giờ, thường dùng UTC. Không trộn `LocalDateTime` mang ý nghĩa giờ địa phương với thời điểm UTC nếu chưa chuyển đổi rõ ràng.

## 7. Kết hợp điều kiện bằng And và Or

Derived query có thể ghép nhiều điều kiện bằng `And` hoặc `Or`:

```java
List<Movie> findByStatusAndReleaseYearGreaterThanEqual(
        String status,
        Integer year);

List<Movie> findByReleaseYearLessThanOrRatingGreaterThan(
        Integer year,
        Integer rating);
```

Phương thức thứ nhất tương ứng với trạng thái khớp và năm phát hành từ mốc trở đi. Phương thức thứ hai diễn đạt điều kiện năm phát hành nhỏ hơn mốc hoặc rating lớn hơn ngưỡng.

Khi trộn `And` và `Or`, cách phân nhóm biểu thức có thể khó đọc nếu tên phương thức dài. Đừng dựa vào trực giác để đoán độ ưu tiên toán tử; hãy kiểm tra truy vấn được tạo hoặc chuyển sang `@Query` để viết rõ điều kiện và dấu ngoặc logic.

Có thể thêm sắp xếp tĩnh bằng `OrderBy`:

```java
List<Movie> findByReleaseYearGreaterThanEqualOrderByReleaseYearAscTitleAsc(
        Integer year);
```

Phương thức trên lọc theo năm phát hành rồi sắp xếp tăng dần theo năm và tiêu đề. Với yêu cầu sắp xếp thay đổi theo request, dùng tham số `Sort` hoặc `Pageable` nếu chữ ký repository và kiểu truy vấn hỗ trợ.

## 8. Bảng tra cứu nhanh

| Nhu cầu | Ví dụ tên phương thức |
|---|---|
| Bằng | `findByStatus(String status)` |
| Bằng tường minh | `findByStatusIs(String status)` |
| Khác | `findByStatusNot(String status)` |
| Lớn hơn | `findByRatingGreaterThan(Integer rating)` |
| Lớn hơn hoặc bằng | `findByReleaseYearGreaterThanEqual(Integer year)` |
| Nhỏ hơn | `findByRatingLessThan(Integer rating)` |
| Nhỏ hơn hoặc bằng | `findByReleaseYearLessThanEqual(Integer year)` |
| Trong khoảng | `findByReleaseYearBetween(Integer from, Integer to)` |
| Trước ngày | `findByReleaseDateBefore(LocalDate date)` |
| Sau ngày | `findByReleaseDateAfter(LocalDate date)` |
| Ngày không muộn hơn mốc | `findByReleaseDateLessThanEqual(LocalDate date)` |
| Ngày từ mốc trở đi | `findByReleaseDateGreaterThanEqual(LocalDate date)` |
| Property rỗng | `findByStatusIsNull()` |
| Property khác rỗng | `findByStatusIsNotNull()` |

## 9. Khi nào nên dùng @Query thay cho derived query?

Derived query phù hợp với điều kiện đơn giản, tên ngắn và bám sát property của entity. Dùng `@Query` khi:

- Điều kiện có nhiều nhánh `AND`/`OR` và cần kiểm soát nhóm logic.
- Truy vấn đi qua nhiều relationship hoặc cần pattern Cypher cụ thể.
- Cần aggregation như `count`, `avg`, `collect` hoặc projection phức tạp.
- Cần sử dụng hàm temporal, phép biến đổi hoặc biểu thức Cypher không được biểu diễn gọn bằng tên phương thức.
- Tên derived query trở nên quá dài, khó hiểu hoặc khó bảo trì.

Ví dụ viết rõ điều kiện bằng Cypher:

```java
@Query("""
    MATCH (m:Movie)
    WHERE m.releaseYear >= $fromYear
      AND m.releaseYear <= $toYear
      AND m.rating >= $minRating
    RETURN m
    ORDER BY m.releaseYear, m.title
    """)
List<Movie> findMoviesInRange(
        @Param("fromYear") Integer fromYear,
        @Param("toYear") Integer toYear,
        @Param("minRating") Integer minRating);
```

Với truy vấn `@Query`, tên tham số trong Cypher phải khớp với giá trị được bind. Câu truy vấn cần trả về cấu trúc phù hợp với kiểu kết quả; nếu trả về entity `Movie`, cần trả node và dữ liệu quan hệ cần thiết cho mapping đó.

## 10. Những lưu ý về null, kiểu dữ liệu và biên khoảng

- So sánh `=` hoặc `<>` trong Cypher không xem `null` như một giá trị thông thường. Dùng `IsNull`/`IsNotNull` để diễn đạt rõ sự tồn tại của property.
- `GreaterThan` và `LessThan` loại trừ giá trị bằng biên; `GreaterThanEqual` và `LessThanEqual` bao gồm giá trị bằng biên.
- `Between` biểu đạt khoảng có cận dưới và cận trên; xác định rõ thứ tự hai tham số và kiểm tra đầu vào.
- Các phép so sánh chỉ có ý nghĩa khi kiểu property và kiểu tham số tương thích. Tránh lưu năm dưới dạng chuỗi nếu cần so sánh số học.
- Với thời gian, phân biệt ngày lịch, giờ địa phương và thời điểm toàn cầu. Chuẩn hóa múi giờ trước khi so sánh dữ liệu từ nhiều vùng.
- Nếu property có thể không tồn tại, hãy xác định rõ nghiệp vụ có muốn loại các node đó khỏi kết quả hay xử lý riêng.
- Kiểm tra truy vấn sinh ra trên phiên bản SDN đang dùng khi phụ thuộc vào một toán tử hoặc cách chuyển đổi temporal cụ thể.

## 11. Tự kiểm tra

1. `findByReleaseYear(2020)` biểu đạt phép so sánh nào?
2. Khác biệt giữa `GreaterThan` và `GreaterThanEqual` là gì?
3. `findByReleaseYearBetween(2015, 2022)` xử lý hai biên như thế nào?
4. Vì sao `findByStatusNot("ARCHIVED")` không nhất thiết bao gồm node thiếu property `status`?
5. Khi cần lọc phim phát hành trước một ngày, nên dùng `Before` hay `LessThanEqual` nếu muốn bao gồm ngày mốc?
6. Vì sao khoảng thời gian nửa mở `[from, to)` hữu ích khi lọc sự kiện theo tháng?
7. Khi nào nên thay một derived query dài bằng `@Query`?
8. Vì sao kiểu Java của tham số cần tương thích với kiểu property trong Neo4j?

Khi hiểu các từ khóa so sánh và cách chúng ánh xạ vào property, người học có thể viết derived query cho điều kiện bằng, khác, khoảng số và ngày giờ; đồng thời chọn biên so sánh chính xác và biết lúc nào cần dùng Cypher tường minh trong Spring Data Neo4j.
