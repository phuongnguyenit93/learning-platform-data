# Thực nghiệm nhiều nguồn cùng khai báo một khóa cấu hình

## 1. Mục tiêu và câu hỏi của thí nghiệm

Một ứng dụng Spring Boot có thể nhận cùng một thuộc tính từ nhiều nơi: tệp `application.yml` được đóng gói trong JAR, tệp cấu hình nằm ngoài JAR, biến môi trường của hệ điều hành, Java system property và tham số dòng lệnh. Khi những nguồn này cùng khai báo một khóa, Spring Boot cần xác định **một giá trị có hiệu lực** để cung cấp cho mã Java.

Bài thực nghiệm này sử dụng duy nhất khóa `lab.marker`, với các giá trị cố tình khác nhau ở từng nguồn, nhằm trả lời bốn câu hỏi:

1. Khi chỉ có một nguồn, bean nhận giá trị nào?
2. Khi thêm nguồn mới có cùng khóa, nguồn nào được ưu tiên?
3. Khi bỏ nguồn có ưu tiên cao hơn, giá trị có tự rơi về nguồn thấp hơn không?
4. Giá trị truy cập bằng `Environment` và giá trị được liên kết bằng `@ConfigurationProperties` có nhất quán không?

Kết quả dự kiến của thí nghiệm, khi sử dụng cấu hình chuẩn của Spring Boot và không có nguồn bổ sung nào khác, là:

```text
Tham số dòng lệnh      --lab.marker=from-cli
          >
Java system property   -Dlab.marker=from-jvm
          >
Biến môi trường        LAB_MARKER=from-env
          >
Config ngoài JAR       ./config/application-prod.yml
          >
Config ngoài JAR       ./config/application.yml
          >
Config trong JAR       application-prod.yml
          >
Config trong JAR       application.yml
```

Dấu `>` nghĩa là **có ưu tiên cao hơn đối với cùng khóa `lab.marker`** trong kịch bản đang xét. Đây là thứ tự giữa những nguồn *được đưa vào thí nghiệm*, không phải danh sách đầy đủ mọi `PropertySource` mà Spring Boot hỗ trợ. Chẳng hạn, cấu hình kiểm thử, `SPRING_APPLICATION_JSON` hoặc cấu hình bổ sung do ứng dụng đăng ký có thể làm thay đổi bức tranh nếu được đưa vào.

## 2. Chuẩn bị ứng dụng nhỏ để quan sát kết quả

Ta dùng một ứng dụng Spring Boot có thể đóng gói thành JAR thực thi. Không cần cơ sở dữ liệu, HTTP endpoint hay chức năng nghiệp vụ phức tạp. Ứng dụng chỉ in giá trị của `lab.marker` sau khi context đã khởi tạo.

Cấu trúc tối thiểu:

```text
config-priority-lab/
├── src/main/java/com/example/configlab/
│   ├── ConfigLabApplication.java
│   └── LabProperties.java
├── src/main/resources/
│   ├── application.yml
│   └── application-prod.yml
└── config/                         # tạo sau, đặt ngoài JAR
    ├── application.yml
    └── application-prod.yml
```

Hai tệp trong `src/main/resources` sẽ trở thành tài nguyên trong JAR sau khi đóng gói. Ngược lại, thư mục `config/` nằm cạnh nơi ta chạy lệnh sẽ là một nguồn cấu hình **bên ngoài** bản dựng. Để thấy từng nguồn xuất hiện theo thứ tự, ban đầu **chưa tạo** hai tệp dưới `config/`.

### 2.1. Định nghĩa đối tượng nhận cấu hình

Tạo `LabProperties.java`:

```java
package com.example.configlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab")
public record LabProperties(String marker) {
}
```

`@ConfigurationProperties(prefix = "lab")` yêu cầu Spring Boot liên kết thuộc tính `lab.marker` với thành phần `marker` của record. Đây là ví dụ về binding có kiểu: tên thuộc tính trong cấu hình được ánh xạ sang thành phần của đối tượng Java. Record một constructor hoạt động phù hợp với cơ chế constructor binding của Spring Boot 3.

