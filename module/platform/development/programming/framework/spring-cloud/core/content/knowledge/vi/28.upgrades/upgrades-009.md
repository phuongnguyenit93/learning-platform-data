# Triển khai thử và chuẩn bị quay lại phiên bản trước

> **Chương:** Nâng cấp  
> **Module:** SPRING_CLOUD_CORE

Một bản nâng cấp Spring Boot hoặc Spring Cloud chỉ được xem là an toàn khi ứng dụng mới có thể chạy cùng phiên bản cũ trong thời gian chuyển tiếp, hệ thống có thể phát hiện lỗi sớm và đội vận hành có đường quay lại đã được kiểm thử. Việc build thành công hoặc một Pod mới chuyển sang Ready chưa đủ để kết luận nâng cấp thành công.

Trong hệ thống phân tán, một lần nâng cấp có thể đồng thời thay đổi Spring Boot, Spring Cloud release train, discovery client, LoadBalancer, cách nạp cấu hình, actuator endpoint, bean lifecycle và hành vi giao tiếp giữa service. Các replica cũ và mới thường cùng tồn tại trong một khoảng thời gian. Chúng có thể dùng chung database, message broker, registry và cache. Vì vậy, migration cần được thiết kế để hai phiên bản cùng hoạt động an toàn trước khi loại bỏ phiên bản cũ.

Bài này xây dựng quy trình triển khai thử (canary), đánh giá tín hiệu, mở rộng rollout và rollback cho module **SPRING_CLOUD_CORE**. Trọng tâm gồm compatibility giữa các phiên bản, quản lý artifact và cấu hình, health/readiness, graceful shutdown, traffic routing, database/message contract, tiêu chí dừng và các bước phục hồi. Ví dụ dùng Kubernetes Deployment, nhưng các nguyên tắc có thể áp dụng cho nền tảng triển khai khác.

## 1. Mục tiêu của triển khai thử và rollback

Triển khai thử đưa phiên bản mới tới một phạm vi nhỏ trước. Đội vận hành quan sát hành vi thật với traffic thật hoặc traffic được chọn lọc, so sánh với phiên bản đang ổn định và chỉ mở rộng khi có đủ bằng chứng.

Rollback đưa dịch vụ về phiên bản ứng dụng đã biết là ổn định khi bản mới vượt ngưỡng lỗi hoặc không đáp ứng mục tiêu vận hành. Rollback chỉ hiệu quả nếu dữ liệu, cấu hình, API, event và dependency vẫn tương thích với phiên bản cũ.

Một quy trình nâng cấp tốt cần trả lời trước các câu hỏi:

- Phiên bản Spring Boot và Spring Cloud nào được hỗ trợ cùng nhau?
- Bản mới có thể chạy đồng thời với bản cũ không?
- Database schema và message schema có tương thích ngược không?
- Traffic được chia cho canary bằng cách nào?
- Điều kiện nào cho phép mở rộng rollout?
- Điều kiện nào buộc phải dừng hoặc rollback?
- Image, config và secret của phiên bản trước có còn sẵn để khôi phục không?
- Ai có quyền quyết định rollback và ai thực hiện?
- Sau rollback, làm sao xác nhận traffic và dữ liệu đã ổn định?

Không chờ tới lúc rollout thất bại mới tìm image cũ, cấu hình cũ hoặc câu lệnh khôi phục. Những thành phần này phải được chuẩn bị trước khi bắt đầu.

## 2. Phân biệt rolling update, canary và blue-green

Ba chiến lược này có cách chuyển traffic và mức độ kiểm soát khác nhau.

| Chiến lược | Cách hoạt động | Khi phù hợp | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Rolling update | Thay Pod cũ bằng Pod mới theo từng đợt | Thay phiên bản thường xuyên, các phiên bản có thể chạy cùng nhau | Trong rollout có thời gian hai phiên bản cùng phục vụ traffic |
| Canary | Đưa một nhóm nhỏ phiên bản mới vào nhận một phần traffic, rồi tăng dần | Thay đổi có rủi ro, cần so sánh với nhóm control | Cần cơ chế chia traffic hoặc routing có trọng số |
| Blue-green | Duy trì hai môi trường; chuyển traffic từ môi trường cũ sang môi trường mới | Cần chuyển đổi nhanh và giữ môi trường cũ để quay lại | Tốn tài nguyên và cần quản lý dữ liệu/cấu hình dùng chung |

### 2.1. Rolling update không tự động là canary

Kubernetes Deployment mặc định dùng chiến lược RollingUpdate. `maxSurge` và `maxUnavailable` điều khiển số Pod được tạo thêm và số Pod có thể unavailable trong lúc thay thế.

Rolling update giúp thay Pod theo từng bước, nhưng Service Kubernetes thông thường không tự chia traffic theo tỷ lệ giữa hai phiên bản. Khi cả Pod cũ và mới cùng Ready, chúng đều có thể nhận request theo cơ chế chọn endpoint của Service.

Nếu cần canary có tỷ lệ traffic rõ ràng, hãy dùng một trong các cách:

- Tạo Deployment riêng cho canary và route một phần traffic qua Ingress hoặc API gateway.
- Dùng service mesh hỗ trợ weighted routing.
- Dùng một nền tảng progressive delivery có khả năng điều khiển traffic và đánh giá metric.
- Chọn canary theo header, cookie, tenant hoặc nhóm người dùng nếu kiến trúc cho phép.

Không mô tả `maxSurge: 1` là “chỉ 1% traffic tới bản mới”. Đây là giới hạn số Pod trong rollout, không phải trọng số traffic.

### 2.2. Chọn chiến lược theo mức rủi ro

