# Kiểm thử stream rỗng, nhiều phần tử và lỗi

## 1. Ba kết cục cần kiểm tra trong server streaming

Trong **SPRING_GRPC**, một server streaming RPC nhận một request và trả nhiều response Protocol Buffers trên cùng một RPC. Vì vậy, kiểm thử không thể chỉ xác nhận “có nhận được một message”. Cần xác minh cả số lượng, thứ tự và **kết cục cuối của RPC**.

Ba trường hợp cơ bản:

1. **Stream rỗng:** server không phát response nào nhưng kết thúc thành công bằng `onCompleted()`. Client nhận iterator hết phần tử hoặc callback `onCompleted`.
2. **Stream có nhiều phần tử:** server gọi `onNext` nhiều lần theo thứ tự rồi `onCompleted`. Client nhận đủ message theo đúng thứ tự.
3. **Stream lỗi:** server có thể gọi `onError` trước response đầu tiên hoặc sau một số response. Client phải quan sát đúng status lỗi và không đánh dấu RPC thành công.

~~~mermaid
flowchart TD
    A["Client gọi server streaming RPC"] --> B{"Server xử lý request"}
    B --> C["Không có phần tử"]
    B --> D["Có N phần tử"]
    B --> E["Gặp lỗi"]
    C --> F["onCompleted / OK"]
    D --> G["onNext × N"]
    G --> H["onCompleted / OK"]
    E --> I{"Đã phát response?"}
    I -- "Chưa" --> J["onError / status lỗi"]
    I -- "Rồi" --> K["onError sau dữ liệu một phần"]
~~~

Mục tiêu của bài là xây dựng các kiểm thử tập trung vào ba kết cục này bằng gRPC Java **in-process transport**. Cách này kiểm tra được proto, stub, serialization, thứ tự message và status mà không cần mở cổng mạng. Sau đó cần biết phần nào phải kiểm tra thêm bằng Spring context hoặc môi trường transport thực.

## 2. Hợp đồng mẫu dùng trong kiểm thử

Một proto nhỏ giúp các ca kiểm thử dễ đọc:

~~~proto
syntax = "proto3";

package teststream.v1;

option java_multiple_files = true;
option java_package = "com.example.streamtest.rpc";

service SampleStreamService {
  rpc ReadItems(ReadItemsRequest) returns (stream StreamItem);
}

message ReadItemsRequest {
  string scenario = 1;
  int32 count = 2;
}

message StreamItem {
  int64 sequence = 1;
  string value = 2;
}
~~~

`scenario` chỉ là tham số của service giả lập dùng trong test để chọn kịch bản; không nhất thiết là trường nên đưa vào API nghiệp vụ production. Các class Java `ReadItemsRequest`, `StreamItem` và `SampleStreamServiceGrpc` được sinh bởi `protoc` cùng plugin gRPC Java.

## 3. Dựng server và channel in-process

In-process transport cho phép chạy server và client trong cùng tiến trình, nhưng vẫn đi qua API gRPC và stub được sinh. Một fixture JUnit 5 có thể khởi tạo server trước mỗi test và đóng tài nguyên sau test:

~~~java
import com.example.streamtest.rpc.ReadItemsRequest;
import com.example.streamtest.rpc.SampleStreamServiceGrpc;
import com.example.streamtest.rpc.StreamItem;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

import java.io.IOException;
import java.util.Iterator;

class ServerStreamBehaviorTest {
    private Server server;
    private ManagedChannel channel;

    @BeforeEach
    void startTransport() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new ScriptedStreamService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();
    }

    @AfterEach
    void stopTransport() {
        if (channel != null) {
            channel.shutdownNow();
        }
        if (server != null) {
            server.shutdownNow();
        }
    }

    private Iterator<StreamItem> invoke(String scenario, int count) {
        ReadItemsRequest request = ReadItemsRequest.newBuilder()
                .setScenario(scenario)
                .setCount(count)
                .build();

        return SampleStreamServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
                .readItems(request);
    }
}
~~~

`directExecutor()` giúp các callback của test chạy trực tiếp trên executor gọi tương ứng, làm ví dụ đơn giản và dễ kiểm soát. Nó không mô phỏng đầy đủ lịch chạy thread, backpressure hay độ trễ mạng production. Deadline ngắn ở stub là hàng rào để test không treo vô hạn nếu service giả lập bị lỗi.

## 4. Service giả lập ba kịch bản

