# Kích hoạt tài liệu bằng spring.config.activate.on-profile

## 1. Bài toán: một tệp cấu hình, nhiều điều kiện áp dụng

Trong ứng dụng Spring Boot, các môi trường phát triển, kiểm thử và production thường cần các giá trị cấu hình khác nhau. Ví dụ, môi trường phát triển dùng cơ sở dữ liệu cục bộ, còn production dùng máy chủ được quản lý và bật các chức năng giám sát.

Một cách quen thuộc là tách thành `application-dev.yml` và `application-prod.yml`. Tuy nhiên, đôi khi ta muốn **giữ nhiều nhóm cấu hình trong cùng một tệp** và chỉ áp dụng từng nhóm khi một profile nhất định đang hoạt động.

Spring Boot hỗ trợ **tài liệu cấu hình có điều kiện** (conditionally activated configuration document) thông qua khóa:

```yaml
spring:
  config:
    activate:
      on-profile: prod
```

Ý nghĩa là: **tài liệu chứa khai báo này chỉ được kích hoạt khi biểu thức profile khớp với tập profile hiện tại**.

Ví dụ, một tệp `application.yml` gồm nhiều tài liệu YAML:

```yaml
# Tài liệu 1: cấu hình chung
demo:
  message: "Cấu hình chung"
  retries: 1

---
# Tài liệu 2: chỉ áp dụng khi profile prod hoạt động
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: "Cấu hình production"
  retries: 5
```

Khi không kích hoạt `prod`, thuộc tính `demo.message` lấy từ tài liệu chung. Khi kích hoạt `prod`, tài liệu thứ hai cũng được áp dụng và có thể ghi đè giá trị của tài liệu trước nó.

**Phân biệt ngay từ đầu:** `spring.config.activate.on-profile` dùng để **kiểm tra điều kiện và chọn tài liệu cấu hình**. Nó không phải một lệnh để tự kích hoạt profile.

## 2. Tài liệu là gì, khác gì tệp?

Một **tệp** như `application.yml` có thể chứa **một hoặc nhiều tài liệu YAML**. Trong cùng tệp, mỗi dấu phân cách `---` bắt đầu một tài liệu mới.

Ví dụ:

```yaml
# Tài liệu A
demo:
  mode: common

---
# Tài liệu B
spring:
  config:
    activate:
      on-profile: dev

demo:
  mode: development

---
# Tài liệu C
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production
```

Cấu trúc trên là **một tệp vật lý** nhưng có **ba tài liệu cấu hình**:

| Tài liệu | Điều kiện kích hoạt | Giá trị khai báo |
| --- | --- | --- |
| A | Không có điều kiện | `demo.mode=common` |
| B | Profile `dev` hoạt động | `demo.mode=development` |
| C | Profile `prod` hoạt động | `demo.mode=production` |

Các tài liệu được xử lý riêng trong cơ chế Config Data. Một tài liệu không có điều kiện áp dụng bình thường; tài liệu có `on-profile` chỉ được xét khi điều kiện khớp.

Trong dạng YAML này, dấu `---` là **phân cách tài liệu**. Đừng nhầm nó với một khóa cấu hình hay một giá trị chuỗi.

Đối với tệp `.properties`, Spring Boot cũng hỗ trợ nhiều tài liệu bằng dấu phân cách dạng chú thích `#---`, nhưng cú pháp và quy tắc viết tệp khác YAML. Phần ví dụ dành riêng cho Properties sẽ xuất hiện bên dưới.

## 3. Cơ chế hoạt động của on-profile

Giả sử tệp `application.yml` chứa một tài liệu chung và một tài liệu có điều kiện:

```yaml
demo:
  title: "Ứng dụng bán hàng"
  connection-timeout: 10s

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  connection-timeout: 3s
  logging-level: warn
```

Khi chạy ứng dụng:

```bash
java -jar app.jar
```

Nếu không có nguồn nào kích hoạt profile `prod`, tài liệu thứ hai không đáp ứng điều kiện. Những giá trị có thể đọc được từ tệp trên là:

```text
demo.title              = Ứng dụng bán hàng
demo.connection-timeout = 10s
demo.logging-level      = không có giá trị trong hai tài liệu trên
```

Nếu chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

thì profile `prod` được kích hoạt; tài liệu thứ hai đủ điều kiện để đóng góp thuộc tính:

```text
demo.title              = Ứng dụng bán hàng
demo.connection-timeout = 3s
demo.logging-level      = warn
```

Giải thích:

1. Tài liệu chung cung cấp `demo.title` và thời gian chờ mặc định.
2. Tài liệu `on-profile: prod` chỉ có hiệu lực khi `prod` đang hoạt động.
3. Khi có hiệu lực, tài liệu sau trong tệp có thể ghi đè khóa trùng của tài liệu trước.
4. Những khóa không bị ghi đè vẫn giữ giá trị từ tài liệu chung, miễn là không có nguồn khác ưu tiên cao hơn.

Trong một ứng dụng thực tế, các nguồn như biến môi trường, thuộc tính JVM hoặc đối số dòng lệnh có thể tiếp tục ghi đè các giá trị từ Config Data. Điều kiện profile **quyết định tài liệu nào tham gia**, còn thứ tự ưu tiên **quyết định giá trị nào thắng khi cùng khóa xuất hiện ở nhiều nguồn**.

## 4. Cách kích hoạt profile mà điều kiện kiểm tra

Để tài liệu `on-profile: prod` được áp dụng, profile `prod` phải có mặt trong tập profile hoạt động. Có nhiều cách cấp profile hoạt động.

### 4.1. Qua đối số dòng lệnh

```bash
java -jar app.jar --spring.profiles.active=prod
```

Đối số nằm sau `-jar app.jar` và là thuộc tính của ứng dụng.

### 4.2. Qua thuộc tính hệ thống Java

```bash
java -Dspring.profiles.active=prod -jar app.jar
```

Tùy chọn `-D...` thuộc JVM nên đặt trước `-jar`.

### 4.3. Qua biến môi trường

Bash hoặc shell tương thích POSIX:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar app.jar
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

### 4.4. Qua cấu hình profile hợp lệ

Một tài liệu không phụ thuộc profile có thể khai báo lựa chọn profile, chẳng hạn:

```yaml
spring:
  profiles:
    active: dev
```

Nhưng khi triển khai, giá trị `spring.profiles.active` từ đối số dòng lệnh hoặc nguồn ưu tiên cao hơn vẫn có thể thay thế giá trị này.

**Không đặt `spring.profiles.active` vào một tài liệu đã được kích hoạt bởi `spring.config.activate.on-profile`.** Cách làm đó gây phụ thuộc vòng giữa “profile nào đang hoạt động” và “tài liệu nào được phép thiết lập profile”, nên Spring Boot giới hạn việc dùng các thuộc tính điều khiển profile bên trong tài liệu dành riêng cho profile.

## 5. on-profile không bật profile

Xem cấu hình:

```yaml
demo:
  region: default

---
spring:
  config:
    activate:
      on-profile: eu

demo:
  region: europe
```

Nhiều người đọc đoạn YAML này và nghĩ Spring Boot tự bật `eu` bởi vì nó được nhắc đến trong tệp. Thực tế, `on-profile: eu` chỉ đặt **điều kiện để tài liệu được sử dụng**.

Diễn giải đúng:

```text
Nếu profile eu đã hoạt động:
    tài liệu thứ hai được kích hoạt
Nếu profile eu không hoạt động:
    tài liệu thứ hai không được áp dụng
```

Không có câu lệnh nào trong ví dụ yêu cầu ứng dụng tự kích hoạt `eu`. Muốn chủ động chọn `eu`, sử dụng `spring.profiles.active=eu` hoặc cơ chế bổ sung profile như `spring.profiles.include`, profile groups, tùy bối cảnh.

Vì vậy:

| Khóa | Tác dụng |
| --- | --- |
| `spring.profiles.active` | Chọn profile hoạt động |
| `spring.profiles.include` | Bổ sung profile vào tập profile hoạt động |
| `spring.profiles.group.*` | Định nghĩa nhóm profile được mở rộng khi chọn profile nhóm |
| `spring.config.activate.on-profile` | Quy định điều kiện để **một tài liệu Config Data** được áp dụng |

Những thuộc tính này liên quan với nhau, nhưng không thay thế được nhau.

## 6. Biểu thức profile: hoặc, và, phủ định

`spring.config.activate.on-profile` nhận **biểu thức profile** (profile expression), không chỉ một tên đơn giản. Những toán tử quan trọng gồm:

- `|`: hoặc (OR);
- `&`: và (AND);
- `!`: phủ định (NOT);
- dấu ngoặc đơn để nhóm biểu thức.

### 6.1. Một trong hai profile

```yaml
spring:
  config:
    activate:
      on-profile: "dev | test"

demo:
  debug-tools-enabled: true
```

Tài liệu này được kích hoạt khi `dev` **hoặc** `test` phù hợp.

### 6.2. Cần đồng thời hai profile

```yaml
spring:
  config:
    activate:
      on-profile: "prod & cloud"

demo:
  connection-pool-size: 40
```

Tài liệu chỉ được kích hoạt khi điều kiện `prod` **và** `cloud` cùng được thỏa mãn.

Ví dụ lệnh khởi động:

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Trong tình huống trên, cả hai profile đều hoạt động nên biểu thức có thể khớp.

### 6.3. Phủ định profile

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"

demo:
  diagnostics-enabled: true
```

Biểu thức trên khớp khi profile `prod` không hoạt động theo ngữ nghĩa biểu thức profile của Spring.

Để diễn tả điều kiện phức tạp, dùng ngoặc:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (aws | gcp)"

demo:
  cloud-endpoint-enabled: true
```

Điều kiện yêu cầu `prod` cùng với **ít nhất một** trong hai profile `aws` hoặc `gcp`. Khi phối hợp `&` và `|`, nên dùng ngoặc rõ ràng, tránh nhập nhằng hoặc vi phạm cú pháp biểu thức.

Các chuỗi biểu thức trong ví dụ được đặt trong dấu nháy YAML. Việc dùng nháy kép đặc biệt cần thiết với biểu thức bắt đầu bằng `!` vì dấu chấm than có ý nghĩa riêng trong YAML.

## 7. Các biểu thức được kiểm tra như thế nào?

Giả sử tài liệu dùng:

```yaml
spring:
  config:
    activate:
      on-profile: "prod & (aws | gcp)"
```

Các tình huống:

| Profile đang hoạt động | Điều kiện khớp? | Lý do |
| --- | --- | --- |
| `prod` | Không | Thiếu `aws` và `gcp` |
| `aws` | Không | Thiếu `prod` |
| `prod,aws` | Có | Có `prod` và `aws` |
| `prod,gcp` | Có | Có `prod` và `gcp` |
| `prod,aws,gcp` | Có | Có `prod` và ít nhất một nhánh |
| `dev,aws` | Không | Thiếu `prod` |

Mục đích của biểu thức là kích hoạt cấu hình khi một **tổ hợp trạng thái** đã hiện diện. Nó không tự thêm tên profile vào tập hoạt động.

Có thể dùng biểu thức để tránh sao chép cấu hình của cùng một tính năng cho nhiều môi trường. Ví dụ, cấu hình chung cho `dev` và `test` có thể nằm trong một tài liệu có điều kiện `"dev | test"`.

Nếu cấu hình cần kích hoạt một tập profile phụ thuộc lẫn nhau, `spring.profiles.group` là cơ chế khác để định nghĩa quan hệ kích hoạt; `on-profile` chỉ đọc kết quả tập profile hoạt động.

## 8. Thứ tự tài liệu và ghi đè thuộc tính

Trong một tệp đa tài liệu được Spring Boot nạp theo cơ chế Config Data, **tài liệu xuất hiện sau có thể ghi đè giá trị cùng khóa ở tài liệu trước**, khi các tài liệu ấy đều được kích hoạt.