Một thay đổi chỉ cập nhật patch dependency và không đổi contract có thể dùng rolling update với batch nhỏ. Một lần nâng Spring Cloud release train, thay discovery provider hoặc thay đổi Config Data nên bắt đầu bằng canary độc lập để quan sát kỹ hơn. Thay đổi lớn ảnh hưởng cả routing và dữ liệu có thể cần blue-green hoặc một đợt migration nhiều bước.

## 3. Xác nhận tương thích trước khi build artifact

Spring Cloud phát hành theo release train. Mỗi train hỗ trợ một phạm vi Spring Boot nhất định. Không nâng Boot và Cloud bằng cách chọn ngẫu nhiên hai phiên bản mới nhất rồi ghép vào cùng build.

### 3.1. Dùng BOM và compatibility verifier

Quản lý các module Spring Cloud bằng Spring Cloud BOM tương ứng với release train:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`spring-cloud.version` cần được chọn theo ma trận tương thích chính thức của Spring Cloud và Spring Boot mà dự án đang dùng. Không tự override riêng phiên bản Spring Cloud Commons, Config, LoadBalancer hoặc Netflix integration nếu BOM đã quản lý chúng.

Spring Cloud có Compatibility Verifier để kiểm tra phiên bản Spring Boot trên classpath có nằm trong phạm vi mà release train chấp nhận hay không. Có thể bật verifier rõ ràng trong môi trường kiểm thử:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
~~~

Verifier giúp phát hiện một số tổ hợp phiên bản không tương thích ngay khi startup. Nó không thay thế compile test, integration test, kiểm thử contract hoặc kiểm thử tải; một ứng dụng có thể vượt qua verifier nhưng vẫn gặp lỗi do API, cấu hình hoặc hành vi runtime riêng.

Trong cấu hình Spring Cloud Commons hiện hành, verifier mặc định không được bật. Nó tập trung kiểm tra phiên bản Spring Boot được hỗ trợ bởi release train; không nên coi đây là bộ kiểm tra toàn bộ dependency graph hoặc toàn bộ API tương thích giữa các service.

Không tắt verifier chỉ để ứng dụng khởi động được khi có cảnh báo tương thích. Hãy giải quyết phiên bản bằng BOM/release train được hỗ trợ và chỉ override danh sách tương thích khi có lý do được kiểm chứng.

### 3.2. Lập ma trận phiên bản

Trước rollout, ghi lại ít nhất:

| Thành phần | Phiên bản hiện tại | Phiên bản canary | Bằng chứng |
| --- | --- | --- | --- |
| Java runtime | Phiên bản đang chạy | Phiên bản mục tiêu | Build và runtime test |
| Spring Boot | Release hiện tại | Release mục tiêu | Ma trận Spring Cloud |
| Spring Cloud release train | BOM hiện tại | BOM mục tiêu | Release notes và compatibility verifier |
| Spring Cloud Config | Module hiện tại | Module mục tiêu | Config import/profile test |
| Discovery provider | Client hiện tại | Client mục tiêu | Registry integration test |
| LoadBalancer | Module hiện tại | Module mục tiêu | Instance selection và cache test |
| Database driver | Driver hiện tại | Driver mục tiêu | Connection, transaction và migration test |
| Message client | Client hiện tại | Client mục tiêu | Producer/consumer contract test |

Ghi lại phiên bản thực tế từ artifact đã build, không chỉ phiên bản trong file quản lý dependency. Dependency transitive có thể khiến runtime classpath khác với kỳ vọng.

### 3.3. Lưu ý nâng cấp theo nhiều bước

Nếu khoảng cách phiên bản lớn, hãy chia thành các bước được hỗ trợ. Ví dụ, nâng Java hoặc Spring Boot trước, ổn định, rồi mới nâng Spring Cloud release train nếu ma trận yêu cầu. Tuy nhiên, không phải tổ hợp trung gian nào cũng hợp lệ; mỗi bước phải có BOM tương thích riêng.

Không bỏ qua release notes giữa các phiên bản liên quan. Kiểm tra các thay đổi về property đã deprecated/removed, package/class bị di chuyển, auto-configuration, Config Data, refresh behavior, discovery và security defaults.

## 4. Chuẩn bị artifact và cấu hình có thể khôi phục

Một rollback nhanh cần xác định chính xác artifact nào đang chạy và cấu hình nào đã dùng để khởi động nó.

### 4.1. Dùng image bất biến

Build một image mới và gắn tag theo version hoặc commit:

~~~text
registry.example.com/platform/order-service:2.8.0
registry.example.com/platform/order-service:2.8.1
~~~

Tốt hơn nữa, lưu image digest của từng bản phát hành. Tag có thể bị di chuyển sang image khác nếu registry cho phép ghi đè; digest xác định chính xác nội dung image.

Release record nên chứa:

- Git commit SHA.
- Image digest.
- Java version.
- Spring Boot version.
- Spring Cloud BOM/release train.
- Build ID và thời điểm build.
- Config version/label.
- Database migration đã áp dụng.
- Feature flag hoặc toggle quan trọng.
- Người/phê duyệt triển khai và kế hoạch rollback.

Không rebuild “phiên bản cũ” trong lúc sự cố nếu image đã phát hành vẫn còn. Dùng đúng artifact đã được kiểm thử để tránh tạo ra một binary khác với bản từng chạy ổn định.

### 4.2. Version hóa cấu hình

Cấu hình cũng là một phần của release. Nếu canary dùng Config Server, ghi lại label/commit của repository cấu hình hoặc revision của ConfigMap/Secret. Tránh thay đổi nội dung cấu hình dùng chung mà không có version record.

Ví dụ tên ConfigMap bất biến theo release:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service-config-r2026-11-18
immutable: true
data:
  application.yml: |
    spring:
      application:
        name: order-service
~~~

Deployment của mỗi phiên bản tham chiếu ConfigMap cụ thể. Khi rollback, Pod cũ có thể tiếp tục dùng đúng cấu hình đã kiểm thử cùng nó.

Không đưa password hoặc token vào ConfigMap. Dùng Secret hoặc secret manager, giới hạn quyền đọc và ghi nhận version/reference của secret. Với credential rotation, duy trì giai đoạn overlap để bản cũ và mới đều dùng được trong lúc rollout nếu provider hỗ trợ.

### 4.3. Không thay đổi cấu hình từ xa giữa chừng mà thiếu kiểm soát

Nếu Spring Cloud Config Server đang cung cấp cấu hình, một commit mới có thể tác động tới tất cả replica đang chạy hoặc được refresh sau đó. Tách thay đổi cấu hình khỏi thay đổi image khi có thể, và ghi rõ mỗi canary đang dùng config label nào.

Một kế hoạch rollback cần khôi phục cả:

- Image/application version.
- Config Server label hoặc ConfigMap revision.
- Secret reference nếu credential đã đổi.
- Feature flag.
- Routing rule và service selector.
- Các thay đổi deployment/environment liên quan.

## 5. Kiểm tra tương thích khi phiên bản cũ và mới cùng chạy

Trong rolling update hoặc canary, hai phiên bản có thể cùng nhận request và cùng đọc/ghi tài nguyên. Đây là điều kiện bắt buộc phải kiểm thử trước.

### 5.1. Database schema: expand rồi contract

Không triển khai một thay đổi schema phá vỡ phiên bản cũ trong cùng thời điểm với bản ứng dụng mới.

Dùng quy trình expand-contract:

1. **Expand:** thêm cột, bảng hoặc index mới theo cách phiên bản cũ vẫn chạy được.
2. **Deploy compatible code:** bản mới có thể đọc schema cũ và mới hoặc ghi theo cách tương thích.
3. **Migrate data:** backfill dữ liệu theo batch có giới hạn tải.
4. **Switch usage:** chuyển code sang field/structure mới.
5. **Observe:** xác nhận không còn reader/writer cũ phụ thuộc schema cũ.
6. **Contract:** xóa cột hoặc constraint cũ trong một release sau, khi rollback về code cũ không còn là mục tiêu.

Ví dụ đổi cột `customer_name` sang `display_name`:

| Giai đoạn | Schema | Code cũ | Code mới |
| --- | --- | --- | --- |
| Trước migration | Chỉ có `customer_name` | Đọc/ghi cột cũ | Chưa triển khai |
| Expand | Có cả hai cột | Tiếp tục dùng cột cũ | Có thể đọc/ghi cả hai |
| Chuyển tiếp | Hai cột được đồng bộ | Vẫn hoạt động | Đọc/ghi cột mới hoặc dual-write |
| Sau khi loại code cũ | Hai cột vẫn còn | Không còn instance cũ | Chỉ dùng cột mới |
| Contract | Xóa cột cũ | Không còn cần rollback code cũ | Chỉ dùng cột mới |

Không xóa cột cũ ngay khi canary đầu tiên thành công. Nếu phải rollback application, code cũ vẫn cần schema mà nó hiểu.

Nếu dùng dual-write, hai lần ghi phải được bảo đảm nhất quán trong cùng transaction khi cùng database hỗ trợ; nếu việc đồng bộ đi qua nhiều hệ thống, cần cơ chế như transactional outbox, retry có idempotency và đối soát. Không ghi cột mới thành công rồi bỏ qua lỗi ghi cột cũ, hoặc ngược lại, vì hai phiên bản có thể đọc ra hai giá trị khác nhau trong thời gian rollout.

### 5.2. Migration dữ liệu có thể không đảo ngược

Rollback Deployment không tự rollback dữ liệu đã ghi. Một migration có thể đổi format, backfill hoặc xóa dữ liệu mà code cũ không hiểu.

Trước khi migration:

- Xác định migration nào chỉ thêm cấu trúc và migration nào biến đổi/xóa dữ liệu.
- Ưu tiên migration có thể chạy trong khi cả hai phiên bản đang hoạt động.
- Back up và kiểm tra khả năng restore/PITR nếu có thao tác destructive.
- Chạy migration trên dữ liệu đại diện và đo thời gian/lock.
- Không chạy migration destructive tự động cùng lúc với canary nếu chưa có phương án phục hồi dữ liệu.

Không mặc định chạy script down migration khi rollback. Một số thay đổi dữ liệu không thể đảo ngược an toàn; restore database là một quy trình riêng và có thể gây mất các giao dịch phát sinh sau thời điểm backup.

### 5.3. API và message contract

Nếu service mới thay đổi API hoặc event schema, consumer và producer cũ có thể vẫn đang chạy. Ưu tiên thay đổi additive:

- Thêm field tùy chọn thay vì đổi kiểu field hiện có.
- Không đổi nghĩa của field cũ trong cùng release.
- Giữ endpoint cũ trong giai đoạn consumer chuyển đổi.
- Consumer bỏ qua field chưa biết nếu contract cho phép.
- Producer mới không gửi event mà consumer cũ không thể parse.
- Dùng schema version và kiểm thử backward/forward compatibility cho message.

Với event-driven system, kiểm thử cả producer mới với consumer cũ và producer cũ với consumer mới. Nếu hai hướng không tương thích, cần triển khai adapter, versioned topic hoặc thay đổi theo nhiều bước.

### 5.4. Discovery, registry và LoadBalancer

Trong thời gian nâng cấp, instance cũ và mới có thể cùng đăng ký một service ID. Hãy bảo đảm:

- Cả hai phiên bản đăng ký metadata mà client hiểu.
- Health/status của registration được provider diễn giải thống nhất.
- Client cũ không chọn instance mới nếu protocol/config không tương thích.
- Client mới vẫn gọi được instance cũ trong giai đoạn chuyển tiếp.
- Cache discovery/LoadBalancer không giữ instance lỗi quá lâu.
- Không đổi service ID hoặc port metadata theo cách làm client cũ mất khả năng tìm service.

Nếu thay discovery provider hoặc thay metadata schema, hãy triển khai compatibility layer hoặc tách service ID theo version trong thời gian chuyển tiếp.

## 6. Thiết kế canary có thể quan sát được

Canary chỉ có giá trị khi có thể phân biệt tín hiệu của bản mới với nhóm đang ổn định.

### 6.1. Tạo nhãn version

Gắn nhãn release vào Pod, metric và log:

~~~yaml
metadata:
  labels:
    app: order-service
    app.kubernetes.io/name: order-service
    app.kubernetes.io/version: "2.8.1"
    release-track: canary
~~~

Đưa version/commit vào application info hoặc structured log dưới dạng thông tin không nhạy cảm. Metric label cần giới hạn cardinality; không đưa request ID, user ID hoặc dữ liệu ngẫu nhiên vào tag.

### 6.2. Tách canary traffic

Ví dụ dùng hai Deployment:

- `order-service-stable`: phiên bản đang phục vụ chính.
- `order-service-canary`: phiên bản mới với một replica ban đầu.

Tạo Service riêng cho canary và cấu hình Ingress/service mesh/API gateway để gửi một tỷ lệ nhỏ traffic tới Service đó. Nếu nền tảng không hỗ trợ weighted routing, có thể chọn nhóm request bằng header/tenant hoặc dùng cơ chế progressive delivery phù hợp.

Không chỉ dựa vào số Pod để suy ra tỷ lệ traffic. Một replica canary có thể nhận tỷ lệ request cao hơn dự kiến nếu request phân bố không đều hoặc routing chưa được cấu hình đúng.

### 6.3. Chọn canary traffic an toàn

Bắt đầu bằng traffic ít rủi ro, nhưng vẫn đại diện cho hành vi thật:

- Request đọc trước request ghi nếu có thể.
- Nhóm tenant nội bộ hoặc người dùng thử nghiệm.
- Một tỷ lệ nhỏ request không chứa giao dịch không thể đảo ngược.
- Tránh tác vụ batch lớn trong giai đoạn đầu.
- Giữ cùng điều kiện xác thực, network và downstream như production.

Nếu cần thử write path, dùng giao dịch có khả năng đối soát hoặc dữ liệu test được tách biệt. Không để canary vô tình gửi email, thanh toán hoặc phát event trùng cho khách hàng thật mà chưa có kiểm soát.

## 7. Cấu hình rollout và readiness trên Kubernetes

Một Deployment rolling update cơ bản:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 6
  revisionHistoryLimit: 10
  minReadySeconds: 20
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: registry.example.com/platform/order-service:2.8.1
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

`maxUnavailable: 0` giữ số Pod sẵn sàng theo desired count trong khi rollout, nếu cluster có đủ tài nguyên để tạo Pod surge. `maxSurge: 1` giới hạn số Pod bổ sung. Giá trị phải phù hợp quota, capacity, connection limit và chi phí cluster.

`minReadySeconds` yêu cầu Pod giữ trạng thái Ready trong một khoảng thời gian trước khi được xem là available. `progressDeadlineSeconds` giúp nhận diện rollout bị đình trệ. Readiness probe phải kiểm tra khả năng nhận traffic; liveness probe không nên phụ thuộc vào database hoặc service ngoài có thể tạm thời lỗi.

Với ứng dụng có startup time dài hoặc biến động sau khi nâng framework, có thể dùng startup probe để Kubernetes chờ ứng dụng khởi động trước khi áp dụng liveness/readiness:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 30
~~~

Ví dụ này cho tối đa khoảng năm phút để startup probe thành công. Hãy đặt ngưỡng theo startup time thực tế; startup probe quá rộng có thể kéo dài thời gian phát hiện một lần khởi động bị treo.

### 7.1. Spring Boot readiness và liveness

Spring Boot Actuator có thể cung cấp:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Trong môi trường Kubernetes, các health group này phản ánh `ApplicationAvailability`. Mặc định Spring Boot không tự thêm mọi health indicator vào readiness. Chỉ đưa dependency ngoài vào readiness khi ứng dụng thực sự không thể phục vụ nếu dependency đó lỗi.

Các endpoint probe phải được expose và truy cập được từ port mà kubelet gọi. Nếu Actuator dùng management port riêng, cân nhắc thêm probe path trên main server port để tránh trường hợp management context khỏe nhưng web server chính không nhận request.

Không đưa database hoặc registry vào liveness một cách máy móc. Nếu dependency chung gặp sự cố, tất cả Pod có thể bị restart đồng thời và làm sự cố nặng hơn.

### 7.2. Graceful shutdown

Khi Pod cũ bị thay thế, cần cho request đang chạy hoàn tất trong khoảng thời gian shutdown:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Kubernetes cần có `terminationGracePeriodSeconds` lớn hơn hoặc bằng thời gian ứng dụng cần để dừng cùng khoảng thời gian preStop/hạ tầng liên quan. Cần căn chỉnh readiness, deregistration khỏi service registry, load balancer propagation và graceful shutdown để instance không nhận request mới trong khi đang đóng.

Không đặt timeout graceful shutdown ngắn hơn thời gian xử lý request dài nhất mà hệ thống cho phép. Ngược lại, timeout quá dài có thể kéo dài rollout và giữ tài nguyên.

