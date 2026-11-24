# Đối chiếu CloudEvents, loại sự kiện và thế hệ runtime được hỗ trợ

> **Chương:** Serverless  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Phạm vi:** Chuẩn hóa envelope sự kiện bằng CloudEvents, phân biệt loại event với phiên bản schema payload, đối chiếu định dạng sự kiện của AWS, Azure và Google Cloud, đồng thời chọn thế hệ runtime Java phù hợp khi triển khai cùng một logic Spring Cloud Function.  
> **Mốc thông tin runtime:** 24/11/2026. Các bảng hỗ trợ runtime có thể thay đổi theo hệ điều hành, hosting plan, region và lịch deprecation của từng nhà cung cấp.

## 1. Vì sao cần một chuẩn chung cho event?

Trong hệ thống hướng sự kiện, một nghiệp vụ có thể được phát ra từ nhiều nguồn: file được tạo trong object storage, message được publish vào broker, bản ghi database thay đổi hoặc một dịch vụ hoàn tất công việc. Mỗi nhà cung cấp thường có envelope riêng để mô tả event.

Ví dụ, một event tạo file có thể xuất hiện dưới các dạng:

- Azure Event Grid dùng trường `eventType`, `eventTime`, `topic` và `dataVersion` trong Event Grid schema; khi chọn CloudEvents, các trường được biểu diễn theo envelope CloudEvents.
- Google Eventarc gửi CloudEvents qua HTTP; các thuộc tính như `ce-id`, `ce-source` và `ce-type` nằm trong HTTP headers ở binary mode.
- AWS EventBridge dùng `detail-type`, `source`, `id` và `detail` trong event envelope của EventBridge. Có thể cấu hình transformer để chuyển event sang CloudEvents trước khi gửi đến API destination.

Nếu business function đọc trực tiếp envelope của từng nền tảng, code sẽ gắn với provider. Khi chuyển trigger hoặc thêm một nguồn event, phần mapping và kiểm thử phải thay đổi theo.

**CloudEvents chuẩn hóa metadata và cách đóng gói event. Nó không chuẩn hóa toàn bộ payload nghiệp vụ, không thay thế broker và cũng không quyết định delivery semantics.**

Trong Spring Cloud Function, mục tiêu là giữ bean nghiệp vụ ở dạng `Supplier`, `Function` hoặc `Consumer`. Lớp adapter nhận envelope của provider, chuyển event về dạng ứng dụng hiểu được, rồi gọi function qua `FunctionCatalog`. Khi đổi nền tảng, adapter có thể thay đổi trong khi logic nghiệp vụ vẫn giữ nguyên.

## 2. CloudEvents là gì và không phải là gì?

CloudEvents là một đặc tả mở thuộc Cloud Native Computing Foundation, định nghĩa một cách nhất quán để mô tả event metadata. Đặc tả tách hai phần:

1. **Context attributes:** mô tả event là gì, đến từ đâu, được định danh ra sao và liên quan tới subject nào.
2. **Event data:** payload chứa thông tin nghiệp vụ hoặc dữ liệu của lần xảy ra sự kiện.

Ví dụ một đơn hàng được tạo:

~~~json
{
  "specversion": "1.0",
  "id": "evt-2026-00042",
  "source": "urn:acme:commerce:orders",
  "type": "com.acme.order.created.v1",
  "subject": "orders/ORD-42",
  "time": "2026-11-24T09:15:00Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.acme.example/orders/order-created-v1.json",
  "data": {
    "orderId": "ORD-42",
    "customerId": "CUS-18",
    "total": 1250000,
    "currency": "VND"
  }
}
~~~

Envelope này có thể được gửi qua HTTP, broker hoặc event router. Consumer có thể đọc metadata mà chưa cần hiểu toàn bộ payload.

CloudEvents **không** quy định:

- Broker phải lưu event trong bao lâu.
- Event có được giao đúng một lần hay nhiều lần.
- Event có được xử lý theo thứ tự hay không.
- Consumer phải retry bao nhiêu lần.
- Cách xác thực producer và phân quyền consumer.
- Schema nghiệp vụ cụ thể bên trong `data`.
- Cách một provider ánh xạ mọi event nội bộ sang CloudEvents.

Vì vậy, một CloudEvent hợp lệ vẫn có thể được giao nhiều lần, đến trễ hoặc chứa payload mà consumer chưa hỗ trợ. Các chính sách retry, idempotency, ordering, security và schema compatibility vẫn cần thiết kế riêng.

## 3. Bốn thuộc tính bắt buộc của CloudEvents

Mọi CloudEvent phải có bốn context attributes sau:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `id` | Định danh event trong phạm vi producer. | `evt-2026-00042` |
| `source` | URI-reference xác định context nơi event xảy ra. | `urn:acme:commerce:orders` |
| `specversion` | Phiên bản đặc tả CloudEvents dùng để diễn giải context. | `1.0` |
| `type` | Loại event mô tả sự kiện đã xảy ra. | `com.acme.order.created.v1` |

### 3.1. `id` và `source` phải được xét cùng nhau

Producer phải đảm bảo tổ hợp `source` + `id` là duy nhất cho mỗi event khác nhau. Nếu cùng event được gửi lại do lỗi mạng, producer có thể giữ nguyên ID.

Ví dụ:

- Event đầu tiên: `source=urn:acme:orders`, `id=evt-42`.
- Bản giao lại: cùng `source` và `id`.
- Event mới cho đơn hàng khác: phải có ID khác.

Consumer có thể dùng cặp `source` + `id` làm khóa deduplication. Không nên chỉ dùng `id` nếu nhiều producer có thể phát ra ID trùng nhau.

`id` định danh một lần xảy ra sự kiện; `subject` định danh đối tượng được nói tới trong context của source. Hai thuộc tính này không thay thế nhau.

### 3.2. `source` là context, không phải URL để tải payload

`source` thường là URI tuyệt đối hoặc URI-reference do producer định nghĩa. Nó có thể là URI, URN hoặc một đường dẫn có ý nghĩa trong hệ thống.

Ví dụ:

- `urn:acme:commerce:orders`
- `https://events.acme.example/inventory`
- `//storage.googleapis.com/projects/_/buckets/orders-archive`

Consumer không nên mặc định gửi HTTP GET tới giá trị `source`. Đây là định danh context của event, không phải endpoint được bảo đảm có thể truy cập.

### 3.3. `specversion` không phải phiên bản Java hoặc payload

Với CloudEvents 1.0, giá trị `specversion` là `1.0`. Nó cho biết consumer phải diễn giải envelope theo phiên bản đặc tả nào.

