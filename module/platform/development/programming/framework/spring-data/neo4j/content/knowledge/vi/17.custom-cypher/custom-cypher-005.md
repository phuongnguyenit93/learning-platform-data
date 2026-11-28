# SpEL và các phần mở rộng biểu thức được SDN hỗ trợ

Spring Data Neo4j (SDN) cho phép dùng Spring Expression Language (SpEL) trong các truy vấn Cypher tùy chỉnh khai báo bằng `@Query`. SpEL giúp tính giá trị tham số, chèn một số thành phần cấu trúc mà Cypher không cho phép bind như tham số, tạo `ORDER BY` từ `Sort` hoặc `Pageable`, và tái sử dụng label được khai báo trên entity.

Các biểu thức này mở rộng khả năng tạo truy vấn, nhưng mỗi loại có vai trò khác nhau. Giá trị dữ liệu như tên, ID, ngày tháng vẫn nên truyền bằng tham số Cypher thông thường. Các extension như `literal`, `allOf` và `anyOf` phục vụ thành phần cấu trúc của câu truy vấn; chúng cần được kiểm soát chặt chẽ. Bài viết tập trung vào `@Query` của repository trong SDN native mapping.

## 1. Phân biệt tham số Cypher và SpEL

Trong Cypher, tham số thông thường có dạng `$name`, `$id` hoặc `$0`. Đây là lựa chọn mặc định khi chỉ cần thay giá trị dữ liệu:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("MATCH (p:Person) WHERE p.name = $name RETURN p")
    Optional<Person> findByName(@Param("name") String name);
}
```

SpEL được đặt trong `:#{...}` khi biểu thức cần được tính thành một giá trị tham số. Ví dụ, chuẩn hóa chuỗi đầu vào trước khi truyền cho Cypher:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.normalizedName = :#{#name.trim().toLowerCase()}
    RETURN p
    """)
Optional<Person> findByNormalizedName(@Param("name") String name);
```

SDN đánh giá biểu thức `#name.trim().toLowerCase()` rồi truyền kết quả cho Neo4j dưới dạng tham số. Biểu thức không biến giá trị thành một đoạn Cypher tùy ý. Đây là khác biệt quan trọng giữa parameter expression và literal extension.

Trong SpEL:

- `#name` tham chiếu tham số phương thức có tên `name`.
- `#pt1 + #pt2` có thể kết hợp hai tham số thành một giá trị.
- `:#{...}` đánh dấu biểu thức được đánh giá tại vị trí tham số của query.
- Tên tham số có thể được xác định nhờ `-parameters`; nếu không, dùng `@Param` để khai báo tên rõ ràng.

Ví dụ kết hợp hai tham số:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.displayName = :#{#firstName + ' ' + #lastName}
    RETURN p
    """)
Optional<Person> findByFullName(
    @Param("firstName") String firstName,
    @Param("lastName") String lastName
);
```

Nếu biểu thức chỉ trả về một giá trị đầu vào có thể bind, hãy dùng `$parameter` trực tiếp khi không cần xử lý thêm. Cách viết đó đơn giản hơn và giúp người đọc nhận ra ngay đâu là dữ liệu đầu vào.

## 2. Vì sao một số vị trí cần literal extension?

Cypher cho phép bind tham số ở vị trí giá trị, ví dụ:

```cypher
MATCH (p:Person)
WHERE p.name = $name
RETURN p
```

Nhưng các thành phần cấu trúc như label hoặc relationship type không thể được thay bằng tham số Cypher thông thường. Câu sau không phải cách dùng hợp lệ để chọn label động:

```cypher
MATCH (n:$label)
RETURN n
```

SDN cung cấp `literal(...)` để chèn một giá trị đã đánh giá thành literal trong câu query. Ví dụ:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("MATCH (n:`:#{literal(#label)}`) RETURN n")
List<BaseNode> findByLabel(@Param("label") String label);
```

Trong ví dụ này, `BaseNode` đại diện cho kiểu domain đã được mapping mà các node có label được tìm thấy có thể ánh xạ vào.

Nếu phương thức nhận `label = "ArchivedDocument"`, phần query được tạo sẽ có dạng:

```cypher
MATCH (n:`ArchivedDocument`)
RETURN n
```

Trong ví dụ, dấu backtick được viết tường minh trong chuỗi query để quote label; SDN không tự thêm backtick cho bạn. `literal` vẫn chèn thành phần cấu trúc vào câu query, không phải cơ chế bind dữ liệu. Chỉ cho phép các label đã được ứng dụng định nghĩa trước:

```java
import java.util.Set;