Tạo `ConfigLabApplication.java`:

```java
package com.example.configlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@EnableConfigurationProperties(LabProperties.class)
public class ConfigLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigLabApplication.class, args);
    }

    @Bean
    ApplicationRunner reportConfiguration(
            Environment environment,
            LabProperties properties) {
        return args -> {
            String fromEnvironment =
                    environment.getProperty("lab.marker");

            String fromBinding = properties.marker();

            System.out.println("=== CONFIG PRIORITY LAB ===");
            System.out.println("Environment = " + fromEnvironment);
            System.out.println("Bound bean  = " + fromBinding);
            System.out.println("===========================");
        };
    }
}
```

Trong ví dụ này, `ApplicationRunner` chạy khi quá trình khởi động ứng dụng đã hoàn tất đến giai đoạn thực thi runner. Ta đo cùng một thuộc tính bằng hai cách:

- `Environment.getProperty("lab.marker")`: tra cứu giá trị có hiệu lực theo khóa.
- `properties.marker()`: đọc giá trị đã được Spring Boot liên kết vào bean `LabProperties`.

Nếu nguồn cấu hình và binding được thiết lập đúng, hai dòng phải phản ánh cùng một giá trị. Thí nghiệm không dựa vào thứ tự in của các log khởi động khác; chỉ quan sát hai dòng sau nhãn `CONFIG PRIORITY LAB`.

### 2.2. Tạo cấu hình đóng gói trong JAR

Trong `src/main/resources/application.yml`:

```yaml
lab:
  marker: from-packaged-default
```

Trong `src/main/resources/application-prod.yml`:

```yaml
lab:
  marker: from-packaged-prod
```

Tên `application-prod.yml` biểu thị cấu hình dành cho profile `prod`. Nếu không kích hoạt profile này, giá trị trong tệp đó sẽ không được áp dụng chỉ vì tệp tồn tại. Nếu kích hoạt `prod`, giá trị `from-packaged-prod` ghi đè `from-packaged-default` ở cùng khóa, miễn là không có nguồn ưu tiên cao hơn.

Sau khi thêm cả hai tệp, hãy đóng gói ứng dụng theo công cụ build hiện có, chẳng hạn nhiệm vụ Gradle `bootJar`, rồi dùng đường dẫn thực tế tới JAR đã sinh ra. Trong các lệnh bên dưới, `app.jar` chỉ là tên minh họa cho **JAR thực thi đã đóng gói**, không phải một tệp Spring Boot tự tạo mặc định.

Đảm bảo mở terminal tại thư mục dự án, nơi về sau sẽ chứa `./config/`. Vị trí làm việc hiện tại quan trọng vì Spring Boot mặc định tìm cấu hình bên ngoài ở các vị trí tương đối với thư mục chạy ứng dụng.

## 3. Lần chạy A — Chỉ dùng application.yml trong JAR

Trước khi tạo thư mục `config/` và trước khi đặt biến môi trường hoặc Java system property cho khóa thí nghiệm, chạy:

```bash
java -jar app.jar
```

Kết quả mong đợi:

```text
=== CONFIG PRIORITY LAB ===
Environment = from-packaged-default
Bound bean  = from-packaged-default
===========================
```

Ta có một nguồn cho `lab.marker`: `application.yml` đóng gói trong JAR. Spring Boot nạp tệp này qua cơ chế Config Data, đưa thuộc tính vào hệ thống cấu hình, rồi trả về cùng một giá trị khi tra cứu và binding.

Điều cần quan sát không chỉ là chuỗi được in ra. Cần nhận ra ranh giới: **mã `ConfigLabApplication` không biết thuộc tính được lưu trong tệp YAML nào**. Mã chỉ nêu khóa hoặc tiền tố; Spring Boot quyết định nguồn nào cấp giá trị.

