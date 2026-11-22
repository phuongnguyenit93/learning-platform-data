# Biểu diễn danh sách và ánh xạ bằng .properties và YAML trong Spring Boot 3.3

## 1. Mục tiêu và ý tưởng chung

Trong Spring Boot 3.3, file `application.properties` và `application.yaml`/`application.yml` đều có thể cấu hình **danh sách** (`List`, `Set`, mảng) và **ánh xạ** (`Map<K,V>`). Hai định dạng thể hiện dữ liệu khác nhau nhưng khi nạp vào `Environment`, Spring Boot chuyển YAML thành các khóa cấu hình dạng phẳng và dùng **Binder** để ánh xạ chúng thành kiểu Java, thường thông qua `@ConfigurationProperties`.

Phân biệt ngay từ đầu:

- **List**: tập phần tử có thứ tự, ví dụ danh sách máy chủ hoặc danh sách endpoint; thường truy cập bằng chỉ số `[0]`, `[1]`…
- **Map**: tập cặp khóa–giá trị, ví dụ `region → URL` hoặc `serviceName → cấu hình service`; truy cập theo tên khóa.
- **List của object**: mỗi phần tử có nhiều thuộc tính như `name`, `url`, `weight`.
- **Map của object**: mỗi khóa trỏ tới một cấu trúc có các thuộc tính riêng, ví dụ `backends.billing.base-url`.

Các ví dụ bên dưới sử dụng tiền tố `app`. Với cùng dữ liệu, chọn **một** trong hai file `application.properties` hoặc `application.yaml`; không cần khai báo cả hai.

## 2. Danh sách các giá trị đơn giản

### 2.1. `application.properties`: chỉ số `[index]`

```properties
# application.properties
app.regions[0]=ap-southeast-1
app.regions[1]=ap-northeast-1
app.regions[2]=eu-west-1
```

Chỉ số bắt đầu từ **0**. Khi bind vào `List<String> regions`, kết quả dự kiến theo thứ tự là:

```text
["ap-southeast-1", "ap-northeast-1", "eu-west-1"]
```

Đối với danh sách scalar đơn giản, Spring Boot cũng hỗ trợ dạng phân tách bằng dấu phẩy:

```properties
app.regions=ap-southeast-1,ap-northeast-1,eu-west-1
```

Hai cách trên là **hai phương án thay thế nhau**; nên chọn một cách cho một property tại cùng nguồn cấu hình. Dùng dạng `[index]` khi cần gán rõ từng phần tử hoặc đang biểu diễn danh sách object. Dùng dạng dấu phẩy khi các phần tử ngắn, không chứa dấu phân tách cần xử lý riêng.

### 2.2. `application.yaml`: sequence

```yaml
# application.yaml
app:
  regions:
    - ap-southeast-1
    - ap-northeast-1
    - eu-west-1
```

Có thể viết cùng dữ liệu ở dạng flow sequence:

```yaml
app:
  regions: [ap-southeast-1, ap-northeast-1, eu-west-1]
```

Khi Spring Boot flatten YAML, danh sách ở ví dụ đầu có ý nghĩa tương đương:

```properties
app.regions[0]=ap-southeast-1
app.regions[1]=ap-northeast-1
app.regions[2]=eu-west-1
```

**Điểm quan trọng:** dấu `-` có tác dụng đánh dấu phần tử trong YAML; các phần tử cùng cấp phải có độ thụt lề nhất quán. YAML dùng **dấu cách**, tránh dùng tab để thụt lề.

### 2.3. Danh sách số, boolean và kiểu khác

Giá trị từ file cấu hình có thể được Binder chuyển sang kiểu phù hợp theo khai báo Java:

```properties
app.retry-delays[0]=1s
app.retry-delays[1]=5s
app.limits[0]=10
app.limits[1]=20
app.features[0]=true
app.features[1]=false
```

```yaml
app:
  retry-delays:
    - 1s
    - 5s
  limits: [10, 20]
  features: [true, false]
```

Ví dụ tương ứng với `List<Duration> retryDelays`, `List<Integer> limits`, `List<Boolean> features` trong `@ConfigurationProperties`. Với `Duration`, biểu thức `1s` hoặc `5s` nêu đơn vị rõ ràng. Việc chuyển kiểu không xảy ra chỉ vì YAML có sequence; kiểu đích được quyết định bởi lớp cấu hình và bộ chuyển đổi.

