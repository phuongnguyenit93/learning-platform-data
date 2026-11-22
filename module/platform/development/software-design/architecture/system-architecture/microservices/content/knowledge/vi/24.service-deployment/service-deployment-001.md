# Lựa chọn máy ảo, container, nền tảng quản lý hoặc serverless

**Phạm vi:** Triển khai dịch vụ trong kiến trúc hệ thống và microservices. Các mô hình được so sánh gồm máy ảo (virtual machine – VM), container, nền tảng được quản lý (managed platform/PaaS), Kubernetes được quản lý, serverless container và hàm serverless (Function as a Service – FaaS).

Một ứng dụng có thể hoạt động đúng trên máy phát triển nhưng thất bại trong sản xuất vì máy chủ thiếu bộ nhớ, không có cách mở rộng, triển khai gây ngắt dịch vụ, cấu hình bí mật bị lộ hoặc không có phương án khôi phục. **Lựa chọn mô hình chạy ứng dụng** tác động trực tiếp đến độ tin cậy, tốc độ phát hành, chi phí, an toàn dữ liệu và công sức vận hành.

Không có lựa chọn mặc định tốt cho mọi hệ thống. Một API Java có lưu lượng đều, một tác vụ chạy mỗi đêm, một consumer đọc hàng đợi liên tục và một bộ xử lý ảnh phát sinh theo sự kiện có đặc tính khác nhau. Cùng một tổ chức có thể sử dụng nhiều mô hình triển khai, miễn là mỗi lựa chọn giải quyết được bài toán cụ thể và đội ngũ có khả năng vận hành.

Mục tiêu bài học: hiểu điều gì đang được quản lý ở mỗi tầng, chọn mô hình từ đặc tính workload và yêu cầu nghiệp vụ, định lượng những đánh đổi quan trọng, và xây dựng đường triển khai có thể kiểm chứng và chuyển đổi khi hệ thống phát triển.

## 1. Mô hình tư duy: ứng dụng chạy trên một chuỗi trách nhiệm

Mọi dịch vụ đều cần các lớp cơ sở hạ tầng: phần cứng, hệ điều hành, runtime, mạng, lưu trữ, cấu hình, lịch triển khai, quan sát và phục hồi. Khác biệt chính giữa các mô hình là **ai chịu trách nhiệm cho những lớp đó và giới hạn tùy biến ở đâu**.

~~~text
Ứng dụng nghiệp vụ + dữ liệu + hợp đồng API
                 |
       Runtime / process / container
                 |
   OS + kết nối mạng + lưu trữ + bảo mật
                 |
      Máy tính + datacenter + vùng lỗi
                 |
     Triển khai + giám sát + khôi phục
~~~

- **Máy ảo:** người triển khai thường quản lý hệ điều hành khách, bản vá, runtime, service manager, vận hành và phần lớn cấu hình của workload; nhà cung cấp hạ tầng quản lý host vật lý và hypervisor.
- **Container:** ứng dụng được đóng gói cùng phần lớn phụ thuộc userspace vào image. Container vẫn cần nơi chạy và cơ chế điều phối; **container là định dạng đóng gói và cách cô lập tiến trình, không tự là nền tảng vận hành hoàn chỉnh**.
- **Nền tảng được quản lý:** người dùng nộp code hoặc image, khai báo tài nguyên và chính sách; nền tảng đảm nhiệm thêm khâu chạy, lịch triển khai, cân bằng tải hay mở rộng tùy dịch vụ.
- **Serverless:** người dùng tập trung vào code/image, cấu hình nguồn kích hoạt và ngân sách; nhà cung cấp chủ động cấp phát thực thi theo mô hình sự kiện hoặc yêu cầu. Serverless không có nghĩa không có server, cũng không bảo đảm chi phí bằng không lúc ít tải.

Phải phân biệt **hình thức đóng gói** với **dịch vụ vận hành**. Một ứng dụng đóng gói Docker có thể chạy trên VM, trên Kubernetes, trên PaaS hoặc trên serverless container. Hai hệ thống đều dùng container vẫn có mức trách nhiệm vận hành rất khác nhau.

## 2. Bốn nhóm lựa chọn thường gặp

| Mô hình | Cách triển khai | Nhóm chịu trách nhiệm nhiều hơn | Phù hợp ban đầu khi |
|---|---|---|---|
| **VM / IaaS** | Cài ứng dụng/runtime hoặc chạy container trên VM; dùng systemd, load balancer, autoscaling group | Đội ngũ quản lý OS, bản vá, cấu hình và vòng đời tiến trình | Cần kiểm soát hệ điều hành, phụ thuộc đặc biệt, workload ổn định hoặc chuyển từ hệ thống cũ |
| **Container do đội ngũ tự vận hành** | Đóng image, chạy qua Docker/Compose hoặc orchestrator do đội tự quản | Đội ngũ quản lý host, scheduler, mạng, backup, log, HA | Có năng lực vận hành và yêu cầu tùy biến cao |
| **Nền tảng quản lý / PaaS / managed orchestrator** | Nộp code/image + khai báo tài nguyên; nền tảng vận hành phần chung | Nhà cung cấp quản lý nhiều lớp hơn, đội ngũ vẫn quản lý ứng dụng, dữ liệu và policy | Cần giảm công vận hành, tăng tốc phát hành, workload phục vụ dài hạn |
| **Serverless function hoặc serverless container** | Hàm/sự kiện hoặc container xử lý yêu cầu; tự cấp phát theo đặc tính nền tảng | Nhà cung cấp quản lý phân bổ compute, runtime nền, scale | Công việc ngắn/theo sự kiện, tải biến động, API/stateless phù hợp giới hạn dịch vụ |

**Managed Kubernetes** không tương đương với PaaS đơn giản: nhà cung cấp có thể quản lý control plane, nhưng người dùng vẫn phải thiết kế Deployment, Service, ingress, RBAC, chính sách mạng, tài nguyên, rollout, observability và đôi khi cả node. “Được quản lý” phải được hỏi cụ thể **nền tảng quản lý những thành phần nào**.

**Serverless container** có thể chạy một ứng dụng HTTP đầy đủ và tự scale theo request, trong khi **FaaS** thực thi từng handler theo sự kiện. Hai lựa chọn có thể cùng được gọi là serverless nhưng khác rõ về timeout, concurrency, khởi tạo, hỗ trợ background work và cách tính phí.

## 3. Bắt đầu từ workload, không bắt đầu từ tên sản phẩm

Trước khi chọn công nghệ, hãy viết ra đặc tính của dịch vụ.

**Mẫu mô tả workload:**

~~~yaml
service: checkout-api
kind: synchronous-http
runtime: java-21
traffic:
  baselineRps: 20
  peakRps: 200
  dailyPattern: business-hours
latency:
  p95TargetMs: 300
  hardDeadlineMs: 3000
availability:
  target: "theo SLO đã được phê duyệt"
state:
  requestHandling: stateless
  persistentStore: external-database
dependencies:
  - payment-api
  - message-broker
constraints:
  dataResidency: region-approved
  privateConnectivity: required
  maintenanceWindow: limited
team:
  operationalCapacity: small
~~~

Các trường là ví dụ mô tả, không phải manifest triển khai. Cần khảo sát thêm CPU, RAM, disk I/O, network, thời gian khởi động, phiên làm việc, lưu lượng đến theo burst, yêu cầu GPU/thiết bị, nhu cầu chạy liên tục, tác vụ nền, phương án backup và kỹ năng đội ngũ.

Một API có 20 RPS nhưng mỗi request tốn 5 giây kết nối DB không giống API 200 RPS xử lý trong 10 ms. **RPS không đủ để chọn nền tảng hoặc kích thước tài nguyên.** Cần đo thông lượng bền vững, concurrency, độ trễ, mức tiêu thụ bộ nhớ và các tài nguyên phía sau.

### 3.1. Các nhóm workload tiêu biểu

| Workload | Đặc tính cần xét | Những hướng triển khai đáng thử |
|---|---|---|
| API HTTP stateless | RPS, latency, startup, kết nối DB, scale-out | VM + LB, PaaS, managed container, serverless container |
| WebSocket/streaming lâu | Kết nối giữ lâu, affinity, idle timeout, giới hạn nền tảng | VM, nền tảng container hỗ trợ kết nối dài; kiểm tra giới hạn từng dịch vụ |
| Consumer Kafka/RabbitMQ liên tục | Duy trì kết nối, partition, consumer group, backpressure | VM, container service, managed Kubernetes; một số nền tảng event-driven tương thích |
| Cron hoặc batch ngắn | Thời gian chạy, lịch, khả năng retry, concurrency | Managed job, scheduled container, FaaS nếu thời gian/tài nguyên phù hợp |
| Tác vụ AI/ảnh cần GPU | GPU, thời gian thực thi, disk/cache, chi phí chờ | VM GPU, managed job/container có GPU; serverless chuyên dụng nếu được hỗ trợ |
| State-intensive database | Độ bền, backup, replication, IOPS, phục hồi | Dịch vụ database managed hoặc kiến trúc stateful được vận hành chuyên biệt |
| Legacy/ứng dụng phụ thuộc OS | Kernel/package/binary đặc thù, IP cố định | VM hoặc image tùy biến trên nền tảng hỗ trợ |
| Webhook tải theo đợt | Burst, cold start, deadline, idempotency | Serverless function/container hoặc PaaS autoscaling |
| Công việc vài phút đến hàng giờ | Thời gian chạy, retry, checkpoint | Job runner, container worker, VM; kiểm tra trần thời gian của FaaS |

