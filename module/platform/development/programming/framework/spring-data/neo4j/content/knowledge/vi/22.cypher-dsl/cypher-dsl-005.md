# Tích hợp CypherdslConditionExecutor vào repository

Khi một màn hình tìm kiếm có nhiều bộ lọc tùy chọn, việc khai báo một derived query cho từng tổ hợp điều kiện sẽ nhanh chóng trở nên khó bảo trì. `@Query` giải quyết được truy vấn tùy chỉnh, nhưng nếu chỉ cần thay đổi phần điều kiện `WHERE` trong truy vấn mà Spring Data Neo4j đã biết cách sinh, ta có thể dùng **`CypherdslConditionExecutor`**.

Đây là một repository extension của Spring Data Neo4j. Repository chỉ cần kế thừa thêm interface này để nhận các đối tượng `Condition` được tạo bằng Cypher-DSL. SDN tiếp tục tạo truy vấn và ánh xạ entity theo domain model; điều kiện do ứng dụng cung cấp được bổ sung vào truy vấn đó.

## 1. CypherdslConditionExecutor giải quyết vấn đề gì?

`CypherdslConditionExecutor<T>` là một interface trong package:

```java
org.springframework.data.neo4j.repository.support.CypherdslConditionExecutor
```

Nó có thể được thêm vào repository để thực hiện các truy vấn domain với điều kiện động. API này có từ Spring Data Neo4j 6.1 và được đánh dấu ổn định trong tài liệu API.

Thay vì tự viết toàn bộ câu Cypher, ứng dụng xây dựng một `Condition` bằng Cypher-DSL. SDN dùng condition đó để bổ sung phần lọc vào truy vấn được tạo từ entity metadata. Vì vậy, kết quả vẫn được ánh xạ về kiểu domain `T` của repository.

Ví dụ, một form tìm kiếm người dùng có thể chỉ gửi tên hoặc trạng thái. Ở request này chỉ lọc theo tên; request khác có thể lọc theo tên và trạng thái. Service xây dựng condition tương ứng rồi gọi cùng một repository method.

## 2. Thêm CypherdslConditionExecutor vào repository

Giả sử có entity `Person`:

```java
@Node("Person")
public class Person {

    @Id
    private String personId;

    private String firstName;
    private String lastName;
    private String status;
}
```

Repository kế thừa cả `Neo4jRepository` và `CypherdslConditionExecutor`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.support.CypherdslConditionExecutor;

public interface PersonRepository
        extends Neo4jRepository<Person, String>,
                CypherdslConditionExecutor<Person> {
}
```

Tham số generic `Person` phải là kiểu domain mà repository quản lý. Sau khi thêm interface, Spring Data Neo4j cung cấp implementation cho extension thông qua repository infrastructure; không cần tự viết lớp triển khai `CypherdslConditionExecutor`.

## 3. Tạo Node và Property bằng Cypher-DSL

Cypher-DSL biểu diễn các thành phần của truy vấn bằng object Java. Để tạo condition cho `Person`, trước hết khai báo node và các property cần lọc:

```java
import org.neo4j.cypherdsl.core.Cypher;
import org.neo4j.cypherdsl.core.Node;
import org.neo4j.cypherdsl.core.Property;

Node person = Cypher.node("Person").named("person");

Property firstName = person.property("firstName");
Property lastName = person.property("lastName");
Property status = person.property("status");
```

`Cypher.node("Person")` tạo node có label `Person`; `named("person")` đặt symbolic name cho node trong biểu thức DSL. Các lời gọi `property(...)` tạo tham chiếu đến property trên node đó.

Tên symbolic name phải tương ứng với biến root mà SDN dùng trong truy vấn được sinh. Ví dụ domain type `Person` thường được tham chiếu bằng biến `person` trong condition. Khi dùng condition trên entity hoặc relationship liên quan, cần dùng đúng symbolic name mà truy vấn sinh ra; không nên tự đặt tên tùy ý rồi giả định SDN sẽ tự nối các biến đó vào query.

## 4. Tạo Condition và thực thi findAll

Cypher-DSL cho phép tạo các biểu thức so sánh và kết hợp chúng bằng `and`, `or`, `not` cùng các toán tử phù hợp.

Ví dụ tìm người có tên `An` hoặc họ `Nguyen`:

```java
import java.util.Collection;

import org.neo4j.cypherdsl.core.Condition;
import org.neo4j.cypherdsl.core.Cypher;

Condition condition = firstName.eq(Cypher.parameter("firstName", "An"))
    .or(lastName.eq(Cypher.parameter("lastName", "Nguyen")));

