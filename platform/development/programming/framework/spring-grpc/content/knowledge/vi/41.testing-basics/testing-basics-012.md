# Không dùng network thật cho mọi unit test

## 1. Unit test cần kiểm tra logic, không cần dựng cả hệ thống mạng

Trong **SPRING_GRPC**, ứng dụng dùng Protocol Buffers làm hợp đồng, generated stub để gọi RPC và service implementation trong hệ sinh thái Spring. Một lời gọi gRPC khi chạy thật đi qua channel, HTTP/2, TCP, có thể thêm TLS, proxy, DNS và nhiều thành phần hạ tầng.

Không phải mọi bài kiểm thử đều cần những thành phần đó. Unit test nên chạy nhanh, cô lập và lặp lại được; nó tập trung xác minh một đơn vị logic với đầu vào/đầu ra đã kiểm soát. Nếu mỗi unit test đều mở socket, khởi động server thật, kết nối database hoặc phụ thuộc broker, bộ test sẽ chậm, dễ lỗi do môi trường và khó chỉ ra nguyên nhân thất bại.

Điều này không có nghĩa bỏ kiểm thử transport. Hãy chọn đúng cấp độ:

| Cấp độ | Phạm vi | Cách chạy phù hợp |
|---|---|---|
| Unit test domain/use case | Quy tắc nghiệp vụ, validation, mapping | Gọi trực tiếp class; dùng fake/mock cho dependency |
| gRPC service test | Generated stub, method descriptor, service adapter, status/observer | In-process gRPC transport |
| Component test | Wiring Spring, interceptor, configuration, serialization | Spring test context và dependency giả/lokal |
| Integration test | TCP, TLS, HTTP/2, database, broker, proxy | Server thật trên port tạm và dependency containerized |
| End-to-end test | Luồng giữa các service trong môi trường gần production | Môi trường tích hợp riêng, số lượng nhỏ |

Mục tiêu là giữ phần lớn test ở các cấp không cần network thật, đồng thời vẫn có một tập integration test đủ nhỏ để kiểm chứng các ranh giới hạ tầng quan trọng.

## 2. Kiểm thử use case trực tiếp

Quy tắc nghiệp vụ không nên phụ thuộc vào `ManagedChannel`, `StreamObserver` hoặc socket. Service adapter nhận protobuf request, chuyển thành application command/query, gọi use case và ánh xạ kết quả trở lại protobuf response.

~~~text
gRPC client
    |
    v
Generated stub
    |
    v
gRPC service adapter
    |
    v
Application use case
    |
    +---- repository / external port
~~~

Unit test use case nên gọi trực tiếp use case và thay dependency ngoài bằng fake hoặc mock. Không cần dựng gRPC server để kiểm tra một quy tắc như “không cho đặt số lượng nhỏ hơn 1”.

Ví dụ:

~~~java
class CreateOrderUseCaseTest {
    private final OrderRepository repository =
            mock(OrderRepository.class);
    private final CreateOrderUseCase useCase =
            new CreateOrderUseCase(repository);

    @Test
    void rejectsNonPositiveQuantity() {
        CreateOrderCommand command =
                new CreateOrderCommand("customer-1", List.of(
                        new OrderLine("sku-1", 0)));

        assertThrows(
                InvalidOrderException.class,
                () -> useCase.execute(command));

        verifyNoInteractions(repository);
    }
}
~~~

Test này xác minh validation và bảo đảm repository không bị gọi khi command sai. Nó không cần port, channel, server hay broker. Các test khác có thể dùng fake repository lưu dữ liệu trong bộ nhớ nếu cần kiểm tra nhiều bước nghiệp vụ.

## 3. Dùng fake và mock ở đúng ranh giới

Một dependency được thay thế tốt sẽ giúp test tập trung vào hành vi của đơn vị đang kiểm tra:

- **Fake:** implementation đơn giản nhưng chạy được, ví dụ in-memory repository hoặc clock giả.
- **Mock:** đối tượng ghi nhận lời gọi để xác minh tương tác, thường hữu ích khi cần bảo đảm một side effect không xảy ra.
- **Stub:** trả kết quả cố định theo lời gọi, dùng để kiểm soát nhánh xử lý.

