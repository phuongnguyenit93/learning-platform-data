# Dọn channel và server sau test

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt vòng đời của client ManagedChannel, gRPC Server và Spring ApplicationContext.
- Đóng channel graceful, chờ kết thúc và dùng shutdownNow khi hết thời hạn.
- Dừng server theo thứ tự an toàn, xử lý RPC đang chạy và xác minh server đã terminated.
- Hủy streaming call trước khi đóng channel.
- Để Spring quản lý server do starter hoặc lifecycle bean sở hữu.
- Viết teardown an toàn khi test pass, fail hoặc bị interrupt.
- Phát hiện channel, stream, thread và executor bị rò rỉ sau integration test.

## 1. Vì sao cleanup là một phần của integration test?

Một integration test gRPC tạo ra nhiều tài nguyên sống lâu hơn một lời gọi Java thông thường: ManagedChannel, HTTP/2 transport, connection, executor, server listener, streaming call và đôi khi cả worker thread của service. Nếu test không đóng đúng các tài nguyên này, suite có thể giữ socket/thread sau khi test kết thúc, làm port bị chiếm, test chạy sau bị ảnh hưởng hoặc JVM không thoát.

Trong **SPRING_GRPC**, cần phân biệt tài nguyên do test tạo với tài nguyên do Spring quản lý. Test thường sở hữu client channel; Spring context hoặc gRPC starter sở hữu server. Dọn channel ở teardown của test method không có nghĩa phải dừng server sau từng method, vì Spring Test có thể cache và dùng lại context.

Cleanup đúng phải có thời hạn, có thứ tự và có xác nhận. Gọi shutdown chỉ bắt đầu quá trình đóng; test cần đợi awaitTermination và có đường fallback khi tài nguyên không kết thúc.

## 2. Ai sở hữu tài nguyên nào?

| Tài nguyên | Chủ sở hữu thường gặp | Thời điểm cleanup |
| --- | --- | --- |
| Client ManagedChannel | Test hoặc client fixture | Sau khi mọi RPC/stream của test đã kết thúc. |
| Generated stub | Test, tạo từ channel | Không có close riêng; ngừng dùng khi channel đóng. |
| Client interceptor channel wrapper | Test, bọc channel gốc | Đóng channel gốc; wrapper không phải ManagedChannel độc lập. |
| gRPC Server do starter quản lý | Spring gRPC starter/Spring lifecycle | Khi ApplicationContext đóng. |
| Server fixture do test tự quản lý | Test fixture hoặc Spring test bean | Sau khi client channel đã đóng. |
| Streaming call | Test/client code | Cancel hoặc đợi terminal callback trước teardown. |
| Executor/service worker | Spring bean hoặc test fixture | Chủ sở hữu executor dừng sau khi công việc liên quan kết thúc. |

Không đóng tài nguyên chỉ vì đang giữ một reference tới nó. Hãy xác định ai tạo và ai chịu trách nhiệm dừng. Đặc biệt, không gọi shutdownNow trên server do starter quản lý từ @AfterEach; context có thể còn được chia sẻ với test khác.

## 3. ManagedChannel có hai giai đoạn shutdown

ManagedChannel.shutdown() bắt đầu graceful shutdown. Channel ngừng nhận call mới nhưng cho các call đang chạy cơ hội kết thúc. Sau đó gọi awaitTermination(timeout, unit) để chờ channel dừng trong một khoảng hữu hạn.

Nếu hết thời hạn mà channel chưa terminated, shutdownNow() yêu cầu hủy các call còn lại và đóng transport nhanh hơn. Có thể chờ thêm một khoảng ngắn để xác nhận channel đã kết thúc:

~~~java
static void closeChannel(ManagedChannel channel)
        throws InterruptedException {
    if (channel == null) {
        return;
    }

    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "ManagedChannel did not terminate");
        }
    }
}
~~~

Timeout trong ví dụ chỉ là giá trị test minh họa. Chọn timeout theo suite và môi trường CI; không chờ vô hạn vì một call bị treo có thể giữ toàn bộ tiến trình test.

