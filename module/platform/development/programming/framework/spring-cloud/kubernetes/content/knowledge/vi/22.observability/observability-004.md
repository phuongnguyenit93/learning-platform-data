# Đo thời gian nạp cấu hình và phát hiện thay đổi

Trong chương **Khả năng quan sát** của module **SPRING_CLOUD_KUBERNETES**, đo cấu hình cần trả lời được hai câu hỏi: ứng dụng mất bao lâu để có cấu hình cần thiết khi khởi động, và một thay đổi mất bao lâu để đi từ Kubernetes đến hành vi thực tế của ứng dụng.

Một dòng log “đã phát hiện ConfigMap thay đổi” chưa trả lời được câu hỏi thứ hai. Sau đó vẫn có thể còn bước tìm instance, gửi thông báo, đọc lại nguồn, cập nhật Environment và tạo lại bean. Bài học xây dựng các mốc đo riêng để bạn xác định đúng giai đoạn chậm hoặc bị đứt.

## 1. Mục tiêu và phạm vi ví dụ

Sau bài học, bạn có thể:

- Phân biệt thời gian nạp nguồn cấu hình, thời gian khởi động và độ trễ áp dụng thay đổi.
- Đặt đồng hồ và điểm kết thúc phép đo phù hợp cho từng giai đoạn.
- Dùng Micrometer Timer, log có cấu trúc và revision công khai để liên kết bằng chứng.
- Kiểm chứng cấu hình có hiệu lực trên từng Pod thay vì chỉ quan sát API server hoặc health.
- Phát hiện cập nhật bị bỏ lỡ, lỗi RBAC, lỗi gửi thông báo và tình trạng dữ liệu cũ.
- Chọn mức quan sát phù hợp cho API-based config, mounted file hoặc cấu hình bất biến theo lần triển khai.

Các ví dụ tham chiếu **Spring Boot 3.5.x** và **Spring Cloud Kubernetes 3.3.x** trong một bộ phiên bản tương thích được quản lý qua Spring Cloud BOM. Không coi tên logger, metric tùy biến hoặc tham số minh họa trong bài là mặc định chung cho mọi phiên bản.

Phần lab giả định có ứng dụng JVM tên `orders`, namespace `config-lab`, ConfigMap `orders` và Configuration Watcher đã được triển khai. Ứng dụng có Spring Web, Actuator, Spring Cloud Context và **một** bộ starter Kubernetes config phù hợp với client đã chọn. Watcher và ứng dụng có các quyền và đường kết nối cần thiết. Không cần thêm DiscoveryClient hoặc LoadBalancer vào nghiệp vụ chỉ để đo cấu hình; Watcher dùng discovery theo cơ chế riêng của nó.

## 2. Xác định các mốc trước khi đặt tên metric

### 2.1. Lần nạp đầu tiên

Cần phân biệt:

| Khoảng đo | Bắt đầu | Kết thúc | Có thể bao gồm |
| --- | --- | --- | --- |
| Đọc một nguồn | Ngay trước khi gọi nguồn | Dữ liệu nguồn đã được nhận hoặc thao tác kết thúc lỗi | Mạng, xác thực, API, đọc file |
| Nạp cấu hình logic | Bắt đầu quy trình nạp | Các nguồn cần thiết đã được kết hợp và xử lý | Nhiều lần đọc, parse, retry, hợp nhất |
| Sẵn sàng của ứng dụng | Bắt đầu vòng đời khởi động đã chọn | Ứng dụng phát tín hiệu sẵn sàng | Cấu hình, bean, kết nối, runner và khởi tạo khác |
| Sẵn sàng phục vụ bên ngoài | Bắt đầu triển khai hoặc khởi động đã chọn | Yêu cầu đại diện từ bên ngoài thành công | Image pull, scheduling, startup, probe, định tuyến |

`application.ready.time` không phải thời gian riêng để đọc ConfigMap. Thời gian một HTTP GET đến API server cũng không phải tổng thời gian nạp cấu hình nếu phía trên có retry hoặc nhiều nguồn.

Nếu các nguồn được đọc song song, tổng thời gian quy trình không bằng tổng duration của từng lần đọc. Nếu startup step có quan hệ cha/con, cộng cả step cha lẫn step con sẽ đếm trùng.

### 2.2. Một thay đổi trong thời gian chạy

Đặt các mốc cho một thử nghiệm cập nhật:

~~~mermaid
sequenceDiagram
    participant Test as Bộ kiểm chứng
    participant API as API server
    participant Watcher as Configuration Watcher
    participant App as Ứng dụng
    participant Bean as Bean nghiệp vụ

    Test->>API: t0: gửi cập nhật revision
    API-->>Test: t1: trả kết quả cập nhật thành công
    API-->>Watcher: t2: Watcher quan sát thay đổi
    Watcher->>App: t3: gửi thông báo refresh
    App->>API: đọc lại nguồn nếu dùng API
    App->>App: cập nhật nguồn và Environment
    App->>Bean: t4: tạo/cập nhật trạng thái được sử dụng
    Test->>App: gọi hành vi kiểm chứng
    App-->>Test: t5: trả đúng revision và kết quả mong muốn
~~~

