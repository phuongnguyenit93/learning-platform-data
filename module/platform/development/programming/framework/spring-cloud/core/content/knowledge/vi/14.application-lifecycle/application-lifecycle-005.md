# Endpoint restart và trạng thái bật tắt theo mặc định

Spring Boot Actuator và Spring Cloud Context cung cấp một số endpoint có thể tác động trực tiếp đến vòng đời ứng dụng. Trong đó, `/actuator/restart` có thể đóng rồi khởi động lại `ApplicationContext`; `/actuator/pause` và `/actuator/resume` điều khiển các thành phần có hỗ trợ tạm dừng/tiếp tục; còn `/actuator/shutdown` yêu cầu ứng dụng kết thúc.

Các endpoint này có mức ảnh hưởng khác nhau và không cùng một cơ chế. `restart`, `pause` và `resume` thuộc **Spring Cloud Context**; `shutdown` là endpoint của **Spring Boot Actuator**. Việc một endpoint có implementation, được bật, được expose qua HTTP và được cấp quyền gọi là những điều kiện riêng. Vì vậy, không thể kết luận endpoint sẽ truy cập được chỉ từ việc thấy tên endpoint trong tài liệu hoặc thêm một dòng cấu hình expose.

Bài học thuộc chương **Vòng đời ứng dụng** của module **SPRING_CLOUD_CORE**. Phạm vi tập trung vào các nền tảng Spring Cloud dùng chung, vòng đời `ApplicationContext`, cấu hình bên ngoài, cách quản trị dịch vụ và những giới hạn khi vận hành nhiều instance.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt restart, pause, resume, shutdown và refresh.
2. Mô tả vai trò của Spring Cloud `RestartEndpoint` và các endpoint con.
3. Xác định trạng thái mặc định của restart, pause/resume và shutdown.
4. Phân biệt endpoint được tạo, được cấp quyền truy cập và được expose qua HTTP/JMX.
5. Cấu hình endpoint theo phiên bản Spring Boot 3.x hoặc 4.x.
6. Gọi endpoint bằng HTTP method phù hợp và xác minh kết quả.
7. Giải thích tác động của restart/shutdown lên `ApplicationContext`, JVM và các replica.
8. Thiết kế quyền quản trị, graceful shutdown, kiểm thử và giám sát phù hợp.

## 2. Bốn thao tác vòng đời không giống nhau

| Thao tác | Endpoint | Thành phần | Tác động chính |
| --- | --- | --- | --- |
| Restart context | `/actuator/restart` | Spring Cloud Context | Đóng `ApplicationContext` hiện tại và khởi động lại context |
| Pause | `/actuator/pause` | Spring Cloud Context | Gọi `pause()` trên các `PauseHandler` được đăng ký |
| Resume | `/actuator/resume` | Spring Cloud Context | Gọi `resume()` trên các `PauseHandler` được đăng ký |
| Shutdown | `/actuator/shutdown` | Spring Boot Actuator | Đóng context và kết thúc ứng dụng; chỉ hỗ trợ khi chạy dạng executable JAR |
| Refresh cấu hình | `/actuator/refresh` | Spring Cloud Context | Nạp lại cấu hình theo cơ chế refresh và làm mới các bean phù hợp |

**Restart không phải refresh.** Refresh giữ context đang chạy và cập nhật cấu hình/bean theo cơ chế của Spring Cloud. Restart tạo lại context, do đó nhiều bean và resource sẽ đi qua lifecycle khởi tạo từ đầu.

**Pause không phải shutdown.** Pause chỉ điều khiển những thành phần có `PauseHandler`; nó không mặc nhiên ngừng toàn bộ HTTP server, đóng context hay kết thúc JVM.

**Shutdown không tự khởi động lại ứng dụng.** Sau khi process kết thúc, nền tảng triển khai như Kubernetes, systemd hoặc một process supervisor có thể khởi động lại process theo chính sách riêng.

~~~mermaid
flowchart TD
    A[Ứng dụng đang chạy] --> B{Thao tác quản trị}
    B -->|restart| C[Đóng ApplicationContext]
    C --> D[Tạo và khởi động ApplicationContext mới]
    D --> A
    B -->|pause| E[Gọi PauseHandler.pause]
    E --> F[Thành phần được hỗ trợ tạm dừng]
    F -->|resume| G[Gọi PauseHandler.resume]
    G --> A
    B -->|shutdown| H[Đóng ApplicationContext]
    H --> I[Ứng dụng kết thúc]
    B -->|refresh| J[Cập nhật Environment và bean phù hợp]
    J --> A
