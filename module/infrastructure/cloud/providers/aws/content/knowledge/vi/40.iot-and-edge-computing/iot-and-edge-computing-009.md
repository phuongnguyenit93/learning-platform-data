# Bảo mật thiết bị, quan sát telemetry và tích hợp backend AWS

Một hệ thống IoT production có thể quản lý hàng nghìn hoặc hàng triệu thiết bị ở nhà máy, cửa hàng, phương tiện hoặc địa điểm xa. Mỗi thiết bị gửi telemetry, nhận lệnh, cập nhật firmware và có thể hoạt động qua mạng không ổn định. Nếu các thiết bị dùng chung credential, topic MQTT quá rộng hoặc backend không ghi nhận được trạng thái kết nối, một thiết bị bị xâm nhập có thể ảnh hưởng tới cả fleet và đội vận hành khó xác định lỗi nằm ở thiết bị, mạng hay dịch vụ cloud.

AWS IoT Core cung cấp message broker, registry, policy và các khả năng quản lý thiết bị để kết nối thiết bị với ứng dụng cloud. AWS IoT Rules Engine có thể lọc, biến đổi và chuyển message tới các dịch vụ backend như Amazon S3, Amazon Kinesis, AWS Lambda, Amazon DynamoDB, Amazon SQS, Amazon SNS, Amazon OpenSearch Service, AWS IoT SiteWise và Amazon CloudWatch. AWS IoT Device Management cung cấp các khả năng như fleet provisioning, fleet indexing, jobs và secure tunneling. AWS IoT Greengrass bổ sung runtime cho xử lý và quản lý ứng dụng ở edge.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, người học cần thiết kế danh tính riêng cho từng thiết bị, giới hạn quyền publish/subscribe theo topic, bảo vệ credential, quan sát kết nối và telemetry, đồng thời tích hợp dữ liệu vào backend có thể mở rộng. Bài học tập trung vào ba mục tiêu: thiết bị chỉ được làm đúng việc được cấp phép; dữ liệu và trạng thái thiết bị có thể quan sát; backend tiếp nhận, xử lý và lưu trữ telemetry theo cách có thể vận hành và kiểm soát chi phí.

## 1. Kiến trúc tổng thể của hệ thống IoT

Một kiến trúc tham khảo gồm thiết bị/edge gateway, AWS IoT Core, Rules Engine, các dịch vụ xử lý và lớp quan sát.

~~~mermaid
flowchart LR
    subgraph Edge["Thiết bị và Edge"]
      A[Sensor / MCU]
      B[Industrial gateway]
      C[Greengrass components]
      A --> B
      B --> C
    end
    subgraph IoT["AWS IoT"]
      D[IoT Core MQTT broker]
      E[Thing Registry and Policies]
      F[Device Shadows]
      G[Rules Engine]
      D <--> E
      D <--> F
      D --> G
    end
    subgraph Backend["Backend AWS"]
      H[Kinesis / Firehose]
      I[Lambda / SQS]
      J[S3 data lake]
      K[DynamoDB / SiteWise / OpenSearch]
      L[CloudWatch]
      H --> J
      I --> K
    end
    C <-->|MQTT over TLS| D
    G --> H
    G --> I
    G --> K
    D --> L
    G --> L
~~~

Mỗi thành phần có trách nhiệm riêng:

- **Device identity:** xác định thiết bị nào đang kết nối.
- **Authentication:** chứng minh thiết bị sở hữu credential hợp lệ.
- **Authorization:** giới hạn hành động và topic thiết bị được phép dùng.
- **Message broker:** nhận và phân phối message MQTT.
- **Device Shadow:** lưu trạng thái mong muốn và trạng thái thiết bị báo cáo.
- **Rules Engine:** định tuyến telemetry sang backend.
- **Device Management:** provisioning, firmware/software jobs, indexing và remote operations.
- **Observability:** theo dõi kết nối, lỗi, throughput, độ trễ, chất lượng dữ liệu và hành vi bất thường.

Không nên dùng một policy, certificate hoặc IAM role chung cho toàn bộ thiết bị. Mỗi lớp cần có ranh giới quyền riêng và được kiểm thử trong tình huống thiết bị mất mạng, credential bị lộ hoặc backend không sẵn sàng.

## 2. Thing Registry và danh tính thiết bị

AWS IoT Thing Registry lưu thông tin logic về thiết bị, thường gọi là Thing. Một Thing có thể có tên, loại, attribute và quan hệ với Thing Group. Registry giúp tổ chức fleet và liên kết thiết bị với certificate hoặc principal.

Ví dụ một Thing đại diện cho cảm biến nhiệt độ:

~~~json
{
  "thingName": "factory-line-01-sensor-007",
  "thingTypeName": "TemperatureSensor",
  "attributePayload": {
    "site": "factory-01",
    "line": "line-01",
    "firmware": "2.4.1",
    "environment": "production"
  }
}
~~~

Thing Registry không phải kho telemetry. Các thuộc tính trong Thing mô tả thiết bị và hỗ trợ quản lý fleet; dữ liệu đo liên tục nên được chuyển qua MQTT và Rules Engine tới hệ thống lưu trữ phù hợp.

### Thing Groups

Thing Group gom thiết bị theo site, model, môi trường, firmware hoặc đơn vị vận hành. Thing Groups có thể lồng nhau theo cấu trúc phân cấp, giúp target jobs và áp dụng cấu hình theo phạm vi fleet.

Ví dụ:

- factory-01
  - line-01
  - line-02
- factory-02
  - line-01

Nhóm thiết bị theo môi trường production, staging và test giúp giảm nguy cơ phát hành nhầm firmware hoặc policy tới toàn bộ fleet.

## 3. Một danh tính riêng cho mỗi thiết bị

AWS khuyến nghị dùng một identity riêng cho mỗi thiết bị. Với MQTT mutual TLS, thiết bị thường xác thực bằng X.509 client certificate và private key tương ứng.

Thiết kế identity nên đáp ứng:

- Certificate được tạo riêng cho từng thiết bị hoặc từng đơn vị có ranh giới tin cậy riêng.
- Private key được lưu trong secure element, TPM hoặc vùng bảo vệ phần cứng nếu thiết bị hỗ trợ.
- Certificate được gắn với Thing phù hợp; cân nhắc exclusive attachment để một principal không bị dùng chung ngoài ý muốn.
- Certificate có trạng thái ACTIVE, INACTIVE hoặc REVOKED được quản lý theo vòng đời.
- Có quy trình cấp mới, luân chuyển, thu hồi và xử lý thiết bị mất hoặc bị đánh cắp.
- Không đóng gói một private key chung vào image firmware cho cả lô sản phẩm.

Một credential dùng chung khiến việc thu hồi trở nên nguy hiểm: thu hồi một thiết bị có thể làm gián đoạn mọi thiết bị khác. Identity riêng giúp cô lập sự cố và tạo audit trail theo từng Thing.

## 4. X.509 mutual TLS và bảo vệ kết nối

Khi thiết bị kết nối MQTT qua TLS mutual authentication, hai phía xác minh danh tính:

1. Thiết bị xác minh server certificate của AWS IoT Core.
2. AWS IoT Core xác minh client certificate của thiết bị.
3. AWS IoT kiểm tra certificate có được đăng ký, active và có policy phù hợp không.
4. Policy quyết định client được kết nối bằng client ID nào và được publish/subscribe topic nào.

Thiết bị phải xác minh certificate chain và hostname của endpoint AWS IoT. Không bỏ qua kiểm tra certificate khi lỗi TLS; hành vi này có thể khiến thiết bị kết nối tới server giả mạo.

### Đồng hồ thiết bị

Certificate có thời hạn hiệu lực. Nếu clock của thiết bị sai, certificate hợp lệ có thể bị xem là chưa hiệu lực hoặc đã hết hạn. Thiết bị nên đồng bộ thời gian bằng NTP trước khi tạo TLS connection nếu phần cứng cho phép. Với thiết bị không có RTC hoặc mạng chưa sẵn sàng, cần thiết kế bước bootstrap thời gian đáng tin cậy.

### Các biện pháp ở thiết bị

- Secure boot để chỉ khởi chạy firmware đã được xác minh.
- Signed firmware và kiểm tra chữ ký trước khi cài.
- Tắt debug interface hoặc bảo vệ bằng cơ chế xác thực.
- Mã hóa dữ liệu nhạy cảm tại thiết bị nếu có lưu trữ cục bộ.
- Giới hạn dịch vụ mạng và port đang lắng nghe.
- Ghi log sự kiện bảo mật và đồng bộ khi có kết nối.
- Không ghi private key, token hoặc secret vào log.

## 5. AWS IoT Policies và nguyên tắc least privilege

AWS IoT Policy là lớp authorization dành cho các thao tác IoT như connect, publish, subscribe và receive. Policy này khác IAM policy của backend service.

Các action quan trọng:

| Action | Mục đích | Resource ARN |
|---|---|---|
| iot:Connect | Kết nối MQTT broker | client |
| iot:Publish | Gửi message tới topic | topic |
| iot:Subscribe | Đăng ký topic filter | topicfilter |
| iot:Receive | Nhận message từ topic | topic |

Policy nên giới hạn:

- Client ID được phép dùng.
- Topic telemetry mà thiết bị được publish.
- Topic command mà thiết bị được subscribe.
- Topic shadow tương ứng với Thing.
- Các API/operation bổ sung mà thiết bị thực sự cần.

Không cấp wildcard trên toàn bộ topic namespace nếu thiết bị chỉ cần một nhánh. Policy rộng có thể cho phép thiết bị đọc lệnh hoặc dữ liệu của thiết bị khác.

## 6. Policy mẫu dùng Thing policy variables

Khi certificate được gắn với Thing, có thể dùng policy variable để tạo policy có thể tái sử dụng cho nhiều thiết bị mà vẫn giới hạn theo Thing name. Ví dụ dưới đây cho phép thiết bị chỉ kết nối với client ID trùng tên Thing, publish telemetry riêng và subscribe/receive lệnh riêng.

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
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/factory/${iot:Connection.Thing.ThingName}/telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topicfilter/factory/${iot:Connection.Thing.ThingName}/commands"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-southeast-1:111122223333:topic/factory/${iot:Connection.Thing.ThingName}/commands"
    }
  ]
}
~~~

Thay account ID và Region theo môi trường. Policy variable chỉ được phân giải khi identity được gắn với Thing theo điều kiện hỗ trợ; nếu variable không phân giải, request có thể bị từ chối. Client ID trong MQTT CONNECT phải khớp Thing name trong ví dụ này.

Policy là một phần của authorization. Cần kiểm tra cả certificate attachment, policy attachment, Thing Registry và client ID trong log khi kết nối bị từ chối.

## 7. Vòng đời certificate và luân chuyển credential

Certificate không nên được xem là cấu hình cài một lần rồi bỏ quên. Hãy quản lý vòng đời từ lúc sản xuất tới khi thiết bị hết hạn sử dụng.

### Quy trình luân chuyển tham khảo

1. Tạo certificate mới và gắn policy giới hạn theo Thing.
2. Đưa certificate mới tới thiết bị qua kênh update đã xác thực.
3. Thiết bị kiểm tra certificate/key pair và lưu an toàn.
4. Kết nối thử bằng certificate mới.
5. Xác nhận telemetry, shadow và command hoạt động.
6. Thu hồi hoặc deactivate certificate cũ sau khi thiết bị đã chuyển thành công.
7. Ghi nhận phiên bản credential và kết quả rotation trong inventory.

Không deactivate certificate cũ trước khi thiết bị có thể sử dụng certificate mới, trừ khi đang ứng phó sự cố compromise và chấp nhận thiết bị tạm thời mất kết nối. Với fleet lớn, chia rotation thành từng nhóm và theo dõi tỷ lệ thành công.

### Khi thiết bị bị mất hoặc nghi bị xâm nhập

- Deactivate/revoke certificate của thiết bị bị ảnh hưởng.
- Thu hẹp hoặc gỡ policy liên quan.
- Chặn hoặc cô lập thiết bị ở mạng tại chỗ nếu có thể.
- Kiểm tra client ID, source IP, topic activity và message volume.
- Đánh giá xem credential có bị dùng ở thiết bị khác hay không.
- Cấp lại identity và thực hiện onboarding an toàn sau khi xử lý.

## 8. Provisioning fleet: JITP và Fleet Provisioning

Tạo Thing, certificate và policy thủ công cho từng thiết bị không phù hợp với fleet lớn. AWS IoT hỗ trợ các cách provisioning tự động.

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Manual provisioning | Người vận hành tạo Thing/certificate/policy | Lab, prototype hoặc số lượng nhỏ |
| Just-in-time provisioning (JITP) | Certificate do CA đã đăng ký ký; khi thiết bị kết nối lần đầu, AWS IoT có thể đăng ký và tạo resource theo template | Nhà sản xuất có PKI và quy trình cấp certificate riêng |
| Fleet Provisioning by claim | Thiết bị dùng claim credential có phạm vi hẹp để nhận certificate riêng khi onboarding | Sản xuất thiết bị hàng loạt |
| Fleet Provisioning by trusted user | Ứng dụng/người dùng đáng tin cấp onboarding flow cho thiết bị | Thiết bị được cấu hình tại điểm bán hoặc khi cài đặt |

Provisioning template mô tả Thing, certificate và policy cần tạo. Có thể dùng pre-provisioning hook để kiểm tra serial number, entitlement, inventory hoặc dữ liệu đăng ký trước khi cho phép tạo resource.

### Bảo vệ claim certificate

Claim certificate là credential onboarding tạm thời, không nên dùng cho giao tiếp production lâu dài. Policy của claim chỉ nên cho phép các thao tác provisioning cần thiết. Sau khi thiết bị nhận certificate riêng:

1. Lưu permanent private key an toàn.
2. Hoàn tất RegisterThing theo template.
3. Ngắt session claim.
4. Kết nối lại bằng certificate riêng.
5. Kiểm tra policy production đã được gắn đúng.

Nếu claim credential bị trích xuất, kẻ tấn công có thể thử đăng ký thiết bị giả. Vì vậy cần kiểm soát lô sản xuất, bảo vệ claim key, giới hạn template và xác thực thông tin thiết bị.

### Kiểm thử thiết bị trước khi đưa vào fleet

AWS IoT Device Advisor cung cấp test suites để kiểm tra thiết bị có thể kết nối ổn định với AWS IoT Core và đáp ứng một số best practices về TLS, MQTT, Device Shadow, Jobs, permissions/policies và long-duration connection. Chạy kiểm thử trên firmware và hardware đại diện trước khi sản xuất hàng loạt; sau khi thay đổi TLS library, MQTT client hoặc provisioning flow, chạy lại các test phù hợp.

Device Advisor hiện hỗ trợ các Region us-east-1, us-west-2, ap-northeast-1 và eu-west-1; không có ap-southeast-1 trong danh sách Region hỗ trợ. Nếu hệ thống IoT chính đặt tại Singapore, cần kiểm tra thiết kế kết nối tới test endpoint ở Region được hỗ trợ trước khi đưa công cụ này vào quy trình qualification.

Device Advisor hỗ trợ qualification và troubleshooting cho thiết bị. Nó không thay thế kiểm thử bảo mật phần cứng, fuzzing, penetration test hoặc giám sát fleet production.

## 9. MQTT và thiết kế topic

MQTT là giao thức publish/subscribe nhẹ, phù hợp thiết bị có CPU, memory và bandwidth hạn chế. Thiết bị publish message lên topic; subscriber nhận message từ topic hoặc topic filter.

Một topic convention cần:

- Có namespace theo site, Thing hoặc loại message.
- Phân biệt telemetry, command, status, event và diagnostics.
- Có quy tắc chữ thường/hoa và separator nhất quán.
- Tránh đưa PII hoặc secret vào topic name.
- Không nhúng cấu trúc quá sâu khiến policy và filter khó quản lý.

Ví dụ:

~~~text
factory/{thingName}/telemetry
factory/{thingName}/status
factory/{thingName}/commands
factory/{thingName}/events
factory/{thingName}/diagnostics
~~~

Topic name và payload schema cần được version hóa. Nếu thay đổi schema, nên có schemaVersion hoặc topic version để backend có thể xử lý producer cũ và mới trong giai đoạn chuyển đổi.

## 10. MQTT QoS, retained message và persistent session

AWS IoT Core hỗ trợ MQTT QoS 0 và QoS 1; không hỗ trợ QoS 2.

| Cơ chế | Ý nghĩa | Cách dùng |
|---|---|---|
| QoS 0 | Gửi zero hoặc nhiều lần; message có thể bị mất | Telemetry tần suất cao, có thể chấp nhận mất một số sample |
| QoS 1 | Gửi ít nhất một lần; có thể nhận trùng | Command hoặc event cần xác nhận, backend phải xử lý idempotent |
| Retained message | Broker giữ message cuối cùng trên một topic | Gửi cấu hình hoặc trạng thái mới nhất cho subscriber mới |
| Persistent session | Lưu subscription và message QoS 1 chưa được xác nhận trong giới hạn dịch vụ | Thiết bị thường xuyên offline và cần nhận message khi reconnect |

QoS 1 không đồng nghĩa exactly-once. Consumer có thể nhận message trùng khi retry hoặc reconnect. Dùng messageId, sequence number, event timestamp hoặc idempotency key để loại trùng ở backend.

Retained message và Device Shadow có mục đích khác nhau. Retained message giữ một payload cuối trên topic, không có schema state chuẩn, version tự động hay delta. Device Shadow có desired/reported state, version và timestamp.

Persistent session không phải message queue vô hạn. Message có giới hạn lưu, có thể hết hạn hoặc bị drop khi vượt quota. Ứng dụng cần xử lý reconnect, replay và đồng bộ trạng thái.

## 11. Chuẩn hóa telemetry payload

Telemetry cần mang đủ thông tin để backend xác định nguồn, thời điểm, loại metric và schema. Một payload mẫu:

~~~json
{
  "schemaVersion": "1.0",
  "deviceId": "factory-line-01-sensor-007",
  "eventId": "evt-20261120-00001234",
  "sequence": 1234,
  "eventTime": "2026-11-20T07:30:15.245Z",
  "measurements": {
    "temperatureC": 82.4,
    "humidityPct": 46.2,
    "vibrationMmS": 2.1
  },
  "quality": {
    "sensorStatus": "OK",
    "calibrationVersion": "cal-2026-04"
  }
}
~~~

Thiết kế payload:

- Dùng UTC và ISO 8601 cho event time.
- Phân biệt eventTime với thời điểm backend nhận message.
- Có sequence/eventId để phát hiện duplicate và gap.
- Ghi rõ đơn vị đo, tránh các field như temperature không nói rõ Celsius hay Fahrenheit.
- Có schemaVersion để hỗ trợ thay đổi schema.
- Giới hạn payload size và không gửi field không cần thiết.
- Không đưa credential, thông tin cá nhân hoặc bí mật vào telemetry.

Nếu thiết bị offline, có thể buffer telemetry cục bộ rồi gửi lại theo batch khi kết nối phục hồi. Backend phải chấp nhận dữ liệu đến trễ và không giả định message luôn đến theo thứ tự.

## 12. AWS IoT Device Shadows

Device Shadow lưu trạng thái logic của thiết bị dưới dạng JSON document trên AWS IoT. Ứng dụng có thể cập nhật desired state ngay cả khi thiết bị offline; thiết bị đồng bộ khi kết nối lại.

Shadow document có ba khái niệm:

- **desired:** trạng thái mà ứng dụng muốn thiết bị đạt được.
- **reported:** trạng thái mà thiết bị báo cáo hiện tại.
- **delta:** phần khác biệt giữa desired và reported.

Ví dụ ứng dụng yêu cầu đặt nhiệt độ mục tiêu 22°C:

~~~json
{
  "state": {
    "desired": {
      "targetTemperatureC": 22
    },
    "reported": {
      "targetTemperatureC": 24
    }
  }
}
~~~

Device Shadow có thể phát delta để thiết bị biết giá trị cần thay đổi. Khi thiết bị áp dụng xong, nó cập nhật reported state thành 22.

### Named và classic shadow

Mỗi Thing có thể có một classic unnamed shadow. Named shadows cho phép tách trạng thái theo chức năng, ví dụ configuration, connectivity hoặc firmware. Nếu dự kiến có nhiều nhóm trạng thái độc lập, nên cân nhắc named shadows ngay từ thiết kế.

### Version và message ordering

Shadow document có version tăng sau mỗi lần cập nhật. Client có thể gửi version hiện tại để tránh ghi đè bằng state cũ. Tuy nhiên, message từ AWS IoT không được bảo đảm đến thiết bị theo đúng thứ tự. Thiết bị nên bỏ qua delta có version cũ hơn version mà nó đã xử lý.

Chỉ ứng dụng hoặc thiết bị đáng tin cậy mới nên có quyền update phần desired state. Nếu mọi client đều có thể sửa desired, thiết bị có thể nhận cấu hình ngoài dự kiến.

