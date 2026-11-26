# Luân chuyển thông tin truy cập mà không gián đoạn dịch vụ

## 1. Bối cảnh và mục tiêu

Một lần đổi mật khẩu hoặc API token có thể làm ứng dụng Spring mất kết nối dù Secret trong Kubernetes đã được cập nhật thành công. Nguyên nhân thường nằm ở khoảng cách giữa dữ liệu đã lưu, dữ liệu tiến trình đã nạp và thông tin xác thực mà client đang thực sự gửi.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Bảo mật tích hợp**. Bài tập trung vào cách phối hợp Secret, cập nhật cấu hình, vòng đời client, sức khỏe Pod và triển khai để duy trì dịch vụ khi luân chuyển thông tin truy cập.

Sau bài học, bạn có thể:

- Thiết kế khoảng thời gian cùng chấp nhận thông tin truy cập cũ và mới.
- Phân biệt cập nhật Secret với cập nhật cấu hình và thay thế client.
- Chọn rollout hoặc refresh tại chỗ dựa trên khả năng thực tế của ứng dụng.
- Xác minh mọi replica dùng được bản mới trước khi thu hồi bản cũ.
- Chuẩn bị đường khôi phục phù hợp với trạng thái đã thu hồi.

“Không gián đoạn” là mục tiêu cần được kiểm chứng bằng lưu lượng và điều kiện triển khai. Nó phụ thuộc cả hệ thống xác thực phía nhận, năng lực phục vụ, readiness, thời gian chuyển đổi và các request đang chạy.

## 2. Một lần luân chuyển đi qua những trạng thái nào?

Giả sử orders gọi dịch vụ payments bằng một API token. Gọi hai thế hệ thông tin truy cập là G1 và G2; đây là tên phiên bản để quan sát, không phải nội dung token.

~~~text
1. Phía nhận chấp nhận G1
        |
2. Cấp G2, phía nhận cùng chấp nhận G1 và G2
        |
3. Phân phối G2 qua Secret
        |
4. Từng replica tạo hoặc cập nhật client dùng G2
        |
5. Xác minh request hoặc kết nối mới bằng G2
        |
6. Dừng sử dụng G1 và xử lý công việc đang chạy
        |
7. Thu hồi G1 tại phía nhận
        |
8. Theo dõi sau thu hồi và dọn dữ liệu cũ theo chính sách
~~~

Những mốc này không đồng nghĩa với nhau:

| Mốc | Chứng minh được gì? | Chưa chứng minh được gì? |
| --- | --- | --- |
| Secret mới đã lưu | Kubernetes đã nhận dữ liệu | Pod đã thấy dữ liệu mới |
| File trong Pod đã đổi | Dữ liệu tới filesystem | Spring đã nạp lại thuộc tính |
| Thuộc tính đã đổi | Environment hoặc cấu hình đã cập nhật | HTTP client, SDK hoặc pool đã thay |
| Client báo generation G2 | Client được gắn phiên bản mới | Phía nhận đã xác thực request mới |
| Request mới bằng G2 thành công | Một đường gọi đã hoạt động | Mọi replica và mọi luồng đều đã chuyển |
| Không còn dùng G1 trong phạm vi quan sát | Có bằng chứng hội tụ | G1 đã bị vô hiệu hóa tại phía nhận |

Sai lầm điển hình là thực hiện bước 7 ngay sau bước 3. Một số Pod hoặc connection pool vẫn dùng G1 sẽ gặp lỗi sau đó.

## 3. Điều kiện quan trọng nhất: hai thế hệ có thời gian cùng hợp lệ

### 3.1. Đổi phía nhận trước khi đổi bên gọi

Với API token, hệ thống phía nhận nên có khả năng chấp nhận G1 và G2 trong một khoảng chuyển tiếp. Với database, có thể dùng hai tài khoản hoặc cơ chế nhiều thông tin xác thực mà hệ quản trị thực sự hỗ trợ.

Một trình tự không phù hợp là:

~~~text
Đổi mật khẩu duy nhất ở phía nhận
    -> mọi client cũ dùng mật khẩu cũ
    -> cập nhật Secret
    -> chờ các Pod chuyển đổi
~~~

Khoảng giữa hai bước đầu và cuối có thể gây gián đoạn. Kubernetes không tự tạo ra khả năng chấp nhận hai mật khẩu cho database hoặc dịch vụ bên ngoài.

Nếu bên nhận chỉ có một thông tin truy cập hợp lệ tại một thời điểm, cần thay đổi thiết kế, dùng cơ chế chuyển tiếp mà nhà cung cấp hỗ trợ hoặc chấp nhận cửa sổ bảo trì. Không thể bảo đảm mục tiêu chỉ bằng một thứ tự cập nhật YAML.

