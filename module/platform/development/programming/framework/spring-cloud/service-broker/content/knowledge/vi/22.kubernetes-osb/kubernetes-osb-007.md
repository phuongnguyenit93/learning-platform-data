# Triển khai broker trên Kubernetes độc lập với việc nền tảng có dùng OSB

Một service broker viết bằng Spring Boot có thể chạy trong Kubernetes như một ứng dụng HTTP thông thường. Kubernetes chịu trách nhiệm chạy container, duy trì Pod, cấp địa chỉ mạng, cấu hình, secret, health check và khả năng mở rộng. Ứng dụng broker chịu trách nhiệm triển khai hợp đồng Open Service Broker API (OSB API), quản lý catalog, service instance, binding, operation và giao tiếp với provider.

Hai vai trò này độc lập với nhau. **Đưa broker lên Kubernetes không có nghĩa Kubernetes tự động trở thành một nền tảng tiêu thụ OSB API.** Một nền tảng khác như Cloud Foundry có thể gọi broker đang chạy trong Kubernetes. Kubernetes cũng có thể chỉ là nơi host broker, trong khi broker cấp phát tài nguyên ở một cloud provider hoặc hệ thống bên ngoài. Nếu muốn một nền tảng Kubernetes sử dụng broker theo OSB, cần có thành phần client/controller tích hợp giao thức đó.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, bài học này tập trung vào việc đóng gói và triển khai broker lên Kubernetes một cách độc lập: xây dựng container image, cấu hình Deployment và Service, công bố endpoint, quản lý credentials, health probes, persistence, worker bất đồng bộ, bảo mật mạng, scaling, rollout và kiểm tra vận hành. Phần cuối phân biệt việc Kubernetes host broker với việc Kubernetes hoặc một thành phần mở rộng đóng vai trò OSB consumer.

## 1. Phân biệt môi trường chạy và giao thức tích hợp

OSB API định nghĩa giao diện HTTP(S) giữa một platform và service broker. Broker cung cấp catalog và xử lý yêu cầu provision, bind, unbind, update hoặc deprovision. Platform là client gọi các endpoint này.

Kubernetes là hệ thống điều phối container. Nó có thể chạy một ứng dụng Spring Boot thực thi OSB API, nhưng Kubernetes core không tự đăng ký broker, đọc catalog OSB hoặc gọi endpoint provision chỉ vì broker đang nằm trong cluster.

Cần phân biệt ba kiến trúc:

| Kiến trúc | Kubernetes làm gì? | Ai gọi OSB API? |
|---|---|---|
| Kubernetes chỉ host broker | Chạy container broker, cấp network, config, secret và health monitoring | Cloud Foundry hoặc platform khác |
| Broker chạy trong Kubernetes, provider ở ngoài | Host broker và có thể host worker; broker gọi database/cloud provider qua mạng | Platform OSB-compatible bên ngoài |
| Kubernetes vừa host broker vừa là nơi triển khai tài nguyên | Host broker; broker có thể gọi Kubernetes API để tạo resource trong namespace được cấp quyền | OSB consumer vẫn là platform hoặc controller đã tích hợp OSB |

Ví dụ, broker có thể chạy ở namespace **service-broker** của Kubernetes, expose qua HTTPS tại **broker.example.com**, còn Cloud Foundry đăng ký endpoint đó làm service broker. Cloud Foundry gọi catalog và các operation OSB; Kubernetes chỉ quản lý workload broker.

Một ví dụ khác là broker chạy trong Kubernetes và cấp phát PostgreSQL ở dịch vụ managed database ngoài cluster. Broker vẫn dùng OSB API để giao tiếp với platform; provider adapter dùng HTTPS/SDK riêng để gọi nhà cung cấp.

Nếu broker tạo Kubernetes Deployment, Service hoặc PersistentVolumeClaim cho từng service instance, đó là logic provider của broker. Nó không làm cho Kubernetes API trở thành OSB API.

## 2. Kiến trúc triển khai tham khảo

Với broker Spring Boot, kiến trúc production thường gồm:

- **Deployment API**: chạy HTTP endpoint OSB, nhận request từ platform.
- **Service**: cung cấp địa chỉ ổn định trong cluster cho các Pod broker.
- **Ingress hoặc Gateway**: công bố endpoint HTTPS cho platform bên ngoài khi cần.
- **Database bền vững**: lưu instance, binding, operation, idempotency và outbox.
- **Secret manager**: bảo vệ database credentials, broker authentication và provider credentials.
- **Worker**: xử lý operation dài hoặc tác vụ outbox nếu ứng dụng dùng asynchronous workflow.
- **Monitoring/logging**: thu thập metric, trace và log đã lọc dữ liệu nhạy cảm.

Sơ đồ tổng quát:

~~~mermaid
flowchart TB
    Platform["OSB-compatible platform"] -->|"HTTPS / OSB API"| Gateway["Ingress / Gateway"]
    Gateway --> KService["Kubernetes Service"]
    KService --> API1["Broker API Pod 1"]
    KService --> API2["Broker API Pod 2"]
    API1 --> DB[("Shared durable database")]
    API2 --> DB
    API1 --> Provider["Provider API"]
    API2 --> Provider
    API1 --> Secrets["Secret manager"]
    API2 --> Secrets
    DB --> Outbox["Outbox / operation records"]
    Outbox --> Worker["Broker worker Pods"]
    Worker --> Provider
    Worker --> Secrets
