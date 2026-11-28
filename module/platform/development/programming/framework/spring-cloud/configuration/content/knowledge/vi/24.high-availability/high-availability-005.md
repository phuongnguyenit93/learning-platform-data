# Sự cố kho Git, Vault hoặc broker và ảnh hưởng tới từng luồng

Spring Cloud Config thường phụ thuộc nhiều hệ thống bên ngoài: Git lưu cấu hình ứng dụng, Vault cung cấp bí mật, còn RabbitMQ hoặc Kafka chuyển sự kiện refresh qua Spring Cloud Bus. Khi một dependency gặp sự cố, mức độ ảnh hưởng không giống nhau. Git có thể ngừng truy cập nhưng Config Server vẫn phục vụ bản clone cục bộ; Vault bị seal có thể khiến request chứa secret thất bại; broker ngừng hoạt động có thể làm mất luồng refresh phân tán trong khi API lấy cấu hình trực tiếp vẫn chạy.

Muốn thiết kế độ sẵn sàng đúng, cần phân biệt từng luồng: ứng dụng lấy cấu hình lúc khởi động, ứng dụng refresh trực tiếp, Config Server phát sự kiện refresh qua Bus, và Config Server đọc bí mật từ Vault. Cần biết dependency nào nằm trên đường đi của từng luồng, dữ liệu nào còn được cache, lúc nào hệ thống fail fast và cách xác minh sau khi dependency phục hồi.

## 1. Bản đồ các luồng và dependency

Một triển khai thường có kiến trúc khái quát:

```text
                         +------------------+
                         | Git repository   |
                         +---------+--------+
                                   |
                                   v
+-------------+        +-----------+------------+       +----------------+
| Config      |------->| Spring Cloud Config   |------>| Vault cluster  |
| Client      | HTTP   | Server                 | HTTPS | secrets        |
+------+------+        +-----------+------------+       +----------------+
       ^                            |
       |                            | publish refresh event
       |                            v
       |                  +---------+----------+
       +------------------| RabbitMQ / Kafka  |
         receive event    | Spring Cloud Bus  |
                          +--------------------+
```

| Luồng | Thành phần bắt buộc trên đường đi | Dependency nào không trực tiếp tham gia |
|---|---|---|
| Startup Config Data | Config Client → Config Server → Environment Repository | Broker không cần thiết nếu chỉ lấy cấu hình HTTP |
| Refresh trực tiếp | Client refresh endpoint → Config Server → repository | Broker không cần thiết |
| Refresh phân tán | Git webhook hoặc thao tác vận hành → Config Server → broker → các client | Broker là chặng bắt buộc để fan-out qua Bus |
| Đọc secret | Config Server → Vault, hoặc client đọc Vault theo kiến trúc riêng | Git có thể không liên quan nếu secret nằm hoàn toàn trong Vault |
| Health/diagnostics | Health indicator, repository probe, broker/Vault/Git metrics | Một health check tổng quát không thay thế kiểm tra từng luồng |

Không nên gộp mọi dependency thành một trạng thái “Config Server UP/DOWN”. Cần đo riêng khả năng phục vụ cấu hình đã cache, khả năng lấy revision mới, khả năng đọc secret và khả năng phát sự kiện đến tất cả client.

## 2. Khi kho Git không truy cập được

### Git hỏng trước khi Config Server clone lần đầu

Config Server dùng Git backend thường clone repository theo yêu cầu đầu tiên (lazy clone). Vì vậy, Config Server có thể khởi động thành công dù URI sai, credential hết hạn hoặc Git host đang down. Lỗi chỉ xuất hiện khi có client yêu cầu cấu hình thuộc repository đó.

Nếu muốn phát hiện lỗi trước khi nhận traffic, bật `clone-on-start`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          clone-on-start: true
```

Khi bật, Config Server clone repository lúc khởi động và có thể fail fast nếu Git không truy cập được. Cách này làm startup phụ thuộc Git nhiều hơn, nhưng giúp readiness phản ánh sớm lỗi cấu hình backend.

### Git hỏng sau khi Config Server đã clone thành công

Sau khi clone, Config Server giữ một working copy cục bộ. Nếu Git server mất kết nối, Config Server vẫn có thể phục vụ các application/profile/label có trong working copy đó. Đây là cơ chế cache quan trọng để giữ khả năng đọc cấu hình khi Git outage.

Hệ quả là hệ thống có thể tiếp tục hoạt động với cấu hình cũ. Một lần refresh của client không đồng nghĩa với việc lấy được commit mới: nếu fetch từ xa thất bại, Config Server vẫn có thể trả bản clone cuối cùng mà nó có. Cần quan sát revision/commit được trả về và hiển thị trạng thái stale, tránh báo “refresh mới nhất thành công” chỉ vì endpoint trả HTTP 200.

Các thuộc tính liên quan:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          clone-on-start: true
          refresh-rate: 15
          force-pull: true
```

