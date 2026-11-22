# Tạo client streaming cho upload batch

Trong dự án này, bạn sẽ xây dựng một luồng upload dữ liệu tồn kho theo batch bằng Spring gRPC. Client đọc một file CSV, gửi nhiều bản ghi trong cùng một client-streaming RPC và chỉ nhận một kết quả tổng hợp khi server xử lý xong toàn bộ batch.

Đây là tình huống phù hợp với client streaming: số lượng bản ghi có thể lớn, client muốn gửi dữ liệu tuần tự thay vì tạo một RPC cho từng dòng, còn server cần kiểm tra và ghi nhận dữ liệu trong khi luồng đang chạy. Dự án cũng xử lý các vấn đề vận hành thường gặp như metadata xác thực, deadline, status, giới hạn kích thước, cancellation, backpressure, tính idempotent và kiểm thử tích hợp.

## 1. Kết quả cần đạt

Xây dựng hai thành phần:

- **Batch upload server:** một dịch vụ Spring gRPC nhận luồng bản ghi tồn kho, xác thực caller, kiểm tra thứ tự và dữ liệu, ghi dữ liệu vào vùng staging rồi công bố batch khi client kết thúc stream hợp lệ.
- **Batch upload client:** một chương trình Java đọc CSV theo từng dòng, mở một RPC, gửi frame bắt đầu và các bản ghi, sau đó chờ kết quả cuối cùng từ server.

Ví dụ dữ liệu đầu vào:

```csv
sku,warehouse_code,quantity
SKU-001,HCM-01,30
SKU-002,HCM-01,12
SKU-003,DN-02,7
```

Khi hoàn tất, server trả về `batch_id`, số bản ghi đã nhận và trạng thái commit. Nếu một bản ghi sai, stream bị hủy, deadline hết hoặc server không thể commit, batch không được công bố một phần. Client có thể tra cứu trạng thái batch bằng một API riêng nếu cần theo dõi sau khi mất kết nối.

### Phạm vi phiên bản đầu

- Một RPC client streaming: nhiều `UploadFrame` đi vào, một `UploadResult` đi ra.
- Mỗi stream có đúng một frame `BatchStart`, đứng đầu luồng.
- Các frame tiếp theo chứa bản ghi có sequence tăng liên tục từ 1.
- Một batch được commit toàn bộ hoặc bị abort toàn bộ.
- Giới hạn số bản ghi, dung lượng và thời gian upload.
- Client gửi cùng `batch_id` khi cần thử lại một batch; server bảo đảm xử lý idempotent theo tenant và batch ID.

Phiên bản đầu không hỗ trợ resume từ sequence bất kỳ sau khi kết nối bị ngắt. Khi upload bị gián đoạn, client gửi lại batch với cùng `batch_id`; server phải nhận diện batch đã commit hoặc cho phép tạo lại batch chưa hoàn tất theo chính sách đã định nghĩa.

## 2. Thiết kế contract Protocol Buffers

Tạo file `src/main/proto/batch_upload.proto`:

```protobuf
syntax = "proto3";

package inventory.batch.v1;

option java_package = "com.example.inventory.batch.v1";
option java_multiple_files = true;

service BatchUploadService {
  rpc UploadBatch(stream UploadFrame) returns (UploadResult);
}

message UploadFrame {
  oneof frame {
    BatchStart start = 1;
    InventoryRecord record = 2;
  }
}

message BatchStart {
  string batch_id = 1;
  string source = 2;
  uint64 expected_records = 3;
}

message InventoryRecord {
  uint64 sequence = 1;
  string sku = 2;
  string warehouse_code = 3;
  int32 quantity = 4;
}

message UploadResult {
  string batch_id = 1;
  uint64 accepted_records = 2;
  UploadState state = 3;
}

enum UploadState {
  UPLOAD_STATE_UNSPECIFIED = 0;
  UPLOAD_STATE_COMMITTED = 1;
}
```

`oneof` giúp server phân biệt frame bắt đầu với frame dữ liệu và phát hiện frame không có nội dung. `expected_records` cho phép server xác nhận client đã gửi đủ số bản ghi dự kiến trước khi commit. `sequence` giúp phát hiện bản ghi bị thiếu, lặp hoặc sai thứ tự.

Thông tin xác thực không đặt trong từng record. Client gửi access token trong gRPC metadata; server xác thực token và lấy tenant từ principal đã xác thực. `batch_id` là khóa idempotency trong phạm vi tenant, không phải thông tin xác thực.

