# Sử dụng ký tự * trong cấu hình và quy tắc đặt dấu nháy trong YAML

## 1. Một ký tự, hai lớp xử lý

Khi muốn công bố toàn bộ endpoint Actuator đủ điều kiện qua HTTP, ta có thể dùng ký tự đại diện `*`. Tuy nhiên, cùng ký tự đó có ý nghĩa đặc biệt trong cú pháp YAML. Cấu hình phải được YAML đọc thành dữ liệu hợp lệ trước khi Actuator có cơ hội hiểu nó.

Cách viết thông dụng trong `application.yml` là:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Ở đây, dấu nháy giúp YAML tạo ra một giá trị chuỗi chứa đúng một ký tự `*`. Sau đó, cơ chế công bố endpoint của Actuator hiểu giá trị đó là chọn tất cả. Dấu nháy không biến `*` thành một tên endpoint thông thường và cũng không làm mất ý nghĩa chọn tất cả của Actuator.

Ngược lại, đoạn sau là ví dụ **sai cú pháp cho mục đích này**:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: *
```

Ứng dụng có thể thất bại ngay khi đọc YAML. Đây chưa phải tình huống endpoint bị thiếu quyền truy cập hoặc chưa được chọn để công bố.

Spring Boot hướng dẫn đặt dấu sao trong dấu nháy khi dùng YAML cho danh sách include/exclude. [Tài liệu công bố endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 2. Vì sao YAML cần dấu nháy?

Trong YAML, `*` có thể mở đầu một tham chiếu (alias) tới nút đã được đặt tên bằng điểm neo (anchor). Cặp ký hiệu này phục vụ việc tham chiếu dữ liệu trong tài liệu YAML; chúng không do Spring Boot tạo ra.

Vì vậy, khi gặp `include: *`, bộ đọc không mặc nhiên coi đây là một chuỗi chứa dấu sao. Nó bắt đầu xử lý cú pháp alias nhưng không nhận được tên hợp lệ. Với bộ đọc SnakeYAML 2.2 dùng trong thí nghiệm Boot 3.3.0, trường hợp này bị từ chối bằng lỗi thuộc nhóm `ScannerException`.

Để yêu cầu một chuỗi thông thường, dùng nháy đơn hoặc nháy kép:

```yaml
include: '*'
```

```yaml
include: "*"
```

Hai đoạn ngắn này là các cách thay thế cho giá trị `include` bên dưới nhánh `management.endpoints.web.exposure`; chúng không phải cấu hình đầy đủ cho một ứng dụng.

Cả hai cho cùng dữ liệu sau khi đọc: chuỗi `*`, có độ dài một ký tự. Dấu nháy là cú pháp bao chuỗi, không phải một phần của giá trị. [Ký tự chỉ thị, alias và kiểu chuỗi trong đặc tả YAML 1.2.2](https://yaml.org/spec/1.2.2/).

### 2.1. Không cần thêm dấu escape trước dấu sao

Viết trực tiếp `"*"` đã đủ. Không cần biến nó thành `"\*"`.

Đoạn dưới đây là ví dụ **sai**:

```yaml
include: "\*"
```

Trong kiểm tra bằng SnakeYAML 2.2, bộ đọc từ chối cách viết này vì `\*` không phải chuỗi escape được chấp nhận trong chuỗi nháy kép. Việc thêm dấu gạch chéo ngược không phải cách sửa lỗi alias.

Dùng nháy thẳng ASCII `'` hoặc `"` khi nhập cấu hình. Dấu nháy trang trí do trình soạn thảo văn bản thay thế không phải ký hiệu bao chuỗi YAML tương ứng.

### 2.2. Không suy ra rằng mọi chuỗi có dấu sao đều là wildcard hợp lệ

Đoạn này có thể được YAML đọc thành chuỗi:

```yaml
include: "health*"
```

Nhưng qua được bước đọc YAML không có nghĩa là Actuator hỗ trợ mẫu tên `health*`. Trong Boot 3.3.0, giá trị trên bị từ chối khi kiểm tra ID endpoint. Giá trị đặc biệt cần dùng để chọn tất cả là toàn bộ chuỗi `*`, không phải một cơ chế ghép mẫu tiền tố/hậu tố tùy ý.

Đây là hai loại lỗi khác nhau:

| Ví dụ | Lớp phát hiện vấn đề trong thí nghiệm | Cách sửa theo mục đích |
| --- | --- | --- |
| `include: *` | Bộ đọc YAML | Nếu cần chọn tất cả, viết `include: "*"` |
| `include: "\*"` | Bộ đọc YAML | Bỏ dấu gạch chéo ngược, giữ dấu nháy |
| `include: "health*"` | Kiểm tra ID của Actuator sau khi YAML đã đọc được | Dùng ID cụ thể như `health` hoặc dùng riêng `"*"` |

