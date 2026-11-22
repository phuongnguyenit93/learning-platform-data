# Cloud Storage notifications và sự kiện đối tượng

Một hệ thống thương mại điện tử cho khách hàng tải lên ảnh sản phẩm. File được ghi vào **Cloud Storage** qua ứng dụng Java, nhưng việc tạo thumbnail, kiểm tra định dạng và cập nhật danh mục không nên chạy ngay trong request upload: các tác vụ có thể tốn thời gian, thất bại hoặc phải xử lý lại. Thay vào đó, Cloud Storage phát thông báo khi có đối tượng mới; một dịch vụ xử lý sự kiện nhận thông báo và xử lý file độc lập.

**Cloud Storage notifications** giúp kết nối các thay đổi trên object với **Pub/Sub**, từ đó kích hoạt Cloud Run, worker trên GKE/Compute Engine, Dataflow hoặc các dịch vụ khác. Trong học phần **CLOUD_PROVIDERS_GCP**, đây là phần kiến thức của chương **Cloud Storage** gắn với thiết kế project, IAM, VPC, tự động hóa phát hành, khả năng chịu lỗi và quản lý chi phí. Bài này tập trung vào **Pub/Sub notifications cho object changes**, đồng thời giải thích sự khác biệt với Eventarc và các lựa chọn tích hợp khác.

Sau bài này, bạn có thể:

- Mô tả kiến trúc Cloud Storage bucket → Pub/Sub topic → subscription → consumer.
- Phân biệt các event `OBJECT_FINALIZE`, `OBJECT_DELETE`, `OBJECT_ARCHIVE`, `OBJECT_METADATA_UPDATE` và trường hợp `OBJECT_INITIALIZE` dành cho zonal bucket.
- Đọc thông tin `bucketId`, `objectId`, `objectGeneration`, `eventTime` và payload của thông báo.
- Tạo notification configuration với `gcloud storage`, cấu hình IAM đúng cho Cloud Storage service agent và thử nhận event qua Pub/Sub.
- Xử lý sự kiện **at-least-once**, có thể trùng và **không bảo đảm thứ tự** bằng consumer idempotent.
- So sánh Pub/Sub notifications với Eventarc trigger trực tiếp đến Cloud Run.
- Thiết kế retry, dead-letter handling, quan sát, bảo mật dữ liệu và ước lượng chi phí.

> **Lưu ý thực hành:** Tên project, bucket, topic và file trong ví dụ đều là placeholder. Các lệnh tạo tài nguyên hoặc upload có thể phát sinh phí Cloud Storage/Pub/Sub/Cloud Run. Chỉ chạy trong project lab được phép; không chỉnh notification configuration của bucket production khi chưa kiểm kê consumer hiện có.

## 1. Khi nào cần phát sự kiện đối tượng?

Object trong Cloud Storage có **tên (object name)**, nội dung bytes, metadata và **generation**. Các thay đổi thường gặp:

- Upload đối tượng mới, ví dụ `incoming/photo-001.jpg`.
- Upload lại cùng object name, tạo **generation** mới.
- Xóa object hoặc chuyển generation hiện tại thành noncurrent theo Object Versioning.
- Đổi metadata (ví dụ `contentType` hoặc custom metadata), không thay bytes.
- Copy/rewrite/restore object để tạo một generation mới.

Một số ứng dụng không cần chạy logic đồng bộ với upload:

| Nhu cầu | Event có thể dùng | Consumer |
|---|---|---|
| Tạo thumbnail khi ảnh được upload thành công | `OBJECT_FINALIZE` | Cloud Run worker / function |
| Trích xuất nội dung PDF | `OBJECT_FINALIZE` với prefix `documents/` | Worker Java, Dataflow |
| Xóa bản ghi tìm kiếm khi file bị xóa vĩnh viễn | `OBJECT_DELETE` | Search indexing service |
| Ghi nhận một version chuyển sang noncurrent | `OBJECT_ARCHIVE` | Audit/cleanup workflow |
| Đồng bộ metadata sang catalog | `OBJECT_METADATA_UPDATE` | Metadata indexer |
| Theo dõi upload bắt đầu ở zonal bucket | `OBJECT_INITIALIZE` (trường hợp đặc thù) | Pipeline tương thích tính năng zonal bucket |

**Không nên hiểu notification là dữ liệu thực của file.** Thông báo chủ yếu cung cấp thuộc tính sự kiện và metadata; consumer đọc **bytes object** qua Cloud Storage API khi thật sự cần. Việc tên object xuất hiện trong thông báo không chứng minh consumer có quyền đọc object đó.

## 2. Kiến trúc Pub/Sub notifications

~~~mermaid
flowchart LR
    A["Uploader: Java / GKE / Cloud Run"] --> B["Cloud Storage bucket"]
    B --> C["Notification configuration"]
    C --> D["Pub/Sub topic"]
    D --> E["Pull subscription"]
    D --> F["Push subscription"]
    E --> G["Java worker trên VM/GKE/Cloud Run"]
    F --> H["HTTP handler Cloud Run"]
    G --> I["Cloud Storage read + xử lý + DB"]
    H --> I
~~~

Một **notification configuration** gắn vào bucket xác định:

1. Topic Pub/Sub đích, có thể nằm ở **project khác** nếu đủ quyền.
2. Những event type được gửi (hoặc tất cả event type được hỗ trợ nếu không chỉ định).
3. Optional **object name prefix** để chỉ gửi khi object name bắt đầu bằng chuỗi đã chọn.
4. Định dạng payload `JSON_API_V1` hoặc `NONE`.
5. Custom attributes gắn thêm vào mỗi message.

**Topic** lưu luồng message cho các **subscription**. Một topic có thể có nhiều subscription độc lập; mỗi subscription có thể được xử lý bằng pull hoặc push. Nếu hai service muốn cùng xử lý mọi event, tạo **hai subscription** (không phải chỉ hai worker cùng kéo từ một subscription) để mỗi service nhận luồng sự kiện riêng.

Không nhầm:

- **Bucket notification configuration**: định tuyến event của bucket tới topic, không có cơ chế ack ứng dụng.
- **Pub/Sub subscription**: định nghĩa cách consumer nhận, retry, ack và lưu message.
- **Consumer**: xử lý nghiệp vụ thực tế; phải chịu được message trùng, đến muộn hoặc theo thứ tự khác.

### Dòng thời gian một lần upload

~~~text
T0  Client upload incoming/photo.jpg
T1  Cloud Storage tạo generation mới thành công
T2  Notification configuration phát OBJECT_FINALIZE đến Pub/Sub topic
T3  Subscription cung cấp message cho worker
T4  Worker đọc đúng generation, tạo thumbnail và ghi trạng thái xử lý
T5  Worker ack message thành công
~~~

T2–T3 thường diễn ra nhanh nhưng **không có SLA về thời gian phát thông báo**; có trường hợp bị trễ đáng kể. Không thiết kế endpoint HTTP trả thành công cho người dùng dựa trên giả định job sẽ xử lý xong trong vài giây.

## 3. Các loại sự kiện và điều kiện phát sinh

| Event type | Khi nào xảy ra? | Ví dụ | Điều không nên suy luận |
|---|---|---|---|
| `OBJECT_FINALIZE` | Một object generation mới được tạo thành công; gồm upload, copy/rewrite/restore | Upload `photo.jpg` phiên bản mới | Không phát chỉ vì upload thất bại |
| `OBJECT_METADATA_UPDATE` | Metadata của một generation hiện có thay đổi | Sửa `contentType` hoặc custom metadata | Không có nghĩa nội dung bytes đã được thay |
| `OBJECT_DELETE` | Object generation bị xóa **vĩnh viễn** theo mô hình sự kiện của Pub/Sub notifications | Xóa hẳn generation / lifecycle delete | Không đồng nghĩa mọi thao tác archive/versioning |
| `OBJECT_ARCHIVE` | Generation đang live trở thành **noncurrent** khi bật Object Versioning | Upload lại cùng tên làm version cũ noncurrent | Không phải xóa hẳn dữ liệu |
| `OBJECT_INITIALIZE` | Bắt đầu tạo object trong **zonal bucket** theo khả năng hỗ trợ riêng | Bắt đầu upload lên zonal bucket | Không phải event hoàn tất upload; không dùng làm trigger xử lý file đã sẵn sàng |

