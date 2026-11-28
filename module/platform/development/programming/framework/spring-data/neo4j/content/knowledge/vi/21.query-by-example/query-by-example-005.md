# Khớp chuỗi, phân biệt hoa thường và tùy chỉnh theo trường

## Mục tiêu bài học

Query by Example (QBE) cho phép tạo truy vấn từ một object mẫu (probe) thay vì viết tên phương thức dài hoặc tự viết Cypher. Khi cần tìm theo chuỗi, Spring Data Neo4j (SDN) có thể dùng `ExampleMatcher` để xác định cách so khớp: khớp chính xác, bắt đầu bằng, kết thúc bằng hoặc chứa một đoạn văn bản. Matcher cũng cho phép quy định có phân biệt chữ hoa và chữ thường hay không, áp dụng chung hoặc tùy chỉnh riêng cho từng property.

Bài học này hướng dẫn cách tạo probe, cấu hình `ExampleMatcher`, kết hợp nhiều điều kiện, xử lý giá trị null và primitive, rồi thực thi qua repository. Bạn sẽ biết cách chọn chế độ so khớp cho từng trường, kiểm thử hành vi thực tế trên Neo4j và nhận diện khi nào QBE không còn phù hợp với yêu cầu truy vấn.

## 1. Ba thành phần của Query by Example

QBE gồm ba thành phần cốt lõi:

- **Probe:** object domain có những property được gán giá trị dùng làm điều kiện tìm kiếm.
- **ExampleMatcher:** quy định cách so khớp, cách xử lý null, chữ hoa/thường và các tùy chỉnh theo property.
- **Example:** kết hợp probe và matcher thành đối tượng mà repository dùng để tạo truy vấn.

Ví dụ ứng dụng quản lý người dùng:

```java
@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;

    private String lastName;

    private String email;

    private String city;

    private Integer age;

    // Constructor, getter và setter được lược bỏ.
}
```

Repository cần triển khai `QueryByExampleExecutor<Person>`:

```java
public interface PersonRepository
        extends Neo4jRepository<Person, Long>,
                QueryByExampleExecutor<Person> {
}
```

Tạo một probe chỉ có tên:

```java
Person probe = new Person();
probe.setFirstName("Minh");

Example<Person> example = Example.of(probe);
Iterable<Person> people = personRepository.findAll(example);
```

Các property có giá trị `null` được bỏ qua theo mặc định. Vì vậy, probe trên chỉ đặt điều kiện cho `firstName`; `lastName`, `email`, `city` và `age` không tham gia điều kiện.

`Example` và `ExampleMatcher` là immutable. Các phương thức cấu hình như `withStringMatcher()`, `withIgnoreCase()` và `withMatcher()` trả về một matcher mới. Hãy gán kết quả trả về vào biến để cấu hình được áp dụng.

## 2. Cách kết hợp các điều kiện trong probe

Mặc định, `ExampleMatcher.matching()` (tương đương `matchingAll()`) yêu cầu tất cả predicate được tạo từ các property có giá trị đều khớp. Có thể hiểu đây là phép AND giữa các điều kiện.

```java
Person probe = new Person();
probe.setFirstName("Minh");
probe.setCity("Hà Nội");

Example<Person> example = Example.of(
        probe,
        ExampleMatcher.matching()
);
```

Truy vấn này tìm người có cả tên khớp `Minh` và thành phố khớp `Hà Nội` theo chế độ chuỗi mặc định của store.

Nếu nghiệp vụ chỉ cần khớp ít nhất một trong các điều kiện đã cung cấp, dùng `matchingAny()`:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny();