Nếu hai dòng ra `null`, hãy kiểm tra tệp YAML đã thực sự được đóng gói vào JAR, lớp record đã được đăng ký bằng `@EnableConfigurationProperties`, và không có lỗi chính tả ở tiền tố hoặc tên khóa. Nếu ra giá trị khác, có thể một nguồn cấu hình từ môi trường máy đang ghi đè giá trị trong JAR.

## 4. Lần chạy B — Kích hoạt profile prod

Giữ nguyên JAR nhưng thêm tham số lựa chọn profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả mong đợi:

```text
Environment = from-packaged-prod
Bound bean  = from-packaged-prod
```

Vì `prod` được kích hoạt, Spring Boot nạp cấu hình trong `application-prod.yml`. Đối với cùng khóa `lab.marker`, cấu hình theo profile trong JAR có độ ưu tiên cao hơn cấu hình không gắn profile trong cùng JAR.

Cần phân biệt:

- `--spring.profiles.active=prod` quyết định **profile nào đang hoạt động**.
- `application-prod.yml` cung cấp **một ứng viên giá trị** cho `lab.marker`.
- Việc chọn giá trị cuối cùng vẫn chịu thứ tự ưu tiên của toàn bộ nguồn cấu hình.

Do đó, profile không tạo một hệ thống tra cứu tách biệt. Nó điều khiển việc tham gia của một số nguồn cấu hình trong cùng `Environment`.

## 5. Lần chạy C — Thêm application.yml bên ngoài JAR

Bây giờ mới tạo thư mục `config` tại thư mục đang chạy terminal, và thêm `./config/application.yml`:

```yaml
lab:
  marker: from-external-default
```

Giữ nguyên JAR và vẫn kích hoạt profile `prod`:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả mong đợi:

```text
Environment = from-external-default
Bound bean  = from-external-default
```

Điểm thú vị là tệp `application-prod.yml` *trong JAR* đang khai báo `from-packaged-prod`, nhưng giá trị được chọn lại là `from-external-default` từ `application.yml` *ngoài JAR*. Với quy tắc mặc định về các vị trí Config Data thông dụng, cấu hình ngoài JAR có ưu tiên cao hơn cấu hình đóng gói bên trong JAR.

Điều này giúp vận hành một bản dựng duy nhất trên nhiều máy: mỗi môi trường triển khai có thể đặt cấu hình ngoài JAR mà không cần biên dịch lại. Tuy nhiên, hãy nhớ vị trí `./config/` được tính theo **thư mục làm việc của tiến trình**, không nhất thiết theo thư mục chứa JAR. Nếu chạy ứng dụng từ thư mục khác, file ngoài có thể không được tìm thấy theo cách bạn dự kiến.

Ở lần chạy này, danh sách ứng viên cho `lab.marker` là:

| Nguồn | Giá trị | Có hiệu lực? |
| --- | --- | --- |
| Trong JAR, `application.yml` | `from-packaged-default` | Không |
| Trong JAR, `application-prod.yml` | `from-packaged-prod` | Không |
| Ngoài JAR, `config/application.yml` | `from-external-default` | **Có** |

Không cần xóa hai giá trị trong JAR; Spring Boot tự chọn theo độ ưu tiên của nguồn.

## 6. Lần chạy D — Thêm cấu hình theo profile bên ngoài JAR

Tạo thêm `./config/application-prod.yml`:

```yaml
lab:
  marker: from-external-prod
```

Chạy lại:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Kết quả mong đợi:

```text
Environment = from-external-prod
Bound bean  = from-external-prod
```

Lúc này cả bốn tệp đều có `lab.marker`. Trong phạm vi Config Data thông dụng của thí nghiệm, thứ tự từ cao xuống thấp là:

1. Ngoài JAR: `config/application-prod.yml`.
2. Ngoài JAR: `config/application.yml`.
3. Trong JAR: `application-prod.yml`.
4. Trong JAR: `application.yml`.

Đây chính là lý do `from-external-prod` thắng. Cấu hình theo profile và vị trí tệp **cùng tham gia** xác định ưu tiên; không thể kết luận đơn giản rằng “mọi tệp có profile luôn thắng mọi tệp không có profile” nếu bỏ qua việc tệp nằm trong hay ngoài JAR.

Nếu chạy lại mà **không** có `--spring.profiles.active=prod`, hai tệp `application-prod.yml` thông thường không được dùng, và `from-external-default` sẽ có hiệu lực. Đây là phép kiểm tra độc lập để chứng minh việc kích hoạt profile tác động đến tập nguồn được xét.

## 7. Lần chạy E — Biến môi trường ghi đè YAML

Giữ nguyên bốn tệp cấu hình. Trên Linux/macOS, đặt biến môi trường chỉ cho một lệnh chạy:

```bash
LAB_MARKER=from-env java -jar app.jar --spring.profiles.active=prod
```

Trên Windows PowerShell:

```powershell
$env:LAB_MARKER = "from-env"
java -jar app.jar --spring.profiles.active=prod

# Dọn biến sau thí nghiệm để không ảnh hưởng lần chạy sau
Remove-Item Env:LAB_MARKER
```

Kết quả mong đợi khi biến môi trường đang được đặt:

```text
Environment = from-env
Bound bean  = from-env
```

Trong Spring Boot, `LAB_MARKER` là dạng biến môi trường tương ứng với tên thuộc tính `lab.marker`. Đối với nguồn cấu hình tiêu chuẩn đang sử dụng ở đây, biến môi trường hệ điều hành có ưu tiên cao hơn các tệp Config Data.

Nhờ vậy, môi trường chạy có thể ghi đè một giá trị mặc định ở trong JAR hoặc tệp cấu hình mà không sửa mã. Ví dụ, một hệ thống triển khai có thể cấp các biến môi trường riêng cho từng phiên chạy.

Một lưu ý thực tế: nếu bạn dùng `export LAB_MARKER=from-env` trong Bash, biến sẽ còn trong phiên shell đó cho đến khi `unset LAB_MARKER` hoặc phiên shell kết thúc. Trong PowerShell, `$env:LAB_MARKER` cũng tiếp tục tồn tại trong tiến trình shell cho đến khi được gỡ hoặc thay đổi. Nếu quên bước này, thí nghiệm về YAML ở lần chạy sau sẽ cho kết quả khác mong đợi.

## 8. Lần chạy F — Java system property ghi đè biến môi trường

Tiếp tục giữ biến môi trường `LAB_MARKER=from-env` và thêm Java system property `lab.marker` bằng tham số `-D` của JVM:

Linux/macOS:

```bash
LAB_MARKER=from-env java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod
```

Windows PowerShell:

```powershell
$env:LAB_MARKER = "from-env"
java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod
Remove-Item Env:LAB_MARKER
```

Kết quả mong đợi:

```text
Environment = from-jvm
Bound bean  = from-jvm
```

Ở đây có cả biến môi trường `from-env` và giá trị JVM `from-jvm`, nhưng `from-jvm` thắng vì Java system properties có độ ưu tiên cao hơn OS environment variables trong thứ tự nguồn chuẩn của Spring Boot.

Về cú pháp, `-Dlab.marker=from-jvm` phải đứng **trước `-jar`** để được JVM hiểu là system property. Nếu viết `java -jar app.jar -Dlab.marker=from-jvm`, chuỗi đó chỉ còn là đối số gửi cho ứng dụng, không có cùng ý nghĩa. Với Spring Boot, để truyền trực tiếp thuộc tính qua đối số ứng dụng, ta sử dụng dạng `--lab.marker=value` ở bước tiếp theo.

