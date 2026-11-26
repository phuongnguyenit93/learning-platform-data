# Thời gian khởi động và chi phí làm nóng ứng dụng

## Mục tiêu bài học

Trong chương **Đóng gói ứng dụng** của **SPRING_CLOUD_KUBERNETES**, thời gian khởi động quyết định Pod mới có thể bổ sung năng lực phục vụ nhanh đến đâu. Chi phí làm nóng quyết định mỗi lần triển khai, tự phục hồi hoặc mở rộng cần thêm bao nhiêu CPU, bộ nhớ và tài nguyên của hệ thống phụ thuộc.

Sau bài học, bạn có thể:

- Phân biệt thời gian tạo Pod, khởi động tiến trình, khởi tạo Spring, trở thành Ready và đạt hiệu năng ổn định.
- Đo các giai đoạn này với cùng image và điều kiện tài nguyên.
- Nhận diện chi phí đọc ConfigMap/Secret, khởi tạo DiscoveryClient và Spring Cloud LoadBalancer.
- Cấu hình startup, readiness và liveness probe đúng mục đích.
- Chọn warm-up, lazy initialization hoặc tối ưu đóng gói dựa trên số liệu và đánh đổi vận hành.

Ví dụ mã sử dụng Java 21, Spring Boot 3.5, Web starter và Actuator. Khi ghép Spring Cloud Kubernetes vào ứng dụng, chọn release train và phiên bản tương thích với Spring Boot đang dùng. Các lệnh shell trong bài dùng cú pháp Bash; tên image, tên Pod và số liệu đều là ví dụ, không phải kết quả benchmark đã đo cho hệ thống của bạn.

## 1. “Ứng dụng đã khởi động” có nhiều nghĩa

Một dòng log `Started CatalogApplication` không mô tả toàn bộ thời gian người dùng phải chờ. Có thể image còn được kéo về node trước khi tiến trình tồn tại, hoặc request đầu tiên vẫn phải tạo serializer, mở kết nối và nạp cache.

### 1.1. Các mốc cần ghi riêng

| Mốc | Ý nghĩa | Nguồn quan sát |
| --- | --- | --- |
| T0 | Pod được tạo | `metadata.creationTimestamp` |
| T1 | Pod được gán node | Condition `PodScheduled`, sự kiện scheduler |
| T2 | Container ứng dụng bắt đầu chạy | `containerStatuses[].state.running.startedAt` |
| T3 | Spring hoàn thành một phần khởi tạo context và phát log `Started` | Log ứng dụng, startup instrumentation |
| T4 | Runner bắt buộc hoàn tất, ứng dụng chấp nhận traffic | Availability của Spring, readiness probe |
| T5 | Kubernetes ghi nhận Pod Ready | Condition `Ready` |
| T6 | Đường đi nghiệp vụ đạt mục tiêu độ trễ và throughput | Load test và metric theo từng Pod |

T2 gần với thời điểm tiến trình container bắt đầu, nhưng không phải đồng hồ bên trong JVM. T4 và T5 cũng không trùng tuyệt đối: kubelet còn phải chạy probe và cập nhật trạng thái.

Một timeline minh họa:

```text
Pod tạo ── chờ node/kéo image ── container chạy ── context ── runner ── Ready ── hiệu năng ổn định
  T0                               T2             T3         T4       T5           T6
```

Những giai đoạn bên trong có thể chạy song song. Không cộng tổng thời gian tất cả startup step nếu chúng lồng nhau hoặc chồng lấp.

### 1.2. Chọn thước đo theo câu hỏi vận hành

```text
Thời gian cung cấp Pod = T5 - T0
Thời gian tiến trình tới Ready ≈ T5 - T2
Khoảng làm nóng sau Ready = T6 - T5
```

Ví dụ giả định:

- Tạo Pod đến container chạy: 12 giây.
- Container chạy đến Ready: 20 giây.
- Sau Ready cần thêm 15 giây mới đạt latency mục tiêu.

Kết quả là 32 giây tới Ready và khoảng 47 giây tới trạng thái hiệu năng mong muốn. Chỉ báo cáo “Spring chạy trong 18 giây” có thể bỏ qua phần chờ ảnh hưởng trực tiếp đến scale-out.

Nếu đưa warm-up bắt buộc vào trước readiness, một phần chi phí sẽ chuyển từ `T6 - T5` sang `T5 - T2`. Phải đo cả hai thay vì chỉ cố làm một cột nhỏ đi.

## 2. Ứng dụng Spring tốn thời gian ở đâu?

