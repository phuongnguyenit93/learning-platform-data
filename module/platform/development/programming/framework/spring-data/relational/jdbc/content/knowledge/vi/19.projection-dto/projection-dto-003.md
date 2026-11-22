# Projection mở, biểu thức và chi phí xử lý

Projection cho phép một repository trả về **góc nhìn giới hạn của aggregate** thay vì luôn trả về toàn bộ domain object. Với Spring Data JDBC, projection hữu ích cho màn hình danh sách, API đọc và các trường hợp chỉ cần một số thuộc tính. Khi cần tính giá trị trình bày từ nhiều thuộc tính, Spring Data còn hỗ trợ **open projection**: interface projection có thể dùng biểu thức SpEL qua annotation `@Value`.

Open projection linh hoạt, nhưng biểu thức có thể đọc bất kỳ thuộc tính nào của aggregate root. Vì vậy Spring Data không thể biết trước tập thuộc tính tối thiểu để tối ưu việc lấy dữ liệu. Ngoài chi phí truy vấn và ánh xạ aggregate, ứng dụng còn phải trả chi phí tạo proxy và đánh giá biểu thức. Cần hiểu rõ các chi phí này trước khi dùng open projection cho danh sách lớn.

Bài học dùng ví dụ hồ sơ người dùng để trình bày:

- Projection interface và class-based projection (DTO).
- Closed projection và open projection.
- Biểu thức SpEL với `@Value`.
- `target`, `args` và gọi Spring bean từ expression.
- Default method như một lựa chọn cho phép tính đơn giản.
- Dynamic projection và nullable wrapper.
- Ảnh hưởng đến SQL, object materialization, CPU, bộ nhớ và serialization.
- Cách chọn projection phù hợp trong Spring Data JDBC.

## 1. Projection là gì?

Một repository thông thường trả về aggregate root:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<Person> findByLastName(String lastName);
}
~~~

Khi gọi `findByLastName("Nguyen")`, ứng dụng nhận các object `Person` theo mô hình domain. Nhưng một màn hình danh bạ có thể chỉ cần tên và email; nó không cần mọi thuộc tính hoặc mọi thành phần con của aggregate.

Projection mô tả một **view chuyên biệt** chứa những thuộc tính mà use case đọc cần.

Ví dụ:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();
}
~~~

Repository có thể khai báo:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<PersonNameView> findByLastName(String lastName);
}
~~~

Spring Data tạo proxy cho interface projection ở thời điểm chạy. Khi ứng dụng gọi `getFirstName()`, proxy chuyển lời gọi đến thuộc tính tương ứng của object đích.

Projection type nằm ngoài hệ thống kế thừa của entity. Nếu repository trả về một superclass hoặc interface mà `Person` đã triển khai, Spring Data có thể trả về entity được materialize đầy đủ; việc khai báo một supertype không tự tạo projection.

### 1.1. Projection không phải một entity mới

`PersonNameView` chỉ mô tả dữ liệu đọc. Nó không phải aggregate root và không có repository riêng. Các getter của projection không tạo ra một bản ghi mới hoặc thay đổi vòng đời persistence của `Person`.

| Loại kết quả | Ý nghĩa |
|---|---|
| `Person` | Aggregate root theo mô hình domain |
| Interface projection | View được tạo qua proxy từ các thuộc tính của object đích |
| DTO projection | Object giá trị được dựng từ các thuộc tính được chọn |
| Read model tùy chỉnh | Kết quả truy vấn được thiết kế riêng cho màn hình hoặc báo cáo |

Projection phù hợp khi ứng dụng cần đọc một phần dữ liệu. Các thao tác nghiệp vụ ghi vẫn nên tải aggregate root và gọi hành vi domain để bảo vệ invariant.

## 2. Closed projection

Một interface projection là **closed projection** khi các accessor khai báo của nó tương ứng trực tiếp với các thuộc tính của aggregate root.

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();
}
~~~

Các phương thức getter ánh xạ đến `firstName` và `lastName` của `Person`. Spring Data biết chính xác projection cần những thuộc tính nào.

