# Nhận diện môi trường Kubernetes và kích hoạt profile phù hợp

Một ứng dụng Spring có thể chạy trên máy phát triển, trong test container, trên Kubernetes hoặc trong một môi trường staging khác. Mỗi môi trường có nguồn cấu hình, endpoint, cách xác thực và cách báo sức khỏe riêng. Nếu ứng dụng chọn profile bằng một điều kiện mơ hồ, nó có thể cố gọi Kubernetes API khi chạy local, dùng cấu hình local trong cluster hoặc vô tình bật quyền truy cập không cần thiết.

Spring Boot và Spring Cloud Kubernetes hỗ trợ nhiều cách để phân biệt môi trường. Cách an toàn thường là kích hoạt profile một cách rõ ràng từ deployment, sau đó dùng tín hiệu môi trường để kiểm tra hoặc làm cơ chế dự phòng có kiểm soát. Tự động phát hiện có thể hữu ích, nhưng không nên được xem là bằng chứng duy nhất cho mọi quyết định bảo mật và kết nối.

Bài học thuộc chương **Thiết lập dự án** của module **SPRING_CLOUD_KUBERNETES**. Phạm vi gồm profile Spring, biến môi trường Kubernetes, Downward API, cấu hình ConfigMap/Secret, discovery, RBAC và cách kiểm tra ứng dụng đang chạy đúng môi trường.

## 1. Profile Spring là một lựa chọn cấu hình

Profile cho phép nhóm bean và property theo môi trường hoặc mục đích chạy:

| Profile | Mục đích | Nguồn thường dùng |
| --- | --- | --- |
| local | Chạy trên máy phát triển | File local, service giả lập hoặc dependency cục bộ |
| test | Test unit/integration | Test property, container test hoặc mock |
| kubernetes | Chạy trong cluster | Service DNS, ConfigMap/Secret, ServiceAccount |
| staging | Môi trường tiền production | Cấu hình staging và endpoint staging |
| production | Môi trường thật | Secret management, policy mạng, quan sát production |

Profile không tự tạo namespace, Service, ConfigMap hoặc quyền RBAC. Nó chỉ ảnh hưởng cách Spring chọn bean và property. Kubernetes vẫn cần manifest đúng, còn ứng dụng phải kiểm tra dữ liệu sau khi profile được kích hoạt.

Một profile tốt mô tả khác biệt thực sự của môi trường. Không nên tạo profile riêng cho từng Pod hoặc từng replica nếu các Pod dùng cùng một cấu hình logic. Replica identity nên lấy từ metadata hoặc runtime khi cần, không nên nhân số profile theo số Pod.

## 2. Ba chiến lược kích hoạt profile

Có ba chiến lược thường gặp:

| Chiến lược | Cách làm | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| Explicit | Deployment đặt SPRING_PROFILES_ACTIVE | Dễ review và tái tạo | Manifest phải được quản lý đúng |
| External config | ConfigMap hoặc môi trường cấp giá trị profile | Tách image khỏi môi trường | Cấu hình sai có thể chọn nhầm profile |
| Auto-detection | Ứng dụng suy ra đang ở Kubernetes | Giảm cấu hình lặp | Tín hiệu có thể không đầy đủ hoặc bị giả |
| Kết hợp có kiểm soát | Explicit là nguồn chính, detection dùng kiểm tra | Rõ ràng và có bảo vệ | Cần quy định ưu tiên và lỗi |

Trong production, explicit activation thường dễ vận hành nhất:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: kubernetes
~~~

Image không cần biết nó đang chạy trong namespace nào để chọn profile chính. Deployment là nơi đã biết workload đang được triển khai vào Kubernetes, nên nó có thể khai báo profile rõ ràng.

Với staging, có thể dùng một giá trị khác như kubernetes,staging nếu ứng dụng cần cả cấu hình chung của Kubernetes và khác biệt staging. Cần quy định thứ tự và property nào có ưu tiên cao hơn khi nhiều profile cùng active.

## 3. Vì sao không nên chỉ dựa vào tên profile?

