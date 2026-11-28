# Khớp toàn bộ hoặc bất kỳ thuộc tính được chọn

Khi xây dựng màn hình tìm kiếm, người dùng thường chỉ nhập một vài tiêu chí. Có người lọc theo tên và thành phố, có người chỉ nhập email hoặc trạng thái. Nếu viết một phương thức repository riêng cho từng tổ hợp, số lượng phương thức sẽ tăng nhanh và khó bảo trì.

**Query by Example (QBE)** giải quyết bài toán này bằng cách lấy một đối tượng mẫu làm điều kiện tìm kiếm. Ứng dụng điền các thuộc tính cần tìm vào đối tượng đó, tạo một **Example** và giao cho repository thực thi. **ExampleMatcher** quyết định các tiêu chí được kết hợp theo logic AND hay OR, cách so khớp chuỗi, cách xử lý giá trị null và các thuộc tính cần bỏ qua.

Trong Spring Data Neo4j (SDN), **Neo4jRepository** đã tích hợp **QueryByExampleExecutor**. Bạn có thể dùng QBE trực tiếp trên repository để tìm node theo các property của entity mà không cần tự viết Cypher cho những điều kiện đơn giản.

Sau bài học, bạn có thể:

- Tạo **Probe**, **ExampleMatcher** và **Example** để tìm kiếm động.
- Phân biệt **matching()** (khớp tất cả) và **matchingAny()** (khớp bất kỳ).
- Chọn thuộc tính tham gia điều kiện bằng giá trị probe, **withIgnorePaths** và cách xử lý null.
- Tùy chỉnh so khớp chuỗi và không phân biệt chữ hoa/chữ thường.
- Dùng các phương thức QBE và fluent API để sắp xếp, phân trang, giới hạn hoặc chiếu kết quả.
- Nhận biết khi nào QBE không đủ biểu đạt và nên chuyển sang derived query hoặc Cypher.

## 1. QBE gồm những thành phần nào?

QBE có bốn thành phần:

| Thành phần | Vai trò |
|---|---|
| **Probe** | Đối tượng miền chứa các giá trị muốn dùng làm tiêu chí |
| **ExampleMatcher** | Cấu hình cách kết hợp tiêu chí, so khớp chuỗi, bỏ qua property và xử lý null |
| **Example** | Đóng gói probe cùng matcher thành điều kiện truy vấn |
| **FetchableFluentQuery** | API tùy biến việc thực thi Example, như sắp xếp, phân trang, projection và lấy kết quả |

Ví dụ, nếu probe có tên là **An** và thành phố là **Hồ Chí Minh**, matcher mặc định sẽ yêu cầu cả tên và thành phố cùng khớp. Không cần tạo một phương thức repository có tên chứa hai property đó.

## 2. Chuẩn bị entity và repository

Giả sử ứng dụng quản lý hồ sơ người dùng:

