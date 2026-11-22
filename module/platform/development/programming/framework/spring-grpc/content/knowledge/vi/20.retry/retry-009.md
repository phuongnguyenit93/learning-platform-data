# Retry client streaming và batch duplicate

## 1. Vì sao client streaming và batch cần chiến lược retry riêng?

Trong **Spring gRPC**, client-streaming RPC cho phép client gửi nhiều request message trên một call, sau đó server trả một response tổng hợp. Mẫu này phù hợp với import dữ liệu, đồng bộ danh mục, upload sự kiện hoặc gửi một batch lệnh.

Khó khăn xuất hiện khi kết nối bị ngắt giữa chừng. Server có thể đã xử lý một phần hoặc toàn bộ batch, nhưng client chưa nhận được response cuối. Nếu client mở call mới và gửi lại toàn bộ dữ liệu, server có thể xử lý trùng những item đã commit.

Hai khái niệm cần tách biệt:

- **Automatic retry của gRPC:** runtime có thể replay một RPC khi call chưa commit, request còn trong retry buffer và status phù hợp policy.
- **Replay/resubmit ở tầng ứng dụng:** client tạo một RPC mới và gửi lại batch hoặc phần chưa xác nhận, dùng ID ổn định để server deduplicate.

Với batch có tác dụng phụ, không thể dựa vào `maxAttempts` để bảo đảm không xử lý trùng. Cần định danh ổn định cho batch và từng item, lưu kết quả idempotency bền vững, rồi xác định cách khôi phục khi client không biết batch đã xử lý đến đâu.

## 2. Automatic retry bị giới hạn bởi commitment và retry buffer

gRPC chỉ có thể tự replay một call khi call còn **chưa commit**. Hai sự kiện quan trọng có thể làm call commit:

- Client nhận response headers từ server.
- Dữ liệu request được gửi vượt giới hạn retry buffer mà runtime có thể giữ để replay.

Với client streaming, client gửi nhiều message trên cùng call. Nếu toàn bộ request còn được buffer và server chưa gửi response headers, một số lỗi retryable có thể cho phép runtime replay call. Nhưng khi stream dài hoặc payload lớn vượt retry buffer, call có thể commit trước khi client gửi xong. Sau khi commit, lỗi tiếp theo không làm gRPC tự phát lại toàn bộ batch.

Vì vậy:

| Tình huống | Automatic retry | Hành vi ứng dụng |
| --- | --- | --- |
| Lỗi sớm, call chưa commit, status retryable | Có thể replay nếu policy và deadline cho phép | Để gRPC runtime xử lý |
| Request stream vượt retry buffer | Call có thể đã commit | Không dựa vào automatic retry |
| Server đã gửi response headers | Call đã commit | Tra cứu batch hoặc mở call mới theo contract |
| Server đã xử lý một phần rồi kết nối đứt | Không có bảo đảm replay an toàn | Replay với item ID ổn định và dedup |
| Server xử lý xong nhưng response cuối bị mất | Client không biết kết quả | Tra cứu receipt/status trước khi gửi lại |

Đừng mặc định mọi client-streaming RPC đều được retry tự động. Khả năng replay phụ thuộc thời điểm commitment, retry buffer, status, policy và deadline.

## 3. Định danh batch và từng item

Một batch cần ít nhất hai cấp định danh:

- `batch_id`: định danh một lần nhập liệu logic, giữ nguyên khi resubmit batch.
- `item_id`: định danh ổn định của từng record/lệnh trong batch, không đổi khi item được gửi lại.

Ví dụ:

```text
batch_id = import-2026-11-19-warehouse-17
item_id  = source-system:product:SKU-1042
item_id  = source-system:product:SKU-1043
item_id  = source-system:product:SKU-1044
```

Server nên tạo khóa dedup theo scope `(tenant_id, method_name, batch_id, item_id)`. Như vậy cùng item ID ở một batch mới là thao tác khác, còn item được gửi lại trong cùng batch vẫn deduplicate. Nếu contract bảo đảm item ID duy nhất toàn cục theo tenant/method, có thể dùng khóa hẹp hơn; phải chọn một semantics duy nhất và công bố rõ.

Không tạo UUID mới cho item mỗi lần retry. Nếu ID thay đổi, server không thể biết item mới là bản gửi lại của item cũ.

