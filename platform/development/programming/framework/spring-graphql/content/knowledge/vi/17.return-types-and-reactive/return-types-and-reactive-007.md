# Kotlin suspend function trong Spring for GraphQL

Spring for GraphQL hỗ trợ Kotlin coroutine trong annotated controller. Nhờ đó, một phương thức `suspend` có thể xử lý Query, Mutation hoặc field mapping và trả về kết quả đơn lẻ mà không cần bọc thủ công bằng `CompletableFuture` hay `Mono`.

`suspend` không tự biến mọi lời gọi thành non-blocking. Coroutine chỉ nhường quyền thực thi khi gọi một hàm thực sự suspend hoặc khi chuyển sang dispatcher phù hợp. Nếu bên trong phương thức vẫn gọi JDBC/JPA đồng bộ trên thread hiện tại, thread đó vẫn bị chặn. Cần phân biệt API coroutine, API reactive và thư viện blocking khi thiết kế resolver.

## Coroutine được dùng ở đâu trong GraphQL?

Trong Kotlin, hàm `suspend` có thể tạm dừng và tiếp tục sau khi một tác vụ bất đồng bộ hoàn tất. Spring for GraphQL nhận diện suspend function trong annotated controller và tích hợp nó với cơ chế thực thi GraphQL.

Các trường hợp thường gặp:

- Query trả về một object, scalar hoặc collection sau khi gọi service suspend.
- Mutation thực hiện thao tác ghi bất đồng bộ rồi trả về kết quả.
- Field resolver dùng `@SchemaMapping` gọi một service suspend để lấy dữ liệu liên quan.
- Subscription trả về `Flow<T>` để phát nhiều sự kiện theo thời gian.

Ví dụ, một Query có thể dùng `suspend fun` thay cho phương thức đồng bộ hoặc `CompletableFuture`:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
```

```kotlin
@Controller
class BookController(
    private val bookService: BookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? {
        return bookService.findById(id)
    }
}
```

Khi GraphQL thực thi field `Query.book`, Spring gọi suspend function và chờ kết quả theo cơ chế coroutine. Giá trị `Book?` có thể là một `Book` hoặc `null`; schema SDL vẫn quyết định field có được phép null hay không.

## Thêm dependency coroutine

Để tích hợp coroutine với Spring for GraphQL, ứng dụng Kotlin cần có thư viện coroutine và cầu nối Reactor. Ví dụ Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")
}
```

Trong dự án dùng Spring Boot dependency management, để BOM quản lý phiên bản tương thích thay vì tự chọn các phiên bản coroutine rời rạc. Ứng dụng Kotlin với Spring thường cũng dùng Kotlin Spring plugin và Kotlin reflection theo cấu hình nền tảng của dự án.

`kotlinx-coroutines-reactor` cung cấp tích hợp giữa coroutine và Reactor, cần thiết cho việc chuyển đổi và phối hợp với các API reactive mà Spring sử dụng. Không cần dùng WebFlux chỉ vì muốn khai báo `suspend`; coroutine support ở annotated controller không đồng nghĩa toàn bộ ứng dụng phải chuyển sang WebFlux.

## Query bằng suspend function

Service có thể khai báo API suspend để controller không phải biết chi tiết cách lấy dữ liệu:

```kotlin
interface BookService {
    suspend fun findById(id: String): Book?
}
```

Controller gọi service trực tiếp:

```kotlin
@Controller
class BookQueryController(
    private val bookService: BookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? =
        bookService.findById(id)
}
```

Kiểu trả về của hàm là `Book?`, không phải `Mono<Book>` hoặc `CompletableFuture<Book>`. Spring for GraphQL nhận biết suspend function và điều phối kết quả qua coroutine integration.

Kotlin nullability cần nhất quán với SDL. Nếu schema khai báo `book(id: ID!): Book!`, controller phải trả về một Book khác null hoặc phát lỗi phù hợp. Nếu schema khai báo `Book`, controller có thể trả `null` khi không tìm thấy. Kotlin type system giúp thể hiện ý định trong code, nhưng schema mới là hợp đồng GraphQL mà client nhìn thấy.

