# AWS IoT Greengrass và xử lý khi mất kết nối

Thiết bị IoT thường hoạt động ở nơi Internet không ổn định: nhà máy có vùng phủ sóng yếu, trạm bơm ở xa, phương tiện di chuyển hoặc hệ thống giám sát năng lượng. Nếu mọi quyết định đều phải gửi lên cloud rồi chờ phản hồi, chỉ một lần mất WAN cũng có thể làm quy trình tại hiện trường dừng lại.

AWS IoT Greengrass đưa khả năng xử lý ứng dụng xuống thiết bị biên. Một Greengrass core device có thể chạy component, trao đổi message trong mạng cục bộ, xử lý dữ liệu và lưu tạm dữ liệu cần gửi lên cloud. Khi kết nối phục hồi, thiết bị tiếp tục đồng bộ và chuyển dữ liệu theo cấu hình.

Offline không có nghĩa mọi dịch vụ AWS vẫn hoạt động khi Internet bị ngắt. Cần phân biệt xử lý cục bộ, lưu đệm để gửi sau, đồng bộ trạng thái và các thao tác bắt buộc phải gọi AWS Cloud. Một hệ thống bền vững phải xác định dữ liệu nào được giữ, giữ ở đâu, trong bao lâu, điều gì xảy ra khi bộ nhớ/đĩa đầy và cách xử lý bản ghi trùng sau reconnect.

Bài học tập trung vào AWS IoT Greengrass V2, đặc biệt là Greengrass nucleus, component lifecycle, MQTT spooler, local MQTT broker, IPC pub/sub, Stream Manager, Shadow Manager, local deployment và quy trình phục hồi sau khi mất kết nối.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Mô tả vai trò của Greengrass core device, nucleus và component.
- Phân biệt mất kết nối Internet với mất kết nối mạng LAN hoặc lỗi chính thiết bị.
- Xác định chức năng nào vẫn chạy cục bộ và chức năng nào cần cloud.
- Cấu hình MQTT spooler để lưu message chờ gửi lại AWS IoT Core.
- Phân biệt QoS 0, QoS 1, bộ đệm memory và disk spooler.
- Cho phép client devices xác thực khi core device đang offline.
- Dùng local MQTT broker, MQTT bridge và local publish/subscribe để xử lý message tại edge.
- Dùng Stream Manager để lưu trữ, ưu tiên và export dữ liệu sau khi mạng phục hồi.
- Đồng bộ device shadows và xử lý xung đột trạng thái.
- Cập nhật component bằng local deployment khi không có Internet.
- Thiết kế idempotency, retry, capacity planning, security và runbook cho offline operation.

## 1. AWS IoT Greengrass V2 trong kiến trúc edge

AWS IoT Greengrass V2 là runtime và nền tảng quản lý component chạy trên thiết bị biên. Thiết bị chạy Greengrass Core software, gồm Greengrass nucleus và các component được cài đặt.

| Thành phần | Vai trò |
|---|---|
| Greengrass core device | Máy tính biên tại nhà máy, cửa hàng, phương tiện hoặc gateway. |
| Greengrass nucleus | Runtime bắt buộc, quản lý component, deployment, IPC, kết nối cloud và cấu hình core. |
| Greengrass component | Module phần mềm có recipe, artifact, dependency và lifecycle. |
| AWS IoT Core | Kênh MQTT và dịch vụ cloud để quản lý thiết bị, nhận dữ liệu và trao đổi trạng thái. |
| Client device | Cảm biến, PLC gateway, camera hoặc thiết bị IoT kết nối cục bộ tới core qua MQTT. |
| Stream Manager | Lưu và chuyển các luồng dữ liệu lớn từ edge lên cloud hoặc local destination. |
| Shadow Manager | Lưu shadow cục bộ và đồng bộ trạng thái với AWS IoT Device Shadow. |

~~~mermaid
flowchart TB
    subgraph Edge["Nhà máy / Edge site"]
        D1["Sensor / PLC"]
        D2["Camera / Client device"]
        B["Local MQTT broker"]
        N["Greengrass nucleus"]
        P["Local IPC pub/sub"]
        C1["Component: control"]
        C2["Component: analytics"]
        SM["Stream Manager"]
        SH["Shadow Manager"]
        D1 --> B
        D2 --> B
        B <--> C1
        B <--> P
        P <--> C1
        P <--> C2
        C1 --> SM
        C2 --> SM
        N --- P
        N --- B
        N --- SM
        N --- SH
    end
    SM -->|Khi có mạng| IOT["AWS IoT Core / Kinesis / S3 / SiteWise"]
    SH <-->|Khi có mạng| CLOUDSH["AWS IoT Device Shadow"]
    N <-->|Control plane / MQTT| CLOUD["AWS IoT Greengrass Cloud"]
~~~

Một component có thể lọc dữ liệu, chạy inference, điều khiển thiết bị, ghi log hoặc giao tiếp với component khác qua IPC. Các component đã được cài đặt có thể tiếp tục chạy khi kết nối cloud bị gián đoạn, miễn là thiết bị và các dependency cục bộ vẫn hoạt động.

## 2. Hiểu đúng các trạng thái mất kết nối

Trong thực tế có nhiều loại sự cố khác nhau. Không nên gom tất cả thành một trạng thái offline.

| Tình huống | Tác động | Khả năng tiếp tục |
|---|---|---|
| Mất Internet/WAN, LAN vẫn hoạt động | Core không gọi được AWS Cloud; thiết bị cục bộ vẫn thấy nhau | Local component, local MQTT, local IPC và dữ liệu đã lưu cục bộ có thể tiếp tục |
| Mất kết nối từ core tới AWS IoT Core | MQTT publish/subscribe cloud và cloud deployment bị gián đoạn | MQTT spooler có thể lưu message outbound; local processing vẫn chạy |
| Client device mất kết nối tới core | Core không nhận được dữ liệu từ client đó | Các client khác và component trên core vẫn có thể hoạt động |
| Mất LAN giữa client devices và core | Không thể trao đổi MQTT cục bộ | Chỉ các chức năng chạy trực tiếp trên core còn hoạt động |
| Core device mất điện hoặc hỏng ổ đĩa | Runtime và local processing dừng | Cần khởi động lại, phục hồi storage hoặc thay thiết bị |
| AWS Cloud/service bị gián đoạn | Một số cloud API không khả dụng | Edge vẫn có thể xử lý cục bộ và gửi lại sau khi dịch vụ phục hồi |

### 2.1. Ma trận chức năng khi WAN bị ngắt

