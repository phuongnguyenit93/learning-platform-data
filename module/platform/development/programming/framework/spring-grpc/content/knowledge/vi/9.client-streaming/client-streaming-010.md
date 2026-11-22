# Idempotency khi client gửi lại batch

**Chương:** Client streaming  
**Phạm vi:** Spring gRPC (SPRING_GRPC), hợp đồng Protocol Buffers, mã Java được sinh và RPC nhận nhiều request, trả một response.

## 1. Vấn đề: client không biết lần gửi trước đã thành công chưa

Client gửi một batch gồm 500 bản ghi. Server nhận đủ, ghi dữ liệu và commit transaction. Nhưng ngay sau commit, kết nối bị đứt trước khi UploadReceipt tới client. Client chỉ thấy UNAVAILABLE hoặc DEADLINE_EXCEEDED; nó không biết server đã lưu hay chưa.

Nếu client gửi lại toàn bộ batch với một định danh mới, server có thể ghi trùng 500 bản ghi. Nếu client không gửi lại, dữ liệu có thể bị thiếu trong trường hợp lần đầu chưa commit. Đây là **kết quả không chắc chắn** thường gặp khi RPC có tác dụng phụ.

**Idempotency** giúp một thao tác có thể được gửi lại nhiều lần mà không tạo thêm tác dụng phụ ngoài kết quả của lần xử lý logic đầu tiên. Với client streaming, cần định danh batch ổn định, nhận diện nội dung, chống trùng từng phần tử và lưu biên nhận cuối để trả lại khi client retry.

Luồng điển hình:

1. Client gửi batch B42.
2. Server lưu dữ liệu và commit B42.
3. Response bị mất trước khi client nhận được receipt.
4. Client retry cùng B42 và cùng nội dung.
5. Server tìm thấy B42 đã COMMITTED và trả lại receipt đã lưu, không commit lần nữa.

Kết quả mong muốn: server không ghi dữ liệu lần thứ hai; client nhận cùng biên nhận đã được lưu. **Retry cùng một batch phải giữ nguyên idempotency key và nội dung batch.**

## 2. Một batch_id ổn định là cần thiết, nhưng chưa đủ

Client tạo batch_id **một lần trước lần gửi đầu tiên** và lưu lại cho đến khi biết kết quả cuối. Khi retry do timeout hoặc mất mạng, client dùng lại chính ID đó.

Chỉ có batch_id chưa đủ để phân biệt:

- Retry đúng cùng batch và cùng payload.
- Client vô tình dùng lại ID cho payload khác.
- Hai lần gửi đồng thời cùng ID nhưng dữ liệu khác nhau.
- Retry chỉ gửi một phần batch hoặc thay đổi thứ tự chunk.

Do đó, định danh batch cần gắn với một **manifest bất biến** mô tả nội dung mong đợi:

| Thuộc tính | Vai trò |
| --- | --- |
| batch_id | Khóa idempotency ổn định do client tạo |
| expected_chunks | Số chunk dự kiến trong batch |
| content_sha256 | Hash nội dung batch theo thứ tự đã quy định |
| sequence | Vị trí ổn định của từng chunk, ví dụ từ 0 đến N-1 |
| chunk_sha256 | Hash payload từng chunk để phát hiện chunk trùng nhưng khác nội dung |

Phạm vi khóa ở server thường là **tenant/owner + batch_id**, không chỉ batch_id toàn cục. Tenant phải được xác định từ danh tính đã xác thực, không tin một trường tenant do client tự khai báo trong protobuf.

Nếu cùng khóa idempotency nhưng manifest khác, server phải từ chối thay vì âm thầm xem đó là retry hợp lệ.

## 3. Thiết kế hợp đồng streaming có manifest

Một cách biểu diễn là message đầu tiên khai báo batch, các message tiếp theo mang chunk:

    syntax = "proto3";
    package ingest.v1;
    option java_package = "com.example.ingest.grpc";
    option java_multiple_files = true;

    service BatchUploadService {
      rpc Upload(stream UploadRequest) returns (UploadReceipt);
    }

    message UploadRequest {
      oneof body {
        BatchStart start = 1;
        BatchChunk chunk = 2;
      }
    }

    message BatchStart {
      string batch_id = 1;
      uint32 expected_chunks = 2;
      bytes content_sha256 = 3;
    }

    message BatchChunk {
      uint32 sequence = 1;
      bytes payload = 2;
      bytes chunk_sha256 = 3;
    }

    message UploadReceipt {
      string batch_id = 1;
      uint32 accepted_chunks = 2;
      bytes content_sha256 = 3;
      string committed_record_id = 4;
    }

