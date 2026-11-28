# Giới hạn áp dụng Sort từ Pageable cho @Query

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt cách Spring Data Neo4j áp dụng `Sort` cho derived query và custom query dùng `@Query`.
- Giải thích vì sao truyền một `Pageable` đã sắp xếp chưa đủ để thay đổi thứ tự của Cypher tùy chỉnh.
- Dùng SpEL extension `orderBy` để đưa tiêu chí sắp xếp từ `Pageable` hoặc `Sort` vào câu Cypher.
- Kết hợp `ORDER BY`, `SKIP`, `LIMIT` và `countQuery` đúng vị trí khi trả về `Slice` hoặc `Page`.
- Chọn thứ tự ổn định và nhận biết những giới hạn khi sắp xếp kết quả đồ thị.

## 1. Pageable gồm phân trang và sắp xếp

`Pageable` là abstraction của Spring Data để truyền thông tin trang vào repository. Một đối tượng `Pageable` thường chứa:

- Số trang, bắt đầu từ 0.
- Kích thước trang.
- Thông tin sắp xếp, biểu diễn bằng `Sort`.

Ví dụ:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending()
);
```

Đối tượng trên yêu cầu lấy trang đầu tiên, tối đa 20 kết quả và sắp xếp theo property `name` tăng dần.

Với derived query, Spring Data Neo4j (SDN) tạo Cypher từ tên phương thức và tự xử lý thông tin phân trang, sắp xếp:

```java
Page<Person> findByActiveTrue(Pageable pageable);
```

Nếu gọi bằng một `Pageable` có `Sort`, thứ tự được đưa vào truy vấn do SDN tạo.

Với phương thức dùng `@Query`, nhà phát triển đã tự viết Cypher. SDN không thể mặc định đoán vị trí cần chèn `ORDER BY` vào mọi câu truy vấn tùy chỉnh. Vì vậy, **Sort bên trong Pageable không tự động thay đổi thứ tự của custom Cypher**. Cần khai báo rõ cách đưa Sort vào câu truy vấn.

Đây là giới hạn quan trọng khi chuyển từ derived query sang `@Query`: cùng nhận một kiểu tham số `Pageable`, nhưng trách nhiệm xây dựng thứ tự trong custom query thuộc về câu Cypher và cách khai báo của bạn.

## 2. Vì sao Sort không tự áp dụng vào @Query?

Một câu Cypher tùy chỉnh có thể có cấu trúc phức tạp:

```cypher
MATCH (p:Person)-[:MEMBER_OF]->(d:Department)
WHERE d.code = $departmentCode
RETURN p
```

SDN không thể biết chắc nên sắp xếp theo:

- Property của node `Person`.
- Property của node `Department`.
- Một biểu thức tính toán.
- Giá trị được tổng hợp từ relationship.
- Alias hoặc kết quả trung gian trong các mệnh đề `WITH`.

Do đó, với `@Query`, không nên giả định rằng:

```java
@Query("""
    MATCH (p:Person)
    RETURN p
    """)
List<Person> findPeople(Pageable pageable);
```

sẽ tự động thêm `ORDER BY` theo `pageable.getSort()`. Nếu không có cơ chế chèn Sort, phần sắp xếp trong `Pageable` không được dùng cho câu Cypher tùy chỉnh.

SDN cung cấp SpEL extension tên `orderBy` để chủ động đưa thông tin sắp xếp vào custom query. Đây là cách được tài liệu SDN hướng dẫn cho trường hợp cần dynamic sort với `@Query`.

## 3. Dùng orderBy(#pageable) trong @Query

Trong custom query, biểu thức:

```text
:#{orderBy(#pageable)}
```

yêu cầu SDN chuyển phần `Sort` của tham số `Pageable` thành đoạn `ORDER BY` phù hợp với truy vấn.

Trong SpEL context của SDN:

- `#pageable` tham chiếu đến tham số kiểu `Pageable`.
- `orderBy(...)` là extension do SDN cung cấp.
- Kết quả được chèn vào câu Cypher tại vị trí biểu thức xuất hiện.

Ví dụ repository dùng `Slice`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {

    @Query("""
        MATCH (p:Person)
        WHERE p.active = $active
        RETURN p :#{orderBy(#pageable)}
        SKIP $skip LIMIT $limit
        """)
    Slice<Person> findSliceByActive(
        @Param("active") boolean active,
        Pageable pageable
    );
}
```

Khi gọi:

```java
Pageable pageable = PageRequest.of(
    0,
    10,
    Sort.by("name").ascending()
);

Slice<Person> people =
    personRepository.findSliceByActive(true, pageable);