Closed projection giúp Spring Data có khả năng tối ưu query execution vì tập thuộc tính cần thiết đã được xác định. Mức độ tối ưu cụ thể phụ thuộc module và đường thực thi truy vấn; không nên mặc định mọi phương thức Spring Data JDBC đều chắc chắn phát sinh một câu SELECT chỉ chứa đúng các cột getter. Khi tối ưu SQL là yêu cầu quan trọng, hãy kiểm tra statement thực tế.

### 2.1. Dùng default method để tính giá trị trình bày

Một closed projection vẫn có thể có giá trị tính toán nếu logic chỉ dựa trên những accessor đã khai báo:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

`getFullName()` không cần một thuộc tính `fullName` trong entity. Default method gọi hai getter đã biết và ghép kết quả.

Đây thường là lựa chọn gọn cho phép tính đơn giản:

- Ghép tên và họ.
- Tạo nhãn từ hai thuộc tính.
- Chuẩn hóa cách hiển thị một giá trị đã có.
- Trả về một giá trị mặc định dựa trên getter.

Vì các thuộc tính phụ thuộc vẫn được khai báo rõ, Spring Data vẫn có thể xác định tập dữ liệu cần thiết cho projection.

## 3. Open projection và biểu thức @Value

Một interface projection trở thành **open projection** khi accessor sử dụng `@Value` để tính giá trị bằng SpEL.

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

Trong biểu thức:

- `target` là object domain đứng sau projection.
- `target.firstName` đọc thuộc tính `firstName`.
- `target.lastName` đọc thuộc tính `lastName`.
- Kết quả được trả về như giá trị của `getDisplayName()`.

`displayName` không cần là cột database. Nó được tính khi accessor projection được gọi.

### 3.1. Vì sao open projection không thể tối ưu thuộc tính như closed projection?

Với closed projection, Spring Data biết chính xác các getter yêu cầu những thuộc tính nào.

Với open projection, expression có thể truy cập bất kỳ thuộc tính nào của `target`. Hôm nay biểu thức chỉ đọc `firstName` và `lastName`; sau đó có thể được đổi để đọc `email`, `address` hoặc một thuộc tính khác.

Do không thể xác định trước mọi phụ thuộc, Spring Data không thể áp dụng tối ưu hóa query execution dựa trên một tập thuộc tính hẹp như closed projection.

Hệ quả:

1. Ứng dụng có thể phải đọc nhiều thuộc tính hơn màn hình thực sự cần.
2. Object đích có thể được materialize với dữ liệu rộng hơn dự kiến.
3. Các thành phần aggregate được ánh xạ có thể phát sinh chi phí đọc riêng theo cơ chế Spring Data JDBC.
4. SpEL được đánh giá khi accessor open projection được gọi.

Vì vậy, open projection thường phù hợp với phép tính trình bày nhỏ trên dữ liệu đã có, không phải công cụ thay thế SQL projection hoặc DTO query cho mọi danh sách lớn.

## 4. Dùng target và args trong SpEL

`target` đại diện object đích. Ngoài ra, các tham số được truyền vào phương thức projection có thể được truy cập thông qua mảng `args`.

~~~java
public interface PersonGreetingView {

    String getFirstName();

    @Value("#{args[0] + ' ' + target.firstName + '!'}")
    String getGreeting(String prefix);
}
~~~

Cách gọi:

~~~java
PersonGreetingView view = ...;

String greeting = view.getGreeting("Xin chào");
~~~

Khi đó `args[0]` là chuỗi `"Xin chào"`, còn `target.firstName` lấy tên từ object đích.

Có thể dùng tham số để thay đổi cách trình bày mà không phải tạo nhiều interface projection. Tuy nhiên, hãy giữ expression ngắn và dễ đọc. Nếu phải xử lý nhiều nhánh, quy tắc định dạng hoặc nghiệp vụ phức tạp, nên chuyển logic sang Java method hoặc một Spring bean.

## 5. Gọi Spring bean từ open projection

Với phép tính phức tạp hơn, Spring Data cho phép expression gọi một bean trong ApplicationContext.

Bean:

~~~java
import org.springframework.stereotype.Component;

