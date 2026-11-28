# Không thấy endpoint modulith

## 1. Tình huống và mục tiêu chẩn đoán

Trong chương **Chẩn đoán lỗi** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, bạn dùng Spring Modulith để tài liệu hóa ranh giới *application module* và quan sát tương tác giữa các phần của một ứng dụng Spring Boot. Spring Modulith có thể xuất cấu trúc module qua **Spring Boot Actuator** để bạn kiểm tra module graph ở runtime. Các tính năng khác như metrics sự kiện, tracing và context propagation bổ sung bằng chứng về hành vi của module trong lúc chạy.

Giả sử ứng dụng khởi động bình thường; `GET /actuator/health` trả về `200 OK` nhưng `GET /actuator/modulith` trả về `404 Not Found`. Bạn cần xác định endpoint chưa được đăng ký, chưa được mở qua HTTP, đang ở URL khác, hay đang bị lớp bảo mật/proxy chặn.

**Mục tiêu:** sau bài này, bạn có thể (1) xác định tên endpoint đúng; (2) lần lượt kiểm tra dependency, cấu hình Actuator, profile, đường dẫn, quyền truy cập và cấu trúc package; (3) giải thích các mã HTTP khác nhau; (4) xác minh endpoint trả thông tin module đúng; và (5) tránh nhầm endpoint mô tả kiến trúc với dữ liệu event metrics/tracing.

### Điểm cần biết ngay

Với Spring Modulith hiện đại, **ID của endpoint là `modulith`**, vì vậy URL HTTP mặc định là:

~~~http
GET http://localhost:8080/actuator/modulith
~~~

Lớp Java hiện thực mang tên `ApplicationModulesEndpoint` và được khai báo `@Endpoint(id = "modulith")`. Đừng đoán tên URL từ tên lớp Java: `/actuator/applicationmodules` và `/actuator/application-modules` là các tên từng xuất hiện ở các bản rất cũ/giai đoạn phát triển, không phải URL mặc định của các bản hiện đại. Khi xử lý dự án legacy, hãy tra tài liệu **đúng phiên bản** mà dự án chạy trước khi kết luận.

Endpoint `modulith` trả **JSON về cấu trúc module** (tên module, package, dependencies), không phải ảnh PNG/Mermaid của module graph và cũng không phải một dashboard hiển thị metric hay trace. Tài liệu sơ đồ có thể được sinh riêng bằng `Documenter`; event metrics/tracing cần hạ tầng observability riêng.

## 2. Phân biệt triệu chứng trước khi sửa cấu hình

Chạy trên máy đang chạy ứng dụng, thay cổng và prefix theo cấu hình thực tế:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/health"
curl.exe -i "http://localhost:8080/actuator"
curl.exe -i "http://localhost:8080/actuator/modulith"
~~~

Trên Linux/macOS dùng `curl -i` tương đương. Tùy cấu hình security, `health` cũng có thể yêu cầu xác thực. Quan sát **HTTP status**, `Location` khi redirect, body phản hồi và log ứng dụng.

| Hiện tượng | Nhận định ban đầu | Bước kiểm tra gần nhất |
| --- | --- | --- |
| `/actuator/health` và `/actuator` đều 404 | Sai host/cổng/base path; thiếu Actuator; quản lý HTTP chưa bật; proxy không route | Xem dependency Boot Actuator, cổng và đường dẫn |
| `health` 200 nhưng `modulith` 404 | Có Actuator nhưng endpoint thiếu hoặc chưa expose, hoặc đường dẫn `modulith` bị đổi | Kiểm tra Modulith actuator dependency, `exposure.include`, `exclude`, path mapping |
| `/actuator` 200, không có liên kết `modulith` | Chưa chứng minh được endpoint hoạt động; có thể chưa khả dụng hoặc chưa expose | Kiểm tra config/beans và thử URL trực tiếp |
| `modulith` 401 | Endpoint tồn tại hoặc có lớp auth chặn trước khi định tuyến; chưa có credential | Kiểm tra Spring Security/gateway và thử bằng tài khoản được phép |
| `modulith` 403 | Danh tính thiếu quyền hoặc chính sách mạng/CSRF/gateway chặn | Kiểm tra quyền với `SecurityFilterChain` hoặc lớp proxy |
| `modulith` 302 đến trang đăng nhập | Form login/SSO đang intercept request | Xem header `Location`, cấu hình cơ chế xác thực |
| `modulith` 500 | Có lỗi trong lúc endpoint/metadata được xử lý | Đọc root-cause exception ở log, kiểm tra classpath và package discovery |
| `modulith` 200 nhưng thiếu module mong đợi | Endpoint hoạt động; khả năng phát hiện module hoặc package structure khác kỳ vọng | Kiểm tra package gốc, `@Modulithic`, `ApplicationModules` |
| Nội bộ gọi được, qua public domain lại 404/403 | Route, path rewrite, firewall, WAF hoặc auth ở proxy/ingress | So sánh kết quả direct-to-app và qua gateway |

