# Bổ sung profile bằng spring.profiles.include

## 1. Vì sao ứng dụng cần bổ sung profile?

Trong Spring Boot, **profile** giúp chọn cấu hình và thành phần ứng dụng phù hợp với từng hoàn cảnh chạy. Một ứng dụng có thể có profile `dev` cho phát triển, `test` cho thử nghiệm và `prod` cho triển khai chính thức. Ngoài những môi trường đó, ứng dụng cũng có thể cần các nhóm chức năng cấu hình dùng chung, chẳng hạn `audit` (ghi nhận hoạt động), `metrics` (đo lường) hay `shared-db` (kết nối cơ sở dữ liệu chung).

Giả sử khi chạy ở môi trường production, ứng dụng phải kích hoạt đồng thời:

- `prod`: các thông số dành cho production;
- `metrics`: cấu hình đo lường;
- `audit`: một số thành phần ghi nhận sự kiện.

Có thể liệt kê tất cả bằng `spring.profiles.active=prod,metrics,audit`. Tuy nhiên, nếu `metrics` và `audit` là các cấu hình luôn cần cho ứng dụng, người vận hành phải nhớ khai báo chúng ở mọi lệnh khởi chạy.

**`spring.profiles.include` giải quyết nhu cầu bổ sung profile:** các profile được khai báo bởi `include` sẽ được thêm vào tập profile đang hoạt động. Nó hữu ích để kích hoạt một hoặc nhiều profile dùng chung mà vẫn cho phép môi trường triển khai chọn profile chính qua `spring.profiles.active`.

Mô hình ban đầu:

```text
Lệnh chạy:                --spring.profiles.active=prod
application.yml:          spring.profiles.include=[metrics, audit]

Tập profile hoạt động:   metrics, audit, prod
                         ↑ thêm vào     ↑ được chọn khi chạy
```

Mỗi profile trong tập hoạt động có thể kích hoạt các tài liệu cấu hình tương ứng và các thành phần Spring được gắn điều kiện `@Profile`.

## 2. spring.profiles.include là gì?

`spring.profiles.include` là một thuộc tính cấu hình của Spring Boot, dùng để **thêm tên profile** vào danh sách profile hoạt động trong quá trình khởi tạo ứng dụng.

Ví dụ trong `src/main/resources/application.yml`:

```yaml
spring:
  profiles:
    include:
      - metrics
      - audit
```

Cách tương đương trong `application.properties`:

```properties
spring.profiles.include=metrics,audit
```

Hai cách trên biểu diễn một danh sách gồm `metrics` và `audit`. Chúng là **tên profile**, không phải đường dẫn đến tệp cấu hình. Spring Boot dùng các tên này để kích hoạt cơ chế profile và tìm những tài liệu cấu hình thích hợp, nếu có.

Ví dụ ứng dụng có thể có:

```text
src/main/resources/
├── application.yml
├── application-metrics.yml
├── application-audit.yml
└── application-prod.yml
```

Trong trường hợp này:

- `application.yml` cung cấp cấu hình không phụ thuộc profile và khai báo `include`.
- `application-metrics.yml` chứa cấu hình áp dụng khi profile `metrics` hoạt động.
- `application-audit.yml` chứa cấu hình áp dụng khi profile `audit` hoạt động.
- `application-prod.yml` chứa cấu hình áp dụng khi profile `prod` hoạt động.

Một profile **vẫn có thể được kích hoạt ngay cả khi không tồn tại tệp `application-<profile>.yml` tương ứng**. Ví dụ `@Profile("audit")` vẫn có thể điều khiển việc đăng ký bean. Vì thế không nên coi profile chỉ là công tắc đọc tệp.

## 3. Thực hành đơn giản: thêm profile dùng chung

Giả sử ứng dụng có hai tệp sau.

Tệp `application.yml`:

```yaml
spring:
  profiles:
    include:
      - metrics

demo:
  mode: normal
  metrics-enabled: false
```

Tệp `application-metrics.yml`:

```yaml
demo:
  metrics-enabled: true
  metrics-export-interval: 15s
```

Khi chạy:

```bash
java -jar app.jar
```

Profile `metrics` được thêm vào tập profile hoạt động. Khi không có nguồn cấu hình ưu tiên cao hơn ghi đè, các giá trị là:

| Thuộc tính | Giá trị | Nguồn giải thích |
| --- | --- | --- |
| `demo.mode` | `normal` | Từ `application.yml` |
| `demo.metrics-enabled` | `true` | Từ `application-metrics.yml` |
| `demo.metrics-export-interval` | `15s` | Từ `application-metrics.yml` |

Chú ý: `application-metrics.yml` không được nạp vì tên tệp xuất hiện trực tiếp trong thuộc tính `include`. Spring Boot **kích hoạt profile `metrics`**, sau đó cơ chế Config Data có thể nạp tài liệu dành cho profile đó.

Nếu bạn bỏ `spring.profiles.include` và không kích hoạt `metrics` bằng cách khác, cấu hình theo profile `metrics` sẽ không còn được chọn chỉ vì tệp tồn tại.

## 4. Phân biệt spring.profiles.active và spring.profiles.include

Hai thuộc tính có ý nghĩa khác nhau.

| Thuộc tính | Vai trò chính | Ví dụ |
| --- | --- | --- |
| `spring.profiles.active` | Chọn các profile hoạt động, thường được quyết định khi triển khai | `prod` |
| `spring.profiles.include` | Bổ sung các profile vào tập đang hoạt động | `metrics,audit` |

Ví dụ:

```yaml
# application.yml
spring:
  profiles:
    include: metrics
```

Chạy ứng dụng với:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Ứng dụng có thể kích hoạt cả `metrics` lẫn `prod`. Việc chọn `prod` qua dòng lệnh **không loại bỏ** `metrics` đã được bổ sung bằng `include`.

So sánh với việc khai báo `spring.profiles.active` ở hai nguồn:

```properties
# application.properties
spring.profiles.active=dev
```

```bash
java -jar app.jar --spring.profiles.active=prod
```

Trong trường hợp chỉ có hai cách đặt `active` như trên, giá trị ở dòng lệnh có ưu tiên cao hơn nên `prod` thay cho lựa chọn `dev` trong tệp. Trong khi đó, `include` bổ sung profile theo cơ chế riêng, không chỉ là một giá trị `active` thứ hai.

Không nên hiểu `include` là lệnh “luôn thắng tất cả”. Nó chỉ bổ sung profile; **các thuộc tính ứng dụng cuối cùng** vẫn tuân theo thứ tự ưu tiên của các nguồn cấu hình.

## 5. Thứ tự profile và kết quả khi thuộc tính bị trùng

Trong cơ chế xử lý profile của Spring Boot, **profile được include được thêm trước profile đang hoạt động**. Thứ tự có ý nghĩa khi nhiều tài liệu cấu hình theo profile chứa cùng một khóa; với các tài liệu profile tương đương, profile xuất hiện sau có thể ghi đè profile xuất hiện trước.

Ví dụ sử dụng ba tệp:

```yaml
# application.yml
spring:
  profiles:
    include: metrics

demo:
  message: "base"
```

```yaml
# application-metrics.yml
demo:
  message: "metrics"
  monitoring: true
```

```yaml
# application-prod.yml
demo:
  message: "prod"
  endpoint: "https://example.invalid"
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Danh sách profile theo ví dụ gồm `metrics` và `prod`, với `metrics` được bổ sung trước `prod`. Trong cấu trúc tệp đơn giản này, kết quả dự kiến là:

```text
demo.message    = prod
demo.monitoring = true
demo.endpoint   = https://example.invalid
```

Lý giải:

1. `application.yml` đặt giá trị chung `demo.message=base`.
2. `application-metrics.yml` đặt `demo.message=metrics`.
3. `application-prod.yml` đặt `demo.message=prod` và trong tình huống này có ưu tiên để ghi đè khóa trùng.
4. `demo.monitoring` chỉ có trong cấu hình `metrics` nên vẫn được giữ.

**Cần phân biệt ưu tiên giữa các profile với ưu tiên giữa các nguồn thuộc tính.** Một biến môi trường, thuộc tính JVM hoặc đối số dòng lệnh có độ ưu tiên cao hơn Config Data vẫn có thể ghi đè `demo.message`. Nếu có thêm tệp cấu hình bên ngoài JAR hoặc các khai báo import, thứ tự Config Data cần được xét đầy đủ.

## 6. Nơi hợp lệ để khai báo spring.profiles.include

Một giới hạn quan trọng của Spring Boot là:

**`spring.profiles.include` chỉ được khai báo trong tài liệu cấu hình không dành riêng cho profile (non-profile-specific document).**

Ví dụ hợp lệ trong `application.yml` cơ sở:

```yaml
spring:
  profiles:
    include:
      - metrics
      - audit
