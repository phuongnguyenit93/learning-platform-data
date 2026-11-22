# Kiểm thử client gửi rỗng, một phần và đầy đủ

**Chương:** Client streaming  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) với hợp đồng Protocol Buffers, mã Java được sinh và client streaming RPC nhận nhiều request, trả một response.

## 1. Ba trường hợp cần kiểm thử

Một client streaming RPC có thể nhận nhiều message request, nhưng server chỉ trả một response thành công sau khi client kết thúc luồng gửi. Khi kiểm thử, cần phân biệt ba trạng thái của batch:

| Trường hợp | Client gửi gì? | Kết quả mong đợi |
| --- | --- | --- |
| **Rỗng** | Khai báo batch có 0 phần tử rồi half-close | Server từ chối bằng `INVALID_ARGUMENT`; không có receipt |
| **Một phần** | Khai báo cần 3 phần tử, chỉ gửi 2 rồi half-close | Server từ chối bằng `FAILED_PRECONDITION`; không có receipt thành công |
| **Đầy đủ** | Khai báo cần 3 phần tử, gửi đủ 3 rồi half-close | Server trả đúng một receipt, sau đó kết thúc `OK` |

Điểm quan trọng là trường hợp **một phần** vẫn có thể kết thúc chiều gửi bình thường: client gọi `requestObserver.onCompleted()`, nhưng số phần tử thực tế không khớp số lượng đã cam kết trong manifest. Đây là lỗi tính đầy đủ của batch, khác với trường hợp client bị mất kết nối hoặc hủy trước khi half-close.

## 2. Đặt quy tắc batch trong hợp đồng

Để server biết một batch đã đầy đủ hay chưa, client phải khai báo số phần tử dự kiến. Ví dụ hợp đồng:

```proto
syntax = "proto3";

package ingest.v1;
option java_package = "com.example.ingest.grpc";
option java_multiple_files = true;

service BatchService {
  rpc Upload(stream UploadRequest) returns (UploadReceipt);
}

message UploadRequest {
  oneof body {
    BatchStart start = 1;
    BatchItem item = 2;
  }
}

message BatchStart {
  string batch_id = 1;
  uint32 expected_count = 2;
}

message BatchItem {
  uint32 sequence = 1;
  string value = 2;
}

message UploadReceipt {
  string batch_id = 1;
  uint32 accepted_count = 2;
}
```

Quy ước của ví dụ:

1. Message đầu tiên phải là `BatchStart`, xuất hiện đúng một lần.
2. `expected_count` phải lớn hơn 0 và không vượt quota của dịch vụ.
3. Các message tiếp theo phải là `BatchItem`, có `sequence` liên tục từ 0.
4. Client gọi `onCompleted()` khi đã gửi hết dữ liệu định gửi.
5. Server chỉ trả receipt nếu số item thực tế bằng `expected_count`.

Không có `expected_count`, server không thể phân biệt một batch đã gửi đủ với một batch bị cắt ngắn nhưng client vẫn chủ động half-close. Với nguồn dữ liệu không biết trước số phần tử, có thể dùng manifest chứa tổng byte/hash hoặc giao thức commit riêng; bài này dùng số lượng dự kiến để minh họa rõ ba trường hợp.

## 3. Server kiểm tra số lượng trước khi trả receipt

Phần xử lý quan trọng nằm ở observer nhận request: đếm item, kiểm tra sequence và so sánh số lượng khi nhận inbound `onCompleted()`.

