# Dùng endpoint env để xác định nguồn và thứ tự ưu tiên của cấu hình

## 1. Vấn đề cần giải quyết: đã sửa tệp nhưng ứng dụng vẫn dùng giá trị khác

Giả sử `application.yml` khai báo `demo.message: from-file`, nhưng ứng dụng lại nhận `from-env`. Sửa tệp thêm lần nữa chưa chắc giải quyết được vấn đề: cùng một khóa cấu hình có thể còn được khai báo trong biến môi trường, thuộc tính JVM hoặc tham số khởi động.

Spring tập hợp các nguồn cấu hình vào `Environment`. Mỗi nguồn được biểu diễn bằng một `PropertySource` và có vị trí trong thứ tự tra cứu. Khi nhiều nguồn cung cấp cùng một khóa đơn, nguồn có độ ưu tiên cao hơn quyết định giá trị được chọn; các khai báo ở nguồn thấp hơn vẫn có thể tồn tại.

Endpoint Actuator `env` giúp trả lời ba câu hỏi:

1. **Khóa này được cung cấp bởi nguồn nào?**
2. **Những nguồn nào khác cũng khai báo khóa đó nhưng đang bị ghi đè?**
3. **Khai báo ban đầu nằm ở đâu, nếu có thông tin vị trí?**

Đây là công cụ chẩn đoán `Environment` của **tiến trình đang chạy**, không chỉ là cách đọc lại một tệp trong repository. Bài dùng Spring Boot **3.3.x**, JDK **21** và một thuộc tính thử nghiệm không nhạy cảm: `demo.message`.

## 2. Mô hình tra cứu: đi theo thứ tự ưu tiên và tìm nguồn có khóa

Xét ba nguồn cùng khai báo `demo.message`:

```text
Ưu tiên cao
    commandLineArgs     → demo.message = from-cli
    systemEnvironment   → DEMO_MESSAGE = from-env
    application.yml     → demo.message = from-file
Ưu tiên thấp

Khóa demo.message được chọn từ commandLineArgs.
```

Có hai điểm dễ nhầm:

- Nguồn đầu tiên trong danh sách tổng thể không nhất thiết có khóa đang tìm. Phải tìm **nguồn đầu tiên cung cấp khóa đó**, không lấy máy móc `propertySources[0]`.
- Giá trị trong tệp không biến mất khi bị ghi đè. Nó có thể được chọn trở lại sau khi bỏ khai báo ở nguồn cao hơn và khởi động lại ứng dụng.

Trong nhóm nguồn thường dùng của một ứng dụng thông thường, có thể ghi nhớ thứ tự rút gọn sau, từ cao xuống thấp:

```text
Tham số ứng dụng --key=value
    > SPRING_APPLICATION_JSON
    > thuộc tính JVM -Dkey=value
    > biến môi trường hệ điều hành
    > dữ liệu cấu hình application.properties / application.yml
    > default properties do SpringApplication thiết lập
```