## 4. Hợp đồng Protobuf cho batch streaming

Ví dụ `batch_import.proto`:

```proto
syntax = "proto3";

package import.v1;

option java_multiple_files = true;
option java_package = "com.example.importing.v1";

service BatchImport {
  rpc UploadBatch(stream BatchItem) returns (BatchReceipt);
  rpc GetBatchStatus(GetBatchStatusRequest) returns (BatchStatus);
}

message BatchItem {
  string batch_id = 1;
  string item_id = 2;
  string source_version = 3;
  string payload = 4;
}

message BatchReceipt {
  string batch_id = 1;
  // Các bộ đếm dưới đây mô tả lần upload RPC hiện tại.
  int32 total_items = 2;
  int32 applied_items = 3;
  int32 duplicate_items = 4;
  int32 rejected_items = 5;
  string state = 6;
  int32 pending_items = 7;
}

message GetBatchStatusRequest {
  string batch_id = 1;
}

message BatchStatus {
  // Trạng thái và bộ đếm bền vững của toàn batch.
  string batch_id = 1;
  string state = 2;
  int32 total_items = 3;
  int32 applied_items = 4;
  int32 rejected_items = 5;
  string detail = 6;
  int32 pending_items = 7;
}
```

`UploadBatch` nhận nhiều item và chỉ trả một `BatchReceipt` khi request stream hoàn tất. `GetBatchStatus` giúp client tra cứu kết quả sau khi call bị ngắt hoặc response cuối bị mất.

`BatchReceipt` đếm số item nhận/xử lý trong **lần upload hiện tại**: một item được áp dụng lần đầu là applied, item đã có kết quả là duplicate, item bị validation/conflict là rejected. `GetBatchStatus` phản ánh trạng thái bền vững của toàn batch qua nhiều lần upload; không cộng bộ đếm từng attempt một cách mù quáng.

Khi tra cứu trạng thái, server phải lấy tenant từ security context đã xác thực và kiểm tra quyền truy cập batch; không tin một `batch_id` do client cung cấp là đủ để đọc dữ liệu tenant khác.

Contract cần quy định rõ:

- Một `batch_id` chỉ đại diện một batch logic; replay phải giữ nguyên ID.
- Một `item_id` luôn đại diện cùng một nội dung nghiệp vụ.
- Cùng ID và cùng payload fingerprint là duplicate hợp lệ; server trả lại kết quả đã lưu và không áp dụng side effect lần nữa.
- Cùng ID nhưng payload khác là conflict, không được âm thầm ghi đè.
- `BatchReceipt` kết hợp bộ đếm của lần upload hiện tại với kết quả bền vững; `GetBatchStatus` là nguồn chuẩn để biết trạng thái toàn batch.
- Trạng thái batch có thể là `PROCESSING`, `COMPLETED`, `COMPLETED_WITH_ERRORS` hoặc `FAILED`; cần thống nhất semantics giữa client và server.

Ví dụ giữ kết quả từng item trong database và chỉ trả số đếm trong receipt. Với batch lớn, không nhét toàn bộ lỗi chi tiết vào một response duy nhất; cung cấp API truy vấn kết quả theo trang hoặc theo item ID.

## 5. Xử lý duplicate theo từng item

Không nên deduplicate chỉ bằng `batch_id`. Một batch có thể được gửi lại sau khi server đã xử lý một phần; server cần biết item nào đã commit, item nào chưa.

Một bảng idempotency tối thiểu:

```sql
CREATE TABLE batch_item_result (
    tenant_id       VARCHAR(100) NOT NULL,
    method_name     VARCHAR(200) NOT NULL,
    batch_id        VARCHAR(160) NOT NULL,
    item_id         VARCHAR(200) NOT NULL,
    payload_hash    VARCHAR(64) NOT NULL,
    state           VARCHAR(32) NOT NULL,
    result_payload  BYTEA,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, method_name, batch_id, item_id)
);
```

Khóa chính bảo đảm cùng item trong cùng batch không thể được claim hai lần. Một batch mới có thể chứa item ID tương tự mà không bị nhầm với lần import trước.

Luồng xử lý một item:

1. Xác thực tenant và batch.
2. Chuẩn hóa payload và tính fingerprint.
3. Thử claim item bằng thao tác database atomic dựa trên unique constraint.
4. Nếu claim mới thành công, áp dụng thay đổi nghiệp vụ và lưu kết quả trong cùng transaction.
5. Nếu item đã tồn tại và fingerprint khớp, trả trạng thái đã lưu, không thực hiện lại side effect.
6. Nếu item đã tồn tại nhưng fingerprint khác, đánh dấu conflict và từ chối item.

Không dùng `SELECT` rồi `INSERT` mà thiếu unique constraint. Hai request đồng thời có thể cùng đọc “chưa tồn tại” và cùng áp dụng side effect.

### 5.1. Xử lý item đồng thời

Khi hai batch upload trùng item cùng lúc:

- Unique constraint chỉ cho một transaction claim item mới.
- Request còn lại phải đọc trạng thái đã được claim/commit.
- Nếu item đã hoàn tất, trả kết quả cũ.
- Nếu item đang xử lý, không khởi chạy side effect lần hai; trả trạng thái `IN_PROGRESS` hoặc để client tra cứu sau.
- Nếu transaction owner rollback, item claim cũng rollback để request sau có thể xử lý.

Nếu dùng trạng thái `IN_PROGRESS` được commit trước side effect, cần lease, owner token và cơ chế phục hồi khi worker chết. Nếu side effect và kết quả có thể nằm trong cùng transaction database, giữ chúng cùng transaction sẽ đơn giản và an toàn hơn.

## 6. Spring service: xử lý stream và tổng hợp receipt

Ví dụ dưới đây xử lý từng item đồng bộ trong callback để thể hiện ranh giới transaction. Trong production, có thể dùng worker/queue riêng, nhưng phải giới hạn queue, giữ thứ tự khi cần và chỉ trả receipt sau khi mọi item đã có kết quả bền vững.

```java
package com.example.importing;

import com.example.importing.v1.BatchImportGrpc;
import com.example.importing.v1.BatchItem;
import com.example.importing.v1.BatchReceipt;
import com.example.importing.v1.BatchStatus;
import com.example.importing.v1.GetBatchStatusRequest;
import io.grpc.Status;
import io.grpc.stub.ServerCallStreamObserver;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;

@Service
public class BatchImportGrpcService
        extends BatchImportGrpc.BatchImportImplBase {

    private final BatchItemHandler itemHandler;
    private final BatchResultStore resultStore;

    public BatchImportGrpcService(
            BatchItemHandler itemHandler,
            BatchResultStore resultStore) {
        this.itemHandler = itemHandler;
        this.resultStore = resultStore;
    }

    @Override
    public StreamObserver<BatchItem> uploadBatch(
            StreamObserver<BatchReceipt> responseObserver) {
        ServerCallStreamObserver<BatchReceipt> output =
                (ServerCallStreamObserver<BatchReceipt>) responseObserver;
        return new StreamObserver<>() {
            private String batchId;
            private boolean terminated;
            private int totalItems;
            private int appliedItems;
            private int duplicateItems;
            private int rejectedItems;
            private int pendingItems;

            {
                output.setOnCancelHandler(() -> {
                    synchronized (this) {
                        terminated = true;
                        if (batchId != null) {
                            resultStore.markInterruptedIfOpen(batchId);
                        }
                    }
                });
            }

            @Override
            public synchronized void onNext(BatchItem item) {
                if (terminated) return;
                if (item.getBatchId().isBlank()
                        || item.getItemId().isBlank()) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("batch_id và item_id bắt buộc"));
                    return;
                }
                if (batchId == null) {
                    batchId = item.getBatchId();
                } else if (!batchId.equals(item.getBatchId())) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("Một stream chỉ chứa một batch_id"));
                    return;
                }

                totalItems++;
                try {
                    // Atomic dedup + business effect + stored outcome.
                    switch (itemHandler.applyOnce(item)) {
                        case APPLIED -> appliedItems++;
                        case DUPLICATE -> duplicateItems++;
                        case REJECTED -> rejectedItems++;
                        case IN_PROGRESS -> pendingItems++;
                    }
                } catch (ItemConflictException conflict) {
                    // Conflict là lỗi của item; handler ghi nhận kết quả reject.
                    rejectedItems++;
                    itemHandler.recordConflict(item, conflict);
                } catch (RuntimeException error) {
                    fail(Status.INTERNAL
                            .withDescription("Không thể xử lý batch item"));
                }
            }

            @Override
            public synchronized void onError(Throwable error) {
                terminated = true;
                // Batch vẫn có thể ở trạng thái PARTIAL/PROCESSING.
                // Client tra cứu bằng batchId trước khi resubmit.
                if (batchId != null) {
                    resultStore.markInterruptedIfOpen(batchId);
                }
            }

            @Override
            public synchronized void onCompleted() {
                if (terminated) return;
                if (output.isCancelled()) {
                    terminated = true;
                    if (batchId != null) {
                        resultStore.markInterruptedIfOpen(batchId);
                    }
                    return;
                }
                if (batchId == null) {
                    fail(Status.INVALID_ARGUMENT
                            .withDescription("Batch không có item"));
                    return;
                }
                try {
                    BatchReceipt receipt = resultStore.buildReceipt(
                            batchId, totalItems, appliedItems,
                            duplicateItems, rejectedItems, pendingItems);
                    terminated = true;
                    output.onNext(receipt);
                    output.onCompleted();
                } catch (RuntimeException error) {
                    fail(Status.INTERNAL
                            .withDescription("Không thể tổng hợp batch receipt"));
                }
            }

            private synchronized void fail(Status status) {
                if (!terminated) {
                    terminated = true;
                    if (batchId != null) {
                        resultStore.markInterruptedIfOpen(batchId);
                    }
                    if (!output.isCancelled()) {
                        output.onError(status.asRuntimeException());
                    }
                }
            }
        };
    }

    @Override
    public void getBatchStatus(
            GetBatchStatusRequest request,
            StreamObserver<BatchStatus> responseObserver) {
        try {
            responseObserver.onNext(
                    resultStore.getStatus(request.getBatchId()));
            responseObserver.onCompleted();
        } catch (BatchNotFoundException error) {
            responseObserver.onError(Status.NOT_FOUND
                    .withDescription("Không tìm thấy batch")
                    .asRuntimeException());
        }
    }
}
```

