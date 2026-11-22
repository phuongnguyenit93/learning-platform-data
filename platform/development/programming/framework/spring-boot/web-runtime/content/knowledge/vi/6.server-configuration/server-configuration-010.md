# Đối chiếu thuộc tính hỗ trợ và giá trị mặc định theo phiên bản Spring Boot

## 1. Mục tiêu và phạm vi

Các cấu hình máy chủ của Spring Boot không phải lúc nào cũng giữ nguyên tên, mặc định hoặc phạm vi tác dụng qua các bản phát hành. Một file application.yaml chạy đúng với Spring Boot 2.x có thể dùng tên thuộc tính đã bị đổi trong 3.x hoặc 4.x; thậm chí khi tên khóa giữ nguyên, server nhúng hoặc cách diễn giải giá trị có thể thay đổi.

Bài này đối chiếu ba **mốc phiên bản cụ thể**:

- **Spring Boot 2.7.18**: đại diện cho nhánh 2.7 cuối.
- **Spring Boot 3.5.x**: đại diện cho nhánh 3.5; bảng đối chiếu lấy từ tài liệu 3.5.
- **Spring Boot 4.0.x**: đại diện cho nhánh 4.0; bảng đối chiếu lấy từ tài liệu 4.0.

Đây là ba mốc tài liệu, không phải khẳng định mọi bản minor trong một nhánh hoặc bản Spring Boot mới nhất đều giống nhau. Khi dự án dùng một phiên bản khác, phải kiểm tra tài liệu và metadata của **đúng phiên bản đang chạy**.

Trọng tâm là các thuộc tính liên quan đến **embedded web server**, HTTP listener, servlet/reactive server, request/response, compression, shutdown và cấu hình đặc thù của Tomcat. Cấu hình database, messaging hoặc security application không thuộc phạm vi so sánh này.

## 2. Phân biệt “hỗ trợ”, “mặc định” và “giá trị hiệu lực”

Khi đối chiếu một thuộc tính, phải trả lời ba câu hỏi riêng biệt:

1. **Tên khóa có được hỗ trợ không?** Tài liệu hoặc configuration metadata của bản Spring Boot đó có mô tả khóa này không? Nó có bị đổi tên, thay thế hoặc loại bỏ không?
2. **Mặc định được tài liệu công bố là gì?** Nếu không ghi giá trị, Spring Boot có dùng một giá trị cụ thể như 8080, false, 8KB hoặc 30m không? Một ô mặc định trống trong tài liệu có thể nghĩa là không thiết lập cố định ở tầng Spring Boot và hành vi phụ thuộc server, OS hoặc môi trường.
3. **Giá trị thực tế khi chạy là gì?** Giá trị có thể bị override bởi application.yaml, profile, biến môi trường, command-line, test configuration hoặc code Java; embedded server cũng có thể điều chỉnh theo hệ điều hành.

Ví dụ, tài liệu liệt kê server.port mặc định 8080. Nhưng ứng dụng chạy với SERVER_PORT=9090 thì cổng thực tế là 9090. Nếu server.port=0 thì hệ điều hành chọn một cổng ngẫu nhiên và giá trị cổng đã bind không phải số 0. Do đó, **giá trị mặc định theo tài liệu không thay thế kiểm tra runtime**.

Một thuộc tính tồn tại trong danh sách chung cũng chưa chắc có tác dụng với ứng dụng hiện tại. Thuộc tính **server.tomcat.threads.max** liên quan Tomcat và không tự cấu hình Reactor Netty. Thuộc tính **server.servlet.context-path** dùng cho servlet stack; WebFlux có cấu hình base path riêng.

## 3. Bảng đối chiếu thuộc tính phổ biến

Bảng dưới đây ghi giá trị mặc định được công bố trong tài liệu của từng mốc. “Không đặt cố định” nghĩa là tài liệu không công bố một địa chỉ/giá trị duy nhất. Giá trị “trống” ở context path là trường hợp ứng dụng ở root path.

