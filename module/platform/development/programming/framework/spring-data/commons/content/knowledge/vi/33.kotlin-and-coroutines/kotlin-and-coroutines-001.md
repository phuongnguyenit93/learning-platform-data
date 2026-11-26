# Phạm vi dùng Kotlin bên cạnh mô hình Java trong Spring Data

## Mục tiêu và phạm vi

Spring Data được xây dựng trên nền JVM và các abstraction như repository, mapping metadata, query method, projection và auditing. Kotlin có thể sử dụng những abstraction đó cùng với Java trong một ứng dụng.

Một dự án có thể giữ entity và repository bằng Java, viết service hoặc DTO bằng Kotlin, rồi chuyển từng phần khác khi có nhu cầu. Việc sử dụng Kotlin cũng có thể mở đường cho coroutine, nhưng lựa chọn ngôn ngữ và lựa chọn mô hình truy cập dữ liệu là hai quyết định riêng.

Bài học giúp bạn xác định:

- Những phần nào có thể viết bằng Kotlin trong một dự án Spring Data đang dùng Java.
- Cách đọc hợp đồng nullability khi đi qua ranh giới Java–Kotlin.
- Điều kiện mapping của Kotlin class và giới hạn của từng store.
- Khi nào dùng repository đồng bộ, reactive repository hoặc coroutine repository.
- Cách đưa Kotlin vào dự án theo từng bước mà vẫn giữ rõ hợp đồng dữ liệu.

Các ví dụ JPA và R2DBC là hai lựa chọn triển khai riêng. Không cần bật cả hai để sử dụng Kotlin. Ví dụ cũng giả định cấu hình dependency, compiler và database của từng lựa chọn đã được thiết lập phù hợp.

## 1. Tách ba quyết định trước khi chọn cách triển khai

Khi thiết kế một phần truy cập dữ liệu, hãy xét ba trục:

| Trục quyết định | Ví dụ | Điều nó chi phối |
|---|---|---|
| Ngôn ngữ mã nguồn | Java, Kotlin | Cú pháp, nullability, đặc tính kiểu và cách khai báo |
| Module store và mapping | JPA, MongoDB, JDBC, R2DBC | Cách đối tượng được lưu, query và lifecycle |
| Mô hình thực thi | Đồng bộ, reactive, coroutine trên hạ tầng phù hợp | Cách chờ kết quả, truyền lỗi, quản lý luồng xử lý |

Một service Kotlin gọi `JpaRepository` vẫn sử dụng đường truy cập JPA đồng bộ. Một coroutine repository dựa trên R2DBC dùng driver và transaction infrastructure khác.

Có thể đưa Kotlin vào lớp service mà chưa thay đổi store. Cũng có thể giữ entity Java và viết repository interface Kotlin. Các quyết định này không buộc toàn bộ ứng dụng phải chuyển sang coroutine.

Cần xác định rõ mục tiêu của thay đổi:

- Muốn code biểu đạt nullability và DTO rõ hơn.
- Muốn giảm mã lặp khi xây dựng mô hình giá trị.
- Muốn dùng API Kotlin tiện dụng hơn.
- Muốn thiết kế một đường truy cập non-blocking với coroutine.

Mỗi mục tiêu có phạm vi cấu hình và kiểm chứng khác nhau.

## 2. Kotlin có thể tham gia ở những lớp nào?

| Thành phần | Cách dùng Kotlin bên cạnh Java | Điều cần giữ rõ |
|---|---|---|
| DTO và mô hình giá trị | Khai báo class hoặc data class Kotlin | Hợp đồng null, serialization và validation |
| Application service | Gọi repository và entity Java | Tính blocking, transaction và API Java được gọi |
| Repository interface | Kế thừa interface Spring Data | Kiểu trả về, query derivation và khả năng store |
| Domain model | Class Kotlin được store mapping | Constructor, property, annotation và tính bất biến |
| Projection | Interface hoặc DTO Kotlin khi store hỗ trợ | Thuộc tính cần chọn, constructor và cách ánh xạ |
| Repository tùy biến | Viết implementation bằng Kotlin | Quy ước discovery và hợp đồng interface |
| Coroutine repository | Dùng `suspend`, `Flow` với module phù hợp | Hạ tầng reactive và coroutine integration |

Kotlin không thay thế quy tắc derived query. Một phương thức tên `findByEmail` vẫn được phân tích theo property của mô hình và khả năng của store.

