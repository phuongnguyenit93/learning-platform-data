# Tra cứu hoặc xóa session qua endpoint `sessions` khi dùng Spring Session phù hợp

## 1. Hiểu session và phạm vi quản trị của endpoint

Phiên làm việc HTTP (HTTP session) lưu trạng thái phía máy chủ qua nhiều yêu cầu của một trình duyệt hoặc thiết bị. Ví dụ, session có thể chứa ngữ cảnh đăng nhập, tùy chọn giao diện hoặc dữ liệu tạm của người dùng. Session ID giúp máy chủ tìm đúng phiên; một username có thể liên quan tới nhiều session khác nhau.

Spring Session đưa việc lưu và tìm session qua một kho quản lý (session repository), chẳng hạn JDBC hoặc Redis. Endpoint tích hợp `sessions` của Spring Boot Actuator sử dụng kho này để tra cứu thông tin và xóa một session theo ID.

~~~text
Alice trên trình duyệt A → session A
Alice trên trình duyệt B → session B
                                  ↓
                     Kho session của Spring Session
                                  ↑
             Actuator: tra cứu hoặc xóa theo phạm vi được hỗ trợ
~~~

Ba đối tượng cần phân biệt:

| Đối tượng | Ý nghĩa |
| --- | --- |
| Username/principal name | Danh tính dùng để tìm các session đã được lập chỉ mục |
| Session ID | Định danh một session cụ thể |
| Cookie session | Thông tin trình duyệt gửi để máy chủ xác định session theo cấu hình ứng dụng |

**Xóa session A không tự xóa session B**, dù cả hai thuộc Alice. Tương tự, cookie còn nằm trên trình duyệt không có nghĩa bản ghi session tương ứng vẫn còn trong kho.

Endpoint quản trị không phải API đăng nhập, không tạo session cho username được truyền vào, và không có thao tác tích hợp “xóa mọi session của mọi người dùng”.

Bài tập trung vào **Spring Boot 3.3.x, Servlet và Spring Session JDBC**. Ví dụ chạy được dùng Boot **3.3.0**, Spring Session **3.3.0**, H2 **2.2.224** và Java **17 trở lên**.

## 2. “Dùng Spring Session phù hợp” gồm những điều kiện nào?

### 2.1. Có HttpSession thông thường chưa đủ

Một ứng dụng Servlet có thể dùng `HttpSession` do Tomcat quản lý mà chưa dùng kho Spring Session. Chỉ thêm `spring-boot-starter-actuator` và công bố `sessions` không biến toàn bộ session của container thành dữ liệu mà endpoint tự quản lý.

Với cấu hình Servlet của Boot 3.3, endpoint cần `SessionRepository` của Spring Session. Các session cần quan sát phải thực sự được lưu qua kho phù hợp với ứng dụng. Spring Session cung cấp lớp tích hợp để việc dùng `HttpSession` đi qua cơ chế lưu trữ đó.

Boot có tự cấu hình các kho Spring Session được hỗ trợ; không cần thêm annotation `@Enable*HttpSession` chỉ để lặp lại cấu hình đã do Boot quản lý. Nguồn: [Spring Session trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html).

### 2.2. Đọc theo ID và tìm theo username có yêu cầu khác nhau

Trong Boot 3.3, `SessionsEndpoint` nhận hai khả năng:

| Khả năng của kho | Thao tác dùng khả năng đó |
| --- | --- |
| `SessionRepository` | `findById`, `deleteById` |
| `FindByIndexNameSessionRepository` | Tìm session bằng chỉ mục principal name |

Kho hỗ trợ đọc/xóa theo ID chưa chắc hỗ trợ tìm theo username. Không được kết luận “endpoint hoạt động” đồng nghĩa mọi thao tác của nó đều có dữ liệu và khả năng tương ứng.

Ví dụ:

- `JdbcIndexedSessionRepository` hỗ trợ cả hai khả năng.
- `RedisSessionRepository` và `RedisIndexedSessionRepository` không có cùng khả năng lập chỉ mục.
- `MapSessionRepository` dùng trong thí nghiệm chỉ hỗ trợ các thao tác cơ bản, không tự cung cấp truy vấn theo principal.

Constructor hai tham số đã có từ Boot 3.3.0; tham số kho chỉ mục có thể không được cung cấp. Ví dụ bên dưới kiểm chứng trực tiếp sự khác nhau này. Nguồn: [API SessionsEndpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/session/SessionsEndpoint.html).

### 2.3. Username phải được đưa vào đúng chỉ mục

Tìm theo username sử dụng `findByPrincipalName(username)`, không duyệt mọi thuộc tính để đoán danh tính.

Một thuộc tính tự đặt tên `"username"` không mặc nhiên trở thành chỉ mục principal. Với các kho phù hợp, Spring Session có cơ chế phân giải principal; tích hợp Spring Security hoặc thuộc tính theo hằng số `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME` có thể cung cấp giá trị cần lập chỉ mục.

Phải kiểm tra đúng cơ chế phân giải và thời điểm lưu session của hệ thống. Không nhận username từ trình duyệt rồi tự coi đó là danh tính đã xác thực.

### 2.4. Ranh giới Servlet và reactive trong đúng phiên bản

Các ví dụ trong bài dùng `SessionsEndpoint` của Servlet và JDBC. Mã tự cấu hình Boot **3.3.0** còn có nhánh `ReactiveSessionsEndpoint` cho `ReactiveSessionRepository`, với khả năng tìm theo chỉ mục reactive được cung cấp riêng khi có.

Bảng tổng quan endpoint trong tài liệu Boot 3.3 mô tả yêu cầu Servlet, nhưng mã 3.3.0 đã có cả nhánh reactive. Vì vậy, khi đánh giá một ứng dụng WebFlux, cần đối chiếu đúng mã và loại kho của phiên bản đang dùng, không lấy cấu hình JDBC/Servlet trong bài áp nguyên xi. Có thể kiểm tra trực tiếp [SessionsEndpointAutoConfiguration ở thẻ v3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/session/SessionsEndpointAutoConfiguration.java).

## 3. Cấu hình một ứng dụng web Servlet dùng JDBC

Đoạn Gradle sau ghép vào một dự án Spring Boot 3.3 đã có cơ chế quản lý phiên bản:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.session:spring-session-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

Đây là cấu hình phục vụ lab trên ứng dụng Spring Boot hiện có, không phải một dự án Gradle độc lập.

Ví dụ `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  datasource:
    url: jdbc:h2:mem:session_web_lab;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
  session:
    timeout: 30m
    jdbc:
      initialize-schema: always

management:
  endpoint:
    sessions:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,sessions
~~~

`initialize-schema: always` ở đây dành cho lab H2 trong bộ nhớ mới. Với cơ sở dữ liệu được quản lý lâu dài, việc chuẩn bị bảng Spring Session cần theo cơ chế quản lý schema của môi trường đó.

Các lớp điều kiện vẫn độc lập:

1. Ứng dụng có đúng kho Spring Session và các bảng/kết nối cần thiết.
2. Endpoint được bật.
3. Endpoint được công bố qua HTTP.
4. Yêu cầu được cho phép qua lớp bảo mật.

Trong Boot 3.3, mặc định chỉ `health` được công bố qua HTTP; `exclude` được ưu tiên hơn `include`. Nguồn: [bật, công bố và bảo vệ endpoint Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Nếu dùng Redis và cần tìm theo username, phải chọn khả năng lập chỉ mục phù hợp; cấu hình Boot có thể dùng `spring.session.redis.repository-type=indexed`. Chỉ định Redis làm nơi lưu không tự chứng minh kho đang dùng hỗ trợ truy vấn principal. Xem [cách chọn kho Redis có chỉ mục của Spring Session](https://docs.spring.io/spring-session/reference/3.0/configuration/redis.html).

## 4. Các thao tác HTTP cần dùng

Các đường dẫn sau giả định cổng `8080`, base path `/actuator`, không có context path bổ sung và yêu cầu đã được cấp quyền.

| Yêu cầu | Kết quả/phạm vi |
| --- | --- |
| `GET /actuator/sessions?username=alice` | Danh sách session được chỉ mục cho Alice |
| `GET /actuator/sessions/{sessionId}` | Metadata của một session |
| `DELETE /actuator/sessions/{sessionId}` | Xóa đúng session có ID đó trong kho |

### 4.1. Tìm session của một username

Dùng URL encoding cho giá trị tìm kiếm:

~~~shell
curl -i -G --data-urlencode "username=alice" "http://localhost:8080/actuator/sessions"
~~~

Trên Windows PowerShell có alias `curl`, dùng `curl.exe` để gọi đúng công cụ curl.

Ví dụ hình dạng phản hồi, với ID và thời gian minh họa:

~~~json
{
  "sessions": [
    {
      "id": "60000000-0000-4000-8000-000000000001",
      "attributeNames": ["theme"],
      "creationTime": "2026-11-06T02:00:00Z",
      "lastAccessedTime": "2026-11-06T02:10:00Z",
      "maxInactiveInterval": 1800,
      "expired": false
    }
  ]
}
~~~

Không truyền `username` không có nghĩa “liệt kê mọi session”. Đây là tham số bắt buộc của thao tác tìm theo username.

Một username không có kết quả trong kho có chỉ mục bình thường trả danh sách rỗng `{"sessions":[]}`. Đó khác với trường hợp endpoint không có khả năng tìm theo chỉ mục.

### 4.2. Tra cứu một ID cụ thể

Ví dụ với ID minh họa phía trên:

~~~shell
curl -i "http://localhost:8080/actuator/sessions/60000000-0000-4000-8000-000000000001"
~~~

Kết quả thành công là một đối tượng session, không có lớp bọc `sessions` bên ngoài.

| Trường | Cách đọc |
| --- | --- |
| `id` | ID của session |
| `attributeNames` | Tên các thuộc tính, không phải giá trị |
| `creationTime` | Thời điểm tạo |
| `lastAccessedTime` | Thời điểm truy cập gần nhất được session ghi nhận |
| `maxInactiveInterval` | Khoảng bất hoạt tối đa, đơn vị giây |
| `expired` | Kết quả kiểm tra hết hạn của session được trả về |

Không hiểu `maxInactiveInterval=1800` là “chỉ còn 1800 giây”. Nó là khoảng bất hoạt cho phép; thời gian còn lại phụ thuộc thời điểm truy cập và thời điểm quan sát.

Tên `attributeNames` có thể cho biết có ngữ cảnh bảo mật hay tùy chọn giao diện, nhưng API không trả toàn bộ giá trị các thuộc tính đó. Hợp đồng HTTP được trình bày trong [Actuator Sessions API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/sessions.html).

### 4.3. Xóa đúng session đã chọn

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/sessions/60000000-0000-4000-8000-000000000001"
~~~

Endpoint gọi `deleteById(sessionId)` của kho, không tự chuyển thành “xóa mọi session của username đang gắn với ID đó”.

Trong Boot 3.3, thao tác xóa trả `void`; với xử lý bình thường không có lỗi, phản hồi HTTP là **204 No Content**. Không có phần thân JSON chứa số session đã xóa.

## 5. Phân biệt các trường hợp trống, không hỗ trợ và không tồn tại

| Tình huống trong Boot 3.3 | Kết quả thông thường sau khi qua bảo mật/định tuyến |
| --- | --- |
| Có chỉ mục, tìm được session theo username | `200`, mảng có dữ liệu |
| Có chỉ mục, username không có session phù hợp | `200`, mảng rỗng |
| Thiếu tham số bắt buộc `username` | `400` |
| Không có kho chỉ mục cho thao tác tìm username | Thao tác đọc trả `null`, được ánh xạ thành `404` |
| GET một ID không còn được kho trả về | `404` |
| DELETE xử lý bình thường | `204`, kể cả khi kho không tìm thấy ID và thực hiện thao tác rỗng |

Điểm cuối quan trọng: hợp đồng `SessionRepository.deleteById` cho phép không làm gì nếu không tìm thấy session. **204 không chứng minh ID đã tồn tại trước yêu cầu.** Muốn kiểm tra sau xóa, tra cứu lại ID và đọc kết quả tại thời điểm đó.

Mã HTTP còn có thể do lớp bảo mật, reverse proxy hoặc đường dẫn sai tạo ra. Một `404` riêng lẻ chưa đủ để kết luận nguyên nhân là session đã bị xóa.

Trong triển khai Boot 3.3, GET theo ID gọi `findById` rồi tạo đối tượng mô tả; thao tác không tự cập nhật `lastAccessedTime` hoặc lưu lại session đích. Cũng không nên mong endpoint liệt kê toàn bộ session hết hạn: kho có thể loại các session hết hạn khỏi kết quả tìm kiếm.

## 6. Thí nghiệm Java với kho JDBC thật trên H2 trong bộ nhớ

Thí nghiệm dùng chính `SessionsEndpoint` và `JdbcIndexedSessionRepository`. Nó không mở máy chủ HTTP, không đăng nhập người dùng thật và không tác động kho session bên ngoài.

Mục tiêu:

1. Lưu hai session cùng principal `alice`.
2. Tìm theo username để thấy cả hai.
3. Xóa một ID, xác nhận ID còn lại vẫn tồn tại.
4. Xóa lặp để hiểu vì sao kết quả xóa không chứng minh session từng tồn tại.
5. Đối chiếu với kho không có chỉ mục.

### 6.1. Dependency

Tạo `pom.xml` trong thư mục lab riêng:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>sessions-endpoint-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.session</groupId>
            <artifactId>spring-session-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Maven dùng để tạo classpath; phần tiếp theo biên dịch trực tiếp bằng `javac`. Dependency Spring Session JDBC mang theo các thư viện Spring cần thiết.

### 6.2. Chương trình đầy đủ

Đặt `SessionsEndpointDemo.java` cùng cấp với `pom.xml`:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.boot.actuate.session.SessionsEndpoint;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.MapSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.session.jdbc.JdbcIndexedSessionRepository;
import org.springframework.transaction.support.TransactionTemplate;

public class SessionsEndpointDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:sessions_endpoint_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");
        new ResourceDatabasePopulator(new ClassPathResource(
                "org/springframework/session/jdbc/schema-h2.sql"))
                .execute(dataSource);

        var transactions = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
        var repository = new JdbcIndexedSessionRepository(
                new JdbcTemplate(dataSource), transactions);
        var endpoint = new SessionsEndpoint(repository, repository);

        String firstId = saveSession(repository, "alice");
        String secondId = saveSession(repository, "alice");
        System.out.println("alice before="
                + endpoint.sessionsForUsername("alice").getSessions().size());
        System.out.println("attribute name visible="
                + endpoint.getSession(firstId).getAttributeNames().contains("theme"));

        endpoint.deleteSession(firstId);
        System.out.println("deleted session absent="
                + (endpoint.getSession(firstId) == null));
        System.out.println("alice after="
                + endpoint.sessionsForUsername("alice").getSessions().size());
        System.out.println("other session remains="
                + (endpoint.getSession(secondId) != null));
        endpoint.deleteSession(firstId);
        System.out.println("repeat delete completed=true");
        System.out.println("unknown user sessions="
                + endpoint.sessionsForUsername("nobody").getSessions().size());

        var plainRepository = new MapSessionRepository(new ConcurrentHashMap<>());
        String plainId = saveSession(plainRepository, "alice");
        var plainEndpoint = new SessionsEndpoint(plainRepository, null);
        System.out.println("id lookup without index="
                + (plainEndpoint.getSession(plainId) != null));
        System.out.println("username lookup without index available="
                + (plainEndpoint.sessionsForUsername("alice") != null));
    }

    private static <S extends Session> String saveSession(
            SessionRepository<S> repository, String username) {
        S session = repository.createSession();
        session.setAttribute(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                username);
        session.setAttribute("theme", "dark");
        repository.save(session);
        return session.getId();
    }
}
~~~

Script `schema-h2.sql` nằm trong thư viện Spring Session JDBC và tạo các bảng cần thiết của lab. Không cần tự sao chép cấu trúc bảng sang một mô hình dữ liệu khác. Kho JDBC cung cấp cả khả năng lưu theo ID và tìm theo principal. Nguồn: [API JdbcIndexedSessionRepository 3.3.0](https://docs.spring.io/spring-session/docs/3.3.0/api/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html).

Hàm `saveSession` dùng tham số kiểu `S extends Session` để lưu đúng kiểu session mà từng kho tạo ra. Việc đặt principal `alice` ở đây là tạo dữ liệu thí nghiệm phía máy chủ, **không phải cơ chế xác thực**.

### 6.3. Biên dịch và chạy

Yêu cầu JDK 17+ và Maven; lần đầu tải dependency cần kết nối kho Maven.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$sessionsClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$sessionsClasspath" SessionsEndpointDemo.java
java -cp ".;$sessionsClasspath" SessionsEndpointDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
sessions_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$sessions_classpath" SessionsEndpointDemo.java
java -cp ".:$sessions_classpath" SessionsEndpointDemo
~~~

Stdout:

~~~text
alice before=2
attribute name visible=true
deleted session absent=true
alice after=1
other session remains=true
repeat delete completed=true
unknown user sessions=0
id lookup without index=true
username lookup without index available=false
~~~

Những kết luận được chứng minh bởi lần chạy:

- Hai phiên cùng username không phải một phiên duy nhất.
- Xóa `firstId` làm session đó không còn được tìm thấy, còn `secondId` vẫn đọc được.
- Xóa lại cùng ID hoàn thành bình thường.
- Username không có kết quả cho danh sách rỗng trong kho JDBC có chỉ mục.
- Kho `MapSessionRepository` vẫn đọc được theo ID; truyền `null` cho kho chỉ mục khiến truy vấn username không cung cấp mô tả kết quả.

Chương trình không in ID ngẫu nhiên hoặc thời gian cụ thể để stdout ổn định. H2 của lab nằm trong bộ nhớ và hết vòng đời khi tiến trình kết thúc.

## 7. Thực hành vòng đời session qua HTTP

Để tạo dữ liệu kiểm chứng trên **ứng dụng web lab** đã cấu hình ở phần 3, có thể thêm controller minh họa sau:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionLabController {
    @GetMapping("/lab/touch")
    public Map<String, String> touch(HttpSession session) {
        session.setAttribute(
                FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
                "alice");
        session.setAttribute("theme", "dark");
        return Map.of("sessionId", session.getId());
    }
}
~~~

Đây là controller tạo dữ liệu lab với principal cố định, không dùng để xác thực hay làm API ứng dụng thật. Đặt lớp trong vùng package được Spring Boot quét.

Ví dụ PowerShell, giả định lab cục bộ không yêu cầu xác thực:

~~~powershell
$lab = Invoke-RestMethod -Uri "http://localhost:8080/lab/touch" -SessionVariable labCookies
$sessionId = $lab.sessionId
$sessionUrl = "http://localhost:8080/actuator/sessions/" + [uri]::EscapeDataString($sessionId)

Invoke-RestMethod -Uri "http://localhost:8080/actuator/sessions?username=alice"
Invoke-RestMethod -Uri $sessionUrl
Invoke-WebRequest -Method Delete -Uri $sessionUrl
~~~

Sau DELETE, GET lại `$sessionUrl` bình thường trả `404`. Trong PowerShell, phản hồi lỗi HTTP có thể được biểu diễn bằng exception; cần đọc mã trạng thái thay vì coi mọi exception là lỗi kết nối.

Có thể gửi lại yêu cầu ứng dụng bằng cookie cũ:

~~~powershell
$next = Invoke-RestMethod -Uri "http://localhost:8080/lab/touch" -WebSession $labCookies
$next.sessionId -ne $sessionId
~~~

Trong lab này, controller luôn yêu cầu một `HttpSession`, nên khi session cũ không còn hợp lệ, một session mới được tạo và ID mới được trả về. Đây không phải session cũ “sống lại”; cũng không phải DELETE đã ngăn trình duyệt tạo mọi session mới trong tương lai.

Ở ứng dụng có Spring Security, yêu cầu sau khi mất session đăng nhập có thể bị yêu cầu đăng nhập lại, chuyển hướng hoặc trả lỗi theo cấu hình bảo mật. Không lấy hành vi của controller lab không xác thực để khẳng định mọi ứng dụng sẽ phản hồi giống nhau.

## 8. Phạm vi xóa và các giới hạn cần hiểu

### 8.1. Một ID khác với toàn bộ phiên của người dùng

Nếu Alice đang đăng nhập trên ba thiết bị, DELETE một session ID không đăng xuất hai thiết bị còn lại. Để xử lý nhiều phiên, quy trình quản trị phải tìm và chọn các ID phù hợp rồi xử lý riêng từng ID.

Ngay cả khi lần đầu tìm được tất cả session của Alice, một session mới có thể được tạo sau thời điểm tìm. Chuỗi “tìm rồi xóa từng ID” không tự trở thành một thao tác nguyên tử cấm mọi phiên mới của tài khoản.

### 8.2. Kho và phạm vi triển khai quyết định nơi bị tác động

Nếu các bản sao ứng dụng dùng chung cùng kho JDBC hoặc Redis và cùng phạm vi cấu hình session, việc xóa tác động lên bản ghi trong kho dùng chung. Nếu mỗi tiến trình dùng kho riêng, yêu cầu tới một tiến trình không tự điều khiển kho của tiến trình khác.

Cần kiểm tra datasource, tên bảng, namespace và cấu hình thực tế. Chỉ nhìn URL `/actuator/sessions` không cho biết thao tác đang ảnh hưởng tới hệ thống nào hoặc tất cả bản sao nào.

### 8.3. Xóa session không thu hồi mọi loại thông tin xác thực

Session là trạng thái phía máy chủ. Xóa nó không mặc nhiên thu hồi JWT, refresh token, cookie remember-me hoặc phiên ở nhà cung cấp danh tính bên ngoài.

Một hệ thống dùng JWT hoàn toàn không trạng thái có thể không tạo session đăng nhập để endpoint này tìm. Danh sách rỗng trong trường hợp đó không chứng minh người dùng chưa được xác thực.

### 8.4. Xóa không hoàn tác yêu cầu đang xử lý

Một yêu cầu đã đọc session hoặc ngữ cảnh xác thực trước khi bản ghi bị xóa có thể đã đi tiếp trong luồng xử lý. Endpoint không cam kết hủy ngược mọi yêu cầu đang chạy hoặc hoàn tác giao dịch nghiệp vụ.

Khi cần vô hiệu hóa quyền truy cập khẩn cấp, phải xác định thêm cơ chế kiểm tra quyền và vòng đời thông tin xác thực của ứng dụng.

### 8.5. ID trong phản hồi và giá trị cookie cần được phân biệt

Dùng ID mà endpoint hoặc ứng dụng trả về cho đường dẫn theo ID. Không tự giả định toàn bộ giá trị cookie thô luôn bằng chính chuỗi ID đó, vì cách biểu diễn cookie phụ thuộc bộ tuần tự hóa/cấu hình.

Cũng không ghi ID session thật vào nội dung hướng dẫn công khai hoặc dùng nó như bằng chứng danh tính. Khi vận hành, coi ID là thông tin cần được kiểm soát truy cập.

## 9. Bảo mật thao tác quản trị và chẩn đoán lỗi

Tham số `username=alice` là điều kiện tìm kiếm, không phải một phép kiểm tra người gọi có quyền xem Alice hay không. Quyền tra cứu và xóa phải do lớp bảo mật quản trị quyết định.

Nếu xây API để người dùng tự quản lý các phiên của mình, API đó phải xác định principal đã xác thực và kiểm tra quyền sở hữu session phía máy chủ. Không đưa nguyên endpoint quản trị ra giao diện người dùng rồi cho phép thay username/ID tùy ý.

Với Spring Security, GET được phép chưa chắc DELETE được phép. Ngoài phân quyền, CSRF mặc định có thể chặn DELETE và trả `403`; chỉ có thông tin xác thực chưa đủ để kết luận mọi yêu cầu ghi sẽ được chấp nhận. Không tắt CSRF toàn ứng dụng chỉ để làm lệnh lab chạy được. Nguồn: [bảo mật và CSRF của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Endpoint không xuất hiện | Actuator, kho Spring Session, điều kiện tự cấu hình, bật/công bố endpoint, cổng/base path |
| GET username trả `400` | Có truyền đúng tham số bắt buộc và URL encode giá trị chưa |
| Đọc theo ID được, tìm username không được | Kho có cung cấp khả năng lập chỉ mục principal không |
| Trả mảng rỗng dù biết có người đang đăng nhập | Đúng principal name, đúng kho, đúng chỉ mục, đúng thời điểm lưu và đúng kiểu xác thực chưa |
| GET theo ID trả `404` | ID sai, hết hạn, đã xóa, khác kho hoặc đường dẫn sai |
| DELETE trả `403` | Phân quyền và CSRF; chưa kết luận kho session bị lỗi |
| DELETE `204`, người dùng vẫn truy cập được | Có phiên khác, session mới, remember-me/JWT hoặc yêu cầu đã xác thực trước đó không |
| Cookie cũ vẫn còn trên trình duyệt | Xóa bản ghi phía máy chủ không tự sửa cookie trên mọi thiết bị từ xa |

## 10. Chọn đúng bằng chứng khi xử lý một phiên bất thường

Giả sử Alice báo có một thiết bị lạ đang giữ phiên đăng nhập.

1. Xác định đúng môi trường, kho session và principal name mà hệ thống sử dụng.
2. Với quyền quản trị phù hợp, tìm các session của Alice.
3. Đối chiếu thông tin có sẵn để chọn đúng ID; metadata cơ bản không mặc nhiên chứa IP, loại thiết bị hay lịch sử hoạt động đầy đủ.
4. Xóa ID được chọn rồi kiểm tra lại khả năng tra cứu ID đó.
5. Kiểm tra hành vi truy cập tiếp theo theo cơ chế xác thực của ứng dụng; không coi `204` là bằng chứng đã vô hiệu hóa mọi loại phiên/token của Alice.

**Bài tập tự kiểm tra:**

- Trong thí nghiệm, vì sao xóa một ID làm số session của Alice từ 2 xuống 1?
- Tại sao username không có kết quả trong kho có chỉ mục khác với truy vấn username trên kho không có chỉ mục?
- Nếu xóa cùng một ID hai lần đều hoàn thành, mã `204` cho biết điều gì và không cho biết điều gì?
- Vì sao một trình duyệt có thể tạo ID mới sau khi session cũ bị xóa?
- Một ứng dụng JWT không trạng thái trả danh sách session rỗng: còn thiếu bằng chứng nào trước khi kết luận người dùng đã đăng xuất?

Khi mô tả kết quả, ghi rõ **session ID được chọn, kho quản lý, khả năng chỉ mục và thời điểm quan sát** để người khác có thể kiểm tra lại phạm vi thao tác.
