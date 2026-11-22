# Không dùng null để biểu diễn một phần tử trong luồng phản ứng

Trong Spring Data Relational R2DBC, dữ liệu được truyền qua `Mono` và `Flux` của Project Reactor. Một luồng phản ứng biểu diễn kết quả bằng các tín hiệu `onNext`, `onComplete` và `onError`. Theo Reactive Streams, một phần tử phát ra bằng `onNext` không được là `null`. Vì vậy, không thể dùng `Mono.just(null)` hoặc phát một phần tử null trong `Flux` để nói rằng “có kết quả nhưng giá trị đang trống”.

Thay vào đó, cần phân biệt rõ ba tình huống: có một giá trị, không có phần tử nào, và có lỗi. Trong ứng dụng truy cập database, còn cần phân biệt một hàng không tồn tại với một hàng tồn tại nhưng một cột có SQL `NULL`. Có thể biểu diễn giá trị nullable bằng `Mono.justOrEmpty`, `Optional`, DTO/record có thuộc tính nullable hoặc một kiểu kết quả riêng. Chọn cách phù hợp giúp pipeline reactive giữ đúng semantics và tránh lỗi `NullPointerException` khi mapping.

## 1. Vì sao Reactive Streams không cho phép phần tử null?

Reactive Streams định nghĩa một publisher phát ra các phần tử thông qua tín hiệu `onNext(T)`. Tín hiệu này phải chứa một phần tử hợp lệ; `null` không được dùng làm giá trị thay thế cho một phần tử. Việc kết thúc luồng và việc phát lỗi đã có tín hiệu riêng:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `onNext(value)` | Có một phần tử hợp lệ được phát ra; `value` không được null |
| `onComplete()` | Luồng kết thúc bình thường; có thể đã phát nhiều phần tử hoặc không phát phần tử nào |
| `onError(error)` | Luồng kết thúc do lỗi |

Do đó, một `Mono<T>` có thể phát đúng một giá trị, hoàn tất rỗng hoặc phát lỗi. Nó không có trạng thái “phát một giá trị null”. Một `Flux<T>` có thể phát không, một hoặc nhiều phần tử khác null rồi hoàn tất, hoặc kết thúc bằng lỗi.

```mermaid
flowchart TD
    A[Publisher] --> B{Kết quả}
    B -->|Có giá trị| C[onNext(value)]
    C --> D[onComplete]
    B -->|Không có giá trị| E[onComplete]
    B -->|Thất bại| F[onError(error)]
```

Không có nhánh `onNext(null)`. Nếu nguồn dữ liệu bên ngoài có thể trả null, ứng dụng phải chuyển trạng thái đó thành một biểu diễn hợp lệ trước khi phát vào pipeline.

## 2. `Mono.just(null)` là không hợp lệ

`Mono.just(value)` tạo một `Mono` phát ra giá trị đã cho. Giá trị này phải khác null:

```java
String name = null;

Mono<String> result = Mono.just(name); // Phát sinh NullPointerException
```

Lỗi xảy ra ngay khi tạo `Mono.just(...)`, vì Reactor kiểm tra giá trị đầu vào. Không nên viết code dựa trên giả định `Mono` sẽ phát null rồi để subscriber tự xử lý.

Nếu giá trị có thể null, dùng `Mono.justOrEmpty(...)`:

```java
String name = findNameOrNull();

Mono<String> result = Mono.justOrEmpty(name);
```

- Nếu `name` khác null, `Mono` phát giá trị đó rồi hoàn tất.
- Nếu `name` là null, `Mono` hoàn tất rỗng.

`justOrEmpty` có overload nhận `Optional<T>`:

```java
Optional<String> name = findOptionalName();

Mono<String> result = Mono.justOrEmpty(name);
```

Nếu `Optional` có giá trị, publisher phát giá trị bên trong. Nếu `Optional.empty()`, publisher hoàn tất rỗng.

## 3. Phân biệt giá trị, luồng rỗng và lỗi

Ba trường hợp này có semantics khác nhau và nên được xử lý riêng:

```java
Mono<String> found = Mono.just("An");
Mono<String> missing = Mono.empty();
Mono<String> failed = Mono.error(new IllegalStateException("Database unavailable"));
```

| Publisher | Hành vi khi subscribe | Ý nghĩa thường gặp |
| --- | --- | --- |
| `Mono.just("An")` | `onNext("An")`, sau đó `onComplete` | Có kết quả |
| `Mono.empty()` | `onComplete`, không có `onNext` | Không tìm thấy hoặc không có giá trị theo hợp đồng của phương thức |
| `Mono.error(...)` | `onError` | Thao tác thất bại |

Không chuyển lỗi database thành `Mono.empty()` chỉ để tránh exception. Ví dụ mất kết nối database là lỗi vận hành, không đồng nghĩa với “không tìm thấy bản ghi”. Nếu hai tình huống bị gộp, tầng gọi có thể trả HTTP 404 trong khi nguyên nhân thật là database đang không hoạt động.

Tương tự, không dùng null để biểu diễn lỗi. Dùng `Mono.error(...)` hoặc để exception được truyền qua publisher theo cách phù hợp.

