# Tránh port cố định và test phụ thuộc thứ tự

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao port cố định gây xung đột khi chạy integration test.
- Để hệ điều hành cấp port động cho gRPC server và lấy port sau khi bind thành công.
- Tạo client channel sau khi Spring test context và gRPC server đã sẵn sàng.
- Phân biệt port động với việc cô lập dữ liệu, state và tài nguyên giữa các test.
- Viết test không phụ thuộc thứ tự chạy, không dựa vào Thread.sleep và không dùng state toàn cục.
- Tổ chức test chạy song song khi server, channel và dependency có vòng đời rõ ràng.
- Biết khi nào dùng Spring context cache, @DirtiesContext và JUnit resource lock.

## 1. Vì sao port cố định làm test thiếu ổn định?

Một integration test gRPC cần client kết nối tới host và port mà server đang lắng nghe. Nếu mọi test đều giả định server dùng port 9090, test có thể thất bại khi port đó đang được ứng dụng khác sử dụng, khi một test khác chưa dừng server cũ hoặc khi nhiều application context khởi động đồng thời.

Port cố định còn tạo phụ thuộc môi trường: máy lập trình có thể đang trống port, nhưng CI agent hoặc một job song song có thể đã chiếm port. Lỗi thường xuất hiện ngẫu nhiên dưới dạng bind failure, connection refused hoặc test kết nối nhầm tới một server cũ.

Với **SPRING_GRPC**, mỗi integration test cần kết nối đúng gRPC listener của application context. Port của HTTP server Spring Boot, management endpoint và gRPC server có thể khác nhau. Dùng nhầm web port sẽ không kiểm tra được gRPC transport.

## 2. Để chính gRPC server bind port động

gRPC Java cho phép truyền port 0 vào ServerBuilder. Hệ điều hành chọn một port khả dụng trong lúc server bind:

~~~java
Server server = NettyServerBuilder.forPort(0)
    .addService(greeterService)
    .build()
    .start();

int actualPort = server.getPort();
~~~

Port 0 chỉ là yêu cầu cấp phát. Client phải dùng giá trị getPort() sau khi start thành công. Không đọc port từ cấu hình 0 rồi dùng số 0 để tạo channel.

Không nên mở ServerSocket(0), đọc port rồi đóng socket trước khi gRPC server bind. Một tiến trình khác có thể chiếm port trong khoảng giữa hai thao tác. Hãy để chính gRPC server bind port 0 và công bố port thực tế sau khi start.

## 3. Sơ đồ vòng đời test với port động

~~~mermaid
flowchart TD
  A["Spring tạo test context"] --> B["gRPC server bind port 0"]
  B --> C["Server start thành công"]
  C --> D["Fixture công bố port thực tế"]
  D --> E["Test tạo ManagedChannel"]
  E --> F["Test gọi RPC và assert"]
  F --> G["Test đóng channel"]
  G --> H["Spring đóng server khi context kết thúc"]
~~~

Điểm mấu chốt là thứ tự: server phải bind xong trước khi client channel được tạo. Test không nên tự đoán thời điểm server sẵn sàng bằng một khoảng sleep cố định.

## 4. Tạo server fixture có port động

Khi test tự quản lý server, có thể tạo fixture Spring với init/destroy method:

~~~java
final class TestGrpcServer {
    private final List<BindableService> services;
    private volatile Server server;

    TestGrpcServer(List<BindableService> services) {
        this.services = List.copyOf(services);
    }

    synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        ServerBuilder<?> builder = NettyServerBuilder.forPort(0);
        services.forEach(builder::addService);

        try {
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException(
                "gRPC test server is not running");
        }
        return current.getPort();
    }

    synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
                if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "gRPC test server did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đăng ký fixture trong test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcTestConfiguration {
    @Bean(initMethod = "start", destroyMethod = "stop")
    TestGrpcServer testGrpcServer(
            GreeterServiceImpl greeter,
            CatalogServiceImpl catalog) {
        return new TestGrpcServer(List.of(greeter, catalog));
    }
}
~~~

