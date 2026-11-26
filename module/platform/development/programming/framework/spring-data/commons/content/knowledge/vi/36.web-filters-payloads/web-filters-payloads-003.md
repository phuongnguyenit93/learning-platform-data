# QuerydslBinderCustomizer cho quy tắc theo repository

Một endpoint tìm khách hàng có thể nhận `name=Lan`, `status=ACTIVE` hoặc nhiều trạng thái cùng lúc. Nếu chỉ bật Querydsl Web Support rồi chấp nhận mọi quy tắc mặc định, API có thể không diễn đạt đúng nhu cầu tìm kiếm: tên cần tìm gần đúng, email cần so khớp chính xác không phân biệt hoa thường, còn các trường nội bộ không nên trở thành bộ lọc công khai.

Trong chương **Bộ lọc và payload web** của **Spring Data Commons**, `QuerydslBinderCustomizer` là điểm mở rộng để mô tả cách biến giá trị query parameter thành biểu thức Querydsl theo domain/repository. Bài học tập trung vào quy tắc binding; truy vấn thực tế, phân trang, projection và khả năng thực thi vẫn cần được đối chiếu với module lưu trữ hỗ trợ Querydsl.

## 1. Binding nằm ở đâu trong đường truy vấn?

Một đường xử lý điển hình trong Spring MVC:

```text
Query parameter HTTP
    → chuyển giá trị sang kiểu thuộc tính
    → QuerydslBindings áp dụng quy tắc binding
    → Predicate của client
    → service ghép phạm vi tenant và điều kiện bắt buộc
    → QuerydslPredicateExecutor của repository
    → truy vấn của module lưu trữ
```

`QuerydslBinderCustomizer` tùy biến bước tạo predicate từ tham số web. Nó không phải một repository implementation, không thực thi truy vấn khi khai báo rule và không tự thiết lập transaction.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `@QuerydslPredicate` | Đánh dấu đối số controller cần được phân giải thành predicate |
| `QuerydslBindings` | Lưu quy tắc cho path, kiểu dữ liệu và tập thuộc tính được phép |
| `QuerydslBinderCustomizer<QType>` | Cung cấp các quy tắc binding cho root Querydsl tương ứng |
| Q-type, ví dụ `QCustomer` | Mô tả có kiểu của các thuộc tính domain |
| `QuerydslPredicateExecutor<Customer>` | Thực thi các predicate theo khả năng module |
| Service nghiệp vụ | Quyết định phạm vi dữ liệu và điều kiện không được client bỏ qua |

Một predicate đúng cú pháp không đồng nghĩa người gọi được phép xem mọi bản ghi mà predicate đó khớp.

## 2. Điều kiện hỗ trợ của ví dụ

Các ví dụ giả định:

- Ứng dụng dùng Spring MVC và Spring Data Web với tích hợp Querydsl phù hợp.
- Module persistence hỗ trợ Querydsl cho kiểu repository đang dùng.
- Q-type đã được sinh tương thích với mô hình domain và bộ thư viện của dự án.
- Repository được tạo thành bean và được hạ tầng Spring Data phát hiện.
- Các converter cần thiết cho kiểu dữ liệu của thuộc tính đã được cấu hình.

`QuerydslBinderCustomizer` thuộc cơ chế chung của Spring Data, nhưng không làm mọi module tự có `QuerydslPredicateExecutor`. Không thêm một interface rồi mặc định backend đã thực hiện được mọi phép toán Querydsl.

Với cấu hình Spring MVC chủ động, `@EnableSpringDataWebSupport` là một cách bật hỗ trợ Spring Data Web. Ứng dụng Spring Boot phù hợp có thể đã được cấu hình tự động. Cần hiểu hạ tầng đang dùng trước khi tự đăng ký thêm resolver hoặc thay conversion service.

Ví dụ dùng `QCustomer` như một lớp đã được sinh. Không tự viết Q-type bằng tay để che một lỗi cấu hình sinh metadata. Khi áp dụng trong dự án thực tế, cấu hình build, namespace và dependency Querydsl phải khớp với phiên bản/module đang sử dụng.