- `refresh-rate` tính bằng giây. Mặc định `0` nghĩa là Config Server thử fetch Git mỗi lần có request; giá trị dương giới hạn tần suất fetch; giá trị âm tắt việc refresh repository.
- `force-pull` mặc định `false`. Khi bật, server bỏ các thay đổi cục bộ trong working copy và ép nó theo remote. Chỉ bật khi working copy không được dùng để chỉnh sửa thủ công; tránh làm mất dữ liệu local có chủ đích.
- `clone-on-start` giúp phát hiện lỗi sớm, nhưng không tự bảo đảm clone còn mới sau khi Git mất kết nối.

Nếu Git outage kéo dài, Config Server tiếp tục phục vụ revision cuối cùng có sẵn. Khi Git phục hồi, lần fetch tiếp theo mới cập nhật working copy. Nếu đặt `refresh-rate` quá lớn, thời gian từ lúc Git phục hồi đến lúc cấu hình mới được nhìn thấy cũng có thể kéo dài.

### Config Server restart trong lúc Git vẫn down

Đây là tình huống khác với Git outage sau khi clone. Nếu server khởi động lại và working copy cục bộ không còn (ví dụ container mới, pod mới hoặc thư mục tạm bị xóa), lazy clone không thể lấy repository. Request đầu tiên sẽ lỗi; nếu bật `clone-on-start`, chính Config Server có thể không khởi động được.

Vì vậy, không giả định cache Git tồn tại qua mọi lần restart. Với container/Kubernetes, hãy quyết định rõ working directory có persistent volume hay không. Thường nên coi local clone là cache có thể tái tạo từ remote, đồng thời bảo đảm Git đủ sẵn sàng để dựng lại cache. Nếu cần phục vụ stale config qua một lần restart khi Git down, phải có chiến lược lưu working copy bền vững và kiểm thử khả năng phục hồi của nó.

### Nhiều Config Server instance và working copy không đồng nhất

Mỗi Config Server instance có thể có local clone riêng. Nếu Git bị down sau khi các instance đã clone ở những thời điểm khác nhau, instance A có thể giữ commit mới hơn instance B. Load balancer có thể khiến cùng một client nhận hai phiên bản cấu hình khác nhau tùy request được gửi tới instance nào.

Để giảm rủi ro:

- Cho tất cả instance dùng cùng Git URI, branch/label và credential.
- Đồng bộ chu kỳ fetch và theo dõi commit SHA của từng instance.
- Dùng readiness check để loại instance không có repository hoặc label cần thiết.
- Không chỉnh sửa working copy cục bộ bằng tay.
- Nếu dùng `file:` URI trỏ thẳng vào local repository, mọi instance phải thấy cùng filesystem; với triển khai HA, tài liệu Spring khuyến nghị dùng remote Git qua SSH/HTTPS để mỗi server có local clone riêng thay vì cùng thao tác trên một repository local.

## 3. Khi Vault không truy cập được

Vault thường chứa password, API key, certificate hoặc các giá trị có quyền truy cập hạn chế. Config Server có thể dùng Vault làm Environment Repository, hoặc resolve một số property thông qua cú pháp `{vault}`. Hai trường hợp có cùng dependency nhưng cách lỗi hiển thị khác nhau.

### Vault backend là nguồn cấu hình

Khi Config Server chạy với Vault profile, server kết nối Vault để đọc path và key tương ứng với application/profile. Nếu Vault không sẵn sàng, bị seal, token hết hạn, ACL từ chối hoặc request timeout, Config Server không thể lấy các giá trị đó.

Ví dụ cấu hình Vault backend:

```yaml
spring:
  profiles:
    active: vault
  cloud:
    config:
      server:
        vault:
          host: vault.service.internal
          port: 8200
          scheme: https
          backend: secret
          default-key: application
          kv-version: 2
          authentication: TOKEN
          token: ${VAULT_CONFIG_TOKEN}
          timeout: 5
```

Token phải được cấp từ một cơ chế xác thực được quản lý; không lưu token trong chính Vault path mà nó cần đọc. Spring Cloud Config hỗ trợ token auth mặc định và các cơ chế khác như AppRole, LDAP, JWT, Kubernetes Auth khi có Spring Vault Core phù hợp.

Nếu token bị revoke, hết TTL hoặc policy bị thay đổi, lỗi thường biểu hiện như lỗi xác thực/phân quyền chứ không phải lỗi mạng. Retry không thể sửa một token sai hoặc policy thiếu quyền. Cần phân biệt `401/403` với timeout, `5xx`, trạng thái sealed và lỗi path.

### Vault HA: active, standby và load balancer

