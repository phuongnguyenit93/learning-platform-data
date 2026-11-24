# Nạp App Configuration vào môi trường cấu hình Spring

**Azure App Configuration** cho phép quản lý tập trung các tham số vận hành mà một ứng dụng Spring Boot cần khi khởi động: thời gian chờ, giới hạn xử lý, thông điệp hiển thị, endpoint không nhạy cảm và cấu hình theo môi trường. Thông qua thư viện **Spring Cloud Azure App Configuration**, những giá trị được chọn từ store được đưa vào Spring `Environment` và sử dụng bằng những cơ chế quen thuộc: `@Value`, `Environment#getProperty`, `@ConfigurationProperties`.

Đây là bài thực hành trong chương **Cấu hình Azure** thuộc mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, tập trung tích hợp Spring Boot với dịch vụ managed của Azure, cách cấp danh tính/quyền và kiểm tra hoạt động tích hợp. Mục tiêu chính là **nạp được App Configuration vào hệ thống cấu hình của Spring**, hiểu chính xác key nào được nạp, vì sao có giá trị ghi đè và cách chẩn đoán khi ứng dụng đọc sai cấu hình.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Tạo các key-value trong App Configuration theo quy ước mà Spring Cloud Azure đọc được.
2. Khai báo thư viện, `spring.config.import`, endpoint và quyền truy cập.
3. Nhận cấu hình từ store thành Spring property và bind vào đối tượng Java có kiểu dữ liệu.
4. Chọn key/label theo Spring profile, nhận biết thứ tự ưu tiên giữa các nguồn.
5. Tách kiểm thử nghiệp vụ khỏi dịch vụ Azure thật, xử lý lỗi khởi động và hiểu ranh giới của cơ chế refresh.

Luồng khởi động cơ bản:

~~~mermaid
flowchart TD
    A["Spring Boot đọc application.yml"] --> B["Config Data xử lý spring.config.import"]
    B --> C["Spring Cloud Azure truy cập App Configuration"]
    C --> D["Chọn key-value theo key filter và label"]
    D --> E["Đưa PropertySource vào Spring Environment"]
    E --> F["Bind @ConfigurationProperties / @Value / Environment"]
    F --> G["Khởi tạo các bean dùng cấu hình"]
~~~

**Điểm mấu chốt:** App Configuration là **nguồn cấu hình ngoài**. Thư viện sẽ nạp nó vào cơ chế `PropertySource` của Spring; mã nghiệp vụ sau đó không cần gọi Azure SDK để lấy từng timeout hoặc ngưỡng retry.

## 2. Spring Environment và cơ chế import

Trong Spring, `Environment` tập hợp nhiều `PropertySource`, có thể đến từ:

- `application.yml` và `application-{profile}.yml`;
- biến môi trường, system properties, command-line arguments;
- dữ liệu cấu hình ngoài được import, ở đây là **Azure App Configuration**.

Khi gọi `environment.getProperty("catalog.timeout")`, Spring tra cứu theo **thứ tự ưu tiên** của các nguồn đang có. `@Value` và `@ConfigurationProperties` đọc từ cùng cơ chế này.

`spring.config.import=azureAppConfiguration` yêu cầu Spring Boot dùng **Config Data API** để đưa App Configuration vào **trong giai đoạn xử lý cấu hình**, trước khi Spring tạo các bean ứng dụng. Đây là lý do bạn có thể bind dữ liệu Azure qua `@ConfigurationProperties` mà không phải tải dữ liệu thủ công ở `@PostConstruct`.

### Phân biệt ba loại cấu hình

| Nơi khai báo | Vai trò |
| --- | --- |
| `application.yml` | Khai báo cách kết nối Azure, profile, default cục bộ và các thiết lập bootstrap |
| Azure App Configuration | Lưu key-value cho nghiệp vụ và biến thể theo môi trường; provider nạp giá trị vào `Environment` |
| Azure Key Vault | Lưu secret/key/certificate; khi App Configuration chứa Key Vault reference, cần cơ chế giải tham chiếu và quyền đọc Key Vault tương ứng |

Không dùng App Configuration làm nơi đặt plaintext password, API key hoặc connection string nhạy cảm. Các giá trị này thuộc Key Vault; App Configuration có thể chỉ lưu reference khi cần.

## 3. Chuẩn bị môi trường thực hành