Test cần một service có hành vi xác định: trả rỗng, trả nhiều phần tử hoặc phát lỗi. Service giả lập này cố ý chỉ dùng trong test:

~~~java
import com.example.streamtest.rpc.ReadItemsRequest;
import com.example.streamtest.rpc.SampleStreamServiceGrpc;
import com.example.streamtest.rpc.StreamItem;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

final class ScriptedStreamService
        extends SampleStreamServiceGrpc.SampleStreamServiceImplBase {

    @Override
    public void readItems(
            ReadItemsRequest request,
            StreamObserver<StreamItem> responses) {

        String scenario = request.getScenario();

        if ("empty".equals(scenario)) {
            responses.onCompleted();
            return;
        }

        if ("many".equals(scenario)) {
            int count = request.getCount();
            for (int i = 1; i <= count; i++) {
                responses.onNext(StreamItem.newBuilder()
                        .setSequence(i)
                        .setValue("item-" + i)
                        .build());
            }
            responses.onCompleted();
            return;
        }

        if ("error-before-first".equals(scenario)) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid test request")
                    .asRuntimeException());
            return;
        }

        if ("error-after-two".equals(scenario)) {
            responses.onNext(StreamItem.newBuilder()
                    .setSequence(1)
                    .setValue("item-1")
                    .build());
            responses.onNext(StreamItem.newBuilder()
                    .setSequence(2)
                    .setValue("item-2")
                    .build());
            responses.onError(Status.UNAVAILABLE
                    .withDescription("Test source interrupted")
                    .asRuntimeException());
            return;
        }

        responses.onError(Status.INVALID_ARGUMENT
                .withDescription("Unknown test scenario")
                .asRuntimeException());
    }
}
~~~

Mỗi nhánh kết thúc bằng đúng một terminal signal:

- Stream rỗng: `onCompleted`.
- Stream nhiều phần tử: nhiều `onNext`, sau đó `onCompleted`.
- Lỗi trước response: `onError(INVALID_ARGUMENT)`.
- Lỗi sau hai response: hai `onNext`, sau đó `onError(UNAVAILABLE)`.

Không gọi `onCompleted` sau `onError`, và không phát thêm `onNext` sau terminal signal. Nếu service production có repository hoặc event publisher, test tích hợp nên thay service giả lập bằng implementation thật và điều khiển nguồn dữ liệu qua mock/fake có khả năng tạo lỗi tại vị trí xác định.

## 5. Kiểm thử stream rỗng

Stream rỗng **không phải lỗi**. Khi truy vấn hợp lệ nhưng không có phần tử, server gọi `onCompleted()` mà không gọi `onNext()`. Với blocking stub, iterator phải hết ngay:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;

@org.junit.jupiter.api.Test
void emptyStreamCompletesSuccessfully() {
    Iterator<StreamItem> stream = invoke("empty", 0);

    assertFalse(stream.hasNext());
}
~~~

Kiểm thử này xác nhận:

- Không có response nào được cung cấp.
- RPC kết thúc bình thường thay vì ném `StatusRuntimeException`.
- Client không nhầm “không có dữ liệu” với lỗi nguồn.

Nếu API cần phân biệt “đối tượng không tồn tại” và “đối tượng tồn tại nhưng không có event”, hợp đồng phải quy định rõ: trường hợp đầu có thể trả `NOT_FOUND`, còn trường hợp sau trả stream rỗng và status `OK`. Không nên dùng stream rỗng để che giấu một lỗi mà client cần biết.

## 6. Kiểm thử stream có nhiều phần tử

Một stream nhiều phần tử cần kiểm tra **đủ số lượng**, **thứ tự**, và **giá trị từng response**. Chỉ kiểm tra `hasNext()` một lần không đủ để chứng minh server phát hết dữ liệu.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

@org.junit.jupiter.api.Test
void streamReturnsAllItemsInOrder() {
    Iterator<StreamItem> stream = invoke("many", 4);

    java.util.List<StreamItem> received = new java.util.ArrayList<>();
    while (stream.hasNext()) {
        received.add(stream.next());
    }

    assertEquals(4, received.size());
    assertEquals(
            java.util.List.of(1L, 2L, 3L, 4L),
            received.stream().map(StreamItem::getSequence).toList());
    assertEquals(
            java.util.List.of("item-1", "item-2", "item-3", "item-4"),
            received.stream().map(StreamItem::getValue).toList());
}
~~~

