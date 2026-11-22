# Nullability của tham số và kết quả theo phiên bản Spring Data

Nullability mô tả một tham số hoặc giá trị trả về có được phép là `null` hay không. Trong Spring Data, hợp đồng này ảnh hưởng trực tiếp tới cách khai báo repository method, cách xử lý khi query không tìm thấy bản ghi, cách truyền tham số tùy chọn và khả năng phát hiện lỗi ngay tại thời điểm gọi method.

Cách biểu đạt nullability đã thay đổi theo các thế hệ Spring Data. Từ Spring Data 2.0, các CRUD method trả về một aggregate đơn lẻ sử dụng Java `Optional`; các phiên bản 2.x và 3.x thường dùng annotation nullability của Spring Framework dựa trên JSR-305; từ Spring Framework 7 và Spring Data 4, JSpecify là hướng được khuyến nghị và annotation nullability cũ của Spring đã bị deprecated.

Bài này tập trung vào Spring Data JPA, Java và Kotlin. Cần đối chiếu phiên bản Spring Data Commons đi kèm dự án vì phần lớn hợp đồng repository được định nghĩa ở module Commons, còn Spring Data JPA sử dụng lại chúng.

## 1. Null có thể xuất hiện ở đâu trong repository?

Một repository method có thể gặp null ở hai vị trí độc lập:

1. **Tham số đầu vào:** caller có thể truyền null hay bắt buộc phải truyền một giá trị?
2. **Kết quả trả về:** query có thể không tìm thấy bản ghi; khi đó method trả null, Optional rỗng hay ném exception?

Ví dụ:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Customer findByEmail(String email);

    Optional<Customer> findOptionalByEmail(String email);

    List<Customer> findAllByActiveTrue();
}
```

Ba method có hợp đồng khác nhau:

- `findByEmail` trả về một Customer hoặc có thể trả null nếu không có kết quả, trừ khi nullability contract quy định kết quả không được null.
- `findOptionalByEmail` biểu diễn kết quả có thể vắng mặt bằng `Optional<Customer>`.
- `findAllByActiveTrue` trả về danh sách; nếu không có bản ghi thì danh sách rỗng, không phải null.

Không nên dùng cùng một quy tắc cho mọi kiểu trả về. Một entity đơn lẻ có thể vắng mặt; một collection thường biểu diễn tập kết quả rỗng bằng collection rỗng; một tham số có thể nullable dù kết quả vẫn bắt buộc có giá trị.

## 2. Hợp đồng kết quả từ Spring Data 2.0

Một thay đổi quan trọng xuất hiện từ **Spring Data 2.0**: các CRUD method trả về một aggregate instance sử dụng Java 8 `Optional` để biểu diễn khả năng không tìm thấy giá trị.

Ví dụ API hiện đại:

```java
Optional<Customer> customer = customerRepository.findById(42L);
```

Nếu ID tồn tại, Optional chứa Customer. Nếu không tồn tại, kết quả là `Optional.empty()`. Caller phải xử lý cả hai trường hợp.

Trước Spring Data 2.0, API CRUD cũ thường dùng method như `findOne(ID)` và có thể trả về null khi không tìm thấy. Khi nâng cấp lên 2.0, method được đổi thành `findById(ID)` với kiểu trả về Optional. Vì vậy, code cũ không thể chỉ đổi tên method mà giữ nguyên cách xử lý kết quả.

Ví dụ cách xử lý:

```java
Customer customer = customerRepository.findById(id)
    .orElseThrow(() -> new CustomerNotFoundException(id));
```

Hoặc nếu việc vắng mặt là một nhánh nghiệp vụ bình thường:

```java
Optional<Customer> customer = customerRepository.findById(id);

