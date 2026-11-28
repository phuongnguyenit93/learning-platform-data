# MATCH, WHERE, RETURN và tham số có tên

Cypher là ngôn ngữ truy vấn đồ thị của Neo4j. Trong một truy vấn đọc dữ liệu cơ bản, `MATCH` mô tả mẫu node và relationship cần tìm, `WHERE` lọc các kết quả theo điều kiện, còn `RETURN` xác định dữ liệu được trả về. Khi ứng dụng truyền giá trị động, **tham số có tên** như `$personName` giúp tách dữ liệu đầu vào khỏi câu lệnh Cypher.

Đây là nhóm thành phần được dùng thường xuyên khi viết truy vấn cho Neo4j, bao gồm cả truy vấn trong `@Query` của Spring Data Neo4j. Bài học sử dụng ví dụ người và phim để giải thích cách ghép các clause, đọc kết quả và truyền tham số an toàn.

## 1. Mô hình đồ thị dùng trong ví dụ

Giả sử cơ sở dữ liệu có hai loại node `Person` và `Movie`. Một người có thể tham gia diễn xuất trong nhiều phim, được biểu diễn bằng relationship có hướng `ACTED_IN`:

```text
(Person)-[:ACTED_IN]->(Movie)
```

Có thể tạo một cặp dữ liệu mẫu bằng Cypher:

```cypher
CREATE (:Person {name: 'An', age: 28})
       -[:ACTED_IN]->
       (:Movie {title: 'Mùa hè', released: 2024})
```

Trong biểu thức trên:

- `Person` và `Movie` là label của node.
- `name`, `age`, `title` và `released` là property.
- `ACTED_IN` là relationship type; mũi tên biểu thị hướng từ người đến phim.

Các truy vấn tiếp theo giả định đồ thị có những node và relationship theo mô hình này. Nếu chạy lệnh `CREATE` nhiều lần, Neo4j sẽ tạo thêm dữ liệu mới; trong môi trường thực tế nên dùng dữ liệu thử nghiệm có kiểm soát.

## 2. MATCH: tìm mẫu trong đồ thị

`MATCH` mô tả một pattern mà Neo4j cần tìm trong đồ thị. Pattern có thể chỉ gồm một node, một relationship hoặc một đường đi qua nhiều node.

### Tìm một loại node

```cypher
MATCH (p:Person)
RETURN p
```

`(p:Person)` yêu cầu tìm các node mang label `Person`. `p` là biến gắn với node được tìm thấy. Mỗi node phù hợp tạo ra một dòng kết quả cho phần tiếp theo của truy vấn.

Có thể bỏ label nếu muốn tìm node bất kỳ:

```cypher
MATCH (n)
RETURN n
```

Trong ứng dụng, nên chỉ rõ label khi có thể để pattern dễ đọc và giúp cơ sở dữ liệu thu hẹp phạm vi tìm kiếm.

### Tìm node theo relationship

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m
```

Pattern trên tìm đường đi gồm node `Person`, relationship `ACTED_IN` và node `Movie`. Ba biến `p`, `r`, `m` lần lượt đại diện cho người, quan hệ và phim.

Một số cách viết hướng relationship thường gặp:

```cypher
// Relationship đi từ Person đến Movie
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m

// Relationship đi từ Movie đến Person
MATCH (m:Movie)<-[r:ACTED_IN]-(p:Person)
RETURN p, r, m