Không nên “sửa 404” bằng cách tắt toàn bộ Spring Security hay expose mọi actuator endpoint. Trước hết hãy xác định **lớp nào trả lỗi**.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Thử đúng URL /actuator/modulith"] --> B{"HTTP status?"}
    B -->|200| C["Kiểm tra JSON và module được phát hiện"]
    B -->|401 / 403 / 302| D["Kiểm tra SecurityFilterChain, SSO, gateway"]
    B -->|500| E["Đọc exception, dependency, cấu trúc module"]
    B -->|404| F["Thử /actuator/health và /actuator"]
    F --> G{"Actuator có phản hồi?"}
    G -->|Không| H["Kiểm tra starter actuator, port, base path, proxy"]
    G -->|Có| I["Kiểm tra Modulith actuator runtime, exposure, access, remapping"]
    I --> J["Thử trực tiếp trên management port"]
    J --> K{"Endpoint có tồn tại?"}
    K -->|Có| L["Sửa route hoặc quyền truy cập"]
    K -->|Không| M["Kiểm tra auto-configuration, phiên bản, package scan"]
~~~

Sơ đồ là thứ tự khảo sát, không phải quy tắc suy luận tuyệt đối: một proxy có thể cố tình trả `404` cho tài nguyên không được phép, và `/actuator` có thể bị tắt discovery. Vì vậy phải kết hợp log và cấu hình thực tế.

## 3. Kiểm tra dependency: có Spring Modulith chưa đủ

Điều kiện quan trọng nhất là ứng dụng phải có **Spring Boot Actuator** và **Spring Modulith actuator integration** trong **runtime classpath**. Chỉ có `spring-modulith-starter-core` hoặc dependency phục vụ kiểm thử/tạo tài liệu chưa làm xuất hiện endpoint HTTP.

### 3.1. Lựa chọn tối thiểu: Actuator + Modulith actuator

Ví dụ Gradle (phiên bản do BOM tương thích của Spring Boot/Spring Modulith quản lý):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'

    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
}
~~~

Ví dụ Maven tương đương (dự án đã quản lý đúng BOM):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-actuator</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Cần import Spring Modulith BOM hoặc quản lý phiên bản ở cơ chế dependency management tương đương; các snippet cố ý không gắn phiên bản riêng lẻ. Chọn release train tương thích với Spring Boot đang dùng, không tự trộn các JAR Modulith 1.x/2.x.

### 3.2. Lựa chọn tích hợp: Insight starter

Nếu bạn còn cần quan sát tương tác giữa các module, có thể dùng:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

`spring-modulith-starter-insight` cung cấp các tích hợp actuator và observability cùng phần khởi tạo Actuator cần thiết theo release tương ứng. **Không cần thêm `spring-modulith-actuator` một lần nữa** chỉ để tạo endpoint khi đã dùng starter này. Bạn vẫn cần thư viện exporter phù hợp nếu muốn gửi trace/metric ra hệ thống quan sát bên ngoài; exporter không phải điều kiện để chính endpoint `modulith` tồn tại.

**Các lỗi dependency thường gặp:**

- Đặt `spring-modulith-actuator` dưới `testImplementation`, `test` hoặc trong module phụ không được đóng gói vào ứng dụng thực tế.
- Chỉ thêm `spring-boot-starter-actuator`, nhưng không có `spring-modulith-actuator` hay `spring-modulith-starter-insight`.
- Đọc hướng dẫn Spring Modulith phiên bản khác, dẫn đến tên artifact hoặc yêu cầu Boot không khớp.
- Chạy JAR/container đã build trước khi thêm dependency; IDE chạy classpath khác với image.
- Bị exclude dependency bắc cầu hoặc cấu hình build minimization loại auto-configuration ở runtime.

