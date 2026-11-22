# Publisher và subscription

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của Reactive Streams `Publisher`, `Subscriber` và `Subscription`.
- Phân biệt `org.reactivestreams.Subscription` với GraphQL Subscription operation.
- Hiểu cách `Mono` và `Flux` triển khai Publisher.
- Dùng `@SubscriptionMapping` để trả về một publisher cho GraphQL subscription field.
- Mô tả cách mỗi event được chuyển thành một GraphQL response.
- Phân biệt cold publisher và hot publisher.
- Hiểu backpressure, cancellation, lỗi và vòng đời của một subscription.
- Chọn transport phù hợp và kiểm thử subscription bằng `StepVerifier` cùng `WebSocketGraphQlTester`.

## 1. Publisher là gì?

Reactive Streams định nghĩa một giao thức bất đồng bộ để truyền dữ liệu giữa nguồn phát và bên nhận. Thành phần trung tâm của giao thức là interface `Publisher<T>`.

Một Publisher có thể phát ra không, một hoặc nhiều phần tử kiểu `T`. Nó không đẩy dữ liệu tùy ý vào bên nhận; quá trình truyền được điều khiển bằng một subscription handle và cơ chế demand.

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `Publisher<T>` | Nguồn phát dữ liệu |
| `Subscriber<T>` | Bên nhận dữ liệu |
| `Subscription` | Handle điều khiển demand và hủy đăng ký |
| `onNext(T)` | Phát một phần tử |
| `onError(Throwable)` | Kết thúc luồng bằng lỗi |
| `onComplete()` | Kết thúc luồng bình thường |

Publisher không nhất thiết tạo dữ liệu ngay khi được khởi tạo. Thông thường, dữ liệu bắt đầu được phát khi có Subscriber đăng ký.

Trong Reactor:

- `Mono<T>` triển khai Publisher và phát tối đa một phần tử.
- `Flux<T>` triển khai Publisher và có thể phát không hoặc nhiều phần tử.

Vì vậy, Spring for GraphQL có thể nhận `Mono` hoặc `Flux` từ controller hay DataFetcher để phối hợp thực thi bất đồng bộ.

## 2. Vòng đời Reactive Streams

Khi một Subscriber đăng ký với Publisher, Publisher gọi `onSubscribe` và cung cấp một đối tượng `Subscription`. Subscriber dùng đối tượng đó để yêu cầu số phần tử muốn nhận hoặc hủy luồng.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe(subscriber)
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>P: request(more)
    P-->>S: onNext(item 3)
    P-->>S: onComplete()
~~~

Một luồng Reactive Streams có thể kết thúc theo hai cách:

- Hoàn tất bình thường bằng `onComplete()`.
- Kết thúc bằng lỗi bằng `onError(Throwable)`.

Sau tín hiệu terminal `onComplete` hoặc `onError`, Publisher không được tiếp tục phát `onNext` cho cùng subscription.

Subscriber cũng có thể gọi `cancel()` trên Subscription để hủy việc nhận dữ liệu. Khi hủy, nguồn phát nên dừng các công việc không còn cần thiết và giải phóng tài nguyên liên quan.

### Subscription trong Reactive Streams khác GraphQL Subscription

Từ *Subscription* xuất hiện ở hai tầng khác nhau:

1. `org.reactivestreams.Subscription` là đối tượng điều khiển demand và cancellation giữa Publisher và Subscriber.
2. GraphQL Subscription là một loại operation cho phép client nhận nhiều response theo thời gian.

GraphQL Subscription thường được triển khai trên Reactive Streams Publisher, nhưng hai khái niệm không đồng nhất. Một `Flux` có thể được dùng trong Query list mà không tạo GraphQL Subscription operation.

## 3. Mono và Flux là Publisher

Reactor cung cấp hai kiểu Publisher phổ biến:

~~~java
Mono<Book> oneBook = bookService.findById("b-01");

Flux<Book> books = bookService.findAll();
~~~

`Mono<Book>` có thể phát một Book rồi hoàn tất, hoặc hoàn tất rỗng, hoặc phát lỗi.

`Flux<Book>` có thể phát nhiều Book theo thời gian, hoàn tất sau phần tử cuối cùng hoặc phát lỗi.

