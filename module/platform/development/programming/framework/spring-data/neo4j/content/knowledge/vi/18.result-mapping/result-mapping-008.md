# Alias cột, kết quả tổng hợp và giá trị scalar

Một truy vấn Cypher có thể trả về cả node, relationship, property riêng lẻ hoặc giá trị được tính bằng hàm tổng hợp. Khi dùng Spring Data Neo4j, kết quả cần được ánh xạ đúng với kiểu Java mà repository khai báo. Nếu tên cột không khớp projection, kiểu số không phù hợp hoặc truy vấn trả về số dòng khác với dự kiến, ứng dụng có thể nhận `null`, lỗi chuyển đổi hoặc kết quả không đúng nghiệp vụ.

Bài học này giải thích cách đặt alias bằng `AS`, ánh xạ kết quả nhiều cột vào projection, trả về giá trị scalar như `Long` và `Double`, đồng thời xử lý các hàm tổng hợp như `count`, `sum`, `avg` và `collect`.

## 1. RETURN có thể trả về nhiều hình dạng dữ liệu

Trong Cypher, `RETURN` xác định các cột của kết quả. Ví dụ:

```cypher
MATCH (p:Person)
RETURN p
```

Truy vấn trả về node `Person`. Nếu chỉ cần một vài property:

```cypher
MATCH (p:Person)
RETURN p.personId, p.name
```

Kết quả lúc này có hai cột, mỗi cột mang tên biểu thức tương ứng. Để chủ động tên cột, dùng alias:

```cypher
MATCH (p:Person)
RETURN p.personId AS personId,
       p.name AS displayName
```

Alias là tên mà phần ánh xạ kết quả có thể sử dụng. Khi trả về projection hoặc DTO, hãy đặt alias ổn định và có ý nghĩa thay vì phụ thuộc vào tên biểu thức mặc định do Neo4j tạo ra.

## 2. Alias cột với AS

`AS` đặt tên cho một biểu thức trong `RETURN` hoặc `WITH`:

```cypher
MATCH (p:Person)
RETURN p.name AS personName,
       p.age AS personAge
```

Ở đây, kết quả có hai cột `personName` và `personAge`. Nếu interface projection khai báo `getPersonName()` và `getPersonAge()`, tên alias tương ứng với property mà Spring Data dùng để ánh xạ.

Một số quy tắc nên tuân thủ:

- Dùng alias theo camelCase tương ứng với tên getter/property Java.
- Mỗi cột nên có alias rõ ràng, duy nhất.
- Không dùng cùng một alias cho hai biểu thức khác nhau trong cùng kết quả.
- Khi đổi alias trong Cypher, cập nhật projection, DTO hoặc phần đọc `Record` tương ứng.
- Với truy vấn tổng hợp, alias cả biểu thức tổng hợp để code đọc kết quả dễ hiểu.

Ví dụ, thay vì trả về một biểu thức khó nhận diện:

```cypher
MATCH (p:Person)
RETURN count(p)
```

nên đặt tên:

```cypher
MATCH (p:Person)
RETURN count(p) AS peopleCount
```

## 3. Ánh xạ nhiều cột vào interface projection

Khi truy vấn trả về nhiều giá trị scalar, interface projection là cách gọn để định nghĩa hình dạng kết quả.

Giả sử cần hiển thị thống kê một khoa:

```java
public interface DepartmentSummary {
    String getDepartmentCode();
    Long getPeopleCount();
    Double getAverageAge();
}
```

Repository:

```java
public interface DepartmentRepository
        extends Neo4jRepository<Department, String> {

    @Query("""
        MATCH (d:Department {departmentCode: $code})
        OPTIONAL MATCH (p:Person)-[:BELONGS_TO]->(d)
        RETURN d.departmentCode AS departmentCode,
               count(p) AS peopleCount,
               avg(p.age) AS averageAge
        """)
    Optional<DepartmentSummary> summarize(
        @Param("code") String code
    );
}
```

Các alias trong `RETURN` khớp với getter của projection:

| Alias Cypher | Getter Java | Kiểu kết quả |
|---|---|---|
| `departmentCode` | `getDepartmentCode()` | `String` |
| `peopleCount` | `getPeopleCount()` | `Long` |
| `averageAge` | `getAverageAge()` | `Double` có thể null |

`OPTIONAL MATCH` giữ node `Department` ngay cả khi chưa có người thuộc khoa đó. Khi khoa tồn tại nhưng không có người, `count(p)` trả về `0`, còn `avg(p.age)` có thể là `null` vì không có giá trị tuổi để tính trung bình. Do đó, dùng wrapper `Double` phù hợp hơn primitive `double` cho getter có thể nhận null.

Nếu không tồn tại khoa có mã được truyền vào, truy vấn không tạo dòng kết quả và `Optional<DepartmentSummary>` là empty. Đây là tình huống khác với một dòng có `peopleCount = 0` và `averageAge = null`.

## 4. Trả về một giá trị scalar

Scalar là một giá trị đơn như số lượng, tổng, trung bình, tên hoặc trạng thái. Nếu Cypher chỉ trả về một cột, repository có thể khai báo kiểu Java tương ứng.

Ví dụ đếm số người theo trạng thái:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person)
        WHERE p.status = $status
        RETURN count(p) AS total
        """)
    Long countByStatusValue(@Param("status") String status);
}
```

`count(p)` trả về số nguyên 64-bit, vì vậy `Long` là kiểu Java phù hợp. Kể cả khi không có node nào khớp, truy vấn tổng hợp không có grouping key vẫn trả về một dòng với giá trị `0`.

Ví dụ lấy danh sách scalar thay vì entity:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.active = true
    RETURN p.name AS name
    ORDER BY name
    """)
List<String> findActiveNames();
```

Mỗi dòng trả về một chuỗi nên kết quả được ánh xạ thành `List<String>`. Nếu truy vấn không có dòng nào, danh sách rỗng được trả về.

Với giá trị có thể không tồn tại, có thể khai báo `Optional<T>` nếu truy vấn trả về tối đa một dòng:

```java
@Query("""
    MATCH (p:Person {personId: $personId})
    RETURN p.name AS name
    """)
Optional<String> findName(@Param("personId") String personId);
```

Không khai báo một kiểu scalar đơn cho truy vấn có thể trả về nhiều dòng. Nếu mỗi node tạo ra một giá trị, hãy dùng `List<T>` hoặc giới hạn truy vấn để bảo đảm chỉ có một dòng theo đúng nghiệp vụ.

## 5. Các hàm tổng hợp thường dùng

Cypher cung cấp các hàm tổng hợp để tính toán trên nhiều dòng kết quả.

| Hàm | Ý nghĩa | Ví dụ kiểu Java thường dùng |
|---|---|---|
| `count(expr)` | Đếm giá trị khác null | `Long` |
| `sum(expr)` | Tính tổng giá trị số | `Long` hoặc `Double`, tùy kiểu đầu vào |
| `avg(expr)` | Tính trung bình số học | `Double` |
| `min(expr)` | Giá trị nhỏ nhất | Kiểu tương ứng với biểu thức |
| `max(expr)` | Giá trị lớn nhất | Kiểu tương ứng với biểu thức |
| `collect(expr)` | Gom các giá trị thành danh sách | `List<T>` |

Ví dụ tính tổng và trung bình tuổi:

```cypher
MATCH (p:Person)
WHERE p.age IS NOT NULL
RETURN count(p) AS peopleCount,
       sum(p.age) AS totalAge,
       avg(p.age) AS averageAge,
       min(p.age) AS youngestAge,
       max(p.age) AS oldestAge