Vòng lặp chỉ kết thúc bình thường nếu RPC hoàn tất thành công. Nếu server phát ba response rồi kết thúc lỗi, `hasNext()` hoặc thao tác đọc tiếp theo có thể ném `StatusRuntimeException` thay vì trả `false`.

Nên thêm ca biên:

- `count = 1`: stream chỉ có một response.
- `count` bằng giới hạn tối đa của service: kiểm tra giới hạn request.
- `count = 0` hoặc âm: xác minh status theo hợp đồng, nếu service không coi đây là stream rỗng.
- Nhiều message có payload giống nhau nhưng sequence khác: không dùng payload để suy ra thứ tự.

## 7. Kiểm thử lỗi trước response đầu tiên

Nếu request không hợp lệ hoặc server không thể mở nguồn dữ liệu, server có thể kết thúc ngay bằng status lỗi. Client không được nhận response giả và không được coi iterator hết bình thường:

~~~java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@org.junit.jupiter.api.Test
void errorBeforeFirstItemIsExposedAsStatus() {
    Iterator<StreamItem> stream = invoke("error-before-first", 0);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            stream::hasNext);

    assertEquals(Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
}
~~~

Điều cần xác nhận là status code, không nên phụ thuộc quá chặt vào toàn bộ chuỗi `description` nếu mô tả có thể thay đổi. Nếu client cần phân nhánh logic, hãy dựa vào `Status.Code` hoặc error detail có cấu trúc theo hợp đồng.

## 8. Kiểm thử lỗi sau khi đã nhận một phần dữ liệu

Đây là ca quan trọng nhất của server streaming. Client nhận hai response trước khi server trả `UNAVAILABLE`. Hai response đó đã được giao cho client, nhưng **toàn bộ RPC thất bại**:

~~~java
@org.junit.jupiter.api.Test
void errorAfterTwoItemsDoesNotLookLikeSuccessfulCompletion() {
    Iterator<StreamItem> stream = invoke("error-after-two", 0);

    assertEquals(1L, stream.next().getSequence());
    assertEquals(2L, stream.next().getSequence());

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            stream::hasNext);

    assertEquals(Status.Code.UNAVAILABLE,
            error.getStatus().getCode());
}
~~~

Test này phân biệt hai trạng thái:

- Client **đã nhận** hai message.
- RPC **không hoàn tất thành công** vì terminal status là `UNAVAILABLE`.

Không viết test theo kiểu chỉ đếm hai response rồi kết luận thành công. Nếu client áp dụng dữ liệu vào database, cần kiểm tra riêng checkpoint/transaction của ứng dụng. Transport test không thể chứng minh side effect đã commit bền vững.

## 9. Kiểm thử asynchronous observer

Với asynchronous stub, client nhận từng response qua `onNext`, rồi một trong hai callback kết thúc là `onCompleted` hoặc `onError`. Một test nên ghi nhận chuỗi sự kiện để xác nhận thứ tự:

~~~java
java.util.List<String> callbacks =
        new java.util.concurrent.CopyOnWriteArrayList<>();
java.util.concurrent.CountDownLatch terminal =
        new java.util.concurrent.CountDownLatch(1);

SampleStreamServiceGrpc.newStub(channel)
        .withDeadlineAfter(3, java.util.concurrent.TimeUnit.SECONDS)
        .readItems(
                ReadItemsRequest.newBuilder()
                        .setScenario("error-after-two")
                        .build(),
                new io.grpc.stub.StreamObserver<StreamItem>() {
                    @Override
                    public void onNext(StreamItem item) {
                        callbacks.add("next-" + item.getSequence());
                    }

                    @Override
                    public void onError(Throwable error) {
                        callbacks.add("error-" +
                                io.grpc.Status.fromThrowable(error)
                                        .getCode().name());
                        terminal.countDown();
                    }

                    @Override
                    public void onCompleted() {
                        callbacks.add("completed");
                        terminal.countDown();
                    }
                });

assertTrue(terminal.await(3, java.util.concurrent.TimeUnit.SECONDS));
assertEquals(
        java.util.List.of("next-1", "next-2", "error-UNAVAILABLE"),
        callbacks);
~~~

Đoạn này giả định đang ở trong test có `channel` và các import JUnit cần thiết. `CopyOnWriteArrayList` giúp đọc danh sách callback an toàn trong test; latch chờ terminal callback mà không dùng sleep tùy ý. Với executor bất đồng bộ, không đọc danh sách trước khi latch kết thúc.

Không kỳ vọng `onCompleted` xuất hiện sau `onError`. Đây là hai terminal callback thay thế nhau. Client cũng không tự gọi chúng; gRPC runtime gọi callback phù hợp khi nhận kết cục của RPC.

