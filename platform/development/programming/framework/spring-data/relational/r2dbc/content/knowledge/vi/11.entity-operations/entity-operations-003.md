# Select một thực thể, nhiều thực thể và trường hợp không có kết quả

Trong Spring Data Relational R2DBC, thao tác đọc dữ liệu thường trả về publisher của Reactor. Kiểu trả về cho biết ứng dụng mong đợi một thực thể, một tập thực thể hay có thể không có hàng nào phù hợp. Chọn đúng kiểu trả về giúp xử lý rõ ràng trường hợp tìm thấy, không tìm thấy và dữ liệu không đúng số lượng mong đợi.

Hai kiểu thường dùng nhất là `Mono<T>` và `Flux<T>`:

- `Mono<T>` biểu diễn kết quả có tối đa một phần tử. Publisher có thể phát ra một entity rồi hoàn tất, hoặc hoàn tất rỗng nếu không có kết quả.
- `Flux<T>` biểu diễn từ không đến nhiều phần tử. Publisher phát ra từng entity rồi hoàn tất; nếu không có hàng nào phù hợp, nó hoàn tất mà không phát phần tử.

Không có kết quả không đồng nghĩa với lỗi. Một truy vấn không tìm thấy bản ghi thường là kết quả hợp lệ của nghiệp vụ. Ngược lại, lỗi kết nối, lỗi SQL hoặc lỗi ánh xạ được truyền dưới dạng tín hiệu lỗi reactive.

Bài học này trình bày cách đọc một entity, đọc nhiều entity, xử lý kết quả rỗng, phân biệt truy vấn đơn với truy vấn giới hạn một hàng, và lựa chọn API phù hợp trong repository, `@Query` và `DatabaseClient`.

## 1. Mono và Flux biểu diễn kết quả truy vấn

Trong Reactor, một publisher có thể phát ra dữ liệu, hoàn tất hoặc kết thúc bằng lỗi. Số lượng phần tử tối đa là điểm phân biệt cơ bản giữa `Mono` và `Flux`.

| Kiểu trả về | Số phần tử | Khi không có hàng |
|---|---:|---|
| `Mono<T>` | 0 hoặc 1 | Hoàn tất rỗng (`Mono.empty()`) |
| `Flux<T>` | 0 đến nhiều | Hoàn tất rỗng, không phát phần tử |
| `Mono<List<T>>` | Một list | Phát ra list rỗng nếu truy vấn không có hàng |
| `Mono<Boolean>` | Một giá trị boolean | Phát `true` hoặc `false` tùy phép kiểm tra |

Ví dụ minh họa:

~~~text
Truy vấn theo ID, kết quả có một hàng:
Mono<Customer>  ---- Customer ---- complete

Truy vấn theo ID, không có hàng:
Mono<Customer>  ------------------ complete (empty)

Truy vấn theo điều kiện, có nhiều hàng:
Flux<Customer>  -- C1 -- C2 -- C3 -- complete

Truy vấn theo điều kiện, không có hàng:
Flux<Customer>  ------------------ complete (empty)
~~~

`Mono<T>` không phải là một đối tượng có thể chứa `null` để biểu diễn không tìm thấy. Reactor không cho phép phát ra `null`; trường hợp không có phần tử được biểu diễn bằng publisher rỗng.

Tương tự, `Flux<T>` rỗng vẫn là một publisher hoàn tất bình thường. Không cần ném exception chỉ vì danh sách kết quả không có phần tử, trừ khi quy tắc nghiệp vụ yêu cầu phải có ít nhất một bản ghi.

## 2. Đọc một thực thể bằng ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` cung cấp các thao tác đọc phổ biến cho repository reactive. Với một entity có khóa chính, phương thức `findById` thường trả về `Mono<T>`.

Ví dụ entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    // Constructor, getters và setters
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Đọc một khách hàng theo ID:

~~~java
Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Nếu tồn tại hàng có ID tương ứng, publisher phát ra một `Customer`. Nếu không tồn tại, publisher hoàn tất rỗng. Repository trả về publisher; truy vấn chỉ thực sự chạy khi publisher được subscribe bởi framework hoặc subscriber ở phía gọi.

### 2.1. Xử lý trường hợp không tìm thấy

Có thể dùng `switchIfEmpty` để thay publisher rỗng bằng một publisher khác:

~~~java
Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Đoạn mã chuyển trường hợp không tìm thấy thành lỗi nghiệp vụ. Cách này phù hợp với endpoint yêu cầu tài nguyên phải tồn tại, chẳng hạn lấy chi tiết khách hàng theo ID.

Nếu không tìm thấy là trường hợp bình thường, có thể giữ nguyên `Mono.empty()` để tầng gọi quyết định cách phản hồi.

Một lựa chọn khác là trả về giá trị mặc định:

~~~java
Mono<Customer> getCustomerOrDefault(Long id) {
    return customerRepository.findById(id)
            .defaultIfEmpty(Customer.guest());
}
~~~

Chỉ dùng giá trị mặc định khi nghiệp vụ thực sự định nghĩa một đối tượng thay thế. Không nên âm thầm tạo một entity giả để che việc thiếu dữ liệu, vì tầng gọi có thể nhầm nó với bản ghi đã lưu trong database.

### 2.2. Phân biệt không tìm thấy với lỗi truy vấn

Không tìm thấy thường tạo publisher rỗng. Lỗi database tạo tín hiệu lỗi:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(id)))
        .onErrorMap(
                DataAccessException.class,
                DatabaseOperationException::new);
~~~

Không nên dùng `onErrorResume` để chuyển mọi lỗi database thành `Mono.empty()`. Làm vậy có thể biến lỗi kết nối hoặc lỗi SQL thành thông báo "không tìm thấy", khiến nguyên nhân thật bị che khuất.

Hãy phân loại lỗi theo ý nghĩa:

- Không có hàng phù hợp: publisher rỗng.
- Database không truy cập được: publisher lỗi.
- SQL sai hoặc mapping sai: publisher lỗi.
- Quy tắc nghiệp vụ không chấp nhận việc thiếu entity: chủ động chuyển publisher rỗng thành lỗi domain.

## 3. Đọc nhiều thực thể bằng Flux

Khi điều kiện truy vấn có thể trả về nhiều hàng, dùng `Flux<T>`. Ví dụ repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByCity(String city);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByLastNameContaining(String keyword);
}
~~~

Các phương thức trên có thể phát ra không, một hoặc nhiều khách hàng. Nếu không có khách hàng phù hợp, chúng hoàn tất rỗng.

Ví dụ sử dụng:

~~~java
Flux<Customer> customersInHanoi =
        customerRepository.findByCity("Hanoi");
~~~

Không cần kiểm tra `null` trước khi duyệt kết quả. Một `Flux` rỗng đơn giản là không phát ra `onNext`; subscriber vẫn nhận tín hiệu hoàn tất.

### 3.1. Duyệt và xử lý từng phần tử

Có thể xử lý từng entity bằng các toán tử Reactor:

~~~java
Flux<String> customerNames =
        customerRepository.findByCity("Hanoi")
                .map(Customer::getFullName);
~~~

Nếu cần gọi một thao tác reactive cho mỗi entity, dùng `flatMap`:

~~~java
Flux<CustomerSummary> summaries =
        customerRepository.findByCity("Hanoi")
                .flatMap(customer ->
                        summaryService.createSummary(customer));
~~~

`flatMap` có thể cho phép các publisher con chạy đồng thời và kết quả có thể không giữ thứ tự nguồn. Nếu cần xử lý tuần tự và giữ thứ tự, cân nhắc `concatMap`. Nếu cần giới hạn số thao tác đồng thời, dùng biến thể có tham số concurrency phù hợp.

Không gọi `subscribe()` bên trong `map` hoặc `flatMap` để khởi chạy một luồng độc lập. Hãy trả về publisher từ callback để Reactor quản lý toàn bộ chuỗi.

### 3.2. Thu thập kết quả thành List

Nếu tập kết quả nhỏ và tầng gọi cần một danh sách hoàn chỉnh, có thể dùng `collectList`:

~~~java
Mono<List<Customer>> findCustomersAsList(String city) {
    return customerRepository.findByCity(city)
            .collectList();
}
~~~

`collectList()` luôn phát ra một list khi nguồn hoàn tất thành công. Nếu không có hàng nào, list phát ra là list rỗng:

~~~text
Flux<Customer> rỗng
       |
       | collectList()
       v
Mono<List<Customer>>
       |
       v