Đừng nhầm Java system property `System.getProperty("lab.marker")` với biến môi trường `System.getenv("LAB_MARKER")`. Đây là hai cơ chế lưu giá trị khác nhau của JVM và hệ điều hành; `Environment` của Spring tổng hợp các nguồn đó theo thứ tự ưu tiên.

## 9. Lần chạy G — Tham số dòng lệnh có ưu tiên cao nhất trong thí nghiệm

Giữ cả biến môi trường và Java system property như bước trên, rồi thêm đối số Spring Boot `--lab.marker=from-cli`:

Linux/macOS:

```bash
LAB_MARKER=from-env java -Dlab.marker=from-jvm -jar app.jar \
  --spring.profiles.active=prod \
  --lab.marker=from-cli
```

Windows PowerShell (một dòng):

```powershell
$env:LAB_MARKER = "from-env"
java -Dlab.marker=from-jvm -jar app.jar --spring.profiles.active=prod --lab.marker=from-cli
Remove-Item Env:LAB_MARKER
```

Kết quả mong đợi:

```text
Environment = from-cli
Bound bean  = from-cli
```

Đến đây, bảy nguồn của thí nghiệm có thể cùng cung cấp `lab.marker`:

| Thứ tự ưu tiên trong thí nghiệm | Nguồn khai báo | Giá trị |
| ---: | --- | --- |
| 1 — cao nhất | Đối số `--lab.marker=...` | **`from-cli`** |
| 2 | Java system property `-Dlab.marker=...` | `from-jvm` |
| 3 | Biến môi trường `LAB_MARKER` | `from-env` |
| 4 | `./config/application-prod.yml` | `from-external-prod` |
| 5 | `./config/application.yml` | `from-external-default` |
| 6 | `application-prod.yml` bên trong JAR | `from-packaged-prod` |
| 7 — thấp nhất | `application.yml` bên trong JAR | `from-packaged-default` |

Mọi nguồn đều có một ứng viên giá trị, nhưng `Environment` trả về giá trị có hiệu lực là `from-cli`, và `LabProperties.marker()` cũng nhận `from-cli`.

**Thứ tự trên là kết quả trong phạm vi các nguồn đã chọn**, với profile `prod` đang hoạt động và xử lý command-line properties ở chế độ mặc định. Spring Boot còn có các nguồn như `SPRING_APPLICATION_JSON`, tham số của môi trường servlet và thuộc tính dành cho test. Một ứng dụng cũng có thể tự thay đổi cách đăng ký nguồn; không nên áp dụng bảng này như thứ tự bất biến cho mọi chương trình Spring.

## 10. Thí nghiệm đảo chiều: bỏ từng nguồn ưu tiên cao

Thêm nguồn từng bước giúp thấy ai ghi đè ai. **Gỡ từng nguồn theo chiều ngược lại** giúp chứng minh các giá trị có ưu tiên thấp vẫn còn đó và có thể được sử dụng khi nguồn cao hơn vắng mặt.

Giữ nguyên bốn tệp YAML và profile `prod`; thực hiện các lần chạy độc lập trong môi trường shell được kiểm soát:

| Tình huống | Nguồn vẫn tham gia cho `lab.marker` | Kỳ vọng |
| --- | --- | --- |
| A | Có command line, JVM, OS env và bốn YAML | `from-cli` |
| B | Bỏ riêng `--lab.marker=from-cli`; vẫn có JVM và OS env | `from-jvm` |
| C | Bỏ cả CLI lẫn `-Dlab.marker`; còn OS env | `from-env` |
| D | Bỏ CLI, JVM và biến môi trường; còn bốn YAML | `from-external-prod` |
| E | Đổi tên/xóa tạm `config/application-prod.yml`, giữ YAML ngoài còn lại | `from-external-default` |
| F | Đổi tên/xóa tạm tiếp `config/application.yml`, giữ profile `prod` | `from-packaged-prod` |
| G | Giữ không có YAML ngoài, không bật profile `prod` | `from-packaged-default` |

