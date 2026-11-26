# Kiểm tra kết nối và trạng thái sẵn sàng của ứng dụng

## 1. Vấn đề: ứng dụng đã khởi động nhưng chưa thể phục vụ người dùng

Một dịch vụ Spring Boot in dòng `Started OrdersApplication`, cổng HTTP 8080 đã mở, nhưng `GET /orders/order::1001` trả lỗi vì không truy cập được Couchbase. Một lần khác, Couchbase Key–Value (KV) hoạt động, nhưng truy vấn SQL++ `findByCustomerId(...)` bị timeout vì Query Service hoặc chỉ mục chưa sẵn sàng.

Hai hiện tượng trên đặt ra câu hỏi cốt lõi của chương **Quan sát và vận hành**:

> Làm thế nào kiểm tra ứng dụng còn sống, đủ điều kiện nhận traffic và có thể sử dụng các chức năng Couchbase mà nghiệp vụ thật sự cần — mà không biến endpoint kiểm tra sức khỏe thành nguồn gây quá tải hoặc restart vô ích?

Bài học nằm trong module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, Repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, index, TTL, CAS, transaction và lựa chọn API reactive để cân bằng hiệu năng, nhất quán, khả năng vận hành.

**Sau bài học, bạn cần:**

1. Phân biệt **connectivity**, **liveness**, **readiness**, **startup** và **deep functional checks**.
2. Biết ý nghĩa của Spring Boot Actuator `/actuator/health`, `/actuator/health/liveness` và `/actuator/health/readiness`.
3. Cấu hình health group có hoặc không bao gồm Couchbase tùy hợp đồng nghiệp vụ và topology.
4. Xác minh đúng bucket/scope/collection, quyền KV, Query Service, secondary index và đường mạng/TLS khi cần.
5. Hiểu mức độ bảo đảm của một KV `exists`, SDK ping, `SELECT RAW 1` và truy vấn nghiệp vụ thực.
6. Tạo Kubernetes startup/liveness/readiness probes không dùng database outage để quyết định restart tiến trình.
7. Viết một `HealthIndicator` kiểm tra KV tối thiểu và kiểm thử endpoint health trong môi trường cô lập.
8. Xây runbook điều tra lỗi kết nối, alert phù hợp, timeout và degradation an toàn.
9. Phân biệt connectivity với CAS, durability, TTL, scan consistency, giao dịch và độ mới index.

**Nguyên tắc:** Health endpoint phải trả lời **một câu hỏi đã định nghĩa rõ**; một kết quả `UP` không phải chứng nhận rằng toàn bộ nghiệp vụ luôn thành công.

## 2. Mô hình ba mặt phẳng: ứng dụng, Couchbase và tuyến nhận traffic

~~~mermaid
flowchart TD
    LB["Kubernetes Service / Load Balancer"] --> WEB["Spring Boot HTTP API"]
    WEB --> CACHE["Tùy chọn: cache / circuit breaker"]
    WEB --> REPO["Spring Data Repository / CouchbaseTemplate"]
    REPO --> SDK["Couchbase Java SDK"]
    SDK --> KV[("Data Service / KV")]
    SDK --> QUERY[("Query Service / SQL++")]
    QUERY --> INDEX[("Index Service / GSI")]
    SDK --> OTHER["Các dịch vụ khác nếu sử dụng"]
    K8S["Kubernetes probes"] --> LIVE["Liveness / Startup"]
    K8S --> READY["Readiness"]
    READY -. "Có thể kiểm tra phụ thuộc" .-> SDK
~~~

Một API có thể nhận request HTTP nhưng không xử lý được Order. Một SDK client có thể được khởi tạo thành công trong bộ nhớ nhưng chưa hoàn tất thao tác mạng cần thiết. Một KV probe có thể thành công trong khi truy vấn theo field thiếu secondary index.

Phải xác định **đường đi mà ứng dụng cần thực sự kiểm tra**, thay vì chỉ hỏi “Couchbase có up không?” ở mức quá chung.

## 3. Năm khái niệm không được nhầm

| Khái niệm | Câu hỏi | Phản ứng vận hành thường gặp |
| --- | --- | --- |
| **Startup** | Ứng dụng đã hoàn tất quá trình khởi tạo cần thiết để phục vụ chưa? | Chặn liveness/readiness đánh giá quá sớm khi khởi động lâu |
| **Liveness** | Tiến trình có bị kẹt tới mức cần khởi động lại không? | Orchestrator có thể restart container khi thật sự không sống |
| **Readiness** | Instance này có nên nhận request mới ngay lúc này không? | Loại instance tạm khỏi endpoint routing khi không sẵn sàng |
| **Dependency health** | KV, Query Service hoặc hệ ngoài có phản hồi trong ngân sách kiểm tra không? | Tác động readiness/cảnh báo tùy criticality |
| **Deep functional check** | Một thao tác đúng keyspace, quyền, index và logic nghiệp vụ có hoạt động? | Synthetic monitor, smoke/integration test, chẩn đoán có kiểm soát |

### 3.1. Liveness không phải kiểm tra Couchbase

Nếu Couchbase tạm thời unavailable mà JVM vẫn xử lý request, logging, retry có giới hạn và phục hồi khi kết nối trở lại, restart mọi pod Spring Boot thường **không làm Couchbase phục hồi**. Ngược lại, restart đồng loạt có thể tăng connection storm và làm outage nghiêm trọng hơn.

Liveness nên phản ánh sức khỏe **bản thân tiến trình**. Nếu cần dependency awareness, thường đặt ở readiness hoặc một endpoint chẩn đoán riêng.

### 3.2. Readiness không đơn giản là “database luôn phải UP”

Nếu mọi endpoint của dịch vụ Orders đều phụ thuộc Couchbase, việc mất kết nối KV có thể khiến instance không thể phục vụ traffic hữu ích. Nhưng nếu một phần endpoint vẫn phục vụ từ cache hoặc dịch vụ vẫn có khả năng degrade có chủ đích, việc hạ readiness của **toàn bộ pod** có thể không phù hợp.

Hơn nữa, nếu nhiều pod đều phụ thuộc cùng Couchbase cluster đang lỗi, đưa tất cả pod về NotReady có thể khiến Service **không còn endpoint nhận traffic**. Đó có thể là hành vi mong muốn cho API bắt buộc data source, hoặc có thể tạo cascading outage với hệ thống lân cận. Cần quyết định từ hợp đồng phục vụ, không áp đặt một cấu hình chung.

### 3.3. Health-check success không đồng nghĩa business correctness

KV `exists("__probe__")` thành công chỉ chứng tỏ một request KV đã được xử lý theo ngữ cảnh/credential hiện tại. Nó không chứng minh `save` CAS thành công, transaction nhiều document commit, SQL++ có index hay Query Service đủ throughput.

## 4. Định nghĩa hợp đồng readiness trước khi cấu hình

Giả sử ứng dụng quản lý khách hàng và đơn hàng có những endpoint:

| Endpoint | Phụ thuộc tối thiểu | Tác động khi phụ thuộc lỗi |
| --- | --- | --- |
| `GET /orders/{id}` | Active KV path, đúng collection và quyền đọc | Có thể trả lỗi nếu không có nguồn khác |
| `POST /orders` | KV mutation, quyền ghi, idempotency | Không được báo thành công khi chưa xác nhận ghi |
| `GET /customers/{id}/orders` | Query Service, GSI, đúng scope/collection và query plan | Có thể timeout/thiếu khả năng tìm theo field |
| `GET /reports/orders` | SQL++ hoặc read model/báo cáo riêng | Có thể degrade tùy SLO |
| `GET /public/config` | Có thể không cần Couchbase | Vẫn có thể phục vụ |
| `GET /actuator/health/liveness` | Spring Boot process/availability | Không nên phụ thuộc Couchbase |

Từ bảng này, viết rõ:

- **Readiness tối thiểu:** instance có thể nhận request và kết nối KV nếu phần lớn traffic bắt buộc KV.
- **Query-path readiness:** có thể đo riêng khi SQL++ là dependency cốt lõi; không nhất thiết chạy Query Service mỗi vài giây trong liveness.
- **Deep business probe:** kiểm tra quyền, index, kết quả mapping trong một bài synthetic hoặc smoke test định kỳ, **không phải mọi Kubernetes probe**.

Mỗi quyết định phải có **ngân sách timeout**, cách xử lý lỗi và hậu quả khi tất cả instance cùng đánh dấu NotReady.

## 5. Connection configuration: đúng địa chỉ chưa đủ

Ví dụ ứng dụng Spring Boot dùng starter của Spring Data Couchbase:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Cấu hình minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Các tham số thực tế phải lấy từ secret manager/environment, không commit credential thật. Với kết nối TLS phù hợp, connection string có thể dùng lược đồ `couchbases://` cùng cấu hình certificate/trust cần thiết của môi trường.

**Những điều cấu hình trên chưa bảo đảm:**

- Scope `sales` và collection `orders` đã tồn tại.
- User có quyền KV read/write trên collection dự định.
- Query Service đang khả dụng và user có quyền SQL++.
- Secondary index phục vụ `findByCustomerId(...)` đã online.
- TLS chain, hostname, DNS và network policy từ pod tới mọi node/dịch vụ đều hợp lệ.
- Query đạt SLO latency trong lúc Index Service backlog.

Không xem việc Spring đọc được YAML và tạo bean `Cluster` là chứng cứ rằng mọi đường truy cập thực sự thông suốt.

## 6. Kết nối mạng là một quá trình nhiều giai đoạn

Một chuỗi điều tra hợp lý:

~~~mermaid
flowchart TD
    A["Spring khởi tạo SDK"] --> B["Phân giải DNS / seed nodes"]
    B --> C["TCP / TLS handshake"]
    C --> D["Cluster bootstrap/config"]
    D --> E["Xác thực và mở bucket"]
    E --> F["KV request tới collection"]
    F --> G["SQL++ query tới Query Service"]
    G --> H["Truy cập GSI cần thiết"]
~~~

Ở mỗi giai đoạn có thể thất bại độc lập:

1. **DNS/seed:** địa chỉ sai, DNS không phân giải, endpoint private không truy cập được.
2. **Firewall/network policy:** TCP connect tới một hoặc nhiều dịch vụ/endpoint bị chặn.
3. **TLS:** certificate chain, hostname verification hoặc trust configuration không đúng.
4. **Authentication:** username/password hoặc cơ chế chứng thực không hợp lệ.
5. **Authorization:** user đăng nhập được nhưng thiếu quyền trên bucket/scope/collection.
6. **Bucket/collection:** tên sai, chưa tồn tại hoặc không được mở trên môi trường đang dùng.
7. **Query/Index:** KV hoạt động nhưng SQL++ service unavailable, index offline hoặc query permission thiếu.
8. **Timeout/capacity:** kết nối không hoàn toàn hỏng nhưng response vượt ngân sách.

Do SDK có cơ chế bootstrap/kết nối nền tùy phiên bản, lỗi thực có thể chỉ xuất hiện khi thực hiện **thao tác I/O**, không nhất thiết ngay tại constructor hoặc lúc app in thông báo started.

## 7. Actuator health endpoints của Spring Boot

Khi dùng Spring Boot Actuator, endpoint health thường có dạng:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Đường liveness/readiness cần được bật/hỗ trợ theo phiên bản và cấu hình ứng dụng. Một cấu hình cơ bản:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Với cấu hình phù hợp, request trả payload mức khái quát như:

~~~json
{
  "status": "UP"
}
~~~

Hoặc khi chưa sẵn sàng:

~~~json
{
  "status": "OUT_OF_SERVICE"
}
~~~

Cách ánh xạ trạng thái sang HTTP code có thể cấu hình; thông thường những trạng thái unhealthy như `DOWN` hoặc `OUT_OF_SERVICE` được trả bằng HTTP 503. **Không xây logic orchestration bằng cách parse JSON text trong khi bỏ qua HTTP status.**

### 7.1. Vì sao không nên phơi toàn bộ health details?

Response chi tiết có thể tiết lộ tên dependency, phiên bản, host, exception hoặc topology. Endpoint probe nên trả status cần thiết; diagnostics sâu và metrics phải có xác thực/phân quyền, không công khai cho Internet.

### 7.2. Kiểm tra khả dụng bằng lệnh đơn giản

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Nếu trả 404, xác minh Actuator dependency, probe configuration, context path và phiên bản. Nếu trả 401/403, xem security configuration; không tắt bảo mật toàn bộ ứng dụng chỉ để Kubernetes probe hoạt động. Nếu 503, kiểm tra health group/availability state và contributor đang báo lỗi.

## 8. Spring Boot availability states và thời điểm nhận traffic

Spring Boot có khái niệm availability state, trong đó:

- **LivenessState:** tiến trình ở trạng thái correct hoặc broken theo tín hiệu ứng dụng.
- **ReadinessState:** tiến trình đang accepting traffic hoặc refusing traffic.

Spring Boot có thể phản ánh những state này qua health indicators `livenessState` và `readinessState`, được đưa vào các health group tương ứng khi probe support được bật.

Về mặt luồng khởi động, ứng dụng có thể:

~~~text
JVM start
  -> Spring context tạo bean
  -> ứng dụng chạy các bước khởi tạo
  -> trạng thái readiness chuyển sang ACCEPTING_TRAFFIC
  -> Kubernetes có thể đưa pod vào Service endpoints
~~~

Đây là mô hình khái niệm; thứ tự callback, runner và tín hiệu availability phụ thuộc vòng đời Spring Boot thực. Không tự phát tín hiệu “ready” trước khi các tài nguyên bắt buộc hoàn tất initialization.

### 8.1. Ready rồi vẫn có thể mất dependency

Một ứng dụng đã ready lúc 10:00 có thể mất Couchbase lúc 10:05. Health checks sau đó cần phản ánh chính sách runtime. Đừng chỉ đặt một phép kiểm tra lúc startup rồi coi trạng thái sẵn sàng được bảo đảm vĩnh viễn.

### 8.2. Readiness không thay API error handling

Kubernetes cập nhật readiness theo chu kỳ; trong khoảng giữa các lần probe, một request thực vẫn có thể gặp lỗi Couchbase. Controller/service cần xử lý timeout, lỗi dependency, idempotency và response thích hợp. Health endpoint không thay lỗi runtime được phân loại đúng.

## 9. Couchbase health indicator do Spring Boot cung cấp

Ở các dòng Spring Boot có Couchbase Actuator auto-configuration, ứng dụng có thể có health contributor cho Couchbase (thường có tên `couchbase`). Contributor này thực hiện một loại kiểm tra do phiên bản framework/SDK quy định.

**Điều cần kiểm tra trực tiếp trong môi trường đang dùng:**

1. Starter Actuator có trên classpath.
2. SDK/Cluster bean và autoconfiguration Couchbase có được tạo.
3. Có health contributor `couchbase` đang đăng ký không.
4. Check này đo connectivity kiểu nào, timeout ra sao.
5. Nó có kiểm tra **bucket/collection/Query Service/index** mà ứng dụng cần, hay chỉ kiểm tra một phần dịch vụ?

**Không suy rằng status `UP` của CouchbaseHealthIndicator đồng nghĩa mọi SQL++ repository query đều có thể chạy.** Một health contributor chung thường không chứng minh query cụ thể có index, quyền truy cập hoặc type mapping đúng.

### 9.1. Tránh một cấu hình giả định health contributor luôn tồn tại

Nếu project không bật Couchbase auto health hoặc dùng cấu hình rất khác, thêm tên `couchbase` vào một health group có thể khiến Spring Boot báo group không tìm thấy contributor tùy phiên bản/validation. Phải xác minh contributor trước khi đưa cấu hình vào production; không tắt validation để che cấu hình sai.

## 10. Readiness health group: lựa chọn dependency có chủ đích

Một health group readiness tối thiểu có thể chỉ dựa trên state của ứng dụng:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState
~~~

