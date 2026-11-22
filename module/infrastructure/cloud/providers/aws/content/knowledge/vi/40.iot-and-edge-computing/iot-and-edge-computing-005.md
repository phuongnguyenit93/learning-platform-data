# IoT Rules Engine và định tuyến telemetry

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, AWS IoT Core cung cấp MQTT message broker để thiết bị và ứng dụng gửi telemetry, nhận lệnh và trao đổi trạng thái. Khi message đi vào broker, AWS IoT Rules Engine có thể lọc, biến đổi payload bằng cú pháp SQL đơn giản rồi định tuyến dữ liệu tới các dịch vụ AWS như Amazon S3, Kinesis Data Streams, Amazon Data Firehose, DynamoDB, Lambda, Amazon Timestream, AWS IoT SiteWise, SNS, SQS hoặc OpenSearch.

Rules Engine giúp tách thiết bị khỏi chi tiết của hệ thống backend. Thiết bị chỉ cần publish theo một topic contract ổn định; rule có thể quyết định dữ liệu nào được lưu, dữ liệu nào cần phân tích, dữ liệu nào cần cảnh báo và dữ liệu nào phải chuyển tới hệ thống khác. Tuy nhiên, định tuyến telemetry vẫn cần thiết kế topic, schema, IAM role, retry, error action và idempotency rõ ràng. Một rule không phải transaction phân tán bao trùm mọi action.

Sau bài học, người học có thể:

- Mô tả luồng message từ thiết bị qua MQTT broker, Rules Engine và rule actions.
- Thiết kế topic namespace cho tenant, site, device và loại telemetry.
- Phân biệt MQTT topic name với topic filter; dùng đúng wildcard `+` và `#`.
- Viết AWS IoT SQL với SET, SELECT, FROM, WHERE và các hàm như `topic()` hoặc `timestamp()`.
- Trích xuất trường từ payload và topic, lọc dữ liệu, tạo output document.
- Chọn rule action phù hợp cho S3, Kinesis, Firehose, DynamoDB, Lambda, Timestream, IoT SiteWise, SQS và SNS.
- Dùng substitution templates để tạo partition key, object key hoặc destination topic.
- Phân biệt MQTT QoS với kết quả thực thi action và thiết kế chống duplicate.
- Cấu hình Basic Ingest để giảm chi phí messaging khi không cần pub/sub broker.
- Thiết kế error action, IAM role và IoT policy theo least privilege.
- Giám sát Rules Engine bằng CloudWatch metrics/logs và kiểm thử pipeline telemetry đầu cuối.

## 1. Rules Engine trong kiến trúc AWS IoT Core

AWS IoT Rules Engine nhận message từ MQTT broker hoặc Basic Ingest, so khớp topic filter, thực thi SQL statement và gửi kết quả tới một hoặc nhiều action. SQL có thể chọn trường, đổi tên, tính giá trị mới và lọc message theo điều kiện.

Luồng cơ bản:

~~~mermaid
flowchart LR
    D[IoT devices and gateways] -->|MQTT publish| B[AWS IoT Core message broker]
    B --> R[Rules Engine]
    R --> F[Topic filter and IoT SQL]
    F --> A1[Kinesis Data Streams]
    F --> A2[Amazon S3 or Data Firehose]
    F --> A3[DynamoDB or Timestream]
    F --> A4[Lambda or IoT SiteWise]
    F --> E[Error action]
    A1 --> C[Stream consumers and analytics]
    A2 --> L[Data lake]
    A3 --> Q[Applications and dashboards]
    A4 --> W[Business workflows]
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| MQTT publisher | Thiết bị/gateway publish message lên một topic cụ thể |
| Message broker | Xác thực, phân phối message tới subscriber và chuyển message phù hợp cho Rules Engine |
| Topic filter | Xác định nhóm topic mà rule theo dõi |
| AWS IoT SQL | Chọn, lọc và biến đổi payload |
| Rule action | Gửi kết quả tới một AWS service hoặc endpoint được hỗ trợ |
| Error action | Nhận thông tin khi một hoặc nhiều rule action thất bại |
| IAM role | Cho Rules Engine quyền truy cập target resource |
| CloudWatch | Lưu log, metrics và tín hiệu vận hành |

Một rule có thể có nhiều actions. Ví dụ, cùng một telemetry message có thể được ghi vào Kinesis để xử lý real-time và lưu vào S3 để phân tích lịch sử. Các action chạy độc lập theo cấu hình của rule; không có transaction ACID bao trùm tất cả target.

Rules Engine xử lý message và định tuyến dữ liệu. Nó không thay thế một hệ thống stream processing phức tạp hoặc workflow dài hạn. Khi cần logic tùy chỉnh, gọi API ngoài, tính toán nặng hoặc nhiều bước có trạng thái, hãy chuyển message tới Lambda, Step Functions, Kinesis consumers hoặc một pipeline chuyên biệt.

## 2. Thiết kế MQTT topic namespace

Topic là hợp đồng định tuyến giữa thiết bị, Rules Engine và các MQTT subscriber. Topic nên thể hiện phạm vi sở hữu và loại message, đồng thời giữ cấu trúc ổn định khi fleet tăng lên.

Một cấu trúc tham khảo:

~~~text
org/{tenantId}/site/{siteId}/device/{deviceId}/telemetry
org/{tenantId}/site/{siteId}/device/{deviceId}/status
org/{tenantId}/site/{siteId}/device/{deviceId}/alert
org/{tenantId}/site/{siteId}/device/{deviceId}/command
org/{tenantId}/site/{siteId}/device/{deviceId}/command/accepted
org/{tenantId}/site/{siteId}/device/{deviceId}/command/rejected
~~~

Ví dụ topic thực tế:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
org/acme/site/hcmc-01/device/pump-042/status
org/acme/site/hcmc-01/device/pump-042/alert
~~~

Các nguyên tắc:

- Dùng một thứ tự segment thống nhất để rule có thể trích xuất tenant, site và device.
- Tách telemetry, status, alert và command thành các nhánh riêng để subscriber có thể lọc đúng loại message.
- Không đưa mật khẩu, token, email hoặc dữ liệu cá nhân vào topic.
- Giữ tên topic ổn định; thay đổi cấu trúc cần có kế hoạch tương thích cho firmware và rule.
- Dùng chữ thường và quy tắc đặt tên nhất quán; MQTT topic phân biệt chữ hoa/chữ thường.
- Đặt tenant/site/device trong topic khi cần routing hoặc authorization theo phạm vi.
- Không tạo một topic duy nhất cho mọi loại dữ liệu nếu các consumer cần xử lý khác nhau.