Tương tự, một kiểu DTO Kotlin không tự trở thành projection được mọi module tối ưu. Việc lựa chọn cột, document field hoặc cách tạo DTO vẫn do store implementation quyết định.

`Sort`, `Pageable`, `Example` và các metadata chung có thể được sử dụng từ Kotlin khi API tương ứng hỗ trợ. Khả năng áp dụng của chúng vẫn theo loại repository và module đang dùng.

## 3. Giữ entity và repository Java, viết service Kotlin

Đây là một cách bắt đầu có phạm vi nhỏ: giữ nguyên mô hình lưu trữ Java, cho Kotlin sử dụng API đã có.

### 3.1. Entity Java với mapping JPA

```java
import java.util.Objects;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    protected Customer() {
    }

    public Customer(String displayName) {
        this.displayName = Objects.requireNonNull(
                displayName,
                "displayName"
        );
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String displayName) {
        this.displayName = Objects.requireNonNull(
                displayName,
                "displayName"
        );
    }
}
```

Repository Java:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Hai kiểu public được hiểu là các đơn vị mã nguồn riêng. Cấu hình JPA và schema vẫn là những phần cần có của ứng dụng.

### 3.2. DTO và service Kotlin

```kotlin
data class CustomerView(
    val id: Long,
    val displayName: String
)
```

Kotlin có thể truy cập getter Java bằng cú pháp property, chẳng hạn `customer.id` và `customer.displayName`.

```kotlin
import java.util.NoSuchElementException

import org.springframework.data.repository.findByIdOrNull
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class CustomerService(
    private val customers: CustomerRepository
) {

    @Transactional(readOnly = true)
    fun find(id: Long): CustomerView? {
        val customer = customers.findByIdOrNull(id)
            ?: return null

        return toView(customer)
    }

    @Transactional
    fun rename(id: Long, newName: String): CustomerView {
        require(newName.isNotBlank()) {
            "Display name is required"
        }

        val customer = customers.findByIdOrNull(id)
            ?: throw NoSuchElementException(
                "Customer not found: $id"
            )

        customer.rename(newName)

        val saved = customers.save(customer)
        return toView(saved)
    }

    private fun toView(customer: Customer): CustomerView =
        CustomerView(
            id = requireNotNull(customer.id) {
                "A persisted customer must have an identifier"
            },
            displayName = customer.displayName
        )
}
```

Những điểm đáng chú ý:

- `findByIdOrNull` là extension của Spring Data giúp chuyển kết quả `Optional` của repository đồng bộ thành giá trị nullable trong Kotlin.
- `CustomerView?` biểu diễn rõ khả năng không tìm thấy.
- `rename` chọn chính sách báo lỗi khi không có khách hàng.
- Service vẫn gọi JPA đồng bộ; thread thực thi vẫn có thể chờ database.
- Việc kiểm tra tên rỗng là quy tắc ứng dụng. Kotlin `String` chỉ loại khả năng null ở hợp đồng kiểu, không tự loại chuỗi rỗng.
- Service dùng kết quả trả về từ `save`; đây là thói quen phù hợp khi thao tác lưu có thể trả instance khác.

Ví dụ giả định cấu hình Kotlin cho Spring cho phép tạo proxy cần thiết của service. Phần cấu hình đó được bàn ở mục sau.

## 4. Hiểu extension Kotlin trước khi thay đổi repository

Extension giúp viết cách gọi phù hợp hơn với Kotlin trong khi vẫn sử dụng hợp đồng repository đã có.

Ví dụ:

```kotlin
import org.springframework.data.repository.findByIdOrNull

val customer: Customer? = customers.findByIdOrNull(id)
```

Ở mức ý nghĩa, extension chuyển:

```text
Optional<Customer>
    -> Customer hoặc null
```

Nó không tự:

- Chuyển query blocking thành non-blocking.
- Thêm một truy vấn mới vào repository.
- Bổ sung transaction ngoài cấu hình hiện có.
- Thay đổi semantics không tìm thấy của store.
- Tạo một Kotlin entity thay cho entity Java.

Extension cần import đúng và cần có dependency chứa extension đó. Không nên tạo một method mới trùng ý nghĩa chỉ vì IDE chưa tự đề xuất import.

Kotlin còn có extension theo từng module, đôi khi tận dụng generic reified để giảm việc truyền `Class`. Phải phân biệt extension của Commons với extension riêng của store; sự tiện dụng ở cú pháp không mở rộng khả năng mà implementation chưa hỗ trợ.