## 3. Danh sách object: một phần tử có nhiều thuộc tính

Giả sử mỗi endpoint cần `name`, `url`, `weight`.

**Dạng .properties:**

```properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100

app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10
```

**Dạng YAML tương đương:**

```yaml
app:
  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10
```

Spring Boot flatten đoạn YAML trên thành:

```text
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10
```

Hãy hiểu `endpoints[0]` là **toàn bộ object đầu tiên**; các khóa `.name`, `.url` và `.weight` là thuộc tính cùng một object. Thêm phần tử nghĩa là thêm chỉ số mới trong .properties hoặc thêm một mục bắt đầu bằng `-` trong YAML. Nên dùng chỉ số tuần tự, liên tiếp từ 0 để Binder có thể tạo collection dự kiến.

Một trường hợp thường gặp với YAML là đặt sai cấp thụt lề:

```yaml
# SAI: weight trở thành khóa ngang cấp endpoints, không thuộc phần tử đầu tiên
app:
  endpoints:
    - name: primary
      url: https://primary.example.test
  weight: 100
```

## 4. Map với giá trị đơn giản

### 4.1. `Map<String,String>`

**Dạng .properties:**

```properties
app.labels.team=platform
app.labels.env=staging
app.labels.owner=backend
```

**Dạng YAML:**

```yaml
app:
  labels:
    team: platform
    env: staging
    owner: backend
```

Kết quả sau khi bind vào `Map<String,String> labels`:

```text
{
  "team": "platform",
  "env": "staging",
  "owner": "backend"
}
```

Ở đây `labels` là tên property, còn `team`, `env`, `owner` là các **key thực sự của Map**. Không nhầm `app.labels.team` với thuộc tính Java cố định tên `team`: tập key có thể thay đổi theo cấu hình.

### 4.2. Map có giá trị số/boolean

```properties
app.max-connections.alpha=10
app.max-connections.beta=25
app.flags.audit=true
app.flags.preview=false
```

```yaml
app:
  max-connections:
    alpha: 10
    beta: 25
  flags:
    audit: true
    preview: false
```

Có thể bind tương ứng vào `Map<String,Integer> maxConnections` và `Map<String,Boolean> flags`. Sử dụng kiểu giá trị đúng mục đích để không phải tự parse chuỗi sau khi đọc cấu hình.

## 5. Map có giá trị là object hoặc cấu trúc lồng nhau

Ví dụ mỗi backend được đặt tên theo một key và chứa URL, thời gian timeout.

**Dạng .properties:**

```properties
app.backends.billing.base-url=https://billing.example.test
app.backends.billing.connect-timeout=2s
app.backends.inventory.base-url=https://inventory.example.test
app.backends.inventory.connect-timeout=5s
```

**Dạng YAML:**

```yaml
app:
  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s
```

Mô hình dữ liệu:

```text
app.backends
  ├── billing   → { baseUrl, connectTimeout }
  └── inventory → { baseUrl, connectTimeout }
```

Trong Java, `Map<String,Backend> backends` được bind thành hai entry `billing` và `inventory`. Với `Backend` là object, các property sau key Map tiếp tục được bind như thuộc tính của object. Kiểu `Duration` có thể nhận các giá trị như `2s` và `5s`.

Cấu trúc tương tự có thể sâu hơn, chẳng hạn một `Map<String,List<Endpoint>>`:

```yaml
app:
  routes-by-region:
    vn:
      - name: primary
        url: https://vn-1.example.test
        weight: 100
    sg:
      - name: primary
        url: https://sg-1.example.test
        weight: 100
      - name: fallback
        url: https://sg-2.example.test
        weight: 20
```

Tương đương trong .properties (trích các khóa chính):

```properties
app.routes-by-region.vn[0].name=primary
app.routes-by-region.vn[0].url=https://vn-1.example.test
app.routes-by-region.vn[0].weight=100
app.routes-by-region.sg[0].name=primary
app.routes-by-region.sg[0].url=https://sg-1.example.test
app.routes-by-region.sg[0].weight=100
app.routes-by-region.sg[1].name=fallback
app.routes-by-region.sg[1].url=https://sg-2.example.test
app.routes-by-region.sg[1].weight=20
```