```

Hoặc dùng `application.properties` không gắn profile:

```properties
spring.profiles.include=metrics,audit
```

Không nên đặt `spring.profiles.include` vào tệp `application-prod.yml` để chỉ khi `prod` hoạt động mới include thêm `metrics`:

```yaml
# KHÔNG HỢP LỆ: application-prod.yml
spring:
  profiles:
    include: metrics
```

Tương tự, không đặt nó trong một tài liệu YAML được kích hoạt bằng `spring.config.activate.on-profile`:

```yaml
# KHÔNG HỢP LỆ: tài liệu profile-specific
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics
```

Đây không chỉ là vấn đề ưu tiên giá trị; Spring Boot hạn chế việc dùng các thuộc tính điều khiển kích hoạt profile bên trong các tài liệu vốn chỉ được lựa chọn sau khi profile đã xác định. Việc khai báo sai có thể khiến quá trình khởi động báo lỗi cấu hình, ví dụ một ngoại lệ liên quan tới thuộc tính không hợp lệ trong tài liệu dành cho profile.

Nếu muốn dùng một tên profile mang ý nghĩa nhóm để kích hoạt những profile khác, hãy xem **profile groups** ở phần sau, thay vì đặt `include` có điều kiện vào `application-prod.yml`.

## 7. Dùng profile groups khi muốn một profile kéo theo nhiều profile khác

Giả sử người vận hành chỉ muốn chọn `prod`, còn ứng dụng cần tự động kích hoạt thêm `proddb` và `prodmq` mỗi khi `prod` được chọn.

Spring Boot cung cấp **profile groups** để diễn đạt mối quan hệ này:

```yaml
# application.yml
spring:
  profiles:
    group:
      prod:
        - proddb
        - prodmq
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Nhóm `prod` được mở rộng, khiến `proddb` và `prodmq` cũng hoạt động.

Sự khác nhau:

- `spring.profiles.include=metrics`: bổ sung `metrics` khi tài liệu không phụ thuộc profile chứa thuộc tính này được áp dụng.
- `spring.profiles.group.prod=proddb,prodmq`: định nghĩa rằng **khi chọn `prod`**, Spring Boot kích hoạt thêm các profile thành viên của nhóm.

Ví dụ muốn có `metrics` trong mọi cách chạy, đồng thời bật những profile đặc thù khi dùng `prod`:

```yaml
spring:
  profiles:
    include: metrics
    group:
      prod:
        - proddb
        - prodmq
```

Khi chạy với `--spring.profiles.active=prod`, các profile liên quan gồm `metrics`, `prod`, `proddb` và `prodmq`. Khi chạy với `--spring.profiles.active=dev`, `metrics` vẫn có thể được bổ sung, còn nhóm `prod` không tự được kích hoạt chỉ vì đã được định nghĩa.

Giống `spring.profiles.include`, khai báo `spring.profiles.group` phải nằm ở tài liệu không dành riêng cho profile. Đây là một cấu hình định nghĩa **quan hệ kích hoạt**, không phải một tài liệu profile đã được chọn.

## 8. spring.profiles.include được xử lý theo từng PropertySource

Một đặc điểm cần biết là `spring.profiles.include` được Spring Boot xử lý **theo từng nguồn thuộc tính (PropertySource)**. Vì vậy các nguồn có thể đóng góp thêm profile vào tập hoạt động.

Ví dụ một tệp không phụ thuộc profile chứa:

```yaml
spring:
  profiles:
    include: audit
```

Trong khi một nguồn cấu hình khác phù hợp ở giai đoạn khởi tạo cung cấp:

```text
spring.profiles.include=metrics
```

