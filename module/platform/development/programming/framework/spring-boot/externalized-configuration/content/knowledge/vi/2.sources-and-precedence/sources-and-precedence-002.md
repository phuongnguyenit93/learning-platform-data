# Thứ tự ưu tiên đầy đủ của PropertySource trong Spring Boot 3.3

## 1. Nguyên tắc cốt lõi

Spring Boot 3.3 xây dựng `Environment` từ nhiều `PropertySource`: cấu hình mặc định, file `application.properties`/`application.yaml`, biến môi trường, JVM system properties, tham số dòng lệnh và một số nguồn dành riêng cho web/test/devtools. Khi **cùng một khóa** xuất hiện ở nhiều nguồn, giá trị đến từ nguồn **có mức ưu tiên cao nhất** sẽ được dùng. Nguồn không khai báo khóa đó không xóa giá trị của nguồn thấp hơn.

**Quy ước của bảng dưới đây:** số **1 = ưu tiên thấp nhất**, số **15 = ưu tiên cao nhất**; nguồn ở hàng phía dưới có thể ghi đè nguồn phía trên. Đây là thứ tự chính thức được mô tả trong tài liệu *Externalized Configuration* của **Spring Boot 3.3**, dành cho các nguồn mặc định do Spring Boot thiết lập. Không phải ứng dụng nào cũng có đủ 15 nguồn: nguồn Servlet/JNDI, test và Devtools chỉ tồn tại khi môi trường tương ứng hỗ trợ.

> Phân biệt hai cách nhìn: tài liệu sắp xếp từ **thấp → cao**, còn khi duyệt `ConfigurableEnvironment#getPropertySources()`, các nguồn thường được liệt kê theo thứ tự **cao → thấp** để tìm giá trị khớp đầu tiên. Đừng nhầm chiều của hai danh sách.

## 2. Toàn bộ 15 mức ưu tiên

| Mức (thấp → cao) | PropertySource | Ý nghĩa và điều kiện áp dụng |
| ---: | --- | --- |
| **1** | **Default properties** | Bản đồ giá trị mặc định do mã khởi động truyền qua `SpringApplication.setDefaultProperties(Map)`. Đây là tầng dự phòng cuối cùng. |
| **2** | **`@PropertySource` trên lớp `@Configuration`** | Nạp file properties qua annotation của Spring. Nguồn này chỉ được thêm khi `ApplicationContext` đang được refresh, nên có thể **quá muộn** cho các khóa được đọc trước đó, như `logging.*` và `spring.main.*`. |
| **3** | **Config Data** | `application.properties`/`application.yaml`, các biến thể theo profile, file ngoài JAR, dữ liệu được nhập bằng `spring.config.import` và các bộ nạp Config Data được hỗ trợ. Có thứ tự ưu tiên **bên trong mức 3**, trình bày ở phần sau. |
| **4** | **`RandomValuePropertySource`** | Cấp giá trị cho các biểu thức `random.*`, ví dụ `random.uuid`, `random.int`; không phải nguồn ghi đè tổng quát cho mọi khóa ứng dụng. |
| **5** | **Biến môi trường của hệ điều hành** | Ví dụ `SERVER_PORT=8082` tương ứng với `server.port` trong trường hợp thông thường. Thường được dùng trong container/Kubernetes/CI. |
| **6** | **Java System properties** | Các khóa từ `System.getProperties()`, ví dụ `-Dserver.port=8083` truyền cho JVM. Cao hơn biến môi trường OS trong thứ tự mặc định của Boot 3.3. |
| **7** | **Thuộc tính JNDI** | Giá trị trong `java:comp/env` khi chạy với môi trường hỗ trợ JNDI. Không có trong nhiều ứng dụng executable JAR thông thường. |
| **8** | **`ServletContext` init parameters** | Tham số khởi tạo cấp `ServletContext` trong ứng dụng Servlet. |
| **9** | **`ServletConfig` init parameters** | Tham số khởi tạo cấp servlet, cao hơn `ServletContext` init params. |
| **10** | **`SPRING_APPLICATION_JSON`** | JSON cấu hình nội tuyến được truyền qua biến môi trường, JVM system property, đối số dòng lệnh `spring.application.json` hoặc JNDI. JSON được phân tích thành các khóa phân cấp. |
| **11** | **Command-line arguments** | Các tùy chọn dạng `--key=value` được `SpringApplication` chuyển thành properties. Theo mặc định, chúng cao hơn các nguồn cấu hình khi chạy ứng dụng ở trên. |
| **12** | **`properties` của test annotation** | Ví dụ `@SpringBootTest(properties = "...")` hoặc các annotation test slice của Spring Boot. Chỉ dùng trong ngữ cảnh test. |
| **13** | **`@DynamicPropertySource` trong test** | Các giá trị động do test đăng ký, thường dùng để nhận địa chỉ/port từ Testcontainers. |
| **14** | **`@TestPropertySource` trong test** | Các nguồn hoặc thuộc tính dành riêng cho Spring Test. Theo danh sách Spring Boot 3.3, cao hơn mục 12 và 13. |
| **15** | **Devtools global settings** | Thuộc tính cấu hình Devtools toàn cục trong `$HOME/.config/spring-boot`, **chỉ khi Devtools hoạt động**. Đây là mức cao nhất trong danh sách chính thức. |

