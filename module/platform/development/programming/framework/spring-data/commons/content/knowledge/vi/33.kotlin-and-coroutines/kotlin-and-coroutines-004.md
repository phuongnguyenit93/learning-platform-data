# Extension function và ánh xạ generic có kiểu

## 1. Bài toán: API gọn nhưng hợp đồng kiểu vẫn rõ

Một ứng dụng Kotlin đọc sản phẩm qua Spring Data rồi trả về `ProductView`. Nhóm phát triển muốn bớt lặp lại việc xử lý `Optional`, truyền `Class<T>` và viết các vòng lặp chuyển entity sang DTO. Đồng thời, kết quả phải giữ kiểu cụ thể như `Page<ProductView>` hoặc `Flow<ProductView>`, thay vì biến thành `Any` rồi ép kiểu ở cuối.

Bài thuộc chương **Kotlin và coroutine** của module **SPRING_DATA_COMMONS**. Trọng tâm là dùng extension function để diễn đạt tiện ích cho repository và dữ liệu có kiểu, kết hợp với các abstraction như CRUD, projection và phân trang. Những API riêng của store sẽ được ghi rõ trong từng ví dụ.

Có ba việc cần phân biệt ngay từ đầu:

| Việc cần làm | Ví dụ | Cơ chế chính |
| --- | --- | --- |
| Thêm cách gọi tiện dụng | `repository.findByIdOrNull(id)` | Kotlin extension |
| Chuyển dữ liệu giữa hai kiểu | `Product` sang `ProductView` | Hàm ánh xạ thực sự tạo kết quả |
| Cung cấp kiểu cho một API cần thông tin runtime | `find<Product>(query)` | Extension dùng kiểu reified hoặc type token |

Cú pháp generic gọn không tự thực hiện cả ba việc. Cần đọc phần triển khai hoặc hợp đồng API để biết dữ liệu được tìm, ánh xạ hay chỉ được kiểm tra kiểu.

## 2. Extension function bổ sung cách gọi, không sửa class gốc

