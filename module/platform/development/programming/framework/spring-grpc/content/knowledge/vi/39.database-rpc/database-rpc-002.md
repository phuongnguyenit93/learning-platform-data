# Transaction trong streaming RPC

## 1. Vì sao streaming RPC cần transaction boundary riêng?

Trong **SPRING_GRPC**, streaming RPC cho phép một lời gọi gRPC trao đổi nhiều message theo thời gian. Server streaming gửi nhiều response; client streaming nhận nhiều request; bidirectional streaming vừa nhận vừa gửi message. Một stream có thể kéo dài từ vài giây đến nhiều phút, chịu backpressure, cancellation, deadline và lỗi mạng giữa chừng.

Database transaction lại được thiết kế cho một đơn vị công việc hữu hạn: bắt đầu, đọc/ghi và commit hoặc rollback. Nếu giữ một transaction mở suốt vòng đời stream, connection và lock có thể bị giữ lâu, transaction timeout, deadlock và áp lực connection pool tăng. Nếu gắn @Transactional lên method gRPC tạo StreamObserver, transaction thường kết thúc khi method trả về observer; các callback onNext/onCompleted diễn ra sau đó và không tự nằm trong transaction ban đầu.

Vì vậy, cần chọn transaction scope theo semantics của stream. Phần lớn hệ thống dùng **transaction ngắn theo message hoặc theo batch**, commit trước khi gửi acknowledgment tương ứng. Nếu nghiệp vụ cần toàn bộ stream nguyên tử, hãy dùng staging và một bước finalize ngắn thay vì giữ transaction database mở trong lúc truyền dữ liệu.

Bài tập trung vào:

- Khác biệt transaction giữa server streaming, client streaming và bidirectional streaming.
- Vì sao không giữ transaction mở qua network hoặc callback.
- Transaction theo message, theo batch và staging/finalize.
- Thứ tự commit trước khi phát response/ack.
- Partial commit, retry, idempotency, checkpoint và cancellation.
- Tích hợp Spring transaction, outbox và kiểm thử streaming.

## 2. Ba kiểu streaming và hướng dữ liệu

| Kiểu RPC | Hướng dữ liệu | Ví dụ nghiệp vụ | Transaction thường phù hợp |
| --- | --- | --- | --- |
| Server streaming | Một request, nhiều response | Xuất lịch sử giao dịch, theo dõi trạng thái | Transaction đọc ngắn theo snapshot/page |
| Client streaming | Nhiều request, một response cuối | Upload dữ liệu, nhập lô bản ghi | Transaction theo chunk hoặc staging rồi finalize |
| Bidirectional streaming | Nhiều request và response hai chiều | Đồng bộ sự kiện, phiên điều khiển thiết bị | Transaction ngắn theo command/message |

Chọn transaction scope theo đơn vị nghiệp vụ, không theo số lượng callback. Một callback onNext không nhất thiết là một transaction nghiệp vụ độc lập; nhiều chunk có thể cùng tạo thành một upload, trong khi một stream bidi có thể chứa nhiều command độc lập.

Trước khi triển khai, trả lời ba câu hỏi:

1. Nếu stream bị ngắt ở message thứ N, các message trước có được phép giữ hiệu lực không?
2. Client có thể retry hoặc resume từ một sequence/cursor không?
3. Khi nào server được phép xác nhận một message đã được lưu bền vững?

Các câu trả lời quyết định có thể commit từng message, commit theo batch hay phải dùng staging.

## 3. Vì sao @Transactional trên method tạo stream không bao trùm callback?