## 5. Viết repository interface Kotlin trên domain Java

Có thể khai báo repository bằng Kotlin trong khi kiểu domain vẫn là Java.

Ví dụ lựa chọn khác:

```kotlin
import org.springframework.data.repository.CrudRepository

interface KotlinCustomerRepository :
    CrudRepository<Customer, Long> {

    fun findByDisplayName(displayName: String): Customer?

    fun findAllByDisplayNameStartingWith(
        prefix: String
    ): List<Customer>
}
```

Query một kết quả cần có dữ liệu và ràng buộc phù hợp. Nếu nhiều khách hàng cùng tên, `findByDisplayName` không có hợp đồng “tùy ý chọn một người”; cần chọn kiểu kết quả nhiều hoặc một khóa nghiệp vụ duy nhất khi đó là yêu cầu thực tế.

Những điểm cần hiểu:

- Dấu `:` trong Kotlin biểu diễn việc kế thừa interface.
- Chữ ký kế thừa từ Java vẫn giữ hợp đồng Java tương ứng.
- `findById` của `CrudRepository` vẫn trả `Optional<Customer>`.
- Không thể chỉ override `findById` thành `Customer?` và coi đó là cùng một chữ ký với kiểu trả về tương thích.
- Có thể sử dụng `findByIdOrNull` ở nơi gọi để viết code nullable tự nhiên hơn.

Repository Kotlin ở đây là một biến thể minh họa. Khi đưa vào ứng dụng, tổ chức interface, component scan và injection rõ ràng; không cần tạo thêm repository cho cùng domain chỉ để đổi ngôn ngữ.

Với fragment hoặc repository base interface tùy biến, Kotlin vẫn phải tuân theo quy ước và metadata của Spring Data. Tên một class Kotlin không tự làm nó trở thành implementation được repository factory sử dụng.

## 6. Nullability tại ranh giới Java–Kotlin

Kotlin có sự khác biệt ở mức kiểu:

```kotlin
val requiredName: String
val optionalName: String?
```

Với mã Java, mức thông tin mà compiler Kotlin nhìn thấy phụ thuộc annotation nullability và metadata có sẵn. Một API Java thiếu thông tin có thể được nhìn dưới dạng platform type.

Platform type cho phép cách dùng linh hoạt để tương tác với Java, nhưng cũng có thể đẩy lỗi null sang runtime. Không coi mọi getter Java được gọi bằng cú pháp property là một hợp đồng non-null đã được xác minh.

### 6.1. Hợp đồng repository cần có chủ đích

| Khai báo/kiểu nhìn từ Kotlin | Ý nghĩa cần thiết kế |
|---|---|
| `Customer?` | Không tìm thấy có thể được biểu diễn bằng null |
| `Customer` | Bên gọi kỳ vọng một giá trị, thiếu kết quả phải được xử lý theo hợp đồng |
| `Optional<Customer>` | Sự vắng mặt nằm trong wrapper Java |
| `List<Customer>` | Không có kết quả thường được biểu diễn bằng list rỗng |
| `Flow<Customer>` | Không có kết quả có thể là flow hoàn tất mà không phát phần tử |
| `Boolean` | `false` là một giá trị hợp lệ, không đồng nghĩa thiếu giá trị |

Với hạ tầng kiểm tra nullability của repository Kotlin được hỗ trợ, một query không có kết quả nhưng khai báo kiểu trả về non-null có thể bị báo lỗi thay vì trả null, chẳng hạn bằng `EmptyResultDataAccessException`.

Không khai báo non-null chỉ để tránh viết nhánh xử lý không tìm thấy. Hãy chọn đúng hợp đồng nghiệp vụ.

### 6.2. Nullability không thay thế schema hoặc validation

Các ràng buộc sau ở những lớp khác nhau:

```text
Kotlin String
    -> hợp đồng kiểu trong mã Kotlin

Validation nghiệp vụ
    -> chuỗi phải có nội dung hoặc đúng định dạng

Mapping và schema
    -> cách lưu, cột có cho phép NULL hay không

Dữ liệu hiện hữu
    -> giá trị thực tế đang có trong store
```

Một property Kotlin non-null không tự sửa các hàng cũ đang có dữ liệu không hợp lệ. Nếu store trả null cho một constructor parameter non-null, quá trình materialization có thể lỗi.

