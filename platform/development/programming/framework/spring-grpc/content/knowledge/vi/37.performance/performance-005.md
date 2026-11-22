# Batching và message frequency

Trong gRPC streaming, **batching** là việc gom nhiều record hoặc event ở tầng ứng dụng vào một message Protobuf, hoặc gom nhiều thao tác nhỏ thành một đợt xử lý. **Message frequency** là tần suất ứng dụng phát các gRPC message trên một stream. Hai yếu tố này ảnh hưởng trực tiếp đến throughput, latency, CPU, network overhead, memory và khả năng phản hồi của service.

Trong **SPRING_GRPC**, batching thường hữu ích cho event ingestion, đồng bộ dữ liệu, upload/download theo chunk, telemetry và xử lý nhiều record trong một stream. Tuy nhiên, gRPC không tự động gộp nhiều lần gọi onNext thành một message ứng dụng. Mỗi message được gửi qua observer vẫn là một gRPC message riêng; muốn gom record, contract Protobuf và application code phải biểu diễn batch một cách tường minh.

## 1. Batching ở tầng ứng dụng là gì?

Giả sử producer có 1.000 event nhỏ. Có hai cách truyền:

- **Không batch:** phát 1.000 gRPC message, mỗi message chứa một event.
- **Batch:** gom 100 event vào một message, phát 10 gRPC message.

Batching giảm số lần xử lý message envelope, callback, dispatch và một phần protocol overhead. Nó cũng có thể giúp server ghi database theo lô. Đổi lại, producer phải chờ gom dữ liệu; message lớn hơn cần nhiều memory và có thể làm tăng thời gian xử lý một batch.

Điều cần phân biệt:

- Một gRPC stream có thể chứa nhiều message.
- Một message Protobuf có thể chứa nhiều logical record qua repeated field.
- Một batch ứng dụng không tự động là một transaction nguyên tử.
- Một lần onNext không chứng minh consumer đã commit dữ liệu.

Do đó, batching là quyết định về contract và xử lý nghiệp vụ, không chỉ là một mẹo tối ưu transport.

## 2. Message frequency và trade-off throughput/latency

Message frequency cao có nghĩa ứng dụng phát nhiều message nhỏ trong một đơn vị thời gian. Frequency thấp thường có nghĩa mỗi message chứa nhiều record hơn hoặc producer đợi lâu hơn trước khi flush.

| Chiến lược | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Gửi từng record ngay khi có | Latency thấp, xử lý sớm, lỗi khoanh vùng nhỏ | Nhiều callback, framing, scheduling và overhead cho message nhỏ |
| Gom theo số record | Kích thước batch dễ kiểm soát, throughput thường tốt hơn | Khi tải thấp có thể phải chờ lâu mới đủ batch |
| Gom theo khoảng thời gian | Giới hạn thời gian chờ, phù hợp event liên tục | Batch size biến động theo tải |
| Gom theo số byte | Kiểm soát payload và memory tốt hơn | Cần ước lượng/đo serialized size |
| Kết hợp count, bytes và time | Cân bằng throughput, latency và giới hạn message | Cần quản lý timer, flush và cạnh tranh giữa các trigger |

Nếu gửi từng event nhỏ, chi phí cố định trên mỗi message có thể chiếm tỷ lệ đáng kể. Nếu chờ batch quá lớn, event đầu tiên phải chờ lâu, làm tăng latency p95/p99. Vì vậy, tối ưu cần xét đồng thời messages/s, bytes/s, thời gian chờ gom batch và thời gian consumer xử lý.

### 2.1. Chọn ngưỡng flush

Một batch thường được flush khi đạt điều kiện đầu tiên trong các điều kiện:

1. **Max count:** đủ số record, ví dụ 100 event.
2. **Max bytes:** tổng serialized size gần ngưỡng cho phép, ví dụ 256 KiB.
3. **Max wait:** record đầu tiên đã chờ đến thời gian tối đa, ví dụ 20 ms.
4. **Lifecycle:** stream hoàn tất, client đóng input hoặc cần flush trước checkpoint.

Các con số chỉ là ví dụ để giải thích. Ngưỡng thực tế phải được benchmark với payload, network, downstream và SLO của hệ thống.

Với tải cao, count/bytes trigger thường flush nhanh. Với tải thấp, time trigger bảo đảm event không bị giữ vô thời hạn chỉ vì batch chưa đầy.

## 3. Thiết kế Protobuf contract cho batch

Một contract batch nên thể hiện rõ nội dung và khả năng xác nhận:

```protobuf
syntax = "proto3";

package telemetry.v1;

service EventIngestService {
  rpc Publish(stream EventBatch) returns (PublishSummary);
}

message Event {
  uint64 sequence = 1;
  string event_type = 2;
  bytes payload = 3;
}

message EventBatch {
  string batch_id = 1;
  repeated Event events = 2;
  uint64 first_sequence = 3;
  uint64 last_sequence = 4;
}

message PublishSummary {
  uint64 accepted_count = 1;
  uint64 rejected_count = 2;
  uint64 last_committed_sequence = 3;
}
```

Ví dụ này dùng client streaming: client gửi nhiều EventBatch và server trả một summary khi client hoàn tất. Các field sequence và batch_id giúp server phát hiện khoảng sequence, duplicate hoặc retry.

Contract thực tế cần quyết định:

- Batch có được phép rỗng không?
- Thứ tự event trong batch có quan trọng không?
- Sequence liên tục hay có thể bỏ khoảng?
- Một batch lỗi thì từ chối toàn batch hay trả kết quả từng event?
- Server xác nhận đã nhận, đã xử lý hay đã commit?
- Batch có idempotency key hay không?
- Giới hạn count và serialized bytes là bao nhiêu?

Không mặc định rằng repeated field luôn là lựa chọn tốt nhất. Nếu record rất lớn, cần truyền file/chunk, hoặc từng record cần retry độc lập, có thể dùng message riêng trong stream và checkpoint theo sequence.

## 4. Chọn batch size theo count và bytes

Chỉ giới hạn số record là chưa đủ. 100 event nhỏ có thể chỉ chiếm vài KiB, trong khi 100 event có payload lớn có thể vượt giới hạn message của server hoặc client.

Nên có ít nhất hai giới hạn:

- Max records per batch.
- Max serialized bytes per batch.

Với Protobuf Java, message sinh ra từ compiler cung cấp getSerializedSize() để ước lượng serialized size của message. Khi tính batch, phải cộng cả overhead của wrapper và metadata Protobuf ở mức message; không dùng tổng kích thước payload thô như thể đó là toàn bộ kích thước wire.

Không nên tạo batch lớn hơn giới hạn inbound message size đã cấu hình ở client/server. Giới hạn phải được thống nhất trong contract/deployment và có headroom cho wrapper fields. Nếu một record đơn lẻ đã vượt max bytes, cần từ chối rõ ràng hoặc chia record thành chunk theo contract.

## 5. Ví dụ gom batch trong Java

Một accumulator có thể giữ batch hiện tại và trả batch đã đầy cho caller gửi đi. Ví dụ dưới đây minh họa trigger theo count và serialized bytes:

```java
final class EventBatchAccumulator {
    private final int maxEvents;
    private final int maxBytes;
    private final List<Event> pending = new ArrayList<>();
    private int pendingBytes;

    EventBatchAccumulator(int maxEvents, int maxBytes) {
        if (maxEvents < 1 || maxBytes < 1) {
            throw new IllegalArgumentException("Batch limits must be positive");
        }
        this.maxEvents = maxEvents;
        this.maxBytes = maxBytes;
    }

    synchronized List<EventBatch> add(Event event) {
        int eventBytes = event.getSerializedSize();
        if (eventBytes > maxBytes) {
            throw new IllegalArgumentException("Event exceeds batch byte limit");
        }

        List<EventBatch> ready = new ArrayList<>(2);
        if (!pending.isEmpty()
                && (pending.size() >= maxEvents
                    || pendingBytes + (long) eventBytes > maxBytes)) {
            ready.add(detach());
        }

        pending.add(event);
        pendingBytes += eventBytes;

        if (pending.size() >= maxEvents || pendingBytes >= maxBytes) {
            ready.add(detach());
        }
        return ready;
    }

    synchronized Optional<EventBatch> flush() {
        return pending.isEmpty()
            ? Optional.empty()
            : Optional.of(detach());
    }

    private EventBatch detach() {
        EventBatch batch = EventBatch.newBuilder()
            .setBatchId(UUID.randomUUID().toString())
            .addAllEvents(pending)
            .setFirstSequence(pending.get(0).getSequence())
            .setLastSequence(pending.get(pending.size() - 1).getSequence())
            .build();
        pending.clear();
        pendingBytes = 0;
        return batch;
    }
}
```

Đây là accumulator minh họa; production code cần bổ sung sequence range, timestamp, giới hạn tổng buffer và xử lý record quá lớn. Caller nhận các batch từ add/flush rồi gửi chúng trên một execution path được serialize. Không giữ lock của accumulator trong lúc gọi network hoặc observer, vì thao tác gửi có thể chậm hoặc callback re-enter.

