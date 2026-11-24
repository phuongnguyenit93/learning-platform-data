# Kết thúc an toàn, shutdown hook và thời gian chờ hoàn tất yêu cầu

Một Spring Boot service không nên dừng bằng cách kết thúc process ngay khi nhận lệnh stop. Khi triển khai phiên bản mới, scale down hoặc thay Pod, ứng dụng cần ngừng nhận công việc mới, hoàn tất request đang xử lý, dừng consumer và scheduler, giải phóng kết nối, ghi dữ liệu còn tồn và kết thúc trong khoảng thời gian nền tảng cho phép.

Quy trình này được gọi là **graceful shutdown**. Nó đặc biệt quan trọng với Spring Boot Native Image vì container thường khởi chạy native executable trực tiếp. Binary cần nhận đúng tín hiệu dừng của hệ điều hành, Spring phải đóng `ApplicationContext`, web server phải drain request và các thành phần nền phải hoàn tất trước khi container runtime gửi `SIGKILL`.

Bài học này giải thích mối quan hệ giữa shutdown hook của Java, signal handler của GraalVM Native Image, lifecycle của Spring, thời gian chờ HTTP request, Docker và Kubernetes. Bạn sẽ cấu hình graceful shutdown, quản lý tác vụ nền, tính ngân sách thời gian, kiểm thử bằng request đang chạy và xử lý các trường hợp process bị dừng cưỡng bức.

## 1. Graceful shutdown giải quyết vấn đề gì?

Một service đang xử lý request có thể đồng thời giữ:

- HTTP request và response chưa hoàn tất.
- Database transaction hoặc connection đang sử dụng.
- Message đã nhận từ broker nhưng chưa acknowledge.
- Tác vụ đang chạy trong executor hoặc scheduler.
- File, socket, lock hoặc tài nguyên JNI/native.
- Log, trace và telemetry buffer chưa được flush.

Nếu process kết thúc ngay, client có thể nhận connection reset hoặc timeout; transaction có thể rollback; message chưa acknowledge có thể được gửi lại; file có thể chưa được flush. Client thường retry, vì vậy một thao tác nghiệp vụ có thể được gửi nhiều lần.

Graceful shutdown tổ chức việc dừng theo các bước:

1. Nhận tín hiệu yêu cầu kết thúc.
2. Chuyển ứng dụng sang trạng thái không nhận traffic/công việc mới.
3. Chờ request và công việc đang chạy hoàn tất trong thời hạn cho phép.
4. Dừng consumer, scheduler và executor theo thứ tự phụ thuộc.
5. Đóng connection pool, client, file và tài nguyên ứng dụng.
6. Kết thúc process trước deadline của container runtime.

Mục tiêu là bảo toàn công việc đã nhận và làm cho các request mới được định tuyến sang instance khác. Graceful shutdown không thể bảo đảm mọi tác vụ hoàn thành nếu chúng vượt quá deadline hoặc process bị `SIGKILL`.

## 2. Phân biệt shutdown hook, signal handler và Spring lifecycle

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Vai trò | Ví dụ |
|---|---|---|
| OS signal | Báo cho process biết hệ điều hành hoặc container muốn dừng | `SIGTERM`, `SIGINT` |
| Shutdown hook | Chạy logic kết thúc khi runtime bắt đầu shutdown sequence | `Runtime.addShutdownHook` |
| Spring lifecycle | Dừng web server, bean, consumer và giải phóng tài nguyên trong `ApplicationContext` | `SmartLifecycle`, `@PreDestroy`, `DisposableBean` |

Spring Boot tự đăng ký shutdown hook với runtime để đóng `ApplicationContext` khi ứng dụng kết thúc. Khi context đóng, các callback lifecycle của Spring được gọi. Vì vậy, phần lớn ứng dụng chỉ cần quản lý tài nguyên thông qua Spring bean lifecycle.

Với Native Image, OS signal phải được chuyển thành shutdown sequence của runtime thì shutdown hook mới có cơ hội chạy. Sau đó Spring mới đóng context và thực hiện các callback tương ứng.

Không nên tạo thêm nhiều shutdown hook độc lập để đóng cùng một tài nguyên. Các hook có thể chạy đồng thời và thứ tự không được bảo đảm; điều đó dễ tạo race condition giữa hook tự viết và hook do Spring Boot quản lý.

## 3. Java shutdown hook hoạt động như thế nào?