Cần xác định workload **có thể dừng và khởi động lại tùy thời điểm** không. Một tiến trình giữ trạng thái quan trọng trong RAM hoặc phụ thuộc duy nhất vào ổ đĩa cục bộ rất khó scale hoặc di chuyển an toàn, bất kể chạy trên VM hay Kubernetes.

## 4. VM: quyền kiểm soát cao đi cùng trách nhiệm vận hành

Máy ảo cung cấp hệ điều hành khách và tài nguyên tính toán có thể cấu hình. Ví dụ một dịch vụ Spring Boot có thể được cài bằng JAR, chạy dưới tài khoản riêng, được systemd giám sát và đặt sau load balancer.

~~~text
Client
  |
Load Balancer / Reverse Proxy
  |
  +-- VM A: OS + JDK + Checkout JAR
  |
  +-- VM B: OS + JDK + Checkout JAR
  |
  +-- VM C: OS + JDK + Checkout JAR
           |
       Managed Database
~~~

**Điểm mạnh:**

- Chủ động lựa chọn hệ điều hành, thư viện native, agent, cấu hình kernel được phép và cách quản lý tiến trình.
- Hữu ích cho hệ thống có ràng buộc đặc biệt hoặc cần di chuyển một ứng dụng vốn chạy trên server truyền thống.
- Có thể tối ưu chi phí cho tải ổn định trên máy được đặt trước/cam kết, tùy phương án mua compute.
- Dễ gắn các thành phần hạ tầng quen thuộc như systemd, reverse proxy, log collector hoặc backup agent.

**Chi phí và rủi ro vận hành:**

- Phải quản lý patch OS/JDK, cập nhật thư viện, chuẩn hóa image VM, tạo tài khoản ít quyền nhất và quản lý secret.
- Phải thiết kế HA, load balancing, autoscaling, thay VM lỗi, backup, health check và giám sát.
- Đổi kích thước VM có thể yêu cầu thay/restart; scale-out cần cân bằng tải và giải quyết state phiên.
- Nếu triển khai trực tiếp lên cùng một VM đang phục vụ, restart có thể gián đoạn. Muốn zero/minimal downtime cần nhiều instance và quy trình rolling hoặc blue/green.
- “Cài bằng tay” dễ gây configuration drift, khó truy vết phiên bản nào đang chạy.

### 4.1. Ví dụ đơn vị service cho Spring Boot bằng systemd

Giả sử artifact đã nằm tại **/opt/checkout/checkout.jar**, có user hệ thống riêng và cấu hình bí mật được cung cấp an toàn.

~~~ini
[Unit]
Description=Checkout Service
After=network-online.target
Wants=network-online.target

[Service]
User=checkout
Group=checkout
WorkingDirectory=/opt/checkout
EnvironmentFile=-/etc/checkout/checkout.env
ExecStart=/usr/bin/java -jar /opt/checkout/checkout.jar
Restart=on-failure
RestartSec=5
SuccessExitStatus=143
TimeoutStopSec=40

[Install]
WantedBy=multi-user.target
~~~

Ví dụ này cho thấy hệ điều hành quản lý tiến trình và khởi động lại khi process lỗi. Nó **chưa tự bảo đảm** HA, resource limit, bảo mật thư mục, logging, firewall, TLS, rolling deployment hoặc kiểm soát credential. File môi trường phải được giới hạn quyền đọc; secret manager hoặc cách cấp bí mật chuyên dụng thường thích hợp hơn cho production.

Nếu chỉ có một VM, một lỗi vùng máy chủ, bản vá OS hoặc thao tác restart có thể làm dịch vụ ngừng hoàn toàn. Tính sẵn sàng phải đến từ kiến trúc nhiều instance, vùng lỗi độc lập và kiểm tra phục hồi.

### 4.2. Khi nào VM vẫn là lựa chọn hợp lý?

VM vẫn phù hợp nếu đội đã có hạ tầng tự động hóa đáng tin, ứng dụng có nhu cầu hệ điều hành đặc thù, lưu lượng tương đối ổn định, thời gian nâng cấp chấp nhận được và tổng chi phí thấp hơn lựa chọn khác sau khi **tính cả chi phí vận hành**. Không phải mọi hệ thống đều cần orchestrator phức tạp.

## 5. Container: đóng gói nhất quán nhưng vẫn cần nơi vận hành

Container image mô tả filesystem/runtime và cách khởi chạy ứng dụng. Với Docker, đội có thể build cùng một image, kiểm thử ở CI rồi chạy image đó trên nhiều môi trường.

~~~text
Source code
   |
   v
Build JAR + tests
   |
   v
Build OCI image
   |
   v
Registry (version/digest)
   |
   +-- VM chạy container
   +-- Nền tảng PaaS nhận image
   +-- Managed container service
   +-- Kubernetes cluster
   +-- Serverless container platform
~~~

**Lợi ích:**

- Image giúp giảm sai lệch do “máy dev có thư viện A, server có thư viện B”.
- Artifact có version/digest và quy trình kiểm tra bảo mật.
- Dễ tạo replica mới nếu ứng dụng stateless và phụ thuộc được quản lý bên ngoài.
- Phù hợp CI/CD, immutable deployment và tách build khỏi runtime.

**Giới hạn:**

- Container không phải VM đầy đủ; thường chia sẻ kernel host. Cô lập phụ thuộc runtime, user namespace, quyền, profile bảo mật và cấu hình host.
- Image đồng nhất không thay thế network, storage, secret distribution, LB, autoscaling, health probes và monitoring.
- Docker Compose chạy được nhiều service nhưng tự nó không mang toàn bộ các bảo đảm của một môi trường orchestration nhiều node.
- Khi image là production artifact, cần tránh tag linh động như latest trong deployment quan trọng; nên gắn digest hoặc version bất biến để biết chính xác binary nào được chạy.

### 5.1. Dockerfile minh họa cho ứng dụng Java 21

Giả sử pipeline đã build được JAR thực thi và đặt tên **checkout.jar** trong ngữ cảnh build image:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --home-dir /app appuser

COPY --chown=appuser:appgroup checkout.jar /app/checkout.jar

USER appuser
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/checkout.jar"]
~~~

Dockerfile minh họa việc chọn runtime Java, sao chép JAR và chạy dưới user không phải root. Trong sản xuất còn cần quản lý base image theo digest, quét lỗ hổng, hạn quyền filesystem, chặn capability không cần thiết, cấu hình memory của JVM theo container và không đưa secret vào image.

**EXPOSE 8080** chỉ cung cấp metadata về port dự kiến; nó không tự công khai port ra Internet. Nền tảng sẽ quyết định network, ingress và cấu hình publish thực tế.

Một image JVM vẫn có thời gian khởi động và chi phí heap/threads. Khi scale nhanh, cần đo startup, hiệu quả cache và số kết nối DB mà mỗi replica mới tạo.

### 5.2. Image bất biến và cấu hình tách riêng

Không build một image cho mỗi mật khẩu hay mỗi môi trường nếu có thể tránh. Dùng một artifact đã kiểm thử, nhận cấu hình theo cơ chế của nền tảng:

~~~text
checkout-service:1.8.2 (image digest cố định)
   |
   +-- staging: endpoint và quota staging
   +-- production: endpoint và quota production
   |
   +-- secret tham chiếu theo danh tính workload
~~~

Cấu hình quan trọng nên có phiên bản và validation; secret cần nguồn chuyên dụng. Với các thay đổi phải restart, nền tảng cần rolling deployment có kiểm soát. Khi cấu hình thay đổi lúc chạy, ứng dụng phải có cơ chế hot reload thực sự chứ không giả định thay environment variable là tiến trình sẽ tự đổi.

## 6. Managed platform và PaaS: nhận dịch vụ chạy, giảm công xây nền tảng

PaaS/managed application platform thường cung cấp một hợp đồng như “đưa code hoặc image, khai báo CPU/RAM, port, số instance, mạng và environment; nền tảng triển khai, theo dõi trạng thái và có thể mở rộng”. Những dịch vụ cụ thể có thể khác nhau đáng kể.

Các nhóm phổ biến:

- **PaaS theo source/buildpack:** nhận mã nguồn hoặc artifact và xây ứng dụng theo runtime được hỗ trợ.
- **Managed container service:** nhận image, cung cấp task/service scheduling, logging, networking và khả năng scale theo cấu hình.
- **Serverless container:** nhận image hoặc source, cấp phát instance theo request/sự kiện; có thể scale xuống rất thấp hoặc về zero tùy dịch vụ/cấu hình.
- **Managed Kubernetes:** nhà cung cấp vận hành control plane và một số dịch vụ nền, nhưng đội ngũ vẫn sở hữu phần lớn cấu hình Kubernetes và luồng triển khai của workload.
- **Managed batch/job:** chạy job có điểm kết thúc và retry/schedule theo hợp đồng riêng.

Ví dụ công nghệ có thể xuất hiện trong môi trường thực tế là Google Cloud Run, Azure Container Apps, AWS App Runner hoặc các dịch vụ container quản lý khác; Kubernetes thường được cung cấp qua GKE, EKS, AKS hoặc hạ tầng tương đương. Các tên sản phẩm là ví dụ về họ giải pháp, **không phải cam kết mọi tính năng giống nhau**. Trần thời gian request, quy tắc scale, tính phí, mạng riêng, storage và loại CPU/GPU phải được xác nhận với sản phẩm và cấu hình cụ thể.

