# Schema message giữa các phiên bản trong Spring Batch phân tán

## 1. Vì sao schema message là vấn đề tương thích phiên bản?

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, Spring Batch được mở rộng cho workload lớn bằng multi-threaded step, parallel steps, partitioning, remote chunking và các mô hình phân tán. Khi nhiều instance cùng tham gia xử lý một job, một lần nâng cấp thường không thay toàn bộ manager và worker tại cùng một thời điểm: worker phiên bản cũ có thể vẫn nhận message mới, hoặc manager mới phải nhận response do worker cũ tạo ra.

**Schema message** là hợp đồng mô tả cấu trúc và ý nghĩa của thông điệp truyền giữa các thành phần, bao gồm tên trường, kiểu dữ liệu, tính bắt buộc, giá trị mặc định, định danh nghiệp vụ, phiên bản và quy tắc xử lý. **Schema evolution** là cách thay đổi hợp đồng qua các bản phát hành sao cho hệ thống vẫn đọc và xử lý đúng thông điệp đã được tạo ở phiên bản khác.

Ví dụ: worker v1 chỉ biết `itemIds`, còn manager v2 bắt đầu gửi thêm `priority`. Nếu worker v1 từ chối mọi trường lạ, việc bổ sung một trường tưởng như vô hại cũng khiến toàn bộ chunk thất bại. Ngược lại, nếu worker v2 bắt buộc nhận `priority` nhưng message do manager v1 không có trường này, worker mới không xử lý được các message cũ còn trong queue.

Các rủi ro thường gặp:

- **Rolling deployment:** manager và worker chạy lệch version trong thời gian chuyển đổi.
- **Message tồn đọng:** broker giữ thông điệp từ bản phát hành cũ; worker mới khởi động phải đọc được.
- **Retry/redelivery:** cùng một message được giao lại sau timeout, crash hoặc broker reconnect.
- **Restart job:** `JobExecution`/`StepExecution` hoặc `ExecutionContext` đã tồn tại trước khi nâng cấp.
- **Rollback:** triển khai phiên bản mới thất bại và phải khôi phục worker/manager cũ nhưng queue đã có message theo schema mới.
- **Thay đổi nghĩa dữ liệu:** dù parser đọc thành công, giá trị có thể được hiểu sai, như chuyển `amount` từ đơn vị xu sang đơn vị đồng.

Kết quả mong muốn là **tương thích ở ba lớp**: giải mã được message, hiểu cùng ngữ nghĩa nghiệp vụ, và duy trì tính đúng đắn của xử lý phân tán (không xử lý trùng, không bỏ sót, restart được).

## 2. Đâu là hợp đồng truyền tin trong các kiểu mở rộng Spring Batch?

Phải xác định rõ **biên giao tiếp** trước khi thiết kế schema. Spring Batch cung cấp các cơ chế phân tán, nhưng serializer, transport, policy phiên bản và quy tắc quản trị message vẫn cần được xác nhận theo cấu hình thực tế.

| Mô hình | Thông tin thường đi qua biên truyền tin | Điểm cần bảo toàn khi thay schema |
|---|---|---|
| Multi-threaded step | Chủ yếu chia sẻ object trong một JVM; thường không có message qua broker | Thread safety, kiểu object chia sẻ, trạng thái reader/writer; schema broker không phải mối quan tâm chính |
| Parallel steps trong một tiến trình | Luồng thực thi và `JobRepository` nội bộ | Sự tương thích của metadata, `ExecutionContext`, dữ liệu trung gian |
| Remote partitioning | Manager giao tham chiếu partition/step cho worker; worker tra metadata/`ExecutionContext` từ `JobRepository` dùng chung | `jobExecutionId`, `stepExecutionId`, step name, partition identity, trạng thái và khả năng worker đọc dữ liệu persisted |
| Remote chunking | Manager đọc item, gửi request mang chunk hoặc tham chiếu item; worker trả response/tổng hợp kết quả | Kiểu item, thứ tự/định danh chunk, correlation, số lần thử, response và xử lý trùng |
| Remote step execution (các phiên bản Spring Batch hỗ trợ) | Yêu cầu thực thi step ở worker từ manager qua messaging | Tên remote step, identity execution, mapping request/response và tương thích framework |

Ở **remote partitioning**, request của framework có thể là một `StepExecutionRequest` chứa tham chiếu, còn ranh giới phân vùng như `fromId`/`toId` thường nằm trong `ExecutionContext` đã lưu ở `JobRepository`. Không mặc định mọi thông số partition đều được nhúng vào payload broker.

Ở **remote chunking**, framework có các kiểu `ChunkRequest<T>` và `ChunkResponse`, trong đó phần tử `T` phải được serialize/deserialize phù hợp. Nếu ứng dụng tự thiết kế envelope chứa `itemIds` và để worker đọc bản ghi từ nguồn dữ liệu, đây là lựa chọn kiến trúc riêng, không phải cấu trúc mặc định của mọi `ChunkRequest<T>`.

**Ranh giới cần tách biệt:**

1. **Wire contract:** nội dung message trên broker giữa manager và worker.
2. **Business data contract:** cấu trúc item, mã trạng thái, đơn vị đo và ý nghĩa trường.
3. **Persisted state contract:** dữ liệu trong `JobRepository`, `ExecutionContext`, checkpoint và trạng thái phục vụ restart.

