# Kotlin suspend, Flow và ranh giới chuyển đổi với Reactor trong Spring WebFlux

## 1. Bức tranh tổng thể

Spring WebFlux xây dựng trên Reactive Streams và Reactor, thường dùng `Mono<T>` (0..1 phần tử) và `Flux<T>` (0..N phần tử). Kotlin cung cấp một cách viết bất đồng bộ khác: **coroutines**, `suspend fun` và `Flow<T>`. Spring Framework hỗ trợ cả hai mô hình, vì vậy một ứng dụng có thể dùng API Reactor ở repository/WebClient, nhưng trình bày API service/controller bằng Kotlin coroutines.

Điều quan trọng không phải chỉ đổi cú pháp, mà là **giữ ý nghĩa thực thi** khi đi qua ranh giới:

- Không chặn thread bằng `block()`, `runBlocking` hoặc `Future.get()` trong HTTP request.
- Không tự `subscribe()` hay tự tạo coroutine sống ngoài vòng đời request.
- Giữ trường hợp không có phần tử, lỗi và cancellation đúng nghĩa.
- Giữ demand/backpressure khi chuyển `Flux` ↔ `Flow`, hiểu các buffer có thể xuất hiện.
- Giữ Reactor Context, security/trace context và reactive transaction context khi tích hợp.
- Không vô tình chuyển một stream nhiều phần tử thành một collection chiếm nhiều memory.

Ví dụ luồng hợp lệ:

~~~text
HTTP GET /api/catalog/42
          |
          v
suspend Controller.get(id)
          |
          v
suspend CatalogService.find(id)
          |
          v
ReactorRepository.findById(id): Mono<Item>
          |
          v
Mono<Item>.awaitSingleOrNull(): Item?
          |
          v
Kotlin nullable result / HTTP 200 hoặc 404
~~~

Với nhiều phần tử:

~~~text
HTTP GET /api/catalog/stream
          |
          v
Controller.stream(): Flow<Item>
          |
          v
Service.list(): Flow<Item>
          |
          v
Repository.findAll(): Flux<Item>
          |
          v
Publisher.asFlow()
          |
          v
WebFlux adapt Flow -> Reactive Streams -> NDJSON response
~~~

Ở hai ví dụ, Spring WebFlux và adapters sẽ điều phối subscription/collection. Code nghiệp vụ không cần tự tạo một “công việc nền” riêng.

## 2. Đối chiếu Mono/Flux với suspend/Flow

Theo tài liệu Kotlin Coroutines của Spring Framework, cách ánh xạ thông thường là:

| Reactor API | Kotlin coroutines API | Ý nghĩa |
| --- | --- | --- |
| `Mono<T>` có một giá trị | `suspend fun f(): T` | Chờ một giá trị mà không block thread |
| `Mono<T>` có thể hoàn tất rỗng | `suspend fun f(): T?` | Vắng mặt được biểu diễn bằng nullable type |
| `Mono<Void>` / `Mono<Unit>` theo hợp đồng tác vụ | `suspend fun f()` | Chờ hoàn tất, có thể phát lỗi |
| `Flux<T>` | `fun f(): Flow<T>` | Chuỗi 0..N phần tử được thu thập bất đồng bộ |
| `Mono<List<T>>` | `suspend fun f(): List<T>` | Một collection đã được materialize |
| `Flux<T>` với nguồn stream | `Flow<T>` với nguồn stream | Không nhất thiết gom hết dữ liệu |

Cần phân biệt: `suspend fun f(): T` không phải là publisher. Nó là một hàm có thể **tạm dừng coroutine** khi cần chờ I/O. Ngược lại `Mono<T>` là một object mô tả tác vụ có thể được subscribe.

`Flow<T>` cũng không trực tiếp là một `org.reactivestreams.Publisher<T>`. Khi một Java API yêu cầu Publisher, cần adapter như `flow.asFlux()` hoặc `flow.asPublisher()`. Khi Kotlin code cần Flow từ một Flux, dùng `flux.asFlow()`.

### Khác biệt về API và cách viết

Reactor:

~~~kotlin
fun find(id: Long): Mono<ItemView> =
    repository.findById(id)
        .map { ItemView(it.id, it.name) }
~~~

Coroutines:

~~~kotlin
suspend fun find(id: Long): ItemView? =
    repository.findById(id)
        .awaitSingleOrNull()
        ?.let { ItemView(it.id, it.name) }
~~~

Hai cách đều có thể non-blocking khi repository dùng reactive driver. Hãy chọn API phù hợp hợp đồng của từng module, không chuyển đổi qua lại chỉ vì một cú pháp trông ngắn hơn.

## 3. Những thư viện tích hợp cần biết

| Dependency | Chức năng |
| --- | --- |
| `kotlinx-coroutines-core` | Coroutines, `suspend`, `Flow`, `coroutineScope`, `async` |
| `kotlinx-coroutines-reactive` | Adapter Reactive Streams: `Publisher.asFlow`, `Flow.asPublisher`, các hàm `Publisher.await...` |
| `kotlinx-coroutines-reactor` | Adapter Reactor: `Mono.awaitSingle`, `Mono.awaitSingleOrNull`, `Flow.asFlux`, `mono`, `flux`, `ReactorContext` |
| `spring-boot-starter-webflux` | WebFlux + Reactor + WebClient |
| `jackson-module-kotlin` | Decode/encode Kotlin data class với Jackson |
| `kotlin-reflect` | Hỗ trợ phản xạ Kotlin được nhiều thành phần Spring sử dụng |
| `kotlin("plugin.spring")` | Cho phép Spring proxy các Kotlin class được annotation phù hợp |

Với Spring Framework 6.2, tài liệu yêu cầu `kotlinx-coroutines-core` và `kotlinx-coroutines-reactor` trên classpath để hỗ trợ coroutine. Với Spring Data coroutine repositories, nên bổ sung cả `kotlinx-coroutines-reactive` vì các repository được xây dựng trên reactive repositories.

Spring Boot 3.5 quản lý các phiên bản Kotlin/Coroutines thông qua dependency management. Với Gradle, Boot plugin có cơ chế căn chỉnh Kotlin dependency version theo Kotlin Gradle plugin. Tránh tự trộn nhiều phiên bản `kotlinx-coroutines-*` không tương thích.

Một dependency chỉ giúp thích ứng API; nó **không** biến JDBC/JPA blocking thành non-blocking.

## 4. Từ Mono sang suspend bằng awaitSingle và awaitSingleOrNull