## Mutation bằng suspend function

Mutation cũng có thể là suspend function. Ví dụ schema nhận input và trả về sách sau khi cập nhật:

```graphql
input RenameBookInput {
  id: ID!
  title: String!
}

type Mutation {
  renameBook(input: RenameBookInput!): Book!
}
```

Kotlin input model và controller:

```kotlin
data class RenameBookInput(
    val id: String,
    val title: String
)

@Controller
class BookMutationController(
    private val bookService: BookService
) {
    @MutationMapping
    suspend fun renameBook(
        @Argument("input") input: RenameBookInput
    ): Book {
        return bookService.rename(input.id, input.title)
    }
}
```

Việc dùng `suspend` không thay đổi ngữ nghĩa Mutation của GraphQL. Các field cấp cao nhất trong cùng một mutation operation vẫn được thực thi tuần tự theo quy tắc GraphQL. Transaction và tính nguyên tử của nghiệp vụ vẫn phải được triển khai ở tầng service hoặc persistence.

## Field resolver bằng suspend và `@SchemaMapping`

Coroutine cũng hữu ích khi một field lồng nhau cần gọi service bất đồng bộ. Giả sử `Book` chứa `authorId`, còn thông tin `Author` được tải riêng:

```graphql
type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
```

```kotlin
@Controller
class BookFieldController(
    private val authorService: AuthorService
) {
    @SchemaMapping(typeName = "Book", field = "author")
    suspend fun author(@Source book: Book): Author? {
        return authorService.findById(book.authorId)
    }
}
```

`@Source` đánh dấu object cha mà GraphQL đã resolve; `Book` là source của field `Book.author`. Nếu field có argument, có thể kết hợp `@Argument` với source parameter:

```graphql
type Book {
  translatedTitle(locale: String!): String
}
```

```kotlin
@SchemaMapping(typeName = "Book", field = "translatedTitle")
suspend fun translatedTitle(
    @Source book: Book,
    @Argument("locale") locale: String
): String? {
    return translationService.title(book.id, locale)
}
```

Như với Java controller, không cần viết `@SchemaMapping` cho field chỉ đọc được từ property/getter có sẵn. Dùng resolver riêng khi cần gọi service, tính toán, chuyển đổi hoặc kiểm tra quyền.

## Kết hợp coroutine với API reactive

Một service có thể đang dùng Reactor và trả về `Mono` hoặc `Flux`. Khi muốn viết controller theo phong cách coroutine, có thể chuyển đổi `Mono` thành giá trị suspend bằng extension từ `kotlinx-coroutines-reactor`.

```kotlin
import kotlinx.coroutines.reactor.awaitSingleOrNull

@Controller
class BookController(
    private val bookService: ReactiveBookService
) {
    @QueryMapping
    suspend fun book(@Argument("id") id: String): Book? {
        return bookService.findById(id).awaitSingleOrNull()
    }
}
```

`awaitSingleOrNull()` suspend coroutine cho tới khi Mono phát giá trị, hoàn tất rỗng hoặc lỗi. Nếu Mono phát lỗi, exception được truyền vào coroutine để Spring for GraphQL xử lý như lỗi thực thi field.

Với `Mono` bắt buộc phải có giá trị, có thể dùng `awaitSingle()`. Chọn hàm await theo đúng hợp đồng của publisher: đừng dùng hàm yêu cầu một phần tử nếu nguồn có thể hoàn tất rỗng.

Khi service đã có API suspend, gọi trực tiếp API đó thường đơn giản hơn việc chuyển qua lại giữa `Mono` và coroutine. Tránh tạo nhiều lớp chuyển đổi không cần thiết vì chúng làm luồng xử lý và context khó theo dõi hơn.

## Dùng coroutine để phối hợp nhiều lời gọi