## 8. Xác định baseline và tiêu chí tiếp tục/dừng

Trước canary, ghi nhận baseline từ phiên bản stable trong cùng khung thời gian và điều kiện tải gần tương đương.

### 8.1. Các tín hiệu cần theo dõi

| Nhóm | Tín hiệu |
| --- | --- |
| Availability | Tỷ lệ request thành công, HTTP 5xx, timeout, readiness failure |
| Latency | p50, p95, p99 theo endpoint và dependency |
| Saturation | CPU, memory, GC pause, thread pool, connection pool |
| Startup | Thời gian startup, lỗi bean creation, restart count |
| Discovery | Lỗi registry, thời gian cập nhật instance, số lần không tìm được instance |
| LoadBalancer | Lỗi chọn instance, request failed/discard, phân bố request theo instance |
| Config | Lỗi tải Config Server, binding failure, config version thực tế |
| Database | Connection count, lock wait, query latency, deadlock |
| Messaging | Consumer lag, retry, dead-letter queue, serialization error |
| Business | Tỷ lệ giao dịch thành công, dữ liệu sai, tác vụ bị lặp hoặc bỏ sót |

So sánh canary với stable theo tỷ lệ request và cùng loại traffic. Một nhóm canary ít request có thể có số lỗi tuyệt đối nhỏ nhưng error rate rất cao.

### 8.2. Viết ngưỡng trước khi triển khai

Đừng chọn ngưỡng sau khi đã nhìn thấy số liệu. Ghi rõ:

- Error rate tối đa được phép.
- Mức tăng p95/p99 so với baseline.
- Số lần restart hoặc readiness failure cho phép.
- Mức CPU/memory/connection tối đa.
- Mức queue lag và thời gian xử lý event.
- Các lỗi nghiệp vụ không chấp nhận được.
- Thời gian quan sát tối thiểu cho mỗi bước.

Ví dụ minh họa, không phải SLO chung:

| Điều kiện | Quyết định |
| --- | --- |
| 5xx tăng hơn 1 điểm phần trăm so với stable trong 5 phút | Dừng mở rộng và điều tra |
| p95 tăng hơn 20% trong khi traffic tương đương | Giữ canary, kiểm tra profile |
| Readiness failure lặp lại hoặc Pod crash loop | Dừng rollout |
| Database connection vượt giới hạn vận hành | Dừng mở rộng |
| Sai lệch dữ liệu hoặc giao dịch bị nhân đôi | Dừng ngay, xử lý sự cố dữ liệu |
| Canary ổn định qua chu kỳ traffic đại diện và không vi phạm SLO | Có thể tăng tỷ lệ |

Các ngưỡng thực tế phải dựa trên SLO, baseline và khả năng chịu tải của service. Với lỗi dữ liệu, bảo mật hoặc giao dịch tài chính, không cần đợi đủ cửa sổ thời gian mới dừng.

### 8.3. Quan sát đủ lâu

Một vài phút không đủ nếu service có batch job theo giờ, traffic theo khung giờ hoặc consumer xử lý event chậm. Canary phải đi qua các luồng quan trọng và chu kỳ nghiệp vụ cần thiết trước khi mở rộng.

Nếu không thể chờ hết chu kỳ, cần bổ sung replay test, synthetic transaction hoặc test môi trường staging có dữ liệu/traffic đại diện và ghi rõ phần chưa được xác minh.

## 9. Quy trình triển khai canary từng bước

Một runbook có thể áp dụng cho lần nâng Spring Cloud release train:

1. **Đóng băng thay đổi không liên quan:** tránh đồng thời đổi code, schema, config và routing không có trong phạm vi release.
2. **Ghi baseline:** snapshot metric, log, config version, dependency version và trạng thái registry.
3. **Kiểm tra preflight:** BOM/compatibility, startup test, integration test, contract test và database migration.
4. **Triển khai canary:** tạo một replica hoặc một nhóm nhỏ bằng image digest mới.
5. **Xác nhận startup:** kiểm tra log, readiness, liveness, Config Server và discovery.
6. **Chạy smoke test:** gọi các API quan trọng, xác nhận authentication, routing, persistence và messaging.
7. **Mở traffic nhỏ:** dùng routing rule đã chuẩn bị, không suy ra tỷ lệ từ replica count.
8. **So sánh với stable:** theo dõi error rate, latency, saturation và business metric.
9. **Kiểm tra tương thích chéo:** xác nhận client cũ gọi server mới và client mới gọi server cũ nếu cả hai hướng có thể xảy ra.
10. **Tăng traffic theo bước:** chỉ tăng khi mọi ngưỡng đều đạt.
11. **Mở rộng replica:** tiếp tục theo batch và giữ rollback artifact/config sẵn sàng.
12. **Kết thúc rollout:** xác nhận toàn bộ instance chạy version mới, registry sạch và không còn consumer cũ chưa xử lý.
13. **Giữ thời gian ổn định:** chưa chạy contract migration phá hủy hoặc xóa code cũ ngay trong cùng đợt.
14. **Đóng release:** lưu metric, config revision, image digest, quyết định và sự cố đã xử lý.

Nếu một bước không đạt, dừng mở rộng. Không tăng traffic chỉ vì Pod đang Ready.

## 10. Ví dụ lệnh kiểm soát rollout

Xem trạng thái:

~~~bash
kubectl rollout status deployment/order-service
kubectl get pods -l app=order-service -o wide
kubectl describe deployment/order-service
~~~

Xem lịch sử:

~~~bash
kubectl rollout history deployment/order-service
~~~

Tạm dừng một rolling update để kiểm tra:

~~~bash
kubectl rollout pause deployment/order-service
~~~

Tiếp tục khi đã xác nhận:

~~~bash
kubectl rollout resume deployment/order-service
~~~

Nếu dùng Deployment canary riêng, hãy điều khiển traffic qua gateway/service mesh tương ứng. Các lệnh rollout trên chỉ điều khiển Deployment; chúng không tự thay đổi trọng số traffic của Ingress hoặc service mesh.

## 11. Quyết định rollback

Rollback khi bản mới vi phạm điều kiện dừng hoặc có bằng chứng rõ ràng rằng nó làm giảm độ tin cậy. Không nên chờ lỗi lan rộng chỉ để thu thập thêm dữ liệu.

### 11.1. Các tín hiệu cần rollback ngay

- Giao dịch bị mất, nhân đôi hoặc ghi sai dữ liệu.
- Lỗ hổng bảo mật hoặc quyền truy cập sai.
- Canary làm tăng 5xx/timeout vượt ngưỡng đã định.
- Lỗi khởi động hoặc crash loop không thể khắc phục trong thời gian cho phép.
- Discovery/LoadBalancer không định tuyến được service quan trọng.
- Message consumer không parse được event hoặc tạo dead-letter tăng mạnh.
- Connection pool hoặc thread pool cạn kiệt.
- Config mới khiến service không thể phục vụ đúng nghiệp vụ.
- Không thể xác minh tính toàn vẹn dữ liệu sau thay đổi.

Một lỗi nghiệp vụ nghiêm trọng có thể yêu cầu dừng traffic canary ngay cả khi health endpoint vẫn báo UP.

### 11.2. Phân biệt rollback với roll-forward

Có lỗi có thể khắc phục bằng cấu hình hoặc feature flag mà không cần đổi image. Khi đó, roll-forward có thể nhanh và ít rủi ro hơn.

Rollback application phù hợp khi binary mới là nguyên nhân và bản cũ vẫn tương thích với dữ liệu/config hiện tại. Nếu schema đã thay đổi theo cách code cũ không đọc được, rollback image có thể làm sự cố nghiêm trọng hơn.

Trước khi quyết định, xác định chính xác lớp gây lỗi:

- Image/application code.
- Config Server/ConfigMap/Secret.
- Database schema/data.
- Service contract hoặc message schema.
- Routing/discovery/registry.
- Infrastructure hoặc dependency bên ngoài.

Chọn thao tác khôi phục tương ứng; không dùng `kubectl rollout undo` để kỳ vọng nó hoàn tác database, Config Server hoặc traffic routing.

## 12. Runbook rollback trên Kubernetes

Khi quyết định rollback:

1. Dừng tăng traffic và pause rollout nếu cần.
2. Chuyển traffic khỏi canary hoặc scale canary về 0 nếu kiến trúc tách Deployment.
3. Ghi lại release, config revision, metric, log và thời điểm lỗi.
4. Xác nhận database schema vẫn tương thích với phiên bản trước.
5. Khôi phục image digest hoặc Deployment revision đã biết ổn định.
6. Khôi phục config/secret reference và feature flag nếu chúng đã thay đổi.
7. Chờ rollout rollback hoàn tất.
8. Xác nhận readiness và smoke test.
9. Kiểm tra registry, LoadBalancer, queue và connection pool.
10. Theo dõi error rate và business metric sau rollback.
11. Đối soát dữ liệu/giao dịch phát sinh trong khoảng canary.
12. Ghi nhận nguyên nhân và khóa lại bước contract migration nếu chưa an toàn.

Ví dụ xem lịch sử và rollback về revision trước:

~~~bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service
~~~

Rollback về revision cụ thể:

~~~bash
kubectl rollout undo deployment/order-service --to-revision=12
kubectl rollout status deployment/order-service
~~~

Revision number trong ví dụ chỉ mang tính minh họa. Trước khi dùng, xác định revision chứa đúng image/config template cần khôi phục. Lịch sử Deployment chỉ giữ số ReplicaSet theo `revisionHistoryLimit`; nếu đặt bằng 0 thì không còn revision cũ để rollback bằng cách này.

### 12.1. Rollback canary traffic

Nếu canary dùng Deployment riêng:

- Đặt weighted route về 0% cho canary.
- Xác nhận request mới không còn đi tới canary.
- Chờ request in-flight hoàn tất hoặc drain theo chính sách.
- Scale canary về 0 hoặc giữ lại để điều tra theo chính sách sự cố.
- Giữ log/metric và image digest để phân tích.

Nếu canary dùng blue-green, chuyển route/service selector về môi trường blue đã biết ổn định. Kiểm tra DNS/cache/connection pooling của gateway để xác nhận traffic thực sự đã quay lại.

### 12.2. Khôi phục cấu hình

Nếu Config Server đã phát hành label mới, khôi phục label/reference mà bản cũ tương thích. Nếu dùng ConfigMap versioned, đổi Deployment về tên ConfigMap cũ. Nếu secret đã xoay vòng, bảo đảm credential cũ vẫn hợp lệ hoặc cấp credential tương thích trước khi rollback.

Không xóa secret cũ ngay sau khi phát hành secret mới. Giai đoạn overlap giúp cả hai phiên bản tiếp tục hoạt động trong lúc chuyển đổi.

### 12.3. Xác minh sau rollback

Rollback chỉ hoàn tất khi:

- Tất cả Pod phục vụ traffic chạy image đúng.
- Readiness ổn định và restart count không tăng bất thường.
- Routing không còn gửi request tới canary lỗi.
- Registry không còn instance cũ/new status không hợp lệ.
- Error rate và latency trở về baseline.
- Consumer lag và dead-letter queue được kiểm soát.
- Database connection và pool ổn định.
- Giao dịch trong khoảng rollout được đối soát.
- Config version và secret reference đúng với phiên bản phục hồi.