~~~java
package com.acme.graph.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String email;
    private String city;
    private String status;

    public Person() {
    }

    public Person(String name, String email, String city, String status) {
        this.name = name;
        this.email = email;
        this.city = city;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getCity() {
        return city;
    }

    public String getStatus() {
        return status;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Khai báo repository:

~~~java
package com.acme.graph.repository;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import com.acme.graph.domain.Person;

public interface PersonRepository
        extends Neo4jRepository<Person, Long> {
}
~~~

**Neo4jRepository<Person, Long>** đã cung cấp các phương thức QBE như **findAll(Example)**, **findOne(Example)**, **count(Example)**, **exists(Example)** và **findBy(Example, queryFunction)**. Không cần kế thừa thêm **QueryByExampleExecutor<Person>** vì interface đó đã là superinterface của **Neo4jRepository**.

## 3. Tạo Example đơn giản

Đầu tiên, tạo một probe và chỉ điền các thuộc tính muốn tìm:

~~~java
import java.util.List;

import org.springframework.data.domain.Example;

import com.acme.graph.domain.Person;
import com.acme.graph.repository.PersonRepository;

Person probe = new Person();
probe.setName("An");
probe.setCity("Ho Chi Minh City");

Example<Person> example = Example.of(probe);

List<Person> people = personRepository.findAll(example);
~~~

Ví dụ giả định entity có setter tương ứng cho các thuộc tính được điền. Khi chạy truy vấn, QBE chỉ đưa các property có giá trị khác null vào điều kiện theo mặc định. Các thuộc tính **email**, **status** và **id** đang null nên không tham gia điều kiện.

Có thể hình dung điều kiện được tạo như sau:

~~~cypher
MATCH (p:Person)
WHERE p.name = $name
  AND p.city = $city
RETURN p
~~~

Đây là cách diễn giải logic để hiểu QBE; SDN tự tạo truy vấn thực tế dựa trên metadata entity và probe, không yêu cầu bạn viết câu Cypher trên.

**Example** là đối tượng bất biến. Nếu muốn thay đổi điều kiện, hãy tạo probe hoặc Example mới thay vì cố sửa Example đã tạo.

## 4. Khớp tất cả thuộc tính bằng matching()

**ExampleMatcher.matching()** cấu hình chế độ khớp tất cả các tiêu chí được chọn. Đây cũng là chế độ mặc định khi dùng **Example.of(probe)** mà không truyền matcher.

Ví dụ, tìm người có tên là **An**, thành phố là **Hồ Chí Minh** và trạng thái là **ACTIVE**:

~~~java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

import com.acme.graph.domain.Person;

Person probe = new Person();
probe.setName("An");
probe.setCity("Ho Chi Minh City");
probe.setStatus("ACTIVE");

ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "email");

Example<Person> example = Example.of(probe, matcher);

List<Person> results = personRepository.findAll(example);
~~~

Logic tương ứng:

~~~text
name = "An"
AND city = "Ho Chi Minh City"
AND status = "ACTIVE"
~~~

Một node chỉ được trả về khi đáp ứng tất cả các điều kiện đã chọn. **withIgnorePaths** loại property khỏi tiêu chí, kể cả khi probe có giá trị ở property đó. Trong ví dụ, ID và email không tham gia truy vấn.

Dùng matching khi các tiêu chí là những điều kiện bắt buộc cùng đúng, chẳng hạn lọc hồ sơ theo thành phố, trạng thái và loại tài khoản.

## 5. Khớp bất kỳ thuộc tính nào bằng matchingAny()

Nếu yêu cầu tìm kiếm cho phép một trong nhiều tiêu chí khớp, dùng **ExampleMatcher.matchingAny()**.

Ví dụ, người dùng có thể nhập tên hoặc email để tìm hồ sơ:

~~~java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

import com.acme.graph.domain.Person;

Person probe = new Person();
probe.setName("an");
probe.setEmail("an@example.com");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
    .withIgnorePaths("id", "city", "status");

Example<Person> example = Example.of(probe, matcher);

List<Person> results = personRepository.findAll(example);
~~~

Logic tương ứng:

~~~text
name = "an"
OR email = "an@example.com"
~~~

Chỉ cần một trong hai điều kiện đúng là hồ sơ có thể được trả về. Các property null hoặc được chỉ định bỏ qua không tạo thêm điều kiện OR.

### So sánh hai chế độ

Giả sử probe chứa:

- **name = "An"**
- **city = "Da Nang"**
- **status = "ACTIVE"**

| Dữ liệu của node | matching() | matchingAny() |
|---|---|---|
| An, Da Nang, ACTIVE | Khớp | Khớp |
| An, Hà Nội, ACTIVE | Không khớp | Khớp |
| Bình, Da Nang, INACTIVE | Không khớp | Khớp |
| Bình, Hà Nội, ACTIVE | Không khớp | Khớp |
| Bình, Hà Nội, INACTIVE | Không khớp | Không khớp |

Hãy chọn chế độ theo ý nghĩa nghiệp vụ. **matchingAny()** có thể trả về nhiều kết quả hơn vì chỉ cần một tiêu chí thỏa mãn.

## 6. Chọn thuộc tính tham gia điều kiện

QBE quyết định property nào được đưa vào truy vấn dựa trên giá trị probe và cấu hình matcher.

### Mặc định bỏ qua null

Giá trị null trong probe được bỏ qua theo mặc định:

~~~java
Person probe = new Person();
probe.setName("An");
probe.setCity(null);
probe.setEmail(null);

Example<Person> example = Example.of(probe);
~~~

Chỉ **name** tham gia điều kiện. Các property city và email không được yêu cầu phải null.

Đây là điểm quan trọng khi xây dựng bộ lọc tùy chọn: không điền một property có nghĩa là không lọc theo property đó.

### Bỏ qua property cụ thể

Ngay cả khi probe đã có giá trị, có thể loại một property khỏi điều kiện:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIgnorePaths("id", "status");
~~~

Thao tác này hữu ích với ID, trường quản trị, version hoặc property được điền tự động nhưng không thuộc tiêu chí tìm kiếm.

### Bao gồm giá trị null

Nếu muốn kiểm tra property không có giá trị, có thể dùng **withIncludeNullValues()**:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withIncludeNullValues()
    .withIgnorePaths("id");
~~~

Khi đó các property null có thể tham gia tiêu chí. Trong Neo4j, property có giá trị null không được lưu như một giá trị riêng; thao tác gán null tương đương loại bỏ property. Điều kiện kiểm tra null vì vậy liên quan đến property không tồn tại trên node. Hãy dùng chế độ này có chủ đích, vì nó có thể khiến nhiều property chưa được điền trở thành điều kiện lọc.

### Cẩn thận với kiểu primitive

QBE xác định property có tham gia điều kiện dựa trên khả năng null. Các kiểu primitive như **int**, **long** và **boolean** luôn có giá trị mặc định, nên chúng có thể tham gia điều kiện dù ứng dụng không chủ định lọc theo chúng.

Ví dụ, một probe có trường **boolean active** chưa được gán sẽ có giá trị **false**. QBE có thể hiểu đó là tiêu chí tìm người không hoạt động. Với các trường lọc tùy chọn, nên dùng kiểu wrapper như **Boolean**, **Integer** hoặc **Long**, hoặc chủ động thêm property vào **withIgnorePaths**.

## 7. Tùy chỉnh cách so khớp chuỗi

Mặc định, các chuỗi được so khớp chính xác và phân biệt chữ hoa/chữ thường. **ExampleMatcher** cho phép thay đổi cách so khớp.

Các chế độ thường dùng:

| StringMatcher | Ý nghĩa | Ví dụ probe |
|---|---|---|
| **EXACT** | Khớp toàn bộ chuỗi | An |
| **STARTING** | Chuỗi bắt đầu bằng giá trị probe | An |
| **ENDING** | Chuỗi kết thúc bằng giá trị probe | An |
| **CONTAINING** | Chuỗi chứa giá trị probe | An |
| **REGEX** | Khớp theo biểu thức chính quy | ^An.* |

Ví dụ tìm người có tên chứa **an**, không phân biệt chữ hoa/chữ thường:

~~~java
import java.util.List;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

import com.acme.graph.domain.Person;

Person probe = new Person();
probe.setName("an");

ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher(
        "name",
        match -> match.contains().ignoreCase()
    )
    .withIgnorePaths("id", "email", "city", "status");

Example<Person> example = Example.of(probe, matcher);

List<Person> results = personRepository.findAll(example);
~~~

Có thể cấu hình nhiều property với các quy tắc khác nhau:

~~~java
ExampleMatcher matcher = ExampleMatcher.matching()
    .withMatcher("name", match -> match.contains().ignoreCase())
    .withMatcher("email", match -> match.exact().ignoreCase())
    .withIgnorePaths("id", "city", "status");
~~~

Quy tắc cấu hình ở cấp property sẽ ghi đè mặc định của matcher. Hỗ trợ các kiểu so khớp chuỗi phụ thuộc store; SDN hỗ trợ các kiểu như starts, contains, ends và regex. Với property không phải chuỗi, QBE dùng phép so sánh chính xác.

## 8. Dùng fluent API để sắp xếp và phân trang

Ngoài **findAll(example)**, repository hỗ trợ fluent API qua **findBy(example, queryFunction)**. API này cho phép điều khiển kết quả mà không cần thay đổi Example.

Ví dụ phân trang và sắp xếp theo tên:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<Person> page = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("name").ascending())
        .page(PageRequest.of(0, 20))
);
~~~