Điểm cần phân biệt với `spring.profiles.active`: đối với `active`, thông thường nguồn có ưu tiên cao hơn chọn giá trị có hiệu lực cho thuộc tính đó; đối với `include`, Spring Boot có cơ chế xử lý đóng góp từ các nguồn.

Tuy nhiên, đừng dựa vào suy đoán rằng **hai khai báo cùng khóa trong cùng một tài liệu sẽ tự nối thành danh sách**. Cách định nghĩa danh sách trong YAML/Properties phải hợp lệ. Với các tài liệu hoặc nguồn khác nhau, cần kiểm tra tập profile thực tế và quy tắc Config Data áp dụng.

Khi sử dụng `application.yml` và biến môi trường, luôn giữ một cách biểu diễn rõ ràng, tránh khai báo cùng khóa nhiều lần không cần thiết. Mục tiêu của `include` là giúp thấy profile nào phải được bổ sung, không tạo nhiều lớp cấu hình khó theo dõi.

## 9. Kích hoạt profile qua biến môi trường và dòng lệnh

Có thể đặt các thuộc tính profile bằng những nguồn khởi tạo sớm quen thuộc. Ví dụ đặt profile chính qua dòng lệnh:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Trong khi `application.yml` chứa:

```yaml
spring:
  profiles:
    include: metrics
```

Cách khác là cấp profile chính qua biến môi trường trong Bash:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

Có thể cung cấp `spring.profiles.include` từ một nguồn khởi tạo phù hợp, chẳng hạn:

```bash
java -jar app.jar --spring.profiles.include=metrics,audit
```

Ví dụ này bổ sung hai profile từ đối số ứng dụng. Khi áp dụng trong môi trường có nhiều nguồn cấu hình, hãy kiểm tra tập profile hoạt động thực tế.

**Lưu ý về dấu phẩy và shell:** giá trị `metrics,audit` trong một thuộc tính danh sách phải đến ứng dụng nguyên vẹn; các công cụ triển khai, shell và dạng cấu hình có quy tắc riêng về dấu nháy, khoảng trắng và biểu diễn danh sách.

## 10. spring.profiles.include ảnh hưởng gì đến @Profile?

Spring Framework hỗ trợ điều kiện `@Profile` trên bean hoặc cấu hình. Spring Boot kích hoạt profile rồi sử dụng tập profile hoạt động ấy trong lúc tạo ứng dụng.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class AuditConfiguration {

    @Bean
    @Profile("audit")
    public AuditRecorder auditRecorder() {
        return new AuditRecorder();
    }
}

class AuditRecorder {
    public void record(String message) {
        System.out.println("AUDIT: " + message);
    }
}
```

Giả sử `application.yml` khai báo:

```yaml
spring:
  profiles:
    include: audit
```

Profile `audit` được kích hoạt, vì vậy bean `auditRecorder` có thể được đăng ký mà người chạy ứng dụng không cần thêm `--spring.profiles.active=audit`.

Nếu `audit` không nằm trong tập profile hoạt động và không được kích hoạt bằng cơ chế khác, điều kiện `@Profile("audit")` không được đáp ứng.

Điểm này cho thấy `include` có thể ảnh hưởng cả **cấu trúc bean được tạo** chứ không chỉ cách nạp `application-audit.yml`.

Khi dùng `@Profile` với các điều kiện phức tạp, hãy nhớ rằng biểu thức như `@Profile("prod & audit")` kiểm tra đồng thời các profile. Việc include có thể khiến điều kiện trước đây chưa đúng trở thành đúng.

## 11. Cách xác nhận các profile đã được kích hoạt

Trong quá trình học hoặc chẩn đoán, có thể in danh sách profile từ `Environment`:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ActiveProfilesPrinter implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfilesPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("demo.mode = "
                + environment.getProperty("demo.mode", "<không có>"));
    }
}
```

Khi `application.yml` khai báo `include=metrics,audit` và chạy với `--spring.profiles.active=prod`, phần in profile sẽ thể hiện các tên profile có hiệu lực, trong đó có các profile đã được thêm và profile được chọn khi khởi động.

Danh sách này là cách quan sát đáng tin cậy hơn việc suy đoán chỉ qua tên tệp. Một profile có thể tồn tại nhưng không có tệp profile riêng, hoặc một nguồn cấu hình khác có thể làm thay đổi tập profile hoạt động.