`BatchItemHandler.applyOnce()` trả về `APPLIED`, `DUPLICATE`, `REJECTED` hoặc `IN_PROGRESS`, đồng thời thực hiện claim, dedup, side effect và lưu outcome theo transaction/unique constraint ở phần trước. `IN_PROGRESS` nghĩa là một request khác đang sở hữu item; không được thực thi side effect lần hai. `recordConflict()` ghi nhận conflict của lần upload hiện tại ở attempt log/receipt riêng; không ghi đè fingerprint hoặc kết quả canonical của item đã được xử lý trước đó. `BatchResultStore.buildReceipt()` kết hợp bộ đếm của lần upload hiện tại với trạng thái batch bền vững; `GetBatchStatus` mới là nguồn chuẩn để reconciliation sau khi mất response.

Ví dụ dùng callback tuần tự và xử lý đồng bộ. Nếu chuyển xử lý sang executor:

- Dùng queue hữu hạn và manual inbound flow control hoặc cơ chế backpressure phù hợp.
- Không trả response cuối trước khi mọi item đã hoàn tất hoặc được ghi nhận trạng thái.
- Đồng bộ việc cập nhật trạng thái batch và tránh callback ghi response đồng thời.
- Khi RPC bị cancel, dừng nhận item mới; không xóa kết quả đã commit.

## 7. Client: giữ batch identity qua resubmit

Client cần lưu `batch_id`, danh sách `item_id` và payload trước khi gửi. Khi stream kết thúc bình thường, đọc receipt. Khi nhận lỗi hoặc mất kết nối, không tạo ID mới và không mặc định batch thất bại.

Luồng khôi phục:

1. Gọi `GetBatchStatus(batch_id)` trên nguồn trạng thái có consistency phù hợp và scope theo tenant đã xác thực.
2. Nếu `COMPLETED`, dùng receipt/trạng thái đã lưu; không upload lại.
3. Nếu `PROCESSING`, chờ hoặc poll có giới hạn.
4. Nếu batch còn thiếu item và server hỗ trợ replay an toàn, mở RPC mới với **cùng batch ID và item ID**.
5. Server deduplicate item đã commit và chỉ xử lý item chưa có kết quả.
6. Nếu status không thể xác định, giữ trạng thái client là `UNKNOWN`; không gửi batch mới với ID khác.