Sơ đồ là một đường đi minh họa. Nếu dùng volume, ứng dụng đọc file đã được kubelet cập nhật. Nếu dùng Bus, có thêm giai đoạn broker và consumer. Một số thao tác có thể chồng lấn, nên các mốc không tạo thành chuỗi tuần tự tuyệt đối trên mọi hệ thống.

Các duration cần ghi rõ định nghĩa:

- **Độ trễ quan sát thay đổi:** từ mốc cập nhật đã chọn đến lúc Watcher quan sát thay đổi.
- **Thời gian thông báo:** từ lúc bắt đầu gửi đến lúc nhận kết quả hoặc timeout.
- **Thời gian đọc lại:** quanh thao tác đọc nguồn thực tế.
- **Thời gian áp dụng:** quanh bước chuyển dữ liệu hợp lệ thành trạng thái nghiệp vụ mới.
- **Độ trễ được kiểm chứng:** từ trước khi gửi cập nhật đến khi bộ kiểm chứng nhận phản hồi đúng.

Chọn `t0` ngay trước khi gửi yêu cầu cập nhật sẽ bao gồm cả thời gian ghi qua API. Đừng gọi giá trị đó là “thời gian truyền watch thuần túy”.

`t1` chỉ là thời điểm client nhận phản hồi, không phải timestamp chính xác của lúc dữ liệu được lưu. Watcher có thể nhận sự kiện trước khi phản hồi cập nhật về đến client; vì thế hiệu `t2 - t1` không luôn là một khoảng dương ngay cả khi đồng hồ đã đồng bộ.

## 3. Cơ chế cấp cấu hình quyết định đường đi cần đo

| Cơ chế | Khi nạp ban đầu | Khi thay đổi | Điểm dễ đo sai |
| --- | --- | --- | --- |
| Kubernetes PropertySource qua API | Ứng dụng đọc ConfigMap/Secret trong quá trình nạp cấu hình | Cần cơ chế đọc lại và refresh phù hợp | Chỉ đo một request rồi bỏ qua retry và hợp nhất |
| ConfigMap/Secret mount thành file | Ứng dụng đọc file trong volume | Kubelet cập nhật volume, ứng dụng cần đọc và áp dụng lại | Thấy API đã đổi rồi mặc định file trong Pod cũng đã đổi |
| Biến môi trường | Giá trị được cấp cho tiến trình lúc container khởi động | Tiến trình hiện tại không tự nhận giá trị mới | Chờ Watcher làm biến môi trường đổi trực tiếp |
| Cấu hình theo image hoặc tài nguyên bất biến | Nạp trong lần triển khai mới | Thay đổi được áp dụng qua rollout | Đo refresh mặc dù thiết kế không có refresh |

Theo [tài liệu ConfigMap của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/), cập nhật volume có tính eventual; biến môi trường không tự cập nhật và mount bằng `subPath` không nhận cập nhật ConfigMap. Vì thế phải xác định rõ ứng dụng đang đọc qua API, file hay môi trường trước khi đặt SLO.

Với Kubernetes PropertySource, `spring.config.import: "kubernetes:"` là một cách nạp cấu hình. Không đồng thời bật cả Config Data import và cơ chế bootstrap cũ cho cùng mục đích; xem [Kubernetes PropertySource implementations 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

Tính năng `PropertySource Reload` cũ đã được đánh dấu deprecated; tài liệu hướng đến Configuration Watcher như phương án thay thế. Không trộn các tham số polling của cơ chế cũ vào Watcher rồi suy ra chu kỳ phát hiện của Watcher. Xem [PropertySource Reload](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/propertysource-reload.html).

## 4. Đồng hồ, timestamp và sai số

Dùng hai loại thời gian cho hai mục đích:

| Loại thời gian | Công dụng | Giới hạn |
| --- | --- | --- |
| Đồng hồ đơn điệu, ví dụ `System.nanoTime()` | Duration trong cùng tiến trình | Không so sánh giá trị tuyệt đối giữa hai JVM hoặc hai lần khởi động |
| Timestamp UTC, ví dụ `Instant.now()` | Ghép log giữa Watcher, Pod và bộ kiểm chứng | Chịu sai lệch đồng hồ giữa các máy |
| Thời gian một bộ kiểm chứng đo xuyên suốt | Độ trễ quan sát từ cập nhật đến hành vi mới | Bao gồm thời gian gọi API, polling và HTTP kiểm chứng |

Micrometer `Timer.Sample` dùng đồng hồ của registry để lưu mốc bắt đầu; duration là đơn vị đo thích hợp cho Timer. Tham khảo [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

Để so sánh log nhiều thành phần, cần đồng bộ thời gian và biết sai số chấp nhận được. Một khoảng đo âm là tín hiệu cần xem lại mốc, thứ tự sự kiện hoặc đồng hồ; không sửa thành số 0 rồi đưa vào báo cáo.

Nếu bộ kiểm chứng hỏi ứng dụng mỗi 500 ms, thời điểm nhận phản hồi đúng đầu tiên là một mốc quan sát có thêm trễ polling và HTTP. Không thể báo kết quả đó chính xác đến microsecond chỉ vì đồng hồ hỗ trợ nanosecond.

Không dùng `metadata.creationTimestamp` của ConfigMap làm thời điểm cập nhật: trường đó mô tả lúc đối tượng được tạo, không phải lúc nội dung vừa thay đổi.

## 5. Đo nạp ban đầu khi Actuator chưa tồn tại

Spring Boot cung cấp `application.started.time` và `application.ready.time`. Chúng giúp so sánh khởi động giữa các Pod nhưng không tách riêng chi phí của ConfigMap hoặc Secret. Xem [Application Startup Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html#actuator.metrics.supported.application-startup).

Có thể bật thu thập startup steps để điều tra thêm:

~~~java
package example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(OrdersApplication.class);
        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));
        application.run(args);
    }
}
~~~