Một tiến trình local cũng có thể được chạy với SPRING_PROFILES_ACTIVE=kubernetes. Khi đó, tên profile không chứng minh tiến trình đang ở trong cluster. Ngược lại, một Pod có thể không đặt profile dù vẫn có các tín hiệu Kubernetes.

Profile trả lời câu hỏi “ứng dụng nên dùng nhóm cấu hình nào”; nó không luôn trả lời câu hỏi “tiến trình đang chạy ở đâu”. Hai câu hỏi nên được kiểm tra riêng:

- Chọn profile: do deployment hoặc runtime configuration quyết định.
- Kiểm tra môi trường: do tín hiệu runtime, kết nối API, DNS và policy xác nhận.
- Kiểm tra năng lực: do ứng dụng xác định nó có thể dùng discovery/config/refresh nào.

Nếu profile kubernetes yêu cầu đọc ConfigMap qua API, ứng dụng nên fail fast với lỗi rõ ràng khi môi trường được khai báo là Kubernetes nhưng resource hoặc RBAC bị thiếu. Không nên âm thầm chuyển sang cấu hình local và tiếp tục chạy với dữ liệu sai.

## 4. Tín hiệu Kubernetes thường có trong Pod

Kubernetes có thể cung cấp một số tín hiệu trong container:

- Biến môi trường KUBERNETES_SERVICE_HOST và KUBERNETES_SERVICE_PORT thường được service environment tạo cho API server.
- ServiceAccount token và CA certificate có thể được mount nếu Pod cho phép automount.
- File namespace hiện tại thường có thể được cung cấp qua Downward API hoặc service account volume tùy manifest.
- Metadata Pod, namespace, tên và IP có thể được đưa vào biến môi trường bằng fieldRef.
- DNS trong cluster có thể phân giải các Service nội bộ.
- API server có thể trả lời nếu network policy, token và RBAC cho phép.

Không tín hiệu đơn lẻ nào chứng minh mọi tính năng Kubernetes đều sẵn sàng. Ví dụ, có KUBERNETES_SERVICE_HOST chỉ cho biết container nhận được một biến môi trường; nó không chứng minh token hợp lệ hoặc ServiceAccount có quyền đọc ConfigMap.

Có thể đưa namespace và Pod name vào container bằng Downward API:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: POD_IP
    valueFrom:
      fieldRef:
        fieldPath: status.podIP
  - name: POD_NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
~~~

Các biến này hữu ích cho log, metric, tên instance hoặc giới hạn phạm vi cấu hình. Không nên dùng Pod IP làm địa chỉ gọi lâu dài; Service DNS vẫn là điểm truy cập ổn định cho traffic nội bộ.

## 5. Tín hiệu ServiceAccount và giới hạn của nó

Pod có thể được gắn ServiceAccount:

~~~yaml
spec:
  serviceAccountName: order-api
  automountServiceAccountToken: true
~~~

Token được mount giúp client in-cluster xác thực với Kubernetes API theo cơ chế của cluster. Nhưng token tồn tại không đồng nghĩa ứng dụng có quyền thực hiện mọi thao tác. RBAC vẫn quyết định các verb và resource được phép.

Ngược lại, Pod có thể tắt automountServiceAccountToken:

~~~yaml
spec:
  automountServiceAccountToken: false
~~~

Đây là lựa chọn phù hợp khi ứng dụng chỉ gọi Service qua DNS hoặc nhận cấu hình bằng biến môi trường/volume mà không cần tự gọi API. Nếu tắt token rồi bật Spring Cloud Kubernetes integration đọc ConfigMap trực tiếp, ứng dụng có thể không khởi động hoặc không đọc được dữ liệu.

Không nên dùng sự tồn tại của file token làm điều kiện duy nhất để bật mọi tính năng Kubernetes. Một image dùng chung có thể chạy trong Pod với token bị tắt, token được cung cấp qua cơ chế khác hoặc filesystem có cấu trúc khác. Cần tách việc nhận diện môi trường khỏi việc quyết định quyền và tính năng.

## 6. Explicit profile và ConfigMap

