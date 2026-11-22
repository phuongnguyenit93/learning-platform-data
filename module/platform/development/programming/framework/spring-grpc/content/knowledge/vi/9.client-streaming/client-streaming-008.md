# Giới hạn số message và kích thước batch

**Chương:** Client streaming  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) — thiết kế hợp đồng Protocol Buffers, sinh mã Java và kiểm soát tài nguyên cho RPC nhận nhiều request, trả một response.

## 1. Vì sao client streaming phải có giới hạn?

Client streaming cho phép một RPC nhận nhiều message request trước khi server trả kết quả cuối. Cơ chế này thuận tiện cho nhập dữ liệu, tải file theo chunk hoặc gửi số đo cảm biến theo lô. Tuy nhiên, nếu client có thể gửi vô hạn message hoặc một message có kích thước tùy ý, một RPC có thể chiếm băng thông, bộ nhớ, CPU, file descriptor và thời gian xử lý của server quá lâu.

Một giới hạn duy nhất như “tối đa 10 MB” chưa đủ rõ. Cần phân biệt **ba ngân sách độc lập**:

1. **Số message trong một RPC:** giới hạn số lần server nhận `onNext()`.
2. **Kích thước của từng message:** giới hạn một protobuf message đơn lẻ.
3. **Tổng kích thước của cả batch:** giới hạn tổng dữ liệu được gửi trong một RPC.

Ví dụ chính sách của dịch vụ tải dữ liệu:

| Ngân sách | Giới hạn minh họa | Mục đích |
| --- | ---: | --- |
| Số message / RPC | 1.024 message | Chặn luồng có quá nhiều phần tử nhỏ |
| Serialized size / message | 256 KiB | Chặn một message quá lớn |
| Tổng serialized size / batch | 8 MiB | Chặn tổng dữ liệu của cả lô |

Các con số trên là **chính sách minh họa**, không phải giá trị mặc định của gRPC hoặc Spring gRPC. Hệ thống thật cần chọn giới hạn dựa trên payload, năng lực máy chủ, độ trễ, quota của người dùng và giới hạn của các hệ thống phía sau.

## 2. Ba giới hạn giải quyết ba kiểu quá tải khác nhau

### 2.1. Giới hạn số message

Một client có thể gửi hàng triệu message rất nhỏ. Dù mỗi message chỉ vài byte, mỗi lần nhận vẫn phát sinh chi phí giải mã protobuf, callback, validation, logging, cập nhật trạng thái và có thể là một thao tác database. Giới hạn số message bảo vệ CPU và số thao tác theo từng RPC.

Điều kiện thường dùng:

```java
if (messageCount >= MAX_MESSAGES) {
    reject(Status.RESOURCE_EXHAUSTED, "Batch có quá nhiều message");
    return;
}
// Chỉ tăng sau khi request được xác thực và chấp nhận.
messageCount++;
```

Nếu `MAX_MESSAGES = 1_024`, server chấp nhận tối đa 1.024 message. Khi đã nhận đủ 1.024 mà có message thứ 1.025, server từ chối RPC. Kiểm tra trước khi tăng giúp tránh lệch một phần tử ở biên.

### 2.2. Giới hạn kích thước từng message

Một message protobuf có thể chứa trường `bytes`, chuỗi lớn hoặc nhiều phần tử lồng nhau. Nếu không giới hạn từng message, một request đơn có thể làm tăng đột biến bộ nhớ khi giải mã và xử lý.

Với lớp Java được sinh từ protobuf, `getSerializedSize()` trả về kích thước serialized của message theo byte:

```java
long messageBytes = request.getSerializedSize();
if (messageBytes > MAX_MESSAGE_BYTES) {
    reject(Status.RESOURCE_EXHAUSTED, "Message quá lớn");
    return;
}
```

Kích thước này bao gồm các trường protobuf được serialize, ví dụ `batch_id`, `sequence`, `payload` và overhead mã hóa trường. Nó **không phải** số byte chính xác truyền trên dây: HTTP/2 framing, header, compression và transport có thể làm số byte thực tế khác đi. Hãy ghi rõ hợp đồng quota đang tính theo serialized protobuf size hay theo riêng `payload.size()`.