Đây là dạng kết hợp: `routes-by-region` là Map; `vn` và `sg` là key của Map; mỗi giá trị là List được chỉ số hóa.

## 6. Map key chứa ký tự đặc biệt: cách giữ nguyên tên key

Quy tắc này rất dễ bị bỏ qua. Khi bind Map, Spring Boot 3.3 dùng cú pháp **ngoặc vuông `[key]`** để giữ nguyên những ký tự đặc biệt trong key. Nếu không dùng ngoặc, các ký tự ngoài chữ, số, dấu `-` hoặc dấu `.` có thể bị loại bỏ trong quá trình bind.

### 6.1. Ví dụ với dấu `/`

Muốn key thực sự là `/api/v1`, hãy viết:

```properties
app.routes.[/api/v1]=billing
app.routes.[/health]=management
```

```yaml
app:
  routes:
    "[/api/v1]": billing
    "[/health]": management
```

Với `Map<String,String> routes`, các entry nhận được là `"/api/v1" → "billing"` và `"/health" → "management"`.

**Trong YAML, phần key có ngoặc vuông phải được đặt trong dấu nháy**. Nếu dùng:

```properties
app.routes./api/v1=billing
```

mà không có `[]`, dấu `/` không được giữ nguyên theo quy tắc Map binding; key có thể bị biến thành `apiv1`. Cần phân biệt việc tên property trông hợp lệ trong file với việc **Map key sau khi bind** có còn đúng hay không.

### 6.2. Dấu chấm trong key: phụ thuộc vào kiểu giá trị Map

- Với **`Map<String,String>`** hoặc scalar tương tự, key như `a.b` có thể được giữ nguyên dấu chấm, kể cả không dùng `[]`.
- Với **`Map<String,Object>`** hoặc giá trị phức tạp, dấu chấm không có ngoặc có thể được diễn giải thành phân cấp object/map lồng nhau.

Ví dụ để giữ chính xác key `a.b` khi giá trị Map có thể không phải scalar:

```properties
app.metadata.[a.b]=value
```

```yaml
app:
  metadata:
    "[a.b]": value
```

Đừng áp dụng một cách máy móc `app.metadata.a.b=value` khi mục đích là lưu đúng key `a.b` trong `Map<String,Object>`; cách đó có thể tạo cấu trúc lồng nhau `a → b`. Tương tự, key chứa `/` hoặc ký tự đặc biệt khác nên dùng ngoặc vuông để tránh việc chuẩn hóa làm thay đổi tên.

### 6.3. Map key từ biến môi trường

Tên biến môi trường được chuẩn hóa khi relaxed binding, và khi bind Map, tên key đến từ biến môi trường thường **bị chuyển thành chữ thường**. Ví dụ:

```bash
APP_LABELS_TEAM=PLATFORM
```

Khi bind vào `Map<String,String> labels`, key là `team`, còn value vẫn là `PLATFORM`. Nếu cần giữ nguyên kiểu chữ hoặc ký tự đặc biệt của key, cân nhắc dùng file cấu hình hoặc nguồn có thể biểu diễn key chính xác.

## 7. Binding vào Java bằng `@ConfigurationProperties`

`@ConfigurationProperties` thích hợp cho collection và object cấu hình lồng nhau vì có **type-safe binding**, chuyển đổi kiểu và relaxed binding. Ví dụ hoàn chỉnh sau phù hợp với **Java 17+ và Spring Boot 3.3**.

**File `AppProperties.java`:**

```java
package com.example.demo.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<String> regions,
        List<Endpoint> endpoints,
        Map<String, String> labels,
        Map<String, Backend> backends,
        Map<String, String> routes) {

    public record Endpoint(String name, String url, int weight) {
    }

    public record Backend(String baseUrl, Duration connectTimeout) {
    }
}
```

**Bật scan cấu hình trong ứng dụng:**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**File `application.yaml` khớp với record:**

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1

  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10

  labels:
    team: platform
    env: staging

  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s

  routes:
    "[/api/v1]": billing
    "[/health]": management
