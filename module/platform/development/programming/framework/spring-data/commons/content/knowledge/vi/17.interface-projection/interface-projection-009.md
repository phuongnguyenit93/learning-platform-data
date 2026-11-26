# Vì sao đổi kiểu trả về của phương thức CRUD cơ sở không tự tạo projection?

## 1. Hai câu hỏi phải được trả lời riêng

Một interface projection mô tả góc nhìn đọc dữ liệu. Chẳng hạn, thay vì lấy toàn bộ `Customer`, ứng dụng chỉ muốn nhận `firstName` và `lastName`.

Tuy nhiên, việc viết tên projection vào kiểu trả về chưa đủ để biến mọi phương thức repository thành một truy vấn projection. Cần kiểm tra hai vấn đề khác nhau:

1. **Java có cho phép chữ ký đó không?** Khi kế thừa một phương thức, kiểu trả về phải tuân thủ quy tắc override và generic.
2. **Spring Data sẽ thực thi phương thức qua đường nào?** Một phương thức CRUD cơ sở vẫn có thể được chuyển tới implementation CRUD, thay vì được xử lý như query method tạo projection.

Quy tắc cốt lõi của Spring Data Commons là: **khai báo lại phương thức cơ sở với kiểu trả về khác không tự chuyển nó thành query method dùng projection**. Phương thức cơ sở được xử lý theo hợp đồng CRUD của domain type. Muốn có projection, cần một đường truy vấn hoặc phép chuyển đổi được định nghĩa rõ ràng.

Một số mô-đun hỗ trợ dùng annotation query để đưa một khai báo tương ứng sang đường xử lý query. Đây là khả năng riêng cần kiểm tra, không phải hệ quả tự động của việc đổi return type.

## 2. Mô hình dữ liệu dùng trong bài

Giả sử domain type `Customer` đã được mapping với kho dữ liệu:

| Thuộc tính | Kiểu minh họa | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh của Customer |
| `firstName` | `String` | Tên gọi |
| `lastName` | `String` | Họ |
| `email` | `String` | Địa chỉ liên hệ |
| `status` | `String` | Trạng thái |

Projection đọc tên:

```java
public interface CustomerName {
    String getFirstName();
    String getLastName();
}
```

Trong các ví dụ, `Customer` không implement `CustomerName`. Interface này là kiểu kết quả đọc riêng, do cơ chế projection thích hợp tạo ra.

Dù entity có hai getter cùng tên, nó không tự implement một interface Java chỉ vì các phương thức trông giống nhau. Java không coi hai kiểu là tương thích chỉ dựa trên việc chúng có cùng tập getter.

Các ví dụ repository giả định mô-đun và phiên bản đang dùng hỗ trợ dạng query được nêu. Mapping domain, cấu hình repository và dependency phải phù hợp với kho dữ liệu thực tế.

## 3. Phương thức CRUD cơ sở có hợp đồng riêng

Với repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Các phương thức cơ sở làm việc với domain type `Customer` và kiểu định danh `Long`.

| Phương thức cơ sở | Hình dạng kết quả hoặc tác dụng |
| --- | --- |
| `findById(Long id)` | `Optional<Customer>` |
| `findAll()` | `Iterable<Customer>` theo hợp đồng CrudRepository |
| `save(S entity)` với `S extends Customer` | Lưu và trả về entity theo hợp đồng phương thức |
| `existsById(Long id)` | Trả trạng thái tồn tại |
| `count()` | Trả số lượng |
| `deleteById(Long id)` | Thực hiện thao tác xóa |

Implementation cụ thể do mô-đun cung cấp, chẳng hạn implementation repository cho JPA hoặc cho một kho tài liệu. Việc khai báo một interface projection trong ứng dụng không tự sửa implementation CRUD đó.

Đặc biệt, `save`, `deleteById`, `count` hay `existsById` không trở thành các thao tác đọc những trường tùy chọn của projection chỉ vì sửa kiểu trả về ở interface.

## 4. Trường hợp thứ nhất: Java không cho override kiểu trả về

Đoạn sau không phải một cách khai báo projection hợp lệ:

```java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface IncorrectCustomerRepository
        extends CrudRepository<Customer, Long> {

    // Không biên dịch: kiểu trả về không tương thích với phương thức cha.
    Optional<CustomerName> findById(Long id);
}
```

Phương thức kế thừa trả `Optional<Customer>`, còn khai báo mới trả `Optional<CustomerName>`. Hai kiểu generic này không có quan hệ subtype cần thiết để override.

Ngay cả khi một domain type thực sự implement `CustomerName`, `Optional<Customer>` vẫn không tự trở thành subtype của `Optional<CustomerName>`. Generic như Optional không tự có tính hiệp biến theo quan hệ subtype của phần tử.

Quy tắc tương tự áp dụng khi thử đổi `findAll()` sang collection của projection:

```java
// Cũng không phải override hợp lệ của Iterable<Customer> findAll().
List<CustomerName> findAll();
```

`List<CustomerName>` không phải subtype của `Iterable<Customer>`. Annotation Spring Data không thể làm một chữ ký vi phạm quy tắc Java trở thành hợp lệ.

### 4.1. Đổi collection bao ngoài có thể hợp lệ nhưng vẫn là entity

Về mặt Java, kiểu trả về có thể được thu hẹp nếu vẫn tương thích:

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Override
    List<Customer> findAll();
}
```

`List<Customer>` là một subtype của `Iterable<Customer>`. Việc triển khai và thích nghi kiểu collection vẫn phải phù hợp với mô-đun đang dùng, nhưng điểm quan trọng là **phần tử vẫn là Customer**.

Thay đổi lớp bao collection không đồng nghĩa tạo interface projection. Hình dạng collection và hình dạng từng phần tử là hai phần riêng của hợp đồng kết quả.

## 5. Trường hợp thứ hai: biên dịch được nhưng vẫn khớp CRUD cơ sở

Có thể người viết tránh xung đột Java bằng cách chỉ kế thừa marker interface `Repository`:

```java
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface MisleadingCustomerReads
        extends Repository<Customer, Long> {

    Optional<CustomerName> findById(Long id);
}
```

Vì `Repository` không trực tiếp khai báo `findById`, trình biên dịch không phải kiểm tra override với `Optional<Customer>`. Điều đó không có nghĩa Spring Data sẽ tự coi phương thức này là một derived query projection mới.

Spring Data hỗ trợ chọn lọc các phương thức của repository cơ sở. Khi khai báo một phương thức khớp hợp đồng cơ sở như `findById`, hạ tầng có thể chuyển lời gọi tới implementation CRUD tương ứng. Kiểu trả về khác không tự thay đổi đường thực thi đó.

Nếu đường CRUD trả Customer, việc viết generic `Optional<CustomerName>` không biến đối tượng bên trong thành một proxy CustomerName.

Ví dụ nơi vấn đề có thể lộ ra:

```java
CustomerName name = repository.findById(42L)
        .orElseThrow(() -> new IllegalStateException("Customer not found"));
```

Nếu đối tượng thực tế bên trong là Customer không implement CustomerName, việc sử dụng nó như CustomerName có thể gây `ClassCastException`. Chi tiết phát hiện lỗi còn tùy mô-đun, kiểm tra metadata và implementation; không nên dựa vào việc một trường hợp biên dịch hoặc khởi động được để coi chữ ký đó là projection hợp lệ.

### 5.1. Vì sao Optional có thể làm lỗi xuất hiện muộn?

Ở runtime, lớp bao vẫn chỉ là Optional. Generic không tự thêm một bước chuyển đổi entity sang projection vào bên trong Optional.

Những thao tác chỉ hỏi `isPresent()` có thể chưa cần lấy phần tử dưới kiểu CustomerName, nên chưa bộc lộ lỗi kiểu. Khi lấy phần tử và gọi accessor qua kiểu projection, sự không tương thích mới có thể xuất hiện.

Điều đó giải thích vì sao kiểm tra “phương thức trả một Optional không rỗng” chưa đủ để xác nhận projection.

## 6. Return type không tự chọn lại đường thực thi

Có thể hình dung hai đường khác nhau:

```text
Phương thức khớp CRUD cơ sở
    → implementation CRUD của mô-đun
    → kết quả theo hợp đồng entity của phương thức cơ sở

