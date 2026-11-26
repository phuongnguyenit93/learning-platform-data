# Quan hệ giữa sức khỏe ứng dụng và khả năng truy cập API server

Trong chương **Actuator và sức khỏe** của module **SPRING_CLOUD_KUBERNETES**, cần phân biệt hai câu hỏi: ứng dụng có phục vụ được nghiệp vụ hay không, và tiến trình ứng dụng có thực hiện được một thao tác cụ thể với Kubernetes API server hay không. Hai câu trả lời có thể khác nhau.

Một dịch vụ đặt hàng vẫn có thể xử lý yêu cầu khi API server tạm thời không truy cập được, nếu cấu hình đã nạp, các kết nối nghiệp vụ còn hoạt động và dữ liệu discovery hiện có vẫn đủ dùng. Ngược lại, một controller phải tạo tài nguyên Kubernetes cho mỗi yêu cầu sẽ bị ảnh hưởng trực tiếp. Chính quan hệ phụ thuộc này quyết định cách dùng Actuator, liveness, readiness và cảnh báo.

## 1. Mục tiêu và điều kiện thực hành

Sau bài học, bạn có thể:

- Giải thích vì sao mất kết nối API server không đồng nghĩa JVM bị hỏng hoặc mọi nghiệp vụ đều dừng.
- Phân biệt tín hiệu liveness, readiness, sức khỏe tổng hợp và kết quả truy cập Kubernetes API.
- Xác định tác động đến DiscoveryClient, Spring Cloud LoadBalancer, ConfigMap, Secret và Configuration Watcher.
- Thiết kế probe tránh gây khởi động lại hàng loạt khi một phụ thuộc chung gặp sự cố.
- Phân biệt lỗi mạng, TLS, xác thực và RBAC bằng một thao tác đọc có phạm vi rõ ràng.
- Chọn bật hoặc tắt Kubernetes health contributor theo nhu cầu triển khai thực tế.

Các ví dụ cấu hình dùng cách tổ chức Actuator của **Spring Boot 3.5.x**, kết hợp **Spring Cloud Kubernetes 3.3.x** trong một bộ phiên bản tương thích do Spring Cloud BOM quản lý. Đây là mốc tham chiếu cho ví dụ, không phải yêu cầu nâng cấp dự án. Nếu dùng dòng phiên bản khác, đối chiếu tài liệu tương ứng trước khi sao chép cấu hình.

Ứng dụng thực hành cần có Actuator và phần tích hợp Kubernetes đang sử dụng. Các lệnh `kubectl` giả định có namespace `health-lab`, Deployment `orders` và ServiceAccount `orders-sa`. Bạn thay các tên này bằng môi trường lab của mình.

## 2. Hai luồng giao tiếp có thể hỏng độc lập

