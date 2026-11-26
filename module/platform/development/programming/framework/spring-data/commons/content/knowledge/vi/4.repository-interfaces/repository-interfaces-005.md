# Giao diện cơ sở generic và @NoRepositoryBean

## 1. Vì sao cần một repository cơ sở của ứng dụng?

Một ứng dụng thường có nhiều repository với những nhu cầu giống nhau:

- Lưu một aggregate.
- Đọc theo định danh.
- Kiểm tra sự tồn tại.
- Chuyển trường hợp không tìm thấy thành một lỗi thống nhất.
- Giới hạn những thao tác được công khai cho tầng nghiệp vụ.

Nếu từng repository tự khai báo lại những hợp đồng đó, chữ ký và quy ước rất dễ lệch nhau. Một interface cơ sở generic giúp diễn đạt phần chung ở một nơi, rồi để repository cụ thể gắn kiểu domain và kiểu ID.

Trong module **SPRING_DATA_COMMONS**, đây là bước nối từ các abstraction có sẵn như `Repository`, `CrudRepository` đến cách tổ chức repository của ứng dụng. Nó cũng tạo nền cho việc mở rộng truy vấn, phân trang, projection và auditing, nhưng không tự hiện thực mọi nhu cầu theo store.

Hai câu hỏi phải được trả lời riêng:

1. Interface nào chỉ dùng làm hợp đồng trung gian?
2. Interface nào đại diện cho repository cụ thể cần tạo bean?

`@NoRepositoryBean` giải quyết việc phân loại ở câu hỏi thứ nhất. Annotation này không cung cấp phần triển khai cho những phương thức mới.

## 2. Đọc đúng hai tham số generic

Một hợp đồng cơ sở có thể bắt đầu như sau:

```java
import org.springframework.data.repository.Repository;

public interface ApplicationRepository<T, ID>
        extends Repository<T, ID> {
}
```

Đây mới là hình dạng generic, chưa phải khai báo hoàn chỉnh nên dùng để quét repository. Phần tiếp theo sẽ bổ sung annotation cần thiết và các phương thức.

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu aggregate hoặc domain object mà repository quản lý | `Customer`, `Product` |
| `ID` | Kiểu định danh của domain đó | `Long`, `UUID`, `String` |

Repository cụ thể sẽ đóng các tham số:

```text
ApplicationRepository<T, ID>
        |
        +-- CustomerRepository
        |      T  = Customer
        |      ID = Long
        |
        +-- ProductRepository
               T  = Product
               ID = UUID
```

`ID` là kiểu dữ liệu, không phải tên trường và cũng không phải giá trị định danh. Việc một domain dùng `Long` không buộc mọi domain khác phải dùng `Long`.

Kiểu ID phải khớp mapping thực tế của domain trong store. Khai báo `ApplicationRepository<Customer, String>` không tự chuyển một định danh `Long` của Customer thành String.

Các ví dụ dưới đây giả định domain đã có mapping và hạ tầng repository phù hợp. Generic và annotation của Commons không tự cấu hình kết nối hoặc tạo mapping cho kho dữ liệu.

## 3. @NoRepositoryBean đánh dấu một hợp đồng trung gian

