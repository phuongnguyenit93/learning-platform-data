# suspend, Flow và chuyển đổi từ Mono hoặc Flux

## Mục tiêu và phạm vi

Trong Spring Data, một chức năng truy cập dữ liệu có thể được biểu diễn bằng Reactor hoặc bằng Kotlin coroutines khi module store có hạ tầng phù hợp:

- Reactor sử dụng `Mono<T>` và `Flux<T>`.
- Coroutine sử dụng hàm `suspend` cho một kết quả hoặc completion.
- `Flow<T>` biểu diễn một chuỗi kết quả được thu thập theo cơ chế coroutine.

Chuyển đổi giữa các hình thức này cần giữ nguyên ý nghĩa của số lượng kết quả, sự vắng mặt, lỗi và vòng đời thực thi. Việc thay `Mono<T>` bằng `T` mà không xét kết quả rỗng có thể làm thay đổi hợp đồng nghiệp vụ.

Bài học giúp bạn:

1. Chọn `suspend fun ...: T`, `T?`, `Unit` hoặc `Flow<T>` theo kết quả thực tế.
2. Dùng adapter thay cho `block()` và subscription thủ công.
3. Phân biệt chuyển đổi tín hiệu với thay đổi đặc tính I/O.
4. Giữ rõ cancellation, context và transaction khi nối Reactor với coroutine.
5. Áp dụng các cách kết hợp đó cho repository của một store được hỗ trợ.

Ví dụ cụ thể dùng R2DBC. Commons cung cấp các abstraction chung, còn driver, mapping và transaction phải được cấu hình theo module store. Không suy rằng một repository JPA đồng bộ trở thành non-blocking chỉ vì được gọi từ hàm suspend.

## 1. Chọn kiểu kết quả trước khi chọn adapter

Bắt đầu từ câu hỏi nghiệp vụ: một thao tác cần trả bao nhiêu giá trị và có chấp nhận không tìm thấy hay không?

| Hợp đồng kết quả | Dạng Reactor | Dạng coroutine phù hợp |
|---|---|---|
| Bắt buộc một giá trị | `Mono<T>` cùng chính sách lỗi nếu rỗng | `suspend fun ...: T` |
| Không hoặc một giá trị | `Mono<T>` | `suspend fun ...: T?` |
| Hoàn tất, không có dữ liệu trả về | `Mono<Void>` | `suspend fun ...: Unit` |
| Không đến nhiều giá trị | `Flux<T>` | `fun ...: Flow<T>` |
| Một collection đã gom xong | `Mono<List<T>>` | `suspend fun ...: List<T>` |

Các hàng này biểu diễn hợp đồng, không phải phép đổi tên kiểu tự động.

Ví dụ:

```kotlin
suspend fun findProduct(id: Long): Product?
suspend fun requireProduct(id: Long): Product
suspend fun deleteProduct(id: Long)
fun findActiveProducts(): Flow<Product>
```

`findProduct` cho phép không có kết quả. `requireProduct` cần một chính sách báo lỗi khi thiếu dữ liệu. `deleteProduct` hoàn tất hoặc ném lỗi, không cung cấp số hàng bị xóa. Flow có thể hoàn tất mà không phát phần tử.

Cũng cần phân biệt:

- `false` là một giá trị của `Boolean`.
- Một list rỗng là một giá trị của `List<T>`.
- `null` là một giá trị được kiểu `T?` cho phép.
- Một flow rỗng không phát phần tử nào.
- Exception biểu diễn lỗi, không nên bị đổi tùy tiện thành không tìm thấy.

## 2. suspend tạm ngừng coroutine tại điểm chờ phù hợp

Một hàm suspend có thể được viết theo thứ tự thông thường:

```kotlin
suspend fun loadView(id: Long): ProductView {
    val product = requireProduct(id)
    return ProductView(
        id = requireNotNull(product.id),
        name = product.name
    )
}
```

Bên gọi nhìn thấy một luồng logic tuần tự. Khi thao tác bên trong hỗ trợ suspension, coroutine có thể tạm ngừng chờ kết quả mà không giữ thread chỉ để chờ I/O.

Cần hiểu đúng các giới hạn:

- Hàm suspend chạy trong ngữ cảnh coroutine của bên gọi.
- Gọi một hàm suspend không tự tạo công việc chạy nền.
- Hai lời gọi suspend viết liên tiếp vẫn có thứ tự tuần tự nếu không chủ động tạo concurrency.
- Không có cam kết rằng coroutine luôn tiếp tục trên đúng một thread vật lý.
- Mã blocking bên trong vẫn chặn thread đang thực hiện nó.

Ví dụ sau vẫn gọi API JPA đồng bộ:

```kotlin
suspend fun findWithJpa(id: Long): Customer? =
    jpaRepository.findByIdOrNull(id)
```

Từ khóa `suspend` không thay đổi cách JDBC hoặc JPA chờ database. Nếu phải tích hợp mã blocking, cần một ranh giới thực thi và chính sách tài nguyên riêng, phù hợp cả transaction đang dùng.

## 3. Flow biểu diễn một chuỗi được collect

Một flow được sử dụng bằng terminal operation như `collect` hoặc `toList`:

```kotlin
import kotlinx.coroutines.flow.collect

suspend fun inspectProducts(products: Flow<Product>) {
    products.collect { product ->
        println(product.name)
    }
}
```

Ví dụ chỉ minh họa việc tiêu thụ chuỗi. Một service web thường trả flow cho lớp biên phù hợp thay vì tự in hoặc thu thập toàn bộ dữ liệu.

Đối với nguồn cold thông thường:

```text
Tạo Flow
    -> mô tả cách xử lý

Collect Flow
    -> thực hiện nguồn
    -> nhận từng phần tử
    -> hoàn tất, lỗi hoặc bị hủy
```

Flow cũng có các dạng nguồn chia sẻ hoặc hot. Không mặc định mọi flow đều khởi động lại cùng dữ liệu từ đầu cho mỗi collector.

Một điểm thuận tiện là transform của các operator như `map` có thể gọi hàm suspend:

```kotlin
val views: Flow<ProductView> = products.map { product ->
    buildView(product)
}
```

Ví dụ giả định `buildView` có thể là hàm suspend. Trong một flow đơn giản, các phần tử được xử lý tuần tự; không tự có xử lý song song chỉ vì transform có thể suspend.

## 4. Thư viện và import của các adapter

Những import thường dùng:

```kotlin
import kotlinx.coroutines.reactive.asFlow
import kotlinx.coroutines.reactor.asFlux
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.reactor.mono
```

Vai trò:

| API | Chuyển đổi |
|---|---|
| `Mono<T>.awaitSingle()` | Chờ đúng kết quả bắt buộc của Mono trong coroutine |
| `Mono<T>.awaitSingleOrNull()` | Chờ kết quả hoặc nhận null khi Mono rỗng |
| `Publisher<T>.asFlow()` | Chuyển nguồn Reactive Streams thành Flow |
| `Flow<T>.asFlux()` | Chuyển flow thành Flux |
| `mono { ... }` | Đóng gói công việc suspend thành Mono |

`asFlow` ở đây thuộc adapter Reactive Streams, còn `asFlux`, `mono` và các extension chờ Mono thuộc phần tích hợp Reactor.

Ứng dụng cần các thư viện coroutine và adapter tương ứng, thường liên quan `kotlinx-coroutines-core`, `kotlinx-coroutines-reactive` và `kotlinx-coroutines-reactor`. Phiên bản phải tương thích với bộ Spring, Reactor và Kotlin đang sử dụng.

Import cùng tên ở thư viện khác có thể có receiver hoặc hợp đồng khác. Hãy đọc kiểu đối tượng đang chuyển đổi thay vì chỉ dựa vào tên hàm được IDE đề xuất.

Adapter nối hai mô hình thực thi. Nó không tự thêm connection factory, không đổi mapping và không bổ sung tính năng store chưa hỗ trợ.

## 5. Chuyển Mono sang một kết quả suspend

### 5.1. Dùng awaitSingle khi bắt buộc có giá trị

```kotlin
import kotlinx.coroutines.reactor.awaitSingle

suspend fun requireProduct(id: Long): Product =
    reactiveProducts.findById(id).awaitSingle()
```

Hàm nhận một sản phẩm nếu Mono phát giá trị. Nếu Mono hoàn tất rỗng, `awaitSingle` báo lỗi thiếu phần tử, thay vì tạo một `Product` hoặc trả null.

Nếu nghiệp vụ cần một exception có ngữ nghĩa rõ hơn, có thể xử lý rỗng chủ động:

```kotlin
import java.util.NoSuchElementException

import kotlinx.coroutines.reactor.awaitSingleOrNull

suspend fun requireProduct(id: Long): Product =
    reactiveProducts.findById(id).awaitSingleOrNull()
        ?: throw NoSuchElementException(
            "Product not found: $id"
        )
```

Hai ví dụ là hai cách triển khai thay thế cho cùng một nhu cầu. Chọn cách phù hợp với hợp đồng lỗi của ứng dụng.

### 5.2. Dùng awaitSingleOrNull khi chấp nhận không có kết quả

```kotlin
suspend fun findProduct(id: Long): Product? =
    reactiveProducts.findById(id).awaitSingleOrNull()
```

Quy tắc:

| Tín hiệu Mono | Kết quả ở hàm suspend |
|---|---|
| Phát product rồi hoàn tất | Trả product |
| Hoàn tất rỗng | Trả null |
| Phát lỗi | Ném exception tương ứng |
| Chưa kết thúc | Coroutine tiếp tục chờ, trừ khi có hủy hoặc chính sách khác |

`awaitSingleOrNull` không biến lỗi kết nối thành null. Đây là khác biệt quan trọng giữa không tìm thấy dữ liệu và truy cập dữ liệu thất bại.

Không bắt mọi exception rồi trả null chỉ để giữ kiểu nullable. Cách đó làm sai hợp đồng lỗi.

### 5.3. Không dùng block trong service coroutine

Cách dễ sai:

```kotlin
suspend fun findProduct(id: Long): Product? =
    reactiveProducts.findById(id).block()
```

`block()` chặn thread gọi nó để chờ. Nó không phải cách tận dụng suspension và có thể không được phép trên thread event loop.

Adapter `await...` liên kết việc chờ với coroutine và hỗ trợ cancellation theo cơ chế của thư viện.

## 6. Mono<Void> chuyển thành Unit

Một thao tác xóa reactive thường không phát dữ liệu:

```kotlin
fun deleteById(id: Long): Mono<Void>
```

Cách viết một hàm suspend tương ứng:

```kotlin
import kotlinx.coroutines.reactor.awaitSingleOrNull

suspend fun deleteProduct(id: Long) {
    reactiveProducts.deleteById(id).awaitSingleOrNull()
}
```

Hàm có block body ở trên trả `Unit). Nếu thao tác phát lỗi, lỗi được ném; nếu hoàn tất bình thường, hàm kết thúc.

Không dùng `awaitSingle()` cho một `Mono<Void>` chỉ hoàn tất mà không có phần tử. Không có phần tử là hình dạng thành công của thao tác này.

Cũng không suy rằng completion chứng minh một entity trước đó có tồn tại. `Mono<Void>` không cung cấp entity đã xóa hoặc số hàng bị ảnh hưởng.

Nếu cần báo lỗi khi không tìm thấy:

```kotlin
suspend fun deleteRequiredProduct(id: Long) {
    val product = reactiveProducts.findById(id)
        .awaitSingleOrNull()
        ?: throw NoSuchElementException(
            "Product not found: $id"
        )

    reactiveProducts.delete(product).awaitSingleOrNull()
}
```

Ví dụ kiểm tra sự tồn tại tại thời điểm đọc. Tính nhất quán giữa đọc và xóa, đặc biệt khi có cạnh tranh, cần cơ chế của store hoặc transaction phù hợp.

## 7. Chuyển Flux sang Flow

Chuyển trực tiếp khi muốn tiếp tục xử lý một chuỗi:

```kotlin
import kotlinx.coroutines.reactive.asFlow

fun activeProducts(): Flow<Product> =
    reactiveProducts.findByActiveTrue().asFlow()
```

Adapter đăng ký với nguồn Reactive Streams khi flow được collect. Các giá trị, lỗi và tín hiệu kết thúc được nối sang vòng đời collection.

Có thể kết hợp operator coroutine:

```kotlin
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.reactive.asFlow

fun activeViews(): Flow<ProductView> =
    reactiveProducts.findByActiveTrue()
        .asFlow()
        .map { product ->
            ProductView(
                id = requireNotNull(product.id),
                name = product.name
            )
        }
```

Không cần gom toàn bộ sản phẩm thành list để đổi API từ Reactor sang coroutine.

### 7.1. Khi thật sự cần một List

Hai cách sau đều materialize toàn bộ kết quả:

```kotlin
val products: List<Product> =
    reactiveProducts.findAll()
        .collectList()
        .awaitSingle()
