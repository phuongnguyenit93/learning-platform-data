# Thiết kế API stateless với container có quản lý

Một API được triển khai trên nhiều container cần có khả năng phục vụ request từ bất kỳ replica nào. Nếu phiên đăng nhập, file tạm, tiến trình đang xử lý hoặc dữ liệu nghiệp vụ chỉ tồn tại trong RAM hay filesystem cục bộ của một container, request tiếp theo có thể đến replica khác và không tìm thấy trạng thái trước đó. Khi container bị thay thế, scale-in hoặc chuyển node, trạng thái cục bộ cũng có thể mất.

**API stateless** là API không phụ thuộc vào trạng thái phiên hoặc trạng thái request được giữ riêng trong bộ nhớ của một replica để xử lý request tiếp theo. Trạng thái cần tồn tại được lưu ở dịch vụ bên ngoài có vòng đời độc lập, chẳng hạn database, cache dùng chung, object storage hoặc message queue. Container trở thành đơn vị thực thi có thể thay thế và mở rộng theo tải.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, container có quản lý có thể là workload chạy trên Kubernetes được quản lý, container application platform hoặc dịch vụ container serverless. Nền tảng hỗ trợ lập lịch, khởi chạy, health check, service discovery và scale; đội ứng dụng vẫn phải thiết kế API, dữ liệu, bảo mật, quan sát và vòng đời request để nhiều replica hoạt động nhất quán.

## 1. Stateless API là gì?

Một API stateless không yêu cầu replica đang nhận request phải nhớ những request trước đó trong local memory hoặc local disk. Mỗi request mang đủ thông tin cần thiết để xác thực, định tuyến nghiệp vụ và xử lý; dữ liệu cần dùng chung được đọc từ hệ thống lưu trữ hoặc dịch vụ độc lập.

Ví dụ:

- Client gửi access token trong mỗi request; mọi replica xác minh token bằng cùng trust configuration.
- Giỏ hàng được lưu trong database hoặc cache dùng chung; không nằm riêng trong RAM của một container.
- File upload được ghi vào object storage; API chỉ quản lý metadata và quyền truy cập.
- Công việc dài được gửi vào queue; worker xử lý độc lập với vòng đời request HTTP.
- Idempotency key được lưu bền vững để request retry không tạo giao dịch trùng.

### 1.1. Stateless không có nghĩa ứng dụng không có dữ liệu

Một hệ thống stateless vẫn có thể đọc và ghi dữ liệu nghiệp vụ. Điểm khác biệt là replica API không giữ bản trạng thái duy nhất cần thiết để request kế tiếp hoạt động.

| Trạng thái | Nơi nên lưu | Lý do |
| --- | --- | --- |
| Session đăng nhập | Token có chữ ký hoặc session store dùng chung | Request có thể đến replica bất kỳ |
| Hồ sơ và đơn hàng | Database | Dữ liệu bền vững, có transaction và backup |
| Cache | Distributed cache hoặc cache có thể tái tạo | Không phụ thuộc một container |
| File upload | Object storage hoặc persistent storage được quản lý | Container có thể bị thay thế |
| Job đang chờ | Message queue/workflow service | Tách xử lý dài khỏi HTTP request |
| Idempotency record | Database hoặc store có atomic operation | Ngăn side effect trùng |
| Request-local data | RAM của request đang xử lý | Chỉ tồn tại trong thời gian request |

### 1.2. Stateful và stateless replica

Trong mô hình stateful theo nghĩa lưu session cục bộ, client có thể phải quay lại đúng replica cũ. Điều này tạo ra sticky session và làm giảm khả năng thay thế hoặc mở rộng replica.

Với API stateless, load balancer có thể gửi request đến bất kỳ replica healthy nào. Một replica có thể bị terminate mà không làm mất session hoặc dữ liệu nghiệp vụ đã được lưu bền vững.

| Tiêu chí | API phụ thuộc state cục bộ | API stateless |
| --- | --- | --- |
| Session | Lưu trong RAM/disk của replica | Token hoặc store dùng chung |
| Load balancing | Có thể cần sticky session | Có thể phân phối đến replica bất kỳ |
| Scale-out | Phải xử lý đồng bộ trạng thái | Thêm replica độc lập |
| Scale-in | Có thể mất session hoặc job | Replica có thể drain và thay thế |
| Recovery | Cần khôi phục state của instance | Khởi tạo replica mới và kết nối dịch vụ dữ liệu |
| Deployment | Khó thay thế replica đang giữ state | Rolling update thuận lợi hơn |

Sticky session đôi khi là giải pháp chuyển tiếp, nhưng không thay thế thiết kế stateless. Nếu một replica bị lỗi, session gắn với replica đó có thể mất hoặc client phải đăng nhập lại.

## 2. Kiến trúc tham chiếu

Một API stateless chạy trên managed container platform thường có các lớp:

1. Client hoặc hệ thống gọi API.
2. DNS, CDN hoặc WAF tùy yêu cầu.
3. Load balancer hoặc ingress/API gateway.
4. Managed container platform và service discovery.
5. Nhiều replica API stateless.
6. Database, cache, object storage và message queue.
7. Observability, secret management và identity service.

