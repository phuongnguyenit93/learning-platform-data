# Chuyển cấu trúc YAML thành tên thuộc tính phẳng trong Spring Boot

## 1. Vì sao cần chuyển YAML thành thuộc tính phẳng?

YAML cho phép biểu diễn cấu hình theo dạng phân cấp bằng thụt lề, rất thuận tiện khi ứng dụng có nhiều nhóm thiết lập. Tuy nhiên, cơ chế cấu hình của Spring Boot cần có thể tra cứu từng thuộc tính bằng một tên thống nhất, chẳng hạn `server.port` hoặc `spring.datasource.url`.

Vì vậy, khi nạp file `application.yml` hoặc `application.yaml`, Spring Boot chuyển cấu trúc phân cấp thành các **tên thuộc tính phẳng** (flattened property names). Tên thuộc tính phẳng thể hiện đường đi đến giá trị bằng dấu chấm và chỉ số danh sách. Sau đó, các giá trị được đưa vào `Environment` và có thể được đọc trực tiếp hoặc bind vào đối tượng `@ConfigurationProperties`.

Ví dụ, YAML:

~~~yaml
server:
  port: 8085
spring:
  application:
    name: inventory-service
~~~

Tương ứng với hai khóa:

~~~properties
server.port=8085
spring.application.name=inventory-service
~~~

Hai cách viết khác nhau về hình thức, nhưng thể hiện cùng hai thiết lập. **Flattening không thay đổi ý nghĩa của giá trị**, mà biểu diễn địa chỉ của giá trị theo dạng tên thuộc tính để các cơ chế cấu hình có thể sử dụng.

Trong bài này, cần phân biệt ba khái niệm:

- **Cấu trúc YAML:** cây ánh xạ, danh sách và các giá trị cuối.
- **Tên thuộc tính phẳng:** đường dẫn đến một giá trị cuối, ví dụ `app.clients[1].url`.
- **Binding:** bước Spring Boot chuyển các giá trị theo tên thuộc tính thành trường Java, ví dụ `List<Client>` trong một class `@ConfigurationProperties`.

Flattening là bước biểu diễn cấu trúc; binding là bước ánh xạ giá trị sang kiểu Java.

## 2. Quy tắc cơ bản: thụt lề trở thành dấu chấm

Một cặp `key: value` trong YAML là một khóa và giá trị. Nếu giá trị tiếp tục chứa các khóa con, Spring Boot nối tên các khóa từ ngoài vào trong bằng dấu chấm (`.`).

~~~yaml
app:
  service:
    name: billing
    timeout: 15s
  audit:
    enabled: true
    retention-days: 30
~~~

Các tên thuộc tính thu được:

~~~properties
app.service.name=billing
app.service.timeout=15s
app.audit.enabled=true
app.audit.retention-days=30
~~~

Có thể hình dung một đường dẫn:

~~~text
app
 ├── service
 │    ├── name            → app.service.name
 │    └── timeout         → app.service.timeout
 └── audit
      ├── enabled         → app.audit.enabled
      └── retention-days  → app.audit.retention-days
~~~

Dấu cách dùng để thụt lề có ý nghĩa quyết định vị trí cha-con. YAML không dùng dấu ngoặc nhọn để bao một object như JSON. Vì vậy, thay đổi thụt lề có thể thay đổi tên thuộc tính dù dòng văn bản trông gần giống nhau.

Ví dụ:

~~~yaml
# Cấu trúc A
app:
  service:
    timeout: 15s

# Cấu trúc B, xem như một ví dụ riêng
app:
  service: active
  timeout: 15s
~~~

Ở cấu trúc A, tên thuộc tính là `app.service.timeout`. Ở cấu trúc B, tên là `app.service` và `app.timeout`; không còn khóa `app.service.timeout`.

**Nguyên tắc:** đi từ nút gốc đến giá trị cuối; mỗi cấp mapping thêm một đoạn `.<tên-khóa>`.

## 3. Giá trị cuối (scalar) giữ nguyên khóa, không sinh thêm cấp

Một scalar là giá trị không còn cấu trúc con: chuỗi, số, boolean hoặc giá trị đặc biệt như `null`. Khi flatten, tên khóa là đường dẫn đến scalar; phần biểu diễn giá trị được chuyển tiếp tới cơ chế cấu hình và có thể được convert khi bind sang kiểu Java.

~~~yaml
shop:
  title: "Cửa hàng nội bộ"
  port: 8090
  enabled: true
  min-order: 0
  timeout: 750ms