Ví dụ tạo publisher đơn giản:

~~~java
Mono<String> greeting = Mono.just("Hello GraphQL");

Flux<Integer> numbers = Flux.just(1, 2, 3);
~~~

Publisher có thể được tạo từ một giá trị có sẵn, một collection, một reactive repository, một message broker hoặc một event source.

Trong ứng dụng Spring for GraphQL, nên giữ Publisher xuyên suốt service và controller nếu nguồn dữ liệu đã hỗ trợ reactive. Không cần chuyển `Flux` thành `List` bằng cách block để GraphQL nhận kết quả.

## 4. GraphQL Subscription operation là gì?

GraphQL có ba loại operation chính:

- Query: đọc dữ liệu theo request.
- Mutation: thay đổi dữ liệu.
- Subscription: đăng ký nhận các event hoặc cập nhật theo thời gian.

Ví dụ schema:

~~~graphql
type Query {
  books: [Book!]!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: ID!
  title: String!
}
~~~

Client gửi một subscription operation:

~~~graphql
subscription {
  bookAdded {
    id
    title
  }
}
~~~

Server thiết lập một luồng theo dõi event. Khi một Book mới được phát ra, GraphQL thực thi selection set `id` và `title` trên event đó rồi gửi một response cho client.

Mỗi event tạo một GraphQL execution result riêng. Một subscription có thể tạo nhiều response cho tới khi publisher hoàn tất, phát lỗi hoặc bị hủy.

Theo GraphQL specification, subscription operation có đúng một root field. Các field con bên trong root field vẫn có thể lồng nhau như query thông thường.

## 5. Dùng @SubscriptionMapping trong Spring for GraphQL

Spring for GraphQL cung cấp `@SubscriptionMapping` để ánh xạ một controller method vào field thuộc root type `Subscription`.

SDL:

~~~graphql
type Subscription {
  bookAdded: Book!
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventPublisher eventPublisher;

    public BookSubscriptionController(
            BookEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return eventPublisher.bookAdded();
    }
}
~~~

Spring suy luận tên field từ tên method `bookAdded` và ánh xạ tới `Subscription.bookAdded`.

Nếu tên method khác tên field trong SDL, có thể khai báo tường minh:

~~~java
@SubscriptionMapping(name = "bookAdded")
public Flux<Book> streamNewBooks() {
    return eventPublisher.bookAdded();
}
~~~

Method trả về `Flux<Book>`, là Publisher phát các Book event. Spring for GraphQL và GraphQL Java phối hợp thực thi selection set cho từng phần tử được phát.

Có thể nhận argument và thông tin xác thực giống các annotated controller method khác:

~~~graphql
type Subscription {
  bookAdded(authorId: ID): Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded(@Argument String authorId) {
    return eventPublisher.bookAdded()
            .filter(book -> authorId == null
                    || authorId.equals(book.authorId()));
}
~~~

Bộ lọc được áp dụng riêng cho từng subscription. Trong ứng dụng thực tế, cần kết hợp điều kiện nghiệp vụ với tenant và quyền của principal đã xác thực.

## 6. Nguồn event tạo Publisher

Một subscription cần nguồn dữ liệu có thể phát event. Nguồn đó có thể là:

- Message broker như Kafka hoặc RabbitMQ.
- Event bus trong ứng dụng.
- Reactor Sink.
- Change stream từ database.
- Một publisher được tạo từ dịch vụ bên ngoài.

Ví dụ đơn giản dùng Reactor Sink để phát Book mới:

~~~java
@Component
public class BookEventPublisher {

    private final Sinks.Many<Book> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<Book> bookAdded() {
        return sink.asFlux();
    }

    public void publish(Book book) {
        Sinks.EmitResult result = sink.tryEmitNext(book);

        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Cannot publish book event: " + result);
        }
    }
}
~~~

Khi nghiệp vụ tạo sách thành công, ứng dụng phát event:

~~~java
public Book createBook(CreateBookInput input) {
    Book book = bookRepository.save(toEntity(input));
    eventPublisher.publish(book);
    return book;
}
~~~

Ví dụ này minh họa luồng event trong một ứng dụng đơn giản. Với hệ thống production, cần quyết định rõ:

- Event có cần lưu bền vững hay không.
- Có cần phát lại event cho client kết nối muộn hay không.
- Nhiều instance ứng dụng có cần cùng nhận event hay không.
- Điều gì xảy ra khi sink đầy hoặc không có subscriber.
- Event chỉ được phát sau khi transaction commit hay trước commit.

Một Reactor Sink trong bộ nhớ không phải message broker bền vững. Khi process dừng, event trong bộ nhớ mất; một client kết nối sau không mặc nhiên nhận lại lịch sử event.

## 7. Cold Publisher và Hot Publisher

Hai kiểu publisher có hành vi khác nhau khi có nhiều Subscriber.

### Cold Publisher

Cold Publisher thường bắt đầu công việc riêng cho từng Subscriber. Mỗi lần subscribe có thể tạo một quá trình đọc dữ liệu độc lập.

Ví dụ:

~~~java
Flux<Book> books = Flux.defer(() ->
        bookRepository.findAll());
~~~

Mỗi subscriber đăng ký có thể kích hoạt một lần truy vấn mới. Cold publisher phù hợp với thao tác đọc hoặc xử lý cần thực hiện riêng theo từng subscription.

### Hot Publisher

Hot Publisher có thể phát dữ liệu độc lập với thời điểm Subscriber đăng ký. Nhiều subscriber có thể cùng quan sát một nguồn event đang hoạt động.

Ví dụ Reactor Sink:

~~~java
Sinks.Many<Book> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<Book> sharedEvents = sink.asFlux();
~~~

Khi ứng dụng gọi `tryEmitNext`, các subscriber đang tham gia luồng multicast nhận event theo chính sách của sink.

| Tiêu chí | Cold Publisher | Hot Publisher |
|---|---|---|
| Thời điểm phát | Thường bắt đầu khi có subscriber | Có thể phát độc lập với subscriber |
| Nhiều subscriber | Mỗi subscriber có thể có nguồn riêng | Có thể chia sẻ cùng nguồn |
| Event phát trước khi subscribe | Subscriber mới thường không thấy | Có thể mất nếu không có replay |
| Ví dụ | Truy vấn reactive repository | Event bus, live notification |

Nếu cần client mới kết nối vẫn nhận lịch sử event, cần chọn replay hoặc lưu trữ event riêng. Không nên dùng replay không giới hạn trong bộ nhớ nếu luồng có thể phát lâu dài.

## 8. GraphQL Subscription cần transport hỗ trợ streaming

Một GraphQL Subscription có vòng đời dài và phát nhiều response. Transport cần hỗ trợ giữ kết nối hoặc trao đổi nhiều message.

Spring for GraphQL hỗ trợ các lựa chọn như:

- WebSocket với giao thức GraphQL WebSocket, thường dùng subprotocol `graphql-transport-ws`.
- RSocket với cơ chế request-stream.

Ví dụ cấu hình WebSocket endpoint trong Spring Boot:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

Client kết nối WebSocket tới endpoint đã cấu hình, gửi message đăng ký operation, nhận các event và có thể gửi message complete để dừng subscription.

Một request-response HTTP thông thường không thể giữ một response duy nhất mở mãi để gửi event theo cách tương tự. Hãy chọn transport và client hỗ trợ streaming cho use case subscription, đồng thời kiểm tra endpoint, subprotocol và chính sách proxy/load balancer.

Không nên giả định việc một controller trả `Flux` là đủ để mọi transport tự động hỗ trợ subscription. Cần cấu hình transport streaming và client tương ứng.

## 9. Mỗi event được GraphQL xử lý như thế nào?

Publisher của subscription phát ra một object hoặc payload. GraphQL sử dụng payload đó làm source cho root subscription field rồi thực thi selection set.

Ví dụ:

~~~graphql
subscription {
  bookAdded {
    id
    title
    author {
      name
    }
  }
}
~~~

Khi publisher phát Book:

~~~java
new Book("b-01", "GraphQL in Practice", "a-01")
~~~

GraphQL xử lý:

1. Dùng Book làm source của field `Subscription.bookAdded`.
2. Đọc `Book.id` và `Book.title`.
3. Phân giải field `Book.author`.
4. Dùng object Author làm source cho `Author.name`.
5. Tạo một response chứa dữ liệu của event đó.

