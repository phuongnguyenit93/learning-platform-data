# Đổi tên cơ sở của tệp bằng spring.config.name

## 1. Tại sao cần đổi tên tệp cấu hình?

Khi tạo ứng dụng Spring Boot, cách thông dụng là đặt cấu hình trong các tệp có tên cơ sở `application`:

```text
src/main/resources/
├── application.properties
├── application.yml
└── application-prod.yml
```

Từ “tên cơ sở” (base name) là phần đứng trước đuôi tệp như `.properties`, `.yml` hoặc `.yaml`. Ví dụ, `application.yml` có tên cơ sở là `application`.

Spring Boot mặc định tìm các tệp mang tên cơ sở `application` tại những vị trí cấu hình được hỗ trợ. Nhưng một dự án có thể muốn sử dụng `billing.yml`, `orders.yml` hoặc `my-service.properties` để thể hiện rõ mục đích triển khai.

Thuộc tính **`spring.config.name`** cho phép chỉ định tên cơ sở mà cơ chế nạp cấu hình của Spring Boot sẽ tìm.

Ví dụ:

```bash
java -jar app.jar --spring.config.name=billing
```

Khi đó Spring Boot tìm tệp có tên cơ sở `billing`, chẳng hạn `billing.properties`, `billing.yml` hoặc `billing.yaml`, tại các vị trí tìm kiếm cấu hình đang có hiệu lực.

**Cần phân biệt:** lệnh trên không đổi tên tệp vật lý, không sao chép tệp và không tự động tạo tệp mới. Bạn phải chuẩn bị tệp `billing.yml` hoặc tệp tương ứng ở nơi Spring Boot có thể đọc.

## 2. spring.config.name thay đổi điều gì?

Giả sử dự án có cấu trúc:

```text
src/
└── main/
    └── resources/
        ├── application.yml
        └── billing.yml
```

Nội dung `application.yml`:

```yaml
demo:
  message: "Cấu hình mặc định"
  timeout-seconds: 10
```

Nội dung `billing.yml`:

```yaml
demo:
  message: "Cấu hình dịch vụ billing"
  timeout-seconds: 25
```

Nếu khởi động ứng dụng bình thường:

```bash
java -jar app.jar
```

Spring Boot dùng tên cơ sở mặc định `application`. Vì vậy cấu hình trên có thể cung cấp `demo.message=Cấu hình mặc định` và `demo.timeout-seconds=10`.

Nếu khởi động với:

```bash
java -jar app.jar --spring.config.name=billing
```

Spring Boot dùng `billing` làm tên cơ sở cho việc tìm kiếm tệp cấu hình. Khi không có nguồn ưu tiên cao hơn ghi đè, các giá trị trở thành:

```text
demo.message = Cấu hình dịch vụ billing
demo.timeout-seconds = 25
```

Điều đáng chú ý là `spring.config.name=billing` **không có nghĩa là nạp `application.yml` trước rồi đè bằng `billing.yml`**. Việc tìm kiếm theo tên cơ sở đã thay đổi; `application.yml` không còn được tìm theo tên mặc định, trừ khi bạn bổ sung `application` vào danh sách tên hoặc tệp đó được nạp qua cơ chế khác.

## 3. Ba cách đặt spring.config.name trước khi ứng dụng chạy

`spring.config.name` là một thuộc tính khởi tạo sớm. Spring Boot cần biết giá trị này **trước khi quyết định sẽ đọc những tệp cấu hình nào**. Những cách đặt thường dùng là đối số dòng lệnh, thuộc tính hệ thống Java và biến môi trường hệ điều hành.

### 3.1. Đối số dòng lệnh

```bash
java -jar app.jar --spring.config.name=billing
```

Đây là cách thuận tiện khi chạy thủ công hoặc muốn kiểm chứng nhanh. Cú pháp `--spring.config.name=billing` là đối số ứng dụng truyền sau `-jar app.jar`.

### 3.2. Thuộc tính hệ thống Java

```bash
java -Dspring.config.name=billing -jar app.jar
```

Chú ý `-Dspring.config.name=billing` đặt **trước** `-jar`, vì đây là tùy chọn của JVM.

### 3.3. Biến môi trường

Trên Bash hoặc shell tương thích POSIX:

```bash
export SPRING_CONFIG_NAME=billing
java -jar app.jar
```

Hoặc chỉ áp dụng cho một lần chạy:

```bash
SPRING_CONFIG_NAME=billing java -jar app.jar
```

Trên Windows PowerShell:

```powershell
$env:SPRING_CONFIG_NAME = "billing"
java -jar app.jar
Remove-Item Env:SPRING_CONFIG_NAME
```

Biến `SPRING_CONFIG_NAME` là cách biểu diễn theo biến môi trường của khóa `spring.config.name`. Việc áp dụng những cách viết khác nhau tuân theo cơ chế đọc cấu hình của Spring Boot.

**Không nên kỳ vọng đặt `spring.config.name` bên trong chính `application.yml` sẽ làm thay đổi việc tìm `application.yml` thành một tệp khác.** Đến khi Spring Boot đọc được `application.yml`, quá trình lựa chọn tên và vị trí tệp cấu hình đã diễn ra. Vì vậy hãy cung cấp thuộc tính này từ nguồn có sẵn ở giai đoạn khởi tạo sớm.

## 4. Kết hợp với cấu hình theo profile

Spring Boot hỗ trợ biến thể tệp cấu hình theo profile. Khi tên cơ sở là `application` và profile `prod` được kích hoạt, một tệp thường gặp là `application-prod.yml`.

Nếu đổi tên cơ sở thành `billing`, quy tắc đặt tên theo profile được áp dụng tương ứng:

```text
src/main/resources/
├── billing.yml
├── billing-dev.yml
└── billing-prod.yml
```

Ví dụ `billing.yml` chứa giá trị chung:

```yaml
demo:
  message: "Giá trị chung"
  timeout-seconds: 20
```

Tệp `billing-prod.yml` chứa cấu hình riêng của profile:

```yaml
demo:
  message: "Giá trị production"
```

Chạy:

```bash
java -jar app.jar --spring.config.name=billing --spring.profiles.active=prod
```

Khi không có nguồn cấu hình ưu tiên cao hơn:

| Thuộc tính | Giá trị có hiệu lực | Nguồn giải thích |
| --- | --- | --- |
| `demo.message` | `Giá trị production` | `billing-prod.yml` ghi đè giá trị chung |
| `demo.timeout-seconds` | `20` | `billing.yml` cung cấp giá trị chưa bị ghi đè |

Cách hiểu đúng là:

1. `spring.config.name=billing` xác định tên cơ sở được tìm.
2. `spring.profiles.active=prod` kích hoạt profile `prod`.
3. Cơ chế Config Data xem xét các tệp phù hợp với tên cơ sở và profile trong những vị trí tìm kiếm có hiệu lực.
4. Các nguồn cấu hình được kết hợp theo quy tắc ưu tiên; thuộc tính chỉ xuất hiện trong tệp chung vẫn có thể được sử dụng.

Đổi tên cơ sở **không làm thay đổi tên profile**, cũng không loại bỏ cơ chế ghi đè của cấu hình theo profile.

## 5. Có thể cấu hình nhiều tên cơ sở

`spring.config.name` cho phép khai báo danh sách tên cơ sở ngăn cách bằng dấu phẩy.

Ví dụ:

```bash
java -jar app.jar --spring.config.name=application,billing
```

Điều này hướng Spring Boot xem xét cả các tệp mang tên `application` và các tệp mang tên `billing` tại các vị trí cấu hình tương ứng.

Một cách bố trí là:

```text
src/main/resources/
├── application.yml
├── application-prod.yml
├── billing.yml
└── billing-prod.yml
```

Cấu hình này hữu ích khi muốn **giữ tên mặc định `application` và đồng thời bổ sung một nhóm tệp theo tên riêng**. Nếu chỉ dùng `--spring.config.name=billing`, đừng mặc định `application.yml` vẫn được tìm như trước.

Khi các tệp có cùng một khóa, kết quả không được xác định bằng cách “gộp nội dung JSON/YAML theo ý muốn”. Spring Boot có quy tắc về thứ tự vị trí cấu hình, các tài liệu, profile và nguồn thuộc tính. Cần phân biệt việc **chọn tập tệp được tìm** với việc **chọn giá trị có hiệu lực** trong các tệp đó.

Trong ví dụ cần bảo đảm rõ nguồn nào có hiệu lực, hãy đọc chính thuộc tính cần kiểm chứng từ `Environment` thay vì suy đoán chỉ dựa vào tên tệp.

## 6. Tên cơ sở khác với vị trí tìm tệp

