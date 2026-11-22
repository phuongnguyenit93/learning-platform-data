# Startup probe, readiness probe và liveness probe sau restore

Kubernetes dùng ba loại probe để theo dõi vòng đời container: **startup probe**, **readiness probe** và **liveness probe**. Mỗi probe trả lời một câu hỏi khác nhau: ứng dụng đã khởi động xong chưa, có thể nhận traffic chưa và tiến trình còn hoạt động đúng không.

Khi Java application sử dụng CRaC (Coordinated Restore at Checkpoint), những câu hỏi này cần được áp dụng lại sau khi process được restore. Một JVM có thể phục hồi nhanh từ checkpoint nhưng vẫn đang kết nối lại database, tải secret, mở HTTP client, xác thực lease hoặc khởi tạo background worker. Nếu Kubernetes đưa Pod vào Service quá sớm, request có thể đến khi dependency chưa sẵn sàng. Nếu liveness probe đánh giá một dependency bên ngoài bị lỗi là lỗi sống của process, kubelet có thể liên tục restart container và làm tình hình tệ hơn.

Thiết kế phù hợp là dùng startup probe để cho phép giai đoạn khởi động/restore hoàn tất trong một khoảng thời gian có giới hạn, readiness probe để quyết định Pod có nhận traffic hay không, và liveness probe để phát hiện process thực sự không thể tiếp tục hoạt động. Ứng dụng phải cập nhật trạng thái health theo lifecycle CRaC; Kubernetes chỉ quan sát kết quả probe và thực hiện hành động tương ứng.

## 1. Ba probe trả lời ba câu hỏi khác nhau

| Probe | Câu hỏi | Khi thất bại | Mục đích |
|---|---|---|---|
| Startup | Ứng dụng đã hoàn tất khởi động hoặc restore chưa? | Kubelet restart container sau khi đạt failure threshold | Bảo vệ ứng dụng có startup/restore chậm |
| Readiness | Container có thể nhận request mới ngay lúc này không? | Pod không được xem là Ready và bị loại khỏi Service endpoints phù hợp | Điều khiển traffic |
| Liveness | Process còn ở trạng thái có thể tiếp tục phục vụ hoặc tự phục hồi không? | Kubelet restart container sau khi đạt failure threshold | Phát hiện deadlock hoặc trạng thái process không thể phục hồi |

Không dùng ba probe thay thế cho nhau:

- Startup probe chỉ kiểm soát giai đoạn khởi động ban đầu. Sau khi startup probe thành công, kubelet bắt đầu áp dụng readiness và liveness probe.
- Readiness probe có thể thất bại tạm thời nhiều lần mà không restart container. Đây là hành vi mong muốn khi ứng dụng đang chờ database hoặc service bên ngoài.
- Liveness probe thất bại có thể khiến kubelet restart container. Vì vậy, chỉ dùng nó cho lỗi nội bộ nghiêm trọng mà restart có khả năng khắc phục.

Kubernetes đánh giá probe dựa trên kết quả HTTP, TCP, exec hoặc gRPC tùy cấu hình. Với HTTP probe, status code trong khoảng 200–399 được xem là thành công; các kết quả khác, lỗi kết nối hoặc timeout được tính là thất bại.

## 2. Vì sao cần điều chỉnh probe sau CRaC restore?

Checkpoint lưu trạng thái của process ở một thời điểm. Trong thời gian process không chạy, hệ thống bên ngoài vẫn tiếp tục hoạt động. Khi restore, object Java có thể được khôi phục nhưng resource mà object đại diện đã thay đổi hoặc hết hiệu lực.

Ví dụ:

- Connection tới database có thể đã bị server đóng.
- Token hoặc credential có thể hết hạn.
- DNS record hoặc địa chỉ service có thể thay đổi.
- Distributed lease có thể đã hết hạn và được cấp cho instance khác.
- Message consumer có thể phải tạo session mới.
- Scheduler có thể có lịch chạy đã đến hạn trong thời gian checkpoint.
- HTTP server có thể chưa mở listener hoặc chưa hoàn tất warm-up.

Vì thế, trạng thái "JVM đã restore" không đồng nghĩa "ứng dụng đã sẵn sàng nhận traffic".

Một chu trình điển hình:

~~~text
Kubernetes khởi động container
          │
          ▼
JVM restore từ checkpoint
          │
          ▼
CRaC afterRestore callbacks
          │
          ▼
Nạp runtime config và secret
          │
          ▼
Kết nối lại database / broker / API
          │
          ▼
Kiểm tra dependency và khôi phục worker
          │
          ▼
Ứng dụng hoàn tất bootstrap
          │
          ▼
Readiness chuyển sang ACCEPTING_TRAFFIC
          │
          ▼
Kubernetes đưa Pod vào Service endpoints
~~~

Trong thời gian các bước trên diễn ra, readiness phải trả trạng thái chưa sẵn sàng. Liveness vẫn nên thành công nếu process đang tiến triển bình thường. Startup probe cho kubelet biết thời gian chờ tối đa dành cho giai đoạn restore.

## 3. Startup probe: dành thời gian cho khởi động và restore

