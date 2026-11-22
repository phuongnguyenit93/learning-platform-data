# Test subscription bằng StepVerifier

GraphQL subscription trả về một luồng kết quả thay vì một response duy nhất. Một query thường hoàn tất sau khi trả data; subscription có thể phát nhiều event theo thời gian, tiếp tục chạy cho đến khi nguồn event hoàn tất, gặp lỗi hoặc bị hủy. Vì vậy, kiểm thử subscription cần xác nhận cả nội dung event lẫn vòng đời của publisher.

Trong Spring for GraphQL, resolver subscription thường trả về Flux hoặc một Publisher. GraphQlTester có thể thực thi subscription và chuyển một field trong mỗi event thành Flux Java. Reactor Test cung cấp StepVerifier để điều khiển demand, kiểm tra thứ tự event, xác nhận completion/error và chủ động cancel stream.

Bài này tập trung vào cách kết hợp GraphQlTester với StepVerifier, từ test resolver/publisher đơn giản đến test GraphQL execution và WebSocket transport. Mục tiêu là tạo test xác định, có timeout và không để subscription chạy vô hạn sau khi test kết thúc.

## 1. Vì sao subscription cần StepVerifier?

Một subscription có các hành vi mà assertion thông thường không thể kiểm tra đầy đủ:

- Phát một event hay nhiều event.
- Giữ đúng thứ tự event theo contract.
- Hoàn tất khi nguồn dữ liệu kết thúc.
- Phát lỗi khi nguồn event gặp sự cố.
- Dừng nguồn dữ liệu khi subscriber cancel.
- Tôn trọng demand/backpressure ở ranh giới publisher.
- Giữ đúng GraphQL selection set và mapping cho từng event.

StepVerifier đăng ký vào Publisher, sau đó mô tả chuỗi tín hiệu mong đợi. Test có thể yêu cầu một số event, kiểm tra nội dung từng event, chờ completion hoặc cancel stream. Nếu publisher không phát tín hiệu đúng như kịch bản, test thất bại thay vì chỉ kiểm tra một giá trị trả về.

Query và mutation thường dùng GraphQlTester.execute(). Subscription dùng executeSubscription() để nhận đối tượng subscription, sau đó gọi toFlux(path, type) để lấy luồng giá trị tại một response path.

## 2. Khai báo schema và resolver subscription

Ví dụ schema cho event phát hành sách:

~~~graphql
type Subscription {
    bookReleased: BookEvent!
}

type BookEvent {
    id: ID!
    title: String!
    releasedAt: String!
}
~~~

Java record biểu diễn payload:

~~~java
public record BookEvent(
        String id,
        String title,
        String releasedAt) {
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookReleased() {
        return eventService.events();
    }
}
~~~

@SubscriptionMapping ánh xạ method vào field của type Subscription. Mỗi subscriber nhận một publisher riêng theo cơ chế của service. GraphQL thực thi selection set cho từng event được phát ra, vì vậy lỗi ở field con có thể xuất hiện trong response của một event dù nguồn publisher vẫn tiếp tục.

## 3. Test publisher ở mức service

Trước khi test GraphQL mapping, có thể kiểm tra riêng publisher do service cung cấp. Test này tập trung vào logic reactive như thứ tự, filtering, completion và cancellation.

Ví dụ nguồn event hữu hạn:

~~~java
class BookEventServiceTests {

    @Test
    void emitsEventsInOrder() {
        Flux<BookEvent> events = Flux.just(
            new BookEvent("book-01", "Spring GraphQL", "2026-01-10"),
            new BookEvent("book-02", "Reactive Java", "2026-01-11"));

        StepVerifier.create(events)
            .assertNext(event -> {
                assertThat(event.id()).isEqualTo("book-01");
                assertThat(event.title()).isEqualTo("Spring GraphQL");
            })
            .assertNext(event -> {
                assertThat(event.id()).isEqualTo("book-02");
                assertThat(event.title()).isEqualTo("Reactive Java");
            })
        .expectComplete()
        .verify(Duration.ofSeconds(3));
    }
}
~~~