### 6.1. Những gì đội vẫn phải quản lý

Ngay cả khi nền tảng tự tạo máy, đội ứng dụng vẫn cần:

1. Viết ứng dụng an toàn, có timeout và xử lý lỗi.
2. Chọn kích thước tài nguyên, giới hạn concurrency, min/max instances.
3. Thiết kế database, cache, queue và quyền mạng.
4. Quản lý secret, IAM/RBAC, TLS đối với những lớp mình phụ trách.
5. Định nghĩa readiness/liveness hoặc health behavior phù hợp.
6. Thiết lập alert, SLO, dashboard, tracing và log không lộ dữ liệu nhạy cảm.
7. Kiểm thử rollout, rollback và khôi phục khi phụ thuộc hỏng.
8. Theo dõi chi phí và quota của dịch vụ managed.

“Managed” có nghĩa trách nhiệm được **chia sẻ và phân định**, không có nghĩa bên cung cấp chịu mọi sự cố ứng dụng hoặc dữ liệu.

## 7. Kubernetes: sức mạnh điều phối và chi phí phức tạp

Kubernetes là nền tảng điều phối container. Nó mô tả **desired state**: cần bao nhiêu Pod, image nào, cấu hình gì, health check và network nào. Controller cố gắng đưa thực tế về trạng thái mong muốn.

~~~mermaid
flowchart TB
    CICD["CI/CD phát hành image"] --> API["Kubernetes API"]
    API --> DEP["Deployment"]
    DEP --> P1["Pod A"]
    DEP --> P2["Pod B"]
    DEP --> P3["Pod C"]
    SVC["Service"] --> P1
    SVC --> P2
    SVC --> P3
    ING["Ingress/Gateway"] --> SVC
    HPA["Horizontal Pod Autoscaler"] --> DEP
~~~

**Kubernetes hữu ích khi:**
- Có nhiều dịch vụ với quy tắc vận hành tương tự và đội platform đủ năng lực.
- Cần scheduling, rollout, sidecar, policy, autoscaling hoặc topology phân tán được cấu hình chi tiết.
- Cần tự vận hành worker, API và job bằng cùng một lớp orchestration.
- Hệ thống có yêu cầu mạng, phân vùng lỗi và tích hợp điều hành vượt khả năng nền tảng đơn giản hơn.

**Chi phí cần chấp nhận:**
- Các khái niệm như namespace, RBAC, Service, Ingress/Gateway, CNI, CSI, resource requests/limits, HPA, PDB, node pool và admission policy.
- Cần quan sát và bảo vệ control plane, worker node, registry, secret, backup/restore và GitOps/IaC.
- Cấu hình sai liveness probe hoặc autoscaler có thể gây vòng restart, tăng tải DB hoặc làm cạn node.
- Managed control plane vẫn đòi hỏi người hiểu vận hành workload, giới hạn cụm và cập nhật các thành phần phụ thuộc.

Không chọn Kubernetes chỉ vì tên “microservices”. Một đội nhỏ với ba API đơn giản có thể phát hành nhanh và ít rủi ro hơn trên managed container platform. Ngược lại, nhiều dịch vụ với yêu cầu scheduling đặc biệt có thể biện minh cho nền tảng này.

### 7.1. Deployment và Service minh họa

Ví dụ tối giản cho ứng dụng Spring Boot đã bật các actuator health endpoint và cấu hình access phù hợp:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      containers:
        - name: checkout
          image: registry.example.com/checkout@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health
              port: 8080
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: checkout-api
spec:
  selector:
    app: checkout-api
  ports:
    - port: 80
      targetPort: 8080
~~~

**Lưu ý thực thi:** chuỗi digest REPLACE_WITH_REAL_DIGEST là placeholder, không thể deploy nguyên dạng. Cấu hình actuator probes phụ thuộc ứng dụng; Spring Boot có thể cần kích hoạt probes và cấu hình đường dẫn tương ứng. Các giá trị CPU/RAM là giả định minh họa, phải hiệu chỉnh bằng thử tải thực tế. Ví dụ chưa cấu hình secret, service account, network policy, ingress, anti-affinity, topology spread, PodDisruptionBudget, HPA hay securityContext.

**Startup probe** tạo thời gian cho JVM khởi động trước khi liveness đánh giá. **Readiness probe** quyết định Pod có đủ điều kiện nhận traffic; nó không nên phụ thuộc mù vào một hệ thống ngoài khiến toàn bộ Pod đồng loạt bị loại khỏi load balancer trong sự cố ngắn. **Liveness probe** nên phát hiện tiến trình kẹt thật sự, tránh restart vì một database phụ thuộc đang chậm.

### 7.2. HPA và khả năng mở rộng thực tế

HPA có thể dùng CPU, memory hoặc metric tùy chỉnh qua các thành phần thích hợp. Khi Pod tăng, database connection pool của từng Pod cũng có thể tăng tổng số kết nối. Vì vậy:

~~~text
maxReplicas × maxDbConnectionsPerReplica
       <= ngân sách kết nối DB cấp cho dịch vụ
~~~

Đây là ràng buộc cần xem xét, không phải công thức duy nhất để chọn HPA. Khi node thiếu tài nguyên, HPA tạo Pod mới chưa chắc Pod được schedule; cần cơ chế mở rộng node hoặc capacity dự phòng theo hạ tầng.

Không tăng replica để chữa một truy vấn DB bị nghẽn nếu nút cổ chai nằm ở DB. Scale-out tầng API có thể làm downstream chịu tải cao hơn.

## 8. Serverless: cấp phát theo sự kiện, nhưng mỗi nền tảng có hợp đồng riêng

**FaaS** thường cung cấp handler nhận một sự kiện và trả kết quả. **Serverless container** thường nhận request qua HTTP hoặc sự kiện và chạy một tiến trình container với concurrency được kiểm soát. Hai mô hình có thể giảm việc quản lý server nhưng cần đặc biệt quan tâm đến giới hạn thực thi.

Ví dụ luồng xử lý ảnh:

~~~mermaid
flowchart LR
    U["Người dùng tải ảnh"] --> S[("Object Storage")]
    S --> E["Sự kiện ảnh mới"]
    E --> F["Function/Serverless Worker"]
    F --> O[("Lưu ảnh đã xử lý")]
    F --> Q[("Queue thông báo")]
~~~

**Phù hợp:**
- Tác vụ ngắn theo sự kiện, webhook, xử lý file, fan-out không yêu cầu giữ trạng thái cục bộ.
- Traffic rất biến động, có khoảng nhàn rỗi dài và cơ chế scale phù hợp.
- Đội muốn giảm việc trực ca hạ tầng và chấp nhận giới hạn của sản phẩm.
- Công việc có tính độc lập, dễ retry và dễ phân chia thành những bước idempotent.

**Cần đo và kiểm chứng:**
- **Cold start:** thời gian cấp instance/runtime, tải class/JIT/khởi tạo dependency, thiết lập kết nối.
- **Concurrency:** số request mỗi instance, số instance tối đa, độ trễ khi scale.
- **Thời gian xử lý tối đa:** mỗi dịch vụ có timeout, request lifetime và background execution policy khác nhau.
- **Memory/CPU:** cách tài nguyên được cấp, tính phí, giới hạn /tmp, có GPU hay không.
- **Network:** kết nối VPC/private network, egress, địa chỉ IP tĩnh, DNS, NAT và chi phí.
- **Storage:** filesystem cục bộ có thể là tạm thời; dữ liệu bền vững phải ở external store phù hợp.
- **Kết nối lâu:** WebSocket, streaming, consumer liên tục, scheduled task có khả năng vượt mô hình.
- **Thời gian chờ / queued event:** khi scale chậm hoặc đạt quota, request được xếp hàng, từ chối hay retry theo cơ chế nào?
- **Giới hạn tài khoản/region:** quota là ràng buộc thực tế, không đồng nghĩa “tự scale vô hạn”.
- **Khả năng kiểm thử:** môi trường cục bộ có tái hiện chính xác trigger, IAM và failure semantics hay không?

Không nên nói “serverless luôn rẻ hơn” hoặc “FaaS luôn chậm với Java”. Cần đo thời gian khởi tạo, cấu hình min instances, bộ nhớ, mức song song và mô hình giá của chính dịch vụ dự kiến sử dụng.

### 8.1. Đặc biệt với Spring Boot và JVM

Ứng dụng Spring Boot có thể chạy trong container serverless nếu nền tảng hỗ trợ tiến trình HTTP. Nhưng với FaaS, đôi khi cần handler/adapter và lifecycle phù hợp. Cold start JVM có thể chịu ảnh hưởng của class loading, autoconfiguration, JIT, kết nối DB lúc khởi động và kích thước artifact.

Các hướng cải thiện tùy nền tảng:
- Giảm khởi tạo dependency không cần thiết; tránh kết nối downstream nặng tại startup nếu không bắt buộc.
- Sử dụng health/startup readiness phù hợp với thời gian khởi động.
- Kiểm tra khả năng dùng snapshot, runtime tối ưu hoặc native image ở hệ sinh thái hỗ trợ.
- Cân nhắc **minimum warm instances** khi p99 latency yêu cầu chặt; nhưng phải tính chi phí giữ nóng.
- Giới hạn connection pool theo concurrency thực và khả năng DB, tránh tạo quá nhiều kết nối khi scale nhanh.
- Xử lý shutdown và timeout, bảo đảm ghi trạng thái công việc bền vững trước khi runtime bị dừng.