~~~

Sơ đồ mô tả tác động khái quát. Việc một thao tác thực sự điều khiển thành phần nào còn phụ thuộc endpoint có sẵn, handler được đăng ký và cách ứng dụng cấu hình.

## 3. Trạng thái bật/tắt mặc định

### 3.1. Bảng tổng quan

Tài liệu Spring Cloud Commons 5.0.4 hiện hành mô tả `/actuator/restart` là **disabled by default**. `/actuator/pause` và `/actuator/resume` chỉ được tạo khi có `RestartEndpoint`, vì vậy chúng cũng không khả dụng theo cấu hình mặc định khi restart endpoint chưa được bật.

Spring Boot Actuator mô tả `/actuator/shutdown` là **disabled by default**. Với Spring Boot 4.x, quyền truy cập mặc định của shutdown endpoint là `none`.

| Endpoint | Chủ sở hữu | Mặc định theo tài liệu hiện hành | Điều kiện quan trọng |
| --- | --- | --- | --- |
| `restart` | Spring Cloud Context | Tắt | Phải bật quyền/enable endpoint; cần Actuator và Spring Cloud Context |
| `pause` | Spring Cloud Context | Không khả dụng khi `RestartEndpoint` bị tắt | Cần `RestartEndpoint` và `PauseHandler` phù hợp để có tác dụng |
| `resume` | Spring Cloud Context | Không khả dụng khi `RestartEndpoint` bị tắt | Cần `RestartEndpoint` và `PauseHandler` phù hợp để có tác dụng |
| `shutdown` | Spring Boot Actuator | Tắt | Cần bật endpoint, cho phép write access và expose đúng giao thức; chỉ hoạt động với executable JAR |
| `refresh` | Spring Cloud Context | Phụ thuộc cấu hình endpoint của release đang dùng | Không thực hiện restart toàn bộ context |

**Chú ý về phiên bản:** trạng thái và cách cấu hình endpoint đã thay đổi qua các thế hệ Spring Boot/Spring Cloud. Một số tài liệu hoặc metadata cũ có thể ghi `restart.enabled=true` mặc định. Với dự án đang dùng, luôn đối chiếu tài liệu của đúng Spring Cloud release train và Spring Boot version. Bảng trên mô tả tài liệu Spring Cloud Commons 5.0.4 và Spring Boot 4.x hiện hành tại thời điểm biên soạn.

### 3.2. Vì sao phải kiểm tra nhiều điều kiện?

Để một endpoint được gọi qua HTTP, ít nhất cần kiểm tra:

1. **Có implementation:** dependency cung cấp endpoint có trong runtime classpath và auto-configuration phù hợp được kích hoạt.
2. **Endpoint khả dụng:** endpoint không bị tắt hoặc bị giới hạn quyền truy cập.
3. **Được expose:** công nghệ HTTP/JMX được phép công bố endpoint.
4. **Được phép gọi:** Spring Security, firewall, management port và network policy không chặn request.
5. **Đúng HTTP method:** thao tác thay đổi trạng thái thường dùng `POST`.

~~~mermaid
flowchart TD
    A[Endpoint có implementation?] -->|Không| X[Không có endpoint]
    A -->|Có| B[Endpoint enabled / access được phép?]
    B -->|Không| Y[Endpoint không khả dụng]
    B -->|Có| C[Đã expose qua HTTP hoặc JMX?]
    C -->|Không| Z[Không có đường truy cập tương ứng]
    C -->|Có| D[Authentication và authorization cho phép?]
    D -->|Không| Q[401 / 403 hoặc bị chặn]
    D -->|Có| E[Endpoint có thể nhận request]
~~~

Không nên dùng một lỗi HTTP duy nhất để kết luận nguyên nhân. `404` có thể do endpoint chưa tồn tại hoặc chưa expose; `401`/`403` thường liên quan xác thực/phân quyền; `405` có thể do dùng sai HTTP method.

## 4. `/actuator/restart` của Spring Cloud Context

### 4.1. Chức năng

`RestartEndpoint` cho phép đóng `ApplicationContext` hiện tại và khởi động lại context trong cùng ứng dụng. Endpoint được cung cấp bởi Spring Cloud Context và tích hợp với Spring Boot Actuator.