Có thể đưa profile qua ConfigMap, nhưng cần tránh vòng phụ thuộc. Nếu ứng dụng cần profile để biết cách đọc ConfigMap, mà profile lại chỉ được đọc từ chính ConfigMap đó, startup có thể trở nên khó hiểu.

Cách đơn giản là đặt profile trong Deployment hoặc Helm/Kustomize overlay, còn ConfigMap cung cấp property của profile đã chọn:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-kubernetes-settings
  namespace: shop
data:
  ORDER_CATALOG_BASE_URL: http://catalog-api
  ORDER_CATALOG_TIMEOUT: 2s
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  template:
    spec:
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: kubernetes
            - name: ORDER_CATALOG_BASE_URL
              valueFrom:
                configMapKeyRef:
                  name: order-kubernetes-settings
                  key: ORDER_CATALOG_BASE_URL
            - name: ORDER_CATALOG_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: order-kubernetes-settings
                  key: ORDER_CATALOG_TIMEOUT
~~~

Trong mẫu này, profile được quyết định bởi Deployment; các giá trị nghiệp vụ được lấy từ ConfigMap. Thay đổi ConfigMap không tự đổi biến môi trường của container đang chạy. Muốn cập nhật property qua env, cần tạo Pod mới bằng rollout hoặc cách triển khai tương đương.

Nếu dùng volume hoặc Spring Cloud Kubernetes để đọc ConfigMap qua API, quy trình cập nhật có thể khác, nhưng vẫn cần chứng minh bean và client đã dùng giá trị mới.

## 7. Spring Boot profile file và thứ tự nguồn cấu hình

Một dự án thường có file mặc định và file theo profile:

~~~text
src/main/resources/
  application.yaml
  application-local.yaml
  application-kubernetes.yaml
~~~

application.yaml nên chứa cấu hình chung an toàn. application-local.yaml có thể trỏ tới dịch vụ local; application-kubernetes.yaml có thể dùng Service DNS, endpoint Actuator phù hợp và property cho Kubernetes integration.

Không nên đặt Secret thật trong application-kubernetes.yaml. File này có thể chứa tên key hoặc placeholder, còn Secret đi qua environment, volume hoặc nguồn secret management.

Spring Boot hợp nhất property từ nhiều nguồn theo thứ tự ưu tiên của phiên bản và cách khởi động. Các nguồn thường gặp gồm command-line arguments, system properties, environment variables, config files và external config. Vì vậy:

- Hãy ghi rõ nguồn nào là nguồn chính cho từng property.
- Tránh khai báo cùng một property ở nhiều nơi với giá trị khác nhau.
- Không dùng profile để che một giá trị sai trong environment.
- Khi debug, in tên nguồn hoặc giá trị đã được che, không in Secret.
- Kiểm tra effective configuration bằng cách an toàn thay vì dump toàn bộ Environment.

Nếu dùng SPRING_PROFILES_ACTIVE từ Deployment, hãy xem nó là một phần của contract triển khai. Thay đổi tên profile phải được review cùng các file cấu hình và auto-configuration liên quan.

## 8. Auto-detection của Spring Boot

Một số phiên bản Spring Boot hỗ trợ điều kiện theo cloud platform, trong đó có Kubernetes. Một file cấu hình profile có thể dùng điều kiện kích hoạt theo cloud platform nếu phiên bản đang dùng hỗ trợ:

~~~yaml
spring:
  config:
    activate:
      on-cloud-platform: kubernetes
~~~

Cơ chế này có thể hữu ích khi muốn một tài liệu cấu hình chỉ được kích hoạt khi Spring nhận diện cloud platform tương ứng. Tuy nhiên, thuộc tính, giá trị được hỗ trợ và hành vi nhận diện phụ thuộc phiên bản Spring Boot. Hãy xác nhận với tài liệu của dòng Boot đã chọn trước khi dùng trong production.

Auto-detection không nên được dùng để che mất quyết định triển khai. Nếu ứng dụng có thể chạy trên nhiều nền tảng, hãy xác định:

- Nếu detection không nhận ra Kubernetes, ứng dụng dùng profile nào?
- Nếu biến SPRING_PROFILES_ACTIVE mâu thuẫn với detection, ưu tiên nào?
- Nếu Kubernetes API không truy cập được, ứng dụng fail hay fallback?
- Nếu chạy test trong container có một số biến Kubernetes nhưng không có API, kết quả có sai không?
- Có log an toàn cho biết profile và cloud platform đã chọn không?

Một chiến lược thận trọng là dùng explicit profile làm nguồn chính, còn cloud detection chỉ cung cấp conditional bean hoặc kiểm tra nhất quán. Ví dụ, profile kubernetes được khai báo trong Deployment; trong application-kubernetes.yaml, ứng dụng kiểm tra rằng các property bắt buộc có mặt và không tự fallback sang local.

## 9. Nhận diện môi trường trong mã ứng dụng

Đôi khi mã cần biết cloud platform để chọn một implementation. Có thể dùng abstraction điều kiện của Spring Boot hoặc một bean cung cấp thông tin môi trường, tùy phiên bản. Không nên tự viết điều kiện rải rác kiểu “nếu tồn tại một biến thì gọi Kubernetes API” ở nhiều service.

Một cách tổ chức tốt là gom việc nhận diện vào một configuration boundary:

~~~text
Runtime signals
  |
  v
EnvironmentClassifier
  |
  +--> profile/config validation
  +--> Kubernetes client configuration
  +--> local fallback cho test được phép
  +--> metric và log an toàn
~~~

Boundary này nên trả lời những câu hỏi rõ:

- Có khai báo profile Kubernetes không?
- Có tín hiệu cluster tối thiểu không?
- Tính năng đang yêu cầu là DNS, API discovery hay config API?
- Có credential và quyền tương ứng không?
- Fallback có được phép trong môi trường hiện tại không?

Không nên dùng fallback local trong production chỉ để ứng dụng “vẫn chạy”. Nếu ConfigMap bắt buộc không đọc được, chạy với giá trị mặc định có thể tạo đơn hàng sai, gọi nhầm dịch vụ hoặc bỏ qua chính sách bảo mật.

Nếu mã cần đọc namespace để giới hạn truy vấn, hãy lấy namespace từ cấu hình hoặc Downward API theo một quy ước nhất quán. Không suy ra namespace bằng cách cắt hostname hoặc đoán từ tên Service.

## 10. Kích hoạt Spring Cloud Kubernetes integration

Khi profile kubernetes được chọn, ứng dụng có thể bật các integration phù hợp. Ví dụ property minh họa:

~~~yaml
spring:
  application:
    name: order-api
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: true
        namespace: shop
~~~

Tên property và khả năng bật/tắt phụ thuộc module và release train. Hãy dùng property theo tài liệu của phiên bản thực tế, không sao chép nguyên xi giữa các phiên bản.

Nếu ứng dụng chỉ gọi catalog-api qua DNS, discovery integration có thể không cần bật. Nếu ứng dụng đọc ConfigMap qua API, config integration cần ServiceAccount và RBAC. Nếu dùng watcher hoặc refresh, cần thêm cơ chế nhận sự kiện và kiểm tra bean có thể cập nhật.

Có thể tách profile:

~~~yaml
# application-local.yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: false

# application-kubernetes.yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: true
        namespace: shop
~~~

Đây chỉ là cấu trúc minh họa. Property chính xác cần khớp dòng Spring Cloud Kubernetes đã chọn. Quan trọng là profile local không cố gọi API server và profile Kubernetes không được bật các integration mà ứng dụng không dùng.

## 11. Cấu hình import và optional fallback

Các dòng Spring Cloud Kubernetes hiện đại có thể hỗ trợ đưa ConfigMap hoặc Secret vào Config Data qua spring.config.import. Ví dụ khái niệm:

~~~yaml
spring:
  config:
    import: optional:kubernetes:
~~~

Cú pháp và cách chỉ định resource phụ thuộc phiên bản. Từ khóa optional có ý nghĩa lớn: nếu nguồn Kubernetes không có, ứng dụng có thể tiếp tục dùng nguồn khác. Điều này hữu ích cho local nhưng nguy hiểm trong production nếu ConfigMap bắt buộc mà ứng dụng lại âm thầm dùng default.