MQTT publisher gửi một topic name cụ thể, không dùng wildcard khi publish. Wildcard chỉ xuất hiện trong topic filter của subscriber hoặc Rules Engine.

## 3. Topic filter và wildcard

Trong AWS IoT SQL, `FROM` nhận một topic filter đặt trong dấu nháy đơn. Rule được kích hoạt với từng message có topic khớp filter.

Hai wildcard MQTT:

| Wildcard | Ý nghĩa | Ví dụ |
|---|---|---|
| `+` | Khớp đúng một segment của topic | `factory/+/telemetry` |
| `#` | Khớp các segment ở cấp hiện tại và bên dưới | `factory/#` |

Quy tắc:

- `+` phải chiếm toàn bộ một segment, không ghép với ký tự khác trong segment.
- `#` phải là segment cuối cùng và chiếm toàn bộ segment đó.
- Có thể kết hợp `+` và `#` trong cùng filter.
- `factory/+/telemetry` khớp `factory/line-1/telemetry`, nhưng không khớp `factory/line-1/zone-a/telemetry`.
- `factory/#` khớp các topic bắt đầu bằng `factory/`; filter này không khớp topic cha `factory` không có dấu `/` phía sau.

Ví dụ rule theo dõi telemetry của mọi thiết bị trong tenant acme:

~~~sql
SELECT *
FROM 'org/acme/site/+/device/+/telemetry'
~~~

Rule chỉ khớp các topic có đúng cấu trúc segment trên. Nếu dùng `#` quá rộng, một rule có thể nhận lượng message lớn hơn dự kiến, làm tăng số lần đánh giá, tải của target và chi phí. Hãy giới hạn filter theo tenant, loại message và phạm vi thiết bị cần xử lý.

### 3.1. Wildcard trong MQTT khác wildcard trong IoT policy

Đây là điểm dễ gây lỗi bảo mật:

- MQTT topic filter dùng `+` và `#`.
- AWS IoT Core policies dùng wildcard IAM `*` và `?`.
- Trong policy document, `+` và `#` chỉ là ký tự thông thường, không có ý nghĩa wildcard.

Ví dụ policy resource có thể dùng `*` để cho phép publish tới một nhóm topic. Hãy giới hạn wildcard trong policy theo tenant/device; không sao chép nguyên topic filter `org/acme/+/telemetry` vào policy rồi kỳ vọng `+` hoạt động.

Trong IoT policy, `iot:Publish` và `iot:Receive` dùng resource loại `topic`; `iot:Subscribe` dùng resource loại `topicfilter`. Cấp quyền subscribe không tự cấp quyền receive message.

## 4. Cấu trúc AWS IoT SQL

AWS IoT SQL là cú pháp kiểu SQL được tối giản cho message payload. Các mệnh đề chính:

| Mệnh đề | Vai trò |
|---|---|
| SET | Khai báo biến có thể dùng lại trong SQL và substitution templates |
| SELECT | Chọn trường, hàm và biểu thức để tạo output payload |
| FROM | Topic filter xác định message nào kích hoạt rule |
| WHERE | Điều kiện quyết định message có được chuyển tới actions hay không |

Ví dụ:

~~~sql
SELECT temperature AS tempC, humidity
FROM 'factory/+/telemetry'
WHERE temperature > 50
~~~

Nếu message có payload:

~~~json
{
  "temperature": 72.5,
  "humidity": 61,
  "unit": "C"
}
~~~

Output được gửi tới action:

~~~json
{
  "tempC": 72.5,
  "humidity": 61
}
~~~

Một số điểm cần nhớ:

- `SELECT *` giữ lại các trường trong payload đầu vào.
- `AS` đổi tên trường trong output.
- `WHERE` lọc message; nếu điều kiện không đúng, action không được kích hoạt.
- SQL comments không được hỗ trợ; không chèn `-- comment` vào statement.
- Field name có dấu cách không thể được tham chiếu trực tiếp như identifier trong SQL; nếu dùng `*`, trường đó vẫn có thể được chuyển qua output.
- Nên khai báo `awsIotSqlVersion` rõ ràng. Console hiện đặt mặc định `2016-03-23`; nếu CLI hoặc CloudFormation không truyền version, mặc định có thể là `2015-10-08`.

Với rule chỉ được gọi bằng Basic Ingest, `FROM` có thể được bỏ qua. Với rule nhận message qua MQTT broker thông thường, `FROM` là bắt buộc.

## 5. Trích xuất dữ liệu từ topic và tạo metadata

Topic thường chứa thông tin routing như tenant, site và device. Payload chứa dữ liệu đo, timestamp và sequence. Hàm `topic(n)` trích xuất segment theo vị trí bắt đầu từ 1; `topic()` trả về toàn bộ topic.

Giả sử thiết bị publish:

~~~text
org/acme/site-hcmc/device/pump-042/telemetry
~~~

Các kết quả:

| Biểu thức | Giá trị |
|---|---|
| `topic(1)` | `org` |
| `topic(2)` | `acme` |
| `topic(3)` | `site-hcmc` |
| `topic(4)` | `device` |
| `topic(5)` | `pump-042` |
| `topic(6)` | `telemetry` |

Hàm `timestamp()` trả về thời gian hiện tại theo millisecond Unix epoch do Rules Engine quan sát. Hàm `traceid()` trả về trace ID của MQTT message nếu có.

Ví dụ telemetry:

~~~json
{
  "eventId": "evt-01J8QK9M4X",
  "sequence": 18231,
  "observedAt": "2026-11-20T06:30:00Z",
  "temperature": 72.5,
  "humidity": 61,
  "pressureKpa": 101.3,
  "batteryPct": 87
}
~~~

Rule SQL:

Trong topic filter, `+` phải chiếm toàn bộ segment. Vì vậy, filter `org/+/site-+/device/+/telemetry` không hợp lệ: wildcard không thể ghép với tiền tố `site-`. Với namespace không có segment `site` cố định, filter đúng để chấp nhận mọi site là:

~~~sql
SELECT
  *,
  topic(2) AS tenantId,
  topic(3) AS siteId,
  topic(5) AS deviceId,
  timestamp() AS receivedAt,
  traceid() AS mqttTraceId