~~~

Các Pod API có thể thay thế lẫn nhau nếu broker không giữ trạng thái nghiệp vụ trong heap hoặc local filesystem. Khi platform gửi retry đến một Pod khác, Pod đó vẫn phải đọc được cùng instance, binding và operation từ database chung.

Worker có thể chạy cùng ứng dụng hoặc thành một Deployment riêng. Nếu tách riêng, API và worker vẫn dùng chung kho trạng thái, operation ID và idempotency key. Không dùng local queue trong bộ nhớ của một Pod làm nơi duy nhất lưu tác vụ cần phục hồi.

## 3. Chuẩn bị ứng dụng Spring Boot cho container

Spring Cloud Open Service Broker cung cấp framework để xây dựng Spring Boot application triển khai OSB API. Framework hỗ trợ ứng dụng Spring MVC và Spring WebFlux; việc đóng gói container không thay đổi hợp đồng OSB mà ứng dụng đã triển khai.

Trước khi tạo image, cần xác định:

1. Phiên bản Java và Spring Boot tương thích với phiên bản Spring Cloud Open Service Broker đang dùng.
2. Port HTTP mà broker lắng nghe.
3. Cấu hình profile dành cho Kubernetes.
4. Nguồn cấu hình database, authentication và provider.
5. Endpoint health của Spring Boot Actuator.
6. Cơ chế graceful shutdown.
7. Những dữ liệu phải lưu bền vững bên ngoài Pod.

Ví dụ Dockerfile multi-stage:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -q -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd --system --uid 10001 --create-home broker
COPY --from=build /workspace/target/service-broker.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dockerfile chỉ là ví dụ. Cần điều chỉnh JDK/JRE, Maven hoặc Gradle, tên artifact và phiên bản Java theo dự án thực tế. Nếu dùng Gradle, thay bước build bằng Gradle Wrapper và sao chép đúng file JAR được tạo.

Một số nguyên tắc khi tạo image:

- Dùng image base được cập nhật và có nguồn tin cậy.
- Không COPY file chứa credentials vào image.
- Không truyền password qua build argument rồi để lại trong layer.
- Chạy process bằng user không phải root.
- Gắn version hoặc image digest bất biến để có thể rollback.
- Quét lỗ hổng dependency và container image trước khi triển khai.
- Không phụ thuộc vào file được tạo trong filesystem của container để lưu trạng thái vòng đời.

Ví dụ build và push:

~~~bash
docker build -t registry.example.com/platform/service-broker:1.0.0 .
docker push registry.example.com/platform/service-broker:1.0.0
~~~

Kubernetes cần pull được image từ registry. Nếu registry private, cấu hình imagePullSecret theo namespace và giới hạn quyền đọc secret đó.

## 4. Tách cấu hình khỏi container image

Cùng một image nên có thể chạy ở development, staging và production bằng cách thay đổi cấu hình. Không đóng cứng hostname database, broker username, provider token hoặc URL secret manager vào image.

Có thể phân loại cấu hình:

| Nhóm | Ví dụ | Cơ chế phù hợp |
|---|---|---|
| Cấu hình không nhạy cảm | Port, profile, feature flag, timeout | ConfigMap hoặc biến môi trường |
| Credentials | Database password, provider token, broker authentication | Kubernetes Secret hoặc secret manager ngoài |
| Certificate/key | TLS certificate, private key, trust bundle | Secret volume, CSI driver hoặc certificate manager |
| Dữ liệu nghiệp vụ | Instance, binding, operation | Database bền vững |
| Dữ liệu tạm | Cache, temp file | Pod memory/ephemeral storage |

ConfigMap không phải nơi lưu password hoặc token. Kubernetes Secret dành cho dữ liệu nhạy cảm, nhưng cần hiểu rằng giá trị trong manifest thường được biểu diễn dạng base64; base64 không phải mã hóa. Cần bật encryption at rest cho dữ liệu Secret trong etcd, giới hạn RBAC và cân nhắc secret manager bên ngoài.

Một cách cấu hình đơn giản là dùng ConfigMap cho các giá trị không nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: service-broker-config
  namespace: service-broker
data:
  SPRING_PROFILES_ACTIVE: kubernetes
  SERVER_PORT: "8080"
  MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED: "true"
  MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE: health
  SERVER_SHUTDOWN: graceful
  SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE: 25s
~~~

Tên biến môi trường theo quy tắc relaxed binding của Spring Boot. Cần kiểm tra chúng phù hợp với phiên bản Spring Boot và cấu hình ứng dụng đang dùng.

Với credentials, Deployment có thể tham chiếu Secret đã được tạo bởi quy trình bảo mật của cluster:

~~~yaml
env:
  - name: SPRING_DATASOURCE_URL
    valueFrom:
      secretKeyRef:
        name: service-broker-runtime
        key: datasource-url
  - name: SPRING_DATASOURCE_USERNAME
    valueFrom:
      secretKeyRef:
        name: service-broker-runtime
        key: datasource-username
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: service-broker-runtime
        key: datasource-password
  - name: BROKER_PROVIDER_TOKEN
    valueFrom:
      secretKeyRef:
        name: service-broker-runtime
        key: provider-token
~~~