@Component
public class PersonPresentation {

    public String displayName(Person person) {
        if (person.getFirstName() == null) {
            return person.getLastName();
        }

        if (person.getLastName() == null) {
            return person.getFirstName();
        }

        return person.getFirstName() + " " + person.getLastName();
    }
}
~~~

Projection:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayView {

    @Value("#{@personPresentation.displayName(target)}")
    String getDisplayName();
}
~~~

`@personPresentation` tham chiếu bean có tên `personPresentation`; `target` được truyền vào phương thức Java.

Cách này có một số lợi ích:

- Logic được viết bằng Java, có thể refactor và kiểm thử trực tiếp.
- Expression chỉ còn một lời gọi ngắn.
- Có thể tái sử dụng logic trình bày.
- Có thể áp dụng quy tắc null hoặc định dạng rõ ràng.

Bean nên thực hiện phép tính nhẹ, có tính xác định và không có side effect. Tránh gọi repository, HTTP client hoặc dịch vụ bên ngoài từ phương thức được projection gọi. Nếu một danh sách 500 người gọi bean và mỗi lần bean truy vấn database, ứng dụng có thể tạo thêm 500 truy vấn và biến phép tính trình bày thành N+1.

## 6. Default method hay SpEL?

Cả default method và SpEL đều có thể tạo thuộc tính tính toán. Hãy chọn theo độ phức tạp và phạm vi phụ thuộc.

| Tiêu chí | Default method | Open projection với SpEL |
|---|---|---|
| Dữ liệu đầu vào | Các getter projection đã khai báo | Có thể truy cập toàn bộ `target` |
| Kiểu logic | Java | Expression dạng chuỗi |
| Kiểm tra khi biên dịch | Tốt hơn | Thuộc tính/biểu thức không được kiểm tra đầy đủ bởi Java compiler |
| Tính linh hoạt | Vừa đủ cho logic đơn giản | Linh hoạt hơn, hỗ trợ `args` và bean |
| Khả năng tối ưu thuộc tính | Có thể giữ closed projection nếu chỉ dùng getter đã khai báo | Không thể tối ưu như closed projection |
| Bảo trì | Dễ đọc khi logic ngắn | Dễ khó đọc nếu expression dài |

Ví dụ, nếu chỉ ghép tên:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Nếu logic cần một formatter dùng chung, có thể dùng bean. Nếu biểu thức chỉ là một phép ghép ngắn và có phụ thuộc rõ, default method thường dễ bảo trì hơn.

Không nên viết toàn bộ quy tắc nghiệp vụ trong SpEL. Projection là lớp biểu diễn dữ liệu đọc; domain rule nên nằm trong domain/service phù hợp.

## 7. DTO projection: không cần proxy

Ngoài interface projection, Spring Data hỗ trợ class-based projection, thường được triển khai bằng DTO hoặc Java record.

~~~java
public record PersonCard(
        UUID id,
        String firstName,
        String lastName
) {
    public String displayName() {
        return firstName + " " + lastName;
    }
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<PersonCard> findByLastName(String lastName);
}
~~~

Khác với interface projection, Spring Data không tạo proxy cho DTO. Nó dựng object từ constructor của DTO.

Các điểm cần nhớ:

- Constructor cần có các tham số tương ứng với thuộc tính projection.
- Java record phù hợp vì constructor canonical và thuộc tính bất biến.
- Nếu class có nhiều constructor, dùng `@PersistenceCreator` để chỉ constructor cần dùng khi cần thiết.
- Class-based projection không hỗ trợ nested projection theo cùng cách interface projection.
- Việc giảm cột được tải phụ thuộc khả năng tối ưu của module và truy vấn.

DTO thường phù hợp khi hình dạng dữ liệu trả về ổn định, đặc biệt cho API response hoặc read model. Phép tính đơn giản có thể nằm trong method của record; nếu cần phép tính dựa trên SQL, cân nhắc custom query trả DTO với alias phù hợp.

## 8. Dynamic projection

Có thể chọn kiểu projection tại thời điểm gọi repository bằng tham số `Class<T>`.

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    <T> List<T> findByLastName(
            String lastName,
            Class<T> projectionType
    );
}
~~~