FROM 'org/+/+/device/+/telemetry'
WHERE temperature >= -40
  AND temperature <= 125
  AND humidity >= 0
  AND humidity <= 100
~~~

Khi topic namespace có thêm segment cố định `site`, nên dùng:

~~~sql
SELECT
  *,
  topic(2) AS tenantId,
  topic(4) AS siteId,
  topic(6) AS deviceId,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= -40
  AND temperature <= 125
  AND humidity >= 0
  AND humidity <= 100
~~~

Chỉ số `topic(n)` phải khớp đúng cấu trúc topic. Khi thêm hoặc bỏ segment, hãy cập nhật SQL, substitution templates, IoT policies và test cases cùng lúc.

## 6. Lọc và biến đổi telemetry

Rules Engine có thể lọc message theo giá trị đo, trạng thái thiết bị, loại event hoặc version schema. Lọc sớm giúp tránh ghi dữ liệu lỗi hoặc gửi những message không cần thiết tới downstream.

Ví dụ chỉ định tuyến cảnh báo nhiệt độ cao:

~~~sql
SELECT
  topic(6) AS deviceId,
  temperature,
  observedAt,
  eventId,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= 80
~~~

Ví dụ chuyển trạng thái số sang nhãn:

~~~sql
SELECT
  deviceId,
  CASE
    WHEN batteryPct < 15 THEN 'LOW'
    WHEN batteryPct < 40 THEN 'MEDIUM'
    ELSE 'NORMAL'
  END AS batteryState,
  batteryPct,
  observedAt
FROM 'factory/+/device/+/telemetry'
WHERE batteryPct >= 0 AND batteryPct <= 100
~~~

Ví dụ dùng `SET` để tạo biến tái sử dụng:

~~~sql
SET threshold = 80
SELECT
  topic(3) AS siteId,
  topic(5) AS deviceId,
  temperature,
  timestamp() AS receivedAt
FROM 'org/+/site/+/device/+/telemetry'
WHERE temperature >= threshold
~~~

Hãy validate schema trước khi dùng field trong WHERE. Nếu payload thiếu field hoặc gửi kiểu dữ liệu khác dự kiến, điều kiện có thể không đánh giá như mong muốn. Với payload JSON phức tạp, có thể dùng nested object expressions hoặc external functions được AWS IoT SQL hỗ trợ; kiểm tra giới hạn của SQL version và từng function.

Rules Engine phù hợp với filtering, projection, enrichment đơn giản và routing. Logic cần join nhiều nguồn, xử lý state dài hạn hoặc thuật toán phức tạp nên chuyển sang Lambda, Amazon Managed Service for Apache Flink, Step Functions hoặc service xử lý chuyên biệt.

## 7. Substitution templates trong rule actions

Substitution template cho phép action parameter thay đổi theo từng message. Cú pháp:

~~~text
${expression}
~~~

Expression có thể đọc field trong payload, gọi hàm SQL, dùng toán tử được hỗ trợ hoặc tham chiếu biến đã khai báo trong mệnh đề SET. Ví dụ:

- `${topic(5)}` lấy device ID từ topic.
- `${timestamp()}` tạo timestamp hiện tại.
- `${eventId}` lấy event ID từ payload.
- `${replace(topic(), '/', '-')}` biến topic thành chuỗi phù hợp cho tên object.

Một giới hạn quan trọng: substitution template được đánh giá độc lập với câu SELECT. Nó không thể tham chiếu alias được tạo bằng `AS`. Ví dụ nếu SQL tạo `topic(5) AS deviceId`, action không thể giả định `${deviceId}` sẽ đọc alias đó. Hãy dùng `${topic(5)}` hoặc trường `deviceId` vốn có trong payload.

Ví dụ S3 object key:

~~~text
telemetry/${topic(3)}/${topic(5)}/${timestamp()}-${newuuid()}.json
~~~

Nếu topic có cấu trúc `org/{tenant}/site/{site}/device/{device}/telemetry`, hãy chọn segment index chính xác cho tenant/site/device. Object key cần có thành phần duy nhất để tránh hai message ghi đè cùng một object.

## 8. Chọn rule action theo mục tiêu

AWS IoT Rules Engine hỗ trợ nhiều action tới dịch vụ AWS và một số endpoint ngoài:

| Action | Đích đến | Khi phù hợp |
|---|---|---|
| Kinesis Data Streams | Stream record | Xử lý real-time, nhiều consumer, partition theo device/site |
| Amazon Data Firehose | Delivery stream | Buffer và chuyển dữ liệu tới S3, Redshift, OpenSearch hoặc destination hỗ trợ |
| Amazon S3 | Object storage | Lưu raw telemetry, archive, data lake và replay |
| DynamoDB / DynamoDBv2 | NoSQL table | Trạng thái hiện tại, metadata hoặc event cần truy cập theo key |
| AWS Lambda | Function | Logic tùy chỉnh, enrichment hoặc gọi API |
| Amazon Timestream | Time-series database | Truy vấn chuỗi thời gian theo device, measure và timestamp |
| AWS IoT SiteWise | Asset properties | Telemetry công nghiệp theo asset model và hierarchy |
| Amazon SQS | Queue | Tách producer khỏi worker xử lý bất đồng bộ |
| Amazon SNS | Pub/sub notification | Fan-out thông báo tới nhiều subscriber |
| OpenSearch | Search endpoint | Tìm kiếm và phân tích log/telemetry |
| CloudWatch Logs/Metrics | Observability | Ghi log hoặc metric vận hành |
| Republish | MQTT topic khác | Chuẩn hóa hoặc chuyển tiếp message trong MQTT namespace |
| Step Functions | State machine | Khởi chạy workflow có nhiều bước |
| HTTP / Apache Kafka | Endpoint hoặc Kafka cluster | Tích hợp hệ thống bên ngoài khi phù hợp |

Các action có thể khác nhau theo Region và dịch vụ đích. Tài nguyên của service đích thường cần nằm cùng Region với rule để action kết nối đúng. Kiểm tra tài liệu action cụ thể về payload, IAM permissions, limits, batching và retry trước khi triển khai.

### 8.1. Kinesis Data Streams

Dùng Kinesis khi nhiều consumer cần đọc telemetry độc lập hoặc cần xử lý streaming. Chọn partition key dựa trên thứ tự nghiệp vụ, ví dụ device ID để các record cùng thiết bị được phân phối cùng shard theo partition key.