Trong JVM, ứng dụng có thể đăng ký hook bằng `Runtime.getRuntime().addShutdownHook`. Khi shutdown sequence bắt đầu, runtime khởi chạy các hook đã đăng ký. Thứ tự giữa các hook không được xác định và chúng có thể chạy đồng thời với nhau.

Ví dụ tối giản:

~~~java
Runtime.getRuntime().addShutdownHook(
    new Thread(() -> {
        System.out.println("Process is shutting down");
    }, "custom-shutdown-hook")
);
~~~

Shutdown hook phù hợp cho thao tác cấp process không thuộc lifecycle của Spring, ví dụ một thành phần native độc lập không được Spring quản lý. Với datasource, message listener, executor hoặc bean ứng dụng, hãy ưu tiên cơ chế đóng của Spring.

Một hook nên:

- Chạy nhanh và có giới hạn thời gian.
- Có thể gọi lặp an toàn nếu thiết kế yêu cầu.
- Tránh deadlock và chờ vô hạn.
- Không phụ thuộc mù quáng vào một hook khác đã có thể bắt đầu đóng tài nguyên.
- Không gọi `System.exit` từ chính shutdown hook.
- Không giả định `finally` hoặc callback sẽ chạy nếu process bị `SIGKILL`.

Một shutdown hook bị treo có thể ngăn runtime hoàn tất shutdown sequence cho tới khi hệ điều hành cưỡng bức kết thúc process.

## 4. Native Image nhận SIGTERM như thế nào?

Native executable không chạy trong HotSpot, vì vậy không nên mặc định mọi hành vi signal giống hệt JVM. GraalVM Native Image có cơ chế exit handler để xử lý tín hiệu kết thúc và khởi chạy shutdown hooks.

Tùy phiên bản GraalVM:

- Ở các phiên bản cũ, có thể cần build executable với `--install-exit-handlers` để cài đặt signal/exit handlers.
- Từ GraalVM 25, exit handlers được bật mặc định cho native executable; tùy chọn `--install-exit-handlers` đã được deprecated và thường có thể bỏ.
- Hành vi dành cho shared library khác executable; ứng dụng Spring Boot triển khai thành process thường là executable.

Hãy kiểm tra GraalVM distribution và release notes đang dùng. Không sao chép build argument của một phiên bản cũ vào mọi pipeline mà không xác minh.

Có thể kiểm tra toolchain trên máy build:

~~~bash
native-image --version
native-image --help
~~~

Đối chiếu version và các option builder thực sự nhận với GraalVM release notes. Nếu dùng Buildpacks, kiểm tra version GraalVM bên trong builder image và log build thay vì chỉ kiểm tra JDK trên máy chạy Maven/Gradle.

Khi signal handler được cài đặt và runtime nhận `SIGTERM`, Native Image có thể bắt đầu shutdown sequence, chạy hook của Spring Boot và đóng context. Nếu handler không hoạt động, signal mặc định của hệ điều hành có thể kết thúc process mà không chạy cleanup như mong đợi.

## 5. Phân biệt SIGTERM, SIGINT và SIGKILL

| Signal | Nguồn thường gặp | Có thể xử lý graceful? |
|---|---|---|
| `SIGTERM` | Docker stop, Kubernetes hoặc process supervisor | Có, nếu runtime và ứng dụng hỗ trợ |
| `SIGINT` | Ctrl+C trong terminal | Có, nếu runtime cài handler phù hợp |
| `SIGKILL` | Hết thời gian chờ, kill cưỡng bức hoặc hệ điều hành | Không thể bắt hoặc bỏ qua |

`SIGTERM` là tín hiệu yêu cầu process kết thúc. Process có cơ hội đóng tài nguyên trước khi thoát. `SIGKILL` kết thúc process ngay ở cấp hệ điều hành; không có shutdown hook, `@PreDestroy` hay Spring lifecycle callback nào có thể cứu vãn.

Do đó, graceful shutdown luôn cần một deadline. Nếu công việc không thể hoàn tất trong thời hạn đó, thiết kế nghiệp vụ phải xác định cách retry, rollback hoặc redeliver.

## 6. SpringApplication đóng ApplicationContext khi process kết thúc

Mỗi `SpringApplication` đăng ký shutdown hook để đóng `ApplicationContext` khi runtime shutdown. Các callback chuẩn của Spring có thể được dùng:

- `@PreDestroy` trên bean.
- `DisposableBean.destroy()`.
- Phương thức destroy được khai báo trong bean definition.
- `Lifecycle` và `SmartLifecycle` cho thành phần cần start/stop có thứ tự.
- `ContextClosedEvent` nếu cần phản ứng với sự kiện context đang đóng.

