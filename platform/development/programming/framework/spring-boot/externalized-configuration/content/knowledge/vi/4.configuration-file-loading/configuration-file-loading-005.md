# Bổ sung vị trí tìm cấu hình bằng `spring.config.additional-location` trong Spring Boot

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot thường có cấu hình mặc định được đóng gói cùng mã nguồn trong `application.properties` hoặc `application.yml`. Khi triển khai đến staging, production, Docker hoặc Kubernetes, đội vận hành có thể muốn cung cấp **một thư mục cấu hình bên ngoài JAR** mà không sửa file gốc và không build lại ứng dụng.

Ví dụ, JAR đang có cấu hình mặc định:

~~~yaml
# src/main/resources/application.yml
server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  request-timeout: 3s
  retry-count: 2
~~~

Ở production, cần đổi endpoint và timeout, đồng thời giữ lại `server.port` và `app.retry-count`. Có thể đặt một `application.yml` trong thư mục riêng và yêu cầu Spring Boot **bổ sung nơi tìm cấu hình** bằng thuộc tính:

~~~properties
spring.config.additional-location=optional:file:/etc/my-service/
~~~

Điều quan trọng nhất: **`spring.config.additional-location` thêm các vị trí tìm kiếm mới sau các vị trí mặc định**. Nó không buộc ứng dụng bỏ qua cấu hình đang có trong JAR.

## 2. Khái niệm và cú pháp

`spring.config.additional-location` là một thuộc tính khởi động của Spring Boot dùng để khai báo **các địa điểm bổ sung để tìm config data**. Giá trị thường là danh sách các địa chỉ thư mục hoặc tệp, chẳng hạn:

~~~text
optional:file:./external/
file:/etc/my-service/
optional:file:./ops/application.yml
optional:classpath:/extra-config/
~~~

Các thành phần của một location:

- `file:`: đọc từ hệ thống tệp của máy hoặc container đang chạy ứng dụng.
- `classpath:`: đọc tài nguyên nằm trong classpath, chẳng hạn thư mục đóng gói trong JAR.
- `./external/`: đường dẫn tương đối theo **working directory**, không mặc nhiên theo thư mục chứa file JAR.
- `/etc/my-service/`: đường dẫn tuyệt đối trên hệ thống Unix/Linux.
- `optional:`: cho phép location không tồn tại mà không gây lỗi thiếu location.
- Dấu `/` ở cuối đường dẫn thư mục: báo cho Spring Boot đây là **directory location** để tự tìm tên tệp cấu hình phù hợp.
- Đường dẫn kết thúc bằng tên tệp, ví dụ `file:/etc/my-service/application.yml`: đó là **file location**, được xử lý như một tệp cụ thể.

Đối với **directory location**, Spring Boot dùng tên cấu hình mặc định `application` (hoặc tên khác do `spring.config.name` chỉ định) để tìm `.properties`, `.yaml` và `.yml` cùng biến thể theo profile. Đối với **file location**, Spring Boot tham chiếu trực tiếp file được nêu tên; nó cũng xét biến thể theo profile khi phù hợp.

`spring.config.additional-location` cần được cung cấp **từ sớm**, trước khi cơ chế nạp config data quyết định phải tìm ở đâu. Vì vậy các cách khai báo thông dụng là **đối số dòng lệnh**, **Java system property** hoặc **biến môi trường hệ điều hành**.

## 3. Spring Boot tìm cấu hình ở đâu khi không khai báo gì?

Với cấu hình mặc định thông thường, Spring Boot tìm các tệp tên `application.*` tại:

| Nhóm | Vị trí | Ví dụ |
| --- | --- | --- |
| Classpath | `classpath:/` | `src/main/resources/application.yml` được đóng gói vào JAR |
| Classpath | `classpath:/config/` | `src/main/resources/config/application.yml` |
| File system | `file:./` | `./application.yml` bên ngoài JAR |
| File system | `file:./config/` | `./config/application.yml` |
| File system | `file:./config/*/` | `./config/mysql/application.yml`, `./config/redis/application.yml` |