**Lưu ý về CLI:** tài liệu tham chiếu của `gcloud storage buckets notifications create --event-types` hiện liệt kê bốn loại chính `OBJECT_FINALIZE`, `OBJECT_METADATA_UPDATE`, `OBJECT_DELETE` và `OBJECT_ARCHIVE`. `OBJECT_INITIALIZE` xuất hiện trong tài liệu tổng quan cho **zonal buckets**; cần tra khả năng hỗ trợ API/client cụ thể trước khi yêu cầu cấu hình loại sự kiện này.

### Ghi đè cùng tên: vì sao có nhiều sự kiện?

Giả sử object `images/avatar.jpg` có generation `100`, ứng dụng upload lại cùng tên tạo generation `101`.

| Chế độ bucket | Sự kiện cho generation mới | Sự kiện cho generation cũ |
|---|---|---|
| **Không dùng Object Versioning** | `OBJECT_FINALIZE` cho `101` | `OBJECT_DELETE` cho `100` khi version cũ bị thay thế/xóa vĩnh viễn |
| **Bật Object Versioning** | `OBJECT_FINALIZE` cho `101` | `OBJECT_ARCHIVE` cho `100` (trở thành noncurrent) |

Thông báo `OBJECT_FINALIZE` có thể chứa `overwroteGeneration` = `100`. Thông báo `OBJECT_DELETE` hoặc `OBJECT_ARCHIVE` tương ứng có thể chứa `overwrittenByGeneration` = `101`.

**Không có bảo đảm thứ tự nhận** hai event này. Nếu handler `DELETE` chạy sau `FINALIZE`, việc “xóa theo object name” mà không xét generation có thể xóa nhầm kết quả của generation mới. Phải thiết kế idempotency và concurrency theo **object generation**.

### Soft delete, versioning và lifecycle

**Object Versioning** và **Soft delete** là những cơ chế riêng. Với Eventarc direct events, khái niệm `deleted` có thể dùng cho thao tác soft delete theo định nghĩa của Eventarc; không ánh xạ máy móc với `OBJECT_DELETE` của **Pub/Sub notifications**, vốn được tài liệu mô tả là sự kiện xóa vĩnh viễn. Lifecycle rules, retention policy, object holds và soft delete có thể thay đổi thời điểm object bị loại bỏ thật.

Khi yêu cầu nghiệp vụ là “người dùng bấm xóa thì xóa ngay record trong DB”, cần xác định xem hệ thống muốn phản ứng với **ý định xóa**, **object không còn live**, hay **xóa vĩnh viễn**. Không dùng tên event thay cho phân tích trạng thái dữ liệu.

### Vì sao không dùng notification cho mọi hành động?

Pub/Sub notifications theo dõi các thay đổi object được hỗ trợ, không phát mặc định cho **object read/download**, thay IAM hoặc mọi thao tác ở cấp bucket. Khi cần audit ai đọc hoặc thay đổi IAM, xem **Cloud Audit Logs**; có thể định tuyến audit logs qua sink đến Pub/Sub nếu nhu cầu phù hợp. Không coi notifications là một hệ thống audit đầy đủ.

## 4. Cấu trúc message: attributes và payload

Thông báo Cloud Storage được gửi dưới dạng **Pub/Sub message**, gồm:

- **Attributes:** các cặp key/value mô tả event, luôn có một số trường bắt buộc.
- **Data payload:** tùy cấu hình có thể rỗng hoặc chứa metadata object dạng JSON UTF-8.
- **Envelope Pub/Sub:** `messageId`, `publishTime` và thông tin ack thuộc lớp Pub/Sub, không phải ID bất biến duy nhất của object event.

### Attributes quan trọng

| Attribute | Ví dụ | Ý nghĩa |
|---|---|---|
| `notificationConfig` | `projects/_/buckets/shop-uploads/notificationConfigs/3` | Cấu hình nào tạo thông báo |
| `eventType` | `OBJECT_FINALIZE` | Loại thay đổi |
| `payloadFormat` | `JSON_API_V1` | Dạng payload |
| `bucketId` | `shop-uploads` | Bucket phát event |
| `objectId` | `incoming/photo-001.jpg` | Object name, có thể có dấu `/` |
| `objectGeneration` | `1700000000000000` | Generation được event nói đến |
| `eventTime` | `2026-11-19T01:02:03Z` | Thời điểm sự kiện ở định dạng RFC 3339 |
| `overwroteGeneration` | `1699999999999999` | Generation cũ mà FINALIZE mới thay thế, nếu có |
| `overwrittenByGeneration` | `1700000000000000` | Generation mới thay thế generation bị archive/delete, nếu có |

`objectId` là **object name**, không nhất thiết là thư mục thực; prefix `incoming/` chỉ là phần đầu của tên object theo chuỗi. Nếu object chứa dấu cách hoặc Unicode, consumer phải xử lý URL encoding khi xây đường gọi API thay vì nối chuỗi một cách không an toàn.

### Ví dụ một message dạng khái niệm

~~~json
{
  "message": {
    "messageId": "1234567890123456",
    "publishTime": "2026-11-19T01:02:04Z",
    "attributes": {
      "notificationConfig": "projects/_/buckets/shop-uploads/notificationConfigs/3",
      "eventType": "OBJECT_FINALIZE",
      "payloadFormat": "JSON_API_V1",
      "bucketId": "shop-uploads",
      "objectId": "incoming/photo-001.jpg",
      "objectGeneration": "1700000000000000",
      "eventTime": "2026-11-19T01:02:03Z"
    },
    "data": "eyJraW5kIjoi..."
  }
}
~~~

`data` của một Pub/Sub message khi xuất qua API/CLI ở định dạng JSON thường được **base64 encode**. Sau khi decode, khi chọn `JSON_API_V1`, dữ liệu là **Cloud Storage JSON API Object resource metadata**: các trường như `name`, `bucket`, `generation`, `metageneration`, `size`, `contentType` hoặc `updated` theo trạng thái/event. Đây **không phải bytes ảnh/PDF**. Giá trị base64 phía trên chỉ minh họa cấu trúc.

Với `--payload-format=none`, Pub/Sub `data` không chứa metadata; attributes vẫn có các trường sự kiện. Chọn `none` khi consumer chỉ cần tên/generation và sẽ gọi Storage API để lấy thông tin cần thiết; chọn `json` khi muốn có snapshot metadata trong message, nhưng cần xem giới hạn kích thước và bảo vệ thông tin nhạy cảm.

### Generation và metageneration

**Generation** phân biệt các phiên bản **bytes/object**. **Metageneration** tăng khi metadata của một generation thay đổi; một event metadata update có thể liên quan cùng generation nhưng metageneration khác. Sự kết hợp hữu ích khi thiết kế:

~~~text
bucket + objectName + generation  → khóa một phiên bản nội dung
bucket + objectName + generation + metageneration
                                 → khóa một phiên bản metadata
eventType + các giá trị trên       → khóa nghiệp vụ xử lý sự kiện
~~~

Để tránh ghi đè nhầm, khi xử lý từ event cũ hãy dùng **generation/metageneration preconditions** khi Google Cloud Storage API hỗ trợ (ví dụ `ifGenerationMatch`/`ifMetagenerationMatch`), không chỉ đọc “latest object” theo tên.