### 3.2. Lập ngân sách cho khoảng chuyển tiếp

Có thể phân rã:

~~~text
T_overlap >= T_distribute
           + T_apply
           + T_verify
           + T_drain
           + T_margin
~~~

Trong đó:

- T_distribute: thời gian dữ liệu mới tới các workload cần sử dụng.
- T_apply: thời gian refresh hoặc rollout các replica.
- T_verify: thời gian tạo và kiểm chứng thao tác xác thực mới.
- T_drain: thời gian xử lý an toàn công việc còn dùng client cũ.
- T_margin: dự phòng cho độ trễ, retry và biến động.

Đây là mô hình lập kế hoạch, không phải công thức thời gian cố định của Spring hoặc Kubernetes. Một số giai đoạn có thể chồng lấn; dùng timeline đo được để tránh giả định sai.

Ví dụ giả định gồm 90 giây phân phối, 180 giây áp dụng, 60 giây xác minh, 30 giây drain và 60 giây dự phòng cần khoảng 420 giây, tức 7 phút. Con số đó chỉ minh họa cách cộng ngân sách, không phải cấu hình dùng chung.

### 3.3. Phân biệt luân chuyển định kỳ và xử lý lộ lọt

Trong luân chuyển định kỳ, khoảng chuyển tiếp giúp duy trì phục vụ. Nếu nghi ngờ G1 đã bị lộ, việc tiếp tục chấp nhận G1 kéo dài thời gian có thể bị sử dụng trái phép.

Khi đó, quyết định thu hồi sớm phải dựa trên mức độ sự cố. Có thể cần giảm cửa sổ chuyển tiếp, chuyển sang G3 hoặc chấp nhận ảnh hưởng tạm thời. Không dùng mục tiêu sẵn sàng làm lý do tự động giữ một thông tin truy cập đã bị xâm phạm.

## 4. Secret được cập nhật không có nghĩa tiến trình đã cập nhật

### 4.1. So sánh các cách cung cấp dữ liệu

| Cách đưa thông tin truy cập vào ứng dụng | Khi Secret đổi | Việc ứng dụng còn phải làm |
| --- | --- | --- |
| Biến môi trường từ Secret | Biến môi trường của tiến trình đang chạy không tự đổi | Tạo lại Pod hoặc tiến trình theo thiết kế |
| Secret volume thông thường | File được cập nhật theo cơ chế nhất quán cuối cùng | Đọc lại và áp dụng vào đối tượng sử dụng |
| Secret mount bằng subPath | Không nhận cập nhật tự động cho file đó | Đổi cách mount hoặc tạo lại Pod |
| Nạp Secret trực tiếp qua API | Phụ thuộc chu kỳ lấy hoặc theo dõi và implementation | Cập nhật cấu hình, client và pool |
| Secret theo phiên bản, tên mới | Pod đang tham chiếu tên cũ tiếp tục dùng bản cũ | Đổi Pod template và rollout |