**Cách kiểm chứng:** xem dependency tree của **đúng module ứng dụng thực thi** và kiểm tra `spring-modulith-actuator`/`spring-boot-actuator` thực sự có trong runtime artifact. Với một ứng dụng gồm nhiều Gradle module, dependency chỉ có trong thư viện con không đảm bảo runtime app sẽ có đủ nếu đóng gói tùy biến.

## 4. Expose endpoint qua HTTP

**Có bean Actuator không có nghĩa endpoint sẽ được mở qua web.** Spring Boot mặc định thường chỉ expose `health` qua HTTP. Để thử cục bộ, cấu hình trong `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith"
~~~

Khởi động lại với đúng profile, thử:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/modulith"
~~~

Nếu đạt, bạn sẽ nhận JSON có key là tên các application module, ví dụ cấu trúc minh họa sau:

~~~json
{
  "orders": {
    "displayName": "Orders",
    "basePackage": "com.example.shop.orders",
    "dependencies": []
  },
  "notifications": {
    "displayName": "Notifications",
    "basePackage": "com.example.shop.notifications",
    "dependencies": [
      {
        "target": "orders",
        "types": ["EVENT_LISTENER"]
      }
    ]
  }
}
~~~

Đây là dữ liệu ví dụ: tên module và dependency phải xuất phát từ mã của ứng dụng đang chạy. Các metadata về `dependencies[].types` có thể chứa `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` tùy tương tác thực tế.

### 4.1. `include`, `exclude` và quyền access

Cấu hình dưới đây sẽ **không** expose `modulith` dù đã có trong `include`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,modulith"
        exclude: "modulith"
~~~

Vì `exclude` được ưu tiên hơn `include`. Hãy kiểm tra file cấu hình, profile, environment variable và command-line overrides cùng lúc.

Ở các phiên bản Spring Boot mới có cơ chế quản lý **endpoint access** (ví dụ `management.endpoints.access.default`, `management.endpoint.modulith.access` và `management.endpoints.access.max-permitted`). Nếu cài đặt global `none` hoặc giới hạn read access, endpoint có thể bị loại khỏi context dù bạn đã thêm nó vào `exposure.include`.

Ví dụ trong Spring Boot hỗ trợ thuộc tính `access`, khi hệ thống đặt mặc định `none`:

~~~yaml
management:
  endpoints:
    access:
      default: none
    web:
      exposure:
        include: "health,modulith"
  endpoint:
    health:
      access: read-only
    modulith:
      access: read-only
~~~

Lưu ý `max-permitted: none` ở cấp toàn ứng dụng có thể vô hiệu hóa cả thiết lập riêng; phải kiểm tra chính sách toàn cục. Với Spring Boot cũ chưa hỗ trợ `access`, dùng những property `enabled` tương ứng theo tài liệu đúng phiên bản, không áp nguyên YAML mới vào mọi release.

### 4.2. Đừng phụ thuộc duy nhất vào trang discovery

`GET /actuator` là trang discovery có thể liệt kê đường dẫn `modulith` trong `_links`. Nhưng ứng dụng có thể tắt discovery:

~~~yaml
management:
  endpoints:
    web:
      discovery:
        enabled: false
~~~

Hoặc ứng dụng đặt `base-path: /` khiến discovery bị vô hiệu để tránh xung đột mapping. Trong những trường hợp này, **không thấy liên kết** ở `/actuator` không đủ để kết luận endpoint chưa đăng ký; hãy truy cập URL cụ thể dựa trên cấu hình path.

## 5. Sai host, port hoặc base path

Nhiều sự cố được báo là “modulith 404” thực chất là gọi nhầm nơi.

### 5.1. Đổi cổng quản trị

Ví dụ:

~~~yaml
server:
  port: 8080
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,modulith"
~~~

Lúc này endpoint thông thường ở:

~~~text
http://localhost:9090/actuator/modulith
~~~

Yêu cầu tới `http://localhost:8080/actuator/modulith` có thể trả 404 dù ứng dụng vẫn hoạt động.

### 5.2. Đổi prefix hoặc mapping riêng

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        modulith: modules
      exposure:
        include: "health,modulith"
~~~

URL tương ứng là `/manage/modules`; ID vẫn là `modulith`, nên trong `exposure.include` vẫn phải viết `modulith`, **không dùng `modules`**.