```

**Sử dụng bean đã bind:**

```java
package com.example.demo.service;

import com.example.demo.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class EndpointService {

    private final AppProperties config;

    public EndpointService(AppProperties config) {
        this.config = config;
    }

    public void printConfig() {
        System.out.println(config.regions());
        System.out.println(config.endpoints().get(0).url());
        System.out.println(config.labels().get("team"));
        System.out.println(config.backends().get("billing").connectTimeout());
        System.out.println(config.routes().get("/api/v1"));
    }
}
```

Trong Spring Boot 3.3, record cấu hình với một constructor tự nhiên được hỗ trợ bởi constructor binding; không cần thêm `@ConstructorBinding` cho trường hợp một constructor. Nếu dùng class JavaBean thay vì record, có thể sử dụng constructor hoặc các getter/setter phù hợp. `@ConfigurationPropertiesScan` tìm các class/record được đánh dấu `@ConfigurationProperties` trong package được scan. Có thể đăng ký rõ ràng bằng `@EnableConfigurationProperties(AppProperties.class)` thay cho scan khi cần.

**Rel​axed binding:** tên YAML `base-url` ánh xạ tới thành phần Java `baseUrl` và `connect-timeout` đến `connectTimeout`. Tương tự `routes-by-region` có thể bind vào `routesByRegion`. Prefix của `@ConfigurationProperties` nên dùng dạng chuẩn chữ thường, kebab-case.

## 8. Danh sách và Map khi cấu hình đến từ nhiều nguồn/profile

Đây là phần khác biệt **quan trọng nhất về hành vi**, không phụ thuộc định dạng .properties hay YAML.

### 8.1. **List được thay thế toàn bộ, không ghép từng phần tử**

Giả sử `application.yaml`:

```yaml
app:
  regions:
    - ap-southeast-1
    - eu-west-1
  endpoints:
    - name: primary
      url: https://primary.example.test
      weight: 100
    - name: backup
      url: https://backup.example.test
      weight: 10
```

Và `application-dev.yaml`:

```yaml
app:
  regions:
    - localhost
  endpoints:
    - name: local
      url: http://localhost:8081
```

Khi profile `dev` hoạt động và hai file được nạp theo thứ tự ưu tiên thông thường:

- `regions` trở thành **`["localhost"]`**, không phải danh sách ba phần tử.
- `endpoints` chỉ có **một** object với `name=local`, `url=http://localhost:8081`.
- `weight` của object này không được kế thừa từ phần tử `[0]` ở cấu hình thấp hơn. Với `int weight` nguyên thủy ở ví dụ record, giá trị mặc định khi không được khai báo có thể là `0`; nếu muốn phân biệt “không khai báo”, dùng kiểu wrapper `Integer`, có thể là `null`, hoặc quy định giá trị mặc định rõ ràng.

Với collection, phần cấu hình thuộc **nguồn có ưu tiên cao nhất** được dùng cho toàn bộ List. Không dựa vào việc chỉ viết `app.endpoints[0].name` ở profile cao hơn rồi trông đợi các trường `url` hoặc `weight` từ profile thấp hơn được ghép vào cùng phần tử.

**Tương đương dùng .properties:**

```properties
# application.properties
app.regions[0]=ap-southeast-1
app.regions[1]=eu-west-1
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.endpoints[0].weight=100
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.test
app.endpoints[1].weight=10

# application-dev.properties (file KHÁC)
app.regions[0]=localhost
app.endpoints[0].name=local
app.endpoints[0].url=http://localhost:8081
```

Kết quả List ở profile `dev` theo quy tắc tương tự, không phụ thuộc YAML hay .properties.

### 8.2. **Map có thể kết hợp các key và thuộc tính từ nhiều nguồn**

Giả sử `application.yaml`:

```yaml
app:
  backends:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 2s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 5s
```

Và `application-dev.yaml`:

```yaml
app:
  backends:
    billing:
      base-url: http://localhost:9000
    notifications:
      base-url: http://localhost:9010
      connect-timeout: 1s
```

Khi `dev` hoạt động, Map có các key `billing`, `inventory` và `notifications`:

| Key | `baseUrl` | `connectTimeout` |
| --- | --- | --- |
| `billing` | `http://localhost:9000` | `2s` từ nguồn thấp hơn |
| `inventory` | `https://inventory.example.test` | `5s` |
| `notifications` | `http://localhost:9010` | `1s` |

