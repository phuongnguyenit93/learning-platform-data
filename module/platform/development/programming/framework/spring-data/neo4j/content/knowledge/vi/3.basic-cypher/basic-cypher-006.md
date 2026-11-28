# WITH, phạm vi biến và truy vấn nhiều giai đoạn

Trong Cypher, một truy vấn đồ thị thường không chỉ tìm node rồi trả về ngay. Ta có thể cần lọc dữ liệu, tính số lượng, sắp xếp, giữ lại một nhóm kết quả, sau đó tiếp tục đi qua relationship để lấy thêm thông tin. `WITH` giúp chia truy vấn thành các giai đoạn như vậy.

`WITH` nhận các hàng kết quả từ phần trước, chọn những biến hoặc biểu thức sẽ chuyển tiếp, có thể đổi tên, tính toán, gom nhóm và lọc chúng. Nó đồng thời tạo ranh giới phạm vi biến: chỉ những biến được đưa qua `WITH` mới còn dùng được ở phần tiếp theo. Nắm vững hai vai trò này giúp viết Cypher nhiều bước dễ đọc và tránh lỗi tham chiếu biến.

## 1. `WITH` hoạt động như một bước chuyển tiếp

Hãy hình dung Cypher xử lý kết quả theo một luồng hàng. Mỗi hàng chứa các biến đang có, chẳng hạn node `p`, node `m` hoặc một giá trị số. `WITH` tạo một tập hàng trung gian mới từ luồng đó.

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, m
WHERE m.released >= 2020
RETURN p.name AS actor, m.title AS movie
ORDER BY actor, movie
```

Truy vấn thực hiện theo thứ tự:

1. `MATCH` tìm các cặp người và phim được nối bởi relationship `ACTED_IN`.
2. `WITH p, m` chuyển hai node sang giai đoạn tiếp theo.
3. `WHERE` gắn với `WITH` lọc các hàng theo năm phát hành.
4. `RETURN` chọn các giá trị cần trả về; `ORDER BY` sắp xếp kết quả cuối.

`WITH` không phải lệnh lưu dữ liệu tạm xuống database và cũng không tạo một transaction mới. Nó tổ chức luồng xử lý logic bên trong cùng một câu lệnh Cypher. Nếu truy vấn chạy qua Spring Data Neo4j, ranh giới transaction vẫn do cấu hình transaction của ứng dụng và Spring quản lý.

Một `WITH` có thể chuyển tiếp node, relationship, scalar, list, map hoặc biểu thức được tính toán. Ta cũng có thể đặt bí danh bằng `AS`:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p.name AS actorName, m.released AS releaseYear
WHERE releaseYear >= 2020
RETURN actorName, releaseYear
```

Sau `WITH`, phần truy vấn phía sau làm việc với `actorName` và `releaseYear`. Hai biến `p` và `m` không còn trong phạm vi vì chúng không được chuyển tiếp.

## 2. Phạm vi biến: biến nào còn tồn tại sau `WITH`?

Quy tắc quan trọng nhất là: một biến chỉ còn khả dụng sau `WITH` nếu nó xuất hiện trong danh sách biểu thức của `WITH`, kể cả dưới một bí danh mới.

Ví dụ hợp lệ:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p AS actor, m.title AS movieTitle
MATCH (actor)-[:ACTED_IN]->(nextMovie:Movie)
RETURN actor.name AS actorName, movieTitle, nextMovie.title AS nextTitle
```

`p` được chuyển tiếp dưới tên `actor`, còn tiêu đề phim được chuyển tiếp dưới tên `movieTitle`. Vì thế giai đoạn tiếp theo có thể dùng `actor`, `movieTitle`; nó không thể dùng tên cũ `p` hoặc `m`.

Ví dụ lỗi phạm vi biến:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p.name AS actorName
MATCH (p)-[:ACTED_IN]->(otherMovie:Movie)
RETURN actorName, otherMovie.title
```

Đoạn trên không hợp lệ vì `p` đã bị loại khỏi phạm vi ở `WITH`. Nếu giai đoạn sau cần node người, hãy chuyển tiếp node đó:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p AS actor, p.name AS actorName
MATCH (actor)-[:ACTED_IN]->(otherMovie:Movie)
RETURN actorName, otherMovie.title
```

`WITH *` chuyển tiếp tất cả biến hiện đang có trong phạm vi:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH *
WHERE m.released >= 2020
RETURN p.name, m.title
```

