# Lựa chọn một định dạng và xử lý trường hợp `.properties` cùng tồn tại với YAML

## 1. Vấn đề cần giải quyết

Trong Spring Boot 3.3, cùng một ứng dụng có thể cấu hình bằng tệp `application.properties` hoặc `application.yaml`/`application.yml`. Cả hai cách đều nhằm tạo các thuộc tính để Spring Boot sử dụng, ví dụ `server.port`, `spring.application.name` hay `app.payment.timeout`.

Khi dự án bắt đầu, nhóm phát triển thường chỉ cần chọn một định dạng. Sau vài lần bổ sung tính năng hoặc nâng cấp dự án, có thể xuất hiện cả hai định dạng trong cùng thư mục. Khi ấy có ba câu hỏi quan trọng:

1. Khi nào nên chọn `.properties`, khi nào nên chọn YAML?
2. Nếu cả hai tệp cùng khai báo một khóa, Spring Boot dùng giá trị nào?
3. Khi cấu hình theo profile, cấu hình ngoài JAR hoặc biến môi trường tham gia, làm sao biết chắc giá trị cuối cùng?

Mục tiêu của bài là đưa ra tiêu chí chọn định dạng, giải thích quy tắc nạp cấu hình trong **Spring Boot 3.3**, rồi thực hành xác định giá trị có hiệu lực. Để theo dõi, bạn chỉ cần hiểu cặp khóa–giá trị, cấu trúc thư mục, Java 17 và cách khởi động một ứng dụng Spring Boot.

**Nguyên tắc làm việc:** ưu tiên **một định dạng chính cho cấu hình ứng dụng**. Nếu tạm thời phải dùng cả hai, hãy quản lý rõ tệp nào chứa khóa nào và kiểm tra thứ tự ưu tiên thực tế. Việc có nhiều định dạng không tự động gây lỗi, nhưng các khóa trùng lặp dễ làm người đọc nhầm về nguồn gốc giá trị.

## 2. `.properties` và YAML biểu diễn cùng một cấu hình ra sao?

### 2.1. `.properties`: một khóa trên một dòng

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=order-service
server.port=8080

app.payment.enabled=true
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=3s
app.payment.max-retries=4
```

Mỗi dòng có dạng `key=value`; có thể dùng dấu `:` làm dấu phân cách theo cú pháp Java properties, nhưng dấu `=` thường dễ đọc hơn. Dấu chấm giúp biểu diễn nhóm khóa lồng nhau theo cách phẳng. Trong ví dụ, các khóa bắt đầu bằng `app.payment` cùng mô tả một chức năng.

Đây là lựa chọn gọn khi tập cấu hình không quá nhiều tầng và khi cần nhìn nhanh từng khóa độc lập. Hầu hết các công cụ chỉnh sửa văn bản, script và hệ thống triển khai đều thao tác thuận tiện với các cặp khóa–giá trị.

### 2.2. YAML: cấu trúc phân cấp theo thụt lề

Tệp `src/main/resources/application.yaml` có thể biểu diễn cùng dữ liệu:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  payment:
    enabled: true
    endpoint: https://payments.example.test
    connect-timeout: 3s
    max-retries: 4
```

Spring Boot chuyển cấu trúc YAML thành những khóa phẳng có thể tra cứu trong `Environment`. Chẳng hạn:

```text
app.payment.enabled=true
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=3s
app.payment.max-retries=4
```

Do đó, **tầng của YAML là cách trình bày**, không tạo ra một bộ API cấu hình riêng. Bean nhận cấu hình sẽ sử dụng các khóa logic tương ứng với cách dùng `.properties`.

Spring Boot hỗ trợ YAML thông qua thư viện SnakeYAML. Trong ứng dụng Spring Boot thông thường sử dụng các starter chính thức, thư viện cần thiết được cung cấp sẵn theo phụ thuộc. Nếu tự tùy chỉnh classpath, cần bảo đảm bộ nạp YAML khả dụng.

### 2.3. Ví dụ với danh sách

`.properties`:

```properties
app.notification.recipients[0]=ops@example.test
app.notification.recipients[1]=support@example.test
```

YAML:

```yaml
app:
  notification:
    recipients:
      - ops@example.test
      - support@example.test
```

Cả hai có thể liên kết vào `List<String> recipients`. Khi cấu hình danh sách bị ghi đè từ một nguồn ưu tiên cao hơn, không nên mặc định các phần tử sẽ được ghép từng vị trí giữa nhiều nguồn. Với cơ chế liên kết danh sách của Spring Boot, nguồn ưu tiên cao hơn thường **thay toàn bộ danh sách**; tình huống này đặc biệt quan trọng khi tệp chung và tệp profile cùng đặt danh sách.

### 2.4. Khác biệt cú pháp dễ gây lỗi