API server cung cấp giao diện để đọc, ghi và theo dõi tài nguyên Kubernetes. Nó thuộc control plane. Lưu lượng HTTP nghiệp vụ giữa các dịch vụ đi qua những thành phần mạng khác; API server thường không đứng giữa từng yêu cầu nghiệp vụ. Vai trò các thành phần được mô tả trong [Kubernetes Components](https://kubernetes.io/docs/concepts/overview/components/).

~~~mermaid
flowchart LR
    User["Người dùng"] --> Entry["Ingress / Gateway / Service"]
    Entry --> App["Ứng dụng Spring Boot"]
    App --> Business["Database / dịch vụ nghiệp vụ"]

    Kubelet["kubelet trên node"] -->|"HTTP probe"| Actuator["Actuator trong ứng dụng"]
    App -->|"đọc cấu hình / discovery / watch"| API["Kubernetes API server"]
    Watcher["Configuration Watcher"] -->|"theo dõi thay đổi"| API
    Watcher -->|"thông báo cập nhật"| App
~~~

Từ sự phân tách đó có thể suy ra một kịch bản: API server gián đoạn nhưng Pod đang chạy vẫn trả lời HTTP qua đường mạng đã thiết lập. Đây là khả năng cần kiểm chứng trong kiến trúc cụ thể, không phải cam kết rằng toàn bộ cluster tiếp tục vận hành bình thường.

Khi control plane gián đoạn, việc cập nhật trạng thái, thay đổi tập endpoint, điều phối Pod mới hoặc nhận cấu hình mới có thể bị chậm hay dừng. Nếu đồng thời hỏng CNI, DNS, node hoặc database, tác động sẽ rộng hơn. Vì vậy, kết luận “API server lỗi nhưng ứng dụng không bị ảnh hưởng” cũng quá tuyệt đối.

Một chi tiết quan trọng: kubelet gọi HTTP probe của container từ node. Probe không cần gọi Kubernetes API server chỉ để gửi HTTP đến ứng dụng. Tuy nhiên, nếu chính mã xử lý health lại gọi API server, bạn đã đưa phụ thuộc đó vào đường đi của probe. Việc truyền trạng thái readiness và cập nhật định tuyến qua control plane còn có độ trễ; không nên giả định thay đổi readiness được mọi thành phần quan sát tức thì trong một sự cố control plane.

## 3. Sức khỏe là một tập tín hiệu, không phải một biến duy nhất

Hãy coi sức khỏe ứng dụng là các chiều độc lập:

| Chiều đánh giá | Câu hỏi | Bằng chứng phù hợp |
| --- | --- | --- |
| Liveness | Tiến trình có ở trạng thái cần được khởi động lại để phục hồi không? | Trạng thái nội bộ, khả năng tiến triển của tiến trình |
| Readiness | Instance này có nên nhận thêm lưu lượng nghiệp vụ không? | Trạng thái sẵn sàng và các điều kiện thiết yếu của nghiệp vụ |
| Kết nối API server | Từ vị trí này, thao tác Kubernetes nào vừa thành công hoặc thất bại? | Kết quả gọi API có timeout, danh tính và tài nguyên xác định |
| Tính mới của dữ liệu | Cấu hình hoặc dữ liệu discovery đang dùng có còn phù hợp không? | Thời điểm đồng bộ thành công, phiên bản cấu hình, tình trạng watch |
| Chất lượng nghiệp vụ | Người dùng có hoàn thành thao tác với độ trễ và độ đúng chấp nhận được không? | Tỷ lệ lỗi, độ trễ, kiểm thử giao dịch đại diện |

Ví dụ, một Pod có thể đồng thời **liveness UP**, **readiness UP**, **đọc Kubernetes API thất bại** và **đơn hàng vẫn xử lý thành công**. Điều này hợp lý nếu dữ liệu hiện có đủ phục vụ.

Một Pod khác có thể đọc API server thành công nhưng readiness không đạt do thiếu cấu hình bắt buộc hoặc không hoàn thành bước khởi tạo. Kết nối API tốt không chứng minh ứng dụng đã sẵn sàng.

## 4. Đọc đúng ý nghĩa của Kubernetes health contributor

Spring Cloud Kubernetes cung cấp Kubernetes health contributor, thường xuất hiện với tên `kubernetes` trong Actuator khi điều kiện tự cấu hình được đáp ứng. Tài liệu mô tả các thông tin như tên Pod, IP, namespace, ServiceAccount, node và cờ cho biết ứng dụng ở trong hay ngoài Kubernetes. Có thể tắt contributor bằng `management.health.kubernetes.enabled=false`. Xem [Pod Health Indicator của Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/pod-health-indicator.html).

Cần tránh diễn giải rộng hơn phạm vi đó:

- Có metadata Pod không chứng minh mọi thao tác `get`, `list`, `watch` đều được cấp quyền.
- Đọc Pod thành công không chứng minh đọc Secret hoặc theo dõi EndpointSlice thành công.
- Một kết quả health không tự chứng minh dữ liệu DiscoveryClient hay cấu hình nghiệp vụ đang mới.
- Không được mặc định mỗi lần gọi endpoint health đều thực hiện một yêu cầu mạng mới đến API server. Muốn kết luận về điều này phải đối chiếu triển khai, client và phiên bản đang chạy.

Khi điều tra, ghi rõ tên contributor đang lỗi. Kubernetes health contributor, health của DiscoveryClient và một indicator tự viết để kiểm tra API server là các tín hiệu khác nhau; không gom tất cả thành “Kubernetes hỏng”.

Ví dụ JSON sau chỉ minh họa cách các tín hiệu có thể được tổng hợp, không mô tả đầu ra bắt buộc của contributor có sẵn:

~~~json
{
  "status": "DOWN",
  "components": {
    "livenessState": {
      "status": "UP"
    },
    "readinessState": {
      "status": "UP"
    },
    "kubernetesApiAccess": {
      "status": "DOWN"
    }
  }
}
~~~

Ở đây, `kubernetesApiAccess` là tên minh họa cho một contributor tùy biến. Nó không phải bean mặc định mà mọi ứng dụng Spring Cloud Kubernetes đều có.

## 5. Mức phụ thuộc vào API server quyết định tác động

Trước khi đưa kiểm tra API server vào readiness, hãy xem đường đi của một yêu cầu nghiệp vụ.

| Cách ứng dụng dùng Kubernetes | Khi truy cập API server bị gián đoạn | Điều cần quan sát |
| --- | --- | --- |
| Cấu hình đã được nạp và giữ trong bộ nhớ | Có thể tiếp tục xử lý bằng cấu hình hiện tại | Cấu hình đó còn hợp lệ và an toàn trong bao lâu |
| ConfigMap hoặc Secret được đưa vào qua biến môi trường | Giá trị trong tiến trình đang chạy không tự thay đổi | Cách triển khai bản cấu hình mới và nhu cầu khởi động lại |
| Cấu hình được mount thành file | Đọc file đã có không phải mỗi lần đều gọi API từ ứng dụng | Việc cập nhật volume và việc ứng dụng đọc lại file |
| DiscoveryClient lấy dữ liệu Kubernetes | Đồng bộ ban đầu hoặc cập nhật tiếp theo có thể bị ảnh hưởng | Client cụ thể, trạng thái đồng bộ và dữ liệu còn sử dụng được |
| Spring Cloud LoadBalancer dùng instance từ discovery | Việc chọn đích phụ thuộc danh sách mà supplier đang cung cấp | Có đích hợp lệ hay chỉ còn địa chỉ đã lỗi thời |
| Gọi dịch vụ qua DNS/ClusterIP | Ứng dụng thường không cần gọi API server cho từng request | DNS, đường mạng Service và khả năng cập nhật endpoint |
| Configuration Watcher theo dõi ConfigMap/Secret | Thông báo thay đổi có thể đến chậm hoặc không đến | Lần đồng bộ thành công gần nhất và cơ chế phục hồi |
| Xử lý yêu cầu phải tạo hoặc sửa tài nguyên Kubernetes | Nghiệp vụ đó có thể thất bại ngay | Timeout, phân quyền, tính lặp an toàn và cách trả lỗi |

Các hàng trên là phân tích tình huống, không khẳng định mọi client có cùng cơ chế cache hoặc retry. DiscoveryClient của Spring Cloud Kubernetes có các cách triển khai và cơ chế đồng bộ riêng; xem [DiscoveryClient cho Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html). DNS, ClusterIP và tập endpoint cũng có vai trò khác nhau như mô tả trong [Kubernetes Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Cần tách **khởi động** khỏi **vận hành sau khởi động**. Một Pod đang phục vụ có thể dùng cấu hình và dữ liệu discovery đã nạp. Một Pod mới có thể chưa nạp được cùng dữ liệu đó và không thể sẵn sàng. Vì vậy, khởi động lại Pod đang hoạt động trong lúc API server lỗi có thể làm mất khả năng phục vụ vốn đang còn.

Configuration Watcher cũng có thể chạy như một thành phần riêng. Watcher mất quyền truy cập API không đồng nghĩa đường HTTP nghiệp vụ trong mọi Pod cùng mất sức khỏe. Tín hiệu của Watcher nên được quan sát tại đúng thành phần và gắn với tác động “không nhận cấu hình mới”.

## 6. Phân biệt endpoint tổng hợp, liveness và readiness

Spring Boot cung cấp các health group dành cho probe:

| Endpoint thông dụng | Mục đích | Tác động khi dùng làm probe |
| --- | --- | --- |
| `/actuator/health` | Tổng hợp các contributor được chọn | Tùy cách bạn gắn endpoint này vào probe |
| `/actuator/health/liveness` | Đánh giá liveness | Liveness thất bại đủ ngưỡng có thể làm container bị khởi động lại |
| `/actuator/health/readiness` | Đánh giá readiness | Instance không sẵn sàng bị loại khỏi tập đích phục vụ thông thường |
| `/actuator/health/platform` | Group tùy chọn do bạn cấu hình | Chỉ phục vụ chẩn đoán nếu không gắn vào probe |

Theo mặc định của Spring Boot, `DOWN` và `OUT_OF_SERVICE` ánh xạ sang HTTP 503, còn `UNKNOWN` không mặc nhiên ánh xạ thành lỗi HTTP. Khi đã tùy biến ánh xạ, phải kiểm tra hành vi thực tế. Spring Boot không tự đưa các kiểm tra phụ thuộc bên ngoài vào liveness và readiness; xem [Actuator Endpoints của Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Điểm dễ gây sự cố là gắn cả liveness và readiness vào `/actuator/health`. Khi một contributor phụ thuộc API server làm health tổng hợp thành `DOWN`, kubelet có thể khởi động lại ứng dụng vẫn còn phục vụ được.

Quy trình phản ứng của probe, các ngưỡng thất bại và cách startup probe trì hoãn probe còn lại được mô tả trong [cấu hình probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

## 7. Cấu hình mẫu: giữ probe đúng phạm vi

Ví dụ này dành cho dịch vụ `orders` đã xác định API server không phải phụ thuộc trực tiếp của từng yêu cầu nghiệp vụ. Kubernetes contributor đã tồn tại và được bật trong môi trường triển khai.

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include:
            - livenessState
        readiness:
          include:
            - readinessState
        platform:
          include:
            - kubernetes
  health:
    kubernetes:
      enabled: true
~~~

Ý nghĩa của lựa chọn này:

- Liveness chỉ dùng `livenessState`.
- Readiness dùng `readinessState`. Nếu có điều kiện nghiệp vụ thiết yếu khác, ứng dụng phải bổ sung hoặc cập nhật trạng thái tương ứng; cấu hình này không tự phát hiện mọi lỗi nghiệp vụ.
- Group `platform` quan sát contributor `kubernetes` riêng.
- `add-additional-paths` cung cấp `/livez` và `/readyz` trên cổng chính của ứng dụng.
- `show-details: never` giữ phản hồi không hiển thị chi tiết. Khi chẩn đoán nội bộ có thể chọn chính sách chi tiết khác với kiểm soát truy cập phù hợp.

Nếu contributor `kubernetes` không được tạo, group `platform` tham chiếu nó có thể làm bước xác thực cấu hình group thất bại. Chỉ dùng group này khi contributor thực sự có mặt. Nếu tắt Kubernetes contributor, đồng thời bỏ hoặc sửa group tham chiếu nó.

Tắt contributor là một lựa chọn khi ứng dụng không cần tín hiệu đó:

~~~yaml
management:
  health:
    kubernetes:
      enabled: false
~~~

Đây là **cấu hình thay thế**, không ghép nguyên xi với group `platform` phía trên. Tắt contributor không sửa lỗi RBAC, không phục hồi mạng và không tắt những chức năng discovery, config hoặc watch mà ứng dụng vẫn đang dùng.

Nếu bổ sung indicator tự viết có tên `kubernetesApiAccess`, group chẩn đoán có thể chọn indicator đó. Không dùng tên này trong `include` trước khi bean tương ứng tồn tại.

## 8. Gắn probe vào cổng phục vụ thực tế

Đây là phần `spec.template.spec` của một Deployment, không phải manifest hoàn chỉnh. Ứng dụng dùng cổng 8080 và đã bật đường dẫn bổ sung ở phần trước.

~~~yaml
serviceAccountName: orders-sa
containers:
  - name: orders
    image: example.invalid/orders:lab
    ports:
      - name: http
        containerPort: 8080
    env:
      - name: POD_NAME
        valueFrom:
          fieldRef:
            fieldPath: metadata.name
    startupProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 24
    livenessProbe:
      httpGet:
        path: /livez
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: http
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 3
      successThreshold: 1
~~~

Thay image minh họa bằng image thực tế. Startup probe có ngân sách thời gian xấp xỉ 120 giây theo các tham số trên; đây là giá trị lab, cần điều chỉnh bằng số đo khởi động của ứng dụng. Startup probe dùng liveness không khẳng định các bước khởi tạo nghiệp vụ đã hoàn tất; readiness vẫn phải chặn lưu lượng cho đến khi ứng dụng sẵn sàng.

Khi Actuator chạy trên cổng quản trị riêng, chỉ kiểm tra cổng đó có thể bỏ sót lỗi ở cổng nghiệp vụ. Đường dẫn bổ sung trên cổng chính giúp kiểm tra gần hơn với khả năng tiếp nhận HTTP của ứng dụng. Nếu có Spring Security tùy biến, bảo đảm kubelet được gọi đúng các đường dẫn probe mà không phải thực hiện đăng nhập.

Ngay cả một HTTP probe thành công cũng không thay thế kiểm tra một giao dịch nghiệp vụ đại diện.

## 9. Khi nào nên cho khả năng truy cập API ảnh hưởng readiness?

Chỉ đưa phụ thuộc API server vào readiness khi có lý do gắn với khả năng phục vụ của instance.

Một quyết định hợp lý cần trả lời:

1. Yêu cầu nghiệp vụ nào bắt buộc dùng Kubernetes API?
2. Khi API lỗi, ứng dụng có fallback hoặc dữ liệu hợp lệ để dùng tiếp không?
3. Có thời hạn tối đa cho dữ liệu cũ không?
4. Ngừng nhận lưu lượng toàn instance có phù hợp nếu chỉ một nhóm chức năng bị ảnh hưởng không?
5. Nếu mọi replica cùng mất kết nối, hệ thống còn cách trả lỗi có kiểm soát hoặc phục vụ chức năng còn lại không?

Hai chính sách minh họa:

| Ứng dụng | Chính sách khi API server tạm thời lỗi |
| --- | --- |
| Dịch vụ đọc danh mục, cấu hình đã nạp và còn hợp lệ | Giữ readiness nếu nghiệp vụ vẫn đạt yêu cầu; cảnh báo mất đồng bộ |
| API cấp phát môi trường, mọi yêu cầu hợp lệ đều phải tạo tài nguyên Kubernetes | Cân nhắc readiness không đạt khi không còn khả năng phục vụ; liveness vẫn độc lập |

Nếu chỉ chức năng cấp phát bị ảnh hưởng trong một ứng dụng có nhiều API, việc từ chối riêng chức năng đó có thể chính xác hơn việc loại toàn Pod khỏi Service. Quyết định phải dựa trên hợp đồng dịch vụ.

Với cấu hình nhạy cảm, dữ liệu cũ không nhất thiết an toàn vô thời hạn. Chẳng hạn, một chính sách quyền truy cập đã hết thời hạn có thể buộc ứng dụng ngừng chấp nhận thao tác liên quan dù JVM vẫn khỏe. Đây là điều kiện nghiệp vụ, không chỉ là “kết nối API có thành công không”.

Không đưa API server vào liveness chỉ vì nó quan trọng: khởi động lại tiến trình không khắc phục một phụ thuộc bên ngoài đang ngừng hoạt động.

## 10. “Không truy cập được API” cần được phân loại

Khả năng truy cập có nhiều lớp. Một phép thử tốt ghi rõ vị trí gọi, danh tính, tài nguyên, động từ, namespace, thời điểm và giới hạn thời gian.

| Hiện tượng | Điều đã biết | Hướng điều tra |
| --- | --- | --- |
| Không phân giải được tên API server | Chưa thực hiện được kết nối bằng tên đó | DNS, cấu hình resolver, tên endpoint |
| TCP timeout hoặc connection refused | Chưa có phản hồi API hợp lệ cho yêu cầu này | Đường mạng, egress, firewall, proxy, endpoint |
| Lỗi chứng thư TLS | Quá trình thiết lập tin cậy TLS thất bại | CA, hostname, chứng thư và thời gian hệ thống |
| HTTP 401 | Yêu cầu bị từ chối ở bước xác thực | Token, audience, thời hạn và cấu hình client |
| HTTP 403 | Máy chủ đã phản hồi từ chối quyền cho yêu cầu | Danh tính thực tế, Role, RoleBinding và phạm vi |
| HTTP 404 | Endpoint hoặc tài nguyên yêu cầu không tồn tại theo phản hồi | Tên tài nguyên, namespace, phiên bản API |
| HTTP 429 | Yêu cầu đang bị giới hạn | Tần suất gọi, đồng thời, retry và tải |
| HTTP 5xx | Máy chủ hoặc thành phần trung gian trả lỗi phía server | Log, độ trễ và sức khỏe control plane |

Một `403` chứng minh có phản hồi HTTP cho yêu cầu đó; nó không chứng minh mạng bị đứt. Đồng thời, không nên mặc định `403` luôn đến từ ServiceAccount mong muốn: hãy xác minh client có gửi token hay đang bị nhận diện là danh tính khác.

Lệnh `kubectl` chạy tốt từ máy quản trị cũng không chứng minh Pod truy cập tốt. Hai nơi có thể dùng tuyến mạng, CA, proxy, token và quyền khác nhau.

## 11. Ví dụ RBAC cho một phép đọc Pod

Giả sử phép chẩn đoán cần đọc đối tượng Pod trong namespace `health-lab`, còn ServiceAccount `orders-sa` đã tồn tại. Quyền cho thao tác minh họa có thể được mô tả bằng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-diagnostic-reader
  namespace: health-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-pod-diagnostic-reader
  namespace: health-lab
subjects:
  - kind: ServiceAccount
    name: orders-sa
    namespace: health-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: pod-diagnostic-reader
~~~

Role này cho phép `get` các Pod trong namespace, không cho phép `list` hay `watch`. Đây là quyền cho **phép thử đọc Pod** trong bài, không phải bộ quyền đầy đủ của mọi tính năng Spring Cloud Kubernetes. Nếu cần giới hạn theo tên, có thể dùng `resourceNames`; tên Pod do Deployment tạo thay đổi qua rollout nên cần tính đến vòng đời của tên đó.

Discovery có thể cần quyền trên Service, Endpoints hoặc EndpointSlice tùy cấu hình. Đọc ConfigMap, đọc Secret và theo dõi thay đổi lại cần các quyền tương ứng. Không cấp quyền Secret chỉ để làm cho một kiểm tra Pod chuyển sang `UP`. Cách biểu diễn resource và verb được quy định trong [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Từ máy quản trị có quyền impersonation, kiểm tra riêng từng thao tác:

~~~bash
kubectl auth can-i get pods \
  --namespace health-lab \
  --as system:serviceaccount:health-lab:orders-sa

kubectl auth can-i list services \
  --namespace health-lab \
  --as system:serviceaccount:health-lab:orders-sa

kubectl auth can-i watch endpointslices.discovery.k8s.io \
  --namespace health-lab \
  --as system:serviceaccount:health-lab:orders-sa
~~~

Đây là kiểm tra phân quyền, không kiểm tra đường mạng từ Pod. Nếu người chạy không được impersonate, lỗi của lệnh không tự chứng minh ServiceAccount thiếu quyền. Hơn nữa, quyền hiệu lực còn có thể đến từ RoleBinding khác; không suy ra toàn bộ quyền chỉ bằng một manifest.

## 12. Kiểm tra một thao tác từ chính container

Phép thử dưới đây dành cho shell bên trong container ứng dụng, có `curl` và shell POSIX. Nó giả định ServiceAccount token được mount ở đường dẫn chuẩn, cùng biến `POD_NAME` lấy từ Downward API như phần Deployment.

Chỉ chạy thủ công trong lab hoặc khi được phép chẩn đoán. Không dùng shell tracing `set -x` vì có thể làm lộ token.

~~~bash
sa_dir=/var/run/secrets/kubernetes.io/serviceaccount
namespace="$(cat "$sa_dir/namespace")"
api_server=https://kubernetes.default.svc

printf 'Authorization: Bearer %s\n' "$(cat "$sa_dir/token")" |
  curl --silent --show-error \
    --connect-timeout 1 \
    --max-time 3 \
    --cacert "$sa_dir/ca.crt" \
    --header @- \
    --output /dev/null \
    --write-out 'HTTP=%{http_code} total=%{time_total}s\n' \
    "$api_server/api/v1/namespaces/$namespace/pods/$POD_NAME"
~~~

Header được truyền qua stdin, không in token ra màn hình. Không thêm `-k` để bỏ xác minh chứng thư rồi coi kết quả đó là bằng chứng client thực tế đã được cấu hình đúng.

Cách đọc:

- `200`: thao tác đọc Pod cụ thể đã thành công từ vị trí và danh tính này tại thời điểm kiểm tra.
- `403`: kiểm tra token thực tế, namespace và quyền `get pods`.
- `404`: kiểm tra `POD_NAME`, namespace và sự tồn tại của Pod.
- Lỗi TLS hoặc timeout: đọc thông báo từ `curl` và mã thoát; `HTTP=000` không phải một mã HTTP do API server trả về.

Lệnh không dùng `--fail` để bạn quan sát được mã HTTP lỗi; vì vậy không dùng riêng mã thoát thành công của `curl` để kết luận API trả `2xx`. Khi cấu hình `automountServiceAccountToken: false`, đường dẫn token có thể không tồn tại; đó là điều kiện triển khai cần xử lý, không phải bằng chứng API server ngừng hoạt động.

Nếu container không có shell hoặc `curl`, dùng công cụ chẩn đoán được phê duyệt. Một Pod chẩn đoán khác không mặc nhiên có cùng danh tính hoặc chính sách mạng với Pod ứng dụng.

## 13. Nếu cần indicator kiểm tra API riêng

Không nên để mỗi HTTP probe đồng bộ gọi API server rồi chờ hết timeout. Với nhiều replica, cách đó vừa làm probe chậm vừa tạo thêm tải lên một phụ thuộc chung.

Một thiết kế có thể áp dụng là:

~~~text
Tác vụ nền có giới hạn đồng thời:
  thực hiện thao tác đọc nhỏ, phù hợp với quyền đã cấp
  đặt connect timeout và tổng thời gian tối đa
  lưu kết quả cuối cùng, lastAttemptAt, lastSuccessAt và loại lỗi
  giãn nhịp thử lại có backoff và jitter khi thất bại

HealthIndicator:
  đọc kết quả đã lưu
  đánh giá kết quả có quá cũ theo chính sách hay không
  trả về nhanh, không mở yêu cầu mạng mới
~~~

Đây là thiết kế đề xuất cho mã tùy biến, không khẳng định contributor có sẵn hoạt động theo thuật toán này.

Có ba điều kiện cần làm rõ:

1. Chưa có kết quả ban đầu được biểu diễn thế nào, và có được phép nhận lưu lượng không?
2. Một kết quả thành công cũ sau bao lâu không còn đủ chứng minh khả năng phục vụ?
3. Mất kết nối và dữ liệu hết hạn có cùng tác động đến readiness hay cần hai chính sách khác nhau?

Nếu dùng trạng thái `UNKNOWN` cho tình huống chưa kiểm tra, nhớ rằng mặc định HTTP của trạng thái này không phải 503. Muốn nó chặn readiness, cần chính sách trạng thái và ánh xạ HTTP rõ ràng, rồi kiểm chứng phản hồi endpoint.

Ví dụ về tải do probe, chỉ tính các lời gọi từ probe: 200 replica, hai probe mỗi 10 giây, mỗi probe gọi API một lần tạo khoảng `200 × 2 / 10 = 40` yêu cầu mỗi giây. Con số còn tăng khi có retry, scraper hoặc người kiểm tra thủ công. Giảm số lời gọi đồng bộ thường hữu ích hơn tăng timeout.

Các số như chu kỳ kiểm tra 15 giây hoặc thời hạn dữ liệu 60 giây chỉ là tham số thiết kế minh họa. Chọn chúng theo nghiệp vụ, tải và thời gian phục hồi đã đo.

## 14. Bài thực hành: chứng minh hai tín hiệu có thể khác nhau

Mục tiêu là quan sát ứng dụng phục vụ được trong khi một thao tác Kubernetes bị từ chối, sau đó quan sát quá trình phục hồi. Chỉ thực hiện thay đổi RBAC hoặc lỗi mạng trong môi trường lab do bạn quản lý.

### Bước 1: Ghi trạng thái ban đầu

Quan sát một yêu cầu nghiệp vụ đại diện, `/livez`, `/readyz` và số lần restart của container. Nếu có group `platform`, ghi thêm kết quả group này. Thực hiện phép đọc Pod từ container để có bằng chứng độc lập.

Có thể xem các endpoint từ máy quản trị bằng port-forward:

~~~bash
kubectl -n health-lab port-forward deployment/orders 18080:8080
~~~

Trong terminal khác:

~~~bash
curl --include http://127.0.0.1:18080/livez
curl --include http://127.0.0.1:18080/readyz
curl --include http://127.0.0.1:18080/actuator/health/platform
~~~

Port-forward phụ thuộc đường quản trị qua control plane. Nó phù hợp với bài thử RBAC của ServiceAccount; khi thử sự cố control plane thật, việc port-forward thất bại không chứng minh cổng nghiệp vụ cũng thất bại. Khi đó cần một đường quan sát độc lập.

### Bước 2: Tạo lỗi RBAC có kiểm soát

Trong lab, làm cho ServiceAccount mất riêng quyền đọc Pod mà phép thử cần. Ghi lại cấu hình trước khi thay đổi để phục hồi. Không thay Role dùng chung với workload khác.

Xác nhận phép đọc trả `403`; nếu vẫn `200`, kiểm tra các binding khác trước khi kết luận. Lặp lại yêu cầu nghiệp vụ, liveness và readiness.

Với kiến trúc dịch vụ `orders` đã nêu, kỳ vọng là:

| Tín hiệu | Kỳ vọng |
| --- | --- |
| Đọc Pod bằng ServiceAccount | `403` nếu không còn nguồn cấp quyền nào khác |
| `/livez` | Vẫn thành công nếu tiến trình không bị lỗi nội bộ |
| `/readyz` | Vẫn thành công nếu ứng dụng tiếp tục nhận lưu lượng và nghiệp vụ không cần quyền đó |
| Yêu cầu nghiệp vụ đại diện | Tiếp tục thành công trong các giả định của bài |
| Kubernetes contributor có sẵn | Ghi nhận thực tế; không giả định luôn đổi trạng thái ngay |
| Số lần restart | Không tăng vì một lỗi phân quyền riêng lẻ |

Nếu Kubernetes contributor vẫn `UP`, điều đó không phủ nhận kết quả `403` của phép đọc trực tiếp. Hai phép đo có thể khác phạm vi và thời điểm lấy dữ liệu. Đây chính là lý do không dùng tên “health Kubernetes” như bằng chứng tổng quát về mọi quyền truy cập.

### Bước 3: Khôi phục và quan sát

Khôi phục quyền ban đầu, xác nhận phép đọc lại thành công và kiểm tra nghiệp vụ. Với discovery hoặc watcher đang dùng thật, quan sát riêng việc đồng bộ lại; một lần đọc Pod thành công không chứng minh watch đã phục hồi.

Sau khi đã hiểu lỗi RBAC, có thể thực hiện bài thử chặn kết nối API trong lab cô lập. Đó là loại lỗi khác. Đích API, CNI, Service DNAT và cách thực thi NetworkPolicy ảnh hưởng kết quả; không sao chép một quy tắc egress bất kỳ rồi giả định đã cô lập đúng API server.

Bản ghi thực hành nên chứa thời điểm, loại lỗi, HTTP của từng probe, kết quả nghiệp vụ và chênh lệch restart count. Không ghi token hoặc nội dung Secret.

## 15. Những kết luận cần tránh khi vận hành

| Kết luận vội vàng | Cách diễn giải chính xác hơn |
| --- | --- |
| “Health tổng hợp DOWN, phải restart ngay” | Xác định contributor lỗi và xem restart có sửa được nguyên nhân không |
| “API server không truy cập được, mọi Pod đều chết” | Kiểm tra riêng control plane, mạng nghiệp vụ và tiến trình đang chạy |
| “API server UP, ứng dụng chắc chắn sẵn sàng” | Kiểm tra khởi tạo, cấu hình và các điều kiện nghiệp vụ |
| “Đọc Pod được thì RBAC đầy đủ” | Kiểm tra từng resource, verb và namespace mà tính năng cần |
| “Watch mất kết nối nhưng health UP nên dữ liệu còn mới” | Quan sát lần đồng bộ thành công và giới hạn chấp nhận dữ liệu cũ |
| “Tắt health contributor là sửa xong lỗi API” | Việc đó chỉ thay đổi tín hiệu quan sát; nguyên nhân truy cập vẫn còn |
| “Tăng timeout sẽ làm probe đáng tin cậy hơn” | Timeout dài có thể giữ tài nguyên lâu và làm phản hồi probe không kịp |

Một chính sách sức khỏe hữu ích phải nối **tín hiệu** với **hành động có khả năng phục hồi đúng**. Liveness dành cho tình trạng mà khởi động lại instance có thể giúp; readiness phản ánh khả năng nhận lưu lượng; chẩn đoán API phản ánh thao tác và độ mới của bằng chứng. Với Spring Cloud Kubernetes, hãy chọn những tính năng thực sự cần, cấp quyền đúng phạm vi và chỉ để một phụ thuộc điều khiển probe khi nghiệp vụ đòi hỏi điều đó.