Trong bài, giả định ứng dụng có tên `catalog-api` và App Configuration store tên `demo-catalog-config`; hãy thay tên ví dụ bằng tài nguyên của bạn.

Yêu cầu tối thiểu:

- Azure subscription, một Azure App Configuration store hoạt động và quyền đọc dữ liệu trên store.
- JDK 17 trở lên, Maven và dự án Spring Boot có Spring Web.
- Một **danh tính** được cấp role **App Configuration Data Reader** cho store nếu xác thực bằng Microsoft Entra ID.
- Kết nối mạng cho phép ứng dụng truy cập endpoint `https://demo-catalog-config.azconfig.io`.

Ví dụ xuyên suốt sử dụng **Spring Boot 3.5.x** và BOM **Spring Cloud Azure 6.5.0**. Theo ma trận tương thích, Spring Boot 4.0.x dùng Spring Cloud Azure 7.x; không trộn hai dòng này tùy ý. Nếu dự án có Spring Boot/Spring Cloud cố định, chọn phiên bản Azure phù hợp theo bảng phiên bản ở cuối bài.

### 3.1. Tạo key-value trong Azure App Configuration

Trong Azure portal, mở store → **Configuration Explorer** → tạo ba key-value có **Label để trống** (giao diện có thể ghi “(No Label)”):

| Key trong App Configuration | Value | Label |
| --- | --- | --- |
| `/application/catalog.banner` | `Xin chao tu Azure` | *(No Label)* |
| `/application/catalog.timeout` | `PT4S` | *(No Label)* |
| `/application/catalog.max-items` | `25` | *(No Label)* |

Giữ Content Type mặc định cho các key-value thông thường. Chưa tạo label `dev`/`prod` ở bước này để có thể xác nhận luồng nạp cơ bản trước.

**Vì sao phải có `/application/`?** Bộ chọn mặc định của App Configuration provider đọc key theo mẫu `/application/*`, rồi ánh xạ phần phía sau thành tên Spring property. Ví dụ:

~~~text
Azure App Configuration                  Spring Environment
/application/catalog.banner     ----->    catalog.banner
/application/catalog.timeout    ----->    catalog.timeout
/application/catalog.max-items  ----->    catalog.max-items
~~~

Nếu tạo key tên `catalog.banner` mà không có tiền tố, bộ chọn mặc định không khớp; giá trị có thể vẫn tồn tại trên portal nhưng không xuất hiện trong ứng dụng. Có thể thay đổi `key-filter` nếu muốn một quy ước khác, song cần xác minh cách ánh xạ tên của bộ chọn tương ứng.

### 3.2. Cấp quyền cho danh tính

Đối với xác thực bằng Microsoft Entra ID, gán role **App Configuration Data Reader** tại scope store cho đúng principal sẽ chạy ứng dụng. Quyền quản lý tài nguyên trên Azure portal và quyền đọc dữ liệu App Configuration là hai khái niệm riêng; role quản trị chung không nhất thiết cấp data-plane permission.

| Môi trường | Danh tính nên kiểm tra |
| --- | --- |
| Azure App Service / VM được bật Managed Identity | Principal của system-assigned hoặc user-assigned managed identity |
| Container/workload dùng workload identity | Principal/federated identity của workload thực tế |
| Máy cá nhân | Danh tính mà provider/credential chain đã được cấu hình để sử dụng, có thể khác tài khoản đang chọn trên portal |

Lựa chọn ưu tiên khi chạy trên Azure là **Managed Identity**, tránh giữ access key trong mã nguồn. Khi vừa cấp role, cần tính đến thời gian đồng bộ quyền trước lần truy cập tiếp theo.

## 4. Thêm dependency vào Spring Boot

Với một dự án Maven Spring Boot 3.5.x đã có parent hoặc cơ chế quản lý dependency Spring Boot, bổ sung vào `pom.xml`:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-azure.version>6.5.0</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-appconfiguration-config-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

BOM giúp các dependency thuộc Spring Cloud Azure sử dụng cùng bộ phiên bản tương thích, vì vậy không cần khai báo `<version>` riêng cho `spring-cloud-azure-appconfiguration-config-web`.

Có hai provider thường gặp:

| Artifact | Khi sử dụng |
| --- | --- |
| `spring-cloud-azure-appconfiguration-config` | Ứng dụng Spring Boot không cần tích hợp refresh tự động gắn với Spring Web |
| `spring-cloud-azure-appconfiguration-config-web` | Ứng dụng Spring Web; ngoài tải cấu hình còn hỗ trợ kiểm tra refresh theo hoạt động request |

