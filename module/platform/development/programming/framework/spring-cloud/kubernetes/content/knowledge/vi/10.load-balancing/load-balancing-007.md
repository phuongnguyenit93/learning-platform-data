# Cache danh sách bản sao và độ trễ loại bỏ Pod

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, cache danh sách bản sao giúp ứng dụng tái sử dụng thông tin instance khi chọn đích gọi. Đổi lại, caller có thể còn nhìn thấy một Pod đã không còn phù hợp để nhận yêu cầu mới.

Một tình huống thường gặp: Kubernetes đã đánh dấu Pod không ready hoặc đang kết thúc, nhưng orders-api vẫn có lần chọn địa chỉ cũ của inventory-api. Hiện tượng đó cần được lần theo từ trạng thái endpoint, dữ liệu DiscoveryClient, các lớp cache và thời điểm lựa chọn instance. Chỉ nhìn trạng thái Pod hoặc chỉ giảm một thuộc tính TTL chưa đủ để xác định nguyên nhân.

Bài học kết nối DiscoveryClient, Spring Cloud LoadBalancer, RBAC và theo dõi sức khỏe Pod trong phạm vi module. ConfigMap, Secret và Configuration Watcher có thể tham gia cung cấp hoặc cập nhật cấu hình, nhưng không mặc định làm mọi cache discovery được xóa khi Pod thay đổi.

Sau bài học, bạn có thể:

- Nhận diện những lớp đang giữ danh sách instance.
- Phân biệt TTL của cache với độ trễ loại bỏ Pod khỏi lựa chọn.
- Giải thích vì sao nhiều lớp cache có thể làm dữ liệu cũ tồn tại lâu hơn dự kiến.
- Chọn cấu hình cache theo nguồn discovery thực tế.
- Đo các mốc cập nhật mà không nhầm thời điểm hoàn tất request với thời điểm chọn đích.
- Phối hợp cập nhật discovery và quá trình dừng ứng dụng có kiểm soát.

## 1. Cache đang giữ dữ liệu gì?

Trong bài này, “danh sách bản sao” là danh sách instance có thể được dùng làm đích cho một service ID, thường biểu diễn bằng các ServiceInstance. Nó không phải số replicas mong muốn trong Deployment.

Ví dụ một snapshot cho inventory-api:

~~~text
serviceId = inventory-api

[
  instance A -> 10.42.1.21:8080,
  instance B -> 10.42.2.22:8080,
  instance C -> 10.42.3.23:8080
]
~~~

Cache có thể giữ snapshot này để LoadBalancer không phải dựng lại danh sách từ nguồn discovery cho mỗi lần lựa chọn.

Cần phân biệt các loại dữ liệu:

| Loại dữ liệu | Ví dụ | Có được điều khiển bởi TTL danh sách instance không? |
| --- | --- | --- |
| Danh sách ứng viên | Ba địa chỉ của inventory-api | Có, nếu thuộc đúng lớp cache đang cấu hình |
| Kết quả nghiệp vụ | Số lượng tồn kho của một sản phẩm | Không |
| Phân giải DNS | Tên Service thành địa chỉ mạng | Không |
| HTTP connection pool | Kết nối đã mở tới một địa chỉ | Không |
| Số replica mong muốn | replicas: 3 trong Deployment | Không |
| Trạng thái tài nguyên trong discovery | Bản sao Service, Pod hoặc endpoint tại client | Có cơ chế cập nhật riêng, không mặc định cùng TTL |

Một cache chứa ba instance không có nghĩa Deployment luôn có ba Pod sẵn sàng. Ngược lại, Deployment đã có ba Pod cũng không chứng minh mọi caller đã nhìn thấy đủ ba địa chỉ.

Cache phía ứng dụng thường nằm trong từng tiến trình caller. Hai Pod orders-api có thể giữ hai snapshot khác nhau tại cùng thời điểm. Việc làm mới danh sách ở một caller không tự chứng minh những caller còn lại đã hội tụ.

## 2. Vẽ đường dữ liệu trước khi chỉnh TTL

Luồng gọi trực tiếp dựa trên Kubernetes DiscoveryClient có thể được mô tả như sau:

~~~mermaid
flowchart LR
    K["Kubernetes API: Service, Pod, endpoint"] --> D["Dữ liệu nội bộ DiscoveryClient"]
    D --> S["Supplier lấy danh sách instance"]
    S --> C["Cache LoadBalancer nếu được dùng"]
    C --> L["Chọn một instance"]
    L --> H["HTTP client gửi request"]
~~~

Các ô là những trách nhiệm cần kiểm tra; không phải implementation nào cũng có đúng từng lớp độc lập như hình.

Ở kiến trúc HTTP discovery, còn có các thành phần trung gian:

~~~text
Kubernetes API
  -> Discovery Server và trạng thái nội bộ của server
  -> HTTP DiscoveryClient ở ứng dụng gọi
  -> cache bổ sung nếu được bật
  -> supplier và cache LoadBalancer
  -> lựa chọn instance
~~~

