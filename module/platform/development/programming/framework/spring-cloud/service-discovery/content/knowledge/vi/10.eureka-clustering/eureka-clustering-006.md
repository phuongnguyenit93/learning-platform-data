# Thiết kế vùng, khu vực và metadata về vị trí triển khai

## 1. Vì sao cần mô hình region và zone?

Trong một hệ thống microservice chạy trên nhiều máy chủ hoặc nhiều vùng hạ tầng, khoảng cách mạng và phạm vi sự cố ảnh hưởng trực tiếp đến khả năng gọi dịch vụ. Hai instance của cùng một service có thể nằm ở hai availability zone khác nhau, hai trung tâm dữ liệu hoặc hai khu vực địa lý. Nếu client luôn chọn instance ở xa, request có thể tăng latency và tạo lưu lượng liên vùng không cần thiết.

Eureka hỗ trợ khái niệm **region** và **zone** để mô tả cách tổ chức hạ tầng discovery. Ứng dụng cũng có thể công bố metadata về vị trí triển khai để các thành phần quan sát hoặc chọn instance phù hợp.

Các khái niệm này nên được phân biệt:

- **Region:** khu vực lớn, thường đại diện cho một vùng địa lý hoặc một miền triển khai có ranh giới vận hành riêng.
- **Zone:** một vùng nhỏ hơn bên trong region, thường tương ứng với availability zone hoặc failure domain.
- **Instance metadata:** các cặp key/value mà từng instance công bố, chẳng hạn region, zone, datacenter, rack và version.

Region và zone giúp tổ chức endpoint Eureka và ưu tiên kết nối theo vị trí. Metadata cung cấp thông tin về chính instance. Chỉ gắn metadata không tự làm Eureka hoặc LoadBalancer định tuyến theo vị trí; cần cấu hình thành phần tiêu thụ metadata.

## 2. Phân cấp vị trí triển khai

Một mô hình phổ biến có thể biểu diễn như sau:

~~~mermaid
flowchart TB
    R[Region: ap-southeast-1]
    R --> ZA[Zone: zone-a]
    R --> ZB[Zone: zone-b]
    ZA --> A1[Datacenter / Rack A]
    ZB --> B1[Datacenter / Rack B]
    A1 --> APP1[Payment instance A]
    B1 --> APP2[Payment instance B]
~~~

Region chứa nhiều zone. Mỗi zone có thể có một hoặc nhiều Eureka Server và nhiều instance nghiệp vụ. Khi một zone gặp sự cố, các zone còn lại trong cùng region có thể tiếp tục phục vụ nếu mạng, registry và ứng dụng đã được triển khai dự phòng.

Tên region và zone là nhãn logic do tổ chức quy ước hoặc lấy từ nền tảng hạ tầng. Không nên trộn lẫn các cấp độ. Ví dụ, **ap-southeast-1** có thể là region, **zone-a** là zone, **dc-hcm-1** là datacenter và **rack-03** là rack.

## 3. Region và zone trong Eureka Client

Eureka Client sử dụng region và availability zones để xác định các Eureka Server mà nó nên kết nối. Một số thuộc tính thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| **eureka.client.region** | Region mà Eureka Client đang hoạt động |
| **eureka.client.availability-zones** | Ánh xạ region tới danh sách zone theo thứ tự ưu tiên |
| **eureka.client.service-url** | Ánh xạ zone tới một hoặc nhiều URL của Eureka Server |
| **eureka.client.prefer-same-zone-eureka** | Ưu tiên Eureka Server thuộc zone của client nếu có thể |

Region mặc định trong Eureka thường là **us-east-1**. Trong môi trường thực tế, hãy khai báo region và zone theo topology của tổ chức để tránh phụ thuộc vào giá trị mặc định.

### 3.1. Ví dụ cấu hình client ở zone-a

Giả sử hệ thống có một region **ap-southeast-1**, gồm hai zone **zone-a** và **zone-b**. Client đang chạy ở zone-a:

~~~yaml
eureka:
  client:
    region: ap-southeast-1
    availability-zones:
      ap-southeast-1: zone-a,zone-b
    service-url:
      zone-a: http://eureka-a.internal:8761/eureka/
      zone-b: http://eureka-b.internal:8761/eureka/
    prefer-same-zone-eureka: true