Nâng cấp schema message không tự bảo đảm tương thích database metadata hay serializer của `ExecutionContext`. Khi nâng Spring Batch, Spring Framework, Spring Integration hoặc thư viện serialization, phải kiểm tra cả ba ranh giới này.

## 3. Phân biệt backward, forward và full compatibility

Quy ước: `W1`/`W2` là writer (bên tạo message) ở schema v1/v2; `R1`/`R2` là reader (bên nhận message).

| Chế độ | Cặp đọc phải thành công | Ví dụ yêu cầu |
|---|---|---|
| **Backward compatibility** | `R2 ← W1` | Worker mới đọc được message cũ còn trong queue |
| **Forward compatibility** | `R1 ← W2` | Worker cũ đọc được message mới trong rolling deployment |
| **Full compatibility** | Cả `R2 ← W1` và `R1 ← W2` | Trộn manager/worker cũ–mới trong cùng một giai đoạn triển khai |
| **Transitive compatibility** | So với **toàn bộ** các schema lịch sử còn hỗ trợ, thay vì chỉ bản ngay trước | Worker mới phải đọc message từ v1, v2 và v3 nếu queue/replay có thể giữ cả ba |

Đây là định nghĩa về **khả năng đọc hợp đồng**; chính sách trên từng schema registry có thể có tên/cấu hình riêng. **Đọc parse thành công chưa đủ**: worker phải hiểu giá trị đúng nghĩa, giữ nguyên quy tắc kiểm tra idempotency và xử lý response hợp lệ.

Ví dụ với JSON message:

**Schema v1 — manager gửi:**

~~~json
{
  "messageType": "BATCH_CHUNK_REQUEST",
  "schemaMajor": 1,
  "schemaMinor": 0,
  "messageId": "req-521",
  "jobExecutionId": 314,
  "stepExecutionId": 728,
  "chunkSequence": 12,
  "payload": {
    "itemIds": ["order-11", "order-12"]
  }
}
~~~

**Schema v1.1 — chỉ thêm một trường tùy chọn:**

~~~json
{
  "messageType": "BATCH_CHUNK_REQUEST",
  "schemaMajor": 1,
  "schemaMinor": 1,
  "messageId": "req-522",
  "jobExecutionId": 314,
  "stepExecutionId": 728,
  "chunkSequence": 13,
  "payload": {
    "itemIds": ["order-13", "order-14"],
    "priority": "NORMAL"
  }
}
~~~

Muốn v1.1 tương thích hai chiều, cần có hai điều kiện được **kiểm thử**, không chỉ ghi trong tài liệu:

- Worker cũ **cho phép trường không biết** như `priority` và vẫn xử lý đúng các trường v1; nếu parser bật chế độ từ chối trường lạ, forward compatibility không đạt.
- Worker mới **có giá trị mặc định** `priority = NORMAL` khi đọc message v1; nếu thêm trường bắt buộc không có default, backward compatibility không đạt.

Nếu v1.1 thay `itemIds` thành `items` hoặc đổi ý nghĩa `chunkSequence` thì đó có thể là thay đổi phá vỡ hợp đồng ngay cả khi dữ liệu vẫn là JSON hợp lệ.

## 4. Định nghĩa message envelope ổn định

Khi tự quản lý wire contract, tách **envelope** phục vụ điều phối/truy vết khỏi **payload** nghiệp vụ. Mẫu dưới đây chỉ là **hợp đồng do ứng dụng tự định nghĩa**, không phải cấu trúc cố định của class message nội bộ Spring Batch.

~~~json
{
  "messageType": "BATCH_CHUNK_REQUEST",
  "schemaMajor": 1,
  "schemaMinor": 2,
  "schemaId": "batch.chunk.request/1.2",
  "messageId": "f8b15644-3e7d-41fb-9b15-8da3ee4c6b18",
  "correlationId": "job-314-step-728",
  "producedAt": "2026-11-26T03:20:00Z",
  "producerRelease": "manager-2026.11.1",
  "tenantId": "tenant-a",
  "jobExecutionId": 314,
  "stepExecutionId": 728,
  "chunkSequence": 12,
  "attempt": 1,
  "payload": {
    "itemIds": ["order-11", "order-12"],
    "priority": "NORMAL"
  }
}
~~~