Cách nhớ trong các trường hợp chạy ứng dụng phổ biến: **mặc định < @PropertySource < Config Data < random.* < OS environment < JVM -D < JNDI < ServletContext < ServletConfig < JSON < --command-line**. Khi test hoặc chạy với Devtools, cần tính thêm các tầng 12–15. Dấu `<` ở đây nghĩa là “ưu tiên thấp hơn”.

**Ví dụ lập trình giá trị mặc định (mức 1):**

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setDefaultProperties(Map.of(
    "server.port", "8080",
    "app.mode", "default"
));
app.run(args);
```

Lưu ý: trên môi trường thực tế có thể xuất hiện thêm nguồn do thư viện, Spring Cloud hoặc mã ứng dụng tự chèn vào `Environment`. Bảng 15 tầng mô tả **thứ tự mặc định của Spring Boot 3.3**, không phải lời khẳng định rằng bất kỳ `PropertySource` tùy biến nào cũng phải tuân theo vị trí cố định này.

## 3. Thứ tự **bên trong Config Data** (mức 3)

### 3.1. Bốn nhóm file cấu hình, từ thấp lên cao

Spring Boot 3.3 xét Config Data file của ứng dụng theo thứ tự tổng quát:

1. **Trong JAR, không theo profile:** `application.properties` hoặc biến thể YAML.
2. **Trong JAR, theo profile:** `application-{profile}.properties` hoặc YAML.
3. **Ngoài JAR, không theo profile:** file `application.properties`/YAML từ vị trí external.
4. **Ngoài JAR, theo profile:** `application-{profile}.properties`/YAML từ vị trí external.

Nhóm phía sau có thể ghi đè nhóm phía trước. Chẳng hạn, nếu profile `prod` đang active, `./config/application-prod.properties` có thể ghi đè `src/main/resources/application-prod.properties` được đóng trong JAR.

Trong **cùng một vị trí**, nếu đồng thời có `application.properties` và `application.yaml`/`application.yml`, bản **`.properties` được ưu tiên**. Nên dùng thống nhất một định dạng để tránh khó dự đoán cấu hình.

### 3.2. Các vị trí được tìm mặc định

Khi chưa ghi đè đường dẫn tìm kiếm, các vị trí cấu hình điển hình được xét theo thứ tự từ thấp đến cao như sau:

1. `classpath:/` (gốc classpath).
2. `classpath:/config/`.
3. `file:./` (thư mục làm việc hiện tại).
4. `file:./config/`.
5. `file:./config/*/` (các thư mục con trực tiếp bên dưới `config/`).

`file:./` được tính theo **working directory của tiến trình**, không mặc định theo thư mục chứa file JAR. Wildcard `config/*/` chỉ lấy một cấp thư mục con; các đường dẫn wildcard hợp lệ được sắp theo thứ tự chữ cái dựa trên đường dẫn tuyệt đối. Khi có nhiều file và profile, kết quả còn chịu quy tắc **location group**.

### 3.3. Profile và location group

- `application-prod.properties` được áp dụng khi profile `prod` hoạt động; file đặc thù profile có thể ghi đè file không đặc thù.
- Nếu `spring.profiles.active=prod,live`, trong cùng **location group**, profile sau (`live`) có quyền ghi đè profile trước (`prod`) khi hai file khai báo cùng khóa.
- Không có active profile thì Spring Boot sử dụng nhóm default profile (mặc định tên `default`); `application-default.properties` có thể được nạp.
- Trong `spring.config.location`, dấu phẩy `,` phân tách các **location group** theo thứ tự ưu tiên; dấu chấm phẩy `;` gom nhiều location vào **cùng cấp**. Việc nhóm thay đổi thứ tự xử lý khi có nhiều profile.

Ví dụ `spring.config.location=classpath:/cfg/,classpath:/ext/` cho phép toàn bộ cấu hình từ `ext` ghi đè `cfg` theo nhóm vị trí, còn `spring.config.location=classpath:/cfg/;classpath:/ext/` xử lý `cfg` và `ext` cùng một nhóm và xét thứ tự profile trong nhóm đó. Vì vậy không thể kết luận “profile sau thắng mọi vị trí” khi chưa nhìn cách nhóm location.

### 3.4. Thay thế, bổ sung và import nguồn cấu hình

| Cơ chế | Tác động đến thứ tự ưu tiên |
| --- | --- |
| `spring.config.name=myapp` | Chọn basename `myapp` thay cho `application` trong tìm kiếm mặc định. |
| `spring.config.location=...` | **Thay thế** danh sách địa điểm mặc định. Những location được nêu sau có thể ghi đè location trước. |
| `spring.config.additional-location=...` | **Bổ sung** location sau các vị trí mặc định; dữ liệu ở các vị trí bổ sung có thể ghi đè Config Data mặc định. |
| `spring.config.import=...` | Nhập Config Data ngay bên cạnh tài liệu khai báo; **dữ liệu import được ưu tiên hơn tài liệu khai báo import**. Nếu có nhiều import, import sau được ưu tiên hơn import trước. |
| `optional:` | Cho phép thiếu một location được chỉ định mà không làm ứng dụng khởi động thất bại vì thiếu địa điểm đó. |
| Tài liệu nhiều phần | Trong một file `application.yaml` chia bằng `---`, hoặc `application.properties` chia bằng `#---`, tài liệu đến sau có thể ghi đè tài liệu trước, nếu đều được kích hoạt. |

