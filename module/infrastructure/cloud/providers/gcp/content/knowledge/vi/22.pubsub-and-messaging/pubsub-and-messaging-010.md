# Flow control, batching và tối ưu publisher, subscriber

Trong một nền tảng học trực tuyến, dịch vụ đăng ký khóa học có thể phát hàng chục nghìn sự kiện `EnrollmentCreated` trong giờ cao điểm. **Publisher** gửi quá nhanh sẽ tích hàng đợi trong RAM rồi timeout; **subscriber** nhận quá nhiều sẽ tăng độ trễ xử lý, hết connection đến database và liên tục bị phát lại message. Chỉ tăng số worker không luôn giải quyết được vấn đề.

**Google Cloud Pub/Sub** là dịch vụ nhắn tin bất đồng bộ được quản lý, giúp tách nơi phát sự kiện khỏi nơi xử lý. Trong chương **Pub/Sub và thông điệp** thuộc module **CLOUD_PROVIDERS_GCP**, bài học này hướng dẫn điều chỉnh **batching**, **flow control**, **concurrency** và **acknowledgment** để cân bằng thông lượng, độ trễ, khả năng phục hồi và chi phí. Các ví dụ liên hệ với publisher trên Cloud Run/GKE/Compute Engine, subscriber cập nhật cơ sở dữ liệu và giám sát độ tin cậy của toàn hệ thống.

Sau bài học, bạn có thể:

1. Phân biệt batching publisher với flow control ở publisher và subscriber.
2. Cấu hình giới hạn số message, byte và thời gian chờ batch bằng client library.
3. Thiết kế cơ chế backpressure để tránh tích tụ message trong bộ nhớ hoặc làm quá tải database.
4. Điều chỉnh StreamingPull, xử lý ack/nack, lease extension và redelivery một cách an toàn.
5. Đo backlog, oldest unacked age, publish/ack latency và chi phí để chọn cấu hình.
6. Thực hành publish/subscribe có kiểm soát và giải các bài toán sizing.

## 1. Đường đi của message và ba cơ chế điều tiết

~~~mermaid
flowchart LR
    A["Ứng dụng tạo sự kiện"] --> PF["Publisher flow control<br/>giới hạn outstanding"]
    PF --> BAT["Publisher batching<br/>gom message theo count/bytes/time"]
    BAT --> TOP["Pub/Sub topic"]
    TOP --> SUB["Subscription + backlog"]
    SUB --> SF["Subscriber flow control<br/>giới hạn unacked messages/bytes"]
    SF --> WORK["Callback / worker<br/>xử lý nghiệp vụ"]
    WORK -->|"Thành công: ack"| SUB
    WORK -. "Lỗi: nack / hết ack deadline" .-> SUB
~~~

| Cơ chế | Nơi hoạt động | Giới hạn điều gì? | Không tự giải quyết |
| --- | --- | --- | --- |
| **Publisher batching** | Client publisher | Số message, tổng bytes hoặc thời gian chờ trước khi gửi một publish request. | RAM tăng vô hạn khi input đến nhanh hơn tốc độ publish. |
| **Publisher flow control** | Client publisher | Số message/bytes **chưa được hoàn tất publish**, và hành vi khi đạt ngưỡng. | Quota dịch vụ và tốc độ xử lý của subscriber. |
| **Subscriber flow control** | Client pull/StreamingPull | Số message/bytes **đã nhận nhưng chưa ack/nack**. | Publisher gửi quá nhiều hoặc thiếu subscriber capacity kéo dài. |
| **Subscriber concurrency** | Process/executor/thread pool | Số handler có thể xử lý thực sự đồng thời. | Backlog nếu downstream/database vẫn không theo kịp. |
| **Ack deadline/lease management** | Subscription + client | Khoảng thời gian Pub/Sub chờ ack trước khi phát lại; SDK có thể tự gia hạn. | Giao dịch không idempotent hoặc xử lý thất bại lâu dài. |

Hai bên điều tiết **độc lập**: subscriber giảm tốc độ nhận không tự làm publisher ngừng gửi; message có thể tích trong **subscription backlog**. Khi publisher bị flow control chặn, nó cũng không đồng nghĩa subscription đã hết backlog. Muốn xử lý sự cố phải xác định hàng đợi đang nằm ở **client publisher**, **dịch vụ Pub/Sub**, hay **client subscriber**.

### 1.1. Phân biệt message, batch và subscription

- **Message** chứa dữ liệu `data` dạng bytes, attributes và metadata; có thể mang `ordering_key` nếu dùng message ordering.
- **Batch publish** là nhiều message cùng gửi trong **một API publish request**. Các message vẫn có message ID riêng sau khi publish thành công.
- **Topic** nhận message từ publisher; mỗi **subscription** có dòng phân phối và backlog riêng. Hai subscription cùng topic cần subscriber capacity riêng.
- **Outstanding publish** là message phía publisher đang đợi gửi/xác nhận; **outstanding receive** là message phía subscriber nhận nhưng chưa ack/nack.

Client library có thể khác nhau về mặc định, tên property và hỗ trợ từng cơ chế. Ví dụ trong bài dùng **Python `google-cloud-pubsub`** với thông số được đặt tường minh; khi sử dụng Java/Go/Node.js phải đối chiếu đúng SDK phiên bản đang chạy.

## 2. Batching publisher: gom request để tăng hiệu quả

Batching giảm số lần gọi Publish API khi gửi nhiều message nhỏ. Thay vì gọi một RPC cho mỗi sự kiện, client gom message rồi gửi khi **một trong ba ngưỡng** đạt:

| Ngưỡng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Message count** | 100 message | Batch được gửi khi số message đạt ngưỡng. |
| **Byte size** | 1 MiB | Batch được gửi khi tổng kích thước vượt/đạt ngưỡng cấu hình theo SDK. |
| **Max latency / delay** | 50 ms | Gửi batch chưa đầy sau khoảng chờ tối đa của client. |

Điều kiện kích hoạt là **OR**, không phải chờ đồng thời đủ cả ba ngưỡng. Với 10.000 message/s và message nhỏ, ngưỡng count thường được chạm trước; với tải chỉ 5 message/s, ngưỡng thời gian giúp không giữ message quá lâu.

**Giới hạn dịch vụ:** một Publish request của Pub/Sub có giới hạn tổng kích thước khoảng **10 MB** và số lượng **1.000 messages**. Chọn ngưỡng nhỏ hơn giới hạn và tính cả overhead khi lập kế hoạch; một **message đơn lẻ** không thể được chia qua hai publish request bằng batching. High-level client libraries thường giúp giữ request trong giới hạn nhưng ứng dụng phải kiểm tra kích thước dữ liệu đầu vào.

### 2.1. Đánh đổi latency và throughput