## 5. Delivery semantics: không thể giả định exactly-once hoặc đúng thứ tự

Cloud Storage cố gắng gửi thông báo và bảo đảm **at-least-once** khi cấu hình hoạt động. Pub/Sub cũng có thể giao lại message nếu subscriber chưa ack thành công hoặc ack deadline đã hết. Kết quả là **cùng một sự kiện có thể xuất hiện nhiều lần**, có khi dưới **messageId khác nhau** nếu publisher gửi trùng.

Các sự kiện **không được đảm bảo publish/receive theo thứ tự tạo object**. Trong tình huống upload lại một object nhiều lần, consumer có thể nhận `FINALIZE(g=103)` trước `FINALIZE(g=102)`; event cũ đến sau không được phép ghi đè trạng thái mới trong database.

Những bảo đảm cần hiểu:

| Câu hỏi | Trả lời |
|---|---|
| Có đảm bảo mọi event tới ngay trong vài giây? | **Không**. Thường nhanh nhưng có thể trễ lâu, không có SLA delivery time |
| Một object event chỉ tạo đúng một Pub/Sub message? | **Không**. Có thể trùng ngay ở nguồn publish |
| Pub/Sub pull ack thành công có bảo đảm nghiệp vụ “exactly once”? | **Không tự động**; phải thiết kế idempotency và transaction ở consumer |
| Message luôn đến theo thứ tự generation? | **Không** |
| Khi thêm notification, sự kiện cũ có được gửi bù? | **Không nên kỳ vọng**. Cấu hình chỉ bắt đầu phát cho thay đổi sau khi có hiệu lực |
| Có thể dùng Pub/Sub exactly-once subscription? | Có cho **pull** theo điều kiện hỗ trợ, nhưng không loại bỏ event publish trùng với message ID khác |
| Có thể chỉ cần messageId làm idempotency key? | **Không đủ** nếu cùng Cloud Storage event được publish thành nhiều message ID |

Khi tạo notification, có thể cần **tối đa khoảng 30 giây** trước khi cấu hình bắt đầu gửi event; nếu xóa cấu hình, cũng có thể trễ trước khi mọi notification dừng. Nếu Cloud Storage liên tục không publish được do topic mất, quyền Publisher bị thu hồi hoặc quota lỗi, cấu hình notification **có thể bị xóa sau khoảng 7 ngày**. Vì vậy monitoring phải kiểm tra cả **tình trạng configuration**, không chỉ log consumer.

## 6. Thiết kế consumer idempotent và an toàn theo generation

Ví dụ workflow tạo thumbnail:

~~~text
Upload incoming/A.jpg generation=100
      ↓ OBJECT_FINALIZE
Pub/Sub message (có thể lặp / tới trễ)
      ↓
Worker kiểm tra eventType, prefix, bucket, generation
      ↓
Ghi nhận processing key vào database (atomic upsert)
      ↓
Đọc object đúng generation, tạo thumbnail
      ↓
Ghi kết quả với precondition / unique key
      ↓
Đánh dấu DONE, ACK message
~~~

Khóa idempotency gợi ý:

~~~text
key = eventType + "|" + bucketId + "|" + objectId + "|" + objectGeneration
~~~

Với metadata updates, thêm `metageneration` nếu nghiệp vụ muốn xử lý từng thay đổi metadata. Với yêu cầu xử lý nhiều notification configurations cùng trỏ một topic, idempotency key theo **sự kiện nghiệp vụ**, không nhất thiết chứa `notificationConfig`: nếu cùng event được gửi từ hai cấu hình, bạn thường chỉ muốn xử lý một lần.

### Thuật toán xử lý mẫu

~~~text
onMessage(message):
  attrs = message.attributes
  validate attrs.eventType, bucketId, objectId, objectGeneration

  if attrs.eventType != "OBJECT_FINALIZE":
      ACK; return
  if not attrs.objectId.startsWith("incoming/"):
      ACK; return

  key = hash("thumbnail|" + attrs.bucketId + "|" +
             attrs.objectId + "|" + attrs.objectGeneration)

  if processingStore.hasStatus(key, DONE):
      ACK; return

  try:
      # Atomic claim, lease hoặc lock ngắn hạn để tránh hai worker chạy cùng lúc.
      claimJob(key)

      # ĐỌC ĐÚNG generation, không đọc phiên bản live mới hơn theo tên.
      source = storage.read(
          bucket=attrs.bucketId,
          name=attrs.objectId,
          generation=attrs.objectGeneration)

      thumbnail = transform(source)
      output = "thumbnails/" + hash(attrs.objectId) + "/" +
               attrs.objectGeneration + ".jpg"

      # Create-if-absent (ifGenerationMatch=0) hoặc kiểm tra đích đã tồn tại.
      storage.write(output, thumbnail, precondition=createIfAbsent)

      markDone(key, output)
      ACK

  except TemporaryFailure:
      NACK hoặc để ack deadline hết để Pub/Sub retry
  except PermanentInvalidInput:
      lưu trạng thái lỗi có thể kiểm toán, sau đó ACK/đưa sang DLQ
~~~

**Đây là pseudocode**, không phải mã Java chạy trực tiếp. Khóa và thao tác `claimJob` phải **atomic** (ví dụ unique constraint/transaction trong Cloud SQL hoặc cơ chế tương đương); kiểm tra `exists` rồi ghi không atomic vẫn có race condition. Khi lỗi xảy ra giữa “upload thumbnail” và “markDone”, lần retry có thể gặp output đã tồn tại: phải xử lý trạng thái này như một lần chạy hợp lệ, không tạo thumbnail trùng hoặc ghi đè phiên bản khác.

### Trường hợp source generation không còn đọc được

Nếu bucket không bật Object Versioning, generation cũ có thể đã bị thay thế/xóa trước khi worker nhận event. Khi gọi read với generation được event nêu, API có thể trả `404`. Consumer cần chính sách rõ:

- Chấp nhận **skip as stale** khi chỉ cần xử lý generation mới nhất.
- Bật Object Versioning hoặc lưu staging object theo tên bất biến nếu mỗi generation bắt buộc được xử lý.
- Xử lý retry cho lỗi transient nhưng **không retry vô hạn** một generation đã bị xóa hẳn.
- Giữ kết quả/nguyên nhân lỗi để kiểm toán và khôi phục bằng quy trình ngoài luồng.

**Không đọc `gs://bucket/path` không chỉ định generation** để xử lý event cũ nếu nghiệp vụ phải đúng nội dung file tại thời điểm sự kiện.

## 7. Chuẩn bị IAM và Pub/Sub trước khi cấu hình notification

Giả sử bucket và Pub/Sub topic nằm trong cùng project để bắt đầu học. Khi thiết kế thực tế, chúng **có thể ở hai project khác nhau**; khi đó dùng đúng project của bucket để xác định service agent và cấp quyền publish ở **topic project**.

Những đối tượng có quyền khác nhau:

| Danh tính | Quyền cần thiết | Phạm vi nên cấp |
|---|---|---|
| Người/pipeline tạo notification configuration | Quyền cập nhật cấu hình bucket, chẳng hạn `storage.buckets.update`; quyền xem topic và quản trị topic nếu cần | Bucket và topic liên quan |
| **Cloud Storage service agent** của project chứa bucket | `pubsub.topics.publish`, thường cấp `roles/pubsub.publisher` | **Chính topic đích** |
| Người/pipeline tạo topic và subscription | `pubsub.topics.create`, `pubsub.subscriptions.create` cùng quyền liên quan | Project/tài nguyên Pub/Sub |
| Worker đọc subscription | `pubsub.subscriptions.consume`, thường cấp `roles/pubsub.subscriber` | Subscription cụ thể |
| Worker đọc dữ liệu object | `storage.objects.get`, ví dụ vai trò Object Viewer phù hợp | Bucket hoặc managed folder chứa dữ liệu được phép |
| Cloud Run/Eventarc trigger identity | Các vai trò nhận event và gọi Cloud Run theo cấu hình | Trigger, destination service |

