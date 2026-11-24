# Triển khai thử, kiểm tra kết nối và rollback thay đổi tích hợp

Một thay đổi tích hợp cloud có thể làm ứng dụng lỗi dù mã nguồn đã biên dịch và unit test đều đạt. Phiên bản mới có thể dùng sai region, thiếu quyền IAM/RBAC, trỏ đến queue hoặc bucket khác, không phân giải được endpoint riêng, hoặc thay đổi cách xử lý message khiến dữ liệu bị lặp. Vì vậy, triển khai cần có bước thử nghiệm trên môi trường kiểm soát, kiểm tra bằng chính danh tính và đường mạng của workload, theo dõi sau khi nhận traffic, cùng phương án rollback đã được chuẩn bị.

Trong module `SPRING_CLOUD_PROVIDER_INTEGRATION`, bài học này hướng dẫn quy trình đưa thay đổi Spring Boot tích hợp dịch vụ managed của AWS, Azure và Google Cloud vào môi trường chạy. Trọng tâm là kiểm chứng hành vi thực tế, phát hiện lỗi sớm, giới hạn phạm vi ảnh hưởng và khôi phục phiên bản ổn định khi cần.

## Mục tiêu

Sau bài học, bạn có thể:

- Lập kế hoạch triển khai thử cho thay đổi endpoint, identity, storage, messaging hoặc cấu hình cloud.
- Kiểm tra kết nối, xác thực, quyền và hành vi nghiệp vụ từ đúng môi trường runtime.
- Chọn rolling, canary hoặc blue-green phù hợp với mức độ rủi ro.
- Theo dõi health check, log, metric và trace để quyết định tiếp tục hay dừng rollout.
- Rollback ứng dụng và cấu hình an toàn, kể cả khi thay đổi liên quan đến schema hoặc message.
- Phân biệt rollback phần mềm với thao tác khôi phục dữ liệu và tài nguyên cloud.

## 1. Vì sao cần triển khai thử

Unit test thường chạy với mock hoặc dependency giả lập. Chúng kiểm tra logic của ứng dụng nhưng không chứng minh rằng workload trong VPC, VNet hoặc VPC network có thể kết nối đến dịch vụ managed. Integration test có thể chạy trong môi trường phát triển, nhưng vẫn khác production về DNS, route, firewall, workload identity, quota, region và chính sách tài nguyên.

Một thay đổi tích hợp có thể ảnh hưởng đến nhiều lớp:

| Loại thay đổi | Rủi ro khi triển khai | Bằng chứng cần kiểm tra |
|---|---|---|
| Endpoint hoặc region | Gọi nhầm tài nguyên, DNS sai, TLS không khớp | Hostname, region, địa chỉ DNS, chứng thư và tài nguyên đích |
| IAM, RBAC hoặc workload identity | Ứng dụng khởi động được nhưng request bị từ chối | Danh tính runtime và thao tác tối thiểu được cấp quyền |
| Storage | Đọc được nhưng ghi, mã hóa hoặc truy cập object thất bại | Upload, đọc lại metadata/nội dung, quyền và mã hóa |
| Messaging | Không publish/consume, message bị lặp hoặc vào dead-letter queue | Gửi, nhận, ack, retry, ordering và DLQ |
| Cơ sở dữ liệu | Sai kết nối, migration không tương thích, pool cạn | Kết nối, truy vấn kiểm tra, migration và latency |
| Secret hoặc cấu hình | Thiếu secret, sai version hoặc lộ thông tin nhạy cảm | Tải secret bằng identity runtime và kiểm tra version |
| Thư viện Spring Cloud/SDK | Thay đổi hành vi retry, timeout, serialization hoặc endpoint | Kiểm thử tương thích và metric của request thực tế |

Triển khai thử giúp xác nhận cả cấu hình hạ tầng và hành vi ứng dụng trước khi mở rộng phạm vi người dùng. Môi trường thử nghiệm nên gần production về topology, DNS, identity và phiên bản dịch vụ, nhưng dùng dữ liệu và tài nguyên được cô lập.

