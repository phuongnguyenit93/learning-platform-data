# Xử lý sự kiện được giao nhiều lần mà không triển khai trùng

## 1. Vì sao một sự kiện có thể kích hoạt nhiều lần triển khai?

Trong CI/CD, một lần push, pull request được hợp nhất, tag được tạo hoặc yêu cầu phát hành có thể đi qua webhook, hàng đợi, scheduler và nhiều worker. Hệ thống phân tán thường giao sự kiện theo cơ chế có thể thử lại. Nếu bên nhận không trả lời kịp, bị ngắt kết nối hoặc gặp lỗi sau khi đã bắt đầu xử lý, nguồn phát có thể gửi lại cùng sự kiện.

Một số tình huống thường gặp:

- Git provider gửi lại webhook vì endpoint phản hồi chậm hoặc trả mã lỗi.
- Queue giao lại message khi consumer chưa xác nhận hoàn tất trước visibility timeout.
- Worker đã triển khai xong nhưng bị dừng trước khi ghi nhận trạng thái thành công.
- Người vận hành bấm retry trong khi lần chạy trước vẫn còn hoạt động.
- Hai pipeline cùng nhận một commit và cùng nhắm tới một môi trường.
- Scheduler chạy lại job do lần trước không ghi nhận heartbeat hoặc completion.
- Một webhook mới có ID khác nhưng vẫn đại diện cho cùng một yêu cầu phát hành.

Nếu mỗi lần nhận sự kiện đều tạo một deployment mới, hệ thống có thể triển khai trùng, tranh quyền trên môi trường, ghi đè phiên bản mới bằng phiên bản cũ hoặc thực hiện side effect nhiều lần. Vì vậy, consumer cần xử lý được việc một sự kiện xuất hiện nhiều lần và nhiều worker cùng xử lý gần như đồng thời.

Mục tiêu là biến việc giao lặp thành một thao tác có kết quả ổn định: cùng một ý định triển khai không tạo ra nhiều lần thay đổi ngoài mong muốn. Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, điều này bảo vệ tính nhất quán giữa sự kiện Git, pipeline, artifact, môi trường và release record.

## 2. Phân biệt giao lặp và yêu cầu mới

Không phải mọi lần nhận sự kiện giống nhau đều là duplicate. Cần phân biệt:

- **Delivery duplicate:** cùng một lần phát sinh được gửi lại, thường có cùng event ID hoặc delivery ID.
- **Semantic duplicate:** nhiều sự kiện khác ID nhưng biểu diễn cùng một ý định nghiệp vụ, ví dụ hai webhook cùng yêu cầu deploy cùng commit vào cùng môi trường.
- **Concurrent execution:** hai worker bắt đầu xử lý cùng một sự kiện hoặc cùng một release gần như đồng thời.
- **Intentional rerun:** người vận hành chủ động yêu cầu chạy lại một thao tác, dù commit và artifact không đổi.
- **Stale event:** sự kiện hợp lệ nhưng đã cũ; một release mới hơn đã được triển khai trước đó.

Các trường hợp này cần cách xử lý khác nhau. Event ID phù hợp để nhận diện delivery duplicate. Một idempotency key theo nghiệp vụ giúp nhận diện semantic duplicate. Lock hoặc lease điều phối concurrent execution. Release sequence hoặc revision check ngăn stale event ghi đè trạng thái mới. Rerun có chủ đích cần một operation ID mới hoặc một cờ cho phép chạy lại.

Nếu chỉ deduplicate bằng event ID, hai webhook khác ID cho cùng một commit vẫn có thể tạo hai pipeline. Nếu chỉ deduplicate bằng commit SHA, một lần rollback có chủ đích về commit cũ có thể bị chặn nhầm. Khóa chống trùng phải phản ánh đúng ý định mà nhóm muốn thực hiện một lần.

## 3. Delivery semantics: at-most-once, at-least-once và effectively-once

Hệ thống giao sự kiện thường có một trong các mô hình:

| Mô hình | Đặc điểm | Rủi ro |
|---|---|---|
| At-most-once | Sự kiện được giao tối đa một lần | Có thể mất sự kiện nếu lỗi xảy ra trước khi xử lý |
| At-least-once | Sự kiện được giao lại cho đến khi được xác nhận | Consumer phải xử lý duplicate |
| Exactly-once | Hệ thống cố bảo đảm một hiệu ứng chỉ xảy ra một lần trong phạm vi xác định | Khó bảo đảm xuyên suốt nhiều hệ thống độc lập |

Trong thực tế, webhook và message queue thường dùng at-least-once để tránh mất sự kiện. Vì thế, consumer nên giả định một event có thể đến nhiều lần.