~~~mermaid
flowchart TD
    C["Client / Service caller"] --> D["DNS / WAF / API Gateway"]
    D --> LB["Load balancer / Ingress"]
    LB --> S["Kubernetes Service / Container endpoint"]
    S --> P1["API replica 1"]
    S --> P2["API replica 2"]
    S --> P3["API replica N"]
    P1 --> DB["Managed database"]
    P2 --> DB
    P3 --> DB
    P1 --> CACHE["Shared cache"]
    P2 --> CACHE
    P3 --> CACHE
    P1 --> OBJ["Object storage"]
    P2 --> Q["Message queue"]
    P3 --> Q
    P1 --> OBS["Logs / metrics / traces"]
    P2 --> OBS
    P3 --> OBS
~~~

Load balancer phân phối traffic đến endpoint healthy. Service discovery cung cấp địa chỉ ổn định cho client nội bộ. Replica API không cần biết request trước đó đã được xử lý bởi container nào.

### 2.1. Luồng xử lý request

Một request đọc đơn hàng có thể đi qua các bước:

1. Client gửi HTTPS request cùng access token.
2. Gateway kiểm tra TLS, rate limit và policy ở lớp biên.
3. Load balancer chuyển request đến replica healthy.
4. Replica xác minh token và quyền truy cập.
5. API đọc đơn hàng từ database bằng workload identity.
6. API có thể đọc cache nếu dữ liệu phù hợp và cache policy cho phép.
7. API trả response có request ID và metadata cần thiết.
8. Metric, log và trace được gửi đến hệ thống quan sát.

Mọi replica phải có cùng cấu hình tương thích và quyền truy cập cần thiết. Không nên dựa vào biến toàn cục hoặc local file được tạo trong một request trước.

## 3. Externalize state: đưa trạng thái ra khỏi container

Thiết kế stateless bắt đầu bằng việc phân loại trạng thái và chọn nơi lưu phù hợp.

### 3.1. Session và authentication

Các lựa chọn phổ biến:

- **Token có chữ ký:** client gửi token trong mỗi request; API xác minh chữ ký, issuer, audience, expiry và claims.
- **Opaque session ID:** client gửi ID; API đọc session từ distributed session store.
- **OAuth/OIDC:** API xác minh access token theo issuer và key rotation của identity provider.

Token không nên chứa dữ liệu bí mật hoặc trạng thái cần thay đổi liên tục. Nếu cần thu hồi session ngay lập tức, token ngắn hạn kết hợp revocation/session store có thể phù hợp hơn token dài hạn hoàn toàn self-contained.

Không lưu session duy nhất trong local memory của pod. Nếu dùng distributed cache làm session store, cần cấu hình TTL, replication, access control và hành vi khi cache unavailable.

### 3.2. Dữ liệu nghiệp vụ

Database là nguồn dữ liệu có thẩm quyền cho entity nghiệp vụ. API nên:

- Dùng transaction phù hợp với invariant nghiệp vụ.
- Đặt timeout và giới hạn connection pool.
- Dùng migration tương thích khi rolling deployment.
- Không lưu database password trong image.
- Phân quyền theo workload identity hoặc secret có vòng đời quản lý.
- Xử lý retry có kiểm soát và idempotency cho thao tác ghi.

Không dùng filesystem tạm của container làm nơi lưu dữ liệu cần tồn tại sau restart hoặc reschedule.

### 3.3. Cache dùng chung

Cache có thể giảm tải database và latency, nhưng cần xác định:

- Cache là dữ liệu có thể tái tạo hay là session state cần độ bền cao.
- TTL và invalidation strategy.
- Cache miss có gây stampede lên database không.
- Hành vi khi cache unavailable.
- Consistency giữa cache và database.
- Network latency và chi phí liên vùng.

Cache không nên trở thành nguồn dữ liệu duy nhất nếu dữ liệu không thể tái tạo. Nếu cache chỉ là acceleration layer, API cần có fallback có giới hạn để tránh database quá tải khi cache mất.

### 3.4. File và artifact

Upload/download nên dùng object storage hoặc dịch vụ file có vòng đời độc lập:

- API cấp URL upload/download có thời hạn hoặc proxy dữ liệu theo thiết kế.
- Metadata file và quyền sở hữu lưu trong database.
- Kiểm tra content type, kích thước, checksum và malware scan theo yêu cầu.
- File được ghi vào object storage trước khi metadata chuyển sang trạng thái sẵn sàng.
- Không ghi file nghiệp vụ vào writable layer của container.

Local ephemeral storage chỉ nên dùng cho file tạm có thể tạo lại và phải có giới hạn dung lượng.

### 3.5. Công việc dài và xử lý bất đồng bộ

Request HTTP không nên giữ kết nối trong nhiều phút để xử lý công việc dài nếu có thể tách thành job:

1. API xác thực và kiểm tra yêu cầu.
2. API ghi job record hoặc tạo idempotency record.
3. API gửi message vào queue.
4. API trả 202 Accepted cùng job ID và URL tra cứu trạng thái.
5. Worker xử lý message và cập nhật trạng thái.
6. Client polling hoặc nhận callback/event khi hoàn tất.