## 2. Chuẩn bị trước khi rollout

### 2.1. Ghi nhận trạng thái hiện tại

Trước khi triển khai, ghi lại:

- Phiên bản ứng dụng đang chạy và image digest hoặc artifact version.
- Phiên bản cấu hình, secret reference và feature flag liên quan.
- Region, project/subscription/account, tên tài nguyên và endpoint được ứng dụng sử dụng.
- Danh tính runtime, vai trò và quyền quan trọng.
- Số replica, mức traffic, error rate, latency, queue backlog và dead-letter count.
- Phiên bản schema database hoặc message contract có liên quan.
- Các cảnh báo đang tồn tại để phân biệt lỗi cũ với lỗi mới.

Dùng artifact bất biến đã được kiểm thử. Tránh build lại một image cùng tag trong lúc rollout vì tag có thể trỏ đến nội dung khác nhau giữa các node. Ghi lại image digest để có thể triển khai lại chính xác phiên bản ổn định.

### 2.2. Kiểm tra tính tương thích của cấu hình

Tách cấu hình theo môi trường bằng biến môi trường, ConfigMap, secret manager hoặc cơ chế cấu hình của nền tảng. Các giá trị cần kiểm tra thường gồm:

- Region và tên tài nguyên: queue, topic, bucket, container, database hoặc subscription.
- Endpoint URL và chế độ private/public.
- Timeout, retry, connection pool và giới hạn concurrency.
- Workload identity, managed identity hoặc service account.
- Secret reference và version đang sử dụng.
- Feature flag điều khiển luồng tích hợp mới.

Có thể dùng Spring Boot externalized configuration để đưa giá trị theo môi trường vào ứng dụng:

```yaml
# application.yml
app:
  cloud:
    region: ${APP_CLOUD_REGION}
    orders-queue: ${ORDERS_QUEUE_NAME}
    connect-timeout: 2s
    read-timeout: 5s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Không đặt access key, client secret hoặc nội dung secret trực tiếp trong file cấu hình được commit. Chỉ expose các actuator endpoint cần thiết và giới hạn quyền truy cập theo chính sách vận hành.

### 2.3. Chuẩn bị tài nguyên và quyền trước ứng dụng

Nếu phiên bản mới cần queue, topic, bucket, secret hoặc quyền mới, hãy tạo và xác minh chúng trước khi chuyển traffic. Ưu tiên thay đổi theo hướng tương thích ngược:

1. Tạo tài nguyên mới hoặc mở rộng schema.
2. Cấp quyền tối thiểu cho identity của phiên bản mới.
3. Kiểm tra DNS, route, firewall và private endpoint.
4. Triển khai ứng dụng có khả năng làm việc với cả cấu trúc cũ và mới nếu cần.
5. Chuyển traffic hoặc bật feature flag.
6. Chỉ xóa tài nguyên cũ sau thời gian ổn định và khi chắc chắn không còn phiên bản nào sử dụng.

Không xóa queue, subscription, bucket, secret version hoặc cột dữ liệu cũ ngay trong cùng lần rollout nếu ứng dụng cũ vẫn có thể cần chúng để rollback.

## 3. Kiểm tra từ môi trường runtime thực tế

Một phép thử từ laptop hoặc máy CI không thay thế được kiểm tra từ pod, VM, container hoặc dịch vụ serverless thực sự chạy ứng dụng. Hai môi trường có thể dùng DNS resolver, route, firewall, proxy, certificate store và identity khác nhau.

Nên kiểm tra theo thứ tự sau:

### 3.1. DNS và đường mạng

Xác minh hostname được phân giải đúng trong môi trường chạy:

```bash
getent hosts <service-hostname>
```

Nếu container không có `getent`, có thể dùng công cụ DNS sẵn có như `nslookup` hoặc `dig`. Khi dùng private endpoint, đối chiếu địa chỉ trả về với mạng và endpoint dự kiến.

Tiếp theo kiểm tra TCP và TLS trên đúng cổng của dịch vụ:

```bash
nc -vz <service-hostname> 443