if (customer.isPresent()) {
    updateCustomer(customer.get());
} else {
    createCustomer();
}
```

Không gọi `get()` khi chưa xác định Optional có giá trị. Có thể dùng `orElseThrow`, `ifPresent`, `map`, `orElse` hoặc các phép kết hợp phù hợp.

## 3. Bảng thay đổi theo thế hệ Spring Data

| Thế hệ | Cách biểu diễn thường gặp | Điểm cần chú ý |
|---|---|---|
| Spring Data 1.x | CRUD single-result API cũ như findOne có thể trả null | Chưa có hợp đồng Optional hiện đại của CRUD API |
| Spring Data 2.x | Optional cho CRUD single aggregate; Spring nullability annotations | Có thể dùng @NonNullApi, @NonNull, @Nullable để khai báo và kiểm tra |
| Spring Data 3.x | Tiếp tục Optional; Spring Framework 6 nullability annotations | Phổ biến với Spring Boot 3 và Java 17+; annotation Spring vẫn là cách thường gặp |
| Spring Data 4.x / Spring Framework 7 | Optional vẫn được hỗ trợ; JSpecify là hướng nullability được khuyến nghị | Spring @NonNullApi/@Nullable cũ đã deprecated để chuyển sang @NullMarked/@Nullable của JSpecify |

Bảng trên mô tả thay đổi chính của hợp đồng nullability, không phải danh sách mọi thay đổi API giữa các major version. Một số wrapper như Guava Optional, Scala Option và Vavr Option cũng được hỗ trợ cho query methods tùy module/classpath. Với code Java mới, ưu tiên `java.util.Optional`.

Khi đọc một repository cũ, đừng suy luận hợp đồng chỉ từ tên method. Hãy kiểm tra phiên bản Spring Data Commons thực tế, kiểu trả về, annotation trên package và annotation trên method/parameter.

## 4. Spring Data 2.x và 3.x: @NonNullApi

Trong Spring Data 2.x và 3.x, cách phổ biến để khai báo mặc định không nullable cho một package là dùng `@NonNullApi` trong file `package-info.java`.

Ví dụ cấu trúc:

```text
src/main/java/
  com/example/customer/
    package-info.java
    Customer.java
    CustomerRepository.java
```

Nội dung `package-info.java`:

```java
@NonNullApi
package com.example.customer;

import org.springframework.lang.NonNullApi;
```

Khi package được đánh dấu `@NonNullApi`:

- Tham số repository method mặc định không được nhận null.
- Giá trị trả về repository method mặc định không được là null.
- Có thể dùng `@Nullable` trên tham số hoặc method cụ thể để cho phép null.
- `@NonNull` có thể ghi rõ một vị trí bắt buộc không null, nhưng thường không cần lặp lại trong package đã có @NonNullApi.

Annotation Spring được meta-annotate bằng JSR-305 để IDE và công cụ phân tích có thể hiểu nullability. Việc dùng annotation ở package giúp thể hiện hợp đồng cho cả repository interface mà không phải đánh dấu từng tham số và return type.

Lưu ý: package annotation không tự động áp dụng cho package con theo cách đệ quy. Nếu repository nằm trong package con, hãy khai báo nullability ở package tương ứng hoặc kiểm tra phạm vi annotation đang áp dụng.

## 5. @Nullable cho tham số và kết quả trong Spring Data 2.x/3.x

Dùng `org.springframework.lang.Nullable` để đánh dấu rõ vị trí được phép nhận hoặc trả null:

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.lang.Nullable;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    // email bắt buộc; kết quả có thể vắng mặt dưới dạng Optional.
    Optional<Customer> findOptionalByEmail(String email);

    // Tham số có thể null và kết quả đơn lẻ cũng có thể null.
    @Nullable
    Customer findByLegacyCode(@Nullable String legacyCode);

    // Collection luôn biểu diễn không có kết quả bằng danh sách rỗng.
    List<Customer> findAllByActiveTrue();
}
```

Trong package có `@NonNullApi`:

- `findOptionalByEmail(null)` bị từ chối vì email không nullable.
- Nếu không tìm thấy email, method trả `Optional.empty()`.
- `findByLegacyCode(null)` được phép nhận null.
- Nếu query của `findByLegacyCode` không có kết quả, method trả null vì return type được đánh dấu @Nullable.
- `findAllByActiveTrue()` trả danh sách rỗng nếu không có Customer active.

Annotation ở method/parameter là ngoại lệ có chủ đích so với mặc định package. Đặt `@Nullable` ở return type không tự động cho phép tham số null; muốn cho phép cả hai thì phải đánh dấu cả hai vị trí.