Quy tắc của hợp đồng:

1. Message đầu tiên phải là BatchStart; chỉ có một manifest cho một RPC.
2. Các message sau là BatchChunk, có sequence duy nhất và payload đúng hash.
3. Server kiểm tra đủ expected_chunks, thứ tự và hash tổng trước khi commit.
4. Thành công trả đúng một UploadReceipt; lỗi kết thúc bằng gRPC status.
5. Retry dùng cùng batch_id, expected_chunks, content_sha256 và nội dung chunk.

Hash phải được tính trên một biểu diễn byte **xác định và thống nhất**. Ví dụ, hash tổng có thể là SHA-256 của payload chunk nối theo sequence; cần mô tả cách phân định ranh giới chunk để tránh nhập nhằng. Không hash một chuỗi JSON tùy ý nếu thứ tự field, encoding hoặc cách serialize có thể thay đổi giữa các client.

## 4. Lưu trạng thái idempotency bền vững

Idempotency phải tồn tại qua restart server. Một map trong RAM hoặc biến trong observer không đủ vì process có thể dừng sau commit, hoặc request retry tới instance khác.

Một mô hình dữ liệu đơn giản:

| Bảng | Khóa/ràng buộc chính | Dữ liệu |
| --- | --- | --- |
| upload_batch | Unique (tenant_id, batch_id) | Manifest, trạng thái, thời điểm tạo/cập nhật, receipt đã commit |
| upload_chunk | Unique (tenant_id, batch_id, sequence) | Chunk hash, payload staging hoặc vị trí lưu staging |
| domain_record | Unique theo ID nghiệp vụ/event | Dữ liệu đã commit, liên kết tới batch |

Trạng thái batch có thể là:

    RECEIVING -> COMMITTED
         |
         +----> FAILED / EXPIRED

- **RECEIVING:** manifest đã đăng ký, server đang nhận chunk.
- **COMMITTED:** dữ liệu và receipt đã được commit bền vững; trạng thái terminal thành công.
- **FAILED:** batch không thể tiếp tục theo chính sách nghiệp vụ.
- **EXPIRED:** staging chưa hoàn tất đã quá thời gian giữ và được dọn theo chính sách.

Chuyển trạng thái phải được bảo vệ bằng transaction, unique constraint hoặc cơ chế khóa phù hợp. Không để hai RPC đồng thời cùng xử lý và commit một batch theo hai đường khác nhau.

### Quy tắc nhận batch và chunk

Khi nhận BatchStart:

1. Xác thực caller và lấy tenant_id.
2. Tìm hoặc tạo upload_batch với khóa (tenant_id, batch_id).
3. Nếu chưa tồn tại, tạo trạng thái RECEIVING cùng manifest.
4. Nếu đã tồn tại, so sánh manifest. Cùng manifest thì xem là retry; manifest khác thì trả lỗi xung đột.
5. Nếu trạng thái đã là COMMITTED, trả lại receipt đã lưu; client dừng producer vì công việc đã hoàn tất.

Khi nhận mỗi BatchChunk:

- Nếu sequence chưa tồn tại, kiểm tra sequence hợp lệ, hash và giới hạn quota rồi ghi staging.
- Nếu sequence đã tồn tại **với cùng hash**, coi là bản gửi lại và không ghi thêm.
- Nếu sequence đã tồn tại **với hash khác**, từ chối vì cùng vị trí nhưng nội dung khác.
- Chỉ cập nhật tiến độ sau khi dữ liệu staging và hash được ghi bền vững theo transaction.

Khi nhận inbound onCompleted(), kiểm tra đã đủ expected_chunks và hash tổng khớp manifest. Sau đó commit dữ liệu nghiệp vụ, chuyển batch sang COMMITTED và lưu receipt trong cùng ranh giới transaction phù hợp. Chỉ sau khi transaction thành công mới gửi receipt về client.

## 5. Xử lý retry theo từng trạng thái

| Trạng thái khi client retry | Hành vi server |
| --- | --- |
| Chưa có batch ID | Tạo batch mới ở RECEIVING nếu manifest hợp lệ |
| RECEIVING, cùng manifest | Tiếp tục/resume; chunk trùng cùng hash là no-op |
| COMMITTED, cùng manifest | Trả lại receipt đã lưu; không commit lần nữa |
| Cùng batch ID nhưng manifest khác | Từ chối xung đột, không sửa manifest cũ |
| FAILED hoặc EXPIRED | Áp dụng chính sách đã công bố: yêu cầu batch ID mới hoặc cho phép reset có kiểm soát |
| Một RPC khác đang giữ lease xử lý batch | Từ chối/đợi theo chính sách; không cho hai writer cạnh tranh |

