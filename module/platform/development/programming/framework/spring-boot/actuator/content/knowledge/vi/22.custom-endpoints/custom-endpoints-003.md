# Khai báo @ReadOperation, @WriteOperation và @DeleteOperation

Một endpoint quản trị có thể cần ba khả năng: đọc trạng thái hiện tại, thay đổi một giá trị và xóa một cấu hình đã đặt. Spring Boot Actuator dùng `@ReadOperation`, `@WriteOperation` và `@DeleteOperation` để mô tả các thao tác ấy trên endpoint tùy chỉnh.

Các annotation này giúp Actuator khám phá phương thức, nhận đầu vào và công bố thao tác qua công nghệ được cấu hình, như HTTP hoặc JMX. Phần thân phương thức vẫn là nơi ta viết hành vi thật.

Bài dùng Spring Boot 3.3.x và Java 21. Ví dụ quản lý các cờ bật/tắt tính năng trong bộ nhớ, đủ nhỏ để quan sát rõ cả ba loại thao tác.

## 1. Vai trò của ba annotation

| Annotation | Ý nghĩa của thao tác | Khi công bố qua HTTP | Ví dụ phù hợp |
| --- | --- | --- | --- |
| `@ReadOperation` | Đọc thông tin/trạng thái | `GET` | Đọc các cờ đang được đặt |
| `@WriteOperation` | Thay đổi hoặc thực hiện một thao tác ghi | `POST` | Đặt giá trị một cờ |
| `@DeleteOperation` | Xóa dữ liệu hoặc trạng thái do endpoint quản lý | `DELETE` | Xóa một cờ đã đặt |

Cả ba nằm trong package `org.springframework.boot.actuate.endpoint.annotation` và được đặt trên phương thức của endpoint. API mô tả chúng là các dấu hiệu xác định loại thao tác: [ReadOperation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/ReadOperation.html) và [WriteOperation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/WriteOperation.html).

Tên phương thức Java không quyết định HTTP method. Một phương thức tên `update` được gắn `@ReadOperation` vẫn được công bố là thao tác đọc; tên không làm nó trở thành `POST`. Vì vậy, nên đặt tên phương thức và viết hành vi nhất quán với annotation.

Các annotation cũng không tự thực hiện nghiệp vụ:

- `@ReadOperation` không tự cấm mọi thay đổi trạng thái trong thân phương thức.
- `@WriteOperation` không tự lưu vào cơ sở dữ liệu hoặc mở transaction.
- `@DeleteOperation` không tự biết phải xóa phần tử nào.
- Loại thao tác không tự cấp quyền cho người gọi.

Hãy giữ thao tác đọc không có tác dụng phụ nghiệp vụ, đặc biệt vì công cụ giám sát có thể gọi nó nhiều lần.

## 2. Endpoint, bean và thao tác liên hệ với nhau thế nào?

```text
Bean Spring có @Endpoint(id = "featureflags")
  ├── @ReadOperation   → đọc thông tin
  ├── @WriteOperation  → ghi/thay đổi
  └── @DeleteOperation → xóa
            ↓
    Actuator khám phá thao tác
            ↓
    Công bố qua HTTP/JMX theo cấu hình
```

Có ba điều kiện khác nhau:

1. **Có bean:** lớp endpoint phải được Spring tạo, chẳng hạn qua `@Component` hoặc một phương thức `@Bean`.
2. **Endpoint được bật:** cấu hình enablement cho phép endpoint hoạt động.
3. **Được công bố qua công nghệ cần dùng:** cấu hình exposure bao gồm endpoint đó trên HTTP hoặc JMX.

Chỉ viết `@Endpoint` trên một lớp chưa được đăng ký thành bean thì chưa đủ. Tương tự, có bean không đồng nghĩa đường dẫn HTTP đã được công bố.