```

Kết quả là một dòng gồm năm giá trị tổng hợp. Với property tuổi được lưu dưới dạng số nguyên, `count` và `sum` thường được ánh xạ thành `Long`, còn `avg` thành `Double`. Cần khai báo kiểu projection phù hợp và kiểm tra kiểu dữ liệu thật trong database.

### count(*) và count(expression)

`count(*)` đếm số dòng đầu vào. `count(expression)` chỉ đếm các dòng mà biểu thức không phải `null`.

Sự khác biệt rất quan trọng khi dùng `OPTIONAL MATCH`:

```cypher
MATCH (d:Department {departmentCode: $code})
OPTIONAL MATCH (p:Person)-[:BELONGS_TO]->(d)
RETURN count(*) AS rowCount,
       count(p) AS peopleCount
```

Nếu khoa tồn tại nhưng không có người, `OPTIONAL MATCH` vẫn giữ một dòng với `p = null`. Khi đó `count(*)` là `1`, còn `count(p)` là `0`. Nếu muốn đếm số node người thực sự tìm được, hãy dùng `count(p)`.

### collect() và loại bỏ giá trị trùng

`collect(expr)` gom các giá trị khác null thành danh sách:

```cypher
MATCH (d:Department {departmentCode: $code})
OPTIONAL MATCH (p:Person)-[:BELONGS_TO]->(d)
RETURN collect(p.name) AS peopleNames
```

Nếu không có người, danh sách thu được là danh sách rỗng vì `collect` bỏ qua `null`. Nếu cần loại trùng:

```cypher
MATCH (p:Person)-[:BELONGS_TO]->(d:Department)
RETURN d.departmentCode AS departmentCode,
       collect(DISTINCT p.name) AS uniqueNames
```

Chỉ dùng `DISTINCT` khi nghiệp vụ cần các giá trị duy nhất. Nó có thể làm tăng chi phí xử lý và thay đổi ý nghĩa nếu những phần tử trùng nhau thực sự đại diện cho các sự kiện riêng.

## 6. GROUP BY trong Cypher thông qua biểu thức không tổng hợp

Cypher không dùng cú pháp `GROUP BY` riêng như SQL. Các biểu thức trong `RETURN` hoặc `WITH` không nằm trong hàm tổng hợp trở thành khóa nhóm.

Ví dụ đếm số người theo trạng thái:

```cypher
MATCH (p:Person)
RETURN p.status AS status,
       count(p) AS peopleCount
ORDER BY peopleCount DESC
```

`p.status` là biểu thức không tổng hợp nên mỗi giá trị trạng thái tạo một nhóm. `count(p)` tính số người trong nhóm đó.

Có thể nhóm theo nhiều chiều:

```cypher
MATCH (p:Person)-[:BELONGS_TO]->(d:Department)
RETURN d.departmentCode AS departmentCode,
       p.status AS status,
       count(p) AS peopleCount
ORDER BY departmentCode, status
```

Mỗi cặp `departmentCode` và `status` tạo thành một nhóm riêng. Nếu một người có nhiều relationship phù hợp, cần xác định liệu đang đếm số đường đi hay số người khác nhau. Dùng `count(DISTINCT p)` khi muốn đếm mỗi node người một lần trong nhóm.

## 7. Dùng WITH để chia giai đoạn tổng hợp

`WITH` chuyển kết quả trung gian sang phần tiếp theo của truy vấn. Nó có thể lọc sau khi tổng hợp, đổi tên biểu thức và giới hạn biến còn trong phạm vi.

Ví dụ, chỉ lấy các khoa có ít nhất 10 người:

```cypher
MATCH (p:Person)-[:BELONGS_TO]->(d:Department)
WITH d, count(DISTINCT p) AS peopleCount
WHERE peopleCount >= $minimumPeople
RETURN d.departmentCode AS departmentCode,
       d.name AS departmentName,
       peopleCount
