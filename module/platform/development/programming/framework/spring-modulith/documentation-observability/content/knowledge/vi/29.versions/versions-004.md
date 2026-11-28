# Kiểm tra thay đổi endpoint modulith

## 1. Vấn đề đặt ra

Trong chương **Phiên bản** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, chúng ta học cách kiểm tra ranh giới *application module* và những tương tác giữa chúng trong ứng dụng Spring Boot. Spring Modulith giúp dựng module graph, expose cấu trúc qua Actuator và bổ sung thông tin runtime thông qua event metrics, tracing, context propagation.

Giả sử ứng dụng `shop` đang sử dụng Spring Boot 3.5 và Spring Modulith 1.4. Sau khi nâng cấp lên Spring Boot 4 và Spring Modulith 2.x, nhóm phát triển gặp một trong các tình huống:

- `GET /actuator/modulith` từng trả `200 OK`, nhưng giờ trả `404`, `401` hoặc `403`.
- Endpoint vẫn trả `200`, nhưng module graph mất module hoặc có một cạnh phụ thuộc mới.
- Endpoint hoạt động, song dashboard metric/trace không còn hiển thị như trước.
- Custom security configuration không biên dịch do package Spring Boot thay đổi.

Muốn xác định **có thực sự xảy ra thay đổi endpoint** hay không, cần phân biệt ba hợp đồng:

1. **HTTP contract:** endpoint ID, URL, phương thức, status, quyền truy cập và việc expose endpoint.
2. **Data contract:** cấu trúc JSON, module ID, base package, dependency và loại dependency.
3. **Runtime observability contract:** event metrics, spans, tracing và khả năng truyền context sang async listener.

**Mục tiêu:** học cách chụp baseline phiên bản cũ, chạy kiểm tra ở phiên bản mới, so sánh đúng bản chất dữ liệu, giải thích khác biệt và xây dựng kiểm thử hồi quy. Nội dung dùng dữ liệu ứng dụng giả định, vì module graph cụ thể tùy thuộc source code từng dự án.

> Tài liệu chính thức của Spring Modulith **1.4.14** và **2.2.0** đều mô tả endpoint có ID `modulith` và đường dẫn mặc định `/actuator/modulith`. Việc nâng major version **không tự chứng minh** endpoint đã đổi tên. Chúng ta phải kiểm tra dependency, cấu hình và dữ liệu của bản chạy thực tế.

## 2. Endpoint `modulith` cung cấp gì?

Spring Modulith cung cấp *Application Module Actuator*. Khi được đăng ký và expose qua HTTP, URL mặc định là:

~~~http
GET http://localhost:8080/actuator/modulith
~~~

Response JSON có dạng ánh xạ tên kỹ thuật module sang thông tin về module và quan hệ phụ thuộc:

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

Các trường cần nắm:

| JSONPath | Ý nghĩa | Điều cần kiểm tra sau upgrade |
| --- | --- | --- |
| `$.{moduleName}` | ID kỹ thuật của application module | Đúng tập module bắt buộc |
| `$.{moduleName}.displayName` | Tên hiển thị | Không đổi ngoài dự kiến nếu dashboard dùng tên này |
| `$.{moduleName}.basePackage` | Java package gốc của module | Không đổi hoặc đã được review khi refactor |
| `$.{moduleName}.dependencies[]` | Các phụ thuộc đi ra từ module | So sánh như tập hợp các cạnh |
| `$.{moduleName}.dependencies[].target` | ID module đích | Luôn tham chiếu một module tồn tại |
| `$.{moduleName}.dependencies[].types[]` | Loại phụ thuộc, như `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` | So sánh như tập hợp, không dựa vào thứ tự mảng |
| `$.{moduleName}.parent` | Module cha, tùy chọn | Chỉ bắt buộc nếu có nested modules |
| `$.{moduleName}.nested` | Danh sách module con, tùy chọn | Chấp nhận vắng mặt nếu không có nested modules |

Endpoint mô tả **mô hình kiến trúc được phát hiện**. Nó không phải trang hình ảnh của `Documenter`, không phải Event Publication Registry và không phản ánh trạng thái thành công của từng listener. Metric `module.events.published` nói về việc event được phát; tracing nói về tương tác đã được instrument và lấy mẫu. Vì vậy phải kiểm thử ba bề mặt này riêng.