assertNext nhận từng phần tử và cho phép kiểm tra nhiều thuộc tính. verifyComplete() xác nhận publisher phát đủ các event rồi kết thúc bình thường. Với test có nguy cơ treo, nên dùng verify(Duration) để đặt giới hạn thời gian.

Test service không xác nhận GraphQL schema, @SubscriptionMapping hay serialization. Nó hữu ích để định vị lỗi ở business publisher trước khi kiểm tra cả GraphQL execution.

## 4. Tạo GraphQlTester cho subscription

Với GraphQL service trong Spring context, có thể tạo tester ở mức execution:

~~~java
@SpringBootTest
class BookSubscriptionGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }
}
~~~

Tester này thực thi GraphQL operation trực tiếp qua GraphQL service, không kiểm tra WebSocket handshake hoặc HTTP upgrade. Nó phù hợp để xác nhận schema, resolver, selection set, event mapping và GraphQL execution.

Khi cần kiểm tra giao thức WebSocket thật, dùng WebSocketGraphQlTester kết nối đến endpoint. Cả hai tester đều có thể cung cấp API subscription theo cấu hình hỗ trợ; lựa chọn tester dựa trên ranh giới cần kiểm tra.

## 5. Thực thi subscription bằng executeSubscription()

Document subscription:

~~~graphql
subscription BookReleased {
    bookReleased {
        id
        title
        releasedAt
    }
}
~~~

Test lấy stream tại path bookReleased:

~~~java
Flux<BookEvent> events = graphQlTester.document("""
        subscription BookReleased {
            bookReleased {
                id
                title
                releasedAt
            }
        }
        """)
    .executeSubscription()
    .toFlux("bookReleased", BookEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.id().equals("book-01")
            && event.title().equals("Spring GraphQL"))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

executeSubscription() bắt đầu GraphQL subscription operation. toFlux("bookReleased", BookEvent.class) đọc field tương ứng trong mỗi GraphQL event response và chuyển giá trị thành BookEvent.

Path phải là response key trong document. Nếu client đặt alias, dùng alias trong toFlux, không dùng tên field gốc trong schema.

## 6. Kiểm tra nhiều event và thứ tự

Một nguồn event hữu hạn giúp test deterministic:

~~~java
@Test
void mapsEveryGraphQlEventInOrder() {
    Flux<BookEvent> source = Flux.just(
        new BookEvent("book-01", "Spring GraphQL", "2026-01-10"),
        new BookEvent("book-02", "Reactive Java", "2026-01-11"));

    // eventService là mock được inject vào GraphQL controller trong test.
    when(eventService.events()).thenReturn(source);
    Flux<BookEvent> events = graphQlTester.document("""
            subscription {
                bookReleased {
                    id
                    title
                    releasedAt
                }
            }
            """)
        .executeSubscription()
        .toFlux("bookReleased", BookEvent.class);

    StepVerifier.create(events)
        .assertNext(event ->
            assertThat(event.id()).isEqualTo("book-01"))
        .assertNext(event ->
            assertThat(event.id()).isEqualTo("book-02"))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

Nếu dùng test fixture thay cho mock, inject fixture đó vào controller trước khi chạy GraphQL operation. Điều quan trọng là publisher mà resolver trả về phải chính là nguồn event đang được StepVerifier kiểm tra.

Khi thứ tự là một phần của contract, dùng assertNext hoặc expectNext theo đúng thứ tự. Nếu nguồn event không bảo đảm thứ tự, hãy kiểm tra tập event hoặc thuộc tính ổn định thay vì ép thứ tự giả tạo vào test.

## 7. Dùng TestPublisher hoặc Sinks để điều khiển event

Với stream sống lâu, test cần chủ động phát event sau khi subscriber đã đăng ký. Reactor cung cấp TestPublisher; Reactor Core cũng cung cấp Sinks.Many.

Ví dụ nguồn event có thể điều khiển bằng Sinks.Many:

~~~java
class BookEventSource {

    private final Sinks.Many<BookEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<BookEvent> events() {
        return sink.asFlux();
    }

    Sinks.EmitResult publish(BookEvent event) {
        return sink.tryEmitNext(event);
    }

    void complete() {
        sink.tryEmitComplete();
    }
}
~~~

multicast().onBackpressureBuffer() phát event đến subscriber đang hoạt động và buffer khi subscriber tạm thời chưa xử lý kịp theo policy của sink. Trong test, hãy tạo source riêng cho từng test để tránh event từ test trước lọt vào test sau.

Ví dụ test phát event sau khi StepVerifier subscribe:

~~~java
StepVerifier.create(events)
    .then(() -> {
        assertThat(eventSource.publish(
            new BookEvent("book-01", "Spring GraphQL", "2026-01-10")))
            .isEqualTo(Sinks.EmitResult.OK);
    })
    .assertNext(event ->
        assertThat(event.id()).isEqualTo("book-01"))
    .then(() -> eventSource.complete())
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

then(...) thực thi callback sau khi StepVerifier đã đăng ký và xử lý các bước demand trước đó. Nhờ vậy, event được phát sau khi subscriber sẵn sàng. Nếu phát event trước khi có subscriber với multicast sink, event có thể không được gửi đến subscription mới.

Có thể dùng TestPublisher.create() để điều khiển next, complete và error trong unit test. Chọn một cơ chế fixture nhất quán, tránh dùng một singleton publisher chung cho nhiều test chạy song song.

## 8. Kiểm tra stream không hoàn tất và chủ động cancel

Subscription thực tế thường không hoàn tất tự nhiên. Khi test chỉ cần xác nhận một vài event, hãy cancel sau assertion:

~~~java
StepVerifier.create(events)
    .then(() -> eventSource.publish(
        new BookEvent("book-01", "Spring GraphQL", "2026-01-10")))
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Không dùng verifyComplete() với publisher được thiết kế chạy liên tục nếu test không chủ động hoàn tất nguồn. Test sẽ chờ mãi hoặc chỉ kết thúc khi timeout toàn cục.

Cancellation là một phần quan trọng của subscription lifecycle. Khi client ngừng nghe, server nên hủy publisher và giải phóng listener, broker consumer hoặc tài nguyên đã đăng ký cho subscriber đó.

## 9. Kiểm tra cleanup khi cancel

Có thể gắn callback để xác nhận nguồn event nhận tín hiệu cancel:

~~~java
AtomicInteger cancelCount = new AtomicInteger();

Flux<BookEvent> source = Flux.<BookEvent>never()
    .doOnCancel(cancelCount::incrementAndGet);

StepVerifier.create(source)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertThat(cancelCount).hasValue(1);
~~~

Test này kiểm tra cancellation ở publisher boundary. Với GraphQL subscription, có thể dùng một source có doOnCancel tương tự, chạy operation qua executeSubscription(), rồi cancel stream từ StepVerifier và xác nhận cleanup callback được gọi.

Nếu resolver đăng ký listener với message broker, cleanup cần nằm trong publisher lifecycle. Tránh gọi subscribe() thủ công bên trong controller vì GraphQL sẽ không còn quản lý publisher con để propagate cancellation.

## 10. Đặt timeout cho StepVerifier

Một test reactive không nên treo vô hạn. Có thể đặt timeout cho lần verify:

~~~java
StepVerifier.create(events)
    .expectNextCount(2)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Hoặc dùng:

~~~java
StepVerifier.create(events)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Timeout giúp test thất bại rõ ràng nếu publisher không phát event hoặc không complete như mong đợi. Chọn thời gian đủ rộng cho CI nhưng không quá dài khiến lỗi làm chậm cả suite.

Nếu dùng StepVerifier.setDefaultTimeout, cần nhớ đó là cấu hình ảnh hưởng đến các verify trong phạm vi process/test JVM. Với test cần timeout khác nhau, truyền timeout trực tiếp vào verify giúp ý định rõ ràng hơn.

## 11. Kiểm tra publisher error

Nguồn event có thể kết thúc bằng lỗi, ví dụ broker mất kết nối hoặc service không thể đọc event. Ở mức service publisher, StepVerifier kiểm tra error signal:

~~~java
RuntimeException failure =
    new IllegalStateException("event source unavailable");

StepVerifier.create(Flux.<BookEvent>error(failure))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().equals("event source unavailable"))
    .verify(Duration.ofSeconds(3));