Nếu muốn tìm lý do vì sao một thuộc tính nhận giá trị bất ngờ, dùng thêm `environment.getProperty("demo.mode")` hoặc các công cụ chẩn đoán Config Data phù hợp. Tuy nhiên, không ghi giá trị nhạy cảm vào nhật ký khi kiểm tra cấu hình thật.

## 12. Một ví dụ hoàn chỉnh: profile môi trường và profile chức năng

Giả sử ứng dụng quản lý đơn hàng có bộ tệp:

```text
src/main/resources/
├── application.yml
├── application-logging.yml
├── application-audit.yml
├── application-dev.yml
└── application-prod.yml
```

`application.yml`:

```yaml
spring:
  profiles:
    include:
      - logging
      - audit

orders:
  retries: 1
  storage: local
  logging-enabled: false
  audit-enabled: false
```

`application-logging.yml`:

```yaml
orders:
  logging-enabled: true
```

`application-audit.yml`:

```yaml
orders:
  audit-enabled: true
```

`application-dev.yml`:

```yaml
orders:
  storage: in-memory
  retries: 1
```

`application-prod.yml`:

```yaml
orders:
  storage: postgres
  retries: 5
```

Chạy ứng dụng phát triển:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Với các tệp đã nêu và không có nguồn khác ghi đè:

```text
orders.storage         = in-memory
orders.retries         = 1
orders.logging-enabled = true
orders.audit-enabled   = true
```

Chạy ứng dụng production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả:

```text
orders.storage         = postgres
orders.retries         = 5
orders.logging-enabled = true
orders.audit-enabled   = true
```

Cấu hình về môi trường thay đổi theo `dev` hoặc `prod`. Các chức năng khai báo trong `include` vẫn được bổ sung cho cả hai lần chạy.

Nếu sau này chỉ production mới cần `audit`, không nên vội đưa `spring.profiles.include=audit` vào `application-prod.yml`. Có thể xem xét profile group để chỉ kích hoạt `audit` khi chọn `prod`, hoặc quyết định lại cách tổ chức cấu hình cho dễ quản lý.

## 13. Các nhầm lẫn cần tránh

### 13.1. Nhầm include với việc thay thế active

Sai: “Nếu thêm `spring.profiles.include=metrics` thì `prod` sẽ bị bỏ.”

Đúng: `include` **bổ sung** `metrics`; lựa chọn profile chính của môi trường vẫn có thể hoạt động đồng thời.

### 13.2. Nhầm include với khai báo import tệp

`spring.profiles.include=metrics` kích hoạt một **profile**, còn `spring.config.import=classpath:feature.yml` chỉ định một **tài nguyên cấu hình** cần nạp. Hai thuộc tính phục vụ hai mục đích khác nhau.

Việc có một tệp tên `application-metrics.yml` làm cho cấu hình theo profile dễ hình dung, nhưng `include` không yêu cầu bạn viết đường dẫn đến tệp ấy.

### 13.3. Đặt include trong tệp theo profile

Không đặt `spring.profiles.include` vào `application-prod.yml` hoặc tài liệu kích hoạt bằng `spring.config.activate.on-profile=prod`. Hãy chuyển khai báo vào tài liệu không phụ thuộc profile, hoặc dùng profile group nếu cần kích hoạt có điều kiện.

### 13.4. Dự đoán rằng profile include luôn ghi đè profile active

Profile được include được thêm trước profile đang hoạt động. Với tình huống Config Data điển hình, profile đang hoạt động được chọn sau có thể ghi đè khóa trùng của profile include. Thứ tự ưu tiên của cả hệ thống còn chịu ảnh hưởng bởi vị trí tệp, import và những nguồn cấu hình khác.

### 13.5. Cho rằng một profile chỉ hoạt động khi có tệp cấu hình riêng

Profile không chỉ là hậu tố tên tệp. Nó còn ảnh hưởng đến điều kiện `@Profile` và các tài liệu được kích hoạt bởi biểu thức profile.

### 13.6. Dùng include cho quan hệ phụ thuộc chỉ ở một môi trường