Với `@Endpoint`, các thao tác được mô tả theo cách không phụ thuộc riêng vào Spring MVC. Khi công bố qua JMX, chúng là thao tác của MBean; JMX không dùng các HTTP method GET/POST/DELETE. Nếu cần endpoint chỉ dành cho web, Actuator còn có `@WebEndpoint`, nhưng không cần đổi sang nó cho ví dụ này.

Cơ chế công bố và thực thi endpoint tùy chỉnh được mô tả trong [tài liệu endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

## 3. Ví dụ đầy đủ: quản lý cờ trong bộ nhớ

### 3.1. Chuẩn bị dự án thực hành

Dùng một dự án Gradle độc lập có Gradle Wrapper tương thích, ví dụ Gradle 8.5, và JDK 21. Các tệp dưới đây thuộc dự án thực hành đó.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-operations-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Phiên bản `3.3.0` là mốc để tái lập ví dụ; khi đặt trong dự án đã có, theo phiên bản 3.3.x và bộ phụ thuộc mà dự án quản lý. Ví dụ này dùng BOM qua cơ chế `platform` của Gradle.

Tạo `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    featureflags:
      enabled: true
  endpoints:
    web:
      exposure:
        include: featureflags
```

Cấu hình chỉ công bố endpoint `featureflags` qua web trong ứng dụng thực hành cục bộ. Nó không tự cấp quyền truy cập nếu dự án đã có Spring Security. Bộ phụ thuộc tối thiểu ở trên không thêm Spring Security.

### 3.2. Lớp khởi động

Tạo `src/main/java/demo/EndpointApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointApplication.class, args);
    }
}
```

### 3.3. Lớp endpoint

Tạo `src/main/java/demo/FeatureFlagsEndpoint.java`:

```java
package demo;

import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "featureflags")
public class FeatureFlagsEndpoint {
    private final ConcurrentMap<String, Boolean> flags = new ConcurrentHashMap<>();

    @ReadOperation
    public Map<String, Boolean> readAll() {
        return new TreeMap<>(flags);
    }

    @ReadOperation
    public Boolean readOne(@Selector String name) {
        return flags.get(name);
    }

    @WriteOperation
    public Map<String, Boolean> write(@Selector String name, boolean enabled) {
        flags.put(name, enabled);
        return Map.of(name, enabled);
    }

    @DeleteOperation
    public void delete(@Selector String name) {
        flags.remove(name);
    }
}
```

Các phương thức có trách nhiệm cụ thể:

- `readAll()` trả một bản sao các cờ hiện có. Người nhận không được đưa trực tiếp cấu trúc lưu trữ nội bộ ra để sửa.
- `readOne(name)` đọc một cờ; `null` có nghĩa chưa có giá trị cho tên ấy.
- `write(name, enabled)` thêm cờ mới hoặc thay giá trị cờ đã có.
- `delete(name)` xóa cờ nếu nó tồn tại. Gọi lại khi cờ đã mất vẫn không làm thay đổi trạng thái.

`ConcurrentHashMap` cho phép các thao tác đọc/ghi từng khóa an toàn khi có nhiều luồng. Nó không biến một chuỗi nhiều thao tác thành một transaction. Ví dụ lưu trong RAM của một instance, nên dữ liệu mất khi khởi động lại và không tự đồng bộ giữa các instance.

Trong hệ thống thực tế, mã nghiệp vụ phải đọc cờ từ nguồn thích hợp để sử dụng giá trị đó. Các annotation không tự liên kết bản đồ này với mọi tính năng trong ứng dụng.

## 4. Từ annotation đến đường dẫn HTTP

Giữ base path mặc định `/actuator` và endpoint ID `featureflags`, ta có:

| Phương thức Java | Annotation | HTTP method | Đường dẫn |
| --- | --- | --- | --- |
| `readAll()` | `@ReadOperation` | `GET` | `/actuator/featureflags` |
| `readOne(name)` | `@ReadOperation` | `GET` | `/actuator/featureflags/{name}` |
| `write(name, enabled)` | `@WriteOperation` | `POST` | `/actuator/featureflags/{name}` |
| `delete(name)` | `@DeleteOperation` | `DELETE` | `/actuator/featureflags/{name}` |

`@Selector String name` làm cho `name` trở thành một thành phần đường dẫn. Khi gọi `/actuator/featureflags/checkout`, Actuator truyền chuỗi `checkout` vào tham số đó.

Tên phương thức `readOne` không được tự thêm vào URL. `@WriteOperation` dùng `POST`, kể cả khi hành vi trong ví dụ có thể được diễn đạt bằng PUT trong một API nghiệp vụ khác.

Ở đây có hai thao tác đọc nhưng đường dẫn khác nhau: một đường không có selector và một đường có selector. Ba thao tác đọc/ghi/xóa trên đường có selector cũng phân biệt được bằng HTTP method.

Nếu thêm một thao tác đọc nữa với cùng đường dẫn đã có, chỉ đổi tên phương thức Java sẽ không làm ánh xạ web trở nên duy nhất. Tránh các thao tác trùng điều kiện ánh xạ; kiểm tra cả HTTP method và đường dẫn.

## 5. Gắn đầu vào vào tham số

Với phương thức ghi:

```java
@WriteOperation
public Map<String, Boolean> write(@Selector String name, boolean enabled) {
    flags.put(name, enabled);
    return Map.of(name, enabled);
}
```

Đây là đoạn trích từ lớp endpoint hoàn chỉnh ở trên. Một request tương ứng là:

```http
POST /actuator/featureflags/checkout
Content-Type: application/json
Accept: application/json

{"enabled": true}
```

Hai nguồn đầu vào là:

- `name` lấy từ thành phần đường dẫn do `@Selector` xác định.
- `enabled` lấy từ thuộc tính gốc `enabled` của JSON body.

Đầu vào operation cũng có thể được cung cấp qua query parameter theo cơ chế của Actuator. Khi viết ví dụ và hợp đồng sử dụng, nên chọn một cách rõ ràng, tránh gửi cùng một tham số ở nhiều nguồn rồi dựa vào thứ tự ghi đè.

### Tên tham số phải được giữ khi biên dịch

Actuator cần biết tên `enabled` để gắn đầu vào với tham số Java. Mã endpoint cần được biên dịch với `-parameters`. Spring Boot Gradle plugin trong ví dụ đã cấu hình việc này.

Nếu dùng công cụ biên dịch khác, phải bảo đảm cờ tương đương được bật; đừng chỉ dựa vào việc IDE hiện đúng tên biến. Thiếu metadata tên tham số có thể làm việc khám phá hoặc gọi operation không hoạt động như dự kiến.

### Kiểu đầu vào và tham số tùy chọn

Các tham số của endpoint dùng kiểu đơn giản, chẳng hạn `String`, `boolean`, `int`. Actuator chuyển đổi đầu vào sang kiểu cần thiết trước khi gọi thân phương thức.

Tham số mặc định là bắt buộc. Nếu cần tùy chọn, có thể dùng `org.springframework.lang.Nullable` với kiểu tham chiếu thích hợp, rồi tự quy định cách xử lý khi thiếu. Ví dụ cần chấp nhận `null` thì dùng `Boolean` thay cho kiểu nguyên thủy `boolean`.

Không áp dụng cách viết controller MVC một cách máy móc:

- Không cần `@RequestBody` để Actuator đọc thuộc tính gốc của JSON trong ví dụ.
- Dùng `@Selector` cho thành phần đường dẫn của operation.
- Không đổi toàn bộ đầu vào thành một DTO phức tạp rồi mặc định nó được hỗ trợ như tham số `@RequestBody` của controller.

Giới hạn kiểu đầu vào không có nghĩa đầu ra chỉ được là một giá trị đơn: ví dụ trả `Map` để xuất JSON. Nếu cần hợp đồng HTTP chuyên biệt hơn, hãy cân nhắc endpoint dành cho web hoặc extension phù hợp.

## 6. Hiểu giá trị trả về và mã phản hồi

Bảng dưới áp dụng cho phản hồi mặc định của operation khi được công bố qua HTTP, không phải một wrapper tùy chỉnh mã trạng thái:

| Loại operation | Giá trị trả về | HTTP mặc định |
| --- | --- | --- |
| Read | Có giá trị | `200 OK` |
| Read | Không có giá trị, chẳng hạn `null` | `404 Not Found` |
| Write | Có giá trị | `200 OK` |
| Write | Không có giá trị, chẳng hạn `void` hoặc `null` | `204 No Content` |
| Delete | Có giá trị | `200 OK` |
| Delete | Không có giá trị, chẳng hạn `void` hoặc `null` | `204 No Content` |

Vì vậy, việc chọn kiểu trả về là một phần của hợp đồng operation:

- `readAll()` trả bản đồ rỗng vẫn là **có giá trị**, nên phản hồi là `200` với `{}`.
- `readOne()` trả `Boolean.FALSE` vẫn là **có giá trị**, nên phản hồi là `200` với `false`.
- `readOne()` trả `null` khi tên chưa có nên nhận `404`.
- `write()` trả bản đồ có giá trị nên nhận `200`, không tự trở thành `201` chỉ vì vừa thêm cờ.
- `delete()` trả `void` nên nhận `204`, kể cả trường hợp cờ đã không tồn tại theo cách viết của ví dụ.

Thiếu tham số bắt buộc hoặc không chuyển đổi được tham số sang kiểu cần thiết làm request nhận `400 Bad Request` trước khi thân operation được gọi. Đây khác với ngoại lệ nghiệp vụ phát sinh bên trong phương thức; đừng mặc định mọi `IllegalArgumentException` tự thành `400`.

Khi cần mã HTTP cụ thể ngoài quy tắc mặc định, `WebEndpointResponse` là một công cụ cho operation của extension dành cho web. Nó thể hiện lựa chọn phụ thuộc HTTP; xem [API WebEndpointResponse](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html). Với bài này, giữ các giá trị trả về đơn giản để quan sát đúng hành vi mặc định.


## 7. Chạy và gọi endpoint

### 7.1. Khởi động ứng dụng

Từ thư mục dự án thực hành, trên Linux/macOS:

```bash
./gradlew bootRun
```

Trên PowerShell/Windows:

```powershell
.\gradlew.bat bootRun
```

Có thể đóng tiến trình chạy bằng `bootRun`, rồi đóng gói và chạy JAR:

```bash
./gradlew bootJar
java -jar build/libs/actuator-operations-demo-1.0.0.jar
```

Trên Windows, thay lệnh gọi Wrapper bằng `.\gradlew.bat bootJar`. Lệnh `java -jar` giống nhau. Log khởi động có thời gian và thông tin môi trường thay đổi; các giá trị dưới đây mô tả hợp đồng phản hồi của endpoint, không phải toàn bộ stdout của ứng dụng.

### 7.2. Thử luồng đọc → ghi → đọc → xóa

Các lệnh curl trong phần này dùng cú pháp Bash. Bắt đầu với một tiến trình ứng dụng mới để bản đồ chưa chứa cờ nào.

Đọc tất cả:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags
```

Kết quả: `200 OK`, body `{}`.

Đặt cờ `checkout`:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"enabled":true}' http://localhost:8080/actuator/featureflags/checkout
```

Kết quả: `200 OK`, body `{"checkout":true}`.

Đọc riêng cờ ấy:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

Kết quả: `200 OK`, body `true`.

Đặt lại thành `false` rồi đọc:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"enabled":false}' http://localhost:8080/actuator/featureflags/checkout
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