~~~

Dạng tương ứng theo phong cách `.properties`:

~~~properties
shop.title=Cửa hàng nội bộ
shop.port=8090
shop.enabled=true
shop.min-order=0
shop.timeout=750ms
~~~

Ở đây `750ms` có thể được bind thành `java.time.Duration` khi loại đích phù hợp; `8090` có thể được bind thành `int`. Việc biểu diễn bằng khóa phẳng **không đồng nghĩa mọi giá trị đều là chuỗi Java**. Kiểu thực tế phụ thuộc YAML parser, nguồn thuộc tính và bộ chuyển đổi được dùng khi binding.

Với giá trị có ký tự dễ gây nhầm lẫn, nên đặt trong dấu nháy:

~~~yaml
shop:
  display-code: "0012"
  base-url: "https://example.org:8443/api"
  message: "Khởi động thành công"
~~~

Dấu nháy là cú pháp YAML để diễn tả giá trị; chúng không trở thành một đoạn trong tên thuộc tính. Ví dụ, khóa vẫn là `shop.base-url`.

## 4. Danh sách: dùng chỉ số [0], [1], [2]...

Đối với danh sách YAML (sequence), Spring Boot sử dụng **chỉ số bắt đầu từ 0**, đặt trong cặp ngoặc vuông sau tên thuộc tính.

~~~yaml
app:
  supported-locales:
    - vi
    - en
    - ja
~~~

Dạng phẳng:

~~~properties
app.supported-locales[0]=vi
app.supported-locales[1]=en
app.supported-locales[2]=ja
~~~

Danh sách viết kiểu inline vẫn có ý nghĩa tương đương:

~~~yaml
app:
  supported-locales: [vi, en, ja]
~~~

Chỉ số phản ánh đúng vị trí phần tử, do đó việc đổi thứ tự phần tử trong YAML cũng đổi các giá trị gắn với `[0]`, `[1]`, v.v.

### 4.1. Danh sách chứa các object

Ví dụ thường gặp là danh sách endpoint:

~~~yaml
app:
  endpoints:
    - name: primary
      url: "https://primary.example.org"
      retries: 2
    - name: backup
      url: "https://backup.example.org"
      retries: 1
~~~

Dạng phẳng:

~~~properties
app.endpoints[0].name=primary
app.endpoints[0].url=https://primary.example.org
app.endpoints[0].retries=2
app.endpoints[1].name=backup
app.endpoints[1].url=https://backup.example.org
app.endpoints[1].retries=1
~~~

Cách đọc `app.endpoints[1].url` là: vào `app` → thuộc tính `endpoints` → phần tử thứ hai (`[1]`) → thuộc tính `url`.

### 4.2. Danh sách lồng nhau

~~~yaml
app:
  teams:
    - name: backend
      members:
        - An
        - Bình
    - name: frontend
      members:
        - Chi
~~~

Dạng phẳng:

~~~properties
app.teams[0].name=backend
app.teams[0].members[0]=An
app.teams[0].members[1]=Bình
app.teams[1].name=frontend
app.teams[1].members[0]=Chi
~~~

Mỗi lần đi qua danh sách, ta thêm một `[index]`; mỗi lần đi qua mapping, ta thêm một `.key`. Hai quy tắc kết hợp được với nhau mà không cần ngoại lệ mới.

## 5. Mapping, Map và tên khóa có ký tự đặc biệt

YAML mapping có các khóa, thường là chuỗi. Trong ví dụ đơn giản, chúng được ghép bằng dấu chấm:

~~~yaml
app:
  labels:
    region: asia
    tier: gold
~~~

Dạng phẳng:

~~~properties
app.labels.region=asia
app.labels.tier=gold
~~~

Nếu ở Java có `Map<String, String> labels`, Spring Boot có thể bind hai khóa `region` và `tier` thành các entry trong map.

Tuy nhiên, với **tên key của Map chứa ký tự đặc biệt**, cần phân biệt việc tạo tên thuộc tính phẳng với việc giữ nguyên key khi binding. Spring Boot hỗ trợ **bracket notation** để giữ những ký tự không phù hợp với quy tắc tên thuộc tính thông thường.

~~~yaml
app:
  labels:
    "[/api/v1]": public
    "[user.role]": admin
~~~

Các đường dẫn có bracket notation tương ứng:

~~~properties
app.labels.[/api/v1]=public
app.labels.[user.role]=admin
~~~

