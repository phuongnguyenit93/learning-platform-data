# Tương tác với Kotlin và kiểm thử dữ liệu thiếu

Trong Kotlin, `Customer` và `Customer?` là hai hợp đồng khác nhau. Nhưng một ứng dụng Spring Data còn có nhiều dạng “thiếu dữ liệu”: không có entity phù hợp, có entity nhưng một thuộc tính null, không có phần tử trong tập kết quả hoặc đầu vào không được cung cấp. Nếu gom tất cả thành một nhánh `null`, ứng dụng dễ xử lý sai nghiệp vụ và viết những kiểm thử vẫn pass dù truy vấn không trả đúng dữ liệu.

Bài học thuộc chương **Null và nullability** của **SPRING_DATA_COMMONS**. Mục tiêu là đọc đúng hợp đồng Kotlin/Java ở repository, xác định trách nhiệm của compiler và runtime, rồi thiết kế dữ liệu kiểm thử phân biệt được từng tình huống. Các ví dụ đồng bộ chính dùng JPA; phần reactive và coroutine được tách riêng theo khả năng module.

## 1. “Thiếu dữ liệu” có nhiều tầng

| Tình huống | Biểu hiện có thể có | Ý nghĩa |
| --- | --- | --- |
| Không có entity khớp predicate | `null`, `Optional.empty()` hoặc lỗi theo hợp đồng đơn kết quả | Truy vấn chạy nhưng không tìm thấy entity |
| Entity có thuộc tính tùy chọn chưa được đặt | Entity tồn tại, thuộc tính bằng null | Không được đánh đồng với không có entity |
| Không có phần tử trong truy vấn nhiều kết quả | Collection rỗng hoặc publisher/flow hoàn tất không có phần tử | Một kết quả hợp lệ của truy vấn |
| Caller truyền null vào tham số | Được chấp nhận hoặc bị từ chối tùy hợp đồng | Là vấn đề đầu vào, chưa nói lên dữ liệu trong store |
| Store không cung cấp giá trị cho thuộc tính bắt buộc | Có thể lỗi mapping/khởi tạo object | Không phải một entity “không tìm thấy” bình thường |
| Store hoặc truy vấn bị lỗi | Exception hoặc tín hiệu lỗi | Không nên tự biến thành dữ liệu thiếu |

Ví dụ, `customer == null` khác với `customer.nickname == null`. Một kiểm thử cho biệt danh chưa được đặt cần chứng minh khách hàng thật sự tồn tại trước khi kiểm tra biệt danh.

## 2. Kotlin mô tả hợp đồng ở chữ ký

Những hình dạng kết quả cơ bản:

```kotlin
fun findCustomer(...): Customer?          // Không có hoặc một entity
fun requireCustomer(...): Customer       // Kỳ vọng một entity không null
fun findCustomers(...): List<Customer>   // Một danh sách không null
```

Về mặt kiểu Kotlin:

| Kiểu | Chính container/giá trị có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| `Customer` | Không | Không áp dụng |
| `Customer?` | Có | Không áp dụng |
| `List<Customer>` | Không | Không theo hợp đồng kiểu |
| `List<Customer?>` | Không | Có |
| `List<Customer>?` | Có | Không theo hợp đồng kiểu |

Khi dùng repository truy vấn nhiều entity, `List<Customer>` với danh sách rỗng thường là hợp đồng rõ ràng hơn việc dùng một danh sách nullable để biểu đạt “không có hàng”. Không suy từ việc Kotlin viết được một generic rằng mọi Spring Data module hỗ trợ trực tiếp chữ ký đó.

### Compiler bảo vệ những gì?

Với tham số `email: String`, một lời gọi Kotlin thông thường truyền trực tiếp `null` sẽ không hợp lệ ở mức kiểu. Với giá trị `Customer?`, caller phải kiểm tra, dùng safe call, Elvis hoặc một cách xử lý phù hợp trước khi sử dụng như `Customer`.