Các key và biến BROKER_PROVIDER_TOKEN là ví dụ; ứng dụng cần ánh xạ chúng vào cấu hình provider adapter. Nếu dùng R2DBC, cấu hình kết nối có thể dùng SPRING_R2DBC_URL thay cho SPRING_DATASOURCE_URL.

Với môi trường production, cân nhắc mount secret dưới dạng file read-only hoặc tích hợp external secret store/Secrets Store CSI Driver. Tránh truyền secret qua command-line argument hoặc ghi nó vào log, crash dump hay diagnostic endpoint.

## 5. Tạo namespace và ServiceAccount riêng

Tách broker vào namespace riêng giúp quản lý quota, network policy, secret và quyền truy cập độc lập.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: service-broker
  labels:
    app.kubernetes.io/part-of: service-broker-platform
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: service-broker
  namespace: service-broker
automountServiceAccountToken: false
~~~

Nếu broker chỉ gọi provider bên ngoài qua HTTPS và không cần truy cập Kubernetes API, tắt tự động mount service account token là lựa chọn phù hợp.

Nếu broker dùng Kubernetes làm provider và cần tạo resource trong cluster, tạo ServiceAccount riêng, bật token mount có chủ đích và cấp Role/RoleBinding với quyền tối thiểu trong namespace đích. Chỉ cấp các verb và resource thực sự cần, chẳng hạn get/list/watch/create/patch/delete trên loại resource mà provider adapter quản lý. Không cấp cluster-admin hoặc quyền quản lý Role/ClusterRole chỉ để tiện triển khai.

Nếu broker cần provision resource ở nhiều namespace, xác định rõ ranh giới tenant và phạm vi quyền. Không để một broker credential có thể tùy ý tạo hoặc xóa resource trên toàn cluster nếu service contract chỉ cho phép thao tác trong một namespace.

## 6. Triển khai broker bằng Deployment

Broker API thường phù hợp với Deployment vì các Pod có thể thay thế lẫn nhau khi trạng thái nghiệp vụ được lưu bên ngoài. Kubernetes Deployment quản lý ReplicaSet, rollout và thay thế Pod theo desired state.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker
  namespace: service-broker
  labels:
    app.kubernetes.io/name: service-broker
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: service-broker
  template:
    metadata:
      labels:
        app.kubernetes.io/name: service-broker
    spec:
      serviceAccountName: service-broker
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: broker
          image: registry.example.com/platform/service-broker:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: service-broker-config
          env:
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-url
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: datasource-password
            - name: BROKER_PROVIDER_TOKEN
              valueFrom:
                secretKeyRef:
                  name: service-broker-runtime
                  key: provider-token
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
            sizeLimit: 64Mi
~~~

Các giá trị CPU/memory, timeout và replica chỉ là ví dụ. Cần đo tải thật, kích thước heap JVM, connection pool và yêu cầu latency để điều chỉnh. Nếu ứng dụng cần ghi file ở đường dẫn khác ngoài /tmp, phải cấp volume phù hợp hoặc cấu hình ứng dụng không ghi vào root filesystem.

Ví dụ sử dụng JDBC datasource. Nếu broker dùng R2DBC, cấu hình secret và connection pool tương ứng với driver reactive.

### Vì sao dùng Deployment thay vì StatefulSet?

Deployment phù hợp khi broker API không phụ thuộc danh tính Pod và không giữ dữ liệu duy nhất trong local disk. StatefulSet thường dành cho workload cần identity ổn định hoặc storage gắn với từng Pod. Broker có thể chạy bằng Deployment ngay cả khi nó quản lý service instance có trạng thái, miễn là trạng thái đó nằm trong database/secret store bền vững.

Không nên gắn một PersistentVolume riêng cho từng broker API Pod chỉ để lưu operation hoặc binding. Khi scale hoặc rollout, các Pod sẽ có bản sao dữ liệu không đồng nhất. Dùng kho dữ liệu dùng chung làm nguồn sự thật.

## 7. Tạo Kubernetes Service cho broker

Service cung cấp endpoint ổn định trong cluster và phân phối traffic đến các Pod đủ điều kiện nhận request.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: service-broker
  namespace: service-broker
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: service-broker
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
~~~

Các workload trong cluster có thể gọi broker qua DNS nội bộ:

~~~text
http://service-broker.service-broker.svc.cluster.local
~~~

Nếu platform OSB client ở ngoài cluster, ClusterIP không thể tự truy cập từ Internet. Cần expose qua Ingress, Gateway API hoặc LoadBalancer theo chính sách mạng. Không expose trực tiếp Pod IP vì Pod có thể được thay thế trong quá trình rollout.

## 8. Công bố endpoint qua Ingress hoặc Gateway API

Platform tiêu thụ OSB cần truy cập được endpoint broker. Nếu Cloud Foundry nằm ngoài cluster, broker thường cần một URL HTTPS ổn định mà Cloud Controller có thể kết nối.

Ví dụ Ingress:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: service-broker
  namespace: service-broker
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - broker.example.com
      secretName: service-broker-tls
  rules:
    - host: broker.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: service-broker
                port:
                  number: 80
~~~

Manifest giả định cluster đã cài Ingress controller phù hợp và secret TLS đã được tạo bởi quy trình certificate management. Kubernetes Ingress API chỉ mô tả routing; controller mới thực hiện load balancing, TLS termination và các policy tương ứng.