Cách dùng:

~~~java
List<Person> entities =
        repository.findByLastName("Nguyen", Person.class);

List<PersonNameView> names =
        repository.findByLastName("Nguyen", PersonNameView.class);

List<PersonCard> cards =
        repository.findByLastName("Nguyen", PersonCard.class);
~~~

Dynamic projection hữu ích khi nhiều use case cần các view khác nhau nhưng cùng điều kiện tìm kiếm.

Có một lưu ý: Spring Data kiểm tra tham số `Class` để xác định nó có phải dynamic projection parameter không. Nếu kiểu generic của tham số khớp kiểu generic trong return type, tham số Class đó được dùng để chọn projection và không còn là query parameter thông thường hoặc biến SpEL. Nếu cần truyền một Class như dữ liệu query, dùng kiểu generic khác, chẳng hạn `Class<?>`.

Không nên tạo quá nhiều projection type cho những khác biệt rất nhỏ. Mỗi view mới đều thêm một hợp đồng cần bảo trì.

## 9. Projection lồng nhau và nullable wrapper

Interface projection có thể dùng đệ quy cho thuộc tính lồng nhau. Ví dụ một người có địa chỉ:

~~~java
public interface AddressView {

    String getCity();
}

public interface PersonAddressView {

    String getFirstName();

    AddressView getAddress();
}
~~~

Khi gọi `getAddress()`, Spring Data lấy giá trị thuộc tính `address` từ object đích và bọc nó trong projection tương ứng.

Việc dùng nested projection giúp giới hạn view ở cấp thuộc tính. Tuy nhiên, nó không đồng nghĩa một quan hệ entity sẽ được tải lazy theo yêu cầu như một số ORM khác. Spring Data JDBC đọc aggregate theo mapping của nó; hãy quan sát SQL và số lượng dữ liệu thực tế nếu nested property là collection hoặc entity được lưu ở bảng riêng.

Projection getter cũng có thể dùng wrapper nullable như `Optional<T>`:

~~~java
public interface PersonContactView {

    Optional<String> getEmail();
}
~~~

Nếu giá trị underlying là `null`, getter trả `Optional.empty()`; nếu có giá trị, getter trả `Optional.of(value)`.

Nullable wrapper giúp API đọc diễn đạt rõ thuộc tính có thể vắng mặt. Nó không thay thế validation cho dữ liệu bắt buộc trong domain.

## 10. Projection không tự biến biểu thức thành SQL

Cần phân biệt **SpEL trong projection** và **SpEL trong câu query**.

### 10.1. Projection expression

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getDisplayName();
~~~

Expression này chạy trong ứng dụng khi projection accessor được gọi. Nó sử dụng object `target` và tính giá trị hiển thị. Nó không được gửi như biểu thức SQL đến database.

### 10.2. SpEL dùng làm bind parameter trong @Query

~~~java
@Query("""
    SELECT *
    FROM people
    WHERE id = :#{#person.id}
    """)
Person findForPerson(PersonRef person);
~~~

Ở đây `:#{#person.id}` được đánh giá để lấy giá trị bind parameter. SQL được thực thi với tham số tương ứng.

Spring Data JDBC còn hỗ trợ expression thay thế một phần câu query, ví dụ tên bảng động:

~~~java
@Query("SELECT * FROM #{tableName} WHERE id = :id")
Person findByDynamicTable(Long id);
~~~

Dạng expression thay thế SQL này được đánh giá trước lần thực thi đầu tiên; nó phù hợp với trường hợp cần tên bảng động và phải kiểm soát chặt giá trị được phép dùng.

Hai trường hợp có mục đích khác nhau:

| Biểu thức | Thời điểm và nơi xử lý | Tác dụng |
|---|---|---|
| `@Value("#{target...}")` trên projection | Khi gọi accessor trong ứng dụng | Tạo giá trị trình bày |
| `:#{...}` trong `@Query` | Khi chuẩn bị query parameter | Tạo giá trị bind |
| `#{tableName}` trong SQL | Trước lần query đầu tiên | Thay thế một phần câu SQL |

