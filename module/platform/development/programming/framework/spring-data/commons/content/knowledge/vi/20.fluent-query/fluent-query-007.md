# ReactiveFluentQuery và các phép kết thúc tương ứng

`ReactiveFluentQuery` là biến thể fluent query dành cho truy vấn reactive trong Spring Data Commons. Thay vì trả ngay một đối tượng, danh sách hoặc số đếm, các phép kết thúc trả về publisher như `Mono<T>` và `Flux<T>`.

Điểm thay đổi không chỉ nằm ở kiểu trả về. Ứng dụng cần hiểu thời điểm subscription, cách biểu diễn không có dữ liệu, cách truyền lỗi và cách kết hợp truy vấn vào một luồng reactive hoàn chỉnh.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Dùng fluent query trong callback của `ReactiveQueryByExampleExecutor.findBy`.
- Chọn đúng giữa `first`, `one`, `all`, `count`, `exists` và phân trang khi được hỗ trợ.
- Phân biệt `Mono.empty()`, `Mono.just(false)` và `Mono.just(0L)`.
- Xử lý trường hợp không có dữ liệu và trường hợp có nhiều kết quả.
- Trả publisher cho tầng gọi mà không tự tạo subscription hoặc chặn luồng xử lý.
- Nhận biết giới hạn phụ thuộc module, driver và phiên bản Spring Data.

Bài sử dụng Query by Example (QBE) làm nguồn điều kiện. `ReactiveFluentQuery<T>` là interface lồng trong `org.springframework.data.repository.query.FluentQuery`. Repository cần một module thực sự hỗ trợ reactive QBE và các thao tác được sử dụng.

Một interface reactive trong Commons không biến một driver đồng bộ thành driver reactive. Kiểu projection, đường dẫn sắp xếp, phân trang và cách thực thi truy vấn vẫn phải phù hợp với module lưu trữ cụ thể.

## 2. Mono và Flux thay đổi hợp đồng trả về như thế nào?

Trong Reactor:

- `Mono<T>` phát tối đa một phần tử, sau đó hoàn tất; nó cũng có thể hoàn tất mà không phát phần tử.
- `Flux<T>` có thể phát nhiều phần tử, không có phần tử, hoặc kết thúc bằng lỗi.
- Lỗi trong quá trình thực thi được truyền qua tín hiệu lỗi thay vì biến thành một phần tử dữ liệu thông thường.
- Publisher không phát giá trị null. Không có phần tử và có một phần tử mang giá trị `false` hoặc `0L` là những trạng thái khác nhau.

Ví dụ:

```java
Mono<Customer> customer;
Mono<Long> total;
Mono<Boolean> found;
Flux<Customer> customers;
```

Đoạn mã cần các import:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
```

Tên `Mono<Customer>` không có nghĩa đã có sẵn một khách hàng trong bộ nhớ. Nó biểu diễn một nguồn có thể phát một khách hàng, hoàn tất rỗng hoặc báo lỗi khi được thực thi.

## 3. Repository và dữ liệu mẫu

### 3.1. Domain tối giản

Các ví dụ giả định domain `Customer` có getter, setter và mapping đúng với module đang dùng:

| Thuộc tính | Kiểu Java | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh duy nhất |
| `displayName` | `String` | Tên hiển thị |
| `email` | `String` | Email tra cứu |
| `country` | `String` | Mã quốc gia |

Các field tham chiếu không được gán sẵn giá trị trên probe mới. Nếu domain thật có field nguyên thủy hoặc initializer, cần kiểm soát chúng để không tạo thêm điều kiện ngoài ý muốn.

Repository chỉ khai báo khả năng cần cho bài:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.ReactiveQueryByExampleExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                ReactiveQueryByExampleExecutor<Customer> {
}
```

`Repository` là marker interface. Module reactive cần tạo được implementation tương ứng; khai báo trên không tự cung cấp toàn bộ phương thức CRUD.

### 3.2. Tạo Example

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCountry("VN");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues();