Một lần restart context thường làm các thành phần sau đi qua lifecycle mới:

- Bean singleton được hủy và tạo lại.
- Các callback như `@PreDestroy`, `DisposableBean` hoặc `destroyMethod` được thực hiện khi bean/context đóng.
- Cấu hình và auto-configuration được xử lý lại khi context khởi động.
- Các connection, client, scheduler hoặc listener được quản lý bởi context có thể được khởi tạo lại.
- Các runner và listener startup có thể được gọi lại theo lifecycle của lần khởi động mới.

`restart` không thay thế JVM hoặc executable JAR. Process có thể tiếp tục tồn tại trong cùng PID, trong khi `ApplicationContext` được tạo lại. Nó cũng không tự triển khai phiên bản artifact mới; muốn thay đổi classpath hoặc binary, cần build/deploy lại ứng dụng.

### 4.2. Khi nào cân nhắc restart?

Restart context có thể hữu ích khi:

- Một thay đổi chỉ có hiệu lực lúc khởi tạo bean và không có cơ chế refresh an toàn.
- Một thành phần cần được tái tạo theo cấu hình mới.
- Cần kiểm thử hành vi startup trong môi trường được kiểm soát.
- Ứng dụng có yêu cầu vận hành cụ thể cho phép tạo lại context mà không kết thúc JVM.

Không nên xem restart là công cụ sửa mọi lỗi. Nếu lỗi nằm ở JVM, classpath, native library, thread ngoài Spring, process state hoặc resource không thể tạo lại an toàn, cần restart process hoặc triển khai lại bằng nền tảng quản lý process.

### 4.3. Restart chỉ tác động đến context của instance nhận request

Nếu ứng dụng có nhiều replica, gọi endpoint trên một instance chỉ restart context trong process đó. Các instance còn lại không tự restart.

Ví dụ:

~~~text
orders-service-1 -> JVM 1 -> ApplicationContext 1
orders-service-2 -> JVM 2 -> ApplicationContext 2
orders-service-3 -> JVM 3 -> ApplicationContext 3
~~~

Gọi `POST /actuator/restart` trên `orders-service-1` không đồng nghĩa `orders-service-2` và `orders-service-3` cũng restart. Cần orchestration hoặc quy trình rollout riêng nếu muốn tác động nhiều replica.

## 5. Bật restart endpoint

### 5.1. Spring Boot 3.x: thuộc tính `enabled`

Với các phiên bản Spring Boot 3.x còn dùng cơ chế `enabled`, có thể bật endpoint bằng:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,restart,pause,resume
~~~

`management.endpoint.restart.enabled=true` cho phép Spring Boot Actuator tạo endpoint restart. `management.endpoints.web.exposure.include` công bố các endpoint được chọn qua HTTP.

Từ Spring Boot 3.4, mô hình quản lý access mới được bổ sung và thuộc tính `enabled` đã bị deprecated để chuyển sang `management.endpoint.<id>.access`. Khi dùng Boot 3.4/3.5, nên ưu tiên cú pháp access nếu dự án và dependency hỗ trợ; không sao chép cấu hình `enabled` cũ mà không kiểm tra cảnh báo deprecated.

### 5.2. Spring Boot 4.x: dùng `access`

Trong Spring Boot 4.x, có thể cấu hình quyền truy cập endpoint bằng `management.endpoint.<id>.access`:

~~~yaml
management:
  endpoint:
    restart:
      access: unrestricted
    pause:
      access: unrestricted
    resume:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,info,restart,pause,resume
~~~

Các mức access thường gặp:

- `none`: endpoint không được truy cập và có thể bị loại khỏi context.
- `read-only`: chỉ cho phép thao tác đọc.
- `unrestricted`: cho phép các thao tác mà endpoint cung cấp, bao gồm write operation.

`restart`, `pause` và `resume` là thao tác thay đổi trạng thái nên cần write access. `read-only` không đủ để thực hiện các lệnh này.

Nếu ứng dụng đặt `management.endpoints.access.default=none`, phải cấp quyền riêng cho endpoint cần dùng. Đồng thời, `management.endpoints.access.max-permitted` có thể giới hạn mức cao nhất; đặt giới hạn này thành `none` sẽ ngăn việc mở lại endpoint bằng cấu hình riêng.

### 5.3. Chỉ expose endpoint thật sự cần dùng