### 2.3. Giới hạn tổng kích thước batch

Một lô có thể chứa nhiều message đều nhỏ hơn giới hạn từng message nhưng tổng cộng lại quá lớn. Vì vậy server cần một bộ đếm tổng byte riêng:

```java
if (messageBytes > MAX_BATCH_BYTES - batchBytes) {
    reject(Status.RESOURCE_EXHAUSTED, "Batch vượt giới hạn byte");
    return;
}
batchBytes += messageBytes;
```

Biểu thức `MAX_BATCH_BYTES - batchBytes` tránh cộng trước rồi mới so sánh, giảm nguy cơ tràn số khi cộng hai giá trị lớn. Dùng `long` cho bộ đếm tổng; không dùng `int` nếu tổng byte có thể vượt phạm vi số nguyên 32-bit.

### 2.4. Vì sao không thể thay ba giới hạn bằng một?

| Tình huống | Chỉ giới hạn message count | Chỉ giới hạn mỗi message | Chỉ giới hạn tổng batch |
| --- | --- | --- | --- |
| Hàng triệu message rất nhỏ | Có thể chặn | Không chặn | Chặn khi tổng byte vượt ngưỡng, nhưng có thể tốn CPU trước đó |
| Một message khổng lồ | Không chặn | Chặn | Có thể chặn, nhưng message đã phải được nhận/giải mã tùy tầng |
| Nhiều message nhỏ, tổng quá lớn | Chặn nếu đủ nhiều message | Không chặn | Chặn đúng tổng byte |
| Nhiều message gần mức tối đa | Chặn số lượng | Không chặn tổng | Chặn tổng byte |

Ba quota nên được kiểm tra đồng thời, trước khi message được đưa vào accumulator hoặc ghi xuống kho lưu trữ.

## 3. Kích thước message ở tầng protobuf và tầng transport

Giới hạn nghiệp vụ và giới hạn transport liên quan nhưng khác nhau:

- **Giới hạn nghiệp vụ** do service định nghĩa: tối đa bao nhiêu message, bao nhiêu byte mỗi message và bao nhiêu byte cho cả batch.
- **Giới hạn inbound message của gRPC server** được áp dụng ở tầng transport. Nếu một message vượt ngưỡng này, gRPC có thể từ chối trước khi gọi `onNext()` của service.
- **Giới hạn tổng batch** là trạng thái tích lũy qua nhiều request; giới hạn một message của transport không thể tự tính tổng này.
- **HTTP/2 flow control** điều tiết dữ liệu đang truyền và khả năng tiếp nhận của transport; nó không thay thế quota số message hay quota tổng batch.

Trong gRPC Java, server builder có API `maxInboundMessageSize(int)` để cấu hình giới hạn inbound message ở tầng server. Với Spring gRPC, hãy cấu hình builder/customizer tương ứng theo phiên bản starter đang dùng; tên property hoặc điểm mở rộng cấu hình có thể khác nhau giữa các phiên bản. Không giả định một property YAML chung nếu phiên bản thư viện chưa xác nhận.

Giới hạn inbound transport nên được đặt **ít nhất đủ để cho phép mức message nghiệp vụ đã công bố**, đồng thời không quá rộng so với khả năng của server. Nếu transport limit thấp hơn, request có thể bị từ chối trước khi logic quota của service chạy. Nếu transport limit cao hơn nhiều, service vẫn phải tự kiểm tra giới hạn từng message.

Với `getSerializedSize()`, ứng dụng đo kích thước protobuf trước khi compression. Transport có thể nén payload; không nên dùng số byte sau nén làm quota nghiệp vụ nếu mục tiêu là giới hạn chi phí giải mã và cấu trúc dữ liệu. Đồng thời, giới hạn message inbound của gRPC là cơ chế bảo vệ transport, không phải cơ chế giới hạn toàn bộ tài nguyên mà nghiệp vụ sử dụng.

## 4. Định nghĩa batch trong hợp đồng Protocol Buffers

