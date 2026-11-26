# DTO dựa trên constructor và tên tham số

## 1. DTO projection được tạo từ dữ liệu truy vấn

Một màn hình danh sách khách hàng có thể chỉ cần mã định danh và họ tên. Repository có thể trả một DTO dành riêng cho nhu cầu đó, thay vì đưa toàn bộ entity cho bên gọi.

Với class-based projection, framework hoặc cơ chế truy vấn của store tạo đối tượng DTO qua constructor. Khi store tối ưu việc chọn trường theo kiểu DTO, tên tham số của constructor giúp xác định các thuộc tính cần đọc. Xem [Spring Data Commons — Class-based Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.dtos).

Hai câu hỏi phải được trả lời riêng:

1. Cần lấy những thuộc tính nào từ dữ liệu nguồn?
2. Các giá trị đã lấy được truyền vào constructor theo thứ tự và kiểu nào?

Trong derived query, metadata constructor có vai trò quan trọng ở câu hỏi đầu tiên. Trong một constructor expression JPQL viết rõ bằng `new`, danh sách biểu thức trong query quyết định các đối số của lời gọi tạo DTO.

Bài học này tập trung vào hợp đồng constructor và tên tham số. Phần minh họa JPQL dành riêng cho JPA; cách tạo DTO ở store khác phải được đối chiếu với module tương ứng.

## 2. Ví dụ DTO có một constructor rõ ràng

### 2.1. Mô hình domain cần đọc

Giả sử ứng dụng đã ánh xạ domain type `Customer` với các property:

| Property domain | Kiểu | Vai trò |
|---|---|---|
| `id` | `Long` | Mã khách hàng |
| `firstName` | `String` | Tên |
| `lastName` | `String` | Họ |
| `email` | `String` | Thông tin liên hệ |
| `active` | `boolean` | Trạng thái hoạt động |

DTO cho màn hình danh sách chỉ nhận ba giá trị đầu. Các ví dụ giả định Java và bộ Spring Data của ứng dụng hỗ trợ các API được dùng, cùng một store hỗ trợ đường projection tương ứng.

### 2.2. DTO dùng class thông thường

```java
package example.readmodel;

public final class CustomerSummary {

    private final Long id;
    private final String firstName;
    private final String lastName;

    public CustomerSummary(
            Long id,
            String firstName,
            String lastName) {

        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getDisplayName() {
        String first = firstName == null ? "" : firstName;
        String last = lastName == null ? "" : lastName;

        return (last + " " + first).trim();
    }
}
```

Constructor công khai cung cấp đủ đầu vào cho hình dạng DTO. Các field `final` được gán tại lúc tạo đối tượng; ví dụ không cần setter hoặc constructor không đối số.

`getDisplayName()` chỉ tính nhãn từ dữ liệu đã có. Nó không làm phát sinh yêu cầu đọc một property `displayName` từ database vì không phải tham số constructor được dùng để chọn đầu vào.

DTO này không được khai báo là entity và không nằm trong hệ phân cấp kiểu của `Customer`. Nó biểu diễn một kết quả đọc riêng.

### 2.3. Repository trả DTO

```java
import java.util.List;

import example.readmodel.CustomerSummary;
import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    List<CustomerSummary> findByActiveTrueOrderByIdAsc();
}
```

Query method chọn các khách hàng đang hoạt động. Kiểu phần tử trả về là `CustomerSummary`, còn domain type của repository vẫn là `Customer`.

Với một hàng dữ liệu:

```text
id        = 41
firstName = An
lastName  = Nguyễn
active    = true
```

việc tạo DTO có ý nghĩa tương đương:

```java
new CustomerSummary(41L, "An", "Nguyễn");
```

Đây là mô tả kết quả mong đợi, không phải khẳng định mọi store đều sử dụng cùng một lớp tạo đối tượng nội bộ.

## 3. Tên tham số constructor là một phần của hợp đồng đọc

### 3.1. Tên field và getter không tự sửa tên tham số

Trong DTO ở trên, các tham số `id`, `firstName`, `lastName` khớp property domain.

Nếu đổi constructor thành:

```java
public CustomerSummary(
        Long id,
        String givenName,
        String familyName) {

    this.id = id;
    this.firstName = givenName;
    this.lastName = familyName;
}
```

Java vẫn hiểu cách gán field. Nhưng khi đường projection dùng tên tham số để xác định thuộc tính cần đọc, `givenName` và `familyName` không còn khớp mô hình `Customer` đã nêu.

Việc field vẫn tên `firstName` hoặc getter vẫn tên `getFirstName()` không tự biến tham số `givenName` thành một tên tương đương. Framework không đọc thân constructor để suy ngược ý nghĩa của từng phép gán.

Với derived DTO projection trong ví dụ, hãy giữ tham số mang tên property cần đọc:

```java
CustomerSummary(Long id, String firstName, String lastName)
```

### 3.2. Tên property domain khác tên cột

Giả sử mapping JPA có:

```java
@Column(name = "first_name")
private String firstName;
```

Tên tham số DTO vẫn là `firstName`, vì đó là property Java của domain. `first_name` là tên cột mà mapping persistence xử lý.

| Thành phần | Tên đúng trong ví dụ |
|---|---|
| Property domain | `firstName` |
| Tham số DTO phục vụ discovery theo property | `firstName` |
| Cột database | `first_name` |
| Getter DTO cho bên gọi | `getFirstName()` |

Đổi tham số thành `first_name` chỉ để giống schema có thể làm sai hợp đồng theo tên property.

Với query native hoặc mapping kết quả riêng, tên cột và alias thuộc một hợp đồng khác. Phải xác định đang dùng đường chuyển đổi nào trước khi áp dụng quy tắc đặt tên.

### 3.3. @Param không đặt tên tham số constructor

`@Param` trên phương thức repository phục vụ bind tham số query, chẳng hạn `:lastName`. Nó không thay thế metadata tên tham số của DTO.

Tương tự, annotation phục vụ JSON không mặc nhiên hướng dẫn query engine cách chọn property cho DTO. Mỗi lớp metadata có mục đích riêng:

| Metadata | Trách nhiệm |
|---|---|
| Tên tham số constructor DTO | Mô tả đầu vào dùng để tạo DTO |
| `@PersistenceCreator` | Chỉ ra constructor cần dùng khi có nhiều lựa chọn theo cơ chế hỗ trợ |
| `@Param` ở repository | Bind đối số phương thức vào query parameter |
| Mapping entity như `@Column` | Liên hệ property với dữ liệu lưu trữ |
| Cấu hình serialization | Quyết định hình dạng dữ liệu khi truyền ra ngoài |

## 4. Tên trong source phải còn khả dụng ở runtime

### 4.1. Vai trò của -parameters

Nhìn thấy `firstName` trong mã nguồn chưa chứng minh reflection ở runtime cũng đọc được tên đó. Đối với class Java thông thường, cần bảo đảm pipeline biên dịch lưu metadata tên tham số.