### 3.1. Khai báo hoàn chỉnh

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ApplicationRepository<T, ID>
        extends Repository<T, ID> {

    <S extends T> S save(S entity);

    Optional<T> findById(ID id);

    boolean existsById(ID id);
}
```

Annotation thuộc package:

```java
org.springframework.data.repository.NoRepositoryBean
```

Khi hạ tầng Spring Data quét repository, interface này được loại khỏi danh sách ứng viên tạo repository bean độc lập.

Lý do là `ApplicationRepository<T, ID>` chưa gắn với một domain cụ thể. Nó tồn tại để các interface khác kế thừa hợp đồng.

### 3.2. Annotation không làm gì?

`@NoRepositoryBean`:

- Không tạo implementation của `save`, `findById` hoặc phương thức tùy chỉnh.
- Không tự bật repository scanning.
- Không thay thế cấu hình JPA, MongoDB hoặc store khác.
- Không làm các repository con ngừng hoạt động.
- Không thiết lập transaction, quyền truy cập hoặc chính sách chỉ đọc.
- Không ngăn mọi cách đăng ký bean thủ công trong Spring container.

Ý nghĩa của nó nằm trong quy trình phát hiện repository của Spring Data. Không nên diễn giải annotation thành một lệnh cấm toàn cục rằng “không bao giờ được có đối tượng thực hiện interface này”.

### 3.3. Vì sao phương thức chuẩn vẫn hoạt động?

Interface trên mở rộng marker interface `Repository`, rồi công khai một tập con các chữ ký CRUD quen thuộc.

Với store hỗ trợ repository tương ứng, hạ tầng có thể chuyển các phương thức khớp hợp đồng chuẩn đến implementation repository của store. Ví dụ, Spring Data JPA có implementation cơ sở riêng cho các thao tác đó.

Điều làm các phương thức hoạt động là sự phối hợp giữa chữ ký được hỗ trợ và hạ tầng repository của store. `@NoRepositoryBean` chỉ loại interface trung gian khỏi việc tạo bean riêng.

## 4. Repository cụ thể gắn domain và ID

### 4.1. Hai repository dùng chung hợp đồng

```java
import java.util.Optional;

public interface CustomerRepository
        extends ApplicationRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

```java
import java.util.Optional;
import java.util.UUID;

public interface ProductRepository
        extends ApplicationRepository<Product, UUID> {

    Optional<Product> findBySku(String sku);
}
```

Giả định:

- `Customer` có định danh Long và thuộc tính Java `email`.
- `Product` có định danh UUID và thuộc tính Java `sku`.
- Store được chọn hỗ trợ các phương thức truy vấn này.
- Cấu hình quét bao phủ hai repository cụ thể.

Không gắn `@NoRepositoryBean` lên hai interface cụ thể nếu bạn muốn hạ tầng tạo bean cho chúng.

Annotation ở interface cơ sở không làm toàn bộ cây repository con bị loại. Hạ tầng vẫn xem xét repository cụ thể, giải quyết generic của nó và đăng ký bean theo cấu hình store.

### 4.2. Những gì người gọi nhìn thấy

| Repository | Phương thức kế thừa | Phương thức riêng |
| --- | --- | --- |
| CustomerRepository | `save(Customer)` theo hợp đồng generic, `findById(Long)`, `existsById(Long)` | `findByEmail(String)` |
| ProductRepository | `save(Product)` theo hợp đồng generic, `findById(UUID)`, `existsById(UUID)` | `findBySku(String)` |

Cột phương thức kế thừa diễn tả cách sử dụng theo domain cụ thể; chữ ký thực của `save` vẫn là `<S extends T> S save(S entity)`.

Bản thân `ApplicationRepository` không có `deleteById`, nên người gọi qua hợp đồng này không được cung cấp thao tác xóa. Đây là cách thiết kế API hẹp hơn thay vì kế thừa toàn bộ CRUD rồi nhắc người dùng tránh gọi một số phương thức.

### 4.3. Inject repository cụ thể

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Customer findCustomer(Long id) {
        return customers.findById(id)
                .orElseThrow(
                        () -> new IllegalArgumentException(
                                "Không tìm thấy khách hàng"
                        )
                );
    }
}
```

Inject theo repository cụ thể giúp biểu đạt rõ service cần làm việc với domain nào. Nếu inject một kiểu cơ sở quá rộng hoặc raw type khi có nhiều repository, việc chọn bean có thể trở nên mơ hồ.

Spring có thể dùng thông tin generic trong nhiều tình huống phân giải dependency, nhưng không nên bỏ kiểu rồi trông chờ framework tự suy ra domain từ tên biến.

## 5. Chọn kế thừa toàn bộ CRUD hay công khai một tập con

### 5.1. Kế thừa toàn bộ hợp đồng

Nếu ứng dụng thật sự muốn mọi repository cơ sở có toàn bộ CRUD:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface FullCrudRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Các repository con nhận cả lưu, đọc, đếm và các thao tác xóa được hợp đồng CRUD cung cấp.

Cách này ngắn gọn, nhưng mọi phương thức được kế thừa đều trở thành một phần API công khai. Không thể dùng một interface con để “bỏ kế thừa” một phương thức xóa đã công khai ở interface cha.

### 5.2. Công khai hợp đồng hẹp

`ApplicationRepository` ở phần trước chỉ công khai lưu, đọc theo ID và kiểm tra tồn tại. Một biến thể chỉ phục vụ đọc có thể là:

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface LookupRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    boolean existsById(ID id);
}
```