Collection<Person> people = personRepository.findAll(condition);
```

Trong ví dụ:

- `firstName.eq(...)` tạo điều kiện bằng trên property `firstName`.
- `lastName.eq(...)` tạo điều kiện bằng trên property `lastName`.
- `or(...)` kết hợp hai điều kiện thành một biểu thức OR.
- `Cypher.parameter(name, value)` tạo tham số có tên và gắn giá trị cần truyền.
- `findAll(condition)` yêu cầu SDN sinh truy vấn domain, bổ sung condition và ánh xạ kết quả thành `Person`.

Condition tương ứng về mặt logic với:

```cypher
MATCH (person:Person)
WHERE person.firstName = $firstName
   OR person.lastName = $lastName
RETURN person
```

Đây là cách minh họa ý nghĩa của condition; câu truy vấn thực tế được Spring Data Neo4j sinh dựa trên metadata entity và có thể chứa thêm phần ánh xạ quan hệ.

## 5. Dùng tham số thay cho nối chuỗi

Giá trị tìm kiếm thường đến từ request của người dùng. Hãy truyền chúng qua parameter của Cypher-DSL:

```java
Condition condition = firstName.eq(
    Cypher.parameter("firstName", searchRequest.firstName())
).and(status.eq(
    Cypher.parameter("status", searchRequest.status())
));

Collection<Person> people = personRepository.findAll(condition);
```

Các giá trị được gắn với placeholder có tên. Không ghép chuỗi đầu vào vào một đoạn Cypher rồi cố biến đoạn đó thành condition. Parameter giúp dữ liệu được xử lý như giá trị, giữ cấu trúc truy vấn ổn định và tránh để input trở thành cú pháp truy vấn.

Cypher-DSL cũng cung cấp `Cypher.anonParameter(value)` khi không cần đặt tên tham số tường minh:

```java
Condition condition = firstName.eq(Cypher.anonParameter("An"));
```

Tham số ẩn danh phù hợp với biểu thức ngắn. Với condition được tạo từ nhiều bộ lọc hoặc cần dễ theo dõi khi debug, tham số có tên thường rõ ràng hơn.

Không dùng `Cypher.literalOf(...)` cho dữ liệu request thông thường chỉ để tránh khai báo parameter. Literal là giá trị được đưa trực tiếp vào biểu thức được render; parameter là lựa chọn phù hợp hơn cho dữ liệu đầu vào.

## 6. Kết hợp điều kiện động trong service

Một lợi ích chính của extension là service có thể tạo condition theo những trường người dùng thực sự nhập. Ví dụ:

```java
public Collection<Person> search(PersonSearchRequest request) {
    Node person = Cypher.node("Person").named("person");
    Property firstName = person.property("firstName");
    Property status = person.property("status");

    Condition condition = firstName.eq(
        Cypher.parameter("firstName", request.firstName())
    );

    if (request.status() != null && !request.status().isBlank()) {
        condition = condition.and(
            status.eq(Cypher.parameter("status", request.status()))
        );
    }

    return personRepository.findAll(condition);
}
```

Trong ví dụ, `firstName` là bộ lọc bắt buộc; `status` chỉ được thêm nếu request có giá trị. Nếu mọi trường đều tùy chọn, hãy xử lý riêng trường hợp không có điều kiện nào: gọi `findAll()` của repository hoặc trả về kết quả rỗng theo quy tắc API, thay vì tạo một `Condition` giả.

Nên validate request trước khi tạo condition: trim chuỗi, giới hạn độ dài, kiểm tra mã trạng thái và giới hạn kích thước trang. Các tên label, relationship type và property trong Cypher-DSL nên được định nghĩa trong mã ứng dụng, không lấy trực tiếp từ chuỗi tùy ý của người dùng.

## 7. Sắp xếp kết quả

`CypherdslConditionExecutor` có overload nhận `SortItem` của Cypher-DSL hoặc `Sort` của Spring Data.

Sắp xếp bằng `SortItem`:

```java
Collection<Person> people = personRepository.findAll(
    condition,
    lastName.ascending()
);
```

Có thể kết hợp nhiều tiêu chí:

```java
Collection<Person> people = personRepository.findAll(
    condition,
    lastName.ascending(),
    firstName.ascending()
);
```

Hoặc sử dụng `Sort` của Spring Data:

```java
Collection<Person> people = personRepository.findAll(
    condition,
    Sort.by("lastName").ascending()
        .and(Sort.by("firstName").ascending())
);
```

Hai cách sắp xếp là các overload khác nhau. Chọn một cách phù hợp với phần còn lại của ứng dụng và bảo đảm property dùng để sort tồn tại trong entity mapping.

## 8. Phân trang, đếm và kiểm tra tồn tại

Ngoài `findAll(condition)`, extension cung cấp các thao tác đọc thường gặp:

```java
Page<Person> page = personRepository.findAll(
    condition,
    PageRequest.of(0, 20, Sort.by("lastName").ascending())
);