~~~

Không nên để test phụ thuộc vào message exception dài hoặc có dữ liệu nhạy cảm. Khi chỉ cần xác nhận loại lỗi, dùng expectError(Class) hoặc expectErrorMatches kiểm tra type/code phù hợp.

Test publisher error không đồng nghĩa test GraphQL error mapping. Khi lỗi xảy ra trong source publisher, subscription stream có thể kết thúc. Khi resolver của một field con lỗi trong lúc xử lý một event, GraphQL có thể tạo một event response chứa errors và áp dụng null propagation theo schema. Hai tình huống cần được kiểm tra riêng.

## 12. Kiểm tra GraphQL event response có lỗi

Trong GraphQL subscription, mỗi event được xử lý như một lần thực thi selection set. Một field con có thể lỗi dù nguồn event vẫn phát các event khác. Khi cần kiểm tra path, locations hoặc extensions.code, hãy kiểm tra GraphQL response error ở đúng boundary thay vì chỉ kiểm tra DTO đã map thành công.

Nếu dùng GraphQlTester.Subscription.toFlux(path, type), việc truy cập field có lỗi có thể được biểu diễn thành lỗi truy cập field ở client tester, tùy loại tester và phiên bản. Với test cần xác nhận chính xác error payload của từng event, dùng API/test transport phù hợp để quan sát ClientGraphQlResponse của từng event hoặc kiểm tra error mapping ở lớp execution riêng.

Không gộp mọi lỗi thành một onError của toàn stream. Hãy phân biệt:

- Source publisher phát onError: nguồn subscription kết thúc bằng lỗi.
- DataFetcher của field con ném exception: GraphQL tạo error cho field/event theo execution semantics.
- WebSocket connection đóng: lỗi ở transport có thể ảnh hưởng nhiều operation cùng connection.

## 13. Kiểm tra backpressure ở publisher boundary

Reactor Test cho phép bắt đầu với demand bằng 0 rồi yêu cầu từng phần tử:

~~~java
StepVerifier.create(source, 0)
    .thenRequest(1)
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(3));
~~~

Test này xác nhận publisher được kiểm tra phản ứng với demand như mong đợi. Đây là test ở ranh giới Reactor Publisher. Không nên suy ra rằng một test in-process đã chứng minh toàn bộ WebSocket, browser hoặc message broker thực hiện backpressure end-to-end giống nhau; mỗi transport có buffering và flow-control riêng.

Nếu nguồn event không thể backpressure trực tiếp, cần định nghĩa chính sách buffer, drop hoặc overflow. Test nên xác nhận chính sách đó thay vì giả định mọi event luôn được giữ vô hạn.

## 14. Dùng virtual time cho publisher dựa trên thời gian

Nếu business publisher dùng Flux.interval hoặc delay, StepVerifier.withVirtualTime giúp test mà không phải chờ thời gian thực:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .map(index -> "event-" + index))
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("event-0", "event-1", "event-2")
    .thenCancel()
    .verify(Duration.ofSeconds(1));
~~~

Publisher cần được tạo bên trong supplier của withVirtualTime để scheduler được thay bằng virtual scheduler trước khi publisher khởi tạo. Nếu tạo Flux.interval trước rồi mới truyền vào, test có thể vẫn dùng clock thật.

Virtual time phù hợp cho unit test publisher. Nó không tự điều khiển clock của WebSocket server, network I/O hoặc scheduler bên ngoài; không nên dùng nó để kết luận timeout transport hoạt động đúng.

## 15. Test GraphQL selection set và alias