**Đặc biệt:** service agent xuất bản notification **khác** service account mà Java worker dùng để đọc bucket. Cấp Pub/Sub Publisher cho Java worker không giúp Cloud Storage gửi event nếu **service agent** thiếu quyền. Ngược lại, Pub/Sub Subscriber không tự cho worker quyền tải ảnh từ Cloud Storage.

### Lấy Cloud Storage service agent

~~~bash
BUCKET_PROJECT="my-storage-project"
TOPIC_PROJECT="my-events-project"
TOPIC="object-events"

# Lấy email service agent do Google Cloud quản lý cho project CHỨA BUCKET.
gcloud storage service-agent --project="$BUCKET_PROJECT"
~~~

Ví dụ dạng email trả về:

~~~text
service-123456789012@gs-project-accounts.iam.gserviceaccount.com
~~~

Đây là định danh minh họa, không phải email dùng được trên project thực. Chỉ cấp quyền lên **topic cần publish**, ví dụ sau khi thay email chính xác:

~~~bash
SERVICE_AGENT="service-123456789012@gs-project-accounts.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --project="$TOPIC_PROJECT" \
  --member="serviceAccount:$SERVICE_AGENT" \
  --role="roles/pubsub.publisher"
~~~

CLI tạo notification có thể **tự kiểm tra và thử cấp** quyền Pub/Sub Publisher cho service agent nếu người thao tác đủ quyền. Trong hệ thống hạn chế IAM, tốt hơn để pipeline platform tạo IAM binding có kiểm soát rồi dùng `--skip-topic-setup` khi cần. Sau khi cấp role, cần tính cả thời gian IAM propagation trước khi thử event.

**Khác project:** bucket ở project A, topic ở project B → service agent của **A** phải được cấp Publisher trên topic của **B**; notification configuration trên bucket A ghi đường topic đầy đủ `projects/B/topics/TOPIC`. Không cấp sai service agent của project B.

## 8. Thực hành CLI từ bucket đến thông báo

Ví dụ các lệnh dưới đây dùng **Bash** với Cloud SDK đã đăng nhập và có quyền trong project lab. Người học phải thay tên bucket globally unique và project thực. Để tránh tạo/xóa bucket không cần thiết, giả sử bucket `shop-uploads-lab-unique` đã được chuẩn bị, có uniform bucket-level access và không chứa dữ liệu quan trọng.

### Bước 1 — Tạo topic và subscription trước khi thử upload

~~~bash
BUCKET_PROJECT="my-storage-project"
TOPIC_PROJECT="my-events-project"
BUCKET="shop-uploads-lab-unique"
TOPIC="object-events"
SUB="object-events-debug"

gcloud services enable pubsub.googleapis.com --project="$TOPIC_PROJECT"

gcloud pubsub topics create "$TOPIC" \
  --project="$TOPIC_PROJECT"

# Tạo subscription trước để không bỏ lỡ messages khi demo bắt đầu.
gcloud pubsub subscriptions create "$SUB" \
  --project="$TOPIC_PROJECT" \
  --topic="$TOPIC"

gcloud pubsub topics describe "$TOPIC" --project="$TOPIC_PROJECT"
gcloud pubsub subscriptions describe "$SUB" --project="$TOPIC_PROJECT"
~~~

Lệnh tạo topic/subscription sẽ báo lỗi nếu tài nguyên đã tồn tại; trong hệ thống đang chạy, **kiểm tra trước rồi mới áp dụng** qua IaC. Topic có thể có nhiều subscription độc lập, chẳng hạn một cho xử lý thumbnail và một cho cập nhật search index.

### Bước 2 — Cấp quyền Publisher cho service agent

Lấy email service agent của `BUCKET_PROJECT` như mục 7 rồi cấp `roles/pubsub.publisher` trên topic thuộc `TOPIC_PROJECT`. Kiểm tra IAM policy của topic trước khi tạo notification:

~~~bash
gcloud pubsub topics get-iam-policy "$TOPIC" \
  --project="$TOPIC_PROJECT"
~~~

### Bước 3 — Tạo notification configuration có lọc event và prefix

~~~bash
gcloud storage buckets notifications create "gs://$BUCKET" \
  --topic="projects/$TOPIC_PROJECT/topics/$TOPIC" \
  --event-types=OBJECT_FINALIZE,OBJECT_DELETE \
  --object-prefix="incoming/" \
  --payload-format=json

# Kiểm tra danh sách configuration của bucket.
gcloud storage buckets notifications list "gs://$BUCKET"
~~~

Lệnh tạo configuration sẽ chọn **chỉ hai event type**. Vì có `--object-prefix=incoming/`, các object có tên bắt đầu bằng `incoming/` mới được xét; object `archive/photo.jpg` không match. Prefix là **chuỗi đầu tên**, không phải regex, glob hay bộ lọc đuôi `.jpg`. Cần kiểm tra cả ký tự viết hoa, slash và cách ứng dụng xây object name.

Nếu muốn topic nhận mọi loại event được hỗ trợ, bỏ `--event-types`. Nếu muốn message không có metadata body, chọn `--payload-format=none`. Để thêm custom attributes, xem `--custom-attributes` trong `gcloud storage buckets notifications create --help`.

**Quan trọng:** Không thể quản lý **Pub/Sub notification configurations** của Cloud Storage bằng giao diện Cloud Storage Console theo tài liệu hiện hành; sử dụng Cloud CLI, client library hoặc JSON API. Console vẫn có thể giúp quản trị **Pub/Sub topics/subscriptions** và quan sát message, nhưng không thay thế lệnh tạo configuration gắn với bucket.

### Bước 4 — Đọc lại cấu hình trước khi tạo event thử

Sau lệnh `list`, mỗi configuration có một **ID**. Với ID ví dụ `3`:

~~~bash
gcloud storage buckets notifications describe \
  "projects/_/buckets/$BUCKET/notificationConfigs/3"
~~~

Không sao chép ID `3` cho mọi bucket: ID thực tế được Cloud Storage trả về. Cần lưu nó vào registry/Infrastructure as Code để biết chính xác configuration nào đang phục vụ hệ thống.

### Bước 5 — Upload tệp thử, kiểm tra Pub/Sub

Chờ cấu hình có hiệu lực (có thể mất tới khoảng 30 giây), sau đó tạo file test ở **máy lab**, không trên workspace dự án đang soạn bài:

~~~bash
# Chỉ là lệnh minh họa chạy trong môi trường lab.
printf 'demo upload event\n' > upload-demo.txt

gcloud storage cp ./upload-demo.txt \
  "gs://$BUCKET/incoming/upload-demo.txt"

gcloud pubsub subscriptions pull "$SUB" \
  --project="$TOPIC_PROJECT" \
  --limit=10 \
  --auto-ack \
  --format=json
~~~

`--auto-ack` **chỉ phù hợp với subscription debug**: message đã nhận sẽ được ack ngay, không còn để worker khác trong **cùng subscription** xử lý. Trong production, consumer phải ack **sau khi hoàn tất xử lý bền vững**. Dùng một subscription debug riêng để không ăn mất message trên subscription sản xuất.

Kết quả CLI có thể hiển thị `message.attributes.eventType` là `OBJECT_FINALIZE`, `objectId` là `incoming/upload-demo.txt` và `objectGeneration` có giá trị số thực. Trường `message.data` (nếu có) là base64 của metadata JSON. Đừng kỳ vọng nhìn thấy nguyên văn nội dung `demo upload event` trong payload.

### Bước 6 — Thử DELETE, rồi đọc lại event

