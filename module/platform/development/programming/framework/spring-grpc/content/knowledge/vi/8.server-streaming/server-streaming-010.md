# Retry server stream và khả năng phát lại

## 1. Vì sao retry một server stream cần thiết kế riêng?

Trong **SPRING_GRPC**, server streaming cho phép client gửi một request và nhận nhiều response Protocol Buffers trên cùng một RPC. Cách truyền này phù hợp với tiến độ công việc, sự kiện, log hoặc kết quả truy vấn lớn. Nhưng một stream có thể bị ngắt sau khi client đã nhận một phần dữ liệu: server mất kết nối với nguồn, proxy đóng transport, deadline hết hoặc client tạm thời mất mạng.

Ví dụ client đang theo dõi một job:

~~~text
RPC lần 1:
  Client -> WatchJob(after_sequence = 0)
  Server -> Event #1
  Server -> Event #2
  Server -> Event #3
  Server -> UNAVAILABLE

RPC lần 2:
  Client -> WatchJob(after_sequence = 2)
  Server -> Event #3, #4, #5, ...
  Server -> onCompleted()
~~~

Client đã áp dụng bền vững đến #2, nhưng chưa chắc đã xử lý xong #3. Khi kết nối lại, server phát lại #3 để client không bỏ sót. Vì vậy có thể xuất hiện một event đã được truyền ở lần trước; client cần nhận diện và xử lý trùng an toàn.

**Retry** là tạo một lần gọi mới sau khi lần gọi trước thất bại. **Replay** là server phát lại những event đã tồn tại trong nguồn dữ liệu. **Resume** là kết hợp hai việc đó bằng một cursor/checkpoint để lần gọi mới tiếp tục từ vị trí đã xác nhận.

Đây là điểm trọng tâm: một server stream đã nhận dữ liệu một phần không thể được phục hồi chỉ bằng cách gọi lại cùng một stub hoặc tiếp tục dùng iterator cũ. Muốn tiếp tục đúng, ứng dụng phải xác định **đã xử lý bền vững đến đâu** và server phải có khả năng đọc lại dữ liệu từ vị trí đó.

## 2. Phân biệt retry tự động của gRPC và resume ở tầng ứng dụng

gRPC có cơ chế retry theo cấu hình cho một số lỗi và điều kiện nhất định. Cơ chế này hữu ích khi lời gọi chưa được commit theo quy tắc retry của runtime. Nhưng khi một server streaming RPC đã bắt đầu trả response và được commit, client không nên kỳ vọng gRPC tự phát lại các message đã nhận hoặc tiếp tục từ message còn thiếu.

| Cơ chế | Phạm vi | Giải quyết được gì? | Không giải quyết được gì? |
|---|---|---|---|
| Retry policy của gRPC | Một RPC trước khi bị commit theo quy tắc runtime | Thử lại một số lỗi phù hợp với policy | Không thay thế checkpoint/replay sau khi stream đã phát dữ liệu |
| Retry thủ công | Client tạo RPC mới sau lỗi | Cho phép quyết định thời điểm, status và backoff | Không tự biết event nào client đã commit |
| Replay từ nguồn lưu bền | Server đọc lại event theo cursor/offset | Cung cấp lại dữ liệu đã phát trước đó | Không tự ngăn client áp dụng trùng |
| Resume bằng checkpoint | Client gửi vị trí đã áp dụng trong request mới | Tiếp tục từ điểm đã xác nhận | Cần sequence ổn định, retention và xử lý gap/duplicate |

Một server stream có thể đã gửi response headers trước khi phát message đầu tiên; khi RPC được commit, cơ chế retry tự động không thể tùy ý tạo một phiên mới mà không có nguy cơ lặp dữ liệu. Hành vi cụ thể còn phụ thuộc cấu hình và runtime. Vì vậy, thiết kế khả năng phục hồi cho stream dài nên dựa vào **retry ở tầng ứng dụng cùng cursor/replay**, không phụ thuộc vào giả định rằng transport sẽ tự nối tiếp stream.

## 3. Hợp đồng cần cursor hoặc sequence ổn định

Để server có thể phát lại, mỗi event cần một định danh và vị trí ổn định. Ví dụ theo dõi tiến độ job:

~~~proto
syntax = "proto3";

package jobs.v1;

option java_multiple_files = true;
option java_package = "com.example.jobs.rpc";

service JobEventService {
  rpc WatchEvents(WatchEventsRequest) returns (stream JobEvent);
}

message WatchEventsRequest {
  string job_id = 1;
  int64 after_sequence = 2;
}