Nếu **hợp đồng phục vụ** yêu cầu Couchbase luôn khả dụng mới nhận traffic, ở phiên bản có contributor `couchbase`, có thể đưa nó vào readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,couchbase
~~~

Hai khối trên là **hai lựa chọn chính sách**, không phải phải gộp cả hai. Không nên copy block thứ hai nếu `couchbase` contributor không tồn tại.

### 10.1. Khi nào nên include Couchbase?

Cân nhắc khi phần lớn request thực sự không thể thành công nếu KV unavailable và ứng dụng không có fallback có ý nghĩa. Hạ readiness sẽ tránh tiếp tục gửi traffic tới một instance đang không đáp ứng hợp đồng.

### 10.2. Khi nào không nên include trực tiếp?

Cân nhắc để readiness dựa trên ứng dụng nếu:

- Mất Couchbase là lỗi **chung cho mọi pod**, việc loại mọi pod chỉ tạo tình trạng không có endpoints.
- Ứng dụng vẫn có thể trả các API quan trọng từ nguồn khác hoặc degrade an toàn.
- Health dependency quá chậm/flaky khiến instance dao động Ready/NotReady.
- Mỗi probe đắt hoặc có nguy cơ góp phần làm database quá tải.

Trong các trường hợp này cần **metrics/alert và error handling độc lập**; không có nghĩa được phép giấu outage.

### 10.3. Một endpoint có thể cần hai loại readiness

Nếu cùng service chứa hai nhóm route với dependency khác nhau, một readiness boolean cho cả pod có thể quá thô. Hãy cân nhắc tách deployment/service, kiểm tra theo chức năng ở synthetic monitor, hoặc thiết kế degrade có chủ đích. Đừng cố nhét toàn bộ danh sách nghiệp vụ vào một health check nhiều giây.

## 11. Thao tác KV tối thiểu để kiểm tra collection

Một phép kiểm tra đơn giản có thể gọi KV `exists` theo key giả định không quan trọng. Mục đích **không phải** tìm một document thật, mà là xác minh một request đến đúng collection và nhận response từ KV Service.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;
import com.couchbase.client.java.kv.ExistsResult;

public class OrdersKvProbe {

    private final Collection orders;

    public OrdersKvProbe(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public void check() {
        ExistsResult response = orders.exists(
                "__orders_readiness_probe__",
                ExistsOptions.existsOptions()
                        .timeout(Duration.ofSeconds(1)));

        // false vẫn có thể là một phản hồi KV khỏe mạnh:
        // key sentinel không cần tồn tại.
        boolean documentExists = response.exists();
    }
}
~~~

Đây là ví dụ cách dùng API SDK 3.x. `documentExists` chỉ có ý nghĩa nếu ứng dụng muốn kiểm tra sentinel data; với mục tiêu connectivity, **lệnh hoàn thành mà không lỗi** là điều quan trọng. Không coi `exists() == false` là DOWN.

### 11.1. Ưu điểm của read-only KV probe

- Không ghi/xóa dữ liệu thử mỗi vài giây.
- Không cần Query Service hoặc secondary index.
- Có thể đi đúng scope/collection mà Order API dùng.
- Có thể đặt timeout ngắn, tần suất thấp và điều khiển tải.

### 11.2. Giới hạn của KV exists probe

- Không chứng minh quyền **ghi** hoặc CAS/transaction hoạt động.
- Không chứng minh truy vấn SQL++ có index.
- Không chứng minh cache/replica/cross-region đủ mới.
- Một phản hồi thành công tại thời điểm T không bảo đảm request sau đó luôn thành công.
- Nếu không có quyền KV thích hợp hoặc SDK timeout, check báo lỗi dù ứng dụng có thể vẫn phục vụ một số route khác.

Vì vậy, chỉ dùng nó trong readiness nếu KV thực sự là dependency cần thiết của instance.

## 12. Viết HealthIndicator đọc-only cho Spring Boot

Một custom `HealthIndicator` phù hợp khi bạn cần kiểm tra **đúng collection** theo yêu cầu nghiệp vụ, thay vì chỉ dùng health contributor chung của Couchbase.

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.ExistsOptions;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersKv")
public class OrdersKvHealthIndicator implements HealthIndicator {

    private final Collection orders;

    public OrdersKvHealthIndicator(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    @Override
    public Health health() {
        try {
            orders.exists(
                    "__orders_readiness_probe__",
                    ExistsOptions.existsOptions()
                            .timeout(Duration.ofSeconds(1)));

            return Health.up()
                    .withDetail("check", "orders-kv")
                    .build();
        } catch (Exception failure) {
            // Log nội bộ đã được khử nhạy cảm ở nơi phù hợp.
            return Health.down()
                    .withDetail("check", "orders-kv")
                    .build();
        }
    }
}
~~~

Đây là bản demo **đồng bộ**. Trong hệ thống thật nên xem exception type, logging và timeout của SDK, đồng thời cân nhắc instrumentation/circuit breaker để tránh một sự cố mạng khiến health check treo hàng loạt thread.

### 12.1. Include custom indicator trong readiness

Nếu `ordersKv` thực sự là contributor được đăng ký với ID tương ứng, và readiness bắt buộc kiểm tra collection đó:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,ordersKv
~~~

Không cần đồng thời include `couchbase` nếu điều đó tạo kiểm tra trùng không mang thêm thông tin; phụ thuộc mức độ sâu của health contributor hiện có. Nếu muốn cả hai, phải đo chi phí và xem cấu hình thực tế.

### 12.2. Không nhầm HealthIndicator với application service

Health endpoint cần đơn giản, nhanh, read-only và có ngân sách rõ. Nó không nên gọi một workflow đặt hàng thật, trừ khi đang chạy **synthetic test riêng biệt** với quyền, dữ liệu test và cleanup có kiểm soát.

## 13. Tại sao không nên thực hiện INSERT trong mỗi readiness probe?

Một giải pháp tưởng là “đáng tin nhất” là mỗi vài giây tạo một document, query rồi xóa. Nhưng trong Kubernetes với 50 pod và ba probes/pod, chiến lược này có thể khiến database chịu:

- Hàng nghìn mutation không cần thiết trong mỗi khoảng thời gian.
- Chi phí duy trì secondary index.
- Dữ liệu rác nếu write/delete timeout hoặc kết quả ambiguous.
- Race giữa các probe và nguy cơ collision key.
- Sự cố cascade khi database vốn đang quá tải.
- Yêu cầu quyền write quá rộng cho endpoint health.

**Khuyến nghị:** Readiness thường chỉ cần check tối thiểu đáp ứng hợp đồng phục vụ. Đưa end-to-end CRUD/SQL++ consistency check có mutation sang **synthetic monitor hoặc integration test** chạy tần suất thấp, namespace tách biệt và có cleanup.

## 14. SDK ping, diagnostics và waitUntilReady có ý nghĩa gì?

Couchbase Java SDK có những cơ chế để kiểm tra khả năng tiếp cận dịch vụ, trạng thái endpoint và chờ tài nguyên sẵn sàng. Tùy phiên bản, người dùng có thể gặp các khái niệm:

- **Ping:** thực hiện phép kiểm tra phản hồi tới những loại dịch vụ được SDK hỗ trợ.
- **Diagnostics:** cung cấp trạng thái/thông tin của các endpoint client đang biết tại thời điểm gọi.
- **Wait until ready:** đợi tài nguyên/client đạt trạng thái sẵn sàng theo điều kiện/timeout của API.

Các cơ chế này **không đồng nghĩa**:

| Phép kiểm tra | Có thể giúp trả lời | Không tự chứng minh |
| --- | --- | --- |
| SDK ping | Dịch vụ/endpoint được chọn có phản hồi không? | Query business, index, RBAC đầy đủ |
| SDK diagnostics | Client thấy các connection/endpoint ở trạng thái nào? | Tất cả nghiệp vụ sẽ thành công |
| `Bucket.waitUntilReady(...)` | Bucket/client đã đạt điều kiện ready được yêu cầu trong timeout? | Mọi collection/index và transaction đều hoạt động |
| KV `exists` | Đúng collection có thể phục vụ một KV operation? | Quyền SQL++ hoặc index đầy đủ |
| SQL++ `SELECT RAW 1` | Query Service có thể thực thi một câu query rất nhỏ? | GSI/index theo customerId đã online |
| Query nghiệp vụ có `EXPLAIN` và read-only SQL++ | Query/index/keyspace/permission tương ứng có thể hoạt động? | Write, transaction và các index khác |

Ví dụ một bước warm-up có kiểm soát theo API SDK hiện hành:

~~~java
import java.time.Duration;

var bucket = cluster.bucket("shop");
bucket.waitUntilReady(Duration.ofSeconds(10));
~~~

Đây là thao tác **chờ có timeout**, không phải lời hứa hoàn thành mọi connection trên mọi dịch vụ sau 10 giây. Phải đối chiếu chữ ký và điều kiện của SDK đang dùng. Không gọi `waitUntilReady` trên mỗi HTTP request hoặc mỗi health probe.

### 14.1. Tại sao “new Cluster đã thành công” không đủ?

Khởi tạo client có thể thiết lập bootstrap/connection nền. Một lần request đầu mới bộc lộ sai network, certificate hoặc quyền. Phải kiểm tra **operation thật** khi hợp đồng readiness yêu cầu, và mô tả check đã đi qua dịch vụ nào.

## 15. Kiểm tra Query Service không đồng nghĩa kiểm tra secondary index

Một SQL++ query tối thiểu:

~~~sql
SELECT RAW 1;
~~~

Có thể thử ở môi trường test/diagnostic để kiểm tra đường tới Query Service. Tuy nhiên, nó **không buộc phải quét một index trên collection Orders**.

Muốn kiểm tra đường query thực sự của ứng dụng, dùng câu truy vấn read-only với keyspace/field đã tạo index:

~~~sql
SELECT RAW META(o).id
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
LIMIT 1;
~~~

Ví dụ `$customerId` là một ID test an toàn và có thể không có row. **Không có row không có nghĩa query không khỏe**, miễn câu query được thực thi thành công theo dự kiến. Cần:

1. Kiểm tra index online.
2. Dùng `EXPLAIN` để biết index nào được chọn.
3. Xác minh user có đúng quyền Query.
4. Ghi query timeout và error rõ.
5. Nếu dùng `REQUEST_PLUS`, nhận thức rằng health check có thể phải **đợi index**, không phù hợp làm readiness probe cực thường xuyên.

### 15.1. Query Service hoạt động nhưng index chưa online

Một startup process có thể thấy KV đã UP và `SELECT RAW 1` trả thành công, trong khi truy vấn theo `customerId` lỗi thiếu index hoặc Index Service đang phục hồi. Khi đó cần **query-path check hoặc synthetic monitor** riêng, thay vì sửa một KV health check để tuyên bố nó kiểm tra mọi thứ.

## 16. Java SDK query probe có timeout và parameter binding

Đoạn mã minh họa một chẩn đoán SQL++ read-only, **không chạy ở mọi liveness check**:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

public class OrdersQueryDiagnostic {
    private final Cluster cluster;

