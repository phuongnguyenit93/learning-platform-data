# Cây cấu hình configtree: từ tên thư mục, tên tệp đến khóa và giá trị

> **Chủ đề:** Spring Boot Externalized Configuration  
> **Nhóm:** Config Data Import

## 1. Mục tiêu và bối cảnh

Trong Spring Boot, không phải cấu hình nào cũng được lưu thành từng dòng `key=value` trong `application.properties` hoặc thành các cặp khóa–giá trị trong YAML. Khi triển khai trên Kubernetes, Docker hoặc một nền tảng vận hành tập trung, thông tin cấu hình và secret thường được **mount thành các tệp riêng lẻ**. Ví dụ một tệp chứa username, một tệp chứa password; tên tệp định danh thuộc tính, còn nội dung tệp chính là giá trị.

Spring Boot hỗ trợ nguồn cấu hình kiểu **configuration tree**, gọi bằng prefix `configtree:` trong `spring.config.import`. Cơ chế này biến cấu trúc thư mục và tệp thành các thuộc tính có thể đọc qua Spring `Environment` hoặc bind vào `@ConfigurationProperties`.

Sau bài này, bạn sẽ hiểu:

- Gốc của một `configtree:` là **thư mục** nào, và vì sao chọn gốc quyết định tên khóa.
- Cách tên tệp và các thư mục con được chuyển thành tên property, kể cả tệp có dấu chấm.
- Vì sao **nội dung của tệp** trở thành value, thay vì được phân tích như một file properties/YAML.
- Cách import config tree, dùng giá trị trong ứng dụng, xử lý thiếu thư mục, nguồn trùng khóa và triển khai secret bằng volume.
- Các lỗi vận hành thường gặp khi làm việc với cấu hình dạng tệp.

## 2. Mô hình cơ bản: một tệp, một thuộc tính

Giả sử môi trường chạy có cấu trúc:

~~~text
/run/secrets/
├── payment.username
├── payment.password
└── payment.endpoint
~~~

Nội dung từng tệp là:

~~~text
/run/secrets/payment.username  ->  service-user
/run/secrets/payment.password  ->  <giá trị bí mật>
/run/secrets/payment.endpoint  ->  https://payment.internal
~~~

Trong `application.yml` của ứng dụng:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Khi Spring Boot nạp config tree ở thời điểm khởi động, các file trong cây sẽ cung cấp các khóa tương ứng:

| Tệp trong cây | Tên property | Giá trị property |
| --- | --- | --- |
| `payment.username` | `payment.username` | Nội dung tệp, ví dụ `service-user` |
| `payment.password` | `payment.password` | Nội dung bí mật trong tệp |
| `payment.endpoint` | `payment.endpoint` | `https://payment.internal` |

Code ứng dụng có thể truy cập:

~~~java
String username = environment.getProperty("payment.username");
String endpoint = environment.getProperty("payment.endpoint");
~~~

Điểm cần phân biệt:

1. Tên tệp (và thư mục con nếu có) quyết định **khóa**.
2. Nội dung tệp quyết định **giá trị**.
3. Tên `configtree:` chỉ ra **cơ chế đọc cấu hình** cho Spring Boot.
4. `application.yml` chứa khai báo import vẫn là một nguồn config data riêng; cấu hình của tree được đưa vào `Environment` theo quy tắc ưu tiên của config data.

**Không cần** tạo tệp `payment.username.properties` hay chèn dòng `payment.username=service-user` vào mỗi tệp. Với config tree, toàn bộ nội dung của file là value.

## 3. Từ đường dẫn đến tên property

### 3.1. Chọn đúng gốc import

Ví dụ hệ thống tệp:

~~~text
/etc/app-config/
└── inventory/
    ├── host
    ├── port
    └── credentials/
        ├── username
        └── password
~~~

Import từ gốc cha:

~~~properties
spring.config.import=configtree:/etc/app-config/
~~~

Các tên property được tạo theo phần đường dẫn **tương đối với thư mục gốc**:

| Đường dẫn tương đối trong cây | Khóa nhận được |
| --- | --- |
| `inventory/host` | `inventory.host` |
| `inventory/port` | `inventory.port` |
| `inventory/credentials/username` | `inventory.credentials.username` |
| `inventory/credentials/password` | `inventory.credentials.password` |