Hãy quy định optional theo môi trường:

- Local: optional có thể giúp chạy nhanh với file local.
- Test: dùng test property hoặc resource giả lập rõ ràng.
- Staging/production: resource bắt buộc nên làm startup fail khi thiếu hoặc không truy cập được, trừ khi có default được phê duyệt.
- Credential: không fallback sang giá trị rỗng hoặc secret mặc định.

Một lỗi phổ biến là để optional ở mọi môi trường rồi chỉ phát hiện ConfigMap không được nạp khi yêu cầu nghiệp vụ đã chạy. Nếu dữ liệu bắt buộc, hãy validate khi startup và phát ra lỗi không tiết lộ Secret.

## 12. Downward API, profile và metadata Pod

Downward API cung cấp metadata của Pod mà không cần ứng dụng gọi Kubernetes API:

~~~yaml
env:
  - name: APP_POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: APP_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: APP_POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: APP_NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName
~~~

Có thể dùng APP_POD_NAME cho log hoặc instance id, nhưng không dùng nó để quyết định profile kubernetes nếu deployment đã biết môi trường. Metadata mô tả Pod; nó không đảm bảo Kubernetes API, discovery hoặc ConfigMap integration được phép.

Có thể đưa label hoặc annotation cụ thể vào environment theo fieldRef ở những trường hợp được Kubernetes hỗ trợ. Hãy dùng metadata không nhạy cảm. Không đưa token hoặc Secret vào label/annotation vì chúng có thể xuất hiện trong API, event, log hoặc giao diện quản trị.

## 13. Fallback local và môi trường test

Một image dùng chung thường cần chạy local và trên Kubernetes. Fallback nên được thiết kế rõ theo cách khởi động:

| Môi trường | Profile | Nguồn dịch vụ | Nguồn cấu hình | Quyền Kubernetes API |
| --- | --- | --- | --- | --- |
| Local | local | localhost hoặc container network | file/env local | Không cần |
| Test | test | mock, test container hoặc service test | test property | Chỉ khi test thật sự kiểm tra API |
| Kubernetes | kubernetes | Service DNS hoặc discovery integration | ConfigMap/Secret | Theo integration |
| Production-like | kubernetes,staging | DNS và policy staging | Secret/config staging | Theo workload |

Test không nên vô tình đọc token của máy phát triển hoặc gọi cluster thật chỉ vì một biến môi trường tồn tại. Có thể đặt profile test rõ ràng và tắt integration Kubernetes trong test unit. Test integration với Kubernetes phải là nhóm riêng, có resource và quyền được kiểm soát.

Fallback local không nên được kích hoạt khi SPRING_PROFILES_ACTIVE=kubernetes mà Kubernetes config bị lỗi. Trong trường hợp đó, fail fast giúp phát hiện manifest, RBAC hoặc network policy sai trước khi nhận traffic.

## 14. Readiness và profile đã chọn

Profile ảnh hưởng tới endpoint, dependency và cách ứng dụng khởi tạo. Readiness probe chỉ nên thành công khi ứng dụng đã sẵn sàng theo contract của profile đang chạy.

Ví dụ Pod có profile kubernetes và endpoint readiness:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: kubernetes
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  failureThreshold: 30
~~~

Nếu profile kubernetes yêu cầu ConfigMap bắt buộc, readiness không nên báo thành công khi ứng dụng chưa có cấu hình tối thiểu. Nhưng cũng không nên đưa mọi phụ thuộc bên ngoài vào liveness, vì Kubernetes có thể restart toàn bộ Pod khi một API server hoặc database tạm thời gián đoạn.

Nếu profile local vô tình chạy trong cluster, endpoint readiness có thể báo healthy dù nó đang gọi localhost thay vì Service DNS. Vì vậy, profile validation và test deployment quan trọng ngang với probe.

## 15. RBAC theo profile