openssl s_client \
  -connect <service-hostname>:443 \
  -servername <service-hostname>
```

Cổng 443 chỉ là ví dụ cho API HTTPS. Cơ sở dữ liệu, cache hoặc giao thức khác có thể dùng cổng khác. Giữ hostname trong TLS handshake để kiểm tra SNI và chứng thư. Không chuyển sang gọi bằng IP hoặc tắt xác minh chứng thư để né lỗi.

### 3.2. Identity và quyền

Kết nối TCP thành công không chứng minh identity có quyền thao tác. Hãy kiểm tra ứng dụng đang dùng đúng danh tính của workload:

- AWS: xác minh IAM role hoặc cơ chế workload identity được gắn với workload; kiểm tra quyền trên đúng resource ARN và region.
- Azure: xác minh managed identity hoặc service principal được chọn; kiểm tra role assignment ở đúng scope của subscription, resource group hoặc resource.
- Google Cloud: xác minh service account hoặc Workload Identity Federation; kiểm tra IAM binding trên đúng project và resource.

Chạy phép thử bằng chính runtime identity. Tránh dùng credential cá nhân của kỹ sư để kiểm tra thay cho workload vì kết quả có thể che giấu lỗi phân quyền khi triển khai.

### 3.3. Kiểm tra thao tác nghiệp vụ nhỏ nhất

Sau DNS, TCP, TLS và identity, thực hiện một thao tác nhỏ, có thể quan sát và có thể dọn dẹp. Chọn thao tác tương ứng với tích hợp:

| Tích hợp | Phép thử đề xuất | Điều cần xác nhận |
|---|---|---|
| Object storage | Ghi một object thử vào prefix riêng, đọc lại rồi xóa | Bucket/container đúng, quyền ghi/đọc/xóa, mã hóa và metadata |
| Queue | Gửi message có correlation ID thử nghiệm, nhận và ack | Đúng queue, serialization, quyền publish/consume và ack |
| Pub/sub | Publish event thử vào topic kiểm thử, xác nhận subscription nhận được | Topic, subscription, quyền và delivery |
| Database | Mở kết nối và chạy truy vấn kiểm tra chỉ đọc | Endpoint, TLS, identity, schema và connection pool |
| Secret manager | Đọc một secret kiểm thử hoặc version được phép | Quyền đọc, version, định dạng và cơ chế refresh |
| API nội bộ | Gọi endpoint kiểm tra hoặc truy vấn read-only | DNS, TLS, token, timeout và response contract |

Không gửi dữ liệu giả vào queue production nếu consumer có thể xử lý nó như đơn hàng hoặc giao dịch thật. Dùng tài nguyên thử riêng, correlation ID dễ nhận biết và quy trình dọn dẹp rõ ràng. Nếu buộc phải kiểm tra trên production, chọn thao tác read-only hoặc một luồng thử đã được thiết kế để không tạo side effect nghiệp vụ.

### 3.4. Chạy smoke test bằng cùng cấu hình triển khai

Smoke test nên chạy trong job hoặc pod tạm thời dùng cùng image, network policy và workload identity với ứng dụng. Bài kiểm tra cần trả về kết quả rõ ràng theo từng dependency, chẳng hạn DNS đạt, TLS đạt, xác thực đạt, thao tác read-only đạt.

Ví dụ, một interface kiểm tra có thể được triển khai riêng cho từng provider:

```java
// CloudIntegrationProbe.java
public interface CloudIntegrationProbe {
    ProbeResult verify();
}
```

```java
// ProbeResult.java
public record ProbeResult(
        boolean reachable,
        boolean authorized,
        String dependency
) {
    public boolean successful() {
        return reachable && authorized;
    }
}
```

Job smoke test gọi adapter tương ứng và kết thúc với exit code khác 0 nếu kiểm tra thất bại. Không ghi token, secret, connection string hoặc payload nhạy cảm vào output. Với từng provider, adapter nên gọi một API nhẹ, có quyền tối thiểu và không tạo side effect không cần thiết.

## 4. Health check và readiness của Spring Boot

Spring Boot Actuator cung cấp health endpoint để nền tảng kiểm tra trạng thái ứng dụng. Khi bật probe, Spring Boot cung cấp các nhóm health dành cho liveness và readiness:

- **Liveness** trả lời ứng dụng có còn hoạt động để tiếp tục chạy hay cần được khởi động lại.
- **Readiness** trả lời instance có sẵn sàng nhận traffic hay chưa.

Ví dụ cấu hình:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Các endpoint thường dùng trong Kubernetes là:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Liveness không nên phụ thuộc trực tiếp vào dịch vụ cloud bên ngoài. Nếu queue hoặc database tạm thời mất kết nối, việc restart liên tục mọi pod có thể làm tình hình tệ hơn. Readiness có thể bao gồm dependency bắt buộc nếu ứng dụng thực sự không thể phục vụ request khi dependency đó lỗi; phép kiểm tra phải có timeout ngắn và tránh tạo tải lớn.

Một health indicator tùy chỉnh có thể mô tả trạng thái tích hợp:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("cloudIntegration")
class CloudIntegrationHealthIndicator implements HealthIndicator {

    private final CloudIntegrationProbe probe;

    CloudIntegrationHealthIndicator(CloudIntegrationProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        ProbeResult result = probe.verify();

        if (result.successful()) {
            return Health.up()
                    .withDetail("dependency", result.dependency())
                    .build();
        }

        return Health.down()
                .withDetail("dependency", result.dependency())
                .withDetail("reason", "integration check failed")
                .build();
    }
}
```

