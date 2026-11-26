# Giới hạn tự động gắn ServiceAccount token khi không cần

## 1. Bối cảnh: chạy trong Kubernetes chưa có nghĩa là cần gọi Kubernetes API

Một ứng dụng Spring Boot có thể nhận HTTP, gọi cơ sở dữ liệu, đọc cấu hình từ volume và gọi một Service qua DNS mà không cần tự xác thực với Kubernetes API. Nếu ứng dụng vẫn được gắn ServiceAccount token, tiến trình có thêm một thông tin xác thực dù chức năng nghiệp vụ không sử dụng nó.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Bảo mật tích hợp**. Mục tiêu là quyết định thành phần nào thật sự cần token khi dùng DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer, Configuration Watcher và kiểm tra sức khỏe Pod.

Sau bài học, bạn có thể:

- Phân biệt danh tính ServiceAccount, token, quyền RBAC và khả năng kết nối API.
- Tắt tự động gắn token ở đúng vị trí trong ServiceAccount và Pod template.
- Giữ ứng dụng hoạt động bằng DNS và cấu hình đã được mount khi không cần API.
- Cấp token ngắn hạn có chủ đích cho trường hợp ngoại lệ.
- Kiểm chứng Pod thực tế, quyền truy cập và các luồng chức năng sau thay đổi.

Nguyên tắc triển khai là: **chỉ đưa thông tin xác thực vào tiến trình có nhu cầu sử dụng rõ ràng**. Việc này bổ sung cho phân quyền tối thiểu bằng RBAC.

## 2. ServiceAccount, token, RBAC và mạng là bốn vấn đề khác nhau

Xét một Pod sử dụng ServiceAccount catalog-app:

~~~text
Pod
  |
  +-- serviceAccountName: catalog-app
  |      Danh tính được gán cho Pod
  |
  +-- token được mount, nếu có
  |      Thông tin xác thực mà tiến trình có thể sử dụng
  |
  +-- RoleBinding / ClusterRoleBinding
  |      Những quyền được cấp cho danh tính và các nhóm liên quan
  |
  +-- đường mạng tới Kubernetes API
         Khả năng kết nối tới máy chủ API
~~~

Bốn lớp này cần được kiểm tra độc lập:

| Thành phần | Trả lời câu hỏi nào? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| serviceAccountName | Pod gắn với ServiceAccount nào? | Không chứng minh token có trong filesystem |
| Token | Client có thể trình thông tin xác thực nào? | Không tự cấp quyền đọc tài nguyên |
| RBAC | Danh tính được phép thực hiện hành động nào? | Không chứng minh client có token hoặc kết nối được |
| Mạng và TLS | Client có thể liên lạc và xác minh máy chủ không? | Không thay thế xác thực hoặc phân quyền |

Đặt automountServiceAccountToken thành false không xóa ServiceAccount, không sửa RoleBinding và không thu hồi mọi thông tin xác thực khác. Một client vẫn có thể được cấu hình bằng kubeconfig hoặc token do cơ chế khác cung cấp.

Điều giảm được ở đây là việc Kubernetes tự đưa bộ thông tin xác thực mặc định vào container khi không cần. Nếu mã trong container bị chiếm quyền hoặc vô tình đọc được file, việc không có token sẵn sẽ loại bỏ một nguồn thông tin xác thực có thể bị sử dụng ngoài ý muốn.

## 3. Kubernetes tự gắn những gì?

