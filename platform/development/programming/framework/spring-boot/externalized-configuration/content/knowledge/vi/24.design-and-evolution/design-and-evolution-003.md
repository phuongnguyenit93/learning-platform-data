# Tránh sao chép toàn bộ cấu hình giữa các profile

Trong Spring Boot Externalized Configuration, `application.yml` và các file theo profile như `application-dev.yml`, `application-staging.yml`, `application-prod.yml` cho phép cùng một artifact chạy ở nhiều môi trường. Nhưng khi dự án lớn dần, một lỗi thiết kế thường xuất hiện: **copy toàn bộ `application.yml` sang từng file theo profile**, sau đó chỉ sửa vài giá trị. Cách làm ban đầu trông dễ hiểu, nhưng về lâu dài tạo ra hàng loạt bản sao khó đồng bộ.

Hãy tưởng tượng ứng dụng có hơn 100 property, trong đó chỉ khoảng 10 property khác nhau giữa development, staging và production. Nếu sao chép cả 100 property vào ba file, bạn sẽ phải duy trì 300 dòng cấu hình thay vì một bộ cấu hình nền và vài dòng chênh lệch. Khi đổi timeout, tên key, cấu trúc nested hoặc policy mặc định, một file có thể bị bỏ quên, khiến các môi trường dần có hành vi khác nhau mà không ai chủ động thiết kế.

Mục tiêu không phải loại bỏ mọi khác biệt môi trường. Mục tiêu là **chỉ khai báo khác biệt thực sự có chủ đích** và giữ phần chung ở **một nguồn rõ ràng**. Bài này trình bày cách tổ chức cấu hình DRY (Don't Repeat Yourself) của Spring Boot, phân biệt override và merge, cách xử lý list/map, profile groups, Config Data imports, secrets, validation, kiểm thử và từng bước refactor hệ thống đang có nhiều bản sao.

Ví dụ hướng đến Spring Boot 3.x, Java 17+. Cú pháp profile, Config Data và thứ tự ưu tiên cần được đối chiếu với phiên bản Spring Boot thật của dự án.

## 1. Vấn đề: mỗi profile là một bản sao toàn bộ cấu hình

Ví dụ cấu trúc ban đầu:

~~~text
src/main/resources/
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

File development:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 1s
    read-timeout: 3s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: true
~~~

File production:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 3s
    read-timeout: 10s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: false
~~~

Các key `spring.application.name`, `server.port`, `max-retries`, `retry.backoff` và `retry.enabled` bị copy dù giá trị giống nhau. Khi thay một setting chung như `max-retries` từ 2 thành 3, developer phải nhớ sửa mọi file. Một file bị bỏ sót sẽ tạo ra **configuration drift**.

Nhược điểm chính của mô hình copy toàn bộ:

- **Trùng dữ liệu:** một sự thật được lưu tại nhiều nơi.
- **Dễ lệch:** thay đổi phải được đồng bộ thủ công.
- **Khó review:** trong pull request, người đọc không biết dòng nào thực sự khác môi trường.
- **Khó nâng cấp:** rename key hoặc chia nested object cần sửa nhiều file.
- **Khó kiểm thử:** file dài có thể che những override vô tình.
- **Dễ lộ secret:** developer có thể copy password/API key vào file production rồi commit.
- **Khó rollback:** rollback một profile có thể vô tình trả lại nhiều setting không liên quan.

Giải pháp cốt lõi: **cấu hình chung nằm ở `application.yml`; file profile chỉ chứa phần khác biệt**.

## 2. Thiết kế đích: base configuration + profile-specific delta

Cấu trúc khuyến nghị cho một ứng dụng đơn giản:

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml
~~~

File nền:

~~~yaml
# application.yml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 2
  retry:
    backoff: 250ms
    enabled: true
  feature:
    new-checkout: false
~~~

File development:

~~~yaml
# application-dev.yml
app:
  client:
    connect-timeout: 1s
    read-timeout: 3s
  feature:
    new-checkout: true
~~~

File staging:

~~~yaml
# application-staging.yml
app:
  client:
    read-timeout: 7s
~~~

File production:

~~~yaml
# application-prod.yml
app:
  client:
    connect-timeout: 3s
    read-timeout: 10s
~~~

Điểm đáng chú ý: file profile không khai báo lại `spring.application.name`, `server.port` hoặc `max-retries` vì chúng không khác base.

Khi `prod` active và không có nguồn ưu tiên cao hơn ghi đè:

~~~text
spring.application.name = order-service
server.port             = 8080
app.client.max-retries  = 2
app.client.connect-timeout = 3s
app.client.read-timeout = 10s
app.retry.backoff       = 250ms
app.feature.new-checkout = false
~~~

**Không cần copy cả block `app.client` chỉ để đổi một field.** Với các scalar/nested object thông thường, key không được override có thể tiếp tục đến từ cấu hình nền, theo quy tắc Config Data precedence.

## 3. Nguyên tắc “chỉ ghi delta” là gì?

**Delta** là tập giá trị **khác** so với đường cấu hình mặc định, chứ không phải bản sao để người đọc thấy lại toàn bộ object.

Ví dụ một service dùng:

~~~yaml
# application.yml
app:
  invoice:
    currency: VND
    rounding-scale: 2
    retry-count: 3
    timeout: 5s
~~~

Ở production, nếu chỉ `timeout` cần là 12 giây:

~~~yaml
# application-prod.yml
app:
  invoice:
    timeout: 12s
~~~

Không cần viết lại `currency`, `rounding-scale` hoặc `retry-count`.

Một quy tắc chọn nơi đặt property:

| Câu hỏi | Nơi nên đặt |
| --- | --- |
| Giá trị có giống nhau ở mọi môi trường? | Base `application.yml` |
| Giá trị chỉ khác vì profile? | `application-{profile}.yml` |
| Giá trị phụ thuộc hạ tầng triển khai/region/tenant? | Config Data ngoài JAR, env hoặc config store được quản lý |
| Giá trị là password/token/private key? | Secret manager/secret mount/runtime channel |
| Giá trị bắt buộc có nhưng không có default an toàn? | Không hardcode; dùng validation/fail-fast |
| Giá trị phải thay đổi thường xuyên khi deploy? | Nguồn deploy có version và change control |
| Một khối cấu hình được chia sẻ nhiều service? | Shared Config Data/central config contract có kiểm soát |

**Base file không nhất thiết chứa mọi key.** Những property bắt buộc do deployment cấp có thể hoàn toàn không có giá trị trong repository. Base chỉ chứa những default an toàn và chính sách chung thực sự thuộc về artifact.

## 4. Cơ chế Spring Boot đọc file theo profile

Spring Boot hỗ trợ Config Data từ file như:

~~~text
application.properties
application.yml
application-dev.properties
application-dev.yml
application-prod.properties
application-prod.yml
~~~

Tài liệu cơ sở có thể được nạp cùng tài liệu theo profile được kích hoạt. Profile-specific values thường override những key tương ứng của file cơ sở trong nhóm Config Data tương ứng. Ngoài ra còn có các nguồn ưu tiên khác như command-line, JVM system properties và OS environment.

Ví dụ:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

hoặc cấp biến môi trường:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Khi profile `prod` được chọn, Spring Boot cân nhắc cấu hình dành cho `prod` và các nguồn khác theo precedence. **Không phải cứ file `application-prod.yml` tồn tại là nó được nạp**; cần đúng active/default profile và location.

Cần nhớ:

- **Active profile** quyết định tài liệu profile-specific nào có thể tham gia.
- **Default profile** có vai trò khi không có active profiles.
- File chứa key **không nhất thiết là nguồn thắng** nếu một nguồn cao hơn cũng cung cấp key đó.
- Một key trong file profile **không phải** giá trị cuối cùng khi CLI/env có override.
- Nhiều active profiles cần được hiểu theo thứ tự và Config Data rules, không xem các file là ba bản YAML deep-merge vô điều kiện.

## 5. Không đặt spring.profiles.active vào file profile-specific

Một anti-pattern:

~~~yaml
# application-prod.yml - không nên dùng để tự kích hoạt prod
spring:
  profiles:
    active: prod
~~~

Ý định “file prod tự bật prod” là vòng logic: file profile-specific được chọn **sau** khi Spring xác định các profile theo quy tắc phù hợp. Spring Boot đặt hạn chế đối với `spring.profiles.active`, `spring.profiles.include` và cấu hình profile groups trong tài liệu profile-specific hoặc tài liệu có `spring.config.activate.on-profile`.

Đặt profile activation ở nguồn đủ sớm, chẳng hạn:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Hoặc ở mức deployment:

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
~~~

Ví dụ Compose trên chỉ dùng để truyền runtime environment; không đồng nhất **Docker Compose profiles** với **Spring profiles**. `docker compose --profile debug` điều khiển service nào được chạy, không tự đặt `spring.profiles.active=debug`.

Khi cân nhắc base `application.yml` có `spring.profiles.active` cố định, nên cẩn trọng: artifact dùng chung nhiều môi trường thường nên để runtime/deployment quyết định profile, thay vì mặc định dùng production hay development mà không rõ chủ ý.

## 6. Không có nghĩa YAML được deep-merge tùy ý

Đây là điểm quan trọng nhất khi refactor: **đừng nghĩ Spring Boot “nối tất cả YAML thành một object rồi merge sâu mọi thứ”**.

Spring Boot giải quyết properties theo tên/key và precedence của các sources. Kết quả bind một object Java phụ thuộc cả:

- Cách YAML được flatten thành property paths.
- Kiểu Java target.
- Scalar, nested object, list hay map.
- Nguồn nào cung cấp từng key.
- Các converter, constructor binding và default.
- Một số cơ chế nguồn có thể thay cả collection.

Với scalar:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 10s
~~~

kết quả thường là `timeout=10s` và `max-retries=3` trong điều kiện không có override cao hơn.

Nhưng với list, **nếu nguồn cao hơn cung cấp một list, danh sách thường được thay thế chứ không được deep-merge từng phần tử với danh sách nguồn thấp hơn**. Với map, có thể có hành vi kết hợp entry theo key, trong đó giá trị trùng được nguồn cao hơn ghi đè. Hai loại collection không nên áp dụng cùng một suy luận.

## 7. Scalar: override đúng key và giữ các key khác

Ví dụ typed config:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
    Duration connectTimeout,
    Duration readTimeout,
    int maxRetries,
    boolean retryEnabled
) {}
~~~