Không dùng projection expression để thay thế một phép lọc, join, group hoặc aggregate mà database có thể thực hiện hiệu quả hơn.

## 11. Chi phí xử lý của open projection

Open projection mang lại tính linh hoạt, nhưng có nhiều tầng chi phí.

### 11.1. Chi phí đọc dữ liệu từ database

Vì SpEL có thể truy cập bất kỳ thuộc tính nào của `target`, Spring Data không thể giới hạn query execution dựa trên một danh sách getter cố định như closed projection.

Điều này có thể làm tăng:

- Số cột được đọc.
- Dung lượng ResultSet.
- Chi phí chuyển đổi JDBC value sang Java object.
- Chi phí dựng aggregate và các thành phần được ánh xạ.
- Bộ nhớ cần giữ cho danh sách kết quả.

Nếu projection chỉ cần hai thuộc tính, open projection có thể đọc rộng hơn mức cần thiết. Closed projection hoặc DTO phù hợp hơn khi mục tiêu chính là giảm dữ liệu.

### 11.2. Chi phí tạo proxy

Interface projection cần một proxy để chuyển các method call đến object đích hoặc xử lý biểu thức. Proxy giúp tách hợp đồng view khỏi entity, nhưng vẫn có chi phí tạo object và dispatch method.

Với vài bản ghi, chi phí này thường không đáng kể. Với danh sách rất lớn, nên đo tổng thời gian materialization, số object và bộ nhớ thay vì chỉ nhìn thời gian SQL.

DTO projection tránh proxy và dựng object trực tiếp từ constructor. Điều đó không đảm bảo DTO luôn nhanh hơn trong mọi trường hợp, nhưng làm đường mapping đơn giản và rõ ràng hơn.

### 11.3. Chi phí đánh giá SpEL

Khi ứng dụng gọi một accessor được gắn `@Value`, Spring đánh giá expression để tạo giá trị trả về.

Nếu serializer hoặc code ứng dụng gọi cùng getter nhiều lần, không nên giả định giá trị đã được cache. Expression càng dài, truy cập càng sâu hoặc gọi bean càng nhiều thì chi phí càng lớn.

Ví dụ đơn giản:

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getDisplayName();
~~~

thường nhẹ hơn một expression có nhiều nhánh, gọi nhiều method và truy cập nhiều object lồng nhau.

### 11.4. Chi phí gọi bean

Bean có thể làm expression dễ bảo trì hơn, nhưng method được gọi vẫn tiêu tốn CPU và có thể tạo thêm I/O nếu viết không cẩn thận.

Tránh những mẫu sau:

- Mỗi lần gọi getter lại truy vấn repository.
- Gọi HTTP service để bổ sung một thuộc tính cho từng projection.
- Đọc file hoặc truy cập hệ thống ngoài từ expression.
- Thực hiện nghiệp vụ có side effect trong method trình bày.
- Lặp lại cùng một phép tính nặng cho từng getter.

Nếu cần dữ liệu từ bảng khác, hãy thiết kế query/read model lấy dữ liệu theo batch hoặc join phù hợp. Nếu cần gọi dịch vụ ngoài, nên xử lý ở application/service layer theo một quy trình có kiểm soát.

### 11.5. Chi phí từ aggregate có collection

Một open projection có thể tham chiếu đến thuộc tính của root hoặc các thành phần con. Trong Spring Data JDBC, không nên giả định truy cập một getter lồng nhau sẽ kích hoạt lazy loading theo kiểu JPA. Aggregate loading và SQL tải collection phụ thuộc mapping, phương thức truy vấn và chiến lược của Spring Data JDBC.

Nếu biểu thức đọc một collection để tính tổng hoặc tạo chuỗi, ứng dụng có thể phải giữ toàn bộ các phần tử đó trong bộ nhớ. Với danh sách nhiều aggregate, chi phí đọc collection có thể lớn hơn nhiều chi phí SpEL.

## 12. Ví dụ so sánh ba cách tạo display name

Giả sử `Person` có `firstName`, `lastName` và `email`.