Tùy chọn `javac -parameters` lưu tên tham số constructor và phương thức vào class file để reflection có thể đọc. Xem [javac — -parameters](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html#standard-options).

Một lệnh biên dịch minh họa cho DTO độc lập:

```text
javac -parameters -d out src/example/readmodel/CustomerSummary.java
```

Trong dự án thực tế, cấu hình compiler tương đương phải được áp dụng tại module tạo ra DTO. Nếu DTO nằm trong một thư viện JAR đã biên dịch thiếu metadata, thêm tùy chọn cho module sử dụng JAR không tự sửa class file bên trong thư viện đó.

Không dùng việc IDE hiển thị tên biến hoặc có debug information làm bằng chứng duy nhất rằng cơ chế discovery ở phiên bản framework đang dùng sẽ đọc được tên constructor.

### 4.2. Quan sát metadata bằng reflection

Đoạn Java dưới đây minh họa cách kiểm tra constructor của class DTO:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

import example.readmodel.CustomerSummary;

Constructor<CustomerSummary> constructor =
        CustomerSummary.class.getDeclaredConstructor(
                Long.class, String.class, String.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(
            parameter.getName()
            + " / namePresent="
            + parameter.isNamePresent());
}
```

Với metadata tên tham số được giữ đúng cho constructor đã khai báo, kết quả mong đợi là:

```text
id / namePresent=true
firstName / namePresent=true
lastName / namePresent=true
```

Nếu metadata không có, reflection có thể cung cấp tên tổng hợp như `arg0`. `Parameter.isNamePresent()` giúp phân biệt tên thật được lưu trong class file với tên tổng hợp. Xem [Java Parameter API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html).

Đây là ví dụ chẩn đoán, không phải kết quả chạy trên artifact của một dự án cụ thể. Metadata đúng cũng mới xác nhận một phần; còn phải kiểm tra property domain và query thực tế.

### 4.3. Discovery theo tên khác lời gọi constructor thông thường

Java có thể gọi `new CustomerSummary(...)` dựa trên chữ ký kiểu và vị trí đối số mà không cần dùng tên tham số tại runtime.

Do đó, việc đoạn mã tạo DTO thủ công chạy được không chứng minh framework sẽ xác định được các property cần chọn cho derived projection. Hai thao tác sử dụng thông tin khác nhau.

## 5. Nhiều constructor cần một lựa chọn rõ ràng

DTO projection nên có một constructor phục vụ hình dạng dữ liệu cần đọc. Nếu class có nhiều constructor, tài liệu Commons hướng dẫn đánh dấu constructor dự định dùng bằng `@PersistenceCreator`.

Ví dụ mở rộng class `CustomerSummary` bằng một constructor tiện ích, đồng thời đánh dấu constructor đầy đủ:

```java
import org.springframework.data.annotation.PersistenceCreator;

// Các constructor đặt bên trong CustomerSummary;
// các field và getter giữ như ví dụ trước.
public CustomerSummary(String firstName, String lastName) {
    this(null, firstName, lastName);
}

@PersistenceCreator
public CustomerSummary(
        Long id,
        String firstName,
        String lastName) {

    this.id = id;
    this.firstName = firstName;
    this.lastName = lastName;
}
```

Constructor hai tham số phục vụ bên gọi chủ động tạo DTO khi chưa có ID. Constructor ba tham số được chỉ ra cho đường projection.

Khi áp dụng biến thể này, thay constructor ba tham số cũ bằng constructor đã gắn annotation; không giữ hai khai báo trùng chữ ký.

`@PersistenceCreator` giải quyết việc chọn constructor. Nó không:

- Đổi tên `givenName` thành property `firstName`.
- Tự tạo metadata đã bị bỏ khỏi class file.
- Thêm một property còn thiếu vào domain.
- Sửa thứ tự biểu thức trong query JPQL đã viết rõ.

Quy tắc materialize domain object của từng store có thể rộng hơn quy tắc DTO projection này. Tài liệu object mapping chung cũng nêu phạm vi của nó là các module có mapper riêng; JPA ủy quyền mapping cho provider. Không chuyển nguyên thuật toán tạo entity của một module sang mọi query DTO. Xem [Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html).

## 6. Record diễn đạt gọn hợp đồng constructor

Nếu phiên bản Java của dự án hỗ trợ record, có thể thay class `CustomerSummary` bằng:

```java
package example.readmodel;

public record CustomerSummary(
        Long id,
        String firstName,
        String lastName) {
}
```

Đây là một định nghĩa thay thế, không đặt cùng class cùng tên trong một package.

Các component của record thể hiện rõ ba dữ liệu đầu vào. Record có canonical constructor tương ứng và các accessor:

```java
summary.id();
summary.firstName();
summary.lastName();
```

Khi đổi từ class có getter sang record, bên gọi cần dùng đúng API của record. Tên component vẫn phải phù hợp với hợp đồng projection theo property.

Record còn có `equals`, `hashCode` và `toString` được tạo từ các component. Tính bất biến của record là bất biến nông; component tham chiếu đến một collection mutable vẫn cần thiết kế riêng nếu muốn cố định nội dung. Xem [Java Record API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

Đối với các component `Long` và `String` của ví dụ, record là một mô hình kết quả đọc gọn. Nó không tự tạo mapping đúng cho một query không khớp hoặc làm mọi store hỗ trợ cùng một đường constructor projection.

## 7. Tên, thứ tự và kiểu có vai trò khác nhau theo query

### 7.1. Derived query dựa trên metadata DTO

Trong mẫu:

```java
List<CustomerSummary> findByActiveTrueOrderByIdAsc();
```

metadata của constructor giúp đường query xác định các property như `id`, `firstName`, `lastName`. Store tạo kết quả phù hợp để dựng DTO.

Điều kiện lọc `active = true` không bắt buộc DTO phải có tham số `active`. Property dùng để lọc và property trả về có thể khác nhau.

### 7.2. JPQL constructor expression truyền đối số theo vị trí

Với JPA, có thể viết rõ việc tạo DTO trong JPQL:

```java
import java.util.List;

import example.readmodel.CustomerSummary;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Phương thức đặt trong CustomerRepository.
@Query("""
        select new example.readmodel.CustomerSummary(
                c.id, c.firstName, c.lastName)
        from Customer c
        where c.lastName = :lastName
        order by c.id
        """)
List<CustomerSummary> findSummaryByLastName(
        @Param("lastName") String lastName);
```

Tên lớp DTO trong biểu thức `new` là tên đầy đủ gồm package. Thứ tự `c.id, c.firstName, c.lastName` tương ứng với constructor `Long, String, String`.

Nếu vô tình viết:

```text
new example.readmodel.CustomerSummary(
    c.id, c.lastName, c.firstName)
```

hai đối số chuỗi đã bị đảo. Chữ ký vẫn có dạng `Long, String, String`, nên kiểm tra kiểu có thể không phát hiện được ý nghĩa bị sai. Kết quả có thể đặt họ vào field tên và ngược lại.

Tên tham số constructor không biến JPQL constructor expression thành lời gọi có named argument. Khi query đã liệt kê đối số, phải kiểm tra vị trí và ý nghĩa của từng biểu thức.

Không đặt alias `as firstName` bên trong các đối số của constructor expression JPQL. Quy tắc alias ở interface projection không được sao chép nguyên sang dạng `select new`. Xem [Spring Data JPA — JPQL Queries](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa.queries).

### 7.3. Query rewriting và native query cần đúng phiên bản

Spring Data JPA có khả năng viết lại một số query thành constructor expression. Khả năng đó có điều kiện theo dạng query và phiên bản; không mặc định mọi câu `select` đều được biến đổi thành DTO đúng.

Với native query, phải đánh giá cách ánh xạ kết quả của phiên bản JPA module đang dùng. Nếu kết quả không khớp trực tiếp với constructor, có thể cần result-set mapping hoặc phần chuyển đổi riêng.

| Đường thực thi | Điểm cần đối chiếu |
|---|---|
| Derived DTO projection | Constructor được chọn, tên tham số và property domain |
| JPQL `select new` | Tên lớp đầy đủ, thứ tự biểu thức và kiểu constructor |
| Native query | Thứ tự, kiểu dữ liệu thực tế và mapping kết quả được hỗ trợ |
| Store có object mapper riêng | Quy tắc tạo DTO và metadata của module đó |
| Tạo DTO thủ công trong service | Mã ánh xạ do ứng dụng viết |

Không dùng sự thành công của một hàng query để kết luận mọi DTO có cùng số field sẽ tương thích.

## 8. Null, phép tính và phạm vi dữ liệu

### 8.1. Kiểu tham số phải tiếp nhận được giá trị thực tế

Nếu một biểu thức query có thể trả null, tham số primitive như `long` hoặc `boolean` không biểu diễn được trạng thái đó. Cần quyết định dùng kiểu tham chiếu phù hợp, xử lý giá trị trong query hoặc đặt invariant có căn cứ.

Ví dụ, một DTO cho kết quả left join có thể cần `Long relatedId` thay vì `long relatedId` nếu không có bản ghi liên quan.

Constructor có thể kiểm tra dữ liệu, nhưng một `Objects.requireNonNull` mới thêm cũng có thể khiến những hàng dữ liệu trước đây hợp lệ không còn tạo DTO được. Điều kiện bắt buộc phải phù hợp với query và nghiệp vụ.

### 8.2. DTO không tự tính một tham số chưa được cung cấp

Nếu thêm tham số `String displayName` vào constructor, đường query theo tên property sẽ cần một cách cung cấp giá trị đó. Framework không tự suy ra phải ghép họ và tên.

Nếu chỉ cần nhãn hiển thị từ các trường đã lấy, có thể dùng phương thức tính như `getDisplayName()` trong class ban đầu. Nếu muốn tính ở database, cần một query biểu đạt phép tính và constructor phù hợp.

Tương tự, khả năng nullable wrapper trên getter của interface projection không tự chứng minh DTO constructor có tham số `Optional<String>` được bind từ scalar nullable theo cùng cơ chế.

### 8.3. DTO chỉ chứa dữ liệu đã được đưa vào

DTO projection không sử dụng proxy getter như interface projection. Không mặc định rằng một field DTO chứa interface khác sẽ tự trở thành nested projection.

Nếu cần dữ liệu nhiều cấp, hãy chọn cách query và ánh xạ được store hỗ trợ. Một phương án là lấy các scalar cần thiết rồi tạo DTO lồng trong service. Phương án khác là query constructor expression phù hợp với provider, khi đã được xác nhận.

Việc DTO có ít field cũng không chứng minh query chắc chắn có ít join hoặc ít cột. Cần quan sát đường query thực tế, nhất là khi có quan hệ, aggregation hoặc query khai báo sẵn.

## 9. Các tình huống thực hành để hiểu đúng hợp đồng

Các tình huống sau dành cho việc áp dụng vào dự án đích. Chúng là kỳ vọng cần xác minh, không phải kết quả đã chạy trên một bộ thư viện cụ thể.

| Tình huống | Điều cần quan sát |
|---|---|
| DTO có một constructor, tên tham số khớp domain | Đọc được đúng `id`, `firstName`, `lastName` |
| DTO class biên dịch có metadata tên | Reflection thấy tên thật thay vì chỉ tên tổng hợp |
| Constructor đổi `firstName` thành `givenName` | Phát hiện thay đổi hợp đồng property ở đường discovery theo tên |
| Có hai constructor | Chọn rõ constructor projection bằng cơ chế được hỗ trợ |
| Thêm constructor không đối số | Không kỳ vọng việc thêm đó tự hoàn thiện mapping DTO |
| Cột là `first_name`, property là `firstName` | Giữ tên tham số theo property ở derived projection |
| JPQL đảo hai biểu thức cùng kiểu String | Phát hiện giá trị bị đảo dù không sai chữ ký kiểu |
| Query có giá trị null | Constructor và kiểu tham số xử lý theo invariant đã chọn |
| Đổi class sang record | Metadata, API bên gọi và mapping vẫn đúng |
| DTO được đóng gói trong module khác | Kiểm tra artifact thực tế của module chứa DTO |
| Chuyển store hoặc nâng phiên bản | Xác nhận lại khả năng constructor projection và dữ liệu được lấy |

Một dữ liệu mẫu nên dùng họ và tên khác nhau, chẳng hạn `firstName = "An"`, `lastName = "Nguyễn"`. Nếu hai giá trị giống nhau, lỗi đảo thứ tự có thể bị che khuất.

Khi chẩn đoán, nên đi theo quan hệ phụ thuộc: constructor nào được chọn, tên và kiểu tham số là gì, domain có property tương ứng không, rồi query cung cấp giá trị theo cách nào. Cách đọc này giúp phân biệt lỗi metadata với lỗi query và lỗi nghiệp vụ.

## 10. Hợp đồng DTO cần được giữ khi refactor

Đối với constructor projection, tên tham số có thể ảnh hưởng trực tiếp đến dữ liệu được yêu cầu. Vì vậy, đổi tên tham số không phải lúc nào cũng là thay đổi cục bộ vô hại.

Một DTO dễ bảo trì có một hình dạng đầu vào rõ ràng, metadata khả dụng và quy tắc null phù hợp. Repository thể hiện đúng domain type; query khai báo giữ đúng thứ tự và kiểu đối số; bên gọi dùng DTO như một mô hình kết quả đọc.

Khi những phần đó thống nhất, class hoặc record DTO giúp giới hạn và diễn đạt dữ liệu cần dùng mà không buộc bên gọi phụ thuộc vào toàn bộ entity.