| Cấu hình | Lợi ích | Rủi ro |
| --- | --- | --- |
| Batch rất nhỏ hoặc `max_messages=1` | Độ trễ chờ batch thấp, dễ kiểm tra một message. | Nhiều RPC, overhead và chi phí xử lý tăng. |
| Batch lớn, `max_latency` dài | Hiệu quả cao khi traffic đều/đủ lớn. | Message ít có thể chờ lâu, p99 publish latency tăng. |
| Batch vừa, latency ngắn | Cân bằng cho API/luồng sự kiện thời gian gần thực. | Cần thử tải để chọn ngưỡng phù hợp. |
| Batch lớn nhưng publisher không có flow control | Gửi nhiều RPC hiệu quả, nhưng vẫn có nguy cơ backlog trong RAM. | Timeout, memory pressure, mất dữ liệu nếu process dừng trước khi futures hoàn tất. |

Batching ảnh hưởng **publish latency** và **end-to-end latency**; không có cấu hình tối ưu chung cho mọi workload. SDK có thể bật batching mặc định, nhưng mặc định khác nhau giữa ngôn ngữ và phiên bản.

### 2.2. Message ID và xác nhận publish

Lệnh `publish(...)` ở nhiều SDK trả **Future/Promise** ngay khi message mới được xếp hàng cục bộ; điều đó **chưa chứng minh Pub/Sub đã nhận**. Chỉ khi future hoàn tất thành công và có `message_id`, ứng dụng mới có kết quả xác nhận từ dịch vụ.

Do đó:

1. Giữ publisher client sống đủ lâu để batch được gửi, ưu tiên **tái sử dụng** giữa nhiều request.
2. Chờ/cập nhật trạng thái của futures thay vì coi “đã gọi publish” là thành công.
3. Khi thoát ứng dụng có kiểm soát, thực hiện flush/shutdown theo API của SDK.
4. Với sự kiện phải phát đáng tin cậy ngay sau một giao dịch database, cân nhắc **transactional outbox** thay vì ghi DB xong rồi gửi Pub/Sub “best effort”.

**Lưu ý dữ liệu trùng:** publisher có thể timeout sau khi Pub/Sub đã nhận message nhưng trước khi client nhận phản hồi. Retry có thể tạo message mới với message ID khác. Vì vậy không dựa duy nhất vào `message_id` để chống lặp nghiệp vụ; thêm `event_id` ổn định và xử lý idempotent ở subscriber.

## 3. Publisher flow control: backpressure trước khi hết RAM

Nếu producer tạo 30.000 message/s nhưng client chỉ publish được 10.000 message/s, khoảng **20.000 message/s** tiếp tục dồn vào hàng đợi cục bộ. Sau một phút, chỉ riêng số lượng message đang chờ có thể tăng khoảng **1,2 triệu**. Batching giúp gửi nhanh hơn, nhưng nếu chênh lệch kéo dài thì **bắt buộc cần backpressure hoặc capacity lớn hơn**.

Trong Python, `PublishFlowControl` có hai ngưỡng:

- `message_limit`: số lượng message đang chờ publish.
- `byte_limit`: tổng byte đang chờ publish.

Khi đạt giới hạn, hành vi `limit_exceeded_behavior` có thể là:

| Hành vi | Tác động | Dùng khi |
| --- | --- | --- |
| `BLOCK` | Lời gọi `publish()` chờ đến khi có chỗ trống. | Muốn tạo **backpressure** lên producer và kiểm soát bộ nhớ. |
| `ERROR` | Báo lỗi khi không thể nhận thêm vào queue cục bộ. | Ứng dụng có hàng đợi bền vững hoặc cơ chế retry/backoff riêng. |
| `IGNORE` | Bỏ qua giới hạn flow control phía client. | Chỉ khi đã hiểu mức memory pressure; thường không phù hợp dưới tải không giới hạn. |

Đây là **giới hạn tại publisher process**, không phải quota của Pub/Sub service hay giới hạn cho mọi publisher cùng topic. Nhiều process có bộ đếm riêng; tổng tải của chúng vẫn có thể vượt quota project/region hoặc khả năng subscriber.

### 3.1. Ví dụ Python: batching và flow control đồng thời

Ví dụ sử dụng thư viện `google-cloud-pubsub` hiện hành. Chạy trong môi trường **đã có topic lab**, Application Default Credentials (ADC) và IAM `roles/pubsub.publisher` trên topic:

~~~python
import json
import os
import uuid

from google.cloud import pubsub_v1
from google.cloud.pubsub_v1.types import (
    BatchSettings,
    LimitExceededBehavior,
    PublisherOptions,
    PublishFlowControl,
)

project_id = os.environ["PROJECT_ID"]
topic_id = os.environ["TOPIC_ID"]

# Một batch được gửi khi đạt MỘT trong các ngưỡng.
batch = BatchSettings(
    max_messages=50,
    max_bytes=1024 * 1024,  # 1 MiB
    max_latency=0.05,       # 50 ms
)

# Tạo backpressure, không để publisher nhận vô hạn.
flow = PublishFlowControl(
    message_limit=200,
    byte_limit=5 * 1024 * 1024,  # 5 MiB
    limit_exceeded_behavior=LimitExceededBehavior.BLOCK,
)

publisher = pubsub_v1.PublisherClient(
    batch_settings=batch,
    publisher_options=PublisherOptions(flow_control=flow),
)
topic_path = publisher.topic_path(project_id, topic_id)

futures = []
for index in range(100):
    event = {
        "event_id": str(uuid.uuid4()),
        "type": "EnrollmentCreated",
        "enrollment_id": f"lab-{index}",
    }
    payload = json.dumps(event).encode("utf-8")
    future = publisher.publish(
        topic_path, payload, event_type="EnrollmentCreated"
    )
    futures.append(future)

# Chỉ xem là thành công khi từng future được xác nhận.
published = 0
for future in futures:
    message_id = future.result(timeout=60)
    published += 1
    print("Published:", message_id)

print("Confirmed messages:", published)
~~~

Ý nghĩa:

- 100 `publish()` là **100 message riêng**; SDK có thể gom chúng vào một số publish RPC.
- `max_latency=0.05` giúp không chờ quá lâu khi batch chưa đầy trong điều kiện client hoạt động bình thường.
- `BLOCK` khiến producer tạm chờ khi quá nhiều message/bytes đang outstanding; đây là backpressure, **không phải thao tác ghi bền vững**.
- `future.result()` có thể ném exception hoặc timeout; code production phải ghi trạng thái, retry theo quy tắc và xử lý thất bại **từng message**.
- Ví dụ chỉ in message ID đã được xác nhận; không gửi dữ liệu cá nhân thật hoặc thông tin bí mật vào topic lab.

