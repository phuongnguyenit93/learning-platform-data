# Import tùy chọn và phân biệt thiếu tài nguyên với nội dung không hợp lệ

Trong **Spring Boot Externalized Configuration**, `spring.config.import` cho phép một tài liệu cấu hình nhập thêm cấu hình từ vị trí khác. Đây là một phần của **Config Data API**: Spring Boot giải quyết các vị trí được khai báo, nạp tài nguyên phù hợp, kết hợp các nguồn property và sau đó sử dụng chúng để cấu hình ứng dụng.

Điểm dễ nhầm nhất là tiền tố **`optional:`**. Tiền tố này nói rằng **không tìm thấy vị trí cấu hình được import có thể được chấp nhận**. Nó **không** nói rằng Spring Boot sẽ bỏ qua mọi lỗi của tài nguyên đã tìm thấy. Nếu file tồn tại nhưng YAML sai cú pháp, cấu trúc không hợp lệ hoặc giá trị không bind/validate được vào kiểu Java, ứng dụng vẫn có thể khởi động thất bại.

Bài này làm rõ cách dùng import tùy chọn, phân biệt từng loại lỗi, thiết kế giá trị dự phòng và kiểm tra đúng hành vi.

## 1. Nhắc lại vai trò của spring.config.import

Giả sử ứng dụng có file `src/main/resources/application.yml`:

~~~yaml
spring:
  config:
    import: "classpath:integration.yml"

app:
  name: "order-service"
~~~

Spring Boot gặp `spring.config.import` và tìm cấu hình ở vị trí `classpath:integration.yml`. Nếu tài nguyên tồn tại và được nạp hợp lệ, property bên trong nó tham gia vào tập externalized configuration của ứng dụng.

Ví dụ `src/main/resources/integration.yml`:

~~~yaml
remote:
  client:
    base-url: "https://api.example.invalid"
    timeout: 3s
~~~

Một bean có thể dùng các giá trị `remote.client.base-url` và `remote.client.timeout` thông qua `@ConfigurationProperties` hoặc cơ chế cấu hình thích hợp.

Điểm quan trọng:

- Import là **hướng dẫn tìm và nạp nguồn cấu hình**, không phải khai báo một Spring bean.
- Một file import có thể chứa nhiều property; các property sau đó được kết hợp với những nguồn khác theo quy tắc ưu tiên của Spring Boot.
- Tài liệu được import có thứ tự ưu tiên so với tài liệu khai báo import; thông thường giá trị từ import **ghi đè giá trị cùng key trong tài liệu đã import nó**.
- Nếu khai báo nhiều vị trí trong một `spring.config.import`, thứ tự của các vị trí có ý nghĩa; vị trí đứng sau có thể ghi đè giá trị từ vị trí trước.
- Nếu cùng một vị trí được khai báo import lặp lại, Spring Boot không mặc nhiên nạp lại file đó nhiều lần.

Không nên xem `spring.config.import` như câu lệnh “copy nguyên văn nội dung file” vào đúng vị trí dòng YAML. Đây là cơ chế nạp cấu hình và giải quyết thứ tự ưu tiên.

## 2. Import bắt buộc và import tùy chọn

Có hai cách khai báo cơ bản.

**Import bắt buộc:**

~~~yaml
spring:
  config:
    import: "file:./config/payment.yml"
~~~

Nếu vị trí `./config/payment.yml` không tồn tại và không có chính sách bỏ qua phù hợp, quá trình khởi động sẽ thất bại vì Spring Boot không thể nạp một vị trí cấu hình **được yêu cầu**. Tình huống này thường được báo bởi nhóm lỗi `ConfigDataLocationNotFoundException`; tên thông báo cụ thể có thể khác theo loại vị trí/phiên bản Spring Boot.

**Import tùy chọn:**

~~~yaml
spring:
  config:
    import: "optional:file:./config/payment.yml"
~~~