Chọn GraalVM native image chỉ khi thời gian startup và dấu chân bộ nhớ thực sự là vấn đề đáng giải quyết; native build có tradeoff về thời gian build, reflection/config, tương thích thư viện và cách debug. Cần thử trên workload cụ thể.

## 9. So sánh có điều kiện: kiểm soát, mở rộng, chi phí và vận hành

Không có thứ hạng phổ quát. Bảng sau là **xu hướng thường gặp**, không phải số liệu hiệu năng hay giá của một nhà cung cấp.

| Tiêu chí | VM | Container + điều phối tự quản | Managed platform | FaaS / serverless container |
|---|---|---|---|---|
| Quyền điều chỉnh OS/runtime | Cao | Tùy quyền host và cluster | Trung bình đến thấp | Theo giới hạn nền tảng |
| Công vận hành host/scheduler | Cao | Cao | Thấp đến trung bình | Thường thấp |
| Tạo bản chạy giống nhau | Cần chuẩn hóa image/automation | Tốt qua image bất biến | Tốt qua artifact/deploy revision | Tốt qua function/image revision |
| Scale theo biến động | Cần autoscaling/LB | Cần orchestrator/autoscaler | Tùy tính năng managed | Thường thuận tiện nếu workload phù hợp |
| Scale xuống zero | Không tự có | Cần giải pháp bổ sung | Tùy sản phẩm | Có ở nhiều dịch vụ, tùy cấu hình |
| Thời gian khởi tạo khi scale | Boot VM hoặc container | Boot/schedule container | Tùy nền tảng | Có thể có cold start |
| Workload chạy liên tục | Phù hợp | Phù hợp | Thường phù hợp | Cần phân biệt container service và function |
| Quyền network/storage tùy biến | Cao | Cao nếu sở hữu cluster | Tùy nhà cung cấp | Có nhiều giới hạn riêng |
| Loại chi phí nổi bật | VM giờ chạy, disk, LB, nhân sự | Node/cluster + network + vận hành | Compute/service + request + network | Invocation, CPU/memory-duration, tối thiểu instance, request |
| Khả năng chuyển nền tảng | Phụ thuộc OS/tooling | Image OCI hỗ trợ nhiều nơi, manifest khác nhau | API/feature có thể tạo khóa phụ thuộc | Event/handler, IAM và giới hạn runtime có thể tạo khóa phụ thuộc |

Thay vì hỏi “VM hay serverless tốt hơn?”, hãy hỏi: **trong tải dự kiến và SLO đã cam kết, phương án nào cho tổng chi phí và rủi ro chấp nhận được với năng lực đội?**

## 10. Cây quyết định thực dụng

~~~text
Dịch vụ có phụ thuộc kernel/OS/driver hoặc phần cứng đặc biệt?
    |
    +-- Có --> Bắt đầu với VM hoặc nền tảng container hỗ trợ quyền/tài nguyên đó.
    |
    +-- Không
         |
         +-- Cần giữ kết nối hoặc tiến trình liên tục rất lâu?
         |       |
         |       +-- Có --> Managed container/service, Kubernetes hoặc VM.
         |       |
         |       +-- Không
         |            |
         |            +-- Tải theo sự kiện, ngắn và nhiều thời gian nhàn rỗi?
         |            |      |
         |            |      +-- Có --> Thử FaaS hoặc serverless job/container.
         |            |      |
         |            |      +-- Không --> Thử managed HTTP container/PaaS.
         |
         +-- Nhiều workload cần scheduling/policy đặc thù và có đội platform?
                |
                +-- Có --> Đánh giá managed Kubernetes.
                +-- Không --> Ưu tiên nền tảng vận hành đơn giản hơn.
~~~

Cây này chỉ **rút ngắn danh sách ứng viên**. Sau đó cần thử tải, kiểm tra mạng/bảo mật, khả năng phục hồi và tính toán tổng chi phí. Ví dụ serverless phù hợp sự kiện ngắn nhưng không đạt điều kiện mạng riêng; lúc đó một managed container service có kết nối VPC có thể thích hợp hơn.

## 11. Stateless, stateful và bài toán lưu trữ

**Stateless service** nghĩa là trạng thái cần giữ lâu dài không phụ thuộc duy nhất vào một instance đang chạy. Một instance có thể bị thay thế mà không mất dữ liệu nghiệp vụ.

~~~text
Client -> Load Balancer -> Replica A / Replica B / Replica C
                                   |
                          Shared DB + Cache + Broker
~~~

Để scale và rolling deployment thuận lợi:

- Không ghi file nghiệp vụ quan trọng vào filesystem tạm của Pod/function.
- Dùng cơ sở dữ liệu hoặc object storage bền vững có backup.
- Phiên đăng nhập lưu ở token/session store phù hợp, tránh chỉ nằm trong RAM một replica.
- Job cần ghi checkpoint và trạng thái xử lý nếu có thể bị dừng.
- Cache cục bộ có thể mất khi instance thay; nó phải là tối ưu hiệu năng, không là nguồn dữ liệu duy nhất.
- Ứng dụng phải xử lý graceful shutdown, request đang chạy và thông điệp chưa ACK.

**Stateful workload** như database, broker hoặc storage đòi hỏi tính bền vững, quorum, replica placement, backup/restore và xử lý split-brain. Kubernetes có StatefulSet/PersistentVolume nhưng bản thân việc khai báo resource không thay thế thiết kế consistency và phục hồi dữ liệu. Trong nhiều trường hợp, managed database/broker phù hợp hơn tự vận hành stateful core trên cùng cluster ứng dụng.

Quyết định “đưa database lên Kubernetes” là một quyết định độc lập với “ứng dụng API chạy Kubernetes”, cần đánh giá năng lực vận hành lưu trữ và tiêu chuẩn khôi phục.

## 12. Ràng buộc độ trễ và thời gian khởi động

**Latency của một request** gồm thời gian chờ nhận, queue, xử lý, mạng và downstream. Trong serverless hoặc autoscaling mạnh, có thể có thêm thời gian khởi tạo instance.

~~~text
Thời gian phản hồi =
  đợi được tiếp nhận
  + (khởi tạo runtime nếu cần)
  + đợi tài nguyên/DB
  + xử lý nghiệp vụ
  + truyền dữ liệu
~~~

Giả sử mục tiêu p95 = 200 ms. Nếu cold start thêm hàng giây cho một tỷ lệ đủ lớn request, mục tiêu không thể đạt chỉ bằng tối ưu logic bên trong handler. Các lựa chọn có thể là giữ một số instance ấm, chuyển sang managed container chạy liên tục, giảm thời gian startup hoặc điều chỉnh kiến trúc async.

**Phải đo p95/p99**, không chỉ trung bình. Hệ thống có thể có 99% request nhanh nhưng 1% chậm vì scale, network hoặc JVM GC. Độ trễ cũng phụ thuộc:
- Vị trí ứng dụng so với DB và dịch vụ ngoài.
- Kích thước connection pool và số kết nối được tạo lúc scale.
- CPU throttling, memory limit, GC pauses.
- Cơ chế LB/retry và số lần chuyển tiếp mạng.
- Vùng lỗi hoặc region của nhà cung cấp.

Đặt số instance tối thiểu theo SLO là một lựa chọn kỹ thuật hợp lệ, nhưng nó làm thay đổi mô hình chi phí của serverless. Cần đo lại điểm hòa vốn.

## 13. Tăng giảm quy mô và bảo vệ tài nguyên phía sau

Mở rộng có hai hướng:

- **Vertical scaling:** tăng CPU/RAM/IOPS cho một instance. Giới hạn bởi cỡ máy, chi phí và đôi khi downtime.
- **Horizontal scaling:** tăng số instance xử lý. Cần ứng dụng stateless hoặc phân chia trạng thái tốt, load balancing và nguồn phụ thuộc chịu tải.
- **Event-driven scaling:** điều chỉnh số consumer/worker dựa trên queue depth, oldest message age hoặc lag; cần tránh làm broker/DB bị nghẽn.

Một quy tắc ngân sách quan trọng:

~~~text
Tổng DB connections có thể mở
  = số replica tối đa × số connection mỗi replica
    + connection của job, admin, service khác
~~~

Nếu database cho ứng dụng tối đa 300 kết nối và mỗi instance giữ 40, autoscaler từ 4 lên 12 replica có thể yêu cầu tới 480 kết nối chỉ riêng dịch vụ này. Scale thành công ở tầng compute nhưng làm thất bại ở tầng dữ liệu. Cần quản lý pool, proxy, giới hạn tổng và backpressure.

**Autoscaling không chữa nút cổ chai bằng phép màu.** Tăng replica khi DB đã quá tải có thể khiến timeout tăng nhanh. Giới hạn concurrency, rate limiting và load shedding vẫn cần thiết.

### 13.1. Chọn tín hiệu scale

| Workload | Metric gợi ý | Điểm cần kiểm chứng |
|---|---|---|
| API CPU-bound | CPU utilization, RPS/replica | CPU có phản ánh tải thực không? |
| API I/O-bound | In-flight requests, latency, pool wait | CPU thấp không có nghĩa dư năng lực |
| Queue worker | Queue age, backlog/replica, lag | Có đủ thời gian xử lý trước deadline không? |
| Function | Invocation rate, concurrent executions, throttle | Có chạm quota hoặc cold start không? |
| Batch job | Số job chờ, thời gian hoàn thành | Có làm nghẽn storage/DB chung không? |

