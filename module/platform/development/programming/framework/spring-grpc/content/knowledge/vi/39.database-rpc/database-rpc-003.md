# Không giữ transaction quá lâu khi stream

## 1. Vì sao transaction dài nguy hiểm trong streaming RPC?

Trong **SPRING_GRPC**, một streaming RPC có thể trao đổi message trong nhiều giây hoặc nhiều phút. Client có thể gửi chunk chậm, server có thể bị backpressure khi client đọc response chậm, và stream có thể bị hủy hoặc hết deadline bất cứ lúc nào.

Database transaction có mục đích bảo vệ một đơn vị đọc/ghi hữu hạn. Nếu mở transaction khi nhận message đầu tiên rồi giữ đến khi stream kết thúc, hệ thống phải giữ connection và có thể giữ lock trong suốt thời gian truyền dữ liệu. Một stream chậm có thể chiếm connection pool, làm request khác phải chờ; lock lâu làm tăng lock contention, deadlock và transaction timeout. Snapshot/MVCC lâu cũng có thể giữ lại phiên bản row cũ, làm tăng áp lực dọn dẹp dữ liệu trên một số database.

Nguyên tắc thiết kế là **không gắn vòng đời transaction với vòng đời network stream**. Hãy mở transaction sát thời điểm thực hiện thao tác database, commit sớm sau khi đơn vị công việc hoàn tất, rồi mới tiếp tục gửi/nhận dữ liệu qua mạng.

Bài tập trung vào cách giới hạn thời lượng transaction trong server streaming, client streaming và bidirectional streaming; cách dùng page, batch có giới hạn và staging; cùng các biện pháp kiểm soát connection, lock, timeout, cancellation và retry.

## 2. Transaction scope phải ngắn hơn stream

Một stream không nhất thiết tương ứng với một transaction. Hãy chọn ranh giới commit theo đơn vị nghiệp vụ:

| Mô hình | Transaction mở khi nào? | Transaction kết thúc khi nào? | Phù hợp |
| --- | --- | --- | --- |
| Per-message | Khi xử lý một command/chunk | Ngay sau khi command/chunk commit | Event hoặc command độc lập |
| Per-batch | Khi một batch hữu hạn đã sẵn sàng | Sau khi ghi xong batch | Import/ingest cần throughput |
| Staging/finalize | Transaction ngắn để lưu từng chunk vào staging; transaction khác để finalize | Sau mỗi chunk hoặc sau bước finalize | Upload cần công bố nguyên tử |
| Read page | Khi truy vấn một page | Ngay khi page DTO đã được materialize | Server streaming dữ liệu lớn |

Tránh mô hình mở transaction rồi chờ message tiếp theo. Trong thời gian chờ, không có database work nhưng connection và transaction vẫn có thể bị giữ.

Trước khi chọn mô hình, xác định điều gì được phép xảy ra nếu stream ngắt giữa chừng. Nếu các message trước có thể giữ hiệu lực, per-message hoặc per-batch thường phù hợp. Nếu không được công bố bất kỳ phần dữ liệu nào trước khi toàn bộ upload hợp lệ, dùng staging/finalize thay vì giữ một transaction xuyên suốt stream.

## 3. Vì sao @Transactional trên method gRPC không bảo vệ callback?

Với client streaming và bidirectional streaming, method gRPC thường trả về một StreamObserver để runtime gọi callback khi message đến:

```java
@Override
public StreamObserver<UploadChunk> upload(
        StreamObserver<UploadResult> responseObserver) {
    return new StreamObserver<>() {
        @Override
        public void onNext(UploadChunk chunk) {
            // Được gọi sau khi upload() đã trả về.
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

Nếu đặt @Transactional trên upload(), Spring proxy chỉ bao quanh thời gian gọi upload() để tạo và trả về observer. Transaction kết thúc khi method trả về; các callback onNext/onCompleted đến sau đó không nằm trong transaction ban đầu.

Cách phù hợp là để callback gọi một Spring application-service bean có method @Transactional. Mỗi lần gọi qua proxy mở transaction, xử lý database và commit/rollback trước khi trả quyền điều khiển về callback.

```java
@Service
@RequiredArgsConstructor
public class ChunkWriter {
    private final ChunkRepository repository;