Nếu vị trí này không có, Spring Boot **có thể tiếp tục khởi động** và bỏ qua nguồn import bị thiếu. Các property lẽ ra do file đó cung cấp sẽ không xuất hiện từ nguồn ấy, nên ứng dụng cần có giá trị dự phòng hoặc không yêu cầu chúng.

Bảng so sánh:

| Tình huống | Import bắt buộc | Import tùy chọn |
| --- | --- | --- |
| Vị trí tồn tại và tài nguyên hợp lệ | Nạp cấu hình | Nạp cấu hình |
| Vị trí không tồn tại | Thường thất bại khi xử lý Config Data | Bỏ qua vị trí không tìm thấy |
| File tồn tại nhưng YAML sai cú pháp | Thất bại khi parse | **Vẫn thất bại khi parse** |
| File tồn tại nhưng không có quyền đọc | Báo lỗi truy cập/nạp | **Không được bảo đảm bỏ qua**; `optional:` không phải chế độ bỏ qua lỗi IO |
| Giá trị đã nạp không convert được sang kiểu Java | Có thể thất bại khi bind | **Vẫn có thể thất bại khi bind** |
| Giá trị đã nạp vi phạm validation | Có thể thất bại khi validation | **Vẫn có thể thất bại khi validation** |
| File có nội dung hợp lệ nhưng thiếu property bắt buộc của ứng dụng | Phụ thuộc cách ứng dụng sử dụng/validate property | Phụ thuộc cách ứng dụng sử dụng/validate property |

Điểm phân biệt: `optional:` xử lý việc **không tìm thấy vị trí**; nó không khiến nội dung sai trở thành nội dung đúng.

## 3. Cú pháp của optional: và các vị trí phổ biến

Tiền tố `optional:` được đặt **ngay trước vị trí import**.

### 3.1. Import từ classpath

~~~yaml
spring:
  config:
    import: "optional:classpath:feature-overrides.yml"
~~~

Cách này phù hợp với một file đi kèm ứng dụng nhưng không bắt buộc có trong mọi build hoặc module. Khi file đã được đóng gói trong classpath, nó được nạp; khi thiếu, nguồn ấy được bỏ qua.

Nếu file cần có trong **mọi bản build**, hãy sử dụng import bắt buộc để lỗi đóng gói bị phát hiện sớm.

### 3.2. Import từ hệ thống file

~~~yaml
spring:
  config:
    import: "optional:file:./config/local-overrides.yml"
~~~

`file:./config/local-overrides.yml` được giải quyết theo vị trí và quy tắc của file-system location. Với đường dẫn tương đối, **thư mục làm việc của tiến trình** ảnh hưởng nơi Spring tìm file; đường dẫn tương đối không mặc nhiên tính từ thư mục chứa `application.yml`.

Tình huống phù hợp: máy phát triển có file cấu hình riêng mà không phải lập trình viên nào cũng tạo.

Nếu cấu hình ngoài là bắt buộc đối với production, nên khai báo vị trí bắt buộc hoặc dùng một cơ chế kiểm tra runtime phù hợp. Không chọn `optional:` chỉ để làm “mất thông báo lỗi”.

### 3.3. Import nhiều vị trí

~~~yaml
spring:
  config:
    import:
      - "optional:classpath:defaults-extra.yml"
      - "optional:file:./config/local-overrides.yml"
      - "file:./config/required-security.yml"
~~~

Ở đây:

- `defaults-extra.yml` có thể vắng mặt.
- `local-overrides.yml` có thể vắng mặt.
- `required-security.yml` được yêu cầu; không tìm thấy là lỗi khởi động.

Có thể khai báo danh sách import dưới dạng chuỗi phân tách bằng dấu phẩy:

~~~yaml
spring:
  config:
    import: "optional:classpath:defaults-extra.yml,optional:file:./config/local-overrides.yml"
~~~