private static final Set<String> ALLOWED_LABELS =
    Set.of("Person", "Company", "ArchivedDocument");

public List<BaseNode> searchByLabel(String requestedLabel) {
    if (!ALLOWED_LABELS.contains(requestedLabel)) {
        throw new IllegalArgumentException("Unsupported label");
    }
    return repository.findByLabel(requestedLabel);
}
```

Áp dụng cùng nguyên tắc khi dùng literal cho relationship type. Không lấy trực tiếp label, relationship type hoặc đoạn query từ nội dung người dùng gửi lên.

## 3. `allOf` và `anyOf`: tạo biểu thức label từ danh sách

Khi cần lọc node theo nhiều label, SDN cung cấp hai list extensions:

- `allOf(...)` nối các label bằng toán tử `&`, nghĩa là node phải có tất cả label trong danh sách.
- `anyOf(...)` nối các label bằng toán tử `|`, nghĩa là node có ít nhất một label trong danh sách.

Ví dụ tìm node có đồng thời label `Bike`, `Gravel` và `Electric`:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("MATCH (n:`:#{allOf(#labels)}`) RETURN n")
List<BikeNode> findWithAllLabels(@Param("labels") List<String> labels);
```

Phần label expression được tạo tương ứng với dạng `Bike&Gravel&Electric`.

Nếu chỉ cần node có một trong các label được chọn:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("MATCH (n:`:#{anyOf(#labels)}`) RETURN n")
List<BikeNode> findWithAnyLabel(@Param("labels") List<String> labels);
```

Phần label expression được tạo tương ứng với dạng `Bike|Gravel|Electric`.

Các extension này được dùng cho label expression trong Cypher. Hãy kiểm tra danh sách đầu vào, giới hạn các label được phép và xử lý trường hợp collection rỗng theo hợp đồng API của ứng dụng. Nếu danh sách là dữ liệu do client cung cấp, không mặc định mọi giá trị đều là một label hợp lệ.

## 4. `#{#staticLabels}`: tái sử dụng label của entity

Một entity có thể khai báo primary label và các label tĩnh bổ sung:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node(primaryLabel = "Bike", labels = {"Gravel", "Easy Trail"})
public class BikeNode {

    @Id
    private String id;

    private String name;
}
```

Khi viết custom query, thay vì lặp lại tất cả label, có thể dùng `#{#staticLabels}`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface BikeRepository extends Neo4jRepository<BikeNode, String> {

    @Query("""
        MATCH (n:#{#staticLabels})
        WHERE n.id = $id
        RETURN n
        """)
    Optional<BikeNode> findByIdUsingStaticLabels(@Param("id") String id);
}
```

SDN thay biểu thức bằng các label tĩnh của domain type, tương đương:

```cypher
MATCH (n:`Bike`:`Gravel`:`Easy Trail`)
WHERE n.id = $id
RETURN n
```

Chú ý cú pháp: `#{#staticLabels}` không có dấu hai chấm bên trong expression. Dấu `:` trước expression là ký hiệu label trong Cypher. Đây cũng là expression sinh cấu trúc query, không phải tham số dữ liệu.

`staticLabels` giúp query bám theo metadata của entity. Khi label tĩnh được đổi trong annotation, query dùng expression này sẽ lấy metadata mới mà không phải sửa chuỗi label lặp lại trong từng phương thức.

## 5. `orderBy(...)`: dùng Sort và Pageable trong custom query