`./` được hiểu theo **thư mục làm việc của tiến trình**. Khi chạy `cd /srv/my-service && java -jar app.jar`, vị trí `file:./config/` là `/srv/my-service/config/`. Nếu tiến trình được khởi chạy bởi systemd hoặc container với working directory khác, vị trí tương đối cũng thay đổi.

Theo thứ tự tìm kiếm mặc định của Spring Boot, các location bên ngoài có thể ghi đè thuộc tính trùng tên từ các location bên trong JAR. Spring Boot còn áp dụng quy tắc file theo profile: `application-prod.yml` được xét khi profile `prod` hoạt động.

Vậy khi thêm:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/
~~~

danh sách tìm kiếm sẽ gồm **các vị trí mặc định** và **`file:/etc/my-service/` ở phần bổ sung**. Nếu thư mục này chứa `application.yml`, các giá trị trùng tên trong đó có thể ghi đè giá trị mặc định.

## 4. Ví dụ hoàn chỉnh: một JAR, thêm một thư mục ngoài

Giả sử có cấu trúc triển khai:

~~~text
/srv/my-service/
├── app.jar
└── logs/

/etc/my-service/
├── application.yml
└── application-prod.yml
~~~

Trong JAR có file `application.yml`:

~~~yaml
server:
  port: 8080

app:
  endpoint: https://sandbox.example.test
  request-timeout: 3s
  retry-count: 2
  audit-enabled: false
~~~

Thư mục ngoài chứa `/etc/my-service/application.yml`:

~~~yaml
app:
  endpoint: https://api.example.test
  request-timeout: 8s
~~~

Và file `/etc/my-service/application-prod.yml`:

~~~yaml
app:
  request-timeout: 12s
  audit-enabled: true
~~~

Chạy ứng dụng với profile `prod`:

~~~bash
java -jar /srv/my-service/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/
~~~

Kết quả hiệu lực trong ví dụ, giả sử không có nguồn có ưu tiên cao hơn:

| Property | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `server.port` | `8080` | File chung trong JAR: thư mục ngoài không khai báo khóa này |
| `app.endpoint` | `https://api.example.test` | `/etc/my-service/application.yml` |
| `app.request-timeout` | `12s` | `/etc/my-service/application-prod.yml` |
| `app.retry-count` | `2` | File chung trong JAR: giữ giá trị mặc định |
| `app.audit-enabled` | `true` | `/etc/my-service/application-prod.yml` |

Điều này thể hiện ba việc: **thêm vị trí ngoài JAR**, **ghi đè theo ưu tiên** và **giữ các khóa không bị ghi đè**. File `application-prod.yml` trong thư mục bổ sung được xét vì profile `prod` đã được kích hoạt.

Nếu **không kích hoạt** `prod`, file `application-prod.yml` ở ví dụ sẽ không được dùng như file cấu hình profile thông thường; `app.request-timeout` sẽ nhận `8s`, còn `app.audit-enabled` tiếp tục là `false` nếu không có nguồn khác thay đổi.

Nếu khi chạy còn cung cấp:

~~~bash
java -jar /srv/my-service/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/ \
  --app.request-timeout=20s
~~~

thì `app.request-timeout=20s` vì đối số dòng lệnh có ưu tiên cao hơn config data trong ví dụ. Thuộc tính bổ sung location không khiến file được ưu tiên hơn **mọi** loại nguồn cấu hình.

## 5. Ba cách cung cấp `spring.config.additional-location`

### 5.1. Qua đối số dòng lệnh

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./external/
~~~

Đây là cách dễ thấy khi thử nghiệm: giá trị nằm ngay trong lệnh chạy ứng dụng. Chuỗi `optional:file:./external/` là **một location**, có tiền tố `optional:`, scheme `file:` và đường dẫn thư mục `./external/`.

### 5.2. Qua biến môi trường

~~~bash
export SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/my-service/
java -jar app.jar
~~~

Spring Boot nhận biến môi trường `SPRING_CONFIG_ADDITIONAL_LOCATION` như một hình thức biểu diễn thuộc tính `spring.config.additional-location`. Cách này thuận tiện khi nền tảng triển khai hoặc container cấp biến môi trường.

Ví dụ trong PowerShell:

~~~powershell
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = "optional:file:./external/"
java -jar app.jar
~~~