| Chức năng | Có thể hoạt động offline? | Điều kiện |
|---|---|---|
| Component đã cài và có đủ artifact/dependency | Có | Core device vẫn chạy |
| Local IPC pub/sub giữa component | Có | Nucleus và component liên quan còn hoạt động |
| Client device gửi MQTT tới local broker | Có | LAN, broker và auth local hoạt động |
| MQTT bridge chuyển message giữa LocalMqtt và Pubsub | Có | Mapping và component bridge còn chạy |
| MQTT bridge gửi message tới AWS IoT Core | Không trong thời gian mất WAN | Sẽ tiếp tục khi cloud connection phục hồi |
| MQTT spooler giữ message outbound | Có | Message nằm trong spool và chưa vượt capacity |
| Stream Manager lưu stream cục bộ | Có | Storage còn dung lượng |
| Stream Manager export tới AWS service | Không trong thời gian cloud không truy cập được | Export tiếp tục sau khi có mạng |
| Local device shadow | Có | Shadow Manager và local shadow service hoạt động |
| Đồng bộ shadow với AWS IoT Core | Không trong thời gian mất WAN | Đồng bộ lại sau khi reconnect |
| Cloud deployment mới | Không thể nhận từ cloud khi mất kết nối | Có thể dùng local deployment nếu recipe/artifact có sẵn |
| Local deployment qua Greengrass CLI | Có | Có CLI, recipe, artifact và dependency cục bộ |
| Gọi AWS API từ component | Thường không | Chỉ hoạt động nếu endpoint và credentials có thể truy cập |

Greengrass duy trì runtime ở edge, nhưng không biến các AWS cloud APIs thành API cục bộ. Một component gọi S3, DynamoDB hoặc dịch vụ AWS khác vẫn cần đường mạng và credentials hợp lệ.

## 3. Component lifecycle và khả năng chạy độc lập

Mỗi Greengrass component gồm:

- Recipe: tên, version, configuration, dependency, platform compatibility và lifecycle.
- Artifact: script, binary, thư viện hoặc file dữ liệu cần để chạy.
- Dependency: component khác phải có trước hoặc cùng lúc để component hoạt động.

| Trạng thái | Ý nghĩa |
|---|---|
| NEW | Recipe và artifact đã được nạp nhưng component chưa cài. |
| INSTALLED | Đã cài component. |
| STARTING | Đang chạy startup lifecycle. |
| RUNNING | Component đang chạy. |
| FINISHED | Run lifecycle đã kết thúc thành công. |
| ERRORED | Component gặp lỗi và chạy recover lifecycle nếu có. |
| BROKEN | Component lỗi lặp lại và không thể tự phục hồi. |
| STOPPING | Đang chạy shutdown lifecycle. |
| UNINSTALLING / UNINSTALLED | Đang gỡ hoặc đã gỡ component. |

Nếu component chuyển sang ERRORED, Greengrass chạy recover script rồi thử khởi động lại. Nếu component vào ERRORED ba lần mà chưa có lần chạy thành công, nó chuyển sang BROKEN. Vì vậy, một component có retry vô hạn bên trong script nhưng không báo trạng thái đúng cho Greengrass có thể khiến vận hành khó phát hiện.

### 3.1. Thiết kế component chịu được mất cloud

Một edge component nên:

- Khởi động được từ recipe/artifact đã có trên thiết bị.
- Không gọi cloud API trong bước startup nếu chức năng cốt lõi không cần cloud.
- Dùng local IPC hoặc local storage cho hoạt động bắt buộc tại site.
- Tách cloud exporter khỏi local processing để exporter lỗi không kéo component điều khiển dừng theo.
- Có health check, log và recover script phù hợp.
- Xử lý dependency rõ ràng và giới hạn tài nguyên CPU/RAM.

Ví dụ, component điều khiển máy có thể nhận telemetry từ local broker và phát lệnh dừng máy khi nhiệt độ vượt ngưỡng. Một component khác chịu trách nhiệm upload telemetry lên Kinesis. Khi WAN mất, exporter bị gián đoạn nhưng component điều khiển vẫn phải hoạt động.

## 4. Cloud deployment và local deployment

Greengrass hỗ trợ hai cách cập nhật component:

- Cloud deployment: tạo deployment trong AWS IoT Greengrass Cloud, thiết bị nhận deployment qua AWS IoT Jobs.
- Local deployment: tạo deployment trực tiếp trên core device bằng Greengrass CLI hoặc CLI IPC service.

### 4.1. Điều gì xảy ra với cloud deployment khi offline?

Khi core device nhận cloud deployment, nucleus giải quyết dependency. Nucleus ưu tiên tìm component candidate có sẵn trên thiết bị. Với cloud deployment, nucleus có thể gọi AWS Cloud để tìm version mới nhất phù hợp. Nếu thiết bị offline, nó có thể dùng local candidate đã có.

Nếu không có local candidate thỏa version/dependency, deployment thất bại. Không thể tải artifact mới từ cloud khi không có mạng.

Vì vậy, trước khi triển khai offline, cần chuẩn bị sẵn:

- Component recipe.
- Artifact và dependency.
- Phiên bản tương thích với OS/architecture.
- Configuration cần thiết.
- Dung lượng đĩa và quyền truy cập thư mục.

### 4.2. Tạo local deployment

Ví dụ triển khai component đã có recipe và artifact trên Linux core device:

~~~bash
sudo /greengrass/v2/bin/greengrass-cli deployment create \
  --recipeDir ./recipes \
  --artifactDir ./artifacts \
  --merge "com.example.EdgeProcessor=1.0.0"
~~~

Theo dõi deployment:

~~~bash
sudo /greengrass/v2/bin/greengrass-cli deployment list

sudo /greengrass/v2/bin/greengrass-cli deployment status \
  --deploymentId <DEPLOYMENT_ID>
~~~

Local deployment chỉ dùng local candidates. Nếu recipe yêu cầu dependency chưa có và không nằm trong local artifact store, deployment sẽ không thể hoàn tất.

Local deployment status được xem trên thiết bị qua Greengrass CLI; không thể theo dõi local deployment này trong AWS IoT Greengrass console như cloud deployment.

### 4.3. Quản lý thay đổi offline

Một quy trình an toàn:

1. Đóng gói recipe/artifact theo component version.
2. Kiểm tra checksum và chữ ký artifact nếu pipeline phát hành có hỗ trợ.
3. Sao chép gói tới thiết bị bằng kênh quản trị được phê duyệt.
4. Tạo local deployment trong maintenance window.
5. Kiểm tra deployment status và component lifecycle.
6. Chạy smoke test cục bộ.
7. Ghi lại phiên bản đang chạy và kết quả.
8. Khi có mạng, đối chiếu component/version đã chạy với cloud deployment policy và quyết định có cần tạo cloud deployment để đưa thiết bị về baseline hay không.

Tránh để local deployment và cloud deployment quản lý cùng một component theo các phiên bản không được phối hợp. Khi cloud deployment tiếp theo đến, nó có thể thay đổi component set hoặc configuration của target.