Startup probe được thiết kế cho container có thời gian khởi động dài. Khi probe này được cấu hình, Kubernetes chưa chạy liveness và readiness probe cho tới khi startup probe thành công.

Điều này hữu ích khi một ứng dụng Java phải thực hiện các bước sau restore:

1. Hoàn tất CRaC restore lifecycle.
2. Nạp runtime configuration của môi trường triển khai.
3. Lấy secret và credential hiện hành.
4. Tạo lại resource đã đóng trước checkpoint.
5. Khôi phục framework, scheduler hoặc consumer.
6. Hoàn thành các bước bootstrap bắt buộc.

### 3.1. Chọn endpoint startup

Spring Boot Actuator cung cấp health group cho liveness và readiness. Startup probe là khái niệm của Kubernetes; ứng dụng có thể cung cấp một endpoint riêng, ví dụ **/internal/startupz**, trả về thành công khi giai đoạn bootstrap/restore đã hoàn tất.

Endpoint startup nên trả về:

- **503 Service Unavailable** khi ứng dụng vẫn đang restore hoặc bootstrap.
- **200 OK** khi phần khởi động/restore đã hoàn tất và ứng dụng đã sẵn sàng bước sang giai đoạn kiểm tra readiness/liveness.

Không nhất thiết phải đưa mọi dependency bên ngoài vào startup endpoint. Nếu database tạm thời unavailable nhưng ứng dụng vẫn có thể tiếp tục chạy và chờ kết nối lại, startup có thể hoàn tất trong khi readiness vẫn thất bại. Cách phân chia này tránh restart container chỉ vì một dịch vụ bên ngoài đang gián đoạn.

Nếu ứng dụng bắt buộc phải kết nối database trước khi hoàn tất bootstrap và không thể tiến triển nếu database không có, có thể chọn đưa bước đó vào startup condition. Hãy xác định policy rõ ràng vì startup probe thất bại đủ lâu sẽ khiến kubelet restart container.

### 3.2. Tính thời gian startup tối đa

Các trường quan trọng:

- **periodSeconds**: khoảng thời gian giữa các lần probe.
- **timeoutSeconds**: thời gian tối đa cho một lần probe.
- **failureThreshold**: số lần thất bại liên tiếp trước khi probe bị xem là thất bại.

Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /internal/startupz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 60
~~~

Cấu hình này cho phép một khoảng chờ xấp xỉ 5 phút trước khi startup probe bị xem là thất bại. Thời gian thực tế còn phụ thuộc thời điểm bắt đầu probe, timeout và cách kubelet lập lịch.

Đừng đặt failureThreshold quá thấp nếu restore cần tải nhiều resource. Cũng không nên đặt quá cao để che giấu một lỗi restore vĩnh viễn; cần theo dõi thời gian restore thực tế và có giới hạn vận hành hợp lý.

### 3.3. Startup probe không phải readiness probe thứ hai

Startup probe chỉ xác nhận giai đoạn khởi động đã qua một mốc xác định. Sau khi nó thành công, readiness vẫn tiếp tục quyết định traffic. Ví dụ, startup hoàn tất nhưng database chưa kết nối được:

- Startup: thành công.
- Liveness: thành công nếu process vẫn hoạt động.
- Readiness: thất bại vì ứng dụng chưa thể phục vụ request cần database.

Đây là trạng thái hợp lệ. Container không cần restart chỉ vì chưa thể nhận traffic.

## 4. Readiness probe: chỉ nhận traffic sau khi restore hoàn tất

Readiness probe xác định container có thể nhận request mới hay không. Khi readiness thất bại, Pod không được xem là Ready và thông thường bị loại khỏi các Service endpoints dùng để gửi traffic tới Pod đó. Container vẫn chạy, kubelet không restart nó chỉ vì readiness thất bại.

Đây là probe quan trọng nhất để bảo vệ ứng dụng trong giai đoạn sau restore.

### 4.1. Các điều kiện readiness nên kiểm tra

Readiness sau restore có thể phụ thuộc vào:

- CRaC callback đã hoàn tất.
- Runtime config đã được đọc và validate.
- Secret/credential đã lấy được.
- Database pool đã tạo lại và cấp được connection hợp lệ.
- HTTP client hoặc broker client đã kết nối lại.
- Cache bắt buộc đã được nạp.
- Các resource cần thiết cho request đã hoạt động.
- Worker hoặc consumer bắt buộc đã được khôi phục theo policy.
- Ứng dụng đã mở listener và có thể xử lý request.

Không phải mọi dependency đều phải nằm trong readiness. Chỉ đưa vào các dependency thực sự cần cho khả năng phục vụ request. Nếu một tính năng tùy chọn bị lỗi, ứng dụng có thể vẫn Ready nếu các endpoint phụ thuộc tính năng đó được xử lý đúng và hệ thống có policy degraded mode rõ ràng.

### 4.2. Readiness không nên làm liveness thất bại theo dây chuyền

Ví dụ, database tạm thời không truy cập được:

- Readiness nên trả thất bại nếu request nghiệp vụ bắt buộc cần database.
- Liveness vẫn có thể thành công vì JVM và web server còn hoạt động, có thể kết nối lại khi database hồi phục.

Nếu cùng một health check database được dùng cho cả readiness và liveness, sự cố database có thể khiến mọi Pod restart đồng thời. Khi database trở lại, các Pod khởi động cùng lúc và tạo thêm connection burst.

### 4.3. Readiness của Kubernetes không dừng background job

Readiness chủ yếu điều khiển traffic qua Service. Nó không tự động dừng:

- @Scheduled method.
- @Async task.
- Message listener.
- Worker thread riêng.
- Retry loop hoặc polling task.

Nếu background worker cũng phải chờ dependency sau restore, cần có admission gate hoặc lifecycle coordinator riêng để chỉ resume công việc khi các resource đã sẵn sàng. Không dựa vào việc Pod chưa Ready để ngăn mọi loại công việc nền.

## 5. Liveness probe: phát hiện process không thể tự phục hồi

Liveness probe trả lời câu hỏi process có còn hoạt động theo cách mà ứng dụng có thể tiếp tục phục vụ hay không.

Các tình huống có thể làm liveness thất bại:

- JVM bị deadlock ở phần thiết yếu.
- Main event loop hoặc thread điều phối quan trọng không còn tiến triển.
- Ứng dụng rơi vào trạng thái nội bộ không thể phục hồi.
- Một lỗi nghiêm trọng khiến process không thể nhận hoặc xử lý công việc nữa.

Liveness không nên kiểm tra mọi dependency bên ngoài. Database, Redis, Kafka hoặc partner API có thể tạm thời lỗi mà process vẫn sống và có thể tiếp tục khi dependency hồi phục.

### 5.1. Không dùng liveness để restart khi database mất kết nối

Một thiết kế dễ gây sự cố:

~~~text
Liveness probe
     │
     ▼
Kiểm tra HTTP + database query
     │
     ▼
Database mất kết nối
     │
     ▼
Liveness thất bại trên nhiều Pod
     │
     ▼
Kubelet restart các container
     │
     ▼
Tất cả pool tạo kết nối lại cùng lúc
     │
     ▼
Database đang phục hồi bị quá tải
~~~

Thiết kế phù hợp hơn:

~~~text
Liveness: kiểm tra process nội bộ
Readiness: kiểm tra khả năng nhận request, gồm dependency bắt buộc
     │
     ├── Liveness OK, Readiness FAIL
     │       └── Container tiếp tục chạy, Pod tạm ngừng nhận traffic
     │
     └── Liveness FAIL
             └── Kubelet restart container
~~~

Chỉ đánh dấu liveness BROKEN khi process không còn cách tự phục hồi. Nếu dependency bên ngoài đang lỗi, thường nên giữ liveness CORRECT và readiness REFUSING_TRAFFIC.

## 6. Spring Boot Actuator và Kubernetes health group

Spring Boot Actuator hỗ trợ health group dành cho Kubernetes:

- /actuator/health/liveness
- /actuator/health/readiness

Liveness group phản ánh LivenessState; readiness group phản ánh ReadinessState. Khi ứng dụng chạy trong môi trường Kubernetes, Spring Boot có thể tự cấu hình các group này theo điều kiện runtime. Có thể bật rõ ràng để hành vi nhất quán giữa môi trường local, test và cluster.

Ví dụ application.yml:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

Với add-additional-paths, Spring Boot có thể cung cấp thêm các đường dẫn probe trên cổng HTTP chính:

- /livez
- /readyz

Điều này hữu ích khi management endpoint chạy trên một port riêng. Probe trên main application port kiểm tra được cả web server mà request thật sử dụng, thay vì chỉ xác nhận management server còn hoạt động.

Nếu không bật additional paths, dùng endpoint Actuator trên đúng port mà ứng dụng expose. Kiểm tra management.server.port, context path và security rules để chắc chắn kubelet truy cập được.

### 6.1. Tùy chỉnh readiness group

Readiness mặc định phản ánh trạng thái readiness của ứng dụng. Nếu database là dependency bắt buộc cho mọi request, có thể thêm health indicator database vào group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

Nếu database không cần thiết cho mọi request hoặc có thể phục vụ degraded mode, đừng thêm nó một cách máy móc. Một dependency tùy chọn bị lỗi không nhất thiết phải loại toàn bộ Pod khỏi Service.

Cũng tránh chạy một truy vấn nặng trên mỗi lần probe. Health indicator nên dùng timeout ngắn, thao tác nhẹ và không tạo tải đáng kể lên hệ thống đang gặp sự cố.

### 6.2. Lưu ý về management port

Nếu Actuator được expose trên cổng riêng, probe vào cổng đó có thể thành công ngay cả khi web server chính không hoạt động. Ngược lại, nếu cổng management chỉ được bind vào localhost, kubelet HTTP probe có thể không truy cập được theo cách mong muốn.

Hãy chọn một trong hai cách:

1. Dùng /livez và /readyz trên main application port khi phiên bản Spring Boot hỗ trợ additional paths.
2. Dùng /actuator/health/... trên management port và bảo đảm port đó được bind, expose và truy cập đúng từ kubelet.