    public OrdersQueryDiagnostic(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult checkIndexPath(String customerId) {
        String sql = """
            SELECT RAW META(o).id
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.customerId = $customerId
            LIMIT 1
            """;

        QueryOptions options = QueryOptions.queryOptions()
                .parameters(JsonObject.create()
                        .put("customerId", customerId))
                .scanConsistency(
                        QueryScanConsistency.NOT_BOUNDED)
                .timeout(Duration.ofSeconds(2));

        return cluster.query(sql, options);
    }
}
~~~

Dùng `NOT_BOUNDED` ở đây nhằm **kiểm tra khả năng thực thi đường Query/Index** mà không buộc probe chờ mọi mutation trước request; nó không đo độ mới index. `2s` là **giá trị minh họa**, phải điều chỉnh theo SLO và giới hạn tài nguyên.

Nếu yêu cầu sâu hơn là kiểm tra read-after-write, hãy làm một integration/synthetic test riêng với mutation token hoặc `REQUEST_PLUS`, fixture an toàn và cleanup.

### 16.1. Đừng dùng kết quả không có row để đánh dấu DOWN

Nếu `customerId` kiểm tra không tồn tại trong bộ dữ liệu, query có thể trả danh sách rỗng **nhưng đã chứng minh Query Service, quyền và index path thực thi được**. Trạng thái DOWN nên dựa vào lỗi/timeout không được chấp nhận; còn kiểm tra dữ liệu sentinel phải là một hợp đồng riêng có dữ liệu được quản lý.

### 16.2. Health probe và query diagnostics có SLO khác nhau

Một readiness probe phải kết thúc nhanh để orchestrator quyết định routing. Một diagnostic SQL++ sâu có thể mất thêm thời gian hoặc tốn tài nguyên. Tách chúng để một recovery của Index Service không bị khuếch đại thành hàng trăm query nặng mỗi giây.

## 17. Chọn phạm vi health: KV, Query, Index hay end-to-end?

| Nhu cầu | Kiểm tra nên đặt | Tần suất/chi phí gợi ý |
| --- | --- | --- |
| Pod process còn sống | Liveness state | Kubernetes probe nhẹ |
| Instance đã hoàn tất initialization | Readiness state | Kubernetes probe nhẹ |
| KV là dependency bắt buộc | Couchbase contributor/readonly KV check | Readiness có timeout/giới hạn |
| Query Service phục vụ endpoint trọng yếu | Query diagnostic tách biệt hoặc readiness có kiểm soát | Cân nhắc kỹ chi phí; không lặp query nặng |
| Index Orders đã online và dùng được | Read-only SQL++ có `EXPLAIN` lúc deploy/synthetic | Tần suất thấp, quyền phù hợp |
| CRUD + SQL++ read-after-write đúng | Synthetic/integration test riêng | Tách dữ liệu/cluster, cleanup |
| CAS/transaction đúng dưới cạnh tranh | Integration/concurrency test | Không phù hợp health probe |
| Replica/Search freshness | Probe riêng theo API dịch vụ đó | Không suy từ KV/SQL++ health |

**Mức sâu hơn thường đắt hơn** và có thể phụ thuộc dữ liệu/traffic. Đừng biến liveness thành danh sách dài mọi API phải thành công.

## 18. Kubernetes startup, liveness và readiness probes

Ví dụ trích từ Deployment dành cho ứng dụng phục vụ port 8080, **Actuator cũng dùng cùng port**:

~~~yaml
containers:
  - name: orders-api
    image: registry.example.invalid/orders-api:TAG
    ports:
      - containerPort: 8080

    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 2
      timeoutSeconds: 2
      failureThreshold: 30

    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3

    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
~~~

Các giá trị thời gian chỉ là **ví dụ**; cần chọn từ startup time, query/health budget và mức nhạy với lỗi tạm thời của hệ thống. `startupProbe` giúp bảo vệ giai đoạn khởi động lâu khỏi việc liveness restart quá sớm. Readiness quyết định **có đưa pod vào endpoints để nhận traffic hay không**, còn liveness có thể dẫn tới restart.

### 18.1. Không gắn Couchbase vào liveness

Nếu Couchbase cluster outage, liveness nên vẫn phản ánh process còn hoạt động. Một readiness liên kết dependency có thể chuyển sang DOWN/OUT_OF_SERVICE tùy chính sách. Nếu đặt check Couchbase vào liveness, mất dependency có thể gây restart đồng loạt, cache warm-up/connection storm và làm tình hình xấu đi.

### 18.2. Cẩn thận nếu dùng management port riêng

Nếu Actuator được phục vụ ở một **port quản trị khác port HTTP ứng dụng**, endpoint health có thể vẫn UP dù main application port bị kẹt hoặc không chấp nhận request. Khi có thể, cho probes đi qua **đường phục vụ tương tự HTTP traffic thật**, hoặc dùng tính năng bổ sung đường health lên main port của phiên bản Spring Boot đang chạy.

### 18.3. Network policy và security

Kubernetes kubelet phải truy cập được probe path/port, nhưng endpoint health không cần công khai toàn Internet. Sử dụng network policy, security configuration và HTTP status codes thích hợp; tránh mở tất cả Actuator endpoints.

## 19. Startup check: khi nào nên đợi bucket sẵn sàng?

Một ứng dụng có thể cần hoàn tất cấu hình/validation trước khi nhận traffic. Các bước được cân nhắc:

- Kết nối tới cluster và xác minh credential.
- Bucket đã tồn tại và có quyền cần thiết.
- Collection quan trọng đã có sẵn.
- Migration/index deployment đã được thực hiện bởi quy trình riêng.
- Cache/read model bắt buộc đã nạp xong nếu ứng dụng yêu cầu.
- Warm-up hoặc lazy init không gây timeout request đầu tiên.

**Không nhất thiết ép Spring application fail startup mỗi khi Couchbase tạm thời unavailable.** Nếu dependency có thể phục hồi tự động, để process sống nhưng readiness từ chối traffic là một lựa chọn. Nếu thiếu schema/keyspace là lỗi cấu hình không thể phục hồi mà không deploy lại, fail-fast có thể phù hợp.

### 19.1. Phân biệt lỗi tạm thời và lỗi cấu hình

| Lỗi | Hành vi khởi động có thể phù hợp |
| --- | --- |
| DNS/network tạm thời unavailable | Retry giới hạn hoặc NotReady, không restart storm |
| Username/password cấu hình sai | Cảnh báo rõ, có thể fail startup/deployment |
| Bucket/scope/collection không tồn tại | Fail deployment validation hoặc NotReady cho đến khi provision |
| Index chưa tạo do migration | Không tạo index âm thầm trong health; chạy migration riêng |
| Query Service đang rebalance | Degrade/chờ theo SLO, theo dõi recovery |
| Application không thể bind port | Liveness/startup không thành công; sửa lỗi ứng dụng |

Không gộp tất cả exception thành `DOWN: database` mà không có thông tin nội bộ đủ để điều tra.

## 20. Readiness và rủi ro cascading outage

Một tình huống:

~~~text
Couchbase cluster tạm thời nghẽn
   -> mỗi pod gọi DB health check liên tục
   -> tất cả pod NotReady
   -> không còn Kubernetes endpoints
   -> client retry dữ dội / traffic dồn hệ thống khác
   -> khi DB phục hồi, các pod đồng thời reconnect
~~~

Không phải mọi hệ thống đều đi theo chuỗi trên, nhưng nó là **rủi ro thiết kế**.

Các biện pháp:

1. Giữ health check nhẹ và có timeout rõ.
2. Dùng liveness độc lập dependency.
3. Quy định readiness fail hay degrade theo tính quan trọng của Couchbase với request.
4. Giới hạn tần suất, concurrent checks, retries và connection warm-up.
5. Có alert riêng cho cluster, Query/Index Service và API error rate.
6. Kiểm tra recovery behavior khi DB trở lại.
7. Tránh mọi instance tự tạo index hoặc sửa schema trong health handler.
8. Không dùng một endpoint SQL++ đắt làm probe cho hàng trăm replica.

Cần nhớ: nếu mọi pod mất cùng một dependency, **load balancer không thể tự biến database khỏe lại** bằng cách loại những pod đó khỏi routing.

## 21. Quan sát bằng metrics, logs và traces

Health endpoint là một tín hiệu đơn giản; để chẩn đoán cần dữ liệu quan sát phong phú hơn.

| Tín hiệu | Câu hỏi |
| --- | --- |
| Availability state transitions | Pod chuyển Ready/NotReady khi nào? |
| Actuator health contributor failures | Check nào đang báo lỗi? |
| Couchbase SDK timeout/error categories | Lỗi DNS, TLS, auth, KV hay Query? |
| KV request latency p50/p95/p99 | Data path chậm hay không? |
| Query latency, timeout và error rate | SQL++ có hoạt động và đáp ứng SLO không? |
| Index state, update backlog/lag | Index có bắt kịp mutation không? |
| HTTP 5xx và latency | Người dùng thực sự bị ảnh hưởng ra sao? |
| Connection pool/endpoint health của SDK | Client có đang phục hồi connection? |
| Pod restart count và readiness flaps | Health policy có tạo vòng lặp restart không? |
| Network DNS/TLS errors | Vấn đề nằm ở mạng/chứng thực? |

Tên metric chính xác phụ thuộc Spring Boot, Micrometer, SDK và Couchbase Server version; nên lấy từ dashboard/runtime thay vì bịa tên metric cố định.

### 21.1. Một trace minh họa

~~~text
requestId=demo-123
endpoint=GET /customers/c-1001/orders
dependency=couchbase
operation=SQL++
keyspace=shop.sales.orders
query.timeout=true
http.status=503
readiness.state=ACCEPTING_TRAFFIC
~~~

Đây là ví dụ về trường dữ liệu log, không phải format mặc định SDK. Nó cho thấy readiness từng thời điểm có thể còn accepting traffic trong khi một request query thất bại; cần nhìn **runtime errors** chứ không chỉ health.

### 21.2. Không log bí mật

Không log password, connection string chứa credential, bearer token, session ID, toàn bộ JSON khách hàng hay chi tiết thanh toán. Có thể log tên operation, keyspace đã chuẩn hóa, error category, duration, correlation ID và status sau khi che thông tin nhạy cảm.

## 22. Phân loại lỗi để xử lý đúng

| Triệu chứng | Khả năng nguyên nhân | Hướng xác minh |
| --- | --- | --- |
| `/health/liveness` trả 503 | Application liveness state broken/handler lỗi | Spring logs, JVM, startup |
| `/health/readiness` trả 503 | Chưa accepting traffic hoặc contributor DOWN | Health group, availability events |
| Actuator health UP, `findById` lỗi | Health không kiểm tra đúng collection/quyền, lỗi mới xảy ra | KV exists/get qua keyspace |
| KV OK, SQL++ timeout | Query Service/index/plan/timeout | Query logs, EXPLAIN, index metrics |
| KV OK, SQL++ báo thiếu index | Index chưa tạo/online hoặc query plan | Triển khai index, EXPLAIN |
| Connection timeout khi bootstrap | DNS, mạng, endpoint/port | Resolver, NetworkPolicy, firewall |
| TLS handshake lỗi | Cert chain/trust/hostname | TLS config, certificate validity |
| Authentication lỗi | Credential/secret mismatch | Kiểm tra secret/rotation và RBAC |
| Authorization lỗi | User thiếu quyền keyspace/Query | RBAC theo bucket/scope/collection |
| Một pod lỗi, pod khác OK | DNS route, node network, config, stale credentials | So sánh topology/versions |
| Tất cả pod NotReady cùng lúc | Dependency chung hoặc health policy quá nhạy | Cluster metrics, probe config |
| Health check luôn timeout khi DB tải cao | Probe quá đắt/timeout không hợp lý | Rút nhẹ check, hạn chế tần suất |

### 22.1. Đừng sửa mọi lỗi bằng tăng timeout

Nếu user thiếu quyền hoặc bucket sai tên, tăng timeout không giúp. Nếu index chưa online, retry vô hạn làm logs nhiễu. Nếu chỉ là một spike ngắn, timeout quá thấp lại gây readiness flapping. Phải phân loại lỗi trước khi chọn chính sách retry, timeout, alert hoặc fail-fast.

## 23. Tương quan giữa SQL++ scan consistency và readiness

Trong chương nhất quán, `NOT_BOUNDED`, `REQUEST_PLUS` và mutation-based `consistentWith` diễn đạt **mốc tiến của secondary index trước khi query quét**.

Chúng không giống connectivity:

- KV probe thành công không nghĩa SQL++ query `REQUEST_PLUS` sẽ hoàn tất nhanh.
- `SELECT RAW 1` thành công không nghĩa GSI đã phản ánh ghi vừa xảy ra.
- `NOT_BOUNDED` query trả row không nghĩa index không có lag.
- `REQUEST_PLUS` query timeout có thể do index backlog, không đồng nghĩa mọi node Data Service chết.
- Query được bọc `@Cacheable` có thể trả cache mà không gọi Couchbase.
- Một Query Service đang hoạt động không đảm bảo Search index, Analytics hoặc replication cross-region đã đủ mới.

**Sự phân tầng đúng:**

~~~text
Liveness           : JVM/process có thể tiếp tục vận hành?
Readiness          : pod nên nhận traffic lúc này?
KV dependency      : đúng collection có thể phục vụ KV?
SQL++ dependency   : Query Service/index path thực thi được?
Data freshness     : index đã nhìn thấy mutation cần thiết?
Business invariant : ghi có an toàn CAS/transaction/idempotency?
~~~

Đừng dùng một phép kiểm tra cho tất cả các câu hỏi này.

## 24. TTL, CAS, transaction và durability: ngoài phạm vi health cơ bản

### 24.1. CAS

`@Version` ở Spring Data Couchbase có thể hỗ trợ optimistic locking theo CAS. Một KV health probe thành công không chứng minh hai nhân viên cập nhật đồng thời đã xử lý conflict đúng. Phải có integration/concurrency test ở đường ghi.

### 24.2. Durability

Một mutation với durability cao có thể yêu cầu xác nhận bền/nhân bản theo option. Health `UP` không nói mutation sau đó chắc chắn đạt durability SLO; phải cấu hình write options và xử lý timeout/ambiguous result.

### 24.3. Transaction

Một API tạo Order và trừ Inventory cần transaction hoặc workflow bù trừ/idempotency nếu hai thay đổi phải cùng thành công. Health endpoint không nên chạy transaction thật mỗi vài giây để “chứng minh hệ thống OK”.

### 24.4. TTL

Session có expiry metadata; document TTL không phải một JSON field `expiresAt` tự hoạt động. Health KV exists trên một sentinel key không chứng minh toàn bộ TTL/session revocation workflow đúng. Kiểm thử TTL phải tách khỏi readiness.

### 24.5. Reactive

Reactive client/Repository có thể giúp tránh blocking thread khi xử lý I/O, nhưng một query timeout/index lag vẫn tồn tại ở database. Không coi việc chuyển WebFlux là cách “chữa” trạng thái NotReady do dependency lỗi.

## 25. Reactive HealthIndicator cần tránh blocking event loop

Trong ứng dụng Spring WebFlux, một health check được xử lý trên event loop không nên gọi trực tiếp SDK blocking operation nhiều giây. Có thể:

- Dùng `ReactiveHealthIndicator` và API reactive thực sự của Couchbase SDK theo phiên bản.
- Nếu phải dùng thư viện blocking, cô lập khỏi event loop bằng scheduler chuyên cho blocking với giới hạn phù hợp.
- Đặt timeout và trả status chính xác thay vì tự `subscribe()` rồi lập tức báo UP.
- Quan sát cancellation, exception và retry.
- Không phát sinh hàng nghìn request nền khi dependency đang lỗi.

Pseudocode luồng:

~~~java
// Minh họa cấu trúc, không phải class độc lập biên dịch.
// Reactive client và operation tùy SDK version.
Mono<Health> health() {
    return reactiveKvProbe()
            .thenReturn(Health.up().build())
            .onErrorResume(error ->
                    Mono.just(Health.down().build()));
}
~~~

Một `Mono<Health>` chỉ được coi là success sau khi **I/O đã hoàn thành**; không trả UP ngay khi chỉ mới tạo Publisher. Spring Boot có ReactiveHealthIndicator và cơ chế health endpoint tương ứng khi sử dụng reactive stack. Kiểm tra signature và threading trên đúng phiên bản.

## 26. Timeout budget: giảm nhiễu mà không che lỗi thật

Ví dụ chỉ để minh họa một ngân sách:

~~~text
Kubernetes readiness timeout: 2 s
  |
  +-- health handler overhead: nhỏ
  +-- KV exists timeout: 1 s
  +-- response serialization: nhỏ
  +-- buffer dành cho scheduling/network
~~~

Nếu SDK operation timeout lớn hơn Kubernetes timeout, kubelet có thể bỏ probe trước khi health handler hoàn thành. Nếu mọi probe cùng sử dụng một deadline quá thấp khi cluster đang spike, pod có thể flip Ready/NotReady liên tục.

**Không có cấu hình chuẩn duy nhất**. Cần đo p95/p99 bình thường của KV operation và mức chịu lỗi cho phép. Đồng thời:

- Health check không nên retry nhiều lần trong một probe.
- Retry chung của SDK có thể tác động tổng duration.
- Đặt số lần probe thất bại trước khi NotReady phù hợp.
- Giới hạn concurrency của health checks.
- Alert/diagnostics phân biệt spike ngắn với outage kéo dài.

### 26.1. Readiness không phải cách duy nhất ngăn quá tải

Khi Couchbase chậm nhưng vẫn phục vụ một phần traffic, cần thêm circuit breaker, rate limiting, backpressure, timeout ở business operations và load shedding. Readiness chỉ quyết định routing ở cấp pod, không thay mọi cơ chế resiliency.

## 27. Smoke test sau deploy: khác với liveness/readiness

Sau khi deploy phiên bản mới hoặc tạo index mới, thực hiện một **smoke test có kiểm soát**:

1. Gọi `/actuator/health/liveness`: app process đang sống.
2. Gọi `/actuator/health/readiness`: health policy cho phép nhận traffic.
3. Đọc một document đã biết theo ID trong namespace test: kiểm tra mapping và KV permission.
4. Chạy SQL++ read-only theo keyspace/index thực: kiểm tra Query Service và index.
5. Xác minh một Repository derived query hoặc `CouchbaseTemplate` method trả entity mapping đúng.
6. Kiểm tra `EXPLAIN`/index state khi vừa thay index definition.
7. Nếu cần read-after-write, chạy integration/synthetic test riêng có mutation ACK và scan consistency.
8. Xác minh log/metrics và error handling, không chỉ status code.
9. Cleanup dữ liệu test theo thiết kế, kể cả khi write ambiguous.

Đừng trộn smoke test có ghi dữ liệu vào Kubernetes readiness probe. Smoke test nên chạy với quyền và tần suất riêng, có audit và timeout.

## 28. Test tích hợp health endpoints trong Spring Boot

Ví dụ JUnit/Spring Boot Test cho một ứng dụng đã cấu hình Actuator và Couchbase **test cluster**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthEndpointIT {

    @Autowired
    private TestRestTemplate http;

    @Test
    void livenessIsAvailable() {
        ResponseEntity<String> response = http.getForEntity(
                "/actuator/health/liveness", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
    }

    @Test
    void readinessIsUpWhenDependenciesAreReady() {
        // Test fixture phải có Couchbase thật và health contributors
        // tương thích với readiness group đang cấu hình.
        ResponseEntity<String> response = http.getForEntity(
                "/actuator/health/readiness", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
    }
}
~~~

Mẫu test **phụ thuộc môi trường**:

- Tạo cluster/bucket/scope/collection test trước.
- Dùng credential có quyền tối thiểu cần thiết.
- Không dựa vào database production.
- Health group phải được bật và Actuator HTTP path đúng.
- Khi health contributor Couchbase timeout do hạ tầng CI không ổn định, báo rõ lỗi môi trường; không xóa assertion để “cho xanh”.
- Nếu cần test trạng thái DOWN, dùng dependency/indicator giả lập hoặc cluster lab tách biệt; không ngắt Couchbase production.

### 28.1. Test trạng thái không ready

Trong một test context kiểm soát được availability, có thể phát sự kiện readiness từ accepting sang refusing traffic và kiểm tra endpoint chuyển trạng thái phù hợp. Nếu readiness group còn có Couchbase contributor, cần tách test availability state khỏi lỗi dependency; đừng nhập hai nguyên nhân vào cùng assertion.

### 28.2. Test lỗi Query khác test readiness

Một integration test `findByCustomerId` thất bại vì index thiếu là **lỗi query/index**, không nên tự biến thành health endpoint DOWN trừ khi chính sách readiness đã quy định Query Service/index là dependency bắt buộc và check liên quan thực sự được chạy.

## 29. Kiểm thử lỗi kết nối và khôi phục theo kịch bản

Nhóm vận hành có thể tổ chức các kịch bản trên **cluster lab cô lập**:

| Kịch bản | Hành vi nên quan sát | Bằng chứng |
| --- | --- | --- |
| KV unavailable tạm thời | Business API lỗi được phân loại, readiness theo policy | KV timeout, health group status |
| Query Service unavailable | KV có thể vẫn dùng, SQL++ lỗi | Query error, index state |
| Secret sai | Authentication failure rõ, readiness/fail-fast theo thiết kế | Log đã khử nhạy cảm |
| Scope/collection chưa tạo | KV check/Repository phù hợp thất bại | Keyspace/RBAC diagnostics |
| Index offline | Query cần GSI lỗi/chậm, KV còn hoạt động | EXPLAIN, index metrics |
| Network latency tăng | Health latency, readiness flaps nếu budget kém | SDK/pod/network timings |
| Database phục hồi | Pod/SDK phục hồi mà không restart storm | Readiness transitions, connection recovery |
| Pod bị kill/kẹt thật | Liveness/startup có thể kích hoạt restart | Kubernetes events, restart count |

Không cần chủ động phá hỏng node Couchbase đang phục vụ khách hàng. Các test failover/network partition chỉ thực hiện khi có môi trường và quyền vận hành riêng cùng kế hoạch rollback.

## 30. Runbook chẩn đoán “pod ready nhưng không truy cập được Couchbase”

~~~mermaid
flowchart TD
    A["API lỗi khi thao tác Couchbase"] --> B{"Health/readiness đã include dependency?"}
    B -->|Không| C["Health UP không phủ nhận lỗi DB"]
    B -->|Có| D["Đọc contributor/status và timeout"]
    C --> E["Xác minh DNS, TLS, auth, network"]
    D --> E
    E --> F{"KV operation theo đúng collection thành công?"}
    F -->|Không| G["Kiểm tra RBAC, bucket/scope/collection, SDK endpoints"]
    F -->|Có| H{"SQL++ query đúng hoạt động?"}
    H -->|Không| I["Query Service, index online, EXPLAIN, timeout"]
    H -->|Có| J["Mapping, cache, CAS, transaction, business logic"]
    G --> K["Đo request errors / latency và khôi phục"]
    I --> K
    J --> K
~~~

**Trình tự điều tra thực tế:**

1. **Khoanh vùng:** một instance, một vùng mạng hay toàn cluster? endpoint KV hay SQL++?
2. **Xác nhận deployment:** image/config/secret/version vừa đổi gì?
3. **Xem HTTP health và availability:** liveness/readiness trả status gì, group include ai?
4. **Đọc log SDK đã khử nhạy cảm:** DNS, TLS, auth, timeout, permission hoặc index issue?
5. **Kiểm tra một KV operation read-only đúng keyspace.**
6. **Kiểm tra một SQL++ query read-only và EXPLAIN** nếu API truy vấn theo field lỗi.
7. **Đối chiếu metric Couchbase và pod:** CPU/memory, query p99, index backlog, connection recovery.
8. **Phân loại nguyên nhân:** cấu hình sai, quyền thiếu, dependency outage, index lag hay cache stale.
9. **Khôi phục theo nguyên nhân:** sửa secret/network/RBAC, điều chỉnh index, kiểm soát tải, rollback deploy nếu cần.
10. **Theo dõi sau khôi phục:** readiness ổn định, error rate giảm, query đạt SLO, không có retry storm.

Không dùng cách “restart tất cả pod” như phản xạ mặc định trước khi biết nguyên nhân.

## 31. Ma trận thiết kế health theo mục tiêu nghiệp vụ

| Mẫu triển khai | Liveness | Readiness | Deep diagnostics |
| --- | --- | --- | --- |
| Orders API phụ thuộc KV cho hầu hết route | Process state | App state + KV/Couchbase lightweight | SQL++/index/CRUD smoke riêng |
| Service báo cáo chủ yếu đọc read model | Process state | App state; xét dependency report riêng | Query/aggregate/read model freshness |
| Gateway có fallback khi Couchbase lỗi | Process state | App state nếu fallback vẫn đáp ứng contract | Dependency alert và degrade metrics |
| Batch worker không nhận HTTP traffic | Process/worker state | Theo giao thức/job scheduler phù hợp | Batch source/sink checks |
| WebFlux API dùng reactive SDK | Process state | Reactive/lightweight dependency check | Reactive SQL++ synthetic riêng |
| Nhiều route có dependency khác nhau | Process state | Cân nhắc chia deployment/service | Endpoint-specific functional monitors |

Không copy một mẫu cho mọi service; đọc từ đặc điểm traffic, điều kiện thất bại chấp nhận được và SLO.

## 32. Những lỗi thiết kế health check thường gặp

1. **Chỉ thấy `Started` nên coi đã ready:** SDK có thể chưa thực hiện I/O cần thiết.
2. **Đưa Couchbase vào liveness:** DB outage gây restart storm.
3. **Cho health chạy SQL++ query nặng liên tục:** chính probe làm tăng tải.
4. **Bỏ qua keyspace thật:** kết nối cluster OK nhưng thiếu collection/quyền của ứng dụng.
5. **`SELECT RAW 1` được coi là kiểm tra index:** câu query không cần GSI của Orders.
6. **Health `UP` được coi là bảo đảm mọi request đều thành công:** availability thay đổi theo thời gian.
7. **Health và HTTP app nằm ở port khác nhưng chỉ probe management port:** app port chính có thể lỗi.
8. **Health response phơi stack trace/topology/credential:** rủi ro bảo mật.
9. **Mỗi probe tạo và xóa một document:** tạo write load và fixture leaks.
10. **Không đặt timeout:** probe có thể chờ quá lâu hoặc tích tụ thread.
11. **Timeout quá ngắn:** readiness flapping dù dependency chỉ spike nhẹ.
12. **Không có cảnh báo runtime errors:** readiness UP nhưng Query API liên tục timeout.
13. **Đánh đồng SQL++ consistency với connectivity:** index lag khác lỗi kết nối.
14. **Đánh đồng cache với Couchbase:** ứng dụng có thể trả cached result dù backend down.
15. **Khi DB outage, hạ mọi pod readiness mà không xét khả năng degrade:** service có thể mất toàn bộ endpoints.
16. **Không kiểm thử recovery:** khi dependency trở lại, ứng dụng vẫn NotReady do state stale hoặc lỗi kết nối.
17. **Retry vô hạn trong health indicator:** nhân tải đúng lúc hệ thống yếu.
18. **Không version-pin cấu hình:** copy property từ Spring Boot generation khác mà không xác minh.
19. **Giữ health check đồng bộ trên event loop reactive:** chặn các request khác.
20. **Coi lỗi permission là lỗi transient:** retry không sửa được RBAC.

## 33. Bài tập thực hành

### Bài A — Chọn liveness và readiness

Couchbase cluster unavailable trong ba phút, JVM vẫn khỏe và có thể nhận HTTP.

**Hỏi:** Có nên để liveness DOWN không?

**Hướng giải:** Thông thường không. Để liveness phản ánh tiến trình; readiness quyết định theo contract dependency. Nếu DB outage ảnh hưởng mọi pod, đánh giá cascading risk và cơ chế degrade.

### Bài B — Cluster UP nhưng Order query lỗi

Actuator Couchbase contributor UP. `findByCustomerId` báo lỗi do thiếu secondary index.

**Hỏi:** Health có mâu thuẫn không?

**Hướng giải:** Không. Contributor có thể chỉ kiểm tra connectivity ở mức nào đó; nó không chứng minh index/query plan. Cần Query Service/index diagnostic hoặc smoke test riêng.

### Bài C — Chọn phép kiểm tra KV

Dịch vụ chỉ cần xác minh `shop.sales.orders` đọc KV được. Developer dùng `Collection.exists("__probe__")` và nhận `exists() == false`.

**Hỏi:** Có nên báo DOWN?

**Hướng giải:** Không, nếu lệnh KV hoàn tất bình thường. Key không tồn tại là một response hợp lệ; nếu muốn test dữ liệu sentinel thì đó là hợp đồng riêng.

### Bài D — Đặt SQL++ trong readiness

Một Kubernetes deployment có 100 pod. Mỗi pod cứ 2 giây chạy một SQL++ REQUEST_PLUS phức tạp trong readiness.

**Hỏi:** Vấn đề?

**Hướng giải:** Check quá đắt, có thể đợi index, tăng concurrency và kéo theo timeout/flapping. Dùng lightweight probe; chuyển query-depth validation sang synthetic monitor có giới hạn.

### Bài E — Hai tầng phụ thuộc

KV get thành công nhưng SQL++ `SELECT RAW 1` thất bại.

**Hỏi:** Có thể kết luận Index Service offline không?

**Hướng giải:** Chưa. Cần kiểm tra Query Service, RBAC và network; `SELECT RAW 1` không bắt buộc dùng GSI. Chỉ khi query thật và index state được kiểm tra mới có căn cứ về Index Service.

### Bài F — Actuator chạy port riêng

Kubernetes chỉ probe port management; main app port bị cấu hình sai nhưng management port vẫn UP.

**Hỏi:** Làm sao khắc phục?

**Hướng giải:** Cấu hình health probes trên main serving port hoặc có kiểm tra end-to-end main HTTP path theo khả năng framework/version.

### Bài G — Reactive health

Một developer viết `Mono.just(blockingSdk.get(...))` để tạo reactive health indicator.

**Hỏi:** Có non-blocking không?

**Hướng giải:** Không. Lệnh blocking chạy trước khi Publisher được tạo. Dùng API SDK reactive hoặc cô lập blocking I/O khỏi event loop và giới hạn timeout/concurrency.

### Bài H — Mất secret

Secret Couchbase bị thay sai, pod vẫn liveness UP và readiness DOWN.

**Hỏi:** Xử lý như thế nào?

**Hướng giải:** Kiểm tra auth errors và rollout/secret rotation; không tăng timeout hoặc restart vô hạn. Giữ liveness process và xử lý cấu hình sai như một lỗi deployment.

### Bài I — Cải thiện quan sát

Ứng dụng chỉ log `DB down` khi SQL++ timeout.

**Hỏi:** Cần bổ sung gì?

**Hướng giải:** Operation type, keyspace, query vs KV, error category, timeout, duration, correlation ID, cluster/index metrics và trạng thái health contributor, không log secret.

## 34. Checklist trước khi triển khai production

- [ ] Đã định nghĩa rõ liveness, readiness, startup và deep diagnostics?
- [ ] Liveness có độc lập với Couchbase và những dependency không thuộc process?
- [ ] Readiness policy dựa trên contract của các route thực tế?
- [ ] Đã cân nhắc rủi ro tất cả pod NotReady khi dependency chung outage?
- [ ] Spring Boot Actuator/probes được bật trên phiên bản phù hợp?
- [ ] Health group include đúng contributor đang tồn tại, không giả định tên?
- [ ] Probe hoạt động trên đường port/path mà orchestrator thực sự dùng?
- [ ] Endpoint health chỉ phơi status cần thiết và được bảo vệ phù hợp?
- [ ] Cấu hình Couchbase connection string, TLS, DNS và secret đúng?
- [ ] Bucket/scope/collection và RBAC phù hợp với app path?
- [ ] KV check đọc-only, có timeout và không yêu cầu sentinel tồn tại?
- [ ] Query/index check được tách khỏi liveness và có tần suất phù hợp?
- [ ] `SELECT RAW 1` không bị hiểu nhầm là kiểm tra GSI?
- [ ] Đã kiểm tra secondary index online và `EXPLAIN` cho query trọng yếu?
- [ ] Startup không tạo index hoặc ghi/xóa document trong health handler?
- [ ] Có timeout budget hợp lý với Kubernetes probe timeout?
- [ ] SDK retry/concurrency không tạo load storm khi dependency lỗi?
- [ ] Reactive health không block event loop?
- [ ] Health output/logging không làm lộ credential, token hay PII?
- [ ] Đã có metrics KV latency, Query Service, index backlog và API 5xx?
- [ ] Đã kiểm thử trạng thái dependency down/up trong cluster lab?
- [ ] Health `UP` không bị dùng thay cho integration test CAS/TTL/transaction?
- [ ] Có smoke test sau deploy cho Repository/Template và Query path?
- [ ] Có runbook khi pod ready nhưng API Couchbase vẫn lỗi?
- [ ] Đã đo readiness flapping, startup duration và recovery behavior?

## 35. Câu hỏi tự kiểm tra

**1. Liveness nên báo DOWN khi Couchbase mất kết nối không?** Thường không; dependency outage không nhất thiết làm JVM chết hoặc treo.

**2. Readiness nên include Couchbase ở mọi ứng dụng?** Không. Phải xét mức độ phụ thuộc của traffic, fallback và nguy cơ cascading outage.

**3. Health contributor `couchbase` UP có nghĩa SQL++ query nào cũng thành công?** Không. Chưa chắc nó kiểm tra đúng index, quyền hoặc keyspace.

**4. `Collection.exists(key)` trả false có nghĩa KV unavailable?** Không. Một request thành công với document không tồn tại vẫn là phản hồi KV hợp lệ.

**5. `SELECT RAW 1` chứng minh điều gì?** Query Service có thể thực thi một query tối giản, không chứng minh GSI Orders online.

**6. Vì sao không nên write/delete sentinel ở mọi readiness probe?** Tăng mutation/index load, tạo fixture leaks và nguy cơ race dưới outage.

**7. Readiness và liveness khác nhau về Kubernetes action?** Readiness điều khiển routing endpoint; liveness có thể dẫn tới restart.

**8. SDK initialization thành công có đủ để khẳng định connection hoạt động?** Không. Cần hiểu bootstrap/lazy I/O và thực hiện phép kiểm tra phù hợp.

**9. Tại sao REQUEST_PLUS không phù hợp mặc định cho health query nặng?** Nó có thể chờ GSI bắt kịp mutation, tăng probe latency và flapping.

**10. Mất auth credential xử lý bằng tăng timeout được không?** Không. Cần sửa secret/RBAC/cấu hình.

**11. Reactive health indicator có nên gọi SDK blocking ngay trong `Mono.just`?** Không. Cách đó vẫn thực hiện blocking trước khi tạo Publisher.

**12. Health readiness UP có loại trừ mọi lỗi runtime trong khoảng giữa hai probes?** Không. Availability và phụ thuộc thay đổi liên tục.

## 36. Kết luận

**Kiểm tra kết nối Couchbase và trạng thái sẵn sàng của ứng dụng là hai vấn đề liên quan nhưng không đồng nhất.** Trong Spring Data Couchbase, một instance có thể đã khởi động, còn liveness và cổng HTTP nhưng chưa dùng được KV, Query Service hoặc một index cần thiết. Ngược lại, Couchbase tạm thời outage không phải lý do tự động restart mọi tiến trình Spring Boot.

Hãy dùng **Spring Boot Actuator availability groups** để phản ánh liveness/readiness theo hợp đồng phục vụ; đưa **KV health check read-only, ngắn, có timeout** vào readiness khi thật sự cần, và tách **SQL++/GSI/CRUD smoke test** sang kiểm tra sâu có kiểm soát. Luôn đối chiếu DNS/TLS/RBAC, đúng bucket/scope/collection, phiên bản SDK/Boot và quan sát runtime errors, tail latency, Index Service metrics bên cạnh health status. Với các bất biến nghiệp vụ như CAS, TTL, transaction, durability hay read-after-write, cần test riêng chứ không suy ra từ một kết quả `UP`.

Một health policy tốt giúp orchestrator đưa traffic đến đúng instance **mà không gây quá tải, restart storm hoặc cảm giác an toàn giả**; đó là nền tảng vận hành đáng tin cậy cho ứng dụng **SPRING_DATA_COUCHBASE**.