Ví dụ action:

~~~json
{
  "kinesis": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleKinesisRole",
    "streamName": "iot-telemetry",
    "partitionKey": "${topic(6)}"
  }
}
~~~

Với topic `org/acme/site/hcmc-01/device/pump-042/telemetry`, segment 6 là `pump-042`, nên biểu thức `${topic(6)}` dùng device ID làm partition key. Kinesis partition key ảnh hưởng tới shard distribution và ordering; một key quá nóng có thể gây hot shard.

### 8.2. Amazon Data Firehose

Dùng Data Firehose khi cần buffer và delivery dữ liệu tới destination được hỗ trợ mà không muốn tự vận hành consumer. Firehose có thể batch record và chuyển dữ liệu theo buffer size/time.

Ví dụ action:

~~~json
{
  "firehose": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleFirehoseRole",
    "deliveryStreamName": "iot-telemetry-delivery",
    "separator": "\n"
  }
}
~~~

Chọn format, compression, buffer hints, dynamic partitioning và error prefix ở cấu hình Firehose delivery stream. Rules Engine chỉ gửi record vào Firehose; schema conversion, buffering và delivery tới S3/Redshift/OpenSearch được cấu hình ở Firehose. Kiểm tra giới hạn record size và throughput của cả hai dịch vụ.

### 8.3. Amazon S3

Dùng S3 để lưu raw telemetry hoặc archive. Object key nên phân vùng theo tenant, site, device hoặc thời gian để query bằng Athena/Glue hiệu quả.

Ví dụ:

~~~json
{
  "s3": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleS3Role",
    "bucketName": "company-iot-raw",
    "key": "telemetry/${topic(2)}/${topic(4)}/${topic(6)}/${timestamp()}-${newuuid()}.json"
  }
}
~~~

Với topic `org/acme/site/hcmc-01/device/pump-042/telemetry`, `topic(2)` là `acme`, `topic(4)` là `hcmc-01`, `topic(6)` là `pump-042`. Key có timestamp và UUID để tránh ghi đè. Nếu cần file lớn hơn hoặc tối ưu small files, cân nhắc Firehose buffering thay vì tạo một object cho từng message.

### 8.4. DynamoDB và Timestream

DynamoDB phù hợp khi ứng dụng cần đọc trạng thái thiết bị hiện tại hoặc truy cập theo partition key. DynamoDBv2 action có thể ghi các field trong payload vào nhiều attribute của item; hãy thiết kế key schema và write capacity theo tốc độ telemetry. Tránh dùng một partition key chung cho toàn fleet.

Timestream phù hợp với time-series measurements. Chọn dimensions như tenant, site, device và measure names phù hợp với query pattern. Đảm bảo timestamp và data types nhất quán; không đưa mọi metadata thay đổi liên tục vào dimensions nếu điều đó tạo cardinality quá lớn.

### 8.5. Lambda, SQS và SNS

Lambda phù hợp khi cần logic tùy chỉnh, kiểm tra business rule, enrich dữ liệu hoặc gọi dịch vụ không có action trực tiếp. SQS phù hợp khi muốn worker xử lý độc lập, có visibility timeout và DLQ. SNS phù hợp khi một event cần phát tới nhiều subscriber.

Nếu Lambda thực hiện xử lý dài hoặc downstream có thể throttling, cân nhắc gửi vào SQS trước rồi để Lambda consumer đọc queue. Cách này tách tốc độ ingest telemetry khỏi tốc độ xử lý nghiệp vụ.

## 9. Một rule có nhiều action: fan-out telemetry

Một rule có thể gửi cùng output tới nhiều action. Ví dụ telemetry vừa vào Kinesis cho phân tích real-time, vừa vào S3 để lưu raw.

~~~mermaid
flowchart TD
    A[MQTT telemetry] --> B[IoT SQL filter and enrich]
    B --> C[Kinesis Data Streams]
    B --> D[S3 raw archive]
    B --> E[CloudWatch metric]
    C --> F[Anomaly detection consumer]
    C --> G[Operational dashboard consumer]
    D --> H[Glue and Athena analytics]
~~~

Fan-out trong một rule giúp giảm số lần thiết bị publish và giữ logic routing tập trung. Nhưng các action có thể thành công/thất bại độc lập. Ví dụ Kinesis nhận record nhưng S3 action thất bại. Error action có thể ghi nhận lỗi S3, nhưng không rollback record đã vào Kinesis.

Nếu các target phải cùng hoàn tất trước khi coi một nghiệp vụ thành công, hãy tạo workflow hoặc một consumer điều phối có state. Rules Engine không cung cấp distributed transaction giữa S3, DynamoDB và Kinesis.

## 10. Republish và tránh vòng lặp rule

Republish action gửi output sang một MQTT topic khác. Cách này hữu ích khi muốn chuẩn hóa topic hoặc tạo topic dành riêng cho consumer.

Ví dụ:

~~~json
{
  "republish": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleRepublishRole",
    "topic": "normalized/${topic(2)}/${topic(4)}/${topic(6)}",
    "qos": 1
  }
}
~~~

Hãy bảo đảm topic đích không khớp lại chính rule đang xử lý message, nếu không có thể tạo vòng lặp republish, tăng số rule executions và chi phí. AWS khuyến nghị tránh wildcard topic patterns trong republish rules vì có thể gây duplicate processing hoặc lặp routing.

Một cách tổ chức là tách namespace input và output:

~~~text
raw/...
normalized/...
alerts/...
commands/...
~~~

Rule chỉ nghe `raw/#`, sau đó republish tới `normalized/...`. Consumer đọc normalized topic; không tạo rule tổng quát `#` bắt lại toàn bộ output.

## 11. Basic Ingest: gửi thẳng tới Rules Engine

Basic Ingest cho phép thiết bị hoặc ứng dụng gửi dữ liệu trực tiếp tới một rule mà không đi qua publish/subscribe message broker. Cách này giảm chi phí messaging khi message chỉ cần được chuyển tới rule actions và không cần broker phân phối tới MQTT subscribers khác.

Topic Basic Ingest có prefix:

~~~text
$aws/rules/{ruleName}/{originalTopic}
~~~

Ví dụ rule tên `TelemetryRouter` vốn xử lý topic:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Thiết bị publish Basic Ingest tới:

~~~text
$aws/rules/TelemetryRouter/org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Các điểm cần nhớ:

- Device policy cần cho phép publish tới `$aws/rules/*` hoặc prefix của rule cụ thể.
- Ba segment prefix `$aws/rules/{ruleName}` không được tính vào giá trị mà hàm `topic()` trả về.
- Rule chỉ được kích hoạt bằng Basic Ingest có thể bỏ `FROM`; nếu cũng nhận message qua broker thì `FROM` vẫn cần thiết.
- Basic Ingest không cung cấp broker fan-out tới MQTT subscribers.
- QoS 1 PUBACK xác nhận message đã tới Rules Engine, không chứng minh rule actions đã hoàn tất.
- Rule action error handling vẫn hoạt động như với message đi qua broker.
- Basic Ingest loại bỏ messaging charge của broker path; chi phí rule evaluation, target service và các action vẫn cần tính riêng.

Dùng Basic Ingest cho telemetry chỉ cần đi vào cloud data pipeline. Giữ MQTT broker publish/subscribe khi gateway hoặc thiết bị khác cần nhận cùng message, ví dụ trạng thái, cảnh báo hoặc lệnh điều khiển.

## 12. MQTT QoS, retry và duplicate

AWS IoT Core hỗ trợ MQTT QoS 0 và QoS 1; không hỗ trợ QoS 2.

| QoS | Semantics | Khi phù hợp |
|---|---|---|
| QoS 0 | At most once; không có PUBACK xác nhận | Telemetry tần suất cao, mất một số sample có thể chấp nhận |
| QoS 1 | At least once; broker gửi PUBACK | Event quan trọng cần xác nhận ở tầng MQTT |

QoS là cam kết ở lớp MQTT giữa publisher và broker hoặc giữa broker và subscriber. Nó không phải cam kết exactly-once end-to-end cho toàn bộ rule actions và database writes.

Ví dụ, thiết bị publish QoS 1 và nhận PUBACK. Điều đó không đồng nghĩa record đã được ghi thành công vào mọi target như Kinesis, S3 hoặc DynamoDB. Basic Ingest documentation cũng nêu rõ PUBACK chỉ xác nhận message đã được chuyển tới Rules Engine, không xác nhận action đã hoàn tất.

Rules Engine có thể thử lại action khi gặp lỗi tạm thời. Nếu mọi lần thử đều thất bại, message bị loại bỏ và lỗi được ghi vào CloudWatch Logs; nếu cấu hình error action, thông tin thất bại được chuyển tới error destination. Producer retry, action retry hoặc consumer retry đều có thể dẫn tới duplicate.

Để xử lý an toàn:

- Gắn `eventId` ổn định do device/gateway tạo.
- Giữ `eventId` không đổi khi retry cùng một event.
- Gắn `deviceId`, `sequence` hoặc version để phát hiện duplicate/out-of-order.
- Dùng conditional write, unique key hoặc idempotency record ở consumer.
- Với Kinesis, chọn partition key theo entity cần ordering.
- Với S3, tạo object key duy nhất hoặc dùng batch/manifest để tránh ghi đè.
- Với DynamoDB, thiết kế key và conditional update phù hợp với event semantics.
- Theo dõi event age và sequence gap để phát hiện mất dữ liệu.

Không giả định một rule action chạy đúng một lần chỉ vì MQTT QoS 1 đã nhận PUBACK.

## 13. Error action và xử lý lỗi

Error action là action tùy chọn được Rules Engine kích hoạt khi một rule action gặp lỗi. Ví dụ:

- IAM role không có quyền PutObject vào bucket.
- DynamoDB throttling hoặc table/key configuration sai.
- Target endpoint không tồn tại hoặc không phản hồi.
- Kinesis stream hoặc Firehose delivery stream không đúng tên.
- Dịch vụ đích từ chối request.

Error action xử lý lỗi khi kích hoạt rule actions. Nó không thay thế CloudWatch logging để debug lỗi SQL hoặc external function trong câu query.

Một error message có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| ruleName | Tên rule gây ra lỗi |
| topic | Topic ban đầu nhận message |
| cloudwatchTraceId | ID liên kết với log tương ứng |
| clientId | MQTT client gửi message |
| base64OriginalPayload | Payload gốc được mã hóa Base64 |
| failures | Danh sách action thất bại |
| failedAction | Tên action lỗi |
| failedResource | Resource đích gặp lỗi |
| errorMessage | Mô tả nguyên nhân |

Một message lỗi được tạo cho mỗi cặp rule/message. Nếu hai action trong cùng rule cùng lỗi, error action có thể nhận một message chứa cả hai failure.

Ví dụ error action ghi lỗi vào S3:

~~~json
{
  "s3": {
    "roleArn": "arn:aws:iam::111122223333:role/IoTRuleErrorRole",
    "bucketName": "company-iot-rule-errors",
    "key": "errors/${replace(topic(), '/', '-')}-${timestamp()}-${newuuid()}.json"
  }
}
~~~

Bucket lỗi nên có lifecycle policy và quyền truy cập hạn chế. Payload gốc có thể chứa dữ liệu nhạy cảm; chỉ cho đội vận hành cần thiết đọc error objects.

Quy trình xử lý:

1. Đọc `cloudwatchTraceId` và `ruleName`.
2. Kiểm tra `failedAction`, `failedResource`, `errorMessage`.
3. Xác định lỗi IAM, quota, network, target availability hay payload/schema.
4. Sửa nguyên nhân và kiểm tra quyền/target.
5. Replay message từ error store theo event ID gốc.
6. Xác minh target đã xử lý và đánh dấu replay hoàn tất.

Error action không tự động replay message sau khi sửa lỗi. Hãy xây dựng quy trình redrive có kiểm soát nếu cần đảm bảo không mất telemetry.

Nên chọn error destination độc lập với target chính khi có thể. Ví dụ, nếu action chính ghi vào S3, dùng SQS hoặc Kinesis làm error destination để lỗi quyền, bucket hoặc outage của S3 không đồng thời làm mất cả dữ liệu lỗi. Error destination cần bền vững, có lifecycle và quy trình redrive riêng.

## 14. IAM và quyền truy cập cho Rules Engine

Một rule action thường sử dụng IAM role để Rules Engine truy cập target service. Role phải được định nghĩa trong cùng AWS account với rule và có trust policy cho phép service principal `iot.amazonaws.com` assume role.