## 3. Domain minh họa và hợp đồng bộ lọc

Giả sử `Customer` có các thuộc tính:

| Thuộc tính | Kiểu minh họa | Vai trò |
|---|---|---|
| `id` | `Long` | Định danh |
| `name` | `String` | Tên công khai |
| `email` | `String` | Email tìm kiếm |
| `status` | `CustomerStatus` | Trạng thái khách hàng |
| `age` | `Integer` | Tuổi dùng trong ví dụ bộ lọc |
| `tenantId` | `UUID` | Phạm vi tenant của ứng dụng |
| `deleted` | `boolean` | Trạng thái xóa mềm |
| `internalScore` | Kiểu số | Dữ liệu nội bộ |

Enum dùng trong ví dụ:

```java
enum CustomerStatus {
    TRIAL,
    ACTIVE,
    SUSPENDED
}
```

Giả định Q-type có các path tương ứng như `root.name`, `root.email`, `root.status` và `root.age`.

Hợp đồng tìm kiếm công khai được chọn là:

```text
name     → chứa chuỗi, không phân biệt hoa thường
email    → bằng giá trị, không phân biệt hoa thường
status   → thuộc tập giá trị được gửi
age      → mặc định bằng giá trị, trừ khi chủ động đổi sang rule khoảng
```

`tenantId`, `deleted` và `internalScore` không thuộc bộ lọc công khai. Tenant và điều kiện chưa xóa sẽ được service thêm từ chính sách của ứng dụng.

## 4. Khai báo customizer ngay trên repository

Một repository có thể kết hợp CRUD, khả năng thực thi predicate và quy tắc binding:

```java
import java.util.Optional;

import com.querydsl.core.types.dsl.StringPath;

import org.springframework.data.querydsl.QuerydslPredicateExecutor;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;
import org.springframework.data.repository.CrudRepository;

interface CustomerRepository extends
        CrudRepository<Customer, Long>,
        QuerydslPredicateExecutor<Customer>,
        QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(QuerydslBindings bindings, QCustomer root) {
        bindings.excludeUnlistedProperties(true);
        bindings.including(
                root.name,
                root.email,
                root.status,
                root.age);

        bindings.bind(String.class)
                .first((StringPath path, String value) ->
                        path.containsIgnoreCase(value));

        bindings.bind(root.email)
                .first((path, value) -> path.equalsIgnoreCase(value));

        bindings.bind(root.status)
                .all((path, values) -> Optional.of(path.in(values)));
    }
}
```

Đây là chữ ký minh họa cho một module hỗ trợ các interface tương ứng. `Customer` vẫn cần mapping hợp lệ của module, còn `QCustomer` phải phản ánh đúng mô hình đó.

Khi hạ tầng Querydsl Web phát hiện customizer của repository cho domain phù hợp, các rule này có thể được dùng để phân giải predicate mà không cần lặp lại lớp cấu hình ở mọi controller.

`customize(...)` mô tả quy tắc tạo biểu thức; nó không phải nơi gọi database để kiểm tra từng giá trị filter.

## 5. Rule theo kiểu và rule theo thuộc tính

Rule sau áp dụng cho các path kiểu chuỗi được phép binding và không có rule riêng:

```java
bindings.bind(String.class)
        .first((StringPath path, String value) ->
                path.containsIgnoreCase(value));
```

Trong ví dụ, `name=Lan` được diễn giải như tên chứa `Lan` không phân biệt hoa thường, theo ngữ nghĩa mà Querydsl và module chuyển thành truy vấn.

Email có rule riêng:

```java
bindings.bind(root.email)
        .first((path, value) -> path.equalsIgnoreCase(value));
```

Rule theo path cụ thể được dùng cho `email` thay vì rule kiểu chuỗi chung. Nhờ đó, `email=lan@example.com` không mang nghĩa tìm mọi email có chứa đoạn đó.

Không nên kết luận rằng rule chứa chuỗi luôn nhanh hoặc luôn dùng được index theo cùng một cách. Hàm xử lý hoa thường, collation, cấu trúc index và chiến lược truy vấn phụ thuộc kho dữ liệu.