Ví dụ một bean ghi log và flush buffer khi context đóng:

~~~java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class ExportBuffer {

    private final AtomicBoolean closed = new AtomicBoolean();

    @PreDestroy
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        flushPendingRecords();
    }

    private void flushPendingRecords() {
        // Ghi phần dữ liệu còn tồn bằng API của ứng dụng.
    }
}
~~~

Đoạn code minh họa callback, không phải một cơ chế flush chung cho mọi thư viện. Trong ứng dụng thực tế, thao tác flush phải có deadline, log lỗi và xử lý trạng thái đã đóng. Nếu tài nguyên đã được một Spring bean khác quản lý, không tự đóng lại cùng tài nguyên ở nhiều nơi.

Ví dụ dùng jakarta.annotation.PreDestroy phù hợp với Spring Boot 3 trở lên. Dự án Spring Boot 2 dùng namespace javax.annotation.PreDestroy và dependency tương ứng.

Không tắt shutdown hook mặc định của `SpringApplication` nếu ứng dụng dựa vào nó để đóng context, trừ khi bạn chủ động cung cấp cơ chế đóng khác.

## 7. Bật graceful shutdown cho web server

Spring Boot hỗ trợ graceful shutdown với các embedded web server được tích hợp. Khi context đóng, web server ngừng nhận request mới và cho request đang chạy một khoảng thời gian để hoàn tất.

Cấu hình rõ ràng trong `application.yml`:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Hoặc trong `application.properties`:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Tài liệu Spring Boot 4.2 hiện hành cho biết graceful shutdown được bật mặc định với embedded Jetty, Reactor Netty và Tomcat. Có thể đặt `server.shutdown=immediate` để tắt. Một số phiên bản Spring Boot cũ yêu cầu cấu hình `server.shutdown=graceful` để bật; hãy kiểm tra tài liệu đúng phiên bản của dự án.

`spring.lifecycle.timeout-per-shutdown-phase` cấu hình thời gian chờ cho mỗi lifecycle phase. Đây không nhất thiết là tổng thời gian đóng toàn bộ ứng dụng nếu có nhiều phase khác nhau.

## 8. Điều gì xảy ra với request đang chạy?

Khi graceful shutdown bắt đầu, web server ngừng nhận request mới theo cơ chế riêng của server. Request đã được nhận có cơ hội hoàn tất trong thời gian grace period.

Cách từ chối request mới có thể khác theo server và phiên bản:

- Tomcat, Jetty và Reactor Netty có thể ngừng nhận request ở tầng mạng.
- Một số server/phiên bản có thể nhận kết nối nhưng trả trạng thái từ chối, chẳng hạn `503 Service Unavailable`.
- Persistent connection, HTTP/2 stream, WebSocket và request bất đồng bộ có vòng đời riêng cần kiểm thử.

Không giả định mọi client luôn nhận cùng một status code khi server bắt đầu dừng. Contract của client nên xử lý cả connection reset, timeout và response retryable trong thời điểm rollout.

Các request dài cần có giới hạn hợp lý. Nếu một request có thể chạy nhiều phút nhưng Pod chỉ được cấp 30 giây để dừng, server không thể bảo đảm request đó hoàn tất.

## 9. Thứ tự dừng SmartLifecycle bean

`SmartLifecycle` cho phép thành phần tham gia vào lifecycle của Spring với thứ tự và callback dừng.

Quy tắc phase:

- Phase nhỏ hơn được start trước.
- Khi shutdown, phase lớn hơn được stop trước.
- Các bean trong cùng phase có thể dừng đồng thời.
- Quan hệ `depends-on` cũng ảnh hưởng thứ tự: bean phụ thuộc được dừng trước dependency mà nó cần.

Spring Boot thực hiện graceful shutdown của web server trong phase sớm nhất của quá trình stop `SmartLifecycle`. Sau đó các phase khác tiếp tục dừng theo lifecycle processor.

Điều này hữu ích khi service có message consumer, worker và datasource. Ví dụ, consumer phải ngừng nhận message và hoàn tất công việc trước khi connection pool mà nó dùng bị đóng.

Không đặt phase tùy tiện. Hãy vẽ rõ dependency và xác định thành phần nào cần còn hoạt động trong lúc thành phần khác đang dừng.

## 10. Dùng SmartLifecycle cho tác vụ cần dừng bất đồng bộ

`SmartLifecycle.stop(Runnable callback)` cho phép bean thực hiện công việc dừng bất đồng bộ. Bean phải gọi callback sau khi đã hoàn tất việc dừng; nếu quên callback, lifecycle processor phải chờ tới timeout của phase.