Nhưng Kotlin vẫn tương tác với Java, reflection, proxy và dữ liệu từ bên ngoài. Compiler không tự thực thi câu truy vấn, không tạo ràng buộc cơ sở dữ liệu và không chứng minh mapping luôn cung cấp dữ liệu hợp lệ.

`!!` chỉ yêu cầu kiểm tra không null tại runtime. Nó không sửa hợp đồng repository hay tạo entity còn thiếu.

## 3. Spring Data đọc nullability Kotlin như thế nào?

Kotlin biểu đạt nullability trong metadata của khai báo, không chỉ bằng một annotation Java đơn lẻ. Hạ tầng Spring Data có thể sử dụng metadata Kotlin để xác định hợp đồng tham số và kết quả của repository.

Để các cơ chế introspection Kotlin liên quan hoạt động đúng, cần có các dependency hỗ trợ phù hợp, trong đó `kotlin-reflect` là thành phần cần chú ý cho việc đọc nullability Kotlin ở runtime. Không nên chỉ nhìn việc source Kotlin biên dịch thành công rồi kết luận repository proxy đã có đầy đủ thông tin để kiểm tra hợp đồng.

Có thể hình dung hai lớp bổ sung nhau:

```text
Kotlin compiler
    Kiểm tra kiểu tại các lời gọi mà compiler nhìn thấy
             |
             v
Repository proxy và metadata Kotlin
    Áp dụng hợp đồng ở ranh giới được hạ tầng quản lý
             |
             v
Module lưu trữ
    Thực thi truy vấn và ánh xạ dữ liệu thực tế
```

Một phương thức đơn kết quả khai báo không null có thể phát `EmptyResultDataAccessException` khi không tìm thấy entity trong cơ chế repository được cấu hình đúng. Một phương thức trả kiểu nullable có thể trả null thay vì phát lỗi thiếu kết quả đó.

Không coi đây là một bộ kiểm tra đệ quy cho mọi field và mọi object trong toàn ứng dụng. Một hàm Kotlin thông thường, một mock hoặc một instance được tạo trực tiếp không tự chứng minh hành vi của repository proxy thật.

## 4. Mô hình và repository minh họa

Giả sử entity `Customer` có mapping và constructor phù hợp cho JPA:

| Thuộc tính | Kiểu Kotlin | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long?` trong vòng đời entity | Chưa được gán trước khi lưu nếu dùng định danh sinh tự động |
| `tenantId` | `String` | Phạm vi tổ chức |
| `email` | `String` | Địa chỉ email |
| `nickname` | `String?` | Biệt danh có thể chưa được đặt |

Giả định cặp tenant và email được thiết kế là duy nhất theo nghiệp vụ và schema tương ứng. Trong các đoạn tạo fixture, entity có thể được dựng bằng các named argument `tenantId`, `email`, `nickname`; phần mapping đầy đủ được lược bỏ.

Ví dụ **Spring Data JPA**:

```kotlin
import org.springframework.data.jpa.repository.JpaRepository

interface CustomerRepository : JpaRepository<Customer, Long> {

    fun findNullableByTenantIdAndEmail(
        tenantId: String,
        email: String
    ): Customer?

    fun getRequiredByTenantIdAndEmail(
        tenantId: String,
        email: String
    ): Customer

    fun findAllByTenantId(tenantId: String): List<Customer>