Cách này tiện khi chỉ muốn thêm một bước lọc mà chưa muốn thay đổi danh sách biến. Tuy nhiên, nó có thể giữ lại nhiều biến hơn mức cần thiết và làm phạm vi truy vấn khó theo dõi. Trong truy vấn nhiều giai đoạn, nên liệt kê tường minh các biến thực sự cần dùng ở bước kế tiếp.

Khi đổi tên bằng `AS`, hãy dùng bí danh mới ở các phần sau. Ví dụ `WITH p AS actor` có nghĩa là giai đoạn tiếp theo tham chiếu `actor`, không tham chiếu `p`.

## 3. Lọc, sắp xếp và giới hạn kết quả giữa các giai đoạn

`WITH` có thể kết hợp với `WHERE`, `ORDER BY`, `SKIP` và `LIMIT`. Nhờ đó, ta kiểm soát số hàng được chuyển sang phần truy vấn tiếp theo.

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, count(DISTINCT m) AS movieCount
WHERE movieCount >= $minMovies
ORDER BY movieCount DESC, p.name
LIMIT 10
MATCH (p)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actor, movieCount, collect(DISTINCT m.title) AS movies
ORDER BY movieCount DESC, actor
```

Ở giai đoạn đầu, truy vấn đếm số phim khác nhau của mỗi người. `WHERE` giữ lại người có số phim đạt ngưỡng; `ORDER BY` sắp xếp theo số phim và tên; `LIMIT 10` chỉ chuyển tối đa mười người sang giai đoạn tiếp theo. Sau đó truy vấn tìm lại các phim của những người đã chọn và gom tiêu đề thành danh sách.

Thứ tự các bước làm thay đổi ý nghĩa truy vấn. `LIMIT 10` ở trên giới hạn mười người sau khi đã gom nhóm, trước khi tìm lại danh sách phim. Nếu đặt `LIMIT` sau lần `MATCH` thứ hai, nó có thể giới hạn mười hàng phim thay vì mười người. Khi đọc hoặc sửa truy vấn, hãy xác định mỗi `LIMIT` đang giới hạn loại hàng nào.

Có thể dùng `SKIP` và `LIMIT` để phân trang một giai đoạn:

```cypher
MATCH (m:Movie)
WITH m
ORDER BY m.released DESC, m.title
SKIP $offset
LIMIT $pageSize
RETURN m.title AS title, m.released AS released
```

Luôn dùng `ORDER BY` với tiêu chí ổn định trước khi phân trang. Nếu không có thứ tự xác định, các hàng ở từng trang có thể thay đổi giữa các lần chạy. Trong ứng dụng, truyền `offset` và `pageSize` dưới dạng tham số; đồng thời kiểm tra giới hạn kích thước trang ở tầng service.

## 4. Gom nhóm và tính toán với `WITH`

Một công dụng quan trọng của `WITH` là gom nhóm hàng và tạo giá trị tổng hợp. Khi có hàm tổng hợp như `count()`, `collect()`, `sum()`, `avg()`, `min()` hoặc `max()`, các biểu thức không tổng hợp trong cùng `WITH` trở thành khóa nhóm.

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, count(DISTINCT m) AS movieCount
RETURN p.name AS actor, movieCount
ORDER BY movieCount DESC
```

Ở đây `p` là khóa nhóm, vì vậy mỗi người tạo ra một hàng với số phim khác nhau. `count(DISTINCT m)` đếm node phim duy nhất; dùng `count(m)` nếu muốn đếm số hàng có `m`, kể cả khi một node có thể xuất hiện ở nhiều hàng.

Các hàm tổng hợp thường dùng:

| Hàm | Ý nghĩa |
| --- | --- |
| `count(x)` | Đếm số giá trị khác `null`; `count(*)` đếm số hàng |
| `collect(x)` | Gom các giá trị thành một list; giá trị `null` bị bỏ qua |
| `sum(x)` | Tính tổng |
| `avg(x)` | Tính trung bình |
| `min(x)`, `max(x)` | Lấy giá trị nhỏ nhất hoặc lớn nhất |