Cũng cần thống nhất cấu hình compiler khi đọc annotation nullability từ Java theo bộ phiên bản Spring và Kotlin đang dùng. Không áp dụng máy móc một tùy chọn compiler từ dự án khác mà chưa xem nó phù hợp với metadata của dependency hay không.

## 7. Kotlin domain model và materialization của Spring Data

Ngoài service và repository, Kotlin có thể biểu diễn domain model bằng primary constructor và các property bất biến.

Ví dụ cho mapping quan hệ của Spring Data R2DBC:

```kotlin
import org.springframework.data.annotation.Id
import org.springframework.data.relational.core.mapping.Table

@Table("customer_profile")
data class CustomerProfile(
    @field:Id
    val id: Long? = null,
    val email: String,
    val displayName: String
)
```

Ví dụ chọn:

- `Long?` cho ID vì đối tượng mới chưa được store cấp ID.
- `val` để code ứng dụng không gán lại property sau khi tạo.
- Primary constructor để biểu đạt dữ liệu cần khi tạo object.
- Use-site target `@field:Id` để chỉ rõ annotation gắn vào backing field.

Đây là mapping quan hệ của lựa chọn R2DBC, không phải một JPA entity. JPA sử dụng annotation ID và quy tắc entity của JPA.

### 7.1. Constructor là một phần của hợp đồng lưu trữ

Spring Data có cơ chế tạo đối tượng từ dữ liệu store, bao gồm hỗ trợ mô hình Kotlin trong các module phù hợp.

Nếu class có nhiều constructor hoặc factory tham gia việc tạo persistent object, cần tổ chức đường tạo đối tượng rõ ràng. `@PersistenceCreator` có thể được dùng để chỉ định creator trong những cơ chế mapping hỗ trợ annotation này.

Không thêm annotation chỉ để che một mô hình constructor mâu thuẫn. Constructor được chọn phải nhận đủ dữ kiện cần thiết và có tên/thông tin parameter phù hợp để mapping làm việc.

`@PersistenceCreator` cũng không thay thế các yêu cầu của JPA về constructor entity.

### 7.2. Giá trị mặc định Kotlin khác với default ở database

Spring Data có hỗ trợ sử dụng default parameter Kotlin trong quá trình materialization phù hợp. Khi dữ liệu không cung cấp giá trị hoặc giá trị được xử lý như không có đối số theo cơ chế hỗ trợ, constructor có thể dùng default.

Ví dụ ý tưởng:

```kotlin
data class Preferences(
    val locale: String = "vi"
)
```

Default này là hành vi khi tạo object Kotlin. Nó không tự tạo `DEFAULT 'vi'` trong database và không nên bị dùng để che một field bắt buộc đang thiếu dữ liệu.

Cần phân biệt:

- Giá trị mặc định khi ứng dụng tạo object.
- Giá trị mặc định khi mapping đọc dữ liệu.
- Giá trị mặc định mà database áp dụng khi insert.
- Quy tắc migration cho dữ liệu cũ.

### 7.3. Dùng kết quả trả về sau save

Một model bất biến có thể cần instance mới để mang ID hoặc metadata do store gán.

Với repository phù hợp:

```kotlin
val draft = CustomerProfile(
    email = "an@example.test",
    displayName = "Nguyễn An"
)

val saved = profiles.save(draft)
val persistedId = requireNotNull(saved.id)
```

Đoạn này đặt trong một hàm suspend khi `profiles` là coroutine repository ở phần sau.

Không giả định rằng `draft.id` đã tự đổi sau save. Kiểu `val` và data class cần được hiểu cùng cách store thực hiện mapping và trả kết quả.

`val` cũng không làm toàn bộ đồ thị object bất biến. Một property `val items: MutableList<...>` vẫn có nội dung thay đổi được.

## 8. Những lưu ý riêng khi dùng Kotlin với JPA

JPA có yêu cầu và cơ chế khác với constructor mapping của R2DBC hoặc MongoDB. Khi chuyển một JPA entity sang Kotlin, cần xét:

- Constructor không tham số phù hợp cho JPA.
- Điều kiện để provider tạo proxy hoặc thực hiện cơ chế hỗ trợ của nó.
- Class và member Kotlin có tính final theo mặc định.
- Cách truy cập field/property của mapping.
- ID, version và các thuộc tính do persistence infrastructure quản lý.
- Hành vi của `equals`, `hashCode` và `toString`.