## 10. Ma trận kiểm thử và các lỗi thường gặp

| Kịch bản | Message client nhận | Kết cục mong đợi |
|---|---:|---|
| Truy vấn hợp lệ, không có dữ liệu | 0 | `OK` / `onCompleted` |
| Truy vấn hợp lệ, có N phần tử | N | Đủ N message đúng thứ tự, rồi `OK` |
| Request sai trước khi phát | 0 | Status lỗi như `INVALID_ARGUMENT` |
| Nguồn lỗi sau k phần tử | Có thể k hoặc ít hơn tùy transport | Status lỗi; không đánh dấu stream hoàn tất |
| Lỗi trong một phần tử nhưng hợp đồng cho phép tiếp tục | Các kết quả hợp lệ và một message mô tả lỗi phần tử | Có thể kết thúc `OK` |
| Deadline hết giữa stream | Một phần hoặc không có message | `DEADLINE_EXCEEDED` ở client |
| Client chủ động hủy | Một phần hoặc không có message | Cancellation; server cleanup |

Các lỗi test phổ biến:

- **Chỉ assert số lượng:** có thể bỏ qua thứ tự sai hoặc payload sai.
- **Chỉ assert `onNext`:** chưa kiểm tra terminal status; stream có thể thất bại sau đó.
- **Dùng `sleep` để chờ callback:** test chập chờn theo tốc độ máy; dùng `CountDownLatch` hoặc future.
- **Không đóng channel/server:** rò rỉ thread và làm các test sau bị ảnh hưởng.
- **Dùng service giả lập rồi tuyên bố đã test Spring integration:** in-process test xác minh gRPC contract/transport, không tự xác minh Spring bean registration, interceptor hay cấu hình TLS.
- **Kiểm tra chính xác description của status:** dễ làm test giòn khi thông điệp lỗi được chỉnh sửa; ưu tiên kiểm tra status code và metadata cần thiết.

## 11. Khi nào cần test Spring context và transport thật?

In-process test đủ tốt để kiểm tra các hành vi gRPC cốt lõi: message rỗng, nhiều response, thứ tự và terminal status. Nhưng nó không chạy toàn bộ hạ tầng của ứng dụng Spring và không mô phỏng mạng thật.

Nên bổ sung `@SpringBootTest` hoặc integration test phù hợp khi cần xác minh:

- Spring gRPC tự đăng ký đúng service bean và cấu hình endpoint.
- Interceptor xác thực, phân quyền và trace được áp dụng.
- Lỗi từ repository thật được ánh xạ sang status dự kiến.
- TLS, certificate, proxy/load balancer và giới hạn message hoạt động đúng.
- Cancellation/deadline đóng cursor, subscription, timer và tài nguyên nguồn.

Với lỗi nguồn dữ liệu, một fake repository có thể phát hai bản ghi rồi ném lỗi xác định để kiểm tra implementation thật. Với transport, test qua cổng mạng cần kiểm soát timeout và cleanup; không thay mọi test logic nhanh bằng test mạng chậm.

## 12. Checklist cho một bộ test server streaming

- [ ] Có test stream rỗng và xác minh kết thúc `OK`.
- [ ] Có test nhiều response, xác minh số lượng, sequence, thứ tự và payload.
- [ ] Có test lỗi trước response đầu tiên và kiểm tra status code.
- [ ] Có test lỗi sau một số response và xác minh dữ liệu một phần cùng terminal error.
- [ ] Có test không phát `onCompleted` sau `onError`.
- [ ] Có test giới hạn đầu vào, deadline và cancellation khi phù hợp với method.
- [ ] Async test dùng latch/future thay cho `sleep` tùy ý.
- [ ] Server và channel được đóng trong `finally`/lifecycle test.
- [ ] Có integration test riêng cho Spring context, interceptor và TLS nếu đó là yêu cầu triển khai.

**Ghi nhớ:** Kiểm thử server streaming phải xác minh cả **chuỗi response** và **terminal status**. Stream rỗng có thể hoàn thành `OK`; stream nhiều phần tử phải trả đủ message đúng thứ tự; stream lỗi có thể đã giao một phần dữ liệu nhưng vẫn kết thúc bằng status không thành công. Hãy kiểm thử cả ba trường hợp bằng stub/transport, rồi kiểm tra riêng tác động của Spring, nguồn dữ liệu và hạ tầng mạng khi cần.