Ví dụ, muốn có danh sách phim của từng người:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, collect(DISTINCT m.title) AS movieTitles
RETURN p.name AS actor, movieTitles
```

Nếu thứ tự phần tử trong list có ý nghĩa, hãy sắp xếp các hàng trước khi gom:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, m
ORDER BY m.released DESC, m.title
WITH p, collect(m.title) AS newestFirst
RETURN p.name AS actor, newestFirst
```

Đừng dựa vào thứ tự ngẫu nhiên của các hàng đầu vào để suy ra thứ tự trong list. Đặt `ORDER BY` ở giai đoạn ngay trước `collect()` để thể hiện rõ thứ tự mong muốn.

## 5. Xây dựng truy vấn nhiều giai đoạn

Một truy vấn nhiều giai đoạn thường có dạng:

```cypher
MATCH ...
WITH ...
WHERE ...
MATCH ...
WITH ...
RETURN ...
```

Mỗi `WITH` nên có một mục đích cụ thể: giảm số hàng, tính chỉ số, đổi tên biến, loại trùng lặp hoặc chuẩn bị dữ liệu cho bước tiếp theo. Ví dụ sau tìm những diễn viên đã tham gia ít nhất một số lượng phim nhất định, rồi trả về số phim và danh sách tiêu đề:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, count(DISTINCT m) AS movieCount
WHERE movieCount >= $minMovies
MATCH (p)-[:ACTED_IN]->(m:Movie)
WITH p, movieCount, collect(DISTINCT m.title) AS movieTitles
RETURN p.name AS actorName, movieCount, movieTitles
ORDER BY movieCount DESC, actorName
```

Truy vấn này có ba giai đoạn rõ ràng:

1. Tìm người và phim, sau đó gom nhóm theo người để tính `movieCount`.
2. Lọc theo `$minMovies`, rồi dùng node `p` đã chuyển tiếp để tìm các phim của người đó.
3. Gom tiêu đề phim và trả về một hàng cho mỗi người.

Lưu ý rằng `p` và `movieCount` phải được chuyển qua giai đoạn thứ hai. Ở `WITH` tiếp theo, cả hai tiếp tục được giữ lại vì kết quả cuối vẫn cần node người và số lượng phim. Nếu bỏ `p` khỏi danh sách `WITH`, `MATCH` sau đó sẽ không thể dùng nó.

## 6. Dùng truy vấn nhiều giai đoạn trong Spring Data Neo4j

Cypher nhiều giai đoạn có thể đặt trong `@Query` của repository khi truy vấn ổn định và gắn với một thao tác nghiệp vụ cụ thể. Nếu kết quả là thống kê hoặc DTO thay vì entity, `Neo4jClient` giúp ánh xạ các cột trả về một cách tường minh.

Ví dụ dùng `Neo4jClient` với DTO:

```java
public record ActorSummary(
    String actorName,
    long movieCount,
    List<String> movieTitles
) {}
```

```java
public Collection<ActorSummary> findActors(long minMovies) {
    return neo4jClient.query("""
            MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
            WITH p, count(DISTINCT m) AS movieCount
            WHERE movieCount >= $minMovies
            MATCH (p)-[:ACTED_IN]->(m:Movie)
            WITH p, movieCount, collect(DISTINCT m.title) AS movieTitles
            RETURN p.name AS actorName, movieCount, movieTitles
            ORDER BY movieCount DESC, actorName
            """)
        .bind(minMovies).to("minMovies")
        .fetchAs(ActorSummary.class)
        .mappedBy((typeSystem, record) -> new ActorSummary(
            record.get("actorName").asString(),
            record.get("movieCount").asLong(),
            record.get("movieTitles").asList(Value::asString)
        ))
        .all();
}
```

Các bí danh trong `RETURN` (`actorName`, `movieCount`, `movieTitles`) là tên cột mà mapper đọc. Tham số `$minMovies` được bind riêng, không ghép trực tiếp vào chuỗi Cypher. Ví dụ giả định đã inject `Neo4jClient` và dùng Neo4j Java Driver có kiểu `Value` tương ứng. Tùy phiên bản Spring Data Neo4j, hãy kiểm tra API mapping thực tế của dependency trong dự án.

Nếu truy vấn trả về node entity, có thể cân nhắc `@Query` trên repository để SDN ánh xạ kết quả theo metadata entity. Nếu trả về projection hoặc DTO, bảo đảm các alias và kiểu dữ liệu trả về khớp với cấu trúc projection hoặc mapper. Không nên trả về toàn bộ node và relationship khi API chỉ cần một vài trường tổng hợp.

`WITH` không chia một câu Cypher thành nhiều transaction. Toàn bộ truy vấn vẫn chạy trong transaction của câu lệnh. Khi gọi từ service có `@Transactional`, hãy cấu hình và sử dụng transaction manager của Spring Data Neo4j nhất quán với repository, template và client.

## 7. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Variable ... not defined` sau `WITH` | Biến cần dùng đã không được chuyển tiếp | Thêm biến vào danh sách `WITH`, hoặc dùng đúng bí danh mới |
| Kết quả có ít hàng hơn dự kiến | `WHERE`, `DISTINCT` hoặc `LIMIT` đặt ở giai đoạn trước khi mở rộng dữ liệu | Kiểm tra số hàng sau từng giai đoạn và xác định đúng thứ tự xử lý |
| Số lượng bị nhân đôi | Một node xuất hiện qua nhiều đường đi hoặc nhiều relationship | Dùng `count(DISTINCT node)` khi ý nghĩa nghiệp vụ là đếm node duy nhất |
| List chứa phần tử trùng | Nhiều hàng mang cùng giá trị được đưa vào `collect()` | Dùng `collect(DISTINCT expression)` nếu cần loại trùng |
| Trang kết quả thiếu hoặc lặp dữ liệu | Phân trang không có thứ tự ổn định | Thêm `ORDER BY` với tiêu chí xác định trước `SKIP` và `LIMIT` |
| Truy vấn giữ quá nhiều dữ liệu trung gian | Dùng `WITH *` hoặc mang theo biến không cần thiết | Chỉ chuyển tiếp các biến và giá trị cần cho giai đoạn tiếp theo |