Các extension của `kotlinx.coroutines.reactor` thường dùng:

~~~kotlin
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull

suspend fun getRequired(id: Long): Item =
    repository.findById(id).awaitSingle()

suspend fun getOptional(id: Long): Item? =
    repository.findById(id).awaitSingleOrNull()
~~~

Hai hàm đều chờ bất đồng bộ, không giữ một thread chỉ để đợi kết quả.

### Khi Mono phát một phần tử

- `awaitSingle()` trả về phần tử.
- `awaitSingleOrNull()` trả về phần tử.
- Nếu Mono phát lỗi, cả hai ném exception tương ứng vào coroutine đang chờ.

### Khi Mono hoàn tất rỗng

- `awaitSingle()` ném `NoSuchElementException`.
- `awaitSingleOrNull()` trả `null`.

Do đó, với `findById` của reactive repository, `awaitSingleOrNull()` diễn đạt trường hợp “không tìm thấy” tốt hơn.

~~~kotlin
suspend fun findOr404(id: Long): Item =
    repository.findById(id).awaitSingleOrNull()
        ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)
~~~

### Khi Mono chỉ mang tín hiệu hoàn tất

Một `Mono<Void>` từ delete operation không phát phần tử; không dùng `awaitSingle()` vì nó sẽ báo empty. Có thể dùng:

~~~kotlin
suspend fun delete(id: Long) {
    repository.deleteById(id).awaitSingleOrNull()
}
~~~

Hoặc nếu gọi WebClient để nhận response không có body, dùng Kotlin extension `awaitBodilessEntity()` trên response spec. Mục tiêu là chờ thao tác hoàn tất hoặc phát lỗi, không đòi một giá trị giả.

## 5. Từ Flux sang Flow bằng asFlow()

`Publisher.asFlow()` nằm trong package `kotlinx.coroutines.reactive`:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.reactive.asFlow

fun names(): Flow<String> =
    repository.findAll()
        .asFlow()
        .map { it.name }
~~~

Điều cần nhớ:

1. `Flux<T>` có thể phát 0..N item, complete hoặc error.
2. `asFlow()` tạo adapter để một coroutine có thể collect chúng.
3. `Flow` mặc định là cold đối với các flow builders thông thường; collection mới thường bắt đầu tác vụ lại. Tuy nhiên, nếu Publisher nguồn là hot, adapter **không** tự biến nó thành nguồn replayable.
4. Lỗi từ Publisher xuất hiện trong coroutine collector.
5. Hủy coroutine collection sẽ hủy subscription tới Publisher trong khả năng adapter.
6. `Flow.map { ... }` nhận một suspending lambda, nên phép biến đổi có thể gọi một suspending function khác.

Ví dụ với thao tác suspend bên trong `Flow.map`:

~~~kotlin
fun enriched(): Flow<EnrichedItem> =
    repository.findAll()
        .asFlow()
        .map { item ->
            val score = scoringService.getScore(item.id) // suspend fun
            EnrichedItem(item.id, item.name, score)
        }
~~~

Vì Flow map xử lý tuần tự theo mặc định, nó đợi scoring cho mỗi item trước khi xử lý item tiếp theo. Nếu cần xử lý song song, phải thiết kế concurrency có giới hạn và xem xét thứ tự đầu ra.

### Flow được tạo khi nào và được chạy khi nào?

~~~kotlin
val flow = repository.findAll().asFlow()
~~~

Dòng này tạo object `Flow`. Dữ liệu chỉ được tiêu thụ khi collector hoạt động, ví dụ `collect` hoặc khi Spring WebFlux adapt Flow để ghi HTTP response.

Không thu thập Flow bằng `toList()` nếu mục tiêu là stream dữ liệu lớn/vô hạn, vì nó phải giữ toàn bộ item trong memory và chờ nguồn hoàn tất.

## 6. Từ Flow sang Flux hoặc Publisher

Khi cần truyền Flow vào một Java API yêu cầu Reactor Flux:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactor.asFlux
import reactor.core.publisher.Flux

fun sendToReactor(flow: Flow<Item>): Flux<Item> =
    flow.asFlux()
~~~

`Flow.asFlux()` chuyển Flow thành một Flux tuân thủ Reactive Streams. Flux mới là cold adapter: mỗi subscription sẽ collect Flow nguồn; khi subscriber hủy, collection tương ứng bị cancel.

Khi chỉ cần `Publisher<T>`:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactive.asPublisher
import org.reactivestreams.Publisher

fun asPublisher(items: Flow<Item>): Publisher<Item> =
    items.asPublisher()
~~~

Nếu hệ thống đã dùng Reactor thì ưu tiên `asFlux()` để tận dụng API Reactor.

### Lưu ý Flow<T?> có thể chứa null

Reactive Streams không cho phép `onNext(null)`. Các API adapter như `asFlux` có ràng buộc `T : Any`, tức element không nullable.

Vì thế:

~~~kotlin
val values: Flow<String?> = flowOf("a", null, "b")
~~~

không thể được adapt nguyên trạng thành `Flux<String?>` bằng `asFlux()`. Hãy xử lý null theo hợp đồng nghiệp vụ:

~~~kotlin
val nonNull: Flow<String> = values.filterNotNull()
val reactorFlux: Flux<String> = nonNull.asFlux()
~~~

Nếu null có ý nghĩa như một bản ghi riêng, thay nó bằng một DTO biểu diễn trạng thái vắng mặt thay vì phát null.

## 7. Từ suspend block sang Mono và Flux builders

Khi Java/Reactor API mong chờ Mono nhưng logic đang viết bằng `suspend fun`, dùng `mono { ... }`:

~~~kotlin
import kotlinx.coroutines.reactor.mono
import reactor.core.publisher.Mono

fun loadAsMono(id: Long): Mono<Item> = mono {
    suspendItemService.load(id) // suspend fun load(): Item
}
~~~

Builder `mono` tạo **cold Mono**: block coroutine chỉ bắt đầu khi có subscription. Nếu block trả `null`, Mono hoàn tất rỗng.

~~~kotlin
fun lookupAsMono(id: Long): Mono<Item> = mono {
    suspendItemService.find(id) // trả Item?
}
~~~

Khi muốn tạo Flux với logic coroutine:

~~~kotlin
import kotlinx.coroutines.reactor.flux
import reactor.core.publisher.Flux

fun countdown(): Flux<Int> = flux {
    send(3)
    send(2)
    send(1)
}
~~~