| Thuộc tính | 2.7.18 | 3.5.x | 4.0.x | Ý nghĩa thực tế |
|---|---|---|---|---|
| server.port | 8080 | 8080 | 8080 | Cổng HTTP của embedded server |
| server.address | Không đặt cố định | Không đặt cố định | Không đặt cố định | Địa chỉ IP cục bộ mà listener bind |
| server.http2.enabled | false | false | false | Cho phép HTTP/2 nếu môi trường và server hỗ trợ |
| server.compression.enabled | false | false | false | Bật nén HTTP response |
| server.compression.min-response-size | 2KB | 2KB | 2KB | Ngưỡng cấu hình nén response |
| server.servlet.context-path | Trống | Trống | Trống | Prefix context của servlet application |
| server.servlet.session.timeout | 30m | 30m | 30m | Timeout của HTTP session trong servlet stack |
| server.tomcat.threads.max | 200 | 200 | 200 | Giới hạn Tomcat worker threads khi cơ chế này có hiệu lực |
| server.tomcat.threads.min-spare | 10 | 10 | 10 | Tomcat minimum spare worker threads |
| server.tomcat.accesslog.enabled | false | false | false | Access log của Tomcat |
| server.shutdown | immediate | graceful | graceful | Kiểu shutdown mặc định ở từng mốc |

Các giá trị trong bảng **không phải cam kết hiệu quả giống nhau trên mọi server**. Đặc biệt, tùy chọn threads của Tomcat trong các phiên bản mới không có tác dụng như mô hình thread pool thông thường khi virtual threads được kích hoạt; phải đọc mô tả đúng phiên bản và chế độ runtime.

Với server.address, mặc định không có một IP literal cố định được công bố. Ứng dụng nhúng thường có thể nhận kết nối trên các interface thích hợp, nhưng socket IPv4/IPv6 thực tế còn phụ thuộc container, hệ điều hành và JVM. Đừng ghi cứng “mặc định 0.0.0.0” như một quy tắc tuyệt đối.

**Nguồn đối chiếu:** Common Application Properties của Spring Boot 2.7.18, 3.5 và 4.0, được liên kết ở cuối bài.

## 4. Thay đổi quan trọng: giới hạn HTTP header

Một ví dụ rõ về **thay đổi tên property** là giới hạn kích thước HTTP request header.

| Mốc | Thuộc tính được tài liệu liệt kê | Mặc định |
|---|---|---|
| Spring Boot 2.7.18 | server.max-http-header-size | 8KB |
| Spring Boot 3.5.x | server.max-http-request-header-size | 8KB |
| Spring Boot 4.0.x | server.max-http-request-header-size | 8KB |

Trong 2.7, tên cũ có chữ **header-size**. Ở 3.5 và 4.0, tên mới bổ sung **request** để làm rõ phạm vi. Không nên sao chép cấu hình từ tutorial 2.x vào dự án 3.x hoặc 4.x mà không đổi tên khóa.

Cấu hình cho Spring Boot 2.7:

~~~yaml
server:
  max-http-header-size: 16KB
~~~

Cấu hình cho Spring Boot 3.5 hoặc 4.0:

~~~yaml
server:
  max-http-request-header-size: 16KB
~~~

Lưu ý quan trọng:

- Mục tiêu ở bản mới là HTTP **request** header. Không đồng nhất nó với giới hạn mọi HTTP response header.
- Tài liệu 3.5 và 4.0 nói rõ cách áp dụng có thể khác nhau theo embedded server: Tomcat tính tổng request line cùng các header name/value, còn Netty có thể áp dụng giới hạn riêng cho từng request header. Vì vậy, cùng giá trị 16KB chưa chắc tương đương về hành vi giữa Tomcat và Reactor Netty.
- Nếu cần thay đổi giới hạn response header của Tomcat, hãy kiểm tra thuộc tính Tomcat-specific như server.tomcat.max-http-response-header-size của phiên bản tương ứng, thay vì giả định request-header-size cũng áp dụng cho response.
- Việc property có cùng giá trị mặc định 8KB tại nhiều mốc **không chứng minh** thư viện server dưới tầng ứng dụng giữ nguyên cơ chế từ chối request quá lớn.

Sai lầm phổ biến là thấy ứng dụng vẫn khởi động sau khi nâng cấp rồi cho rằng khóa cũ vẫn đang có hiệu lực. Một property không được bind có thể không làm ứng dụng fail lúc startup. Do đó cần kiểm chứng configuration metadata, warning từ migrator và thử nghiệm giới hạn ở server thực.

## 5. Thay đổi ở Spring Boot 4.0: cấu hình nội dung lỗi HTTP

Spring Boot 2.7 và 3.5 liệt kê nhóm thuộc tính **server.error.*** để điều khiển các thông tin được đưa vào HTTP error response. Ở tài liệu Spring Boot 4.0, các thuộc tính tương ứng được liệt kê dưới **spring.web.error.***.