Query method có hỗ trợ projection
    → phân tích hoặc thực thi truy vấn
    → xử lý kết quả query theo kiểu projection được khai báo
```

Ở đường query, kiểu trả về là thông tin quan trọng cho cơ chế projection. Nhưng thông tin đó không tự làm mọi phương thức cơ sở đổi sang đường query.

Java cũng không cho overload hai phương thức chỉ bằng cách đổi return type. Hai khai báo cùng tên và cùng danh sách tham số không trở thành hai API khác nhau chỉ vì một bên trả Customer còn bên kia trả CustomerName.

Cần phân biệt ba việc:

- **Khai báo kiểu:** điều người viết nói caller sẽ nhận.
- **Định tuyến phương thức:** implementation hoặc query nào thực sự chạy.
- **Chuyển đổi kết quả:** có thực sự tạo projection hay chỉ trả lại đối tượng nguồn.

Một chữ ký đáng tin cậy cần ba việc này phù hợp với nhau.

## 7. Cách thông thường: tạo query method có tên riêng

Thay vì đổi kiểu trả về của `findById`, hãy giữ phương thức CRUD đúng hợp đồng và thêm một query method riêng:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<CustomerName> findProjectedById(Long id);

    List<CustomerName>
    findProjectedByStatusOrderByLastNameAscFirstNameAscIdAsc(String status);
}
```

Ở đây:

- `findById(Long)` kế thừa từ CrudRepository tiếp tục trả `Optional<Customer>`.
- `findProjectedById(Long)` là phương thức riêng, không phải khai báo lại phương thức CRUD cùng tên.
- `findProjectedByStatus...` là query đọc nhiều kết quả theo trạng thái.

Trong quy tắc đặt tên derived query, phần mô tả giữa `find` và `By`, như `Projected`, giúp tạo tên phương thức riêng. **Từ Projected không phải annotation hay công tắc đặc biệt để bật projection.** Hình dạng projection đến từ return type và cơ chế query được hỗ trợ.

Ví dụ sử dụng:

```java
Optional<Customer> entity = repository.findById(42L);
Optional<CustomerName> view = repository.findProjectedById(42L);
```

Hai phương thức thể hiện hai mục đích đọc khác nhau. Điều này cũng làm mã gọi dễ hiểu hơn: nơi cần entity dùng hợp đồng entity, nơi cần góc nhìn đọc dùng query projection.

### 7.1. Tên query vẫn phải khớp thuộc tính domain

`findProjectedById` phân tích phần điều kiện `Id` theo domain model. Trong ví dụ, thuộc tính định danh thực sự tên là `id`, nên tên này phù hợp.

Nếu thuộc tính định danh tên là `customerId`, một query method có thể cần tên như:

```java
Optional<CustomerName> findProjectedByCustomerId(Long customerId);
```

Không chỉ đổi tên phương thức rồi bỏ qua việc kiểm tra property path. Tên mới phải là query hợp lệ của mô-đun đang dùng.

## 8. Tên CRUD dành riêng và thuộc tính có tên id

`findById` của repository cơ sở có ý nghĩa tìm theo định danh được metadata của domain xác định. Ý nghĩa này không nhất thiết trùng với việc tìm một thuộc tính thường có tên `id`.

Giả sử một model có:

- Thuộc tính `pk` là định danh theo mapping của mô-đun.
- Thuộc tính `id` là một giá trị nghiệp vụ khác.

Khi đó cần phân biệt:

| Phương thức | Ý nghĩa cần hiểu |
| --- | --- |
| `findById(value)` theo hợp đồng cơ sở | Tìm theo định danh `pk` |
| `findProjectedById(value)` theo derived query | Tìm theo thuộc tính domain tên `id` |
| `findProjectedByPk(value)` theo derived query | Tìm theo thuộc tính `pk` |

Bảng giả định mô-đun hỗ trợ các derived query tương ứng. Nó cho thấy việc đổi tên để tránh phương thức cơ sở cần đi cùng kiểm tra ý nghĩa điều kiện.