Nếu `proddb` chỉ cần khi chạy `prod`, khai báo `spring.profiles.include=proddb` trong `application.yml` sẽ bổ sung nó cả khi chạy `dev`. Profile groups phù hợp hơn khi mục đích là “chọn `prod` thì đi kèm `proddb`”.

### 13.7. Trông chờ include vô hiệu hóa một profile

`spring.profiles.include` là cơ chế bổ sung. Nó không cung cấp một cú pháp loại bỏ profile đang hoạt động. Cần thiết kế danh sách profile và điều kiện bean rõ ràng, thay vì mong giá trị `include` có thể phủ định một profile ở nguồn khác.

## 14. Bài tập: tự dự đoán kết quả

### Bài tập A: tính tập profile

Tệp `application.yml`:

```yaml
spring:
  profiles:
    include:
      - cache
      - audit
```

Khởi chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Câu hỏi:

1. Các profile nào được kích hoạt?
2. Có cần tệp `application-cache.yml` để profile `cache` tồn tại không?
3. Bean gắn `@Profile("audit")` có thể được đăng ký không?

Đáp án gợi ý:

1. Tập profile chứa `cache`, `audit` và `prod` trong ví dụ.
2. Không nhất thiết; profile là trạng thái kích hoạt, còn tệp theo profile là một cách cung cấp Config Data.
3. Có, nếu không có điều kiện hoặc lỗi khác ngăn đăng ký bean.

### Bài tập B: tính giá trị cấu hình

Cho:

```yaml
# application.yml
spring:
  profiles:
    include: common

demo:
  color: gray
  retries: 2
```

```yaml
# application-common.yml
demo:
  color: blue
  enabled: true
```

```yaml
# application-prod.yml
demo:
  color: red
  retries: 5
```

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Khi không có tệp và nguồn khác ghi đè, hãy dự đoán:

| Khóa | Giá trị kỳ vọng | Lý do |
| --- | --- | --- |
| `demo.color` | `red` | Profile `prod` ghi đè giá trị của `common` |
| `demo.retries` | `5` | Tệp `application-prod.yml` ghi đè cấu hình chung |
| `demo.enabled` | `true` | Tệp `application-common.yml` cung cấp giá trị |

Thử thêm:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.color=black
```

Kết quả `demo.color` là `black` vì đối số dòng lệnh thông thường có độ ưu tiên cao hơn các tệp Config Data.

### Bài tập C: xác định khai báo không hợp lệ

Xem tài liệu:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: audit
```

Câu hỏi: Vì sao không nên dùng cấu hình này?

Đáp án: đây là một tài liệu chỉ được kích hoạt theo profile `prod`, trong khi `spring.profiles.include` chỉ được dùng ở tài liệu **không dành riêng cho profile**. Với nhu cầu “prod kéo theo audit”, có thể định nghĩa:

```yaml
spring:
  profiles:
    group:
      prod:
        - audit
```

trong một tài liệu không phụ thuộc profile, rồi kích hoạt `prod` khi khởi chạy.

## 15. Ghi nhớ

- `spring.profiles.include` **thêm profile** vào tập profile hoạt động của ứng dụng Spring Boot.
- Khác với `spring.profiles.active` dùng để chọn profile chính, `include` cho phép cấu hình những profile cần bổ sung ngay cả khi môi trường chọn `dev` hay `prod`.
- Có thể dùng danh sách YAML hoặc danh sách phân tách bằng dấu phẩy trong tệp Properties.
- Profile được include được thêm **trước** profile đang hoạt động; điều này ảnh hưởng tới ghi đè thuộc tính khi có tài liệu cấu hình theo profile.
- **Chỉ khai báo `spring.profiles.include` trong tài liệu không dành riêng cho profile.** Không đặt ở `application-prod.yml` hoặc trong tài liệu dùng `spring.config.activate.on-profile`.
- Nếu cần “một profile kéo theo nhiều profile khác khi chính profile ấy được chọn”, hãy dùng **profile groups**.
- Một profile có thể kích hoạt tệp cấu hình theo profile và điều kiện `@Profile`; nó không bắt buộc phải có tệp riêng.
- Kiểm chứng tập profile bằng `Environment#getActiveProfiles()` và kiểm chứng từng giá trị bằng `Environment#getProperty()`.