## 3. Viết dấu sao trong các dạng danh sách YAML

Thuộc tính công bố chấp nhận danh sách ID. Có thể biểu diễn một phần tử dấu sao bằng chuỗi hoặc bằng danh sách một phần tử.

### 3.1. Chuỗi đơn

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops"
```

Trong cấu hình này, include chọn tất cả, còn exclude loại `env` và `configprops`. Chuỗi chứa các ID phân tách bằng dấu phẩy được Spring Boot chuyển thành tập giá trị tương ứng.

### 3.2. Danh sách theo từng dòng

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
        exclude:
          - env
          - configprops
```

Việc dấu sao nằm sau dấu `-` không loại bỏ yêu cầu đặt nháy. Phần tử `- "*"` là chuỗi hợp lệ; viết `- *` vẫn làm bộ đọc xử lý ký hiệu alias không hoàn chỉnh.

### 3.3. Danh sách trên một dòng

```yaml
management:
  endpoints:
    web:
      exposure:
        include: ["*"]
        exclude: [env, configprops]
```

`["*"]` là một danh sách có một chuỗi dấu sao. `[*]` không phải cách viết thay thế hợp lệ cho mục đích này. Trong kiểm tra bằng SnakeYAML 2.2, `include: [*]` cũng bị từ chối khi đọc YAML.

Các dạng hợp lệ trên có cùng ý định lựa chọn endpoint. Dùng một dạng nhất quán trong tệp để người đọc dễ kiểm tra; không chép nhiều khối `management` trùng nhau vào cùng một tài liệu để kết hợp các ví dụ.

## 4. Giá trị * được Actuator hiểu như thế nào?

Sau khi YAML đọc và Spring Boot chuyển dữ liệu vào cấu hình, dấu sao mới tham gia vào quy tắc công bố HTTP.

```text
Tệp YAML
  → đọc cú pháp và tạo dữ liệu
  → chuyển dữ liệu vào thuộc tính include/exclude
  → Actuator chọn hoặc loại endpoint
  → yêu cầu HTTP còn chịu đường dẫn và chính sách truy cập
```

### 4.1. include có dấu sao: chọn tất cả endpoint đủ điều kiện

`include: "*"` chọn tất cả trong phạm vi cơ chế công bố endpoint, nhưng không tự tạo endpoint đang thiếu thư viện hoặc điều kiện cần thiết. Nó cũng không bật lại endpoint đã bị tắt.

Ví dụ:

```yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: "*"
```

`info` vẫn bị tắt. Tương tự, ứng dụng không có thư viện cung cấp endpoint Prometheus thì không xuất hiện `/actuator/prometheus` chỉ nhờ dấu sao.

### 4.2. exclude có dấu sao: loại toàn bộ endpoint khỏi HTTP

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "*"
```

Exclude được ưu tiên, nên cấu hình này không công bố endpoint Actuator nào qua HTTP. Không thể dùng include để “thắng lại” dấu sao trong exclude.

Cũng có thể chỉ đặt `exclude: "*"` để loại toàn bộ endpoint khỏi kênh HTTP. Điều đó không đồng nghĩa dừng máy chủ web hoặc xóa các controller nghiệp vụ.

### 4.3. Đánh giá phạm vi sau khi dùng dấu sao

Giả sử hôm nay ứng dụng có một tập endpoint, rồi ngày mai bổ sung thư viện hoặc một endpoint quản trị tự viết. Nếu cấu hình chọn tất cả, endpoint mới đủ điều kiện có thể được đưa vào giao diện HTTP mà không cần thêm ID vào tệp cấu hình.

Vì vậy, dấu sao thuận tiện cho thí nghiệm hoặc môi trường đã xác định rõ phạm vi quản trị; còn một danh sách tường minh giúp việc rà soát chỉ ra trực tiếp các khả năng được chọn. Dấu nháy chỉ giải quyết cú pháp YAML, không cung cấp xác thực, phân quyền hay giới hạn kết nối mạng.

## 5. Phân biệt chuỗi dấu sao với alias YAML

Ví dụ sau dùng một alias **có chủ đích**:

```yaml
chosen: &ids "health,info"

management:
  endpoints:
    web:
      exposure:
        include: *ids
        exclude: env
