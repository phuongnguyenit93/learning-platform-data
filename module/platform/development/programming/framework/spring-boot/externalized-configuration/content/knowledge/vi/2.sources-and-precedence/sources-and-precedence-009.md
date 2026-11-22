# Phân biệt thứ tự ưu tiên nguồn, thứ tự nạp tệp và ghi đè từng khóa trong Spring Boot

## 1. Vì sao cần phân biệt ba khái niệm?

Khi cùng một thuộc tính xuất hiện ở nhiều nơi, câu hỏi quan trọng là: **Spring Boot sẽ dùng giá trị nào?** Để trả lời đúng, cần tách ba lớp quy tắc thường bị gọi chung là “thứ tự cấu hình”:

1. **Thứ tự ưu tiên nguồn (property source precedence):** khi các nguồn cấu hình khác nhau cùng cung cấp một thuộc tính, nguồn nào có quyền ghi đè?
2. **Thứ tự nạp và xử lý tệp (config data loading order):** các tệp `application.yml`, `application-prod.yml`, tệp ngoài JAR và các tệp được `import` được đưa vào cơ chế cấu hình theo thứ tự nào?
3. **Ghi đè từng khóa (property-level override):** khi nguồn có ưu tiên cao chỉ khai báo một số khóa, các khóa còn thiếu có được kế thừa từ nguồn thấp hơn hay không?

Ba khái niệm có liên quan, nhưng không đồng nhất. Một tệp được đọc sau chưa chắc có ưu tiên cao hơn **mọi** nguồn khác; còn một nguồn ghi đè một thuộc tính không có nghĩa nó thay thế toàn bộ cấu hình có trước.

> Quy tắc cốt lõi: Spring Boot xác định **giá trị hiệu lực cho từng thuộc tính** dựa trên các nguồn đang tham gia và thứ tự ưu tiên tương ứng. “Tệp sau thắng tệp trước” chỉ có ý nghĩa trong ngữ cảnh xử lý tệp đã được xác định.

## 2. Mô hình xử lý: nguồn, tệp và khóa

Một cách hình dung đơn giản:

~~~text
Đối số dòng lệnh             --app.timeout=20s
Java system properties       -Dapp.timeout=15s
Biến môi trường              APP_TIMEOUT=10s
Config data                  application*.yml, .properties, import...
Giá trị mặc định             các nguồn mặc định mức thấp
             |
             v
        Spring Environment
   (tập hợp các PropertySource)
             |
             v
     Tra cứu từng tên thuộc tính
       app.timeout  → 20s
       app.region   → giá trị từ nguồn có khai báo
             |
             v
     @ConfigurationProperties / @Value
             |
             v
      Bean ứng dụng sử dụng giá trị
~~~

Sơ đồ minh họa các loại nguồn thường dùng, chưa liệt kê hết những nguồn chỉ xuất hiện trong web container, kiểm thử hoặc môi trường phát triển.

- **`PropertySource`** là một nguồn chứa các cặp tên–giá trị. `Environment` truy xuất giá trị qua danh sách những nguồn này.
- **Config data** là cơ chế Spring Boot dùng để tìm, nạp và tổ chức nội dung của các tệp cấu hình cùng những nguồn được hỗ trợ qua `spring.config.import`.
- **Binding** là bước chuyển giá trị đã được giải quyết thành kiểu Java, ví dụ `Duration`, `boolean`, một record hay một nhóm `@ConfigurationProperties`.

Việc tệp nào được nạp và việc property nào “thắng” là hai câu hỏi phải xét theo đúng lớp này.

## 3. Thứ tự ưu tiên nguồn (property source precedence)

### 3.1. Các nguồn thường gặp

Trong **một ứng dụng Spring Boot chạy thông thường**, có thể ghi nhớ thứ tự gần đúng sau, từ **ưu tiên cao xuống thấp**:

| Mức ưu tiên | Nguồn | Ví dụ |
| --- | --- | --- |
| Cao | Đối số dòng lệnh của Spring Boot | `--server.port=9090` |
| | JSON cấu hình do Spring Boot hỗ trợ | `SPRING_APPLICATION_JSON` |
| | Java system properties | `-Dserver.port=8089` |
| | Biến môi trường hệ điều hành | `SERVER_PORT=8088` |
| | Config data | `application.yml`, tệp theo profile, tệp ngoài JAR, tệp import |
| | `@PropertySource` trên lớp `@Configuration` | Tệp properties do ứng dụng khai báo |
| Thấp | Default properties do ứng dụng thiết lập | `SpringApplication.setDefaultProperties(...)` |

Đây là **bảng rút gọn** để học cách giải quyết xung đột giữa các nguồn thông dụng, không phải danh sách đầy đủ mọi `PropertySource` của Spring Boot. Ví dụ, môi trường servlet, Spring Boot Test và Devtools có thể bổ sung nguồn với vị trí ưu tiên riêng. Tính ưu tiên của `@PropertySource` còn có giới hạn vì nguồn này được thêm khi application context đang refresh, quá muộn đối với một số cấu hình phải đọc rất sớm như `logging.*` hoặc `spring.main.*`.

Một ví dụ trực tiếp:

~~~yaml
# application.yml
server:
  port: 8080
~~~

~~~bash
# Biến môi trường:
SERVER_PORT=9090

# Đối số ứng dụng:
java -jar demo.jar --server.port=9191
~~~

Khi cả ba giá trị cùng tồn tại, cổng hiệu lực là **`9191`**. Bỏ đối số dòng lệnh thì giá trị thành **`9090`**; bỏ tiếp biến môi trường thì còn **`8080`**.

Từ ví dụ này, **không** thể suy ra rằng mọi giá trị trong tệp cấu hình đều bị thay bằng biến môi trường. Chỉ các tên thuộc tính trùng nhau mới xảy ra cạnh tranh.

### 3.2. Ưu tiên là một quy tắc chọn giá trị

Giả sử:

~~~yaml
# application.yml
app:
  timeout: 3s
  region: vn
  retry-count: 2
~~~

Và có biến môi trường `APP_TIMEOUT=10s`. Khi truy xuất:

| Thuộc tính | Giá trị hiệu lực | Lý do |
| --- | --- | --- |
| `app.timeout` | `10s` | Biến môi trường có ưu tiên cao hơn config data |
| `app.region` | `vn` | Biến môi trường không khai báo khóa này |
| `app.retry-count` | `2` | Không có nguồn cao hơn ghi đè |

Cơ chế tương tự hoạt động khi hai tệp cấu hình có thứ tự ưu tiên khác nhau. **Ứng dụng không chọn một “tệp chiến thắng” rồi bỏ qua tất cả tệp còn lại.**

## 4. Thứ tự nạp tệp (config data loading order)

Trong nhóm **config data**, Spring Boot tiếp tục áp dụng những quy tắc cụ thể về vị trí tệp, profile, tài liệu YAML và cấu hình được import.

### 4.1. Trật tự mặc định của các tệp cấu hình

Với vị trí tìm kiếm mặc định và cùng tên cấu hình `application`, nhóm config data phổ biến có thứ tự từ **thấp đến cao**:

1. `application.properties` hoặc `application.yml` được đóng gói **bên trong JAR**.
2. `application-{profile}.properties` hoặc `application-{profile}.yml` được đóng gói **bên trong JAR**.
3. `application.properties` hoặc `application.yml` nằm **bên ngoài JAR** tại vị trí được tìm kiếm.
4. `application-{profile}.properties` hoặc `application-{profile}.yml` nằm **bên ngoài JAR**.

Ví dụ, `./config/application-prod.yml` là tệp bên ngoài thường gặp khi ứng dụng chạy từ thư mục có thư mục con `config/`. Các đường dẫn tương đối phụ thuộc vào **working directory** của tiến trình.