Khi Actuator discovery hoạt động, `GET /actuator` có thể có `_links.modulith.href`. Nhưng nếu discovery bị tắt hoặc endpoint nằm trên cổng quản trị riêng, việc không thấy link ở URL đã thử **chưa đủ** để kết luận endpoint không tồn tại.

## 3. Đối chiếu phiên bản có căn cứ

Đến **27/11/2026**, Spring Modulith **2.2.0** đã được công bố ngày 19/11/2026. Bảng dưới đây tổng hợp các thế hệ liên quan đến bài thực hành:

| Thế hệ Modulith | Nền tảng Spring Boot chính của nhánh | Điểm cần chú ý khi upgrade |
| --- | --- | --- |
| `1.4.x` (ví dụ 1.4.14) | Boot 3.5 | Chụp baseline HTTP và graph trước khi chuyển Boot 4 |
| `2.0.x` (ví dụ 2.0.10) | Boot 4.0 / Framework 7 | Nền tảng lớn thay đổi, có nâng cấp event publication lifecycle |
| `2.1.x` (ví dụ 2.1.3) | Boot 4.1 | Phát triển observability và sự kiện/tính năng test |
| `2.2.0` | Boot 4.2 / Framework 7.1 | Event completion trong listener transaction, trạng thái `ABANDONED`, quy tắc dependency mới |

Đây là mô tả **nền tảng từng thế hệ**, không phải cam kết mọi cặp phiên bản đều tương thích. Trước khi nâng, đọc release notes và compatibility của đúng release.

### 3.1. So sánh tài liệu Spring Modulith 1.4 và 2.2

| Nội dung | 1.4.14 | 2.2.0 |
| --- | --- | --- |
| ID Actuator | `modulith` | `modulith` |
| URL mặc định | `/actuator/modulith` | `/actuator/modulith` |
| Thư viện endpoint | `spring-modulith-actuator` | `spring-modulith-actuator` |
| Starter gồm Actuator + observability | `spring-modulith-starter-insight` | `spring-modulith-starter-insight` |
| JSON cơ bản | `displayName`, `basePackage`, `dependencies` | Vẫn công bố các trường này |
| Loại dependency | `DEFAULT`, `USES_COMPONENT`, `EVENT_LISTENER` | Cùng các loại nêu trong tài liệu |
| Observability riêng lẻ | Tài liệu dùng `spring-modulith-observability` | Tài liệu dùng `spring-modulith-observability-core` và `spring-modulith-observability-api` |