Queue và worker có vòng đời riêng với API replica. Khi API scale-in, job vẫn nằm trong queue và worker khác có thể tiếp tục xử lý.

## 4. Thiết kế hợp đồng API để hỗ trợ nhiều replica

Statelessness không chỉ là cách lưu session. API contract cũng cần hỗ trợ retry, phân trang và request độc lập.

### 4.1. Request phải mang đủ ngữ cảnh

Mỗi request cần mang thông tin xác thực và định danh nghiệp vụ cần thiết. Tránh yêu cầu client gọi đúng replica hoặc dựa vào thứ tự request được gửi đến một kết nối cụ thể.

Ví dụ header:

~~~http
POST /v1/orders
Authorization: Bearer <access-token>
Idempotency-Key: 9d9c8f7b-5f9e-4f8e-9dcb-0a9f0d8f1d21
Content-Type: application/json
X-Request-ID: req-20261122-00042
~~~

Idempotency key giúp server nhận biết lần gửi lại của cùng một thao tác nghiệp vụ. Request ID dùng để quan sát và truy vết, không nhất thiết là khóa chống duplicate.

### 4.2. Idempotency cho thao tác ghi

Client có thể retry khi timeout nhưng không biết server đã commit transaction hay chưa. Nếu API tạo đơn hàng hai lần, hệ thống có thể phát sinh duplicate.

Một cách triển khai:

1. Client tạo idempotency key duy nhất cho thao tác.
2. API lưu key, principal, request hash và trạng thái xử lý.
3. API thực hiện transaction tạo entity và ghi kết quả gắn với key.
4. Request lặp lại với cùng key và cùng payload nhận lại kết quả đã lưu.
5. Cùng key nhưng payload khác phải bị từ chối hoặc xử lý theo contract.

Idempotency record cần có TTL/retention phù hợp với thời gian client có thể retry và yêu cầu nghiệp vụ. Việc lưu key và side effect nên có transaction boundary rõ ràng.

### 4.3. Pagination và cursor

Không nên lưu vị trí phân trang trong memory của replica. Dùng cursor hoặc continuation token có thể được xác minh và mang đủ thông tin để request tiếp theo độc lập.

Cursor cần tránh lộ thông tin nhạy cảm. Có thể ký hoặc mã hóa token và gắn với filter, sort order, tenant và version của query.

### 4.4. Không dựa vào thứ tự request

Nhiều replica có thể nhận request đồng thời. Nếu nghiệp vụ yêu cầu ordering, cần đảm bảo bằng database transaction, optimistic concurrency, sequence number, partitioned queue hoặc cơ chế khóa phù hợp. Không giả định load balancer sẽ gửi mọi request của một client đến cùng container theo đúng thứ tự.

## 5. Container image và cấu hình runtime

Container nên được đóng gói thành image bất biến, có thể triển khai lặp lại ở nhiều node và môi trường.

### 5.1. Image có thể tái tạo

- Pin base image và dependency version.
- Build image trong CI pipeline.
- Scan lỗ hổng và tạo SBOM nếu quy trình yêu cầu.
- Không nhúng credential hoặc dữ liệu môi trường vào image.
- Gắn version/digest và provenance.
- Ưu tiên image nhỏ, chỉ chứa runtime cần thiết.
- Chạy cùng một artifact qua dev, staging và production; thay cấu hình bằng runtime configuration.

### 5.2. Ví dụ Dockerfile

~~~dockerfile
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY --chown=node:node dist ./dist
USER node

EXPOSE 8080
CMD ["node", "dist/server.js"]
~~~

Đây là ví dụ cho ứng dụng Node.js đã build dist trước đó. Pipeline thực tế nên dùng multi-stage build nếu cần compiler/toolchain và pin image theo digest khi phát hành production. USER node giảm quyền của process; cấu hình runtime còn cần kiểm soát filesystem, capabilities và network.

### 5.3. Cấu hình tách khỏi image

ConfigMap hoặc cơ chế cấu hình của managed platform phù hợp với giá trị không bí mật như:

- Port và log level.
- Feature flag.
- Timeout và concurrency limit.
- Endpoint dịch vụ nội bộ.
- Tên queue hoặc bucket.

Secret manager hoặc Kubernetes Secret được tích hợp với mã hóa, RBAC và rotation phù hợp cho credential. Không đưa secret vào Dockerfile, build argument, source control, command line hoặc log.

### 5.4. Runtime filesystem

API stateless nên có thể chạy với root filesystem read-only nếu framework hỗ trợ. File tạm cần dùng thư mục tạm có giới hạn và được dọn khi process kết thúc.

Các thiết lập bảo mật thường cân nhắc:

- Chạy non-root.
- allowPrivilegeEscalation: false.
- Drop Linux capabilities không cần thiết.
- Dùng seccomp profile phù hợp.
- Read-only root filesystem.
- Resource requests/limits.
- Không mount hostPath tùy tiện.

## 6. Service discovery, ingress và network

Replica thay đổi IP khi được tạo lại hoặc chuyển node. Client nội bộ không nên cấu hình IP pod cố định.

### 6.1. Service discovery

Trong Kubernetes, Service cung cấp endpoint ổn định cho nhóm pod được chọn bằng label selector. EndpointSlice được cập nhật theo trạng thái endpoint. Service type và ingress/gateway phụ thuộc cách workload được công bố.