~~~bash
# Chỉ xóa OBJECT VỪA TẠO TRÊN BUCKET LAB.
gcloud storage rm "gs://$BUCKET/incoming/upload-demo.txt"

gcloud pubsub subscriptions pull "$SUB" \
  --project="$TOPIC_PROJECT" \
  --limit=10 \
  --auto-ack \
  --format=json
~~~

Thời điểm và loại sự kiện liên quan deletion có thể chịu ảnh hưởng Object Versioning/Soft delete/retention của bucket. Nếu không thấy `OBJECT_DELETE`, kiểm tra cấu hình bucket, event matching, thời gian chờ và semantics xóa thực tế; không vội kết luận pipeline hỏng.

### Bước 7 — Gỡ cấu hình lab an toàn

~~~bash
gcloud storage buckets notifications list "gs://$BUCKET"

# Xóa đúng notification ID, KHÔNG truyền cả gs://BUCKET vào lệnh delete.
gcloud storage buckets notifications delete \
  "projects/_/buckets/$BUCKET/notificationConfigs/3"
~~~

Lưu ý cực kỳ quan trọng: `gcloud storage buckets notifications delete gs://BUCKET` có thể **xóa toàn bộ notification configurations trong bucket**. Chỉ xóa chính xác ID đã xác nhận thuộc bài lab; đừng xóa các cấu hình của service khác. Xóa notification configuration **không tự xóa** topic/subscription Pub/Sub. Cần rà soát consumer và retention trước khi dọn các tài nguyên này; một số notification có thể tiếp tục phát trong khoảng thời gian ngắn sau lệnh xóa.

## 9. Quản lý cấu hình bằng Terraform

Đối với nhiều project/environments, nên đưa notification, topic, subscription và quyền IAM service agent vào Infrastructure as Code. Ví dụ HCL mô tả **bucket đã tồn tại**, tạo topic và pull subscription phục vụ một pipeline:

~~~hcl
variable "bucket_project_id" {
  type = string
}

variable "topic_project_id" {
  type = string
}

variable "bucket_name" {
  type = string
}

# Tìm đúng service agent của project CHỨA BUCKET.
data "google_storage_project_service_account" "bucket" {
  project = var.bucket_project_id
}

resource "google_pubsub_topic" "objects" {
  project = var.topic_project_id
  name    = "object-events"
}

resource "google_pubsub_topic_iam_member" "publisher" {
  project = var.topic_project_id
  topic   = google_pubsub_topic.objects.name
  role    = "roles/pubsub.publisher"
  member  = format(
    "serviceAccount:%s",
    data.google_storage_project_service_account.bucket.email_address
  )
}

resource "google_storage_notification" "incoming_finalized" {
  bucket             = var.bucket_name
  topic              = google_pubsub_topic.objects.id
  payload_format     = "JSON_API_V1"
  event_types        = ["OBJECT_FINALIZE"]
  object_name_prefix = "incoming/"

  depends_on = [google_pubsub_topic_iam_member.publisher]
}

resource "google_pubsub_subscription" "thumbnail_worker" {
  project = var.topic_project_id
  name    = "thumbnail-worker"
  topic   = google_pubsub_topic.objects.id
}
~~~

Đây là **mẫu tham khảo**: còn cần `terraform` provider/credentials, bật API, cấp quyền cho CI/CD, cấu hình retry/dead-letter và xử lý object. Với bucket đã có notification thủ công, phải **import resource hoặc xử lý kế hoạch chuyển giao ownership**, tránh tạo trùng configuration và khiến consumer nhận hai bản event.

Nếu nhiều ứng dụng muốn cùng xử lý `OBJECT_FINALIZE`, thường nên dùng **một notification configuration → một topic → nhiều subscriptions** thay vì tạo một configuration cho mỗi application. Mô hình này giảm nguy cơ chạm giới hạn bucket và đơn giản hóa vận hành; vẫn cần quyền Pub/Sub cho từng consumer.

### Giới hạn số notification configurations

Theo tài liệu Cloud Storage, mỗi bucket có:

- Tối đa **100 notification configurations tổng cộng**.
- Tối đa **10 configurations cùng đăng ký một event type cụ thể**.
- Mỗi configuration có một ID riêng và có thể gửi sang topic ở project khác.

Với nhiều team, nên dùng topic như một **event bus** (có owner, retention và governance). Không cho từng nhóm tự tạo hàng chục configurations trên cùng bucket production mà không có registry; một số Cloud Run/Eventarc triggers cũng có thể tiêu tốn slot notification tùy mô hình.

## 10. Eventarc trực tiếp đến Cloud Run khác Pub/Sub notifications ra sao?

Cloud Storage có thể kích hoạt **Eventarc Standard direct events** và Cloud Run functions mà không bắt người dùng tự quản topic/subscription. Cơ chế có thể dùng Pub/Sub ở phía dưới, nhưng giao diện cho developer khác.

| Tiêu chí | Pub/Sub notifications trực tiếp | Eventarc direct events |
|---|---|---|
| Cấu hình đầu vào | Bucket notification → topic → subscription | Eventarc trigger với filters và destination |
| Payload nhận ở ứng dụng | Pub/Sub message attributes/data | **CloudEvents** qua HTTP theo định dạng Eventarc |
| Phù hợp | Fan-out nhiều consumer, pull worker, xử lý theo batch, subscription riêng | Sự kiện gửi thẳng tới Cloud Run và destination được Eventarc hỗ trợ |
| Retry/ack | Tùy Pub/Sub subscription và consumer | Eventarc quản lý delivery/retry theo trigger |
| Location | Topic có thể ở project khác với bucket nếu đủ IAM | Direct Storage trigger có ràng buộc project/location theo dịch vụ |
| Tên event | `OBJECT_FINALIZE`, `OBJECT_DELETE`,... | `google.cloud.storage.object.v1.finalized`, `deleted`,... |
| Khả năng replay | Có thể quản lý retention/seek của Pub/Sub khi đã nhận message | Không coi Eventarc là kho lưu sự kiện vô hạn |

Ví dụ đường đi:

~~~text
Cloud Storage OBJECT_FINALIZE
   → (A) Notification configuration → Pub/Sub topic → Pull Java worker

Cloud Storage object finalized
   → (B) Eventarc direct trigger → CloudEvents HTTP → Cloud Run
~~~

Khi dùng **Eventarc direct events cho Cloud Storage**, bucket cần ở **cùng project** và **location tương thích** với trigger theo tài liệu (region, dual-region hoặc multi-region được hỗ trợ). Destination Cloud Run thường ở **cùng project** với trigger, có thể chạy ở region được dịch vụ hỗ trợ khác. Trigger identity cần quyền nhận event và gọi Cloud Run; service identity cần quyền đọc object nếu nội dung phải được xử lý.

Các event type Eventarc direct gồm ví dụ:

~~~text
google.cloud.storage.object.v1.finalized
google.cloud.storage.object.v1.deleted
google.cloud.storage.object.v1.archived
google.cloud.storage.object.v1.metadataUpdated
~~~

Không lấy tên `OBJECT_FINALIZE` từ Pub/Sub notification rồi đưa nguyên vào `--event-filters=type=...` của Eventarc; và **không đưa nguyên envelope Pub/Sub** vào code handler CloudEvents mà không chuyển đổi.

### Khi nào chọn mỗi cách?

- **Một Cloud Run service duy nhất** cần xử lý object finalized và muốn ít cấu hình hạ tầng: cân nhắc Eventarc direct trigger.
- **Nhiều hệ thống** (Java worker, Dataflow, search indexing, audit) cùng cần event: Pub/Sub topic với nhiều subscription thường rõ ràng hơn.
- Cần **quản lý backlog, flow control, pull-based processing, retry và DLQ**: Pub/Sub subscription mang lại công cụ trực tiếp.
- Cần theo dõi **truy cập object** hay một hành động bucket không thuộc danh sách object changes: xem Cloud Audit Logs và khả năng route log qua Pub/Sub/Eventarc tương ứng.