| Trường | Tác dụng | Quy ước |
|---|---|---|
| `messageType` | Phân biệt request/response, partition, control event | Giá trị enum/documented; không suy từ tên topic đơn thuần |
| `schemaMajor` / `schemaMinor` | Xác định version của **hợp đồng**, độc lập version ứng dụng | Major thay khi phá vỡ compatibility; minor thay khi mở rộng tương thích |
| `schemaId` | Tra schema chính xác trong registry hoặc bộ schema được phân phối | Không tin schemaId chưa kiểm chứng do client gửi |
| `messageId` | Định danh bản message để log, deduplicate theo chính sách | Bền vững qua **redelivery cùng message** |
| `correlationId` | Ghép request với response và trace | Giữ thống nhất ở manager, worker và consumer |
| `jobExecutionId` / `stepExecutionId` | Gắn message với thực thi trong `JobRepository` | Xác thực phạm vi, không tin ID lạ từ bên ngoài |
| `chunkSequence` / partition key | Chỉ định đơn vị xử lý trong một execution | Phải đủ phân biệt và ổn định khi retry |
| `attempt` | Mô tả lần phát/tiếp nhận lại theo quy ước ứng dụng | Không dùng riêng `attempt` làm idempotency key |
| `producedAt` | Thời điểm phát message | ISO-8601 UTC; không dùng làm cơ chế ordering duy nhất |
| `tenantId` | Phân định dữ liệu khi đa tenant | Kiểm tra lại theo context server tin cậy |
| `payload` | Dữ liệu thực thi | Versioned theo messageType; giới hạn kích thước và loại dữ liệu |

Nếu transport đã có headers như message ID, trace, content-type hay schema ID, vẫn phải xác định header nào **được bảo toàn qua mọi broker, dead-letter queue và replay tool**. Một số bridge hoặc quá trình xuất/nhập message có thể không giữ nguyên headers; hợp đồng nên quy định rõ vị trí thông tin tối thiểu để giải mã.

**Không nhầm** `schemaMajor` với major version của Spring Batch hay số thứ tự triển khai. Một ứng dụng v4 có thể tiếp tục ghi schema v1 miễn hợp đồng v1 vẫn đáp ứng yêu cầu nghiệp vụ.

### 4.1. Phân biệt request và response

Cùng một pipeline thường có **hai contract độc lập**:

~~~text
Manager -- BATCH_CHUNK_REQUEST/v1 --> Worker
Manager <-- BATCH_CHUNK_RESPONSE/v1 -- Worker

     messageId(request) ---+
     correlationId --------+--> response.correlationId
     job/step/chunk identity +--> xác nhận đúng đơn vị công việc
~~~

Request có thể mở rộng một trường tùy chọn mà không ảnh hưởng response; tuy nhiên rolling deploy vẫn thất bại nếu manager mới chỉ đọc response v2 còn worker cũ chỉ trả response v1. Hãy version từng `messageType` và kiểm tra cả chiều đi lẫn chiều về.

Với response, đặt rõ `result` (ví dụ `SUCCEEDED`, `RETRYABLE_FAILURE`, `PERMANENT_FAILURE`) và số lượng item đã thực sự commit; không đánh đồng ack của broker với thành công của step. Mã kết quả mới phải có chính sách đối với reader cũ: nếu reader cũ không biết enum, nó cần từ chối an toàn và phát cảnh báo, không mặc định “thành công”.

## 5. Quy tắc đổi schema: thay đổi nào an toàn?

| Thay đổi | Khả năng tương thích | Điều kiện và rủi ro |
|---|---|---|
| Thêm trường tùy chọn, có default | Thường có thể backward compatible | Reader mới phải xử lý khi thiếu; reader cũ phải bỏ qua trường lạ nếu cần forward |
| Thêm trường bắt buộc không default | Thường phá backward compatibility | Message cũ không có giá trị để reader mới xử lý |
| Xóa trường reader cũ cần | Phá forward compatibility | Reader cũ không có trường bắt buộc |
| Đổi tên trường | Có thể phá vỡ cả hai chiều | Cần alias/upcaster hoặc giữ tên cũ trong giai đoạn chuyển đổi |
| Đổi kiểu `string → integer` | Thường là breaking change | Ngay cả khi giá trị nhìn giống số |
| Đổi đơn vị tiền tệ, timezone hoặc ý nghĩa trạng thái | **Breaking semantic change** | Parser vẫn thành công nhưng dữ liệu có thể bị xử lý sai |
| Thêm giá trị enum | Phụ thuộc cách reader xử lý giá trị chưa biết | Không tự ánh xạ enum lạ sang `SUCCESS` hoặc kết quả an toàn giả |
| Thay định dạng ID hoặc quy tắc thứ tự chunk | Có thể phá tương thích/idempotency | Ảnh hưởng correlation, dedup và restart |
| Đổi codec/serializer/encoding | Có thể phá toàn bộ wire contract | Cần content-type, negotiated version hoặc dual reader |
| Đổi nội dung mặc định `null`/missing thành giá trị khác | Có thể phá ngữ nghĩa | Phải làm rõ “không có”, “chưa xác định” và “0” |

**Schema syntax không thể phát hiện mọi thay đổi nguy hiểm.** Registry có thể chấp nhận một thay đổi cùng kiểu chuỗi, nhưng chuyển `currency = "USD"` từ ký hiệu tiền sang đơn vị quy đổi nội bộ vẫn phá nghĩa dữ liệu.

Một chiến lược hỗ trợ v1 và v2 khi thay đổi phá vỡ:

1. **Expand:** reader mới nhận cả tên cũ và tên mới, chuẩn hóa về model nội bộ; producer vẫn phát schema cũ.
2. **Migrate:** triển khai đủ worker hiểu schema mới, producer bắt đầu gửi schema mới có giám sát.
3. **Contract:** chỉ bỏ reader/schema cũ khi queue cũ đã hết, replay window khép lại, các job còn có thể restart đã được đánh giá và rollback window kết thúc.