Ví dụ rút gọn cho queue consumer:

~~~java
@Override
public void stop(Runnable callback) {
    running = false;
    consumer.pause();

    try {
        boolean drained = consumer.awaitInFlight(Duration.ofSeconds(10));
        if (!drained) {
            log.warn("Consumer drain timed out");
        }
    }
    finally {
        try {
            consumer.close();
        }
        finally {
            callback.run();
        }
    }
}
~~~

`consumer` ở đây là adapter của broker mà ứng dụng đang dùng. Lớp triển khai đầy đủ còn phải cung cấp `start()`, `stop()` và `isRunning()` theo contract của `SmartLifecycle`.

Callback chỉ được gọi khi phần việc dừng của bean đã kết thúc hoặc đã quyết định kết thúc theo timeout. Không gọi callback ngay khi mới bắt đầu dừng nếu worker vẫn đang chạy, vì Spring có thể chuyển sang đóng dependency mà worker còn cần.

## 11. Dừng executor và scheduled task

Executor do ứng dụng tự tạo cần có chính sách shutdown rõ ràng. Khi dừng, cần ngăn task mới, chờ task đang chạy và quyết định xử lý queue còn tồn.

Với `ThreadPoolTaskExecutor`, có thể cấu hình:

~~~java
@Bean
ThreadPoolTaskExecutor exportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(15);
    return executor;
}
~~~

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ task đã nhận; `setAwaitTerminationSeconds` giới hạn thời gian chờ. Chọn queue capacity và timeout theo workload thực tế. Nếu queue có thể chứa công việc quan trọng, cân nhắc lưu bền vững thay vì chỉ giữ trong RAM.

Với scheduler, cần ngăn lịch mới được kích hoạt trong khi shutdown và chờ tác vụ hiện tại hoàn tất theo giới hạn. Không để một scheduled task chạy vô hạn giữ process ở trạng thái đang đóng.

Nếu dùng executor do Spring Boot tự cấu hình, kiểm tra các thuộc tính shutdown của `spring.task.execution` và `spring.task.scheduling` theo phiên bản Boot. Tránh tạo executor thủ công mà không có bean lifecycle quản lý.

## 12. Dừng message consumer mà không làm mất message

Với Kafka, RabbitMQ, JMS hoặc broker khác, shutdown cần phân biệt message đã nhận với message chưa nhận.

Một trình tự thường dùng:

1. Ngừng poll/consume message mới.
2. Chờ message đang xử lý hoàn tất trong deadline.
3. Commit offset hoặc acknowledge các message đã xử lý thành công.
4. Để message chưa hoàn tất được redeliver theo cơ chế broker.
5. Đóng consumer/channel/connection.

Nếu hết deadline, không acknowledge một message mà nghiệp vụ chưa hoàn tất. Broker có thể gửi lại message đó; handler cần idempotent để không tạo tác động trùng khi retry.

Không chỉ dựa vào HTTP graceful shutdown. Một service có thể không còn nhận HTTP request nhưng vẫn có message consumer đang xử lý. Consumer phải tham gia Spring lifecycle và có thời hạn drain riêng.

## 13. Đóng dependency theo thứ tự an toàn

Một ứng dụng có thể cần giữ database hoặc HTTP client mở trong lúc worker cuối cùng hoàn tất. Vì vậy, thứ tự shutdown cần phản ánh quan hệ phụ thuộc:

| Thành phần | Việc cần làm |
|---|---|
| Web server | Ngừng nhận request mới, chờ request đang chạy |
| Message consumer | Ngừng nhận message mới, drain message đang xử lý |
| Scheduler | Không tạo công việc mới |
| Executor | Chờ task đã nhận hoàn tất hoặc hết timeout |
| Transaction manager | Cho transaction hiện tại hoàn tất trước khi đóng datasource |
| Database connection pool | Đóng sau khi worker/transaction không còn dùng |
| HTTP client/broker connection | Đóng sau khi request/consumer hoàn tất |
| Telemetry/logging | Flush buffer có giới hạn rồi đóng exporter/appender |

Spring sẽ xử lý dependency bean và destruction callback theo lifecycle của context, nhưng custom component cần được đăng ký và cấu hình đúng. Nếu tự quản lý một thread hoặc native resource ngoài Spring, hãy cung cấp một bean lifecycle để đóng nó có thứ tự.

Không đóng datasource trong một shutdown hook độc lập chạy song song với Spring. Điều đó có thể khiến worker vẫn đang ghi dữ liệu nhưng connection pool đã bị đóng.