Không đổi `specversion` thành `21` khi chạy Java 21 hoặc `25` khi chạy Java 25. Phiên bản JDK, phiên bản runtime provider và phiên bản CloudEvents là ba khái niệm độc lập.

### 3.4. `type` là hợp đồng phân loại event

`type` mô tả loại sự kiện liên quan đến occurrence. Producer định nghĩa tên này; consumer có thể dùng nó để routing, filtering, authorization policy, metrics hoặc chọn decoder.

Một quy ước có thể dùng namespace ngược DNS và suffix version:

- `com.acme.order.created.v1`
- `com.acme.order.cancelled.v1`
- `com.acme.inventory.reserved.v2`

Đây là quy ước thiết kế ứng dụng, không phải format tên bắt buộc của CloudEvents. Điều quan trọng là type phải ổn định, không mơ hồ và có hợp đồng payload đi kèm.

## 4. Thuộc tính tùy chọn và extension attributes

CloudEvents định nghĩa các thuộc tính tùy chọn thường gặp:

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| `subject` | Đối tượng được nhắc đến trong context của source. | `orders/ORD-42` |
| `time` | Thời điểm occurrence xảy ra, theo RFC 3339. | `2026-11-24T09:15:00Z` |
| `datacontenttype` | Media type của event data. | `application/json` |
| `dataschema` | URI nhận diện schema mà data tuân theo. | `https://schemas.acme.example/order-v1.json` |

Không phải event nào cũng cần tất cả các thuộc tính tùy chọn. Tuy nhiên, nếu consumer cần lọc theo subject, kiểm tra thời gian hoặc giải mã payload theo schema, producer nên phát các thuộc tính tương ứng một cách nhất quán.

### 4.1. Extension attributes

CloudEvents cho phép thêm thuộc tính mở rộng để mang metadata mà core specification chưa định nghĩa. Ví dụ:

~~~json
{
  "specversion": "1.0",
  "id": "evt-42",
  "source": "urn:acme:orders",
  "type": "com.acme.order.created.v1",
  "tenantid": "tenant-7",
  "traceid": "trace-abc",
  "region": "ap-southeast-1",
  "data": {
    "orderId": "ORD-42"
  }
}
~~~

Tên extension phải tuân theo quy tắc đặt tên của CloudEvents. Hãy dùng tên chữ thường, ngắn, có ý nghĩa và tránh xung đột với core attributes.

Extension là metadata cấp event. Không dùng extension để nhét toàn bộ business payload, token xác thực hoặc dữ liệu cá nhân. Các trung gian có thể đọc, route hoặc ghi log context attributes.

### 4.2. Không biến extension thành schema riêng của từng team

Nếu mỗi team tự đặt các trường như `tenant`, `tenant_id`, `tenantId` và `org` cho cùng một ý nghĩa, khả năng tương tác sẽ giảm.

Hãy thống nhất:

- Tên extension.
- Kiểu dữ liệu.
- Phạm vi giá trị.
- Producer nào chịu trách nhiệm phát.
- Consumer nào được phép sử dụng.
- Quy tắc giữ hoặc bỏ extension khi chuyển tiếp event.

Extension không được hiểu bởi consumer vẫn cần được xử lý an toàn. Nếu không cần dùng, consumer có thể bỏ qua; nếu làm proxy/intermediary, nên giữ các extension không bị thay đổi khi có thể.

## 5. Phân biệt event type, spec version và data schema version

Đây là ba khái niệm dễ bị nhầm:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| CloudEvents `specversion` | Envelope tuân theo phiên bản đặc tả nào? | `1.0` |
| CloudEvents `type` | Sự kiện nghiệp vụ nào đã xảy ra? | `com.acme.order.created.v1` |
| `dataschema` hoặc quy ước schema của ứng dụng | Payload data tuân theo cấu trúc nào? | `order-created-v1.json` |

`specversion` thường giữ nguyên `1.0` trong khi ứng dụng phát hành nhiều loại event và nhiều phiên bản payload.

### 5.1. Khi nào tăng version trong event type?

Nếu thay đổi làm consumer hiểu khác ý nghĩa occurrence, có thể tạo type mới, ví dụ:

- `com.acme.order.created.v1`
- `com.acme.order.created.v2`

Đây là quyết định của hợp đồng producer/consumer. Không phải mọi thay đổi payload đều bắt buộc tạo type mới.

### 5.2. Khi nào thay đổi `dataschema`?

Nếu type vẫn diễn tả cùng một occurrence nhưng cấu trúc payload thay đổi theo schema được quản lý riêng, producer có thể cập nhật `dataschema` theo chính sách versioning của hệ thống.

Consumer cần biết cách hỗ trợ nhiều schema version, hoặc từ chối/quarantine schema chưa hỗ trợ. Không chỉ dựa vào việc parse JSON thành công: JSON có thể parse được nhưng ý nghĩa field đã thay đổi.

### 5.3. Quy tắc tiến hóa payload

Một chiến lược an toàn thường gồm:

1. Ưu tiên thêm field tùy chọn thay vì đổi nghĩa field hiện tại.
2. Consumer bỏ qua field không biết nếu hợp đồng cho phép.
3. Không đổi kiểu dữ liệu của field đang được consumer sử dụng mà không có kế hoạch migration.
4. Dùng schema registry hoặc tài liệu schema có version khi nhiều producer/consumer cần phối hợp.
5. Có contract test cho từng phiên bản được hỗ trợ.
6. Giữ khả năng quan sát event type và schema version trong log/metrics.

CloudEvents cung cấp vị trí để nhận diện schema; nó không tự kiểm tra tính tương thích của schema nghiệp vụ.

## 6. Các chế độ truyền CloudEvents

Đặc tả CloudEvents HTTP protocol binding định nghĩa các content modes. Hai mode quan trọng nhất trong tích hợp HTTP là **structured** và **binary**. Batch mode chỉ dùng khi cả format và binding liên quan hỗ trợ.

### 6.1. Structured mode

Structured mode đặt toàn bộ event envelope, gồm context attributes và data, trong một body duy nhất.

HTTP request ví dụ:

~~~http
POST /events HTTP/1.1
Content-Type: application/cloudevents+json

{
  "specversion": "1.0",
  "id": "evt-42",
  "source": "urn:acme:orders",
  "type": "com.acme.order.created.v1",
  "datacontenttype": "application/json",
  "data": {
    "orderId": "ORD-42"
  }
}
~~~

Đặc điểm:

- Một JSON object chứa cả metadata và payload.
- `Content-Type` của envelope là `application/cloudevents+json`.
- Dễ lưu trữ, ghi fixture và gửi giữa các hệ thống qua HTTP.
- Consumer cần giải mã envelope trước khi đọc data.