Gateway API là lựa chọn khác nếu cluster đã cài Gateway controller và tổ chức muốn dùng các resource Gateway/HTTPRoute. Chọn cơ chế phù hợp với cluster, không khai báo cả Ingress lẫn Gateway chỉ để tạo thêm một lớp routing không cần thiết.

Một số nguyên tắc khi công bố endpoint:

- Chỉ cho phép HTTPS từ platform hoặc mạng tin cậy.
- Cấu hình certificate chain và hostname đúng.
- Không để endpoint quản trị, actuator hoặc debug endpoint public.
- Giới hạn request size, timeout và rate theo nhu cầu operation.
- Cấu hình proxy headers đúng để ứng dụng nhận diện scheme/client theo mô hình tin cậy.
- Bảo vệ OSB endpoint bằng cơ chế platform-to-broker authentication đã thống nhất.
- Không xem TLS termination là thay thế cho authentication và authorization ở broker.

Nếu platform nằm trong cùng cluster hoặc cùng private network, có thể chỉ expose qua private load balancer hoặc internal Gateway. Không cần public Internet nếu platform không yêu cầu.

## 9. Health probes cho Spring Boot

Kubernetes sử dụng probe để quyết định khi nào Pod được nhận traffic và khi nào container cần restart. Spring Boot Actuator cung cấp health endpoint và các health group dành cho liveness/readiness.

Cần phân biệt:

| Probe | Câu hỏi | Hành động của Kubernetes |
|---|---|---|
| Startup | Ứng dụng đã khởi động đủ để bắt đầu kiểm tra định kỳ chưa? | Chờ startup probe thành công trước khi chạy liveness/readiness |
| Liveness | Tiến trình có còn hoạt động đúng để tiếp tục chạy không? | Restart container nếu thất bại quá ngưỡng |
| Readiness | Pod có thể nhận request mới ngay lúc này không? | Loại Pod khỏi endpoint Service khi chưa sẵn sàng |

Với Spring Boot, các endpoint thường dùng là:

- /actuator/health/liveness
- /actuator/health/readiness

Cần có Spring Boot Actuator dependency và bật health probes nếu phiên bản/cấu hình ứng dụng yêu cầu:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

Không đưa toàn bộ Actuator endpoint ra Internet. Chỉ expose health group cần thiết cho kubelet và monitoring nội bộ; kiểm soát quyền truy cập và chi tiết health response.

### Liveness không nên phụ thuộc provider bên ngoài

Nếu database provider hoặc secret manager tạm thời mất kết nối, liveness không nên lập tức báo unhealthy khiến Kubernetes restart tất cả Pod broker. Restart hàng loạt có thể làm tăng tải và tạo cascading failure.

Liveness nên phản ánh tình trạng tiến trình broker. Readiness có thể kiểm tra dependency thật sự bắt buộc để phục vụ request, chẳng hạn database trạng thái nếu broker không thể xử lý an toàn khi database mất kết nối. Việc đưa provider API vào readiness cần cân nhắc vì provider có thể chậm hoặc giới hạn rate; không biến một lỗi bên ngoài thành vòng lặp restart.

Nếu management port tách khỏi application port, probe trên management port có thể thành công trong khi HTTP listener chính gặp vấn đề. Ưu tiên cung cấp probe trên cùng server port hoặc bảo đảm probe phản ánh đúng khả năng nhận traffic của broker.

## 10. Lưu trạng thái broker bên ngoài Pod

Kubernetes có thể thay Pod khi node lỗi, rollout, autoscaling hoặc eviction. Vì vậy, dữ liệu quyết định vòng đời service instance không được chỉ nằm trong heap hay local filesystem.

Các dữ liệu cần lưu bền vững:

- Service instance và provider resource ID.
- Service binding và provider principal ID.
- Credentials hoặc secret reference.
- Operation ID, state và last-operation result.
- Request fingerprint/idempotency record.
- Outbox event và retry schedule.
- Audit metadata và correlation reference.

Một mô hình phổ biến là broker API chạy nhiều replica và cùng kết nối tới database quan hệ bên ngoài. Worker cũng đọc operation/outbox từ kho dữ liệu đó. Nếu database được triển khai trong Kubernetes, cần dùng StatefulSet hoặc dịch vụ database operator có storage, backup, replication và restore được thiết kế riêng; không xem việc database Pod đang Running là bằng chứng dữ liệu an toàn.

### Không giữ operation chỉ trong background thread của request Pod

Nếu một request provision trả async và tạo task trong ExecutorService nội bộ của Pod, Pod bị restart có thể làm mất task. Hãy ghi operation và event vào database/outbox hoặc queue bền vững trước khi trả response async.

Worker phải có cơ chế claim/lease, retry, idempotency và reconciliation. Nhiều worker replica có thể xử lý song song nếu có khóa hoặc reservation bền vững để tránh chạy cùng operation đồng thời.

## 11. Tách API Pod và worker Pod khi cần

Với tải nhỏ, broker API và worker có thể chạy trong cùng Spring Boot process. Khi operation dài hoặc cần scale độc lập, có thể tách hai Deployment:

- **service-broker-api**: nhận OSB HTTP request, xác thực, trả catalog và tạo operation record.
- **service-broker-worker**: đọc outbox/queue, gọi provider, cập nhật operation và phát kết quả.