Đây là **một phần của thứ tự đầy đủ**. Môi trường Servlet, kiểm thử, Devtools và các nguồn do ứng dụng hoặc thư viện thêm vào có thể bổ sung những vị trí khác. Không dùng sơ đồ rút gọn để phủ nhận danh sách thực tế mà ứng dụng đang báo cáo. Tham khảo [thứ tự nguồn cấu hình của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Tài liệu cấu hình có thể liệt kê nguồn theo hướng nguồn xuất hiện sau ghi đè nguồn trước. Trong phản hồi `env`, `propertySources` được sắp theo ưu tiên tra cứu, nguồn cao hơn đứng trước. Cần nhận biết hướng của danh sách thay vì chỉ nhớ số thứ tự.

## 3. Chuẩn bị ứng dụng và công bố endpoint

### 3.1. Điều kiện của ví dụ

Dùng một ứng dụng web Spring Boot 3.3.x có sẵn lớp khởi động và Gradle Wrapper. Trong khối `dependencies`, bảo đảm có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là đoạn bổ sung vào dự án Spring Boot đã được cấu hình plugin và quản lý dependency, không phải toàn bộ `build.gradle` độc lập. Nếu dự án đang dùng WebFlux, giữ starter WebFlux hiện có; không cần thêm MVC cho mục đích đọc `env`.

Ví dụ thực hành giả định không có Spring Security, không có proxy và không đổi context path. Với ứng dụng đã có bảo mật, dùng tài khoản và quyền truy cập đã được thiết lập cho endpoint quản trị.

### 3.2. Cấu hình cho phòng thực hành trên máy cá nhân

Đặt nội dung sau vào `src/main/resources/application.yml` của ứng dụng ví dụ:

```yaml
demo:
  message: from-file

server:
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,env"
  endpoint:
    env:
      enabled: true
      show-values: never
```

Ở cấu hình này, API nghiệp vụ dùng cổng `8080`, còn Actuator dùng cổng `8081` và chỉ lắng nghe trên loopback. Khi hợp nhất với cấu hình có sẵn, giữ một khóa `management` chung; không tạo hai khối YAML trùng khóa ở cùng cấp.

Trong Spring Boot 3.3, cần phân biệt **bật endpoint**, **công bố qua HTTP** và **được phép truy cập**. `enabled: true` không tự thêm `env` vào danh sách HTTP exposure. `show-values` chỉ điều khiển việc hiện giá trị, không phải quy tắc cho phép truy cập URL.

Không nhầm `management.info.env.enabled` với cấu hình trong bài: thuộc tính đó bật nguồn thông tin `info.*` cho endpoint `info`, không công bố endpoint `env`.

Cách tách cổng và giới hạn địa chỉ quản trị được mô tả trong [tài liệu quản trị qua HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html). Khi chạy trong container hoặc máy từ xa, `127.0.0.1` thuộc môi trường đó; terminal trên máy cá nhân không tự truy cập được loopback của máy khác.

## 4. Chọn cách đọc phù hợp: toàn bộ môi trường hay một khóa

### 4.1. Đọc một khóa trước

Với ví dụ trên, dùng Windows PowerShell:

```powershell
curl.exe -i http://127.0.0.1:8081/actuator/env/demo.message
```

Trên macOS/Linux:

```bash
curl -i http://127.0.0.1:8081/actuator/env/demo.message
```

Đường dẫn `/actuator/env/{property.name}` phù hợp khi đã biết khóa cần điều tra. Bắt đầu từ một khóa cụ thể giúp tránh đọc hoặc chia sẻ cả danh sách cấu hình không liên quan.

Giả sử ứng dụng được chạy với cả biến môi trường và tham số dòng lệnh. Phản hồi dưới đây **đã rút gọn chỉ giữ các nguồn cùng khai báo khóa**, với các giá trị bị che:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  },
  "activeProfiles": [],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "property": {
        "value": "******"
      }
    },
    {
      "name": "systemEnvironment",
      "property": {
        "value": "******"
      }
    },
    {
      "name": "Config resource 'class path resource [application.yml]' via location 'optional:classpath:/'",
      "property": {
        "value": "******",
        "origin": "class path resource [application.yml] - 2:12"
      }
    }
  ]
}
```

Đọc lần lượt:

| Thành phần | Cách hiểu khi chẩn đoán |
| --- | --- |
| `property.source` | Nguồn được chọn cho khóa đang truy vấn |
| `property.value` | Giá trị mà endpoint cho phép hiển thị; có thể bị che |
| `propertySources[].name` | Tên từng nguồn theo thứ tự ưu tiên |
| `propertySources[].property` | Khai báo của khóa tại nguồn đó, nếu có |
| `propertySources[].property.origin` | Vị trí gốc của khai báo, nếu nguồn cung cấp thông tin này |
| `activeProfiles` | Những profile đang hoạt động |
| `defaultProfiles` | Những profile mặc định; không đồng nghĩa với danh sách profile đang hoạt động |

Phản hồi thực tế có thể chứa thêm nguồn không cung cấp khóa, khi đó mục của nguồn đó không có `property`. Tên nguồn, đường dẫn tài nguyên và vị trí dòng/cột phụ thuộc ứng dụng; không cố định chuỗi tên tệp minh họa trong công cụ kiểm tra.

Cấu trúc hai kiểu phản hồi được mô tả tại [API `env` của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html).

### 4.2. Đọc toàn bộ khi cần khảo sát

```powershell
curl.exe http://127.0.0.1:8081/actuator/env
```

Ở phản hồi toàn bộ, mỗi nguồn dùng `properties` là một đối tượng chứa nhiều khóa. Ví dụ rút gọn:

```json
{
  "activeProfiles": [],
  "defaultProfiles": ["default"],
  "propertySources": [
    {
      "name": "commandLineArgs",
      "properties": {
        "demo.message": {
          "value": "******"
        }
      }
    }
  ]
}
```

Lưu ý khác biệt về hình dạng dữ liệu: truy vấn một khóa dùng `property` tại từng nguồn, còn truy vấn toàn bộ dùng `properties` chứa các khóa. Viết công cụ đọc JSON bằng nhầm hình dạng sẽ dẫn đến kết luận thiếu dữ liệu dù endpoint đang hoạt động.

## 5. Thực nghiệm: xác định nguồn thắng qua ba lần chạy

### 5.1. Lần chạy có tham số dòng lệnh và biến môi trường

Trong một terminal PowerShell dành cho bài thực hành, lưu giá trị cũ trước khi đặt biến:

```powershell
$previousDemoMessage = $env:DEMO_MESSAGE
$env:DEMO_MESSAGE = 'from-env'
.\gradlew.bat bootRun --args="--demo.message=from-cli"
```

Ở terminal khác, gọi `/actuator/env/demo.message`. Kỳ vọng:

- `property.source` là `commandLineArgs`.
- Khai báo từ `systemEnvironment` và tệp cấu hình vẫn có thể xuất hiện phía dưới.
- Với `show-values: never`, các giá trị vẫn là `******`; thông tin nguồn vẫn đủ để xác định bên nào thắng.

`DEMO_MESSAGE` là dạng biến môi trường được dùng cho khóa `demo.message` trong ví dụ này. Tên thật trong danh sách toàn bộ có thể là `DEMO_MESSAGE`, trong khi truy vấn khóa dùng `demo.message`. Không vì khác hình thức tên mà vội kết luận đó là hai cấu hình không liên quan.

Trên macOS/Linux, lần chạy tương đương là:

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun --args='--demo.message=from-cli'
```