## 13. Chuẩn bị rollback cho database và message

### 13.1. Không tự động down migration khi rollback ứng dụng

Nếu migration chỉ thêm cột hoặc index và code cũ bỏ qua chúng, thường có thể giữ schema mở rộng trong lúc rollback code. Xóa cấu trúc mới ngay có thể làm mất dữ liệu hoặc phá code mới đang còn chạy ở một replica.

Nếu migration đã xóa/đổi nghĩa dữ liệu, cần kế hoạch phục hồi riêng. Có thể phải restore từ backup hoặc point-in-time recovery, nhưng thao tác này có thể loại bỏ giao dịch phát sinh sau thời điểm restore. Cần đánh giá dữ liệu trước khi thực hiện.

### 13.2. Message queue có thể giữ event từ phiên bản mới

Consumer cũ có thể đọc message do producer mới phát ra sau khi rollback. Vì vậy:

- Giữ schema event tương thích trong giai đoạn chuyển tiếp.
- Không xóa field cũ ngay khi producer mới bắt đầu chạy.
- Nếu event version mới không tương thích, route sang topic/version riêng hoặc dùng adapter.
- Theo dõi dead-letter queue và retry.
- Không purge queue để “làm sạch” lỗi nếu chưa xác định tác động dữ liệu.
- Kiểm tra idempotency khi replay message sau rollback.

### 13.3. API consumer/producer

Nếu service mới phát hành API contract mới, rollback producer có thể khiến consumer mới gọi endpoint không còn tồn tại. Giữ endpoint cũ cho tới khi consumer đã chuyển hoàn toàn hoặc có gateway adapter xử lý hai contract.

Một nguyên tắc hữu ích: deploy thay đổi mở rộng trước, chuyển consumer sau, loại bỏ contract cũ trong release riêng sau khi không còn caller.

## 14. Tự động hóa tiêu chí canary và rollback

Một pipeline progressive delivery có thể đánh giá metric trước khi tăng traffic. Quy tắc phải rõ và có thể audit:

~~~yaml
# Pseudocode minh họa, không phải schema của một controller cụ thể
canary:
  initialWeight: 5
  steps:
    - weight: 5
      duration: 10m
    - weight: 15
      duration: 15m
    - weight: 30
      duration: 20m
    - weight: 50
      duration: 30m
  analysis:
    metrics:
      - name: http_5xx_rate
        max: 0.01
      - name: p95_latency_ratio
        max: 1.20
      - name: readiness_failures
        max: 0
  onFailure: pause-and-rollback
~~~

Các con số chỉ minh họa cách thể hiện chính sách. Schema thật phụ thuộc Argo Rollouts, Flagger hoặc nền tảng progressive delivery đang dùng. Không copy pseudocode vào Kubernetes Deployment manifest.

Một pipeline tốt nên:

- Lấy baseline của stable và canary cùng cửa sổ thời gian.
- So sánh tỷ lệ lỗi, không chỉ số lỗi tuyệt đối.
- Có ngưỡng riêng cho business error và data integrity.
- Tự dừng khi metric không đủ dữ liệu.
- Ghi lại quyết định và người phê duyệt.
- Không tự động rollback database hoặc dữ liệu khi rollback application.
- Cho phép người vận hành pause khi xuất hiện tín hiệu ngoài dashboard.

Không tự động tăng traffic nếu telemetry bị mất hoặc canary chưa nhận đủ request đại diện. “Không có dữ liệu lỗi” khác với “đã chứng minh không có lỗi”.

## 15. Diễn tập rollback trước production

Rollback cần được thử trên staging hoặc môi trường có topology tương tự production.

Một buổi diễn tập nên xác minh:

1. Có thể tìm đúng image digest và Deployment revision cũ.
2. Config/Secret version cũ vẫn tồn tại và có quyền đọc.
3. Traffic có thể chuyển khỏi canary trong thời gian mục tiêu.
4. `kubectl rollout undo` hoặc quy trình GitOps đưa đúng Pod template về bản trước.
5. Readiness và graceful shutdown hoạt động.
6. Database schema hiện tại vẫn tương thích với code cũ.
7. Consumer cũ vẫn xử lý được message trong queue.
8. Discovery registry loại instance mới lỗi và giữ instance stable.
9. Metrics/log cho biết thời điểm bắt đầu, dừng và hoàn tất rollback.
10. Người trực vận hành biết ai quyết định, ai thực hiện và cách thông báo nội bộ.

Đo thời gian từ lúc quyết định rollback tới lúc traffic ổn định. So sánh với mục tiêu RTO của service. Nếu rollback kéo dài hơn thời gian chịu lỗi của nghiệp vụ, cần cải thiện automation hoặc chiến lược triển khai.

## 16. Checklist trước, trong và sau canary

### Trước triển khai

- [ ] Spring Boot và Spring Cloud BOM nằm trong ma trận tương thích.
- [ ] Compatibility verifier và startup tests đã chạy.
- [ ] Image digest, commit và dependency versions được ghi lại.
- [ ] Config/Secret version của stable và canary được lưu.
- [ ] API, database và message contract tương thích giữa hai phiên bản.
- [ ] Expand migration đã hoàn tất và không phá code cũ.
- [ ] Có baseline metric và ngưỡng stop/go.
- [ ] Có routing rule cho canary và cách đưa traffic về stable.
- [ ] Readiness/liveness và graceful shutdown đã kiểm tra.
- [ ] Rollback command và người chịu trách nhiệm đã xác định.
- [ ] Đã diễn tập rollback trong môi trường phù hợp.