Example<Customer> example = Example.of(probe, matcher);
```

Trong các đoạn mã tiếp theo, `customerRepository` là repository đã được ứng dụng cung cấp, còn `example` là điều kiện quốc gia VN. Các snippet là những lựa chọn sử dụng riêng, không yêu cầu gọi tất cả liên tiếp.

Giả định việc so khớp mã quốc gia phù hợp với matcher và module lưu trữ.

### 3.3. Dữ liệu để đối chiếu kết quả

| id | displayName | email | country |
| --- | --- | --- | --- |
| 101 | An | shared@example.test | VN |
| 102 | An | shared@example.test | VN |
| 103 | Binh | binh@example.test | TH |
| 104 | Chi | chi@example.test | VN |

Quốc gia VN có ba kết quả, TH có một kết quả và JP không có kết quả. Email trùng được giữ có chủ đích để minh họa trường hợp không duy nhất.

## 4. Bảng đối chiếu các phép kết thúc

Đối với `ReactiveFluentQuery<T>` đang xét, khi không đặt giới hạn riêng cho truy vấn:

| Phép kết thúc | Kiểu trả về | Không có kết quả | Một kết quả | Nhiều kết quả |
| --- | --- | --- | --- | --- |
| `first()` | `Mono<T>` | Hoàn tất rỗng | Phát phần tử đó | Phát phần tử đầu theo thứ tự |
| `one()` | `Mono<T>` | Hoàn tất rỗng | Phát phần tử đó | Báo lỗi `IncorrectResultSizeDataAccessException` |
| `all()` | `Flux<T>` | Hoàn tất rỗng | Phát một phần tử | Phát các phần tử phù hợp |
| `count()` | `Mono<Long>` | Phát `0L` | Phát `1L` | Phát số lượng phù hợp |
| `exists()` | `Mono<Boolean>` | Phát `false` | Phát `true` | Phát `true` |

Nếu phiên bản và module hỗ trợ `page(Pageable)`, phép này trả `Mono<Page<T>>`: một phần tử Page chứa nội dung cùng metadata phân trang. Trang không có nội dung vẫn là một đối tượng Page, không đồng nghĩa publisher rỗng.

So với fluent query đồng bộ:

- `Optional<T>` ở `first` và `one` được thay bằng `Mono<T>` có thể rỗng.
- `List<T>` ở `all` được thay bằng `Flux<T>`.
- `long` và `boolean` được đưa vào `Mono<Long>` và `Mono<Boolean>`.

Không tự bọc kết quả thành `Mono<Optional<T>>` hoặc `Mono<Flux<T>>` nếu tầng gọi không có một hợp đồng đặc biệt yêu cầu các lớp lồng nhau đó.

## 5. first(): nhận phần tử đầu theo thứ tự

```java
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(
    Sort.Order.asc("displayName"),
    Sort.Order.asc("id")
);