~~~

Trong cấu hình này:

- Client thuộc region **ap-southeast-1**.
- **availability-zones** liệt kê zone-a trước zone-b, thể hiện thứ tự ưu tiên của các zone trong region.
- **service-url** khai báo endpoint Eureka tương ứng với từng zone.
- **prefer-same-zone-eureka: true** yêu cầu client ưu tiên Eureka Server trong zone gần với vị trí của client khi chọn server để giao tiếp.

Tên zone trong **availability-zones** phải khớp với key zone trong **service-url**. Các hostname Eureka phải phân giải được và có thể truy cập từ workload trong mạng triển khai.

### 3.2. Client ở zone-b

Client ở zone-b có thể dùng cùng region và danh sách endpoint, nhưng cần được triển khai với thông tin vị trí phù hợp. Thứ tự ưu tiên zone có thể được cấu hình theo topology của client hoặc theo quy ước chung của môi trường. Không nên sao chép nguyên cấu hình zone-a cho mọi workload nếu điều đó làm client luôn ưu tiên một zone xa.

Khi có nhiều endpoint trong cùng zone, có thể khai báo danh sách URL theo cú pháp được phiên bản Spring Cloud Netflix hỗ trợ. Hãy xác nhận cấu hình hiệu lực bằng log Eureka Client và thử nghiệm khi một endpoint không truy cập được.

## 4. Eureka Server cũng cần được bố trí theo zone

Để tránh một zone trở thành điểm lỗi đơn, hãy triển khai nhiều Eureka Server ở các failure domain khác nhau. Các node cần biết peer của mình và phải có thể giao tiếp qua mạng nội bộ.

Ví dụ một node Eureka ở zone-a:

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-a1.internal
    metadata-map:
      region: ap-southeast-1
      zone: zone-a
  client:
    register-with-eureka: true
    fetch-registry: true
    region: ap-southeast-1
    availability-zones:
      ap-southeast-1: zone-a,zone-b
    service-url:
      zone-a: http://eureka-a2.internal:8761/eureka/
      zone-b: http://eureka-b.internal:8761/eureka/
    prefer-same-zone-eureka: true
~~~

Node ở zone-b cần hostname và metadata zone tương ứng, đồng thời cấu hình endpoint peer phù hợp. Các URL trong danh sách service URL của một Eureka Server phải trỏ đến peer; không thêm URL của chính node đó vào danh sách peer. Ví dụ trên giả định zone-a có một peer khác là eureka-a2 và zone-b có eureka-b. Trong môi trường triển khai thật, nên có Eureka Server ở nhiều failure domain; số lượng node và cách phân bố phải dựa trên tải, yêu cầu sẵn sàng và topology mạng.

Việc cấu hình **prefer-same-zone-eureka** liên quan đến lựa chọn **Eureka Server** mà client giao tiếp. Nó không đồng nghĩa với việc request nghiệp vụ sẽ tự động được gửi đến instance cùng zone. Đó là hai quyết định ở hai tầng khác nhau.

## 5. Metadata về vị trí của service instance

Eureka instance có thể công bố metadata tùy chỉnh qua **eureka.instance.metadata-map**. Ví dụ:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      region: ap-southeast-1
      zone: zone-a
      datacenter: dc-hcm-1
      rack: rack-03
      version: 2.5.0
~~~

Khi instance đăng ký, các cặp key/value này được lưu trong registry và có thể được trả về cho client thông qua Eureka API. Metadata giúp:

- Nhận biết instance đang chạy ở region hoặc zone nào.
- Phân biệt datacenter, rack hoặc nhóm triển khai.
- Quan sát phân bố phiên bản trong quá trình rolling update.
- Hỗ trợ dashboard, log, metric và công cụ vận hành.
- Làm đầu vào cho chính sách lọc instance theo vị trí nếu client được cấu hình để sử dụng metadata.

Metadata là dữ liệu do ứng dụng công bố. Eureka không xác minh rằng giá trị **zone** trong metadata thật sự khớp với vị trí vật lý của máy chủ. Nền tảng triển khai cần cung cấp giá trị chính xác qua environment variable, ConfigMap hoặc cấu hình tương ứng.

### 5.1. Đặt tên metadata nhất quán

Nên thống nhất tên key và quy ước giá trị trên toàn hệ thống:

| Key | Ví dụ | Ý nghĩa |
|---|---|---|
| **region** | ap-southeast-1 | Region triển khai |
| **zone** | zone-a | Availability zone hoặc failure domain |
| **datacenter** | dc-hcm-1 | Trung tâm dữ liệu |
| **rack** | rack-03 | Rack hoặc nhóm máy chủ |
| **cluster** | payments-prod | Cụm triển khai |
| **version** | 2.5.0 | Phiên bản ứng dụng |
| **build** | 2026.11.24.1 | Mã build hoặc release |

Không nên dùng nhiều tên key cho cùng một ý nghĩa, ví dụ **az**, **availabilityZone** và **zone** cùng xuất hiện mà không có quy ước. Nếu một thành phần routing mong đợi key **zone**, hãy bảo đảm mọi instance đều công bố đúng key và đúng định dạng giá trị.

Không đưa token, password, khóa bí mật hoặc dữ liệu nhạy cảm vào metadata. Registry có thể được nhiều service client truy vấn; chỉ công bố thông tin cần thiết cho discovery và vận hành.

## 6. Ưu tiên instance cùng zone khi gọi dịch vụ

Việc client kết nối đến Eureka Server gần nhất giúp giảm độ trễ khi đọc registry. Tuy nhiên, để request nghiệp vụ ưu tiên instance cùng zone, cần cấu hình chính sách chọn instance ở tầng load balancing.

Spring Cloud LoadBalancer có thể sử dụng **ZonePreferenceServiceInstanceListSupplier** để ưu tiên các instance có metadata zone trùng với zone của client. Ví dụ cấu hình zone của workload:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Instance của service đích cần công bố metadata tương ứng:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

Để cơ chế ưu tiên zone có hiệu lực, ứng dụng cần sử dụng supplier có hỗ trợ zone preference và bảo đảm phiên bản Spring Cloud LoadBalancer đang dùng có cấu hình tương ứng. Chỉ đặt **spring.cloud.loadbalancer.zone** hoặc chỉ thêm metadata không tự thay đổi thuật toán chọn instance nếu supplier vẫn là cấu hình mặc định không lọc theo zone.

Khi có instance cùng zone, supplier có thể ưu tiên nhóm đó. Nếu không có instance phù hợp, hành vi fallback phụ thuộc implementation và cấu hình supplier. Hãy kiểm thử trường hợp zone cục bộ trống để bảo đảm ứng dụng vẫn có đường gọi sang zone khác khi chính sách yêu cầu.

### 6.1. Phân biệt hai kiểu ưu tiên

| Cấu hình | Tầng tác động | Mục tiêu |
|---|---|---|
| **eureka.client.prefer-same-zone-eureka** | Eureka Client kết nối Eureka Server | Ưu tiên endpoint registry cùng zone |
| **spring.cloud.loadbalancer.zone** kết hợp zone-aware supplier | Load balancing request nghiệp vụ | Ưu tiên service instance cùng zone |

Hai cấu hình có thể cùng được sử dụng, nhưng không thay thế nhau. Một client có thể lấy registry từ Eureka Server ở zone-a rồi vẫn chọn instance nghiệp vụ ở zone-b nếu LoadBalancer không có chính sách zone preference.

## 7. Thiết kế fallback giữa zone và region

Một thiết kế chịu lỗi thường có thứ tự ưu tiên:

1. Ưu tiên instance trong cùng zone để giảm latency và lưu lượng liên vùng.
2. Nếu zone cục bộ không còn instance phù hợp, cho phép fallback sang zone khác trong cùng region.
3. Chỉ fallback sang region khác khi yêu cầu nghiệp vụ, năng lực hệ thống và chính sách dữ liệu cho phép.

~~~mermaid
flowchart TD
    REQ[Request đến payment-service] --> LOCAL{Có instance khỏe cùng zone?}
    LOCAL -->|Có| SAME[Chọn instance cùng zone]
    LOCAL -->|Không| REGIONAL{Có instance ở zone khác cùng region?}
    REGIONAL -->|Có| OTHERZONE[Chọn instance zone khác]
    REGIONAL -->|Không| REMOTE{Cho phép fallback region khác?}
    REMOTE -->|Có| OTHERREGION[Chọn instance region khác]
    REMOTE -->|Không| FAIL[Trả lỗi có kiểm soát]
