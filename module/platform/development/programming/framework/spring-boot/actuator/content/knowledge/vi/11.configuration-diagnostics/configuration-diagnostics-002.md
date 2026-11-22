# Tra cứu một thuộc tính cụ thể và hiểu giá trị đã được che

## 1. Bắt đầu từ một câu hỏi cấu hình

Giả sử ứng dụng gọi dịch vụ ngoài với thuộc tính `demo.client.timeout`. File cấu hình ghi `2s`, nhưng môi trường triển khai có thể ghi đè thành `5s`. Để chẩn đoán, cần biết thuộc tính có tồn tại trong tiến trình đang chạy, nguồn nào đang có ưu tiên và phản hồi có cho phép xem giá trị hay không.

Spring Boot Actuator cung cấp tuyến tra cứu một thuộc tính:

```http
GET /actuator/env/demo.client.timeout
```

Đây là một cách quan sát `Environment` của ứng dụng. Thông tin hữu ích gồm nguồn có hiệu lực, các nguồn cùng khai báo thuộc tính và vị trí xuất xứ khi nguồn đó cung cấp được. API được mô tả tại [Environment endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html#_retrieving_a_single_property).

Ba câu hỏi nên được trả lời riêng:

1. **Tìm thấy thuộc tính chưa?** Thuộc tính có thể chưa được nạp, sai tên hoặc nằm trong profile khác.
2. **Nguồn nào có hiệu lực?** Một giá trị từ tham số khởi động có thể ghi đè cấu hình trong file.
3. **Được xem giá trị đến mức nào?** Dữ liệu có thể tồn tại và đang được sử dụng dù phản hồi chỉ hiện `******`.

Ví dụ:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  }
}
```

Đây là phần trích từ phản hồi. Nó cho biết giá trị có hiệu lực đến từ `commandLineArgs` và giá trị trả ra đã được che. Không thể kết luận giá trị thật là `2s`, `5s`, rỗng hay một chuỗi gồm sáu dấu sao chỉ từ phần thân này.

Trong Spring Boot 3.3, chính sách mặc định che toàn bộ giá trị ở endpoint `env`, kể cả một thuộc tính không có tên gợi ý bí mật. Vì vậy, thấy dấu che ở `demo.client.timeout` là hành vi có thể hoàn toàn bình thường.

## 2. Đọc phản hồi theo nguồn và mức ưu tiên

Một phản hồi tra cứu đơn lẻ có thể có các thành phần sau:

| Thành phần | Cách sử dụng khi chẩn đoán |
| --- | --- |
| `property.source` | Tên nguồn cung cấp giá trị có hiệu lực của thuộc tính |
| `property.value` | Giá trị được phép trả ra; có thể đã bị che |
| `activeProfiles` | Các profile đang hoạt động |
| `defaultProfiles` | Các profile mặc định được khai báo |
| `propertySources` | Các nguồn cấu hình theo thứ tự ưu tiên |
| `propertySources[i].name` | Tên của một nguồn |
| `propertySources[i].property.value` | Giá trị của thuộc tính trong chính nguồn đó, nếu có; cũng có thể bị che |
| `propertySources[i].property.origin` | Xuất xứ nếu có, chẳng hạn resource và vị trí trong file |

Chỉ số `i` trong bảng là ký hiệu vị trí, không phải một phần tên thuộc tính. Không cố định một chỉ số mảng trong công cụ chẩn đoán: nguồn có thể thay đổi khi đổi cách khởi động, thêm cấu hình ngoài hoặc bật profile.

Một nguồn xuất hiện trong danh sách nhưng không có mục `property` có nghĩa nguồn đó không cung cấp thuộc tính đang tra cứu trong phản hồi này. Nó không cho biết toàn bộ nguồn đó trống.

### Nguồn có hiệu lực và nguồn bị ghi đè

Trong tình huống đơn giản:

```text
commandLineArgs:
    demo.client.timeout = 5s