Ví dụ:

```yaml
# Tài liệu 1
demo:
  mode: base
  retries: 2

---
# Tài liệu 2
spring:
  config:
    activate:
      on-profile: "dev | test"

demo:
  mode: development
  retries: 1

---
# Tài liệu 3
spring:
  config:
    activate:
      on-profile: "prod | test"

demo:
  mode: hardened
```

Khi chạy với `--spring.profiles.active=dev`:

```text
demo.mode    = development
demo.retries = 1
```

Khi chạy với `--spring.profiles.active=prod`:

```text
demo.mode    = hardened
demo.retries = 2
```

Khi chạy với `--spring.profiles.active=test`, **cả tài liệu 2 và tài liệu 3** đều khớp. Trong ví dụ một tệp này, tài liệu 3 xuất hiện sau và có thể ghi đè `demo.mode`, còn `demo.retries` giữ giá trị từ tài liệu 2:

```text
demo.mode    = hardened
demo.retries = 1
```

Đừng lấy vị trí của một tài liệu trong một tệp để suy ra ưu tiên tuyệt đối so với tất cả tệp khác. Các tệp cấu hình ngoài JAR, tệp theo profile, `spring.config.import` và các nguồn như biến môi trường, đối số dòng lệnh cũng tham gia lựa chọn giá trị cuối cùng.

## 9. So sánh với application-prod.yml

Hai cách tổ chức sau thường phục vụ nhu cầu tương tự.

**Cách A: nhiều tệp theo profile**

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

Tệp `application-prod.yml`:

```yaml
demo:
  timeout: 5s
  audit: true
```

Tệp này thuộc nhóm Config Data dành cho profile `prod` theo quy tắc đặt tên tệp.

**Cách B: một tệp chứa nhiều tài liệu**

```yaml
# application.yml
demo:
  timeout: 30s
  audit: false

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  timeout: 5s
  audit: true
```

Cách B khai báo trực tiếp điều kiện trong tài liệu, nên tên tệp không cần hậu tố `-prod` để thể hiện điều kiện ấy.

| Khía cạnh | Tệp theo profile | Tài liệu on-profile |
| --- | --- | --- |
| Nơi đặt điều kiện | Quy ước tên `application-prod.yml` | Khóa `spring.config.activate.on-profile` |
| Cách tổ chức | Tách tệp riêng | Nhiều tài liệu trong cùng tệp |
| Điều kiện nhiều profile | Có thể phải tổ chức thêm tệp/cơ chế | Có thể viết biểu thức như `"dev | test"` |
| Có thể kết hợp? | Có | Có, nhưng cần hiểu thứ tự nguồn |

Không có lựa chọn nào tự động tốt hơn trong mọi dự án. Khi một cấu hình đủ lớn và thuộc riêng một môi trường, tệp riêng dễ quản lý. Khi một tập giá trị ngắn chỉ khác nhau theo vài tổ hợp profile, tài liệu có điều kiện có thể giúp nhìn được quan hệ ngay trong một tệp.

## 10. Dùng on-profile trong application.properties

Spring Boot còn hỗ trợ tài liệu cấu hình nhiều phần trong tệp Properties. Dấu phân cách tài liệu là `#---`.

Ví dụ:

```properties
# application.properties - tài liệu chung
demo.mode=default
demo.retries=2

#---
spring.config.activate.on-profile=dev
demo.mode=development
demo.retries=1

#---
spring.config.activate.on-profile=prod
demo.mode=production
demo.retries=5
```

Cách hoạt động về mặt điều kiện tương tự YAML: tài liệu chứa `spring.config.activate.on-profile=prod` được áp dụng khi `prod` hoạt động.

Phân biệt:

- Trong YAML, `---` là dấu phân cách tài liệu.
- Trong Properties, Spring Boot nhận dạng dòng chú thích `#---` làm dấu phân cách theo quy tắc riêng.
- Dấu phân cách Properties cần viết đúng dạng, không có khoảng trắng ở đầu dòng và gồm đúng ba dấu gạch ngang. Không viết nhầm `# ----` hoặc thêm dấu cách bên trong.
- Dạng đa tài liệu này được cơ chế nạp Config Data của Spring Boot hỗ trợ; không nên mặc định mọi thư viện đọc `.properties` hoặc mọi cách nạp `@PropertySource` đều hiểu các dấu phân cách như Spring Boot.

