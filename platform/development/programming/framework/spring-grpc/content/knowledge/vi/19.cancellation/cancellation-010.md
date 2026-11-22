# Kiểm thử hủy giữa chừng

Kiểm thử cancellation chỉ có giá trị khi nó chứng minh được lời gọi bị dừng ở đúng thời điểm và công việc phía server thực sự phản ứng. Một test chỉ gọi future.cancel(true) rồi xác minh future ở trạng thái cancelled chưa chứng minh gRPC call đã nhận tín hiệu, worker đã dừng hoặc tài nguyên đã được giải phóng.

**Kiểm thử hủy giữa chừng** tập trung vào việc điều khiển một RPC đang xử lý, chủ động hủy call hoặc để deadline hết hạn, rồi quan sát cả client lẫn server. Bài thuộc chương **Cancellation** của mô-đun **SPRING_GRPC**, nơi phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers và mã Java sinh ra, hỗ trợ unary/streaming RPC, metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát.

## 1. Những điều một cancellation test cần chứng minh

Một bài kiểm thử đầy đủ nên xác minh bốn khía cạnh:

1. **Client kết thúc đúng cách:** explicit cancellation thường kết thúc client call với CANCELLED; deadline hết hạn thường cho DEADLINE_EXCEEDED.
2. **Server nhận tín hiệu:** Context của RPC chuyển sang cancelled hoặc ServerCallStreamObserver gọi cancellation handler.
3. **Công việc dừng:** worker không tiếp tục bước xử lý tiếp theo, downstream call được yêu cầu hủy hoặc producer dừng phát message.
4. **Resource được giải phóng:** subscription, cursor, statement hoặc tài nguyên thuộc call được cleanup đúng một lần.

Ngoài ra, nếu test kiểm tra side effect, phải đặt một điểm đồng bộ rõ ràng trước side effect. Hủy call khi handler đã đi qua điểm commit không thể chứng minh rollback; khi đó kết quả đúng có thể là operation đã commit và client cần tra cứu bằng idempotency key.

## 2. Dùng in-process transport để kiểm soát thời điểm

gRPC Java cung cấp InProcessServerBuilder và InProcessChannelBuilder để tạo server/channel trong cùng process. Cách này phù hợp cho integration test ở mức gRPC call lifecycle:

- Không cần mở port TCP.
- Có thể gắn service test double trực tiếp vào server.
- Có thể điều khiển thời điểm handler bắt đầu, tiếp tục hoặc kết thúc bằng CountDownLatch.
- Có thể quan sát cancellation từ client tới server mà không phụ thuộc DNS hoặc mạng ngoài.

Test cần dependency grpc-inprocess cùng phiên bản với các thư viện gRPC Java khác. Ví dụ Gradle khi không dùng BOM:

~~~kotlin
testImplementation("io.grpc:grpc-inprocess:<grpc-version>")
~~~

Nếu dự án quản lý phiên bản qua gRPC BOM, dùng cùng version alignment hiện tại của dự án thay vì khai báo một phiên bản độc lập. Bài này dùng JUnit 5 cho các assertion và lifecycle fixture.

## 3. Tạo server handler có thể dừng tại một điểm xác định

Để hủy đúng giữa chừng, server test service cần một latch báo handler đã vào xử lý và một latch cho phép test quyết định khi nào worker tiếp tục. Cancellation listener ghi nhận tín hiệu từ gRPC:

~~~java
final class BlockingGreeter extends GreeterGrpc.GreeterImplBase {

    final CountDownLatch handlerStarted = new CountDownLatch(1);
    final CountDownLatch allowContinue = new CountDownLatch(1);
    final CountDownLatch cancellationObserved = new CountDownLatch(1);
    final CountDownLatch handlerFinished = new CountDownLatch(1);
    final AtomicInteger sideEffectCount = new AtomicInteger();
    final AtomicInteger resourceCloseCount = new AtomicInteger();
    final AtomicInteger responseCount = new AtomicInteger();

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {

        Context rpcContext = Context.current();
        Context.CancellationListener listener =
                ignored -> cancellationObserved.countDown();
        rpcContext.addListener(listener, Runnable::run);

        handlerStarted.countDown();
        try {
            // Giữ handler ở giữa công việc cho tới khi test cho tiếp tục.
            allowContinue.await();

            // Không bắt đầu side effect nếu cancellation đã được nhận.
            if (rpcContext.isCancelled()) {
                return;
            }

            sideEffectCount.incrementAndGet();
            responseObserver.onNext(HelloReply.newBuilder()
                    .setMessage("Hello " + request.getName())
                    .build());
            responseCount.incrementAndGet();
            responseObserver.onCompleted();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } finally {
            rpcContext.removeListener(listener);
            resourceCloseCount.incrementAndGet();
            handlerFinished.countDown();
        }
    }
}
~~~