Bảng trên dựa trên [tài liệu 1.4](https://docs.spring.io/spring-modulith/reference/1.4/production-ready.html) và [tài liệu 2.2](https://docs.spring.io/spring-modulith/reference/production-ready.html). Thay đổi ở observability dependency **không đồng nghĩa** endpoint HTTP đã đổi. Các tính năng registry của 2.x cũng cần được kiểm chứng riêng với lưu trữ và listener.

### 3.2. Đồng bộ dependency

Chỉ nâng Spring Modulith cùng hệ Spring Boot tương thích. Ví dụ khi ứng dụng đã chọn Boot 4.2 và Modulith 2.2.0, dùng BOM của Spring Modulith:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>2.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

`spring-modulith-starter-insight` tích hợp các phần Actuator và observability. Nếu chỉ cần endpoint, có thể dùng `spring-modulith-actuator` và `spring-boot-starter-actuator` theo release tương ứng. Không trộn các JAR Modulith 1.x và 2.x trong cùng ứng dụng.

Xác minh dependency **thực sự** được đưa vào runtime:

~~~powershell
# Maven:
mvn dependency:tree

# Gradle Wrapper trên Windows:
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Một dependency chỉ có trong `testImplementation` hoặc trong classpath IDE không đảm bảo có ở JAR/container production.

## 4. Ghi baseline trước khi nâng cấp

Hồ sơ baseline cần tối thiểu:

1. Git commit, image/JAR digest, Java version, Boot version, Modulith version.
2. Profile đang chạy; host, `server.port`, `management.server.port`, context path, management base path và path mapping.
3. Runtime dependencies, cấu hình exposure/access, Spring Security và gateway.
4. HTTP status, content type, body JSON từ endpoint với tài khoản có quyền.
5. Module IDs, package, các module lồng nhau và dependency graph đã chuẩn hóa.
6. Kết quả `ApplicationModules.verify()`, và metrics/traces có liên quan nếu mục tiêu nâng cấp bao gồm observability.

Ví dụ đưa Actuator lên cổng quản trị riêng:

~~~yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,info,modulith"
~~~

Lúc này URL mặc định là `http://localhost:9090/actuator/modulith`.

Đọc và lưu JSON với PowerShell:

~~~powershell
$endpoint = "http://127.0.0.1:9090/actuator/modulith"
$response = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -ErrorAction Stop

if ($response.StatusCode -ne 200) {
    throw "Expected HTTP 200"
}

$graph = $response.Content | ConvertFrom-Json
$moduleNames = @($graph.PSObject.Properties.Name)
if ($moduleNames.Count -eq 0) {
    throw "Module graph is empty"
}

$response.Content | Set-Content -LiteralPath ".\modulith-before.json" -Encoding UTF8
Write-Host "Recorded $($moduleNames.Count) modules"
~~~

Đây là ví dụ chạy từ máy quản trị có quyền. Nếu endpoint yêu cầu Basic/OAuth/mTLS, thêm cơ chế xác thực từ secret/environment; không hardcode credential vào script hay snapshot. Bảo vệ các file JSON vì chúng tiết lộ tên package và phụ thuộc nội bộ.

Để ghi status và headers:

~~~powershell
curl.exe -i "http://127.0.0.1:9090/actuator"
curl.exe -i "http://127.0.0.1:9090/actuator/modulith"
~~~

### 4.1. Kiểm tra kiến trúc trực tiếp từ source

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithStructureTest {

    @Test
    void verifiesModules() {
        ApplicationModules modules =
            ApplicationModules.of(ShopApplication.class);
        modules.verify();
        System.out.println(modules);
    }
}
~~~

`ShopApplication` giả định là class ứng dụng. `ApplicationModules.verify()` kiểm tra cấu trúc được phát hiện; nó không đảm bảo endpoint đã được HTTP exposure. Nếu ứng dụng tùy biến module discovery, cần dùng cùng customization trong **production source**, không chỉ trong test.

## 5. Quy trình kiểm tra sau nâng cấp

~~~mermaid
flowchart TD
    A["Chụp baseline phiên bản cũ"] --> B["Chọn Boot + Modulith tương thích"]
    B --> C["Build và chạy với cấu hình tương đương"]
    C --> D{"GET modulith trả 200?"}
    D -->|Không| E["Dependency, exposure/access, port/path, security, proxy"]
    D -->|Có| F["Parse JSON và chuẩn hóa graph"]
    F --> G{"Graph khác baseline?"}
    G -->|Có| H["Kiểm tra code/package, discovery, release notes"]
    G -->|Không| I["Kiểm tra metrics, trace và context propagation"]
    H --> I
    I --> J["Ghi báo cáo và regression tests"]
~~~

Nên giữ nguyên mã nghiệp vụ và cấu hình càng nhiều càng tốt khi muốn đo riêng tác động của framework. Nếu đồng thời refactor package `orders`, thay gateway và nâng phiên bản, cần phân loại từng nguyên nhân trước khi đưa ra kết luận.

### 5.1. Kiểm tra HTTP contract

| HTTP status | Cách diễn giải | Hành động |
| --- | --- | --- |
| `200` và JSON | Endpoint đang truy cập được | Tiếp tục kiểm tra dữ liệu |
| `404` | Sai URL/port/path, thiếu endpoint, chưa expose, hoặc proxy ẩn | Kiểm tra dependency, Actuator, routing |
| `401` | Thiếu xác thực | Kiểm tra Basic/OAuth/SSO và role |
| `403` | Thiếu quyền hoặc bị chính sách mạng chặn | Kiểm tra SecurityFilterChain/gateway |
| `302` | Redirect tới đăng nhập | Xem `Location` |
| `500` | Lỗi khởi tạo/đọc endpoint hoặc tích hợp framework | Đọc exception và auto-config report |
| Timeout / connection refused | Request chưa đến HTTP server | Kiểm tra DNS, cổng, TLS, firewall |

Một reverse proxy có thể chủ động trả `404` thay `403`. Nếu nghi ngờ, so sánh URL public với việc gọi trực tiếp trên cổng quản trị nội bộ.

### 5.2. Kiểm tra JSON contract

Các invariant nên kiểm tra:

- Body là JSON object không rỗng.
- Mọi module bắt buộc còn xuất hiện.
- `basePackage` là chuỗi hợp lệ, đúng ranh giới mong đợi.
- `dependencies[]` là mảng, mọi `target` đều trỏ đến một module đang tồn tại.
- `types[]` chứa những giá trị loại dependency có ý nghĩa.
- `parent`/`nested` là tùy chọn; chỉ yêu cầu nếu có nested modules.
- Thêm field mới không làm client thất bại; thứ tự các key JSON không ảnh hưởng.

Ví dụ hai JSON sau có cùng ý nghĩa:

~~~json
{"notifications":{"displayName":"Notifications",
  "basePackage":"com.example.shop.notifications",
  "dependencies":[{"target":"orders",
    "types":["EVENT_LISTENER","USES_COMPONENT"]}]}}
~~~

~~~json
{"notifications":{"dependencies":[{"types":["USES_COMPONENT","EVENT_LISTENER"],
  "target":"orders"}],
  "basePackage":"com.example.shop.notifications",
  "displayName":"Notifications"}}
~~~

So sánh nguyên chuỗi JSON sẽ tạo lỗi giả. Cần sắp xếp module ID, dependency target và loại dependency trước khi so sánh.

## 6. Chuẩn hóa và so sánh semantic snapshot

Quy tắc chuẩn hóa:

1. Lấy ID mỗi module, sắp xếp.
2. Ghi `basePackage`, `displayName`, `parent`, `nested` nếu có.
3. Với từng dependency, ghi `source -> target : sorted(types)`.
4. Sắp xếp các cạnh, so theo tập hợp.
5. Báo module thêm/bớt, package đổi, cạnh đổi và field mà consumer cần dùng.

Ví dụ script PowerShell (chạy khi đã có hai file baseline):

~~~powershell
function Get-ModuleSignature([string]$filePath) {
    $graph = Get-Content -LiteralPath $filePath -Raw | ConvertFrom-Json

    foreach ($property in $graph.PSObject.Properties) {
        $id = $property.Name
        $module = $property.Value

        $edges = @($module.dependencies | ForEach-Object {
            $types = @($_.types | Sort-Object) -join ","
            "{0}>{1}:{2}" -f $id, $_.target, $types
        } | Sort-Object)

        $nested = @($module.nested | Sort-Object) -join ","
        $signature = "{0}|{1}|{2}|{3}|{4}|{5}" -f $id, $module.basePackage, $module.displayName, $module.parent, $nested, (@($edges) -join ";")

        [pscustomobject]@{ Module = $id; Signature = $signature }
    }
}

$before = @(Get-ModuleSignature ".\modulith-before.json")
$after = @(Get-ModuleSignature ".\modulith-after.json")
$diff = Compare-Object -ReferenceObject $before -DifferenceObject $after -Property Module,Signature
$diff | Format-Table -AutoSize
if ($diff) {
    throw "Review module graph difference before accepting upgrade"
}
~~~

Script trên minh họa một contract tương đối chặt, tính cả `displayName`. Nếu tên hiển thị được phép thay đổi, chỉ giữ các trường bắt buộc thực sự cho consumer. Đừng tự động làm mới snapshot mỗi khi test thất bại; phải review diff.

| Khác biệt | Nguyên nhân cần điều tra |
| --- | --- |
| Module `inventory` biến mất | Package gốc, nested module hoặc detection strategy thay đổi |
| Cạnh `notifications -> orders : EVENT_LISTENER` bị mất | Listener/event type hoặc cấu trúc module thay đổi |
| Thêm `billing -> orders : USES_COMPONENT` | Thêm phụ thuộc bean xuyên module |
| Chỉ đổi `displayName` | Metadata hiển thị khác; có thể ảnh hưởng dashboard |
| Chỉ đảo thứ tự key và types | Thứ tự serialization khác, không nhất thiết breaking |
| Có thêm field JSON | Xem consumer có chấp nhận field mới |

Tổng số module không phải phép kiểm tra đủ mạnh: một module bị mất và một module khác được thêm có thể giữ nguyên số đếm.

## 7. Những khác biệt dễ bị nhầm là do phiên bản endpoint

### 7.1. Thiếu dependency hoặc thiếu HTTP exposure

Một ứng dụng có `spring-modulith-starter-core` chưa chắc có Actuator endpoint. Nếu không dùng `spring-modulith-starter-insight`, cần tích hợp phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-starter-core'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-actuator'
}
~~~