Nếu đổi gốc import thành:

~~~properties
spring.config.import=configtree:/etc/app-config/inventory/
~~~

thì prefix `inventory.` không còn trong khóa được tạo. Các tệp giống hệt ở trên cho ra `host`, `port`, `credentials.username` và `credentials.password`. Vì thế, **việc chọn đường dẫn gốc là một quyết định thiết kế tên property**, không đơn thuần là chọn thư mục có tồn tại.

Trong ví dụ này, để bind vào cấu hình có prefix `inventory`, import từ `/etc/app-config/`; hoặc tổ chức lại tên file/thư mục phù hợp nếu chọn gốc sâu hơn.

### 3.2. Tên file chứa dấu chấm

Spring Boot có thể ánh xạ dấu chấm trong tên file thành dấu chấm trong property key. Ví dụ cây:

~~~text
/etc/config/
├── spring.datasource.username
├── spring.datasource.password
└── service/
    └── timeout
~~~

Với:

~~~properties
spring.config.import=configtree:/etc/config/
~~~

các property có tên:

~~~text
spring.datasource.username
spring.datasource.password
service.timeout
~~~

Đây là lý do Kubernetes Secret thường được mount bằng các file có tên khớp trực tiếp với Spring property, ví dụ `spring.datasource.password`. Tệp `spring.datasource.password` **không cần** chứa chuỗi `spring.datasource.password=...`; nó chỉ cần chứa giá trị password.

### 3.3. Đường dẫn khác nhau có thể cùng tạo một tên khóa

Một ví dụ cần tránh trong cùng vùng cấu hình:

~~~text
/etc/config/
├── service.timeout
└── service/
    └── timeout
~~~

Cả hai cách biểu diễn đều nhắm tới tên `service.timeout`. Đừng dựa vào một thứ tự duyệt file không được bạn kiểm soát để giải quyết xung đột này. Thiết kế cây sao cho **mỗi property có một đường dẫn tệp rõ ràng**, hoặc xác định rõ vị trí import nào chịu trách nhiệm cho khóa đó.

### 3.4. Tệp là giá trị, thư mục là cấu trúc tên

Không nên nhầm tên thư mục với một namespace được export độc lập hay một đối tượng Java tự tạo. Cây:

~~~text
/etc/config/
└── mail/
    ├── host
    └── port
~~~

tạo `mail.host` và `mail.port`. Nó không có nghĩa là tồn tại một file hoặc một scalar property có tên `mail`. Spring có thể dùng prefix `mail` để bind các property con vào một object, nhưng đó là việc **binding các khóa**, khác với việc config tree tạo một value cho chính thư mục.

## 4. Cú pháp import bằng Spring Boot

### 4.1. Import một thư mục