Ví dụ trên expose một danh sách cụ thể. Không nên cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
~~~

trên production chỉ để tiện thao tác. Endpoint quản trị có thể cung cấp thông tin nhạy cảm hoặc thay đổi trạng thái ứng dụng. Hãy giới hạn exposure, đặt management port riêng nếu phù hợp và bảo vệ bằng xác thực/phân quyền.

### 5.4. Gọi restart bằng HTTP POST

Đường dẫn mặc định:

~~~http
POST /actuator/restart
~~~

Ví dụ:

~~~bash
curl -X POST http://localhost:8080/actuator/restart
~~~

Nếu management base path hoặc port được tùy chỉnh, URL phải thay đổi tương ứng. Không dùng `GET` cho thao tác restart.

Một lệnh gọi thành công chỉ xác nhận request đã được xử lý ở mức endpoint. Sau đó cần quan sát log startup, readiness, health và kết nối dependency để xác nhận context mới đã sẵn sàng.

## 6. `/actuator/pause` và `/actuator/resume`

### 6.1. Vai trò của PauseHandler

Spring Cloud Context cung cấp abstraction `PauseHandler` để các thành phần đăng ký hành vi tạm dừng và tiếp tục. Hai endpoint tương ứng gọi các phương thức `pause()` và `resume()` trên những handler có trong context.

Với Spring Integration, Spring Cloud có thể cung cấp handler tích hợp cho các component triển khai `Pausable`. Ứng dụng cũng có thể đăng ký `PauseHandler` riêng để điều khiển scheduler, consumer hoặc thành phần nội bộ có hỗ trợ pause/resume.

Ví dụ khái niệm:

~~~java
public interface PauseHandler {
    void pause();

    void resume();
}
~~~

Đây là hợp đồng hành vi để minh họa. Khi viết implementation, hãy dùng đúng package/API của Spring Cloud Commons version mà dự án đang sử dụng.

### 6.2. Pause không tự dừng toàn bộ ứng dụng

Nếu ứng dụng không có `PauseHandler` phù hợp, endpoint pause/resume có thể không tạo ra thay đổi hữu ích. Việc endpoint tồn tại không có nghĩa mọi request HTTP, scheduler, Kafka consumer hay background worker đều tự động bị dừng.

Hãy xác định rõ thành phần nào cần pause:

- Consumer nhận message.
- Scheduled task.
- Integration flow.
- Công việc nền có thể dừng an toàn.
- Tác vụ nội bộ cần drain trước khi bảo trì.

Không dùng pause thay cho readiness management hoặc load balancer drain nếu các thành phần đó chưa được tích hợp với handler tương ứng.

### 6.3. Quan hệ phụ thuộc với RestartEndpoint

Trong Spring Cloud Commons hiện hành, `PauseEndpoint` và `ResumeEndpoint` được tạo khi có bean `RestartEndpoint`. Vì vậy, khi restart endpoint bị tắt, pause và resume cũng bị vô hiệu hóa theo quan hệ phụ thuộc này.

Điều đó giải thích vì sao chỉ đặt thuộc tính expose `pause,resume` chưa đủ. Cần bật điều kiện để `RestartEndpoint` được tạo trước.

### 6.4. Gọi pause và resume

~~~http
POST /actuator/pause
POST /actuator/resume
~~~

Ví dụ:

~~~bash
curl -X POST http://localhost:8080/actuator/pause
curl -X POST http://localhost:8080/actuator/resume
~~~

Hai thao tác nên được kiểm thử trên từng handler. Sau khi pause, xác minh consumer hoặc scheduler thật sự ngừng nhận công việc mới; sau resume, xác minh chúng tiếp tục hoạt động và không xử lý trùng hoặc bỏ sót message.

### 6.5. Khác biệt theo release train

Một số tài liệu Spring Cloud cũ mô tả pause/resume theo các phương thức `Lifecycle.stop()` và `Lifecycle.start()` trên `ApplicationContext`. Tài liệu Spring Cloud Commons 5.0.4 hiện hành mô tả endpoint gọi `pause()`/`resume()` trên `PauseHandler` beans, trong đó có handler cho Spring Integration `Pausable`.

Khi nâng cấp, hãy đọc đúng reference guide và Javadoc của release train. Đừng giả định một handler hoặc semantics từ dự án cũ vẫn hoạt động giống hệt trong phiên bản mới.

## 7. `/actuator/shutdown` của Spring Boot Actuator