Rule chuỗi chung cũng cần được cân nhắc về phạm vi. Nếu mọi trường chuỗi mới đều tự được mở cho binding, một rule thuận tiện có thể làm thay đổi API khi domain phát triển. Whitelist rõ ràng giúp tách quyết định công khai thuộc tính khỏi kiểu Java của thuộc tính.

## 6. Whitelist và blacklist giải quyết bài toán khác nhau

Với blacklist:

```java
bindings.excluding(root.tenantId, root.deleted, root.internalScore);
```

Ứng dụng chỉ rõ các path bị loại khỏi binding. Tuy nhiên, một thuộc tính domain mới có thể vẫn trở thành đường lọc nếu cơ chế mặc định cho phép nó.

Với whitelist:

```java
bindings.excludeUnlistedProperties(true);
bindings.including(root.name, root.email, root.status, root.age);
```

Ứng dụng chỉ mở các thuộc tính đã chọn. Đây là lựa chọn hữu ích khi API cần giữ tập bộ lọc ổn định trong lúc domain bổ sung trường nội bộ.

Hai điểm cần phân biệt:

1. Không được binding không đồng nghĩa request chắc chắn bị trả HTTP 400.
2. Không được binding không đồng nghĩa server đã thêm điều kiện bảo vệ dữ liệu tương ứng.

Nếu client gửi `internalScore=100`, hạ tầng binding có thể bỏ qua path không được phép. Nếu hợp đồng API yêu cầu từ chối mọi tên tham số không được hỗ trợ, cần có bước kiểm tra tên query parameter riêng.

Bước kiểm tra đó phải biết cả các tham số điều khiển hợp lệ như `page`, `size`, `sort`, qualifier hoặc tham số khác của endpoint; không dùng whitelist của thuộc tính domain làm toàn bộ whitelist HTTP một cách máy móc.

Đặc biệt, loại `tenantId` khỏi binding chỉ ngăn client tạo điều kiện qua path đó. Nó không tự giới hạn truy vấn theo tenant hiện tại.

## 7. Giá trị lặp: first và all không có cùng ngữ nghĩa

### 7.1. first dùng một giá trị

Với rule:

```java
bindings.bind(root.email)
        .first((path, value) -> path.equalsIgnoreCase(value));
```

Ứng dụng chọn binding dựa vào giá trị đầu tiên được xử lý cho path. Gửi lặp `email` không tự biến điều kiện thành OR hoặc IN.

Nếu API chỉ chấp nhận một email, nên công bố và kiểm tra cardinality thay vì để client tự suy đoán cách xử lý nhiều giá trị.

### 7.2. all cho phép định nghĩa ngữ nghĩa của tập giá trị

Với trạng thái:

```java
bindings.bind(root.status)
        .all((path, values) -> Optional.of(path.in(values)));
```

Request:

```http
GET /api/customers?status=ACTIVE&status=TRIAL
```

được chọn để diễn đạt một điều kiện kiểu:

```text
status IN (ACTIVE, TRIAL)
```

Không phải `status = ACTIVE AND status = TRIAL`.

`all(...)` không tự có nghĩa OR cho mọi rule. Chính biểu thức mà customizer trả về quyết định cách các giá trị được kết hợp. Có thể viết `in`, một khoảng hoặc một biểu thức khác phù hợp, nhưng cần công bố đúng cú pháp và ý nghĩa.

Giá trị được chuyển sang kiểu của path theo hạ tầng conversion. Một chuỗi không chuyển được thành `CustomerStatus` là lỗi chuyển đổi đầu vào, không phải một trạng thái mới được tự thêm vào enum.

Không mặc định `status=ACTIVE,TRIAL` luôn tương đương hai query parameter lặp trong mọi cấu hình conversion. Nếu API chọn một cú pháp, hãy công bố và kiểm chứng đúng cú pháp đó.

## 8. Kết hợp nhiều thuộc tính

Một request minh họa:

```http
GET /api/customers?name=Lan&email=lan@example.com&status=ACTIVE&status=TRIAL&page=0&size=20&sort=name,asc&sort=id,asc
```

Với customizer ở phần 4, phần bộ lọc có ý nghĩa khái niệm:

```text
name chứa "Lan", không phân biệt hoa thường
AND email bằng "lan@example.com", không phân biệt hoa thường
AND status thuộc {ACTIVE, TRIAL}
```

Nhóm tham số `page`, `size`, `sort` được hạ tầng phân trang/sắp xếp xử lý theo cấu hình của nó. Chúng không phải các thuộc tính được thêm vào `QuerydslBindings` trong ví dụ.

Binding nhiều thuộc tính thường hình thành tổ hợp điều kiện theo cơ chế predicate builder. Nếu API cần biểu thức OR phức tạp giữa các trường, dấu ngoặc lồng nhau hoặc một ngôn ngữ tìm kiếm đầy đủ, đừng suy ra rằng chỉ cần thêm tên query parameter là cơ chế này tự hiểu.

Một path dạng chuỗi không phải chỗ để chèn tùy ý SQL, JPQL hoặc toán tử riêng. Quy tắc được customizer mã hóa bằng API Querydsl có kiểu; client chỉ cung cấp các giá trị theo hợp đồng đã công bố.

## 9. Dùng predicate ở controller và giữ phạm vi trong service

Controller minh họa:

```java
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.querydsl.binding.QuerydslPredicate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    private final CustomerSearchService service;

    CustomerController(CustomerSearchService service) {
        this.service = service;
    }

    @GetMapping("/api/customers")
    CustomerPageResponse search(
            @QuerydslPredicate(root = Customer.class) Predicate filter,
            Pageable pageable) {

        Page<CustomerView> result = service.searchVisible(filter, pageable);
        return CustomerPageResponse.from(result);
    }
}
```

`CustomerPageResponse` là DTO biểu diễn trang của ứng dụng, giả định có phương thức `from(Page<CustomerView>)`. Cách bọc kết quả web là quyết định riêng với binding bộ lọc.

Khai báo `root = Customer.class` làm rõ domain dùng để phân giải path. Điều này đặc biệt hữu ích khi kiểu trả về của controller là DTO và không đủ để suy ra root domain.

Phần cốt lõi trong service có thể là:

```java
import java.util.UUID;

import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Predicate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public Page<CustomerView> searchVisible(
        Predicate clientFilter,
        Pageable pageable) {

    UUID tenantId = tenantContext.requireTenantId();
    QCustomer customer = QCustomer.customer;

    BooleanBuilder scoped = new BooleanBuilder(
            customer.tenantId.eq(tenantId));
    scoped.and(customer.deleted.isFalse());

    if (clientFilter != null) {
        scoped.and(clientFilter);
    }

    Pageable safePageable = pagingPolicy.normalize(pageable);

    return repository.findAll(scoped, safePageable)
            .map(customerEntity -> new CustomerView(
                    customerEntity.getId(),
                    customerEntity.getName()));
}
```

Các dependency `tenantContext`, `pagingPolicy` và `repository` thuộc service của ứng dụng. Ví dụ giả định `CustomerView` là DTO có ID và tên; module hỗ trợ `findAll(Predicate, Pageable)` tương ứng.

Điều kiện tenant và chưa xóa được thêm từ phía server dù client không gửi bộ lọc nào. Dùng `AND` giữ phạm vi bắt buộc; ghép tenant với bộ lọc client bằng `OR` có thể làm rộng tập kết quả ngoài chủ đích.

Customizer không biết đầy đủ danh tính và chính sách nghiệp vụ của từng lần gọi. Không dùng việc có annotation `@QuerydslPredicate` làm bằng chứng rằng truy vấn đã được giới hạn quyền.

## 10. Mở rộng rule khoảng cho một thuộc tính

Giả sử endpoint muốn thay ngữ nghĩa của `age` thành khoảng đóng:

```text
age=18&age=65 → 18 <= age <= 65
```

Có thể thay rule của path bằng một binding nhận nhiều giá trị:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