| Giai đoạn | Công việc thường gặp | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Chuẩn bị Pod | Scheduling, kéo image, init container, mount volume | Chưa có log ứng dụng |
| Nạp cấu hình | Đọc tệp, ConfigMap/Secret qua API, kiểm tra thuộc tính | Timeout hoặc retry trước khi web server chạy |
| JVM | Nạp class, kiểm tra bytecode, cấp phát, JIT | CPU cao, class loading hoặc GC nổi bật |
| Spring context | Quét component, auto-configuration, tạo proxy và bean | Một nhóm startup step chiếm thời gian lớn |
| Hạ tầng ứng dụng | DB pool, migration, HTTP client, DNS/TLS | Chờ I/O hoặc khóa dùng chung |
| Khám phá dịch vụ | Tạo client Kubernetes, đồng bộ dữ liệu dịch vụ | API latency, lỗi RBAC, phạm vi namespace rộng |
| Request đầu | Khởi tạo lazy bean, serializer, cache, kết nối | Ready nhanh nhưng request đầu chậm |
| Vận hành ổn định | JIT tiếp tục tối ưu, cache dần có dữ liệu | Throughput tăng dần sau một thời gian có tải |

Không phải ứng dụng nào cũng thực hiện đầy đủ các bước trên. Một dịch vụ chỉ gọi Service bằng DNS có thể không cần DiscoveryClient; một ứng dụng chỉ đọc cấu hình từ volume có thể không cần gọi Kubernetes API khi khởi động.

Đóng gói ít dependency hơn có thể giảm công việc khởi tạo, nhưng chỉ loại bỏ thư viện khi xác định nó không cần cho hành vi ứng dụng. Loại một dependency để số giây đẹp hơn rồi làm mất chức năng không phải tối ưu.

## 3. Chi phí riêng của Spring Cloud Kubernetes

### 3.1. ConfigMap và Secret: đường đọc quyết định nơi phải chờ

Hai cách cấp cùng một giá trị có chi phí khác nhau:

```text
Volume:
Kubernetes chuẩn bị dữ liệu → mount tệp → Spring đọc tệp

API:
Spring khởi tạo client → xác thực/RBAC → gọi API → chuyển dữ liệu thành PropertySource
```

Dùng volume chuyển một phần công việc sang giai đoạn chuẩn bị Pod; không làm chi phí đó biến mất. Dùng API thêm phụ thuộc mạng và quyền truy cập vào đường khởi động của ứng dụng.

Khi dùng ConfigMap PropertySource qua API, kiểm tra tên nguồn, namespace, timeout và retry. Spring Cloud Kubernetes có cấu hình fail-fast và retry; yêu cầu dependency cũng như hành vi cụ thể phụ thuộc phiên bản. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Không tăng số lần retry để che lỗi `403 Forbidden`, sai tên Secret hoặc giá trị không hợp lệ. Hãy sửa nguyên nhân. Retry hữu ích với lỗi tạm thời, nhưng phải có thời hạn tổng.

Ví dụ tính ngân sách retry tự thiết kế, không phải giá trị mặc định của thư viện:

```text
4 lần thử × tối đa 2 giây mỗi lần + các lần chờ 1, 2, 4 giây
= tối đa khoảng 15 giây cho một chuỗi gọi
```

Nếu có nhiều nguồn được đọc tuần tự, thời gian cộng dồn có thể lớn hơn. Khi có lời gọi song song, đánh giá đường thực thi chậm nhất và mức tải đồng thời. Không suy ra ngân sách từ một timeout riêng lẻ.

### 3.2. DiscoveryClient: giới hạn phạm vi cần thiết

Khởi tạo discovery có thể liên quan đến đọc hoặc theo dõi danh mục dịch vụ. Phạm vi nhiều namespace và nhiều tài nguyên có thể làm tăng dữ liệu phải xử lý, bộ nhớ cache và tải API.

Chỉ khám phá những namespace và dịch vụ cần dùng. Tài liệu [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html) mô tả lựa chọn namespace và bộ lọc. Không dùng tùy chọn khám phá toàn cluster chỉ để tránh khai báo phạm vi.

Phân biệt:

- Web server của ứng dụng đã mở cổng.
- DiscoveryClient đã có dữ liệu phục vụ lựa chọn instance.
- Một lời gọi nghiệp vụ thật đã tìm được instance và kết nối thành công.

Ba điều này cần quan sát riêng. Cũng không đưa lỗi tạm thời của Kubernetes API vào liveness khiến mọi Pod bị restart đồng loạt.

### 3.3. Spring Cloud LoadBalancer: khởi tạo sớm hay trả giá ở request đầu?