Bật HTTP exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith"
~~~

`management.endpoints.web.exposure.exclude` ưu tiên hơn `include`. Nếu `modulith` nằm trong danh sách exclude, việc include không đủ.

### 7.2. Endpoint access model của Boot

Trong các nhánh Boot hỗ trợ `management.endpoints.access.*`, access đặt thành `none` có thể khiến endpoint bị loại khỏi context. Ví dụ cấu hình chỉ mở quyền đọc cho `health` và `modulith`:

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

Kiểm tra thêm `management.endpoints.access.max-permitted`; nếu được đặt `none` ở cấp global, rule access riêng có thể không đủ. Một số phiên bản Boot cũ có cơ chế enabled/disabled khác; tra tài liệu đúng release.

### 7.3. Management port hoặc URL đã đổi

~~~yaml
server:
  port: 8080
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        modulith: modules
      exposure:
        include: "health,modulith"
~~~

URL thực tế trở thành `http://localhost:9090/manage/modules`. Endpoint ID **vẫn là `modulith`**. `404` ở `http://localhost:8080/actuator/modulith` là kết quả hợp lý do cấu hình, không cho biết JSON schema đã đổi.

Nếu dùng cùng cổng với ứng dụng, kiểm tra `server.servlet.context-path`; nếu dùng management port riêng, còn có `management.server.base-path`. Kiểm tra path rewrite của gateway/ingress.