| Chức năng | 2.7.18 và 3.5.x | 4.0.x | Mặc định công bố |
|---|---|---|---|
| Có đưa message vào error body không? | server.error.include-message | spring.web.error.include-message | never |
| Có đưa exception name không? | server.error.include-exception | spring.web.error.include-exception | false |
| Có đưa stacktrace không? | server.error.include-stacktrace | spring.web.error.include-stacktrace | never |
| Có đưa binding errors không? | server.error.include-binding-errors | spring.web.error.include-binding-errors | never |
| Error controller path | server.error.path | spring.web.error.path | /error |
| Bật trang lỗi mặc định | server.error.whitelabel.enabled | spring.web.error.whitelabel.enabled | true |

Ví dụ cho Spring Boot 3.5:

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    path: /error
~~~

Ví dụ theo bộ tên property trong tài liệu Spring Boot 4.0:

~~~yaml
spring:
  web:
    error:
      include-message: never
      include-stacktrace: never
      path: /error
~~~

Không nên hiểu rằng mọi thiết lập có tiền tố server.* bị đổi tên trong Boot 4.0. Các thuộc tính server.port, server.address, server.http2.enabled và nhiều cấu hình của Tomcat vẫn giữ tên như trong bảng. Vì vậy, việc migrate cần làm **theo từng property**, không đổi hàng loạt prefix.

Cũng không nên thay đổi cấu hình bảo mật hoặc chính sách tiết lộ lỗi chỉ vì đổi tên khóa. Ví dụ, include-stacktrace=never là giá trị an toàn phổ biến trong production; đổi thành always có thể làm lộ thông tin về implementation.

## 6. Một thay đổi ở giá trị mặc định: server.shutdown

Không phải mọi khác biệt phiên bản đều thể hiện bằng việc đổi tên property. Có thuộc tính **giữ nguyên tên nhưng đổi mặc định**.

| Mốc so sánh | Mặc định server.shutdown |
|---|---|
| 2.7.18 | immediate |
| 3.0.1 (đối chiếu bổ sung) | immediate |
| 3.5.x | graceful |
| 4.0.x | graceful |

Trong các mốc đã kiểm tra, 2.7.18 và 3.0.1 dùng mặc định immediate; tài liệu 3.5 và 4.0 liệt kê graceful. Bảng không kết luận chính xác bản minor đầu tiên thay đổi mặc định, vì đó là câu hỏi cần kiểm tra release notes theo từng bản.

**immediate**: server dừng tiếp nhận/xử lý theo chế độ dừng tức thời của implementation. **graceful**: server cố gắng hoàn tất những request đang hoạt động trong khoảng thời gian được phép trước khi dừng. Chi tiết phụ thuộc embedded server và lifecycle của ứng dụng.

Nếu hệ thống yêu cầu cùng hành vi qua nhiều phiên bản, hãy **đặt rõ giá trị** thay vì dựa vào mặc định:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Đây là ví dụ cấu hình shutdown có chủ đích. Không đánh đồng timeout của lifecycle shutdown với timeout cho từng HTTP request. Trong môi trường container, thời gian termination grace period của orchestrator cũng cần đủ dài để ứng dụng kịp dừng.

Thay đổi mặc định có thể ảnh hưởng thời gian process thoát, hành vi đóng kết nối và quy trình rolling deployment, nên nên đưa shutdown vào kế hoạch test nâng cấp.

## 7. Thuộc tính có tên ổn định nhưng phạm vi tác dụng phụ thuộc web stack

Spring Boot có hai mô hình web chính:

- **Servlet stack**: Spring MVC với embedded Tomcat, Jetty hoặc server tương thích.
- **Reactive stack**: Spring WebFlux với Reactor Netty hoặc server reactive tương thích.

Cùng một file application.yaml có thể chứa property chỉ có tác dụng trên một stack:

| Property | Tác dụng | Khi không phù hợp |
|---|---|---|
| server.port | Cổng HTTP của embedded server | Không có HTTP server nếu web application type là none |
| server.address | Local bind address của embedded server | Không có listener thì không có gì để bind |
| server.servlet.context-path | Context path của servlet application | Không cấu hình base path của WebFlux |
| spring.webflux.base-path | Base path của WebFlux web handlers | Không thay thế servlet context path |
| server.tomcat.threads.max | Tomcat-specific worker threads | Không áp dụng cho Reactor Netty |
| server.netty.idle-timeout | Reactor Netty-specific idle timeout | Không áp dụng cho Tomcat |
| server.http2.enabled | Cấu hình HTTP/2 khi server/environment hỗ trợ | Chưa bảo đảm mọi kết nối sẽ thực sự dùng HTTP/2 |

Với Spring MVC:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /api
~~~

Với Spring WebFlux:

~~~yaml
server:
  port: 8080