Ví dụ một file `application.properties`:

```properties
app.name=service-default
spring.config.import=optional:file:./local-overrides.properties
```

Nếu `./local-overrides.properties` tồn tại và chứa `app.name=service-local`, giá trị cuối trong nhóm Config Data là `service-local`, trừ khi một Config Data khác có ưu tiên cao hơn ghi đè. Import dù khai báo đầu hay cuối file vẫn được xét theo quy tắc trên. Các file import có thể tự có biến thể theo profile phù hợp.

**Lưu ý về thời điểm xử lý:** `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được đọc **rất sớm** để Boot biết phải tải file nào. Vì vậy nên truyền chúng từ OS environment, JVM `-D` hoặc command-line; không dựa vào `@PropertySource` được thêm muộn để quyết định đường dẫn nạp Config Data.

## 4. Ví dụ xung đột: nguồn nào thắng?

Giả sử ứng dụng cùng khai báo `server.port` tại các nguồn sau:

| Nguồn | Giá trị | Mức ưu tiên |
| --- | ---: | ---: |
| `application.properties` đóng trong JAR | `8080` | 3 |
| `./config/application.properties` bên ngoài JAR | `8081` | 3, nhưng cao hơn file trong JAR |
| OS environment `SERVER_PORT` | `8082` | 5 |
| JVM system property `-Dserver.port` | `8083` | 6 |
| `SPRING_APPLICATION_JSON` với khóa `server.port` | `8084` | 10 |
| Command-line `--server.port` | `8085` | 11 |

Trên shell kiểu Unix, có thể biểu diễn tình huống này bằng lệnh:

```bash
SERVER_PORT=8082 \
SPRING_APPLICATION_JSON='{"server":{"port":8084}}' \
java -Dserver.port=8083 -jar myapp.jar --server.port=8085
```

**Kết quả: `server.port=8085`** vì tham số `--server.port` có ưu tiên cao nhất trong các nguồn **đang hiện diện**. Nếu bỏ tham số đó thì JSON `8084` thắng; bỏ cả JSON thì JVM `8083` thắng; sau đó mới đến environment `8082`, file external `8081` và file đóng gói `8080`. Ví dụ này giả định không có test/devtools hay nguồn tùy biến nào đưa giá trị `server.port` ở mức cao hơn.

Có thể tắt việc bổ sung command-line properties bằng:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

Khi đó `--server.port=...` không còn đóng vai trò `PropertySource` qua cơ chế này.

### JSON và giá trị null

Các dạng sau đều có thể cung cấp `spring.application.json`/`SPRING_APPLICATION_JSON`:

```bash
SPRING_APPLICATION_JSON='{"app":{"mode":"json"}}' java -jar myapp.jar
java -Dspring.application.json='{"app":{"mode":"json"}}' -jar myapp.jar
java -jar myapp.jar --spring.application.json='{"app":{"mode":"json"}}'
```

JSON được trải phẳng, ví dụ `{"app":{"mode":"json"}}` thành `app.mode=json`. **JSON null không dùng để “xóa” cấu hình thấp hơn**: dù nguồn JSON chứa khóa mang giá trị null, `PropertySourcesPropertyResolver` coi null như thiếu giá trị.

## 5. Các trường hợp dễ nhầm

### 5.1. OS environment và Java system properties

`SERVER_PORT` (OS environment, mức 5) và `-Dserver.port=9000` (JVM, mức 6) là **hai nguồn khác nhau**. Nếu cả hai được cung cấp, JVM system property thắng với cùng khóa. Với tên có dấu chấm hoặc dấu gạch nối, quy tắc relaxed binding của `@ConfigurationProperties` thường ánh xạ sang kiểu biến môi trường viết hoa, dùng dấu gạch dưới; ví dụ `server.port` → `SERVER_PORT` và `spring.main.log-startup-info` → `SPRING_MAIN_LOGSTARTUPINFO` (bỏ dấu gạch nối).

Không nên giả định mọi biểu thức truy cập trực tiếp hoặc mọi property name tùy biến đều ánh xạ giống hệt nhau. Ưu tiên đặt tên property theo dạng chuẩn `lowercase.kebab-case` và kiểm tra giá trị nhận được qua `Environment` hoặc `@ConfigurationProperties`.

### 5.2. `@PropertySource` không phải Config Data

`@PropertySource("classpath:custom.properties")` ở mức **2**, thấp hơn file `application.properties` ở mức **3**. Ngoài ra, nó chỉ xuất hiện khi context refresh; các thuộc tính thiết lập hệ thống logging hoặc hành vi `SpringApplication` có thể đã được đọc trước. Spring Framework cũng không tự hỗ trợ YAML qua `@PropertySource` mặc định như cơ chế Config Data của Boot.

### 5.3. `RandomValuePropertySource` không thắng mọi khóa

`random.uuid`, `random.int` và `random.long` là các khóa đặc biệt; việc RandomValuePropertySource nằm ở mức 4 **không có nghĩa** nó cung cấp hay ghi đè `server.port`/`app.mode`. Nếu ứng dụng tham chiếu `app.token=${random.uuid}` từ Config Data, giá trị placeholder sẽ được giải quyết thông qua Environment khi dùng.

### 5.4. Chỉ test mới có các mức 12–14

Theo bảng ưu tiên của Spring Boot 3.3, trong ngữ cảnh test:

```java
@SpringBootTest(properties = "demo.flag=from-boot-test")
@TestPropertySource(properties = "demo.flag=from-test-property-source")
class ExampleTest {

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("demo.flag", () -> "from-dynamic-property-source");
    }
}
```

Khi xét đúng thứ tự 12 → 13 → 14 trong tài liệu Boot 3.3, `@TestPropertySource` là nguồn đứng sau. Các cơ chế trên **không xuất hiện tự động trong ứng dụng production**. Trong test thực tế, nếu có context hierarchy, custom initializers hoặc thư viện thêm nguồn khác, cần quan sát trực tiếp `Environment`.

### 5.5. Devtools global settings

Mức 15 dành cho thuộc tính Devtools toàn cục khi Devtools hoạt động, **không phải** một file `application.properties` tùy ý đặt trong `$HOME/.config/spring-boot`. Các giá trị này có thể gây khác biệt giữa máy phát triển và môi trường chạy thật; khi điều tra một property chỉ sai trên máy dev, hãy kiểm tra cả nguồn này.

## 6. Xem thứ tự thực tế khi chạy

Để chẩn đoán một khóa, có thể duyệt `ConfigurableEnvironment#getPropertySources()`. Ví dụ sau **chỉ in tên nguồn chứa khóa**, tránh in dữ liệu nhạy cảm từ toàn bộ Environment:

```java
@Configuration
class PropertyDiagnostics {

    @Bean
    ApplicationRunner showPropertyOrigin(ConfigurableEnvironment env) {
        return args -> {
            String key = "server.port";
            env.getPropertySources().forEach(source -> {
                if (source.containsProperty(key)) {
                    System.out.println("Contains " + key + ": " + source.getName());
                }
            });
            System.out.println("Effective " + key + ": " + env.getProperty(key));
        };
    }
}
```

Các `PropertySource` được duyệt có thể có tên khác nhau giữa các cách nạp file, và **nguồn cao hơn được xét trước**. Lệnh này kiểm tra kết quả sau khi ứng dụng đã khởi tạo; nó không thể sửa lại những thiết lập đã được đọc sớm như logging.

Nếu bật Spring Boot Actuator, endpoint `/actuator/env` hoặc `/actuator/env/server.port` có thể giúp xem property, giá trị hiệu lực và nguồn (tùy cấu hình). Endpoint này **không được mặc nhiên phơi ra công khai qua HTTP**; chỉ bật và bảo vệ khi cần chẩn đoán, nhớ rằng nhiều giá trị được che để tránh lộ bí mật.

### Quy trình xác định một giá trị cấu hình

1. Xác định chính xác tên property và nguồn nào thực sự khai báo nó, lưu ý quy tắc ánh xạ tên biến môi trường.
2. Xếp các nguồn xuất hiện theo **15 tầng** ở phần 2; nguồn có ưu tiên cao hơn thắng cho cùng khóa.
3. Nếu các nguồn đều là Config Data, xét tiếp **file nội/ngoại JAR, profile, location group, import và multi-document** ở phần 3.
4. Nếu kết quả vẫn khác mong đợi, kiểm tra các `PropertySource` thực tế trong `Environment` và các nguồn do thư viện/mã ứng dụng bổ sung.

## 7. Tài liệu tham khảo

- Spring Boot **3.3** Reference Guide – **Externalized Configuration**, đặc biệt các mục *PropertySource Order*, *Config Data Files*, *External Application Properties*, *Profile Specific Files* và *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework – `PropertySource`, `Environment` và `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html

**Ghi nhớ:** Trong Spring Boot 3.3, **nguồn liệt kê sau trong danh sách 15 mức có ưu tiên cao hơn**, nhưng Config Data còn có thứ tự con. Muốn giải thích một giá trị cụ thể, phải xét **nguồn hiện diện thật sự, thời điểm nạp và thứ tự bên trong cùng nhóm**.
