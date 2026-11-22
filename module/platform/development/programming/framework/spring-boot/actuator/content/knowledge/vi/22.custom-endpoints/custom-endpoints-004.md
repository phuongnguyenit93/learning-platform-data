# Ánh xạ operation sang HTTP method và mã phản hồi

## 1. Từ phương thức Java đến hợp đồng HTTP

Khi viết endpoint Actuator, ta khai báo các **thao tác (operation)** bằng annotation. Khi endpoint được công bố qua web, Spring Boot tạo điều kiện ánh xạ yêu cầu dựa trên định danh endpoint, loại thao tác, tham số chọn đường dẫn và kiểu dữ liệu được hỗ trợ.

Một phương thức Java có tên `update` không tự trở thành PUT. Một phương thức có tên `delete` cũng không tự trở thành DELETE. **Annotation operation mới quyết định loại thao tác**, từ đó Actuator chọn HTTP method tương ứng.

Cần phân biệt ba phần của hợp đồng:

| Phần | Câu hỏi cần trả lời |
| --- | --- |
| Định tuyến yêu cầu | Gọi đường dẫn nào, dùng HTTP method nào? |
| Tiếp nhận đầu vào | Giá trị nằm ở path, query hay JSON body? Có chuyển được sang kiểu Java không? |
| Tạo phản hồi | Trả mã trạng thái nào? Có body không? Body được biểu diễn như thế nào? |

Bài dùng Spring Boot 3.3.x và ví dụ Java 21. Các mã phản hồi được mô tả trong điều kiện endpoint đã được đăng ký, bật, công bố qua HTTP và yêu cầu được phép đi tới lớp xử lý. Một bộ lọc bảo mật hoặc proxy có thể kết thúc yêu cầu trước đó.

## 2. Bảng ánh xạ operation sang HTTP method

| Annotation trên phương thức | Loại thao tác | HTTP method chính khi công bố qua web |
| --- | --- | --- |
| `@ReadOperation` | Đọc thông tin | GET |
| `@WriteOperation` | Thay đổi hoặc thực hiện thao tác quản lý | POST |
| `@DeleteOperation` | Xóa hoặc loại bỏ trạng thái/tài nguyên quản lý | DELETE |

Đây là quy ước của web endpoint Actuator trong [Spring Boot 3.3: HTTP method của operation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates.http-method).

Những hệ quả cần nhớ:

- Không đổi `@WriteOperation` thành PUT bằng cách đặt tên phương thức là `put`.
- `@WriteOperation` cũng không tự tạo PATCH.
- Tên phương thức giúp người đọc mã hiểu ý nghĩa, nhưng không phải một đoạn URL được nối thêm tự động.
- Cùng một đường dẫn có thể có GET, POST và DELETE nếu các operation tương ứng được khai báo.
- Hai phương thức đọc có cùng đường dẫn không tự được phân biệt chỉ nhờ tên Java hoặc kiểu đối tượng trả về. Cần tránh các ánh xạ trùng nhau.

Đặc tính `produces` trên annotation, chẳng hạn `@WriteOperation`, mô tả kiểu nội dung trả về; nó không phải thuộc tính chọn HTTP method. Xem [hợp đồng WriteOperation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/WriteOperation.html).

Nếu cần một hợp đồng HTTP không phù hợp với mô hình operation của Actuator, hãy chọn điểm mở rộng dành cho web hoặc một API controller thích hợp với mục đích của chức năng, thay vì suy diễn thêm khả năng từ tên phương thức.

## 3. Đường dẫn và đầu vào cùng tham gia ánh xạ

Giả sử endpoint có `id = "flags"`, dùng base path mặc định `/actuator`:

| Khai báo minh họa | Đường dẫn và phương thức |
| --- | --- |
| `@ReadOperation snapshot()` | GET /actuator/flags |
| `@ReadOperation find(@Selector String name)` | GET /actuator/flags/{name} |
| `@WriteOperation put(String name, boolean enabled)` | POST /actuator/flags |
| `@WriteOperation update(@Selector String name, boolean enabled)` | POST /actuator/flags/{name} |
| `@DeleteOperation delete(@Selector String name)` | DELETE /actuator/flags/{name} |