Trong `src/main/resources/application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/myapp/config/"
~~~

Hoặc trong `application.properties`:

~~~properties
spring.config.import=configtree:/etc/myapp/config/
~~~

Một số điểm về cú pháp:

- Prefix **`configtree:`** chỉ định Spring Boot đọc theo kiểu cây tệp.
- Phần sau là vị trí thư mục chứa các file cấu hình.
- Nên kết thúc đường dẫn thư mục bằng `/` để thể hiện rõ đây là một directory location.
- Đường dẫn như `/etc/myapp/config/` là ví dụ cho Linux/container; trên máy phát triển và Windows phải thay bằng vị trí tương ứng.
- Khai báo ở `application.yml` hoặc `application.properties` phải **được Spring Boot tìm thấy từ trước**, rồi mới có thể thực hiện import.

### 4.2. Thư mục có thể không tồn tại: `optional:`

Nếu ứng dụng có thể chạy mà không có volume secret trong môi trường phát triển, dùng:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Ý nghĩa:

- Có thư mục hợp lệ: Spring Boot nhập các key/value của config tree.
- Không có vị trí import: phần import này có thể bị bỏ qua thay vì khiến startup thất bại vì thiếu config data.
- `optional:` **không làm cho một bí mật bắt buộc trở thành an toàn khi bị thiếu**. Nếu code yêu cầu password, nên kiểm tra cấu hình bắt buộc và báo lỗi rõ ràng khi không có giá trị.

Nếu môi trường production **bắt buộc** phải mount secret, có thể bỏ `optional:` để thiếu vị trí cấu hình trở thành lỗi khởi động dễ phát hiện:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Khi dữ liệu bắt buộc là một **khóa** cụ thể, dù thư mục đã tồn tại, vẫn cần validation ở ứng dụng để phát hiện key thiếu hoặc value rỗng.

### 4.3. Đường dẫn tuyệt đối và tương đối

Hai biểu thức này phụ thuộc vào ngữ cảnh khác nhau:

~~~properties
spring.config.import=configtree:/etc/myapp/config/
~~~

~~~properties
spring.config.import=optional:configtree:./config/secret-tree/
~~~

Ví dụ thứ hai dùng thư mục tương đối với working directory của tiến trình. Khi chạy từ IDE, bằng `java -jar` ở terminal khác hoặc từ container có `WORKDIR` khác, `./config/secret-tree/` có thể trỏ tới thư mục khác. Vì vậy, với secret volume trong môi trường triển khai, đường dẫn tuyệt đối thường dễ quan sát và quản lý hơn.

### 4.4. Import nhiều cây cấu hình

Có thể khai báo nhiều vị trí config tree, chẳng hạn:

~~~properties
spring.config.import=\
  optional:configtree:/etc/myapp/defaults/,\
  configtree:/run/secrets/
~~~

Đây là cách ghi một property Java `.properties` qua nhiều dòng bằng dấu nối dòng `\`. Khi nhiều vị trí import định nghĩa cùng khóa, **quy tắc thứ tự config data quyết định value thắng**; với nhiều imports được liệt kê trong cùng một khai báo, các imports phía sau thường được ưu tiên hơn các imports phía trước.

Ví dụ: `/etc/myapp/defaults/api.timeout` chứa `10s`, còn `/run/secrets/api.timeout` chứa `20s`. Khi import thành công theo thứ tự trên và không có nguồn ưu tiên cao hơn, `api.timeout` nhận `20s`. Đối với secret như password, nên tránh cùng đặt giá trị không rõ nguồn ở nhiều vị trí để người vận hành dễ xác định hệ thống đang dùng cấu hình nào.

## 5. Config tree khác import file YAML/properties thế nào?

Hai khai báo sau **không tương đương**:

~~~properties
# Đọc nội dung file như một tài liệu cấu hình.
spring.config.import=file:/etc/myapp/extra.yml
~~~

~~~properties
# Đọc tên file và nội dung của từng file trong một thư mục.
spring.config.import=configtree:/etc/myapp/secrets/
~~~

Với `file:/etc/myapp/extra.yml`, Spring Boot đọc YAML và diễn giải cấu trúc khóa/giá trị bên trong:

~~~yaml
payment:
  username: service-user
  endpoint: https://payment.internal
~~~

Với `configtree:/etc/myapp/secrets/`, Spring Boot đọc các file riêng lẻ:

~~~text
/etc/myapp/secrets/
├── payment.username   # file chứa: service-user
└── payment.endpoint   # file chứa: https://payment.internal
~~~

Hai cách có thể tạo những property **cùng tên** trong `Environment`, nhưng cách đóng gói, cập nhật và mount cấu hình hoàn toàn khác nhau.

Nếu trong config tree có tệp tên `application.yml` mà nội dung là:

~~~yaml
payment:
  username: service-user
~~~

thì file đó **không tự được parse như một YAML document** chỉ vì tên nó kết thúc bằng `.yml`. Theo cơ chế config tree, file được ánh xạ từ tên file và nội dung là value cho khóa tương ứng. Muốn Spring nạp YAML đúng nghĩa, hãy dùng một import theo kiểu file/config data phù hợp.

Ngoài ra, việc Java code gọi `Files.readString(...)` để đọc một file trong thư mục không tự đăng ký một property source với Spring. `spring.config.import` đưa dữ liệu vào quy trình config-data loading của Boot.

## 6. Đọc giá trị từ Environment

Sau khi import:

~~~text
/run/secrets/
├── warehouse.api-key
├── warehouse.endpoint
└── warehouse.retry-count
~~~

một service có thể đọc:

~~~java
package com.example.warehouse;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class WarehouseSettings {

    private final Environment environment;

    public WarehouseSettings(Environment environment) {
        this.environment = environment;
    }

    public String endpoint() {
        return environment.getRequiredProperty("warehouse.endpoint");
    }

    public int retryCount() {
        return environment.getRequiredProperty(
                "warehouse.retry-count", Integer.class);
    }
}
~~~

`Environment` thực hiện tra cứu qua các nguồn theo precedence, nên giá trị trả về có thể đến từ config tree hoặc từ một nguồn có ưu tiên cao hơn. `getRequiredProperty(...)` báo lỗi khi không có property; với kiểu `Integer`, Spring dùng conversion phù hợp và lỗi nếu value không thể chuyển đổi.

Ví dụ inject trực tiếp bằng `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class WarehouseClientSettings {

    private final String endpoint;

    public WarehouseClientSettings(
            @Value("${warehouse.endpoint}") String endpoint) {
        this.endpoint = endpoint;
    }

    public String getEndpoint() {
        return endpoint;
    }
}
~~~