Đối với các bước E/F, chỉ đổi tên tạm các tệp cấu hình của bài thực nghiệm nếu bạn muốn giữ lại nội dung; không sửa tệp trong JAR. Đối với các bước B/C, phải thực sự bỏ đối số hoặc biến môi trường khỏi lệnh chạy mới.

Có thể thực hiện bước D độc lập bằng lệnh sau trên một shell không còn `LAB_MARKER`:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Nếu dòng kết quả hiển thị `from-external-prod`, ta chứng minh việc bỏ ba nguồn trên cho phép giá trị trong external profile config xuất hiện. Cơ chế này thường được gọi là **ghi đè có ưu tiên**: nhiều nguồn được giữ trong hệ thống, còn việc tra cứu khóa xác định giá trị thắng.

Cần nhớ mỗi dòng trong bảng là **một lần khởi động ứng dụng mới**. Thay biến môi trường hoặc tệp sau khi ứng dụng đã chạy không bảo đảm bean `LabProperties` tự cập nhật; thí nghiệm nhằm so sánh trạng thái cấu hình ở các lần khởi động.

## 11. Tự nhìn vào nguồn: Environment làm gì?

Đến đây, ta đã biết *nguồn nào thắng* nhờ chuỗi in ra. Để hiểu *vì sao*, cần phân biệt:

- **PropertySource**: đại diện cho một nguồn chứa nhiều thuộc tính, chẳng hạn Java system properties, biến môi trường, nguồn Config Data.
- **Environment**: cung cấp khả năng tra cứu thuộc tính trên các nguồn đó theo độ ưu tiên, đồng thời quản lý thông tin profile.
- **ConfigurationProperties binding**: sử dụng hệ thống cấu hình để liên kết tên thuộc tính với thành phần Java và chuyển kiểu nếu cần.
- **Bean sử dụng cấu hình**: chỉ nhận giá trị đã liên kết, không cần tự quyết định đọc tệp nào.

Với `lab.marker`, ứng dụng nhận về một chuỗi nên bước chuyển kiểu hầu như không gây chú ý. Nếu thay khóa bằng `lab.timeout` và giá trị `5s`, rồi dùng thành phần `Duration timeout` trong record, Spring Boot có thể chuyển biểu diễn thời gian từ cấu hình thành đối tượng Java. **Ưu tiên nguồn** trả lời “giá trị đầu vào nào được chọn”; **binding** trả lời “giá trị ấy được đưa vào kiểu Java như thế nào”. Đây là hai câu hỏi khác nhau.

Khi cần phân tích chuyên sâu, có thể duyệt `ConfigurableEnvironment.getPropertySources()` trong một chương trình thử nghiệm hoặc quan sát thông tin qua các endpoint Spring Boot Actuator `env` và `configprops` nếu dự án đã bật và bảo vệ chúng thích hợp. Tuy nhiên, nguồn tổng hợp và cách biểu diễn chi tiết có thể khác nhau theo phiên bản, nên không nên viết logic nghiệp vụ phụ thuộc vào tên nội bộ của từng `PropertySource`.

Không in danh sách tất cả thuộc tính của ứng dụng thật vì có thể làm lộ khóa truy cập, mật khẩu và thông tin kết nối. Bài thí nghiệm cố tình chỉ dùng `lab.marker` chứa các chuỗi vô hại.

## 12. Vì sao giá trị trong YAML khác với kết quả ở bean?

Một lỗi suy luận thường gặp là mở `application.yml`, thấy `lab.marker: from-packaged-default` và cho rằng bean chắc chắn nhận chuỗi đó. Trong mô hình nhiều nguồn, tệp này chỉ là **một ứng viên**. Khi bean được tạo, Spring quyết định giá trị có hiệu lực từ tất cả những nguồn đang được nạp.

Một số trường hợp dễ gây nhầm lẫn:

### 12.1. Quên biến môi trường đã được đặt từ trước