| Tình huống | Trong `.properties` | Trong YAML |
| --- | --- | --- |
| Quan hệ nhóm khóa | Viết rõ `app.payment.timeout=3s` | Dùng các mức thụt lề bên dưới `app` và `payment` |
| Danh sách | Chỉ số `[0]`, `[1]` hoặc cách biểu diễn được binder hỗ trợ | Dùng `-` trong danh sách |
| Chú thích | Dòng bắt đầu bằng `#` hoặc `!` | `#` mở đầu chú thích khi nằm ở vị trí cú pháp phù hợp |
| Giá trị có `:` hoặc `#` | Chú ý cú pháp tệp properties và ký tự thoát | Nên đặt giá trị trong dấu nháy nếu có khả năng bị hiểu thành cú pháp |
| Chuỗi trông giống số/bool | Chủ yếu được xử lý như văn bản lúc đọc thuộc tính | YAML có kiểu vô hướng; nên dùng dấu nháy khi cần giữ nguyên dạng chuỗi |
| Dấu nháy | Dấu `"` không mặc nhiên được bỏ đi như trong YAML | Dấu nháy là một phần của cú pháp biểu diễn chuỗi và thường không thuộc giá trị kết quả |
| Sai thụt lề | Không áp dụng | Có thể đổi cấu trúc hoặc làm YAML không đọc được |

Ví dụ, nếu định danh cần giữ số `0` ở đầu, hãy thể hiện rõ nó là chuỗi trong YAML:

```yaml
app:
  branch-code: "0012"
```

Khi đọc YAML, **dùng dấu cách để thụt lề; không dùng tab**. Đặc biệt cẩn thận với chuỗi chứa ký tự đặc biệt, giá trị bắt đầu bằng `{`, `[`, `*`, `&` hoặc chuỗi dễ bị nhầm với kiểu dữ liệu. Nên thống nhất cách đặt khóa bằng chữ thường và dấu gạch nối, chẳng hạn `connect-timeout`, trong cả hai định dạng.

## 3. Chọn định dạng theo nhu cầu thực tế

Không có định dạng nào luôn tốt hơn trong mọi dự án. Hãy chọn dựa vào cấu hình thực tế, người bảo trì và công cụ đang dùng.

| Tiêu chí | Thường hợp phù hợp `.properties` | Thường hợp phù hợp YAML |
| --- | --- | --- |
| Số lượng khóa ít, tương đối phẳng | Rất gọn, mỗi khóa trên một dòng | Có thể dài hơn do cấu trúc lồng |
| Nhiều nhóm khóa có quan hệ cha–con | Lặp lại tiền tố nhưng dễ tìm nguyên khóa | Dễ nhìn quan hệ phân cấp và nhóm chức năng |
| Danh sách, nhóm đối tượng lồng nhau | Có thể viết bằng chỉ số hoặc quy ước binder | Cú pháp danh sách và đối tượng tự nhiên hơn |
| Script thao tác từng khóa | Dễ xử lý trong hệ thống quen với file properties | Cần công cụ biết cấu trúc YAML để chỉnh sửa an toàn |
| Đọc diff trong pull request | Thay đổi một khóa thường là một dòng | Thay đổi thụt lề hoặc sắp xếp có thể ảnh hưởng khối |
| Quy ước của đội ngũ | Phù hợp nếu dự án đã dùng properties | Phù hợp nếu dự án đã dùng YAML và có kiểm tra cú pháp |

Một lựa chọn hợp lý:

- **Dự án nhỏ hoặc cấu hình phẳng:** có thể chọn `application.properties`.
- **Dự án có nhiều nhóm cấu hình và danh sách:** có thể chọn `application.yaml`.
- **Dự án đang có một định dạng ổn định:** thường nên giữ quy ước hiện có thay vì đổi định dạng chỉ vì sở thích.
- **Dự án dùng cả hai do chuyển đổi từng phần:** cần quy tắc rõ về nơi khai báo khóa, các cấu hình ngoại lệ và cách kiểm tra xung đột.

`.yml` và `.yaml` đều là đuôi YAML được Spring Boot hỗ trợ. Để người khác dễ đoán vị trí cấu hình, hãy thống nhất **một cách đặt tên** trong dự án; không nên tạo cả `application.yml` và `application.yaml` cùng chỗ rồi phụ thuộc vào thứ tự xử lý giữa chúng.

## 4. Spring Boot 3.3 đọc tệp nào và theo thứ tự nào?

Khi ứng dụng khởi động, Spring Boot thu thập các nguồn cấu hình thành những `PropertySource` trong `Environment`. **Nguồn ưu tiên cao hơn quyết định giá trị của khóa trùng tên.** Các khóa chỉ có ở một nguồn vẫn có thể được sử dụng.