### Ví dụ: lần đầu bị ngắt sau chunk 2

Giả sử batch có 5 chunk với sequence 0..4:

1. Lần đầu server đã lưu staging chunk 0, 1, 2; kết nối mất trước khi client hoàn tất.
2. Client retry cùng batch_id và manifest, gửi lại chunk 0, 1, 2.
3. Server thấy sequence và hash trùng, không ghi thêm bản sao.
4. Client gửi tiếp chunk 3, 4.
5. Client half-close; server xác minh đủ 5 chunk và hash tổng, rồi commit một lần.

Nếu chunk 1 ở lần retry có payload khác, server không được ghi đè chunk đã nhận. Trả lỗi xung đột để client tạo batch mới với ID mới nếu đó thực sự là một nội dung nghiệp vụ khác.

## 6. Phần cốt lõi ở tầng Java

Không nên đặt toàn bộ chính sách idempotency trong một StreamObserver hoặc một map singleton. Tách phần xử lý bền vững thành một service có thao tác nguyên tử:

    public interface BatchIdempotencyStore {
        BeginResult begin(
                String tenantId, String batchId,
                int expectedChunks, byte[] contentSha256);

        // Cùng sequence + cùng hash: no-op.
        // Cùng sequence + khác hash: conflict.
        ChunkResult acceptChunk(
                String tenantId, String batchId,
                int sequence, byte[] payload, byte[] chunkSha256);

        // Kiểm tra đủ chunk/hash, commit và lưu receipt.
        UploadReceipt commit(String tenantId, String batchId);

        UploadReceipt findCommittedReceipt(
                String tenantId, String batchId, byte[] contentSha256);
    }

Đây là **hợp đồng minh họa ở tầng ứng dụng**, không phải API có sẵn của Spring gRPC. Implementation cần dùng database transaction/unique constraint; không được chỉ kiểm tra tồn tại rồi insert mà thiếu bảo vệ cạnh tranh giữa các request.

Một số nhánh xử lý server:

    // Khi nhận BatchStart:
    BeginResult begin = store.begin(tenantId, batchId, expectedChunks, digest);
    if (begin.isManifestConflict()) {
        responseObserver.onError(Status.ALREADY_EXISTS
            .withDescription("batch_id đã gắn với manifest khác")
            .asRuntimeException());
        return;
    }
    if (begin.isCommitted()) {
        responseObserver.onNext(begin.receipt());
        responseObserver.onCompleted();
        return;
    }

    // Khi nhận BatchChunk:
    ChunkResult result = store.acceptChunk(
        tenantId, batchId, sequence, payload, chunkDigest);
    if (result.isConflict()) {
        responseObserver.onError(Status.ALREADY_EXISTS
            .withDescription("sequence đã tồn tại với nội dung khác")
            .asRuntimeException());
        return;
    }

    // Khi inbound request onCompleted:
    UploadReceipt receipt = store.commit(tenantId, batchId);
    responseObserver.onNext(receipt);
    responseObserver.onCompleted();

Đoạn trích mô tả các nhánh chính; implementation thực cần kiểm soát vòng đời observer, trạng thái terminal, lỗi transaction và cancellation. Đặc biệt, nếu batch đã COMMITTED, server có thể trả receipt sớm ngay sau khi manifest khớp. Client phải dừng producer khi nhận response hoàn tất; không tiếp tục dùng request observer đã đóng.

### Đồng bộ khi có hai retry cùng lúc

Hai RPC có thể cùng dùng batch_id sau khi client retry quá sớm hoặc một worker khác cũng đang gửi lại. Unique constraint ngăn tạo hai hàng batch, nhưng chưa tự giải quyết toàn bộ việc ghi chunk và commit.

Cần một trong các cơ chế:

- Lease/lock theo (tenant_id, batch_id) để chỉ một RPC active ghi batch tại một thời điểm.
- Transaction/optimistic version để phát hiện cạnh tranh; request thua cuộc nhận ABORTED hoặc lỗi phù hợp và thử lại theo chính sách.
- Unique constraint trên chunk sequence cùng kiểm tra hash để mọi lần ghi lặp có kết quả xác định.

Lease phải có thời hạn và cơ chế thu hồi khi process chết; không giữ khóa vĩnh viễn vì một client mất mạng.

## 7. Status và quy tắc retry