application.properties:
    demo.client.timeout = 2s
```

Spring Boot ưu tiên tham số dòng lệnh hơn cấu hình trong file trong trường hợp này. Khi không có nguồn ưu tiên cao hơn cung cấp thuộc tính, giá trị đọc từ `Environment` là `5s`. File vẫn chứa `2s`, nhưng sửa riêng giá trị đó chưa chắc thay đổi kết quả của lần khởi động có tham số ghi đè.

Thứ tự các nguồn cấu hình do Spring Boot quy định được trình bày trong [Externalized Configuration 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html). Với một tiến trình cụ thể, dùng phản hồi thực tế để đối chiếu; tránh đoán chỉ từ file đang mở trong trình soạn thảo.

Nếu mọi `value` đều là `******`, vẫn có thể xác định **nguồn đang được chọn** qua `property.source` và thấy **những nguồn cùng cung cấp khóa** qua `propertySources`. Tuy nhiên, không thể suy ra các giá trị bị che có giống nhau hay khác nhau.

`origin` giúp tìm chỗ cần kiểm tra, nhưng không phải nguồn nào cũng có xuất xứ chi tiết. Tên nguồn và đường dẫn có thể thay đổi giữa chạy từ IDE, JAR, container và cấu hình mount ngoài.

## 3. Ví dụ có thể chạy với Spring Boot 3.3 và Java 21

Ví dụ sau là ứng dụng thực hành cục bộ, chỉ dùng dữ liệu giả và một thuộc tính timeout thông thường. Nó cần JDK 21 và Gradle wrapper 8.5 đã có trong thư mục thực hành. Lần build đầu cần truy cập kho plugin và dependency nếu máy chưa có cache.

Cấu trúc tối thiểu:

```text
env-lookup-demo/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/main/java/com/example/envlookup/EnvLookupApplication.java
  src/main/resources/application.properties
```

Các tệp wrapper là bộ wrapper chuẩn của Gradle. Nếu dùng một ứng dụng đã có sẵn wrapper và các starter tương ứng, có thể đặt lớp và cấu hình mẫu trong phạm vi ứng dụng đó.

### 3.1. Cấu hình build và lớp khởi động

`settings.gradle`:

```groovy
rootProject.name = 'env-lookup-demo'
```

`build.gradle`, Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
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

Bản `3.3.0` được cố định để ví dụ tái lập trong dòng Spring Boot 3.3; khi làm việc với dự án cụ thể, theo phiên bản đã được dự án lựa chọn và kiểm chứng.

`src/main/java/com/example/envlookup/EnvLookupApplication.java`:

```java
package com.example.envlookup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EnvLookupApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnvLookupApplication.class, args);
    }
}
```

Lớp này khởi động ứng dụng Spring Boot; nó cần classpath của các dependency trong build. Không chạy file bằng `javac` riêng mà bỏ các thư viện Spring.

### 3.2. Cấu hình ứng dụng

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
demo.client.timeout=2s
management.endpoints.web.exposure.include=health,env
management.endpoint.env.show-values=never
```

`server.address=127.0.0.1` giới hạn điểm nghe của bài thực hành trên máy cá nhân. Trong ví dụ không thêm Spring Security nên endpoint không có bước đăng nhập do ứng dụng cung cấp. Không đưa cấu hình thực hành này lên một địa chỉ công khai.

`exposure.include=health,env` đưa đúng các endpoint cần quan sát ra HTTP. Nếu dự án đã tắt `env` ở lớp cấu hình khác, cần đối chiếu cả trạng thái bật endpoint. Exposure, xác thực người gọi và quyền xem giá trị là các lớp điều khiển khác nhau.

Giữ rõ `management.endpoint.env.show-values=never` để bài thực hành có hành vi ổn định khi quan sát. Thuộc tính này cấu hình dữ liệu trả ra, không thay đổi giá trị `demo.client.timeout` mà ứng dụng sử dụng.

