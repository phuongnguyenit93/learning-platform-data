# AWS IoT Core và kiến trúc kết nối thiết bị

Một hệ thống IoT thường có hàng trăm đến hàng triệu thiết bị ở nhà máy, cửa hàng, phương tiện, tòa nhà hoặc ngoài hiện trường. Mỗi thiết bị cần gửi telemetry, nhận lệnh, cập nhật cấu hình và duy trì danh tính riêng. Kết nối phải hoạt động qua mạng không ổn định, thiết bị có tài nguyên hạn chế và đội vận hành cần quản lý vòng đời thiết bị trong nhiều năm. Nếu mỗi ứng dụng tự xây message broker, xác thực và cơ chế quản lý thiết bị, chi phí vận hành và rủi ro bảo mật sẽ tăng nhanh.

AWS IoT Core cung cấp nền tảng cloud để kết nối thiết bị với ứng dụng và các dịch vụ AWS. Dịch vụ có device gateway để tiếp nhận kết nối bảo mật, message broker để publish/subscribe, rules engine để định tuyến dữ liệu, Device Shadow để đồng bộ trạng thái và các khả năng quản lý fleet. Thiết bị có thể dùng MQTT, MQTT over WebSocket Secure (WSS) hoặc HTTPS theo kiểu giao tiếp và cơ chế xác thực phù hợp.

Một kiến trúc IoT hoàn chỉnh còn phải giải quyết việc đăng ký thiết bị, cấp và thu hồi certificate, giới hạn quyền theo từng thiết bị, xử lý mất kết nối, quản lý firmware, lưu trữ telemetry và giám sát sức khỏe fleet. Với nhu cầu xử lý tại biên, AWS IoT Greengrass bổ sung runtime để chạy component, lọc dữ liệu và xử lý cục bộ trên gateway hoặc edge device. AWS IoT Core và Greengrass phục vụ hai phần bổ sung của cùng một hệ thống: kết nối và quản lý ở cloud, cùng xử lý tại nơi dữ liệu được tạo ra.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: khám phá dịch vụ AWS và lựa chọn kiến trúc an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Trọng tâm là thiết kế kết nối thiết bị với AWS IoT Core, tổ chức danh tính và topic, định tuyến telemetry, đồng bộ trạng thái, quản lý fleet và kết hợp edge computing khi cần.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của AWS IoT Core và các thành phần device gateway, message broker, rules engine, registry và Device Shadow.
- Phân biệt Thing Registry, X.509 certificate, AWS IoT policy và IAM policy.
- Chọn MQTT, MQTT over WSS hoặc HTTPS theo nhu cầu giao tiếp thiết bị.
- Thiết kế endpoint, TLS, port, SNI và quy trình xác thực thiết bị.
- Tổ chức MQTT topic, QoS, persistent session, retained message và Last Will and Testament.
- Cấp phát thiết bị bằng quy trình đăng ký ban đầu hoặc Fleet Provisioning.
- Dùng Rules Engine để lọc, chuyển đổi và định tuyến telemetry tới dịch vụ AWS.
- Dùng Device Shadow để đồng bộ desired state và reported state khi thiết bị online/offline.
- Quản lý firmware và tác vụ từ xa bằng AWS IoT Jobs.
- Kết hợp AWS IoT Greengrass cho xử lý cục bộ và hoạt động khi mất kết nối cloud.
- Bảo vệ fleet bằng certificate lifecycle, least privilege, logging và Device Defender.
- Ước tính chi phí và xây dựng quy trình vận hành hệ thống IoT.

## 2. AWS IoT Core là gì?

### 2.1. Nền tảng kết nối thiết bị

AWS IoT Core là dịch vụ managed giúp thiết bị và ứng dụng giao tiếp an toàn với AWS Cloud. Thiết bị có thể gửi dữ liệu tới cloud, nhận thông điệp từ ứng dụng hoặc thiết bị khác, đồng thời tương tác với các dịch vụ AWS thông qua rules engine và API.

Các khả năng chính:

- Kết nối thiết bị qua MQTT, MQTT over WSS hoặc HTTPS theo cơ chế xác thực được hỗ trợ.
- Xác thực thiết bị bằng X.509 client certificate, custom authorizer hoặc phương thức được hỗ trợ khác.
- Phân quyền publish, subscribe, receive và connect bằng AWS IoT Core policies.
- Quản lý Thing Registry, Thing Groups và metadata của thiết bị.
- Lưu trạng thái thiết bị bằng Device Shadow.
- Định tuyến message tới S3, Lambda, SQS, SNS, Kinesis, DynamoDB, OpenSearch, CloudWatch và các đích được hỗ trợ.
- Cấp phát thiết bị theo quy mô bằng Fleet Provisioning.
- Quản lý firmware và tác vụ từ xa bằng AWS IoT Jobs.
- Tìm kiếm và tổng hợp thông tin fleet bằng Fleet Indexing.
- Bảo vệ fleet bằng AWS IoT Device Defender.

AWS IoT Core quản lý phần kết nối và message broker. Dịch vụ không thay thế firmware, hệ điều hành, ứng dụng điều khiển, thiết kế mạng tại nhà máy hoặc hệ thống lưu trữ phân tích cuối cùng. Các phần đó cần được xây dựng hoặc chọn dịch vụ riêng.

### 2.2. Các thành phần của AWS IoT Core

| Thành phần | Vai trò |
|---|---|
| Device Gateway | Tiếp nhận kết nối bảo mật từ thiết bị |
| Message Broker | Nhận publish và phân phối message tới subscriber |
| Rules Engine | Lọc, biến đổi và định tuyến message tới dịch vụ khác |
| Thing Registry | Lưu danh tính logic, loại và thuộc tính của thiết bị |
| Device Shadow | Lưu trạng thái desired/reported để đồng bộ khi thiết bị offline |
| Device Management | Provisioning, Jobs, Fleet Indexing và quản lý fleet |
| Device Defender | Kiểm tra cấu hình và phát hiện hành vi bất thường của fleet |

### 2.3. Control plane và data plane

Control plane quản lý tài nguyên và cấu hình như Thing, Thing Group, certificate, policy, rule, job và provisioning template. Các thao tác này thường được gọi bằng AWS Console, AWS CLI, SDK hoặc API với IAM permission.

Data plane xử lý giao tiếp thiết bị, ví dụ MQTT publish/subscribe, Device Shadow và một số API dành cho thiết bị. Thiết bị thường xác thực bằng X.509 certificate và được cấp quyền bằng AWS IoT Core policy.

Phân biệt hai lớp giúp thiết kế quyền đúng:

- Người vận hành cần IAM permission để tạo, cập nhật hoặc xóa tài nguyên IoT.
- Thiết bị cần certificate và IoT policy để kết nối, publish hoặc subscribe.
- Backend service có thể dùng IAM role để gọi API AWS hoặc giao tiếp với IoT data plane theo cơ chế được hỗ trợ.

IAM policy và AWS IoT Core policy là hai loại policy khác nhau. Không gắn IAM policy vào certificate như cách cấp quyền cho một role; certificate của thiết bị được liên kết với IoT policy.

## 3. Kiến trúc kết nối thiết bị

### 3.1. Luồng dữ liệu tổng quát

Một kiến trúc IoT phổ biến có các bước:

1. Thiết bị khởi động và đọc certificate/private key được bảo vệ trong thiết bị.
2. Thiết bị kết nối tới endpoint AWS IoT Core của account và Region.
3. Device Gateway xác thực kết nối và kiểm tra quyền theo IoT policy.
4. Thiết bị publish telemetry lên MQTT topic.
5. Message Broker phân phối message cho subscriber và Rules Engine.
6. Rules Engine lọc hoặc chuyển đổi message rồi gửi tới dịch vụ lưu trữ/xử lý.
7. Ứng dụng backend truy vấn dữ liệu, hiển thị dashboard hoặc phát lệnh.
8. Lệnh có thể được gửi qua MQTT topic hoặc cập nhật Device Shadow.
9. Thiết bị nhận lệnh, thực thi và publish trạng thái mới.