## 4. `Mono.empty()` không phải `Mono.just(null)`

Hai biểu thức sau không tương đương:

```java
Mono<String> absent = Mono.empty();
Mono<String> invalid = Mono.just(null); // Ném NullPointerException
```

`Mono.empty()` là một publisher hợp lệ không phát phần tử nào. `Mono.just(null)` không tạo được publisher hợp lệ. Subscriber có thể phân biệt `onComplete` không có phần tử với `onNext` có dữ liệu; không có giá trị null cần kiểm tra.

Với `Mono<T>`, hoàn tất rỗng thường được dùng để biểu diễn không có kết quả. Với `Flux<T>`, hoàn tất rỗng có nghĩa không có phần tử nào trong luồng. Cần quy định rõ ý nghĩa đó ở từng phương thức: không tìm thấy entity, không có kết quả tìm kiếm, hoặc một thao tác `Mono<Void>` đã hoàn tất.

`Mono<Void>` thường hoàn tất mà không phát giá trị vì kiểu `Void` không dùng để mang một đối tượng kết quả. Đây là một hợp đồng hoàn tất thao tác, không phải cách biểu diễn một trường dữ liệu null.

## 5. `map` không được trả về null

Toán tử `map` biến đổi một phần tử thành một phần tử khác. Hàm mapper phải trả về giá trị khác null:

```java
Mono<String> result = Mono.just("An")
        .map(name -> lookupNicknameOrNull(name));
```

Nếu `lookupNicknameOrNull` trả null, Reactor không phát null; pipeline kết thúc bằng `NullPointerException`. Cần chuyển giá trị nullable thành `Mono` rỗng hoặc một wrapper không null.

Nếu mục tiêu là bỏ qua giá trị null:

```java
Mono<String> result = Mono.just("An")
        .flatMap(name -> Mono.justOrEmpty(lookupNicknameOrNull(name)));
```

Nếu cần giữ sự khác biệt giữa “có hàng nhưng cột null” và “không có hàng”, dùng wrapper:

```java
Mono<Optional<String>> result = Mono.just("An")
        .map(name -> Optional.ofNullable(lookupNicknameOrNull(name)));
```

Ở ví dụ thứ hai, `map` luôn trả một `Optional` khác null. `Optional.empty()` là một phần tử hợp lệ, không phải null.

## 6. `flatMap` cũng không được trả về null publisher

`flatMap` nhận một phần tử rồi chuyển nó thành publisher khác. Hàm mapper phải trả về một `Publisher` hợp lệ, không được trả null:

```java
Mono<Customer> result = customerRepository.findById(42L)
        .flatMap(customer -> loadDetailsOrNull(customer));
```

Nếu `loadDetailsOrNull` trả null thay vì `Mono`, Reactor sẽ phát lỗi. Khi không có kết quả phụ thuộc, hãy trả `Mono.empty()`:

```java
Mono<CustomerDetails> result = customerRepository.findById(42L)
        .flatMap(customer -> loadDetails(customer));
```

`loadDetails` cần trả về `Mono<CustomerDetails>` và dùng `Mono.empty()` khi không có chi tiết. Nếu phương thức bên dưới chỉ trả một giá trị nullable đồng bộ, chuyển nó bằng `Mono.justOrEmpty`:

```java
Mono<CustomerDetails> result = customerRepository.findById(42L)
        .flatMap(customer -> Mono.justOrEmpty(loadDetailsOrNull(customer)));
```

Không dùng `return null` trong nhánh của `flatMap`, `switchIfEmpty`, `onErrorResume` hoặc các callback yêu cầu một publisher.

## 7. `Mono.fromCallable` và giá trị trả về null

Khi bọc một lời gọi đồng bộ có thể trả null, `Mono.fromCallable` có semantics hữu ích: nếu callable trả về giá trị khác null, `Mono` phát giá trị; nếu callable trả null, `Mono` hoàn tất rỗng.

```java
Mono<String> name = Mono.fromCallable(() -> findNameOrNull());
```

Điều này khác với `Mono.just(findNameOrNull())`: biểu thức đối số của `just` được tính trước khi gọi `just`, và `just(null)` ném lỗi. `fromCallable` thực hiện callable khi subscribe và chuyển kết quả null thành luồng rỗng.

`Mono.fromSupplier(...)` cũng có thể dùng cho supplier trả giá trị nullable và sẽ hoàn tất rỗng nếu supplier trả null. Dù vậy, chỉ dùng các nguồn đồng bộ này cho công việc phù hợp; không bọc một lời gọi blocking database/JDBC trong `fromCallable` rồi xem nó thành non-blocking. R2DBC repository đã trả publisher reactive, nên hãy nối trực tiếp publisher đó.

## 8. `Mono.justOrEmpty` và `Optional`

`Optional<T>` là một cách biểu diễn giá trị có thể vắng mặt trong Java. Nó không chứa null: một `Optional` là `Optional.of(value)` hoặc `Optional.empty()`.

```java
Optional<String> maybeName = Optional.ofNullable(findNameOrNull());

Mono<String> namePublisher = Mono.justOrEmpty(maybeName);
```

Một cách dùng khác là phát `Optional` như chính phần tử của `Mono`:

```java
Mono<Optional<String>> result = Mono.fromSupplier(
        () -> Optional.ofNullable(findNameOrNull()));
```

Hai kiểu trả về thể hiện hợp đồng khác nhau:

| Kiểu | Ý nghĩa |
| --- | --- |
| `Mono<String>` qua `justOrEmpty` | Có tên thì phát tên; không có tên thì publisher rỗng |
| `Mono<Optional<String>>` | Publisher phát một `Optional`; phần tử có thể là `Optional.empty()` |

`Mono<Optional<T>>` hữu ích khi cần giữ một phần tử kết quả để phân biệt các trạng thái, nhưng không nên bọc mọi giá trị một cách máy móc. Nếu `Optional.empty()` chỉ đơn giản có nghĩa không có kết quả, `Mono<T>` rỗng thường tự nhiên hơn.

## 9. Phân biệt hàng không tồn tại với cột SQL NULL

Trong truy vấn R2DBC, cần phân biệt hai trường hợp:

1. Không có hàng nào khớp điều kiện `WHERE`.
2. Có một hàng khớp, nhưng một cột của hàng đó chứa SQL `NULL`.

Ví dụ bảng `customer` có cột `phone_number` nullable:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    phone_number VARCHAR(30)
);
```

Hàng có thể tồn tại với `phone_number = NULL`. Điều này khác với việc không có customer mang ID được tìm.

Repository `findById(id)` thường trả `Mono<Customer>`: nếu không có customer, publisher hoàn tất rỗng; nếu có customer nhưng `phone_number` là SQL `NULL`, entity vẫn được phát ra và thuộc tính `phoneNumber` có thể là null nếu kiểu Java cho phép.

```java
public class Customer {
    @Id
    private Long id;

    private String name;

    @Column("phone_number")
    private String phoneNumber; // Có thể null
}
```

Đừng nhầm `Mono.empty()` với entity có một thuộc tính null. Một trường null không làm toàn bộ entity trở thành null.

## 10. Biểu diễn hàng có cột nullable bằng DTO hoặc record

Nếu truy vấn chỉ đọc một phần dữ liệu và cần phân biệt hàng tồn tại với cột null, một DTO/record là lựa chọn rõ ràng:

```java
public record CustomerContact(
        Long id,
        String name,
        String phoneNumber
) {
}
```

Truy vấn có thể ánh xạ một hàng thành `CustomerContact`. Record là một đối tượng khác null, dù component `phoneNumber` có thể null:

```java
Mono<CustomerContact> contact = databaseClient.sql("""
        SELECT id, name, phone_number
        FROM customer
        WHERE id = :id
        """)
        .bind("id", customerId)
        .map((row, metadata) -> new CustomerContact(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("phone_number", String.class)))
        .one();
```

Kết quả có ba khả năng:

- Không có hàng: `Mono.empty()`.
- Có hàng và `phone_number` là SQL `NULL`: `Mono` phát `CustomerContact` với `phoneNumber == null`.
- Có hàng và số điện thoại có giá trị: `Mono` phát `CustomerContact` với chuỗi tương ứng.

Mapper trả về một record không null, nên hợp lệ với Reactor. Không viết `.map((row, metadata) -> row.get("phone_number", String.class))` nếu cột có thể null mà hợp đồng cần phân biệt hàng tồn tại; mapper khi đó có thể trả null và vi phạm quy tắc phát phần tử của Reactor.

## 11. Dùng `Optional` để giữ riêng trạng thái SQL NULL

Nếu chỉ cần đọc một cột nullable nhưng vẫn cần phân biệt “không có hàng” với “có hàng, cột null”, có thể bọc giá trị cột bằng `Optional`:

```java
Mono<Optional<String>> phoneNumber = databaseClient.sql("""
        SELECT phone_number
        FROM customer
        WHERE id = :id
        """)
        .bind("id", customerId)
        .map((row, metadata) ->
                Optional.ofNullable(row.get("phone_number", String.class)))
        .one();
```

Ngữ nghĩa:

| Tình huống database | Kết quả publisher |
| --- | --- |
| Không tìm thấy customer | `Mono.empty()` |
| Customer tồn tại, phone là SQL `NULL` | `Mono.just(Optional.empty())` |
| Customer tồn tại, phone có giá trị | `Mono.just(Optional.of(phone))` |

Đây là cách biểu diễn rõ ràng khi một phương thức phải giữ cả hai chiều thông tin. Tuy nhiên, nếu ứng dụng cần thêm ID, tên hoặc trạng thái của hàng, record có thuộc tính nullable thường dễ dùng hơn `Mono<Optional<String>>`.

## 12. `Row.get(...)` có thể trả null

R2DBC SPI cho phép giá trị cột SQL `NULL` được đọc thành Java null qua `Row.get(...)`. Điều đó không có nghĩa publisher được phép phát null. Giá trị null chỉ là dữ liệu trung gian trong mapper; mapper phải chuyển nó thành một đối tượng kết quả khác null hoặc chọn không phát phần tử.

Ví dụ an toàn khi tạo DTO:

```java
.map((row, metadata) -> new CustomerContact(
        row.get("id", Long.class),
        row.get("name", String.class),
        row.get("phone_number", String.class)))