**Mỗi vị trí cần tiền tố `optional:` riêng nếu muốn nó là tùy chọn.** Đừng giả định viết `optional:` ở đầu sẽ làm mọi vị trí sau dấu phẩy thành tùy chọn.

## 4. Phân biệt “vị trí không tìm thấy” và “nội dung không hợp lệ”

Đây là trọng tâm của bài.

### Trường hợp A — Không có file được import

`application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/optional-extra.yml"

service:
  retry-count: 3
~~~

Giả sử trên máy chạy ứng dụng **không có** file `./config/optional-extra.yml`. Spring Boot có thể bỏ qua import; giá trị `service.retry-count` từ `application.yml` vẫn có mặt.

Không có nghĩa mọi thứ tự động an toàn: nếu ứng dụng cần property chỉ tồn tại trong file vắng mặt, một bean hoặc validation liên quan có thể thất bại **ở bước sau**. `optional:` chỉ cho phép bước tìm nguồn import thiếu được tiếp tục.

### Trường hợp B — File có thật nhưng YAML sai

Giữ nguyên `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/optional-extra.yml"
~~~

Tạo `./config/optional-extra.yml` với nội dung lỗi:

~~~yaml
service:
  retry-count: 4
  message: Status: Ready
~~~

Dòng `message: Status: Ready` chứa `: ` bên trong plain scalar, nên dễ tạo lỗi cú pháp YAML. Spring Boot đã **tìm thấy file** và cố nạp nó. Tiền tố `optional:` không làm parser bỏ qua YAML lỗi.

Sửa cú pháp:

~~~yaml
service:
  retry-count: 4
  message: "Status: Ready"
~~~

Sau khi file hợp lệ, cấu hình trong file được đưa vào xử lý bình thường.

### Trường hợp C — File hợp lệ nhưng giá trị không bind được

Nội dung `optional-extra.yml`:

~~~yaml
service:
  retry-count: "many"
~~~

YAML này **hợp lệ về cú pháp**, nhưng nếu ứng dụng bind `service.retry-count` vào kiểu `int`, chuỗi `"many"` không chuyển được sang số nguyên theo cách thông thường. Lỗi xuất hiện ở bước **binding/conversion**, không phải do không tìm thấy vị trí hoặc parse YAML.

Một record có thể nhận dữ liệu đó:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(int retryCount) {}
~~~

Khi bean cấu hình này được đăng ký và bind, giá trị `"many"` có thể gây lỗi khởi động. Dù import có `optional:`, Spring không được yêu cầu “chuyển sai cũng bỏ qua”.

### Trường hợp D — File hợp lệ, đúng kiểu nhưng vi phạm validation

Giả sử ứng dụng yêu cầu số lần thử lại phải không âm. Cấu hình:

~~~yaml
service:
  retry-count: -1
~~~

Đây là YAML hợp lệ và `-1` có thể chuyển thành `int`. Tuy nhiên, một ràng buộc validation (ví dụ `@Min(0)` với cơ chế validation đã cấu hình) sẽ từ chối nó.

Sự khác biệt:

1. **Not found:** không định vị được tài nguyên.
2. **Parse error:** tìm được tài nguyên nhưng không hiểu cú pháp.
3. **Bind/conversion error:** đọc được property nhưng không chuyển sang kiểu yêu cầu.
4. **Validation error:** chuyển được kiểu nhưng vi phạm quy tắc.

Chỉ tình huống đầu tiên nằm trong mục đích chính của `optional:`.

## 5. Ví dụ có fallback rõ ràng

Một import tùy chọn hữu ích khi ứng dụng có giá trị mặc định hợp lý.