// Không chỉ định hướng
MATCH (a)-[r:ACTED_IN]-(b)
RETURN a, r, b
```

Khi relationship có tên kiểu và hướng rõ ràng, pattern thể hiện chính xác cấu trúc cần tìm. Biến relationship có thể được bỏ nếu không cần đọc relationship hoặc property của nó, ví dụ `MATCH (p:Person)-[:ACTED_IN]->(m:Movie)`.

### Dùng property trong pattern

Có thể đưa điều kiện property đơn giản trực tiếp vào pattern:

```cypher
MATCH (p:Person {name: 'An'})
RETURN p
```

Biểu thức `{name: 'An'}` yêu cầu node có property `name` bằng chuỗi `An`. Khi giá trị đến từ ứng dụng, nên dùng tham số thay cho literal:

```cypher
MATCH (p:Person {name: $personName})
RETURN p
```

`$personName` là tham số có tên. Phần sau giải thích cách truyền giá trị này từ Java.

## 3. WHERE: lọc các kết quả phù hợp

`WHERE` đặt điều kiện logic cho pattern đã tìm bởi `MATCH`. Nó thường được đặt ngay sau `MATCH` và trước `RETURN`:

```cypher
MATCH (p:Person)
WHERE p.age >= 18
RETURN p
```

Truy vấn trả về những người có `age` lớn hơn hoặc bằng 18. `p.age` là property `age` của node được gắn với biến `p`.

### Toán tử so sánh và logic

Các toán tử cơ bản có thể dùng trong điều kiện:

| Nhóm | Toán tử | Ý nghĩa |
|---|---|---|
| So sánh | `=`, `<>` | Bằng, khác |
| So sánh | `<`, `<=`, `>`, `>=` | Nhỏ hơn, nhỏ hơn hoặc bằng, lớn hơn, lớn hơn hoặc bằng |
| Logic | `AND` | Tất cả điều kiện đều đúng |
| Logic | `OR` | Có ít nhất một điều kiện đúng |
| Logic | `NOT` | Phủ định điều kiện |
| Tập hợp | `IN` | Giá trị thuộc một danh sách |

Ví dụ kết hợp nhiều điều kiện:

```cypher
MATCH (p:Person)
WHERE p.age >= 18 AND p.age < 30
RETURN p.name AS name, p.age AS age
```

Ví dụ dùng `OR` và `IN`:

```cypher
MATCH (m:Movie)
WHERE m.released = 2023 OR m.released = 2024
RETURN m.title AS title, m.released AS year

MATCH (m:Movie)
WHERE m.released IN [2022, 2023, 2024]
RETURN m.title AS title
```

Khi kết hợp `AND` và `OR`, hãy dùng dấu ngoặc để thể hiện rõ thứ tự mong muốn và giúp người đọc tránh hiểu nhầm.

### Kiểm tra property rỗng

Cypher dùng `IS NULL` và `IS NOT NULL` để kiểm tra một property không có giá trị hoặc có giá trị:

```cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
RETURN p.name AS name, p.email AS email
```

Nếu property không tồn tại trên node, biểu thức đọc property đó có giá trị `null`. Vì vậy, so sánh trực tiếp với `null` bằng `= null` không phải cách kiểm tra phù hợp; hãy dùng `IS NULL` hoặc `IS NOT NULL`.

### Điều kiện trên node và relationship

`WHERE` có thể lọc property của cả node lẫn relationship:

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
WHERE p.age >= 18 AND r.role = 'Mai'
RETURN p.name AS actor, m.title AS movie
```

Trong pattern này, `r` là biến relationship nên có thể đọc property `r.role`. Điều kiện `WHERE` được áp dụng cho từng kết quả pattern trước khi tạo phần dữ liệu trả về.

## 4. RETURN: chọn dữ liệu đầu ra

`RETURN` xác định biểu thức nào sẽ được gửi về cho ứng dụng. Ta có thể trả về node, relationship, property riêng lẻ hoặc biểu thức được đặt bí danh.

### Trả về node hoặc nhiều thành phần

```cypher
MATCH (p:Person)
RETURN p
```

Truy vấn trả về node `Person` cùng các property của node đó. Nếu chỉ cần một vài trường, có thể chọn property cụ thể:

```cypher
MATCH (p:Person)
RETURN p.name, p.age
```

Để trả về cả người, relationship và phim:

```cypher
MATCH (p:Person)-[r:ACTED_IN]->(m:Movie)
RETURN p, r, m
```

### Đặt bí danh bằng AS

`AS` đặt tên dễ hiểu cho một cột kết quả:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN p.name AS actorName, m.title AS movieTitle
```

Kết quả gồm hai cột `actorName` và `movieTitle`. Bí danh hữu ích khi trả dữ liệu dạng projection, map hoặc DTO cho tầng service.

### Loại bỏ dòng trùng với DISTINCT

Một node có thể xuất hiện trong nhiều pattern phù hợp. Nếu chỉ muốn mỗi giá trị xuất hiện một lần, dùng `DISTINCT`:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
RETURN DISTINCT p.name AS actorName
```