Ví dụ dịch vụ nhập các bản ghi sự kiện. Một RPC chứa các message `BatchItem`, cùng một `batch_id`, sequence tăng dần; server trả một biên nhận có số message và tổng serialized bytes đã chấp nhận.

Tạo `src/main/proto/batch_ingest.proto`:

```proto
syntax = "proto3";

package ingest.v1;
option java_package = "com.example.ingest.grpc";
option java_multiple_files = true;

service BatchIngestService {
  rpc Upload(stream BatchItem) returns (BatchReceipt);
}

message BatchItem {
  string batch_id = 1;
  uint32 sequence = 2;
  string source = 3;
  bytes payload = 4;
}

message BatchReceipt {
  string batch_id = 1;
  int64 accepted_messages = 2;
  int64 accepted_serialized_bytes = 3;
}
```

Ở đây `accepted_serialized_bytes` được định nghĩa rõ là tổng `getSerializedSize()` của các `BatchItem` được chấp nhận. Nó **không** phải tổng riêng payload và cũng không phải số byte HTTP/2. Nếu nghiệp vụ cần số byte nội dung file, hãy thêm trường riêng và tính `payload.size()`.

Sau khi chạy protobuf compiler và plugin gRPC Java, các lớp `BatchItem`, `BatchReceipt`, `BatchIngestServiceGrpc` được sinh. Không viết tay lớp message hoặc stub.

## 5. Kiểm tra quota trong server Spring gRPC

Ví dụ dưới đây dùng ba hằng số chính sách: 1.024 message, 256 KiB serialized cho mỗi message và 8 MiB serialized cho cả batch. Service chỉ đếm và xác thực trong bộ nhớ; không ghi database và không giữ toàn bộ payload. Mỗi RPC có accumulator riêng.

```java
package com.example.ingest.server;

import com.example.ingest.grpc.BatchIngestServiceGrpc;
import com.example.ingest.grpc.BatchItem;
import com.example.ingest.grpc.BatchReceipt;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class BatchIngestGrpcService
        extends BatchIngestServiceGrpc.BatchIngestServiceImplBase {

    private static final long MAX_MESSAGES = 1_024L;
    private static final long MAX_MESSAGE_BYTES = 256L * 1024L;
    private static final long MAX_BATCH_BYTES = 8L * 1024L * 1024L;

    @Override
    public StreamObserver<BatchItem> upload(
            StreamObserver<BatchReceipt> responseObserver) {

        return new StreamObserver<>() {
            private String batchId;
            private long messageCount;
            private long batchBytes;
            private int nextSequence;
            private boolean terminated;

            @Override
            public void onNext(BatchItem item) {
                if (terminated) return;

                // Kiểm tra cấu trúc và tính nhất quán trước khi tiêu thụ quota.
                if (item.getBatchId().isBlank()
                        || item.getSource().isBlank()
                        || item.getPayload().isEmpty()) {
                    fail(Status.INVALID_ARGUMENT, "BatchItem không hợp lệ");
                    return;
                }
                if (batchId != null && !batchId.equals(item.getBatchId())) {
                    fail(Status.INVALID_ARGUMENT,
                            "Mọi message phải cùng batch_id");
                    return;
                }
                if (item.getSequence() != nextSequence) {
                    fail(Status.INVALID_ARGUMENT,
                            "sequence không liên tục");
                    return;
                }

                // getSerializedSize() là kích thước protobuf serialized.
                long messageBytes = item.getSerializedSize();

                if (messageBytes > MAX_MESSAGE_BYTES) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "Một message vượt giới hạn 256 KiB");
                    return;
                }
                if (messageCount >= MAX_MESSAGES) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "Batch vượt giới hạn 1.024 message");
                    return;
                }
                // So sánh trước khi cộng để tránh overflow.
                if (messageBytes > MAX_BATCH_BYTES - batchBytes) {
                    fail(Status.RESOURCE_EXHAUSTED,
                            "Batch vượt giới hạn 8 MiB");
                    return;
                }

                // Chỉ tiêu thụ quota sau khi tất cả kiểm tra đã đạt.
                batchId = item.getBatchId();
                messageCount++;
                batchBytes += messageBytes;
                nextSequence++;
            }

            @Override
            public void onError(Throwable cause) {
                // Inbound stream bị lỗi/hủy: dừng accumulator, cleanup nếu có.
                terminated = true;
            }

            @Override
            public void onCompleted() {
                if (terminated) return;
                if (messageCount == 0) {
                    fail(Status.INVALID_ARGUMENT, "Batch rỗng");
                    return;
                }

                BatchReceipt receipt = BatchReceipt.newBuilder()
                        .setBatchId(batchId)
                        .setAcceptedMessages(messageCount)
                        .setAcceptedSerializedBytes(batchBytes)
                        .build();

                terminated = true;
                responseObserver.onNext(receipt);
                responseObserver.onCompleted();
            }

            private void fail(Status status, String reason) {
                if (terminated) return;
                terminated = true;
                responseObserver.onError(
                        status.withDescription(reason).asRuntimeException());
            }
        };
    }
}
```