### 3.3. Build và tạo tình huống ghi đè

Từ thư mục ứng dụng, chạy PowerShell:

```powershell
.\gradlew.bat clean bootJar
java -jar build/libs/env-lookup-demo-1.0.0.jar --demo.client.timeout=5s
```

Giữ tiến trình chạy và mở một terminal khác để tra cứu:

```powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'
```

Bài dùng cổng `8080` và đường dẫn `/actuator` mặc định. Nếu đã đổi cổng, context path, management base path hoặc tuyến proxy thì dùng URL tương ứng với tiến trình thực tế.

Đọc hai trường cần thiết thay vì dán toàn bộ JSON vào báo cáo:

```powershell
$result = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'
$result.property.source
$result.property.value
```

Với cấu hình và tham số khởi động mẫu, hai dòng đầu ra là:

```text
commandLineArgs
******
```

Bộ đôi này xác nhận nguồn có hiệu lực là tham số dòng lệnh và phản hồi đang che giá trị. Mã của ứng dụng vẫn có thể đọc `5s` từ `Environment`; dấu che chỉ thuộc biểu diễn chẩn đoán trả ra.

Để xem nguồn file nào cũng khai báo khóa, lọc các mục có `property`:

```powershell
$result.propertySources |
    Where-Object { $null -ne $_.property } |
    ForEach-Object {
        [pscustomobject]@{
            Source = $_.name
            Value = $_.property.value
            Origin = $_.property.origin
        }
    }
```

Tên resource và vị trí dòng phụ thuộc cách đóng gói. Không sao chép một `origin` của lần chạy khác rồi coi đó là chứng cứ của tiến trình đang kiểm tra.

### 3.4. Kiểm tra suy luận về ưu tiên

Dừng tiến trình mẫu, sau đó chạy cùng JAR mà không truyền thuộc tính ghi đè:

```powershell
java -jar build/libs/env-lookup-demo-1.0.0.jar
```

Trong môi trường thực hành không có nguồn khác ghi đè, `property.source` sẽ chuyển sang nguồn cấu hình từ `application.properties`. `property.value` vẫn là `******` vì chính sách che không đổi. Không dùng sự giống nhau của hai dấu che để kết luận giá trị thực không đổi.

Nếu nguồn không chuyển như dự kiến, tìm cấu hình khác trong môi trường của chính tiến trình: tham số còn sót trong IDE, biến môi trường, thuộc tính JVM hoặc cấu hình ngoài. Bài thực hành không yêu cầu xuất mọi giá trị của những nguồn đó.

## 4. “Đã được che” có ý nghĩa chính xác đến đâu?

Che giá trị (sanitization) là thay giá trị trong kết quả quan sát bằng biểu diễn được phép công bố. Nó giúp hạn chế dữ liệu nhạy cảm trong phản hồi, không mã hóa thuộc tính đang nằm trong bộ nhớ và không làm rỗng cấu hình mà bean sử dụng.

Với chính sách `never`, phản hồi của một khóa đã tìm thấy có thể giúp xác nhận tên nguồn và xuất xứ mà không tiết lộ nội dung giá trị. Cách triển khai API thuộc về [EnvironmentEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/env/EnvironmentEndpoint.html); xử lý giá trị đã che dùng cơ chế [Sanitizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/Sanitizer.html).

Từ `******`, không suy ra được:

- Độ dài của giá trị thật.
- Giá trị có hợp lệ về mặt nghiệp vụ hay không.
- Giá trị đang bằng giá trị mặc định hay bị ghi đè thành giá trị khác.
- Tên khóa đã khớp một danh sách tên bí mật nào.
- Người gọi đã có quyền đăng nhập hoặc quyền xem giá trị rõ.

Dấu che có thể trùng với một chuỗi thật mà người dùng cố ý cấu hình. Khi cần phân biệt, dựa trên chính sách và kiểm tra có kiểm soát của ứng dụng; không đoán từ sáu ký tự trong JSON.