```java
@GrpcService
public class BatchGrpcService extends BatchServiceGrpc.BatchServiceImplBase {

    private static final int MAX_ITEMS = 1_000;

    @Override
    public StreamObserver<UploadRequest> upload(
            StreamObserver<UploadReceipt> responseObserver) {

        return new StreamObserver<>() {
            private String batchId;
            private int expectedCount;
            private int receivedCount;
            private boolean started;
            private boolean terminated;

            @Override
            public void onNext(UploadRequest request) {
                if (terminated) return;

                switch (request.getBodyCase()) {
                    case START -> {
                        if (started) {
                            fail(Status.INVALID_ARGUMENT,
                                    "BatchStart chỉ được gửi một lần");
                            return;
                        }
                        BatchStart start = request.getStart();
                        if (start.getBatchId().isBlank()
                                || start.getExpectedCount() > MAX_ITEMS) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Manifest không hợp lệ");
                            return;
                        }
                        started = true;
                        batchId = start.getBatchId();
                        expectedCount = start.getExpectedCount();
                    }
                    case ITEM -> {
                        if (!started) {
                            fail(Status.INVALID_ARGUMENT,
                                    "BatchStart phải là message đầu tiên");
                            return;
                        }
                        if (receivedCount >= expectedCount) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Nhận nhiều item hơn expected_count");
                            return;
                        }
                        BatchItem item = request.getItem();
                        if (item.getSequence() != receivedCount) {
                            fail(Status.INVALID_ARGUMENT,
                                    "Sequence không liên tục");
                            return;
                        }
                        receivedCount++;
                    }
                    case BODY_NOT_SET -> fail(
                            Status.INVALID_ARGUMENT, "Thiếu nội dung request");
                }
            }

            @Override
            public void onError(Throwable error) {
                // Client hủy hoặc inbound stream gặp lỗi.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) return;
                if (!started) {
                    fail(Status.INVALID_ARGUMENT, "Thiếu BatchStart");
                    return;
                }
                if (expectedCount == 0) {
                    fail(Status.INVALID_ARGUMENT, "Batch rỗng");
                    return;
                }
                if (receivedCount < expectedCount) {
                    fail(Status.FAILED_PRECONDITION,
                            "Batch chưa đủ phần tử");
                    return;
                }

                UploadReceipt receipt = UploadReceipt.newBuilder()
                        .setBatchId(batchId)
                        .setAcceptedCount(receivedCount)
                        .build();
                terminated = true;
                responseObserver.onNext(receipt);
                responseObserver.onCompleted();
            }

            private void fail(Status status, String description) {
                if (terminated) return;
                terminated = true;
                responseObserver.onError(status
                        .withDescription(description)
                        .asRuntimeException());
            }
        };
    }
}
```

Ví dụ tập trung vào kiểm tra đầy đủ, không lưu dữ liệu nghiệp vụ. Trong dịch vụ thực, validation từng item và commit dữ liệu phải diễn ra trước khi gửi receipt. Nếu commit lỗi, server kết thúc bằng status lỗi; không trả receipt thành công chỉ vì số lượng message đã đủ.

### Vì sao chọn hai status khác nhau?

- `INVALID_ARGUMENT`: client khai báo batch rỗng, thiếu manifest, gửi sai thứ tự hoặc gửi nhiều phần tử hơn đã khai báo. Request vi phạm quy tắc đầu vào.
- `FAILED_PRECONDITION`: client đã half-close nhưng số item nhận được ít hơn số đã cam kết. Batch chưa đạt điều kiện để hoàn tất.

Đây là chính sách API của ví dụ. Một hệ thống có thể chọn status khác nếu hợp đồng quy định rõ, nhưng phải giữ cách phân loại nhất quán giữa server, client và test.

## 4. Viết test cho ba trường hợp bằng gRPC in-process

Kiểm thử in-process chạy gRPC server và channel trong cùng tiến trình, nhưng vẫn đi qua stub, transport nội bộ và callback thực của gRPC. Nhờ đó test có thể xác nhận status cuối, số response và hành vi khi client half-close.

Một helper kiểm thử có thể mở stream, gửi manifest, gửi số item được chỉ định rồi gọi `onCompleted()`:

```java
record Outcome(
        UploadReceipt receipt,
        Status.Code error,
        int responseCount,
        boolean completed) {}

private Outcome upload(int expected, int actual) throws Exception {
    CompletableFuture<Outcome> result = new CompletableFuture<>();
    AtomicInteger responseCount = new AtomicInteger();

    StreamObserver<UploadReceipt> responses = new StreamObserver<>() {
        private UploadReceipt receipt;

        @Override
        public void onNext(UploadReceipt value) {
            receipt = value;
            responseCount.incrementAndGet();
        }

        @Override
        public void onError(Throwable error) {
            result.complete(new Outcome(
                    null,
                    Status.fromThrowable(error).getCode(),
                    responseCount.get(),
                    false));
        }

        @Override
        public void onCompleted() {
            result.complete(new Outcome(
                    receipt, null, responseCount.get(), true));
        }
    };

    StreamObserver<UploadRequest> requests =
            BatchServiceGrpc.newStub(channel).upload(responses);

    requests.onNext(UploadRequest.newBuilder()
            .setStart(BatchStart.newBuilder()
                    .setBatchId("test-batch")
                    .setExpectedCount(expected))
            .build());

    for (int i = 0; i < actual; i++) {
        requests.onNext(UploadRequest.newBuilder()
                .setItem(BatchItem.newBuilder()
                        .setSequence(i)
                        .setValue("value-" + i))
                .build());
    }

    requests.onCompleted();
    return result.get(3, TimeUnit.SECONDS);
}
```

Helper giả định test đã khởi tạo `channel` in-process và thêm `BatchGrpcService`. Mỗi lần gọi tạo một RPC mới; `CompletableFuture` chờ terminal callback thay vì dùng `Thread.sleep()`.

### Test 1: client gửi batch rỗng

```java
@Test
void rejectsEmptyBatch() throws Exception {
    Outcome outcome = upload(0, 0);

    assertEquals(Status.Code.INVALID_ARGUMENT, outcome.error());
    assertNull(outcome.receipt());
    assertEquals(0, outcome.responseCount());
    assertFalse(outcome.completed());
}
```

Client vẫn gửi `BatchStart(expected_count = 0)` rồi half-close. Đây là một batch rỗng được khai báo rõ, không phải trường hợp không gửi bất kỳ request message nào. Có thể thêm test riêng cho stream không có cả `BatchStart`; server cũng phải từ chối vì thiếu manifest.

### Test 2: client gửi một phần batch

```java
@Test
void rejectsPartialBatchAfterHalfClose() throws Exception {
    // Cam kết 3 item nhưng chỉ gửi 2, sau đó kết thúc chiều request.
    Outcome outcome = upload(3, 2);

    assertEquals(Status.Code.FAILED_PRECONDITION, outcome.error());
    assertNull(outcome.receipt());
    assertEquals(0, outcome.responseCount());
    assertFalse(outcome.completed());
}
```

Đây là test quan trọng: client đã gọi `onCompleted()`, nhưng server vẫn từ chối vì batch không đầy đủ. **Kết thúc chiều gửi không tự chứng minh batch hợp lệ.**

### Test 3: client gửi đầy đủ batch

```java
@Test
void acceptsCompleteBatchWithOneReceipt() throws Exception {
    Outcome outcome = upload(3, 3);

    assertNull(outcome.error());
    assertTrue(outcome.completed());
    assertNotNull(outcome.receipt());
    assertEquals("test-batch", outcome.receipt().getBatchId());
    assertEquals(3, outcome.receipt().getAcceptedCount());
    assertEquals(1, outcome.responseCount());
}
```

Test đầy đủ xác nhận server trả đúng **một** response rồi kết thúc bình thường. Không chỉ kiểm tra `completed == true`: cần kiểm tra receipt, batch ID và số lượng đã chấp nhận.

## 5. Phân biệt batch một phần với stream bị gián đoạn

Hai tình huống này không giống nhau:

| Tình huống | Client có gọi `onCompleted()`? | Kết quả |
| --- | --- | --- |
| Gửi 2/3 item rồi half-close | Có | Server nhận inbound `onCompleted()`, phát hiện thiếu và trả `FAILED_PRECONDITION` |
| Gửi 2/3 item rồi mất kết nối/hủy | Không nhất thiết | RPC kết thúc do transport/cancellation; server cleanup staging, client nhận status tương ứng |