Có hai tầng quy tắc cần tách riêng:

1. **Quy tắc chọn giữa `.properties` và YAML ở cùng vị trí.**
2. **Quy tắc ưu tiên tổng thể giữa các vị trí, profile và nguồn khác.**

Không nên rút gọn mọi trường hợp thành câu “properties luôn thắng YAML”.

### 4.1. Hai định dạng cùng vị trí: `.properties` được ưu tiên

Tài liệu chính thức của **Spring Boot 3.3** khuyến nghị dùng một định dạng xuyên suốt ứng dụng và nêu rõ: nếu có cả tệp `.properties` và YAML ở **cùng một vị trí**, `.properties` được ưu tiên.

Ví dụ hai tệp cùng ở `src/main/resources/`:

`application.properties`:

```properties
app.ui.title=Tiêu đề từ properties
app.ui.page-size=25
```

`application.yaml`:

```yaml
app:
  ui:
    title: Tiêu đề từ YAML
    accent-color: blue
```

Khi không có profile hay nguồn ưu tiên cao hơn ghi đè các khóa này, kết quả dự kiến:

| Khóa | Giá trị có hiệu lực | Lý do |
| --- | --- | --- |
| `app.ui.title` | `Tiêu đề từ properties` | Có ở cả hai tệp trong cùng vị trí; `.properties` ưu tiên |
| `app.ui.page-size` | `25` | Chỉ có trong `.properties` |
| `app.ui.accent-color` | `blue` | Chỉ có trong YAML |

Đây là ví dụ về **ghi đè theo từng khóa**, không có nghĩa toàn bộ YAML bị bỏ qua chỉ vì tồn tại tệp properties.

### 4.2. Tệp theo profile có thể thắng tệp chung

Giả sử thêm:

`application-dev.yaml`:

```yaml
app:
  ui:
    title: Tiêu đề cho môi trường dev
    accent-color: orange
```

Nếu profile `dev` đang hoạt động và không có nguồn ưu tiên cao hơn, `app.ui.title` từ **tệp profile** có thể ghi đè khóa trong `application.properties` chung. Quy tắc ưu tiên của tệp theo profile cần được xét trước khi đưa ra kết luận cuối.

Ví dụ khởi động:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Trong cùng một vị trí:

- `application.properties` và `application.yaml` là hai tệp **chung**; với khóa trùng nhau, `.properties` ưu tiên.
- `application-dev.properties` và `application-dev.yaml` là hai tệp **riêng của profile dev**; với khóa trùng nhau ở cùng vị trí, `.properties` ưu tiên.
- Một tệp `application-dev.yaml` đang hoạt động có thể ghi đè giá trị từ tệp **chung** `application.properties`, vì độ ưu tiên của tệp profile được xét trong quá trình nạp config data.

Nếu không bật `dev`, tệp `application-dev.yaml` không trở thành nguồn cấu hình theo profile hoạt động chỉ vì nó hiện diện trong dự án.

### 4.3. Tệp ngoài JAR có thể thắng tệp đóng gói trong JAR

Spring Boot kiểm tra các vị trí cấu hình mặc định, bao gồm vị trí classpath và một số vị trí bên ngoài ứng dụng như thư mục làm việc và thư mục `config/` của nó.

Ở mức khái quát cho config data mặc định, nhóm ưu tiên tăng dần:

```text
Tệp ứng dụng chung bên trong JAR
          <
Tệp profile bên trong JAR
          <
Tệp ứng dụng chung bên ngoài JAR
          <
Tệp profile bên ngoài JAR
```

Điều này có nghĩa là `./config/application.yaml` được cung cấp khi triển khai có thể ghi đè một khóa từ `application.properties` đóng gói trong JAR, dù tệp ngoài là YAML và tệp trong là properties. **Vị trí và profile cũng góp phần quyết định ưu tiên.**

Tài liệu chính thức còn hỗ trợ tùy chỉnh vị trí và nhóm vị trí; khi dự án tự thiết lập `spring.config.location` hoặc `spring.config.additional-location`, hãy xem cấu hình thực tế thay vì áp dụng máy móc sơ đồ mặc định.

### 4.4. Biến môi trường và đối số khởi động có thể ghi đè tệp

Chẳng hạn:

```bash
java -jar app.jar --app.ui.title="Từ dòng lệnh"
```

Với cấu hình khởi động thông thường, đối số dòng lệnh này có ưu tiên cao hơn các tệp cấu hình đã nêu. Biến môi trường như `APP_UI_TITLE` cũng có thể ghi đè giá trị trong tệp.

Không nên cho rằng đổi `.yaml` thành `.properties` sẽ làm tệp đó thắng đối số dòng lệnh, biến môi trường hoặc các nguồn cấu hình khác. **Ưu tiên định dạng cùng vị trí chỉ là một phần của toàn bộ cơ chế.**