**Ứng dụng thực:** nên dùng publisher dạng singleton hoặc client tái sử dụng trong một worker/process. Tạo client mới cho từng HTTP request khiến batching kém hiệu quả, tăng connection/threads và làm shutdown khó bảo đảm hoàn tất message. Khi ứng dụng dừng có kiểm soát, ngừng tiếp nhận sự kiện mới và chờ các future đang pending theo deadline vận hành.

### 3.2. Chọn giới hạn từ ngân sách bộ nhớ

Giả sử payload trung bình **8 KiB**, cho phép tối đa 500 outstanding messages:

\[
500 \times 8\ \text{KiB} \approx 3{,}9\ \text{MiB}
\]

Đây chỉ là **payload**, chưa tính Python objects, future, batching overhead, attributes, gRPC buffers và biến nghiệp vụ. Vì vậy đừng đặt `byte_limit` bằng đúng RAM còn trống. Chọn giá trị có margin, đo RSS/heap thật dưới tải, đồng thời đặt **cả message_limit và byte_limit** vì message size có thể biến động.

### 3.3. Lỗi publisher và hướng xử lý

| Tín hiệu | Nguyên nhân thường gặp | Biện pháp |
| --- | --- | --- |
| `publish()` bị chặn lâu với `BLOCK` | Pub/Sub quota, mạng, service latency hoặc ngưỡng quá thấp | Xem publish latency/error, quota và tốc độ producer; không tự bỏ flow control. |
| `DEADLINE_EXCEEDED`, futures lỗi | Publish request treo hoặc client nhận nhanh hơn khả năng gửi | Retry có backoff và deadline, kiểm tra batch/flow control, phát hiện trùng nghiệp vụ. |
| RAM tăng liên tục | `IGNORE`, future tích tụ hoặc ứng dụng giữ toàn bộ payload/futures | Giới hạn outstanding, xử lý future hoàn tất, giảm bộ nhớ do chính app giữ. |
| Pub/Sub báo `RESOURCE_EXHAUSTED` | Quota/throughput giới hạn hoặc lưu lượng vượt sức chứa cho phép | Kiểm tra quota, tốc độ publish và phương án tăng quota chính thức. |
| Publish latency p99 tăng sau tăng batch size | Batch chờ đủ count/bytes quá lâu | Giảm `max_latency` hoặc count threshold; kiểm tra request size/RPS. |
| Shutdown làm mất event chưa gửi | Process dừng trước khi futures/flush hoàn tất | Graceful shutdown, hàng đợi bền vững/outbox và xác nhận publish. |

**Không “sửa” publish failure bằng retry vô hạn:** nếu producer quá nhanh lâu dài, retry sẽ làm nghẽn thêm. Cần cân bằng **tốc độ sự kiện đầu vào, capacity publish, quota và khả năng xử lý cuối**.

## 4. Subscriber flow control: nhận vừa đủ khả năng xử lý

Subscriber pull/StreamingPull lấy message theo subscription. Với high-level client libraries, flow control giới hạn message **đã được giao tới client nhưng chưa được ack/nack**, tránh tải vào RAM hoặc mở quá nhiều xử lý đồng thời. Khi đạt một trong các ngưỡng, client tạm dừng nhận thêm cho đến khi outstanding giảm.

| Tham số Python `FlowControl` | Ý nghĩa | Rủi ro nếu đặt sai |
| --- | --- | --- |
| `max_messages` | Số message outstanding tối đa. | Quá cao gây overload handler; quá thấp lãng phí capacity. |
| `max_bytes` | Tổng kích thước message outstanding tối đa. | Quá cao có thể hết RAM khi payload lớn. |
| `max_lease_duration` | Giới hạn thời gian client giữ lease/quản lý gia hạn ack deadline cho message. | Quá ngắn so với xử lý làm tăng redelivery; quá dài có thể kéo dài thời gian phát lại khi worker kẹt. |
| `min_duration_per_lease_extension` / `max_duration_per_lease_extension` | Giới hạn mỗi lần gia hạn lease trong những trường hợp SDK hỗ trợ. | Cần kiểm tra semantics với exactly-once/latency và SDK cụ thể. |

Mặc định của `FlowControl` Python hiện hành là khoảng **1.000 messages** và **100 MiB**; tuy nhiên mặc định và mức hỗ trợ có thể khác nhau theo SDK/ngôn ngữ. Với ứng dụng quan trọng, khai báo tường minh theo kết quả đo.

### 4.1. Ví dụ Python StreamingPull an toàn cho lab

Ví dụ chỉ đọc sự kiện `EnrollmentCreated` rồi in event ID để minh họa. Trong production, thay thao tác in bằng **giao dịch xử lý idempotent thực sự** trước khi ack.

~~~python
import json
import os

from google.cloud import pubsub_v1

project_id = os.environ["PROJECT_ID"]
subscription_id = os.environ["SUBSCRIPTION_ID"]

subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(
    project_id, subscription_id
)

flow = pubsub_v1.types.FlowControl(
    max_messages=40,
    max_bytes=10 * 1024 * 1024,  # 10 MiB
    max_lease_duration=600,      # 10 phút
)

def callback(message):
    try:
        event = json.loads(message.data.decode("utf-8"))
        event_id = event["event_id"]  # bắt buộc có

        # LAB: không có side effect bền vững.
        # PROD: commit DB transaction idempotent trước khi ack.
        print("Handled event:", event_id)

    except Exception as error:
        print("Processing failed:", type(error).__name__)
        message.nack()  # có thể được phát lại
    else:
        message.ack()   # chỉ sau khi xử lý thành công

streaming = subscriber.subscribe(
    subscription_path, callback=callback, flow_control=flow
)
print("Listening for messages; Ctrl+C to stop")

try:
    streaming.result()
except KeyboardInterrupt:
    streaming.cancel()
finally:
    subscriber.close()
~~~

**Vì sao đặt cả 40 messages và 10 MiB?** Với nhiều message nhỏ, giới hạn count chặn trước; với payload lớn, giới hạn bytes giúp tránh một số ít message sử dụng quá nhiều RAM. Đây là **giới hạn trên client**, không có nghĩa có đúng 40 thread chạy cùng lúc. Thực tế còn phụ thuộc executor/scheduler, CPU và code callback.

**Xử lý thực tế:** nếu callback ghi database, chỉ `ack()` sau khi commit thành công. Nếu dùng transaction với unique key `event_id` để chống trùng, một message được phát lại có thể được nhận diện là đã xử lý và ack an toàn. Tránh giữ transaction hoặc connection trong thời gian chờ I/O ngoài quá dài.

### 4.2. Ack/nack và redelivery

Pub/Sub thường cung cấp **at-least-once delivery**: một message có thể đến lại vì ack deadline hết, client mất kết nối, hoặc retry sau lỗi tạm. Vì vậy:

1. **Xử lý trước, ack sau**: ack sớm có thể gây mất xử lý khi worker crash.
2. **Nack khi có lỗi tạm** và có chiến lược retry/delay phù hợp; nack ngay liên tục có thể tạo retry storm.
3. **Poison messages** (payload hỏng, schema không hỗ trợ) cần dead-letter policy và quy trình xử lý/quarantine, không phát lại vô hạn.
4. **Idempotency** theo business key/event ID cần có ngay cả khi sử dụng cơ chế exactly-once cho pull, bởi exactly-once không biến thao tác DB của ứng dụng thành một transaction chung với Pub/Sub.
5. Ghi message ID, event ID, delivery attempt và error category **không chứa PII** để điều tra redelivery.

Với **exactly-once delivery**, chỉ những pull subscriptions đủ điều kiện mới hỗ trợ; tăng độ trễ/phí và có yêu cầu vùng, ack confirmation cùng giới hạn. Không bật chỉ để che lỗi thiếu idempotency ở database.

### 4.3. Ack deadline và lease extension

Subscription có **ack deadline** ban đầu. Khi subscriber chưa ack đúng hạn, message có thể được phát lại. High-level client libraries thường tự **gia hạn lease** cho message vẫn đang xử lý, tối đa trong giới hạn cấu hình. Nhưng:

- Xử lý lâu hơn `max_lease_duration` có thể dẫn đến phát lại dù callback chưa kết thúc.
- Crash process, mất kết nối hoặc callback kẹt khiến cơ chế gia hạn không còn đáng tin.
- Không nên đặt ack deadline rất dài để “giữ” mọi message; điều này có thể kéo dài phục hồi sau lỗi.
- Tác vụ mất hàng chục phút/giờ nên cân nhắc **job orchestration** (ví dụ Cloud Tasks/Workflows/Batch) thay vì một callback giữ ack mãi.

Một message được phát lại có thể đang được xử lý bởi worker khác; dùng khóa idempotent, transaction isolation hoặc cơ chế đồng bộ nghiệp vụ thích hợp.

### 4.4. Pull, StreamingPull và push không giống nhau

| Chế độ | Ai điều tiết việc nhận? | Cách tối ưu |
| --- | --- | --- |
| **StreamingPull (high-level SDK)** | Subscriber client giữ kết nối, dùng flow control/lease management. | `max_messages`, `max_bytes`, callback concurrency, số process. |
| **Unary Pull** | Ứng dụng gọi Pull RPC theo batch/thời điểm. | Giới hạn `maxMessages` của từng pull, polling phù hợp, không dùng `returnImmediately=true` đã deprecated. |
| **Push subscription** | Pub/Sub gửi HTTP request đến endpoint; kết quả HTTP quyết định ack/retry. | Capacity/latency endpoint, số instance/concurrency, retry policy, auth; **không** dùng `FlowControl` của StreamingPull ở server. |
| **Cloud Run/GKE subscriber** | Phụ thuộc chọn pull worker hay HTTP push. | Pull: điều chỉnh worker/flow. Push: điều chỉnh HTTP handler, instances, concurrency và ack qua response. |

Đối với **push**, trả HTTP success chỉ khi xử lý xong theo tiêu chí nghiệp vụ; nếu trả 2xx trước khi persist, Pub/Sub có thể coi là đã ack và không phát lại khi bước xử lý sau đó thất bại. Lúc cao tải, backend phải có backpressure phù hợp và giới hạn concurrency có cơ sở.

### 4.5. Concurrency khác flow control

Một process có `max_messages=200` nhưng chỉ **5 worker threads** có thể khiến 195 message chờ xử lý ở client và liên tục bị gia hạn lease. Ngược lại, 100 threads trên VM 1 vCPU có thể tăng CPU context switching, giữ nhiều DB connections và làm p99 tệ hơn.

Để điều chỉnh:

- **I/O-bound**: tăng concurrency có giới hạn nếu network/database cho phép.
- **CPU-bound**: xem giới hạn vCPU, số process và profiling trước khi tăng threads.
- **DB-bound**: giới hạn connection pool, transaction và QPS; tăng subscriber không giải quyết DB saturation.
- **Ordering key**: cùng key có yêu cầu xử lý tuần tự theo cơ chế ordered delivery; tăng parallel workers không làm một hot key nhanh lên vô hạn.

Đối với Java, có thể cấu hình **`FlowControlSettings` trên subscriber**, tách nó khỏi executor/concurrency control của callback. Không lấy `maxOutstandingElementCount` làm số threads mà không đọc scheduler configuration.

## 5. Sizing: từ throughput đến outstanding limits

Chọn cấu hình bằng **số liệu của workload** thay vì nhân các default một cách máy móc. Với lưu lượng ổn định, định luật Little cho ước lượng:

\[
\text{Outstanding trung bình} \approx
\text{messages/s} \times \text{thời gian xử lý trung bình (s)}
\]

Ví dụ subscriber nhận **200 messages/s** và callback xử lý mất trung bình **250 ms**:

\[
200 \times 0{,}25 = 50\ \text{messages xử lý/chờ trung bình}
\]

`max_messages=50` có thể **vừa khít** mức trung bình, chưa có headroom khi p99 tăng hay có burst. Thử ngưỡng như **80–120** (chỉ minh họa), đo số outstanding và memory, rồi chọn lại theo SLO. Nếu worker executor chỉ xử lý được 10 messages đồng thời, tăng giới hạn lên 1.000 không làm capacity tăng tương ứng.

### 5.1. Kiểm tra đồng thời hai giới hạn

Giả sử payload trung bình **256 KiB**, nhưng có message lên đến **2 MiB**. Nếu đặt `max_messages=100`:

- Theo **payload trung bình**: `100 × 256 KiB = 25 MiB`.
- Theo **payload lớn**: có thể lên tới `100 × 2 MiB = 200 MiB`.

Với một container có ít RAM, nên đặt `max_bytes` theo ngân sách thực (ví dụ **32 MiB**) để tránh chạy đến 100 message lớn. Chừa bộ nhớ cho runtime, JSON parsing, business objects, TLS buffers, client library và cache.

**Quy tắc:** giới hạn thứ nhất chạm (messages hoặc bytes) sẽ quyết định khi nào subscriber ngừng nhận thêm. Các SDK có thể cho phép overshoot nhẹ do message đang trên đường truyền; không dùng flow control như cơ chế cách ly bộ nhớ tuyệt đối.

### 5.2. Backlog tăng vì thiếu capacity lâu dài

Nếu publisher gửi ổn định **500 messages/s** nhưng toàn bộ subscriber chỉ xử lý/ack được **300 messages/s**, backlog tăng xấp xỉ:

\[
(500-300)\times3600=720.000\ \text{messages/giờ}
\]

Tăng `max_messages` của một subscriber từ 100 lên 1.000 chỉ giúp hút thêm backlog vào RAM, **không tạo thêm 200 messages/s năng lực xử lý**. Cần tối ưu handler, tăng replicas/workers, tăng capacity database, hoặc giảm tốc producer theo cơ chế chấp nhận được.

### 5.3. Bài toán batch publisher

Một producer gửi **2.000 messages/s**, trung bình mỗi message **1 KiB**. Nếu đặt `max_messages=100`, `max_bytes=1 MiB`, `max_latency=50 ms`:

- Trong 50 ms, producer tạo khoảng **100 messages**.
- Ngưỡng count/time có thể đạt gần đồng thời, tạo cỡ **20 batch RPC/s** trong trường hợp lý tưởng.
- Mỗi batch khoảng **100 KiB payload**, nhỏ hơn ngưỡng byte 1 MiB.

Con số thực tế khác vì phân phối lưu lượng, overhead, network/RPC latency, việc client flush và retry. Không coi 20 RPC/s là quota được Pub/Sub bảo đảm.

### 5.4. Bảng chọn cấu hình khởi đầu

| Đặc tính tải | Publisher | Subscriber |
| --- | --- | --- |
| Sự kiện nhỏ, lượng lớn, ưu tiên thông lượng | Tăng count/byte batch hợp lý; latency ngắn-vừa, flow control `BLOCK`/`ERROR` | Nhiều workers, flow control theo RAM/CPU, theo dõi backlog |
| Request tương tác cần xử lý gần thời gian thực | Batch latency thấp; không chờ batch lớn | Ít outstanding hơn, đủ concurrency, p99 ack latency thấp |
| Message lớn, parse tốn RAM | Byte limit chặt hơn count, đo serialization overhead | Byte limit chặt, tránh handler nhân đôi payload trong bộ nhớ |
| Xử lý database tốn I/O | Không dùng publish rate vô giới hạn | Concurrency và connection pool theo DB capacity, idempotency |
| Tải biến động theo giờ | Backpressure tại producer + buffer bền vững nếu cần | Autoscale workers theo backlog age/throughput, không chỉ CPU |
| Ordered messages theo một hot key | Bật ordering khi thực sự cần, quản lý lỗi theo key | Không kỳ vọng tăng threads xử lý song song cùng ordering key |

## 6. Điều chỉnh theo metric và SLO

### 6.1. Theo dõi pipeline theo ba tầng

| Tầng | Metric/câu hỏi | Gợi ý |
| --- | --- | --- |
| Publisher client | Publish futures thành công/thất bại, p95/p99 publish latency, outstanding messages/bytes, thời gian `BLOCK` | Phát hiện nghẽn trước khi message vào Pub/Sub. |
| Topic/Pub/Sub | Publish request/error rate, quota utilization, message size, latency phía dịch vụ | Xác định quota, payload lớn hoặc thay đổi lưu lượng. |
| Subscription | **`subscription/num_unacked_messages_by_region`**, **`subscription/oldest_unacked_message_age_by_region`** | Đo backlog theo region và tuổi message lâu nhất. |
| Pull/StreamingPull | **`subscription/expired_ack_deadlines_count`**, ack latency, redelivery/nack, flow control saturation | Phát hiện xử lý chậm hoặc lease không theo kịp. |
| Push endpoint | **`subscription/push_request_count`** theo response code, HTTP latency, container concurrency | Phân biệt lỗi push/HTTP với logic xử lý. |
| Business | Số `event_id` xử lý mới, thời gian từ event tới khi commit DB, duplicate rate | Đo mục tiêu nghiệp vụ thay vì chỉ lượng request. |

Khi alert theo khả dụng theo region, ưu tiên **metric có hậu tố `_by_region`** nếu cần tránh một region lỗi làm mất khả năng quan sát các region khác. Kiểm tra tên metric, nhãn, cách lấy mẫu và phạm vi theo tài liệu Cloud Monitoring hiện hành; không mặc định mọi biểu đồ có cùng độ trễ cập nhật.

### 6.2. Đọc backlog đúng cách

| Diễn biến | Khả năng nguyên nhân | Hướng hành động |
| --- | --- | --- |
| Backlog count **và** oldest age cùng tăng | Subscriber xử lý chậm hơn đầu vào | Tăng capacity phù hợp, tối ưu handler/downstream. |
| Backlog ít nhưng oldest age rất cao | Một số poison/stuck messages | Kiểm tra message lỗi, retry, DLQ, ack timeout. |
| Ack deadline expirations tăng | Xử lý lâu, callback kẹt, thiếu lease hoặc quá nhiều outstanding | Giảm flow limit, tối ưu xử lý, chỉnh lease trong giới hạn hợp lý. |
| CPU subscriber thấp, backlog cao | Thiếu workers/connections, flow limit thấp, hot ordering key hoặc DB block | Kiểm tra executor, stream status, ordering, DB metrics. |
| Publish latency tăng nhưng backlog subscriber thấp | Nghẽn publisher/quota/network | Xem batching, futures, `BLOCK` và publish RPC latency. |
| Redelivery tăng sau autoscaling | Worker bị kill trong lúc xử lý, graceful shutdown kém | Chờ in-flight callback, không ack sớm, idempotency và shutdown hooks. |

Đừng chỉ nhìn `num_unacked_messages` rồi tăng worker vô hạn. Nếu downstream database đã đạt giới hạn connection/IOPS, tăng subscriber có thể tạo nhiều timeout và phát lại hơn.

### 6.3. Quy trình tối ưu tuần tự

~~~mermaid
flowchart TD
    M["Thu thập baseline:<br/>publish/ack latency, backlog, errors"] --> B{"Nút thắt chính?"}
    B -->|Producer| P["Batching + publisher flow control,<br/>quota/network/RAM"]
    B -->|Consumer| C["Flow control + handler concurrency,<br/>CPU/DB/ack lease"]
    B -->|Downstream| D["DB/HTTP capacity, idempotency,<br/>backpressure và retries"]
    P --> T["Chỉ đổi một nhóm tham số,<br/>load test với mẫu tải thật"]
    C --> T
    D --> T
    T --> S{"SLO, backlog age,<br/>cost, error rate đạt?"}
    S -->|Không| M
    S -->|Có| E["Lưu quyết định và alert;<br/>theo dõi sau phát hành"]
~~~

**Đừng đồng thời tăng batch size, worker count và DB pool**, vì không biết thay đổi nào giúp hoặc làm hại. Test các profile riêng: message nhỏ/lớn, burst kéo dài, callback lỗi, restart worker, database chậm và peak traffic. Đo ít nhất **end-to-end latency p95/p99**, backlog age, memory và tổng chi phí.

