# Bind tham số bằng $name, @Param và tên tham số Java

Khi khai báo Cypher tùy chỉnh trong Spring Data Neo4j (SDN), truy vấn thường cần nhận dữ liệu từ method repository hoặc từ service. Thay vì ghép giá trị đầu vào trực tiếp vào chuỗi Cypher, hãy dùng tham số có tên theo cú pháp `$name`. Spring Data liên kết tham số đó với đối số Java thông qua `@Param` hoặc tên tham số Java được giữ lại khi biên dịch.

Bind tham số giúp một câu truy vấn được tái sử dụng với nhiều giá trị, làm rõ ranh giới giữa cấu trúc truy vấn và dữ liệu đầu vào, đồng thời tránh lỗi cú pháp và nguy cơ Cypher injection do nối chuỗi không an toàn.

## 1. Cú pháp tham số trong Cypher

Trong Cypher, tham số có tên được viết với dấu `$` đứng trước tên. Ví dụ, `$email`, `$minimumAge` và `$status` là các tham số:

```cypher
MATCH (p:Person)
WHERE p.email = $email
  AND p.age >= $minimumAge
  AND p.status = $status
RETURN p;
```

Các giá trị được truyền khi thực thi truy vấn. Cypher phân tích cấu trúc truy vấn riêng với giá trị tham số, vì vậy cùng một câu lệnh có thể chạy với nhiều email, độ tuổi hoặc trạng thái khác nhau.

Tên tham số trong Cypher phải tương ứng với tên được bind từ Java. Ví dụ, truy vấn có `$email` thì phía repository phải cung cấp tham số tên `email`.

## 2. Dùng `@Param` để liên kết tên Java với `$name`