## 5. Bảng tình huống: tệp nào thực sự thắng?

Giả sử mọi ví dụ sau dùng cùng khóa `app.ui.title`, không có nguồn nào khác ghi đè và chỉ kích hoạt profile được ghi rõ.

| Tình huống | Nguồn thắng với khóa trùng | Giải thích |
| --- | --- | --- |
| `application.properties` và `application.yaml` cùng trong `src/main/resources` | `application.properties` | `.properties` ưu tiên YAML cùng vị trí, cùng mức tệp chung |
| `application-dev.properties` và `application-dev.yaml` cùng vị trí, bật `dev` | `application-dev.properties` | Cùng mức profile; `.properties` ưu tiên |
| `application.properties` và `application-dev.yaml` cùng vị trí, bật `dev` | `application-dev.yaml` | Tệp profile ưu tiên hơn tệp chung trong trường hợp này |
| `application.properties` trong JAR, `./config/application.yaml` bên ngoài | YAML bên ngoài | Vị trí cấu hình bên ngoài có ưu tiên cao hơn vị trí đóng gói theo quy tắc mặc định |
| Tệp cấu hình có `app.ui.title=A`, chạy với `--app.ui.title=B` | Đối số dòng lệnh `B` | Đối số ứng dụng có độ ưu tiên cao hơn các tệp config data |
| Tệp chứa `app.ui.title=A`, biến môi trường đặt `APP_UI_TITLE=B` | Biến môi trường `B` | Biến môi trường có thể ghi đè giá trị tệp |
| Chỉ YAML có `app.ui.accent-color=blue`; properties không có khóa đó | YAML | Không có xung đột để ghi đè |

Bảng này minh họa các trường hợp phổ biến, **không phải danh sách đầy đủ của mọi nguồn cấu hình**. Khi có nhiều profile, tệp nhiều tài liệu, `spring.config.import`, nguồn do thư viện bổ sung hoặc tùy chỉnh vị trí, phải xét thêm quy tắc riêng của từng cơ chế.

## 6. Thực hành: quan sát hai định dạng cùng tồn tại

Ví dụ dùng **Java 17 + Spring Boot 3.3.x** và dependency `spring-boot-starter`. Có thể tạo dự án tối thiểu bằng Spring Initializr. Đặt các lớp dưới package `example.configformat`; chạy từ IDE, Maven, Gradle hoặc từ JAR đã đóng gói.

### Bước 1 — tạo hai tệp cấu hình

`src/main/resources/application.properties`:

```properties
spring.application.name=config-format-demo
app.ui.title=Giao diện từ properties
app.ui.page-size=25
```

`src/main/resources/application.yaml`:

```yaml
app:
  ui:
    title: Giao diện từ YAML
    accent-color: blue
```

### Bước 2 — tạo lớp nhận cấu hình có kiểu

`src/main/java/example/configformat/UiSettings.java`:

```java
package example.configformat;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.ui")
public record UiSettings(
        String title,
        int pageSize,
        String accentColor
) {
}
```

`@ConfigurationProperties` liên kết nhóm khóa có tiền tố `app.ui` vào record `UiSettings`. Dù nguồn gốc là `.properties` hay YAML, mã Java vẫn dùng cùng một kiểu dữ liệu.

### Bước 3 — đăng ký đối tượng và in giá trị

`src/main/java/example/configformat/ConfigFormatApplication.java`:

```java
package example.configformat;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigFormatApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigFormatApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfig(UiSettings ui) {
        return args -> {
            System.out.println("title=" + ui.title());
            System.out.println("pageSize=" + ui.pageSize());
            System.out.println("accentColor=" + ui.accentColor());
        };
    }
}
```

`@ConfigurationPropertiesScan` đăng ký kiểu cấu hình để Spring tạo bean. Sau đó Spring tiêm bean `UiSettings` vào phương thức `showConfig(...)`; không cần viết mã đọc từng tệp trong `ApplicationRunner`.

### Bước 4 — chạy với cấu hình chung

Ví dụ chạy qua Maven wrapper trên hệ thống hỗ trợ lệnh tương ứng:

```bash
./mvnw spring-boot:run
```

Hoặc chạy JAR đã được đóng gói:

```bash
java -jar app.jar
```

`app.jar` là tên minh họa; hãy thay bằng đường dẫn JAR thực tế.

Kết quả dự kiến của ba dòng do `ApplicationRunner` in:

```text
title=Giao diện từ properties
pageSize=25
accentColor=blue
```

Ba dòng này cho thấy thuộc tính có thể được kết hợp từ hai tệp, đồng thời khóa `title` trùng nhau chịu quy tắc ưu tiên.