SDN có extension `orderBy(...)` để chuyển đối tượng Spring Data `Sort` hoặc `Pageable` thành phần `ORDER BY` trong Cypher. Trong SpEL context, các đối tượng này có tên cố định:

- `#sort` là tham số `Sort`.
- `#pageable` là tham số `Pageable`.

Ví dụ sắp xếp động theo `Sort`:

```java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

@Query("""
    MATCH (p:Person)
    WHERE p.city = $city
    RETURN p
    :#{orderBy(#sort)}
    """)
List<Person> findByCity(
    @Param("city") String city,
    Sort sort
);
}
```

Gọi repository:

```java
List<Person> people = repository.findByCity(
    "Da Nang",
    Sort.by(Sort.Order.asc("name"), Sort.Order.desc("createdAt"))
);
```

SDN tạo phần `ORDER BY` theo các thuộc tính và hướng sắp xếp trong `Sort`.

Với phân trang trả về `Slice`, có thể dùng `Pageable`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

@Query("""
    MATCH (p:Person)
    WHERE p.city = $city
    RETURN p
    :#{orderBy(#pageable)}
    SKIP $skip LIMIT $limit
    """)
Slice<Person> findSliceByCity(
    @Param("city") String city,
    Pageable pageable
);
}
```

`Pageable` luôn được SDN đưa vào SpEL context với tên `pageable`; `Sort` dùng tên `sort`. Khi query tùy chỉnh dùng `Pageable`, câu Cypher phải có phần sắp xếp và giới hạn phù hợp. Với `Slice`, ví dụ trên dùng `SKIP $skip LIMIT $limit` để áp dụng vị trí và kích thước trang.

Không ghép chuỗi `ORDER BY` từ tham số người dùng. Dùng `Sort`/`Pageable`, đồng thời chỉ cho phép sắp xếp theo những property hợp lệ trong API của ứng dụng. Kiểm tra cách SDN ánh xạ property trong `Sort` ở đúng phiên bản dự án.

## 6. Property placeholders `${...}` trong custom query

Ngoài SpEL, Spring có thể thay thế property placeholder từ `Environment` trong chuỗi `@Query`. Ví dụ, ứng dụng có cấu hình:

```properties
app.neo4j.person-status=ACTIVE
```

Có thể đặt placeholder trong query:

```java
@Query("""
    MATCH (p:Person)
    WHERE p.status = '${app.neo4j.person-status:ACTIVE}'
    RETURN p
    """)
List<Person> findConfiguredActivePeople();
```

`${app.neo4j.person-status:ACTIVE}` được thay bằng giá trị cấu hình; `ACTIVE` là giá trị mặc định nếu property chưa được đặt. Đây là thay thế chuỗi query từ cấu hình Spring, không phải parameter binding của Cypher. Chỉ dùng cho cấu hình đáng tin cậy, ổn định theo môi trường. Với dữ liệu thay đổi theo từng lần gọi, tiếp tục dùng `$status` hoặc `:#{...}`.

## 7. Chọn đúng expression cho từng nhu cầu

| Nhu cầu | Cách dùng | Ví dụ |
| --- | --- | --- |
| Truyền giá trị dữ liệu | Tham số Cypher | `$name` |
| Tính giá trị tham số từ đối số method | SpEL parameter expression | `:#{#name.trim()}` |
| Chọn label hoặc relationship type động | Literal extension | `` `:#{literal(#label)}` `` |
| Node phải có tất cả label trong danh sách | List extension `allOf` | `` `:#{allOf(#labels)}` `` |
| Node có ít nhất một label trong danh sách | List extension `anyOf` | `` `:#{anyOf(#labels)}` `` |
| Dùng label tĩnh của entity | Static labels expression | `:#{#staticLabels}` |
| Sắp xếp từ `Sort` | `orderBy(#sort)` | `:#{orderBy(#sort)}` |
| Sắp xếp và phân trang từ `Pageable` | `orderBy(#pageable)` | `:#{orderBy(#pageable)}` |
| Thay giá trị cấu hình vào query | Property placeholder | `${app.neo4j.person-status}` |