Khái niệm exactly-once cần được dùng thận trọng. Broker có thể hỗ trợ giao dịch hoặc deduplication trong phạm vi riêng, nhưng nếu consumer còn gọi API cloud, registry, database khác hoặc gửi thông báo thì không có một transaction chung bao trùm tất cả. Một thiết kế thực tế thường hướng đến **effectively-once**: nhận lặp vẫn được chấp nhận, nhưng nhờ khóa duy nhất, idempotency key, trạng thái và đối soát, hiệu ứng nghiệp vụ cuối cùng không bị nhân đôi.

## 4. Idempotency là nền tảng

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng đầu vào mà trạng thái cuối cùng vẫn giống như thực hiện một lần.

Ví dụ:

- Đặt desired image của môi trường thành một digest cụ thể là thao tác có thể lặp lại.
- Tạo một release record với khóa duy nhất cho cùng một release intent là thao tác có thể lặp lại.
- Gán feature flag về trạng thái false là thao tác idempotent nếu API thực hiện kiểu set.
- Tăng số replica thêm một đơn vị không idempotent vì gọi hai lần sẽ tăng hai lần.

So sánh:

~~~text
Không idempotent:
  POST /deploy
  -> mỗi lần gọi tạo một deployment mới

Idempotent theo desired state:
  PUT /environments/staging
  body: { "artifactDigest": "sha256:..." }
  -> nhiều lần đặt cùng digest vẫn hướng tới một trạng thái đích
~~~

Tên HTTP method không tự bảo đảm idempotency. Một API POST vẫn có thể hỗ trợ idempotency key; một API PUT có thể gây side effect không an toàn nếu được thiết kế sai. Cần hiểu hợp đồng của thao tác thực tế.

Trong CI/CD, nên ưu tiên mô tả trạng thái mong muốn, chẳng hạn môi trường X phải chạy artifact digest Y, thay vì chỉ phát lệnh "triển khai thêm một lần".

## 5. Thiết kế idempotency key

Idempotency key là định danh ổn định cho một ý định xử lý. Consumer dùng key này để nhận biết một yêu cầu đã được tiếp nhận hoặc hoàn tất.

Một key có thể được tạo từ các thành phần:

- Repository hoặc project.
- Loại sự kiện và hành động.
- Commit SHA hoặc release ID.
- Artifact digest.
- Môi trường đích.
- Tên dịch vụ hoặc component.
- Operation ID nếu là lần chạy lại có chủ đích.

Ví dụ key theo ý định deploy:

~~~text
deploy:
  repository=payments-api
  environment=production
  artifact=sha256:abc...
  operation=release-2026-042
~~~

Trong triển khai thực tế, có thể chuẩn hóa các trường rồi băm thành một chuỗi ngắn. Không nên dùng thời điểm nhận webhook làm thành phần chính vì mỗi lần retry có thể có timestamp khác nhau.

### 5.1. Chọn phạm vi key

Key quá rộng có thể chặn một thao tác hợp lệ. Ví dụ, chỉ dùng commit SHA sẽ khiến cùng một commit không thể được deploy lại vào staging sau khi đã deploy vào dev.

Key quá hẹp lại không chặn được semantic duplicate. Ví dụ, dùng webhook delivery ID sẽ coi hai lần gửi cùng yêu cầu là hai thao tác khác nhau nếu provider tạo delivery ID mới.

Một số phạm vi tham khảo:

| Ý định | Thành phần key gợi ý |
|---|---|
| Xử lý một webhook delivery | Provider + delivery ID |
| Build một commit cho một pipeline | Repository + commit SHA + pipeline definition/version |
| Deploy artifact vào môi trường | Service + environment + artifact digest + release operation |
| Chạy migration một lần | Migration ID + database/tenant scope |
| Xử lý một nghiệp vụ | Tenant + business operation ID |
| Rerun có chủ đích | Operation ID mới + mục tiêu phát hành |

Cần quyết định rõ rerun có nghĩa là tiếp tục thao tác cũ, thử lại thao tác lỗi hay tạo một release operation mới. Ba trường hợp này không nên vô tình dùng chung một key.

## 6. Deduplication store và ràng buộc duy nhất

Consumer cần lưu dấu vết của sự kiện đã nhận. Có thể dùng database quan hệ, key-value store hoặc cơ chế deduplication của broker. Với luồng triển khai cần audit, một bảng có trạng thái thường hữu ích hơn một cache boolean.

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name   VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(300) NOT NULL,
    event_id        VARCHAR(200),
    payload_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(24) NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    result_ref      VARCHAR(300),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    owner_id        VARCHAR(120),
    lease_until     TIMESTAMPTZ,
    fencing_token  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (consumer_name, idempotency_key)
);
~~~

Khóa chính duy nhất giúp hai worker không thể đồng thời tạo hai bản ghi cho cùng một consumer và key. Cột consumer_name cho phép nhiều consumer độc lập xử lý cùng một event theo mục đích riêng.