long total = personRepository.count(condition);

boolean hasMatch = personRepository.exists(condition);
```

`Pageable` cho phép chỉ định số trang, kích thước trang và sort. `count` đếm số entity phù hợp với condition; `exists` kiểm tra có kết quả nào phù hợp hay không.

Khi chỉ cần một entity:

```java
Optional<Person> person = personRepository.findOne(condition);
```

Chỉ dùng `findOne` nếu điều kiện được kỳ vọng khớp tối đa một entity. Nếu nhiều entity thỏa condition, phương thức sẽ báo lỗi kết quả không duy nhất. Khi kết quả có thể có nhiều phần tử, dùng `findAll`, hoặc dùng `findAll` với `Pageable` nếu cần phân trang.

Các phương thức chính của API imperative gồm:

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| `findAll(condition)` | `Collection<T>` | Lấy tất cả entity phù hợp |
| `findAll(condition, sort)` | `Collection<T>` | Lấy entity và sắp xếp |
| `findAll(condition, pageable)` | `Page<T>` | Lấy một trang kết quả |
| `findOne(condition)` | `Optional<T>` | Lấy tối đa một entity |
| `count(condition)` | `long` | Đếm kết quả |
| `exists(condition)` | `boolean` | Kiểm tra có kết quả |

## 9. Dùng condition trên quan hệ đã ánh xạ

Cypher-DSL có thể tạo condition từ property của node hoặc relationship. Tuy nhiên, `CypherdslConditionExecutor` bổ sung condition vào truy vấn domain do SDN sinh; nó không tự tạo một traversal tùy ý giống như khi viết toàn bộ `MATCH` bằng Cypher.

Nếu muốn lọc theo property của node liên quan hoặc relationship đã ánh xạ, cần tham chiếu đúng symbolic name của node/relationship trong query do SDN tạo. Các tên này phụ thuộc cấu trúc entity và cách SDN sinh truy vấn. Hãy kiểm tra query được render/log trong phiên bản đang dùng trước khi xây dựng condition phụ thuộc vào các biến liên quan.

Ví dụ về mặt ý tưởng, một điều kiện trên node liên quan có dạng:

```java
Node department = Cypher.node("Department").named("department");
Property departmentCode = department.property("departmentCode");