Nếu mô hình có định danh phức hợp hoặc property path lồng nhau, phải xác định đúng cấu trúc domain và kiểu tham số thay vì suy từ tên `findById` quen thuộc.

## 9. Chỉ kế thừa Repository khi muốn một giao diện đọc nhỏ

Nếu một thành phần chỉ cần một query projection, có thể khai báo một interface hẹp:

```java
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface CustomerNameReads
        extends Repository<Customer, Long> {

    Optional<CustomerName> findProjectedById(Long id);
}
```

Cách này không công khai toàn bộ CRUD trong interface đó. Tuy nhiên, yếu tố tránh nhầm lẫn ở đây vẫn là phương thức có tên query riêng phù hợp, không phải chỉ vì interface cha là Repository.

Chỉ kế thừa Repository rồi đặt lại `findById` với return type khác vẫn gặp vấn đề định tuyến phương thức cơ sở đã phân tích ở trên.

Tương tự, không nên coi `@RepositoryDefinition` hoặc một cách khai báo metadata tương đương là cơ chế tự biến base method thành projection. Cần nhìn cả hợp đồng domain, phương thức đã khai báo và đường thực thi của mô-đun.

## 10. Ngoại lệ cần kiểm tra: annotation query của mô-đun

Một số mô-đun cho phép annotation query làm cho khai báo tương ứng được xử lý như query method, thay vì đi theo đường CRUD cơ sở. Khi đó projection có thể hoạt động theo cơ chế query đó.

Đây là một khả năng của mô-đun. Spring Data Commons không cung cấp một annotation query dùng chung có cùng ngôn ngữ cho mọi kho dữ liệu.

### 10.1. Ví dụ riêng cho Spring Data JPA

Giả sử `Customer` là JPA entity có entity name `Customer`, có định danh `Long` ở thuộc tính `id`, và dự án hỗ trợ interface projection từ query tương ứng:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface CustomerExplicitReads
        extends Repository<Customer, Long> {

    @Query("select c.firstName as firstName, "
         + "c.lastName as lastName "
         + "from Customer c where c.id = :id")
    Optional<CustomerName> findById(@Param("id") Long id);
}
```

Trong ví dụ này, yếu tố quyết định là annotation `org.springframework.data.jpa.repository.Query` và đường xử lý query của JPA, không phải việc Optional chứa tên một interface khác.

Các alias `firstName` và `lastName` thể hiện hình dạng kết quả cần cho accessor của projection. Query, alias và mapping vẫn phải được kiểm chứng trong phiên bản đang dùng.

### 10.2. Annotation không vượt qua quy tắc Java

Nếu cùng chữ ký trên được đặt vào interface kế thừa `CrudRepository<Customer, Long>`, xung đột giữa `Optional<Customer>` và `Optional<CustomerName>` vẫn là vấn đề của trình biên dịch.

`@Query` không làm kiểu generic không tương thích trở thành một override hợp lệ. Ví dụ dùng marker Repository để không kế thừa trực tiếp khai báo có kiểu trả về xung đột ở mức Java.

### 10.3. Không chuyển nguyên ví dụ sang mô-đun khác

Một kho tài liệu có thể có annotation Query riêng, ngôn ngữ query khác và cơ chế ánh xạ khác. Một mô-đun khác có thể không hỗ trợ thay đường xử lý của phương thức cơ sở theo cùng cách.

Trước khi dựa vào ngoại lệ này, cần xác nhận:

1. Annotation thuộc đúng mô-đun.
2. Phiên bản hỗ trợ trường hợp phương thức đang khai báo.
3. Query thực sự tạo được hình dạng projection.
4. Khai báo vẫn hợp lệ theo Java.

Trong thiết kế thông thường, một tên query riêng như `findProjectedById` vẫn dễ đọc và ít gây nhầm giữa CRUD với query projection hơn.

## 11. Phương án khác: giữ CRUD và chuyển thành DTO tường minh

Không phải mọi nhu cầu “chỉ trả tên” đều yêu cầu query projection. Có thể đọc entity bằng CRUD rồi chuyển sang một DTO riêng:

```java
public final class CustomerNameDto {