`DISTINCT` áp dụng lên tổ hợp biểu thức được trả về. Nếu trả về nhiều cột, hai dòng chỉ được xem là trùng khi tất cả giá trị trong dòng tương ứng bằng nhau.

### Sắp xếp và giới hạn kết quả

Trong truy vấn đọc, `ORDER BY` và `LIMIT` thường được dùng sau `RETURN` để sắp xếp và giới hạn số dòng:

```cypher
MATCH (m:Movie)
RETURN m.title AS title, m.released AS year
ORDER BY year DESC
LIMIT 10
```

Truy vấn trả về tối đa 10 phim có năm phát hành mới nhất. Có thể dùng `ASC` cho thứ tự tăng dần hoặc `DESC` cho thứ tự giảm dần. Nếu không chỉ định `ORDER BY`, không nên giả định thứ tự các dòng kết quả.

## 5. Tham số có tên trong Cypher

Tham số có tên là placeholder được viết với dấu `$` ở phía trước tên, ví dụ `$personName`, `$minAge` hoặc `$fromYear`. Khi thực thi, ứng dụng truyền giá trị riêng cho từng tham số.

```cypher
MATCH (p:Person)
WHERE p.name = $personName AND p.age >= $minAge
RETURN p.name AS name, p.age AS age
```

Truy vấn không chứa sẵn giá trị cụ thể của tên hoặc tuổi. Ứng dụng có thể chạy lại cùng câu truy vấn với những bộ tham số khác nhau.

### Truyền tham số từ Neo4j Java Driver

Khi dùng Neo4j Java Driver trực tiếp, truyền tham số dưới dạng map cùng câu Cypher:

```java
try (Session session = driver.session()) {
    var result = session.run(
        "MATCH (p:Person) " +
        "WHERE p.name = $personName AND p.age >= $minAge " +
        "RETURN p.name AS name, p.age AS age",
        Map.of("personName", personName, "minAge", minAge)
    );

    var people = result.list(record -> Map.of(
        "name", record.get("name").asString(),
        "age", record.get("age").asInt()
    ));
}
```

`driver` là đối tượng `org.neo4j.driver.Driver` đã được cấu hình. Các khóa trong map phải khớp với tên tham số trong Cypher, không có dấu `$`. Driver dùng giá trị trong map để gắn vào các placeholder tương ứng. `try-with-resources` bảo đảm session được đóng sau khi đọc kết quả.

### Truyền tham số từ Spring Data Neo4j

Với Spring Data Neo4j, tham số của phương thức repository có thể được tham chiếu trong `@Query` bằng tên có tiền tố `$`. Dùng `@Param` để khai báo rõ mối liên hệ giữa tham số Java và tên trong Cypher:

```java
public interface PersonRepository extends Neo4jRepository<Person, Long> {

    @Query("MATCH (p:Person) " +
           "WHERE p.name = $personName AND p.age >= $minAge " +
           "RETURN p")
    List<Person> findAdultsByName(
        @Param("personName") String personName,
        @Param("minAge") int minAge
    );
}
```

Khi gọi `findAdultsByName("An", 18)`, Spring Data Neo4j liên kết `personName` với `$personName` và `minAge` với `$minAge`, sau đó thực thi truy vấn và ánh xạ các node được trả về thành `Person`.

Nếu truy vấn chỉ trả về một số property thay vì node đầy đủ, kiểu trả về cũng cần phản ánh cấu trúc dữ liệu đó, chẳng hạn projection hoặc DTO phù hợp. Không nên khai báo kiểu entity đầy đủ khi câu lệnh chỉ trả về các cột không đủ để ánh xạ entity.

### Vì sao nên dùng tham số?

- **An toàn:** dữ liệu đầu vào được truyền riêng, không cần nối trực tiếp vào chuỗi truy vấn. Cách này giúp tránh lỗi cú pháp và nguy cơ Cypher injection do dữ liệu người dùng.
- **Tái sử dụng:** cùng một câu truy vấn có thể chạy với nhiều bộ giá trị khác nhau.
- **Dễ bảo trì:** cấu trúc truy vấn và dữ liệu đầu vào tách biệt, giúp đọc, kiểm thử và thay đổi câu lệnh thuận tiện hơn.