Một số thao tác fluent thường dùng:

| Thao tác | Công dụng |
|---|---|
| **sortBy(Sort)** | Sắp xếp kết quả |
| **limit(n)** | Giới hạn số kết quả |
| **as(Class)** | Chọn kiểu projection trả về |
| **project(String...)** | Chỉ lấy các property cần thiết |
| **first()** | Lấy kết quả đầu tiên dưới dạng Optional |
| **one()** | Yêu cầu tối đa một kết quả |
| **all()** | Lấy tất cả kết quả |
| **page(Pageable)** | Trả về Page |
| **slice(Pageable)** | Trả về Slice |
| **count()** | Đếm kết quả phù hợp |
| **exists()** | Kiểm tra có kết quả hay không |

Ví dụ chỉ cần một người đầu tiên theo thứ tự tên:

~~~java
import java.util.Optional;

import org.springframework.data.domain.Sort;

Optional<Person> firstMatch = personRepository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("name").ascending())
        .first()
);
~~~

**one()** sẽ báo lỗi nếu có nhiều hơn một kết quả. Dùng nó khi nghiệp vụ yêu cầu kết quả duy nhất và điều kiện tìm kiếm được thiết kế để bảo đảm điều đó.

Nếu dùng **stream()**, hãy đóng stream sau khi xử lý vì stream giữ tài nguyên đọc kết quả:

~~~java
import java.util.stream.Stream;

try (Stream<Person> people = personRepository.findBy(
        example,
        query -> query.stream())) {
    people.forEach(person -> {
        // Xử lý từng hồ sơ tại đây.
    });
}
~~~

## 9. Giới hạn của Query by Example trong Neo4j