Trigger theo thời gian thường được thực hiện bằng scheduler gọi flush định kỳ hoặc bằng timer bắt đầu khi batch chuyển từ rỗng sang có record. Timer phải được hủy/reset khi batch đã detach. Khi timer và producer cùng flush, cần đồng bộ để một record chỉ thuộc đúng một batch.

## 6. Thread safety và thứ tự gửi

Producer, timer và cancellation callback có thể chạy trên các thread khác nhau. Nếu cùng sửa một accumulator, cần đồng bộ trạng thái:

- Chỉ một nơi sở hữu batch đang mở, hoặc dùng lock quanh thao tác add/detach.
- Detach batch trong vùng đồng bộ; gửi batch sau khi nhả lock.
- Serialize việc gọi onNext trên cùng StreamObserver.
- Không để timer gửi batch mới vượt qua batch cũ.
- Khi stream cancel, ngừng producer và quyết định rõ batch đang giữ được bỏ, lưu bền vững hay retry.

Nếu batch được gửi bất đồng bộ qua executor, queue gửi cũng phải bounded. Nếu accumulator bounded nhưng queue gửi không giới hạn, hệ thống vẫn có thể tăng heap không kiểm soát.

Thứ tự record trong một batch thường theo sequence tăng dần. Nếu nhiều producer tạo event đồng thời, phải xác định sequence được cấp tại đâu và thứ tự nào là authoritative. Không suy luận thứ tự nghiệp vụ chỉ từ thời điểm callback chạy.

## 7. Flush theo thời gian và message frequency

Time-based flush hữu ích khi traffic không đều. Một timer có thể flush batch khi thời gian chờ của record đầu tiên đạt max wait. Không nên dùng fixed-rate flush như một bảo đảm rằng mọi batch đều có cùng tuổi; timer có thể trễ do scheduler bận hoặc JVM pause.

Thiết kế cần quyết định:

- Max wait tính từ record đầu tiên hay từ record gần nhất.
- Timer flush batch rỗng có được bỏ qua không.
- Khi stream hoàn tất, có flush batch cuối trước onCompleted không.
- Khi client cancel, batch cuối có được lưu để resume không.
- Khi lỗi xảy ra trong lúc flush, batch được giữ lại hay chuyển trạng thái pending retry.

Nếu max wait tính từ record gần nhất, một luồng event liên tục có thể trì hoãn flush vô thời hạn. Thường dùng thời gian từ record đầu tiên của batch để đặt giới hạn latency rõ ràng.

## 8. Backpressure và giới hạn buffer

Batching làm giảm số message nhưng tăng lượng dữ liệu giữ trong bộ nhớ trước khi flush. Vì vậy, batching phải đi cùng backpressure:

- Giới hạn số record và byte đang chờ.
- Giới hạn số batch đang chờ gửi.
- Khi đầy, pause producer, giảm tốc, từ chối hoặc persist vào durable queue theo yêu cầu nghiệp vụ.
- Chỉ yêu cầu thêm inbound message khi consumer có capacity nếu dùng manual flow control.
- Với outbound stream, kiểm tra readiness trước khi phát batch.
- Hủy timer, producer và pending work khi stream đóng.

HTTP/2 flow control điều tiết byte ở tầng transport. Nó không ngăn application tạo một danh sách hàng triệu record trước khi gọi onNext. Bounded buffer là trách nhiệm của application.

Một batch có thể vượt ngưỡng readiness ngay cả khi stream trước đó sẵn sàng. Vì thế, producer nên kiểm tra readiness trước khi gửi từng batch và chỉ giữ số batch pending có giới hạn.

## 9. Batch atomicity, acknowledgement và retry

Một gRPC message chứa nhiều event không có nghĩa server xử lý chúng trong một transaction duy nhất. Server có thể:

- Commit toàn bộ batch hoặc rollback toàn bộ.
- Commit từng event và trả kết quả theo từng event.
- Chấp nhận batch vào durable queue rồi xử lý bất đồng bộ.

Contract phải nói rõ semantics nào được dùng. Nếu server commit từng event nhưng client chỉ nhận một status cuối cho toàn stream, client có thể không biết event nào đã được commit trước khi lỗi xảy ra.

Để retry an toàn:

- Mỗi event có event ID hoặc sequence ổn định.
- Mỗi batch có batch ID ổn định qua lần retry.
- Server lưu idempotency/deduplication state theo thời hạn đã công bố.
- Ack nêu rõ sequence hoặc batch đã commit.
- Client chỉ gửi lại phần chưa được xác nhận.
- Retry phải tuân thủ deadline và giới hạn số lần thử.