Data class sinh các method dựa trên property trong primary constructor. Với entity JPA, việc đưa association lazy hoặc ID thay đổi sau persist vào các method đó có thể tạo hành vi không mong muốn.

Ví dụ:

- `toString` có thể truy cập association mà ứng dụng chưa định tải.
- `equals` và `hashCode` có thể phụ thuộc những thuộc tính chưa ổn định.
- Tính final có thể không phù hợp với chiến lược proxy đang dùng.

Vì vậy, không dùng data class làm khuôn mặc định cho mọi JPA entity. DTO và value object thường có nhu cầu khác với entity có lifecycle persistence.

Một lựa chọn thực tế là giữ JPA entity Java ở giai đoạn đầu, dùng Kotlin cho service và DTO, rồi chuyển entity khi đã thống nhất chiến lược mapping.

Plugin hoặc cấu hình compiler cho JPA có thể hỗ trợ đáp ứng yêu cầu constructor và class. Hãy kiểm tra đầy đủ nhu cầu no-arg và khả năng proxy của provider, thay vì chỉ thêm một plugin rồi mặc định mọi entity Kotlin đã hợp lệ.

## 9. Cấu hình Kotlin cần xét theo thành phần đang dùng

Những thành phần thường liên quan:

| Thành phần | Vai trò |
|---|---|
| Kotlin compiler cho JVM | Biên dịch mã Kotlin để tương tác với Java/JVM |
| Kotlin standard library | Các kiểu và API Kotlin cơ bản |
| `kotlin-reflect` | Hỗ trợ đọc cấu trúc, constructor và thông tin Kotlin khi framework cần |
| Cấu hình/plugin Kotlin cho Spring | Hỗ trợ các class Spring cần được mở cho proxy |
| Cấu hình/plugin cho JPA nếu dùng JPA | Hỗ trợ các yêu cầu riêng của entity |
| Module Jackson cho Kotlin nếu dùng JSON | Hỗ trợ serialization/deserialization Kotlin theo cấu hình web |
| Thư viện coroutine nếu dùng coroutine | Cung cấp `suspend` runtime, `Flow` và adapter cần thiết |

Không phải mọi thành phần đều cần cho một mục đích giống nhau. Module Jackson phục vụ JSON; nó không phải cơ chế mapping của database. Thư viện coroutine không thay thế driver của store.

Kotlin class final theo mặc định. Nếu một Spring service cần proxy dựa trên class cho transaction hoặc tính năng khác, phải có cấu hình phù hợp, chẳng hạn plugin Kotlin cho Spring hoặc khai báo mở theo chủ đích.

Trong dự án Java–Kotlin hỗn hợp, cũng cần cấu hình thứ tự/source set biên dịch và JVM target tương thích. Compiler Java và Kotlin phải nhìn thấy các kiểu mà chúng tham chiếu.

Nên để bộ dependency của ứng dụng quản lý các phiên bản tương thích, thay vì chọn độc lập từng thư viện Spring Data, Kotlin và coroutine mà không xét tương thích.

## 10. Coroutine là lựa chọn bổ sung của mô hình thực thi

Coroutine giúp viết luồng bất đồng bộ bằng cú pháp tuần tự. Một hàm `suspend` có thể tạm ngừng coroutine khi chờ kết quả thông qua API phù hợp.

Tuy nhiên, bản thân từ khóa `suspend` không sửa cách một thư viện thực hiện I/O.

```kotlin
suspend fun loadWithJpa(id: Long): Customer? =
    jpaRepository.findByIdOrNull(id)
```

Nếu repository bên trong là JPA đồng bộ, lời gọi vẫn có thể chặn thread trong thời gian chờ database. Việc đặt nó vào một hàm suspend không tạo driver non-blocking.

Với coroutine repository dựa trên hạ tầng reactive được hỗ trợ, cách sử dụng thường là:

| Dạng reactive | Dạng coroutine thường tương ứng | Ý nghĩa |
|---|---|---|
| `Mono<T>` với kết quả bắt buộc | `suspend fun ...: T` | Một giá trị hoặc lỗi |
| `Mono<T>` cho phép không có kết quả | `suspend fun ...: T?` | Giá trị hoặc null |
| `Flux<T>` | `fun ...: Flow<T>` | Chuỗi không đến nhiều giá trị |
| `Mono<Void>` | `suspend fun ...: Unit` | Hoàn tất hoặc lỗi |

Kiểu trả về phải phản ánh hợp đồng thực tế. Chọn `T` hay `T?` quyết định cách biểu diễn không tìm thấy.

`Flow` là abstraction của Kotlin coroutines; nó không phải `java.util.stream.Stream` và cũng không phải trực tiếp cùng interface với Reactive Streams `Publisher`. Adapter có thể nối các mô hình khi có dependency phù hợp.

Coroutine không buộc mỗi lời gọi tạo một thread mới. Non-blocking còn phụ thuộc đường I/O bên dưới và cách ứng dụng kết hợp công việc.

## 11. CoroutineCrudRepository và ví dụ R2DBC

Interface của Commons:

```kotlin
import org.springframework.data.repository.kotlin.CoroutineCrudRepository
```

Repository cho `CustomerProfile`:

```kotlin
import kotlinx.coroutines.flow.Flow

import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface ProfileRepository :
    CoroutineCrudRepository<CustomerProfile, Long> {

    suspend fun findByEmail(
        email: String
    ): CustomerProfile?

    fun findAllByDisplayNameStartingWith(
        prefix: String
    ): Flow<CustomerProfile>
}
```

Ví dụ giả định module R2DBC và các thư viện coroutine/adapter cần thiết đã được cấu hình, đồng thời query derivation được module hỗ trợ.

Việc khai báo interface này không tự bổ sung khả năng coroutine repository cho một store không có tích hợp tương ứng. Với JPA, không suy rằng thay `JpaRepository` bằng `CoroutineCrudRepository` là một phép chuyển đổi tương đương.

Một service:

```kotlin
import java.util.NoSuchElementException

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

import org.springframework.stereotype.Service

data class ProfileView(
    val id: Long,
    val displayName: String
)

@Service
class ProfileService(
    private val profiles: ProfileRepository
) {

    suspend fun create(
        email: String,
        displayName: String
    ): CustomerProfile {
        require(email.isNotBlank())
        require(displayName.isNotBlank())

        val draft = CustomerProfile(
            email = email,
            displayName = displayName
        )

        return profiles.save(draft)
    }

    suspend fun requireProfile(id: Long): CustomerProfile =
        profiles.findById(id)
            ?: throw NoSuchElementException(
                "Profile not found: $id"
            )

    fun search(prefix: String): Flow<ProfileView> =
        profiles.findAllByDisplayNameStartingWith(prefix)
            .map { profile ->
                ProfileView(
                    id = requireNotNull(profile.id),
                    displayName = profile.displayName
                )
            }
}
```

Các điểm cần đọc đúng:

- `create` và `requireProfile` phải được gọi từ ngữ cảnh coroutine phù hợp.
- `findById` của coroutine repository cho phép null khi không có đối tượng theo hợp đồng của nó.
- `search` trả về flow, không tự thu thập toàn bộ dữ liệu trong service.
- Trong đường repository flow được trì hoãn thông thường, collection mới thực hiện công việc nguồn.
- Data class được lưu qua cơ chế của R2DBC, không qua JPA persistence context.

Ví dụ không thiết lập một transaction cho nhiều thao tác. Nếu nghiệp vụ cần tính nguyên tử giữa các bước, phải bổ sung transaction infrastructure và cách tích hợp coroutine được store hỗ trợ.

## 12. Giữ rõ ranh giới Java, Reactor và coroutine

Một dự án có thể có cả API đồng bộ, Reactor và coroutine. Cần chọn ranh giới chuyển đổi rõ ràng.

### 12.1. Java gọi Kotlin thông thường

Java có thể sử dụng nhiều class và method Kotlin qua bytecode JVM. Với API hướng đến bên gọi Java, nên xét:

- Constructor và parameter mặc định.
- Cách gọi property/getter.
- Các kiểu collection và nullability.
- Việc cần overload hoặc factory dễ sử dụng.
- Các annotation tương tác JVM khi thật sự cần.

Không giả định default parameter Kotlin tự tạo mọi overload mà Java muốn gọi.

### 12.2. Java gọi suspend cần một hợp đồng phù hợp

Hàm suspend có biểu diễn JVM liên quan đến continuation. Bên gọi Java không sử dụng nó giống một method đồng bộ trả `CustomerProfile`.

Nếu cần API dùng thuận tiện từ Java, có thể thiết kế một lớp biên giữ hợp đồng Java thích hợp, chẳng hạn API reactive hoặc một facade đồng bộ có ranh giới chờ được xác định rõ.