Ví dụ dùng bản `-web`. Đây không phải Spring Cloud Config Server; không cần tạo một config server riêng để tải App Configuration.

## 5. Khai báo import và endpoint

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: catalog-api
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Tại runtime, cung cấp biến môi trường:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://demo-catalog-config.azconfig.io
~~~

Với PowerShell khi chạy trên Windows, có thể thiết lập **trong phiên terminal hiện tại**:

~~~powershell
$Env:AZURE_APPCONFIG_ENDPOINT = "https://demo-catalog-config.azconfig.io"
~~~

Với shell Linux/macOS:

~~~bash
export AZURE_APPCONFIG_ENDPOINT="https://demo-catalog-config.azconfig.io"
~~~

Các thuộc tính cần nhớ:

- `spring.config.import=azureAppConfiguration`: bật quá trình import từ provider ở giai đoạn xử lý Spring Config Data.
- `spring.cloud.azure.appconfiguration.stores[0].endpoint`: URI của store, **không phải** connection string hoặc Key Vault endpoint.
- `stores` là một danh sách; `[0]` có nghĩa store đầu tiên.
- Khi chưa khai báo `selects`, provider dùng bộ chọn key và label mặc định. Với ví dụ này, hãy chạy **không kích hoạt Spring profile nào** để đọc các key có Label trống.

Nếu ứng dụng không thực sự import (ví dụ gõ nhầm `azureAppConfiguration`), việc chỉ đặt endpoint sẽ không tự biến dữ liệu từ Azure thành `PropertySource`.

### 5.1. Endpoint và connection string là hai cách kết nối

**Cách khuyến nghị cho môi trường Azure:** dùng `endpoint` cùng Managed Identity có role đọc dữ liệu.

**Phương án riêng cho local development** nếu chưa cấu hình được xác thực Microsoft Entra ID: dùng connection string được quản lý như secret qua biến môi trường:

~~~properties
spring.config.import=azureAppConfiguration
spring.cloud.azure.appconfiguration.stores[0].connection-string=${AZURE_APPCONFIG_CONNECTION_STRING}
~~~

Đoạn `application.properties` trên là **phương án thay thế** đoạn kết nối `endpoint`, không đặt cả hai thuộc tính cho cùng một store. Không đưa connection string thật vào file commit, tài liệu, issue hay log.

Lệnh `az login` chỉ tạo phiên đăng nhập Azure CLI; ứng dụng còn phải sử dụng credential provider phù hợp. Nếu muốn truy cập bằng tài khoản local và token thay vì connection string, hãy cấu hình credential chain/credential provider theo phiên bản Spring Cloud Azure và cấp quyền đọc store cho **đúng danh tính được chọn**.

## 6. Bind cấu hình thành Java object

Hãy ưu tiên `@ConfigurationProperties` cho một nhóm setting có cấu trúc, vì Spring tự xử lý phép chuyển đổi kiểu và kiểm tra cấu trúc binding.