## 5. MQTT spooler: lưu message chờ gửi lên AWS IoT Core

Greengrass nucleus quản lý MQTT messages của component khi giao tiếp với AWS IoT Core. Khi core device mất kết nối cloud, nucleus có thể lưu message để thử publish lại khi kết nối phục hồi.

MQTT spooler là cơ chế store-and-forward cho message MQTT outbound. Nó không phải một message broker thay thế AWS IoT Core và cũng không phải kho lưu trữ dài hạn cho mọi loại dữ liệu.

### 5.1. QoS ảnh hưởng thế nào?

| QoS | Hành vi khi core offline |
|---|---|
| QoS 0 | Mặc định bị loại bỏ nếu không thể gửi. Có thể bật keepQos0WhenOffline để spool QoS 0 messages. |
| QoS 1 | Nucleus luôn spool message để gửi lại, trừ khi spool đã đầy. |
| QoS 2 | Không nên mặc định giả định spooler hỗ trợ đầy đủ QoS 2 end-to-end; kiểm tra broker, protocol và bridge cụ thể. |

MQTT QoS 1 là at-least-once. Sau reconnect hoặc retry, consumer có thể nhận message trùng. Ứng dụng downstream cần idempotency key hoặc event ID để tránh xử lý nghiệp vụ hai lần.

### 5.2. Memory spooler và disk spooler

Theo cấu hình Greengrass nucleus hiện hành:

| Thuộc tính | Giá trị mặc định / hỗ trợ |
|---|---|
| storageType | Memory |
| maxSizeInBytes | 2.5 MB cho cache message chưa xử lý trong memory |
| keepQos0WhenOffline | false |
| Disk spooler | Có từ Greengrass nucleus 2.11.0 |
| Disk plugin mặc định | aws.greengrass.DiskSpooler |
| maxPublishRetry | 100 lần |
| maxInFlightPublishes | 5 message QoS 1 chưa ACK cùng lúc |

Nếu cache đầy, message mới bị từ chối. Vì vậy, không nên dùng memory spooler mặc định làm hàng đợi nhiều giờ cho một thiết bị gửi telemetry liên tục.

Disk spooler phù hợp hơn khi cần lưu outbound MQTT lâu hơn và muốn tránh mất queue chỉ vì tiến trình restart. Tuy nhiên, dung lượng đĩa vẫn hữu hạn; cần theo dõi disk usage, quyền thư mục và tốc độ export sau reconnect.

### 5.3. Cấu hình MQTT spooler

Ví dụ phần cấu hình nucleus minh họa cho MQTT 5 và disk spooler:

~~~json
{
  "mqtt": {
    "version": "mqtt5",
    "spooler": {
      "storageType": "Disk",
      "keepQos0WhenOffline": false
    },
    "minimumReconnectDelaySeconds": 1,
    "maximumReconnectDelaySeconds": 120
  }
}
~~~

Đây là cấu hình minh họa cho aws.greengrass.Nucleus. Khi triển khai, hãy dùng configuration update đúng cấu trúc deployment của Greengrass và kiểm tra phiên bản nucleus trên thiết bị. Thay đổi một số MQTT nucleus configuration sẽ restart Greengrass Core software để áp dụng.

maxSizeInBytes mô tả giới hạn cache message chưa xử lý trong memory theo tài liệu nucleus; không coi đây là cấu hình dung lượng đĩa cho Disk spooler.

### 5.4. Retry và reconnect

Với nucleus 2.10.0 trở lên:

- minimumReconnectDelaySeconds mặc định là 1 giây.
- maximumReconnectDelaySeconds mặc định là 120 giây khi dùng MQTT 5.
- Khi dùng MQTT 3, maximumReconnectDelaySeconds bị bỏ qua và mức tối đa cố định là 128 giây.
- minimumConnectedTimeBeforeRetryResetSeconds mặc định 30 giây.

Kết nối chập chờn có thể làm reconnect liên tục. Cần dùng backoff, tránh retry quá nhanh và theo dõi trạng thái ổn định trước khi reset retry delay.

## 6. Local MQTT broker và MQTT bridge

Greengrass hỗ trợ client devices kết nối với core device qua local MQTT broker. Các thiết bị như sensor, camera hoặc gateway PLC có thể gửi dữ liệu cho component xử lý ngay tại site.

Các component hỗ trợ client devices phổ biến:

| Component | Vai trò |
|---|---|
| aws.greengrass.clientdevices.Auth | Xác thực client device và kiểm tra quyền hành động. |
| aws.greengrass.clientdevices.mqtt.Moquette | MQTT broker 3.1.1 cục bộ. |
| aws.greengrass.clientdevices.mqtt.EMQX | MQTT 5 broker cục bộ. |
| aws.greengrass.clientdevices.mqtt.Bridge | Chuyển message giữa LocalMqtt, local Pubsub và AWS IoT Core. |
| aws.greengrass.clientdevices.IPDetector | Công bố endpoint broker để client device khám phá core device. |
| aws.greengrass.ShadowManager | Quản lý local shadows và đồng bộ cloud shadows. |

Core device cần nucleus 2.2.0 trở lên để hỗ trợ client devices. EMQX MQTT 5 broker cần nucleus 2.6.0 trở lên và Client device auth tương thích. AWS khuyến nghị chỉ triển khai một MQTT broker component cho mỗi core device, trừ khi có lý do và cấu hình port riêng.

### 6.1. MQTT bridge có ba hướng message

MQTT bridge có thể chuyển message giữa:

- LocalMqtt: broker cục bộ cho client devices.
- Pubsub: local Greengrass publish/subscribe cho component.
- IotCore: AWS IoT Core MQTT broker.

Ví dụ cấu hình relay message từ client device sang component local và lên cloud:

~~~json
{
  "mqttTopicMapping": {
    "SensorToLocalComponent": {
      "topic": "factory/line1/telemetry",
      "source": "LocalMqtt",
      "target": "Pubsub"
    },
    "SensorToCloud": {
      "topic": "factory/line1/telemetry",
      "source": "LocalMqtt",
      "target": "IotCore"
    },
    "LocalAlarmToSensor": {
      "topic": "factory/line1/alarm",
      "source": "Pubsub",
      "target": "LocalMqtt"
    }
  }
}
~~~

Khi WAN mất, route LocalMqtt → Pubsub và Pubsub → LocalMqtt vẫn có thể chạy vì chỉ dùng thành phần cục bộ. Route tới IotCore không thể chuyển message trong thời gian cloud không truy cập được; message outbound được xử lý theo MQTT spooler và bridge behavior.

MQTT bridge dùng QoS 1 khi publish/subscribe tới AWS IoT Core, ngay cả khi client device dùng QoS 0 ở local broker. Điều này có thể tăng latency khi relay lên cloud.