`application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/local-overrides.yml"

notification:
  enabled: false
  sender-name: "Demo App"
  retry-count: 2
~~~

Trên máy phát triển, có thể tạo `./config/local-overrides.yml`:

~~~yaml
notification:
  enabled: true
  sender-name: "Developer Sandbox"
  retry-count: 1
~~~

Hai tình huống:

- **Không có override file:** ứng dụng có thể dùng các giá trị `false`, `Demo App`, `2` từ cấu hình gốc.
- **Có override file hợp lệ:** các key được import có thể ghi đè giá trị trùng key trong tài liệu khai báo import, theo thứ tự ưu tiên Config Data.

Đây là ví dụ về **cấu hình dự phòng có chủ đích**. Các mặc định nên an toàn và rõ ý nghĩa; nếu một tích hợp không được cấu hình đầy đủ, mặc định `enabled: false` có thể phù hợp hơn tự kết nối tới endpoint production.

Nếu file tồn tại nhưng sai:

~~~yaml
notification:
  retry-count: "always"
~~~

Giá trị đó có thể làm binding vào số nguyên thất bại. Trạng thái “optional” không có nghĩa là “nếu nội dung sai thì quay về mặc định”.

## 6. Phân biệt import tùy chọn với property tùy chọn

Một nhầm lẫn khác là giả định bỏ qua được import thì **mọi property bên trong file đó cũng thành tùy chọn**.

Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:file:./config/mail.yml"
~~~

Nếu file `mail.yml` không tồn tại, import có thể bỏ qua. Nhưng bean cần `mail.smtp.host` không có mặc định, chẳng hạn:

~~~java
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "mail.smtp")
public record MailSmtpProperties(URI host) {}
~~~

Bản thân khai báo record trên không tự bảo đảm host bắt buộc. Tùy cách đăng ký, sử dụng và validation, giá trị có thể vắng mặt và gây lỗi ở bước sau. Để thể hiện yêu cầu rõ ràng, cần thiết kế validation, điều kiện bean hoặc cách vô hiệu hóa tích hợp nếu chưa có cấu hình.

Một cấu trúc dễ hiểu hơn:

~~~yaml
spring:
  config:
    import: "optional:file:./config/mail.yml"

mail:
  enabled: false
~~~

Kết hợp logic đăng ký thành phần với `mail.enabled`, ràng buộc dữ liệu khi tích hợp được bật và validation cần thiết. Nếu production **bắt buộc** có SMTP, đừng dùng `optional:` làm cách bỏ qua trách nhiệm kiểm tra.

**Hai câu hỏi độc lập:**

- Có bắt buộc **tài nguyên cấu hình ở vị trí đó** phải hiện diện không?
- Có bắt buộc **một property có giá trị hợp lệ** để nghiệp vụ/tích hợp hoạt động không?

`optional:` chỉ trả lời câu hỏi thứ nhất.

## 7. Kỹ thuật bắt lỗi đúng theo giai đoạn

Khi ứng dụng không khởi động, cần tìm đúng giai đoạn:

| Dấu hiệu | Giai đoạn | Hướng xử lý |
| --- | --- | --- |
| Thông báo không tìm thấy config data location | Resolve/import location | Kiểm tra đường dẫn, classpath, packaging, working directory; quyết định có cần `optional:` |
| Lỗi YAML parser / indentation / duplicate key | Parse tài liệu | Sửa nội dung YAML và cú pháp |
| Không hỗ trợ định dạng được chỉ ra | Nạp tài liệu | Kiểm tra loại file và cách ghi location, loader/hint |
| Permission denied, IO error | Đọc tài nguyên | Kiểm tra quyền truy cập, mount, volume, đường dẫn |
| Failed to bind properties | Binding/conversion | Kiểm tra kiểu Java, biểu diễn số, boolean, date, duration |
| Validation failed / constraint violation | Validation | Sửa dữ liệu hoặc quy tắc validation |
| Missing placeholder | Resolve property/placeholder | Bổ sung nguồn property, default hợp lý hoặc điều kiện bật tính năng |
| BeanCreationException sau khi load config | Bean initialization | Xác định bean phụ thuộc property nào và vì sao khởi tạo thất bại |

Tên exception có thể thay đổi theo phiên bản, resolver và nguyên nhân gốc. Hãy đọc **cause chain**; một lỗi tổng thể “Application failed to start” không đủ để kết luận cần thêm `optional:`.

### Ví dụ về thư mục làm việc

Với:

~~~yaml
spring:
  config:
    import: "optional:file:./config/local.yml"
~~~

Một tiến trình chạy trong thư mục `/srv/app` sẽ tìm vị trí tương đối khác tiến trình được khởi chạy từ `/home/user`. Nếu file luôn “bị thiếu” trên container nhưng có trên máy developer, cần kiểm tra working directory, mount path và cách đóng gói file; `optional:` có thể làm tình trạng thiếu tài nguyên không gây lỗi ngay nhưng cũng khiến override mong muốn không được áp dụng.

### Ví dụ về classpath

Với:

~~~yaml
spring:
  config:
    import: "classpath:billing.yml"
~~~

Tài nguyên phải thật sự có trong classpath ứng dụng khi chạy, ví dụ được đóng gói từ `src/main/resources/billing.yml`. Việc file tồn tại ở thư mục làm việc bên ngoài JAR không đồng nghĩa nó tồn tại tại vị trí `classpath:billing.yml`.

## 8. Khi nào không nên dùng optional:?

### 8.1. Cấu hình là điều kiện bắt buộc của vận hành

Nếu hệ thống không được phép chạy thiếu thông tin quan trọng, hãy dùng import bắt buộc:

~~~yaml
spring:
  config:
    import: "file:/etc/myapp/required-integration.yml"
~~~

Ví dụ có thể là cấu hình kết nối tới hệ thống thanh toán, mapping bắt buộc hoặc chính sách bảo mật mà không có nó ứng dụng sẽ xử lý sai.

Tuy nhiên, **file có mặt không bảo đảm nội dung đúng**. Import bắt buộc chỉ kiểm tra được điều kiện tồn tại; validation và kiểm tra business invariant vẫn cần thiết.

### 8.2. Muốn che lỗi YAML hoặc lỗi quyền truy cập

Không nên chuyển:

~~~yaml
spring:
  config:
    import: "file:./config/required.yml"
~~~

thành:

~~~yaml
spring:
  config:
    import: "optional:file:./config/required.yml"
~~~

chỉ vì trước đó gặp lỗi không khởi động. Nếu file phải tồn tại, sửa cấu hình vận hành hoặc đường dẫn. Nếu file tồn tại nhưng lỗi cú pháp, `optional:` không khắc phục được nguyên nhân.

### 8.3. Mong mọi tài liệu thiếu đều bị bỏ qua

Spring Boot có thiết lập `spring.config.on-not-found=ignore` để xử lý rộng hơn lỗi không tìm thấy config data location. Có thể cấu hình chẳng hạn qua tham số khởi động:

~~~text
--spring.config.on-not-found=ignore
~~~

Đây là chính sách **rộng**, có thể che việc thiếu các nguồn bắt buộc. Ưu tiên `optional:` cho **từng vị trí thực sự tùy chọn**, vì nó ghi rõ ý định và giữ fail-fast cho những nguồn cần có.

Cũng cần phân biệt: cấu hình bỏ qua vị trí không tìm thấy vẫn **không biến lỗi parser, binding hoặc validation thành hợp lệ**.

## 9. Config tree và những nguồn cấu hình đặc thù

Spring Boot có thể import config tree từ một thư mục, thường hữu ích trong môi trường container hoặc Kubernetes:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/myapp/secrets/"
~~~

Với config tree, từng file bên trong thư mục có thể được xem như một property. Tiền tố `optional:` vẫn nói về **khả năng thiếu location**; nó không cho phép Spring tự bỏ qua mọi lỗi trong thư mục hoặc bảo đảm các secret quan trọng đã có.

Ví dụ một dịch vụ phụ trợ tùy chọn có thể dùng secret tree không bắt buộc tại development, nhưng production phải có cơ chế xác nhận các secret cần thiết.

Không nên tự suy luận mọi loader có cùng cách biểu diễn “resource not found”. Các location scheme khác nhau (file, classpath, configtree hay resolver do thư viện bổ sung) có quy tắc riêng về quyền truy cập và lỗi. Cần xem root cause khi thực tế gặp sự cố.

## 10. Config data là cấu hình khởi động, không phải file watcher

Một điểm liên quan: `spring.config.import` nạp nguồn cấu hình trong quy trình xử lý Config Data khi ứng dụng khởi động. Nó không mặc nhiên tạo cơ chế theo dõi file để mỗi thay đổi ở `local-overrides.yml` được áp dụng tức thì vào bean đã khởi tạo.

Nếu vận hành yêu cầu đổi cấu hình trong lúc chạy, phải thiết kế cơ chế refresh hoặc reconfiguration rõ ràng và xác định cách component sử dụng giá trị mới. Đó là vấn đề khác với việc có hay không có `optional:`.

Ví dụ:

1. Ứng dụng khởi động khi file override chưa tồn tại. Import tùy chọn được bỏ qua.
2. Sau đó người vận hành tạo file override trên máy.
3. Bean đã khởi tạo **không mặc nhiên cập nhật** chỉ vì file vừa xuất hiện.

Điều tương tự áp dụng cho file YAML được sửa sau khi khởi động.

## 11. Ví dụ hoàn chỉnh: tích hợp báo cáo tùy chọn

Giả sử một ứng dụng chỉ bật tính năng gửi báo cáo qua dịch vụ bên ngoài ở một số môi trường.

**Cấu hình chính** — `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/reporting.yml"