    private final String firstName;
    private final String lastName;

    public CustomerNameDto(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }
}
```

Trong service có repository CRUD:

```java
public Optional<CustomerNameDto> readName(Long id) {
    return repository.findById(id)
            .map(customer -> new CustomerNameDto(
                    customer.getFirstName(),
                    customer.getLastName()));
}
```

Đây là phép chuyển đổi thật sự: tạo một đối tượng DTO từ dữ liệu của entity. Nó khác với ép kiểu Customer sang CustomerName.

Tuy nhiên, query CRUD đã được thực hiện theo hợp đồng lấy entity. DTO chỉ chứa hai trường không chứng minh database chỉ đọc hai trường. Nếu mục tiêu là giảm dữ liệu lấy từ kho lưu trữ, cần dùng đường query có hỗ trợ projection và kiểm tra hiệu quả thực tế.

Khi mapping DTO cần truy cập quan hệ lazy, vẫn phải bảo đảm phạm vi truy cập dữ liệu phù hợp. Hình dạng DTO không tự kéo dài transaction hoặc session.

### 11.1. Tạo proxy thủ công cũng là một bước riêng

Nếu dùng ProjectionFactory để tạo interface projection từ một entity đã tải, đó là một thao tác tường minh ở tầng ứng dụng. Nó không làm lời gọi `findById` trước đó biến thành một query chỉ lấy các trường projection.

Cần phân biệt “đối tượng trả cho caller có dạng projection” với “truy vấn được thực thi như một query projection”. Hai điều này có thể cùng tồn tại nhưng không đồng nghĩa.

## 12. Dynamic projection cũng cần query method phù hợp

Khi mô-đun hỗ trợ dynamic projection, có thể khai báo một phương thức riêng:

```java
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface CustomerFlexibleReads
        extends Repository<Customer, Long> {

    <R> Optional<R> findProjectedById(Long id, Class<R> projectionType);
}
```

Sử dụng:

```java
Optional<CustomerName> name =
        repository.findProjectedById(42L, CustomerName.class);

Optional<Customer> customer =
        repository.findProjectedById(42L, Customer.class);
