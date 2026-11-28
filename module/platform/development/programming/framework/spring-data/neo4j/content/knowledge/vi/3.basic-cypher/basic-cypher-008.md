# COUNT, COLLECT, DISTINCT và tổng hợp kết quả

Khi truy vấn đồ thị Neo4j, kết quả ban đầu thường có nhiều dòng: mỗi dòng tương ứng với một node, relationship hoặc một đường đi khớp với mẫu `MATCH`. Trong nhiều nghiệp vụ, ứng dụng không cần toàn bộ các dòng đó mà cần một con số, một danh sách hoặc một nhóm kết quả đã được tóm tắt. Cypher cung cấp các phép tổng hợp như `count()`, `collect()`, `sum()`, `avg()`, `min()` và `max()` để thực hiện việc này.

Bài học thuộc module **SPRING_DATA_NEO4J**, tập trung vào cách tổng hợp dữ liệu đồ thị trước khi đưa kết quả về ứng dụng Java. Các ví dụ dùng mô hình phim–diễn viên: node `Person`, node `Movie` và relationship có hướng `(:Person)-[:ACTED_IN]->(:Movie)`. Relationship `ACTED_IN` có thể chứa thuộc tính `roles` mô tả vai diễn. Đây là nền tảng để hiểu cách đếm diễn viên, lập danh sách phim và tạo thống kê theo từng nhóm.

## 1. Từ các dòng MATCH đến kết quả tổng hợp

Xét truy vấn tìm người tham gia diễn xuất trong phim:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actor, m.title AS movie;
```

Mỗi cặp người–phim khớp với `MATCH` tạo ra một dòng kết quả. Nếu một diễn viên tham gia ba phim, tên người đó xuất hiện trên ba dòng. Tổng hợp cho phép thu gọn các dòng này thành số lượng hoặc danh sách.

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actor,
       count(m) AS movieCount,
       collect(m.title) AS movies
ORDER BY actor;
```

Kết quả có một dòng cho mỗi giá trị `actor`, kèm số phim và danh sách tiêu đề. Điểm quan trọng là Cypher nhóm dữ liệu dựa trên các biểu thức không nằm trong hàm tổng hợp. Trong ví dụ này, `p.name` là biểu thức nhóm; `count(m)` và `collect(m.title)` được tính riêng cho từng nhóm.

## 2. COUNT: đếm dòng và đếm giá trị

`count()` trả về số lượng. Cần phân biệt hai cách dùng phổ biến:

- `count(*)` đếm số dòng đầu vào, kể cả khi một biểu thức trong dòng có giá trị `null`.
- `count(expression)` đếm số dòng mà biểu thức có giá trị khác `null`.

Ví dụ, đếm số relationship diễn xuất trong đồ thị:

```cypher
MATCH (p:Person)-[credit:ACTED_IN]->(m:Movie)
RETURN count(*) AS actingCredits,
       count(credit) AS relationshipCount,
       count(p) AS matchedPeople;
```

Với mẫu `MATCH` này, `p`, `credit` và `m` đều phải tồn tại nên ba giá trị thường bằng nhau. Dù vậy, `count(*)` và `count(expression)` vẫn có ý nghĩa khác nhau khi truy vấn có `OPTIONAL MATCH` hoặc biểu thức có thể là `null`.

### 2.1. Đếm node duy nhất

Một node có thể xuất hiện trên nhiều dòng nếu nó tham gia nhiều relationship hoặc nhiều đường đi. Nếu mục tiêu là đếm số người khác nhau, hãy dùng `DISTINCT` bên trong `count()`:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(:Movie)
RETURN count(p) AS actingRows,
       count(DISTINCT p) AS uniqueActors;
```

`actingRows` đếm số dòng khớp, còn `uniqueActors` đếm số node `Person` khác nhau. Nên đếm node khi câu hỏi nghiệp vụ nói về số thực thể. `count(DISTINCT p.name)` đếm các giá trị tên khác nhau; cách đó có thể khác với số node nếu dữ liệu cho phép hai người có cùng tên.

### 2.2. Đếm theo từng nhóm

Để biết mỗi phim có bao nhiêu diễn viên, đặt thuộc tính phim ở ngoài hàm tổng hợp và đặt phép đếm bên trong:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN m.title AS movie,
       count(DISTINCT p) AS actorCount
ORDER BY actorCount DESC, movie;
```

Mỗi giá trị `m.title` tạo thành một nhóm. `count(DISTINCT p)` đếm số node diễn viên duy nhất trong nhóm đó. `ORDER BY` sắp xếp phim theo số diễn viên giảm dần; `movie` là tiêu chí phụ để kết quả có thứ tự ổn định khi số diễn viên bằng nhau.