### Ba chính sách xem giá trị

Cấu hình theo endpoint bằng `management.endpoint.env.show-values`:

| Chính sách | Hành vi khi yêu cầu đã được phép tới endpoint |
| --- | --- |
| `never` | Luôn che giá trị |
| `when-authorized` | Chỉ cho người gọi đủ điều kiện xem giá trị chưa che |
| `always` | Cho mọi người gọi tới được endpoint xem giá trị chưa che |

Hàm `SanitizingFunction` tùy chỉnh vẫn có thể che một giá trị khi chính sách cho phép xem rõ. Vì thế, đăng nhập thành công chưa bảo đảm mọi trường đều được hiển thị nguyên văn.

Quy định của Spring Boot 3.3 được mô tả ở [Sanitize Sensitive Values](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization). Đối với HTTP, `when-authorized` xét danh tính đã xác thực và vai trò được cấu hình; nếu không chỉ định vai trò, danh tính đã xác thực có thể đủ điều kiện xem rõ.

Chỉ khi đã có yêu cầu và kênh quản trị phù hợp, một cấu hình có thể là:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: ENV_DIAGNOSTICS
```

Đây là phần minh họa chính sách, không phải bước bắt buộc của bài thực hành. Nếu ứng dụng dùng `application.properties` như ví dụ trên, biểu diễn tương đương là:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ENV_DIAGNOSTICS
```

Chọn một cách cấu hình nhất quán và kiểm tra giá trị thực có hiệu lực. Không thêm đồng thời nhiều file chỉ để thử thuộc tính rồi quên các thiết lập ưu tiên nhau.

Cấu hình `roles` không tạo người dùng, không cấp vai trò và không tự bảo vệ tuyến HTTP. Vai trò phải được ánh xạ đúng trong cơ chế bảo mật đang dùng. Lớp Spring Security/gateway có thể chặn yêu cầu trước khi Actuator thực hiện kiểm tra quyền xem.

`always` là phạm vi cho xem rộng đối với mọi yêu cầu tới được endpoint, kể cả khi URL được cho là khó đoán. Không đổi sang `always` chỉ để làm mất dấu che trong một lần chẩn đoán thông thường.

### Ma trận quyền: phân biệt được truy cập và được thấy giá trị

Giả sử tuyến HTTP đã cho phép một người gọi đến được endpoint và đang dùng `when-authorized` với vai trò `ENV_DIAGNOSTICS`:

| Trạng thái người gọi tại Actuator | Giá trị thông thường, không bị hàm tùy chỉnh che |
| --- | --- |
| Chưa có danh tính xác thực | `******` |
| Đã xác thực nhưng thiếu vai trò yêu cầu | `******` |
| Đã xác thực và có vai trò yêu cầu | Giá trị chưa che |

Nếu lớp bảo mật HTTP đã từ chối yêu cầu bằng `401` hoặc `403` thì người gọi chưa tới bước đọc dữ liệu này. Ngược lại, `200` với giá trị đã che không chứng minh người gọi có quyền xem rõ.

Nhánh JMX có quy tắc xét quyền khác HTTP; không lấy kết quả quan sát qua JMX để suy ra người gọi HTTP sẽ thấy gì. Bài thực hành đang kiểm tra HTTP.

## 5. Tra cứu một khóa là cách thu hẹp quan sát

Khi chỉ điều tra `demo.client.timeout`, gọi đúng tuyến của khóa đó giúp giảm lượng thông tin phải đọc và xử lý. Không cần lấy toàn bộ `/actuator/env` rồi tìm bằng mắt.

Tuy nhiên, việc đưa endpoint `env` ra HTTP thường cũng làm tuyến đọc toàn bộ môi trường có mặt. Chỉ gọi một khóa ở phía công cụ không tạo ra danh sách thuộc tính được phép đọc ở phía máy chủ. Nếu cần giới hạn theo khóa, phải thiết kế giới hạn ở lớp quản trị thích hợp và kiểm chứng các tuyến được truy cập.