    fun findByTenantIdAndNickname(
        tenantId: String,
        nickname: String?
    ): List<Customer>
}
```

Các từ `Nullable` và `Required` trước `By` giúp diễn đạt và phân biệt tên method; nullability thật sự đến từ kiểu trả về và metadata, không đến từ việc parser hiểu hai từ đó như một chính sách bắt buộc.

Không dùng từ `get` để suy rằng mọi repository method ở mọi module luôn phải trả entity. Phương thức minh họa là một query method riêng có hợp đồng return không null, không phải mọi thao tác cơ sở có tên bắt đầu bằng `get`.

### 4.1. Khi không có khách hàng

```kotlin
val optionalCustomer: Customer? = repository.findNullableByTenantIdAndEmail(
    "tenant-a", "missing@example.test"
)
```

Kết quả có thể là null. Nếu gọi phương thức `getRequiredByTenantIdAndEmail` với cùng dữ liệu không tồn tại, cần kỳ vọng đường xử lý thiếu kết quả theo hợp đồng không null, thay vì viết caller như thể nó luôn nhận được một entity hợp lệ.

### 4.2. Khi có khách hàng nhưng thiếu nickname

```kotlin
val customer = repository.findNullableByTenantIdAndEmail(tenantId, email)
    ?: throw CustomerNotFoundException()

val label = customer.nickname ?: "Chưa đặt biệt danh"
```

Giả sử ứng dụng có exception nghiệp vụ:

```kotlin
class CustomerNotFoundException : RuntimeException("Customer not found")
```

Hai Elvis có trách nhiệm khác nhau: nhánh thứ nhất xử lý không có entity, nhánh thứ hai xử lý một thuộc tính tùy chọn của entity đã tồn tại.

Viết ngay `repository.findNullableByTenantIdAndEmail(...)?.nickname ?: "Chưa đặt"` có thể hợp lệ cho một yêu cầu hiển thị cụ thể, nhưng nó gộp hai trường hợp. Nếu nghiệp vụ phân biệt không tìm thấy khách hàng với thiếu biệt danh, cách đó làm mất thông tin cần thiết.

## 5. Gọi repository Java từ Kotlin

### 5.1. Platform type là một điểm cần đọc kỹ

Một API Java không có metadata nullability đủ rõ có thể được Kotlin biểu diễn dưới dạng platform type, thường được IDE hiển thị với dấu `!`. Ký hiệu đó không phải một kiểu để viết trực tiếp trong source Kotlin.

Platform type tạo sự linh hoạt khi dùng API Java, nhưng cũng để lại rủi ro: một giá trị được caller sử dụng như không null vẫn có thể là null tại runtime.

Cần đọc hợp đồng API Java, annotation và cách query biểu đạt thiếu kết quả, thay vì chỉ dựa vào việc một phép gán Kotlin được compiler chấp nhận.

### 5.2. Annotation và cấu hình phụ thuộc hệ phiên bản

Với Spring Data 3.x dùng các annotation `org.springframework.lang.NonNullApi`, `NonNull` và `Nullable`, metadata JSR-305 giúp Kotlin hiểu API Java rõ hơn. Cấu hình compiler như `-Xjsr305=strict` ảnh hưởng mức độ xử lý hợp đồng này.

Không áp dụng một cấu hình nullability cho mọi major version hoặc mọi hệ annotation mà không đối chiếu phiên bản dự án. Chữ ký Kotlin viết trực tiếp và nullability của API Java được nhập vào là hai nguồn thông tin cần được xem riêng.

### 5.3. Phương thức CRUD Java có thể trả Optional

Một repository JPA kế thừa API Java vẫn có phương thức `findById` trả `Optional<Customer>`. Khi dùng từ Kotlin, có thể dùng extension phù hợp cho repository CRUD đồng bộ:

```kotlin
import org.springframework.data.repository.findByIdOrNull

