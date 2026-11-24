# Key, label, bộ lọc và ánh xạ cấu hình theo môi trường

Khi một ứng dụng Spring Boot triển khai ở `dev`, `staging` và `prod`, mã nguồn thường giống nhau nhưng các giá trị như timeout, mức retry hoặc địa chỉ API phải khác nhau. **Azure App Configuration** giải quyết nhu cầu này bằng cặp **key–value**, **label** và các **bộ lọc lựa chọn**. Spring Cloud Azure đọc tập giá trị phù hợp rồi ánh xạ thành thuộc tính của Spring `Environment`.

Bài thuộc chương **Cấu hình Azure** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud, chú trọng danh tính/quyền, dữ liệu và bí mật, kiểm thử tích hợp và sự khác biệt giữa các nhà cung cấp. Trong bài này, ta tập trung vào **quy tắc chọn cấu hình và biến đổi tên key** của Azure; các ví dụ dùng cấu hình vận hành không nhạy cảm.

## 1. Mục tiêu và tình huống thực tế

Sau khi học, bạn cần giải thích và thực hiện được:

1. Khác biệt giữa **key**, **label**, **value**, **tag** và **store**.
2. Cách `key-filter` và `label-filter` quyết định key-value nào được nạp.
3. Quy tắc **(No Label)**, `spring.profiles.active` và thứ tự ưu tiên khi trùng key.
4. Cách bỏ tiền tố (`trim-key-prefix`) để biến key Azure thành Spring property.
5. Cách tổ chức cấu hình chung + cấu hình từng môi trường; khi nào cần store riêng.
6. Cách xác minh dữ liệu vào `Environment`, bind vào Java và xử lý lỗi chọn sai key/label.

Xét `checkout-service` có cùng mã ở ba môi trường:

| Cấu hình | dev | staging | prod |
| --- | --- | --- | --- |
| Thời gian chờ thanh toán | `PT15S` | `PT8S` | `PT3S` |
| Số lần retry tối đa | `2` (mặc định chung) | `2` (mặc định chung) | `5` |
| API endpoint | `https://sandbox-payments.example.com` | `https://sandbox-payments.example.com` | `https://payments.example.com` |

Thay vì duy trì ba bản `application.yml` gần giống nhau, ta đặt các **biến thể của cùng key** vào App Configuration và sử dụng label để chọn cấu hình thích hợp.

~~~mermaid
flowchart LR
    A["App Configuration: nhiều (key, label, value)"] --> B["key-filter"]
    B --> C["label-filter"]
    C --> D["Chọn phiên bản và giải quyết key trùng"]
    D --> E["trim-key-prefix"]
    E --> F["Spring PropertySource"]
    F --> G["@ConfigurationProperties / Environment"]
~~~

> **Nhớ đúng thứ tự khái niệm:** *Lọc* quyết định bản ghi nào được lấy; *ưu tiên* quyết định giá trị thắng khi key trùng; *trim* quyết định key cuối cùng xuất hiện dưới tên nào trong Spring.

## 2. Mô hình dữ liệu: key, label, value và tag

Một cấu hình App Configuration có các thuộc tính thường gặp:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Key** | Tên logic của tham số, có thể tổ chức bằng prefix/dấu phân cách | `/application/checkout.timeout` |
| **Label** | Biến thể của key theo môi trường, phiên bản hoặc phạm vi | `dev`, `staging`, `prod` |
| **Value** | Giá trị của key-label cụ thể | `PT3S` |
| **Content type** | Gợi ý kiểu nội dung cho provider, ví dụ JSON hay reference | `application/json` |
| **Tags** | Metadata dạng tên–giá trị giúp phân loại/chọn lọc | `team=payments` |
| **Store** | Tài nguyên Azure chứa tập key-value và cấu hình truy cập | `checkout-config` |

**Đơn vị định danh thực tế là cặp (key, label).** Trong một store có thể tồn tại đồng thời:

~~~text
Key                              Label       Value
/application/checkout.timeout    (No Label)  PT6S
/application/checkout.timeout    dev         PT15S
/application/checkout.timeout    staging     PT8S
/application/checkout.timeout    prod        PT3S
~~~

Đây là **bốn bản ghi khác nhau của cùng key**, không phải bốn key Java khác nhau. Ở phía Spring, sau khi đã chọn label và bỏ tiền tố, tất cả đều hướng tới tên property `checkout.timeout`.

### 2.1. (No Label) không phải chuỗi "default"