```

Trong cùng tài liệu, `&ids` đặt tên cho giá trị `health,info`; `*ids` tham chiếu lại giá trị đó. Kết quả include được chuyển thành hai ID `health` và `info`. Nó không mang ý nghĩa chọn tất cả.

Nếu không có điểm neo tên `missing`, đoạn `include: *missing` bị bộ đọc từ chối vì tham chiếu chưa được định nghĩa. Đây là lỗi YAML, không phải thông báo rằng Actuator thiếu một endpoint tên `missing`.

Ví dụ alias giúp nhận biết vì sao ký tự `*` có ý nghĩa cú pháp. Với một giá trị chọn tất cả đơn giản, viết trực tiếp `include: "*"` thường dễ đọc hơn việc tạo điểm neo.

## 6. Không sao chép nguyên quy tắc dấu nháy sang properties hoặc dòng lệnh

### 6.1. Tệp application.properties

Cách viết để chọn tất cả trong properties là:

```properties
management.endpoints.web.exposure.include=*
management.endpoints.web.exposure.exclude=env,configprops
```

Tệp properties không xử lý nháy đơn/nháy kép như cú pháp bao chuỗi của YAML. Nếu viết:

```properties
management.endpoints.web.exposure.include="*"
```

thì dấu nháy trở thành một phần của giá trị cấu hình. Trong kiểm tra Boot 3.3.0, giá trị có cả dấu nháy này bị từ chối khi kiểm tra ID endpoint.

| Nơi viết cấu hình | Ví dụ phù hợp | Giá trị mong muốn sau khi đọc |
| --- | --- | --- |
| YAML, dạng chuỗi nháy kép | `include: "*"` | `*` |
| YAML, dạng chuỗi nháy đơn | `include: '*'` | `*` |
| Properties | `management.endpoints.web.exposure.include=*` | `*` |

Vì vậy, khi chuyển cấu hình giữa hai định dạng, phải chuyển cả cú pháp biểu diễn, không chỉ đổi phần mở rộng tên tệp.

### 6.2. Dấu nháy của shell là một lớp khác

Khi chạy một lệnh có tham số `--management.endpoints.web.exposure.include=*`, shell xử lý cú pháp dòng lệnh trước khi Java nhận tham số. Dấu nháy dùng để bao đối số dòng lệnh thuộc quy tắc của shell, không phải dấu nháy trong tệp YAML.

Mục tiêu cuối cùng vẫn là giá trị thuộc tính chứa đúng ký tự `*`, không có dấu nháy hay dấu gạch chéo ngược ngoài ý muốn. Không áp dụng máy móc cách viết trong tệp properties cho một chuỗi được bọc thêm bởi shell, JSON hoặc công cụ triển khai.

## 7. Thực nghiệm bằng ứng dụng Spring Boot nhỏ

Dự án sau dùng Java 21, Gradle 8.5 và Boot 3.3.0. Lần xây dựng đầu cần tải plugin và thư viện. Ứng dụng không thêm Spring Security, chỉ lắng nghe trên loopback để quan sát cấu hình công bố HTTP trên máy cá nhân.

### 7.1. Các tệp cần tạo

```text
actuator-wildcard-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/wildcard/WildcardApplication.java
    └── resources/application.yml
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'actuator-wildcard-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'actuator-wildcard-demo.jar'
}
```

Tệp `src/main/java/lab/wildcard/WildcardApplication.java`:

```java
package lab.wildcard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WildcardApplication {
    public static void main(String[] args) {
        SpringApplication.run(WildcardApplication.class, args);
    }
}
```

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
```