Sử dụng định dạng mà nhóm phát triển hiểu rõ nhất và áp dụng nhất quán.

## 11. Ví dụ hoàn chỉnh với mã Java

### 11.1. Tạo cấu hình

Tạo `src/main/resources/application.yml`:

```yaml
# Cấu hình chung
demo:
  service: catalog
  message: "running with base config"
  retries: 2
  feature-enabled: false

---
spring:
  config:
    activate:
      on-profile: dev

demo:
  message: "running in development"
  retries: 1
  feature-enabled: true

---
spring:
  config:
    activate:
      on-profile: prod

demo:
  message: "running in production"
  retries: 5
```

Cấu hình gồm ba tài liệu. Tài liệu chung không có điều kiện; hai tài liệu tiếp theo dành cho `dev` và `prod`.

### 11.2. Viết thành phần quan sát Environment

Trong một ứng dụng Spring Boot có `@SpringBootApplication`, tạo thành phần:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConditionalDocumentPrinter implements ApplicationRunner {

    private final Environment environment;

    public ConditionalDocumentPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles = "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("demo.service = "
                + environment.getProperty("demo.service"));

        System.out.println("demo.message = "
                + environment.getProperty("demo.message"));

        System.out.println("demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));

        System.out.println("demo.feature-enabled = "
                + environment.getProperty("demo.feature-enabled", Boolean.class));
    }
}
```

Các phương thức `Environment#getProperty` đọc giá trị có hiệu lực. Dạng đọc có tham số `Integer.class` hoặc `Boolean.class` cho phép Spring chuyển chuỗi cấu hình thành kiểu phù hợp.

### 11.3. Trường hợp không kích hoạt dev hoặc prod

Chạy:

```bash
java -jar app.jar
```

Nếu không có nguồn nào thêm `dev` hoặc `prod`, các giá trị từ ba tài liệu này được chọn như sau:

```text
demo.service = catalog
demo.message = running with base config
demo.retries = 2
demo.feature-enabled = false
```

Không có tài liệu theo điều kiện `dev` hoặc `prod` nào khớp.

### 11.4. Trường hợp dev

Chạy:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Kết quả từ các thuộc tính minh họa:

```text
demo.service = catalog
demo.message = running in development
demo.retries = 1
demo.feature-enabled = true
```

Tài liệu `dev` bổ sung hoặc ghi đè các khóa của tài liệu chung.

### 11.5. Trường hợp prod

Chạy:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả:

```text
demo.service = catalog
demo.message = running in production
demo.retries = 5
demo.feature-enabled = false
```

Giá trị `demo.feature-enabled=false` đến từ tài liệu chung vì tài liệu `prod` không khai báo khóa đó.

### 11.6. Ghi đè bằng đối số ứng dụng

Thử:

```bash
java -jar app.jar --spring.profiles.active=prod --demo.retries=9
```

Kết quả `demo.retries` là `9`: đối số dòng lệnh có độ ưu tiên cao hơn Config Data trong trường hợp chạy Spring Boot thông thường. Điều kiện `prod` vẫn khớp, nhưng **giá trị cuối cùng cho khóa cụ thể** có thể đến từ một nguồn ưu tiên cao hơn.

Đây là sự khác nhau giữa **tài liệu được kích hoạt** và **nguồn giá trị chiến thắng**.

## 12. on-profile kết hợp với profile groups và include

Trong ứng dụng có nhiều profile, tập profile hoạt động có thể được mở rộng bằng `spring.profiles.include` hoặc `spring.profiles.group.*`.

Ví dụ:

```yaml
spring:
  profiles:
    group:
      prod:
        - proddb
        - observability

---
spring:
  config:
    activate:
      on-profile: "prod & observability"

demo:
  tracing-enabled: true
```