Hai hệ quả rất dễ bỏ sót:

- Cấu hình ngoài JAR có thể ghi đè cấu hình theo profile **đóng gói trong JAR**. Không phải cứ có hậu tố `-prod` thì tệp đó thắng mọi tệp không có profile.
- Trong cùng một nhóm vị trí, cấu hình theo profile có thể ghi đè cấu hình chung của vị trí tương ứng.

Thứ tự trên mô tả cách xử lý **config data ở các vị trí mặc định**, không thay thế bảng ưu tiên nguồn ở mục 3. Ví dụ, một đối số `--app.timeout=20s` vẫn có thể ghi đè giá trị `app.timeout` trong `application-prod.yml` bên ngoài JAR.

### 4.2. Nhiều tệp hoặc tài liệu ở cùng một vị trí

Spring Boot hỗ trợ `.properties` và YAML. Nếu cả hai định dạng được dùng với **cùng tên tại cùng vị trí**, `.properties` có ưu tiên hơn YAML theo quy tắc của Spring Boot; thường nên chọn một định dạng để tránh xung đột khó thấy.

Một file YAML cũng có thể chứa nhiều tài liệu phân cách bằng `---`. Trong cùng file, tài liệu được kích hoạt về sau có thể ghi đè thuộc tính cùng tên từ tài liệu trước.

~~~yaml
# application.yml — tài liệu chung
app:
  timeout: 3s
  retry-count: 2

---
spring:
  config:
    activate:
      on-profile: prod
app:
  timeout: 5s
~~~

Chạy ứng dụng với:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Nếu không có nguồn ưu tiên cao hơn, kết quả là `app.timeout=5s` và `app.retry-count=2`. Tài liệu theo profile chỉ định nghĩa `timeout` nên khóa `retry-count` tiếp tục được lấy từ tài liệu chung.

### 4.3. Thứ tự nhiều profile đang hoạt động

Nếu kích hoạt nhiều profile, thứ tự profile có ý nghĩa khi chúng khai báo cùng một thuộc tính. Với các tệp theo profile cùng vị trí:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,region-apac
~~~

Giả sử `application-prod.yml` khai báo `app.timeout=5s` và `application-region-apac.yml` khai báo `app.timeout=7s`. Trong cách kết hợp thông dụng này, **profile xuất hiện sau thắng** với thuộc tính trùng tên, nên `app.timeout` nhận `7s` nếu không có nguồn khác ưu tiên cao hơn.

Nếu cấu hình có nhiều location group hoặc import phức tạp, cần xét cả nhóm vị trí, thứ tự tài liệu và thứ tự profile; không nên áp dụng nguyên câu “profile sau luôn thắng” mà bỏ qua các yếu tố khác.

## 5. Ví dụ đầy đủ: bốn tệp, một kết quả cho từng khóa

Giả sử CI build một JAR và trong đó có hai tệp:

**Tệp 1 — `classpath:/application.yml`**, cấu hình chung trong JAR:

~~~yaml
app:
  region: vn
  timeout: 3s
  retry-count: 2
  banner: welcome
~~~

**Tệp 2 — `classpath:/application-prod.yml`**, cấu hình theo profile trong JAR:

~~~yaml
app:
  timeout: 5s
  retry-count: 3
~~~

Ở bên ngoài JAR, thư mục làm việc có:

**Tệp 3 — `./config/application.yml`**, cấu hình chung bên ngoài:

~~~yaml
app:
  region: apac
  timeout: 8s
~~~

**Tệp 4 — `./config/application-prod.yml`**, cấu hình theo profile bên ngoài:

~~~yaml
app:
  retry-count: 5
  feature:
    enabled: true
~~~

Kích hoạt profile `prod`:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Giả sử không có nguồn cấu hình khác cung cấp các khóa này, các giá trị hiệu lực là:

| Khóa | Giá trị cuối | Nguồn thắng và giải thích |
| --- | --- | --- |
| `app.region` | `apac` | Tệp 3 ghi đè `vn` của tệp 1 |
| `app.timeout` | `8s` | Tệp 3 ở ngoài JAR ghi đè `5s` của tệp 2 và `3s` của tệp 1 |
| `app.retry-count` | `5` | Tệp 4 ghi đè `3` của tệp 2 và `2` của tệp 1 |
| `app.banner` | `welcome` | Chỉ tệp 1 khai báo nên giá trị vẫn được dùng |
| `app.feature.enabled` | `true` | Tệp 4 là nguồn có giá trị cho khóa này |

**Điểm mấu chốt của ví dụ:** `app.timeout` được lấy từ một tệp **không có hậu tố profile** nằm ngoài JAR, dù trong JAR có `application-prod.yml`. Giá trị nào thắng phụ thuộc vào **độ ưu tiên nguồn config data**, không chỉ nhìn vào tên file.

Tiếp tục đặt biến môi trường:

~~~bash
APP_TIMEOUT=12s java -jar demo.jar --spring.profiles.active=prod
~~~

`app.timeout` trở thành `12s`, còn `app.region=apac`, `app.retry-count=5` và các thuộc tính khác vẫn giữ nguyên.

Thêm đối số:

~~~bash
APP_TIMEOUT=12s java -jar demo.jar --spring.profiles.active=prod --app.timeout=15s
~~~

Lúc này `app.timeout=15s`. Đây là tác động của **ưu tiên giữa nguồn dòng lệnh, biến môi trường và config data**, chứ không phải thay đổi thứ tự nạp bốn file.

Lệnh gán biến môi trường trực tiếp ở trên dùng cú pháp shell Unix. Với PowerShell, có thể đặt `$env:APP_TIMEOUT = "12s"` trước khi chạy ứng dụng.

## 6. Ghi đè từng khóa là gì?

### 6.1. Nguồn cao hơn chỉ thay thế giá trị nó cung cấp

Một file không khai báo `app.region` thì không có lý do loại bỏ `app.region` của file ưu tiên thấp. Ngược lại, nếu file ưu tiên cao có khai báo `app.region`, giá trị đó được sử dụng cho khóa này.

~~~text
Nguồn ưu tiên thấp            Nguồn ưu tiên cao
app.region = vn               app.timeout = 10s
app.timeout = 3s              app.retry-count = 4
app.retry-count = 2
          \                      /
           \                    /
            Kết quả hiệu lực
            app.region = vn
            app.timeout = 10s
            app.retry-count = 4
~~~

Các thuộc tính như `app.timeout` và `app.retry-count` được giải quyết độc lập. Trong trường hợp binding thông thường, một thuộc tính có cấu trúc lồng nhau cũng có thể nhận các trường từ nhiều nguồn:

~~~yaml
# Nguồn thấp
app:
  client:
    base-url: https://sandbox.example.test
    timeout: 3s
    enabled: false
~~~

~~~yaml
# Nguồn cao
app:
  client:
    timeout: 10s
~~~

Kết quả sử dụng `base-url` và `enabled` từ nguồn thấp, nhưng `timeout=10s` từ nguồn cao.

### 6.2. Chú ý đặc biệt khi binding List và Map

Câu “ghi đè từng khóa” cần được hiểu chính xác ở lớp **property lookup**. Khi bind nhiều thuộc tính thành collection bằng `@ConfigurationProperties`, Spring Boot có quy tắc riêng:

- **List:** một danh sách được khai báo ở nguồn ưu tiên cao **thay thế danh sách** của nguồn ưu tiên thấp; không tự ghép các phần tử.
- **Map:** các entry có thể được tổng hợp từ nhiều nguồn; cùng một key trong map thì giá trị từ nguồn ưu tiên cao ghi đè.

Ví dụ với list:

~~~yaml
# Nguồn thấp
app:
  servers:
    - alpha
    - beta