### 7.1. Đây là endpoint khác với restart

`shutdown` thuộc Spring Boot Actuator. Khi được bật và gọi hợp lệ, endpoint yêu cầu ứng dụng đóng `ApplicationContext` và kết thúc.

Khác với restart:

- `shutdown` không tạo context mới.
- Ứng dụng kết thúc sau khi context đóng.
- JVM/process có thể kết thúc khi không còn thành phần giữ process sống.
- Nền tảng bên ngoài có thể khởi động lại process theo restart policy, nhưng đó là trách nhiệm của nền tảng.

Endpoint này chỉ hoạt động khi ứng dụng được đóng gói/chạy theo dạng executable JAR theo tài liệu Spring Boot.

### 7.2. Mặc định và cấu hình

Spring Boot mô tả shutdown endpoint là disabled by default.

Với Spring Boot 3.x trước cơ chế access mới, có thể bật bằng:

~~~yaml
management:
  endpoint:
    shutdown:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,shutdown
~~~

Từ Spring Boot 3.4 và trong Boot 4.x, nên dùng access property. Ví dụ:

~~~yaml
management:
  endpoint:
    shutdown:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: health,shutdown
~~~

Trong Boot 4.x, `management.endpoint.shutdown.access` mặc định là `none`. Chỉ thay thành `unrestricted` khi đã có xác thực, phân quyền và giới hạn mạng phù hợp.

### 7.3. Gọi shutdown

~~~http
POST /actuator/shutdown
~~~

Ví dụ:

~~~bash
curl -X POST http://localhost:8080/actuator/shutdown
~~~

Sau request, ứng dụng bắt đầu đóng context. Kết nối HTTP có thể kết thúc trong lúc server đang dừng; không dùng việc client nhận được một response cụ thể làm bằng chứng duy nhất rằng process đã tắt hoàn toàn.

### 7.4. Graceful shutdown

Spring Boot hỗ trợ graceful shutdown cho các embedded web server phổ biến. Khi context đóng, server ngừng nhận request mới và cho request đang xử lý một khoảng thời gian hoàn tất theo cấu hình timeout.

Ví dụ:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Graceful shutdown là cơ chế xử lý request trong quá trình dừng ứng dụng; nó không tự expose `/actuator/shutdown` và cũng không tự bật endpoint này. Cần phân biệt hai cấu hình.

## 8. Phân biệt restart endpoint với Spring Boot DevTools Restart

Spring Boot DevTools có chức năng tự restart ứng dụng trong môi trường phát triển khi classpath thay đổi. Đây là cơ chế developer productivity, khác với endpoint restart của Spring Cloud Context.

| Tiêu chí | Spring Cloud `/actuator/restart` | Spring Boot DevTools restart |
| --- | --- | --- |
| Mục tiêu | Quản trị vòng đời context khi ứng dụng chạy | Tự khởi động lại khi phát hiện thay đổi trong môi trường phát triển |
| Cách kích hoạt | HTTP/JMX write operation | Theo dõi thay đổi classpath hoặc trigger file |
| Dependency | Spring Cloud Context và Actuator | `spring-boot-devtools` |
| Môi trường phù hợp | Có thể dùng trong môi trường được quản trị và bảo vệ | Chủ yếu dành cho development |
| Cấu hình liên quan | `management.endpoint.restart.*` | `spring.devtools.restart.*` |
| Thay đổi binary production | Không tự deploy artifact mới | Không phải cơ chế triển khai production |

Không nhầm `spring.devtools.restart.enabled=true` với `management.endpoint.restart.enabled=true`. Hai thuộc tính điều khiển hai tính năng khác nhau.

## 9. Dependency và điều kiện runtime

### 9.1. Thành phần cần có

Để sử dụng các endpoint Spring Cloud Context:

- Spring Boot Actuator phải có trên runtime classpath.
- Spring Cloud Context phải có thông qua dependency phù hợp, thường được kéo vào bởi các Spring Cloud starter.
- Spring Cloud release train phải tương thích với Spring Boot.
- Auto-configuration endpoint phải được kích hoạt và không bị exclude.
- Với pause/resume, phải có `RestartEndpoint` và handler phù hợp.

Ví dụ Maven dependencies minh họa:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