```

SDN dùng Sort trong `pageable` để tạo phần `ORDER BY`; đồng thời cung cấp các tham số `$skip` và `$limit` cho vị trí trang và kích thước trang. Đoạn Cypher sau khi xử lý có ý nghĩa tương đương:

```cypher
MATCH (p:Person)
WHERE p.active = $active
RETURN p
ORDER BY p.name ASC
SKIP $skip
LIMIT $limit
```

Đây là minh họa kết quả với tiêu chí sắp xếp theo `name`; đoạn Cypher thực tế còn phụ thuộc vào các tiêu chí và hướng sắp xếp trong `Sort`.

**Vị trí của extension rất quan trọng:** đặt `orderBy(#pageable)` ở phần sau `RETURN`, tại vị trí Cypher chấp nhận `ORDER BY`, và trước `SKIP`/`LIMIT`. Không đặt biểu thức này vào phần điều kiện `WHERE` hoặc vị trí của một giá trị tham số thông thường.

## 4. Dùng orderBy(#sort) khi chỉ cần Sort

Nếu phương thức chỉ cần sắp xếp, không cần số trang và kích thước trang, có thể nhận trực tiếp `Sort`:

```java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person)
    WHERE p.active = $active
    RETURN p :#{orderBy(#sort)}
    """)
List<Person> findActivePeople(
    @Param("active") boolean active,
    Sort sort
);
```

Gọi phương thức:

```java
List<Person> people = personRepository.findActivePeople(
    true,
    Sort.by("name").ascending()
        .and(Sort.by("id").ascending())
);
```

Trong SpEL context, tham số kiểu `Sort` có tên `#sort`. Vì thế:

| Tham số repository | SpEL extension |
| --- | --- |
| `Pageable pageable` | `:#{orderBy(#pageable)}` |
| `Sort sort` | `:#{orderBy(#sort)}` |

Không cần khai báo đồng thời cả `Pageable` và `Sort` cho một phương thức. `Pageable` đã chứa thông tin `Sort`; hai tham số đặc biệt này không được kết hợp trong cùng một query method.

## 5. Phân trang custom query với Slice

`Slice<T>` cho biết có thể còn một trang tiếp theo hay không. Nó không cung cấp tổng số phần tử và tổng số trang như `Page<T>`.

Với custom query trả về `Slice`, câu Cypher phải tự xử lý phần phân trang:

- Có `$skip` để xác định vị trí bắt đầu.
- Có `$limit` để giới hạn số kết quả.
- Có thứ tự ổn định để các lần lấy trang không phụ thuộc thứ tự ngẫu nhiên của graph.

Ví dụ:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.departmentCode = $departmentCode
    RETURN p :#{orderBy(#pageable)}
    SKIP $skip LIMIT $limit
    """)
Slice<Person> findSliceByDepartment(
    @Param("departmentCode") String departmentCode,
    Pageable pageable
);
```

Nếu bỏ `$skip` hoặc `$limit`, SDN có thể phát cảnh báo và kết quả không phân trang như mong đợi. `Pageable` cần được truyền vào phương thức, kể cả khi chỉ dùng nó để lấy offset và giới hạn.

Khi cần dynamic sort, dùng `orderBy(#pageable)`. Nếu câu truy vấn chỉ dùng thứ tự cố định được viết trực tiếp trong Cypher, truyền một `Pageable` không có Sort và tự khai báo `ORDER BY`.

Ví dụ thứ tự cố định:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.active = $active
    RETURN p
    ORDER BY p.name ASC, p.id ASC
    SKIP $skip LIMIT $limit
    """)
Slice<Person> findActivePeople(
    @Param("active") boolean active,
    Pageable pageable
);
```

Cách gọi tương ứng:

```java
import org.springframework.data.domain.PageRequest;

Pageable pageable = PageRequest.of(0, 20);
```

Nếu truyền một `Pageable` có Sort vào ví dụ dùng thứ tự cố định, SDN không tự ghi đè hoặc thay thế `ORDER BY` đã viết trong Cypher. Hãy dùng đúng một chiến lược sắp xếp để tránh hiểu nhầm kết quả.

## 6. Phân trang custom query với Page và countQuery

`Page<T>` cung cấp thêm tổng số phần tử và tổng số trang. Để tính các thông tin này, SDN cần một truy vấn đếm. Với custom query, nên khai báo `countQuery` riêng để xác định chính xác tập kết quả cần đếm.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.neo4j.repository.query.Query;

@Query(
    value = """
        MATCH (p:Person)
        WHERE p.departmentCode = $departmentCode
        RETURN p :#{orderBy(#pageable)}
        SKIP $skip LIMIT $limit
        """,
    countQuery = """
        MATCH (p:Person)
        WHERE p.departmentCode = $departmentCode
        RETURN count(p)
        """
)
Page<Person> findPageByDepartment(
    @Param("departmentCode") String departmentCode,
    Pageable pageable
);
```