## 6. Runtime validation khi dùng @NonNullApi

Nullability annotation không chỉ phục vụ tài liệu hoặc cảnh báo IDE. Khi package repository được đánh dấu `@NonNullApi`, Spring Data có thể kiểm tra hợp đồng nullability tại runtime cho query method.

Ví dụ:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Customer getByEmail(String email);
}
```

Nếu package áp dụng @NonNullApi:

- Truyền `null` cho email không nullable có thể làm method ném `IllegalArgumentException`.
- Nếu query không tìm thấy Customer và method được khai báo không nullable, Spring Data ném `EmptyResultDataAccessException` thay vì trả null.

So sánh ba kiểu khai báo:

| Khai báo | Tham số null | Không tìm thấy kết quả |
|---|---|---|
| `Customer getByEmail(String email)` trong package @NonNullApi | Bị từ chối | EmptyResultDataAccessException |
| `@Nullable Customer findByEmail(@Nullable String email)` | Được phép | Trả null |
| `Optional<Customer> findOptionalByEmail(String email)` | Bị từ chối nếu package mặc định non-null | Optional.empty() |

Các kiểm tra này được thực hiện qua cơ chế repository của Spring Data; chúng không có nghĩa mọi method Java trong toàn ứng dụng đều tự động được kiểm tra. Phạm vi phụ thuộc annotation, package, loại method và phiên bản framework.

Nếu package không có nullability default và method không có annotation, hợp đồng có thể không được khai báo rõ. Khi đó caller không nên tự suy luận rằng kết quả chắc chắn non-null. Hãy dùng Optional hoặc khai báo nullability tường minh để tránh phụ thuộc vào giả định ngầm.

## 7. Collection, Page, Slice và Stream không trả null

Spring Data bảo đảm các repository method trả collection, collection alternative, wrapper hoặc stream biểu diễn không có kết quả bằng dạng rỗng tương ứng.

Ví dụ:

```java
List<Customer> findByLastname(String lastname);

Set<Customer> findByActiveTrue();

Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

Slice<Customer> findByCity(
    String city,
    Pageable pageable
);

Stream<Customer> streamByActiveTrue();
```

Nếu không có bản ghi:

- List trả `Collections.emptyList()` hoặc một list rỗng tương đương.
- Set trả set rỗng.
- Page trả Page có content rỗng.
- Slice trả Slice có content rỗng.
- Stream trả stream rỗng.

Vì vậy, không cần viết:

```java
List<Customer> customers = repository.findByLastname(lastname);

if (customers != null && !customers.isEmpty()) {
    // ...
}
```

Chỉ cần:

```java
if (!customers.isEmpty()) {
    // ...
}
```

Stream cần được đóng đúng cách và sử dụng trong transaction phù hợp. Cam kết không trả null không có nghĩa stream luôn được tải an toàn từng phần hoặc không giữ tài nguyên JDBC.

## 8. Optional phù hợp với một kết quả đơn lẻ

Dùng `Optional<T>` khi query có thể trả tối đa một entity:

```java
Optional<Customer> findByEmail(String email);

