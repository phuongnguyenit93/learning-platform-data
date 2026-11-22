# Cách Map kết hợp các khóa từ nhiều nguồn cấu hình

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Collection và Map

## 1. Bài toán: nhiều nơi cùng cung cấp một Map

Trong Spring Boot, một ứng dụng có thể nhận cấu hình từ `application.yml`, `application-{profile}.yml`, file nằm ngoài JAR, biến môi trường, Java system properties, `SPRING_APPLICATION_JSON` hoặc command-line arguments. Khi cấu hình là một giá trị đơn như `server.port`, quy tắc thường dễ nhận thấy: nguồn có ưu tiên cao hơn sẽ cung cấp giá trị cuối cùng.

Với một `Map<K, V>` trong `@ConfigurationProperties`, tình huống thú vị hơn: hai nguồn cấu hình có thể chứa **những key khác nhau của cùng một map**, hoặc chứa **cùng key nhưng khác value**. Spring Boot Binder không nhất thiết chọn nguyên một map từ một nguồn rồi bỏ qua tất cả các entry của nguồn khác.

Quy tắc cốt lõi:

> Khi bind một `Map`, Spring Boot có thể **kết hợp các entry đến từ nhiều property sources**. Entry mới ở nguồn ưu tiên cao hơn được bổ sung; nếu **cùng một property** xuất hiện trong nhiều nguồn, giá trị của nguồn ưu tiên cao hơn được dùng.

Đây là hành vi được trình bày trong mục **Merging Complex Types** của tài liệu Spring Boot. Nó **khác với List**, vốn thường được thay thế toàn bộ bởi danh sách từ nguồn ưu tiên cao thay vì nối hay trộn các phần tử.

### Mục tiêu bài học

Sau bài học, bạn sẽ:

- Bind `Map<String,String>` và `Map<String, SomeProperties>` từ nhiều nguồn khác nhau.
- Tính được map kết quả khi nguồn thấp khai báo key A, B còn nguồn cao khai báo B, C.
- Hiểu object nằm **bên trong một entry Map** có thể nhận các field từ nhiều nguồn.
- Phân biệt cơ chế kết hợp Map với cơ chế thay thế List.
- Giải thích thứ tự ưu tiên của file mặc định, file theo profile, environment variables, system properties, JSON và CLI.
- Giữ đúng map key khi tên chứa `/`, dấu chấm hoặc ký tự đặc biệt.
- Chẩn đoán sai key, sai kiểu, xung đột cấu hình và thiết kế test tái lập.

## 2. Cơ chế chung: Environment, PropertySource và Binder

Có ba lớp khác nhau:

1. **`PropertySource`**: mỗi nguồn cấu hình đưa vào `Environment` những property có tên và giá trị.
2. **Thứ tự ưu tiên**: nếu cùng một tên property xuất hiện nhiều nơi, Spring Boot xác định giá trị có hiệu lực theo precedence.
3. **`ConfigurationProperties Binder`**: tập hợp những property phù hợp prefix và chuyển chúng thành Java object, gồm các field scalar, object lồng nhau, collection và Map.

Sơ đồ:

~~~text
application.yml             catalog.labels.owner = platform
application-dev.yml         catalog.labels.region = apac
OS environment              CATALOG_LABELS_TEAM = catalog
Command line                --catalog.labels.region=eu
          \                       |                       /
           \                      v                      /
            +---- Spring Environment / PropertySources ---+
                                |
                                v
                  @ConfigurationProperties Binder
                                |
                                v
                  Map<String, String> labels
                    owner  = platform
                    region = eu
                    team   = catalog
~~~

Sơ đồ minh họa khi profile `dev` hoạt động và không có nguồn ưu tiên cao hơn ngoài những nguồn đã nêu. `region` do CLI cung cấp nên thắng `application-dev.yml`; `owner` và `team` vẫn được giữ từ nguồn của chúng.

**Điểm mấu chốt:** Map trong bean được dựng từ **các property con** của prefix, không phải lúc nào cũng là một scalar duy nhất tên `catalog.labels`.

## 3. Ví dụ cơ bản: Map<String, String> kết hợp entry

### 3.1. Cấu hình mặc định

`src/main/resources/application.yml`:

~~~yaml
catalog:
  labels:
    owner: platform
    region: global
    version: v1
~~~

Giả sử bean:

~~~java
package com.example.catalog.config;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        Map<String, String> labels
) {}
~~~

Khi chỉ có file mặc định, `labels` chứa:

~~~text
owner   = platform
region  = global
version = v1
~~~

### 3.2. Ghi đè một entry và bổ sung một entry khác

`src/main/resources/application-dev.yml`:

~~~yaml
catalog:
  labels:
    region: apac
    stage: development
~~~

Khởi động:

~~~bash
java -jar catalog.jar --spring.profiles.active=dev
~~~

Trong trường hợp config data thông thường, file theo profile có ưu tiên cao hơn file mặc định cùng location. Map kết quả:

| Key | `application.yml` | `application-dev.yml` | Kết quả |
| --- | --- | --- | --- |
| `owner` | `platform` | không khai báo | `platform` |
| `region` | `global` | `apac` | `apac` |
| `version` | `v1` | không khai báo | `v1` |
| `stage` | không khai báo | `development` | `development` |

Kết quả tương đương:

~~~text
labels = {
  owner=platform,
  region=apac,
  version=v1,
  stage=development
}
~~~

Không phải map mới chỉ còn `region` và `stage`. Những key `owner` và `version` có thể tiếp tục được bind từ file mặc định vì nguồn cao hơn không khai báo lại đúng property của chúng.

### 3.3. Ghi đè thêm bằng CLI

Chạy:

~~~bash
java -jar catalog.jar \
  --spring.profiles.active=dev \
  --catalog.labels.region=eu \
  --catalog.labels.deploy-id=build-42
~~~

Khi command-line properties được bật theo cơ chế mặc định, kết quả:

~~~text
owner     = platform
region    = eu
version   = v1
stage     = development
deploy-id = build-42
~~~

`region` từ CLI có ưu tiên cao hơn giá trị `apac` từ file profile. `deploy-id` là entry bổ sung, không làm mất các entry đã được bind từ nguồn thấp hơn.

## 4. Phân biệt entry Map và property bên trong entry

Với `Map<String,String>`, mỗi entry có một scalar value. Nhưng `Map<String, Backend>` có thể chứa **object nhiều field**. Trong trường hợp đó, một key map (ví dụ `primary`) có thể nhận các field từ nhiều nguồn.