Đây là service kiểm thử có chủ đích giữ handler tại một điểm. Trong ứng dụng thực tế, phần chờ được thay bằng database call, downstream RPC, xử lý nghiệp vụ hoặc stream producer. resourceCloseCount đại diện cho một resource giả được giải phóng trong finally; nếu kiểm tra resource cụ thể, dùng fake AutoCloseable và đếm số lần close().

Handler chỉ tăng sideEffectCount sau khi được cho tiếp tục và sau khi kiểm tra context. Test có thể hủy call trong lúc handler đang chờ, xác minh cancellation đã đến, rồi mới mở latch. Như vậy test chứng minh server không bước qua ranh giới side effect sau khi cancellation được quan sát.

## 4. Tạo fixture server/channel và đóng đúng lifecycle

Server nên chạy handler trên executor riêng để việc chờ latch không chặn thread gửi request từ test. Fixture dưới đây dùng in-process transport:

~~~java
class CancellationIntegrationTest {

    private final String serverName = InProcessServerBuilder.generateName();
    private final BlockingGreeter service = new BlockingGreeter();
    private final ExecutorService serverExecutor =
            Executors.newFixedThreadPool(2);

    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void startGrpc() throws IOException {
        server = InProcessServerBuilder.forName(serverName)
                .executor(serverExecutor)
                .addService(service)
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void stopGrpc() throws InterruptedException {
        // Không để test lỗi làm server worker mắc kẹt ở latch.
        service.allowContinue.countDown();

        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(2, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(2, TimeUnit.SECONDS);
        }

        serverExecutor.shutdownNow();
        serverExecutor.awaitTermination(2, TimeUnit.SECONDS);
    }
}
~~~

directExecutor() ở channel giúp callback client chạy trực tiếp theo executor của call; server vẫn dùng serverExecutor riêng. Trong test lớn hơn, có thể dùng executor riêng cho client callback nếu cần kiểm tra concurrency. Luôn mở latch trong teardown để test thất bại không giữ worker vô hạn.

## 5. Kiểm thử explicit cancellation khi handler đang chạy

Client dùng ClientResponseObserver.beforeStart(...) để lấy ClientCallStreamObserver, sau đó hủy đúng call đang chạy:

~~~java
@Test
void explicitCancelStopsWorkBeforeSideEffect() throws Exception {
    AtomicReference<ClientCallStreamObserver<HelloRequest>> callRef =
            new AtomicReference<>();
    AtomicReference<Throwable> clientFailure = new AtomicReference<>();
    CountDownLatch clientTerminal = new CountDownLatch(1);
    AtomicInteger clientMessageCount = new AtomicInteger();

    ClientResponseObserver<HelloRequest, HelloReply> observer =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<HelloRequest> call) {
                    callRef.set(call);
                }

                @Override
                public void onNext(HelloReply reply) {
                    clientMessageCount.incrementAndGet();
                }

                @Override
                public void onError(Throwable failure) {
                    clientFailure.set(failure);
                    clientTerminal.countDown();
                }

                @Override
                public void onCompleted() {
                    clientTerminal.countDown();
                }
            };

    GreeterGrpc.newStub(channel).sayHello(
            HelloRequest.newBuilder().setName("Lan").build(),
            observer);

    assertTrue(service.handlerStarted.await(2, TimeUnit.SECONDS));
    ClientCallStreamObserver<HelloRequest> call = callRef.get();
    assertNotNull(call);

    call.cancel("Test cancels while handler is active", null);

    assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
    assertTrue(clientTerminal.await(2, TimeUnit.SECONDS));

    // Cho worker chạy tiếp sau khi server đã quan sát cancellation.
    service.allowContinue.countDown();
    assertTrue(service.handlerFinished.await(2, TimeUnit.SECONDS));

    assertEquals(Status.Code.CANCELLED,
            Status.fromThrowable(clientFailure.get()).getCode());
    assertEquals(0, service.sideEffectCount.get());
    assertEquals(0, service.responseCount.get());
    assertEquals(0, clientMessageCount.get());
    assertEquals(1, service.resourceCloseCount.get());
}
~~~