Các khai báo trong bảng rút gọn phần kiểu trả về để tập trung vào ánh xạ. Mã đầy đủ ở mục 6.

`@Selector` biến tham số thành một phần của đường dẫn. Các tham số đầu vào khác có thể được lấy từ query hoặc từ thuộc tính ở cấp gốc của JSON body theo cơ chế operation. Ví dụ POST có body:

```json
{"name":"blue","enabled":true}
```

có thể cung cấp hai đối số `String name` và `boolean enabled`. Không cần và không nên mặc định sao chép `@RequestBody` từ controller vào phương thức operation này.

Để ánh xạ dựa trên tên tham số Java, cần biên dịch với `-parameters`. Với đầu vào trung lập giữa HTTP/JMX, phải tuân thủ các kiểu tham số operation được hỗ trợ; một DTO đầu vào phức tạp không được xử lý giống hệt cơ chế nhận body của Spring MVC controller.

Trong khi đó, **đối tượng trả về có thể là một cấu trúc dữ liệu để được chuyển thành JSON**. Đừng nhầm giới hạn kiểu đầu vào với việc không được trả record hoặc đối tượng kết quả.

Thay đổi base path, cổng quản lý hoặc context path có thể làm URL thực tế khác ví dụ. Việc đổi URL không làm thay đổi quy tắc GET/POST/DELETE của operation.

## 4. Quy tắc mã phản hồi mặc định

Khi operation hoàn tất bình thường và không chủ động chỉ định một phản hồi web riêng, Actuator xét loại thao tác và việc nó có trả về giá trị hay không:

| Operation | Có giá trị trả về | Không có giá trị trả về |
| --- | --- | --- |
| Read | 200 OK | 404 Not Found |
| Write | 200 OK | 204 No Content |
| Delete | 200 OK | 204 No Content |