Đây là cách truy cập giá trị cho **một khóa**. Khi cấu hình có nhiều khóa chung prefix, `@ConfigurationProperties` giúp gom, đặt kiểu và xác thực dữ liệu dễ hơn.

## 7. Binding thành object bằng `@ConfigurationProperties`

Ví dụ một cây:

~~~text
/etc/myapp/config/
└── warehouse/
    ├── endpoint
    ├── retry-count
    └── enabled
~~~

Spring Boot tạo các property `warehouse.endpoint`, `warehouse.retry-count` và `warehouse.enabled`. Trong ứng dụng Spring Boot 3 có Java 17+:

~~~java
package com.example.warehouse;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "warehouse")
public record WarehouseProperties(
        String endpoint,
        int retryCount,
        boolean enabled
) {}
~~~

Kích hoạt scanning tại ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class WarehouseApplication {
    public static void main(String[] args) {
        SpringApplication.run(WarehouseApplication.class, args);
    }
}
~~~

Một service chỉ cần inject bean:

~~~java
import org.springframework.stereotype.Service;

@Service
public class WarehouseService {
    private final WarehouseProperties properties;

    public WarehouseService(WarehouseProperties properties) {
        this.properties = properties;
    }

    public String endpoint() {
        return properties.endpoint();
    }
}
~~~

Spring Boot có thể chuyển các value dạng text từ file thành những kiểu cấu hình thông thường như số nguyên hoặc boolean thông qua cơ chế binding. Ví dụ nội dung tệp `retry-count` là `3` và `enabled` là `true`.

Để yêu cầu cấu hình bắt buộc và ràng buộc format, kết hợp Bean Validation với `@Validated`, các annotation constraint tương ứng và dependency validation thích hợp. Đừng chỉ dựa vào việc volume tồn tại rồi cho rằng các giá trị đều hợp lệ.

### 7.1. Tên property trong file và tên trường Java

Ví dụ `warehouse.retry-count` có thể bind vào `retryCount` nhờ relaxed binding của Spring Boot. Khi thiết kế tên file nên dùng quy ước ổn định, dễ đọc, phù hợp hệ thống mount volume. Đừng dựa vào relaxed binding để che giấu sự không nhất quán của tên key trong nhiều môi trường.

### 7.2. Byte content và việc biểu diễn giá trị

Tệp trong config tree có thể chứa dữ liệu text hoặc bytes; Spring Boot hỗ trợ lấy dữ liệu dạng `String` và, với trường hợp phù hợp, dạng `byte[]`. Ví dụ certificate, key hoặc password được mount từ Kubernetes Secret có thể chứa ký tự xuống dòng hoặc bytes không phù hợp để in ra log.

Với cấu hình dạng text:

- Xác định encoding nhất quán, thường dùng UTF-8 khi tạo tệp.
- Chú ý script tạo file: `echo` thường thêm newline, còn `printf %s` có thể ghi mà không thêm newline.
- Không mặc định Spring Boot sẽ luôn cắt mọi khoảng trắng hoặc newline cuối file theo cách bạn mong muốn. Hãy kiểm soát nội dung ngay tại nguồn và kiểm tra hành vi của consumer thực tế.

Với dữ liệu nhị phân, bind vào kiểu dữ liệu phù hợp và xử lý theo API tương ứng; không ép giả thành text UTF-8 nếu không có cơ sở.

## 8. Ví dụ ứng dụng dùng Kubernetes Secret

Một cách phổ biến để cung cấp credential mà không đặt trực tiếp giá trị trong `application.yml` là mount Kubernetes Secret thành volume.

Giả sử Secret có hai key:

~~~text
spring.datasource.username
spring.datasource.password
~~~

Kubernetes có thể đưa các key này thành hai file trong mount:

~~~text
/etc/secrets/db/
├── spring.datasource.username
└── spring.datasource.password
~~~

Ứng dụng Spring Boot dùng:

~~~yaml
spring:
  config:
    import: "configtree:/etc/secrets/db/"
~~~

Khi import, hai tên file trở thành:

~~~properties
spring.datasource.username=<nội dung file username>
spring.datasource.password=<nội dung file password>
~~~

Những dòng trên chỉ minh họa tên property, **không phải** nội dung cần ghi vào mỗi file. Trong volume, file username chỉ chứa username, file password chỉ chứa password.

Ví dụ manifest Kubernetes rút gọn:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: warehouse-app
spec:
  containers:
    - name: app
      image: registry.example.com/warehouse:1.0
      volumeMounts:
        - name: db-secrets
          mountPath: /etc/secrets/db
          readOnly: true
  volumes:
    - name: db-secrets
      secret:
        secretName: warehouse-db
~~~

Manifest giả định Secret `warehouse-db` **đã được tạo** với các key cần thiết. Ví dụ `image` là tên minh họa, không phải một image có sẵn để triển khai. Việc mount volume này chỉ bảo đảm các file xuất hiện đúng nơi nếu môi trường Kubernetes và Secret đã cấu hình thành công; ứng dụng vẫn cần khai báo `spring.config.import` tương ứng.

Trong môi trường thực tế:

- Nếu có nhiều Secret hoặc ConfigMap, dùng các mount path khác nhau, rồi import những cây cần thiết.
- Bảo vệ quyền đọc file tại container; chỉ thành phần cần thiết mới nên truy cập secret.
- Không lưu các bí mật thực vào Git hoặc ảnh chụp/log của môi trường.
- Không coi việc Kubernetes cập nhật Secret trên volume là bằng chứng Spring Boot sẽ tự rebind mọi bean đang chạy. Config data được nạp trong vòng đời khởi động; muốn áp dụng thay đổi động cần một cơ chế refresh/restart đã được thiết kế và kiểm chứng.

## 9. Quy tắc ưu tiên khi có khóa trùng nhau

Ví dụ trong `application.yml`:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"

payment:
  endpoint: "https://default.example"
~~~

Và file:

~~~text
/run/secrets/payment.endpoint
~~~

chứa:

~~~text
https://live.payment.internal
~~~

Trong cơ chế config data của Boot, dữ liệu import có thể ghi đè cấu hình trong tài liệu khai báo import. Vì vậy, khi không có nguồn ưu tiên cao hơn, `payment.endpoint` thường nhận giá trị từ config tree là `https://live.payment.internal`.

Tuy nhiên, config tree chỉ là **một nguồn config data** trong hệ thống externalized configuration. Các nguồn như biến môi trường, Java system properties hoặc tham số dòng lệnh có thể có ưu tiên cao hơn config data. Ví dụ chạy:

~~~bash
java -jar warehouse-app.jar \
  --payment.endpoint=https://override.example
~~~

thì tham số dòng lệnh thường thắng nếu ứng dụng giữ cơ chế command-line properties mặc định.

Khi thấy giá trị bất ngờ, cần xác định:

1. Có đúng thư mục/tên file và nội dung không?
2. `spring.config.import` đã được Boot nạp chưa?
3. Có thêm profile-specific document hoặc import khác đặt cùng khóa không?
4. Có biến môi trường, system property, command-line argument hoặc custom `PropertySource` ghi đè không?
5. Code đọc giá trị từ `Environment` nào và ở thời điểm nào?

Không suy luận chỉ từ tên file. Spring Boot giải quyết property trên **tổng thể các nguồn cấu hình** theo thứ tự ưu tiên.

## 10. Nhiều cây, wildcard và thứ tự import

Giả sử các nhóm cấu hình được mount:

~~~text
/etc/config/
├── database/
│   ├── spring.datasource.username
│   └── spring.datasource.password
└── messaging/
    ├── messaging.url
    └── messaging.timeout
~~~

Có thể import riêng từng thư mục:

~~~properties
spring.config.import=\
  configtree:/etc/config/database/,\
  configtree:/etc/config/messaging/
~~~

Các tệp trong từng thư mục khi đó tạo property **tính từ gốc tương ứng**. Vì tên file đã có prefix đầy đủ (`spring.datasource.*` và `messaging.*`), việc chọn gốc con là hợp lý trong ví dụ này.

Với nhiều thư mục con được tạo động, có thể sử dụng mẫu wildcard được Boot hỗ trợ, ví dụ:

~~~properties
spring.config.import=optional:configtree:/etc/config/*/
~~~

Mẫu này hướng tới các thư mục con trực tiếp nằm dưới `/etc/config/`. Các wildcard import thường được xử lý theo thứ tự đường dẫn tuyệt đối được sắp xếp để cho kết quả ổn định; nếu **cần thứ tự ưu tiên riêng giữa những cây có khóa trùng nhau**, nên liệt kê từng import một cách tường minh.

Không dùng wildcard để thay thế việc hiểu namespace của từng thư mục: import `/etc/config/*/` có các gốc là từng thư mục con, còn import `/etc/config/` dùng một gốc chung và có thể dẫn tới tên property chứa thêm các segment thư mục. Hãy dựa trên **khóa mong muốn** để chọn cách import.

## 11. Thực hành cục bộ từ đầu đến cuối

### 11.1. Tạo config tree giả lập

Trên Linux/macOS, chạy tại thư mục project:

~~~bash
mkdir -p ./local-secrets/catalog

printf '%s' 'https://catalog.internal' \
  > ./local-secrets/catalog/catalog.endpoint

printf '%s' '5' \
  > ./local-secrets/catalog/catalog.retry-count
~~~

Cây tạo ra:

~~~text
local-secrets/
└── catalog/
    ├── catalog.endpoint
    └── catalog.retry-count
~~~

Tệp `catalog.endpoint` chứa URL, tệp `catalog.retry-count` chứa số `5` dưới dạng text.

### 11.2. Import vào Spring Boot

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:./local-secrets/catalog/"

catalog:
  endpoint: "https://fallback.invalid"
  retry-count: 1
~~~

Với working directory là gốc dự án, khi hai file tồn tại, các property import sẽ được dùng theo precedence của config data. Nếu không có thư mục import, `optional:` cho phép Boot tiếp tục và dùng các giá trị mặc định trong `application.yml`.

Ví dụ component đọc cấu hình:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogSettings(String endpoint, int retryCount) {}
~~~

Khi đã bật `@ConfigurationPropertiesScan`, inject `CatalogSettings` và truy cập `endpoint()`, `retryCount()`. Cặp value mong đợi khi có cây đã nêu là URL của file và số `5`.

### 11.3. Thử nghiệm từng biến thể

1. Xóa hoặc đổi tên tệp `catalog.retry-count` rồi khởi động lại: chỉ riêng khóa này sẽ dùng fallback `1` từ YAML nếu không có nguồn nào khác ghi đè.
2. Đổi nội dung file thành số hợp lệ khác rồi khởi động lại: giá trị mới được bind.
3. Đổi tên file `catalog.endpoint` thành `endpoint`: với gốc `./local-secrets/catalog/`, tên property trở thành `endpoint` thay vì `catalog.endpoint`; bean có prefix `catalog` sẽ không lấy được từ file này.
4. Đổi vị trí import sang `configtree:./local-secrets/`: phần tên thư mục `catalog` trở thành một segment của khóa; khi đó file `catalog/catalog.endpoint` có thể tạo `catalog.catalog.endpoint`, không còn là `catalog.endpoint`.
5. Thử thêm tham số `--catalog.retry-count=8` khi chạy ứng dụng: kiểm tra trường hợp CLI có ưu tiên cao hơn config data.

Để tránh nhầm lẫn giữa giá trị do file tree cung cấp và giá trị fallback, chỉ thực hiện từng thay đổi một và khởi động lại ứng dụng giữa các lượt thử.

### 11.4. Thử lỗi bắt buộc và tùy chọn

Nếu đang dùng `optional:configtree:./local-secrets/catalog/`, hãy đổi tên thư mục để import không còn tìm thấy. Ứng dụng có thể vẫn khởi động bằng fallback nếu các property đều có giá trị thay thế.

Sau đó bỏ `optional:`, thử khởi động khi không có thư mục. Spring Boot sẽ báo lỗi do vị trí config data bắt buộc bị thiếu. Với secret production, kiểu lỗi sớm này thường hữu ích hơn việc âm thầm chạy với credential rỗng.

## 12. Chẩn đoán khi không thấy property trong config tree

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Environment.getProperty("catalog.endpoint")` trả về `null` | Chọn sai gốc import, sai tên tệp hoặc không có vị trí import | So sánh tên property với đường dẫn tương đối từ root |
| Giá trị vẫn là default từ YAML | Cây chưa được import hoặc có nguồn khác ưu tiên hơn | Kiểm tra declaration `spring.config.import` và property sources |
| Khởi động lỗi do thiếu vị trí | Import bắt buộc nhưng thư mục không tồn tại/không truy cập được | Kiểm tra mount path, quyền đọc, cân nhắc `optional:` nếu phù hợp |
| Value có ký tự không mong muốn | Nội dung tệp chứa newline/space hoặc encoding không khớp | Kiểm tra bytes thực tế của file theo cách an toàn |
| Một file chứa `foo=bar` nhưng property `foo` không xuất hiện | Config tree coi toàn bộ nội dung tệp là value; nó không parse properties | Đặt tên file là `foo`, nội dung chỉ `bar` |
| Cùng key được thấy nhưng value khác | Trùng key trong nhiều imports hoặc nguồn như CLI/env | Kiểm tra thứ tự import và nguồn có ưu tiên cao hơn |
| Runtime thay Secret nhưng bean vẫn dùng giá trị cũ | Không có cơ chế reload/rebind phù hợp | Thiết kế restart hoặc refresh có kiểm soát |
| Bind `int`/`boolean` lỗi | Nội dung file không chuyển đổi được sang kiểu đích | Kiểm tra format value và validation |