Tạo `src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Tạo `src/main/java/com/example/catalog/CatalogSettings.java`:

~~~java
package com.example.catalog;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogSettings(
        String banner,
        Duration timeout,
        int maxItems) {
}
~~~

Spring ánh xạ:

| Property đã nạp | Thành phần Java | Kiểu |
| --- | --- | --- |
| `catalog.banner` | `CatalogSettings.banner()` | `String` |
| `catalog.timeout=PT4S` | `CatalogSettings.timeout()` | `Duration` |
| `catalog.max-items=25` | `CatalogSettings.maxItems()` | `int` |

`PT4S` là cú pháp duration ISO-8601 nghĩa là **4 giây**. Spring Binder hỗ trợ chuyển giá trị này sang `java.time.Duration`. Cách đặt tên `max-items` cũng được Spring relaxed binding ánh xạ tới `maxItems`.

Tạo `src/main/java/com/example/catalog/CatalogController.java`:

~~~java
package com.example.catalog;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {
    private final CatalogSettings settings;

    public CatalogController(CatalogSettings settings) {
        this.settings = settings;
    }

    @GetMapping("/catalog/config")
    public Map<String, Object> showPublicConfig() {
        return Map.of(
                "banner", settings.banner(),
                "timeout", settings.timeout().toString(),
                "maxItems", settings.maxItems());
    }
}
~~~

Endpoint demo chỉ hiển thị ba thông số **không nhạy cảm**; ứng dụng thật không nên cung cấp endpoint chung để lộ toàn bộ `Environment`.

Ngoài `@ConfigurationProperties`, có thể đọc từng giá trị:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;

// Ví dụ trong một bean đã được Spring quản lý
@Value("${catalog.banner}")
private String banner;

// Hoặc inject Environment rồi đọc:
String timeout = environment.getProperty("catalog.timeout");
~~~

`@Value` gọn cho một thuộc tính nhưng dễ rải chuỗi key trong nhiều lớp. `@ConfigurationProperties` thuận lợi hơn cho nhóm tham số được sử dụng cùng nhau; cũng có thể kết hợp với validation khi thêm dependency Bean Validation phù hợp.

## 7. Chạy thử và xác minh dữ liệu đã được nạp

Sau khi endpoint được khai báo, danh tính có quyền đọc store và ba key tồn tại đúng nhãn, chạy:

~~~bash
mvn spring-boot:run
~~~

Gọi API thử nghiệm:

~~~bash
curl http://localhost:8080/catalog/config
~~~

Kết quả kỳ vọng (thứ tự trường JSON có thể khác):

~~~json
{
  "banner": "Xin chao tu Azure",
  "timeout": "PT4S",
  "maxItems": 25
}
~~~

Để chứng minh dữ liệu đến từ **Azure** thay vì giá trị hard-code, đổi `/application/catalog.banner` ở Configuration Explorer rồi **khởi động lại ứng dụng** và gọi API lần nữa. Ở phần cơ bản, chưa bật refresh động nên thay đổi trên portal không nhất thiết phản ánh trong phiên ứng dụng đang chạy.

### Đọc nhanh nguồn cấu hình mà không log giá trị

Khi cần kiểm tra nguồn nào đang cung cấp một key, có thể tạm tạo một `ApplicationRunner` trong môi trường phát triển để in **tên nguồn** có chứa key đó:

~~~java
package com.example.catalog;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigDiagnostic {
    @Bean
    ApplicationRunner checkConfigSource(ConfigurableEnvironment environment) {
        return args -> {
            String key = "catalog.banner";
            System.out.println(key + " present: " + environment.containsProperty(key));
            for (PropertySource<?> source : environment.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("Found in source: " + source.getName());
                }
            }
        };
    }
}
~~~

Ví dụ này kiểm tra **sự tồn tại** của key và những nguồn chứa key, không xuất giá trị. Spring có thể nhìn thấy cùng key ở nhiều nguồn; thứ tự `PropertySource` quyết định nguồn nào được chọn. Chỉ sử dụng cách này cho key không nhạy cảm và gỡ phần chẩn đoán khi không còn cần thiết.

## 8. Chọn key và label theo Spring profile

App Configuration có hai chiều chọn dữ liệu:

- **Key filter** lọc theo tên key.
- **Label filter** lọc các phiên bản có label tương ứng (ví dụ `dev`, `staging`, `prod`).

Theo provider, bộ chọn mặc định dùng `/application/*` và label tương ứng với `spring.profiles.active`; nếu không có active profile thì dùng **(No Label)**. Khi đặt `label-filter` rõ ràng, bộ lọc đó **thay thế** cách chọn label theo active profile mặc định.

### 8.1. Minh họa hai môi trường

Tạo thêm các giá trị cùng key:

| Key | Label | Value |
| --- | --- | --- |
| `/application/catalog.banner` | *(No Label)* | `Xin chao tu Azure` |
| `/application/catalog.banner` | `dev` | `Moi truong DEV` |
| `/application/catalog.banner` | `prod` | `Moi truong PRODUCTION` |
| `/application/catalog.timeout` | `prod` | `PT2S` |
| `/application/catalog.max-items` | `prod` | `50` |

Để chạy theo label `prod`, có thể kích hoạt Spring profile `prod`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Nếu cần **giá trị chung từ No Label + giá trị ghi đè từ prod**, khai báo `selects` rõ ràng trong `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ",prod"
~~~

Ở ví dụ này, dấu phẩy đầu biểu thị **(No Label)**, còn phần sau là `prod`. Khi hai label cung cấp cùng key, giá trị của label liệt kê **sau** có độ ưu tiên cao hơn **trong tập dữ liệu được provider nạp**. Vì vậy `catalog.banner` là `Moi truong PRODUCTION`, còn key chỉ có No Label vẫn có thể được nạp.

Để không cố định môi trường trong file, có thể dùng:

~~~yaml
label-filter: ",${spring.profiles.active}"
~~~

Chỉ dùng biến thể này khi luôn có active profile hợp lệ. Nếu muốn hỗ trợ chạy không profile, cần thiết kế riêng cho trường hợp placeholder profile trống hoặc đặt bộ chọn phù hợp.

### 8.2. Cấu hình nhiều key-filter hoặc nhiều store

Khi cần chọn một tập key cụ thể, ví dụ chỉ lấy nhóm catalog:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/catalog.*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

Giá trị của `key-filter` là mẫu lọc phía dịch vụ; không phải regular expression Java. Quy tắc tên key ở App Configuration và bộ chọn phải thống nhất.

Ứng dụng cũng có thể tải từ nhiều stores:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].endpoint=${CATALOG_CONFIG_ENDPOINT}
spring.cloud.azure.appconfiguration.stores[1].endpoint=${SHARED_CONFIG_ENDPOINT}
~~~

Theo tài liệu provider, khi hai store có key trùng nhau, store đứng **sau** trong danh sách có ưu tiên cao hơn **giữa các store**. Điều này chỉ mô tả ưu tiên trong các nguồn Azure; `Environment` vẫn còn nguồn khác có thứ tự ưu tiên riêng.

## 9. Hiểu thứ tự ưu tiên khi property bị ghi đè

Ví dụ, ta có cùng một key ở nhiều nơi:

~~~yaml
# application.yml
catalog:
  banner: "Gia tri local"
~~~

~~~text
Azure App Configuration:
/application/catalog.banner = "Gia tri Azure"
~~~

Khi import theo Spring Config Data API, dữ liệu import có thể ghi đè giá trị trong tài liệu cấu hình đã khai báo import đó, theo quy tắc của Spring Boot. Tuy nhiên, **không được kết luận Azure luôn thắng tất cả**: các nguồn có mức ưu tiên cao hơn, chẳng hạn command-line arguments và nhiều biến môi trường, có thể quyết định giá trị cuối cùng.

Ví dụ chạy thử:

~~~bash
java -jar target/catalog-api.jar --catalog.banner="Gia tri tu command line"
~~~

Một cách tư duy để chẩn đoán:

1. **Key có tồn tại ở Azure không?** Kiểm tra đúng store, tên key và label.
2. **Provider có chọn key đó không?** Kiểm tra `spring.config.import`, `key-filter`, `label-filter` và profile.
3. **Giá trị có vào `Environment` không?** Kiểm tra `environment.containsProperty(...)` và các `PropertySource`.
4. **Nguồn nào đang thắng?** Kiểm tra thứ tự `PropertySource`, biến môi trường, tham số dòng lệnh và file cấu hình.
5. **Bean đã được tạo trước hay sau khi cấu hình đổi?** Đây là vấn đề refresh, không phải lỗi tải cấu hình khởi động.

Mở `/actuator/env` hoặc `/actuator/configprops` ra Internet chỉ để debug là rủi ro vì có thể tiết lộ metadata và cấu hình nhạy cảm; chỉ kiểm tra qua công cụ và quyền truy cập được bảo vệ.

## 10. Khi tải cấu hình thất bại lúc khởi động

Provider mặc định hỗ trợ **fail-fast**: nếu không đọc được store, ứng dụng có thể thất bại ngay khi khởi động. Điều này hữu ích khi cấu hình bắt buộc phải có để vận hành đúng.

Có thể thay đổi hành vi của một store:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].fail-fast=false
~~~

Khi `fail-fast=false`, provider có thể bỏ qua store lỗi ở giai đoạn khởi động; lúc đó ứng dụng chỉ chạy đúng nếu đã có default hợp lệ hoặc cơ chế tự kiểm tra cấu hình bắt buộc. Không nên bật tùy chọn này chỉ để che một lỗi xác thực hoặc thiếu endpoint.

Bảng chẩn đoán:

| Biểu hiện | Nguyên nhân cần kiểm tra |
| --- | --- |
| Spring báo không hiểu import `azureAppConfiguration` | Chưa có dependency App Configuration tương ứng, sai tên import hoặc BOM không tương thích |
| Lỗi 401/403 khi tải store | Danh tính dùng để lấy token, role `App Configuration Data Reader`, scope role hoặc thời gian đồng bộ |
| Lỗi `IllegalArgumentException` về phương thức kết nối | Đồng thời khai báo `endpoint` và `connection-string` trong cùng store |
| Không thấy key mặc dù có trên portal | Key thiếu `/application/`, sai `key-filter`, sai label/profile hoặc đang trỏ sang store khác |
| Giá trị Azure có nhưng bean nhận giá trị local | Nguồn có ưu tiên cao hơn hoặc bean được khởi tạo/cached trước lần refresh |
| Bị lỗi kết nối dù danh tính có quyền | DNS, firewall, proxy, private endpoint, VNet routing, TLS hoặc throttling |
| `Duration` hoặc số nguyên không bind được | Giá trị không đúng định dạng, ví dụ `PT4S` và số nguyên `25` |
| Ứng dụng lỗi chỉ ở môi trường cloud | Principal Managed Identity khác danh tính local; cấu hình mạng và role trên cloud chưa đúng |

Tránh in access token, connection string, key-value nhạy cảm hoặc toàn bộ `Environment` khi xử lý lỗi. Ưu tiên log tên tài nguyên, key filter, nhãn và loại lỗi đã được làm sạch.

## 11. Kiểm thử ứng dụng mà không truy cập Azure thật

Nếu bài test chỉ cần kiểm tra logic sử dụng cấu hình, hãy **tắt App Configuration provider** trong `@SpringBootTest` và cung cấp giá trị giả:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "catalog.banner=Gia tri test",
    "catalog.timeout=PT1S",
    "catalog.max-items=8"
})
class CatalogSettingsTest {

    @Autowired
    CatalogSettings settings;

    @Test
    void bindsLocalTestProperties() {
        assertThat(settings.banner()).isEqualTo("Gia tri test");
        assertThat(settings.timeout().getSeconds()).isEqualTo(1);
        assertThat(settings.maxItems()).isEqualTo(8);
    }
}
~~~

Cách làm này xác nhận ứng dụng **bind Spring property thành Java object**. Nó không chứng minh cấu hình ngoài hay Azure RBAC hoạt động; những phần đó thuộc integration test với một store thử nghiệm thực tế.

Một bài integration test phù hợp có thể:

1. Chuẩn bị store và principal có quyền đọc tối thiểu trong môi trường dev.
2. Tạo `/application/catalog.banner` có label thích hợp.
3. Khởi động ứng dụng với endpoint dev, xác nhận banner đọc từ Azure.
4. Thử đổi label hoặc role để chắc rằng lỗi nhận được có thể chẩn đoán.
5. Chạy kiểm thử từ CI bằng identity thử nghiệm riêng, không dùng secret production.

Không hard-code connection string thật trong `@SpringBootTest` hoặc commit vào repo.

## 12. Refresh: nạp lại không đồng nghĩa được cập nhật ngay

Việc import trong các bước trên diễn ra **khi khởi động**. Để ứng dụng nhận thay đổi mà không khởi động lại, cần cấu hình refresh của provider theo nhu cầu.

Ví dụ nâng cao: tạo key sentinel `/application/catalog.refresh-sentinel` với Label trống và Value `1`. Sau đó bổ sung:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].monitoring.enabled=true
spring.cloud.azure.appconfiguration.stores[0].monitoring.triggers[0].key=/application/catalog.refresh-sentinel
~~~

Mỗi khi muốn xuất bản đồng bộ một nhóm cấu hình mới, cập nhật các key trước, sau đó cập nhật sentinel để báo có thay đổi. Theo tài liệu provider, kiểm tra refresh thường có khoảng cách tối thiểu mặc định **30 giây** và cần một trigger/watch key thích hợp khi monitoring được bật.

Với bản thư viện `-web`, một lần kiểm tra tự động có thể xảy ra khi ứng dụng **nhận servlet request** và đã đến thời điểm kiểm tra. Nếu ứng dụng không có request, chỉ chờ đủ thời gian không bảo đảm rằng refresh đã chạy. Một request kích hoạt việc kiểm tra cũng chưa chắc dùng giá trị mới ngay trong chính request đó.

Sau khi provider nạp dữ liệu mới, `@ConfigurationProperties` có thể được cập nhật theo cơ chế refresh hỗ trợ; bean khác tự giữ giá trị có thể cần `@RefreshScope` hoặc một cơ chế tái tạo rõ ràng. Cần thử nghiệm theo phiên bản và loại bean cụ thể trước khi dựa vào khả năng thay đổi runtime.

**Ranh giới của bài này:** tải cấu hình khởi động phải hoạt động đúng trước. Refresh, feature management và Key Vault references là những luồng nâng cao cần kiểm thử riêng, đặc biệt khi giá trị là secret hoặc đi qua nhiều instance.

## 13. Bài thực hành tự kiểm tra

Bạn quản lý `catalog-api` cho hai môi trường:

- `dev` dùng timeout `PT8S` và banner `Thu nghiem`;
- `prod` dùng timeout `PT2S` và banner `San sang phuc vu`;
- cả hai môi trường dùng `catalog.max-items=20` làm mặc định chung.

Hãy tạo dữ liệu Azure, chọn cách nạp **No Label + label theo môi trường**, bind thành `CatalogSettings` rồi xác minh ứng dụng bằng API thử nghiệm.

**Gợi ý thiết kế:**

| Key | Label | Value |
| --- | --- | --- |
| `/application/catalog.max-items` | *(No Label)* | `20` |
| `/application/catalog.timeout` | `dev` | `PT8S` |
| `/application/catalog.timeout` | `prod` | `PT2S` |
| `/application/catalog.banner` | `dev` | `Thu nghiem` |
| `/application/catalog.banner` | `prod` | `San sang phuc vu` |

Bật profile tương ứng và đặt label filter theo biểu thức `,${spring.profiles.active}` (chú ý bảo đảm profile tồn tại).

**Câu hỏi ôn tập:**

1. Vì sao một key tồn tại trên portal nhưng `@Value` vẫn báo không có property?
2. `spring.config.import` đóng vai trò gì khác với `stores[0].endpoint`?
3. Sự khác nhau giữa `key-filter` và `label-filter` là gì?
4. Khi cùng key có trong Azure và command-line arguments, nên kiểm tra điều gì trước khi kết luận nguồn giá trị?
5. Tại sao unit test không nên mặc định gọi store Azure và tại sao refresh không luôn xảy ra ngay sau khi đổi key?

**Đáp án định hướng:** (1) kiểm tra import, tên key, bộ chọn, label và quyền; (2) import đăng ký nguồn Config Data, endpoint chỉ xác định nơi kết nối; (3) key filter chọn tên key, label filter chọn biến thể; (4) thứ tự `PropertySource` thực tế; (5) test cần tách external dependency, còn refresh phụ thuộc monitoring, trigger, interval, request và bean lifecycle.

## 14. Nguồn tham khảo

- [Microsoft Learn – Quickstart: Spring Boot với Azure App Configuration](https://learn.microsoft.com/en-us/azure/azure-app-configuration/quickstart-java-spring-app): cách tạo key, dependency, Config Data import và đọc dữ liệu.
- [Microsoft Learn – Spring App Configuration provider reference](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-cloud-azure-starter-appconfiguration-config-readme?view=azure-java-stable): `selects`, label, store, fail-fast, monitoring.
- [Microsoft Learn – Dynamic configuration trong Spring](https://learn.microsoft.com/en-us/azure/azure-app-configuration/enable-dynamic-configuration-java-spring-app): refresh thủ công/tự động và điều kiện kích hoạt.
- [Microsoft Learn – Nâng cấp App Configuration provider lên v6](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-convert-to-the-new-spring-boot): yêu cầu `spring.config.import` và thay đổi từ bootstrap sang application config.
- [Microsoft Learn – Tổng quan cấu hình Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration): cách cấu hình credential và tính nhất quán trong các thư viện Azure.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `Environment`, nguồn dữ liệu cấu hình, `spring.config.import` và thứ tự ưu tiên.
- [Azure SDK for Java – Spring Versions Mapping](https://github.com/Azure/azure-sdk-for-java/wiki/Spring-Versions-Mapping): chọn phiên bản Spring Cloud Azure phù hợp Spring Boot.

Sau khi hoàn tất bài này, bạn cần giải thích được **giá trị đi từ App Configuration store vào Spring `Environment` theo quy tắc nào** và xác minh bằng một API nhỏ hoặc `@ConfigurationProperties`. Khi luồng nạp khởi động đã ổn định, mới bổ sung lựa chọn label nâng cao, refresh và kết hợp Key Vault cho secret.