Bản ghi có label trống thường được Azure portal hiển thị là **(No Label)**. Ở tầng API, giá trị này có biểu diễn null/`\0` tùy ngữ cảnh; ở thuộc tính `label-filter` của Spring provider, phần tử **rỗng trước dấu phẩy** biểu thị (No Label):

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=,prod
~~~

Cấu hình trên có nghĩa: lấy giá trị **không có label trước**, sau đó lấy giá trị label `prod` để ghi đè những key trùng. Nó không liên quan tới một label có tên đúng bằng `default`, `null` hay `(No Label)`.

### 2.2. Quy ước đặt tên key

Các key dạng sau hữu ích trong Spring:

~~~text
/application/checkout.timeout
/application/checkout.max-retries
/application/checkout.endpoint
/application/checkout.feature-message
~~~

- `/application/` là tiền tố mà Spring App Configuration provider chọn **theo mặc định**.
- Phần sau tiền tố dùng cú pháp Spring property, ví dụ `checkout.max-retries`.
- Azure App Configuration phân biệt chữ hoa/chữ thường trong tên key; nên thống nhất chữ thường và dấu gạch nối để tránh lỗi khó phát hiện.
- Prefix có thể tách ứng dụng hoặc lĩnh vực, ví dụ `/checkout-service/checkout.timeout`, miễn là bạn cấu hình bộ lọc và trim phù hợp.

**Không dùng label để chứa secret hoặc mặc định coi label là hàng rào bảo mật.** Label phân loại bản ghi; phân quyền đọc dữ liệu của App Configuration chủ yếu thực hiện ở phạm vi store. Dữ liệu nhạy cảm như API token, mật khẩu và khóa truy cập nên ở **Azure Key Vault**.

## 3. Bộ chọn mặc định của Spring Cloud Azure

Khi dự án có App Configuration provider và khai báo:

~~~properties
spring.config.import=azureAppConfiguration
spring.cloud.azure.appconfiguration.stores[0].endpoint=${AZURE_APPCONFIG_ENDPOINT}
~~~

provider đọc key-value từ store theo bộ chọn mặc định:

| Thành phần | Khi không cấu hình riêng |
| --- | --- |
| Key filter | `/application/*` |
| Label filter, không có active Spring profile | `(No Label)` |
| Label filter, có active Spring profile | Label trùng tên các active profile theo quy tắc ưu tiên Spring |
| Tên property trong Spring | Bỏ phần tiền tố đã match bởi key filter, điển hình `/application/` |

Ví dụ chỉ có key `checkout.timeout` (không có `/application/`) sẽ **không được chọn** bởi filter mặc định. Ngược lại, key `/application/checkout.timeout` có label `prod` sẽ **không được nạp** khi ứng dụng không có active profile và cũng không chỉ định filter `prod`.

**Hai điều kiện phải đúng đồng thời:** tên key khớp key filter **và** label khớp label filter.

### 3.1. Cấu hình tối thiểu để chạy thử

Giả sử dùng Spring Boot 3.5.x với dòng Spring Cloud Azure 6.x tương thích. BOM trong `pom.xml` chọn một phiên bản 6.x được hỗ trợ, rồi khai báo App Configuration dependency:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-appconfiguration-config</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: checkout-service
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
~~~

Khi dùng endpoint và xác thực Microsoft Entra ID, danh tính ứng dụng cần quyền **App Configuration Data Reader** trên store. Trên Azure, nên dùng Managed Identity; máy local có thể dùng cấu hình credential chain phù hợp và một tài khoản được cấp quyền. Endpoint ví dụ:

~~~text
AZURE_APPCONFIG_ENDPOINT=https://checkout-config.azconfig.io
~~~

Tên store và endpoint phải thay bằng tài nguyên thật. Dependency `spring-cloud-azure-appconfiguration-config` đủ cho tải cấu hình; ứng dụng Spring Web có thể dùng biến thể `-web` để thêm hỗ trợ kiểm tra refresh qua request.

## 4. Key filter: chọn phạm vi cấu hình cần nạp

`key-filter` chỉ định tên key hoặc mẫu key. Với Spring Cloud Azure, cú pháp cấu hình là:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
~~~

Một số mẫu phổ biến:

| Key filter | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `/application/*` | Các key bắt đầu bằng `/application/` | Mặc định của provider |
| `/application/checkout.*` | Chỉ nhóm key có prefix `/application/checkout.` | Phải kiểm tra **trim prefix** để giữ tên `checkout.*` trong Spring |
| `/application/checkout.timeout` | Chọn đúng một key | Không tự động lấy `checkout.max-retries` |
| `/checkout-service/*` | Chỉ namespace của checkout-service | Hữu ích khi dùng chung store cho nhiều ứng dụng |

Filter hỗ trợ wildcard tiền tố `*` và có thể hỗ trợ chọn nhiều key cụ thể bằng dấu phẩy theo quy tắc của provider. **Không kết hợp wildcard và danh sách phân tách bằng dấu phẩy trong cùng filter**; nếu cần hai phạm vi, dùng nhiều phần tử `selects`.

Ví dụ, chỉ tải hai nhóm cấu hình khác nhau:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/checkout.*"
                label-filter: "prod"
              - key-filter: "/application/fulfillment.*"
                label-filter: "prod"
            trim-key-prefix:
              - "/application/"
~~~

Phần `trim-key-prefix` được khai báo rõ ràng để cả hai nhóm có dạng `checkout.*` và `fulfillment.*` ở phía Spring. Nếu không hiểu quy tắc trim của filter hẹp, có thể vô tình làm `checkout.timeout` thành `timeout`.

**Bộ lọc là điều kiện truy xuất**, không phải luật tự động gán mọi key vào đúng class Java. Kết quả cuối cùng phụ thuộc thêm vào tên đã được trim và cơ chế binding của Spring.

## 5. Label filter: chọn biến thể theo môi trường

`label-filter` lựa chọn biến thể label của các key đã match. Khi giá trị bị trùng, provider xử lý theo **thứ tự ưu tiên label**.

### 5.1. Một label tường minh

