# Ưu tiên của dữ liệu nhập so với tài liệu khai báo import

## 1. Vấn đề: cùng một thuộc tính xuất hiện ở hai tài liệu cấu hình

Khi học Spring Boot Externalized Configuration, chúng ta thường bắt đầu với `application.yml` hoặc `application.properties`. Tuy nhiên, một ứng dụng thực tế có thể chia cấu hình thành nhiều tệp: cấu hình chung trong `application.yml`, cấu hình riêng cho một chức năng ở `feature.yml` và cấu hình triển khai trong tệp bên ngoài JAR.

Spring Boot cung cấp `spring.config.import` để **nạp thêm dữ liệu cấu hình (Config Data)** từ một tài nguyên khác. Khi hai tài liệu cùng khai báo một thuộc tính, câu hỏi quan trọng là:

**Thuộc tính trong tài liệu được import có ưu tiên cao hơn hay thấp hơn thuộc tính trong tài liệu khai báo `spring.config.import`?**

Quy tắc cốt lõi của cơ chế Config Data là:

> **Giá trị từ tài liệu được import có ưu tiên cao hơn giá trị cùng khóa trong tài liệu đã khai báo import đó.**

Hãy xem cấu hình:

```yaml
# application.yml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  message: "Từ application.yml"
  retries: 2
```

Và tệp thứ hai:

```yaml
# feature.yml
demo:
  message: "Từ feature.yml"
```

Sau khi nạp Config Data, nếu không có nguồn cấu hình khác ghi đè, kết quả là:

| Khóa | Giá trị có hiệu lực | Giải thích |
| --- | --- | --- |
| `demo.message` | `Từ feature.yml` | Tài liệu được import thắng tài liệu khai báo import |
| `demo.retries` | `2` | Tệp import không có khóa này, nên giữ giá trị từ `application.yml` |

Điều này cho thấy Spring Boot phân giải **theo từng thuộc tính**. Việc import không có nghĩa toàn bộ thuộc tính của tài liệu gốc bị xóa hoặc bị thay thế đồng loạt.

## 2. Tài liệu khai báo import và tài liệu được import là gì?

Để diễn đạt rõ, cần phân biệt hai vai trò:

- **Tài liệu khai báo import (importing document):** tài liệu cấu hình chứa khóa `spring.config.import`, ví dụ `application.yml`.
- **Tài liệu được import (imported document):** tài nguyên cấu hình được tìm và nạp dựa trên giá trị của `spring.config.import`, ví dụ `feature.yml`.

Trong ví dụ trên, `application.yml` là tài liệu khai báo; `feature.yml` là tài liệu được import. Thứ tự này là quan hệ **giữa các tài liệu** trong cơ chế Config Data, không phải thứ tự các dòng YAML.

Spring Boot xử lý các khai báo import khi phát hiện chúng. Tài liệu được import được đưa vào tập Config Data gần tài liệu đã kích hoạt việc import và có mức ưu tiên để **ghi đè giá trị cùng khóa của tài liệu khai báo**.

Sơ đồ ý tưởng:

```text
application.yml
    |
    | spring.config.import=classpath:feature.yml
    v
feature.yml

Khi cả hai cùng khai báo demo.message:

feature.yml
    > application.yml
```

Ký hiệu `>` chỉ mức ưu tiên cao hơn khi giải quyết cùng một khóa, chứ không chỉ thứ tự đọc trên đĩa.

Nếu `feature.yml` không khai báo `demo.message`, Spring Boot tiếp tục dùng giá trị phù hợp từ `application.yml` hoặc một nguồn cấu hình khác.

## 3. Vì sao giá trị từ import được ưu tiên hơn?

Cơ chế import giúp bạn xây dựng cấu hình theo lớp. Tài liệu chính định nghĩa các giá trị chung và chỉ ra nơi cần lấy cấu hình bổ sung; tài liệu được import có thể cung cấp những giá trị cụ thể hơn.

Ví dụ một ứng dụng xử lý đơn hàng có cấu hình mặc định:

```yaml
# application.yml
spring:
  config:
    import: "classpath:payment-defaults.yml"

payment:
  currency: "VND"
  timeout: 30s
  provider: "basic"
```

Tệp được import:

```yaml
# payment-defaults.yml
payment:
  timeout: 10s
  provider: "sandbox"
```

Giá trị cuối cùng có thể hiểu như sau:

```text
payment.currency  = VND      (chỉ có ở tài liệu khai báo)
payment.timeout   = 10s      (tài liệu import ghi đè 30s)
payment.provider  = sandbox  (tài liệu import ghi đè basic)
```

Tính năng này thuận tiện khi cấu hình bổ sung được quản lý ở vị trí riêng. Tuy nhiên, nên đặt tên và tổ chức các tệp sao cho người đọc dự đoán được nguồn nào đang áp dụng, nhất là khi nhiều môi trường triển khai sử dụng các tệp khác nhau.

Đừng suy luận rằng mọi tệp có tên chứa từ “defaults” đương nhiên có ưu tiên thấp: **tên tệp không quyết định ưu tiên**. Quan hệ nạp qua `spring.config.import` và các quy tắc Config Data mới là điều quyết định.

## 4. Ví dụ thực hành với application.properties và imported.properties

Có thể kiểm chứng nguyên tắc bằng một ứng dụng Spring Boot đơn giản.

### 4.1. Chuẩn bị tệp

Đặt hai tệp trong thư mục tài nguyên:

```text
src/main/resources/
├── application.properties
└── imported.properties
```

Tệp `application.properties`:

```properties
spring.config.import=classpath:imported.properties

demo.source=main
demo.mode=from-main
demo.timeout=45
```

Tệp `imported.properties`:

```properties
demo.mode=from-import
demo.timeout=15
demo.feature-enabled=true
```

### 4.2. Đọc giá trị bằng Environment

Thêm một thành phần in đúng các thuộc tính cần quan sát:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigImportPrinter implements ApplicationRunner {

    private final Environment environment;

    public ConfigImportPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("demo.source = "
                + environment.getProperty("demo.source"));
        System.out.println("demo.mode = "
                + environment.getProperty("demo.mode"));
        System.out.println("demo.timeout = "
                + environment.getProperty("demo.timeout", Integer.class));
        System.out.println("demo.feature-enabled = "
                + environment.getProperty("demo.feature-enabled", Boolean.class));
    }
}
```

Đây là ví dụ đọc `Environment`, không cần tạo Controller hoặc API HTTP. Trong ứng dụng thực tế, cũng có thể liên kết các thuộc tính với lớp `@ConfigurationProperties`.

### 4.3. Chạy và giải thích

Giả sử ứng dụng đã được đóng gói thành `app.jar`:

```bash
java -jar app.jar
```

Các dòng in từ thành phần minh họa:

```text
demo.source = main
demo.mode = from-import
demo.timeout = 15
demo.feature-enabled = true
```

Bảng phân tích:

| Thuộc tính | application.properties | imported.properties | Kết quả |
| --- | --- | --- | --- |
| `demo.source` | `main` | Không có | `main` |
| `demo.mode` | `from-main` | `from-import` | `from-import` |
| `demo.timeout` | `45` | `15` | `15` |
| `demo.feature-enabled` | Không có | `true` | `true` |

Chúng ta có hai kiểu kết hợp: **ghi đè** khi cùng khóa xuất hiện và **bổ sung** khi một khóa chỉ tồn tại trong một nguồn. Đây là cơ sở để lý giải phần lớn tình huống import đơn giản.

## 5. Vị trí import trong YAML không quyết định thứ tự ưu tiên

Một nhầm lẫn thường gặp là cho rằng nếu viết `spring.config.import` ở đầu tệp, giá trị nhập sẽ bị những dòng bên dưới ghi đè; nếu viết cuối tệp, giá trị nhập sẽ thắng. Cách hiểu ấy không đúng với một tài liệu YAML thông thường.

Hai cách trình bày sau đều khai báo import trong cùng một tài liệu:

```yaml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  mode: "main"
```

Và:

```yaml
demo:
  mode: "main"

spring:
  config:
    import: "classpath:feature.yml"