Ví dụ:

~~~text
routing.backends.primary.url
routing.backends.primary.timeout
routing.backends.primary.enabled
routing.backends.backup.url
routing.backends.backup.timeout
~~~

Ở đây:

- `backends` là tên field Map.
- `primary` và `backup` là các map keys.
- `url`, `timeout`, `enabled` là field của value object.
- Precedence áp dụng đến các property cụ thể như `routing.backends.primary.timeout`.

### 4.1. Model Java cho Map của object

Dùng JavaBean binding để minh họa rõ việc cập nhật các field nested:

~~~java
package com.example.routing.config;

import java.net.URI;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public class RoutingProperties {

    private final Map<String, Backend> backends = new LinkedHashMap<>();

    public Map<String, Backend> getBackends() {
        return backends;
    }

    public static class Backend {
        private URI url;
        private Duration timeout;
        private boolean enabled;

        public URI getUrl() { return url; }
        public void setUrl(URI url) { this.url = url; }

        public Duration getTimeout() { return timeout; }
        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
~~~

Đăng ký cấu hình bằng scanning:

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

Spring Boot bind các giá trị vào `RoutingProperties` khi bean được đăng ký thành công. `LinkedHashMap` trong ví dụ là kiểu collection Java; **không nên phụ thuộc vào thứ tự duyệt Map để quyết định thứ tự ưu tiên property sources**. Precedence được giải quyết trước trong Binder, không dựa trên vị trí entry khi lặp map.

### 4.2. File mặc định định nghĩa hai backend

`application.yml`:

~~~yaml
routing:
  backends:
    primary:
      url: "https://primary.example.test"
      timeout: 5s
      enabled: true
    backup:
      url: "https://backup.example.test"
      timeout: 10s
      enabled: false
~~~

Kết quả ban đầu:

~~~text
primary.url      = https://primary.example.test
primary.timeout  = 5s
primary.enabled  = true

backup.url       = https://backup.example.test
backup.timeout   = 10s
backup.enabled   = false
~~~

### 4.3. File profile thay đổi một field của primary và thêm backend

`application-prod.yml`:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
    analytics:
      url: "https://analytics.example.test"
      timeout: 7s
      enabled: true
~~~

Với `prod` active, trong các file của ví dụ:

| Map key | Field | Default | Prod | Kết quả |
| --- | --- | --- | --- | --- |
| `primary` | `url` | `https://primary.example.test` | không có | từ default |
| `primary` | `timeout` | `5s` | `2s` | `2s` |
| `primary` | `enabled` | `true` | không có | `true` |
| `backup` | `url` | `https://backup.example.test` | không có | từ default |
| `backup` | `timeout` | `10s` | không có | `10s` |
| `backup` | `enabled` | `false` | không có | `false` |
| `analytics` | `url` | không có | `https://analytics.example.test` | từ prod |
| `analytics` | `timeout` | không có | `7s` | `7s` |
| `analytics` | `enabled` | không có | `true` | `true` |

Kết quả `Map<String, Backend>` chứa **ba key**: `primary`, `backup`, `analytics`. Trong entry `primary`, `timeout` lấy giá trị mới còn `url` và `enabled` vẫn có thể lấy từ file mặc định.

Điều này quan trọng: nói “Map merge” không chỉ có nghĩa thêm key mới ở top-level. Với **object value**, nhiều field của cùng một map entry có thể được bind từ các property sources khác nhau.

### 4.4. Không có dữ liệu cho một field không tự xóa field từ nguồn dưới

Nếu `application-prod.yml` chỉ khai báo:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
~~~

thì việc không nhắc tới `url` **không** tương đương việc gửi yêu cầu “xóa url”. Binder vẫn có thể tìm `routing.backends.primary.url` trong nguồn khác.

Muốn một hành vi như “tắt primary”, nên cấu hình tường minh:

~~~yaml
routing:
  backends:
    primary:
      enabled: false
~~~

Không dùng sự vắng mặt của field trong nguồn ưu tiên cao như một phép xóa property có chủ đích.

## 5. Map không hoạt động như List

Spring Boot có quy tắc khác biệt cho `List`/`Array`. Khi một danh sách xuất hiện ở nhiều nguồn cấu hình, danh sách của nguồn có ưu tiên cao thường **thay thế toàn bộ danh sách** của nguồn thấp.

### 5.1. So sánh với cùng bài toán

`application.yml`:

~~~yaml
routing:
  regions:
    - "sg"
    - "jp"
  labels:
    owner: "core"
    stage: "default"
~~~

`application-prod.yml`:

~~~yaml
routing:
  regions:
    - "eu"
  labels:
    stage: "production"
    cluster: "blue"
~~~

Nếu profile `prod` hoạt động:

~~~text
routing.regions = ["eu"]

routing.labels = {
  owner="core",
  stage="production",
  cluster="blue"
}
~~~

**List `regions`** không trở thành `["sg", "jp", "eu"]`. Nó chỉ có `["eu"]` từ nguồn ưu tiên cao.

**Map `labels`** có thể giữ entry `owner`, ghi đè `stage` và thêm `cluster`.

### 5.2. List object còn có thể mất các field không được nhắc lại

Ví dụ list ở nguồn thấp:

~~~yaml
routing:
  servers:
    - name: primary
      description: Main server
~~~

Nguồn cao hơn:

~~~yaml
routing:
  servers:
    - name: production-primary
~~~

Khi bind vào `List<Server>`, kết quả trong tình huống thông thường là **một phần tử** có `name=production-primary` và `description=null` nếu không có default khác. Không lấy `description=Main server` từ phần tử cùng index của nguồn thấp.

Đó chính là lý do **Map** phù hợp hơn List khi mục tiêu là override **một phần các thuộc tính của từng đối tượng được định danh bằng key ổn định**, ví dụ `backends.primary.timeout`.

### 5.3. Không nên đổi List thành Map chỉ để lấy merge

Hãy chọn cấu trúc theo nghiệp vụ:

- Nếu dữ liệu là danh sách **có thứ tự** hoặc thứ tự phần tử có ý nghĩa, List có thể đúng hơn.
- Nếu dữ liệu là tập đối tượng **được truy cập bằng định danh ổn định** như `primary`, `backup`, `team-a`, Map thường biểu diễn rõ ý định.
- Map không tự bảo đảm thứ tự nghiệp vụ, dù class Java đang dùng `LinkedHashMap`.
- Dùng một key map cố định giúp override các field của cùng đối tượng qua môi trường mà không phải dựa vào index `[0]`, `[1]` dễ thay đổi.

## 6. Thứ tự ưu tiên quyết định entry trùng khóa

Hành vi kết hợp Map không bỏ qua hệ thống precedence của Spring Boot. Với các property cùng tên, **giá trị ưu tiên cao hơn thắng**.

Một cách nhìn đơn giản trong ứng dụng chạy thông thường:

| Nguồn | Ví dụ | Vai trò |
| --- | --- | --- |
| Config data mặc định | `application.yml` | Cung cấp giá trị nền |
| Config data theo profile | `application-prod.yml` | Có thể override bản mặc định trong cùng nhóm location |
| Config data ngoài JAR/imports | `./config/application.yml`, `spring.config.import` | Tham gia các quy tắc thứ tự config data riêng |
| OS environment variables | `ROUTING_LABELS_REGION` | Thường ưu tiên cao hơn config data |
| Java system properties | `-Drouting.labels.region=...` | Thường ưu tiên cao hơn OS env |
| `SPRING_APPLICATION_JSON` | JSON object chứa `routing.labels` | Ưu tiên cao hơn nhiều nguồn thông thường |
| Command-line arguments | `--routing.labels.region=...` | Thường ưu tiên cao hơn JSON trong cấu hình mặc định |

Đây là danh sách **một số nguồn thường gặp**, không phải mọi nguồn của Spring Boot. Trong Servlet, test, devtools hoặc custom environment, sẽ còn nguồn khác. Ngoài ra, thứ tự giữa các tệp và import phụ thuộc location groups, profile, document activation và các tùy chọn `spring.config.*`.

### 6.1. Ví dụ xung đột qua ba nguồn

Default `application.yml`:

~~~yaml
catalog:
  labels:
    owner: platform
    region: global
~~~

Biến môi trường:

~~~bash
export CATALOG_LABELS_REGION=apac
~~~

Chạy:

~~~bash
java -jar catalog.jar \
  --catalog.labels.owner=commerce \
  --catalog.labels.revision=2026-11
~~~

Map kết quả trong cấu hình thông thường:

~~~text
owner    = commerce  (CLI)
region   = apac      (OS environment)
revision = 2026-11   (CLI)
~~~

`owner` từ CLI ghi đè `platform`. `region` từ environment ghi đè `global`. `revision` được thêm từ CLI.

### 6.2. Không lấy thứ tự trong file làm thứ tự ưu tiên xuyên mọi nguồn

Nếu `application-prod.yml` được load sau `application.yml`, đó là quy tắc config data trong hoàn cảnh cụ thể. Một tham số CLI vẫn có thể thắng cả hai. Không được phát biểu rằng “dòng nằm dưới cùng trong YAML luôn thắng” cho mọi nguồn dữ liệu.

Tương tự, giữa các file được `spring.config.import`, Boot có quy tắc import và mức ưu tiên riêng. Khi dự đoán map, cần xác định **nguồn thật sự được nạp** và **nguồn nào ưu tiên hơn**.

## 7. Map trong file YAML đa document

Một file `application.yml` có thể chứa nhiều documents ngăn bằng `---`:

~~~yaml
catalog:
  labels:
    owner: platform
    stage: default
    trace: "false"

---
spring:
  config:
    activate:
      on-profile: dev

catalog:
  labels:
    stage: development
    debug: "true"
~~~

Khi `dev` không active:

~~~text
owner=platform, stage=default, trace=false
~~~

Khi `dev` active:

~~~text
owner=platform, stage=development, trace=false, debug=true
~~~

Các tài liệu trong cùng file được xử lý theo thứ tự; tài liệu sau đang active có thể ghi đè property trùng của tài liệu trước. Map binder kết hợp những key hiện diện từ các document có hiệu lực.

Ở đây `trace` và `debug` được viết thành string có quote vì Map đích là `Map<String,String>`. Nếu Map được định nghĩa `Map<String, Boolean>`, có thể dùng boolean scalar và Spring Boot chuyển đổi kiểu tương ứng.

## 8. Map trong file `.properties`

Không nhất thiết phải dùng YAML để bind Map. Dạng dotted properties cũng biểu diễn được:

~~~properties
catalog.labels.owner=platform
catalog.labels.region=global
catalog.labels.version=v1
~~~

Khi dùng một file theo profile:

~~~properties
# application-prod.properties
catalog.labels.region=eu
catalog.labels.stage=production
~~~

Kết quả theo precedence thông thường:

~~~text
owner=platform
region=eu
version=v1
stage=production
~~~

Điểm cần chú ý là Spring Boot bind theo **đường dẫn property có prefix `catalog.labels`**, không dựa vào việc trong file có một khối YAML tên `labels`. Dạng `.properties` và YAML có thể biểu diễn cùng hợp đồng cấu hình.

Nếu cả `application.properties` và `application.yml` nằm ở cùng location, Spring Boot có quy tắc ưu tiên giữa hai format. Nên chọn một format nhất quán để tránh các xung đột khó quan sát.

## 9. Map từ environment variables

Environment variables thường dùng chữ hoa và dấu gạch dưới. Spring Boot hỗ trợ relaxed binding để ánh xạ tên biến sang property.

Ví dụ:

~~~bash
export CATALOG_LABELS_TEAM=backend
export CATALOG_LABELS_REGION=apac
java -jar catalog.jar
~~~

Với `@ConfigurationProperties(prefix="catalog")` và field `Map<String,String> labels`, có thể bind các entry:

~~~text
team   = backend
region = apac
~~~

### 9.1. Key map từ biến môi trường được chuyển về chữ thường

Điểm dễ bỏ qua được Spring Boot nêu trong phần **Binding Maps From Environment Variables**: khi bind từ system environment, Boot lower-case tên environment variable. Vì vậy, một entry được khai báo bằng biến:

~~~bash
export MY_PROPS_VALUES_KEY=VALUE
~~~

trong mô hình `@ConfigurationProperties(prefix="my.props")` có `Map<String,String> values` thường tạo key `key`, còn value là `VALUE`. **Tên key** được lower-case, nhưng **nội dung value** không bị lower-case.

Không nên dựa vào biến môi trường để cung cấp một map key cần phân biệt chữ hoa/thường chính xác (ví dụ tên header hoặc token identifier có casing quan trọng) nếu quy tắc binding không đáp ứng yêu cầu. Với map key phức tạp, cân nhắc YAML/properties hoặc JSON có cú pháp thích hợp.

### 9.2. Dấu gạch ngang trong tên field

Một field Java `defaultRegion` thường có property canonical `catalog.default-region`. Theo quy ước Boot, environment variable tương ứng là `CATALOG_DEFAULTREGION`: thay `.` bằng `_`, bỏ `-`, viết hoa. Nếu cấu hình là Map, các segment dành cho tên field và map key cần được tổ chức nhất quán.

Không tự suy luận rằng mọi dấu gạch dưới đều là một ký tự literal của map key. Relaxed binding có cách phân tách tên property theo nguồn.

### 9.3. Một key cần giữ nguyên dấu chấm hoặc ký tự đặc biệt

Environment variables có giới hạn về ký tự tên. Ví dụ `/webhook` hoặc `tenant.a` không phải lúc nào cũng biểu diễn nguyên vẹn bằng biến môi trường theo cấu trúc mặc định. Trong trường hợp này, JSON hoặc file YAML/properties với **bracket notation** thường dễ kiểm soát hơn.

## 10. Map từ `SPRING_APPLICATION_JSON`

Biến `SPRING_APPLICATION_JSON` cho phép truyền một JSON object có cấu trúc. Ví dụ:

~~~bash
export SPRING_APPLICATION_JSON='{"catalog":{"labels":{"region":"apac","stage":"staging","owner":"commerce"}}}'
java -jar catalog.jar
~~~

Với giá trị này, các property `catalog.labels.region`, `catalog.labels.stage` và `catalog.labels.owner` được đưa vào nguồn JSON của Spring Boot.

Nếu `application.yml` còn có:

~~~yaml
catalog:
  labels:
    version: v1
    owner: platform
~~~

thì, nếu không có nguồn nào ưu tiên hơn JSON:

~~~text
region  = apac
stage   = staging
owner   = commerce
version = v1
~~~

`owner` lấy từ JSON; `version` vẫn lấy từ YAML. Đây là một ví dụ Map nhận các entry từ **hai loại PropertySource khác nhau**, không chỉ các file config data.

### 10.1. JSON null không phải cách xóa entry cũ

Nếu nguồn JSON chứa:

~~~json
{
  "catalog": {
    "labels": {
      "owner": null
    }
  }
}
~~~

thì không nên kỳ vọng `null` sẽ xóa `catalog.labels.owner` từ YAML. Spring Boot xử lý JSON `null` như missing value trong property resolution, nên nguồn thấp hơn vẫn có thể cung cấp giá trị.

Đây là điểm khác biệt giữa **đè một key bằng một giá trị thật** và **yêu cầu xóa key**. Cấu hình của Spring Boot không phải một bộ JSON Patch. Nếu cần vô hiệu hóa entry, thiết kế cơ chế nghiệp vụ rõ ràng thay vì mặc định null có nghĩa delete.

### 10.2. JSON nhiều cấp và Map value là object

~~~json
{
  "routing": {
    "backends": {
      "primary": {
        "timeout": "2s"
      },
      "analytics": {
        "url": "https://analytics.example.test",
        "enabled": true
      }
    }
  }
}
~~~

Với `Map<String, Backend>` ở mục 4, JSON có thể override riêng `primary.timeout` và thêm `analytics`, trong khi các field `primary.url`, `primary.enabled` và entry `backup` vẫn lấy từ default YAML nếu không có nguồn ưu tiên hơn thay thế.

Không cần parse chuỗi JSON bằng tay trong service khi Spring Boot đã cung cấp nguồn `spring.application.json`.

## 11. Map keys có dấu chấm, slash và ký tự đặc biệt

Không phải mọi tên map key đều là một từ đơn giản như `primary` hoặc `region`. Một số ứng dụng dùng route `/v1/orders`, tên header hoặc tên domain.

Spring Boot cung cấp **bracket notation** khi bind Map để giữ nguyên key chứa ký tự đặc biệt. Nếu key không được bao bằng `[ ]`, những ký tự không thuộc chữ/số, dấu `-` hoặc dấu `.` có thể bị loại bỏ trong quá trình chuẩn hóa tên.

### 11.1. Trong file properties

~~~properties
gateway.routes.[/orders]=orders-service
gateway.routes.[/inventory]=inventory-service
gateway.routes./legacy=legacy-service
~~~

Giả sử `Map<String,String> routes`, kết quả có thể là:

~~~text
/orders    -> orders-service
/inventory -> inventory-service
legacy     -> legacy-service
~~~

Key `/legacy` bị mất dấu `/` vì không có bracket notation. Đây có thể là một lỗi rất khó nhìn thấy khi cấu hình route.

### 11.2. Trong YAML, phải quote key chứa bracket

~~~yaml
gateway:
  routes:
    "[/orders]": orders-service
    "[/inventory]": inventory-service
    "/legacy": legacy-service
~~~

Dấu nháy quanh `"[/orders]"` giúp YAML parser hiểu đó là một scalar key. Binder sau đó dùng bracket notation để giữ slash trong map key.

**Không dùng** `[/orders]` trần trong YAML theo giả định nó sẽ được parse như một string bình thường. Ký tự bracket có ý nghĩa cú pháp đối với YAML.

### 11.3. Dấu chấm trong map key: phụ thuộc kiểu value

Tài liệu Spring Boot phân biệt hai tình huống:

- Với `Map<String,String>` hoặc map có scalar value theo những kiểu được hỗ trợ, dấu chấm trong key thường có thể được giữ mà không cần bracket.
- Với `Map<String,Object>` hoặc nested object value, dấu chấm có thể được hiểu là **dấu phân cách các cấp property**, nên muốn giữ toàn bộ key cần bracket notation.

Ví dụ:

~~~properties
example.values.a.b=c
~~~

Với `Map<String,String> values`, có thể bind entry có key `a.b` và value `c`.

Nhưng nếu `values` là `Map<String,Object>`, đường dẫn `a.b` có thể tạo một Map lồng như `a -> b -> c` thay vì một key literal `a.b`.

Để giữ key literal:

~~~properties
example.values.[a.b]=c
~~~

Trong YAML:

~~~yaml
example:
  values:
    "[a.b]": c
~~~

Không sử dụng một mẫu key naming mà không xét **kiểu value của Map**.

### 11.4. Key map là business identifier chứ không phải Java field

Trong:

~~~yaml
tenant:
  endpoints:
    "[tenant.a]": "https://tenant-a.example.test"
    "[tenant.b]": "https://tenant-b.example.test"
~~~

`tenant.a` và `tenant.b` là **map key**, không phải field của class Java. Nếu tên này là ID có ý nghĩa nghiệp vụ, hãy giữ nguyên theo bracket notation khi cần, rồi truy cập bằng `map.get("tenant.a")`.

Khác biệt với nested object: `Map<String, Endpoint>` có thể yêu cầu key literal phù hợp để tránh Binder diễn giải nhầm dấu chấm thành phân cấp trong Endpoint.

## 12. Mẫu thiết kế Map cho cấu hình có kiểu

Một cấu trúc phổ biến là tên environment, tên backend hoặc tên nhà cung cấp làm key:

~~~yaml
payments:
  providers:
    primary:
      endpoint: "https://pay-a.example.test"
      timeout: 3s
    secondary:
      endpoint: "https://pay-b.example.test"
      timeout: 5s
~~~

Record cấu hình:

~~~java
package com.example.payments.config;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        Map<String, Provider> providers
) {
    public record Provider(URI endpoint, Duration timeout) {}
}
~~~

Đăng ký record qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Một service có thể lấy provider:

~~~java
public PaymentProperties.Provider findProvider(
        PaymentProperties properties, String name) {
    PaymentProperties.Provider provider =
            properties.providers().get(name);

    if (provider == null) {
        throw new IllegalArgumentException(
                "Không có cấu hình provider: " + name);
    }
    return provider;
}
~~~

### 12.1. Ưu điểm khi dùng Map có key ổn định

- Thêm một provider chỉ bằng khai báo một key mới trong config.
- Override `payments.providers.primary.timeout` mà không phải sao chép toàn bộ provider.
- Có thể dùng giá trị mặc định và bổ sung cấu hình riêng cho từng môi trường.
- Code dễ truy cập provider theo tên hơn là dựa vào index danh sách.
- Sự khác biệt giữa các môi trường có thể nhỏ và tập trung vào field cần đổi.

### 12.2. Rủi ro cần kiểm soát

- Một provider bị cấu hình thiếu `endpoint` trong mọi nguồn có thể tạo object thiếu field.
- Một map key viết sai (`primray` thay vì `primary`) có thể tạo **entry mới ngoài ý muốn**, không phải override.
- Mỗi môi trường có thể thêm entry không mong muốn nếu không giới hạn tập provider hợp lệ.
- Một value kiểu URL hoặc Duration sai sẽ gây binding/conversion error.
- Map có key đặc biệt có thể bị chuẩn hóa tên nếu không dùng cú pháp giữ key phù hợp.

Nên dùng validation và test binding cho các key thiết yếu, thay vì dựa vào việc map có ít nhất một entry.

## 13. Validation cho Map và các value object

Dùng `@Validated` kết hợp Bean Validation khi cấu hình có yêu cầu bắt buộc. Ví dụ Spring Boot 3, Java 17+:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "payments")
@Validated
public record PaymentProperties(
        @NotEmpty Map<String, @Valid Provider> providers
) {
    public record Provider(
            @NotNull URI endpoint,
            @NotNull Duration timeout
    ) {}
}
~~~