Nếu đã chạy `export LAB_MARKER=from-env` hoặc `$env:LAB_MARKER = "from-env"`, lần chạy kế tiếp có thể vẫn nhận `from-env` dù đã đổi YAML. Kiểm tra và gỡ biến trong shell trước khi kết luận thí nghiệm YAML sai.

### 12.2. Chạy JAR từ sai thư mục

Một file nằm cạnh JAR chưa chắc được Spring tự tìm thấy nếu tiến trình được khởi chạy từ thư mục khác. Các vị trí tìm mặc định như `./config/` liên quan đến thư mục làm việc. Hãy cố định `pwd` hoặc `Get-Location` khi so sánh, hoặc cấu hình vị trí ngoài một cách tường minh khi cần.

Spring Boot hỗ trợ tham số `spring.config.additional-location` để bổ sung vị trí tìm Config Data. Đây là một công cụ vận hành riêng; nếu sử dụng thì phải ghi nhận nó trong thiết kế thí nghiệm vì có thể thay đổi tập nguồn và mức ưu tiên.

### 12.3. Không bật đúng profile

`application-prod.yml` không phải lúc nào cũng được nạp. Nếu quên `--spring.profiles.active=prod`, hãy kiểm tra liệu profile `prod` có đang được kích hoạt từ một nguồn khác hay không. Không suy đoán profile chỉ dựa vào tên tệp.

### 12.4. Nhầm tham số JVM với đối số ứng dụng

Hai lệnh dưới đây có ý nghĩa khác nhau:

```bash
java -Dlab.marker=from-jvm -jar app.jar
java -jar app.jar --lab.marker=from-cli
```

Dạng `-D` là Java system property; dạng `--lab.marker=...` là command-line property được Spring Boot nhận qua tham số ứng dụng. Trong cấu hình tiêu chuẩn, dòng lệnh dạng `--` thắng `-D` nếu cả hai cùng khai báo một khóa.

### 12.5. Có nhiều nguồn ngoài phạm vi bài lab

Nếu hệ thống thực tế sử dụng `SPRING_APPLICATION_JSON`, test properties, cấu hình import, nhiều profile, hoặc có mã thay đổi `PropertySources`, kết quả có thể khác bảng thí nghiệm. Khi đó phải mở rộng danh sách nguồn được phân tích, không ép kết quả theo bảng mẫu.

### 12.6. Đọc giá trị lúc đang chạy rồi mong nó tự đổi

`@ConfigurationProperties` thường được liên kết khi bean được tạo. Chỉnh sửa file cấu hình ngoài JAR sau khi Spring Boot đã chạy không đồng nghĩa ứng dụng tự nạp lại đối tượng cấu hình. Muốn thử nguồn mới một cách dễ xác nhận, hãy dừng rồi khởi động lại tiến trình. Cơ chế cập nhật cấu hình động, nếu cần, phải được thiết kế riêng.

## 13. Kịch bản bổ sung: dùng giá trị khác cho từng máy

Giả sử cả nhóm triển khai chung một JAR:

```yaml
# application.yml nằm trong JAR
lab:
  marker: safe-default
```

Máy phát triển không khai báo thêm gì sẽ nhận `safe-default`. Máy staging có `LAB_MARKER=staging` sẽ nhận `staging`. Máy production có biến môi trường `LAB_MARKER=production` sẽ nhận `production`. Cùng một class `LabProperties` và cùng mã gọi `properties.marker()` vẫn hoạt động.

Tất nhiên, trong ứng dụng thật, cấu hình thường là URL dịch vụ, thời gian chờ, kích thước nhóm kết nối hoặc cờ tính năng thay vì một chuỗi đánh dấu. Nguyên tắc vẫn như nhau: mã chứa **tên và cách dùng cấu hình**, môi trường triển khai cung cấp **giá trị cụ thể**. Không nên hardcode địa chỉ sản xuất, mật khẩu hoặc token vào mã chỉ vì chương trình có thể chạy bằng giá trị đó.