POST trả `200` với `{"checkout":false}`; GET trả `200` với `false`. Trạng thái tắt không bị hiểu thành “không tồn tại”.

Xóa và kiểm tra lại:

```bash
curl -i -X DELETE http://localhost:8080/actuator/featureflags/checkout
curl -i -H "Accept: application/json" http://localhost:8080/actuator/featureflags/checkout
```

DELETE trả `204 No Content` với body rỗng. GET sau đó trả `404 Not Found` do `readOne()` trả `null`. Gọi DELETE lần nữa vẫn nhận `204` theo cách viết của phương thức.

### 7.3. Gọi từ PowerShell

Để tránh nhầm cách truyền dấu nháy JSON giữa các shell, có thể dùng trực tiếp:

```powershell
$demoEndpointUri = 'http://localhost:8080/actuator/featureflags'
$demoRequestBody = @{ enabled = $true } | ConvertTo-Json

Invoke-RestMethod -Uri "$demoEndpointUri/checkout" -Method Post -ContentType 'application/json' -Body $demoRequestBody
Invoke-RestMethod -Uri "$demoEndpointUri/checkout" -Method Get

$demoDeleteResponse = Invoke-WebRequest -UseBasicParsing -Uri "$demoEndpointUri/checkout" -Method Delete
$demoDeleteResponse.StatusCode
```