~~~properties
spring.cloud.azure.appconfiguration.stores[0].selects[0].key-filter=/application/*
spring.cloud.azure.appconfiguration.stores[0].selects[0].label-filter=prod
~~~

Cách này **chỉ chọn** các key có label `prod`; key chỉ tồn tại với (No Label) sẽ không tự xuất hiện. Điều đó có thể làm các default chung bị thiếu.

### 5.2. Kết hợp (No Label) và label của môi trường

Tạo dữ liệu tại Configuration Explorer:

| Key | Label | Value |
| --- | --- | --- |
| `/application/checkout.timeout` | (No Label) | `PT6S` |
| `/application/checkout.timeout` | `dev` | `PT15S` |
| `/application/checkout.timeout` | `staging` | `PT8S` |
| `/application/checkout.timeout` | `prod` | `PT3S` |
| `/application/checkout.max-retries` | (No Label) | `2` |
| `/application/checkout.max-retries` | `prod` | `5` |
| `/application/checkout.endpoint` | (No Label) | `https://sandbox-payments.example.com` |
| `/application/checkout.endpoint` | `prod` | `https://payments.example.com` |

Tại `application.yml`, chọn label trống trước và label theo active profile sau:

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: ',${spring.profiles.active}'
~~~

YAML dùng dấu nháy đơn quanh cả chuỗi `',${spring.profiles.active}'` để giữ nguyên dấu phẩy và placeholder cho Spring xử lý. Ví dụ này **yêu cầu active profile được đặt rõ ràng**.

Chạy với profile `prod`:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=prod
~~~

Hoặc thiết lập môi trường tương đương:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Theo quy tắc **label bên phải được ưu tiên**, kết quả dự kiến:

| Spring property | Giá trị khi profile `prod` | Nguồn thắng |
| --- | --- | --- |
| `checkout.timeout` | `PT3S` | Label `prod` |
| `checkout.max-retries` | `5` | Label `prod` |
| `checkout.endpoint` | `https://payments.example.com` | Label `prod` |

Nếu chạy profile `dev`, kết quả dự kiến là `checkout.timeout=PT15S`, `checkout.max-retries=2` (fallback từ No Label) và endpoint sandbox. Profile `staging` có timeout `PT8S` và các giá trị chung còn lại.

Đây chính là **mô hình xếp lớp**:

~~~mermaid
flowchart TB
    A["Lớp chung: (No Label)"] --> C["Kết quả cấu hình trong Spring"]
    B["Lớp môi trường: dev / staging / prod"] --> C
    D["Nếu cùng key, lớp môi trường ghi đè"] --> C
~~~

Khi không có active Spring profile, không nên dùng `',${spring.profiles.active}'` vì placeholder có thể không phân giải như dự kiến. Hãy dùng mặc định của provider để lấy riêng **(No Label)** hoặc khai báo label độc lập với profile, ví dụ `label-filter: ',${DEPLOY_ENV:dev}'`. Nếu dùng `DEPLOY_ENV`, bạn cần bảo đảm nó phản ánh đúng môi trường triển khai.

### 5.3. Nhiều profile đồng thời

Ứng dụng có thể bật `dev,observability`, nhưng đây là **hai active profiles**, không nhất thiết là một nhãn Azure có tên `dev,observability`. Provider hỗ trợ xét nhiều profile theo thứ tự ưu tiên; thứ tự nạp có ảnh hưởng khi hai label cùng định nghĩa một key.

Để cấu hình nghiệp vụ theo môi trường nhất quán, nên có **một profile môi trường chính** (`dev`, `staging`, `prod`) và tách các cấu hình phụ như `observability` nếu cần. Kiểm tra giá trị cuối cùng của các key trùng ở môi trường thực, đặc biệt khi sử dụng nhiều `selects` hoặc có thêm biến môi trường/command-line arguments.

### 5.4. Khi nào dùng label wildcard?

Một số phiên bản provider hỗ trợ `label-filter=*` để lấy nhiều label. Tuy nhiên, nếu cả `dev` và `prod` đều có cùng key, lựa chọn tất cả label sẽ làm **mất ý nghĩa phân tách môi trường** và phụ thuộc vào quy tắc ghi đè khi nạp. Đối với vận hành, hãy ưu tiên chọn **rõ label cần dùng**; không dùng `*` như cách sửa nhanh lỗi thiếu dữ liệu.

## 6. Ánh xạ key Azure thành Spring property

Spring Cloud Azure không nhất thiết dùng **nguyên tên key** của Azure làm tên trong `Environment`. Nó có thể **cắt tiền tố** trước khi tạo property.

### 6.1. Trường hợp mặc định

~~~text
App Configuration key                  Spring property
/application/checkout.timeout   ---->  checkout.timeout
/application/checkout.endpoint  ---->  checkout.endpoint
/application/checkout.max-retries ----> checkout.max-retries
~~~

Vì mặc định chọn `/application/*` nên prefix `/application/` thường được bỏ đi. Mã Java chỉ dùng `checkout.timeout` thay vì `/application/checkout.timeout`.

### 6.2. Khi thay key-filter, cần kiểm tra trim

Giả sử store có:

~~~text
/application/checkout.timeout
/application/checkout.max-retries
/application/catalog.timeout
~~~

Để chỉ lấy nhóm checkout nhưng **giữ** tên `checkout.timeout` và `checkout.max-retries`, hãy chủ động khai báo prefix cần bỏ:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/checkout.*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/application/"
~~~

Khi trim `/application/`, tên `checkout.timeout` được giữ nguyên. Đây là cách làm đáng tin cậy khi key filter hẹp hơn namespace chung. Nếu để trim phụ thuộc hoàn toàn vào key-filter `/application/checkout.*`, prefix `/application/checkout.` có thể bị cắt, khiến property còn `timeout`. Sau đó `@ConfigurationProperties(prefix = "checkout")` sẽ không bind đúng.

Khi có nhiều prefix cần bỏ trong một store, `trim-key-prefix` có thể khai báo dưới dạng danh sách; hãy chọn các prefix cụ thể và kiểm tra các key trùng nhau **sau khi trim**.

### 6.3. Đặt namespace theo ứng dụng

Có thể dùng một store chung và đặt key:

~~~text
/checkout-service/checkout.timeout
/checkout-service/checkout.max-retries
/catalog-service/catalog.timeout
~~~

Để checkout-service chỉ nhận dữ liệu thuộc mình:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/checkout-service/*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/checkout-service/"
~~~

Đích trong Spring là `checkout.timeout` và `checkout.max-retries`. Cách chia namespace dùng **key prefix** để chọn ứng dụng và **label** để chọn môi trường; hai chiều này khác nhau và có thể kết hợp.

### 6.4. Binding Java và kiểu dữ liệu

Định nghĩa các property:

~~~java
package com.example.checkout;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutSettings(
        Duration timeout,
        int maxRetries,
        URI endpoint) {
}
~~~

Kích hoạt scanning ở ứng dụng:

~~~java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
~~~

| Spring property | Constructor record | Ví dụ dữ liệu |
| --- | --- | --- |
| `checkout.timeout` | `Duration timeout` | `PT3S` → 3 giây |
| `checkout.max-retries` | `int maxRetries` | `5` |
| `checkout.endpoint` | `URI endpoint` | `https://payments.example.com` |

Spring Binder hỗ trợ relaxed binding, nên `max-retries` được ánh xạ vào `maxRetries`. Tuy vậy, **không được kỳ vọng Binder tự khôi phục phần tiền tố đã trim sai**: tên property phải có cấu trúc đúng trước khi binding diễn ra.

## 7. Phân biệt bốn tầng ưu tiên dễ bị nhầm

Nhiều người thấy key `checkout.timeout` nhận giá trị lạ và quy kết “Azure ghi đè file local”. Thực tế có bốn tầng cần kiểm tra:

| Tầng | Quy tắc cần xem xét |
| --- | --- |
| **Tập key được chọn** | `key-filter` và `label-filter` quyết định bản ghi nào lọt vào provider |
| **Các bản ghi trùng key trong một store** | Với chuỗi label như `,prod`, label liệt kê sau được ưu tiên; với nhiều `selects` phải kiểm tra thứ tự nạp |
| **Các App Configuration stores** | Nếu hai store cho cùng property sau khi trim, store đứng sau trong danh sách provider có ưu tiên cao hơn |
| **Toàn bộ Spring Environment** | File local, biến môi trường, system property, command-line arguments và import có thứ tự ưu tiên riêng của Spring Boot |

Ví dụ hai stores:

~~~properties
spring.cloud.azure.appconfiguration.stores[0].endpoint=${SHARED_CONFIG_ENDPOINT}
spring.cloud.azure.appconfiguration.stores[1].endpoint=${CHECKOUT_CONFIG_ENDPOINT}
~~~

Nếu cả hai cung cấp `checkout.timeout` và bộ lọc đều chọn, provider cho giá trị từ store `[1]` ưu tiên cao hơn giá trị từ store `[0]`. Tuy nhiên, command-line argument chẳng hạn:

~~~bash
java -jar checkout-service.jar --checkout.timeout=PT1S
~~~

có thể ghi đè giá trị đã nạp từ App Configuration do **quy tắc ưu tiên cấp Spring Environment**. Cần kiểm tra toàn bộ nguồn property trước khi khẳng định “label prod không hoạt động”.

### 7.1. Vì sao dùng label có thể gây lỗi phân quyền?

Không có bảo đảm rằng một identity đọc được store chỉ đọc được label `dev` mà không đọc được label `prod`. Do đó:

- Nếu `dev`/`staging`/`prod` chỉ khác nhau ở các tham số không nhạy cảm và cùng nhóm vận hành được phép đọc, **một store + labels** có thể phù hợp.
- Nếu môi trường `prod` yêu cầu quyền truy cập tách biệt, **store riêng cho prod** là mô hình rõ ràng hơn.
- Nếu giá trị là secret (password, token), lưu trong **Key Vault** rồi dùng reference khi cần; không coi label hoặc tag là cơ chế bảo mật secret.

### 7.2. Tổ chức store và label khi có nhiều ứng dụng

| Bối cảnh | Cấu trúc gợi ý |
| --- | --- |
| Một ứng dụng, vài môi trường cùng nhóm quyền | Một store; key `/application/*`, label `dev`/`staging`/`prod` |
| Nhiều ứng dụng dùng chung store | Key prefix riêng theo ứng dụng, label theo môi trường; trim để mã Java ổn định |
| Nhiều ứng dụng dùng tham số chung | Store dùng chung cho defaults, store ứng dụng đứng sau để override một số key |
| Production cần quyền và mạng tách biệt | Store riêng theo môi trường, role data reader riêng |
| Cần giữ nguyên tập cấu hình cho một lần phát hành | Xem xét **App Configuration snapshots** thay vì chỉ dựa vào label mutable |

## 8. Các bộ lọc nâng cao: tag và snapshot

### 8.1. Tag filter khi thư viện hỗ trợ

Tag là metadata dạng `name=value`, chẳng hạn `team=checkout` và `region=apac`. Trong dòng Spring Cloud Azure hỗ trợ `tags-filter` (ví dụ App Configuration library 7.1 trở lên), bạn có thể giới hạn bản ghi bằng nhiều tag:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/*"
                label-filter: "prod"
                tags-filter:
                  - "team=checkout"
                  - "region=apac"
~~~

Nhiều mục `tags-filter` được kết hợp theo **AND**: bản ghi cần khớp **tất cả tag được yêu cầu**. Khác với label, tag có thể mô tả nhiều chiều metadata, nhưng không thể thay thế phân quyền.

**Lưu ý phiên bản:** Không sao chép `tags-filter` vào dự án đang dùng Spring Cloud Azure 6.x nếu bản phát hành đó không hỗ trợ thuộc tính; hãy kiểm tra README/changelog của **phiên bản dependency đang dùng**. Phần lõi của bài thực hành chỉ cần key filter và label filter.

### 8.2. Snapshot và vấn đề trim prefix

Snapshot là tập cấu hình được chụp tại một thời điểm, hữu ích khi cần kiểm soát chính xác cấu hình của một release. Khi chọn snapshot bằng `snapshot-name`, quy tắc tự trim của key-filter không được áp dụng theo cách thông thường; cần chỉ rõ prefix:

~~~yaml
spring:
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - snapshot-name: "checkout-release-2026-11"
            trim-key-prefix:
              - "/application/"
~~~

Đoạn trên chỉ là ví dụ **nếu snapshot đã tồn tại** với tên và composition type mà provider hỗ trợ. Snapshot bất biến; sửa key ngoài store không làm snapshot đó thay đổi. Không kết hợp `snapshot-name` với `key-filter`/`label-filter` trong **cùng một select** nếu phiên bản thư viện yêu cầu chọn một trong các phương thức.

## 9. Kiểm tra key, label và property đã nạp

### 9.1. Kết quả trước và sau khi chọn label

Giả sử dùng bảng ở mục 5 và cấu hình `label-filter: ',${spring.profiles.active}'`:

| Active profile | `checkout.timeout` | `checkout.max-retries` | `checkout.endpoint` |
| --- | --- | --- | --- |
| `dev` | `PT15S` | `2` | Sandbox |
| `staging` | `PT8S` | `2` | Sandbox |
| `prod` | `PT3S` | `5` | Production |

Đây là tiêu chí kiểm tra đầu tiên: **một profile khác phải khiến đúng các key được override thay đổi**, còn default chung giữ nguyên.

### 9.2. In tên PropertySource, tránh log giá trị

Để kiểm tra nguồn nào chứa key mà không đưa giá trị nhạy cảm vào log, có thể dùng đoạn chẩn đoán trong **môi trường phát triển**:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Configuration
class ConfigSourceDiagnostics {
    @Bean
    ApplicationRunner reportKeySources(ConfigurableEnvironment env) {
        return args -> {
            String key = "checkout.timeout";
            System.out.println("Has property: " + env.containsProperty(key));
            for (PropertySource<?> source : env.getPropertySources()) {
                if (source.containsProperty(key)) {
                    System.out.println("PropertySource: " + source.getName());
                }
            }
        };
    }
}
~~~

Danh sách có thể có **nhiều nguồn chứa một key**; nguồn ưu tiên cao nhất theo thứ tự Spring đang sử dụng cung cấp giá trị hiệu lực. Kiểm tra tên nguồn và key đã trim an toàn hơn việc in `env.getProperty(...)` cho mọi property.

### 9.3. Kiểm thử binding mà không phụ thuộc Azure thật

Đối với một test chỉ kiểm tra mapping Java, vô hiệu hóa App Configuration và đưa cấu hình test vào Spring:

~~~java
package com.example.checkout;

import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cloud.azure.appconfiguration.enabled=false",
    "checkout.timeout=PT2S",
    "checkout.max-retries=9",
    "checkout.endpoint=https://localhost.example.test"
})
class CheckoutSettingsTest {
    @Autowired
    CheckoutSettings settings;

    @Test
    void bindsValues() {
        assertThat(settings.timeout()).isEqualTo(Duration.ofSeconds(2));
        assertThat(settings.maxRetries()).isEqualTo(9);
        assertThat(settings.endpoint().getHost()).isEqualTo("localhost.example.test");
    }
}
~~~

Test này xác nhận Spring Binder và kiểu dữ liệu. Một **integration test** mới chứng minh được provider thật sự chọn đúng key và label trong App Configuration, rằng danh tính có quyền đọc và rằng kết quả ghi đè đúng theo môi trường.

### 9.4. Checklist kiểm thử tích hợp

Với một store dev thử nghiệm và principal có quyền đọc tối thiểu:

1. Tạo `checkout.timeout` với (No Label) và hai label `dev`/`prod`.
2. Chạy profile `dev`, xác minh `checkout.timeout` bằng bean hoặc endpoint nội bộ chỉ cho dữ liệu không nhạy cảm.
3. Đổi profile `prod`, khởi động lại và xác minh giá trị khác.
4. Xóa **bản ghi dev** trong môi trường thử nghiệm, kiểm tra fallback về (No Label) khi dùng filter `,dev`.
5. Thu hẹp key-filter thành `/application/checkout.*`, kiểm tra `trim-key-prefix` để Java property vẫn giữ tên `checkout.*`.
6. Kiểm tra hành vi khi chuyển store, sai label hoặc khi danh tính mất quyền đọc; xác nhận không rò rỉ credential trong log.

## 10. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Key có trong Azure nhưng Spring không nhìn thấy | Không khớp `key-filter` hoặc `label-filter` | Xác minh cặp (key, label) cụ thể; không chỉ kiểm tra tên key |
| Chạy profile `prod` nhưng thấy default | Chỉ chọn (No Label), hoặc giá trị bị nguồn Spring khác ghi đè | Kiểm tra `label-filter` và thứ tự `PropertySource` |
| Chạy profile `prod` nhưng không có default chung | Bộ lọc chọn riêng `prod` | Dùng `label-filter: ',prod'`, đặt (No Label) trước |
| `@ConfigurationProperties(prefix="checkout")` không bind | `trim-key-prefix` đã cắt luôn chữ `checkout.` | Kiểm tra tên đã vào `Environment`, trim đúng `/application/` |
| Key thiếu mặc dù không đổi code Java | Có thay đổi key prefix hoặc cấu trúc đặt tên | Chuẩn hóa namespace và cung cấp migration cho key cũ |
| Hai key sau trim ghi đè nhau | Các prefix khác nhau tạo cùng tên Spring property | Thiết kế namespace không xung đột và xác định nguồn có ưu tiên |
| Có nhiều profile, kết quả không như dự kiến | Label priority và thứ tự profile | Giữ profile môi trường rõ ràng; kiểm tra cấu hình hiệu lực bằng test |
| Azure trả 403 | Identity thiếu `App Configuration Data Reader` | Gán data role cho principal thực tế; kiểm tra scope |
| App local đúng, cloud sai | Store endpoint/profile/role của môi trường cloud khác | So sánh metadata kết nối, profile và namespace; không log credential |
| Dùng `tags-filter` nhưng không có dữ liệu | Thiếu tag cần thiết hoặc phiên bản provider không hỗ trợ | Kiểm tra tag theo AND và phiên bản dependency |
| Chọn snapshot nhưng key giữ `/application/` | Snapshot không tự trim như key filter thông thường | Thêm `trim-key-prefix: ["/application/"]` |

**Phân biệt lỗi chọn key với lỗi refresh:** thay giá trị trong store khi ứng dụng đang chạy không luôn cập nhật bean ngay. Bài này chủ yếu xét **giá trị được nạp khi khởi động**; nếu cần cập nhật runtime, cấu hình monitoring/refresh và vòng đời bean riêng. Trước khi điều tra refresh, hãy kiểm tra giá trị nhận được sau **khởi động mới** có đúng hay không.

## 11. Những quyết định thiết kế cần chủ động

Khi đưa App Configuration vào dự án thật, hãy thống nhất:

1. **Quy ước namespace:** `/application/` cho một app đơn giản, hoặc `/<service-name>/` nếu nhiều ứng dụng chia sẻ store.
2. **Quy ước label:** `dev`, `staging`, `prod` hoặc tên môi trường do nhóm xác định; không dùng nhiều tên đồng nghĩa.
3. **Fallback:** có lấy (No Label) chung cho mọi môi trường không; nếu có, đặt (No Label) ở đầu `label-filter`.
4. **Giá trị trùng:** xác định thứ tự nhiều labels, nhiều selects và nhiều stores bằng bài kiểm thử thực tế.
5. **Trim prefix:** định nghĩa rõ Spring property sau khi nạp, nhất là khi key-filter hẹp hoặc dùng snapshot.
6. **Mức độ cách ly:** môi trường cần quyền khác nhau nên cân nhắc store riêng; secret thuộc Key Vault.
7. **Quan sát và kiểm thử:** không log credential; kiểm tra nguồn property và có bài test cho mỗi môi trường trọng yếu.

Việc thống nhất các quyết định này giúp mã Spring giữ cùng các tên property (`checkout.timeout`, `checkout.endpoint`) qua nhiều môi trường, trong khi Azure chỉ thay đổi **bản ghi nào được chọn** và **giá trị nào được ưu tiên**.

## 12. Bài tập áp dụng

Một tổ chức triển khai `shipping-service` ở `dev` và `prod`. Store dùng chung chứa:

~~~text
/application/shipping.timeout    (No Label)  PT5S
/application/shipping.timeout    prod        PT2S
/application/shipping.max-batch  (No Label)  50
/application/shipping.max-batch  prod        200
/application/catalog.timeout     prod        PT9S
~~~

Yêu cầu:

1. Chỉ tải nhóm key `shipping.*`.
2. Chọn (No Label) rồi override `prod` theo active profile.
3. Trong Spring, tên property phải là `shipping.timeout` và `shipping.max-batch`.
4. Không nạp `catalog.timeout`.
5. Kiểm tra kết quả dự kiến khi chạy `dev` và `prod`.

Cấu hình gợi ý (giả sử luôn kích hoạt đúng một profile môi trường):

~~~yaml
spring:
  config:
    import: azureAppConfiguration
  cloud:
    azure:
      appconfiguration:
        stores:
          - endpoint: "${AZURE_APPCONFIG_ENDPOINT}"
            selects:
              - key-filter: "/application/shipping.*"
                label-filter: ',${spring.profiles.active}'
            trim-key-prefix:
              - "/application/"
~~~

**Kết quả kỳ vọng:**

| Profile | `shipping.timeout` | `shipping.max-batch` | `catalog.timeout` |
| --- | --- | --- | --- |
| `dev` | `PT5S` (fallback) | `50` (fallback) | Không được nạp |
| `prod` | `PT2S` | `200` | Không được nạp |

**Câu hỏi tự đánh giá:**

- Nếu chỉ dùng `label-filter=prod`, điều gì xảy ra với key không có biến thể `prod`?
- Vì sao `key-filter=/application/shipping.*` có thể khiến `shipping.timeout` biến thành `timeout` nếu thiếu trim tường minh?
- Một App Configuration Data Reader có bị cấm đọc riêng label `prod` trong cùng store chỉ nhờ filter của ứng dụng không?
- Một key-value có label `dev` được nạp khi Spring không có active profile và label-filter để trống hay không?
- Sau khi đổi giá trị ở Azure, vì sao test cần khởi động lại hoặc có cơ chế refresh để quan sát thay đổi?

Đáp án định hướng: (1) key chỉ có No Label sẽ bị bỏ qua; (2) prefix bị cắt theo bộ lọc hẹp thay vì prefix chung; (3) không, filter ứng dụng không phải biên phân quyền; (4) không, mặc định dùng (No Label); (5) vì giá trị đã nạp có thể được cache và bean không tự động cập nhật tức thì.

## 13. Tài liệu tham khảo chính thức

- [Microsoft Learn – Developer Guide for Using Spring Cloud Azure App Configuration](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/app-configuration-support): `key-filter`, `label-filter`, `trim-key-prefix`, lựa chọn theo profile và tải nhiều stores.
- [Azure SDK for Java – README App Configuration Spring starter](https://github.com/Azure/azure-sdk-for-java/blob/main/sdk/spring/spring-cloud-azure-starter-appconfiguration-config/README.md): bảng thuộc tính, `selects`, label priority, tag filter và snapshot.
- [Microsoft Learn – Azure App Configuration FAQ](https://learn.microsoft.com/en-us/azure/azure-app-configuration/faq): (No Label), Spring profile, store riêng khi cần cách ly bảo mật.
- [Microsoft Learn – Understand Azure App Configuration key-value store](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-key-value): cấu trúc key, label và phân biệt các bản ghi.
- [Microsoft Learn – App Configuration best practices](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-best-practices): quy hoạch key prefix, label và cách tổ chức cấu hình.
- [Microsoft Learn – Manage App Configuration snapshots](https://learn.microsoft.com/en-us/azure/azure-app-configuration/howto-create-snapshots): snapshot bất biến và nhu cầu trim prefix rõ ràng.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Spring `Environment`, `PropertySource` và quy tắc ưu tiên cấu hình.

Khi thiết kế cấu hình đa môi trường, hãy đọc các thuộc tính theo bốn câu hỏi: **(1) key có khớp filter, (2) label nào được chọn, (3) tên property sau trim là gì, (4) nguồn nào có quyền ưu tiên cuối cùng?** Trả lời được bốn câu hỏi này sẽ giúp dự đoán và kiểm thử cấu hình Spring Cloud Azure một cách có hệ thống.