## 7. Độ tin cậy và những giới hạn liên quan

### 7.1. At-least-once, idempotency và outbox

Một hệ thống đăng ký khóa học không được gửi email hai lần chỉ vì message đến lại. Mẫu xử lý an toàn:

1. Publisher tạo **`event_id` duy nhất, ổn định** và đưa vào payload/attributes.
2. Subscriber dùng transaction DB kiểm tra `event_id` đã xử lý chưa, cùng lúc cập nhật trạng thái nghiệp vụ và ghi dấu hoàn thành.
3. **Chỉ ack sau khi transaction commit**.
4. Với side effect bên ngoài (gửi email/thanh toán), dùng idempotency key hoặc workflow bền vững để tránh lặp ngay cả khi worker crash.

Nếu DB ghi thành công nhưng publisher chưa chắc đã gửi event, **transactional outbox** lưu event cùng giao dịch DB; worker độc lập publish và đánh dấu đã gửi. Outbox giúp giảm nguy cơ mất event ở ranh giới DB/Pub/Sub, nhưng subscriber vẫn cần idempotency vì publish có thể lặp.

### 7.2. Ordering keys và giới hạn thông lượng

Pub/Sub hỗ trợ **message ordering** khi publisher và subscription được cấu hình đúng theo region/key. Tính thứ tự được xét **trong một ordering key**; không phải thứ tự toàn topic.

Ví dụ `ordering_key="student-42"` bảo đảm những sự kiện cần tuần tự theo một học viên được xử lý theo thứ tự trong các điều kiện sản phẩm. Nếu chỉ có **một hot key** chứa toàn bộ traffic, subscriber không thể tùy ý xử lý message của key ấy ở nhiều callback song song mà vẫn giữ thứ tự. Phải chọn key đủ phân tán mà không làm mất quy tắc nghiệp vụ.

Với ordered delivery, ack các message cùng key cần **đúng thứ tự**; lỗi/thiếu ack ở message trước có thể làm các message sau bị redeliver. Batch publisher không thay thế ordering configuration, và có thể tăng tác động lan truyền khi một message trong nhóm xử lý lỗi.

### 7.3. Retry, dead letter và autoscaling

- Chọn retry policy với backoff để tránh poison message gây lặp quá nhanh.
- Dùng **dead-letter topic** cho lỗi không thể xử lý sau những lần thử phù hợp; cấu hình IAM, delivery attempts và việc xử lý DLQ riêng.
- Với worker trên GKE/Compute Engine, autoscale theo **backlog/oldest age** và năng lực backend, không chỉ theo CPU.
- Với Cloud Run push, kiểm tra request timeout, concurrency, min/max instances và tín hiệu HTTP thành công; không áp cấu hình StreamingPull client lên endpoint push.
- Khi process dừng, ngừng nhận message mới và hoàn tất/để Pub/Sub phát lại in-flight messages theo chiến lược; không ack trước khi trạng thái thật được commit.

**Exactly-once pull** có phạm vi áp dụng/chi phí và độ trễ khác với at-least-once mặc định. Chọn nó khi yêu cầu thực sự cần xác nhận ack có tính bảo đảm phù hợp, không phải giải pháp thay thế transaction, deduplication hoặc idempotent side effects.

## 8. Lab: batching publisher và StreamingPull subscriber

**Mục tiêu:** tạo một topic/subscription mới trong project lab, publish **100 message** theo cấu hình batching/flow control ở mục 3, nhận bằng subscriber ở mục 4, theo dõi metrics và dọn tài nguyên. Lab này **không** thực hiện benchmark tải lớn.

**Điều kiện:** project được duyệt có billing và Pub/Sub API; account đủ quyền tạo topic/subscription, còn runtime publisher/subscriber có IAM tương ứng. Không chạy trong project production hoặc trên topic/subscription có khách hàng thật. IAM thông thường:

- Principal tạo/xóa tài nguyên lab cần quyền quản trị Pub/Sub tương ứng; không nhất thiết cấp Owner toàn project.
- Publisher chỉ cần `roles/pubsub.publisher` trên **topic**.
- Subscriber chỉ cần `roles/pubsub.subscriber` trên **subscription**.
- Trên Compute Engine/GKE/Cloud Run ưu tiên **service account gắn với workload**, không lưu JSON key trong image. Với máy local, dùng ADC đã đăng nhập theo chính sách tổ chức.

### 8.1. Chuẩn bị project và tạo tài nguyên riêng

Trong Bash/Cloud Shell đã xác thực:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export TOPIC_ID="pubsub-batching-lab-UNIQUE"
export SUBSCRIPTION_ID="pubsub-flow-lab-UNIQUE"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Kiểm tra chưa có topic/subscription cùng tên trước khi tạo
gcloud pubsub topics list --filter="name:$TOPIC_ID"
gcloud pubsub subscriptions list --filter="name:$SUBSCRIPTION_ID"

# THAO TÁC GHI: chỉ dùng tên tài nguyên do bạn sở hữu trong lab
gcloud pubsub topics create "$TOPIC_ID"
gcloud pubsub subscriptions create "$SUBSCRIPTION_ID" \
  --topic="$TOPIC_ID" \
  --ack-deadline=30

# Đọc lại thông tin subscription
gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID"
~~~

`--ack-deadline=30` là deadline ban đầu của subscription, **không** phải thời gian xử lý tối đa cứng của subscriber SDK; với StreamingPull, client có thể gia hạn lease theo cấu hình.

Nếu Pub/Sub API chưa bật, cần người có quyền và quy trình được phê duyệt bật `pubsub.googleapis.com`. Nếu tên đã tồn tại, **không tạo/xóa chồng lên tài nguyên khác**; chọn tên lab mới.

### 8.2. Chạy hai script từ bài

Tạo file local `publisher.py` với mã ở **mục 3.1**, `subscriber.py` với mã ở **mục 4.1**. Cài thư viện trong virtual environment của **máy lab**:

~~~bash
python -m pip install google-cloud-pubsub
~~~

Trong terminal thứ nhất, đảm bảo các biến môi trường cùng project/subscription được set:

~~~bash
python subscriber.py
~~~

Trong terminal thứ hai, với project/topic lab:

~~~bash
python publisher.py
~~~

Kết quả mong đợi:

- Publisher nhận **100 message IDs** từ futures thành công, trừ khi có lỗi cần điều tra.
- Subscriber in ra các `event_id` tương ứng và ack **sau** khi callback xử lý xong.
- Pub/Sub backlog giảm theo thời gian nếu subscriber xử lý nhanh hơn tốc độ publish và không có consumer cạnh tranh.