Với repository method có `@Query`, cách rõ ràng và ổn định là gắn `@Param("...")` cho từng tham số. Annotation `@Param` được import từ `org.springframework.data.repository.query.Param`.

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {email: $email})
        RETURN p
        """)
    Optional<Person> findByEmail(@Param("email") String email);
}
```

Trong ví dụ:

- `$email` là placeholder trong câu Cypher.
- `@Param("email")` khai báo tên tham số mà Spring Data dùng để bind.
- `email` sau `String` là tên biến Java trong method.

Tên trong `@Param` phải khớp với placeholder `$email`. Tên biến Java có thể khác nếu annotation chỉ rõ tên bind:

```java
@Query("MATCH (p:Person {email: $email}) RETURN p")
Optional<Person> findPerson(@Param("email") String address);
```

Ở đây biến Java tên `address`, nhưng Spring Data bind giá trị của nó vào tham số Cypher tên `email`. Đây là cách hữu ích khi tên tham số trong API Java khác tên được dùng trong câu truy vấn.

## 3. Dùng tên tham số Java mà không cần `@Param`

Spring Data có thể suy ra tên tham số từ chữ ký method nếu mã Java được biên dịch với tùy chọn `-parameters`. Khi đó, method sau có thể bind `email` vào `$email` mà không cần annotation:

```java
@Query("""
    MATCH (p:Person {email: $email})
    RETURN p
    """)
Optional<Person> findByEmail(String email);
```

Để giữ tên tham số trong bytecode, có thể bật `-parameters` trong Gradle với Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
```

Nếu không bật tùy chọn này, tên tham số có thể không còn khả dụng ở runtime để Spring Data suy ra. Khi đó, việc bind theo tên có thể thất bại lúc khởi tạo hoặc thực thi truy vấn. Với code cần hoạt động ổn định giữa các cấu hình build, khai báo `@Param` tường minh là lựa chọn dễ kiểm tra hơn.

Không nên dựa vào tên biến cục bộ hoặc tên tham số hiển thị trong IDE; điều quan trọng là tên tham số mà Spring Data thực sự có thể đọc từ bytecode hoặc annotation.

## 4. Bind nhiều tham số trong cùng một truy vấn

Một method có thể nhận nhiều đối số. Mỗi placeholder có tên riêng và được liên kết bằng `@Param` tương ứng:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    @Query("""
        MATCH (p:Product)-[:IN_CATEGORY]->(c:Category {code: $categoryCode})
        WHERE p.priceMinor <= $maxPriceMinor
          AND p.status = $status
        RETURN p
        ORDER BY p.priceMinor
        """)
    List<Product> findProducts(
            @Param("categoryCode") String categoryCode,
            @Param("maxPriceMinor") long maxPriceMinor,
            @Param("status") String status);
}
```

Ánh xạ tham số trong ví dụ:

| Placeholder Cypher | Tham số Java | Giá trị mẫu |
|---|---|---|
| `$categoryCode` | `categoryCode` | `HARDWARE` |
| `$maxPriceMinor` | `maxPriceMinor` | `2500000` |
| `$status` | `status` | `ACTIVE` |

Các điều kiện có thể dùng lại cùng một tham số nhiều lần. Không cần tạo thêm đối số Java nếu cùng một giá trị được sử dụng ở nhiều vị trí trong truy vấn.

## 5. Bind danh sách và map

Tham số Cypher không chỉ nhận giá trị scalar. Có thể truyền collection để dùng với `IN`, hoặc truyền map để thao tác với nhiều property.

### Truyền danh sách

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    @Query("""
        MATCH (p:Product)
        WHERE p.sku IN $skus
        RETURN p
        """)
    List<Product> findAllBySkus(@Param("skus") List<String> skus);
}
```

`$skus` nhận một danh sách giá trị. Cypher kiểm tra `p.sku` có thuộc danh sách hay không. Nếu danh sách rỗng, truy vấn không tìm được sản phẩm nào; hãy xác định trước cách API muốn xử lý trường hợp đầu vào rỗng.

### Truyền map

Cypher có thể nhận map để cập nhật tập property:

```cypher
MATCH (p:Product {sku: $sku})
SET p += $changes
RETURN p;
```

Ở đây `$changes` là map các cặp key-value. `SET p += $changes` thêm hoặc cập nhật những property được truyền; các property khác của node được giữ lại. Nếu map chứa key có giá trị `null`, Cypher có thể loại bỏ property tương ứng. Vì vậy, hãy xác thực nội dung map và chỉ cho phép những key nghiệp vụ được cập nhật. Không chuyển nguyên một map tùy ý từ request bên ngoài vào node mà không kiểm soát.

## 6. Tham số hóa giúp tránh Cypher injection

Không ghép trực tiếp dữ liệu người dùng vào chuỗi Cypher. Ví dụ sau không an toàn:

```java
String query = "MATCH (p:Person) WHERE p.email = '" + email + "' RETURN p";
```

Nếu `email` chứa dấu nháy hoặc đoạn cú pháp Cypher, chuỗi truy vấn có thể bị thay đổi ngoài ý định. Cách đúng là giữ nguyên cấu trúc truy vấn và bind giá trị:

```java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (p:Person {email: $email})
        RETURN p
        """)
    Optional<Person> findByEmail(@Param("email") String email);
}
```

Driver gửi giá trị tham số riêng với câu lệnh Cypher. Giá trị đầu vào vì vậy không thể biến thành một phần cú pháp của truy vấn.

Tham số hóa cũng giúp Neo4j tái sử dụng kế hoạch truy vấn khi cấu trúc truy vấn giữ nguyên và chỉ thay đổi giá trị. Hiệu quả thực tế còn phụ thuộc query plan cache, schema, index và phiên bản máy chủ.

## 7. Tham số dùng cho giá trị, không thay thế tùy ý cấu trúc Cypher

Placeholder `$name` được dùng cho dữ liệu như chuỗi, số, boolean, ngày giờ, point, list hoặc map. Nó không phải cách thay thế tùy ý cho tên label, relationship type, property key hoặc từ khóa Cypher.

Ví dụ, không thể coi truy vấn sau là cách bind động label:

```cypher
MATCH (n:$label)
RETURN n;
```

Nếu cần lựa chọn giữa các label hoặc relationship type, hãy thiết kế các nhánh truy vấn cố định, hoặc dùng cú pháp dynamic token được phiên bản Neo4j của dự án hỗ trợ. Nếu phải xây dựng một phần cấu trúc truy vấn động trong ứng dụng, chỉ chọn từ danh sách identifier được whitelist trong code; không đưa nguyên văn identifier do người dùng gửi vào chuỗi truy vấn.

Tương tự, `$propertyName` không tự thay thế tên property ở mọi vị trí cú pháp. Hãy kiểm tra khả năng dynamic property access của phiên bản Neo4j đang dùng nếu nghiệp vụ thực sự cần truy cập property động.

## 8. Bind tham số với `Neo4jClient`

Ngoài repository `@Query`, SDN cung cấp `Neo4jClient` để thực hiện Cypher linh hoạt hơn. Có thể dùng `.bind(value).to("name")` để bind giá trị vào placeholder `$name`:

```java
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class PersonLookup {

    private final Neo4jClient neo4jClient;

    public PersonLookup(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<Long> countByEmail(String email) {
        return neo4jClient.query("""
                MATCH (p:Person {email: $email})
                RETURN count(p) AS total
                """)
                .bind(email).to("email")
                .fetchAs(Long.class)
                .mappedBy((typeSystem, record) -> record.get("total").asLong())
                .one();
    }
}
```

`.bind(email).to("email")` liên kết giá trị Java với placeholder `$email`. Tên trong `to(...)` không có dấu `$`; dấu `$` chỉ xuất hiện trong câu Cypher. `mappedBy(...)` chuyển cột `total` trong record thành kiểu Java `Long`.

Khi bind nhiều giá trị, gọi `.bind(value).to("parameterName")` cho từng tham số. Cách này giữ nguyên nguyên tắc: dữ liệu được truyền riêng, câu lệnh Cypher không cần ghép chuỗi.

## 9. Quy tắc đặt tên và kiểm tra lỗi bind

Để code dễ đọc và ít lỗi, hãy thống nhất quy tắc đặt tên:

1. Dùng tên thể hiện ý nghĩa, ví dụ `$customerId`, `$fromDate`, `$maxPriceMinor`.
2. Với repository method, đặt `@Param` trùng chính xác với placeholder trong Cypher.
3. Khai báo `@Param` cho tất cả tham số của custom query nếu muốn tránh phụ thuộc vào compiler option.
4. Không dùng một tên cho hai giá trị khác ý nghĩa trong cùng truy vấn.
5. Kiểm tra kiểu Java tương thích với kiểu dữ liệu mà Cypher mong đợi.
6. Xử lý rõ `null`, collection rỗng và trường hợp không có kết quả theo quy tắc nghiệp vụ.

Ví dụ lỗi tên tham số:

```java
@Query("MATCH (p:Person {email: $email}) RETURN p")
Optional<Person> findByEmail(@Param("mail") String email);
```

Placeholder là `$email`, nhưng annotation khai báo tên bind là `mail`. Spring Data không thể tự suy ra rằng hai tên này có cùng ý nghĩa. Sửa thành:

```java
Optional<Person> findByEmail(@Param("email") String email);
```

Khi gặp lỗi parameter không được bind, hãy kiểm tra ba vị trí: tên placeholder `$...` trong Cypher, giá trị `@Param("...")` và tên Java nếu đang dựa vào parameter name discovery. Với `Neo4jClient`, kiểm tra tên trong `.to("...")` có khớp placeholder hay không.

## 10. Bài tập thực hành

Tạo repository tìm sản phẩm theo danh mục, trạng thái và giới hạn giá:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    @Query("""
        MATCH (p:Product)-[:IN_CATEGORY]->(c:Category {code: $categoryCode})
        WHERE p.status = $status
          AND p.priceMinor <= $maxPriceMinor
        RETURN p
        ORDER BY p.priceMinor
        """)
    List<Product> search(
            @Param("categoryCode") String categoryCode,
            @Param("status") String status,
            @Param("maxPriceMinor") long maxPriceMinor);
}
```

Thực hiện các yêu cầu:

1. Gọi method với `categoryCode = "HARDWARE"`, `status = "ACTIVE"` và một giới hạn giá cụ thể.
2. Đổi tên biến Java `categoryCode` thành `category` nhưng giữ `@Param("categoryCode")`; xác nhận truy vấn vẫn bind theo tên annotation.
3. Bỏ `@Param` và bật `-parameters`; kiểm tra Spring Data đọc đúng tên tham số Java.
4. Tắt `-parameters` trong môi trường thử nghiệm và quan sát khác biệt khi không khai báo `@Param`.
5. Viết method nhận `List<String> skus` và dùng `p.sku IN $skus`.
6. Thử đầu vào có dấu nháy để xác nhận tham số hóa giữ nguyên giá trị dữ liệu, không làm thay đổi cú pháp Cypher.
7. Dùng `Neo4jClient` với `.bind(value).to("name")` để chạy truy vấn đếm kết quả theo email.

Sau bài tập, hãy giải thích được cách `$name` liên kết với `@Param`, khi nào có thể dựa vào tên tham số Java, vì sao `-parameters` quan trọng và vì sao không nên nối chuỗi đầu vào vào Cypher.

## Kết luận

Trong custom Cypher của Spring Data Neo4j, `$name` là placeholder cho giá trị dữ liệu. `@Param("name")` liên kết rõ ràng đối số Java với placeholder; nếu không dùng annotation, Spring Data cần tên tham số Java được giữ lại trong bytecode, thường bằng tùy chọn biên dịch `-parameters`. Với `Neo4jClient`, dùng `.bind(value).to("name")`. Hãy tham số hóa mọi giá trị đầu vào, giữ tên bind nhất quán và chỉ xây dựng cấu trúc truy vấn động từ identifier được kiểm soát. Cách làm này giúp truy vấn an toàn, dễ đọc và dễ bảo trì.