Health indicator chỉ nên được đưa vào readiness group khi dependency đó thực sự quyết định khả năng phục vụ. Cấu hình nhóm health có thể chỉ định thành phần cần tham gia:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,cloudIntegration
```

Trong môi trường production, cân nhắc dùng cache ngắn hoặc cơ chế kiểm tra nền để tránh mỗi lần kubelet gọi health endpoint lại tạo một request mới đến dịch vụ managed. Không trả chi tiết exception, hostname nội bộ hoặc tên resource nhạy cảm ra endpoint public.

## 5. Chọn chiến lược triển khai

Không có một chiến lược phù hợp cho mọi thay đổi. Chọn theo mức độ rủi ro, khả năng tách traffic, thời gian khởi động và khả năng tương thích dữ liệu.

| Chiến lược | Cách hoạt động | Ưu điểm | Điểm cần lưu ý |
|---|---|---|---|
| Rolling update | Thay instance theo từng nhóm | Dễ áp dụng, giảm thời gian gián đoạn | Phiên bản cũ và mới chạy song song; cần tương thích cấu hình và message |
| Canary | Chuyển một tỷ lệ nhỏ traffic sang phiên bản mới | Phát hiện lỗi với phạm vi ảnh hưởng nhỏ | Cần routing và metric đủ tốt để so sánh |
| Blue-green | Dựng môi trường mới song song rồi chuyển traffic | Chuyển đổi nhanh và có đường quay lại rõ ràng | Tốn tài nguyên; phải xử lý session, queue consumer và dữ liệu dùng chung |
| Feature flag | Triển khai code nhưng bật tính năng theo nhóm | Tách phát hành code khỏi thời điểm kích hoạt | Cần quản lý trạng thái flag và dọn code cũ |

### 5.1. Rolling update

Rolling update thay từng instance trong khi các instance khác tiếp tục phục vụ. Với Kubernetes, cấu hình cơ bản có thể giới hạn số pod bị thiếu trong quá trình cập nhật:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: registry.example/order-service@sha256:<image-digest>
          ports:
            - containerPort: 8080
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
```

Đây là cấu hình minh họa; cần điều chỉnh số replica, thời gian probe và tài nguyên theo ứng dụng. `startupProbe` cho phép ứng dụng có thời gian khởi động mà không bị liveness probe đánh giá quá sớm. Readiness probe ngăn pod chưa sẵn sàng nhận traffic.