Nên có giới hạn **min/max**, cooldown, hành vi khi metric mất, và cơ chế giảm dao động khi tải thay đổi liên tục.

## 14. Chi phí: tính cả compute, mạng, lưu trữ và nhân sự

**Tổng chi phí sở hữu (TCO)** không chỉ là giá CPU/RAM. Một mô hình cần kể đến:

~~~text
TCO =
  compute đang chạy
  + lưu trữ / backup / registry / log / metrics
  + load balancer / NAT / egress / truyền dữ liệu giữa vùng
  + dịch vụ hỗ trợ / control plane / quota
  + công vận hành / bảo mật / nâng cấp / ứng phó sự cố
  + dự phòng cho HA và disaster recovery
~~~

Các đơn vị tính giá thường khác:

- VM: instance theo thời gian chạy, disk và network; tải nhàn rỗi vẫn có thể trả compute.
- Container trên node tự quản: trả tiền node/cụm và các dịch vụ hỗ trợ dù ít Pod đang chạy.
- PaaS/managed container: có thể tính theo CPU/RAM cấp phát, thời gian active, instance tối thiểu, request và mạng.
- FaaS: thường tính invocation cùng thời lượng/tài nguyên, nhưng min capacity, lưu trữ, egress hoặc mạng riêng có thể làm chi phí tăng.

**Ví dụ tính tư duy, không phải báo giá:** Một API chạy 24/7 có lưu lượng đều có thể tận dụng VM/container được cấp phát ổn định. Cùng ứng dụng chỉ nhận 10 phút traffic mỗi ngày có thể có lợi khi dùng mô hình theo request nếu cold start và giới hạn thời gian phù hợp. Nhưng nếu cần giữ một instance ấm liên tục và mọi request đi qua NAT đắt, chi phí serverless thực tế có thể không thấp.

### 14.1. Bài toán minh họa theo biến

Đặt:

- **H** = số giờ trong kỳ tính phí.
- **C_vm** = chi phí compute VM cho một giờ.
- **C_fixed** = chi phí hạ tầng hỗ trợ và dự phòng của phương án VM.
- **N** = tổng số request trong kỳ.
- **D** = tổng thời lượng xử lý đã quy đổi theo đơn vị tính phí của nền tảng.
- **C_req** = chi phí mỗi request.
- **C_dur** = chi phí mỗi đơn vị thời lượng/tài nguyên.
- **C_min** = chi phí giữ instance tối thiểu, network và các khoản cố định khác của phương án serverless.

Khi đó:

~~~text
Cost_VM ≈ H × C_vm + C_fixed
Cost_Serverless ≈ N × C_req + D × C_dur + C_min
~~~

Các công thức là mô hình sơ bộ: giá thực tế còn phụ thuộc vùng, lớp tài nguyên, thời gian làm tròn, free tier, lưu lượng ra ngoài, disk, reservations, concurrency và thỏa thuận. Chỉ dùng chúng để lập giả thuyết rồi điền số đo tải và bảng giá hiện hành của nhà cung cấp.

Để quyết định, tính **hai kịch bản**: bình thường và đỉnh, thêm kịch bản tăng trưởng cùng chi phí khi một vùng lỗi cần chuyển tải. Đừng chọn serverless chỉ dựa trên một ngày traffic thấp hoặc VM chỉ dựa trên giá một instance.

## 15. Độ tin cậy: mô hình triển khai không tự tạo khả năng chịu lỗi

Dù dùng VM, container hay serverless, hệ thống vẫn có phụ thuộc bên ngoài: database, cache, message broker, hệ thống thanh toán, DNS hoặc IAM. Nếu phụ thuộc chính thất bại, việc tạo nhiều bản ứng dụng không bảo đảm phục vụ được request.

Các thành phần của thiết kế chịu lỗi:

1. **Nhiều vùng lỗi:** replica ở các zone/nút khác nhau nếu SLO và nền tảng hỗ trợ.
2. **Health và readiness:** chỉ đưa traffic tới instance sẵn sàng; phân biệt sống với có thể phục vụ.
3. **Giới hạn tài nguyên:** tránh một instance chiếm hết memory/CPU hoặc mở quá nhiều kết nối.
4. **Timeout, retry budget và circuit breaker:** bảo vệ downstream; retry có backoff và jitter.
5. **Idempotency:** xử lý an toàn khi retry, redelivery và sự kiện duplicate.
6. **Graceful shutdown:** ngừng nhận mới, xử lý công việc đang chạy theo deadline, đóng kết nối.
7. **Backup và restore drill:** dữ liệu cần được khôi phục thử, không chỉ dựa trên việc có snapshot.
8. **RPO/RTO:** xác định mức mất dữ liệu và thời gian khôi phục chấp nhận được.
9. **SLO và alert:** dựa trên kết quả người dùng nhận, không chỉ CPU của platform.
10. **Canary/rollback:** giảm phạm vi ảnh hưởng của bản build hoặc cấu hình lỗi.

**Multi-zone** giúp chống một số loại lỗi hạ tầng, nhưng không tự chữa lỗi code được phát cùng lúc cho mọi instance hay lỗi schema DB phá vỡ tương thích. Cần tách kế hoạch khôi phục ứng dụng, dữ liệu và phụ thuộc.

## 16. Triển khai phiên bản: rolling, blue/green và canary

Hình thức rollout có thể tồn tại trên nhiều nền tảng, nhưng mức tự động hóa và quyền điều khiển khác nhau.

| Chiến lược | Cách hoạt động | Lợi ích | Điều phải chuẩn bị |
|---|---|---|---|
| **Recreate / stop-start** | Dừng bản cũ rồi chạy bản mới | Đơn giản | Có thể có downtime |
| **Rolling** | Thay dần replica cũ bằng mới | Giảm gián đoạn | Tương thích giữa phiên bản, readiness tốt |
| **Blue/green** | Duy trì hai môi trường/bộ replica, đổi routing | Chuyển đổi và quay lại nhanh với ứng dụng stateless | Chi phí chạy song song, migration dữ liệu |
| **Canary** | Phát bản mới cho một phần nhỏ traffic | Quan sát lỗi trước khi mở rộng | Routing theo cohort, guardrail, quan sát riêng |
| **Feature flag** | Code đã triển khai nhưng bật chức năng theo điều kiện | Giảm rủi ro cho nhánh chức năng | Kiểm soát flag, rollback side effect |

Một pipeline tối thiểu:

~~~text
Build -> Unit/Integration Tests -> Image Scan
    -> Publish immutable artifact
    -> Deploy staging -> Smoke tests
    -> Deploy canary -> Check SLO/guardrails
    -> Progressive rollout
    -> Verify effective version
    -> Finish or rollback
~~~

Rollback ứng dụng về image cũ không tự rollback DB schema, message đã gửi hoặc secret đã thu hồi. Khi cần thay đổi schema, áp dụng cách **expand → migrate → contract** và kiểm tra các bản ứng dụng có thể cùng tồn tại.

### 16.1. Với serverless revision

Một số nền tảng hỗ trợ traffic splitting giữa các revision. Khi đó, canary có thể đơn giản về mặt điều phối, nhưng vẫn cần đo side effects và xử lý các request/job đã bắt đầu trên revision lỗi. Với FaaS theo sự kiện, nguồn sự kiện và retry policy có thể khiến một event được chạy lại nhiều lần; rollback handler phải xét payload mới đã được lưu trong queue.

### 16.2. Với VM tự quản

Có thể triển khai blue/green ở tầng load balancer hoặc nhóm VM. Cần đảm bảo nhóm mới thật sự healthy trước khi chuyển traffic; nhóm cũ chỉ được tắt sau khi hoàn thành drain hoặc đạt deadline. Ghi lại image/AMI, JAR version và cấu hình để có thể khôi phục có chứng cứ.

## 17. Quan sát và vận hành sau triển khai

Một nền tảng quản lý có dashboard không có nghĩa hệ thống đã có observability đầy đủ. Cần biết **dịch vụ nào, phiên bản nào, ở đâu, vì sao lỗi, và người dùng chịu tác động gì**.

| Lớp quan sát | Dữ liệu gợi ý | Vấn đề phát hiện |
|---|---|---|
| Traffic | RPS, concurrency, request size, tỷ lệ 4xx/5xx | Tăng tải, bị giới hạn, lỗi hành vi |
| Trải nghiệm | Latency p50/p95/p99, success rate, SLO burn | Chất lượng phục vụ |
| Tài nguyên | CPU, RSS/heap, GC pause, thread, disk, network | Throttle, OOM, cạn tài nguyên |
| Kết nối | DB pool in-use/wait, downstream timeout, DNS | Nút cổ chai phụ thuộc |
| Nền tảng | Instance count, scale event, startup time, restart count | Lỗi scale/schedule/cold start |
| Container | OOMKilled, readiness failure, image pull error | Vấn đề rollout và runtime |
| Hàng đợi | Lag, oldest message age, retry, DLQ | Worker chậm hoặc poison message |
| Phát hành | Artifact digest, revision, config version | Drift, rollback không hoàn tất |
| Chi phí | Chi phí theo service/namespace/tenant | Tăng chi phí bất thường |

