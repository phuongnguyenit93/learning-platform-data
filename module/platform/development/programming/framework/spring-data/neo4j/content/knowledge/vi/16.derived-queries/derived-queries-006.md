# Tìm chuỗi với `Containing`, `StartingWith`, `EndingWith` và `IgnoreCase`

Spring Data Neo4j (SDN) cho phép tạo truy vấn tìm kiếm chuỗi từ tên phương thức repository. Với các từ khóa `Containing`, `StartingWith` và `EndingWith`, bạn có thể tìm một đoạn văn bản xuất hiện ở bất kỳ vị trí nào, ở đầu hoặc ở cuối giá trị. Thêm `IgnoreCase` để so sánh không phân biệt chữ hoa và chữ thường.

Các từ khóa này giúp diễn đạt ý định tìm kiếm ngay trong hợp đồng repository, không cần tự viết Cypher cho những điều kiện chuỗi thông dụng. Để sử dụng đúng, cần hiểu mỗi từ khóa biểu diễn kiểu so khớp nào, cách kết hợp với `IgnoreCase`, và giới hạn về chuẩn hóa văn bản cũng như hiệu năng.

## 1. Ba kiểu so khớp chuỗi cơ bản

Giả sử ứng dụng có các node `Person` với property `name`:

| Từ khóa | Ý nghĩa | Điều kiện Cypher tương ứng về mặt ngữ nghĩa |
|---|---|---|
| `Containing` | Giá trị chứa đoạn văn bản ở bất kỳ vị trí nào | `name CONTAINS $value` |
| `StartingWith` | Giá trị bắt đầu bằng đoạn văn bản | `name STARTS WITH $value` |
| `EndingWith` | Giá trị kết thúc bằng đoạn văn bản | `name ENDS WITH $value` |

Ví dụ với các tên `Nguyen An`, `Tran Anh`, `An Nguyen`:

- `Containing("An")` tìm những tên có chuỗi `An` xuất hiện ở bất kỳ vị trí nào.
- `StartingWith("Ng")` tìm những tên bắt đầu bằng `Ng`.
- `EndingWith("Anh")` tìm những tên kết thúc bằng `Anh`.

Các phép so khớp trên là tìm chuỗi con, tiền tố hoặc hậu tố. Chúng không phải tìm kiếm gần đúng, không tự sửa lỗi chính tả và không tương đương với biểu thức chính quy.

## 2. Khai báo entity và repository

Entity đơn giản để minh họa:

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private boolean active;

    protected Person() {
    }

    public Person(String name) {
        this.name = name;
        this.active = true;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository khai báo các phương thức tìm kiếm:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    List<Person> findByNameContaining(String fragment);

    List<Person> findByNameStartingWith(String prefix);

    List<Person> findByNameEndingWith(String suffix);
}
```

SDN phân tích tên phương thức để xác định property `name` và kiểu điều kiện cần tạo. Bạn không cần viết `@Query` chỉ để thực hiện ba kiểu so khớp cơ bản này.

## 3. `Containing`: tìm chuỗi con ở bất kỳ vị trí nào

`Containing` phù hợp khi đoạn văn bản cần tìm có thể xuất hiện ở đầu, giữa hoặc cuối giá trị.

```java
List<Person> findByNameContaining(String fragment);
```

Ví dụ gọi repository:

```java
List<Person> matches = personRepository.findByNameContaining("uyen");
```

Phương thức tìm các node `Person` có `name` chứa `uyen`, chẳng hạn `Nguyen An`. Về mặt ngữ nghĩa, điều kiện tương ứng là:

```cypher
MATCH (p:Person)
WHERE p.name CONTAINS $fragment
RETURN p
```

`Containing` không yêu cầu đoạn tìm kiếm nằm ở một vị trí cố định. Đây là lựa chọn phù hợp cho ô tìm kiếm tên hoặc mã có thể nhập một phần.

## 4. `StartingWith`: tìm theo tiền tố

`StartingWith` chỉ khớp khi giá trị bắt đầu bằng đoạn văn bản được truyền vào:

```java
List<Person> findByNameStartingWith(String prefix);
```

Ví dụ:

```java
List<Person> matches = personRepository.findByNameStartingWith("Ngu");
```

Điều kiện tương ứng về mặt ngữ nghĩa:

```cypher
MATCH (p:Person)
WHERE p.name STARTS WITH $prefix
RETURN p
```

Kiểu truy vấn này phù hợp với gợi ý khi người dùng nhập phần đầu của tên, mã hoặc tiêu đề. Nó không tìm chuỗi ở giữa giá trị; với nhu cầu đó, dùng `Containing`.

## 5. `EndingWith`: tìm theo hậu tố

`EndingWith` khớp khi giá trị kết thúc bằng đoạn văn bản:

```java
List<Person> findByNameEndingWith(String suffix);
```

Ví dụ:

```java
List<Person> matches = personRepository.findByNameEndingWith("An");
```

Điều kiện Cypher tương ứng:

```cypher
MATCH (p:Person)
WHERE p.name ENDS WITH $suffix
RETURN p
```

Hậu tố có thể hữu ích khi tìm mã có phần kết thúc cố định hoặc tên theo một quy ước nhất định. Với tìm kiếm tên người, hãy xác định rõ người dùng đang muốn tìm theo phần cuối của toàn bộ chuỗi hay theo một thành phần tên riêng; derived query chỉ so khớp trên giá trị của property đã chọn.

## 6. `IgnoreCase`: không phân biệt chữ hoa và chữ thường

Mặc định, các phép so khớp chuỗi trong Cypher phân biệt chữ hoa và chữ thường. Thêm `IgnoreCase` vào tên phương thức để yêu cầu SDN thực hiện so khớp không phân biệt hoa thường:

```java
List<Person> findByNameContainingIgnoreCase(String fragment);