Ví dụ client streaming trong gRPC Java:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {
    // Method này trả về observer ngay lập tức.
    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            // Callback được gọi sau khi method upload đã trả về.
        }

        @Override
        public void onError(Throwable error) {
        }

        @Override
        public void onCompleted() {
        }
    };
}
```

Nếu đặt @Transactional trên upload(), Spring proxy chỉ bao quanh thời gian gọi upload() để tạo và trả về StreamObserver. Transaction kết thúc trước khi gRPC runtime gọi onNext() hoặc onCompleted(). Annotation ở method ngoài không tự lan sang những callback được gọi sau đó.

Tương tự, nếu một server streaming method bắt đầu producer bất đồng bộ rồi trả về, transaction gắn với method có thể kết thúc trước khi producer truy vấn database hoặc gửi response.

Với Spring transaction manager kiểu imperative, transaction context thường gắn với thread hiện tại. Không nên giả định transaction tự truyền sang executor, callback hoặc thread khác.

Cách an toàn là gọi một Spring bean method có transaction từ từng callback hoặc từ một worker cụ thể. Lời gọi qua bean proxy mở và kết thúc transaction trong cùng execution; callback chỉ phát acknowledgment sau khi lời gọi transactional trả về thành công.

## 4. Server streaming: đọc dữ liệu trong transaction ngắn

Một server streaming RPC thường xuất nhiều bản ghi. Không nên giữ transaction và database cursor mở trong suốt thời gian gửi qua network, vì client có thể đọc chậm hoặc ngừng nhận dữ liệu.

Với tập dữ liệu vừa phải, có thể đọc một snapshot cần thiết trong application service rồi đóng transaction trước khi gửi:

```java
@Service
@RequiredArgsConstructor
public class ExportQueryService {
    private final TransactionRepository repository;

    @Transactional(readOnly = true)
    public List<TransactionRow> loadExport(String accountId) {
        return repository.findExportRows(accountId);
    }
}
```

Adapter nhận danh sách đã đọc xong rồi gửi từng response:

```java
@Override
public void export(
        ExportRequest request,
        StreamObserver<ExportRow> observer) {
    try {
        List<TransactionRow> rows =
            exportQueryService.loadExport(request.getAccountId());

        for (TransactionRow row : rows) {
            observer.onNext(toProto(row));
        }
        observer.onCompleted();
    } catch (RuntimeException ex) {
        observer.onError(toStatus(ex));
    }
}
```

Khi loadExport() trả về, transaction đọc đã kết thúc. Network backpressure không giữ database transaction hoặc connection mở.

Không nên tải hàng triệu bản ghi vào bộ nhớ chỉ để đóng transaction sớm. Với dữ liệu lớn, dùng keyset pagination hoặc cursor có thời hạn:

1. Transaction đọc một page theo khóa tăng dần.
2. Đóng transaction và trả page DTO.
3. Adapter gửi page qua stream.
4. Đọc page tiếp theo bằng transaction ngắn.
5. Dùng cursor/high-watermark để xác định ranh giới export.

Nếu dữ liệu thay đổi trong khi export, các page đọc ở transaction khác nhau có thể không tạo thành một snapshot nhất quán. Có thể cố định high-watermark, dùng version/as-of timestamp, tạo export snapshot/staging hoặc chọn isolation/snapshot strategy phù hợp với database. Không giả định pagination nhiều transaction tự có cùng snapshot.

## 5. Client streaming: chọn atomicity theo ý nghĩa upload

Client streaming thường nhận nhiều chunk rồi trả một kết quả tổng hợp. Có hai kiểu semantics phổ biến.

**Mỗi chunk độc lập:** chunk nào commit thành công thì tồn tại, stream lỗi ở chunk sau không rollback các chunk trước. Phù hợp telemetry, ingest event hoặc xử lý dữ liệu có thể resume.

**Toàn bộ upload nguyên tử:** không chunk nào được công bố cho nghiệp vụ cho tới khi toàn bộ upload hợp lệ. Không nên giữ một transaction mở suốt lúc client truyền file; dùng staging để lưu dữ liệu tạm, sau đó finalize.

Ví dụ interface callback chỉ điều phối từng chunk:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {

    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            try {
                uploadChunkService.storeChunk(toCommand(chunk));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
                // Đánh dấu stream đã thất bại; bỏ qua callback tiếp theo
                // theo cơ chế lifecycle của implementation.
            }
        }

        @Override
        public void onError(Throwable error) {
            uploadSessionService.markInterruptedIfNeeded();
        }

        @Override
        public void onCompleted() {
            try {
                UploadResult result = uploadFinalizeService.finalizeUpload();
                responseObserver.onNext(result);
                responseObserver.onCompleted();
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }
    };
}
```

Đây là cấu trúc minh họa; implementation thực tế cần bảo vệ trạng thái terminal để không gọi observer nhiều lần và phải gắn mọi callback với đúng upload session. Không dùng một session ID toàn cục hoặc mutable field chung trên singleton service.

Mỗi lần gọi uploadChunkService.storeChunk() có thể mở một transaction ngắn. finalizeUpload() chạy transaction riêng để xác minh dữ liệu và công bố upload.