Mono<Customer> firstCustomer = customerRepository.findBy(
    example,
    query -> query
        .sortBy(sort)
        .first()
);
```

Khi được subscribe và thực thi thành công trên bộ dữ liệu minh họa, publisher phát khách hàng 101 rồi hoàn tất.

Tên An đứng trước Chi theo giả định thứ tự của ví dụ. Hai bản ghi cùng tên An được phân định bằng ID tăng dần.

Nếu không có `Sort`, không nên hiểu “đầu tiên” là ID nhỏ nhất, bản ghi mới nhất hoặc thứ tự chèn. Tên thuộc tính trong Sort là tên domain như `displayName`, không phải tên cột hay tên getter.

`first()` cho phép có nhiều bản ghi phù hợp. Nó chọn một phần tử và không dùng để xác nhận kết quả duy nhất. Nếu nghiệp vụ yêu cầu phát hiện trùng dữ liệu, cần hợp đồng của `one()`.

## 6. one(): tối đa một kết quả, lỗi nếu có nhiều

```java
Mono<Customer> uniqueCustomer = customerRepository.findBy(
    example,
    query -> query.one()
);
```

Vì `example` quốc gia VN phù hợp với ba khách hàng, việc thực thi báo lỗi `org.springframework.dao.IncorrectResultSizeDataAccessException`.

Nếu dùng một Example tìm quốc gia TH, publisher phát khách hàng 103. Nếu tìm JP, publisher hoàn tất rỗng.

`one()` không có nghĩa bắt buộc phải tìm thấy một phần tử. Nó yêu cầu kết quả không có nhiều hơn một phần tử. Muốn yêu cầu đúng một phần tử, ứng dụng phải xử lý thêm trường hợp rỗng:

```java
Mono<Customer> requiredCustomer = customerRepository.findBy(
    example,
    query -> query.one()
).switchIfEmpty(
    Mono.error(new IllegalStateException(
        "Không tìm thấy khách hàng"
    ))
);
```

Hai tình huống vẫn được phân biệt:

- Không có dữ liệu: fallback của `switchIfEmpty` phát lỗi ứng dụng.
- Có nhiều dữ liệu: lỗi cardinality của `one()` được truyền xuống.

Thêm `sortBy` trước `one()` không làm ba kết quả biến thành một. Nếu chỉ muốn chọn phần tử đứng đầu, hãy dùng `first()`.

Cũng không nên dùng `all().take(1).singleOrEmpty()` để kiểm tra duy nhất: `take(1)` đã giới hạn luồng còn một phần tử và che mất việc nguồn có thể có nhiều kết quả.

## 7. all(): nhiều phần tử dưới dạng Flux

```java
Flux<Customer> customers = customerRepository.findBy(
    example,
    query -> query
        .sortBy(sort)
        .all()
);
```

Với dữ liệu minh họa, luồng phát lần lượt các khách hàng 101, 102 và 104 theo thứ tự đã chọn, rồi hoàn tất.

Điểm khác với biến thể đồng bộ là `all()` trả `Flux<Customer>`, không trả `List<Customer>`. Ứng dụng có thể biến đổi từng phần tử khi chúng đi qua pipeline:

```java
public record CustomerSummary(
    Long id,
    String displayName
) {}
```

```java
Flux<CustomerSummary> summaries = customers.map(
    customer -> new CustomerSummary(
        customer.getId(),
        customer.getDisplayName()
    )
);
```

Ví dụ record dùng Java 17 trở lên; DTO class thông thường cũng có thể thay thế.

Nếu tầng gọi thực sự cần danh sách:

```java
import java.util.List;

Mono<List<Customer>> customerList = customers.collectList();
```

`collectList()` đợi nguồn hoàn tất và gom các phần tử vào bộ nhớ. Khi nguồn rỗng, nó phát một danh sách rỗng thay vì hoàn tất không có phần tử.

Do đó:

```text
Flux rỗng
    -> collectList()
    -> Mono phát List rỗng
```

Không dùng `collectList()` cho tập dữ liệu có thể rất lớn nếu nghiệp vụ không cần toàn bộ danh sách.

### 7.1. Backpressure không thay thế phân trang nghiệp vụ

Flux tham gia giao thức backpressure: subscriber có thể yêu cầu số phần tử mà nó sẵn sàng nhận. Tuy nhiên, điều đó không có nghĩa một request HTTP tự có số trang, tổng số trang hoặc một truy vấn giới hạn đúng bằng số phần tử đang được yêu cầu.

Cách lấy dữ liệu theo lô, buffer và truyền demand xuống driver phụ thuộc implementation. Backpressure không bảo đảm bộ nhớ luôn bị chặn ở một hằng số nhỏ và không thay thế việc thiết kế truy vấn phù hợp.

Nếu màn hình cần trang 0, kích thước 20 và tổng số kết quả, cần một API phân trang được hỗ trợ; không chỉ thêm `take(20)` vào một Flux rồi xem đó là một Page đầy đủ.

## 8. count(): Mono phát số lượng, kể cả số không

```java
Mono<Long> total = customerRepository.findBy(
    example,
    query -> query.count()
);
```

Với quốc gia VN, publisher phát `3L`. Với JP, nó phát `0L`.

Đây là điểm quan trọng:

```text
Không có bản ghi phù hợp
    -> count()
    -> onNext(0L)
    -> onComplete()
