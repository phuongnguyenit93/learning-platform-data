# Phân loại thao tác đọc, ghi và xóa trên endpoint

Một endpoint Actuator có thể cho biết trạng thái hiện tại, thay đổi một thiết lập hoặc loại bỏ dữ liệu quản trị. Đây là các thao tác khác nhau dù cùng thuộc một khả năng quản trị và có thể dùng chung phần đường dẫn.

Trong mô hình endpoint của Spring Boot, ba annotation thường dùng là `@ReadOperation`, `@WriteOperation` và `@DeleteOperation`. Bài học giúp bạn chọn đúng loại thao tác, hiểu ánh xạ qua HTTP và kiểm chứng hành vi bằng một endpoint nhỏ chỉ lưu dữ liệu trong bộ nhớ.

Các ví dụ dùng Spring Boot 3.3, với thí nghiệm cố định ở 3.3.5. Việc ghi/xóa trong thí nghiệm chỉ tác động tới dữ liệu giả lập của tiến trình học tập.

## 1. Endpoint là một khả năng, operation là một thao tác

**Endpoint** là một điểm quản trị có định danh, ví dụ `health`, `loggers` hoặc endpoint tự viết. **Operation** là một thao tác mà endpoint cung cấp.

Một endpoint không bắt buộc có đủ cả ba loại. Chỉ cần khai báo các thao tác có ý nghĩa đối với khả năng đó. Một endpoint cũng có thể có nhiều thao tác đọc với đường dẫn khác nhau.