Không tạo batch ID mới khi retry cùng một batch đã gửi nhưng chưa nhận ack; làm vậy sẽ khiến server khó nhận diện duplicate.

## 10. Xử lý lỗi một phần trong batch

Nếu một batch có 100 record và một record không hợp lệ, API cần quy định rõ:

| Semantics | Hành vi |
| --- | --- |
| Atomic batch | Từ chối toàn batch; không record nào được commit |
| Per-item result | Xử lý record hợp lệ, trả kết quả cho từng record |
| Durable enqueue | Ack khi batch đã được lưu bền vững; xử lý nghiệp vụ diễn ra sau |

Với per-item result, response có thể chứa sequence, result code và mô tả lỗi đã được phép công khai. Không dùng một status cuối để ngụ ý toàn bộ batch thất bại nếu một phần đã commit.

Với atomic batch, phải bảo đảm transaction bao phủ đúng các record trong batch và giới hạn transaction size. Batch quá lớn có thể giữ lock lâu, tăng log pressure và làm giảm concurrency.

## 11. Compression và message frequency

Batch lớn có thể tăng hiệu quả compression vì nhiều record có cấu trúc lặp nằm trong cùng payload. Nhưng compression cũng tiêu tốn CPU và có thể làm tăng thời gian trước khi message sẵn sàng gửi.

| Workload | Hướng cân nhắc |
| --- | --- |
| Event nhỏ, field lặp nhiều | Batch có thể cải thiện compression ratio |
| Payload đã nén | Compression thêm thường ít lợi ích |
| CPU là bottleneck | Đo kỹ trước khi bật compression |
| Network là bottleneck | Batch/compression có thể tăng goodput |
| Message lớn và latency nhạy cảm | Giới hạn batch size và thời gian gom |

Không nên so sánh chỉ bytes/s. Hãy đo CPU/message, latency p95/p99, memory/batch và goodput. Một cấu hình giảm network 30% nhưng tăng CPU gấp đôi có thể làm tổng throughput thấp hơn.

## 12. Kết hợp batching với HTTP/2 flow control

Mỗi batch là một gRPC message riêng trên stream. HTTP/2 có flow control ở cấp stream và connection; gRPC runtime sẽ điều tiết byte theo window. Application cần phối hợp:

1. Tạo batch không vượt giới hạn message size.
2. Chỉ gửi khi stream readiness cho phép.
3. Giữ số batch đang chờ gửi trong giới hạn.
4. Theo dõi thời gian chờ flow control.
5. Không tăng batch size để che consumer chậm.

Nếu receiver không theo kịp, tăng batch size có thể làm mỗi lần gửi hiệu quả hơn nhưng cũng khiến receiver phải xử lý các đợt dữ liệu lớn hơn. Cần đo consumer processing time và queue depth, không chỉ sender throughput.

## 13. Benchmark batching và message frequency

Benchmark nên so sánh nhiều cấu hình trên cùng workload:

| Thử nghiệm | Count limit | Byte limit | Time limit |
| --- | ---: | ---: | ---: |
| A: gửi từng record | 1 | nhỏ | gần 0 |
| B: batch nhỏ | 16 | 32 KiB | 5 ms |
| C: batch vừa | 64 | 128 KiB | 15 ms |
| D: batch lớn | 256 | 512 KiB | 30 ms |

Đây là ma trận thử nghiệm minh họa, không phải giá trị mặc định. Cần điều chỉnh theo message size, server max inbound size, downstream batch capacity và SLO.

Với mỗi cấu hình, đo:

- Messages/s và logical records/s.
- Payload goodput và wire bytes/s.
- Thời gian từ khi event được tạo đến khi flush.
- End-to-end latency p50/p95/p99.
- CPU, allocation rate, heap, GC pause.
- Queue depth, batch fill ratio và số lần flush do count/bytes/time.
- Error, retry, duplicate và partial commit.

Chạy warm-up trước khi lấy số liệu steady-state. Tăng tải dần và giữ đủ lâu để phát hiện queue tăng theo thời gian. Nếu throughput tăng nhưng p99 latency hoặc memory vượt SLO, cấu hình đó không phải lựa chọn tốt.

## 14. Observability cho batching

