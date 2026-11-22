# Mối liên hệ giữa cấu hình ngoài, tự cấu hình, máy chủ web và Actuator trong Spring Boot

## 1. Bức tranh tổng thể

Một ứng dụng Spring Boot không hoạt động nhờ bốn cơ chế độc lập. Chúng kết nối thành một chuỗi: **cấu hình ngoài (externalized configuration)** cung cấp giá trị theo môi trường; **tự cấu hình (auto-configuration)** dựa vào classpath, các bean sẵn có và giá trị cấu hình để quyết định thành phần cần tạo; **máy chủ web nhúng (embedded web server)** nhận và xử lý lưu lượng HTTP nếu ứng dụng là web; **Actuator** cung cấp các điểm quan sát/quản trị, thường được đăng ký lên chính hạ tầng web đó hoặc một cổng quản trị riêng.

Ví dụ, cùng một gói ứng dụng có thể được chạy ở máy phát triển với cổng 8080, ở môi trường kiểm thử với cổng 9080, và ở production với cổng 8080 nhưng chỉ cho phép truy cập `/actuator/health` từ mạng nội bộ. Mã nghiệp vụ không nhất thiết phải thay đổi: giá trị cấu hình và hạ tầng triển khai quyết định các khác biệt này.

~~~mermaid
flowchart TD
  A["Classpath: Spring Web, Actuator, thư viện khác"] --> C["Điều kiện auto-configuration"]
  B["YAML/properties, biến môi trường, JVM, CLI"] --> D["Spring Environment"]
  D --> C
  C --> E["ApplicationContext và các bean"]
  E --> F["DispatcherServlet / WebFlux và máy chủ HTTP nhúng"]
  D --> F
  E --> G["Actuator endpoints và Micrometer"]
  D --> G
  F --> H["HTTP API của ứng dụng"]
  G --> I["HTTP/JMX quản trị, sức khỏe, metrics"]
  F --> I
~~~

Sơ đồ biểu diễn quan hệ logic; trình tự khởi tạo thực tế có nhiều pha và cổng quản trị riêng có thể dùng một management context/server khác.

| Thành phần | Trả lời câu hỏi | Đầu vào chính | Tác động thấy được |
| --- | --- | --- | --- |
| Externalized configuration | Ứng dụng nên chạy với thông số nào? | `application.yaml`, profile, biến môi trường, tham số JVM/CLI | Cổng, địa chỉ bind, tính năng, log, cấu hình quản trị |
| Auto-configuration | Với thư viện, bean và cấu hình hiện có, Boot nên tạo những bean nào? | Classpath, `Environment`, điều kiện `@Conditional...`, bean do ứng dụng khai báo | MVC/WebFlux, web server factory, JSON converter, actuator infrastructure... |
| Embedded web server | Yêu cầu HTTP đến và được xử lý ở đâu? | Web stack, web server implementation, `server.*` | Listener HTTP, routing, request/response, cổng và context path |
| Actuator | Hệ thống đang sống, sẵn sàng và vận hành ra sao? | Starter Actuator, bean, health indicators, `management.*`, Micrometer | `health`, `info`, `metrics` và các endpoint quản trị được cấp phép |

**Phân biệt quan trọng:** giá trị cấu hình không tự tạo mọi chức năng; một starter cũng không có nghĩa mọi endpoint sẽ được công khai. Auto-configuration cần điều kiện phù hợp, còn Actuator chịu thêm các quy tắc về endpoint access, HTTP exposure và bảo mật.

## 2. Cấu hình ngoài là điểm khởi đầu

Spring Boot hợp nhất nhiều `PropertySource` vào `Environment`. Nhờ đó, cùng một key có thể được dùng trong mã Java, trong cơ chế binding `@ConfigurationProperties`, hoặc bởi auto-configuration có sẵn. Các nguồn thường gặp:

- `application.yaml`/`application.properties` đóng gói trong JAR: giá trị mặc định đi cùng ứng dụng.
- Tệp cấu hình bên ngoài JAR và tệp theo profile: khác nhau giữa dev, test và production mà không cần build lại.
- Biến môi trường: phù hợp container và CI/CD; ví dụ `SERVER_PORT=9090` tương ứng `server.port`.
- Java system properties và tham số chạy ứng dụng: ví dụ `-Dserver.port=9090` hoặc `--server.port=9090`.
- Nguồn bổ sung (config import/config tree, secret store thông qua integration phù hợp): đưa cấu hình vận hành và bí mật ra khỏi mã nguồn.

Trong **các nguồn thông dụng theo cấu hình mặc định**, tham số dòng lệnh có độ ưu tiên cao hơn Java system properties, Java system properties cao hơn biến môi trường, biến môi trường cao hơn config data; trong config data, tệp bên ngoài JAR và tệp theo profile thường có khả năng ghi đè mặc định đóng gói. Đây là mô tả có điều kiện, không phải bảng thứ tự đầy đủ: test properties, `SPRING_APPLICATION_JSON`, `@PropertySource` và các nhóm config location còn có quy tắc riêng. Khi cần kết luận chính xác, tra mục *Externalized Configuration* của tài liệu phiên bản đang dùng.

Ví dụ:

~~~yaml
# src/main/resources/application.yaml
spring:
  application:
    name: runtime-demo

server:
  port: 8080

demo:
  message: "Xin chào từ YAML"

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

- `server.port` được dùng để cấu hình cổng HTTP của ứng dụng web.
- `spring.application.name` là thông tin tên ứng dụng; nó không tự tạo route HTTP.
- `demo.message` là cấu hình do dự án định nghĩa; ứng dụng phải tự đọc/bind giá trị đó.
- `management.endpoints.web.exposure.include` xác định các endpoint Actuator nào được phép **expose qua web**, với điều kiện endpoint được cung cấp, được phép truy cập và không bị chặn bởi bảo mật.

Khi chạy với `--server.port=9091`, thông thường lệnh CLI ghi đè `server.port: 8080` trong YAML. Cơ chế này cho phép triển khai một artifact qua nhiều môi trường.

### Profile và thời điểm áp dụng

`application-dev.yaml` hoặc `application-prod.yaml` có thể mang cấu hình theo môi trường; chọn profile bằng `spring.profiles.active` từ nguồn hợp lệ hoặc tham số `--spring.profiles.active=prod`. Việc chọn profile và đọc config data diễn ra sớm để các bean được tạo với giá trị phù hợp. Đừng giả định sửa file YAML trên đĩa sau khi ứng dụng đã khởi động thì bean, cổng HTTP hoặc auto-configuration sẽ tự đổi ngay: Boot mặc định không thực hiện hot reload cấu hình runtime như vậy; cần cơ chế refresh riêng hoặc khởi động lại.

## 3. Auto-configuration chuyển classpath + cấu hình thành hạ tầng

`@SpringBootApplication` bao gồm việc bật auto-configuration. Boot đọc các lớp auto-configuration được đăng ký bởi dependency phù hợp, rồi đánh giá các điều kiện trước khi tạo bean. Những điều kiện thường gặp:

- `@ConditionalOnClass`: thư viện cần thiết có trong classpath.
- `@ConditionalOnWebApplication`: ngữ cảnh phù hợp loại ứng dụng web.
- `@ConditionalOnMissingBean`: ứng dụng chưa cung cấp bean có vai trò tương đương, nên Boot tạo mặc định.
- `@ConditionalOnProperty`: cấu hình cho phép một nhánh tính năng.

Ví dụ, thêm dependency **Spring Web** cho ứng dụng servlet thường dẫn đến cấu hình Spring MVC, `DispatcherServlet`, mapping HTTP và web server nhúng thích hợp. Thêm **Spring Boot Actuator** cho phép Boot cấu hình nhiều endpoint, health indicator và tích hợp metrics khi điều kiện tương ứng thỏa mãn.

Một số kết quả quan trọng:

1. **Classpath tạo khả năng:** không có dependency web phù hợp thì việc đặt `server.port=8080` không đủ để tạo một HTTP server.
2. **Cấu hình điều chỉnh quyết định:** giá trị `spring.main.web-application-type=none` có thể khiến ứng dụng không chạy như web, dù classpath có thư viện web; nhiều nhánh cấu hình quản trị cũng phụ thuộc các giá trị `management.*`.
3. **Bean tùy chỉnh có thể làm auto-configuration “nhường chỗ”:** Boot thường dùng `@ConditionalOnMissingBean` để tránh tạo bản mặc định trùng với bean do ứng dụng định nghĩa. Không nên kết luận mọi bean tùy chỉnh đều thay thế toàn bộ auto-configuration.
4. **Auto-configuration không thay thế code nghiệp vụ:** Controller, service, rule của domain vẫn phải do ứng dụng cung cấp.

Để tìm lý do một auto-configuration được áp dụng hoặc bị loại, có thể khởi động bằng tham số `--debug` rồi xem condition evaluation report trong log. Actuator có endpoint `conditions` dành cho tình huống điều tra chuyên sâu, nhưng endpoint đó không được mặc định mở công khai qua HTTP; chỉ kích hoạt và bảo vệ khi cần.

## 4. Máy chủ web là hạ tầng thực thi các quyết định trên

Ứng dụng Spring Boot chạy độc lập thường mang máy chủ HTTP trong chính process Java:

- **Servlet stack:** Spring MVC kết hợp máy chủ servlet nhúng như Tomcat hoặc Jetty theo dependency được chọn. `DispatcherServlet` điều phối các request tới controller.
- **Reactive stack:** Spring WebFlux có thể chạy với Reactor Netty hoặc HTTP server tương thích. Luồng xử lý reactive khác với Servlet API, dù cùng nhận HTTP.
- **Non-web:** một tiến trình batch, consumer hoặc CLI có thể không mở cổng HTTP. Sự có mặt của Spring Boot không đồng nghĩa luôn phải chạy web server.

Khi Boot khởi động web context, cấu hình máy chủ tác động tới listener và đường dẫn. Các key hay gặp là `server.port`, `server.address`, và với Servlet là `server.servlet.context-path`. Ví dụ, nếu ứng dụng Servlet dùng `server.servlet.context-path=/shop` thì route business `/api/hello` sẽ xuất hiện ở `/shop/api/hello`; khi không có cổng quản trị riêng, đường dẫn Actuator mặc định cũng chịu ảnh hưởng của context path.

**Cổng và đường dẫn không giống nhau:**

- `server.port=9090` đổi cổng nhận HTTP chính.
- `server.servlet.context-path=/shop` đổi tiền tố path của ứng dụng Servlet.
- `management.endpoints.web.base-path=/manage` đổi tiền tố endpoint quản trị từ `/actuator` sang `/manage`.
- `management.server.port=9091` có thể mở management HTTP trên cổng riêng; khi đó base path quản trị được tính trong bối cảnh management server, không đơn giản nối tiếp context path của ứng dụng.

Port 8080 chỉ là giá trị mặc định thông dụng; port thực tế có thể được ghi đè bởi config khác hoặc do hệ điều hành cấp khi đặt `server.port=0`. Nếu cổng bị chiếm và không cấu hình cổng thay thế, ứng dụng web có thể không khởi động được.

## 5. Actuator sử dụng cùng hạ tầng cấu hình và web

`spring-boot-starter-actuator` tích hợp endpoint phục vụ theo dõi và chẩn đoán; thông tin đến từ các bean trong `ApplicationContext` và từ hệ thống đang chạy. Một số endpoint tiêu biểu:

| Endpoint | Ý nghĩa | Điều cần lưu ý |
| --- | --- | --- |
| `health` | Tổng hợp tình trạng sức khỏe ứng dụng và các health indicator | Trạng thái có thể là UP/DOWN/OUT_OF_SERVICE; không đánh đồng HTTP 200 với mọi thành phần phụ thuộc luôn khỏe |
| `info` | Thông tin ứng dụng, build, Git... khi có cấu hình/contributor | Có thể rất ít dữ liệu nếu chưa khai báo contributor |
| `metrics` | Khám phá số liệu Micrometer đang được ghi nhận | Dùng để chẩn đoán; muốn lưu lâu dài cần monitoring backend/registry thích hợp |
| `env`, `configprops` | Điều tra nguồn và giá trị cấu hình/binding | Nhạy cảm; có cơ chế che giá trị và cần hạn chế quyền truy cập |
| `conditions` | Xem điều kiện auto-configuration khớp/không khớp | Hữu ích khi một bean không xuất hiện như dự kiến |

Nếu ứng dụng có web server và không tùy chỉnh base path, endpoint health thông thường nằm tại `/actuator/health`. Nếu đặt cổng management riêng, URL sẽ dùng cổng ấy. Actuator cũng có các cách expose khác HTTP (ví dụ JMX, tùy cấu hình), nên “endpoint tồn tại” không đồng nghĩa “endpoint đã mở HTTP”.

Ba lớp kiểm soát cần hiểu riêng:

1. **Có endpoint:** starter, auto-configuration và điều kiện tạo endpoint có thỏa hay không.
2. **Access/exposure:** endpoint có được phép truy cập và được expose qua HTTP/JMX hay không. Với cấu hình mặc định hiện đại, chỉ health được expose qua HTTP; `include: health,info,metrics` nới tập exposure qua web, không thay thế bước bảo mật.
3. **Security/network:** Spring Security, firewall, ingress, network policy và quyền người gọi có cho phép truy cập hay không. Khi ứng dụng tự định nghĩa `SecurityFilterChain`, chính cấu hình đó phải bao phủ cả URL Actuator thích hợp.

**Khuyến nghị production:** không expose `env`, `configprops`, `beans`, `conditions`, `heapdump` hoặc toàn bộ endpoint qua Internet công cộng chỉ để tiện debug. Giữ tập endpoint tối thiểu, bảo vệ metrics theo nhu cầu, giới hạn thông tin chi tiết của health, và cân nhắc cổng quản trị tách biệt/mạng riêng. Cấu hình `management.server.port` một mình không thay thế firewall hoặc xác thực.

### Management port và sức khỏe của ứng dụng

Khi management chạy cùng cổng với ứng dụng, endpoint được xử lý trong hạ tầng HTTP chính. Khi `management.server.port` khác `server.port`, Boot có thể tạo management context và web server riêng: điều này tách lưu lượng quản trị nhưng cũng có hệ quả khi kiểm tra sức khỏe. Một cổng quản trị vẫn phản hồi được không luôn chứng minh listener cổng business hoặc toàn bộ dependency nghiệp vụ đang hoạt động tốt. Kiểm thử readiness/liveness và route thực tế theo yêu cầu triển khai; không coi một câu trả lời từ `/actuator/health` là bằng chứng tuyệt đối cho mọi luồng chức năng.

## 6. Ví dụ chạy được: một ứng dụng, hai nhóm endpoint, nhiều nguồn cấu hình

Tạo dự án Maven từ Spring Initializr, đặt group `com.example`, artifact `runtime-demo`, chọn Java 17+ và các dependency **Spring Web** và **Spring Boot Actuator** tương ứng với phiên bản Boot được chọn. Dưới đây là hai file Java và một file YAML; các class nằm cùng package để component scan nhận đúng controller.

**File `src/main/java/com/example/runtime/RuntimeDemoApplication.java`:**

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeDemoApplication.class, args);
    }
}
~~~

**File `src/main/java/com/example/runtime/HelloController.java`:**

~~~java
package com.example.runtime;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    private final Environment environment;

    public HelloController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/api/hello")
    public String hello() {
        String name = environment.getProperty("spring.application.name", "app");
        String message = environment.getProperty("demo.message", "Hello");
        return name + ": " + message;
    }
}
~~~

**File `src/main/resources/application.yaml`:** sử dụng đúng nội dung YAML ở mục 2.

Chạy từ thư mục dự án Maven có cấu hình Spring Boot plugin:

~~~bash
mvn spring-boot:run
~~~

Trong terminal thứ hai, gọi:

~~~bash
curl -s http://localhost:8080/api/hello
curl -s http://localhost:8080/actuator/health
~~~

Trong điều kiện ứng dụng khởi động và các health indicator đều khỏe, body trả về lần lượt là:

~~~text
runtime-demo: Xin chào từ YAML
~~~

~~~json
{"status":"UP"}
~~~

Hai URL được tạo theo hai con đường khác nhau: `/api/hello` đến từ `@RestController` của ứng dụng; `/actuator/health` đến từ auto-configuration của Actuator. Chúng có thể dùng cùng web server mặc dù chức năng khác nhau.

Để thấy khả năng override mà không sửa Java/YAML, đóng phiên chạy trước, đóng gói và chạy JAR (với artifact và version mặc định của dự án ví dụ):

~~~bash
mvn -q -DskipTests package
java -jar target/runtime-demo-0.0.1-SNAPSHOT.jar --server.port=9091 --demo.message="Xin chào từ CLI"
~~~

Gọi `curl -s http://localhost:9091/api/hello` sẽ nhận body:

~~~text
runtime-demo: Xin chào từ CLI
~~~

Đồng thời, health chuyển sang `http://localhost:9091/actuator/health` vì chưa cấu hình cổng management riêng. Cổng 8080 không còn là cổng business của instance mới. Nếu tệp cấu hình/CLI của máy thực tế có override khác, hãy kiểm tra giá trị cuối cùng mà Boot nhận được.

**Mở rộng một bước:** thêm vào `application.yaml`:

~~~yaml
management:
  server:
    port: 9092
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Ở lần chạy tiếp theo với business port 9091, endpoint business vẫn nằm tại `http://localhost:9091/api/hello` còn health quản trị nằm tại `http://localhost:9092/actuator/health`. Không tự suy ra endpoint health cũng tồn tại trên business port. Trong hệ thống thực, cần cấu hình bảo vệ đường truy cập 9092 và kiểm tra firewall/network policy.

### Khi cần cấu hình nghiệp vụ có kiểu dữ liệu rõ ràng

`Environment.getProperty(...)` phù hợp để minh họa, nhưng trong ứng dụng lớn nên nhóm cấu hình thành `@ConfigurationProperties` với kiểm tra hợp lệ và binding có kiểu dữ liệu. Ví dụ `demo.message`, `demo.retry-count` và `demo.timeout` có thể được gom trong một lớp cấu hình. Đây là cấu hình **của ứng dụng**, khác với các key `server.*` hoặc `management.*` đã có auto-configuration đọc sẵn.

## 7. Theo dõi tác động khi thay đổi một đầu vào

| Thay đổi | Cấu hình/điều kiện bị ảnh hưởng | Kết quả dự kiến |
| --- | --- | --- |
| Đổi `--server.port=9091` | Environment → web server factory | HTTP business đổi cổng; Actuator cùng cổng đổi theo nếu không tách management |
| Thêm Spring Web vào app trước đó non-web | Classpath → web auto-configuration | Có thể xuất hiện Spring MVC, DispatcherServlet và embedded HTTP server |
| Bỏ dependency Actuator | Classpath → actuator auto-configuration | Các endpoint Actuator tương ứng không được tạo, dù cấu hình `management.*` còn trong file |
| Đặt `management.server.port=9092` | Management context/server config | Management HTTP có thể chạy cổng riêng |
| Chỉ thêm `metrics` vào web exposure | Quy tắc expose endpoint | `/actuator/metrics` có thể truy cập qua HTTP nếu endpoint có mặt, access và bảo mật cho phép; không tự thêm monitoring backend |
| Tự khai báo bean mà Boot chỉ tạo khi thiếu | `@ConditionalOnMissingBean` | Nhánh mặc định tương ứng có thể nhường chỗ cho bean ứng dụng |
| Đặt `spring.main.web-application-type=none` | Loại ApplicationContext | Không có HTTP listener ứng dụng thông thường; `server.port` không tự tạo server |
| Sửa file config sau khi đã start | Giá trị đã bind và hạ tầng đang chạy | Thường cần restart/refresh được thiết kế riêng để thay đổi có hiệu lực |