spring:
  webflux:
    base-path: /api
~~~

Hai ví dụ hướng tới kết quả URL path có prefix /api nhưng hoạt động ở các cơ chế framework khác nhau. Phải kiểm tra web application type đã được Spring Boot lựa chọn, nhất là khi cùng classpath có cả spring-boot-starter-web và spring-boot-starter-webflux.

Cũng cần phân biệt **version của Spring Boot** với **version của embedded Tomcat/Jetty/Netty**. Một bản Boot thường quản lý version dependency tương thích. Cùng một khóa được Boot hỗ trợ nhưng runtime server được nâng cấp có thể thay đổi giới hạn nội bộ hoặc điều kiện hỗ trợ.

## 8. Những giá trị mặc định “trống” trong tài liệu phải được hiểu thế nào?

Không phải ô nào trong bảng Common Application Properties cũng có con số. “Không có giá trị mặc định được ghi trong bảng” có ít nhất ba khả năng:

1. Spring Boot không áp đặt một giá trị cụ thể và để embedded server tự chọn.
2. Giá trị được tính dựa trên hệ điều hành, tài nguyên máy, kiểu connection hoặc điều kiện runtime.
3. Một phần cấu hình chỉ có ý nghĩa khi tính năng khác được bật.

Ví dụ:

- **server.address**: tài liệu thường không ghi một IP literal mặc định. Listener thực tế có thể bind theo wildcard phù hợp với hệ điều hành/server; không thể dùng dấu trống trong tài liệu để khẳng định server chỉ nghe trên 127.0.0.1.
- **server.tomcat.connection-timeout**: ô default có thể không ghi một Duration cố định. Điều này không có nghĩa server “không có timeout”; cần xem mặc định của Tomcat version đang chạy.
- **server.forward-headers-strategy**: giá trị không nên suy ra từ việc proxy có tồn tại. Spring Boot có thể chọn hành vi phụ thuộc môi trường và cần cấu hình rõ khi tin cậy forwarded headers.
- **server.ssl.enabled** có thể được tài liệu mô tả default là true ở nhánh hỗ trợ, nhưng không có nghĩa ứng dụng mặc định tự cấp chứng chỉ và mở HTTPS. Cần có SSL material hoặc cấu hình tương ứng để HTTPS thực sự hoạt động.

Vì vậy, khi viết tài liệu nội bộ, nên dùng nhãn **“không công bố mặc định cụ thể”** hoặc **“phụ thuộc implementation”**, thay vì tự điền 0, false, null hoặc unlimited nếu chưa xác minh.

## 9. Bảng cấu hình theo nhu cầu triển khai

Một số giá trị không đổi theo version vì là lựa chọn nghiệp vụ hoặc hạ tầng, không phải mặc định:

| Tình huống | Gợi ý cấu hình | Điều cần xác nhận |
|---|---|---|
| Phát triển local | server.port=8085, server.address=127.0.0.1 | Chỉ truy cập qua loopback của máy chạy |
| Chạy trong container | server.port=8080, server.address=0.0.0.0 | Port mapping/Service/Ingress vẫn cần đúng |
| Tích hợp kiểm thử với random port | server.port=0 | Đọc cổng runtime sau khi server start |
| Không cần HTTP listener nhưng vẫn giữ web context | server.port=-1 | Không giống spring.main.web-application-type=none |
| Ứng dụng cần nén response | server.compression.enabled=true | Kiểm tra Content-Type, ngưỡng size và server hỗ trợ |
| Cần HTTP/2 | server.http2.enabled=true | Kiểm tra TLS/ALPN, container/server và hạ tầng hỗ trợ |
| Giữ shutdown dự đoán được | server.shutdown=graceful | Test độ dài graceful period và termination signal |
| Chạy sau reverse proxy | server.forward-headers-strategy được chọn có chủ đích | Chỉ tin header do proxy đáng tin cậy cung cấp |

Lưu ý: server.port=0 không phải cổng dùng để kết nối từ client. Sau khi web server khởi động, cần lấy cổng thật từ WebServerInitializedEvent hoặc @LocalServerPort trong integration test. Cấu hình server.address=0.0.0.0 là **bind wildcard IPv4**, không phải URL public mà client nên nhập.

## 10. Cách xác định chính xác phiên bản đang chạy

Không nên căn cứ vào file build vừa sửa hoặc README của dự án cũ để kết luận version thực tế. Với Maven/Gradle, dependency management, BOM, parent và dependency resolution quyết định các JAR đang được nạp.

Một số cách kiểm tra:

- Maven: xem version của spring-boot-starter-parent, dependencyManagement hoặc BOM Spring Boot; dùng dependency tree để kiểm tra JAR đã resolve.
- Gradle: xem plugin org.springframework.boot, dependency management và kết quả runtimeClasspath; không chỉ nhìn version khai báo trong một dependency tùy ý.
- Khi chạy: xem thông tin version trong build info, startup log hoặc actuator info nếu được cấu hình. Không coi bất cứ chuỗi version nào không kiểm chứng là bản đang chạy.
- Với Spring Boot 4.x, package/module nội bộ của một số thành phần có thể thay đổi. Vì vậy, code dùng API configuration class cần đối chiếu Javadoc đúng bản.

Ví dụ Maven:

~~~bash
./mvnw dependency:tree
~~~

Ví dụ Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Windows có thể dùng mvnw.cmd hoặc gradlew.bat thay vì script Unix. Trong nhiều dự án, log dependency tree dài nên lọc thông tin các artifact Spring Boot và embedded server.

## 11. Cách tra property hỗ trợ theo đúng phiên bản

Quy trình kiểm tra một property mới hoặc cũ:

1. Xác định chính xác version Spring Boot và web stack đang dùng.
2. Mở **Common Application Properties** cho version đó; tìm **tên property nguyên vẹn**.
3. Đọc Description và Default Value, đồng thời xem mô tả về yêu cầu server/stack.
4. Kiểm tra **Configuration Metadata** của các starter/autoconfigure JAR tương ứng, thường ở META-INF/spring-configuration-metadata.json.
5. Khi property được đánh dấu deprecated, đọc replacement và migration guide thay vì giữ tên cũ.
6. Khi default trống, đối chiếu @ConfigurationProperties class, customizer và embedded server documentation của version tương ứng.
7. Viết test hoặc kiểm tra runtime để xác nhận property thật sự có tác dụng.

Configuration metadata hữu ích cho IDE completion, type, description, defaultValue và deprecation hints. Nhưng **metadata không phải bằng chứng duy nhất của giá trị runtime**: có trường hợp giá trị được tính động, do implementation quyết định hoặc bị override bởi các nguồn cấu hình.

Không nên chỉ tìm từ khóa trên Internet mà không ghim version. Một trang Common Application Properties không có số version cố định trong URL có thể thay đổi theo bản tài liệu hiện hành. Khi lưu tài liệu cho đội dự án, nên đính kèm URL có version.

## 12. Đọc giá trị hiệu lực tại runtime

Một giá trị được gán trong application.yaml có thể bị ghi đè bởi environment variable, system property, profile hoặc command-line. Ví dụ:

~~~yaml
server:
  port: 8080
  compression:
    enabled: false
~~~

Khi khởi chạy JAR bằng:

~~~bash
java -jar app.jar --server.port=9090 --server.compression.enabled=true
~~~

Giá trị runtime thường là cổng 9090 và bật compression, do command-line arguments ưu tiên hơn application.yaml đóng gói trong JAR theo quy tắc externalized configuration.

Tương tự, biến môi trường:

~~~bash
export SERVER_PORT=9090
export SERVER_COMPRESSION_ENABLED=true
java -jar app.jar
~~~

Trên PowerShell:

~~~powershell
$env:SERVER_PORT = "9090"
$env:SERVER_COMPRESSION_ENABLED = "true"
java -jar app.jar
~~~

Chú ý relaxed binding có thể chuyển giữa cách viết server.port và SERVER_PORT. Tuy nhiên không nên tự suy luận rằng một property **đã đổi tên qua các bản** sẽ tự được ánh xạ sang khóa mới. Relaxed binding giải quyết khác biệt về định dạng tên, không phải thay thế cho migration deprecation/renaming.

### Quan sát configured port và cổng thực đang bind

Ví dụ Spring Boot 3.5 với Java 17+, đặt trong src/main/java/example/ServerPortReporter.java của dự án Spring Boot có starter-web:

~~~java
package example;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ServerPortReporter {

    private final Environment environment;

    public ServerPortReporter(Environment environment) {
        this.environment = environment;
    }

    @EventListener
    public void onWebServerInitialized(WebServerInitializedEvent event) {
        String configured = environment.getProperty(
                "server.port", "(not explicitly configured)");
        String address = environment.getProperty(
                "server.address", "(not explicitly configured)");
        int actual = event.getWebServer().getPort();

        System.out.println("Configured server.port: " + configured);
        System.out.println("Configured server.address: " + address);
        System.out.println("Actual listening port: " + actual);
    }
}
~~~

Giải thích:

- Environment.getProperty trả giá trị hiện diện trong Environment hoặc fallback; nó không tự chứng minh “giá trị mặc định bên trong embedded server”.
- WebServerInitializedEvent được phát khi server đã được khởi động; getPort() cho biết cổng thực do server báo cáo.
- Nếu server.port=0, dòng cấu hình có thể là 0 nhưng dòng actual có thể là một cổng bất kỳ do OS cấp.
- Nếu ứng dụng cấu hình management server độc lập, event có thể xuất hiện cho nhiều web server; cần phân biệt ApplicationContext của từng event.
- Ví dụ chỉ nhắm vào package/API của Spring Boot 3.5. Khi migrate sang 4.x, tra Javadoc đúng version trước khi copy nguyên class này.

Không đưa stdout với cổng random cố định vì giá trị phụ thuộc môi trường.

### Kiểm tra bằng Spring Boot Actuator

Khi ứng dụng có Actuator và endpoint được cấu hình/cho phép truy cập phù hợp:

- Endpoint **/actuator/env** giúp tra giá trị property và nguồn PropertySource; có thể tra theo tên thuộc tính cụ thể.
- Endpoint **/actuator/configprops** hiển thị các @ConfigurationProperties bean đã bind, giúp đối chiếu giá trị gắn với ServerProperties hoặc các configuration properties khác.
- Không phải mọi property có thể đọc được nguyên văn qua endpoint: dữ liệu nhạy cảm thường bị che, và endpoint có thể bị vô hiệu hoặc hạn chế theo cấu hình bảo mật.
- Không nên public /env hoặc /configprops lên Internet chỉ để debug; sử dụng quyền truy cập quản trị phù hợp.

Ví dụ truy vấn khi endpoint env đã được expose và có quyền:

~~~bash
curl -i http://localhost:8080/actuator/env/server.port
~~~

Phải chỉnh localhost/port theo listener thật. Kết quả JSON, status và các trường có thể khác giữa các version/cấu hình, nên tránh viết một stdout giả làm kết quả cố định.

## 13. Dùng properties migrator khi nâng cấp

Spring Boot cung cấp thư viện **spring-boot-properties-migrator** để hỗ trợ chẩn đoán các property bị rename/remove khi nâng cấp feature release. Nó có thể phát cảnh báo khi startup và trong một số tình huống hỗ trợ migration tạm thời.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Quy trình an toàn:

1. Chốt version nguồn và version đích.
2. Đối chiếu keys của application.yaml, environment variables, Helm values hoặc deployment manifests.
3. Thêm migrator **tạm thời** trong giai đoạn nâng cấp nếu phù hợp với version đang dùng.
4. Chạy ứng dụng hoặc integration test, xem warning về keys đã rename, removed hoặc không còn được hỗ trợ.
5. Sửa cấu hình nguồn thành tên thuộc tính mới, chạy lại test; đừng dựa vào cơ chế ánh xạ tạm thời mãi mãi.
6. **Gỡ dependency migrator sau khi chuyển đổi xong**.

Migrator không xác minh được mọi thay đổi về semantics runtime, đặc biệt là mặc định bên trong server hoặc property xuất hiện muộn trong Environment. Bên cạnh migrator, cần đọc release notes và migration guide chính thức.

## 14. Kiểm thử cấu hình khi nâng cấp version

Một migration có thể startup thành công nhưng vận hành khác. Các nhóm kiểm thử nên gồm:

| Nhóm | Điều phải kiểm tra | Cách kiểm tra |
|---|---|---|
| Bind và port | Đúng address/port thực, không mở port ngoài ý muốn | Startup log, ss, curl từ đúng network |
| HTTP/2 | Protocol được thương lượng như mong muốn | Client hỗ trợ HTTP/2, proxy/server logs |
| Compression | Response đúng encoding và điều kiện kích hoạt | curl với Accept-Encoding, Content-Encoding |
| Request header limit | Request lớn được accept/reject theo ngưỡng đã đặt | Integration test với header có kích thước kiểm soát |
| Error response | Status, body và thông tin lỗi không vô tình đổi | Test request lỗi, kiểm tra JSON và trang lỗi |
| Session timeout | Session hết hạn theo chính sách | Test có đồng hồ/clock hoặc integration test phù hợp |
| Graceful shutdown | Request đang chạy và kết nối được đóng đúng thời điểm | Gửi SIGTERM và quan sát request inflight |
| Tomcat threads | Max/min thread phù hợp với cấu hình và virtual threads | Metrics server/thread pool cùng tài liệu runtime |
| Management port | Endpoint quản trị ở đúng mạng/cổng | Kiểm tra management.server.port và listener |
| Proxy forwarding | Redirect, URL và scheme đúng; không tin proxy giả mạo | Test qua reverse proxy đáng tin cậy |

Nếu test **request header size** dùng cùng một payload cho Tomcat và Netty, có thể nhận kết quả khác nhau do semantics limit khác nhau. Thay vì kết luận framework lỗi, hãy kiểm tra cách áp dụng của từng engine.

Nếu test **graceful shutdown**, cần thống nhất timeout ứng dụng với stop timeout trong Docker/Kubernetes. Với server.shutdown=graceful nhưng orchestrator kill process quá sớm, request vẫn có thể bị ngắt.

Nếu test **server.port=0**, hãy lấy cổng thực sau khi server start. Không gửi HTTP tới port số 0.

## 15. Các lỗi thường gặp khi so sánh phiên bản

### Lỗi 1: lấy mặc định của một bản khác

Một tutorial cũ có thể ghi server.shutdown=immediate là default trong khi tài liệu 3.5/4.0 ghi graceful. Giải pháp: trích version cụ thể, đọc bảng Application Properties của chính bản đó và override giá trị khi cần hành vi ổn định.

### Lỗi 2: giữ property cũ dù đã đổi tên

Ví dụ dùng server.max-http-header-size từ 2.7 hoặc server.error.include-message từ 3.5 trong một ứng dụng 4.0 mà không kiểm tra replacement. Giải pháp: dùng migration guide, configuration metadata và migrator; sửa đúng từng property.

### Lỗi 3: coi property tồn tại là chắc chắn có tác dụng

server.tomcat.threads.max không tự điều khiển Reactor Netty. server.servlet.context-path không điều chỉnh WebFlux base path. Giải pháp: xác minh stack và server implementation mà ứng dụng đang sử dụng.

### Lỗi 4: điền một giá trị suy đoán vào bảng mặc định

server.address không được công bố là một literal IP thống nhất trong bảng. Giải pháp: ghi “không công bố mặc định cụ thể”, rồi kiểm tra listener thực tế và môi trường mạng.

### Lỗi 5: xem giá trị trong file là giá trị runtime

application.yaml ghi 8080 nhưng SERVER_PORT=9090 hoặc CLI override 9090. Giải pháp: kiểm tra PropertySource hiệu lực và cổng sau khi server start.

### Lỗi 6: coi tên thuộc tính không đổi là semantics không đổi

Các phụ thuộc và embedded server có thể thay đổi; HTTP header size, thread pool, session, TLS và forwarded headers cần test sau khi nâng cấp. Giải pháp: đọc tài liệu của cả Spring Boot và embedded server, rồi kiểm thử hành vi.

### Lỗi 7: không phân biệt mặc định của feature và điều kiện kích hoạt

server.ssl.enabled có thể có default được ghi trong metadata, nhưng không có nghĩa HTTPS chạy mà không cấu hình chứng chỉ. server.http2.enabled=true cũng không bảo đảm mọi client sẽ dùng HTTP/2. Giải pháp: xác minh điều kiện tiên quyết và protocol thực tế.

## 16. Quy trình tạo bảng chuẩn cho một dự án

Để có bảng đối chiếu đáng tin cậy giữa hai bản Spring Boot bất kỳ:

1. **Chốt phiên bản cụ thể**: ví dụ 2.7.18 → 3.5.x hoặc 3.5.x → 4.0.x; ghi rõ patch version thực tế của dự án.
2. **Liệt kê thuộc tính đang dùng**: tìm trong application.yaml/properties, deployment, environment, secret templates, tests và các customizers Java. Không cần liệt kê hàng nghìn property không dùng.
3. **Tra property cũ và mới**: với từng key, ghi supported/deprecated/removed/renamed, mô tả, type, default công bố và nguồn tài liệu.
4. **Phân loại theo stack**: chung cho server, servlet-only, reactive-only, Tomcat-only, Jetty/Undertow/Netty-only, management-only.
5. **Kiểm tra nguồn override**: profile, env, CLI, config tree, container values và code.
6. **Quan sát runtime**: cổng thật, listener address, protocol, response headers, shutdown, thread pool/metrics và startup diagnostics.
7. **Chạy regression tests**: test giá trị hiệu lực cùng behavior đã cam kết, nhất là trường hợp property rename hoặc default đổi.
8. **Đặt giá trị explicit cho các hành vi quan trọng**: nếu ứng dụng phụ thuộc vào immediate/graceful shutdown, header limit hoặc compression, nên cấu hình rõ và kiểm thử.
9. **Lưu link tài liệu theo version**: tránh dẫn duy nhất tới trang /current hoặc /latest vì nội dung có thể thay đổi.
10. **Gỡ migrator khi xong nâng cấp**, đồng thời cập nhật tài liệu vận hành để tránh khuyến cáo cũ.