~~~mermaid
flowchart LR
    D[IoT device] -->|MQTT / TLS| G[Device Gateway]
    G --> B[Message Broker]
    B --> R[Rules Engine]
    B <--> S[Device Shadow]
    R --> K[Kinesis / Firehose]
    R --> L[Lambda]
    R --> Q[SQS / SNS]
    K --> T[S3 data lake]
    L --> DB[DynamoDB / application API]
    APP[Web / mobile / backend] --> S
    APP --> B
    M[Thing Registry / IoT policies] -. identity and authorization .-> G
    JOB[AWS IoT Jobs] --> B
~~~

Sơ đồ thể hiện các luồng logic. Trong triển khai thực tế, Rules Engine có thể có nhiều rule, đích đến có thể nằm trong nhiều account hoặc VPC và ứng dụng có thể sử dụng API thay vì subscribe trực tiếp.

### 3.2. Device Gateway

Device Gateway là điểm kết nối của thiết bị với AWS IoT Core. Gateway hỗ trợ các giao thức được dịch vụ công bố, xử lý kết nối bảo mật và xác thực thiết bị. Mỗi account trong từng Region có endpoint IoT riêng cho các mục đích data plane, credential provider hoặc Jobs.

Thiết bị nên lưu endpoint hostname sau khi được cấp. Có thể lấy endpoint bằng AWS CLI:

~~~bash
aws iot describe-endpoint --endpoint-type iot:Data-ATS
~~~

Kết quả trả về một hostname dạng:

~~~text
xxxxxxxxxxxxxx-ats.iot.ap-southeast-1.amazonaws.com
~~~

Endpoint data ATS dùng chứng chỉ server do Amazon Trust Services ký. Endpoint của account không thay đổi sau khi AWS IoT Core tạo; thiết bị có thể cache hostname và không cần gọi DescribeEndpoint mỗi lần kết nối.

Không hard-code endpoint của account khác hoặc Region khác vào firmware dùng chung. Khi triển khai đa Region, cần cấu hình endpoint theo môi trường và chiến lược failover đã kiểm thử.

### 3.3. Message Broker

Message Broker nhận message từ publisher và chuyển tới subscriber dựa trên MQTT topic hoặc cơ chế messaging tương ứng. Thiết bị có thể gửi telemetry, sự kiện trạng thái hoặc nhận command mà không cần biết địa chỉ mạng của từng consumer.

Broker giúp tách rời producer và consumer:

- Thiết bị chỉ cần publish lên topic đã thỏa thuận.
- Dashboard hoặc backend subscribe topic phù hợp.
- Rules Engine có thể xử lý cùng message để lưu hoặc chuyển tiếp.
- Nhiều consumer có thể nhận cùng một sự kiện theo quyền được cấp.

Message Broker không tự đảm bảo logic nghiệp vụ như lưu trữ lâu dài, transaction giữa nhiều dịch vụ hoặc xử lý đúng một lần cho toàn bộ hệ thống. Consumer cần thiết kế retry, deduplication và persistence theo yêu cầu.

### 3.4. Rules Engine

Rules Engine dùng câu lệnh SQL để lọc và chuyển đổi message theo topic, sau đó thực hiện action. Ví dụ, chỉ nhận telemetry có trường temperature hợp lệ, thêm metadata hoặc chuyển message tới S3, Kinesis Data Streams, Data Firehose, Lambda, DynamoDB, SQS, SNS, OpenSearch, CloudWatch hoặc AWS IoT SiteWise theo khả năng và Region hỗ trợ.

Một rule đơn giản:

~~~sql
SELECT
    deviceId,
    temperature,
    humidity,
    timestamp() AS receivedAt
FROM 'factory/+/+/telemetry'
WHERE temperature IS NOT NULL
~~~

Topic filter trong rule có thể dùng wildcard MQTT như dấu cộng để khớp một cấp topic. Rule có thể chọn trường, tạo trường dẫn xuất và lọc message trước khi gọi action.

Mỗi action thường cần IAM role cho phép AWS IoT thực hiện thao tác tới đích. Nếu role thiếu quyền, message vẫn có thể đến broker nhưng action của rule thất bại. Cần bật logging phù hợp và theo dõi lỗi rule.

### 3.5. Thing Registry

Thing Registry lưu biểu diễn logic của thiết bị, gọi là Thing. Thing có tên, loại và attributes như model, serial number, site, firmware channel hoặc business unit. Thing Group giúp tổ chức fleet theo site, model, môi trường hoặc nhóm triển khai.

Thing Registry không phải cơ chế xác thực duy nhất. Một Thing có thể được liên kết với X.509 certificate hoặc principal phù hợp; certificate xác thực kết nối, còn IoT policy quyết định thiết bị được phép làm gì.

Ví dụ:

| Thing | Attributes | Thing Group |
|---|---|---|
| pump-001 | model=pump-v2, site=hcm-01 | pumps-production |
| pump-002 | model=pump-v2, site=hcm-01 | pumps-production |
| meter-014 | model=meter-v1, site=dn-02 | meters-production |

Attributes giúp tìm kiếm và áp dụng policy theo thuộc tính. Không lưu private key, mật khẩu hoặc secret vào Thing attributes.

## 4. Giao thức và kết nối mạng

### 4.1. MQTT

MQTT là giao thức publish/subscribe nhẹ, phù hợp với thiết bị có băng thông, CPU, RAM hoặc nguồn điện hạn chế. AWS IoT Core hỗ trợ MQTT 3.1.1 và MQTT 5.0 theo các khác biệt được AWS tài liệu hóa.

Đặc điểm:

- Publisher gửi message lên topic.
- Subscriber đăng ký topic filter để nhận message.
- Broker phân phối message theo subscription và authorization.
- Client không cần duy trì kết nối trực tiếp với từng client khác.
- MQTT hỗ trợ QoS, retained message, persistent session và Last Will and Testament theo tính năng dịch vụ.

MQTT thường là lựa chọn phù hợp cho telemetry hai chiều, trạng thái thiết bị và command. Với dữ liệu lớn hoặc file firmware, nên dùng luồng upload/download riêng thay vì gửi toàn bộ payload qua message broker.

### 4.2. MQTT over WebSocket Secure

MQTT over WSS cho phép client dùng WebSocket bảo mật qua HTTPS/TLS. Đây là lựa chọn hữu ích cho web application hoặc môi trường mạng chỉ cho phép outbound HTTPS. Xác thực có thể dùng AWS Signature Version 4 hoặc cơ chế được hỗ trợ theo endpoint/domain configuration.

WSS không biến trình duyệt thành thiết bị có certificate riêng theo mặc định. Ứng dụng web thường xác thực người dùng ở backend hoặc dùng Cognito/IAM và cấp quyền kết nối phù hợp. Không nhúng AWS secret access key dài hạn vào JavaScript phía client.

### 4.3. HTTPS

HTTPS phù hợp với thiết bị chỉ cần publish dữ liệu hoặc gửi một request mà không cần giữ subscription hai chiều liên tục. AWS IoT Core hỗ trợ HTTPS publish theo các cơ chế xác thực như SigV4, X.509 hoặc custom authentication trong cấu hình được hỗ trợ.

HTTPS không cung cấp mô hình subscribe/push hai chiều như MQTT. Nếu thiết bị cần nhận command liên tục, MQTT hoặc WSS thường phù hợp hơn.

### 4.4. So sánh giao thức

| Tiêu chí | MQTT | MQTT over WSS | HTTPS |
|---|---|---|---|
| Mô hình | Publish/subscribe | Publish/subscribe qua WebSocket | Request/response, publish |
| Kết nối dài hạn | Có | Có | Không theo mô hình subscribe |
| Phù hợp | Thiết bị IoT, gateway | Web app, mạng ưu tiên HTTPS | Gửi dữ liệu theo request |
| Xác thực | X.509 hoặc cơ chế được hỗ trợ | SigV4, custom auth hoặc X.509 theo cấu hình | SigV4, X.509 hoặc custom auth |
| Hướng message | Hai chiều qua broker | Hai chiều qua broker | Chủ yếu publish lên IoT Core |