~~~

~~~yaml
# Nguồn cao
app:
  servers:
    - gamma
~~~

Khi bind `app.servers` vào `List<String>`, kết quả là **`[gamma]`**, không phải `[gamma, beta]` và cũng không phải `[alpha, beta, gamma]`.

Ví dụ với map:

~~~yaml
# Nguồn thấp
app:
  labels:
    region: vn
    owner: team-a
~~~

~~~yaml
# Nguồn cao
app:
  labels:
    owner: team-b
~~~

Khi bind thành `Map<String, String>`, kết quả có thể gồm `region=vn` và `owner=team-b`. Do đó không nên áp dụng một quy tắc “merge tất cả” cho mọi cấu trúc Java.

### 6.3. Không có khóa và có khóa nhưng giá trị rỗng không giống nhau

Một property **không được khai báo** trong nguồn cao cho phép tra cứu tiếp xuống các nguồn thấp. Một property **được khai báo với chuỗi rỗng** có thể được coi là có giá trị, làm binding thành `int`, `Duration` hoặc kiểu bắt buộc bị lỗi. Vì vậy cần kiểm tra cả **nguồn đã cung cấp giá trị gì**, không chỉ kiểm tra rằng một file chứa hay không chứa tên thuộc tính.

Tương tự, một property dạng placeholder như `${APP_TIMEOUT:5s}` còn có logic thay thế khi được đánh giá. Không nên suy luận giá trị cuối chỉ từ văn bản nguồn mà không xét các nguồn và placeholder thực tế.

## 7. `spring.config.import` liên quan đến thứ tự nạp như thế nào?

Một file config data có thể khai báo nguồn cấu hình bổ sung:

~~~yaml
# application.yml
spring:
  config:
    import: optional:file:./secrets/extra.yml

app:
  timeout: 3s
~~~

Giả sử `./secrets/extra.yml` chứa:

~~~yaml
app:
  timeout: 8s
  region: vn
~~~

Đối với config data trong ví dụ này, tài liệu được import có **ưu tiên cao hơn tài liệu đã khai báo import**, nên `app.timeout=8s`; `app.region=vn` cũng có mặt trong kết quả.

Điều này không có nghĩa file import sẽ thắng các nguồn ở cấp ưu tiên khác như đối số dòng lệnh. Nếu thêm `--app.timeout=20s`, giá trị hiệu lực của thuộc tính vẫn có thể là `20s`.

Những điểm cần nhớ:

- `spring.config.import` khai báo **nguồn dữ liệu cấu hình bổ sung**, không phải annotation Java.
- `optional:` cho phép một location không tồn tại mà không khiến ứng dụng thất bại vì thiếu location; nếu bỏ `optional:`, location bắt buộc bị thiếu có thể khiến startup lỗi.
- Với nhiều import, thứ tự khai báo import có ý nghĩa; import sau có thể ghi đè import trước khi cùng khai báo một khóa.
- Vị trí import và profile đang hoạt động có thể ảnh hưởng đến thứ tự xử lý. Đừng chỉ nhìn vào thời điểm một dòng log thông báo “Loaded” để kết luận về property thắng.

## 8. `spring.config.location` và `spring.config.additional-location`

Khi chạy từ môi trường có cấu trúc thư mục riêng, Spring Boot hỗ trợ chỉ định nơi tìm config data:

- `spring.config.location`: chỉ định các location dùng để tìm config data và **thay thế danh sách location tìm kiếm mặc định**.
- `spring.config.additional-location`: **bổ sung** location vào các location mặc định; những location bổ sung ở phía sau có thể ghi đè những giá trị trùng khóa ở phía trước.

Ví dụ:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:/etc/demo/
~~~

Nếu `/etc/demo/application.yml` tồn tại và chứa `app.timeout=9s`, cấu hình này có thể ghi đè `app.timeout` trong các tệp config data mặc định; các thuộc tính không khai báo ở đó vẫn lấy từ nguồn khác.