Không thêm `runBlocking` vào mọi method chỉ để che sự khác biệt. Làm vậy thay đổi đặc tính thực thi và có thể chặn thread của một server reactive.

### 12.3. Chuyển từ Mono sang suspend bằng adapter

Với reactive repository đã có, có thể dùng adapter coroutine thay vì `block()`:

```kotlin
import kotlinx.coroutines.reactor.awaitSingleOrNull

suspend fun findProfile(id: Long): CustomerProfile? =
    reactiveProfiles.findById(id).awaitSingleOrNull()
```

Ví dụ giả định `reactiveProfiles` là repository reactive trả `Mono<CustomerProfile>`.

`awaitSingleOrNull` phù hợp khi nguồn có thể hoàn tất rỗng. `awaitSingle` phù hợp với hợp đồng bắt buộc có một phần tử và sẽ không coi nguồn rỗng là một giá trị hợp lệ.

Đặc biệt, `Mono<Void>` không phát một phần tử dữ liệu. Không chờ một phần tử bắt buộc từ nó chỉ để xác nhận thao tác thành công.

Adapter giữ sự liên hệ với cơ chế coroutine theo hỗ trợ của thư viện. Nó không biến một nguồn có mã blocking bên trong thành I/O non-blocking.

## 13. Transaction, context và cancellation

Khi đưa coroutine vào ứng dụng Spring Data, cần xét context của đường thực thi.

### 13.1. Transaction phải phù hợp với mô hình

Transaction đồng bộ thường gắn với ngữ cảnh thread theo hạ tầng tương ứng. Transaction reactive dùng cơ chế context của pipeline và cần transaction manager phù hợp.

Một hàm Kotlin có `@Transactional` không đủ để kết luận rằng mọi sự kết hợp JPA, coroutine và việc đổi dispatcher đều giữ cùng semantics.

Cần kiểm tra:

- Transaction manager nào thực sự được chọn.
- Module store hỗ trợ cách thực thi nào.
- Toàn bộ thao tác cần nguyên tử có nằm trong ranh giới quản lý hay không.
- Việc suspension và chuyển context có được hạ tầng đang dùng hỗ trợ đúng không.

`withContext(Dispatchers.IO)` có thể bố trí mã blocking lên dispatcher thích hợp, nhưng vẫn sử dụng thread trong thời gian chờ. Cũng không nên coi nó là cách tự chuyển một transaction ThreadLocal từ thread khác sang.

### 13.2. Giữ công việc trong vòng đời của bên gọi

Không tự tạo `GlobalScope.launch` để thực hiện thao tác repository rồi trả kết quả như công việc đã hoàn tất. Công việc tách rời có thể vượt khỏi vòng đời request và ranh giới transaction dự kiến.

Với flow, không collect ở service rồi lại trả cùng nguồn để framework collect thêm nếu ứng dụng chỉ định thực hiện một lần. Nguồn cold có thể chạy lại khi được collect lại.

### 13.3. Cancellation cần được truyền đúng

Coroutine có cơ chế cancellation. Không bắt mọi exception rồi đổi thành null nếu điều đó nuốt cả `CancellationException`.

Việc biến lỗi thành “không tìm thấy” còn làm sai hợp đồng repository. Hãy phân biệt:

- Kết quả không có dữ liệu.
- Lỗi truy cập store.
- Lỗi nghiệp vụ.
- Yêu cầu hủy công việc.

Cancellation cũng không tự là bằng chứng mọi thao tác database đã rollback; điều đó thuộc transaction và khả năng của driver.

## 14. Chọn phạm vi đưa Kotlin vào dự án

Có thể tiến hành theo các bước có kết quả quan sát được:

| Bước | Thay đổi | Điều nên xác minh |
|---|---|---|
| 1 | Thêm DTO hoặc value object Kotlin | Java gọi được khi cần, JSON và validation đúng |
| 2 | Viết service Kotlin gọi repository Java | Nullability, exception và transaction được giữ rõ |
| 3 | Viết một repository interface Kotlin | Query method và kiểu trả về đúng hợp đồng |
| 4 | Chuyển một domain model phù hợp | Constructor, ID, mapping và round-trip dữ liệu đúng |
| 5 | Thêm một đường coroutine có mục tiêu | Store, driver, adapter và transaction phù hợp |
| 6 | Mở rộng sau khi có bằng chứng | Không tạo hai mô hình thực thi khó phân biệt cho cùng use case |