QBE rất phù hợp cho các bộ lọc động trên property đơn giản của entity. Tuy nhiên, nó không thay thế toàn bộ khả năng truy vấn của Cypher.

**Không biểu diễn được nhóm điều kiện logic tùy ý.** QBE có chế độ AND hoặc OR cho các tiêu chí được chọn, nhưng không diễn đạt được các biểu thức nhóm phức tạp như:

~~~text
name = "An"
OR
(city = "Da Nang" AND status = "ACTIVE")
~~~

**Không thay thế truy vấn traversal qua graph.** Nếu cần tìm Person có relationship đến Movie thỏa điều kiện, chẳng hạn người tham gia một phim có năm phát hành cụ thể, hãy dùng derived query hỗ trợ property traversal, **@Query** hoặc Cypher DSL phù hợp.

**Property path không đồng nghĩa với nhóm điều kiện lồng nhau.** ExampleMatcher cho phép cấu hình tùy chọn cho các property path như **address.city** khi mapping và store hỗ trợ đường dẫn đó. Điều này không có nghĩa QBE hỗ trợ mọi kiểu nhóm điều kiện lồng nhau hoặc mọi phép duyệt relationship trong Neo4j.

**Các kiểu không phải chuỗi dùng so khớp chính xác.** QBE không phải ngôn ngữ truy vấn khoảng giá trị hoặc biểu thức số học tổng quát. Nếu cần khoảng ngày, điều kiện lớn hơn/nhỏ hơn, nhiều nhánh OR/AND có ngoặc hoặc truy vấn theo relationship phức tạp, hãy chọn derived query hoặc Cypher.

## 10. Những lỗi thường gặp

**Probe không có tiêu chí.** Nếu tất cả property đều null hoặc bị bỏ qua, truy vấn có thể không còn điều kiện lọc và trả về tập dữ liệu rất rộng. Hãy kiểm tra ít nhất một tiêu chí trước khi gọi repository.

**Dùng matchingAny khi nghiệp vụ cần tất cả.** Một kết quả chỉ cần khớp một property có thể được trả về. Hãy xác định rõ ý nghĩa AND/OR trước khi tạo matcher.

**Không bỏ qua ID.** Nếu probe vô tình chứa ID, QBE có thể giới hạn kết quả vào đúng định danh đó. Dùng **withIgnorePaths("id")** khi ID không phải điều kiện tìm kiếm.

**Dùng primitive cho bộ lọc tùy chọn.** Giá trị mặc định 0 hoặc false có thể trở thành tiêu chí. Dùng wrapper hoặc bỏ qua property.

**Cho rằng null có nghĩa là không lọc trong mọi chế độ.** Mặc định null bị bỏ qua, nhưng **withIncludeNullValues()** thay đổi hành vi này.

**Mong đợi chuỗi luôn không phân biệt hoa thường.** Hãy cấu hình **ignoreCase()** rõ ràng nếu yêu cầu nghiệp vụ cần hành vi đó.

**Dùng QBE cho truy vấn graph phức tạp.** Khi điều kiện cần traversal, nhiều nhóm logic hoặc phép tính riêng, hãy chuyển sang Cypher hoặc công cụ truy vấn phù hợp.

## 11. Tự kiểm tra

1. Probe, ExampleMatcher và Example đảm nhiệm vai trò gì trong QBE?
2. **matching()** và **matchingAny()** khác nhau như thế nào?
3. Vì sao các property null được bỏ qua theo mặc định?
4. **withIgnorePaths** có tác dụng gì?
5. Vì sao kiểu primitive có thể tạo điều kiện ngoài ý muốn?
6. Khi nào nên dùng **withIncludeNullValues()**?
7. Vì sao QBE không phù hợp với một truy vấn traversal có nhiều nhóm điều kiện AND/OR?

**Bài tập thực hành:** Xây dựng chức năng tìm Person với các trường name, email, city và status. Tạo một ví dụ dùng **matching()** để yêu cầu tên, thành phố và trạng thái cùng khớp. Tạo ví dụ thứ hai dùng **matchingAny()** để tìm theo tên hoặc email. Thêm quy tắc tên chứa chuỗi không phân biệt hoa thường, bỏ qua ID và phân trang kết quả theo tên. Cuối cùng, thử probe không có tiêu chí và probe có trường primitive mặc định để quan sát vì sao cần kiểm tra đầu vào.

## Tài liệu tham khảo

- [Spring Data Neo4j — Query by Example](https://docs.spring.io/spring-data/neo4j/reference/query-by-example.html)
- [Spring Data Neo4j API — Neo4jRepository](https://docs.spring.io/spring-data/neo4j/docs/current/api/org/springframework/data/neo4j/repository/Neo4jRepository.html)
- [Spring Data Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html)
- [Spring Data Neo4j — FAQ: Find by example](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
