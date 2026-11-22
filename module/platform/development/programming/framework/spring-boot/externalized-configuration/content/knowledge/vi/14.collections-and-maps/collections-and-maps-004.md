# Danh sách bị thay thế khi xuất hiện ở nguồn ưu tiên cao hơn trong Spring Boot

## 1. Vấn đề cần hiểu

Trong Spring Boot, cấu hình có thể nằm trong nhiều `PropertySource` và tài liệu Config Data như `application.yml`, `application-prod.yml`, file bên ngoài JAR, Java system properties, biến môi trường hoặc command-line arguments.

Với những giá trị đơn như `app.timeout=5s`, ta thường hiểu khá dễ: nguồn ưu tiên cao hơn có cùng tên property thì giá trị của nguồn ấy được dùng. Nhưng khi cấu hình là **danh sách (`List`)**, nhiều người kỳ vọng Spring Boot sẽ gộp các phần tử từ các nguồn khác nhau, hoặc cập nhật từng trường của từng phần tử. Đó **không phải quy tắc binding List của Spring Boot**.

Quy tắc trọng tâm:

> **Khi cùng một danh sách được khai báo ở nhiều nguồn cấu hình có mức ưu tiên khác nhau, binder của `@ConfigurationProperties` dùng danh sách từ nguồn có ưu tiên cao nhất đã cung cấp danh sách đó. Danh sách ở nguồn thấp hơn không được gộp vào danh sách đang được bind.**

Nghĩa là:

- Nguồn cao có một phần tử, nguồn thấp có ba phần tử: danh sách hiệu lực có thể chỉ còn **một phần tử**.
- Nguồn cao chỉ khai báo `app.backends[0].url`, nguồn thấp khai báo cả `name` và `timeout` cho phần tử 0: khi bind List, các trường còn thiếu của phần tử 0 không nhất thiết được lấy từ nguồn thấp.
- Nguồn cao không khai báo danh sách: có thể tiếp tục sử dụng danh sách từ nguồn thấp hơn.
- Cấu hình dạng **`Map`** hoạt động khác: nhiều key từ các nguồn có thể được kết hợp, và giá trị trùng key được quyết định theo ưu tiên.

Bài học này tập trung vào **cơ chế binding collection** qua `@ConfigurationProperties`, không phải cách nối hai `List` bằng Java sau khi ứng dụng đã chạy.

## 2. Đặt List trong một cấu hình Spring Boot

Giả sử dịch vụ cần danh sách các backend để gửi yêu cầu:

~~~yaml
# src/main/resources/application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Hai phần tử YAML ở trên là một list:

| Chỉ số | `name` | `url` | `timeout` |
| --- | --- | --- | --- |
| `0` | `primary` | `https://primary.example.test` | `2s` |
| `1` | `backup` | `https://backup.example.test` | `4s` |

Theo quy ước biểu diễn property của Spring Boot, ta có thể hình dung các leaf properties:

~~~properties
app.backends[0].name=primary
app.backends[0].url=https://primary.example.test
app.backends[0].timeout=2s

app.backends[1].name=backup
app.backends[1].url=https://backup.example.test
app.backends[1].timeout=4s
~~~

Đây là **một danh sách gồm hai object**, không phải một map có khóa `0` và `1` theo ý nghĩa nghiệp vụ. Chỉ số `[0]`, `[1]` phục vụ thao tác binding collection.

Nếu trong toàn bộ môi trường chỉ có file trên khai báo `app.backends`, Spring Boot có thể bind đủ hai phần tử vào `List<Backend>`.

## 3. Một model Java dùng chung trong các ví dụ

Trong Spring Boot 3.x và Java 17+, có thể dùng record:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Backend> backends,
        Map<String, String> labels) {

    public record Backend(
            String name,
            String url,
            Duration timeout) {
    }
}
~~~

Đăng ký type cấu hình:

~~~java
package com.example;

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
~~~

Đặt `AppProperties` trong package con được scan, hoặc dùng `@EnableConfigurationProperties(AppProperties.class)` để đăng ký tường minh.

Bean nhận cấu hình:

~~~java
package com.example.service;

import com.example.config.AppProperties;
import org.springframework.stereotype.Service;

@Service
public class BackendRouter {
    private final AppProperties properties;

    public BackendRouter(AppProperties properties) {
        this.properties = properties;
    }

    public void printBackends() {
        if (properties.backends() == null) {
            System.out.println("No backend list configured");
            return;
        }

        properties.backends().forEach(backend ->
            System.out.println(backend.name() + " -> " + backend.url()));
    }
}
~~~

Đối với record, các accessor là `backends()`, `name()` và `url()`, thay vì các getter JavaBean kiểu `getBackends()` hay `getName()`.