Payload hash giúp phát hiện trường hợp cùng key nhưng nội dung khác nhau. Nếu key được tạo từ các trường không đủ, hai yêu cầu khác nhau có thể bị gộp nhầm. Khi phát hiện cùng key nhưng payload hash khác, cần đánh dấu conflict và điều tra thay vì âm thầm bỏ qua.

### 6.1. Nhận sự kiện bằng insert nguyên tử

Ví dụ:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    idempotency_key,
    event_id,
    payload_hash,
    status
)
VALUES (
    :consumer,
    :key,
    :event_id,
    :payload_hash,
    'RECEIVED'
)
ON CONFLICT (consumer_name, idempotency_key) DO NOTHING
RETURNING idempotency_key;
~~~

Nếu câu lệnh trả về một dòng, worker đã tạo được bản ghi nhận diện key. Nếu không có dòng trả về, key đã tồn tại và worker phải đọc trạng thái hiện có để quyết định bỏ qua, chờ, tiếp tục retry hoặc trả kết quả đã hoàn tất.

Không nên dùng thao tác kiểu "SELECT xem có chưa rồi mới INSERT" mà không có unique constraint hoặc lock phù hợp. Hai worker có thể cùng SELECT thấy chưa tồn tại rồi cùng INSERT. Đây là race condition kinh điển.

## 7. Trạng thái xử lý và state machine

Một bản ghi deduplication nên thể hiện tiến trình, không chỉ có true/false.

Các trạng thái thường gặp:

- **RECEIVED:** đã tiếp nhận sự kiện.
- **PROCESSING:** một worker đang sở hữu lượt xử lý hiện tại.
- **SUCCEEDED:** hiệu ứng cần thiết đã hoàn tất và được xác minh.
- **RETRYABLE_FAILED:** thất bại tạm thời, có thể thử lại.
- **TERMINAL_FAILED:** lỗi không thể tự retry, cần can thiệp.
- **CONFLICT:** cùng idempotency key nhưng payload hoặc ý định không nhất quán.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> SUCCEEDED
    PROCESSING --> RETRYABLE_FAILED
    PROCESSING --> TERMINAL_FAILED
    PROCESSING --> CONFLICT
    RETRYABLE_FAILED --> PROCESSING
    PROCESSING --> PROCESSING: lease hết hạn và worker khác claim
    SUCCEEDED --> [*]
    TERMINAL_FAILED --> [*]
    CONFLICT --> [*]
~~~

Khi nhận duplicate:

| Trạng thái hiện tại | Hành động gợi ý |
|---|---|
| SUCCEEDED | Trả lại kết quả đã lưu, không thực hiện side effect lần nữa |
| PROCESSING và lease còn hạn | Không khởi chạy song song; trả accepted/in-progress hoặc retry sau |
| RETRYABLE_FAILED | Claim lại theo policy và tăng attempt |
| TERMINAL_FAILED | Không retry tự động vô hạn; yêu cầu xử lý |
| CONFLICT | Cách ly và điều tra key/payload |
| PROCESSING nhưng lease hết hạn | Có thể claim lại sau khi xác minh quyền sở hữu đã hết |

Không nên đánh dấu SUCCEEDED ngay khi vừa nhận event. Nếu worker chết trước khi thực hiện tác vụ, sự kiện sẽ bị coi là hoàn tất dù chưa có hiệu ứng. Cũng không nên đánh dấu hoàn tất sau khi chỉ gọi một API trả HTTP 202 nếu tác vụ bất đồng bộ phía sau chưa thực sự đạt trạng thái mong muốn; cần xác định rõ completion semantics.

## 8. Tránh race condition khi nhiều worker cùng nhận một sự kiện

Hai worker có thể cùng nhận một message do retry hoặc queue redelivery. Chỉ kiểm tra trạng thái ở ứng dụng không đủ để ngăn cả hai bắt đầu.

Các cơ chế phổ biến:

- Unique constraint trên idempotency key.
- Atomic insert hoặc compare-and-set.
- Row-level lock trong transaction ngắn.
- Lease có thời hạn cho worker sở hữu.
- Distributed lock cho tài nguyên dùng chung.
- Fencing token để chặn worker cũ tiếp tục ghi sau khi mất quyền.

Với database, có thể claim bản ghi bằng UPDATE có điều kiện:

~~~sql
UPDATE processed_events
SET status = 'PROCESSING',
    attempt_count = attempt_count + 1,
    owner_id = :worker_id,
    lease_until = now() + INTERVAL '60 seconds',
    fencing_token = fencing_token + 1,
    updated_at = now()
WHERE consumer_name = :consumer
  AND idempotency_key = :key
  AND (
       status IN ('RECEIVED', 'RETRYABLE_FAILED')
       OR (status = 'PROCESSING' AND lease_until < now())
  )
RETURNING idempotency_key, owner_id, lease_until, fencing_token;
~~~