Ưu tiên fake khi cần một dependency có trạng thái và hành vi đủ thực tế. Dùng mock cho tương tác quan trọng như “không publish message khi validation thất bại”. Tránh mock quá sâu mọi method của generated stub, channel và gRPC runtime; test khi đó dễ gắn chặt với chi tiết triển khai hơn là hợp đồng quan sát được.

Ví dụ fake repository:

~~~java
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> orders = new HashMap<>();

    @Override
    public void save(Order order) {
        orders.put(order.id(), order);
    }

    @Override
    public Optional<Order> findById(String id) {
        return Optional.ofNullable(orders.get(id));
    }
}
~~~

Fake này phù hợp cho test logic đọc/ghi cơ bản. Nó không kiểm chứng SQL, transaction, isolation hoặc migration; những điều đó thuộc integration test với database thật.

## 4. In-process gRPC transport là gì?

gRPC Java cung cấp transport **in-process** qua `grpc-inprocess`. Nó cho phép tạo server và channel trong cùng JVM, rồi gọi service bằng generated stub như client bình thường, nhưng không mở TCP socket và không đi qua network interface.

In-process hữu ích để kiểm tra:

- Generated blocking, future hoặc async stub gọi đúng service method.
- Service adapter ánh xạ request/response đúng.
- gRPC status, metadata và interceptor hoạt động trong call.
- Unary và streaming RPC tuân thủ quy tắc `onNext`, `onError`, `onCompleted`.
- Client nhận đúng lỗi khi service trả status.
- Deadline và cancellation ở mức call được xử lý trong transport test.

In-process không kiểm chứng TCP, DNS, TLS handshake, certificate, ALPN, proxy, HTTP/2 wire behavior hoặc firewall. Đây là một test transport gRPC trong JVM, không phải bằng chứng server triển khai ngoài mạng hoạt động.

## 5. Thêm dependency in-process cho test

Dùng phiên bản `grpc-inprocess` đồng bộ với các module gRPC Java còn lại. Nếu dự án quản lý dependency bằng gRPC BOM, để BOM chọn version thay vì ghi một version độc lập có thể lệch runtime.

Ví dụ Gradle:

~~~kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
}
~~~

Nếu dự án dùng Spring Boot dependency management hoặc version catalog, khai báo dependency theo cơ chế sẵn có. Không đưa `grpc-inprocess` vào runtime production chỉ vì test cần nó; đây là dependency phục vụ test.

## 6. Dựng in-process server và channel

Test fixture tạo tên server riêng, đăng ký service implementation, khởi động in-process server rồi tạo channel cùng tên:

~~~java
class OrdersGrpcServiceTest {
    private Server server;
    private ManagedChannel channel;
    private OrdersGrpc.OrdersBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new OrdersGrpcService(
                        new InMemoryOrderRepository()))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        stub = OrdersGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(5, TimeUnit.SECONDS);
        server.awaitTermination(5, TimeUnit.SECONDS);
    }

    @Test
    void returnsOrderThroughGeneratedStub() {
        GetOrderReply reply = stub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("order-42")
                        .build());

        assertEquals("order-42", reply.getOrderId());
    }
}
~~~

Các import và generated class phụ thuộc package trong file `.proto`. Ví dụ giả định service `Orders` có RPC `GetOrder` và server implementation `OrdersGrpcService`.

`InProcessServerBuilder.generateName()` tránh trùng tên giữa test chạy song song. Server và channel phải được shutdown sau mỗi test để không rò tài nguyên hoặc làm test khác dùng nhầm service. Trong test thực tế, nếu `channel` hoặc `server` có thể chưa được tạo khi setup lỗi, cleanup nên kiểm tra null trước khi shutdown.

## 7. Ý nghĩa và giới hạn của directExecutor

`directExecutor()` chạy callback ngay trên thread thực hiện lời gọi thay vì chuyển sang executor khác. Nó giúp test đơn giản, giảm bất định do scheduling và phù hợp với nhiều test service đồng bộ.

Tuy nhiên, direct executor không mô phỏng đầy đủ concurrency của server production. Nó có thể làm lộ reentrancy hoặc thứ tự callback khác với executor thực tế; không dùng nó làm bằng chứng về thread safety, race condition, throughput hay fairness. Với test cancellation, callback bất đồng bộ hoặc code phụ thuộc executor, có thể cấu hình executor riêng và đồng bộ test bằng latch/future thay vì sleep.