**Không phải mọi trigger đều “miễn phí” hoặc không ảnh hưởng notification quota**. Cần xem nguyên tắc và hạn mức hiện hành của Cloud Storage, Eventarc, Pub/Sub và Cloud Run cùng nhau.

## 11. Tổ chức Java consumer và Cloud Run worker

Ở hệ thống Java, có hai kiểu phổ biến:

**Pull subscription:** Worker chạy trên Compute Engine, GKE hoặc một dịch vụ có vòng đời xử lý phù hợp. Nó sử dụng thư viện Google Cloud Pub/Sub, tự nhận, xử lý và ack message. Đây là cách thuận tiện khi muốn kiểm soát concurrency, flow control và xử lý khối lượng lớn.

**Push subscription:** Pub/Sub gửi HTTP POST đến endpoint như Cloud Run. Dịch vụ xác thực request, xử lý sự kiện, trả HTTP thành công để xác nhận; nếu không thành công theo quy tắc Pub/Sub, message có thể được gửi lại. Với Cloud Run cần thiết kế **authenticated push**, service account OIDC và quyền gọi `roles/run.invoker`; không để endpoint nghiệp vụ nhận event công khai nếu không cần.

### Thiết kế Java pull subscriber

Pseudocode ở mức interface, thể hiện thứ tự xử lý — **chưa phải một project Java biên dịch độc lập**:

~~~java
// Giả định có Pub/Sub Subscriber, Cloud Storage client và repository.
void onPubsubMessage(PubsubMessage message, AckReplyConsumer consumer) {
    Map<String, String> a = message.getAttributesMap();

    String type = a.get("eventType");
    String bucket = a.get("bucketId");
    String object = a.get("objectId");
    String generation = a.get("objectGeneration");

    if (!"OBJECT_FINALIZE".equals(type)
            || bucket == null || object == null
            || generation == null || !object.startsWith("incoming/")) {
        consumer.ack();
        return;
    }

    String jobKey = "thumbnail:" + bucket + ":" + object + ":" + generation;
    try {
        // Phải có unique constraint/transaction hoặc lock phân tán.
        if (repository.isDone(jobKey)) {
            consumer.ack();
            return;
        }

        // Đọc generation ĐÚNG trong Cloud Storage, không mặc định latest.
        BlobId blobId = BlobId.of(bucket, object, Long.parseLong(generation));
        Blob blob = storage.get(blobId);

        if (blob == null) {
            repository.markStale(jobKey, "Source generation is unavailable");
            consumer.ack();
            return;
        }

        byte[] bytes = blob.getContent();
        byte[] thumbnail = imageProcessor.resize(bytes);

        // Hàm này phải ghi idempotently, dùng output name có generation
        // và precondition, không overwrite output của generation mới.
        repository.commitThumbnailOnce(jobKey, thumbnail);
        consumer.ack();
    } catch (RetryableProcessingException ex) {
        consumer.nack();
    } catch (InvalidImageException ex) {
        repository.recordPermanentError(jobKey, ex.getMessage());
        consumer.ack();
    }
}
~~~

Các tên `repository`, `storage`, `imageProcessor` và exception là đối tượng/phương thức **do ứng dụng tự triển khai**; `getContent()` tải toàn bộ bytes vào RAM nên chỉ phù hợp file nhỏ. Với video/PDF lớn, dùng streaming và giới hạn memory/runtime; có thể giao việc nặng cho Dataflow hoặc các worker có tài nguyên phù hợp.

**Quan trọng:** `repository.isDone` đứng riêng trước `commitThumbnailOnce` **không đủ ngăn race**. Cần claim/commit có tính nguyên tử. Khi consumer bị crash sau khi tạo output nhưng trước ack, lần chạy lại phải nhận biết output đã có và kết thúc thành công, không tạo dữ liệu trùng.

### Khác biệt ack ở pull và push

| Kiểu subscriber | Khi xử lý thành công | Khi tạm thời lỗi | Vấn đề cần chú ý |
|---|---|---|---|
| **Pull** | Gọi `ack` sau durable commit | `nack` hoặc chờ ack deadline hết | Điều chỉnh flow control/ack extension |
| **Push HTTP** | Trả response thành công theo Pub/Sub push semantics | Trả mã phản hồi không thành công hoặc timeout | Service phải kiểm tra authentication và xử lý retry |
| **Eventarc → Cloud Run** | Handler xử lý CloudEvent và trả thành công | Eventarc retry theo cấu hình | Payload là CloudEvent, không phải envelope Pub/Sub notifications truyền thống |

Không ack ngay khi vừa parse JSON nếu chưa ghi kết quả bền vững. Cũng không retry vô hạn với file hỏng vĩnh viễn: nên lưu trạng thái lỗi, alert hoặc đưa sang **dead-letter topic (DLQ)** theo khả năng Pub/Sub và nhu cầu vận hành.

## 12. Retry, dead-letter handling và phục hồi backlog

Những lỗi thường gặp:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| **Transient** | Cloud SQL timeout, quota tạm thời, API 5xx | Retry với backoff, giới hạn concurrency |
| **Poison message** | Event malformed, MIME không hỗ trợ, object bytes không hợp lệ | Lưu lỗi, đưa DLQ hoặc ack sau khi xác nhận không thể xử lý |
| **Stale generation** | File bị overwrite trước khi worker đọc version cũ | Dùng Object Versioning hoặc skip có ghi nhận |
| **Duplicate delivery** | Ack deadline hết, Pub/Sub giao lại | Dedupe theo business key, idempotent writes |
| **Out-of-order delivery** | Event generation 102 đến sau 103 | So sánh generation; dùng preconditions |
| **Slow consumer** | Một file lớn mất nhiều phút | Flow control, streaming, gia hạn ack deadline hoặc chia job |
| **Publisher không gửi được** | Topic mất, service agent mất Publisher role | Kiểm tra configuration, IAM, Pub/Sub publish quota |

### Dead-letter topic

Pub/Sub có thể chuyển message qua **dead-letter topic** khi số lần giao thất bại vượt ngưỡng được hỗ trợ. Cần tạo DLQ, cấp IAM đúng cho Pub/Sub service agent, chọn max delivery attempts và có worker/alert để điều tra và replay sau khi sửa lỗi.

**DLQ không phải nơi “bỏ qua lỗi vĩnh viễn”.** Nếu có 200 ảnh lỗi do một bug của parser, khi sửa bug cần biết cách gửi lại những công việc hợp lệ. Dùng `jobKey` và trạng thái xử lý để tránh lặp tác dụng phụ khi replay. Nếu DLQ tăng liên tục, hệ thống đang gặp sự cố dù HTTP upload thành công.

### Bảo vệ subscription khi consumer ngừng hoạt động

Nếu worker dừng vài giờ, message tồn trong subscription theo **message retention policy** và giới hạn backlog hiện hành. Khi worker trở lại, nó có thể nhận một lượng lớn event quá cũ hoặc đã hết ý nghĩa nghiệp vụ.

Đề xuất:

1. Monitor `num_undelivered_messages` và `oldest_unacked_message_age`.
2. Chọn message retention/ack deadline phù hợp với RTO và tính chất job.
3. Giới hạn số concurrent jobs để không làm quá tải Cloud SQL hoặc API downstream.
4. Đánh dấu stale events theo generation, nhưng không loại bỏ tùy tiện các job cần tuân thủ audit.
5. Khi phát hiện mất message hoặc notification config bị xóa, chạy **reconciliation**: liệt kê object/generation cần xử lý rồi so với processing registry; tạo jobs bù theo quyền và phạm vi đã duyệt.