Có thể nhóm theo nhiều biểu thức. Ví dụ, nếu cần thống kê theo năm phát hành và tiêu đề:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN m.released AS released,
       m.title AS movie,
       count(DISTINCT p) AS actorCount
ORDER BY released, movie;
```

Mỗi tổ hợp `released` và `movie` là một nhóm. Bất kỳ biểu thức nào xuất hiện trong `RETURN` mà không được đặt trong hàm tổng hợp đều tham gia xác định nhóm. Vì vậy, thêm `p.name` vào `RETURN` sẽ làm nhóm nhỏ hơn, thường thành một nhóm cho từng người trong từng phim.

### 2.3. COUNT kết hợp OPTIONAL MATCH

`OPTIONAL MATCH` giữ lại node đã tìm được ngay cả khi không có relationship phù hợp; các biến không khớp được gán `null`. Điều này ảnh hưởng trực tiếp đến cách đếm.

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS person,
       count(*) AS rowsAfterOptionalMatch,
       count(m) AS movieCount
ORDER BY person;
```

Với một người không có phim, `OPTIONAL MATCH` vẫn tạo một dòng cho người đó, trong đó `m` là `null`. Vì thế `count(*)` là `1`, còn `count(m)` là `0`. Khi muốn đếm số phim liên quan, `count(m)` thường phản ánh đúng ý nghĩa nghiệp vụ hơn.

## 3. COLLECT: gom giá trị thành danh sách

`collect(expression)` gom các giá trị khác `null` trong một nhóm thành một danh sách. Ví dụ, lập danh sách phim của mỗi diễn viên:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actor,
       collect(m.title) AS movies
ORDER BY actor;
```

Nếu cùng một tiêu đề xuất hiện nhiều lần trong nhóm, danh sách có thể chứa giá trị lặp. Dùng `collect(DISTINCT expression)` khi cần danh sách giá trị duy nhất:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actor,
       collect(DISTINCT m.title) AS movies
ORDER BY actor;
```

`collect()` cũng có thể gom node, thuộc tính hoặc map. Gom map hữu ích khi ứng dụng cần trả về một danh sách các cấu trúc dữ liệu gọn:

```cypher
MATCH (p:Person)-[credit:ACTED_IN]->(m:Movie)
RETURN p.name AS actor,
       collect({
           title: m.title,
           released: m.released,
           roles: credit.roles
       }) AS filmography
ORDER BY actor;
```

Mỗi phần tử trong `filmography` là một map có các khóa `title`, `released` và `roles`. Cách này giữ thông tin vai diễn gắn với đúng phim. Nếu chỉ gom `m.title` thì dữ liệu về relationship `ACTED_IN` sẽ không có trong danh sách trả về.

### 3.1. COLLECT và giá trị null

`collect()` bỏ qua các giá trị `null`. Kết hợp với `OPTIONAL MATCH`, điều này cho phép trả về danh sách rỗng cho người chưa tham gia phim nào:

```cypher
MATCH (p:Person)
OPTIONAL MATCH (p)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS person,
       count(m) AS movieCount,
       collect(m.title) AS movies
ORDER BY person;
```

Khi không có phim phù hợp, `count(m)` trả về `0` và `collect(m.title)` trả về danh sách rỗng `[]`, vì biểu thức `m.title` là `null` và bị bỏ qua. Đây thường là dạng kết quả thuận tiện cho tầng dịch vụ hoặc API vì mỗi người vẫn xuất hiện trong kết quả.

### 3.2. Kiểm soát thứ tự trong danh sách

Không nên mặc định thứ tự phần tử do `collect()` tạo ra là thứ tự nghiệp vụ mong muốn. Nếu danh sách cần có thứ tự, hãy sắp xếp các dòng đầu vào ngay trước bước tổng hợp:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, m
ORDER BY m.released, m.title
RETURN p.name AS actor,
       collect(m.title) AS moviesByRelease;
```

`WITH` chuyển các dòng khớp sang bước tiếp theo; `ORDER BY` sắp xếp các dòng đó trước khi `collect()` gom chúng thành danh sách. Nếu thứ tự không mang ý nghĩa trong nghiệp vụ, không cần thêm bước sắp xếp vì nó có thể làm tăng chi phí truy vấn.

## 4. DISTINCT: loại bỏ kết quả trùng lặp

`DISTINCT` không phải là một hàm tổng hợp độc lập. Đây là từ khóa yêu cầu Cypher chỉ giữ lại các giá trị hoặc tổ hợp giá trị duy nhất tại vị trí sử dụng. Có ba cách dùng thường gặp.

### 4.1. DISTINCT trong RETURN

```cypher
MATCH (p:Person)-[:ACTED_IN]->(:Movie)
RETURN DISTINCT p.name AS actor
ORDER BY actor;
```

Truy vấn trả về các tên diễn viên duy nhất, dù một người có thể tham gia nhiều phim. Nếu cần danh sách node duy nhất thay vì danh sách tên, hãy trả về `p`:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(:Movie)
RETURN DISTINCT p AS actor;
```