Structured mode phù hợp khi muốn một representation hoàn chỉnh của event để lưu, replay hoặc chuyển qua API destination.

### 6.2. Binary mode

Binary mode đặt context attributes trong HTTP headers, còn event data nằm trong request body.

Ví dụ:

~~~http
POST / HTTP/1.1
Content-Type: application/json
ce-specversion: 1.0
ce-id: evt-42
ce-source: urn:acme:orders
ce-type: com.acme.order.created.v1
ce-subject: orders/ORD-42

{
  "orderId": "ORD-42"
}
~~~

Đặc điểm:

- Các context attributes được ánh xạ thành HTTP headers có prefix `ce-`.
- Body chứa riêng event data.
- `Content-Type` mô tả media type của data, ví dụ `application/json`.
- Adapter có thể chuyển headers thành Spring Message headers và body thành payload.

**Binary mode không có nghĩa payload bắt buộc là byte array nhị phân.** Payload có thể là JSON, text hoặc binary; tên mode nói về cách tách metadata khỏi data.

### 6.3. Batch mode

Batch mode đóng gói nhiều CloudEvents trong một message. Các event trong batch vẫn độc lập và không nhất thiết cùng source hoặc type. Các event trong cùng batch phải dùng cùng `specversion`.

Không phải mọi event format hoặc protocol binding đều hỗ trợ batch. Không tự giả định một mảng JSON tùy ý là CloudEvents batch hợp lệ. Hãy xác minh đúng format và binding của transport đang dùng.

### 6.4. So sánh content mode

| Tiêu chí | Structured | Binary | Batch |
| --- | --- | --- | --- |
| Metadata | Nằm trong body envelope. | Nằm trong HTTP headers. | Nằm trong từng event trong batch format. |
| Payload | Nằm trong field `data` hoặc `data_base64`. | Nằm trực tiếp trong body. | Mỗi event có data riêng. |
| Content-Type | `application/cloudevents+json` với JSON format. | Media type của event data. | Theo batch event format. |
| Phù hợp | API, lưu trữ, replay, API destination. | HTTP event receiver, Eventarc. | Tối ưu giao nhiều event khi binding hỗ trợ. |
| Rủi ro | Cần decode envelope. | Header có thể bị proxy lọc hoặc chuẩn hóa. | Một event lỗi có thể ảnh hưởng cách xử lý batch. |

## 7. Đối chiếu envelope sự kiện của AWS, Azure và Google Cloud

Các nền tảng không phát cùng một envelope cho mọi dịch vụ. Cần xác định cả **provider event format** và **CloudEvents binding** mà trigger đang sử dụng.

### 7.1. AWS EventBridge và Lambda

EventBridge event mặc định có envelope riêng, thường gồm:

~~~json
{
  "version": "0",
  "id": "event-id-42",
  "detail-type": "Object Created",
  "source": "aws.s3",
  "account": "123456789012",
  "time": "2026-11-24T09:15:00Z",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:s3:::orders-archive"
  ],
  "detail": {
    "bucket": {
      "name": "orders-archive"
    },
    "object": {
      "key": "ORD-42.json"
    }
  }
}
~~~

Các điểm cần nhớ:

- `version` của EventBridge envelope không phải CloudEvents `specversion`.
- `detail-type` là trường phân loại event của EventBridge; nó không tự động là CloudEvents `type`.
- `detail` là payload chi tiết do nguồn event định nghĩa.
- EventBridge có thể dùng input transformer để chuyển event sang structured CloudEvents trước khi gửi tới API destination.
- Nếu muốn các consumer dùng CloudEvents, cần định nghĩa mapping rõ ràng và gửi đúng content type `application/cloudevents+json`.

Ví dụ mapping ở tầng ứng dụng:

| EventBridge | CloudEvents | Ghi chú |
| --- | --- | --- |
| `id` | `id` | Có thể giữ ID nguồn nếu bảo đảm duy nhất cùng source. |
| `source` | `source` | Cần quyết định URI-reference ổn định của producer. |
| `detail-type` | `type` | Chuyển thành tên type có namespace theo hợp đồng ứng dụng. |
| `time` | `time` | Giữ timestamp nếu hợp lệ RFC 3339. |
| `detail` | `data` | Payload chi tiết của event. |
| `region`, `account` | Extension attributes | Chỉ thêm nếu consumer cần metadata này. |
| `version` | Không map thẳng sang `specversion` | Đây là version của EventBridge envelope. |

AWS Lambda có thể nhận event từ nhiều nguồn như EventBridge, SQS, S3 và API Gateway. Event source mapping hoặc integration có thể đưa cho handler các kiểu payload khác nhau. Không giả định mọi event gửi đến Lambda đã là CloudEvents.

Nếu hệ thống dùng Spring Cloud Function, hãy đặt bước chuyển EventBridge/SQS envelope sang event model của ứng dụng trong adapter. Bean nghiệp vụ không nên phụ thuộc tên field `detail-type` hoặc cấu trúc `Records[]` của một provider.

### 7.2. Azure Event Grid

Azure Event Grid hỗ trợ hai schema thường gặp:

1. **Event Grid schema:** định dạng riêng của Azure với các trường như `eventType`, `eventTime`, `topic`, `dataVersion`, `metadataVersion`, `id` và `data`.
2. **CloudEvents schema:** JSON implementation của CloudEvents v1.0, hỗ trợ HTTP protocol binding.

Ví dụ CloudEvent Blob Created:

~~~json
{
  "specversion": "1.0",
  "type": "Microsoft.Storage.BlobCreated",
  "source": "/subscriptions/sub-1/resourceGroups/rg-demo/providers/Microsoft.Storage/storageAccounts/acmefiles",
  "id": "9aeb0fdf-c01e-0131-0922-9eb54906e209",
  "time": "2026-11-24T09:15:00Z",
  "subject": "blobServices/default/containers/orders/blobs/ORD-42.json",
  "data": {
    "api": "PutBlockList",
    "contentType": "application/json",
    "contentLength": 812,
    "url": "https://acmefiles.blob.core.windows.net/orders/ORD-42.json"
  }
}
~~~

Điểm khác nhau khi đối chiếu Event Grid schema và CloudEvents:

| Event Grid schema | CloudEvents | Ý nghĩa |
| --- | --- | --- |
| `id` | `id` | Định danh event. |
| `topic` | `source` | Context của nguồn phát event; cần giữ đúng semantics. |
| `eventType` | `type` | Loại occurrence. |
| `eventTime` | `time` | Thời điểm event. |
| `subject` | `subject` | Đối tượng trong context của source. |
| `data` | `data` | Payload nghiệp vụ. |
| `dataVersion` | `dataschema` hoặc quy ước type/extension | Không map tự động nếu chưa thống nhất hợp đồng. |
| `metadataVersion` | `specversion`? | Không map thẳng. `metadataVersion` là metadata version của Event Grid schema; `specversion` là phiên bản đặc tả CloudEvents. |

Event Grid hỗ trợ CloudEvents schema làm input/output schema và hỗ trợ chuyển Event Grid schema sang CloudEvents schema trong event subscription. Event Grid schema không biểu diễn đầy đủ extension attributes của CloudEvents, vì vậy không thể coi hai schema là hai JSON object chỉ đổi tên field.

Khi dùng Azure Functions, cần xác định trigger và extension cụ thể. Ví dụ tài liệu Event Grid có thể nhận CloudEvent trong trigger binding của một số programming model. Với Java, hãy kiểm tra loại parameter và version của Java Event Grid extension được hỗ trợ trong project; nếu dùng HTTP trigger, adapter có thể nhận CloudEvents theo HTTP binding rồi chuyển sang Spring Message.

### 7.3. Google Eventarc và Cloud Run functions

Eventarc gửi event tới target qua HTTP dưới dạng CloudEvents 1.0 **binary mode**. Các context attributes được ánh xạ thành headers:

| HTTP header | CloudEvents attribute |
| --- | --- |
| `ce-id` | `id` |
| `ce-source` | `source` |
| `ce-specversion` | `specversion` |
| `ce-type` | `type` |
| `ce-time` | `time` (nếu có) |
| `ce-subject` | `subject` (nếu có) |

Ví dụ Pub/Sub event:

~~~http
POST / HTTP/1.1
Content-Type: application/json; charset=utf-8
ce-specversion: 1.0
ce-id: 2070443601311540
ce-source: //pubsub.googleapis.com/projects/demo/topics/orders
ce-type: google.cloud.pubsub.topic.v1.messagePublished
ce-time: 2026-11-24T09:15:00Z

{
  "message": {
    "data": "eyJvcmRlcklkIjoiT1JELTQyIn0=",
    "messageId": "2070443601311540",
    "publishTime": "2026-11-24T09:15:00Z",
    "attributes": {
      "producer": "checkout"
    }
  },
  "subscription": "projects/demo/subscriptions/orders-worker"
}
~~~

Trong ví dụ này, body là data message theo schema của Pub/Sub event type. Field `message.data` là Base64; consumer cần decode payload đó theo hợp đồng ứng dụng. CloudEvents không tự decode Base64 của payload lồng bên trong.

Một số event type thường gặp:

| Nguồn | CloudEvents `type` | Data message |
| --- | --- | --- |
| Pub/Sub | `google.cloud.pubsub.topic.v1.messagePublished` | `MessagePublishedData` |
| Cloud Storage | `google.cloud.storage.object.v1.finalized` | `StorageObjectData` |
| Cloud Storage | `google.cloud.storage.object.v1.deleted` | `StorageObjectData` |
| Firestore | `google.cloud.firestore.document.v1.created` hoặc các type tương ứng | `DocumentEventData` |
| Cloud Audit Logs | `google.cloud.audit.log.v1.written` | `LogEntryData` |

Tên event type và data schema phải được lấy từ danh sách event types của Eventarc, không tự đoán từ tên dịch vụ. Một số event type dùng cùng một data message, nhưng envelope type vẫn phân biệt occurrence.

### 7.4. Bảng tổng hợp provider

| Tiêu chí | AWS EventBridge | Azure Event Grid | Google Eventarc |
| --- | --- | --- | --- |
| Envelope mặc định | EventBridge event schema. | Event Grid schema hoặc CloudEvents nếu cấu hình. | CloudEvents 1.0. |
| CloudEvents native trên đường HTTP | Có thể transform sang structured CloudEvents trước khi gửi API destination. | Hỗ trợ CloudEvents JSON v1.0 và HTTP binding. | Gửi CloudEvents qua HTTP binary mode. |
| Trường type nguồn | `detail-type` | `eventType` hoặc CloudEvents `type` | `ce-type` |
| Payload nguồn | `detail` | `data` | HTTP body; phụ thuộc event type. |
| Cần mapping adapter? | Có nếu nguồn là EventBridge schema. | Có nếu dùng Event Grid schema; ít hơn khi cấu hình CloudEvents. | Vẫn cần decode data và chuyển sang model ứng dụng. |
| Điều phải kiểm tra | Event source, target input transformer, Lambda event type. | Input/output schema, trigger extension, dataVersion. | Event type, source, binary headers, data schema và Base64 lồng. |

## 8. Event type không phải tên function

Một event có type `com.acme.order.created.v1` có thể được xử lý bởi function tên `processOrderCreated`, `auditOrder` hoặc `notifyWarehouse`. Hai khái niệm có mục đích khác nhau:

- Event type mô tả occurrence của event.
- Function name là tên bean hoặc function definition trong ứng dụng.
- Routing policy quyết định event type nào được gửi tới function nào.

Ví dụ mapping:

| CloudEvents `type` | Spring Cloud Function bean |
| --- | --- |
| `com.acme.order.created.v1` | `processOrderCreated` |
| `com.acme.order.cancelled.v1` | `processOrderCancelled` |
| `com.acme.inventory.reserved.v1` | `processInventoryReserved` |

Không nên dùng trực tiếp tên type từ producer làm tên bean rồi cho phép mọi event chọn function tùy ý. Hãy dùng allowlist mapping để tránh event không tin cậy điều khiển routing nội bộ.

Một function router có thể chọn function theo `ce-type`, nhưng phải xác thực event và kiểm tra type được hỗ trợ trước khi lookup.

## 9. Runtime generation và Java version là hai trục độc lập

Khi triển khai serverless, cần phân biệt:

1. **Runtime generation/host:** thế hệ môi trường thực thi do nhà cung cấp quản lý.
2. **Java runtime version:** phiên bản JDK mà function chạy trên đó.
3. **Operating system/base image:** ví dụ Amazon Linux 2, Amazon Linux 2023, Google buildpack stack hoặc managed Linux image của Azure.
4. **Framework version:** Spring Boot, Spring Cloud Function, Spring Integration và thư viện CloudEvents.
5. **Event format version:** CloudEvents `specversion` hoặc schema nghiệp vụ của event.

Các trục này có quan hệ tương thích, nhưng không thể thay thế nhau. Chọn Java 25 không có nghĩa ứng dụng tự chuyển sang generation mới; nâng Azure Functions host lên v4 không tự đổi CloudEvents specversion.