Trong managed container platform khác, service discovery có thể được cung cấp bằng service name, internal load balancer hoặc endpoint abstraction riêng.

### 6.2. Ingress và API gateway

API gateway hoặc ingress có thể đảm nhiệm:

- TLS termination hoặc TLS passthrough.
- Authentication ở lớp biên khi phù hợp.
- Rate limiting và quota.
- Request size limit.
- Routing theo host/path.
- WAF và policy.
- Access log và correlation header.

Các kiểm tra bảo mật và authorization nghiệp vụ vẫn cần được thực hiện trong API. Không tin header do client tự gửi nếu gateway chưa xóa và ghi lại theo quy tắc tin cậy.

### 6.3. Network segmentation

Chỉ mở kết nối cần thiết:

- Public ingress đến gateway/load balancer.
- Gateway đến API service.
- API đến database/cache/queue/object storage.
- Metrics/logging agent đến endpoint observability.

Không cần public IP cho từng pod hoặc container nếu kiến trúc có ingress riêng. Dùng private endpoint và network policy/security group để giảm bề mặt tấn công.

### 6.4. Connection pooling

Scale-out API có thể làm số kết nối database tăng đột biến. Nếu mỗi replica tạo connection pool lớn, tổng kết nối có thể vượt giới hạn database.

Tính tổng connection:

~~~text
Max DB connections from API =
    Max API replicas × Pool size per replica
  + Connections from workers and other services
~~~

Ví dụ 20 replica, mỗi replica pool 15 kết nối tạo tối đa 300 kết nối từ API. Cần tính cả worker, migration, admin và các dịch vụ khác. Dùng pooler hoặc giới hạn HPA nếu database không chịu được số kết nối đó.

## 7. Health check: startup, readiness và liveness

Health probe giúp nền tảng biết container đã khởi động, có thể nhận traffic hay cần khởi động lại.

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| Startup | Ứng dụng đã hoàn tất khởi động chưa? | Chưa đưa vào liveness/readiness cho đến khi startup đạt; quá ngưỡng thì restart |
| Readiness | Replica có thể nhận request mới không? | Loại khỏi endpoint phục vụ traffic |
| Liveness | Process còn sống và có thể tự phục hồi không? | Restart container sau số lần thất bại quy định |

Readiness không nên phụ thuộc vào mọi dịch vụ phụ trợ theo cách khiến tất cả replica đồng loạt bị loại khi một dependency phụ bị lỗi. Hãy xác định dependency nào thực sự cần để phục vụ request.

Liveness không nên kiểm tra database hoặc API bên ngoài quá sâu. Nếu database tạm thời unavailable, restart toàn bộ API có thể làm sự cố nặng hơn. Liveness nên phát hiện process bị deadlock hoặc trạng thái không thể tự phục hồi.

### 7.1. Ví dụ probes trong Kubernetes

~~~yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: http
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /health/ready
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /health/live
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Các endpoint cần có semantics rõ ràng. /health/ready nên trả trạng thái không sẵn sàng khi ứng dụng chưa nạp config hoặc chưa hoàn tất initialization thiết yếu. /health/live nên phản ánh khả năng process tiếp tục hoạt động, không chỉ việc một dependency đang trả lời.

## 8. Graceful shutdown và connection draining

Container có thể bị dừng do deployment, scale-in, node drain hoặc eviction. API cần ngừng nhận request mới và hoàn tất request đang xử lý trong thời gian cho phép.

Một quy trình shutdown:

1. Nền tảng bắt đầu termination và chạy lifecycle hook nếu cấu hình.
2. Ứng dụng chuyển readiness sang false.
3. Endpoint không còn được chọn cho request mới sau khi cập nhật routing.
4. Ứng dụng ngừng nhận request mới và chờ request đang chạy.
5. Process xử lý SIGTERM, flush telemetry và đóng connection pool.
6. Process thoát trước terminationGracePeriodSeconds; nếu quá hạn, container có thể bị kill.

### 8.1. Tránh mất request

- Đặt request timeout nhỏ hơn thời gian shutdown còn lại.
- Có deadline cho request đang xử lý.
- Không bắt đầu job dài trong request nếu không có cơ chế chuyển giao.
- Dùng queue bền vững cho background task.
- Flush log/trace nhưng không giữ shutdown vô hạn.
- Kiểm tra load balancer deregistration delay và propagation time.

preStop hook có thể gọi endpoint nội bộ để chuyển ứng dụng sang drain mode. Không nên chỉ thêm một khoảng sleep cố định mà không đo thời gian cập nhật endpoint và routing.

## 9. Autoscaling và capacity planning

API stateless thuận lợi cho horizontal scaling vì mỗi replica có thể nhận request độc lập. Tuy vậy, scale API không đồng nghĩa mọi dependency có thể scale vô hạn.

### 9.1. Chọn metric scale

Các metric có thể dùng:

- CPU utilization.
- Memory utilization nếu ứng dụng có memory pattern ổn định.
- Requests per second hoặc concurrent requests.
- Request queue/worker queue depth.
- p95 latency như tín hiệu bổ trợ.
- Custom metric phản ánh mức bận của ứng dụng.