Nếu field con cần tải dữ liệu liên quan, có thể dùng `@SchemaMapping`, DataLoader hoặc `@BatchMapping` như trong Query. Tuy nhiên, mỗi event có thể kích hoạt thêm các resolver, vì vậy cần theo dõi chi phí xử lý khi event phát liên tục.

Ví dụ response của một event:

~~~json
{
  "data": {
    "bookAdded": {
      "id": "b-01",
      "title": "GraphQL in Practice",
      "author": {
        "name": "Nguyen An"
      }
    }
  }
}
~~~

Event tiếp theo tạo response tiếp theo với cùng selection set, nhưng payload có thể là một Book khác.

## 10. Backpressure và tốc độ phát event

Reactive Streams có cơ chế backpressure để Subscriber báo cho Publisher biết số phần tử mà nó sẵn sàng nhận.

Subscriber gọi `request(n)` để yêu cầu thêm tối đa `n` phần tử. Điều này giúp nguồn phát và bên nhận phối hợp tốc độ, tránh đẩy dữ liệu không giới hạn vào một consumer chậm.

Trong subscription thực tế, tốc độ event có thể cao hơn tốc độ server xử lý hoặc client nhận. Cần xác định chính sách khi downstream chậm:

- Buffer một số lượng event có giới hạn.
- Drop event cũ hoặc mới nếu nghiệp vụ cho phép.
- Báo lỗi khi buffer đầy.
- Dùng broker có khả năng lưu event và consumer offset.
- Giảm tần suất hoặc gộp nhiều event thành một cập nhật.

Ví dụ, một dashboard hiển thị trạng thái mới nhất có thể chấp nhận gộp nhiều thay đổi liên tiếp. Hệ thống tài chính hoặc audit log thường không được phép âm thầm drop event.

Không nên dùng buffer không giới hạn cho nguồn event lâu dài. Nếu consumer chậm trong thời gian dài, bộ nhớ có thể tăng liên tục.

## 11. Cancellation và dọn dẹp tài nguyên

GraphQL subscription có thể kết thúc khi:

- Publisher phát `onComplete`.
- Publisher phát `onError`.
- Client gửi lệnh complete/unsubscribe.
- Kết nối WebSocket hoặc RSocket bị đóng.
- Server chủ động hủy operation hoặc ứng dụng dừng.

Khi client hủy subscription, cancellation cần được truyền ngược qua reactive chain để upstream dừng công việc không còn cần thiết.

Có thể quan sát vòng đời bằng `doFinally`:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return eventPublisher.bookAdded()
            .doFinally(signalType -> {
                if (signalType == SignalType.CANCEL) {
                    log.debug("Book subscription cancelled");
                }
            });
}
~~~

Không gọi `subscribe()` thủ công trong controller để tạo một luồng tách rời. Hãy trả Publisher cho Spring for GraphQL để framework quản lý subscription lifecycle.

Nếu nguồn event mở tài nguyên như listener, cursor hoặc consumer broker riêng cho từng subscriber, hãy bảo đảm tài nguyên được đóng khi publisher bị cancel hoặc kết thúc. Với nguồn dùng chung toàn ứng dụng, hủy một subscriber không nên vô tình đóng nguồn chung của những subscriber khác.

## 12. Xử lý lỗi trong subscription stream

Có hai nhóm lỗi cần phân biệt:

1. Lỗi khi tạo hoặc đăng ký nguồn publisher.
2. Lỗi phát sinh khi xử lý một event và resolve các field của event đó.

Nếu publisher nguồn phát `onError`, stream thường kết thúc. Client nhận lỗi theo cơ chế GraphQL/transport và không tiếp tục nhận event từ publisher đã kết thúc.

Nếu một field resolver trong quá trình xử lý một event phát sinh lỗi, GraphQL có thể tạo một execution result chứa `data` và `errors` cho event đó. Cách xử lý phụ thuộc vào field, nullability và exception resolver đã cấu hình.

Ví dụ lọc lỗi có thể phục hồi:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return eventPublisher.bookAdded()
            .onErrorResume(
                    TemporaryEventSourceException.class,
                    error -> fallbackPublisher.reconnect()
            );
}
~~~