Sau khi cập nhật `.proto`, chạy tác vụ generate code do Maven hoặc Gradle protobuf plugin của dự án cấu hình. Phiên bản `protoc`, grpc-java plugin và các thư viện runtime phải tương thích. Không chỉnh sửa thủ công các class được sinh mã.

## 3. Cấu trúc thành phần

Có thể tổ chức mã nguồn theo cấu trúc sau:

```text
src/main/
  proto/
    batch_upload.proto
  java/com/example/inventory/
    grpc/
      BatchUploadGrpcService.java
      BatchUploadObserver.java
      AuthServerInterceptor.java
      GrpcTenantContext.java
    application/
      BatchUploadProcessor.java
      UploadSession.java
      UploadLimitExceededException.java
    infrastructure/
      StagingBatchUploadProcessor.java
  resources/
    application.yml
src/test/
  java/com/example/inventory/
    grpc/
      BatchUploadContractTest.java
      BatchUploadSpringIntegrationTest.java
```

Spring gRPC starter cụ thể sẽ quyết định cách đăng ký service, interceptor, port và TLS. Hãy dùng cơ chế auto-configuration hoặc bean registration của starter mà dự án đã chọn; không tự tạo một server thứ hai nếu starter đã quản lý server lifecycle.

## 4. Xây dựng tầng xử lý batch

Không nên để gRPC service tự quản lý SQL, transaction và quy tắc lưu trữ. Tạo một abstraction để service chỉ điều phối các frame:

```java
public interface BatchUploadProcessor {

    UploadSession begin(String tenantId, BatchStart start);

    void append(UploadSession session, InventoryRecord record);

    UploadResult commit(UploadSession session);

    void abort(UploadSession session);
}
```

`UploadSession` đại diện cho một batch đang nhận dữ liệu. Processor chịu trách nhiệm kiểm tra giới hạn, lưu staging record và bảo đảm tính nhất quán. Trong bản triển khai thật, session nên chứa ID nội bộ và metadata cần thiết, không cần giữ toàn bộ file trong RAM.

### 4.1. Dùng staging để giữ tính atomic

Một cách triển khai phù hợp cho batch lớn là lưu dữ liệu vào staging table:

| Bảng | Trường gợi ý | Mục đích |
|---|---|---|
| `upload_batch` | `tenant_id`, `batch_id`, `source`, `expected_records`, `received_records`, `status`, `created_at`, `completed_at` | Theo dõi trạng thái và idempotency của batch. |
| `upload_batch_record` | `tenant_id`, `batch_id`, `sequence`, `sku`, `warehouse_code`, `quantity` | Lưu tạm từng record theo thứ tự. |
| `inventory` | `tenant_id`, `warehouse_code`, `sku`, `quantity` | Dữ liệu tồn kho đã được công bố cho nghiệp vụ. |

Đặt unique constraint cho `(tenant_id, batch_id)` và `(tenant_id, batch_id, sequence)`. Khi `begin`, server tạo hoặc tra cứu batch. Khi `append`, server kiểm tra và ghi record vào staging. Khi `commit`, một transaction ngắn xác nhận đủ số dòng, áp dụng dữ liệu vào bảng nghiệp vụ và chuyển trạng thái batch sang `COMMITTED`.

Các truy vấn nghiệp vụ chỉ đọc dữ liệu đã commit. Như vậy, nếu client mất kết nối giữa chừng, các record staging chưa tạo thành một bản cập nhật tồn kho có thể nhìn thấy. Job dọn dẹp có thể xóa batch `RECEIVING` quá hạn theo chính sách lưu trữ.

Không nên giữ một transaction database mở trong toàn bộ thời gian client gửi stream dài. `@Transactional` đặt trên method gRPC thường không bao trùm các callback `onNext` và `onCompleted` theo cách người mới dễ hình dung: method trả về ngay sau khi tạo `StreamObserver`, còn dữ liệu đến sau đó. Hãy đặt transaction rõ ràng trong các thao tác staging và đặc biệt là thao tác commit cuối cùng.

### 4.2. Xử lý idempotency

Client tạo `batch_id` ổn định trước lần gửi đầu tiên và dùng lại ID đó khi retry. Processor cần quy định rõ các trường hợp:

- Batch đã `COMMITTED` với cùng tenant và batch ID: trả lại kết quả đã lưu nếu request được xác định là cùng nội dung.
- Batch đang `RECEIVING`: từ chối một upload đồng thời khác bằng `ALREADY_EXISTS` hoặc cơ chế lease có kiểm soát.
- Batch chưa hoàn tất đã hết lease: đánh dấu thất bại/expired và cho phép khởi tạo lại theo chính sách.
- Batch ID đã tồn tại nhưng nội dung khác: từ chối, không ghi đè batch cũ.

Để phân biệt cùng nội dung, có thể lưu checksum của nội dung chuẩn hóa hoặc manifest do client cung cấp và server xác minh. Không chỉ dựa vào tên file vì hai file khác nội dung có thể có cùng tên.

Trong state machine ở phần server, trường hợp replay có thể được biểu diễn bằng một `UploadSession` ở chế độ chỉ xác minh: `begin` nhận diện batch đã commit, `append` tính checksum/đối chiếu nội dung gửi lại mà không ghi thêm tồn kho, và `commit` trả kết quả đã lưu nếu nội dung trùng khớp. Nếu không triển khai chế độ này, hãy cung cấp RPC tra cứu trạng thái và để client tra cứu trước khi upload lại; không tuyên bố retry an toàn chỉ vì batch ID là duy nhất.

## 5. Xây dựng server nhận client stream

Server kế thừa generated `ImplBase` và trả về một `StreamObserver` để nhận từng frame. Ví dụ dưới đây tập trung vào state machine và các status quan trọng; `UploadSession`, logging và các exception giới hạn là kiểu của ứng dụng.

```java
@GrpcService
public final class BatchUploadGrpcService
        extends BatchUploadServiceGrpc.BatchUploadServiceImplBase {

    private final BatchUploadProcessor processor;

    public BatchUploadGrpcService(BatchUploadProcessor processor) {
        this.processor = processor;
    }

    @Override
    public StreamObserver<UploadFrame> uploadBatch(
            StreamObserver<UploadResult> responseObserver) {

        @SuppressWarnings("unchecked")
        ServerCallStreamObserver<UploadResult> serverCall =
                (ServerCallStreamObserver<UploadResult>) responseObserver;

        String tenantId = GrpcTenantContext.TENANT_ID.get();
        if (tenantId == null) {
            responseObserver.onError(Status.UNAUTHENTICATED
                    .withDescription("Missing authenticated tenant")
                    .asRuntimeException());
            return new StreamObserver<>() {
                @Override public void onNext(UploadFrame value) { }
                @Override public void onError(Throwable error) { }
                @Override public void onCompleted() { }
            };
        }

        return new BatchUploadObserver(serverCall, processor, tenantId);
    }
}
```

Observer điều phối frame và giới hạn số message được yêu cầu từ transport:

```java
final class BatchUploadObserver implements StreamObserver<UploadFrame> {

    private final ServerCallStreamObserver<UploadResult> response;
    private final BatchUploadProcessor processor;
    private final String tenantId;

    private UploadSession session;
    private long expectedRecords;
    private long nextSequence = 1;
    private boolean started;
    private boolean terminal;

    BatchUploadObserver(
            ServerCallStreamObserver<UploadResult> response,
            BatchUploadProcessor processor,
            String tenantId) {
        this.response = response;
        this.processor = processor;
        this.tenantId = tenantId;

        response.disableAutoRequest();
        response.setOnCancelHandler(this::cancel);
        response.request(1);
    }

    @Override
    public synchronized void onNext(UploadFrame frame) {
        if (terminal || response.isCancelled()) {
            cancel();
            return;
        }

        try {
            switch (frame.getFrameCase()) {
                case START -> acceptStart(frame.getStart());
                case RECORD -> acceptRecord(frame.getRecord());
                case FRAME_NOT_SET -> throw new IllegalArgumentException(
                        "Upload frame must contain start or record");
            }

            if (!terminal) {
                response.request(1);
            }
        } catch (UploadLimitExceededException ex) {
            fail(Status.RESOURCE_EXHAUSTED.withDescription(ex.getMessage()));
        } catch (IllegalArgumentException ex) {
            fail(Status.INVALID_ARGUMENT.withDescription(ex.getMessage()));
        } catch (BatchAlreadyExistsException ex) {
            fail(Status.ALREADY_EXISTS.withDescription(ex.getMessage()));
        } catch (Exception ex) {
            fail(Status.INTERNAL.withDescription("Batch upload failed"));
        }
    }

    private void acceptStart(BatchStart start) {
        if (started) {
            throw new IllegalArgumentException("BatchStart must be the first and only start frame");
        }
        if (start.getBatchId().isBlank() || start.getExpectedRecords() == 0) {
            throw new IllegalArgumentException("batch_id and expected_records are required");
        }

        expectedRecords = start.getExpectedRecords();
        session = processor.begin(tenantId, start);
        started = true;
    }

    private void acceptRecord(InventoryRecord record) {
        if (!started) {
            throw new IllegalArgumentException("BatchStart must precede records");
        }
        if (record.getSequence() != nextSequence) {
            throw new IllegalArgumentException("Record sequence is missing, duplicated or out of order");
        }
        if (record.getSku().isBlank() || record.getWarehouseCode().isBlank()
                || record.getQuantity() < 0) {
            throw new IllegalArgumentException("Invalid inventory record");
        }

        processor.append(session, record);
        nextSequence++;
    }

    @Override
    public synchronized void onCompleted() {
        if (terminal) {
            return;
        }
        if (!started || nextSequence - 1 != expectedRecords) {
            fail(Status.INVALID_ARGUMENT.withDescription("Uploaded record count does not match expected_records"));
            return;
        }

        try {
            UploadResult result = processor.commit(session);
            session = null;
            terminal = true;
            response.onNext(result);
            response.onCompleted();
        } catch (Exception ex) {
            fail(Status.INTERNAL.withDescription("Could not commit batch"));
        }
    }

    @Override
    public synchronized void onError(Throwable error) {
        abort();
        terminal = true;
    }

    private synchronized void cancel() {
        if (terminal) {
            return;
        }
        terminal = true;
        abort();
    }

    private void fail(Status status) {
        if (terminal) {
            return;
        }
        terminal = true;
        abort();
        response.onError(status.asRuntimeException());
    }

    private void abort() {
        if (session != null) {
            try {
                processor.abort(session);
            } catch (Exception cleanupError) {
                // Ghi log cleanupError; giữ nguyên status/cause của RPC ban đầu.
            } finally {
                session = null;
            }
        }
    }
}
```

Đoạn mã minh họa cần được hoàn thiện theo exception và logging của ứng dụng. Trong production, `abort()` phải an toàn khi gọi lặp và không được che mất lỗi gốc; nên bắt và ghi log riêng lỗi cleanup. Cần bổ sung giới hạn `expected_records`, tổng byte, độ dài từng field và thời lượng upload ở processor hoặc tầng kiểm soát request. `response.disableAutoRequest()` cùng `request(1)` thể hiện inbound flow control: server chỉ yêu cầu frame tiếp theo sau khi xử lý frame hiện tại.

Không được gọi `response.onNext()` sau `onError()` hoặc sau khi stream đã kết thúc. Cancellation phải dừng xử lý càng sớm càng tốt và abort staging. Nếu processor chuyển công việc sang executor khác, cần truyền cancellation rõ ràng và không giả định `Context.current()` tự tồn tại trong mọi tác vụ bất đồng bộ.

## 6. Xác thực metadata và tenant

Client gửi access token trong metadata `authorization`. Server interceptor xác thực token, lấy tenant từ principal đã xác minh và đặt tenant vào gRPC `Context`. Không tin một `tenant-id` do client tự gửi vì caller có thể sửa metadata để truy cập dữ liệu của tenant khác.

Ví dụ phần khai báo context và metadata key:

```java
public final class GrpcTenantContext {
    public static final Context.Key<String> TENANT_ID = Context.key("tenant-id");

    private GrpcTenantContext() {
    }
}

public final class AuthServerInterceptor implements ServerInterceptor {

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of("authorization", Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public AuthServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        try {
            AuthenticatedPrincipal principal =
                    tokenVerifier.verify(headers.get(AUTHORIZATION));
            Context context = Context.current().withValue(
                    GrpcTenantContext.TENANT_ID, principal.tenantId());
            return Contexts.interceptCall(context, call, headers, next);
        } catch (AuthenticationException ex) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Invalid credentials"), new Metadata());
            return new ServerCall.Listener<>() { };
        }
    }
}
```

`TokenVerifier` và `AuthenticatedPrincipal` là thành phần của ứng dụng. Đăng ký interceptor bằng cơ chế của Spring gRPC starter. Không ghi access token vào log. Nếu cần correlation ID, dùng metadata riêng, kiểm tra độ dài và chuẩn hóa giá trị trước khi đưa vào log hoặc trace.