```

Nó khác với:

```text
Không có bản ghi phù hợp
    -> first()
    -> onComplete() mà không có onNext
```

Vì count phát một giá trị kể cả khi số lượng bằng không, `switchIfEmpty` không phải cách xử lý `0L`. Hãy dùng toán tử trên giá trị:

```java
Mono<Boolean> hasCustomers = total.map(
    value -> value > 0L
);
```

Nếu nhu cầu ban đầu chỉ là tồn tại, hãy dùng `exists()` trực tiếp. Ví dụ trên chỉ minh họa cách xử lý số đếm.

Cũng cần phân biệt:

```java
Mono<Long> countAtQuery = customerRepository.findBy(
    example,
    query -> query.count()
);

Mono<Long> countFromStream = customerRepository.findBy(
    example,
    query -> query.all()
).count();
```

Ở trường hợp thứ hai, Reactor đếm các phần tử đi qua Flux; luồng phải đọc các phần tử từ nguồn để hoàn thành phép đếm. Trường hợp thứ nhất yêu cầu phép đếm ở cấp truy vấn, cho implementation cơ hội dùng cơ chế đếm phù hợp với kho.

Không khẳng định mọi module đều sinh SQL COUNT hoặc phép đếm luôn rẻ. Chi phí phụ thuộc điều kiện, index, đặc tính kho và chiến lược thực thi.

## 9. exists(): Mono phát true hoặc false

```java
Mono<Boolean> found = customerRepository.findBy(
    example,
    query -> query.exists()
);
```

Với điều kiện VN, publisher phát `true`; với JP, nó phát `false`.

`false` là một phần tử hợp lệ nên đoạn mã sau không chuyển false thành true:

```java
Mono<Boolean> result = found.switchIfEmpty(
    Mono.just(true)
);
```

Fallback chỉ dùng khi nguồn hoàn tất không phát phần tử. Nó không được chọn vì phần tử Boolean có giá trị false.

Để xử lý hai nhánh:

```java
Mono<String> message = found.map(
    exists -> exists
        ? "Có khách hàng phù hợp"
        : "Không có khách hàng phù hợp"
);
```

Nếu mỗi nhánh cần một thao tác bất đồng bộ khác, dùng `flatMap` và trả về publisher phù hợp từ từng nhánh.

Một số cách như `all().hasElements()` cũng có thể trả lời có phần tử hay không ở cấp luồng. Tuy nhiên, khi đang xây truy vấn fluent và chỉ cần sự tồn tại, `query.exists()` diễn đạt trực tiếp nhu cầu để module lựa chọn cách thực thi. Không mặc định mọi cách viết có cùng truy vấn xuống kho.

Kiểm tra tồn tại không bảo đảm dữ liệu sẽ không đổi trước bước ghi tiếp theo. Nếu email phải duy nhất, vẫn cần cơ chế duy nhất và xử lý xung đột phù hợp với kho; `exists()` không tự khóa khoảng thời gian giữa kiểm tra và ghi.

## 10. page(Pageable): một Page được phát qua Mono

Khi phiên bản và module hỗ trợ thao tác phân trang reactive:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(0, 20, sort);

Mono<Page<Customer>> customerPage =
    customerRepository.findBy(
        example,
        query -> query.page(pageable)
    );
```

`page` trong ví dụ là một phép kết thúc fluent. Kết quả là publisher phát một Page, không phải Flux chỉ phát nội dung của trang.

Với điều kiện VN và kích thước 20:

- Nội dung trang có ba khách hàng.
- Tổng số phần tử phù hợp là ba theo kết quả truy vấn phân trang.
- Page chứa thông tin chỉ số trang, kích thước và các metadata liên quan.

Nếu trang không có nội dung, kiểm tra `page.isEmpty()` hoặc `page.getContent().isEmpty()` bên trong toán tử reactive. Không dùng `switchIfEmpty` với kỳ vọng nó nhận diện một Page có nội dung rỗng.

Ví dụ chuyển nội dung sang DTO và giữ metadata:

```java
Mono<Page<CustomerSummary>> summaryPage =
    customerPage.map(page -> page.map(
        customer -> new CustomerSummary(
            customer.getId(),
            customer.getDisplayName()
        )
    ));
```

Có hai phép map khác nhau:

- `Mono.map` biến đổi đối tượng Page được phát.
- `Page.map` biến đổi từng phần tử bên trong Page.

Cách chuyển đổi này diễn ra sau khi đọc Customer; nó không tự tạo projection tại kho dữ liệu.

Metadata tổng có thể yêu cầu thêm công việc đếm. Không khẳng định mọi lần gọi luôn phát ra đúng hai truy vấn. Nếu chỉ cần tiếp tục lấy dữ liệu mà không cần tổng, hãy đối chiếu các API Slice, giới hạn hoặc cuộn mà module và phiên bản thực sự hỗ trợ.

## 11. Projection trước phép kết thúc

Nếu module hỗ trợ projection interface:

```java
public interface CustomerView {
    Long getId();
    String getDisplayName();
}
```

```java
Flux<CustomerView> views = customerRepository.findBy(
    example,
    query -> query
        .as(CustomerView.class)
        .sortBy(sort)
        .all()
);
```

Có thể chọn `first()` thay `all()` để nhận `Mono<CustomerView>` trong trường hợp được hỗ trợ.

`as(...)` cấu hình kiểu kết quả, còn `all()` hoặc `first()` kết thúc yêu cầu fluent. Không mặc định một phép đổi kiểu kết quả làm truy vấn chỉ đọc đúng các cột hoặc field xuất hiện trong projection; cần xác minh implementation.

Projection không tự loại bỏ bản ghi trùng và không đổi `one()` thành phép kiểm tra số giá trị tên khác nhau. Các loại projection interface, DTO theo constructor và projection lồng nhau cũng không có mức hỗ trợ đồng nhất ở mọi module.

## 12. Subscription: phép kết thúc fluent chưa phải subscribe

Tên gọi “phép kết thúc” có nghĩa kết thúc phần xây dựng fluent query và trả về publisher. Nó không có nghĩa mã ứng dụng đã nhận dữ liệu ngay tại dòng gọi.

Với publisher truy vấn reactive thông thường, công việc đọc diễn ra khi có subscription. Tuy nhiên, mã Java tạo probe, xác thực đối số hoặc gọi callback có thể chạy ngay lúc xây pipeline, tùy cách API được gọi và implementation.

Vì vậy, cần tách hai thời điểm:

| Thời điểm | Công việc có thể xảy ra |
| --- | --- |
| Xây pipeline | Tạo probe, tạo Example, cấu hình fluent, xác thực đầu vào |
| Subscription và thực thi | Đọc dữ liệu, phát phần tử, hoàn tất hoặc truyền lỗi |

Một service nên trả publisher đã kết hợp đầy đủ cho tầng gọi. Trong luồng request được framework reactive quản lý, framework đảm nhiệm subscription.

Không gọi `subscribe()` bên trong service chỉ để lấy dữ liệu rồi trả một biến bên ngoài:

- Callback xử lý dữ liệu có thể chạy sau khi phương thức đã trả về.
- Subscription riêng làm tách lỗi và cancellation khỏi luồng request.
- Tầng gọi không còn kiểm soát được đầy đủ vòng đời truy vấn.

Cũng không gọi `block()` trên luồng cần giữ tính non-blocking chỉ để đổi `Mono<Customer>` thành Customer. Hãy kết hợp bằng `map`, `flatMap`, `switchIfEmpty` rồi trả publisher.

Một publisher truy vấn không mặc nhiên là cache kết quả. Subscribe lại có thể thực thi lại truy vấn và nhìn thấy dữ liệu mới; không suy ra hai subscription sẽ dùng cùng dữ liệu hoặc cùng transaction.

## 13. Ví dụ service trả một Mono hoàn chỉnh

Phương thức dưới đây được đặt trong service đã có `customerRepository`:

```java
public Mono<Customer> findRequiredByEmail(String email) {
    return Mono.defer(() -> {
        if (email == null || email.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                "Email tìm kiếm không được để trống"
            ));
        }

        Customer probe = new Customer();
        probe.setEmail(email);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnoreNullValues()
            .withMatcher(
                "email",
                ExampleMatcher.GenericPropertyMatchers.exact()
            );

        Example<Customer> emailExample =
            Example.of(probe, matcher);

        return customerRepository.findBy(
            emailExample,
            query -> query.one()
        ).switchIfEmpty(
            Mono.error(new IllegalStateException(
                "Không tìm thấy khách hàng"
            ))
        );
    });
}
```

Đoạn mã dùng `String.isBlank()` của Java 11 trở lên, cùng các import Reactor và Spring Data đã giới thiệu.

Hành vi:

1. Kiểm tra đầu vào khi publisher được subscribe.
2. Tạo probe riêng trong mỗi lần thực thi supplier của `Mono.defer`.
3. Tra cứu với hợp đồng tối đa một kết quả.
4. Đổi trường hợp không có dữ liệu thành lỗi ứng dụng.
5. Truyền lỗi nhiều kết quả hoặc lỗi truy vấn về tầng gọi.

`Mono.defer` trì hoãn cả phần tạo truy vấn bên trong supplier. Nó không biến một lời gọi chặn thành I/O non-blocking và không tự thay thế transaction.

Việc tạo probe riêng giúp tránh chia sẻ một đối tượng mẫu có thể bị sửa giữa các subscription. Không sửa probe sau khi đã xây pipeline với kỳ vọng đó là cách thay đổi điều kiện an toàn.

Quy tắc so khớp email phải nhất quán với nghiệp vụ và kho dữ liệu, bao gồm chuẩn hóa, hoa thường và collation. So khớp exact trong matcher không tự tạo unique constraint hoặc unique index.

## 14. Xử lý lỗi đúng vị trí

Các lỗi đọc dữ liệu trong quá trình reactive execution được truyền qua tín hiệu lỗi. Một khối try/catch bao quanh việc tạo Mono không bắt được các lỗi phát sinh về sau khi publisher được subscribe.

Có thể ánh xạ riêng lỗi nhiều kết quả:

```java
import org.springframework.dao.IncorrectResultSizeDataAccessException;
```

```java
Mono<Customer> customer = findRequiredByEmail(
    "shared@example.test"
).onErrorMap(
    IncorrectResultSizeDataAccessException.class,
    error -> new IllegalStateException(
        "Dữ liệu khách hàng không đáp ứng yêu cầu duy nhất",
        error
    )
);
```

Không nên chuyển mọi lỗi thành nguồn rỗng:

```java
Mono<Customer> hiddenFailure = customerRepository.findBy(
    example,
    query -> query.one()
).onErrorResume(error -> Mono.empty());
```

Cách xử lý đó có thể làm lỗi dữ liệu trùng, lỗi kết nối và lỗi truy vấn đều bị hiểu thành không tìm thấy khách hàng.

Cũng cần phân biệt lỗi xảy ra trước khi publisher được trả về, chẳng hạn xác thực đối số hoặc lỗi trong phần xây truy vấn được thực thi ngay. Nếu hợp đồng ứng dụng cần đưa cả việc xây truy vấn vào luồng lỗi reactive, có thể đặt phần đó trong `Mono.defer` hoặc `Flux.defer` phù hợp. Không mặc định mọi exception của một phương thức trả Mono đều tự xuất hiện dưới dạng tín hiệu lỗi.

## 15. Kết hợp kết quả bằng map và flatMap

Dùng `map` khi hàm chuyển đổi trả một giá trị thông thường:

```java
Mono<CustomerSummary> summary = findRequiredByEmail(
    "chi@example.test"
).map(customer -> new CustomerSummary(
    customer.getId(),
    customer.getDisplayName()
));
```

Nếu bước tiếp theo đã trả một Mono, cần `flatMap` để kết hợp vào luồng. Ví dụ giả định có service cung cấp phương thức:

```java
Mono<CustomerSummary> enrich(Customer customer);
```

Cách kết hợp:

```java
Mono<CustomerSummary> summary = findRequiredByEmail(
    "chi@example.test"
).flatMap(customer -> summaryService.enrich(customer));
```