Kubernetes mô tả cập nhật Secret volume là nhất quán cuối cùng; subPath không nhận cập nhật tự động. [Secret volume và cập nhật](https://kubernetes.io/docs/concepts/configuration/secret/).

Nếu Secret được dùng làm biến môi trường, cần khởi động lại container để có giá trị mới. [Cấp Secret cho ứng dụng](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

### 4.2. Các lớp trong tiến trình Spring

~~~text
Secret / file / phản hồi API
    -> property source
    -> Environment và cấu hình đã bind
    -> HTTP client / SDK / DataSource / SSL context
    -> kết nối, phiên hoặc request đang chạy
~~~

Mỗi mũi tên là một điểm cần được kiểm chứng. Một giá trị @Value trong singleton hoặc một token đã được sao chép vào cấu hình SDK có thể tiếp tục tồn tại sau khi nguồn dữ liệu đổi.

Spring Boot hỗ trợ nhập file và configuration tree. Việc nhập cấu hình từ filesystem không tự chứng minh client đang chạy có khả năng thay thông tin xác thực tại chỗ. [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Khi dùng nhiều khóa như username, password và generation, cần đọc thành một cấu hình nhất quán. Không thay từng trường trong client dùng chung khi request khác có thể nhìn thấy trạng thái pha trộn.

## 5. Chọn một trong hai chiến lược áp dụng

| Chiến lược | Phù hợp khi | Điều phải chứng minh |
| --- | --- | --- |
| Secret theo phiên bản và rolling update | Client/pool được khởi tạo cùng tiến trình; muốn đơn vị chuyển đổi rõ ràng | Pod mới dùng được G2, Pod cũ drain được, đủ năng lực phục vụ |
| Secret thay đổi và refresh tại chỗ | Đường nạp và client hỗ trợ cập nhật đã được kiểm thử | Dữ liệu tới đúng lúc, client mới được dựng an toàn, request cũ không bị phá |
| Client tự quản lý luân chuyển | SDK hoặc mã ứng dụng có vòng đời credential rõ ràng | Tính nhất quán, kiểm tra candidate, thay thế và đóng client cũ |

Rollout có thể đạt liên tục ở cấp dịch vụ dù từng Pod được thay. Refresh tại chỗ không mặc nhiên tốt hơn nếu phải xử lý client phức tạp hoặc không hỗ trợ làm mới.

Spring Cloud Refresh Scope hỗ trợ vòng đời của những bean phù hợp. Tài liệu nêu HikariDataSource thuộc nhóm không thể refresh; không coi việc thêm @RefreshScope là lời giải chung cho connection pool. [Refresh Scope và HikariDataSource](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Với từng dependency, kiểm tra phiên bản và khả năng đổi thông tin xác thực của chính client. Nếu chưa có bằng chứng, chọn ranh giới thay thế tiến trình có thể kiểm soát là một phương án để đánh giá.

## 6. Ví dụ chính: Secret theo phiên bản và rolling update

### 6.1. Điều kiện môi trường thử nghiệm

Giả sử namespace rotation-lab có:

- Deployment orders đang phục vụ bằng Secret orders-payments-auth-v1.
- Ba replica, có Service chuyển request tới các Pod sẵn sàng.
- Một payments-simulator chấp nhận token giả lập G1 và có thể thêm G2.
- Ứng dụng đọc token khi khởi động và không tự refresh client.
- Endpoint health/probe đã được cấu hình; có phép kiểm tra riêng xác thực mới với simulator.

Trong bài thực hành, chỉ dùng thông tin truy cập giả lập. URL HTTP bên dưới dành cho simulator trong môi trường cách ly; thông tin truy cập thực cần được truyền qua kênh TLS đã xác minh.

### 6.2. Phía nhận cùng chấp nhận G1 và G2

Trước khi thay Secret của orders, cấu hình simulator nhận thêm G2 mà vẫn giữ G1. Thử một thao tác vô hại được bảo vệ bởi xác thực để xác nhận G2 hợp lệ.

Bước này diễn ra ở hệ thống phía nhận. Không được suy ra “G2 đã được cấp” chỉ từ việc đã tạo một chuỗi mới trong Secret.

### 6.3. Tạo Secret mới

Manifest minh họa chứa dữ liệu giả, không phải token để sử dụng thực tế:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-payments-auth-v2
  namespace: rotation-lab
  labels:
    app: orders
    credential-generation: g2
immutable: true
type: Opaque
stringData:
  payments.api-token: "TRAINING_ONLY_G2_DO_NOT_USE"
  rotation.generation: "g2"
~~~

Secret mới có tên riêng và immutable để giữ cố định dữ liệu của lần triển khai này. Những lần luân chuyển sau tạo tên mới; không sửa nội dung của bản immutable. [Immutable Secret](https://kubernetes.io/docs/concepts/configuration/secret/).

generation là định danh không nhạy cảm phục vụ điều phối. Nhãn hoặc thuộc tính generation không phải bằng chứng token hợp lệ và không nên được tạo bằng cách công khai token.

### 6.4. Đổi Pod template sang Secret G2

Đây là Deployment minh họa cần tích hợp với image và Service đang có:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: rotation-lab
spec:
  replicas: 3
  minReadySeconds: 10
  progressDeadlineSeconds: 300
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      serviceAccountName: orders-app
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/training/orders:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/run/credentials/"
            - name: PAYMENTS_BASE_URL
              value: "http://payments-simulator.rotation-lab.svc:8080"
          volumeMounts:
            - name: payments-auth
              mountPath: /run/credentials
              readOnly: true
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
      volumes:
        - name: payments-auth
          secret:
            secretName: orders-payments-auth-v2
~~~

Thay image minh họa bằng image thử nghiệm thực tế. ServiceAccount orders-app phải tồn tại. Cấu hình false phù hợp với giả định ứng dụng chỉ đọc file và không dùng client Kubernetes trực tiếp; nếu có discovery hoặc API property source, đánh giá nhu cầu đó riêng.

Tham chiếu secretName trong Pod template đổi từ v1 sang v2 sẽ tạo một lần rollout. Những Pod cũ vẫn đọc G1; Pod mới đọc G2. Phía nhận phải tiếp tục chấp nhận cả hai trong giai đoạn này.

maxUnavailable và maxSurge điều khiển cách Deployment thay replica; minReadySeconds yêu cầu Pod mới duy trì trạng thái sẵn sàng một khoảng trước khi được tính là available. [Rolling update của Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

Các con số là ví dụ, cần điều chỉnh theo thời gian khởi động và tải. progressDeadlineSeconds giúp phát hiện rollout không tiến triển; không coi nó là cơ chế tự động khôi phục đầy đủ ứng dụng và thông tin truy cập.

### 6.5. Readiness phải phản ánh khả năng dùng G2

Liveness và readiness mặc định không phải phép thử token mới với payments. Trước khi Pod G2 nhận lưu lượng, ứng dụng cần hoàn thành bước xác minh có kiểm soát bằng chính client đang được đưa vào phục vụ.

Có thể thiết kế một trạng thái kiểm tra khởi động:

~~~text
Đọc credential G2
    -> dựng client
    -> xác thực qua một thao tác an toàn với kết nối mới
    -> ghi nhận client G2 đã được xác minh
    -> cho phép chuyển readiness sang sẵn sàng
~~~

Đây là hành vi cần bổ sung trong ứng dụng hoặc hệ thống kiểm soát triển khai, không phải tính năng tự có chỉ từ manifest probe ở trên. Nếu chưa có gate này, phải xác minh canary trước khi mở rộng rollout; đừng coi health UP là đủ.

Tránh làm readiness phụ thuộc vào một lần gọi dịch vụ ngoài ở mọi chu kỳ probe mà chưa đánh giá tác động. Kiểm tra có giới hạn và lưu trạng thái phù hợp giúp tránh làm một lỗi phụ thuộc ngắn hạn loại toàn bộ replica khỏi phục vụ. [Liveness và readiness của Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

### 6.6. Drain request cũ

Cấu hình graceful shutdown phù hợp với phiên bản Spring Boot:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Graceful shutdown dành thời gian cho request hiện có hoàn tất trong quá trình dừng. [Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).

Thời gian terminationGracePeriodSeconds phải đủ cho toàn bộ quá trình dừng, kể cả hook hoặc các pha khác nếu có. Không suy ra rằng 60 giây luôn đủ chỉ vì một pha được cấu hình 30 giây.

Cũng cần tính thời gian endpoint và cache định tuyến cập nhật. Nếu Spring Cloud LoadBalancer hoặc proxy còn giữ danh sách instance cũ, có thể vẫn phát sinh request tới Pod đang dừng. Kiểm thử hành vi drain trên đúng đường gọi thực tế.

## 7. Phương án refresh tại chỗ với Configuration Watcher

### 7.1. Chỉ chọn khi toàn bộ đường áp dụng đã được kiểm thử

Trong phương án này, ứng dụng tiếp tục mount một Secret có thể thay đổi, chẳng hạn orders-payments-auth. Watcher theo dõi Secret và thông báo refresh.

Đây là phương án thay thế cho ví dụ Secret immutable theo phiên bản, không phải một bước bắt buộc phải thêm vào rollout ở mục 6.

Ví dụ dữ liệu giả trong một tài liệu YAML:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-payments-auth
  namespace: rotation-lab
  labels:
    spring.cloud.kubernetes.secret: "true"
  annotations:
    spring.cloud.kubernetes.secret.apps: "orders"
type: Opaque
stringData:
  application.yaml: |
    payments:
      api-token: "TRAINING_ONLY_G2_DO_NOT_USE"
    rotation:
      generation: "g2"
~~~

Ứng dụng mount cả thư mục, không dùng subPath. Đường nhập cấu hình cho ví dụ này là file YAML, khác với configtree của mục trước:

~~~yaml
spring:
  config:
    import: "file:/run/credentials/application.yaml"
~~~

Giữ các trường liên quan trong một tài liệu giúp thiết kế thao tác đọc snapshot nhất quán. Tuy vậy, vẫn phải kiểm chứng cách nguồn cấu hình và client đọc lại dữ liệu trong phiên bản đang dùng.

### 7.2. Cấu hình ở chính Deployment của Watcher

Ví dụ trích đoạn biến môi trường:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
    value: "true"
  - name: SPRING_CLOUD_KUBERNETES_RELOAD_NAMESPACES_0
    value: "rotation-lab"
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
    value: "10000"
~~~

Watcher không theo dõi Secret theo mặc định; cần bật chức năng và chọn nguồn phù hợp. Annotation trong ví dụ xác định ứng dụng nhận thông báo khi tên Secret khác tên ứng dụng. [Theo dõi Secret và xác định đích cập nhật](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Giá trị 10000 là khoảng chờ minh họa trước thông báo. Nó không phải cam kết mọi volume đã có dữ liệu mới sau 10 giây. Đo độ trễ phân phối và xác minh generation thực tế; nếu refresh tới trước dữ liệu, cần cơ chế thử lại có kiểm soát hoặc chờ đúng trạng thái.

Đích HTTP refresh phải được expose, bảo vệ và truy cập đúng cổng. Nếu dùng Bus, cần kiểm soát broker và phạm vi nhận sự kiện. Một thông báo thành công chỉ là tín hiệu bắt đầu áp dụng, không phải biên nhận rằng từng client đã dùng G2.

### 7.3. Không đồng nhất refresh bean với thay client an toàn

Có thể phân chia một thiết kế client tự quản lý như mã giả sau:

~~~text
candidate = đọc một snapshot credential hoàn chỉnh
newClient = tạo client riêng từ candidate
xác minh newClient bằng một thao tác xác thực mới

nếu xác minh thất bại:
    đóng candidate chưa sử dụng
    giữ client đang phục vụ
    ghi nhận lỗi không chứa secret
nếu xác minh thành công:
    chuyển tham chiếu active sang newClient theo cách nguyên tử
    để request đang giữ oldClient hoàn tất
    đóng oldClient khi không còn được sử dụng an toàn
~~~

Đây là thuật toán thiết kế, không phải đoạn Java có thể chạy ngay hoặc hành vi được @RefreshScope bảo đảm tự động.

Cần giải quyết thêm:

- Xử lý nhiều sự kiện cho cùng generation theo cách có thể lặp lại.
- Không để một lần xử lý chậm đưa generation cũ trở lại.
- Không giữ khóa toàn cục trong suốt request mạng.
- Có timeout và quyền sở hữu rõ ràng khi đóng client cũ.
- Giữ đúng cơ chế thread safety của SDK hoặc connection pool.
- Không hủy tài nguyên mà request đang chạy còn sử dụng.

Refresh Scope tạo proxy và có vòng đời khởi tạo lại riêng; một lần refresh được chấp nhận chưa có nghĩa mọi bean lazy đã được khởi tạo thành công. [Vòng đời Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Nếu chưa kiểm soát được những điều này, rollout tiến trình vẫn là lựa chọn cần cân nhắc cho lần luân chuyển.

## 8. Các loại thông tin truy cập cần cách xác minh khác nhau

### 8.1. Database và connection pool

Một truy vấn thành công trên kết nối đã mở không chứng minh mật khẩu mới hợp lệ. Kết nối cũ có thể đã xác thực từ trước và còn sống sau khi phía server thay chính sách.

Trước khi thu hồi G1, cần:

1. Dựng pool hoặc client candidate dùng G2 theo cơ chế được hỗ trợ.
2. Buộc phép thử tạo kết nối vật lý mới, không chỉ mượn lại kết nối cũ.
3. Thực hiện truy vấn kiểm tra an toàn và xác nhận đúng tài khoản/quyền.
4. Chuyển traffic sang pool mới, xử lý transaction đang chạy.
5. Xác minh cách server xử lý session G1 khi thu hồi.

Không giả định đổi mật khẩu sẽ ngắt mọi session cũ, hoặc ngược lại sẽ giữ mọi session. Hành vi phụ thuộc database và cách thu hồi.

Trong rollout, mỗi Pod mới tạo pool G2 nhưng Pod cũ có thể vẫn giữ pool G1 trong giai đoạn chuyển tiếp. Tính ngân sách tổng kết nối để việc tăng thêm một replica không làm database quá tải.

### 8.2. API key, token và OAuth

Với API key hoặc bearer token, xác minh bằng request mới mà phía nhận có thể ghi nhận định danh credential đã chấp nhận. Không in token để đối chiếu.

Nếu đang dùng OAuth hoặc SDK tự làm mới token, cần phân biệt access token ngắn hạn với client secret hoặc refresh token đang luân chuyển. Vòng đời và khả năng chấp nhận đồng thời của từng loại do hệ thống xác thực quyết định.

Không áp dụng fallback G1 cho mọi lỗi 401 một cách vô hạn. Cơ chế đó có thể che việc chuyển G2 chưa hoàn tất và làm khó quyết định thu hồi. Với thao tác có tác dụng phụ, retry còn phải tuân thủ idempotency để tránh tạo giao dịch trùng.

### 8.3. Chứng chỉ TLS và trust material

Đổi chứng chỉ cần kiểm tra cả bên trình chứng chỉ và bên tin cậy nó. Nếu đổi CA, một trình tự có thể gồm mở rộng trust sang CA mới, chuyển chứng chỉ, xác minh handshake mới rồi mới bỏ CA cũ.

File chứng chỉ đổi không chứng minh SSL context hoặc các kết nối hiện tại đã đổi. Dùng handshake mới để kiểm tra.

Spring Boot có SSL bundle và khả năng reload cho những tích hợp được hỗ trợ. Không suy ra mọi HTTP client hoặc loại keystore đều tự nhận cập nhật. [SSL bundles và reload](https://docs.spring.io/spring-boot/reference/features/ssl.html).

### 8.4. Token ServiceAccount để gọi Kubernetes API

Token ServiceAccount được project vào volume có cơ chế hết hạn và làm mới do kubelet phối hợp với API server. Client cần đọc được token mới thay vì giữ mãi nội dung cũ. [Vòng đời token ServiceAccount](https://kubernetes.io/docs/concepts/security/service-accounts/).

Đối với DiscoveryClient hoặc Watcher, kiểm thử request mới và khả năng reconnect WATCH sau một chu kỳ thay token. Một WATCH còn mở chưa chứng minh lần xác thực tiếp theo sẽ dùng được token mới.

Không sao chép token được project thành một Secret token tĩnh để né việc làm mới. Nếu ứng dụng không cần API, đánh giá việc không gắn token ngay từ đầu.

## 9. Xác minh hội tụ trên toàn bộ bên sử dụng

### 9.1. Lập danh sách consumer đầy đủ

Không chỉ đếm các Pod có trong Service. Cùng một credential có thể được dùng bởi:

- Replica đang phục vụ, canary hoặc workload ở namespace khác.
- Job đang chạy, consumer xử lý nền hoặc tác vụ theo lịch.
- Pod cũ đang drain và các request đang thực thi.
- Công cụ vận hành hoặc tích hợp ngoài cụm.

Một CronJob vẫn tham chiếu G1 có thể tạo Pod lỗi sau khi đợt rollout web đã hoàn tất. Kiểm tra cả template sẽ được dùng trong tương lai và các công việc đang chạy.

DiscoveryClient giúp tìm instance theo phạm vi cấu hình; danh sách instance không thay thế danh mục đầy đủ các consumer của một credential.

### 9.2. Quan sát phiên bản thay vì lộ nội dung

Các tín hiệu hữu ích:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| activeGeneration theo Pod | Phiên bản client đang được đưa vào phục vụ |
| verifiedGeneration theo Pod | Phiên bản đã qua phép thử xác thực mới |
| Kết quả xác thực theo credential ID ở phía nhận | Bằng chứng thông tin mới được chấp nhận |
| Số request hoặc tác vụ đang dùng client cũ | Điều kiện drain |
| Lỗi xác thực và lỗi tạo kết nối mới | Phát hiện chuyển đổi thất bại |
| Độ trễ, timeout và lỗi nghiệp vụ | Đánh giá mức gián đoạn |
| Số Pod ready/available | Quan sát năng lực phục vụ trong rollout |

Tên G1/G2 là metadata không nhạy cảm. Không dùng token hoặc mật khẩu làm nhãn metric, không xuất toàn bộ cấu hình và không ghi Authorization header vào log.

Một endpoint nội bộ tự xây dựng có thể trả trạng thái như sau:

~~~json
{
  "pod": "orders-example",
  "activeGeneration": "g2",
  "verifiedGeneration": "g2",
  "lastFreshAuthentication": "SUCCESS"
}
~~~

Đây là giao diện minh họa cần được ứng dụng triển khai và bảo vệ, không phải endpoint có sẵn của Spring. verifiedGeneration chỉ có giá trị khi được cập nhật từ phép thử thực tế của client tương ứng.

### 9.3. Kiểm tra rollout mà không đọc dữ liệu Secret

Các lệnh sau là hướng dẫn thực hành, không tự thực hiện luân chuyển ở phía nhận:

~~~bash
kubectl rollout status deployment/orders -n rotation-lab --timeout=300s
kubectl get pods -n rotation-lab -l app=orders -o 'custom-columns=POD:.metadata.name,READY:.status.containerStatuses[*].ready,SECRET:.spec.volumes[*].secret.secretName'
kubectl get secret orders-payments-auth-v2 -n rotation-lab -o 'custom-columns=NAME:.metadata.name,IMMUTABLE:.immutable'
kubectl get endpointslices -n rotation-lab -l kubernetes.io/service-name=orders -o yaml
~~~

Kết hợp trạng thái này với phép thử credential trên từng replica và bằng chứng phía payments. Không chỉ gọi Service một lần: LoadBalancer có thể liên tục đưa request tới một Pod đã chuyển G2 trong khi Pod khác vẫn còn G1.

Không dùng kubectl get secret -o yaml hoặc lệnh giải mã dữ liệu để chứng minh hội tụ. Chúng có thể làm nội dung credential xuất hiện trong terminal, log tác vụ hoặc lịch sử xử lý.

### 9.4. Điều kiện được phép thu hồi G1

Trước khi thu hồi, xác nhận:

- Mọi consumer đang hoạt động đã dùng và xác minh được G2.
- Template của workload có thể chạy lại đã được chuyển phù hợp.
- Không còn công việc cần hoàn tất bằng G1 theo thiết kế.
- Không có request xác thực mới bằng G1 trong khoảng quan sát đã chọn.
- Lỗi xác thực, độ trễ và năng lực phục vụ ở mức chấp nhận được.
- Có kế hoạch xử lý nếu G2 gặp lỗi sau khi G1 đã bị thu hồi.

Không chọn cửa sổ quan sát ngắn hơn chu kỳ của tác vụ chạy thưa rồi kết luận chắc chắn không còn G1. Cần kiểm tra cấu hình và chủ động thực hiện phép thử phù hợp thay vì chờ thiếu bằng chứng.

## 10. Thu hồi, khôi phục và dọn dữ liệu cũ

### 10.1. Thu hồi tại đúng nơi

G1 phải bị vô hiệu hóa ở hệ thống xác thực phía nhận. Xóa Secret khỏi Kubernetes không tự thu hồi token API, tài khoản database hoặc chứng chỉ ở nơi khác.

Sau thu hồi:

1. Xác nhận G2 tiếp tục hoạt động bằng request/kết nối mới.
2. Kiểm tra G1 bị từ chối bằng phép thử được kiểm soát.
3. Theo dõi lỗi từ consumer bị bỏ sót.
4. Dọn Secret và bản triển khai cũ theo chính sách lưu giữ.
5. Ghi nhận thời điểm cấp, áp dụng, xác minh và thu hồi bằng metadata an toàn.

Phép thử G1 sau thu hồi không được làm token xuất hiện trong command line hoặc log. Dùng công cụ kiểm thử được cấp quyền và quản lý secret phù hợp.

### 10.2. Rollback phụ thuộc việc G1 còn hợp lệ hay không

| Thời điểm sự cố | Khả năng khôi phục |
| --- | --- |
| G2 chưa áp dụng, G1 vẫn hợp lệ | Dừng chuyển đổi và giữ G1 |
| Một số replica dùng G2, G1 vẫn hợp lệ | Dừng mở rộng; sửa G2 hoặc đưa workload về phiên bản phù hợp |
| G1 đã thu hồi | Quay về template G1 có thể làm ứng dụng lỗi |
| G1 bị nghi lộ | Không tự khôi phục bằng cách bật lại G1 |
| Secret cũ đã bị xóa | Revision cũ có thể không tạo Pod được dù dữ liệu triển khai còn |

Revision của Deployment và hiệu lực credential là hai loại trạng thái khác nhau. Khôi phục Deployment không làm phía payments tự chấp nhận lại G1.

Khi G1 không thể dùng lại, kế hoạch có thể là cấp G3, sửa client hoặc chuyển tiếp sang cấu hình hợp lệ khác. Quy trình cần mô tả điều kiện thực hiện và người chịu trách nhiệm, thay vì chỉ ghi “rollback nếu lỗi”.

### 10.3. Phân biệt nguồn cấu hình bị lỗi và credential bị lỗi

Nếu G2 bị từ chối, có thể do token chưa được cấp quyền, Secret sai dữ liệu, thuộc tính bị nguồn khác ghi đè hoặc client vẫn gửi G1.

Trước khi cấp lại hàng loạt, kiểm tra từng lớp mà không công khai nội dung:

~~~text
Phiên bản được phát hành
    -> phiên bản Secret được tham chiếu
    -> phiên bản cấu hình có hiệu lực
    -> phiên bản client đang dùng
    -> credential ID được phía nhận xác thực
~~~

Một biến môi trường cũ có thể ghi đè cấu hình nhập từ file. Cần xem thứ tự nguồn cấu hình và cấu hình triển khai, không chỉ nội dung file mới.

## 11. RBAC, mạng và quyền quản lý quá trình luân chuyển

Tách trách nhiệm theo nhu cầu:

| Thành phần | Quyền và đường truy cập cần xem xét |
| --- | --- |
| Bộ phận hoặc hệ thống cấp credential | Tạo/thu hồi ở phía nhận theo chính sách |
| Thành phần ghi Secret | Ghi đúng Secret trong phạm vi được giao |
| Ứng dụng chỉ đọc volume | Đọc file đã mount; không tự cần quyền list Secret |
| Ứng dụng đọc Secret qua API | Token/CA, RBAC tối thiểu và đường API |
| Configuration Watcher | Theo dõi đúng nguồn, tìm đúng đích và gửi thông báo |
| Công cụ xác minh | Quan sát trạng thái và thực hiện kiểm tra được phép |

Không cấp quyền ghi Secret cho ứng dụng chỉ vì nó cần sử dụng credential. Không cấp quyền đọc tất cả Secret cho công cụ chỉ cần biết trạng thái generation.

NetworkPolicy cần bảo đảm các đường thực sự sử dụng: ứng dụng tới payments/database, Watcher tới API và endpoint quản trị, hoặc các thành phần tới broker. Lỗi mạng trong lúc chuyển G2 có thể giống lỗi credential nếu chỉ nhìn thông báo tổng quát.

Bảo vệ actuator refresh và các endpoint quan sát riêng. Quyền gọi Kubernetes API bằng ServiceAccount không tự cấp quyền gọi endpoint Spring, và một allow rule mạng không thay thế xác thực ứng dụng.

## 12. Bài thực hành và tiêu chí hoàn thành

Thực hiện trên môi trường thử nghiệm có simulator và thông tin truy cập giả theo mục 6.

### 12.1. Kịch bản bình thường

1. Duy trì lưu lượng kiểm thử qua Service orders bằng G1.
2. Thêm G2 tại simulator và xác nhận G2 hoạt động.
3. Tạo Secret phiên bản v2, cập nhật Pod template theo cách quản lý triển khai.
4. Quan sát từng replica mới, phép thử xác thực mới và quá trình drain.
5. Xác minh không còn consumer cần G1.
6. Thu hồi G1 ở simulator.
7. Kiểm tra G2 tiếp tục hoạt động và G1 đã bị từ chối.

Lưu kết quả lỗi, độ trễ và từng mốc chuyển đổi. Các lệnh hoặc manifest minh họa không thay thế việc kiểm thử trên hệ thống thực.

### 12.2. Các tình huống cần chủ động thử

| Tình huống | Hành vi mong đợi |
| --- | --- |
| G2 chưa được simulator chấp nhận | Candidate không được đưa vào phục vụ; rollout không tiếp tục loại Pod đang hoạt động |
| Một Pod không nạp được Secret | Phát hiện Pod chưa hội tụ; chưa thu hồi G1 |
| Refresh tới trước file mới | Không xác nhận nhầm G2; có cơ chế chờ hoặc thử lại phù hợp |
| Property đổi nhưng SDK giữ token cũ | Phép thử xác thực mới phát hiện khác biệt |
| Pool chỉ còn kết nối cũ | Phép thử kết nối vật lý mới vẫn được thực hiện |
| Watcher mất quyền hoặc mất mạng | Có tín hiệu lỗi và không coi thông báo đã được gửi |
| Job chạy thưa còn tham chiếu G1 | Kiểm kê consumer phát hiện trước khi thu hồi |
| G2 lỗi sau khi G1 đã thu hồi | Dùng kế hoạch sau thu hồi, không tự quay về credential đã mất hiệu lực |

### 12.3. Bằng chứng hoàn thành

Một lần luân chuyển đạt mục tiêu khi:

- G2 được phía nhận chấp nhận trước khi đưa vào sử dụng.
- Từng consumer cần thiết có bằng chứng dùng được G2 bằng xác thực mới.
- Request và công việc đang chạy được xử lý theo thiết kế.
- Chất lượng phục vụ được đo trong suốt quá trình.
- G1 được thu hồi tại đúng hệ thống và không còn được sử dụng thành công.
- Secret, quyền truy cập và dữ liệu cũ được xử lý theo chính sách.
- Có cách ứng phó cho trạng thái sau thu hồi.

Kết quả cần đạt là một quy trình có điều kiện chuyển bước rõ ràng. Mỗi bước dựa trên bằng chứng của client và hệ thống phía nhận, thay vì chỉ dựa vào thông báo cập nhật Secret hoặc refresh thành công.
