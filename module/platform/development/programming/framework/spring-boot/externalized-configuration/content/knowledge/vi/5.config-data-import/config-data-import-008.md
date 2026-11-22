# Nạp tệp không có phần mở rộng bằng gợi ý `[.properties]` hoặc `[.yaml]` trong Spring Boot

## 1. Bối cảnh: tệp cấu hình không có đuôi mở rộng

Spring Boot hỗ trợ nạp cấu hình ngoài từ tệp Java Properties (`.properties`), YAML (`.yaml` hoặc `.yml`) và các loại nguồn config data khác. Thông thường, phần mở rộng của tên tệp giúp Spring Boot xác định cách đọc nội dung:

~~~text
/etc/my-service/application.properties  → Java Properties
/etc/my-service/application.yaml        → YAML
~~~

Nhưng khi chạy trên Docker, Kubernetes hoặc một nền tảng cloud, nội dung cấu hình có thể được mount thành **tệp không có phần mở rộng**, chẳng hạn:

~~~text
/etc/config/
└── runtimeconfig
~~~

Tệp `runtimeconfig` có thể chứa YAML hợp lệ:

~~~yaml
app:
  endpoint: https://api.example.test
  timeout: 8s
  enabled: true
~~~

Vấn đề là đường dẫn `/etc/config/runtimeconfig` không cho Spring Boot biết nên dùng bộ đọc YAML hay Properties. Khi khai báo import một file trực tiếp, cơ chế config data cần nhận diện định dạng để phân tích các cặp property.

Spring Boot giải quyết việc đó bằng **extension hint**: một gợi ý định dạng nằm trong dấu ngoặc vuông ngay sau đường dẫn import.

~~~properties
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

Ở đây tệp thật **vẫn tên là `runtimeconfig`**. Chuỗi `[.yaml]` là chỉ dẫn cho Spring Boot về định dạng nội dung; không phải phần tên file được bổ sung trên đĩa.

## 2. Extension hint là gì?

**Extension hint** là hậu tố cú pháp `[.extension]` gắn vào một **config data import location** để cho Spring Boot biết phải dùng bộ phân tích định dạng nào khi tệp thực tế không có đuôi mở rộng.

Hai cách quan trọng nhất:

| Nội dung tệp thực tế | Hậu tố gợi ý | Import location |
| --- | --- | --- |
| Các dòng `key=value` hoặc `key: value` theo định dạng Java Properties | `[.properties]` | `file:/etc/config/settings[.properties]` |
| YAML có cấu trúc phân cấp | `[.yaml]` | `file:/etc/config/settings[.yaml]` |

Cú pháp tổng quát:

~~~text
spring.config.import=[optional:]file:<đường-dẫn-tệp-không-đuôi>[.properties]
spring.config.import=[optional:]file:<đường-dẫn-tệp-không-đuôi>[.yaml]
~~~

Thay `<đường-dẫn-tệp-không-đuôi>` bằng path cụ thể, ví dụ `/etc/config/settings` hoặc `./external/runtimeconfig`.

Giải thích các thành phần:

- `spring.config.import`: yêu cầu Spring Boot nạp thêm tài liệu cấu hình từ một location.
- `file:`: chỉ định tài nguyên trên hệ thống tệp của tiến trình đang chạy.
- `optional:`: cho phép location không tồn tại mà không làm fail startup chỉ vì thiếu location.
- `[.yaml]` hoặc `[.properties]`: gợi ý **định dạng nội dung**.
- Nội dung nằm trong ngoặc vuông **không** phải cú pháp array của YAML hay cú pháp biểu diễn một property riêng.

**Sai lầm thường gặp:** tạo file `settings[.yaml]` trên filesystem để khớp chính xác chuỗi import. Không cần làm vậy; file thật chỉ có tên `settings`.

## 3. Ví dụ 1: import tệp YAML không có phần mở rộng

Giả sử dự án Spring Boot có:

~~~text
src/main/resources/
└── application.yml

# Thư mục làm việc khi chạy JAR
./
├── app.jar
└── external/
    └── runtimeconfig          # file không có phần mở rộng
~~~

### Bước 1 — Cấu hình mặc định trong JAR