Với Map object, các **thuộc tính khác nhau** của cùng một entry có thể đến từ nhiều nguồn; khi **cùng một thuộc tính** xuất hiện nhiều lần, nguồn có ưu tiên cao hơn thắng. Khác với List, không nhất thiết phải viết lại toàn bộ Map ở profile cao hơn.

Quy tắc thay thế List và kết hợp Map áp dụng khi binding từ **nhiều PropertySource** nói chung, không chỉ từ các file profile. Để hiểu “nguồn nào cao hơn”, phải xét thứ tự ưu tiên PropertySource của Spring Boot và thứ tự các Config Data file đang được nạp.

## 9. Từ biến môi trường sang List, Map và object

Nếu ứng dụng lấy cấu hình từ container, Spring Boot hỗ trợ relaxed binding cho biến môi trường. Quy tắc chuyển từ tên chuẩn là: **dấu chấm thành `_`, bỏ dấu `-`, chuyển sang chữ hoa**. Với phần tử List, chỉ số được kẹp giữa các dấu gạch dưới.

```properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.test
app.backends.billing.base-url=https://billing.example.test
```

Có thể thay bằng biến môi trường ở dạng khái niệm:

```bash
APP_ENDPOINTS_0_NAME=primary
APP_ENDPOINTS_0_URL=https://primary.example.test
APP_BACKENDS_BILLING_BASEURL=https://billing.example.test
```

Đặc biệt: `APP_ENDPOINTS_0_NAME` ánh xạ đến `app.endpoints[0].name`; `BASEURL` phù hợp với property canonical `base-url` vì dấu `-` bị loại khi đổi sang dạng biến môi trường. Tránh kỳ vọng một biến môi trường với key Map phức tạp, chứa dấu `/` hoặc cần phân biệt chữ hoa/thường, sẽ giữ nguyên chính xác key sau bind.

Khi cấu hình danh sách dài hoặc Map phức tạp, file YAML có thể dễ quản lý hơn nhiều biến môi trường rời rạc. Tuy nhiên, việc chọn cách đưa cấu hình vào ứng dụng còn phụ thuộc hạ tầng triển khai và độ nhạy cảm của dữ liệu.

## 10. `@ConfigurationProperties`, `@Value` và `Environment` khác nhau ở đâu?

| Cách đọc | Phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| `@ConfigurationProperties` | `List<T>`, `Map<K,V>`, object lồng nhau, nhiều thuộc tính dưới một prefix | Có relaxed binding và chuyển kiểu; đây là lựa chọn chính cho cấu hình collection. |
| `Environment#getProperty(String)` | Đọc một **khóa đã được flatten** | Ví dụ `getProperty("app.regions[0]")` có thể đọc một phần tử; không tự tạo `List<Endpoint>` từ prefix. |
| `@Value` | Một vài giá trị đơn hoặc biểu thức cụ thể | Không có đầy đủ khả năng type-safe/relaxed binding như `@ConfigurationProperties`; đặc biệt không nên dựa vào `@Value("${app.endpoints}")` để dựng List object phức tạp. |

Ví dụ:

```java
String firstRegion = environment.getProperty("app.regions[0]");
```

Với YAML list, dạng khóa có index mới là khóa được flatten; đừng giả định `environment.getProperty("app.regions")` luôn trả về một chuỗi danh sách hoàn chỉnh. Cách ổn định cho collection là binder + model Java phù hợp.