bindings.bind(root.age).all((path, values) -> {
    List<Integer> bounds = new ArrayList<>(values);

    if (bounds.size() != 2) {
        throw new InvalidCustomerFilterException(
                "age cần đúng hai cận: cận dưới và cận trên");
    }

    int lower = bounds.get(0);
    int upper = bounds.get(1);

    if (lower < 0 || upper > 150 || lower > upper) {
        throw new InvalidCustomerFilterException(
                "Khoảng age không hợp lệ");
    }

    return Optional.of(path.between(lower, upper));
});
```

Đây là đoạn đặt bên trong `customize(...)`, với `root.age` là path số nguyên. Nó là **một lựa chọn hợp đồng thay thế** cho cách lọc tuổi mặc định, không phải rule được tự thêm vào ví dụ phần 4.

Ngưỡng 0–150 chỉ là quy tắc minh họa. Hợp đồng cần xác định thứ tự hai giá trị là cận dưới rồi cận trên, và hạ tầng phải bảo toàn cách xử lý giá trị lặp mà endpoint sử dụng.

Nếu API cần tên rõ hơn như `minAge` và `maxAge`, có thể thiết kế DTO bộ lọc hoặc cơ chế binding riêng thích hợp. Không mặc định hai tên tùy ý sẽ tự được ghép thành khoảng chỉ vì domain có thuộc tính `age`.

Một lỗi thiết kế là trả `Optional.empty()` cho khoảng sai chỉ để bỏ qua điều kiện. Nếu người dùng yêu cầu lọc tuổi nhưng điều kiện bị bỏ qua, truy vấn có thể rộng hơn mong muốn. Với input không hợp lệ, thường cần phản hồi lỗi rõ ràng theo hợp đồng.

## 11. Xử lý giá trị sai và tên tham số không hỗ trợ

Exception minh họa cho rule khoảng:

```java
final class InvalidCustomerFilterException extends RuntimeException {

    InvalidCustomerFilterException(String message) {
        super(message);
    }
}
```

Một advice có thể ánh xạ exception có chủ đích sang HTTP 400:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class CustomerFilterAdvice {

    @ExceptionHandler(InvalidCustomerFilterException.class)
    ResponseEntity<FilterError> invalidFilter(
            InvalidCustomerFilterException exception) {

        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(new FilterError(
                        "INVALID_CUSTOMER_FILTER",
                        exception.getMessage()));
    }
}

record FilterError(String code, String message) {
}
```

Thông báo của exception trong ví dụ là nội dung do ứng dụng tự kiểm soát. Không dùng handler bắt mọi exception rồi trả nguyên thông báo kỹ thuật của Querydsl, driver hoặc kho dữ liệu.

Các nhóm lỗi cần được phân biệt:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Chuyển đổi kiểu | `age=abc`, enum không hợp lệ | Lỗi đầu vào theo cơ chế conversion và advice phù hợp |
| Giá trị nghiệp vụ | Khoảng tuổi đảo cận | Exception có chủ đích và phản hồi 400 |
| Tên filter không được công khai | `internalScore=100` | Bỏ qua hoặc từ chối theo hợp đồng đã chọn |
| Hạ tầng truy vấn | Timeout, lỗi kết nối | Chính sách lỗi hạ tầng, không giả làm filter sai |
| Cấu hình metadata | Q-type hoặc repository không khớp | Sửa cấu hình, không biến thành kết quả tìm kiếm rỗng |

Handler minh họa chỉ xử lý exception tùy biến. Những exception chuyển đổi của hạ tầng cần được tích hợp vào chính sách lỗi chung theo kiểu thực tế mà stack đang dùng phát sinh.

Không nên bắt mọi `IllegalArgumentException` của toàn ứng dụng rồi coi đó đều là lỗi bộ lọc. Cùng kiểu exception có thể đến từ lỗi lập trình hoặc lớp khác.

## 12. Quy tắc theo repository và quy tắc theo endpoint

Đặt customizer trên repository thích hợp khi các endpoint dùng cùng một hợp đồng bộ lọc cho domain đó. Ví dụ mọi màn hình tìm khách hàng đều tìm tên bằng contains-ignore-case và không công khai trường nội bộ.

Nếu endpoint quản trị và endpoint công khai cần hợp đồng khác nhau, có thể dùng customizer được chỉ định trên annotation:

```java
@QuerydslPredicate(
        root = Customer.class,
        bindings = PublicCustomerBindings.class)
Predicate filter
```

Một lớp cấu hình độc lập minh họa:

```java
import com.querydsl.core.types.dsl.StringPath;

import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;
import org.springframework.stereotype.Component;

@Component
class PublicCustomerBindings implements QuerydslBinderCustomizer<QCustomer> {

    @Override
    public void customize(QuerydslBindings bindings, QCustomer root) {
        bindings.excludeUnlistedProperties(true);
        bindings.including(root.name);

        bindings.bind(String.class)
                .first((StringPath path, String value) ->
                        path.containsIgnoreCase(value));
    }
}
```

Customizer được chọn tường minh cần tự nêu rõ tập thuộc tính và ngữ nghĩa cần duy trì. Không giả định đây luôn là phép cộng mọi rule của repository với mọi rule của endpoint; cần hiểu cơ chế chọn customizer của bộ phiên bản đang dùng.

Dù endpoint chỉ mở `name`, service vẫn phải thêm phạm vi tenant, trạng thái công khai và các điều kiện bắt buộc. Việc lựa chọn customizer không thay thế chính sách truy cập.

Nếu dự án có cơ chế mặc định chung như `QuerydslBinderCustomizerDefaults` ở phiên bản hỗ trợ, cần xác định rõ phạm vi và quan hệ với rule cụ thể. Một thay đổi default toàn cục có thể ảnh hưởng nhiều repository; rule thuộc tính công khai của từng API vẫn nên được mô tả rõ.

## 13. Binding bộ lọc không kiểm soát mọi đầu vào

`QuerydslBindings` trong bài xử lý query parameter được dùng để tạo predicate. Nó không tự định nghĩa toàn bộ payload JSON của request body, không thay DTO ghi dữ liệu và không thay Bean Validation.

Các chính sách khác vẫn cần được xử lý ở lớp phù hợp:

| Chính sách | Vì sao cần riêng |
|---|---|
| Whitelist sort | Thuộc tính được phép lọc không tự là danh sách thuộc tính được phép sắp xếp |
| Giới hạn page size | Binder không tự giới hạn số bản ghi trả về |
| Giới hạn số giá trị lặp | Một rule `in` vẫn có thể nhận tập giá trị quá lớn nếu không có giới hạn |
| Độ dài chuỗi tìm kiếm | Contains với chuỗi quá ngắn hoặc rất dài có thể không phù hợp hợp đồng |
| Tenant và quyền | Cần gắn với danh tính và nghiệp vụ, không lấy từ filter tự do |
| Schema response | Predicate đúng không tự tạo một biểu diễn trang ổn định |

Không công khai path lồng nhau một cách vô tình. Việc đi qua quan hệ hoặc collection có thể ảnh hưởng cách tạo join, độ chọn lọc và chi phí truy vấn tùy module.

Cũng không suy ra rule Querydsl sẽ áp dụng cho derived query, Query by Example hoặc mọi repository fragment. Chỉ đường xử lý sử dụng binding web tương ứng mới có quy tắc này; các cách truy vấn khác có hợp đồng riêng.

## 14. Tình huống kiểm chứng khi tích hợp

| Tình huống | Điều cần quan sát |
|---|---|
| `name=Lan` | Dùng contains-ignore-case theo rule chuỗi |
| `email=lan@example.com` | Rule riêng của email được dùng thay rule chuỗi chung |
| Hai giá trị `status` | Một điều kiện thuộc tập giá trị, không phải hai equality mâu thuẫn |
| Hai giá trị email với rule first | Theo cardinality đã công bố, không tự suy ra OR |
| Không có filter | Điều kiện tenant/chưa xóa vẫn được service áp dụng |
| `tenantId` do client gửi | Không thay thế tenant đã xác định của người dùng |
| Thuộc tính mới được thêm vào domain | Không tự mở thành filter nếu dùng whitelist |
| Filter bị loại khỏi binding | Theo chính sách bỏ qua hoặc từ chối đã công bố |
| `age=abc` | Lỗi chuyển kiểu được phân biệt với khoảng tuổi sai |
| Khoảng tuổi đảo cận | Không âm thầm bỏ điều kiện |
| Sort dùng trường ngoài chính sách | Được kiểm soát bởi chính sách sort riêng |
| Endpoint chọn customizer riêng | Không vô tình mở thêm path từ hợp đồng khác |
| Module không hỗ trợ Querydsl mong muốn | Phát hiện giới hạn khả năng thay vì giả định interface là đủ |

Khi chẩn đoán, nên xác định root domain, repository được phát hiện, customizer được chọn, path được phép và predicate sau khi ghép phạm vi server. Sau đó mới đối chiếu truy vấn của module.

Không dùng việc nhận được HTTP 200 và danh sách rỗng làm bằng chứng binding đã đúng. Kết quả đó có thể đến từ filter bị bỏ qua, enum sai được xử lý không đúng hoặc điều kiện được kết hợp khác mong muốn.

## 15. Bài tập tự kiểm tra

### Tình huống 1: Đã loại tenantId khỏi binding nên cho rằng truy vấn đã an toàn theo tenant

Service gọi thẳng `repository.findAll(clientFilter, pageable)`.

**Phân tích:** việc loại path chỉ ngăn client tạo filter tương ứng. Service vẫn cần thêm điều kiện tenant từ danh tính tin cậy vào mọi truy vấn thuộc phạm vi tenant.

### Tình huống 2: Rule chung dùng containsIgnoreCase, nhưng email cần so khớp chính xác

Nhóm phát triển định bỏ rule chuỗi chung để sửa email.

**Phân tích:** có thể giữ rule theo kiểu và thêm rule theo path `root.email`. Rule cụ thể giúp diễn đạt khác biệt mà không làm mất hành vi tìm tên.

### Tình huống 3: Client gửi nhiều status nhưng customizer dùng first

Ứng dụng mong nhận tập trạng thái, nhưng rule chỉ dùng một giá trị.

**Phân tích:** cần định nghĩa binding nhiều giá trị bằng `all(...)` và biểu thức phù hợp, chẳng hạn `in(values)`. Đồng thời phải công bố cú pháp và giới hạn số giá trị.

### Tình huống 4: Filter sai bị bỏ qua bằng Optional.empty

Một khoảng tuổi đảo cận bị chuyển thành không có điều kiện tuổi.

**Phân tích:** truy vấn có thể rộng hơn yêu cầu của người dùng. Nên phân biệt input không hợp lệ với input không được gửi và trả lỗi có chủ đích khi hợp đồng yêu cầu.

### Tình huống 5: Đã whitelist filter nhưng sort theo trường nội bộ vẫn chạy

Endpoint dùng `Pageable` do resolver khác tạo.

**Phân tích:** binding predicate và binding sort là hai đường xử lý. Cần chính sách sort riêng thay vì kỳ vọng whitelist filter áp dụng cho mọi tham số web.

### Tình huống 6: Thêm trường mới vào Customer rồi nó xuất hiện trong bộ lọc ngoài ý muốn

Repository chỉ blacklist một vài trường cũ.

**Phân tích:** blacklist không tự kiểm soát mọi thuộc tính tương lai. Nếu cần hợp đồng công khai ổn định, dùng whitelist và chủ động quyết định mỗi lần mở thêm path.

`QuerydslBinderCustomizer` hữu ích khi biến quy tắc lọc thành một hợp đồng có kiểu và có phạm vi rõ ràng. Hãy kiểm soát tập path công khai, ý nghĩa của giá trị đơn/lặp và cách kết hợp điều kiện; đồng thời giữ tenant, quyền truy cập, sort và giới hạn truy vấn trong các chính sách riêng phù hợp với module lưu trữ.