### 5.2. Bỏ tham số ứng dụng, giữ biến môi trường

Dừng ứng dụng bằng `Ctrl+C`. Trong terminal PowerShell đã đặt biến, chạy:

```powershell
.\gradlew.bat bootRun
```

Gọi lại endpoint. Khi không có nguồn cao hơn khác khai báo cùng khóa, `property.source` chuyển thành `systemEnvironment`. Tệp vẫn chứa `from-file`, nhưng biến môi trường đang được ưu tiên.

Trên macOS/Linux:

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun
```

### 5.3. Bỏ cả biến môi trường thử nghiệm

Dừng ứng dụng. Với PowerShell:

```powershell
$env:DEMO_MESSAGE = $null
.\gradlew.bat bootRun
```

Nếu không còn khai báo khác, nguồn thắng lúc này là tài nguyên `application.yml`. Xem `origin` để biết đúng tài nguyên và vị trí khai báo, thay vì chỉ đoán theo tên tệp đang mở trong IDE.

Trên macOS/Linux, chạy khi terminal không có `DEMO_MESSAGE` được export và không có tham số ghi đè:

```bash
./gradlew bootRun
```

Sau khi dừng ứng dụng và hoàn tất bài thực hành PowerShell, khôi phục biến ban đầu:

```powershell
$env:DEMO_MESSAGE = $previousDemoMessage
```

| Lần chạy | Khai báo đang có trong ví dụ | Nguồn dự kiến được chọn |
| --- | --- | --- |
| 1 | Tham số ứng dụng + biến môi trường + tệp | `commandLineArgs` |
| 2 | Biến môi trường + tệp | `systemEnvironment` |
| 3 | Tệp | Tài nguyên `application.yml` |

Điều kiện của bảng là không có profile, tệp ngoài, thuộc tính JVM hoặc nguồn tùy chỉnh khác ghi đè khóa đó. Nếu kết quả khác, chính sự khác biệt ấy là bằng chứng để tìm nguồn còn thiếu trong giả thuyết ban đầu.

### 5.4. Phân biệt tham số ứng dụng và thuộc tính JVM

Với một executable JAR đã được build và có tên `env-lab.jar`, cú pháp hai loại tham số là:

```text
java -Ddemo.message=from-jvm -jar env-lab.jar --demo.message=from-cli
```

`-Ddemo.message=...` đứng trước `-jar` để thiết lập thuộc tính của JVM. `--demo.message=...` đứng sau tên JAR để Spring Boot xử lý như tham số ứng dụng. Với cơ chế mặc định, tham số ứng dụng thắng trong tình huống này.

Không lấy `-D` truyền cho chính Gradle rồi mặc định rằng nó đã trở thành thuộc tính JVM của tiến trình ứng dụng do `bootRun` tạo ra. Khi chẩn đoán, kiểm tra tham số của đúng tiến trình Java và nhìn lại nguồn `systemProperties` trên endpoint.

Nếu ứng dụng chủ động tắt việc đưa tham số dòng lệnh vào `Environment` bằng `SpringApplication.setAddCommandLineProperties(false)`, kết quả sẽ khác. Vì vậy, quy tắc phải đi cùng điều kiện của cơ chế khởi động thực tế.

## 6. Phân biệt nguồn, vị trí và giá trị sử dụng trong mã

### 6.1. `source` cho biết lớp nguồn; `origin` giúp tìm chỗ cần sửa

Ví dụ, `systemEnvironment` cho biết cấu hình đến từ môi trường tiến trình; nó không tự cho biết biến được đặt ở IDE, script, unit dịch vụ hay cấu hình triển khai. Bước tiếp theo là kiểm tra cách tiến trình đó được khởi động.

Với tệp cấu hình, `origin` có thể chỉ đến classpath, tệp ngoài, cùng dòng và cột. Một tệp `application.yml` nằm ngoài JAR và một tệp cùng tên bên trong JAR là hai nguồn khác nhau. Sửa đúng tên nhưng sai vị trí vẫn có thể không đổi hành vi.

Không phải nguồn nào cũng hỗ trợ origin. Thiếu `origin` không chứng minh khóa không tồn tại; dùng `property.source` và các khai báo trong danh sách nguồn để tiếp tục truy vết.

### 6.2. Profile và vị trí nạp tệp ảnh hưởng tập nguồn

Khi `activeProfiles` không đúng dự kiến, hãy xác minh cấu hình kích hoạt profile và tài nguyên nào đã được nạp. Không chỉ nhìn thấy một tệp `application-prod.yml` trong repository rồi kết luận tiến trình đang dùng nó.

Trong cách nạp thông thường, tệp theo profile và tệp cấu hình ngoài JAR có thể ghi đè khai báo ở các tệp mặc định có ưu tiên thấp hơn. `spring.config.import`, location tùy chỉnh hoặc nhiều tài liệu cấu hình làm việc suy đoán bằng tên tệp càng kém chắc chắn.

Hãy dùng quy trình: **xem profile thực tế → tìm khóa → đọc nguồn thắng → đọc origin → kiểm tra nguồn triển khai tương ứng**. Danh sách nguồn đã được nạp là bằng chứng sát tiến trình hơn thứ tự các tệp trong IDE.

### 6.3. `env` chưa phải ảnh chụp mọi giá trị trong bean

`env` cung cấp bằng chứng về `Environment`; nó không chứng minh mọi đối tượng trong ứng dụng đang giữ giá trị giống hệt chuỗi được trả về.

- Một khai báo có thể chứa biểu thức giữ chỗ như `${demo.host}`. Khi cần, truy vấn cả khóa được tham chiếu để lần theo chuỗi phụ thuộc.
- Mã có thể dùng giá trị mặc định trong `@Value`, giá trị khởi tạo của trường hoặc logic dự phòng riêng; những giá trị đó không nhất thiết là một khóa đã được khai báo trong `Environment`.
- Bộ gắn cấu hình có thể chuyển chuỗi sang kiểu khác, chẳng hạn thời lượng. Bean cũng có thể đã giữ giá trị từ thời điểm khởi tạo.

Nếu cần kiểm tra dữ liệu đã gắn vào bean `@ConfigurationProperties`, endpoint `configprops` là bước chẩn đoán bổ sung phù hợp. Nó có cấu trúc riêng cho bean và đầu vào khi gắn cấu hình; xem [API `configprops` của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html). Không mở thêm endpoint này chỉ để thay thế việc xác định nguồn bằng `env`.

## 7. Giá trị bị che vẫn có thể dùng để truy vết nguồn

Trong Spring Boot 3.3, mặc định của `management.endpoint.env.show-values` là `never`: **mọi giá trị** đều bị che, không chỉ những khóa mang tên password hoặc secret. Dấu `******` không phải giá trị thật được bind vào ứng dụng.

| `show-values` | Ý nghĩa |
| --- | --- |
| `never` | Không hiện giá trị thật |
| `when-authorized` | Hiện cho người dùng được xác định là có quyền xem giá trị |
| `always` | Cho phép hiện cho mọi người đã truy cập được endpoint, nếu không có hàm che dữ liệu tùy chỉnh tiếp tục áp dụng |

Với HTTP, `when-authorized` còn liên quan đến trạng thái xác thực và các vai trò cấu hình tại `management.endpoint.env.roles`. Khi không cấu hình vai trò cụ thể, người dùng đã xác thực được xem là có quyền xem giá trị theo cơ chế mặc định này. Điều đó không thay thế quy tắc bảo vệ URL trong Spring Security. Cơ chế này được mô tả trong [quy tắc che dữ liệu của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization).

Ưu tiên xác định nguồn khi dữ liệu vẫn được che. Nếu thật sự cần nhìn giá trị trong **ứng dụng thực hành riêng trên máy cá nhân, không chứa bí mật**, có thể chạy một lượt với:

```powershell
.\gradlew.bat bootRun --args="--demo.message=from-cli --management.endpoint.env.show-values=always"
```

Trong lượt này, các giá trị không bị che bởi cơ chế tùy chỉnh sẽ hiện ra. Việc cho hiện áp dụng cho endpoint `env`, không chỉ riêng `demo.message`. Sau khi dừng và chạy lại không có tham số này, cấu hình `never` trong tệp lại có hiệu lực nếu không còn nguồn khác ghi đè.

Không lưu đầu ra toàn bộ `env` vào log, ticket hoặc tài liệu chia sẻ khi chưa kiểm tra nội dung. Ngay cả khi các giá trị bị che, tên khóa, đường dẫn và origin vẫn có thể tiết lộ cấu trúc triển khai.

## 8. Quy trình chẩn đoán một cấu hình sai

1. **Xác định đúng instance và khóa.** Với nhiều replica, bảo đảm yêu cầu đến tiến trình cần điều tra; tránh so sánh hai instance như một.
2. **Gọi endpoint cho một khóa.** Đọc `property.source` trước khi sửa bất kỳ tệp nào.
3. **Duyệt các nguồn cùng cung cấp khóa.** Đối chiếu thứ tự ưu tiên; phân biệt nguồn thắng với những khai báo bị ghi đè.
4. **Theo origin hoặc cách khởi động.** Nguồn từ tệp thì tìm đúng tệp; nguồn môi trường/JVM/CLI thì kiểm tra cách truyền cấu hình cho tiến trình.
5. **Đối chiếu profile và giá trị đã bind khi cần.** Một nguồn đúng chưa đủ giải thích mọi xử lý trong bean.
6. **Thay đổi đúng nguồn theo cơ chế triển khai rồi kiểm tra lại.** Với ví dụ thông thường, khởi động lại ứng dụng; không mặc định rằng sửa tệp sẽ làm mọi bean tự cập nhật.

Endpoint `env` tích hợp của Spring Boot 3.3 phục vụ thao tác đọc. Không suy ra có API `POST /actuator/env` để sửa cấu hình hoặc có cơ chế tự làm mới bean; các thư viện bổ sung nếu có phải được đánh giá theo hợp đồng riêng.

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| HTTP `404` ở URL mong đợi | Kiểm tra cổng quản trị, base path/context path, enablement và HTTP exposure |
| HTTP `401` hoặc `403` | Kiểm tra xác thực, quyền truy cập và lớp trung gian |
| HTTP `200`, giá trị là `******` | Kiểm tra `show-values`; tiếp tục dùng thông tin nguồn trước khi cần xem giá trị |
| Sửa `application.yml` nhưng giá trị không đổi | Tìm khóa trong nguồn cao hơn và xác minh đúng tệp/origin |
| Không thấy khóa trong danh sách toàn bộ như dự kiến | Kiểm tra profile, tài nguyên đã nạp và hình thức tên; thử truy vấn trực tiếp khóa |
| `env` đúng nhưng hành vi ứng dụng vẫn khác | Kiểm tra binding, chuyển kiểu, giá trị mặc định, dữ liệu đã giữ trong bean và đúng instance |

Mã HTTP có thể chịu ảnh hưởng của bảo mật hoặc proxy tùy ứng dụng; bảng là hướng điều tra, không phải phép suy luận duy nhất từ một mã lỗi.

## 9. Bài tập tự kiểm tra

Thực hiện ba lần chạy ở phần 5 và ghi lại cho mỗi lần: nguồn thắng, những nguồn còn khai báo khóa, origin nếu có và trạng thái che giá trị. Sau đó trả lời:

- Vì sao đổi tệp ở lần chạy 1 không làm mất `commandLineArgs`?
- Vì sao đọc `propertySources[0]` mà không kiểm tra khóa có thể dẫn đến kết luận sai?
- Khi `value` đều là `******`, bằng chứng nào vẫn chỉ ra nguồn cần sửa?
- Nếu `origin` chỉ đến tệp ngoài JAR, vì sao sửa bản cùng tên trong mã nguồn có thể chưa có tác dụng?
- Vì sao một giá trị đã xuất hiện đúng trong `env` chưa đủ chứng minh mọi bean đã được cập nhật?

Kết quả cần đạt là truy được đường đi **khóa cần điều tra → nguồn được chọn → vị trí hoặc cách truyền cấu hình → kiểm chứng lại trên đúng tiến trình**.