message JobEvent {
  string job_id = 1;
  int64 sequence = 2;
  string event_id = 3;
  string event_type = 4;
  string payload = 5;
}
~~~

Quy ước của hợp đồng:

- `sequence` tăng đơn điệu trong phạm vi một `job_id`.
- `event_id` giữ nguyên cho cùng một event qua các lần replay.
- `after_sequence = N` nghĩa là server chỉ phát event có sequence **lớn hơn N**.
- Client chỉ tăng checkpoint sau khi event đã được áp dụng và lưu bền vững.

Ví dụ client đã commit đến sequence 12 thì gửi `after_sequence = 12`; server bắt đầu phát từ 13. Không dùng `last_received_sequence` làm checkpoint nếu client có xử lý bất đồng bộ và chưa hoàn thành việc lưu event.

Với hệ thống phức tạp, cursor có thể là token opaque thay vì một số nguyên. Token có thể mã hóa partition, offset, snapshot/version và thông tin xác thực. Dù dùng kiểu nào, server cần định nghĩa rõ phạm vi, thời hạn hiệu lực và cách báo cursor không còn hợp lệ.

**Sequence không tự tạo ra khả năng replay.** Server phải có nguồn dữ liệu bền vững để tìm event sau vị trí đã yêu cầu. Một bộ đếm trong RAM của từng instance không đủ nếu client có thể reconnect sang instance khác.

## 4. Client chỉ checkpoint sau khi xử lý thành công

Có ba vị trí khác nhau:

1. **Server đã phát:** server gọi `onNext(event)`.
2. **Client đã nhận:** callback/iterator đã cung cấp event.
3. **Client đã commit:** thay đổi nghiệp vụ và checkpoint đã được lưu bền vững.

Chỉ vị trí thứ ba là điểm resume an toàn. Ví dụ client nhận #13, cập nhật UI hoặc bắt đầu ghi database, nhưng ứng dụng crash trước khi transaction commit. Nếu checkpoint đã tăng lên 13 trước khi dữ liệu được lưu, lần reconnect sẽ bắt đầu từ #14 và bỏ mất #13.

Quy trình xử lý nên là:

~~~text
Nhận event #13
    |
    v
Kiểm tra event_id và sequence
    |
    v
Áp dụng thay đổi nghiệp vụ + lưu checkpoint trong transaction
    |
    v
Transaction commit thành công
    |
    v
Checkpoint mới = 13
~~~

Ví dụ pseudocode Java:

~~~java
void applyAndCheckpoint(JobEvent event) {
    transactionTemplate.executeWithoutResult(tx -> {
        if (eventStore.wasApplied(event.getEventId())) {
            checkpointStore.advanceIfNeeded(
                    event.getJobId(), event.getSequence());
            return;
        }

        eventStore.apply(event);
        eventStore.markApplied(event.getEventId());
        checkpointStore.advanceIfNeeded(
                event.getJobId(), event.getSequence());
    });
}
~~~

Đây là logic minh họa; các thao tác kiểm tra, áp dụng, đánh dấu và lưu checkpoint phải cùng một transaction nếu chúng nằm trong cùng database. Nếu tác động nghiệp vụ nằm ở hệ thống khác, cần idempotency key hoặc inbox/outbox phù hợp. Không giả định hai thao tác ghi độc lập luôn cùng thành công.

Khi client đã commit #13 nhưng bị mất phản hồi trước khi server biết điều đó, lần reconnect vẫn có thể yêu cầu sau #13 hoặc nhận lại #13 nếu checkpoint chưa được ghi/đồng bộ đúng. `event_id` và thao tác idempotent giúp việc nhận lại không tạo side effect hai lần.

## 5. Server phải đọc lại lịch sử và chuyển sang live mà không mất event

Một lỗi thiết kế phổ biến là server đọc backlog rồi mới đăng ký listener cho event mới:

~~~text
1. Đọc lịch sử đến #100
2. Event #101 xuất hiện
3. Server đăng ký listener

Kết quả: #101 có thể bị bỏ sót.
~~~

Server cần một **điểm nối nhất quán** giữa dữ liệu lịch sử và luồng live. Có một số cách tùy nguồn:

- Dùng broker có offset/cursor và consumer API hỗ trợ đọc tiếp từ một offset.
- Lấy watermark/snapshot nhất quán, đăng ký live trước, buffer event mới, phát backlog đến watermark rồi drain buffer theo sequence.
- Dùng transaction hoặc cơ chế subscription của kho dữ liệu để bảo đảm không có khoảng trống giữa đọc lịch sử và nhận sự kiện mới.