List<Customer> = []
~~~

Khác với `Mono<Customer>`, `Mono<List<Customer>>` trong trường hợp này không rỗng khi truy vấn không có hàng; nó phát ra một list rỗng. Nếu truy vấn lỗi, lỗi vẫn được truyền tới subscriber.

Không dùng `collectList()` cho tập kết quả không giới hạn hoặc rất lớn. Toàn bộ entity sẽ được giữ trong bộ nhớ cho tới khi nguồn hoàn tất. Với dữ liệu lớn, hãy xử lý từng phần tử hoặc chia trang theo nhu cầu.

## 4. Các phương thức đọc có sẵn của repository

Một số phương thức phổ biến từ `ReactiveCrudRepository`:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `findById(id)` | `Mono<T>` | Đọc tối đa một entity theo khóa chính |
| `findById(publisherOfId)` | `Mono<T>` | Đọc theo ID được phát ra bởi publisher |
| `findAll()` | `Flux<T>` | Đọc tất cả entity |
| `findAllById(ids)` | `Flux<T>` | Đọc các entity có ID nằm trong tập đầu vào |
| `existsById(id)` | `Mono<Boolean>` | Kiểm tra entity có tồn tại hay không |
| `count()` | `Mono<Long>` | Đếm số entity |
| `deleteById(id)` | `Mono<Void>` | Xóa theo ID, không phát entity đã xóa |

Một số lưu ý:

- `findAll()` có thể trả về rất nhiều hàng. Hãy cân nhắc phân trang hoặc điều kiện lọc thay vì tải toàn bộ bảng.
- `findAllById(...)` trả về các entity tìm được; các ID không tồn tại không tạo ra entity giả hoặc phần tử `null`.
- `existsById(...)` phù hợp khi chỉ cần biết có tồn tại hay không, không cần tải toàn bộ entity.
- `count()` trả về `0` khi bảng hoặc tập dữ liệu không có hàng phù hợp.
- `deleteById(...)` hoàn tất mà không phát dữ liệu; nếu cần biết có bản ghi bị xóa hay không, cần thiết kế cách kiểm tra riêng.

### 4.1. Kiểm tra tồn tại thay vì tải entity

Nếu chỉ cần trả lời câu hỏi "ID này có tồn tại không?", dùng:

~~~java
Mono<Boolean> customerExists(Long id) {
    return customerRepository.existsById(id);
}
~~~

Không cần tải toàn bộ entity chỉ để kiểm tra `customer != null`. `existsById` diễn đạt đúng ý định và cho phép framework tối ưu truy vấn theo khả năng của database.

Với điều kiện tùy chỉnh, có thể khai báo derived query:

~~~java
Mono<Boolean> existsByEmail(String email);
~~~

### 4.2. Đếm kết quả

Ví dụ:

~~~java
Mono<Long> countActiveCustomers() {
    return customerRepository.countByActiveTrue();
}
~~~

Phương thức đếm trả về `0` khi không có bản ghi. Đây là một giá trị kết quả, không phải publisher rỗng. Cần phân biệt `Mono<Long>` phát ra `0L` với `Mono.empty()`.

## 5. Derived query: chọn Mono hay Flux theo ý nghĩa dữ liệu

Spring Data có thể tạo truy vấn từ tên phương thức repository. Kiểu trả về nên phản ánh số kết quả nghiệp vụ mong đợi.

Ví dụ:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByCity(String city);

    Mono<Customer> findFirstByCityOrderByCreatedAtDesc(String city);

    Flux<Customer> findTop10ByCityOrderByCreatedAtDesc(String city);
}
~~~

Cách đọc:

- `findByEmail`: dùng `Mono<Customer>` nếu email được kỳ vọng là duy nhất.
- `findByCity`: dùng `Flux<Customer>` vì một thành phố có thể có nhiều khách hàng.
- `findFirstByCityOrderByCreatedAtDesc`: lấy tối đa một khách hàng đầu tiên theo thứ tự tạo mới nhất.
- `findTop10ByCityOrderByCreatedAtDesc`: giới hạn kết quả ở tối đa mười khách hàng theo thứ tự chỉ định.