## 13. AWS IoT Rules Engine

Rules Engine đọc MQTT topic stream, áp dụng SQL-like statement để lọc/biến đổi message rồi gọi một hoặc nhiều action. Nhờ đó thiết bị chỉ cần publish telemetry tới AWS IoT Core; backend không cần duy trì một MQTT subscriber riêng cho mọi luồng dữ liệu.

Luồng xử lý:

1. Thiết bị publish telemetry lên topic.
2. Rule filter topic và điều kiện trong payload.
3. SQL projection chọn hoặc đổi tên field.
4. Rule action gửi kết quả tới dịch vụ backend.
5. Nếu action lỗi, error action có thể chuyển message lỗi tới nơi xử lý riêng.

Các action phổ biến gồm:

- Amazon S3 để lưu raw event hoặc file.
- Amazon Kinesis Data Streams để xử lý streaming.
- Amazon Data Firehose để giao dữ liệu tới S3 và các destination hỗ trợ.
- AWS Lambda để chạy business logic.
- Amazon DynamoDB để lưu trạng thái hoặc event đã chuẩn hóa.
- Amazon SQS và Amazon SNS để tích hợp hệ thống bất đồng bộ.
- Amazon OpenSearch Service để tìm kiếm và phân tích log/event.
- Amazon CloudWatch Logs và Metrics để quan sát.
- AWS IoT SiteWise để lưu dữ liệu công nghiệp theo asset model.
- AWS Step Functions để bắt đầu workflow.

Khả năng action phụ thuộc Region và dịch vụ đích. Kiểm tra tài liệu rule action cho Region đang triển khai.

## 14. Ví dụ Rule SQL và định tuyến telemetry

Giả sử thiết bị publish lên topic:

~~~text
factory/+/telemetry
~~~

Rule sau lấy các field cần thiết và chỉ chuyển message khi nhiệt độ vượt ngưỡng:

~~~sql
SELECT
    topic(2) AS deviceId,
    temperatureC,
    humidityPct,
    eventTime,
    sequence,
    timestamp() AS receivedAt
FROM 'factory/+/telemetry'
WHERE temperatureC >= 80
~~~

Rule có thể gửi dữ liệu tới Lambda để tạo alarm, hoặc tới Kinesis/Firehose để lưu và phân tích. topic(2) trích segment thứ hai từ topic mẫu, nên với factory/{thingName}/telemetry nó trả về Thing name.

### Role cho Rule Action

Rule cần IAM role cho phép AWS IoT thực hiện action tới dịch vụ đích. Ví dụ action S3 cần quyền ghi đúng bucket/prefix; action Lambda cần quyền invoke function; action Kinesis cần quyền PutRecord/PutRecords phù hợp.

Tách role theo rule hoặc data domain để giảm blast radius. Không dùng role admin cho mọi rule.

## 15. Error action và xử lý lỗi tích hợp

Một rule có thể lọc đúng nhưng action tới backend thất bại do thiếu quyền, quota, network hoặc service unavailable. Error action cho phép chuyển thông tin về lỗi và message gốc tới nơi xử lý, ví dụ SQS, S3 hoặc CloudWatch Logs.

Thiết kế error handling:

- Có error action cho rule quan trọng.
- Ghi lại rule name, action type, timestamp và correlation ID.
- Tách retry có giới hạn khỏi dead-letter/error storage.
- Có cảnh báo khi số lỗi action tăng.
- Thiết kế downstream consumer idempotent.
- Có quy trình replay message sau khi sửa lỗi.

Không nên âm thầm drop message quan trọng khi action lỗi. Với telemetry không quan trọng, có thể chấp nhận sampling/drop theo policy; với alarm hoặc command, cần lưu vết và cơ chế khôi phục rõ ràng.

## 16. Tích hợp backend: chọn dịch vụ theo workload

| Nhu cầu | Dịch vụ AWS phù hợp | Gợi ý thiết kế |
|---|---|---|
| Lưu raw telemetry dài hạn | Amazon S3 | Dùng prefix theo thời gian/device group và lifecycle |
| Streaming analytics | Kinesis Data Streams | Consumer xử lý gần real-time |
| Buffer và delivery managed | Amazon Data Firehose | Ghi batch tới S3 hoặc destination hỗ trợ |
| Business logic hoặc enrichment | AWS Lambda | Giữ function stateless, idempotent |
| Hàng đợi command/event | Amazon SQS | Tách producer/consumer, xử lý retry và DLQ |
| Notification | Amazon SNS | Fan-out thông báo tới subscriber |
| Trạng thái thiết bị/key-value | Amazon DynamoDB | Lưu trạng thái cần lookup nhanh |
| Search và log analytics | Amazon OpenSearch Service | Index các field cần tìm kiếm |
| Dữ liệu công nghiệp theo asset | AWS IoT SiteWise | Ánh xạ telemetry thành asset/property |
| Metric vận hành | Amazon CloudWatch | Theo dõi rule, broker và backend |

Không đưa mọi telemetry trực tiếp vào Lambda nếu cần throughput rất lớn hoặc xử lý dài. Kinesis/Firehose có thể tạo buffer và tách ingestion khỏi processing. Chọn dịch vụ theo latency, ordering, retention, throughput và cách tiêu thụ dữ liệu.

## 17. Lưu telemetry vào S3 và xây dựng data lake

S3 phù hợp để lưu telemetry raw và dữ liệu đã chuẩn hóa với chi phí lưu trữ linh hoạt. Có thể dùng Rule Action S3 cho các luồng đơn giản hoặc Kinesis Data Firehose khi cần buffering, batch delivery và transformation.

Một layout tham khảo:

~~~text
s3://iot-data-lake/
  raw/
    site=factory-01/
      year=2026/month=11/day=20/hour=07/
  curated/
    site=factory-01/
      year=2026/month=11/day=20/
~~~

Raw giữ message gốc để replay; curated chuẩn hóa schema, timestamp, units và loại bỏ duplicate. AWS Glue Data Catalog có thể lưu metadata để Athena hoặc Redshift Spectrum truy vấn dữ liệu.

Đừng tạo một object S3 cho mỗi message nhỏ nếu throughput cao. Dùng Firehose buffering hoặc stream processing để gom batch thành file đủ lớn, giảm overhead request và metadata.

## 18. Tích hợp với AWS IoT SiteWise cho công nghiệp

AWS IoT SiteWise phù hợp với dữ liệu vận hành công nghiệp, nơi telemetry cần gắn với asset, equipment, property và hierarchy.

Ví dụ:

- Factory là asset cấp cao.
- Production line là asset con.
- Motor là asset thiết bị.
- Temperature, pressure, vibration là asset properties.

Rules Engine có thể chuyển message tới SiteWise asset property. Điều này giúp dữ liệu cảm biến gắn với mô hình tài sản, hỗ trợ dashboard, tính toán metric và theo dõi hiệu năng thiết bị.

Nếu dữ liệu chỉ là event chung hoặc log ứng dụng, S3/Kinesis/OpenSearch có thể phù hợp hơn. Không cần ép mọi loại telemetry vào asset model.