### Thứ tự kiểm tra quan trọng

1. Kiểm tra trường bắt buộc, `batch_id` và `sequence`.
2. Đo serialized size của message.
3. Kiểm tra giới hạn **mỗi message**.
4. Kiểm tra giới hạn **số message**.
5. Kiểm tra giới hạn **tổng batch bytes** bằng phép trừ an toàn.
6. Chỉ sau khi tất cả điều kiện đạt mới tăng bộ đếm và cập nhật trạng thái.

Như vậy, message bị từ chối không làm tăng `messageCount` hoặc `batchBytes`. Khi quota vượt, server kết thúc bằng `RESOURCE_EXHAUSTED`; không trả `BatchReceipt` thành công. Các lỗi sai cấu trúc hoặc sequence dùng `INVALID_ARGUMENT`.

### Vì sao không lưu toàn bộ message vào một List?

Mục tiêu của ví dụ là chứng minh cách giới hạn và đếm. Nếu service giữ tất cả `BatchItem` trong `List`, quota batch 8 MiB giới hạn serialized size nhưng bộ nhớ Java thực tế có thể cao hơn do object overhead, byte array, reference và cấu trúc collection. Nếu cần xử lý từng message, nên xử lý/ghi theo luồng với buffer hữu hạn; nếu cần xử lý toàn lô nguyên tử, dùng staging có giới hạn và chính sách dọn dẹp rõ ràng.

## 6. Client cũng nên kiểm tra trước khi gửi

Server là nơi thực thi quota có thẩm quyền; client kiểm tra trước giúp tránh gửi một batch chắc chắn bị từ chối. Client có thể duy trì cùng ba bộ đếm khi đọc nguồn dữ liệu, thay vì phải giữ toàn bộ batch trong RAM.

Một helper nhỏ cho producer tuần tự:

```java
import com.example.ingest.grpc.BatchItem;

final class BatchBudget {
    static final long MAX_MESSAGES = 1_024L;
    static final long MAX_MESSAGE_BYTES = 256L * 1024L;
    static final long MAX_BATCH_BYTES = 8L * 1024L * 1024L;

    private long count;
    private long totalBytes;

    void checkAndConsume(BatchItem item) {
        long size = item.getSerializedSize();
        if (size > MAX_MESSAGE_BYTES) {
            throw new IllegalArgumentException("Message quá lớn");
        }
        if (count >= MAX_MESSAGES) {
            throw new IllegalArgumentException("Quá số message tối đa");
        }
        if (size > MAX_BATCH_BYTES - totalBytes) {
            throw new IllegalArgumentException("Batch quá lớn");
        }

        count++;
        totalBytes += size;
    }
}
```

Producer gọi `checkAndConsume(item)` **trước** `requestObserver.onNext(item)`. Nếu kiểm tra thất bại, producer dừng nguồn đọc và hủy RPC đang mở; không gọi `onCompleted()` để biến một lô gửi thiếu thành công. Helper này chỉ là kiểm tra phía client; client có thể bị sửa hoặc bỏ qua nên server vẫn phải xác thực mọi request.