Example<Person> example = Example.of(probe, matcher);
```

Khi đó, các predicate được kết hợp theo OR. Chỉ các property có giá trị trong probe mới tạo predicate; `matchingAny()` không tự biến những trường null thành điều kiện.

| Cấu hình | Ý nghĩa |
|---|---|
| `matching()` hoặc `matchingAll()` | Tất cả predicate phải khớp (AND) |
| `matchingAny()` | Chỉ cần một predicate khớp (OR) |

QBE phù hợp với điều kiện phẳng kiểu “tất cả trường đều đúng” hoặc “một trong các trường đúng”. Nó không biểu diễn được mọi nhóm điều kiện phức tạp như `firstName = A OR (city = B AND age > C)`. Với biểu thức logic lồng nhau, hãy dùng custom Cypher bằng `@Query` hoặc `Neo4jClient`.

## 3. Các chế độ so khớp chuỗi

`ExampleMatcher.StringMatcher` cung cấp các chế độ mô tả cách so sánh chuỗi. Có thể cấu hình một chế độ mặc định cho tất cả trường chuỗi hoặc ghi đè theo từng property.

| Chế độ | Hành vi | Ví dụ probe | Giá trị có thể khớp |
|---|---|---|---|
| `DEFAULT` | Dùng cách so khớp mặc định của store | `"Minh"` | Phụ thuộc store |
| `EXACT` | Giá trị chuỗi phải khớp chính xác | `"Minh"` | `"Minh"` |
| `STARTING` | Giá trị lưu bắt đầu bằng probe | `"Min"` | `"Minh Anh"` |
| `ENDING` | Giá trị lưu kết thúc bằng probe | `"Anh"` | `"Minh Anh"` |
| `CONTAINING` | Giá trị lưu chứa probe | `"Minh"` | `"Nguyễn Minh Anh"` |
| `REGEX` | So khớp bằng biểu thức chính quy | `"Min.*"` | Phụ thuộc regex và store |

Tài liệu QBE của Spring Data lưu ý rằng hỗ trợ string matching phụ thuộc từng datastore. Vì vậy, không nên mặc định mọi chế độ trong API đều được hỗ trợ giống nhau ở mọi phiên bản SDN. Các ví dụ phổ biến như exact, starts-with, ends-with và contains cần được xác nhận bằng integration test trên phiên bản SDN của ứng dụng; chỉ dùng regex khi backend và phiên bản đang chạy hỗ trợ rõ ràng.

### Cấu hình chung cho mọi trường chuỗi

Ví dụ tìm người có tên chứa chuỗi `minh`, không phân biệt hoa thường:

```java
Person probe = new Person();
probe.setFirstName("minh");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
        .withIgnoreCase();

Example<Person> example = Example.of(probe, matcher);

Iterable<Person> people = personRepository.findAll(example);
```

`withStringMatcher(CONTAINING)` áp dụng chế độ chứa chuỗi cho các property kiểu String có tham gia vào probe. `withIgnoreCase()` đặt mặc định không phân biệt hoa thường cho các property chuỗi phù hợp.

Có thể dùng `STARTING` khi xây dựng tìm kiếm theo tiền tố, ví dụ gợi ý tên khi người dùng nhập vài ký tự đầu. `ENDING` hữu ích khi nghiệp vụ tìm theo hậu tố. `EXACT` phù hợp với giá trị cần so khớp toàn bộ như mã phân loại hoặc email khi chính sách của ứng dụng yêu cầu so sánh chính xác.

### Tùy chỉnh chế độ cho từng trường

Không phải mọi trường đều cần cùng một cách so khớp. Ví dụ, tên có thể tìm theo một phần và không phân biệt hoa thường, trong khi email cần khớp chính xác và phân biệt hoa thường:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withMatcher("firstName",
                match -> match.contains().ignoreCase())
        .withMatcher("email",
                match -> match.exact().caseSensitive());
```

Có thể đặt nhiều matcher theo từng property:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withMatcher("firstName",
                match -> match.startsWith().ignoreCase())
        .withMatcher("lastName",
                match -> match.endsWith().caseSensitive())
        .withMatcher("email",
                match -> match.exact().caseSensitive());
```

Trong ví dụ trên:

- `firstName` bắt đầu bằng chuỗi probe và bỏ qua khác biệt hoa thường.
- `lastName` kết thúc bằng chuỗi probe và phân biệt hoa thường.
- `email` được so khớp chính xác và phân biệt hoa thường.

Tên trong `withMatcher("firstName", ...)` là property Java của entity, không phải tên label hoặc tên property vật lý trong Neo4j. Nếu entity dùng `@Property("first_name")` cho trường Java `firstName`, matcher vẫn tham chiếu `firstName`.

## 4. Phân biệt hoa thường ở cấp toàn bộ matcher và từng property

Theo mặc định của `ExampleMatcher`, chế độ ignore case không được bật; cấu hình mặc định là phân biệt hoa thường. Có thể đổi mặc định cho mọi property chuỗi:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase();
```

Hoặc đặt rõ ràng:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase(false);
```

Nếu chỉ muốn bỏ qua hoa thường cho một số trường, dùng danh sách property:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase("firstName", "city");
```