Khi có cùng một khóa ở nhiều nguồn, cần vận hành có kỷ luật: ghi lại nguồn nào được phép ghi đè, giới hạn những override nhạy cảm, xác định giá trị mặc định hợp lý và quan sát trạng thái có hiệu lực qua kênh chẩn đoán được bảo vệ.

## 14. Bài tập củng cố

Hãy dự đoán đầu ra trước khi chạy; sau đó dùng `Environment` và `LabProperties` để kiểm chứng:

**Bài tập 1 — Hai nguồn trong JAR:** Với `application.yml` và `application-prod.yml` như phần chuẩn bị, tại sao chạy không có profile cho kết quả `from-packaged-default` nhưng bật `prod` cho `from-packaged-prod`?

**Bài tập 2 — Nguồn ngoài và trong:** Khi `application-prod.yml` bên trong JAR đang được dùng, vì sao thêm `./config/application.yml` lại có thể đổi kết quả sang `from-external-default`?

**Bài tập 3 — Biến môi trường:** Cả `config/application-prod.yml` và `LAB_MARKER` cùng đặt một khóa. Nếu bỏ biến môi trường khỏi **lần chạy mới**, Spring Boot dùng giá trị nào?

**Bài tập 4 — JVM và CLI:** Lệnh sau có những ứng viên nào cho `lab.marker` và giá trị cuối là gì?

```bash
LAB_MARKER=os java -Dlab.marker=jvm -jar app.jar \
  --spring.profiles.active=prod \
  --lab.marker=cli
```

**Bài tập 5 — Khôi phục giá trị thấp hơn:** Khi xóa tham số `--lab.marker=cli` khỏi lệnh ở bài tập 4, giá trị có hiệu lực chuyển sang đâu? Nếu bỏ tiếp `-Dlab.marker=jvm` thì sao?

**Bài tập 6 — Chuyển kiểu:** Thay `lab.marker` bằng `lab.timeout`, cấu hình lần lượt `1s` trong YAML, `LAB_TIMEOUT=4s` trong môi trường và `--lab.timeout=2s` trên dòng lệnh. Dùng `@ConfigurationProperties` với thành phần `Duration timeout`. Trước khi chạy, hãy dự đoán `timeout.toSeconds()` trả về bao nhiêu và lý do.

Qua các bài tập, cần phân biệt chính xác ba giai đoạn: **nguồn nào tham gia**, **nguồn nào có ưu tiên cao nhất cho khóa**, và **bean nhận giá trị đã được liên kết**. Đó là bản chất của việc thực nghiệm externalized configuration khi nhiều nguồn cùng khai báo một khóa.

## 15. Tổng hợp kết quả thí nghiệm

Với mã Java không đổi, ta đã tạo một chuỗi kết quả kiểm chứng được:

```text
Không kích hoạt profile, chưa có config ngoài:
    from-packaged-default

Kích hoạt prod, chưa có config ngoài:
    from-packaged-prod

Thêm ./config/application.yml:
    from-external-default

Thêm ./config/application-prod.yml:
    from-external-prod

Thêm LAB_MARKER:
    from-env

Thêm -Dlab.marker:
    from-jvm

Thêm --lab.marker:
    from-cli
```

Điểm mấu chốt không nằm ở việc học thuộc chuỗi giá trị ví dụ. Hãy luôn tự hỏi: **“Ở thời điểm khởi động này, những `PropertySource` nào đang tham gia và nguồn nào có độ ưu tiên cao nhất cho khóa cần đọc?”**

Trả lời câu đó trước, rồi mới kiểm tra binding và cách bean sử dụng cấu hình. Khi làm như vậy, việc điều tra một giá trị cấu hình “không đúng như trong YAML” trở thành một quy trình có thể quan sát và lặp lại, thay vì thử sửa ngẫu nhiên các tệp cấu hình.