### Bước 5 — bật profile `dev`

Thêm `src/main/resources/application-dev.yaml`:

```yaml
app:
  ui:
    title: Giao diện cho dev
    accent-color: orange
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Khi không có nguồn ưu tiên cao hơn:

```text
title=Giao diện cho dev
pageSize=25
accentColor=orange
```

Lưu ý phải **đóng gói lại** nếu đã thêm tệp vào `src/main/resources` nhưng đang chạy một JAR đóng gói từ trước. Chạy qua công cụ build sẽ sử dụng tài nguyên sau khi được công cụ build cập nhật.

### Bước 6 — thêm tệp properties riêng của profile

Thêm `src/main/resources/application-dev.properties`:

```properties
app.ui.title=Giao diện dev từ properties
```

Khởi động lại với profile `dev` sẽ cho kết quả dự kiến:

```text
title=Giao diện dev từ properties
pageSize=25
accentColor=orange
```

Giải thích: cả hai tệp `application-dev.properties` và `application-dev.yaml` nằm cùng vị trí, cùng profile; khóa `title` lấy từ `.properties`, còn khóa `accent-color` không bị tệp `.properties` ghi đè.

### Bước 7 — ghi đè bằng đối số dòng lệnh

```bash
java -jar app.jar --spring.profiles.active=dev --app.ui.title="Từ CLI"
```

Kết quả dự kiến:

```text
title=Từ CLI
pageSize=25
accentColor=orange
```

Bài thực hành này cho thấy tệp profile và định dạng không quyết định mọi thứ: đối số khởi động vẫn có thể ghi đè chúng.

## 7. Nếu phải giữ cả hai định dạng trong dự án đang vận hành

### 7.1. Tổ chức cấu hình theo nguồn sở hữu rõ ràng

Một dự án chuyển đổi từng phần có thể tạm thời giữ:

```text
src/main/resources/
├── application.properties
├── application.yaml
├── application-dev.yaml
└── application-prod.yaml
```

Trong giai đoạn chuyển đổi, hãy ghi rõ quy ước trong tài liệu dự án, ví dụ:

- `application.properties`: chỉ giữ một số khóa cũ chưa chuyển đổi.
- `application.yaml`: giữ cấu hình chính mới được nhóm theo chức năng.
- `application-{profile}.yaml`: chỉ chứa những giá trị thay đổi theo profile.
- Khi một khóa được chuyển sang YAML, xóa **khai báo cũ của chính khóa đó** khỏi tệp properties trong cùng nguồn, để tránh cấu hình mới bị che.

Trước khi sửa tệp cấu hình, người bảo trì cần kiểm tra môi trường triển khai có đưa thêm tệp hoặc biến môi trường bên ngoài hay không. Một khóa trùng tên ở nơi khác có thể khiến kết quả chạy khác với dự đoán chỉ dựa trên mã nguồn.

### 7.2. Di chuyển theo từng nhóm khóa

Giả sử tệp properties cũ:

```properties
app.mail.from-address=noreply@example.test
app.mail.retry-count=3
app.cache.enabled=true
```

Muốn chuyển phần `app.mail` sang YAML:

```yaml
app:
  mail:
    from-address: noreply@example.test
    retry-count: 3
```

Sau khi chuyển, tệp properties nên còn:

```properties
app.cache.enabled=true
```

Nếu giữ cả `app.mail.retry-count=3` trong properties và một giá trị mới `retry-count: 5` trong YAML cùng vị trí, Spring Boot vẫn có thể lấy `3` từ properties. Người sửa YAML có thể tưởng việc đổi sang `5` đã có tác dụng nhưng thực tế không phải vậy.

Vì thế, chuyển đổi định dạng **phải đồng thời xử lý khai báo cũ trùng khóa**. Có thể thực hiện theo từng nhóm cấu hình để dễ xác định tác động; không cần đổi toàn bộ dự án trong một lần.

### 7.3. Không thay định dạng với hy vọng thay thứ tự ưu tiên

Chuyển `application.yaml` thành `application.properties` không giải quyết tình huống biến môi trường hoặc đối số dòng lệnh đang ghi đè một khóa. Tương tự, đặt tệp ở vị trí khác có thể đổi thứ tự ưu tiên dù nội dung không đổi.

Trước khi chuyển đổi, hãy trả lời:

1. Khóa này hiện được khai báo ở những tệp và nguồn nào?
2. Profile nào thực sự đang hoạt động?
3. Ứng dụng nạp cấu hình từ classpath, thư mục bên ngoài hay vị trí chỉ định?
4. Có đối số khởi động, thuộc tính JVM hay biến môi trường nào ghi đè không?
5. Giá trị phải có hiệu lực sau chuyển đổi là gì?

Trả lời các câu này giúp tránh lỗi do cấu hình bị che, đặc biệt ở môi trường staging hoặc production.

## 8. Những cấu hình nâng cao làm thay đổi bức tranh

### 8.1. `spring.config.location` và `spring.config.additional-location`

Theo mặc định, Spring Boot tìm config data ở các vị trí quen thuộc. Có hai thiết lập quan trọng:

- `spring.config.location`: **thay thế** danh sách vị trí tìm kiếm mặc định bằng các vị trí được chỉ định.
- `spring.config.additional-location`: **bổ sung** các vị trí bên cạnh vị trí mặc định; vị trí bổ sung có thể ghi đè giá trị mặc định.

Ví dụ ứng dụng đóng gói có cấu hình chung và được triển khai kèm một thư mục ngoài:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./custom-config/
```