Với khóa **không nhạy cảm**, một đoạn chẩn đoán đơn giản:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigTreeProbe implements ApplicationRunner {

    private final Environment environment;

    public ConfigTreeProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments arguments) {
        System.out.println("catalog.retry-count = "
                + environment.getProperty("catalog.retry-count"));
    }
}
~~~

Chỉ dùng khóa demo để quan sát. Không in giá trị `*.password`, token, private key hoặc toàn bộ nội dung `Environment` ra log. Nếu dùng Actuator `env`/`configprops` để hỗ trợ chẩn đoán, phải bảo vệ endpoint và cấu hình cơ chế che giấu giá trị nhạy cảm.

Ở phía OS/container, kiểm tra thư mục mount thực tế và quyền đọc bằng những lệnh quan sát phù hợp. Ví dụ trong môi trường Linux, `ls -la /run/secrets` cho biết tên file và quyền, nhưng không cần in secret values vào terminal hoặc CI log. Khi dùng Kubernetes, đối chiếu key của Secret với tên file được mount, tên mount path, và container mà ứng dụng thực sự chạy.

## 13. Các nguyên tắc vận hành và bảo mật

**Tách cấu hình triển khai khỏi bản build.** Dữ liệu như endpoint, credential hoặc key material có vòng đời khác code. Mount file hoặc lấy từ hệ thống quản lý secret giúp không phải rebuild JAR mỗi lần thay thông tin vận hành.