    @Transactional
    public void save(ChunkCommand command) {
        repository.insert(command);
    }
}
```

Không gọi method transactional bằng self-invocation trong cùng object nếu đang dựa vào Spring proxy mode; lời gọi nội bộ có thể bỏ qua transaction interceptor. Đặt transaction boundary ở bean riêng và inject qua constructor.

## 4. Server streaming: đọc theo page rồi đóng transaction

Một lỗi thường gặp là mở transaction, lấy database cursor/Stream rồi gọi observer.onNext() cho từng row. Nếu client đọc chậm, transaction và connection có thể bị giữ suốt thời gian truyền.

Với dữ liệu lớn, dùng keyset pagination: mỗi lần chỉ đọc một page trong transaction ngắn, materialize thành DTO, đóng transaction rồi mới gửi page qua gRPC.

```java
@Service
@RequiredArgsConstructor
public class ExportQueryService {
    private final TransactionRepository repository;

    @Transactional(readOnly = true)
    public List<ExportRow> loadPage(
            String accountId, long afterId, int pageSize) {
        return repository.findNextPage(accountId, afterId, pageSize);
    }
}
```

Adapter điều phối page:

```java
long cursor = 0;
while (true) {
    List<ExportRow> page =
        exportQueryService.loadPage(accountId, cursor, PAGE_SIZE);

    if (page.isEmpty()) {
        break;
    }

    for (ExportRow row : page) {
        observer.onNext(toProto(row));
    }

    cursor = page.get(page.size() - 1).id();
}
observer.onCompleted();
```

Khi loadPage() trả về, transaction đọc đã kết thúc; observer gửi dữ liệu mà không giữ connection database. Trong code thực tế, cần xử lý cancellation, lỗi giữa page và trạng thái terminal của observer.

Pagination nhiều transaction không tự bảo đảm một snapshot nhất quán. Nếu dữ liệu thay đổi trong lúc export, chọn high-watermark, version/as-of timestamp, snapshot export hoặc isolation phù hợp. Không mở một transaction dài chỉ để có snapshot mà chưa đánh giá chi phí connection, MVCC và lock.

## 5. Client streaming: không mở transaction khi chờ chunk

Client streaming nhận nhiều request message. Không nên bắt đầu transaction ở callback đầu tiên rồi giữ nó mở trong lúc chờ client gửi chunk tiếp theo.

Có ba cách phổ biến:

- **Per-chunk:** mỗi chunk được kiểm tra và lưu trong một transaction ngắn. Chunk đã commit vẫn tồn tại nếu stream dừng ở chunk sau.
- **Bounded batch:** gom số lượng/kích thước chunk giới hạn trong bộ nhớ hoặc staging; chỉ mở transaction khi batch đã sẵn sàng ghi. Sau commit mới xác nhận batch.
- **Staging/finalize:** lưu từng chunk vào bảng tạm bằng transaction ngắn; khi client hoàn tất, một transaction finalize kiểm tra và công bố dữ liệu chính.

Với batch, giới hạn cả số message và tổng byte. Nếu batch quá lớn, transaction ghi lâu và bộ nhớ tăng; nếu batch quá nhỏ, overhead commit tăng. Chọn ngưỡng dựa trên throughput, lock time và khả năng retry.

Không gom vô hạn message trong RAM để tránh transaction dài. Với upload lớn, staging bền vững thường an toàn hơn.

## 6. Staging/finalize thay cho một transaction xuyên suốt upload

Nếu yêu cầu nghiệp vụ là “toàn bộ upload hoặc không có dữ liệu nào được công bố”, dùng upload session:

1. Tạo uploadId và lưu trạng thái OPEN.
2. Mỗi chunk có uploadId, sequence, checksum và payload.
3. Lưu chunk vào staging bằng transaction ngắn.
4. Khi client hoàn tất, kiểm tra đủ sequence, checksum và validation.
5. Trong một transaction ngắn, áp dụng dữ liệu staging vào bảng nghiệp vụ và chuyển session sang COMPLETED.
6. Worker dọn session hết hạn hoặc staging không còn được dùng.

```java
@Service
@RequiredArgsConstructor
public class UploadFinalizeService {
    private final UploadSessionRepository sessions;
    private final StagingRepository staging;
    private final InventoryRepository inventory;