reporting:
  enabled: false
  timeout: 2s
~~~

**Cấu hình override tùy môi trường** — `./config/reporting.yml`, nếu có:

~~~yaml
reporting:
  enabled: true
  endpoint: "https://reports.example.invalid/api"
  timeout: 5s
~~~

**Kiểu cấu hình:**

~~~java
package example.reporting;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled,
        URI endpoint,
        Duration timeout
) {}
~~~

Đăng ký record cấu hình qua `@ConfigurationPropertiesScan` ở ứng dụng hoặc `@EnableConfigurationProperties(ReportingProperties.class)` trong cấu hình phù hợp.

**Điều kiện tạo bean tích hợp:**

~~~java
package example.reporting;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ReportingConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "reporting",
        name = "enabled",
        havingValue = "true"
    )
    ReportingClient reportingClient(ReportingProperties properties) {
        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                "reporting.endpoint is required when reporting.enabled=true"
            );
        }
        return new ReportingClient(
            properties.endpoint(),
            properties.timeout()
        );
    }
}
~~~

Ở đây `ReportingClient` là lớp tích hợp giả định với constructor nhận `URI` và `Duration`; cách gọi API thực tế phụ thuộc module.

Cách hiểu:

- Không có `reporting.yml`: import được bỏ qua; `reporting.enabled` có mặc định `false` nên bean tích hợp có thể không được đăng ký.
- Có `reporting.yml` hợp lệ: file được nạp, tính năng có thể bật, bean nhận `endpoint` và `timeout`.
- Có file nhưng YAML lỗi: startup có thể thất bại ở giai đoạn parse.
- Có file với `timeout: "unknown"`: startup có thể thất bại trong binding `Duration`.
- Có file bật tích hợp nhưng thiếu endpoint: đoạn kiểm tra ứng dụng làm startup thất bại có chủ đích khi tạo bean, tránh để tính năng chạy với cấu hình thiếu.