Quy tắc này được nêu tại [Spring Boot 3.3: Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

### 4.1. “Không có giá trị” khác với “giá trị rỗng”

Các trường hợp sau cần tách rõ:

| Giá trị Java | Có giá trị để trả không? | Ý nghĩa đối với quy tắc mặc định |
| --- | --- | --- |
| `null` | Không | Read → 404; Write/Delete → 204 |
| Phương thức `void` | Không | Không tạo một đối tượng kết quả |
| `false` | Có | Không tự trở thành 404 hay 204 |
| `0` | Có | Không tự trở thành 404 hay 204 |
| Map rỗng hoặc danh sách rỗng | Có | Có thể trả 200 với body rỗng về mặt tập hợp |
| Record chứa `enabled=false` | Có | Vẫn có đối tượng kết quả để trả |

Với GET trả một map rỗng, body có thể là `{}` và mã vẫn là 200. Với GET trả `null`, hành vi mặc định là 404; đó không phải 200 với chuỗi JSON `null`.

Tương tự, một phương thức đọc khai báo `void` không phải cách thông thường để tạo GET trả 204. Nếu cần hợp đồng mã phản hồi riêng, phải thể hiện điều đó bằng cơ chế phản hồi web phù hợp.

### 4.2. HTTP status không tự hiểu nội dung đối tượng

Nếu một write operation trả về một đối tượng như:

```json
{"success":false,"reason":"not-ready"}
```

thì “có đối tượng kết quả” vẫn là điều kiện của mã mặc định 200. Actuator không tự nhìn trường `success` để chọn 409 hoặc 503.

Các trường hợp khác cũng không được tự suy ra:

- POST tạo dữ liệu không tự trở thành 201 Created.
- Phương thức khởi tạo công việc nền không tự trở thành 202 Accepted.
- DELETE không tìm thấy dữ liệu không tự trở thành 404 nếu phương thức chỉ trả `null`; mặc định của Delete lúc này là 204.
- 204 cho biết phản hồi không có body; nó không tự chứng minh dữ liệu đã được lưu bền vững hoặc một công việc nền đã hoàn tất.

Hợp đồng của thao tác phải được thiết kế rõ trước; mã phản hồi là cách biểu đạt hợp đồng đó, không thay cho việc triển khai.

## 5. Lỗi có thể xảy ra trước khi operation được gọi

Một operation đúng annotation chưa chắc được thực thi. Yêu cầu còn phải khớp mapping và cung cấp đầu vào hợp lệ.

| Mã | Tình huống điển hình trong ví dụ không có lớp bảo mật |
| --- | --- |
| 400 Bad Request | Thiếu tham số bắt buộc hoặc không chuyển được sang kiểu Java cần thiết |
| 404 Not Found | Không có đường dẫn khả dụng; hoặc Read trả `null` sau khi đã được gọi |
| 405 Method Not Allowed | Đường dẫn có mapping nhưng không có operation cho HTTP method đang dùng |
| 406 Not Acceptable | Yêu cầu định dạng phản hồi không phù hợp với khả năng `produces` |
| 415 Unsupported Media Type | Content-Type của body không phù hợp với operation nhận body |

Cùng một mã 404 có thể xuất hiện ở **hai giai đoạn khác nhau**:

```text
Không có endpoint được expose / không khớp đường dẫn
    -> không gọi operation -> 404

Khớp GET, gọi read operation, kết quả là null
    -> đã gọi operation -> 404 mặc định của Read
```

Ngược lại, khi thiếu một tham số bắt buộc hoặc chuyển kiểu thất bại, operation không được gọi và phản hồi là 400. Không đặt hiệu ứng phụ vào bước mà bạn mong “sẽ chạy trước khi kiểm tra tham số”.

Với ứng dụng có Spring Security, 401 hoặc 403 có thể xuất hiện trước lớp operation; CSRF cũng có thể làm yêu cầu POST/DELETE bị từ chối. Thêm `@WriteOperation` không tự bỏ qua các quy tắc đó.

Ngoại lệ phát sinh trong logic operation là một vấn đề khác với lỗi chuyển tham số. Không mặc định mọi `IllegalArgumentException` do mã ứng dụng ném ra đều trở thành 400, hoặc mọi `null` đều biểu diễn lỗi nội bộ.

Để theo dõi cách kết quả được thích ứng trong Spring MVC, có thể xem [mã ánh xạ endpoint của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java).

## 6. Ví dụ đầy đủ: đọc, ghi và xóa cờ mô phỏng

Ví dụ dùng một map trong bộ nhớ để quan sát hợp đồng HTTP. Nó không tác động tới cấu hình vận hành thật, không lưu dữ liệu qua lần khởi động lại và không đồng bộ giữa nhiều bản ứng dụng.

### 6.1. Cấu trúc và build

Tạo một dự án Gradle độc lập:

```text
operation-mapping-demo/
├── build.gradle
└── src/main/
    ├── java/example/operationmapping/OperationMappingApplication.java
    └── resources/application.properties
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.compilerArgs.add('-parameters')
}
```

Dùng Gradle 8.5 và JDK 21 cho ví dụ. Nếu sử dụng wrapper, gọi lệnh wrapper tương ứng của dự án. Đây là dự án mẫu riêng, không phải yêu cầu thay thế cấu hình build của một module hiện có.

### 6.2. Mã Java

Tệp `src/main/java/example/operationmapping/OperationMappingApplication.java`:

```java
package example.operationmapping;

import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OperationMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(OperationMappingApplication.class, args);
    }

    @Bean
    FlagsEndpoint flagsEndpoint() {
        return new FlagsEndpoint();
    }

    @Bean
    @ConditionalOnProperty(
            name = "demo.strict-delete", havingValue = "true")
    FlagsWebExtension flagsWebExtension(FlagsEndpoint endpoint) {
        return new FlagsWebExtension(endpoint);
    }

    public record FlagView(String name, boolean enabled) {
    }

    @Endpoint(id = "flags")
    public static class FlagsEndpoint {
        private final Map<String, Boolean> flags = new ConcurrentHashMap<>();

        public FlagsEndpoint() {
            flags.put("demo", false);
        }

        @ReadOperation
        public Map<String, Boolean> snapshot() {
            return new TreeMap<>(flags);
        }

        @ReadOperation
        public FlagView find(@Selector String name) {
            Boolean value = flags.get(name);
            return value == null ? null : new FlagView(name, value);
        }

        @WriteOperation
        public FlagView put(String name, boolean enabled) {
            flags.put(name, enabled);
            return new FlagView(name, enabled);
        }

        @WriteOperation
        public void update(@Selector String name, boolean enabled) {
            flags.put(name, enabled);
        }

        @DeleteOperation
        public FlagView delete(@Selector String name) {
            Boolean value = flags.remove(name);
            return value == null ? null : new FlagView(name, value);
        }
    }

    @EndpointWebExtension(endpoint = FlagsEndpoint.class)
    public static class FlagsWebExtension {
        private final FlagsEndpoint endpoint;

        public FlagsWebExtension(FlagsEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @DeleteOperation
        public WebEndpointResponse<FlagView> delete(@Selector String name) {
            FlagView removed = endpoint.delete(name);
            return removed == null
                    ? new WebEndpointResponse<>(404)
                    : new WebEndpointResponse<>(removed, 200);
        }
    }
}
```

Ở chế độ mặc định, bean `FlagsWebExtension` chưa được tạo vì chưa bật `demo.strict-delete=true`. Vì vậy, ta quan sát được mã mặc định của các operation trước khi bật phần tùy chỉnh ở mục 8.

Một số chi tiết của mẫu:

- Map ban đầu chứa `demo=false`.
- `snapshot()` luôn trả về một map, kể cả khi map không còn phần tử.
- `find()` trả `null` khi không có tên được yêu cầu.
- `put()` ghi giá trị và trả `FlagView`, nên mặc định POST trả 200.
- `update()` ghi giá trị nhưng khai báo `void`, nên mặc định POST trả 204.
- Cả hai thao tác ghi trong mẫu đều có thể thêm hoặc thay thế một tên. Chúng không tự kiểm tra “phải tồn tại trước”.
- `delete()` trả đối tượng đã xóa nếu tìm thấy; lần xóa tiếp theo trả `null`.

Tên phương thức `put()` được chọn để mô tả việc đặt giá trị trong map. Nó vẫn là POST vì được gắn `@WriteOperation`.

### 6.3. Cấu hình công bố

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,flags
demo.strict-delete=false
```

Mẫu chỉ lắng nghe trên loopback và không có phụ thuộc Spring Security để tách riêng việc học mapping khỏi cấu hình xác thực. Trong hệ thống thực, thao tác thay đổi trạng thái quản lý cần được bảo vệ phù hợp.

Chạy từ thư mục dự án:

```shell
gradle bootRun
```

Nếu đã có Gradle Wrapper trên Windows:

```powershell
.\gradlew.bat bootRun
```

## 7. Thực hành quan sát mã và body

Các bước dưới bắt đầu từ một ứng dụng vừa khởi động, chưa thay đổi dữ liệu. JSON được trình bày là phần thân phản hồi; các header có thời gian hoặc thông tin máy chủ không được giả định là cố định.

### 7.1. GET có kết quả và GET không có kết quả

Gọi trong PowerShell:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/flags
```

Body:

```json
{"demo":false}
```

GET `/actuator/flags/demo` trả 200 với:

```json
{"name":"demo","enabled":false}
```

Giá trị `false` không có nghĩa là “không có kết quả”. `find()` đã trả một `FlagView` hợp lệ.

Kiểm tra tên không tồn tại:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:8080/actuator/flags/missing
```

Kết quả mã trạng thái:

```text
404
```

Trong trường hợp này, mapping đã khớp và `find()` trả `null`. Phản hồi không có một body JSON `null`.

### 7.2. POST có kết quả trả về

Dùng PowerShell để gửi body JSON, tránh nhầm cách shell chuyển dấu nháy cho chương trình ngoài:

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/flags' -ContentType 'application/json' -Body '{"name":"blue","enabled":true}'
$r.StatusCode
$r.Content
```

Kết quả:

```text
200
{"name":"blue","enabled":true}
```

Dù `blue` là tên mới được thêm vào map, mã vẫn là 200 theo quy tắc mặc định của Write có giá trị trả về. Việc “tạo mới” trong mã không tự đổi nó thành 201.

### 7.3. POST không có kết quả trả về

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/flags/demo' -ContentType 'application/json' -Body '{"enabled":true}'
$r.StatusCode
$r.Content.Length
```

Kết quả:

```text
204
0
```

`name` đến từ path selector, còn `enabled` đến từ JSON body. Phương thức `update()` đã thay đổi map nhưng không trả một đối tượng kết quả.

Sau đó GET `/actuator/flags/demo` trả 200 với:

```json
{"name":"demo","enabled":true}
```

Không cố giải mã body 204 thành JSON. Nếu bên gọi cần biết kết quả mới trong chính phản hồi ghi, hãy thiết kế operation trả về dữ liệu phù hợp thay vì suy đoán một body không có.

### 7.4. DELETE có dữ liệu và DELETE lặp lại

Sau bước cập nhật trên, lần DELETE đầu:

```powershell
$r = Invoke-WebRequest -Method Delete -Uri 'http://127.0.0.1:8080/actuator/flags/demo'
$r.StatusCode
$r.Content
```

Kết quả:

```text
200
{"name":"demo","enabled":true}
```

Lần DELETE thứ hai:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" -X DELETE http://127.0.0.1:8080/actuator/flags/demo
```

Kết quả:

```text
204
```

Lần đầu `delete()` trả đối tượng đã xóa; lần sau nó trả `null`. Mã mặc định của Delete không có giá trị là 204, dù tên không còn trong map. Đây là hợp đồng của mẫu, không phải kết luận rằng mọi API DELETE trong mọi hệ thống đều phải trả 204 khi dữ liệu không tồn tại.

Nếu xóa nốt `blue`, GET `/actuator/flags` trả 200 với body:

```json
{}
```

Map rỗng vẫn là một giá trị trả về, khác với `null`.

### 7.5. Ma trận các lỗi yêu cầu

Với ứng dụng mẫu, không bật extension web và không thêm lớp bảo mật:

| Yêu cầu | Kết quả dự kiến | Lý do |
| --- | --- | --- |
| POST /actuator/flags/demo, JSON `{}` | 400 | Thiếu `enabled` bắt buộc |
| POST /actuator/flags/demo, JSON `{"enabled":"not-a-boolean"}` | 400 | Không chuyển được thành boolean |
| PUT /actuator/flags/demo | 405 | Write operation được ánh xạ thành POST |
| POST /actuator/flags/demo với Content-Type text/plain | 415 | Không phù hợp operation nhận JSON body |
| GET /actuator/flags/demo với Accept text/plain | 406 | Không phù hợp kiểu phản hồi của operation |

Các lỗi 405/406/415 trong bảng được xác định ở lớp xử lý yêu cầu trước khi gọi phương thức tương ứng; chúng không phụ thuộc việc `demo` còn trong map hay đã bị xóa.

Nếu thử bằng `Invoke-WebRequest`, cần nhớ PowerShell có thể ném lỗi khi nhận phản hồi 4xx. Điều đó không có nghĩa operation Java đã ném ngoại lệ tương ứng. Có thể dùng công cụ HTTP hiển thị mã/phần thân hoặc kiểm tra trực tiếp phản hồi trong một bài test.

## 8. Chủ động chỉ định mã phản hồi bằng WebEndpointResponse

Giả sử yêu cầu của endpoint là: “DELETE một tên không tồn tại phải trả 404”. Chỉ trả `null` từ Delete không đạt yêu cầu đó, vì quy tắc mặc định là 204.

`WebEndpointResponse<T>` biểu diễn body và mã HTTP riêng. Theo [hợp đồng WebEndpointResponse của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html), đây là kiểu phản hồi dùng cho thông tin đặc thù web, điển hình trong `@EndpointWebExtension`.

Mẫu đã có phần mở rộng:

```java
@DeleteOperation
public WebEndpointResponse<FlagView> delete(@Selector String name) {
    FlagView removed = endpoint.delete(name);
    return removed == null
            ? new WebEndpointResponse<>(404)
            : new WebEndpointResponse<>(removed, 200);
}
```

Đây là phần trích của `FlagsWebExtension` trong mã đầy đủ, không phải một phương thức độc lập để chèn thêm vào `FlagsEndpoint`.

`@EndpointWebExtension(endpoint = FlagsEndpoint.class)` liên kết extension với endpoint gốc. Extension bổ sung hoặc thay thế operation tương ứng ở lớp web; nó không đổi endpoint ID thành tên của lớp extension. Tham khảo [EndpointWebExtension](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

Để quan sát, đổi cấu hình rồi khởi động lại:

```properties
demo.strict-delete=true
```

Ứng dụng được khởi tạo lại nên map ban đầu trở về `demo=false`. Kết quả:

| Thao tác theo thứ tự | Khi bật strict-delete |
| --- | --- |
| DELETE /actuator/flags/missing | 404, không có body |
| DELETE /actuator/flags/demo lần đầu | 200, body là FlagView đã xóa |
| DELETE /actuator/flags/demo lần tiếp theo | 404, không có body |

Điểm quyết định không phải “object `WebEndpointResponse` khác null nên phải 200”. Adapter web nhận biết kiểu phản hồi này và dùng mã đã chỉ định. Đây là hợp đồng tường minh, khác với suy luận mặc định từ giá trị của operation.

Lựa chọn extension cũng giữ sự phân chia trách nhiệm: endpoint gốc diễn tả thao tác và kết quả, extension xử lý cách biểu đạt đặc thù HTTP. Nếu endpoint được công bố qua JMX, cơ chế gọi và kết quả của JMX không có các mã HTTP 200/404 này.

Không mặc định áp dụng mọi kiểu trả về quen thuộc từ controller cho Actuator. Khi cần điều khiển mã HTTP của operation, hãy dùng cơ chế được Actuator hỗ trợ và kiểm chứng trên stack web đang sử dụng.

## 9. Cách đọc một lỗi phản hồi theo từng giai đoạn

Một trình tự chẩn đoán hữu ích:

1. **Khả dụng:** endpoint đã là bean, được bật và được công bố đúng giao thức chưa? Có dùng đúng cổng/base path không?
2. **Bảo mật:** yêu cầu có bị chặn bởi xác thực, quyền hoặc CSRF trước khi tới operation không?
3. **Mapping:** path và HTTP method có khớp không?
4. **Kiểu nội dung:** Content-Type của body và Accept của phản hồi có phù hợp không?
5. **Đầu vào:** tham số bắt buộc có đủ và chuyển kiểu được không?
6. **Thực thi:** operation có chạy, thay đổi trạng thái và trả kết quả gì?
7. **Thích ứng phản hồi:** đang dùng mã mặc định hay `WebEndpointResponse`?

Ví dụ, để giải thích một 404, hãy xác định nó xuất hiện vì không tìm thấy mapping, vì Read trả `null`, hay vì extension chủ động trả 404. Chỉ nhìn URL có từ `flags` không đủ kết luận.

Tương tự, một 405 không được sửa bằng cách đổi tên phương thức Java; cần gọi đúng HTTP method hoặc thiết kế lại loại API. Một 400 do thiếu `enabled` không được sửa bằng cách thay return type sang `void`; cần sửa đầu vào.

Hành vi của adapter là phần nối giữa operation và HTTP. Nó không thay thế quy tắc nghiệp vụ, giao dịch, xử lý đồng thời hoặc quyền thực hiện thao tác trong ứng dụng.

## 10. Bài tập củng cố

1. Đổi `update()` từ `void` sang trả `FlagView`. Giữ nguyên `@WriteOperation`. Dự đoán HTTP method, mã trạng thái và body sau thay đổi.
2. Cho `find()` trả một đối tượng biểu thị “không có dữ liệu” thay vì `null`. Giải thích vì sao HTTP status mặc định có thể đổi dù đường dẫn không đổi.
3. Đổi `snapshot()` để trả map rỗng trong mọi trường hợp. So sánh với việc trả `null`.
4. Giữ `put()` nhưng gửi PUT từ bên gọi. Chỉ ra thành phần nào cần thay đổi để yêu cầu tương thích với operation hiện tại.
5. Bật và tắt `demo.strict-delete`, rồi xóa cùng một tên hai lần. Giải thích sự khác biệt giữa mã mặc định và mã do extension chỉ định.
6. Viết kiểm tra cho thiếu tham số, sai kiểu boolean, sai HTTP method, sai Content-Type và Accept không được hỗ trợ. Kiểm tra cả mã phản hồi lẫn trạng thái của map sau yêu cầu.

Khi giải thích một kết quả, hãy nêu đủ annotation, đường dẫn, đầu vào, giá trị Java trả về và lớp tạo mã HTTP. Cách đối chiếu đó giúp phân biệt lỗi mapping với kết quả của thao tác và với chính sách phản hồi riêng.