Không dùng `Thread.sleep()` để chờ callback. Hãy chờ bằng `CountDownLatch`, `CompletableFuture` hoặc assertion có timeout để test có điều kiện kết thúc rõ ràng.

## 8. Kiểm tra status và lỗi gRPC mà không mở port

Service adapter nên chuyển lỗi domain thành gRPC status có ý nghĩa. In-process stub cho phép kiểm tra status mà không cần network:

~~~java
@Test
void mapsMissingOrderToNotFound() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getOrder(
                    GetOrderRequest.newBuilder()
                            .setOrderId("missing")
                            .build()));

    assertEquals(Status.Code.NOT_FOUND, error.getStatus().getCode());
}
~~~

Test này kiểm tra hành vi mà client quan sát được: RPC kết thúc với `NOT_FOUND`. Nó không cần kiểm tra exception nội bộ cụ thể của repository nếu exception đó là chi tiết triển khai.

Với metadata, có thể gửi metadata qua `MetadataUtils`/stub interceptor và xác minh server interceptor đưa principal hoặc correlation context vào handler đúng cách. Cần kiểm tra cả trường hợp metadata thiếu, sai định dạng và không hợp lệ.

## 9. Kiểm tra unary và streaming RPC

Unary RPC trả đúng một response rồi kết thúc. Server streaming có thể trả nhiều response trước khi hoàn tất. In-process transport giúp kiểm tra contract và terminal signal:

~~~java
@Test
void serverStreamingEmitsAllItemsThenCompletes() {
    List<OrderUpdate> updates = new ArrayList<>();
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    stub.watchOrder(
            WatchOrderRequest.newBuilder()
                    .setOrderId("order-42")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(OrderUpdate value) {
                    updates.add(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    completed.countDown();
                }

                @Override
                public void onCompleted() {
                    completed.countDown();
                }
            });

    assertTrue(await(completed, 2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals(3, updates.size());
}
~~~

Đây là ví dụ rút gọn; helper `await` nên chuyển interrupt thành trạng thái test phù hợp và không nuốt lỗi. Nếu callback có thể chạy đồng thời, dùng collection thread-safe hoặc đồng bộ truy cập. Test phải xác minh server chỉ phát một terminal signal và không gọi `onNext` sau `onError`/`onCompleted`.

Với client streaming hoặc bidirectional streaming, test gửi lần lượt request qua `StreamObserver`, kiểm tra server xử lý nhiều message, backpressure/application flow và terminal signal. In-process giúp kiểm tra luồng API, nhưng không đo kích thước frame, TCP buffering hoặc HTTP/2 flow control thực tế.

## 10. Test interceptor và metadata ở ranh giới gRPC

Interceptor là phần của contract runtime nên có thể kiểm tra bằng in-process server. Các trường hợp đáng kiểm tra:

- Metadata hợp lệ được đọc đúng.
- Metadata thiếu hoặc sai định dạng trả status phù hợp.
- Authentication interceptor tạo principal đúng và không để lộ token trong log.
- Correlation ID được đưa vào `io.grpc.Context`.
- Server interceptor gọi tiếp handler đúng một lần.
- Exception trong interceptor được map thành gRPC status.
- Client interceptor thêm header đúng một lần cho mỗi call.

Đừng chỉ kiểm tra một helper parser nếu mục tiêu là xác minh interceptor đã được gắn vào server. Một test in-process gọi generated stub qua server đã đăng ký interceptor sẽ phát hiện trường hợp interceptor không nằm trong chain.

## 11. Kiểm tra deadline và cancellation

In-process transport phù hợp để kiểm tra hành vi gRPC ở mức call:

~~~java
@Test
void clientDeadlineIsObservedByServer() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> slowStub.withDeadlineAfter(20, TimeUnit.MILLISECONDS)
                    .getOrder(request));

    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            error.getStatus().getCode());
}
~~~

Test cần một service test double có thể chờ có kiểm soát và cleanup chắc chắn. Không dùng sleep dài để tạo timeout; có thể dùng latch hoặc future được điều khiển để tái hiện việc server chậm.