### Trong triển khai

- [ ] Canary chỉ nhận traffic theo tỷ lệ đã định.
- [ ] Startup, readiness, discovery và config loading ổn định.
- [ ] Error rate và latency được so sánh với stable.
- [ ] Database, broker và connection pool chưa vượt ngưỡng.
- [ ] Không có data corruption hoặc message incompatibility.
- [ ] Mỗi bước tăng traffic có quyết định rõ ràng.
- [ ] Có thể pause ngay khi metric bất thường.

### Sau triển khai

- [ ] Toàn bộ replica chạy đúng image digest.
- [ ] Không còn instance cũ ngoài kế hoạch.
- [ ] Registry và LoadBalancer phản ánh danh sách instance mới.
- [ ] Config version và secret reference đồng nhất.
- [ ] Error rate, latency và business metric ổn định.
- [ ] Database migration chưa contract quá sớm.
- [ ] Message queue không còn backlog bất thường.
- [ ] Release record và kết quả canary đã lưu.
- [ ] Thời điểm contract migration được lên kế hoạch riêng.

## 17. Tình huống minh họa: nâng Spring Cloud release train

Giả sử `order-service` đang dùng release train cũ và cần nâng Spring Boot/Spring Cloud cùng BOM mới. Ứng dụng dùng Config Server, Eureka, LoadBalancer, PostgreSQL và Kafka.

Một kế hoạch có thể là:

1. Tạo nhánh nâng cấp, cập nhật Spring Boot và Spring Cloud BOM theo ma trận hỗ trợ.
2. Chạy unit, auto-configuration, Config Data, Eureka, LoadBalancer và Kafka integration tests.
3. Thêm cột database mới theo expand migration, giữ cột cũ.
4. Đảm bảo producer vẫn phát event tương thích với consumer cũ.
5. Build image bất biến và lưu digest cùng config label.
6. Tạo Deployment canary riêng với một replica.
7. Route 5% traffic đọc tới canary; chưa chuyển write path rủi ro cao.
8. Theo dõi startup, 5xx, p95/p99, registry, connection pool và consumer lag.
9. Tăng traffic theo từng bước khi đạt ngưỡng.
10. Khi tất cả replica dùng bản mới, tiếp tục theo dõi một chu kỳ nghiệp vụ.
11. Giữ cột database cũ và event contract cũ trong thời gian rollback window.
12. Chỉ contract schema/API ở release sau, khi không còn code cũ cần tương thích.

Nếu canary gặp lỗi do LoadBalancer không chọn đúng instance, dừng tăng traffic, chuyển traffic về stable, giữ image/log/config revision và kiểm tra discovery cache cùng provider status. Nếu lỗi do schema, không rollback image trước khi xác nhận code cũ vẫn đọc được schema hiện tại.

## 18. Lỗi thường gặp và cách tránh

1. **Coi rolling update là canary traffic:** dùng weighted routing nếu cần tỷ lệ traffic cụ thể.
2. **Nâng Boot và Cloud không theo BOM:** kiểm tra release train và compatibility verifier.
3. **Không lưu image digest cũ:** không thể chắc chắn rollback đúng binary.
4. **Dùng ConfigMap/Secret bị sửa tại chỗ:** version hóa cấu hình và lưu revision.
5. **Chỉ kiểm tra Pod Ready:** theo dõi cả business metrics, latency và lỗi downstream.
6. **Liveness phụ thuộc database:** tránh restart storm khi dependency ngoài lỗi.
7. **Không bật graceful shutdown:** request đang chạy có thể bị cắt khi Pod bị thay thế.
8. **Xóa cột database ngay sau rollout:** code cũ có thể không còn rollback được.
9. **Thay message schema không tương thích:** producer và consumer cũ/mới có thể không đọc được event.
10. **Rollback chỉ image:** cần khôi phục config, routing, feature flag và secret reference khi chúng đã đổi.
11. **Chạy down migration tự động:** có thể mất dữ liệu hoặc phá schema mà bản cũ cần.
12. **Không test rollback:** quy trình chưa diễn tập thường kéo dài hơn dự kiến.
13. **Tăng traffic khi telemetry mất:** thiếu dữ liệu không phải tín hiệu an toàn.
14. **Contract ngay sau canary:** giữ compatibility window đủ lâu cho rollback và consumer lag.

## 19. Điểm cần ghi nhớ

Triển khai thử giúp phát hiện vấn đề trước khi toàn bộ traffic chuyển sang phiên bản mới; rollback giúp khôi phục dịch vụ khi bản mới không đạt ngưỡng. Cả hai chỉ đáng tin cậy khi phiên bản cũ và mới có thể cùng chạy, artifact/config cũ còn nguyên, schema/API/message tương thích và các tiêu chí stop/go đã được định nghĩa trước.

Với **SPRING_CLOUD_CORE**, hãy dùng đúng Spring Cloud BOM, kiểm tra compatibility verifier, triển khai canary có routing rõ ràng, theo dõi readiness cùng metric nghiệp vụ, bật graceful shutdown và áp dụng expand-contract cho database. Khi rollback, khôi phục image cùng cấu hình/routing cần thiết, xác minh registry và đối soát dữ liệu. Chỉ loại bỏ schema hoặc contract cũ sau khi thời gian rollback đã kết thúc và không còn consumer cũ.

## Tài liệu tham khảo

- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Release Trains and Compatibility](https://spring.io/projects/spring-cloud#overview)
- [Spring Boot Actuator — Kubernetes Probes and Availability](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/)
- [Kubernetes — Deployment Rollback](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Martin Fowler — Evolutionary Database Design](https://martinfowler.com/articles/evodb.html)