Khi chọn entity đầu tiên để chuyển, nên xem độ phức tạp mapping, association và lifecycle. Một DTO độc lập hoặc model constructor-based đơn giản có ít ràng buộc hơn một JPA entity có nhiều association lazy và inheritance.

Phạm vi coroutine nên được quyết định từ đường xử lý thực tế. Nếu cả ứng dụng đang sử dụng JPA đồng bộ và mục tiêu chỉ là viết service dễ đọc, Kotlin thông thường có thể đáp ứng mà không cần thay đổi mô hình I/O.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách đánh giá đúng |
|---|---|
| Viết Kotlin thì phải chuyển toàn bộ entity Java | Có thể đưa Kotlin vào từng lớp |
| `suspend` làm mọi repository non-blocking | Cần hạ tầng I/O và module hỗ trợ |
| Data class luôn là entity phù hợp | Phải xét constructor, equality, lifecycle và proxy |
| `val` làm object cùng mọi thành phần bất biến | Các object hoặc collection bên trong vẫn có thể thay đổi |
| `String` bảo đảm database không chứa null | Schema và dữ liệu thực tế vẫn phải nhất quán |
| `findById` kế thừa từ Java tự trả `T?` | Hợp đồng `Optional` vẫn tồn tại; extension giúp chuyển cách gọi |
| Default parameter tương đương default cột | Đây là các cơ chế ở những lớp khác nhau |
| Có Jackson Kotlin module là mapping database đã đủ | JSON và persistence là hai cơ chế riêng |
| Có coroutine library là mọi store hỗ trợ coroutine repository | Khả năng phụ thuộc module và implementation |
| Đổi dispatcher tự giữ transaction JPA | Context và transaction phải được thiết kế phù hợp |
| `Flow` tự có tổng trang và số bản ghi | Metadata phân trang phải được xây dựng theo API hỗ trợ |
| Query DTO Kotlin luôn được tối ưu giống nhau | Khả năng projection và mapping phụ thuộc store |

## 16. Kiểm chứng trước khi mở rộng phạm vi

Với một phần Kotlin mới, nên xác minh những hợp đồng quan trọng:

- Java và Kotlin cùng biên dịch, bên gọi nhìn đúng constructor và method.
- Repository vẫn được phát hiện và gắn đúng module.
- Query tìm thấy, không tìm thấy và có nhiều kết quả phản ánh đúng kiểu khai báo.
- Entity hoặc document được lưu rồi đọc lại đúng dữ liệu.
- ID và version do store quản lý được lấy từ kết quả lưu.
- Proxy transaction của service hoạt động theo cấu hình.
- JSON của DTO giữ đúng tên field và chính sách null nếu có lớp web.
- Với coroutine, kết quả nullable, flow rỗng, lỗi và cancellation được xử lý rõ.

Mock một repository không đủ để chứng minh constructor mapping hoặc transaction integration của store. Khi chuyển domain model hay mô hình thực thi, cần có kiểm chứng tích hợp phù hợp với thay đổi đó.

Bài học này tập trung vào phạm vi sử dụng ngôn ngữ; những kiểm chứng trên giúp xác định phần nào vẫn giữ hợp đồng cũ và phần nào đã thật sự thay đổi cách truy cập dữ liệu.

## 17. Bài thực hành

Chọn một chức năng đang dùng repository Java:

1. Giữ entity và repository hiện có.
2. Viết một DTO Kotlin và một service Kotlin gọi repository đó.
3. Dùng `findByIdOrNull` và chọn rõ chính sách khi không tìm thấy.
4. Giải thích platform type nào còn xuất hiện ở API Java và cách kiểm soát nó.
5. Đề xuất một domain model Kotlin phù hợp, ghi rõ store và yêu cầu constructor/mapping.
6. Nếu muốn dùng coroutine, chỉ ra module reactive, driver và adapter cần thiết.
7. So sánh semantics của `Customer?`, `Optional<Customer>`, `Mono<Customer>` và `Flow<Customer>`.
8. Xác định ranh giới transaction trước khi thay đổi cách thực thi.

Kết quả cần giải thích được là: **Kotlin bổ sung cách biểu đạt kiểu và API trên JVM; Spring Data giữ các abstraction chung; mapping và mô hình thực thi vẫn do lựa chọn store cùng hạ tầng tương ứng quyết định**.