Vault HA thường có một node active và các node standby. Standby có thể forward request đến active hoặc redirect client tùy cấu hình và trạng thái cluster. Nếu active hỏng, một standby đủ điều kiện có thể được bầu/promote thành active.

Endpoint `/v1/sys/health` trả các mã mặc định quan trọng:

| HTTP status | Trạng thái Vault | Ý nghĩa vận hành |
|---:|---|---|
| `200` | Initialized, unsealed, active | Node active đang phục vụ |
| `429` | Unsealed standby | Node standby; không nên coi đây là lỗi toàn cluster nếu forwarding hoạt động |
| `473` | Performance standby | Có thể phục vụ một số request đọc trong Vault Enterprise; cần kiểm tra cấu hình và khả năng của client/LB |
| `474` | Standby không kết nối được active | Node không còn hoạt động đúng trong HA cluster; cần cảnh báo |
| `501` | Chưa initialized | Vault chưa được khởi tạo |
| `503` | Sealed | Node sealed không phục vụ secret |

Không cấu hình load balancer chỉ dựa trên quy tắc “mọi mã khác 200 là node chết”. `429` có thể là standby bình thường; `473` có thể là performance standby hợp lệ. Ngược lại, nếu Config Server hoặc health checker không theo redirect/forwarding như dự kiến, nó có thể báo Vault DOWN dù cluster vẫn khỏe. Dùng endpoint/LB policy phù hợp với mô hình active/standby, kiểm tra thực tế request đọc secret qua đường đi mà Config Server sử dụng.

Một lựa chọn phổ biến là đặt load balancer trước Vault và định tuyến request đến active node. Nếu cho phép performance standby phục vụ read-only traffic, chỉ đưa `473` vào trạng thái healthy sau khi xác minh phiên bản Vault, license, policy và client hỗ trợ. Không đánh dấu `474` hoặc `503` là healthy để làm cho dashboard xanh.

### Vault lỗi khi Config Server dùng composite repository

Nếu Environment Repository là composite gồm Git và Vault, mặc định bất kỳ lỗi nào khi lấy dữ liệu từ một repository cũng làm toàn bộ request composite thất bại. Đây là hành vi fail-closed: Config Client không nhận một Environment thiếu nguồn mà hệ thống kỳ vọng.

Có thể đặt:

```yaml
spring:
  cloud:
    config:
      server:
        fail-on-composite-error: false
```

Khi tắt fail-on-composite-error, composite có thể tiếp tục trả các repository còn hoạt động. Điều này hữu ích nếu một nguồn thực sự tùy chọn, nhưng đặc biệt nguy hiểm khi Vault chứa password hoặc token bắt buộc. Ứng dụng có thể khởi động với secret bị thiếu, rơi về default hoặc nhận một phần cấu hình không nhất quán.

Không đặt `false` chỉ để giữ HTTP endpoint hoạt động. Nếu dùng partial response, phải xác định repository nào là optional, property nào phụ thuộc vào nó, validation nào ngăn ứng dụng chạy thiếu secret và cảnh báo nào báo trạng thái degraded. Với secret thiết yếu, ưu tiên fail rõ ràng.

### `{vault}` placeholder và lỗi resolve secret

Config Server cũng có thể resolve một property bằng placeholder `{vault}:path/to/secret#key`. Nếu path không tồn tại, thiếu quyền hoặc Vault không truy cập được, tài liệu Spring Cloud Config mô tả property bị đánh dấu `invalid.` và giá trị là `<n/a>`. Ứng dụng cần validation để phát hiện trường hợp này ngay khi bind cấu hình; không để chuỗi `<n/a>` lọt vào kết nối database hoặc header xác thực.

### KV secret và dynamic lease không giống nhau

Vault KV thường trả một giá trị tĩnh theo version; việc đọc lại sẽ lấy giá trị hiện tại của path. Dynamic secrets như credential database có TTL/lease và có thể bị revoke khi hết hạn. Spring Cloud Config Vault backend chủ yếu là một backend đọc cấu hình/secret; không nên mặc định rằng nó cung cấp đầy đủ vòng đời renewal/rotation cho credential dynamic đã trả về các ứng dụng.

Nếu ứng dụng cần tự gia hạn lease và thay credential khi Vault phát secret mới, dùng cơ chế lease lifecycle của Spring Vault/Spring Cloud Vault hoặc Vault Agent phù hợp với kiến trúc. Kiểm tra riêng thời điểm token hết hạn, lease của secret, thời gian refresh cấu hình và khả năng pool/database thay credential. Một lần Config refresh không tự chứng minh lease cũ đã được gia hạn hoặc connection pool đã đổi credential.

## 4. Khi broker RabbitMQ hoặc Kafka gặp sự cố

Spring Cloud Bus dùng Spring Cloud Stream để phát các event như `RefreshRemoteApplicationEvent` qua broker. Config Server và các Config Client tham gia Bus cần cấu hình binder và kết nối đến broker phù hợp.