toFlux nhận response path. Nếu document dùng alias, path phải là alias:

~~~graphql
subscription {
    released: bookReleased {
        id
        title
    }
}
~~~

Test:

~~~java
Flux<BookEvent> events = graphQlTester.document("""
        subscription {
            released: bookReleased {
                id
                title
            }
        }
        """)
    .executeSubscription()
    .toFlux("released", BookEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

GraphQL chỉ trả field được chọn trong selection set. DTO test nên phản ánh đúng payload đã yêu cầu. Nếu test cần một field nhưng document không chọn field đó, giá trị không thể tự xuất hiện chỉ vì Java event object có property tương ứng.

## 16. Test authorization và filtering của event

Nếu subscription chỉ được phép phát event theo user hoặc tenant, test cần xác nhận cả event được phép và event phải bị loại. Ví dụ publisher lọc theo principal:

~~~java
Flux<OrderEvent> visibleEvents(
        String username,
        Flux<OrderEvent> source) {

    return source.filterWhen(event ->
        authorizationService.canRead(username, event));
}
~~~

Unit test có thể phát event thuộc hai tenant và xác nhận subscriber chỉ nhận event trong scope:

~~~java
Flux<OrderEvent> source = Flux.just(
    new OrderEvent("order-01", "tenant-a"),
    new OrderEvent("order-02", "tenant-b"));

StepVerifier.create(service.visibleEvents("user-a", source))
    .assertNext(event ->
        assertThat(event.tenantId()).isEqualTo("tenant-a"))
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Trong GraphQL integration test, thiết lập principal qua cơ chế security test của ứng dụng và chạy operation qua tester phù hợp. Xác nhận user không có quyền không mở được subscription hoặc không nhận event trái quyền. Với quyền có thể bị thu hồi, thay đổi policy giữa hai event rồi kiểm tra event tiếp theo bị lọc hoặc stream bị hủy theo contract.

## 17. Test qua WebSocketGraphQlTester

ExecutionGraphQlServiceTester kiểm tra GraphQL execution nhưng không kiểm tra handshake, subprotocol hoặc connection initialization. Khi ứng dụng phục vụ subscription qua WebSocket, cần có integration test với WebSocketGraphQlTester.

Test WebSocket nên xác nhận:

- Handshake đến đúng endpoint.
- Origin và authentication được xử lý theo policy.
- Client và server thương lượng đúng GraphQL WebSocket subprotocol.
- Connection initialization được chấp nhận hoặc từ chối đúng cách.
- Subscription operation nhận đúng event.
- Cancel operation giải phóng publisher/listener.
- Connection close kết thúc các operation gắn với connection.

Sau khi tạo WebSocketGraphQlTester theo cấu hình WebSocket client của ứng dụng, vẫn có thể dùng executeSubscription().toFlux(...) và StepVerifier để kiểm tra event stream. Cấu hình tester cần dùng endpoint test thực tế và được đóng/giải phóng sau test theo lifecycle của phiên bản Spring for GraphQL.

Không dùng test in-process để kết luận WebSocket transport, proxy upgrade hoặc Origin policy đã đúng. Đây là các hành vi ở tầng transport cần test qua endpoint.

## 18. Tránh test flaky và rò rỉ subscription

Subscription test dễ flaky nếu event được phát trước khi subscriber đăng ký, nếu dùng publisher singleton giữa các test hoặc nếu test không cancel stream.

Một số nguyên tắc:

- Tạo publisher fixture riêng cho mỗi test.
- Phát event sau khi StepVerifier đã subscribe, dùng then(...) khi phù hợp.
- Không dùng Thread.sleep để chờ event; điều khiển publisher hoặc dùng virtual time.
- Đặt timeout cho mọi verify có thể chờ.
- Cancel stream vô hạn sau khi đã kiểm tra đủ event.
- Xác nhận cleanup callback khi test cancellation.
- Không chạy test song song trên cùng một mutable sink nếu không cô lập dữ liệu.
- Dọn broker listener, scheduler hoặc connection sau test.

Nếu cần kiểm tra event đến trong khoảng thời gian, dùng publisher điều khiển được hoặc scheduler ảo ở unit boundary. Thread.sleep chỉ làm test chậm hơn và vẫn không bảo đảm subscriber đã sẵn sàng.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test treo ở verifyComplete | Publisher subscription không hoàn tất tự nhiên | Dùng thenCancel hoặc chủ động complete source |
| Không nhận event đầu tiên | Phát event trước khi subscriber đăng ký | Phát event trong StepVerifier.then hoặc dùng replay source có chủ đích |
| Event từ test khác xuất hiện | Dùng sink/publisher singleton dùng chung | Tạo fixture mới cho từng test |
| Test chỉ kiểm tra service, bỏ sót GraphQL mapping | Không thực thi document qua GraphQlTester | Thêm test executeSubscription và toFlux |
| Test in-process xanh nhưng WebSocket lỗi | Chưa kiểm tra handshake/protocol/Origin | Thêm WebSocketGraphQlTester integration test |
| Không xác nhận cleanup | Chỉ cancel mà không quan sát nguồn | Gắn doOnCancel hoặc cleanup counter |
| Dùng virtual time nhưng test vẫn chờ thật | Publisher được tạo trước withVirtualTime hoặc dùng scheduler ngoài | Tạo publisher trong supplier và kiểm soát scheduler |
| Backpressure assertion không phản ánh transport | Chỉ test Reactor Publisher | Tách publisher test và transport test |
| Mọi lỗi bị coi là stream failure | Nhầm source onError với GraphQL event errors | Test riêng source error và field execution error |
| Test nhận event không đúng field | toFlux dùng schema field thay vì response alias/path | Dùng đúng response path trong document |

## 20. Ma trận kiểm thử subscription

Một bộ test có thể chia theo ranh giới và hành vi:

| Ranh giới | Hành vi | Công cụ phù hợp |
| --- | --- | --- |
| Service publisher | Thứ tự, filtering, completion, error, cancellation | StepVerifier |
| GraphQL execution | Schema, @SubscriptionMapping, selection set, event mapping | GraphQlTester với executeSubscription |
| WebSocket transport | Handshake, Origin, subprotocol, connection init, disconnect | WebSocketGraphQlTester |
| Authorization | Principal, tenant scope, revoke, event filtering | Spring Security test support + StepVerifier |
| Time-based publisher | Interval, delay, scheduled event | StepVerifier.withVirtualTime |
| Backpressure | Demand, buffer/overflow policy | StepVerifier ở publisher boundary |

Không cần đặt mọi hành vi vào một integration test lớn. Unit test publisher cho phản hồi nhanh; GraphQL execution test kiểm tra mapping; transport test xác nhận WebSocket. Khi một test thất bại, ranh giới rõ ràng giúp tìm đúng lớp gây lỗi.

## 21. Nguyên tắc thiết kế test subscription

Dùng StepVerifier để mô tả tín hiệu mong đợi của subscription: event nào xuất hiện, thứ tự ra sao, publisher hoàn tất hay lỗi, và khi nào subscriber cancel. Dùng GraphQlTester.executeSubscription().toFlux(path, type) để kiểm tra event sau khi GraphQL áp dụng schema và selection set. Với publisher sống lâu, chủ động cancel thay vì chờ completion; với publisher hữu hạn, xác nhận completion và đặt timeout.

Tách test service publisher khỏi test GraphQL execution và test WebSocket transport. Dùng Sinks.Many hoặc TestPublisher để điều khiển event, tạo fixture riêng cho từng test và xác nhận cleanup khi cancel. Dùng virtual time cho publisher dựa trên scheduler có thể kiểm soát; test backpressure ở publisher boundary và không suy diễn thành flow control của transport.

Một subscription test tốt xác nhận toàn bộ hành vi quan trọng của luồng: dữ liệu đúng, event đúng thứ tự theo contract, lỗi được phân loại đúng, tài nguyên được giải phóng và test luôn kết thúc trong thời gian hữu hạn.