val customer: Customer? = repository.findByIdOrNull(id)
```

Extension giúp biểu đạt kết quả bằng nullable type Kotlin; nó không đổi truy vấn, không tạo ràng buộc uniqueness và không thay id null thành một đầu vào hợp lệ.

Không áp dụng extension này như một hợp đồng chung cho repository reactive hoặc coroutine. Những abstraction đó có API và vòng đời thực thi khác.

## 6. Nullable parameter không có nghĩa tự bỏ qua bộ lọc

Trong repository ví dụ:

```kotlin
fun findByTenantIdAndNickname(
    tenantId: String,
    nickname: String?
): List<Customer>
```

Kotlin cho phép truyền null vào `nickname`. Điều đó mới giải quyết câu hỏi “tham số có được phép null ở ranh giới API không”.

Với derived query JPA so sánh bằng trong ví dụ, một nickname null có thể được diễn giải thành điều kiện `nickname IS NULL`, vẫn kết hợp với tenant đã cho. Nó không có nghĩa lấy mọi khách hàng rồi bỏ qua điều kiện biệt danh.

Do đó cần viết kiểm thử tách biệt:

- `nickname = null`: lấy khách hàng chưa có biệt danh theo ngữ nghĩa truy vấn đã chọn.
- `nickname = "An"`: lấy khách hàng có giá trị đó.
- Không muốn áp dụng bộ lọc nickname: cần một phương thức hoặc cơ chế dựng truy vấn thể hiện yêu cầu riêng.

Ngữ nghĩa null của SQL khai báo, truy vấn tài liệu, Query by Example hoặc một API khác có thể khác nhau. Kiểu `String?` không tự đồng nhất các cơ chế đó.

## 7. Dữ liệu thiếu ở tầng mapping không phải không có entity

### 7.1. Thuộc tính bắt buộc gặp dữ liệu null

Nếu store trả null cho một thuộc tính được mô hình và constructor yêu cầu không null, việc materialize object có thể thất bại. Exception cụ thể phụ thuộc module, mapping và đường khởi tạo.

Không xử lý một lỗi khởi tạo object như một kết quả “không có khách hàng” bằng cách bắt mọi exception rồi trả null. Entity có thể tồn tại, nhưng dữ liệu hoặc projection không thỏa hợp đồng.

### 7.2. Default value không phải migration dữ liệu

```kotlin
data class CustomerSummary(
    val displayName: String = "Chưa đặt tên"
)
```

Default value có ý nghĩa khi Kotlin hoặc một cơ chế khởi tạo có hỗ trợ chọn dùng giá trị mặc định. Không mặc định mọi JPA provider, projection hoặc document mapper sẽ dùng nó để sửa mọi giá trị null hoặc trường bị thiếu.

Một số module có quy tắc xử lý constructor default riêng. Cần xác nhận quy tắc đó và kiểm tra chính mapping đang dùng, không suy từ kết quả của một lời gọi constructor trực tiếp.

### 7.3. lateinit và id sinh tự động cần được đọc theo vòng đời

Một field `lateinit` có thể chưa được khởi tạo và gây lỗi khi truy cập; đó không phải cùng vấn đề với query không tìm thấy entity. Tương tự, một entity mới có `id: Long? = null` có thể đang ở trạng thái hợp lệ trước khi được lưu và nhận định danh.

Không đổi mọi thuộc tính sang nullable chỉ để im lỗi mapping. Cũng không thêm `!!` vào mọi truy cập để tạo vẻ ngoài không null. Cần xác định trạng thái nào của domain cho phép thiếu giá trị và trạng thái nào phải được ràng buộc rõ.

Với JPA/Kotlin, các yêu cầu về constructor, class/proxy và plugin hỗ trợ nếu cần là cấu hình mapping riêng. Lỗi vì entity không thể được khởi tạo không nên bị chẩn đoán nhầm thành lỗi nullability của query method.

## 8. Ma trận kiểm thử dữ liệu thiếu

Một bộ kiểm thử nên có dữ liệu đủ để phân biệt các hợp đồng:

| Fixture hoặc đầu vào | Query/hành vi | Điều cần xác nhận |
| --- | --- | --- |
| Có khách hàng đúng tenant/email | Query trả nullable và query trả không null | Cùng trả đúng khách hàng |
| Không có khách hàng phù hợp | Query trả `Customer?` | Nhận null |
| Không có khách hàng phù hợp | Query trả `Customer` | Phát lỗi thiếu kết quả theo hạ tầng repository |
| Có entity, nickname null | Query theo email | Entity tồn tại và thuộc tính bằng null |
| Không có entity trong tenant | Query trả `List<Customer>` | Nhận danh sách rỗng |
| Null nickname được cho phép | Derived equality query JPA | Chỉ chọn entity có nickname null trong đúng tenant |
| Null email từ caller Java | Tham số Kotlin `String` không null | Bị từ chối theo hợp đồng/hạ tầng runtime được cấu hình |
| Cùng email nhưng khác tenant | Query theo tenant/email | Không trả nhầm entity ngoài phạm vi |
| Nhiều hàng cho query đơn kết quả, nếu schema cho phép | Return đơn hoặc optional | Không âm thầm coi một hàng bất kỳ là dữ liệu duy nhất |
| Store/truy vấn bị lỗi | Đường lỗi | Không bị biến thành null hoặc danh sách rỗng ngoài ý định |

Nếu schema đã có unique constraint cho tenant/email, không cố tạo dữ liệu trùng rồi giả định nó sẽ được lưu thành công để kiểm tra cardinality. Khi đó cần kiểm tra ràng buộc ghi ở đúng tầng; kiểm tra nhiều kết quả chỉ phù hợp với một predicate mà schema cho phép khớp nhiều entity.

## 9. Ví dụ kiểm thử tích hợp JPA bằng Kotlin

Phần này minh họa một cấu hình **Spring Boot 3.x, Spring Data JPA 3.x và JUnit 5**, cùng `kotlin.test`. Nếu dự án dùng bộ phiên bản hoặc module khác, import và bootstrap kiểm thử cần theo đúng stack đó.

Giả định test đã có entity `Customer`, repository ở package được quét, database test phù hợp, hỗ trợ introspection Kotlin và fixture được cô lập. Các constructor/accessor sử dụng đúng mô hình ở phần trên. Đoạn mã minh họa hợp đồng, không bao gồm toàn bộ cấu hình dự án.

```kotlin
import jakarta.persistence.EntityManager
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest
import org.springframework.dao.EmptyResultDataAccessException

@DataJpaTest
class CustomerRepositoryMissingDataTest @Autowired constructor(
    private val repository: CustomerRepository,
    private val entityManager: EntityManager
) {

    @Test
    fun `nullable result is null when no customer matches`() {
        val result = repository.findNullableByTenantIdAndEmail(
            "missing-tenant", "missing@example.test"
        )

        assertNull(result)
    }

    @Test
    fun `required result fails when no customer matches`() {
        assertFailsWith<EmptyResultDataAccessException> {
            repository.getRequiredByTenantIdAndEmail(
                "missing-tenant", "missing@example.test"
            )
        }
    }

    @Test
    fun `existing customer can have a null nickname`() {
        val saved = repository.saveAndFlush(
            Customer(
                tenantId = "tenant-a",
                email = "present@example.test",
                nickname = null
            )
        )
        val expectedId = assertNotNull(saved.id)
        entityManager.clear()

        val result = assertNotNull(
            repository.findNullableByTenantIdAndEmail(
                "tenant-a", "present@example.test"
            )
        )

        assertEquals(expectedId, result.id)
        assertNull(result.nickname)
    }

    @Test
    fun `multi result query returns an empty list`() {
        val result = repository.findAllByTenantId("missing-tenant")

        assertTrue(result.isEmpty())
    }
}
```

Trong test thuộc tính null, `saveAndFlush` đưa thay đổi qua bước flush, sau đó clear persistence context trước khi đọc lại. Điều này giúp kiểm tra đường đọc/mapping thực tế thay vì chỉ quan sát object mà test vừa tạo và vẫn đang giữ trong context.

Không dùng đoạn clear như một quy tắc cho mọi test hoặc mọi store. Nó có ý nghĩa cụ thể trong kiểm tra JPA này, sau khi dữ liệu đã được flush.

### Một assertion dễ tạo kết quả sai

```kotlin
assertNull(result?.nickname)
```

Nếu `result` là null vì query sai hoặc fixture chưa có, biểu thức vẫn cho null và assertion vẫn pass. Vì vậy test cần khẳng định entity tồn tại trước:

```kotlin
val customer = assertNotNull(result)
assertNull(customer.nickname)
```

Đây là khác biệt giữa kiểm tra “không có entity” và kiểm tra “entity có thuộc tính thiếu”.

## 10. Kiểm thử null input từ ranh giới Java

Kotlin không cho truyền trực tiếp null vào một tham số `String` không null trong lời gọi thông thường. Nhưng repository có thể được gọi từ Java hoặc một ranh giới không được compiler Kotlin kiểm soát.

Không viết một test Kotlin như sau để chứng minh repository từ chối null:

```kotlin
// Lỗi có thể xảy ra ngay tại phép cast, trước khi repository được gọi.
val invalid = null as String
```

Một test như vậy không kiểm tra hạ tầng repository. Tương tự, `null!!` chỉ chứng minh một biểu thức Kotlin ném lỗi trước lời gọi.

Có thể kiểm tra qua một caller Java trong cùng test context. Ví dụ đoạn test Java minh họa, giả định biến `repository` là bean thật và đã bật đầy đủ hỗ trợ nullability Kotlin:

```java
assertThrows(IllegalArgumentException.class, () ->
    repository.findNullableByTenantIdAndEmail("tenant-a", null)
);
```

Mục tiêu là lời gọi thật đi qua repository proxy. Nếu test dùng reflection, exception có thể bị bọc; cần kiểm tra đúng nguyên nhân gốc thay vì nhầm wrapper của reflection với hợp đồng repository.

Không chỉ kiểm tra tên exception: cũng cần đảm bảo không có một bước gọi hoặc cast khác ném lỗi trước khi repository được chạm tới.

## 11. Tách kiểm thử contract, mapping và nghiệp vụ

Ba nhóm kiểm tra trả lời những câu hỏi khác nhau:

| Nhóm | Ví dụ | Bằng chứng mang lại |
| --- | --- | --- |
| Contract repository | Không có entity thì nullable return là null, required return báo lỗi | Hạ tầng repository áp dụng đúng hợp đồng kết quả |
| Mapping/store | Đọc lại một nickname null sau flush/clear | Dữ liệu lưu và object được materialize đúng theo mapping |
| Nghiệp vụ service | Không có khách hàng được chuyển thành lỗi nghiệp vụ cụ thể | Chính sách ứng dụng đúng |

Một mock trả null hữu ích để thử nhánh service, nhưng không chứng minh Spring Data sẽ trả null hay ném exception trong một query thật. Ngược lại, một test repository không tự chứng minh controller chuyển lỗi thành phản hồi đúng theo yêu cầu sản phẩm.

Với các điều kiện thuộc phạm vi tenant, nên có fixture cùng email ở tenant khác để đảm bảo thiếu dữ liệu trong tenant đang xét không bị thay bằng một entity ngoài phạm vi.

Khi dự án có Query by Example, projection hoặc fragment, cần kiểm tra đúng đường truy vấn được dùng. Ví dụ quy tắc bỏ qua null trong một cấu hình ExampleMatcher không tự áp dụng sang derived query equality.

## 12. Coroutine và reactive: rỗng cần được quan sát bằng đúng cách

### 12.1. Coroutine repository

Nếu module hỗ trợ coroutine repository, một hình dạng có thể là:

```kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CoroutineCustomerRepository : CoroutineCrudRepository<Customer, Long> {

    suspend fun findByTenantIdAndEmail(
        tenantId: String,
        email: String
    ): Customer?

    fun findAllByTenantId(tenantId: String): Flow<Customer>
}
```

Đây là repository cho một module có hỗ trợ tương ứng, không phải cách biến JPA đồng bộ thành non-blocking bằng việc thêm `suspend` hoặc `Flow`.

Một hàm suspend trả nullable cần được gọi trong môi trường coroutine kiểm thử phù hợp và assert giá trị thực tế. Một `Flow` không có phần tử cần được collect để xác nhận không có phần tử và hoàn tất theo hợp đồng; chỉ tạo object Flow chưa chứng minh truy vấn đã chạy.

### 12.2. Reactor từ Kotlin

Nếu dùng một module Reactor, cần phân biệt:

```text
Mono<Customer> hoàn tất không có phần tử
Mono<Boolean> phát false
Mono<Long> phát 0
Mono<Void> hoàn tất
```

Chúng không cùng nghĩa. Một publisher không null vẫn có thể rỗng; annotation hoặc kiểu Kotlin của chính publisher không ép nó phải phát entity.

Kiểm thử cần subscribe và quan sát giá trị/tín hiệu, chẳng hạn bằng công cụ kiểm thử Reactor phù hợp. Không dùng một `try/catch` chỉ bao quanh dòng tạo publisher rồi kết luận mọi lỗi đã được kiểm tra.

### 12.3. Không đánh đồng hai hệ vòng đời

Nullable return của repository đồng bộ, kết quả từ hàm suspend và tín hiệu rỗng của publisher đều có thể biểu đạt thiếu entity, nhưng cách kích hoạt và kiểm chứng khác nhau.

Cũng không dùng việc thêm `!!`, `block()` hoặc một subscription tách rời như cách sửa chung cho mọi loại dữ liệu thiếu. Cần giữ đúng hợp đồng của stack đang sử dụng và ranh giới thực thi của ứng dụng.

## 13. Dữ liệu rỗng không phải lỗi hạ tầng hoặc lỗi truy vấn

Một chính sách như sau dễ che lỗi:

```kotlin
fun findCustomer(tenantId: String, email: String): Customer? =
    try {
        repository.findNullableByTenantIdAndEmail(tenantId, email)
    } catch (exception: Exception) {
        null
    }