**Không thể dùng sự kiện để bảo đảm không bao giờ sai lệch dữ liệu.** Một hệ thống quan trọng nên có cơ chế so sánh định kỳ giữa danh mục object và bảng trạng thái xử lý; Pub/Sub notifications cung cấp luồng phản ứng nhanh, còn reconciliation giúp khôi phục khi có thiếu sót vận hành.

## 13. Bảo mật: event có thể chứa metadata nhạy cảm

Tên object có thể chứa ID khách hàng, email, tên báo cáo hoặc cấu trúc đường dẫn nội bộ. Payload `JSON_API_V1` còn có thể chứa content type, custom metadata và các thuộc tính khác. Vì thế, event message cũng là **dữ liệu cần bảo vệ**.

Checklist bảo mật:

- **Bucket permissions:** uploader chỉ được ghi vào prefix/phạm vi cần thiết; worker chỉ được đọc những object cần xử lý, hạn chế xóa.
- **Topic Publisher:** cấp `roles/pubsub.publisher` cho **Cloud Storage service agent** đúng project chứa bucket trên topic cần thiết, không cấp quyền rộng toàn project theo thói quen.
- **Subscription Consumer:** worker identity có `roles/pubsub.subscriber` trên subscription được giao, không cho quyền đọc mọi topic không liên quan.
- **Compute/Cloud Run identity:** dùng service account riêng cho mỗi pipeline; không dùng khóa JSON dài hạn khi có thể dùng Workload Identity hoặc token ngắn hạn.
- **Cloud Run push authentication:** xác thực token OIDC của Pub/Sub/Eventarc, không coi request đến từ Internet là đáng tin chỉ vì có JSON đúng shape.
- **Encryption và retention:** xem CMEK, IAM của Cloud Storage/Pub/Sub, thời gian giữ message, logs và dữ liệu xử lý theo yêu cầu doanh nghiệp.
- **Object name từ event là input không tin cậy:** validate prefix, loại file, kích thước, ký tự lạ, tránh path traversal hoặc SQL injection khi ghi vào DB/filesystem.
- **Không ghi bytes hoặc thông tin nhạy cảm vào log**; ưu tiên log có event type, hash/object ID đã kiểm soát, generation, status và trace/correlation ID.

Nếu ứng dụng xử lý file người dùng không đáng tin cậy (PDF, ảnh, CSV), cần cách ly parser, giới hạn bộ nhớ/CPU, kiểm tra loại file và đề phòng file nén độc hại, thay vì chỉ tin vào `contentType` từ metadata.

## 14. Monitoring, logging và cảnh báo sự kiện

Để vận hành pipeline đáng tin cậy, theo dõi **cả ba tầng**:

1. **Cloud Storage:** bucket notification configurations, thay đổi IAM, số object mới, operation failures.
2. **Pub/Sub:** publish/message backlog, unacked age, push errors, dead-letter messages, quota và retention.
3. **Consumer:** request count, xử lý thành công/thất bại, duration, retry count, duplicate/stale count và chi phí backend.

| Metric/đầu mối | Mục tiêu quan sát | Dấu hiệu cần xử lý |
|---|---|---|
| Notification configuration inventory | Cấu hình vẫn tồn tại và trỏ đúng topic | Không thấy config sau lỗi publish kéo dài |
| `subscription/num_undelivered_messages` | Số message đang đợi | Backlog tăng liên tục |
| `subscription/oldest_unacked_message_age` | Độ trễ message lâu nhất chưa ack | SLO xử lý file bị vi phạm |
| Push request errors / ack deadline expirations | Subscriber nhận và ack ổn định | 4xx/5xx/timeout tăng |
| DLQ message count | Lỗi kéo dài cần người xử lý | Poison message lặp lại |
| `processed / failed / stale / duplicate` theo event type | Chất lượng xử lý nghiệp vụ | Thành công giảm hoặc nhiều stale bất thường |
| Cloud Run CPU/memory/concurrency | Worker đủ tài nguyên | Quá tải khi ảnh lớn |
| Storage operations và Pub/Sub throughput | Dự toán chi phí | Volume sự kiện hoặc đọc object tăng đột biến |

### Ví dụ structured log trong consumer

~~~json
{
  "severity": "INFO",
  "eventType": "OBJECT_FINALIZE",
  "bucket": "shop-uploads",
  "objectKeyHash": "sha256:example",
  "generation": "1700000000000000",
  "jobState": "DONE",
  "attempt": 1,
  "durationMs": 340,
  "correlationId": "thumbnail-job-001"
}
~~~

Không cần log toàn bộ `PubsubMessage.data` hoặc nội dung file. Với mỗi event, ghi đủ thông tin để truy vết quyết định `ACK`, `NACK`, `DLQ` và kết quả dữ liệu; bảo vệ logs bằng IAM và retention phù hợp.

### Runbook khi không có event

1. Xác minh object thay đổi **sau** thời điểm notification configuration có hiệu lực.
2. Kiểm tra bucket name, event type, prefix, và Object Versioning/Soft delete.
3. Chạy `gcloud storage buckets notifications list gs://BUCKET` và so với configuration ID trong registry.
4. Kiểm tra topic đích tồn tại, Pub/Sub Publisher role của đúng service agent và publish quota.
5. Kiểm tra subscription tồn tại và đã được tạo đúng topic; một topic không có subscription phù hợp sẽ không cho worker nhận message cũ về sau.
6. Kiểm tra message đã được consumer khác ack trong **cùng subscription** hay chưa.
7. Kiểm tra backlog, dead-letter messages, Cloud Run/worker logs và vùng thời gian quan sát.
8. Nếu thiếu dữ liệu nghiệp vụ, dùng reconciliation để bù; không dựa vào việc “upload lại mọi object” khi điều đó tạo generation mới và nhiều event mới.

## 15. Chi phí và hạn mức vận hành

Một luồng sự kiện có nhiều nhóm chi phí:

| Thành phần | Chi phí có thể phát sinh | Cách kiểm soát |
|---|---|---|
| **Cloud Storage** | Lưu object, thao tác API, network/đọc dữ liệu, versioning/soft delete theo cấu hình | Lifecycle, lựa chọn storage class, retention, đo hoạt động |
| **Pub/Sub** | Lưu lượng message, retention, số lần delivery và tính năng tương ứng | Lọc sự kiện ngay từ nguồn, tối ưu subscription |
| **Cloud Run / worker** | CPU, memory, thời gian xử lý, request, network | Concurrency, timeouts, streaming, autoscaling |
| **Eventarc** | Các sự kiện được định tuyến theo gói dịch vụ | Chỉ tạo trigger thực sự cần |
| **Cloud Logging/Monitoring** | Lượng log, retention và metric tùy sử dụng | Sampling có chủ đích, không log payload |
| **Downstream** | Cloud SQL, BigQuery, image/video processing, API đối tác | Batching, idempotency, retry/backoff |

Ví dụ nếu mỗi ngày upload 1 triệu ảnh và **hai notification configurations** cùng gửi `OBJECT_FINALIZE` đến một topic, số Pub/Sub messages và công việc downstream có thể tăng đáng kể dù mỗi ảnh chỉ có một generation. Còn nếu một topic có hai **subscriptions**, mỗi subscription nhận luồng riêng vì mục đích fan-out — đó là hành vi mong đợi, nhưng vẫn tính chi phí delivery và xử lý.

Các thực hành tiết kiệm:

- Cấu hình `--event-types` và `--object-prefix` **đúng phạm vi** để giảm event không cần thiết.
- Dùng một topic và nhiều subscriptions thay vì nhiều notification configurations chồng chéo.
- Chỉ đọc bytes khi cần; payload `JSON_API_V1` thường đủ cho use case cập nhật metadata.
- Dùng cache hoặc database processing registry để tránh chạy tác vụ nặng khi nhận duplicate event.
- Đặt giới hạn worker concurrency, retry và retention; theo dõi bất thường trên billing.
- Đặt Cloud Billing budgets/alerts, nhưng nhớ **budget alert không phải hard stop** cho event processing.