Một cách nhớ hữu ích: **tham số Cypher mang dữ liệu; SpEL tính giá trị hoặc gọi extension; literal và label expressions sinh thành phần cấu trúc; property placeholder lấy giá trị cấu hình từ Spring Environment.**

## 8. Các lưu ý bảo mật và hiệu năng

**Không đánh giá SpEL do người dùng cung cấp.** Biểu thức SpEL có thể truy cập property, method và các thành phần trong evaluation context. Chỉ dùng expression được khai báo tĩnh trong annotation hoặc cấu hình do đội phát triển kiểm soát. Không nhận nguyên chuỗi `#{...}` từ request rồi đưa vào bộ đánh giá.

**Ưu tiên bind parameter cho dữ liệu.** Dùng `$name`, `$id`, `$status` hoặc `:#{...}` khi cần tính giá trị. Tránh nối dữ liệu người dùng vào chuỗi Cypher.

**Giới hạn literal và list extensions bằng allow-list.** `literal`, `allOf` và `anyOf` thay đổi cấu trúc label/type trong query. Nếu cần quote identifier, hãy đặt dấu backtick tường minh trong query template; SDN không tự thêm chúng. Ứng dụng vẫn cần xác thực giá trị theo danh sách label hoặc relationship type được phép.

**Dùng static labels khi query gắn với entity.** `#{#staticLabels}` giảm lỗi lặp label và giữ query đồng bộ với metadata của domain type. Không dùng nó nếu query đang nhắm đến một schema khác với entity hiện tại.

**Không lạm dụng expression.** Expression được đánh giá trong quá trình xử lý query và làm tăng độ phức tạp cũng như chi phí so với tham số thông thường. Nếu chỉ cần truyền một giá trị, `$parameter` dễ đọc hơn. Nếu query có nhiều nhánh động hoặc logic cấu trúc lớn, hãy cân nhắc custom repository fragment hoặc Cypher-DSL thay vì tạo một annotation khó bảo trì.

**Kiểm thử query sau khi expression được thay thế.** Kiểm tra label expression, relationship type, `ORDER BY`, `SKIP` và `LIMIT` được tạo đúng; kiểm thử cả đầu vào rỗng, label không hợp lệ và property cấu hình bị thiếu.

## 9. Phạm vi phiên bản

Các extension được mô tả trong tài liệu SDN có thể khác nhau giữa các dòng phiên bản. Tài liệu SDN 6.2.2 đã mô tả SpEL `:#{...}`, `literal`, `orderBy` và `#{#staticLabels}`. Tài liệu stable SDN 8.2.0 hiện hành cũng mô tả list extensions `allOf` và `anyOf`.

Vì vậy, trước khi dùng một extension trong dự án, hãy kiểm tra tài liệu đúng version của `spring-data-neo4j` đang được resolve, đặc biệt nếu dự án dùng SDN 6.x hoặc 7.x. Không suy ra extension mới có mặt ở mọi phiên bản chỉ vì cú pháp SpEL cơ bản đã được hỗ trợ.

## Kết luận

SpEL trong `@Query` giúp SDN xử lý các truy vấn Cypher linh hoạt hơn: `:#{...}` tính giá trị tham số; `literal(...)` chèn thành phần cấu trúc như label; `allOf(...)` và `anyOf(...)` tạo label expression từ danh sách; `#{#staticLabels}` lấy label tĩnh của entity; `orderBy(...)` tích hợp `Sort` và `Pageable`; còn `${...}` thay thế giá trị cấu hình từ Spring Environment. Hãy chọn extension theo đúng vị trí sử dụng, ưu tiên bind parameter cho dữ liệu, giới hạn thành phần cấu trúc bằng allow-list và kiểm tra tài liệu của đúng phiên bản SDN.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2.0 — Custom queries, SpEL và extensions](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j 6.2.2 — Spring Expression Language in custom queries](https://docs.spring.io/spring-data/neo4j/docs/6.2.2/reference/html/)
- [Spring Data Commons — Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html)