Cancellation của RPC không tự rollback database hoặc thu hồi message đã publish. Unit test use case phải kiểm tra riêng chính sách hủy nghiệp vụ; integration test cần kiểm chứng behavior khi side effect đã commit. In-process test chỉ xác minh cancellation được truyền trong call và handler phản ứng theo code đã viết.

## 12. Kiểm tra downstream gRPC client bằng in-process server

Nếu use case gọi một gRPC service khác, có thể tạo một in-process server cho downstream để kiểm tra adapter/client integration mà không mở TCP:

~~~text
Test subject
    |
    v
Generated downstream stub
    |
    v
InProcessChannel
    |
    v
InProcessServer
    |
    v
Fake downstream service
~~~

Fake downstream service có thể trả success, `UNAVAILABLE`, `NOT_FOUND` hoặc phản hồi chậm có kiểm soát. Test subject cần ánh xạ status và kết quả đúng. Cách này xác minh việc dùng generated stub, deadline, metadata và mapping lỗi qua gRPC API.

Không cần mock mọi method của generated stub. Một fake service thật qua in-process transport thường kiểm tra được nhiều hành vi hợp đồng hơn, đồng thời ít phụ thuộc chi tiết nội bộ của stub.

## 13. Khi nào vẫn cần network thật?

Một số hành vi không thể được chứng minh bằng in-process transport:

| Hành vi | Vì sao cần integration test |
|---|---|
| TCP bind, port conflict, firewall, route | In-process không mở socket |
| DNS và service discovery | Không có bước resolve hostname thật |
| TLS, certificate, SNI, mTLS | Không thực hiện TLS handshake |
| ALPN và HTTP/2 negotiation | Không kiểm tra negotiation trên network |
| Proxy, ingress, service mesh | Không đi qua các thành phần này |
| Network interruption, packet loss, connection reset | Không mô phỏng đầy đủ network failure |
| Message broker delivery/ack/redelivery | Cần broker thật hoặc containerized broker |
| Database transaction/locking/migration | Fake repository không có semantics của database |
| Load, throughput và resource usage | In-process direct executor không đại diện production transport |

Hãy tạo một tập integration test nhỏ, có mục tiêu rõ, dùng port tạm (ví dụ port `0` nếu server builder hỗ trợ), certificate test và broker/database containerized khi cần. Không cố gắng biến mọi unit test thành integration test chỉ để tăng độ “thật”.

## 14. Phân biệt in-process test, mock server và embedded server

Các kỹ thuật này có mục đích khác nhau:

| Kỹ thuật | Điểm mạnh | Giới hạn |
|---|---|---|
| Gọi use case trực tiếp | Nhanh, cô lập logic nghiệp vụ | Không kiểm tra gRPC adapter |
| Mock/fake dependency | Kiểm soát lỗi và kết quả ngoài | Không chứng minh implementation thật của dependency |
| gRPC in-process server | Kiểm tra stub, service, status, metadata không cần TCP | Không kiểm tra TLS/HTTP2/network |
| Server thật trên port tạm | Kiểm tra socket và transport thật | Chậm hơn, cần cleanup và tránh port conflict |
| Testcontainers | Kiểm tra database/broker thật trong môi trường cô lập | Tốn thời gian và Docker/runtime |

Không nhầm in-process server với embedded network server. In-process không phải server Netty bind vào loopback; nó là transport riêng của gRPC Java.

## 15. Tổ chức test trong dự án Spring

Một cấu trúc hợp lý có thể chia test theo package hoặc source set:

~~~text
src/test/java/
  .../domain/
    CreateOrderUseCaseTest.java
  .../application/
    SubmitOrderHandlerTest.java
  .../grpc/
    OrdersGrpcServiceTest.java
    CorrelationInterceptorTest.java
  .../integration/
    OrdersGrpcTcpIntegrationTest.java
    OrdersGrpcTlsIntegrationTest.java
    OrderMessagingIntegrationTest.java
~~~

Unit test domain/application không cần `@SpringBootTest`. Khởi động toàn bộ Spring context cho một class thuần Java sẽ làm test chậm và khiến lỗi wiring lẫn với lỗi logic.