| Tình huống | gRPC status gợi ý | Client nên làm gì |
| --- | --- | --- |
| Payload hoặc manifest sai định dạng | INVALID_ARGUMENT | Sửa dữ liệu; không retry nguyên trạng |
| Cùng batch ID nhưng manifest khác | ALREADY_EXISTS hoặc FAILED_PRECONDITION theo hợp đồng | Dùng ID mới cho batch nội dung mới |
| Cùng sequence nhưng hash khác | ALREADY_EXISTS hoặc FAILED_PRECONDITION | Dừng batch; điều tra dữ liệu thay đổi |
| Batch đang được RPC khác xử lý | ABORTED hoặc RESOURCE_EXHAUSTED theo chính sách | Chờ/tra cứu rồi retry cùng ID |
| Deadline hết hoặc kết nối đứt | DEADLINE_EXCEEDED / UNAVAILABLE | Tra cứu batch trước khi gửi lại |
| Batch đã commit, retry cùng manifest | OK với receipt đã lưu | Xem như thành công; không xử lý lại |
| Vượt quota message/byte | RESOURCE_EXHAUSTED | Chia batch theo chính sách; dùng ID phù hợp cho batch mới |

Không retry vô hạn. Dùng exponential backoff có jitter, giới hạn số lần thử và tổng thời gian retry. UNAVAILABLE có thể là lỗi tạm thời; INVALID_ARGUMENT thường không thể sửa bằng cách thử lại cùng payload. Với DEADLINE_EXCEEDED, tra cứu trạng thái trước vì server có thể đã commit.

## 8. Kiểm thử idempotency

Kiểm thử cần chứng minh **tác dụng phụ chỉ xảy ra một lần**, không chỉ kiểm tra client nhận status OK.

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Gửi batch lần đầu thành công | Một lần commit và một receipt được lưu |
| Retry cùng ID, cùng manifest sau commit | Trả receipt cũ; số record không tăng |
| Retry cùng ID nhưng manifest khác | Từ chối xung đột; dữ liệu đã commit không đổi |
| Ngắt sau vài chunk rồi retry cùng manifest | Chunk trùng cùng hash là no-op; tiếp tục phần còn thiếu |
| Cùng sequence nhưng payload/hash khác | Từ chối; không ghi đè chunk đã lưu |
| Hai RPC đồng thời cùng batch ID | Chỉ một writer/commit thắng; không nhân đôi tác dụng phụ |
| Mất response sau commit | Retry/tra cứu nhận lại receipt đã lưu |
| Batch staging hết TTL | Dọn staging, trạng thái chuyển EXPIRED; không để tài nguyên mồ côi |

Nên dùng database test thật hoặc test container để kiểm tra unique constraint, transaction rollback và cạnh tranh. Mock repository đơn thuần không chứng minh tính nguyên tử hay idempotency khi có hai request đồng thời.

## 9. Bảo mật và vận hành

- Phạm vi idempotency key phải gắn với caller/tenant đã xác thực; không cho người dùng khác đoán batch_id để đọc receipt.
- Dùng TLS để bảo vệ dữ liệu trên đường truyền; metadata/interceptor có thể xác thực và gắn correlation ID cho toàn RPC.
- Giới hạn số message, kích thước từng message, tổng batch bytes, số RPC đồng thời và thời gian giữ staging.
- Ghi metrics cho số retry, số batch đã trả receipt cũ, manifest conflict, duplicate chunk, batch hết hạn và thời gian từ RECEIVING đến COMMITTED.
- Không ghi payload nhạy cảm hoặc token vào log; log batch ID đã được kiểm soát và status phù hợp.
- Có job dọn staging hết hạn; cleanup phải an toàn với batch đang có lease hoặc vừa commit.

## 10. Tự luyện tập

1. Client gửi batch B-100, server commit nhưng response bị mất. Vì sao lần retry phải dùng lại batch_id và manifest?
2. Hai lần gửi cùng batch_id nhưng khác content_sha256: server nên làm gì và vì sao không được coi là retry hợp lệ?
3. Server nhận lại chunk sequence 4 với cùng hash. Làm thế nào để no-op mà không tăng số chunk đã lưu?
4. Hai RPC đồng thời retry cùng batch. Hãy đề xuất lease/lock và unique constraint để chỉ có một commit.
5. Thiết kế test mô phỏng “commit thành công, mất receipt, retry và nhận receipt cũ”; cần kiểm tra những bảng hoặc số lần gọi nào?

**Ghi nhớ:** Idempotency cho client streaming dựa trên **ID batch ổn định + manifest bất biến + nhận diện chunk + trạng thái commit bền vững**. Khi client retry đúng cùng batch, server phải tiếp tục hoặc trả lại receipt đã lưu mà không lặp tác dụng phụ; cùng ID nhưng nội dung khác phải bị từ chối. Timeout và mất response không chứng minh server chưa commit.