Rolling update không tự tạo canary theo tỷ lệ phần trăm. Nếu cần giới hạn traffic theo phiên bản, cần ingress controller, service mesh hoặc nền tảng triển khai có hỗ trợ phân chia traffic.

### 5.2. Canary

Canary triển khai phiên bản mới cho một nhóm nhỏ request hoặc người dùng. Ví dụ, chuyển 5% traffic sang phiên bản mới, theo dõi trong một khoảng thời gian đủ để quan sát các chu kỳ nghiệp vụ, rồi tăng lên 25%, 50% và 100% nếu các chỉ số đạt ngưỡng.

Không chỉ theo dõi HTTP 5xx. Với tích hợp managed, cần quan sát thêm:

- Tỷ lệ lỗi theo từng dependency và loại thao tác.
- Timeout, retry và số request bị throttling.
- Message publish/consume failure, backlog và dead-letter count.
- Storage operation failure và thời gian hoàn thành.
- Connection pool usage, thread pool và memory.
- Latency p95/p99 của các request có gọi dịch vụ cloud.

So sánh canary với nhóm phiên bản ổn định trong cùng khoảng thời gian. Nếu nhóm mới có lỗi tăng bất thường, dừng tăng traffic và chuyển về phiên bản cũ.

### 5.3. Blue-green

Blue-green duy trì hai môi trường tương đương. Môi trường blue đang nhận traffic; môi trường green chạy phiên bản mới và được kiểm tra trước. Khi smoke test, health check và metric đạt yêu cầu, bộ định tuyến chuyển traffic sang green.

Giữ blue sẵn sàng trong thời gian quan sát để có thể chuyển traffic ngược lại. Tuy nhiên, blue và green có thể cùng truy cập một database hoặc queue. Nếu phiên bản mới đã ghi dữ liệu theo schema hoặc message format mà phiên bản cũ không hiểu, chuyển traffic lại không đảm bảo rollback thành công. Phải thiết kế tương thích dữ liệu trước khi triển khai.

## 6. Theo dõi sau khi triển khai

Sau khi pod hoặc instance trở thành Ready, tiếp tục theo dõi trong một cửa sổ ổn định. Health endpoint chỉ là một tín hiệu; ứng dụng có thể trả health 200 nhưng vẫn gửi message sai topic hoặc không xử lý được payload thực tế.

### 6.1. Ba nguồn quan sát

- **Metric:** tỷ lệ request thành công, latency, retry, throttling, queue lag, dead-letter count, số kết nối và tỷ lệ lỗi theo dependency.
- **Log:** ghi operation, resource alias, kết quả, error category và correlation ID; loại bỏ credential, token và payload nhạy cảm.
- **Trace:** theo dõi một request từ API của ứng dụng qua SDK/client đến dịch vụ managed. Gắn trace context hoặc correlation ID qua message nếu hệ thống hỗ trợ.

Nên gắn nhãn phiên bản ứng dụng, môi trường, provider, region và dependency để so sánh trước/sau rollout. Tránh dùng ID người dùng hoặc resource ID có độ đa dạng cao làm metric label.

### 6.2. Đặt ngưỡng quyết định

Xác định trước điều kiện tiếp tục, tạm dừng và rollback. Ví dụ:

| Tín hiệu | Tiếp tục khi | Dừng rollout khi |
|---|---|---|
| Readiness | Replica mới Ready ổn định | Pod liên tục NotReady hoặc restart |
| HTTP error rate | Không tăng đáng kể so với baseline | 5xx vượt ngưỡng đã thống nhất |
| Dependency error | Không có lỗi quyền hoặc kết nối mới | Timeout, 401/403 hoặc throttling tăng bất thường |
| Messaging | Backlog và DLQ trong giới hạn | Message không được ack hoặc DLQ tăng nhanh |
| Latency | p95/p99 gần baseline | Latency vượt SLO hoặc tăng kéo dài |
| Tài nguyên | CPU, memory, connection pool ổn định | Cạn pool, OOM hoặc saturation |