Base:

~~~yaml
app:
  http:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
    retry-enabled: true
~~~

Production delta:

~~~yaml
app:
  http:
    read-timeout: 12s
~~~

Nếu `prod` active và không có source cao hơn:

~~~text
connectTimeout = 2s
readTimeout    = 12s
maxRetries     = 3
retryEnabled   = true
~~~

Không cần khai báo lại 3 giá trị không đổi trong file prod. Khi thêm field mới vào record, có thể đặt default phù hợp ở base hoặc qua `@DefaultValue`, thay vì mở ba profile files chỉ để copy giá trị.

**Một lưu ý:** nếu code dùng `@Value` kèm placeholder default hoặc getter tự fallback, kết quả consumer có thể chịu thêm logic ngoài Config Data. Việc giữ file DRY không có nghĩa mọi consumer đều đọc đúng một tập default nếu thiết kế code không thống nhất.

## 8. Nested object: tổ chức theo nhóm trách nhiệm

Cấu hình thường có các nhóm lồng nhau:

~~~yaml
app:
  notifications:
    mail:
      enabled: true
      retries: 2
      timeout: 3s
    webhook:
      enabled: true
      retries: 1
      timeout: 5s
~~~

Nếu development chỉ tắt webhook:

~~~yaml
# application-dev.yml
app:
  notifications:
    webhook:
      enabled: false
~~~

Đây là delta rõ ràng. Còn việc copy nguyên block `mail` và `webhook` sang development sẽ khiến developer khó nhìn ra lý do khác biệt.

Một record:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
    Channel mail,
    Channel webhook
) {
    public record Channel(
        boolean enabled,
        int retries,
        Duration timeout
    ) {}
}
~~~

Nếu các nested fields cần bắt buộc, hãy dùng validation thay vì kỳ vọng base luôn đủ trong mọi tình huống. Một profile-specific file chỉ khai báo `webhook.enabled` không thể sửa lỗi nếu một key bắt buộc khác vốn thiếu ở base.

## 9. List: vấn đề sao chép/merge rất dễ gây lỗi

Giả sử base có danh sách:

~~~yaml
# application.yml
app:
  servers:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Trong `application-prod.yml`, bạn muốn timeout của primary thành 5 giây nên viết:

~~~yaml
app:
  servers:
    - timeout: 5s
~~~

**Đừng giả định** kết quả cuối sẽ là hai servers từ base, trong đó primary được đổi timeout. Đối với binding list trong Spring Boot, nguồn cao ưu tiên thường **thay cả list**, không merge nested fields theo index. Có thể dẫn tới danh sách chỉ một phần tử và phần tử thiếu `name`/`url`.

Cách rõ ràng nếu muốn dùng list:

~~~yaml
# application-prod.yml
app:
  servers:
    - name: primary
      url: https://primary.example.test
      timeout: 5s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Ở đây việc lặp **toàn bộ list** là có lý do kỹ thuật. Nó không trái hoàn toàn với mục tiêu DRY: **đừng ép tránh duplication đến mức làm sai semantics list binding**.

Nếu những phần tử được nhận diện bằng tên và cần override từng phần tử, cân nhắc cấu trúc `Map`.

## 10. Map: chọn key định danh để override có chủ đích

Thay vì list:

~~~yaml
app:
  servers:
    - name: primary
      timeout: 2s
    - name: backup
      timeout: 4s
~~~

có thể dùng map:

~~~yaml
# application.yml
app:
  servers:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 4s
~~~

Production delta:

~~~yaml
# application-prod.yml
app:
  servers:
    primary:
      timeout: 5s
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ServerCatalog(
    Map<String, Server> servers
) {
    public record Server(
        URI url,
        Duration timeout
    ) {}
}
~~~

Spring Boot hỗ trợ map binding với cách tổng hợp entries theo key và precedence phù hợp. Trong nhiều trường hợp, `primary.timeout` từ source cao hơn có thể override field đó, còn `backup` vẫn đến từ base.

Tuy nhiên, **đừng coi map là deep merge không điều kiện cho mọi shape**. Sự kết hợp giữa scalar map values, nested POJOs, dotted keys và multiple sources có các quy tắc riêng; cần test actual binding trên target type và phiên bản Boot của dự án.