Đoạn trên là ví dụ tối thiểu theo mục đích minh họa. Trong một ứng dụng có starter tính năng khác, Spring Cloud Context có thể đã nằm trong cây phụ thuộc. Hãy kiểm tra `dependency:tree` và dùng Spring Cloud BOM tương thích thay vì tự đặt version cho từng module.

### 9.2. Kiểm tra endpoint được tạo

Có thể dùng Actuator `beans` hoặc `conditions` trong môi trường được bảo vệ để kiểm tra auto-configuration và bean endpoint. Endpoint `mappings` có thể giúp xem đường dẫn HTTP đã được map hay chưa.

Không expose `beans`, `conditions` hoặc `mappings` ra mạng công khai chỉ để debug. Có thể dùng startup log hoặc test context nếu không muốn mở endpoint quản trị.

## 10. Kiểm thử các endpoint vòng đời

### 10.1. Kiểm tra restart

Kịch bản tích hợp nên:

1. Khởi động ứng dụng trong môi trường test có management endpoint riêng.
2. Xác nhận endpoint restart chưa khả dụng khi giữ mặc định.
3. Bật endpoint trong cấu hình test và expose qua HTTP.
4. Gọi `POST /actuator/restart`.
5. Quan sát log đóng context và log startup mới.
6. Kiểm tra readiness, bean khởi tạo lại và kết nối dependency.
7. Xác nhận PID/process không bị nhầm là đã restart nếu chỉ context được tạo lại.

Không gọi restart trong một test suite chia sẻ context mà các test khác vẫn đang dùng. Nên chạy test trong process riêng hoặc kiểm soát lifecycle rõ ràng.

### 10.2. Kiểm tra pause/resume

Tạo một `PauseHandler` có bộ đếm hoặc một integration component có thể quan sát trạng thái:

- Sau `POST /actuator/pause`, handler nhận đúng một lệnh pause.
- Thành phần được điều khiển ngừng nhận công việc mới.
- Sau `POST /actuator/resume`, handler tiếp tục hoạt động.
- Gọi pause/resume nhiều lần không gây trạng thái sai hoặc resource leak.
- Khi không có handler, test phải phản ánh rằng endpoint không điều khiển thành phần nghiệp vụ nào.

### 10.3. Kiểm tra shutdown

Shutdown endpoint nên được kiểm thử trong một process độc lập:

1. Khởi động executable JAR với shutdown endpoint được bật và expose.
2. Gửi `POST /actuator/shutdown`.
3. Xác nhận context đóng, callback resource chạy và process kết thúc.
4. Kiểm tra graceful shutdown theo timeout đã cấu hình.
5. Xác nhận process supervisor có hoặc không khởi động lại process theo chính sách mong muốn.

Không chạy test shutdown trong cùng JVM đang điều phối toàn bộ test suite.

### 10.4. Kiểm tra endpoint không được expose

Nếu endpoint tồn tại nhưng không expose qua HTTP, request HTTP không thể truy cập endpoint đó. Test nên xác nhận cả ba trạng thái:

- Endpoint disabled hoặc access `none`.
- Endpoint available nhưng không nằm trong `web.exposure.include`.
- Endpoint available, exposed và được cấp quyền.

Điều này giúp tránh việc test chỉ kiểm tra response HTTP mà không biết điều kiện nào đã tạo ra kết quả.

## 11. Bảo mật endpoint quản trị

Restart, pause, resume và shutdown có thể làm gián đoạn nghiệp vụ hoặc thay đổi trạng thái hệ thống. Chúng phải được xem là API quản trị nhạy cảm.

Khuyến nghị:

- Chỉ expose endpoint thật sự cần thiết.
- Dùng authentication và role riêng cho operator.
- Giới hạn management port vào mạng quản trị.
- Dùng TLS khi truy cập qua mạng.
- Không cấp quyền restart/shutdown cho service account thông thường.
- Ghi audit người gọi, thời điểm, endpoint và instance đích.
- Không expose toàn bộ Actuator bằng wildcard.
- Tách môi trường dev, staging và production về network/credentials.
- Thử nghiệm quyền truy cập trong pipeline để tránh cấu hình production vô tình mở endpoint.

Nếu Spring Security có mặt, kiểm tra `SecurityFilterChain` tùy chỉnh. Một cấu hình security do ứng dụng tự khai báo có thể thay thế quy tắc Actuator mặc định; cần bảo đảm write operation chỉ được cấp cho role quản trị phù hợp.

## 12. Tác động trong hệ thống nhiều instance