Condition departmentCondition = departmentCode.eq(
    Cypher.parameter("departmentCode", "ENG")
);
```

Condition này chỉ hoạt động khi symbolic name `department` tồn tại trong truy vấn được SDN sinh cho domain model tương ứng. Không thể chỉ khai báo một node DSL mới rồi kỳ vọng executor tự thêm relationship đến node đó.

Nếu yêu cầu truy vấn cần tự xác định nhiều `MATCH`, lọc relationship tùy ý, `OPTIONAL MATCH`, aggregation hoặc trả về projection không theo entity, hãy dùng `@Query`, `Neo4jClient` hoặc `CypherdslStatementExecutor` thay vì cố nhồi toàn bộ logic vào `Condition`.

## 10. Phân biệt ConditionExecutor và StatementExecutor

Hai extension đều sử dụng Cypher-DSL nhưng có mức kiểm soát khác nhau:

| Tiêu chí | `CypherdslConditionExecutor` | `CypherdslStatementExecutor` |
|---|---|---|
| Đầu vào | `Condition` | `Statement` hoàn chỉnh từ Cypher-DSL |
| Phần truy vấn do SDN tạo | Có | Ứng dụng tự xây dựng statement |
| Mục tiêu | Bổ sung điều kiện vào truy vấn domain | Kiểm soát đầy đủ cấu trúc truy vấn |
| Kết quả | Domain type `T` của repository | Có thể làm việc với domain type hoặc projection |
| Phù hợp | Bộ lọc động trên truy vấn entity đã ánh xạ | Truy vấn động phức tạp, graph shape hoặc projection riêng |

Nếu chỉ có điều kiện động, `CypherdslConditionExecutor` giữ code ngắn và tận dụng mapping của SDN. Nếu cần tự tạo pattern hoặc thay đổi hình dạng kết quả, `CypherdslStatementExecutor` là lựa chọn phù hợp hơn.

## 11. Reactive repository

Với ứng dụng reactive, Spring Data Neo4j cung cấp `ReactiveCypherdslConditionExecutor<T>` trong package `org.springframework.data.neo4j.repository.support`. Repository reactive có thể kế thừa extension tương ứng để bổ sung condition vào truy vấn được sinh.

Hãy dùng đúng cặp abstraction:

- Imperative: `Neo4jRepository<T, ID>` và `CypherdslConditionExecutor<T>`.
- Reactive: `ReactiveNeo4jRepository<T, ID>` và `ReactiveCypherdslConditionExecutor<T>`.

Không trộn repository imperative với executor reactive hoặc ngược lại. Trong luồng reactive, giữ publisher xuyên suốt service/controller và tránh gọi blocking repository bên trong reactive pipeline.

## 12. Kiểm thử condition và kết quả repository

Nên kiểm thử cả biểu thức condition lẫn kết quả được ánh xạ từ database. Một kịch bản đơn giản:

1. Tạo ba node `Person`: An Nguyen, An Tran và Bình Nguyen.
2. Tạo condition `firstName = 'An' OR lastName = 'Nguyen'`.
3. Gọi `findAll(condition)` và xác nhận cả ba node đều xuất hiện đúng một lần.
4. Thêm sort theo `lastName` và xác nhận thứ tự.
5. Gọi `count(condition)` và `exists(condition)` để xác nhận kết quả thống kê.
6. Dùng `Pageable` và kiểm tra nội dung, tổng phần tử và số trang.
7. Dùng `findOne` với condition duy nhất; kiểm tra riêng trường hợp condition khớp nhiều entity.

Ngoài ra, kiểm tra query khi condition dùng tham số có tên, chuỗi đặc biệt và giá trị đầu vào không hợp lệ. Chạy test với Neo4j cô lập để kết quả không phụ thuộc dữ liệu từ lần chạy trước.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không gọi được `findAll(Condition)` | Repository chưa kế thừa `CypherdslConditionExecutor<T>` hoặc import sai package | Thêm đúng interface từ `org.springframework.data.neo4j.repository.support`. |
| Condition không lọc đúng property | Property name hoặc symbolic name không khớp entity/query được sinh | Kiểm tra tên property Java và symbolic name của node root. |
| Condition tham chiếu node liên quan nhưng query không có biến đó | Tự đặt symbolic name không thuộc generated query | Dùng biến thực tế từ query SDN sinh hoặc chuyển sang statement/query tùy chỉnh. |
| Tham số bị nhầm thành literal | Nối chuỗi đầu vào hoặc render literal không phù hợp | Dùng `Cypher.parameter(...)` hoặc `Cypher.anonParameter(...)`. |
| `findOne` báo nhiều kết quả | Condition không đủ tính duy nhất | Dùng `findAll`, thêm điều kiện hoặc chọn `Pageable`. |
| Không phân trang/sort được | Dùng sai overload hoặc property sort không hợp lệ | Dùng `Pageable`, `Sort` hoặc `SortItem` đúng kiểu. |
| Muốn tạo traversal mới nhưng chỉ có Condition | Nhầm ConditionExecutor với StatementExecutor | Dùng `CypherdslStatementExecutor`, `@Query` hoặc `Neo4jClient`. |

## 14. Quy trình áp dụng

1. Xác định repository đang quản lý entity nào và các property cần lọc.
2. Kế thừa `CypherdslConditionExecutor<T>` cùng `Neo4jRepository<T, ID>`.
3. Tạo node DSL có label và symbolic name tương ứng với root node của truy vấn SDN sinh.
4. Lấy các `Property` từ node rồi xây dựng `Condition` bằng toán tử phù hợp.
5. Truyền dữ liệu đầu vào qua named hoặc anonymous parameter.
6. Gọi `findAll`, `findOne`, `count`, `exists` hoặc overload có sort/pageable.
7. Kiểm thử các nhánh AND/OR, tham số, kết quả trùng và trường hợp không có dữ liệu.
8. Chuyển sang `CypherdslStatementExecutor` hoặc custom Cypher nếu cần toàn quyền điều khiển graph pattern và kết quả.

## 15. Ghi nhớ

`CypherdslConditionExecutor<T>` là extension cho repository Spring Data Neo4j, cho phép truyền `Condition` của Cypher-DSL vào các truy vấn domain do SDN tạo. Chỉ cần thêm interface này vào repository là có thể dùng `findAll`, `findOne`, `count`, `exists`, sort và pagination với điều kiện động.

Hãy tạo node/property DSL với symbolic name khớp truy vấn được sinh, dùng parameter cho giá trị đầu vào và giữ condition trong phạm vi mà generated query hỗ trợ. Extension này phù hợp khi phần thay đổi chủ yếu là `WHERE`; nếu cần tự xây dựng `MATCH`, traversal, aggregation hoặc projection riêng, hãy chuyển sang `CypherdslStatementExecutor`, `@Query` hoặc `Neo4jClient`.

## Tài liệu tham khảo

- [Spring Data Neo4j – CypherdslConditionExecutor API](https://docs.spring.io/spring-data/neo4j/docs/8.1.x/api/org/springframework/data/neo4j/repository/support/CypherdslConditionExecutor.html)
- [Spring Data Neo4j – FAQ: Is @Query the only way to use custom queries?](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – Repository support package](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/repository/support/package-summary.html)