### Broker lỗi lúc ứng dụng khởi động

Việc Config Client lấy cấu hình trực tiếp qua HTTP và việc Bus kết nối broker là hai bước khác nhau. Client có thể lấy Config Data từ Config Server thành công nhưng vẫn gặp lỗi khi Bus binder cố tạo binding.

Hành vi startup phụ thuộc binder và cấu hình retry/late binding. Spring Cloud Stream có thuộc tính `spring.cloud.stream.bindingRetryInterval`, mặc định 30 giây; đặt bằng `0` có thể khiến ứng dụng fail khi binder không hỗ trợ late binding và broker chưa sẵn sàng. Không giả định tất cả binder Rabbit/Kafka xử lý startup giống hệt nhau. Hãy kiểm tra log binding và tài liệu binder đang dùng.

Nếu Bus không phải dependency bắt buộc để phục vụ request nghiệp vụ, cân nhắc tách readiness của chức năng Bus khỏi readiness của API chính. Nếu chính sách yêu cầu mọi instance phải nhận refresh phân tán trước khi nhận traffic, giữ startup/readiness ở trạng thái chưa sẵn sàng cho đến khi binding thành công.

### Broker lỗi sau khi ứng dụng đã chạy

Khi broker mất kết nối:

- API Config Server vẫn có thể trả Environment qua HTTP nếu Git/Vault backend còn hoạt động.
- Một client vẫn có thể refresh trực tiếp qua endpoint `/actuator/refresh` nếu client gọi được Config Server.
- `/actuator/busrefresh` cần publish event qua broker; việc fan-out có thể thất bại hoặc bị trì hoãn.
- Webhook Git gọi Config Server `/monitor` có thể được nhận nhưng bước phát event Bus không hoàn tất. Phải kiểm tra response và log, sau đó redeliver hoặc phát lại refresh khi broker phục hồi.
- Các client chưa nhận event tiếp tục dùng giá trị đang có trong Environment/bean; cấu hình mới trong Git/Vault không tự xuất hiện trong bean chỉ vì backend đã được cập nhật.

Không coi broker là nguồn dữ liệu cấu hình. Git/Vault mới là nguồn sự thật; Bus chỉ truyền tín hiệu để các client đọc lại nguồn đó. Sau khi broker phục hồi, cần có thao tác phát lại sự kiện hoặc refresh có kiểm soát và xác nhận từng instance đã hội tụ. Đừng giả định mọi event thất bại trong thời gian broker outage sẽ tự được phát lại.

### Thiết kế broker HA

Broker cũng cần được triển khai theo mô hình HA của chính nó:

- Với RabbitMQ, dùng cluster có quorum queue/replication và cấu hình publisher confirms, consumer acknowledgement, TLS và credential theo hướng dẫn của RabbitMQ binder.
- Với Kafka, cấu hình replication factor, `min.insync.replicas`, producer acknowledgement và số broker đủ để chịu lỗi theo topology; dùng binder Kafka tương thích.
- Đặt broker gần các workload, kiểm soát DNS/load balancer và giới hạn kết nối.
- Theo dõi queue/lag, consumer, connection churn, publish failures và thời gian event tới client.
- Kiểm thử mất một node, mất leader, partition mạng và khôi phục broker trong môi trường staging.

Đây là cấu hình của middleware/binder; chỉ thêm `spring-cloud-starter-bus-amqp` hoặc `spring-cloud-starter-bus-kafka` không tự tạo ra broker cluster HA.

## 5. Bảng ảnh hưởng khi từng dependency hỏng

| Sự cố | Startup Config Client | Refresh trực tiếp | Refresh qua Bus | Dữ liệu có thể tiếp tục dùng |
|---|---|---|---|---|
| Git down sau khi Config Server đã clone | Có thể khởi động với local clone | Có thể trả cấu hình cũ từ clone | Event vẫn có thể phát; client đọc lại bản cũ | Revision Git cuối cùng trong working copy |
| Git down trước clone đầu tiên | Request cấu hình lỗi; fail-fast có thể làm client dừng | Không lấy được cấu hình | Bus không sửa được lỗi Git | Chỉ có default/local config nếu chính sách cho phép |
| Git down và Config Server restart mất clone | Backend không thể dựng lại; request lỗi | Không có local copy để phục vụ | Event không thể lấy cấu hình mới | Không có cache nếu cache đã mất |
| Vault down hoặc sealed | Request cần Vault thất bại | Refresh secret thất bại | Bus có thể phát event nhưng client không lấy được secret mới | Secret/bean đang giữ trong process có thể còn dùng tạm; không đảm bảo sau restart |
| Vault token hết hạn hoặc ACL bị thu hồi | Lỗi xác thực/phân quyền | Lỗi đọc secret | Event không khắc phục credential | Không nên dùng retry vô hạn; cần cấp token/policy đúng |
| Composite Git + Vault, Vault down | Toàn bộ request thất bại theo mặc định | Refresh thất bại | Event có thể tới nhưng fetch thất bại | Client giữ cấu hình cũ nếu process còn sống |
| Broker down trước startup | Config HTTP có thể thành công; Bus binding có thể retry hoặc làm startup lỗi tùy binder | Refresh trực tiếp vẫn có thể hoạt động | Không thể fan-out qua Bus | Environment hiện có và backend HTTP |
| Broker down khi runtime | Không ảnh hưởng lần đọc Config HTTP nếu broker không nằm trong startup gate | Vẫn refresh từng client trực tiếp | Không phân phối event | Client giữ giá trị hiện tại cho đến khi được refresh |
| Config Server instance down | Client cần instance khác hoặc fail startup | Client cần server còn sống | Bus có thể vẫn truyền event nhưng client không lấy được Config Server | Config Data đang giữ trong process |
| Một Config Server replica có Git clone cũ | Client có thể nhận cấu hình khác tùy instance | Refresh có thể tạo kết quả không đồng nhất | Bus phát đến tất cả nhưng mỗi client có thể fetch từ replica khác | Local clone của từng replica |

Bảng này mô tả hành vi thường gặp, không phải cam kết cho mọi cấu hình. Kết quả thực tế phụ thuộc `fail-fast`, `optional`, retry, local clone, composite policy, Vault auth, binder và topology.

## 6. Thiết kế fail-fast, retry và fallback

### Config Client không kết nối được Config Server

Với Config Data import, bỏ tiền tố `optional:` để coi Config Server là dependency bắt buộc. Nếu cho phép thiếu cấu hình, dùng `optional:configserver:` và bảo đảm default an toàn. Có thể bật retry khi server thỉnh thoảng không sẵn sàng:

```yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
```

Với Config Data import, retry parameters cũng có thể được truyền trên URI import theo cú pháp phiên bản đang dùng, đặc biệt khi import nằm trong profile-specific file. Kiểm tra tài liệu Config Client của release train; đừng sao chép cú pháp bootstrap cũ một cách máy móc.

### Nhiều Config Server URL

Config Client có thể dùng nhiều URL để dự phòng instance Config Server:

```yaml
spring:
  cloud:
    config:
      uri: https://config-a.internal,https://config-b.internal
      multiple-uri-strategy: always
```

Với `spring.cloud.config.uri`, các URL được thử theo thứ tự. `multiple-uri-strategy: always` cho phép thử URL tiếp theo khi lần gọi trước không thành công; `connection-timeout-only` giới hạn fallback cho trường hợp server không chạy hoặc connection timeout. Ví dụ lỗi 401/500 thường không được coi là lý do thử server khác khi dùng chiến lược connection-timeout-only.

Với Config Data API, có thể khai báo nhiều `configserver:` import locations. Cách xử lý khác với `spring.cloud.config.uri`: các import được xử lý theo thứ tự và import sau có thể có precedence cao hơn; `spring.cloud.config.multiple-uri-strategy` không áp dụng cho danh sách `spring.config.import`. Theo tài liệu hiện hành, `fail-fast=true` có thể làm client dừng ngay khi location đầu tiên thất bại; khi `false`, client có thể tiếp tục thử các URL. Hãy kiểm thử chính xác hành vi trên phiên bản Spring Cloud Config của dự án.

### Retry không thay thế circuit breaker và validation

Retry phù hợp với lỗi mạng ngắn hạn. Retry không sửa được:

- Git credential sai hoặc branch/label không tồn tại.
- Vault token hết hạn, policy thiếu quyền hoặc secret path bị xóa.
- Broker credential sai hoặc cấu hình TLS không khớp.
- YAML/properties sai cú pháp hoặc giá trị không vượt qua validation.
- Một backend trả dữ liệu không tương thích với schema của ứng dụng.

Đặt timeout hữu hạn, backoff tăng dần và giới hạn số lần thử. Tránh retry đồng loạt không có jitter khi nhiều client khởi động cùng lúc vì có thể tạo retry storm lên Git, Vault hoặc broker.

## 7. Health check phải kiểm tra đúng luồng

Config Server có Health Indicator kiểm tra `EnvironmentRepository`. Mặc định indicator yêu cầu application `app`, profile `default` và default label của repository. Điều này có thể chưa đủ nếu production chỉ dùng application/profile/label cụ thể.

Có thể khai báo repository cần kiểm tra:

```yaml
spring:
  cloud:
    config:
      server:
        health:
          repositories:
            order-prod:
              name: order-service
              profiles: prod
              label: main
            payment-prod:
              name: payment-service
              profiles: prod
              label: release
```

Health check nên kiểm tra những tổ hợp đại diện và thiết yếu, không quét tất cả repository ở mỗi lần probe. Với composite repository, health có thể DOWN nếu một backend lỗi theo chính sách fail-on-composite-error. Nếu cho phép partial response, phải có metric riêng để biết backend nào đang thiếu.

Ở phía Config Client, Config Health Indicator thử tải cấu hình từ Config Server và cache kết quả theo TTL mặc định; không coi một health result cũ là bằng chứng dependency vẫn khỏe tại thời điểm hiện tại. Điều chỉnh TTL theo nhu cầu giám sát và chi phí gọi server.

Không dùng cùng một health endpoint để trả lời mọi câu hỏi. Nên tách:

- **Liveness:** tiến trình có còn hoạt động và có thể tự phục hồi không; không nên restart toàn bộ pod chỉ vì Git/Vault tạm thời down.
- **Readiness:** instance có thể phục vụ nghiệp vụ với cấu hình hiện có và dependency bắt buộc không.
- **Dependency health:** Git fetch có thành công, Vault đọc được secret, broker publish/consume được và Config Server trả đúng revision.

Nếu liveness phụ thuộc trực tiếp vào Git/Vault, một outage bên ngoài có thể khiến mọi pod đồng loạt restart, làm mất local cache và khiến sự cố lan rộng hơn.

## 8. Theo dõi trạng thái stale và sự hội tụ sau phục hồi

Trong thời gian dependency lỗi, điều quan trọng không chỉ là endpoint có trả lời hay không mà còn là phiên bản cấu hình nào đang được sử dụng.

Nên theo dõi:

| Tín hiệu | Ý nghĩa |
|---|---|
| Git commit SHA / label đang phục vụ | Xác định revision thực tế mà Config Server trả về |
| Thời điểm fetch Git thành công gần nhất | Phát hiện local clone đã stale bao lâu |
| Vault `/sys/health` status | Phân biệt active, standby, performance standby, sealed và node rời cluster |
| Vault authentication/permission errors | Phát hiện token hết hạn, bị revoke hoặc policy sai |
| Broker connection và publish failure | Biết event refresh có thể phát đi hay không |
| Bus event trace và acknowledgement | Xác nhận event được gửi và instance nào phản hồi |
| Refresh timestamp theo instance | Phát hiện client nào chưa hội tụ |
| Config Environment version trên client | So sánh cấu hình đang dùng với revision mong muốn |

Spring Cloud Bus có thể bật trace:

```yaml
spring:
  cloud:
    bus:
      trace:
        enabled: true
```

Sau đó kiểm tra `/actuator/bustrace` nếu endpoint đã được expose và bảo vệ. Trace mặc định có thể dùng in-memory repository; nếu cần audit lâu dài, tích hợp TraceRepository bền vững hoặc ghi sự kiện vào hệ thống quan sát tập trung. Không expose trace công khai vì nó có thể tiết lộ topology và danh tính instance.

Sau khi Git/Vault/broker phục hồi:

1. Xác nhận dependency thực sự khỏe bằng một request đọc thử có danh tính/policy giống ứng dụng.
2. Xác nhận Config Server đang đọc đúng commit/secret version.
3. Gửi lại webhook hoặc refresh event nếu notification trước đó có thể đã thất bại.
4. Kiểm tra Bus publish và acknowledgement hoặc gọi refresh trực tiếp cho từng instance.
5. Xác minh Environment và bean cấu hình trên client.
6. Chỉ kết thúc incident khi tất cả instance quan trọng đã hội tụ hoặc đã được restart/rollout theo kế hoạch.

## 9. Quy trình xử lý sự cố theo từng dependency

### Git repository

1. Kiểm tra DNS, network, TLS certificate, SSH host key và credential từ chính Config Server pod/host.
2. Kiểm tra Git URI, branch/label, quyền đọc và trạng thái remote.
3. Xem log fetch/clone, commit SHA và working directory của từng Config Server instance.
4. Nếu local clone còn hợp lệ, xác định có thể tạm phục vụ stale config trong thời gian cho phép hay không.
5. Nếu clone mất hoặc hỏng, phục hồi Git trước khi restart các instance phụ thuộc.
6. Sau khi Git lên lại, fetch/reload và xác minh revision giống nhau trên tất cả replica.

### Vault

1. Gọi `/v1/sys/health` và phân biệt mã standby với sealed/HA unhealthy.
2. Kiểm tra active node, forwarding/redirect, load balancer và cluster address.
3. Kiểm tra token, auth method, TTL, namespace, KV engine version, path và policy.
4. Đọc thử một secret kiểm soát bằng đúng credential mà Config Server sử dụng.
5. Nếu dùng composite, xác định fail-on-composite-error và quyết định có cho phép partial response hay không.
6. Sau phục hồi, đọc lại secret version và kiểm tra ứng dụng không còn dùng credential hết hạn.

### RabbitMQ/Kafka broker

1. Kiểm tra DNS, TLS, credential, network route và broker cluster quorum/leader.
2. Kiểm tra Spring Cloud Stream binder đã tạo binding chưa; đọc `bindingRetryInterval` và log reconnect.
3. Kiểm tra publish failure, queue/consumer lag, partition ISR hoặc Rabbit quorum state.
4. Xác nhận Config Server và từng client đang cùng destination/topic và Bus ID hợp lệ.
5. Khi broker phục hồi, phát lại refresh event hoặc dùng endpoint refresh trực tiếp.
6. Kiểm tra trace/ack và revision trên từng instance; không chỉ dựa vào HTTP response của endpoint gửi event.

## 10. Kịch bản kiểm thử chịu lỗi

Không nên đợi production mới biết cache Git hoặc Bus hoạt động ra sao. Tạo các bài kiểm thử fault injection trong staging:

| Kịch bản | Cách tạo lỗi | Kết quả cần quan sát |
|---|---|---|
| Git down sau clone | Chặn outbound tới Git host | Config Server tiếp tục phục vụ local clone; revision không tăng |
| Git down trước clone | Xóa clone thử nghiệm và chặn Git | `clone-on-start` fail khi startup hoặc lazy clone fail ở request đầu |
| Restart Config Server khi Git down | Xóa pod/cache rồi restart | Xác minh server không có clone sẽ không phục vụ được repository |
| Replica Git cache lệch | Tạm chặn fetch ở một replica | Health/metrics phát hiện revision lệch; không để LB che giấu sai khác |
| Vault standby | Đưa request qua standby | Xác minh forwarding/redirect hoặc LB định tuyến đúng |
| Vault sealed | Seal node trong môi trường thử nghiệm | Secret request thất bại rõ; không trả secret giả/default không an toàn |
| Vault token revoke | Revoke token test | Config Server báo auth error; cảnh báo và quy trình cấp token mới hoạt động |
| Broker down lúc startup | Tắt broker trước khi start client | Xác minh binding retry/fatal behavior theo binder và readiness policy |
| Broker down lúc runtime | Chặn kết nối broker | HTTP Config fetch/direct refresh còn hoạt động; Bus fan-out thất bại hoặc chậm |
| Broker leader/node failover | Dừng một broker node | Cluster phục hồi trong RTO; Bus event sau phục hồi tới đủ client |
| Composite Vault failure | Chặn Vault khi Git còn hoạt động | Theo default, toàn bộ composite request thất bại; nếu partial được bật, kiểm tra validation chặn thiếu secret |

Mỗi kịch bản cần ghi RTO (thời gian phục hồi), RPO (mức mất/cũ dữ liệu chấp nhận được), revision đang dùng, hành động thủ công cần thiết và tiêu chí kết thúc incident.

## 11. Các lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Điều chỉnh |
|---|---|---|
| Chỉ kiểm tra Config Server process còn sống | Server có thể không đọc được Git/Vault | Health probe theo application/profile/label thiết yếu và dependency metrics |
| Bật `clone-on-start` nhưng không có chiến lược Git HA | Git outage ngăn Config Server khởi động | Cân nhắc local clone bền vững, remote Git HA và readiness phù hợp |
| Dùng local clone như nguồn sự thật | Replica trả revision khác nhau hoặc mất cache khi pod thay thế | Git remote là nguồn sự thật; theo dõi commit và tái tạo clone có kiểm soát |
| Cho composite tiếp tục khi Vault down mà không validation | Client nhận Environment thiếu secret | Giữ fail-closed cho secret bắt buộc hoặc validation chặn startup |
| Coi Vault standby `429` là cluster DOWN | LB loại hết node dù forwarding có thể hoạt động | Dùng Vault health semantics và kiểm thử active/standby routing |
| Cho mọi client dùng một Vault token dài hạn | Blast radius lớn, khó rotate và audit | Token riêng theo service, policy tối thiểu, auth method và rotation |
| Chỉ thêm Bus starter rồi coi hệ thống HA | Một broker duy nhất vẫn là single point of failure | Thiết kế cluster/replication theo RabbitMQ hoặc Kafka |
| Coi `/busrefresh` thành công là mọi client đã cập nhật | Event có thể chưa tới hoặc client fetch thất bại | Kiểm tra trace/ack và revision trên từng instance |
| Dùng retry vô hạn | Retry storm và kéo dài outage | Timeout, backoff, giới hạn lần thử, jitter và cảnh báo |
| Liveness phụ thuộc Git/Vault/Broker | Outage làm pod restart hàng loạt, mất cache | Tách liveness, readiness và dependency health |

## 12. Checklist độ sẵn sàng production

| Hạng mục | Điều kiện đạt |
|---|---|
| Git backend | Remote HA, credential read-only, clone-on-start được chọn có chủ đích, cache và refreshRate được hiểu rõ |
| Git consistency | Mỗi Config Server replica có revision được quan sát; không chỉnh sửa working copy thủ công |
| Vault HA | Active/standby, storage/quorum, unseal, forwarding và load balancer đã được kiểm thử |
| Vault auth | Token/role có TTL và policy rõ; có rotation/revocation runbook |
| Secret failure | Composite policy và validation không cho ứng dụng chạy thiếu secret bắt buộc |
| Broker HA | RabbitMQ/Kafka cluster có replication/quorum và binder reconnect được kiểm thử |
| Bus fan-out | Có trace/ack hoặc cơ chế quan sát tương đương; có cách phát lại sau outage |
| Config Server HA | Nhiều replica có cấu hình, backend access và encryption key đồng nhất |
| Client failover | Có nhiều Config Server URI/discovery hoặc LB; đã kiểm tra semantics fallback của version |
| Startup policy | Fail-fast/optional/retry phù hợp từng loại cấu hình bắt buộc và tùy chọn |
| Health | Tách liveness, readiness, backend health và freshness/revision |
| Observability | Có Git fetch age, Vault status/auth errors, broker publish/lag, refresh age theo instance |
| Recovery | Có runbook cho Git, Vault, broker và kiểm tra hội tụ sau phục hồi |
| Fault testing | Đã thử Git outage, Vault standby/seal, broker outage và replica failover trong staging |

## 13. Nguyên tắc cần ghi nhớ

- Git outage sau khi clone không nhất thiết làm Config Server ngừng phục vụ; server có thể trả bản clone cũ. Git outage trước clone hoặc sau khi mất local cache làm request cấu hình thất bại.
- `clone-on-start` phát hiện lỗi Git sớm; `refresh-rate` điều khiển tần suất fetch; working copy của nhiều replica có thể lệch revision.
- Vault outage ảnh hưởng trực tiếp đến luồng đọc secret. Token hết hạn, ACL sai, node sealed và path thiếu là các loại lỗi khác nhau, không giải quyết bằng retry giống nhau.
- Vault standby `429` không nhất thiết là cluster hỏng; `473` có thể là performance standby; `474` và `503` cần được xử lý như tín hiệu nghiêm trọng.
- Composite repository mặc định fail khi một backend lỗi; tắt fail-on-composite-error có thể tạo Environment thiếu secret và phải có validation/giám sát.
- Spring Cloud Bus cần broker để fan-out refresh event; broker down không tự làm hỏng Config Server HTTP API hoặc refresh trực tiếp từng client.
- Bus event là tín hiệu, Git/Vault mới là nguồn dữ liệu; sau outage phải phát lại/refresh và xác minh từng instance đã hội tụ.
- Broker HA cần được thiết kế ở tầng RabbitMQ/Kafka; starter Bus không tự tạo replication hoặc quorum.
- Health check phải kiểm tra đúng application/profile/label và dependency thiết yếu; liveness không nên phụ thuộc mọi backend bên ngoài.
- Theo dõi revision, secret version, Bus acknowledgement và thời gian refresh để phân biệt “đang phục vụ” với “đang phục vụ dữ liệu mới nhất”.

Sự cố Git, Vault và broker tác động vào những đoạn khác nhau của hệ thống cấu hình. Git thường quyết định tính mới của cấu hình và có thể được giảm tác động nhờ local clone; Vault quyết định khả năng lấy secret và cần fail-closed khi dữ liệu nhạy cảm không có; broker quyết định khả năng phân phối refresh event nhưng không thay thế API lấy cấu hình trực tiếp. Khi phân tách rõ các luồng, thiết kế HA theo từng dependency và kiểm tra sự hội tụ sau phục hồi, nhóm có thể giữ dịch vụ hoạt động an toàn mà vẫn biết chính xác ứng dụng đang dùng revision và secret nào.

## Tài liệu tham khảo

- [Spring Cloud Config — Git Backend và local working copy](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Vault Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/vault-backend.html)
- [Spring Cloud Config — Composite Environment Repositories](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/composite-repositories.html)
- [Spring Cloud Config — Health Indicator](https://docs.spring.io/spring-cloud-config/reference/server/health-indicator.html)
- [Spring Cloud Config Client — Fail Fast, Retry và multiple URLs](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Bus — Quickstart](https://docs.spring.io/spring-cloud-bus/reference/quickstart.html)
- [Spring Cloud Bus — Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html)
- [Spring Cloud Stream — Binding retry interval](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-service-properties.html)
- [HashiCorp Vault — High Availability](https://developer.hashicorp.com/vault/docs/concepts/ha)
- [HashiCorp Vault — `/sys/health` API](https://developer.hashicorp.com/vault/api-docs/system/health)
- [Spring Vault — Credential Rotation và Lease Lifecycle](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