### 7.4. Spring Security khác khi nâng Boot

Nếu nhận `401`/`403`, kiểm tra filter chain và quyền của tài khoản truy cập. Nên match Actuator theo ID bằng `EndpointRequest.to("modulith")` cùng chính sách role/scope phù hợp.

Một ví dụ về khác biệt **API tích hợp của Spring Boot**, không phải URL HTTP:

~~~java
// Spring Boot 3.x
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;

// Spring Boot 4.x
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
~~~

Spring Boot có thể ngừng dùng auto-configuration security mặc định cho Actuator khi ứng dụng khai báo custom `SecurityFilterChain`; cần kiểm tra mọi chain và endpoint khác. Không sử dụng `permitAll()` toàn cục chỉ để khắc phục 401/403. Module graph chứa thông tin kiến trúc, nên chỉ cho quyền truy cập qua kênh quản trị phù hợp.

### 7.5. Module discovery khác sau upgrade

Khi HTTP trả 200 nhưng graph thay đổi, kiểm tra:

- Package của `@SpringBootApplication`, `@Modulithic` và các package con trực tiếp.
- Các annotation `@ApplicationModule`, named interfaces và nested module.
- Tùy biến module detection được đặt ở production hay chỉ trong test.
- Refactor chuyển gọi bean trực tiếp sang event, làm thay đổi `dependencies[].types`.
- Chênh lệch runtime classpath, AOT/native image hoặc classpath IDE.
- Các cải tiến/bug fix module discovery theo release notes đích.

`ApplicationModules.verify()` chạy trong test có thể xanh mà endpoint production vẫn có graph khác, nếu cơ chế discovery hoặc classpath hai môi trường khác nhau.

## 8. Kiểm thử hồi quy sau nâng cấp

| Kiểm thử | Bằng chứng |
| --- | --- |
| Dependency smoke | Runtime có Actuator và Modulith actuator hoặc insight starter |
| HTTP endpoint | GET đúng management URL trả 200 và JSON |
| JSON contract | Có module ID, package và dependencies đúng kiểu |
| Semantic snapshot | Các module và cạnh quan trọng khớp baseline |
| Kiến trúc nguồn | `ApplicationModules.verify()` không báo vi phạm |
| Quyền truy cập | User được phép đọc, user khác nhận 401/403 |
| Event metrics và trace | Có dữ liệu runtime sau khi kích hoạt luồng nghiệp vụ, context propagation phù hợp |

### Ví dụ HTTP contract test

Đoạn mã JUnit bên dưới giả định ứng dụng chạy trên management port đã cấu hình và có `orders`, `notifications`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;

class ModulithHttpContractTest {

    @Test
    void returnsExpectedModules() throws Exception {
        String url = System.getProperty(
            "modulith.management.url",
            "http://localhost:9090/actuator/modulith"
        );

        var request = HttpRequest.newBuilder(URI.create(url))
            .GET()
            .build();
        var response = HttpClient.newHttpClient().send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());

        JsonNode graph = new ObjectMapper().readTree(response.body());
        assertTrue(graph.isObject());
        assertTrue(graph.has("orders"));
        assertTrue(graph.has("notifications"));
        assertEquals("com.example.shop.orders",
            graph.path("orders").path("basePackage").asText());

        JsonNode dependencies =
            graph.path("notifications").path("dependencies");
        assertTrue(dependencies.isArray());

        boolean pointsToOrders = false;
        for (JsonNode dependency : dependencies) {
            if ("orders".equals(dependency.path("target").asText())) {
                pointsToOrders = true;
                break;
            }
        }
        assertTrue(pointsToOrders);
    }
}
~~~

Đây là mã minh họa: Java test cần HTTP server đang hoạt động, dependency Jackson phù hợp và authentication của environment nếu endpoint được bảo vệ. Khi nâng Boot 4, kiểm tra lựa chọn Jackson/mapping theo dependency thực tế. Với CI, truyền URL qua cấu hình test; không hardcode credential. Mẫu này kiểm tra những bất biến tối thiểu, còn snapshot ở mục 6 kiểm tra toàn graph.

Ma trận tình huống nên có:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Bản cũ chạy đúng cấu hình | 200, baseline lưu được |
| Bản mới và cùng source code | 200, schema hợp lệ, graph tương đương nếu không dự kiến đổi |
| Bỏ `modulith` khỏi exposure | HTTP không truy cập được endpoint |
| Đổi management port hoặc path mapping | URL mới hoạt động |
| User không có quyền | 401/403 theo chính sách |
| Cố tình đổi package trong bản thử nghiệm | Semantic snapshot phát hiện |
| Đổi listener sự kiện sang gọi trực tiếp | Có thể phát hiện thay đổi loại dependency |
| Ngừng exporter trace | Endpoint vẫn có thể 200, trace không đến backend |
| Async context propagation mất | Endpoint vẫn hoạt động nhưng trace bị đứt mạch |

## 9. Quy trình xử lý một số lỗi điển hình

### A. Sau nâng cấp endpoint trả 404

1. Xác minh đúng host/cổng quản trị bằng `/actuator/health`.
2. Xem runtime dependency, tránh nhầm dependency chỉ có ở test.
3. Kiểm tra `exposure.include`, `exclude` và endpoint access model.
4. Kiểm tra management base path, path mapping, context path, proxy.
5. Xem startup log và condition evaluation report nếu endpoint vẫn mất.
6. Chỉ khi HTTP 200, mới chuyển sang kiểm tra dữ liệu JSON.

### B. Trả 200 nhưng thiếu module

1. Parse JSON, so module ID và base package với baseline.
2. So các cạnh theo tập hợp và phân biệt dependency type.
3. Kiểm tra cấu trúc package, module detection, named interfaces.
4. Chạy `ApplicationModules.verify()` với cấu hình phù hợp.
5. Đối chiếu source code và release notes; xác nhận thay đổi mong muốn trước khi chấp nhận snapshot mới.

### C. Graph không đổi nhưng metric/trace mất

Kiểm tra dependency `spring-modulith-starter-insight` hoặc những artifact observability riêng, Micrometer registry, tracing bridge và exporter, sampling, TaskDecorator/context propagation cho async executor. `module.events.published` đo số event được phát, không chứng minh listener đã xử lý thành công. Không sửa endpoint `modulith` nếu vấn đề nằm ở exporter hoặc event lifecycle.

### D. Custom Actuator Security lỗi sau khi chuyển Boot 3 sang Boot 4

Kiểm tra package `EndpointRequest`, cấu hình `SecurityFilterChain`, endpoint access và test 200/401/403. HTTP ID có thể giữ nguyên trong khi Java import hoặc framework security APIs thay đổi.

## 10. Báo cáo thay đổi và rollback

Một báo cáo có thể review nên ghi:

~~~text
BASELINE:
  Spring Boot: ...
  Spring Modulith: ...
  Commit/image: ...
  Management URL: ...
  GET modulith status: ...
  Graph modules and dependencies: ...

CANDIDATE:
  Spring Boot: ...
  Spring Modulith: ...
  Commit/image: ...
  Management URL: ...
  GET modulith status: ...
  Graph modules and dependencies: ...