Ở đây, nếu bind vào `Map<String, String>` thì key được mong muốn là `/api/v1` và `user.role`, không phải hai cấp thuộc tính `user` → `role`.

**Lưu ý:** trong YAML, khi dùng khóa có ngoặc vuông, nên **đặt toàn bộ khóa trong dấu nháy** (`"[/api/v1]"`). Nếu bỏ nháy, dấu `[` và `]` có thể được YAML hiểu như cú pháp cấu trúc thay vì là ký tự literal trong tên khóa.

Với Map phức tạp hoặc có key chứa dấu chấm, dấu gạch chéo, khoảng trắng, hãy xác định kiểu Map đích và chọn bracket notation phù hợp. Không nên mặc định rằng một dấu chấm luôn đại diện cho một dấu chấm bên trong key Map: thông thường nó là ký tự phân tách các cấp của tên thuộc tính.

## 6. Ví dụ tổng hợp: từ một cây YAML sang một danh sách khóa phẳng

Giả sử file `application.yml` chứa cấu hình cho một ứng dụng bán hàng:

~~~yaml
server:
  port: 8088

spring:
  application:
    name: storefront

store:
  region: vn
  checkout:
    enabled: true
    timeout: 4s
  currencies:
    - VND
    - USD
  warehouses:
    - code: hcm
      address:
        city: Ho Chi Minh City
        country: VN
      priorities: [1, 2]
    - code: hn
      address:
        city: Ha Noi
        country: VN
      priorities: [3]
~~~

Tất cả các giá trị cuối được biểu diễn theo dạng phẳng như sau:

~~~properties
server.port=8088
spring.application.name=storefront
store.region=vn
store.checkout.enabled=true
store.checkout.timeout=4s
store.currencies[0]=VND
store.currencies[1]=USD
store.warehouses[0].code=hcm
store.warehouses[0].address.city=Ho Chi Minh City
store.warehouses[0].address.country=VN
store.warehouses[0].priorities[0]=1
store.warehouses[0].priorities[1]=2
store.warehouses[1].code=hn
store.warehouses[1].address.city=Ha Noi
store.warehouses[1].address.country=VN
store.warehouses[1].priorities[0]=3
~~~

Bảng đối chiếu các mẫu đường dẫn:

| Cấu trúc YAML | Ví dụ | Quy tắc tạo tên |
| --- | --- | --- |
| Mapping lồng mapping | `store.checkout.timeout` | Ghép key qua dấu `.` |
| Mapping chứa danh sách scalar | `store.currencies[1]` | Thêm chỉ số phần tử |
| Danh sách chứa mapping | `store.warehouses[0].code` | Chỉ số rồi đến key con |
| Mapping lồng bên trong phần tử danh sách | `store.warehouses[0].address.city` | Tiếp tục ghép key bằng dấu `.` |
| Danh sách trong phần tử danh sách | `store.warehouses[0].priorities[1]` | Mỗi danh sách có cặp `[index]` riêng |

Cây YAML có thể sâu nhiều cấp; quy tắc vẫn là nối đường dẫn đến từng giá trị cuối. Không cần viết một dòng `store.warehouses` chỉ để chỉ ra rằng nó là danh sách: những phần tử con đã thể hiện đầy đủ cấu trúc.

## 7. Nhận giá trị phẳng qua Environment

Sau khi Spring Boot nạp cấu hình, bạn có thể hỏi `Environment` bằng tên thuộc tính. Ví dụ, với YAML tổng hợp phía trên:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigInspector {
    private final Environment environment;

    public ConfigInspector(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("store.region");
    }

    public String firstCurrency() {
        return environment.getProperty("store.currencies[0]");
    }

    public String firstWarehouseCity() {
        return environment.getProperty("store.warehouses[0].address.city");
    }

    public Integer serverPort() {
        return environment.getProperty("server.port", Integer.class);
    }
}
~~~

Ở đây:

- `getProperty("store.region")` truy cập scalar `vn`.
- `getProperty("store.currencies[0]")` truy cập phần tử đầu tiên `VND`.
- `getProperty("store.warehouses[0].address.city")` truy cập `Ho Chi Minh City`.
- `getProperty("server.port", Integer.class)` yêu cầu chuyển giá trị sang `Integer`.