Repository cụ thể:

```java
public interface ProductLookupRepository
        extends LookupRepository<Product, java.util.UUID> {
}
```

Đây là giới hạn ở hợp đồng Java, không phải cơ chế bảo mật hay bằng chứng dữ liệu tuyệt đối không thể thay đổi. Quyền ghi của tài khoản cơ sở dữ liệu, các API khác và cơ chế quản lý entity vẫn cần được thiết kế riêng.

Ví dụ, một entity JPA được quản lý có thể bị thay đổi và được dirty checking ghi lại trong transaction phù hợp. Không có phương thức `save` trên một interface chưa đủ để vô hiệu hóa cơ chế đó.

### 5.3. Cẩn thận với chữ ký generic

Khi chọn sao chép phương thức chuẩn, giữ đúng chữ ký có chủ đích:

```java
<S extends T> S save(S entity);
```

`S` là kiểu con của `T`, cho phép kiểu trả về giữ quan hệ với kiểu đối tượng truyền vào theo hợp đồng.

Không tùy ý thay đổi chữ ký khi đang mở rộng một interface đã có phương thức generic cùng tên. Do type erasure và quy tắc override của Java, một khai báo có vẻ gần giống có thể gây xung đột thay vì tạo overload hợp lệ.

Cũng không tự đổi `Optional<T> findById(ID id)` thành một kiểu trả về khác rồi mặc định store sẽ hiểu cùng một cách. Hãy dựa vào hợp đồng mà phiên bản và store thực sự hỗ trợ.

## 6. Thêm hành vi chung bằng default method

Một hành vi có thể được viết hoàn toàn bằng các phương thức mà hợp đồng đã công khai thì phù hợp để cân nhắc default method.

Ví dụ, bổ sung vào `ApplicationRepository<T, ID>`:

```java
default T requireById(ID id) {
    if (id == null) {
        throw new IllegalArgumentException(
                "Định danh không được null"
        );
    }

    return findById(id)
            .orElseThrow(
                    () -> new java.util.NoSuchElementException(
                            "Không tìm thấy đối tượng"
                    )
            );
}
```

Sau đó service có thể gọi:

```java
Customer customer = customers.requireById(customerId);
```

### 6.1. Điều gì được tái sử dụng?

- Kiểm tra đầu vào.
- Chuyển kết quả rỗng thành loại lỗi đã thống nhất.
- Cách ghép hành vi dựa trên `findById`.

Default method đã có thân phương thức Java. Hạ tầng repository có thể thực thi nó mà không cần suy ra một truy vấn mới chỉ từ tên `requireById`.

Bên trong default method, lời gọi `findById` vẫn đi qua cơ chế repository tương ứng để đọc dữ liệu. Phần xử lý không tìm thấy nằm ở hợp đồng ứng dụng; phần truy cập kho dữ liệu do store thực hiện.

### 6.2. Không cần existsById trước findById

Một cách viết kém phù hợp là:

```text
nếu existsById(id) là false thì báo lỗi
sau đó gọi findById(id) để lấy đối tượng
```

Cách này có thể tạo hai thao tác truy cập dữ liệu và vẫn không loại bỏ tình huống dữ liệu thay đổi giữa chúng.

Nếu nhu cầu là lấy đối tượng hoặc báo không tìm thấy, dùng trực tiếp `findById` và xử lý `Optional` rõ ràng hơn.

### 6.3. Giới hạn của default method

Default method không tự cấp `EntityManager`, `MongoTemplate` hoặc driver. Nó cũng không tự tạo ranh giới transaction bao phủ mọi lời gọi mà bạn ghép bên trong.

Nếu hành vi cần phối hợp nhiều aggregate, kiểm soát tồn kho, gửi sự kiện hoặc kết hợp nhiều store, hãy cân nhắc service và ranh giới transaction thích hợp.