### 6.2. Tránh loop message

Nếu tạo route hai chiều giữa LocalMqtt và IotCore, message có thể quay lại nguồn và tạo vòng lặp. Với MQTT 5 bridge, có thể cấu hình noLocal cho route có source LocalMqtt để tránh relay message mà bridge tự publish.

Thiết kế topic rõ ràng, dùng prefix khác nhau cho upstream/downstream và kiểm tra loop trong môi trường thử nghiệm trước khi rollout.

## 7. Xác thực client devices khi core offline

Thông thường, core device cần cloud để xác thực client device. Greengrass có hỗ trợ offline authentication thông qua Client device auth component.

Điều kiện chính:

- Client device auth component version 2.3.0 trở lên.
- Client device phải được xác thực và đăng ký với AWS IoT khi core có cloud connectivity lần đầu.
- Core device lưu thông tin thiết bị đã xác thực cục bộ.
- Khi core mất cloud connection, nó có thể dùng thông tin đã lưu để xác thực client device đã từng kết nối.

### 7.1. Thời gian tin cậy offline

Tham số clientDeviceTrustDurationMinutes quyết định thời gian lưu credential/trust information.

- Mặc định: 1 phút, gần như tắt offline authentication.
- Có thể cấu hình từ 1 phút tới 2,147,483,647 phút.
- Core cập nhật credential store khi client kết nối lần đầu, khi client reconnect trong lúc core có cloud connection và theo chu kỳ hàng ngày khi core online.
- Chỉ các client device được associate với core mới được làm mới qua API tương ứng.

Không nên đặt trust duration quá dài chỉ để tiện vận hành. Thời gian dài làm tăng khả năng một client đã bị thu hồi certificate vẫn được core chấp nhận trong thời gian offline. Hãy cân bằng thời gian outage dự kiến với yêu cầu bảo mật.

### 7.2. Local discovery và giới hạn

Client devices có thể dùng cloud discovery để tìm core device. Nếu thiết bị chưa có thông tin endpoint broker, lần đầu khám phá có thể cần cloud. Trong môi trường offline, hãy provision sẵn endpoint hoặc dùng discovery strategy cục bộ đã được kiểm thử.

Offline authentication chỉ giúp client đã biết kết nối tới core trong lúc core không gọi được cloud; nó không thay thế TLS, certificate lifecycle hoặc authorization policy cho MQTT topic.

## 8. Local publish/subscribe qua IPC

Greengrass component có thể trao đổi message bằng local publish/subscribe IPC. Đây là message broker cục bộ giữa các component trên cùng core device.

Ví dụ:

- sensor-ingest publish factory/line1/telemetry.
- edge-rule-engine subscribe telemetry và phát cảnh báo.
- local-dashboard subscribe trạng thái đã xử lý.
- cloud-exporter đọc dữ liệu cần chuyển lên cloud.

Local IPC không đồng nghĩa AWS IoT Core MQTT. Muốn gửi message lên AWS IoT Core, component phải dùng API/IPC phù hợp hoặc cấu hình MQTT bridge.

### 8.1. Authorization cho IPC

Component cần được cấp quyền publish/subscribe trong recipe. Ví dụ policy rút gọn:

~~~json
{
  "accessControl": {
    "aws.greengrass.ipc.pubsub": {
      "com.example.EdgeProcessor:pubsub:1": {
        "policyDescription": "Allow local telemetry topics",
        "operations": [
          "aws.greengrass#PublishToTopic",
          "aws.greengrass#SubscribeToTopic"
        ],
        "resources": [
          "factory/line1/telemetry",
          "factory/line1/alarm"
        ]
      }
    }
  }
}
~~~

Dùng topic scope cụ thể theo component. Không cấp quyền toàn bộ topic nếu component chỉ cần một số kênh. Wildcard * trong authorization resource không giống MQTT wildcard # hoặc +; hãy đọc đúng semantics của nucleus version đang dùng.

## 9. Stream Manager: lưu dữ liệu tại edge và export khi có mạng

Stream Manager là component quản lý data streams trên Greengrass core device. Nó phù hợp với telemetry có volume lớn, dữ liệu sensor, time-series, batch upload hoặc dữ liệu cần ưu tiên theo mức quan trọng.

Stream Manager cho phép:

- Ghi dữ liệu vào local stream.
- Đặt storage type, size và retention policy theo stream.
- Cấu hình export destination.
- Điều chỉnh bandwidth và timeout.
- Đặt priority để stream quan trọng được export trước.
- Cho component đọc, lọc, aggregate và phân tích dữ liệu cục bộ trước khi upload.

### 9.1. Quy trình store-and-forward

~~~mermaid
flowchart LR
    S["Sensors / PLC"] --> C["Edge component"]
    C --> F["Filter / compress / enrich"]
    F --> SM["Stream Manager local storage"]
    SM --> L["Local analytics / control"]
    SM --> Q["Pending export queue"]
    Q -->|WAN restored| K["Kinesis Data Streams"]
    Q -->|WAN restored| S3["Amazon S3"]
    Q -->|WAN restored| SW["AWS IoT SiteWise"]
~~~

Component ghi dữ liệu vào Stream Manager bằng Stream Manager SDK. Khi có kết nối, Stream Manager export dữ liệu theo destination và policy đã cấu hình.

### 9.2. AWS Cloud destinations hiện hành

Stream Manager hỗ trợ export tới:

- Amazon Kinesis Data Streams.
- Amazon S3 objects.
- AWS IoT SiteWise asset properties.

AWS IoT Analytics đã discontinued ngày 15-12-2025; export tới IoT Analytics channel không còn hoạt động. Không cấu hình destination này cho dự án mới và cần gỡ các IoTAnalyticsConfig cũ để tránh export retry lỗi liên tục.

### 9.3. Cấu hình Stream Manager

Các tham số thường dùng:

| Tham số | Ý nghĩa |
|---|---|
| STREAM_MANAGER_STORE_ROOT_DIR | Thư mục local lưu stream; phải tồn tại và user chạy component có quyền đọc/ghi. |
| STREAM_MANAGER_AUTHENTICATE_CLIENT | Xác thực client SDK; mặc định true, chỉ Greengrass components được truy cập. |
| STREAM_MANAGER_EXPORTER_MAX_BANDWIDTH | Giới hạn bandwidth trung bình dùng cho export; mặc định cho phép dùng bandwidth sẵn có. |
| STREAM_MANAGER_EXPORTER_THREAD_POOL_SIZE | Số thread export tối đa; mặc định 5. |
| STREAM_MANAGER_SERVER_PORT | Port local của Stream Manager; mặc định 8088. |
| STREAM_MANAGER_EXPORTER_KINESIS_INTER_CALL_DELAY_MS | Delay fallback giữa request Kinesis khi không xác định được shard layout; mặc định 1000 ms. |