Với thí nghiệm này, chỉ tạo một tệp cấu hình ứng dụng như trên để tránh nguồn khác làm thay đổi include/exclude. Spring Boot còn hỗ trợ nguồn cấu hình ngoài tệp; khi kết quả khác dự kiến, cần kiểm tra nguồn có ưu tiên cao hơn. [Cơ chế cấu hình ngoài của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 7.2. Chạy cấu hình hợp lệ

Tại thư mục chứa `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-wildcard-demo.jar
```

Giữ cửa sổ chạy Java hoạt động, mở cửa sổ khác và gọi:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/env
```

Trên PowerShell Windows, dùng `curl.exe` nếu `curl` là một bí danh.

| Yêu cầu trong ứng dụng mẫu | Mã HTTP dự kiến | Lý do |
| --- | --- | --- |
| GET `/actuator/health` | 200 | Được dấu sao chọn, không bị loại |
| GET `/actuator/info` | 200 | Được dấu sao chọn, không bị loại |
| GET `/actuator/metrics` | 200 | Được dấu sao chọn, không bị loại |
| GET `/actuator/env` | 404 | Bị exclude loại |

Không cần giả định toàn bộ JSON số liệu hoặc các header giống nhau giữa các máy. Mục tiêu ở đây là kiểm tra lựa chọn endpoint.

### 7.3. Thay đổi từng trường hợp

Mỗi lần thử: dừng tiến trình bằng Ctrl+C, sửa YAML, chạy lại `gradle bootJar`, rồi khởi động lại JAR. Tệp đang nằm trong JAR không tự thay đổi theo tệp nguồn vừa sửa.

| Thay đổi trong cấu hình mẫu | Kết quả cần quan sát |
| --- | --- |
| Đổi `include: "*"` thành `include: '*'` | Cùng giá trị dấu sao, các kết quả HTTP trên không đổi |
| Đổi thành `include: ["*"]` | Danh sách một phần tử vẫn chọn tất cả |
| Đổi thành `include: *` | Thất bại khi đọc YAML; chưa thể kiểm tra HTTP của lần khởi động này |
| Đổi thành `include: "\*"` | Thất bại khi đọc chuỗi escape |
| Giữ include có dấu sao, đổi exclude thành `"*"` | Các endpoint Actuator trên không còn được công bố qua HTTP |
| Đổi include thành `"health*"` | YAML đọc được nhưng Actuator từ chối ID không hợp lệ trong Boot 3.3.0 |

Khi chủ đích thử cấu hình sai, cần dừng bản chạy hợp lệ trước. Nếu tiến trình cũ vẫn phục vụ cổng 8080, phản hồi từ nó không chứng minh cấu hình mới đã khởi động thành công.

## 8. Nhận diện đúng lớp gây lỗi

| Dấu hiệu | Cần kiểm tra trước |
| --- | --- |
| Không khởi động được; thông báo liên quan quét alias, alias chưa định nghĩa hoặc escape YAML | Dấu nháy, ký tự sau `*`, cấu trúc YAML của đúng tệp được báo |
| YAML đã đọc được, nhưng lỗi ID endpoint hoặc cấu hình công bố | Giá trị thực tế: dấu nháy bị giữ trong properties, mẫu `health*` hoặc ký tự thừa |
| Ứng dụng chạy nhưng một endpoint trả 404 | Endpoint có đủ điều kiện, có bị tắt hoặc bị exclude không; đồng thời kiểm tra địa chỉ và đường dẫn |
| Ứng dụng có bảo mật trả 401/403 | Chính sách xác thực/phân quyền, thay vì chỉ đổi dấu nháy |
| Sửa cấu hình nhưng kết quả vẫn như cũ | JAR đang chạy, lần xây dựng, profile và các nguồn cấu hình ghi đè |

Chỉ sửa dấu nháy khi vấn đề thuộc cách biểu diễn giá trị. Việc thêm dấu nháy vào một ID không hợp lệ không thể sửa hợp đồng của ID; việc dùng dấu sao cũng không giải quyết lỗi quyền truy cập.

## 9. Tự kiểm tra

**Câu 1.** Vì sao `include: "*"` đúng nhưng `include: *` không phù hợp để chọn tất cả?

**Đáp án:** Nháy kép yêu cầu YAML tạo chuỗi chứa dấu sao. Dấu sao không có nháy ở vị trí đó bắt đầu cú pháp alias; bộ đọc không tạo được giá trị wildcard mong muốn.

**Câu 2.** Sau khi đọc `include: '*'`, Actuator nhận một hay ba ký tự?

**Đáp án:** Một ký tự `*`. Hai dấu nháy đơn là cú pháp bao chuỗi của YAML, không thuộc dữ liệu.

**Câu 3.** Viết `include: [*]` có tránh được lỗi vì đã dùng danh sách không?

**Đáp án:** Không. Phần tử dấu sao vẫn cần được biểu diễn thành chuỗi, chẳng hạn `["*"]`.

**Câu 4.** `include: "*"` và `exclude: "*"` công bố endpoint nào?

**Đáp án:** Không endpoint Actuator nào qua HTTP trong cơ chế công bố chuẩn, vì exclude thắng.

**Câu 5.** `include: *ids` luôn có nghĩa là chọn tất cả phải không?

**Đáp án:** Không. Đó là cú pháp alias. Kết quả phụ thuộc giá trị đã được đặt tên bằng `&ids`; nếu điểm neo chưa được định nghĩa thì YAML không đọc được.

**Câu 6.** Chuyển `include: "*"` từ YAML sang properties có nên giữ nguyên hai dấu nháy không?

**Đáp án:** Không. Trong properties, dùng `management.endpoints.web.exposure.include=*` để giá trị chỉ chứa dấu sao.