Truy vấn chính chịu trách nhiệm:

- Tìm các node phù hợp.
- Áp dụng dynamic sort qua `orderBy(#pageable)`.
- Áp dụng offset và giới hạn kết quả qua `SKIP` và `LIMIT`.

Truy vấn đếm chịu trách nhiệm xác định tổng số node thỏa điều kiện. Nó không cần `ORDER BY`, `SKIP` hoặc `LIMIT`, vì các thành phần đó không có ý nghĩa khi đếm tổng.

Điều kiện lọc trong `countQuery` phải tương ứng với điều kiện của truy vấn chính. Nếu truy vấn chính đếm các node `Person` thuộc một phòng ban, nhưng `countQuery` lại đếm tất cả `Person`, metadata của `Page` sẽ sai.

Nếu custom query có `MATCH` qua relationship một-nhiều làm một node gốc xuất hiện ở nhiều record, cần xử lý hình dạng kết quả trước khi phân trang. Có thể dùng `collect()` để tạo một record cho mỗi node gốc, hoặc dùng `count(DISTINCT p)` trong count query nếu logic thực sự đếm node duy nhất. Nếu không, trang kết quả có thể chứa node lặp và tổng số đếm có thể lớn hơn số entity thực tế.

## 7. Static ORDER BY và dynamic Sort là hai lựa chọn khác nhau

Có hai cách tổ chức thứ tự cho custom query:

| Cách | Cypher | Cách truyền Pageable |
| --- | --- | --- |
| Thứ tự cố định | Viết `ORDER BY p.name ASC` trực tiếp | Truyền Pageable không có Sort |
| Thứ tự động | Dùng `:#{orderBy(#pageable)}` | Truyền Pageable có Sort |
| Chỉ sắp xếp động, không phân trang | Dùng `:#{orderBy(#sort)}` | Truyền Sort trực tiếp |

Không nên ghép hai `ORDER BY` độc lập vào cùng một câu truy vấn. Ví dụ, nếu Cypher đã có `ORDER BY p.createdAt DESC` rồi lại thêm `orderBy(#pageable)` tạo một mệnh đề `ORDER BY` khác, truy vấn có thể không hợp lệ hoặc không thể hiện thứ tự mong muốn.

Nếu cần một thứ tự mặc định khi client không gửi Sort, có thể chuẩn hóa `Pageable` tại service hoặc controller để luôn có tiêu chí sắp xếp mặc định. Nếu yêu cầu nghiệp vụ là luôn có thứ tự cố định, hãy để Cypher quản lý thứ tự và truyền Pageable không có Sort.

## 8. Sort cần dùng property phù hợp với domain

`Sort` của Spring Data được mô tả bằng tên property và hướng tăng/giảm, ví dụ:

```java
Sort sort = Sort.by(
    Sort.Order.asc("name"),
    Sort.Order.desc("createdAt")
);
```

Đây là tên property của entity mà repository quản lý, không phải một đoạn Cypher tùy ý. Không truyền một chuỗi như `"name DESC, rand()"` để mong Spring hiểu đó là biểu thức sắp xếp hợp lệ.

Nếu cần sắp xếp theo biểu thức tính toán hoặc kết quả tổng hợp, hãy viết biểu thức đó trực tiếp trong Cypher, hoặc xây dựng truy vấn động bằng cơ chế phù hợp như Cypher-DSL/custom repository fragment. `Sort` không phải ngôn ngữ để truyền toàn bộ biểu thức Cypher.

Khi nhận tên trường sắp xếp từ query parameter của API, hãy kiểm tra danh sách property được phép. Ví dụ, API chỉ cho phép `name`, `createdAt` và `id`; service chuyển lựa chọn hợp lệ thành `Sort`. Không nên chuyển thẳng một chuỗi sort tùy ý từ request vào cấu trúc truy vấn.

## 9. Thứ tự ổn định khi phân trang

Nếu nhiều node có cùng giá trị của property sắp xếp, thứ tự giữa các node đó có thể không xác định. Khi người dùng chuyển từ trang này sang trang khác, các node có cùng giá trị sort có thể xuất hiện lặp hoặc bị bỏ qua nếu dữ liệu thay đổi hoặc thứ tự không ổn định.

Ví dụ, chỉ sắp xếp theo `name`:

```java
Sort.by("name").ascending()
```

Nếu nhiều người có cùng tên, hãy thêm một property phân biệt ổn định:

```java
Sort.by("name").ascending()
    .and(Sort.by("id").ascending())
```

Với thứ tự cố định trong Cypher:

```cypher
ORDER BY p.name ASC, p.id ASC
```

Một tiêu chí phụ duy nhất như ID giúp thứ tự giữa các bản ghi có cùng tên ổn định hơn. Nó không ngăn mọi thay đổi dữ liệu giữa hai lần truy vấn, nhưng giúp việc phân trang dễ dự đoán và nhất quán hơn.

## 10. Những giới hạn cần nhớ

| Tình huống | Hành vi hoặc yêu cầu |
| --- | --- |
| Derived query có Pageable đã sắp xếp | SDN tạo truy vấn và áp dụng Sort tự động |
| `@Query` chỉ có tham số Pageable | Sort không tự động được chèn vào Cypher |
| `@Query` dùng `:#{orderBy(#pageable)}` | SDN chèn thứ tự từ Sort của Pageable |
| `@Query` dùng `:#{orderBy(#sort)}` | SDN chèn thứ tự từ tham số Sort riêng |
| Custom Slice thiếu `$skip` hoặc `$limit` | Không phân trang đúng theo Pageable; SDN có thể phát cảnh báo |
| Custom Page không có count query phù hợp | Không thể xác định chính xác tổng số phần tử theo logic mong muốn |
| Pageable có Sort nhưng query dùng static ORDER BY | Thứ tự trong Cypher vẫn là thứ tự đã khai báo |
| MATCH một-nhiều tạo nhiều record cho một root | Phải xử lý duplicate/collect trước khi phân trang theo root entity |
| Sort theo biểu thức Cypher tính toán | Cần biểu thức Cypher hoặc cơ chế xây dựng query riêng, không chỉ tên property trong Sort |

## 11. Quy trình kiểm tra khi Sort không có tác dụng

Khi gửi `Pageable` có Sort nhưng kết quả không đổi thứ tự, hãy kiểm tra:

1. Phương thức repository là derived query hay dùng `@Query`.
2. Nếu dùng `@Query`, có đặt `:#{orderBy(#pageable)}` ở vị trí hợp lệ sau phần trả về hay chưa.
3. Tên trong SpEL có đúng là `#pageable` hoặc `#sort` theo kiểu tham số hay không.
4. Property trong Sort có tồn tại trong entity và đúng với mô hình domain không.
5. Query có một mệnh đề `ORDER BY` rõ ràng, không bị lặp hoặc xung đột không.
6. Nếu phân trang, query có cả `SKIP $skip` và `LIMIT $limit` hay chưa.
7. Nếu trả về `Page`, `countQuery` có cùng điều kiện lọc với query chính hay không.
8. Nếu truy vấn qua relationship một-nhiều, mỗi record có tương ứng với một root entity hay chưa.

Có thể kiểm tra trực tiếp Cypher sau khi thay giá trị tham số để chắc chắn rằng `ORDER BY`, `SKIP` và `LIMIT` xuất hiện đúng thứ tự và đang áp dụng lên tập kết quả mong muốn.

## 12. Câu hỏi tự kiểm tra

1. Vì sao Sort trong Pageable không tự động áp dụng cho mọi custom query dùng `@Query`?
2. `:#{orderBy(#pageable)}` có nhiệm vụ gì?
3. Khi phương thức chỉ nhận `Sort`, cần dùng tên nào trong SpEL?
4. Vì sao custom query trả về `Slice` cần có `$skip` và `$limit`?
5. Vì sao custom query trả về `Page` cần `countQuery`?
6. Nếu đã viết static `ORDER BY`, nên truyền Pageable có Sort hay không?
7. Vì sao cần thêm ID làm tiêu chí sắp xếp phụ?
8. Vì sao một truy vấn `MATCH` qua relationship một-nhiều có thể làm sai phân trang theo root entity?
9. Khi cần sort theo biểu thức Cypher tính toán, nên dùng cách nào?

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2 – Custom queries và orderBy extension](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j – FAQ: custom query với Page và Slice](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – Defining Query Methods, Paging and Sorting](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)

## Kết luận

Với derived query, SDN có thể tạo Cypher và áp dụng Sort từ Pageable tự động. Với custom query `@Query`, câu Cypher do nhà phát triển kiểm soát nên Sort không tự được chèn vào. Muốn dùng sắp xếp động, hãy đặt `:#{orderBy(#pageable)}` trong câu truy vấn; nếu chỉ cần Sort, dùng `:#{orderBy(#sort)}`.

Phân trang custom query còn cần `SKIP $skip` và `LIMIT $limit`. Nếu trả về `Page`, hãy khai báo `countQuery` đếm đúng tập kết quả. Khi không dùng dynamic sort, hãy truyền Pageable không có Sort và viết thứ tự ổn định trực tiếp trong Cypher. Luôn kiểm tra mỗi record đại diện cho đúng một entity gốc trước khi phân trang, đặc biệt với các truy vấn đi qua relationship một-nhiều.