ORDER BY peopleCount DESC
```

Ở đây:

1. `MATCH` tìm người và khoa.
2. `WITH` nhóm theo `d` và tính `peopleCount`.
3. `WHERE` lọc kết quả tổng hợp sau khi đã tính số người.
4. `RETURN` trả về các trường cần hiển thị.

Sau `WITH`, chỉ những biến được đưa vào `WITH` mới còn trong phạm vi. Vì vậy, nếu phần sau cần dùng `d`, hãy giữ `d` trong danh sách `WITH`; nếu chỉ trả `peopleCount`, biến `d` sẽ không còn khả dụng.

## 8. Ánh xạ kết quả tổng hợp vào projection

Projection giúp đóng gói một dòng kết quả tổng hợp thành kiểu Java có tên rõ ràng:

```java
public interface DepartmentStatusCount {
    String getDepartmentCode();
    String getStatus();
    Long getPeopleCount();
}
```

```java
@Query("""
    MATCH (p:Person)-[:BELONGS_TO]->(d:Department)
    RETURN d.departmentCode AS departmentCode,
           p.status AS status,
           count(DISTINCT p) AS peopleCount
    ORDER BY departmentCode, status
    """)
List<DepartmentStatusCount> countPeopleByDepartmentAndStatus();
```

Mỗi dòng trong kết quả tương ứng với một tổ hợp khoa và trạng thái. Alias `departmentCode`, `status` và `peopleCount` cần khớp với getter trong interface. `Long` được dùng cho số đếm để tránh giới hạn của `Integer` khi dữ liệu tăng.

Nếu cần một DTO class thay cho interface projection, có thể dùng constructor mapping được Spring Data Neo4j hỗ trợ theo kiểu kết quả và phiên bản thư viện. Hãy kiểm tra thứ tự tham số constructor, tên cột và kiểu dữ liệu thực tế. Khi mapping tùy chỉnh phức tạp, `Neo4jClient` cho phép đọc từng `Record` và chuyển đổi tường minh.

## 9. Ánh xạ thủ công bằng Neo4jClient

`Neo4jClient` phù hợp khi muốn kiểm soát việc chuyển từng cột Cypher sang DTO. Ví dụ:

```java
public record DepartmentStatsRow(
    String departmentCode,
    long peopleCount,
    Double averageAge
) {}
```

```java
Optional<DepartmentStatsRow> result = neo4jClient.query("""
    MATCH (d:Department {departmentCode: $code})
    OPTIONAL MATCH (p:Person)-[:BELONGS_TO]->(d)
    RETURN d.departmentCode AS departmentCode,
           count(p) AS peopleCount,
           avg(p.age) AS averageAge
    """)
    .bind(code).to("code")
    .fetchAs(DepartmentStatsRow.class)
    .mappedBy((typeSystem, record) -> new DepartmentStatsRow(
        record.get("departmentCode").asString(),
        record.get("peopleCount").asLong(),
        record.get("averageAge").isNull()
            ? null
            : record.get("averageAge").asDouble()
    ))
    .one();
```

Mapper đọc giá trị theo alias đã đặt. Với `averageAge`, kiểm tra `isNull()` trước khi gọi `asDouble()` vì hàm `avg()` có thể không có giá trị khi không có tuổi hợp lệ. Phương thức `.one()` biểu thị mong đợi tối đa một dòng và trả về `Optional`; nếu truy vấn trả nhiều dòng, API sẽ báo lỗi thay vì âm thầm chọn một dòng.

Nếu cần nhiều dòng, dùng `.all()` và ánh xạ thành collection. Nếu chỉ cần map đơn giản, `fetch().all()` có thể trả về danh sách map theo tên cột; cách mapping tường minh bằng `mappedBy` thường giúp kiểm soát kiểu và xử lý null tốt hơn.

## 10. Phân biệt không có dòng kết quả và giá trị null

Hai tình huống sau không giống nhau:

**Không có dòng kết quả:** `MATCH` không tìm được node hoặc pattern. Repository trả collection rỗng hoặc `Optional.empty()` tùy kiểu trả về.

**Có dòng nhưng một cột là null:** node gốc tồn tại nhưng property không có, hoặc hàm tổng hợp không có giá trị để tính. Projection vẫn có thể được tạo, nhưng trường tương ứng là null.

Ví dụ:

```cypher
MATCH (d:Department {departmentCode: $code})
OPTIONAL MATCH (p:Person)-[:BELONGS_TO]->(d)
RETURN d.name AS departmentName,
       count(p) AS peopleCount,
       avg(p.age) AS averageAge