Stream Manager cần tối thiểu khoảng 70 MB RAM ngoài phần Greengrass Core software. Tổng tài nguyên thực tế phụ thuộc số stream, throughput và export concurrency.

### 9.4. Bảo mật dữ liệu Stream Manager

Một điểm quan trọng: Stream Manager không mã hóa stream data at rest hoặc dữ liệu truyền giữa các local component trên cùng core device theo mặc định.

- Dữ liệu local dựa vào file permission và full-disk encryption nếu bật.
- Dữ liệu export lên AWS Cloud dùng TLS.
- Client authentication mặc định bật (true); không tắt nếu không có lý do rõ ràng.
- Thư mục store phải được giới hạn quyền truy cập.
- Nếu đổi STREAM_MANAGER_STORE_ROOT_DIR, Greengrass không tự xóa thư mục cũ và dữ liệu cũ.

Với dữ liệu nhạy cảm, bật mã hóa toàn bộ đĩa, giới hạn user/process trên edge và bảo vệ thiết bị khỏi truy cập vật lý trái phép.

## 10. Local device shadows và đồng bộ trạng thái

Device Shadow là JSON document lưu trạng thái mong muốn (desired) và trạng thái thiết bị báo cáo (reported). Greengrass Shadow Manager cung cấp local shadow service để component đọc/ghi shadow trên core device ngay cả khi thiết bị không kết nối AWS IoT Core.

Khi cloud connectivity phục hồi, Shadow Manager đồng bộ các shadow đã cấu hình với AWS IoT Core.

### 10.1. Shadow hữu ích cho trạng thái, không phải hàng đợi event

Ví dụ:

- desired: tốc độ motor cần đặt là 1200 RPM.
- reported: tốc độ motor hiện tại là 1180 RPM.
- metadata: timestamp của các thuộc tính.

Nếu WAN mất, local component vẫn có thể đọc desired state đã lưu và cập nhật reported state cục bộ. Khi reconnect, Shadow Manager đồng bộ theo cấu hình.

Không dùng shadow làm kho lưu mọi telemetry event. Shadow biểu diễn trạng thái mới nhất; nếu cần giữ từng event theo thứ tự, dùng Stream Manager hoặc durable queue.

### 10.2. Cấu hình đồng bộ

Shadow Manager không đồng bộ mọi shadow lên cloud theo mặc định. Cần cấu hình synchronize và chỉ định thing/shadow names.

Có thể chọn:

- realTime: đồng bộ khi mỗi thay đổi xảy ra.
- periodic: đồng bộ theo khoảng thời gian.
- betweenDeviceAndCloud: hai chiều.
- deviceToCloud: local state ghi lên cloud.
- cloudToDevice: cloud state ghi xuống local.

Với Shadow Manager v2.2.0 trở lên, có thể chọn hướng đồng bộ một chiều. Nếu hai phía cùng thay đổi trong lúc offline, xung đột được xử lý theo direction và version của Shadow Manager. Với đồng bộ hai chiều, desired-state conflict có thể ưu tiên giá trị cloud, còn reported-state conflict có thể ưu tiên giá trị local theo quy tắc của dịch vụ.

Hãy chọn direction theo source of truth của từng thuộc tính. Ví dụ, desired setpoint có thể do cloud điều khiển, còn reported temperature do thiết bị sở hữu.

## 11. Reconnect và đồng bộ sau khi có mạng

Khi Internet phục hồi, không nên cho mọi thiết bị upload toàn bộ backlog cùng lúc. Một fleet lớn có thể tạo reconnect storm và vượt quota của AWS IoT Core hoặc dịch vụ đích.

Một quy trình phục hồi nên gồm:

1. Nucleus thiết lập lại MQTT connection với AWS IoT Core.
2. Các message đang chờ trong MQTT spooler được retry theo cấu hình.
3. Stream Manager tiếp tục export các stream có destination cloud.
4. Shadow Manager đồng bộ local/cloud shadows.
5. Component có thể gọi AWS APIs khi network và credentials hoạt động trở lại.
6. Thiết bị gửi status/health và backlog metrics.
7. Backend xử lý duplicate, late events và dữ liệu theo thứ tự nghiệp vụ.
8. Sau khi backlog giảm, hệ thống quay lại chế độ ingest bình thường.

### 11.1. Giảm reconnect storm

- Dùng exponential backoff và jitter trong custom exporter.
- Giới hạn số worker upload đồng thời.
- Đặt export bandwidth phù hợp đường truyền site.
- Ưu tiên alarm và event quan trọng hơn raw telemetry.
- Không restart toàn bộ component chỉ vì một cloud request timeout.
- Chỉ đánh dấu backlog đã gửi sau khi nhận acknowledgement phù hợp.
- Có circuit breaker cho destination liên tục lỗi.

### 11.2. Xử lý duplicate và thứ tự

QoS 1 và retry có thể tạo duplicate. Nên gắn mỗi event với:

- deviceId.
- eventId duy nhất.
- sequenceNumber theo thiết bị hoặc stream.
- eventTimestamp.
- schemaVersion.
- createdAt và ingestedAt.

Cloud consumer cần idempotent: cùng eventId đến nhiều lần chỉ được áp dụng một lần. Nếu thứ tự nghiệp vụ quan trọng, dùng sequenceNumber và xử lý gap/reorder ở downstream thay vì dựa vào thứ tự arrival sau reconnect.

## 12. Dung lượng lưu trữ và backpressure

Offline duration có thể kéo dài hàng giờ hoặc nhiều ngày. Nếu thiết bị tạo dữ liệu nhanh hơn tốc độ export sau reconnect, backlog sẽ tiếp tục tăng ngay cả khi mạng đã phục hồi.

Ước tính storage cơ bản:

\[
Storage \approx IngressRate \times OfflineDuration \times SafetyFactor
\]

Ví dụ thiết bị tạo 80 KB/s và cần chịu outage 6 giờ:

\[
80 \times 3600 \times 6 = 1{,}728{,}000\text{ KB}
\]

Tương đương khoảng 1.65 GiB dữ liệu thô. Thực tế cần cộng overhead metadata, file format, retry, logs và phần dự phòng.

### 12.1. Thiết kế policy khi gần đầy

Cần xác định trước:

- Dữ liệu nào phải giữ tuyệt đối.
- Dữ liệu nào có thể lấy mẫu hoặc tổng hợp.
- Dữ liệu nào có thể drop khi vượt ngưỡng.
- Thứ tự ưu tiên khi export.
- Thời hạn tối đa giữ backlog.
- Alert khi disk usage hoặc queue depth vượt ngưỡng.
- Quy trình operator can thiệp khi không thể upload.