## 19. AWS IoT Greengrass cho xử lý tại edge

AWS IoT Greengrass V2 đưa runtime và component deployment tới edge device. Edge device có thể xử lý dữ liệu gần nguồn, phản hồi local event và tiếp tục một số hoạt động khi mất kết nối cloud.

Các use case:

- Lọc hoặc tổng hợp sensor data tại nhà máy trước khi gửi cloud.
- Chạy inference gần camera hoặc thiết bị công nghiệp.
- Kết nối thiết bị legacy qua gateway.
- Chạy local MQTT pub/sub giữa component.
- Điều khiển thiết bị hoặc phát hiện anomaly với latency thấp.
- Quản lý component và cấu hình trên nhiều edge devices.

### Thành phần

- **Greengrass nucleus:** runtime lõi điều phối component và kết nối với cloud.
- **Components:** ứng dụng, Lambda function, connector hoặc dependency chạy ở edge.
- **Deployments:** cấu hình component/version/parameter được triển khai tới core device hoặc nhóm thiết bị.
- **Local resources:** file, port, device interface hoặc service mà component cần truy cập.

Greengrass không thay thế AWS IoT Core. IoT Core quản lý kết nối và message broker cloud; Greengrass quản lý runtime và xử lý cục bộ ở edge.

## 20. Edge offline behavior và đồng bộ dữ liệu

Mạng tại edge có thể chập chờn. Một hệ thống production cần quyết định rõ điều gì tiếp tục chạy khi cloud không truy cập được:

- Local control loop nào phải tiếp tục hoạt động.
- Telemetry nào được buffer tại edge.
- Dung lượng disk và thời gian giữ dữ liệu offline.
- Cách xử lý khi buffer đầy.
- Chính sách gửi bù và loại bỏ duplicate khi reconnect.
- Cách đồng bộ desired/reported state và configuration.
- Cách tránh áp dụng command đã hết hạn sau khi thiết bị online lại.

Không để cloud dependency nằm trong safety-critical control loop nếu thiết bị phải tiếp tục vận hành an toàn khi mất mạng. Thiết kế local fail-safe, watchdog và manual override theo yêu cầu hệ thống.

### Store-and-forward

Edge gateway có thể ghi telemetry vào local queue/database rồi gửi lên cloud theo batch. Mỗi event cần có ID, sequence và event time. Backend nên xử lý idempotent vì khi reconnect, batch có thể được gửi lại sau timeout.

## 21. AWS IoT Jobs để cập nhật firmware và phần mềm

AWS IoT Jobs quản lý remote operation gửi tới một hoặc nhiều Thing hoặc Thing Group. Job document mô tả thao tác thiết bị cần thực hiện, ví dụ tải firmware, cài phần mềm, reboot, rotate certificate hoặc chạy diagnostics.

Một deployment có thể cấu hình:

- Rollout rate: tốc độ phân phối job tới fleet.
- Abort criteria: dừng rollout khi tỷ lệ lỗi vượt ngưỡng.
- Timeout: giới hạn thời gian một thiết bị hoàn thành.
- Retry: gửi lại job execution thất bại theo policy.
- Scheduling: lên lịch bảo trì hoặc update theo khung giờ.

### Quy trình OTA an toàn

1. Build firmware và ký artifact.
2. Lưu artifact ở location được bảo vệ.
3. Tạo job document với version, checksum và hướng dẫn cài đặt.
4. Target một Thing Group thử nghiệm.
5. Thiết bị tải artifact, kiểm tra chữ ký/checksum rồi cài.
6. Thiết bị báo trạng thái job execution.
7. Quan sát tỷ lệ thành công, reboot, kết nối lại và health metrics.
8. Mở rộng rollout theo từng nhóm.
9. Abort hoặc rollback khi vượt ngưỡng lỗi.

Job quản lý phân phối và trạng thái remote operation; firmware installer trên thiết bị vẫn phải kiểm tra tính toàn vẹn, tương thích phần cứng và khả năng rollback.

## 22. Fleet indexing và quản lý thiết bị

Fleet indexing giúp tìm kiếm Thing và tổng hợp thuộc tính/Shadow data theo cấu hình indexing. Đội vận hành có thể tìm thiết bị theo firmware version, site, trạng thái kết nối hoặc thuộc tính được index.

Ví dụ các câu hỏi vận hành:

- Thiết bị nào còn chạy firmware version cũ?
- Thiết bị nào thuộc site factory-01 và mất kết nối lâu?
- Thiết bị nào đang báo trạng thái calibration expired?
- Có bao nhiêu thiết bị thuộc nhóm cần update?

Thing attributes và Shadow data có thể được index theo cấu hình. Không index mọi field nếu không cần; cần cân nhắc giới hạn, chi phí và dữ liệu nhạy cảm.

Fleet indexing giúp tìm và phân nhóm thiết bị, còn Jobs dùng nhóm đó để triển khai operation. Kết hợp hai khả năng giúp tạo vòng lặp discover → target → update → verify.

## 23. AWS IoT Device Defender: Audit và Detect

AWS IoT Device Defender cung cấp các khả năng kiểm tra cấu hình bảo mật và theo dõi hành vi thiết bị.

### Audit

Audit kiểm tra cấu hình account/device theo các best practices, ví dụ:

- Nhiều thiết bị dùng chung identity/certificate.
- Policy quá rộng cho phép một thiết bị truy cập topic của thiết bị khác.
- Certificate hết hạn hoặc đã bị revoke nhưng vẫn active.
- Cấu hình có thể làm tăng nguy cơ truy cập trái phép.

Audit có thể chạy on-demand hoặc theo lịch. Kết quả có severity và finding để đội vận hành khắc phục.

### Detect và trạng thái availability

Detect sử dụng cloud-side metrics từ AWS IoT và device-side metrics từ agent/SDK để phát hiện hành vi bất thường như traffic tăng đột biến, kết nối tới endpoint lạ hoặc số port lắng nghe thay đổi.

**Lưu ý availability hiện hành:** AWS thông báo AWS IoT Device Defender Detect không còn mở cho khách hàng mới. Khách hàng hiện hữu đủ điều kiện có thể tiếp tục sử dụng theo điều kiện dịch vụ; AWS IoT Device Defender Audit vẫn khả dụng cho khách hàng mới. Vì vậy, kiến trúc mới không nên phụ thuộc Detect như một capability chắc chắn có thể bật trong mọi account.

Nếu account đã có quyền dùng Detect, security profile có thể theo dõi behavior theo Thing Group và gửi cảnh báo qua CloudWatch/SNS. Nếu không, xây dựng monitoring riêng bằng CloudWatch metrics/logs, Rules Engine, Kinesis và analytics phù hợp.

## 24. Quan sát telemetry và vận hành fleet bằng CloudWatch

AWS IoT Core có metrics trong CloudWatch cho message broker, rule engine, rule actions, authentication, provisioning, shadows, jobs và các thành phần khác. Dịch vụ phát metric theo chu kỳ, thường là mỗi phút.

Nhóm metric cần quan sát:

| Nhóm | Metric hoặc tín hiệu | Câu hỏi vận hành |
|---|---|---|
| Kết nối | Connect.Success, Connect.AuthError, Connect.Throttle, Connection.AuthNError | Thiết bị có kết nối được không; authentication hoặc authorization có lỗi không? |
| Message broker | PublishIn.Success, PublishIn.AuthError, PublishIn.Throttle, PublishOut.Success, PublishOut.Throttle | Message có được nhận/phân phối hay bị từ chối, throttling? |
| Persistent sessions | Queued.Success, Queued.Throttle | Message QoS 1 chờ thiết bị reconnect có được lưu không? |
| Rules | TopicMatch, RulesExecuted, RuleExecutionThrottled, ParseError, RuleNotFound | Rule có match, chạy và xử lý payload đúng không? |
| Rule actions | Success, Failure, ErrorActionSuccess, ErrorActionFailure | Backend action hoặc error action có lỗi không? |
| Shadow | GetThingShadow.Accepted, UpdateThingShadow.Accepted | Đọc và cập nhật Shadow có thành công không? |
| Jobs | QueuedJobExecutionCount, InProgressJobExecutionCount, FailedJobExecutionCount | OTA rollout có bị tồn đọng hoặc thất bại không? |
| Provisioning | ProvisionThing.Success, ProvisionThing.ClientError, ProvisionThing.ServerError, RegisterThingFailed | Onboarding thiết bị có lỗi không? |

Rule action metrics dùng dimensions RuleName và ActionType. Connection.AuthNError là lỗi xác thực ở lớp kết nối và có thể bao gồm cả hoạt động dò quét từ nguồn Internet bên ngoài, còn Connect.AuthError là lỗi authorization của message broker. Tên metric và dimension có thể khác theo API, protocol và loại resource; kiểm tra danh sách AWS IoT metrics hiện hành trước khi tạo alarm.

### Alarm gợi ý

- Connection.AuthNError hoặc Connect.AuthError tăng nhanh; đối chiếu source IP và log reason để phân biệt thiết bị thật với hoạt động dò quét.
- Connect.Throttle hoặc PublishIn/PublishOut.Throttle tăng bất thường so với baseline.
- Publish throttling hoặc message quota gần chạm giới hạn.
- Rule action failure tăng hoặc ErrorActionSuccess giảm.
- Shadow rejected update tăng.
- Job execution failure vượt ngưỡng rollout.
- Provisioning failure tăng sau khi phát hành template mới.

## 25. AWS IoT Core V2 logging

CloudWatch metrics cho biết xu hướng và số lượng; CloudWatch Logs giúp điều tra sự kiện cụ thể. AWS IoT Core V2 logging hỗ trợ ba cấp cấu hình:

- **Account-level:** mức mặc định cho toàn account.
- **Event-level:** tùy chỉnh theo loại sự kiện như authentication/authorization.
- **Resource-specific:** override theo Thing Group, source IP, client ID hoặc principal ID.

Event-level và resource-specific logging là khả năng của V2 logging. Nếu account đang dùng logging V1, cần thực hiện migration sang V2 trước khi dùng các cấu hình chi tiết này.

Các log level:

| Level | Nội dung |
|---|---|
| ERROR | Operation thất bại, ví dụ certificate hết hạn |
| WARN | Nguy cơ hoặc tình huống có thể gây không nhất quán |
| INFO | Luồng hoạt động mức cao, ví dụ client subscribe thành công |
| DEBUG | Chi tiết phục vụ điều tra, ví dụ Rules Engine bắt đầu thực thi |
| DISABLED | Tắt log cho phạm vi cấu hình |

Để bật logging, cần IAM role cho phép AWS IoT ghi vào CloudWatch Logs. Người có quyền đọc CloudWatch Logs có thể nhìn thấy thông tin debug liên quan thiết bị, vì vậy cần giới hạn quyền log access.

### Chiến lược log

1. Bắt đầu với INFO hoặc mức phù hợp trong giai đoạn kiểm thử.
2. Chỉ bật DEBUG cho resource hoặc event cần điều tra.
3. Sau khi xác định nguyên nhân, giảm về WARN/ERROR.
4. Đặt retention policy cho log group.
5. Không log payload nhạy cảm nếu không cần.
6. Theo dõi CloudWatch Logs ingestion cost.

Nếu chạy load test lớn, log quá chi tiết có thể tạo lượng ingest lớn và ảnh hưởng chi phí/throttling. Dùng resource-specific logging để thu hẹp phạm vi.

## 26. Phân biệt service logs, telemetry và device-side logs

Ba loại dữ liệu này trả lời ba câu hỏi khác nhau:

| Loại dữ liệu | Ví dụ | Nơi lưu/quan sát |
|---|---|---|
| Service logs | Authentication failure, rule action failure, disconnect reason | CloudWatch Logs từ AWS IoT Core |
| Telemetry | Temperature, vibration, battery, pressure | S3, Kinesis, SiteWise hoặc kho time-series phù hợp với workload |
| Device-side logs | Firmware crash, sensor driver error, local queue full | Edge log collector, Greengrass log manager hoặc upload pipeline riêng |

Không dùng service log thay telemetry. AWS IoT Core log có thể cho biết message publish thất bại nhưng không phải nơi lưu lịch sử mọi phép đo của sensor. Ngược lại, telemetry có thể cho thấy nhiệt độ tăng nhưng không giải thích được tại sao certificate authentication bị từ chối.

## 27. Security monitoring và phát hiện hành vi bất thường

Ngay cả khi thiết bị đã xác thực bằng certificate, credential có thể bị đánh cắp hoặc firmware có lỗ hổng. Hãy xây dựng baseline cho từng loại thiết bị và Thing Group.

Các tín hiệu có thể giám sát:

- Số lần connect/disconnect mỗi giờ.
- Authentication/authorization failures.
- Message rate và payload size.
- Tỷ lệ publish/subscribe theo topic.
- IP/source network thay đổi bất thường.
- Device clock lệch hoặc certificate sắp hết hạn.
- Số TCP/UDP port đang lắng nghe ở edge.
- Firmware version không nằm trong danh sách approved.
- Thiết bị gửi dữ liệu ngoài lịch hoạt động hoặc ngoài phạm vi địa lý dự kiến.

Với Detect không khả dụng cho khách hàng mới, có thể:

1. Đẩy event/security metrics qua Rules Engine.
2. Ghi metric vào CloudWatch hoặc stream vào Kinesis.
3. Tính baseline theo device type/Thing Group.
4. Tạo CloudWatch alarms cho threshold rõ ràng.
5. Dùng Lambda hoặc stream processor để phát hiện pattern phức tạp.
6. Gửi finding tới SNS/SQS/ticketing workflow.
7. Dùng mitigation workflow để deactivate certificate, thu hẹp policy hoặc tạo IoT Job điều tra.

Không tự động deactivate certificate chỉ từ một anomaly đơn lẻ nếu có nguy cơ false positive làm dừng thiết bị quan trọng. Với hành động có ảnh hưởng lớn, dùng mức độ severity, xác nhận bổ sung và quy trình approval.

## 28. Mitigation và incident response

Khi phát hiện thiết bị có dấu hiệu compromise:

1. Xác định Thing, certificate, principal, client ID và source IP.
2. Kiểm tra log kết nối, policy authorization và topic activity.
3. So sánh với baseline của Thing Group.
4. Cô lập thiết bị tại mạng edge nếu có thể.
5. Deactivate/revoke certificate hoặc thu hẹp policy khi cần.
6. Dừng hoặc hủy Jobs đang triển khai tới thiết bị bị ảnh hưởng.
7. Bảo toàn log và telemetry để điều tra.
8. Đánh giá các thiết bị dùng chung firmware, claim credential hoặc cấu hình tương tự.
9. Cấp lại credential và triển khai firmware đã sửa sau khi xác nhận an toàn.
10. Ghi lại nguyên nhân, thời gian phát hiện, thời gian cô lập và phạm vi ảnh hưởng.

Mitigation có thể được tự động hóa qua AWS IoT Device Defender Audit/Detect nếu capability phù hợp với account, hoặc qua Lambda/Step Functions và các API IoT. Cần thử nghiệm hành động thu hồi và khôi phục trên staging fleet trước khi dùng production.

## 29. Bảo vệ dữ liệu telemetry

Telemetry có thể tiết lộ hoạt động nhà máy, vị trí thiết bị, sản lượng hoặc hành vi người dùng. Cần bảo vệ cả khi truyền, lưu trữ và truy cập:

- TLS cho kết nối thiết bị tới AWS IoT.
- SSE-S3 hoặc SSE-KMS cho dữ liệu lưu ở S3 theo yêu cầu.
- KMS key policy giới hạn principal được decrypt.
- IAM role của Rule Action chỉ ghi đúng destination.
- S3 bucket policy chặn public access và giới hạn prefix.
- Lake Formation hoặc catalog permissions cho phân tích dữ liệu.
- CloudTrail để audit thay đổi IAM, IoT policy, certificate và resource.
- Data retention và lifecycle theo mục đích sử dụng.
- Mask hoặc loại bỏ PII trước khi đưa vào analytics.

Không đưa dữ liệu bí mật vào MQTT topic name hoặc log payload. Nếu telemetry cần chứa định danh người dùng, dùng token/pseudonymous identifier và tách mapping nhạy cảm sang kho có quyền hạn chế.

## 30. Quản lý quota, throughput và chi phí

IoT fleet có thể tạo lưu lượng lớn theo số lượng thiết bị, tần suất publish và kích thước payload. Chi phí có thể đến từ kết nối/message, Rules Engine, các action downstream, S3, Kinesis/Firehose, Lambda, CloudWatch Logs và lưu trữ.

### Tối ưu ingestion

- Chọn sampling interval theo nhu cầu nghiệp vụ.
- Gộp nhiều measurement vào một payload nếu phù hợp.
- Dùng QoS 0 cho dữ liệu có thể mất và QoS 1 cho event cần xác nhận.
- Giới hạn payload và tránh gửi field không đổi liên tục.
- Buffer ở edge khi mạng gián đoạn.
- Dùng Kinesis/Firehose để gom batch trước khi lưu S3.
- Tách telemetry high-volume khỏi command/control topic.

### Tối ưu backend

- Chỉ dùng Rule SQL lấy field cần thiết.
- Filter sớm trước khi gọi Lambda hoặc ghi database.
- Dùng S3 lifecycle cho raw data.
- Compact file nhỏ trong data lake.
- Chọn retention CloudWatch Logs hợp lý.
- Đặt alarm cho rule throttling, Lambda errors và queue backlog.
- Theo dõi chi phí theo site, Thing Group hoặc data domain.

Không giảm telemetry frequency nếu làm mất khả năng phát hiện sự cố hoặc vi phạm yêu cầu an toàn. Tối ưu dựa trên giá trị thông tin và SLO, không chỉ dựa trên số message.

## 31. Ví dụ end-to-end: giám sát nhiệt độ dây chuyền sản xuất

Một nhà máy có 2.000 cảm biến nhiệt độ và độ rung trên nhiều dây chuyền. Mỗi thiết bị gửi telemetry mỗi 30 giây, nhận cấu hình từ cloud và cần được cập nhật firmware theo từng đợt.

### Thiết kế

1. Mỗi sensor có Thing và X.509 certificate riêng.
2. Fleet Provisioning tạo Thing/certificate/policy khi thiết bị onboarding.
3. IoT policy chỉ cho phép connect bằng client ID của Thing, publish telemetry và subscribe command riêng.
4. Thiết bị publish JSON telemetry lên factory/{thingName}/telemetry.
5. IoT Rule lọc nhiệt độ vượt ngưỡng và chuyển alarm event tới Lambda/SNS.
6. Firehose lưu telemetry batch vào S3 raw data lake.
7. Glue Data Catalog mô tả dữ liệu curated; Athena truy vấn lịch sử.
8. Device Shadow lưu desired configuration như sampling interval và reported firmware/status.
9. Greengrass gateway thực hiện lọc và buffering cục bộ khi WAN mất kết nối.
10. IoT Jobs triển khai firmware theo Thing Group canary trước, rồi mới rollout toàn nhà máy.
11. CloudWatch metrics/logs theo dõi connection, authentication, rule actions và backend.
12. Device Defender Audit kiểm tra policy/certificate; nếu account không có Detect, dùng metrics và alarm riêng.

### Sơ đồ

~~~mermaid
flowchart TB
    A[Temperature / vibration sensors] --> B[Edge gateway / Greengrass]
    B -->|MQTT TLS| C[AWS IoT Core]
    C --> D[Thing Registry / X.509 / IoT Policies]
    C --> E[Device Shadow]
    C --> F[Rules Engine]
    F --> G[Lambda / SNS alarm]
    F --> H[Firehose]
    H --> I[S3 raw and curated lake]
    I --> J[Glue Catalog / Athena]
    C --> K[CloudWatch metrics and logs]
    L[IoT Jobs] --> B
    M[Device Defender Audit] --> D
~~~

### Vận hành

- Nếu authentication error tăng, kiểm tra certificate expiry, clock và policy.
- Nếu rule action failure tăng, kiểm tra IAM role, quota và downstream service.
- Nếu nhiệt độ vượt ngưỡng, gửi alarm tới đội vận hành nhưng vẫn lưu telemetry đầy đủ.
- Nếu firmware canary có tỷ lệ lỗi cao, abort job trước khi rollout rộng.
- Nếu WAN mất kết nối, edge tiếp tục local control và buffer telemetry theo giới hạn dung lượng.

## 32. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| TLS handshake thất bại | Clock sai, CA/server certificate không được tin cậy hoặc client certificate lỗi | Đồng bộ NTP, xác minh server hostname/CA và certificate validity |
| MQTT connect bị từ chối | Certificate inactive, policy thiếu iot:Connect hoặc client ID sai | Kiểm tra certificate, Thing attachment, policy và client ID |
| Publish bị AccessDenied | Topic ARN không khớp hoặc policy không cho iot:Publish | Kiểm tra topic thực tế và policy variable |
| Subscribe thành công nhưng không nhận message | Thiếu iot:Receive hoặc publisher dùng topic khác | Kiểm tra cả Subscribe topicfilter và Receive topic |
| Message bị trùng | QoS 1 retry hoặc reconnect | Dùng eventId/sequence và xử lý idempotent |
| Thiết bị offline không nhận command | Session hết hạn, QoS/queue limit hoặc command không được lưu | Dùng Shadow cho desired state; thiết kế retry và expiry |
| Shadow update bị rejected | Version cũ hoặc policy thiếu quyền | Get shadow mới, kiểm tra version và topic permission |
| Rule không match | Topic filter hoặc SQL expression sai | Test topic, payload và Rule SQL |
| Rule action thất bại | IAM role thiếu quyền hoặc dịch vụ đích throttling | Xem Rule metrics/logs, role policy và quota |
| CloudWatch không có IoT logs | Chưa bật logging V2 hoặc logging role sai | Kiểm tra V2 options, trust policy và log group permission |
| Job rollout bị kẹt | Device offline, timeout hoặc firmware installer không báo trạng thái | Kiểm tra job execution, device logs và retry policy |
| Greengrass component không deploy | Nucleus, dependency, artifact hoặc IAM role lỗi | Kiểm tra deployment status và component logs |
| Telemetry đến trễ | Edge buffer hoặc mạng không ổn định | Dùng eventTime/sequence và xử lý late arrival |
| Chi phí log tăng mạnh | DEBUG bật rộng hoặc retention không giới hạn | Thu hẹp resource-specific logging và đặt retention |

## 33. Checklist production

- [ ] Mỗi thiết bị có identity riêng và certificate/private key được bảo vệ.
- [ ] Thiết bị xác minh server certificate và đồng bộ clock.
- [ ] Certificate có quy trình rotation, revoke và expiration monitoring.
- [ ] Fleet Provisioning template và claim policy có phạm vi tối thiểu.
- [ ] IoT policy giới hạn client ID, topic publish, subscribe và receive.
- [ ] Thing Registry và Thing Groups phản ánh site, model và môi trường.
- [ ] Topic convention và telemetry schema được version hóa.
- [ ] QoS 0/1 được chọn theo mức độ quan trọng; consumer xử lý duplicate.
- [ ] Shadow desired/reported state có owner và quyền update rõ ràng.
- [ ] Rule SQL filter sớm và Rule Action dùng IAM role least privilege.
- [ ] Error action và cơ chế replay được cấu hình cho luồng quan trọng.
- [ ] Backend có buffer/queue phù hợp với throughput và burst.
- [ ] S3, Kinesis, Lambda, DynamoDB, SiteWise hoặc OpenSearch được chọn theo use case.
- [ ] CloudWatch metrics có dashboard và alarms cho connection, rules, jobs và backend.
- [ ] CloudWatch IoT V2 logging có log level và retention phù hợp.
- [ ] Device Defender Audit được lập lịch; Detect availability đã được xác nhận theo account.
- [ ] Greengrass edge behavior khi offline đã được kiểm thử.
- [ ] OTA Jobs có canary rollout, timeout, abort và rollback plan.
- [ ] Dữ liệu telemetry được mã hóa, retention và access control phù hợp.
- [ ] Đã kiểm thử certificate compromise, network outage, duplicate message và backend failure.
- [ ] Chi phí message, rule actions, logs, storage và downstream services được theo dõi.

## 34. Ghi nhớ

Một hệ thống IoT an toàn bắt đầu bằng identity riêng cho từng thiết bị, X.509 mutual TLS, xác minh server certificate và IoT policy least privilege. Fleet Provisioning tự động hóa onboarding; Device Shadows đồng bộ desired/reported state; MQTT cung cấp publish/subscribe với QoS 0 và 1; Jobs quản lý update và remote operation.

Rules Engine chuyển telemetry sang backend AWS như S3, Kinesis, Firehose, Lambda, DynamoDB, SQS/SNS, OpenSearch, CloudWatch và IoT SiteWise. Greengrass đưa xử lý tới edge để giảm latency và tiếp tục hoạt động cục bộ khi mạng gián đoạn.

CloudWatch metrics và V2 logs giúp quan sát hoạt động dịch vụ; telemetry và device-side logs cần pipeline lưu trữ/giám sát riêng. Device Defender Audit vẫn khả dụng, còn Detect không mở cho khách hàng mới. Thiết kế production cần kết hợp IAM, KMS, certificate lifecycle, policy scope, fleet rollout, error handling, retention và cost monitoring để kiểm soát rủi ro từ thiết bị tới backend.

## Tài liệu tham khảo

- [AWS IoT Core Security Best Practices](https://docs.aws.amazon.com/iot/latest/developerguide/security-best-practices.html)
- [AWS IoT Device Advisor](https://docs.aws.amazon.com/iot/latest/developerguide/device-advisor.html)
- [AWS IoT Device Advisor Test Cases](https://docs.aws.amazon.com/iot/latest/developerguide/device-advisor-tests.html)
- [Authentication and Authorization for AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-authentication.html)
- [AWS IoT Policies](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policies.html)
- [AWS IoT Policy Variables](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policy-variables.html)
- [Registering a Client Certificate](https://docs.aws.amazon.com/iot/latest/developerguide/register-CA-cert.html)
- [Fleet Provisioning](https://docs.aws.amazon.com/iot/latest/developerguide/iot-provision.html)
- [Provisioning Templates](https://docs.aws.amazon.com/iot/latest/developerguide/provision-template.html)
- [Fleet Provisioning without Device Certificates](https://docs.aws.amazon.com/iot/latest/developerguide/provision-wo-cert.html)
- [MQTT Protocol and QoS](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [AWS IoT Core Endpoints and Quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [Device Shadow Service](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [Device Shadow Documents](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html)
- [Device Shadow MQTT Topics](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html)
- [Rules for AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [AWS IoT Rule Actions](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rule-actions.html)
- [AWS IoT Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Jobs Key Concepts](https://docs.aws.amazon.com/iot/latest/developerguide/key-concepts-jobs.html)
- [AWS IoT Greengrass V2 Developer Guide](https://docs.aws.amazon.com/greengrass/v2/developerguide/what-is-iot-greengrass.html)
- [AWS IoT Greengrass Components](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-components.html)
- [AWS IoT Metrics and Dimensions](https://docs.aws.amazon.com/iot/latest/developerguide/metrics_dimensions.html)
- [Configure AWS IoT V2 Logging](https://docs.aws.amazon.com/iot/latest/developerguide/configure-logging.html)
- [Security Monitoring for IoT Fleets](https://docs.aws.amazon.com/iot/latest/developerguide/security-monitoring.html)
- [AWS IoT Device Defender Audit](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/device-defender-audit.html)
- [AWS IoT Device Defender Detect Availability](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/device-defender-detect.html)
- [AWS IoT Device Defender Detect Metrics](https://docs.aws.amazon.com/iot-device-defender/latest/devguide/detect-concepts.html)
- [AWS IoT Device Management Fleet Indexing](https://docs.aws.amazon.com/iot/latest/developerguide/iot-indexing.html)