Khi không dùng management port riêng, `management.endpoints.web.base-path` được tính tương đối với `server.servlet.context-path` (MVC) hoặc `spring.webflux.base-path` (WebFlux). Nếu có `management.server.port` riêng, base path tương đối với `management.server.base-path`. Ví dụ servlet app với context path `/shop`, base path mặc định sẽ có dạng `/shop/actuator/modulith` **khi chung cổng**.

### 5.3. Reverse proxy, Kubernetes và service mesh

Nếu gọi trực tiếp trên app thành công nhưng qua gateway không thành công:

1. So sánh đường dẫn client gửi và đường dẫn backend nhận sau khi proxy rewrite.
2. Kiểm tra route có forward management port (nếu tách cổng), hay management chỉ bind `127.0.0.1`.
3. Kiểm tra ingress/service chỉ public cổng ứng dụng, không public management port.
4. Kiểm tra TLS termination, hostname, context path, auth tại gateway, path whitelist/denylist.
5. Đối chiếu HTTP status và header từ direct-to-app với từ domain bên ngoài.

Không mở management endpoint ra Internet chỉ để thử. Trong môi trường thật, ưu tiên truy cập qua mạng quản trị hoặc phương án nội bộ được kiểm soát.

## 6. Spring Security có thể chặn trước khi thấy JSON

Khi Spring Security có mặt, `401` nghĩa là thiếu xác thực và `403` thường là danh tính chưa đủ quyền. Nếu dùng form login, browser hoặc `curl -i` có thể thấy `302` tới trang đăng nhập.

Đặc biệt, nếu bạn tự định nghĩa `SecurityFilterChain`, cấu hình bảo vệ Actuator tự động của Spring Boot có thể không còn áp dụng như trước. Hãy kiểm tra toàn bộ filter chain của ứng dụng, không chỉ `application.yml`.

Ví dụ matcher chuyên cho Actuator endpoint trong ứng dụng Servlet/Spring Security 6:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

// Đưa vào SecurityFilterChain phù hợp và cấu hình một fallback chain
// bảo vệ các đường dẫn khác theo chính sách của ứng dụng.
http.securityMatcher(EndpointRequest.to("modulith"))
    .authorizeHttpRequests(auth ->
        auth.anyRequest().hasRole("OPS"));
~~~

Ví dụ là một đoạn cấu hình minh họa cách match **endpoint ID** thay vì so chuỗi `/actuator/modulith`. Nó phải được ghép vào cấu hình đầy đủ với phương thức xác thực phù hợp, thứ tự filter chains và chính sách fallback cho các URL còn lại. Khi cổng quản trị tách biệt hoặc có reverse proxy/security ngoài ứng dụng, cũng phải kiểm tra lớp bảo vệ tương ứng.

**Quy tắc an toàn:** endpoint `modulith` có thể lộ tên package và cấu trúc phụ thuộc nội bộ. Với production, bảo vệ bằng tài khoản vận hành, tách mạng hoặc giới hạn nguồn truy cập. Không dùng `permitAll()` hay `management.endpoints.web.exposure.include: "*"` như giải pháp mặc định chỉ để làm hết lỗi.

## 7. Endpoint đã trả 200 nhưng module graph sai hoặc thiếu

Có khi `/actuator/modulith` hiện JSON nhưng không có `orders`, `inventory` hoặc `notifications` như mong đợi. Đây là vấn đề **phát hiện ranh giới application module**, không còn là lỗi “không thấy endpoint”.

Spring Modulith thường phát hiện module từ các package con trực tiếp của package ứng dụng được chọn làm gốc. Ví dụ:

~~~text
src/main/java/
└── com/example/shop/
    ├── ShopApplication.java        // @SpringBootApplication
    ├── orders/                    // module orders
    │   ├── OrderService.java
    │   └── api/OrderConfirmed.java
    ├── inventory/                 // module inventory
    │   └── InventoryService.java
    └── notifications/             // module notifications
        └── OrderEventListener.java
~~~

Nếu `ShopApplication` lại nằm trong `com.example.shop.bootstrap` hoặc cấu trúc module nằm ngoài package gốc mà Modulith đang dùng, mô hình phát hiện có thể khác kỳ vọng. Kiểm tra cả cấu hình `@Modulithic`, `@ApplicationModule`, named interfaces, nested modules và quy tắc phát hiện module đang áp dụng.