Chọn giao thức theo khả năng thiết bị, yêu cầu nhận lệnh, firewall, quản lý certificate và chi phí kết nối. Không cần giữ MQTT connection liên tục nếu thiết bị chỉ gửi một batch nhỏ mỗi ngày.

### 4.5. TLS, SNI và ALPN

AWS IoT Core dùng TLS 1.2 và TLS 1.3 để bảo vệ kết nối. Thiết bị cần xác minh server certificate và hostname để tránh kết nối tới máy chủ giả mạo. AWS IoT yêu cầu SNI trong các trường hợp kết nối theo endpoint/domain configuration, bao gồm các tính năng như custom domain và VPC endpoint.

Với default endpoint:

| Giao thức | Xác thực | Port thường dùng | Ghi chú |
|---|---|---:|---|
| MQTT | X.509 client certificate | 8883 | MQTT over TLS |
| MQTT | X.509 client certificate | 443 | Cần ALPN x-amzn-mqtt-ca |
| MQTT over WSS | SigV4 hoặc cơ chế hỗ trợ | 443 | Dùng WebSocket Secure |
| HTTPS publish | SigV4 | 443 | HTTP API |
| HTTPS publish | X.509 client certificate | 8443 | TLS mutual authentication |
| HTTPS publish | X.509 client certificate | 443 | Cần ALPN x-amzn-http-ca |

Tổ chức cần kiểm tra đúng protocol, port, authentication và ALPN combination. Mở TCP 443 không tự động bảo đảm mọi kiểu kết nối hoạt động nếu thiết bị thiếu SNI, ALPN hoặc certificate chain phù hợp.

### 4.6. Network design

Thiết bị thường tạo outbound connection tới AWS IoT endpoint. Trong mạng nhà máy:

- Cho phép DNS resolve endpoint.
- Cho phép outbound TCP port cần thiết theo giao thức.
- Đồng bộ thời gian bằng NTP để certificate validation hoạt động.
- Kiểm tra firewall/proxy không làm TLS interception sai cách.
- Đảm bảo MTU và đường truyền không gây phân mảnh hoặc timeout.
- Có cơ chế retry với backoff để tránh hàng loạt thiết bị reconnect cùng lúc.
- Dùng Direct Connect hoặc Site-to-Site VPN khi hệ thống cần đường truyền riêng tới AWS.

Thiết bị không cần inbound public port để nhận MQTT message; kết nối đã thiết lập với broker cho phép nhận dữ liệu theo subscription. Nếu dùng proxy, cần kiểm tra hỗ trợ MQTT/WSS và certificate handling.

## 5. MQTT topic và semantics của message

### 5.1. Thiết kế topic namespace

Topic là hợp đồng giao tiếp giữa firmware, backend và Rules Engine. Một cấu trúc có thể dùng:

~~~text
factory/{siteId}/{deviceId}/telemetry
factory/{siteId}/{deviceId}/status
factory/{siteId}/{deviceId}/events
factory/{siteId}/{deviceId}/commands
factory/{siteId}/{deviceId}/acks
~~~

Ví dụ:

~~~text
factory/hcm-01/pump-001/telemetry
factory/hcm-01/pump-001/status
factory/hcm-01/pump-001/commands
~~~

Quy tắc đặt tên:

- Dùng tên nhất quán và có cấu trúc.
- Tránh nhúng thông tin bí mật hoặc PII vào topic.
- Phân biệt telemetry, event, command và acknowledgement.
- Định nghĩa rõ publisher/subscriber của từng topic.
- Quy định schema, timestamp, unit và version của payload.
- Có chiến lược versioning khi thay đổi cấu trúc message.

### 5.2. Wildcard trong MQTT subscription

MQTT hỗ trợ:

- Dấu cộng (+): khớp một cấp topic.
- Dấu thăng (#): khớp nhiều cấp còn lại và phải nằm ở cuối topic filter.

Ví dụ:

~~~text
factory/hcm-01/+/telemetry
factory/+/+/status
factory/#
~~~

Wildcard giúp backend subscribe nhiều thiết bị. Tuy nhiên, không cấp quyền subscribe toàn bộ factory topic cho mọi thiết bị nếu mỗi thiết bị chỉ nên đọc command của chính nó.

### 5.3. QoS 0 và QoS 1

AWS IoT Core hỗ trợ MQTT QoS 0 và QoS 1; không hỗ trợ QoS 2.

| QoS | Ý nghĩa | Khi phù hợp |
|---|---|---|
| 0 | Giao message best-effort, không có xác nhận QoS 1 | Telemetry tần suất cao, có thể bỏ lỡ một số mẫu |
| 1 | Ít nhất một lần; publisher chờ PUBACK và có thể gửi lại | Command hoặc event cần xác nhận giao tới broker |

QoS 1 có thể tạo duplicate vì message được gửi lại khi acknowledgement không đến đúng hạn. Consumer nên xử lý idempotent bằng message ID, sequence number hoặc event key. QoS 1 không đồng nghĩa message đã được lưu bền vững trong database hoặc nghiệp vụ đã hoàn tất.

### 5.4. Persistent sessions

Persistent session giữ subscription và một số message QoS 1 chưa được xác nhận trong lúc client offline theo giới hạn dịch vụ. Khi thiết bị reconnect với cùng session, subscription được khôi phục và message đang chờ có thể được gửi lại.

MQTT 3.1.1 dùng cờ cleanSession; MQTT 5 dùng Clean Start và Session Expiry Interval. Persistent session hữu ích cho thiết bị di động hoặc kết nối chập chờn. Tuy nhiên, message được lưu có giới hạn và tốc độ gửi lại bị giới hạn theo dịch vụ; không nên dùng session như một kho lưu trữ vô hạn.

### 5.5. Retained messages

Retained message lưu lại message cuối cùng của một topic. Subscriber mới có thể nhận giá trị gần nhất khi subscribe. Phù hợp với cấu hình hoặc trạng thái hiện tại, ví dụ trạng thái vận hành cuối cùng.

Retained message khác persistent session:

- Retained message là giá trị gần nhất gắn với topic.
- Persistent session giữ trạng thái subscription và message QoS 1 chờ cho một client.

Không dùng retained message cho mọi telemetry lịch sử. Nếu publish liên tục, giá trị cũ sẽ bị thay thế; dữ liệu lịch sử nên được lưu ở dịch vụ dữ liệu.

### 5.6. Last Will and Testament

Last Will and Testament (LWT) là message mà broker publish thay client nếu kết nối bị mất bất thường. Có thể dùng LWT để cập nhật trạng thái offline:

~~~text
factory/hcm-01/pump-001/status
~~~

Payload ví dụ:

~~~json
{
  "connectionState": "offline",
  "reason": "unexpected_disconnect"
}
~~~

Khi kết nối bình thường, thiết bị publish trạng thái online. LWT hỗ trợ phát hiện mất kết nối, nhưng không thay thế heartbeat và health check ở tầng ứng dụng. Mạng có thể gián đoạn tạm thời; hệ thống nên có timeout và trạng thái stale phù hợp.

### 5.7. Thiết kế payload

Payload telemetry nên có message ID, thời điểm đo, sequence number, schema version và đơn vị:

~~~json
{
  "schemaVersion": 1,
  "messageId": "pump-001-00004567",
  "deviceId": "pump-001",
  "measuredAt": "2026-11-20T10:15:30Z",
  "sequence": 4567,
  "temperatureC": 68.4,
  "vibrationMmPerS": 2.1
}
~~~

Timestamp đo tại thiết bị và timestamp nhận ở cloud có ý nghĩa khác nhau. Nếu đồng hồ thiết bị không đáng tin cậy, Rules Engine hoặc consumer có thể bổ sung receivedAt để hỗ trợ đối soát. Đừng dùng timestamp thiết bị làm căn cứ duy nhất cho thứ tự event nếu đồng hồ có thể lệch.

## 6. Danh tính và cấp phát thiết bị

### 6.1. Thing, certificate và IoT policy

Một thiết bị được quản lý tốt thường có:

- Một Thing đại diện cho thiết bị trong registry.
- Một X.509 certificate để xác thực thiết bị.
- Một private key tương ứng được giữ an toàn trên thiết bị.
- Một AWS IoT Core policy giới hạn các thao tác được phép.
- Liên kết giữa certificate/principal và Thing.

Certificate chứng minh danh tính khi kết nối TLS mutual authentication. IoT policy quyết định certificate được phép connect với client ID nào, publish topic nào, subscribe topic filter nào và receive message nào.

Certificate được tạo nhưng chưa gắn policy có thể xác thực được nhưng không có quyền thực hiện thao tác IoT cần thiết. Tương tự, policy tồn tại nhưng certificate không hợp lệ hoặc bị inactive thì thiết bị không thể kết nối.

### 6.2. X.509 mutual TLS

Trong mutual TLS:

1. Thiết bị xác minh server certificate của AWS IoT.
2. Thiết bị gửi client certificate của chính nó.
3. AWS IoT kiểm tra certificate, trạng thái và chuỗi tin cậy.
4. AWS IoT đánh giá policy gắn với certificate/principal.
5. Kết nối được cho phép hoặc từ chối.

Mỗi thiết bị nên có certificate riêng. Không dùng một certificate và private key chung cho toàn bộ fleet vì một thiết bị bị xâm nhập có thể làm lộ danh tính của tất cả thiết bị.

Private key nên được bảo vệ bằng secure element, TPM hoặc cơ chế phần cứng tương đương khi thiết bị hỗ trợ. Nếu phải lưu trong filesystem, dùng quyền truy cập tối thiểu, mã hóa phù hợp và quy trình bảo vệ boot/debug interface.

### 6.3. AWS IoT Core policy

IoT policy dùng để giới hạn quyền trên resource IoT như client, topic, topic filter và shadow. Một policy ví dụ cho thiết bị pump-001:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:client/pump-001"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topic/factory/hcm-01/pump-001/telemetry"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/factory/hcm-01/pump-001/commands"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:topic/factory/hcm-01/pump-001/commands"
    }
  ]
}
~~~