```

Ví dụ an toàn khi chỉ cần chuỗi nếu có:

```java
.map((row, metadata) ->
        Optional.ofNullable(row.get("phone_number", String.class)))
```

Ví dụ có thể lỗi nếu cột nullable:

```java
.map((row, metadata) -> row.get("phone_number", String.class))
```

Trong ví dụ cuối, mapper có thể trả null. Hãy chọn kiểu kết quả theo yêu cầu của use case, không để null đi thẳng vào `onNext`.

## 13. Bind SQL NULL khi ghi bằng DatabaseClient

Một giá trị Java null cũng không thể được bind bằng `bind(name, value)` thông thường. Với `DatabaseClient`, dùng `bindNull(name, type)` để nói rõ tham số cần bind SQL `NULL`:

```java
public Mono<Long> insertCustomer(String name, String phoneNumber) {
    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql("""
            INSERT INTO customer (name, phone_number)
            VALUES (:name, :phoneNumber)
            """)
            .bind("name", name);

    if (phoneNumber == null) {
        spec = spec.bindNull("phoneNumber", String.class);
    } else {
        spec = spec.bind("phoneNumber", phoneNumber);
    }

    return spec.fetch().rowsUpdated();
}
```

`bindNull` cần kiểu Java tương ứng để driver biết kiểu tham số null. Chọn kiểu phù hợp với cột và driver, ví dụ `String.class` cho cột chuỗi hoặc `LocalDate.class` cho cột ngày.

Với R2DBC SPI trực tiếp, dùng `Statement.bindNull(index, type)`:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (name, phone_number) VALUES ($1, $2)");

statement.bind(0, name);
if (phoneNumber == null) {
    statement.bindNull(1, String.class);
} else {
    statement.bind(1, phoneNumber);
}
```

Không truyền null trực tiếp vào `Statement.bind(...)`. Placeholder, chỉ số và kiểu dữ liệu phải phù hợp với driver đang dùng.

## 14. `null` khác với database default

Gửi SQL `NULL` và bỏ cột khỏi câu lệnh `INSERT` là hai hành vi khác nhau:

```sql
-- Lưu SQL NULL vào cột nếu schema cho phép
INSERT INTO customer (name, status)
VALUES ('An', NULL);

-- Bỏ cột status để database áp dụng DEFAULT nếu có
INSERT INTO customer (name)
VALUES ('An');
```

Nếu cột `status` có `DEFAULT 'NEW'`, câu lệnh thứ hai có thể nhận giá trị `NEW`; câu lệnh thứ nhất ghi SQL `NULL` nếu cột cho phép null. Không giả định bind null sẽ kích hoạt default của database.

Trong Spring Data R2DBC, cách entity được chuyển thành câu lệnh insert phụ thuộc mapping metadata và API đang dùng. Nếu muốn database tự áp dụng default, hãy kiểm tra câu SQL thực tế và dùng cơ chế insert phù hợp để bỏ cột khỏi câu lệnh. Nếu muốn lưu null, bind/ghi null một cách tường minh và bảo đảm cột nullable.

## 15. Dùng `Criteria` để tìm SQL NULL

Không dùng phép so sánh bằng với null:

```sql
WHERE phone_number = NULL
```

SQL dùng logic ba giá trị; phép so sánh này không trả `TRUE` cho hàng có null. Dùng `IS NULL`:

```sql
WHERE phone_number IS NULL
```

Với `R2dbcEntityTemplate`, có thể biểu diễn điều kiện null bằng Criteria:

```java
Criteria criteria = where("phoneNumber").isNull();

return template.select(Customer.class)
        .matching(Query.query(criteria))
        .all();
```

Để tìm các hàng có giá trị, dùng `isNotNull()` nếu API của phiên bản Spring Data Relational đang dùng hỗ trợ:

```java
Criteria criteria = where("phoneNumber").isNotNull();
```

Tên property trong Criteria là tên thuộc tính entity; mapping sẽ chuyển sang cột `phone_number`. Đối chiếu API với phiên bản Spring Data của dự án nếu chữ ký khác.

## 16. `switchIfEmpty` và `defaultIfEmpty`

Khi publisher hoàn tất rỗng, có thể chọn một giá trị mặc định hoặc chạy một publisher thay thế.

`defaultIfEmpty` phát giá trị mặc định nếu nguồn không phát phần tử:

```java
Mono<String> displayName = customerRepository.findById(id)
        .map(Customer::getName)
        .defaultIfEmpty("Unknown customer");
```

`switchIfEmpty` chuyển sang publisher khác:

```java
Mono<Customer> customer = customerRepository.findById(id)
        .switchIfEmpty(Mono.defer(() -> loadFromArchive(id)));
```

`Mono.defer` giúp tạo publisher thay thế khi thật sự cần dùng. Điều này hữu ích nếu tạo fallback có chi phí hoặc có side effect cần tránh thực hiện sớm.

Giá trị mặc định trong `defaultIfEmpty` cũng phải khác null:

```java
Mono<String> result = Mono.<String>empty()
        .defaultIfEmpty(null); // Không hợp lệ
```