Không mở rộng management endpoint ra Internet chỉ để Kubernetes probe được. Giữ các endpoint health trong phạm vi mạng nội bộ và áp dụng chính sách bảo vệ phù hợp.

## 7. Cập nhật trạng thái Spring Boot trong lifecycle CRaC

Spring Boot có mô hình availability với hai trạng thái quan trọng:

- LivenessState.CORRECT và LivenessState.BROKEN.
- ReadinessState.ACCEPTING_TRAFFIC và ReadinessState.REFUSING_TRAFFIC.

Ứng dụng có thể phát AvailabilityChangeEvent để cập nhật trạng thái. Health group của Actuator đọc các trạng thái này và trả kết quả cho Kubernetes.

Ví dụ helper:

~~~java
package com.example.probes;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class ReadinessController {

    private final ApplicationEventPublisher publisher;

    public ReadinessController(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refusingTraffic() {
        publisher.publishEvent(
                new AvailabilityChangeEvent<>(
                        this, ReadinessState.REFUSING_TRAFFIC));
    }

    public void acceptingTraffic() {
        publisher.publishEvent(
                new AvailabilityChangeEvent<>(
                        this, ReadinessState.ACCEPTING_TRAFFIC));
    }
}
~~~

Trước checkpoint, coordinator chuyển readiness sang REFUSING_TRAFFIC trước khi drain request và background work. Sau restore, chỉ chuyển sang ACCEPTING_TRAFFIC sau khi các dependency bắt buộc đã được khôi phục.

Liveness nên giữ CORRECT trong giai đoạn restore nếu process vẫn tiến triển và có thể tự hoàn tất. Nếu ứng dụng phát BROKEN quá sớm, liveness probe có thể khiến kubelet restart container trong khi callback vẫn đang thực hiện công việc phục hồi.

## 8. Tạo startup endpoint riêng cho giai đoạn restore

Spring Boot không có Kubernetes startup health group mặc định tương đương liveness/readiness. Có thể tạo một trạng thái riêng để biểu diễn quá trình bootstrap:

~~~java
package com.example.probes;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class RestoreStartupState {

    private final AtomicBoolean complete = new AtomicBoolean(false);

    public boolean isComplete() {
        return complete.get();
    }

    public void markInProgress() {
        complete.set(false);
    }

    public void markComplete() {
        complete.set(true);
    }
}
~~~

Endpoint HTTP:

~~~java
package com.example.probes;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StartupProbeController {

    private final RestoreStartupState state;

    public StartupProbeController(RestoreStartupState state) {
        this.state = state;
    }

    @GetMapping("/internal/startupz")
    public ResponseEntity<Void> startup() {
        if (!state.isComplete()) {
            return ResponseEntity.status(503).build();
        }

        return ResponseEntity.ok().build();
    }
}
~~~

Endpoint phải nhẹ, không gọi database hoặc partner API mỗi lần kubelet probe. Nó chỉ đọc một trạng thái trong bộ nhớ đã được coordinator cập nhật.

Đảm bảo trạng thái này được đặt về false khi bắt đầu mỗi chu kỳ restore. Nếu checkpoint được tạo khi biến complete vẫn là true, snapshot có thể giữ trạng thái đó và startup probe sẽ thành công quá sớm. Trước checkpoint, đặt startup state về false; sau restore, chỉ đặt true khi restore bootstrap hoàn tất.

## 9. Coordinator CRaC cập nhật readiness sau restore

Một coordinator có thể quản lý thứ tự khôi phục resource và availability. Mẫu sau minh họa phần điều phối; các thành phần RuntimeResources cần triển khai logic reconnect, validation và cleanup phù hợp với ứng dụng.

~~~java
package com.example.probes;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public class CracAvailabilityResource implements Resource {

    private final ReadinessController readiness;
    private final RestoreStartupState startupState;
    private final RuntimeResources runtimeResources;

    public CracAvailabilityResource(
            ReadinessController readiness,
            RestoreStartupState startupState,
            RuntimeResources runtimeResources) {

        this.readiness = readiness;
        this.startupState = startupState;
        this.runtimeResources = runtimeResources;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        readiness.refusingTraffic();
        startupState.markInProgress();

        runtimeResources.pauseBackgroundWork();
        runtimeResources.drainRequestsAndJobs();
        runtimeResources.closeResourcesForCheckpoint();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        readiness.refusingTraffic();
        startupState.markInProgress();

        try {
            runtimeResources.reloadRuntimeConfiguration();
            runtimeResources.reconnectDependencies();
            runtimeResources.validateRequiredResources();
            runtimeResources.resumeBackgroundWork();

            startupState.markComplete();
            readiness.acceptingTraffic();

        } catch (Exception failure) {
            readiness.refusingTraffic();
            throw failure;
        }
    }
}
~~~

Điểm quan trọng:

1. beforeCheckpoint đánh dấu Pod không nhận traffic trước khi dừng resource.
2. Startup state được reset để checkpoint không mang theo trạng thái bootstrap đã hoàn tất từ lần chạy trước.
3. afterRestore giữ readiness ở trạng thái từ chối traffic trong toàn bộ quá trình phục hồi.
4. Runtime config và secret được nạp trước khi tạo resource phụ thuộc.
5. Background worker chỉ được resume khi dependency cần thiết đã sẵn sàng.
6. Readiness chỉ chuyển sang ACCEPTING_TRAFFIC ở bước cuối.

Ví dụ là skeleton để minh họa trình tự. Nếu closeResourcesForCheckpoint() hoặc một bước callback thất bại, ứng dụng cần có policy phục hồi và logging cụ thể. Không nuốt exception để Kubernetes nhìn thấy trạng thái khỏe giả.

### 9.1. Tránh hai thành phần cùng sở hữu một resource

Nếu HikariCP, HTTP client hoặc message listener đã tự đăng ký CRaC Resource, coordinator không nên đóng/mở cùng resource lần thứ hai. Chọn một lifecycle owner cho từng thành phần và sắp xếp thứ tự đăng ký theo dependency.

Readiness coordinator có thể điều phối availability và admission gate; resource owner chuyên biệt chịu trách nhiệm vòng đời nội bộ của pool hoặc client. Phải bảo đảm callback không mở traffic trước khi các owner đó hoàn tất.

## 10. Cấu hình Deployment với đủ ba probe

Ví dụ Deployment dùng HTTP probe trên cổng chính của ứng dụng:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example/orders-service:2.4.0
          ports:
            - name: http
              containerPort: 8080

          startupProbe:
            httpGet:
              path: /internal/startupz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60

          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1

          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Trong ví dụ:

- Startup probe cho ứng dụng tối đa khoảng 5 phút để hoàn tất restore bootstrap.
- Readiness được kiểm tra thường xuyên hơn để Pod nhanh chóng rời Service khi không thể nhận traffic và quay lại khi đã sẵn sàng.
- Liveness chỉ restart container khi endpoint liveness thất bại liên tiếp theo ngưỡng đã đặt.
- terminationGracePeriodSeconds cho phép ứng dụng có thời gian xử lý shutdown khi container bị dừng.

Các giá trị chỉ là điểm bắt đầu. Hãy đo restore duration, thời gian kết nối database, warm-up và drain thực tế để chọn threshold. Nếu startup probe thất bại đủ số lần, kubelet restart container; nếu entrypoint luôn cố restore cùng checkpoint lỗi, ứng dụng có thể rơi vào restart loop. Cần có chiến lược fallback sang cold start hoặc loại bỏ checkpoint không còn hợp lệ theo quy trình triển khai.

### 10.1. Dùng /actuator/health hay /readyz?

Nếu đã bật:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

có thể dùng /livez và /readyz như Deployment trên.

Nếu không bật additional paths, thay path bằng endpoint Actuator tương ứng, ví dụ /actuator/health/liveness và /actuator/health/readiness, đồng thời trỏ đúng port management. Không dùng một path giả định rồi triển khai khi chưa kiểm tra endpoint thực tế.

## 11. Probe qua HTTP, TCP hay exec?

Kubernetes hỗ trợ nhiều loại probe. Chọn loại phù hợp với trạng thái cần kiểm tra.

| Loại | Ưu điểm | Hạn chế | Dùng khi |
|---|---|---|---|
| HTTP GET | Có thể phản ánh readiness/liveness logic của ứng dụng | Cần web server và endpoint probe hoạt động | Java web application, Spring Boot Actuator |
| TCP socket | Kiểm tra cổng có nhận kết nối | Chỉ chứng minh port mở, không chứng minh dependency hoặc request path hoạt động | Ứng dụng không có HTTP health endpoint |
| Exec | Kiểm tra command bên trong container | Command có thể tốn tài nguyên và tạo thêm process | Worker không expose HTTP hoặc cần kiểm tra trạng thái local |
| gRPC | Tích hợp với health protocol của gRPC | Cần server hỗ trợ health service và cấu hình phù hợp | gRPC service |

TCP probe chỉ xác nhận socket accept connection. Một HTTP server có thể mở port nhưng application service chưa sẵn sàng; do đó TCP không thay thế readiness logic.

Exec probe cũng không nên chạy script nặng hoặc gọi hàng loạt dependency. Probe được thực hiện định kỳ; mỗi lần chạy cần nhanh và có timeout rõ ràng.

## 12. Thiết kế endpoint probe đáng tin cậy

Probe endpoint là một phần của control plane. Nếu endpoint quá nặng, không ổn định hoặc phụ thuộc vào chính thành phần đang gặp sự cố, nó có thể tạo ra false negative.

### 12.1. Trả lời nhanh và có timeout

Endpoint nên:

- Trả kết quả nhanh, không chờ vô hạn.
- Không thực hiện migration hoặc warm-up trong request probe.
- Không tạo connection mới nếu chỉ cần đọc trạng thái đã được cập nhật.
- Không ghi log stack trace mỗi lần probe thất bại.
- Không yêu cầu authentication phức tạp mà kubelet không thể cung cấp.
- Không redirect sang login page.
- Có timeout ngắn hơn chu kỳ probe hợp lý.

Nếu cần kiểm tra database, nên dùng health indicator có timeout và giới hạn tần suất. Một query nặng trên mỗi lần probe có thể làm database quá tải hơn trong thời gian phục hồi.

### 12.2. Không expose thông tin nhạy cảm

Health response không nên trả:

- JDBC URL chứa thông tin nhạy cảm.
- Username/password/token.
- Nội dung exception nội bộ.
- Connection string hoặc topology không cần thiết.
- Dữ liệu nghiệp vụ của khách hàng.

Kubernetes chỉ cần biết probe thành công hay thất bại. Log chi tiết cần được giữ ở application log/metrics với quyền truy cập phù hợp.

### 12.3. Kiểm tra đúng port và context path

Nếu ứng dụng dùng server.servlet.context-path, management.endpoints.web.base-path hoặc management port riêng, URL probe phải phản ánh đúng đường dẫn cuối cùng.

Kiểm tra trong container:

~~~bash
curl -i http://127.0.0.1:8080/internal/startupz
curl -i http://127.0.0.1:8080/readyz
curl -i http://127.0.0.1:8080/livez
~~~

Đây là kiểm tra endpoint tại local container. Kết quả thực tế của kubelet còn phụ thuộc port binding, network namespace và cấu hình Pod.

## 13. Readiness trong lúc checkpoint và khi checkpoint thất bại

Readiness không chỉ quan trọng sau restore; nó còn cần được cập nhật trước khi tạo checkpoint.

Một quy trình checkpoint thường gồm:

1. Đánh dấu REFUSING_TRAFFIC.
2. Ngừng nhận request mới và background work.
3. Drain request, transaction và task đang chạy.
4. Đóng resource cần tạo lại.
5. Yêu cầu CRaC checkpoint.
6. Sau restore, khôi phục dependency và chỉ chuyển sang ACCEPTING_TRAFFIC khi hoàn tất.

Khi readiness false, Service ngừng gửi traffic mới tới Pod theo trạng thái endpoint. Request đang chạy có thể vẫn tồn tại; readiness không tự drain request hiện tại. Ứng dụng phải có cơ chế graceful drain riêng.

Nếu bước chuẩn bị checkpoint thất bại trước khi process được dump, ứng dụng cần khôi phục admission/readiness theo policy. Ví dụ, nếu drain timeout và callback từ chối checkpoint, process vẫn có thể tiếp tục chạy; cần mở gate và readiness lại khi resource vẫn an toàn. Nếu dump đã thành công và process được restore, afterRestore chịu trách nhiệm mở lại readiness.

Không giả định kubelet sẽ tự suy ra checkpoint bắt đầu hoặc kết thúc từ probe. Kubernetes chỉ phản ứng với kết quả health endpoint và lifecycle của container mà runtime báo cáo.

## 14. Background workers và consumer sau restore

Readiness của Pod không tự điều khiển scheduler hoặc consumer. Một ứng dụng có thể chưa nhận HTTP traffic nhưng background worker vẫn tiếp tục xử lý.

Nếu worker cần dependency đã được phục hồi, thứ tự nên là:

~~~text
afterRestore
    │
    ▼
Load runtime config/secrets
    │
    ▼
Reconnect database / broker / API
    │
    ▼
Validate required resources
    │
    ▼
Resume scheduled jobs and consumers
    │
    ▼
Set readiness ACCEPTING_TRAFFIC
~~~

Một số ứng dụng muốn mở HTTP traffic trước khi resume worker. Điều đó có thể hợp lý nếu worker không ảnh hưởng khả năng phục vụ request. Hãy quyết định dựa trên dependency graph và mục tiêu availability.

Với message consumer, xác thực lease/session và trạng thái offset sau restore. Với @Scheduled, tính lại next-run time và missed-run policy. Với worker nhiều instance, dùng distributed lock, lease hoặc idempotency để tránh xử lý trùng.

## 15. Liveness và readiness trong môi trường nhiều replica

Giả sử Deployment có ba replica. Một replica restore chậm vì database connection chưa sẵn sàng:

- Replica đó trả readiness thất bại và chưa nhận traffic.
- Hai replica còn lại tiếp tục phục vụ.
- Liveness của replica đang restore vẫn thành công nếu process đang tiến triển.
- Khi database connection được xác nhận và readiness chuyển thành công, replica được đưa lại vào Service endpoints.

Nếu liveness phụ thuộc database, cả ba replica có thể bị restart cùng lúc khi database mất kết nối. Khi database hồi phục, các pool cùng warm-up và tạo connection burst. Đây là lý do phải tách readiness khỏi liveness.

Nếu tất cả replica cùng restore, readiness sẽ giữ traffic khỏi các instance cho tới khi chúng thực sự sẵn sàng. Có thể dùng rollout strategy, maxUnavailable, maxSurge, startup budget và staggered restore để tránh khởi động lại toàn bộ capacity cùng lúc.

## 16. Phân biệt lỗi restore với lỗi liveness

Không phải mọi lỗi sau restore đều nên dẫn đến cùng một hành động.

| Tình huống | Startup | Readiness | Liveness | Hành động |
|---|---|---|---|---|
| Callback đang khôi phục resource | Chưa thành công | Fail | OK | Chờ trong startup budget |
| Database tạm thời unavailable | Complete nếu bootstrap có thể chờ độc lập | Fail nếu DB bắt buộc | OK | Giữ container chạy, retry có giới hạn |
| Partner API tùy chọn unavailable | Complete | Có thể OK theo degraded policy | OK | Giữ tính năng phụ thuộc ở trạng thái hạn chế |
| Web server chưa bind port | Fail hoặc endpoint chưa truy cập được | Fail | Chưa probe cho tới startup success nếu có startup probe | Chờ trong startup budget |
| JVM/process deadlock không tự phục hồi | Có thể đã complete | Fail | Fail | Kubelet restart container |
| Runtime config sai schema | Fail nếu không thể hoàn tất bootstrap | Fail | Process có thể vẫn sống | Báo lỗi, không mở traffic; cần sửa config |
| Checkpoint image không tương thích | Restore process thất bại trước khi endpoint mở | Fail | Không truy cập được | Fallback cold start hoặc phát hành checkpoint phù hợp |

Bảng này giả định startup endpoint biểu diễn bootstrap completion, readiness phản ánh dependency bắt buộc và liveness chỉ phản ánh process health. Điều chỉnh theo kiến trúc thực tế.

## 17. Quan sát và chẩn đoán probe sau restore

Khi Pod không Ready hoặc bị restart, cần phân biệt probe nào gây ra hành động.

Các lệnh hữu ích:

~~~bash
kubectl describe pod <POD_NAME>
kubectl get pod <POD_NAME> -o wide
kubectl logs <POD_NAME> -c app --previous
kubectl logs <POD_NAME> -c app
~~~

Lệnh kubectl describe pod hiển thị Events và thông tin probe failure. Tham số --previous lấy log của container instance trước đó nếu container đã restart và log còn được giữ.

Nên ghi log lifecycle theo các mốc:

- restore_started
- runtime_config_loaded
- secrets_loaded
- database_reconnected
- external_clients_ready
- background_workers_resumed
- readiness_accepting_traffic

Có thể thêm metric:

| Metric | Ý nghĩa |
|---|---|
| crac_restore_duration_seconds | Thời gian từ khi restore bắt đầu đến khi bootstrap hoàn tất |
| crac_restore_failures_total | Số lần restore thất bại |
| application_readiness | Trạng thái nhận traffic |
| startup_probe_failures_total | Số lần startup probe thất bại |
| readiness_probe_failures_total | Số lần readiness probe thất bại |
| liveness_probe_failures_total | Số lần liveness probe thất bại |
| background_active_tasks | Số task nền đang chạy |
| dependency_reconnect_duration_seconds | Thời gian kết nối lại dependency |

Tên metric là ví dụ do ứng dụng/monitoring stack định nghĩa; Kubernetes không tự tạo tất cả các metric này.

Không log secret, token hoặc toàn bộ health response có thông tin nội bộ. Ghi rõ phase và component để phân biệt restore đang tiến triển, dependency đang retry hay process đã thực sự bị treo.

## 18. Những lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không có startup probe cho restore kéo dài | Liveness có thể restart container quá sớm | Dùng startup probe với budget đo từ restore thực tế |
| Startup probe kiểm tra database trong khi DB chỉ tạm thời unavailable | Container bị restart dù process có thể chờ | Tách startup completion khỏi readiness dependency |
| Readiness luôn trả 200 sau restore | Pod nhận traffic khi pool/client chưa sẵn sàng | Giữ REFUSING_TRAFFIC đến khi resource hợp lệ |
| Liveness gọi database query | Database outage gây restart đồng loạt | Giữ liveness độc lập với dependency bên ngoài |
| Probe dùng sai port/context path | Kubelet liên tục báo failure | Kiểm tra endpoint thực tế trong container |
| Management port sống nhưng main server chết | Probe cho kết quả khỏe giả | Dùng additional paths trên main port hoặc kiểm tra cả web server |
| Readiness được dùng để dừng scheduler | Background job vẫn chạy | Dùng admission gate riêng cho worker |
| Startup flag được checkpoint ở trạng thái true | Startup probe thành công trước khi restore xong | Reset startup state trước checkpoint và chỉ set complete sau restore |
| Threshold quá thấp | Restore hợp lệ bị restart | Đo p95/p99 restore duration và tăng budget hợp lý |
| Threshold quá cao | Lỗi restore kéo dài bị phát hiện chậm | Đặt timeout hữu hạn, alert và fallback |
| Liveness thất bại rồi restore cùng checkpoint lỗi lặp lại | Container restart loop | Có chiến lược cold-start/fallback và quản lý checkpoint invalid |

## 19. Kiểm thử probe với CRaC

Cần kiểm tra cả đường thành công và đường lỗi trên đúng phiên bản Kubernetes, container runtime, JDK CRaC, CRIU và Spring Boot sẽ triển khai.

### 19.1. Đường thành công

1. Tạo checkpoint trong môi trường chuẩn bị.
2. Bảo đảm readiness được chuyển sang REFUSING_TRAFFIC trước khi checkpoint.
3. Khởi động Pod từ checkpoint.
4. Xác nhận startup probe thất bại trong khi restore chưa hoàn tất.
5. Xác nhận liveness/readiness chưa được dùng trước khi startup probe thành công.
6. Quan sát callback sau restore nạp config và kết nối lại dependency.
7. Xác nhận startup endpoint chuyển thành công.
8. Xác nhận readiness chỉ chuyển thành công sau health check bắt buộc.
9. Gửi request qua Service và xác nhận Pod chỉ nhận traffic khi Ready.

### 19.2. Database unavailable

1. Restore Pod khi database tạm thời không truy cập được.
2. Để bootstrap hoàn tất nếu ứng dụng có thể tiếp tục chờ dependency.
3. Xác nhận readiness thất bại.
4. Xác nhận liveness vẫn thành công.
5. Khôi phục database.
6. Xác nhận ứng dụng reconnect và readiness chuyển thành công mà không cần restart container.

Nếu ứng dụng không thể hoàn tất startup khi thiếu database, kiểm tra startup budget và quyết định restart/fallback có chủ đích.

### 19.3. Process bị treo

Trong môi trường thử nghiệm, tạo một tình huống liveness thực sự không thể phục hồi, chẳng hạn làm cho component điều phối chính không còn tiến triển. Xác nhận liveness thất bại liên tiếp và kubelet restart container theo policy.

Không dùng database outage để giả lập process deadlock, vì hai tình huống cần hành động khác nhau.

### 19.4. Restore thất bại

Thử checkpoint không tương thích hoặc thiếu runtime resource trong staging. Xác nhận:

- Startup probe không báo thành công giả.
- Readiness không chuyển ACCEPTING_TRAFFIC.
- Log cho biết phase restore thất bại.
- Kubelet có hành động đúng theo threshold.
- Deployment có fallback phù hợp thay vì lặp vô hạn cùng checkpoint lỗi.

### 19.5. Kiểm tra Service endpoints

Có thể quan sát Pod readiness và EndpointSlice:

~~~bash
kubectl get pods -l app=orders-service
kubectl get endpointslices -l kubernetes.io/service-name=orders-service
~~~

Khi readiness fail, xác nhận Pod không được xem là endpoint Ready để Service gửi traffic mới. Sau khi readiness thành công, endpoint được cập nhật theo trạng thái của Pod.

## 20. Quy trình triển khai đề xuất

Một quy trình vận hành rõ ràng có thể tổ chức như sau:

~~~text
CHECKPOINT PREPARATION
  - Đánh dấu readiness REFUSING_TRAFFIC
  - Pause background job/consumer admission
  - Drain request và task active
  - Đóng resource cần tạo lại
  - Tạo checkpoint
          │
          ▼
CONTAINER START / RESTORE
  - Khởi chạy từ checkpoint
  - Startup probe chờ restore bootstrap
          │
          ▼
AFTER RESTORE
  - Reset/giữ startup state chưa hoàn tất
  - Load runtime config và secrets
  - Reconnect dependencies
  - Validate resource
  - Resume worker theo policy
          │
          ▼
PROBE STATES
  - Startup: success
  - Liveness: process healthy
  - Readiness: accepting traffic
          │
          ▼
KUBERNETES SERVICE
  - Pod được xem là Ready
  - Service có thể gửi traffic mới
~~~

Cấu hình nên được version hóa cùng deployment. Khi thay đổi endpoint, health group hoặc startup duration, kiểm thử lại cả quá trình restore chứ không chỉ kiểm tra ứng dụng cold start.

## 21. Nguyên tắc cần nhớ

Startup, readiness và liveness có vai trò riêng. Sau CRaC restore, startup probe bảo vệ thời gian phục hồi; readiness giữ traffic khỏi Pod cho tới khi resource và dependency bắt buộc đã hoạt động; liveness chỉ yêu cầu restart khi process thật sự không thể tiếp tục.

Spring Boot Actuator cung cấp health group liveness/readiness và availability state để ứng dụng điều khiển kết quả probe. CRaC callback nên giữ readiness ở REFUSING_TRAFFIC trong suốt quá trình phục hồi, reset startup completion trước checkpoint và chỉ công bố trạng thái sẵn sàng sau khi cấu hình, secret, connection pool, client và worker cần thiết đã được khôi phục.

Kubernetes không hiểu ý nghĩa của checkpoint image hoặc callback CRaC. Nó chỉ nhìn thấy kết quả probe và trạng thái container. Khi endpoint phản ánh đúng lifecycle, kubelet có thể chờ restore, tránh gửi traffic quá sớm và chỉ restart process khi có bằng chứng về lỗi sống thực sự.

## 22. Tài liệu tham khảo

- [Kubernetes: Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): semantics, cấu hình và hành vi của ba probe.
- [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): health group liveness/readiness và các endpoint Actuator.
- [Spring Boot: Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): trạng thái liveness/readiness và availability events.
- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): quản lý resource trước checkpoint và sau restore.