Đây là ví dụ minh họa; account ID, Region, topic và resource ARN phải thay bằng giá trị của môi trường. Production policy nên giới hạn từng thiết bị vào topic của chính nó và chỉ cấp đúng action cần thiết.

MQTT subscription dùng wildcard dấu cộng và dấu thăng, nhưng wildcard trong resource ARN của AWS IoT policy tuân theo quy tắc policy của AWS. Không mặc định rằng ký tự MQTT này sẽ hoạt động như wildcard trong policy resource.

### 6.4. Thing policy variables

AWS IoT Core hỗ trợ policy variables như ThingName, ThingTypeName và Thing attributes trong các trường hợp được hỗ trợ. Điều này cho phép dùng một policy template cho nhiều thiết bị thay vì tạo policy riêng cho từng Thing.

Để sử dụng thing policy variables đúng cách:

- Certificate/principal phải được gắn với Thing theo mô hình đã chọn.
- Client ID MQTT cần khớp Thing name khi dùng các biến phụ thuộc Thing connection.
- Topic namespace phải có quy tắc thống nhất.
- Kiểm thử cả thiết bị hợp lệ và thiết bị cố truy cập Thing/topic khác.

Không dùng policy có wildcard quá rộng chỉ để giảm số lượng policy. Có thể chuẩn hóa policy template mà vẫn giới hạn từng thiết bị bằng ThingName hoặc CertificateId.

### 6.5. Quy trình onboarding thiết bị quy mô nhỏ

Với số lượng thiết bị nhỏ hoặc pilot:

1. Tạo Thing trong registry.
2. Tạo hoặc đăng ký X.509 certificate.
3. Tải certificate, private key và CA certificate cần thiết theo quy trình an toàn.
4. Attach certificate vào Thing.
5. Attach IoT policy vào certificate.
6. Lưu private key vào thiết bị.
7. Cấu hình endpoint, client ID và topic.
8. Kiểm tra TLS handshake, connect, publish và subscribe.
9. Ghi nhận serial number, Thing name và certificate ID trong inventory.

Private key chỉ được tải và lưu theo quy trình bảo mật; không đưa vào ticket, email hoặc repository. Nếu private key bị lộ, cần deactivate/revoke certificate và cấp credential mới.

### 6.6. Fleet Provisioning

Khi số lượng thiết bị lớn, tạo Thing và certificate thủ công không phù hợp. AWS IoT Core Fleet Provisioning hỗ trợ cấp phát tự động bằng provisioning template.

Các mô hình thường gặp:

- **Provisioning by claim:** thiết bị có claim certificate tạm thời để khởi tạo quy trình đăng ký và nhận certificate riêng.
- **Provisioning by trusted user:** ứng dụng hoặc quy trình tin cậy tạo provisioning claim và chuyển claim cho thiết bị qua kênh an toàn.
- **Just-in-time provisioning/registration:** dùng certificate được ký bởi CA đã đăng ký hoặc cơ chế provisioning tương ứng để tự động tạo tài nguyên khi thiết bị lần đầu kết nối.

Provisioning template mô tả tài nguyên cần tạo, ví dụ Thing, certificate và policy. Template có thể dùng parameters để áp dụng cho nhiều thiết bị.

Luồng provisioning by claim khái quát:

1. Thiết bị kết nối bằng claim certificate được bảo vệ.
2. Thiết bị gửi yêu cầu provisioning và thông tin nhận dạng được phép.
3. AWS IoT kiểm tra provisioning template và policy của claim.
4. Dịch vụ tạo certificate riêng và Thing.
5. Certificate mới được liên kết với Thing và policy.
6. Thiết bị lưu credential riêng và chuyển sang kết nối thông thường.
7. Claim certificate được quản lý theo chính sách để tránh tái sử dụng ngoài ý muốn.

Claim certificate là credential bootstrap có quyền đặc biệt. Hạn chế số thao tác và phạm vi được phép, bảo vệ private key, theo dõi số lần sử dụng và vô hiệu hóa khi có dấu hiệu lạm dụng. Không để claim certificate có quyền publish/subscribe rộng trên topic production.

## 7. Device Shadow và đồng bộ trạng thái

### 7.1. Vì sao cần Device Shadow?

Thiết bị có thể offline do mất mạng, hết pin, bảo trì hoặc di chuyển. Ứng dụng vẫn cần biết trạng thái gần nhất và có thể đặt cấu hình mong muốn để thiết bị áp dụng khi kết nối lại.

Device Shadow lưu trạng thái thiết bị trên AWS IoT Core. Ứng dụng có thể cập nhật desired state ngay cả khi thiết bị offline; khi thiết bị kết nối và đồng bộ, nó đọc thay đổi rồi cập nhật reported state.

Shadow không phải bản sao đầy đủ của database telemetry. Nó phù hợp để lưu trạng thái hoặc cấu hình hiện tại, không phải lưu toàn bộ lịch sử đo đạc.

### 7.2. Desired, reported và delta

Shadow document có ba phần quan trọng:

- desired: trạng thái mà ứng dụng mong muốn thiết bị đạt tới.
- reported: trạng thái thiết bị báo rằng nó đang có.
- delta: phần khác biệt giữa desired và reported do AWS IoT tính toán.

Ví dụ:

~~~json
{
  "state": {
    "desired": {
      "samplingIntervalSeconds": 30,
      "operatingMode": "eco"
    },
    "reported": {
      "samplingIntervalSeconds": 60,
      "operatingMode": "normal"
    }
  }
}
~~~

Thiết bị nhận delta, áp dụng cấu hình nếu hợp lệ rồi publish reported state mới. Khi desired và reported khớp nhau, delta tương ứng biến mất.

### 7.3. MQTT topics của Shadow

Shadow có các topic dành riêng cho thao tác như get, update, delete và response accepted/rejected/delta. Ví dụ với named shadow:

~~~text
$aws/things/pump-001/shadow/name/config/update
$aws/things/pump-001/shadow/name/config/update/delta
$aws/things/pump-001/shadow/name/config/update/accepted
$aws/things/pump-001/shadow/name/config/update/rejected
~~~