## 14. Tính ngân sách thời gian shutdown

Container runtime chỉ chờ process trong một khoảng thời gian hữu hạn. Ngân sách tổng phải bao gồm các công việc thực sự diễn ra:

\[
T_{\text{total}} =
T_{\text{preStop}} +
T_{\text{drain}} +
T_{\text{lifecycle}} +
T_{\text{cleanup}} +
T_{\text{margin}}
\]

Trong đó:

- `T_preStop`: thời gian chạy hook `preStop` nếu có.
- `T_drain`: thời gian chờ load balancer/routing ngừng gửi traffic mới tới instance.
- `T_lifecycle`: thời gian dừng các Spring lifecycle phase; phần này bao gồm web server chờ request đang chạy và callback dừng worker/consumer được quản lý bằng `SmartLifecycle`.
- `T_cleanup`: đóng connection, flush buffer và giải phóng tài nguyên trong các destruction callback như `@PreDestroy`.
- `T_margin`: phần dự phòng cho scheduling, log và biến động tải.

Tổng thời gian cần nhỏ hơn `terminationGracePeriodSeconds` của Kubernetes hoặc stop timeout của container runtime.

Lưu ý `spring.lifecycle.timeout-per-shutdown-phase` là timeout cho từng phase, không phải tổng thời gian shutdown. Các callback trong cùng phase có thể chạy đồng thời; các phase tuần tự có thể làm tổng thời gian dài hơn một timeout đơn lẻ. Những khoảng `T_drain`, `T_lifecycle` và `T_cleanup` ở công thức là các khoảng thời gian thực tế, không cộng thêm một lần nữa timeout cấu hình của Spring. Đo wall-clock shutdown và tính các bước chạy tuần tự cùng phần dự phòng.

Ví dụ, nếu một phase có thể mất 20 giây và ứng dụng còn cần thời gian dừng consumer, flush telemetry và xử lý preStop, không nên đặt toàn bộ Pod grace period đúng 20 giây.

## 15. Docker gửi tín hiệu dừng tới native executable

Với Docker, `docker stop` gửi stop signal tới process chính trong container. Mặc định thường là `SIGTERM`; sau thời gian chờ được chỉ định, runtime gửi `SIGKILL` nếu process chưa kết thúc.

Ví dụ:

~~~bash
docker stop --time 45 orders-native
~~~

Container có tối đa 45 giây để thoát sau khi nhận tín hiệu dừng.

Dockerfile nên dùng exec form:

~~~dockerfile
ENTRYPOINT ["/app/application"]
~~~

Exec form giúp native executable trở thành process chính và nhận signal trực tiếp. Nếu dùng shell form như `ENTRYPOINT /app/application`, shell có thể trở thành process trung gian và việc chuyển tiếp signal phụ thuộc shell/script.

Nếu phải dùng script khởi động, hãy kết thúc script bằng `exec /app/application` để thay shell bằng process ứng dụng. Không cần thêm init process nếu container chỉ chạy một process và không có nhu cầu quản lý child process; nếu có wrapper hoặc child process, chọn init phù hợp và kiểm thử signal forwarding.

## 16. Kubernetes Pod termination hoạt động ra sao?

Khi Pod bị xóa hoặc rollout thay thế, Kubernetes bắt đầu termination flow:

1. Pod được đánh dấu đang terminating và grace-period countdown bắt đầu.
2. Nếu có `preStop`, kubelet chạy hook đó trước khi gửi signal.
3. Sau khi `preStop` hoàn tất, container runtime gửi `SIGTERM` tới process chính.
4. Ứng dụng có thời gian còn lại để graceful shutdown.
5. Khi hết `terminationGracePeriodSeconds`, process còn chạy sẽ nhận `SIGKILL`.

Mặc định `terminationGracePeriodSeconds` là 30 giây nếu không cấu hình. **Thời gian chạy preStop nằm trong cùng grace period**, không được cộng thêm ngoài thời gian đó. Nếu preStop mất 10 giây trong ngân sách 30 giây, ứng dụng chỉ còn khoảng 20 giây sau khi nhận SIGTERM.

Trong lúc termination, Kubernetes cũng cập nhật EndpointSlice để endpoint terminating không còn được xem là endpoint sẵn sàng cho traffic thông thường. Việc lan truyền thay đổi tới load balancer và client vẫn cần thời gian; ứng dụng cần xử lý request mới đến trễ trong giai đoạn chuyển tiếp.

## 17. Cấu hình Kubernetes cho Spring Boot Native Image

Ví dụ Deployment với grace period 60 giây và readiness probe:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-native
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-native
  template:
    metadata:
      labels:
        app: orders-native
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: orders
          image: example/orders:native
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_SHUTDOWN
              value: graceful
            - name: SPRING_LIFECYCLE_TIMEOUT_PER_SHUTDOWN_PHASE
              value: 20s
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Các biến môi trường Spring Boot dùng relaxed binding; tên trong ví dụ tương ứng với `server.shutdown` và `spring.lifecycle.timeout-per-shutdown-phase`. Đảm bảo Actuator readiness/liveness endpoint được bật và expose theo cấu hình bảo mật của ứng dụng.

Giá trị 60 giây và 20 giây chỉ là ví dụ. Hãy tính từ thời gian request dài nhất được hỗ trợ, các lifecycle phase, tác vụ nền và độ trễ của hạ tầng.

Không thêm `preStop: sleep 10` chỉ để kéo dài thời gian. Nếu cần drain load balancer bên ngoài, hãy dùng hook có mục đích rõ ràng và tính thời gian của hook vào cùng ngân sách termination.

## 18. Tùy chọn preStop dùng khi nào?

`preStop` chạy trước khi container nhận SIGTERM. Nó hữu ích khi cần thông báo cho một hệ thống ngoài Kubernetes hoặc yêu cầu load balancer riêng ngừng gửi traffic trước khi ứng dụng đóng.

Một `preStop` có thể là HTTP hook hoặc exec hook. Nhưng cần cân nhắc:

- Countdown của termination grace period đã bắt đầu trước khi hook chạy.
- Hook phải hoàn tất trước khi SIGTERM được gửi.
- Nếu hook treo, ứng dụng còn ít thời gian hơn để dừng.
- Run image distroless/tiny có thể không có shell hoặc curl cho exec hook.
- Nếu hook thất bại, quá trình termination vẫn có thể kết thúc cưỡng bức.

Với phần lớn service HTTP, readiness probe và cơ chế endpoint termination của Kubernetes đã là nền tảng cho traffic drain. Chỉ thêm preStop khi có yêu cầu thực tế từ load balancer, service mesh hoặc quy trình nghiệp vụ.

## 19. Kiểm tra signal handler trong GraalVM build

Với native executable, kiểm tra phiên bản GraalVM và trạng thái exit handlers trước khi điều tra Spring lifecycle.

Từ GraalVM 25, exit handlers được bật mặc định cho executable. Với các phiên bản cũ hơn, nếu builder hỗ trợ và yêu cầu signal handling, có thể thêm `--install-exit-handlers` vào native build arguments.

Gradle Native Build Tools, ví dụ cho toolchain cũ cần bật:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--install-exit-handlers")
        }
    }
}
~~~

Maven Native Build Tools:

~~~xml
<configuration>
    <buildArgs>
        <buildArg>--install-exit-handlers</buildArg>
    </buildArgs>
</configuration>
~~~

Chỉ dùng các đoạn cấu hình này khi GraalVM version của dự án cần tùy chọn. Trên GraalVM 25+, tùy chọn đã deprecated và exit handlers cho executable được bật mặc định; bỏ argument cũ giúp tránh cảnh báo không cần thiết. Kiểm tra tài liệu/release notes và log native build của đúng distribution.

Nếu build bằng Cloud Native Buildpacks, hãy xác minh phiên bản GraalVM được buildpack sử dụng và các native build arguments thực sự được truyền tới builder. Không suy luận từ JDK trên máy developer nếu builder image dùng toolchain khác.

## 20. Kiểm thử graceful shutdown với request đang chạy

Một test tốt cần chứng minh request đã bắt đầu trước khi gửi tín hiệu dừng.

Có thể tạo một endpoint chỉ dùng trong môi trường test, ví dụ `GET /test/slow?seconds=15`, endpoint này chờ có kiểm soát rồi trả response.

Quy trình:

1. Khởi động native container.
2. Gửi request tới endpoint chậm ở background.
3. Chờ log xác nhận request đã được nhận và bắt đầu xử lý.
4. Gửi `docker stop --time 45`.
5. Xác nhận request đang chạy nhận được response đầy đủ.
6. Xác nhận container kết thúc trước deadline.
7. Kiểm tra log cho thấy graceful shutdown và callback cleanup đã chạy.

Ví dụ lệnh:

~~~bash
curl --fail --silent \
  http://127.0.0.1:8080/test/slow?seconds=15 \
  > slow-response.txt &