Trust policy nên giới hạn `aws:SourceAccount` và `aws:SourceArn` theo account và rule cụ thể để giảm rủi ro confused deputy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "iot.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "111122223333"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:iot:ap-southeast-1:111122223333:rule/TelemetryRouter"
        }
      }
    }
  ]
}
~~~

Policy gắn vào role chỉ cấp quyền cần cho action. Ví dụ role ghi Kinesis và S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "kinesis:PutRecord",
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/iot-telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::company-iot-raw/telemetry/*"
    }
  ]
}
~~~

Nếu bucket, stream hoặc target database dùng customer managed KMS key, kiểm tra key policy/grant và quyền mã hóa/giải mã cần thiết của dịch vụ đích. IAM policy cho PutObject hoặc PutRecord không tự cấp quyền dùng KMS key.

Người tạo hoặc thay thế rule cần quyền `iam:PassRole` đối với role được gắn vào rule. Không cấp `iam:PassRole` tới mọi role trong account nếu chỉ cần một role dành cho telemetry.

Lambda action là ngoại lệ: Lambda function sử dụng resource-based policy để cho phép AWS IoT gọi function. Người tạo rule không truyền IAM role cho Lambda action theo cách các action khác dùng role.

### 14.1. Device policy và rule role là hai lớp khác nhau

- Device IoT policy quyết định thiết bị có được connect, publish, subscribe hoặc receive trên topic nào.
- Rule IAM role quyết định Rules Engine có được ghi dữ liệu vào Kinesis, S3, DynamoDB hoặc target khác hay không.
- IAM permission của người vận hành quyết định ai được tạo, sửa hoặc xóa rule và ai được `iam:PassRole`.

Ví dụ device chỉ được publish telemetry của chính Thing:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:client/${iot:Connection.Thing.ThingName}"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/org/acme/site/hcmc-01/device/${iot:Connection.Thing.ThingName}/telemetry"
    }
  ]
}
~~~

Policy này minh họa Thing policy variable; cần gắn Thing với certificate/principal và kiểm tra tên Thing thực tế. Không dùng wildcard cho phép thiết bị publish lên command topic hoặc telemetry của thiết bị khác.

Tạo hoặc cập nhật rule là quyền quản trị nhạy cảm: người có quyền thay đổi SQL/actions có thể truy cập dữ liệu mà rule xử lý. Giới hạn quyền quản trị Rules Engine và review mọi thay đổi trước khi đưa vào production.

## 15. Tạo rule bằng AWS CLI

Một rule definition gồm tên, SQL statement, SQL version, một hoặc nhiều actions và error action tùy chọn.

Ví dụ file `telemetry-rule.json`:

~~~json
{
  "sql": "SELECT *, topic(2) AS tenantId, topic(4) AS siteId, topic(6) AS deviceId, timestamp() AS receivedAt FROM 'org/+/site/+/device/+/telemetry' WHERE temperature >= -40 AND temperature <= 125",
  "awsIotSqlVersion": "2016-03-23",
  "ruleDisabled": false,
  "actions": [
    {
      "kinesis": {
        "roleArn": "arn:aws:iam::111122223333:role/IoTRuleKinesisRole",
        "streamName": "iot-telemetry",
        "partitionKey": "${topic(6)}"
      }
    },
    {
      "s3": {
        "roleArn": "arn:aws:iam::111122223333:role/IoTRuleS3Role",
        "bucketName": "company-iot-raw",
        "key": "telemetry/${topic(2)}/${topic(4)}/${topic(6)}/${timestamp()}-${newuuid()}.json"
      }
    }
  ],
  "errorAction": {
    "s3": {
      "roleArn": "arn:aws:iam::111122223333:role/IoTRuleErrorRole",
      "bucketName": "company-iot-rule-errors",
      "key": "errors/${replace(topic(), '/', '-')}-${timestamp()}-${newuuid()}.json"
    }
  }
}
~~~

Tạo rule:

~~~bash
aws iot create-topic-rule \
  --rule-name TelemetryRouter \
  --topic-rule-payload file://telemetry-rule.json \
  --region ap-southeast-1
~~~

Liệt kê rule:

~~~bash
aws iot list-topic-rules \
  --region ap-southeast-1
~~~

Lấy thông tin rule:

~~~bash
aws iot get-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

Disable rule khi cần dừng routing:

~~~bash
aws iot disable-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

Enable lại:

~~~bash
aws iot enable-topic-rule \
  --rule-name TelemetryRouter \
  --region ap-southeast-1
~~~

Các ARN trong ví dụ là placeholder. Trước khi tạo rule, phải tạo stream, bucket, IAM roles và policy phù hợp. Khi thay đổi SQL hoặc action, review ảnh hưởng tới tất cả topic đang match; rule wildcard rộng có thể tăng tải target đột ngột.

## 16. Giám sát Rules Engine với CloudWatch

AWS IoT gửi metrics và logs để theo dõi message broker, rule evaluation và rule actions. Metrics được publish trong namespace `AWS/IoT`; CloudWatch metrics thường được cập nhật theo chu kỳ một phút.

Một số metric quan trọng:

| Metric | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `TopicMatch` | Số message match topic filter của rule | Xác nhận topic filter có nhận đúng traffic |
| `RulesExecuted` | Số lần rule được thực thi | Đo hoạt động tổng thể |
| `RuleNotFound` | Không tìm thấy rule được gọi | Phát hiện Basic Ingest gọi sai/tên rule không tồn tại |
| `ParseError` | Lỗi parse JSON trên topic có rule lắng nghe | Phát hiện payload không hợp lệ |
| `RuleExecutionThrottled` | Message bị throttle bởi cơ chế bảo vệ của Rules Engine, ví dụ Basic Ingest gửi quá nhiều request tới rule không tồn tại | Điều tra traffic Basic Ingest và rule name |
| `RuleEvaluation` với Status=Throttled | Lượt đánh giá rule bị throttle | Kiểm tra account quota |
| `Success` | Rule action invocation thành công | Theo dõi theo RuleName và ActionType |
| `Failure` | Rule action invocation thất bại | Tìm target/action có vấn đề |
| `ErrorActionSuccess` | Error action chạy thành công | Xác nhận lỗi được chuyển tới error store |
| `ErrorActionFailure` | Error action thất bại | Cảnh báo nguy cơ mất thông tin lỗi |

Bật AWS IoT logging để ghi progress events của message broker và Rules Engine vào CloudWatch Logs. Log group thường dùng là `AWSIotLogsV2`.

Một số event log:

- `RuleMatch`: message khớp rule.
- `StartingRuleExecution`: Rules Engine bắt đầu chạy action.
- `RuleExecution`: ghi kết quả thực thi action.
- `RuleEvaluation`: ghi kết quả hoặc lỗi đánh giá rule.
- `RuleExecutionThrottled`: rule bị throttle.
- `RuleNotFound`: Basic Ingest gọi rule không tồn tại hoặc không active.

Mỗi log có thể có `traceId`, `topicName`, `ruleName`, `clientId`, `principalId`, `ruleAction` và trạng thái. Dùng trace ID để liên kết message, rule và lỗi target.

### 16.1. Log level

AWS IoT hỗ trợ các mức:

| Mức | Nội dung |
|---|---|
| ERROR | Operation thất bại |
| WARN | Dấu hiệu có thể gây không nhất quán hoặc lỗi |
| INFO | Thông tin luồng hoạt động ở mức cao |
| DEBUG | Chi tiết phục vụ chẩn đoán |
| DISABLED | Tắt logging |

Dùng DEBUG trong thời gian điều tra và chuyển về mức phù hợp sau đó. Debug log có thể tăng dung lượng, chi phí CloudWatch và chứa metadata nhạy cảm. Không log raw payload nếu không cần.

## 17. Tối ưu chi phí và thông lượng

Chi phí của một pipeline telemetry có thể gồm AWS IoT messaging, rule evaluation, rule actions, dịch vụ target, CloudWatch Logs/Metrics, Kinesis/Firehose, Lambda và lưu trữ S3/Timestream. Tối ưu Rules Engine phải nhìn tổng pipeline, không chỉ một action.

Các biện pháp:

- Dùng Basic Ingest nếu message chỉ cần vào rule actions và không cần broker fan-out.
- Giới hạn topic filter để không đánh giá rule cho message ngoài phạm vi.
- Tránh nhiều rule trùng lặp cùng nghe `#` nếu có thể gom logic hợp lý.
- Dùng WHERE để loại message không cần downstream.
- Chọn action đúng workload: Firehose cho buffering/batch delivery; Kinesis cho nhiều stream consumers; S3 cho archive; Timestream cho time-series queries.
- Không gọi Lambda cho mọi message nếu action native đã đáp ứng yêu cầu.
- Batch hoặc aggregate telemetry ở gateway khi dữ liệu và latency cho phép.
- Giữ payload nhỏ, schema ổn định và chỉ gửi field cần thiết.
- Đặt retention/lifecycle ở target theo nhu cầu phân tích.
- Theo dõi throttling, action failure và destination capacity.

Basic Ingest loại bỏ messaging charge trên đường broker, nhưng không miễn phí rule evaluation, action invocation, Firehose, Kinesis, S3, Lambda hay CloudWatch. Hãy kiểm tra trang giá theo Region và loại message/action thực tế.

Nếu thiết bị gửi hàng nghìn message/giây, cần load test cả Rules Engine evaluation quota và throughput của target. Một rule fan-out tới nhiều target có thể nhân số request downstream; đặt alarm trước khi tăng fleet.

## 18. Kiểm thử và xử lý lỗi thường gặp

AWS IoT Console có MQTT test client để subscribe và publish thử topic. Có thể dùng nó để xác minh payload, topic filter và kết quả republish trước khi triển khai firmware thật.

Quy trình test:

1. Tạo rule ở môi trường development với SQL version được chỉ định.
2. Publish payload hợp lệ tới topic dự kiến.
3. Xác nhận `TopicMatch` và `RulesExecuted` tăng.
4. Kiểm tra dữ liệu ở từng target action.
5. Publish payload không hợp lệ để xác minh WHERE/filter hoặc parse error.
6. Thu hồi quyền target tạm thời trong môi trường test để kiểm tra error action.
7. Kiểm tra `cloudwatchTraceId` và log tương ứng.
8. Publish message có cùng event ID hai lần để kiểm tra dedup ở consumer.
9. Test topic ngoài phạm vi để bảo đảm rule không match.
10. Load test theo peak fleet throughput và theo dõi throttling/target latency.

Bảng troubleshooting:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Rule không chạy | Topic không khớp filter hoặc rule disabled | Kiểm tra topic spelling, case, segment và trạng thái rule |
| Topic wildcard không match | Dùng `+` giữa segment hoặc `#` không ở cuối | Sửa topic filter theo MQTT wildcard rules |
| Rule SQL parse error | SQL version, field expression hoặc JSON payload sai | Kiểm tra SQL version và CloudWatch IoT logs |
| `topic(n)` lấy sai device ID | Segment index không khớp topic schema | Đếm segment từ 1 và kiểm thử bằng topic mẫu |
| Action bị AccessDenied | IAM role policy thiếu quyền hoặc trust policy sai | Kiểm tra role, resource ARN, SourceAccount/SourceArn |
| Rule không assume được role | Role trust thiếu `iot.amazonaws.com` hoặc role khác account | Sửa trust policy và xác minh role cùng account |
| Lambda action bị từ chối | Lambda resource policy chưa cho phép IoT invoke | Thêm permission cho service principal và source rule ARN |
| Kinesis action lỗi | Stream sai Region/tên hoặc role thiếu PutRecord | Kiểm tra stream, Region và IAM policy |
| S3 object bị ghi đè | Object key giống nhau cho nhiều message | Thêm timestamp, event ID hoặc UUID vào key |
| Error action không chạy | Lỗi nằm ở SQL evaluation hoặc error action cũng thiếu quyền | Dùng CloudWatch logs cho SQL; kiểm tra quyền error destination |
| Duplicate telemetry | QoS 1/action retry/producer retry | Dùng event ID và idempotent consumer |
| Rules Engine throttling | Rule evaluation rate hoặc wildcard fan-out quá lớn | Giảm số rule match, kiểm tra quota và scale downstream |
| Target throttling | DynamoDB/Kinesis/SQS hoặc API không đủ capacity | Tăng capacity, buffer qua Firehose/SQS hoặc giảm ingest rate |
| Republish loop | Topic output lại khớp cùng rule | Tách namespace raw/normalized và giới hạn FROM filter |
| Basic Ingest RuleNotFound | Prefix gọi sai rule name hoặc rule không active | Kiểm tra `$aws/rules/{ruleName}` và RuleNotFound metric |

## 19. Bài thực hành: định tuyến telemetry nhà máy

Một nhà máy có nhiều site, mỗi site có nhiều máy bơm và cảm biến. Mỗi thiết bị gửi telemetry mỗi vài giây. Hệ thống cần:

- Lưu toàn bộ raw telemetry vào S3.
- Phát telemetry real-time vào Kinesis cho anomaly detection.
- Ghi trạng thái hiện tại của thiết bị vào DynamoDB.
- Chuyển các cảnh báo nhiệt độ cao tới SQS để worker xử lý.
- Giữ quyền publish riêng cho từng thiết bị.

### 19.1. Topic và payload

Topic:

~~~text
org/acme/site/hcmc-01/device/pump-042/telemetry
~~~

Payload:

~~~json
{
  "eventId": "evt-000184",
  "sequence": 184,
  "observedAt": "2026-11-20T06:30:00Z",
  "temperature": 84.2,
  "pressureKpa": 104.8,
  "vibration": 0.72,
  "batteryPct": 87
}
~~~

### 19.2. Rule routing

- Một rule telemetry chung nhận `org/+/site/+/device/+/telemetry`.
- SQL bổ sung tenantId, siteId, deviceId và receivedAt.
- Kinesis action dùng deviceId làm partition key.
- S3 action dùng tenant/site/device/time để tạo object key duy nhất.
- Một rule alert riêng lọc `temperature >= 80` và gửi SQS.
- Một job/consumer cập nhật DynamoDB current state theo deviceId và sequence.

### 19.3. Vận hành và xác minh

1. Tạo Kinesis stream, S3 bucket, SQS queue và DynamoDB table.
2. Tạo IAM roles riêng cho Kinesis, S3 và SQS actions.
3. Tạo device policy chỉ cho phép publish đúng telemetry topic của Thing.
4. Tạo rule SQL và kiểm tra `topic(n)` theo topic schema.
5. Tạo error action lưu failure vào S3 hoặc SQS chuyên dụng.
6. Publish telemetry bằng MQTT test client và kiểm tra tất cả target.
7. Publish nhiệt độ bình thường và cao để kiểm tra WHERE.
8. Gửi cùng event ID hai lần để xác minh consumer dedup.
9. Thu hồi quyền target trong môi trường test để kiểm tra error action.
10. Bật CloudWatch metrics/logs và đặt alarm cho `Failure`, `RuleExecutionThrottled` và `ErrorActionFailure`.
11. Load test với số lượng thiết bị giả lập và tốc độ publish dự kiến.
12. Kiểm tra chi phí messaging, rule actions và target services trước khi mở rộng fleet.

Tiêu chí thành công:

- Topic filter nhận đúng tenant/site/device.
- SQL output có đầy đủ metadata và không làm sai schema.
- Kinesis partition key giữ record của cùng thiết bị trong cùng partition mapping.
- S3 object key không ghi đè message khác.
- Alert chỉ gửi khi điều kiện nghiệp vụ đúng.
- IAM role của từng action chỉ có quyền target cần thiết.
- Error action lưu được thông tin lỗi và original payload.
- Consumer xử lý duplicate an toàn.
- CloudWatch metrics giúp phân biệt lỗi SQL, lỗi action và throttling.

## Kết luận

AWS IoT Rules Engine kết nối MQTT telemetry với hệ sinh thái AWS bằng topic filters, SQL statements và rule actions. Topic namespace quyết định cách phân nhóm và phân quyền message; SQL quyết định dữ liệu nào được chọn, lọc và biến đổi; actions quyết định telemetry được gửi tới Kinesis, Firehose, S3, DynamoDB, Lambda, Timestream, IoT SiteWise hoặc dịch vụ khác.

Một pipeline đáng tin cậy cần chọn đúng topic filter, chỉ định SQL version, dùng substitution templates đúng ngữ cảnh, cấp IAM role least privilege và có error action cho lỗi target. MQTT QoS 1 không bảo đảm mọi action hoàn tất đúng một lần; hãy giữ event ID ổn định và thiết kế downstream idempotent. Basic Ingest giảm messaging cost khi không cần broker fan-out, còn CloudWatch metrics/logs giúp quan sát rule execution và xử lý lỗi.

Khi thiết kế production, hãy kiểm thử topic/payload thực tế, đo peak throughput, theo dõi target capacity, kiểm soát wildcard fan-out và diễn tập error redrive. Rules Engine phù hợp cho routing và biến đổi nhẹ; workflow hoặc stream processor chuyên biệt nên đảm nhiệm các nghiệp vụ nhiều bước, có state hoặc cần transaction semantics phức tạp.

## Tài liệu tham khảo

- [AWS IoT Rules Engine overview](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [Creating an AWS IoT rule](https://docs.aws.amazon.com/iot/latest/developerguide/iot-create-rule.html)
- [AWS IoT SQL reference](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-reference.html)
- [AWS IoT SQL functions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-functions.html)
- [FROM clause and topic filters](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-from.html)
- [AWS IoT rule actions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rule-actions.html)
- [Substitution templates](https://docs.aws.amazon.com/iot/latest/developerguide/iot-substitution-templates.html)
- [Error handling and error actions](https://docs.aws.amazon.com/iot/latest/developerguide/rule-error-handling.html)
- [MQTT topics and topic filters](https://docs.aws.amazon.com/iot/latest/developerguide/topics.html)
- [MQTT protocol and QoS options](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [Reducing messaging costs with Basic Ingest](https://docs.aws.amazon.com/iot/latest/developerguide/iot-basic-ingest.html)
- [Granting an AWS IoT rule the access it requires](https://docs.aws.amazon.com/iot/latest/developerguide/iot-create-role.html)
- [Passing role permissions](https://docs.aws.amazon.com/iot/latest/developerguide/pass-role.html)
- [Publish/Subscribe policy examples](https://docs.aws.amazon.com/iot/latest/developerguide/pub-sub-policy.html)
- [Configure AWS IoT logging](https://docs.aws.amazon.com/iot/latest/developerguide/configure-logging.html)
- [AWS IoT metrics and dimensions](https://docs.aws.amazon.com/iot/latest/developerguide/metrics_dimensions.html)
- [AWS IoT Core endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [AWS IoT Core pricing](https://aws.amazon.com/iot-core/pricing/)
- [AWS IoT Lens: failure management and error actions](https://docs.aws.amazon.com/wellarchitected/latest/iot-lens/failure-management.html)