`@Endpoint` định nghĩa mô hình có thể được thích nghi cho các công nghệ công khai như HTTP hoặc JMX. Vì vậy, ba loại thao tác được khai báo ở cấp mô hình trước khi được ánh xạ sang một giao thức cụ thể. Xem [Endpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

### 1.1. Câu hỏi để chọn loại thao tác

| Loại | Câu hỏi chính | Ví dụ ý định |
| --- | --- | --- |
| Đọc — `@ReadOperation` | Cần lấy thông tin gì mà không chủ ý thay đổi trạng thái được quản trị? | Xem thiết lập hiện tại |
| Ghi — `@WriteOperation` | Cần áp dụng thay đổi hoặc thực hiện lệnh quản trị gì? | Đặt một giá trị cấu hình |
| Xóa — `@DeleteOperation` | Cần loại bỏ hoặc làm mất hiệu lực dữ liệu nào trong phạm vi quản trị? | Xóa giá trị giả lập hoặc làm sạch bộ nhớ đệm |

“Ghi” không chỉ có nghĩa tạo mới một hàng cơ sở dữ liệu. Một lệnh quản trị làm thay đổi trạng thái cũng có thể thuộc loại này.

“Xóa” không có nghĩa xóa class Java, xóa bean endpoint hoặc gỡ toàn bộ khả năng quản trị. Phần thân phương thức quyết định đối tượng nào bị loại bỏ.

### 1.2. Một đường dẫn có thể phục vụ nhiều thao tác

Với endpoint giả lập `labstate` và một khóa `theme`:

```text
GET    /actuator/labstate/theme  → đọc giá trị
POST   /actuator/labstate/theme  → đặt giá trị
DELETE /actuator/labstate/theme  → xóa giá trị
```

Cùng URL không đồng nghĩa cùng yêu cầu: phương thức HTTP là một phần quan trọng để chọn thao tác.

## 2. Ánh xạ mặc định qua HTTP

Với endpoint web dựa trên các annotation operation:

| Annotation | Phương thức HTTP |
| --- | --- |
| `@ReadOperation` | `GET` |
| `@WriteOperation` | `POST` |
| `@DeleteOperation` | `DELETE` |

Đây là ánh xạ được Spring Boot mô tả trong [Web Endpoint Request Predicates](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates).

Đặc biệt, `@WriteOperation` không tự ánh xạ sang `PUT` hoặc `PATCH` chỉ vì phương thức Java có tên `update`. Tên phương thức thể hiện ý nghĩa trong mã; annotation và các tham số chọn thao tác, đường và đầu vào.

### 2.1. Không thay bằng annotation của controller thông thường

Mô hình `@Endpoint` dùng các annotation operation của Actuator. Nếu đang viết một controller HTTP với `@RestController`, đó là cơ chế ánh xạ khác.

Không gắn thêm `@PostMapping` vào một operation rồi mặc định rằng nó sẽ đổi ánh xạ Actuator. Khi cần thiết kế một API HTTP nghiệp vụ đầy đủ, hãy chọn mô hình controller phù hợp thay vì ép mọi API vào điểm quản trị.

### 2.2. Khi dùng JMX

Qua JMX, các thao tác được thể hiện theo cơ chế của MBean, không phải gửi `GET` hay `POST`. Việc công khai HTTP và JMX cũng được cấu hình riêng.

Xem [Spring Boot 3.3 — Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html). Bảng phương thức ở trên chỉ mô tả cách thích nghi qua HTTP, không biến operation thành một khái niệm chỉ dành cho URL.

## 3. Chọn loại theo tác động, không chỉ theo tên

### 3.1. Đọc: trả thông tin về trạng thái

Một thao tác đọc nên được thiết kế để truy xuất thông tin, không để người gọi vô tình kích hoạt một thay đổi quản trị quan trọng.

Ví dụ, phương thức tên `status` nhưng xóa các bản ghi sau khi trả kết quả vẫn có tác động thay đổi. Đổi tên thành “đọc trạng thái” không làm nó trở thành thao tác đọc phù hợp.

Đọc cũng có thể tốn CPU, I/O hoặc làm phát sinh nhật ký kỹ thuật. Điều cần phân biệt là ý định thay đổi trạng thái được người gọi yêu cầu. Ý nghĩa phương thức an toàn và tính lặp lại của HTTP được giải thích trong [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).

### 3.2. Ghi: đặt giá trị hoặc thực hiện lệnh

Một operation ghi có thể đặt thiết lập, áp dụng cấu hình hoặc yêu cầu một hành động quản trị.

Ví dụ có sẵn: endpoint `loggers` dùng `POST` để đặt mức ghi nhật ký. Thậm chí việc xóa mức cấu hình riêng của logger được API này thực hiện bằng một yêu cầu `POST` với dữ liệu phù hợp. Xem [Actuator Loggers REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

Điều đó cho thấy không thể nhìn thấy từ “xóa” trong mô tả rồi tự đổi mọi API thành `DELETE`. Phải dùng hợp đồng của endpoint đã được thiết kế.

Endpoint `shutdown` cũng nhận một lệnh quản trị qua `POST`, không phải cập nhật bản ghi thông thường. Xem [Actuator Shutdown REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html). Bài thực hành không bật hoặc gọi endpoint này.

### 3.3. Xóa: loại bỏ dữ liệu trong phạm vi đã định

Với endpoint giả lập, xóa có thể bỏ một giá trị khỏi bản đồ trong bộ nhớ. Với bộ nhớ đệm, mục tiêu có thể là làm sạch dữ liệu đã lưu tạm.

Ví dụ `CachesEndpoint` có thao tác đọc thông tin cache và các thao tác `@DeleteOperation` để làm sạch cache. Xem [CachesEndpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html).

Cần nêu rõ phạm vi: xóa một khóa, một cache hay toàn bộ dữ liệu thuộc endpoint. Không dùng cùng một mô tả mơ hồ cho các hành động có phạm vi khác nhau.

## 4. Đường dẫn và đầu vào của operation

Mặc định, đường HTTP được hình thành từ base path, định danh endpoint và các tham số chọn đường.

Trong thí nghiệm:

```text
base path: /actuator
endpoint id: labstate
selector name: theme
→ /actuator/labstate/theme
```

### 4.1. @Selector chọn đối tượng trên đường dẫn

Tham số `@Selector String name` lấy phần đường tương ứng. Với URL trên, `name` nhận `theme`.

`@Selector` không tự truy vấn cơ sở dữ liệu và không tự kiểm tra khóa có tồn tại. Phương thức của bạn quyết định cách dùng giá trị đó.

Nếu chỉ có các operation với selector, không suy ra đường gốc `/actuator/labstate` cũng có thao tác đọc. Muốn có thao tác tại đường gốc, phải có operation phù hợp.

### 4.2. Tham số ghi và JSON

Với phương thức:

```text
@WriteOperation
public Map<String, String> write(@Selector String name, String value)
```

Đây là đoạn trích chữ ký, không phải một chương trình độc lập. `name` lấy từ đường, còn yêu cầu sau cung cấp giá trị `value` qua JSON:

```json
{
  "value": "dark"
}
```

Các tham số operation mặc định là bắt buộc. Java cần giữ tên tham số bằng tùy chọn biên dịch `-parameters` để cơ chế ánh xạ có thông tin cần thiết. Đầu vào của mô hình endpoint trung lập công nghệ sử dụng các kiểu đơn giản phù hợp; không mặc định đưa một DTO tùy ý vào tham số như cách viết controller HTTP. Xem [Receiving Input](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input).

Nếu muốn tham số tùy chọn hoặc chuyển đổi kiểu riêng, cần thiết kế hợp đồng tương ứng. Bài này giữ `value` là chuỗi bắt buộc để tập trung quan sát ba loại thao tác.

### 4.3. Annotation không viết hộ logic nghiệp vụ

`@WriteOperation` không tự lưu dữ liệu. `@DeleteOperation` không tự xóa một mục trong bản đồ. Annotation giúp hạ tầng nhận diện thao tác; phần thân Java vẫn chịu trách nhiệm cho thay đổi, kiểm tra giá trị và phạm vi tác động.

Khi công khai một thao tác cho công cụ vận hành, cần giải thích rõ đối tượng, đầu vào và kết quả mong đợi để tránh người gọi suy đoán.

## 5. Mã phản hồi mặc định của operation web

Với operation thông thường và không có tùy chỉnh phản hồi riêng:

| Loại thao tác | Có giá trị trả về | Không có giá trị trả về |
| --- | --- | --- |
| Read | 200 | 404 |
| Write | 200 | 204 |
| Delete | 200 | 204 |

Vì vậy, một phương thức delete trả kết quả có thể tạo phản hồi 200; không mặc định mọi `DELETE` đều phải là 204.

Các mã này nói về quy tắc phản hồi của operation. Endpoint chuyên biệt hoặc phần mở rộng web có thể có hợp đồng khác. Ví dụ `WebEndpointResponse` hỗ trợ phần mở rộng cung cấp thông tin HTTP cụ thể. Xem [WebEndpointResponse — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html).

Nếu thiếu tham số bắt buộc hoặc không chuyển đổi được đầu vào, hạ tầng có thể trả 400 trước khi gọi thân operation. Ta sẽ kiểm chứng trường hợp thiếu `value` ở ví dụ bên dưới.

Không dùng mã HTTP một cách tách rời: 404 có thể đến từ đường không được ánh xạ hoặc từ một thao tác đọc không trả dữ liệu. Cần đối chiếu URL, phương thức và phần thân phương thức Java.

## 6. Thí nghiệm hoàn chỉnh với trạng thái trong bộ nhớ

Ta tạo endpoint `labstate` chứa một bản đồ khóa–giá trị. Nó có ba operation cùng dùng tham số chọn đường `name`.

Thí nghiệm không dùng cơ sở dữ liệu, không thay đổi cấu hình thật và không làm sạch cache của ứng dụng khác. Mục tiêu là thấy rõ yêu cầu nào gọi thao tác nào và trạng thái thay đổi ra sao.

### 6.1. Chuẩn bị dự án

Dùng JDK 17 trở lên cùng Gradle tương thích. Tạo một thư mục mới, với `settings.gradle`:

```groovy
rootProject.name = 'actuator-operation-demo'
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

BOM cố định phiên bản để dễ tái lập. Trong dự án dùng Spring Boot Gradle Plugin, việc giữ tên tham số có tích hợp sẵn; dự án Java nhỏ ở đây khai báo rõ tùy chọn.

### 6.2. Lớp khởi động

Tạo `src/main/java/lab/operations/OperationDemo.java`:

```java
package lab.operations;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OperationDemo {
    public static void main(String[] args) {
        SpringApplication.run(OperationDemo.class, args);
    }
}
```

### 6.3. Endpoint có ba operation

Tạo `src/main/java/lab/operations/LabStateEndpoint.java`:

```java
package lab.operations;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "labstate")
public class LabStateEndpoint {
    private final Map<String, String> values = new ConcurrentHashMap<>();

    @ReadOperation
    public Map<String, String> read(@Selector String name) {
        String value = values.get(name);
        return value == null ? null : Map.of("name", name, "value", value);
    }

    @WriteOperation
    public Map<String, String> write(@Selector String name, String value) {
        values.put(name, value);
        return Map.of("name", name, "value", value);
    }

    @DeleteOperation
    public void delete(@Selector String name) {
        values.remove(name);
    }
}
```

Các điểm cần nối với khái niệm:

- `@Component` giúp lớp được đăng ký làm bean qua cơ chế quét của ứng dụng.
- `@Endpoint(id = "labstate")` xác định khả năng quản trị.
- `@Selector` đưa khóa cần thao tác vào đường dẫn.
- Thao tác đọc lấy giá trị, không gọi `put` hay `remove`.
- Thao tác ghi đặt giá trị và trả dữ liệu vừa đặt.
- Thao tác xóa bỏ giá trị, trả `void`.
- `ConcurrentHashMap` hỗ trợ các thao tác bản đồ riêng lẻ khi có nhiều luồng; nó không biến toàn bộ chuỗi đọc–ghi–xóa thành một giao dịch.

Dữ liệu chỉ thuộc tiến trình hiện tại. Khởi động lại sẽ làm mất bản đồ. Nếu chạy nhiều phiên bản ứng dụng, mỗi tiến trình có bản đồ riêng; ví dụ này không mô tả một kho cấu hình dùng chung.

### 6.4. Biên dịch và chạy

Tại gốc dự án thử, dùng PowerShell:

```powershell
gradle copyDemoLibraries
javac -parameters -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/operations/OperationDemo.java src/main/java/lab/operations/LabStateEndpoint.java
java -cp "out;lib/*" lab.operations.OperationDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,labstate"
```

Nếu có Gradle Wrapper, dùng wrapper phù hợp thay cho lệnh `gradle`. Trên Linux/macOS, classpath của lệnh chạy dùng dấu `:`:

```bash
java -cp "out:lib/*" lab.operations.OperationDemo --server.address=127.0.0.1 --server.port=8080 --management.endpoints.web.exposure.include=health,labstate
```

Ứng dụng thử chỉ lắng nghe trên máy cục bộ. Nếu cổng 8080 đã được dùng, chọn cổng trống và sửa đồng bộ các lệnh gọi.

Dự án không thêm Spring Security. Khi thử trong ứng dụng đã có bảo mật, cần quyền và cơ chế bảo vệ tương ứng. Chỉ công khai endpoint bằng danh sách `include` không tự cấp quyền truy cập cho mọi người.

Ứng dụng giữ tiến trình để phục vụ HTTP; console có log thay đổi theo lần chạy, không phải một stdout cố định. Mở terminal thứ hai để thực hiện các bước tiếp theo.

## 7. Theo dõi một khóa qua đọc, ghi và xóa

Dùng khóa `theme`. Mọi giá trị trong phần này là dữ liệu thử nghiệm.

### 7.1. Đọc trước khi có dữ liệu

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Kết quả trong thí nghiệm: **404**.

Ở đây URL có thao tác đọc, nhưng `values.get("theme")` chưa có giá trị. Phương thức trả `null`, nên phản hồi đọc là 404. Không được dùng riêng mã này để kết luận endpoint chưa được đăng ký.

### 7.2. Ghi giá trị dark

Đưa JSON vào stdin của `curl.exe` để giữ nguyên dấu ngoặc kép trên PowerShell:

```powershell
'{"value":"dark"}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Kết quả: **200**, với dữ liệu thể hiện:

```json
{
  "name": "theme",
  "value": "dark"
}
```

Thứ tự các trường và khoảng trắng trong JSON không phải hợp đồng của bản đồ Java. Hãy so giá trị trường, không so toàn bộ phản hồi theo chuỗi định dạng.

Cùng `name` đến từ URL, còn `value` đến từ JSON. Thân `write` thực hiện `put`; annotation không tự thực hiện việc lưu.

### 7.3. Đọc lại

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Kết quả: **200**, `value` bằng `dark`. Đây là bằng chứng rằng thao tác ghi đã thay đổi trạng thái mà thao tác đọc sử dụng.

### 7.4. Ghi lại cùng khóa bằng giá trị light

```powershell
'{"value":"light"}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Kết quả: **200**, `value` bằng `light`. Gọi GET tiếp theo cũng thấy `light`.

Ví dụ dùng `Map.put`, nên ghi cùng khóa sẽ thay giá trị cũ. Không suy ra mọi `@WriteOperation` đều có cơ chế thay thế này: một operation khác có thể thực hiện lệnh hoàn toàn khác.

### 7.5. Xóa khóa

```powershell
curl.exe -i -X DELETE "http://127.0.0.1:8080/actuator/labstate/theme"
```

Kết quả: **204**, không có body. Phương thức `delete` đã gọi `remove` rồi trả `void`.

Gọi GET lại:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Kết quả: **404**, vì dữ liệu không còn. Endpoint và phương thức đọc vẫn tồn tại.

### 7.6. Lặp lại DELETE

```powershell
curl.exe -i -X DELETE "http://127.0.0.1:8080/actuator/labstate/theme"
```

Trong triển khai này, vẫn nhận **204**. `remove` không có gì để bỏ, nhưng phương thức không tạo kết quả lỗi hoặc trả thông tin khác.

Điều này giúp phân biệt trạng thái sau thao tác với việc mục dữ liệu đã tồn tại trước đó. Không được nói phản hồi 204 tự chứng minh khóa đã có và vừa bị xóa.

Tiếp tục kiểm tra các yêu cầu lỗi ở phần 8 trước khi dừng ứng dụng.

## 8. Các yêu cầu không khớp hoặc thiếu dữ liệu

### 8.1. Dùng nhầm PUT

Khi ứng dụng còn chạy, thử yêu cầu cùng đường nhưng dùng PUT:

```powershell
'{"value":"dark"}' | curl.exe -i -X PUT "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Trong thí nghiệm Servlet không có bảo mật bổ sung, kết quả là **405 Method Not Allowed**. `@WriteOperation` đã tạo thao tác POST, không tạo thao tác PUT.

Đổi tên phương thức Java từ `write` thành `update` không tự làm phương thức HTTP thay đổi.

### 8.2. Thiếu value bắt buộc

Để có trạng thái kiểm tra rõ ràng, đặt lại `theme=light` bằng lệnh POST ở mục 7.4, rồi gửi:

```powershell
'{}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Kết quả: **400 Bad Request**. Thao tác yêu cầu `value`, nhưng JSON không cung cấp giá trị đó.

Trong kiểm tra đã chạy, GET sau yêu cầu lỗi vẫn trả `light`. Đây là bằng chứng cho thấy nhánh ghi hợp lệ không được thực hiện với dữ liệu thiếu này.

Phân biệt lỗi ánh xạ đầu vào với kiểm tra nghiệp vụ trong phương thức. Nếu cần giới hạn độ dài hoặc tập giá trị được chấp nhận, bạn phải thiết kế thêm, không trông chờ annotation operation tự suy ra.

### 8.3. Gọi đường gốc chưa có operation

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate"
```

Kết quả trong thí nghiệm: **404**. Cả ba phương thức trong lớp đều có selector, nên thao tác đang được cung cấp ở đường có thêm `name`.

Đường gốc có định danh endpoint không đồng nghĩa luôn có một thao tác GET liệt kê mọi dữ liệu.

### 8.4. Tổng hợp kiểm tra đã thực hiện

Các kiểm tra sau được thực hiện tuần tự trên cùng một tiến trình, với bản đồ ban đầu trống:

| Bước | Yêu cầu | Mã phản hồi | Trạng thái/điều được kiểm tra |
| --- | --- | --- | --- |
| 1 | GET trước khi ghi | 404 | Chưa có khóa |
| 2 | POST `dark` | 200 | Giá trị trả về là `dark` |
| 3 | GET | 200 | Đọc được `dark` |
| 4 | POST `light` | 200 | Giá trị trả về là `light` |
| 5 | GET | 200 | Đọc được `light` |
| 6 | PUT cùng đường | 405 | Không có thao tác PUT |
| 7 | POST thiếu `value` | 400 | Đầu vào bắt buộc không đủ |
| 8 | GET sau yêu cầu lỗi | 200 | Giá trị vẫn là `light` |
| 9 | DELETE | 204 | Body rỗng |
| 10 | GET sau xóa | 404 | Giá trị không còn |
| 11 | DELETE lần nữa | 204 | Kết quả theo triển khai `void` hiện tại |
| 12 | GET đường gốc | 404 | Không có read operation tại đường đó |

Bảng nói về một lượt kiểm chứng của ứng dụng thử theo thứ tự trên, không phải lời hứa mọi endpoint Actuator sẽ trả cùng mã. Trong môi trường khác, hãy đọc phản hồi thật cùng điều kiện và chính sách của nó. Dừng đúng tiến trình thử bằng `Ctrl+C` khi hoàn tất.

## 9. Loại thao tác, quyền truy cập và CSRF

Phân loại thao tác giúp mô tả tác động. Nó không tự quyết định ai được gọi.

Một thao tác đọc có thể trả dữ liệu nhạy cảm; một thao tác ghi có thể thay đổi cách ứng dụng hoạt động. Cần chọn phạm vi công khai và quyền theo nội dung thực tế, thay vì mặc định GET luôn được truy cập công khai.

### 9.1. Công khai endpoint không đồng nghĩa chỉ cho đọc

Danh sách:

```text
management.endpoints.web.exposure.include=health,labstate
```

chọn endpoint được công khai qua web. Với lớp mẫu, `labstate` chứa cả read, write và delete operation. Danh sách này không có nghĩa chỉ cho GET.

Nếu nhu cầu chỉ là quan sát, hãy thiết kế endpoint chỉ có thao tác đọc cần thiết hoặc áp dụng chính sách truy cập phù hợp cho các thao tác thay đổi. Không suy ra quyền chỉ từ việc endpoint xuất hiện trong trang khám phá.

### 9.2. Vì sao GET được mà POST/DELETE trả 403?

Với Spring Security, phương thức thay đổi trạng thái có thể chịu bảo vệ CSRF bên cạnh xác thực và phân quyền. Thiếu thông tin bảo vệ cần thiết có thể làm yêu cầu bị chặn trước khi tới operation.

Đây là hướng cần kiểm tra khi GET hoạt động còn POST/DELETE không hoạt động. Nó chưa chứng minh `@WriteOperation` hoặc `@DeleteOperation` ánh xạ sai. Xem [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Thực hiện theo cơ chế bảo mật của ứng dụng. Không tắt toàn bộ lớp bảo vệ chỉ để khớp mã phản hồi của một thí nghiệm không có Spring Security.

### 9.3. Thông tin cần ghi khi điều tra lỗi truy cập

Ghi URL, phương thức HTTP, loại nội dung, mã phản hồi và trạng thái sau yêu cầu. Với ứng dụng có bảo mật, kiểm tra thêm danh tính/quyền và yêu cầu CSRF tương ứng mà không đưa thông tin bí mật vào tài liệu học tập.

Nhờ đó có thể tách được: sai phương thức, sai đầu vào, không tìm thấy dữ liệu và bị chặn bởi chính sách.

## 10. Những giới hạn cần hiểu khi thiết kế operation

### 10.1. Annotation mô tả hợp đồng, không ngăn bạn viết sai tác động

Java vẫn cho phép một phương thức có `@ReadOperation` gọi mã thay đổi trạng thái. Vì vậy cần đọc thân phương thức và kiểm tra hành vi, không chỉ tin tên annotation.

Trong ví dụ, phần thân read chỉ lấy giá trị. Nếu thêm `values.remove(name)` vào đó, bạn đã thay đổi ý nghĩa thao tác và cần thiết kế lại.

### 10.2. Ghi cùng giá trị không đại diện cho mọi lệnh POST

Đặt cùng giá trị vào bản đồ hai lần làm trạng thái cuối giống nhau. Tuy nhiên, một lệnh POST khác có thể tạo thêm công việc, gửi thêm yêu cầu hoặc thực hiện hành động nhiều lần.

Không tự động thử lại mọi lệnh quản trị chỉ vì lần trước hết thời gian chờ. Có thể lệnh đã chạy nhưng phản hồi chưa tới bên gọi. Hợp đồng cần nêu rõ tính lặp lại và cách xác nhận kết quả khi điều đó quan trọng.

### 10.3. Xóa lặp lại không bắt buộc có cùng mã phản hồi

Trong ví dụ, delete trả `void`, nên hai lần đều là 204. Một thiết kế khác có thể báo riêng trường hợp dữ liệu không tồn tại.

Khi đánh giá tác động lặp lại, xem trạng thái được quản trị sau thao tác, đồng thời đọc hợp đồng phản hồi. Không lấy mã phản hồi của endpoint tự viết này làm quy tắc cho mọi API.

### 10.4. Thay đổi trong bộ nhớ không phải thay đổi bền vững

Bản đồ không ghi ra tệp hay cơ sở dữ liệu. 200 của POST chỉ xác nhận phần thực thi trong tiến trình mẫu đã trả kết quả; nó không chứng minh dữ liệu đã được lưu bền vững hoặc nhân bản sang nơi khác.

Tương tự, thao tác xóa trong bản đồ không mô tả mọi yêu cầu khôi phục, kiểm toán hoặc giao dịch của hệ thống thật. Đây là phạm vi cố ý của thí nghiệm để học cách phân loại operation.

## 11. Tự kiểm tra cách phân loại

### Tình huống A: xem số công việc đang chờ

Mục tiêu chỉ là đọc số lượng hiện tại, không thay đổi hàng đợi.

**Phân loại:** read operation là lựa chọn tự nhiên. Cần bảo đảm phần thân thực sự chỉ quan sát theo hợp đồng và kiểm soát quyền nếu dữ liệu nhạy cảm.

### Tình huống B: yêu cầu tải lại một thiết lập

Mục tiêu là kích hoạt hành động thay đổi trạng thái đang dùng.

**Phân loại:** write operation có thể phù hợp. Khi thích nghi qua HTTP theo mô hình chuẩn, thao tác dùng POST; không suy ra phải dùng PUT chỉ vì có từ “cập nhật”.

### Tình huống C: bỏ một giá trị thử nghiệm

Mục tiêu là loại bỏ đúng khóa trong bản đồ.

**Phân loại:** delete operation phù hợp với thiết kế mẫu. Endpoint không biến mất; chỉ dữ liệu mà phần thân nhắm tới bị loại bỏ.

### Tình huống D: tên phương thức là readAndReset

Phương thức vừa trả thông tin vừa đặt lại trạng thái.

**Phân tích:** có tác động thay đổi cần được thể hiện rõ. Không gắn `@ReadOperation` chỉ vì phương thức có trả dữ liệu. Có thể tách thao tác đọc và lệnh đặt lại, hoặc thiết kế một lệnh quản trị có hợp đồng rõ ràng.

### Bài tập áp dụng

Chọn một khả năng quản trị có thật và ghi:

1. Dữ liệu hoặc trạng thái nào thuộc phạm vi quản trị?
2. Cần những thao tác nào; thao tác nào không cần tồn tại?
3. Mỗi thao tác có annotation và phương thức HTTP nào?
4. Đầu vào đến từ đường, tham số hay body?
5. Sau thành công, trạng thái và phản hồi mong đợi là gì?
6. Làm sao phân biệt lỗi đầu vào, không có dữ liệu và thiếu quyền?

Bạn hiểu cách phân loại khi giải thích được **ý định, ánh xạ và tác động thực tế** của từng thao tác, rồi kiểm chứng chúng bằng yêu cầu và trạng thái trước–sau.