Cú pháp đặt biến là của shell; giá trị mà Spring Boot nhận vẫn là location string như nhau.

### 5.3. Qua Java system property

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/my-service/ -jar app.jar
~~~

Cần đặt `-D...` **trước `-jar`** để nó là tùy chọn JVM. Phần `--spring.config.additional-location=...`, ngược lại, là đối số dành cho ứng dụng và đặt **sau tên JAR**.

Một số nền tảng triển khai cung cấp các giá trị này trong cấu hình service hoặc manifest container. Nguyên tắc vẫn là phải cung cấp trước khi ứng dụng nạp config data.

### 5.4. Vì sao không đặt nó trong `application.yml` để bổ sung một thư mục?

Spring Boot cần biết `spring.config.additional-location` **trong giai đoạn rất sớm** để xác định những file cần tìm. Do đó, cách đáng tin cậy là đưa nó qua **environment, system properties hoặc CLI**. Đặt thuộc tính này trong chính file `application.yml` mà bạn mong Spring Boot đang tìm có thể là quá muộn để thay đổi tập location cần nạp.

Nếu mục tiêu là yêu cầu một tài liệu cấu hình **import thêm một nguồn**, có thể dùng `spring.config.import` bên trong file cấu hình. Đây là cơ chế khác và có quy tắc import riêng.

## 6. Khác nhau giữa thêm location và thay thế location

Hai thuộc tính dễ bị nhầm lẫn:

| Thuộc tính | Tác động đến đường dẫn tìm kiếm mặc định | Trường hợp dùng |
| --- | --- | --- |
| `spring.config.additional-location` | **Giữ** các location mặc định và **bổ sung** location mới | Có default trong JAR; deployment cung cấp file ghi đè |
| `spring.config.location` | **Thay thế** danh sách location mặc định bằng danh sách được chỉ định | Muốn kiểm soát cụ thể các nơi ứng dụng được phép tìm cấu hình |

Ví dụ:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot vẫn xét các vị trí mặc định, rồi xét `/etc/my-service/`. Trong khi đó:

~~~bash
java -jar app.jar --spring.config.location=file:/etc/my-service/
~~~

làm danh sách location mặc định được **thay bằng** location chỉ định. Nếu chỉ muốn thêm cấu hình triển khai mà vẫn tận dụng default trong JAR, `additional-location` thường phù hợp hơn.

Cả hai thuộc tính đều ảnh hưởng đến **tìm kiếm config data**, không phải cơ chế ưu tiên tổng quát giữa CLI, Java system properties, environment variables và config data.

## 7. Bổ sung một file cụ thể hay cả thư mục?

### 7.1. Bổ sung cả thư mục

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot tìm các file theo tên cấu hình hiện hành, ví dụ:

~~~text
/etc/my-service/application.properties
/etc/my-service/application.yml
/etc/my-service/application-prod.yml   (nếu prod được bật)
~~~

Điểm quan trọng là **dấu `/` cuối cùng**. Khi định nghĩa directory location, nên dùng dạng `file:/etc/my-service/` hoặc `file:./custom/`. Thiếu dấu `/` có thể khiến Spring Boot diễn giải location không đúng với ý định tìm thư mục.

### 7.2. Bổ sung tệp với tên cụ thể

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/company-defaults.yml
~~~

Ở đây Spring Boot sử dụng file `company-defaults.yml` được chỉ ra trực tiếp. Khi profile phù hợp đang hoạt động, biến thể `company-defaults-{profile}.yml` cũng có thể được xét theo quy tắc profile-specific file.

Không cần đổi tên mọi file thành `application.yml` khi sử dụng **file location**. Tuy nhiên nếu bạn cung cấp **directory location**, Spring Boot dựa vào `spring.config.name` để tìm tệp đúng tên; file bất kỳ như `company-defaults.yml` không tự xuất hiện chỉ nhờ thư mục được liệt kê.

### 7.3. Đổi basename bằng `spring.config.name`

Theo mặc định, basename là `application`. Nếu khởi động với:

~~~bash
java -jar app.jar \
  --spring.config.name=my-service \
  --spring.config.additional-location=file:/etc/my-service/
~~~