```

```kotlin
import kotlinx.coroutines.flow.toList

val products: List<Product> =
    reactiveProducts.findAll()
        .asFlow()
        .toList()
```

Chúng phù hợp với tập hữu hạn có kích thước kiểm soát. Chúng dùng bộ nhớ theo kết quả và chờ nguồn hoàn tất.

Một nguồn không hoàn tất không cung cấp list cuối cùng. Đổi `Flux` thành `Flow` rồi gọi `toList` vẫn không giải quyết vấn đề đó.

### 7.2. Lấy phần tử đầu tiên khác với yêu cầu đúng một phần tử

Nếu nghiệp vụ chỉ cần phần tử đầu tiên:

```kotlin
val first: Product? = reactiveProducts.findAll()
    .next()
    .awaitSingleOrNull()
```

`next()` chọn phần tử đầu tiên, không xác minh toàn bộ nguồn chỉ có một phần tử.

Nếu hợp đồng yêu cầu nguồn phải có đúng một phần tử, cần operator kiểm tra cardinality tương ứng. Đừng dùng “lấy đầu tiên” để che một query đáng lẽ phải trả duy nhất.

## 8. Chuyển Flow hoặc công việc suspend về Reactor

Một lớp biên có thể cần trả Reactor cho bên gọi Java hoặc API reactive đã có.

### 8.1. Flow sang Flux

```kotlin
import kotlinx.coroutines.reactor.asFlux

fun activeAsFlux(): Flux<ProductView> =
    productService.activeViews().asFlux()
```

Subscriber của Flux điều khiển vòng đời tiêu thụ. Với flow cold, subscription mới có thể tạo một lượt collect mới. Adapter không tự cache kết quả.

### 8.2. Công việc suspend sang Mono

```kotlin
import kotlinx.coroutines.reactor.mono

fun findAsMono(id: Long): Mono<ProductView> =
    mono {
        productService.find(id)
    }
```

Ví dụ giả định `productService.find` là hàm suspend trả `ProductView?`.

Builder `mono` tạo nguồn để công việc coroutine chạy khi được subscribe. Kết quả null trong hợp đồng của builder được biểu diễn bằng Mono hoàn tất rỗng; nó không được phát thành một phần tử null.

Lỗi trong công việc suspend được biểu diễn thành tín hiệu lỗi của Mono. Khi subscription bị hủy, công việc coroutine liên quan được hủy theo hỗ trợ của adapter.

Không dùng:

```kotlin
fun findAsMono(id: Long): Mono<ProductView> =
    Mono.just(
        runBlocking {
            productService.requireView(id)
        }
    )
```

Java đánh giá đối số trước khi gọi `Mono.just`; `runBlocking` ở đây đã chặn bên gọi trong lúc tạo publisher.

Builder phù hợp giúp giữ việc thực thi trong vòng đời của subscription thay vì thực hiện trước ở bước xây dựng API.

## 9. Flow có thể chứa null, Reactor không phát null

Kotlin cho phép khai báo:

```kotlin
val names: Flow<String?>
```

Reactor không chấp nhận `null` như một phần tử `onNext`. Vì vậy, trước khi chuyển một flow nullable sang Flux, cần quyết định cách biểu diễn sự vắng mặt.

Nếu null không cần giữ lại:

```kotlin
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.reactor.asFlux

val nonNullNames: Flux<String> =
    names.filterNotNull().asFlux()
```

Lựa chọn này loại bỏ các phần tử null. Nó làm thay đổi số phần tử và chỉ phù hợp khi đó là chính sách mong muốn.

Nếu cần một kết quả cho từng yêu cầu, dùng wrapper không-null:

```kotlin
data class ProductLookup(
    val requestedId: Long,
    val product: Product?
)
```

Một `ProductLookup` luôn là object hợp lệ để phát. Trạng thái không tìm thấy nằm trong property nullable của nó.

Đừng ép kiểu hoặc dùng `!!` chỉ để vượt qua khác biệt kiểu giữa hai mô hình. Cần giữ rõ semantics của sự vắng mặt.

## 10. Ví dụ đầy đủ ở lớp truy cập và service

Ví dụ dưới đây dùng R2DBC với model bất biến. Mỗi kiểu được hiểu là một đơn vị mã nguồn phù hợp trong ứng dụng.

### 10.1. Model và repository reactive

```kotlin
import java.math.BigDecimal

import org.springframework.data.annotation.Id
import org.springframework.data.relational.core.mapping.Table

@Table("product")
data class Product(
    @field:Id
    val id: Long? = null,
    val name: String,
    val price: BigDecimal,
    val active: Boolean = true
)
```

```kotlin
import org.springframework.data.repository.reactive.ReactiveCrudRepository

import reactor.core.publisher.Flux

interface ReactiveProductRepository :
    ReactiveCrudRepository<Product, Long> {

    fun findByActiveTrue(): Flux<Product>
}
```

Schema phải phù hợp với mapping, trong đó chiến lược cấp ID cần khớp với cách tạo đối tượng mới có `id = null`. Cấu hình connection factory và repository thuộc module R2DBC.

### 10.2. Service coroutine sử dụng repository reactive đã có

```kotlin
import java.math.BigDecimal
import java.util.NoSuchElementException

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.reactive.asFlow
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull

import org.springframework.stereotype.Service

data class ProductView(
    val id: Long,
    val name: String
)

@Service
class ProductService(
    private val products: ReactiveProductRepository
) {

    suspend fun find(id: Long): ProductView? =
        products.findById(id)
            .awaitSingleOrNull()
            ?.let { toView(it) }

    suspend fun requireView(id: Long): ProductView =
        find(id)
            ?: throw NoSuchElementException(
                "Product not found: $id"
            )

    suspend fun create(
        name: String,
        price: BigDecimal
    ): ProductView {
        require(name.isNotBlank()) {
            "Name is required"
        }

        require(price.signum() >= 0) {
            "Price must be non-negative"
        }

        val draft = Product(
            name = name,
            price = price
        )

        val saved = products.save(draft).awaitSingle()
        return toView(saved)
    }

    fun activeViews(): Flow<ProductView> =
        products.findByActiveTrue()
            .asFlow()
            .map { product -> toView(product) }

    suspend fun delete(id: Long) {
        products.deleteById(id).awaitSingleOrNull()
    }

    private fun toView(product: Product): ProductView =
        ProductView(
            id = requireNotNull(product.id) {
                "A persisted product must have an identifier"
            },
            name = product.name
        )
}
```

Những hợp đồng quan trọng:

- `find` cho phép null khi không tìm thấy.
- `requireView` chuyển null thành lỗi nghiệp vụ có chủ đích.
- `create` yêu cầu một entity từ thao tác lưu và dùng instance đã được phát ra.
- `activeViews` giữ kết quả dạng chuỗi; service chưa collect toàn bộ.
- `delete` dùng completion, không đòi một phần tử từ `Mono<Void>`.
- Không có `block`, `runBlocking` hay subscription thủ công bên trong service.

Ví dụ minh họa cách chuyển đổi kết quả. Nó chưa thiết lập transaction cho một use case nhiều thao tác; yêu cầu đó cần hạ tầng tương ứng.

### 10.3. Lớp biên WebFlux có thể dùng suspend và Flow

```kotlin
import kotlinx.coroutines.flow.Flow

import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/products")
class ProductController(
    private val service: ProductService
) {

    @GetMapping("/{id}")
    suspend fun find(
        @PathVariable id: Long
    ): ResponseEntity<ProductView> {
        val product = service.find(id)
            ?: return ResponseEntity.notFound()
                .build<ProductView>()

        return ResponseEntity.ok(product)
    }

    @GetMapping("/active")
    fun active(): Flow<ProductView> =
        service.activeViews()
}
```

Ví dụ giả định WebFlux và coroutine integration đã được cấu hình. Framework quản lý vòng đời xử lý response; controller không cần mở một coroutine nền để chạy repository.

Định dạng HTTP và serialization của chuỗi còn phụ thuộc cấu hình web. Việc trả flow không tự định nghĩa một giao thức streaming cụ thể cho mọi client.

## 11. Dùng CoroutineCrudRepository khi muốn API coroutine trực tiếp

Nếu module store hỗ trợ, có thể khai báo repository coroutine thay vì tự chuyển từng thao tác từ Reactor:

```kotlin
import kotlinx.coroutines.flow.Flow