Cùng quy tắc thay thế List được áp dụng khi model được viết bằng JavaBean có setter hoặc bằng immutable class có constructor binding. **Kiểu Java dùng để chứa list không làm thay đổi nguyên tắc ưu tiên giữa các nguồn config data.**

## 4. Ví dụ chính: `application-prod.yml` thay cả danh sách

Giữ `application.yml` như phần 2, gồm hai backend `primary` và `backup`.

Thêm file:

~~~yaml
# src/main/resources/application-prod.yml
app:
  backends:
    - name: primary-prod
      url: https://api.example.test
      timeout: 6s
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Khi `prod` hoạt động, file `application-prod.yml` tham gia cơ chế Config Data. Với ví dụ không có nguồn ưu tiên cao hơn, danh sách được bind là:

~~~text
backends.size() = 1

backends[0].name    = primary-prod
backends[0].url     = https://api.example.test
backends[0].timeout = PT6S
~~~

**Không có** phần tử `backends[1]` từ `application.yml` được tự giữ lại. `backup` biến mất khỏi kết quả List binding, mặc dù nó vẫn tồn tại trong file mặc định.

So sánh hai trạng thái:

| Trạng thái | Phần tử 0 | Phần tử 1 | Số phần tử |
| --- | --- | --- | --- |
| Không kích hoạt `prod` | `primary` | `backup` | `2` |
| Kích hoạt `prod` | `primary-prod` | Không có | `1` |

Đây là cơ chế **replacement**, không phải nối danh sách, không phải update riêng phần tử 0 rồi giữ nguyên phần tử 1.

Nếu muốn production có cả backend chính và dự phòng, cần khai báo **cả hai phần tử** trong danh sách ở nguồn hiệu lực ưu tiên cao:

~~~yaml
# application-prod.yml
app:
  backends:
    - name: primary-prod
      url: https://api.example.test
      timeout: 6s
    - name: backup-prod
      url: https://backup-api.example.test
      timeout: 8s
~~~

Lúc này list có hai phần tử vì **file production đã khai báo hai phần tử**, không phải vì Spring Boot ghép phần tử từ file mặc định.

## 5. Trường hợp dễ nhầm nhất: nguồn cao chỉ ghi đè một field

Giả sử file mặc định:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

File theo profile lại chỉ có:

~~~yaml
# application-prod.yml
app:
  backends:
    - url: https://api.example.test
~~~

Người mới thường dự đoán:

~~~text
backends[0]:
    name    = primary                 (lấy từ file mặc định)
    url     = https://api.example.test
    timeout = 2s                      (lấy từ file mặc định)

backends[1]:
    name    = backup                  (giữ nguyên)
    url     = https://backup.example.test
    timeout = 4s
~~~

**Dự đoán đó không đúng với binding List nhiều nguồn trong Spring Boot.** Dữ liệu `backends` ở nguồn ưu tiên cao hơn được sử dụng để bind list, nên kết quả về bản chất là:

~~~text
backends.size() = 1

backends[0].name    = null
backends[0].url     = https://api.example.test
backends[0].timeout = null
~~~

Trong ví dụ này, record `Backend` dùng các kiểu tham chiếu `String` và `Duration`, nên các trường không được cấp có thể là `null`. Với field primitive như `int`, việc thiếu dữ liệu có thể dẫn đến giá trị mặc định kiểu nguyên thủy tùy hình thức binding; nhưng **giá trị đó không phải giá trị được kế thừa từ phần tử trong list nguồn thấp hơn**.

Điều này gây lỗi thực tế rất đáng chú ý:

- Một backend có URL mới nhưng thiếu tên hiển thị.
- Timeout bị thiếu khiến code sử dụng gặp `NullPointerException`.
- Backend dự phòng bị bỏ khỏi danh sách mà người triển khai không nhận ra.
- Một trường bắt buộc bị thiếu làm validation fail khi khởi động.

**Quy tắc thực hành:** khi override một `List` chứa các object, hãy khai báo lại toàn bộ danh sách và các field bắt buộc của từng phần tử ở nguồn ưu tiên cao hơn.

## 6. Nguồn cao không có list thì sao?

Replacement chỉ xảy ra khi một nguồn ưu tiên cao hơn **đóng góp cấu hình cho chính danh sách ấy**. Không có nghĩa bất kỳ file profile nào cũng xóa toàn bộ list ở file chung.

Ví dụ:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
  display-name: Demo Service
~~~

File production:

~~~yaml
# application-prod.yml
app:
  display-name: Production Service
~~~

File production **không khai báo** `app.backends`. Vì vậy danh sách mặc định trong `application.yml` vẫn có thể được bind với hai phần tử. `app.display-name` được ghi đè độc lập.

Cần phân biệt ba tình huống:

| Cấu hình trong nguồn cao | Ý nghĩa thực tế |
| --- | --- |
| Hoàn toàn không khai báo `app.backends` | Danh sách từ nguồn thấp có thể vẫn được dùng |
| Khai báo một hoặc vài phần tử `app.backends` | Danh sách từ nguồn cao thay thế danh sách của nguồn thấp |
| Khai báo rõ `app.backends: []` dưới dạng YAML list rỗng | Chủ đích khai báo một danh sách rỗng; cần xác minh đặc tính binding/định dạng trong ứng dụng đang dùng nếu muốn “xóa hết” |

Với tình huống muốn tắt hoàn toàn một chức năng, đôi khi một key boolean rõ ràng như `app.routing.enabled=false` sẽ dễ hiểu và ổn định hơn phụ thuộc vào việc một list trống được biểu diễn như thế nào trong từng nguồn cấu hình.

## 7. Đối chiếu quan trọng: `Map` được kết hợp theo key

Khác với `List`, Spring Boot có quy tắc binding `Map` cho phép các key được kết hợp từ nhiều nguồn. Xét YAML mặc định:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
    tier: standard
~~~

File profile:

~~~yaml
# application-prod.yml
app:
  labels:
    region: apac
    environment: production
~~~

Khi `prod` hoạt động và không có nguồn ưu tiên cao hơn, `Map<String, String> labels` có thể nhận:

~~~text
owner       = platform     (từ file mặc định)
region      = apac         (file prod ghi đè key trùng)
tier        = standard     (từ file mặc định)
environment = production   (key chỉ có ở file prod)
~~~

Bảng phân biệt:

| Đặc điểm | `List` | `Map` |
| --- | --- | --- |
| Nhận dạng phần tử | Vị trí/chỉ số `[0]`, `[1]` | Key có ý nghĩa như `owner`, `region` |
| Cùng cấu hình ở hai nguồn | Nguồn ưu tiên cao thay **cả list** | Các key có thể được **kết hợp** |
| Khi một phần tử/key vắng ở nguồn cao | Phần tử list nguồn thấp không tự ghép vào | Key map chỉ có ở nguồn thấp có thể vẫn còn |
| Khi một key trùng ở hai nguồn | Không merge từng phần tử theo index | Giá trị key ở nguồn cao được ưu tiên |
| Phù hợp cho | Danh sách có thứ tự, mỗi lần override cung cấp một danh sách đầy đủ | Các cấu hình được định danh bằng key ổn định |

Đừng suy ra Map luôn deep-merge **mọi** kiểu dữ liệu phức tạp trong mọi tình huống. Kết quả còn chịu cách dữ liệu được biểu diễn, kiểu value, quy tắc binder và các nguồn cung cấp. Với map của những giá trị đơn giản trong ví dụ, cơ chế kết hợp key là trực quan nhất.

## 8. List các object và Map các object: so sánh sâu hơn

Xét cấu hình các service cùng thuộc tính `url` và `timeout`.

### 8.1. Khi biểu diễn bằng List

~~~yaml
# application.yml
app:
  services:
    - name: catalog
      url: https://catalog.example.test
      timeout: 3s
    - name: inventory
      url: https://inventory.example.test
      timeout: 5s
~~~

Override chỉ phần catalog:

~~~yaml
# application-prod.yml
app:
  services:
    - name: catalog
      url: https://catalog.example.com
~~~

Khi bind List, kết quả chỉ còn một item `catalog`, `timeout` của item này không được tự lấy từ file mặc định; item `inventory` không được giữ lại.

### 8.2. Khi biểu diễn bằng Map có key ổn định

Đổi YAML thành:

~~~yaml
# application.yml
app:
  services:
    catalog:
      url: https://catalog.example.test
      timeout: 3s
    inventory:
      url: https://inventory.example.test
      timeout: 5s
~~~

File prod:

~~~yaml
# application-prod.yml
app:
  services:
    catalog:
      url: https://catalog.example.com
~~~

Model Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record ServiceMapProperties(
        Map<String, Service> services) {

    public record Service(String url, Duration timeout) {
    }
}
~~~

Với map binding, các property của `catalog` và key `inventory` có thể được kết hợp theo cách sau:

~~~text
services["catalog"].url      = https://catalog.example.com
services["catalog"].timeout  = PT3S
services["inventory"].url    = https://inventory.example.test
services["inventory"].timeout= PT5S
~~~

Trong Map, `catalog` và `inventory` là **định danh có ý nghĩa**, không phải số index. Vì vậy hình thức Map thích hợp khi yêu cầu thường xuyên là “thay URL của một service nhưng giữ cấu hình service khác”.

Điều kiện lựa chọn:

- Cần **thứ tự rõ ràng** (thử backend theo thứ tự 0, 1, 2), danh sách có thể phù hợp.
- Cần override **từng phần tử theo tên** từ nhiều nguồn, Map thường dễ quản lý hơn.
- Nếu vẫn cần thứ tự trong Map, hãy định nghĩa quy tắc thứ tự tường minh (ví dụ property `priority` cho mỗi service), không dựa vào suy đoán rằng trật tự YAML luôn được bảo toàn xuyên mọi nguồn.

## 9. Ví dụ đầy đủ gồm List và Map trong cùng một ứng dụng

Sử dụng model đã nêu ở mục 3:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        List<Backend> backends,
        Map<String, String> labels) {
    public record Backend(
            String name,
            String url,
            Duration timeout) {
    }
}
~~~

File mặc định:

~~~yaml
# application.yml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
  labels:
    owner: platform
    environment: default
~~~

File profile:

~~~yaml
# application-prod.yml
app:
  backends:
    - name: production
      url: https://api.example.test
      timeout: 6s
  labels:
    environment: production
    region: apac
~~~

Bật `prod`:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Kết quả theo quy tắc binding:

| Cấu hình | Kết quả |
| --- | --- |
| `backends` | Chỉ có **một item** `production` |
| `backends[0].url` | `https://api.example.test` |
| `backends[0].timeout` | `6s` |
| `labels.owner` | `platform` |
| `labels.environment` | `production` |
| `labels.region` | `apac` |

Thấy rõ: **List thay thế nguyên danh sách**, nhưng **Map giữ thêm key ở nguồn thấp** và ghi đè key trùng theo mức ưu tiên.

Nếu sau đó thêm một nguồn ưu tiên cao hơn như CLI:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.labels.region=eu
~~~

`labels.region` có thể trở thành `eu`, trong khi danh sách `backends` vẫn đến từ file profile vì CLI không khai báo danh sách.

Ngược lại, nếu CLI có `--app.backends[0].url=...`, nó có thể trở thành nguồn list ưu tiên cao nhất và làm list hiệu lực chỉ phản ánh phần được cung cấp từ nguồn CLI đó.

## 10. Override List qua command-line arguments

Giả sử YAML đóng gói:

~~~yaml
app:
  backends:
    - name: primary
      url: https://primary.example.test
      timeout: 2s
    - name: backup
      url: https://backup.example.test
      timeout: 4s
~~~

Trên một shell hỗ trợ truyền đối số chuỗi, có thể truyền một property index:

~~~bash
java -jar app.jar '--app.backends[0].url=https://temporary.example.test'
~~~

Dấu nháy đơn ở đây giúp shell Unix truyền nguyên ký tự `[` và `]`; các shell khác có quy tắc quote riêng. Khi `SpringApplication` vẫn chấp nhận command-line properties, option này có thể cung cấp cấu hình cho `app.backends` ở nguồn ưu tiên cao.

Với `@ConfigurationProperties` bind List, đừng kỳ vọng nó chỉ thay `url` của phần tử 0 và giữ lại `name`, `timeout` cùng phần tử 1 từ YAML. Nó có thể làm list được bind từ nguồn cao chỉ có phần tử 0 với `url` mới, các field khác thiếu.

Nếu muốn đặt lại **một list hoàn chỉnh** bằng CLI, phải khai báo tất cả index và field cần thiết, chẳng hạn:

~~~bash
java -jar app.jar \
  '--app.backends[0].name=primary-temp' \
  '--app.backends[0].url=https://temporary.example.test' \
  '--app.backends[0].timeout=3s' \
  '--app.backends[1].name=backup-temp' \
  '--app.backends[1].url=https://backup-temporary.example.test' \
  '--app.backends[1].timeout=5s'
~~~

Cách này dài và dễ nhầm. Với List object nhiều field, việc cung cấp **một YAML config data file hoàn chỉnh theo môi trường** thường dễ kiểm soát hơn truyền từng index qua command line.

Lưu ý: nếu code đã gọi `setAddCommandLineProperties(false)`, các option `--app.backends[...]` không được đưa vào `Environment` qua command-line property source mặc định.

## 11. Override List qua biến môi trường

Tên biến môi trường có quy ước khác với tên property trong YAML. Với relaxed binding của Spring Boot, khi binding List, **chỉ số phần tử được đặt giữa dấu gạch dưới** trong tên biến môi trường.

Ví dụ:

~~~text
Tên cấu hình:  app.backends[0].name
Biến môi trường: APP_BACKENDS_0_NAME

Tên cấu hình:  app.backends[1].url
Biến môi trường: APP_BACKENDS_1_URL
~~~

Một deployment có thể cấp:

~~~bash
APP_BACKENDS_0_URL=https://temporary.example.test java -jar app.jar
~~~