File `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: config-demo
  config:
    import: "optional:file:./external/runtimeconfig[.yaml]"

server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  timeout: 3s
  retries: 2
~~~

Dòng import cho biết: hãy đọc `./external/runtimeconfig` như YAML nếu file này tồn tại.

### Bước 2 — Tạo file bên ngoài không có đuôi

Nội dung **`./external/runtimeconfig`**:

~~~yaml
app:
  endpoint: https://api.example.test
  timeout: 10s
  feature:
    enabled: true
~~~

Lưu đúng tên `runtimeconfig`, **không** đổi thành `runtimeconfig.yaml`. Trên Windows, cần kiểm tra trình quản lý file có đang tự ẩn phần mở rộng hay không.

### Bước 3 — Khởi chạy

Tại working directory có JAR và thư mục `external/`:

~~~bash
java -jar app.jar
~~~

Với giả định không có property source khác ghi đè, các giá trị hiệu lực là:

| Thuộc tính | Kết quả | Giải thích |
| --- | --- | --- |
| `spring.application.name` | `config-demo` | Từ file cấu hình chung trong JAR |
| `server.port` | `8080` | File import không khai báo nên vẫn lấy giá trị mặc định |
| `app.endpoint` | `https://api.example.test` | Giá trị từ file YAML không đuôi được import |
| `app.timeout` | `10s` | File import ghi đè `3s` |
| `app.retries` | `2` | Chỉ có trong file gốc |
| `app.feature.enabled` | `true` | Giá trị mới được bổ sung từ file import |

Đây là **ghi đè theo property**, không phải thay toàn bộ cấu hình gốc bằng tài liệu mới. Nếu bỏ file `./external/runtimeconfig`, tiền tố `optional:` cho phép ứng dụng tiếp tục với các giá trị mặc định.

Nếu file tồn tại nhưng chứa YAML sai cú pháp, `optional:` **không** làm dữ liệu sai trở thành hợp lệ. Lỗi phân tích cấu hình vẫn cần được xử lý.

## 4. Ví dụ 2: import tệp Java Properties không có phần mở rộng

Giả sử nền tảng mount một tệp tên `/etc/my-service/overrides` chứa:

~~~properties
app.endpoint=https://api.example.test
app.timeout=12s
app.retries=4
logging.level.com.example=INFO
~~~

Đây là cú pháp Java Properties, vì vậy khai báo:

~~~properties
# application.properties trong JAR
spring.config.import=optional:file:/etc/my-service/overrides[.properties]
app.timeout=3s
app.retries=2
~~~

Spring Boot dùng bộ đọc Properties để nạp tệp `overrides` dù tên vật lý không kết thúc bằng `.properties`.

Cấu hình tương đương khi file chính dùng YAML:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/my-service/overrides[.properties]"

app:
  timeout: 3s
  retries: 2
~~~

Trong cả hai trường hợp, tệp nguồn được import thực sự là `/etc/my-service/overrides`. Không có yêu cầu tệp chính và tệp import phải dùng cùng một định dạng: file chính YAML có thể import file Properties và ngược lại.

**Gợi ý chọn định dạng:** dùng `[.properties]` nếu nội dung là các dòng Java Properties; dùng `[.yaml]` nếu nội dung là YAML. Đổi hint mà không đổi nội dung có thể khiến parser lỗi hoặc tạo giá trị khác dự kiến.

## 5. `[.yaml]` nằm ở đâu trong lệnh import?

Cần phân biệt **đường dẫn thực tế** với **chuỗi cấu hình location**:

~~~text
Đường dẫn trên đĩa:
  /etc/config/runtimeconfig

Chuỗi khai báo cho Spring Boot:
  file:/etc/config/runtimeconfig[.yaml]
  └file:┘└──── đường dẫn ────┘└hint┘
~~~

Ví dụ đúng:

~~~properties
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

Ví dụ sai về ý nghĩa:

~~~properties
# File thật không có đuôi; dưới đây đang tìm một tên file khác:
spring.config.import=file:/etc/config/runtimeconfig.yaml
~~~

~~~properties
# Thiếu hint nếu muốn nạp YAML từ file không đuôi:
spring.config.import=file:/etc/config/runtimeconfig
~~~