### Khi nào vẫn dùng List?

Dùng list khi **thứ tự phần tử có nghĩa**, cần lặp có thứ tự hoặc format bên ngoài tự nhiên là sequence. Dùng map khi **identity theo key ổn định** và cần override từng entry. Chuyển list thành map là thay đổi contract cấu hình, nên cần xem consumer và tài liệu triển khai.

## 11. Một profile-specific file không phải nơi nhân bản cấu trúc

Có hai cách tư duy khác nhau:

**Cách nhân bản:**

~~~text
application-dev.yml    -> toàn bộ hệ thống, tất cả key
application-prod.yml   -> toàn bộ hệ thống, tất cả key
application-test.yml   -> toàn bộ hệ thống, tất cả key
~~~

**Cách chia ownership:**

~~~text
application.yml         -> default an toàn và các giá trị chung
application-dev.yml     -> khác biệt dành cho dev
application-staging.yml -> khác biệt dành cho staging
application-prod.yml    -> khác biệt dành cho prod
runtime/secret manager  -> giá trị riêng từng deployment cần bảo mật
~~~

Ưu điểm của cách thứ hai không chỉ là ít dòng. Nó tạo ra **ngữ nghĩa dễ review**: mỗi dòng trong profile-specific file nói “chính sách này thực sự khác base”.

Khi các giá trị chung thay đổi, thường chỉ sửa một nơi. Khi thay đổi environment-specific setting, chỉ sửa đúng file profile hoặc deployment config liên quan.

## 12. Đặt default ở đúng tầng

Cấu hình nền có thể chứa các default phù hợp:

~~~yaml
app:
  retry:
    enabled: true
    max-attempts: 3
    backoff: 250ms
~~~

Trong JavaBean mutable:

~~~java
public class RetryProperties {
    private int maxAttempts = 3;
    // getter/setter...
}
~~~

Trong record constructor-bound:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.bind.DefaultValue;

public record RetryProperties(
    @DefaultValue("3") int maxAttempts,
    @DefaultValue("250ms") Duration backoff
) {}
~~~

Ba nơi có thể chứa giá trị mặc định: base Config Data, field initializer/constructor, và `@DefaultValue`. **Không nên đặt nhiều default khác nhau cho cùng một key mà không có lý do**.

Một policy thực dụng:

1. Những giá trị mặc định **vận hành chung**: đặt trong base `application.yml`.
2. Những giá trị mặc định **gắn với invariant của type**: cân nhắc constructor/`@DefaultValue`.
3. Những giá trị **bắt buộc do deployment cung cấp**: không tạo fallback giả; fail fast khi thiếu.
4. Những khác biệt **theo profile**: file profile chỉ ghi delta.

Nếu một default ở code và một default ở base cùng tồn tại, cần document đâu là nguồn thật và test trường hợp key bị thiếu. Không mặc định rằng Java default là một `PropertySource` có precedence thấp nhất; nó thuộc giai đoạn tạo/bind object.

## 13. Giá trị giống nhau hôm nay có nên luôn đặt ở base?

Không nhất thiết. DRY không có nghĩa phải gom mọi giá trị trùng nhau thành một default.

Ví dụ staging và prod hiện đều có:

~~~yaml
app:
  payment:
    sandbox-mode: false
~~~

Nhưng về chính sách, **mỗi môi trường cần một quyết định rõ ràng** về việc gọi sandbox hay production payment gateway. Nếu default sai có thể gây giao dịch thật ngoài ý muốn, đặt giá trị bắt buộc theo môi trường hoặc dùng validation là lựa chọn tốt hơn, dù hiện tại xuất hiện trùng dòng.

Một câu hỏi cần đặt:

> Nếu ngày mai một môi trường quên khai báo key này, ứng dụng nên dùng default chung hay phải từ chối khởi động?

Nếu câu trả lời là **từ chối**, đừng đưa một default “tiện tay” vào base chỉ để giảm số dòng. DRY phải phục vụ an toàn và rõ nghĩa, không phải mục tiêu số dòng thấp nhất.

Các key liên quan billing, authentication, encryption, region tuân thủ hoặc dữ liệu người dùng có thể cần explicitness nhiều hơn timeout thông thường.

## 14. Secrets không thuộc về bản sao file profile

Một anti-pattern:

~~~yaml
# application-prod.yml - KHÔNG COMMIT CREDENTIAL THẬT
spring:
  datasource:
    username: orders_app
    password: real-secret-here
~~~

Có hai vấn đề: copy password vào source repository và tạo nhiều bản sao khi profile/environments tăng.

Cấu hình tốt hơn có thể giữ metadata không bí mật trong file:

~~~yaml
# application.yml
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
~~~

và production cấp:

~~~text
SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/orders
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=<injected-through-secret-channel>
~~~

Trong ví dụ, giá trị placeholder không phải credential thật. Runtime nên cấp secret qua secret manager, file mount hoặc cơ chế kiểm soát phù hợp.

**Profile không phải security boundary.** `application-prod.yml` có trong JAR/repository không tự an toàn hơn `application.yml`. Không đặt secret thật trong file được commit, kể cả file theo profile.

## 15. Dùng placeholder cẩn thận

Một pattern có thể dùng để nối thông số:

~~~yaml
app:
  client:
    base-url: "\${CLIENT_BASE_URL:https://localhost:8443}"
    timeout: "\${CLIENT_TIMEOUT:5s}"
~~~

Ý nghĩa: Spring giải quyết placeholder từ Environment; nếu không có property được tham chiếu theo cách tương ứng, fallback có thể được dùng.

Tuy nhiên, khi đã có `application.yml` và file theo profile, việc rải nhiều placeholder defaults vào từng file dễ tạo **hai tầng default**:

- Default ở placeholder.
- Default ở profile-specific override.
- Default ở constructor binding.
- Default do JavaBean field initializer.

Nên đặt policy có chủ đích và tránh viết cùng một default ở ba nơi. Với secret bắt buộc, **đừng dùng fallback credential yếu** như `\${API_TOKEN:demo}` trong artifact chung.

## 16. Config Data import: tái sử dụng cấu hình có chủ đích

Khi một khối cấu hình quá lớn để nằm trong một `application.yml`, có thể chia file và import qua Spring Boot Config Data:

~~~text
src/main/resources/
  application.yml
  config/
    client-defaults.yml
    messaging-defaults.yml
~~~

Ví dụ:

~~~yaml
# application.yml
spring:
  config:
    import:
      - classpath:config/client-defaults.yml
      - classpath:config/messaging-defaults.yml
~~~

Một file:

~~~yaml
# config/client-defaults.yml
app:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-retries: 3
~~~

Cách chia này giúp phân nhóm ownership, nhưng **không cần làm với mọi dự án nhỏ**. Nhiều file import có thể làm graph cấu hình khó hiểu nếu không có naming contract và tài liệu thứ tự.

Trong Spring Boot, imported documents tham gia Config Data theo các quy tắc precedence riêng; không đơn thuần là nối raw YAML text. Đặc biệt, **imported values có thể ghi đè tài liệu khai báo import** theo quy tắc của Boot, và profile-specific variants của imported config có thể được cân nhắc.

Hãy test khi có key trùng giữa file gốc và file import. Đừng dùng import để vô tình tạo một tầng override ẩn mà reviewer không biết.