Khi một field cần dữ liệu từ nhiều service độc lập, có thể dùng `coroutineScope` và `async` để chạy các tác vụ suspend đồng thời:

```kotlin
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

@QueryMapping
suspend fun bookDashboard(@Argument("id") id: String): BookDashboard =
    coroutineScope {
        val book = async { bookService.findByIdRequired(id) }
        val recommendations = async { recommendationService.forBook(id) }

        BookDashboard(
            book = book.await(),
            recommendations = recommendations.await()
        )
    }
```

`async` chỉ giúp chạy đồng thời hiệu quả khi các hàm được gọi thực sự suspend trên I/O bất đồng bộ hoặc chuyển sang dispatcher phù hợp. Nếu hai hàm đều gọi JDBC đồng bộ trên cùng coroutine context, chúng vẫn có thể block thread và không tự nhiên trở thành non-blocking.

`coroutineScope` bảo đảm các child coroutine thuộc vòng đời của operation. Khi một child thất bại, scope áp dụng structured concurrency và hủy các child còn lại theo quy tắc coroutine. Không dùng `GlobalScope` để khởi chạy công việc gắn với request GraphQL vì công việc đó có thể sống lâu hơn request và khó được hủy đúng lúc.

## Subscription với Kotlin Flow

Với Subscription, server cần phát nhiều kết quả theo thời gian. Kotlin `Flow<T>` là kiểu phù hợp để biểu diễn một luồng dữ liệu bất đồng bộ. Một controller có thể trả Flow trực tiếp:

```graphql
type OrderStatusUpdate {
  orderId: ID!
  status: String!
}

type Subscription {
  orderStatusChanged(orderId: ID!): OrderStatusUpdate!
}
```

```kotlin
import kotlinx.coroutines.flow.Flow

@Controller
class OrderSubscriptionController(
    private val orderEventService: OrderEventService
) {
    @SubscriptionMapping
    fun orderStatusChanged(
        @Argument("orderId") orderId: String
    ): Flow<OrderStatusUpdate> {
        return orderEventService.watch(orderId)
    }
}
```

`Flow` không giống `suspend fun` trả một giá trị. Suspend function tạo một kết quả cho lần thực thi; Flow biểu diễn chuỗi giá trị và được thu thập trong vòng đời subscription. Spring for GraphQL tích hợp Flow với Reactive Streams để chuyển từng phần tử thành một execution result.

Flow thường là cold stream: mỗi lần collect có thể tạo một subscription mới tới nguồn sự kiện. Nếu nguồn là callback API, có thể chuyển nó thành Flow bằng `callbackFlow` và giải phóng listener khi collector bị hủy:

```kotlin
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow

fun watchOrder(orderId: String): Flow<OrderStatusUpdate> = callbackFlow {
    val registration = eventSource.subscribe(orderId) { event ->
        trySend(event)
    }

    awaitClose {
        registration.close()
    }
}
```

`awaitClose` giữ Flow mở trong khi còn collector và chạy cleanup khi subscription kết thúc hoặc bị cancel. `eventSource` và kiểu `registration` là API minh họa của ứng dụng; cần kiểm tra kết quả `trySend` để xử lý khi channel đã đóng hoặc buffer đầy, đồng thời chọn chính sách buffer/overflow theo yêu cầu nghiệp vụ.

## Blocking I/O không tự biến thành non-blocking

Đây là điểm dễ hiểu nhầm nhất khi chuyển Java controller sang Kotlin coroutine. Từ khóa `suspend` không làm cho một hàm JDBC, JPA hoặc HTTP client blocking trở thành non-blocking.

Ví dụ không phù hợp trong ứng dụng reactive:

```kotlin
@QueryMapping
suspend fun book(@Argument("id") id: String): Book? {
    return blockingJpaRepository.findById(id).orElse(null)
}
```

Lời gọi repository vẫn chặn thread đang thực thi coroutine cho tới khi database trả kết quả. Nếu cần giữ thư viện blocking, hãy chuyển riêng phần đó sang dispatcher dành cho blocking I/O:

```kotlin
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@QueryMapping
suspend fun book(@Argument("id") id: String): Book? =
    withContext(Dispatchers.IO) {
        blockingJpaRepository.findById(id).orElse(null)
    }
```

`Dispatchers.IO` dành cho blocking I/O và giúp không chiếm event-loop thread. Với hệ thống tải cao, có thể dùng dispatcher riêng được tạo từ executor có giới hạn để cô lập công việc và đồng bộ giới hạn với connection pool. Không chuyển mọi đoạn code sang `Dispatchers.IO` nếu service đã non-blocking.

Với Spring MVC và JPA, cách triển khai đồng bộ có thể phù hợp nếu tải được kiểm soát. Không cần thêm coroutine chỉ để đổi cú pháp. Với WebFlux, ưu tiên WebClient, R2DBC hoặc API non-blocking khác; nếu bắt buộc dùng JDBC/JPA, offload blocking call và thiết kế transaction cẩn thận.

## Transaction, security context và cancellation

Coroutine có thể tạm dừng rồi tiếp tục trên thread khác. Vì vậy, không nên giả định mọi dữ liệu gắn với ThreadLocal luôn tồn tại giống nhau xuyên suốt một suspend function.

- **Transaction:** transaction JDBC/JPA truyền thống thường gắn với thread. Khi dùng `withContext` để đổi dispatcher, cần bảo đảm transaction bao quanh đúng đoạn blocking work. Với reactive transaction manager, dùng cơ chế transaction coroutine/reactive tương ứng của Spring và kiểm thử thực tế.
- **Security context:** nếu resolver cần principal hoặc quyền, lấy từ context đã được Spring Security thiết lập và dùng cơ chế context propagation tương thích. Không truyền quyền từ argument do client tự khai báo.
- **Reactor context:** khi tích hợp Reactor và coroutine qua `kotlinx-coroutines-reactor`, Reactor context có thể được đưa vào coroutine context. Kiểm thử việc truyền trace ID, security context hoặc tenant theo cấu hình thực tế của ứng dụng.
- **Cancellation:** khi client hủy operation hoặc kết nối kết thúc, coroutine và Flow cần được hủy theo vòng đời thực thi. Công việc con nên là structured child coroutine; nguồn callback cần được dọn bằng `finally` hoặc `awaitClose`.

Với tác vụ ghi dữ liệu, không nên khởi chạy coroutine nền rồi trả response trước khi biết kết quả nếu nghiệp vụ yêu cầu mutation hoàn tất đồng bộ với response. Công việc nền cần cơ chế hàng đợi, retry và theo dõi riêng.

## Xử lý lỗi trong suspend function

Exception được ném từ suspend function sẽ đi vào luồng xử lý lỗi của GraphQL. Có thể dùng `DataFetcherExceptionResolver` trong Spring for GraphQL để ánh xạ exception nghiệp vụ sang message, error code và metadata công khai.

Ví dụ controller ném lỗi khi không tìm thấy sách:

```kotlin
@QueryMapping
suspend fun book(@Argument("id") id: String): Book =
    bookService.findById(id)
        ?: throw BookNotFoundException(id)
```

Không trả stack trace, câu SQL hoặc thông tin hạ tầng trong error message. Nếu field nullable, lỗi có thể khiến field đó thành `null` trong khi các field khác vẫn có dữ liệu. Nếu field Non-Null, null có thể lan lên field cha theo quy tắc GraphQL.

Với Flow subscription, lỗi có thể xảy ra sau khi client đã nhận một số event. Khi nguồn phát lỗi, Flow kết thúc và GraphQL gửi thông tin lỗi/kết thúc operation theo transport. Nếu service tự retry, cần có giới hạn và bảo đảm không phát trùng sự kiện ngoài ý muốn.

## Kiểm thử coroutine controller

Có thể dùng `GraphQlTester` như khi kiểm thử controller Java. Việc method là `suspend` không làm thay đổi cách client gửi GraphQL document:

```kotlin
@Test
fun `book query returns requested book`() {
    graphQlTester.document("""
        query {
          book(id: "book-10") {
            id
            title
          }
        }
    """)
        .execute()
        .path("book.id")
        .entity(String::class.java)
        .isEqualTo("book-10")
}
```

Với service coroutine, có thể dùng `kotlinx-coroutines-test` và `runTest` để kiểm tra logic suspend một cách xác định. Test controller tích hợp vẫn cần chạy qua `GraphQlTester` để xác minh Spring phát hiện suspend function, bind argument và xử lý kết quả đúng.

Với Flow subscription, kiểm tra nhiều event, thứ tự phát, lỗi, hoàn tất và cancellation. Nếu Flow bọc callback, xác minh `awaitClose` thực sự giải phóng listener khi client hủy subscription.

Các trường hợp nên kiểm tra:

- Query và Mutation suspend trả kết quả đúng với SDL.
- Nullable và Non-Null mapping nhất quán giữa Kotlin và schema.
- Argument được bind đúng, kể cả input object.
- Exception được ánh xạ thành GraphQL error theo chính sách.
- Blocking I/O được chuyển khỏi event-loop khi ứng dụng dùng WebFlux.
- Transaction, security context và tracing được truyền đúng khi coroutine đổi dispatcher.
- Subscription Flow phát nhiều event và cleanup khi cancellation.
- Child coroutine không tiếp tục chạy ngoài vòng đời operation.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Spring không nhận diện suspend function | Thiếu coroutine integration cần thiết hoặc dependency không tương thích. | Kiểm tra `kotlinx-coroutines-reactor` và phiên bản Spring/Kotlin đang dùng. |
| Hàm `suspend` vẫn làm WebFlux chậm | Bên trong gọi JDBC/JPA blocking trên event loop. | Dùng API non-blocking hoặc `withContext(Dispatchers.IO)`/dispatcher riêng. |
| `Mono` được trả về thay vì giá trị mong đợi | Chưa chuyển đổi publisher sang coroutine hoặc service API không đúng kiểu. | Dùng extension `await...` phù hợp hoặc giữ nhất quán phong cách reactive. |
| Flow chỉ phát một event | Nguồn Flow hoàn tất sau event đầu tiên hoặc service chỉ phát một giá trị. | Kiểm tra nguồn sự kiện và vòng đời collector. |
| Listener vẫn tồn tại sau khi client rời đi | Flow từ callback không cleanup khi cancellation. | Dùng `callbackFlow` và `awaitClose` để gỡ listener. |
| Transaction mất khi coroutine đổi thread | Dựa vào transaction ThreadLocal của thread ban đầu. | Đặt transaction đúng ranh giới hoặc dùng reactive transaction integration phù hợp. |
| Principal/trace ID bị mất | Context không được truyền qua dispatcher hoặc Reactor bridge. | Cấu hình context propagation và kiểm thử với security/tracing thật. |
| Công việc vẫn chạy sau khi request kết thúc | Dùng coroutine detached như `GlobalScope` hoặc không xử lý cancellation. | Dùng structured concurrency và quản lý vòng đời child coroutine. |

## Ghi nhớ

Spring for GraphQL hỗ trợ `suspend` function trong annotated controller cho Query, Mutation và field mapping. Hàm suspend trả một kết quả đơn lẻ; Kotlin `Flow<T>` phù hợp với Subscription phát nhiều event. `@Argument`, `@Source`, `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` vẫn được dùng theo cách quen thuộc.

Coroutine giúp viết luồng bất đồng bộ gọn và có structured concurrency, nhưng không tự biến JDBC/JPA thành non-blocking. Hãy dùng API suspend/reactive thực sự khi có thể; nếu phải gọi blocking I/O, chuyển sang dispatcher phù hợp. Quản lý transaction, security context, cancellation, lỗi và cleanup của Flow để resolver hoạt động đúng trong suốt vòng đời GraphQL operation.