Nếu status store đọc từ replica eventual-consistent, `NOT_FOUND` hoặc bộ đếm chưa cập nhật không chứng minh batch chưa được xử lý. Khi cần quyết định replay, status lookup phải đọc từ nguồn nhất quán hoặc dùng một cơ chế reconciliation có thể xác nhận trạng thái.

Ví dụ client-streaming stub:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import io.grpc.stub.StreamObserver;
import com.example.importing.v1.BatchItem;
import com.example.importing.v1.BatchReceipt;

String batchId = persistedBatch.batchId();
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<BatchReceipt> receiptRef = new AtomicReference<>();
AtomicReference<Throwable> failureRef = new AtomicReference<>();

StreamObserver<BatchReceipt> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(BatchReceipt receipt) {
        receiptRef.set(receipt);
    }

    @Override
    public void onError(Throwable error) {
        failureRef.set(error);
        completed.countDown();
    }

    @Override
    public void onCompleted() {
        completed.countDown();
    }
};

StreamObserver<BatchItem> requestObserver = batchStub
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .uploadBatch(responseObserver);

for (PersistedItem item : persistedBatch.items()) {
    requestObserver.onNext(BatchItem.newBuilder()
            .setBatchId(batchId)
            .setItemId(item.itemId())
            .setSourceVersion(item.sourceVersion())
            .setPayload(item.payload())
            .build());
}
requestObserver.onCompleted();