import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface CoroutineProductRepository :
    CoroutineCrudRepository<Product, Long> {

    fun findByActiveTrue(): Flow<Product>
}
```

Khi đó service sử dụng trực tiếp:

```kotlin
suspend fun findProduct(id: Long): Product? =
    coroutineProducts.findById(id)

fun activeProducts(): Flow<Product> =
    coroutineProducts.findByActiveTrue()

suspend fun deleteProduct(id: Long) {
    coroutineProducts.deleteById(id)
}
```

Các đoạn này giả định `coroutineProducts` đã được inject đúng kiểu. Đây là lựa chọn thay thế cho ví dụ service dựa trên reactive repository, không phải yêu cầu tạo hai repository trong cùng một use case.

Không gọi `awaitSingle` trên một giá trị mà coroutine repository đã trả trực tiếp. Adapter chỉ cần ở nơi đổi mô hình.

`CoroutineCrudRepository` thuộc Commons, nhưng khả năng tạo implementation cần hạ tầng reactive/coroutine của module store. Việc interface tồn tại trên classpath không chứng minh mọi store đều tạo được repository đó.

## 12. Kết hợp nhiều thao tác mà không tạo publisher lồng

Với Flow, transform có thể suspend nên có thể chờ một query khác trong mỗi bước.

Cách dễ sai:

```kotlin
val nested: Flow<Mono<Product>> = ids.map { id ->
    reactiveProducts.findById(id)
}
```

Kết quả là một flow phát các object Mono. Nó chưa tự kết hợp việc thực thi các query để phát sản phẩm.

Nếu chính sách là bỏ qua ID không tồn tại:

```kotlin
import kotlinx.coroutines.flow.mapNotNull
import kotlinx.coroutines.reactor.awaitSingleOrNull