Hai truy vấn này không hoàn toàn tương đương về ý nghĩa. `DISTINCT p.name` gộp các node có cùng tên thành một giá trị; `DISTINCT p` phân biệt các node theo danh tính node.

### 4.2. DISTINCT bên trong COUNT và COLLECT

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN count(DISTINCT p) AS actorCount,
       collect(DISTINCT m.title) AS movieTitles;
```

Ở đây `count(DISTINCT p)` đếm node người duy nhất và `collect(DISTINCT m.title)` tạo danh sách tiêu đề duy nhất. Mỗi biểu thức áp dụng tính duy nhất cho đầu vào của chính phép tổng hợp đó.

### 4.3. DISTINCT trong WITH

`WITH DISTINCT` loại bỏ dòng trùng trước khi chuyển dữ liệu sang bước tiếp theo:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(:Movie)
WITH DISTINCT p
RETURN count(p) AS actorCount;
```

Kết quả tương đương về mục tiêu đếm người với `count(DISTINCT p)` trong ví dụ đơn giản. Dùng `WITH DISTINCT` khi cần tiếp tục xử lý tập node đã khử trùng lặp ở các bước sau, chẳng hạn nối thêm một mẫu quan hệ hoặc tính toán nhiều thống kê trên cùng tập dữ liệu.

## 5. Các hàm tổng hợp thường dùng

Ngoài `count()` và `collect()`, Cypher còn có các hàm tổng hợp số học và so sánh. Các hàm này thường bỏ qua giá trị `null` khi tính trên biểu thức.

| Hàm | Công dụng | Ví dụ |
|---|---|---|
| `count(expr)` | Đếm số giá trị khác `null` | `count(m)` |
| `collect(expr)` | Gom giá trị thành danh sách | `collect(m.title)` |
| `sum(expr)` | Tính tổng giá trị số | `sum(m.released)` |
| `avg(expr)` | Tính trung bình giá trị số | `avg(m.released)` |
| `min(expr)` | Lấy giá trị nhỏ nhất | `min(m.released)` |
| `max(expr)` | Lấy giá trị lớn nhất | `max(m.released)` |

Ví dụ thống kê khoảng năm phát hành và năm trung bình của các phim có diễn viên:

```cypher
MATCH (:Person)-[:ACTED_IN]->(m:Movie)
RETURN count(DISTINCT m) AS movieCount,
       min(m.released) AS firstRelease,
       max(m.released) AS latestRelease,
       avg(m.released) AS averageReleaseYear;
```

Các hàm tổng hợp này tính trên những dòng được tạo ra bởi `MATCH`. Vì một phim có thể xuất hiện trên nhiều dòng nếu có nhiều diễn viên, ví dụ dùng `count(DISTINCT m)` để đếm node phim duy nhất. `min`, `max` và `avg` trên `m.released` không bị thay đổi bởi việc một năm xuất hiện nhiều lần đối với min/max, nhưng trung bình có thể bị ảnh hưởng nếu một phim xuất hiện lặp. Nếu muốn trung bình theo từng phim, cần khử trùng lặp phim trước khi tính:

```cypher
MATCH (:Person)-[:ACTED_IN]->(m:Movie)
WITH DISTINCT m
RETURN count(m) AS movieCount,
       avg(m.released) AS averageReleaseYear;
```

## 6. Dùng WITH để chia các bước tổng hợp

`WITH` chuyển các biến và biểu thức được chọn sang phần tiếp theo của truy vấn. Nó đặc biệt hữu ích khi cần lọc theo kết quả tổng hợp, đổi mức nhóm hoặc tính nhiều bước liên tiếp.