Spring Boot sẽ tìm các biến thể `my-service.properties` và `my-service.yml` tại location. Tên này ảnh hưởng đến việc tìm tệp tại các location dạng thư mục, bao gồm location mặc định; do đó không nên tự ý thay `spring.config.name` nếu vẫn muốn dùng các file mặc định tên `application.*`.

## 8. Bổ sung nhiều location và thứ tự ưu tiên

Giá trị `spring.config.additional-location` có thể liệt kê nhiều location. Ví dụ:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./ops/,optional:file:/etc/my-service/
~~~

Spring Boot xử lý theo thứ tự được khai báo. Với các location nằm trong những **nhóm ưu tiên kế tiếp nhau**, location xuất hiện sau có thể ghi đè các thuộc tính trùng tên ở location trước. Trong ví dụ đơn giản:

- File trong JAR đặt `app.timeout=3s`.
- `./ops/application.yml` đặt `app.timeout=5s`.
- `/etc/my-service/application.yml` đặt `app.timeout=9s`.

Nếu cả hai thư mục thêm đều tồn tại, `app.timeout` nhận `9s`, trừ khi một nguồn có ưu tiên cao hơn, như CLI, còn ghi đè tiếp.

Với các bộ file theo profile phức tạp, cần hiểu **location groups**:

- Dấu phẩy `,` phân cách các **nhóm location** trong khai báo; nhóm sau được xử lý ở mức ưu tiên sau.
- Dấu chấm phẩy `;` gom các location **cùng một nhóm ưu tiên**, khiến cách kết hợp file theo profile có thể khác khi dùng dấu phẩy.

Ví dụ hai chuỗi sau **không tương đương khi nhiều profile được bật**:

~~~text
optional:file:./ops/,optional:file:./regional/
optional:file:./ops/;optional:file:./regional/
~~~

Với profile `prod,region-apac`, các file `application-prod.yml` và `application-region-apac.yml` ở nhiều location có thể được sắp theo **nhóm location và thứ tự profile** khác nhau. Không thể kết luận chỉ dựa trên việc “file nào nằm ở thư mục bên phải”. Cần xem danh sách location và quy tắc group đang áp dụng.

Trong trường hợp chỉ có **một** thư mục bổ sung, cấu hình đơn giản nhất vẫn là một location duy nhất; chỉ dùng group khi thực sự cần phối hợp nhiều tập tệp theo profile.

## 9. `optional:` và lỗi thiếu location

Mặc định, một location được chỉ định tường minh nhưng không tồn tại có thể làm ứng dụng không khởi động, với lỗi kiểu `ConfigDataLocationNotFoundException`.

Ví dụ một đường dẫn bắt buộc:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/my-service/
~~~

Nếu thư mục `/etc/my-service/` không tồn tại, Spring Boot có thể dừng ở giai đoạn tìm config data. Đây là hành vi hữu ích khi deployment **bắt buộc** có cấu hình riêng để chạy đúng.

Nếu thư mục có thể vắng mặt ở môi trường phát triển:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/
~~~

Khi đó, việc **không tìm thấy location** không tự làm ứng dụng thất bại. Các giá trị mặc định vẫn có thể được sử dụng.

Có thể thêm `optional:` cho từng location riêng:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:./dev-overrides/,file:/etc/my-service/
~~~

Trong ví dụ, `./dev-overrides/` được phép vắng mặt, còn `/etc/my-service/` được coi là location bắt buộc.

Một vài giới hạn phải nhớ:

- `optional:` cho phép thiếu **location**, không có nghĩa cấu hình sai cú pháp, binding sai kiểu hay mật khẩu thiếu sẽ được bỏ qua.
- Nếu dịch vụ thực sự cần giá trị bắt buộc như database URL hoặc API key, vẫn nên validate cấu hình khi startup.
- Có thuộc tính `spring.config.on-not-found=ignore` để bỏ qua lỗi không tìm thấy location rộng hơn; chỉ nên dùng khi rõ lý do, vì nó có thể che giấu thiếu file triển khai bắt buộc.
- Đường dẫn không tồn tại do gõ sai cũng sẽ bị bỏ qua nếu đặt `optional:`, làm ứng dụng chạy bằng default ngoài ý muốn. Cần quan sát giá trị cấu hình hiệu lực khi triển khai.

