# Nullability Kotlin và metadata phản chiếu

Trong Kotlin, `Member` và `Member?` là hai hợp đồng khác nhau. Khác biệt này ảnh hưởng trực tiếp tới repository: không tìm thấy dữ liệu có thể là một kết quả hợp lệ được biểu diễn bằng `null`, hoặc là việc vi phạm cam kết phải trả về một thực thể. Tuy nhiên, khi mã Kotlin được biên dịch sang JVM, không thể khôi phục toàn bộ hợp đồng đó chỉ bằng `Class<?>` mà Java reflection nhìn thấy.

Trong phần **Kotlin và coroutine** của **Spring Data Commons**, bài học này giải thích cách nullability được biểu diễn bằng metadata Kotlin, vai trò của `kotlin-reflect`, và cách thông tin đó tham gia vào hợp đồng repository cùng quá trình mapping. Mục tiêu là sử dụng đúng abstraction chung mà vẫn tôn trọng khả năng của từng module lưu trữ, không đồng nhất kiểu Kotlin với ràng buộc của cơ sở dữ liệu.

## 1. Nullability là hợp đồng về giá trị, không phải trạng thái dữ liệu

Kotlin phân biệt rõ một kiểu chấp nhận `null` với một kiểu không chấp nhận `null`:

```kotlin
val requiredName: String = "Linh"
val optionalName: String? = null
```

Trong mã Kotlin được kiểm tra kiểu đầy đủ:

- Không thể gán `null` trực tiếp cho `String`.
- Có thể gán `null` cho `String?`.
- Truy cập thành viên của giá trị nullable cần xử lý nhánh vắng mặt.

Ví dụ:

```kotlin
fun displayName(nickname: String?): String =
    nickname?.takeIf { it.isNotBlank() } ?: "Chưa đặt tên"
```

Nhưng những điều này không tự chứng minh rằng:

- Cột trong cơ sở dữ liệu đã có `NOT NULL`.
- Dữ liệu cũ không chứa giá trị rỗng.
- Một truy vấn luôn tìm thấy bản ghi.
- Java caller không bao giờ truyền vào `null`.
- Một mapper hoặc projection luôn cung cấp đúng field.

Kiểu Kotlin mô tả hợp đồng của chương trình. Schema, truy vấn và mapping phải đáp ứng hợp đồng đó bằng các cơ chế riêng.

## 2. JVM nhìn thấy gì sau khi Kotlin biên dịch?

### 2.1. Kiểu tham chiếu đơn thuần không mang đủ thông tin

Hai phương thức Kotlin có thể trả về cùng một class JVM dù nullability khác nhau:

```kotlin
fun requiredEmail(): String = "linh@example.test"

fun optionalEmail(): String? = null
```

Ở mức Java reflection thông thường, `getReturnType()` của cả hai đều nhận diện `java.lang.String`. Chỉ kiểm tra class trả về không cho biết phương thức thứ hai cho phép `null`.

Đối với một số kiểu giá trị, boxing có thể tạo khác biệt, chẳng hạn `Long` không nullable và `Long?` có thể dùng biểu diễn JVM khác nhau. Tuy vậy, suy luận nullability từ primitive hay wrapper không đủ để thay thế metadata ngôn ngữ cho mọi kiểu, generic, constructor và phương thức.

### 2.2. Metadata Kotlin lưu thông tin ngôn ngữ

Kotlin compiler ghi metadata vào class thông qua annotation `kotlin.Metadata`. Metadata mô tả các khái niệm Kotlin mà chữ ký JVM không biểu diễn đầy đủ, trong đó có thông tin cần thiết để hiểu nullability và chữ ký logic của khai báo Kotlin.

Compiler cũng có thể phát các annotation nullability cho công cụ và khả năng tương tác Java. Không nên giả định rằng mọi annotation đó đều có thể được đọc bằng `getAnnotations()` lúc chạy: mục tiêu annotation và chính sách lưu giữ của từng loại có thể khác nhau.

Điểm cần nhớ là:

```text
Class JVM
    cho biết kiểu thực thi ở JVM

Metadata Kotlin
    giúp khôi phục hợp đồng và cấu trúc ngôn ngữ Kotlin

Kotlin reflection
    cung cấp API để đọc các thông tin đó ở mức Kotlin
```

`@Metadata` không phải annotation persistence. Nó không xác định tên bảng, tên collection hay cột khóa chính.

### 2.3. Vai trò của kotlin-reflect

Spring Data sử dụng hỗ trợ Kotlin để hiểu các đặc điểm của khai báo Kotlin, bao gồm ràng buộc nullability trong repository. `kotlin-reflect` cần có trong classpath phù hợp để hỗ trợ đầy đủ việc đọc metadata phản chiếu mà các tính năng Kotlin tương ứng yêu cầu.

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| Kotlin compiler | Kiểm tra kiểu lúc biên dịch và tạo bytecode/metadata |
| `kotlin-stdlib` | Thư viện runtime cơ bản của Kotlin |
| `kotlin-reflect` | API và hỗ trợ phản chiếu ở mức khai báo Kotlin |
| Spring Data Commons | Hợp đồng repository và hạ tầng nhận diện metadata dùng chung |
| Module Spring Data | Query execution, mapping và hành vi lưu trữ cụ thể |

Chỉ có `kotlin-stdlib` không đồng nghĩa mọi tính năng reflection đã sẵn sàng. Khi đóng gói ứng dụng, cần giữ dependency và metadata phù hợp, không chỉ bảo đảm mã nguồn Kotlin biên dịch thành công.

Các thư viện Kotlin và Spring phải nằm trong bộ phiên bản tương thích của ứng dụng. Không nên giải quyết lỗi reflection bằng cách thêm một phiên bản `kotlin-reflect` ngẫu nhiên khác xa bộ Kotlin đang dùng.

## 3. Nullability thay đổi hợp đồng repository như thế nào?

Xét repository truy vấn đơn giá trị:

```kotlin
import org.springframework.data.repository.Repository

interface MemberRepository : Repository<Member, Long> {

    fun findByEmail(email: String): Member

    fun findByNickname(nickname: String): Member?

    fun findAllByActive(active: Boolean): List<Member>
}
```

`Member` là domain type được mapping theo module thực tế. Những phương thức trên giả định module hỗ trợ derived query tương ứng. Với truy vấn đơn giá trị, mô hình dữ liệu và ràng buộc duy nhất cũng phải phù hợp nếu nghiệp vụ mong đợi tối đa một kết quả.

Khi hạ tầng repository có hỗ trợ kiểm tra nullability Kotlin và được cấu hình đầy đủ, cách đọc hợp đồng là:

| Khai báo | Không tìm thấy bản ghi | Ý nghĩa |
|---|---|---|
| `findByEmail(...): Member` | Vi phạm cam kết có kết quả; query method thông thường có thể phát `EmptyResultDataAccessException` | Bên gọi không nhận `null` như kết quả bình thường |
| `findByNickname(...): Member?` | Trả `null` | Vắng mặt là một kết quả được hợp đồng cho phép |
| `findAllByActive(...): List<Member>` | Trả danh sách rỗng | Không cần một List nullable chỉ để biểu diễn không có phần tử |

Một kết quả có nhiều bản ghi cho phương thức đơn giá trị là vấn đề khác. Đổi `Member` thành `Member?` không làm truy vấn cho phép nhiều kết quả; nullability mô tả khả năng vắng mặt, không thay đổi cardinality thành một collection.

### 3.1. Nullable return không làm tham số trở thành nullable

Trong phương thức:

```kotlin
fun findByNickname(nickname: String): Member?
```

Kết quả cho phép `null`, nhưng tham số `nickname` vẫn không cho phép `null`. Kotlin caller không thể truyền `null` trực tiếp. Nếu một lời gọi qua Java hoặc reflection vi phạm hợp đồng, hạ tầng kiểm tra nullability của repository có thể từ chối với `IllegalArgumentException` thay vì coi đó là một bộ lọc hợp lệ.

