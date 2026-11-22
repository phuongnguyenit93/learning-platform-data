# Config tree cho cấu hình được gắn từ hệ thống triển khai

## 1. Bài toán: ứng dụng nhận cấu hình từ volume mount

Trong môi trường triển khai như Docker hoặc Kubernetes, nền tảng thường cung cấp cấu hình cho ứng dụng bằng cách **gắn file hoặc thư mục vào container** (volume mount). Những file này có thể chứa tham số ứng dụng, thông tin kết nối dịch vụ, chứng thư hoặc thông tin xác thực.

Có hai kiểu dữ liệu thường gặp:

1. Một file chứa toàn bộ cấu hình, ví dụ file YAML hoặc Java Properties.
2. Một thư mục gồm nhiều file nhỏ, trong đó **tên file là tên thuộc tính** và **nội dung file là giá trị**.

Spring Boot hỗ trợ kiểu thứ hai qua cơ chế **configuration tree (config tree)** và tiền tố vị trí `configtree:` trong **Config Data**. Cơ chế này biến cấu trúc thư mục được mount thành các property trong Spring `Environment`, từ đó ứng dụng đọc bằng `@Value`, `Environment` hoặc bind vào `@ConfigurationProperties`.

Bài học thuộc chương **Nạp cấu hình** của **SPRING_CLOUD_CORE**. Trọng tâm là cách ứng dụng Spring Cloud dùng cấu hình ngoài do hệ thống triển khai cấp, nhất là khi cần tách secrets khỏi image và mã nguồn. Cần nhớ rằng **config tree là tính năng nạp cấu hình của Spring Boot**; Spring Cloud Commons/Context có thể phối hợp với `Environment` và refresh bean, còn Spring Cloud Config Server là một cơ chế cấu hình từ xa khác.

## 2. Config tree ánh xạ thư mục thành property như thế nào?

Giả sử nền tảng mount thư mục sau vào container:

```text
/etc/config/
└── inventory/
    ├── feature/
    │   └── reservation-enabled
    └── service/
        └── timeout
```

Khi import thư mục `/etc/config/`, tên các thư mục và file bên dưới được ghép thành property key:

| Đường dẫn file | Property key | Giá trị |
| --- | --- | --- |
| `/etc/config/inventory/feature/reservation-enabled` | `inventory.feature.reservation-enabled` | Nội dung file `reservation-enabled` |
| `/etc/config/inventory/service/timeout` | `inventory.service.timeout` | Nội dung file `timeout` |

Ví dụ nếu file `timeout` chứa `1500ms`, ứng dụng nhận property `inventory.service.timeout` với nội dung tương ứng. Việc chuyển kiểu sang `Integer`, `Duration` hoặc kiểu dữ liệu khác do Spring Boot Binder xử lý khi bind property; không nên mặc định nội dung file tự trở thành một kiểu Java cụ thể ngay lúc đọc.

**Tên thư mục cũng là một phần của property key.** Nếu import trực tiếp `/etc/config/inventory/`, hai property sẽ lần lượt là `feature.reservation-enabled` và `service.timeout`, vì tiền tố `inventory` đã bị loại khỏi cây import.