Lệnh cuối trả mã `204`. `Invoke-RestMethod` chuyển JSON thành đối tượng PowerShell nên cách hiển thị khác chuỗi JSON gốc của curl. Khi thử ca lỗi như GET sau xóa, các lệnh PowerShell có thể ném lỗi cho HTTP 4xx; đó không có nghĩa ứng dụng đã ngừng chạy.

## 8. Kiểm tra đầu vào lỗi và HTTP method

### Thiếu tham số bắt buộc

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{}' http://localhost:8080/actuator/featureflags/checkout
```

Request không cung cấp `enabled`, nên nhận `400`. Không có giá trị mặc định `false` được tự đưa vào phương thức chỉ vì tham số Java là `boolean`.

### Tham số sai kiểu

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{"enabled":"not-a-boolean"}' http://localhost:8080/actuator/featureflags/checkout
```

Chuỗi này không chuyển được thành `boolean`, nên nhận `400`. Có thể tạo lại cờ hợp lệ trước, gửi request sai, rồi GET lại để xác nhận trạng thái cũ không bị ghi đè.

### Dùng PUT cho WriteOperation

```bash
curl -i -X PUT -H "Content-Type: application/json" -d '{"enabled":true}' http://localhost:8080/actuator/featureflags/checkout
```

Trong ứng dụng tối thiểu này, đường dẫn tồn tại nhưng không có thao tác PUT, nên nhận `405 Method Not Allowed`. Nếu cần một API có hợp đồng PUT/PATCH cụ thể, không suy ra rằng tên phương thức `write` sẽ đổi được ánh xạ cố định của Actuator.