Ngay khi giá trị đã được che, phản hồi vẫn có thể chứa tên nguồn, profile và đường dẫn resource. Các chi tiết đó có thể tiết lộ cấu trúc triển khai hoặc đường dẫn có tên người dùng. Chỉ chia sẻ phần chứng cứ cần thiết cho vấn đề đang xử lý.

Một báo cáo ngắn có thể ghi:

```text
Thuộc tính: demo.client.timeout
Tiến trình: ứng dụng thực hành cục bộ, cổng 8080
Nguồn có hiệu lực: commandLineArgs
Giá trị trong phản hồi: đã che theo chính sách never
Nguồn khác cũng khai báo: application.properties
Kết luận: cần kiểm tra tham số khởi động trước khi sửa file
```

Báo cáo này không khẳng định một giá trị thực chưa được quan sát trong kênh được phép. Với bí mật thật, không đưa nội dung bí mật vào ticket, chat, ảnh chụp hoặc URL để chứng minh đã tìm thấy.

## 6. Phân biệt thuộc tính không tồn tại, bị che và truy cập thất bại

| Quan sát | Hướng kiểm tra |
| --- | --- |
| `200`, có `property` và `value="******"` | Thuộc tính đã được tìm thấy; xem nguồn và chính sách che |
| `200`, thấy giá trị rõ | Kiểm tra chính sách xem, vai trò và việc có đang quan sát đúng môi trường không |
| `404` khi tra một khóa | Có thể khóa không có; cũng phải loại trừ sai URL, endpoint bị tắt/chưa expose hoặc proxy trả lỗi |
| `401/403` | Kiểm tra lớp xác thực/phân quyền; không suy ra khóa có hay không từ lỗi này |
| `5xx` hoặc kết nối thất bại | Điều tra lỗi xử lý, mạng/cổng và log đã kiểm soát; chưa đủ chứng cứ về thuộc tính |

Trong ví dụ đã chạy đúng endpoint, tra một khóa chắc chắn không được khai báo:

```powershell
curl.exe --silent --output NUL --write-out '%{http_code}' 'http://127.0.0.1:8080/actuator/env/demo.no-such-property'
```

Mã trạng thái dự kiến là `404`. Để hiểu đúng kết quả, đối chiếu với yêu cầu tới khóa mẫu đã biết tồn tại trên cùng tiến trình; một lỗi tuyến không đủ chứng minh riêng khóa bị thiếu.

### Đúng tên khóa và đúng tiến trình

Dùng tên thuộc tính đã được ứng dụng quy ước, chẳng hạn `demo.client.timeout`. Khi nguồn là biến môi trường, tên vật lý có thể dùng chữ hoa và dấu gạch dưới; kiểm tra cả tên nguồn và quy tắc ánh xạ cấu hình của Spring Boot.

Đừng đồng nhất mọi thao tác tra `Environment` với toàn bộ cơ chế ràng buộc `@ConfigurationProperties`. Nếu nghi ngờ khác biệt tên, kiểu dữ liệu hoặc giá trị mặc định của một bean, kiểm tra có mục tiêu tại ranh giới cấu hình của bean đó. Ví dụ, chuỗi `5s` còn cần được chuyển đổi và sử dụng theo kiểu mà ứng dụng định nghĩa.

`env` phản ánh môi trường cấu hình được quan sát tại lúc gọi. Một bean đã chụp giá trị khi khởi tạo có thể giữ giá trị đó; endpoint không chứng minh rằng tất cả bean, thư viện hoặc kết nối đã nhận một thay đổi động. Đối chiếu hành vi thực khi đó là câu hỏi cần trả lời.