Mô hình subscribe trước rồi replay:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as gRPC server
    participant E as Event store
    C->>S: WatchEvents(after_sequence = 100)
    S->>E: Register live subscription
    S->>E: Read durable events > 100
    E-->>S: #101, #102
    E-->>S: Live #103 (buffered)
    S-->>C: #101
    S-->>C: #102
    S-->>C: #103
    Note over S,C: Chuyển sang live mà không tạo gap
~~~

Sơ đồ mô tả nguyên tắc, không áp đặt một API broker cụ thể. Nếu subscription phát ra event trong lúc replay, server phải giữ buffer có giới hạn, loại trùng theo sequence và chỉ dùng một sender tuần tự để gọi `onNext`. Nếu không thể giữ buffer hoặc nguồn không có cursor đáng tin cậy, cần chọn chính sách khác và công bố rõ giới hạn phục hồi.

## 6. Client retry với backoff và checkpoint

Khi một server stream kết thúc bằng lỗi, client cần tạo **RPC mới** với `after_sequence` lấy từ checkpoint bền vững. Không tái sử dụng iterator đã lỗi. Retry nên có backoff tăng dần và jitter để tránh nhiều client reconnect cùng lúc.

Ví dụ chiến lược:

~~~text
Lần lỗi 1: đợi ngẫu nhiên khoảng 200–400 ms
Lần lỗi 2: đợi ngẫu nhiên khoảng 400–800 ms
Lần lỗi 3: đợi ngẫu nhiên khoảng 800–1600 ms
...
Giới hạn backoff tối đa: ví dụ 5 giây
Giới hạn tổng thời gian retry: theo ngân sách nghiệp vụ
~~~

Không phải status nào cũng nên retry:

| Status | Hướng xử lý thường gặp |
|---|---|
| `UNAVAILABLE` | Có thể retry với backoff nếu nguồn tạm thời lỗi và cursor còn hiệu lực |
| `RESOURCE_EXHAUSTED` | Giảm tải; chỉ retry sau khoảng chờ/quota policy phù hợp |
| `DEADLINE_EXCEEDED` | Xem lại ngân sách thời gian; retry chỉ khi còn budget và thao tác an toàn |
| `CANCELLED` | Không tự retry nếu do người dùng hoặc tác vụ cha chủ động hủy |
| `UNAUTHENTICATED` | Làm mới thông tin xác thực theo chính sách rồi mới cân nhắc gọi lại |
| `PERMISSION_DENIED` | Không retry liên tục với cùng quyền |
| `INVALID_ARGUMENT` | Sửa request; retry nguyên trạng không có ích |
| `FAILED_PRECONDITION` | Có thể cần đồng bộ lại snapshot hoặc tạo cursor mới theo hợp đồng |

Status chỉ là một đầu vào cho quyết định. Ví dụ `UNAVAILABLE` có thể là lỗi tạm thời, nhưng nếu nguồn dữ liệu đã xóa lịch sử thì retry cùng cursor vẫn thất bại. `RESOURCE_EXHAUSTED` có thể đi kèm thông tin thời gian chờ; client cần tôn trọng quota thay vì retry dồn dập.

### 6.1. Ví dụ blocking client

Đoạn code sau minh họa vòng lặp reconnect. Các helper `isRetryable`, `sleepWithJitter` và repository/checkpoint là thành phần ứng dụng, cần cài đặt theo chính sách của hệ thống.

~~~java
long checkpoint = checkpointStore.load(jobId);
long retryDelayMs = 200;
long retryDeadline = System.nanoTime()
        + TimeUnit.MINUTES.toNanos(2);

while (System.nanoTime() < retryDeadline) {
    WatchEventsRequest request = WatchEventsRequest.newBuilder()
            .setJobId(jobId)
            .setAfterSequence(checkpoint)
            .build();

    long remainingNanos = retryDeadline - System.nanoTime();
    long attemptNanos = Math.min(
            remainingNanos, TimeUnit.SECONDS.toNanos(20));

    try {
        var responses = JobEventServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(attemptNanos, TimeUnit.NANOSECONDS)
                .watchEvents(request);

        while (responses.hasNext()) {
            JobEvent event = responses.next();

            if (event.getSequence() <= checkpoint) {
                continue; // Có thể là event replay; deduplicate theo event_id.
            }
            if (event.getSequence() != checkpoint + 1) {
                throw new MissingSequenceException(
                        "Expected " + (checkpoint + 1)
                        + " but received " + event.getSequence());
            }

            applyAndCheckpoint(event); // Commit dữ liệu và checkpoint.
            checkpoint = event.getSequence();
        }

        return; // Iterator hết bình thường: RPC hoàn thành thành công.
    } catch (StatusRuntimeException error) {
        if (!isRetryable(error.getStatus())) {
            throw error;
        }

        sleepWithJitter(retryDelayMs);
        retryDelayMs = Math.min(retryDelayMs * 2, 5_000);
    }
}