Không nên tối ưu chi phí bằng cách tắt logging/retention tùy tiện nếu điều đó khiến không thể khôi phục dữ liệu hoặc phân tích sự cố.

## 16. Tình huống tích hợp: xử lý ảnh sản phẩm

Một hệ thống Java cho phép seller upload ảnh sản phẩm:

~~~text
Seller Web/Mobile
     ↓
Java API → tạo upload URL/quyền upload vào Cloud Storage
     ↓
Bucket: product-uploads (prefix incoming/)
     ↓ OBJECT_FINALIZE
Cloud Storage notification configuration
     ↓
Pub/Sub topic: product-image-events
     ├── Subscription A: thumbnail-worker
     │       ↓ Cloud Run/GKE Java worker
     │       ↓ thumbnails/ + trạng thái DB
     │
     └── Subscription B: security-scanner
             ↓ Quét file và phân loại kết quả
     ↓
Catalog API chỉ công bố ảnh đã qua xử lý/kiểm tra
~~~

Mỗi event mang `bucketId`, `objectId` và `objectGeneration`. Worker A chỉ nhận `incoming/` và xử lý theo generation; Worker B kiểm tra tính an toàn của file. Hai consumer dùng **hai subscription khác nhau**, vì mỗi bên cần xử lý cùng một upload độc lập.

### Khi upload lại cùng tên

Seller upload `incoming/item-42.jpg` generation `100`, sau đó upload bản mới generation `101`. Do không có bảo đảm thứ tự, worker có thể xử lý `101` trước `100`.

Thiết kế an toàn:

- Thumbnail ghi theo key chứa generation, ví dụ `thumbnails/item-42/101.jpg`.
- DB catalog lưu generation được phép công bố và dùng điều kiện update: chỉ tăng lên generation mới, không cho event cũ hạ generation.
- Nếu source generation đã bị xóa, log `STALE` thay vì xử lý bytes phiên bản khác dưới tên cũ.
- Nếu một worker xử lý xong nhưng chưa ack, lần retry nhìn thấy output và processing registry để kết thúc idempotently.
- Nếu scanner chưa xong, catalog vẫn giữ trạng thái `PENDING_REVIEW` thay vì mặc định ảnh mới đã an toàn.

**Ranh giới trách nhiệm:** Pub/Sub notifications giúp điều phối xử lý theo sự kiện; chúng không tự thực hiện image resizing, virus scanning, xác thực người upload, cấp quyền Cloud Storage, CDN cache invalidation hay đồng bộ transaction với Cloud SQL. Các phần đó phải được thiết kế thành ứng dụng và quy trình riêng.

## 17. Checklist trước khi triển khai production

- [ ] Đã xác định event nghiệp vụ cần là finalize, metadata update, archive hay permanent delete.
- [ ] Đã phân biệt Pub/Sub notifications với Eventarc direct CloudEvents.
- [ ] Bucket, topic, subscription, project/location và IAM có owner rõ ràng.
- [ ] Cloud Storage **service agent của bucket project** có Publisher ở topic đích.
- [ ] Worker có Subscriber ở subscription và Object Viewer đúng phạm vi dữ liệu.
- [ ] Có filters event types/prefix, tránh cấu hình trùng hoặc vượt giới hạn bucket.
- [ ] Tạo subscription trước khi bắn event thử, không giả định notification có replay quá khứ.
- [ ] Consumer sử dụng business idempotency key có generation/metageneration phù hợp.
- [ ] Đọc object theo đúng generation khi nghiệp vụ yêu cầu.
- [ ] Ack sau durable commit; có backoff, retry, DLQ và xử lý lỗi vĩnh viễn.
- [ ] Đã kiểm tra out-of-order event, duplicate delivery và overwrite cùng object name.
- [ ] Đã xử lý Object Versioning/Soft delete/retention theo đúng ngữ nghĩa.
- [ ] Có reconciliation để khắc phục trường hợp thiếu event hoặc pipeline ngừng lâu.
- [ ] Có log/metric/alert cho backlog, oldest unacked age, DLQ và processing SLO.
- [ ] Payload và object name không làm lộ dữ liệu nhạy cảm qua logs/subscriptions.
- [ ] Đã dự toán Cloud Storage, Pub/Sub, Eventarc/Cloud Run, Logging và downstream cost.
- [ ] Có quy trình rollback: sửa config, chuyển topic, tạm dừng consumer và khôi phục sau sự cố.

**Bài tập thực hành:** Một nhóm xây dịch vụ phân tích PDF: người dùng upload vào `gs://training-pdfs/incoming/`, Java worker trích xuất text và lưu kết quả vào Cloud SQL. Một số người dùng upload lại file cùng tên, có object versioning và mỗi ngày có vài nghìn tệp.

1. Vẽ kiến trúc Bucket → notification configuration → Pub/Sub topic → Java pull subscriber → Cloud SQL.
2. Chọn event type, prefix filter và payload format phù hợp; giải thích lựa chọn.
3. Viết các lệnh tạo topic/subscription, cấp IAM cho Cloud Storage service agent, tạo và liệt kê notification.
4. Mô tả cấu trúc event `OBJECT_FINALIZE` và cách lấy đúng generation khi xử lý.
5. Thiết kế unique key/idempotency và database transaction để hai bản event trùng không tạo hai dòng kết quả.
6. Giải thích thứ tự event có thể đảo khi version `101` được upload trước khi worker xử lý `100`.
7. Xử lý trường hợp PDF hỏng, quota Cloud SQL tạm hết, worker crash trước ACK và subscription backlog tăng.
8. So sánh dùng Eventarc Cloud Run trigger thay vì Pub/Sub pull trong use case này.
9. Đề xuất monitoring, DLQ, reconciliation, bảo mật metadata và phương án kiểm soát chi phí.

## Tài liệu tham khảo chính thức

- [Pub/Sub notifications for Cloud Storage](https://cloud.google.com/storage/docs/pubsub-notifications) — định nghĩa event, attributes, payload và delivery guarantees.
- [Configure Pub/Sub notifications](https://cloud.google.com/storage/docs/reporting-changes) — yêu cầu IAM và cách tạo/list/delete notification configurations.
- [gcloud storage buckets notifications create](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/create) — event filters, prefix, payload và topic flags.
- [gcloud storage buckets notifications delete](https://cloud.google.com/sdk/gcloud/reference/storage/buckets/notifications/delete) — xóa một configuration hoặc toàn bộ cấu hình theo target.
- [Get the Cloud Storage service agent](https://cloud.google.com/storage/docs/getting-service-agent) — xác định identity publisher chính xác.
- [Cloud Storage Object Versioning](https://cloud.google.com/storage/docs/object-versioning) — generation và archive của phiên bản cũ.
- [Cloud Storage soft delete](https://cloud.google.com/storage/docs/soft-delete) — vòng đời object và khả năng phục hồi.
- [Cloud Storage preconditions](https://cloud.google.com/storage/docs/request-preconditions) — ifGenerationMatch/ifMetagenerationMatch và cập nhật an toàn.
- [Pub/Sub subscribe best practices](https://cloud.google.com/pubsub/docs/subscribe-best-practices) — ack, retries, flow control và duplicate handling.
- [Pub/Sub exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery) — phạm vi exactly-once và giới hạn pull.
- [Route Cloud Storage events to Cloud Run with Eventarc](https://cloud.google.com/eventarc/standard/docs/run/route-trigger-cloud-storage) — CloudEvents, filters, IAM và location.
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing) — message delivery và lưu trữ.
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing) — object operations, storage class và dữ liệu.