Nếu client đã gửi một phần rồi mới phát hiện vượt batch limit, RPC hiện tại không thể xóa những message đã gửi khỏi transport. Hãy hủy RPC và xử lý theo chính sách batch (bỏ staging, tra cứu trạng thái, hoặc chia lại dữ liệu thành lô mới). Đừng âm thầm mở RPC mới với cùng dữ liệu nếu server có tác dụng phụ mà chưa có idempotency.

## 7. Chọn con số giới hạn dựa trên ngân sách tài nguyên

Không chọn quota chỉ theo một con số dễ nhớ. Hãy bắt đầu từ payload thực tế và mục tiêu vận hành:

### 7.1. Xác định kích thước message

- Đo kích thước protobuf serialized của message điển hình và trường hợp lớn nhất.
- Tính cả metadata nằm trong message, ví dụ `batch_id`, `source`, sequence và các trường tùy chọn.
- Xác định có trường `bytes` nào có thể chứa dữ liệu lớn hoặc dữ liệu lồng nhau không.
- Đặt giới hạn thấp hơn ngưỡng gây áp lực lên memory/CPU, nhưng đủ cho payload hợp lệ.

### 7.2. Xác định batch size và số message

Nếu payload trung bình khoảng 4 KiB và batch tối đa 8 MiB, số message theo byte có thể xấp xỉ 2.048; nhưng quota 1.024 message sẽ chặn sớm hơn. Nếu payload rất nhỏ, giới hạn message count vẫn bảo vệ CPU và callback overhead. Nếu một message lớn, per-message quota chặn trước khi tổng batch đạt giới hạn.

Ba điều kiện có thể viết thành:

\[
\begin{aligned}
N &\leq N_{\max} \\
S_i &\leq S_{\text{message,max}} \quad \forall i \\
\sum_{i=1}^{N} S_i &\leq S_{\text{batch,max}}
\end{aligned}
\]

Trong đó \(S_i\) là serialized protobuf size của message thứ \(i\), không phải số byte file gốc hay byte truyền sau compression.

### 7.3. Tính tải đồng thời

Giới hạn 8 MiB/batch không có nghĩa server chỉ dùng 8 MiB. Nếu có 200 RPC đồng thời và mỗi RPC giữ staging buffer gần 8 MiB, lượng dữ liệu staging có thể tiến gần 1.6 GiB, chưa tính heap/object overhead, transport buffer và phần còn lại của ứng dụng.

Do đó cần đánh giá thêm:

- Số RPC đang mở tối đa theo người dùng/tenant hoặc toàn dịch vụ.
- Tổng quota bộ nhớ, file tạm và dung lượng staging trên toàn server.
- Số tác vụ ghi đồng thời và giới hạn connection pool database.
- Chính sách backpressure khi hàng đợi nội bộ đầy.
- Thời gian sống tối đa của một batch và deadline toàn RPC.

**Quota theo từng RPC phải kết hợp quota toàn hệ thống.** Nếu không, client có thể mở nhiều stream đồng thời để nhân tổng tài nguyên tiêu thụ.

## 8. Giới hạn batch khác với flow control và deadline

Ba cơ chế này bổ sung cho nhau:

| Cơ chế | Kiểm soát điều gì? | Không thay thế điều gì? |
| --- | --- | --- |
| Message/batch quota | Tổng lượng công việc được phép trong một RPC | Không điều tiết tốc độ gửi tức thời |
| HTTP/2/gRPC flow control | Khả năng truyền/nhận và áp lực buffer trong transport | Không giới hạn tổng số message hay tổng byte nghiệp vụ |
| Deadline | Thời gian tối đa cho toàn RPC | Không giới hạn số message/byte nếu client gửi rất nhanh |
| Concurrent RPC/quota toàn hệ thống | Tổng số công việc đồng thời | Không thay thế giới hạn từng batch |

Với gRPC Java, client có thể dùng `ClientResponseObserver` và `ClientCallStreamObserver.isReady()`/ `setOnReadyHandler()` để phát dữ liệu theo khả năng transport. Điều đó giúp tránh đẩy quá nhanh, nhưng một batch vẫn có thể vượt 8 MiB nếu không có bộ đếm nghiệp vụ.