REQUEST_PID=$!

# Chờ log/test signal xác nhận request đã bắt đầu.
docker stop --time 45 orders-native

wait "$REQUEST_PID"
cat slow-response.txt
~~~

Đoạn lệnh là skeleton; cần đồng bộ bước chờ với log hoặc test barrier để chắc chắn request đã vào server trước khi gửi stop. Không dựa vào một `sleep` ngắn rồi giả định request đã bắt đầu.

Kết quả cần quan sát:

- Request đang chạy hoàn tất trước timeout.
- Request mới không tiếp tục được nhận như traffic bình thường sau khi server bắt đầu drain.
- Log shutdown xuất hiện theo thứ tự hợp lý.
- Executor, consumer và datasource đóng theo lifecycle.
- Process kết thúc trước khi runtime buộc phải gửi SIGKILL.

## 21. Kiểm thử tình huống vượt quá timeout

Cũng cần kiểm thử trường hợp request hoặc background task dài hơn ngân sách shutdown.

Ví dụ:

- Request test chạy 60 giây nhưng Spring lifecycle phase chỉ chờ 20 giây.
- Consumer đang xử lý message lớn và không thể drain trong thời hạn.
- Một shutdown callback bị treo hoặc không gọi callback.
- `preStop` chiếm gần hết grace period.

Xác nhận hệ thống có hành vi dự đoán được:

- Request có thể bị ngắt khi hết deadline.
- Client có timeout và retry theo policy.
- Message chưa acknowledge được broker redeliver.
- Transaction đang mở được rollback khi connection/process bị đóng.
- Không có giả định rằng `@PreDestroy` sẽ chạy nếu process đã bị `SIGKILL`.

Đừng tăng timeout vô hạn để che một tác vụ bị treo. Hãy giới hạn thời gian xử lý, lưu trạng thái công việc bền vững và thiết kế retry/idempotency.

## 22. Kiểm thử shutdown trên Kubernetes

Với môi trường Kubernetes:

1. Triển khai ít nhất hai replica để traffic có nơi chuyển sang.
2. Gửi một request dài và xác nhận request bắt đầu.
3. Thực hiện rollout hoặc xóa một Pod có kiểm soát.
4. Theo dõi Pod chuyển sang `Terminating`.
5. Quan sát readiness/EndpointSlice và log ứng dụng.
6. Xác nhận request đang chạy hoàn tất trong grace period.
7. Xác nhận Pod kết thúc mà không bị timeout cưỡng bức.

Một số lệnh quan sát:

~~~bash
kubectl get pods -w
kubectl describe pod orders-native-xxxxx
kubectl logs orders-native-xxxxx
kubectl get endpointslices
~~~

Nếu Pod thuộc Deployment, controller sẽ tạo replica thay thế. Khi test, cần phân biệt log của Pod cũ đang terminating với Pod mới vừa được tạo.

Kiểm thử cả rollout update và scale down vì thời điểm traffic chuyển hướng và số replica còn lại có thể khác nhau. Không chạy bài test trên workload production nếu chưa có kế hoạch kiểm soát tác động.

## 23. Quan sát và chẩn đoán shutdown

Log là bằng chứng đầu tiên để xác định shutdown bắt đầu và dừng ở bước nào. Spring Boot có thể ghi log như:

~~~text
Commencing graceful shutdown. Waiting for active requests to complete
Graceful shutdown complete
~~~

Tên logger và nội dung cụ thể phụ thuộc web server và Spring Boot version.

Nên ghi lại:

- Thời điểm nhận SIGTERM và bắt đầu context close.
- Thời điểm web server ngừng nhận request mới.
- Số request đang chạy và thời gian drain.
- Số message consumer đang xử lý và kết quả acknowledge.
- Executor task còn tồn và thời gian chờ.
- Thời gian đóng datasource, broker, HTTP client và telemetry.
- Lý do timeout hoặc lỗi cleanup.
- Exit code và thời gian process kết thúc.

Có thể bổ sung metric như số request in-flight, số task pending, số message đang xử lý và thời gian shutdown. Không log token, payload nhạy cảm hoặc thông tin xác thực trong callback dừng.

Nếu container thoát bằng SIGKILL, thường không có log cleanup cuối cùng. Hãy đối chiếu Pod event, container exit reason, grace period và thời điểm log cuối cùng.