Giả sử biến môi trường đó được nhận dạng và là nguồn ưu tiên cao nhất liên quan tới danh sách, cần chú ý đến khả năng **toàn bộ List binding lấy dữ liệu từ nguồn biến môi trường** chứ không tự bổ sung mọi field và mọi item từ YAML.

Điểm này đặc biệt quan trọng trong Docker Compose và Kubernetes: dù chỉ thay đổi một biến môi trường tưởng như nhỏ, kết quả list binding có thể khác với kỳ vọng cập nhật từng trường.

Để tránh cấu hình thiếu, có thể:

- Cấp đủ mọi biến môi trường cần thiết cho toàn bộ List.
- Tạo file cấu hình riêng theo môi trường với danh sách đầy đủ.
- Chuyển cấu trúc sang Map nếu muốn override các đối tượng theo key ổn định.
- Thêm validation để từ chối danh sách thiếu field bắt buộc.

Không nên đưa password, token hoặc các secret vào ví dụ CLI/log. Với dữ liệu nhạy cảm cần dùng nguồn secret phù hợp và kiểm soát quyền đọc.

## 12. Các profile có tạo ra cách merge List khác không?

Không. Một profile chỉ làm thay đổi **tập tài liệu cấu hình đang hoạt động và thứ tự ưu tiên của chúng**. Khi nhiều tài liệu cùng cung cấp một List, quy tắc replacement vẫn áp dụng.

Giả sử:

~~~yaml
# application.yml
app:
  backends:
    - name: default
      url: https://default.example.test
~~~

~~~yaml
# application-staging.yml
app:
  backends:
    - name: staging
      url: https://staging.example.test
~~~

~~~yaml
# application-prod.yml
app:
  backends:
    - name: prod
      url: https://prod.example.test
~~~

Khi chạy với profile `staging`, list có item `staging`. Khi chạy với profile `prod`, list có item `prod`. Khi chạy với nhiều profile, các file tương ứng được tham gia theo quy tắc thứ tự profile, location group và config data priority. **List đến từ tài liệu có ưu tiên cao nhất phù hợp**, không phải phép nối của mọi file profile đang bật.

Ví dụ:

~~~bash
java -jar app.jar --spring.profiles.active=staging,prod
~~~

Trong cấu hình đơn giản này và không có nguồn khác ghi đè, profile được khai báo sau có thể ghi đè giá trị trùng tên của profile trước. Không nên mặc định rằng có hai profile thì danh sách kết quả sẽ gồm một item `staging` và một item `prod`.

Khi dùng nhiều file ngoài, `spring.config.import` hoặc location groups qua `spring.config.location`, cần xác định đúng priority của các tài liệu. Quy tắc lựa chọn List **không thay đổi**, nhưng việc xác định “nguồn nào cao nhất” có thể phức tạp hơn.

## 13. Thứ tự ưu tiên không phụ thuộc vào vị trí phần tử

Danh sách biểu diễn bằng index, nhưng **index không quyết định priority giữa các nguồn**.

Ví dụ YAML trong nguồn thấp:

~~~yaml
app:
  backends:
    - name: alpha
      url: https://alpha.example.test
    - name: beta
      url: https://beta.example.test
    - name: gamma
      url: https://gamma.example.test
~~~

Nguồn cao:

~~~properties
app.backends[2].name=gamma-override
app.backends[2].url=https://gamma-new.example.test
~~~

Không nên suy ra binder sẽ giữ ``alpha`` và ``beta`` từ nguồn thấp rồi điền phần tử index `2` của nguồn cao. Index chỉ là địa chỉ của phần tử **trong một nguồn**, còn binding List nhiều nguồn không phải phép merge theo index.

Ngoài ra, nhiều collection binder kỳ vọng các index bắt đầu từ `0` và tạo thành dải phù hợp để tạo list. Chỉ khai báo index `2` mà thiếu `0` và `1` trong nguồn ưu tiên cao có thể dẫn đến list không như mong đợi hoặc binding thất bại tùy tình huống và kiểu dữ liệu. Cách an toàn là khai báo danh sách hoàn chỉnh, bắt đầu từ index `0` và không tạo lỗ.

## 14. Khi khai báo List rỗng: tránh nhầm “không khai báo” với “xóa tất cả”

Cấu hình YAML có thể thể hiện danh sách rỗng:

~~~yaml
app:
  backends: []
~~~

Nhưng cần phân biệt:

~~~yaml
# Không khai báo property app.backends:
app:
  routing-enabled: false
~~~

và:

~~~yaml
# Có khai báo app.backends theo dạng empty list:
app:
  backends: []
~~~

Chúng **không mang cùng ý định**. Trường hợp thứ nhất thường cho phép binder lấy danh sách từ nguồn ưu tiên thấp hơn; trường hợp thứ hai diễn tả ý muốn list không có phần tử.