Một matcher theo property có thể ghi đè mặc định chung:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withStringMatcher(ExampleMatcher.StringMatcher.CONTAINING)
        .withIgnoreCase()
        .withMatcher("email",
                match -> match.exact().caseSensitive());
```

Trong cấu hình này, các trường chuỗi kế thừa chế độ contains và ignore case. Riêng `email` dùng exact và case-sensitive. Cấu hình ở cấp property có độ ưu tiên cao hơn cấu hình mặc định của matcher.

Lưu ý: `ignoreCase()` là tùy chọn của Spring Data. Kết quả cuối cùng còn phụ thuộc khả năng dịch điều kiện của store và phiên bản SDN. Với Neo4j, hãy kiểm thử dữ liệu có cả `Minh`, `MINH` và `minh` để xác nhận đúng hành vi mong muốn. Nếu hệ thống có yêu cầu chuẩn hóa đặc biệt về dấu tiếng Việt hoặc quy tắc locale, cần kiểm thử riêng vì bỏ qua hoa thường không đồng nghĩa loại bỏ dấu.

## 5. Kết hợp matcher chung và matcher riêng

Một màn hình tìm người dùng có thể có các quy tắc như sau:

- Tên bắt đầu bằng chuỗi nhập vào, không phân biệt hoa thường.
- Họ chứa chuỗi nhập vào, không phân biệt hoa thường.
- Email khớp chính xác và phân biệt hoa thường.
- Thành phố khớp chính xác theo mặc định của matcher.

Có thể cấu hình như sau:

```java
Person probe = new Person();
probe.setFirstName("an");
probe.setLastName("ng");
probe.setEmail("An@example.com");
probe.setCity("Hà Nội");

ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnoreCase()
        .withMatcher("firstName",
                match -> match.startsWith().ignoreCase())
        .withMatcher("lastName",
                match -> match.contains().ignoreCase())
        .withMatcher("email",
                match -> match.exact().caseSensitive())
        .withMatcher("city",
                match -> match.exact());

Example<Person> example = Example.of(probe, matcher);
Iterable<Person> result = personRepository.findAll(example);
```

Vì matcher dùng `matching()`, một người chỉ được trả về khi tất cả điều kiện được cấu hình đều khớp. `email` vẫn phân biệt hoa thường dù matcher chung đã bật ignore case, bởi cấu hình riêng của property ghi đè mặc định.

Hãy giữ matcher gần với quy tắc tìm kiếm của màn hình hoặc use case. Nếu một phương thức service phải xử lý nhiều bộ quy tắc khác nhau, có thể tạo các hàm xây dựng `ExampleMatcher` riêng để tránh lặp cấu hình và giúp kiểm thử dễ hơn.

## 6. Bỏ qua property và xử lý null

QBE mặc định bỏ qua property có giá trị `null`. Điều này giúp probe chỉ cần gán các trường mà người dùng đã nhập.

```java
Person probe = new Person();
probe.setFirstName("Lan");
// lastName, email, city và age vẫn null.

Example<Person> example = Example.of(probe);
```

Nếu cần bỏ qua một property dù nó đang có giá trị, dùng `withIgnorePaths()`:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withIgnorePaths("id", "age");

Example<Person> example = Example.of(probe, matcher);
```

Một điểm dễ gây nhầm là các trường primitive như `int`, `long` và `boolean` luôn có giá trị mặc định như `0` hoặc `false`, nên QBE xem chúng là property có giá trị và đưa vào điều kiện nếu không bị ignore. Với probe tìm kiếm động, nên ưu tiên kiểu wrapper như `Integer`, `Long` và `Boolean` để có thể biểu diễn trạng thái chưa được cung cấp bằng `null`.

Nếu muốn tìm các node không có giá trị cho một property, có thể yêu cầu đưa null vào tiêu chí:

```java
ExampleMatcher matcher = ExampleMatcher.matching()
        .withIncludeNullValues();
```

Chỉ dùng `withIncludeNullValues()` khi null thực sự là điều kiện tìm kiếm. Trong Neo4j, property không có giá trị được biểu diễn bằng việc property không tồn tại trên node; hãy kiểm thử kết quả QBE với dữ liệu thiếu property theo đúng phiên bản SDN đang dùng. Không bật include-null toàn cục cho probe tìm kiếm thông thường nếu không muốn thêm nhiều điều kiện null ngoài ý định.