    @Transactional
    public UploadResult finalizeUpload(String uploadId) {
        UploadSession session = sessions.lockById(uploadId)
            .orElseThrow(UploadNotFoundException::new);

        if (session.isCompleted()) {
            return session.previousResult();
        }

        validateAllChunks(session, staging);
        applyToInventory(session, staging, inventory);
        session.markCompleted();

        return session.toResult();
    }
}
```

Việc khóa session, áp dụng dữ liệu và đánh dấu COMPLETED cần nằm trong cùng transaction. Unique constraint theo (upload_id, sequence) ngăn lưu chunk trùng; locking hoặc optimistic version ngăn hai finalize đồng thời áp dụng cùng upload hai lần.

Staging có thể còn dữ liệu sau khi finalize thất bại, nhưng dữ liệu nghiệp vụ chính chưa bị công bố một phần. Client có thể retry finalize bằng cùng uploadId nếu thao tác được thiết kế idempotent.

## 7. Bidirectional streaming: transaction theo command

Trong bidirectional streaming, mỗi request thường là một command có thể xử lý độc lập. Callback không nên mở transaction rồi giữ nó qua thời gian chờ command tiếp theo.

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

                // apply() trả về sau khi transaction commit.
                responseObserver.onNext(toReply(result));
            } catch (RuntimeException ex) {
                responseObserver.onError(toStatus(ex));
            }
        }

        @Override
        public void onError(Throwable error) {
            // Các command đã commit vẫn giữ hiệu lực.
        }

        @Override
        public void onCompleted() {
            responseObserver.onCompleted();
        }
    };
}
```

deviceCommandService.apply() là method transactional trên Spring bean khác. Transaction chỉ tồn tại trong lúc xử lý command, không kéo dài giữa hai lần onNext.

Nếu offload callback sang executor, dùng queue có giới hạn và giữ thứ tự theo stream/aggregate khi nghiệp vụ yêu cầu. Transaction imperative của Spring thường gắn với thread; hãy gọi bean transactional bên trong worker thread. Không giữ transaction ở thread callback rồi chờ future hoàn tất.

## 8. Giới hạn connection, lock và thời gian transaction

Transaction ngắn làm giảm thời gian chiếm connection và lock, nhưng vẫn cần giới hạn rõ ràng:

- **Transaction timeout:** đặt giới hạn theo loại use case; không để một transaction ghi batch treo vô hạn.
- **Query/statement timeout:** ngăn câu SQL hoặc chờ lock kéo dài vượt ngân sách.
- **Pool sizing:** theo dõi active/idle/pending connection; không chữa pool starvation bằng cách chỉ tăng pool size nếu nguyên nhân là transaction dài.
- **Batch size:** giới hạn số row và byte xử lý trong một transaction.
- **Lock scope:** khóa đúng row cần thiết, giữ lock trong thời gian ngắn và tránh gọi network khi đang giữ lock.
- **Read strategy:** dùng keyset pagination/index phù hợp để page không phải quét ngày càng nhiều row.
- **Isolation:** chọn mức isolation theo consistency cần thiết; isolation cao hơn có thể làm tăng lock/conflict.

Một transaction dài có thể giữ snapshot cũ hoặc làm chậm vacuum/cleanup tùy database. Theo dõi database-specific metrics thay vì chỉ nhìn thời gian RPC tổng thể.