throw new IllegalStateException("Resume budget exhausted");
~~~

Ví dụ giả định `channel`, `jobId`, `checkpointStore`, `applyAndCheckpoint`, `MissingSequenceException`, `isRetryable` và `sleepWithJitter` đã được định nghĩa. `applyAndCheckpoint` phải chỉ trả về sau khi transaction commit thành công. Trong ứng dụng thật, cần bắt riêng lỗi sequence gap để đồng bộ lại hoặc báo lỗi dữ liệu; không coi đó là lỗi tạm thời để retry vô hạn.

Vòng lặp dùng deadline tổng thể hai phút và deadline tối đa 20 giây cho từng attempt. `System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng tiến trình. Backoff phải có jitter, giới hạn số lần/thời gian retry, và có thể reset khi một phiên stream đã hoạt động ổn định đủ lâu.

`Thread.sleep` trong helper chỉ nên chạy trên worker thread dành cho việc retry, không chạy trên event loop hoặc thread phục vụ request của ứng dụng web.

## 7. Khi cursor hết hạn hoặc lịch sử không còn

Nguồn event thường có retention hữu hạn. Ví dụ client mất mạng ba ngày, trong khi server chỉ lưu event bảy ngày. Nếu checkpoint cũ hơn watermark sớm nhất còn giữ, server không thể phát lại toàn bộ phần còn thiếu.

Server nên trả một status có ý nghĩa, chẳng hạn `FAILED_PRECONDITION`, kèm mô tả an toàn cho biết client cần đồng bộ lại snapshot hoặc tạo phiên đọc mới. Không được âm thầm bỏ các event cũ rồi gọi `onCompleted()` như thể dữ liệu đầy đủ.

Quy trình resync có thể là:

1. Client nhận biết cursor đã hết hạn.
2. Client gọi API lấy snapshot nhất quán hiện tại.
3. Server trả snapshot cùng watermark sequence `W`.
4. Client lưu snapshot và checkpoint `W` một cách nguyên tử.
5. Client mở server stream mới với `after_sequence = W`.

Điểm quan trọng là snapshot và watermark phải thuộc cùng một trạng thái logic. Nếu snapshot được tạo ở thời điểm khác với watermark, event có thể bị bỏ sót hoặc áp dụng hai lần.

## 8. Retry không đồng nghĩa exactly-once

Sau một lỗi mạng, client có thể không biết server đã phát event cuối hay chưa; server cũng không biết client đã commit event cuối hay chưa. Đây là lý do một giao thức resume thường phải chấp nhận khả năng phát lại:

- **At-most-once:** tránh phát trùng nhưng có nguy cơ mất event khi client không nhận được phần cuối.
- **At-least-once:** phát lại từ checkpoint, có thể giao trùng; client deduplicate/idempotent để tránh side effect lặp.
- **Exactly-once effect:** không phải bảo đảm mặc định của gRPC. Có thể đạt hiệu ứng gần exactly-once trong phạm vi một transaction/định danh nghiệp vụ bằng idempotency, unique constraint và checkpoint nhất quán; cần thiết kế rõ ràng.

Đối với hầu hết event stream cần không mất dữ liệu, at-least-once cùng xử lý idempotent là lựa chọn thực tế. Client phải coi `event_id` hoặc cặp `(resource_id, sequence)` là khóa deduplication ổn định.

Nếu một RPC thực hiện side effect (ví dụ tạo job hoặc gửi lệnh thanh toán), không retry mù chỉ vì client nhận `UNAVAILABLE`. Deadline hoặc lỗi transport không chứng minh server chưa thực hiện side effect. Dùng idempotency key và API truy vấn trạng thái để xác định kết quả trước khi phát lệnh lại.

## 9. Kiểm thử retry và replay

Kiểm thử cần xác minh cả luồng truyền lẫn trạng thái bền vững của ứng dụng:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Stream hoàn tất bình thường | Client nhận đủ event và không mở RPC mới |
| Server phát #1–#3 rồi `UNAVAILABLE` | Client lưu checkpoint đúng rồi mở RPC mới |
| Client nhận #3 nhưng chưa commit | Resume có thể nhận lại #3; không mất dữ liệu |
| Client đã commit #3 | Request mới dùng `after_sequence = 3` |
| Event replay bị lặp | Client deduplicate, không tạo side effect lần hai |
| Sequence bị nhảy | Client phát hiện gap, không âm thầm tiến checkpoint |
| Cursor còn hạn | Server phát lại backlog và chuyển sang live không có gap |
| Cursor hết retention | Server báo cần resync snapshot |
| Client chủ động cancel | Không tự reconnect nếu người dùng đã dừng |
| Nhiều client cùng reconnect | Backoff/jitter giảm đợt tải dồn |
| Job tạo side effect | Retry dùng idempotency key hoặc kiểm tra trạng thái trước |

Một test in-process có thể tạo server gửi hai event rồi kết thúc `UNAVAILABLE`, sau đó lần gọi tiếp theo phát lại event thứ hai và event thứ ba. Test cần kiểm tra client chỉ áp dụng event thứ hai một lần. Ngoài transport test, cần integration test với event store thật hoặc test double có cursor/retention để xác minh logic replay-live handoff.

## 10. Quan sát vận hành và bảo mật

Trong Spring gRPC, interceptor và hệ thống metrics/tracing có thể ghi nhận method, thời lượng, status và correlation ID. Với retry/replay, cần thêm chỉ số ở tầng nghiệp vụ:

| Chỉ số | Mục đích |
|---|---|
| Số RPC stream mở mới sau lỗi | Theo dõi tần suất reconnect |
| Status của attempt trước | Phân loại lỗi tạm thời và lỗi không retry |
| Checkpoint trước/sau reconnect | Biết vị trí resume |
| Số event replay và duplicate | Đánh giá chi phí at-least-once |
| Sequence gap | Phát hiện mất dữ liệu hoặc lỗi handoff |
| Cursor hết hạn/resync | Đánh giá retention có đủ dài không |
| Backoff và thời gian phục hồi | Đánh giá trải nghiệm client |
| Queue depth và số stream đồng thời | Phát hiện tải tăng do reconnect |

Sử dụng TLS trong môi trường thật, xác thực caller và phân quyền theo `job_id`/resource trước khi cho replay. Cursor không nên là bằng chứng duy nhất để cấp quyền đọc dữ liệu. Tránh đưa token, payload nhạy cảm hoặc thông tin nội bộ vào log/status.

## 11. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi lại RPC từ sequence 0 sau mọi lỗi | Client xử lý trùng toàn bộ dữ liệu | Resume từ checkpoint đã commit |
| Dùng sequence cuối đã nhận làm checkpoint | Có thể bỏ event chưa commit | Lưu checkpoint sau khi xử lý bền vững |
| Nghĩ gRPC tự replay response đã nhận | Mất phần dữ liệu sau reconnect | Xây dựng cursor và nguồn replay |
| Server dùng sequence trong RAM của một instance | Reconnect sang instance khác không khớp | Sequence ổn định từ event store |
| Đọc backlog rồi mới subscribe live | Có khoảng trống event | Handoff lịch sử/live nhất quán |
| Retry mọi status | Lặp lỗi xác thực, request sai hoặc quá tải | Phân loại status và giới hạn retry |
| Không có backoff/jitter | Nhiều client tạo retry storm | Exponential backoff, jitter và quota |
| Không deduplicate event replay | Side effect bị lặp | Event ID, idempotency và transaction |
| Cursor hết hạn nhưng server vẫn trả dữ liệu mới | Client tưởng đã nhận đủ lịch sử | Báo resync rõ ràng bằng status phù hợp |

### Câu hỏi tự kiểm tra

1. Vì sao retry policy của gRPC không thay thế khả năng resume sau khi server stream đã phát response?
2. Client nên lưu sequence cuối đã nhận hay sequence cuối đã commit?
3. `after_sequence = 12` cần có ý nghĩa chính xác nào ở server?
4. Vì sao server phải xử lý khoảng thời gian giữa đọc backlog và đăng ký live subscription?
5. Khi nào nên retry `UNAVAILABLE`, và vì sao không nên retry `PERMISSION_DENIED` liên tục?
6. At-least-once replay tạo ra rủi ro gì và client xử lý thế nào?
7. Khi cursor đã hết retention, vì sao cần snapshot cùng watermark?

**Ghi nhớ:** Retry server stream là tạo RPC mới; replay là đọc lại event từ nguồn có lưu trữ; resume dùng checkpoint/cursor để tiếp tục sau vị trí client đã commit. Muốn phục hồi an toàn, server phải giữ sequence ổn định và nối lịch sử với live không có gap; client phải checkpoint sau khi xử lý bền vững, deduplicate event replay và retry có backoff theo status. gRPC vận chuyển stream, còn khả năng phát lại và tính idempotent thuộc thiết kế ứng dụng.