Các metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Records per batch | Batch fill ratio và hiệu quả gom |
| Serialized bytes per batch | Phân bố kích thước message |
| Batch flush count theo trigger | Count/bytes/time/lifecycle trigger nào chi phối |
| Batch wait duration | Thời gian record phải chờ trước khi flush |
| Records per second | Throughput nghiệp vụ |
| Messages per second | Tần suất message gRPC |
| Pending records/bytes | Áp lực buffer |
| Send queue depth | Khả năng gửi có theo kịp producer không |
| Ack latency | Thời gian từ gửi đến xác nhận commit |
| Retry/duplicate/partial failure | Tính đúng đắn và chi phí phục hồi |

Không dùng batch ID, event ID, user ID hoặc resource ID làm metric label có cardinality cao. Dùng trace/log có kiểm soát để điều tra một batch cụ thể; không ghi payload nhạy cảm.

Batch fill ratio thấp có thể cho thấy time trigger quá ngắn hoặc traffic thấp. Batch wait duration cao có thể do max wait lớn, producer không đều hoặc timer bị trễ. Pending bytes tăng liên tục thường cho thấy consumer hoặc network không theo kịp.

## 15. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm tốt hơn |
| --- | --- | --- |
| Cho rằng gRPC tự batch nhiều onNext | Không giảm được số logical gRPC message | Gom record vào Protobuf batch ở application |
| Chỉ giới hạn count | Batch có thể vượt max message size | Giới hạn cả count và serialized bytes |
| Chỉ flush khi batch đầy | Tải thấp khiến event chờ vô hạn | Thêm max wait trigger |
| Flush timer và producer không đồng bộ | Gửi trùng, mất hoặc đảo thứ tự batch | Đồng bộ detach và serialize send |
| Queue gửi không giới hạn | Heap tăng dù accumulator có giới hạn | Bounded send queue và backpressure |
| Xem một batch là transaction nguyên tử | Client hiểu sai partial commit | Công bố atomic/per-item/durable enqueue semantics |
| Retry với batch ID mới | Duplicate khó phát hiện | Giữ batch/event id ổn định qua retry |
| Batch quá lớn | Latency, lock duration và memory tăng | Benchmark nhiều ngưỡng và giữ max bytes |
| Chỉ đo messages/s | Không biết số logical records đã xử lý | Đo records/s, ack và commit throughput |

## 16. Checklist chọn batching và message frequency

Trước khi phát hành stream có batching, hãy xác định:

1. **Mục tiêu:** tối ưu records/s, payload goodput, CPU hay network?
2. **Contract:** batch message có field ID, sequence và semantics rõ không?
3. **Trigger:** có count, serialized bytes và max wait không?
4. **Message size:** một record hoặc batch có thể vượt giới hạn inbound không?
5. **Buffer:** accumulator và send queue có bounded không?
6. **Timer:** flush theo thời gian có an toàn khi producer/cancel cùng chạy không?
7. **Ordering:** batch và event có sequence/ordering rule không?
8. **Atomicity:** toàn batch hay từng event được commit?
9. **Acknowledgement:** ack xác nhận received, processed hay committed?
10. **Retry:** batch ID/event ID có ổn định để deduplicate không?
11. **Backpressure:** producer có dừng/giảm tốc khi receiver không theo kịp không?
12. **Benchmark:** đã đo throughput, p95/p99, memory, CPU và fill ratio chưa?
13. **Observability:** có pending bytes, flush reason, ack latency và duplicate rate không?

## 17. Ghi nhớ

Batching gom nhiều logical record vào một gRPC message để giảm overhead cố định và có thể tăng throughput. Message frequency thấp hơn thường giảm số lần dispatch/callback nhưng làm record chờ lâu hơn và tạo payload lớn hơn. Một thiết kế cân bằng dùng đồng thời ngưỡng số record, serialized bytes và thời gian chờ tối đa.

Trong Spring gRPC, batching phải đi cùng Protobuf contract rõ ràng, bounded buffer, flush thread-safe, readiness/flow control và acknowledgement có semantics cụ thể. Một batch không tự động là transaction nguyên tử; retry cần batch/event ID ổn định và deduplication. Benchmark phải đo records/s, messages/s, goodput, batch wait, p95/p99 latency, CPU và memory. Chọn frequency dựa trên workload và SLO giúp tăng throughput mà không đánh đổi khả năng phản hồi, tính đúng đắn hoặc độ tin cậy.

### Tài liệu tham khảo

- [gRPC – Performance](https://grpc.io/docs/guides/performance/)
- [gRPC – Flow control](https://grpc.io/docs/guides/flow-control/)
- [gRPC Java – Generated code reference](https://grpc.io/docs/languages/java/generated-code/)
- [gRPC Java – API documentation](https://grpc.github.io/grpc-java/javadoc/)
- [Protocol Buffers – Best practices](https://protobuf.dev/best-practices/dos-donts/)