Chỉ worker nhận được một dòng RETURNING mới được xem là đã claim. Worker cần dùng owner_id và fencing_token trả về cho mọi lần gia hạn lease hoặc cập nhật trạng thái tiếp theo. Câu lệnh phải được thực hiện nguyên tử trong database; thời hạn lease thực tế cần phù hợp với heartbeat và thời gian xử lý.

Không giữ transaction database mở trong suốt một deployment kéo dài. Hãy claim trong transaction ngắn, thực hiện công việc bên ngoài, sau đó cập nhật trạng thái bằng điều kiện owner/token để tránh ghi đè tiến trình của worker khác.

## 9. Lease, heartbeat và fencing token

Một lock vĩnh viễn có thể khiến hệ thống bị kẹt nếu worker chết. Lease giải quyết bằng cách cho quyền sở hữu hết hạn sau một khoảng thời gian.

Một lease thường có:

- Resource key, ví dụ service + environment.
- Owner ID hoặc worker ID.
- Thời điểm hết hạn.
- Heartbeat để gia hạn khi còn xử lý.
- Fencing token hoặc generation tăng đơn điệu.

Ví dụ:

~~~text
resource: payments-api:production
owner: worker-17
lease_until: 2026-11-18T09:15:00Z
fencing_token: 1842
~~~

Khi worker mới claim sau khi lease hết hạn, hệ thống cấp fencing token lớn hơn, ví dụ 1843. Mọi thao tác ghi tiếp theo cần kiểm tra token. Nếu worker cũ tỉnh lại sau khi bị pause lâu và cố ghi với token 1842, hệ thống đích từ chối vì token đã cũ.

Lease đơn thuần không đủ ngăn stale worker. Một worker có thể bị treo, lease hết hạn, worker khác tiếp quản, rồi worker cũ tiếp tục chạy. Fencing token chỉ phát huy tác dụng khi thành phần nhận lệnh kiểm tra và từ chối token cũ. Nếu API triển khai bên ngoài không hỗ trợ fencing, cần thêm kiểm tra generation hoặc desired revision ở lớp điều phối.

Heartbeat cũng không chứng minh worker đang khỏe về mặt nghiệp vụ. Cần giới hạn số lần gia hạn và có cơ chế xử lý worker không còn tiến triển.

## 10. Phân biệt event deduplication với deployment lock

Hai cơ chế giải quyết hai vấn đề khác nhau:

- **Event deduplication:** cùng một ý định xử lý không được tạo thành nhiều công việc độc lập.
- **Deployment lock:** tại một thời điểm chỉ có một tiến trình được thay đổi một môi trường hoặc tài nguyên có xung đột.

Có thể có hai release khác nhau, mỗi release có idempotency key riêng, nhưng cùng deploy vào production. Deduplication không ngăn chúng chạy đồng thời. Ngược lại, lock chỉ tuần tự hóa thao tác; sau khi worker đầu hoàn tất, worker thứ hai vẫn có thể triển khai cùng artifact thêm lần nữa nếu không có deduplication hoặc desired-state check.

Một thiết kế thường cần cả hai:

1. Nhận event và tạo operation theo idempotency key.
2. Claim operation để chỉ một worker xử lý key đó.
3. Lấy lock theo service/environment trước khi thay đổi môi trường.
4. Kiểm tra trạng thái thực và release hiện tại.
5. Thực hiện thay đổi theo desired state.
6. Xác minh digest và trạng thái môi trường.
7. Ghi kết quả rồi giải phóng lock.

## 11. Điều phối các pipeline cùng nhắm tới một môi trường

Một môi trường như staging hoặc production thường chỉ nên có một deployment đang thay đổi tại một thời điểm, trừ khi hệ thống hỗ trợ các vùng độc lập.

Lock key nên thể hiện phạm vi xung đột:

~~~text
deployment-lock:payments-api:production
deployment-lock:catalog-api:production
deployment-lock:payments-api:staging
~~~

Trong ví dụ này, deploy payments-api production không chặn catalog-api production nếu hai dịch vụ không chia sẻ tài nguyên xung đột. Nhưng hai lần deploy payments-api production cần được tuần tự hóa.

Các nền tảng CI thường có tính năng concurrency group hoặc environment deployment queue. Cần cấu hình theo service và environment, không gom mọi pipeline vào một lock toàn cục nếu không cần thiết.

Nếu dùng database lock hoặc distributed lock service, cần xác định:

- Lock key và thời hạn.
- Cơ chế renew/heartbeat.
- Hành vi khi worker chết.
- Fencing token hoặc generation.
- Thời điểm giải phóng lock.
- Cách phát hiện lock bị giữ quá lâu.
- Quy tắc xử lý thao tác thủ công ngoài pipeline.

## 12. Ngăn release cũ ghi đè release mới

Một race condition khác xảy ra khi pipeline cũ chạy chậm hơn pipeline mới.

Ví dụ:

1. Commit A tạo pipeline A.
2. Commit B mới hơn tạo pipeline B.
3. Pipeline B deploy trước và production chạy B.
4. Pipeline A hoàn tất muộn và deploy A sau đó.