Không rút ngắn giai đoạn cuối chỉ vì metrics queue đang bằng 0; một hệ thống có thể còn message trong dead-letter queue, kho lưu sự kiện hoặc bản snapshot phục vụ replay.

## 6. Chọn định dạng: JSON Schema, Avro, Protobuf

Không có định dạng nào tự bảo đảm compatibility. Quy tắc vận hành, chính sách parser/registry và schema evolution mới quyết định kết quả.

| Định dạng | Điểm mạnh | Ràng buộc quan trọng |
|---|---|---|
| JSON + JSON Schema | Dễ đọc trong log, debug trực tiếp, tích hợp phổ biến | Cần validation; parser có thể từ chối unknown properties; payload lớn hơn |
| Apache Avro | Binary gọn; cơ chế writer/reader schema resolution; dùng registry thuận tiện | Phải biết writer schema; thêm field reader mới đọc dữ liệu cũ cần default thích hợp |
| Protocol Buffers | Binary gọn; field number ổn định; codegen đa ngôn ngữ | Không đổi/tái sử dụng field number; phải reserve khi xóa; cần quan tâm field presence, enum lạ và JSON mapping |
| Java native object serialization | Có thể tiện trong nội bộ cùng runtime | Dễ phụ thuộc class/`serialVersionUID`/classpath, khó nâng cấp độc lập và rủi ro bảo mật; tránh làm hợp đồng mạng lâu dài |

### 6.1. Ví dụ Avro: thêm field có default

Schema v1:

~~~json
{
  "type": "record",
  "name": "ChunkTask",
  "namespace": "example.batch.contract",
  "fields": [
    {"name": "messageId", "type": "string"},
    {"name": "itemIds", "type": {"type": "array", "items": "string"}}
  ]
}
~~~

Schema v2:

~~~json
{
  "type": "record",
  "name": "ChunkTask",
  "namespace": "example.batch.contract",
  "fields": [
    {"name": "messageId", "type": "string"},
    {"name": "itemIds", "type": {"type": "array", "items": "string"}},
    {"name": "priority", "type": "string", "default": "NORMAL"}
  ]
}
~~~

Khi **reader v2** đọc bản ghi do **writer v1** tạo, default của `priority` được sử dụng vì writer không có trường này. Khi **reader v1** đọc writer v2, thuật toán resolution cho phép bỏ qua trường không tồn tại trong reader schema. Điều kiện là bộ đọc có đúng writer schema để giải mã và phần còn lại của contract vẫn tương thích. **Default trong Avro chủ yếu phục vụ lúc reader đọc trường mà writer thiếu; nó không tự biến trường thành tùy chọn lúc producer tạo dữ liệu.**

### 6.2. Ví dụ Protobuf: giữ field number

~~~protobuf
syntax = "proto3";

message ChunkTask {
  string message_id = 1;
  repeated string item_ids = 2;
  // v2 thêm một trường tùy chọn về mặt nghiệp vụ.
  string priority = 3;

  // Một field đã xóa ở schema lịch sử:
  reserved 4;
  reserved "legacy_note";
}
~~~

Nếu một schema cũ từng dùng tag số 4 cho `legacy_note`, không tái sử dụng số đó cho field khác. Với `proto3`, scalar không có presence rõ ràng trong một số cách khai báo; khi cần phân biệt “không truyền” với chuỗi rỗng, phải thiết kế presence phù hợp (ví dụ `optional` hoặc wrapper). Đồng thời kiểm tra cách hệ thống chuyển protobuf sang JSON vì hành vi với unknown fields không nhất thiết giống binary protobuf.