Đề xuất biểu mẫu cho từng property:

| Cột | Nội dung |
|---|---|
| Property cũ | Tên key trong version nguồn |
| Property mới | Tên key được chấp nhận trong version đích |
| Hỗ trợ | Có/không/đã đổi tên/đã loại bỏ |
| Default nguồn | Giá trị chính thức, ghi đúng version |
| Default đích | Giá trị chính thức, ghi đúng version |
| Điều kiện | Servlet/reactive/server-specific/feature-specific |
| Runtime | Giá trị sau khi áp dụng mọi overrides |
| Bằng chứng | Link docs, metadata, test hoặc log |
| Hành động | Giữ nguyên, đổi tên, cấu hình explicit hoặc viết test |

## 17. Ví dụ migration cấu hình cụ thể

Giả sử một ứng dụng Spring Boot 2.7 có file:

~~~yaml
server:
  port: 8080
  max-http-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true
  error:
    include-message: never
~~~

Khi chuyển lên **Spring Boot 3.5**, nên sửa header property sang tên mới và khai báo rõ kiểu shutdown để tránh lệ thuộc mặc định:

~~~yaml
server:
  port: 8080
  max-http-request-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true
  error:
    include-message: never
~~~

Khi chuyển tiếp lên **Spring Boot 4.0**, dùng đúng nhóm error property được tài liệu 4.0 liệt kê:

~~~yaml
server:
  port: 8080
  max-http-request-header-size: 16KB
  shutdown: immediate
  compression:
    enabled: true

spring:
  web:
    error:
      include-message: never
~~~

Ba file chỉ minh họa **di chuyển property được nhắc đến trong bài**, không phải hướng dẫn nâng cấp hoàn chỉnh. Nâng cấp major version có thể còn yêu cầu thay đổi Java, Spring Framework, Jakarta APIs, dependencies và code của ứng dụng. Hãy chạy migrator và integration tests để xác nhận mọi property thực sự được bind.

Trong ví dụ, shutdown được giữ rõ là immediate qua ba mốc nhằm bảo toàn một quyết định trước đây. Nếu vận hành muốn graceful, hãy đổi có chủ đích và kiểm thử shutdown behavior; không đổi chỉ vì một version mới có mặc định khác.

## 18. Tài liệu gốc để tự đối chiếu

Các trang chính thức được sử dụng để chọn những mốc trong bài:

1. [Spring Boot 2.7.18 – Common Application Properties](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/application-properties.html) — tên property và default của 2.7.18.
2. [Spring Boot 3.0.1 – Common Application Properties](https://docs.spring.io/spring-boot/docs/3.0.1/reference/html/application-properties.html) — mốc bổ sung để không suy đoán lúc mặc định shutdown thay đổi.
3. [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) — property và default của nhánh 3.5.
4. [Spring Boot 4.0 – Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html) — tên và default của nhánh 4.0.
5. [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html) — cấu hình cổng, tắt HTTP endpoint và tắt web application type.
6. [Spring Boot – Upgrading](https://docs.spring.io/spring-boot/upgrading.html) — quy trình đọc migration guide và sử dụng spring-boot-properties-migrator tạm thời.

Khi cần kết luận cho một patch release cụ thể, mở tài liệu và metadata của đúng patch release đó thay vì mặc định mọi version trong cùng major sẽ giống nhau.

## 19. Kết luận thực hành

**Đối chiếu cấu hình server qua các version là đối chiếu cả tên property, default, phạm vi tác dụng lẫn giá trị runtime.** Các mốc minh họa cho thấy server.port vẫn là 8080 và nhiều key phổ biến giữ nguyên, nhưng server.max-http-header-size đổi sang server.max-http-request-header-size, nhóm error property đổi namespace ở 4.0, và mặc định server.shutdown khác giữa 2.7/3.0 và 3.5/4.0.

Để tránh lỗi khi nâng cấp, hãy ghi rõ phiên bản nguồn/đích, tra tài liệu được ghim version, dùng migrator để nhận cảnh báo rename/remove, kiểm tra nguồn override và chạy test trên embedded server thật. Với các hành vi quan trọng cho production, cấu hình explicit cùng regression test giúp kết quả ổn định hơn việc phụ thuộc vào mặc định của framework.