```

Nếu `feature.yml` có `demo.mode=feature`, giá trị được import vẫn thắng `demo.mode=main` trong tài liệu khai báo. Spring Boot không áp dụng quy tắc “dòng nào xuất hiện sau thì thắng” cho thứ tự key trong một đối tượng YAML.

Cần phân biệt **vị trí khóa trong tài liệu** với **thứ tự ưu tiên giữa các tài liệu cấu hình**.

Khi một tệp YAML gồm nhiều tài liệu được phân cách bằng `---`, mỗi tài liệu lại tham gia vào thứ tự Config Data theo ngữ cảnh của nó. Do đó phải xem tài liệu nào khai báo import và có điều kiện kích hoạt profile hay không, thay vì chỉ coi toàn bộ tệp vật lý là một khối duy nhất.

## 6. Import không có ưu tiên cao hơn tất cả các nguồn cấu hình

Quy tắc “import thắng tài liệu khai báo” là một quy tắc **cục bộ trong quá trình nạp Config Data**. Nó không có nghĩa tệp import được đặt ở vị trí cao nhất của mọi `PropertySource` mà ứng dụng có.

Ví dụ vẫn dùng hai tệp:

```properties
# application.properties
spring.config.import=classpath:imported.properties
demo.mode=from-main
```

```properties
# imported.properties
demo.mode=from-import
```

Khi chạy:

```bash
java -jar app.jar --demo.mode=from-cli
```

Giá trị của `demo.mode` là:

```text
from-cli
```

Đối số dòng lệnh thông thường `--demo.mode=from-cli` có độ ưu tiên cao hơn các giá trị thuộc nhóm Config Data, kể cả tệp được import.

Với những nguồn thường gặp trong Spring Boot 3.x, mô hình khái quát từ cao xuống thấp là:

```text
Đối số dòng lệnh --demo.mode=...
    >
Nguồn SPRING_APPLICATION_JSON
    >
Thuộc tính hệ thống Java -Ddemo.mode=...
    >
Biến môi trường DEMO_MODE
    >
Config Data được import: imported.properties
    >
Tài liệu Config Data khai báo import: application.properties
```

Hai dòng cuối chỉ đúng cho **quan hệ tài liệu khai báo/import đang xét**. Nếu ứng dụng có thêm các tệp profile, vị trí ngoài JAR, nhóm vị trí cấu hình hoặc tài liệu khác, phải xem thêm quy tắc ưu tiên của toàn bộ Config Data. Không nên nâng sơ đồ minh họa này thành thứ tự tuyệt đối cho mọi tệp của mọi ứng dụng.

Điểm cần nhớ: có **hai tầng quyết định**. Tầng thứ nhất là thứ tự giữa các nguồn như dòng lệnh, JVM, biến môi trường và Config Data. Tầng thứ hai là thứ tự **bên trong Config Data**, bao gồm tài liệu nào đã khai báo import và tài liệu nào được nạp bởi import ấy.

## 7. Tài liệu được import có thể nằm ngoài JAR

Import không bị giới hạn ở tệp trong classpath. Chẳng hạn, bạn có thể có:

```text
deploy/
├── app.jar
└── config/
    └── overrides.properties
```

Trong `application.properties` đã đóng gói trong JAR:

```properties
spring.config.import=optional:file:./config/overrides.properties
demo.mode=default
demo.timeout=30
```

Tệp `deploy/config/overrides.properties`:

```properties
demo.mode=external
```

Khi thư mục làm việc là `deploy/` và chạy:

```bash
java -jar app.jar
```

giá trị `demo.mode` sẽ là `external` còn `demo.timeout` vẫn là `30`, nếu không có nguồn ưu tiên cao hơn.

Các thành phần trong vị trí import:

- `file:` biểu thị tài nguyên trên hệ thống tệp.
- `./config/overrides.properties` là đường dẫn tương đối với thư mục làm việc trong ví dụ này.
- `optional:` cho phép ứng dụng tiếp tục nếu vị trí import không tồn tại, thay vì coi riêng việc thiếu vị trí ấy là lỗi bắt buộc.

Nếu xóa hoặc không cung cấp `overrides.properties`, ví dụ với `optional:` vẫn có thể dùng `demo.mode=default` từ `application.properties`.

**`optional:` không thay đổi thứ tự ưu tiên khi tệp có mặt.** Nó chỉ thay đổi cách xử lý việc không tìm thấy tài nguyên cần nạp. Khi đã nạp thành công, `overrides.properties` vẫn ghi đè cùng khóa trong tài liệu khai báo import.

Chú ý không nhầm việc không tìm thấy tệp với lỗi cú pháp trong tệp có tồn tại: `optional:` không làm cho nội dung cấu hình sai định dạng trở nên hợp lệ.

## 8. Import theo vị trí cố định và import tương đối

Có hai cách tham chiếu đáng lưu ý:

```properties
spring.config.import=classpath:feature.properties
```

Cách này chỉ rõ tài nguyên trên classpath.

```properties
spring.config.import=feature.properties
```

Một vị trí import không có tiền tố cố định như `classpath:` hoặc `file:` có thể được giải quyết **tương đối với vị trí của tài liệu khai báo import** theo cơ chế Config Data. Do đó, `feature.properties` không mặc nhiên có nghĩa là “tìm trong thư mục làm việc hiện tại”.

Ví dụ một tệp cấu hình ở vị trí `file:./config/application.properties` khai báo:

```properties
spring.config.import=feature.properties
```

Spring Boot giải quyết import tương đối so với vị trí cấu hình đó, nên tệp `./config/feature.properties` là ứng viên tự nhiên. Nếu muốn chỉ định một tài nguyên cụ thể với vị trí rõ ràng, dùng tiền tố `file:` hoặc `classpath:`.

**Quan hệ ưu tiên không đổi vì cách viết đường dẫn:** một khi tài liệu được import thành công, giá trị cùng khóa trong nó vẫn có ưu tiên hơn giá trị thuộc tài liệu khai báo import.

## 9. Khi import gặp cấu hình theo profile

Cấu hình theo profile làm cho bài toán nhiều tài liệu hơn. Ví dụ:

```text
src/main/resources/
├── application.yml
├── feature.yml
└── feature-prod.yml
```

Tệp `application.yml`:

```yaml
spring:
  config:
    import: "classpath:feature.yml"