Khi khởi chạy với:

```bash
java -jar app.jar --spring.profiles.active=prod
```

nhóm `prod` sẽ kích hoạt thêm các profile thành viên, trong đó có `observability`. Do đó tài liệu chứa biểu thức `"prod & observability"` có thể được áp dụng.

Điều cần hiểu là:

1. Việc chọn và mở rộng profile được thực hiện bằng cơ chế kích hoạt profile.
2. `spring.config.activate.on-profile` kiểm tra tập profile đã được xác định.
3. Các thuộc tính của tài liệu phù hợp sau đó tham gia Config Data.

**Giới hạn quan trọng:** không chuyển `spring.profiles.group`, `spring.profiles.active` hoặc `spring.profiles.include` xuống tài liệu có `on-profile`. Những thuộc tính định nghĩa hoặc thay đổi tập profile nên nằm trong tài liệu không dành riêng cho profile theo quy tắc của Spring Boot.

## 13. Kết hợp điều kiện profile với Config Data Import

Tài liệu có điều kiện có thể chứa cấu hình phụ thuộc môi trường, bao gồm khai báo nạp nguồn cấu hình khác trong các trường hợp được hỗ trợ bởi Config Data.

Ví dụ:

```yaml
demo:
  region: local

---
spring:
  config:
    activate:
      on-profile: prod
    import: "optional:file:./config/prod-overrides.properties"

demo:
  region: production
```

Ở ví dụ này, tài liệu thứ hai chỉ được kích hoạt khi `prod` phù hợp. Khi tài liệu được kích hoạt, cơ chế Config Data có thể xử lý khai báo import của nó để nạp tệp bổ sung.

Nếu tệp `./config/prod-overrides.properties` tồn tại và chứa:

```properties
demo.region=external-production
```

thì giá trị được import có ưu tiên hơn giá trị cùng khóa trong tài liệu đã khai báo import trong quan hệ trực tiếp đó, miễn là không có nguồn khác ưu tiên cao hơn ghi đè.

Nếu không có tệp và import được đánh dấu `optional:`, riêng việc thiếu tài nguyên này không buộc ứng dụng thất bại theo cơ chế thiếu vị trí import.

Trong ứng dụng có nhiều tài liệu, nhiều vị trí và profile khác nhau, cần đánh giá toàn bộ thứ tự Config Data thay vì suy luận rằng mọi tệp được import đều thắng mọi tệp khác.

## 14. Những trường hợp dễ nhầm

### 14.1. Đặt active trong tài liệu được kích hoạt

Ví dụ không đúng:

```yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: audit
```

Tài liệu đã phụ thuộc profile `prod` nhưng lại cố thay đổi tập profile hoạt động. Spring Boot không cho phép sử dụng `spring.profiles.active` trong tài liệu dành riêng cho profile như vậy.

Nếu muốn `prod` kéo theo `audit`, định nghĩa profile group trong tài liệu không phụ thuộc profile:

```yaml
spring:
  profiles:
    group:
      prod:
        - audit
```

### 14.2. Bỏ dấu phân cách YAML

Ví dụ:

```yaml
demo:
  mode: base
spring:
  config:
    activate:
      on-profile: prod
demo:
  mode: production
```

Đây không phải cách hợp lệ để tạo hai tài liệu YAML riêng. Việc lặp lại khóa gốc `demo` trong cùng tài liệu còn gây vấn đề phân tích YAML. Hãy tách chúng bằng `---` nếu muốn tài liệu chung và tài liệu có điều kiện khác nhau.

### 14.3. Ghi on-profile ngoài tài liệu cần điều kiện

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: prod

demo:
  mode: production

---
demo:
  feature-enabled: true
```

Chỉ **tài liệu trước dấu `---`** bị ràng buộc bởi `on-profile: prod`. Tài liệu sau dấu phân cách không tự kế thừa điều kiện của tài liệu trước. Nếu cũng cần điều kiện, khai báo `on-profile` trong tài liệu thứ hai.

### 14.4. Không dùng dấu nháy cho biểu thức bắt đầu bằng dấu chấm than

Trong YAML, biểu thức:

```yaml
spring:
  config:
    activate:
      on-profile: "!prod"