Không phải cứ file có nội dung YAML thì Spring Boot tự suy ra định dạng khi đường dẫn không có đuôi. Gợi ý trong dấu ngoặc vuông làm ý định đọc file trở nên tường minh.

Khi khai báo trong YAML, nên **đặt toàn bộ location trong dấu nháy kép** để giữ nguyên các ký tự `:`, `[` và `]` và giúp người đọc phân biệt nó với cấu trúc YAML. Khi đặt trực tiếp ở CLI, cũng nên bao location hoặc toàn bộ đối số trong dấu nháy phù hợp với shell, vì một số shell xử lý `[ ]` như cú pháp pattern.

## 6. Import cố định và import tương đối

Spring Boot hỗ trợ hai dạng location thông dụng:

### 6.1. Fixed location

Một location bắt đầu bằng scheme như `file:` hoặc `classpath:`, hoặc đường dẫn tuyệt đối theo quy tắc cấu hình, là dạng **fixed**. Ví dụ:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/config/runtimeconfig[.yaml]"
~~~

Nó trỏ tới đúng file `/etc/config/runtimeconfig` trong filesystem nơi ứng dụng chạy. Với container, đó là **filesystem bên trong container**, không phải trực tiếp host.

Một vị trí tương đối nhưng có scheme `file:` cũng thuộc dạng fixed theo cách Spring Boot phân loại import:

~~~yaml
spring:
  config:
    import: "optional:file:./external/runtimeconfig[.yaml]"
~~~

Trong ví dụ này, `./external/` được tính từ **working directory** của tiến trình. Nó không tự động tương đối với thư mục chứa `application.yml` hay thư mục chứa JAR.

### 6.2. Import-relative location

Nếu không bắt đầu bằng scheme hoặc dấu `/`, location có thể được giải quyết **tương đối với tài liệu đã khai báo import**.

Giả sử có file ngoài:

~~~text
/opt/demo/
├── application.yml
└── extra/
    └── runtimeconfig
~~~

Trong `/opt/demo/application.yml` có thể khai báo:

~~~yaml
spring:
  config:
    import: "extra/runtimeconfig[.yaml]"
~~~

Khi đó location import-relative có thể được giải quyết tương đối với `/opt/demo/application.yml`, dẫn tới file `/opt/demo/extra/runtimeconfig`.

Lưu ý: phần `[.yaml]` chỉ quyết định **cách đọc file** sau khi location được giải quyết. Nó không thay đổi quy tắc đường dẫn tương đối/cố định.

## 7. Cơ chế hoạt động khi Spring Boot khởi động

Luồng tổng quát:

~~~text
application.yml / application.properties
           |
           v
phát hiện spring.config.import
           |
           v
phân giải location và optional:
           |
           v
tách extension hint [.yaml] / [.properties]
           |
           v
tìm tài nguyên thật: /etc/config/runtimeconfig
           |
           v
chọn loader YAML / Java Properties
           |
           v
nạp document, đưa vào Config Data / Environment
           |
           v
giải quyết property theo thứ tự ưu tiên
           |
           v
@Value / @ConfigurationProperties / bean sử dụng giá trị
~~~

Cơ chế này thuộc **Config Data API** của Spring Boot, được xử lý trong giai đoạn khởi động, trước khi nhiều bean ứng dụng được tạo. Vì vậy:

- Tệp import phải tồn tại **trước hoặc tại lúc khởi động** nếu nó là bắt buộc.
- Giá trị từ tài liệu được import có thể ghi đè những giá trị trùng tên trong **tài liệu khai báo import**.
- Nếu một property source có ưu tiên cao hơn, chẳng hạn đối số dòng lệnh, cũng khai báo cùng property, nguồn ưu tiên cao hơn vẫn có thể thắng.
- Việc sửa tệp mount sau khi ứng dụng đã chạy **không tự đảm bảo** toàn bộ bean được refresh.

**Extension hint không tạo một kiểu cấu hình mới.** Nó cho phép Spring Boot dùng cùng loader YAML hoặc Properties vốn đã được hỗ trợ với file có đuôi thông thường.

## 8. Thứ tự import và quy tắc ghi đè

Ví dụ cấu hình gốc:

~~~yaml
spring:
  config:
    import: "optional:file:./runtimeconfig[.yaml]"