Ở môi trường triển khai, bật TLS và xác minh certificate ở cả hai phía theo mô hình bảo mật đã chọn. Chỉ dùng plaintext trong môi trường local được cô lập. TLS bảo vệ đường truyền; interceptor vẫn phải xác thực và phân quyền caller.

## 7. Xây dựng client đọc CSV và gửi một stream

Client dùng generated asynchronous stub vì client-streaming RPC nhận kết quả bất đồng bộ. Ví dụ dưới đây minh họa luồng gửi cơ bản; hàm `parseCsvRecord` cần dùng CSV parser hỗ trợ quoting và escape thay vì tách chuỗi bằng dấu phẩy thủ công.

`expectedRecords` phải được xác định trước khi gửi frame đầu tiên, chẳng hạn đọc manifest do hệ thống tạo cùng file hoặc thực hiện một lượt đếm CSV bằng parser. Nếu cần đọc file hai lượt, kiểm tra file không bị thay đổi giữa lúc đếm và lúc upload; có thể lưu kích thước, modification time hoặc checksum để phát hiện thay đổi.

```java
// Đặt đoạn mã trong một phương thức có khai báo throws Exception.
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .useTransportSecurity()
        .build();

CountDownLatch completed = new CountDownLatch(1);
AtomicReference<UploadResult> resultRef = new AtomicReference<>();
AtomicReference<Throwable> errorRef = new AtomicReference<>();

try {
    BatchUploadServiceGrpc.BatchUploadServiceStub stub =
            BatchUploadServiceGrpc.newStub(channel);

    Metadata headers = new Metadata();
    Metadata.Key<String> authorization = Metadata.Key.of(
            "authorization", Metadata.ASCII_STRING_MARSHALLER);
    headers.put(authorization, "Bearer " + accessToken);
    stub = stub.withInterceptors(
            MetadataUtils.newAttachHeadersInterceptor(headers));

    StreamObserver<UploadResult> responseObserver = new StreamObserver<>() {
        @Override
        public void onNext(UploadResult result) {
            resultRef.set(result);
        }

        @Override
        public void onError(Throwable error) {
            errorRef.set(error);
            completed.countDown();
        }

        @Override
        public void onCompleted() {
            completed.countDown();
        }
    };

    StreamObserver<UploadFrame> requestObserver = stub
            .withDeadlineAfter(20, TimeUnit.MINUTES)
            .uploadBatch(responseObserver);

    requestObserver.onNext(UploadFrame.newBuilder()
            .setStart(BatchStart.newBuilder()
                    .setBatchId(batchId)
                    .setSource("inventory-csv")
                    .setExpectedRecords(expectedRecords))
            .build());

    long sequence = 1;
    try (BufferedReader reader = Files.newBufferedReader(csvPath)) {
        String line = reader.readLine(); // Bỏ qua header.
        while ((line = reader.readLine()) != null) {
            CsvInventoryRow row = parseCsvRecord(line);
            InventoryRecord record = InventoryRecord.newBuilder()
                    .setSequence(sequence++)
                    .setSku(row.sku())
                    .setWarehouseCode(row.warehouseCode())
                    .setQuantity(row.quantity())
                    .build();

            requestObserver.onNext(UploadFrame.newBuilder()
                    .setRecord(record)
                    .build());
        }
    } catch (Exception ex) {
        requestObserver.onError(ex);
        throw ex;
    }

    requestObserver.onCompleted();

    if (!completed.await(21, TimeUnit.MINUTES)) {
        throw new TimeoutException("Timed out waiting for batch result");
    }
    if (errorRef.get() != null) {
        throw new RuntimeException("Batch upload failed", errorRef.get());
    }
    UploadResult result = Objects.requireNonNull(resultRef.get());
    if (result.getState() != UploadState.UPLOAD_STATE_COMMITTED) {
        throw new IllegalStateException("Server did not commit the batch");
    }
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

Đây là ví dụ luồng cơ bản cho file có kích thước vừa phải. Với file lớn, không nên đọc toàn bộ file thành `List` trước khi gửi. Đồng thời, vòng lặp `onNext` đơn giản có thể đẩy dữ liệu vào buffer nhanh hơn tốc độ transport. Hãy nâng cấp client để dùng `ClientResponseObserver` và `ClientCallStreamObserver.isReady()`/`setOnReadyHandler()`: chỉ đọc và gửi thêm record khi channel sẵn sàng, dùng một producer duy nhất và một buffer có giới hạn. Logic producer có dạng: đăng ký `setOnReadyHandler(this::pump)`, trong `pump()` gửi record tiếp theo khi `call.isReady()` còn đúng, và chỉ gọi `call.onCompleted()` khi iterator đã hết. Nếu người dùng hủy upload hoặc deadline hết, hủy call và giữ nguyên `batch_id` để tra cứu hoặc retry theo chính sách.

Không retry mù một client-streaming RPC. Server có thể đã commit nhưng response bị mất trên đường về. Dùng `batch_id` idempotent và API tra cứu trạng thái để xác định kết quả trước khi gửi lại. Deadline phải đủ cho kích thước batch và tốc độ mạng dự kiến, đồng thời server vẫn cần giới hạn thời gian tối đa để tránh stream chiếm tài nguyên vô hạn.

## 8. Quy ước status và lỗi

Chọn status ổn định để client có thể xử lý nhất quán:

| Status | Trường hợp sử dụng | Hành vi client gợi ý |
|---|---|---|
| `INVALID_ARGUMENT` | Thiếu frame bắt đầu, sequence sai, record không hợp lệ hoặc số lượng không khớp. | Sửa file đầu vào; không retry nguyên trạng. |
| `UNAUTHENTICATED` | Token thiếu, hết hạn hoặc không hợp lệ. | Làm mới thông tin xác thực rồi quyết định gửi lại bằng cùng batch ID. |
| `PERMISSION_DENIED` | Caller không được phép upload cho tenant hoặc nguồn dữ liệu đó. | Dừng và yêu cầu quyền phù hợp. |
| `RESOURCE_EXHAUSTED` | Vượt số record, dung lượng, quota hoặc số upload đồng thời. | Giảm batch hoặc chờ theo chính sách quota. |
| `ALREADY_EXISTS` | Batch ID đang được xử lý hoặc xung đột với batch khác. | Tra cứu trạng thái batch; không tạo ID mới một cách tự động. |
| `DEADLINE_EXCEEDED` | Upload không hoàn tất trong deadline. | Tra cứu batch trước khi retry vì server có thể đã commit. |
| `CANCELLED` | Client hủy hoặc kết nối bị hủy. | Xác định batch đã commit hay chưa trước khi gửi lại. |
| `UNAVAILABLE` | Lỗi hạ tầng tạm thời hoặc server không sẵn sàng. | Retry có backoff sau khi kiểm tra idempotency và trạng thái batch. |
| `INTERNAL` | Lỗi không dự kiến ở server. | Ghi nhận mã tương quan, không lặp retry vô hạn. |

Không trả stack trace hoặc thông tin database trong status description. Ghi exception đầy đủ ở server với correlation ID; phía client chỉ nhận thông tin đủ để xử lý và hỗ trợ vận hành.

## 9. Kiểm thử contract và tích hợp

### 9.1. Kiểm thử bằng in-process server

Dùng generated stub và gRPC in-process transport để kiểm tra contract nhanh mà không mở socket. Có thể mock repository hoặc processor phụ thuộc, nhưng giữ service implementation thật. Kiểm tra ít nhất:

- Frame `BatchStart` đứng đầu và chỉ xuất hiện một lần.
- Record có sequence liên tục từ 1.
- `expected_records` khớp số record thực nhận.
- Kết quả cuối cùng chứa đúng `batch_id`, số lượng và trạng thái `COMMITTED`.
- Frame không hợp lệ trả `INVALID_ARGUMENT` và gọi abort.
- Vượt giới hạn trả `RESOURCE_EXHAUSTED`.
- Client cancellation gọi abort và không công bố batch.

### 9.2. Kiểm thử Spring integration

Khởi tạo Spring application context và gRPC server trên cổng kiểm thử. Dùng generated client kết nối vào server thật để xác nhận service bean được đăng ký, interceptor chạy, metadata được đọc, tenant được lấy từ principal và cấu hình lifecycle hoạt động. Nếu starter hỗ trợ cổng động, dùng cơ chế đó thay vì hard-code cổng có thể xung đột.

### 9.3. Kiểm thử transaction và idempotency

Kiểm tra rằng các record staging không xuất hiện trong bảng tồn kho trước commit. Khi record cuối sai hoặc commit thất bại, không có phần dữ liệu nào được công bố. Gửi lại cùng batch ID sau một lần commit thành công phải trả kết quả đã lưu mà không nhân đôi tồn kho. Hai upload đồng thời cùng tenant và batch ID phải có kết quả xác định.

### 9.4. Kiểm thử giới hạn và transport

- Upload đúng giới hạn và vượt số record tối đa.
- Record có field quá dài hoặc tổng byte vượt quota.
- Upload kéo dài đến deadline.
- Client ngắt kết nối giữa stream.
- Nhiều client upload đồng thời để xác nhận quota và backpressure.
- Token không hợp lệ, token hợp lệ nhưng sai tenant và certificate TLS không được tin cậy.
- File CSV có dấu phẩy trong trường được quote, dòng rỗng, encoding không hợp lệ và giá trị số sai.

Không chỉ kiểm tra status. Hãy xác nhận session được abort, staging được dọn theo chính sách và dữ liệu nghiệp vụ không bị cập nhật một phần.

## 10. Quan sát và vận hành

Ghi nhận metric theo method và status, ví dụ:

- `grpc_server_handled_total` theo method và status.
- Số upload đang hoạt động.
- Số batch thành công/thất bại và số record đã nhận.
- Thời gian upload, thời gian commit và kích thước batch.
- Số cancellation, deadline và lần vượt quota.
- Số batch staging quá hạn cần cleanup.

Không dùng `batch_id`, access token, SKU hoặc tenant ID làm metric label có cardinality cao. Có thể ghi batch ID vào structured log hoặc trace khi chính sách dữ liệu cho phép. Dùng correlation ID để ghép log client và server.

Đặt cảnh báo khi tỷ lệ `RESOURCE_EXHAUSTED`, `DEADLINE_EXCEEDED`, `UNAVAILABLE` hoặc số batch staging quá hạn tăng bất thường. Theo dõi thời gian commit riêng với thời gian truyền dữ liệu để biết nút thắt nằm ở network, parse/validation hay database.

## 11. Trình tự thực hiện dự án

1. Tạo `.proto`, cấu hình code generation và xác nhận generated service/stub được tạo đúng package.
2. Tạo `BatchUploadProcessor` cùng cơ chế staging, commit, abort và idempotency.
3. Viết server implementation nhận frame theo state machine; kiểm tra start, sequence, số lượng và giới hạn.
4. Đăng ký auth interceptor; xác thực metadata và đưa tenant đã xác minh vào gRPC context.
5. Viết client đọc CSV theo dòng, tạo batch ID, gửi start frame rồi gửi từng record và chờ kết quả.
6. Bổ sung deadline, cancellation, inbound/outbound flow control và giới hạn tài nguyên.
7. Viết contract test, Spring integration test, transaction test và transport/TLS test.
8. Bổ sung metric, structured log, cleanup job và tài liệu chạy thử.

## 12. Tiêu chí nghiệm thu

- [ ] Client gửi nhiều record trong đúng một client-streaming RPC và nhận một response cuối.
- [ ] Server từ chối frame sai thứ tự, sequence sai và số lượng record không khớp.
- [ ] Batch chỉ được công bố sau khi toàn bộ stream hợp lệ và transaction commit thành công.
- [ ] Client cancellation, lỗi validation và lỗi commit đều abort staging an toàn.
- [ ] Metadata được xác thực; tenant được lấy từ principal đã xác minh.
- [ ] Có deadline, giới hạn số record/byte/thời gian và cơ chế backpressure hai phía.
- [ ] Retry với cùng batch ID không tạo dữ liệu tồn kho trùng lặp.
- [ ] Client xử lý status theo quy ước và không retry mù các lỗi không an toàn.
- [ ] Integration test chạy qua Spring gRPC server thật; TLS được kiểm tra khi bật transport bảo mật.
- [ ] Metric và log cho phép theo dõi số batch, số record, thời gian xử lý và nguyên nhân thất bại.

Khi hoàn thành, bạn có một luồng upload batch có kiểm soát từ file CSV đến dữ liệu nghiệp vụ. Client streaming giảm overhead của việc gọi RPC cho từng record; staging, idempotency, deadline, flow control và kiểm thử tích hợp giúp luồng upload có thể vận hành an toàn khi dữ liệu lớn, kết nối gián đoạn hoặc server gặp lỗi.