Các ngưỡng cụ thể phải dựa trên SLO và baseline của hệ thống. Không áp dụng một con số chung cho mọi ứng dụng. Cũng cần phân biệt lỗi do dependency dùng chung đang gặp sự cố với lỗi chỉ xuất hiện ở phiên bản mới.

### 6.3. Lệnh quan sát rollout trên Kubernetes

```bash
kubectl rollout status deployment/order-service
kubectl get pods -l app=order-service
kubectl describe deployment order-service
kubectl logs deployment/order-service --since=10m
```

Lệnh `rollout status` chỉ cho biết trạng thái rollout của Deployment. Nó không chứng minh nghiệp vụ tích hợp hoạt động đúng. Hãy kết hợp smoke test và metric của dependency trước khi coi phát hành hoàn tất.

## 7. Quy trình rollback

Rollback là đưa traffic và ứng dụng về trạng thái phiên bản ổn định đã biết. Cần xác định trước ai có quyền dừng rollout, artifact nào là phiên bản trước, cấu hình nào phải khôi phục và những tài nguyên nào phải được giữ lại.

Quy trình tổng quát:

1. **Dừng mở rộng rollout.** Ngừng tăng tỷ lệ canary hoặc tạm dừng pipeline.
2. **Giảm hoặc chuyển traffic.** Đưa traffic về phiên bản ổn định bằng bộ định tuyến, deployment controller hoặc cơ chế blue-green.
3. **Triển khai lại artifact cũ.** Dùng image digest hoặc artifact version đã ghi nhận trước đó.
4. **Khôi phục cấu hình tương thích.** Kiểm tra endpoint, region, secret reference, feature flag và timeout của phiên bản cũ.
5. **Giữ tài nguyên dùng chung.** Không xóa queue, topic, bucket, subscription, schema hoặc secret version khi chưa xác nhận không còn consumer/producer cần chúng.
6. **Kiểm tra lại tích hợp.** Chạy health check, smoke test, xác minh identity và theo dõi metric sau khi traffic quay về.
7. **Ghi nhận nguyên nhân và bằng chứng.** Lưu release ID, correlation ID, thời điểm, log đã lọc secret và metric liên quan.

Với Kubernetes, có thể dùng lệnh:

```bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service
```

Lệnh `rollout undo` khôi phục revision của Deployment theo lịch sử mà Kubernetes lưu. Nó không tự khôi phục ConfigMap, Secret, IAM policy, DNS record, database schema hoặc tài nguyên cloud được thay đổi bên ngoài Deployment. Những thành phần đó cần quy trình khôi phục riêng.

### 7.1. Rollback theo loại thay đổi

| Thành phần thay đổi | Cách xử lý khi rollback | Rủi ro cần tránh |
|---|---|---|
| Image ứng dụng | Triển khai lại digest ổn định trước đó | Dùng lại tag đã bị ghi đè |
| Feature flag | Tắt flag hoặc chuyển về giá trị trước | Flag không được đồng bộ giữa các instance |
| Endpoint/region | Khôi phục cấu hình đã kiểm chứng | Phiên bản cũ không tương thích với endpoint mới |
| IAM/RBAC | Khôi phục quyền tối thiểu cần cho phiên bản cũ | Thu hồi quyền khi instance cũ vẫn đang chạy |
| Secret reference | Chuyển về version còn hiệu lực và được phép dùng | Xóa hoặc vô hiệu hóa version cũ quá sớm |
| Route, DNS, firewall | Khôi phục thay đổi theo kế hoạch mạng | Làm đứt kết nối của workload khác dùng chung mạng |
| Database schema | Giữ schema tương thích; dùng migration tiến về phía trước khi cần | Chạy migration phá hủy dữ liệu để cố quay lại |
| Queue/topic/subscription | Giữ tài nguyên và kiểm tra backlog, consumer | Xóa message hoặc subscription còn dữ liệu chưa xử lý |

## 8. Migration dữ liệu và message cần tương thích ngược

Một trong những nguyên nhân khiến rollback thất bại là phiên bản mới đã thay đổi dữ liệu mà phiên bản cũ không đọc được.

Với database, áp dụng quy trình expand-and-contract:

1. **Expand:** thêm cột, bảng hoặc index mới theo cách không phá vỡ ứng dụng cũ.
2. **Deploy tương thích:** phiên bản mới đọc được cấu trúc cũ và mới; nếu cần, ghi đồng thời theo giai đoạn có kiểm soát.
3. **Migrate:** chuyển dữ liệu theo batch, có thể tiếp tục hoặc chạy lại an toàn.
4. **Verify:** đối chiếu số lượng, tính toàn vẹn và hành vi đọc/ghi.
5. **Contract:** chỉ xóa cột hoặc cấu trúc cũ sau khi phiên bản cũ không còn cần thiết và thời hạn rollback đã kết thúc.

Với message, thêm field mới theo hướng optional hoặc có default phù hợp. Consumer nên bỏ qua field chưa biết nếu contract cho phép; producer không nên bỏ field cũ ngay khi vẫn còn consumer phiên bản cũ. Khi thay đổi serialization, cần kiểm tra tương thích giữa producer và consumer ở các phiên bản đang chạy song song.

Retry có thể khiến một message được xử lý nhiều lần. Handler cần idempotent hoặc có cơ chế deduplication theo message ID/business key. Rollback không tự hoàn tác email, thanh toán, webhook hoặc side effect đã thực hiện. Những nghiệp vụ đó cần thao tác bù (compensating action) có kiểm soát và audit riêng.

## 9. Áp dụng trên AWS, Azure và Google Cloud

Nguyên tắc rollout và rollback giống nhau, nhưng công cụ, identity và tín hiệu quan sát phụ thuộc nền tảng.

| Nền tảng | Cơ chế triển khai thường gặp | Điểm cần xác minh |
|---|---|---|
| AWS | Rolling trên EKS/ECS; blue-green hoặc traffic shifting qua CodeDeploy/Lambda tùy workload | IAM role, VPC endpoint, region, CloudWatch metric, queue backlog và target health |
| Azure | Rolling/canary trên AKS; deployment slot và swap với App Service | Managed identity, Private Endpoint, role assignment, Application Insights và Service Bus metrics |
| Google Cloud | Rolling/canary trên GKE; traffic splitting giữa Cloud Run revisions | Service account/Workload Identity, PSC hoặc Private Google Access, Cloud Monitoring và Pub/Sub metrics |

Trên AWS, nếu dùng SQS hoặc SNS, kiểm tra đúng queue/topic ARN, policy và dead-letter configuration. Với S3, xác minh bucket, prefix, encryption và quyền object. Nếu triển khai Lambda hoặc ECS bằng traffic shifting, giữ lại phiên bản và cấu hình có thể khôi phục trong thời gian quan sát.

Trên Azure, với Service Bus hoặc Storage, xác minh namespace/account, entity hoặc container, managed identity và scope của role assignment. Nếu dùng App Service deployment slots, kiểm tra cả slot-specific settings và connection configuration trước khi swap.

Trên Google Cloud, với Pub/Sub hoặc Cloud Storage, xác minh project, topic/subscription hoặc bucket, service account và IAM binding. Khi dùng Cloud Run revisions, traffic splitting có thể hỗ trợ canary; khi dùng GKE, cần ingress hoặc công cụ progressive delivery phù hợp để điều khiển traffic.

Dù dùng công cụ nào, cần kiểm tra cả cấu hình gắn với phiên bản và cấu hình dùng chung bên ngoài workload. Việc quay lại revision ứng dụng không tự động đảo ngược thay đổi trong IAM, DNS, secret manager hoặc tài nguyên dữ liệu.

## 10. Ví dụ quy trình phát hành thay đổi tích hợp queue

Giả sử phiên bản mới của `order-service` chuyển từ cấu hình queue cũ sang queue mới và dùng workload identity để gửi message.

**Giai đoạn chuẩn bị**