## 17. Khi nào dùng import thay vì profile-specific file?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Một vài scalar khác giữa dev và prod | `application-dev.yml` / `application-prod.yml` |
| Nhóm default dùng chung lớn, có ownership riêng | Config Data file được import |
| Cấu hình dành cho region hoặc deployment | External Config Data, env hoặc config store |
| Cần shared config nhiều ứng dụng | Centralized configuration có version/ownership |
| Nhóm chứa secrets | Secret manager/configtree/file mount |
| Cần bật/tắt bean theo môi trường | `@Profile` hoặc conditional config rõ ràng |
| Cần tập hợp các profile logic | `spring.profiles.group.*` |
| Cần thiết lập một giá trị ở mọi nơi | Base `application.yml` |

Chọn ít cơ chế nhất vẫn đủ rõ. Không cần trộn profile groups, import, environment variables, placeholders và custom EnvironmentPostProcessor cho một timeout đơn giản.

## 18. Profile groups: gom những “capability profiles”

Trong các hệ thống có nhiều profile logic, một môi trường có thể bao gồm những capability như `prod`, `metrics` và `remote-cache`.

Có thể cấu hình profile group ở tài liệu không profile-specific:

~~~yaml
# application.yml
spring:
  profiles:
    group:
      production:
        - prod
        - metrics
        - remote-cache
~~~

Khi kích hoạt:

~~~bash
java -jar app.jar --spring.profiles.active=production
~~~

Spring Boot có thể mở rộng group để kích hoạt các profile được khai báo. Điều này giảm việc viết lại cùng danh sách profiles trong nhiều deployment commands.

Nhưng **profile groups không phải cách để thay một giá trị scalar** như timeout; chúng phù hợp khi muốn tổ chức một nhóm profile theo ý nghĩa vận hành.

Một rủi ro khác: nhóm profile làm tăng số tài liệu được nạp. Nếu nhiều tài liệu cùng override một key, cần test thứ tự và giá trị cuối. Không coi group là cơ chế merge “mọi file đều bổ sung ngang nhau”.

### Không đặt group ở tài liệu profile-activated

Các thuộc tính điều khiển profile như `spring.profiles.group.*` có hạn chế về vị trí khai báo; đặt chúng trong non-profile-specific document phù hợp để tránh vòng phụ thuộc lựa chọn profile.

## 19. Multi-document YAML với on-profile

Thay vì nhiều file, một file `application.yml` có thể chứa nhiều YAML documents:

~~~yaml
app:
  client:
    timeout: 5s
    max-retries: 3

---
spring:
  config:
    activate:
      on-profile: dev

app:
  client:
    timeout: 2s

---
spring:
  config:
    activate:
      on-profile: prod

app:
  client:
    timeout: 10s
~~~

Trong ví dụ, tài liệu thứ nhất là base; tài liệu tiếp theo chỉ được xét khi profile activation phù hợp. Đây vẫn là **cấu hình base + delta**, chỉ khác cách đóng gói file.

Ưu điểm:

- Người đọc thấy base và overrides trong cùng file.
- Ít file hơn đối với dự án có số profile nhỏ.

Nhược điểm:

- File dễ dài khi nhiều môi trường.
- Dễ bỏ sót delimiter `---`.
- Dễ nhầm lẫn khi profile groups/imports phức tạp.
- Quy tắc đặt `spring.profiles.active` trong tài liệu kích hoạt theo profile vẫn cần tuân thủ.

Chọn một convention của dự án. Không đồng thời sao chép cùng override vào `application-prod.yml` và một YAML document `on-profile: prod` trừ khi có lý do rõ và precedence đã được test.

## 20. Không xem on-profile là cơ chế bảo mật

Ví dụ:

~~~yaml
---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    client-secret: real-secret
~~~

Đây vẫn là secret thật nằm trong file config; profile-activation chỉ điều khiển khi nào document tham gia, **không mã hóa giá trị**. File có thể được đọc từ repository hoặc artifact.

Thay vì đặt credential trong YAML document theo profile, hãy cung cấp từ secret store/runtime với key rõ ràng. Tài liệu profile có thể chứa **tên endpoint**, **timeout**, **feature toggles** hoặc thông số non-secret cần cho production.

## 21. application-local, application-dev và Git

Một dự án cần chạy local:

~~~text
application.yml
application-dev.yml
application-prod.yml
application-local.yml
~~~

`application-local.yml` có thể chứa cổng, URL mock server và feature flags dành cho laptop, nhưng không nên chứa credentials thật được commit.

Nếu mỗi developer cần cấu hình riêng:

- Dùng env vars hoặc file local nằm ngoài repo.
- Có `.env.example` hoặc file sample không chứa secret.
- Dùng `.gitignore` để tránh commit nhầm file chưa theo dõi, nhưng nhớ rằng nó không xóa file đã được Git track trước đó.
- Không tạo thêm một profile cho từng cá nhân trong repository chính nếu chỉ khác vài giá trị tạm thời.

Một pattern là profile `local` cho defaults chung của development và các overrides cá nhân đến từ biến môi trường. Tách **team defaults** khỏi **machine secrets/overrides**.

## 22. Đừng copy application-prod.yml thành application-staging.yml

Một thói quen nguy hiểm là lấy file production, copy thành staging rồi sửa URL. Điều này có thể mang theo:

- Feature flags production chưa nên bật ở staging.
- Logging level thấp khiến staging khó debug.
- Callback URL hoặc queue name trỏ về production.
- Resource limits/quota quá lớn.
- Credentials/cert paths không phù hợp.
- Profile activation sai.
- Cấu hình chịu ràng buộc pháp lý/region không đúng.

Thay vì copy, hãy bắt đầu từ base và **liệt kê khác biệt thực sự của staging**:

~~~yaml
# application-staging.yml
app:
  external-api:
    base-url: https://sandbox.example.test
  job:
    concurrency: 2
  feature:
    new-checkout: true
~~~

Sau đó test những property bắt buộc và môi trường bên ngoài. Một file staging chỉ có vài dòng không phải thiếu nội dung nếu base và runtime đã cung cấp phần còn lại.

## 23. Kiểm soát sự khác biệt có chủ đích

Một bảng contract có thể giúp đội ngũ biết key nào được phép khác giữa môi trường:

| Key | Base | Dev | Staging | Prod | Lý do |
| --- | --- | --- | --- | --- | --- |
| `app.client.timeout` | 5s | 2s | 7s | 12s | Network latency/SLA |
| `app.retry.max-attempts` | 3 | inherit | inherit | inherit | Chính sách chung |
| `app.feature.new-checkout` | false | true | true | false | Rollout |
| `app.job.concurrency` | 4 | 1 | 2 | 8 | Capacity |
| `spring.datasource.password` | Không có | Secret dev | Secret staging | Secret prod | Credential tách môi trường |
| `app.payment.mode` | Bắt buộc | sandbox | sandbox | live | Cần chọn rõ mode |

Từ `inherit` chỉ mang nghĩa **file profile không khai báo key và source thấp hơn có thể cung cấp giá trị**. Đây không phải literal YAML cần viết.

Một tài liệu contract riêng giúp review, nhưng **tránh sinh thêm một bản sao chứa toàn bộ values bí mật**. Ghi tên key, owner, policy và lý do khác biệt, không lưu secret.

## 24. Type-safe configuration giảm trùng lặp trong code

Nếu service dùng:

~~~java
@Value("\${app.client.timeout:5s}")
private Duration timeout;
~~~