Thứ tự trong test rất quan trọng:

1. Chờ handlerStarted để biết server đã vào RPC.
2. Hủy call từ client.
3. Chờ cancellationObserved để biết server context thực sự nhận tín hiệu.
4. Chờ client terminal callback.
5. Mở allowContinue, để handler đi tới điểm kiểm tra cancellation và thoát.
6. Chờ handlerFinished, rồi mới kiểm tra side effect và cleanup.

Không mở allowContinue ngay sau call.cancel(...) rồi kiểm tra side effect tức thì; khi đó cancellation listener có thể chưa chạy. Latch tạo thứ tự sự kiện xác định, không cần Thread.sleep().

Trong test trên onNext chỉ tăng response counter, còn server cũng tăng counter trước khi gọi onCompleted. Ở code test thực tế nên dùng một counter riêng cho message client nhận và một counter server-side cho message được phát để phân biệt hai điều: server đã gọi observer hay client đã nhận response.

## 6. Kiểm thử deadline hết hạn riêng với explicit cancel

Deadline expiry cũng hủy call ở server, nhưng status phía client khác explicit cancellation. Tạo một call có deadline ngắn hơn thời gian handler chờ:

~~~java
@Test
void deadlineExpiryCancelsServerWork() throws Exception {
    AtomicReference<Throwable> clientFailure = new AtomicReference<>();
    CountDownLatch clientTerminal = new CountDownLatch(1);
    AtomicInteger clientMessageCount = new AtomicInteger();

    ClientResponseObserver<HelloRequest, HelloReply> observer =
            new ClientResponseObserver<>() {
                @Override
                public void beforeStart(
                        ClientCallStreamObserver<HelloRequest> call) {
                    // Không cần giữ handle vì deadline tự kết thúc call.
                }

                @Override
                public void onNext(HelloReply reply) {
                    clientMessageCount.incrementAndGet();
                }

                @Override
                public void onError(Throwable failure) {
                    clientFailure.set(failure);
                    clientTerminal.countDown();
                }

                @Override
                public void onCompleted() {
                    clientTerminal.countDown();
                }
            };

    GreeterGrpc.newStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS)
            .sayHello(
                    HelloRequest.newBuilder().setName("Lan").build(),
                    observer);

    assertTrue(service.handlerStarted.await(2, TimeUnit.SECONDS));
    assertTrue(clientTerminal.await(4, TimeUnit.SECONDS));
    assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));

    service.allowContinue.countDown();
    assertTrue(service.handlerFinished.await(2, TimeUnit.SECONDS));

    assertEquals(Status.Code.DEADLINE_EXCEEDED,
            Status.fromThrowable(clientFailure.get()).getCode());
    assertEquals(0, service.sideEffectCount.get());
    assertEquals(0, clientMessageCount.get());
    assertEquals(1, service.resourceCloseCount.get());
}
~~~

Deadline một giây là giới hạn của call; handler bị giữ bởi latch nên không thể hoàn tất trước deadline. Test chờ handlerStarted và các latch thay vì dựa vào sleep để đoán lúc server bắt đầu. Trong CI chậm, có thể tăng deadline và thời gian chờ assertion tương ứng để tránh flaky test.

Hai test nên được giữ riêng: explicit cancel kỳ vọng CANCELLED; deadline expiry kỳ vọng DEADLINE_EXCEEDED. Ở server, cả hai có thể làm Context.isCancelled() thành true. Chỉ kiểm tra context cancelled không đủ để phân loại nguyên nhân; test status phía client và deadline của context bổ sung bằng chứng.

## 7. Kiểm thử resource cleanup

Một test chỉ xác minh client nhận CANCELLED chưa chứng minh JDBC statement, subscription hoặc worker đã được giải phóng. Tạo resource giả có bộ đếm:

~~~java
final class CountingResource implements AutoCloseable {
    private final AtomicInteger closeCount;