Để import một cây cấu hình, khai báo `spring.config.import` trong file cấu hình ứng dụng:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
```

Các giá trị từ cây được đưa vào `Environment` giống như các nguồn Config Data khác. Sau đó có thể đọc theo cách thông thường:

```java
@Value("${inventory.service.timeout}")
private Duration timeout;
```

Hoặc bind thành một object có cấu trúc:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public class InventoryProperties {

    private Feature feature = new Feature();
    private Service service = new Service();

    public Feature getFeature() {
        return feature;
    }

    public void setFeature(Feature feature) {
        this.feature = feature;
    }

    public Service getService() {
        return service;
    }

    public void setService(Service service) {
        this.service = service;
    }

    public static class Feature {
        private boolean reservationEnabled;

        public boolean isReservationEnabled() {
            return reservationEnabled;
        }

        public void setReservationEnabled(boolean reservationEnabled) {
            this.reservationEnabled = reservationEnabled;
        }
    }

    public static class Service {
        private Duration timeout;

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }
}
```

Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` trên application class hoặc `@EnableConfigurationProperties(InventoryProperties.class)` trong cấu hình phù hợp. Khi tên property là kebab-case, Spring Boot relaxed binding có thể ánh xạ `reservation-enabled` vào thuộc tính Java `reservationEnabled`.

### 2.1. Tên file có dấu chấm

Không bắt buộc phải tạo nhiều cấp thư mục. Config tree cũng hiểu dấu chấm trong tên file:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Import `/run/secrets/` sẽ tạo hai key:

- `spring.datasource.username`
- `spring.datasource.password`

Kiểu đặt tên này tiện khi secret store hoặc nền tảng triển khai mount từng secret thành một file trực tiếp dưới cùng thư mục.

### 2.2. Giá trị kiểu chuỗi và byte array

Giá trị config tree có thể được bind thành `String` hoặc `byte[]`, tùy dữ liệu mong muốn. Chuỗi username, password hoặc URL thường được bind thành `String`; dữ liệu nhị phân như chứng thư hoặc key material có thể cần `byte[]`.

Không nên đọc một file chứng thư nhị phân như một chuỗi UTF-8 rồi giả định nội dung vẫn nguyên vẹn. Hãy xác định kiểu dữ liệu và API nhận dữ liệu tương ứng. Với chứng thư/keystore, cần kiểm tra định dạng file, cách cấu hình SSL và quyền đọc của process.

## 3. Khai báo Config Data import

### 3.1. Cấu hình trong YAML

Ví dụ ứng dụng cần lấy cấu hình chung từ một volume và thông tin database từ volume secrets:

```yaml
spring:
  config:
    import:
      - "optional:configtree:/etc/config/"
      - "optional:configtree:/run/secrets/"