Spring khởi động fixture sau khi inject service bean và gọi stop khi context đóng. Fixture bind port động, đăng ký các service vào cùng server và công bố port thật qua port().

Đây là cách dùng khi test sở hữu server. Nếu Spring gRPC starter đã tự khởi động server, hãy dùng cấu hình port động và API/test support của starter để đọc port thực tế. Không tạo server thứ hai cho cùng service chỉ để lấy một port riêng.

## 5. Lấy đúng gRPC port trong Spring test

Test tạo channel sau khi Spring context refresh hoàn tất:

~~~java
@SpringBootTest
@Import(GrpcTestConfiguration.class)
class GreeterIntegrationTest {
    @Autowired
    TestGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeClient() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Port accessor trong ví dụ thuộc fixture. Nếu starter quản lý server, thay bằng accessor được starter cung cấp; không giả định @LocalServerPort là gRPC port vì annotation đó thường đại diện web server port.

Channel được tạo sau khi fixture start. Deadline hữu hạn giúp test kết thúc rõ ràng nếu server chưa sẵn sàng hoặc handler bị treo. Channel do test tạo nên được đóng trong teardown.

## 6. Port động không có nghĩa port mới cho mỗi test method

Spring Test có thể cache ApplicationContext để tái sử dụng giữa nhiều test class có cấu hình tương thích. Nếu gRPC server là bean trong context, server có thể tiếp tục chạy trên cùng port động trong suốt vòng đời context.

Điều đó là bình thường:

- Port được cấp khi server fixture start.
- Các test method dùng chung context có thể dùng cùng port.
- Mỗi test method vẫn có thể tạo channel riêng rồi đóng channel đó.
- Khi context bị đóng, Spring dừng server; context mới có thể nhận port khác.

Không viết assertion rằng port phải đổi sau mỗi test method. Mục tiêu của port động là tránh xung đột giữa listener đang chạy, không phải ép server restart liên tục.

Nếu test cần server state hoàn toàn riêng, hãy tạo context/fixture riêng hoặc reset state có kiểm soát. Không dựa vào việc port thay đổi để thay thế test isolation.

## 7. Vì sao test phụ thuộc thứ tự?

Một test phụ thuộc thứ tự khi nó chỉ pass nếu test khác đã chạy trước để tạo dữ liệu, reset counter hoặc thay đổi trạng thái dùng chung. Những phụ thuộc thường gặp:

- Database có record còn lại từ test trước.
- Spring singleton service giữ mutable state hoặc cache.
- Static field, global counter hoặc singleton test fixture không được reset.
- HealthStatusManager còn NOT_SERVING từ test trước.
- Một test đóng channel/server dùng chung mà test sau vẫn cần.
- Test dựa vào thứ tự tạo ID, thời gian hoặc dữ liệu ngẫu nhiên.
- Test async kết thúc trước khi callback/worker hoàn tất.

Chạy riêng một test thường không phát hiện vấn đề này. Test có thể pass đơn lẻ nhưng fail khi chạy cả suite hoặc khi JUnit thực thi song song.

## 8. Mỗi test phải tự chuẩn bị dữ liệu cần thiết

Test nên tạo dữ liệu đầu vào riêng và không giả định record đã được test khác tạo:

~~~java
@Test
void createsAndReadsItsOwnOrder() {
    String testId = UUID.randomUUID().toString();
    String orderId = "it-" + testId;

    CreateOrderReply created = orderStub.createOrder(
        CreateOrderRequest.newBuilder()
            .setOrderId(orderId)
            .setCustomerId("customer-" + testId)
            .build());

    assertEquals(orderId, created.getOrderId());

    OrderReply loaded = orderStub.getOrder(
        GetOrderRequest.newBuilder()
            .setOrderId(orderId)
            .build());

    assertEquals(orderId, loaded.getOrderId());
}
~~~

ID riêng giúp các test chạy đồng thời không ghi đè dữ liệu của nhau. Dữ liệu tạo ra cần được xóa hoặc namespace theo test run để không tích lũy trong database dùng chung.

Không dùng dữ liệu cố định như order-1 trong mọi test nếu database được chia sẻ giữa test method hoặc CI job. Nếu ID cố định là một phần của contract test, hãy dùng database/schema riêng hoặc fixture reset có kiểm soát.

## 9. Cleanup dữ liệu không phụ thuộc transaction của test

Với Spring integration test, không nên mặc định @Transactional trên test sẽ rollback mọi thay đổi do gRPC service thực hiện. RPC có thể chạy trên server thread và transaction khác với transaction gắn trên test thread. Giao dịch của test không tự động bao trùm lời gọi qua TCP.

Các cách cô lập dữ liệu đáng tin cậy:

- Dùng database/schema/container riêng cho test suite hoặc test class.
- Tạo record với namespace/test ID duy nhất.
- Gọi API cleanup rõ ràng trong @AfterEach hoặc fixture teardown.
- Dùng transaction ở tầng service/repository theo đúng ranh giới nghiệp vụ.
- Reset cache/test state bằng API dành riêng cho test.

Nếu dùng Testcontainers hoặc dịch vụ ngoài, quản lý vòng đời container và endpoint riêng. Testcontainers có thể cấp port host động; lấy mapped port từ container thay vì hard-code cổng host.

## 10. Không dùng test order để che state bị rò

JUnit cho phép chỉ định thứ tự test, nhưng @TestMethodOrder không nên là cách sửa một test phụ thuộc test khác. Nếu test B chỉ pass sau test A, test B chưa tự chuẩn bị dữ liệu hoặc test A chưa cleanup state của nó.

Chỉ dùng thứ tự tường minh khi thứ tự là hành vi đang được kiểm thử, ví dụ một scenario state machine gồm nhiều bước có chủ đích. Với các integration test độc lập, mỗi test phải tự tạo precondition và dọn dữ liệu nó sở hữu.

Một cách kiểm tra hữu ích là chạy test class riêng, chạy toàn suite, đảo thứ tự hoặc bật random order trong môi trường test. Nếu kết quả đổi theo thứ tự, tìm shared state thay vì thêm annotation ép thứ tự.

## 11. Tránh state mutable dùng chung trong Spring singleton

Spring service bean thường là singleton. Điều đó phù hợp với dependency stateless hoặc thread-safe, nhưng dễ làm test phụ thuộc nhau nếu implementation giữ state theo request trong field:

~~~java
// Không an toàn nếu field này đại diện dữ liệu của từng RPC.
@Service
final class GreeterServiceImpl extends GreeterGrpc.GreeterImplBase {
    private String lastRequestName;
}
~~~

Dữ liệu theo call nên nằm trong local variable hoặc object context riêng của call. Nếu cần cache dùng chung, định nghĩa eviction/reset và concurrency semantics rõ ràng. Không để test thay đổi state singleton mà không khôi phục trước khi kết thúc.

Với test cần thay đổi health status, interceptor policy hoặc server-wide config, cân nhắc context riêng. Nếu server dùng chung qua context cache, một test không nên tạm đổi trạng thái toàn server trong lúc test khác đang chạy.

## 12. Chạy test song song an toàn

Port động loại bỏ một nguồn xung đột socket, nhưng không tự làm test an toàn khi chạy song song. Cần kiểm tra riêng:

- Mỗi test sở hữu channel riêng hoặc dùng channel chia sẻ có lifecycle rõ.
- Server dùng chung không bị shutdown/reset từ test method.
- Test data có ID/schema riêng.
- Mutable singleton state được đồng bộ hoặc không chia sẻ.
- File, queue, counter và temporary directory không dùng chung tên.
- Health state hoặc cấu hình toàn server không bị test khác thay đổi giữa call.

Chỉ bật @Execution(CONCURRENT) sau khi test độc lập và resource ownership đã rõ. Nếu một test thật sự cần độc quyền một resource dùng chung, có thể dùng JUnit @ResourceLock hoặc chạy test đó tuần tự. Resource lock là cơ chế đồng bộ có chủ đích, không phải thay thế cleanup.

## 13. Chờ readiness bằng tín hiệu, không bằng sleep

Sau khi server bind port, service vẫn có thể chưa sẵn sàng vì dependency chưa kết nối hoặc dữ liệu chưa được nạp. Không dùng Thread.sleep(1000) để hy vọng server đã sẵn sàng.

Thay vào đó:

- Đợi Spring context refresh và server lifecycle start hoàn tất.
- Dùng health Check/Watch nếu ứng dụng có health service.
- Đợi một readiness condition hoặc latch do fixture công bố.
- Đặt deadline cho RPC và timeout hữu hạn cho thao tác chờ.
- Nếu điều kiện không đạt, fail với thông tin port, server state và dependency liên quan.

Readiness cần phản ánh khả năng xử lý RPC. Một socket mở không đồng nghĩa service đã sẵn sàng.

## 14. @DynamicPropertySource và port được cấp trong context

@DynamicPropertySource phù hợp để đưa endpoint được tạo trước ApplicationContext vào cấu hình Spring, ví dụ mapped port của Testcontainers hoặc một dịch vụ phụ đã start bên ngoài context.

Nếu chính gRPC server được tạo bên trong ApplicationContext, @DynamicPropertySource chạy trước khi bean server được tạo. Vì vậy không thể lấy port từ bean đó trong callback này. Với server nội bộ context, inject port accessor rồi tạo channel sau khi context refresh, ví dụ trong @BeforeEach.

Nếu starter nhận cấu hình port 0, hãy cấu hình bằng property đúng của starter/phiên bản và đọc port thực tế qua API test support. Giá trị cấu hình 0 không phải endpoint mà client dùng để kết nối.

## 15. Khi nào dùng @DirtiesContext?

@DirtiesContext yêu cầu Spring loại context khỏi cache và đóng các bean lifecycle thuộc context. Điều này hữu ích khi test làm thay đổi cấu hình hoặc state không thể reset an toàn, hoặc khi cần xác minh context/server shutdown.

Không dùng @DirtiesContext chỉ để đóng channel do test tạo; hãy đóng channel trực tiếp. Dùng annotation cho mọi test method làm suite chậm vì Spring phải khởi động lại context và server nhiều lần.

Nếu server fixture là bean do Spring quản lý, để destroy method/SmartLifecycle dừng server khi context đóng. Không gọi stop ở @AfterEach nếu context có thể được tái sử dụng.

## 16. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng port cố định cho mọi test | Bind collision khi suite chạy song song | Bind server bằng port 0 và lấy port thực tế. |
| Mở ServerSocket để dò port rồi đóng | Race trước khi gRPC server bind | Để gRPC server tự bind port 0. |
| Dùng @LocalServerPort làm gRPC port | Client kết nối nhầm web listener | Lấy port từ gRPC server/starter accessor. |
| Cho rằng port đổi sau mỗi method | Assertion sai khi Spring cache context | Hiểu port gắn với vòng đời server/context. |
| Dùng chung ID và dữ liệu test | Test ghi đè hoặc đọc dữ liệu cũ | Namespace dữ liệu theo test/run. |
| Dựa vào @Transactional để rollback RPC qua TCP | Dữ liệu server có thể vẫn được commit | Cleanup tại service/database fixture. |
| Dùng @TestMethodOrder để che phụ thuộc | Test fail khi chạy riêng hoặc đổi thứ tự | Tự chuẩn bị precondition cho từng test. |
| Reset server/shared singleton trong @AfterEach | Phá test đang chạy đồng thời | Cô lập context hoặc đồng bộ resource. |
| Bật concurrent execution quá sớm | Race trong state, DB và fixture | Xác minh ownership/isolation trước. |
| Dùng Thread.sleep để đợi readiness | Test flaky và chậm | Dùng health/readiness signal và timeout. |
| Lạm dụng @DirtiesContext | Suite khởi động context liên tục | Đóng resource do test sở hữu trực tiếp. |

## 17. Ma trận kiểm thử độc lập

Một bộ integration test ổn định nên được xác minh theo các chiều:

1. **Port**: hai server fixture đồng thời bind port động mà không xung đột.
2. **Context cache**: nhiều test dùng chung context có thể gọi server; channel từng test được đóng riêng.
3. **Data isolation**: test tạo record riêng và không đọc dữ liệu do test khác tạo.
4. **Order independence**: mỗi test pass khi chạy riêng và khi đảo thứ tự trong suite.
5. **Parallel execution**: test chạy đồng thời không sửa cùng state/database record.
6. **Readiness**: client chỉ gọi sau khi server/service sẵn sàng, có timeout rõ.
7. **Failure cleanup**: test fail giữa setup vẫn đóng channel và dữ liệu tạm.
8. **Server lifecycle**: Spring/starter dừng server khi context đóng, không phải sau từng method dùng chung context.

Port động chỉ giải quyết xung đột listener. Phải kiểm tra riêng data isolation, shared state, readiness và lifecycle mới kết luận test không phụ thuộc thứ tự.

## 18. Bài tập thực hành

Tổ chức lại integration test cho hai service Greeting và Catalog:

1. Bỏ mọi port cố định; cấu hình server tự bind port 0 hoặc dùng port động của starter.
2. Expose port thực tế sau khi server start và tạo channel trong @BeforeEach.
3. Đóng channel trong @AfterEach; để Spring quản lý server nếu context được cache.
4. Tạo customer/order ID riêng cho từng test thay vì dùng record cố định.
5. Xóa dữ liệu test trong teardown hoặc dùng schema/container riêng.
6. Loại bỏ phụ thuộc vào @TestMethodOrder và Thread.sleep.
7. Chạy từng test riêng, chạy cả suite và bật parallel execution cho nhóm test đã cô lập.
8. Dùng @ResourceLock hoặc context riêng cho test phải thay đổi server-wide state.
9. Xác minh test fail giữa setup vẫn cleanup channel và dữ liệu.

**Tiêu chí hoàn thành:** không có port hard-code, mỗi test tự chuẩn bị dữ liệu, channel có lifecycle riêng, server theo lifecycle Spring và kết quả không đổi theo thứ tự hoặc chế độ chạy song song được hỗ trợ.

## 19. Ghi nhớ

- Bind gRPC server bằng port 0 và đọc port thực tế sau khi start.
- Không dò port bằng cách mở rồi đóng ServerSocket trước khi server bind.
- Port động tránh xung đột listener nhưng không tự cô lập dữ liệu hoặc state.
- Spring context cache có thể giữ server và port qua nhiều test method; không mong port đổi sau từng method.
- Tạo channel theo phạm vi test và đóng channel do test sở hữu.
- Mỗi test tự tạo precondition, dùng ID riêng và cleanup dữ liệu nó tạo.
- Không dựa vào @Transactional để rollback side effect của RPC chạy trên server thread khác.
- Tránh @TestMethodOrder, Thread.sleep và mutable singleton state làm test phụ thuộc thứ tự.
- Chỉ chạy song song khi server, channel, database và shared state có ownership/isolation rõ.
- Dùng readiness signal và timeout thay vì đoán thời gian khởi động.
- Để Spring/starter dừng server khi context đóng; chỉ dùng @DirtiesContext khi thật sự cần loại context khỏi cache.

Tránh port cố định và test phụ thuộc thứ tự giúp integration test Spring gRPC chạy ổn định trên máy lập trình lẫn CI, có thể chạy song song và cho kết quả nhất quán khi thứ tự test thay đổi.