Các ca cần phân biệt trong ví dụ:

| Ca | Mã phản hồi | Ý nghĩa |
| --- | --- | --- |
| GET bản đồ chưa có phần tử | `200` | Bản đồ rỗng là kết quả hợp lệ |
| GET một cờ có giá trị `false` | `200` | Có cờ, giá trị hiện tại là tắt |
| GET một cờ không tồn tại | `404` | Operation trả `null` |
| POST hợp lệ | `200` | Operation ghi và trả một bản đồ |
| POST thiếu/sai kiểu `enabled` | `400` | Chưa gọi được thân operation |
| DELETE theo phương thức trả `void` | `204` | Không có nội dung phản hồi |
| PUT đến đường chỉ có GET/POST/DELETE | `405` | Không có ánh xạ cho method đó |

Việc gọi trực tiếp `new FeatureFlagsEndpoint().write(...)` chỉ kiểm tra logic Java; nó bỏ qua khám phá endpoint, exposure, gắn đầu vào và phản hồi web. Khi kiểm tra hợp đồng operation, cần thêm kiểm tra ở tầng xử lý request, chẳng hạn MockMvc với application context có Actuator, hoặc gọi một ứng dụng đang chạy.

## 9. Lỗi thường gặp khi khai báo operation

| Hiện tượng | Cần kiểm tra |
| --- | --- |
| Không thấy endpoint trên HTTP | Lớp có thành bean không, endpoint có được bật không, web exposure có chứa đúng ID không |
| Gọi `/actuator/featureflags/readAll` không đúng kết quả mong đợi | Tên phương thức không tự tạo thành một đoạn URL; `readAll` có thể bị coi là giá trị selector |
| POST không đến phương thức ghi | Đúng HTTP method, đường dẫn, content type, tên tham số và JSON body chưa |
| Có lỗi liên quan tên tham số | Cờ biên dịch `-parameters` và metadata của đúng lớp được chạy |
| Khởi động báo ánh xạ trùng | Có hai operation cùng HTTP method và cùng hình dạng đường dẫn không |
| GET trả 404 dù endpoint đã được công bố | Operation có đang trả `null` không; phân biệt với việc endpoint/path chưa có |
| POST/DELETE trả 401 hoặc 403 | Xác thực, phân quyền và CSRF trong cấu hình Spring Security đang có |
| Ghi xong nhưng dữ liệu mất sau restart | Ví dụ lưu RAM, chưa có cơ chế lưu bền |
| Một instance thấy giá trị khác instance khác | Mỗi instance đang giữ bản đồ riêng |