Trong hệ thống nhiều bản sao, bảo đảm đang tra đúng bản sao hoặc ghi nhận rõ bản sao đã gọi. Hai tiến trình có thể nhận cấu hình khác nhau dù chạy cùng phiên bản JAR.

## 7. Quy trình chẩn đoán có thể lặp lại

1. **Chốt tên thuộc tính và tiến trình.** Ghi cổng/base path, môi trường và bản sao cần kiểm tra.
2. **Tra đúng một khóa.** Quan sát mã HTTP trước, rồi phân tích JSON nếu có.
3. **Đọc nguồn có hiệu lực.** Dùng `property.source` để tìm lớp cấu hình phải đối chiếu.
4. **Đọc các nguồn cùng cung cấp khóa.** Dùng `propertySources` và `origin` khi có để nhận ra nguồn bị ghi đè.
5. **Diễn giải dấu che theo chính sách.** Không kết luận giá trị thật hoặc sai mật khẩu chỉ từ `******`.
6. **Kiểm tra đầu vào tại nguồn được chọn.** Với tham số khởi động, xem cấu hình launch/triển khai được phép; với file, xem đúng resource/profile của tiến trình.
7. **Chỉ quan sát giá trị rõ khi có nhu cầu và quyền phù hợp.** Ưu tiên chứng cứ không chứa bí mật; xác nhận hành vi nghiệp vụ bằng phép kiểm tra có mục tiêu.
8. **Kiểm tra lại sau thay đổi.** Khởi động lại hoặc dùng cơ chế cập nhật được ứng dụng hỗ trợ; không mặc định sửa file sẽ cập nhật bean đang chạy.

Không log toàn bộ `Environment` hoặc gọi `System.getenv()` rồi in mọi giá trị để vượt qua dấu che. Cách đó tạo thêm một kênh công bố dữ liệu, trong khi vấn đề cần giải có thể chỉ là một tham số ghi đè.

## 8. Tự kiểm tra bài thực hành

Với tiến trình đang chạy bằng `--demo.client.timeout=5s` và chính sách `never`, thực hiện kiểm tra nhỏ sau:

```powershell
$result = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'

if ($result.property.source -ne 'commandLineArgs') {
    throw 'Nguon co hieu luc khong dung du kien'
}

if ($result.property.value -ne '******') {
    throw 'Gia tri chua duoc che theo hop dong bai thuc hanh'
}

foreach ($source in $result.propertySources) {
    if ($null -ne $source.property -and $source.property.value -ne '******') {
        throw 'Mot nguon da tra gia tri chua che'
    }
}

'PASS'
```

Kết quả đầu ra khi các điều kiện đúng:

```text
PASS
```

Phép kiểm tra này xác nhận nguồn và biểu diễn đã che, không đọc giá trị thật để so sánh. Nó cũng không thay thế kiểm tra quyền truy cập của môi trường triển khai.

Tiếp tục các tình huống:

- Bỏ tham số ghi đè, chạy lại và giải thích vì sao nguồn đổi nhưng dấu che vẫn giống nhau.
- Tra một khóa không tồn tại rồi so sánh với khóa mẫu đã biết tồn tại.
- Liệt kê những gì vẫn biết được khi mọi giá trị đều bị che và những điều chưa có chứng cứ.
- Trong môi trường kiểm thử có bảo mật, kiểm tra người chưa đăng nhập, người thiếu vai trò và người đủ vai trò theo chính sách của dự án; chỉ dùng dữ liệu giả.
- Nếu đang dùng hàm che tùy chỉnh, xác nhận giá trị mà hàm bảo vệ vẫn được che khi một người dùng có quyền xem các giá trị khác.

Kỹ năng cần hình thành là tìm đúng nguồn cấu hình của tiến trình và diễn giải đúng giới hạn của phản hồi. Khi đã phân biệt việc tìm thấy khóa, quyền truy cập endpoint và quyền xem giá trị, dấu che trở thành thông tin có thể giải thích trong quá trình chẩn đoán.