Ví dụ, alarm sự cố máy có thể giữ ở priority cao, telemetry nhiệt độ định kỳ có thể downsample khi storage gần đầy, còn raw camera frame có thể không lưu nếu vượt retention.

Không dùng một queue chung cho cả alarm, raw telemetry và debug logs nếu các dữ liệu có retention/priority khác nhau.

## 13. Security và quyền truy cập trong môi trường offline

Mất kết nối không làm giảm yêu cầu bảo mật. Thiết bị offline có thể không nhận được cập nhật certificate, policy hoặc component security patch kịp thời.

Best practices:

- Dùng unique device certificate cho từng core/client device.
- Giới hạn clientDeviceTrustDurationMinutes theo outage SLA.
- Thu hồi hoặc rotate certificate theo quy trình khi thiết bị reconnect.
- Cấp IAM policy least privilege cho Greengrass device role.
- Giới hạn S3/Kinesis/SiteWise destination theo resource cụ thể.
- Dùng TLS cho cloud communication.
- Bật full-disk encryption cho Stream Manager data.
- Dùng local component authorization cho IPC topics.
- Giới hạn quyền local MQTT theo client group/topic.
- Bảo vệ Greengrass CLI và local debug console.
- Không để component local deployment tự ý thay đổi nucleus hoặc component nhạy cảm nếu không cần thiết.
- Ghi audit local và đồng bộ log khi có mạng.

Một component có quyền tạo local deployment hoặc restart component khác có thể thay đổi hành vi thiết bị mà không cần cloud. Chỉ cấp Greengrass CLI IPC permission cho component quản trị được tin cậy.

## 14. Logging và monitoring khi offline

Greengrass Core software ghi log mặc định vào local filesystem:

/greengrass/v2/logs/greengrass.log

Component generic thường có log riêng theo component name trong cùng thư mục. Khi mất kết nối, log local vẫn có thể được ghi; khi có mạng, có thể cấu hình Log Manager để gửi log tới CloudWatch Logs.

Các metric cần theo dõi:

| Metric / tín hiệu | Ý nghĩa |
|---|---|
| MQTT connection state | Core có kết nối AWS IoT Core không |
| Reconnect attempts | Tần suất reconnect và thời gian gián đoạn |
| Spooler queue size | Số lượng/bytes message đang chờ |
| Spooler rejection | Message bị từ chối do cache đầy |
| Stream Manager stream size | Dung lượng backlog theo stream |
| Export lag | Độ trễ từ lúc ghi local đến lúc export thành công |
| Disk free space | Dung lượng còn lại trên edge |
| Component lifecycle | RUNNING, ERRORED, BROKEN hoặc FINISHED |
| Local deployment status | QUEUED, IN_PROGRESS, SUCCEEDED hoặc FAILED |
| Shadow sync lag | Trạng thái local/cloud đã đồng bộ đến đâu |
| Client authentication failures | Số client bị từ chối do trust hoặc authorization |
| Duplicate event rate | Tỷ lệ event trùng khi replay/reconnect |

Đặt alert theo thời gian offline, dung lượng còn lại, số message bị reject và backlog age. Đừng chỉ cảnh báo khi thiết bị chuyển offline; cần cảnh báo cả khi thiết bị online lại nhưng backlog không giảm.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Component local vẫn chạy nhưng không thấy dữ liệu cloud | WAN mất hoặc bridge không kết nối AWS IoT Core | Kiểm tra nucleus log, MQTT endpoint, DNS, firewall và certificate |
| QoS 0 message bị mất sau outage | keepQos0WhenOffline=false | Dùng QoS 1 cho dữ liệu cần đảm bảo hoặc bật QoS 0 spooling nếu phù hợp |
| Message outbound bị reject | Spooler cache đầy | Kiểm tra storageType, capacity, export throughput và retry |
| Disk spooler không hoạt động | Nucleus version dưới 2.11 hoặc plugin/config sai | Kiểm tra nucleus version và DiskSpooler dependency |
| Client device không kết nối khi core offline | Offline auth chưa bật hoặc trust duration hết hạn | Kiểm tra Client device auth >=2.3, credential cache và associated device |
| Client kết nối được broker nhưng không publish | Authorization policy không cho topic/action | Kiểm tra device group và mqtt:publish/mqtt:subscribe permissions |
| Component không nhận MQTT từ client | Thiếu MQTT bridge route LocalMqtt → Pubsub | Kiểm tra mqttTopicMapping và local Pubsub subscription |
| MQTT bridge không đẩy cloud | WAN hoặc IAM/device role lỗi | Kiểm tra IotCore route, IoT policy và cloud connection |
| Stream Manager export retry liên tục | Destination IAM, KMS, quota hoặc endpoint lỗi | Kiểm tra role, destination resource, local log và CloudWatch |
| Stream Manager không ghi được stream | Disk permission hoặc store directory không tồn tại | Kiểm tra STREAM_MANAGER_STORE_ROOT_DIR và quyền user |
| Shadow local và cloud khác nhau | Có thay đổi đồng thời trong outage | Kiểm tra sync direction và merge conflict policy |
| Cloud deployment không thể áp dụng offline | Thiếu local candidate/dependency/artifact | Chuẩn bị recipe/artifact local và tạo local deployment |
| Component chuyển BROKEN | Lỗi lifecycle lặp lại | Xem component log, recover script và dependency |
| Không thấy log trên CloudWatch | Thiết bị offline hoặc Log Manager/IAM chưa cấu hình | Đọc log local và kiểm tra log upload sau reconnect |
| Backlog không giảm sau reconnect | Ingress rate cao hơn export rate hoặc destination throttle | Giảm ingest, tăng export capacity và điều chỉnh priority |

### 15.1. Lệnh kiểm tra tại core device

Linux:

~~~bash
sudo systemctl status greengrass.service

sudo tail -n 100 /greengrass/v2/logs/greengrass.log

sudo /greengrass/v2/bin/greengrass-cli component list

sudo /greengrass/v2/bin/greengrass-cli deployment list
~~~

Kiểm tra component log riêng:

~~~bash
sudo tail -f /greengrass/v2/logs/com.example.EdgeProcessor.log
~~~

Trên Windows, dùng PowerShell Get-Content để đọc file log trong C:\greengrass\v2\logs.

## 16. Tình huống thực hành: gateway nhà máy mất Internet 8 giờ

Một nhà máy có gateway chạy Greengrass với các thiết bị:

- 12 PLC gửi trạng thái mỗi giây.
- 30 cảm biến nhiệt độ/áp suất.
- Một edge component phát hiện quá nhiệt và gửi lệnh dừng máy cục bộ.
- Một component analytics tổng hợp sản lượng.
- Một component exporter gửi dữ liệu lên Kinesis và S3.
- Shadow Manager đồng bộ desired/reported state với cloud.