Named shadow cho phép tách nhiều nhóm trạng thái, ví dụ config, maintenance hoặc diagnostics. Một Thing chỉ có một classic unnamed shadow; nếu dự kiến cần nhiều nhóm trạng thái độc lập, hãy cân nhắc named shadows từ đầu.

### 7.4. Version và xử lý cập nhật đồng thời

Shadow document có version tăng theo mỗi lần cập nhật. Client có thể dùng version để tránh ghi đè một trạng thái mới bằng dữ liệu cũ. Nếu update dùng version không còn hiện hành, dịch vụ có thể từ chối để client đọc lại và đồng bộ.

Message delta có thể đến không theo thứ tự mà ứng dụng kỳ vọng. Thiết bị nên theo dõi version và bỏ qua thông điệp cũ hơn trạng thái đã xử lý.

### 7.5. Shadow không thay thế command workflow

Shadow phù hợp với trạng thái mong muốn có tính duy trì, ví dụ cấu hình lấy mẫu hoặc chế độ vận hành. Với command cần xác nhận thực thi, theo dõi tiến trình, retry, timeout hoặc rollout đến nhiều thiết bị, nên dùng MQTT command pattern hoặc AWS IoT Jobs.

Ví dụ:

| Nhu cầu | Cách phù hợp |
|---|---|
| Đặt sampling interval mới | Desired state trong Shadow |
| Báo nhiệt độ và firmware hiện tại | Reported state/telemetry |
| Chạy firmware update theo fleet | AWS IoT Jobs |
| Gửi lệnh khẩn cấp cần phản hồi | Command topic với correlation ID và acknowledgement |

## 8. Rules Engine và tích hợp AWS services

### 8.1. Lọc và định tuyến telemetry

Rules Engine cho phép dùng SQL để chỉ chọn message cần thiết rồi gọi action. Ví dụ:

- Lưu telemetry vào S3 qua Firehose.
- Đưa sự kiện cần xử lý nhanh vào Lambda.
- Gửi message tới SQS để consumer xử lý bất đồng bộ.
- Ghi metric vào CloudWatch.
- Gửi dữ liệu time-series tới dịch vụ phân tích phù hợp.
- Ghi dữ liệu thiết bị vào DynamoDB.

Một thiết kế tốt tránh gửi mọi message tới mọi dịch vụ. Lọc tại Rules Engine giúp giảm tải downstream và chi phí.

### 8.2. Ví dụ rule lưu dữ liệu

Giả sử thiết bị publish telemetry lên factory/{site}/{device}/telemetry. Rule có thể chọn dữ liệu:

~~~sql
SELECT
    deviceId,
    measuredAt,
    temperatureC,
    vibrationMmPerS
FROM 'factory/+/+/telemetry'
WHERE temperatureC >= -40
  AND temperatureC <= 150
~~~

Rule có thể gửi message đã lọc tới Data Firehose để buffer và ghi xuống S3. Firehose có thể dùng prefix theo ngày hoặc site tùy cấu hình delivery stream. Dữ liệu sau đó được xử lý bằng Glue hoặc truy vấn bằng Athena.

### 8.3. IAM role cho rule action

Rules Engine cần quyền thực hiện action trên dịch vụ đích. Thường cấu hình IAM role được AWS IoT assume, với quyền tối thiểu như PutRecord vào Firehose stream hoặc PutObject theo bucket/prefix được chỉ định.

Không cấp quyền * cho role của mọi rule. Tách role theo action hoặc nhóm rule để giảm blast radius. Nếu rule gửi tới Lambda, giới hạn quyền invoke đúng function; nếu gửi tới S3, giới hạn bucket và prefix.

### 8.4. Xử lý lỗi rule

Một rule có thể được kích hoạt nhưng action thất bại vì thiếu IAM permission, sai ARN, resource chưa tồn tại hoặc dịch vụ đích gặp lỗi. Cần:

- Bật AWS IoT logging ở mức phù hợp.
- Theo dõi error metrics và CloudWatch Logs.
- Dùng error action hoặc dead-letter pattern nếu workflow hỗ trợ.
- Thiết kế consumer idempotent.
- Theo dõi số message nhận và số message ghi thành công ở đích.
- Có quy trình replay dữ liệu khi downstream lỗi.

Không giả định rule engine sẽ thay thế durable queue cho mọi workflow. Với xử lý quan trọng, hãy định tuyến qua SQS/Kinesis hoặc một lớp lưu trữ có khả năng replay phù hợp.

## 9. Quản lý fleet, firmware và thiết bị

### 9.1. AWS IoT Jobs

AWS IoT Jobs giúp gửi và theo dõi tác vụ từ xa cho một Thing hoặc nhóm thiết bị. Job document có thể mô tả:

- URL hoặc vị trí firmware package.
- Phiên bản phần mềm cần cài.
- Lệnh nâng cấp hoặc cấu hình.
- Tham số và bước thực hiện.
- Quy tắc retry, timeout hoặc rollout.

Thiết bị nhận thông báo Job qua MQTT hoặc truy vấn Jobs API, tải job document, thực hiện tác vụ và cập nhật trạng thái execution như IN_PROGRESS, SUCCEEDED, FAILED hoặc trạng thái phù hợp khác.

### 9.2. OTA firmware update

Một quy trình OTA an toàn:

1. Build firmware và kiểm tra chữ ký/hash.
2. Đưa package lên vị trí lưu trữ được bảo vệ.
3. Tạo Job document với version, URL và thông tin xác minh.
4. Chọn Thing Group hoặc danh sách thiết bị.
5. Rollout theo batch/canary.
6. Thiết bị tải package và xác minh chữ ký trước khi cài.
7. Thiết bị khởi động lại, kiểm tra health và báo kết quả.
8. Theo dõi tỷ lệ thành công và dừng rollout nếu lỗi vượt ngưỡng.

Firmware nên có cơ chế rollback hoặc recovery partition nếu phần cứng hỗ trợ. Không coi việc thiết bị tải xong file là nâng cấp thành công; cần xác nhận boot và health check sau update.

### 9.3. Fleet Indexing

Fleet Indexing cho phép tìm kiếm và tổng hợp thông tin thiết bị dựa trên dữ liệu registry, Device Shadow, connectivity, package catalog và Device Defender violations theo cấu hình được hỗ trợ.

Ví dụ truy vấn fleet:

- Tìm thiết bị theo model hoặc site.
- Tìm thiết bị đang offline.
- Tìm thiết bị có firmware version cũ.
- Tổng hợp số lượng thiết bị theo trạng thái hoặc vi phạm.
- Tạo dynamic thing group từ query.

Fleet Indexing hữu ích cho vận hành và troubleshooting. Chỉ bật các nguồn index cần thiết vì indexing tạo thêm chi phí và cần kiểm soát quyền truy vấn.

### 9.4. AWS IoT Device Defender

Device Defender hỗ trợ bảo vệ fleet bằng:

- **Audit:** kiểm tra cấu hình và security posture của tài nguyên IoT, certificate, policy và các thành phần được hỗ trợ.
- **Detect:** phát hiện hành vi bất thường dựa trên metric thiết bị hoặc cloud-side metric.
- **Mitigation actions:** thực hiện phản ứng được cấu hình, ví dụ cập nhật policy, cách ly certificate hoặc đưa thiết bị vào nhóm xử lý theo workflow.

Device Defender không thay thế secure boot, patching, firmware signing hoặc bảo vệ phần cứng. Đây là lớp giám sát và phát hiện giúp đội vận hành nhận diện cấu hình yếu và hành vi bất thường.

### 9.5. Device Advisor

AWS IoT Device Advisor cung cấp các bài kiểm tra để xác minh thiết bị tương thích với AWS IoT Core theo các tiêu chí kết nối và giao thức được hỗ trợ. Nên dùng trong giai đoạn phát triển firmware và chứng nhận thiết bị trước khi đưa vào fleet production.

Kiểm thử sớm giúp phát hiện vấn đề về TLS, certificate, MQTT behavior, reconnect và protocol handling trước khi sản xuất hàng loạt.

## 10. AWS IoT Greengrass và edge computing

### 10.1. Khi nào cần xử lý tại edge?

Không phải mọi dữ liệu đều nên gửi lên cloud. Edge computing phù hợp khi:

- Thiết bị cần phản hồi nhanh hoặc điều khiển cục bộ.
- Kết nối Internet không ổn định.
- Dữ liệu có dung lượng lớn và chỉ cần gửi phần tổng hợp.
- Có yêu cầu giữ dữ liệu tại site hoặc giảm băng thông.
- Cần chạy inference gần camera, máy móc hoặc cảm biến.

Ví dụ, gateway tại nhà máy có thể đọc dữ liệu từ PLC và cảm biến, tính rolling average, phát hiện ngưỡng bất thường rồi chỉ gửi event quan trọng lên cloud.

### 10.2. AWS IoT Greengrass

AWS IoT Greengrass là runtime edge cho phép chạy component trên thiết bị core tại chỗ. Component có thể là process native, container, Lambda hoặc runtime được hỗ trợ. Greengrass giúp triển khai, cấu hình và quản lý phần mềm tại edge thông qua cloud.

Khả năng thường dùng:

- Xử lý message MQTT cục bộ.
- Lọc, aggregate và buffer dữ liệu.
- Chạy business logic khi kết nối cloud bị gián đoạn.
- Chạy model inference tại edge theo kiến trúc phù hợp.
- Quản lý deployment và version component.
- Kết nối client device trong mạng local và đồng bộ dữ liệu/shadow với AWS IoT Core.

Greengrass core device cần được provision và kết nối tới AWS IoT. Client devices có thể kết nối tới core qua MQTT để gửi dữ liệu hoặc tương tác với component cục bộ.

### 10.3. AWS IoT Core và Greengrass khác nhau thế nào?

| Tiêu chí | AWS IoT Core | AWS IoT Greengrass |
|---|---|---|
| Vị trí chính | AWS Cloud | Gateway/edge device |
| Vai trò | Kết nối, broker, registry, rules, shadow, fleet management | Runtime và xử lý cục bộ |
| Giao tiếp | Thiết bị với cloud và cloud services | Edge component và local client devices |
| Offline | Hỗ trợ session/shadow theo cơ chế dịch vụ | Có thể tiếp tục xử lý local theo component và thiết kế |
| Triển khai | Managed service | Cài runtime và deploy component trên core device |

Hai dịch vụ thường được dùng cùng nhau. IoT Core quản lý kết nối cloud và fleet; Greengrass thực hiện logic gần nguồn dữ liệu.

### 10.4. Kiến trúc edge-gateway

~~~mermaid
flowchart TB
    subgraph EDGE["Nhà máy / edge site"]
        S1[Cảm biến và PLC]
        S2[Camera / máy đo]
        G[Greengrass Core]
        C[Local components]
        Q[Local buffer]
        S1 --> G
        S2 --> G
        G --> C
        C --> Q
    end
    Q -->|MQTT/TLS khi có mạng| I[AWS IoT Core]
    I --> R[Rules Engine]
    R --> D[S3 / Kinesis / Lambda]
    I <--> SH[Device Shadow]
    I --> J[IoT Jobs deployment]
    J --> G
~~~

Khi mất Internet, edge application cần tiếp tục hành động an toàn dựa trên dữ liệu local và policy đã được cache. Khi kết nối trở lại, dữ liệu được đồng bộ theo thứ tự và giới hạn lưu trữ. Không phụ thuộc cloud round-trip cho một vòng điều khiển công nghiệp cần latency rất thấp hoặc an toàn chức năng.

## 11. Bảo mật kết nối và thiết bị

### 11.1. Xác thực server và client

Thiết bị phải xác minh AWS IoT server certificate bằng CA tin cậy, đồng thời AWS IoT xác thực client certificate của thiết bị. Việc kiểm tra hostname, certificate validity và thời gian hệ thống là cần thiết.

Các biện pháp:

- Dùng certificate riêng cho từng thiết bị.
- Bảo vệ private key bằng phần cứng nếu có.
- Kiểm tra certificate chain và hostname.
- Dùng TLS 1.2 hoặc 1.3 theo hỗ trợ.
- Cấu hình SNI và ALPN khi kết nối qua port 443.
- Không tắt certificate validation để xử lý lỗi kết nối.

### 11.2. Certificate lifecycle

Certificate có vòng đời:

1. Tạo hoặc cấp từ CA được tin cậy.
2. Đăng ký với AWS IoT.
3. Attach Thing và IoT policy.
4. Phân phối an toàn tới thiết bị.
5. Theo dõi trạng thái và thời hạn.
6. Rotate trước khi hết hạn hoặc khi nghi ngờ bị lộ.
7. Deactivate/revoke certificate cũ.
8. Xác minh thiết bị đã chuyển sang certificate mới.

Certificate bị lộ cần được vô hiệu hóa nhanh. Cần có inventory ánh xạ certificate ID với serial number, owner và vị trí thiết bị để tránh thu hồi nhầm hoặc bỏ sót.

### 11.3. Least privilege cho IoT policy

Mỗi thiết bị chỉ nên:

- Connect bằng client ID của chính nó.
- Publish vào topic telemetry/status của nó.
- Subscribe command hoặc shadow topic cần thiết.
- Receive message trên topic đã được cấp.
- Truy cập đúng Job/Shadow resource nếu workflow yêu cầu.

Không cho mọi thiết bị subscribe tất cả topic hoặc publish command tùy ý. Tách quyền thiết bị, backend, operator và provisioning role.

### 11.4. Credential và secret

Không nhúng IAM access key dài hạn vào firmware. Nếu thiết bị cần truy cập dịch vụ AWS khác, đánh giá IoT Credential Provider để trao đổi X.509 identity lấy temporary credentials theo role alias và policy được cấu hình.

Temporary credential cần scope theo thiết bị và chỉ cho phép resource cần thiết. Không cấp role có quyền quản trị account cho thiết bị.

### 11.5. Chống giả mạo và replay

Ngoài TLS, payload nên có:

- Message ID duy nhất.
- Sequence number tăng theo thiết bị.
- Timestamp và thông tin đồng hồ.
- Schema version.
- Chữ ký ứng dụng nếu yêu cầu end-to-end integrity vượt ngoài TLS session.

Consumer có thể phát hiện duplicate hoặc message cũ dựa trên sequence number và event ID. Với command quan trọng, thêm command ID, expiry, acknowledgement và trạng thái thực thi.

### 11.6. Logging và audit

AWS IoT logging có thể ghi nhận sự kiện broker, kết nối và lỗi theo mức log được cấu hình. CloudTrail ghi nhận hoạt động control plane như tạo Thing, thay đổi certificate, policy hoặc rule. Device Defender giúp audit cấu hình và phát hiện hành vi bất thường.

Log nên được bảo vệ ở account/bucket riêng, có retention và quyền truy cập phù hợp. Tránh log private key, secret, payload chứa PII hoặc dữ liệu sản xuất nhạy cảm nếu không có mục đích và kiểm soát rõ ràng.

## 12. Reliability và xử lý mất kết nối

### 12.1. Reconnect strategy

Thiết bị di động hoặc edge thường gặp mạng chập chờn. Dùng exponential backoff với jitter để tránh toàn fleet reconnect cùng lúc sau sự cố mạng hoặc broker. Có thể đặt giới hạn thời gian tối đa giữa các lần thử và reset backoff sau khi kết nối ổn định.

### 12.2. Store-and-forward

Nếu dữ liệu không được phép mất, thiết bị hoặc edge gateway cần buffer local. Khi mất kết nối:

1. Ghi event vào queue/buffer bền vững.
2. Đánh dấu sequence và thời điểm.
3. Áp dụng giới hạn dung lượng và retention.
4. Khi mạng trở lại, gửi lại theo batch/rate limit.
5. Consumer deduplicate theo message ID.
6. Xác nhận dữ liệu đã được xử lý trước khi xóa khỏi buffer.

Không dùng MQTT QoS 1 như cơ chế lưu trữ vô hạn. QoS 1 xử lý delivery tới broker theo semantics của giao thức, còn dữ liệu cần đảm bảo không mất phải có persistence và replay logic ở thiết bị hoặc downstream.

### 12.3. Persistent session và shadow

Persistent session có thể giữ subscription và message QoS 1 chờ theo giới hạn dịch vụ. Shadow giữ desired/reported state để thiết bị đồng bộ sau khi reconnect. Hai cơ chế giải quyết hai vấn đề khác nhau:

- Session giúp duy trì trạng thái messaging.
- Shadow giúp đồng bộ trạng thái ứng dụng.

Nếu thiết bị offline lâu hơn session expiry hoặc vượt giới hạn message queue, message có thể hết hạn hoặc bị loại bỏ. Với lệnh quan trọng, dùng Jobs hoặc workflow có trạng thái và timeout rõ ràng.

### 12.4. Backpressure và rate control

Khi hàng nghìn thiết bị cùng gửi telemetry sau outage, downstream có thể bị quá tải. Thiết kế:

- Randomize reconnect và publish schedule.
- Batch dữ liệu phù hợp.
- Giới hạn tốc độ flush buffer.
- Dùng SQS/Kinesis làm lớp đệm downstream khi cần.
- Đặt retry và DLQ.
- Theo dõi throttling và queue depth.
- Ưu tiên command/control traffic so với telemetry không quan trọng.

### 12.5. Multi-Region

Nếu cần DR hoặc phân phối fleet theo địa lý, có thể triển khai IoT architecture ở nhiều Region. Tuy nhiên, Thing Registry, certificate, policy, rules, shadow và Jobs cần được quản lý theo thiết kế multi-Region; không giả định tài nguyên tự động replicate đầy đủ.

Xác định:

- Region primary và secondary.
- Endpoint và DNS strategy.
- Cách đồng bộ registry/certificate/policy.
- Cách đồng bộ dữ liệu và shadow state.
- Quy trình chuyển thiết bị sang endpoint dự phòng.
- Cách tránh split-brain khi cả hai Region nhận command.
- RPO/RTO và kiểm thử failover.

## 13. Giám sát và vận hành fleet

### 13.1. CloudWatch metrics

Theo dõi các metric liên quan:

- Số kết nối đang hoạt động.
- Connect/disconnect và lỗi xác thực.
- Số message publish/receive.
- Message throttling hoặc quota-related errors.
- Rules Engine invocation/action errors.
- Device Shadow request và lỗi.
- Jobs execution status.
- Fleet indexing và Device Defender findings.

Tên metric và dimensions có thể thay đổi theo thành phần và Region. Chọn metric theo mục tiêu vận hành thay vì bật mọi log/metric ở mức chi tiết cao.

### 13.2. CloudWatch Logs

Có thể bật AWS IoT logging để điều tra:

- Thiết bị không kết nối được.
- Certificate hoặc policy bị từ chối.
- Topic publish/subscribe không được cấp quyền.
- Rule action thất bại.
- Message broker behavior bất thường.

Log ở mức verbose cho toàn fleet có thể tạo chi phí lớn và chứa dữ liệu nhạy cảm. Dùng sampling, mức log theo nhóm thiết bị và thời hạn lưu trữ.

### 13.3. Fleet health dashboard

Một dashboard fleet có thể hiển thị:

| Chỉ số | Ý nghĩa |
|---|---|
| Online devices | Số thiết bị đang kết nối |
| Offline duration | Thời gian từ lần cuối thiết bị online |
| Firmware distribution | Phân bố version firmware |
| Telemetry freshness | Độ mới của dữ liệu cuối cùng |
| Job success rate | Tỷ lệ hoàn thành OTA/configuration job |
| Certificate expiry | Thiết bị sắp hết hạn certificate |
| Defender violations | Số thiết bị có finding |
| Rule delivery errors | Lỗi định tuyến message |

Kết hợp Fleet Indexing, CloudWatch, Device Defender và dữ liệu nghiệp vụ để xác định thiết bị nào cần bảo trì.

### 13.4. Quy trình incident

Khi fleet có nhiều thiết bị mất kết nối:

1. Kiểm tra AWS Health Dashboard và CloudWatch metrics.
2. Phân biệt sự cố cloud, DNS, ISP, firewall hay nguồn điện tại site.
3. Xem Connect/Disconnect logs và certificate errors.
4. Kiểm tra endpoint, TLS, SNI, ALPN và thời gian thiết bị.
5. Đánh giá reconnect storm và throttling.
6. Giảm tốc độ reconnect hoặc publish nếu downstream quá tải.
7. Khôi phục theo từng site/nhóm và xác minh telemetry.
8. Ghi nhận nguyên nhân, thiết bị bị ảnh hưởng và biện pháp phòng ngừa.

## 14. Chi phí AWS IoT Core

### 14.1. Các thành phần tính phí

AWS IoT Core tính phí theo các thành phần sử dụng, thường gồm:

- Connectivity: thời gian kết nối thiết bị.
- Messaging: số lượng và kích thước message theo cách đo của dịch vụ.
- Device Shadow và registry operations.
- Rules Engine: số rule được kích hoạt và số action thực hiện.
- Các tính năng quản lý/quan sát hoặc dịch vụ liên quan theo bảng giá.

Ngoài IoT Core, tổng chi phí còn có thể gồm Lambda, S3, Kinesis, Firehose, DynamoDB, CloudWatch, KMS, Greengrass, network và lưu trữ downstream. Giá thay đổi theo Region và loại workload; cần dùng trang pricing hiện hành hoặc AWS Pricing Calculator.

### 14.2. Những yếu tố làm chi phí tăng

- Giữ kết nối liên tục cho thiết bị không cần online.
- Publish message quá thường xuyên hoặc payload quá lớn.
- Gửi nhiều bản sao cùng một telemetry qua nhiều topic.
- Gọi Device Shadow update liên tục dù state không thay đổi.
- Một message kích hoạt quá nhiều rule/action.
- Log verbose cho toàn fleet.
- Lưu trữ lịch sử quá lâu trong S3 hoặc database nóng.
- Chạy Greengrass/edge compute trên tài nguyên lớn hơn nhu cầu.

### 14.3. Tối ưu chi phí

- Chọn chu kỳ telemetry theo yêu cầu nghiệp vụ.
- Gộp nhiều mẫu thành batch khi chấp nhận được.
- Giảm payload và loại bỏ trường không cần.
- Chỉ update Shadow khi trạng thái thực sự thay đổi.
- Lọc message ở Rules Engine.
- Dùng Firehose để buffer và ghi dữ liệu theo lô.
- Chuyển dữ liệu lịch sử sang storage class phù hợp.
- Tắt log verbose sau khi hoàn tất điều tra.
- Dùng edge filtering để chỉ gửi dữ liệu cần thiết.
- Theo dõi chi phí theo site, Thing Group và loại thiết bị.

### 14.4. Ví dụ ước tính

Giả sử một site có 1.000 cảm biến, mỗi cảm biến gửi một message 1 KB mỗi phút và giữ kết nối liên tục. Số message mỗi ngày:

\[
1.000 \times 60 \times 24 = 1.440.000\ \text{messages/day}
\]

Nếu giữ trong 30 ngày:

\[
1.440.000 \times 30 = 43.200.000\ \text{messages/month}
\]

Đây chỉ là lượng message, chưa tính connectivity minutes, rules, actions, Shadow, registry, lưu trữ downstream và các dịch vụ liên quan. Khi lập estimate, cần tính từng thành phần theo Region và đơn giá hiện hành.

## 15. Ví dụ kiến trúc: giám sát máy bơm công nghiệp

### 15.1. Bối cảnh

Một nhà máy có 500 máy bơm, mỗi máy có cảm biến nhiệt độ, áp suất và độ rung. Hệ thống cần:

- Gửi telemetry định kỳ.
- Cảnh báo khi nhiệt độ hoặc rung vượt ngưỡng.
- Cho phép kỹ sư thay đổi sampling interval từ dashboard.
- Theo dõi trạng thái online/offline.
- Cập nhật firmware theo nhóm máy.
- Tiếp tục ghi dữ liệu khi kết nối Internet bị gián đoạn ngắn.

### 15.2. Thiết kế thiết bị và kết nối

- Mỗi máy bơm có Thing và certificate riêng.
- Client ID khớp Thing name.
- MQTT over TLS dùng X.509 certificate.
- Thiết bị publish telemetry và status vào topic riêng.
- IoT policy chỉ cho phép publish telemetry/status của thiết bị và subscribe command/shadow cần thiết.
- Site gateway chạy Greengrass để buffer dữ liệu và xử lý ngưỡng local.

### 15.3. Định tuyến dữ liệu

- Rules Engine lọc telemetry hợp lệ.
- Message thường được gửi tới Data Firehose để lưu S3 theo partition site/date.
- Event vượt ngưỡng được gửi tới Lambda hoặc SQS để xử lý cảnh báo.
- Glue/Athena dùng dữ liệu S3 để phân tích xu hướng và dự báo bảo trì.
- CloudWatch theo dõi kết nối, rule errors và throughput.

### 15.4. Điều khiển và quản lý

- Dashboard cập nhật desired sampling interval trong named Shadow config.
- Thiết bị nhận delta, áp dụng cấu hình và cập nhật reported state.
- AWS IoT Jobs triển khai firmware theo Thing Group, bắt đầu từ canary group.
- Fleet Indexing tìm thiết bị offline hoặc firmware cũ.
- Device Defender audit policy/certificate và phát hiện hành vi bất thường.

### 15.5. Xử lý outage

Khi Internet mất:

- Greengrass tiếp tục đọc cảm biến và áp dụng ngưỡng an toàn local.
- Telemetry được lưu trong local buffer.
- Dashboard hiển thị trạng thái dữ liệu stale/offline.
- Khi mạng trở lại, gateway gửi dữ liệu theo batch và tốc độ giới hạn.
- Consumer dùng message ID/sequence để loại duplicate.
- Shadow đồng bộ desired/reported state mới nhất.

Hệ thống điều khiển an toàn của máy bơm vẫn phải hoạt động cục bộ; không phụ thuộc round-trip tới AWS IoT Core cho thao tác dừng khẩn cấp.

## 16. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| TLS handshake thất bại | Sai CA, clock lệch, hostname/SNI hoặc TLS config | Kiểm tra server certificate, thời gian, SNI và TLS version |
| Certificate rejected | Certificate inactive, sai chain hoặc chưa đăng ký | Kiểm tra certificate status và registration |
| Kết nối được nhưng publish bị từ chối | IoT policy thiếu iot:Publish hoặc topic ARN sai | Kiểm tra policy gắn với certificate và resource |
| Subscribe thành công nhưng không nhận message | Thiếu iot:Receive, publisher sai topic hoặc không có message | Kiểm tra policy, topic và broker logs |
| Device ID xung đột | Nhiều client dùng cùng client ID | Dùng client ID duy nhất gắn với Thing |
| Kết nối liên tục bị ngắt | Mạng chập chờn, keepalive, clock hoặc credential | Kiểm tra network, keepalive, backoff và certificate |
| Rule không ghi dữ liệu | IAM role thiếu quyền hoặc action config sai | Kiểm tra rule logs, role trust và target ARN |
| Shadow không đồng bộ | Sai topic, version cũ hoặc payload không hợp lệ | Kiểm tra named shadow, version và response rejected |
| OTA job thất bại | URL không truy cập được, chữ ký sai hoặc thiếu storage | Kiểm tra job document, download, signature và device logs |
| Fleet báo offline sai | Thing name không khớp client ID hoặc disconnect delay | Kiểm tra association, lifecycle events và heartbeat |
| Message duplicate | QoS 1 retry hoặc consumer xử lý lại | Dùng message ID, sequence và idempotency |
| Chi phí tăng đột biến | Message/rule/action/log tăng hoặc reconnect storm | Phân tích billing dimensions, CloudWatch và rule metrics |

## 17. Checklist thiết kế AWS IoT Core

### Trước khi triển khai

1. Xác định loại thiết bị, firmware, OS, network và yêu cầu latency.
2. Chọn Region và endpoint.
3. Chọn MQTT, WSS hoặc HTTPS.
4. Thiết kế topic namespace và payload schema.
5. Xác định Thing Registry, Thing Group và naming convention.
6. Thiết kế certificate issuance, rotation và revocation.
7. Viết IoT policy least privilege.
8. Chọn provisioning workflow phù hợp quy mô fleet.
9. Xác định Shadow, Jobs và Greengrass có cần thiết không.
10. Ước tính connectivity, message, rules, storage và logging cost.

### Khi triển khai

1. Tạo Thing, certificate và policy.
2. Kiểm tra TLS, SNI, ALPN và port.
3. Kiểm thử connect, publish, subscribe và reconnect.
4. Tạo Rules Engine và IAM role cho action.
5. Cấu hình Shadow và kiểm thử desired/reported/delta.
6. Thiết lập Jobs và OTA canary rollout.
7. Cấu hình CloudWatch logging/metrics và CloudTrail.
8. Kiểm tra quyền truy cập và negative test.

### Khi vận hành

1. Theo dõi online/offline, telemetry freshness và message rate.
2. Theo dõi certificate expiry và policy changes.
3. Rà soát Device Defender audit/detect findings.
4. Kiểm tra Job success rate và firmware distribution.
5. Kiểm thử outage, local buffer và reconnect.
6. Kiểm soát rule failures, queue depth và downstream throttling.
7. Review chi phí theo site, device type và workload.
8. Kiểm thử rotation, decommission và thu hồi certificate.

## 18. Kết luận

AWS IoT Core cung cấp nền tảng kết nối thiết bị qua device gateway, message broker và Rules Engine, đồng thời hỗ trợ Thing Registry, Device Shadow và các tính năng quản lý fleet. MQTT phù hợp với giao tiếp publish/subscribe nhẹ; WSS hữu ích cho web client hoặc mạng ưu tiên HTTPS; HTTPS phù hợp với thiết bị chỉ cần publish theo request. TLS, X.509 certificate và IoT policy tạo lớp xác thực và phân quyền cho từng thiết bị.

Một kiến trúc IoT production cần quản lý toàn bộ vòng đời: onboarding, certificate, topic, telemetry, command, shadow, firmware, monitoring, outage và decommission. Rules Engine giúp chuyển dữ liệu tới dịch vụ AWS; Jobs và Fleet Indexing hỗ trợ quản lý quy mô lớn; Device Defender bổ sung audit và phát hiện bất thường. Với yêu cầu xử lý tại chỗ, AWS IoT Greengrass chạy component và logic cục bộ, sau đó đồng bộ dữ liệu với AWS IoT Core khi có kết nối.

Thiết kế tốt giới hạn quyền theo từng Thing, dùng message ID và sequence để xử lý duplicate, buffer dữ liệu khi offline và không phụ thuộc cloud cho vòng điều khiển an toàn. Khi kết hợp bảo mật thiết bị, khả năng phục hồi, quan sát fleet và kiểm soát chi phí, AWS IoT Core trở thành nền tảng để kết nối và vận hành thiết bị ở quy mô lớn.

## 19. Tài liệu tham khảo chính thức

- [How AWS IoT Core works](https://docs.aws.amazon.com/iot/latest/developerguide/aws-iot-how-it-works.html)
- [Connect devices to AWS IoT](https://docs.aws.amazon.com/iot/latest/developerguide/iot-connect-devices.html)
- [Device communication protocols](https://docs.aws.amazon.com/iot/latest/developerguide/protocols.html)
- [MQTT in AWS IoT Core](https://docs.aws.amazon.com/iot/latest/developerguide/mqtt.html)
- [Security best practices in AWS IoT Core](https://docs.aws.amazon.com/iot/latest/developerguide/security-best-practices.html)
- [AWS IoT Core policies and authorization](https://docs.aws.amazon.com/iot/latest/developerguide/iot-authorization.html)
- [Device provisioning](https://docs.aws.amazon.com/iot/latest/developerguide/iot-provision.html)
- [AWS IoT Rules Engine](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)
- [AWS IoT Device Shadows](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [AWS IoT Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Greengrass – How it works](https://docs.aws.amazon.com/greengrass/v2/developerguide/how-it-works.html)
- [AWS IoT Core pricing](https://aws.amazon.com/iot-core/pricing/)