demo:
  mode: "main"
  region: "local"
```

Tệp `feature.yml`:

```yaml
demo:
  mode: "feature-base"
```

Tệp `feature-prod.yml`:

```yaml
demo:
  mode: "feature-prod"
```

Khi chạy ứng dụng với profile `prod`:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Cơ chế Config Data có xét đến các biến thể theo profile của tài nguyên được import. Với tập tệp đơn giản này và không có nguồn khác ghi đè:

```text
demo.mode   = feature-prod
demo.region = local
```

Giải thích:

- `feature.yml` cung cấp giá trị cấu hình import cơ sở.
- `feature-prod.yml` cung cấp biến thể ứng với profile `prod`.
- `demo.region` chỉ có ở `application.yml` nên vẫn sử dụng giá trị `local`.

Bây giờ giả sử xuất hiện thêm `application-prod.yml` hoặc các tài liệu YAML có điều kiện `spring.config.activate.on-profile`. Khi đó số tài liệu tham gia tăng lên và phải xét toàn bộ thứ tự Config Data, bao gồm profile và vị trí; không thể chỉ nói “bất cứ thứ gì được import đều thắng mọi cấu hình profile”.

Một quy tắc thực hành hữu ích là: khi gặp kết quả khó hiểu, trước tiên liệt kê **những tài liệu thực sự đã được nạp**, sau đó tìm khóa xung đột và xét ưu tiên của các tài liệu ấy. Việc một tệp tồn tại trên ổ đĩa chưa chứng minh rằng nó đã được nạp.

## 10. Import lồng nhau và import lặp

Một tệp được import có thể tiếp tục khai báo `spring.config.import` để nạp thêm tài nguyên. Ví dụ:

```text
application.properties
    |
    v
feature.properties
    |
    v
feature-overrides.properties
```

Tệp chính:

```properties
# application.properties
spring.config.import=classpath:feature.properties
demo.mode=main
```

Tệp thứ hai:

```properties
# feature.properties
spring.config.import=classpath:feature-overrides.properties
demo.mode=feature
```

Tệp thứ ba:

```properties
# feature-overrides.properties
demo.mode=override
```

Với chuỗi tài liệu đơn giản này, kết quả `demo.mode` là `override`: tài liệu ngoài cùng nạp `feature.properties`, sau đó `feature.properties` nạp `feature-overrides.properties`; mỗi quan hệ import áp dụng cùng quy tắc ghi đè.

Spring Boot cũng có cơ chế tránh nhập cùng một tài nguyên nhiều lần chỉ vì nó được khai báo lặp. Vì vậy không nên trông chờ rằng viết lại cùng một đường dẫn import hai lần sẽ làm thay đổi thứ tự ưu tiên hoặc tạo hai bản sao cấu hình.

Khi cần tổ chức nhiều tệp, đặt quan hệ import rõ ràng và tránh thiết kế vòng phụ thuộc hoặc chuỗi import quá sâu. Một tập tệp nhỏ, có mục đích dễ hiểu sẽ thuận tiện hơn khi chẩn đoán vì người đọc theo dõi được nguồn của mỗi thuộc tính.

## 11. Phân biệt thứ tự import với thứ tự các nhóm cấu hình khác

Câu “tài liệu nhập có ưu tiên cao hơn tài liệu khai báo import” rất hữu ích, nhưng chỉ giải quyết trực tiếp **cặp tài liệu có quan hệ import**. Nó chưa đủ để trả lời mọi câu hỏi kiểu “tệp nào thắng?” trong hệ thống có nhiều cấu hình.

Ví dụ:

```text
application.yml
    import: feature.yml