- Tạo queue mới trong môi trường staging và production.
- Cấp quyền gửi cho identity của ứng dụng trên queue mới; giữ quyền cũ trong thời gian chuyển đổi.
- Cấu hình DNS, endpoint và route nếu queue sử dụng kết nối riêng.
- Kiểm tra schema message và bảo đảm consumer hiện tại đọc được format mới.
- Ghi lại image digest, tên queue cũ, tên queue mới và feature flag.

**Giai đoạn triển khai thử**

- Triển khai phiên bản mới vào staging bằng cùng cơ chế identity và network như production.
- Chạy smoke test gửi message có correlation ID vào queue kiểm thử.
- Xác nhận consumer nhận, xử lý và ack message; kiểm tra retry và DLQ.
- Theo dõi latency, lỗi publish/consume và backlog.
- Triển khai một replica canary hoặc một tỷ lệ traffic nhỏ trong production nếu staging đạt.

**Giai đoạn mở rộng**

- Tăng traffic theo từng bước sau mỗi cửa sổ quan sát.
- Xác nhận message mới vào đúng queue và consumer xử lý ổn định.
- Khi toàn bộ producer và consumer đã dùng queue mới, tiếp tục giữ queue cũ trong thời gian rollback đã định.
- Sau khi hết thời hạn rollback và không còn message cần xử lý, thu hồi quyền và xóa tài nguyên cũ theo quy trình thay đổi hạ tầng.

**Nếu phải rollback**

- Tắt feature flag hoặc chuyển traffic về phiên bản cũ.
- Khôi phục cấu hình queue cũ và triển khai lại artifact ổn định.
- Giữ queue mới để kiểm tra backlog và xử lý message đã publish; không xóa queue để che lỗi.
- Đối chiếu message theo correlation ID để tránh xử lý trùng.
- Chỉ thu hồi quyền và dọn tài nguyên sau khi xác nhận không còn workload nào sử dụng.

## 11. Checklist trước và sau triển khai

### Trước triển khai

- [ ] Artifact có version hoặc digest bất biến và đã qua kiểm thử phù hợp.
- [ ] Đã ghi nhận phiên bản ổn định, cấu hình, secret reference và feature flag hiện tại.
- [ ] Endpoint, region, project/subscription và tên tài nguyên đã được xác minh.
- [ ] Workload identity có đúng quyền tối thiểu trên tài nguyên đích.
- [ ] DNS, route, firewall, TLS và private endpoint đã được kiểm tra từ runtime.
- [ ] Schema database và message tương thích với phiên bản cũ đang chạy.
- [ ] Có smoke test an toàn, dữ liệu thử riêng và cách dọn dẹp.
- [ ] Có metric, log, trace và ngưỡng dừng rollout.
- [ ] Có lệnh hoặc thao tác rollback đã được kiểm tra trong môi trường phù hợp.

### Sau triển khai

- [ ] Readiness ổn định và không có restart bất thường.
- [ ] Smoke test xác nhận thao tác thực tế trên dịch vụ managed.
- [ ] Không phát sinh lỗi identity, DNS, TLS hoặc endpoint ngoài dự kiến.
- [ ] Error rate, latency, retry, throttling và backlog nằm trong giới hạn.
- [ ] Message không bị mất hoặc xử lý trùng ngoài dự kiến.
- [ ] Phiên bản, cấu hình và tài nguyên đang dùng được ghi nhận.
- [ ] Hết thời hạn rollback mới dọn tài nguyên, quyền hoặc schema cũ.

## Kết luận

Triển khai thay đổi tích hợp cần kiểm tra từ đúng môi trường runtime, dùng đúng identity và thực hiện thao tác nghiệp vụ nhỏ nhất có thể quan sát. Rolling, canary và blue-green giúp giới hạn rủi ro khi chuyển traffic; health check, metric, log và trace cung cấp bằng chứng để quyết định tiếp tục hay dừng. Một kế hoạch rollback tốt phải khôi phục được artifact và cấu hình, đồng thời giữ dữ liệu, message và tài nguyên dùng chung ở trạng thái tương thích. Trên AWS, Azure và Google Cloud, hãy chuẩn bị và xác minh các bước này trước khi mở rộng rollout đến toàn bộ workload.