## 10. Ma trận runtime Java theo nhà cung cấp tại 24/11/2026

### 10.1. AWS Lambda

AWS dùng runtime identifier và hệ điều hành nền để xác định môi trường thực thi Java.

| Java | Runtime identifier | Hệ điều hành | Trạng thái cần chú ý |
| --- | --- | --- | --- |
| Java 25 | `java25` | Amazon Linux 2023 | Runtime hiện hành. |
| Java 21 | `java21` | Amazon Linux 2023 | Runtime hiện hành. |
| Java 17 | `java17.al2023` | Amazon Linux 2023 | Có lựa chọn AL2023. |
| Java 11 | `java11.al2023` | Amazon Linux 2023 | Có lựa chọn AL2023. |
| Java 8 | `java8.al2023` | Amazon Linux 2023 | Có lựa chọn AL2023. |
| Java 17 | `java17` | Amazon Linux 2 | Legacy; lịch deprecation khác AL2023. |
| Java 11 | `java11` | Amazon Linux 2 | Legacy; lịch deprecation khác AL2023. |
| Java 8 | `java8.al2` | Amazon Linux 2 | Legacy; lịch deprecation khác AL2023. |

Tài liệu runtime AWS hiện công bố lịch deprecation cho các runtime Java AL2023 là 30/06/2029; các runtime Java AL2 có lịch 30/06/2027. Ngày block create/update có thể khác ngày deprecation, vì vậy phải xem đủ các cột trong runtime lifecycle khi lập kế hoạch nâng cấp.

Lưu ý:

- `java17` và `java17.al2023` là hai runtime identifier khác nhau.
- Java 25 và Java 21 chạy trên Amazon Linux 2023.
- Với container image, đội phát triển tự quản lý base image, JDK và bản vá; không áp lịch managed runtime một cách máy móc.
- Event source của Lambda vẫn quyết định payload event mà handler nhận; JDK version không biến envelope thành CloudEvents.

### 10.2. Azure Functions

Tại mốc tham khảo, Azure Functions chỉ hỗ trợ **Functions host runtime 4.x**. Runtime host 2.x và 3.x đã hết hỗ trợ; ứng dụng cũ cần migration.

Các phiên bản Java được tài liệu Azure liệt kê ở mức GA:

| Java | Support level | Supported until |
| --- | --- | --- |
| Java 25 | GA | May 2029 |
| Java 21 | GA | September 2028 |
| Java 17 | GA | September 2027 |
| Java 11 | GA | September 2027 |
| Java 8 | GA | September 2027 |

Có một ràng buộc hosting plan quan trọng: **Java 21 là phiên bản Java mới nhất được hỗ trợ trên Linux Consumption plan**. Java mới hơn không được bổ sung vào plan này; nếu cần Java 25, phải chọn hosting plan có hỗ trợ.

Ngoài ra:

- Functions host version được cấu hình qua setting như `FUNCTIONS_EXTENSION_VERSION`.
- Java version trong `pom.xml` phải khớp Java runtime trên function app.
- Trigger/binding extension có vòng đời và yêu cầu version riêng.
- Java programming model dùng method có annotation `@FunctionName`; trigger và binding quyết định cách event được đưa vào method.
- Event Grid CloudEvents schema không tự đảm bảo mọi Java trigger extension có cùng kiểu parameter. Kiểm tra Java binding/extension hoặc nhận HTTP CloudEvents trực tiếp.

Không nhầm Functions host v4.x với Java 21 hoặc CloudEvents 1.0. Đây là ba version độc lập.

### 10.3. Google Cloud Run functions

Google hiện dùng tên **Cloud Run functions** cho thế hệ runtime chạy trên nền Cloud Run. Tài liệu runtime phân biệt `1st gen` và `Run functions`.

| Java | Runtime generation | Runtime ID | Base image stack | Deprecation |
| --- | --- | --- | --- | --- |
| Java 25 | Run functions | `java25` | `google-24` / `google-24-full` | October 2031 |
| Java 21 | Run functions | `java21` | `google-22` / `google-22-full` | September 2031 |
| Java 17 | 1st gen và Run functions | `java17` | `google-22` / `google-22-full` | October 2027 |
| Java 11 | 1st gen và Run functions (đã decommission) | `java11` | `google-18-full` | Decommissioned October 31, 2025 |

Điểm cần lưu ý:

- Java 25 và Java 21 nằm trong Run functions generation.
- Java 17 còn được liệt kê cho cả 1st gen và Run functions.
- Java 11 đã đến ngày decommission; không chọn cho workload mới.
- Base image stack cũng là một phần của runtime. `google-24` và `google-22` không phải Java version.
- Eventarc gửi CloudEvents 1.0 qua HTTP binary mode; generation của function không làm thay đổi envelope CloudEvents.

### 10.4. So sánh runtime generation

| Nhà cung cấp | Khái niệm generation/host | Lựa chọn Java mới hiện hành | Ghi chú migration |
| --- | --- | --- | --- |
| AWS Lambda | Managed runtime ID + OS generation AL2/AL2023 | Java 25, Java 21 trên AL2023 | Ưu tiên AL2023; phân biệt runtime identifier cũ và mới. |
| Azure Functions | Functions host 4.x | Java 25, Java 21, Java 17, Java 11, Java 8 theo plan | Host 2.x/3.x retired; Linux Consumption giới hạn Java 21. |
| Google Cloud Run functions | 1st gen và Run functions | Java 25, Java 21 trên Run functions; Java 17 trên cả hai | Chuyển workload mới sang Run functions; Java 11 đã decommission. |

**Khuyến nghị chọn baseline dùng chung:** Java 21 là lựa chọn thực tế nếu cùng một artifact cần chạy trên cả ba nhà cung cấp và phải tương thích với Azure Linux Consumption plan. Nếu không bị ràng buộc plan cũ, có thể đánh giá Java 25 trên AWS, Azure và Google theo framework, dependency và build pipeline.

Bảng trên là ảnh chụp trạng thái tài liệu tại 24/11/2026, không phải cam kết rằng mọi region, hosting plan hoặc custom container đều có cùng lịch hỗ trợ. Trước khi triển khai, kiểm tra runtime lifecycle và region/plan cụ thể.

## 11. Runtime tương thích không đồng nghĩa framework tương thích

Một function chạy được trên Java 21 chưa chắc chạy được với mọi version Spring Boot hoặc Spring Cloud Function.

Trước khi chọn runtime, kiểm tra đồng thời:

- Java version mà Spring Boot release hỗ trợ.
- Spring Cloud release train tương thích với Spring Boot.
- Version Spring Cloud Function và adapter tương ứng.
- Version Spring Integration nếu dùng CloudEvents transformer.
- Version CloudEvents Java SDK hoặc Event Format implementation.
- Provider handler contract, reflection/AOT requirement và startup behavior.
- Native image hoặc container base image nếu triển khai theo hướng đó.

Không chỉ nâng `java.version` trong Maven rồi kết luận migration hoàn tất. Phải build, test và deploy thử trên đúng runtime generation.

Một module nghiệp vụ dùng Spring Cloud Function có thể giữ code function tương đối ổn định, nhưng entrypoint, request wrapper, dependency và deployment descriptor thường khác nhau theo AWS Lambda, Azure Functions và Cloud Run functions.

## 12. Đưa CloudEvents vào Spring Cloud Function

### 12.1. `FunctionCatalog` không tự giải mã mọi CloudEvent

`FunctionCatalog` đăng ký và cung cấp wrapper cho các functional beans, hỗ trợ lookup, composition và type conversion. Nó không phải CloudEvents HTTP binding parser.

Một request CloudEvents cần đi qua các bước:

1. Nhận HTTP request hoặc provider envelope.
2. Kiểm tra content mode và CloudEvents context attributes.
3. Parse envelope hoặc map `ce-*` headers.
4. Giải mã event data theo `datacontenttype` và schema ứng dụng.
5. Tạo Spring `Message<?>` với payload nghiệp vụ và metadata cần thiết.
6. Gọi function qua `FunctionCatalog`.

Đừng gửi nguyên JSON CloudEvents vào bean nghiệp vụ rồi giả định Spring tự bỏ envelope và tìm payload bên trong `data`. Việc đó chỉ xảy ra nếu adapter/converter được cấu hình để thực hiện.

### 12.2. Spring Integration hỗ trợ CloudEvents

Spring Integration cung cấp module `spring-integration-cloudevents` và hai transformer chính:

- `FromCloudEventTransformer`: chuyển CloudEvent thành Spring Integration Message; payload trở thành event data, context attributes và extensions được ánh xạ thành headers có prefix `ce-`.
- `ToCloudEventTransformer`: chuyển Spring Message thành CloudEvent; có thể cấu hình EventFormat để serialize envelope.

Transformer hỗ trợ CloudEvents specification v1.0. Với serialized CloudEvent, transformer dùng `content-type` để tìm EventFormat. Nếu không tìm được format và không cấu hình fallback, quá trình transform sẽ thất bại.

Dependency Maven minh họa:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-cloudevents</artifactId>
    <version>7.1.1</version>
</dependency>
~~~

Chọn version Spring Integration tương thích với Spring Boot/Spring Framework đang dùng. Không suy ra rằng Spring Cloud Function BOM luôn quản lý version của module CloudEvents này.

### 12.3. Đọc structured CloudEvent

Ví dụ sau minh họa việc chuyển serialized JSON CloudEvent thành Spring Message. Đây là bước adapter, trước khi gọi business function:

~~~java
Message<byte[]> rawMessage = MessageBuilder
        .withPayload(cloudEventJsonBytes)
        .setHeader(MessageHeaders.CONTENT_TYPE, "application/cloudevents+json")
        .build();

FromCloudEventTransformer transformer =
        new FromCloudEventTransformer();

Message<?> decoded = transformer.transform(rawMessage);

byte[] eventData = (byte[]) decoded.getPayload();
OrderCreated order = objectMapper.readValue(
        eventData, OrderCreated.class);

Message<OrderCreated> businessMessage = MessageBuilder
        .withPayload(order)
        .copyHeaders(decoded.getHeaders())
        .build();
~~~

Trong ví dụ này:

- `cloudEventJsonBytes` là toàn bộ structured envelope.
- `FromCloudEventTransformer` giải mã envelope CloudEvents.
- `eventData` là phần data của event.
- `businessMessage` chứa payload kiểu `OrderCreated` cùng các metadata headers.

Đoạn code giả định data được serialize dưới dạng JSON byte array. Nếu data là Protobuf hoặc một media type khác, cần EventFormat và decoder phù hợp.

### 12.4. Đọc binary CloudEvent

Với binary mode như Eventarc, HTTP adapter nhận metadata từ request headers và payload từ body. Có thể tạo Spring Message sau khi validate:

~~~java
Message<OrderCreated> eventMessage = MessageBuilder
        .withPayload(orderCreated)
        .setHeader("ce-id", eventId)
        .setHeader("ce-source", eventSource)
        .setHeader("ce-specversion", specVersion)
        .setHeader("ce-type", eventType)
        .setHeader("ce-subject", subject)
        .setHeader("ce-time", eventTime)
        .build();
~~~

Ở đây `orderCreated` đã được deserialize từ body theo `Content-Type` của event. Hãy kiểm tra bốn thuộc tính bắt buộc trước khi gọi function:

~~~java
if (eventId == null || eventId.isBlank()
        || eventSource == null || eventSource.isBlank()
        || !"1.0".equals(specVersion)
        || eventType == null || eventType.isBlank()) {
    throw new IllegalArgumentException("CloudEvent context không hợp lệ");
}
~~~

Trong production, nên dùng CloudEvents SDK hoặc một HTTP binding implementation đã được kiểm thử để xử lý URI, timestamp, extension và serialization. Ví dụ trên chỉ minh họa việc chuyển header đã nhận thành Spring Message.

### 12.5. Gọi function bằng FunctionCatalog

Giả sử ứng dụng có bean nghiệp vụ:

~~~java
@Bean
public Function<Message<OrderCreated>, OrderAccepted> processOrder() {
    return message -> {
        String eventId = (String) message.getHeaders().get("ce-id");
        String eventType = (String) message.getHeaders().get("ce-type");

        if (!"com.acme.order.created.v1".equals(eventType)) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        OrderCreated order = message.getPayload();
        return new OrderAccepted(order.orderId(), eventId);
    };
}
~~~

Adapter có thể lookup và gọi function:

~~~java
Function<Message<OrderCreated>, OrderAccepted> function =
        functionCatalog.lookup("processOrder");

OrderAccepted result = function.apply(eventMessage);
~~~

Qua `FunctionCatalog`, Spring Cloud Function có thể áp dụng wrapper và type conversion. Business function nhận Spring Message nên có thể đọc event metadata mà không phụ thuộc trực tiếp vào AWS EventBridge, Azure Event Grid hoặc Eventarc envelope.

### 12.6. Chỉ giữ metadata thật sự cần thiết