Đây là sự kết hợp giữa **location optional** và **ràng buộc hợp lệ khi feature được bật**. Cả hai cần có, vì “file tùy chọn” không có nghĩa “tích hợp đang bật có thể thiếu tham số bắt buộc”.

### Thứ tự ưu tiên trong ví dụ

Khi `reporting.yml` được import từ `application.yml`, những key trùng nhau như `reporting.enabled` hoặc `reporting.timeout` từ import có thể ghi đè giá trị trong tài liệu gọi import. Nhưng vẫn có thể có những nguồn externalized configuration khác có thứ tự ưu tiên cao hơn (ví dụ tham số dòng lệnh trong cấu hình mặc định), nên kết quả runtime phải xét toàn bộ nguồn cấu hình và quy tắc ưu tiên, không chỉ hai file YAML.

## 12. Thử nghiệm bốn tình huống với một cấu hình

Để tự quan sát, dùng cùng `application.yml` sau:

~~~yaml
spring:
  config:
    import: "optional:file:./config/test-extra.yml"

demo:
  message: "default"
  max-items: 10
~~~

Lần lượt chuẩn bị môi trường và quan sát:

**Tình huống 1: Không có file.**

Không tạo `./config/test-extra.yml`. Spring Boot có thể khởi động với `demo.message=default` và `demo.max-items=10`, giả sử không có ràng buộc khác.