Ở Kubernetes hiện đại, cơ chế mặc định sử dụng token có thời hạn qua projected volume. Kubelet lấy và làm mới token; không nên hiểu rằng mỗi ServiceAccount luôn đi kèm một Secret token tồn tại lâu dài. [Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Bộ volume mặc định thường có:

~~~text
/var/run/secrets/kubernetes.io/serviceaccount/
    token
    ca.crt
    namespace
~~~

Token dùng để xác thực; ca.crt giúp xác minh Kubernetes API; namespace cho biết namespace của Pod. Ba nguồn dữ liệu này được ghép trong volume tự động. [Cấu trúc volume ServiceAccount](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/).

Khi tắt automount, đừng mặc định rằng ca.crt và namespace tại đường dẫn trên vẫn còn. Nếu ứng dụng chỉ cần biết namespace, có thể cung cấp thông tin đó qua Downward API mà không cấp token.

Một vài điểm cần nhớ:

- Tên volume tự động thường bắt đầu bằng kube-api-access-, nhưng không nên chỉ kiểm tra tiền tố này.
- Một projected volume được khai báo tường minh có thể chứa token ở đường dẫn khác.
- Admission webhook hoặc cơ chế workload identity có thể bổ sung volume thông tin xác thực riêng.
- Một Pod nhiều container có thể có nhu cầu token khác nhau giữa các container.

Do đó, “không thấy file ở đường dẫn quen thuộc” chỉ là một phần bằng chứng; cần xem cả PodSpec sau admission.

## 4. Khi nào ứng dụng Spring cần token?

Trước khi thay đổi manifest, lập danh sách các thành phần thực sự gọi Kubernetes API:

| Nhu cầu | Tiến trình ứng dụng có cần token Kubernetes không? | Điều phải kiểm tra |
| --- | --- | --- |
| Nhận HTTP, gọi database, xử lý nghiệp vụ | Không do các tác vụ này tự thân | Thư viện hoặc mã tùy biến có gọi API không? |
| Gọi Service bằng DNS và cổng Service | Không do việc phân giải DNS/gọi Service tự thân | HTTP client có đang dùng đường discovery khác không? |
| DiscoveryClient dùng Fabric8 hoặc Kubernetes Java Client để đọc API | Thường cần thông tin xác thực phù hợp | Tài nguyên, namespace và các động từ cần dùng |
| DiscoveryClient gọi DiscoveryServer qua HTTP | Không nhất thiết cần token Kubernetes trong ứng dụng | Server discovery gọi API; phía HTTP có yêu cầu xác thực riêng |
| Spring Cloud LoadBalancer lấy instance từ Kubernetes API | Phụ thuộc đường lấy danh sách instance | Không suy ra từ tên LoadBalancer hoặc một chế độ cấu hình |
| Đọc ConfigMap/Secret đã được kubelet mount thành file | Không do thao tác đọc file tự thân | Quyền đọc file và cách Spring nạp cấu hình |
| Nạp hoặc theo dõi ConfigMap/Secret bằng API trong ứng dụng | Thường cần | Quyền get/list/watch theo implementation |
| Configuration Watcher chạy riêng | Watcher cần quyền cho công việc của nó | Ứng dụng nhận thông báo có tự đọc lại API không? |
| Kubelet gọi readiness/liveness HTTP của ứng dụng | Không cần token trong ứng dụng chỉ để nhận probe | Health contributor có gọi API riêng không? |
| Workload identity cho dịch vụ cloud bên ngoài | Phụ thuộc nhà cung cấp và audience | Có token projection riêng được inject hay không? |

Spring Cloud Kubernetes cung cấp cả discovery qua Kubernetes client và discovery qua server HTTP. Cần xác định đúng implementation đang sử dụng. [Các loại DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Ví dụ, một HTTP client thường gọi địa chỉ sau có thể dùng cơ chế Service của Kubernetes:

~~~text
http://inventory.sck-security-lab.svc:8080
~~~

Tên này sử dụng DNS search domain phù hợp của Pod trong cụm thông thường. Với DNS tùy biến, phải xác nhận cách phân giải thực tế. Không cần lấy danh sách Pod chỉ để gọi một địa chỉ Service ổn định. [Discovery bằng tên Service](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-kubernetes-native.html).

Không thay đường discovery của một hệ thống đang chọn instance theo metadata mà chưa đánh giá lại hành vi định tuyến. Quyết định bỏ token phải đi cùng quyết định bỏ hoặc chuyển giao nhu cầu gọi API.

## 5. Đặt automountServiceAccountToken đúng vị trí

### 5.1. Mặc định ở ServiceAccount

Ở tài nguyên ServiceAccount, trường này nằm ở cấp gốc:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-app
  namespace: sck-security-lab
automountServiceAccountToken: false
~~~

Cấu hình này đặt mặc định không tự gắn token cho Pod dùng ServiceAccount đó, trừ khi Pod khai báo giá trị khác.

### 5.2. Quyết định ở Pod

Đối với Pod, trường nằm trong spec:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: catalog-example
  namespace: sck-security-lab
spec:
  serviceAccountName: catalog-app
  automountServiceAccountToken: false
  containers:
    - name: app
      image: registry.example.com/training/catalog:1.0.0
~~~

Image trong các ví dụ là địa chỉ minh họa; thay bằng image ứng dụng thực tế trước khi triển khai.

Nếu cả ServiceAccount và Pod đều khai báo automountServiceAccountToken, giá trị ở Pod được ưu tiên. [Quy tắc ưu tiên cấu hình](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

| Giá trị ở ServiceAccount | Giá trị ở Pod | Tự động gắn token theo cơ chế mặc định |
| --- | --- | --- |
| Không khai báo | Không khai báo | Có |
| false | Không khai báo | Không |
| true | false | Không |
| false | true | Có |
| false | false | Không |

Bảng này mô tả cơ chế automount chuẩn. Token được khai báo tường minh hoặc được một admission webhook khác bổ sung phải được kiểm tra riêng.

### 5.3. Vị trí trong Deployment

Deployment cần đặt trường ở spec.template.spec:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: sck-security-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      serviceAccountName: catalog-app
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.com/training/catalog:1.0.0
~~~

Đặt ở metadata hoặc trực tiếp dưới spec của Deployment là sai vị trí. Với StatefulSet, DaemonSet, Job và CronJob, cũng cần tìm đúng Pod template tương ứng thay vì sao chép vị trí một cách máy móc.

Có thể khai báo false ở cả ServiceAccount và Pod template để thể hiện mặc định của danh tính và ý định của workload. Đây không phải rào cản bất biến: người có quyền sửa Pod template vẫn có thể yêu cầu true hoặc khai báo một token projection khác.

## 6. Ví dụ ứng dụng không gọi API: DNS và cấu hình từ volume

Giả sử catalog:

- Nhận HTTP trên cổng 8080.
- Đọc catalog.message từ cấu hình.
- Gọi inventory bằng URL DNS đã cấu hình.
- Không dùng discovery trực tiếp, API property source, leader election hoặc client Kubernetes tùy biến.

### 6.1. Cấu hình ứng dụng

Ưu tiên chỉ đưa các dependency cần thiết vào ứng dụng. Nếu dự án dùng chung dependency và vẫn chứa Spring Cloud Kubernetes, cấu hình tường minh những tích hợp không dùng, phù hợp với phiên bản đang triển khai:

~~~yaml
spring:
  application:
    name: catalog
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: false
      secrets:
        enabled: false
      loadbalancer:
        enabled: false
      leader:
        enabled: false
~~~

Các thuộc tính trên điều khiển từng tính năng tương ứng. Chúng không phải bảo đảm rằng mọi thư viện hoặc mã tùy biến ngừng gọi API. [Danh mục thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Nếu cấu hình hiện tại có spring.config.import trỏ tới Kubernetes API, cần chuyển nó sang nguồn thực sự sử dụng. Đừng giữ đường nạp API rồi chỉ tắt fail-fast để che việc thiếu thông tin xác thực.

### 6.2. Bộ manifest minh họa

Manifest sau tạo namespace, ServiceAccount, ConfigMap và Deployment. Thay image minh họa bằng image có cấu hình ứng dụng ở trên. Service inventory được giả định đã tồn tại nếu kiểm thử luồng gọi dịch vụ:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-security-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-app
  namespace: sck-security-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-settings
  namespace: sck-security-lab
data:
  catalog.message: "Catalog dùng cấu hình từ volume"
  inventory.base-url: "http://inventory.sck-security-lab.svc:8080"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: sck-security-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      serviceAccountName: catalog-app
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.com/training/catalog:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/catalog/"
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          volumeMounts:
            - name: catalog-settings
              mountPath: /etc/catalog
              readOnly: true
      volumes:
        - name: catalog-settings
          configMap:
            name: catalog-settings
~~~

Spring Boot configtree biến tên file thành khóa cấu hình. Trong ví dụ, file catalog.message cung cấp thuộc tính catalog.message. Dùng nguồn bắt buộc giúp phát hiện thư mục cấu hình thiếu ở lúc khởi động. [Configuration trees của Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Luồng đọc cấu hình là:

~~~text
Kubelet lấy ConfigMap theo cơ chế của Kubernetes
    -> mount file vào /etc/catalog
    -> Spring Boot đọc file
    -> tiến trình không cần dùng token để gọi API lấy ConfigMap
~~~

Không có RoleBinding đọc ConfigMap cho catalog-app trong ví dụ. Khi quản lý cụm thật, vẫn cần kiểm tra các quyền được cấp sẵn cho ServiceAccount hoặc nhóm của nó.

POD_NAMESPACE đi qua Downward API, nên việc ứng dụng biết namespace không đòi hỏi phải giữ bộ volume token mặc định.

### 6.3. Trường hợp Secret và imagePullSecrets

Một Secret có thể được mount thành file theo cùng ý tưởng: kubelet chuẩn bị dữ liệu cho Pod, ứng dụng đọc file được cấp cho container. Image pull cũng do kubelet sử dụng thông tin xác thực registry qua imagePullSecrets. [Cách Kubernetes sử dụng Secret](https://kubernetes.io/docs/concepts/configuration/secret/).

Tắt automount token không đồng nghĩa phải xóa ServiceAccount, bỏ imagePullSecrets hoặc cấp quyền get secrets cho ứng dụng. Đây là những đường sử dụng thông tin xác thực khác nhau.

Chỉ mount các khóa Secret cần thiết vào container cần dùng. Việc không có token API không làm mật khẩu trong Secret hết nhạy cảm hoặc ngăn mã của ứng dụng đọc file đã được mount.

## 7. Nếu cần Kubernetes API, cấp ngoại lệ có chủ đích

Một ứng dụng sử dụng DiscoveryClient trực tiếp không thể được chuyển thành ứng dụng không cần thông tin xác thực chỉ bằng cách đặt automount thành false. Có hai hướng triển khai thường gặp.

### 7.1. Bật automount cho workload đã được xác định rõ

Có thể giữ mặc định false ở ServiceAccount rồi bật true ở Pod template của workload cần API:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: catalog-discovery
      automountServiceAccountToken: true
~~~

Đây là trích đoạn Deployment. Tạo ServiceAccount catalog-discovery riêng và cấp đúng quyền cho chức năng discovery. Xem các container và init container thực tế nhận volume token sau admission.

Ngoại lệ cần có lý do cụ thể, chẳng hạn “đọc Service và EndpointSlice trong namespace sck-security-lab để chọn instance”. Câu “ứng dụng dùng Spring Cloud” chưa đủ để mô tả nhu cầu.

### 7.2. Giữ automount false và mount token tường minh

Khi chỉ một container cần API, có thể khai báo projected volume rồi chỉ mount vào container đó. Đoạn PodSpec sau minh họa cách đưa token, CA và namespace vào đường dẫn client thường dùng:

~~~yaml
spec:
  serviceAccountName: catalog-discovery
  automountServiceAccountToken: false
  containers:
    - name: discovery-consumer
      image: registry.example.com/training/catalog:1.0.0
      volumeMounts:
        - name: api-credentials
          mountPath: /var/run/secrets/kubernetes.io/serviceaccount
          readOnly: true
  volumes:
    - name: api-credentials
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600
          - configMap:
              name: kube-root-ca.crt
              items:
                - key: ca.crt
                  path: ca.crt
          - downwardAPI:
              items:
                - path: namespace
                  fieldRef:
                    apiVersion: v1
                    fieldPath: metadata.namespace
~~~

Đây là PodSpec để tích hợp vào template, không phải một Deployment hoàn chỉnh. Giả định namespace có ConfigMap kube-root-ca.crt và ứng dụng dùng client đọc đúng đường dẫn này.

Audience được bỏ qua trong ví dụ để sử dụng audience mặc định của API server. Nếu token dành cho hệ thống khác, cần audience mà hệ thống nhận chấp nhận. expirationSeconds là thời hạn yêu cầu; cần đối chiếu chính sách API server và khả năng làm mới của client. [ServiceAccountTokenProjection](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/).

Projected token được kubelet làm mới. Client phải sử dụng được token mới; mã tự đọc token một lần rồi lưu vĩnh viễn trong bộ nhớ có thể tiếp tục gửi token cũ sau khi nó hết hạn. Kiểm thử qua một chu kỳ thay token, không chỉ kiểm tra lần gọi API đầu tiên. [Vòng đời ServiceAccount token](https://kubernetes.io/docs/concepts/security/service-accounts/).

Không dùng subPath để ghim một file token cần được cập nhật. Không chép token sang image, ConfigMap hoặc biến cấu hình tĩnh để né cơ chế làm mới. Projected volume có quy tắc cập nhật riêng cần được client tôn trọng. [Projected volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/).

Nếu Pod có container không cần token, bỏ volumeMount tương ứng khỏi container đó. Các container trong một Pod vẫn dùng cùng ServiceAccount; mount chọn lọc không tạo ra nhiều danh tính hoặc một ranh giới cô lập tuyệt đối. Khi hai thành phần cần quyền và mức tin cậy khác nhau, cân nhắc tách thành các Pod với ServiceAccount riêng.

### 7.3. RBAC vẫn phải tối thiểu

Giả sử client đã được cấu hình sử dụng Service và EndpointSlice cho discovery trong một namespace. Phần quy tắc của Role có thể giới hạn như sau:

~~~yaml
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Đây chỉ là phần rules; cần Role và RoleBinding đầy đủ tới catalog-discovery trong đúng namespace. Nếu implementation dùng Endpoints hoặc một tài nguyên khác, phải điều chỉnh theo chức năng thực tế. [DiscoveryClient và quyền EndpointSlice](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Không thêm secrets, quyền ghi hoặc quyền toàn cụm chỉ để xử lý một lỗi thiếu token. Token hợp lệ giải quyết xác thực; quyền phù hợp giải quyết phân quyền. Hai thay đổi này cần lý do riêng.

## 8. Configuration Watcher và ứng dụng nhận refresh có thể có nhu cầu khác nhau

Một kiến trúc có thể phân chia trách nhiệm như sau:

~~~text
Configuration Watcher
  ServiceAccount riêng, token và RBAC cần thiết
        |
        | Theo dõi thay đổi ConfigMap/Secret
        | Gửi thông báo refresh
        v
Ứng dụng catalog
  Cấu hình được mount vào filesystem
  Không tự đọc Kubernetes API
  Có thể tắt automount token
~~~

Configuration Watcher hỗ trợ thông báo qua HTTP tới actuator refresh hoặc qua Spring Cloud Bus. File được Kubernetes cập nhật không đồng nghĩa Spring tự cập nhật các đối tượng cấu hình đang chạy. [Cơ chế Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Để ứng dụng nhận refresh vẫn không cần token, phải xác nhận **cả quá trình nạp lại** chỉ dùng các nguồn không gọi Kubernetes API. Nếu refresh kích hoạt lại một API property source còn tồn tại, nhu cầu token vẫn còn.

Bài toán cần kiểm tra theo thứ tự:

1. Dữ liệu mới đã tới volume chưa?
2. Thông báo refresh có tới đúng ứng dụng không?
3. Property source và bean liên quan có thực sự được đọc lại/cập nhật không?
4. Có đường xử lý nào sau refresh tự gọi Kubernetes API không?

Endpoint refresh cần cơ chế bảo vệ của ứng dụng và đường mạng phù hợp. Token ServiceAccount dùng cho Kubernetes API không tự trở thành thông tin xác thực của Spring Security.

Kubelet gọi readiness/liveness của ứng dụng cũng không đòi hỏi ứng dụng giữ token API. Nếu một health contributor tự truy vấn Pod hoặc API server, hãy đánh giá nhu cầu đó riêng với các probe thông thường.

## 9. Kiểm chứng sau triển khai

Các lệnh sau là hướng dẫn thực hành trên môi trường thử nghiệm. Chúng không cần đọc hoặc in nội dung token.

### 9.1. Xem cấu hình khai báo và Pod thực tế

Kiểm tra ServiceAccount và Deployment:

~~~bash
kubectl get serviceaccount catalog-app -n sck-security-lab -o yaml
kubectl get deployment catalog -n sck-security-lab -o yaml
~~~

Sau đó kiểm tra các Pod đã tạo:

~~~bash
kubectl get pods -n sck-security-lab -l app=catalog -o 'custom-columns=POD:.metadata.name,SA:.spec.serviceAccountName,AUTOMOUNT:.spec.automountServiceAccountToken'
kubectl get pods -n sck-security-lab -l app=catalog -o yaml
~~~

Kết quả mong đợi cho ví dụ không cần API:

- Pod dùng catalog-app.
- PodSpec có automountServiceAccountToken: false.
- Container app không có volume token mặc định hoặc projection token khác.
- Volume catalog-settings vẫn được mount đúng.
- Không có webhook bổ sung thông tin xác thực ngoài dự kiến.

Xem cả volumes, volumeMounts, initContainers và các container được inject. Một trường false trong Deployment chưa chứng minh container thực tế không có token.

### 9.2. Kiểm tra sự tồn tại của file

Nếu image thử nghiệm có sh và test:

~~~bash
kubectl exec -n sck-security-lab deployment/catalog -c app -- sh -c 'test ! -e /var/run/secrets/kubernetes.io/serviceaccount/token'
~~~

Exit code 0 nghĩa là phép kiểm tra không thấy file ở đường dẫn đó trong điều kiện thực thi hiện tại. Lỗi exec, thiếu shell hoặc vấn đề quyền filesystem không được diễn giải thành bằng chứng thành công.

Image distroless có thể không chứa shell; dùng cách kiểm tra phù hợp với môi trường chẩn đoán được phép. Không cần cài shell vào image production chỉ để thực hiện bài này.

Kết hợp kết quả file với PodSpec. Không dùng cat token, bật shell tracing hoặc đưa Authorization header vào log để chứng minh token có hay không.

### 9.3. Kiểm tra quyền của danh tính

Từ máy quản trị có quyền impersonation phù hợp, có thể kiểm tra một hành động nhạy cảm:

~~~bash
kubectl auth can-i get secrets -n sck-security-lab --as=system:serviceaccount:sck-security-lab:catalog-app --as-group=system:serviceaccounts --as-group=system:serviceaccounts:sck-security-lab --as-group=system:authenticated
~~~

Lệnh mô phỏng danh tính cùng các nhóm thông thường của ServiceAccount. Kết quả phụ thuộc toàn bộ chính sách cụm; nếu không cấp quyền đọc Secret cho workload, kết quả mong đợi là no. Lỗi thiếu quyền impersonation của người chạy cần được xử lý như một lỗi kiểm tra. [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Phép kiểm tra này trả lời về **quyền**. Nó không sử dụng token bên trong container, không chứng minh volume đã bị loại bỏ và không chứng minh client kết nối được API.

Ngay cả khi không có token trong ứng dụng, vẫn cần loại bỏ quyền thừa nếu phát hiện chúng. Một danh tính không cần quyền đọc Secret không nên giữ quyền đó chỉ vì token hiện chưa được mount.

### 9.4. Kiểm tra hành vi ứng dụng

Thực hiện đúng các luồng đã xác định ở đầu bài:

| Luồng | Kết quả cần chứng minh |
| --- | --- |
| Khởi động | Ứng dụng lên được, nạp đủ cấu hình bắt buộc |
| Đọc cấu hình | Giá trị từ catalog-settings được ứng dụng sử dụng |
| Gọi inventory | DNS, cổng và giao tiếp nghiệp vụ hoạt động |
| Readiness/liveness | Không phát sinh lỗi do một tích hợp API ngoài dự kiến |
| Cập nhật cấu hình, nếu có | Giá trị mới được sử dụng qua cơ chế đã chọn |
| Quan sát log và request | Không có retry gọi Kubernetes API ngoài nhu cầu |
| Ngoại lệ cần token | Đọc đúng tài nguyên và tiếp tục hoạt động khi token được làm mới |

Ứng dụng khởi động thành công chưa đủ nếu discovery hoặc reload chỉ được gọi khi có request hay sự kiện. Kiểm tra cả chức năng được kích hoạt muộn.

## 10. Triển khai thay đổi mà không bỏ sót Pod cũ

Cơ chế tự động gắn volume được quyết định khi Pod được tạo. Đổi mặc định trên ServiceAccount không tự tháo volume đang tồn tại trong Pod cũ.

Một quy trình cho workload cụ thể:

1. Xác định container và tính năng đang sử dụng API.
2. Chuyển hoặc tắt nhu cầu API không cần thiết.
3. Sửa ServiceAccount và Pod template được quản lý trong hệ thống triển khai.
4. Tạo Pod mới qua rollout được kiểm soát.
5. Kiểm tra Pod thực tế và các luồng chức năng.
6. Hoàn thiện quyền RBAC theo nhu cầu còn lại.

Thay đổi Pod template của Deployment sẽ dẫn tới rollout theo cơ chế của Deployment. Nếu chỉ thay ServiceAccount, cần chủ động tái tạo các Pod thuộc phạm vi thay đổi theo quy trình vận hành.

Không tắt automount trên ServiceAccount default của cả namespace rồi giả định mọi workload đều tương thích. Với ứng dụng cần mặc định khác nhau, dùng ServiceAccount riêng và triển khai từng phạm vi.

Nếu phát hiện chức năng cần API, quyết định rõ giữ nó ở ứng dụng hay chuyển sang thành phần khác. Khi giữ lại, khai báo ngoại lệ cụ thể và quyền tối thiểu; tránh bật token trên diện rộng chỉ để làm biến mất thông báo lỗi.

## 11. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý phù hợp |
| --- | --- | --- |
| Không tìm thấy token hoặc không tạo được in-cluster client | Một tính năng API vẫn bật | Tắt nhu cầu không dùng hoặc cấp token cho đúng thành phần |
| Lỗi không xác định namespace sau khi tắt automount | Mã phụ thuộc file namespace trong volume mặc định | Dùng Downward API hoặc cấu hình namespace rõ ràng |
| Lỗi xác minh chứng chỉ | Thiếu/sai CA hoặc cấu hình TLS | Cấp CA đúng; giữ xác minh TLS |
| HTTP 401 từ API | Token thiếu, hết hạn, sai audience hoặc không được chấp nhận | Xác định nguồn token và cơ chế làm mới |
| HTTP 403 từ API | Chủ thể được xử lý theo chính sách không có quyền phù hợp | Xem danh tính trong phản hồi/audit và RBAC |
| Timeout hoặc DNS lỗi | Đường mạng, DNS, địa chỉ hoặc NetworkPolicy | Kiểm tra kết nối riêng với xác thực |
| Lần đầu gọi API được, sau đó lỗi | Client có thể giữ token cũ | Kiểm tra token rotation và phiên bản client |
| Pod vẫn có token dù automount false | Projection tường minh, webhook hoặc container được inject | Kiểm tra PodSpec và nguồn thông tin xác thực |
| Ứng dụng chạy nhưng không refresh được | Đường refresh còn cần API, hoặc thông báo/file/bean chưa cập nhật | Kiểm tra toàn bộ chuỗi cập nhật cấu hình |

Không khẳng định mọi 403 đều có nghĩa token ServiceAccount hợp lệ. Một yêu cầu thiếu token có thể được xử lý như anonymous rồi bị từ chối, tùy cấu hình máy chủ. Dựa vào chủ thể thực tế thay vì chỉ mã trạng thái.

Cũng không sửa lỗi thiếu token bằng cách tắt xác minh TLS, nhúng token tĩnh hoặc cấp cluster-admin. Mỗi triệu chứng cần được giải quyết đúng ở lớp cấu hình, xác thực, phân quyền hoặc mạng tương ứng.

## 12. Điều kiện hoàn thành bài thực hành

Một workload được coi là đã giới hạn automount đúng khi có đủ bằng chứng sau:

- Nhu cầu gọi Kubernetes API của từng thành phần đã được xác định.
- Workload không cần API có cấu hình false ở Pod template và ServiceAccount theo thiết kế.
- Pod mới sau admission không có token ngoài dự kiến trong container cần loại bỏ token.
- Cấu hình từ volume, giao tiếp DNS, sức khỏe và luồng cập nhật liên quan vẫn hoạt động.
- Những ngoại lệ cần API có ServiceAccount, quyền và cơ chế token được giải thích rõ.
- Không ghi token vào log hoặc dùng thông tin xác thực dài hạn để thay thế tùy tiện.
- Quyền RBAC được kiểm tra riêng với sự tồn tại của token.

Kết quả cần đạt là một quyết định có thể kiểm chứng: ứng dụng nào không cần nhận token, thành phần nào cần token, token được đưa vào đâu và quyền nào cho phép chức năng đó hoạt động.