Không cần chuyển mọi CloudEvents header thành domain object. Nên phân loại:

- Event identity: `ce-id`, `ce-source`.
- Event contract: `ce-type`, `ce-specversion`, `ce-dataschema`.
- Trace/correlation: extension đã thống nhất như `ce-traceid`.
- Business payload: `data`.

Tránh để function nghiệp vụ phụ thuộc vào header HTTP thuần như `Content-Length` hoặc `User-Agent`. Chỉ chuyển những metadata thuộc hợp đồng ứng dụng.

## 13. Routing theo event type một cách an toàn

Một event router có thể dùng `ce-type` để chọn function. Tuy nhiên, routing phải có allowlist và contract rõ ràng.

Ví dụ:

~~~java
Map<String, String> routes = Map.of(
        "com.acme.order.created.v1", "processOrderCreated",
        "com.acme.order.cancelled.v1", "processOrderCancelled",
        "com.acme.inventory.reserved.v1", "processInventoryReserved"
);

String functionName = routes.get(eventType);

if (functionName == null) {
    throw new UnsupportedEventTypeException(eventType);
}

Function<Message<?>, ?> function = functionCatalog.lookup(functionName);
Object result = function.apply(eventMessage);
~~~

Đây là pseudo-code routing; kiểu payload thực tế của từng function phải được kiểm soát. Không cast mọi function về cùng một generic type nếu input/output của chúng khác nhau.

Các nguyên tắc cần áp dụng:

1. Xác thực producer và quyền gửi event trước routing.
2. Kiểm tra `specversion` được hỗ trợ.
3. Kiểm tra `type` nằm trong allowlist.
4. Kiểm tra `dataschema` hoặc payload version phù hợp.
5. Từ chối hoặc quarantine event không hỗ trợ theo policy.
6. Ghi log event identity và type, không log payload nhạy cảm.

Không cho producer bên ngoài gửi tên bean tùy ý qua header rồi dùng trực tiếp làm function definition. Event type là dữ liệu đầu vào; nó không được trở thành lệnh gọi function không giới hạn.

## 14. Kiểm thử CloudEvents contract

Một bộ test tốt cần kiểm tra cả envelope, transport và business function.

### 14.1. Kiểm tra envelope

- Thiếu `id`, `source`, `specversion` hoặc `type` phải bị từ chối.
- `source` + `id` trùng phải được nhận diện là duplicate theo idempotency policy.
- `specversion` không hỗ trợ phải được xử lý rõ ràng.
- `time` sai định dạng RFC 3339 phải bị reject hoặc quarantine.
- Extension lạ không làm parser crash nếu consumer không cần dùng.
- `data` và `data_base64` không được cùng xuất hiện trong JSON event format.

### 14.2. Kiểm tra structured và binary

Tạo fixture cho hai representation cùng một event:

- Structured: envelope trong body, content type `application/cloudevents+json`.
- Binary: context attributes trong `ce-*` headers, data trong body.

Hai fixture phải tạo ra cùng business message sau bước adapter. Như vậy, function nghiệp vụ không cần biết event đến theo content mode nào.

### 14.3. Kiểm tra type và schema version

- Event type được hỗ trợ phải route tới đúng function.
- Event type không biết phải được reject/quarantine theo policy.
- Payload schema version cũ phải được parse theo decoder tương ứng nếu còn hỗ trợ.
- Payload schema version mới không được âm thầm parse thành object cũ rồi làm sai nghiệp vụ.
- Kiểm tra extension attributes có được giữ khi chuyển tiếp event hay không.

### 14.4. Kiểm tra runtime/provider

| Lớp test | Mục tiêu |
| --- | --- |
| Unit test | Validate context attributes, type, data schema. |
| Transformer test | Structured envelope được chuyển thành Spring Message. |
| HTTP contract test | Binary headers và body được map chính xác. |
| FunctionCatalog test | Message payload được đưa tới đúng functional bean. |
| Provider integration | AWS, Azure, Eventarc gửi đúng envelope theo trigger cấu hình. |
| Runtime integration | Ứng dụng khởi động và xử lý event trên Java/host generation mục tiêu. |
| Migration test | So sánh event fixtures trước/sau khi nâng JDK hoặc runtime. |

Đừng chỉ test trên máy local với Java 21 rồi deploy lên Java 25 hoặc runtime generation khác mà không có smoke test. Runtime base image, classpath, TLS provider, reflection, native library và startup time có thể khác.

## 15. Lỗi thường gặp khi tích hợp CloudEvents

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi `specversion` là version payload | Consumer từ chối hoặc diễn giải sai event. | Dùng `dataschema` hoặc versioning convention cho payload. |
| Dùng `id` mà bỏ qua `source` | Có thể deduplicate nhầm event của producer khác. | Dùng cặp `source` + `id`. |
| Coi `source` là URL có thể gọi | Consumer thực hiện request không hợp lệ. | Dùng source như định danh context. |
| Coi `type` là tên function | Producer có thể điều khiển routing tùy ý. | Dùng allowlist type-to-function mapping. |
| Nhầm EventBridge `version` với CloudEvents `specversion` | Envelope mapping sai. | Tạo mapping rõ ràng ở transformer. |
| Nhầm Event Grid `dataVersion` với `specversion` | Schema payload bị hiểu sai. | Quản lý data schema riêng. |
| Parse Eventarc body mà bỏ ce-* headers | Mất event identity, source và type. | Chuyển headers thành Spring Message headers. |
| Coi Pub/Sub `message.data` đã là JSON | Decoder nhận Base64 thay vì payload gốc. | Decode Base64 theo Pub/Sub contract. |
| Cho rằng FunctionCatalog tự parse CloudEvents | Business function nhận nguyên envelope. | Thêm CloudEvents adapter/transformer trước catalog. |
| Dùng Java mới mà không kiểm tra plan/runtime | Deployment thất bại hoặc runtime không hỗ trợ. | Đối chiếu runtime ID, host generation, OS và plan. |
| Nâng Spring Boot nhưng giữ integration module cũ | Lỗi dependency/classpath. | Kiểm tra compatibility matrix và chạy integration test. |
| Log toàn bộ event envelope | Có thể lộ PII hoặc metadata nhạy cảm. | Chỉ log identity/type/correlation và field đã được phép. |

## 16. Bài tập tình huống

### Bài 1 — Nhận diện ba loại version

Một CloudEvent có:

~~~json
{
  "specversion": "1.0",
  "type": "com.acme.invoice.issued.v2",
  "dataschema": "https://schemas.acme.example/invoice/v2.json",
  "id": "evt-99",
  "source": "urn:acme:billing",
  "data": {
    "invoiceId": "INV-99"
  }
}
~~~