## 24. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Native process thoát ngay khi SIGTERM | Exit handler/signal handling không phù hợp với GraalVM version | Kiểm tra release, build output và exit handlers |
| `@PreDestroy` không chạy | Context không được đóng hoặc process bị SIGKILL | Kiểm tra signal, SpringApplication shutdown hook và container deadline |
| Request đang chạy bị ngắt | Grace period ngắn hơn thời gian request hoặc server shutdown timeout | Đo request duration và tăng ngân sách phù hợp |
| Pod bị SIGKILL sau preStop | preStop đã tiêu thụ phần lớn grace period | Tính preStop vào terminationGracePeriodSeconds |
| Message bị xử lý lặp | Process dừng trước khi ack/commit hoặc client retry | Dùng idempotency và ack sau khi xử lý thành công |
| Executor không kết thúc | Task bị block hoặc executor không chờ có giới hạn | Cấu hình await termination và timeout cho task |
| Shutdown callback không hoàn tất | `SmartLifecycle.stop(Runnable)` quên gọi callback | Gọi callback trong đường kết thúc có kiểm soát |
| Database đóng khi worker còn chạy | Thứ tự lifecycle/dependency sai | Sắp xếp phase và quan hệ phụ thuộc |
| Container không nhận SIGTERM | Shell là PID 1 hoặc không forward signal | Dùng exec-form ENTRYPOINT hoặc exec trong script |
| Ứng dụng dừng quá lâu | Nhiều lifecycle phase, hook hoặc task chờ không giới hạn | Đo từng phase và đặt deadline cụ thể |
| Không thấy log cuối | SIGKILL, crash hoặc log exporter đóng quá sớm | Kiểm tra runtime event, stdout/stderr và exit reason |

## 25. Nguyên tắc thiết kế shutdown an toàn

- Dùng shutdown hook mặc định của Spring Boot để đóng context.
- Kiểm tra exit handlers/signal handling theo GraalVM version.
- Ưu tiên `@PreDestroy` cho cleanup đồng bộ, ngắn và có giới hạn.
- Dùng `SmartLifecycle` cho consumer/worker cần dừng bất đồng bộ hoặc có thứ tự.
- Dừng nhận công việc mới trước khi drain công việc đang chạy.
- Đóng dependency sau khi thành phần sử dụng dependency đó đã dừng.
- Đặt timeout cho request, executor, consumer và từng lifecycle phase.
- Tính cả `preStop` vào Kubernetes grace period.
- Dùng exec-form entrypoint để native executable nhận signal trực tiếp.
- Test cả request đang chạy và tác vụ vượt quá timeout.
- Dùng idempotency, retry và durable queue để xử lý công việc bị gián đoạn.
- Không dựa vào shutdown hook để bảo đảm dữ liệu khi process bị SIGKILL hoặc máy bị mất điện.

## 26. Ghi nhớ

Graceful shutdown là một quy trình phối hợp giữa OS signal, Native Image runtime, shutdown hook của Spring Boot, web server, lifecycle bean và container orchestrator. Native executable vẫn có thể chạy các shutdown hook và Spring lifecycle, miễn là signal được xử lý và process có đủ thời gian trước khi bị kết thúc cưỡng bức.

Spring Boot đóng `ApplicationContext` khi shutdown hook chạy. Web server có thể ngừng nhận request mới và chờ request đang chạy trong grace period; `SmartLifecycle`, `@PreDestroy` và executor lifecycle giúp dừng worker và giải phóng dependency theo thứ tự. Kubernetes gửi SIGTERM sau `preStop` và gửi SIGKILL khi hết `terminationGracePeriodSeconds`.

Hãy thiết kế ngân sách shutdown dựa trên request dài nhất, background task, lifecycle phase, hook của orchestrator và phần dự phòng. Kiểm thử trên native executable/container thực tế, không chỉ kiểm tra callback trên JVM. **Một lần dừng an toàn cần kết thúc trước deadline của nền tảng và có phương án retry/idempotency cho công việc không thể hoàn tất.**

### Tài liệu tham khảo

- Spring Boot — Graceful Shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Spring Boot — SpringApplication, Application Exit: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework — SmartLifecycle Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- GraalVM — Native Image Compatibility Guide: https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/
- GraalVM — JDK 25 Release Notes: https://www.graalvm.org/release-notes/JDK_25/
- Java SE — Runtime and Shutdown Hooks: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html
- Kubernetes — Termination of Pods: https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/
- Kubernetes — Container Lifecycle Hooks: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/

Graceful shutdown, signal handling và lifecycle timeout phụ thuộc phiên bản Spring Boot, Spring Framework, GraalVM và container runtime. Hãy pin toolchain và kiểm thử đúng binary cùng môi trường triển khai mà dự án phát hành.