Nếu cần biểu diễn một giá trị thay thế nullable, bọc bằng `Optional` hoặc DTO:

```java
Mono<Optional<String>> result = Mono.<String>empty()
        .defaultIfEmpty(Optional.empty());
```

Không dùng `defaultIfEmpty` để che lỗi. Toán tử này chỉ phản ứng với hoàn tất rỗng, không xử lý `onError`.

## 17. `switchIfEmpty` khác `onErrorResume`

Hai toán tử xử lý hai tín hiệu khác nhau:

```java
Mono<Customer> result = customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorResume(DatabaseUnavailableException.class,
                error -> fallbackRepository.findById(id));
```

- `switchIfEmpty` chạy khi publisher hoàn tất bình thường nhưng không phát phần tử.
- `onErrorResume` chạy khi publisher phát tín hiệu lỗi và có thể thay bằng publisher khác.

Không dùng `onErrorResume(error -> Mono.empty())` cho mọi lỗi database nếu nghiệp vụ cần phân biệt lỗi vận hành với không tìm thấy. Điều đó sẽ biến lỗi kết nối, lỗi mapping hoặc lỗi constraint thành kết quả rỗng và làm mất thông tin quan trọng.

## 18. Các toán tử có thể bỏ hoặc làm mất phần tử

Một số toán tử có thể tạo luồng rỗng mà không cần null:

| Toán tử | Hành vi liên quan |
| --- | --- |
| `filter(predicate)` | Bỏ phần tử nếu predicate trả false |
| `filterWhen(predicate)` | Bỏ phần tử nếu publisher predicate phát false |
| `flatMap(mapper)` | Publisher con có thể là `Mono.empty()`, nên không có phần tử tương ứng ở đầu ra |
| `then()` | Bỏ qua các phần tử nguồn và chỉ phát tín hiệu hoàn tất/error |
| `take(n)` | Chỉ giữ tối đa n phần tử |
| `next()` | Lấy phần tử đầu tiên của Flux dưới dạng Mono; nguồn rỗng thì Mono rỗng |

Ví dụ `flatMap` bỏ qua một kết quả phụ:

```java
Flux<CustomerDetails> details = customerRepository.findAll()
        .flatMap(customer -> detailsRepository.findByCustomerId(customer.getId()));
```

Nếu một customer không có details và repository trả `Mono.empty()`, customer đó không tạo phần tử trong `details`. Đây là semantics hợp lệ, nhưng nếu cần giữ mỗi customer trong kết quả, hãy trả DTO chứa customer và một trường tùy chọn thay vì làm mất phần tử.

## 19. `zip` và publisher rỗng

`Mono.zip(a, b)` cần mỗi nguồn phát một phần tử để tạo tuple. Nếu một nguồn hoàn tất rỗng, phép zip không thể tạo tuple và kết quả thường hoàn tất rỗng:

```java
Mono<Customer> customer = customerRepository.findById(id);
Mono<Preferences> preferences = preferencesRepository.findByCustomerId(id);

Mono<Tuple2<Customer, Preferences>> combined =
        Mono.zip(customer, preferences);
```

Nếu customer tồn tại nhưng chưa có preferences, `preferences` có thể rỗng và toàn bộ `combined` rỗng. Nếu nghiệp vụ muốn giữ customer và dùng preferences mặc định, hãy xử lý nguồn có thể rỗng trước khi zip:

```java
Mono<Preferences> preferencesOrDefault = preferencesRepository.findByCustomerId(id)
        .defaultIfEmpty(Preferences.defaults());

Mono<Tuple2<Customer, Preferences>> combined =
        Mono.zip(customer, preferencesOrDefault);
```

Nếu cần phân biệt không có preferences với preferences có giá trị mặc định, dùng `Optional` hoặc DTO trạng thái rõ ràng thay vì thay thế bằng một giá trị giả.

## 20. Không dùng `filter(Objects::nonNull)` để hợp thức hóa null trong luồng

Một cách viết dễ gây hiểu nhầm là:

```java
Flux<String> names = source
        .filter(Objects::nonNull);
```

`filter` nhận các phần tử đã được phát hợp lệ; nó không phải cơ chế chuẩn để sửa một Publisher vi phạm Reactive Streams bằng cách phát null. Reactor thường từ chối null ngay ở nguồn hoặc toán tử trước đó, nên predicate có thể không bao giờ nhận được null.

Nếu dữ liệu ban đầu là một collection Java có thể chứa null, hãy làm sạch hoặc ánh xạ nó trước khi tạo Publisher:

```java
List<String> nonNullNames = namesFromLegacySource.stream()
        .filter(Objects::nonNull)
        .toList();

Flux<String> names = Flux.fromIterable(nonNullNames);
```

Nếu muốn giữ vị trí của phần tử thiếu, đừng loại bỏ nó; hãy chuyển thành wrapper:

```java
List<Optional<String>> wrappedNames = namesFromLegacySource.stream()
        .map(Optional::ofNullable)
        .toList();

Flux<Optional<String>> names = Flux.fromIterable(wrappedNames);
```