Dấu `/` cuối cho biết đây là đường dẫn thư mục. Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu vị trí đó không tồn tại. Nếu tệp ở nơi được bổ sung có cùng khóa với tệp đóng gói, nguồn bổ sung có thể ghi đè theo quy tắc nạp config data.

Các thiết lập xác định vị trí như `spring.config.location` và `spring.config.additional-location` được dùng rất sớm khi khởi động. Hãy cung cấp chúng dưới dạng biến môi trường, thuộc tính JVM hoặc đối số dòng lệnh thích hợp; không nên dựa vào một tệp mà quá trình nạp vị trí đang cần được xác định bằng chính thiết lập đó.

### 8.2. `spring.config.import`

Spring Boot 3.3 có thể nhập thêm cấu hình từ nơi khác. Ví dụ trong `application.properties`:

```properties
spring.config.import=optional:file:./extra-settings.yaml
app.mode=standard
```

Nếu tệp `extra-settings.yaml` tồn tại và chứa:

```yaml
app:
  mode: imported
```

Giá trị từ tệp được nhập có thể ghi đè khóa trong tài liệu khai báo import. Đây là cơ chế **nhập dữ liệu cấu hình**, không đơn thuần là quy tắc chọn giữa `.properties` và YAML cùng vị trí.

Không nên dùng import trùng lặp để tạo các lớp ghi đè khó hiểu. Nếu dự án dùng import, cần xác định rõ tệp nào là mặc định và tệp nào là phần ghi đè có chủ ý.

### 8.3. Nhiều tài liệu trong một tệp

YAML hỗ trợ phân tách tài liệu bằng `---`:

```yaml
app:
  label: common

---
spring:
  config:
    activate:
      on-profile: dev
app:
  label: dev
```

Khi bật profile `dev`, tài liệu thứ hai được kích hoạt và có thể ghi đè `app.label`. Spring Boot cũng hỗ trợ phân tách nhiều tài liệu trong tệp `.properties` bằng dấu `#---` hoặc `!---` theo cú pháp được quy định.

Vì vậy, không nên cho rằng chỉ nhìn tên tệp là đã hiểu hết nguồn cấu hình có hiệu lực. Một tệp có thể chứa nhiều tài liệu logic với điều kiện kích hoạt khác nhau.

## 9. Những trường hợp cần cẩn thận khi chuyển giữa hai định dạng

### 9.1. Chuỗi, dấu nháy và ký tự đặc biệt

Hai cách viết có thể *trông* giống nhau nhưng không được phân tích như nhau:

```properties
app.message="Xin chào"
```

```yaml
app:
  message: "Xin chào"
```

Trong YAML, dấu nháy thường dùng để bao chuỗi. Trong tệp `.properties`, dấu nháy đôi không có cùng vai trò cú pháp, nên có thể trở thành một phần của giá trị được đọc. Khi di chuyển, đừng máy móc sao chép dấu nháy từ YAML sang properties.

Với chuỗi cần có dấu `#`, dấu `:` hoặc ký tự đầu/cuối đặc biệt, hãy chọn cách biểu diễn an toàn theo đúng định dạng đang dùng. Điều quan trọng là **giá trị sau khi đọc**, không chỉ là vẻ ngoài của dòng cấu hình.

### 9.2. Danh sách và ghi đè theo profile

Tệp chung `application.yaml`:

```yaml
app:
  endpoints:
    - https://a.example.test
    - https://b.example.test
```

Tệp `application-dev.yaml`:

```yaml
app:
  endpoints:
    - http://localhost:8081
```

Khi liên kết cấu hình vào `List<String>`, danh sách từ nguồn profile ưu tiên cao thường thay thế danh sách chung. Không nên mong đợi danh sách kết quả chứa cả ba phần tử. Nếu muốn giữ các giá trị cụ thể ở mọi môi trường, hãy mô hình hóa cấu hình thích hợp và kiểm tra cơ chế liên kết cho loại dữ liệu ấy.

### 9.3. Trường `Map` và giá trị lồng nhau