Ví dụ, “tạo đơn hàng rồi trừ tồn kho” không nên trở thành phương thức mặc định của mọi `ApplicationRepository<T, ID>` chỉ vì có thể gọi nhiều phương thức Java trong thân hàm.

## 7. Khai báo phương thức abstract mới không tạo ra implementation

Xét một thay đổi:

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ArchivingRepository<T, ID>
        extends Repository<T, ID> {

    void archiveById(ID id);
}
```

Interface có `@NoRepositoryBean`, nhưng chưa có logic lưu trữ cho `archiveById`.

Khi một repository cụ thể kế thừa phương thức này, hạ tầng vẫn phải tìm cách thực hiện nó. Annotation ở interface cơ sở không yêu cầu Spring Data tự hiểu “archive” là sửa một cờ, chuyển bảng hay xóa mềm.

Nếu phương thức không khớp phương thức cơ sở được hỗ trợ, không có default body, không có implementation mở rộng và không có truy vấn khai báo phù hợp, hạ tầng có thể cố phân tích nó như một phương thức truy vấn rồi thất bại.

Lỗi cụ thể và thời điểm xuất hiện phụ thuộc cấu hình, store và cách khởi tạo repository.

### 7.1. Chọn cơ chế theo loại hành vi

| Hành vi muốn bổ sung | Cơ chế nên cân nhắc |
| --- | --- |
| Ghép logic từ những phương thức repository đã có | Default method |
| Tìm theo thuộc tính mà store hỗ trợ | Derived query hoặc truy vấn khai báo theo store |
| Một nhóm truy vấn tùy chỉnh cho một số domain | Repository fragment |
| Thay đổi hành vi nền của nhiều repository trong một store | Custom base implementation và cấu hình factory tương ứng |
| Quy trình nghiệp vụ phối hợp nhiều thao tác hoặc aggregate | Service/domain service |

`@NoRepositoryBean` có thể xuất hiện trên interface cơ sở của những thiết kế này, nhưng nó không thay thế cơ chế triển khai trong cột bên phải.

### 7.2. Ví dụ hợp đồng fragment theo domain

```java
public interface CustomerStatusOperations {

    void deactivateCustomer(Long customerId);
}
```

```java
import java.util.Optional;

public interface CustomerRepository
        extends ApplicationRepository<Customer, Long>,
                CustomerStatusOperations {

    Optional<Customer> findByEmail(String email);
}
```

Thiết kế này nêu rõ thao tác trạng thái thuộc Customer. Vẫn phải cung cấp implementation fragment và cấu hình phát hiện phù hợp; chỉ hai interface trên chưa hoàn tất phần tùy chỉnh.

Theo quy ước mặc định, implementation fragment có thể mang tên `CustomerStatusOperationsImpl`. Nội dung implementation phụ thuộc store và mô hình Customer.

Không đưa `deactivateCustomer` vào base generic cho Product và mọi domain khác chỉ để giảm một lần khai báo.

### 7.3. Custom base implementation là một bước khác

Với JPA, một custom base implementation thường mở rộng lớp cơ sở JPA phù hợp, nhận metadata entity và `EntityManager`, rồi được đăng ký qua cấu hình repository tương ứng.

Đối với MongoDB, nền triển khai và thành phần truy cập dữ liệu sẽ khác. Việc interface cơ sở nằm trong Commons không khiến một implementation dùng `EntityManager` trở thành implementation dùng chung cho mọi store.

Chọn hướng này khi cần thay đổi thực sự mang tính nền tảng cho nhóm repository. Không cần tạo custom factory chỉ để thêm một default method chuyển `Optional` thành exception.

## 8. Phương thức truy vấn kế thừa vẫn có ràng buộc domain

### 8.1. Một base dành cho domain có trạng thái hoạt động

```java
import java.util.List;

import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface ActiveRepository<T, ID>
        extends ApplicationRepository<T, ID> {

    List<T> findByActiveTrue();
}
```

Các repository cụ thể có thể dùng:

```java
public interface CustomerRepository
        extends ActiveRepository<Customer, Long> {
}
```

```java
public interface ProductRepository
        extends ActiveRepository<Product, java.util.UUID> {
}
```

Giả định cả Customer và Product đều có thuộc tính Java `active` với ý nghĩa phù hợp.

Compiler chỉ thấy các tham số generic. Nó không tự kiểm tra tên thuộc tính trong derived query có tồn tại trên mọi kiểu `T` hay không.

Hạ tầng truy vấn sẽ kiểm tra thuộc tính khi xử lý repository cụ thể. Nếu Product chỉ có `enabled` mà không có `active`, kế thừa `findByActiveTrue` có thể gây lỗi.

### 8.2. @NoRepositoryBean không bỏ qua kiểm tra phương thức kế thừa

Base ActiveRepository không được tạo bean riêng, nhưng các phương thức của nó vẫn thuộc hợp đồng của CustomerRepository và ProductRepository.

Vì vậy:

- Không tạo bean cho base không có nghĩa bỏ qua tất cả nội dung của base.
- Phương thức truy vấn kế thừa vẫn phải hợp lệ với domain cụ thể.
- Điều kiện lọc chung vẫn cần được store hỗ trợ.
- Tên thuộc tính và ý nghĩa nghiệp vụ cần nhất quán trong nhóm domain áp dụng.

Nếu chỉ một số domain có `active`, dùng một nhánh base riêng cho nhóm đó thay vì thêm phương thức vào base của toàn ứng dụng.

### 8.3. Không để annotation auditing tạo kỳ vọng sai

Một domain có `@CreatedDate` không tự có thuộc tính `active`. Một domain có các trường auditing cũng không tự đáp ứng mọi truy vấn thời gian mà bạn muốn đưa lên base.

Nếu tạo base có phương thức `findByCreatedAtBefore`, từng domain dùng base đó phải có thuộc tính `createdAt` phù hợp, mapping đúng và store hỗ trợ truy vấn tương ứng.

Cấu hình auditing điền giá trị và khả năng truy vấn một thuộc tính là hai vấn đề có liên quan nhưng khác nhau.

## 9. Nhiều tầng interface trung gian

Ứng dụng có thể tổ chức theo cây năng lực:

```text
Repository<T, ID>
    |
    v
ApplicationRepository<T, ID>        @NoRepositoryBean
    |
    +-- ActiveRepository<T, ID>     @NoRepositoryBean
    |       |
    |       +-- CustomerRepository (T=Customer, ID=Long)
    |       |
    |       +-- ProductRepository (T=Product, ID=UUID)
    |
    +-- InvoiceRepository (T=Invoice, ID=Long)
```

Trong cây này:

- ApplicationRepository là hợp đồng chung.
- ActiveRepository bổ sung một yêu cầu mà chỉ nhóm domain có trạng thái hoạt động đáp ứng.
- InvoiceRepository không bắt buộc có `active`.
- Các interface cụ thể đóng generic và là ứng viên tạo bean nếu cấu hình phù hợp.

Đánh dấu rõ mỗi interface trung gian do ứng dụng định nghĩa bằng `@NoRepositoryBean`. Không dựa vào suy luận rằng một annotation ở tầng trên sẽ tự giải quyết đúng mọi tầng bên dưới.

Ngay cả một interface trung gian đã đóng generic cũng có thể dùng annotation nếu bạn chủ ý không muốn nó trở thành bean độc lập:

```java
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface CustomerContract
        extends ApplicationRepository<Customer, Long> {
}
```

Annotation thể hiện vai trò của interface trong thiết kế, không chỉ là cách “sửa lỗi generic”. CustomerRepository cụ thể có thể kế thừa CustomerContract mà vẫn được tạo bean khi cấu hình đúng.

Không tạo nhiều tầng nếu chúng chỉ đổi tên mà không bổ sung năng lực hoặc ý nghĩa. Một base ngắn, có trách nhiệm rõ ràng thường dễ dùng hơn một cây kế thừa sâu.

## 10. Ghép phân trang và sắp xếp có chủ đích

Một base có thể kết hợp các hợp đồng:

```java
import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.PagingAndSortingRepository;

@NoRepositoryBean
public interface PagedApplicationRepository<T, ID>
        extends ApplicationRepository<T, ID>,
                PagingAndSortingRepository<T, ID> {
}
```

Ở các dòng API từ 3.0, không nên mặc định interface phân trang/sắp xếp tự kế thừa toàn bộ CRUD. Khai báo các năng lực cần dùng một cách tường minh giúp hợp đồng dễ đọc hơn.

Trong ví dụ:

- Lưu và đọc theo ID đến từ ApplicationRepository.
- Các thao tác phân trang/sắp xếp chuẩn đến từ PagingAndSortingRepository.
- Các truy vấn riêng theo domain vẫn được đặt ở repository cụ thể.

Chẳng hạn, ProductRepository có thể khai báo thêm:

```java
org.springframework.data.domain.Page<Product> findByActiveTrue(
        org.springframework.data.domain.Pageable pageable
);
```

Kiểu `Pageable` là hợp đồng mô tả yêu cầu. Store module phải hỗ trợ truy vấn và kiểu trả về đang dùng.

Kế thừa base phân trang không tự làm mọi phương thức tùy chỉnh nhận được tham số Pageable. Bạn vẫn phải khai báo chữ ký phù hợp cho phương thức đó.

Nếu cần biến thể trả về `List` thay cho `Iterable`, xem các interface tương ứng trong đúng phiên bản. Không đổi kiểu kết quả bằng cách cast mà chưa có bảo đảm từ hợp đồng.

## 11. Base dùng Commons và base dành riêng cho store

### 11.1. Base dùng các hợp đồng chung

ApplicationRepository mở rộng `Repository` của Commons. Nó tránh phụ thuộc trực tiếp vào JPA hoặc MongoDB ở chữ ký cơ sở.

Điều đó có lợi cho việc tổ chức hợp đồng, nhưng không chứng minh mọi phương thức bổ sung đều di chuyển được giữa các store. Derived query, projection và các kiểu trả về vẫn phải được đối chiếu theo khả năng của module.

Một hợp đồng chung nên tránh đưa vào:

- `EntityManager` hoặc kiểu truy vấn chỉ có ở JPA.
- Tên collection hoặc API MongoDB.
- Giả định mọi store có dirty checking.
- Giả định mọi thao tác lưu có cùng thời điểm ghi và cùng bảo đảm transaction.

### 11.2. Base chủ ý phụ thuộc JPA

Nếu ứng dụng xác định nhóm repository cần đầy đủ năng lực JPA, có thể khai báo:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface JpaApplicationRepository<T, ID>
        extends JpaRepository<T, ID> {
}
```

Tên và hợp đồng lúc này thể hiện rõ phạm vi JPA. Các phương thức gắn với JPA không nên được mô tả như khả năng phổ quát của mọi store.

Trong ứng dụng có nhiều store module, cần tổ chức repository, mapping domain và phạm vi quét rõ ràng. Một base chỉ mở rộng Commons có thể chưa cung cấp đủ dấu hiệu để hạ tầng phân biệt store trong mọi trường hợp.

`@NoRepositoryBean` không tự quyết định repository con thuộc JPA hay MongoDB. Đó là nhiệm vụ của cấu hình và cơ chế nhận diện store tương ứng.

### 11.3. Không trộn hợp đồng blocking và reactive

Nếu chọn repository reactive, thiết kế base dựa trên hợp đồng reactive và store có đường truy cập tương ứng.

Không đưa `Optional<T>` và phương thức đọc đồng bộ vào một base reactive rồi dùng `block()` để làm chúng có vẻ thống nhất. Hai mô hình có hợp đồng thực thi khác nhau; generic chỉ giúp tổ chức kiểu dữ liệu, không xóa khác biệt đó.