```

Cùng khai báo đó có thể viết trong `application.properties`:

```properties
spring.config.import=optional:configtree:/etc/config/,optional:configtree:/run/secrets/
```

Mỗi vị trí import có thể là một cây cấu hình riêng. Các file được nạp thành property source trong quá trình khởi tạo Config Data.

### 3.2. `optional:` có ý nghĩa gì?

Mặc định, nếu một Config Data location được khai báo nhưng không tồn tại, Spring Boot ném `ConfigDataLocationNotFoundException` và ứng dụng không khởi động. Tiền tố `optional:` cho phép bỏ qua lỗi location không tồn tại:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Chọn cách khai báo theo yêu cầu vận hành:

| Cách khai báo | Khi thư mục không tồn tại | Khi nào phù hợp |
| --- | --- | --- |
| `configtree:/run/secrets/` | Khởi động thất bại | Secret là bắt buộc; thiếu secret phải chặn deploy |
| `optional:configtree:/run/secrets/` | Bỏ qua location bị thiếu | Local/dev hoặc môi trường mà nguồn này thực sự không bắt buộc |

**Không dùng `optional:` để che giấu một secret bắt buộc.** Nếu ứng dụng cần `spring.datasource.password` để kết nối database nhưng thư mục secret bị mount sai, việc bỏ qua location chỉ dời lỗi sang giai đoạn bind bean hoặc kết nối database. Trong production, nên fail fast khi thiếu credential thiết yếu.

`optional:` xử lý trường hợp location không có; nó không biến một file có nội dung sai định dạng thành giá trị hợp lệ, cũng không thay thế kiểm tra cấu hình bắt buộc ở tầng ứng dụng.

### 3.3. Nhiều config tree và wildcard

Nếu hệ thống mount nhiều cây con dưới cùng một thư mục, có thể dùng wildcard `/*/` để nhập tất cả **thư mục con trực tiếp**:

```text
/etc/config/
├── database/
│   └── spring/
│       └── datasource/
│           ├── username
│           └── password
└── messaging/
    └── spring/
        └── rabbitmq/
            ├── host
            └── username
```

Import:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/*/"
```

Kết quả gồm các key `spring.datasource.username`, `spring.datasource.password`, `spring.rabbitmq.host` và `spring.rabbitmq.username`.

Một số điểm cần lưu ý:

- Wildcard config tree kết thúc bằng `/*/` và mở rộng các thư mục con trực tiếp của thư mục cha.
- Các thư mục được mở rộng theo thứ tự alphabet của đường dẫn. Nếu cần thứ tự khác, khai báo từng location riêng trong `spring.config.import`.
- Tên thư mục và tên file bên trong mỗi cây vẫn được ghép thành property key.
- Wildcard này không có nghĩa là quét đệ quy mọi thư mục tùy ý ở mọi cấp.

### 3.4. Thứ tự import và ghi đè giá trị

Config Data import được xử lý tại vị trí khai báo. Dữ liệu được import có độ ưu tiên cao hơn document khai báo import đó. Nếu một document import nhiều location, các location được xử lý theo thứ tự khai báo và location đứng sau có thể ghi đè location đứng trước khi cùng định nghĩa một key.

Ví dụ:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/defaults/"
      - "configtree:/etc/config/environment/"
```

Nếu cả hai cây đều cung cấp `inventory.service.timeout`, giá trị từ cây `environment` đứng sau sẽ được ưu tiên trong nhóm import này. Tuy vậy, các property source có độ ưu tiên cao hơn Config Data (chẳng hạn biến môi trường, Java system properties và command-line arguments) vẫn có thể ghi đè kết quả cuối.

## 4. Ví dụ secrets cho database

Giả sử container nhận các file secret từ hệ thống triển khai:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Trong `application.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

  datasource:
    url: jdbc:postgresql://postgres:5432/inventory
    # username và password được nạp từ các file trong config tree
```

Spring Boot có thể bind `spring.datasource.username` và `spring.datasource.password` vào cấu hình DataSource nếu ứng dụng có driver và dependency JDBC phù hợp. Không cần ghi credential trong YAML hoặc truyền password trực tiếp trên command line.

Ví dụ file `spring.datasource.username` chỉ chứa tên tài khoản database; file `spring.datasource.password` chứa password được hệ thống secret manager cấp. **Không đưa nội dung các file này vào Git, Docker image, log hoặc tài liệu triển khai.**

### 4.1. Đọc cấu hình qua `Environment`

Nếu cần kiểm tra sự hiện diện của một property trong code, có thể inject `Environment`:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DatabaseCredentialCheck {

    private final Environment environment;

    public DatabaseCredentialCheck(Environment environment) {
        this.environment = environment;
    }

    public boolean hasDatabasePassword() {
        String password = environment.getProperty("spring.datasource.password");
        return password != null && !password.isBlank();
    }
}
```

Phương thức trên chỉ kiểm tra có giá trị hay không; không trả password ra ngoài. Trong ứng dụng thật, ưu tiên để Spring Boot tự cấu hình DataSource và dùng health check/connection validation phù hợp thay vì tự xây endpoint kiểm tra credential.

### 4.2. Dùng placeholder với giá trị cấu hình

Có thể kết hợp property từ config tree với các thuộc tính khác:

```yaml
app:
  database:
    username: "${spring.datasource.username}"
    pool-name: inventory-pool
```

Khi được resolve, placeholder đọc giá trị hiện có trong `Environment`. Tuy nhiên không nên tạo thêm bản sao của secret trong các object hoặc log nếu không cần thiết. Chỉ bind đúng nơi cần sử dụng và hạn chế quyền truy cập dữ liệu nhạy cảm.

## 5. Gắn ConfigMap và Secret trong Kubernetes

Kubernetes có thể mount ConfigMap và Secret thành file trong container. Đây là trường hợp sử dụng tiêu biểu của config tree.

Ví dụ giả định:

- ConfigMap `inventory-config` chứa key `inventory.feature.reservation-enabled`.
- Secret `inventory-db` chứa key `spring.datasource.username` và `spring.datasource.password`.
- Deployment mount ConfigMap vào `/etc/config`, Secret vào `/run/secrets`.

Đoạn YAML minh họa phần container, volume và volumeMount (các trường metadata, selector và cấu hình Deployment khác được lược bỏ):

```yaml
spec:
  template:
    spec:
      containers:
        - name: inventory
          image: example/inventory-service:1.0
          volumeMounts:
            - name: app-config
              mountPath: /etc/config
              readOnly: true
            - name: db-credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: inventory-config
        - name: db-credentials
          secret:
            secretName: inventory-db
```

Trong ứng dụng, import hai thư mục:

```yaml
spring:
  config:
    import:
      - "configtree:/etc/config/"
      - "configtree:/run/secrets/"
```

Nếu cả hai volume đều bắt buộc, không thêm `optional:`. Khi triển khai, kiểm tra tên ConfigMap/Secret, key được mount thành tên file nào, quyền đọc của user chạy container và đường dẫn thực tế. Nếu dùng `items` hoặc `subPath` để ánh xạ key sang đường dẫn khác, property key mà config tree tạo ra sẽ phụ thuộc tên đường dẫn được mount.

**ConfigMap dành cho dữ liệu cấu hình không nhạy cảm; Secret dành cho thông tin nhạy cảm.** Việc dùng Kubernetes Secret không tự thay thế chính sách bảo mật của cluster: cần RBAC tối thiểu, mã hóa dữ liệu tại rest theo cấu hình cluster, hạn chế quyền đọc, tránh in giá trị ra log và chỉ mount Secret vào container cần nó. Dữ liệu Secret trong manifest/API thường được biểu diễn bằng Base64; Base64 chỉ là encoding, không phải mã hóa bảo mật.

Kubernetes có thể cập nhật nội dung volume ConfigMap/Secret sau khi dữ liệu nguồn thay đổi, nhưng việc cập nhật có độ trễ và không tự refresh `Environment` trong JVM. Ngoài ra, volume mount dùng `subPath` không nhận cập nhật tự động theo cơ chế cập nhật projected volume. Hãy chọn chiến lược rollout và mount phù hợp với yêu cầu xoay vòng credential.

## 6. Docker secrets và thư mục mount

Docker Swarm có thể cấp secret cho service bằng cách mount secret thành file trong container, thường dưới `/run/secrets/`. Ví dụ nếu secret có tên `spring.datasource.password`, ứng dụng có thể nhập:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Khi đó file `/run/secrets/spring.datasource.password` trở thành property `spring.datasource.password`.

Không nên mặc định mọi chế độ chạy Docker đều cấp secret theo cùng một cách. Hãy kiểm tra loại deployment, secret mechanism và đường dẫn mount thực tế. Điều quan trọng với Spring Boot là process phải nhìn thấy **file đã được mount** và có quyền đọc file đó.

## 7. Phân biệt config tree với file YAML và Spring Cloud Config Server

Ba cách cung cấp cấu hình này giải quyết các bài toán liên quan nhưng không giống nhau:

| Cơ chế | Dữ liệu được cung cấp dưới dạng | Cách nhập | Trường hợp phù hợp |
| --- | --- | --- | --- |
| File YAML/Properties được mount | Một file cấu hình hoàn chỉnh | `spring.config.import: "file:/etc/app/application.yaml"` (hoặc vị trí file phù hợp) | Nền tảng mount nguyên file cấu hình |
| **Config tree** | Nhiều file; tên file/thư mục tạo key, nội dung file tạo value | `spring.config.import: "configtree:/etc/config/"` | Kubernetes ConfigMap/Secret volume, Docker secrets |
| **Spring Cloud Config Server** | Property source từ server cấu hình từ xa | Config Client với `spring.config.import: "configserver:..."` | Quản lý cấu hình tập trung qua mạng cho nhiều ứng dụng/môi trường |

Nếu nền tảng mount một file YAML hoàn chỉnh, hãy import file theo định dạng file; không dùng `configtree:` để mong Spring Boot parse toàn bộ YAML đó như một file cấu hình. `configtree:` đọc các file riêng lẻ thành property key/value.

Config tree cũng **không phải Config Server**. Nó không cung cấp API HTTP để nhiều service truy vấn cấu hình tập trung, không quản lý version cấu hình trên server và không tự phát broadcast thay đổi. Mỗi process đọc các file mà nó được mount.

Trong kiến trúc Spring Cloud, hai cơ chế có thể cùng tồn tại: Config Server cung cấp cấu hình dùng chung qua mạng; Config tree cung cấp secret hoặc dữ liệu môi trường gắn vào container. Cần thiết kế thứ tự ưu tiên và nguồn sở hữu từng property rõ ràng để tránh một key bị định nghĩa ở nhiều nơi mà không ai biết giá trị cuối đến từ đâu.

## 8. Độ ưu tiên cấu hình và cách chẩn đoán

Config tree được nhập qua `spring.config.import` nên thuộc nhóm **Config Data**. Spring Boot đặt Config Data dưới các nguồn như OS environment variables, Java system properties và command-line arguments trong thứ tự property source tổng thể. Vì vậy một giá trị có thể bị ghi đè bởi nguồn ưu tiên cao hơn.

Ví dụ config tree cung cấp:

`spring.datasource.url=jdbc:postgresql://postgres:5432/inventory`

nhưng process được khởi chạy với:

```bash
java -jar inventory-service.jar --spring.datasource.url=jdbc:postgresql://localhost:5432/local
```

thì command-line argument có độ ưu tiên cao hơn và giá trị cuối có thể là URL `localhost`. Điều này hữu ích cho override có chủ đích nhưng cũng có thể khiến ứng dụng vô tình kết nối sai môi trường.

Một số nguồn cấu hình quan trọng, theo thứ tự từ thấp đến cao trong nhóm thường gặp:

1. Giá trị mặc định của ứng dụng.
2. Config Data, bao gồm `application.yml` và config tree được import.
3. Biến môi trường của hệ điều hành.
4. Java system properties.
5. `SPRING_APPLICATION_JSON`.
6. Command-line arguments.

Thứ tự đầy đủ còn có các nguồn như `@PropertySource` và test property sources; khi cần chẩn đoán chính xác hãy đối chiếu tài liệu Spring Boot của đúng phiên bản.

### 8.1. Kiểm tra file được mount

Trong container, kiểm tra **tên và quyền file**, không cần in nội dung secret:

```bash
ls -la /etc/config
ls -la /run/secrets
test -r /run/secrets/spring.datasource.password
```

Nếu process chạy dưới user không có quyền đọc file, Config Data có thể không nạp được giá trị hoặc ứng dụng thất bại lúc khởi động. Hãy kiểm tra `runAsUser`, group, `fsGroup`, file mode và quyền mount theo nền tảng triển khai.

### 8.2. Kiểm tra giá trị property mà không làm lộ secret

Actuator có các endpoint `env` và `configprops` hỗ trợ chẩn đoán nguồn cấu hình. Nhưng các endpoint này có thể tiết lộ tên hoặc giá trị property nhạy cảm tùy cấu hình sanitization và phiên bản. Không bật công khai chỉ để debug.

Trong môi trường phát triển, có thể kiểm tra property không nhạy cảm như `inventory.feature.reservation-enabled`; với password/token, chỉ kiểm tra sự hiện diện hoặc trạng thái kết nối, không in giá trị.

Khi cần xem property source, xác minh:

- Đường dẫn `configtree:` có tồn tại trong container.
- File có đúng tên và nằm đúng cấp thư mục không.
- `spring.config.import` có được nạp trong config file trước khi application context hoàn tất khởi tạo không.
- Property có bị biến môi trường, system property hoặc command line ghi đè không.
- Kiểu dữ liệu bind có tương thích với nội dung file không.

## 9. Config tree thay đổi thì ứng dụng có tự refresh không?

**Không nên mặc định một file mount thay đổi sẽ tự động cập nhật Spring `Environment` hoặc bean đang chạy.** Config tree là một nguồn Config Data được đọc trong quá trình nạp cấu hình; bản thân tiền tố `configtree:` không tạo watcher, không gửi sự kiện tới các instance khác và không tự khởi động lại ứng dụng.

Một số nền tảng có thể cập nhật nội dung volume sau khi ConfigMap/Secret thay đổi, nhưng việc file trên filesystem đổi không đồng nghĩa property source và bean trong JVM lập tức đổi theo. Cách triển khai thường dùng là rollout/restart các instance để ứng dụng đọc cấu hình mới khi khởi động.

Nếu hệ thống cần refresh tại runtime, phải thiết kế cơ chế rõ ràng:

1. Xác định nguồn dữ liệu mới đã thực sự được cập nhật và process có thể đọc nó.
2. Có cơ chế nạp lại property vào `Environment` được hỗ trợ trong phiên bản đang dùng.
3. Phát sự kiện thay đổi hoặc gọi cơ chế refresh phù hợp.
4. Rebind các bean `@ConfigurationProperties` hoặc invalidation target bean `@RefreshScope` khi cần.
5. Với nhiều instance, truyền tín hiệu đến toàn bộ instance bằng cơ chế phù hợp (ví dụ Spring Cloud Bus) hoặc điều phối refresh theo deployment.

Spring Cloud Context cung cấp `EnvironmentChangeEvent`, `@RefreshScope` và endpoint refresh trong các cấu hình phù hợp. Nhưng `@RefreshScope` chỉ xử lý target bean trong scope sau khi Environment đã có giá trị mới; nó không phải file watcher và không tự biến một volume mount thành sự kiện refresh. Cần kiểm tra hành vi nạp lại config tree theo đúng phiên bản Boot/Cloud và thử với loại volume thực tế trước khi dựa vào refresh trong production.

Với credential như password database, chứng thư hoặc private key, rollout có kiểm soát thường dễ dự đoán hơn. Đồng thời phải tính đến vòng đời kết nối cũ, khả năng credential cũ bị thu hồi và thời gian chuyển đổi giữa các instance.

## 10. Checklist khi đưa config tree vào triển khai

| Hạng mục | Câu hỏi cần xác minh |
| --- | --- |
| Nguồn dữ liệu | Đây là file YAML/Properties hoàn chỉnh hay nhiều file key/value? Đã chọn đúng `file:` hoặc `configtree:` chưa? |
| Import path | Đường dẫn đúng bên trong container? Có dấu `/` cuối thư mục? Có cần `optional:` không? |
| Property key | Tên thư mục và file có ghép thành đúng key mà ứng dụng mong đợi không? |
| Wildcard | `/*/` có đang mở rộng đúng các thư mục con trực tiếp? Thứ tự alphabet có phù hợp không? |
| Binding | Giá trị bind thành `String`, số, `Duration` hay `byte[]`? Có kiểm tra kiểu và giá trị bắt buộc không? |
| Secrets | Dùng Secret store phù hợp, RBAC tối thiểu, quyền file hạn chế và không log giá trị? |
| Override | Có biến môi trường hoặc command-line argument ghi đè property từ config tree không? |
| Refresh | Thay file có cần restart/rollout? Nếu refresh runtime, nguồn có được nạp lại và mọi instance nhận sự kiện chưa? |
| Quan sát | Có thể chẩn đoán trạng thái mà không hiển thị password/token? |
| Khôi phục | Có quy trình rollback cấu hình và credential khi deploy lỗi không? |

## 11. Bài tập thực hành

**Bối cảnh:** service `inventory-service` chạy trong container. Hệ thống triển khai mount cấu hình vào `/etc/config` và credential database vào `/run/secrets`.

1. Tạo cây file `/etc/config/inventory/feature/reservation-enabled` chứa `true`.
2. Tạo `/etc/config/inventory/service/timeout` chứa `1500ms`.
3. Tạo hai file `/run/secrets/spring.datasource.username` và `/run/secrets/spring.datasource.password` với giá trị thử nghiệm an toàn trong môi trường local.
4. Import hai cây bằng `spring.config.import`, sau đó bind `inventory.feature.reservation-enabled`, `inventory.service.timeout` và cấu hình DataSource.
5. Đổi đường dẫn import từ `/etc/config/` sang `/etc/config/inventory/` và quan sát property key thay đổi như thế nào.
6. Thử bỏ `optional:` khi thư mục không tồn tại, sau đó thêm lại để so sánh hành vi khởi động.
7. Đặt một biến môi trường ghi đè property không nhạy cảm và xác minh giá trị cuối trong `Environment`.
8. Mô phỏng cập nhật file sau khi ứng dụng đã chạy; kiểm tra liệu bean hiện tại có tự đổi không. Thử restart/rollout hoặc cơ chế refresh đã cấu hình và ghi lại kết quả.

**Tiêu chí đạt:** giải thích đúng cách tên thư mục/file tạo property key, nhập đúng `configtree:` location, phân biệt nguồn file hoàn chỉnh với config tree, xác định được độ ưu tiên override và không làm lộ secret khi chẩn đoán.

## 12. Tài liệu tham khảo chính thức

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — Config Data, `spring.config.import`, optional locations, configuration trees, wildcard và property precedence.
- [Spring Boot — Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties) — bind cấu hình có cấu trúc.
- [Spring Cloud Context — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html) — `EnvironmentChangeEvent`, refresh scope và endpoint refresh.
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) — cung cấp dữ liệu cấu hình qua volume.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/) — cung cấp dữ liệu nhạy cảm và các lưu ý bảo mật.
- [Docker — Manage sensitive data with Docker secrets](https://docs.docker.com/engine/swarm/secrets/) — secret được mount vào service container.

*Tài liệu tập trung vào Spring Boot Config Data `configtree:` và cách dùng trong hệ thống triển khai. Cấu trúc volume, quyền file, cập nhật mount và cơ chế refresh cần được kiểm tra trên đúng nền tảng container/orchestrator đang sử dụng.*