```

Mất kết nối, sai query, lỗi chuyển đổi và vi phạm mapping đều có thể bị đổi thành null. Caller tưởng không có khách hàng, trong khi hệ thống chưa thực hiện thành công phép tìm kiếm.

Nên xử lý trường hợp thiếu entity qua hợp đồng nullable/optional đã chọn. Chỉ chuyển đổi những lỗi mà nghiệp vụ có chính sách rõ ràng, giữ được sự khác biệt giữa “không có dữ liệu” và “không đọc được dữ liệu”.

Tương tự, không thay mọi lỗi collection bằng `emptyList()` hoặc mọi lỗi flow bằng một nguồn rỗng để làm test pass. Một test mất kết nối phải kiểm chứng đường lỗi mà ứng dụng thực sự muốn duy trì.

## 14. Những lỗi thường gặp khi kiểm thử Kotlin nullability

| Biểu hiện | Nguyên nhân có thể có | Hướng điều chỉnh |
| --- | --- | --- |
| Test nickname null pass dù fixture không được tìm thấy | Dùng `result?.nickname` trong assertion duy nhất | Assert entity tồn tại trước |
| Test “repository từ chối null” chưa gọi repository | Dùng `null as String` hoặc `!!` trước lời gọi | Kiểm tra qua caller Java hoặc ranh giới thật phù hợp |
| Source Kotlin hợp lệ nhưng runtime contract khác dự kiến | Thiếu hỗ trợ introspection, proxy hoặc cấu hình đúng | Kiểm tra dependency, metadata và đường gọi |
| Không tìm thấy nhưng expected exception không xuất hiện | Chữ ký nullable hoặc đang gọi một API wrapper khác | Đọc đúng kiểu trả về và implementation/query source |
| Null parameter trả khách hàng chưa có nickname | JPA equality đã dùng điều kiện IS NULL | Không coi nullable là bỏ qua predicate |
| Mapping lỗi nhưng service trả null | Bắt toàn bộ exception thành dữ liệu thiếu | Giữ đường lỗi và tách kiểm tra mapping |
| Test chỉ nhìn object vừa lưu | Persistence context vẫn giữ state ban đầu | Khi cần kiểm chứng round-trip, flush rồi đọc lại phù hợp |
| Reactive test không quan sát kết quả | Chưa subscribe hoặc collect | Tiêu thụ bằng hạ tầng kiểm thử của stack |
| Entity mới có id null bị coi là hỏng | Nhầm giai đoạn trước và sau khi store cấp id | Mô tả rõ vòng đời và kiểm tra sau bước lưu thích hợp |

## 15. Bài tập phân tích

### Bài 1: Hai dạng null khác nhau

Một test viết:

```kotlin
val result = repository.findNullableByTenantIdAndEmail(tenantId, email)
assertNull(result?.nickname)
```

Yêu cầu thật sự là chứng minh khách hàng tồn tại nhưng chưa có nickname.

**Phân tích:** assertion hiện tại pass ngay cả khi không có khách hàng. Cần dùng `assertNotNull(result)` rồi mới assert thuộc tính, đồng thời xác nhận định danh hoặc email của entity để bảo đảm đúng fixture.

### Bài 2: Thay kiểu trả về

Một method đổi từ `Customer?` thành `Customer`, nhưng caller vẫn dùng điều kiện `if (result == null)` để xử lý thiếu entity.

**Phân tích:** hợp đồng mới không còn dùng null để biểu đạt thiếu dữ liệu. Với repository được cấu hình kiểm tra đúng, lỗi có thể xảy ra trước khi caller nhận được result. Cần quyết định rõ muốn nullable return hay required return, rồi sửa test và chính sách service tương ứng.

### Bài 3: Null nickname có phải lấy mọi khách hàng?

Một derived query JPA nhận `nickname: String?`; người viết truyền null để yêu cầu không lọc nickname.

**Phân tích:** trong ví dụ equality, null có thể trở thành `IS NULL`. Cần một phương thức không lọc nickname hoặc một cơ chế dựng predicate tùy chọn thể hiện đúng ý định. Test phải có cả khách hàng có và không có nickname để phát hiện nhầm lẫn.

### Bài 4: Test constructor không chứng minh mapping

Một test tạo `CustomerSummary()` có default display name rồi kết luận dữ liệu thiếu ở store sẽ luôn được thay bằng default đó.

**Phân tích:** test mới chứng minh cách gọi constructor trực tiếp. Cần kiểm tra mapping thực tế với trường bị thiếu hoặc null theo store, projection và quy tắc constructor của module đang dùng.

### Bài 5: Mock và integration test kiểm tra gì?

Service test cấu hình mock trả null và xác nhận phát `CustomerNotFoundException`.

**Phân tích:** đây là bằng chứng tốt cho chính sách service ở nhánh đó, nhưng chưa chứng minh query nullable hoặc metadata Kotlin được xử lý đúng bởi Spring Data. Cần một kiểm tra repository thật nếu ứng dụng phụ thuộc vào hợp đồng runtime đó.

## 16. Các điểm cần nhớ

- Kotlin nullable type giúp công bố thiếu giá trị, nhưng compiler, repository proxy và mapping/store có những trách nhiệm khác nhau.
- Không có entity, field null, collection rỗng, publisher rỗng và lỗi truy vấn là những trường hợp riêng cần fixture và assertion riêng.
- Khi tương tác Java, cần đọc metadata nullability, wrapper như Optional và cấu hình theo đúng hệ phiên bản; platform type không phải một bảo đảm không null.
- Test null input phải thực sự đi qua ranh giới cần kiểm tra, không được thất bại sớm vì một phép cast hoặc `!!` của chính test.
- Muốn kiểm tra field thiếu, trước hết phải chứng minh entity tồn tại; muốn kiểm tra reactive/coroutine, phải quan sát đường thực thi thực tế.
- Khả năng query, null parameter, projection, auditing và transaction vẫn phụ thuộc module; kiểu Kotlin không tự đồng nhất mọi store.