Ví dụ này chỉ phù hợp nếu fallback publisher có thể tiếp tục cung cấp cùng loại event và có chính sách reconnect rõ ràng. Không nên biến mọi lỗi thành `Flux.empty()`, vì stream sẽ kết thúc bình thường và client có thể không biết nguồn dữ liệu đã gặp sự cố.

Khi xử lý lỗi:

- Dùng error classification ổn định cho client.
- Không gửi stack trace, SQL hoặc thông tin nội bộ.
- Xác định lỗi nào có thể retry.
- Có chính sách reconnect và resume nếu cần.
- Kiểm thử cả lỗi nguồn publisher và lỗi field resolver.

## 13. Bảo mật subscription dài hạn

Subscription có thể tồn tại lâu hơn một request thông thường. Vì vậy, cần cân nhắc quyền truy cập ở thời điểm bắt đầu và trong suốt thời gian stream hoạt động.

Một số nguyên tắc:

- Xác thực kết nối và subscription operation theo chính sách của ứng dụng.
- Lọc event theo tenant hoặc người dùng đã xác thực.
- Không dùng argument do client gửi làm bằng chứng quyền truy cập.
- Nếu quyền của người dùng có thể thay đổi, cân nhắc kiểm tra lại quyền trên từng event.
- Khi token hết hạn hoặc principal mất quyền, xác định cách kết thúc subscription.
- Không chia sẻ publisher có dữ liệu riêng tư mà không có filter theo subscriber.
- Không để event payload chứa dữ liệu nhạy cảm không cần thiết.

Ví dụ lọc theo tenant đã được xác thực:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded(
        @ContextValue("tenantId") String tenantId) {

    return eventPublisher.bookAdded()
            .filter(book -> tenantId.equals(book.tenantId()));
}
~~~

`tenantId` cần được thiết lập trong GraphQLContext bởi thành phần bảo mật đáng tin cậy. Nếu event source phát chung cho nhiều tenant, filter phải được áp dụng riêng cho từng subscription.

## 14. Kiểm thử Publisher và GraphQL Subscription

Có thể kiểm thử Publisher ở tầng Reactor bằng `StepVerifier`. Công cụ này giúp kiểm tra phần tử, thứ tự, lỗi, hoàn tất và cancellation.

Ví dụ:

~~~java
@Test
void shouldPublishBookEvent() {
    StepVerifier.create(eventPublisher.bookAdded())
            .then(() -> eventPublisher.publish(
                    new Book("b-01", "GraphQL in Practice", "a-01")))
            .assertNext(book ->
                    assertThat(book.id()).isEqualTo("b-01"))
            .thenCancel()
            .verify();
}
~~~

Để kiểm thử GraphQL operation qua transport thực tế, dùng `WebSocketGraphQlTester` và kiểm tra luồng response bằng StepVerifier.

Ví dụ với một biến `graphQlTester` đã được cấu hình để kết nối WebSocket:

Trong integration test thực tế, cần đồng bộ việc phát event với thời điểm server đã đăng ký subscription. Đoạn code dưới đây minh họa luồng kiểm thử; test fixture có thể dùng một tín hiệu xác nhận subscriber đã sẵn sàng. Tránh dùng `sleep` cố định vì handshake và lịch chạy bất đồng bộ có thể thay đổi.

~~~java
@Test
void shouldReceiveBookAddedSubscriptionEvent() {
    Flux<GraphQlTester.Response> responses =
            graphQlTester.document("""
                    subscription {
                      bookAdded {
                        id
                        title
                      }
                    }
                    """)
                    .executeSubscription();

    StepVerifier.create(responses)
            .then(() -> eventPublisher.publish(
                    new Book("b-01", "GraphQL in Practice", "a-01")))
            .assertNext(response -> {
                response.path("bookAdded.id")
                        .entity(String.class)
                        .isEqualTo("b-01");
            })
            .thenCancel()
            .verify();
}
~~~

Các tình huống nên kiểm thử:

1. Publisher phát event theo đúng thứ tự.
2. Một subscriber nhận đúng event theo điều kiện lọc.
3. Hai subscriber nhận dữ liệu theo phạm vi được phép.
4. Client cancel làm upstream dừng công việc.
5. Publisher hoàn tất bình thường.
6. Publisher phát lỗi và stream kết thúc đúng cách.
7. Field resolver lỗi tạo GraphQL error cho event.
8. Backpressure hoặc buffer overflow được xử lý theo chính sách.
9. WebSocket reconnect không tự phát lại event nếu không có cơ chế replay.
10. Tenant và authorization được áp dụng trên toàn bộ subscription lifecycle.

Test ở tầng Publisher không thay thế integration test qua transport. Một Publisher có thể hoạt động đúng trong StepVerifier nhưng WebSocket endpoint hoặc GraphQL protocol vẫn cấu hình sai.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Subscription chỉ trả một event | Publisher là Mono hoặc nguồn phát hoàn tất sau một phần tử | Dùng publisher sống lâu nếu cần nhiều event |
| Client không nhận event | Sink chưa phát, client chưa subscribe hoặc transport chưa hỗ trợ streaming | Kiểm tra event source và WebSocket/RSocket |
| Client kết nối muộn không nhận event cũ | Hot publisher không có replay/history | Dùng replay hoặc event store nếu nghiệp vụ yêu cầu |
| Query Flux bị nhầm là subscription | Flux trong Query được aggregate thành list | Dùng GraphQL Subscription operation |
| Subscription không dừng khi client rời đi | Cancellation không được truyền hoặc nguồn tự subscribe | Trả publisher trực tiếp và kiểm tra cleanup |
| Bộ nhớ tăng liên tục | Buffer không giới hạn khi consumer chậm | Đặt giới hạn và chính sách overflow |
| Một tenant thấy event của tenant khác | Thiếu filter theo principal/tenant | Lọc theo context đã xác thực |
| Stream kết thúc bất ngờ | Publisher phát onError hoặc onComplete | Kiểm tra lỗi nguồn và lifecycle |
| Event bị lặp sau reconnect | Client/server phát lại nhưng không có event ID hoặc resume policy | Thiết kế cursor và idempotency |

## 16. Nguyên tắc thiết kế Publisher và subscription

Khi triển khai subscription trong Spring for GraphQL:

- Trả về `Publisher<T>` hoặc `Flux<T>` từ `@SubscriptionMapping`.
- Dùng `Mono<T>` chỉ khi chủ đích là publisher tối đa một event rồi hoàn tất.
- Phân biệt GraphQL Subscription với Reactive Streams `Subscription`.
- Chọn hot hoặc cold publisher theo yêu cầu nghiệp vụ.
- Dùng transport hỗ trợ streaming như WebSocket hoặc RSocket.
- Hiểu rằng mỗi event kích hoạt GraphQL execution cho selection set.
- Xác định chính sách backpressure và buffer.
- Truyền cancellation để dừng công việc và giải phóng tài nguyên.
- Xử lý lỗi nguồn publisher và lỗi field resolver riêng.
- Kiểm tra quyền truy cập và tenant trong suốt thời gian subscription.
- Dùng StepVerifier cho publisher và WebSocketGraphQlTester cho integration test.
- Chỉ triển khai replay/resume khi hệ thống có yêu cầu và cơ chế lưu event phù hợp.

## Kết luận

Reactive Streams định nghĩa cách Publisher phát dữ liệu tới Subscriber thông qua một Subscription handle. Reactor cung cấp `Mono` và `Flux` để triển khai giao thức này. Spring for GraphQL dùng Publisher làm nền tảng cho GraphQL Subscription: `@SubscriptionMapping` trả về một publisher, mỗi event được GraphQL xử lý thành một response theo selection set của client.

Để subscription hoạt động ổn định, cần hiểu cold và hot publisher, chọn transport streaming, đặt chính sách backpressure, truyền cancellation, xử lý lỗi và kiểm tra quyền truy cập trong suốt vòng đời. Kiểm thử cả publisher lẫn WebSocket/RSocket transport giúp bảo đảm luồng event hoạt động đúng trong điều kiện thực tế.

## Tài liệu tham khảo

- [Spring for GraphQL — Subscription and Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers, Subscription Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — Spring for GraphQL WebSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [GraphQL Specification — Subscription](https://spec.graphql.org/October2021/#sec-Subscription)