Trong thực tế, cách biểu diễn collection rỗng có thể chịu ảnh hưởng của format, binder và việc dữ liệu được làm phẳng thành property sources. Nếu business rule cần chắc chắn vô hiệu hóa backend routing, dùng một thuộc tính riêng như:

~~~yaml
app:
  routing-enabled: false
~~~

rồi để code bỏ qua danh sách khi tắt routing. Như vậy hệ thống không phải dựa hoàn toàn vào một thủ thuật “xóa list” bằng YAML ở nguồn ưu tiên cao.

Bất kể cách triển khai nào, ứng dụng nên validation trạng thái: nếu `routing-enabled=true` thì phải có ít nhất một backend hợp lệ.

## 15. Validation để phát hiện List bị thay thế ngoài ý muốn

Khi nguồn cao chỉ cấu hình một phần object trong danh sách, field thiếu có thể khiến ứng dụng hoạt động sai. Cách tốt là fail-fast khi cấu hình không đầy đủ.

Với Spring Boot 3.x, dùng Jakarta Bean Validation:

~~~java
package com.example.config;

import java.time.Duration;
import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotEmpty @Valid List<Backend> backends) {

    public record Backend(
            @NotBlank String name,
            @NotBlank String url,
            @NotNull Duration timeout) {
    }
}
~~~