Optional<Customer> findByExternalCode(String externalCode);
```

Điều kiện quan trọng là query phải có ngữ nghĩa tối đa một kết quả. Nếu database có nhiều bản ghi phù hợp, Spring Data có thể ném `IncorrectResultSizeDataAccessException`; Optional không có nghĩa "lấy bản ghi đầu tiên trong nhiều bản ghi".

Nếu cần nhiều kết quả, dùng List, Set, Page, Slice hoặc Stream phù hợp.

Không nên dùng `Optional<List<Customer>>` để diễn đạt danh sách có thể rỗng. Hãy trả `List<Customer>` và dùng list rỗng khi không có phần tử. Optional thường hữu ích cho một giá trị có thể vắng mặt.

Với CRUD API, `findById` là ví dụ chuẩn:

```java
Optional<Customer> customer = repository.findById(id);
```

Với query method tự định nghĩa, có thể dùng:

```java
Optional<Customer> findByEmail(String email);
```

## 9. Null của tham số không đồng nghĩa bỏ qua điều kiện tìm kiếm

Đây là nhầm lẫn thường gặp. `@Nullable` trên parameter chỉ nói rằng method chấp nhận giá trị null. Nó không tự nói rằng khi null thì phải bỏ điều kiện khỏi query.

Ví dụ:

```java
List<Customer> findByCity(@Nullable String city);
```

Nếu caller truyền null, derived query có thể diễn giải điều kiện equality thành tìm các hàng có city NULL. Đây không đồng nghĩa với "trả tất cả Customer bất kể city".

Nếu nghiệp vụ yêu cầu tham số null nghĩa là không áp dụng bộ lọc, hãy viết logic rõ ràng:

```java
public List<Customer> searchCustomers(@Nullable String city) {
    if (city == null) {
        return repository.findAll();
    }

    return repository.findByCity(city);
}
```

Với nhiều bộ lọc tùy chọn, có thể dùng Specification, Criteria API hoặc query động. Một JPQL expression dạng `(:city is null or c.city = :city)` cũng có thể biểu diễn bộ lọc tùy chọn, nhưng cần kiểm tra hiệu năng, index và ngữ nghĩa null trên database thực tế.

Đối với native query, SQL tuân theo logic ba giá trị của SQL: so sánh `column = NULL` không tương đương `column IS NULL`. Vì vậy, không mặc định một parameter null trong native SQL sẽ được xử lý giống derived query.

## 10. Nullability của parameter và nullability của dữ liệu database là hai lớp khác nhau

Các annotation repository như `@Nullable`, `@NonNullApi` hoặc JSpecify mô tả hợp đồng của method Java. Chúng không tự tạo constraint trong database.

Phân biệt:

| Cơ chế | Mục đích |
|---|---|
| `@Nullable` / `@NonNullApi` | Hợp đồng null của parameter và return value |
| `@Column(nullable = false)` | Metadata mapping cột không nullable và hỗ trợ schema generation |
| `@NotNull` của Bean Validation | Kiểm tra giá trị object theo validation lifecycle |
| `NOT NULL` trong database | Ràng buộc dữ liệu ở tầng database |

Ví dụ:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull
    @Column(name = "email", nullable = false, length = 254)
    private String email;
}
```

Ở đây `@NotNull` và `nullable = false` nói về dữ liệu email của entity/cột. Chúng không thay thế annotation trên method repository. Một repository method vẫn có thể có parameter nullable nếu nghiệp vụ cần tìm những Customer có email NULL, dù field email ở entity này lại được thiết kế không nullable.

Trong hệ thống thực tế, nên đồng bộ cả ba lớp: hợp đồng API Java, validation nghiệp vụ và constraint database. Database constraint vẫn là lớp bảo vệ cuối cùng trước các thao tác đồng thời hoặc ghi dữ liệu ngoài ứng dụng.

## 11. Spring Data 4.x: chuyển sang JSpecify

Từ **Spring Framework 7 và Spring Data 4**, JSpecify là cách được khuyến nghị để mô tả nullability. Các annotation nullability cũ của Spring như `@NonNullApi` và `org.springframework.lang.Nullable` đã deprecated để chuyển sang JSpecify.

Các annotation chính:

| Annotation | Ý nghĩa |
|---|---|
| `@NullMarked` | Đặt mặc định non-null ở module, package hoặc class |
| `@Nullable` | Kiểu/giá trị có thể là null |
| `@NonNull` | Kiểu/giá trị bắt buộc non-null |
| `@NullUnmarked` | Bỏ phạm vi null-marked trước đó, chuyển về trạng thái chưa xác định |

Khai báo package-level bằng `package-info.java`:

```java
@NullMarked
package com.example.customer;

import org.jspecify.annotations.NullMarked;
```

Repository trong package đó:

```java
package com.example.customer;

import java.util.Optional;
import org.jspecify.annotations.Nullable;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Nullable
    Customer findByLegacyCode(@Nullable String legacyCode);

    List<Customer> findAllByActiveTrue();
}
```

Ý nghĩa giống mô hình non-null mặc định trước đây:

- email mặc định không nullable.
- Optional luôn là wrapper biểu diễn kết quả có thể vắng mặt.
- legacyCode được phép null.
- kết quả Customer của findByLegacyCode được phép null.
- collection trả về dùng collection rỗng khi không có dữ liệu.