List<Person> findByNameStartingWithIgnoreCase(String prefix);

List<Person> findByNameEndingWithIgnoreCase(String suffix);
```

Ví dụ, `findByNameContainingIgnoreCase("AN")` có thể khớp với `An Nguyen`, `nguyen an` hoặc `TRAN ANH` theo quy tắc so sánh không phân biệt hoa thường.

Về mặt ngữ nghĩa, điều kiện có thể được hiểu tương tự như việc chuyển cả property và tham số về cùng dạng chữ thường trước khi so khớp:

```cypher
MATCH (p:Person)
WHERE toLower(p.name) CONTAINS toLower($fragment)
RETURN p
```

Đây là hình dạng diễn giải để hiểu hành vi; truy vấn Cypher thực tế do SDN sinh ra có thể khác về alias, cách bind tham số hoặc biểu thức chuyển đổi tùy phiên bản.

`IgnoreCase` chỉ xử lý khác biệt chữ hoa và chữ thường. Nó không tự loại bỏ dấu tiếng Việt, không chuẩn hóa dấu Unicode và không biến `a`, `á`, `ă`, `â` thành cùng một ký tự. Nếu nghiệp vụ cần tìm không phân biệt dấu, cần thiết kế bước chuẩn hóa dữ liệu và truy vấn riêng.

## 7. Kết hợp các từ khóa trong repository

Một repository có thể cung cấp nhiều biến thể để caller chọn theo ý định tìm kiếm:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, Long> {

    List<Person> findByNameContaining(String fragment);

    List<Person> findByNameContainingIgnoreCase(String fragment);

    List<Person> findByNameStartingWithIgnoreCase(String prefix);

    List<Person> findByNameEndingWithIgnoreCase(String suffix);
}
```

Tên phương thức gồm ba phần:

1. `findBy` cho biết đây là truy vấn tìm kiếm.
2. `Name` xác định property Java cần truy vấn.
3. `Containing`, `StartingWith` hoặc `EndingWith` chọn kiểu so khớp; `IgnoreCase` bổ sung quy tắc không phân biệt hoa thường.

Nếu property Java được ánh xạ sang key Neo4j khác bằng `@Property`, tên trong derived query vẫn dựa trên property Java. Ví dụ field `fullName` có `@Property("full_name")` thì phương thức là `findByFullNameContaining(...)`; khi tự viết Cypher, bạn dùng key lưu trữ `full_name`.

## 8. Kiểm soát đầu vào tìm kiếm

Derived query bind giá trị tham số thay vì nối trực tiếp chuỗi đầu vào vào Cypher. Tuy vậy, ứng dụng vẫn nên kiểm soát đầu vào để có kết quả hữu ích và tránh truy vấn quá rộng.

Một số quy tắc thực tế:

- Loại bỏ khoảng trắng thừa ở hai đầu nếu giao diện không xem chúng là một phần của nội dung tìm kiếm.
- Quy định độ dài tối thiểu cho tìm kiếm `Containing`, đặc biệt trên tập dữ liệu lớn.
- Xử lý chuỗi rỗng trước khi gọi repository; một chuỗi tìm kiếm rỗng có thể khớp với rất nhiều giá trị và tạo kết quả không mong muốn.
- Xác định rõ cách xử lý `null`. Property không tồn tại hoặc có giá trị null không giống một chuỗi rỗng; phép so sánh Cypher với null không cho kết quả true.
- Giới hạn số kết quả hoặc dùng phân trang khi API và truy vấn hỗ trợ, tránh trả về toàn bộ graph chỉ vì đoạn tìm kiếm quá ngắn.

Ví dụ service kiểm tra đầu vào:

```java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {

    private final PersonRepository people;

    public PersonSearchService(PersonRepository people) {
        this.people = people;
    }

    public List<Person> searchByName(String input) {
        if (input == null || input.isBlank()) {
            return List.of();
        }

        String fragment = input.trim();
        if (fragment.length() < 2) {
            return List.of();
        }

        return people.findByNameContainingIgnoreCase(fragment);
    }
}
```

Ví dụ này chọn quy tắc tối thiểu hai ký tự cho use case tìm người. Đây là quyết định của ứng dụng, không phải giới hạn bắt buộc của SDN.

## 9. Khác biệt giữa tìm chuỗi con và full-text search