Khi truy vấn phức tạp, hãy tạm kết thúc từng giai đoạn bằng một `RETURN` để quan sát kết quả trung gian trong Neo4j Browser hoặc công cụ truy vấn. Sau khi xác nhận logic, chuyển lại thành `WITH` để tiếp tục pipeline. Có thể dùng `EXPLAIN` để xem kế hoạch thực thi hoặc `PROFILE` để đo số hàng và lượng công việc thực tế của từng operator. `WITH` giúp biểu đạt luồng xử lý; bản thân nó không đảm bảo truy vấn nhanh hơn.

## 8. Nguyên tắc viết `WITH` dễ bảo trì

- Chuyển tiếp đúng những biến cần dùng ở bước tiếp theo; tránh giữ toàn bộ phạm vi bằng `WITH *` trong truy vấn dài.
- Đặt bí danh dễ hiểu cho biểu thức tính toán, ví dụ `movieCount`, `totalRevenue` hoặc `averageScore`.
- Dùng `WHERE` ngay sau giai đoạn tạo ra giá trị cần lọc để thể hiện rõ điều kiện áp dụng.
- Đặt `ORDER BY` trước `SKIP` và `LIMIT` khi cần phân trang hoặc chọn top-N.
- Dùng `DISTINCT` theo đúng ý nghĩa dữ liệu; phân biệt số hàng với số node duy nhất.
- Giảm số hàng sớm khi có thể, nhưng không đẩy điều kiện qua một giai đoạn nếu việc đó làm thay đổi ý nghĩa gom nhóm hoặc kết quả.
- Dùng tham số Cypher cho dữ liệu đầu vào và giữ alias kết quả nhất quán với mapping ở tầng Spring Data Neo4j.

Khi biết cách điều khiển phạm vi biến và luồng hàng qua `WITH`, ta có thể ghép nhiều thao tác `MATCH`, lọc và tổng hợp thành một truy vấn Cypher rõ ràng. Điều đó đặc biệt hữu ích trong Spring Data Neo4j khi cần trả về entity, projection hoặc DTO từ một đồ thị có nhiều node và relationship.
