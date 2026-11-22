# Lỗi sau khi đã phát một phần dữ liệu

## 1. Một stream có thể thất bại sau khi client đã nhận dữ liệu

Trong **SPRING_GRPC**, dịch vụ gRPC dùng hợp đồng Protocol Buffers và mã Java được sinh để trao đổi giữa client/server trong hệ sinh thái Spring. Với **server streaming**, client gửi một request, server lần lượt phát nhiều response trên cùng một RPC. Khác với một lời gọi unary, server streaming có thể đã chuyển được một phần kết quả trước khi gặp lỗi.

Ví dụ, client yêu cầu đọc lịch sử giao dịch của tài khoản. Server gửi ba giao dịch đầu tiên, nhưng nguồn dữ liệu bị mất kết nối trước khi đọc giao dịch thứ tư:

~~~text
Client gửi: WatchLedger(account_id = "A-42")

Server phát:  #1  DEPOSIT  100
              #2  PAYMENT  25
              #3  REFUND   10
              X   Database connection lost

RPC kết thúc: onError(UNAVAILABLE)
~~~

Client có thể đã nhận và xử lý ba giao dịch, nhưng **toàn bộ RPC không hoàn thành thành công**. Nó phải phân biệt dữ liệu đã nhận với kết quả đầy đủ. Nếu client chỉ hiển thị thông báo lỗi rồi bỏ qua ba response đã nhận, dữ liệu đã xử lý có thể bị mất khỏi góc nhìn người dùng. Nếu client coi ba response là kết quả hoàn chỉnh, nó có thể đưa ra quyết định sai vì còn giao dịch chưa được đọc.

Chủ đề này tập trung vào cách hiểu và xử lý **lỗi sau khi đã phát một phần dữ liệu**:

- Ý nghĩa của response đã gửi, response đã nhận và response đã được áp dụng.
- Cách server kết thúc một stream bằng status lỗi sau một số lần `onNext`.
- Cách client giữ lại tiến độ một phần và không đánh dấu RPC hoàn tất.
- Phân biệt lỗi toàn stream với lỗi của một phần tử dữ liệu.
- Thiết kế sequence, checkpoint và resume để tránh mất hoặc xử lý trùng dữ liệu.
- Kiểm thử trường hợp nhận được một vài response rồi mới gặp status lỗi.

## 2. Ba mốc dữ liệu không được đánh đồng

Khi một stream gặp lỗi, câu hỏi “server đã gửi đến đâu?” không đồng nghĩa với “client đã xử lý đến đâu?”. Có ít nhất ba mốc riêng:

| Mốc | Ý nghĩa | Có thể xác nhận bằng gì? |
|---|---|---|
| **Server đã phát** | Server đã gọi `responseObserver.onNext(event)` | Log/metric tại server |
| **Client đã nhận** | Callback `onNext(event)` hoặc iterator phía client đã cung cấp message | Log/metric tại client |
| **Client đã áp dụng bền vững** | Nghiệp vụ client đã xử lý thành công và lưu kết quả/checkpoint | Trạng thái lưu trữ hoặc ACK ở tầng ứng dụng |

Ví dụ server đã gọi `onNext(#4)` nhưng kết nối bị đứt trước khi client nhận message đó. Server không thể chỉ dựa vào lời gọi `onNext` để kết luận client đã lưu #4. Ngược lại, client có thể đã nhận #3 nhưng lỗi xảy ra trước khi bước ghi database của client hoàn thành.

~~~mermaid
flowchart LR
    A["Server onNext(#1..#3)"] --> B["gRPC / HTTP/2 transport"]
    B --> C["Client callback nhận #1..#3"]
    C --> D["Client xử lý và lưu checkpoint"]
    D --> E["Đã áp dụng đến sequence 2"]
    A -. "Lỗi nguồn dữ liệu sau #3" .-> F["onError(UNAVAILABLE)"]
    F --> C
~~~

Sơ đồ minh họa một tình huống: client nhận đến #3 nhưng chỉ lưu bền đến #2. Khi RPC lỗi, điểm resume an toàn có thể là #2, không phải #3. Client phải quyết định checkpoint dựa trên **kết quả xử lý của chính nó**, không dựa vào số message server đã tạo hoặc số callback đã bắt đầu.

## 3. Quy tắc kết thúc: onNext rồi onError

Server streaming sử dụng `StreamObserver<ResponseT>`:

- `onNext(response)` phát một message. Server có thể gọi nhiều lần khi RPC còn hoạt động.
- `onCompleted()` kết thúc RPC thành công sau khi không còn response nào.
- `onError(throwable)` kết thúc RPC bằng lỗi và status gRPC tương ứng.

Một stream có thể kết thúc theo chuỗi hợp lệ:

~~~text
onNext(event #1)
onNext(event #2)
onNext(event #3)
onError(Status.UNAVAILABLE)
~~~

Sau `onError`, server không gọi tiếp `onNext` hoặc `onCompleted`. `onError` là terminal signal. Trên đường truyền hoạt động bình thường, các response đã gửi trước terminal status được quan sát theo thứ tự trước khi client nhận callback kết thúc. Nhưng nếu transport bị lỗi, client có thể chỉ nhận một phần các message đang truyền.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring gRPC server
    participant DB as Data source
    C->>S: WatchLedger(account_id)
    S->>DB: Read next entries
    DB-->>S: Entry #1
    S-->>C: onNext(#1)
    DB-->>S: Entry #2
    S-->>C: onNext(#2)
    DB-->>S: Entry #3
    S-->>C: onNext(#3)
    DB--xS: Connection lost
    S-->>C: onError(UNAVAILABLE)
    Note over C: Giữ tiến độ một phần; RPC chưa hoàn tất
~~~

Điểm quan trọng: **lỗi sau dữ liệu không xóa các response client đã nhận**. Nhưng các response đó cũng không biến một RPC thất bại thành RPC thành công.

## 4. Hợp đồng Protocol Buffers cần định danh từng phần tử

Một stream có thể khôi phục sau lỗi cần một cách nhận biết phần tử và thứ tự của nó. Ví dụ đọc sổ giao dịch:

~~~proto
syntax = "proto3";

package ledger.v1;

option java_multiple_files = true;
option java_package = "com.example.ledger.rpc";
option java_outer_classname = "LedgerProto";

service LedgerService {
  rpc ReadLedger(ReadLedgerRequest) returns (stream LedgerEntry);
}

message ReadLedgerRequest {
  string account_id = 1;
  int64 after_sequence = 2;
}

message LedgerEntry {
  string account_id = 1;
  int64 sequence = 2;
  string entry_id = 3;
  string entry_type = 4;
  int64 amount_minor_units = 5;
}
~~~

`sequence` là số tăng theo phạm vi tài khoản; `after_sequence` yêu cầu server chỉ phát các phần tử sau checkpoint đã lưu. Ví dụ client đã áp dụng đến #2 thì mở phiên mới với `after_sequence = 2` để tiếp tục từ #3.

Hợp đồng này **chỉ khai báo khả năng tiếp tục**, chưa tự cung cấp khả năng đó. Server phải có nguồn dữ liệu cho phép đọc lại theo sequence, giữ lịch sử đủ lâu và bảo đảm không có khoảng trống khi chuyển từ đọc lịch sử sang nhận sự kiện mới.

Một sequence hữu ích cần có các thuộc tính:

1. **Ổn định:** cùng một phần tử khi replay vẫn giữ cùng sequence và ID.
2. **Có phạm vi:** xác định sequence tăng theo tài khoản, job hay partition; không dùng một bộ đếm không rõ phạm vi.
3. **Có thứ tự xác định:** nếu nghiệp vụ yêu cầu thứ tự, server phải truy vấn hoặc sắp xếp theo quy tắc đó.
4. **Có thể kiểm tra:** client phát hiện sequence trùng hoặc bị nhảy.
5. **Không đồng nghĩa ACK:** sequence cho biết vị trí phần tử, còn checkpoint client cho biết phần tử nào đã được áp dụng bền vững.

Không nên dùng timestamp đơn thuần làm cursor nếu nhiều event có thể cùng timestamp, đồng hồ giữa nguồn không đồng nhất hoặc dữ liệu có thể được chèn ngược thời gian. ID tăng đơn điệu hoặc cặp khóa sắp thứ tự ổn định thường dễ khôi phục hơn.

## 5. Server phát một phần rồi kết thúc bằng status lỗi

Ví dụ service sau đọc dữ liệu từ một nguồn có thể lỗi trong lúc duyệt. Điểm minh họa là **không gọi `onCompleted()` khi nguồn bị lỗi**; server kết thúc bằng status không thành công.

~~~java
package com.example.ledger;

import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

import java.util.Iterator;
import java.util.stream.Stream;

@Service
public class LedgerServiceImpl
        extends LedgerServiceGrpc.LedgerServiceImplBase {

    private final LedgerRepository repository;

    public LedgerServiceImpl(LedgerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void readLedger(
            ReadLedgerRequest request,
            StreamObserver<LedgerEntry> responses) {

        String accountId = request.getAccountId().trim();
        if (accountId.isEmpty() || request.getAfterSequence() < 0) {
            responses.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid account_id or after_sequence")
                    .asRuntimeException());
            return;
        }

        try (Stream<LedgerRow> rows =
                     repository.streamAfter(accountId, request.getAfterSequence())) {
            Iterator<LedgerRow> iterator = rows.iterator();

            while (iterator.hasNext()) {
                LedgerRow row = iterator.next();
                responses.onNext(toProto(row));
            }
        } catch (DataAccessException sourceFailure) {
            // Một số response có thể đã được phát trước lỗi nguồn dữ liệu.
            // Status kết thúc toàn RPC là lỗi; không gọi onCompleted().
            responses.onError(Status.UNAVAILABLE
                    .withDescription("Ledger source became unavailable")
                    .asRuntimeException());
            return;
        }

        // Chỉ hoàn thành thành công sau khi đọc và đóng nguồn dữ liệu bình thường.
        responses.onCompleted();
    }

    private LedgerEntry toProto(LedgerRow row) {
        return LedgerEntry.newBuilder()
                .setAccountId(row.accountId())
                .setSequence(row.sequence())
                .setEntryId(row.entryId())
                .setEntryType(row.entryType())
                .setAmountMinorUnits(row.amountMinorUnits())
                .build();
    }
}
~~~

`LedgerRepository`, `LedgerRow` là kiểu của ứng dụng minh họa. Trong một dự án thực, `streamAfter(...)` cần trả về nguồn dữ liệu có thể đóng và có cách xử lý khi RPC bị hủy. Ví dụ tập trung vào lỗi truy xuất dữ liệu: nếu `iterator.hasNext()` hoặc `iterator.next()` ném `DataAccessException` sau khi đã phát vài response, server gọi `onError(UNAVAILABLE)` và không gọi `onCompleted()`.

Các điểm thiết kế:

- **Validate trước khi phát:** lỗi request được trả trước response đầu tiên.
- **Ánh xạ lỗi nguồn:** `UNAVAILABLE` phù hợp khi nguồn phụ thuộc tạm thời không sẵn sàng; mã khác có thể phù hợp hơn nếu lỗi là vi phạm dữ liệu hoặc lỗi lập trình.
- **Không tiết lộ exception:** mô tả status không chứa SQL, hostname, thông tin xác thực hay stack trace. Chi tiết kỹ thuật ghi vào log/trace nội bộ có kiểm soát.
- **Một terminal signal:** nhánh lỗi gọi `onError` rồi return; nhánh thành công gọi `onCompleted` sau khi stream nguồn đã đóng bình thường.
- **Dữ liệu một phần là có thật:** các response đã được client nhận vẫn có thể được giữ lại; server không thể rollback side effect của client.

Đoạn code đồng bộ minh họa luồng lỗi nguồn. Nếu truy vấn có thể chặn lâu, hoặc stream sống lâu, cần thiết kế producer bất đồng bộ, cancellation handler và backpressure. Không giữ một thread RPC chờ nguồn dữ liệu vô hạn.

### 5.1. Chọn status nào khi lỗi sau một phần dữ liệu?

Status phải mô tả nguyên nhân khiến **RPC không thể hoàn thành**, không chỉ việc một phần tử có vấn đề:

| Status | Ví dụ | Client nên hiểu |
|---|---|---|
| `UNAVAILABLE` | Database hoặc service phụ thuộc tạm thời mất kết nối | Có thể thử lại sau nếu nguồn và hợp đồng cho phép resume |
| `INTERNAL` | Lỗi bất ngờ trong xử lý server | RPC thất bại; cần điều tra server |
| `RESOURCE_EXHAUSTED` | Server hết quota hoặc vượt giới hạn tài nguyên | Có thể giảm tải/chờ theo chính sách |
| `PERMISSION_DENIED` | Quyền đọc bị từ chối | Không retry bằng cùng danh tính/quyền |
| `NOT_FOUND` | Tài khoản hoặc đối tượng nguồn không tồn tại | Không có dữ liệu để tiếp tục với định danh đó |
| `DATA_LOSS` | Phát hiện dữ liệu bị hỏng hoặc mất tính toàn vẹn | Cần xử lý theo chính sách dữ liệu, không retry mù |

`INVALID_ARGUMENT` thường thích hợp cho request sai trước khi stream bắt đầu. Nếu phát hiện một lỗi toàn vẹn nghiêm trọng giữa luồng, status cụ thể tùy hợp đồng và ý nghĩa lỗi; không dùng `OK` để che giấu dữ liệu chưa đầy đủ.

## 6. Client nhận message rồi gặp onError

Với asynchronous stub, client cung cấp `StreamObserver<LedgerEntry>`. Callback `onNext` có thể được gọi nhiều lần trước khi `onError` thông báo RPC thất bại.

~~~java
import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

import java.util.concurrent.atomic.AtomicLong;

AtomicLong lastApplied = new AtomicLong(0);

ReadLedgerRequest request = ReadLedgerRequest.newBuilder()
        .setAccountId("A-42")
        .setAfterSequence(lastApplied.get())
        .build();

LedgerServiceGrpc.newStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .readLedger(request, new StreamObserver<LedgerEntry>() {
            @Override
            public void onNext(LedgerEntry entry) {
                // applyIdempotently phải hoàn thành và ghi checkpoint bền vững.
                applyIdempotently(entry);
                lastApplied.set(entry.getSequence());
            }

            @Override
            public void onError(Throwable error) {
                Status status = Status.fromThrowable(error);
                System.err.println("Ledger stream failed: " + status);
                System.err.println(
                        "Last successfully applied sequence: " + lastApplied.get());
                // Báo caller đây là kết quả một phần, không phải hoàn tất.
            }

            @Override
            public void onCompleted() {
                System.out.println("Ledger stream completed successfully");
                // Chỉ tại đây mới đánh dấu lần đọc này hoàn tất.
            }
        });
~~~

Ví dụ giả định `channel`, `TimeUnit` và hàm `applyIdempotently(...)` đã được định nghĩa. Với ứng dụng thật, cần đảm bảo cập nhật dữ liệu và checkpoint nhất quán: nếu dữ liệu đã được áp dụng nhưng checkpoint chưa ghi, lần resume có thể gửi lại event; vì thế thao tác áp dụng cần idempotent hoặc cùng transaction với checkpoint.

**Không đặt trạng thái thành công trong `onNext`.** `onNext` chỉ chứng minh callback đã nhận một message. Chỉ `onCompleted` mới biểu thị RPC hoàn thành bình thường. Nếu `onError` xảy ra, client cần giữ trạng thái một phần và báo lỗi cuối cùng cho lớp gọi.

### 6.1. Blocking stub cũng có thể ném lỗi sau vài message

Với blocking stub, response được đọc qua `Iterator<LedgerEntry>`. Nếu server kết thúc bằng status lỗi sau một số message, client có thể lấy các message trước đó, rồi gặp `StatusRuntimeException` khi kiểm tra/đọc phần tiếp theo:

~~~java
var iterator = LedgerServiceGrpc.newBlockingStub(channel)
        .withDeadlineAfter(30, TimeUnit.SECONDS)
        .readLedger(request);

long lastApplied = 0;
try {
    while (iterator.hasNext()) {
        LedgerEntry entry = iterator.next();
        applyIdempotently(entry);
        lastApplied = entry.getSequence();
    }
    markReadCompleted();
} catch (StatusRuntimeException error) {
    System.err.printf("Read failed after sequence %d: %s%n",
            lastApplied, error.getStatus());
    markReadPartial(lastApplied, error.getStatus());
}
~~~

Đoạn code minh họa cần import `StatusRuntimeException`, `TimeUnit` và các hàm ứng dụng. Không đặt `markReadCompleted()` trong vòng lặp: nếu status cuối là lỗi, client không được báo rằng toàn bộ lịch sử đã đọc xong.

## 7. Lỗi của toàn stream hay lỗi của một phần tử?

Đây là một quyết định quan trọng khi thiết kế API. Không phải mọi lỗi khi xử lý một phần tử đều cần làm toàn bộ RPC thất bại.

### 7.1. Lỗi toàn stream

Dùng terminal gRPC status khi server không thể tiếp tục cung cấp kết quả theo hợp đồng:

- Nguồn dữ liệu không còn truy cập được.
- Server mất quyền truy cập vào tài nguyên bắt buộc.
- Snapshot/cursor không còn hợp lệ và không thể tiếp tục.
- Dữ liệu không còn đáng tin cậy để phát các phần tiếp theo.

Ví dụ: ba giao dịch đã phát, nhưng database mất kết nối. Server gọi `onError(UNAVAILABLE)`. Client nhận kết quả một phần và phải quyết định resume, hiển thị hoặc hủy bỏ phần đã nhận theo chính sách nghiệp vụ.

### 7.2. Lỗi của một phần tử nhưng stream vẫn tiếp tục

Nếu mỗi phần tử độc lập và hợp đồng cho phép kết quả từng phần, có thể biểu diễn lỗi ngay trong message. Ví dụ một báo cáo xử lý 100 bản ghi; bản ghi thứ 12 không hợp lệ nhưng 99 bản ghi còn lại vẫn có thể xử lý:

~~~proto
message ItemResult {
  int64 sequence = 1;
  string item_id = 2;
  bool succeeded = 3;
  string error_code = 4;
  string error_message = 5;
}

service BatchService {
  rpc ProcessItems(ProcessItemsRequest) returns (stream ItemResult);
}
~~~

Trong thiết kế này, một `ItemResult` có thể báo `succeeded = false`; server vẫn phát các kết quả khác rồi gọi `onCompleted()` nếu toàn bộ phiên xử lý kết thúc đúng hợp đồng. **Lỗi phần tử là dữ liệu của stream; lỗi toàn stream là status kết thúc RPC.**

Không gửi `onError` cho một lỗi phần tử có thể dự đoán và xử lý độc lập nếu client được kỳ vọng tiếp tục. Ngược lại, không biến lỗi nguồn nghiêm trọng thành một message `succeeded = false` rồi tiếp tục phát dữ liệu thiếu hoặc không nhất quán.

| Câu hỏi | Nếu câu trả lời là “có” | Thiết kế gợi ý |
|---|---|---|
| Các phần tử độc lập, một phần tử lỗi không ảnh hưởng phần còn lại? | Có | Message kết quả cho từng phần tử, sau cùng `onCompleted` |
| Không thể xác định kết quả còn lại sau lỗi nguồn? | Có | Terminal `onError` với status thích hợp |
| Client bắt buộc có toàn bộ tập kết quả mới được sử dụng? | Có | Staging kết quả và chỉ commit khi `onCompleted` |
| Client được phép dùng kết quả đã nhận dù phần còn lại thất bại? | Có | Incremental apply, checkpoint và resume |

## 8. Tiếp tục sau lỗi: sequence và checkpoint

Khi stream lỗi sau khi đã phát một phần dữ liệu, retry lại từ đầu có thể làm client xử lý trùng. Một hợp đồng resume thường dùng sequence:

~~~text
Lần 1:
    Client gửi after_sequence = 0
    Server phát #1, #2, #3
    Server gặp lỗi -> onError(UNAVAILABLE)
    Client chỉ áp dụng bền vững #1, #2

Lần 2:
    Client gửi after_sequence = 2
    Server phát #3, #4, #5, ...
    Server onCompleted()
~~~

Điểm bắt đầu của lần hai là **checkpoint đã lưu**, không phải số sequence server đã tạo hay client vừa nhìn thấy trong callback. Trong ví dụ, #3 có thể được phát lại vì client chưa xác nhận đã áp dụng nó.

### 8.1. Quy tắc checkpoint

1. Nhận event.
2. Kiểm tra sequence và ID.
3. Áp dụng thay đổi nghiệp vụ theo cách idempotent.
4. Ghi checkpoint sau khi thay đổi đã được commit.
5. Chỉ sau đó mới coi sequence là đã áp dụng.

Nếu dữ liệu và checkpoint ở cùng database, có thể cập nhật chúng trong một transaction. Nếu nằm ở hai hệ thống khác nhau, cần chiến lược deduplication/idempotency hoặc outbox/inbox phù hợp; không giả định hai thao tác ghi độc lập luôn thành công cùng lúc.

Ví dụ logic phía client:

~~~java
void applyAndCheckpoint(LedgerEntry entry) {
    transactionTemplate.executeWithoutResult(tx -> {
        if (ledgerStore.wasApplied(entry.getEntryId())) {
            return; // Event được replay; không áp dụng lần hai.
        }

        ledgerStore.apply(entry);
        checkpointStore.save(
                entry.getAccountId(), entry.getSequence());
    });
}
~~~

Đây là pseudocode phụ thuộc vào transaction và repository của ứng dụng. `wasApplied`, `apply` và `save` phải cùng bảo vệ một invariant nhất quán; nếu chỉ lưu checkpoint mà không deduplicate theo ID/sequence, retry có thể tạo side effect lặp.

### 8.2. Server phải bảo đảm chuyển từ lịch sử sang sự kiện mới không bị hở

Với một nguồn event liên tục, server có thể đọc các event lịch sử sau `after_sequence`, rồi subscribe event mới. Nếu thực hiện hai bước không nguyên tử:

~~~text
Đọc lịch sử đến #10
             #11 xuất hiện
Đăng ký subscription
~~~

Event #11 có thể bị bỏ sót giữa hai thao tác. Cách khắc phục tùy hệ thống: dùng offset/consumer của broker, snapshot có watermark, đăng ký trước rồi lọc theo sequence, hoặc cơ chế cursor nhất quán của kho dữ liệu. Sau khi resume, client nên phát hiện gap nếu sequence kỳ vọng là 11 nhưng nhận 12.

**Không có replay miễn phí trong gRPC.** gRPC vận chuyển message trên một RPC; lưu trữ lịch sử, cursor, retention, replay và deduplication là trách nhiệm của ứng dụng hoặc hệ thống event bên dưới.

## 9. Client nên giữ hay bỏ kết quả một phần?

Không có một chính sách đúng cho mọi nghiệp vụ. Hai mô hình thường gặp:

### 9.1. Incremental apply: mỗi response hợp lệ có giá trị độc lập

Ví dụ các giao dịch đã được xác thực và lưu vào sổ cái. Client có thể áp dụng từng event idempotent và ghi checkpoint. Khi stream lỗi, các event đã commit vẫn hợp lệ; lần kết nối sau tiếp tục từ checkpoint.

Ưu điểm:

- Dữ liệu được sử dụng sớm.
- Giảm lượng kết quả phải giữ trong bộ nhớ.
- Có thể tiếp tục từ phần đã lưu.

Yêu cầu:

- Sequence ổn định, ID duy nhất và thao tác idempotent.
- Checkpoint không đi trước dữ liệu đã commit.
- Có cơ chế replay và xử lý gap/duplicate.

### 9.2. Stage then commit: chỉ công bố khi stream hoàn tất

Ví dụ tạo báo cáo tổng hợp cần đủ mọi phần mới có thể công bố. Client ghi các response vào vùng staging tạm, nhưng không đánh dấu báo cáo hoàn tất. Khi nhận `onCompleted`, client xác minh đủ sequence rồi commit/publish. Nếu nhận `onError`, vùng staging được giữ để resume hoặc bỏ theo chính sách.

Ưu điểm:

- Người dùng không thấy một báo cáo thiếu nhưng bị hiểu nhầm là hoàn chỉnh.
- Có thể áp dụng kiểm tra toàn tập trước khi công bố.

Đánh đổi:

- Cần bộ nhớ hoặc lưu trữ staging.
- Cần dọn dữ liệu tạm hết hạn.
- Có thể cần resume thay vì bắt đầu lại từ đầu.

| Đặc điểm | Incremental apply | Stage then commit |
|---|---|---|
| Sử dụng response sớm | Có | Chưa công bố ra ngoài |
| Xử lý lỗi giữa luồng | Giữ phần đã commit, resume | Giữ staging hoặc bỏ |
| Nhu cầu idempotency | Cao | Vẫn cần khi resume |
| Bộ nhớ | Có thể thấp nếu xử lý từng event | Có thể cao nếu staging trong RAM; nên dùng storage |
| Ví dụ | Ledger event, trạng thái độc lập | File tổng hợp, snapshot phải đầy đủ |

## 10. Retry sau lỗi một phần: không retry mù

Một lỗi `UNAVAILABLE` có thể là tạm thời, nhưng không tự động chứng minh retry từ đầu là an toàn. Cần trả lời:

- Request có side effect không, hay chỉ đọc dữ liệu?
- Những response trước lỗi đã được client áp dụng chưa?
- Server có lưu lịch sử theo sequence không?
- Client có checkpoint bền và thao tác idempotent không?
- Cursor còn hiệu lực và dữ liệu lịch sử còn trong retention không?

Nếu request chỉ đọc và có cursor ổn định, client có thể retry từ `after_sequence` cuối cùng đã commit, với backoff và giới hạn số lần. Nếu request khởi chạy tác vụ hoặc tạo side effect, phải dùng idempotency key và kiểm tra trạng thái tác vụ trước khi gọi lại.

**Không nên giả định retry tự động của gRPC sẽ phục hồi một server stream sau khi đã nhận response.** Cơ chế retry của gRPC có các điều kiện commitment và cấu hình riêng; nó không thay thế cursor/checkpoint của ứng dụng. Hãy thiết kế và kiểm thử rõ hành vi reconnect/resume.

## 11. Kiểm thử lỗi sau khi đã phát một phần dữ liệu

Một test quan trọng là server phát hai message rồi kết thúc bằng `UNAVAILABLE`. Client phải đọc được hai message trước khi nhận lỗi terminal. Có thể dùng gRPC **in-process transport** để kiểm tra stub, serialization và status mà không cần mở cổng mạng.

~~~java
import com.example.ledger.rpc.LedgerEntry;
import com.example.ledger.rpc.LedgerServiceGrpc;
import com.example.ledger.rpc.ReadLedgerRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class PartialLedgerStreamTest {

    @Test
    void clientReceivesPartialMessagesThenTerminalError() throws Exception {
        String name = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new LedgerServiceGrpc.LedgerServiceImplBase() {
                    @Override
                    public void readLedger(
                            ReadLedgerRequest request,
                            StreamObserver<LedgerEntry> out) {
                        out.onNext(LedgerEntry.newBuilder()
                                .setAccountId(request.getAccountId())
                                .setSequence(1)
                                .setEntryId("entry-1")
                                .build());
                        out.onNext(LedgerEntry.newBuilder()
                                .setAccountId(request.getAccountId())
                                .setSequence(2)
                                .setEntryId("entry-2")
                                .build());

                        // Giả lập nguồn dữ liệu lỗi sau hai response.
                        out.onError(Status.UNAVAILABLE
                                .withDescription("Source interrupted")
                                .asRuntimeException());
                    }
                })
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();

        try {
            ReadLedgerRequest request = ReadLedgerRequest.newBuilder()
                    .setAccountId("A-42")
                    .setAfterSequence(0)
                    .build();

            var iterator = LedgerServiceGrpc.newBlockingStub(channel)
                    .withDeadlineAfter(5, TimeUnit.SECONDS)
                    .readLedger(request);

            List<Long> received = new ArrayList<>();
            assertEquals(1L, iterator.next().getSequence());
            received.add(1L);
            assertEquals(2L, iterator.next().getSequence());
            received.add(2L);

            StatusRuntimeException error = assertThrows(
                    StatusRuntimeException.class, iterator::hasNext);

            assertEquals(List.of(1L, 2L), received);
            assertEquals(Status.Code.UNAVAILABLE, error.getStatus().getCode());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

Test xác minh **hai response đã nhận trước status lỗi**. Nó không chứng minh ứng dụng đã ghi bền hai response, cũng không mô phỏng đầy đủ sự cố mạng thực. Test tích hợp Spring Boot và test qua transport/proxy thật vẫn cần thiết nếu phải xác minh nguồn dữ liệu, cleanup, TLS và hành vi mất kết nối.

### Các ca kiểm thử cần bổ sung

| Tình huống | Kỳ vọng |
|---|---|
| Lỗi trước response đầu tiên | Client chỉ nhận terminal status lỗi |
| Lỗi sau một hoặc nhiều response | Client giữ phần đã nhận và nhận status lỗi |
| Nguồn kết thúc bình thường | Client nhận đủ response rồi `onCompleted` |
| Lỗi phần tử nhưng stream tiếp tục | Message lỗi phần tử được nhận; RPC có thể kết thúc `OK` |
| Client xử lý message thất bại | Không ghi checkpoint trước khi xử lý thành công |
| Resume từ checkpoint | Không mất event; event phát lại được deduplicate |
| Sequence bị nhảy | Client phát hiện gap và không đánh dấu hoàn tất |
| Server mất kết nối sau `onNext` | Client không giả định message cuối đã được áp dụng |
| Nguồn lỗi khi đóng cursor | RPC không phát `onCompleted` nếu việc đọc/đóng nguồn chưa thành công theo hợp đồng |

## 12. Quan sát lỗi một phần trong môi trường Spring gRPC

Chỉ đếm tổng số RPC lỗi sẽ không cho biết lỗi xảy ra trước hay sau khi có dữ liệu. Nên thu thập một số tín hiệu theo từng method và correlation ID:

| Chỉ số | Mục đích |
|---|---|
| Số response server đã phát trước terminal error | Biết lỗi xảy ra sau bao nhiêu dữ liệu |
| Sequence cuối client đã nhận | Biết phía client quan sát được đến đâu |
| Sequence cuối client đã commit/checkpoint | Xác định điểm resume an toàn |
| Status terminal (`UNAVAILABLE`, `INTERNAL`, ...) | Phân loại nguyên nhân kết thúc |
| Số lần reconnect/resume | Đánh giá độ ổn định của nguồn dữ liệu |
| Duplicate và sequence gap | Phát hiện lỗi replay hoặc chuyển lịch sử-sang-live |
| Thời lượng RPC và thời điểm lỗi | Tìm mẫu lỗi theo thời gian/tải |
| Queue depth và thời gian chờ nguồn | Phân biệt quá tải với lỗi phụ thuộc |

Trong Spring gRPC, interceptor và hệ thống tracing/metrics có thể ghi method, thời lượng và status. Để phân tích dữ liệu một phần, ứng dụng cần ghi sequence/cursor ở cấp nghiệp vụ. Không ghi access token, payload nhạy cảm hoặc exception chứa thông tin nội bộ vào metadata/log công khai.

Status `UNAVAILABLE` thường gợi ý một phụ thuộc tạm thời không khả dụng; `INTERNAL` có thể cho thấy lỗi bất ngờ của server. Tuy nhiên, không nên suy luận chỉ từ status. Cần đối chiếu log nguồn dữ liệu, thời điểm server phát message, client callback và checkpoint.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi `onCompleted()` sau khi nguồn dữ liệu ném lỗi | Client tưởng stream đầy đủ | Kết thúc bằng một `onError` phù hợp |
| Client đánh dấu thành công ngay ở `onNext` | Kết quả thiếu có thể bị công bố | Chỉ đánh dấu RPC hoàn tất ở `onCompleted` |
| Bỏ toàn bộ message đã nhận khi có `onError` | Mất phần dữ liệu có thể đã xử lý hợp lệ | Chọn incremental apply hoặc staging theo nghiệp vụ |
| Retry lại từ đầu mà không deduplicate | Side effect hoặc bản ghi bị lặp | Checkpoint, cursor và idempotency |
| Dùng sequence chỉ tăng trong RAM của một server instance | Reconnect sang instance khác không khớp thứ tự | Sequence ổn định từ nguồn dữ liệu dùng chung |
| Trả stack trace/SQL trong status description | Rò rỉ thông tin nội bộ | Status mô tả an toàn; log chi tiết nội bộ |
| Coi lỗi của một item là lỗi toàn stream | Mất các item độc lập còn xử lý được | Biểu diễn kết quả từng item trong message |
| Coi lỗi toàn nguồn là lỗi một item | Tiếp tục phát dữ liệu không đầy đủ | Dùng terminal status khi không thể đáp ứng hợp đồng |
| Chỉ theo dõi số response server đã gửi | Không biết client đã nhận/áp dụng đến đâu | Theo dõi cả received sequence và committed checkpoint |

### Câu hỏi tự kiểm tra

1. Server đã gọi ba lần `onNext` rồi gọi `onError(UNAVAILABLE)`. Client có được đánh dấu toàn bộ RPC thành công không?
2. Vì sao số response server đã phát có thể lớn hơn số response client đã xử lý bền vững?
3. Khi nào lỗi của một phần tử nên nằm trong payload thay vì kết thúc toàn stream?
4. Client nên gửi `after_sequence` bằng sequence cuối đã nhận hay sequence cuối đã commit? Vì sao?
5. Nếu client áp dụng event rồi crash trước khi lưu checkpoint, điều gì có thể xảy ra khi resume?
6. Vì sao gRPC không tự bảo đảm exactly-once processing sau khi stream lỗi?
7. Server cần bảo đảm điều gì khi chuyển từ đọc lịch sử sang nhận event mới để không bỏ sót sequence?

**Ghi nhớ:** Lỗi sau khi đã phát một phần dữ liệu làm RPC kết thúc thất bại, nhưng không xóa những response client đã nhận hoặc side effect đã commit. Server phải dùng terminal status đúng và không gọi `onCompleted` sau lỗi. Client cần phân biệt dữ liệu đã nhận với dữ liệu đã áp dụng, lưu checkpoint an toàn, và chỉ resume khi có sequence/cursor cùng nguồn dữ liệu có thể phát lại. Đây là nền tảng để xử lý kết quả một phần có kiểm soát trong server streaming của Spring gRPC.