`send` phối hợp với demand và có thể suspend khi chưa có khả năng phát tiếp. Đây là cách bridge thích hợp cho coroutine producer, không phải “tự subscribe” vào một Flux hiện có.

### Đừng dùng runBlocking để chuyển suspend sang Mono

Sai trong request pipeline:

~~~kotlin
fun lookup(id: Long): Mono<Item> {
    val item = runBlocking { suspendItemService.load(id) }
    return Mono.just(item)
}
~~~

`runBlocking` chặn thread hiện tại đến khi coroutine hoàn tất. Nếu thread đó là Netty event loop, throughput có thể sụt giảm mạnh hoặc phát sinh deadlock/timeout.

Đúng:

~~~kotlin
fun lookup(id: Long): Mono<Item> = mono {
    suspendItemService.load(id)
}
~~~

Với tác vụ có giá trị đơn từ Reactor sang suspend, làm điều ngược lại bằng `awaitSingle()` hoặc `awaitSingleOrNull()`; không gọi `block()`.

## 8. Các ranh giới chuyển đổi: chọn adapter theo cardinality

| Nguồn | Đích | API | Lưu ý |
| --- | --- | --- | --- |
| `Mono<T>` | `T` trong suspend | `awaitSingle()` | Empty ném NoSuchElementException |
| `Mono<T>` | `T?` trong suspend | `awaitSingleOrNull()` | Empty trở thành null |
| `Flux<T>` | `Flow<T>` | `asFlow()` | Dữ liệu được collect theo nhu cầu |
| `Flow<T : Any>` | `Flux<T>` | `asFlux()` | Reactive Streams không cho phép null |
| `Flow<T : Any>` | `Publisher<T>` | `asPublisher()` | Không yêu cầu Reactor API ở caller |
| Suspend lambda trả `T?` | `Mono<T>` | `mono { ... }` | Cold, null thành empty |
| Coroutine producer | `Flux<T>` | `flux { send(...) }` | Cold, demand-aware |
| Reactor `Scheduler` | CoroutineDispatcher | `asCoroutineDispatcher()` | Có thể đóng dispatcher khi không còn cần |
| Reactor Context | Coroutine context | `ReactorContext` | Phải giữ cùng subscription/context |

Đừng chuyển `Flux<T>` sang `Mono<List<T>>` chỉ vì cần gọi một suspending function. Nếu muốn xử lý từng item, `Flux.asFlow()` và các operator Flow là đường chuyển đổi trực tiếp hơn.

## 9. Backpressure trong Reactor và Flow

Reactor/Reactive Streams dùng cơ chế `Subscription.request(n)`: downstream báo cho upstream biết số phần tử đang được yêu cầu. Flow là API push-based với **suspending emissions**: producer có thể tạm dừng khi consumer chưa sẵn sàng.

Khi `Flux.asFlow()`, adapter dùng một channel/buffer để giao tiếp giữa Reactive Streams và coroutine collector.

Theo tài liệu `kotlinx.coroutines.reactive`, `buffer` đặt trên Flow sau `asFlow()` ảnh hưởng đến kích thước prefetch/backpressure request:

~~~kotlin
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.reactive.asFlow

fun rows(): Flow<Row> =
    repository.streamRows()
        .asFlow()
        .buffer(16)
~~~

`buffer(16)` không có nghĩa “toàn bộ hệ thống chỉ giữ đúng 16 item”; driver, codec, các operator khác cũng có thể buffer. Nhưng nó cho một điểm điều tiết được kiểm soát trong adapter.

Ở chiều ngược lại:

~~~kotlin
val flux: Flux<Item> = itemFlow.asFlux()
~~~

`asFlux()` bridge subscriber demand tới việc collect Flow. Nếu subscriber chậm hoặc cancel, coroutine bên trong adapter phải phối hợp theo tín hiệu đó.

### Những thao tác làm mất lợi ích streaming

~~~kotlin
val all: List<Item> = repository.findAll()
    .asFlow()
    .toList()
~~~

`toList()` phải giữ toàn bộ kết quả hữu hạn trong memory. Chỉ dùng khi nghiệp vụ cần toàn bộ collection. Với nguồn vô hạn, `toList()` không hoàn tất.

Khi trả HTTP, media type cũng quan trọng:

- `application/json` thường tạo JSON array hữu hạn.
- `application/x-ndjson` thích hợp cho nhiều JSON record liên tiếp.
- `text/event-stream` thích hợp với SSE.

Đừng coi việc return Flow là bảo đảm bất kỳ proxy hoặc client nào cũng hiển thị từng phần tử ngay lập tức; cần kiểm tra encoder, flush và buffering toàn tuyến.

## 10. Cancellation và error propagation

Trong coroutines, cancellation thông thường biểu diễn bằng `CancellationException` và `Job` bị cancel. Trong Reactor, subscriber có thể gọi `cancel()`. Các adapter chính thức nối hai khái niệm này:

- Khi coroutine bị hủy lúc chờ `Mono.awaitSingle()`, adapter hủy subscription Reactor đang chờ.
- Khi Flux subscriber hủy `Flow.asFlux()`, coroutine collect Flow tương ứng bị cancel.
- Khi collector dừng `Publisher.asFlow()`, subscription Publisher được cancel theo adapter.
- Khi Reactor phát `onError`, suspending await hoặc collector nhận exception tương ứng.
- Khi coroutine throw exception (ngoài cancellation), `mono` hoặc `flux` phát `onError`.

Ví dụ không nuốt cancellation:

~~~kotlin
suspend fun findSafe(id: Long): Item? {
    return try {
        repository.findById(id).awaitSingleOrNull()
    } catch (e: CancellationException) {
        throw e
    } catch (e: DataAccessException) {
        logger.warn("Database request failed", e)
        throw e
    }
}
~~~

Đây là snippet minh họa, cần import exception và logger tương ứng trong dự án thực tế. Không biến mọi lỗi thành null, vì như vậy lỗi database sẽ bị hiểu sai thành “không tìm thấy”.

### Dùng timeout đúng cách

~~~kotlin
suspend fun getWithDeadline(id: Long): Item? =
    withTimeout(2_000) {
        repository.findById(id).awaitSingleOrNull()
    }
~~~

`withTimeout` hủy coroutine khi hết thời gian; adapter sẽ yêu cầu cancel subscription đang đợi. Timeout ở mức ứng dụng không thay thế timeout kết nối/pool của driver.