### 16.1. Thiết kế khi online

- Client devices kết nối local MQTT broker.
- MQTT bridge chuyển telemetry vào local Pubsub.
- Edge processor đọc Pubsub và áp business rules.
- Stream Manager ghi raw telemetry và alarm events.
- Alarm events có priority cao hơn telemetry định kỳ.
- Shadow Manager đồng bộ trạng thái máy.
- Exporter gửi dữ liệu lên Kinesis/S3.

### 16.2. Khi Internet bị ngắt

- PLC vẫn gửi dữ liệu tới local MQTT broker.
- Edge processor tiếp tục kiểm tra ngưỡng và điều khiển tại chỗ.
- Local dashboard vẫn hiển thị trạng thái.
- MQTT spooler lưu outbound MQTT messages theo QoS và capacity.
- Stream Manager lưu telemetry trong local storage.
- Shadow Manager cập nhật local reported state.
- Client device đã được xác thực trước đó có thể tiếp tục kết nối nếu trust duration còn hiệu lực.
- Cloud deployment mới và cloud API calls bị gián đoạn.

### 16.3. Khi Internet phục hồi

1. Nucleus reconnect AWS IoT Core.
2. MQTT spooler gửi lại message còn trong queue.
3. Stream Manager export alarm trước, sau đó telemetry theo priority.
4. Shadow Manager đồng bộ desired/reported state.
5. Cloud consumer deduplicate theo eventId.
6. Dashboard hiển thị backlog age và số event đã replay.
7. Operator xác nhận không có event bị reject hoặc mất do storage đầy.

### 16.4. Tiêu chí nghiệm thu

- Máy vẫn dừng đúng khi nhiệt độ vượt ngưỡng trong suốt outage.
- Không phụ thuộc cloud API cho vòng điều khiển an toàn.
- Không mất alarm event trong outage theo storage/retention SLA.
- Event duplicate được xử lý idempotent.
- Shadow conflict được giải quyết theo source of truth.
- Backlog được export hết trong thời gian mục tiêu sau reconnect.
- Component có thể restart sau reboot mà không mất trạng thái cần thiết.

## 17. Bài thực hành: mô phỏng offline và reconnect

Mục tiêu là kiểm tra một component cục bộ tiếp tục hoạt động và dữ liệu được chuyển lên cloud sau khi mạng phục hồi.

### Bước 1: Chuẩn bị core device

Cài Greengrass Core software, triển khai component xử lý telemetry và local MQTT broker. Đảm bảo component đã cài đủ recipe/artifact/dependency.

### Bước 2: Thiết lập local message path

Cấu hình MQTT bridge để relay từ LocalMqtt sang Pubsub. Viết component subscribe local topic và log event ID/timestamp.

### Bước 3: Thiết lập lưu đệm

Cấu hình MQTT spooler phù hợp. Với dữ liệu volume lớn, deploy Stream Manager và tạo stream có export destination tới Kinesis hoặc S3.

### Bước 4: Ngắt WAN

Chặn đường Internet của core device trong môi trường test, nhưng giữ LAN giữa client devices và core. Tiếp tục publish telemetry và quan sát local processing.

### Bước 5: Kiểm tra offline authentication

Nếu dùng client device auth, kết nối client lần đầu khi core online. Cấu hình trust duration trong môi trường thử nghiệm, sau đó ngắt WAN và kiểm tra client đã biết có thể reconnect.

### Bước 6: Kiểm tra local deployment

Chuẩn bị recipe/artifact mới trên thiết bị và tạo local deployment. Xác nhận deployment status và component lifecycle.

### Bước 7: Khôi phục WAN

Mở lại Internet. Theo dõi MQTT reconnect, spooler backlog, Stream Manager export và Shadow Manager synchronization.

### Bước 8: Đối chiếu dữ liệu

So sánh số event được phát, lưu local, export thành công và event bị duplicate. Kiểm tra eventId, sequenceNumber và timestamps.

Không thử nghiệm ngắt mạng trên hệ thống điều khiển production đang vận hành. Dùng thiết bị/lab có cơ chế an toàn độc lập.

## 18. Những hiểu lầm thường gặp

1. **Greengrass offline nghĩa là mọi AWS service vẫn hoạt động.** Chỉ các chức năng cục bộ và dữ liệu đã lưu có thể tiếp tục; cloud API cần mạng.
2. **Local MQTT broker giống AWS IoT Core.** Local broker xử lý client devices tại site; AWS IoT Core là cloud broker.
3. **MQTT bridge tự lưu mọi dữ liệu vô hạn.** Bridge chuyển message; spooler có capacity hữu hạn.
4. **QoS 0 luôn được giữ khi offline.** Mặc định QoS 0 bị drop; cần keepQos0WhenOffline=true.
5. **QoS 1 đảm bảo exactly-once.** QoS 1 là at-least-once; consumer cần xử lý duplicate.
6. **Memory spooler phù hợp outage dài.** Cache memory mặc định chỉ 2.5 MB.
7. **Disk spooler có dung lượng vô hạn.** Dung lượng đĩa và filesystem vẫn giới hạn.
8. **Stream Manager chỉ hoạt động khi online.** Stream Manager có thể lưu và xử lý stream cục bộ khi mất mạng.
9. **Shadow là message queue.** Shadow biểu diễn trạng thái mới nhất/desired, không lưu mọi event.
10. **Client device nào cũng xác thực offline được.** Client cần được xác thực trước khi core mất cloud và trust duration còn hiệu lực.
11. **Cloud deployment luôn áp dụng được offline.** Chỉ local candidates và artifact có sẵn mới có thể được dùng khi offline.
12. **Local deployment xuất hiện trong console.** Cần kiểm tra local deployment bằng Greengrass CLI trên thiết bị.
13. **Mất WAN đồng nghĩa component dừng.** Component đã cài và có dependency cục bộ có thể tiếp tục chạy.
14. **Có mạng trở lại là backlog tự xử lý ngay.** Cần capacity, retry, priority và idempotency để tránh nghẽn hoặc duplicate.
15. **Stream Manager local data được mã hóa mặc định.** Local data at rest/in transit giữa component không được mã hóa mặc định.
16. **Có thể export Stream Manager tới AWS IoT Analytics.** AWS IoT Analytics đã discontinued ngày 15-12-2025.

## 19. Câu hỏi tự kiểm tra

**1. Greengrass nucleus có vai trò gì?**

Là runtime bắt buộc quản lý component, deployment, IPC và kết nối cloud của Greengrass Core software.

**2. Component đã cài có tiếp tục chạy khi mất Internet không?**

Có, nếu core device vẫn hoạt động và component có đủ dependency/artifact cục bộ.

**3. Local deployment khác cloud deployment thế nào?**