shutdownNow() là biện pháp kết thúc cưỡng bức. Dùng nó như fallback sau graceful shutdown, không dùng mặc định nếu các RPC có thể hoàn tất bình thường.

## 4. Dọn channel trong JUnit và Spring Boot

Với channel được tạo cho từng test method, @AfterEach là nơi phù hợp để đóng:

~~~java
@SpringBootTest
class GreeterIntegrationTest {
    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcTestEndpoint.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        closeChannel(channel);
        channel = null;
        stub = null;
    }
}
~~~

Ví dụ giả định grpcTestEndpoint là port accessor của server đang chạy trong Spring context. Channel thuộc test và được đóng sau method. Server không bị dừng ở đây nếu nó thuộc context được Spring cache.

Nếu channel được tạo trong @BeforeAll và dùng chung cho toàn class, đóng trong @AfterAll. Không đóng channel sau từng method nếu các method sau vẫn sử dụng channel đó.

Stub không có close(). Stub là object nhẹ gắn với channel; đóng channel gốc sẽ giải phóng transport mà stub sử dụng.

## 5. Channel wrapper và interceptor

Khi dùng ClientInterceptors.intercept(channel, interceptor), kết quả là một Channel wrapper để gắn interceptor vào call. Wrapper này không phải một ManagedChannel mới và không có lifecycle shutdown riêng.

~~~java
ManagedChannel managedChannel = ManagedChannelBuilder
    .forAddress("127.0.0.1", grpcTestEndpoint.port())
    .usePlaintext()
    .build();

Channel intercepted = ClientInterceptors.intercept(
    managedChannel,
    new CorrelationIdClientInterceptor());

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(intercepted);

// Khi kết thúc test, đóng managedChannel.
closeChannel(managedChannel);
~~~

Giữ reference tới ManagedChannel gốc để cleanup. Không ép kiểu wrapper về ManagedChannel hoặc tìm cách đóng wrapper như một transport riêng.

## 6. Server shutdown graceful

Khi test tự sở hữu gRPC server, cleanup tương tự channel nhưng phải tính tới server đang xử lý call:

~~~java
static void closeServer(Server server)
        throws InterruptedException {
    if (server == null) {
        return;
    }

    server.shutdown();
    if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
        server.shutdownNow();
        if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "gRPC Server did not terminate");
        }
    }
}
~~~

Server.shutdown() bắt đầu graceful shutdown: server ngừng nhận call mới và cho call đang chạy cơ hội kết thúc. Server.shutdownNow() yêu cầu hủy các call còn hoạt động. Server chỉ được coi là đã dừng khi awaitTermination trả về true hoặc isTerminated() xác nhận trạng thái đó.

Không chỉ kiểm tra isShutdown(): trạng thái shutdown có thể đã được yêu cầu trong khi server vẫn đang hoàn tất call và giải phóng tài nguyên. Nếu cần chắc chắn port/thread đã được giải phóng, hãy đợi termination.

## 7. Đóng client trước server

Khi test tự sở hữu cả client và server, thứ tự cleanup thường là:

1. Ngừng tạo RPC mới.
2. Cancel hoặc đợi các streaming call đang mở kết thúc.
3. Đóng ManagedChannel và chờ channel terminated.
4. Gọi graceful shutdown server và chờ server terminated.
5. Dừng executor/worker riêng của test sau khi call và server không còn dùng chúng.

Đóng channel trước server giúp client kết thúc call và giải phóng transport trong khi server vẫn còn khả năng xử lý các call đang kết thúc. Nếu server dừng trước, call phía client có thể nhận lỗi transport; điều đó phù hợp với test restart/failure nhưng không phải thứ tự teardown thông thường.

Nếu server do Spring context quản lý, test chỉ đóng channel. Spring/starter sẽ dừng server khi context thật sự bị đóng.

## 8. Xử lý thread bị interrupt trong cleanup

awaitTermination có thể ném InterruptedException. Không nuốt exception và tiếp tục giả vờ cleanup thành công. Khi bị interrupt, yêu cầu shutdown cưỡng bức, khôi phục interrupt flag rồi truyền lỗi ra ngoài:

~~~java
static void closeChannelPreservingInterrupt(
        ManagedChannel channel) throws InterruptedException {
    if (channel == null) {
        return;
    }

    channel.shutdown();
    try {
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    } catch (InterruptedException ex) {
        channel.shutdownNow();
        Thread.currentThread().interrupt();
        throw ex;
    }
}
~~~

Nếu helper được dùng trong teardown của test, để test framework ghi nhận interruption. Không chuyển InterruptedException thành status RPC hoặc bỏ qua để test báo xanh trong khi tài nguyên chưa được dọn.

## 9. Streaming call phải được kết thúc trước teardown

Channel shutdown không thay thế việc quản lý lifecycle của stream. Với stream vô hạn hoặc stream đang chờ input, test cần giữ handle tới call để cancel:

~~~java
AtomicReference<ClientCallStreamObserver<WatchRequest>> callRef =
    new AtomicReference<>();
CountDownLatch terminal = new CountDownLatch(1);

stub.watchStock(
    WatchRequest.newBuilder().setSku("SKU-42").build(),
    new ClientResponseObserver<>() {
        @Override
        public void beforeStart(
                ClientCallStreamObserver<WatchRequest> call) {
            callRef.set(call);
        }

        @Override
        public void onNext(StockUpdate update) {
            // Thu thập message cần assert.
        }

        @Override
        public void onError(Throwable error) {
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });

// Sau khi test đã kiểm tra đủ dữ liệu:
callRef.get().cancel("test finished", null);
assertTrue(terminal.await(2, TimeUnit.SECONDS));
~~~

Trong test thật, kiểm tra callRef.get() khác null trước khi cancel và lưu lỗi callback để assert theo kịch bản. Cancellation thường dẫn tới terminal callback onError ở client; không chờ onCompleted() cho một stream bị cancel.

Với client-streaming, gọi requestObserver.onCompleted() khi đã gửi hết input để yêu cầu server hoàn tất response. Với bidirectional stream, đóng từng chiều theo contract hoặc cancel toàn call. Không gửi onNext sau terminal event.

## 10. Executor và công việc nền của service

gRPC server shutdown không tự động quản lý mọi executor mà service tự tạo. Nếu handler đưa công việc vào ExecutorService, scheduler hoặc queue riêng, thành phần tạo executor phải chịu trách nhiệm shutdown.

Trong Spring, executor dùng chung nên là bean được quản lý lifecycle. Không shutdown executor singleton trong @AfterEach nếu application context còn được cache và test khác còn dùng bean đó.

Với executor do test tạo, cleanup theo trình tự:

- Ngừng submit task mới.
- Gọi shutdown().
- Chờ awaitTermination có timeout.
- Dùng shutdownNow() nếu quá hạn.
- Kiểm tra task bị hủy và xử lý danh sách task chưa chạy nếu cần.

Service streaming cần liên kết cancellation/deadline của RPC với công việc nền. Nếu client cancel mà worker vẫn tiếp tục tạo message hoặc truy vấn dependency, test có thể kết thúc nhưng thread/buffer vẫn bị rò.

## 11. Server do Spring gRPC starter quản lý

Với server auto-configured, không tự gọi server.shutdown() từ test nếu starter sở hữu lifecycle. Spring Test thường cache ApplicationContext giữa test method/class có cấu hình tương thích. Vì vậy server có thể vẫn chạy sau @AfterEach và được tái sử dụng ở test tiếp theo.

Quy tắc thực tế:

- Đóng channel do test tạo trong @AfterEach hoặc @AfterAll tùy phạm vi.
- Để starter/Spring dừng server khi context đóng.
- Không gọi shutdownNow() lên server dùng chung từ một test method.
- Nếu cần buộc context đóng sau class, cân nhắc @DirtiesContext ở phạm vi phù hợp.
- Không dùng @DirtiesContext mặc định cho mọi test vì làm suite khởi động lại context liên tục.

Nếu starter cung cấp lifecycle/port accessor riêng, dùng API của đúng starter và phiên bản. Không tạo server thủ công song song với server auto-configured chỉ để có thể gọi stop.

## 12. Server fixture do Spring quản lý

Khi cần tự tạo server cho integration test, đăng ký fixture như Spring bean với init/destroy method hoặc SmartLifecycle. Khi context đóng, Spring gọi đúng cleanup hook:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class GrpcServerTestConfiguration {
    @Bean(initMethod = "start", destroyMethod = "stop")
    TestGrpcServer testGrpcServer(GreeterServiceImpl service) {
        return new TestGrpcServer(service);
    }
}
~~~

TestGrpcServer.stop() nên gọi graceful shutdown, đợi termination, rồi mới gọi shutdownNow() nếu hết thời hạn. Không đồng thời khai báo destroy method và một lifecycle callback khác cùng dừng server nếu điều đó tạo hai chủ sở hữu cleanup; chọn một cơ chế nhất quán.

Với context cache, fixture sống cùng context. Đừng gọi stop() ở @AfterEach; để Spring gọi khi context thực sự đóng.

## 13. @DirtiesContext và thời điểm server dừng

@DirtiesContext yêu cầu Spring Test loại ApplicationContext khỏi cache và đóng context theo phạm vi annotation. Các bean lifecycle được hủy, bao gồm server fixture được Spring quản lý.

Dùng khi test đã thay đổi context hoặc cần xác minh shutdown/restart riêng. Không dùng chỉ để giải phóng một channel do test tạo; channel có thể được đóng trực tiếp.

Nếu cần test rằng server đã dừng sau context close, giữ một tham chiếu quan sát phù hợp tới fixture/test signal và xác minh termination. Không truy cập bean qua context đã đóng để rồi kết luận cleanup thất bại chỉ vì bean không còn truy xuất được.

## 14. Cleanup khi assertion hoặc setup thất bại

Test có thể fail sau khi channel đã tạo nhưng trước khi stub được khởi tạo. Đặt tài nguyên vào field và cleanup null-safe trong teardown để tránh bỏ sót.

Nếu tạo nhiều channel hoặc server thủ công trong một test helper, dùng try/finally hoặc một fixture AutoCloseable để luôn cleanup:

~~~java
try (GrpcClientFixture client =
         GrpcClientFixture.connect("127.0.0.1", port)) {
    HelloReply reply = client.greeter()
        .sayHello(request);
    assertEquals("Hello, Linh", reply.getMessage());
}
~~~

close() của fixture nên thực hiện bounded graceful shutdown và fallback cưỡng bức. Tránh cleanup chỉ nằm sau assertion trong thân test; khi assertion ném lỗi, các dòng phía sau không chạy.

## 15. Kiểm tra leak sau test

Một test cleanup tốt có thể xác minh:

- Channel đã terminated sau teardown.
- Server fixture đã terminated khi context đóng.
- Không còn stream observer/call hoạt động ngoài dự kiến.
- Executor test đã terminated.
- Port được giải phóng nếu test tự sở hữu server.
- Không có task nền tiếp tục ghi vào collection hoặc log của test đã kết thúc.

Để chẩn đoán, ghi lại channel/server state, invocation count, số stream còn mở và thread name thuộc executor test. Không assert tổng số thread của JVM một cách cứng nhắc vì Spring, JUnit và runtime có thể tạo thread dùng chung. Hãy quan sát tài nguyên mà test sở hữu.

Không dựa vào GC hoặc việc JVM tự thoát để dọn channel/server. Cleanup phải tường minh và xác định.

## 16. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ gọi shutdown() rồi kết thúc test | Channel có thể vẫn còn hoạt động | Đợi awaitTermination có timeout. |
| Chỉ gọi shutdownNow() | Hủy call bình thường và che lỗi lifecycle | Graceful trước, forceful khi timeout. |
| Dừng server starter trong @AfterEach | Phá server dùng chung qua context cache | Để Spring/starter sở hữu shutdown. |
| Đóng server trước khi client stream kết thúc | Call nhận lỗi ngoài ý muốn | Cancel/complete stream, đóng channel rồi dừng server. |
| Không cancel stream vô hạn | Giữ call, observer và worker | Cancel và đợi terminal callback. |
| Đóng wrapper channel thay vì channel gốc | Cleanup không rõ chủ sở hữu | Giữ và đóng ManagedChannel gốc. |
| Shutdown executor singleton mỗi test | Test sau dùng executor đã dừng | Để Spring quản lý executor dùng chung. |
| Nuốt InterruptedException | Cleanup có thể không hoàn tất mà test vẫn xanh | Force shutdown, restore interrupt và báo lỗi. |
| Chờ termination vô hạn | Suite treo khi resource bị kẹt | Dùng timeout hữu hạn và fallback. |
| Dùng @DirtiesContext cho mọi method | Suite chậm do context liên tục khởi động lại | Đóng channel trực tiếp; chỉ dirties context khi cần. |

## 17. Ma trận cleanup cần kiểm thử

Một bộ integration test nên bao gồm:

1. Channel per-method: channel được shutdown và terminated sau mỗi test.
2. Channel per-class: channel còn dùng được giữa các method và chỉ đóng sau class.
3. Server do starter quản lý: vẫn hoạt động khi context được cache và dừng khi context đóng.
4. Server fixture do Spring quản lý: destroy hook dừng server sau context close.
5. Streaming call dài hạn: cancellation kết thúc call và worker.
6. RPC bị treo: deadline/cancellation giải phóng call trong timeout.
7. Cleanup bị timeout: fallback shutdownNow được thực hiện và test báo leak nếu vẫn chưa terminated.
8. Test fail giữa setup: tài nguyên đã tạo vẫn được cleanup qua teardown/finally.
9. Executor test riêng: không còn task/thread sau khi fixture đóng.

Các test nên chạy độc lập và chạy cùng suite để phát hiện tài nguyên sót lại giữa các test.

## 18. Bài tập thực hành

Tạo một integration test Spring gRPC có unary call và streaming call:

1. Khởi động server theo lifecycle của starter hoặc Spring test fixture.
2. Tạo ManagedChannel trong @BeforeEach và gọi unary RPC có deadline.
3. Mở một server-streaming call, nhận đủ dữ liệu rồi xác nhận terminal callback.
4. Mở một stream dài hạn khác và cancel trước teardown.
5. Trong @AfterEach, đợi channel graceful shutdown; nếu quá hạn thì force shutdown.
6. Xác minh channel đã terminated và stream không còn callback mới.
7. Để Spring đóng server khi context đóng; nếu test tự sở hữu server, đóng server sau channel.
8. Tạo một test cố ý fail sau khi channel được tạo và xác nhận teardown vẫn chạy.

**Tiêu chí hoàn thành:** mọi channel, stream và server có chủ sở hữu rõ ràng; graceful shutdown được ưu tiên; timeout và interrupt được xử lý; Spring context cache không bị phá bởi cleanup sai phạm vi.

## 19. Ghi nhớ

- ManagedChannel và Server có graceful shutdown, await termination và forceful shutdown.
- shutdown() khởi động quá trình đóng; awaitTermination() xác nhận tài nguyên đã kết thúc.
- Dùng shutdownNow() khi graceful shutdown hết thời hạn hoặc khi cần hủy call.
- Dừng streaming call trước teardown và chờ terminal callback có timeout.
- Đóng channel do test sở hữu; để Spring/starter đóng server do context sở hữu.
- Server fixture tự tạo nên là Spring lifecycle bean hoặc được cleanup bằng try/finally.
- Context cache làm server có thể sống qua nhiều test method; không dừng server dùng chung ở @AfterEach.
- Executor và worker do ứng dụng/test tạo cũng cần cleanup riêng.
- Xử lý InterruptedException bằng force shutdown, khôi phục interrupt flag và báo lỗi.
- Cleanup phải được kiểm chứng bằng trạng thái terminated và không còn công việc nền thuộc test.

Dọn channel và server đúng vòng đời giúp integration test Spring gRPC không để sót connection, stream hoặc thread, đồng thời giữ server dùng chung trong Spring context hoạt động ổn định giữa các test.