Deadline bao trùm mở stream, gửi message, xử lý server và nhận receipt. Đặt deadline hợp lý để tránh stream bị giữ quá lâu; deadline không phải công cụ duy nhất để giới hạn tài nguyên.

## 9. Status lỗi và hành vi ở biên giới quota

| Tình huống | Status đề xuất | Ghi chú |
| --- | --- | --- |
| Message serialized size vượt mức | `RESOURCE_EXHAUSTED` | Request vượt ngân sách tài nguyên |
| Tổng batch bytes vượt mức | `RESOURCE_EXHAUSTED` | Từ chối toàn RPC theo hợp đồng ví dụ |
| Số message vượt mức | `RESOURCE_EXHAUSTED` | Request tiếp theo sau khi đã đạt quota bị từ chối |
| Thiếu `batch_id`, payload sai cấu trúc | `INVALID_ARGUMENT` | Client cần sửa dữ liệu |
| Sequence không liên tục | `INVALID_ARGUMENT` | Không phải lỗi dung lượng |
| Transport inbound message limit bị vượt | gRPC transport từ chối trước khi service xử lý | Status quan sát tùy lỗi transport; service có thể không nhận callback `onNext` |
| Deadline hết trong khi gửi | Thường `DEADLINE_EXCEEDED` phía client | Batch có thể đã được xử lý một phần |
| Client chủ động hủy | Thường `CANCELLED` | Dừng producer và cleanup |

Chọn một chính sách nhất quán cho cả batch: ví dụ **fail-fast** khi bất kỳ message nào vượt quota, không trả biên nhận thành công một phần. Nếu nghiệp vụ muốn chấp nhận một phần, hợp đồng response phải diễn đạt rõ số message đã chấp nhận, số bị từ chối và cách tra cứu trạng thái; không dùng một status `OK` mơ hồ.

## 10. Kiểm thử ranh giới số message và kích thước

Kiểm thử in-process có thể xác nhận quota nghiệp vụ trong service. Test dưới đây dùng JUnit 5, `grpc-inprocess` và các lớp sinh từ protobuf. Ví dụ gọi server qua async stub và xác nhận message thứ vượt giới hạn nhận status `RESOURCE_EXHAUSTED`.

```java
package com.example.ingest;

import com.example.ingest.grpc.BatchIngestServiceGrpc;
import com.example.ingest.grpc.BatchItem;
import com.example.ingest.grpc.BatchReceipt;
import com.example.ingest.server.BatchIngestGrpcService;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BatchQuotaTest {

    @Test
    void rejectsMessageBeyondCountLimit() throws Exception {
        String name = InProcessServerBuilder.generateName();
        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new BatchIngestGrpcService())
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            CompletableFuture<Status.Code> ended = new CompletableFuture<>();
            StreamObserver<BatchReceipt> responses = new StreamObserver<>() {
                @Override
                public void onNext(BatchReceipt receipt) {
                    ended.completeExceptionally(
                            new AssertionError("Không được trả receipt"));
                }

                @Override
                public void onError(Throwable error) {
                    ended.complete(Status.fromThrowable(error).getCode());
                }

                @Override
                public void onCompleted() {
                    ended.completeExceptionally(
                            new AssertionError("Không được kết thúc OK"));
                }
            };

            StreamObserver<BatchItem> requests =
                    BatchIngestServiceGrpc.newStub(channel).upload(responses);

            // Giới hạn server là 1.024; message thứ 1.025 phải bị từ chối.
            for (int i = 0; i < 1_025; i++) {
                requests.onNext(item(i));
            }

            assertEquals(Status.Code.RESOURCE_EXHAUSTED,
                    ended.get(3, TimeUnit.SECONDS));
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }

    private static BatchItem item(int sequence) {
        return BatchItem.newBuilder()
                .setBatchId("batch-test")
                .setSequence(sequence)
                .setSource("sensor-a")
                .setPayload(com.google.protobuf.ByteString.copyFromUtf8("x"))
                .build();
    }
}
```