Không catch mọi `Exception` rồi trả giá trị mặc định khi nó bao gồm cancellation. Nếu cần cleanup tài nguyên, dùng `try/finally` và hiểu `withContext(NonCancellable)` chỉ nên dùng cho cleanup rất ngắn, có kiểm soát.

## 11. Structured concurrency thay GlobalScope

Một lợi ích của Kotlin coroutines là `coroutineScope` và `supervisorScope` để quản lý các tác vụ con. Trong một HTTP request, các tác vụ con nên có vòng đời gắn với request:

~~~kotlin
suspend fun dashboard(userId: Long): Dashboard = coroutineScope {
    val profile = async { profileClient.load(userId) }
    val permissions = async { permissionClient.load(userId) }

    Dashboard(
        profile = profile.await(),
        permissions = permissions.await()
    )
}
~~~

Khi một child thất bại trong `coroutineScope` thông thường, scope sẽ cancel các child còn lại rồi truyền lỗi lên caller. Khi request/coroutine cha bị hủy, các child cũng bị hủy.

Tránh:

~~~kotlin
GlobalScope.launch {
    auditService.writeAudit()
}
~~~

Đây là fire-and-forget task ngoài vòng đời request; cancellation, error, transaction và tracing context có thể bị tách. Nếu nghiệp vụ thực sự cần background job, dùng queue/message broker hoặc một `CoroutineScope` cấp ứng dụng được quản lý lifecycle, có error handling và chính sách shutdown rõ ràng.

### Khi nào cần concurrency?

`Flow.map { suspendOperation(it) }` xử lý từng phần tử theo tuần tự mặc định. Nếu muốn tăng concurrency, dùng các operator Flow có giới hạn rõ ràng hoặc tạo nhóm tác vụ trong `coroutineScope` và đợi chúng. Đừng tạo hàng nghìn `async` không giới hạn khi DB pool hoặc downstream không chịu được tải.

## 12. Reactor Context và CoroutineContext

Reactor giữ metadata request/subscription bằng `reactor.util.context.Context`. Kotlin coroutines dùng `CoroutineContext`. `kotlinx-coroutines-reactor` cung cấp `ReactorContext` để bridge.

Ví dụ minh họa:

~~~kotlin
import kotlin.coroutines.coroutineContext
import kotlinx.coroutines.reactor.ReactorContext
import kotlinx.coroutines.reactor.mono
import reactor.util.context.Context

val result: Mono<String> = mono {
    val reactorContext = coroutineContext[ReactorContext]?.context
    reactorContext?.getOrDefault("traceId", "missing") ?: "missing"
}.contextWrite(Context.of("traceId", "req-42"))
~~~

Khi subscribe `result`, Mono phát:

~~~text
req-42
~~~

Theo tài liệu kotlinx.coroutines, các adapter `mono`, `flux`, `asFlow`, `asFlux` và các hàm await có tích hợp ReactorContext, nhưng mức độ propagation của MDC/ThreadLocal, security context và observation còn phụ thuộc cấu hình framework, Micrometer Context Propagation và cách tạo coroutine.

Không tự giả định rằng ThreadLocal trong một thread event loop sẽ tự đi theo mọi coroutine/scheduler. Để lấy security principal, dùng cơ chế reactive/coroutine-aware của Spring Security; để tracing, cấu hình context propagation phù hợp phiên bản Spring/Micrometer và kiểm thử end-to-end.

## 13. WebFlux controller hỗ trợ suspend và Flow trực tiếp

Spring WebFlux annotated controllers có thể khai báo:

~~~kotlin
@RestController
@RequestMapping("/api/users")
class UserController(private val service: UserService) {

    @GetMapping("/{id}")
    suspend fun get(@PathVariable id: Long): UserView =
        service.find(id)
            ?: throw ResponseStatusException(HttpStatus.NOT_FOUND)

    @GetMapping
    fun all(): Flow<UserView> = service.findAll()
}
~~~

Không cần đổi `Flow` sang `Flux` chỉ để return từ annotated controller: Spring Framework có adapter cho coroutine return types.

Với functional endpoints, Spring WebFlux còn có `coRouter { }` DSL và các handler suspending. Không trộn lẫn cách viết annotated controller với coRouter trong cùng ví dụ nếu không cần; chọn phong cách theo cấu trúc ứng dụng.

### Mono/Flux vẫn là API hợp lệ trong Kotlin

~~~kotlin
@GetMapping("/reactor")
fun reactorEndpoint(): Flux<UserView> = service.findAll().asFlux()
~~~

Spring WebFlux chấp nhận cả Reactor types lẫn coroutine types. Không có yêu cầu phải chuyển toàn bộ code Kotlin sang Flow; các thư viện/nhóm đã có Reactor pipeline ổn định có thể tiếp tục dùng Reactor ở ranh giới phù hợp.

## 14. WebClient: awaitBody, awaitBodyOrNull và bodyToFlow

Kotlin extensions của Spring WebFlux giúp client gọi một API theo coroutine style:

~~~kotlin
import org.springframework.web.reactive.function.client.awaitBody
import org.springframework.web.reactive.function.client.awaitBodyOrNull
import org.springframework.web.reactive.function.client.bodyToFlow

class CatalogRemoteClient(private val webClient: WebClient) {

    suspend fun get(id: Long): RemoteItem =
        webClient.get()
            .uri("/items/{id}", id)
            .retrieve()
            .awaitBody<RemoteItem>()

    suspend fun optionalResponse(): RemoteItem? =
        webClient.get()
            .uri("/optional")
            .retrieve()
            .awaitBodyOrNull<RemoteItem>()