Dùng `map` cho hàm trả Mono sẽ tạo một lớp publisher lồng nhau thay vì trực tiếp nhận luồng kết quả mong muốn.

Với Flux có các bước bất đồng bộ, `flatMap` có thể làm thứ tự phát kết quả khác thứ tự truy vấn vì các bước hoàn tất ở thời điểm khác nhau. Nếu phải giữ thứ tự bằng cách xử lý lần lượt, cân nhắc `concatMap`; đồng thời đánh giá độ song song và hiệu năng theo yêu cầu.

Một điểm tương tự là cùng tên phương thức nhưng khác tầng API:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `query.all()` | Kết thúc fluent query để nhận Flux các kết quả |
| `flux.all(predicate)` | Kiểm tra mọi phần tử của Flux có thỏa predicate hay không |
| `query.count()` | Yêu cầu phép đếm qua API truy vấn |
| `flux.count()` | Đếm các phần tử đi qua một Flux |

Hãy xác định biến đang là fluent query hay publisher trước khi diễn giải ý nghĩa của toán tử.

## 16. Các tình huống cần tự đối chiếu

| Tình huống | Hành vi cần hiểu |
| --- | --- |
| Tìm JP bằng first | Mono hoàn tất rỗng |
| Tìm JP bằng one | Mono hoàn tất rỗng, không lỗi vì thiếu dữ liệu |
| Tìm JP bằng count | Mono phát 0L |
| Tìm JP bằng exists | Mono phát false |
| Tìm JP bằng all rồi collectList | Mono phát một danh sách rỗng |
| Tìm VN bằng one | Tín hiệu lỗi nhiều kết quả |
| Tìm VN bằng first với thứ tự tên rồi ID | Phát khách hàng 101 |
| Subscribe hai lần vào nguồn truy vấn | Có thể thực thi hai lần, không mặc định dùng cache |
| exists trả false rồi có request khác ghi dữ liệu | Kết quả kiểm tra trước không ngăn xung đột khi ghi |

Các bảng trong bài mô tả hợp đồng và kết quả logic trên dữ liệu minh họa. Khi triển khai, cần đối chiếu đúng module, mapping và phiên bản của dự án.

## 17. Bài tập tự kiểm tra

1. Vì sao không dùng `Optional.empty()` làm giá trị trả trực tiếp của reactive `one()`?
2. Nếu `exists()` phát false, `switchIfEmpty` có được chọn không?
3. Nếu `count()` phát 0L, đó có phải Mono rỗng không?
4. Vì sao `all().collectList()` có thể gây áp lực bộ nhớ?
5. `first()` không có Sort có bảo đảm trả khách hàng mới nhất không?
6. Vì sao `subscribe()` trong service không phải cách phù hợp để biến kết quả truy vấn thành một biến trả về đồng bộ?
7. Khi module không hỗ trợ projection mong muốn, chuyển từng Customer sang DTO bằng `map` có đồng nghĩa kho chỉ đọc các field DTO không?

Gợi ý đáp án:

1. Reactive one trả `Mono<T>`; không có dữ liệu được biểu diễn bằng hoàn tất không phát phần tử.
2. Không. False là một phần tử đã được phát.
3. Không. 0L là giá trị số đếm.
4. Vì các phần tử được gom lại cho đến khi nguồn hoàn tất.
5. Không. Cần thứ tự theo thuộc tính nghiệp vụ phù hợp.
6. Vì subscription có vòng đời bất đồng bộ riêng, làm tách kết quả và lỗi khỏi luồng trả về.
7. Không. Map biến đổi dữ liệu đã đọc, không tự giới hạn dữ liệu truy vấn tại kho.

Nguyên tắc áp dụng là chọn phép kết thúc theo nhu cầu dữ liệu, giữ nguyên ý nghĩa rỗng và lỗi, rồi kết hợp publisher đến đúng tầng chịu trách nhiệm subscription. Khả năng reactive thực tế phải được hỗ trợ xuyên suốt bởi module và driver lưu trữ.