Gắn **service.name, environment, version** nhất quán vào trace và log; bảo vệ dữ liệu nhạy cảm. Với nhiều replica, quan sát theo phiên bản và cohort giúp thấy bản canary lỗi dù metric toàn cụm bị pha loãng.

Nên giữ một lối chẩn đoán khi hạ tầng chính lỗi: ví dụ metrics/log forwarding và quy trình tra cứu không phụ thuộc hoàn toàn vào ứng dụng đang hỏng. Sự cố nền tảng có thể làm cả cơ chế log tập trung chậm, nên cần biết tín hiệu nào còn đáng tin.

## 18. Bảo mật và trách nhiệm chia sẻ

Thay đổi mô hình triển khai **không xóa trách nhiệm bảo mật của ứng dụng**.

### 18.1. Các lớp cần kiểm soát

- **Danh tính workload:** VM role, service account hoặc identity của function; không nhúng credential dài hạn vào source/image.
- **Quyền tối thiểu:** API chỉ được đọc secret và truy cập DB cần thiết; worker khác quyền API nếu trách nhiệm khác.
- **Network:** private endpoint, firewall/security group, network policy, ingress và egress; không mặc định tất cả service trong nội bộ đều đáng tin.
- **TLS:** xác thực chứng chỉ server, mã hóa đường truyền; bảo vệ key và rotation.
- **Image/supply chain:** quét dependencies/base image, cố định artifact, hạn chế quyền registry, theo dõi SBOM khi cần.
- **Runtime:** chạy non-root khi có thể, filesystem chỉ đọc khi phù hợp, giới hạn capability, seccomp/profile theo nền tảng.
- **Secret:** cấp phát từ secret manager, xoay vòng và thu hồi; không ghi secret trong log hoặc container image.
- **Audit:** ai đã triển khai, đổi config, thay quyền, truy cập production và rollback.
- **Backup:** mã hóa, hạn quyền, thử restore và xóa dữ liệu theo chính sách.

### 18.2. Khác biệt trách nhiệm

Trong VM, đội quản lý patch hệ điều hành khách và nhiều cổng mạng. Trong Kubernetes, đội phải bảo vệ namespace/RBAC và workload dù control plane được quản lý. Trong serverless, đội thường không patch host nhưng vẫn chịu trách nhiệm **mã nguồn, IAM, dữ liệu, package, trigger, cấu hình timeout và secret**.

Một function có quyền đọc mọi bucket vẫn nguy hiểm nếu handler bị khai thác. Một container chạy dưới user không phải root cũng không an toàn nếu service account có quyền xóa mọi database.

## 19. Kết nối riêng, dữ liệu theo vùng và chi phí mạng

Tính khả thi về mạng có thể quyết định nền tảng trước cả CPU hoặc giá compute.

Ví dụ yêu cầu:
- API chỉ kết nối DB qua private IP.
- Dữ liệu không được đi ra khỏi một region đã được phê duyệt.
- Một hệ thống đối tác chỉ cho phép IP egress đã đưa vào allowlist.
- Service cần kết nối broker bằng giao thức TCP lâu dài.
- Log và backup phải ở vùng địa lý cụ thể.

Phải kiểm tra cụ thể nền tảng có hỗ trợ ingress private, outbound VPC, NAT, private link, IP egress cố định, giao thức cần thiết và cách kết nối xuyên vùng không. Serverless function có thể cần adapter/kết nối mạng riêng; điều này có thể tăng độ trễ, cold start hoặc chi phí.

**Cùng một region** chưa chắc là cùng một zone; **cùng một cloud** chưa chắc truyền dữ liệu miễn phí. Chi phí egress, NAT, inter-zone và private connectivity có thể làm thay đổi kết quả so sánh TCO.

Việc đặt API gần người dùng nhưng xa database có thể làm tăng tổng latency. Quyết định vùng đặt compute cần đi cùng vị trí dữ liệu, chính sách tuân thủ và mô hình phụ thuộc.

## 20. Java/Spring Boot: tiêu chí triển khai đặc thù

Một ứng dụng Java/Spring Boot cần xem xét:

1. **Version JDK:** runtime phù hợp với mã đã biên dịch; image/VM phải có bản JDK/JRE tương thích.
2. **Heap và container memory:** heap chỉ là một phần RSS; còn metaspace, thread stacks, direct buffers và native allocations.
3. **Thời gian startup:** ảnh hưởng rolling deploy, readiness và serverless cold start.
4. **Garbage collection:** ảnh hưởng p99 latency; cần đo dưới giới hạn CPU/RAM của môi trường thật.
5. **Connection pool:** mỗi replica có pool riêng; tổng connection tăng theo scale-out.
6. **Actuator health/probes:** phân biệt startup, readiness và liveness; không đưa endpoint nhạy cảm ra Internet.
7. **Graceful shutdown:** cho request in-flight hoàn tất trong ngân sách và đóng consumer/connection đúng cách.
8. **Config/secret:** tách cấu hình khỏi artifact, tránh refresh sai lifecycle của bean.
9. **Trace/log:** gắn trace context xuyên HTTP và message broker.
10. **JAR hay native image:** đánh đổi build time, startup, footprint, khả năng debug và compatibility.

### 20.1. Tính tài nguyên JVM từ phép đo

Giả sử một replica dùng:
- Heap thực khoảng 550 MiB.
- Metaspace + native/thread/direct buffer tổng khoảng 200 MiB ở đỉnh.
- Biên dự phòng theo tải/GC khoảng 200 MiB.

Giới hạn memory 600 MiB sẽ có nguy cơ OOM dù heap dưới 600 MiB. Đặt limit cần dựa trên **RSS/peak thực** và profile tải; tránh coi Xmx là toàn bộ bộ nhớ process. Tương tự, CPU limit quá thấp có thể làm chậm JVM startup/JIT và khiến autoscaler phản ứng muộn.

Con số trên là ví dụ học tập, không phải cấu hình mặc định cho Spring Boot.

### 20.2. Health check thực tế

- **Startup:** ứng dụng hoàn tất khởi tạo cần thiết chưa?
- **Readiness:** có thể nhận công việc mới không? Ví dụ chưa tải được cấu hình bắt buộc thì chưa nên nhận.
- **Liveness:** tiến trình còn có thể phục hồi không? Không nên restart vô hạn chỉ vì DB tạm mất kết nối.

Một nền tảng có thể dùng tín hiệu khác tên, nhưng mục tiêu vẫn là bảo vệ traffic và tránh vòng restart.

## 21. Producer/consumer và cron job: không dùng cùng mẫu deploy cho mọi thứ

Một microservices system có API đồng bộ và worker bất đồng bộ. Nếu dùng một deployment chung, scale API vì RPS cao có thể kéo theo nhiều consumer hơn cần thiết, tăng số kết nối DB hoặc làm đảo consumer group.

Thiết kế nên tách:

~~~text
Checkout HTTP API
  - scale theo request/concurrency
  - deadline HTTP
  - replica nhiều zone

Order event consumer
  - scale theo partitions/lag/age
  - retry và idempotency
  - consumer group và graceful rebalance

Nightly reconciliation job
  - chạy theo lịch
  - có checkpoint
  - khóa chống chạy trùng nếu nghiệp vụ yêu cầu
~~~

Trên Kubernetes có thể dùng Deployment cho API/worker và Job/CronJob cho tác vụ hoàn tất. Nền tảng managed thường có service và job khác nhau. FaaS phù hợp nếu nguồn trigger, thời gian xử lý và retry semantics tương thích.

**Không dùng một HTTP function tạm thời để chạy công việc nền kéo dài nếu nền tảng không cam kết CPU tiếp tục được cấp sau khi phản hồi.** Tách công việc dài qua queue/job runner đáng tin, lưu trạng thái và trả kết quả bất đồng bộ khi hợp đồng API cho phép.

Với consumer Kafka, khả năng scale tối đa theo số partition hữu ích cho một consumer group; vượt số partition có thể tạo consumer nhàn rỗi. Việc tăng giảm replica gây rebalance, nên phải kiểm thử thời gian gián đoạn, commit offset và xử lý lại.

## 22. Di chuyển giữa các mô hình: tránh gắn chặt nghiệp vụ với nền tảng

Một đường phát triển thường gặp:

~~~text
Một VM + JAR
    |
    v
VM có load balancer + automation
    |
    v
Container image + managed container service
    |
    +----> Managed Kubernetes khi nhu cầu điều phối tăng
    |
    +----> Serverless container cho API phù hợp
    |
    +----> FaaS/job runner cho một số tác vụ theo sự kiện
~~~

Không có nghĩa mọi hệ thống phải đi theo chuỗi này. Có ứng dụng bắt đầu với serverless là tốt nhất; có ứng dụng giữ VM lâu dài vì ràng buộc OS.

Để giảm khó khăn khi chuyển đổi:
- Phân tách code nghiệp vụ khỏi adapter chạy trên nền tảng.
- Dùng external database/queue/storage với hợp đồng rõ, không dựa vào local filesystem bền vững.
- Cấu hình từ môi trường và secret manager, không hardcode IP nội bộ.
- Có Dockerfile hoặc build artifact tái lập, không sửa binary trên server.
- Có health check, graceful shutdown và log/metrics độc lập nơi chạy.
- Định nghĩa CI/CD, IaC, rollback và resource policies thành mã cấu hình có version.
- Tránh dùng dịch vụ chỉ có trên một nền tảng cho logic cốt lõi nếu yêu cầu chuyển đổi thực sự cao; nhưng không loại bỏ managed service có lợi chỉ vì lo ngại phụ thuộc giả định.