Phải bọc giá trị trước khi tạo `Flux`, vì `Flux.fromIterable` cũng không thể phát phần tử null để rồi chờ `map` chuyển đổi. Mỗi phần tử của `wrappedNames` là một `Optional` khác null, kể cả khi giá trị ban đầu null.

## 21. Dùng `handle` khi cần phát hoặc bỏ qua một phần tử

`handle` cho phép một phần tử đầu vào tạo ra một phần tử đầu ra hoặc không tạo phần tử nào. Đây là cách biểu diễn một phép biến đổi có thể không có kết quả mà không trả null:

```java
Flux<String> validNames = source.handle((raw, sink) -> {
    String normalized = normalizeOrNull(raw);

    if (normalized != null) {
        sink.next(normalized);
    }
});
```

Nếu `normalized` null, callback không gọi `sink.next`, nên phần tử đó bị bỏ qua. Nếu có giá trị, nó phát một phần tử khác null.

Không gọi `sink.next(null)`. Nếu cần biểu diễn phần tử bị loại bỏ như một trạng thái để kiểm toán, phát một wrapper kết quả:

```java
public record NormalizationResult(
        String original,
        String normalized,
        boolean accepted
) {
}
```

Khi đó mỗi đầu vào tạo một `NormalizationResult` khác null; trường `normalized` có thể null nếu trạng thái đó có ý nghĩa và được mô tả rõ.

## 22. Dùng kiểu kết quả tường minh cho nhiều trạng thái

`Optional<T>` biểu diễn có hoặc không có giá trị, nhưng một số nghiệp vụ có nhiều hơn hai trạng thái. Ví dụ kiểm tra một mã khách hàng có thể cho kết quả: không tồn tại, tồn tại nhưng bị khóa, hoặc tồn tại và đang hoạt động.

Không nên dùng null, chuỗi rỗng hoặc một giá trị giả để biểu diễn các trạng thái đó. Có thể định nghĩa kiểu kết quả:

```java
public sealed interface CustomerLookupResult {

    record NotFound() implements CustomerLookupResult {}

    record Inactive(Customer customer) implements CustomerLookupResult {}

    record Active(Customer customer) implements CustomerLookupResult {}
}
```

Service có thể chuyển kết quả repository thành một phần tử kết quả rõ ràng:

```java
public Mono<CustomerLookupResult> lookup(Long id) {
    return customerRepository.findById(id)
            .map(customer -> customer.isActive()
                    ? new CustomerLookupResult.Active(customer)
                    : new CustomerLookupResult.Inactive(customer))
            .defaultIfEmpty(new CustomerLookupResult.NotFound());
}
```

Mọi nhánh đều phát một đối tượng khác null. Caller có thể xử lý từng trạng thái mà không phải suy luận từ null hoặc exception. Nếu lỗi database xảy ra, publisher vẫn phát `onError`; `NotFound` chỉ đại diện cho truy vấn hoàn tất bình thường nhưng không có hàng.

## 23. Trường hợp cập nhật từng phần (PATCH)

Trong API PATCH, một trường có thể mang ba ý nghĩa:

1. Client không gửi trường: giữ nguyên giá trị hiện tại.
2. Client gửi trường với null: xóa giá trị hiện tại nếu nghiệp vụ cho phép.
3. Client gửi giá trị: cập nhật thành giá trị đó.

Một thuộc tính Java `String` có thể null không đủ để phân biệt trường hợp 1 và 2 sau khi deserialize nếu framework/API binding không giữ thông tin trường có xuất hiện hay không. `Optional<String>` đơn giản cũng chỉ biểu diễn có/không có giá trị sau khi tạo; nó không tự định nghĩa hợp đồng PATCH cho mọi serializer.

Hãy dùng DTO/command có cách biểu diễn presence rõ ràng, ví dụ một wrapper `FieldUpdate<T>`:

```java
public record FieldUpdate<T>(boolean supplied, T value) {
    public static <T> FieldUpdate<T> absent() {
        return new FieldUpdate<>(false, null);
    }

    public static <T> FieldUpdate<T> supplied(T value) {
        return new FieldUpdate<>(true, value);
    }
}
```

Khi áp dụng command:

```java
if (command.phoneNumber().supplied()) {
    customer.setPhoneNumber(command.phoneNumber().value());
}
```

Nếu `supplied` là false, giữ nguyên. Nếu true và `value` là null, xóa giá trị. Nếu true và `value` có nội dung, cập nhật. Đây là ví dụ mô hình hóa; bộ giải mã JSON cần được cấu hình để phân biệt field bị thiếu với field hiện diện có giá trị null.

Khi ghi xuống database, giá trị null được bind bằng `bindNull` hoặc mapping entity phù hợp. Không dùng null trong `Mono` để biểu diễn trạng thái PATCH.

## 24. Kiểu primitive và nullable property

Java primitive không thể chứa null. Nếu cột database cho phép null, entity/DTO cần kiểu tham chiếu tương ứng:

| Primitive | Wrapper có thể null |
| --- | --- |
| `int` | `Integer` |
| `long` | `Long` |
| `boolean` | `Boolean` |
| `double` | `Double` |
| `float` | `Float` |
| `short` | `Short` |
| `byte` | `Byte` |
| `char` | `Character` |