Để xác minh mô hình ở mức **code**, có thể tạo một test hoặc một tác vụ kiểm chứng dùng API core:

~~~java
import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithStructureTest {

    @Test
    void verifiesArchitecture() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
        modules.verify();
        System.out.println(modules);
    }
}
~~~

`ApplicationModules.of(...)` cho phép đối chiếu các module được phát hiện; `verify()` kiểm tra các ràng buộc kiến trúc và có thể báo vi phạm như phụ thuộc vòng hoặc truy cập vượt API module. **Một bài test cấu trúc chạy thành công chưa chứng minh endpoint được mở qua HTTP**; ngược lại `/actuator/modulith` trả 200 cũng không thay thế test `verify()`.

Nếu cấu trúc module được tùy biến trong source test nhưng runtime không có customization tương ứng, hai kết quả có thể khác nhau. Hãy đặt các quy tắc cần dùng ở production trong source production.

## 8. Chẩn đoán auto-configuration và lỗi khởi tạo

Sau khi xác nhận runtime có đúng dependencies, `exposure.include` và URL, nếu endpoint vẫn vắng mặt:

1. Bật **condition evaluation report** cho lần chạy chẩn đoán (ví dụ tham số `--debug` của Spring Boot), tìm những dòng liên quan đến Modulith actuator và Actuator endpoint auto-configuration.
2. Trong môi trường nội bộ có quyền phù hợp, xem `/actuator/conditions` để biết auto-configuration nào match hoặc không match. Chỉ expose endpoint chẩn đoán này tạm thời.
3. Xem classpath thực tế, exclusions, file JAR/container đang chạy, profile và cấu hình điều kiện trên các bean.
4. Kiểm tra log startup của context; nếu có exception tạo `ApplicationModules` hoặc lỗi class-loading/Jackson, xử lý **root cause** thay vì chỉ nhìn mã HTTP 500.
5. Kiểm tra một project tối thiểu cùng phiên bản Boot/Modulith. Nếu bản tối thiểu có `modulith` nhưng ứng dụng chính không có, so sánh auto-config exclusions, classpath, security và cấu trúc package.

Trong Spring Boot, điều kiện của một endpoint liên quan đến ít nhất ba vấn đề **độc lập**: thư viện tạo endpoint có thực sự được nạp không, endpoint có được phép truy cập/được expose không, và request có đi đến đúng handler thông qua web/security/gateway không.

### Một cách ghi chép chẩn đoán dễ bàn giao

~~~text
Environment: local / staging / prod
Spring Boot version: ...
Spring Modulith version: ...
Active profiles: ...
Main server URL: ...
Management URL: ...
Runtime dependencies: spring-boot-starter-actuator=present,
                      spring-modulith-actuator=present
GET /actuator/health: 200
GET /actuator: 200, modulith link present/absent
GET /actuator/modulith: 404
Endpoint exposure include: health,info,modulith
Endpoint exclude: none
Management port/base-path/path-mapping: ...
Spring Security / proxy response: ...
Auto-configuration report evidence: ...
Root cause and corrective action: ...
Post-fix HTTP response and module count: ...
~~~

Dòng log “Started ShopApplication” chỉ xác nhận context khởi động tới một mức nhất định; nó **không** tự chứng minh endpoint đã được expose, đặc biệt nếu cấu hình port và quyền quản trị khác với cổng ứng dụng.

## 9. Chẩn đoán theo tình huống thực tế

### Tình huống A: chỉ khai báo starter core

**Triệu chứng:** `/actuator/health` trả 200, `/actuator/modulith` 404; ứng dụng có `spring-modulith-starter-core`.

**Nguyên nhân có khả năng cao:** thiếu `spring-modulith-actuator` hoặc `spring-modulith-starter-insight` trên runtime classpath.

**Cách sửa:** thêm một lựa chọn đúng, build lại artifact và xác nhận trong runtime; sau đó bật `exposure.include` nếu chưa có.

### Tình huống B: đã thêm dependency nhưng quên expose

**Triệu chứng:** runtime có `spring-modulith-actuator`, `/actuator` chỉ có liên kết `health`, gọi `/actuator/modulith` 404.

**Nguyên nhân có khả năng cao:** `management.endpoints.web.exposure.include` đang mặc định chỉ có `health`.