Dù mỗi pipeline chỉ chạy một lần, kết quả cuối cùng vẫn sai vì release cũ ghi đè release mới.

Cần kiểm tra tính mới của release ngay trước khi thay đổi môi trường. Có thể dùng:

- Commit ancestry hoặc branch head hiện tại.
- Release sequence/generation tăng đơn điệu.
- Desired revision được lưu trong deployment controller.
- Compare-and-set trên current deployment revision.
- Policy cho phép rollback có chủ đích với operation ID riêng.

Không nên chỉ so timestamp do các máy có thể lệch giờ. Sequence hoặc revision do một nguồn tin cậy cấp sẽ rõ ràng hơn.

Một thao tác rollback về artifact cũ vẫn phải được cho phép khi có phê duyệt. Vì vậy, "artifact có SHA nhỏ hơn hoặc cũ hơn" không đủ để từ chối; cần phân biệt stale pipeline tự phát với rollback intent được tạo có chủ đích.

## 13. Xử lý retry và acknowledgement đúng thời điểm

Với message queue, consumer thường nhận message, xử lý rồi gửi acknowledgement. Nếu ack trước khi hiệu ứng hoàn tất, message có thể bị mất khi worker chết. Nếu ack sau khi hiệu ứng hoàn tất nhưng worker chết trước ack, queue sẽ giao lại và consumer phải deduplicate.

Một trình tự phổ biến:

1. Nhận message.
2. Xác minh chữ ký/nguồn và schema.
3. Tạo hoặc đọc idempotency record.
4. Claim quyền xử lý.
5. Thực hiện công việc.
6. Xác minh kết quả.
7. Ghi trạng thái SUCCEEDED.
8. Ack message.

Nếu ghi SUCCEEDED và ack không nằm trong cùng một transaction với broker, vẫn có cửa sổ lỗi giữa hai thao tác. Đây là lý do deduplication cần tồn tại bền vững qua lần giao lại.

Với queue có visibility timeout, thời gian timeout phải phù hợp với thời gian xử lý hoặc được gia hạn. Nếu timeout quá ngắn, queue có thể giao message cho worker thứ hai trong khi worker đầu vẫn đang làm. Dù vậy, không nên dựa vào timeout để bảo đảm duy nhất; vẫn cần claim nguyên tử và idempotency.

## 14. Backoff, retry budget và dead-letter queue

Retry vô hạn và ngay lập tức có thể làm tăng tải khi hệ thống đang lỗi. Một chính sách retry nên có:

- Exponential backoff.
- Jitter để tránh nhiều worker retry cùng thời điểm.
- Số lần thử tối đa hoặc retry budget.
- Phân biệt lỗi tạm thời và lỗi vĩnh viễn.
- Timeout cho từng lần gọi.
- Dead-letter queue hoặc hàng chờ cách ly.
- Khả năng replay có kiểm soát sau khi sửa lỗi.

Ví dụ lịch retry có jitter:

~~~text
attempt 1: gần như ngay lập tức
attempt 2: khoảng vài giây
attempt 3: khoảng vài chục giây
attempt 4: khoảng vài phút
sau retry budget: chuyển sang dead-letter
~~~

Không nên retry lỗi validation, chữ ký webhook sai hoặc payload không hỗ trợ như thể đó là lỗi mạng. Những lỗi này thường cần cách ly và điều tra. Ngược lại, timeout hoặc HTTP 503 có thể retry nếu thao tác idempotent.

Khi đưa message từ dead-letter trở lại, giữ nguyên event identity để dedupe nhận ra lần replay, trừ khi người vận hành đang tạo một operation mới có chủ đích. Cần ghi người replay, lý do và liên kết tới incident hoặc change request.

## 15. Transactional inbox và outbox

Khi một service nhận event và cập nhật database của chính nó, mẫu **transactional inbox** giúp lưu việc nhận event và thay đổi nghiệp vụ trong cùng transaction.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO event_inbox (
    consumer_name,
    idempotency_key,
    received_at
)
VALUES (
    :consumer,
    :key,
    now()
)
ON CONFLICT DO NOTHING;

-- Chỉ áp dụng cập nhật nghiệp vụ nếu INSERT thực sự tạo một dòng.
-- Cập nhật trạng thái và đánh dấu inbox trong cùng transaction.

COMMIT;
~~~

Đoạn SQL là mã giả về trình tự. Trong triển khai thật cần kiểm tra số dòng INSERT và chỉ thực hiện cập nhật nghiệp vụ khi worker sở hữu key. Nếu insert inbox và cập nhật nghiệp vụ nằm cùng transaction, transaction rollback sẽ không để lại dấu nhận event giả.

**Transactional outbox** giải quyết chiều phát event: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction, rồi publisher gửi event từ outbox. Publisher có thể gửi lại nếu chết sau khi gửi nhưng trước khi đánh dấu đã gửi, nên consumer vẫn phải idempotent.