Hai Deployment có thể dùng chung image nhưng chạy profile hoặc command khác nhau theo cấu hình ứng dụng. Cần bảo đảm chỉ worker chạy scheduler/consumer; API Pod không vô tình chạy cùng công việc nếu thiết kế yêu cầu tách biệt.

Nếu worker dùng queue, cấu hình consumer group, visibility timeout hoặc lease phù hợp để xử lý khi Pod chết giữa chừng. Nếu worker dùng database polling, claim record bằng transaction/lease và có index cho operation đang chờ.

Không dựa vào số lượng Pod để bảo đảm exactly-once. Mô hình phân tán thường cần chấp nhận delivery ít nhất một lần và làm cho handler/provider adapter idempotent.

## 12. Bảo mật broker trong Kubernetes

Broker nhận request có thể tạo tài nguyên và cấp credentials, do đó endpoint này có quyền tác động đến hệ thống provider. Cấu hình bảo mật phải bao phủ cả container, Kubernetes API, network và secret.

### Bảo mật container

- Chạy bằng user không phải root.
- Tắt privilege escalation.
- Drop Linux capabilities không cần thiết.
- Dùng read-only root filesystem nếu ứng dụng tương thích.
- Giới hạn CPU, memory và ephemeral storage.
- Dùng image đã scan và pin version/digest.
- Áp dụng Pod Security Standards phù hợp với namespace.

### Bảo mật ServiceAccount và RBAC

- Dùng ServiceAccount riêng cho broker.
- Tắt automount token nếu broker không gọi Kubernetes API.
- Nếu phải gọi Kubernetes API, cấp Role/RoleBinding tối thiểu.
- Tránh ClusterRoleBinding rộng.
- Không cho broker tự tạo hoặc sửa quyền RBAC nếu service contract không cần.
- Tách ServiceAccount API và worker nếu quyền truy cập khác nhau.

### Bảo mật Secret

- Không đưa credentials vào ConfigMap hoặc Git manifest.
- Bật encryption at rest cho Kubernetes Secret trong etcd.
- Hạn chế quyền get/list/watch Secret theo namespace.
- Ưu tiên external secret manager hoặc CSI volume nếu hạ tầng hỗ trợ.
- Tránh log environment hoặc serialize object chứa credentials.
- Có rotation cho database password, provider token và broker authentication.

### Bảo vệ mạng

- Chỉ cho ingress từ platform, load balancer hoặc gateway cần thiết.
- Giới hạn egress tới database, secret manager, DNS và provider endpoint.
- Dùng TLS cho kết nối broker-platform và broker-provider.
- Không để health/management endpoint public.
- Xác nhận CNI của cluster có thực thi NetworkPolicy; API object có thể tồn tại nhưng không có tác dụng nếu network plugin không hỗ trợ enforcement.

Nếu đặt default-deny egress, cần cho phép DNS và các endpoint bắt buộc. NetworkPolicy chuẩn không có cơ chế FQDN selector phổ quát; kiểm soát egress theo domain có thể cần firewall, egress gateway hoặc tính năng riêng của CNI.

## 13. Ví dụ NetworkPolicy cho ingress

Một policy ingress có thể giới hạn traffic vào broker Pod từ namespace của Ingress controller. Nhãn namespace và Pod phải được điều chỉnh theo controller thực tế:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: service-broker-ingress
  namespace: service-broker
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: service-broker
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8080
~~~

Đây là ví dụ giới hạn ingress, không phải policy đầy đủ cho production. Nếu platform gọi broker qua private network hoặc một namespace khác, thêm nguồn tương ứng. Nếu cluster dùng CNI có enforcement NetworkPolicy, bảo đảm kubelet health probe và monitoring traffic vẫn hoạt động theo cách triển khai của cluster.

Khi thêm egress policy, phải cho phép DNS, database port, secret manager và provider endpoints cần thiết. Kiểm thử connectivity sau khi áp dụng policy; một policy quá chặt có thể khiến broker không provision được dù Pod vẫn Running.

## 14. High availability và Pod disruption

Một broker production thường cần ít nhất hai replica API nếu platform yêu cầu khả năng phục vụ khi một Pod hoặc node bị gián đoạn. Tuy nhiên, nhiều replica chỉ có ý nghĩa khi trạng thái được chia sẻ và database/provider có tính sẵn sàng tương ứng.

Các yếu tố:

- Chạy nhiều replica trên các node khác nhau.
- Dùng topology spread hoặc pod anti-affinity để tránh dồn tất cả Pod vào một node.
- Đặt readiness probe để Pod chưa sẵn sàng không nhận traffic.
- Cấu hình rolling update với maxUnavailable phù hợp.
- Dùng PodDisruptionBudget để hạn chế số Pod bị eviction đồng thời trong các voluntary disruption.
- Cấu hình graceful shutdown và đủ termination grace period.
- Đảm bảo database có HA, backup và connection capacity.
- Dùng idempotency/lease để worker phục hồi khi Pod bị thay thế.

Ví dụ PodDisruptionBudget:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-broker
  namespace: service-broker
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: service-broker
~~~

PDB giúp giới hạn voluntary eviction thông qua Eviction API, chẳng hạn khi node được drain. Nó không ngăn mọi dạng lỗi node và không thay thế chiến lược rolling update của Deployment. Với hai replica và minAvailable bằng 1, một Pod có thể bị eviction trong khi Pod còn lại tiếp tục phục vụ.