CPU là metric dễ dùng nhưng có thể không đại diện cho workload I/O-bound hoặc bị chặn bởi database. Nên benchmark để xác định replica capacity và chọn metric phù hợp.

### 9.2. HPA và node autoscaler

Trong Kubernetes:

- Horizontal Pod Autoscaler (HPA) tăng/giảm số pod dựa trên metric.
- Cluster Autoscaler hoặc node provisioning controller bổ sung node khi pod không thể schedule vì thiếu tài nguyên.
- Managed control plane quản lý thành phần điều khiển theo dịch vụ.

HPA không tự bảo đảm có node hoặc quota. Nếu node pool đạt max, pod mới có thể Pending. Cần kiểm tra quota, subnet IP, zone capacity và resource request.

### 9.3. Ví dụ HPA

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

Ví dụ yêu cầu tối thiểu 3 và tối đa 20 replica, với mục tiêu CPU trung bình 65% trên resource request. Con số phải được hiệu chỉnh bằng load test; minReplicas 3 chỉ hợp lý nếu cluster có capacity phân bố qua các failure domain cần thiết.

### 9.4. Scale theo bottleneck

Trước khi tăng replica, xác định bottleneck:

- API CPU-bound: tăng replica hoặc chọn CPU phù hợp.
- Database-bound: giảm query, cache hợp lý, giới hạn concurrency hoặc scale database.
- Network-bound: kiểm tra egress, connection và endpoint.
- Queue-bound: tăng worker nếu dependency có capacity.
- Memory-bound: điều chỉnh memory request/limit và kiểm tra leak.

Nếu database đã đạt connection limit, tăng API replica có thể làm latency và error rate tăng. HPA cần được thiết kế cùng với connection budget và downstream capacity.

## 10. High availability và phân bố replica

API production thường cần nhiều replica và phân bố qua các node/zone để giảm điểm lỗi tập trung.

### 10.1. Topology spread

Có thể dùng topology spread constraints để phân bố replica theo zone và hostname:

~~~yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        app: orders-api
~~~

Điều kiện DoNotSchedule theo zone có thể làm pod Pending nếu cluster không có đủ domain eligible hoặc capacity. ScheduleAnyway theo hostname chỉ ưu tiên cân bằng; nó không bảo đảm mỗi node chỉ có một replica.

### 10.2. PodDisruptionBudget

PodDisruptionBudget giới hạn số pod bị gián đoạn trong các voluntary disruption được hỗ trợ, chẳng hạn drain node:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB không ngăn mọi sự cố ngoài ý muốn như node crash hoặc zone outage. Cần kết hợp nhiều replica, topology spread, readiness và capacity dự phòng.

### 10.3. Multi-zone dependency

API có thể chạy qua nhiều zone nhưng database chỉ có một primary ở một zone. Khi zone đó lỗi, API vẫn có pod healthy nhưng không thể phục vụ request cần database.

Đánh giá HA end-to-end cho:

- Database và read replica.
- Cache và queue.
- DNS, ingress và load balancer.
- Secret manager, KMS và identity endpoint.
- Object storage và private endpoint.
- Monitoring/alerting.

Availability của ứng dụng bị giới hạn bởi dependency quan trọng nhất trên đường xử lý request.

## 11. Ví dụ Deployment cho API stateless

Manifest dưới đây ghép các ý chính: nhiều replica, resource request/limit, probes, security context, shutdown grace period và topology spread. Thay image, namespace và endpoint theo môi trường thực tế.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: api
          image: registry.example.invalid/orders-api:1.8.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: PORT
              value: "8080"
            - name: DATABASE_HOST
              value: orders-db.internal
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          lifecycle:
            preStop:
              httpGet:
                path: /internal/drain
                port: http
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
~~~

Image registry là placeholder. Ứng dụng cần triển khai endpoint /internal/drain có xác thực nội bộ hoặc chỉ bind trên interface phù hợp, chuyển readiness sang false và ngừng nhận request mới. Nếu ứng dụng cần ghi file tạm, bổ sung emptyDir mount có giới hạn thay vì bật writable root filesystem.

DATABASE_HOST chỉ là ví dụ cấu hình không bí mật. Credential nên lấy qua workload identity hoặc secret integration của nền tảng; không đặt password vào manifest plain text.

### 11.1. Service nội bộ

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

Service tạo endpoint nội bộ ổn định và chọn pod có label app=orders-api. Ingress hoặc gateway có thể định tuyến traffic bên ngoài đến Service này.

### 11.2. HPA và PDB

HPA và PDB trong các ví dụ trước có thể được áp dụng cùng Deployment. Cần kiểm tra:

- HPA không scale vượt capacity node pool.
- PDB không chặn mọi thao tác drain khi số replica giảm.
- Rolling update có capacity cho maxSurge.
- Topology spread có đủ zone eligible.
- Resource request phù hợp với scheduler và HPA CPU utilization.

## 12. Security cho API container

### 12.1. Identity và least privilege

Mỗi workload nên có danh tính riêng:

- Chỉ đọc đúng secret cần thiết.
- Chỉ truy cập database/schema hoặc bucket cần dùng.
- Không dùng quyền administrator của cloud account.
- Tách identity production khỏi dev/test.
- Dùng short-lived credential hoặc workload identity khi có thể.

### 12.2. Network security

- Chỉ public gateway/ingress cần thiết.
- API chỉ nhận traffic từ nguồn được phép.
- Database/cache/queue chỉ nhận kết nối từ workload identity/network segment phù hợp.
- Giới hạn egress đến dependency được khai báo.
- Bật TLS cho traffic qua ranh giới tin cậy.
- Không coi private network là thay thế authentication/authorization.

### 12.3. Container security

- Dùng image từ registry được kiểm soát.
- Scan image và cập nhật base image.
- Chạy non-root, drop capabilities và tránh privileged container.
- Read-only filesystem nếu ứng dụng hỗ trợ.
- Không mount Docker socket hoặc hostPath không cần thiết.
- Đặt CPU/memory requests và limits.
- Cập nhật runtime và node theo chính sách nền tảng.

### 12.4. API security

- Xác thực token và kiểm tra issuer, audience, expiry.
- Authorization ở cấp resource/tenant, không chỉ kiểm tra đã đăng nhập.
- Rate limit và quota theo principal.
- Validate input và giới hạn body size.
- Chống replay hoặc duplicate cho thao tác nhạy cảm.
- Không log token, password hoặc dữ liệu cá nhân không cần thiết.
- Ghi audit cho hành động quản trị và giao dịch quan trọng.

## 13. Observability và vận hành

Khi có nhiều replica, log cục bộ của một container không đủ để hiểu toàn bộ request.

### 13.1. Structured logging

Log nên có:

- Timestamp UTC.
- Service name và version.
- Pod/instance identity.
- Request ID và trace ID.
- Route/method/status code.
- Duration.
- Error class.
- Tenant/principal ID đã được xử lý theo chính sách bảo mật.

Không ghi token, password, secret hoặc payload nhạy cảm. Log tập trung giúp tìm request dù nó được xử lý bởi replica nào.

### 13.2. Metrics

Theo dõi:

| Nhóm | Metric |
| --- | --- |
| Traffic | Request rate, concurrent requests, request size |
| Errors | 4xx/5xx, timeout, dependency errors |
| Latency | p50, p95, p99 theo route |
| Compute | CPU, memory, throttling, restart, OOM |
| Scaling | Desired/current replicas, pending pods, scale events |
| Dependency | DB pool usage, query latency, cache hit ratio, queue age |
| Lifecycle | Startup duration, readiness transition, drain duration |
| Business | Transaction success, duplicate prevention, job accepted/completed |

### 13.3. Distributed tracing

Trace context cần được truyền qua gateway, API, database client và queue message. Với xử lý bất đồng bộ, tạo span liên kết hoặc trace link để nối request khởi tạo job với worker xử lý sau đó.

## 14. Deployment, rollout và rollback

Container stateless cho phép thay replica theo từng đợt nếu ứng dụng xử lý shutdown và compatibility đúng cách.

### 14.1. Rolling update

Rolling update thay dần pod cũ bằng pod mới:

- maxSurge cho phép tạo thêm pod trong lúc update.
- maxUnavailable giới hạn số pod không sẵn sàng theo chiến lược rollout.
- Readiness probe ngăn pod chưa sẵn sàng nhận traffic.
- Graceful shutdown giúp pod cũ hoàn tất request.

Đảm bảo capacity đủ cho surge. Nếu node pool đã đầy, pod mới có thể Pending và rollout bị chậm.

### 14.2. Backward-compatible change

Ứng dụng và database thường không được deploy đồng thời tức thì. Dùng chiến lược expand-and-contract:

1. Thêm schema/field mới theo cách phiên bản cũ vẫn chạy được.
2. Deploy API có thể đọc/ghi tương thích cả schema cũ và mới.
3. Backfill hoặc chuyển dữ liệu.
4. Chuyển client/traffic sang phiên bản mới.
5. Sau khi xác minh, loại bỏ field/API cũ trong một lần phát hành sau.

Không deploy schema phá vỡ tương thích trước khi mọi replica cũ đã dừng.

### 14.3. Canary và blue-green

Canary đưa một phần traffic vào phiên bản mới để quan sát lỗi và latency. Blue-green chạy hai môi trường song song và chuyển traffic khi môi trường mới đạt tiêu chí.

Với API stateless, hai phiên bản có thể chạy đồng thời nếu:

- API contract tương thích.
- Database schema hỗ trợ cả hai phiên bản.
- Session/token và cache format không bị thay đổi đột ngột.
- Queue message schema có version.
- Rollback không làm mất dữ liệu do phiên bản mới đã ghi.

## 15. Reliability và xử lý dependency failure

API stateless vẫn có thể thất bại nếu database, cache hoặc queue không sẵn sàng.

### 15.1. Timeout và retry

- Mỗi dependency call cần timeout hữu hạn.
- Retry chỉ với lỗi transient.
- Dùng exponential backoff và jitter.
- Đặt retry budget để không khuếch đại tải.
- Dùng circuit breaker hoặc bulkhead khi phù hợp.
- Không retry thao tác ghi nếu chưa có idempotency.