Ví dụ, nếu `middle_name` nullable, dùng `String`; nếu `age` nullable, dùng `Integer` thay vì `int`. Nếu một trường bắt buộc, khai báo `NOT NULL` trong schema và validate ở tầng ứng dụng.

Không tự động đổi null thành `0`, `false` hoặc `''` chỉ để tránh lỗi mapping. Những giá trị đó có ý nghĩa khác nhau và có thể làm sai dữ liệu nghiệp vụ.

## 25. SQL NULL và điều kiện trong Criteria

Khi đọc dữ liệu nullable, entity có thể chứa null. Khi tìm kiếm, phải dùng semantics SQL đúng:

```java
Criteria missingPhone = where("phoneNumber").isNull();
Criteria hasPhone = where("phoneNumber").isNotNull();
```

Không dùng:

```java
Criteria wrong = where("phoneNumber").is(null);
```

`is(null)` có thể không được hỗ trợ như cách diễn đạt `IS NULL` và không nên dùng thay cho toán tử null chuyên biệt. Hãy dùng API `isNull()`/`isNotNull()` của phiên bản Spring Data Relational đang chạy hoặc SQL `IS NULL` trong `@Query`/`DatabaseClient`.

Trong filter động, phân biệt trường hợp client không gửi filter với yêu cầu tìm các hàng có cột null. Nếu null có nghĩa “bỏ qua”, không thêm điều kiện. Nếu null có nghĩa “tìm null”, thêm điều kiện `IS NULL` tường minh.

## 26. Testing: xác minh null không đi vào Publisher

Reactor Test `StepVerifier` giúp xác minh các semantics này:

```java
@Test
void justOrEmptyCompletesWhenValueIsNull() {
    String value = null;

    StepVerifier.create(Mono.justOrEmpty(value))
            .verifyComplete();
}

@Test
void fromCallableCompletesWhenCallableReturnsNull() {
    StepVerifier.create(Mono.fromCallable(() -> (String) null))
            .verifyComplete();
}

@Test
void mapReturningNullSignalsError() {
    StepVerifier.create(Mono.just("input")
                    .map(value -> (String) null))
            .expectError(NullPointerException.class)
            .verify();
}
```

Các test trên xác minh khác biệt giữa nguồn nullable được chuyển thành empty và mapper vi phạm hợp đồng bằng cách trả null.

Có thể kiểm thử wrapper:

```java
@Test
void optionalPreservesPresentElementWhenValueIsNull() {
    StepVerifier.create(Mono.just(Optional.<String>empty()))
            .expectNext(Optional.empty())
            .verifyComplete();
}
```

Ở đây publisher phát một phần tử `Optional.empty()` rồi hoàn tất. Điều này khác với `Mono.<String>empty()`, vốn không phát phần tử nào.

## 27. Integration test với R2DBC và SQL NULL

Unit test Reactor không chứng minh driver ánh xạ SQL NULL đúng với schema. Nên có integration test dùng database và R2DBC driver tương thích với production.

Các trường hợp nên xác minh:

1. Đọc ID không tồn tại trả publisher rỗng.
2. Đọc hàng có `phone_number IS NULL` trả DTO/record có `phoneNumber == null`.
3. Đọc hàng có phone trả DTO có chuỗi đúng.
4. Truy vấn scalar nullable dùng `Optional` nếu cần phân biệt hàng không tồn tại với cột null.
5. Bind null bằng `DatabaseClient.bindNull` lưu SQL NULL.
6. Bind null bằng SPI `Statement.bindNull` dùng đúng kiểu Java.
7. Cột `NOT NULL` từ chối null và lỗi được truyền qua `onError`.
8. `IS NULL` và `IS NOT NULL` trả đúng tập hàng.
9. Giá trị mặc định của database chỉ được áp dụng khi cột được bỏ khỏi insert theo đúng SQL, không phải khi cố tình ghi SQL NULL.
10. DTO có primitive không được dùng cho cột nullable.

Một integration test cần tạo ít nhất hai hàng: một hàng có giá trị và một hàng có SQL NULL. Đồng thời kiểm tra trường hợp không có hàng để xác minh ba trạng thái không bị gộp.

