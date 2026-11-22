# Khởi động gRPC server trong test context

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách Spring Test tạo và quản lý application context cho một integration test.
- Khởi động gRPC server sau khi các service bean đã sẵn sàng và dừng server khi context đóng.
- Dùng cổng động để tránh xung đột port giữa các lần chạy test.
- Tạo ManagedChannel và stub kết nối tới server đang chạy trong test context.
- Phân biệt kiểm thử qua TCP thật với in-process transport.
- Quản lý channel, server lifecycle, context cache và test isolation trong Spring Boot.

## 1. Vì sao cần khởi động server trong test context?

Unit test một service implementation có thể gọi trực tiếp method Java, nhưng cách đó không kiểm tra quá trình một gRPC call đi qua server. Một integration test cần xác minh service đã được Spring tạo đúng, gRPC đăng ký service, server mở cổng, client kết nối được và message đi qua serialization, HTTP/2 transport cùng status handling.

Với **SPRING_GRPC**, server cần truy cập các dependency do Spring quản lý như repository, service nghiệp vụ, interceptor và cấu hình. Khởi động server trong Spring test context giúp kiểm tra các thành phần đó cùng nhau.

Mục tiêu là để Spring quản lý vòng đời server: context được refresh thì server bắt đầu lắng nghe; context đóng thì server dừng và giải phóng tài nguyên. Test chỉ cần tạo client channel tới cổng server đang chạy.

## 2. Vòng đời Spring test context

**@SpringBootTest** tạo application context gần với cấu hình ứng dụng thực tế. Spring khởi tạo bean, inject dependency, áp dụng cấu hình và hoàn tất refresh trước khi chạy các method test.

Nếu gRPC server được đăng ký như một lifecycle bean hoặc do starter tự quản lý, server sẽ khởi động trong quá trình context refresh. Khi Spring đóng context, lifecycle bean nhận tín hiệu stop để dừng server.

~~~mermaid
flowchart TD
  A["JUnit bắt đầu test class"] --> B["Spring tạo ApplicationContext"]
  B --> C["Tạo service và dependency beans"]
  C --> D["Refresh context / start lifecycle"]
  D --> E["gRPC server bind port"]
  E --> F["Test tạo channel và gọi RPC"]
  F --> G["Test đóng channel"]
  G --> H["Spring đóng ApplicationContext"]
  H --> I["gRPC server shutdown"]
~~~

Không nên tự start server trong mọi **@BeforeEach** nếu Spring đã quản lý server. Cách đó có thể tạo nhiều server, bind trùng port hoặc để server cũ không được dừng khi test kết thúc.

## 3. Ưu tiên server lifecycle do starter quản lý

Nếu ứng dụng dùng Spring gRPC starter có auto-configuration, hãy để starter đăng ký service và khởi động server. Trong test:

- Nạp application context bằng **@SpringBootTest**.
- Cấu hình server dùng port động theo property mà đúng phiên bản starter hỗ trợ.
- Lấy cổng thực tế từ cơ chế test support hoặc server lifecycle API mà starter cung cấp.
- Tạo **ManagedChannel** tới cổng đó.
- Để Spring đóng server khi context bị đóng.

Tên property, annotation lấy local port và API truy cập server phụ thuộc starter/phiên bản. Ví dụ **spring.grpc.server.port** chỉ phù hợp với các phiên bản Spring gRPC dùng namespace cấu hình đó; starter khác có thể dùng tên khác. Kiểm tra đúng tài liệu của dependency trong dự án, không sao chép property của starter này sang starter khác.

Không đăng ký thêm một server test riêng nếu auto-configuration đã khởi động server cho cùng service và port. Một test context chỉ nên có một chủ sở hữu rõ ràng cho server cần kiểm tra.

## 4. Test fixture tự quản lý server bằng Spring lifecycle

Khi dự án không dùng starter auto-start server hoặc cần một fixture độc lập, có thể đăng ký server test như một bean **SmartLifecycle**. Spring sẽ gọi **start()** trong quá trình refresh và **stop()** khi context đóng.

Ví dụ fixture:

~~~java
import io.grpc.BindableService;
import io.grpc.Server;
import io.grpc.ServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.springframework.context.SmartLifecycle;

final class TestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private volatile Server server;

    TestGrpcServer(BindableService service) {
        this.service = service;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }
        try {
            server = ServerBuilder.forPort(0)
                .addService(service)
                .build()
                .start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start test gRPC server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }

        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

**ServerBuilder.forPort(0)** yêu cầu hệ điều hành cấp một port còn trống. Sau khi start, **Server.getPort()** trả port thực tế để client test kết nối. **stop()** dừng server graceful trước, rồi mới dùng **shutdownNow()** nếu server không kết thúc trong thời hạn.