`spring.config.name` giải quyết câu hỏi **“Tìm tệp mang tên cơ sở nào?”**; còn `spring.config.location` hoặc `spring.config.additional-location` giải quyết câu hỏi **“Tìm ở đâu?”**.

Mặc định, Spring Boot 3.x xem xét những vị trí quen thuộc như thư mục gốc của classpath, `classpath:/config/`, thư mục làm việc hiện tại, `./config/` và các thư mục con trực tiếp của `./config/` theo cơ chế tìm kiếm mặc định. Các vị trí này liên quan tới việc triển khai ứng dụng chứ không chỉ cấu trúc `src/main/resources` trong lúc phát triển.

Ví dụ tạo cấu hình ngoài ứng dụng:

```text
deploy/
├── app.jar
└── config/
    └── billing.yml
```

Trong `deploy/config/billing.yml`:

```yaml
server:
  port: 9095
demo:
  message: "Cấu hình bên ngoài JAR"
```

Khi thư mục làm việc là `deploy/`, có thể chạy:

```bash
java -jar app.jar --spring.config.name=billing
```

Cơ chế tìm kiếm mặc định có thể tìm thấy `./config/billing.yml`. Thư mục làm việc của **tiến trình chạy Java** là yếu tố quan trọng: đổi thư mục làm việc có thể khiến đường dẫn `./config/` trỏ tới nơi khác.

Nếu muốn chỉ định thư mục rõ ràng, dùng cả tên và vị trí:

```bash
java -jar app.jar \
  --spring.config.name=billing \
  --spring.config.location=file:./config/
```

Dấu `/` cuối `file:./config/` cho biết đó là một thư mục. Với vị trí là **thư mục**, Spring Boot có thể kết hợp tên từ `spring.config.name` để tìm tệp thích hợp.

Ngược lại, nếu `spring.config.location` trỏ tới **tệp cụ thể**, chẳng hạn:

```bash
java -jar app.jar --spring.config.location=file:./config/billing.yml
```

thì đường dẫn tệp đã được chỉ định trực tiếp; việc chọn tên cơ sở không còn mang cùng ý nghĩa đối với vị trí tệp đó.

Lưu ý thêm: `spring.config.location` có thể **thay thế danh sách vị trí tìm kiếm mặc định**; `spring.config.additional-location` bổ sung vị trí vào các vị trí mặc định. Chọn thuộc tính phù hợp để tránh vô tình bỏ qua các nguồn cấu hình cần thiết.

## 7. Phân biệt với các thuộc tính có tên gần giống

| Thuộc tính | Câu hỏi mà thuộc tính trả lời | Ví dụ |
| --- | --- | --- |
| `spring.config.name` | Dùng tên cơ sở nào khi tìm tệp? | `billing` |
| `spring.config.location` | Lấy cấu hình từ những vị trí nào thay cho vị trí mặc định? | `file:./config/` |
| `spring.config.additional-location` | Bổ sung nơi tìm cấu hình ở đâu? | `file:./deploy-overrides/` |
| `spring.config.import` | Nạp thêm tài nguyên cấu hình nào? | `optional:file:./secrets.properties` |
| `spring.application.name` | Tên nhận diện logic của ứng dụng là gì? | `billing-service` |
| `spring.profiles.active` | Kích hoạt profile nào? | `prod` |

Một nhầm lẫn phổ biến:

```yaml
spring:
  application:
    name: billing
```

Cấu hình trên đặt **tên ứng dụng** là `billing`. Nó **không** tự đổi tên tệp mặc định từ `application.yml` sang `billing.yml`. Hai thuộc tính `spring.application.name` và `spring.config.name` phục vụ hai việc độc lập.

Một nhầm lẫn khác là đặt:

```yaml
spring:
  config:
    name: billing
```

trong `application.yml` rồi mong Spring Boot ngừng đọc `application.yml` và chuyển ngay sang `billing.yml`. Cách đó không đáp ứng yêu cầu chọn tên tệp **trước giai đoạn đọc Config Data**; hãy truyền `spring.config.name` khi khởi chạy.

## 8. Ví dụ thực hành có thể chạy

### Bước 1: Chuẩn bị hai tệp

Tệp `src/main/resources/application.yml`:

```yaml
demo:
  source: "application"
  greeting: "Xin chào từ cấu hình mặc định"
```

Tệp `src/main/resources/custom.yml`:

```yaml
demo:
  source: "custom"
  greeting: "Xin chào từ custom.yml"
```