## 10. Profile-specific files tại location bổ sung

Giả sử triển khai có:

~~~text
/etc/my-service/
├── application.yml
├── application-staging.yml
└── application-prod.yml
~~~

Và các file chứa:

~~~yaml
# application.yml
app:
  endpoint: https://sandbox.example.test
  timeout: 3s
~~~

~~~yaml
# application-staging.yml
app:
  timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  endpoint: https://api.example.test
  timeout: 12s
~~~

Lệnh:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/etc/my-service/
~~~

sẽ xét cả file chung và file `application-prod.yml` trong thư mục bổ sung. Giá trị `app.timeout` là `12s` nếu không bị ghi đè bởi nguồn khác.

Với nhiều profile được bật, Spring Boot có quy tắc **last-wins** trong việc kết hợp profile-specific config data ở cùng cấp group. Ví dụ `--spring.profiles.active=staging,prod` cho phép `prod` ghi đè các thuộc tính trùng tên của `staging` trong ngữ cảnh phù hợp.

Đừng nhầm `additional-location` với bật profile: **thêm thư mục không tự kích hoạt `prod`**. Profile phải được bật qua cơ chế profile riêng hoặc được xác định từ cấu hình hợp lệ trước giai đoạn cần thiết.

## 11. Wildcard và thư mục mount cấu hình