Kích hoạt profile kubernetes có thể làm ứng dụng cần quyền mà profile local không cần. Nếu discovery hoặc config integration đọc API trực tiếp, hãy map dependency tới RBAC:

| Tính năng trong profile | Thành phần gọi API | Quyền cần xem xét |
| --- | --- | --- |
| Chỉ gọi Service bằng DNS | HTTP client và DNS | Thường không cần đọc API |
| Discovery trực tiếp | Discovery client trong JVM | Service, EndpointSlice hoặc resource theo implementation |
| ConfigMap qua API | Config client trong JVM | get/list/watch ConfigMap tùy cách đọc |
| Secret qua API | Config client trong JVM | Quyền Secret tối thiểu, tách khỏi ConfigMap nếu có thể |
| Watcher riêng | Watcher workload | watch/list resource và quyền định vị ứng dụng theo cơ chế |
| Downward API | Kubelet cung cấp metadata | Không cần đọc API từ ứng dụng |

Nếu cùng image chạy local và Kubernetes, không nên cấp RBAC cho local; RBAC gắn với workload trong cluster. Nếu profile kubernetes không được bật nhưng ServiceAccount vẫn có quyền rộng, đó vẫn là rủi ro ở cấp triển khai.

Profile cũng không phải ranh giới bảo mật. Người có thể thay SPRING_PROFILES_ACTIVE trong một manifest có thể bật code path khác nếu deployment policy không bảo vệ. Hãy kết hợp image, manifest review, admission policy, RBAC và network policy.

## 16. Quan sát profile và môi trường mà không lộ bí mật

Khi khởi động, log nên cho biết những thông tin giúp chẩn đoán:

- Tên ứng dụng.
- Profile đang active.
- Cloud platform được nhận diện, nếu có.
- Namespace logic đã chọn.
- Nguồn cấu hình chính, không in giá trị Secret.
- Tính năng discovery/config có bật hay không.
- Pod name và revision nếu cần.

Không nên log:

- Toàn bộ environment.
- Token hoặc password.
- Nội dung Secret.
- Authorization header.
- Giá trị property nhạy cảm trong một object cấu hình.

Có thể dùng metric hoặc health detail đã che giá trị để biết config resource đã được nạp. Log “profile kubernetes active” không chứng minh ConfigMap đã đọc thành công; log “config source connected” cũng cần tránh chứa credential.

## 17. Chẩn đoán chọn sai profile

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Local cố gọi Kubernetes API | Profile kubernetes bị active hoặc auto-detection quá rộng | Environment, command line, config import |
| Pod dùng URL localhost | Profile local được chọn trong cluster | SPRING_PROFILES_ACTIVE, file profile, env precedence |
| App khởi động nhưng thiếu property | Kubernetes source optional hoặc ConfigMap sai key | Nguồn import, namespace, key và validation |
| App nhận 403 | Profile bật integration nhưng RBAC thiếu | ServiceAccount, Role, RoleBinding, resource/verb |
| Readiness fail liên tục | Profile yêu cầu dependency chưa sẵn sàng | Actuator, ConfigMap/Secret, DNS, API server |
| Test gọi cluster thật | Test kế thừa environment hoặc token ngoài ý muốn | Profile test, environment cleanup, test configuration |
| Discovery rỗng | Sai namespace, selector, RBAC hoặc integration | Service, EndpointSlice, profile property |
| Cấu hình cũ vẫn được dùng | Env không tự cập nhật hoặc bean chưa refresh | Cách inject, rollout, reload và thời điểm đọc |

Hãy bắt đầu bằng việc in danh sách profile đã active và nguồn cấu hình ở mức an toàn. Sau đó kiểm tra đường đi tương ứng. Đừng sửa RBAC khi profile local đang gọi localhost, và đừng thêm ConfigMap khi ứng dụng thực ra đang đọc property từ environment có ưu tiên cao hơn.

## 18. Quy trình thiết lập profile

Một quy trình có thể dùng cho workload Spring Cloud Kubernetes:

1. Liệt kê khác biệt thật giữa local, test và Kubernetes.
2. Chọn profile rõ ràng ở deployment layer.
3. Đặt property chung trong file mặc định và property môi trường trong file/profile tương ứng.
4. Chọn cách nhận ConfigMap/Secret: env, volume hoặc API.
5. Bật đúng Spring Cloud Kubernetes integration cần thiết.
6. Gắn ServiceAccount và RBAC theo thành phần thực sự gọi API.
7. Cấu hình Downward API cho metadata cần log hoặc định danh.
8. Thiết kế fallback local/test riêng, không fallback âm thầm ở production.
9. Cấu hình startup, readiness và liveness theo hành vi profile.
10. Kiểm tra log an toàn, dependency graph và config source.
11. Triển khai canary hoặc môi trường test trước production.
12. Xác nhận từng replica đã dùng profile và cấu hình mong muốn.

Việc profile được chọn đúng chỉ là bước đầu. Cần kiểm chứng cả profile, property, kết nối, quyền, readiness và hành vi nghiệp vụ.

## 19. Checklist thiết kế

Trước khi triển khai, hãy kiểm tra:

- Profile được đặt rõ trong Deployment hoặc lớp cấu hình triển khai.
- Local/test không vô tình dùng token hoặc Kubernetes API thật.
- Profile kubernetes không âm thầm fallback sang cấu hình local khi resource bắt buộc lỗi.
- Tên và namespace của ConfigMap/Secret đã xác định.
- Cách truyền dữ liệu là env, volume hay API và đã ghi rõ semantics cập nhật.
- Auto-detection chỉ dùng khi hành vi của phiên bản Spring Boot đã được xác nhận.
- Tín hiệu Kubernetes không bị dùng như bằng chứng bảo mật duy nhất.
- Downward API chỉ cung cấp metadata cần thiết và không chứa bí mật.
- ServiceAccount token được tắt nếu ứng dụng không cần gọi API.
- RBAC thuộc đúng workload và chỉ có resource/verb cần thiết.
- Discovery, config và LoadBalancer chỉ bật khi ứng dụng thực sự dùng.
- Readiness phản ánh trạng thái sẵn sàng của profile đang chạy.
- Liveness không biến lỗi phụ thuộc tạm thời thành restart storm.
- Log chỉ nêu profile và nguồn cấu hình ở mức an toàn.
- Test local, test unit và test Kubernetes được tách rõ.
- Có kiểm tra sau rollout để xác nhận mọi replica đã dùng profile mới.

## 20. Tự kiểm tra

1. Vì sao SPRING_PROFILES_ACTIVE=kubernetes không tự chứng minh tiến trình đang ở trong cluster?
2. Những tín hiệu nào có thể gợi ý Pod đang chạy trên Kubernetes, và giới hạn của từng tín hiệu là gì?
3. Khi nào nên đặt profile trong Deployment thay vì để ứng dụng tự đoán?
4. Vì sao Pod có ServiceAccount token nhưng vẫn nhận lỗi 403?
5. Tại sao ConfigMap optional có thể nguy hiểm trong production?
6. Nếu profile Kubernetes bật ConfigMap API integration, những quyền nào cần xem xét?
7. Downward API cung cấp metadata gì và vì sao nó không thay thế discovery?
8. Khi nào fallback local là hợp lý, và khi nào nó che giấu lỗi triển khai?
9. Readiness nên phản ánh điều gì nếu profile kubernetes yêu cầu cấu hình bắt buộc?
10. Bằng chứng nào cho thấy ứng dụng vừa chọn đúng profile vừa dùng đúng nguồn cấu hình?

Nhận diện môi trường và kích hoạt profile nên được thiết kế như một contract giữa image, manifest và ứng dụng. Hãy dùng explicit profile để làm rõ ý định triển khai, dùng auto-detection có kiểm soát để hỗ trợ chứ không thay thế quyết định đó, và kiểm tra riêng các lớp cấu hình, RBAC, DNS, discovery cùng sức khỏe Pod. Khi profile kubernetes chỉ bật những integration thật sự cần, ứng dụng Spring Cloud Kubernetes dễ chạy local, dễ chẩn đoán và an toàn hơn trong cluster.