### 12.1. Endpoint tác động lên instance nhận request

Mỗi replica chạy JVM và `ApplicationContext` riêng. Gọi restart hoặc pause trên một replica không tự áp dụng lên các replica khác.

Nếu cần restart nhiều instance, hãy dùng orchestration rollout hoặc công cụ quản lý deployment. Nếu cần shutdown một instance, phải phối hợp với load balancer để ngừng gửi traffic trước khi process kết thúc.

### 12.2. Restart nhiều replica cùng lúc có thể gây gián đoạn

Restart toàn bộ replica đồng thời có thể khiến service không còn instance sẵn sàng. Một quy trình an toàn hơn thường là:

1. Chọn một instance hoặc một nhóm nhỏ.
2. Drain traffic khỏi nhóm đó.
3. Thực hiện restart/shutdown theo kế hoạch.
4. Chờ readiness và health đạt yêu cầu.
5. Tiếp tục với nhóm kế tiếp.
6. Dừng rollout nếu error rate hoặc latency vượt ngưỡng.

Restart endpoint không thay thế rolling deployment và không cung cấp orchestration tự động.

### 12.3. Service discovery và trạng thái đăng ký

Nếu ứng dụng đăng ký với Eureka, Consul hoặc một registry khác, hãy kiểm tra lifecycle đăng ký/deregister khi context dừng và khởi động lại. Không giả định registry luôn loại bỏ instance cũ ngay lập tức hoặc mọi consumer cập nhật danh sách tức thời.

Nên quan sát:

- Instance có được deregister hoặc đánh dấu không sẵn sàng khi dừng không?
- Instance mới có đăng ký lại sau restart không?
- Health check và lease/heartbeat có phục hồi không?
- Load balancer có tiếp tục gửi request tới instance đang restart không?

Các hành vi này phụ thuộc provider discovery, service registry và cấu hình health/lifecycle.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `404` ở `/actuator/restart` | Endpoint chưa được tạo hoặc chưa expose | Kiểm tra Spring Cloud Context, điều kiện enable/access và exposure |
| Restart vẫn không khả dụng dù đã expose | Endpoint bị disabled by default | Bật endpoint bằng thuộc tính phù hợp với Boot version |
| Pause/resume không xuất hiện | `RestartEndpoint` chưa được tạo hoặc endpoint con chưa available | Kiểm tra restart access và điều kiện bean |
| Pause trả thành công nhưng worker vẫn chạy | Không có `PauseHandler` điều khiển worker đó | Kiểm tra handler và integration component |
| Dùng `GET` nhận `405` | Endpoint là write operation | Dùng `POST` |
| Shutdown trả `404` | Shutdown endpoint đang disabled hoặc không có trong runtime | Kiểm tra Actuator, access/enabled và executable JAR |
| Shutdown không truy cập được dù đã expose | Boot 4 mặc định `shutdown.access=none` hoặc security chặn | Cấp access phù hợp và kiểm tra authorization |
| Restart làm request lỗi | Bean khởi tạo lại thất bại hoặc dependency chưa sẵn sàng | Đọc startup log, health và lifecycle callbacks |
| Restart một replica nhưng service vẫn có request lỗi | Load balancer vẫn gửi traffic hoặc replica khác không đủ capacity | Drain traffic và rollout theo nhóm |
| Cấu hình endpoint cũ không có tác dụng | Dùng `enabled` ở phiên bản đã chuyển sang access model | Đọc property metadata của Boot version |
| Shutdown endpoint không kết thúc process như mong đợi | Không chạy executable JAR hoặc process supervisor quản lý riêng | Kiểm tra cách đóng gói và runtime |

## 14. Quy trình xác minh endpoint trong một dự án

Khi một endpoint vòng đời không hoạt động, kiểm tra theo thứ tự:

1. Xác nhận Spring Boot và Spring Cloud release train đang dùng.
2. Xác nhận Actuator và Spring Cloud Context có trên runtime classpath.
3. Kiểm tra endpoint có được auto-configure và bean tương ứng có tồn tại.
4. Kiểm tra thuộc tính enable/access theo đúng thế hệ Boot.
5. Kiểm tra `management.endpoints.web.exposure.include` và `exclude`.
6. Kiểm tra management port, base path và network binding.
7. Kiểm tra HTTP method (`POST`) và Spring Security.
8. Kiểm tra endpoint có handler/lifecycle component thực sự để điều khiển.
9. Kiểm tra log, health và trạng thái instance sau thao tác.