### 15.2. Degraded mode

Nếu cache unavailable nhưng database còn hoạt động, API có thể bỏ qua cache trong giới hạn concurrency. Nếu một chức năng phụ không thiết yếu lỗi, có thể trả response một phần theo contract.

Không nên chuyển tất cả lỗi thành HTTP 200 hoặc trả dữ liệu giả. Response degraded cần rõ ràng, có metric và không vi phạm invariant nghiệp vụ.

### 15.3. Request deadline

Deadline tổng của request cần lớn hơn tổng timeout của các bước bắt buộc nhưng nhỏ hơn giới hạn của gateway/client. Không để API giữ connection vô hạn khi dependency bị treo.

## 16. Kiểm thử khả năng stateless và scale

Một API chỉ được xem là stateless sau khi đã kiểm tra hành vi khi replica bị thay thế và request được phân phối khác nhau.

Các bài kiểm thử:

1. Gửi request đầu đến replica A và request tiếp theo đến replica B.
2. Restart hoặc terminate một replica khi có traffic.
3. Scale từ min replicas lên peak replicas.
4. Scale-in khi có request đang xử lý.
5. Làm cache hoặc database chậm trong môi trường thử.
6. Gửi lại cùng idempotency key sau timeout.
7. Rolling update khi đang có traffic.
8. Mô phỏng node drain hoặc một zone unavailable.
9. Kiểm tra file upload và job không phụ thuộc local filesystem.
10. Xác minh không có secret hoặc session nhạy cảm trong log/image.

### 16.1. Tiêu chí kiểm thử

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Request đến replica bất kỳ | Cùng contract và authorization behavior |
| Replica bị terminate | Request mới được chuyển đến replica healthy |
| Session | Không mất do container restart |
| File | Vẫn truy cập qua storage bền vững |
| Job dài | Tiếp tục qua queue/worker, không phụ thuộc API process |
| Duplicate request | Idempotency ngăn side effect trùng |
| Scale-out | Pod mới healthy trước khi nhận traffic |
| Scale-in | Request đang chạy được drain trong grace period |
| Dependency outage | Timeout/retry/degraded behavior có giới hạn |
| Rollback | Phiên bản cũ vẫn tương thích dữ liệu đã ghi |

## 17. Troubleshooting

### 17.1. Request đôi khi mất session

Kiểm tra session có nằm trong local memory hoặc filesystem không. Nếu có, chuyển sang token hoặc session store dùng chung. Sticky session có thể giảm triệu chứng nhưng không giải quyết failure khi replica bị mất.

### 17.2. Pod Ready nhưng API trả lỗi

Readiness probe có thể chỉ kiểm tra process chứ chưa kiểm tra cấu hình hoặc dependency thiết yếu. Kiểm tra semantics của endpoint readiness, startup initialization và log lỗi ứng dụng. Tránh làm readiness phụ thuộc mọi dịch vụ phụ không cần thiết.

### 17.3. Scale-out làm database quá tải

Tính tổng connection pool theo max replicas, worker và service khác. Giới hạn pool/concurrency, dùng connection proxy nếu phù hợp, tối ưu query và cân nhắc scale database.

### 17.4. Rolling update bị treo

Kiểm tra pod mới Pending do resource, topology, image pull, secret hoặc probe. Kiểm tra maxSurge, maxUnavailable, node capacity và thời gian startup. Không tăng timeout vô hạn để che lỗi readiness.

### 17.5. Request bị cắt khi scale-in

Kiểm tra readiness chuyển false, preStop hook, SIGTERM handling, load balancer draining và terminationGracePeriodSeconds. Đặt request deadline phù hợp và chuyển tác vụ dài sang queue.

### 17.6. Cache mất làm database tăng tải

Kiểm tra cache miss storm, retry và concurrency. Dùng request coalescing, rate limit, TTL jitter hoặc fallback có giới hạn. Không để tất cả replica đồng thời tải lại cùng một tập dữ liệu lớn.

## 18. Các lựa chọn managed container platform

Mô hình vận hành khác nhau theo nền tảng:

| Nhóm nền tảng | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Managed Kubernetes | Amazon EKS, Azure Kubernetes Service, Google Kubernetes Engine | Provider quản lý một phần control plane; người dùng quản lý workload, policy, node/capacity theo cấu hình |
| Managed container service | Amazon ECS với capacity provider hoặc Fargate | Điều phối task/service, tích hợp load balancer và autoscaling theo mô hình dịch vụ |
| Serverless container platform | Google Cloud Run, Azure Container Apps, AWS App Runner | Provider quản lý phần lớn hạ tầng container; scale theo request/event và cấu hình concurrency/minimum instance |

Tên tính năng và trách nhiệm cụ thể thay đổi theo dịch vụ, mode và region. Managed không có nghĩa provider chịu trách nhiệm cho API contract, dữ liệu, IAM, secret, SLO hoặc logic phục hồi của ứng dụng.

### 18.1. Khi chọn managed Kubernetes

Phù hợp khi cần:

- Nhiều service dùng chung platform.
- Scheduling, policy và network control phong phú.
- Custom controller/operator hoặc workload đặc thù.
- Kiểm soát topology, resource và rollout chi tiết.