## 15. Scaling broker bằng HPA

Kubernetes HorizontalPodAutoscaler có thể tăng/giảm số replica của Deployment dựa trên metric như CPU hoặc memory utilization. Ví dụ:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: service-broker
  namespace: service-broker
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: service-broker
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
~~~

HPA cần metrics pipeline phù hợp, thường là Metrics Server cho resource metrics. Khi HPA quản lý replica count, không liên tục sửa replicas thủ công trong Deployment vì controller HPA sẽ điều chỉnh giá trị này.

CPU không phải lúc nào cũng phản ánh tải broker. Nếu phần lớn request chờ provider I/O, có thể cần metric custom như request concurrency, latency, queue depth hoặc operation backlog. Với worker, scale theo queue depth hoặc số operation chờ có thể phù hợp hơn; KEDA là một lựa chọn nếu cluster đã cài và vận hành nó.

Không scale vô hạn. Giới hạn maxReplicas theo khả năng của database connection pool, provider rate limit và quota của cluster. Nếu HPA tăng Pod nhưng database chỉ chịu được một số lượng connection nhỏ, broker có thể gây quá tải chính kho trạng thái.

## 16. Graceful shutdown và rolling update

Kubernetes gửi SIGTERM khi container cần dừng và chờ trong terminationGracePeriodSeconds trước khi kết thúc cưỡng bức. Broker cần xử lý shutdown để không cắt request đang chạy hoặc bỏ dở worker giữa side effect.

Với Spring Boot, có thể bật graceful shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

Thời gian timeout phải nhỏ hơn terminationGracePeriodSeconds với khoảng dự phòng cho JVM dừng. Readiness cần chuyển sang trạng thái không nhận traffic khi ứng dụng đang shutdown. Worker cần ngừng nhận operation mới, hoàn tất hoặc nhả lease cho công việc đang xử lý.

Một rolling update mẫu:

~~~bash
kubectl apply -f service-broker.yaml
kubectl rollout status deployment/service-broker -n service-broker
kubectl get pods -n service-broker -l app.kubernetes.io/name=service-broker
~~~

Dùng image version mới bất biến. Nếu có database schema migration, triển khai theo hướng tương thích ngược để Pod cũ và mới cùng hoạt động trong giai đoạn rollout. Không chạy migration phá vỡ schema trong lúc worker cũ còn xử lý operation.

Nếu rollout lỗi:

~~~bash
kubectl rollout history deployment/service-broker -n service-broker
kubectl rollout undo deployment/service-broker -n service-broker
~~~

Rollback image không tự rollback database migration hoặc provider side effect. Migration cần kế hoạch tương thích và quy trình phục hồi riêng.

## 17. Triển khai và kiểm tra theo từng bước

Một quy trình triển khai có thể thực hiện như sau:

### Bước 1: Tạo namespace và cấu hình

~~~bash
kubectl apply -f namespace-and-config.yaml
~~~

Tạo Secret qua quy trình quản lý bí mật của tổ chức. Không commit file chứa password/token vào repository.

### Bước 2: Triển khai broker

~~~bash
kubectl apply -f service-broker-deployment.yaml
kubectl rollout status deployment/service-broker -n service-broker
~~~

Nếu Pod không Ready, xem trạng thái và event:

~~~bash
kubectl get pods -n service-broker
kubectl describe pod POD_NAME -n service-broker
kubectl logs deployment/service-broker -n service-broker
~~~

Log phải được lọc để không lộ credentials hoặc dữ liệu khách hàng.

### Bước 3: Kiểm tra Service nội bộ

~~~bash
kubectl get service service-broker -n service-broker
kubectl get endpointslices -n service-broker
~~~

Xác nhận Service selector khớp Pod label và EndpointSlice có endpoint Ready.

Có thể port-forward để kiểm tra endpoint từ máy quản trị:

~~~bash
kubectl port-forward service/service-broker 18080:80 -n service-broker
~~~

Trong terminal khác, gọi catalog qua localhost với authentication đã cấu hình:

~~~bash
curl -i http://127.0.0.1:18080/v2/catalog \
  -H "X-Broker-API-Version: 2.17"
~~~

Ví dụ bỏ phần authentication để dễ đọc. Trong môi trường thật, gửi credentials theo cơ chế đã cấu hình mà không ghi chúng vào shell history hoặc output. Catalog response phải đúng JSON và phản ánh service/plan mà broker công bố.

### Bước 4: Kiểm tra endpoint HTTPS

Sau khi Ingress/Gateway và TLS được cấu hình:

~~~bash
curl -i https://broker.example.com/v2/catalog \
  -H "X-Broker-API-Version: 2.17"
~~~

Kiểm tra DNS, certificate chain, hostname, route, authentication và network path từ chính platform consumer. Một request thành công từ laptop quản trị không chứng minh Cloud Controller hoặc platform ở mạng khác cũng truy cập được.

### Bước 5: Kiểm tra luồng OSB end-to-end

Dùng một platform OSB-compatible hoặc test client để xác minh:

1. Đăng ký broker endpoint và thông tin xác thực ở platform.
2. Platform truy vấn catalog.
3. Provision một service instance thử nghiệm.
4. Theo dõi operation nếu broker xử lý async.
5. Tạo binding và xác nhận credentials được trả đúng.
6. Unbind và xác nhận provider revoke đúng quyền.
7. Deprovision và xác nhận resource được thu hồi.
8. Gửi request retry để kiểm tra idempotency.
9. Restart một Pod giữa operation test để xác nhận trạng thái được phục hồi từ kho bền vững.