## 9. Backpressure, deadline và cancellation

Backpressure điều tiết tốc độ producer/consumer của stream. Nó không nên khiến transaction database bị giữ mở trong lúc chờ observer sẵn sàng hoặc chờ client gửi thêm dữ liệu.

Với server streaming, đọc page, đóng transaction, rồi mới gửi page. Với client/bidi streaming, chỉ mở transaction khi đã có chunk/command hoặc batch sẵn sàng xử lý.

Deadline và cancellation cần được phối hợp:

- Đặt deadline RPC hợp lý.
- Đặt query timeout và transaction timeout nhỏ hơn hoặc phù hợp với ngân sách RPC.
- Khi client hủy, ngừng tạo công việc mới nếu có thể.
- Không bắt đầu transaction cho message đã biết là không còn cần xử lý.
- Dùng cancellation hook của server call để dừng producer/worker; cleanup bền vững vẫn cần TTL hoặc worker vì process có thể dừng đột ngột.
- Nếu transaction đã commit nhưng acknowledgment bị mất, retry phải được bảo vệ bằng idempotency key.

Cancellation không thể rollback transaction đã commit. Nó chỉ có thể ngăn công việc chưa commit tiếp tục hoặc yêu cầu transaction đang chạy dừng theo cơ chế hỗ trợ của driver/database.

## 10. Retry, idempotency và partial commit

Nếu mỗi message hoặc batch commit riêng, stream có semantics **partial commit**. Ví dụ, batch 1 và 2 đã commit; batch 3 lỗi; dữ liệu của hai batch trước vẫn tồn tại. Status lỗi cuối stream không có nghĩa mọi thao tác trước đó đã rollback.

Để client retry/resume an toàn:

- Mỗi command/chunk/batch có ID hoặc sequence ổn định.
- Lưu receipt/kết quả xử lý trong cùng transaction với thay đổi nghiệp vụ.
- Dùng unique constraint theo operation ID hoặc (stream_id, sequence).
- Cùng ID và cùng payload thì trả lại kết quả cũ.
- Cùng ID nhưng payload khác thì trả conflict.
- Cung cấp checkpoint để client biết sequence cuối đã commit.

Nếu một command cập nhật database rồi server mất kết nối trước khi gửi ack, client có thể gửi lại. Idempotency giúp lần gửi lại không lặp side effect.

Với upload atomic qua staging, chunk có thể được ghi bền vững nhưng chưa công bố; finalize là điểm commit nghiệp vụ. Hãy phân biệt rõ “chunk đã nhận”, “chunk đã lưu staging” và “upload đã hoàn tất”.

## 11. External side effects và transactional outbox

Không giữ transaction database mở để chờ broker, email provider hoặc RPC tới service khác. Những hệ thống đó không tự tham gia cùng transaction database.

Nếu command cần cập nhật database và phát event, ghi outbox record trong cùng transaction:

1. Cập nhật domain state.
2. Ghi outbox event với event ID/sequence.
3. Commit.
4. Worker publish event và đánh dấu đã gửi.
5. Consumer xử lý idempotent vì publish có thể lặp lại.

Outbox giúp transaction của từng command kết thúc nhanh mà vẫn lưu bền vững ý định phát event. Với workflow nhiều service cần bù trừ, dùng saga/compensation thay vì giữ một transaction xuyên suốt các RPC.

## 12. Đo thời lượng transaction và tìm stream gây giữ connection

Không chỉ đo tổng thời gian RPC. Một stream có thể kéo dài 10 phút nhưng mỗi transaction chỉ 20 ms; ngược lại, RPC 2 giây có thể giữ transaction 1,8 giây và chiếm connection phần lớn thời gian.

Theo dõi tối thiểu:

- Transaction duration p50/p95/p99 theo use case.
- Số transaction đang mở và transaction lâu nhất.
- Connection pool active, idle, pending/acquire wait.
- Lock wait, deadlock, statement timeout và rollback count.
- Batch size, page size và thời gian commit.
- Số chunk/message xử lý, retry, duplicate và resume.
- Stream duration, cancellation và thời gian chờ backpressure.
- Số upload staging OPEN quá hạn và finalize thất bại.

Dùng metric labels có cardinality giới hạn như RPC method, transaction operation và outcome. Không đưa stream ID, user ID hoặc sequence tùy ý vào label. Log correlation ID để điều tra từng phiên cụ thể.

Đặt ngưỡng cảnh báo cho transaction duration riêng với RPC duration. Nếu RPC dài nhưng transaction ngắn, điều tra network/backpressure; nếu transaction dài, xem query plan, lock và code đang giữ transaction qua I/O.

## 13. Kiểm thử để chứng minh transaction không bị giữ quá lâu

Kiểm thử qua gRPC server thật và database gần production. H2 có thể không tái hiện đúng locking, isolation, pool behavior hoặc statement timeout của database triển khai.

| Test | Điều cần xác nhận |
| --- | --- |
| Server stream, client đọc chậm | Transaction page kết thúc trước khi gửi page qua network |
| Export nhiều page | Không giữ một connection/cursor suốt toàn bộ stream |
| Client stream, gửi chunk cách quãng | Không có transaction mở trong thời gian chờ chunk tiếp theo |
| Bounded batch | Transaction chỉ bắt đầu khi batch sẵn sàng và có giới hạn |
| Upload staging | Chunk lưu staging bằng transaction ngắn; dữ liệu chính chỉ đổi khi finalize |
| Bidi stream nhàn rỗi | Không giữ transaction giữa các command |
| Cancellation/deadline | Không tạo transaction mới sau khi stream đã bị hủy; staging được dọn theo policy |
| Retry sau mất ack | Idempotency ngăn side effect lặp |
| Pool saturation | Stream chậm không chiếm hết connection pool |
| Concurrent finalize | Upload chỉ được công bố một lần |

Một test hữu ích là cố ý làm client đọc chậm hoặc tạm dừng gửi chunk, đồng thời quan sát transaction/connection từ database và pool metrics. Xác nhận thời gian stream tăng nhưng transaction duration vẫn nằm trong giới hạn của từng page/chunk/batch.

## 14. Checklist review

- Transaction scope được chọn theo message, batch, page hoặc finalize; không theo toàn bộ vòng đời stream.
- Không đặt @Transactional lên method chỉ tạo và trả StreamObserver rồi kỳ vọng callback dùng chung transaction.
- Callback gọi transactional application service qua Spring proxy.
- Server streaming materialize page/DTO và đóng transaction trước khi gửi qua network.
- Client streaming không giữ transaction khi chờ chunk tiếp theo.
- Batch có giới hạn số message, byte và thời gian xử lý.
- Upload cần atomicity dùng staging/finalize.
- Bidi command có ordering, sequence và concurrency policy.
- Connection, lock, query và transaction timeout được cấu hình.
- Backpressure không giữ transaction mở.
- Cancellation không bị nhầm với rollback transaction đã commit.
- Retry có idempotency key, receipt và checkpoint.
- External side effects dùng outbox hoặc saga.
- Metrics phân biệt RPC duration với transaction duration.
- Integration tests xác nhận pool, transaction lifetime, cancellation và retry.

Trong **SPRING_GRPC**, giữ transaction ngắn khi stream giúp connection pool phục vụ được nhiều RPC hơn, giảm lock contention và tránh để tốc độ mạng quyết định thời gian giữ tài nguyên database. Hãy đọc theo page, ghi theo message/batch có giới hạn hoặc dùng staging/finalize; chỉ mở transaction khi dữ liệu đã sẵn sàng xử lý và đóng nó trước khi chờ network. Đo transaction duration riêng với stream duration để phát hiện đúng nguyên nhân gây nghẽn.