```

Phương thức này có tên và danh sách tham số riêng, đồng thời khai báo tham số kiểu projection theo cơ chế được hỗ trợ. Nó không chỉ sửa generic của base method `findById(Long)`.

Không thay đổi tùy ý một phương thức thành generic rồi coi framework sẽ tự suy kiểu kết quả theo phép gán của caller. Dynamic projection là một hợp đồng cụ thể, không phải hệ quả tự động của type erasure hoặc type inference trong Java.

## 13. Những cách không tạo ra phép chuyển đổi

### 13.1. Ép kiểu

```java
// Chỉ là ép kiểu, không tạo projection.
CustomerName name = (CustomerName) customer;
```

Nếu Customer không implement CustomerName, ép kiểu có thể thất bại. Nếu entity thực sự implement interface đó thì phép gán có thể hợp lệ, nhưng đối tượng vẫn là entity; không có bằng chứng về việc query đã được tối ưu theo projection.

### 13.2. Dùng raw type hoặc bỏ qua cảnh báo generic

Raw Optional, raw List hoặc `@SuppressWarnings("unchecked")` chỉ làm trình biên dịch bớt kiểm tra hoặc bớt cảnh báo. Chúng không thêm bước ánh xạ các phần tử.

Một collection chứa Customer không tự thành collection chứa proxy CustomerName chỉ vì được gán qua một kiểu generic khác.

### 13.3. Đổi interface CRUD bao ngoài

Chuyển giữa các interface CRUD có kiểu collection khác nhau không tự tạo projection. Cần kiểm tra domain type của repository và kiểu phần tử mà phương thức cơ sở xử lý.

Tương tự, đổi `Iterable<Customer>` thành `List<Customer>` không biến Customer thành một góc nhìn chỉ có vài trường.

### 13.4. Thêm default method vào projection

Default method có thể tính giá trị từ các accessor của một projection đã được tạo đúng. Nó không điều khiển việc base method chọn entity hay projection.

Nếu đường CRUD đã trả một Customer không tương thích với CustomerName, việc CustomerName có thêm `getDisplayName()` không giải quyết được vấn đề nguồn kết quả.

## 14. So sánh các phương án

| Phương án | Kết quả cần hiểu | Có tự tạo query projection không? |
| --- | --- | --- |
| Giữ `findById` của CrudRepository | Đọc entity theo hợp đồng cơ sở | Không |
| Đổi return type không tương thích khi kế thừa CRUD | Vi phạm quy tắc override của Java | Không; có thể không biên dịch |
| Khai báo lại `findById` trên marker Repository với return type projection | Có thể vẫn được chuyển tới implementation cơ sở | Không chỉ nhờ return type |
| Thêm `findProjectedById` trả interface projection | Query method riêng nếu mô-đun hỗ trợ | Có cơ chế projection theo đường query |
| Dùng query annotation phù hợp trên khai báo hợp lệ | Query tường minh theo mô-đun | Có thể, tùy hỗ trợ và mapping |
| Gọi CRUD rồi tạo DTO | Entity được tải, sau đó chuyển đổi trong ứng dụng | Không thay đổi query đã chạy |
| Dùng dynamic projection đúng hợp đồng | Query riêng chọn kiểu kết quả tại lời gọi | Có thể, theo hỗ trợ của mô-đun |
| Viết implementation hoặc fragment tùy chỉnh | Hành vi do implementation định nghĩa | Phải được thực hiện tường minh |

Bảng này giúp tách mục tiêu “đúng kiểu đối tượng caller nhận” khỏi mục tiêu “thay đổi dữ liệu mà truy vấn lấy”. Một giải pháp cần được đánh giá theo mục tiêu thực tế, không chỉ theo hình dạng chữ ký.

## 15. Cách kiểm tra trong một dự án thực tế

Nên kiểm tra theo thứ tự từ hợp đồng Java đến hành vi truy cập dữ liệu:

1. Xác định domain type và ID type của repository.
2. Liệt kê phương thức kế thừa từ interface cơ sở.
3. Xác định phương thức đang xét có khớp base method không.
4. Kiểm tra kiểu trả về có hợp lệ theo quy tắc override và generic không.
5. Xác định đường xử lý: CRUD cơ sở, derived query, query tường minh hay custom implementation.
6. Gọi phương thức với dữ liệu có thật và sử dụng các accessor của kết quả.
7. Kiểm tra cả trường hợp không có dữ liệu và điều kiện không duy nhất nếu query yêu cầu một kết quả.
8. Quan sát query thực tế nếu mục tiêu liên quan tới số trường hoặc lượng dữ liệu đọc.

Các ca đáng chú ý:

| Ca | Điều cần bảo vệ |
| --- | --- |
| CRUD `findById` với bản ghi tồn tại | Nhận đúng entity theo hợp đồng |
| Query `findProjectedById` với bản ghi tồn tại | Dùng được accessor của projection và nhận đúng giá trị |
| Không có bản ghi | Nhận Optional rỗng theo hợp đồng |
| Nhiều thuộc tính tên giống nhau hoặc alias sai | Phát hiện mapping không đúng |
| Model có định danh không tên `id` | Query mới tìm đúng thuộc tính mong muốn |
| Dùng annotation query đặc thù | Annotation và đường query thực sự được mô-đun hỗ trợ |
| Entity được chuyển sang DTO | DTO đúng nhưng không kết luận sai về hình dạng query |
| Trả kết quả qua collection hoặc Optional | Kiểm tra phần tử, không chỉ kiểm tra lớp bao hoặc kích thước |

Không cần dựa vào tên class proxy nội bộ để xác nhận hợp đồng. Quan trọng hơn là caller có dùng được kiểu công khai đã khai báo, dữ liệu đúng và query đi theo đường mong muốn.

Một ví dụ tạo projection từ Map trong bộ nhớ có thể kiểm tra accessor của interface, nhưng không chứng minh phương thức `findById` thật trong repository đã được định tuyến thành query projection.

## 16. Các lỗi thường gặp và cách định hướng

| Hiện tượng | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Báo lỗi return type khi biên dịch | Override generic không tương thích | So chữ ký với CrudRepository sau khi thay domain type |
| Marker Repository biên dịch nhưng dùng kết quả bị ClassCastException | Base method trả entity thay vì projection | Kiểm tra tên phương thức và đường định tuyến |
| Optional có dữ liệu nhưng accessor lỗi | Chỉ kiểm tra lớp bao, chưa kiểm tra phần tử | Lấy phần tử và sử dụng hợp đồng projection |
| Query method mới báo thiếu thuộc tính | Đổi tên chưa đúng domain property | Kiểm tra phần sau By và metadata định danh |
| Thêm Query annotation vẫn không biên dịch | Annotation không sửa được quy tắc Java | Loại xung đột chữ ký trước khi xét framework |
| Copy annotation từ mô-đun khác không hoạt động | Sai annotation hoặc ngôn ngữ query | Xác định đúng mô-đun sở hữu query engine |
| DTO chỉ có hai trường nhưng query vẫn tải entity | Chuyển DTO sau CRUD | Phân biệt mapping ứng dụng và query projection |
| Entity implement interface nên lỗi kiểu biến mất | Tương thích kiểu nhưng chưa có query projection | Kiểm tra mục tiêu tối ưu và truy vấn thực tế |

## 17. Tình huống tự đánh giá

### A. Đổi Optional trong interface kế thừa CRUD

Một repository kế thừa `CrudRepository<Customer, Long>` rồi khai báo `Optional<CustomerName> findById(Long id)`.

Giải thích vì sao trình biên dịch có thể bác bỏ khai báo trước khi Spring Data chạy. Liên hệ với tính bất biến kiểu generic của Optional.

### B. Chỉ kế thừa marker Repository

Nhóm bỏ CrudRepository, giữ nguyên phương thức `findById` trả CustomerName và cho rằng đã tránh được phương thức cơ sở.

Phân biệt việc tránh xung đột Java với cơ chế chọn lọc base method của Spring Data. Đề xuất một query method có tên riêng.

### C. Dữ liệu có pk và id

Metadata xác định `pk` là định danh, còn `id` là mã nghiệp vụ. Nhóm đổi `findById` thành `findProjectedById`.

Giải thích vì sao điều kiện tìm kiếm có thể đã thay đổi ý nghĩa. Chọn tên query đúng nếu mục tiêu vẫn là định danh pk.

### D. Dùng Query annotation

Một nhóm JPA muốn giữ tên `findById` và dùng query tường minh trả interface projection.

Nêu những điều kiện về Java, annotation, query và mapping cần được đáp ứng. Giải thích vì sao không được coi ví dụ đó là quy tắc chung cho mọi mô-đun Spring Data.

### E. Ép kiểu sau khi đọc entity

Một service lấy Customer từ CRUD rồi ép sang CustomerName vì hai kiểu có cùng getter.

Giải thích vì sao phép ép kiểu không tạo proxy projection. Đề xuất một phép chuyển đổi tường minh và nêu giới hạn của nó đối với dữ liệu đã đọc từ database.

### F. Chỉ kiểm tra Optional không rỗng

Một ca kiểm tra gọi phương thức có kiểu khai báo `Optional<CustomerName>` và chỉ xác nhận `isPresent()` trả true.

Chỉ ra vì sao ca này chưa chứng minh phần tử có đúng hợp đồng projection. Nêu hành vi công khai cần kiểm tra thêm.

## 18. Quy tắc áp dụng

Giữ phương thức CRUD cơ sở đúng với hợp đồng domain type. Khi cần một interface projection, hãy tạo query method riêng có tên và property path hợp lệ, hoặc dùng một cơ chế query tường minh đã được mô-đun xác nhận hỗ trợ.

Nếu chọn đọc entity rồi chuyển đổi ở service, hãy mô tả đúng đó là bước mapping trong ứng dụng. Kiểu trả về chỉ có ý nghĩa khi phù hợp cả với quy tắc Java, đường thực thi của Spring Data và đối tượng thực tế được trả cho caller.