Spring Cloud LoadBalancer tạo context theo service ID và mặc định có thể khởi tạo chúng khi lần đầu cần cân bằng tải. Có thể chọn eager loading cho những service ID quan trọng. Xem [eager loading của Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/loadbalancer.html#eager-loading-of-loadbalancer-contexts).

Ví dụ ứng dụng đã có tích hợp LoadBalancer:

```yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - inventory-service
          - pricing-service
```

Đổi lại, khởi động có thể làm thêm công việc và dùng thêm bộ nhớ. Tạo context sớm cũng không đảm bảo DNS, TLS, pool kết nối, cache discovery hoặc đường nghiệp vụ đã nóng. Đo lần gọi thực tế đến từng service quan trọng.

Không khai báo mọi service ID trong tổ chức vào danh sách eager loading. Một dịch vụ ít được gọi có thể phù hợp với khởi tạo theo nhu cầu hơn.

## 4. Đo trước khi đổi cấu hình

### 4.1. Ghi rõ điều kiện thí nghiệm

Mỗi kết quả cần đi kèm:

- Image digest, phiên bản JDK, Spring Boot, Spring Cloud và cấu hình.
- CPU request/limit, memory limit, loại node và mức tranh chấp tài nguyên.
- Image đã có trên node hay chưa.
- Trạng thái dependency, pool, cache và dữ liệu thử.
- Số Pod khởi động đồng thời, số lần lặp, số lần thất bại hoặc restart.
- Endpoint và hình dạng tải dùng để xác định hiệu năng ổn định.

Một container mới vẫn là JVM mới dù image và filesystem cache của node đang nóng. “Cold start” cần được định nghĩa: lạnh image, lạnh JVM, lạnh cache ứng dụng hay lạnh cả hệ thống phụ thuộc?

Để so sánh hai lựa chọn cho Spring, giữ điều kiện image cache giống nhau. Sau đó đo riêng tình huống node chưa có image nếu đây là rủi ro vận hành thực tế.

### 4.2. Thu thập timeline Kubernetes

Sau khi có Pod lab, chọn đúng tên:

```bash
kubectl -n startup-lab get pods -l app=catalog-service

POD=catalog-service-REPLACE_WITH_POD_NAME

kubectl -n startup-lab get pod "$POD" \
  -o jsonpath='{.metadata.creationTimestamp}{"\n"}{.status.containerStatuses[?(@.name=="app")].state.running.startedAt}{"\n"}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{.status.conditions[?(@.type=="Ready")].lastTransitionTime}{"\n"}'

kubectl -n startup-lab logs "$POD" -c app --timestamps

kubectl -n startup-lab get events \
  --field-selector involvedObject.name="$POD" \
  --sort-by=.metadata.creationTimestamp
```

`lastTransitionTime` chỉ mô tả lần chuyển trạng thái gần nhất, không lưu cả lịch sử readiness flapping. Events có thể được gộp hoặc hết thời gian lưu. Khi cần phân tích dài hạn, thu thập chuỗi thời gian và sự kiện bằng hệ thống quan sát của nền tảng.

Đối chiếu đồng hồ giữa nguồn log và control plane. Không dùng chênh lệch timestamp từ các máy lệch giờ để kết luận một bước chỉ kéo dài vài mili giây.

### 4.3. Quan sát startup step trong Spring

Thay cách gọi `SpringApplication.run` bằng cấu hình thu thập có giới hạn:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CatalogApplication.class);
        application.setApplicationStartup(
                new BufferingApplicationStartup(4096));
        application.run(args);
    }
}
```

Trong profile đo đạc nội bộ, expose `startup` cùng `health`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,startup
```

Sau khởi động, dùng port-forward tới đúng Pod:

```bash
kubectl -n startup-lab port-forward pod/"$POD" 8080:8080
```

Trong terminal khác:

```bash
curl -fsS http://localhost:8080/actuator/startup
```

Endpoint cần `BufferingApplicationStartup`; tài liệu [Actuator endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html) mô tả điều kiện sử dụng. Chỉ cho phép truy cập chẩn đoán trong phạm vi được quản lý; cấu hình thông thường của bài chỉ expose `health`.

Buffer có giới hạn và instrumentation cũng có chi phí. Dữ liệu này không bao gồm thời gian chờ scheduler, kéo image hoặc toàn bộ CPU của JVM. Dùng nó để tìm nhóm công việc, không xem là bản đo toàn bộ vòng đời Pod.

Nếu cần liên hệ startup với nạp class, GC hoặc cấp phát, có thể dùng Java Flight Recorder và `FlightRecorderApplicationStartup` thay cho buffer. Đo thêm overhead của công cụ và tránh lưu recording chứa dữ liệu nhạy cảm vào nơi công khai.

### 4.4. Đo request đầu và trạng thái ổn định

Sau khi Pod mới Ready, gửi request đầu đến đúng Pod chưa được thử đường nghiệp vụ:

```bash
curl -fsS -o /dev/null \
  -w 'ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  http://localhost:8080/api/catalog/SKU-001
```

Sau đó dùng tải đại diện để đo p50, p95, throughput và tỷ lệ lỗi. Một vòng `curl` tạo kết nối mới liên tục có thể đo thêm chi phí kết nối; nó không thay thế benchmark có chính sách kết nối giống client thật.

Đo qua Pod giúp cô lập phiên bản vừa khởi động, còn đo qua Service/Ingress phản ánh đường đi người dùng. Không so sánh trực tiếp hai đường đi rồi quy chênh lệch hoàn toàn cho Spring.

## 5. Warm-up cần có phạm vi, điểm kết thúc và ngân sách

### 5.1. Chọn công việc làm nóng có ích

| Công việc | Có thể làm trước readiness? | Cần kiểm soát |
| --- | --- | --- |
| Chuẩn bị serializer cho DTO quan trọng | Có, với dữ liệu tổng hợp | Dùng cùng mapper/kiểu dữ liệu như endpoint |
| Nạp tập quy tắc cục bộ cần thiết | Có | Kích thước, thời hạn và lỗi dữ liệu |
| Mở một số kết nối cần thiết | Có, nếu phụ thuộc bắt buộc | Timeout, tổng số kết nối toàn rollout |
| Nạp toàn bộ bảng dữ liệu vào cache | Chỉ khi thật sự cần | Bộ nhớ, tải DB, thay đổi dữ liệu |
| Gọi API tạo đơn hoặc trừ tiền | Không dùng làm warm-up | Tác dụng phụ nghiệp vụ |
| Chạy vòng lặp tùy ý để “ép JIT” | Không có đảm bảo lợi ích | CPU, profile không đại diện và nhiễu đo |

Warm-up không cần mô phỏng toàn bộ production traffic. Nó nên xử lý phần lạnh đã được chứng minh gây ảnh hưởng và có kết quả kiểm tra được.

### 5.2. Ví dụ warm-up cục bộ trước khi ứng dụng nhận traffic

Ví dụ dưới đây dùng DTO giá sản phẩm và một controller chỉ trả dữ liệu giả cho lab. Mỗi lớp nằm trong tệp Java tương ứng dưới package `com.example.catalog`.

```java
package com.example.catalog;

import java.math.BigDecimal;

public record CatalogPreview(
        String sku,
        BigDecimal price,
        String currency) {
}
```

```java
package com.example.catalog;

import java.math.BigDecimal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    @GetMapping("/api/catalog/{sku}")
    public CatalogPreview preview(@PathVariable("sku") String sku) {
        return new CatalogPreview(sku, new BigDecimal("12.50"), "USD");
    }
}
```

Một runner dùng chính controller và mapper của ứng dụng:

```java
package com.example.catalog;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WarmupConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(WarmupConfiguration.class);

    @Bean
    @ConditionalOnProperty(
            name = "app.warmup.enabled",
            havingValue = "true",
            matchIfMissing = true)
    ApplicationRunner catalogWarmup(
            CatalogController controller,
            ObjectMapper objectMapper) {

        return arguments -> {
            long startedAt = System.nanoTime();

            for (String sku : List.of("WARMUP-001", "WARMUP-002")) {
                CatalogPreview sample = controller.preview(sku);
                byte[] encoded = objectMapper.writeValueAsBytes(sample);
                CatalogPreview decoded =
                        objectMapper.readValue(encoded, CatalogPreview.class);

                if (!sample.equals(decoded)) {
                    throw new IllegalStateException(
                            "Local warmup verification failed");
                }
            }

            long elapsedMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

            log.info("local_warmup_completed duration_ms={}", elapsedMs);
        };
    }
}
```

Đoạn mã dành cho Spring Boot 3.5 với Jackson 2. Không chép nguyên import Jackson sang một thế hệ framework khác mà chưa kiểm tra thư viện đang dùng.

Runner chỉ xử lý hai mẫu tổng hợp, không gọi dịch vụ ngoài, không in payload và không có vòng retry. Nếu một warm-up bắt buộc ném exception, khởi động không hoàn thành.