app:
  timeout: 3s
  region: vn
  retries: 2
~~~

File `./runtimeconfig`:

~~~yaml
app:
  timeout: 10s
  region: apac
~~~

Giá trị của `app.timeout` trở thành `10s` và `app.region` trở thành `apac`; `app.retries` vẫn là `2`.

Nếu chạy:

~~~bash
java -jar app.jar --app.timeout=20s
~~~

thì `app.timeout=20s` vì đối số dòng lệnh có ưu tiên cao hơn các config data source trong trường hợp thông thường.

Một tài liệu có thể khai báo nhiều import. Ví dụ:

~~~yaml
spring:
  config:
    import:
      - "optional:file:./defaults[.properties]"
      - "optional:file:./overrides[.yaml]"
~~~

Giả sử cả hai file đều tồn tại và khai báo `app.timeout`. Với nhiều import trong cùng một khai báo, Spring Boot xử lý theo thứ tự được liệt kê; **import sau có thể ghi đè import trước** nếu chúng cùng định nghĩa property.

Điểm này khác với việc ghi đè toàn bộ tệp: khi `overrides` không khai báo `app.region`, giá trị đến từ `defaults` hoặc file cấu hình gốc vẫn có thể được sử dụng.

Việc một location có hint hay không **không quyết định độ ưu tiên**. Thứ tự ưu tiên xuất phát từ quan hệ giữa các nguồn và các import, không phải việc chọn `[.properties]` hay `[.yaml]`.

## 9. File không đuôi có nhiều tài liệu YAML và profile

Một tệp YAML không đuôi được import với `[.yaml]` vẫn có thể chứa **nhiều tài liệu YAML** phân cách bằng `---`. Ví dụ:

~~~yaml
# /etc/config/runtimeconfig (không có phần mở rộng)
app:
  timeout: 6s
  audit-enabled: false

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 15s
  audit-enabled: true
~~~

Và trong `application.yml`:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

Nếu không có property source khác ưu tiên cao hơn:

- Khi profile `prod` không hoạt động, `app.timeout=6s` và `app.audit-enabled=false`.
- Khi profile `prod` hoạt động, tài liệu YAML thứ hai tham gia và có thể ghi đè bằng `app.timeout=15s` và `app.audit-enabled=true`.

Kích hoạt profile, chẳng hạn:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Đây là cách thực tế để có một **file mount không đuôi** nhưng chứa cấu hình có điều kiện theo profile.

Spring Boot cũng có quy tắc xét **profile-specific variants** khi import location phù hợp. Tuy nhiên, với các hệ thống mount tạo tên file tùy biến, cần kiểm tra chính xác những file thực sự được cấp và cách chúng được import. Dùng tài liệu YAML có `spring.config.activate.on-profile` trong cùng một tệp có thể giúp biểu diễn các giá trị theo profile rõ ràng khi nền tảng chỉ mount một file.

## 10. Phân biệt import file không đuôi với `configtree:`

Đây là phân biệt rất quan trọng khi dùng Kubernetes ConfigMap, Kubernetes Secret hoặc Docker secrets. Nền tảng có thể cung cấp dữ liệu mount theo **hai kiểu cấu trúc khác nhau**.

### 10.1. Một file chứa nhiều property

~~~text
/etc/config/
└── runtimeconfig
~~~

Nội dung:

~~~yaml
app:
  timeout: 10s
  feature:
    enabled: true
~~~

Dùng **import file với hint**:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

Một file cung cấp **nhiều** property nhờ parser YAML.

### 10.2. Nhiều file, mỗi file là một property

~~~text
/etc/config/
└── app/
    ├── timeout
    └── feature.enabled
~~~

Ví dụ nội dung file `timeout` là `10s`, còn file `feature.enabled` là `true`. Đây là dạng **configuration tree**, trong đó tên file có thể trở thành tên property và nội dung file trở thành giá trị.

Khi muốn đọc kiểu này, dùng:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/config/app/"
~~~

Nếu thư mục config tree là `/etc/config/app/`, Spring Boot có thể cung cấp `timeout` và `feature.enabled` tương ứng. Nếu muốn các property bắt đầu bằng `app.`, cấu trúc thư mục và điểm import cần được chọn phù hợp, ví dụ import từ `/etc/config/` khi dưới đó có thư mục con `app/`.