val foundProducts: Flow<Product> = ids.mapNotNull { id ->
    reactiveProducts.findById(id).awaitSingleOrNull()
}
```

Nếu thiếu bất kỳ sản phẩm nào phải là lỗi, dùng chính sách bắt buộc thay vì `mapNotNull`.

Cần xét chi phí: mẫu này có thể tạo một query cho từng ID. Nếu module có API tìm theo tập ID phù hợp, nó có thể hiệu quả hơn; việc đổi sang coroutine không loại bỏ vấn đề N query.

### Thứ tự tuần tự và concurrency

Trong flow đơn giản ở trên, mỗi bước chờ query của nó trước khi xử lý bước tiếp theo. Để có concurrency phải chọn operator hoặc cấu trúc coroutine thể hiện điều đó.

Khi thêm concurrency, cần xác định:

- Giới hạn số tác vụ đang chờ.
- Thứ tự kết quả có cần được giữ hay không.
- Khả năng của pool kết nối.
- Có đang dùng chung một transaction hoặc tài nguyên không hỗ trợ thao tác đồng thời hay không.

Không mặc định `async` hoặc operator merge có thể làm mọi thao tác database chạy song song an toàn.

## 13. Backpressure, buffering và giới hạn truy vấn

Reactive Streams điều phối nhu cầu bằng `request(n)`. Flow thông thường điều phối việc phát và xử lý thông qua suspension. Adapter nối các cơ chế đó và có thể sử dụng buffering.

Nếu bên collect xử lý chậm, upstream không vì thế mà có quyền phát dữ liệu vô hạn vào bộ nhớ ứng dụng. Tuy nhiên, mức prefetch, buffer và chiến lược đọc thực tế còn phụ thuộc adapter và driver.

Một số thay đổi có ý nghĩa khác nhau:

| Thao tác | Ý nghĩa |
|---|---|
| `buffer(...)` trên Flow | Điều chỉnh việc đệm và cách phối hợp producer/consumer |
| `take(n)` | Giới hạn số phần tử tiếp tục được tiêu thụ |
| `toList()` | Gom toàn bộ kết quả trước khi trả list |
| Query có giới hạn | Giảm phạm vi kết quả do store xử lý theo query |
| Phân trang hoặc cursor | Chọn một phần của tập kết quả theo hợp đồng API |

`take(10)` sau `asFlow()` không tự sửa câu SQL thành `LIMIT 10`. Driver hoặc database có thể đã làm một phần công việc trước khi cancellation được truyền đến.

Tương tự, `Flow<Product>` không tự mang tổng số hàng hoặc số trang. Những metadata đó phải được xây dựng theo khả năng của repository và store.

Không thêm buffer lớn chỉ để che một consumer chậm. Nó có thể chuyển áp lực xử lý thành áp lực bộ nhớ.

## 14. Lỗi, cancellation và context khi chuyển đổi

### 14.1. Thời điểm lỗi phụ thuộc thời điểm thực thi

Với `await...`, lỗi từ Mono được ném tại điểm chờ.

Với `Flux.asFlow()`, lỗi nguồn được quan sát khi collect. Chỉ tạo biến Flow không phải một lần đã đọc hết dữ liệu và kiểm tra mọi lỗi.

Nếu ứng dụng bắt lỗi để trả kết quả thay thế, phải phân biệt lỗi hạ tầng với không tìm thấy. Không đổi mọi lỗi thành flow rỗng hoặc null.

### 14.2. Cancellation được nối qua adapter

Các adapter chờ Mono hỗ trợ hủy subscription khi coroutine đang chờ bị hủy. Khi collection của flow từ publisher dừng, adapter cũng liên kết việc dừng với nguồn theo giao thức tương ứng.

Điều đó giúp giữ công việc trong vòng đời của bên gọi. Nó không phải cam kết rằng các tác dụng phụ đã xảy ra ở database hoặc hệ thống ngoài được hoàn tác.

Tránh khối `try/catch` hoặc `runCatching` quá rộng làm `CancellationException` bị đổi thành dữ liệu thành công. Các operator của Flow có quy tắc xử lý lỗi riêng; cần giữ tính minh bạch của cancellation thay vì chặn mọi exception.

### 14.3. Context cần hạ tầng phù hợp

Reactor Context và coroutine context có cơ chế tích hợp trong thư viện tương ứng. Một luồng sử dụng adapter đúng có thể giữ được ngữ cảnh cần thiết theo khả năng của tích hợp.

Tuy nhiên, không mặc định mọi giá trị ThreadLocal, MDC hoặc transaction đồng bộ tự đi theo coroutine qua mọi lần đổi dispatcher.

Cần xác định rõ:

- Nguồn danh tính hoặc metadata được lấy từ context nào.
- Phần nào đi qua adapter hỗ trợ context.
- Transaction manager nào đang quản lý thao tác.
- Có đoạn công việc nào bị tách khỏi coroutine/subscription của bên gọi hay không.

Không dùng `GlobalScope.launch` để chạy thao tác repository rồi trả kết quả như công việc đã hoàn tất. Việc tách vòng đời như vậy có thể làm mất sự phối hợp lỗi, hủy và transaction.

## 15. Transaction và tính thực thi lại

Chuyển đổi `Mono` sang hàm suspend không tự mở một transaction mới. Chuyển `Flux` sang `Flow` cũng không tự làm nhiều thao tác thành nguyên tử.

Với R2DBC, cần transaction manager và cách tích hợp reactive/coroutine phù hợp. Nếu sử dụng cơ chế transaction của Spring, toàn bộ công việc cần quản lý phải nằm trong phạm vi thực thi được cơ chế đó hỗ trợ.

Đừng suy rằng một `@Transactional` dùng cho JPA đồng bộ có thể được giữ nguyên về semantics sau khi thay implementation bằng reactive store hoặc chuyển công việc qua dispatcher.

### Collect hoặc subscribe nhiều lần có thể thực thi nhiều lần

Xét một flow cold chứa thao tác lưu:

```kotlin
fun createLater(
    name: String,
    price: BigDecimal
): Flow<Product> = flow {
    val saved = reactiveProducts.save(
        Product(name = name, price = price)
    ).awaitSingle()

    emit(saved)
}
```

Mỗi lần collect có thể thực hiện thêm một lần lưu. Mẫu trên chỉ dùng để minh họa tính thực thi lại, không phải lựa chọn mặc định cho API tạo sản phẩm.

Với một thao tác tạo trả một kết quả, hàm suspend trực tiếp thường diễn tả vòng đời dễ hiểu hơn. Nếu cố ý tạo một nguồn deferred có tác dụng phụ, phải tài liệu hóa chính sách collection và retry.

Tương tự, `mono { create(...) }` có thể thực hiện lại công việc khi có subscription mới. Các adapter không tự cung cấp cache, idempotency hoặc bảo đảm xử lý đúng một lần.

## 16. Kiểm tra các hợp đồng chuyển đổi

Một số kiểm tra nhỏ có thể xác minh cardinality và dữ liệu mà không cần database:

```kotlin
import kotlin.test.assertEquals
import kotlin.test.assertNull

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.reactive.asFlow
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.test.runTest