Đổi lại, đội ngũ cần năng lực quản lý cluster, node, ingress, storage, upgrade và security.

### 18.2. Khi chọn managed/serverless container

Phù hợp khi:

- Muốn giảm việc quản lý node và cluster.
- Workload HTTP/event có thể scale theo request.
- Runtime và network model của dịch vụ đáp ứng ứng dụng.
- Chấp nhận giới hạn về execution, concurrency hoặc cấu hình hệ thống.

Kiểm tra cold start, minimum instances, scale-to-zero, request timeout, max concurrency, network egress và giới hạn region trước khi quyết định.

## 19. Checklist thiết kế API stateless

**Application**

- [ ] Request không phụ thuộc local session hoặc memory của replica trước.
- [ ] Session/token có thể xác minh ở mọi replica.
- [ ] Dữ liệu nghiệp vụ lưu ở database/storage có vòng đời độc lập.
- [ ] File và job dài không phụ thuộc local filesystem/process.
- [ ] Thao tác ghi có idempotency hoặc cơ chế chống duplicate.
- [ ] API có timeout, pagination và contract rõ ràng.

**Container**

- [ ] Image bất biến, có version/digest và được scan.
- [ ] Không nhúng secret vào image hoặc manifest.
- [ ] Chạy non-root và giảm privilege.
- [ ] Resource requests/limits phù hợp.
- [ ] Filesystem read-only nếu có thể; temp storage có giới hạn.

**Platform**

- [ ] Service discovery và ingress được cấu hình.
- [ ] Readiness, liveness và startup probes có semantics riêng.
- [ ] Graceful shutdown và connection draining hoạt động.
- [ ] HPA/node autoscaling có capacity và quota phù hợp.
- [ ] Replica được phân bố theo node/zone theo yêu cầu.
- [ ] PDB và rollout strategy không chặn deployment.

**Data và security**

- [ ] Database connection budget phù hợp max replicas.
- [ ] Cache có TTL, invalidation và fallback.
- [ ] Object storage có policy và lifecycle.
- [ ] Workload identity có quyền tối thiểu.
- [ ] Network policy, TLS, audit và secret rotation được cấu hình.

**Operations**

- [ ] Log/metric/trace có request ID và trace ID.
- [ ] Theo dõi latency, error, saturation và dependency health.
- [ ] Có alert cho Pending pod, restart, OOM và scale failure.
- [ ] Có rollout, rollback và migration tương thích.
- [ ] Đã thử terminate replica, scale-out, scale-in và dependency outage.

## 20. Quy trình triển khai

1. Phân loại state của ứng dụng: session, dữ liệu nghiệp vụ, file, cache và background job.
2. Chuyển state cần tồn tại sang database, cache dùng chung, object storage hoặc queue.
3. Thiết kế request contract có authentication, authorization, idempotency và pagination.
4. Đóng gói API thành image bất biến, non-root và không chứa secret.
5. Cấu hình runtime, workload identity và network access tối thiểu.
6. Triển khai nhiều replica sau Service/ingress hoặc managed endpoint.
7. Cấu hình startup/readiness/liveness và graceful shutdown.
8. Đặt resource request/limit, autoscaling và capacity buffer.
9. Cấu hình multi-zone placement, PDB và rollout strategy.
10. Tích hợp log, metric, trace và alert.
11. Kiểm thử replica replacement, retry, scale và dependency failure.
12. Phát hành dần, theo dõi SLO/cost và điều chỉnh theo tải thực tế.

## 21. Nguyên tắc vận hành

1. **Replica có thể thay thế:** không giữ trạng thái nghiệp vụ duy nhất trong RAM hoặc filesystem cục bộ.
2. **Externalize state:** dùng database, cache, object storage và queue theo đúng vai trò.
3. **Request độc lập:** mọi replica xác thực và xử lý request theo cùng contract.
4. **Idempotency cho side effect:** retry không tạo giao dịch hoặc job trùng.
5. **Image bất biến:** cùng artifact được triển khai qua môi trường, cấu hình được cấp lúc runtime.
6. **Health probe đúng mục đích:** phân biệt startup, readiness và liveness.
7. **Shutdown có kiểm soát:** drain request, xử lý SIGTERM và đóng connection trước khi hết grace period.
8. **Scale theo bottleneck:** bảo vệ database, cache và queue khỏi việc scale API quá mức.
9. **HA end-to-end:** phân bố replica qua failure domain và đánh giá cả dependency.
10. **Quan sát toàn hệ thống:** correlation ID, trace, metric và log phải xuyên qua mọi replica.

API stateless với container có quản lý giúp ứng dụng mở rộng theo tải, thay thế replica khi lỗi và triển khai phiên bản mới với ít phụ thuộc vào từng máy. Lợi ích này chỉ đạt được khi session, dữ liệu, file và công việc dài được đưa ra khỏi vòng đời container; request có idempotency; health check và shutdown phản ánh đúng trạng thái phục vụ; đồng thời database, network và các dependency có đủ capacity. Khi các phần này được thiết kế đồng bộ, container trở thành đơn vị thực thi linh hoạt và có thể phục hồi trong một kiến trúc API đáng tin cậy.