Spring Boot hỗ trợ wildcard location cho thư mục ngoài hệ thống tệp, chẳng hạn:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/my-service/*/
~~~

Giả sử:

~~~text
/etc/my-service/
├── database/
│   └── application.yml
└── messaging/
    └── application.yml
~~~

Với wildcard thư mục `*/` ở cuối, Spring Boot có thể tìm các file `application.*` trong **những thư mục con trực tiếp** như `database/` và `messaging/`. Wildcard được mở rộng và sắp xếp theo đường dẫn tuyệt đối, vì vậy nếu nhiều thư mục khai báo cùng một khóa, cần chú ý thứ tự thực tế.

Quy tắc hình thức cơ bản:

- Dùng **một** dấu `*` trong location có wildcard.
- Wildcard thư mục kết thúc bằng `*/`.
- Wildcard chỉ hỗ trợ **external location**, không dùng wildcard cho `classpath:`.
- Chỉ thư mục con trực tiếp phù hợp với mẫu được quét; không nên xem `*/` là quét đệ quy mọi cấp.

Hãy phân biệt dạng này với `configtree:`. Wildcard `file:.../*/` có mục đích tìm **file cấu hình** trong thư mục con; còn `configtree:` dùng cho cấu trúc mà **mỗi tên file trở thành tên property và nội dung file trở thành giá trị** (phổ biến với secret mounts). Muốn dùng config tree, thường khai báo `spring.config.import=optional:configtree:/.../` thay vì cho rằng `additional-location=file:.../` tự hiểu cấu trúc ấy.

## 12. Cấu hình trong Docker và Kubernetes

Trong container, ý tưởng vẫn là tách **artifact** khỏi **các giá trị theo môi trường**. Ví dụ Docker:

~~~bash
docker run --rm \
  -v /host/my-service-config:/etc/my-service:ro \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:/etc/my-service/ \
  my-service:1.0
~~~

Giả sử image đã chứa JAR và startup command, container sẽ nhận file `application.yml` từ volume mount read-only. Ở đây:

- `/host/my-service-config` là thư mục trên host, cần tồn tại và được chuẩn bị đúng.
- `/etc/my-service/` là đường dẫn **bên trong container** mà Spring Boot nhìn thấy.
- `:ro` giúp mount chỉ đọc; ứng dụng chỉ cần quyền đọc file.
- `SPRING_CONFIG_ADDITIONAL_LOCATION` được cấp từ lúc container khởi động nên có thể ảnh hưởng đến việc tìm config data.

Trong Kubernetes, có thể mount ConfigMap dưới dạng file cấu hình YAML rồi cấp cùng một biến môi trường. **Secret** nên được quản lý bằng cơ chế bảo mật của nền tảng; việc đưa key/password vào file bên ngoài JAR không tự đảm bảo an toàn. Không nên commit file chứa secret production vào Git chỉ vì file đó không nằm trong source code Java.

Thay đổi file bên ngoài lúc ứng dụng đang chạy **không đồng nghĩa** Spring Boot tự refresh mọi bean hay áp dụng lại toàn bộ thuộc tính. Thông thường cần một rollout/restart có kiểm soát hoặc một cơ chế refresh được triển khai riêng.

## 13. Phân biệt `additional-location` và `spring.config.import`

Hai cơ chế có thể bổ sung dữ liệu cấu hình, nhưng **điểm khai báo và cách xử lý khác nhau**.

| Đặc điểm | `spring.config.additional-location` | `spring.config.import` |
| --- | --- | --- |
| Nơi khai báo điển hình | CLI, JVM system property, OS environment | Trong file `application.yml` hoặc tài liệu config data khác |
| Mục đích | Thêm các location Spring Boot cần tìm khi startup | Từ một tài liệu config data, import thêm tài liệu khác |
| Đối tượng | File hoặc thư mục (và các location được hỗ trợ) | File, resource, config tree hoặc resolver được hỗ trợ |
| Ưu tiên | Các location thêm có thể ghi đè config data từ location mặc định | Nội dung import có thể ghi đè tài liệu đã khai báo import |
| Ví dụ | `--spring.config.additional-location=file:/etc/my-service/` | `spring.config.import=optional:file:/etc/my-service/extras.yml` |

Ví dụ khai báo import trong `application.yml`:

~~~yaml
spring:
  config:
    import: optional:file:./extras.yml
~~~

Cách này yêu cầu một tài liệu đã được nạp chỉ đến tệp khác. Nó phù hợp khi quan hệ import là một phần chủ đích của bộ cấu hình. Trong khi đó, `additional-location` phù hợp khi **môi trường triển khai** quyết định gắn thêm một thư mục chứa `application.*` mà mã nguồn không cần biết trước đường dẫn ấy.

## 14. Chẩn đoán khi cấu hình bổ sung không có hiệu lực

Nếu thêm thư mục mà ứng dụng vẫn dùng giá trị cũ, hãy lần lượt kiểm tra:

1. **Đã truyền đúng thuộc tính rất sớm chưa?** Kiểm tra CLI `--spring.config.additional-location`, `-Dspring.config.additional-location` hoặc biến môi trường `SPRING_CONFIG_ADDITIONAL_LOCATION`. Đừng chỉ đặt nó trong một file mà Spring Boot chưa biết phải nạp.
2. **Đường dẫn thuộc máy nào?** Nếu chạy container, `file:/etc/my-service/` trỏ vào filesystem **của container**. Với `file:./external/`, xác nhận working directory thực tế của tiến trình.
3. **Đang chỉ thư mục hay tệp?** Với thư mục phải có dấu `/` cuối. Với file, ghi đúng tên và phần mở rộng.
4. **Tên file có phù hợp không?** Nếu thêm thư mục, file thường phải tên `application.yml`, `application.properties` hoặc khớp `spring.config.name`.
5. **Profile đã bật chưa?** `application-prod.yml` chỉ tham gia khi profile `prod` hoạt động theo cơ chế thích hợp.
6. **Location có tồn tại không?** Với `optional:`, Spring Boot có thể tiếp tục khi không tìm thấy đường dẫn; lỗi gõ sai vì thế dễ bị bỏ qua.
7. **Có nhiều location hoặc import không?** Kiểm tra dấu `,`, dấu `;`, thứ tự profile và các file được import.
8. **Property có bị ghi đè từ nguồn cao hơn không?** Environment variable, Java system property hoặc command-line argument có thể ghi đè giá trị vừa nạp từ file.
9. **Giá trị đã được binding đúng chưa?** Sai kiểu, placeholder chưa giải quyết hoặc validation có thể làm startup thất bại hay khiến hành vi khác mong đợi.
10. **Ứng dụng đã khởi động lại chưa?** Cơ chế config data bình thường nạp lúc startup; chỉnh tệp trên disk không đảm bảo bean đang chạy tự cập nhật.

Khi cần quan sát có kiểm soát, Spring Boot Actuator có thể cung cấp thông tin về môi trường cấu hình qua endpoint như `/actuator/env` và `/actuator/configprops` nếu được bật và bảo vệ phù hợp. Các endpoint có thể liên quan đến secrets; cần giới hạn truy cập và che dữ liệu nhạy cảm.

Có thể bật log chẩn đoán cho phần nạp config data trong môi trường kiểm thử:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE \
  --spring.config.additional-location=optional:file:./external/
~~~

Chỉ bật chi tiết log theo nhu cầu và không đưa dữ liệu nhạy cảm vào log.

## 15. Những lỗi hiểu sai thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “`additional-location` làm Spring Boot ngừng tìm config trong JAR.” | Nó **bổ sung**, vẫn giữ các location mặc định. |
| “Thêm một thư mục là Spring Boot đọc mọi tên YAML trong thư mục ấy.” | Directory location tìm các tên sinh từ `spring.config.name`, mặc định là `application`. |
| “Đường dẫn tương đối tính từ nơi đặt JAR.” | Nó được giải quyết theo working directory của tiến trình. |
| “Một file mới ghi đè cả file cũ.” | Ghi đè thường dựa theo **từng property**; các khóa không có ở file mới vẫn có thể giữ từ nguồn thấp hơn. |
| “Location bổ sung thắng cả CLI và environment variables.” | Nó chỉ tham gia config data; nguồn ưu tiên cao hơn vẫn có thể ghi đè. |
| “Có `application-prod.yml` trong location bổ sung là tự bật `prod`.” | Profile phải được kích hoạt bằng cơ chế thích hợp. |
| “Thiếu đường dẫn mà có `optional:` thì mọi lỗi cấu hình đều được bỏ qua.” | `optional:` chỉ giải quyết việc location có thể vắng mặt; lỗi cấu hình vẫn cần xử lý. |
| “Gắn thêm một file secret là đã bảo mật.” | Cần phân quyền đọc file/mount và quản lý secret đúng cách. |
| “Thay file cấu hình mount sẽ tự cập nhật bean.” | Không có đảm bảo refresh tự động của toàn bộ context. |

## 16. Bài tập áp dụng

Trong JAR có:

~~~yaml
# application.yml
app:
  title: Demo
  timeout: 2s
  audit-enabled: false
~~~

Thư mục `./extra/` có:

~~~yaml
# extra/application.yml
app:
  timeout: 6s
~~~

và:

~~~yaml
# extra/application-prod.yml
app:
  audit-enabled: true
~~~

Ứng dụng được khởi động từ đúng thư mục chứa `extra/` bằng lệnh:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./extra/
~~~

**Câu hỏi:** `app.title`, `app.timeout`, `app.audit-enabled` có giá trị nào?

**Đáp án:**

- `app.title=Demo`: thư mục bổ sung không khai báo `title`, nên giữ default trong JAR.
- `app.timeout=6s`: file chung ở location bổ sung ghi đè `2s`.
- `app.audit-enabled=true`: file `application-prod.yml` ở location bổ sung được áp dụng do profile `prod` hoạt động.

Nếu gỡ `--spring.profiles.active=prod` mà không có nguồn nào khác kích hoạt profile đó, `app.audit-enabled` trở về `false`. Nếu thêm `--app.timeout=9s`, timeout trở thành `9s` vì đối số CLI có ưu tiên cao hơn file cấu hình.

## 17. Ghi nhớ

**`spring.config.additional-location` là cách để môi trường triển khai mở rộng tập nơi Spring Boot tìm config data mà vẫn sử dụng các location mặc định.**

Cần nắm bốn điểm khi sử dụng:

1. **Cấp từ sớm:** qua CLI, Java system properties hoặc environment variables.
2. **Phân biệt đường dẫn:** directory location kết thúc bằng `/`, file location chỉ rõ tên file, đường dẫn `./` theo working directory.
3. **Hiểu cách ghi đè:** location bổ sung có thể thắng giá trị trùng tên trong config data mặc định, nhưng vẫn phải xét profile, location group và nguồn có ưu tiên cao hơn.
4. **Quản lý khi triển khai:** dùng `optional:` khi được phép thiếu location, còn location bắt buộc nên được kiểm tra; bảo vệ secrets và chủ động khởi động lại/rollout khi cần áp dụng cấu hình mới.

### Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