## 6. Staging và finalize cho upload nguyên tử

Một thiết kế staging thường dùng upload ID và sequence number:

- Client bắt đầu upload và nhận uploadId.
- Mỗi chunk có uploadId, sequence, checksum và payload.
- Server lưu chunk vào bảng staging với unique constraint theo (upload_id, sequence).
- Khi client hoàn tất, server kiểm tra số chunk, sequence liên tục, checksum và quy tắc nghiệp vụ.
- Một transaction finalize tạo hoặc cập nhật dữ liệu chính và đánh dấu upload COMPLETED.
- Worker dọn staging hết hạn hoặc upload bị bỏ dở.

Transaction theo chunk:

```java
@Service
@RequiredArgsConstructor
public class UploadChunkService {
    private final UploadChunkRepository chunks;

    @Transactional
    public void storeChunk(ChunkCommand command) {
        chunks.insertIfAbsent(
            command.uploadId(),
            command.sequence(),
            command.checksum(),
            command.payload()
        );
    }
}
```

Transaction finalize:

```java
@Service
@RequiredArgsConstructor
public class UploadFinalizeService {
    private final UploadSessionRepository sessions;
    private final UploadChunkRepository chunks;
    private final InventoryRepository inventory;

    @Transactional
    public UploadResult finalizeUpload(String uploadId) {
        UploadSession session = sessions.lockById(uploadId)
            .orElseThrow(UploadNotFoundException::new);

        if (session.isCompleted()) {
            return session.previousResult();
        }

        validateCompleteSequence(session, chunks);
        applyStagedChanges(session, chunks, inventory);
        session.markCompleted();

        return session.toResult();
    }
}
```

Ví dụ giả định repository khóa session bằng row lock. Cần unique constraint và locking để hai callback finalize đồng thời không áp dụng dữ liệu hai lần. Việc chuyển staging thành dữ liệu chính và đánh dấu COMPLETED phải cùng transaction.

Staging cho phép lưu bền vững từng chunk nhưng chưa công bố dữ liệu nghiệp vụ. Nếu finalize rollback, dữ liệu chính không thay đổi và client có thể retry finalize bằng cùng uploadId.

## 7. Bidirectional streaming: transaction theo command/message

Bidirectional stream thường mang nhiều command độc lập trong cùng một kết nối. Mỗi command có thể cần cập nhật database và trả một acknowledgment hoặc event.

Một cách triển khai là xử lý từng command đồng bộ qua application service:

```java
@Override
public StreamObserver<DeviceCommand> control(
        StreamObserver<DeviceReply> responseObserver) {

    return new StreamObserver<>() {
        @Override
        public void onNext(DeviceCommand command) {
            try {
                DeviceResult result =
                    deviceCommandService.apply(toCommand(command));

                responseObserver.onNext(toReply(result));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }

        @Override
        public void onError(Throwable error) {
            // Ghi nhận stream bị hủy; không rollback command đã commit.
        }

        @Override
        public void onCompleted() {
            responseObserver.onCompleted();
        }
    };
}
```

DeviceCommandService.apply() là method Spring bean có @Transactional. Khi method trả về, transaction đã commit; adapter mới gửi reply. Nếu transaction thất bại, adapter gửi lỗi và không gửi acknowledgment thành công cho command đó.

Nếu callback được dispatch đồng thời, không mặc định các onNext() có thể cập nhật cùng aggregate an toàn. Cần tuần tự hóa command theo stream hoặc aggregate, dùng sequence/version check và database locking. Không để hai callback cùng sửa một trạng thái theo thứ tự không xác định.

Một gRPC stream có thể gửi nhiều response; mỗi response cần có correlation ID hoặc command sequence để client ghép acknowledgment với command tương ứng.

## 8. Partial commit và semantics khi stream thất bại

Nếu mỗi message dùng transaction riêng, stream không phải một transaction nguyên tử. Ví dụ 10 command đã được nhận:

- Command 1–6 commit thành công và đã có acknowledgment.
- Command 7 gặp lỗi constraint và rollback.
- Stream kết thúc với status lỗi.
- Command 1–6 vẫn đã commit; không thể rollback chúng chỉ bằng cách đóng stream.

Đây là semantics **partial commit**. API cần công bố rõ điều này để client không hiểu rằng lỗi cuối stream đồng nghĩa không có dữ liệu nào được lưu.