**Cách sửa:** thêm `modulith` vào danh sách include, bảo đảm không có `exclude` hoặc `access=none` chặn.

### Tình huống C: local được, staging không được

**Triệu chứng:** cùng commit, máy local gọi 200; staging qua URL chính 404.

**Nguyên nhân có thể:** profile staging thay đổi cấu hình management port, path mapping hoặc ingress không route cổng quản trị; container chạy JAR cũ.

**Cách sửa:** ghi lại **cấu hình thực sự có hiệu lực** ở staging, kiểm tra response trực tiếp trên app/pod trong mạng quản trị và so với ingress. Xác nhận image digest hoặc version đã triển khai.

### Tình huống D: endpoint trả 401 hoặc 403

**Triệu chứng:** thiếu `modulith` trong giao diện quan sát, nhưng gọi URL thấy 401/403.

**Nguyên nhân có khả năng:** Basic auth, JWT, OAuth2, mTLS hoặc quyền hạn ở gateway / Spring Security chưa đáp ứng.

**Cách sửa:** kiểm tra filter chain và scope/role vận hành, truy cập với danh tính đã được cấp quyền; không xóa kiểm soát truy cập.

### Tình huống E: endpoint có JSON nhưng dependency graph không đúng

**Triệu chứng:** `GET /actuator/modulith` trả 200 nhưng chỉ thấy một phần module.

**Nguyên nhân có thể:** đặt sai package gốc, quy tắc phát hiện module hoặc tùy biến chỉ áp trong test.

**Cách sửa:** kiểm tra package, `@SpringBootApplication` / `@Modulithic` và kết quả `ApplicationModules.of(...).verify()`; sau đó đánh giá lại JSON runtime. Nếu mong đợi sơ đồ có hình ảnh, dùng cơ chế sinh documentation thay vì tìm PNG ở endpoint này.

## 10. Liên hệ với module graph, metrics, tracing và context propagation

Mục đích học tập của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY** là dùng ranh giới application module để kiểm chứng cả thiết kế lẫn hành vi runtime. Bốn nguồn thông tin sau trả lời các câu hỏi khác nhau:

| Nguồn | Câu hỏi chính | Điều không được suy ra |
| --- | --- | --- |
| `GET /actuator/modulith` | Ứng dụng đang phát hiện những module nào, quan hệ phụ thuộc của chúng là gì? | Không chứng minh một event cụ thể đã chạy hoặc một request đã gọi module đó. |
| `ApplicationModules` / `Documenter` | Kiến trúc được suy ra từ source và sơ đồ tài liệu như thế nào? | Không khẳng định endpoint HTTP hay hạ tầng runtime đang mở. |
| `module.events.published` và metrics của ứng dụng | Có bao nhiêu event được publish; tốc độ, lỗi nghiệp vụ được đo ra sao? | Không khẳng định mọi listener đã xử lý thành công. |
| Micrometer tracing/spans qua các module | Request/event đi qua những module nào, thời gian tương tác ra sao? | Span thiếu có thể do sampling hoặc mất context propagation, không đồng nghĩa endpoint `modulith` lỗi. |

Nếu endpoint `modulith` xuất JSON đúng nhưng bạn vẫn không thấy trace, hãy kiểm tra dependency observability, bridge OpenTelemetry/Brave, exporter, sampling và cách truyền tracing context qua thread/async executor. Đó là tuyến chẩn đoán khác với việc đăng ký Actuator endpoint. Nếu muốn kiểm tra event delivery, cần thêm event publication registry và trạng thái của từng listener; `/actuator/modulith` là dữ liệu kiến trúc tĩnh theo runtime model, không phải event processing registry.

## 11. Kiểm thử hồi quy và tiêu chí hoàn thành

Sau khi sửa, cần kiểm chứng từ hai góc nhìn: **HTTP endpoint** và **nội dung module**.

### 11.1. HTTP-level integration test (ý tưởng)

Với integration test khởi động ứng dụng web thật, gọi `GET /actuator/modulith` bằng tài khoản vận hành phù hợp và kiểm tra `200`, `Content-Type: application/json`, và JSON có module mong đợi. Bảo đảm test dùng đúng management port nếu tách riêng, và profile có bật exposure.

Một test chỉ làm:

~~~java
var modules = ApplicationModules.of(ShopApplication.class);
modules.verify();
~~~