Nếu muốn tham số chấp nhận `null`, phải khai báo điều đó riêng:

```kotlin
fun findByNickname(nickname: String?): Member?
```

Sau đó vẫn phải xác định ý nghĩa của tham số `null` theo query và module. Nó có thể được diễn giải thành một điều kiện tìm field có giá trị null trong một số kiểu truy vấn; không mặc định rằng `null` nghĩa là bỏ qua điều kiện tìm kiếm.

### 3.2. Bắt buộc có kết quả cần xuất phát từ nghiệp vụ

Không nên khai báo return non-null chỉ vì muốn tránh viết một nhánh kiểm tra. Nếu không tìm thấy là tình huống bình thường, chẳng hạn tìm tài khoản theo mã tùy chọn, `Member?` thường phản ánh hợp đồng rõ hơn.

Ngược lại, khi một service có quy tắc bắt buộc tồn tại, có thể xử lý tường minh:

```kotlin
fun requireMemberByNickname(nickname: String): Member =
    repository.findByNickname(nickname)
        ?: throw MemberNotFoundException(nickname)
```

Ví dụ giả định ứng dụng có `MemberNotFoundException` và biến `repository` phù hợp. Exception này thể hiện ý nghĩa nghiệp vụ, thay vì để một toán tử `!!` tạo lỗi null không có ngữ cảnh.

## 4. Đọc metadata bằng Kotlin reflection

Kotlin reflection cho phép xem nullability ở mức kiểu Kotlin:

```kotlin
import kotlin.reflect.full.memberFunctions

val requiredQuery = MemberRepository::class.memberFunctions
    .single { it.name == "findByEmail" }

val optionalQuery = MemberRepository::class.memberFunctions
    .single { it.name == "findByNickname" }

println(requiredQuery.returnType.isMarkedNullable) // false
println(optionalQuery.returnType.isMarkedNullable) // true
```

Ví dụ dùng repository không có overload trùng tên. Trong công cụ tổng quát, cần phân biệt phương thức bằng đầy đủ chữ ký, không chỉ tên.

Điều này khác với chỉ kiểm tra class trả về qua Java reflection. `KType` biểu diễn thêm thông tin ngôn ngữ, còn `isMarkedNullable` cho biết kiểu đó có được đánh dấu nullable hay không.

### 4.1. Nullability ở ngoài và ở phần tử là hai tầng

```kotlin
data class ResultShapes(
    val first: List<Member>,
    val second: List<Member?>,
    val third: List<Member>?
)
```

Ba thuộc tính có nghĩa khác nhau:

| Kiểu | Collection có thể null? | Phần tử có thể null? |
|---|---|---|
| `List<Member>` | Không | Không |
| `List<Member?>` | Không | Có |
| `List<Member>?` | Có | Không theo khai báo phần tử |

Có thể quan sát hai tầng metadata:

```kotlin
import kotlin.reflect.full.memberProperties

val property = ResultShapes::class.memberProperties
    .single { it.name == "second" }

println(property.returnType.isMarkedNullable) // false
println(property.returnType.arguments.single().type?.isMarkedNullable) // true
```

Khả năng biểu diễn một kiểu trong Kotlin không đồng nghĩa mọi kiểu trả về đó đều được một query engine hỗ trợ với cùng cách chuyển đổi. Repository trả các entity thông thường nên dùng collection không nullable và để collection rỗng biểu diễn không có kết quả.

### 4.2. isMarkedNullable không phải thuật toán kiểm tra mọi kiểu

Với type parameter chưa có ràng buộc chặt, star projection hoặc kiểu đến từ Java, thông tin có thể cần được giải thích thêm. Ví dụ `T` mặc định có thể có upper bound cho phép null dù nó không được viết trực tiếp thành `T?`.

Một kiểu như `List<*>` cũng không cung cấp một đối số kiểu cụ thể để công cụ tự kết luận nullability của mọi phần tử. Khi đọc `KTypeProjection`, `type` có thể vắng mặt.

Vì vậy, không nên tự viết một bộ kiểm tra persistence chỉ bằng quy tắc “`isMarkedNullable == false` thì mọi trường hợp đều không thể có null”. Các framework phải xử lý cả metadata, generic và hợp đồng của API cụ thể.

Các ví dụ reflection trong bài dùng để quan sát cơ chế. Mã nghiệp vụ thông thường nên sử dụng hạ tầng repository/mapping đã có, thay vì phản chiếu lại toàn bộ chữ ký trên mỗi lần truy vấn.

## 5. Metadata constructor: nullable khác với có giá trị mặc định

Một domain type Kotlin có thể khai báo:

```kotlin
import org.springframework.data.annotation.Id

data class Member(
    @field:Id val id: Long? = null,
    val email: String,
    val nickname: String? = null,
    val active: Boolean = true
)
```

Ở đây có hai chiều độc lập:

- `Long?` hoặc `String?` cho phép giá trị null.
- `= null` hoặc `= true` cung cấp giá trị mặc định khi một đối số được bỏ qua theo cơ chế Kotlin.

Có thể quan sát constructor:

```kotlin
import kotlin.reflect.full.primaryConstructor

val constructor = Member::class.primaryConstructor
    ?: error("Không có primary constructor")

constructor.parameters.forEach { parameter ->
    println(
        "${parameter.name}: " +
            "nullable=${parameter.type.isMarkedNullable}, " +
            "optional=${parameter.isOptional}"
    )
}
```

Kết quả về mặt ý nghĩa:

| Tham số | Nullable | Có đối số mặc định |
|---|---|---|
| `id` | Có | Có |
| `email` | Không | Không |
| `nickname` | Có | Có |
| `active` | Không | Có |

`isOptional` của tham số phản ánh khả năng bỏ qua đối số theo cơ chế gọi hỗ trợ defaulting; nó không có nghĩa thuộc tính nhận `null`, cũng không phải `java.util.Optional`.

## 6. Mapping gặp dữ liệu thiếu hoặc null sẽ ra sao?

### 6.1. Tham số bắt buộc không có default

Nếu kho dữ liệu cung cấp null cho `email: String`, trong khi mapper cần dựng `Member` qua constructor trên, dữ liệu không đáp ứng hợp đồng. Quá trình materialize có thể thất bại với lỗi mapping/khởi tạo thực thể, thay vì tạo một `Member` hợp lệ chứa email null.

Đây là lỗi **nội dung bản ghi hoặc mapping**, khác với trường hợp query không tìm thấy bản ghi nào:

```text
Không tìm thấy hàng:
    xét hợp đồng kết quả của repository.

Tìm thấy hàng nhưng email null:
    xét khả năng dựng domain object hợp lệ.
```

Khai báo return `Member?` không tự sửa được hàng có `email = null`. Dấu `?` cho phép không có đối tượng kết quả, không cho phép mọi thuộc tính bên trong đối tượng vi phạm kiểu của chúng.

### 6.2. Tham số có default

Spring Data có hỗ trợ constructor defaulting của Kotlin trong các đường mapping tương ứng. Khi phát hiện tham số có giá trị mặc định, hạ tầng có thể để đối số vắng mặt nếu nguồn không cung cấp giá trị hoặc trả null, để Kotlin áp dụng mặc định.

Ví dụ:

```kotlin
data class LegacyProfile(
    val displayName: String = "Chưa đặt tên"
)
```

Trong một đường mapping hỗ trợ cơ chế đó, dữ liệu thiếu `displayName` hoặc trả null có thể dẫn tới giá trị mặc định, thay vì một lỗi null. Điều này không có nghĩa mã Kotlin có thể gọi trực tiếp `LegacyProfile(null)`; lời gọi đó vẫn không hợp lệ theo kiểu nguồn.

Cần xác định hành vi của module và mapper thực tế, đặc biệt khi nghiệp vụ phân biệt:

- Field không tồn tại.
- Field có tồn tại nhưng mang giá trị null.
- Field có chuỗi rỗng.
- Field có giá trị mặc định do ứng dụng tạo.

Không dùng default như một cách vô tình che dữ liệu hỏng. Nếu email bắt buộc phải tồn tại, mặc định `email = ""` có thể chỉ chuyển lỗi mapping thành lỗi nghiệp vụ khó phát hiện hơn.

### 6.3. Không phải module nào cũng dựng entity cùng cách

Mapper dùng constructor, JPA provider, converter tùy biến và một driver đọc tài liệu có thể có những yêu cầu khác nhau. Không lấy khả năng Kotlin object mapping của Commons làm cam kết rằng mọi module bỏ qua được quy tắc constructor hoặc yêu cầu đặc thù của nó.

Khi chọn mô hình immutable/data class, cần đối chiếu module thực tế về constructor được chọn, cập nhật thuộc tính, ID sinh tự động và cách trả instance sau lưu.

## 7. Annotation persistence và use-site target của Kotlin

Kotlin có các khái niệm property, field, getter và constructor parameter. Một annotation nhìn như được đặt “trên thuộc tính” trong mã nguồn có thể nằm ở một vị trí cụ thể sau biên dịch.

Ví dụ:

```kotlin
@field:Id
val id: Long? = null
```

`@field:` biểu đạt rõ annotation áp dụng lên backing field. Với API khác, có thể cần `@get:` hoặc `@param:` theo mục tiêu mà annotation và framework hỗ trợ.

Không có một use-site target đúng cho mọi annotation:

- Mapping theo field cần nhận diện annotation ở field.
- Mapping theo accessor có thể quan tâm getter.
- Validation trên constructor parameter có thể khác validation trên field.
- Kotlin reflection đọc annotation của property không nhất thiết thấy annotation chỉ được đặt ở Java field.

Vì vậy, khi một annotation không được nhận diện, phải xác định cả mục tiêu đặt annotation và cách framework đọc nó. Metadata nullability không tự sửa annotation ID đặt sai vị trí.

Tương tự, `@NotNull` hoặc `@NotBlank` của Bean Validation có trách nhiệm khác với kiểu Kotlin. Chúng không tự được thực thi ở mọi thao tác repository nếu ứng dụng chưa có cơ chế validation phù hợp. Ràng buộc schema cũng phải được thiết kế riêng.

## 8. Java interop và platform type

Kotlin có thể tiếp nhận một giá trị từ Java mà thông tin nullability chưa được diễn đạt đầy đủ. IDE thường hiển thị platform type bằng dạng như `String!`; đây là cách mô tả của công cụ, không phải kiểu bạn viết trực tiếp trong mã Kotlin.

Ví dụ một API Java không có hợp đồng nullability rõ:

```java
public interface LegacyDirectory {
    String findEmail(String externalId);
}
```

Bên Kotlin cần quyết định cách xử lý giá trị mà API thực tế có thể trả:

```kotlin
val email: String? = legacyDirectory.findEmail(externalId)

val requiredEmail = email
    ?: throw IllegalStateException("Directory không cung cấp email")
```

Nếu API Java có annotation nullability mà compiler/hạ tầng hiểu, Kotlin có thể nhận được hợp đồng chặt hơn. Tuy nhiên, việc này không thay thế yêu cầu API Java phải thực hiện đúng hợp đồng lúc chạy.

Các nguồn dữ liệu qua reflection, Java, serializer hoặc converter có thể đi vào chương trình ngoài phạm vi kiểm tra tĩnh thuần Kotlin. Vì vậy, “đã dùng Kotlin nên không thể có lỗi null” là nhận định quá rộng.

Không dùng `!!` như cách mặc định để xử lý những ranh giới này. Hãy xác định null là kết quả hợp lệ, lỗi tích hợp hay dữ liệu không hợp lệ, rồi chuyển thành hành vi có ý nghĩa.

## 9. Optional của Java không tự biến thành nullable của Kotlin

Một repository kế thừa API Java có thể vẫn sử dụng wrapper của Java. Chẳng hạn `CrudRepository.findById` có hợp đồng trả `Optional<T>`; Kotlin không tự đổi mọi lời gọi đó thành `T?` chỉ vì caller viết bằng Kotlin.

Có thể dùng extension Kotlin của Spring Data cho trường hợp phù hợp:

```kotlin
import org.springframework.data.repository.CrudRepository
import org.springframework.data.repository.findByIdOrNull

interface MemberCrudRepository : CrudRepository<Member, Long>

fun findMember(repository: MemberCrudRepository, id: Long): Member? =
    repository.findByIdOrNull(id)
```

Extension này giúp biểu diễn vắng mặt theo cách quen thuộc của Kotlin ở API tương ứng. Nó không thay đổi truy vấn thành một loại repository khác và không sửa dữ liệu có null bên trong một entity.

Đối với query method Kotlin tự khai báo, nên chọn một quy ước vắng mặt rõ. Tránh tạo nhiều tầng như `Optional<Member>?` nếu nghiệp vụ không có lý do thực sự để phân biệt từng tầng đó.

## 10. Coroutine: chữ ký logic khác chữ ký JVM

### 10.1. suspend không làm nullability biến mất

Một coroutine repository có thể khai báo:

```kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CoroutineMemberRepository
    : CoroutineCrudRepository<Member, Long> {

    suspend fun findByEmail(email: String): Member?

    fun findAllByActive(active: Boolean): Flow<Member>
}
```

Module phải hỗ trợ coroutine repository và hạ tầng truy cập dữ liệu tương ứng. Chỉ thêm `suspend` không tự tạo implementation và không biến JDBC/JPA thành I/O không chặn.

Hợp đồng vẫn có các tầng rõ ràng:

- `suspend fun ...: Member?` cho phép lời gọi hoàn tất với null.
- `Flow<Member>` không có phần tử là một flow rỗng, không phải null.
- `Flow<Member?>` cho phép phần tử null về mặt kiểu Kotlin; điều đó khác flow rỗng và còn phụ thuộc khả năng trả về của API repository.

Với phương thức suspend non-null, ứng dụng phải có hành vi phù hợp khi nguồn không có kết quả, thay vì kỳ vọng compiler tự sinh ra một thực thể. Khi quy ước cần rõ ở mức service, có thể nhận nullable từ repository rồi chuyển thành exception nghiệp vụ bằng Elvis operator.

### 10.2. Java reflection không nhìn thấy chữ ký nguồn nguyên vẹn

Một hàm suspend được compiler biến đổi thành dạng JVM có tham số continuation và kiểu trả về phục vụ giao thức coroutine. Nhìn `Method.getReturnType()` đơn thuần có thể thấy `Object`, không phải kiểu domain mà lập trình viên khai báo trong Kotlin.

Mô tả rút gọn về ý tưởng:

```text
Kotlin source:
    suspend fun findByEmail(email: String): Member?

JVM representation:
    phương thức có thêm Continuation và kiểu trả về theo cơ chế coroutine
```

Metadata Kotlin cùng hạ tầng hiểu coroutine giúp framework nhận diện chữ ký logic. Vì vậy, một công cụ tự viết dựa hoàn toàn trên kiểu trả về Java có thể diễn giải sai cả cardinality lẫn nullability của phương thức suspend.

### 10.3. Nullable bên trong không đồng nghĩa publisher có thể phát null

Nếu có cầu nối tới Reactor hoặc Reactive Streams, cần tôn trọng hợp đồng của nó. Một `Mono<Member>` có thể hoàn tất rỗng nhưng không phát `null` như một phần tử hợp lệ. Khi chuyển sang lời gọi suspend nullable, sự hoàn tất rỗng có thể được biểu diễn bằng null qua cơ chế chuyển đổi thích hợp.

Điều đó khác với `Flow`, nơi hệ kiểu Kotlin có thể cho phép phần tử null nếu khai báo `Flow<Member?>`. Không suy luận trực tiếp rằng mọi wrapper và bridge đều biểu diễn vắng mặt giống nhau.

## 11. Nullability trong projection và DTO

Một projection Kotlin có thể mô tả field tùy chọn:

```kotlin
interface MemberSummary {
    val email: String
    val nickname: String?
}
```

Nếu truy vấn thực tế có thể trả null cho `nickname`, khai báo nullable phản ánh điều đó. Nếu `email` là kết quả của một outer join hoặc biểu thức có thể null, khai báo non-null cần được xem lại hoặc truy vấn phải bảo đảm giá trị hợp lệ.

Metadata không tự biến một outer join thành inner join và không tự thêm giá trị mặc định cho mọi projection. Alias, constructor DTO và kiểu giá trị do driver trả phải khớp cơ chế projection của module.

Các tình huống dễ nhầm:

| Tình huống | Cách hiểu đúng |
|---|---|
| Query không có hàng kết quả | Xét cardinality và nullability ở kết quả repository |
| Có hàng nhưng một cột null | Xét nullability của thuộc tính/constructor/projection |
| Projection không chọn một field | Không mặc định field đó luôn có giá trị khi dựng entity đầy đủ |
| Join làm field phía liên kết vắng mặt | Hợp đồng DTO/projection phải phản ánh khả năng đó |
| Chuỗi rỗng thay cho null | Không còn là vấn đề nullability đơn thuần; cần validation nghiệp vụ |

Projection chỉ phục vụ đọc cũng không nên được coi là aggregate đầy đủ để cập nhật. Nếu nó không chứa version hoặc metadata tạo, dựng entity cập nhật từ projection có thể làm mất thông tin persistence dù các thuộc tính còn lại không nullable.

## 12. ID nullable không đồng nghĩa thực thể luôn không hợp lệ

Trong ví dụ `Member`, `id: Long? = null` có thể biểu diễn giai đoạn trước khi kho dữ liệu cấp ID. Sau lưu, bên gọi nên dùng thực thể kết quả:

```kotlin
val draft = Member(email = "linh@example.test")
val saved = repository.save(draft)
val savedId = requireNotNull(saved.id) {
    "Thực thể lưu thành công nhưng không có ID theo hợp đồng mong đợi"
}
```

Đoạn mã giả định `repository` là `MemberCrudRepository` imperative và module dùng chiến lược sinh ID tương ứng. Nó không phải ví dụ gọi coroutine repository ngoài coroutine.

`id` nullable là lựa chọn mô hình cho một vòng đời cụ thể, không phải lý do làm mọi thuộc tính nghiệp vụ nullable. Nếu dùng ID do ứng dụng cấp, có thể có thiết kế khác phù hợp hơn.

Tương tự, version nullable có thể mang ý nghĩa trạng thái chưa lưu theo chiến lược module. Không tùy tiện đổi version sang non-null với mặc định `0` chỉ để loại dấu `?`; thay đổi đó có thể ảnh hưởng nhận biết thực thể mới và optimistic locking.

Nullability vì vậy cần được đặt theo ý nghĩa từng thuộc tính, không phải theo mục tiêu làm mã nhìn đồng nhất.

## 13. Khi metadata không được nhận diện

Những vấn đề runtime có thể xuất hiện dù source code đúng:

| Hiện tượng | Nguyên nhân cần xem xét | Hướng xử lý |
|---|---|---|
| Framework không hiểu đầy đủ chữ ký Kotlin | Thiếu hỗ trợ reflection hoặc dependency không tương thích | Kiểm tra bộ Kotlin runtime/reflection và phiên bản framework |
| Kết quả kiểm tra chỉ có class JVM | Công cụ chỉ dùng Java reflection cơ bản | Dùng hạ tầng nhận diện Kotlin thay vì suy luận từ class |
| Chạy development được nhưng bản đóng gói lỗi | Dependency hoặc metadata bị loại bỏ khi packaging/shrinking | Kiểm tra artifact triển khai giữ thông tin cần thiết |
| Không nhận ra field ID | Annotation ở sai use-site target so với mapping | Đối chiếu field/getter/parameter mà module đọc |
| Entity non-null vẫn lỗi khi đọc | Hàng có null, thiếu field hoặc converter sai | Kiểm tra dữ liệu và constructor được chọn |
| Null được thay bằng default ngoài dự kiến | Đường mapping áp dụng Kotlin defaulting | Quy định rõ chính sách missing/null/default |
| Hàm suspend bị coi là trả Object | Công cụ chỉ đọc chữ ký JVM đã biến đổi | Dùng hỗ trợ metadata/coroutine tương ứng |

Thêm `kotlin-reflect` không tái tạo được metadata đã bị công cụ đóng gói loại bỏ. Ngược lại, giữ metadata mà thiếu hạ tầng đọc phù hợp cũng chưa chắc đáp ứng toàn bộ tính năng cần dùng.

Khi phân tích, hãy tách ba câu hỏi: metadata có còn không, hạ tầng có đọc được không, và dữ liệu thực tế có thỏa hợp đồng không. Chúng là ba nguyên nhân khác nhau, không nên chữa tất cả bằng cách đổi mọi kiểu thành nullable.

## 14. Bài tập tự kiểm tra

### Tình huống 1: Query đơn giá trị không tìm thấy thành viên

Một query method Kotlin trả `Member`, hạ tầng kiểm tra nullability của repository hoạt động đầy đủ, nhưng truy vấn không tìm thấy bản ghi.

**Phân tích:** kết quả vắng mặt không thỏa return non-null. Với query method đơn giá trị thông thường, cần dự kiến lỗi như `EmptyResultDataAccessException`, không phải một `Member` có field rỗng. Nếu vắng mặt là bình thường, hợp đồng `Member?` nên được cân nhắc.

### Tình huống 2: Return nullable nhưng cột email null

Repository trả `Member?`. Query tìm thấy một hàng có `email = null`, trong khi constructor yêu cầu `email: String` và không có default.

**Phân tích:** dấu `?` ở kết quả không cho phép thuộc tính bên trong vi phạm constructor. Mapping vẫn có thể thất bại. Cần sửa dữ liệu, mapping hoặc mô hình theo đúng nghiệp vụ.

### Tình huống 3: Constructor có default cho tên hiển thị

Mapper hỗ trợ Kotlin defaulting đọc một record thiếu tên hiển thị, trong khi constructor có `displayName: String = "Chưa đặt tên"`.

**Phân tích:** mapper có thể để đối số vắng mặt để Kotlin dùng mặc định. Cần xác nhận ứng dụng có muốn cách xử lý đó cho cả missing/null ở đường mapping đang dùng hay không.

### Tình huống 4: Công cụ reflection thấy Object cho hàm suspend

Một công cụ kiểm tra repository dùng `Method.getReturnType()` và kết luận hàm suspend không có kiểu domain.

**Phân tích:** công cụ đang nhìn chữ ký JVM phục vụ coroutine. Cần đọc chữ ký Kotlin logic bằng hạ tầng hiểu metadata và coroutine, không sửa repository chỉ để làm Java reflection cơ bản thấy kiểu mong muốn.

### Tình huống 5: Danh sách rỗng bị đổi thành null

Một query nhiều kết quả trả `List<Member>`, nhưng tầng adapter tự đổi List rỗng thành null để biểu diễn “không có dữ liệu”.

**Phân tích:** adapter làm sai hợp đồng collection. Không có phần tử đã được biểu diễn bằng List rỗng; không cần thêm một tầng nullability cho cùng một ý nghĩa.

Kotlin nullability giúp hợp đồng repository và domain rõ hơn khi thông tin ngôn ngữ được giữ và được framework đọc đúng. Metadata phản chiếu nối mã nguồn Kotlin với cách Spring Data thực thi ở JVM; schema, mapping và dữ liệu thực tế vẫn phải được thiết kế để đáp ứng hợp đồng đó.