if (!completed.await(35, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Chưa nhận terminal callback");
}
if (failureRef.get() != null) {
    // Tra cứu GetBatchStatus(batchId); không tạo batch_id mới.
    reconcileBatch(batchId, failureRef.get());
} else {
    persistReceipt(receiptRef.get());
}
```

Đây là ví dụ cho một lần upload. `persistedBatch` phải giữ batch ID và item IDs ổn định qua process restart; `reconcileBatch()` thực hiện status lookup và quyết định có resubmit hay không. Trong ứng dụng thực, bảo đảm channel/stub được quản lý vòng đời, xử lý interruption và hủy call khi caller không còn quan tâm.

## 8. Retry cả batch hay chỉ item chưa hoàn tất?

Hai cách có trade-off khác nhau:

| Cách | Ưu điểm | Điều kiện |
| --- | --- | --- |
| Replay toàn batch với cùng ID | Đơn giản; server deduplicate item đã xử lý | Server lưu kết quả item bền vững và xử lý duplicate an toàn |
| Resubmit chỉ item chưa hoàn tất | Giảm băng thông và chi phí xử lý | Client có receipt/status đáng tin cậy theo từng item |
| Chia batch thành chunk nhỏ | Giới hạn lượng dữ liệu cần replay và retry buffer | Mỗi chunk có ID/sequence và receipt riêng |

Với batch nhỏ hoặc vừa, replay toàn batch cùng item IDs có thể đơn giản và đáng tin cậy. Với batch lớn, nên chia chunk có định danh ổn định, ví dụ `batch_id + chunk_number`, rồi lưu receipt từng chunk. Như vậy client chỉ cần resume từ chunk chưa hoàn tất.

Không resubmit một phần dựa trên bộ đếm client nếu client chưa nhận được xác nhận bền vững. Nếu response cuối bị mất, client không biết item cuối cùng server đã commit là item nào; hãy tra cứu server state hoặc replay với dedup.

## 9. Partial success và batch state

Một batch có thể chứa item hợp lệ và item bị từ chối. Contract cần phân biệt:

- **Transport/RPC failure:** call kết thúc bằng gRPC status; client có thể không nhận được receipt.
- **Item rejection:** một item bị từ chối do validation hoặc conflict; các item khác vẫn có thể được xử lý.
- **Batch completion:** mọi item đã có kết quả cuối; receipt phản ánh số applied, duplicate và rejected.
- **Batch processing:** server chưa xử lý xong hoặc còn worker đang thực hiện.

Không dùng `onError()` cho mọi lỗi của item nếu chính sách là cho phép batch partial success. Lỗi validation của một item nên được ghi nhận như outcome của item; lỗi hạ tầng làm batch không thể tiếp tục mới có thể kết thúc toàn RPC.

Nếu batch xử lý song song, receipt chỉ được phát khi mọi item đã đạt trạng thái cuối hoặc batch được đánh dấu partial theo contract. Một item đang `IN_PROGRESS` không được tính là completed.

## 10. Kiểm thử retry và batch duplicate

Kiểm thử phải xác minh số side effect, không chỉ số lần RPC được gọi:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Gửi batch lần đầu thành công | Mỗi item được áp dụng một lần; nhận receipt đúng |
| Gửi lại toàn batch cùng ID và payload | Item cũ được deduplicate; không phát sinh side effect mới |
| Cùng item ID nhưng payload khác | Item conflict; không ghi đè kết quả cũ |
| Ngắt kết nối sau một phần item đã commit | Status phản ánh partial; replay cùng IDs không áp dụng trùng |
| Server xử lý xong nhưng receipt bị mất | Status lookup trả kết quả đã hoàn tất |
| Hai upload cùng batch chạy đồng thời | Unique constraint ngăn item được xử lý hai lần |
| Executor/database lỗi khi xử lý một item | Không để item ở trạng thái giả completed; có thể reconcile |
| Request stream vượt retry buffer | Không kỳ vọng automatic retry; ứng dụng dùng status lookup/replay |
| Deadline hết giữa batch | Client không kết luận batch rollback; tra cứu trạng thái |
| Batch chia chunk | Chunk đã hoàn tất không bị xử lý lại; chunk còn thiếu được tiếp tục |

Dùng test database hoặc repository có unique constraint thật để kiểm thử race condition. Test tuần tự trong memory không đủ chứng minh dedup an toàn khi nhiều replica cùng nhận batch. Mô phỏng response bị mất sau commit để kiểm tra ambiguous outcome.

## 11. Sai lầm thường gặp

1. **Tăng `maxAttempts` và nghĩ client stream luôn replay được.** Retry buffer và commitment có thể làm call commit trước khi stream hoàn tất.
2. **Chỉ dùng `batch_id` để deduplicate.** Cần biết item nào đã commit trong batch.
3. **Tạo item ID mới khi resubmit.** Server coi item gửi lại là item mới.
4. **Dùng bộ đếm trong RAM làm receipt.** Process restart hoặc nhiều replica làm mất tính đúng đắn.
5. **Dùng SELECT rồi INSERT không có unique constraint.** Hai request đồng thời có thể cùng áp dụng side effect.
6. **Trả receipt trước khi mọi item có kết quả bền vững.** Client có thể tin batch đã hoàn tất dù còn item đang xử lý.
7. **Coi RPC error là batch rollback.** Một phần hoặc toàn bộ batch có thể đã commit.
8. **Retry lồng ở client, service và dependency mà không giới hạn.** Một batch có thể khuếch đại thành nhiều lần xử lý downstream.
9. **Không giới hạn kích thước batch.** Batch quá lớn làm tăng retry buffer, bộ nhớ, thời gian xử lý và chi phí replay.

## 12. Bài tập vận dụng

Với `import.v1.BatchImport/UploadBatch`:

1. Tạo batch gồm 100 item với `batch_id` và `item_id` ổn định.
2. Lưu fingerprint và kết quả từng item bằng unique constraint; side effect và outcome phải cùng transaction.
3. Ngắt client sau khi server đã commit một phần batch; gọi `GetBatchStatus` và xác định item còn thiếu.
4. Resubmit toàn batch với cùng IDs; xác minh item đã commit trở thành duplicate và không áp dụng lại.
5. Gửi cùng item ID với payload khác; xác minh conflict.
6. Chạy hai upload đồng thời cùng batch để kiểm tra atomic dedup.
7. Chia batch lớn thành chunk và so sánh chi phí replay với cách gửi lại toàn bộ.

**Tiêu chí hoàn thành:** người học giải thích được giới hạn automatic retry của client streaming, thiết kế batch/item identity ổn định, deduplicate nguyên tử từng item, xử lý partial/ambiguous outcome và khôi phục batch mà không lặp tác dụng phụ.

### Tài liệu tham khảo

- [gRPC Retry](https://grpc.io/docs/guides/retry/): retry commitment, retry buffer và giới hạn replay.
- [gRPC Core Concepts](https://grpc.io/docs/what-is-grpc/core-concepts/): client streaming và vòng đời RPC.
- [gRPC Service Config](https://grpc.io/docs/guides/service-config/): retry policy theo service và method.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction và tính nguyên tử trong Spring.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