## 12. Các lỗi thường gặp và cách đọc nguyên nhân

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Hạ tầng cố xử lý interface generic như repository độc lập | Base chưa có `@NoRepositoryBean` hoặc có interface trung gian chưa được phân loại rõ | Đánh dấu đúng interface trung gian |
| JPA báo không nhận diện được domain hoặc không phải managed type | Generic chưa đóng, sai domain hoặc mapping chưa đúng | Kiểm tra generic và entity mapping; không chỉ thêm annotation một cách máy móc |
| Không inject được CustomerRepository | Interface cụ thể bị loại hoặc nằm ngoài phạm vi quét | Kiểm tra annotation ở concrete repository và cấu hình store |
| Không thực thi được `archiveById` | Khai báo abstract nhưng chưa có cơ chế implementation | Chọn default, fragment, query hoặc custom base phù hợp |
| Lỗi thuộc tính `active` trên một repository con | Phương thức truy vấn chung không hợp với domain đó | Đưa phương thức về nhánh base hoặc repository cụ thể đúng |
| Có nhiều bean phù hợp với base type | Nhiều concrete repository cùng thực hiện interface cơ sở | Inject theo repository cụ thể hoặc dùng cách phân giải bean tường minh |
| Method CRUD có xung đột chữ ký | Khai báo generic/return type không tuân quy tắc override | Giữ hợp đồng chuẩn hoặc thiết kế lại API |
| Tưởng repository chỉ đọc nhưng dữ liệu vẫn thay đổi | Giới hạn interface bị nhầm với chính sách ghi toàn hệ thống | Xem transaction, dirty checking, quyền truy cập và đường ghi khác |

Thiếu `@NoRepositoryBean` không nhất thiết gây cùng một thông báo ở mọi store. Thậm chí interface có thể không được quét trong một cấu hình cụ thể nên lỗi chưa lộ ra.

Ngược lại, thông báo domain không hợp lệ không luôn do thiếu annotation. Một repository cụ thể khai báo sai kiểu domain hoặc thiếu mapping cũng có thể tạo triệu chứng gần giống.

Luôn xem interface mà hạ tầng đang xử lý và nguyên nhân gốc của lỗi.

## 13. Kiểm tra bean đúng cách

### 13.1. Không có bean độc lập khác với không có bean cùng kiểu cha

Với:

```text
ApplicationRepository<T, ID>       @NoRepositoryBean
    ├─ CustomerRepository
    └─ ProductRepository
```

Điều mong đợi là:

- Không tạo một repository độc lập chỉ dành cho ApplicationRepository.
- Có bean cho CustomerRepository nếu cấu hình của nó hợp lệ.
- Có bean cho ProductRepository nếu cấu hình của nó hợp lệ.

Nhưng cả hai bean cụ thể đều là đối tượng thực hiện ApplicationRepository.

Do đó, thao tác:

```java
context.getBeansOfType(ApplicationRepository.class);
```

có thể trả về các repository cụ thể. Kết quả không rỗng không chứng minh `@NoRepositoryBean` thất bại.

Annotation không yêu cầu xóa quan hệ kế thừa Java của proxy.

### 13.2. Không dựa hoàn toàn vào một tên bean

Theo quy ước mặc định, tên bean thường liên quan đến tên interface repository. Tuy nhiên, ứng dụng có thể cấu hình cách đặt tên khác.

Khi cần xác minh, xem repository interface mà bean đại diện và metadata đăng ký tương ứng, thay vì chỉ tìm một tên chuỗi rồi kết luận.

Không sửa `@NoRepositoryBean` chỉ vì một concrete bean được trả về khi tìm theo base type.

## 14. Bài thực hành: một base, hai repository cụ thể

Các đoạn khai báo ở những phần trước minh họa những lựa chọn khác nhau. Trong bài thực hành này, chọn một cấu trúc cuối cùng cho mỗi interface, không khai báo nhiều phiên bản cùng tên.

### Bước 1: chuẩn bị domain và store

Chọn một store đã cấu hình và hai domain:

| Domain | ID | Thuộc tính phục vụ truy vấn |
| --- | --- | --- |
| Customer | Long | `email` |
| Product | UUID | `sku` |

Thiết lập mapping và chiến lược định danh theo store. Nếu dùng UUID tự cấp, kiểm tra cơ chế xác định đối tượng mới; không suy rằng mọi store luôn xử lý ID đã có giá trị giống nhau.

### Bước 2: khai báo ApplicationRepository

Dùng base công khai ba phương thức:

```java
<S extends T> S save(S entity);

java.util.Optional<T> findById(ID id);

boolean existsById(ID id);
```

Base mở rộng `Repository<T, ID>`, có `@NoRepositoryBean` và bổ sung default method `requireById` đã trình bày.