Đăng ký record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AppProperties.class)`. Thông thường cần dependency `spring-boot-starter-validation` để cung cấp Bean Validation implementation phù hợp.

Nếu nguồn cao chỉ có:

~~~yaml
app:
  backends:
    - url: https://api.example.test
~~~

thì `name` và `timeout` không được lấy từ file có ưu tiên thấp để tự hoàn thiện item. Các constraint `@NotBlank` và `@NotNull` có thể làm ứng dụng thất bại khi binding/validation, giúp phát hiện cấu hình thiếu ngay lúc startup.

Lưu ý:

- `@NotEmpty` kiểm tra List không trống, không kiểm tra từng field của phần tử.
- `@Valid` yêu cầu kiểm tra cả các phần tử con.
- `@NotBlank` từ chối null/blank cho string.
- `@NotNull` từ chối timeout thiếu nhưng không bảo đảm timeout dương; thêm ràng buộc riêng nếu nghiệp vụ cần.
- Với trường `url`, `@NotBlank` không kiểm tra URL đúng HTTPS. Nếu bắt buộc HTTPS, dùng validation riêng.
- Nếu danh sách được phép trống khi tính năng tắt, không nên luôn luôn áp dụng `@NotEmpty`; hãy đặt kiểm tra điều kiện phù hợp.

## 16. Chẩn đoán bằng `Environment` và Actuator

Cần phân biệt **tra cứu một leaf property** với **binding cả collection**.

Ví dụ nguồn thấp khai báo:

~~~properties
app.backends[0].name=primary
app.backends[0].url=https://primary.example.test
app.backends[0].timeout=2s
~~~

Nguồn cao chỉ khai báo:

~~~properties
app.backends[0].url=https://api.example.test
~~~

Một lời gọi tra cứu đơn lẻ kiểu:

~~~java
String name =
        environment.getProperty("app.backends[0].name");
~~~

có thể tìm thấy `"primary"` ở nguồn thấp, vì tên property **`app.backends[0].name`** không có trong nguồn cao.

Tuy nhiên, lời gọi binding cả danh sách:

~~~java
List<Backend> backends =
        Binder.get(environment)
              .bind("app.backends", Bindable.listOf(Backend.class))
              .orElseGet(List::of);
~~~

đang áp dụng **quy tắc List binding**. Không nên lấy kết quả `Environment.getProperty("app.backends[0].name")` để suy ra rằng binder chắc chắn sẽ ghép trường `name` từ nguồn thấp vào object trong list ưu tiên cao.

Để dùng đoạn Binder minh họa cần import:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
~~~

Và định nghĩa `Backend` dưới dạng Java type có thể bind (ví dụ record ở phần 3, hoặc static nested record phù hợp).

**Chẩn đoán thực tế:** nếu có Spring Boot Actuator và endpoint được bật/bảo vệ, `/actuator/env` giúp xem giá trị/property source, còn `/actuator/configprops` giúp xem object đã bind. Phân biệt hai mức quan sát này rất hữu ích khi debug list override.

Các endpoint có thể chứa URL nội bộ hoặc secret; chỉ cấp quyền truy cập phù hợp, sử dụng redaction và không mở công khai để tiện debug.

## 17. Giải pháp khi thực sự muốn merge các phần tử List

### Giải pháp A — Khai báo lại cả List trong nguồn ưu tiên cao

Đây là giải pháp đơn giản nhất khi số phần tử nhỏ hoặc danh sách theo môi trường được quản lý tập trung.

~~~yaml
# application-prod.yml
app:
  backends:
    - name: primary
      url: https://primary-prod.example.test
      timeout: 5s
    - name: backup
      url: https://backup-prod.example.test
      timeout: 7s
~~~

Ưu điểm: kết quả rõ ràng, dễ validate, không cần code merge. Nhược điểm: các field giống nhau có thể phải lặp giữa các môi trường.

### Giải pháp B — Biểu diễn cấu hình bằng Map

Nếu phần tử được nhận diện bằng tên ổn định:

~~~yaml
# application.yml
app:
  backends:
    primary:
      url: https://primary.example.test
      timeout: 2s
    backup:
      url: https://backup.example.test
      timeout: 4s
~~~

~~~yaml
# application-prod.yml
app:
  backends:
    primary:
      url: https://primary-prod.example.test
~~~

Dùng:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Map<String, Backend> backends) {

    public record Backend(String url, Duration timeout) {
    }
}
~~~

Với Map binding, key `primary` có thể nhận URL từ profile và timeout từ file gốc; key `backup` vẫn có thể được giữ lại.

Nếu routing cần một thứ tự, hãy thêm property riêng như `order` hoặc `priority` vào mỗi entry và sắp xếp trong mã Java sau khi bind.

### Giải pháp C — Hai List với hai prefix và merge trong mã nghiệp vụ

Một số hệ thống cần sự khác biệt rõ ràng giữa danh sách mặc định và danh sách bổ sung:

~~~yaml
app:
  defaults:
    backends:
      - name: primary
        url: https://primary.example.test
        timeout: 2s

  extra:
    backends:
      - name: secondary
        url: https://secondary.example.test
        timeout: 4s
~~~

Bind hai collection vào hai property path khác nhau, sau đó gộp bằng logic riêng:

~~~java
List<Backend> combined = new ArrayList<>(defaults.backends());
combined.addAll(extra.backends());
~~~

Đây là **merge do ứng dụng tự định nghĩa**, không phải merge mặc định của Spring Boot Binder. Bạn phải quyết định quy tắc trùng phần tử theo name/id, thứ tự, xung đột và validation. Ví dụ cần import `java.util.ArrayList` và dùng type `Backend` phù hợp.

### Giải pháp D — Chuẩn bị một file cấu hình hiệu lực trước khi chạy

Trong pipeline triển khai, có thể sinh một YAML theo môi trường đã chứa danh sách đầy đủ, thay vì cố override từng index từ nhiều file rời rạc.

Chọn cách này khi muốn team vận hành quan sát **một bộ cấu hình cuối rõ ràng**, đồng thời không muốn mang logic merge vào Java.

## 18. Một ví dụ về rủi ro production

Giả sử default có hai máy chủ dự phòng:

~~~yaml
app:
  targets:
    - id: east
      address: https://east.example.test
      timeout: 2s
    - id: west
      address: https://west.example.test
      timeout: 2s
~~~

Deployment production chỉ muốn đổi địa chỉ của `east` nên thêm:

~~~yaml
app:
  targets:
    - address: https://east-prod.example.test
~~~

Kết quả khi bind List không phải “giữ `east` với timeout 2s và giữ `west`”. Danh sách có thể chỉ còn **một target** với `address` mới; `id` và `timeout` không được kế thừa từ list nguồn thấp.

Hậu quả tiềm ẩn:

1. **Mất dự phòng:** target `west` không còn trong danh sách hiệu lực.
2. **Thiếu metadata:** ứng dụng không biết tên `id` của phần tử còn lại.
3. **Timeout bất ngờ:** `Duration` thiếu gây lỗi hoặc logic fallback ngoài dự kiến.
4. **Sự cố chỉ xuất hiện ở môi trường prod:** local không có profile ghi đè nên list đầy đủ.

Cách phòng ngừa:

- Validation khi startup.
- Đơn vị test với hai property sources theo mức ưu tiên.
- Log/tóm tắt **metadata không nhạy cảm** về số lượng target và định danh, tránh log credentials.
- Quy định trong tài liệu triển khai rằng override List nghĩa là **cung cấp danh sách mới hoàn chỉnh**.

## 19. Bài tập: dự đoán List và Map sau khi kích hoạt profile

File `application.yml`:

~~~yaml
app:
  workers:
    - name: normal
      threads: 2
    - name: fallback
      threads: 1

  flags:
    audit: "true"
    region: global
~~~

File `application-prod.yml`:

~~~yaml
app:
  workers:
    - name: production
      threads: 8

  flags:
    region: apac
    metrics: "enabled"
~~~

Chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

**Câu hỏi 1:** `workers` có bao nhiêu phần tử?

**Đáp án:** Một phần tử `production` với `threads=8`. Item `fallback` từ file mặc định không được giữ lại, vì danh sách ở file production có ưu tiên cao hơn.

**Câu hỏi 2:** `flags` có các key nào?

**Đáp án:** Ba key `audit`, `region`, `metrics`. `audit=true` đến từ file mặc định, `region=apac` được ghi đè, `metrics=enabled` được bổ sung từ file production.

**Câu hỏi 3:** Nếu file `application-prod.yml` chỉ có:

~~~yaml
app:
  workers:
    - name: production
~~~

thì `threads` của phần tử 0 có tự lấy `2` từ file mặc định không?

**Đáp án:** Không. Nếu type `threads` là `Integer`, kết quả có thể là `null`; nếu là primitive `int`, giá trị có thể là mặc định kiểu `0`. Điều quan trọng là **`2` không được tự ghép theo index từ nguồn thấp**. Validation nên phát hiện giá trị thiếu hoặc không hợp lệ.

**Câu hỏi 4:** Nếu file production chỉ override `flags.region` mà không khai báo `workers` thì sao?

**Đáp án:** Danh sách `workers` có thể tiếp tục lấy hai phần tử từ file mặc định, còn map `flags` cập nhật key `region` và giữ `audit`.

**Câu hỏi 5:** Nếu muốn đổi riêng `threads` của worker có tên `normal` nhưng không làm mất `fallback` thì nên thiết kế gì?

**Đáp án:** Có thể khai báo lại cả list trong file ưu tiên cao; hoặc chuyển từ List sang Map có key `normal` và `fallback`, để các giá trị gắn với key có thể được phối hợp từ nhiều nguồn. Nếu vẫn cần thứ tự worker, định nghĩa thứ tự độc lập.

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “Profile prod chỉ ghi đè `backends[0]` nên `backends[1]` từ default vẫn tồn tại.” | Bind List theo nguồn ưu tiên cao; phần tử nguồn thấp không tự merge. |
| “List được merge theo index giống JavaScript object.” | Không. Cơ chế config binding của Spring Boot khác thao tác merge object tổng quát. |
| “Nguồn cao chỉ khai báo `url` thì `name` vẫn kế thừa từ phần tử 0 nguồn thấp.” | Không nên kỳ vọng vậy; nested fields có thể thiếu. |
| “Tất cả collection đều bị thay toàn bộ.” | `Map` có thể kết hợp key từ nhiều nguồn. |
| “`@ConfigurationProperties` là record nên List merge khác JavaBean.” | Kiểu container của cấu hình không làm đổi quy tắc List precedence. |
| “`Environment.getProperty` thấy một leaf field từ nguồn thấp nghĩa là List cũng merge field ấy.” | Tra cứu key đơn và bind collection là hai thao tác có quy tắc khác nhau. |
| “Chỉ cần thêm profile mới là Spring Boot nối danh sách các profile.” | Profile chọn config data tham gia; nó không bật chức năng nối List. |
| “Biến môi trường chỉ override một index thì an toàn.” | Biến môi trường có thể trở thành nguồn list ưu tiên cao, khiến các item/field khác không được kế thừa. |
| “List rỗng và List không được khai báo là một.” | Có khác biệt về ý định và biểu diễn; cần quan sát behavior nếu muốn xóa list bằng cấu hình rỗng. |
| “Không có lỗi startup nghĩa là list đầy đủ.” | Nếu thiếu validation, list ngắn hoặc thiếu field vẫn có thể được bind. |

## 21. Ghi nhớ

- **`List`:** nguồn cấu hình có mức ưu tiên cao hơn cung cấp danh sách sẽ **thay thế danh sách** từ nguồn thấp hơn trong `@ConfigurationProperties` binding; không nối phần tử và không merge field theo index.
- **`Map`:** có thể **kết hợp các key** từ nhiều nguồn, với giá trị trùng key được quyết định bởi mức ưu tiên.
- **Nguồn không khai báo list:** không tự xóa một list đã có ở nguồn thấp.
- **Override một phần tử List:** có thể làm mất các field chưa khai báo và các phần tử khác; hãy viết lại danh sách đầy đủ hoặc dùng model Map theo định danh ổn định.
- **Kiểm tra bằng bean đã bind**, không chỉ xem một key qua `Environment.getProperty`. Cân nhắc `@Validated`, `@NotEmpty`, `@Valid` và các constraint cho từng field bắt buộc.
- **Thứ tự ưu tiên nguồn và quy tắc binding khác nhau:** một nguồn thắng vì property-source priority, còn việc List có merge hay không là quyết định của binder cho kiểu collection.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration, Merging Complex Types: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Profiles: https://docs.spring.io/spring-boot/reference/features/profiles.html
- Spring Boot API — Binder: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/bind/Binder.html