Nếu phương thức trả về `Mono<Customer>` nhưng truy vấn thực tế có nhiều hàng phù hợp, Spring Data có thể báo lỗi kích thước kết quả không đúng thay vì chọn ngẫu nhiên một entity. Điều này giúp phát hiện sự không nhất quán giữa kỳ vọng "một kết quả" và dữ liệu thực tế.

### 5.1. Bảo đảm tính duy nhất ở database

Nếu email phải duy nhất, đừng chỉ dựa vào việc repository trả về `Mono<Customer>`. Hãy tạo ràng buộc `UNIQUE` trong database:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email_address);
~~~

Nếu chỉ kiểm tra trước khi insert:

~~~java
return customerRepository.existsByEmail(email)
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new DuplicateEmailException(email));
            }

            return customerRepository.save(customer);
        });
~~~

Hai request đồng thời vẫn có thể cùng nhận `false` trước khi một request insert. Ràng buộc `UNIQUE` mới là lớp bảo vệ cuối cùng. Ứng dụng cần xử lý lỗi vi phạm unique constraint khi lưu.

### 5.2. Khi nghiệp vụ cần lấy bản ghi đầu tiên

Nếu có nhiều hàng và nghiệp vụ thực sự cần một hàng đầu tiên, hãy xác định thứ tự rõ ràng:

~~~java
Mono<Customer> findNewestCustomer(String city) {
    return customerRepository
            .findFirstByCityOrderByCreatedAtDesc(city);
}
~~~

Không dùng một truy vấn không có `ORDER BY` rồi giả định hàng đầu tiên luôn là hàng mới nhất hoặc ổn định. Thứ tự hàng trong SQL không được bảo đảm nếu không yêu cầu sắp xếp.

Tên phương thức `First` hoặc `Top` thể hiện ý định giới hạn kết quả. Nếu chỉ cần một hàng bất kỳ, vẫn nên xác định tiêu chí chọn phù hợp với nghiệp vụ để kết quả có thể dự đoán.

## 6. Truy vấn tùy chỉnh bằng @Query

Với SQL tùy chỉnh, kiểu trả về vẫn quyết định cách ứng dụng nhận kết quả.

Truy vấn một khách hàng theo email:

~~~java
@Query("""
    SELECT id, full_name, email_address
    FROM customer
    WHERE email_address = :email
    """)
Mono<Customer> findOneByEmail(@Param("email") String email);
~~~

Truy vấn nhiều khách hàng theo thành phố:

~~~java
@Query("""
    SELECT id, full_name, email_address
    FROM customer
    WHERE city = :city
    ORDER BY full_name
    """)
Flux<Customer> findAllByCity(@Param("city") String city);
~~~

Trong trường hợp đầu, truy vấn kỳ vọng tối đa một hàng. Nếu dữ liệu có nhiều hàng cùng email, lỗi kích thước kết quả có thể xuất hiện; nên có unique constraint nếu email phải duy nhất.

Trong trường hợp thứ hai, mọi hàng phù hợp được phát lần lượt qua `Flux`. Nếu không có hàng, `Flux` hoàn tất rỗng.

Không nối trực tiếp dữ liệu đầu vào vào chuỗi SQL. Dùng named parameter hoặc cơ chế bind parameter để truyền giá trị. Tên bảng và cột trong SQL phải khớp schema vật lý; annotation mapping của entity không tự viết lại SQL literal tùy chỉnh.

## 7. Đọc kết quả bằng DatabaseClient

`DatabaseClient` cho phép thực hiện SQL trực tiếp và chọn cách lấy kết quả theo số lượng hàng.

Ví dụ đọc tối đa một hàng:

~~~java
Mono<Customer> findCustomer(Long id) {
    return databaseClient.sql("""
            SELECT id, full_name, email_address
            FROM customer
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("full_name", String.class),
                    row.get("email_address", String.class)))
            .one();
}
~~~

`one()` biểu diễn kỳ vọng có tối đa một hàng. Nếu không có hàng, publisher hoàn tất rỗng. Nếu có nhiều hơn một hàng, API báo lỗi thay vì tự ý chọn một hàng.

Đọc một hàng đầu tiên:

~~~java
Mono<Map<String, Object>> firstCustomer =
        databaseClient.sql("""
                SELECT id, full_name, email_address
                FROM customer
                WHERE city = :city
                ORDER BY created_at DESC
                """)
                .bind("city", "Hanoi")
                .fetch()
                .first();
~~~

`first()` trả về hàng đầu tiên nếu có, hoặc publisher rỗng nếu không có hàng. Nó không xác nhận rằng chỉ có một hàng phù hợp. Nếu thứ tự quan trọng, SQL phải có `ORDER BY`.

Đọc tất cả hàng:

~~~java
Flux<Map<String, Object>> customers =
        databaseClient.sql("""
                SELECT id, full_name, email_address
                FROM customer
                WHERE city = :city
                ORDER BY full_name
                """)
                .bind("city", "Hanoi")
                .fetch()
                .all();
~~~

`all()` trả về `Flux` các hàng. Nếu truy vấn không có hàng, `Flux` hoàn tất rỗng.

### 7.1. Phân biệt one() và first()

| API | Không có hàng | Có đúng một hàng | Có nhiều hàng |
|---|---|---|---|
| `one()` | Hoàn tất rỗng | Phát hàng đó | Báo lỗi vì vượt quá một hàng |
| `first()` | Hoàn tất rỗng | Phát hàng đó | Phát hàng đầu tiên và không yêu cầu tính duy nhất |
| `all()` | Flux rỗng | Phát một hàng | Phát tất cả hàng |

Đây là khác biệt quan trọng khi thiết kế truy vấn. Nếu nghiệp vụ yêu cầu duy nhất, `one()` giúp phát hiện dữ liệu trùng. Nếu nghiệp vụ chỉ cần một hàng theo thứ tự ưu tiên, `first()` hoặc truy vấn có giới hạn rõ ràng phù hợp hơn.

## 8. Chuyển đổi publisher nhiều hàng thành một kết quả

Đôi khi API hoặc tầng dịch vụ nhận một `Flux<T>` nhưng cần chuyển thành kết quả đơn. Reactor cung cấp một số toán tử khác nhau; mỗi toán tử mang một quy tắc số lượng riêng.

| Toán tử | Không có phần tử | Một phần tử | Nhiều phần tử |
|---|---|---|---|
| `next()` | `Mono.empty()` | Phát phần tử đó | Lấy phần tử đầu tiên rồi hủy phần còn lại |
| `single()` | Lỗi | Phát phần tử đó | Lỗi |
| `singleOrEmpty()` | `Mono.empty()` | Phát phần tử đó | Lỗi |
| `collectList()` | Phát list rỗng | Phát list một phần tử | Phát list chứa tất cả phần tử |

Ví dụ dùng `singleOrEmpty`:

~~~java
Mono<Customer> findExactlyOneOrNone(String city) {
    return customerRepository.findByCity(city)
            .filter(Customer::isPreferred)
            .singleOrEmpty();
}
~~~

Nếu không có khách hàng ưu tiên, kết quả là `Mono.empty()`. Nếu có đúng một, publisher phát entity. Nếu có nhiều hơn một, publisher lỗi để ứng dụng nhận biết dữ liệu không thỏa kỳ vọng.

Dùng `next()` khi nghiệp vụ chủ động chấp nhận lấy phần tử đầu tiên:

~~~java
Mono<Customer> findAnyCustomer(String city) {
    return customerRepository.findByCity(city)
            .next();
}
~~~

`next()` không kiểm tra tính duy nhất. Nếu dữ liệu có nhiều hàng, các hàng còn lại bị bỏ qua sau phần tử đầu. Vì vậy, không dùng `next()` để che một ràng buộc duy nhất bị vi phạm.

`single()` yêu cầu chính xác một phần tử; cả trường hợp rỗng và nhiều phần tử đều là lỗi. Dùng nó khi nghiệp vụ bắt buộc phải có đúng một kết quả và muốn coi mọi sai lệch là lỗi.

## 9. Không có hàng và cột có giá trị NULL

Cần phân biệt hai tình huống:

1. Truy vấn không trả về hàng nào.
2. Truy vấn trả về một hàng nhưng một cột trong hàng có giá trị SQL `NULL`.

Ví dụ bảng có khách hàng nhưng chưa nhập số điện thoại:

~~~sql
SELECT id, full_name, phone_number
FROM customer
WHERE id = 10;
~~~

Nếu hàng tồn tại và `phone_number` là `NULL`, Spring Data vẫn có thể tạo một `Customer`. Thuộc tính `phoneNumber` tương ứng có giá trị Java `null` nếu kiểu và mapping cho phép.

Kết quả là `Mono<Customer>` phát ra entity có trường `phoneNumber == null`, chứ không phải `Mono.empty()`.

Ngược lại, nếu không có hàng có ID 10, `Mono<Customer>` hoàn tất rỗng.

| Tình huống | Kết quả reactive |
|---|---|
| Không có hàng | `Mono.empty()` |
| Có hàng, cột nullable là SQL `NULL` | `Mono` phát entity với property tương ứng null |
| Có hàng, tất cả giá trị hợp lệ | `Mono` phát entity |
| Database hoặc SQL gặp lỗi | `Mono` phát tín hiệu lỗi |

Không dùng `defaultIfEmpty` để thay thế một cột null bên trong entity; toán tử đó xử lý publisher không phát phần tử, không xử lý từng property null. Muốn thay giá trị cột null, dùng SQL `COALESCE`, custom conversion hoặc logic sau khi entity được ánh xạ.

## 10. Xử lý không có kết quả trong tầng service và API

Cách xử lý phụ thuộc vào ý nghĩa của endpoint hoặc use case.

### 10.1. Tài nguyên bắt buộc phải tồn tại

Ví dụ endpoint lấy chi tiết khách hàng theo ID:

~~~java
public Mono<CustomerResponse> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .map(CustomerResponse::from);
}
~~~

Tầng web có thể ánh xạ `CustomerNotFoundException` thành HTTP 404 bằng exception handler. Repository không cần biết HTTP status; nó chỉ thể hiện dữ liệu không tồn tại bằng publisher rỗng.

### 10.2. Tìm kiếm có thể không có kết quả

Ví dụ tìm khách hàng theo thành phố:

~~~java
public Flux<CustomerResponse> searchCustomers(String city) {
    return customerRepository.findByCity(city)
            .map(CustomerResponse::from);
}
~~~

Nếu không có khách hàng, `Flux` hoàn tất bình thường. Endpoint trả về danh sách rỗng là một phản hồi hợp lệ; không cần biến trường hợp đó thành 404 trừ khi API contract quy định như vậy.

Nếu tầng controller thu thập kết quả thành list, nó có thể phát ra `[]` khi không có hàng.

### 10.3. Cung cấp giá trị mặc định

Ví dụ một cấu hình tùy chọn có thể dùng mặc định khi chưa có bản ghi:

~~~java
Mono<AppSetting> loadSetting(String key) {
    return settingRepository.findById(key)
            .defaultIfEmpty(AppSetting.defaultFor(key));
}
~~~

Chỉ dùng default khi giá trị mặc định là một phần của quy tắc nghiệp vụ. Với dữ liệu quan trọng như tài khoản, đơn hàng hoặc quyền truy cập, việc tự tạo giá trị thay thế có thể che giấu lỗi dữ liệu.

### 10.4. Kiểm tra rỗng bằng hasElement

Nếu cần biết một publisher có phát phần tử hay không, có thể dùng:

~~~java
Mono<Boolean> hasCustomer =
        customerRepository.findById(10L)
                .hasElement();
~~~

`hasElement()` phát `true` nếu nguồn có ít nhất một phần tử và `false` nếu nguồn hoàn tất rỗng. Với kiểm tra theo khóa chính, `existsById` thường diễn đạt mục đích tốt hơn. Với một chuỗi xử lý đã có sẵn, `hasElement()` có thể hữu ích.

## 11. Kết hợp nhiều truy vấn và kết quả rỗng

Trong reactive pipeline, kết quả rỗng ảnh hưởng đến toán tử tiếp theo.

### 11.1. flatMap chỉ chạy khi Mono có phần tử

~~~java
Mono<OrderResponse> loadOrder(Long id) {
    return orderRepository.findById(id)
            .flatMap(order ->
                    customerRepository.findById(order.getCustomerId())
                            .map(customer ->
                                    OrderResponse.from(order, customer)));
}
~~~

Nếu không tìm thấy order, callback của `flatMap` không chạy. Nếu tìm thấy order nhưng không tìm thấy customer, publisher bên trong cũng rỗng và kết quả cuối cùng rỗng.

Nếu customer là dữ liệu bắt buộc, hãy chuyển trường hợp đó thành lỗi:

~~~java
Mono<OrderResponse> loadOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)))
            .flatMap(order ->
                    customerRepository.findById(order.getCustomerId())
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(
                                            order.getCustomerId())))
                            .map(customer ->
                                    OrderResponse.from(order, customer)));
}
~~~

Cách viết này làm rõ entity nào không tồn tại và tránh để kết quả rỗng lan truyền mà tầng gọi không biết nguyên nhân.

### 11.2. zip và publisher rỗng

`Mono.zip` kết hợp các publisher khi mỗi nguồn cung cấp giá trị. Nếu một nguồn hoàn tất rỗng, phép kết hợp có thể hoàn tất rỗng mà không tạo tuple.

~~~java
Mono<CustomerDashboard> dashboard =
        customerRepository.findById(customerId)
                .zipWith(orderRepository.findLatestByCustomerId(customerId))
                .map(tuple ->
                        CustomerDashboard.from(
                                tuple.getT1(), tuple.getT2()));
~~~

Nếu không có customer hoặc không có đơn hàng gần nhất, kết quả có thể rỗng. Hãy quyết định mỗi dữ liệu là bắt buộc hay tùy chọn:

- Dữ liệu bắt buộc: dùng `switchIfEmpty(Mono.error(...))`.
- Dữ liệu tùy chọn: thay bằng publisher mặc định có ý nghĩa hoặc biểu diễn rõ trường tùy chọn trong response.
- Không được dùng giá trị giả nếu nó làm mất phân biệt giữa "không có dữ liệu" và "dữ liệu mặc định".

## 12. Giới hạn kết quả và phân trang

Không phải lúc nào cũng nên đọc toàn bộ kết quả bằng `findAll()`. Khi bảng lớn, hãy giới hạn số hàng và xác định thứ tự.

Derived query có thể giới hạn số kết quả:

~~~java
Flux<Customer> findTop20ByActiveTrueOrderByCreatedAtDesc();
~~~

Với SQL tùy chỉnh, dùng cú pháp giới hạn phù hợp với database:

~~~sql
SELECT id, full_name, email_address
FROM customer
WHERE active = TRUE
ORDER BY created_at DESC
LIMIT 20;
~~~

`LIMIT` là cú pháp phổ biến của PostgreSQL và MySQL; các hệ quản trị khác có thể dùng cú pháp khác. Spring Data R2DBC không biến một truy vấn SQL viết tay thành cú pháp portable cho mọi database.

Nếu API cần phân trang, hãy xác định rõ offset/page hoặc keyset pagination và cách lấy tổng số hàng. Truy vấn trang và truy vấn đếm thường là hai thao tác riêng. Với dữ liệu thay đổi liên tục, offset pagination có thể bỏ sót hoặc lặp bản ghi giữa các trang; keyset pagination dựa trên khóa sắp xếp ổn định thường phù hợp hơn cho tập dữ liệu lớn.

Không chuyển `Flux` lớn thành `List` chỉ để phân trang ở bộ nhớ. Hãy để database giới hạn dữ liệu ngay trong truy vấn.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Trả `Mono<T>` cho truy vấn vốn có nhiều kết quả | Có thể phát sinh lỗi kích thước kết quả | Dùng `Flux<T>` nếu nhiều hàng là hợp lệ |
| Dùng `Flux<T>` cho truy vấn bắt buộc duy nhất mà không kiểm tra | Có thể che giấu dữ liệu trùng | Dùng `Mono<T>` và unique constraint |
| Dùng `next()` để che nhiều kết quả | Chỉ lấy hàng đầu, bỏ qua dữ liệu còn lại | Dùng `one()` hoặc `singleOrEmpty()` nếu cần xác nhận tối đa một |
| Coi `Mono.empty()` là lỗi database | Xử lý sai trường hợp không tìm thấy | Phân biệt publisher rỗng và tín hiệu lỗi |
| Chuyển mọi lỗi thành empty bằng `onErrorResume` | Che lỗi SQL hoặc kết nối | Chỉ xử lý đúng loại lỗi và giữ nguyên lỗi không dự kiến |
| Dùng `defaultIfEmpty(null)` | Reactor không phát giá trị null | Dùng publisher rỗng hoặc một giá trị mặc định hợp lệ |
| Nhầm cột SQL NULL với không có hàng | Mất thông tin về bản ghi thực tế | Kiểm tra entity phát ra và property nullable |
| Dùng `collectList()` cho dữ liệu rất lớn | Tăng bộ nhớ và độ trễ | Xử lý `Flux` hoặc phân trang ở database |
| Dùng `findAll()` cho bảng lớn | Tải quá nhiều dữ liệu | Thêm điều kiện lọc, giới hạn hoặc phân trang |
| Dùng `first()` mà không có thứ tự | Hàng được chọn có thể không ổn định | Dùng `ORDER BY` hoặc derived query có sort |
| Kiểm tra tồn tại rồi insert mà không có unique constraint | Hai request đồng thời có thể tạo bản ghi trùng | Bảo vệ bằng constraint và xử lý lỗi khi insert |
| Gọi `subscribe()` bên trong service | Tạo luồng xử lý tách khỏi chuỗi trả về | Trả publisher và nối bằng toán tử Reactor |

## 14. Quy trình chọn kiểu trả về và xử lý kết quả

Khi khai báo một phương thức đọc, hãy trả lời lần lượt:

1. Điều kiện truy vấn có thể khớp nhiều hàng không?
2. Nếu chỉ có tối đa một hàng, tính duy nhất có được database bảo vệ bằng khóa hoặc constraint không?
3. Nếu không có hàng, đó là kết quả bình thường, một giá trị mặc định hay lỗi nghiệp vụ?
4. Tầng gọi cần xử lý từng entity, một entity hay một danh sách đã thu thập?
5. Tập dữ liệu có đủ nhỏ để `collectList()` hay cần giới hạn/phân trang?
6. Nếu chọn hàng đầu tiên, thứ tự có được xác định bằng `ORDER BY` không?
7. Nếu dùng truy vấn tùy chỉnh, SQL có đúng schema và bind parameter an toàn không?

Có thể tham khảo quy tắc sau:

| Nhu cầu | Lựa chọn |
|---|---|
| Tìm theo ID, có thể không tồn tại | `Mono<T>` với `findById` |
| Tìm theo khóa nghiệp vụ được bảo đảm duy nhất | `Mono<T>` và unique constraint |
| Tìm tất cả hàng theo điều kiện | `Flux<T>` |
| Chỉ kiểm tra có tồn tại | `Mono<Boolean>` từ `existsBy...` |
| Đếm số hàng | `Mono<Long>` |
| Lấy tối đa một hàng đầu tiên theo thứ tự | `Mono<T>` với `First`/`Top` và sort |
| Cần list nhỏ hoàn chỉnh | `Flux<T>.collectList()` |
| Cần xác nhận một Flux có tối đa một phần tử | `singleOrEmpty()` |
| SQL tùy chỉnh, cần tối đa một hàng | `DatabaseClient` với `one()` |
| SQL tùy chỉnh, lấy hàng đầu tiên | `DatabaseClient` với `first()` và `ORDER BY` |
| SQL tùy chỉnh, đọc mọi hàng | `DatabaseClient` với `all()` |

## 15. Ghi nhớ

- `Mono<T>` biểu diễn không hoặc một entity; `Flux<T>` biểu diễn không đến nhiều entity.
- `findById` trả `Mono.empty()` nếu không có bản ghi; `findAll` trả `Flux` rỗng nếu không có hàng.
- Không tìm thấy là kết quả rỗng, còn lỗi database là tín hiệu lỗi reactive.
- `Mono<List<T>>` từ `collectList()` phát list rỗng khi không có kết quả; nó khác `Mono<T>` rỗng.
- Dùng `existsById` hoặc `existsBy...` nếu chỉ cần kiểm tra tồn tại; dùng `count` nếu cần số lượng.
- Chọn `Mono` cho truy vấn kỳ vọng tối đa một hàng và bảo vệ tính duy nhất bằng constraint ở database.
- `one()` xác nhận tối đa một hàng; `first()` chỉ lấy hàng đầu và cần `ORDER BY` nếu thứ tự có ý nghĩa.
- `singleOrEmpty()` kiểm tra `Flux` có tối đa một phần tử; `next()` lấy phần tử đầu và bỏ phần còn lại.
- SQL `NULL` trong một cột không giống với truy vấn không có hàng.
- Chỉ thu thập `Flux` thành list khi tập kết quả có giới hạn hợp lý; dùng lọc và phân trang cho dữ liệu lớn.