Với JSpecify, `@Nullable` là type-use annotation. Cách đặt annotation ngay trước kiểu liên quan giúp phân biệt rõ nullability của giá trị trả về, tham số, generic argument hoặc phần tử mảng.

Ví dụ về ý nghĩa type-use:

```java
@Nullable String findNickname();   // Kết quả String có thể null.

List<@Nullable String> labels();   // List không null, phần tử có thể null.

@Nullable List<String> loadLabels(); // Bản thân List có thể null.
```

Trong repository thông thường, collection return type của Spring Data được bảo đảm không null, vì vậy không nên cố khai báo collection có thể null nếu không có một API riêng thực sự yêu cầu điều đó.

## 12. @NullUnmarked và phạm vi nullability trong JSpecify

`@NullMarked` có thể được đặt ở module, package hoặc class. Phạm vi này giúp áp dụng non-null mặc định cho API mà không phải đánh dấu từng vị trí.

Nếu một vùng code cần giữ trạng thái nullability chưa xác định, có thể dùng `@NullUnmarked` ở package, class hoặc method phù hợp:

```java
@NullUnmarked
class LegacyCustomerAdapter {
    // Nullness trong phạm vi này không được suy ra từ @NullMarked bên ngoài.
}
```

Không nên dùng `@NullUnmarked` rộng để né việc khai báo nullability. Nó làm giảm thông tin mà compiler, IDE và công cụ kiểm tra có thể sử dụng. Khi chuyển một codebase lớn sang JSpecify, có thể dùng nó như ranh giới tương thích có chủ đích rồi thu hẹp dần.

Khi override method, hãy lặp lại nullness annotation phù hợp. Nullability annotation không nên bị xem là tự động kế thừa trong mọi tình huống override.

## 13. Kotlin repository và null-safety

Kotlin biểu diễn nullability ngay trong kiểu:

```kotlin
interface CustomerRepository : JpaRepository<Customer, Long> {

    fun findByEmail(email: String): Customer?

    fun findOptionalByEmail(email: String): Customer?

    fun findByLegacyCode(code: String?): Customer?

    fun findAllByActiveTrue(): List<Customer>
}
```

Các kiểu:

- `String` không cho phép null.
- `String?` cho phép null.
- `Customer` là kết quả bắt buộc không null.
- `Customer?` là kết quả có thể null.
- `List<Customer>` không nullable; danh sách rỗng biểu diễn không có phần tử.
- `List<Customer?>` có nghĩa phần tử có thể null, khác với danh sách nullable `List<Customer>?`.

Kotlin compiler có thể cảnh báo hoặc từ chối lời gọi truyền null vào parameter không nullable. Spring Data cũng đọc metadata Kotlin để thực hiện runtime null checks tương ứng. Cần có `kotlin-reflect` trên classpath để introspection nullability Kotlin hoạt động đúng theo tài liệu Spring Data.

Trong Kotlin, không cần dùng Java Optional cho mọi kết quả vắng mặt; nullable type thường diễn đạt tự nhiên hơn. Tuy nhiên, khi gọi API Java trả Optional, vẫn cần chuyển đổi và xử lý đúng hợp đồng của API đó.

## 14. Kiểm tra phiên bản thực tế của dự án