Fixture này là lựa chọn cho test context tự sở hữu server. Nếu starter đã quản lý server, dùng lifecycle/port accessor của starter thay vì đăng ký fixture thứ hai.

## 5. Đăng ký fixture trong test configuration

Tạo test configuration để Spring inject service implementation và quản lý fixture:

~~~java
import io.grpc.BindableService;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class GrpcTestServerConfiguration {
    @Bean
    TestGrpcServer testGrpcServer(BindableService greeterService) {
        return new TestGrpcServer(greeterService);
    }
}
~~~

Trong dự án thực tế, kiểu bean có thể là class service cụ thể kế thừa generated **GreeterGrpc.GreeterImplBase**. Dùng kiểu cụ thể trong tham số bean nếu context có nhiều BindableService để Spring chọn đúng service. Đảm bảo service bean được tạo bởi component scan hoặc khai báo trong test configuration.

Không dùng test configuration này cùng lúc với auto-config server đang bind cùng service/port. Chọn một cách quản lý server duy nhất cho test.

## 6. Tạo channel sau khi server đã start

Test có thể inject fixture và tạo channel trong **@BeforeEach**:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

@SpringBootTest
@Import(GrpcTestServerConfiguration.class)
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
    void closeChannel() throws InterruptedException {
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

Spring hoàn tất refresh và khởi động **SmartLifecycle** trước khi JUnit chạy **@BeforeEach**, vì vậy **grpcServer.port()** đã sẵn sàng. Dùng **127.0.0.1** giúp test tránh khác biệt phân giải IPv4/IPv6 của **localhost** trên một số môi trường.

**usePlaintext()** chỉ phù hợp với fixture TCP cục bộ không bật TLS. Nếu mục tiêu test bao gồm TLS, tạo channel bằng trust certificate và cấu hình bảo mật tương ứng; không vô tình kiểm thử plaintext rồi kết luận TLS hoạt động.

## 7. Gọi RPC và kiểm tra kết quả thật

Một test unary có thể gọi blocking stub:

~~~java
@Test
void invokesSpringManagedGreeter() {
    HelloReply reply = stub.sayHello(
        HelloRequest.newBuilder()
            .setName("Lan")
            .build());

    assertEquals("Hello, Lan", reply.getMessage());
}
~~~

Đây là integration test qua TCP: request được serialize, truyền qua HTTP/2, server dispatch tới service bean, response được serialize và client parse lại. Có thể mở rộng để kiểm tra:

- Status code khi service ném lỗi.
- Interceptor, metadata và authentication.
- Deadline và cancellation.
- Unary và streaming RPC.
- Cấu hình TLS, compression và message-size limit.

Đặt deadline cho RPC test để lỗi không làm suite treo vô hạn. Deadline test nên đủ dài cho CI chậm nhưng vẫn ngắn hơn timeout tổng của test suite.

## 8. Quản lý channel và server riêng biệt

Channel và server có chủ sở hữu khác nhau:

| Thành phần | Ai tạo? | Ai đóng? |
| --- | --- | --- |
| Spring application context | Spring Test | Spring Test đóng khi context bị loại khỏi cache hoặc test kết thúc theo cấu hình. |
| gRPC server do starter quản lý | Starter/Spring lifecycle | Starter/Spring lifecycle. |
| **TestGrpcServer** fixture | Spring test configuration | Spring gọi **SmartLifecycle.stop()**. |
| Client **ManagedChannel** | Test hoặc test client bean | Test đóng sau mỗi test hoặc sau khi dùng xong. |
| Stub | Tạo từ channel | Không cần shutdown riêng; ngừng dùng khi channel đóng. |

Đừng gọi **server.shutdownNow()** trực tiếp từ từng test nếu server thuộc Spring context; việc đó làm các test khác dùng chung context nhận một server đã chết. Ngược lại, không để channel client mở qua nhiều test nếu mỗi test cần trạng thái kết nối độc lập.

## 9. Cổng động và tránh xung đột test

Không cố định port như **9090** cho integration test chạy song song. Một test khác hoặc tiến trình local có thể đang dùng port đó.

Với fixture gRPC Java, bind port **0** rồi đọc port đã cấp từ **Server.getPort()**. Với starter, cấu hình port động theo property hỗ trợ của phiên bản và lấy port thực tế qua test support tương ứng.

Không tự tìm một port rảnh bằng cách mở **ServerSocket(0)**, đọc port rồi đóng socket trước khi gRPC bind. Một tiến trình khác có thể chiếm port trong khoảng thời gian giữa hai thao tác. Hãy để chính gRPC server bind port 0.

Mỗi application context riêng có thể có một port động khác nhau. Nếu Spring Test cache context, server có thể tiếp tục chạy và được chia sẻ giữa các method/class dùng cùng context configuration; test không được tự ý dừng server dùng chung đó.

## 10. Context caching và test isolation

Spring Test thường cache application context để giảm thời gian suite. Điều đó có nghĩa:

- **@BeforeEach** và **@AfterEach** chạy cho từng test method.
- Server lifecycle bean thường sống cùng context, không start/stop lại cho từng method.
- Channel do test tạo có thể được đóng sau mỗi method.
- Mutable state trong singleton service có thể tồn tại giữa các method.

Nếu service giữ state nghiệp vụ, reset state bằng fixture/test API rõ ràng hoặc dùng context mới khi thật sự cần. **@DirtiesContext** buộc Spring loại context khỏi cache và đóng các bean lifecycle, nhưng làm suite chậm; chỉ dùng khi test đã làm context không thể tái sử dụng.

Với test chạy song song, bảo đảm service không chia sẻ mutable state không an toàn và test data có namespace riêng. Port động tránh xung đột bind nhưng không tự bảo đảm test isolation cho database, cache hoặc singleton bean.

## 11. Khi nào dùng in-process transport?

In-process server/channel có thể làm test nhanh hơn và tránh mở socket:

- Phù hợp cho kiểm tra service dispatch, stub, interceptor hoặc logic gRPC ở mức tích hợp nhẹ.
- Không kiểm tra TCP socket, bind port, HTTP/2 network path hoặc TLS handshake như một server TCP thật.
- Không nên dùng làm bằng chứng duy nhất rằng cấu hình server production có thể khởi động và nhận kết nối qua mạng.

Một chiến lược thực tế là dùng in-process cho nhiều test nhanh và giữ một nhóm integration test qua TCP để kiểm tra server lifecycle, port binding, transport và TLS khi cần. Hai loại test trả lời các câu hỏi khác nhau.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khởi động server thủ công trong mỗi **@BeforeEach** | Nhiều server hoặc rò rỉ thread/port | Để Spring lifecycle quản lý server theo context. |
| Dùng port cố định | Test song song hoặc tiến trình khác chiếm port | Dùng port 0 và đọc port thực tế. |
| Tạo test server thứ hai khi starter đã chạy server | Bind trùng port hoặc đăng ký service không nhất quán | Chỉ có một server owner trong context. |
| Đóng server từ từng test method | Test khác dùng chung context gặp server đã shutdown | Spring đóng server khi context đóng. |
| Không đóng **ManagedChannel** | Giữ thread và connection sau test | Shutdown channel trong teardown. |
| Dùng **usePlaintext()** để kết luận TLS đúng | Bỏ qua TLS handshake/certificate validation | Tạo test TLS riêng với certificate test. |
| Dựa vào port đã kiểm tra trước rồi mới bind | Race với tiến trình khác | Để server bind trực tiếp port 0. |
| Cho rằng context cache reset mọi state | Test phụ thuộc thứ tự chạy | Reset state nghiệp vụ hoặc dùng context riêng khi cần. |
| Chỉ dùng in-process test | Không kiểm tra TCP/HTTP2 server startup | Bổ sung integration test qua TCP thật. |

## 13. Bài tập thực hành

Tạo integration test cho service **Greeter** trong Spring Boot:

1. Khai báo service implementation là Spring bean.
2. Nạp application context bằng **@SpringBootTest**.
3. Chọn server lifecycle do starter quản lý hoặc một **SmartLifecycle** fixture; không chạy cả hai cho cùng server.
4. Bind port động và lấy port thực tế sau khi server start.
5. Tạo **ManagedChannel**, blocking stub và deadline.
6. Gọi unary RPC, xác nhận response và status lỗi.
7. Đóng channel sau mỗi test; xác nhận server dừng khi context bị đóng.
8. Chạy hai test context song song và xác nhận không có port collision.

**Tiêu chí hoàn thành:** server khởi động cùng test context, client kết nối được qua port động, channel được đóng đúng lúc và server được Spring dừng khi context đóng.

## 14. Ghi nhớ

- **@SpringBootTest** tạo context; server cần được quản lý bởi starter lifecycle hoặc một Spring lifecycle bean.
- Spring khởi động lifecycle sau khi bean đã được tạo và dừng lifecycle khi context đóng.
- Dùng port **0** để hệ điều hành cấp port; lấy port thực tế sau khi server start.
- Không tạo server fixture thứ hai nếu starter đã quản lý server trong cùng context.
- Client **ManagedChannel** thuộc trách nhiệm của test và cần shutdown rõ ràng.
- Context cache có thể giữ server sống qua nhiều test method; không đóng server dùng chung từ từng test.
- In-process transport nhanh nhưng không thay thế test TCP/HTTP2 hoặc TLS.
- Dùng deadline và test isolation để integration test ổn định trong CI.

Khởi động gRPC server đúng lifecycle trong Spring test context giúp integration test kiểm tra được wiring của bean, service registration và transport thật, đồng thời tránh xung đột port, thread và tài nguyên giữa các lần chạy.