Để kiểm thử riêng hai quota byte:

1. **Per-message:** tạo một `BatchItem` có payload đủ lớn để `getSerializedSize() > 256 KiB`; xác nhận server trả `RESOURCE_EXHAUSTED`.
2. **Per-batch:** gửi các message đều nhỏ hơn 256 KiB nhưng tổng serialized size vượt 8 MiB; xác nhận server từ chối đúng message vượt ngưỡng.
3. **Biên chính xác:** gửi batch có đúng 1.024 message và tổng serialized size đúng 8 MiB (nếu tạo được payload phù hợp); xác nhận chính sách là chấp nhận bằng dấu `<=`.
4. **Sequence sai:** gửi sequence 0 rồi 2; xác nhận `INVALID_ARGUMENT`, không nhầm thành quota error.
5. **Đồng thời:** hai RPC mỗi cái nằm trong quota; xác nhận quota của một RPC không vô tình cộng vào RPC kia.

Kiểm thử in-process không thay thế kiểm thử giới hạn inbound message ở transport thật. Hãy có một integration test dùng server được cấu hình `maxInboundMessageSize`, gửi message vượt transport limit và xác nhận service không xử lý message đó. Đồng thời đo heap, CPU và file staging khi có nhiều RPC đồng thời; chỉ kiểm tra status là chưa đủ để chứng minh giới hạn bảo vệ được tài nguyên.

## 11. Checklist thiết kế quota cho một dịch vụ

- [ ] Định nghĩa rõ một message được tính theo `getSerializedSize()`, `payload.size()` hay tiêu chí khác.
- [ ] Đặt giới hạn số message trên mỗi RPC.
- [ ] Đặt giới hạn kích thước serialized cho mỗi message.
- [ ] Đặt giới hạn tổng batch bytes bằng bộ đếm `long` và phép so sánh tránh overflow.
- [ ] Cấu hình inbound transport limit tương thích với quota nghiệp vụ.
- [ ] Xác thực quota phía server trước khi tiêu thụ tài nguyên hoặc ghi dữ liệu.
- [ ] Client preflight để tránh gửi lô chắc chắn bị từ chối.
- [ ] Kết hợp quota từng RPC với quota đồng thời/toàn hệ thống.
- [ ] Đặt deadline, flow control và giới hạn hàng đợi.
- [ ] Kiểm thử dưới ngưỡng, đúng ngưỡng, vượt ngưỡng và nhiều RPC đồng thời.
- [ ] Ghi metrics về số message, serialized bytes, batch duration và status; tránh log payload nhạy cảm.

## 12. Tự luyện tập

1. Một batch có 800 message, mỗi message 12 KiB. Với chính sách ở bài, giới hạn nào sẽ chặn trước: số message, kích thước mỗi message hay tổng batch bytes?
2. Vì sao `getSerializedSize()` khác với `payload.size()`? Khi nào nên công bố mỗi đại lượng trong `UploadReceipt`?
3. Nếu transport `maxInboundMessageSize` nhỏ hơn giới hạn 256 KiB của service, điều gì xảy ra với một request 200 KiB? Vì sao service có thể không nhận được `onNext()`?
4. Client đã gửi 500 message rồi phát hiện tổng batch vượt quota. Vì sao không thể chỉ bỏ message cuối và tiếp tục coi lô hiện tại là hợp lệ?
5. Một server cho phép 8 MiB mỗi batch và 500 batch đồng thời. Hãy tính ngân sách dữ liệu thô tối đa theo chính sách đó và đề xuất giới hạn concurrency phù hợp với heap/staging thực tế.

**Ghi nhớ:** Một client streaming RPC cần ít nhất ba quota nghiệp vụ: **số message**, **serialized size của từng message** và **tổng serialized bytes của batch**. Kiểm tra ở server trước khi xử lý, dùng `long` và phép so sánh tránh overflow, cấu hình transport inbound limit phù hợp, đồng thời kết hợp flow control, deadline và quota đồng thời để bảo vệ toàn dịch vụ.
