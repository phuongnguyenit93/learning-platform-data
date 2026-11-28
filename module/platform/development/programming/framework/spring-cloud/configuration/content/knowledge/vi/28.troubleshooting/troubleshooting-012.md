# Thu thập nguồn gốc thuộc tính và khoanh vùng từng chặng

## 1. Vì sao phải truy vết một property qua nhiều chặng?

Trong hệ thống Spring Cloud Config, một giá trị cấu hình không đi thẳng từ Git vào bean. Nó đi qua nhiều bước: Git backend, Config Server `EnvironmentRepository`, HTTP response, Config Client `Environment`, các `PropertySource`, Binder và cuối cùng là bean hoặc thành phần runtime sử dụng giá trị.

Khi một ứng dụng dùng timeout `8s` trong khi nhóm vận hành mong đợi `3s`, chỉ nhìn file Git hoặc chỉ nhìn bean đều chưa đủ. Có thể:

- Config Server đang đọc branch/label khác.
- File theo application/profile ghi đè file chung.
- Config Client gọi sai application name hoặc profile.
- Environment variable, JVM system property hoặc command-line argument ghi đè remote property.
- Placeholder `${...}` tham chiếu đến một property khác.
- Binder chuyển kiểu, áp dụng default hoặc bind vào prefix khác.
- Bean đã được tạo trước lần refresh và vẫn giữ giá trị cũ.

Mục tiêu của bài là lần theo **nguồn gốc của một khóa cụ thể**, xác định nó đổi giá trị ở chặng nào và thu thập bằng chứng đủ để sửa đúng nguyên nhân.

## 2. Bản đồ đường đi của cấu hình

Một request cấu hình qua Spring Cloud Config có thể được mô tả như sau:

```mermaid
flowchart LR
    G[(Git repository)] -->|branch / tag / commit| R[EnvironmentRepository]
    R --> S[Config Server Environment]
    S -->|GET /application/profile/label| H[HTTP response]
    H --> C[Config Client Config Data]
    C --> E[Spring Environment]
    E --> B[Binder / @Value]
    B --> P[@ConfigurationProperties bean]
    P --> U[Code sử dụng giá trị]
    L[Local files / env / JVM / CLI] --> E
    X[Defaults / placeholders / custom sources] --> E
```

Mỗi chặng trả lời một câu hỏi khác nhau:

| Chặng | Câu hỏi cần trả lời | Bằng chứng nên thu thập |
|---|---|---|
| Git | File nào chứa khóa, commit nào đang được dùng? | Repository, path, branch/tag, commit SHA, nội dung khóa không nhạy cảm. |
| Config Server | Server chọn repository và property source nào? | Application/profile/label request, `version`, tên property source, giá trị trong từng source. |
| HTTP | Server trả response nào cho client? | Status, metadata, `propertySources`, response revision. |
| Config Client | Client đã import response nào và đang active profile nào? | Config import, `spring.application.name`, profiles, label, Environment. |
| Environment | Source nào thắng khi nhiều source có cùng key? | `/actuator/env/{property}` và thứ tự `propertySources`. |
| Binder | Giá trị nào đã bind vào object? | `/actuator/configprops`, prefix, inputs/origin, kiểu dữ liệu. |
| Runtime | Bean đang dùng giá trị nào ngay lúc này? | Giá trị quan sát được trong bean, lifecycle, lần refresh gần nhất. |

Không nên nhảy thẳng từ “Git có giá trị đúng” đến “ứng dụng phải dùng giá trị đó”. Một giá trị có thể bị thay đổi ở bất kỳ chặng nào phía sau.

## 3. Phân biệt ba khái niệm: property source, origin và giá trị hiệu lực

Ba khái niệm này thường bị nhầm lẫn:

1. **Property source** là nguồn cung cấp một hoặc nhiều thuộc tính, ví dụ `systemEnvironment`, `systemProperties`, file `application-prod.yml` hoặc remote Config Server property source.
2. **Origin** là thông tin mô tả vị trí xuất phát của một giá trị, nếu nguồn có cung cấp, ví dụ tên file và số dòng hoặc biến môi trường.
3. **Giá trị hiệu lực** là kết quả Spring `Environment` trả về sau khi áp dụng thứ tự ưu tiên, placeholder và quy tắc phân giải.

Ví dụ, cùng một khóa có thể xuất hiện ở ba nơi:

| Property source | Khóa | Giá trị |
|---|---|---:|
| Config Server remote `catalog-service-prod.yml` | `catalog.http.read-timeout` | `8s` |
| `systemEnvironment` | `CATALOG_HTTP_READTIMEOUT` | `3s` |
| `commandLineArgs` | `--catalog.http.read-timeout=2s` | `2s` |

Trong ví dụ này, property source có độ ưu tiên cao nhất trong Environment quyết định giá trị mà `Environment.getProperty("catalog.http.read-timeout")` trả về. Chỉ biết file Git chứa `8s` không có nghĩa bean sẽ nhận `8s`.

Origin cũng không phải lúc nào cũng chỉ ra commit hoặc dòng Git. Với file local, origin có thể là đường dẫn file và số dòng. Với environment variable, origin có thể là tên biến. Với custom `PropertySource` hoặc một số nguồn remote, origin có thể không có hoặc chỉ có tên nguồn tổng quát.

## 4. Bắt đầu bằng một khóa cụ thể và tên chuẩn của nó

Khi điều tra, chọn một property cụ thể thay vì dump toàn bộ cấu hình. Ví dụ:

```text
catalog.http.read-timeout
```

Ghi lại:

- Tên canonical mà code đang đọc.
- Giá trị mong đợi và đơn vị.
- Giá trị thực tế quan sát được.
- Bean/prefix đang sử dụng property.
- Ứng dụng, profile, label và môi trường triển khai.
- Instance/pod và thời điểm quan sát.

Spring hỗ trợ relaxed binding cho nhiều cách viết tên thuộc tính. Ví dụ các dạng sau có thể ánh xạ đến cùng một property trong những ngữ cảnh phù hợp:

```text
catalog.http.read-timeout
catalog.http.readTimeout
CATALOG_HTTP_READTIMEOUT
```

Đối với environment variables, quy tắc phổ biến của Spring Boot là thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch ngang và chuyển thành chữ hoa. Do đó `catalog.http.read-timeout` thường được cung cấp qua `CATALOG_HTTP_READTIMEOUT`.

Khi truy vết, luôn dùng tên canonical trong câu hỏi `/actuator/env/{property.name}` và đối chiếu cả tên biến môi trường thực tế. Tránh tự chuyển đổi bằng cách đoán nếu tên có map key, list index hoặc ký tự đặc biệt.

## 5. Xác minh Config Server nhận đúng application, profile và label

Config Server Environment endpoint có dạng:

```text
GET /{application}/{profile}/{label}
```

Ba tham số có ý nghĩa riêng:

- `application`: thường ánh xạ từ `spring.application.name` của client.
- `profile`: profile active mà client yêu cầu.
- `label`: branch, tag hoặc commit mà Config Server dùng để đọc cấu hình Git.

Ví dụ:

```bash
curl --fail-with-body \
  --header "Accept: application/json" \
  "${CONFIG_SERVER_URL}/catalog-service/prod/release-2026-11"
```

Kiểm tra metadata trong response:

```json
{
  "name": "catalog-service",
  "profiles": ["prod"],
  "label": "release-2026-11",
  "version": "8b4c1f2...",
  "propertySources": []
}
```

Đây là response rút gọn để minh họa. Tên field và dữ liệu cụ thể cần được xác nhận theo phiên bản đang chạy.

Nếu `name`, `profiles` hoặc `label` không đúng, dừng việc điều tra precedence ở client cho đến khi request đúng. Không thể giải thích một giá trị remote sai bằng cách kiểm tra Environment của một application/profile/label khác.

## 6. Kiểm tra file nào đã đóng góp property source trên Config Server

Với Git backend, Config Server thường nạp các file chung `application*` cùng file theo tên application. File theo application có thể ghi đè file chung; file profile-specific có ưu tiên cao hơn file mặc định. Khi có nhiều profile active, profile cuối cùng trong danh sách có ưu tiên cao hơn profile đứng trước.

Ví dụ repository:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── catalog-service.yml
└── catalog-service-prod.yml
```

Với request `catalog-service/prod/release-2026-11`, một property có thể xuất hiện ở nhiều file:

| File | Giá trị `catalog.http.read-timeout` |
|---|---:|
| `application.yml` | `12s` |
| `application-prod.yml` | `10s` |
| `catalog-service.yml` | `8s` |
| `catalog-service-prod.yml` | `6s` |

Trong ví dụ file-based repository một search location, source profile-specific của application thường có ưu tiên cao hơn source profile-specific chung, sau đó đến file mặc định theo application và file mặc định chung. Response Environment của server liệt kê property sources theo thứ tự ưu tiên; source đứng trước có độ ưu tiên cao hơn.

Không tự suy ra thứ tự khi dùng `search-paths`, composite repository, nhiều repository hoặc custom `EnvironmentRepository`. Hãy đọc chính response của server và kiểm tra tên source cùng giá trị trong từng source.

## 7. Kiểm tra thứ tự propertySources trong response Config Server

Ví dụ một phần response:

```json
{
  "propertySources": [
    {
      "name": ".../catalog-service-prod.yml",
      "source": {
        "catalog.http.read-timeout": "6s"
      }
    },
    {
      "name": ".../catalog-service.yml",
      "source": {
        "catalog.http.read-timeout": "8s"
      }
    },
    {
      "name": ".../application-prod.yml",
      "source": {
        "catalog.http.read-timeout": "10s"
      }
    },
    {
      "name": ".../application.yml",
      "source": {
        "catalog.http.read-timeout": "12s"
      }
    }
  ]
}
```

Trong response này, giá trị remote hiệu lực là `6s` vì property source đầu tiên chứa khóa đó có độ ưu tiên cao nhất. Những giá trị ở source thấp hơn vẫn được giữ trong response để phục vụ việc kế thừa và chẩn đoán.

Nếu Config Server response đã chứa giá trị không đúng, lỗi nằm ở phía server/repository selection hoặc nội dung cấu hình. Chưa cần kiểm tra environment variable của client ở bước này.

## 8. Hiểu precedence tại hai tầng khác nhau

Có hai lần áp dụng precedence:

### Tầng Config Server

Server kết hợp các file từ `EnvironmentRepository`, profile, application, label, search path và có thể cả composite repository. Kết quả là Environment response với nhiều property source.

### Tầng Config Client

Client đưa remote property sources vào Spring Boot `Environment` cùng các nguồn khác như local config data, OS environment variables, JVM system properties, JSON properties và command-line arguments.

Hai tầng không phải một danh sách duy nhất. Một khóa có thể thắng ở tầng Config Server nhưng vẫn bị ghi đè ở tầng client.

Spring Boot có thứ tự nguồn cấu hình xác định. Trong đó command-line arguments, JSON properties, system properties và OS environment variables có thể ghi đè các giá trị file config data theo thứ tự của phiên bản. Vị trí remote config data trong quá trình Config Data import còn phụ thuộc import location và cách ứng dụng nạp cấu hình.

Vì thứ tự thực tế chịu ảnh hưởng của phiên bản Spring Boot, Spring Cloud Config, Config Data import và cấu hình bootstrap legacy, hãy dùng `/actuator/env` của chính client để xác nhận thứ tự cuối cùng thay vì chỉ dựa vào một bảng tổng quát.

## 9. Các nguồn local thường ghi đè remote configuration

Khi remote response đúng nhưng client nhận giá trị khác, kiểm tra lần lượt:

| Nguồn | Ví dụ | Cách kiểm tra |
|---|---|---|
| Environment variable | `CATALOG_HTTP_READTIMEOUT=3s` | Kiểm tra container/pod environment và `/actuator/env`. |
| JVM system property | `-Dcatalog.http.read-timeout=2s` | Kiểm tra JVM args và `systemProperties` source. |
| Command-line argument | `--catalog.http.read-timeout=1s` | Kiểm tra entrypoint, deployment args và `commandLineArgs`. |
| `SPRING_APPLICATION_JSON` | JSON chứa `catalog.http.read-timeout` | Kiểm tra env/launcher/secret injection. |
| File local ngoài JAR | `./config/application-prod.yml` | Kiểm tra working directory và Config Data locations. |
| File trong JAR | `application.yml` | Kiểm tra artifact đang chạy và nội dung build. |
| Test properties | `@SpringBootTest(properties=...)` | Kiểm tra test context, không nhầm với production. |
| Custom PropertySource | `@PropertySource`, custom initializer hoặc framework integration | Kiểm tra source name và code khởi tạo Environment. |

Trong Kubernetes, một biến môi trường có thể đến từ `env`, `envFrom`, ConfigMap, Secret hoặc Downward API. Kiểm tra manifest/Pod spec và giá trị đã được inject vào đúng Pod; ConfigMap được sửa không nhất thiết làm environment variable của Pod đang chạy tự thay đổi.

## 10. Kiểm tra `spring.config.import` và profile activation

Với Config Data, client thường khai báo:

```yaml
spring:
  config:
    import: "configserver:https://config.internal"
```

Nếu import không có prefix `optional:`, client fail khi không thể kết nối Config Server. Nếu dùng `optional:configserver:`, ứng dụng có thể tiếp tục với các nguồn khác khi remote config không sẵn sàng.

Config Data xử lý profile theo nhiều pha. Spring Boot có thể gọi Config Server lần đầu với profile `default`, sau đó gọi lại khi profile active được xác định. Vì vậy nhiều request trong lúc startup không nhất thiết là lỗi hoặc request trùng.

Khi điều tra:

1. Xác định import nằm trong file nào và có bị khai báo nhiều lần không.
2. Kiểm tra URL trong import và `spring.cloud.config.uri`; URL trong import có thể có precedence riêng.
3. Kiểm tra `spring.application.name`, `spring.cloud.config.name`, `spring.cloud.config.profile` và `spring.cloud.config.label`.
4. Kiểm tra `spring.profiles.active`, `spring.profiles.default` và profile được kích hoạt từ remote config.
5. Đối chiếu request log ở Config Server với profile/label thực tế.

Với bootstrap legacy, kiểm tra `bootstrap.yml`, `spring.cloud.bootstrap.enabled` và các thuộc tính `spring.cloud.config.*` tương ứng. Không áp dụng giả định Config Data vào ứng dụng vẫn dùng bootstrap context cũ.

## 11. Dùng `/actuator/env` để tìm source thắng

Spring Boot Actuator `env` endpoint hiển thị Spring `Environment`, danh sách active/default profiles và property sources theo thứ tự ưu tiên. Đây thường là điểm bắt đầu tốt nhất khi một property có giá trị không mong đợi.

Ví dụ chỉ kiểm tra một property:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${ACTUATOR_TOKEN}" \
  "${APP_MANAGEMENT_URL}/actuator/env/catalog.http.read-timeout"
```

Response của một property có thể gồm:

```json
{
  "activeProfiles": ["prod"],
  "defaultProfiles": ["default"],
  "property": {
    "source": "systemEnvironment",
    "value": "3s"
  },
  "propertySources": [
    {
      "name": "systemEnvironment",
      "property": {
        "value": "3s",
        "origin": "System Environment Property \"CATALOG_HTTP_READTIMEOUT\""
      }
    },
    {
      "name": "configserver:...",
      "property": {
        "value": "6s",
        "origin": "..."
      }
    }
  ]
}
```

Response là ví dụ rút gọn; origin và tên source phụ thuộc loại `PropertySource`, phiên bản và khả năng cung cấp origin của nguồn đó.

Đọc kết quả theo thứ tự:

1. `activeProfiles` xác nhận profile ứng dụng đang dùng.
2. `property.source` chỉ ra nguồn được chọn cho property.
3. `property.value` cho biết giá trị hiện hành sau khi Environment resolve.
4. `propertySources` cho biết các nguồn đã được xem xét theo thứ tự ưu tiên.
5. `origin` có thể chỉ ra file/dòng, biến môi trường hoặc vị trí nguồn nếu nguồn hỗ trợ.

Nếu source đầu tiên chứa property là `systemEnvironment`, hãy kiểm tra biến môi trường trước khi sửa Git. Nếu source đầu tiên là remote Config Server, quay lại server API và kiểm tra profile/label/file source.

## 12. Dùng `/actuator/env` toàn bộ khi cần xem cấu trúc nguồn

Có thể gọi:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${ACTUATOR_TOKEN}" \
  "${APP_MANAGEMENT_URL}/actuator/env"
```

Endpoint này hữu ích để xác định có những property source nào, nhưng response có thể rất lớn và chứa tên biến, đường dẫn file, thông tin nội bộ hoặc property nhạy cảm. Trong điều tra thông thường, nên bắt đầu với `/actuator/env/{property.name}` để thu hẹp phạm vi.

Nếu cần trích riêng tên source và origin bằng `jq`, có thể lọc response của một property:

```bash
curl --silent --show-error \
  --header "Authorization: Bearer ${ACTUATOR_TOKEN}" \
  "${APP_MANAGEMENT_URL}/actuator/env/catalog.http.read-timeout" \
  | jq '{activeProfiles, property, propertySources}'
```

Không lưu response thô vào ticket hoặc artifact công khai. Chỉ chia sẻ tên property không nhạy cảm, source name, origin và giá trị đã được phê duyệt.

## 13. Dùng `/actuator/configprops` để xác nhận Binder đã nhận gì

`env` trả lời câu hỏi “Environment đang có giá trị nào và nguồn nào cung cấp nó?”. `configprops` trả lời câu hỏi “Bean `@ConfigurationProperties` đã được bind thành giá trị nào?”.

Ví dụ:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${ACTUATOR_TOKEN}" \
  "${APP_MANAGEMENT_URL}/actuator/configprops/catalog"
```

Tùy phiên bản, endpoint có thể hỗ trợ lấy toàn bộ bean ở `/actuator/configprops` hoặc lọc theo prefix. Response gồm các context, bean, prefix, `properties` đã bind và `inputs` mô tả origin/value đầu vào cho từng thuộc tính nếu có.

Ví dụ cấu trúc:

```json
{
  "contexts": {
    "application": {
      "beans": {
        "catalog-com.example.CatalogProperties": {
          "prefix": "catalog",
          "properties": {
            "http": {
              "readTimeout": "PT3S"
            }
          },
          "inputs": {
            "http": {
              "readTimeout": {
                "origin": "System Environment Property ...",
                "value": "3s"
              }
            }
          }
        }
      }
    }
  }
}
```

Response minh họa đã rút gọn. Hình dạng JSON cụ thể có thể khác giữa các phiên bản Spring Boot.

Đối chiếu `env` và `configprops`:

- Nếu `env` đã sai, điều tra nguồn và precedence.
- Nếu `env` đúng nhưng `configprops` sai/thiếu, kiểm tra prefix, Binder, kiểu dữ liệu, cấu trúc nested object và validation.
- Nếu cả hai đúng nhưng code vẫn dùng giá trị cũ, kiểm tra bean lifecycle, nơi lưu cache hoặc refresh.

## 14. Kiểm tra prefix và cấu trúc `@ConfigurationProperties`

Ví dụ bean:

```java
@Validated
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(
        @NotNull Duration requestTimeout,
        HttpProperties http) {

    public record HttpProperties(Duration readTimeout) {
    }
}
```

Các key tương ứng có thể là:

```yaml
catalog:
  request-timeout: 4s
  http:
    read-timeout: 3s
```

Nếu code bind prefix `catalog` nhưng file lại đặt `catalog-service.http.read-timeout`, Binder không tự suy ra hai prefix đó là tương đương. Kiểm tra chính xác:

- `@ConfigurationProperties(prefix = ...)`.
- Bean có được đăng ký qua scan hoặc `@EnableConfigurationProperties` không.
- Tên field/record component có khớp cấu trúc property không.
- Có nested object, map, list hoặc collection không.
- Có getter/setter/constructor binding phù hợp với kiểu bean không.
- Có default value trong constructor hoặc code khởi tạo không.

Đừng sửa key trong Git khi lỗi thực chất là bean đang bind một prefix khác.

## 15. Phân biệt giá trị Environment với giá trị đã convert

Environment thường giữ giá trị nguồn dưới dạng chuỗi hoặc object do nguồn cung cấp. Binder có thể chuyển giá trị sang kiểu Java.

Ví dụ:

```yaml
catalog:
  http:
    read-timeout: 3s
  max-response-size: 4MB
```

Kết quả bind có thể là:

```java
Duration readTimeout; // PT3S
DataSize maxResponseSize; // đã được chuyển thành số byte theo quy tắc DataSize
```

Vì vậy chuỗi trong `/actuator/env` và biểu diễn trong `/actuator/configprops` có thể khác nhau mà không phải lỗi precedence. So sánh cùng một đơn vị và cùng kiểu trước khi kết luận giá trị sai.

Kiểm tra thêm:

- Unit suffix hợp lệ theo kiểu property, ví dụ `ms`, `s`, `m` với `Duration` và `B`, `KB`, `MB`, `GB`, `TB` với `DataSize`.
- Enum name và case.
- Boolean parsing.
- Number format và overflow.
- Converter tùy chỉnh.
- Default value trong code.
- Validation annotation như `@Min`, `@NotNull` hoặc validator tùy chỉnh phù hợp với kiểu dữ liệu.

## 16. Placeholder có thể làm nguồn gốc gián tiếp

Một property có thể tham chiếu đến property khác:

```yaml
catalog:
  endpoint: "https://${catalog.host}:${catalog.port}"
  host: catalog.internal
  port: 8443
```

Giá trị cuối của `catalog.endpoint` phụ thuộc vào `catalog.host` và `catalog.port`. Nếu endpoint không đúng, truy vết cả property gốc lẫn property được tham chiếu.

Ví dụ remote source có:

```yaml
catalog:
  endpoint: "${CATALOG_ENDPOINT:https://catalog.default.internal}"
```

Kết quả phụ thuộc vào `CATALOG_ENDPOINT` có tồn tại trong Environment hay không. Nếu biến này được inject từ container, nguồn cuối có thể không nằm trong Git.

Quy trình:

1. Xác định property cuối đang được dùng.
2. Kiểm tra source/origin của property đó.
3. Nếu giá trị chứa `${...}`, xác định tên property được tham chiếu và default.
4. Truy vết property tham chiếu qua `/actuator/env/{name}`.
5. Xác nhận giá trị cuối sau placeholder resolution.

Không giả định origin của property cuối luôn chỉ đến nơi chứa placeholder. Nguồn của giá trị được tham chiếu có thể nằm ở một property source khác.

## 17. Kiểm tra server-side overrides và client override policy

Spring Cloud Config có một số cơ chế liên quan đến override, cần phân biệt:

### Config Server `overrides`

Operator có thể khai báo các property áp dụng chung trong:

```yaml
spring:
  cloud:
    config:
      server:
        overrides:
          platform.support-contact: platform-ops@example.internal
```

Đây là property source do Config Server thêm vào response cho client. Khi thấy một giá trị xuất hiện từ server dù không có trong Git file, kiểm tra cấu hình runtime của chính Config Server và property source tương ứng.

### Client `overrideNone`

Spring Cloud Config có thuộc tính `spring.cloud.config.overrideNone` để điều chỉnh các server overrides theo hướng giống default values hơn, cho phép giá trị phía ứng dụng như environment/system properties ghi đè trong trường hợp được hỗ trợ.

### Legacy bootstrap `allowOverride`

Trong cơ chế bootstrap legacy, remote property source có thể điều khiển khả năng client override qua các thuộc tính như `spring.cloud.config.allowOverride`, `spring.cloud.config.overrideNone` và `spring.cloud.config.overrideSystemProperties`. Những thuộc tính này cần được đặt ở remote environment theo đúng quy tắc bootstrap.

Không trộn các thuộc tính legacy với Config Data import mà không kiểm tra phiên bản và tài liệu tương ứng. Khi chưa chắc, xem thứ tự `PropertySource` cuối cùng trong `/actuator/env` và response của Config Server.

## 18. Composite repository và thứ tự backend

Nếu Config Server dùng composite repository, một property có thể xuất hiện trong nhiều backend như Git, Vault, JDBC hoặc native. Thứ tự composite repository ảnh hưởng đến thứ tự property source và nguồn nào thắng.

Khi điều tra:

- Xác định Config Server đang dùng một repository hay composite repository.
- Kiểm tra thứ tự khai báo backend.
- Kiểm tra `order` hoặc `Ordered` nếu custom repository có thứ tự riêng.
- Xem response `propertySources` để nhận biết backend/source name.
- Đối chiếu cùng một property trong từng backend.

Không giả định Git luôn có ưu tiên cao nhất chỉ vì Git là nguồn cấu hình chính của tổ chức. Trong composite repository, thứ tự là một phần của thiết kế và phải được xác minh từ cấu hình server cùng response thực tế.

## 19. Kiểm tra label và revision drift giữa các instance

Nếu hai Pod trả giá trị khác nhau, có thể chúng đang dùng các revision khác nhau dù cùng application/profile.

Kiểm tra:

- `spring.cloud.config.label` hoặc label trong Config Data import.
- Commit SHA/revision từ Config Server Environment response.
- Config Server instance nào đã trả request.
- Git fetch/cache/refresh-rate ở từng Config Server instance.
- Thời điểm client bootstrap và lần refresh gần nhất.
- Có instance nào đang giữ Environment cũ sau khi repository đã đổi không.

Nên gắn metadata application, profile, label, revision và instance ID vào log/diagnostic info ở dạng không nhạy cảm. Khi so sánh hai instance, phải so sánh cùng một thời điểm hoặc ghi rõ timestamp.

## 20. Environment đúng nhưng bean runtime vẫn sai

Khi `/actuator/env` cho giá trị đúng và `/actuator/configprops` cũng cho giá trị đúng, nhưng endpoint nghiệp vụ vẫn dùng giá trị cũ, chuyển sang kiểm tra runtime:

- Bean có được tạo trước lần refresh gần nhất không?
- Bean có phải singleton giữ field đã copy giá trị từ `Environment` lúc khởi tạo không?
- Bean có `@RefreshScope` hoặc cơ chế rebind phù hợp không?
- Có cache nội bộ hoặc client object được tạo từ giá trị cũ không?
- Có nhiều application context hoặc child context không?
- Có code nào tự gán lại field sau binding không?
- Refresh event có đến đúng instance không?
- Lỗi tạo lại bean có xuất hiện trong log không?

`Environment` thay đổi không tự động bảo đảm mọi object Java đã được tạo trước đó đều thay đổi. Cần kiểm tra lifecycle và cách bean nhận cấu hình.

## 21. Bật logging có mục tiêu khi cần biết file nào được nạp

Khi cần xác minh Config Data locations và profile-specific files, có thể tăng log cho package xử lý Config Data trong môi trường kiểm soát:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
```

Log này giúp nhận biết file/location nào được xét và nạp trong startup. Nó không thay thế `/actuator/env` để xác định source cuối cùng thắng.

Với Config Client, có thể bật log phù hợp cho package `org.springframework.cloud.config` trong thời gian ngắn để xem request/config fetch. Với Config Server, xem log `EnvironmentRepository`/Git backend để xác định application, profile, label, repository và revision.

Không bật HTTP wire logging hoặc log toàn bộ Environment trong production nếu có nguy cơ ghi token, password, private key hoặc ciphertext/plaintext nhạy cảm. Sau khi điều tra, đưa log level về mức vận hành bình thường.

## 22. Bảo vệ Actuator trong khi truy vết

`/actuator/env` và `/actuator/configprops` rất hữu ích nhưng có thể tiết lộ thông tin nhạy cảm. Spring Boot hiện hành sanitize các giá trị của hai endpoint theo mặc định. Nếu thay đổi `show-values`, hãy giới hạn cho người đã xác thực và có role phù hợp.

Ví dụ chỉ expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,env,configprops
  endpoint:
    env:
      show-values: when-authorized
      roles: config-debug
    configprops:
      show-values: when-authorized
      roles: config-debug
```

Đây là cấu hình cho môi trường quản trị được bảo vệ. Cần cấu hình Spring Security để role `config-debug` chỉ được cấp cho nhóm vận hành có thẩm quyền. Có thể dùng management network riêng, mTLS, VPN hoặc network policy.

Không bật `show-values: always` trên endpoint công khai. Khi chỉ cần biết nguồn gốc, nhiều trường hợp tên source và origin đã đủ mà không cần lộ giá trị. Sau khi hoàn tất điều tra, thu hồi quyền truy cập tạm thời nếu đã cấp.

## 23. Quy trình khoanh vùng từng chặng

Khi nhận báo cáo “property X có giá trị sai”, thực hiện theo trình tự:

1. **Chuẩn hóa câu hỏi**: ghi canonical property name, expected value, actual value, application, profile, label, instance và timestamp.
2. **Kiểm tra client metadata**: xác nhận `spring.application.name`, active profiles, label và Config Data import.
3. **Gọi Config Server trực tiếp**: dùng đúng application/profile/label của instance và kiểm tra `version` cùng `propertySources`.
4. **Xác định server-side winner**: tìm source đầu tiên chứa khóa trong response; kiểm tra Git file, composite repository và server overrides.
5. **Kiểm tra client Environment**: gọi `/actuator/env/{property.name}` để xem giá trị cuối, source và origin.
6. **So sánh với remote response**: nếu khác, tìm property source local hoặc nguồn runtime có độ ưu tiên cao hơn.
7. **Kiểm tra Binder**: dùng `/actuator/configprops/{prefix}` hoặc bean tương ứng để kiểm tra prefix, inputs và giá trị đã bind.
8. **Kiểm tra conversion/default**: xem đơn vị, kiểu dữ liệu, placeholder, constructor default và validation.
9. **Kiểm tra bean runtime**: xác định bean có được refresh/recreate hoặc có cache giữ giá trị cũ không.
10. **So sánh các instance**: đối chiếu label/revision, lần refresh và source winner trên từng Pod.
11. **Ghi nhận nguyên nhân và sửa đúng chặng**: chỉ thay file, environment, import hoặc bean sau khi đã có bằng chứng.
12. **Xác minh sau sửa**: gọi lại server API, client env, configprops và endpoint nghiệp vụ.

## 24. Ví dụ hoàn chỉnh: Git đúng nhưng environment variable thắng

### Tình huống

Nhóm vận hành đặt trong Git:

```yaml
catalog:
  http:
    read-timeout: 6s
```

Config Server endpoint `GET /catalog-service/prod/release-2026-11` trả đúng `6s`. Nhưng `/actuator/env/catalog.http.read-timeout` của Pod lại cho biết source là `systemEnvironment` và giá trị `3s`.

### Điều tra

1. Config Server response đúng application, profile, label và commit SHA.
2. Property source remote chứa `6s`.
3. Client Environment có `systemEnvironment` đứng trước remote source và cung cấp `CATALOG_HTTP_READTIMEOUT=3s`.
4. `/actuator/configprops/catalog` cho thấy bean đã bind `PT3S`.
5. Pod spec cho thấy biến được inject từ ConfigMap cũ.

### Kết luận

Config Server và Git không có lỗi. Environment variable của workload đang ghi đè remote property. Sửa nguồn inject ở deployment/ConfigMap theo quy trình rollout; sau khi Pod nhận biến mới hoặc bỏ biến đó, kiểm tra lại `env`, `configprops` và hành vi runtime.

## 25. Bảng triệu chứng và chặng cần kiểm tra

| Triệu chứng | Chặng nghi ngờ | Bằng chứng đầu tiên |
|---|---|---|
| Config Server trả giá trị sai | Git/repository selection/server precedence | Endpoint `/{application}/{profile}/{label}`, `version`, propertySources. |
| Config Server đúng nhưng client env sai | Config Client import hoặc local override | `/actuator/env/{property}` và source đứng đầu. |
| Chỉ một Pod có giá trị khác | Runtime environment/label drift | Pod env, command args, revision và timestamp. |
| `env` đúng nhưng `configprops` sai | Binder/prefix/conversion | `/actuator/configprops/{prefix}`, class binding và validation. |
| `env` và `configprops` đúng nhưng nghiệp vụ sai | Bean lifecycle/cache/runtime mutation | Bean instance, refresh log, cache và code sử dụng. |
| Profile không như mong đợi | Profile activation/import | `activeProfiles`, `spring.profiles.active`, Config Server request. |
| Giá trị khác sau deploy | Artifact/local config/environment | JAR contents, external config locations, Pod spec. |
| Giá trị đổi ở một số instance | Refresh/Bus/revision drift | Event delivery, refresh timestamp và revision từng instance. |
| Source name đúng nhưng không có origin | Source không cung cấp origin metadata | Kiểm tra backend/file và log nạp cấu hình; không coi thiếu origin là thiếu property. |
| Giá trị bị che thành `******` | Actuator sanitization | Kiểm tra role/show-values theo policy, không tắt sanitize công khai. |

## 26. Checklist thu thập bằng chứng

- [ ] Canonical property name và prefix bean đã được ghi nhận.
- [ ] Expected value, actual value, đơn vị và thời điểm quan sát đã rõ.
- [ ] Application name, active profile, label và revision đã được xác minh.
- [ ] Config Server API đã được gọi với đúng tham số.
- [ ] Tên và thứ tự property source ở server đã được kiểm tra.
- [ ] `spring.cloud.config.server.overrides` và composite repository đã được xem xét.
- [ ] `/actuator/env/{property}` đã xác định source winner và origin nếu có.
- [ ] Environment variables, JVM properties, JSON properties và command-line args đã được kiểm tra.
- [ ] `spring.config.import`, local config locations và profile activation đã được xác nhận.
- [ ] `/actuator/configprops` đã được dùng để kiểm tra binding khi cần.
- [ ] Placeholder, type conversion, default và validation đã được kiểm tra.
- [ ] Bean lifecycle, refresh và cache đã được kiểm tra nếu runtime còn sai.
- [ ] Các instance đã được so sánh theo revision và timestamp.
- [ ] Token, password và property nhạy cảm không xuất hiện trong ticket/log/artifact.

## 27. Bài thực hành

### Bước 1: Tạo nhiều nguồn cùng khai báo một property

Đặt `catalog.http.read-timeout` lần lượt trong `application.yml`, `application-prod.yml`, `catalog-service.yml` và `catalog-service-prod.yml` với các giá trị khác nhau.

**Kết quả cần đạt:** gọi Config Server Environment endpoint và xác định source có độ ưu tiên cao nhất.

### Bước 2: Ghim application/profile/label

Gọi endpoint với application `catalog-service`, profile `prod`, label là tag test bất biến. Ghi nhận `name`, `profiles`, `label`, `version` và propertySources.

**Kết quả cần đạt:** xác nhận server đọc đúng revision.

### Bước 3: Tạo override ở client

Inject `CATALOG_HTTP_READTIMEOUT=3s` vào ứng dụng trong khi remote property là `6s`. Gọi `/actuator/env/catalog.http.read-timeout`.

**Kết quả cần đạt:** nhận biết environment variable là source thắng và origin chỉ ra tên biến nếu được hỗ trợ.

### Bước 4: Kiểm tra Binder

Bind property vào `@ConfigurationProperties` có kiểu `Duration`. Gọi `/actuator/configprops/catalog` và so sánh chuỗi Environment với giá trị đã convert.

**Kết quả cần đạt:** phân biệt giá trị nguồn `3s` với biểu diễn `PT3S` trong bean.

### Bước 5: Kiểm tra placeholder

Đổi `catalog.endpoint` thành `${catalog.host}:${catalog.port}` và inject `catalog.port` từ môi trường. Truy vết cả ba property.

**Kết quả cần đạt:** xác định nguồn của giá trị cuối có thể nằm ở nhiều property source.

### Bước 6: Mô phỏng refresh không đồng nhất

Thay đổi remote value, refresh một instance và giữ instance khác chưa refresh. So sánh Environment, configprops, revision và bean runtime.

**Kết quả cần đạt:** nhận biết Environment source, binding và runtime bean có thể chưa đồng bộ.

### Bước 7: Bảo vệ Actuator

Chỉ expose `health`, `env`, `configprops` trên management interface lab. Bật sanitization mặc định hoặc `when-authorized`, rồi thử truy cập bằng danh tính không có role.

**Kết quả cần đạt:** truy vết được nguồn mà không mở rộng quyền đọc cấu hình nhạy cảm.

## 28. Tự kiểm tra

1. Property source, origin và effective value khác nhau như thế nào?
2. Vì sao Git có giá trị đúng nhưng Config Client vẫn nhận giá trị khác?
3. Config Server Environment endpoint được tham số hóa bởi những giá trị nào?
4. Trong file-based Git repository, file application/profile-specific có quan hệ precedence ra sao?
5. Vì sao phải kiểm tra `version` và label khi so sánh hai instance?
6. Config Server precedence và Config Client precedence khác nhau ở điểm nào?
7. `/actuator/env/{property.name}` giúp xác định điều gì?
8. Origin metadata có luôn chứa Git commit và line number không?
9. `/actuator/configprops` bổ sung thông tin gì so với `/actuator/env`?
10. Vì sao chuỗi `3s` có thể hiển thị thành `PT3S` sau binding?
11. Placeholder `${...}` khiến việc truy vết cần mở rộng như thế nào?
12. `spring.cloud.config.server.overrides` khác local environment override ra sao?
13. Khi nào cần kiểm tra composite repository order?
14. Vì sao Environment đúng chưa chắc bean runtime đã dùng giá trị mới?
15. Làm thế nào truy vết một property mà không expose secret qua Actuator?

Khi hoàn thành bài thực hành, người học có thể lần theo một property từ Git qua Config Server và Config Client đến bean runtime, xác định source/origin/precedence ở từng chặng, phân biệt lỗi nạp cấu hình với lỗi binding hoặc refresh, và ghi nhận bằng chứng đủ để sửa đúng nguyên nhân.

## Tài liệu tham khảo

- [Spring Cloud Config – Environment Repository](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository.html): application/profile/label, property sources và precedence của file chung/profile-specific.
- [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, application/profile/label và các pha nạp profile.
- [Spring Cloud Config – Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html): server-side overrides và `overrideNone`.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, Config Data, environment variables, system properties và command-line arguments.
- [Spring Boot Actuator – Environment API](https://docs.spring.io/spring-boot/api/rest/actuator/env.html): active/default profiles, property sources, property origin và truy vấn một property.
- [Spring Boot Actuator – Configuration Properties API](https://docs.spring.io/spring-boot/api/rest/actuator/configprops.html): bean `@ConfigurationProperties`, bound values và `inputs` origin.
- [Spring Boot Actuator – Endpoints and Sanitization](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, access control và sanitization của `env`/`configprops`.