**Tình huống 2: File hợp lệ.**

~~~yaml
demo:
  message: "from-import"
  max-items: 20
~~~

Import được nạp và có thể ghi đè hai key. Khi đọc giá trị thực tế, chú ý nếu có nguồn ưu tiên cao hơn như argument hoặc biến môi trường.

**Tình huống 3: File có lỗi YAML.**

~~~yaml
demo:
  message: Hello: again
~~~

Ứng dụng có thể dừng ở giai đoạn parse YAML. Lúc này `optional:` không phải giải pháp; cần quote chuỗi hoặc sửa cú pháp.

**Tình huống 4: File hợp lệ về YAML nhưng sai kiểu.**

~~~yaml
demo:
  max-items: "many"
~~~

Nếu ứng dụng có `@ConfigurationProperties` bind `maxItems` vào `int`, hãy quan sát lỗi conversion/binding. Nếu không có bean nào bind giá trị này, chỉ có một property dạng text có thể chưa gây lỗi ngay. Vì vậy, đừng kết luận “YAML đúng nghĩa là ứng dụng đã kiểm tra mọi property”; validation phải được đặt ở nơi sử dụng.

Để so sánh, thử bỏ `optional:` rồi chạy lại **tình huống 1**. Lúc này lỗi thiếu vị trí trở thành lỗi được phát hiện sớm. Sau đó phục hồi `optional:` nếu yêu cầu thật sự là nguồn tùy chọn.

## 13. Những ngộ nhận cần tránh

**Ngộ nhận 1 — “Có optional thì file hỏng cũng được bỏ qua.”**

Không đúng. File có mặt nhưng không parse được vẫn là cấu hình hỏng. Phải sửa nội dung hoặc loại bỏ nguồn không mong muốn.

**Ngộ nhận 2 — “Optional làm property trong file không bắt buộc.”**

Không đúng. Sự hiện diện của file và tính bắt buộc của property là hai yêu cầu độc lập. Property cần validation, default hoặc điều kiện sử dụng hợp lý.

**Ngộ nhận 3 — “Thiếu file thì Spring tự điền giá trị null/mặc định cho mọi key.”**

Không đúng. Bỏ qua import nghĩa là **nguồn ấy không đóng góp property**. Giá trị có thể đến từ nguồn khác, từ default code hoặc vắng mặt hoàn toàn; kết quả phụ thuộc cách cấu hình được sử dụng.

**Ngộ nhận 4 — “Sửa path bằng optional để app chạy là đã giải quyết.”**

Không hẳn. Nếu app chạy được nhưng dùng sai môi trường, endpoint, logging hoặc profile, việc thiếu override có thể là lỗi vận hành ẩn. Cần quyết định file đó bắt buộc hay tùy chọn dựa trên yêu cầu triển khai.