Hãy giải thích:

1. `specversion` biểu thị version nào?
2. `type` mô tả occurrence gì?
3. `dataschema` dùng để làm gì?
4. Nếu đổi JDK từ 21 lên 25, thuộc tính nào trong event phải thay đổi?

**Gợi ý:** `specversion` là version CloudEvents; `type` là event contract; `dataschema` nhận diện payload schema. JDK version không yêu cầu đổi CloudEvents envelope.

### Bài 2 — EventBridge chuyển sang CloudEvents

Một event từ EventBridge có `detail-type=Object Created`, `source=aws.s3` và payload trong `detail`.

1. Những trường nào có thể dùng để tạo CloudEvents?
2. Vì sao không map EventBridge `version` sang `specversion`?
3. Ai chịu trách nhiệm định nghĩa CloudEvents `type`?
4. Content-Type nào phải đặt khi gửi structured JSON CloudEvent?

### Bài 3 — Azure Event Grid

Một ứng dụng dùng Event Grid schema với `eventType` và `dataVersion`. Consumer muốn nhận CloudEvents.

1. Cần cấu hình input/output schema ra sao?
2. `eventType` được map sang thuộc tính nào?
3. `dataVersion` có phải `specversion` không?
4. Vì sao CloudEvents input không thể luôn được chuyển ngược thành Event Grid output schema mà không mất thông tin extension?

### Bài 4 — Google Eventarc binary mode

Một HTTP request chứa `ce-id`, `ce-source`, `ce-specversion`, `ce-type` và body JSON.

1. Vì sao body không chứa toàn bộ CloudEvents envelope?
2. Adapter phải tạo Spring Message như thế nào?
3. Khi event type là Pub/Sub messagePublished, tại sao có thể cần Base64 decode thêm?
4. Event type không hỗ trợ nên được xử lý thế nào?

### Bài 5 — Chọn runtime cho cùng một ứng dụng Java

Một nhóm muốn deploy ứng dụng Spring Cloud Function lên AWS Lambda, Azure Functions và Google Cloud Run functions.

1. Runtime Java 25 nào đang có trên từng nền tảng?
2. Vì sao Azure Linux Consumption plan không phải lựa chọn cho Java 25?
3. Java 17 trên Google Cloud Run functions có thể thuộc những generation nào?
4. AWS Java 17 AL2 và Java 17 AL2023 khác nhau ở đâu?
5. Nếu muốn một baseline dùng chung cho ba provider, vì sao Java 21 là lựa chọn đáng cân nhắc?

### Bài 6 — Thiết kế adapter

Hãy xây dựng adapter nhận structured CloudEvent và gọi `processOrder` qua `FunctionCatalog`:

1. Kiểm tra bốn thuộc tính bắt buộc.
2. Decode `data` thành `OrderCreated`.
3. Giữ `ce-id`, `ce-source`, `ce-type` trong Spring Message headers.
4. Gọi function.
5. Viết test cho duplicate event và unsupported type.

### Bài 7 — Nâng cấp runtime nhưng giữ event contract

Một ứng dụng chuyển từ Java 17 sang Java 21 và từ Azure Functions runtime 3.x lên 4.x. Producer vẫn phát CloudEvents 1.0.

Hãy xác định:

- Phần nào của event envelope không cần thay đổi?
- Những dependency và trigger extension nào cần kiểm tra?
- Vì sao cần chạy contract test và runtime integration test?
- Cách rollout để có thể rollback nếu adapter hoặc serialization behavior thay đổi?

## 17. Checklist triển khai

| Hạng mục | Cần xác nhận |
| --- | --- |
| CloudEvents core | Đúng `specversion` và bốn required attributes. |
| Event identity | `source` + `id` duy nhất trong scope producer. |
| Event type | Namespace, naming convention, versioning và allowlist. |
| Payload schema | `datacontenttype`, `dataschema` và schema evolution. |
| Content mode | Structured, binary hoặc batch theo binding hỗ trợ. |
| Provider envelope | EventBridge, Event Grid hoặc Eventarc mapping rõ ràng. |
| Spring adapter | Parse envelope/headers trước khi gọi FunctionCatalog. |
| Metadata propagation | Giữ identity/type/trace cần thiết; không giữ header không liên quan. |
| Security | Xác thực producer; không tin source/type chỉ vì có trong header. |
| Runtime generation | AWS runtime ID/OS, Azure host/plan, Google generation/base image. |
| Java/framework compatibility | JDK, Boot, Spring Cloud Function, Spring Integration, CloudEvents SDK. |
| Tests | Envelope, payload, duplicate, routing, provider và runtime integration. |
| Operations | Log event identity, type, schema version và runtime version; có DLQ/quarantine. |

## 18. Tài liệu chính thức

1. CloudEvents Specification — Core attributes, event identity, extensions và examples: https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
2. CloudEvents HTTP Protocol Binding — Structured, binary và batch content modes: https://github.com/cloudevents/spec/blob/main/cloudevents/bindings/http-protocol-binding.md
3. CloudEvents JSON Event Format: https://github.com/cloudevents/spec/blob/main/cloudevents/formats/json-format.md
4. CloudEvents Java SDK: https://github.com/cloudevents/sdk-java
5. Spring Cloud Function — Programming Model và FunctionCatalog: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
6. Spring Integration — CloudEvents Support, FromCloudEventTransformer và ToCloudEventTransformer: https://docs.spring.io/spring-integration/reference/cloudevents.html
7. AWS Lambda — Java runtimes: https://docs.aws.amazon.com/lambda/latest/dg/lambda-java.html
8. AWS Lambda — Runtime lifecycle: https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html
9. Amazon EventBridge — Sending CloudEvents to API destinations: https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-api-destinations-cloudevents.html
10. Azure Functions — Compare runtime versions: https://learn.microsoft.com/en-us/azure/azure-functions/functions-versions
11. Azure Functions — Supported languages and Java versions: https://learn.microsoft.com/en-us/azure/azure-functions/supported-languages?pivots=programming-language-java
12. Azure Functions — Java developer reference: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference-java
13. Azure Event Grid — CloudEvents v1.0 schema: https://learn.microsoft.com/en-us/azure/event-grid/cloud-event-schema
14. Google Cloud Run functions — Runtime support: https://docs.cloud.google.com/functions/docs/runtime-support
15. Google Eventarc — CloudEvents HTTP protocol binding: https://docs.cloud.google.com/eventarc/docs/cloudevents
16. Google Eventarc — Event format and CloudEvents payload examples: https://docs.cloud.google.com/eventarc/docs/event-format