## 28. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi `Mono.just(nullableValue)` khi giá trị null | `NullPointerException` ngay khi tạo Mono | Dùng `Mono.justOrEmpty` hoặc wrapper |
| Mapper của `map` trả null | Pipeline phát `onError` với NPE | Chuyển sang `flatMap` + `justOrEmpty`, hoặc trả DTO/Optional |
| Mapper của `flatMap` trả null publisher | Pipeline lỗi | Trả `Mono.empty()`, `Mono.error(...)` hoặc publisher hợp lệ |
| Dùng `Mono.empty()` để biểu diễn lỗi database | Che giấu lỗi vận hành như không tìm thấy | Giữ `onError` hoặc ánh xạ sang lỗi miền phù hợp |
| Đọc cột nullable trực tiếp thành scalar Mono | Có thể tạo mapper trả null và vi phạm hợp đồng | Map thành DTO hoặc `Optional` |
| Dùng primitive cho cột nullable | Không biểu diễn được SQL NULL | Dùng wrapper hoặc thay đổi nullability schema |
| Gọi `bind(name, null)` | Lỗi bind tham số | Dùng `bindNull(name, type)` |
| Dùng `= NULL` trong SQL | Điều kiện không khớp như mong đợi | Dùng `IS NULL` hoặc `IS NOT NULL` |
| Dùng `defaultIfEmpty(null)` | Giá trị mặc định không hợp lệ | Dùng giá trị khác null hoặc wrapper |
| Dùng `filter(Objects::nonNull)` để sửa nguồn vi phạm | Null có thể đã bị Reactor từ chối trước filter | Làm sạch nguồn trước khi tạo Publisher hoặc map sang wrapper |
| Dùng `zip` với nguồn có thể empty | Toàn bộ zip có thể hoàn tất rỗng | Xử lý empty trước zip hoặc dùng kiểu kết quả rõ ràng |
| Gộp field PATCH bị thiếu với field null | Không phân biệt giữ nguyên và xóa giá trị | Dùng wrapper biểu diễn field presence |

## 29. Quy trình xử lý một giá trị nullable trong R2DBC

Khi một nguồn hoặc cột có thể không có giá trị, hãy xác định semantics trước:

1. Giá trị null có nghĩa không có kết quả, hay một hàng tồn tại nhưng cột trống?
2. Nếu không có kết quả, trả `Mono.empty()` hoặc `Flux.empty()` theo hợp đồng.
3. Nếu hàng tồn tại với cột null, map sang entity/DTO có thuộc tính nullable hoặc `Optional`.
4. Nếu nguồn đồng bộ trả nullable, dùng `Mono.justOrEmpty`, `Mono.fromCallable` hoặc wrapper phù hợp.
5. Nếu cần ghi SQL NULL, dùng `bindNull` với kiểu dữ liệu tương ứng hoặc mapping entity đúng.
6. Nếu cần database default, bỏ cột khỏi câu lệnh theo đúng cơ chế thay vì bind null.
7. Giữ lỗi database trong `onError`; không chuyển thành empty nếu semantics không phải “không có kết quả”.
8. Kiểm thử cả giá trị, empty, SQL NULL và lỗi bằng StepVerifier cùng integration test.

## 30. Nguyên tắc thực hành

- Không phát `null` bằng `onNext`; `Mono` và `Flux` chỉ phát phần tử khác null.
- Dùng `Mono.justOrEmpty(value)` khi giá trị đầu vào có thể null và null có nghĩa không có phần tử.
- Dùng `Mono.empty()` cho trường hợp không có kết quả theo hợp đồng, và `Mono.error(...)` cho lỗi.
- Không trả null từ mapper của `map` hoặc publisher mapper của `flatMap`.
- Dùng `Mono.fromCallable`/`fromSupplier` cho nguồn đồng bộ nullable khi semantics null-to-empty là phù hợp; không dùng chúng để biến I/O blocking thành non-blocking.
- Phân biệt không có hàng với có hàng chứa SQL NULL.
- Map hàng có cột nullable thành entity/DTO khác null có thuộc tính nullable, hoặc bọc scalar bằng `Optional` khi cần giữ cả hai trạng thái.
- Dùng kiểu wrapper cho thuộc tính Java có thể nhận SQL NULL.
- Dùng `DatabaseClient.bindNull` hoặc `Statement.bindNull` để bind SQL NULL; không truyền null vào `bind` thông thường.
- Dùng `IS NULL`/`IS NOT NULL`, không so sánh `= NULL`.
- Phân biệt SQL NULL với database default, chuỗi rỗng, số 0 và `Mono.empty()`.
- Dùng `switchIfEmpty` cho luồng rỗng và `onErrorResume` cho lỗi; không gộp hai tín hiệu tùy tiện.
- Kiểm tra semantics của `zip`, `flatMap`, `then` và các toán tử có thể làm mất phần tử.
- Với PATCH, biểu diễn riêng field không được gửi và field được gửi với null.
- Kiểm thử null/empty/error ở mức Reactor và kiểm thử SQL NULL trên database/driver thật.

## 31. Kết luận

Reactive Streams không cho phép một publisher phát null như một phần tử. `Mono` biểu diễn một giá trị khác null, hoàn tất rỗng hoặc phát lỗi; `Flux` phát không hoặc nhiều giá trị khác null rồi hoàn tất hoặc lỗi. Vì vậy, dùng `Mono.justOrEmpty` hoặc `Mono.empty` khi không có phần tử, dùng `Mono.error` cho lỗi và bảo đảm mapper của `map`/`flatMap` không trả null.

Trong Spring Data R2DBC, SQL NULL vẫn là dữ liệu hợp lệ ở cấp cột. Một hàng có cột null phải được ánh xạ thành entity/DTO khác null có thuộc tính nullable, hoặc dùng `Optional` nếu cần phân biệt rõ với trường hợp không có hàng. Khi ghi, dùng `bindNull` để gửi SQL NULL và hiểu sự khác nhau giữa null với database default. Phân biệt chính xác giá trị, empty và error giúp reactive pipeline giữ đúng hợp đồng, tránh NPE và không che giấu lỗi database.