Khi endpoint `startup` được expose, dữ liệu buffer hỗ trợ xem các bước đã được instrument. Nó không bảo đảm mọi client Kubernetes hoặc mọi lần đọc nguồn đều có step riêng. Endpoint cũng chỉ có ích sau khi ứng dụng đã phục vụ được HTTP. Tham khảo [Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

Để đo riêng thao tác nạp nguồn ở giai đoạn sớm:

1. Đặt mốc ở điểm gọi nguồn hoặc adapter thực sự tham gia quy trình nạp.
2. Ghi duration và kết quả, gồm cả lần lỗi hoặc retry.
3. Nếu registry chưa có, giữ bản ghi nhỏ có giới hạn trong bộ nhớ hoặc phát log sớm.
4. Khi registry sẵn sàng, xuất bản bản ghi đã giữ đúng một lần.
5. Nếu startup thất bại, thu bằng log hoặc telemetry ngoài tiến trình; không chờ scrape Actuator của Pod chưa khởi động xong.

Một `@Component` bình thường thường được tạo sau giai đoạn Config Data. Bọc mã trong component đó không tự đo được các lần nạp đã xảy ra trước nó. Muốn instrument loader hoặc client phải dùng đúng điểm mở rộng của phiên bản và client đã chọn; không thêm một lần GET thừa chỉ để có một con số mang tên “config load”.

Ngoài ra, registry có thể được tạo nhưng metrics exporter chưa kịp gửi trước khi tiến trình chết. Vì vậy log lỗi khởi động vẫn cần thiết, ngay cả khi đã có Timer.

## 6. Thiết kế metric và log có phạm vi rõ ràng

Các tên `sck.config.*` dưới đây là **đề xuất tùy biến của bài học**, không phải metric được Spring Cloud Kubernetes tự tạo sẵn:

| Tên Micrometer đề xuất | Loại | Ý nghĩa |
| --- | --- | --- |
| `sck.config.stage` | Timer | Duration một giai đoạn có điểm bắt đầu và kết thúc rõ |
| `sck.config.change.latency` | Timer | Độ trễ từ cập nhật đến hành vi mới được kiểm chứng thành công |
| `sck.config.change.verifications` | Counter | Kết quả kiểm chứng: success, timeout hoặc failure |
| `sck.config.watch.reconnects` | Counter | Số lần kết nối watch phải được thiết lập lại theo định nghĩa đã chọn |
| `sck.config.revision.matches` | Gauge | Instance có khớp revision mong muốn đã biết hay không |
| `sck.config.last.reconcile.success.timestamp` | Gauge | UTC epoch seconds của lần đối soát thành công gần nhất |

Đừng dùng “thời gian từ lần thay đổi cuối” để kết luận dữ liệu cũ. Một ConfigMap đúng có thể không thay đổi suốt nhiều tháng. Cần phân biệt tuổi của **nội dung cấu hình**, tuổi của **bằng chứng đối soát** và tình trạng **khớp revision mong muốn**.

Tương tự, một watch khỏe không bắt buộc liên tục có sự kiện nghiệp vụ. Không có sự kiện mới chưa đủ chứng minh watch đã đứt; một gauge đối soát chỉ có ý nghĩa khi thực sự có tác vụ đối soát cập nhật nó.

Tag nên có tập giá trị hữu hạn, chẳng hạn:

~~~text
phase  = initial | runtime
stage  = source_read | notify | apply
result = success | failure
~~~

Không gắn revision, `resourceVersion`, timestamp, request ID, nội dung cấu hình hoặc thông báo exception làm tag metric. Chúng phù hợp hơn trong log hoặc trace có chính sách lưu trữ. Metadata Pod thường đã được hệ thống scrape gắn vào target; không cần lặp lại mọi giá trị đó trong từng meter.

Bản ghi log tùy biến minh họa:

~~~json
{
  "event": "config_revision_verified",
  "timestamp": "2026-11-24T04:20:15.320Z",
  "application": "orders",
  "namespace": "config-lab",
  "pod": "orders-example",
  "source": "configmap/orders",
  "revision": "r002",
  "duration_ms": 15320,
  "result": "success"
}
~~~

Log này không mặc nhiên được framework phát ra. Nó chỉ được ghi khi logic kiểm chứng xác nhận revision. Với Secret, không log giá trị, không đưa giá trị vào trace và không công khai hash của dữ liệu có thể bị đoán. Dùng mã phiên bản triển khai được cấp riêng nếu cần đối chiếu thay đổi Secret.

## 7. Ví dụ Timer cho một giai đoạn đồng bộ

Lớp dưới đây dùng cho mã mà bạn thực sự kiểm soát, chẳng hạn adapter đọc nguồn hoặc bước áp dụng snapshot của ứng dụng. Nó không tự móc vào Config Data loader hay Configuration Watcher.

~~~java
package example.orders.observability;

import java.time.Duration;
import java.util.concurrent.Callable;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class ConfigStageTiming {

    public enum Phase {
        INITIAL("initial"), RUNTIME("runtime");

        private final String tag;

        Phase(String tag) {
            this.tag = tag;
        }
    }

    public enum Stage {
        SOURCE_READ("source_read"),
        NOTIFY("notify"),
        APPLY("apply");

        private final String tag;

        Stage(String tag) {
            this.tag = tag;
        }
    }

    private final MeterRegistry registry;

    public ConfigStageTiming(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T measure(
            Phase phase, Stage stage, Callable<T> operation)
            throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String result = "failure";

        try {
            T value = operation.call();
            result = "success";
            return value;
        }
        finally {
            Timer timer = Timer.builder("sck.config.stage")
                    .description("Duration of a configuration stage")
                    .tags("phase", phase.tag,
                          "stage", stage.tag,
                          "result", result)
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(
                            Duration.ofMillis(100),
                            Duration.ofSeconds(1),
                            Duration.ofSeconds(5),
                            Duration.ofSeconds(30))
                    .register(registry);
            sample.stop(timer);
        }
    }
}
~~~

Ý nghĩa của `success` phụ thuộc hợp đồng `operation`: một thao tác trả về bình thường nhưng chỉ trả dữ liệu cũ không tự chứng minh revision mong muốn đã được áp dụng. Với `stage=apply`, chỉ cho thao tác thành công sau khi đã validate và công bố trạng thái nghiệp vụ theo đúng thiết kế.

Nếu operation trả về `CompletableFuture` hoặc một publisher, đoạn mã trên chỉ đo đến lúc trả đối tượng bất đồng bộ. Cần kết thúc sample ở callback hoặc tín hiệu hoàn tất tương ứng mới đo được toàn bộ tác vụ.

Timer có cả count và tổng duration. Không bắt buộc thêm một Counter đếm lại cùng tập thao tác nếu count của Timer đã đáp ứng nhu cầu. Mặt khác, Timer chưa dừng không giúp phát hiện thao tác treo; cần timeout của operation và có thể thêm phép đo số tác vụ đang chờ.

Vì lớp này là component được inject registry, nó phù hợp sau khi context đã tạo được bean. Trường hợp nạp ban đầu trước registry vẫn cần cách thu thập sớm ở phần trước.

## 8. Không đánh đồng phát hiện, refresh và cấu hình có hiệu lực

Có ít nhất ba sự kiện cần phân biệt:

1. **Nguồn được quan sát:** Watcher biết tài nguyên đã đổi.
2. **Refresh được xử lý:** ứng dụng đã thực hiện quy trình cập nhật môi trường và scope tương ứng.
3. **Hành vi được kiểm chứng:** đoạn mã nghiệp vụ sử dụng đúng cấu hình mới.

Một `EnvironmentChangeEvent` là bằng chứng về thay đổi môi trường tại một mốc, không phải lời xác nhận rằng mọi consumer đã dùng dữ liệu mới. Không đo duration bằng cách lấy một timestamp toàn cục lúc thấy sự kiện rồi ghép với bất kỳ lần refresh tiếp theo; các lần cập nhật đồng thời hoặc trùng lặp có thể bị ghép sai.

Bean trong `@RefreshScope` được truy cập qua proxy và có thể chỉ khởi tạo lại khi phương thức được gọi sau khi scope bị làm mới. Vì vậy HTTP 200 từ `/actuator/refresh` không đủ chứng minh mọi bean đã tạo lại thành công. Cơ chế này được mô tả trong [Spring Cloud Context: Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html).

Cách kiểm chứng mạnh hơn là đưa một revision công khai vào cùng cấu hình đang dùng, rồi xác nhận **cả revision và giá trị/hành vi mong muốn** ở đường đi thực tế. Đọc riêng revision từ `Environment` trong khi nghiệp vụ dùng một snapshot cũ sẽ tạo bằng chứng sai.

Không dùng `resourceVersion` làm số phiên bản nghiệp vụ: không chuyển nó sang số rồi trừ, không coi chênh lệch là số cập nhật hoặc số mili giây. Giữ nguyên chuỗi nếu cần liên kết log theo quy tắc API. Để theo dõi một đợt cấu hình, dùng revision do quy trình phát hành quản lý. Xem [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/).

## 9. Chuẩn bị một ConfigMap có thể kiểm chứng

Ví dụ chỉ chứa dữ liệu không nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders
  namespace: config-lab
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  demo.config-revision: "r001"
  demo.banner: "Xin chao r001"
~~~

Ứng dụng chọn nguồn bằng tên và namespace rõ ràng. Cách khai báo key riêng lẻ trong ConfigMap được hỗ trợ như mô tả ở [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Phần cấu hình ứng dụng tham chiếu:

~~~yaml
spring:
  application:
    name: orders
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        name: orders
        namespace: config-lab

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,startup,refresh"
  metrics:
    tags:
      application: orders
~~~

Ứng dụng cần registry Prometheus trên classpath nếu muốn xuất `/actuator/prometheus`; khai báo exposure không tự tạo registry. Endpoint `startup` cần `BufferingApplicationStartup` đã trình bày. Endpoint `refresh` cần phần hỗ trợ Spring Cloud tương ứng.

Đây là exposure cho môi trường lab có kiểm soát. Hạn chế đường gọi `refresh` cho Watcher và người vận hành được phép; việc expose endpoint không tự cấu hình xong xác thực hoặc NetworkPolicy. Không cần mở `env` hay `configprops` ra công khai để đo thời gian.

Cấu hình ví dụ dành cho JVM; không mặc định cơ chế refresh tương tự hoạt động với AOT hoặc native image. Nếu dự án chọn rollout thay cho refresh, đo thời gian rollout đến hành vi mới và đặt tên phép đo đúng với lựa chọn đó.

### Một điều kiện của Configuration Watcher

Với Watcher 3.3, label `spring.cloud.kubernetes.config: "true"` cho phép thay đổi ConfigMap kích hoạt thông báo; đường HTTP mặc định gửi đến `/actuator/refresh` của các instance được tìm qua discovery. Cần kiểm tra đúng ứng dụng đích và quyền truy cập. Xem [Configuration Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Nếu dùng mounted volume, Watcher có tham số chờ trước thông báo:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
    value: "10000"
~~~

Đây là ví dụ chờ 10.000 ms trong Watcher, không phải lời hứa rằng thay đổi sẽ có hiệu lực trong 10 giây. Khoảng chờ đó cũng không làm kubelet cập nhật file nhanh hơn. Hãy đo thực tế file đã chứa revision nào khi refresh diễn ra.

Không sao chép cấu hình Watcher rồi giả định label đã đủ: namespace, discovery, cổng quản trị, đường HTTP, quyền của Watcher và quyền đọc nguồn của ứng dụng đều là các điều kiện độc lập.

## 10. Một đường HTTP sử dụng đúng snapshot cấu hình

Hai lớp Java sau minh họa một chức năng banner. Chúng được đặt trong package con của ứng dụng để component scan tìm thấy. Đây là mã ví dụ trong bài học; bạn tích hợp vào ứng dụng lab phù hợp.

Lớp cấu hình có một snapshot bất biến:

~~~java
package example.orders.banner;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class BannerSettings {

    public record Snapshot(String revision, String message) {
    }

    private final Snapshot snapshot;

    public BannerSettings(
            @Value("${demo.config-revision}") String revision,
            @Value("${demo.banner}") String message) {

        if (revision.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException(
                    "Banner configuration must not be blank");
        }
        this.snapshot = new Snapshot(revision, message);
    }

    public Snapshot current() {
        return snapshot;
    }
}
~~~

Controller đọc snapshot đúng một lần cho mỗi phản hồi:

~~~java
package example.orders.banner;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BannerController {

    private final BannerSettings settings;
    private final String podName;

    public BannerController(
            BannerSettings settings,
            @Value("${POD_NAME:unknown}") String podName) {
        this.settings = settings;
        this.podName = podName;
    }

    @GetMapping("/banner")
    public Map<String, String> banner() {
        BannerSettings.Snapshot snapshot = settings.current();
        return Map.of(
                "pod", podName,
                "revision", snapshot.revision(),
                "message", snapshot.message());
    }
}
~~~

Trong container, có thể cấp tên Pod qua Downward API:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

Phản hồi ban đầu minh họa:

~~~json
{
  "pod": "orders-example",
  "revision": "r001",
  "message": "Xin chao r001"
}
~~~

Ở đây, revision và banner nằm trong cùng snapshot được chức năng sử dụng. Điều đó tốt hơn một endpoint chỉ báo “đã nhận yêu cầu refresh”.

Ví dụ kiểm tra giá trị rỗng khi tạo bean nhưng không xây dựng cơ chế giữ cấu hình tốt gần nhất khi refresh thất bại. Trong hệ thống thật, cần validate đầy đủ trước khi công bố snapshot mới và xác định cách phục hồi. Không mặc định `@RefreshScope` tự cung cấp giao dịch nguyên tử cho toàn bộ ứng dụng hoặc tự rollback mọi tài nguyên phụ thuộc.

## 11. Thực hành đo từ cập nhật đến phản hồi mới

### Bước 1: Xác nhận cấu hình và quan sát ban đầu

Kiểm tra tên ConfigMap, namespace, label, nguồn ứng dụng đang nạp và cấu hình Watcher. Quyền cần kiểm tra gồm đọc nguồn của ứng dụng và các thao tác `get/list/watch` tương ứng của Watcher. Không thêm quyền đọc Secret nếu bài lab chỉ dùng ConfigMap.

Bảo đảm chức năng `/banner` đang trả đúng `r001`. Kiểm tra này cũng khởi tạo bean lazy ban đầu, giúp các lần đo tiếp theo có baseline rõ ràng.

Nếu đặt một giá trị trùng tên trong biến môi trường hoặc nguồn có độ ưu tiên cao hơn, thay đổi ConfigMap có thể không làm giá trị hiệu lực đổi. Đó là vấn đề thứ tự nguồn, không nhất thiết là Watcher chậm.

### Bước 2: Cố định Pod được quan sát

Trong terminal dùng Bash, chọn một Pod theo label của Deployment lab:

~~~bash
kubectl -n config-lab get pods -l app=orders

pod="$(kubectl -n config-lab get pods -l app=orders \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl -n config-lab port-forward "pod/$pod" 18080:8080
~~~

Giữ terminal port-forward hoạt động. Trong terminal khác:

~~~bash
curl --silent --show-error http://127.0.0.1:18080/banner
~~~

Kiểm tra trường `pod` trong phản hồi. Dùng một Pod cố định giúp tránh trường hợp Service luân phiên trả về Pod đã cập nhật và Pod chưa cập nhật. Nếu Pod được chọn chưa sẵn sàng hoặc đổi trong lúc thử, xử lý riêng; không tự thay Pod rồi gộp thành cùng một phép đo.

### Bước 3: Cập nhật và đo bằng một đồng hồ đơn điệu

Đoạn sau chạy trong **PowerShell 7+** trên máy có `kubectl`. Nó dùng `ProcessStartInfo.ArgumentList` để truyền JSON thành một đối số nguyên vẹn, tránh phụ thuộc cách shell xử lý dấu nháy của JSON.

Điều kiện trước khi chạy: phản hồi hiện tại là `r001`, và không có tác nhân khác cùng sửa ConfigMap trong lượt thử. Đoạn mã chỉ thay hai key dữ liệu của ConfigMap lab; nó không triển khai ứng dụng hoặc Watcher.

~~~powershell
$expectedRevision = 'r002'
$expectedMessage = 'Xin chao r002'

$patchJson = @{
    data = @{
        'demo.config-revision' = $expectedRevision
        'demo.banner' = $expectedMessage
    }
} | ConvertTo-Json -Compress

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = 'kubectl'
$startInfo.UseShellExecute = $false

$nativeArguments = @(
    '-n', 'config-lab',
    'patch', 'configmap', 'orders',
    '--type=merge',
    '--patch', $patchJson
)

foreach ($nativeArgument in $nativeArguments) {
    $startInfo.ArgumentList.Add($nativeArgument)
}

$clock = [System.Diagnostics.Stopwatch]::StartNew()
$patchProcess = [System.Diagnostics.Process]::Start($startInfo)

if (-not $patchProcess.WaitForExit(10000)) {
    $patchProcess.Kill()
    throw 'Cap nhat ConfigMap vuot thoi gian cho'
}

if ($patchProcess.ExitCode -ne 0) {
    throw 'Cap nhat ConfigMap that bai; khong ghi nhan la lan do thanh cong'
}

$ackMilliseconds = $clock.ElapsedMilliseconds
$verified = $false

while ($clock.Elapsed.TotalSeconds -lt 60) {
    try {
        $state = Invoke-RestMethod `
            -Uri 'http://127.0.0.1:18080/banner' `
            -TimeoutSec 2

        if ($state.revision -eq $expectedRevision -and
            $state.message -eq $expectedMessage) {
            $verified = $true
            break
        }
    }
    catch {
        # Loi HTTP/tam thoi khong duoc xem la da ap dung thanh cong.
    }

    Start-Sleep -Milliseconds 500
}

$clock.Stop()

[pscustomobject]@{
    Revision = $expectedRevision
    Pod = if ($verified) { $state.pod } else { $null }
    Result = if ($verified) { 'success' } else { 'timeout' }
    UpdateAckMilliseconds = $ackMilliseconds
    ObservedMilliseconds = $clock.ElapsedMilliseconds
}

if (-not $verified) {
    throw 'Chua kiem chung duoc revision mong muon trong ngan sach cho'
}
~~~

`ObservedMilliseconds` tính từ trước khi chạy lệnh cập nhật đến khi nhận phản hồi đúng. Nó bao gồm chi phí khởi chạy `kubectl`, gọi API, phát hiện, thông báo, refresh, polling và HTTP kiểm chứng. Không đặt tên nó là thời gian đọc ConfigMap hoặc thời gian watch thuần túy.

Ngân sách vòng lặp là khoảng 60 giây; request đang chạy và khoảng nghỉ có thể làm thời gian kết thúc nhỉnh hơn mốc đó. Trong công cụ đo sản xuất, dùng deadline xuyên suốt, giới hạn riêng từng thao tác và ghi loại lỗi để phân biệt update failure, transport failure và verification timeout.

Đoạn mã là bộ kiểm chứng bên ngoài; nó không tự đăng ký các metric `sck.config.*` trong ứng dụng. Muốn có metric của phép thử, cần xuất kết quả qua cơ chế telemetry của bộ kiểm chứng.

Đừng gọi `/actuator/refresh` thủ công trong lượt thử Watcher: làm vậy có thể che khuất lỗi Watcher. Nếu cần kiểm tra refresh riêng, thực hiện lượt thử khác và đặt tên khác.

### Bước 4: Lặp lại có kiểm soát

Mỗi lượt dùng revision mới, chẳng hạn `r003` rồi `r004`, và cập nhật giá trị banner tương ứng. Không đo lại `r002` khi ứng dụng đã có `r002`, vì phản hồi đúng có thể xuất hiện mà chẳng có thay đổi mới nào cần truyền.

Chờ lượt trước hoàn tất hoặc hết hạn trước khi gửi lượt tiếp theo nếu đang đánh giá từng lần cập nhật. Giữ cùng số replica, cấu hình retry, tài nguyên CPU và cách cấp nguồn khi so sánh hai nhóm kết quả.

Ghi cả các lượt timeout. Một bảng chỉ chứa duration của lượt thành công có thể trông rất tốt trong khi phần lớn cập nhật bị bỏ lỡ.

### Bước 5: Kiểm tra toàn bộ replica

Đo cho một Pod chỉ chứng minh instance đó đã dùng cấu hình mới. Với nhiều replica, xác định tập Pod mục tiêu và kiểm tra từng instance bằng đường quan sát riêng.

Có thể báo cáo:

~~~text
T_first = thời gian đến Pod mục tiêu đầu tiên trả đúng
T_all   = thời gian đến mọi Pod mục tiêu đều trả đúng
Coverage = số Pod mục tiêu trả đúng / tổng Pod mục tiêu
~~~

Nếu một Pod không cập nhật trước deadline, ghi `T_all` chưa đạt hoặc timeout, không lấy giá trị của những Pod thành công làm `T_all`. Khi rollout hoặc autoscaling thay đổi tập Pod, phải có chính sách cập nhật mẫu số; không âm thầm bỏ Pod chậm để đủ 100%.

## 12. Đọc metric bằng Prometheus

Giả sử ứng dụng đã thực sự instrument `sck.config.stage` bằng lớp Timer ở phần trước, đồng thời exporter đang phát **classic histogram** với các series `sck_config_stage_seconds_bucket`, `_sum` và `_count`. Xác nhận tên thực tế trên `/actuator/prometheus` trước khi dùng truy vấn.

Thời gian trung bình đọc nguồn thành công trong 5 phút, theo ứng dụng:

~~~promql
sum by (application) (
  rate(sck_config_stage_seconds_sum{
    phase="runtime", stage="source_read", result="success"
  }[5m])
)
/
sum by (application) (
  rate(sck_config_stage_seconds_count{
    phase="runtime", stage="source_read", result="success"
  }[5m])
)
~~~

P95 của cùng tập thao tác:

~~~promql
histogram_quantile(
  0.95,
  sum by (application, le) (
    rate(sck_config_stage_seconds_bucket{
      phase="runtime", stage="source_read", result="success"
    }[5m])
  )
)
~~~

Tỷ lệ thao tác đọc nguồn kết thúc lỗi:

~~~promql
sum by (application) (
  rate(sck_config_stage_seconds_count{
    phase="runtime", stage="source_read", result="failure"
  }[5m])
)
/
sum by (application) (
  rate(sck_config_stage_seconds_count{
    phase="runtime", stage="source_read"
  }[5m])
)
~~~

Các truy vấn cho kết quả có ý nghĩa khi có mẫu trong cửa sổ. Không có lần đọc mới thì mẫu số có thể bằng 0; “không có mẫu” không đồng nghĩa thời gian bằng 0 hoặc hệ thống chắc chắn khỏe.

Không lấy trung bình các P95 riêng của từng Pod để tạo P95 toàn ứng dụng. Với classic histogram, gộp bucket rồi tính quantile và giữ label `le`. Histogram cho phép cách tổng hợp này; percentile tính sẵn ở client không có cùng tính chất. Xem [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html) và [Prometheus histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile).

Cập nhật cấu hình thường thưa. Một cửa sổ 5 phút có thể không đủ mẫu cho P95 đáng tin cậy; chọn cửa sổ theo tần suất và luôn hiển thị số mẫu. Với nạp đầu tiên, mỗi tiến trình thường chỉ có ít mẫu; không áp dụng máy móc truy vấn rate ngắn hạn rồi kết luận về toàn bộ startup.

## 13. Phân tích một timeline thực tế

Giả sử một lượt thử có timeline minh họa sau, tính tương đối từ `t0`:

| Mốc | Thời gian | Bằng chứng |
| --- | --- | --- |
| Gửi cập nhật | 0 ms | Bộ kiểm chứng bắt đầu đồng hồ |
| Nhận kết quả cập nhật | 120 ms | Lệnh cập nhật kết thúc thành công |
| Watcher quan sát thay đổi | Khoảng 180 ms | Log có revision hoặc liên kết nguồn phù hợp |
| Bắt đầu thông báo | Khoảng 10.200 ms | Log gửi đến instance đích |
| Refresh trả thành công | Khoảng 10.650 ms | Kết quả HTTP của thông báo |
| HTTP nghiệp vụ trả đúng snapshot | 10.900 ms | Bộ kiểm chứng xác nhận revision và banner |

Các mốc xuyên tiến trình cần xem xét sai số đồng hồ. Tuy vậy, khoảng chờ lớn giữa quan sát và gửi thông báo gợi ý kiểm tra refresh delay hoặc hàng đợi trước khi tối ưu thao tác đọc nguồn.

Nếu Watcher dùng volume và cố ý chờ 10 giây, thời gian đọc file 5 ms không làm độ trễ toàn tuyến giảm từ 11 giây xuống 1 giây. Ngược lại, giảm khoảng chờ mà file chưa cập nhật có thể làm refresh đọc lại dữ liệu cũ.

Nếu chỉ một Pod chậm, xem CPU throttling, hàng đợi request, đường management và bước khởi tạo bean của Pod đó. Nếu mọi Pod đều chậm ở cùng mốc, xem phụ thuộc chung như API server, Watcher hoặc broker.

Những con số trên là dữ liệu minh họa để đọc timeline, không phải benchmark hay cam kết hiệu năng của Spring Cloud Kubernetes.

## 14. Các trường hợp lỗi cần đưa vào quan sát

| Hiện tượng | Phép đo hoặc bằng chứng cần xem |
| --- | --- |
| Nạp ban đầu chậm | Duration cả quy trình, từng lần đọc, retry/backoff, số nguồn và thời gian startup |
| Watcher không thấy thay đổi | Namespace, label, quyền watch/list, kết nối và log nhận sự kiện |
| Watcher thấy thay đổi nhưng không tìm được đích | Discovery, tên ứng dụng đích, Service và tập instance |
| Gửi refresh bị 401/403/404 hoặc timeout | Kết quả thông báo, đường actuator, cổng và chính sách truy cập |
| Refresh trả 200 nhưng banner không đổi | Revision hiệu lực, ưu tiên nguồn, file trong Pod và bean thực tế đang dùng |
| Bean tạo lại lỗi | Kết quả apply, lỗi validate và phản hồi chức năng; không chỉ mã HTTP của refresh |
| Một số replica dùng dữ liệu cũ | Coverage và kết quả riêng từng Pod |
| Watch reconnect nhiều | Tần suất reconnect, thời gian đối soát và khả năng bắt kịp trạng thái mới nhất |
| Có nhiều sự kiện cho một lần sửa | Phạm vi đếm event, reconnect/relist, cập nhật metadata và chống xử lý trùng |

Số event nhận được không nhất thiết bằng số lần thay đổi nghiệp vụ duy nhất. Khi ghi counter, phân biệt “event được quan sát”, “refresh attempt”, “revision được kiểm chứng” và “đợt phát hành”. Một revision có thể được refresh nhiều lần; nhiều lần sửa nhanh cũng có thể chỉ dẫn đến việc ứng dụng sử dụng trạng thái cuối.

Với cập nhật liên tiếp `r002` rồi `r003`, ứng dụng đạt trạng thái `r003` không chứng minh nó từng phục vụ `r002`. Nếu hợp đồng chỉ yêu cầu hội tụ về cấu hình mới nhất, không nên coi bỏ qua trạng thái trung gian là lỗi. Nếu cần xử lý từng sự kiện, phải thiết kế một luồng sự kiện phù hợp thay vì coi ConfigMap là hàng đợi.

Lỗi API server hoặc RBAC khi reload cũng không tự chứng minh tiến trình ứng dụng cần restart. Liên kết cảnh báo với revision không khớp, thời hạn dùng cấu hình cũ và tác động nghiệp vụ; không đưa mọi cảnh báo quan sát vào liveness.

## 15. Đặt mục tiêu vận hành từ số đo

Một mục tiêu minh họa có thể là: “Trong điều kiện lab xác định, 99% lượt thay đổi hợp lệ được kiểm chứng trên toàn bộ tập Pod mục tiêu trong 30 giây; lượt quá deadline được tính là không đạt.”

Để mục tiêu đó dùng được, cần ghi rõ:

- Mốc bắt đầu là trước khi gửi cập nhật hay sau khi nhận phản hồi API.
- Phạm vi là một Pod, một ứng dụng hay toàn bộ replica mục tiêu.
- Thế nào là một cập nhật hợp lệ, và cập nhật thất bại qua API được tính riêng ra sao.
- Cách xử lý timeout, Pod restart, thay đổi replica và nhiều revision chồng lấn.
- Cửa sổ đánh giá, số mẫu và độ trễ do công cụ kiểm chứng.

Đừng suy ra một SLO chỉ từ P95 duration của các lượt thành công. Luôn xem tỷ lệ thành công và số lượt chưa xác nhận cùng với phân bố thời gian.

Với DiscoveryClient và Spring Cloud LoadBalancer, các số đo này giúp xác định giai đoạn tìm instance và gửi thông báo nếu chúng nằm trong đường đi thực tế; chúng không thay thế phép đo làm mới danh sách dịch vụ. Với ConfigMap và Secret, cần theo đúng phương thức cấp cấu hình. Với Configuration Watcher, cần nối được sự kiện quan sát đến từng instance sử dụng cấu hình.

Phép đo đáng tin cậy kết thúc ở bằng chứng mà bạn thực sự cần: nguồn đã đọc xong, một giai đoạn đã hoàn tất, hay chức năng đã dùng revision mới. Đặt đúng tên cho mỗi khoảng thời gian sẽ giúp người vận hành chọn đúng bước xử lý khi cấu hình nạp chậm hoặc thay đổi chưa đến được ứng dụng.