và một bean khác dùng:

~~~java
@Value("\${app.client.timeout:3s}")
private Duration timeout;
~~~

thì hai consumer đã có **default khác nhau**. Cấu hình file có DRY vẫn chưa đủ; code đang tạo duplicate policy.

Một hướng nhất quán:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Đăng ký:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {}
~~~

Inject vào các service cần đọc:

~~~java
@Service
public class ClientScheduler {
    private final ClientProperties options;

    public ClientScheduler(ClientProperties options) {
        this.options = options;
    }

    public Duration timeout() {
        return options.timeout();
    }
}
~~~

Một typed bean giúp tập trung contract, conversion và validation thay vì nhiều `@Value` rải rác với default riêng. Nếu cần custom conversion, cân nhắc `@ConfigurationPropertiesBinding` thay vì thay cả registry chuyển đổi.

## 25. Validation để tránh base default che thiếu cấu hình

Với cấu hình bắt buộc:

~~~java
import java.net.URI;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
    @NotNull URI endpoint,
    @NotBlank String merchantId
) {}
~~~

Ứng dụng có thể để base không có `endpoint` và `merchant-id` nếu mỗi deployment bắt buộc cấp riêng, rồi fail fast khi thiếu.

Để Bean Validation hoạt động, cần provider phù hợp, ví dụ `spring-boot-starter-validation` trong Spring Boot 3.x, và đăng ký configuration properties bean đúng cách.

**Đừng thêm default URL production vào base chỉ để app khởi động**. Một môi trường test/staging thiếu config mà tự gọi production là lỗi nghiêm trọng hơn việc startup thất bại rõ ràng.

Cần phân biệt:

- **Missing required config**: validation/policy.
- **Invalid format**: conversion/binding.
- **Wrong profile/source**: selection/precedence.
- **Value valid nhưng sai môi trường**: cần deployment contract và test bổ sung.

## 26. Phân biệt validation và default

Một giá trị như:

~~~yaml
app:
  worker:
    concurrency: 0
~~~

có thể chuyển thành `int` hợp lệ. Nhưng nếu ràng buộc yêu cầu `@Min(1)`, startup nên thất bại khi validation được bật.

Model:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
    @Min(1) @Max(32) int concurrency
) {}
~~~

Không dùng `ignoreInvalidFields` hay bỏ constraint để làm cho một profile sai tiếp tục chạy.

Một default chung 4 workers có thể phù hợp. Nhưng nếu production cần concurrency được sizing theo capacity, buộc khai báo riêng là hợp lý. DRY không loại trừ những **exception cần được thể hiện rõ để tránh fail-open**.

## 27. Thêm field mới: thay một nơi và kiểm toàn bộ profile

Giả sử ban đầu model:

~~~java
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Sau khi nâng cấp:

~~~java
public record ClientProperties(
    Duration timeout,
    int maxRetries,
    boolean circuitBreakerEnabled
) {}
~~~

Cách copy toàn bộ: thêm `circuit-breaker-enabled` vào dev, staging, prod và có thể bỏ sót một file.

Cách base + delta:

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
    circuit-breaker-enabled: true
~~~

Chỉ khi một môi trường cần khác:

~~~yaml
# application-dev.yml
app:
  client:
    circuit-breaker-enabled: false
~~~

Tuy nhiên, nếu field mới có tác động bảo mật hoặc bắt buộc quyết định riêng từng môi trường, cần explicit config/test. **Một default dùng chung phải được review theo ngữ nghĩa, không thêm máy móc**.

## 28. Đổi tên key: tránh để hai thế hệ cấu hình sống song song

Ví dụ đổi:

~~~text
app.client.request-timeout
    -> app.client.read-timeout
~~~

Với mô hình copy toàn bộ, cả ba file có thể chưa được đổi nhất quán; một file giữ key cũ và Bean mới không đọc nó.

Migration:

1. Liệt kê các nguồn thực sự cung cấp key cũ: base, profile, env, CLI, external file, Helm/Compose.
2. Định nghĩa tên canonical mới và tác động tới Java model.
3. Quyết định giai đoạn tương thích nếu cần (alias/converter/migration policy).
4. Đổi base và **các delta thực sự có key cũ**.
5. Cập nhật deployment variables theo quy tắc canonical.
6. Test các profile và nguồn runtime quan trọng.
7. Loại bỏ key cũ theo kế hoạch phát hành.

Không mặc định relaxed binding sẽ hiểu một từ mang ngữ nghĩa mới. `request-timeout` và `read-timeout` là **hai tên khác nhau**, không phải chỉ khác dấu gạch ngang.

## 29. Nhiều active profiles: không nên dựa vào trùng lặp để “merge”

Giả sử ứng dụng active:

~~~text
spring.profiles.active=prod,metrics
~~~

và có:

~~~yaml
# application-prod.yml
app:
  telemetry:
    endpoint: https://metrics-prod.example.test
    sampling-rate: 0.1
~~~

~~~yaml
# application-metrics.yml
app:
  telemetry:
    sampling-rate: 1.0
~~~

Lúc này cần xác định **source order và quy tắc “last wins” tương ứng trong Spring Boot version thực**. Không coi hai file là một union không thứ tự; một key trùng có thể bị profile được ưu tiên hơn ghi đè.

Nếu hai capability profiles có thể active cùng nhau, nên hạn chế các key trùng giữa chúng hoặc document ưu tiên rõ. Cấu hình theo capability nên có **vùng ownership riêng**, ví dụ `app.telemetry.*` của profile metrics, tránh cùng sửa `app.payment.*` của prod.

Test profile combinations là cần thiết khi chúng xuất hiện thực tế, không chỉ test từng profile riêng.

## 30. Tách config liên quan hạ tầng khỏi business flags

Một file profile có thể chứa cả:

~~~yaml
app:
  client:
    timeout: 3s
  feature:
    new-checkout: true
  billing:
    tax-policy: strict
~~~

Các nhóm này có owner/lifecycle khác nhau:

- Timeout phụ thuộc network và vận hành.
- Feature flag có thể do release/rollout quản lý.
- Tax policy có thể chịu yêu cầu nghiệp vụ/pháp lý.

Không nhất thiết dùng cùng một cơ chế override hoặc cùng người phê duyệt cho cả ba. Base + delta giúp giảm duplicate, nhưng **ownership** mới giúp các thay đổi được review đúng.

Đối với feature flags thay thường xuyên, cân nhắc một hệ thống feature management phù hợp khi nhu cầu thực tế đòi hỏi; không tự biến Spring profiles thành cơ chế điều phối mọi rollout runtime.

## 31. Giới hạn của “một file base khổng lồ”

DRY không đồng nghĩa tất cả cấu hình phải nằm trong một `application.yml` dài hàng nghìn dòng. Khi file quá lớn:

- Tổ chức rõ prefix theo module, ví dụ `app.client`, `app.worker`, `app.notifications`.
- Xem có thể chia Config Data import theo chủ đề hay không.
- Đặt mỗi nhóm có một owner.
- Tránh các file nhỏ trùng nhau hoặc circular imports.
- Duy trì tài liệu effective configuration và test.

Tuy nhiên, nếu import file chỉ có 3 property, nhiều lớp indirection có thể làm việc tìm nguồn khó hơn. **Tối ưu cho khả năng hiểu**, không cho số lượng file hay số dòng thấp nhất.