Ví dụ thể hiện ý tưởng xác thực:

- `@NotEmpty` yêu cầu map có ít nhất một entry.
- `@Valid` được đặt trên map value để yêu cầu cascade validation đến các field của `Provider` khi Bean Validation và container-element validation hoạt động đúng.
- `@NotNull` bảo vệ các field `endpoint` và `timeout` khi cấu hình được bind.

Để sử dụng các annotation của Jakarta trong Spring Boot, cần dependency validation thích hợp, chẳng hạn `spring-boot-starter-validation`. Tùy cách khai báo class và phiên bản validator, có thể dùng thêm `@Valid` ở field record/constructor parameter; hãy xác nhận hành vi mong muốn bằng test startup/binding.

Với `Map<String,String>`, hãy cân nhắc các constraint cụ thể cho các value, hoặc một validator tùy chỉnh khi mỗi key yêu cầu một định dạng khác nhau.

### 13.1. Không suy ra “merge thành công” nghĩa là tất cả entry hợp lệ

Map có thể kết hợp đúng các entry từ nhiều nguồn nhưng vẫn chứa cấu hình lỗi:

~~~yaml
payments:
  providers:
    primary:
      timeout: 3s
~~~

Nếu không có `primary.endpoint` ở nguồn nào khác, entry `primary` chưa hoàn chỉnh. Đây là lỗi cấu hình cần được phát hiện, không phải lỗi thuật toán map merge.

### 13.2. Validation và bảo mật

Nếu map chứa API keys hoặc secret, tránh log nguyên object `@ConfigurationProperties`. Một record có thể lộ field qua `toString()`. Các endpoint Actuator như `env` và `configprops` cần được bảo vệ, kiểm soát quyền và che giấu giá trị nhạy cảm.

Map merge không mã hóa, quản lý vòng đời hoặc bảo vệ secrets. Với dữ liệu nhạy cảm, dùng nguồn secret thích hợp và chỉ bind vào Java model ở nơi cần thiết.

## 14. Thêm cấu hình bằng file ngoài JAR

Một ưu điểm lớn của Map merging là cho phép cung cấp **bản cấu hình nền trong artifact** rồi bổ sung một số entry qua file externalized.

`classpath:/application.yml`:

~~~yaml
services:
  endpoints:
    billing: "https://billing.default.test"
    inventory: "https://inventory.default.test"
~~~

File `./config/application.yml` bên ngoài JAR:

~~~yaml
services:
  endpoints:
    billing: "https://billing.prod.internal"
    reporting: "https://reporting.prod.internal"
~~~

Nếu ứng dụng chạy với working directory phù hợp và Spring Boot nạp file ngoài JAR qua cơ chế mặc định:

~~~text
billing   = https://billing.prod.internal
inventory = https://inventory.default.test
reporting = https://reporting.prod.internal
~~~

Không cần sao chép entry `inventory` vào file ngoài JAR chỉ để giữ nó. Điều này giảm trùng lặp giữa cấu hình mặc định và cấu hình triển khai.

Lưu ý: file ngoài JAR chỉ được nhận diện nếu nằm ở location mà Boot đang tìm hoặc được nhập đúng cách. Một file bất kỳ không tự trở thành property source.

## 15. `spring.config.import` và nhiều nguồn

Ví dụ `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:file:./config/routing-extra.yml"

routing:
  backends:
    primary:
      url: "https://default.example.test"
      timeout: 5s
~~~

File `./config/routing-extra.yml`:

~~~yaml
routing:
  backends:
    primary:
      timeout: 2s
    analytics:
      url: "https://analytics.example.test"
      timeout: 8s
~~~

Tài liệu import có thứ tự ưu tiên riêng trong cơ chế Config Data. Khi import được nạp và có precedence cao hơn tài liệu khai báo import, kết quả Map có thể là:

~~~text
primary.url     = https://default.example.test
primary.timeout = 2s

analytics.url     = https://analytics.example.test
analytics.timeout = 8s
~~~

Điểm cần nhớ: việc **đưa một file vào `spring.config.import`** là một bước nạp config data; việc **Map kết hợp các entry** là bước binding/giải quyết property. Hai cơ chế phối hợp nhưng không phải cùng một thao tác.

Nếu file import không tồn tại và có prefix `optional:`, Boot có thể bỏ qua vị trí đó mà không lỗi missing location. Điều này không đảm bảo các property bắt buộc đã có đủ: vẫn cần validation.

## 16. Config tree cũng có thể bổ sung key Map

Khi một nền tảng triển khai mount secret hoặc config thành từng file, Spring Boot hỗ trợ:

~~~properties
spring.config.import=optional:configtree:/run/config/
~~~

Giả sử các file:

~~~text
/run/config/
├── services.endpoints.billing
└── services.endpoints.reporting
~~~

Nội dung của mỗi file là value của property tương ứng, chẳng hạn URL của service. Nếu đã có `services.endpoints.inventory` từ `application.yml`, entry inventory vẫn có thể được bind vào Map cùng các entry đến từ config tree.

Điểm khác với YAML là **tên file trở thành property key** và **nội dung file trở thành value**. Config tree không tự đọc mỗi file như một tài liệu `key=value`.

Nếu map chứa secret như password, cần hạn chế quyền truy cập file, tránh in value ra log và hiểu chính sách cập nhật runtime. Việc Secret được cập nhật trên volume không mặc định khiến mọi bean cấu hình đã bind tự cập nhật.

## 17. Nguồn trùng khóa và hành vi “xóa” entry

Spring Boot externalized configuration là cơ chế **định nghĩa và ghi đè property**, không phải một ngôn ngữ patch đầy đủ để thêm/sửa/xóa object như JSON Patch.

### 17.1. Không khai báo key ở nguồn cao không xóa key ở nguồn thấp

Default:

~~~yaml
features:
  flags:
    beta: true
    legacy: true
~~~

Prod:

~~~yaml
features:
  flags:
    beta: false
~~~

Map kết quả thường:

~~~text
beta   = false
legacy = true
~~~

Nếu muốn tắt `legacy`, hãy khai báo giá trị `false` khi kiểu value phù hợp. Nếu muốn **không còn entry legacy**, cần một chính sách thiết kế khác: không cấp ở nguồn nền, lọc/sanitize sau bind bằng logic nghiệp vụ có kiểm soát hoặc dùng cấu trúc cấu hình có ngữ nghĩa xóa rõ ràng.

### 17.2. Giá trị rỗng khác với không khai báo

Một nguồn cao có:

~~~properties
features.labels.owner=
~~~

là một khai báo **chuỗi rỗng** cho `features.labels.owner`. Khi bind `Map<String,String>`, đây có thể là một value rỗng có hiệu lực và ghi đè chuỗi từ nguồn thấp; nó không mặc định có nghĩa “remove map entry”.

Với các kiểu khác, chuỗi rỗng còn có thể gây lỗi conversion hoặc được xử lý theo converter tương ứng. Đừng dùng empty string làm tín hiệu xóa chung cho mọi kiểu.

### 17.3. JSON null không phải thao tác xóa chắc chắn

`SPRING_APPLICATION_JSON` chứa key có value `null` không bảo đảm xóa giá trị tương ứng từ một nguồn thấp; Spring Boot có quy tắc coi JSON null là missing trong property resolution.

Một thiết kế tốt nên dùng flag hoặc cấu hình tường minh, ví dụ:

~~~yaml
routing:
  backends:
    backup:
      enabled: false
~~~

thay vì trông chờ null hoặc key vắng ở nguồn cao tự xóa backend đã có ở cấu hình mặc định.

## 18. Đọc kết quả qua code

### 18.1. Truy cập Map từ bean đã bind

Với `CatalogProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
public class LabelService {

    private final CatalogProperties properties;

    public LabelService(CatalogProperties properties) {
        this.properties = properties;
    }

    public String region() {
        return properties.labels().get("region");
    }
}
~~~

Service đọc kết quả sau binding, không cần tự merge nhiều file. Nếu entry bắt buộc, hãy validate hoặc kiểm tra rõ ràng thay vì để `Map.get(...)` trả null rồi dùng mù.

### 18.2. `Environment.getProperty("catalog.labels")` không phải cùng việc bind Map

Một nhầm lẫn hay gặp:

~~~java
String labels = environment.getProperty("catalog.labels");
~~~

Lệnh trên tra cứu **property có đúng tên `catalog.labels`**. Nó không có nghĩa Spring sẽ tự tạo một chuỗi chứa toàn bộ các key con. Với dữ liệu thực tế chủ yếu tồn tại dưới `catalog.labels.owner`, `catalog.labels.region`, cách đọc một scalar tên `catalog.labels` có thể không cho kết quả mong muốn.

Để nhận cả Map, nên bind bằng `@ConfigurationProperties` hoặc dùng `Binder` của Spring Boot với kiểu đích được chỉ định.

### 18.3. Dùng `Binder` trong trường hợp cần binding theo yêu cầu

Ví dụ khi cần bind trực tiếp từ một `Environment` đã chuẩn bị:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public Map<String, String> readLabels(Environment environment) {
    return Binder.get(environment)
            .bind("catalog.labels",
                    Bindable.mapOf(String.class, String.class))
            .orElse(Map.of());
}
~~~

Ví dụ này minh họa API của Binder và một fallback map rỗng khi nhóm không được bind. Nó không phải yêu cầu mọi service phải tự gọi Binder; với cấu hình tĩnh, bean `@ConfigurationProperties` vẫn là phương án khuyến nghị.

Cần nhớ: `Environment` và `Binder` không có cùng API tra cứu. Một phép `getProperty` trả scalar không thay thế được thao tác bind Map đa nguồn.

## 19. Chẩn đoán khi Map không có entry như mong muốn

Các tình huống điển hình:

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| Map chỉ có entry từ một nguồn | Nguồn còn lại không được nạp, sai prefix hoặc key | Xem file/profile/import/env thực tế |
| Entry trùng key có value bất ngờ | Nguồn ưu tiên cao hơn ghi đè | Kiểm tra precedence và property source |
| Có entry `primray` thay vì `primary` | Gõ sai map key | Sửa key, thêm validation key hợp lệ |
| Slash biến mất khỏi key | Không dùng bracket notation | Viết `[/orders]` và quote trong YAML |
| Key từ environment chuyển thành chữ thường | Quy tắc binding từ system environment | Dùng nguồn thích hợp nếu casing quan trọng |
| Map value object thiếu field | Không có property cho field trong mọi nguồn | Bổ sung nguồn hoặc validation |
| Map chứa key cũ dù profile không khai báo | Source dưới vẫn cung cấp key đó | Dùng flag disable hoặc thiết kế xóa rõ |
| List không ghép entry như Map | List bị thay thế theo precedence | Chọn cấu trúc đúng hoặc cấp toàn bộ list |
| `Environment.getProperty("prefix.map")` trả null | Không có scalar ở tên prefix | Dùng `@ConfigurationProperties` hoặc `Binder` |
| Chuỗi rỗng làm override | Có value rỗng ở nguồn cao | Không dùng empty string để biểu thị vắng mặt |
| Lỗi khi bind URL/Duration | Converter không xử lý được value | Kiểm tra định dạng và kiểu đích |
| Giá trị cũ sau đổi ConfigMap | Bean chưa refresh/rebind hoặc chưa restart | Thiết kế rollout/refresh phù hợp |

### 19.1. Kiểm tra source của một property cụ thể

Với key **không nhạy cảm**, có thể quan sát:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class MapPropertyProbe implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public MapPropertyProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "catalog.labels.region";

        System.out.println("Resolved = "
                + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " => " + value);
            }
        });
    }
}
~~~

Đoạn này chỉ quan sát một key cụ thể. Tên property source và hành vi tra cứu trực tiếp có thể phụ thuộc nguồn/phiên bản Spring Boot; với relaxed binding, một số tên dạng env có thể cần quan sát theo cơ chế khác hoặc dùng Actuator origin tracking.

Không log mật khẩu, token, private key hoặc toàn bộ Map nhạy cảm. Khi bật Actuator `env` hoặc `configprops`, bảo vệ endpoint và thiết lập hiển thị an toàn.

### 19.2. Quy trình suy luận khi một entry sai

1. Xác nhận bean có `@ConfigurationProperties` và được đăng ký bằng scan/enable thích hợp.
2. Xác định prefix thực tế, ví dụ `catalog.labels`.
3. Ghi các property con tương ứng ở từng source đã được nạp.
4. Xác định source có ưu tiên cao hơn cho **mỗi key hoặc field của map value object**.
5. Kiểm tra key đặc biệt có cần bracket notation không.
6. Kiểm tra env key có bị lower-case/chuẩn hóa không.
7. Phân biệt Map, List, nested object và scalar.
8. Kiểm tra conversion, default và validation.
9. Đọc lại bean đã bind và đối chiếu với các property sources có hiệu lực.

Không chỉ nhìn file YAML cuối cùng trên máy developer và cho rằng đó là toàn bộ cấu hình production.

## 20. Kiểm thử Map merging có hệ thống

### 20.1. Test bằng `ApplicationContextRunner`

Với Spring Boot test, có thể tạo một context nhỏ để xác minh binding Map.

Ví dụ sử dụng model `CatalogProperties` trong mục 3:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogPropertiesTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void mapHasMultipleKeys() {
        runner.withPropertyValues(
                "catalog.labels.owner=platform",
                "catalog.labels.region=apac",
                "catalog.labels.stage=dev")
            .run(context -> {
                CatalogProperties config =
                        context.getBean(CatalogProperties.class);

                assertThat(config.labels())
                        .containsEntry("owner", "platform")
                        .containsEntry("region", "apac")
                        .containsEntry("stage", "dev");
            });
    }
}
~~~

Test trên xác nhận việc bind các entry khác nhau vào Map, nhưng các giá trị được cấp qua **một** set test properties. Để kiểm tra đúng precedence giữa **nhiều property sources**, cần tạo hai nguồn độc lập với thứ tự ưu tiên tường minh.

### 20.2. Test xung đột giữa hai nguồn

Ví dụ khởi tạo `StandardEnvironment` và hai `MapPropertySource` để minh họa:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

public class MapBindingExample {

    public static Map<String, String> bind() {
        StandardEnvironment environment = new StandardEnvironment();

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("catalog.labels.owner", "platform");
        defaults.put("catalog.labels.region", "global");

        Map<String, Object> overrides = new LinkedHashMap<>();
        overrides.put("catalog.labels.region", "apac");
        overrides.put("catalog.labels.stage", "dev");

        environment.getPropertySources().addLast(
                new MapPropertySource("defaults", defaults));

        environment.getPropertySources().addFirst(
                new MapPropertySource("overrides", overrides));

        return Binder.get(environment)
                .bind("catalog.labels",
                        Bindable.mapOf(String.class, String.class))
                .orElse(Map.of());
    }
}
~~~

`addFirst` đặt nguồn `overrides` ở mức ưu tiên cao. Kết quả mong muốn:

~~~text
owner  = platform
region = apac
stage  = dev
~~~

Ví dụ chỉ minh họa thứ tự nguồn. `StandardEnvironment` có sẵn những nguồn hệ thống khác; trong ứng dụng/test thực, nên cô lập hoặc kiểm soát môi trường để tránh một giá trị trùng key không mong muốn từ máy chạy test.

### 20.3. Test Map với value là object

Tạo `application.yml` mặc định cho `routing.backends.primary.url` và `routing.backends.primary.timeout`. Sau đó cấp nguồn ưu tiên cao chỉ có `routing.backends.primary.timeout=2s` cùng `routing.backends.analytics.url=...`.

Xác nhận:

- `primary.url` vẫn có giá trị từ nguồn thấp.
- `primary.timeout` được override.
- `analytics` là entry mới.
- Các entry khác như `backup` không bị xóa.

Cách test này thể hiện bản chất Map merging rõ hơn một test chỉ chứa các scalar entries.

## 21. Bài tập thực hành

### Bài tập A: Map String đơn giản

`application.yml`:

~~~yaml
lesson:
  attributes:
    owner: platform
    level: basic
    region: global
~~~

`application-dev.yml`:

~~~yaml
lesson:
  attributes:
    level: advanced
    stage: development
~~~

Tạo `@ConfigurationProperties(prefix="lesson")` với `Map<String,String> attributes`. Dự đoán các key và value khi `dev` hoạt động. Kết quả cần có `owner=platform`, `level=advanced`, `region=global` và `stage=development`.

### Bài tập B: CLI ghi đè đúng một entry

Giữ bài A và chạy thêm:

~~~bash
java -jar lesson.jar \
  --spring.profiles.active=dev \
  --lesson.attributes.level=expert
~~~

Dự đoán rằng `level=expert` thắng `advanced` từ profile file; các key khác vẫn có thể nhận từ các nguồn tương ứng.

### Bài tập C: Map value là object

Tạo `Map<String, Service>`, mỗi `Service` có `endpoint`, `timeout` và `enabled`. Default khai báo entry `primary` đầy đủ. Profile `prod` chỉ override `primary.timeout`, đồng thời thêm `analytics`. Kiểm tra `primary.endpoint` không bị mất.

### Bài tập D: So sánh List

Đổi mô hình ở bài C từ Map keyed theo tên thành `List<Service>`. Cho profile `prod` một list chỉ chứa một phần tử. Bind và quan sát vì sao phần tử trong List không được merge theo index giống Map value có key ổn định.

### Bài tập E: Key đặc biệt

Thử ba key trong YAML:

~~~yaml
lesson:
  routes:
    "[/v1/orders]": order-service
    "[/v1/products]": product-service
    "/legacy": legacy-service
~~~

Bind vào `Map<String,String> routes`. Quan sát key có slash và key bị chuẩn hóa khi không có bracket. Chỉnh lại key `/legacy` thành `"[/legacy]"` để giữ đúng ký tự.

### Bài tập F: Nhiều PropertySource

Dùng `MapPropertySource` và `Binder` như mục 20.2. Cấp `catalog.labels.region` ở cả hai nguồn, và các key khác ở mỗi nguồn. Kiểm tra precedence đổi kết quả `region` nhưng không loại bỏ `owner` và `stage`.

### Bài tập G: Kiểm tra tên key sai

Trong nguồn mặc định có `payments.providers.primary`. Nguồn production viết nhầm `payments.providers.primray.timeout`. Bind map và quan sát tạo entry mới hoặc cấu hình thiếu thay vì override entry cũ. Thêm validation cho tập provider keys được hỗ trợ để phát hiện lỗi.

### Bài tập H: Không dùng null để xóa key

Mặc định có `features.flags.legacy=true`. Trong nguồn JSON cao hơn dùng `legacy:null`. Kiểm tra kết quả; thay bằng `legacy:false` để diễn tả chính xác hành vi vô hiệu hóa feature.

## 22. Bảng quyết định nhanh

| Nhu cầu | Cấu trúc/cách làm phù hợp |
| --- | --- |
| Bổ sung key mới qua từng environment | `Map<String,String>` hoặc `Map<String, Config>` |
| Override một field của một backend có ID ổn định | `Map<String, Backend>` theo backend name |
| Danh sách phần tử có thứ tự nghiệp vụ | `List<T>`; khi override thường cấp lại toàn bộ list |
| Map key chứa slash | Bracket notation `[/path]` |
| Map key chứa dấu chấm và value phức tạp | Bracket notation `[tenant.a]` |
| Chọn nguồn thắng khi trùng field | Theo precedence của `Environment` |
| Muốn loại bỏ cấu hình cũ | Thiết kế cơ chế disable/remove rõ, không dựa vào sự vắng mặt ở nguồn cao |
| Xác thực entry bắt buộc | Bean Validation và test binding |
| Secret dưới dạng map | Nguồn secret an toàn, giới hạn log/Actuator |
| Đọc đầy đủ Map | `@ConfigurationProperties` hoặc `Binder` |
| Test hai nguồn có key trùng | Tạo property sources độc lập và kiểm tra precedence |

## 23. Những điều cần nhớ

1. **Map được kết hợp theo key** từ nhiều property sources. Key chỉ có ở một nguồn vẫn có thể góp mặt trong Map cuối cùng.
2. **Property trùng tên lấy giá trị từ nguồn có ưu tiên cao hơn.** Đây là precedence của `Environment`, không phải thứ tự lặp map.
3. Với `Map<String, ObjectType>`, các field của cùng một value object có thể đến từ nhiều nguồn: override một field không tự làm mất những field khác.
4. **List không merge như Map**: khi được cấu hình ở nhiều nguồn, list ưu tiên cao thường thay thế cả list ưu tiên thấp.
5. Tên map key cần được giữ đúng bằng bracket notation trong các trường hợp có dấu `/`, dấu chấm ở value type phức tạp hoặc ký tự đặc biệt. Environment variables còn có quy tắc lower-case map keys.
6. **Không khai báo entry ở nguồn cao không xóa entry ở nguồn thấp**; chuỗi rỗng và JSON null cũng không phải một ngữ nghĩa xóa thống nhất.
7. Map merging không thay thế validation, bảo vệ secret hoặc kiểm thử môi trường thật. Hãy kiểm tra prefix, nguồn ưu tiên, kiểu value và tên map key.
8. Khi code cần dùng Map đã kết hợp, ưu tiên `@ConfigurationProperties` thay vì tự đọc từng chuỗi rồi merge thủ công.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): các nguồn cấu hình, precedence, profile-specific files và import.
- [Spring Boot Reference — Merging Complex Types](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.merging-complex-types): quy tắc Map kết hợp entry và List thay thế.
- [Spring Boot Reference — Binding Maps](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps): bracket notation và tên key đặc biệt.
- [Spring Boot Reference — Binding From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables): cách chuyển tên biến và lower-case map keys.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): typed binding, JavaBean, constructor và validation.
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): nhập file cấu hình và thứ tự ưu tiên.