### Bước 3: đóng generic

CustomerRepository mở rộng `ApplicationRepository<Customer, Long>` và có `findByEmail`.

ProductRepository mở rộng `ApplicationRepository<Product, UUID>` và có `findBySku`.

Không đặt `@NoRepositoryBean` lên hai interface này.

### Bước 4: đối chiếu kết quả kỹ thuật

Sau khi context khởi tạo:

1. Inject được CustomerRepository và ProductRepository theo kiểu cụ thể.
2. Lưu rồi đọc lại được từng domain qua ID đúng kiểu.
3. `findByEmail` và `findBySku` trả dữ liệu đúng theo fixture.
4. `requireById` trả đối tượng khi có và ném loại lỗi đã quy định khi không có.
5. Không tạo repository độc lập cho base generic.
6. Tìm bean theo ApplicationRepository vẫn có thể nhìn thấy các concrete repository.

Chỉ dùng một ID khác null và chưa tồn tại cho tình huống “không tìm thấy”. Trường hợp truyền null được default method xử lý theo quy ước riêng và không phải bằng chứng về truy vấn dữ liệu rỗng.

### Bước 5: kiểm tra ranh giới hợp đồng

Quan sát rằng base không khai báo thao tác xóa. Service dùng hợp đồng này không được công khai sẵn `deleteById`.

Tiếp theo, giải thích bằng lời điều gì sẽ thay đổi nếu base mở rộng CrudRepository: toàn bộ nhóm phương thức CRUD được kế thừa, bao gồm các thao tác xóa.

Không cần thêm phương thức xóa chỉ để hoàn thành bài. Mục tiêu là nhận ra lựa chọn interface cha đã quyết định bề mặt API như thế nào.

## 15. Các câu hỏi tự kiểm tra

**Vì sao base generic thường cần @NoRepositoryBean?**

Vì nó là hợp đồng trung gian, thường chưa gắn với một domain cụ thể. Annotation loại nó khỏi danh sách ứng viên tạo repository bean độc lập.

**Một concrete repository kế thừa base có annotation thì có bị loại theo không?**

Không tự động chỉ vì quan hệ kế thừa đó. Concrete repository được hạ tầng xem xét theo khai báo và cấu hình của nó. Không gắn annotation lên concrete repository nếu muốn nó được tạo bean.

**Có thể dùng annotation để làm một phương thức abstract mới tự hoạt động không?**

Không. Phương thức vẫn cần một cơ chế thực hiện: phương thức cơ sở được hỗ trợ, derived query hợp lệ, truy vấn khai báo, default method, fragment hoặc custom implementation.

**Một derived query đặt trên base có được kiểm tra với domain cụ thể không?**

Có. Nó trở thành một phần hợp đồng của repository con và phải hợp lệ với thuộc tính domain cũng như khả năng store.

**Một lookup repository không có save có bảo đảm không thể ghi dữ liệu không?**

Không. Nó giới hạn API được công khai, còn transaction, cơ chế quản lý entity, quyền của kho dữ liệu và các đường truy cập khác là những phần riêng.

**Nếu getBeansOfType trả về bean thực hiện base thì annotation có sai không?**

Không. Concrete repository vẫn thực hiện interface cha. Điều bị loại là repository bean độc lập cho interface được đánh dấu, không phải mọi bean có thể gán cho kiểu đó.

## 16. Nguyên tắc thiết kế cần giữ

Một repository cơ sở tốt có hợp đồng nhỏ, kiểu generic rõ ràng và những hành vi thực sự dùng chung.

Dùng `@NoRepositoryBean` để thể hiện interface trung gian; đóng `T` và `ID` ở repository cụ thể; dùng default method cho logic ghép đơn giản; chọn fragment hoặc implementation theo store khi cần thêm cơ chế truy cập dữ liệu.

Khi bổ sung derived query, phân trang, projection, metadata hoặc auditing lên một nhánh base, hãy kiểm tra rằng mọi domain trong nhánh đều đáp ứng giả định đó. Phần dùng chung nên giúp hợp đồng dễ hiểu hơn, đồng thời giữ rõ giới hạn và trách nhiệm của từng store.