./config/application.yml
application-prod.yml
./config/application-prod.yml

Biến môi trường, thuộc tính JVM, đối số dòng lệnh
```

Ngoài quan hệ import, những yếu tố sau còn có thể thay đổi giá trị được chọn:

1. **Vị trí cấu hình:** tài nguyên đóng gói trong classpath và tài nguyên bên ngoài JAR tham gia quy tắc ưu tiên vị trí của Config Data.
2. **Profile:** các tài liệu áp dụng cho profile đang hoạt động có thể ghi đè những thuộc tính của tài liệu chung.
3. **Nhiều tài liệu trong một tệp:** ký hiệu `---` có thể tách một tệp YAML thành các tài liệu riêng; mỗi tài liệu có thể có điều kiện kích hoạt hoặc khai báo import.
4. **Nguồn ngoài Config Data:** đối số dòng lệnh, biến môi trường và thuộc tính JVM có thể ghi đè các giá trị từ tài liệu cấu hình.
5. **Nguồn cấu hình do ứng dụng bổ sung:** thư viện hoặc mã khởi tạo có thể đưa thêm `PropertySource` vào `Environment`.

Do đó không nên mô tả mọi tình huống bằng một quy tắc duy nhất: “tệp nào được import sau cùng đều thắng tất cả”. Để biết giá trị chính xác, cần xem **tập nguồn thực tế** mà Spring Boot xây dựng và cách chúng được sắp xếp.

## 12. Các lỗi thường gặp

### 12.1. Nghĩ rằng tài liệu chính luôn có ưu tiên cao hơn

Lập luận sai:

> `application.yml` là tệp chính, vì vậy giá trị trong đó phải thắng tệp `feature.yml` mà nó nạp.

Thực tế với một tài liệu trực tiếp khai báo import, giá trị cùng khóa trong tệp nhập **được ưu tiên hơn** giá trị trong tài liệu khai báo. Tên tệp “chính” không tạo ra ưu tiên đặc biệt đối với quan hệ này.

### 12.2. Nghĩ import giống sao chép văn bản vào đầu tệp

Import là hoạt động nạp tài liệu vào hệ thống Config Data, không phải thao tác dán nguyên văn nội dung tệp vào một vị trí trong văn bản YAML hoặc Properties. Vì vậy việc đặt `spring.config.import` trước hay sau một khóa khác trong cùng tài liệu không quyết định thứ tự ghi đè.

### 12.3. Nghĩ mọi giá trị của tài liệu gốc đều mất

Nếu tài liệu nhập không khai báo một khóa, giá trị ở tài liệu khai báo vẫn có thể được dùng. Việc ghi đè xảy ra trên **khóa trùng nhau**, không phải xóa toàn bộ tập thuộc tính của tài liệu gốc.

### 12.4. Dùng optional rồi tưởng import bị hạ ưu tiên

`optional:` cho phép bỏ qua một vị trí không tồn tại trong tình huống được hỗ trợ. Nó không chuyển giá trị của tệp tồn tại sang mức ưu tiên thấp hơn tài liệu khai báo.

### 12.5. Không xét đối số dòng lệnh

Giả sử `feature.properties` định nghĩa `demo.mode=feature` và ứng dụng chạy với `--demo.mode=cli`. Giá trị có hiệu lực là `cli` vì đối số dòng lệnh có ưu tiên cao hơn nhóm Config Data trong cấu hình Spring Boot thông thường.

### 12.6. Chỉ kiểm tra tệp có tồn tại

Tệp có thể tồn tại nhưng không được nạp do đường dẫn import sai, profile không hoạt động hoặc vị trí tìm kiếm khác dự đoán. Hãy xác nhận tài liệu thực sự được đưa vào `Environment` trước khi kết luận về mức ưu tiên.

## 13. Cách quan sát giá trị và nguồn thuộc tính

Cách đơn giản nhất để kiểm chứng bài học là đọc chính khóa đang xảy ra xung đột:

```java
String mode = environment.getProperty("demo.mode");
System.out.println("demo.mode = " + mode);
```

Nếu muốn tìm nguồn đã cung cấp giá trị trong quá trình điều tra, có thể duyệt các `PropertySource` từ `ConfigurableEnvironment`:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class ConfigSourceInspector implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public ConfigSourceInspector(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "demo.mode";

        System.out.println("Effective value: "
                + environment.getProperty(key));

        for (PropertySource<?> source : environment.getPropertySources()) {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        }
    }
}
```