import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

fun verifyAdapters() = runTest {
    val required = Mono.just("Spring Data").awaitSingle()
    assertEquals("Spring Data", required)

    val missing = Mono.empty<String>().awaitSingleOrNull()
    assertNull(missing)

    val values = Flux.just(1, 2, 3)
        .asFlow()
        .toList()

    assertEquals(listOf(1, 2, 3), values)
}
```

Đây là ví dụ kiểm tra adapter với nguồn đơn giản. `runTest` không tự điều khiển mọi scheduler Reactor hoặc I/O database như cùng một đồng hồ kiểm thử.

Với repository thật, cần kiểm tra thêm:

| Kịch bản | Điều cần quan sát |
|---|---|
| ID tồn tại | `awaitSingleOrNull` trả entity |
| ID không tồn tại | Hàm nullable trả null, hàm bắt buộc theo đúng chính sách lỗi |
| Store phát lỗi | Exception được giữ hoặc ánh xạ có chủ đích |
| Xóa hoàn tất không có giá trị | Hàm suspend trả Unit, không đòi một phần tử |
| Flux không có bản ghi | Flow hoàn tất không phát phần tử |
| Flux phát nhiều bản ghi | Flow chuyển đủ giá trị theo hợp đồng nguồn |
| Collect lại nguồn cold | Số lần truy vấn phản ánh số lần thực thi |
| Hủy coroutine đang chờ | Subscription/công việc liên quan được hủy theo tích hợp |
| Transaction nhiều bước | Commit/rollback đúng hạ tầng được cấu hình |

Mock một repository trả Mono không đủ để chứng minh driver non-blocking, mapping hoặc transaction integration. Những phần đó cần được xác minh ở mức tích hợp của store.

## 17. Chẩn đoán nhanh và bài thực hành

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Xóa thành công nhưng hàm báo thiếu phần tử | Có dùng `awaitSingle` cho `Mono<Void>` không? |
| Không tìm thấy lại thành exception ngoài ý muốn | Hợp đồng cần `T?` nhưng đang dùng `awaitSingle`? |
| Không có query khi tạo Flow | Flow đã được collect chưa? |
| Query hoặc ghi chạy hai lần | Có nhiều subscription/collection hoặc retry không? |
| Kết quả là `Flow<Mono<T>>` | Có tạo publisher lồng thay vì chờ/kết hợp thao tác không? |
| Server bị chặn dù dùng suspend | Có gọi `block`, `runBlocking` hoặc API blocking bên trong không? |
| Chuyển Flow nullable không phù hợp Flux | Đã chọn cách biểu diễn null bằng lọc hoặc wrapper chưa? |
| Bộ nhớ tăng khi đổi Flux sang coroutine | Có `toList`, buffer hoặc concurrency quá lớn không? |
| Lỗi database bị nhìn như không tìm thấy | Có khối bắt lỗi quá rộng đang trả null hoặc nguồn rỗng không? |
| Context khác sau khi chuyển mô hình | Đã kiểm tra adapter, transaction manager và việc đổi dispatcher chưa? |

Bài thực hành với một store có hỗ trợ reactive repository:

1. Viết hàm suspend tìm tùy chọn bằng `awaitSingleOrNull`.
2. Viết hàm bắt buộc có kết quả với chính sách lỗi rõ ràng.
3. Viết thao tác xóa trả Unit từ một `Mono<Void>`.
4. Trả Flow từ một query Flux và chuyển đổi từng phần tử thành DTO.
5. Tạo lớp biên trả Mono/Flux từ service coroutine bằng `mono` và `asFlux`.
6. So sánh việc trả Flow với việc gom toàn bộ thành List.
7. Kiểm tra kết quả rỗng, lỗi và collection nhiều lần.
8. Giải thích cách cancellation và transaction đi qua ranh giới đã chọn.

Điểm cần giải thích được là: **suspend biểu diễn việc chờ kết quả trong coroutine; Flow biểu diễn chuỗi cần được collect; adapter nối tín hiệu Reactor với các mô hình đó; cardinality, nullability và vòng đời công việc vẫn phải được giữ đúng theo hợp đồng repository và khả năng của store**.