Không quyết định annotation chỉ dựa vào phiên bản Spring Boot ghi trong README cũ. Hãy xem dependency thực sự được resolve:

Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-jpa,org.springframework.data:spring-data-commons,org.springframework:spring-core
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
```

Kiểm tra cả:

- spring-data-jpa.
- spring-data-commons.
- spring-core / Spring Framework.
- JDK version và Kotlin version nếu repository viết bằng Kotlin.

Nên để Spring Boot dependency management hoặc Spring Data BOM quản lý các phiên bản liên quan. Không tự ghim spring-data-jpa và spring-data-commons vào hai release train khác nhau, vì API và nullability metadata có thể không tương thích.

Quy tắc thực hành:

- Dự án Spring Data 2.x/3.x: thường dùng `org.springframework.lang.NonNullApi`, `NonNull`, `Nullable`.
- Dự án Spring Data 4.x / Spring Framework 7: ưu tiên `org.jspecify.annotations.NullMarked`, `Nullable`, `NonNull`.
- Khi nâng cấp major version: kiểm tra warning deprecated, cập nhật package-info và kiểm thử repository method trả về không có kết quả.

## 15. Thiết kế repository method theo ý nghĩa nghiệp vụ

Chọn kiểu trả về theo số lượng kết quả và ý nghĩa của việc không tìm thấy:

| Nhu cầu | Kiểu trả về gợi ý | Khi không có kết quả |
|---|---|---|
| Tìm tối đa một Customer, không có là trường hợp bình thường | `Optional<Customer>` | Optional.empty() |
| Tìm một Customer và bắt buộc phải tồn tại | `Customer` trong package non-null | Exception khi không có |
| Tìm một Customer, chấp nhận trả null | `@Nullable Customer` | null |
| Tìm nhiều Customer | `List<Customer>` | List rỗng |
| Tìm nhiều Customer có tổng số trang | `Page<Customer>` | Page rỗng |
| Tải thêm mà không cần total count | `Slice<Customer>` | Slice rỗng |
| Duyệt kết quả theo stream | `Stream<Customer>` | Stream rỗng; phải đóng stream |
| Tham số lọc bắt buộc | `String email` trong non-null scope | Null bị từ chối |
| Tham số lọc tùy chọn | `@Nullable String city` hoặc `String?` | Query phải định nghĩa rõ ý nghĩa null |

Ví dụ repository rõ ràng:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByCity(String city);

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );

    long countByStatus(CustomerStatus status);

    boolean existsByEmail(String email);
}
```

Không dùng Optional cho boolean hoặc count: `existsByEmail` đã diễn đạt true/false; `countByStatus` trả số lượng. Cũng không dùng null để thay thế một collection rỗng.

## 16. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi get() trên Optional gây lỗi | Optional.empty() nhưng caller không kiểm tra | Dùng orElseThrow, ifPresent hoặc map |
| findBy... trả null ngoài dự kiến | Method trả entity trực tiếp và không có non-null contract | Dùng Optional hoặc khai báo @Nullable/@NonNullApi rõ ràng |
| Query không có kết quả ném EmptyResultDataAccessException | Method được khai báo non-null trong package @NonNullApi/@NullMarked | Dùng Optional hoặc đánh dấu return @Nullable nếu nghiệp vụ cho phép |
| Truyền null bị IllegalArgumentException | Parameter nằm trong non-null scope | Đánh dấu @Nullable nếu null hợp lệ hoặc từ chối input ở boundary |
| Package con không nhận nullability mặc định | package-info ở package cha không áp dụng đệ quy | Khai báo annotation ở package con hoặc module scope JSpecify |
| Collection bị kiểm tra null không cần thiết | Nhầm empty collection với null | Dùng isEmpty() |
| Optional nhận nhiều kết quả | Query không bảo đảm tối đa một hàng | Dùng List hoặc bổ sung constraint/điều kiện duy nhất |
| @Nullable parameter bị hiểu là bỏ filter | Nhầm hợp đồng null với logic query động | Xử lý null rõ trong service/Specification |
| Dùng annotation Spring trên Spring Data 4 | Annotation cũ đã deprecated từ Spring Framework 7 | Chuyển sang JSpecify |
| Dùng JSpecify trong dự án cũ không đồng bộ | Dependency/tooling không hỗ trợ cùng mức | Kiểm tra version và dùng annotation phù hợp release train |
| @Column(nullable=false) nhưng repository vẫn nhận null | Nhầm mapping database với method contract | Khai báo nullability ở cả repository và entity/validation/database |
| Kotlin code vẫn gặp null runtime | Thiếu kotlin-reflect hoặc metadata không được nhận diện | Kiểm tra dependency và nullability của Kotlin signature |

## 17. Checklist khi nâng cấp Spring Data

Trước khi nâng cấp từ Spring Data 1.x lên 2.x:

1. Tìm các lời gọi `findOne(...)` và chuyển sang `findById(...)`.
2. Thay logic so sánh null bằng xử lý Optional.
3. Kiểm tra query method trả entity trực tiếp và quyết định có nên dùng Optional.
4. Xác định các parameter có thể null và khai báo hợp đồng rõ ràng.
5. Kiểm thử trường hợp không có kết quả và nhiều hơn một kết quả.

Khi nâng từ Spring Data 2.x lên 3.x:

1. Kiểm tra yêu cầu Java 17 và Spring Framework 6.
2. Rà soát import annotation nullability từ `org.springframework.lang`.
3. Kiểm tra runtime validation trong package @NonNullApi.
4. Kiểm thử lại repository query và Kotlin metadata nếu có.

Khi nâng từ Spring Data 3.x lên 4.x:

1. Kiểm tra Spring Framework 7 và phiên bản JDK phù hợp.
2. Chuyển package-level `@NonNullApi` sang `@NullMarked` của JSpecify.
3. Chuyển `org.springframework.lang.Nullable` sang `org.jspecify.annotations.Nullable`.
4. Rà soát `@NonNull` và `@NullUnmarked` theo phạm vi type/package/class.
5. Cập nhật IDE, compiler và static analysis để nhận JSpecify.
6. Chạy test cho tham số null, kết quả không tìm thấy và collection rỗng.

Không nâng cấp bằng cách thay toàn bộ import một cách máy móc. Hãy xác nhận ý nghĩa nullability trước và sau khi đổi, đặc biệt ở package dùng default non-null.

## 18. Kiểm thử hợp đồng nullability

Nên có test cho cả parameter và result:

```java
@DataJpaTest
class CustomerRepositoryNullabilityTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void optionalResultRepresentsMissingCustomer() {
        Optional<Customer> result =
            repository.findByEmail("missing@example.com");

        assertThat(result).isEmpty();
    }

    @Test
    void collectionResultIsEmptyRatherThanNull() {
        List<Customer> result =
            repository.findByCity("unknown-city");

        assertThat(result).isNotNull().isEmpty();
    }

    @Test
    void nullableResultCanRepresentAbsence() {
        Customer result =
            repository.findByLegacyCode("missing-code");

        assertThat(result).isNull();
    }
}
```

Đây là khung minh họa; tên method và annotation phải khớp repository thực tế. Test gọi method có return non-null trong package @NonNullApi và không tìm thấy dữ liệu nên xác nhận exception phù hợp:

```java
assertThatThrownBy(() -> repository.getByEmail("missing@example.com"))
    .isInstanceOf(EmptyResultDataAccessException.class);
```

Test parameter non-null có thể xác nhận null bị từ chối:

```java
assertThatThrownBy(() -> repository.findOptionalByEmail(null))
    .isInstanceOf(IllegalArgumentException.class);
```

Không nên chỉ kiểm tra code compile. Hãy kiểm tra runtime behavior của repository proxy vì nullability validation có thể diễn ra khi method được gọi.

## 19. Tài liệu tham khảo chính thức

- [Spring Data JPA 3.5 — Null Handling of Repository Methods](https://docs.spring.io/spring-data/data-jpa/reference/3.5/repositories/null-handling.html): hợp đồng Optional, @NonNullApi, @Nullable và runtime validation trong thế hệ Spring Data 3.x.
- [Spring Data Commons 4.1 — Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html): JSpecify, wrapper return types, runtime validation và Kotlin null-safety trong Spring Data 4.x.
- [Spring Data Commons 2.0 — Reference Documentation](https://docs.spring.io/spring-data/commons/docs/2.0.13.RELEASE/reference/html/): mốc lịch sử Optional và nullability annotations từ Spring Data 2.0.

**Nguyên tắc xuyên suốt:** chọn kiểu trả về để thể hiện đúng việc có thể không có kết quả; dùng Optional cho một kết quả đơn lẻ có thể vắng mặt, collection rỗng cho nhiều kết quả, và @Nullable khi null thực sự là một phần của hợp đồng. Spring Data 2.x/3.x thường dùng Spring nullability annotations với @NonNullApi; Spring Data 4.x chuyển sang JSpecify với @NullMarked. Luôn kiểm tra version Spring Data Commons thực tế, phạm vi package và runtime behavior của repository thay vì dựa vào giả định về null.