### Cách A — Closed projection với default method

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Các phụ thuộc được khai báo rõ. Đây là lựa chọn tốt cho phép tính nhỏ.

### Cách B — Open projection với SpEL

~~~java
public interface PersonDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();

    @Value("#{target.email != null ? target.email : 'No email'}")
    String getEmailLabel();
}
~~~

Dễ viết và linh hoạt. Nhưng expression có thể truy cập toàn bộ target, vì vậy không có cùng khả năng tối ưu truy vấn như closed projection.

### Cách C — DTO

~~~java
public record PersonCard(
        UUID id,
        String firstName,
        String lastName,
        String email
) {
    public String displayName() {
        return firstName + " " + lastName;
    }
}
~~~

DTO rõ hình dạng dữ liệu và không cần proxy. Phù hợp cho response API hoặc read model có cấu trúc ổn định.

| Tiêu chí | Closed + default | Open + SpEL | DTO |
|---|---|---|---|
| Cách tính | Java default method | SpEL | Java constructor/method |
| Truy cập target | Qua getter đã khai báo | Có thể đọc mọi thuộc tính | Không có target proxy |
| Query optimization | Có thể giới hạn theo getter khi module hỗ trợ | Không thể tối ưu dựa trên tập getter hẹp | Có thể tối ưu theo constructor properties khi store hỗ trợ |
| Proxy | Có | Có | Không |
| Logic phức tạp | Nên chuyển ra bean/service | Nên chuyển ra bean | Nên chuyển ra mapper/service |
| Dễ kiểm tra khi biên dịch | Tốt | Expression là chuỗi | Tốt |

## 13. Lựa chọn projection theo mục đích

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Chỉ cần vài thuộc tính có sẵn | Closed interface projection |
| Ghép vài thuộc tính đã khai báo | Closed projection với default method |
| Cần expression nhỏ, linh hoạt dựa trên target | Open projection với `@Value` |
| Logic trình bày nhiều bước nhưng vẫn nhẹ | Gọi bean từ SpEL hoặc xử lý ở service |
| API response ổn định, không cần proxy | DTO/record projection |
| Nhiều view khác nhau cho cùng điều kiện tìm kiếm | Dynamic projection |
| Cần tổng hợp, join, lọc hoặc tính toán lớn | SQL/read model/DTO query |
| Cần sửa dữ liệu và bảo vệ invariant | Tải aggregate root, gọi domain method, lưu repository |

Một open projection không phải lúc nào cũng sai. Nó là công cụ hợp lý khi expression nhỏ và việc đọc target đã nằm trong ngân sách hiệu năng. Vấn đề xuất hiện khi dùng expression tùy tiện cho danh sách lớn hoặc biến accessor thành điểm gọi các dịch vụ ngoài.

## 14. Những giới hạn khi dùng projection trong repository

### 14.1. Không biến phương thức CRUD gốc thành projection bằng cách đổi return type

Các phương thức có sẵn của `CrudRepository`, như `findById`, vẫn được xử lý theo hợp đồng cơ sở khi bị override. Chỉ đổi return type sang interface projection không bảo đảm Spring Data sẽ tạo query method mới.

Hãy khai báo một query method riêng, ví dụ:

~~~java
List<PersonNameView> findByLastName(String lastName);
~~~

### 14.2. Tên accessor phải khớp property

Với closed projection:

~~~java
String getFirstName();
String getLastName();
~~~

các property phải tồn tại trên aggregate root với tên tương ứng. Nếu đổi tên property domain, hãy cập nhật projection cùng các method query liên quan.

### 14.3. Class-based projection cần constructor xác định

DTO projection cần một constructor để Spring Data xác định các input properties. Nếu class có nhiều constructor, đánh dấu constructor cần dùng bằng `@PersistenceCreator` khi cần.

### 14.4. Nested projection không đồng nghĩa nested SQL projection

Projection lồng nhau mô tả cách bọc property thành view khác. Nó không bảo đảm database chỉ đọc đúng một phần bảng con hoặc tự sinh một JOIN duy nhất. Với Spring Data JDBC, hãy xét riêng cách aggregate mapping và collection loading hoạt động.