Ví dụ, tìm các phim có ít nhất hai diễn viên:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH m, count(DISTINCT p) AS actorCount
WHERE actorCount >= 2
RETURN m.title AS movie, actorCount
ORDER BY actorCount DESC, movie;
```

Trình tự xử lý là:

1. `MATCH` tạo các dòng người–phim.
2. `WITH` nhóm theo `m` và tính số diễn viên duy nhất cho từng phim.
3. `WHERE` sau `WITH` lọc các nhóm dựa trên `actorCount`.
4. `RETURN` định dạng kết quả cuối cùng.

Điều kiện `WHERE` sau `MATCH` lọc các dòng đầu vào trước khi tổng hợp; điều kiện `WHERE` sau `WITH` có thể lọc các nhóm dựa trên giá trị tổng hợp đã tính. Đây là điểm cần nhớ khi viết truy vấn thống kê.

Có thể đổi mức nhóm qua nhiều bước. Ví dụ, trước tiên gom phim theo từng diễn viên, sau đó trả về số phim trong danh sách:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WITH p, collect(DISTINCT m.title) AS movies
RETURN p.name AS actor,
       movies,
       size(movies) AS movieCount
ORDER BY movieCount DESC, actor;
```

Ở bước `WITH`, mỗi người có một danh sách tiêu đề phim. `size(movies)` tính số phần tử trong danh sách đã gom. Trong ví dụ này, `movieCount` tương ứng với số tiêu đề phim duy nhất vì `collect(DISTINCT m.title)` đã loại bỏ tiêu đề trùng.

## 7. Những lỗi thường gặp khi tổng hợp

**Đếm dòng thay vì đếm thực thể.** Một người xuất hiện trên nhiều dòng khi tham gia nhiều phim. Nếu yêu cầu là số người, dùng `count(DISTINCT p)` thay vì `count(*)`.

**Nhầm tên duy nhất với node duy nhất.** `count(DISTINCT p.name)` đếm giá trị tên; `count(DISTINCT p)` đếm node. Chọn biểu thức theo định nghĩa thực thể trong miền nghiệp vụ.

**Quên ảnh hưởng của OPTIONAL MATCH.** Một node không có relationship vẫn tạo một dòng với biến relationship hoặc node đích là `null`. `count(*)` có thể đếm dòng này, trong khi `count(m)` bỏ qua `null`.

**Để danh sách có phần tử trùng.** `collect(m.title)` gom mọi giá trị khác `null`; thêm `DISTINCT` nếu danh sách cần các giá trị duy nhất. Cũng cần xác định nên loại trùng theo node hay theo thuộc tính.

**Đưa quá nhiều biểu thức vào RETURN.** Mỗi biểu thức không tổng hợp đều tham gia nhóm. Thêm một thuộc tính có thể làm một nhóm bị chia thành nhiều nhóm nhỏ, khiến số đếm thay đổi.

**Giả định danh sách luôn có thứ tự.** Hãy sắp xếp đầu vào trước `collect()` nếu thứ tự là yêu cầu của nghiệp vụ.

**Làm phình số dòng khi MATCH nhiều nhánh quan hệ.** Nếu cùng lúc khớp nhiều quan hệ độc lập từ một node, các dòng kết hợp có thể nhân lên. Khi đó số đếm và danh sách có thể bị lặp. Xem lại mẫu truy vấn, dùng `DISTINCT` đúng chỗ hoặc tách các bước bằng `WITH` để mỗi phép tổng hợp nhận đúng tập dòng cần xử lý.

## 8. Bài tập thực hành

Sử dụng đồ thị `Person`, `Movie` và `ACTED_IN` để thực hiện các yêu cầu sau:

1. Đếm tổng số relationship `ACTED_IN` trong đồ thị.
2. Đếm số diễn viên duy nhất và so sánh với số dòng khớp của mẫu `MATCH`.
3. Với mỗi phim, trả về tiêu đề và số diễn viên duy nhất; sắp xếp theo số diễn viên giảm dần.
4. Với mỗi diễn viên, tạo danh sách tiêu đề phim không trùng bằng `collect(DISTINCT ...)`.
5. Dùng `OPTIONAL MATCH` để hiển thị cả người chưa tham gia phim nào; kiểm tra khác biệt giữa `count(*)` và `count(m)`.
6. Tạo danh sách map gồm tiêu đề phim, năm phát hành và `roles` của mỗi diễn viên.
7. Dùng `WITH` để tìm những diễn viên tham gia từ hai phim trở lên.
8. Tính năm phát hành trung bình của các phim duy nhất và giải thích vì sao cần loại trùng node phim trước khi tính.

Khi hoàn thành, bạn cần giải thích được một truy vấn đang tổng hợp theo nhóm nào, biểu thức nào quyết định tính duy nhất, và `null` ảnh hưởng ra sao đến kết quả. Đây là kỹ năng quan trọng khi xây dựng repository hoặc truy vấn `@Query` trong Spring Data Neo4j: kết quả trả về phải phản ánh đúng số thực thể và cấu trúc dữ liệu mà nghiệp vụ cần.