Inbox/outbox giảm cửa sổ mất hoặc nhân đôi giữa database và broker, nhưng không biến toàn bộ chuỗi nhiều hệ thống thành một transaction exactly-once.

## 16. Xử lý side effect bên ngoài

Một deployment thường gọi nhiều dịch vụ:

- Container registry hoặc artifact repository.
- Cloud provider API.
- Kubernetes API.
- DNS hoặc load balancer.
- Feature flag service.
- Notification hoặc chat service.
- Hệ thống ghi release record.

Không phải API nào cũng hỗ trợ idempotency key. Cần thiết kế theo khả năng thực tế:

- Dùng API kiểu set desired state nếu có.
- Gửi idempotency key nếu nhà cung cấp hỗ trợ.
- Ghi operation ID trong metadata hoặc annotation.
- Đọc trạng thái trước khi tạo tài nguyên mới.
- Sau timeout, truy vấn xem thao tác trước đã thành công chưa trước khi gọi lại.
- Ghi nhận external resource ID để tiếp tục hoặc đối soát.
- Dùng retry có giới hạn và xử lý kết quả không xác định.

Ví dụ, nếu request deploy bị timeout, không thể kết luận cloud provider chưa nhận lệnh. Gọi lại ngay có thể tạo một deployment thứ hai. Trước tiên hãy truy vấn deployment theo operation ID, release ID hoặc desired digest để xác định trạng thái.

## 17. Webhook Git và sự kiện CI/CD

Webhook thường chứa delivery ID, event type, repository, ref, commit SHA và metadata. Consumer nên:

1. Xác minh chữ ký webhook theo hướng dẫn của provider.
2. Kiểm tra timestamp hoặc cơ chế chống replay nếu provider hỗ trợ.
3. Lưu delivery ID để phát hiện gửi lại cùng delivery.
4. Tạo semantic idempotency key theo repository, event/action, commit hoặc release intent và environment.
5. Kiểm tra branch/ref có còn là mục tiêu hợp lệ.
6. Đưa operation vào hàng đợi.
7. Trả lời webhook nhanh sau khi đã lưu bền vững, không giữ request mở trong toàn bộ thời gian deploy.

Ví dụ key cho build:

~~~text
build:repository=payments-api:commit=4f8c2a1:pipeline=v3
~~~

Ví dụ key cho deploy:

~~~text
deploy:service=payments-api:environment=staging:artifact=sha256:abc123:operation=release-42
~~~

Nếu cùng commit cần được deploy lại có chủ đích, tạo operation ID mới và lưu lý do. Không nên thay đổi key một cách tùy tiện chỉ để vượt qua deduplication, vì điều đó có thể che giấu retry hoặc duplicate không mong muốn.

## 18. Kiểm tra trạng thái mong muốn trước khi triển khai

Một consumer tốt không chỉ hỏi "event này đã xử lý chưa?" mà còn hỏi "môi trường hiện đã ở trạng thái mà event yêu cầu chưa?".

Ví dụ, release record nói production đã chạy digest D. Một webhook duplicate yêu cầu deploy D đến production. Consumer đọc actual state và xác nhận môi trường đã chạy D thì có thể đánh dấu operation là hoàn tất mà không triển khai lại.

Ngược lại, nếu môi trường đang chạy digest khác, consumer phải xác định operation có còn mới nhất và được phép thực hiện không.

Một luồng reconciliation:

~~~mermaid
flowchart TD
    A["Nhận event"] --> B["Xác minh và tạo idempotency key"]
    B --> C{"Key đã SUCCEEDED?"}
    C -- "Có" --> D["Trả kết quả đã lưu"]
    C -- "Không" --> E["Claim operation"]
    E --> F["Lấy lock service/environment"]
    F --> G["Đọc desired và actual revision"]
    G --> H{"Môi trường đã đúng digest?"}
    H -- "Có" --> I["Ghi SUCCEEDED, không deploy lại"]
    H -- "Không" --> J{"Operation còn hợp lệ và mới nhất?"}
    J -- "Không" --> K["Bỏ qua stale event"]
    J -- "Có" --> L["Apply desired state"]
    L --> M["Verify digest và health"]
    M --> N["Ghi kết quả và giải phóng lock"]
~~~

Reconciliation hữu ích vì nó xử lý được cả trường hợp worker không biết lần trước đã đi đến đâu. Thay vì mù quáng lặp side effect, nó quan sát actual state rồi đưa hệ thống về desired state.

## 19. Phân biệt retry, replay và rerun thủ công

Ba hành động này cần được ghi nhận riêng:

| Hành động | Ý nghĩa | Idempotency |
|---|---|---|
| Retry | Thử lại cùng operation sau lỗi tạm thời | Giữ nguyên key |
| Replay | Phát lại event đã lưu để xử lý lại theo logic consumer | Thường giữ event identity; có thể tăng replay attempt |
| Rerun | Người vận hành tạo yêu cầu chạy mới có chủ đích | Tạo operation ID mới và ghi lý do |