**Không** bắt buộc phải đúng 100 dòng subscriber ngay sau khi publisher kết thúc: client chạy bất đồng bộ, hệ thống có thể phát lại message, và nếu subscriber dừng quá sớm vẫn còn message ở subscription. Một message ID được Pub/Sub xác nhận không đồng nghĩa subscriber đã xử lý thành công. Khi đánh giá, đối chiếu **publish success count, business event IDs và ack/backlog**.

### 8.3. Thử thay đổi một biến

Từ cấu hình ban đầu, chạy lại trong lab có cùng số message/size, lần lượt thử:

| Thử nghiệm | Chỉ thay đổi | Điều cần quan sát |
| --- | --- | --- |
| A | `max_latency: 0.05` → `0.5` | Publish p95/p99 latency có tăng khi tải thưa không? |
| B | `max_messages` của BatchSettings từ 50 → 1 | Số publish RPC/overhead và latency thay đổi thế nào? |
| C | `message_limit` của PublishFlowControl từ 200 → 20 | Producer có bị `BLOCK` khi gửi nhanh hơn không? |
| D | Subscriber `max_messages` từ 40 → 10 | Backlog/ack throughput, RSS và thời gian chờ có thay đổi không? |
| E | Thêm xử lý giả lập chậm **100 ms** trong callback lab | Ack latency, backlog age và số message outstanding thay đổi thế nào? |

Để phép đo có ý nghĩa, cần cùng profile tải và đủ mẫu; bài lab 100 message chỉ chứng minh **cơ chế và tính đúng đắn**, không đủ để xác định cấu hình production. Không tạo hàng trăm nghìn message chỉ để làm đồ thị rõ hơn nếu chưa có quota, budget và approval.

### 8.4. Dọn tài nguyên an toàn

Sau khi dừng subscriber và bảo đảm không có job khác đang sử dụng topic/subscription **do mình tạo**:

~~~bash
gcloud config get-value project
gcloud pubsub subscriptions describe "$SUBSCRIPTION_ID"
gcloud pubsub topics describe "$TOPIC_ID"

# THAO TÁC XÓA: chỉ với tài nguyên lab đã xác minh
gcloud pubsub subscriptions delete "$SUBSCRIPTION_ID"
gcloud pubsub topics delete "$TOPIC_ID"

# Xác minh không còn đối tượng lab
gcloud pubsub topics list --filter="name:$TOPIC_ID"
gcloud pubsub subscriptions list --filter="name:$SUBSCRIPTION_ID"
~~~

Xóa subscription sẽ làm mất những message chưa ack trong subscription đó theo quy tắc sản phẩm; không dùng lệnh trên với dữ liệu cần giữ. Nếu topic có subscription của người khác hoặc được một hệ thống khác sử dụng, **không xóa topic**. Billing, Monitoring và log có thể xuất hiện trễ sau khi tài nguyên đã được dọn.

## 9. Runbook khi hệ thống không theo kịp tải

Khi thấy request đến backend chậm hoặc backlog tăng, điều tra theo thứ tự:

1. **Xác định điểm nghẽn:** publisher futures/latency, Pub/Sub subscription backlog, subscriber callback/ack hay database.
2. **Đo tốc độ thực:** messages/s publish thành công, messages/s ack và oldest unacked age trong cùng khoảng đo.
3. **Đọc giới hạn đang dùng:** batch thresholds, publisher message/byte limits, subscriber message/byte/lease limits, worker threads/replicas và quota.
4. **Kiểm tra tài nguyên:** CPU/RAM, network, DB connection pool, IOPS, retry rates và logs đã redacted.
5. **Thử đúng một thay đổi:** ví dụ giảm subscriber flow limit nếu OOM, tăng workers nếu CPU/DB còn dư, điều chỉnh batch latency nếu publish p99 cao.
6. **Xác minh kết quả và khả năng phục hồi:** backlog age có giảm không, redelivery/duplicate rate có tăng không, chi phí và SLO có tốt hơn không.

| Hiện tượng | Không nên làm ngay | Cần làm trước |
| --- | --- | --- |
| Publisher OOM khi batch lớn | Tăng RAM vô điều kiện | Bật flow control phù hợp, đếm futures, đo payload/overhead. |
| Subscriber có hàng nghìn in-flight message | Tăng threads lên bằng `max_messages` | Kiểm tra CPU, executor, DB pool và ack latency. |
| Backlog liên tục tăng | Chỉ tăng `max_bytes` | So sánh publish vs ack throughput; scale thực hoặc giảm đầu vào. |
| Expired ack deadline tăng | Tăng ack deadline lên mức tối đa | Kiểm tra xử lý quá chậm, worker restart, lease limits và poison messages. |
| 429/quota hoặc `RESOURCE_EXHAUSTED` | Retry liên tục không backoff | Đối chiếu quota, tải peak, retry policy và ngưỡng publish. |
| Một ordering key làm mọi thứ chậm | Bật thêm threads vô hạn | Xem granularity của ordering key và bước xử lý tuần tự bắt buộc. |
| Lặp giao dịch sau redelivery | Tắt retry/ack ngay khi nhận | Thêm idempotency/transaction và chỉ ack sau commit. |

**Bảo mật và chi phí:** Pub/Sub có phí publish/delivery, lưu trữ/retention và những chi phí liên quan theo bảng giá hiện hành; redelivery không cần thiết làm tăng xử lý downstream. Không đưa payload có PII, credential hay token vào log; dùng Cloud Monitoring labels/metrics và event ID đã được kiểm soát.

## 10. Tình huống thực tế và bài tập

### Tình huống A — Subscriber mất kết nối database

Một subscription nhận 1.200 messages/s, có 12 subscriber instances. Mỗi instance đặt `max_messages=1.000` và callback mở connection DB; database chỉ cho phép 100 connections tổng.

**Câu hỏi:** vì sao tăng từ 12 lên 30 instances có thể khiến tình hình xấu hơn? Điều chỉnh gì trước?

**Định hướng:** `max_messages` không phải lượng capacity DB. Nếu mỗi instance mở nhiều connections, tổng vượt 100 sẽ gây timeout, nack/redelivery và tăng backlog. Cần **giới hạn pool/concurrency mỗi instance**, chọn số subscriber theo DB capacity, dùng backpressure và đo commit throughput; chỉ tăng workers nếu downstream còn tài nguyên.

### Tình huống B — Batch lớn gây chậm gửi email thông báo

Publisher gửi vài chục sự kiện mỗi giây nhưng đặt `max_messages=1.000` và `max_latency=2` giây. Học viên than phiền email thông báo chậm dù Pub/Sub service khỏe.

**Câu hỏi:** điều chỉnh nào cải thiện độ trễ đầu-cuối? Có nên giảm subscriber flow control trước không?