Kết quả thực tế có thể bị **nguồn cấu hình ưu tiên cao hơn** ghi đè, ví dụ biến môi trường, Java system property hoặc đối số dòng lệnh. Việc chuyển YAML thành khóa phẳng không có nghĩa những giá trị lấy ra luôn đến từ file YAML đang xem.

Không nên giả định `Environment#getProperty("store.warehouses")` sẽ trả về toàn bộ danh sách dưới dạng một object Java. Để nhận cấu trúc phức tạp, nên sử dụng binding với `@ConfigurationProperties`.

## 8. Binding tên phẳng vào đối tượng Java bằng @ConfigurationProperties

Spring Boot hỗ trợ bind tập hợp thuộc tính có chung tiền tố thành một đối tượng có cấu trúc. Ta có thể chuyển ví dụ trên thành Java record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;
import java.util.List;

@ConfigurationProperties(prefix = "store")
public record StoreProperties(
        String region,
        Checkout checkout,
        List<String> currencies,
        List<Warehouse> warehouses
) {
    public record Checkout(boolean enabled, Duration timeout) {}

    public record Warehouse(
            String code,
            Address address,
            List<Integer> priorities
    ) {}

    public record Address(String city, String country) {}
}
~~~

Bật chức năng quét lớp `@ConfigurationProperties`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

Một service sử dụng kiểu đã bind:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WarehouseService {
    private final StoreProperties properties;

    public WarehouseService(StoreProperties properties) {
        this.properties = properties;
    }

    public String primaryWarehouseCity() {
        return properties.warehouses().get(0).address().city();
    }
}
~~~

Nhìn theo hướng dữ liệu:

~~~text
store.warehouses[0].address.city
          │         │       │
          ▼         ▼       ▼
   warehouses()   address() city()
   (List)         (record)  (String)
~~~

`app` hay `store` là **prefix** do tác giả quyết định; `spring` và `server` là những prefix cấu hình quen thuộc của Spring Boot. Bạn không cần tạo một Java field chứa dấu `.` hoặc `[0]`: bộ Binder hiểu tên phẳng và tự dựng cấu trúc đích.

Một số biến đổi thường gặp khi bind:

- `store.checkout.timeout=4s` → `Duration.ofSeconds(4)`.
- `store.checkout.enabled=true` → `boolean true`.
- `store.warehouses[0].priorities[1]=2` → phần tử thứ hai của `List<Integer>` trong warehouse đầu tiên.
- `store.region=vn` → `String region`.

Nếu có ràng buộc bắt buộc về số lượng phần tử hoặc giá trị hợp lệ, cần kiểm tra/validate đối tượng sau binding; việc flatten chỉ giải quyết **đường dẫn đến giá trị**, không tự đảm bảo các điều kiện nghiệp vụ.

## 9. Relaxed binding và kiểu viết tên thuộc tính

Spring Boot có cơ chế **relaxed binding** khi ánh xạ tên thuộc tính sang `@ConfigurationProperties`. Vì vậy, tên dạng kebab-case trong cấu hình có thể ánh xạ tới tên camelCase trong Java.

~~~yaml
app:
  request-timeout: 5s
  max-retries: 4
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "app")
public record AppSettings(Duration requestTimeout, int maxRetries) {}
~~~

Đường dẫn cấu hình được biểu diễn chuẩn là `app.request-timeout` và `app.max-retries`; các record component Java là `requestTimeout` và `maxRetries`.

Đây là hai việc khác nhau:

1. **Flattening:** `app` + `request-timeout` → `app.request-timeout`.
2. **Relaxed binding:** `app.request-timeout` → Java `requestTimeout`.

Thông thường, nên dùng **lowercase kebab-case** trong tài liệu cấu hình để tên thuộc tính dễ nhất quán. Đừng dựa vào relaxed binding để giải thích mọi cách truy xuất trực tiếp bằng `Environment#getProperty`: truy xuất qua property resolver và binding sang object có các quy tắc liên quan nhưng không hoàn toàn giống nhau.

Biến môi trường hệ điều hành thường dùng cách đặt tên khác, chẳng hạn `APP_REQUESTTIMEOUT` hoặc tên được chuẩn hóa tương ứng với quy tắc của Binder. Việc chuyển từ khóa phẳng sang biến môi trường thuộc lớp nguồn cấu hình, không phải cú pháp thụt lề YAML. Với danh sách, dạng biến môi trường có thể dùng chỉ số được ngăn bởi dấu gạch dưới, ví dụ `APP_ENDPOINTS_0_NAME`.