Nguồn tham khảo chính thức: [Apache Avro Specification](https://avro.apache.org/docs/1.12.0/specification/), [Protocol Buffers Language Guide](https://protobuf.dev/programming-guides/editions/).

## 7. Upcaster/adapter để chuẩn hóa nhiều schema

Khi business logic phải hỗ trợ dữ liệu cũ, nên chuyển payload lịch sử về một **model nội bộ hiện hành** trước khi gọi `ItemProcessor`/`ItemWriter`. Tránh rải logic “nếu v1, nếu v2” xuyên các bước xử lý.

~~~mermaid
flowchart LR
    A[Manager v1 hoặc v2] --> B[Broker: envelope + payload]
    B --> C[Validate envelope, schema ID và scope]
    C --> D{Version hỗ trợ?}
    D -- v1 --> E[Decoder v1 + upcast]
    D -- v2 --> F[Decoder v2]
    D -- Không --> G[Quarantine / DLQ]
    E --> H[Canonical ChunkTask]
    F --> H
    H --> I[Idempotency check]
    I --> J[ItemProcessor / ItemWriter]
    J --> K[Response contract]
~~~

Ví dụ Java thuần minh họa **chuyển model v1 sang v2**; đây là lớp adapter sau deserialize, độc lập thư viện JSON/Avro cụ thể:

~~~java
import java.util.List;
import java.util.Objects;

record ChunkTaskV1(
        String messageId,
        long jobExecutionId,
        long stepExecutionId,
        long chunkSequence,
        List<String> itemIds
) {}

record ChunkTaskV2(
        String messageId,
        long jobExecutionId,
        long stepExecutionId,
        long chunkSequence,
        List<String> itemIds,
        String priority
) {}

final class ChunkContractUpcaster {
    private ChunkContractUpcaster() {}

    static ChunkTaskV2 fromV1(ChunkTaskV1 old) {
        Objects.requireNonNull(old, "old");
        return new ChunkTaskV2(
                old.messageId(),
                old.jobExecutionId(),
                old.stepExecutionId(),
                old.chunkSequence(),
                List.copyOf(old.itemIds()),
                "NORMAL" // Giá trị v2 tương đương hành vi mặc định ở v1.
        );
    }
}
~~~

Phần giải mã cần chọn đúng decoder **trước khi** tạo `ChunkTaskV1` hoặc `ChunkTaskV2`, kiểm tra giới hạn payload/độ dài chuỗi, validate enum và trường bắt buộc, rồi trả mã lỗi có phân loại. Nếu thiếu `schemaMajor`, chỉ nên dùng fallback cho một legacy format **đã xác định rõ**, không tự phỏng đoán theo vài tên field giống nhau.

**Giới hạn hỗ trợ:** mỗi phiên bản legacy cần thời hạn loại bỏ, test fixture và số lượng message tồn thực tế. Nếu tiếp tục hỗ trợ vô hạn, worker ngày càng phức tạp, nhất là khi có thay đổi semantic.

## 8. Hợp đồng giữa các phiên bản với Spring Batch runtime

### 8.1. Remote partitioning

Trong cơ chế dùng `StepExecutionRequest`/`StepExecutionRequestHandler`, worker phải hiểu được request, nhận diện step bằng tên, tra execution trong `JobRepository` mà manager/worker dùng chung và thực thi với `ExecutionContext` hợp lệ.

Nếu đổi tên step, thay kiểu giá trị trong `ExecutionContext` hoặc thay serializer giữa các bản phát hành, worker mới có thể nhận request hợp lệ nhưng không khôi phục hoặc chạy đúng partition. Các thay đổi sau đòi hỏi đánh giá riêng:

- Rename `stepName` khiến worker cũ hoặc mới không tìm được step tương ứng.
- Thay `ExecutionContext["rangeStart"]` từ `Long` sang chuỗi hoặc đổi từ inclusive sang exclusive.
- Thay class/domain DTO được lưu trong execution context khi serializer còn phụ thuộc class cũ.
- Thay cấu trúc/bảng metadata của `JobRepository` làm hai app version không thể cùng truy cập database hợp lệ.

Một biện pháp ổn định là lưu trong `ExecutionContext` những giá trị đơn giản và có schema/semantics rõ ràng (chuỗi, số, mốc offset, cursor…), version hóa key theo quy ước, tránh đặt Java object tùy ý vào dữ liệu phục vụ restart.

### 8.2. Remote chunking

Request thường chứa các item hoặc tham chiếu cần xử lý; response chứa kết quả thực hiện chunk. Khi nâng cấp, cả request và response phải tương thích. Nếu item lớn hoặc có thay đổi domain phức tạp, cân nhắc gửi **ID/memento** rồi worker tra dữ liệu theo nguồn tin cậy, để giảm phụ thuộc trực tiếp vào object serialization và kích thước broker; cách này đánh đổi bằng chi phí truy vấn và yêu cầu consistency nguồn dữ liệu.

Chọn identity xử lý, ví dụ:

~~~text
workUnitKey = (jobExecutionId, stepExecutionId, chunkSequence)
messageId   = định danh vật lý của request được broker giao lại
businessKey = khóa nghiệp vụ dùng để bảo vệ side effect khi retry/restart
~~~

`workUnitKey` hữu ích để chống thực thi lặp cùng chunk trong một execution, nhưng khi **restart** tạo execution mới thì `jobExecutionId`/`stepExecutionId` có thể khác. Nếu cùng dữ liệu nghiệp vụ được gửi lại, dedup chỉ theo workUnitKey sẽ không đủ. `businessKey` và transaction boundary cần được thiết kế theo yêu cầu xử lý chính xác của hệ thống.

Một response của worker cũ phải được manager mới diễn giải đúng kể cả khi response thiếu metric/trường bổ sung. Không giả định ack của broker chứng minh dữ liệu đã commit; cần xác định cách worker commit, ghi response và thực hiện retry.

### 8.3. Remote step execution

Các API như `RemoteStep` được bổ sung trong dòng Spring Batch 6; availability, cấu hình messaging và contract phụ thuộc version triển khai. Không tự suy đoán hệ thống Spring Batch 5 có API này, và không xem khả năng tương thích của class runtime là cam kết tương thích wire format. Khi dùng Spring Integration, cần kiểm tra serializer/converter ở adapter giữa channel và transport cụ thể.

### 8.4. Tránh serialize trực tiếp object nội bộ qua broker

Không thiết kế giao thức lâu dài chỉ bằng cách đẩy `StepExecution`, `ExecutionContext` hoặc DTO Java tự do qua Java native serialization. Các object nội bộ có thể đổi shape, class name hoặc serialization strategy khi nâng thư viện; deserialize dữ liệu không tin cậy còn có rủi ro bảo mật.

Nếu cơ chế framework đang truyền class nội bộ, hãy **xác minh version matrix Spring Batch/Spring Integration và converter** cho cấu hình đó, triển khai đồng bộ các thành phần nếu không có compatibility guarantee, hoặc tạo adapter wire contract do ứng dụng sở hữu. Không thay serializer của message framework tùy tiện nếu chưa chứng minh request/response sau chuyển đổi vẫn tương thích với handler tương ứng.

## 9. Chiến lược rolling deployment và rollback

Để triển khai thay đổi additive v1 → v1.1, một trình tự an toàn thường là:

1. **Chuẩn bị contract:** đăng ký schema v1.1; kiểm tra backward/forward và các fixture message v1 được lưu trong kho test.
2. **Mở rộng reader:** phát hành worker đọc được v1 và v1.1 nhưng manager **vẫn ghi v1**. Đồng thời chuẩn bị manager đọc được response v1 và v1.1.
3. **Xác nhận toàn bộ người tiêu thụ:** kiểm tra fleet worker, scheduler và replay consumer có hỗ trợ v1.1; đặc biệt phải tính đến worker autoscale từ image cũ.
4. **Chuyển writer:** manager bắt đầu gửi v1.1 có thể kiểm soát (cấu hình/feature flag), theo dõi tỷ lệ decode error, message lỗi, retry và job throughput.
5. **Theo dõi rollback window:** giữ khả năng đọc message mới khi rollback worker; nếu không thể, cần ngừng phát schema mới, drain/cách ly message hoặc dùng adapter tương thích.
6. **Thu hẹp hỗ trợ:** sau khi mọi message cũ, DLQ/replay và execution có thể restart được xử lý, lên kế hoạch bỏ v1 theo change control.

Với thay đổi **breaking v2**, cần đổi tuyến tiêu thụ hoặc thiết lập cặp reader/writer riêng. Một chiến lược là topic mới `batch.chunk.request.v2`, worker v2 subscribe riêng, và dual-reader/translator khi cần. Không cho worker v1 và v2 cùng nhận message v2 trong một consumer group nếu worker v1 không hiểu contract đó.

~~~mermaid
flowchart TD
    A[Manager chỉ ghi schema v1] --> B[Deploy worker dual-read v1/v2]
    B --> C[Kiểm thử fleet và reply reader]
    C --> D[Manager bắt đầu ghi v2 từng phần]
    D --> E{Decode error / business mismatch?}
    E -- Có --> F[Dừng phát v2 và đối soát message đã gửi]
    E -- Không --> G[Ổn định, drain queue/DLQ và rà soát restart]
    F --> C
    G --> H[Ngừng hỗ trợ v1 khi đủ điều kiện]
~~~

**Lưu ý:** sơ đồ trên áp dụng khi dual-read đã giải quyết thay đổi giữa v1/v2. Nếu v2 phá ngữ nghĩa hoặc không thể upcast, phải dùng adapter/route riêng hoặc nâng cấp phối hợp, thay vì tự giả định có thể dùng chung queue.

Một ma trận phiên bản làm chuẩn release:

| Manager | Worker | Request | Response | Kết luận |
|---|---|---|---|---|
| M1 | W1 | v1 | v1 | Baseline |
| M1 | W2 | v1 | v1 hoặc v1.1 | Pass nếu W2 đọc v1 và M1 đọc được response thực |
| M2 | W1 | v1.1 | v1 | Pass **chỉ khi** W1 chịu được request v1.1 |
| M2 | W2 | v1.1 | v1.1 | Pass nếu các schema và business semantics tương thích |

Ma trận chỉ là mục tiêu kiểm tra, **không tự mang trạng thái PASS** cho mọi hệ thống. Nếu M1 không đọc response v1.1, bắt buộc worker W2 tiếp tục ghi response v1 hoặc deploy M1 dual-read trước.

## 10. Retry, idempotency và message không hỗ trợ schema

Môi trường phân tán có thể giao lại message nhiều lần. Một worker đọc được schema v2 nhưng không bảo vệ side effect vẫn có thể ghi trùng dữ liệu khi broker retry.

Quy trình nhận message nên tách rõ:

1. **Xác thực nguồn và validate envelope:** kiểm tra quyền producer, `messageType`, `schemaId`, `schemaMajor`, giới hạn payload và identity execution.
2. **Kiểm tra version và deserialize:** từ chối version không hỗ trợ; phân loại malformed hoặc schema mismatch.
3. **Chuẩn hóa payload:** upcast schema cũ về model nội bộ, kiểm tra ràng buộc business.
4. **Kiểm tra duplicate:** dùng inbox/ledger hoặc unique constraint gắn với công việc cần làm; xác định retry của cùng work unit.
5. **Thực thi và commit:** ràng buộc side effect, transaction và cập nhật dấu vết xử lý theo mô hình nhất quán.
6. **Gửi response/ack:** dựa trên kết quả commit thực; sử dụng outbox hoặc reconciliation khi broker và database không có transaction chung.

Ví dụ ledger tối thiểu (PostgreSQL) dùng cho message dedup; schema ứng dụng phải bổ sung trạng thái, transaction và TTL theo nhu cầu:

~~~sql
CREATE TABLE batch_message_inbox (
    consumer_name   VARCHAR(100) NOT NULL,
    message_id      VARCHAR(128) NOT NULL,
    job_execution_id BIGINT NOT NULL,
    step_execution_id BIGINT NOT NULL,
    schema_major    INTEGER NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    processing_status VARCHAR(32) NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Khóa trên chỉ chống xử lý lại **cùng messageId**; nó chưa bảo vệ khi producer tạo messageId mới cho cùng chunk hoặc khi restart phát lại cùng dữ liệu. Cần unique key bổ sung trên work unit và cơ chế idempotency nghiệp vụ nếu side effect phải chống trùng.

| Tình huống lỗi | Cách xử lý | Điều cần tránh |
|---|---|---|
| Không đọc được schema major | Quarantine/DLQ, ghi metadata an toàn, cảnh báo và cho phép replay khi có decoder | Retry vô hạn cùng worker không hỗ trợ |
| Schema hợp lệ nhưng thiếu trường bắt buộc | Đánh dấu contract violation, DLQ, trả lỗi phù hợp | Tự đoán giá trị khiến xử lý sai dữ liệu |
| DB/broker tạm thời mất kết nối | Retry giới hạn + backoff, kiểm tra idempotency | Gửi lại side effect không kiểm soát |
| Response trễ từ execution cũ | Correlation và trạng thái execution để quyết định áp dụng/bỏ qua an toàn | Gộp response vào execution đang hoạt động khác |
| Parser chấp nhận nhưng business semantics đổi | Reject/quarantine theo rule nghiệp vụ, điều tra contract | Đánh dấu chunk `COMPLETED` khi dữ liệu có thể sai |
| Rollback code, queue còn v2 | Duy trì decoder v2 hoặc tách topic/translator | Xóa DLQ để giảm cảnh báo |

Một `DLQ` là vùng chờ xử lý có kiểm soát, không phải chỗ bỏ vĩnh viễn. Lưu `messageId`, version, reasonCode, time, correlation và tham chiếu payload phù hợp chính sách bảo mật; khi replay, giữ identity/dedup semantics và tránh tái tạo message gây xử lý hai lần. Nên có hạn mức retry và quy trình triage rõ ràng cho poison message.

## 11. Kiểm thử tương thích tự động và quan sát thực tế

### 11.1. Contract tests cần chạy ở CI

Kiểm tra tối thiểu mọi messageType được gửi/nhận trong hệ thống:

- **Golden messages:** lưu một tập message v1, v1.1, v2 đã phát sinh thực tế (được làm sạch dữ liệu nhạy cảm); reader mới phải đọc được các bản còn hỗ trợ.
- **Writer-reader matrix:** test `R1(W1)`, `R2(W1)`, `R1(W2)` và `R2(W2)` theo cam kết tương thích đã chọn. Với request-response, chạy cả hai chiều.
- **Negative tests:** trường bị thiếu, field khác kiểu, enum không biết, giá trị ngoài miền, JSON/protobuf/Avro không hợp lệ, unsupported major, message vượt kích thước.
- **Business semantic tests:** v1 thiếu `priority` vẫn mang nghĩa `NORMAL`; đổi `amount` phải có conversion chính xác; tên step/partition key không làm đổi phạm vi công việc.
- **Integration tests:** worker cũ/mới cùng kết nối queue; message tồn đọng, retry sau crash, DLQ/replay, response đến trễ, network partition, rolling deploy và rollback.
- **Restart tests:** job đã tạo ở schema cũ có thể restart sau nâng cấp và vẫn đọc được `ExecutionContext`/metadata theo quy trình đã công bố.

Pseudo-test thể hiện việc xác minh compatibility:

~~~java
// Minh họa logic kiểm thử; deserializeV1/V2 là adapter của ứng dụng.
ChunkTaskV2 fromOld = deserializeV1(goldenV1Bytes()).upcast();
assert fromOld.priority().equals("NORMAL");

ChunkTaskV2 fromNew = deserializeV2(goldenV2Bytes());
assert fromNew.itemIds().equals(List.of("order-13", "order-14"));

// Kiểm tra thêm parser v1 có đọc được message mới hay không,
// nếu contract release có cam kết forward compatibility.
~~~

Không dừng ở test schema registry. Một schema có thể được công nhận là compatible mà worker vẫn xử lý sai nếu enum, default, conversion hoặc ràng buộc nghiệp vụ thay đổi.

### 11.2. Chỉ số và log để phát hiện lệch version

| Quan sát | Ý nghĩa vận hành |
|---|---|
| `message_decode_failure_total{message_type,schema_major,reason}` | Có message không đọc được hoặc bị từ chối do mismatch |
| `batch_message_dlq_total{message_type,reason}` | Số message phải cách ly |
| `batch_message_retry_total{message_type,reason}` | Retry bất thường sau nâng cấp |
| `batch_contract_supported_versions` hoặc version inventory | Fleet nào đang đọc/ghi schema nào |
| Độ trễ queue, outstanding chunk, tỷ lệ response timeout | Lệch phiên bản có đang làm nghẽn job không |
| Job `FAILED`/`STOPPED` và reconciliation backlog | Có gây hỏng kết quả hoặc đứt chuỗi xử lý không |

Không đưa `messageId`, `jobExecutionId` hay `tenantId` biến thiên cao vào metric label. Dùng structured log và distributed tracing để truy ngược từng message. Log an toàn gồm `schemaId`, `messageType`, `producerRelease`, `consumerRelease`, correlation và reasonCode; không đưa token, mật khẩu hoặc toàn bộ dữ liệu item vào log.

Cảnh báo nên phân biệt lỗi **không decode được message** với lỗi **nghiệp vụ sau khi decode**; cả hai đều có thể tăng khi rollout nhưng cần cách khắc phục khác nhau.

## 12. Tình huống thực tế: manager nâng cấp khi worker còn chạy phiên bản cũ

**Bối cảnh:** `invoiceAggregationJob` xử lý hàng triệu hóa đơn. Manager đọc theo chunk, gửi `BATCH_CHUNK_REQUEST` qua message broker đến mười worker. Team cần bổ sung `priority` để phân phối tải trong giờ cao điểm.

1. **Trước nâng cấp:** M1/W1 dùng v1, xử lý itemIds theo FIFO. Trong queue còn 200 chunk v1.
2. **Chuẩn bị:** đội phát triển định nghĩa v1.1 với `priority` có default `NORMAL`; test reader v2 đọc 200 mẫu v1 và kiểm tra worker W1 có bỏ qua trường lạ hay không.
3. **Nâng worker:** nếu W1 là strict parser, phải triển khai W2 dual-read trên toàn fleet trước; manager vẫn phát v1. W2 khi nhận v1 xử lý `priority = NORMAL`.
4. **Đổi manager:** M2 phát v1.1; response của worker cũ/mới đều nằm trong tập version manager hiểu. Theo dõi decode failures, queue lag, retry và throughput.
5. **Giả lập crash:** worker xử lý chunk nhưng chết trước ack. Broker giao lại; dedup dựa trên work unit/side effect đảm bảo không cộng hóa đơn hai lần.
6. **Xử lý rollback:** nếu M2 có lỗi, giảm writer về v1; W2 vẫn hỗ trợ v1. Nếu rollback worker về W1, phải chắc chắn W1 đọc được v1.1 đã gửi hoặc phải cách ly/chuyển đổi các message đó.
7. **Kết thúc:** khi các execution cũ hoàn tất/restart an toàn, queue và DLQ đã đối soát, mới cân nhắc thu hẹp hỗ trợ v1.

Một chi tiết khó thấy: nếu `priority = HIGH` tác động đến **thứ tự** xử lý các chunk mà nghiệp vụ yêu cầu xử lý tuần tự, thì việc thêm field không còn là thay đổi schema thuần túy. Phải chứng minh thay đổi scheduling không làm sai kết quả.

## 13. Checklist thiết kế và nâng cấp schema message

- [ ] Có danh mục `messageType`, producer, consumer, topic/queue và hướng request–response.
- [ ] Phân biệt rõ wire contract, business semantics và dữ liệu persisted trong `JobRepository`/`ExecutionContext`.
- [ ] Mỗi contract có version, schema ID, owner, quy tắc default/unknown field và chính sách sunset.
- [ ] Thống nhất định nghĩa backward/forward/full/transitive và kiểm tra **mọi cặp phiên bản triển khai thực tế**.
- [ ] Không rename/xóa field bắt buộc hoặc đổi kiểu/đổi nghĩa mà chưa có adapter/migration.
- [ ] Worker/manager hỗ trợ message backlog, replay, retry và rollback window trước khi đổi writer.
- [ ] Request và response đều có correlation, identity execution, idempotency và outcome xác thực.
- [ ] Parser validate schema, dữ liệu, giới hạn kích thước và tenant/scope; message sai version vào quarantine thay vì retry vô hạn.
- [ ] Có golden message tests, integration tests cho mixed versions và restart tests qua ranh giới phát hành.
- [ ] Có chỉ số decode error, DLQ, retry, throughput, queue lag và runbook đối soát job.
- [ ] Xem lại compatibility của Spring Batch, Spring Integration, serializer, Java runtime và schema metadata trong lộ trình upgrade.

**Điểm cần nhớ:** Tương thích schema message là cam kết giữa **bên tạo, bên đọc và ý nghĩa xử lý của message**. Để mở rộng Spring Batch an toàn, phải cho manager/worker chạy hỗn hợp phiên bản có kiểm soát, giữ đường đọc dữ liệu cũ đủ lâu cho retry/restart/replay, và xác minh kết quả xử lý đúng chứ không dừng ở việc deserialize thành công.

### Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): remote chunking, remote partitioning và remote step execution theo phiên bản tài liệu.
- [Spring Batch API — ChunkRequestHandler](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/chunk/ChunkRequestHandler.html): vai trò request/response trong remote chunking.
- [Spring Batch API — StepExecutionRequestHandler](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/integration/partition/StepExecutionRequestHandler.html): xử lý step execution request và truy `JobRepository`.
- [Apache Avro Specification](https://avro.apache.org/docs/1.12.0/specification/): writer/reader schema resolution, aliases và defaults.
- [Protocol Buffers — Language Guide](https://protobuf.dev/programming-guides/editions/): field number, reserved fields và quy tắc evolution.