### Bước 2: Thêm mã đọc cấu hình

Dùng một thành phần chạy sau khi ứng dụng Spring Boot khởi động:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationNamePrinter implements ApplicationRunner {

    private final Environment environment;

    public ConfigurationNamePrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String source = environment.getProperty("demo.source", "<không có>");
        String greeting = environment.getProperty("demo.greeting", "<không có>");

        System.out.println("demo.source = " + source);
        System.out.println("demo.greeting = " + greeting);
    }
}
```

### Bước 3: Chạy bằng tên mặc định

Sau khi đóng gói ứng dụng thành `app.jar`, chạy:

```bash
java -jar app.jar
```

Giả sử không có nguồn khác ghi đè `demo.source` và `demo.greeting`, phần nội dung được in sẽ là:

```text
demo.source = application
demo.greeting = Xin chào từ cấu hình mặc định
```

### Bước 4: Chạy bằng tên cơ sở tùy chỉnh

```bash
java -jar app.jar --spring.config.name=custom
```

Phần nội dung được in thay đổi thành:

```text
demo.source = custom
demo.greeting = Xin chào từ custom.yml
```

Không cần sửa code Java để nhận kết quả khác. Tham số khởi động quyết định nhóm tệp cấu hình mà ứng dụng tìm.

### Bước 5: Kết hợp profile

Thêm `src/main/resources/custom-test.yml`:

```yaml
demo:
  greeting: "Xin chào từ profile test"
```

Chạy:

```bash
java -jar app.jar --spring.config.name=custom --spring.profiles.active=test
```

Kết quả dự kiến:

```text
demo.source = custom
demo.greeting = Xin chào từ profile test
```

Giải thích: giá trị `demo.source` đến từ `custom.yml`; giá trị `demo.greeting` được tệp profile `custom-test.yml` ghi đè.

Lưu ý rằng môi trường thực tế có thể đặt thuộc tính bằng đối số dòng lệnh, JSON, biến môi trường hoặc nguồn khác có độ ưu tiên cao hơn, khi đó kết quả cuối cùng có thể khác ví dụ.

## 9. Những tình huống dễ gây nhầm lẫn

### 9.1. Đổi tên trong lệnh nhưng không đổi tên tệp

Tình huống:

```text
Chỉ có application.yml
Chạy với --spring.config.name=custom
```

Không có tệp `custom.yml` (hay định dạng tương ứng) ở vị trí được tìm. Khi đó các giá trị chỉ tồn tại trong `application.yml` sẽ không tự động được sử dụng qua tên cơ sở mới.

Không phải mọi lần không tìm thấy tệp theo tên tùy chỉnh đều làm ứng dụng dừng ngay: với các vị trí tìm kiếm mặc định, ứng dụng vẫn có thể chạy bằng các nguồn cấu hình khác. Vấn đề có thể xuất hiện khi một thành phần bắt buộc cần đến thuộc tính bị thiếu. Một vị trí hoặc tệp được chỉ định rõ là bắt buộc qua cơ chế Config Data có thể phát sinh lỗi không tìm thấy vị trí nếu tài nguyên không tồn tại.

### 9.2. Sử dụng tên đầy đủ thay vì tên cơ sở

Ý định của `spring.config.name` là khai báo tên cơ sở như:

```text
billing
orders
custom
```

Đừng dùng `spring.config.name=billing.yml` để thay cho đường dẫn tệp đầy đủ. Nếu cần chỉ định đúng một tài nguyên cụ thể, hãy cân nhắc `spring.config.location` với đường dẫn tệp.

### 9.3. Đặt sai vị trí của tùy chọn JVM

Đúng:

```bash
java -Dspring.config.name=custom -jar app.jar
```

Đúng với đối số ứng dụng:

```bash
java -jar app.jar --spring.config.name=custom
```

Hai cú pháp này thuộc hai cơ chế nhận tham số khác nhau. Không chuyển `-D...` sang cuối lệnh và kỳ vọng JVM sẽ đọc nó như một tùy chọn hệ thống.

### 9.4. Đọc một tệp từ đường dẫn không ngờ tới

Giả sử đã đóng gói `custom.yml` trong JAR, nhưng máy chạy còn có `./config/custom.yml`. Cơ chế Config Data có thể nạp cấu hình từ nhiều vị trí có độ ưu tiên khác nhau; một tệp bên ngoài có thể ghi đè giá trị cùng khóa trong tệp đóng gói.

Vì vậy, nếu thấy giá trị không như mong đợi, cần phân biệt:

- Tên cơ sở đang sử dụng là gì?
- Những vị trí nào đang được tìm?
- Profile nào đang hoạt động?
- Thuộc tính có xuất hiện tại nguồn ưu tiên cao hơn không?

### 9.5. Thêm tên thứ hai nhưng quên giữ tên thứ nhất

Khi cần nạp cả tệp mặc định và tệp theo dịch vụ, hãy chỉ định rõ các tên cần thiết, chẳng hạn `--spring.config.name=application,custom`. Chỉ đặt `custom` có thể làm mất các giá trị mà trước đó bạn dựa vào trong `application.yml`.

### 9.6. Mong profile tự đổi tên cơ sở

Đặt `--spring.profiles.active=prod` không tự chọn `billing.yml` chỉ vì ứng dụng có tên billing. Profile chỉ tạo ngữ cảnh cho cách chọn tài liệu/tệp theo profile; tên cơ sở vẫn do giá trị `spring.config.name` quyết định.

## 10. Quan sát nguồn cấu hình khi cần chẩn đoán

Để xác định giá trị một khóa đang được lấy từ đâu, có thể đọc `Environment`:

```java
String value = environment.getProperty("demo.greeting");
System.out.println(value);
```

Nếu cần truy vết nguồn thuộc tính trong môi trường phát triển được kiểm soát, Spring Boot Actuator có endpoint `env` khi được đưa vào ứng dụng và cấu hình cho phép truy cập. Chú ý hạn chế công khai dữ liệu cấu hình có thể chứa thông tin nhạy cảm.

Đừng chỉ nhìn tên tệp và kết luận rằng toàn bộ thuộc tính đến từ tệp đó. `spring.config.name` xác định **tên các ứng viên được tìm**, còn việc chọn giá trị cuối cùng phụ thuộc cả vào vị trí, profile và thứ tự ưu tiên giữa các nguồn thuộc tính.

## 11. Bài tập củng cố

Xét thư mục:

```text
src/main/resources/
├── application.yml
├── payment.yml
└── payment-dev.yml
```

Các tệp chứa:

```yaml
# application.yml
demo:
  mode: "application"