DIFF:
  HTTP path and access: ...
  JSON schema: ...
  Added/removed modules: ...
  Dependency edges and types: ...
  Event metrics/tracing/context propagation: ...
  Decision: accept, fix or rollback
~~~

Chỉ cập nhật baseline khi diff đã được review. Nếu rollback bản nâng major version, cần đánh giá thêm migration/schema của **Event Publication Registry** và trạng thái dữ liệu do phiên bản mới ghi ra: endpoint trả 200 sau rollback **không chứng minh** việc xử lý event và database tương thích.

## 11. Bài thực hành

Giả sử ứng dụng `com.example.shop` có ba module `orders`, `inventory`, `notifications`; `notifications` lắng nghe sự kiện từ `orders`.

1. Chạy bản dùng Spring Modulith 1.4 và Spring Boot tương thích, expose `modulith` trong mạng quản trị.
2. Chụp `modulith-before.json` và metadata của bản chạy.
3. Kiểm tra đủ ba module, các `basePackage` và ít nhất một cạnh `notifications -> orders : EVENT_LISTENER`.
4. Nâng lên một nhánh 2.x với Spring Boot tương thích, kiểm tra runtime classpath.
5. Lưu `modulith-after.json` rồi chuẩn hóa và so với baseline.
6. Thử bỏ `modulith` khỏi exposure rồi khôi phục; giải thích vì sao endpoint biến mất mà JSON schema không đổi.
7. Thử đổi management port và path mapping; chứng minh URL có thể đổi dù ID vẫn là `modulith`.
8. Kiểm tra user không đủ quyền nhận 401/403; user vận hành xem được dữ liệu.
9. Phát event giữa các module, kiểm tra metrics/tracing riêng và giải thích liên hệ với module graph.
10. Viết báo cáo quyết định ở mục 10; phân biệt thay đổi framework và thay đổi cấu hình/kiến trúc.

## 12. Câu hỏi tự đánh giá

1. Vì sao nâng Spring Modulith 2.x không tự chứng minh endpoint `modulith` đã đổi tên?
2. Khác biệt giữa endpoint ID và URL quản trị cuối cùng là gì?
3. Khi `GET /actuator` không có link `modulith`, vì sao chưa đủ kết luận endpoint bị loại?
4. Vì sao so JSON byte-by-byte có thể cho lỗi giả?
5. Tại sao cần kiểm tra `dependencies[].target` tham chiếu module tồn tại?
6. Nếu số module giữ nguyên nhưng một module biến mất, test nào phát hiện được?
7. `exposure.include`, endpoint `access` và Spring Security khác nhau thế nào?
8. Vì sao import `EndpointRequest` ở Java có thể đổi sau khi nâng Boot, dù HTTP URL giữ nguyên?
9. Nếu endpoint 200 nhưng tracing không có dữ liệu, nên kiểm tra thành phần nào?
10. Vì sao `module.events.published` không cho biết listener đã xử lý thành công?
11. Khi nào được chấp nhận baseline mới?
12. Vì sao rollback code mà không kiểm tra event registry có thể còn rủi ro?

## Tài liệu tham khảo

- [Spring Modulith 1.4 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/1.4/production-ready.html): endpoint, artifact và JSON schema nhánh 1.4.
- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): endpoint và observability nhánh 2.2.
- [Spring Modulith — Compatibility Appendix](https://docs.spring.io/spring-modulith/reference/appendix.html): đối chiếu phiên bản.
- [Spring Modulith 2.0 GA](https://spring.io/blog/2025/11/21/spring-modulith-2-0-ga-1-4-5-and-1-3-11-released/): nâng nền tảng Boot 4/Framework 7.
- [Spring Modulith 2.1 GA](https://spring.io/blog/2026/06/11/spring-modulith-2-1-ga-2-0-7-and-1-4-12-released/): thay đổi của thế hệ 2.1.
- [Spring Modulith 2.2 GA](https://spring.io/blog/2026/11/19/spring-modulith-2-2-ga-2-1-3-and-2-0-10-released/): thay đổi của thế hệ 2.2 công bố ngày 19/11/2026.
- [Spring Boot 3.4 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html): exposure, access và bảo mật.
- [Spring Boot 4 — Actuator Endpoints](https://docs.spring.io/spring-boot/4.0/reference/actuator/endpoints.html): Actuator security và `EndpointRequest`.
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management port và path mapping.