Với cấu trúc `Map` hoặc bean lồng nhau, một số giá trị có thể được tổng hợp theo khóa con trong quá trình liên kết. Cách xử lý không đồng nhất với danh sách. Khi chuyển từ properties sang YAML, cần để ý liệu cấu trúc mong muốn là `List`, `Map` hay đối tượng có trường cố định.

### 9.4. `@PropertySource` không phải bộ nạp YAML của Boot

`application.yaml` được Spring Boot nạp theo cơ chế config data. Đừng suy luận rằng `@PropertySource("classpath:custom.yaml")` sẽ tự hoạt động giống như nạp YAML mặc định. Cơ chế `@PropertySource` chuẩn không nạp YAML theo cách đó nếu không có xử lý riêng. Khi cần tệp YAML bổ sung, nên xem cơ chế config data và `spring.config.import` phù hợp trong Spring Boot 3.3.

### 9.5. Bí mật không trở nên an toàn chỉ vì chuyển định dạng

Mật khẩu, khóa API và mã thông báo không nên được cam kết vào Git trong cả `.properties` lẫn YAML. Định dạng tệp không cung cấp chức năng mã hóa hay quản lý quyền truy cập. Hãy chọn phương thức cấp bí mật theo hạ tầng triển khai, tránh in thông tin nhạy cảm ra console, log hoặc báo cáo lỗi.

## 10. Cách xác định giá trị thực sự đang được dùng

Khi một thiết lập không như mong đợi, hãy đi theo trình tự điều tra:

**Bước 1 — xác định đúng khóa.** Ví dụ `app.ui.title` có thể được liên kết từ các cách đặt tên phù hợp với quy tắc relaxed binding. Không nhầm `title` với `page-title`.

**Bước 2 — xác định profile.** Kiểm tra đối số `--spring.profiles.active=...`, biến môi trường `SPRING_PROFILES_ACTIVE` hoặc cấu hình khác liên quan. Hãy nhớ profile đang hoạt động mới quyết định các tệp `application-{profile}` được xét.

**Bước 3 — tìm nguồn trùng khóa.** Kiểm tra tệp chung, tệp profile, bản đóng gói trong JAR, tệp ngoài JAR và các nguồn khởi động. Nếu có cả `.properties` và YAML ở một vị trí, áp dụng quy tắc định dạng cho đúng phạm vi ấy.

**Bước 4 — quan sát giá trị có hiệu lực.** Trong môi trường phát triển, có thể dùng `Environment` để đọc một khóa không nhạy cảm:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@Bean
ApplicationRunner printTitle(Environment environment) {
    return args -> System.out.println(
        "app.ui.title=" + environment.getProperty("app.ui.title")
    );
}
```

Đây là ví dụ **phương thức bean đặt trong một lớp `@Configuration` hoặc lớp `@SpringBootApplication`**, không phải một tệp Java độc lập chứa mỗi phương thức. Không in mật khẩu hay bí mật chỉ để chẩn đoán cấu hình.

**Bước 5 — quan sát quá trình nạp cấu hình khi cần.** Có thể tạm bật mức log chi tiết cho thành phần cấu hình ở môi trường phát triển:

```bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
```

Chỉ bật log chẩn đoán ở nơi phù hợp và kiểm tra thông tin ghi ra trước khi chia sẻ. Sau khi tìm được nguyên nhân, đưa mức log trở lại bình thường.

**Bước 6 — kiểm tra bản đóng gói và cách khởi động.** Một tệp `application-dev.yaml` vừa sửa trên mã nguồn chưa chắc đã nằm trong JAR đang chạy. Container hoặc hệ thống triển khai cũng có thể gắn thêm tệp bên ngoài. Giá trị thực tế phụ thuộc vào **bản chạy đang được sử dụng**.

## 11. Quy ước đề xuất cho dự án Spring Boot 3.3

Một quy ước đơn giản, dễ bảo trì:

1. **Chọn một định dạng chuẩn** (`application.properties` hoặc `application.yaml`) và dùng nhất quán ở các tệp cấu hình do dự án sở hữu.
2. **Giữ khóa có tên rõ nghĩa** bằng chữ thường và gạch nối, ví dụ `app.payment.connect-timeout`.
3. **Nhóm các khóa theo chức năng**, để thuận tiện liên kết qua `@ConfigurationProperties` và thay đổi cùng nhau.
4. **Dùng profile cho giá trị thực sự khác theo môi trường**, không sao chép toàn bộ cấu hình chung vào mỗi tệp profile.
5. **Khi chuyển định dạng, xóa khai báo cũ trùng khóa** khỏi nguồn có thể ghi đè nguồn mới và xác nhận giá trị sau khi nạp.
6. **Để cấu hình triển khai ở nguồn phù hợp**, không đặt thông tin bí mật thật vào Git.
7. **Kiểm thử ít nhất một cấu hình mặc định và một cấu hình theo profile** bằng cách quan sát thuộc tính có hiệu lực trong ứng dụng, không chỉ xem nội dung các tệp.
8. **Ghi rõ trường hợp cố ý có nhiều nguồn ghi đè**, nhất là khi ứng dụng đọc tệp ngoài JAR hoặc dùng `spring.config.import`.

Một ví dụ cấu trúc ổn định nếu chọn YAML:

```text
src/main/resources/
├── application.yaml
├── application-dev.yaml
├── application-test.yaml
└── application-prod.yaml
```

Một cấu trúc tương tự với `.properties` cũng hợp lệ. Các tên profile là quy ước của dự án; không phải Spring Boot bắt buộc phải có `dev`, `test` hay `prod`.

## 12. Bài tập dự đoán và đối chiếu kết quả

### Bài 1 — hai định dạng trong cùng thư mục

`application.properties`:

```properties
app.feature.enabled=true
app.feature.label=properties
```

`application.yml`:

```yaml
app:
  feature:
    enabled: false
    color: green