### 14.5. Kiểm tra đường query đang dùng

Derived query, custom `@Query`, DTO và projection interface có thể đi qua các đường mapping khác nhau. Nếu chọn projection vì mục tiêu giảm cột hoặc giảm SQL, hãy đo đúng repository method mà ứng dụng sẽ gọi.

## 15. Kiểm tra chi phí bằng SQL log và benchmark

Đừng kết luận một projection nhanh chỉ vì interface của nó có ít getter. Hãy so sánh các cách trả về bằng cùng dữ liệu và cùng điều kiện truy vấn.

Có thể bật log trong `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

TRACE có thể hiển thị bind parameters; chỉ bật trong môi trường kiểm tra và tránh ghi thông tin nhạy cảm vào log production.

### 15.1. So sánh các phương thức

Chuẩn bị các repository method:

~~~java
List<Person> findByLastName(String lastName);

List<PersonNameView> findNamesByLastName(String lastName);

List<PersonDisplayView> findDisplayByLastName(String lastName);

List<PersonCard> findCardsByLastName(String lastName);
~~~

Tạo fixture có cùng số người, cùng độ dài chuỗi và cùng phân bố giá trị. Sau đó đo:

- Số câu SQL.
- Các cột được SELECT.
- Số hàng ResultSet.
- Thời gian database.
- Thời gian dựng object/proxy.
- Thời gian gọi getter và serialize response.
- Heap allocation và garbage collection khi danh sách lớn.

Các tên method là ví dụ; phần sau `By` vẫn phải mô tả property hợp lệ mà Spring Data có thể phân tích.

### 15.2. Không benchmark chỉ bằng một getter

Nếu chỉ đo thời gian gọi repository rồi bỏ projection chưa được sử dụng, phép đo có thể bỏ sót chi phí đánh giá expression. Ngược lại, nếu gọi cùng getter hàng chục lần, bạn có thể đo một mẫu truy cập không giống serialization thực tế.

Benchmark nên mô phỏng luồng sử dụng thật:

~~~text
Repository query
      |
      v
Nhận projection result
      |
      v
Đọc các getter mà API thực sự dùng
      |
      v
Serialize response
      |
      v
Đo tổng thời gian và allocation
~~~

Lặp lại với số bản ghi đại diện, chẳng hạn 10, 100, 1.000 và mức tải dự kiến. Đo nhiều lần sau warm-up và so sánh median/percentile thay vì dựa vào một lần chạy.

## 16. Quy trình chọn và triển khai open projection

Khi muốn thêm một thuộc tính biểu diễn bằng expression:

**Bước 1 — Xác định dữ liệu đầu vào.** Liệt kê các property mà giá trị mới cần dùng.

**Bước 2 — Kiểm tra có thể dùng closed projection không.** Nếu phép tính chỉ dùng getter đã khai báo, ưu tiên default method.

**Bước 3 — Xem expression có thật sự cần SpEL không.** Nếu có, giữ biểu thức ngắn, thuần và không có side effect.

**Bước 4 — Tách logic phức tạp.** Dùng Spring bean hoặc service method để giữ code Java dễ kiểm thử; không truy vấn database từ từng getter.

**Bước 5 — Xem quy mô dữ liệu.** Open projection trên danh sách lớn có thể tăng chi phí đọc thuộc tính, materialization và evaluation.

**Bước 6 — Chọn DTO/read query nếu cần tối ưu dữ liệu.** Nếu màn hình chỉ cần một số cột, hãy để truy vấn chọn đúng dữ liệu đó.

**Bước 7 — Kiểm tra SQL và serialization.** Xác nhận cột, statement, query count và các getter được gọi thực tế.

**Bước 8 — Kiểm thử null và dữ liệu bất thường.** Expression phải xử lý các thuộc tính có thể null; lỗi SpEL có thể chỉ xuất hiện khi getter được gọi.

~~~text
Yêu cầu hiển thị giá trị mới
          |
          v
Các thuộc tính đầu vào đã rõ?
          |
          v
Chỉ dùng getter đã khai báo?
        /   \
      Có     Không
      |        |
      v        v
Closed +    Cần SpEL thực sự?
default       |
method       / \
           Có   Không
           |      |
           v      v
       Open @Value  DTO/mapper/service
           |
           v
    Expression ngắn, thuần?
           |
           v
    Đo SQL + proxy + evaluation
           |
           v
    Đủ hiệu năng cho quy mô dữ liệu?
~~~

## 17. Bài tập tự suy luận

**Tình huống A — Ghép họ tên**

Projection cần ghép `firstName` và `lastName`. Có nhất thiết dùng `@Value` không?

**Gợi ý:** Không. Closed projection với default method là lựa chọn đơn giản và giữ phụ thuộc rõ ràng.

**Tình huống B — Expression đọc nhiều thuộc tính**

Một open projection có `@Value("#{target.firstName + target.lastName + target.email}")`. Spring Data có thể chắc chắn chỉ chọn ba cột này không?

**Gợi ý:** Không thể tối ưu query execution dựa trên tập thuộc tính hẹp như closed projection vì expression có thể truy cập bất kỳ thuộc tính nào của target.

**Tình huống C — Gọi repository từ bean**

Một bean được gọi bởi projection expression và truy vấn thêm database cho từng người. Với 500 kết quả, điều gì có thể xảy ra?

**Gợi ý:** 500 lần gọi bean có thể tạo thêm 500 truy vấn, dẫn tới N+1. Hãy batch dữ liệu hoặc thiết kế read query phù hợp.

**Tình huống D — API response ổn định**

Một endpoint luôn trả `id`, `firstName`, `lastName` và `email`. Lựa chọn nào dễ kiểm soát hợp đồng dữ liệu?

**Gợi ý:** DTO/record projection thường rõ ràng vì không cần proxy và constructor xác định các trường.

**Tình huống E — Projection có địa chỉ lồng nhau**

Projection trả `AddressView getAddress()`. Có thể mặc định Spring Data JDBC chỉ tải địa chỉ khi gọi getter không?

**Gợi ý:** Không nên giả định lazy loading kiểu JPA. Kiểm tra cách property được ánh xạ và SQL thực tế.

**Tình huống F — Expression dùng args**

Projection có `getGreeting(String prefix)` và expression đọc `args[0]`. Giá trị này đến từ đâu?

**Gợi ý:** Từ tham số truyền vào chính lời gọi accessor projection.

## 18. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| Projection | View giới hạn trên dữ liệu aggregate |
| Interface projection | Proxy chuyển accessor đến object đích |
| Closed projection | Getter tương ứng property đã biết |
| Open projection | Dùng `@Value` và SpEL để tính giá trị |
| `target` | Object domain đứng sau projection |
| `args` | Tham số của lời gọi projection method |
| Default method | Logic Java đơn giản dựa trên getter đã khai báo |
| Spring bean trong SpEL | Tách logic phức tạp khỏi expression |
| DTO projection | Constructor-based object, không tạo proxy |
| Dynamic projection | Chọn kiểu kết quả bằng `Class<T>` |
| Nullable wrapper | Biểu diễn thuộc tính có thể null |
| Query optimization | Closed projection có thể giúp giới hạn dữ liệu khi module hỗ trợ |
| Processing cost | SQL, mapping, proxy, expression, object graph và serialization |

**Open projection nên được dùng cho phép tính trình bày nhỏ, thuần và dễ hiểu.** Nếu chỉ ghép các getter, ưu tiên default method trong closed projection. Nếu cần một hợp đồng dữ liệu ổn định, chọn DTO. Khi dùng SpEL, nhớ rằng `target` có thể truy cập toàn bộ aggregate nên Spring Data không thể tối ưu truy vấn dựa trên một tập thuộc tính hẹp. Hãy đo cả SQL, chi phí dựng object và chi phí expression trên quy mô dữ liệu thực tế.

## Tài liệu tham khảo

- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html): interface projections, closed/open projections, `@Value`, default methods, nullable wrappers, DTO và dynamic projections.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods, SpEL trong query, named parameters và mapping.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): cách Spring Data JDBC ánh xạ aggregate và các thuộc tính liên quan.