## 11. Các lỗi phổ biến và cách tránh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| List không có đủ phần tử | Sai index, thiếu index hoặc khai báo ở nguồn có ưu tiên cao hơn ghi đè cả List | Dùng index liên tiếp từ 0; kiểm tra các profile và nguồn cấu hình. |
| `List<Endpoint>` không có thuộc tính mong đợi | Viết sai `[i].field` hoặc YAML thụt lề sai | So sánh khóa đã flatten với cấu trúc Java. |
| Map mất ký tự `/` trong key | Không dùng cú pháp `[key]` | Viết `app.routes.[/api/v1]` hoặc YAML `"[/api/v1]"`. |
| Map có key lồng `a → b` thay vì key nguyên `a.b` | Dùng `Map<String,Object>` và quên `[a.b]` | Dùng bracket notation cho key chứa dấu chấm khi cần giữ nguyên. |
| Cấu hình `dev` mất các phần tử base | List bị thay thế toàn bộ bởi nguồn cao hơn | Khai báo đầy đủ List mong muốn trong file profile hoặc thiết kế dữ liệu dạng Map nếu cần hợp nhất theo key. |
| Giá trị boolean/số không bind được | Giá trị không chuyển đổi được sang kiểu đích | Kiểm tra kiểu Java và chuỗi cấu hình; quote YAML khi cần bảo toàn chuỗi đặc biệt. |
| YAML không được nạp qua `@PropertySource` | Annotation mặc định không hỗ trợ nạp YAML trực tiếp | Dùng `application.yaml` qua cơ chế Config Data hoặc bộ nạp phù hợp. |
| Hai định dạng cấu hình có kết quả khác kỳ vọng | Cùng vị trí có cả `application.properties` và `application.yaml` | Nên chọn một định dạng; trong cùng vị trí, `.properties` có ưu tiên hơn YAML theo quy tắc Spring Boot. |

Một số lưu ý thực hành:

- **Trích dẫn string trong YAML:** có thể đặt URL, chuỗi chứa `:#{}[]`, hoặc giá trị dễ bị diễn giải thành kiểu khác trong dấu nháy để rõ ý định. Key `"[/path]"` bắt buộc được quote khi dùng bracket notation.
- **Không dùng tab để indent YAML.** Khoảng trắng và vị trí dấu `-` quyết định cấp của phần tử.
- **Đặt tên nhất quán:** dùng tên property dạng lowercase kebab-case, ví dụ `connect-timeout` và `routes-by-region`, rồi để Binder ánh xạ sang Java camelCase.
- **Không phụ thuộc thứ tự Map** để xây dựng logic nghiệp vụ khi không có hợp đồng đảm bảo thứ tự; với danh sách thì thứ tự phần tử là một phần ý nghĩa.
- **Tránh sửa cấu hình bằng việc nối chuỗi thủ công** từ nhiều nguồn: hãy để Spring Boot Binder áp dụng quy tắc collection và precedence.
- **Không đặt bí mật** như API token vào ví dụ, log hoặc source control; cấu hình chứa bí mật nên lấy từ cơ chế quản lý secret phù hợp với môi trường chạy.

## 12. Bảng đối chiếu nhanh

| Kiểu dữ liệu | `application.properties` | `application.yaml` | Kiểu Java thường dùng |
| --- | --- | --- | --- |
| Danh sách scalar | `app.regions[0]=vn`, `app.regions[1]=sg` | `regions: [vn, sg]` | `List<String>` |
| Danh sách object | `app.endpoints[0].name=primary` | `endpoints:` rồi `- name: primary` | `List<Endpoint>` |
| Map scalar | `app.labels.team=platform` | `labels:` rồi `team: platform` | `Map<String,String>` |
| Map object | `app.backends.billing.base-url=...` | `backends:` → `billing:` → `base-url: ...` | `Map<String,Backend>` |
| Map key đặc biệt | `app.routes.[/api/v1]=billing` | `routes:` → `"[/api/v1]": billing` | `Map<String,String>` |
| Map chứa List | `app.routes-by-region.vn[0].name=primary` | `routes-by-region:` → `vn:` → `- name: primary` | `Map<String,List<Endpoint>>` |

**Quy tắc nhớ:** **List dùng vị trí** `[index]` và khi bị ghi đè từ nguồn ưu tiên cao sẽ **thay cả danh sách**; **Map dùng key** và có thể **kết hợp entry/thuộc tính** từ các nguồn khác nhau; muốn giữ key có ký tự đặc biệt thì dùng **`[key]`** và quote key đó trong YAML.

## 13. Nguồn tham khảo

- Spring Boot **3.3** Reference – *Externalized Configuration*, mục *Working With YAML*, *Mapping YAML to Properties*, *Relaxed Binding*, *Binding Maps*, *Binding From Environment Variables* và *Merging Complex Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot **3.3** Reference – *Type-safe Configuration Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties

