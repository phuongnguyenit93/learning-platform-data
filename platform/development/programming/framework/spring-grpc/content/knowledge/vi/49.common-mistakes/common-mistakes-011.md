# Dùng sleep trong streaming test

Một lỗi thường gặp khi kiểm thử gRPC streaming là gửi request, gọi `Thread.sleep(...)` một khoảng thời gian rồi kiểm tra danh sách response. Cách này khiến test phụ thuộc vào tốc độ máy, tải của CI và lịch chạy thread. Test có thể chạy qua trên máy cá nhân nhưng thất bại ngẫu nhiên khi server phản hồi chậm hơn dự kiến.

Trong Spring gRPC, callback của `StreamObserver` được gọi bất đồng bộ. Test cần đồng bộ với sự kiện thực tế của RPC: message đã đến, stream đã kết thúc, stream báo lỗi hoặc lời gọi đã bị hủy. Hãy dùng `CountDownLatch`, `BlockingQueue`, `CompletableFuture` hoặc công cụ kiểm thử reactive phù hợp để chờ đúng sự kiện với một giới hạn thời gian rõ ràng.

## Vì sao `Thread.sleep` làm streaming test thiếu ổn định

Ví dụ dễ mắc:

```java
@Test
void shouldReceiveUpdates() throws Exception {
    List<PriceUpdate> received = new ArrayList<>();

    asyncStub.watch(request, new StreamObserver<>() {
        @Override
        public void onNext(PriceUpdate value) {
            received.add(value);
        }

        @Override
        public void onError(Throwable error) {
            // Test không nhận được tín hiệu kết thúc.
        }

        @Override
        public void onCompleted() {
            // Test không nhận được tín hiệu kết thúc.
        }
    });

    Thread.sleep(1_000);
    assertEquals(3, received.size());
}
```

Đoạn test này có nhiều vấn đề:

- Một giây là giả định về tốc độ xử lý, không phải bằng chứng rằng server đã gửi đủ ba message.
- Nếu RPC hoàn thành sau một giây, test thất bại dù service đúng.
- Nếu RPC hoàn thành sau 20 ms, test vẫn chờ đủ một giây và làm chậm toàn bộ suite.
- Nếu stream lỗi, test chỉ nhìn thấy danh sách thiếu phần tử; nguyên nhân thật nằm trong `onError` bị bỏ qua.
- `ArrayList` được ghi từ callback thread và đọc từ test thread mà không có cơ chế đồng bộ.
- Với stream dài hạn không tự kết thúc, không có khoảng `sleep` nào chứng minh stream đã sẵn sàng hoặc sẽ phát message.

`Thread.sleep` chỉ làm thread hiện tại tạm ngừng. Nó không yêu cầu gRPC hoàn tất callback, không xác nhận message đã đến và không tạo ra một điều kiện đồng bộ có ý nghĩa cho test. Tăng thời gian ngủ chỉ làm test chậm hơn và che khuất race condition.

## Chọn cơ chế chờ theo loại sự kiện

| Điều test cần biết | Cơ chế phù hợp |
| --- | --- |
| Một RPC hữu hạn đã kết thúc thành công hoặc thất bại | `CountDownLatch` được giảm trong `onCompleted` và `onError`. |
| Đã nhận từng message hoặc cần kiểm tra thứ tự message | `BlockingQueue` và `poll(timeout, unit)`. |
| Một thao tác bất đồng bộ hoàn thành bằng một kết quả | `CompletableFuture` hoặc `CompletionStage`. |
| Một trạng thái bên ngoài thay đổi sau một khoảng bất định | Awaitility với điều kiện và thời hạn tối đa. |
| Luồng dữ liệu là Reactor `Flux`/`Mono` | Reactor `StepVerifier`; dùng virtual time nếu kiểm tra scheduler/thời gian ảo. |

Timeout trong các cơ chế này là giới hạn trên để test kết thúc và báo lỗi khi sự kiện không xuất hiện. Với latch, future và queue, test được đánh thức khi sự kiện đến; Awaitility đánh giá lại điều kiện theo chu kỳ polling. Khi điều kiện hoàn tất sớm, test không phải đợi hết toàn bộ khoảng timeout như `sleep`.

## Kiểm thử server-streaming bằng tín hiệu kết thúc

Với RPC server-streaming hữu hạn, server gửi không hoặc nhiều message rồi kết thúc bằng `onCompleted`; nếu có lỗi, callback nhận `onError`. Có thể dùng một latch cho trạng thái terminal và lưu lỗi riêng để phân biệt hai kết quả.

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class PriceServiceGrpcTest {

    @Test
    void receivesAllUpdatesAndCompletes() throws InterruptedException {
        CountDownLatch terminal = new CountDownLatch(1);
        List<PriceUpdate> received = new CopyOnWriteArrayList<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        asyncStub.withDeadlineAfter(5, TimeUnit.SECONDS)
                .watch(WatchRequest.newBuilder().build(), new StreamObserver<>() {
                    @Override
                    public void onNext(PriceUpdate value) {
                        received.add(value);
                    }

                    @Override
                    public void onError(Throwable error) {
                        failure.set(error);
                        terminal.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        terminal.countDown();
                    }
                });

        assertTrue(terminal.await(6, TimeUnit.SECONDS),
                "RPC did not reach a terminal state in time");
        assertNull(failure.get(), "RPC ended with an error");
        assertEquals(expectedUpdates(), List.copyOf(received));
    }
}
```

Trong ví dụ, `asyncStub` là stub bất đồng bộ được tạo từ service proto của ứng dụng; `expectedUpdates()` đại diện cho dữ liệu kỳ vọng của test. Thay tên request, response và method bằng kiểu được sinh từ hợp đồng thực tế.

Điểm quan trọng là latch được giảm trong cả `onCompleted` lẫn `onError`. Nếu chỉ giảm trong `onCompleted`, một RPC lỗi sẽ khiến test chờ đến timeout và che mất lỗi gốc. Sau khi latch mở, test kiểm tra `failure` để xác nhận stream hoàn tất thành công. `CopyOnWriteArrayList` phù hợp với ví dụ có ít message; với stream lớn hoặc cần lấy message theo thứ tự từng cái, dùng `BlockingQueue`.

Deadline của RPC và timeout chờ trong test phục vụ hai mục đích khác nhau. Deadline giới hạn thời gian server được phép xử lý lời gọi; `await` giới hạn thời gian test chờ callback. Đặt thời hạn chờ của test dài hơn deadline RPC một khoảng hợp lý để callback `DEADLINE_EXCEEDED` có thời gian quay về test.

## Kiểm thử client-streaming

Với client-streaming, client gửi nhiều message qua request observer. Khi đã gửi xong, client gọi `onCompleted()` trên request observer để báo rằng không còn message đầu vào. Server thường trả về một response cuối cùng rồi kết thúc response stream.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;

@Test
void uploadsChunksAndReceivesSummary() throws InterruptedException {
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<UploadSummary> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<UploadSummary> responseObserver = new StreamObserver<>() {
        @Override
        public void onNext(UploadSummary value) {
            result.set(value);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    };

    StreamObserver<UploadChunk> requestObserver =
            asyncStub.withDeadlineAfter(5, TimeUnit.SECONDS)
                    .upload(responseObserver);

    requestObserver.onNext(firstChunk());
    requestObserver.onNext(secondChunk());
    requestObserver.onNext(lastChunk());
    requestObserver.onCompleted();

    assertTrue(terminal.await(6, TimeUnit.SECONDS),
            "Upload response did not complete in time");
    assertNull(failure.get(), "Upload RPC failed");
    assertEquals(expectedSummary(), result.get());
}
```

Không chờ bằng `sleep` sau `requestObserver.onCompleted()`. Lệnh này chỉ đóng chiều gửi của client; nó không có nghĩa là server đã xử lý xong dữ liệu hoặc response đã quay về. Chỉ callback terminal của `responseObserver` mới xác nhận kết quả RPC đã kết thúc.

## Kiểm thử bidirectional-streaming

Với bidirectional-streaming, client và server có thể gửi message độc lập trên hai chiều. Client gọi `onCompleted()` để đóng chiều gửi của mình, nhưng server vẫn có thể đang gửi response. Vì vậy, test phải quan sát response và trạng thái terminal từ observer phía client.

Nếu giao thức quy định mỗi command tạo ra một reply, `BlockingQueue` giúp đợi từng reply và xác minh thứ tự:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import io.grpc.stub.StreamObserver;

@Test
void exchangesCommandsInOrder() throws InterruptedException {
    BlockingQueue<ChatReply> replies = new LinkedBlockingQueue<>();
    CountDownLatch terminal = new CountDownLatch(1);
    AtomicReference<Throwable> failure = new AtomicReference<>();

    StreamObserver<ChatCommand> requests = asyncStub.chat(new StreamObserver<>() {
        @Override
        public void onNext(ChatReply value) {
            replies.offer(value);
        }

        @Override
        public void onError(Throwable error) {
            failure.set(error);
            terminal.countDown();
        }

        @Override
        public void onCompleted() {
            terminal.countDown();
        }
    });

    requests.onNext(firstCommand());
    ChatReply firstReply = replies.poll(5, TimeUnit.SECONDS);
    assertNotNull(firstReply, "Did not receive the first reply");
    assertEquals(expectedFirstReply(), firstReply);

    requests.onNext(secondCommand());
    ChatReply secondReply = replies.poll(5, TimeUnit.SECONDS);
    assertNotNull(secondReply, "Did not receive the second reply");
    assertEquals(expectedSecondReply(), secondReply);

    requests.onCompleted();

    assertTrue(terminal.await(6, TimeUnit.SECONDS),
            "Bidirectional RPC did not reach a terminal state");
    assertNull(failure.get(), "Bidirectional RPC failed");
}
```

Ví dụ trên giả định server trả lời từng command theo đúng thứ tự và kết thúc sau khi client đóng chiều gửi. Nếu hợp đồng cho phép server gộp, bỏ qua hoặc phát reply theo một quy tắc khác, hãy viết assertion theo quy tắc đó thay vì giả định một command luôn tương ứng với một reply.

Không gọi `onCompleted()` trên request observer rồi lập tức khẳng định response đã hoàn tất. Đó chỉ là half-close của client. Luôn chờ `onCompleted` hoặc `onError` trên response observer.

## Kiểm thử stream dài hạn

Một subscription hoặc stream theo dõi sự kiện có thể được thiết kế để không tự kết thúc. Trong trường hợp này, đợi `onCompleted` là sai vì RPC chỉ kết thúc khi client hủy, server đóng hoặc deadline hết hạn.

Hãy đợi đúng số message hoặc điều kiện mà test cần, sau đó chủ động hủy lời gọi và kiểm tra hành vi hủy nếu đó là phần của hợp đồng. `BlockingQueue.poll(timeout, unit)` phù hợp khi cần lấy từng message; Awaitility phù hợp khi chỉ cần xác nhận một trạng thái cuối cùng đã xuất hiện.

Khi cần hủy client call từ test, gRPC Java cung cấp callback `ClientResponseObserver.beforeStart(...)` để nhận `ClientCallStreamObserver`. Lưu observer này vào `AtomicReference`, đợi các message mong đợi, rồi gọi `cancel("test complete", null)` trong phần cleanup. Nếu cần kiểm tra server phản ứng với cancellation, xác minh tín hiệu hủy ở server bằng latch riêng. Không chờ một stream vô hạn tự gọi `onCompleted`.

## Dùng Awaitility cho trạng thái bất đồng bộ

Đôi khi test không sở hữu callback trực tiếp mà cần đợi trạng thái được cập nhật ở một thành phần khác. Có thể dùng Awaitility để đánh giá lại điều kiện cho đến khi đúng hoặc hết thời hạn:

```java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() -> assertEquals(3, metrics.receivedCount()));
```

Awaitility hữu ích cho điều kiện eventual như metric, trạng thái lưu trữ hoặc readiness. Nếu API đã cung cấp callback terminal rõ ràng, latch hoặc future thường diễn đạt ý định trực tiếp hơn. Không dùng Awaitility để che việc thiếu tín hiệu kết thúc của RPC.

Thêm dependency Awaitility vào test scope nếu dự án chưa có thư viện này.

Nếu service xử lý dữ liệu bằng Reactor `Flux` hoặc `Mono`, `StepVerifier` cho phép kiểm tra message, lỗi và completion:

```java
import java.time.Duration;

import reactor.test.StepVerifier;

StepVerifier.create(pricePublisher)
        .expectNext(firstUpdate, secondUpdate)
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Với publisher có timer hoặc delay, cân nhắc `StepVerifier.withVirtualTime(...)` cùng scheduler ảo để test không phải chờ thời gian thực. Chỉ dùng `StepVerifier` cho publisher reactive; nó không thay thế trực tiếp `StreamObserver` của gRPC Java.

`StepVerifier` thuộc `reactor-test`; chỉ thêm dependency này nếu module thực sự dùng Reactor trong phần cần kiểm thử.

## Trường hợp cần kiểm thử thời gian thực

Có những chức năng mà thời gian là một phần của yêu cầu, ví dụ retry backoff, rate limit, timeout hoặc phát heartbeat theo chu kỳ. Ngay cả khi đó, `sleep` thường vẫn là lựa chọn yếu vì test không kiểm soát được scheduler và thời điểm thực thi.

- Tách nguồn thời gian thành `Clock` hoặc một abstraction có thể thay thế trong test.
- Tiêm scheduler hoặc timer để test có thể chủ động tiến thời gian.
- Với Reactor, dùng virtual scheduler và `StepVerifier.withVirtualTime`.
- Với integration test cần xác minh tương tác thật, đợi điều kiện có thời hạn và kiểm tra khoảng thời gian bằng đồng hồ đo phù hợp; tránh khẳng định chính xác một thời điểm tuyệt đối trong môi trường CI.

Test thời gian thực nên kiểm tra giới hạn được đặc tả, chẳng hạn không retry trước một khoảng tối thiểu hoặc hoàn tất trong một ngưỡng cho phép, thay vì phụ thuộc vào một khoảng ngủ cố định.

## Những lỗi đồng bộ cần tránh

| Lỗi trong test | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ `countDown` trong `onCompleted` | RPC lỗi khiến test đợi đến timeout và mất lỗi gốc | Giảm latch trong cả `onCompleted` và `onError`; lưu lỗi để assertion sau đó. |
| Không kiểm tra kết quả `await` | Test có thể tiếp tục dù callback chưa chạy | Dùng `assertTrue(await(...))` và thông báo rõ sự kiện bị thiếu. |
| Chỉ chờ request observer `onCompleted` | Nhầm half-close của client với completion của RPC | Chờ terminal callback ở response observer. |
| Chờ completion của stream vô hạn | Test luôn timeout | Đợi message/điều kiện cần thiết rồi hủy stream. |
| Assert trực tiếp bên trong callback | Assertion có thể chạy trên gRPC thread và không được JUnit báo đúng ở test thread | Lưu kết quả/lỗi; assertion sau khi đã đồng bộ. |
| Dùng `ArrayList` chia sẻ giữa callback và test thread | Race condition hoặc đọc dữ liệu chưa đồng bộ | Dùng queue, collection thread-safe hoặc đồng bộ hóa phù hợp. |
| Gửi `onNext` đồng thời từ nhiều thread | Vi phạm giả định tuần tự của outbound observer | Tuần tự hóa việc ghi request bằng một producer hoặc executor. |
| Không đặt deadline cho RPC | Lỗi ở server hoặc mạng có thể khiến lời gọi kéo dài quá lâu | Đặt deadline phù hợp và timeout chờ ở test. |
| Dùng latch hoặc queue static giữa các test | Trạng thái của test trước ảnh hưởng test sau | Tạo trạng thái đồng bộ mới cho từng test. |
| Không đóng channel/server sau test | Rò rỉ thread, socket và làm test khác bị ảnh hưởng | Đóng tài nguyên trong `@AfterEach` hoặc `@AfterAll` theo vòng đời fixture. |

## Quy trình viết một streaming test ổn định

1. Xác định loại RPC và điều kiện kết thúc: server-streaming hữu hạn, client-streaming, bidirectional hay subscription dài hạn.
2. Chọn tín hiệu cần đợi: từng message, kết quả cuối, `onCompleted`, `onError` hoặc trạng thái cancellation.
3. Khởi tạo queue/latch/future trước khi gọi RPC để không bỏ lỡ callback sớm.
4. Đặt deadline cho RPC nếu phù hợp và luôn đặt timeout hữu hạn cho thao tác chờ của test.
5. Gửi request theo đúng thứ tự và đúng quy tắc half-close của loại streaming.
6. Chờ tín hiệu, sau đó kiểm tra nội dung, thứ tự message, trạng thái terminal và lỗi đã lưu.
7. Hủy stream dài hạn khi test đã nhận đủ dữ liệu; đóng channel và server trong cleanup.

Trong Spring gRPC, các service thường được khởi tạo và quản lý theo vòng đời Spring application context. Hãy để test context hoàn tất khởi tạo trước khi gọi stub; với server do test tự quản lý, đợi tín hiệu server đã sẵn sàng hoặc dùng lifecycle hook của fixture. Không dùng `sleep` để đoán thời điểm server đã mở cổng.

Một streaming test đáng tin cậy phải chỉ ra được nó đang đợi message nào hoặc trạng thái terminal nào. Khi đồng bộ theo callback và dùng timeout như giới hạn thất bại, test chạy nhanh khi RPC hoàn tất sớm, báo đúng lỗi khi RPC thất bại và ít phụ thuộc vào tốc độ của máy chạy CI.