    CountingResource(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void close() {
        closeCount.incrementAndGet();
    }
}
~~~

Trong handler, đặt resource trong try-with-resources:

~~~java
try (CountingResource ignored =
             new CountingResource(service.resourceCloseCount)) {
    service.handlerStarted.countDown();
    service.allowContinue.await();
    if (rpcContext.isCancelled()) {
        return;
    }
    performSideEffect();
}
~~~

Sau khi cancellation được nhận và handler thoát, assert closeCount == 1. Bổ sung trường hợp hoàn tất bình thường và trường hợp ném exception để xác minh resource được đóng ở mọi terminal path, không chỉ cancellation.

Với resource thật, kiểm tra đúng API:

- JDBC: xác minh Statement.cancel() được gọi khi call bị hủy; ResultSet, Statement và connection do handler sở hữu được đóng.
- Subscription: xác minh cancel()/close() được gọi một lần dù cancellation đua với lúc subscribe() trả handle.
- Worker: xác minh task nhận interrupt hoặc cancellation token và không còn hoạt động sau khi handler kết thúc.
- Downstream gRPC: xác minh child server nhận cancellation qua setOnCancelHandler.

Không đóng DataSource, connection pool, executor hoặc ManagedChannel dùng chung để đáp ứng cancellation của một RPC.

## 8. Kiểm thử side effect trước và sau commit

Cancellation test phải phân biệt side effect chưa xảy ra với operation đã commit:

| Thời điểm client hủy | Kết quả cần kiểm tra |
| --- | --- |
| Trước khi handler bắt đầu | Không có side effect; handler có thể không được dispatch. |
| Trong xử lý, trước điểm commit | Cancellation token được nhận; transaction rollback; không có business row/outbox row. |
| Sau commit, trước response | Side effect vẫn tồn tại; client có thể nhận cancellation/deadline và phải truy vấn trạng thái bằng idempotency key. |
| Trong lúc downstream xử lý | Child call được yêu cầu hủy, nhưng downstream có thể đã commit; xác minh idempotency/reconciliation. |

Đối với Spring transaction, dùng integration test với transaction manager và database phù hợp. Dùng latch để dừng ngay trước commit, hủy client call, rồi cho handler tiếp tục tới kiểm tra cancellation trong transaction. Sau khi transaction kết thúc, truy vấn database từ transaction mới để xác minh rollback.

Để kiểm thử trường hợp sau commit, đặt latch sau commit nhưng trước khi gửi response. Hủy parent call rồi xác minh bản ghi vẫn tồn tại. Test này bảo vệ một kỳ vọng quan trọng: cancellation không phải rollback và không được dùng làm bằng chứng rằng thao tác ghi chưa xảy ra.

## 9. Kiểm thử cancellation của downstream RPC

Khi parent server gọi child server, test nên có hai in-process server hoặc một fixture parent/child rõ ràng:

1. Child service giữ call đang chạy và đếm latch khi ServerCallStreamObserver.setOnCancelHandler(...) được gọi.
2. Parent service gọi child bằng async stub và giữ ClientCallStreamObserver trong ClientResponseObserver.beforeStart(...).
3. Client gọi parent RPC và chờ child xác nhận đã bắt đầu.
4. Client hủy parent call.
5. Test chờ child cancellation latch và xác minh parent không gửi thêm response.
6. Mở latch của child để worker thoát; xác minh child resource được cleanup.

Kiểm tra thêm race khi parent bị hủy trước khi child beforeStart(...) lưu handle. Parent listener phải đặt cờ; khi child handle xuất hiện, beforeStart đọc cờ và hủy ngay. Nếu parent gọi nhiều child song song, xác minh tất cả child còn active đều nhận cancellation, nhưng child thuộc request khác vẫn hoạt động.

## 10. Dùng latch/barrier thay cho sleep

Thread.sleep(...) chỉ chờ một khoảng thời gian, không chứng minh một sự kiện đã xảy ra. Test dạng:

~~~java
call.cancel("test", null);
Thread.sleep(100);
assertTrue(service.cancelled);
~~~

có thể thất bại khi CI chậm hoặc pass ngẫu nhiên khi lịch chạy thuận lợi. Thay bằng:

~~~java
call.cancel("test", null);
assertTrue(service.cancellationObserved.await(2, TimeUnit.SECONDS));
~~~

Một số nguyên tắc:

- Mỗi latch có một ý nghĩa cụ thể: handler bắt đầu, cancellation được nhận, worker kết thúc, client terminal.
- Dùng timeout hữu hạn cho await để test không treo vô hạn.
- Luôn mở latch trong finally/teardown để worker có thể thoát nếu assertion thất bại.
- Khi cần điều khiển nhiều bước, dùng CyclicBarrier, nhiều latch hoặc test hook có trạng thái tường minh.
- Tránh dùng một latch cho nhiều sự kiện khác nhau vì khó xác định test đang chờ điều gì.

## 11. Khi nào cần kiểm thử qua TCP/TLS?

In-process transport kiểm tra logic call lifecycle, observer và context cancellation. Nó không mô phỏng đầy đủ:

- TCP connection bị mất đột ngột hoặc peer process bị kill.
- HTTP/2 reset, proxy, ingress hoặc service mesh.
- TLS handshake, certificate rotation và lỗi transport.
- Độ trễ phát hiện một kết nối bị đứt âm thầm.
- Keepalive và chính sách idle timeout của hạ tầng.

Vì vậy, giữ unit/in-process tests cho logic deterministic và bổ sung một số integration tests qua TCP/TLS cho hành vi mạng. Không cần lặp lại toàn bộ ma trận test qua mạng; chọn các ca quan trọng như explicit cancel, deadline expiry, peer disconnect và cleanup downstream. Khi test disconnect, xác minh server phát hiện cancellation trong giới hạn phù hợp với cấu hình transport, không giả định nó luôn xảy ra tức thì.

## 12. Những lỗi thường gặp

| Lỗi trong test | Vì sao không đủ | Cách cải thiện |
| --- | --- | --- |
| Chỉ assert future.isCancelled() | Chỉ chứng minh future bị hủy, không chứng minh gRPC call đã dừng. | Giữ call handle và xác minh server cancellation listener. |
| Chỉ assert client nhận CANCELLED | Không chứng minh worker hoặc resource được cleanup. | Chờ handler kết thúc và assert side effect/resource counter. |
| Dùng Thread.sleep() để chờ cancellation | Phụ thuộc timing và dễ flaky. | Dùng CountDownLatch/CyclicBarrier. |
| Mở latch ngay sau cancel() | Worker có thể chạy tiếp trước khi server nhận tín hiệu. | Chờ cancellation latch rồi mới cho worker tiếp tục. |
| Không cleanup server/channel/executor | Thread và resource test rò sang test khác. | Shutdown trong AfterEach; luôn giải phóng latch. |
| Chỉ test explicit cancel | Bỏ sót deadline expiry với status khác. | Có test riêng cho CANCELLED và DEADLINE_EXCEEDED. |
| Giả định cancellation rollback side effect | Commit có thể đã xảy ra. | Test riêng trước commit và sau commit; kiểm tra idempotency. |
| Chỉ dùng in-process để kết luận về network disconnect | In-process không mô phỏng TCP/proxy/keepalive. | Bổ sung integration test qua TCP/TLS. |

## 13. Bài tập thực hành

1. Tạo in-process server với handler có latch tại giữa công việc; chủ động cancel client call và xác minh server nhận cancellation.
2. Assert client status CANCELLED, worker hoàn tất, không có side effect sau cancellation và resource đóng đúng một lần.
3. Viết test deadline expiry riêng, assert DEADLINE_EXCEEDED và server context chuyển sang cancelled.
4. Kiểm thử cancellation khi child RPC đang chạy; xác minh parent listener hủy child call và child cleanup hoàn tất.
5. Dùng latch điều khiển cancellation trước commit và sau commit; xác minh rollback ở trường hợp đầu và trạng thái bền vững ở trường hợp sau.
6. Viết test race khi cancellation đến trước lúc child call handle hoặc subscription handle được lưu.
7. Bổ sung một integration test TCP/TLS cho peer disconnect và ghi nhận thời gian từ disconnect tới cleanup.

Sau bài này, bạn cần thiết kế được cancellation test có điểm đồng bộ xác định, kiểm tra cả client status lẫn phản ứng của server, worker và resource. In-process test phù hợp để kiểm soát logic giữa chừng; TCP/TLS test xác minh hành vi transport thực tế. Tách explicit cancellation, deadline expiry và side effect trước/sau commit giúp bộ kiểm thử phản ánh đúng vòng đời RPC trong hệ thống Spring gRPC.