Có thể sử dụng các lệnh kiểm tra dependency:

~~~bash
# Maven: xem Spring Cloud Context và Actuator có trong runtime tree
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-context,org.springframework.boot:spring-boot-actuator

# Gradle: xem runtime dependencies
./gradlew dependencies --configuration runtimeClasspath
~~~

Kết quả cần được đối chiếu với BOM và release train của ứng dụng.

## 15. Bài tập vận dụng

**Bài tập 1 — Mặc định endpoint.** Tạo ứng dụng có Actuator và Spring Cloud Context. Giữ cấu hình mặc định rồi kiểm tra `/actuator/restart`, `/actuator/pause`, `/actuator/resume` và `/actuator/shutdown`. Ghi rõ endpoint nào không được tạo, endpoint nào chưa expose và nguyên nhân.

**Bài tập 2 — Bật restart.** Với Spring Boot 3.x, cấu hình `management.endpoint.restart.enabled=true`. Với Boot 4.x, dùng `management.endpoint.restart.access=unrestricted`. Expose endpoint và xác minh `POST /actuator/restart` làm context khởi động lại.

**Bài tập 3 — PauseHandler.** Tạo một handler cho worker giả lập. Gọi pause và resume, kiểm tra trạng thái worker và xử lý lời gọi lặp.

**Bài tập 4 — Shutdown.** Bật shutdown endpoint trong một executable JAR test. Gọi POST, xác nhận context đóng và process kết thúc. So sánh với việc dừng process bằng SIGTERM.

**Bài tập 5 — Graceful shutdown.** Cấu hình timeout cho shutdown phase. Gửi request kéo dài, sau đó kích hoạt shutdown và quan sát request hiện tại, request mới và thời gian process kết thúc.

**Bài tập 6 — Bảo mật.** Tạo role `OPS_ADMIN` chỉ được gọi các endpoint vòng đời. Xác nhận user không có role nhận `403` và health endpoint vẫn hoạt động theo chính sách đã định.

**Bài tập 7 — Nhiều replica.** Chạy hai instance của cùng service. Restart một instance và quan sát instance còn lại, service discovery, load balancer và readiness. Thiết kế rollout để không mất toàn bộ capacity.

**Bài tập 8 — So sánh phiên bản.** Chạy cùng một ví dụ trên Spring Boot 3.x và 4.x. So sánh thuộc tính `enabled` với `access`, default exposure và cách xử lý shutdown endpoint.

## 16. Ghi nhớ và nguồn tra cứu

- `/actuator/restart` thuộc Spring Cloud Context và bị tắt theo mặc định trong tài liệu Spring Cloud Commons hiện hành.
- `/actuator/pause` và `/actuator/resume` phụ thuộc vào `RestartEndpoint`; chúng gọi các `PauseHandler` đã đăng ký.
- Pause/resume không tự động dừng toàn bộ web server hoặc mọi worker trong ứng dụng.
- `/actuator/shutdown` thuộc Spring Boot Actuator, bị tắt theo mặc định và chỉ hỗ trợ executable JAR.
- Boot 3.x cũ dùng thuộc tính `management.endpoint.<id>.enabled`; Boot 3.4+ và Boot 4.x chuyển sang mô hình `management.endpoint.<id>.access`.
- Endpoint có implementation, được enable/access, được expose và được cấp quyền gọi là các điều kiện riêng.
- Các thao tác thay đổi trạng thái cần HTTP `POST` và quyền quản trị phù hợp.
- Restart context không restart JVM, không deploy artifact mới và không tự tác động lên các replica khác.
- Graceful shutdown là cơ chế dừng request có kiểm soát; nó không tự bật Actuator shutdown endpoint.
- Khi vận hành nhiều instance, cần drain traffic, kiểm tra discovery/readiness và rollout theo nhóm.

Nguồn chính thức để đối chiếu theo phiên bản:

1. [Spring Cloud Commons – Application Context Services và Endpoints](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – RestartEndpointAutoConfiguration](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/autoconfigure/RefreshEndpointAutoConfiguration.java)
3. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
4. [Spring Boot Reference – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
5. [Spring Boot Reference – Developer Tools Restart](https://docs.spring.io/spring-boot/reference/using/devtools.html)
6. [Spring Boot API – Endpoint Access](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/PropertiesEndpointAccessResolver.html)
7. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