```

**Hỏi:** `enabled`, `label`, `color` có giá trị gì khi không có nguồn ghi đè khác?

**Đáp án mong đợi:** `enabled=true`, `label=properties`, `color=green`. Khóa trùng lấy từ properties, khóa chỉ có trong YAML vẫn sử dụng được.

### Bài 2 — thêm profile

`application.properties`:

```properties
app.mode=default
```

`application-dev.yml`:

```yaml
app:
  mode: development
```

Khởi động với `--spring.profiles.active=dev`.

**Hỏi:** `app.mode` là gì?

**Đáp án mong đợi:** `development`. Tệp dành cho profile hoạt động có thể ghi đè tệp chung, dù chúng dùng hai định dạng khác nhau.

### Bài 3 — thêm đối số dòng lệnh

Vẫn dùng tệp của Bài 2, chạy:

```bash
java -jar app.jar --spring.profiles.active=dev --app.mode=cli
```

**Đáp án mong đợi:** `cli`, vì đối số dòng lệnh có ưu tiên cao hơn những tệp config data đang xét.

### Bài 4 — chuyển định dạng

Ban đầu:

`application.properties`:

```properties
app.mail.retry-count=3
```

Thêm `application.yaml`:

```yaml
app:
  mail:
    retry-count: 5
```

**Hỏi:** Tại sao ứng dụng vẫn có thể nhận `3`, và phải làm gì nếu thật sự muốn chuyển sang YAML?

**Đáp án mong đợi:** hai tệp cùng vị trí và cùng mức cấu hình, nên `.properties` ưu tiên. Khi chuyển đổi có chủ đích, cần loại bỏ khai báo cũ trùng khóa trong properties, rồi xác minh giá trị được nạp.

### Bài 5 — tệp ngoài JAR

Một JAR chứa `application.properties` với `app.mode=packaged`. Khi triển khai, thư mục cấu hình ngoài JAR chứa `application.yaml` với `app.mode=external` ở vị trí mặc định được Spring Boot tìm kiếm.

**Hỏi:** Tại sao không thể chỉ áp dụng câu “properties thắng YAML”?

**Đáp án mong đợi:** vì quy tắc ưu tiên giữa vị trí bên ngoài và tệp đóng gói cũng có tác dụng. Trong bối cảnh mặc định, tệp ngoài có thể ghi đè tệp trong JAR.

## 13. Tổng kết kiến thức cần nhớ

Có thể ghi nhớ năm quan hệ:

```text
.properties và YAML
    -> hai cách biểu diễn khóa cấu hình

Nhiều PropertySource
    -> Spring Environment chọn giá trị có hiệu lực

Hai định dạng cùng vị trí, cùng mức cấu hình
    -> .properties ưu tiên khóa trùng

Profile, vị trí ngoài JAR và nguồn khởi động
    -> cũng thay đổi thứ tự ưu tiên

@ConfigurationProperties
    -> liên kết giá trị cuối cùng thành đối tượng Java có kiểu
```

Khi quyết định dùng `.properties` hay YAML trong Spring Boot 3.3, hãy chọn định dạng giúp đội ngũ duy trì cấu hình rõ ràng nhất và giữ quy ước nhất quán. Khi cả hai cùng tồn tại, câu hỏi quan trọng là **các giá trị trùng khóa nằm ở nguồn nào và được nạp theo thứ tự nào**. Quan sát giá trị trong `Environment` hoặc một bean `@ConfigurationProperties` sẽ cho bạn bằng chứng thực tế thay vì chỉ suy đoán từ tên tệp.

### Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot Reference — Properties and Configuration: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