    fun stream(): Flow<RemoteItem> =
        webClient.get()
            .uri("/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .retrieve()
            .bodyToFlow<RemoteItem>()
}
~~~

Đây là đoạn minh họa dành cho WebClient đã được cấu hình base URL và các kiểu DTO `RemoteItem` tương ứng, không phải project độc lập.

Lưu ý quan trọng: `awaitBodyOrNull()` xử lý **body rỗng**, không tự động biến HTTP 404 thành null. `retrieve()` mặc định coi response 4xx/5xx là lỗi. Nếu hợp đồng endpoint dùng 404 cho “không có record”, cần xử lý HTTP status một cách tường minh, thay vì nhầm giữa response empty và HTTP 404.

### Gửi Flow làm request body

WebClient RequestBodySpec có overload nhận Publisher. Flow không trực tiếp triển khai Publisher nên cần bridge:

~~~kotlin
fun send(events: Flow<Event>): Mono<Void> =
    webClient.post()
        .uri("/events")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(events.asFlux(), Event::class.java)
        .retrieve()
        .bodyToMono(Void::class.java)
~~~

Nếu caller đang ở suspend context, có thể dùng `awaitBodilessEntity()` hoặc `awaitSingleOrNull()` trên Mono<Void>, tùy response contract.

### Không tự subscribe request body

Sai:

~~~kotlin
events.asFlux().subscribe()
return webClient.post().uri("/events").retrieve().bodyToMono(Void::class.java)
~~~

Publisher đã bị consume độc lập; HTTP request chưa chắc chứa body và lỗi không còn được nối đúng pipeline. Cách đúng là truyền Publisher vào `body(...)` và return/await response.

## 15. Spring Data CoroutineCrudRepository và reactive database

Spring Data R2DBC có coroutine repositories built trên reactive repositories. Có thể khai báo:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import org.springframework.data.repository.kotlin.CoroutineCrudRepository

interface BookRepository : CoroutineCrudRepository<BookEntity, Long> {
    fun findByAuthor(author: String): Flow<BookEntity>
}
~~~

Các phương thức điển hình:

- `suspend fun findById(id): BookEntity?`: một bản ghi hoặc null.
- `fun findAll(): Flow<BookEntity>`: nhiều bản ghi.
- `suspend fun save(entity): BookEntity`: lưu một bản ghi.
- `suspend fun deleteById(id)`: chờ thao tác xóa.

Tên chính xác và kiểu nullable của method tuân theo API Spring Data/phiên bản sử dụng. Với custom query methods, khai báo `suspend` hoặc return `Flow` để bảo toàn CoroutineContext; method thông thường `fun getUser(): User` trong repository coroutine có thể chạy blocking và không có context propagation, nên tránh.

Đây là snippet triển khai bên ngoài project demo ở mục 18: cần `spring-boot-starter-data-r2dbc`, một R2DBC driver và entity có mapping tương ứng. Không thể chỉ thêm `CoroutineCrudRepository` mà tiếp tục dùng JPA/JDBC rồi tuyên bố hệ thống non-blocking.

### Từ legacy ReactiveCrudRepository sang service suspend

Nếu đang có repository Reactor ổn định:

~~~kotlin
class BookService(private val repository: ReactiveCrudRepository<Book, Long>) {

    suspend fun find(id: Long): Book? =
        repository.findById(id).awaitSingleOrNull()