~~~

Đây là chính sách định tuyến minh họa, không phải hành vi tự động mà Eureka cung cấp. Ứng dụng cần cấu hình LoadBalancer, gateway hoặc tầng routing tương ứng để thực hiện thứ tự ưu tiên và fallback.

Khi thiết kế fallback, cần đánh giá:

- Latency và chi phí truyền dữ liệu giữa zone/region.
- Khả năng truy cập database, message broker và dependency ở region đích.
- Residency hoặc yêu cầu lưu trữ dữ liệu theo khu vực.
- Dung lượng dự phòng của zone/region nhận traffic.
- Timeout, retry, circuit breaker và nguy cơ retry storm.
- Cách ngăn hai region cùng nhận ghi khi nghiệp vụ không hỗ trợ active-active.

Không nên fallback liên vùng chỉ vì endpoint còn phản hồi. Một instance ở region khác có thể không có quyền truy cập dữ liệu hoặc dependency cần thiết để xử lý nghiệp vụ.

## 8. Multi-region trong Eureka

Trong hệ thống nhiều region, mỗi region có thể vận hành một cụm Eureka riêng và các ứng dụng ưu tiên registry gần mình. Eureka Client có khái niệm region và có thể được cấu hình để lấy registry từ remote region trong những kiến trúc cần thiết.

Khi triển khai multi-region, cần quyết định rõ:

- Region nào là nơi đăng ký chính của từng service instance.
- Client chỉ cần registry của region cục bộ hay cần thêm registry từ region khác.
- Những service nào được phép gọi xuyên region.
- Cách xử lý khi mất kết nối giữa các region.
- Cách đồng bộ hoặc phân phối thông tin registry qua các cụm.

Không nên mặc định rằng cấu hình nhiều URL Eureka đồng nghĩa với một registry toàn cầu nhất quán. Khả năng fetch registry từ remote region và cách đồng bộ giữa các region phụ thuộc cấu hình, phiên bản Eureka và kiến trúc vận hành. Hãy kiểm tra tài liệu phiên bản đang dùng và thử nghiệm lỗi liên vùng trước khi đưa vào production.

## 9. Ví dụ đưa vị trí từ môi trường triển khai vào metadata

Trong Kubernetes, thông tin zone có thể được nền tảng cung cấp qua label của node hoặc biến môi trường do manifest đưa vào container. Ứng dụng có thể nhận các giá trị đó qua biến môi trường rồi ánh xạ vào cấu hình Spring.

Ví dụ cấu hình:

~~~yaml
eureka:
  instance:
    metadata-map:
      region: ${DEPLOY_REGION:local}
      zone: ${DEPLOY_ZONE:local}
      datacenter: ${DATACENTER_ID:dev}
~~~

Ví dụ manifest rút gọn:

~~~yaml
env:
  - name: DEPLOY_REGION
    value: ap-southeast-1
  - name: DEPLOY_ZONE
    value: zone-a
  - name: DATACENTER_ID
    value: dc-hcm-1
~~~

Các giá trị trong ví dụ là minh họa. Trong môi trường thật, nên lấy zone từ metadata của node hoặc cơ chế scheduling của nền tảng để tránh khai báo thủ công sai vị trí. Nếu pod có thể được reschedule sang node thuộc zone khác, metadata phải được cập nhật theo vị trí thực của pod sau khi khởi động.

## 10. Quan sát và kiểm tra phân bố zone

Khi đã công bố metadata, có thể kiểm tra registry qua Eureka Dashboard hoặc REST API. Ví dụ:

~~~bash
curl -H "Accept: application/json" http://eureka-a.internal:8761/eureka/apps/PAYMENT-SERVICE
~~~

Trong mỗi instance, kiểm tra:

- Hostname và IP có thể truy cập từ workload cần gọi hay không.
- Metadata **region** và **zone** có đúng với nơi instance đang chạy không.
- Số lượng instance ở từng zone có phù hợp với capacity dự kiến không.
- Status có phải UP và lease có được gia hạn đều không.
- Phiên bản ứng dụng có phân bố đúng trong rollout không.

Nên theo dõi các metric theo region và zone:

| Metric hoặc tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Số instance theo region/zone | Có zone nào thiếu instance hoặc mất toàn bộ instance không? |
| Request count theo zone đích | Traffic có đang tập trung quá mức vào một zone không? |
| Request latency theo zone nguồn/đích | Có lưu lượng liên zone gây latency cao không? |
| Error rate và timeout theo zone | Một zone có đang suy giảm chất lượng không? |
| Eureka peer/client fetch errors | Các node có còn trao đổi và cập nhật registry không? |
| Version/build theo zone | Rollout có hoàn tất đồng đều không? |

Khi so sánh số lượng instance, hãy tính đến thời gian replication và client fetch. Một lần truy vấn ngay sau rollout có thể cho thấy phân bố chưa hội tụ; cần quan sát qua một khoảng thời gian và đối chiếu nhiều Eureka Server.

## 11. Những lỗi thiết kế thường gặp

### 11.1. Nhầm zone của Eureka Server với zone của service instance

**prefer-same-zone-eureka** ưu tiên server registry. Nó không tự giới hạn service instance mà LoadBalancer chọn. Muốn ưu tiên instance cùng zone, cần metadata và supplier có hỗ trợ zone preference.

### 11.2. Metadata không khớp vị trí thật

Nếu pod chạy ở zone-b nhưng công bố **zone-a**, bộ cân bằng tải có thể đưa request đến sai failure domain. Hãy lấy giá trị từ môi trường triển khai và kiểm tra qua REST API.

### 11.3. Chỉ có một Eureka Server trong một region

Một server duy nhất có thể trở thành điểm lỗi đơn. Hãy phân bố server qua các failure domain phù hợp và cấu hình peer có thể truy cập.

### 11.4. Không có fallback khi zone cục bộ mất toàn bộ instance

Ưu tiên local zone giúp giảm latency trong điều kiện bình thường, nhưng có thể làm service không gọi được nếu chính sách chỉ cho phép instance cùng zone. Hãy xác định rõ fallback sang zone khác và kiểm thử khi local zone trống.

### 11.5. Fallback region không xét dependency và dữ liệu

Instance ở region khác có thể không truy cập được database, queue hoặc dữ liệu đúng miền. Chỉ bật cross-region routing sau khi xác minh khả năng phục vụ của toàn bộ dependency.

### 11.6. Đưa quá nhiều thông tin nội bộ vào metadata

Metadata có thể được client đọc. Chỉ công bố nhãn vị trí và phiên bản cần thiết; không đưa secret, địa chỉ quản trị nhạy cảm hoặc thông tin không phục vụ discovery.

## 12. Quy trình thiết kế và triển khai

Có thể áp dụng quy trình sau:

1. Xác định region và zone theo failure domain thực tế của hạ tầng.
2. Phân bố Eureka Server qua các zone và cấu hình peer.
3. Cấu hình region, availability zones và service URL cho từng nhóm Eureka Client.
4. Bật ưu tiên Eureka Server cùng zone nếu phù hợp với topology.
5. Chuẩn hóa metadata region, zone, datacenter, rack và version cho từng service instance.
6. Nếu cần routing cùng zone, cấu hình zone-aware supplier ở Spring Cloud LoadBalancer.
7. Thiết kế fallback cùng region và cross-region theo yêu cầu nghiệp vụ.
8. Kiểm tra registry bằng REST API và đo request distribution theo zone.
9. Thử nghiệm mất một Eureka Server, mất một zone, mất liên kết giữa các region và phục hồi.

## 13. Tổng kết

Region và zone mô tả cấu trúc hạ tầng discovery. Eureka Client dùng **eureka.client.region**, **availability-zones**, **service-url** và **prefer-same-zone-eureka** để lựa chọn Eureka Server phù hợp. Instance có thể công bố vị trí triển khai qua **eureka.instance.metadata-map**, chẳng hạn region, zone, datacenter và rack.

Ưu tiên Eureka Server cùng zone và ưu tiên service instance cùng zone là hai quyết định riêng. Muốn request nghiệp vụ được cân bằng theo vị trí, cần cấu hình supplier hoặc chính sách routing có thể đọc metadata zone. Một thiết kế tốt giảm lưu lượng liên vùng trong điều kiện bình thường, vẫn có fallback khi zone gặp sự cố và chỉ chuyển sang region khác khi dependency, dữ liệu và năng lực phục vụ cho phép.