## 7. Ví dụ hoàn chỉnh trong service

Có thể đóng gói việc tạo probe và matcher trong service để controller chỉ truyền các tiêu chí tìm kiếm:

```java
@Service
public class PersonSearchService {

    private final PersonRepository personRepository;

    public PersonSearchService(PersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    public Iterable<Person> search(String name, String email) {
        Person probe = new Person();
        probe.setFirstName(name);
        probe.setEmail(email);

        ExampleMatcher matcher = ExampleMatcher.matching()
                .withIgnorePaths("id", "age")
                .withMatcher("firstName",
                        match -> match.contains().ignoreCase())
                .withMatcher("email",
                        match -> match.exact().caseSensitive());

        Example<Person> example = Example.of(probe, matcher);

        return personRepository.findAll(example);
    }
}
```

Nếu `name` là `null`, điều kiện `firstName` bị bỏ qua. Nếu `email` là `null`, điều kiện email cũng bị bỏ qua. Khi cả hai đều null, probe không còn điều kiện chuỗi và có thể trả về rất nhiều người. Vì vậy, service nên xác định tiêu chí tối thiểu trước khi thực thi, ví dụ yêu cầu ít nhất một trường tìm kiếm được cung cấp.

Khi chỉ muốn một kết quả, có thể dùng `findOne(example)`; phương thức này cần tối đa một kết quả và sẽ báo lỗi nếu có nhiều kết quả phù hợp. Với tìm kiếm thông thường có thể trả về nhiều người, dùng `findAll(example)` hoặc fluent API để giới hạn, sắp xếp và phân trang.

## 8. Khi nào QBE không còn phù hợp?

QBE phù hợp với biểu mẫu tìm kiếm có các điều kiện độc lập trên property của một entity. Nó không phải ngôn ngữ truy vấn tổng quát cho mọi cấu trúc graph.

Nên cân nhắc custom Cypher khi cần:

- Điều kiện OR lồng nhau hoặc nhóm AND/OR phức tạp.
- Traversal qua nhiều relationship với điều kiện trên cả node và relationship.
- Lọc theo độ dài path hoặc cấu trúc graph đặc thù.
- So khớp regex hoặc toán tử chuỗi chưa được hỗ trợ trong phiên bản SDN đang dùng.
- Tối ưu một truy vấn cần kiểm soát rõ ràng index, projection hoặc kế hoạch thực thi.

Ví dụ, tìm người có tên chứa một đoạn văn bản và có đơn hàng vượt một mức tiền nhất định cần duyệt qua relationship `PLACED`:

```cypher
MATCH (p:Person)-[:PLACED]->(o:Order)
WHERE toLower(p.firstName) CONTAINS toLower($namePart)
  AND o.total > $minimumTotal
RETURN DISTINCT p
```

Đây là truy vấn graph có điều kiện trên node và node liên quan; QBE của một probe `Person` không biểu diễn trực tiếp đầy đủ quy tắc này. Dùng `@Query` hoặc `Neo4jClient` sẽ minh bạch hơn.

## 9. Kiểm thử chế độ khớp chuỗi

Đừng chỉ kiểm tra rằng repository trả về kết quả. Hãy tạo dữ liệu có khác biệt rõ ràng về tiền tố, hậu tố, chuỗi con và chữ hoa/thường.

Ví dụ bộ dữ liệu:

| ID | firstName | email |
|---|---|---|
| 1 | Nguyễn Minh Anh | Minh@example.com |
| 2 | MINH Hoàng | minh@example.com |
| 3 | Hoàng An | an@example.com |
| 4 | Lan Minh | lan@example.com |

Với probe `firstName = "minh"` và matcher `CONTAINING` + ignore case, các node 1, 2 và 4 có thể khớp. Với matcher `STARTING` + ignore case, node 2 khớp nhưng node 1 và 4 không khớp. Với matcher `ENDING` + case-sensitive cho chuỗi `"Minh"`, node 4 khớp nếu giá trị kết thúc chính xác bằng `Minh`.

Khung integration test:

```java
@DataNeo4jTest
class PersonQueryByExampleTest {

    @Autowired
    private PersonRepository personRepository;

    @Test
    void shouldMatchNameContainsIgnoringCase() {
        Person probe = new Person();
        probe.setFirstName("minh");

        ExampleMatcher matcher = ExampleMatcher.matching()
                .withMatcher("firstName",
                        match -> match.contains().ignoreCase());

        Iterable<Person> result = personRepository.findAll(
                Example.of(probe, matcher));

        // Xác nhận các ID 1, 2 và 4 được trả về.
    }
}
```

Nên có thêm test cho:

1. `EXACT` và `caseSensitive()`.
2. `STARTING`, `ENDING` và `CONTAINING`.
3. Cùng một property với `ignoreCase()`.
4. Matcher chung bị ghi đè bởi matcher riêng.
5. Property null bị bỏ qua theo mặc định.
6. Primitive mặc định được đưa vào điều kiện.
7. `matching()` và `matchingAny()` cho kết quả khác nhau.
8. Regex nếu ứng dụng thực sự dùng và SDN version hỗ trợ.

Nếu hành vi chuỗi thay đổi sau khi nâng cấp SDN hoặc Neo4j, các test này giúp phát hiện khác biệt sớm. Với truy vấn có yêu cầu hiệu năng, hãy kiểm tra thêm Cypher được sinh ra và dùng `PROFILE` trên dữ liệu đại diện.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tìm chính xác nhưng nhận quá ít kết quả | Dùng chế độ mặc định hoặc `EXACT` trong khi cần tìm một phần | Chọn `CONTAINING`, `STARTING` hoặc `ENDING` |
| Kết quả khác nhau giữa chữ hoa và chữ thường | Ignore case chưa được bật | Dùng `withIgnoreCase()` hoặc `ignoreCase()` theo property |
| Bật ignore case toàn cục nhưng email vẫn cần phân biệt | Mặc định chung áp dụng cho mọi trường chuỗi | Ghi đè email bằng `caseSensitive()` |
| Property không được lọc dù probe đã có giá trị | Property nằm trong `withIgnorePaths()` | Kiểm tra danh sách property bị bỏ qua |
| Probe tự thêm điều kiện tuổi bằng 0 | Entity dùng primitive `int` | Dùng `Integer` hoặc ignore path |
| Không tìm được node vì một trường khác vô tình tham gia | Probe có thêm property khác được gán giá trị | Tạo probe riêng và ignore property không liên quan |
| Kỳ vọng QBE xử lý nhóm OR phức tạp | QBE chỉ hỗ trợ tổ hợp predicate ở mức đơn giản | Dùng custom Cypher |
| Dùng regex mà truy vấn không hoạt động như mong đợi | Backend hoặc phiên bản SDN không hỗ trợ chế độ đó | Kiểm tra tài liệu và integration test; dùng `@Query` nếu cần |
| Kỳ vọng null bị đưa vào điều kiện mặc định | Null mặc định được bỏ qua | Chỉ bật `withIncludeNullValues()` khi thực sự cần |

## 11. Tự kiểm tra

1. Probe, ExampleMatcher và Example có vai trò gì trong QBE?
2. `matching()` khác `matchingAny()` như thế nào?
3. `CONTAINING`, `STARTING` và `ENDING` khác nhau ra sao?
4. Làm thế nào để cấu hình ignore case cho mọi property chuỗi?
5. Làm thế nào để chỉ `firstName` không phân biệt hoa thường còn `email` phân biệt?
6. Vì sao matcher riêng có thể ghi đè matcher mặc định?
7. Vì sao trường `int` có thể vô tình tạo điều kiện tìm kiếm bằng 0?
8. Khi nào nên chuyển từ QBE sang custom Cypher?

Hãy tạo probe `Person` có `firstName` và `email`. Viết một matcher dùng contains không phân biệt hoa thường cho tên và exact phân biệt hoa thường cho email. Tạo dữ liệu có tên viết hoa, viết thường và email khác nhau về casing; chạy truy vấn rồi xác nhận từng trường tuân theo matcher riêng. Sau đó đổi matcher chung sang `matchingAny()` để quan sát cách kết hợp điều kiện thay đổi.

## Tài liệu tham khảo

- [Spring Data Neo4j — Query by Example](https://docs.spring.io/spring-data/neo4j/reference/query-by-example.html)
- [Spring Data Commons — ExampleMatcher API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ExampleMatcher.html)
- [Spring Data Commons — GenericPropertyMatcher API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ExampleMatcher.GenericPropertyMatcher.html)