**Định hướng:** nếu thời gian chờ nằm trong publisher batch, **giảm max latency** và đo publish p95/p99 trước. Không có căn cứ giảm subscriber flow limit khi subscriber chưa nhận message. Với notification gần thời gian thực, chấp nhận nhiều RPC hơn để cải thiện latency.

### Tình huống C — Bão redelivery khi worker bị restart

Subscriber xử lý mỗi message 90 giây, nhưng `max_lease_duration=60` giây và autoscaler thường xuyên thay instance. Sau deploy, nhiều đơn hàng bị ghi hai lần.

**Câu hỏi:** nêu ít nhất ba lớp cần xử lý.

**Định hướng:** điều chỉnh lease management theo processing time thực; graceful shutdown để hoàn thành in-flight khi có thể; giảm outstanding tránh quá tải; idempotency key/DB transaction để chống ghi trùng. Nếu công việc quá dài, chuyển sang workflow/job phù hợp. **Tăng lease** không thay thế chống trùng khi process crash.

### Tình huống D — Hot ordering key

Một publisher đặt `ordering_key="all-enrollments"` cho mọi sự kiện, subscriber cần xử lý 10.000 messages/s nhưng thực tế throughput thấp dù tăng nhiều CPU.

**Câu hỏi:** điều gì đang giới hạn? Đề xuất key khác.

**Định hướng:** mọi message chung một key phải được xử lý có thứ tự, làm mất khả năng song song theo key. Nếu nghiệp vụ chỉ cần thứ tự **trong từng học viên hoặc từng đơn hàng**, dùng `student_id`/`order_id` làm ordering key. Kiểm chứng rằng việc đổi key không làm sai thứ tự của transaction nghiệp vụ.

### Bài tập định lượng

Một hệ thống xử lý **400 messages/s**, thời gian callback trung bình **0,2 giây**, p99 **1,2 giây**, payload trung bình 32 KiB và có lúc lên đến 1 MiB. RAM dành cho outstanding message payload chỉ **16 MiB**.

1. Tính số message đang xử lý/chờ trung bình theo định luật Little.
2. Nếu đặt `max_messages=500` nhưng không giới hạn byte, rủi ro tại thời điểm 500 message lớn đồng thời là gì?
3. Đề xuất một cặp `max_messages`/`max_bytes` **khởi đầu để benchmark**, rồi giải thích vì sao không thể chọn chỉ từ trung bình.
4. Nếu subscriber tổng chỉ ack được **350 messages/s**, sau **30 phút** backlog tăng khoảng bao nhiêu message?

**Gợi ý/đáp án:**

- Outstanding trung bình `400 × 0,2 = 80`.
- 500 message × 1 MiB có thể tương đương **500 MiB payload**, vượt ngân sách 16 MiB rất nhiều.
- Có thể thử `max_messages=100` và `max_bytes=8 MiB`, sau đó điều chỉnh dựa trên memory thực, callback concurrency, p99, ack latency và kích thước message; **đây không phải cấu hình production được bảo đảm**.
- Backlog tăng `(400 - 350) × 1800 = 90.000` message nếu chênh lệch ổn định và không có thay đổi khác.

### Tự kiểm tra

1. **Batching có giống flow control không?** Không; batching gom request, flow control giới hạn outstanding work.
2. **Ba ngưỡng batch count/bytes/latency có cần đồng thời chạm không?** Không; chỉ cần một trong ba chạm.
3. **`publish()` trả Future có đồng nghĩa Pub/Sub nhận message chưa?** Chưa; phải quan sát Future hoàn tất thành công.
4. **Publisher `BLOCK` ảnh hưởng gì?** Tạo backpressure khi outstanding vượt giới hạn client.
5. **Subscriber `max_messages` có phải số thread?** Không; nó giới hạn message outstanding, còn concurrency là cơ chế khác.
6. **Subscriber ack khi nào?** Sau khi xử lý và lưu trạng thái nghiệp vụ thành công.
7. **Flow control subscriber có dừng mọi publisher gửi vào topic không?** Không; subscription backlog có thể tiếp tục tăng.
8. **Vì sao message có thể nhận lại?** At-least-once, ack deadline hết, retry hoặc sự cố kết nối.
9. **Exactly-once có loại bỏ yêu cầu idempotency cho ghi DB không?** Không; Pub/Sub ack và transaction DB không tự là một giao dịch nguyên tử.
10. **Khi backlog age tăng, chỉ cần tăng RAM subscriber?** Không; xác định thiếu throughput, poison messages, lease hoặc downstream bottleneck.

## 11. Tài liệu Google Cloud tham khảo

- [Pub/Sub — Publish best practices](https://cloud.google.com/pubsub/docs/publish-best-practices): batching, retry, xác nhận publish và thông lượng.
- [Pub/Sub — Batch messaging](https://cloud.google.com/pubsub/docs/batch-messaging): count/byte/delay thresholds và giới hạn batch.
- [Pub/Sub — Publisher flow control](https://cloud.google.com/pubsub/docs/flow-control-messages): outstanding messages/bytes, `BLOCK`/`ERROR`/`IGNORE`.
- [Pub/Sub — Subscribe best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices): ack sau xử lý, redelivery, ordering và subscriber flow control.
- [Pub/Sub — Subscriber flow control](https://cloud.google.com/pubsub/docs/flow-control): điều chỉnh StreamingPull/Pull khi traffic spike.
- [Pub/Sub — Lease management](https://cloud.google.com/pubsub/docs/lease-management): ack deadline và gia hạn lease.
- [Pub/Sub — Message ordering](https://cloud.google.com/pubsub/docs/ordering): ordering keys, thứ tự và thông lượng.
- [Pub/Sub — Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery): phạm vi pull subscriptions và các đánh đổi.
- [Pub/Sub — Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics): xử lý poison messages.
- [Pub/Sub — Monitor subscriptions](https://cloud.google.com/pubsub/docs/monitoring): backlog, oldest age, expired deadlines và health metrics.
- [Pub/Sub — Quotas and limits](https://cloud.google.com/pubsub/quotas): kích thước message, publish request và quota.
- [Pub/Sub — Pricing](https://cloud.google.com/pubsub/pricing): phí publish/delivery/retention theo bảng giá hiện hành.
- [Python Pub/Sub SDK](https://cloud.google.com/python/docs/reference/pubsub/latest): `BatchSettings`, `PublishFlowControl` và `FlowControl`.

**Kết luận:** tối ưu Pub/Sub là cân bằng **publisher batching để gửi hiệu quả**, **publisher flow control để tránh tích hàng đợi cục bộ**, và **subscriber flow control/concurrency để không quá tải worker hoặc database**. Kết quả phải được chứng minh bằng **publish/ack throughput, oldest backlog age, p95/p99 latency, redelivery rate, memory và chi phí**, chứ không chỉ bằng việc tăng số message/threads trong cấu hình.