Trong dự án có Spring Security, đặc biệt cần phân biệt lỗi ánh xạ với request bị chặn trước khi đến operation. `403` trên POST/DELETE có thể liên quan CSRF, ngay cả khi người gọi đã xác thực. Hãy áp dụng chính sách bảo vệ phù hợp cho endpoint quản trị; annotation operation và exposure không tự thay thế chính sách ấy.

Khi thay đổi trạng thái qua endpoint trong hệ thống thật, xác định rõ quyền ghi/xóa, phạm vi thay đổi và cách ghi nhận hành động. Đây là một phần của thiết kế thao tác quản trị, không phải hiệu ứng có sẵn của `@WriteOperation` hay `@DeleteOperation`.

## 10. Thực hành để hiểu đúng hợp đồng

### Bài tập 1: đổi kiểu trả về của thao tác ghi

Trong bản sao dự án thực hành, đổi `write()` sang trả `void` nhưng giữ nguyên việc đặt giá trị trong bản đồ. Gọi POST rồi GET lại.

Điều cần nhận ra: POST chuyển từ `200` có body sang `204` không có body, trong khi giá trị vẫn được ghi. Mã phản hồi mặc định liên quan cả loại operation lẫn kết quả trả về.

### Bài tập 2: đọc giá trị tắt và giá trị chưa có

Đặt cờ `checkout=false`, GET một lần, xóa rồi GET lại.

Giải thích được sự khác nhau giữa `200 false` và `404`: giá trị `false` là dữ liệu tồn tại; `null` mới biểu diễn việc không tìm thấy trong cách thiết kế này.

### Bài tập 3: thay tên phương thức Java

Đổi tên `write()` thành `setFlag()`, giữ `@WriteOperation` và các tham số. Gọi lại cùng đường dẫn POST.

Ánh xạ HTTP vẫn dựa vào loại operation, endpoint ID và selector. Việc đổi tên Java không tạo URL `/setFlag`. Khi sử dụng JMX, cần kiểm tra lại tên thao tác được công bố vì đó là một hợp đồng truy cập khác.

### Bài tập 4: kiểm tra ranh giới bắt buộc

Tạo một cờ hợp lệ, gửi POST thiếu `enabled` hoặc chứa giá trị sai kiểu, rồi đọc lại.

Kết quả mong đợi: request lỗi nhận `400`, giá trị cũ giữ nguyên vì thân phương thức ghi chưa được gọi. Nếu cần thêm quy tắc nghiệp vụ vượt quá chuyển đổi kiểu, hãy viết và kiểm tra quy tắc ấy riêng.