Kotlin cho phép khai báo hàm với receiver để gọi bằng cú pháp giống member. Extension không thêm member thật vào class hay interface; việc chọn extension dựa trên kiểu receiver tại thời điểm biên dịch. Nếu có member phù hợp cùng tên và chữ ký, member được ưu tiên. [Kotlin: Extensions](https://kotlinlang.org/docs/extensions.html).

Ví dụ một extension do ứng dụng tự viết:

```kotlin
fun Product.toView(): ProductView = ProductView(
    name = name,
    priceInCents = priceInCents
)
```

`Product` trước dấu chấm là receiver type. Bên trong hàm có thể đọc các property công khai của sản phẩm như khi viết `this.name`.

Với một biến có kiểu `Product`, lời gọi:

```kotlin
val view: ProductView = product.toView()
```

được compiler kiểm tra theo chữ ký `Product -> ProductView`. Đây là một hàm chuyển đổi dữ liệu cụ thể, không phải phép cast.

Trong ứng dụng Spring Data, cũng cần phân biệt extension với query method. Đặt tên một extension là `findSomething` không làm repository proxy tự sinh query cho nó. Extension chỉ chạy phần code đã được viết và có thể gọi tiếp một phương thức repository được hỗ trợ.

Khi cần một tính năng thuộc fragment repository, custom implementation hoặc service có phụ thuộc riêng, hãy thiết kế thành abstraction tương ứng. Không dùng extension như nơi giấu một tập dịch vụ toàn cục hoặc trạng thái dùng chung khó theo dõi.

## 3. Extension có sẵn của Commons: findByIdOrNull

Spring Data cung cấp các tiện ích Kotlin qua extension và cần import chúng để sử dụng. Một số extension dùng reified để làm việc với kiểu trên JVM thuận tiện hơn. [Spring Data Commons: Kotlin Extensions](https://docs.spring.io/spring-data/commons/reference/kotlin/extensions.html).

Với repository đồng bộ, có thể import `findByIdOrNull`:

```kotlin
import org.springframework.data.repository.CrudRepository
import org.springframework.data.repository.findByIdOrNull

interface ProductRepository : CrudRepository<Product, String>

fun findOptionalProduct(
    repository: ProductRepository,
    productId: String
): Product? = repository.findByIdOrNull(productId)
```

Extension này chuyển kết quả `Optional<T>` của `CrudRepository.findById` thành `T?`; không tìm thấy thì trả null. Nó vẫn gọi thao tác repository bên dưới, không thay đổi cơ chế truy cập dữ liệu. [Mã nguồn CrudRepositoryExtensions](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/kotlin/org/springframework/data/repository/CrudRepositoryExtensions.kt).

Trong ví dụ này, `ProductRepository` là biến thể đồng bộ. `findByIdOrNull` không biến việc gọi một repository blocking thành lời gọi coroutine không blocking chỉ vì nó thuận tiện hơn trong Kotlin.

Không dùng `!!` để xóa dấu hỏi khi chưa xác định chính sách không tìm thấy. Kotlin phân biệt kiểu nullable và không nullable; caller cần xử lý trường hợp thiếu giá trị bằng hợp đồng thích hợp. [Kotlin: Null Safety](https://kotlinlang.org/docs/null-safety.html).

## 4. Mô hình dùng chung cho các ví dụ

Các đoạn mã dùng Kotlin/JVM và các phiên bản Spring Data, Kotlin, coroutine tương thích. Các khai báo minh họa có thể đặt trong package `example.kotlinmapping`; import ở đầu tệp chứa đoạn mã tương ứng. Bài không kèm cấu hình build hoặc kết nối database.

Entity dưới đây dùng mapping MongoDB để có một ví dụ store cụ thể:

```kotlin
import org.springframework.data.annotation.Id
import org.springframework.data.mongodb.core.mapping.Document

@Document("products")
data class Product(
    @Id val id: String? = null,
    val name: String,
    val category: String,
    val priceInCents: Long
)

data class ProductView(
    val name: String,
    val priceInCents: Long
)

fun Product.toView(): ProductView = ProductView(
    name = name,
    priceInCents = priceInCents
)
```

`ProductView` chỉ lấy các giá trị cần hiển thị. Nó không phải subclass của `Product`, nên phải tạo object mới khi chuyển đổi.

Các đoạn `toView` trong bài mô tả cùng một khai báo; chỉ cần định nghĩa một lần trong chương trình thực hành. Tương tự, những phiên bản repository đồng bộ, có projection và coroutine ở các phần sau là các biến thể để học, không phải yêu cầu bật đồng thời mọi biến thể trong cùng cấu hình.

Một phép ánh xạ có kiểu diễn đạt được các lựa chọn như đổi tên thuộc tính, tính giá trị hoặc bỏ trường không cần trả về. Những lựa chọn đó thuộc thiết kế dữ liệu của ứng dụng; generic không tự suy ra quy tắc nghiệp vụ chỉ từ tên hai class.

## 5. Generic extension cho kết quả và chính sách không tìm thấy

### 5.1. Giữ kiểu entity và kiểu ID

Có thể gói chính sách bắt buộc tìm thấy entity bằng một extension generic:

```kotlin
import org.springframework.data.repository.CrudRepository
import org.springframework.data.repository.findByIdOrNull

fun <T : Any, ID : Any> CrudRepository<T, ID>.requireById(id: ID): T =
    findByIdOrNull(id)
        ?: throw NoSuchElementException("Không tìm thấy entity với id=$id")
```

Với `ProductRepository : CrudRepository<Product, String>`, compiler biết:

```kotlin
val product: Product = repository.requireById("product-42")
val view: ProductView = product.toView()
```

Kiểu `T` và `ID` được suy ra từ receiver. Không cần một tham số `Class<Product>` vì phần code này không yêu cầu tìm thông tin runtime về `T`; nó chỉ dùng hợp đồng repository đã có.

Các bound `T : Any` và `ID : Any` giữ kiểu tham số không nullable ở ranh giới này. Điều đó không nói rằng mọi property bên trong entity đều khác null: `Product.id` trong ví dụ vẫn là `String?`.

Extension này chọn ném `NoSuchElementException` khi thiếu dữ liệu. Đây là chính sách ứng dụng minh họa; ở một API thực tế, có thể dùng lỗi domain riêng hoặc giữ kết quả tùy chọn. Không dùng cùng một helper để che mọi lỗi kết nối hoặc lỗi mapping thành lỗi không tìm thấy.

### 5.2. Hàm chuyển đổi giữ cả kiểu nguồn và kiểu đích

Khi chỉ cần ánh xạ collection, hàm `map` có sẵn thường đã đủ:

```kotlin
val products: List<Product> = listOf(
    Product("p-1", "Chuột", "tools", 180000),
    Product("p-2", "Bàn phím", "tools", 250000)
)

val views: List<ProductView> = products.map(Product::toView)
```

Nếu dự án cần một tên riêng thể hiện mục đích, có thể xây helper generic:

```kotlin
fun <S : Any, R : Any> Iterable<S>.mapViews(
    transform: (S) -> R
): List<R> = map { source -> transform(source) }
```

Cách gọi:

```kotlin
val views: List<ProductView> = products.mapViews(Product::toView)
```

`S` là kiểu phần tử đầu vào và `R` là kiểu do lambda trả về. Hàm không cần `reified`, vì không dùng `S::class`, `R::class` hoặc phép kiểm tra runtime theo type parameter.

Chỉ tạo wrapper khi nó giúp thống nhất hợp đồng hoặc cách dùng trong dự án. Một tên mới chỉ đổi tên `map` mà không mang thêm ý nghĩa có thể làm code khó tìm hơn API chuẩn.

## 6. Ánh xạ Page mà không đánh rơi metadata phân trang

`Page<T>` có phương thức `map` trả một `Page<U>` với nội dung được chuyển đổi. Đây là hợp đồng dành cho việc ánh xạ phần tử trong trang. [API Page.map](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Page.html).

Một helper có kiểu:

```kotlin
import org.springframework.data.domain.Page

fun <S : Any, R : Any> Page<S>.mapViews(
    transform: (S) -> R
): Page<R> = map { source -> transform(source) }
```

Ví dụ sử dụng một trang đã có từ tầng truy vấn:

```kotlin
val productPage: Page<Product> = loadedPage
val viewPage: Page<ProductView> = productPage.mapViews(Product::toView)
```

Chọn receiver `Page<S>` giúp overload này giữ hình dạng kết quả là `Page<R>`. Khi receiver là collection thông thường, helper ở phần 5 trả `List<R>`. Kiểu receiver quyết định contract được gọi.

Đừng thay việc ánh xạ trang bằng thao tác chỉ lấy content nếu caller vẫn cần metadata:

```kotlin
// Kết quả chỉ còn danh sách, không còn hợp đồng Page.
val contentOnly: List<ProductView> = productPage.content.map(Product::toView)
```

Cũng không lấy số phần tử của một trang rồi tự dùng làm tổng số phần tử của toàn bộ tập kết quả. Ví dụ trang có hai sản phẩm không có nghĩa truy vấn chỉ khớp hai sản phẩm.

Mẫu helper trên không lọc bỏ phần tử và không thay query. Nếu cần vừa lọc vừa trả tổng số đúng, phải thiết kế lại việc lọc ở tầng truy vấn hoặc định nghĩa metadata có ý nghĩa khác; không giữ nguyên tổng số cũ trong khi âm thầm thay điều kiện kết quả.

Quan trọng hơn, mapping `Product -> ProductView` sau khi có page không tự biến thành projection ở database. Entity đã được lấy về có thể chứa nhiều dữ liệu hơn DTO. Muốn tối ưu phần dữ liệu được truy vấn, phải xét khả năng projection của store.

## 7. Reified dùng khi API cần kiểu tại runtime

Với một type parameter thông thường, không thể tùy ý dùng `T::class` trong thân hàm. Kotlin cho phép type parameter `reified` trên hàm inline để dùng kiểu cụ thể tại call site cho một số thao tác như lấy class hoặc kiểm tra kiểu. [Kotlin: Reified Type Parameters](https://kotlinlang.org/docs/inline-functions.html#reified-type-parameters).

Một helper minh họa type token:

```kotlin
inline fun <reified T : Any> javaType(): Class<T> = T::class.java

val productType: Class<Product> = javaType<Product>()
```

Ở đây có nhu cầu thật sự về class runtime, nên `reified` phục vụ một hợp đồng cụ thể. Nó không phải điều kiện bắt buộc để mọi hàm generic đều an toàn kiểu.

### 7.1. Ví dụ extension có sẵn của MongoDB

Spring Data MongoDB có extension `find<T>` sử dụng `T::class.java` để gọi API nhận class. [Mã nguồn MongoOperationsExtensions](https://github.com/spring-projects/spring-data-mongodb/blob/main/spring-data-mongodb/src/main/kotlin/org/springframework/data/mongodb/core/MongoOperationsExtensions.kt).

```kotlin
import org.springframework.data.mongodb.core.MongoOperations
import org.springframework.data.mongodb.core.find
import org.springframework.data.mongodb.core.query.Criteria
import org.springframework.data.mongodb.core.query.Query

fun findToolProducts(operations: MongoOperations): List<Product> {
    val query = Query.query(Criteria.where("category").`is`("tools"))
    return operations.find<Product>(query)
}
```

Kiểu `Product` ở call site giúp chọn kiểu mapping. Việc đọc document và dựng entity vẫn do `MongoOperations` cùng mapping infrastructure thực hiện; extension không thay thế converter hoặc constructor của entity.

Đây là API MongoDB đồng bộ. Việc lời gọi ngắn hơn không làm nó trở thành reactive hoặc coroutine. Với API khác, phải dùng đúng receiver và đúng extension của API đó.

Nếu bỏ import extension, một lời gọi vốn trông như member có thể không còn được resolve như mong muốn. Khi IDE báo không tìm thấy hàm hoặc không khớp overload, hãy kiểm tra import và kiểu receiver trước khi thêm cast.

### 7.2. Property reference là một kiểu tiện ích khác

MongoDB còn có các extension query dùng Kotlin property references, giúp biểu đạt thuộc tính qua mô hình thay vì chỉ gõ tên bằng chuỗi. Khả năng này thuộc module MongoDB, không phải mọi store đều có cùng DSL. [Spring Data MongoDB: Kotlin Extensions](https://docs.spring.io/spring-data/mongodb/reference/kotlin/extensions.html).

Cần phân biệt hỗ trợ kiểu ở cấp ngôn ngữ với việc store hỗ trợ toán tử, kiểu lưu trữ hoặc query tối ưu. Compiler biết property tồn tại vẫn chưa chứng minh database có index hoặc converter thích hợp cho mọi điều kiện.

## 8. Dynamic projection khác ánh xạ DTO sau truy vấn

Dynamic projection cho phép chọn kiểu kết quả khi gọi query method, thường bằng tham số `Class<R>`. Khả năng dựng DTO và tối ưu truy vấn cần đối chiếu module cụ thể. [Spring Data Commons: Dynamic Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.dynamic).

Một biến thể repository dành cho ví dụ projection:

```kotlin
import org.springframework.data.repository.CrudRepository

interface ProjectingProductRepository : CrudRepository<Product, String> {

    fun <R : Any> findByCategory(category: String, type: Class<R>): List<R>
}
```

Có thể viết extension ngắn để chuyển type parameter thành class:

```kotlin
inline fun <reified R : Any> ProjectingProductRepository.findViewsByCategory(
    category: String
): List<R> = findByCategory(category, R::class.java)
```

Cách gọi:

```kotlin
val views: List<ProductView> =
    repository.findViewsByCategory<ProductView>("tools")
```

Extension này không tự tạo query cho tên `findViewsByCategory`. Query method được khai báo thật là `findByCategory(category, type)`; extension chỉ cung cấp tham số kiểu và chuyển tiếp lời gọi.

Đặt cạnh hai đường đi:

```text
Đường A:
query trả Product -> hàm Product.toView() -> ProductView

Đường B:
query được yêu cầu trả kiểu projection -> mapping của store -> ProductView
```

Trong mẫu này, hai đường có thể cùng trả một DTO có các field `name` và `priceInCents`, nhưng không tự có cùng kế hoạch đọc dữ liệu. Khi dùng DTO projection, cần tên thuộc tính và constructor phù hợp với khả năng module.

`<R : Any>` không chứng minh mọi class Kotlin đều có thể làm projection. Lời gọi có kiểu đích hợp lệ về cú pháp vẫn có thể thất bại tại runtime nếu store không dựng được kiểu ấy.

## 9. Giới hạn của generic và type erasure

Trên JVM, kiểm tra generic chủ yếu diễn ra ở compile time; thông tin type argument của một instance generic bị xóa theo quy tắc type erasure. `reified` không biến mọi kiểm tra generic lồng nhau thành kiểm tra đầy đủ phần tử. [Kotlin: Type Erasure](https://kotlinlang.org/docs/generics.html#type-erasure).

Ví dụ cần tránh:

```kotlin
@Suppress("UNCHECKED_CAST")
fun <R> Any.pretendToBe(): R = this as R
```

Đây không phải hàm mapping. Nó không tạo `ProductView`, không kiểm tra quy tắc dữ liệu và không bảo đảm collection bên trong chứa đúng kiểu phần tử.

Với payload như `List<ProductView>`, chỉ lấy raw class `List` chưa diễn đạt đầy đủ kiểu phần tử cho một API mapping. Nếu API cần mô tả kiểu generic lồng nhau, phải dùng loại type descriptor mà API đó hỗ trợ, chẳng hạn một `Type` hoặc `KType` phù hợp, thay vì cố ép một `Class` chứa mọi thông tin.

Không phải API nào cũng nhận các loại descriptor đó. Trước khi viết wrapper reified, hãy kiểm tra receiver thực sự cần `Class<T>`, type descriptor, converter hay hàm biến đổi `(S) -> R`.

Một số giới hạn vẫn còn dù code có generic:

| Điều compiler có thể kiểm tra ở ví dụ | Điều vẫn cần thiết kế hoặc xác minh riêng |
| --- | --- |
| Lambda nhận `Product` và trả `ProductView` | Giá trị được tính có đúng nghiệp vụ không |
| Repository dùng ID kiểu `String` | ID có thuộc đúng tenant hoặc phạm vi dữ liệu không |
| DTO có property không nullable | Dữ liệu cũ và mapping có cung cấp đủ giá trị không |
| Call site truyền `ProductView` làm kiểu đích | Store có hỗ trợ constructor và projection đó không |
| Kết quả được khai báo `Flow<ProductView>` | Luồng có được collect và xử lý lỗi đúng không |

## 10. Ánh xạ có kiểu với coroutine và Flow

### 10.1. Coroutine repository có hợp đồng riêng

Spring Data coroutine repository dựa trên hạ tầng reactive để cung cấp API coroutine. Tài liệu phân biệt phương thức `suspend` cho kết quả đơn và `Flow` cho nhiều kết quả, đồng thời yêu cầu repository mở rộng `CoroutineCrudRepository` để được nhận diện theo cơ chế này. [Spring Data Commons: Coroutines](https://docs.spring.io/spring-data/commons/reference/kotlin/coroutines.html).

Một biến thể repository riêng:

```kotlin
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CoroutineProductRepository : CoroutineCrudRepository<Product, String>
```

Để chạy biến thể này cần module hỗ trợ coroutine, driver reactive và các thư viện Kotlin coroutine tương thích. Không ghép nó với repository đồng bộ rồi cho rằng mọi thao tác bên trong đã tự trở thành không blocking.

### 10.2. Extension bắt buộc có kết quả đơn

```kotlin
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

suspend fun <T : Any, ID : Any> CoroutineCrudRepository<T, ID>.requireById(
    id: ID
): T = findById(id)
    ?: throw NoSuchElementException("Không tìm thấy entity với id=$id")
```

Hàm này là `suspend` vì gọi API repository tương ứng. Nó giữ kiểu entity và ID từ receiver, không cần reified để trả về `T`.

### 10.3. Flow mapping giữ kiểu mà không collect sớm

Operator `Flow.map` nhận hàm chuyển đổi có thể suspend và tạo flow chứa các kết quả ánh xạ. [kotlinx.coroutines: Flow.map](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/map.html).

Một helper minh họa:

```kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

fun <S : Any, R : Any> Flow<S>.mapViews(
    transform: suspend (S) -> R
): Flow<R> = map { source -> transform(source) }
```

Service dùng các khai báo trên:

```kotlin
import kotlinx.coroutines.flow.Flow

class CoroutineProductReadService(
    private val repository: CoroutineProductRepository
) {

    suspend fun getView(productId: String): ProductView =
        repository.requireById(productId).toView()

    fun listViews(): Flow<ProductView> =
        repository.findAll().mapViews { product -> product.toView() }
}
```

`listViews` tạo mô tả luồng kết quả, không gom tất cả sản phẩm thành một `List` ngay trong service. Caller collect flow trong coroutine phù hợp.

Một lambda `suspend` có thể gọi thao tác suspend khác, nhưng không vì thế mọi ánh xạ phải thực hiện I/O. Với DTO chỉ lấy field, nên giữ chuyển đổi đơn giản; nếu mỗi sản phẩm lại query thêm dữ liệu, cần đánh giá số lần truy cập và vòng đời xử lý thay vì giấu chi phí đó sau tên `mapViews`.

Không thêm `runBlocking`, `GlobalScope.launch` hoặc tự thu thập flow vào helper chỉ để bên ngoài nhìn thấy kiểu trả về mong muốn. Khi cần orchestration, cancellation hoặc transaction, hãy giữ chúng trong luồng ứng dụng có chủ thể quản lý rõ ràng.

## 11. Thiết kế extension dễ đọc và kiểm tra

Một extension hữu ích nên có receiver đủ cụ thể, kiểu trả về chính xác và hành vi có thể đoán từ tên.

| Thiết kế | Cách đọc hợp đồng |
| --- | --- |
| `Product.toView(): ProductView` | Chuyển một entity theo quy tắc cụ thể |
| `CrudRepository<T, ID>.requireById(ID): T` | Tra cứu đồng bộ với chính sách bắt buộc có dữ liệu |
| `Page<S>.mapViews((S) -> R): Page<R>` | Đổi kiểu nội dung của một page |
| `Flow<S>.mapViews(suspend (S) -> R): Flow<R>` | Tạo flow ánh xạ phần tử |
| Wrapper reified cho query có `Class<R>` | Cung cấp kiểu runtime cho API phía dưới |

Tránh receiver `Any` nếu chức năng thật chỉ có ý nghĩa với `Product`. Tránh trả `Any` nếu compiler đã có thể giữ `ProductView`. Cũng tránh đặt tên extension trùng member với mong muốn ghi đè hành vi của member đó.

Khi một import làm lời gọi khó hiểu, có thể dùng import alias tại call site để phân biệt extension từ các package. Tuy nhiên, tên rõ ở nơi khai báo thường dễ bảo trì hơn việc để nhiều helper tương tự cạnh tranh cùng một tên.

Hãy đặt chính sách ở đúng tầng: helper chuyển DTO không tự truy vấn thêm, helper tra cứu không tự mở tác vụ nền và wrapper reified không tự giả định một transaction mới.

## 12. Kiểm thử ví dụ bằng dữ liệu có kiểu

Các đoạn dưới là ví dụ thực hành dùng Kotlin và JUnit Jupiter, không phải báo cáo đã chạy trên dự án. Không cần database để kiểm tra phép chuyển đổi thuần hoặc metadata của một `PageImpl` đã dựng sẵn.

### 12.1. Kiểm tra nội dung DTO và metadata trang

```kotlin
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.springframework.data.domain.Page
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest

class ProductViewMappingTest {

    @Test
    fun `maps content while preserving page metadata`() {
        val source: Page<Product> = PageImpl(
            listOf(
                Product("p-3", "Chuột", "tools", 180000),
                Product("p-4", "Bàn phím", "tools", 250000)
            ),
            PageRequest.of(1, 2),
            7L
        )

        val mapped: Page<ProductView> = source.mapViews(Product::toView)

        assertEquals(
            listOf(
                ProductView("Chuột", 180000),
                ProductView("Bàn phím", 250000)
            ),
            mapped.content
        )
        assertEquals(1, mapped.number)
        assertEquals(2, mapped.size)
        assertEquals(7L, mapped.totalElements)
        assertEquals(4, mapped.totalPages)
    }
}
```

### 12.2. Kiểm tra Flow chỉ chuyển đổi khi được thu thập

Ví dụ dùng `runTest` từ thư viện coroutine test tương thích:

```kotlin
import kotlinx.coroutines.flow.asFlow
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class ProductFlowMappingTest {

    @Test
    fun `maps flow values when collected`() = runTest {
        var mappedCount = 0
        val source = listOf(
            Product("p-1", "Chuột", "tools", 180000)
        ).asFlow()

        val views = source.mapViews { product ->
            mappedCount += 1
            product.toView()
        }

        assertEquals(0, mappedCount)
        assertEquals(listOf(ProductView("Chuột", 180000)), views.toList())
        assertEquals(1, mappedCount)
    }
}
```

Nguồn trong test là flow từ dữ liệu trong bộ nhớ. Nó kiểm tra hành vi mapping của ví dụ, không chứng minh cấu hình coroutine repository hoặc driver đã đúng.

Với tích hợp store, cần kiểm tra riêng trường hợp không tìm thấy, mapping từ dữ liệu lưu trữ, projection DTO, import extension đúng và khả năng xử lý kiểu đích ở module đang dùng.

## 13. Bài tập áp dụng

Tạo `ProductView` và một extension `Product.toView()` thuần. Sau đó dùng cùng phép chuyển đổi cho `List<Product>`, `Page<Product>` và `Flow<Product>` mà vẫn giữ kiểu container tương ứng.

Giải thích các câu hỏi:

1. Vì sao helper nhận `(S) -> R` không cần reified nếu không dùng thông tin kiểu runtime?
2. Vì sao `findByIdOrNull` không tự đổi repository đồng bộ thành coroutine?
3. Vì sao ánh xạ content rồi trả `List` khác việc trả `Page<ProductView>`?
4. Vì sao wrapper projection nhận `ProductView` chưa bảo đảm mọi mapping runtime đều hợp lệ?
5. Vì sao cast một `Any` thành `List<ProductView>` không thay thế được hàm mapping?

Khi đọc một extension trong code Spring Data Kotlin, hãy xác định receiver, kiểu kết quả, nơi dữ liệu được chuyển đổi và API phía dưới thực sự thực hiện I/O. Bốn điểm đó giúp cú pháp ngắn vẫn giữ hợp đồng kiểu và phạm vi của từng module rõ ràng.