Các `PropertySource` được duyệt theo thứ tự mà `Environment` dùng để tìm thuộc tính. Giá trị từ nguồn phù hợp có ưu tiên cao hơn thường là giá trị được chọn. Tên nguồn thường giúp nhận ra tài liệu cấu hình tương ứng, ví dụ một nguồn được tạo từ `application.properties` hoặc `imported.properties`.

Đoạn mã trên chỉ nên dùng với khóa minh họa không nhạy cảm. Đừng in toàn bộ biến môi trường, mật khẩu, mã truy cập hay các giá trị bí mật ra log. Trong ứng dụng có Spring Boot Actuator, endpoint `env` có thể hỗ trợ điều tra khi được cấu hình và bảo vệ thích hợp.

**Lưu ý:** phương pháp quan sát cho biết kết quả có hiệu lực và nguồn thuộc tính đang có, nhưng không thay thế việc hiểu nguyên tắc import trong Config Data.

## 14. Bài tập: dự đoán thuộc tính có hiệu lực

Cho hai tệp:

```yaml
# application.yml
spring:
  config:
    import: "classpath:module.yml"

demo:
  name: "main"
  retries: 3
  enabled: false
```

```yaml
# module.yml
demo:
  name: "module"
  enabled: true
  region: "asia"
```

**Câu hỏi 1:** Nếu ứng dụng chỉ dùng hai tệp trên, kết quả của bốn khóa là gì?

| Khóa | Đáp án |
| --- | --- |
| `demo.name` | `module` |
| `demo.retries` | `3` |
| `demo.enabled` | `true` |
| `demo.region` | `asia` |

**Giải thích:** `demo.name` và `demo.enabled` được import ghi đè; `demo.retries` còn lại từ tài liệu gốc; `demo.region` do tài liệu import bổ sung.

**Câu hỏi 2:** Nếu chạy thêm:

```bash
java -jar app.jar --demo.name=cli --demo.retries=8
```

thì kết quả thay đổi ở đâu?

```text
demo.name    = cli
demo.retries = 8
demo.enabled = true
demo.region  = asia
```

Hai khóa do dòng lệnh cung cấp có ưu tiên cao hơn Config Data, còn các khóa khác giữ giá trị được chọn sau khi xử lý quan hệ import.

**Câu hỏi 3:** Nếu bỏ `demo.enabled` ra khỏi `module.yml`, kết quả của `demo.enabled` là gì?

```text
demo.enabled = false
```

Khi tài liệu import không còn định nghĩa khóa ấy, cấu hình của tài liệu khai báo tiếp tục có hiệu lực.

## 15. Ghi nhớ

- `spring.config.import` yêu cầu Spring Boot nạp thêm tài nguyên thuộc cơ chế **Config Data**.
- Trong quan hệ trực tiếp giữa hai tài liệu, **tài liệu được import có ưu tiên cao hơn tài liệu khai báo import** đối với các khóa trùng nhau.
- Cấu hình được kết hợp **theo từng khóa**; dữ liệu không bị ghi đè vẫn có thể đến từ tài liệu khai báo.
- Vị trí xuất hiện của `spring.config.import` trong cùng một tài liệu YAML/Properties không quyết định mức ưu tiên giữa tài liệu.
- `optional:` điều chỉnh xử lý khi vị trí import không tồn tại; nó không thay đổi độ ưu tiên của tệp đã nạp thành công.
- Các nguồn khác, đặc biệt **đối số dòng lệnh**, có thể ghi đè kết quả Config Data. Profile, vị trí cấu hình và nhiều tài liệu cũng ảnh hưởng đến thứ tự cuối cùng.
- Khi cần kiểm chứng, đọc khóa qua `Environment` và, nếu cần, kiểm tra các `PropertySource` đã được nạp thay vì chỉ suy đoán từ tên tệp.