**Ngộ nhận 5 — “File có trên ổ đĩa thì classpath import phải thấy.”**

Không đúng. `classpath:` tìm trong classpath runtime; `file:` tìm qua hệ thống file theo quy tắc đường dẫn. Hai vị trí có thể chứa file cùng tên nhưng là hai tài nguyên khác nhau.

**Ngộ nhận 6 — “Đặt nháy là làm optional hoạt động.”**

Không đúng. Nháy trong YAML giúp ghi đúng scalar chứa dấu `:`. Ví dụ `"optional:file:./config/x.yml"` rõ ràng; tiền tố `optional:` mới quyết định chính sách vị trí bị thiếu. Nếu thiếu tiền tố, dù có nháy, location vẫn bắt buộc.

## 14. Quy trình quyết định trước khi dùng optional:

Khi thêm một nguồn cấu hình ngoài, hãy trả lời theo thứ tự:

1. **Nguồn này có cần tồn tại trong mọi môi trường không?** Nếu có, dùng import bắt buộc và bảo đảm file được deploy/mount đúng.
2. **Nếu nguồn vắng mặt, ứng dụng có hoạt động an toàn không?** Nếu có, có thể dùng `optional:` và khai báo các default đủ rõ.
3. **Nếu nguồn có mặt, có cần từ chối nội dung sai không?** Thông thường có. Không tìm cách nuốt lỗi parser/binding/validation.
4. **Các property bên trong có bắt buộc với feature được bật không?** Nếu có, validate theo điều kiện sử dụng, đặt ràng buộc ở nơi phù hợp.
5. **Đường dẫn có đúng với cách chạy không?** Kiểm tra `classpath:`, `file:`, working directory, packaging, container mount.
6. **Khi chạy nhiều môi trường, override và thứ tự ưu tiên có đúng ý định không?** Xác định nguồn nào được phép ghi đè, tránh cài nhầm endpoint production.
7. **Có cần cập nhật động không?** Nếu có, thiết kế riêng cơ chế refresh; `optional:` không giải quyết bài toán này.

Bảng kết luận nhanh:

| Yêu cầu | Lựa chọn |
| --- | --- |
| Cấu hình riêng cho máy phát triển, có cũng được không có cũng được | `optional:file:./config/local.yml` |
| Tài nguyên cấu hình buộc có trên production | `file:/etc/myapp/required.yml` không có `optional:` |
| Tài liệu classpath có thể chỉ xuất hiện ở một vài module | `optional:classpath:module-extra.yml` |
| Có file nhưng cú pháp YAML sai | Sửa file, không thêm `optional:` |
| Có file nhưng giá trị sai kiểu Java | Sửa cấu hình và kiểm tra Binder |
| Có file nhưng thiếu property quan trọng | Bổ sung property hoặc thiết kế default/validation rõ ràng |
| Muốn bỏ qua tất cả location not found | Chỉ cân nhắc `spring.config.on-not-found=ignore` khi hiểu rõ tác động rộng |

## 15. Ghi nhớ

`spring.config.import` cho phép tổ chức nguồn cấu hình thành nhiều tài liệu. Khi thêm `optional:` trước một location, bạn cho phép Spring Boot **tiếp tục khi không tìm thấy vị trí đó**. Quy tắc này hữu ích cho override file của máy phát triển hoặc nguồn tích hợp chỉ có ở một số môi trường.

Tuy nhiên, **tìm thấy tài nguyên nhưng nội dung không hợp lệ** là một vấn đề khác. Lỗi cú pháp YAML, lỗi đọc tài nguyên, lỗi chuyển đổi property và lỗi validation cần được xử lý theo nguyên nhân cụ thể. Hãy giữ nguyên tinh thần fail-fast khi cấu hình có mặt nhưng sai, và chỉ dùng import tùy chọn khi sự vắng mặt của chính nguồn ấy là điều đã được thiết kế từ trước.