```

- Nếu khoa không tồn tại, không có dòng.
- Nếu khoa tồn tại nhưng không có người, `peopleCount = 0` và `averageAge = null`.
- Nếu có người nhưng tất cả `age` đều null, `peopleCount` lớn hơn 0 nhưng `averageAge = null`.
- Nếu có người với tuổi hợp lệ, `averageAge` là số thực.

Hãy chọn `Optional`, collection, wrapper type và quy tắc mặc định theo đúng các trường hợp này. Không thay null bằng `0` nếu nghiệp vụ cần phân biệt “không có dữ liệu” với “giá trị bằng 0”.

## 11. Các lỗi ánh xạ thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Projection trả về null ở một trường | Alias không khớp tên getter/property | Đặt alias trùng tên property mà projection mong đợi. |
| Lỗi chuyển kiểu số | Khai báo `Integer` trong khi giá trị tổng hợp là số nguyên 64-bit hoặc `Double` | Dùng `Long` cho count và kiểu số phù hợp với biểu thức. |
| Scalar repository không nhận kết quả | Truy vấn trả nhiều cột hoặc nhiều dòng trong khi kiểu Java chỉ chứa một giá trị | Chỉ trả một cột và bảo đảm cardinality, hoặc dùng `List`/projection. |
| `Optional` rỗng dù hàm count bằng 0 mong đợi | Truy vấn có grouping key nhưng không tạo nhóm nào | Dùng truy vấn tổng hợp không nhóm hoặc `OPTIONAL MATCH` từ node gốc phù hợp. |
| `count(*)` lớn hơn số node thực tế | `OPTIONAL MATCH` tạo dòng có biến null hoặc nhiều relationship nhân số dòng | Dùng `count(node)` hoặc `count(DISTINCT node)` theo mục tiêu. |
| `avg()` gây lỗi khi không có dữ liệu | Ánh xạ null vào primitive | Dùng `Double` hoặc xử lý null tường minh. |
| Danh sách collect có phần tử lặp | Nhiều đường đi tạo cùng giá trị | Dùng `collect(DISTINCT expression)` nếu cần loại trùng. |

## 12. Quy trình thiết kế result mapping

1. Xác định kết quả cần trả về là entity, một scalar, danh sách scalar hay nhiều cột.
2. Viết `RETURN` chỉ với những biểu thức cần thiết.
3. Đặt alias ổn định theo camelCase và khớp với projection/DTO.
4. Chọn kiểu Java dựa trên kiểu Cypher thực tế: `Long` cho count, `Double` cho avg và wrapper cho giá trị có thể null.
5. Kiểm tra cardinality: không dòng, một dòng hay nhiều dòng.
6. Với aggregation, xác định khóa nhóm và sự khác nhau giữa `count(*)`, `count(node)` và `count(DISTINCT node)`.
7. Kiểm thử dữ liệu rỗng, property null, nhóm không tồn tại và nhiều relationship trùng đường đi.
8. Dùng `Neo4jClient` khi cần mapping tùy chỉnh hoặc xử lý null/kiểu dữ liệu ở mức từng record.

## 13. Ghi nhớ

Alias bằng `AS` là hợp đồng giữa Cypher và lớp Java nhận kết quả. Với interface projection, tên alias phải khớp property/getter; với scalar, truy vấn cần trả đúng một cột và kiểu Java phải tương thích; với danh sách scalar, mỗi dòng tạo một phần tử trong collection.

Các hàm tổng hợp cần được hiểu theo cardinality và null: `count(expr)` bỏ qua null, `count(*)` đếm dòng, `collect()` bỏ qua null, còn `avg()` có thể trả null khi không có giá trị số. Các biểu thức không tổng hợp tạo khóa nhóm, và `WITH` giúp chia truy vấn thành các giai đoạn. Khi hiểu rõ hình dạng dòng kết quả, alias, kiểu và số dòng, việc ánh xạ kết quả trong Spring Data Neo4j sẽ dễ dự đoán và ít lỗi hơn.