Với component cần kiểm tra dependency injection, dùng Spring test slice hoặc context tối thiểu nếu phù hợp. Chỉ dùng `@SpringBootTest` khi mục tiêu thực sự là xác minh wiring toàn ứng dụng hoặc một integration path. Không khởi động embedded server trên port cố định trong nhiều test chạy song song.

Nếu Spring gRPC starter cung cấp test support riêng ở phiên bản dự án, có thể dùng nó để tạo server/channel test. Nếu không, gRPC Java in-process builders là một lựa chọn rõ ràng; tránh giả định mọi starter đều có cùng annotation hoặc auto-configuration cho test.

## 16. Quản lý lifecycle và tính ổn định của test

Test không dùng network thật vẫn có thể rò tài nguyên nếu không dọn channel/server:

- Tạo server/channel theo fixture hoặc test class với scope rõ.
- Shutdown channel và server trong `@AfterEach`/`@AfterAll`.
- Không chia sẻ mutable service state giữa test song song nếu chưa thread-safe.
- Dùng tên in-process server duy nhất.
- Tránh sleep; đồng bộ bằng future/latch.
- Giới hạn timeout để test lỗi không treo suite.
- Không để executor hoặc scheduler do test tạo tiếp tục chạy sau khi test kết thúc.

Với test dùng `directExecutor`, kiểm tra lại những luồng phụ thuộc concurrency bằng executor thực tế trong một test riêng. Một test chạy ổn trên direct executor không chứng minh code không có race trong production.

## 17. Ví dụ chiến lược test cho một RPC

Giả sử `GetOrder` nhận `orderId`, xác thực caller, đọc repository và trả protobuf response:

| Câu hỏi cần kiểm tra | Cấp độ phù hợp | Cách kiểm tra |
|---|---|---|
| `orderId` rỗng bị từ chối? | Unit test use case/validator | Gọi trực tiếp và assert exception |
| Repository trả đúng order? | Unit test use case | In-memory fake |
| Adapter map order sang protobuf đúng? | In-process gRPC test | Generated stub gọi service |
| Không tìm thấy order trả `NOT_FOUND`? | In-process gRPC test | Assert gRPC status code |
| Interceptor chặn caller thiếu token? | In-process gRPC test | Gọi qua server có interceptor |
| Server bind port và TLS certificate đúng? | Integration test | Server thật và client TLS |
| Kubernetes Service route đến pod? | Environment test | Probe từ pod/client trong cluster |

Một RPC có thể có nhiều test ở các tầng khác nhau, nhưng mỗi test nên xác minh một câu hỏi cụ thể. Không lặp lại toàn bộ ma trận network trong từng test nghiệp vụ.

## 18. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Mở TCP server cho mọi unit test | Test chậm, phụ thuộc port và môi trường | Gọi use case trực tiếp hoặc dùng in-process |
| Mock generated stub quá sâu | Test gắn chặt implementation và bỏ qua gRPC semantics | Dùng in-process fake service khi cần kiểm tra RPC |
| Dùng in-process test để kết luận TLS hoạt động | Không có TLS handshake | Tạo integration test TLS riêng |
| Dùng fake repository để kết luận transaction đúng | Fake không mô phỏng isolation/locking | Kiểm tra bằng database integration test |
| Dùng `Thread.sleep()` chờ callback | Flaky và kéo dài suite | Dùng latch/future với timeout |
| Không shutdown channel/server | Rò executor và làm test khác bị ảnh hưởng | Cleanup rõ trong lifecycle |
| Chạy toàn bộ test bằng `@SpringBootTest` | Startup chậm và khó định vị lỗi | Chọn unit, slice, in-process hoặc integration theo mục tiêu |
| Dùng `directExecutor` để kiểm tra concurrency | Không đại diện scheduling production | Test concurrency riêng với executor phù hợp |
| Chạy integration test với port cố định | Xung đột khi chạy song song | Dùng port tạm và discover port thực tế |

**Ghi nhớ:** Không dùng network thật cho mọi unit test. Gọi trực tiếp domain/use case để kiểm tra logic; dùng fake/mock ở ranh giới dependency; dùng gRPC in-process server/channel để kiểm tra generated stub, service adapter, status, metadata và streaming mà không mở TCP. Giữ một tập integration test nhỏ cho TCP, TLS, HTTP/2, proxy, database và broker—những hành vi mà in-process không thể xác minh.