Nếu retry tạo key mới, consumer sẽ coi đó là công việc mới và có thể lặp side effect. Nếu rerun có chủ đích bị dùng lại key đã SUCCEEDED, consumer sẽ bỏ qua dù người vận hành muốn chạy một release operation mới.

Một giao diện vận hành tốt nên hiển thị event ID, idempotency key, trạng thái, số lần thử và operation ID. Khi chọn rerun, cần yêu cầu một ý định mới được ghi nhận rõ ràng.

## 20. Retention của deduplication record

Nếu xóa bản ghi deduplication quá sớm, một message cũ được replay sau đó có thể được coi như mới và thực hiện lại side effect.

Thời gian giữ record cần lớn hơn hoặc bằng:

- Thời gian retry tối đa của webhook/queue.
- Thời gian message có thể nằm trong backlog.
- Thời gian lưu dead-letter trước replay.
- Khoảng thời gian replay lịch sử theo quy trình vận hành.
- Thời gian cần để audit release hoặc nghiệp vụ.

Với thao tác có tác động lâu dài như deploy production hoặc chạy migration, nên lưu release/operation history bền vững thay vì chỉ dựa vào cache TTL ngắn.

Nếu cần dọn record, có thể chuyển dữ liệu cũ sang kho audit hoặc giữ một tombstone gồm key, kết quả và thời điểm. Không nên xóa record PROCESSING đang có lease còn hạn hoặc record liên quan tới incident chưa đóng.

## 21. Bảo mật và tính toàn vẹn của sự kiện

Idempotency không thay thế xác thực. Kẻ tấn công có thể gửi một payload giả với key hợp lệ hoặc cố tình làm đầy deduplication store.

Cần:

- Xác minh chữ ký webhook và nguồn phát.
- Kiểm tra schema, kích thước và trường bắt buộc.
- Ràng buộc event với repository/project được phép.
- Kiểm tra branch, tag và environment policy.
- Không lấy artifact hoặc command tùy ý từ payload chưa tin cậy.
- Giới hạn quyền worker và credential theo môi trường.
- Ghi audit log nhưng không lưu secret trong payload log.
- Giới hạn tốc độ và phát hiện event bất thường.
- Phân quyền thao tác replay/rerun.

Payload hash giúp phát hiện cùng key nhưng nội dung khác. Khi có xung đột, không được ghi đè bản ghi gốc hoặc tự chọn payload đến sau mà không có quy tắc xác minh.

## 22. Quan sát và xử lý sự cố

Để vận hành deduplication, cần đo cả duplicate và trạng thái công việc.

Các metric hữu ích:

- Tổng event nhận được theo loại và nguồn.
- Số delivery duplicate và semantic duplicate.
- Số operation được tạo mới, bỏ qua hoặc trả kết quả cũ.
- Số worker claim thành công/thất bại.
- Số lease hết hạn và fencing rejection.
- Retry count, retry age và dead-letter count.
- Thời gian ở trạng thái PROCESSING.
- Deployment operation bị chặn do lock.
- Số stale event bị bỏ qua.
- Tỷ lệ môi trường đã ở đúng desired digest khi event đến.

Log nên có event ID, idempotency key đã che hoặc băm, operation ID, repository, commit SHA, artifact digest, environment, worker ID và attempt. Tránh ghi nguyên payload nếu chứa thông tin nhạy cảm.

Một cảnh báo cần được tạo khi operation PROCESSING quá lâu, lease liên tục hết hạn, duplicate tăng bất thường, event nằm trong dead-letter hoặc hai pipeline liên tục tranh cùng một environment lock.

## 23. Ví dụ luồng xử lý deploy an toàn

Giả sử Git provider gửi webhook cho commit mới của service checkout. Endpoint nhận webhook hai lần vì lần đầu phản hồi chậm.

Luồng mong muốn:

1. Cả hai request đều được xác minh chữ ký.
2. Delivery ID và semantic key được tính từ repository, commit, service, environment và release operation.
3. Request đầu tạo operation; request sau gặp unique constraint và đọc trạng thái của operation hiện có.
4. Chỉ một worker claim operation.
5. Worker lấy lock cho checkout/production.
6. Worker kiểm tra branch head và desired artifact digest.
7. Nếu môi trường đã chạy đúng digest, worker ghi nhận hoàn tất mà không gọi deploy lần nữa.
8. Nếu chưa đúng, worker yêu cầu controller đặt desired state về digest đã phê duyệt.
9. Worker chờ rollout và xác minh image digest, health check và policy.
10. Worker ghi SUCCEEDED, release lock và ack message.
11. Request duplicate nhận lại trạng thái/result của operation đã tồn tại.