    fun all(): Flow<Book> = repository.findAll().asFlow()
}
~~~

Đây là một ranh giới chuyển đổi hợp lệ, không cần rewrite repository chỉ vì controller được viết bằng Kotlin coroutines.

## 16. Transaction reactive khi dùng coroutines

Một transaction reactive gắn với reactive transaction manager và Reactor Context, không đơn thuần là một ThreadLocal của thread đang chạy.

Spring Framework 6.2 ghi rõ hỗ trợ transaction cho coroutines qua API **programmatic reactive transaction management**:

- `TransactionalOperator.executeAndAwait { ... }` dành cho suspending block.
- `Flow<T>.transactional(operator)` dành cho chuỗi Flow.

Ví dụ minh họa:

~~~kotlin
import org.springframework.transaction.reactive.TransactionalOperator
import org.springframework.transaction.reactive.executeAndAwait

class PaymentService(
    private val operator: TransactionalOperator,
    private val payments: CoroutinePaymentRepository,
    private val ledger: CoroutineLedgerRepository
) {
    suspend fun create(input: NewPayment): Payment =
        operator.executeAndAwait {
            val payment = payments.save(input.toEntity())
            ledger.save(LedgerEntry(paymentId = payment.id))
            payment
        } ?: error("Transaction completed without a value")
}
~~~

Ví dụ này mô tả hai repository coroutine và entity của một module thanh toán, không thuộc project demo. `executeAndAwait` là suspending extension và trả giá trị nullable theo hợp đồng API; nên xác định rõ trường hợp không có giá trị.

Với Flow:

~~~kotlin
import org.springframework.transaction.reactive.transactional

fun updateAll(): Flow<BookEntity> =
    repository.findAll()
        .map { item -> repository.save(item.copy(active = true)) }
        .transactional(operator)
~~~

Toán tử `Flow.map` ở đây có thể gọi suspending save.

Những điều cần tránh:

- Gọi `runBlocking` trong transaction reactive.
- Tự subscribe Publisher bên trong transaction và tạo subscription riêng.
- Dùng Spring JDBC/JPA với giả định rằng reactive transaction manager sẽ quản lý nó.
- Đặt một Flow vô hạn trong transaction kéo dài vô hạn, giữ DB connection.
- Xem một HTTP call tới service khác như một phần của DB transaction có thể rollback tự động.

Cancellation một reactive transaction có thể dẫn đến rollback; đừng vô tình cắt một transaction Flux bằng `take(1)` hoặc `first()` nếu các side effect phải hoàn tất toàn bộ. Cần kiểm thử rollback cả khi exception và khi cancellation.

## 17. Blocking code, context switch và lỗi chuyển đổi

### Blocking không được chữa bằng suspend modifier

Sai:

~~~kotlin
suspend fun load(): User = jdbcDao.findUser()
~~~

Hàm này được khai báo `suspend` nhưng lời gọi JDBC vẫn blocking.

Nếu chưa chuyển hệ thống sang reactive driver, có thể cô lập blocking code như một bước chuyển tiếp:

~~~kotlin
suspend fun loadLegacy(): User = withContext(Dispatchers.IO) {
    jdbcDao.findUser()
}
~~~

Giải pháp này vẫn tiêu thụ thread trong lúc I/O chặn, phải đo đạc và giới hạn concurrency. Không có reactive backpressure thực thụ đến thư viện JDBC; transaction imperative cũng không tự đồng bộ với R2DBC transaction.

### Đừng gọi await lên Flux khi cần toàn bộ stream

Nếu bạn chỉ gọi `awaitFirst()` trên một Flux, coroutine nhận phần tử đầu và có thể cancel các phần tử còn lại. Điều này hợp lệ khi mục tiêu thật sự là “first”, nhưng sai nếu bạn cần xử lý toàn bộ kết quả hoặc side effect của một transaction.

Dùng `asFlow()` và `collect`/operator phù hợp cho 0..N; nếu thật sự cần collection hữu hạn, dùng `toList()` có chủ đích và kiểm soát kích thước.

### Không gọi Flow.collect trong controller chỉ để gửi response

Sai:

~~~kotlin
@GetMapping("/stream")
suspend fun stream(): List<Event> =
    eventService.events().toList()
~~~

Đoạn này làm mất streaming và giữ toàn bộ kết quả. Cách đúng là:

~~~kotlin
@GetMapping("/stream", produces = [MediaType.APPLICATION_NDJSON_VALUE])
fun stream(): Flow<Event> = eventService.events()
~~~

## 18. Ví dụ hoàn chỉnh: Spring Boot 3.5 + Kotlin 2.1 + Java 17

Dự án sau minh họa **hai phía của ranh giới** mà không cần database hoặc API ngoài:

- Tầng nguồn viết bằng Reactor (`Mono`/`Flux`) và lưu danh sách mẫu bất biến.
- Service coroutine gọi `awaitSingleOrNull()`, `awaitSingle()` và `asFlow()`.
- Controller dùng `suspend fun` và `Flow<T>` trực tiếp.
- Hai endpoint tương thích Reactor dùng `mono { ... }` và `Flow.asFlux()`.
- WebTestClient test mapping, null/404, JSON array, NDJSON content type; StepVerifier test tín hiệu adapter.

### 18.1. Cấu trúc project

~~~text
kotlin-reactor-bridge/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/kotlin/com/example/bridge/
    │   └── BridgeApplication.kt
    └── test/kotlin/com/example/bridge/
        └── BridgeApplicationTests.kt
~~~

### 18.2. settings.gradle.kts

~~~kotlin
rootProject.name = "kotlin-reactor-bridge"
~~~

### 18.3. build.gradle.kts

~~~kotlin
plugins {
    kotlin("jvm") version "2.1.20"
    kotlin("plugin.spring") version "2.1.20"
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactive")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

Dùng JDK 17+ và Gradle phiên bản tương thích với Kotlin Gradle plugin 2.1.20; Gradle 8.12 là một lựa chọn phù hợp. Trong dự án thực tế nên commit Gradle Wrapper (`gradlew`, `gradlew.bat` và wrapper files) để thống nhất phiên bản cho cả nhóm.

Không pin phiên bản từng dependency Kotlin/Coroutines riêng lẻ khi đã dùng BOM của Spring Boot. Plugin `kotlin("plugin.spring")` cho phép Spring tạo proxy cho các class Kotlin cần proxying.

### 18.4. BridgeApplication.kt

~~~kotlin
package com.example.bridge

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.reactive.asFlow
import kotlinx.coroutines.reactor.asFlux
import kotlinx.coroutines.reactor.awaitSingle
import kotlinx.coroutines.reactor.awaitSingleOrNull
import kotlinx.coroutines.reactor.mono

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.http.MediaType
import org.springframework.http.ResponseEntity
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

import reactor.core.publisher.Flux
import reactor.core.publisher.Mono

@SpringBootApplication
class BridgeApplication

fun main(args: Array<String>) {
    runApplication<BridgeApplication>(*args)
}

data class CatalogItem(
    val id: Long,
    val name: String
)

// Tầng này cố ý dùng Reactor API để minh họa interop.
// Dữ liệu chỉ là ví dụ in-memory; không phải repository R2DBC.
@Component
class ReactorCatalog {
    private val items = listOf(
        CatalogItem(1, "Kotlin"),
        CatalogItem(2, "Reactor"),
        CatalogItem(3, "WebFlux")
    )

    fun find(id: Long): Mono<CatalogItem> = Mono.defer {
        Mono.justOrEmpty(items.firstOrNull { it.id == id })
    }

    fun all(): Flux<CatalogItem> = Flux.defer {
        Flux.fromIterable(items)
    }

    fun count(): Mono<Long> = all().count()
}

@Service
class CatalogService(private val source: ReactorCatalog) {
    suspend fun find(id: Long): CatalogItem? =
        source.find(id).awaitSingleOrNull()

    fun list(): Flow<CatalogItem> = source.all().asFlow()

    suspend fun count(): Long =
        source.count().awaitSingle()
}

@RestController
@RequestMapping("/api/catalog")
class CatalogController(private val service: CatalogService) {

    // Mono<T> -> suspend T? -> HTTP 200 hoặc 404
    @GetMapping("/{id}")
    suspend fun get(@PathVariable id: Long): ResponseEntity<CatalogItem> {
        val item = service.find(id)
        return if (item == null) {
            ResponseEntity.notFound().build()
        } else {
            ResponseEntity.ok(item)
        }
    }

    // Flux<T> -> Flow<T> -> JSON array
    @GetMapping(produces = [MediaType.APPLICATION_JSON_VALUE])
    fun list(): Flow<CatalogItem> = service.list()

    // Flux<T> -> Flow<T> -> NDJSON stream
    @GetMapping(
        "/stream",
        produces = [MediaType.APPLICATION_NDJSON_VALUE]
    )
    fun stream(): Flow<CatalogItem> = service.list()

    // Mono<Long> -> suspend Long -> JSON object
    @GetMapping("/count")
    suspend fun count(): Map<String, Long> =
        mapOf("count" to service.count())

    // suspend call -> Mono<ResponseEntity<T>> cho caller Reactor
    @GetMapping("/bridge/mono/{id}")
    fun bridgeMono(
        @PathVariable id: Long
    ): Mono<ResponseEntity<CatalogItem>> = mono {
        val item = service.find(id)
        if (item == null) {
            ResponseEntity.notFound().build<CatalogItem>()
        } else {
            ResponseEntity.ok(item)
        }
    }

    // Flow<T> -> Flux<T> cho caller Reactor
    @GetMapping(
        "/bridge/flux",
        produces = [MediaType.APPLICATION_NDJSON_VALUE]
    )
    fun bridgeFlux(): Flux<CatalogItem> =
        service.list().asFlux()
}
~~~

Giải thích:

- `Mono.defer` và `Flux.defer` làm rõ yếu tố cold/lazy ở nguồn Reactor.
- `find` dùng `awaitSingleOrNull` vì record có thể không tồn tại.
- `count` dùng `awaitSingle` vì `Flux.count()` luôn phát một Long nếu nguồn hoàn tất bình thường.
- Endpoint `list` trả Flow; WebFlux tự adapt khi encode response.
- Endpoint `bridgeMono` cho thấy `mono { }` chuyển logic suspend về API Reactor mà không block.
- Endpoint `bridgeFlux` cho thấy `Flow.asFlux()`.
- Không gọi `subscribe()` hay `runBlocking`.
- Danh sách chỉ đọc nên test deterministic và không cần DB.

### 18.5. BridgeApplicationTests.kt

~~~kotlin
package com.example.bridge

import kotlinx.coroutines.reactor.asFlux

import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.http.MediaType
import org.springframework.test.web.reactive.server.WebTestClient

import reactor.test.StepVerifier

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BridgeApplicationTests {

    @Autowired
    lateinit var client: WebTestClient

    @Autowired
    lateinit var service: CatalogService

    @Test
    fun suspendEndpointReturnsItem() {
        client.get()
            .uri("/api/catalog/2")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$.name").isEqualTo("Reactor")
    }

    @Test
    fun monoEmptyMapsTo404() {
        client.get()
            .uri("/api/catalog/999")
            .exchange()
            .expectStatus().isNotFound
    }

    @Test
    fun countAwaitsMono() {
        client.get()
            .uri("/api/catalog/count")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$.count").isEqualTo(3)
    }

    @Test
    fun flowReturnsJsonArray() {
        client.get()
            .uri("/api/catalog")
            .exchange()
            .expectStatus().isOk
            .expectBody()
            .jsonPath("$[0].name").isEqualTo("Kotlin")
            .jsonPath("$[2].name").isEqualTo("WebFlux")
    }

    @Test
    fun bridgeMonoKeepsNotFoundSemantics() {
        client.get()
            .uri("/api/catalog/bridge/mono/999")
            .exchange()
            .expectStatus().isNotFound
    }

    @Test
    fun fluxEndpointUsesNdjsonMediaType() {
        client.get()
            .uri("/api/catalog/bridge/flux")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
    }

    @Test
    fun flowToFluxPreservesSignals() {
        StepVerifier.create(service.list().asFlux().map { it.name })
            .expectNext("Kotlin", "Reactor", "WebFlux")
            .verifyComplete()
    }
}
~~~

Chạy:

~~~bash
gradle test
gradle bootRun
~~~

Hoặc dùng `./gradlew test` và `./gradlew bootRun` khi đã tạo Gradle Wrapper.

Sau khi chạy server, thử:

~~~bash
curl -i http://localhost:8080/api/catalog/2
curl -i http://localhost:8080/api/catalog/999
curl -i http://localhost:8080/api/catalog/count
curl -i http://localhost:8080/api/catalog
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/catalog/stream
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/catalog/bridge/flux
~~~

Response GET `/api/catalog/2`:

~~~json
{"id":2,"name":"Reactor"}
~~~

Response GET `/api/catalog/count`:

~~~json
{"count":3}
~~~

GET `/api/catalog/999` trả HTTP 404.

GET `/api/catalog` trả JSON array:

~~~json
[
  {"id":1,"name":"Kotlin"},
  {"id":2,"name":"Reactor"},
  {"id":3,"name":"WebFlux"}
]
~~~

GET `/api/catalog/stream` trả các record NDJSON (mỗi dòng là JSON riêng):

~~~text
{"id":1,"name":"Kotlin"}
{"id":2,"name":"Reactor"}
{"id":3,"name":"WebFlux"}
~~~

JSON serializer có thể thay đổi khoảng trắng/formatting, nhưng giá trị trường và số lượng item như trên. Ví dụ chạy trong môi trường đã tải đủ dependency Gradle và có cổng 8080 khả dụng.

## 19. Quy trình tích hợp thực tế giữa Kotlin và thư viện Java Reactor

Khi nhận một module Java trả `Mono`/`Flux`, đừng chuyển toàn bộ codebase ngay lập tức. Dùng ranh giới rõ ràng:

1. **Xác định cardinality:** một item hay nhiều item? Mono empty có phải kết quả hợp lệ không?
2. **Chọn API public:** service Kotlin trả suspend T/T? hoặc Flow<T>, hay giữ Reactor types vì Java caller cần?
3. **Chuyển một lần ở boundary:** awaitSingle/awaitSingleOrNull hoặc asFlow/asFlux đúng kiểu.
4. **Giữ lifecycle:** không tách subscription, không GlobalScope launch cho request work.
5. **Xử lý lỗi tường minh:** not found khác backend error, cancellation không phải lỗi nghiệp vụ.
6. **Kiểm soát backpressure:** buffer, concurrency, data size và HTTP media type.
7. **Xác định transaction context:** reactive transaction/CoroutineContext cần giữ xuyên các adapter.
8. **Test hai phía:** StepVerifier cho tín hiệu Reactor, coroutine test cho suspending logic, WebTestClient cho HTTP.
9. **Đo production:** memory, thread count, database pool, request timeout, cancellation và downstream latency.
10. **Giới hạn số lần bridge:** tránh chuỗi asFlow → asFlux → asFlow không cần thiết làm code khó hiểu.

## 20. Những lỗi phổ biến

1. **Dùng `Mono.block()` trong suspend function:** vẫn blocking. Dùng `awaitSingle()`.
2. **Dùng `runBlocking` trong WebFlux controller:** chặn thread xử lý HTTP. Dùng `suspend fun`.
3. **Dùng `awaitSingle()` với Mono có thể empty:** có thể ném NoSuchElementException. Dùng `awaitSingleOrNull()`.
4. **Biến mọi HTTP 404 thành null bằng cách nghĩ awaitBodyOrNull tự xử lý 404:** sai; cần xử lý response status.
5. **Coi Flow là Publisher:** Flow không trực tiếp triển khai Reactive Streams Publisher; dùng `asFlux()`/`asPublisher()`.
6. **Dùng `Flux.asFlow()` nhưng thiếu kotlinx-coroutines-reactive:** import không hoạt động.
7. **Dùng `Flow.asFlux()` nhưng thiếu kotlinx-coroutines-reactor:** không có adapter tương ứng.
8. **Cố phát Flow<T?> qua Flux:** Reactive Streams không chấp nhận null. Lọc/encode null.
9. **Mất empty/error khi bridge:** phải kiểm tra null, exception và complete.
10. **Gọi subscribe riêng trong service:** tạo subscription khác, làm mất coupling với HTTP request và transaction.
11. **Gọi collect/toList trên Flow vô hạn:** không hoàn tất và có thể dùng memory không giới hạn.
12. **Cho rằng Flow là streaming HTTP trong mọi media type:** JSON array có thể buffer; dùng NDJSON/SSE phù hợp.
13. **Cho rằng suspend làm JDBC/JPA thành non-blocking:** JDBC vẫn blocking.
14. **Dùng withContext(Dispatchers.IO) cho mọi lệnh R2DBC:** không cần, làm chuyển context/thread không có lợi rõ ràng.
15. **Tạo GlobalScope.launch trong controller:** side-effect chạy ngoài lifecycle request.
16. **Catch Exception rồi nuốt CancellationException:** làm cancellation bị trì hoãn hoặc che mất.
17. **Gọi awaitFirst trên Flux khi cần tất cả phần tử:** các phần tử còn lại có thể bị cancel.
18. **Dùng Flow.map với suspend call mà tưởng chạy song song:** mặc định map tuần tự.
19. **flatMapMerge concurrency quá cao:** có thể quá tải downstream/DB pool.
20. **Không truyền ReactorContext khi tích hợp thủ công:** transaction/security/tracing metadata có thể mất.
21. **Dùng transaction imperative cho R2DBC coroutine:** reactive manager/context mới phù hợp.
22. **Giữ transaction qua Flow dài hoặc vô hạn:** có nguy cơ giữ connection và lock quá lâu.
23. **Tự retry write không idempotent sau cancellation:** có thể gây side effect trùng.
24. **Test chỉ kiểm giá trị một item:** bỏ sót empty/error/cancel/order/media-type.
25. **Chạy Kotlin và Reactor adapters ở nhiều module với coroutines versions khác nhau:** dễ gặp lỗi runtime hoặc hành vi không mong đợi; dùng BOM đồng nhất.

## 21. Checklist kiểm tra một ranh giới Kotlin ↔ Reactor

- Biết rõ đầu vào là Mono, Flux, Flow hay suspending function chưa?
- Đã chọn cách chuyển phù hợp với 0..1 hay 0..N chưa?
- Mono có thể complete rỗng không? Đã dùng nullable type nếu cần chưa?
- Flow có phát nullable item không? Có xử lý trước asFlux chưa?
- Có dùng adapter chính thức từ kotlinx-coroutines-reactive/reactor chưa?
- Có gọi block, runBlocking, join hoặc subscribe trong HTTP request không?
- Caller có thể cancel request và dừng công việc upstream không?
- Error có được propagate hoặc map đúng semantics không?
- Có buffer/prefetch/concurrency phù hợp không?
- Có đang biến stream thành List vô tình không?
- WebFlux response media type có đúng JSON/NDJSON/SSE không?
- Có dùng CoroutineCrudRepository hoặc reactive driver thực sự không?
- Reactive transaction có cùng context qua các thao tác không?
- Có giữ ReactorContext và context propagation cần thiết không?
- Có test suspend endpoint, Flow endpoint, adapter Mono/Flux và empty/cancel không?
- Có kiểm tra logger/tracing/security khi pipeline chuyển scheduler không?

## 22. Câu hỏi tự kiểm tra

**1.** Mono<T> tương ứng với Kotlin API nào? Thường là suspend fun trả T, hoặc T? khi có thể empty.

**2.** Flux<T> tương ứng với Kotlin API nào? Flow<T> cho chuỗi nhiều phần tử.

**3.** Mono.empty() với awaitSingle() gây gì? NoSuchElementException.

**4.** Mono.empty() với awaitSingleOrNull() trả gì? null.

**5.** Flux.asFlow() nằm ở module nào? kotlinx-coroutines-reactive.

**6.** Flow.asFlux() nằm ở module nào? kotlinx-coroutines-reactor.

**7.** Có dùng Flow.asFlux() trực tiếp với Flow<String?> không? Không, vì Reactive Streams cấm onNext(null).

**8.** mono { ... } chạy ngay khi được tạo không? Không, nó tạo cold Mono bắt đầu coroutine khi subscribe.

**9.** Khi subscriber cancel Flux từ Flow.asFlux thì sao? Coroutine collect nguồn được cancel qua adapter.

**10.** Flow.map có thể gọi suspend function không? Có, nhưng xử lý tuần tự theo mặc định.

**11.** Flow.asFlow().buffer(16) để làm gì? Điều tiết kích thước buffer/prefetch của bridge Publisher → Flow.

**12.** WebFlux có nhận suspend controller và Flow return type trực tiếp không? Có, khi có dependencies coroutine phù hợp.

**13.** awaitBodyOrNull tự biến HTTP 404 thành null không? Không; retrieve() vẫn xử lý 4xx/5xx như lỗi theo mặc định.

**14.** Khi nào cần TransactionalOperator.executeAndAwait? Khi muốn transaction reactive bao một suspending block.

**15.** Vì sao GlobalScope.launch trong controller không phù hợp? Nó tách lifecycle, cancellation và context khỏi HTTP request.

**16.** suspend fun gọi JDBC trực tiếp có trở thành non-blocking không? Không, JDBC vẫn blocking.

**17.** Có phải mọi return Flow đều stream từng JSON record tức thì không? Không, phụ thuộc media type, codec và buffering.

**18.** Cần test những tín hiệu nào khi bridge? Value, empty, error, complete, cancellation và demand/backpressure khi có streaming.

**Ghi nhớ:** Kotlin coroutines và Reactor có thể phối hợp an toàn, miễn là xác định rõ ranh giới. Dùng awaitSingle/awaitSingleOrNull cho Mono, asFlow cho Flux, asFlux/asPublisher cho Flow và mono/flux builders khi Java API cần Reactor. Giữ cardinality, nullability, cancellation, backpressure và Reactor Context. Spring WebFlux hỗ trợ suspend/Flow trực tiếp; không cần tự subscribe hoặc block trong controller/service. Với database và transaction, dùng reactive driver cùng cơ chế transaction coroutine/reactive được Spring hỗ trợ.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — Kotlin Coroutines](https://docs.spring.io/spring-framework/reference/6.2/languages/kotlin/coroutines.html)
- [Spring Boot 3.5 — Kotlin Support](https://docs.spring.io/spring-boot/3.5/reference/features/kotlin.html)
- [Spring Data Relational — Coroutine repositories](https://docs.spring.io/spring-data/relational/reference/kotlin/coroutines.html)
- [kotlinx.coroutines — Reactor integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/)
- [kotlinx.coroutines — Reactive Streams integration](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactive/)
- [kotlinx.coroutines — awaitSingle](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/await-single.html)
- [kotlinx.coroutines — awaitSingleOrNull](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/await-single-or-null.html)
- [kotlinx.coroutines — ReactorContext](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-reactor/kotlinx.coroutines.reactor/-reactor-context/)
- [Spring Framework 6.2 — WebClient Kotlin extension reference](https://docs.spring.io/spring-framework/reference/6.2/languages/kotlin/extensions.html).