Test partial batch ở mục 4 kiểm tra **đầu vào không đầy đủ nhưng stream đóng bình thường**. Nếu muốn kiểm tra gián đoạn, hãy tạo test riêng: gửi manifest và một item, gọi cancel hoặc làm hết deadline trước half-close; xác nhận không có receipt thành công và tài nguyên staging được dọn.

Không nên gộp hai test thành một vì chúng xác minh hai đường kết thúc khác nhau: một đường là server chủ động từ chối điều kiện nghiệp vụ, đường còn lại là RPC bị hủy hoặc lỗi transport.

## 6. Ma trận kiểm thử tối thiểu

| Ca kiểm thử | Request | Kết quả cần xác nhận |
| --- | --- | --- |
| Stream hoàn toàn rỗng | Không có BatchStart, half-close | `INVALID_ARGUMENT`, không receipt |
| Batch khai báo 0 item | Start với expected_count = 0, half-close | `INVALID_ARGUMENT`, không receipt |
| Batch một phần | expected = 3, actual = 2, half-close | `FAILED_PRECONDITION`, không receipt |
| Batch đầy đủ | expected = 3, actual = 3, half-close | `OK`, một receipt, accepted_count = 3 |
| Gửi dư | expected = 2, actual = 3 | `INVALID_ARGUMENT`, không receipt |
| Sai sequence | Gửi 0 rồi 2 | `INVALID_ARGUMENT` |
| Thiếu BatchStart | Gửi item trước manifest | `INVALID_ARGUMENT` |
| Hủy giữa luồng | Gửi một phần rồi cancel | Không receipt thành công; cleanup chạy |
| Hai client đồng thời | Hai batch ID khác nhau | Trạng thái và receipt không bị trộn |

Với mỗi test lỗi, nên khẳng định **không có response message thành công**. Với test thành công, khẳng định đúng một response. Đây là cách phát hiện server vô tình gọi `onNext(receipt)` trước khi kiểm tra số lượng.

## 7. Các lỗi thường gặp khi viết test

- **Chỉ kiểm tra status:** test có thể bỏ sót việc server đã gửi receipt trước khi trả lỗi. Hãy đếm số response message.
- **Nhầm half-close với thành công:** test partial phải gọi `onCompleted()` để chứng minh server vẫn kiểm tra số lượng thực tế.
- **Không có manifest:** nếu server không biết số lượng dự kiến, test không thể định nghĩa “một phần” một cách rõ ràng.
- **Dùng sleep để chờ callback:** dễ tạo test chập chờn. Dùng `CompletableFuture`, latch hoặc barrier với timeout hữu hạn.
- **Chỉ test một RPC:** cần test hai batch đồng thời để phát hiện state bị chia sẻ giữa các observer.
- **Bỏ qua trạng thái lưu trữ:** nếu service ghi staging/database, hãy xác nhận số bản ghi và cleanup sau test partial, empty và cancel.

## 8. Tự luyện tập

1. Viết test cho stream không gửi cả `BatchStart`, sau đó half-close. Status nên là gì?
2. Nếu client khai báo 4 item, gửi 4 item nhưng sequence là 0, 1, 3, 4, server nên trả gì? Vì sao không được trả receipt?
3. Bổ sung test gửi dư một item so với `expected_count`; xác nhận server không phát receipt trước khi báo lỗi.
4. Thêm tầng staging giả lập và xác minh batch partial bị dọn khi half-close thiếu item; phân biệt với cancellation trước half-close.
5. Nếu server trả receipt sau khi đủ số item nhưng commit database thất bại, cần sửa thứ tự xử lý và assertion nào?

**Ghi nhớ:** Kiểm thử client streaming cần bao phủ **batch rỗng, batch một phần và batch đầy đủ**. Hãy khai báo số phần tử dự kiến trong manifest, kiểm tra số message thực tế khi inbound `onCompleted()`, xác nhận status và số response: batch rỗng/thiếu phải bị từ chối không có receipt; batch đủ chỉ trả đúng một receipt rồi kết thúc `OK`.