Một số điểm thực hành:

1. Khi chỉ định một **thư mục**, kết thúc đường dẫn bằng dấu `/` để Spring Boot tìm đúng tệp `application.*` theo quy ước.
2. Khi không tìm thấy một location bắt buộc, startup có thể bị lỗi. Dùng `optional:` nếu việc vắng location là hợp lệ.
3. `spring.config.location`, `spring.config.additional-location` và `spring.config.name` cần được nhận biết **rất sớm** để xác định tệp phải nạp. Thường cấu hình chúng bằng biến môi trường, Java system properties hoặc đối số dòng lệnh.
4. Khi truyền nhiều location, **location group** và dấu phân tách cũng có ý nghĩa. Spring Boot dùng dấu phẩy để phân biệt các nhóm location và dấu chấm phẩy để nhóm các location ở cùng cấp. Các nhóm khác nhau có thể dẫn tới thứ tự ghi đè theo profile khác nhau. Khi cấu hình phức tạp, phải đọc đầy đủ danh sách location/group đã dùng thay vì chỉ xét tên tệp.

Những thiết lập này điều khiển **việc tìm và xử lý config data**; chúng không làm đảo ngược mọi thứ tự ưu tiên của `Environment`.

## 9. Cách xác định giá trị cuối trong một tình huống thực tế

Khi một thuộc tính, chẳng hạn `app.timeout`, khác với dự kiến, có thể kiểm tra theo trình tự:

1. **Viết chính xác tên property cần tra cứu:** `app.timeout`, không nhầm với `spring.mvc.async.request-timeout` hay một thuộc tính khác có tên gần giống.
2. **Kiểm tra các nguồn ưu tiên cao:** đối số `--app.timeout`, `SPRING_APPLICATION_JSON`, Java system property `-Dapp.timeout`, biến môi trường `APP_TIMEOUT`; với test còn phải xét nguồn chỉ có trong quá trình kiểm thử.
3. **Xác định các file config data tham gia:** file trong JAR, file ở working directory/`config/`, các `spring.config.location` hoặc `spring.config.additional-location`, profile đang bật và file import.
4. **Xét thứ tự bên trong config data:** packaged/external, profile-specific, tài liệu YAML, import và location group.
5. **Giải quyết đúng khóa:** nguồn cao nhất thực sự có định nghĩa thuộc tính sẽ cung cấp giá trị cho tra cứu thông thường; đối với `List`/`Map` phải xét thêm quy tắc binding.
6. **Kiểm tra kết quả binding:** thuộc tính đã chuyển thành đúng kiểu Java chưa, có placeholder hay validation tác động không, và bean được khởi tạo ở thời điểm nào?

Nếu bật Spring Boot Actuator và cấu hình quyền truy cập phù hợp, `/actuator/env` hoặc `/actuator/env/{name}` có thể hỗ trợ xem các property source và nguồn gốc giá trị; `/actuator/configprops` giúp quan sát cấu hình đã bind. Những endpoint này phải được bảo vệ và che thông tin nhạy cảm, đặc biệt với password, token và secret.

Với ứng dụng tự viết, có thể truy xuất giá trị qua `Environment`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigPrinter {
    public ConfigPrinter(Environment environment) {
        String timeout = environment.getProperty("app.timeout");
        System.out.println("Effective app.timeout = " + timeout);
    }
}
~~~

Đoạn mã chỉ minh họa truy xuất một **giá trị cuối**. Trong ứng dụng thực tế, không nên in các secret ra stdout hay log. Khi cần xác minh **nguồn gốc** của property, phải kiểm tra property source tương ứng bằng cơ chế quan sát có kiểm soát.

## 10. Các nhầm lẫn thường gặp