**Giới hạn truy cập.** Một config tree chứa secret có thể bị đọc bởi mọi process có quyền đọc file. Thiết lập filesystem permissions, container identity và chính sách access phù hợp. Không commit trực tiếp giá trị bí mật vào Git hoặc ghi ra artifact build.

**Không lạm dụng dấu `optional:`.** Dùng nó cho cấu hình thực sự tùy chọn, và xác thực riêng các thuộc tính bắt buộc. Với môi trường production yêu cầu secret để hoạt động, cần lỗi rõ ràng khi thiếu.

**Kiểm soát cách tạo nội dung file.** Script, ConfigMap hoặc Secret generator có thể thêm newline hoặc encoding không phù hợp. Với những giá trị yêu cầu format chặt, hãy kiểm tra ở nguồn và ràng buộc khi bind.

**Xác định cách cập nhật runtime.** Import config tree qua config data không đồng nghĩa với khả năng tự phát hiện mọi thay đổi và tự cập nhật trạng thái bean đã khởi tạo. Hãy quy định rõ quy trình restart, rollout hoặc giải pháp reload/refresh được hỗ trợ trong hệ thống.

**Cấu trúc tên nhất quán.** Khi nhiều nhóm sở hữu chung một folder volume, quy ước prefix và naming giảm nguy cơ file trùng khóa. Đặt tên file theo property cần cung cấp và xác nhận gốc import ở từng môi trường.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Có tệp `/etc/settings/order/timeout` chứa `25s`, ứng dụng import `configtree:/etc/settings/`. Property nào được tạo?  
**Đáp án:** `order.timeout`, giá trị là nội dung tệp `25s`.

**Câu 2.** Vẫn tệp đó, nhưng ứng dụng import `configtree:/etc/settings/order/`. Property nào được tạo?  
**Đáp án:** `timeout`. Prefix `order.` không còn vì `order/` đã trở thành thư mục gốc.

**Câu 3.** Tệp `/run/secrets/db.password` chứa chuỗi `db.password=hunter2`. Value của property `db.password` là gì?  
**Đáp án:** Toàn bộ chuỗi `db.password=hunter2` (có thể kèm newline tùy nội dung file), **không chỉ** `hunter2`. Vì config tree không tự parse cú pháp properties.

**Câu 4.** `application.yml` khai báo `app.mode=local` và import `configtree:/run/config/`, ở đó file `app.mode` chứa `cluster`. Nếu không có nguồn ưu tiên cao hơn, giá trị nào thường thắng?  
**Đáp án:** `cluster` từ import.

**Câu 5.** Một file Secret được cập nhật trong volume Kubernetes. Có chắc một service đã inject `@ConfigurationProperties` từ lúc startup tự nhận giá trị mới không?  
**Đáp án:** Không thể chắc. Cần một quy trình restart/refresh hoặc cơ chế cập nhật phù hợp đã được thiết kế và xác nhận.

## 15. Ghi nhớ

- `configtree:` là một dạng **Config Data Import**: mỗi file trong cây là một property, tên file và đường dẫn tương đối từ gốc tạo thành key, nội dung file tạo thành value.
- Chọn đúng **root directory** quyết định có hay không có các prefix thư mục trong key. Tên file chứa dấu chấm vẫn có thể biểu diễn key dạng `a.b.c`.
- Dùng `spring.config.import=configtree:/path/` để nạp cây bắt buộc; thêm `optional:` khi cho phép thiếu vị trí import.
- Config tree **khác** việc nạp một YAML/properties file và khác việc đọc file trực tiếp trong code. Nó tham gia precedence của Spring Boot và có thể bind qua `Environment`, `@Value`, `@ConfigurationProperties`.
- Kubernetes Secret/ConfigMap dạng mounted files là trường hợp phổ biến. Cần quản lý quyền đọc, format bytes/newline, tên key, thứ tự imports và chính sách cập nhật runtime.

## Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration, Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree): cách import cây cấu hình, property name và nội dung file.
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): cú pháp `spring.config.import`, `optional:` và precedence.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding cấu hình có cấu trúc.
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret keys được cung cấp qua volume trong container.