## 32. Tránh YAML anchors như giải pháp mặc định cho multi-profile

YAML có cú pháp anchors và aliases, ví dụ:

~~~yaml
defaults: &defaults
  timeout: 5s
  max-retries: 3
~~~

Nhưng **YAML anchors không phải cơ chế chia sẻ dữ liệu giữa các file độc lập** như `application.yml` và `application-prod.yml`. Phạm vi xử lý anchors thuộc tài liệu/parser YAML, không thay thế Spring Boot Config Data precedence.

Không dựa vào anchor cross-file hoặc merge key YAML để giải quyết mọi vấn đề DRY. Với Spring Boot, ưu tiên **base file + profile-specific delta**; cơ chế đó trực tiếp biểu đạt cách application chọn property.

Nếu dùng anchors trong cùng YAML document cho một số lặp cục bộ, cần hiểu parser đang sử dụng và cách Spring Boot flatten kết quả; đừng dùng chúng để tránh test precedence.

## 33. Sửa list duplication: cân nhắc profile riêng cho danh mục

Có những list lớn thực sự khác toàn bộ giữa môi trường:

~~~yaml
# application.yml
app:
  allowed-regions:
    - ap-southeast-1
    - ap-east-1
~~~

Production:

~~~yaml
# application-prod.yml
app:
  allowed-regions:
    - ap-southeast-1
    - eu-west-1
    - us-east-1
~~~

Nếu danh sách đó là một contract không thể merge từng phần tử theo tên, việc khai báo toàn bộ list cho mỗi profile có thể là **lựa chọn đúng**.

Nếu list chỉ khác một field của một đối tượng có identity ổn định, cân nhắc chuyển thành map như `app.regions.primary` để giảm duplicate.

Một hướng khác là giữ whole-list config trong một **file theo môi trường** được quản lý tập trung và import đúng location, thay vì copy toàn bộ file application profile. Mục tiêu là chọn **đơn vị override phù hợp**, không phải tránh mọi dòng bị lặp.

## 34. Bắt đầu refactor từ bảng key khác biệt

Với hệ thống cũ có ba file gần giống nhau, đừng xóa các dòng trùng lặp ngay mà chưa hiểu semantics. Quy trình an toàn:

1. Lập danh sách các key hiện đang khai báo theo từng file.
2. Phân loại scalar, nested object, list và map.
3. Xác định giá trị giống nhau giữa profiles.
4. Xác định giá trị **cố tình giống nhau** nhưng phải khai báo bắt buộc.
5. Tìm secret và giá trị đã nằm sai nguồn.
6. Xác định các external overrides (env/CLI/import) ngoài repository.
7. Đề xuất cấu hình base + delta.
8. Với list, quyết định giữ whole-list override hoặc đổi model có identity theo map.
9. Thêm test giá trị hiệu lực theo từng profile.
10. Thực hiện thay đổi nhỏ rồi so sánh kết quả trước/sau.

**Không dùng phép so sánh text đơn thuần làm toàn bộ kết luận.** Hai file YAML có thể dùng key order khác nhau, placeholder, profiles, list binding hoặc imports khiến giá trị thực tế khác nội dung nhìn thấy.

## 35. Migration ví dụ trước và sau

**Trước:**

~~~text
application-dev.yml
  app.client.timeout=2s
  app.client.max-retries=3
  app.worker.concurrency=1
  app.feature.new-checkout=true

application-prod.yml
  app.client.timeout=12s
  app.client.max-retries=3
  app.worker.concurrency=8
  app.feature.new-checkout=false
~~~

**Sau:**

~~~yaml
# application.yml
app:
  client:
    timeout: 5s
    max-retries: 3
  worker:
    concurrency: 4
  feature:
    new-checkout: false
~~~

~~~yaml
# application-dev.yml
app:
  client:
    timeout: 2s
  worker:
    concurrency: 1
  feature:
    new-checkout: true
~~~

~~~yaml
# application-prod.yml
app:
  client:
    timeout: 12s
  worker:
    concurrency: 8
~~~

Trước/sau, giá trị effective của dev và prod phải **được kiểm chứng thực tế**. Có thể chọn base defaults theo môi trường mặc định của dự án, nhưng không được vô tình thay đổi contract của một profile đang được triển khai.

Nếu trước kia app không có base `application.yml` và chạy khi không profile, việc thêm default có thể làm hành vi “no active profile” thay đổi. Đây là một scenario cần test riêng trong migration.

## 36. Test cấu hình theo profile với @SpringBootTest

Model:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    Duration timeout,
    int maxRetries
) {}
~~~

Với `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` đã đăng ký record, có thể test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("prod")
class ProdConfigTest {

    @Autowired
    ClientProperties client;

    @Test
    void appliesOnlyIntendedProdOverride() {
        assertThat(client.timeout())
            .isEqualTo(Duration.ofSeconds(12));
        assertThat(client.maxRetries())
            .isEqualTo(3);
    }
}
~~~

Test dùng file profile và resource của test context; nó minh họa việc kiểm **giá trị hiệu lực** chứ không kiểm số dòng YAML.

Đối với dev:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class DevConfigTest {

    @Autowired
    ClientProperties client;

    @Test
    void keepsBaseRetryPolicy() {
        assertThat(client.timeout())
            .isEqualTo(Duration.ofSeconds(2));
        assertThat(client.maxRetries())
            .isEqualTo(3);
    }
}
~~~

Cần bảo đảm test không có `@SpringBootTest(properties=...)` hoặc test property source vô tình ghi đè những key đang muốn kiểm. Nếu runtime thực tế cấp env/CLI ngoài source repository, hãy thêm test deployment contract ở tầng thích hợp.

## 37. ApplicationContextRunner để test một cấu hình nhỏ