Với upload nguyên tử qua staging, các chunk có thể được lưu ở staging nhưng dữ liệu chính chỉ được cập nhật khi finalize. Nếu finalize thất bại, client có thể sửa hoặc gửi lại mà không phải đảo ngược từng thay đổi đã công bố.

Chọn semantics phù hợp:

| Nhu cầu | Mô hình |
| --- | --- |
| Mỗi event độc lập và có thể tiếp tục sau lỗi | Transaction theo message |
| Nhiều message tạo một batch nghiệp vụ | Transaction theo batch ngắn hoặc staging/finalize |
| Không được công bố phần dữ liệu chưa hoàn chỉnh | Staging, validate rồi finalize |
| Luồng điều khiển liên tục | Transaction theo command và sequence |

Không tuyên bố “atomic stream” nếu chỉ commit từng callback riêng lẻ.

## 9. Retry, idempotency và resume

gRPC không tự bảo đảm exactly-once processing. Client có thể không biết server đã commit hay chưa nếu kết nối bị ngắt ngay sau commit nhưng trước acknowledgment.

Với stream có side effect:

- Mỗi command/chunk cần một idempotency key hoặc định danh ổn định.
- Dùng unique constraint cho operation ID hoặc (stream/session ID, sequence).
- Lưu kết quả xử lý cùng transaction với thay đổi nghiệp vụ.
- Nếu nhận lại cùng key và cùng payload, trả kết quả cũ.
- Nếu cùng key nhưng payload khác, từ chối conflict.
- Hỗ trợ resume từ sequence/cursor đã commit thay vì gửi lại mù quáng toàn bộ stream.

Ví dụ bảng command receipt có unique key theo client ID và command ID. Khi command được xử lý, cập nhật domain state và lưu receipt trong cùng transaction. Retry sẽ đọc receipt đã tồn tại để trả lại acknowledgment mà không chạy side effect lần nữa.

Với chunk upload, checksum giúp phát hiện client gửi lại cùng sequence nhưng nội dung khác. Unique constraint bảo vệ cả khi hai request retry đến đồng thời.

## 10. Transaction và external side effects

Không gọi email provider, message broker hoặc RPC tới service khác bên trong transaction database rồi giả định tất cả có thể rollback cùng nhau.

Nếu một message đã commit trong database và cần phát event, ghi outbox record trong cùng transaction:

1. Xử lý command và cập nhật domain state.
2. Ghi outbox event với event ID/sequence.
3. Commit transaction.
4. Worker publish event và đánh dấu đã gửi.
5. Consumer xử lý idempotent vì publish có thể lặp lại.

Với stream dài, outbox tạo ranh giới rõ ràng giữa commit từng command và phát side effect bên ngoài. Nếu workflow nhiều service cần bù trừ, dùng saga/compensation và lưu trạng thái tiến trình thay vì giữ transaction xuyên các RPC.

## 11. Cancellation, deadline và thread lifecycle

Client có thể hủy stream hoặc deadline có thể hết ở bất kỳ thời điểm nào. Điều đó không tự động đảo ngược transaction đã commit.

Khi cancellation xảy ra:

- Dừng nhận hoặc xử lý message mới nếu lifecycle cho phép.
- Không phát thêm acknowledgment thành công cho công việc chưa commit.
- Cho transaction đang chạy kết thúc hoặc rollback theo cơ chế database/runtime.
- Đánh dấu upload/session bị gián đoạn nếu cần resume.
- Dọn staging bằng TTL/worker; không phụ thuộc duy nhất vào callback onError vì process có thể bị dừng đột ngột.
- Giữ idempotency để client retry an toàn sau khi không rõ kết quả.

Đặt deadline và query/transaction timeout phù hợp. Không giữ transaction mở khi chờ client gửi chunk tiếp theo hoặc chờ network backpressure.

Với Spring imperative transaction, context thường gắn với thread. Nếu callback đẩy công việc sang executor, hãy gọi transactional bean bên trong worker thread để mở transaction tại đó. Nếu dùng reactive stack với R2DBC, transaction context được truyền trong Reactor Context; cần giữ công việc trong reactive pipeline thay vì trộn tùy tiện với callback imperative StreamObserver.

## 12. Ánh xạ lỗi và trạng thái stream