Đừng đánh đồng quan hệ nhân quả với sự tương quan: thay đổi giá trị YAML **chỉ** ảnh hưởng một thành phần nếu có mã ứng dụng hoặc auto-configuration đọc key ấy và áp dụng nó tại thời điểm thích hợp.

## 8. Chẩn đoán các lỗi thường gặp

**Ứng dụng chạy nhưng request đúng đường dẫn trả 404.** Kiểm tra `server.port` hiệu lực, `server.servlet.context-path` (đối với servlet), `management.endpoints.web.base-path`, và việc có đặt `management.server.port` hay không. Kiểm tra route business/Actuator bằng hai URL riêng. 404 thường khác với 401/403 do security.

**Đặt `management.endpoints.web.exposure.include=health,metrics` nhưng `/actuator/metrics` không thấy.** Kiểm tra dependency Actuator, trạng thái/điều kiện của endpoint, access, cổng và base path; tiếp theo kiểm tra xác thực và Spring Security. Exposure không phải cơ chế cấp quyền vô điều kiện. Không bật `*` cho môi trường public để “sửa nhanh”.

**Có `server.port` nhưng không mở HTTP.** Kiểm tra `spring.main.web-application-type`, starter Web/WebFlux và log khởi động. Spring Boot hỗ trợ ứng dụng non-web; chỉ cấu hình port không tạo web stack.

**Dự kiến có bean tự cấu hình nhưng không thấy.** Kiểm tra dependency, profile, điều kiện property, bean đã tự định nghĩa, và condition evaluation report qua `--debug`. Không đoán rằng “Boot lỗi” chỉ vì một auto-config không kích hoạt.

**Health trả DOWN hoặc HTTP 503.** Kiểm tra health details theo quyền được cấp, health indicator cụ thể (DB, disk, dependency...), logs và trạng thái readiness. Đổi `server.port` hoặc mở thêm endpoint không sửa được sự cố dependency.

**Cấu hình ở YAML “không ăn”.** Tìm xem CLI, JVM system properties, biến môi trường hay config data ngoài JAR có ghi đè hay không; xác minh profile active và key binding. Chú ý key khác nhau có thể được chuẩn hóa bởi relaxed binding, và cấu hình chỉ có hiệu lực sau đúng pha khởi tạo.

**Mở cổng quản trị rồi tưởng đã an toàn.** Hai cổng khác nhau không đồng nghĩa hai mạng được cô lập. Kiểm tra endpoint access/exposure, security rules và network-level access riêng.

## 9. Các nguyên tắc cần nhớ

1. **Externalized configuration là dữ liệu đầu vào vận hành**, không phải một web server hay một cơ chế tự xây bean.
2. **Auto-configuration quyết định thành phần được tạo** từ điều kiện về thư viện, bean và property; ứng dụng vẫn sở hữu nghiệp vụ.
3. **Embedded web server thực thi HTTP**, nhận thông số qua cấu hình và các bean Boot đã tạo.
4. **Actuator quan sát hạ tầng và ứng dụng**, đồng thời dùng cùng hệ thống điều kiện, cấu hình và thường cả web stack; endpoint cần được expose và bảo vệ đúng cách.
5. **Một artifact có thể hoạt động khác nhau theo môi trường** nhờ thay đổi config nguồn ngoài, nhưng chỉ khi thành phần liên quan hỗ trợ key ấy và có cơ chế áp dụng phù hợp.

**Tự kiểm tra:** Nếu thêm Actuator nhưng không thêm starter web vào một ứng dụng non-web, liệu tự nhiên có `/actuator/health` qua HTTP? Không: cần có web HTTP runtime phù hợp. Nếu đã có web runtime mà đặt management port riêng, `/api/hello` và `/actuator/health` có nhất thiết cùng cổng? Không. Nếu đổi `server.port` bằng CLI và muốn hiểu vì sao giá trị YAML bị ghi đè, cần tra thành phần nào? Tra thứ tự `PropertySource` và giá trị `Environment` hiệu lực.

## Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)