Viết đúng:

```cypher
MATCH (p:Person)
WHERE p.name = $personName
RETURN p
```

Không đặt placeholder trong dấu nháy như một chuỗi literal:

```cypher
// Sai mục đích: đây là chuỗi ký tự "$personName"
MATCH (p:Person)
WHERE p.name = '$personName'
RETURN p
```

Trong trường hợp sai, Neo4j so sánh property với chính chuỗi `$personName`, chứ không thay thế bằng giá trị ứng dụng truyền vào.

Tham số thông thường đại diện cho **giá trị** trong biểu thức. Không thể dùng `$label` như cách thay thế tùy ý cho tên label, `$type` cho relationship type hoặc `$property` cho tên property trong mọi vị trí cú pháp. Nếu cần thay đổi cấu trúc pattern, hãy thiết kế truy vấn rõ ràng và kiểm soát chặt phần cấu trúc được tạo ra.

## 6. Ghép MATCH, WHERE, RETURN và tham số thành truy vấn hoàn chỉnh

Giả sử cần tìm các phim có người tên `An` tham gia diễn xuất, phát hành từ một năm cho trước và trả về tên phim cùng năm phát hành. Truy vấn Cypher có thể viết như sau:

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE p.name = $personName
  AND m.released >= $fromYear
RETURN DISTINCT m.title AS title, m.released AS releasedYear
ORDER BY releasedYear DESC
LIMIT $maxResults
```

Đọc truy vấn theo thứ tự:

1. `MATCH` tìm các pattern nối `Person` với `Movie` qua relationship `ACTED_IN`.
2. `WHERE` chỉ giữ các pattern có người mang tên được truyền vào và phim có năm phát hành từ `fromYear` trở đi.
3. `RETURN DISTINCT` chỉ lấy tên và năm phát hành, đồng thời loại các dòng trùng nhau.
4. `ORDER BY` sắp xếp phim theo năm giảm dần.
5. `LIMIT` giới hạn số dòng tối đa theo tham số `maxResults`.

Trong Spring Data Neo4j, truy vấn có thể đặt trong repository:

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {

    @Query("MATCH (p:Person)-[:ACTED_IN]->(m:Movie) " +
           "WHERE p.name = $personName AND m.released >= $fromYear " +
           "RETURN DISTINCT m")
    List<Movie> findMovies(
        @Param("personName") String personName,
        @Param("fromYear") int fromYear
    );
}
```

Ví dụ repository này trả về entity `Movie`. Nếu cần sắp xếp, giới hạn hoặc projection, bổ sung các clause và kiểu trả về tương ứng với nhu cầu của service. Khi dùng tham số trong `LIMIT`, cần bảo đảm giá trị truyền vào là số nguyên không âm hợp lệ theo quy tắc nghiệp vụ.

## 7. Cách đọc kết quả và xử lý trường hợp không có dữ liệu

Một truy vấn `MATCH` không tìm thấy pattern nào sẽ tạo ra không có dòng kết quả. Vì vậy, ứng dụng thường nhận danh sách rỗng khi truy vấn được ánh xạ thành collection. Điều này khác với việc tìm thấy một node có property bằng `null`: trong trường hợp đó vẫn có thể có dòng kết quả, nhưng giá trị property là `null`.

Một số điểm cần nhớ:

- Mỗi tổ hợp pattern phù hợp có thể tạo một dòng kết quả. Một người tham gia nhiều phim có thể xuất hiện ở nhiều dòng.
- `RETURN p` trả về node; `RETURN p.name` trả về property; `RETURN p.name AS name` trả về property với tên cột `name`.
- Nếu chỉ cần một số trường, trả về các property đó để giảm lượng dữ liệu phải truyền và ánh xạ.
- Dùng `DISTINCT` khi nghiệp vụ yêu cầu loại dòng trùng; không thêm một cách máy móc vì việc loại trùng cũng có chi phí.
- Nếu cần giữ lại node bên trái ngay cả khi không có relationship phù hợp, hãy tìm hiểu `OPTIONAL MATCH`. `MATCH` thông thường chỉ giữ các pattern thực sự tồn tại.