```

```yaml
# payment.yml
demo:
  mode: "payment"
  currency: "VND"
```

```yaml
# payment-dev.yml
demo:
  mode: "payment-dev"
```

Hãy dự đoán kết quả khi không có nguồn khác ghi đè:

| Lệnh khởi động | `demo.mode` | `demo.currency` |
| --- | --- | --- |
| `java -jar app.jar` | `application` | Không có trong các tệp được tìm theo tên mặc định |
| `java -jar app.jar --spring.config.name=payment` | `payment` | `VND` |
| `java -jar app.jar --spring.config.name=payment --spring.profiles.active=dev` | `payment-dev` | `VND` |

Thử thêm `--demo.mode=cli` vào lệnh cuối. Khi đó `demo.mode` trở thành `cli` vì đối số dòng lệnh của thuộc tính thông thường có độ ưu tiên cao hơn các giá trị từ tệp cấu hình.

## 12. Ghi nhớ

- `spring.config.name` thay đổi **tên cơ sở** được Spring Boot sử dụng để tìm tệp cấu hình; mặc định là `application`.
- Chỉ truyền phần tên, chẳng hạn `payment`, thay vì mặc định phải truyền `payment.yml` hoặc đường dẫn.
- Hãy cấp `spring.config.name` từ một nguồn có sẵn lúc khởi động sớm: đối số `--spring.config.name=...`, thuộc tính JVM `-Dspring.config.name=...` hoặc biến môi trường `SPRING_CONFIG_NAME`.
- Khi dùng profile, tên cơ sở mới tiếp tục phối hợp với hậu tố profile, ví dụ `payment-dev.yml` khi profile `dev` được kích hoạt.
- Có thể khai báo nhiều tên cơ sở, ví dụ `application,payment`, khi cần tìm nhiều nhóm tệp.
- `spring.config.name` chọn **tên**; `spring.config.location` và `spring.config.additional-location` liên quan đến **vị trí**. `spring.application.name` chỉ đặt tên ứng dụng.
- Việc đổi tên cơ sở không làm thay đổi thứ tự ưu tiên chung giữa các nguồn thuộc tính. Muốn hiểu giá trị đang có hiệu lực, hãy xét thêm nguồn, vị trí và profile.