Nếu đầu ra HTTP của server đã cũ, tắt cache LoadBalancer tại caller chỉ khiến caller đọc lại nguồn cũ thường xuyên hơn.

Cũng cần xác định đích cân bằng tải:

| Đường gọi | Nơi cần quan sát khi một Pod rời hệ thống |
| --- | --- |
| Chọn trực tiếp instance từ DiscoveryClient | Danh sách endpoint mà caller nhìn thấy và đích được chọn |
| Gọi DNS của một Service ClusterIP | Endpoint và hành vi chuyển lưu lượng của tầng mạng |
| Kubernetes LoadBalancer tích hợp ở chế độ SERVICE | Đích cấp Service và lớp chuyển lưu lượng phía sau |
| Qua gateway hoặc service mesh | Cả điểm chọn đích tại ứng dụng và các tầng trung gian có liên quan |

TTL danh sách instance trong JVM không điều khiển trực tiếp cache DNS hoặc toàn bộ dataplane của Kubernetes.

Trong phần thực hành, giả sử orders-api dùng Spring Cloud LoadBalancer để chọn trực tiếp endpoint của inventory-api. Không dùng kết quả của đường gọi này để suy ra mọi kiến trúc Service hoặc gateway đều có cùng độ trễ.

## 3. “Loại bỏ Pod” là một chuỗi mốc

Khi một Pod không còn nhận lưu lượng mới, cần phân biệt ít nhất:

1. Xuất hiện tín hiệu cần ngừng nhận yêu cầu mới.
2. Kubernetes công bố trạng thái endpoint tương ứng.
3. DiscoveryClient quan sát thay đổi.
4. Danh sách hiệu lực ở LoadBalancer không còn cho chọn Pod đó.
5. Các request đã bắt đầu trước đó hoàn tất hoặc thất bại.
6. Tiến trình và Pod kết thúc.

Những mốc này không nhất thiết xảy ra đồng thời hoặc theo một thứ tự tuần tự tuyệt đối giữa mọi thành phần. Chẳng hạn, tiến trình có thể dừng trước khi một caller mất kết nối cập nhật được discovery.