Một test nhỏ không cần khởi chạy toàn web server có thể dùng `ApplicationContextRunner`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class ClientDefaultsTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void baseValuesBindWhenNoOverride() {
        runner
            .withPropertyValues(
                "app.client.timeout=5s",
                "app.client.max-retries=3"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                ClientProperties props =
                    context.getBean(ClientProperties.class);
                assertThat(props.maxRetries()).isEqualTo(3);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {}
}
~~~

Test này kiểm binding với các input được cấp tường minh. **Nó không mặc định chứng minh `application-prod.yml` đã được nạp**, vì `ApplicationContextRunner` không tự mô phỏng toàn bộ đường Config Data như full Spring Boot startup trong mọi setup.

Dùng `@SpringBootTest` hoặc integration setup tương ứng để kiểm Config Data và profile thực, còn `ApplicationContextRunner` phù hợp kiểm conversion, defaults và behavior của một bean configuration nhỏ.

## 38. Test matrix khi có nhiều môi trường

Một ma trận hữu ích:

| Scenario | Profile | Timeout | Retries | Concurrency | Feature |
| --- | --- | --- | --- | --- | --- |
| Base/default | Không active cụ thể | 5s | 3 | 4 | false |
| Development | dev | 2s | 3 | 1 | true |
| Staging | staging | Theo delta staging | 3 | Theo delta staging | Theo policy |
| Production | prod | 12s | 3 | 8 | false |
| Production + metrics | prod,metrics | Không đổi ngoài ý định | 3 | 8 | false |
| Missing required secret | prod, không cấp secret | Startup fail rõ ràng | — | — | — |
| CLI override | prod + timeout CLI | CLI wins | 3 | 8 | false |

Bảng này chỉ minh họa, cần chỉnh theo contract thực tế. **Test cả key phải giữ nguyên và key được override**: chỉ test mỗi timeout prod không phát hiện được maxRetries đã vô tình bị copy thành một giá trị khác.

Với sensitive properties, test có thể assert “thiếu thì fail” mà không sử dụng credentials production. Dùng fake/sandbox secret trong test context.

## 39. Tự động phát hiện configuration drift

DRY giúp giảm drift nhưng không loại bỏ mọi rủi ro. CI có thể kiểm:

- Mỗi key mới có owner và documented behavior.
- Không xuất hiện deprecated key còn được sử dụng trong profile files.
- Không có secret thật trong resources.
- Không có accidental duplication của các scalar chung.
- Những key critical có validation.
- Các test theo profile vẫn pass.
- Cấu trúc list/map bind đúng theo target Java.
- Không có profile-specific documents khai báo profile activation trái quy tắc.

Một tool tĩnh có thể so key sets, nhưng **không được tự sửa/xóa các key trùng khi chưa hiểu semantics**. Bản sao đôi khi là chủ đích, đặc biệt với lists hoặc cấu hình bắt buộc từng môi trường.

Nếu có nhiều service chia sẻ một config library, hãy áp dụng versioning và compatibility rules thay vì sửa một file shared khiến hàng chục service bị ảnh hưởng cùng lúc.

## 40. Khi dùng centralized configuration

Một organization có nhiều microservices có thể cân nhắc kho config tập trung (ví dụ Spring Cloud Config hoặc dịch vụ configuration của cloud).

Mục tiêu có thể là:

- Chia sẻ những giá trị mặc định/common policies theo môi trường.
- Phân quyền thay đổi và audit.
- Version/rollback cấu hình.
- Tách config khỏi artifact.
- Hạn chế nhiều bản sao giữa repositories.

Nhưng đây **không phải** một tính năng được Spring Boot lõi tự động cung cấp chỉ vì dùng `spring.config.import`. Những integration cụ thể cần dependency, server/backend và security configuration riêng.

Centralized config có thể trở thành nguồn ghi đè mới, nên phải tài liệu rõ **precedence với packaged/external Config Data, env và CLI**. Nếu không, việc tránh duplication trong repo chỉ chuyển sự khó hiểu sang một tầng runtime khác.

## 41. Design rules cho nâng cấp nhiều profile

Một bộ quy tắc thực dụng cho nhóm:

1. **Chỉ có một base** chứa các giá trị chung an toàn.
2. **Profile file chỉ chứa delta**, không copy toàn bộ cây cấu hình.
3. **Tách secret** khỏi repository và profile files.
4. **Đối với list**, thay toàn danh sách có chủ đích hoặc đổi model sang map theo identity.
5. **Map override phải có test**, không giả định deep merge trong mọi trường hợp.
6. **Cấu hình quan trọng phải explicit** nếu thiếu value cần làm startup fail.
7. **Một key có một owner**: biết module nào quản lý contract.
8. **Không dùng profile activation trong tài liệu profile-specific**.
9. **Đặt chuẩn tên key** theo kebab-case canonical, kiểm env naming.
10. **Test giá trị hiệu lực**, không chỉ so sánh text YAML.
11. **Tách deployment-specific settings** khỏi defaults của artifact.
12. **Hạn chế layers**: dùng profile/import/group khi thật sự cần.
13. **Review thay đổi liên quan nhiều profile** như một migration contract.
14. **Ghi rõ giá trị kế thừa** và các trường hợp profile combinations.
15. **Đừng tối ưu số dòng bằng cách làm mất fail-fast**.

## 42. Troubleshooting: “đã xóa dòng duplicate nhưng giá trị sai”

Nếu sau refactor, một environment hoạt động khác trước, đi theo trình tự:

1. Xác định key canonical và target Java field.
2. So sánh giá trị hiệu lực trước/sau migration trong cùng profile và cùng nguồn deploy.
3. Kiểm source ứng viên: file cơ sở, file profile, external Config Data, import, env và CLI.
4. Xác nhận active/default profiles thực tế.
5. Kiểm xem key có nằm trong list bị thay thế không.
6. Kiểm map nested có cấu trúc đúng không.
7. Kiểm constructor default, `@DefaultValue` hoặc field initializer có đổi behavior không.
8. Kiểm missing key đang bị fallback hay validation fail.
9. Kiểm artifact/container mới đã được deploy và process restart chưa.
10. Kiểm consumer có copy/snapshot value ở thời điểm trước đó không.
11. Kiểm origin/source name nếu công cụ và phân quyền cho phép.
12. Sửa đúng tầng rồi rerun các test profile và case deployment.

Không dump nguyên Environment ở production: property source có thể chứa password/token. Với Actuator `env` và `configprops`, bảo vệ endpoint, hạn chế truy cập và tránh bật hiển thị giá trị nhạy cảm.

## 43. Anti-pattern: staging kế thừa production một cách gián tiếp

Có dự án định nghĩa cấu hình staging bằng cách import trực tiếp toàn bộ production settings rồi ghi đè vài giá trị:

~~~yaml
# application-staging.yml
spring:
  config:
    import: classpath:application-prod.yml
~~~

Đây thường là thiết kế dễ gây sai sót, vì staging **không phải một bản sao production thiếu vài key**. Nó có thể vô tình nhận endpoint, feature flag, policy hoặc tài nguyên production.

Thay vì kế thừa một environment khác, **cả staging và production nên kế thừa base trung lập**, sau đó khai báo delta độc lập. Nếu hai môi trường thực sự chia sẻ một khối non-secret rõ ràng, có thể tách khối đó thành common file/module với tên và ownership thích hợp, không gọi nó là `application-prod.yml`.

Cùng một nguyên tắc: **môi trường là các biến thể đồng cấp của base, không phải một chuỗi subclass mơ hồ**.

## 44. Anti-pattern: đặt giá trị thường vào từng Kubernetes/Compose manifest

Một ứng dụng có base `application.yml`:

~~~yaml
app:
  retry:
    max-attempts: 3
    backoff: 250ms
~~~

Nhưng Compose, Helm values và CI pipeline đều khai báo lại cùng hai giá trị. Khi đổi policy retry, một nơi bị bỏ quên.

Nên quyết định:

- Nếu đó là **default của ứng dụng**, để trong base.
- Nếu deployment cần override do capacity/network, khai báo ở deployment.
- Nếu đó là secret, quản lý bằng kênh secret.
- Nếu đó là chính sách phải explicit từng môi trường, tài liệu và validate.

Không tự truyền toàn bộ `application.yml` thành environment variables chỉ để “đồng bộ”; điều đó tạo thêm một bản sao cần duy trì và có thể thay precedence bất ngờ.

## 45. Bài tập 1 — Chuyển file copy thành delta

Base cũ:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 5m
    max-entries: 200
~~~

Production copy:

~~~yaml
app:
  cache:
    enabled: true
    ttl: 10m
    max-entries: 200
~~~

**Yêu cầu:** viết `application-prod.yml` theo delta.

**Đáp án:**

~~~yaml
app:
  cache:
    ttl: 10m
~~~

`enabled` và `max-entries` vẫn từ base nếu không có nguồn cao hơn ghi đè.

## 46. Bài tập 2 — List override

Base có hai endpoints, production muốn đổi timeout của endpoint đầu tiên. Developer chỉ ghi:

~~~yaml
app:
  endpoints:
    - timeout: 10s
~~~

**Đáp án:** không an toàn nếu muốn giữ nguyên toàn list. Với Spring Boot list binding, nguồn cao hơn thường thay cả list, không deep merge các phần tử. Viết lại list đầy đủ hoặc thiết kế map theo endpoint ID nếu muốn override từng entry.

## 47. Bài tập 3 — Map thay list

Base:

~~~yaml
app:
  endpoints:
    primary:
      timeout: 2s
      url: https://primary.example.test
    backup:
      timeout: 5s
      url: https://backup.example.test
~~~

Production:

~~~yaml
app:
  endpoints:
    primary:
      timeout: 9s
~~~

**Đáp án:** map có thể phù hợp hơn list khi identity ổn định và cần override theo key, nhưng cần kiểm Spring Boot Binder với target model thực tế. Không tự kết luận mọi nested map có cùng hành vi merge.

## 48. Bài tập 4 — Missing secret

Production không có `spring.datasource.password`. Developer định đưa password demo vào base để tránh startup fail.

**Đáp án:** không làm vậy. Credential cần được cấp an toàn ở runtime; nếu bắt buộc, fail fast khi thiếu. Giảm duplication không quan trọng hơn bảo mật.

## 49. Bài tập 5 — Profile groups

Một deployment cần luôn bật `prod`, `metrics` và `remote-cache`. Có thể dùng gì?

**Đáp án:** một group `spring.profiles.group.production` được khai báo trong non-profile-specific document, sau đó kích hoạt `production`. Kiểm các xung đột key giữa profiles trước khi deploy.

## 50. Bài tập 6 — Multi-document YAML

Một file có base document và document `spring.config.activate.on-profile=prod`. Developer khai báo `spring.profiles.active=prod` bên trong document `on-profile: prod`.

**Đáp án:** không dùng tài liệu profile-activated để tự bật profile; Spring Boot hạn chế profile activation properties ở loại tài liệu này. Cấp active profile từ deployment hoặc nguồn đủ sớm.

## 51. Bài tập 7 — Refactor và @Value

Hai service dùng `@Value` với cùng key nhưng fallback lần lượt `2s` và `5s`.

**Đáp án:** dù YAML files đã DRY, code vẫn duplicate policy. Ưu tiên typed `@ConfigurationProperties` chung với default rõ; cần test khi key thiếu.

## 52. Bài tập 8 — Đổi key

Tên `app.client.request-timeout` đổi thành `app.client.read-timeout`. Một file dev vẫn dùng key cũ.

**Đáp án:** refactor phải cập nhật cả base, các profile có override, env vars/CLI/deployment, model Java và docs. Relaxed binding không tự hiểu đổi nghĩa từ request sang read.

## 53. Bài tập 9 — Cấu hình thường nhưng critical

`app.payment.mode` là `sandbox` hoặc `live`. Có nên đặt `live` vào base để giảm hai dòng lặp?

**Đáp án:** không nên mặc định. Nếu môi trường không cấp giá trị thì phải fail fast để tránh giao dịch thật ngoài ý định, hãy buộc khai báo explicit và validate.

## 54. Bài tập 10 — Profile test chỉ kiểm một key

Test prod assert timeout 12s, nhưng `max-retries` vô tình đổi thành 1 do file copy cũ.

**Đáp án:** test phải kiểm cả key được override và key phải kế thừa base. Một test chỉ kiểm “key thay đổi” chưa đủ phát hiện configuration drift.

## 55. Bảng quyết định cuối bài

| Bài toán | Cách làm |
| --- | --- |
| Một scalar giống mọi môi trường | Đặt một lần trong `application.yml` |
| Scalar khác theo profile | Chỉ đặt override trong `application-{profile}.yml` |
| Nested object chỉ khác một field | Chỉ override leaf key, test binding |
| List có biến thể theo môi trường | Khai báo trọn list hoặc thiết kế lại map |
| Map có entries theo ID | Cân nhắc map binding và test merge/override |
| Nhiều profile logic đi cùng | Profile groups với ownership rõ |
| Shared defaults lớn | Config Data import theo module nếu cần |
| Secret riêng môi trường | Secret manager/env/mount có kiểm soát |
| Setting critical không có default an toàn | Bắt buộc khai báo, validate/fail fast |
| Muốn một source config cho nhiều service | Central config có version và quyền |
| Đổi cấu trúc hoặc key | Migration contract và test tất cả profiles |
| CI muốn phát hiện drift | Test giá trị hiệu lực, secret scan, schema check |
| Muốn một feature rollout động | Cân nhắc feature flag system, không nhồi vào profile |
| Debug file “không được đọc” | Kiểm active profile, Config Data, precedence, origin, startup |
| Đội ngũ có nhiều file gần giống nhau | Base + delta + refactor từng bước |

## 56. Checklist review Pull Request thay đổi config

Khi review một thay đổi profile, hãy hỏi:

- [ ] Key này có thật sự khác giữa các môi trường không?
- [ ] Nếu giống base, vì sao cần lặp lại?
- [ ] Nếu không khai báo key, default có an toàn không?
- [ ] Có secret thật bị đưa vào repository không?
- [ ] Thay đổi có ảnh hưởng profile khác không?
- [ ] Đây là scalar, nested object, list hay map?
- [ ] Nếu là list, toàn danh sách cuối cùng có đúng không?
- [ ] Profile nào active khi test, có group/include liên quan không?
- [ ] Có source env/CLI/import cao hơn che mất override này không?
- [ ] Typed `@ConfigurationProperties` có validation thích hợp không?
- [ ] Có cần cập nhật deployment templates, documentation, charts không?
- [ ] Test có assert cả giá trị override và giá trị được kế thừa không?
- [ ] Có phần code `@Value` nào giữ default khác không?
- [ ] Có plan rollback và đánh giá change control không?

## 57. Tổng kết

**Tránh sao chép toàn bộ cấu hình giữa các profile là bài toán thiết kế nguồn sự thật và kiểm soát khác biệt, không chỉ là rút ngắn YAML.** Mô hình base + delta giúp mỗi giá trị chung có một nơi được quản lý, còn mỗi file profile biểu đạt chính xác điều gì khác môi trường.

Hãy nhớ bốn điểm:

1. **`application.yml` cho default chung và an toàn; `application-{profile}.yml` chỉ ghi chênh lệch có chủ đích.**
2. **Scalar và nested properties thường có thể override theo key; list không nên giả định deep merge.** Với cấu trúc cần override theo identity, cân nhắc map và test behavior thật.
3. **Secret và critical settings cần chính sách riêng.** Không copy credential vào file profile; không hy sinh fail-fast chỉ để giảm duplication.
4. **Nâng cấp phải dựa trên effective configuration.** Kiểm source precedence, active profiles, typed binding, environment/CLI và regression tests trước/sau khi xóa những bản sao.

Một hệ thống cấu hình tốt có thể trả lời nhanh: **giá trị mặc định ở đâu, profile này khác base ở điểm gì, vì sao khác, và điều gì xảy ra nếu key bị thiếu?** Khi câu trả lời rõ ràng, bảo trì và triển khai Spring Boot qua nhiều môi trường trở nên ít bất ngờ hơn.