| Phát biểu sai hoặc thiếu | Cách hiểu đúng |
| --- | --- |
| “Tệp nào nạp cuối thì thắng tất cả.” | Cần xét nguồn tệp đó thuộc cấp ưu tiên nào, profile và import nào tham gia, rồi so từng property. |
| “`application-prod.yml` luôn thắng `application.yml`.” | Chỉ đúng khi so trong ngữ cảnh tương ứng; một tệp chung **ngoài JAR** có thể thắng file profile **trong JAR**. |
| “Có biến môi trường thì toàn bộ YAML bị bỏ qua.” | Chỉ property được biến môi trường cung cấp mới ghi đè; các khóa khác vẫn có thể đến từ YAML. |
| “Khai báo một trường trong object làm mất mọi trường khác.” | Các property lồng nhau thông thường được giải quyết riêng theo khóa; binding collection có quy tắc riêng. |
| “List và map đều tự nối giữa các nguồn.” | List thường bị thay toàn bộ khi bind; map có thể tổng hợp entry và ghi đè entry trùng key. |
| “Chỉ cần đặt `application-prod.yml` là profile `prod` tự bật.” | Profile phải được kích hoạt theo cơ chế phù hợp, ví dụ `--spring.profiles.active=prod`. |
| “`spring.config.location` chỉ thêm một thư mục.” | Nó thay danh sách location mặc định; để bổ sung nên dùng `spring.config.additional-location`. |
| “Đổi file bên ngoài thì bean chạy sẵn sẽ nhận ngay giá trị mới.” | Đa số giá trị được binding lúc startup; thường cần restart hoặc một cơ chế refresh riêng. |
| “Đọc `Environment.getProperty(...)` cho biết file nguồn.” | Nó cho biết giá trị hiệu lực; muốn biết nguồn phải xem property source/origin phù hợp. |

## 11. Bài tập suy luận

Cho ba lớp cấu hình:

~~~yaml
# Trong JAR: application.yml
app:
  host: local
  timeout: 2s
  retries: 1
~~~

~~~yaml
# Bên ngoài JAR: ./config/application.yml
app:
  host: remote
  retries: 3
~~~

~~~bash
APP_TIMEOUT=8s java -jar demo.jar --app.retries=5
~~~

Không có nguồn nào khác định nghĩa các thuộc tính trên. Hãy xác định giá trị hiệu lực trước khi xem lời giải.

**Lời giải:**

- `app.host=remote` vì tệp ngoài JAR cung cấp `host` ở mức ưu tiên cao hơn tệp trong JAR.
- `app.timeout=8s` vì biến môi trường ghi đè giá trị `2s` của tệp trong JAR.
- `app.retries=5` vì đối số dòng lệnh ghi đè cả `3` trong tệp bên ngoài và `1` trong tệp bên trong.

Bài tập cho thấy cần phân biệt ba câu hỏi: **nguồn nào ưu tiên hơn**, **các tệp config data được xử lý theo trật tự nào**, và **khóa nào có mặt trong từng nguồn**.

## 12. Ghi nhớ

- **Thứ tự ưu tiên nguồn** là quy tắc giữa các `PropertySource`, chẳng hạn CLI thường ghi đè biến môi trường và config data.
- **Thứ tự nạp tệp** là quy tắc nằm trong hệ thống config data: vị trí trong/ngoài JAR, file theo profile, tài liệu YAML, import và location group.
- **Ghi đè từng khóa** nghĩa là chỉ thuộc tính có giá trị ở nguồn ưu tiên cao mới bị thay; những thuộc tính không được khai báo vẫn có thể lấy từ nguồn ưu tiên thấp. Với `List` và `Map`, cần xét riêng cách `@ConfigurationProperties` binding.

Khi chẩn đoán, hãy ghi rõ **tên property, các nguồn có khai báo property đó, ưu tiên giữa nguồn, và giá trị cuối**. Đây là cách đáng tin cậy để giải thích vì sao Spring Boot dùng một cấu hình cụ thể.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Framework Reference — Environment Abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