## 10. YAML nhiều tài liệu và profile: flatten theo tài liệu đang có hiệu lực

Một file YAML có thể có nhiều tài liệu ngăn bởi `---`. Spring Boot có thể chỉ kích hoạt một tài liệu khi profile phù hợp:

~~~yaml
app:
  banner: common
  retries: 2

---
spring:
  config:
    activate:
      on-profile: prod
app:
  banner: production
  retries: 5
~~~

Tài liệu đầu có các thuộc tính `app.banner=common` và `app.retries=2`. Khi profile `prod` hoạt động, tài liệu thứ hai được kích hoạt và có thể ghi đè các giá trị đó thành `production` và `5`.

**Dấu `---` không trở thành một đoạn trong tên thuộc tính.** Nó phân chia các tài liệu cấu hình. Tương tự, file `application-prod.yml` vẫn tạo ra các tên khóa như `app.banner`; chữ `prod` trong tên file không tự được thêm vào đường dẫn thuộc tính.

Có thể có nhiều nguồn cùng tạo ra `app.banner`. Spring Boot giải quyết giá trị cuối theo quy tắc ưu tiên của các property source, chứ không nối thêm tên file vào khóa.

## 11. Danh sách trong nhiều nguồn cấu hình: không mặc nhiên ghép phần tử

Việc flatten giúp nhìn thấy từng chỉ số, nhưng không có nghĩa Spring Boot sẽ trộn các danh sách từ các nguồn ưu tiên khác nhau theo từng phần tử khi bind vào `@ConfigurationProperties`.

Ví dụ, file mặc định trong JAR:

~~~yaml
app:
  servers:
    - host: dev-one
      port: 8080
    - host: dev-two
      port: 8081
~~~

File cấu hình bên ngoài ưu tiên cao hơn:

~~~yaml
app:
  servers:
    - host: prod-one
      port: 9090
~~~

Đối với một `List<Server>` được bind từ `app.servers`, Spring Boot thường dùng **danh sách từ nguồn có ưu tiên cao nhất**, thay vì ghép `prod-one` với `dev-two` thành danh sách hai phần tử.

Hệ quả thực tế: khi sửa một danh sách cấu hình theo môi trường, hãy khai báo **đầy đủ danh sách mong muốn** ở nguồn override. Không dựa vào giả định rằng `[1]` từ file mặc định vẫn sẽ được giữ lại.

Điều này khác với nhiều cấu hình object hoặc Map, nơi các khóa riêng biệt có thể được tổng hợp theo quy tắc của Binder. Việc kết hợp giá trị giữa các nguồn là vấn đề **merge/binding và độ ưu tiên**, không phải thao tác flattening ban đầu.

## 12. Cách tự chuyển YAML sang tên phẳng

Có thể làm thủ công bằng một quy trình nhất quán:

1. Đọc từ nút gốc của tài liệu YAML và giữ một đường dẫn hiện tại, ban đầu rỗng.
2. Nếu nút là **mapping**, lần lượt thêm `.<key>` vào đường dẫn cho từng khóa con (ở nút gốc bỏ dấu chấm đầu).
3. Nếu nút là **sequence**, lần lượt thêm `[0]`, `[1]`, ... cho các phần tử.
4. Nếu nút là **scalar**, ghi lại một cặp `đường-dẫn = giá-trị`.
5. Với Map key có ký tự đặc biệt cần giữ nguyên khi bind, xem xét **bracket notation** như `.[/api]` và cách quote YAML.

Minh họa bằng giả mã:

~~~text
flatten(node, path):
    if node is mapping:
        for each (key, value):
            childPath = path is empty ? key : path + "." + key
            flatten(value, childPath)

    else if node is sequence:
        for each (item, index):
            childPath = path + "[" + index + "]"
            flatten(item, childPath)

    else:
        output(path, node)
~~~