Bảng lựa chọn:

| Kiểu mount | Ví dụ | Cách import |
| --- | --- | --- |
| Một file không đuôi chứa toàn bộ YAML | `/etc/config/runtimeconfig` | `file:/etc/config/runtimeconfig[.yaml]` |
| Một file không đuôi chứa Java Properties | `/etc/config/runtimeconfig` | `file:/etc/config/runtimeconfig[.properties]` |
| Một thư mục chứa nhiều file, mỗi file một property | `/etc/config/app/timeout` | `configtree:/etc/config/app/` hoặc điểm gốc phù hợp |

Không nên cố dùng `file:/etc/config/app/[.yaml]` để nạp một **thư mục** theo cơ chế config tree. Extension hint dành cho **định dạng nội dung một file**, còn `configtree:` thể hiện quy ước mỗi file mang một giá trị.

## 11. Sử dụng với ConfigMap, Secret và container

### 11.1. Ví dụ ConfigMap mount một file YAML không đuôi

Một ConfigMap có thể chứa key tên `runtimeconfig`, với value là nội dung YAML:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-runtime-config
data:
  runtimeconfig: |
    app:
      timeout: 12s
      region: apac
~~~

Khi mount ConfigMap vào `/etc/config/` trong container, tệp bên trong có thể là:

~~~text
/etc/config/runtimeconfig
~~~

Nếu `application.yml` trong JAR khai báo:

~~~yaml
spring:
  config:
    import: "file:/etc/config/runtimeconfig[.yaml]"
~~~

ứng dụng có thể đọc file mount đó như YAML lúc khởi động.

Với một mount dưới dạng **Secret**, nguyên tắc kỹ thuật về extension hint vẫn giống nhau; tuy nhiên phải quản lý quyền đọc, phân phối và quay vòng secret đúng cách. Việc chuyển secret vào file ngoài JAR không tự mã hóa secret, cũng không đảm bảo ứng dụng không ghi lộ nó vào log.

### 11.2. Trong Docker

Giả sử host có file `./deploy/runtimeconfig` (không đuôi). Container được chạy với mount chỉ đọc:

~~~bash
docker run --rm \
  -v "$PWD/deploy/runtimeconfig:/etc/config/runtimeconfig:ro" \
  my-service:1.0
~~~

Ví dụ này giả định image đã có lệnh khởi động Spring Boot và file `application.yml` trong JAR chứa import `file:/etc/config/runtimeconfig[.yaml]`.

Cần hiểu:

- Spring Boot nhìn thấy **`/etc/config/runtimeconfig` bên trong container**.
- Phần `[.yaml]` không nằm trong đường dẫn mount của Docker.
- `:ro` giúp mount chỉ đọc; ứng dụng không cần ghi thay đổi vào tệp đó.
- Đối với location không có `optional:`, mount bị thiếu có thể làm ứng dụng fail startup.

Cú pháp volume mount ở trên là ví dụ cho shell Unix. Khi dùng Windows hoặc Docker Desktop, điều chỉnh cách biểu diễn đường dẫn host theo shell và môi trường đang dùng.

## 12. `optional:`, file thiếu và file sai định dạng

Hai import sau có mục đích khác nhau:

~~~properties
# Bắt buộc file phải có
spring.config.import=file:/etc/config/runtimeconfig[.yaml]
~~~

~~~properties
# File có thể không tồn tại
spring.config.import=optional:file:/etc/config/runtimeconfig[.yaml]
~~~

Nếu file **không tồn tại**:

- Với location bắt buộc, Spring Boot có thể dừng startup và báo lỗi không tìm thấy location.
- Với `optional:`, startup có thể tiếp tục với các nguồn cấu hình khác.

Nếu file **tồn tại nhưng sai định dạng**:

- `optional:` không chuyển nội dung YAML hỏng thành YAML hợp lệ.
- `[.properties]` không tự chuyển cấu trúc YAML thành Java Properties.
- Nếu mã ứng dụng yêu cầu một property bắt buộc mà file không khai báo, ứng dụng vẫn có thể fail ở bước binding hoặc validation.

Ví dụ tệp `runtimeconfig` chứa nội dung YAML sai:

~~~yaml
app:
  timeout: [unclosed
~~~

Khi import bằng `[.yaml]`, lỗi parsing vẫn cần sửa tại tệp thực tế.

Vì vậy, với môi trường production **bắt buộc có cấu hình ngoài**, nên cân nhắc location không có `optional:` và kiểm tra các giá trị yêu cầu ngay khi khởi động. `optional:` phù hợp với override dùng ở dev hoặc môi trường mà file vắng mặt là tình huống hợp lệ.

## 13. Cách truy xuất thuộc tính sau khi import

Các giá trị từ file extensionless đi vào `Environment` giống các config data thông thường. Mã Java đọc property **không cần biết** file gốc có đuôi hay có extension hint.

Ví dụ lấy bằng `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigConsumer {
    public ConfigConsumer(Environment environment) {
        String endpoint = environment.getProperty("app.endpoint");
        String timeout = environment.getProperty("app.timeout");
        System.out.println("Endpoint: " + endpoint);
        System.out.println("Timeout: " + timeout);
    }
}
~~~

Trong ứng dụng thực tế, tránh in hoặc ghi log những thuộc tính nhạy cảm như password, token và API key.

Với cấu hình có cấu trúc, có thể dùng `@ConfigurationProperties` để bind thành đối tượng Java:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(String endpoint, Duration timeout, int retries) {
}
~~~

Kết hợp `@ConfigurationPropertiesScan` ở ứng dụng để Spring Boot đăng ký và bind record trên:

~~~java
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

Nếu file import cung cấp `app.timeout: 10s`, Spring Boot có thể chuyển thành `Duration`. Cơ chế bind hoạt động theo **tên property và giá trị hiệu lực**, không phụ thuộc vào việc tài nguyên được import có phần mở rộng hay không.

## 14. Khắc phục sự cố khi import không hoạt động

Khi cấu hình trong file không đuôi không có hiệu lực, kiểm tra tuần tự:

1. **Đường dẫn thật có tồn tại?** Tìm đúng `/etc/config/runtimeconfig` trong filesystem của tiến trình. Với Docker/Kubernetes, kiểm tra đường dẫn **bên trong container**.
2. **Có vô tình thêm đuôi khi tạo file?** File thực tế `runtimeconfig.yaml` khác file `runtimeconfig`. Ngược lại, không tạo file vật lý tên `runtimeconfig[.yaml]`.
3. **Hint khớp nội dung?** YAML cần `[.yaml]`, Java Properties cần `[.properties]`. Kiểm tra lỗi tab, dấu `:`, thụt lề YAML hoặc dấu bằng trong Properties.
4. **Location đang được khai báo ở đâu?** Xác định file hoặc document chứa `spring.config.import` và nó có được Spring Boot nạp hay không.
5. **Fixed hay import-relative?** `file:./...` được giải theo working directory, còn location không có scheme có thể tương đối với file khai báo import.
6. **Có dùng `optional:`?** Nếu có, một location vắng mặt có thể bị bỏ qua; nhờ vậy startup thành công nhưng giá trị override không xuất hiện.
7. **Có profile hoặc nhiều tài liệu YAML?** Kiểm tra `spring.config.activate.on-profile` và các profile được kích hoạt.
8. **Property có bị nguồn khác ghi đè?** CLI, Java system property, environment variable hoặc một config data source có ưu tiên cao hơn có thể cấp giá trị cuối.
9. **Có yêu cầu đọc config tree thay vì một file?** Nếu mỗi file là một key, hãy xem `configtree:`.
10. **Có kỳ vọng reload động?** Spring Boot thông thường nạp config data khi khởi động; sửa file mount sau đó không mặc nhiên cập nhật mọi bean đã được tạo.

Để chẩn đoán quá trình nạp config data, có thể bật log mức TRACE cho package cấu hình trong môi trường được kiểm soát:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Nếu dùng Spring Boot Actuator và bật các endpoint liên quan với xác thực phù hợp, có thể quan sát `/actuator/env` và `/actuator/configprops` để tìm giá trị hiệu lực. Không công khai những endpoint có thể chứa metadata cấu hình hoặc dữ liệu nhạy cảm.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`[.yaml]` là một phần của tên file thật.” | Nó là **gợi ý định dạng** ở chuỗi import; file thật có thể không có đuôi. |
| “Cứ file không có đuôi là phải dùng `configtree:`.” | Dùng extension hint khi **một file chứa nhiều property**; dùng `configtree:` khi **tên file là tên property**. |
| “File chính YAML thì chỉ import được YAML.” | Một tài liệu YAML có thể import file Java Properties bằng `[.properties]`. |
| “Import file không đuôi sẽ thay toàn bộ `application.yml`.” | Nó tham gia thứ tự config data và ghi đè theo property; các property khác vẫn có thể đến từ file gốc. |
| “`optional:` bỏ qua cả lỗi cú pháp.” | `optional:` xử lý việc **không tìm thấy location**, không bỏ qua dữ liệu hỏng hoặc binding sai. |
| “Đổi hint là chuyển đổi định dạng tự động.” | Hint chọn loader; nội dung file phải hợp lệ đối với loader đó. |
| “File mount chỉ cần tồn tại trên host.” | Với container, cần mount thành đường dẫn mà **tiến trình trong container** đọc được. |
| “Chỉnh file mount là ứng dụng tự cập nhật cấu hình.” | Thay đổi sau startup thường đòi hỏi restart hoặc cơ chế refresh riêng. |

## 16. Bài tập thực hành

Giả sử có `application.properties` trong JAR:

~~~properties
spring.config.import=optional:file:./runtime[.properties]
app.name=Demo
app.timeout=3s
app.mode=default
~~~

Trong working directory, tạo file tên **`runtime`** (không có đuôi) với nội dung:

~~~properties
app.timeout=8s
app.feature.enabled=true
~~~

Khởi chạy:

~~~bash
java -jar app.jar
~~~

**Câu hỏi 1:** giá trị nào được dùng cho `app.name`, `app.timeout`, `app.mode` và `app.feature.enabled`?

**Đáp án:**

- `app.name=Demo` vì file import không khai báo `app.name`.
- `app.timeout=8s` vì file import ghi đè giá trị `3s` từ tài liệu khai báo import.
- `app.mode=default` vì chỉ có trong file gốc.
- `app.feature.enabled=true` vì được bổ sung từ file import.

**Câu hỏi 2:** nếu đổi tên file thật thành `runtime.yaml` nhưng giữ nguyên dòng import thì điều gì xảy ra?

Spring Boot tiếp tục tìm **`./runtime`**, không phải `./runtime.yaml`. Do có `optional:`, một location vắng mặt có thể bị bỏ qua và `app.timeout` quay về `3s`. Nếu mục tiêu là nạp `runtime.yaml`, hãy sửa location theo đúng tên thực tế.

**Câu hỏi 3:** nếu file `runtime` chứa YAML nhưng import vẫn là `[.properties]` thì sao?

Spring Boot vẫn dùng loader Java Properties theo hint. Nội dung không đúng cú pháp Java Properties có thể gây lỗi hoặc được diễn giải khác mong muốn. Cần chọn `[.yaml]` khi dữ liệu thật là YAML.

## 17. Ghi nhớ

- **Tệp không có phần mở rộng vẫn có thể được import** bằng `spring.config.import` nếu gắn extension hint `[.properties]` hoặc `[.yaml]` sau tên tài nguyên.
- **Hint là gợi ý parser**, không đổi tên file trên đĩa, không tạo file mới và không phải cơ chế chuyển đổi cú pháp.
- **Import và optional** có vai trò riêng: `spring.config.import` nạp config data; `optional:` chỉ cho phép location vắng mặt.
- **Thứ tự ưu tiên vẫn áp dụng**: thuộc tính được import có thể ghi đè file khai báo import, nhưng nguồn cấu hình ưu tiên cao hơn vẫn có thể ghi đè tiếp.
- **Phân biệt mô hình mount**: một file chứa YAML/Properties dùng extension hint; một thư mục gồm nhiều file mà tên file là key thường dùng `configtree:`.

### Tài liệu tham khảo

- Spring Boot 3.3 — Externalized Configuration, “Importing Extensionless Files”: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#importing-extensionless-files
- Spring Boot — Externalized Configuration / Config Data: https://docs.spring.io/spring-boot/reference/features/external-config.html