**Tính di động có mức độ.** Image OCI có thể di chuyển nhiều nơi nhưng cấu hình mạng, IAM, lưu trữ, trigger, autoscaler và logging vẫn khác. Cần chọn phần nào nên trừu tượng hóa dựa trên khả năng sẽ phải di chuyển và chi phí bảo trì trừu tượng đó.

## 23. Tình huống A: hệ thống đặt hàng lưu lượng đều

**Bối cảnh:** API Checkout xử lý liên tục suốt ngày, nhiều request gọi DB và Payment Service, SLO p95 chặt. Đội có kỹ năng Java và ít nhân sự trực hạ tầng.

**Ứng viên:** VM nhiều replica sau LB; managed container/PaaS; managed Kubernetes; serverless container giữ một số instance tối thiểu.

**Đánh giá:**
- VM có thể hợp lý nếu công ty đã có automation, monitoring và quy trình patch OS tốt.
- Managed container/PaaS giảm khối lượng vận hành host, phù hợp đội nhỏ; vẫn cần giới hạn DB pool và timeout.
- Kubernetes đem lại khả năng điều phối sâu nhưng có thể làm tăng độ phức tạp so với nhu cầu thực.
- Serverless container có thể phù hợp nếu thời gian startup, chi phí giữ nóng, private network và concurrency đáp ứng SLO.

**Cách quyết định:** chạy thử cùng image với workload mô phỏng traffic thật, đo p95/p99, connection pool, cost và thời gian phục hồi sau kill instance. Ghi rõ điều gì khác biệt ở vận hành, không chỉ so RPS tối đa.

### 23.1. Phép thử khởi đầu

~~~text
Load test:
  20 RPS baseline trong 30 phút
  200 RPS peak trong 10 phút
  1 lần cố ý dừng 1 instance
  1 lần làm chậm Payment Service
  đo p95/p99, error rate, CPU/RSS,
      DB pool wait, startup, scale lag

Acceptance:
  theo SLO, retry budget, ngân sách
  kết nối DB và thời gian phục hồi đã duyệt
~~~

Giá trị trên là ví dụ kịch bản; ngưỡng thật phải dựa vào mục tiêu nghiệp vụ.

## 24. Tình huống B: xử lý ảnh đột biến theo sự kiện

**Bối cảnh:** Có những ngày chỉ 100 ảnh nhưng sau một chiến dịch quảng cáo có 100.000 ảnh trong vài giờ. Mỗi ảnh xử lý dưới một phút, tác vụ độc lập và kết quả lưu object storage.

**Ứng viên:** VM worker luôn bật, container job/queue consumer, serverless function hoặc managed event-driven worker.

**Điểm thuận lợi cho serverless:** ít traffic thì không cần giữ nhiều worker; burst có thể được phân tán theo sự kiện nếu quota và downstream chịu được.

**Điều phải bảo vệ:**
- Event có thể bị giao trùng; mỗi ảnh cần idempotency key.
- Giới hạn concurrency để không làm nghẽn object storage, DB metadata và dịch vụ ML.
- Đặt timeout, memory và /tmp theo kích thước file thực.
- Kiểm soát chi phí retry, lỗi phân tích file độc hại và DLQ.
- Có checkpoint hoặc chia tác vụ nếu thời gian xử lý vượt giới hạn function.
- Thử burst lớn và quota, không mặc định nền tảng tự mở vô hạn.

Một nền tảng serverless có thể giảm công vận hành nhưng vẫn cần thiết kế điều tiết tải và an toàn dữ liệu.

## 25. Tình huống C: consumer Kafka chạy liên tục

**Bối cảnh:** Inventory Service giữ consumer group Kafka 24/7, mỗi partition có thứ tự cần tôn trọng. Mỗi event cập nhật tồn kho trong DB.

**Ứng viên ban đầu:** managed container service, Kubernetes Deployment hoặc VM vận hành tốt; một hệ thống event-driven serverless chỉ phù hợp nếu connector/trigger và semantics tương thích rõ.

**Ràng buộc:**
- Consumer duy trì kết nối và heartbeat theo protocol.
- Số replica hữu ích liên quan số partition.
- Scale/restart gây rebalance và có thể redeliver.
- Offset commit phải phù hợp với mốc ghi DB.
- Sự kiện có thể trùng; handler cần idempotent.
- Kết nối DB và tốc độ consumer phải được giới hạn.
- Cần theo dõi lag, queue age, retry, DLQ và graceful shutdown.

Nếu chỉ có 6 partition và 30 replica cùng group, nhiều replica không nhận partition nào. Thêm Pod không tự nâng thông lượng khi DB là nút cổ chai. Mô hình triển khai tốt là mô hình cho phép quản lý consumer lifecycle và quan sát chính xác, không chỉ khởi tạo được container.

## 26. Tình huống D: ứng dụng phụ thuộc phần mềm hệ điều hành đặc biệt

**Bối cảnh:** Một hệ thống phân tích yêu cầu thư viện native chỉ hỗ trợ trên một bản Linux cụ thể và cần driver GPU được kiểm soát chặt.

Nếu PaaS không cung cấp runtime đó, VM hoặc managed GPU container platform hỗ trợ driver có thể phù hợp hơn. Cần kiểm tra:
- Tương thích kernel, driver và thư viện.
- Cơ chế patch và phát hành image có thể tái lập.
- Cách cấp GPU giữa nhiều workload, memory và quota.
- Bảo mật thiết bị và quyền container.
- Chi phí compute khi GPU nhàn rỗi.
- Khả năng phục hồi khi node GPU lỗi và thời gian cấp GPU thay thế.

“Container hóa được” không đồng nghĩa tất cả serverless container đều có quyền truy cập GPU/driver cần thiết. Nên xác minh sản phẩm dự kiến hỗ trợ workload trước khi đầu tư chuyển đổi.

## 27. Thiết kế bằng chứng trước khi quyết định

Một proof of concept nên trả lời những câu hỏi rõ ràng:

| Hạng mục | Cách kiểm chứng | Tiêu chí quyết định |
|---|---|---|
| Tính tương thích | Chạy artifact và dependency thật | Các chức năng bắt buộc hoạt động |
| Độ trễ | Load test ở baseline/peak/burst | p95/p99 trong SLO |
| Scale | Tăng từ min lên max, đo lag | Đạt thông lượng trước deadline |
| Khôi phục | Kill replica, ngắt zone giả lập nếu có thể | Tự phục hồi trong RTO |
| Downstream | Làm chậm DB/API, test backpressure | Không tạo retry storm |
| Bảo mật | Kiểm tra IAM, network, secret, registry | Quyền tối thiểu, không lộ dữ liệu |
| Triển khai | Canary, rollback, version drift | Không hỏng hợp đồng và có trace |
| Vận hành | Diễn tập log/alert, on-call, patch | Đội đủ khả năng chẩn đoán |
| TCO | Dùng số đo resource/traffic và chi phí vận hành | Phù hợp ngân sách theo kịch bản |
| Ràng buộc | Region, data residency, policy | Đáp ứng yêu cầu bắt buộc |

Không cần xây toàn bộ production để làm PoC, nhưng phải dùng **cùng kiểu workload**, serializer/network/DB gần thực tế và tiêu chí chấp nhận đo được. Một hello-world function phản hồi nhanh chưa chứng minh một Spring Boot API dùng DB sẽ đạt p99 tương tự.

## 28. Mẫu bảng quyết định kiến trúc (ADR)

Sau PoC, ghi lại quyết định để người mới hiểu được bối cảnh:

~~~markdown
# ADR: Mô hình triển khai Checkout API

## Bối cảnh
- Java 21 / Spring Boot API
- Traffic ổn định, p95 SLO đã xác định
- Đội platform nhỏ, cần private DB networking
- Chấp nhận triển khai rolling và scale-out

## Các phương án
1. VM + load balancer
2. Managed container/PaaS
3. Managed Kubernetes
4. Serverless container

## Tiêu chí
- Đạt SLO ở baseline, peak và khi hỏng một replica
- Bảo đảm private connectivity và quyền tối thiểu
- Có canary, rollback và khả năng quan sát
- Chi phí theo tải thực và năng lực vận hành

## Quyết định
- [Ghi phương án được chọn sau phép đo]
- [Ghi cấu hình tài nguyên, vùng lỗi và giới hạn]

## Hệ quả
- [Cái gì đơn giản hơn]
- [Chi phí và ràng buộc chấp nhận]
- [Điều kiện cần xem xét lại quyết định]
~~~

Trong bài, các ô vuông là trường của **mẫu học tập**; quyết định thực tế chỉ được điền sau khi có bằng chứng. ADR không nên biến thành tài liệu quảng bá một nền tảng; cần ghi cả lựa chọn đã cân nhắc và điều kiện thay đổi trong tương lai.

## 29. Kế hoạch kiểm thử trước khi chuyển môi trường

Một kế hoạch triển khai mới phải kiểm tra cả lớp ứng dụng và hạ tầng:

### 29.1. Kiểm thử chức năng
- API/consumer thực thi nghiệp vụ đúng và giữ hợp đồng.
- Database, broker, cache và external API kết nối qua đường mạng dự kiến.
- Biến môi trường và secret được cấp đúng, không bị log.
- Timezone, locale, encoding và filesystem behavior phù hợp.

### 29.2. Kiểm thử hiệu năng
- Startup/cold start và readiness.
- Baseline/peak/burst load, p95/p99, error rate.
- CPU/memory/GC và giới hạn tài nguyên.
- Kết nối DB, thread pool và timeout downstream.
- Scale-out/scale-in, khả năng giữ kết nối và tác vụ khi drain.

### 29.3. Kiểm thử chịu lỗi
- Dừng một instance hoặc Pod đột ngột.
- Thử rolling restart và deployment rollback.
- Làm chậm database hoặc broker; đo retry/throttle.
- Mất truy cập config/secret manager tạm thời.
- Phát lại message, xử lý duplicate và kiểm tra DLQ.
- Khôi phục backup và kiểm tra RPO/RTO khi có dữ liệu bền vững.

### 29.4. Kiểm thử bảo mật và vận hành
- Workload identity không có quyền ngoài phạm vi.
- Network chỉ mở inbound/outbound cần dùng.
- Log/trace không chứa token, PII hoặc thông điệp bí mật.
- Runtime/image có quy trình cập nhật bảo mật.
- CI/CD deploy bằng danh tính giới hạn quyền.
- Giám sát chi phí, quota và cảnh báo tài nguyên.
- Diễn tập truy vết phiên bản và rollback dưới áp lực sự cố.

Không cần viết test mô phỏng lại chính manifest mà không kiểm chứng hành vi. Ưu tiên những phép thử mà kết quả có thể thay đổi quyết định: downtime thật khi rollout, khả năng DB chịu scale, cold start ở p99 và phục hồi khi node bị mất.

## 30. Những ngộ nhận phổ biến

1. **“Dùng container là không cần quản lý server.”** Container vẫn cần host, network, storage, runtime bảo mật và nơi điều phối.
2. **“Kubernetes luôn là chuẩn bắt buộc cho microservices.”** Đó là một lựa chọn orchestration, có chi phí học và vận hành; nhu cầu hệ thống quyết định.
3. **“Managed nghĩa là không cần DevOps.”** Đội vẫn chịu trách nhiệm deployment policy, IAM, dữ liệu, metrics, SLO, secret và ứng phó lỗi ứng dụng.
4. **“Serverless luôn scale không giới hạn.”** Quota, downstream, cold start, max concurrency và rate limits tạo trần thực tế.
5. **“Serverless luôn rẻ khi ít request.”** Min instances, NAT, log, egress và thời gian xử lý có thể thay đổi chi phí.
6. **“VM không phù hợp hệ thống hiện đại.”** VM với automation, HA và giám sát tốt vẫn là lựa chọn hợp lệ.
7. **“Một image chạy được ở mọi môi trường nên di chuyển miễn phí.”** Network, IAM, storage và ingress thường khác.
8. **“Tăng replica thì hệ thống sẽ nhanh hơn.”** Nếu nghẽn DB hoặc broker, replica nhiều hơn có thể làm tình hình xấu đi.
9. **“Liveness gọi DB cho chắc.”** Khi DB lỗi, hàng loạt instance có thể bị restart vô ích.
10. **“Cài nhiều instance là đã HA.”** Nếu cùng node/zone, cùng secret sai, cùng DB đơn điểm lỗi thì phạm vi sự cố vẫn lớn.
11. **“Rollback image là khôi phục hoàn toàn.”** DB migration, message và side effect vẫn cần kế hoạch riêng.
12. **“Chỉ cần nhìn giá CPU để so TCO.”** Cần cộng cả storage, log, network, on-call, patch và dự phòng.
13. **“Khi chạy serverless không cần quan tâm process lifecycle.”** Cold start, shutdown, timeout, concurrent invocations và retry vẫn quyết định tính đúng.
14. **“Cấu hình tốt ở local thì production sẽ giống.”** Cần kiểm thử trên tài nguyên, tải và mạng tương tự sản xuất.
15. **“Có dashboard nền tảng là đủ observability.”** Phải đo kết quả nghiệp vụ, phiên bản triển khai, dependency và SLO.

## 31. Bài tập thực hành

**Bài 1 — API tải đều:** Một Spring Boot API chạy liên tục, 80 RPS trung bình, 500 RPS đỉnh, p95 yêu cầu dưới 250 ms, DB private. Hãy đề xuất hai phương án triển khai, so sánh thời gian startup, kết nối DB, HA, TCO và công vận hành. Xác định thử nghiệm nào khiến bạn đổi lựa chọn.

**Bài 2 — function theo sự kiện:** Hệ thống nhận webhook 30 phút mỗi ngày, mỗi công việc 200 ms nhưng thỉnh thoảng cần truy cập database. Hãy đánh giá serverless function và managed container, gồm cold start, số kết nối DB, retry và chi phí khi giữ warm instance.

**Bài 3 — worker xử lý file:** Một job chuyển đổi video có thể chạy 45 phút và dùng nhiều disk tạm. Hãy xác định giới hạn cần kiểm tra trước khi chọn FaaS; đề xuất lựa chọn managed job/container hoặc VM khi cần checkpoint và GPU.

**Bài 4 — năng lực DB:** Có 4 replica, mỗi replica có pool 30 kết nối. Autoscaler có thể tạo 20 replica trong vài phút; DB chỉ cấp 300 kết nối cho dịch vụ. Tính ngân sách kết nối danh nghĩa và giải thích cách thiết kế pool, maxReplicas, proxy và giới hạn tiếp nhận để không gây nghẽn DB.

**Bài 5 — chuyển VM sang container:** Một JAR đang chạy trên hai VM bằng systemd. Lập kế hoạch tạo image bất biến, tách config/secret, health probes, CI/CD, canary, rollback và đo downtime. Những chức năng nào không tự xuất hiện chỉ vì có Dockerfile?

**Bài 6 — lựa chọn Kubernetes:** Một tổ chức có 5 API stateless, 2 consumer Kafka, 1 job theo lịch và đội platform 2 người. Hãy so managed container platform với managed Kubernetes theo công vận hành, nhu cầu scheduling, khả năng scale và cách khôi phục. Nêu điều kiện cụ thể khiến Kubernetes đáng dùng hơn.

**Bài 7 — sự cố rolling deployment:** Sau deploy, readiness pass nhưng checkout error rate tăng do schema DB không tương thích. Hãy mô tả hành động dừng rollout, xử lý traffic, quyết định rollback code/data và những guardrail cần thêm trong lần sau.

**Bài 8 — chi phí:** Dùng dữ liệu giả lập về số giờ chạy, số request, thời lượng xử lý, egress, NAT, lưu trữ và on-call để tính TCO VM/managed container/serverless. Hãy vẽ điểm hòa vốn theo lượng traffic; giải thích vì sao chỉ số RPS cao nhất không đủ.

**Bài 9 — phân vùng lỗi:** Một API có 3 replica nhưng tất cả ở cùng một zone. Khi zone ngừng hoạt động, chuyện gì xảy ra? Thiết kế lại placement, cơ sở dữ liệu và các phụ thuộc để đạt RTO mong muốn.

**Bài 10 — tổng kết lựa chọn:** Chọn một dịch vụ thực tế, viết ADR theo mẫu ở trên. Ghi dữ liệu đo được hoặc giả định có nhãn, điều kiện phải đạt, lý do loại ứng viên, giới hạn vận hành và thời điểm xem lại kiến trúc.

## 32. Ghi nhớ

- **VM, container, managed platform và serverless khác nhau chủ yếu ở ranh giới trách nhiệm và hợp đồng vận hành.** Container là cách đóng gói, có thể chạy trên nhiều loại hạ tầng.
- **Chọn theo workload, SLO, dữ liệu, mạng, bảo mật, năng lực đội và TCO**; không chọn theo xu hướng hay số lượng microservice.
- **Serverless phù hợp nhiều bài toán tải theo sự kiện**, nhưng phải kiểm tra timeout, cold start, concurrency, quota, state và chi phí khi giữ nóng.
- **Managed platform giảm gánh nặng hạ tầng**, song ứng dụng vẫn phải quản lý quyền, cấu hình, khả năng chịu lỗi, kết nối DB, quan sát và rollout.
- **Kubernetes mạnh về điều phối**, có lợi khi nhu cầu và năng lực vận hành tương xứng; nó không mặc nhiên là lựa chọn tốt nhất cho đội nhỏ.
- **VM vẫn hợp lý** khi cần kiểm soát OS/phụ thuộc, đã có automation tốt hoặc tải ổn định với chi phí phù hợp.
- **Mở rộng compute phải đi cùng ngân sách downstream**: DB pool, broker, API ngoài và backpressure.
- **Triển khai thành công nghĩa là SLO, bảo mật và phục hồi hoạt động trong điều kiện thật**; trạng thái “Pod Running” hay “Function deployed” chưa chứng minh hệ thống đúng.
- **Quyết định phải có bằng chứng** qua load test, chaos/failure drill, quyền mạng, tính toán chi phí và ADR có điều kiện xem lại.

Một kiến trúc triển khai tốt cho phép dịch vụ phục vụ đúng nhu cầu hôm nay, tiếp tục hoạt động khi instance lỗi, phát hành phiên bản mới có kiểm soát và thay đổi nền tảng khi những ràng buộc thực sự thay đổi. Công nghệ được chọn là phương tiện để đáp ứng hợp đồng đó, không phải mục tiêu tự thân.