Với EndpointSlice, một endpoint đang terminating có thể vẫn tồn tại trong đối tượng thay vì bị xóa ngay. Kubernetes công bố các điều kiện như ready, serving và terminating để người tiêu thụ xử lý. Không tìm thấy một địa chỉ bị xóa khỏi YAML chưa phải tiêu chí duy nhất để biết nó đã hết phù hợp cho lưu lượng mới. [Luồng kết thúc Pod của Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/), [điều kiện EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Một phần dữ liệu minh họa:

~~~yaml
addresses:
  - 10.42.2.22
conditions:
  ready: false
  serving: true
  terminating: true
~~~

Ví dụ này mô tả một endpoint đang kết thúc nhưng có thể còn phục vụ để hoàn tất công việc đang xử lý. Không được suy ra rằng mọi DiscoveryClient đều tự diễn giải đầy đủ các điều kiện đó theo cùng một cách. Phải kiểm tra implementation và phiên bản của ứng dụng.

Thuộc tính include-not-ready-addresses có ảnh hưởng đến việc nhận cả các địa chỉ chưa ready. Nếu mục đích là gọi nghiệp vụ tới instance sẵn sàng, không bật nó chỉ để tránh một danh sách trống. Đồng thời kiểm tra Service có sử dụng publishNotReadyAddresses hoặc cấu hình công bố endpoint đặc biệt hay không. [Thuộc tính discovery của Spring](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html), [EndpointSlice của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

## 4. TTL không phải thời hạn loại bỏ Pod trên toàn hệ thống

### 4.1. TTL ràng buộc bản ghi cache, không ràng buộc trạng thái Pod

TTL trả lời câu hỏi: “Một bản ghi được ghi vào cache có thể được tái sử dụng trong bao lâu theo chính sách hết hạn?”

Nó không trả lời trực tiếp:

- Kubernetes mất bao lâu để phát hiện thay đổi readiness?
- DiscoveryClient có đang nhận được cập nhật không?
- Nguồn upstream có đang trả lại snapshot cũ không?
- Có request nào đã chọn Pod trước khi cache được làm mới không?
- Các caller khác đã hết giữ địa chỉ đó chưa?

TTL hết hạn cũng không đồng nghĩa có một yêu cầu mạng được gửi đúng tại thời điểm đó. Việc lấy danh sách mới có thể xảy ra ở lần truy cập tiếp theo hoặc theo cơ chế làm mới của implementation đang dùng.

### 4.2. Một timeline với một lớp cache bổ sung

Giả sử cache LoadBalancer giữ danh sách trong 15 giây, được ghi lúc t = 0. Đây là số liệu minh họa, không phải kết quả benchmark.

| Thời điểm | Sự kiện |
| --- | --- |
| t = 0 | Cache LoadBalancer nhận danh sách A, B, C |
| t = 2 | Endpoint của B được quan sát là không còn ready |
| t = 4 | DiscoveryClient tại caller đã trả danh sách A, C |
| t = 10 | LoadBalancer vẫn có thể dùng snapshot A, B, C chưa hết hạn |
| t = 15 | Bản ghi cache đạt thời hạn hết hạn |
| t = 16 | Một lần truy cập lấy lại danh sách A, C từ nguồn đã cập nhật |

Ở ví dụ này, discovery đã mới từ t = 4, nhưng một lớp cache phía sau giữ dữ liệu cũ thêm một khoảng thời gian.

Đổi TTL xuống 5 giây có thể giảm phần chờ thuộc lớp này. Nó không làm mốc t = 2 hoặc t = 4 tự dịch chuyển về t = 0.

### 4.3. Cache được nạp lại bằng dữ liệu cũ

Giả sử TTL LoadBalancer là 10 giây, nhưng nguồn discovery chỉ cập nhật ở t = 12:

| Thời điểm | Nguồn discovery | Cache LoadBalancer |
| --- | --- | --- |
| t = 0 | A, B, C | Nạp A, B, C |
| t = 2 | Chưa phản ánh thay đổi của B | Vẫn giữ A, B, C |
| t = 10 | Vẫn trả A, B, C | Hết hạn rồi nạp lại A, B, C |
| t = 12 | Đã chuyển thành A, C | Bản ghi vừa nạp lại vẫn còn B |
| t = 20 | A, C | Lần truy cập tiếp theo có thể nạp A, C |

Việc hết hạn tại t = 10 không giúp loại B vì upstream chưa mới. Khoảng dữ liệu cũ tính từ t = 2 có thể dài hơn một TTL của LoadBalancer.

Đây là lý do không thể lấy một giá trị TTL làm cam kết độ trễ đầu cuối. Nếu upstream bị mất đồng bộ lâu hoặc có cơ chế giữ dữ liệu cũ khi lỗi, chưa có cơ sở để tuyên bố một giới hạn hữu hạn chỉ từ cấu hình cache phía sau.

### 4.4. Mô hình để phân tích, không phải công thức bảo đảm

Với một đường cập nhật đơn giản, có thể phân rã độ trễ thành:

~~~text
Độ trễ ngừng chọn endpoint
  ≈ thời gian phát hiện và công bố thay đổi
  + thời gian discovery phản ánh thay đổi
  + thời gian các snapshot phía sau còn được dùng
  + thời gian tới lần chọn hoặc lần quan sát tiếp theo
~~~

Các thành phần có thể chồng lấp. Chỉ khi hiểu cơ chế cập nhật của từng lớp mới có thể dùng mô hình này để lập ngân sách độ trễ.

## 5. Cấu hình cache Spring Cloud LoadBalancer

### 5.1. Bật cache với thời hạn tường minh

Một cấu hình để so sánh trong môi trường thực hành:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 5s
        capacity: 256
~~~

Giá trị 5s là lựa chọn thí nghiệm. Không xem đây là khuyến nghị chung cho mọi hệ thống.

Tài liệu Spring Cloud Commons mô tả TTL tính từ lúc ghi bản ghi, giá trị mặc định 35s và capacity ban đầu 256 cho cấu hình chuẩn. Cần đối chiếu phiên bản, provider và cấu hình có hiệu lực trước khi áp dụng các giá trị đó vào phân tích. [Thuộc tính Spring Cloud Commons](https://docs.spring.io/spring-cloud-commons/reference/configprops.html).

Các khái niệm cần hiểu đúng:

| Thuộc tính | Ý nghĩa cần kiểm tra | Cách hiểu sai |
| --- | --- | --- |
| enabled | Có dùng cơ chế cache LoadBalancer được cấu hình hay không | Tắt toàn bộ cache trong discovery và HTTP |
| ttl | Thời hạn bản ghi trong lớp cache tương ứng | Thời gian tối đa để mọi caller loại Pod |
| capacity | Sức chứa ban đầu theo cấu hình chuẩn | Số Pod tối đa được khám phá hoặc giới hạn cứng bộ nhớ |

Một bản ghi có thể giữ cả danh sách nhiều instance. Không dùng capacity để điều chỉnh số replica backend.

### 5.2. Tắt lớp cache bổ sung để đo ảnh hưởng

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Cấu hình này hữu ích khi cần so sánh với một DiscoveryClient đã có cơ chế lưu và đồng bộ trạng thái riêng. Cần xác minh supplier hiệu lực thực sự đi theo cấu hình đó, nhất là khi ứng dụng có bean hoặc cache manager tùy biến.

Tài liệu LoadBalancer lưu ý tránh cache lặp khi DiscoveryClient đã có cache. Điều cần quyết định là lớp nào chịu trách nhiệm giữ danh sách và độ mới nào ứng dụng cần, không phải tắt cache ở mọi nơi. [Cache Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Tắt cache bổ sung không đồng nghĩa mỗi lần chọn instance đều tạo một truy vấn Kubernetes API. Với implementation dùng trạng thái nội bộ, lời gọi DiscoveryClient có thể đọc chính trạng thái đang được theo dõi đó.

Không dùng ttl: 0s như một cách thay thế mặc định cho enabled: false. Cách diễn giải thời hạn bằng không có thể phụ thuộc provider và cấu hình; muốn tắt cơ chế đã có thuộc tính điều khiển thì dùng thuộc tính đó và kiểm chứng kết quả.

### 5.3. Caffeine có thể thay đổi cấu hình bạn nghĩ đang áp dụng

Nếu dùng Caffeine và chỉ định specification riêng, specification có thể ghi đè cấu hình TTL và capacity chung. [Tài liệu provider cache của LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

Ví dụ gây hiểu nhầm:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 5s
        caffeine:
          spec: expireAfterWrite=30s,maximumSize=256
~~~

Không kết luận hệ thống đang dùng 5 giây chỉ từ dòng ttl. Nếu specification Caffeine này có hiệu lực, thời hạn được chỉ định trong specification là 30 giây.

Khi thực sự chọn Caffeine, dùng một cấu hình nhất quán, chẳng hạn:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: expireAfterWrite=5s,maximumSize=256
~~~

Đoạn này chỉ dành cho ứng dụng đã có Caffeine và dùng provider tương ứng. maximumSize là giới hạn số bản ghi theo chính sách cache, không phải số Pod trong mỗi danh sách.

## 6. Những lớp cập nhật dễ bị bỏ sót

### 6.1. Trạng thái nội bộ DiscoveryClient

Một implementation dựa trên Kubernetes có thể giữ dữ liệu tài nguyên qua cơ chế list/watch, informer hoặc cơ chế đồng bộ tương ứng. Việc API đã có dữ liệu mới không chứng minh trạng thái nội bộ tại từng caller đã mới.

Khi có nghi ngờ, so sánh đồng thời:

- Trạng thái endpoint đọc được từ Kubernetes API.
- Danh sách mà chính DiscoveryClient của caller trả về.
- Danh sách ứng viên LoadBalancer đang sử dụng.

Nếu hai lớp đầu đã khác nhau, giảm TTL LoadBalancer chỉ điều chỉnh phần ở phía sau lỗi đồng bộ.

Các thuộc tính cache-loading-timeout-seconds và wait-cache-ready liên quan việc khởi tạo dữ liệu discovery theo implementation được tài liệu hóa. Chúng không phải TTL loại bỏ Pod khi chạy ổn định. [Thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

### 6.2. HTTP discovery và cache phản hồi

Khi dùng Discovery Server, cần đo cả phía server và caller. Server có thể đã nhận thay đổi, trong khi client hoặc một lớp trung gian còn giữ response cũ; chiều ngược lại cũng có thể xảy ra nếu server chưa đồng bộ.

Tài liệu Spring Cloud Kubernetes mô tả các tùy chọn cacheable discovery client được bổ sung từ dòng 5.0, với các thuộc tính cacheable.reactive.enabled và cacheable.blocking.enabled trong nhóm discovery. Chỉ sử dụng khi implementation và phiên bản của dự án hỗ trợ. Các tùy chọn này là một lớp khác với loadbalancer.cache.enabled. [Cacheable discovery client](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Không giả định TTL của LoadBalancer cũng cấu hình thời hạn cho một cache dùng Spring Cache hoặc cache phản hồi HTTP.

### 6.3. Catalog watch và sự kiện thay đổi

Nhịp kiểm tra danh mục hoặc heartbeat có thể góp phần phát hiện thay đổi theo cấu hình. Tuy nhiên, một sự kiện được phát ra không chứng minh mọi cache tùy biến đều đăng ký xử lý và xóa đúng khóa.

Nếu thiết kế dựa vào invalidation theo sự kiện, cần xác minh đủ chuỗi: phát hiện thay đổi, phát sự kiện, bên nhận, khóa bị vô hiệu hóa và lần lấy danh sách mới. Không thay catalog-services-watch-delay rồi mặc định đó là TTL của toàn bộ discovery. [Theo dõi danh mục dịch vụ](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

### 6.4. Supplier kiểm tra sức khỏe hoặc supplier tự viết

Health-check supplier có thể giữ trạng thái và có nhịp kiểm tra riêng. Một supplier tự viết có thể lưu danh sách trong một biến, dùng một bộ đếm thời gian khác hoặc giữ dữ liệu cũ khi upstream lỗi.

Thuộc tính của cache chuẩn không tự kiểm soát mọi bộ nhớ đệm do mã ứng dụng tạo ra. Ghi rõ cấu trúc supplier đang dùng trước khi xem một thay đổi cấu hình là đã có hiệu lực.

Với chuỗi có bộ lọc theo request, không cache một kết quả đã lọc cho request cụ thể rồi vô tình dùng nó cho request khác. Cache danh sách nguồn và việc lọc ứng viên theo ngữ cảnh là hai trách nhiệm cần tổ chức rõ ràng.

## 7. Thiết kế phép đo có thể phân biệt nguyên nhân

Giả sử inventory-api có ba Pod A, B, C và bạn muốn đo việc loại B khi nó không còn phù hợp cho lưu lượng mới.

Dùng namespace thực hành riêng, chọn rõ Pod và ghi nhận UID cùng IP. Một tên Pod hoặc IP có thể xuất hiện lại trong vòng đời khác; UID giúp tránh nhầm instance cũ và mới.

### 7.1. Chọn mốc quan sát

| Mốc | Ý nghĩa |
| --- | --- |
| T0 | Gửi yêu cầu thay đổi hoặc phát tín hiệu drain |
| T1 | Lần đầu bộ quan sát thấy endpoint không còn ready hoặc phù hợp |
| T2 | Lần đầu quan sát thấy DiscoveryClient bỏ instance đó |
| T3 | Lần đầu xác nhận danh sách hiệu lực ở caller không còn ứng viên đó |
| T4 | Thời điểm chọn đích của một request cụ thể |
| T5 | Thời điểm request đó hoàn tất |

T1 và T2 trong một phép lấy mẫu là thời điểm **quan sát**, không mặc định là thời điểm thay đổi thật trên hệ thống nguồn. Khoảng lấy mẫu và độ trễ mạng tạo ra sai số.

T4 không đồng nghĩa T5. Một request bắt đầu trước khi endpoint bị loại có thể hoàn tất sau đó mà không chứng minh có lựa chọn mới sai.

Với nhiều caller, ghi cả định danh caller. Nếu chỉ đo một Pod orders-api, kết luận chỉ áp dụng cho Pod đó và khoảng thời gian đã quan sát.

### 7.2. Thu thập dữ liệu tối thiểu

Một bản ghi theo dõi hữu ích có thể chứa:

~~~text
observedAt
callerPodUID
serviceId
backendPodUID hoặc endpoint cần đối chiếu
endpointReady / endpointTerminating nếu có
danh sách ứng viên hoặc dấu vân tay của danh sách
requestId
attemptNumber
selectedAt
completedAt
kết quả hoặc loại lỗi
~~~

Đây là mẫu dữ liệu do ứng dụng hoặc bộ đo thiết kế, không phải một định dạng log mặc định của Spring Cloud Kubernetes.

Đồng bộ đồng hồ giữa các máy hoặc ghi rõ sai số khi đối chiếu timestamp. Để đo khoảng thời gian trong một tiến trình, có thể dùng đồng hồ đơn điệu; timestamp UTC phục vụ liên kết sự kiện giữa các nguồn.

Không cần ghi toàn bộ annotation, Secret hay nội dung request để đo việc loại endpoint. Chỉ giữ các định danh và trạng thái phục vụ phép đo.

## 8. Quan sát Kubernetes và DiscoveryClient

### 8.1. Ghi nhận Pod và endpoint nguồn

Các lệnh sau dành cho người học chạy trong cluster thực hành đã được phép sử dụng. Bài học không giả định chúng đã được thực thi.

~~~powershell
kubectl -n shop-demo get pods -l app=inventory-api -o wide
kubectl -n shop-demo get endpointslices -l kubernetes.io/service-name=inventory-api -o yaml
~~~

Một Service có thể có nhiều EndpointSlice. Cần xét tất cả slice liên quan và đối chiếu targetRef, địa chỉ, cổng và conditions; không chỉ tìm một đối tượng có tên giống Service.

Có thể lấy mẫu ngắn hạn để in thời điểm quan sát và trạng thái:

~~~powershell
1..20 | ForEach-Object {
    $snapshot = kubectl -n shop-demo get endpointslices -l kubernetes.io/service-name=inventory-api -o json | ConvertFrom-Json
    $observedAt = [DateTimeOffset]::UtcNow.ToString("o")

    foreach ($slice in $snapshot.items) {
        foreach ($endpoint in $slice.endpoints) {
            [pscustomobject]@{
                ObservedAt = $observedAt
                Slice = $slice.metadata.name
                ResourceVersion = $slice.metadata.resourceVersion
                Addresses = ($endpoint.addresses -join ",")
                PodName = $endpoint.targetRef.name
                PodUID = $endpoint.targetRef.uid
                Ready = $endpoint.conditions.ready
                Serving = $endpoint.conditions.serving
                Terminating = $endpoint.conditions.terminating
            } | ConvertTo-Json -Compress
        }
    }

    Start-Sleep -Seconds 1
}
~~~

Timestamp được ghi khi nhận và xử lý snapshot ở máy quan sát. resourceVersion phục vụ nhận diện phiên bản tài nguyên, không phải timestamp để đổi trực tiếp thành số mili giây.

Một vòng lấy mẫu còn mất thời gian thực hiện lệnh, nên chu kỳ thực tế không chính xác một giây. Dùng phép lấy mẫu có giới hạn cho thí nghiệm; không nhân bản các vòng truy vấn tần suất cao trên toàn hệ thống chỉ để theo dõi thường xuyên.

### 8.2. Đọc snapshot từ chính caller

Một thành phần chẩn đoán nội bộ có thể in danh sách mà DiscoveryClient đang trả:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class DiscoverySnapshotProbe {

    private static final Logger log =
            LoggerFactory.getLogger(DiscoverySnapshotProbe.class);

    private final DiscoveryClient discoveryClient;

    public DiscoverySnapshotProbe(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void printSnapshot(String serviceId) {
        List<String> candidates = discoveryClient.getInstances(serviceId)
                .stream()
                .map(instance -> instance.getInstanceId() + "@"
                        + instance.getHost() + ":" + instance.getPort())
                .sorted()
                .toList();

        log.info("discoverySnapshot observedAt={} caller={} service={} candidates={}",
                Instant.now(),
                System.getenv().getOrDefault("HOSTNAME", "unknown"),
                serviceId,
                candidates);
    }
}
~~~

Ví dụ dùng Java 17 trở lên và một ứng dụng đã có DiscoveryClient. Gọi probe trong ngữ cảnh chẩn đoán được kiểm soát; không đặt lời gọi blocking này trên event loop của WebFlux.

Probe chỉ đọc đầu ra DiscoveryClient. Nó chưa chứng minh danh sách hiệu lực sau mọi supplier và cache LoadBalancer đã giống hệt. Nếu cần đo T3 hoặc đích được chọn, bổ sung điểm quan sát tại chuỗi supplier hoặc vòng đời LoadBalancer phù hợp với phiên bản đang dùng.

Việc thêm probe cũng có thể làm nguồn discovery được truy cập hoặc cache được nạp sớm hơn. Giữ cùng cách đo giữa các lượt thử và ghi nhận ảnh hưởng này khi diễn giải kết quả.

### 8.3. Kiểm tra quyền và kênh cập nhật

Với caller đọc Kubernetes API trực tiếp, kiểm tra đúng ServiceAccount và các quyền đọc cần cho implementation, gồm list/watch cho nguồn endpoint đang dùng. Với EndpointSlice, API group là discovery.k8s.io.

~~~powershell
$callerIdentity = "system:serviceaccount:shop-demo:orders-discovery-reader"

kubectl auth can-i list endpointslices.discovery.k8s.io -n shop-demo --as=$callerIdentity
kubectl auth can-i watch endpointslices.discovery.k8s.io -n shop-demo --as=$callerIdentity
kubectl -n shop-demo logs deployment/orders-api --tail=100
~~~

Người thực hiện --as cần quyền impersonation phù hợp. Ngoài RBAC, xem lỗi kết nối API, watch bị ngắt, quá trình kết nối lại và lỗi khởi tạo hoặc đồng bộ cache.

Không cấp thêm quyền đọc Secret để sửa một lỗi watch EndpointSlice. Quyền cần bổ sung phải khớp tài nguyên, thao tác và namespace thực sự thiếu.

## 9. So sánh cấu hình bằng một thí nghiệm có kiểm soát

### 9.1. Chuẩn bị cùng một điều kiện ban đầu

Giữ các điều kiện sau giống nhau giữa các lượt:

- Cùng phiên bản ứng dụng và thư viện.
- Cùng service ID, namespace và nguồn endpoint.
- Số replica backend và caller được ghi nhận rõ.
- Cùng cách tạo tải và cách thu thập dữ liệu.
- Cùng cơ chế readiness và dừng ứng dụng.
- Những cache khác không bị thay đổi ngoài chủ đích thí nghiệm.

Trước mỗi lượt, xác nhận caller đã thấy đủ các instance sẵn sàng và cache cần thử đã được sử dụng. Nếu không làm ấm cache ở lượt bật cache, phép đo có thể bỏ qua chính tình huống giữ danh sách cũ mà bạn muốn kiểm tra.

### 9.2. Chọn thay đổi phù hợp mục tiêu

Có thể so sánh ba cấu hình:

| Lượt | Cache bổ sung ở LoadBalancer | Mục đích |
| --- | --- | --- |
| A | Tắt | Ước lượng phần trễ còn lại trong nguồn discovery và các lớp khác |
| B | TTL 5s | Quan sát ảnh hưởng của một thời hạn ngắn có chủ đích |
| C | TTL 20s | So sánh khi thời hạn giữ snapshot dài hơn |

Các con số là giá trị thử nghiệm, không phải mục tiêu vận hành mặc định.

Nếu dùng thao tác xóa Pod, chọn một Pod cụ thể trong môi trường thực hành và giữ quá trình kết thúc thông thường:

~~~powershell
$retiringPod = "inventory-api-REPLACE_WITH_POD_NAME"
kubectl -n shop-demo delete pod $retiringPod --wait=false
~~~

Thay placeholder bằng đúng Pod đã ghi nhận UID. Lệnh trên có tác động đến workload khi người học thực hiện; không chạy trên môi trường đang phục vụ ngoài phạm vi thí nghiệm.

Xóa Pod và làm readiness thất bại là hai tình huống khác nhau. Không gộp kết quả của chúng thành một độ trễ chung mà không ghi nguyên nhân kích hoạt. ReplicaSet có thể tạo Pod thay thế trong lúc bạn quan sát.

### 9.3. Đo lựa chọn và kết quả theo hai luồng

Luồng thứ nhất ghi trạng thái nguồn và các snapshot. Luồng thứ hai gửi yêu cầu liên tục ở tốc độ có kiểm soát qua caller.

Backend nên trả định danh Pod trong endpoint thử nghiệm hoặc gắn định danh đó vào log có request ID. Ghi cả lỗi, thời điểm bắt đầu, thời điểm hoàn tất và lần thử. Nếu chỉ ghi response thành công, các lần chọn Pod cũ nhưng không kết nối được sẽ biến mất khỏi dữ liệu.

Không dùng retry để che lỗi trong lượt đầu đo ảnh hưởng cache. Nếu hệ thống bắt buộc có retry, ghi từng attempt để phân biệt “lần đầu chọn địa chỉ cũ” với “request cuối cùng vẫn thành công”.

### 9.4. Diễn giải kết quả

Giả sử kết quả minh họa cho thấy:

| Quan sát | Suy luận có thể kiểm tra tiếp |
| --- | --- |
| T1 và T2 gần nhau, T3 muộn hơn rõ ở lượt bật cache | Cache sau discovery có thể là phần trễ đáng kể |
| T2 luôn muộn ở cả ba lượt | Cần kiểm tra nguồn discovery và đường đồng bộ |
| T3 đã mới nhưng còn response từ Pod cũ | Có thể là request đang bay hoặc còn tầng định tuyến khác |
| Chỉ một caller còn dùng Pod cũ | So sánh snapshot, cấu hình và kết nối cập nhật của caller đó |
| Tắt cache nhưng dữ liệu vẫn cũ rất lâu | Tìm cache hoặc lỗi cập nhật ở upstream |

Đây là hướng suy luận, không phải kết luận chỉ từ một dòng log. Lặp lại đủ lần, thay đổi thời điểm kích hoạt so với lúc nạp cache và so sánh phân bố độ trễ. Một lần chạy thuận lợi không thể đại diện cho trường hợp ngay sau khi một snapshot cũ vừa được nạp lại.

Nếu khoảng lấy mẫu là một giây, không báo cáo kết quả chính xác đến từng mili giây như thể nguồn đã được quan sát liên tục.

## 10. Phối hợp cache với quá trình dừng ứng dụng

Giảm cửa sổ giữ địa chỉ cũ và dừng ứng dụng có kiểm soát giải quyết hai phần khác nhau của cùng một tình huống.

Một quá trình dừng có chủ đích thường cần:

1. Làm workload không còn phù hợp để nhận lựa chọn mới.
2. Cho phép tín hiệu đó lan tới các thành phần định tuyến và discovery.
3. Hoàn tất yêu cầu đang xử lý.
4. Dừng tiến trình trong thời hạn Kubernetes cho phép.

Nếu tiến trình đóng cổng ngay khi một caller còn giữ địa chỉ cũ, caller có thể gặp lỗi kết nối. Nếu tiến trình tiếp tục nhận yêu cầu mới vô thời hạn, việc drain lại không có điểm kết thúc.

Ví dụ cấu hình Spring Boot:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Và một phần Pod spec minh họa:

~~~yaml
spec:
  terminationGracePeriodSeconds: 40
~~~

Đây là các giá trị để phân tích, không bảo đảm mọi request sẽ hoàn tất. Thuộc tính timeout-per-shutdown-phase là thời hạn theo pha dừng, không phải TTL discovery hoặc mặc định một giới hạn tổng cho mọi hoạt động shutdown. Cách web server ngừng nhận yêu cầu mới cũng cần đối chiếu với server đang dùng. [Graceful shutdown của Spring Boot](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).

Thời gian grace của Pod còn phải tính các công việc trước khi tiến trình kết thúc, gồm preStop nếu được cấu hình. Không dành toàn bộ thời hạn cho một bước chờ rồi kỳ vọng ứng dụng vẫn còn nguyên từng đó thời gian để hoàn tất request. [Kết thúc Pod và preStop](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/).

Một preStop chỉ chờ cố định không tự chứng minh mọi caller đã làm mới discovery. Nếu dùng một khoảng chờ để hỗ trợ lan truyền trạng thái, phải đo độ trễ thực tế, xác định ứng dụng đang nhận hay từ chối request trong khoảng đó và vẫn dự phòng cho biến động.

Graceful shutdown chủ yếu giúp xử lý việc dừng và các yêu cầu đã nhận. Nó không làm cache trên caller bị xóa từ xa, cũng không buộc mọi lần gọi dùng địa chỉ cũ sẽ thành công.

## 11. Chọn chính sách theo nhu cầu, không chỉ theo TTL nhỏ nhất

| Mục tiêu | Lựa chọn có thể phù hợp | Đánh đổi cần đo |
| --- | --- | --- |
| Hạn chế giữ snapshot lặp | Dùng cơ chế cập nhật của discovery, bỏ cache bổ sung khi phù hợp | Tải và chi phí mỗi lần lấy danh sách từ discovery |
| Giảm số lần dựng hoặc lấy danh sách | Giữ cache có thời hạn rõ ràng | Cửa sổ dùng danh sách cũ |
| Loại endpoint nhanh khi đổi trạng thái | Kiểm tra đồng bộ và invalidation theo sự kiện đã được hỗ trợ | Độ tin cậy của kênh sự kiện và hành vi khi mất kết nối |
| Giữ khả năng hoạt động khi nguồn discovery tạm lỗi | Có chính sách dữ liệu cũ tường minh nếu hệ thống hỗ trợ | Có thể chọn địa chỉ không còn dùng được |
| Giảm lỗi lúc rollout | Phối hợp readiness, cập nhật danh sách và drain | Thời gian rollout, tài nguyên dự phòng và request đang xử lý |

TTL nhỏ làm giảm một phần thời gian giữ snapshot nhưng có thể tăng số lần truy cập delegate, số lần gọi HTTP discovery hoặc chi phí dựng danh sách. Mức tăng tải Kubernetes API còn tùy delegate đọc trạng thái nội bộ hay truy vấn API trực tiếp.

Khi có nhiều caller và nhiều service ID, thời điểm hết hạn gần nhau có thể tạo đợt lấy lại dữ liệu tập trung. Cần đo tại lớp thực sự chịu tải, không chỉ đếm số request nghiệp vụ.

Nếu cân nhắc giữ dữ liệu cũ khi lỗi, xác định rõ trạng thái nào được chấp nhận và bao lâu. Không để một chính sách phục hồi tạm thời trở thành việc giữ danh sách vô thời hạn mà không có cảnh báo vận hành.

Thay TTL qua ConfigMap cũng chưa bảo đảm cache manager và supplier đang chạy được tái cấu hình ngay. Phải kiểm tra vòng đời bean, cách nạp lại cấu hình và cơ chế refresh được dùng. Configuration Watcher chỉ có ý nghĩa trong một luồng cập nhật được thiết kế rõ; không mặc định nó điều khiển cache instance.

## 12. Chẩn đoán theo vị trí danh sách bị chậm

| Triệu chứng | Điều cần kiểm tra | Điều chưa nên kết luận |
| --- | --- | --- |
| Pod không ready nhưng endpoint vẫn được coi phù hợp | Probe, Service, điều kiện endpoint và thời điểm quan sát | Cache LoadBalancer chắc chắn sai |
| API đã mới nhưng DiscoveryClient còn địa chỉ cũ | Đồng bộ, quyền watch, kết nối và cache upstream | Giảm TTL phía sau sẽ chữa toàn bộ vấn đề |
| DiscoveryClient đã bỏ địa chỉ, LoadBalancer vẫn chọn | Supplier hiệu lực, cache bổ sung, cấu hình Caffeine | Kubernetes chưa loại Pod |
| Không còn lựa chọn mới nhưng response vẫn về | Request bắt đầu trước đó, thời gian xử lý và retry | Có một lần chọn mới sau khi endpoint bị loại |
| Tắt cache chuẩn nhưng không đổi hành vi | Bean tùy biến, cache khác, cấu hình có hiệu lực | Thuộc tính chắc chắn bị framework bỏ qua |
| Chỉ vài caller chậm hội tụ | Version, cấu hình và trạng thái riêng của từng tiến trình | Cần khởi động lại toàn bộ hệ thống |
| Pod mới ready nhưng chưa được chọn | Cửa sổ giữ danh sách và tiêu chí chọn ứng viên | Pod mới không chạy đúng |
| Không có lỗi nhưng vẫn chọn Pod cũ | Backend còn phục vụ, retry hoặc cơ chế drain | Danh sách đã hoàn toàn mới |

Không lấy việc “khởi động lại caller thì hết” làm bằng chứng duy nhất cho một lỗi cache. Khởi động lại có thể đồng thời tạo lại kết nối watch, nạp cấu hình mới và dựng lại nhiều bean.

Nếu tạm giảm TTL để giảm tác động vận hành, vẫn cần tìm vị trí dữ liệu bị cũ. Một thay đổi làm ít lỗi hơn chưa chứng minh nguyên nhân gốc đã được xử lý.

## 13. Tiêu chí hoàn thành việc phân tích

Bạn đã hiểu và kiểm soát được tình huống khi có thể chứng minh:

- Đường gọi thực tế chọn endpoint trực tiếp hay đi qua đích cấp Service.
- Những lớp giữ danh sách và cách cập nhật của từng lớp đã được xác định.
- TTL, cache provider và cấu hình có hiệu lực đã được đối chiếu với phiên bản.
- Quyền và đường kết nối cập nhật discovery hoạt động đúng.
- Mốc endpoint đổi trạng thái, mốc discovery cập nhật và mốc caller ngừng chọn được phân biệt.
- Kết quả có định danh caller, instance và thông tin từng attempt cần thiết.
- Request đang bay được tách khỏi lựa chọn mới.
- Thí nghiệm có ghi sai số lấy mẫu và giới hạn phạm vi quan sát.
- Chính sách shutdown phù hợp với thời gian lan truyền và công việc đang xử lý.
- Lựa chọn giữ hoặc bỏ cache bổ sung có lý do dựa trên dữ liệu.

Cấu hình tốt không chỉ có một TTL nhỏ. Nó giúp giải thích được địa chỉ đã cũ ở lớp nào, trong bao lâu, caller nào còn sử dụng và cơ chế nào đưa hệ thống trở lại danh sách đích hợp lệ.