Kubernetes readiness chỉ xác nhận Pod sẵn sàng nhận traffic. Nó không chứng minh OSB contract, provider adapter hoặc toàn bộ vòng đời service hoạt động đúng.

## 18. Quan sát và xử lý sự cố

Nên theo dõi cả lớp Kubernetes lẫn lớp nghiệp vụ broker.

| Tín hiệu | Nơi kiểm tra | Câu hỏi cần trả lời |
|---|---|---|
| Pod không Ready | kubectl describe, readiness probe | Ứng dụng đã khởi động chưa? Database có truy cập được không? |
| Pod restart liên tục | liveness/startup probe, container logs | Có deadlock, OOM hoặc cấu hình startup sai không? |
| Service không có endpoint | Service selector, Pod labels, EndpointSlice | Pod có Ready và label có khớp không? |
| Ingress trả 404/502 | Ingress controller, Service, port | Host/path/backend/targetPort có đúng không? |
| Platform không kết nối broker | DNS, TLS, firewall, NetworkPolicy | Platform có route và trust certificate không? |
| Catalog lỗi | broker logs, authentication, OSB version | Request có đúng API version và credentials không? |
| Provision bị treo | operation table, worker logs, provider request ID | Worker có claim operation và provider có trả kết quả không? |
| Request retry tạo resource trùng | idempotency record, provider external reference | Reservation/key có ổn định qua nhiều Pod không? |
| Pod OOMKilled | resource limit, JVM heap, memory metric | Heap/container memory có phù hợp không? |
| HPA không scale | HPA status, metrics-server | Metrics có được cung cấp và resource requests có khai báo không? |

Một số lệnh hỗ trợ:

~~~bash
kubectl get deployment,service,ingress -n service-broker
kubectl get pods -n service-broker -o wide
kubectl describe deployment service-broker -n service-broker
kubectl get hpa,pdb -n service-broker
kubectl top pods -n service-broker
kubectl logs deployment/service-broker -n service-broker --since=30m
~~~

Không bật wire logging toàn bộ HTTP request/response hoặc dump credentials để điều tra production. Dùng operation ID, correlation ID và provider request reference đã được lọc để tra cứu.

## 19. Kubernetes có bắt buộc phải tiêu thụ OSB API không?

Không. Việc broker chạy trên Kubernetes chỉ có nghĩa Kubernetes là môi trường runtime của ứng dụng broker.

Nếu Cloud Foundry là platform tiêu thụ OSB, Cloud Controller gọi broker qua HTTPS. Broker có thể chạy trong Kubernetes ở bất kỳ cluster/network nào mà Cloud Foundry truy cập được. Không cần cài một service catalog trong Kubernetes chỉ để host broker.

Nếu Kubernetes được chọn làm platform tiêu thụ dịch vụ, cần một thành phần có chức năng OSB client. Thành phần đó phải biết đăng ký broker, đọc catalog, tạo service instance, theo dõi operation, bind và unbind. Kubernetes core API không tự thực hiện những việc này theo OSB.

Trong lịch sử, Kubernetes Service Catalog là một dự án riêng tích hợp OSB API qua các custom resource/controller. Dự án này hiện được lưu trữ trong tổ chức kubernetes-retired; không nên giả định đây là chức năng built-in hoặc lựa chọn mặc định cho cluster mới.

Các cách tích hợp Kubernetes-native hiện nay thường dựa trên:

- **CustomResourceDefinition (CRD)** để định nghĩa API mong muốn của service.
- **Operator/controller** theo dõi CRD và thực hiện reconciliation.
- **GitOps** để quản lý khai báo và trạng thái mong muốn.
- **Crossplane hoặc nền tảng control plane khác** nếu tổ chức đã chọn và vận hành giải pháp đó.
- Một controller riêng đóng vai trò OSB client nếu cần gọi broker theo OSB API.

Các cách này có thể cùng tồn tại với OSB. Ví dụ, một controller đọc custom resource trong Kubernetes rồi gọi broker OSB. Khi đó controller là adapter/consumer của OSB; Kubernetes chỉ cung cấp API object và cơ chế reconciliation.

### Hai chiều tích hợp cần tách biệt

| Chiều | Vai trò broker | Vai trò Kubernetes |
|---|---|---|
| Broker được deploy trên Kubernetes | Server OSB | Runtime host |
| Kubernetes consumer gọi broker OSB | Server OSB bên ngoài hoặc trong cluster | Cần controller/client tích hợp OSB |
| Broker gọi Kubernetes API để tạo resource | Provider adapter của broker | Target provider API |

Tách rõ ba trường hợp giúp tránh cài thêm thành phần không cần thiết và tránh hiểu nhầm Kubernetes Service/Ingress là OSB Service Catalog.

## 20. Checklist triển khai production

Trước khi công bố broker cho platform, kiểm tra các nhóm sau:

**Image và ứng dụng**
- Image có version/digest bất biến.
- Process chạy non-root.
- Không có credentials trong image.
- Actuator health probes được cấu hình đúng.
- Graceful shutdown và timeout được kiểm thử.
- Log/trace không chứa credentials hoặc customer payload.