## 8. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Truy vấn không trả dòng nào | Label, relationship type, hướng quan hệ hoặc điều kiện không khớp dữ liệu | Chạy lần lượt pattern `MATCH` đơn giản, sau đó thêm từng điều kiện `WHERE`. |
| Tham số không được thay thế | Tên placeholder không khớp khóa map hoặc tên `@Param` | Đối chiếu chính xác `$personName`, khóa map và `@Param("personName")`. |
| Kết quả có nhiều dòng trùng | Một node xuất hiện trong nhiều đường đi phù hợp | Xác định ý nghĩa của từng dòng; dùng `DISTINCT` nếu cần kết quả duy nhất. |
| Kết quả thiếu property | Node không có property đó hoặc projection chỉ trả về một phần dữ liệu | Kiểm tra dữ liệu và biểu thức trong `RETURN`; xử lý `null` nếu property là tùy chọn. |
| Spring không ánh xạ được kết quả | Kiểu trả về không phù hợp với biểu thức trong `RETURN` | Trả node phù hợp với entity hoặc định nghĩa projection/DTO tương ứng. |
| Truy vấn chậm khi dữ liệu tăng | Pattern quá rộng, lọc chưa hiệu quả hoặc phải duyệt quá nhiều node | Giới hạn label và relationship, lọc theo property phù hợp, kiểm tra index và kế hoạch truy vấn. |

Khi truy vấn có kết quả bất ngờ, hãy kiểm tra từ pattern đơn giản nhất rồi thêm `WHERE`, `RETURN` và các clause khác từng bước. Cách này giúp xác định điều kiện hoặc đoạn pattern gây ra sai khác.

## 9. Thực hành tổng hợp

Cho đồ thị gồm các node `Person` có property `name`, `age` và các node `Movie` có property `title`, `released`. Relationship `ACTED_IN` đi từ `Person` đến `Movie`.

**Bài tập 1:** Tìm tất cả người từ 18 tuổi trở lên và chỉ trả về tên.

```cypher
MATCH (p:Person)
WHERE p.age >= 18
RETURN p.name AS name
```

**Bài tập 2:** Tìm các phim của người có tên được truyền qua tham số `$personName`.

```cypher
MATCH (p:Person)-[:ACTED_IN]->(m:Movie)
WHERE p.name = $personName
RETURN m.title AS title
```

**Bài tập 3:** Tìm phim phát hành từ `$fromYear`, trả về tên phim và năm, sắp xếp năm phát hành giảm dần.

```cypher
MATCH (m:Movie)
WHERE m.released >= $fromYear
RETURN m.title AS title, m.released AS year
ORDER BY year DESC
```

**Bài tập 4:** Viết một phương thức repository Spring Data Neo4j nhận `personName` và `fromYear`, trả về danh sách `Movie` phù hợp. Dùng `@Query` với `$personName`, `$fromYear` và khai báo `@Param` tương ứng.

```java
public interface MovieRepository extends Neo4jRepository<Movie, Long> {
    @Query("MATCH (p:Person)-[:ACTED_IN]->(m:Movie) " +
           "WHERE p.name = $personName AND m.released >= $fromYear " +
           "RETURN DISTINCT m")
    List<Movie> findByActorAndYear(
        @Param("personName") String personName,
        @Param("fromYear") int fromYear
    );
}
```

## 10. Ghi nhớ

`MATCH` mô tả cấu trúc đồ thị cần tìm và gắn các phần tử phù hợp vào biến. `WHERE` lọc các pattern theo điều kiện trên node, relationship hoặc property. `RETURN` quyết định dữ liệu nào được gửi về, có thể trả node, relationship, property hoặc biểu thức có bí danh. Tham số có tên như `$personName` cho phép ứng dụng truyền giá trị riêng khi chạy truy vấn.

Trong Spring Data Neo4j, những thành phần này kết hợp trực tiếp trong `@Query`: viết pattern Cypher rõ ràng, lọc theo tham số, trả về entity hoặc projection phù hợp và ánh xạ tham số Java bằng `@Param`. Nắm vững cách kết hợp chúng là nền tảng để đọc, viết và tối ưu các truy vấn đồ thị phức tạp hơn.