`Containing`, `StartingWith` và `EndingWith` là các điều kiện chuỗi đơn giản. Chúng phù hợp với trường hợp tìm chính xác một đoạn ký tự trong một property. Chúng không cung cấp xếp hạng mức độ liên quan, tìm gần đúng, xử lý từ đồng nghĩa hoặc phân tích ngôn ngữ.

Nếu ứng dụng cần tìm kiếm trên nhiều field, hỗ trợ tokenization, stemming, fuzzy matching hoặc ranking, hãy xem xét full-text index của Neo4j và truy vấn qua thủ tục tìm kiếm tương ứng. Khi đó, `Neo4jClient` hoặc `@Query` có thể phù hợp hơn derived query thông thường.

Về hiệu năng:

- Điều kiện tiền tố `STARTS WITH` có thể tận dụng range index trong các trường hợp Neo4j hỗ trợ; cần kiểm tra kế hoạch thực thi.
- Điều kiện chứa chuỗi con `CONTAINS` và hậu tố `ENDS WITH` thường không có cùng đặc tính tối ưu như tìm kiếm theo tiền tố trên range index.
- Với nhu cầu tìm kiếm văn bản rộng, full-text index thường là lựa chọn cần đánh giá.
- Dùng `EXPLAIN` hoặc `PROFILE` để xem truy vấn thực tế có sử dụng index hay phải quét nhiều node.

Không nên suy luận hiệu năng chỉ từ tên method. Hãy đo trên dữ liệu có kích thước và phân bố gần với môi trường chạy thật.

## 10. Khi nào cần dùng `@Query` thay cho derived query?

Derived query phù hợp khi điều kiện có thể diễn đạt bằng tên property và từ khóa có sẵn. Chuyển sang `@Query` hoặc `Neo4jClient` khi cần:

- Kết hợp nhiều nhánh điều kiện phức tạp hoặc biểu thức Cypher riêng.
- Chuẩn hóa dấu hoặc xử lý văn bản theo quy tắc nghiệp vụ riêng.
- Tìm kiếm trên nhiều node hoặc relationship trong cùng một truy vấn.
- Dùng full-text index, xếp hạng kết quả hoặc thủ tục tìm kiếm của Neo4j.
- Trả về DTO tổng hợp thay vì entity `Person`.

Ví dụ truy vấn thủ công tìm theo tiền tố không phân biệt hoa thường:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (p:Person)
    WHERE toLower(p.name) STARTS WITH toLower($prefix)
    RETURN p
    ORDER BY p.name
    """)
List<Person> searchByNormalizedPrefix(@Param("prefix") String prefix);
```

Trong ví dụ, Cypher được viết tường minh vì use case cần thể hiện rõ phép chuẩn hóa và sắp xếp. Tham số vẫn được bind bằng `$prefix`.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `Containing` nhưng kỳ vọng chỉ tìm ở đầu chuỗi | Nhầm tìm chuỗi con với tìm tiền tố | Dùng `StartingWith` |
| Dùng `EndingWith` nhưng kết quả rỗng | Đoạn tìm kiếm không nằm ở cuối property | Kiểm tra dữ liệu và dùng đúng hậu tố |
| Kết quả khác nhau giữa `An` và `an` | Điều kiện mặc định phân biệt hoa thường | Thêm `IgnoreCase` khi phù hợp |
| Kỳ vọng `IgnoreCase` bỏ dấu tiếng Việt | IgnoreCase không phải accent-insensitive search | Chuẩn hóa dấu riêng hoặc dùng giải pháp tìm kiếm chuyên biệt |
| Chuỗi rỗng trả về quá nhiều kết quả | `Containing` với đầu vào rỗng có thể quá rộng | Kiểm tra input trước khi gọi repository |
| Tìm kiếm chậm trên graph lớn | Điều kiện chứa/hậu tố có thể không tận dụng range index như tiền tố | Dùng `PROFILE`, đánh giá full-text index hoặc điều chỉnh truy vấn |
| Tên method dùng property key thay cho tên Java | Nhầm metadata mapping với tên field trong mô hình | Dùng tên property Java trong derived query |

## 12. Tự kiểm tra

1. `Containing` khác `StartingWith` và `EndingWith` ở vị trí đoạn tìm kiếm như thế nào?
2. Với method `findByNameContainingIgnoreCase("AN")`, điều kiện tìm kiếm thay đổi ra sao so với `findByNameContaining("AN")`?
3. `IgnoreCase` có làm cho `a` và `á` được xem là giống nhau không?
4. Nếu property Java `fullName` được ánh xạ bằng `@Property("full_name")`, tên derived query phải dùng phần nào?
5. Vì sao cần giới hạn độ dài đầu vào cho tìm kiếm `Containing`?
6. Khi nào nên cân nhắc full-text index thay cho derived query?

Chọn đúng `Containing`, `StartingWith`, `EndingWith` và `IgnoreCase` giúp repository thể hiện chính xác ý định tìm kiếm chuỗi. Khi yêu cầu vượt khỏi so khớp chuỗi cơ bản, hãy chuyển sang Cypher hoặc full-text search để kiểm soát rõ quy tắc tìm kiếm và hiệu năng.