Đây là mô hình giải thích **cách hình thành tên khóa**, không phải bản cài đặt đầy đủ của YAML parser hoặc Spring Binder. Parser còn xử lý cú pháp YAML, tag, escaping và các quy tắc đặc biệt khác trước khi có dữ liệu cần flatten.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Environment#getProperty("app.server.port")` trả `null` | Đường dẫn YAML thực tế có thể là `app.servers.port` hoặc thụt lề khác | Lần theo chính xác các cấp từ gốc đến scalar |
| Tưởng `app.roles.0` là khóa danh sách chuẩn | Spring Boot biểu diễn danh sách bằng `[0]` | Dùng `app.roles[0]` khi đọc tên phẳng |
| `List<Client>` thiếu phần tử sau khi override cấu hình | Danh sách từ nguồn ưu tiên cao thay thế danh sách cũ khi bind | Ghi đủ danh sách tại nguồn override |
| Map key có dấu `/` hoặc `.` bị thay đổi khi bind | Key chứa ký tự đặc biệt nhưng không dùng bracket notation phù hợp | Dùng key có bracket, đặt trong dấu nháy YAML |
| Giá trị boolean hoặc số không bind đúng kiểu | Kiểu giá trị YAML không giống kỳ vọng của trường Java | Kiểm tra scalar, dấu nháy và kiểu trường đích |
| Đã thấy tên khóa trong YAML nhưng giá trị chạy khác | Nguồn ưu tiên cao hơn đang ghi đè, hoặc profile khác đang hoạt động | Kiểm tra thứ tự nguồn cấu hình và profile |
| Viết `@Value` cho cả một danh sách phức tạp | Đang dùng truy xuất scalar cho cấu trúc cần binder | Dùng `@ConfigurationProperties` với `List` hoặc `Map` |

Để điều tra, trước hết lấy **tên thuộc tính phẳng chính xác**, rồi đối chiếu các nguồn có thể định nghĩa cùng khóa. Spring Boot Actuator có thể hỗ trợ xem thông tin cấu hình thông qua `env` và `configprops`, nhưng nên bảo vệ endpoint và giữ cơ chế che giá trị nhạy cảm.

## 14. Bài tập thực hành

### Bài 1 — Mapping lồng nhau

Cho YAML:

~~~yaml
mail:
  smtp:
    host: "smtp.example.org"
    port: 587
    auth:
      enabled: true
~~~

Hãy viết tên thuộc tính phẳng cho cả ba giá trị cuối.

**Đáp án:**

~~~properties
mail.smtp.host=smtp.example.org
mail.smtp.port=587
mail.smtp.auth.enabled=true
~~~

### Bài 2 — Danh sách object

Cho YAML:

~~~yaml
app:
  workers:
    - id: alpha
      enabled: true
    - id: beta
      enabled: false
~~~

Hãy tìm khóa tương ứng với giá trị `false`.

**Đáp án:** `app.workers[1].enabled`.

### Bài 3 — Kết hợp danh sách và cấu trúc con

Cho YAML:

~~~yaml
academy:
  courses:
    - title: Java Core
      lessons:
        - name: Variables
        - name: Loops
    - title: Spring Boot
      lessons:
        - name: Configuration
~~~

Hãy tìm tên thuộc tính phẳng của `Loops` và `Configuration`.

**Đáp án:**

~~~properties
academy.courses[0].lessons[1].name=Loops
academy.courses[1].lessons[0].name=Configuration
~~~

### Bài 4 — Phân biệt tên khóa và nguồn ghi đè

Có `application.yml` đóng gói:

~~~yaml
app:
  timeout: 3s
~~~

Có `./config/application.yml` bên ngoài:

~~~yaml
app:
  timeout: 12s
~~~

Tên thuộc tính được tạo bởi hai file có giống nhau không? Ứng dụng nhận giá trị nào nếu không có override ưu tiên cao hơn?

**Đáp án:** cả hai cùng tạo `app.timeout`. File ngoài JAR có ưu tiên cao hơn trong nhóm Config Data thông thường, vì vậy giá trị cuối là `12s`. **Tên thuộc tính không mã hóa nơi chứa file**.

## 15. Ghi nhớ

- **Mapping lồng nhau → dấu chấm:** `app.database.pool.size`.
- **Danh sách → chỉ số trong ngoặc vuông:** `app.regions[0]`.
- **Danh sách object → kết hợp chỉ số và dấu chấm:** `app.clients[1].url`.
- **Map key đặc biệt → cân nhắc bracket notation và quote key YAML** để bảo toàn tên khi binding.
- **Flattening** tạo tên khóa; **relaxed binding** ánh xạ tên khóa sang tên trường Java; **precedence** chọn nguồn giá trị cuối.
- **Profile và file nguồn** không phải là một phần tự động của tên khóa; chúng ảnh hưởng đến tài liệu được kích hoạt và thứ tự ghi đè.
- Với danh sách `@ConfigurationProperties`, đừng giả định các phần tử từ nhiều nguồn sẽ được ghép.

Tài liệu tham khảo: [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) và [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