Local deployment chạy trực tiếp trên core device bằng recipe/artifact/candidate local; cloud deployment được gửi từ AWS IoT Greengrass Cloud qua AWS IoT Jobs.

**4. Khi cloud deployment đến lúc thiết bị offline, nucleus làm gì?**

Nucleus có thể dùng local candidate phù hợp; nếu không có candidate/dependency phù hợp thì deployment thất bại.

**5. MQTT spooler làm gì?**

Lưu message MQTT outbound chưa gửi được tới AWS IoT Core để retry khi kết nối phục hồi.

**6. QoS 0 có được spool mặc định không?**

Không. Mặc định keepQos0WhenOffline=false.

**7. QoS 1 có thể tạo duplicate không?**

Có. QoS 1 là at-least-once, vì vậy consumer cần idempotency.

**8. Disk spooler có từ phiên bản nào?**

Greengrass nucleus 2.11.0 trở lên.

**9. Client device offline authentication cần điều kiện gì?**

Client device auth >=2.3.0, client đã được xác thực khi core online và trust duration còn hiệu lực.

**10. Stream Manager giải quyết vấn đề gì?**

Lưu, quản lý retention/priority và export dữ liệu IoT từ edge khi có kết nối.

**11. Stream Manager export được tới những destination nào?**

Amazon Kinesis Data Streams, Amazon S3 và AWS IoT SiteWise.

**12. Vì sao không dùng Device Shadow làm telemetry queue?**

Shadow lưu trạng thái mới nhất; nó không được thiết kế để lưu mọi event theo thứ tự.

**13. Local Pubsub có gửi thẳng tới AWS IoT Core không?**

Không. Cần MQTT bridge hoặc API/IPC phù hợp để chuyển message tới cloud.

**14. Điều gì xảy ra khi Stream Manager local storage đầy?**

Ứng dụng không thể tiếp tục giả định dữ liệu được lưu; cần capacity alert và policy xử lý overflow theo thiết kế.

**15. Khi nào cần local deployment?**

Khi cần cài/cập nhật component tại site mà không có cloud connectivity, với điều kiện recipe/artifact/dependency đã có cục bộ.

**16. Tại sao cần idempotency sau reconnect?**

Message có thể được retry hoặc replay và xuất hiện nhiều lần; idempotency ngăn cùng event gây tác động nghiệp vụ lặp.

## 20. Checklist production

- [ ] Đã phân loại outage: WAN, AWS IoT Core, LAN, client device hay core hardware.
- [ ] Local control path không phụ thuộc cloud API.
- [ ] Core device có đủ CPU, RAM, disk và system service tự khởi động.
- [ ] Component recipe/artifact/dependency cần thiết có sẵn cục bộ.
- [ ] Component lifecycle và recover script đã được kiểm thử.
- [ ] Cloud deployment và local deployment có quy trình phối hợp.
- [ ] MQTT spooler có storage mode và capacity phù hợp outage SLA.
- [ ] Đã xác định hành vi QoS 0 và QoS 1.
- [ ] Có xử lý duplicate bằng eventId/idempotency.
- [ ] Reconnect có backoff và không tạo reconnect storm.
- [ ] Local MQTT broker và MQTT bridge có topic mapping rõ ràng.
- [ ] Client device auth có trust duration phù hợp và client đã provision trước.
- [ ] IPC authorization giới hạn topic theo component.
- [ ] Stream Manager có local storage, retention, priority và export target.
- [ ] Có cảnh báo disk usage, spooler backlog và export lag.
- [ ] Không dùng AWS IoT Analytics làm Stream Manager destination.
- [ ] Shadow Manager sync đúng shadow names, direction và conflict policy.
- [ ] Stream Manager local data được bảo vệ bằng file permission/full-disk encryption.
- [ ] Greengrass CLI/local debug console có quyền truy cập hạn chế.
- [ ] Local logs đủ dung lượng và được export khi reconnect.
- [ ] Có runbook kiểm tra nucleus, component, deployment, spooler và stream manager.
- [ ] Đã thử nghiệm WAN outage, reboot, reconnect, backlog replay và duplicate event.
- [ ] Có tiêu chí nghiệm thu về data loss, recovery time và backlog drain time.

## Tài liệu tham khảo

- [How AWS IoT Greengrass works](https://docs.aws.amazon.com/greengrass/v2/developerguide/how-it-works.html)
- [Greengrass nucleus component](https://docs.aws.amazon.com/greengrass/v2/developerguide/greengrass-nucleus-component.html)
- [Configure the AWS IoT Greengrass Core software](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-greengrass-core-v2.html)
- [Resilience in AWS IoT Greengrass](https://docs.aws.amazon.com/greengrass/v2/developerguide/disaster-recovery-resiliency.html)
- [Develop AWS IoT Greengrass components](https://docs.aws.amazon.com/greengrass/v2/developerguide/develop-greengrass-components.html)
- [AWS IoT Greengrass component recipe reference](https://docs.aws.amazon.com/greengrass/v2/developerguide/component-recipe-reference.html)
- [Deploy AWS IoT Greengrass components to devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-deployments.html)
- [Local deployment with Greengrass CLI](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html)
- [Manage local deployments and components with IPC](https://docs.aws.amazon.com/greengrass/v2/developerguide/ipc-local-deployments-components.html)
- [Configure MQTT timeouts and cache settings](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-greengrass-core-v2.html)
- [Authenticate clients while offline](https://docs.aws.amazon.com/greengrass/v2/developerguide/offline-authentication.html)
- [Connect client devices to core devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/connect-client-devices.html)
- [Interact with local IoT devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/interact-with-local-iot-devices.html)
- [MQTT bridge component](https://docs.aws.amazon.com/greengrass/v2/developerguide/mqtt-bridge-component.html)
- [Publish/subscribe local messages](https://docs.aws.amazon.com/greengrass/v2/developerguide/ipc-publish-subscribe.html)
- [Manage data streams on Greengrass core devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-data-streams.html)
- [Configure AWS IoT Greengrass Stream Manager](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-stream-manager.html)
- [Use StreamManagerClient to work with streams](https://docs.aws.amazon.com/greengrass/v2/developerguide/work-with-streams.html)
- [Interact with device shadows](https://docs.aws.amazon.com/greengrass/v2/developerguide/interact-with-shadows.html)
- [Sync local device shadows with AWS IoT Core](https://docs.aws.amazon.com/greengrass/v2/developerguide/sync-shadows-with-iot-core.html)
- [Monitor AWS IoT Greengrass logs](https://docs.aws.amazon.com/greengrass/v2/developerguide/monitor-logs.html)
- [Troubleshooting AWS IoT Greengrass V2](https://docs.aws.amazon.com/greengrass/v2/developerguide/troubleshooting.html)