```

là cách biểu diễn rõ ràng cho điều kiện phủ định. Nếu bỏ dấu nháy và bắt đầu giá trị bằng `!`, YAML có thể hiểu đó là cú pháp thẻ (tag) thay vì một chuỗi, dẫn đến lỗi phân tích tài liệu.

### 14.5. Nghĩ rằng một tài liệu được kích hoạt sẽ luôn thắng biến môi trường

Nếu một tài liệu production đặt:

```yaml
demo:
  timeout: 5s
```

nhưng biến môi trường hoặc đối số dòng lệnh cung cấp giá trị khác với độ ưu tiên cao hơn, kết quả cuối cùng của `demo.timeout` có thể không phải `5s`. Điều kiện kích hoạt tài liệu và thứ tự ưu tiên nguồn là hai khái niệm khác nhau.

### 14.6. Nghĩ rằng profile nào cũng phải có tệp application-<profile>.yml

Một tài liệu có `on-profile: prod` vẫn có thể nằm trong `application.yml` cơ sở. Ngoài ra profile còn được sử dụng bởi điều kiện `@Profile` trong mã Spring. Do đó, “profile đang hoạt động” và “tệp mang hậu tố profile có tồn tại” không phải cùng một điều kiện.

### 14.7. Cho rằng hai tài liệu không có điều kiện phụ thuộc nhau

Mỗi tài liệu được đánh giá với điều kiện của chính nó. Một tài liệu không có `on-profile` có thể áp dụng trong mọi lần chạy, nhưng điều đó không có nghĩa tài liệu đứng trước hoặc đứng sau nó tự động có cùng điều kiện.

## 15. Phân biệt với @Profile trong mã Java

Hai cơ chế cùng dựa trên profile nhưng xử lý các đối tượng khác nhau:

| Cơ chế | Đối tượng được điều khiển | Ví dụ |
| --- | --- | --- |
| `spring.config.activate.on-profile` | Một **tài liệu Config Data** | Nạp khóa `demo.mode` chỉ khi `prod` phù hợp |
| `@Profile` | Bean hoặc cấu hình của Spring Framework | Tạo một bean chỉ khi `prod` phù hợp |

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ExternalClientConfiguration {

    @Bean
    @Profile("prod")
    public ExternalClient externalClient() {
        return new ExternalClient("https://api.example.invalid");
    }
}

class ExternalClient {
    private final String url;

    ExternalClient(String url) {
        this.url = url;
    }

    public String getUrl() {
        return url;
    }
}
```

`@Profile("prod")` điều kiện hóa việc đăng ký bean. Một tài liệu YAML có `spring.config.activate.on-profile: prod` điều kiện hóa dữ liệu cấu hình. Cùng một profile `prod` có thể làm cả hai điều kiện đúng, nhưng hai chức năng có phạm vi khác nhau.

Không cần tạo bean chỉ để dùng tài liệu cấu hình có điều kiện, và không cần có tài liệu `on-profile` để dùng `@Profile`.

## 16. Quan sát profile và cấu hình có hiệu lực

Khi không chắc vì sao một tài liệu được áp dụng, hãy kiểm tra profile hoạt động và một số khóa cụ thể. Ví dụ:

```java
import java.util.Arrays;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileDocumentInspector implements ApplicationRunner {

    private final Environment environment;

    public ProfileDocumentInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Profiles: "
                + Arrays.toString(environment.getActiveProfiles()));

        System.out.println("Mode: "
                + environment.getProperty("demo.mode", "<không có>"));

        System.out.println("Retries: "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

Đoạn mã trên cho biết tập profile thực tế và giá trị đang được ứng dụng nhận. Nếu giá trị không đúng như dự đoán, hãy kiểm tra lần lượt:

1. Profile phù hợp có được kích hoạt thực sự không?
2. Tài liệu có dấu `---` đúng vị trí không?
3. Biểu thức `on-profile` có khớp và có đặt dấu nháy phù hợp không?
4. Có nhiều tài liệu cùng kích hoạt và ghi đè một khóa không?
5. Có tệp Config Data ở vị trí ưu tiên cao hơn hoặc tệp được import không?
6. Có đối số dòng lệnh, biến môi trường hoặc thuộc tính JVM đang ghi đè không?

Trong môi trường kiểm soát, Spring Boot Actuator `env` cũng có thể hỗ trợ quan sát các nguồn thuộc tính khi endpoint được cấu hình cho phép truy cập. Chỉ kiểm tra các khóa không nhạy cảm và bảo vệ thông tin cấu hình triển khai.

## 17. Bài tập tự kiểm tra

Cho tệp `application.yml`:

```yaml
# Tài liệu 1
app:
  name: example
  message: base
  retries: 2
  metrics: false

---
# Tài liệu 2
spring:
  config:
    activate:
      on-profile: "dev | test"

app:
  message: non-production
  metrics: true

---
# Tài liệu 3
spring:
  config:
    activate:
      on-profile: "prod & cloud"

app:
  message: production-cloud
  retries: 7

---
# Tài liệu 4
spring:
  config:
    activate:
      on-profile: "!prod"

app:
  retries: 1
```

Giả sử không có các nguồn cấu hình khác ghi đè. Hãy xác định thuộc tính nào có hiệu lực trong ba tình huống.

### Trường hợp A: chỉ dev

```bash
java -jar app.jar --spring.profiles.active=dev
```

Các tài liệu 1, 2 và 4 phù hợp. Giá trị kỳ vọng:

```text
app.name    = example
app.message = non-production
app.retries = 1
app.metrics = true
```

Giải thích: tài liệu 2 thay `message` và `metrics`; tài liệu 4 đứng sau và ghi đè `retries`.

### Trường hợp B: prod và cloud

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Tài liệu 1 và 3 phù hợp. Tài liệu 2 không khớp, tài liệu 4 không khớp vì `prod` đang hoạt động.

```text
app.name    = example
app.message = production-cloud
app.retries = 7
app.metrics = false
```

### Trường hợp C: chỉ prod

```bash
java -jar app.jar --spring.profiles.active=prod
```

Tài liệu 3 không khớp vì thiếu `cloud`; tài liệu 4 không khớp vì `prod` hoạt động. Tài liệu 1 cung cấp các giá trị:

```text
app.name    = example
app.message = base
app.retries = 2
app.metrics = false
```

Thử thay biểu thức của tài liệu 3 bằng `"prod | cloud"` rồi suy luận lại kết quả: với biểu thức OR, chỉ cần một trong hai profile hoạt động là tài liệu có thể được kích hoạt.

## 18. Ghi nhớ

- `spring.config.activate.on-profile` là **điều kiện kích hoạt một tài liệu Config Data**, không phải thuộc tính tự bật profile.
- Trong YAML, phân cách các tài liệu bằng `---`. Mỗi tài liệu có thể có điều kiện riêng.
- Giá trị `on-profile` có thể là tên profile hoặc biểu thức với `!`, `&`, `|` và dấu ngoặc; nên đặt biểu thức trong chuỗi được nháy để tránh lỗi cú pháp YAML.
- Những tài liệu không thỏa điều kiện không đóng góp thuộc tính; những tài liệu được kích hoạt tham gia thứ tự ưu tiên Config Data.
- Trong cùng một tệp đa tài liệu, tài liệu áp dụng xuất hiện sau có thể ghi đè khóa trùng trong tài liệu đứng trước.
- Không khai báo `spring.profiles.active`, `spring.profiles.include` hoặc profile groups bên trong tài liệu đã ràng buộc bằng `on-profile`.
- Cần phân biệt `spring.config.activate.on-profile` với tệp `application-prod.yml`, với `@Profile` trên bean và với `spring.profiles.active`.
- Để chẩn đoán, kiểm tra profile thực tế bằng `Environment#getActiveProfiles()` và kiểm tra từng giá trị bằng `Environment#getProperty()`.