sẽ hữu ích cho kiến trúc nhưng **không kiểm thử HTTP**. Một test Actuator phải khởi động web environment với dependency và cấu hình quản trị như môi trường triển khai.

### 11.2. Checklist xác minh

- [ ] Xác nhận Spring Boot và Spring Modulith tương thích, các JAR Actuator có trong runtime artifact.
- [ ] Xác nhận `modulith` nằm trong `management.endpoints.web.exposure.include`, không bị `exclude` hoặc chính sách `access` vô hiệu.
- [ ] Xác nhận URL thực: host, scheme, cổng management, context path, base path, path mapping.
- [ ] Truy cập trực tiếp từ mạng quản trị và quan sát HTTP 200 cùng JSON danh sách module.
- [ ] Nếu có Spring Security/gateway, thử lại với đúng quyền vận hành; bảo đảm người không có quyền không xem được metadata.
- [ ] Đối chiếu module graph thực tế với package và kết quả kiểm chứng bằng `ApplicationModules`.
- [ ] Kiểm tra lại sau build/deploy trên môi trường mục tiêu; có log, version và kết quả curl làm bằng chứng.
- [ ] Giữ endpoint trên kênh quản trị bảo mật, không expose các endpoint nhạy cảm khác chỉ vì mục đích chẩn đoán.

### Bài tập thực hành

1. Tạo ứng dụng Spring Boot gồm hai package trực tiếp `orders` và `notifications` dưới package của `@SpringBootApplication`.
2. Chỉ thêm `spring-boot-starter-actuator`; bật `health` và thử `modulith`. Ghi lại HTTP status.
3. Thêm `spring-modulith-actuator`, bật `exposure.include` và so sánh JSON trước/sau.
4. Đặt `management.server.port: 9090`, sau đó đặt `management.endpoints.web.base-path: /manage`. Giải thích vì sao URL cũ 404.
5. Cấu hình Spring Security yêu cầu vai trò vận hành; so sánh 401/403 với 200 khi dùng tài khoản phù hợp.
6. Chuyển `ShopApplication` sang package con không phù hợp trong nhánh thử nghiệm; quan sát cách nhận diện module thay đổi; sau đó khôi phục.
7. Bật observability và phát một domain event giữa hai module. Phân biệt JSON `modulith`, metric event publish và trace cho lời gọi thực tế.

## 12. Câu hỏi tự đánh giá

1. Vì sao dự án có `spring-modulith-starter-core` chưa chắc có `/actuator/modulith`?
2. `@Endpoint(id = "modulith")` cho thấy điều gì về URL mặc định? Vì sao không nên suy từ tên lớp `ApplicationModulesEndpoint`?
3. Khi `/actuator/health` 200 nhưng `modulith` 404, ba nguyên nhân cần kiểm tra đầu tiên là gì?
4. `management.endpoints.web.exposure.include` và `management.endpoint.modulith.access` khác nhau ở mục đích nào?
5. Khi `management.server.port=9090`, vì sao gọi `http://localhost:8080/actuator/modulith` có thể thất bại?
6. Khi nhận 401/403, có nên thêm `permitAll()` hoặc bỏ Spring Security để làm endpoint xuất hiện không? Phương án bảo mật nào phù hợp hơn?
7. Nếu endpoint trả JSON nhưng thiếu một module, nên kiểm tra cấu trúc package và cơ chế phát hiện ra sao?
8. Có thể dùng `GET /actuator/modulith` để kết luận một event đã được listener xử lý thành công không? Tại sao?
9. Khi `GET /actuator` không liệt kê `modulith`, vì sao vẫn cần kiểm tra URL cụ thể và cấu hình discovery?
10. Bằng chứng nào cần giữ lại để xác nhận lỗi đã được sửa trên môi trường triển khai, không chỉ trên máy phát triển?

## Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): dependency Actuator, endpoint `modulith`, cấu trúc JSON và observability.
- [Spring Modulith — Application Modules / Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): quy tắc package, module discovery và verification.
- [Spring Modulith — ApplicationModulesEndpoint API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/actuator/ApplicationModulesEndpoint.html): `@Endpoint(id = "modulith")`.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, endpoint access, discovery và security.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): port, context path, base path và path mapping.
- [Spring Modulith — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html): cấu hình module runtime và tùy biến phát hiện.