Nếu worker bị dừng sau khi controller đã nhận desired state nhưng trước khi ghi SUCCEEDED, message có thể được giao lại. Worker mới claim lại sau khi lease hết hạn, đọc actual state và nhận thấy digest đã đúng; nó hoàn tất record mà không tạo deployment thứ hai.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra event ID | Bỏ sót semantic duplicate có delivery ID khác | Thêm idempotency key theo ý định nghiệp vụ |
| SELECT rồi INSERT không có unique constraint | Hai worker có thể cùng xử lý | Dùng atomic insert/claim và unique key |
| Đánh dấu hoàn tất trước side effect | Worker chết khiến công việc bị mất | Ghi SUCCEEDED sau khi xác minh hiệu ứng |
| Ack queue trước khi xử lý bền vững | Message mất khi worker lỗi | Ack sau khi trạng thái đã được lưu an toàn |
| Giữ database transaction suốt deployment | Lock lâu và cạn connection | Claim ngắn, xử lý ngoài transaction, cập nhật có điều kiện |
| Chỉ dùng lease không có fencing | Worker cũ có thể ghi sau khi mất lease | Dùng generation/fencing và kiểm tra ở đích |
| Chỉ dùng deployment lock | Cùng release vẫn có thể deploy lặp tuần tự | Kết hợp lock với idempotency/digest check |
| Chỉ dùng deduplication | Hai release khác nhau vẫn có thể deploy đồng thời | Khóa theo service/environment |
| Retry tạo idempotency key mới | Side effect bị lặp | Giữ key cho retry; tạo key mới chỉ cho rerun có chủ đích |
| Xóa dedupe record quá sớm | Replay cũ có thể thực hiện lại | Retention theo retry, backlog, replay và audit |
| Cho pipeline cũ ghi đè release mới | Môi trường quay về revision lỗi thời | Kiểm tra generation hoặc desired revision |
| Coi timeout là thất bại chắc chắn | Gọi lại có thể tạo thao tác thứ hai | Đọc trạng thái external operation trước khi retry |

## 25. Checklist xử lý sự kiện được giao nhiều lần

**Định danh và tiếp nhận**

- [ ] Đã xác minh nguồn và chữ ký sự kiện.
- [ ] Có event ID và idempotency key phù hợp.
- [ ] Key phân biệt service, environment và operation scope.
- [ ] Payload hash được kiểm tra khi cùng key xuất hiện với nội dung khác.
- [ ] Retry, replay và rerun được phân biệt.

**Deduplication và concurrency**

- [ ] Có unique constraint hoặc cơ chế atomic claim.
- [ ] Có state machine và trạng thái lỗi rõ ràng.
- [ ] Worker chỉ xử lý khi claim thành công.
- [ ] Có lease/heartbeat cho công việc dài.
- [ ] Có fencing token hoặc kiểm tra generation khi cần.
- [ ] Deployment lock được scope theo service/environment.
- [ ] Stale event không ghi đè revision mới.

**Side effect và phục hồi**

- [ ] Thao tác ưu tiên desired-state/idempotent API.
- [ ] Timeout được xử lý bằng truy vấn trạng thái trước khi gọi lại.
- [ ] DB effect và inbox record có transaction phù hợp.
- [ ] Outbox/consumer hỗ trợ duplicate và retry.
- [ ] Ack chỉ sau khi trạng thái được lưu bền vững.
- [ ] Retry có backoff, budget và dead-letter.
- [ ] Deduplication record được giữ đủ lâu.
- [ ] Replay/rerun có audit và quyền phù hợp.

**Quan sát**

- [ ] Có metric duplicate, retry, lock contention và lease expiry.
- [ ] Log có event/operation/release identity.
- [ ] Có cảnh báo operation bị kẹt hoặc stale event.
- [ ] Có cách đối soát actual digest với desired digest.
- [ ] Có runbook xử lý conflict và replay.

## 26. Kết luận

Sự kiện được giao nhiều lần là tình huống bình thường trong hệ thống webhook, queue và pipeline phân tán. Consumer cần giả định delivery có thể lặp, hai worker có thể tranh nhau và timeout không chứng minh thao tác bên ngoài chưa xảy ra.

Idempotency key và deduplication record nhận diện cùng một ý định; unique constraint và atomic claim ngăn race condition; lease và fencing điều phối worker; deployment lock tuần tự hóa thay đổi trên môi trường; desired-state reconciliation giúp tiếp tục an toàn sau khi worker bị dừng giữa chừng. Retry giữ nguyên operation identity, còn rerun có chủ đích tạo operation mới với audit trail.

Không có một khóa duy nhất thay thế được mọi cơ chế. Khi kết hợp đúng phạm vi định danh, trạng thái xử lý, kiểm tra release revision và xác minh actual state, pipeline có thể nhận lại cùng sự kiện nhiều lần mà vẫn giữ một hiệu ứng triển khai nhất quán, có thể truy vết và phục hồi.