Theo vòng đời Spring Boot, `ApplicationReadyEvent` và trạng thái chấp nhận traffic đến sau các runner. Xem [thứ tự sự kiện của SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html#features.spring-application.application-events-and-listeners).

Điều runner này **không chứng minh** là DNS/TLS, servlet filter, security filter, connection pool hoặc toàn bộ endpoint đã được làm nóng. Gọi trực tiếp phương thức controller bỏ qua pipeline HTTP. Khi áp dụng cho nghiệp vụ thật, chuyển công việc thuần cần dùng chung vào service và warm đúng đường đi đó.

Đây là cơ chế đặt công việc trước readiness, không phải cam kết hai lần serialize sẽ tạo cải thiện đáng kể. Chỉ giữ warm-up khi phép đo cho thấy lợi ích.

### 5.3. Khi warm-up cần I/O

Với truy cập DB hoặc HTTP, đặt timeout ở client, giới hạn số phần tử và deadline tổng. Tác vụ “đợi đến khi thành công” không có giới hạn có thể giữ Pod ở trạng thái chưa Ready mãi.

Phân biệt dữ liệu bắt buộc với cache tùy chọn:

- Bắt buộc: không hoàn thành thì ứng dụng chưa thể phục vụ đúng; giữ readiness chưa đạt và có chính sách thất bại rõ ràng.
- Tùy chọn: có thể nạp nền sau khi Ready nếu đường xử lý lạnh vẫn đúng và đáp ứng yêu cầu tối thiểu.

Nếu chạy bất đồng bộ, việc runner trả về không có nghĩa warm-up đã xong. Cần health indicator/readiness gate phù hợp nếu tác vụ nền vẫn là điều kiện bắt buộc. Không tự công bố Ready sớm để số startup nhỏ đi.

## 6. Probe bảo vệ vòng đời, không tối ưu công việc khởi tạo

### 6.1. Cấu hình ứng dụng

Cấu hình thông thường của lab chỉ mở health endpoint:

```yaml
spring:
  application:
    name: catalog-service

app:
  warmup:
    enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Dùng cùng cổng 8080 với HTTP nghiệp vụ. Nếu dùng Spring Security, cấp quyền cho kubelet truy cập đúng các đường health probe. Không mở toàn bộ management API ra ngoài để giải quyết lỗi probe.

### 6.2. Deployment tối thiểu để đo

Ứng dụng lab không cần Kubernetes API: không có starter đọc cấu hình qua API hoặc DiscoveryClient trong ví dụ tối thiểu. Khi đưa manifest vào ứng dụng có tích hợp API, cấu hình ServiceAccount/RBAC tương ứng thay vì giữ nguyên lựa chọn không mount token.

Lưu manifest minh họa thành `startup-lab.yml` và thay image placeholder bằng digest có thật trước khi áp dụng:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: startup-lab
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: startup-lab
spec:
  replicas: 1
  minReadySeconds: 10
  progressDeadlineSeconds: 300
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
    spec:
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.com/catalog-service@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 768Mi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
            successThreshold: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 1
            failureThreshold: 3
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
  namespace: startup-lab
spec:
  selector:
    app: catalog-service
  ports:
    - port: 8080
      targetPort: http
```

Các mức tài nguyên chỉ phục vụ thí nghiệm, chưa phải sizing production. Image trong registry riêng còn cần cơ chế xác thực kéo image của môi trường.

```bash
kubectl apply -f startup-lab.yml
kubectl -n startup-lab rollout status deployment/catalog-service --timeout=300s
```

Cách đọc các probe:

- Startup probe cho phép khoảng `60 × 2 = 120` giây để endpoint liveness khởi động thành công, với sai số do lịch thực thi và timeout.
- Readiness kiểm soát khả năng nhận traffic thông thường qua Service; hai lần thành công liên tiếp làm thời điểm Ready trễ hơn lần đầu endpoint trả thành công.
- Liveness phát hiện tình trạng ứng dụng không còn sống khỏe sau giai đoạn startup.

Khi startup probe chưa thành công, Kubernetes chưa chạy liveness/readiness probe của container đó. Xem [hướng dẫn cấu hình probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Liveness của Spring có thể đạt trước khi runner kết thúc. Vì thế startup probe dùng đường liveness không phải đồng hồ bao trọn warm-up. Readiness vẫn chịu trách nhiệm chờ phần bắt buộc. Một runner treo sau khi liveness đã đạt cần deadline của chính nó và cơ chế phát hiện rollout không tiến triển.

`minReadySeconds: 10` yêu cầu Pod giữ Ready trước khi Deployment coi nó là available. Nó không chặn traffic trong 10 giây sau Ready và không làm nóng ứng dụng. `progressDeadlineSeconds` báo rollout không tiến triển, không tự rollback. Xem [các thuộc tính Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#min-ready-seconds).

Không thêm DB hoặc API đối tác vào liveness một cách máy móc. Khi một dependency chung lỗi, restart hàng loạt sẽ tạo thêm cold start và có thể gây tải khôi phục lớn hơn.

## 7. CPU, bộ nhớ và chi phí warm-up

### 7.1. CPU limit thấp có thể kéo dài startup

Khởi động thường có đợt CPU cao cho nạp class, tạo bean và JIT. CPU limit áp đặt trần sử dụng; request tham gia scheduling và phân chia tài nguyên khi tranh chấp. Request không phải trần và cũng không đảm bảo startup luôn có lượng CPU mong muốn trong mọi tình huống. Xem [quản lý tài nguyên container](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Có thể thử thay limit từ `250m` lên `1` trong cùng điều kiện node. Nếu thời gian giảm và số liệu throttling giảm tương ứng, đây là bằng chứng đáng xem xét. Nếu đang chờ API 15 giây, tăng CPU có thể hầu như không cải thiện.

Tăng request quá cao cũng có thể khiến Pod chờ node lâu hơn. Phải kiểm tra cả `T5 - T0`, không chỉ giai đoạn JVM chạy.

### 7.2. Đo tổng công việc, không chỉ thời gian trên đồng hồ

```text
CPU dùng cho khởi động = tích phân mức sử dụng CPU theo thời gian
Đơn vị: CPU-second

Bộ nhớ sử dụng tích lũy = tích phân bộ nhớ theo thời gian
Đơn vị: GiB-second hoặc GiB-hour
```

Ví dụ lý tưởng hóa:

```text
0,5 CPU trung bình × 40 giây = 20 CPU-second
1,0 CPU trung bình × 20 giây = 20 CPU-second
```

Cách thứ hai nhanh hơn nhưng chưa chứng minh tốn gấp đôi CPU. Ngược lại, warm-up nạp thêm dữ liệu hoặc tạo thêm đối tượng có thể tăng tổng công việc dù readiness đạt nhanh.

Đây là thước đo kỹ thuật, không tự quy đổi thành hóa đơn. Chi phí thực tế còn phụ thuộc request đã đặt, dung lượng node, khả năng chia sẻ, giá dịch vụ và cách tính phí của nền tảng.

Đừng dùng một lần `kubectl top` để kết luận peak CPU hoặc peak memory. Cần chuỗi mẫu đủ dày hoặc bộ đếm CPU tích lũy, đồng thời tách riêng container ứng dụng khỏi sidecar.

### 7.3. Không cấp toàn bộ memory limit cho heap

Ngoài heap, tiến trình còn dùng metaspace, code cache, thread stack, direct buffer và bộ nhớ native. Warm-up có thể đẩy peak RSS cao hơn trạng thái chạy ổn định.

Nếu limit là `768Mi`, đặt `-Xmx768m` thường để lại quá ít chỗ cho các thành phần khác. Sizing cần dựa trên phép đo của đúng JDK và ứng dụng, đồng thời theo dõi GC, OOMKilled và restart.

Không giảm heap chỉ vì endpoint health hoạt động ở thời điểm đầu. Hãy chạy cả workload sau warm-up và đường request hiếm nhưng tốn bộ nhớ.

## 8. Lazy initialization: chuyển thời điểm trả chi phí

Có thể thử:

```yaml
spring:
  main:
    lazy-initialization: true
```

Spring Boot sẽ trì hoãn nhiều bean đến lúc cần dùng. Điều này có thể giảm startup, nhưng cũng đẩy độ trễ và lỗi khởi tạo sang request đầu. Xem [Lazy Initialization](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.lazy-initialization).

Đánh giá đủ ba yếu tố:

1. Thời gian tới Ready có giảm không?
2. Request đầu và request đầu của từng đường nghiệp vụ còn trong ngân sách không?
3. Lỗi cấu hình quan trọng có bị phát hiện quá muộn không?

Một lần gọi health không tạo mọi controller, repository hoặc client lazy. Ứng dụng vẫn phải có đủ bộ nhớ khi các bean cuối cùng được tạo.

Có thể giữ các bean thiết yếu khởi tạo sớm và trì hoãn phần ít dùng. Không kết luận từ một endpoint đại diện duy nhất rằng toàn bộ ứng dụng đã được làm nóng.

## 9. Tối ưu đóng gói: chọn đúng lớp vấn đề

### 9.1. Image và dependency

Nếu `T2 - T0` lớn vì kéo image, kiểm tra kích thước image, registry gần node, cache layer và điều kiện mạng. Layering hợp lý giúp tái sử dụng phần thư viện không đổi giữa các bản phát hành.

Nếu `T5 - T2` lớn do context, giảm image vài megabyte chưa chắc giải quyết được. Hãy tìm auto-configuration, bean hoặc I/O đang nằm trên đường khởi động.

Giữ cùng image digest giữa các lần thử cấu hình runtime. Nếu đổi cả image, CPU limit và warm-up cùng lúc, không thể xác định lựa chọn nào tạo ra khác biệt.

### 9.2. CDS trên JVM

Với Java 21 và Spring Boot 3.5, có thể thử Class Data Sharing để giảm một phần chi phí nạp class. Quy trình minh họa dùng executable JAR đã đóng gói:

```bash
java -Djarmode=tools -jar target/catalog-service.jar \
  extract --destination extracted

cd extracted

java -XX:ArchiveClassesAtExit=application.jsa \
  -Dspring.context.exit=onRefresh \
  -jar catalog-service.jar

java -XX:SharedArchiveFile=application.jsa \
  -jar catalog-service.jar
```

Training và chạy dùng dạng đã extract, không quay lại JAR đóng gói ban đầu. Archive phải phù hợp ứng dụng, classpath và JVM; tạo lại khi đầu vào liên quan thay đổi. Tham khảo [CDS của Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/packaging/class-data-sharing.html).

`spring.context.exit=onRefresh` kết thúc trước runner làm nóng của ví dụ. Vì vậy, training CDS không thay thế warm-up nghiệp vụ. Kiểm soát cả những bean có thể kết nối DB/API trong lúc refresh context: training build không nên cần Secret production hay quyền truy cập Kubernetes của runtime.

CDS không rút ngắn mọi timeout mạng. Tối ưu này cần một thí nghiệm riêng thay vì được xem là cách chữa chung cho startup chậm.

### 9.3. AOT và native image

Phân biệt ba hướng:

| Hướng | Cơ chế chính | Điều cần đánh giá |
| --- | --- | --- |
| CDS hoặc JVM AOT cache | Tái sử dụng phần chuẩn bị của JVM theo khả năng JDK | Tính tương thích archive/cache và hiệu quả đo được |
| Spring AOT | Chuẩn bị một phần mô hình ứng dụng ở build time | Những lựa chọn cấu hình được cố định và thư viện hỗ trợ |
| GraalVM native image | Tạo executable theo nền tảng | Build, reflection/resources/proxy, startup và throughput |

Native image có thể cải thiện startup và footprint, nhưng có yêu cầu tương thích khác JVM. Xem [GraalVM native images trong Spring Boot](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html).

Với hệ thống dùng DiscoveryClient, HTTP client, LoadBalancer và refresh cấu hình, kiểm tra đường đi thực tế trên lựa chọn đóng gói đó. Không suy ra rằng chạy được health endpoint nghĩa là mọi tích hợp đã tương thích.

JDK mới hơn có khả năng JVM AOT cache khác Java 21. Chọn hướng dẫn theo đúng JDK/Boot, không đưa cờ AOT cache của phiên bản khác vào image Java 21. Xem [AOT cache theo phiên bản Spring Boot](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html).

## 10. Warm-up ảnh hưởng rollout và scale-out

### 10.1. Số Pod đồng thời nhân chi phí dependency

Giả sử mỗi Pod làm nóng bằng 20 truy vấn:

```text
5 Pod cùng khởi động  → 100 truy vấn warm-up
20 Pod cùng khởi động → 400 truy vấn warm-up
```

Tương tự, mỗi Pod mở sẵn 10 kết nối thì 20 Pod mới có thể yêu cầu 200 kết nối, chưa kể Pod cũ và các ứng dụng khác.

Với rolling update, đánh giá `maxSurge`, số replica và năng lực còn trống của node/DB/API. Thêm jitter và giới hạn concurrency khi có các lời gọi warm-up ngoài tiến trình; không để mọi Pod retry cùng nhịp.

### 10.2. Scale-out chỉ có ích sau khi năng lực thật sự sẵn sàng

Thời gian phản ứng gồm phát hiện tải, quyết định mở rộng, có chỗ chạy, khởi động và làm nóng. Nếu Pod Ready nhưng còn chậm, metric số replica có thể làm nhóm đánh giá quá cao năng lực mới.

Hãy cân nhắc năng lực dự phòng và số replica tối thiểu dựa trên biến động tải. Tối ưu startup không thay thế kế hoạch đáp ứng các đợt tăng tải nhanh hơn thời gian cung cấp Pod.

Trong lab không tải, startup có thể nhanh. Cần đo thêm khi node đang bận và nhiều Pod cùng lên; đây thường là điều kiện cần xử lý khi phục hồi sự cố.

### 10.3. Configuration Watcher có loại bỏ nhu cầu khởi động lại?

Watcher có thể hỗ trợ refresh cấu hình thay cho một số lần rollout. Tuy nhiên, refresh có thể tạo lại bean, thay client hoặc làm lạnh cache, tùy loại cấu hình và cách ứng dụng dùng nó. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Đo riêng thời gian refresh và ảnh hưởng tới traffic. Cấu hình không refresh an toàn vẫn cần rollout; controller còn cần quyền theo dõi tài nguyên thích hợp. Không bật Watcher chỉ để tránh nhìn thấy chi phí startup trong dashboard.

## 11. Đọc kết quả và tránh tối ưu sai mục tiêu

Bảng sau là **số liệu giả định để luyện phân tích**, không phải benchmark của đoạn mã trong bài. Giả sử mỗi lựa chọn có 30 lần khởi động cùng điều kiện node và image cache; p95 request đầu được tính từ request đầu của từng Pod.

| Lựa chọn | p95 container tới Ready | p95 request đầu | CPU-second trung bình tới Ready |
| --- | --- | --- | --- |
| A: CPU limit thấp, chưa warm-up | 48 giây | 680 ms | 8,9 |
| B: tăng CPU limit, giữ phần còn lại | 23 giây | 520 ms | 8,7 |
| C: như B, thêm warm-up có mục tiêu | 25 giây | 140 ms | 9,2 |
| D: như C, thêm lazy initialization rộng | 18 giây | 390 ms | 8,8 |

Nếu mục tiêu là Ready dưới 30 giây và request đầu dưới 200 ms, C là lựa chọn thỏa cả hai trong ví dụ. D có readiness nhanh hơn nhưng vượt ngân sách độ trễ request đầu.

Trước khi chọn C cho production, vẫn cần biết:

- Startup thất bại bao nhiêu lần và có bị loại khỏi bảng không?
- CPU/memory peak và latency ổn định có nằm trong ngân sách không?
- Kết quả còn đúng với node lạnh image và nhiều Pod đồng thời không?
- Warm-up có gây thêm tải lên DB/Kubernetes API hay không?
- Cải thiện có lặp lại qua đủ mẫu và điều kiện tải đại diện không?

30 mẫu là điểm bắt đầu cho lab, không đảm bảo ước lượng đuôi phân phối đủ chắc chắn. Không báo p99 có vẻ chính xác từ một tập rất ít lần đo.

## 12. Chẩn đoán nhanh và bài thực hành

### 12.1. Từ triệu chứng đến phép kiểm tra

| Triệu chứng | Kiểm tra trước | Điều chỉnh có căn cứ |
| --- | --- | --- |
| Pod chưa có log | Scheduling, image pull, mount, init container | Xử lý tầng Pod trước khi chỉnh Spring |
| CPU cao, startup kéo dài | Throttling, class loading, startup step | Thử tài nguyên phù hợp, giảm khởi tạo thừa |
| CPU thấp nhưng chờ lâu | Timeout API/DB, DNS, retry, migration lock | Giới hạn chờ và sửa phụ thuộc lỗi |
| Ready nhanh, request đầu chậm | Lazy bean, mapper, LoadBalancer, DNS/TLS | Eager/warm-up đúng phần được đo |
| Pod restart trong startup | Probe events, exit code, OOMKilled | Phân biệt probe quá gắt với thiếu bộ nhớ |
| Runner treo nhưng liveness xanh | Deadline warm-up, readiness, rollout progress | Giới hạn công việc bắt buộc và báo lỗi rõ |
| Nhiều Pod lên làm DB/API quá tải | Số kết nối/truy vấn, concurrency, retry | Giảm fan-out, thêm giới hạn và điều tiết rollout |
| Đổi ConfigMap gây latency tăng | Bean/client/cache bị tạo lại khi refresh | Đo refresh và lựa chọn rollout nếu cần |

### 12.2. Thực hành có kiểm soát

1. Chạy ứng dụng lab với cùng image digest, ghi các mốc T0, T2 và T5.
2. Đo request đầu tới `/api/catalog/SKU-001` và lưu điều kiện kết nối.
3. Dùng `app.warmup.enabled=false` rồi `true` trong hai lượt độc lập, so sánh cả Ready lẫn request đầu.
4. Thu startup step trong profile nội bộ; tìm công việc lớn thay vì cộng mọi duration.
5. Chỉ đổi CPU limit trong một lượt khác, giữ nguyên memory và code; kiểm tra cả thời gian chờ node.
6. Nếu ứng dụng thật dùng LoadBalancer, thử eager loading riêng cho một service ID quan trọng và đo lần gọi đầu.
7. Thử một cấu hình API sai quyền trong môi trường được phép; xác định lỗi RBAC, không kéo dài probe để che lỗi.
8. Thử số Pod khởi động đồng thời phù hợp giới hạn lab, quan sát tổng CPU, kết nối và số lần gọi dependency.
9. Ghi lựa chọn cuối cùng cùng lý do, các số liệu thất bại và kế hoạch quay lại cấu hình trước.

Bài làm đạt yêu cầu khi bạn giải thích được mỗi khoảng chờ thuộc tầng nào, biết warm-up đã chuyển chi phí đi đâu, và lựa chọn cấu hình đáp ứng cả readiness, request đầu lẫn ngân sách tài nguyên.