Một stream chỉ có một terminal outcome: hoàn tất hoặc lỗi. Sau khi gọi onError(), không tiếp tục gọi onNext() hoặc onCompleted(). Sau khi gọi onCompleted(), không phát terminal signal khác.

Một số status có thể dùng:

| Tình huống | gRPC status |
| --- | --- |
| Chunk/request sai cấu trúc | INVALID_ARGUMENT |
| Upload/session không tồn tại | NOT_FOUND |
| Sequence hoặc trạng thái session không hợp lệ | FAILED_PRECONDITION |
| Sequence trùng nhưng payload khác | ALREADY_EXISTS hoặc ABORTED theo contract |
| Conflict optimistic locking | ABORTED |
| Hết deadline | DEADLINE_EXCEEDED |
| Lỗi nội bộ/database không dự kiến | INTERNAL |

Không đưa SQL, stack trace hoặc dữ liệu nhạy cảm vào status description. Ghi log nội bộ kèm stream ID, command ID, sequence và correlation ID có kiểm soát.

Với partial commit, status cuối stream không mô tả đầy đủ các command đã commit trước đó. API nên có receipt/checkpoint hoặc query trạng thái để client biết đã xử lý đến đâu.

## 13. Kiểm thử transaction trong streaming RPC

Cần kiểm thử qua gRPC server thật và database có semantics gần production. H2 có thể không tái hiện đúng locking, isolation, constraint hoặc deferred commit behavior của database đang chạy.

| Test | Điều cần xác nhận |
| --- | --- |
| Server streaming | Transaction đọc kết thúc trước khi response stream được gửi |
| Client streaming chunk commit | Chunk đã commit vẫn tồn tại khi chunk sau thất bại |
| Upload staging | Chunk tạm không xuất hiện trong dữ liệu chính trước finalize |
| Finalize thành công | Toàn bộ dữ liệu được công bố và session COMPLETED cùng transaction |
| Finalize rollback | Không có thay đổi nghiệp vụ một phần |
| Duplicate chunk/command | Retry cùng ID không tạo side effect lặp |
| Sequence conflict | Cùng ID nhưng payload khác bị từ chối |
| Bidi concurrency | Command cùng aggregate được tuần tự hóa hoặc khóa đúng |
| Cancellation | Không commit công việc chưa hoàn tất; session có thể resume/expire |
| Observer lifecycle | Không phát message sau terminal signal |
| Outbox | Domain update và outbox record cùng commit/rollback |

Đối với client streaming, test gửi một số chunk hợp lệ rồi cố tình làm chunk tiếp theo lỗi. Xác nhận kết quả đúng theo semantics đã công bố: per-chunk mode giữ chunk trước; staging mode không công bố dữ liệu chính trước finalize.

Đối với server streaming, test client đọc chậm và hủy giữa chừng; quan sát connection/transaction để xác nhận database transaction không bị giữ suốt thời gian network stream.

## 14. Checklist thiết kế transaction cho streaming RPC

- Đã xác định RPC là server, client hay bidirectional streaming.
- Đã định nghĩa atomicity theo message, batch hay toàn bộ upload.
- Không giữ transaction database mở qua network, backpressure hoặc toàn bộ vòng đời stream.
- Không dựa vào @Transactional trên method chỉ tạo và trả StreamObserver.
- Mỗi callback gọi transactional application service qua Spring bean proxy.
- Chỉ phát acknowledgment sau khi transaction tương ứng commit.
- Server streaming dùng page/snapshot strategy phù hợp với consistency và memory.
- Client streaming dùng staging/finalize nếu cần atomic upload.
- Bidi stream xử lý ordering, sequence và concurrency rõ ràng.
- Partial commit được công bố và có checkpoint/resume.
- Retry có idempotency key và database uniqueness.
- External side effects dùng outbox hoặc saga/compensation.
- Deadline/cancellation không bị nhầm với rollback transaction đã commit.
- Có integration tests cho transaction, observer lifecycle, retry và cancellation.

Trong **SPRING_GRPC**, streaming RPC không nên được xem như một transaction database kéo dài từ message đầu tới message cuối. Hãy chọn transaction ngắn theo command/chunk hoặc staging/finalize cho upload nguyên tử, rồi chỉ gửi acknowledgment sau commit. Thiết kế rõ partial commit, idempotency, checkpoint và cancellation giúp stream có thể retry hoặc resume mà không tạo dữ liệu trùng hay trạng thái nghiệp vụ dở dang.