**Kubernetes workload**
- Deployment có replica phù hợp.
- Requests/limits được đo và cấu hình.
- Startup, liveness và readiness probe phân biệt đúng.
- Rolling update có maxUnavailable/maxSurge phù hợp.
- PDB và topology spread phù hợp với mô hình cluster.
- HPA không vượt khả năng database/provider.

**Mạng và bảo mật**
- Platform truy cập được endpoint HTTPS.
- Certificate và authentication hoạt động.
- Ingress/Gateway không expose management endpoint.
- NetworkPolicy được CNI thực thi.
- ServiceAccount/RBAC theo least privilege.
- Secret được mã hóa và giới hạn truy cập.

**Trạng thái và phục hồi**
- Instance, binding và operation nằm trong kho bền vững.
- Nhiều replica nhìn thấy cùng state.
- Idempotency hoạt động khi retry sang Pod khác.
- Worker dùng queue/outbox/lease bền vững.
- Database có backup, restore và HA.
- Provider timeout được reconciliation.
- Pod restart giữa operation không làm mất tiến độ.

**OSB contract và platform**
- Broker endpoint đúng version OSB.
- Catalog trả service/plan ổn định.
- Provision, update, bind, unbind, deprovision được kiểm thử.
- Async operation và last_operation đúng hợp đồng nếu có dùng.
- Platform consumer đã đăng ký broker bằng endpoint và credentials phù hợp.
- Có test end-to-end từ mạng của platform.

## 21. Những lỗi thường gặp

**Cho rằng deploy broker lên Kubernetes tự động tạo service catalog cho cluster.** Kubernetes chỉ chạy workload; cần một OSB consumer/controller riêng nếu cluster phải gọi broker.

**Lưu instance state trong bộ nhớ Pod.** Request retry có thể đến Pod khác hoặc Pod bị restart. Lưu state trong database dùng chung.

**Dùng StatefulSet chỉ vì broker có dữ liệu.** Broker API thường là workload stateless; dữ liệu nên nằm trong database hoặc secret manager bền vững.

**Expose Pod trực tiếp.** Pod IP thay đổi. Dùng Service và Ingress/Gateway/LoadBalancer phù hợp.

**Dùng ConfigMap cho password.** ConfigMap dành cho cấu hình không nhạy cảm. Dùng Secret hoặc secret manager và bật encryption at rest.

**Tắt readiness hoặc dùng liveness kiểm tra provider.** Pod có thể nhận traffic trước khi sẵn sàng hoặc bị restart hàng loạt khi provider lỗi. Phân biệt rõ ba probe.

**Scale API mà không giới hạn database connection.** Nhiều Pod có thể làm database quá tải. Tính tổng connection pool theo maxReplicas.

**Chạy worker chỉ trong thread của request.** Pod restart sẽ làm mất công việc. Dùng outbox/queue và state bền vững.

**Cấp cluster-admin cho broker.** Nếu broker chỉ cần tạo resource trong một namespace, quyền toàn cluster là quá rộng. Dùng Role/RoleBinding tối thiểu.

**Cho rằng PDB bảo vệ mọi tình huống downtime.** PDB chỉ kiểm soát một số voluntary disruption qua Eviction API; cần replica, readiness, rollout strategy và HA ở database/provider.

**Chỉ kiểm tra Pod Running.** Pod Running không chứng minh catalog, authentication, provider operation hoặc binding hoạt động. Thực hiện OSB end-to-end test.

## 22. Nguyên tắc triển khai trong Spring Cloud Service Broker

Hãy xem broker là một Spring Boot application triển khai OSB API và Kubernetes là runtime quản lý container. Đóng gói broker thành image bất biến, chạy bằng Deployment, expose qua Service và chỉ công bố HTTPS endpoint đến platform cần gọi. Dùng ConfigMap cho cấu hình thông thường, Secret/secret manager cho credentials, Actuator probes cho health và ServiceAccount tối thiểu theo nhu cầu provider.

Giữ broker API stateless giữa các Pod. Lưu instance, binding, operation, idempotency và outbox trong kho dữ liệu bền vững; lưu credentials trong secret manager hoặc encrypted store. Với operation dài, dùng worker có lease và retry để phục hồi sau Pod restart. Thiết kế rolling update, graceful shutdown, PDB và HPA theo khả năng database cũng như rate limit provider.

Cuối cùng, xác định rõ ai là OSB consumer. Cloud Foundry hoặc một platform tương thích có thể gọi broker đang chạy trên Kubernetes. Nếu Kubernetes cần tiêu thụ broker, phải cài hoặc xây dựng controller/client có hỗ trợ OSB; Kubernetes core không tự đảm nhiệm giao thức đó. Sự phân tách này giúp triển khai broker trên Kubernetes mà không buộc kiến trúc runtime phải phụ thuộc vào một kiểu platform consumer duy nhất.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md)
- [Spring Cloud Open Service Broker](https://spring.io/projects/spring-cloud-open-service-broker/)
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [Kubernetes Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Spring Boot Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes Secrets and Configuration](https://kubernetes.io/docs/concepts/configuration/)
- [Kubernetes Application Security Checklist](https://kubernetes.io/docs/concepts/security/application-security-checklist/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/)
- [Kubernetes Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)
- [Retired Kubernetes Service Catalog project](https://github.com/kubernetes-retired/service-catalog)

