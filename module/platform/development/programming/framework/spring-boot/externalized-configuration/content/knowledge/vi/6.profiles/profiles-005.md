# Nhiều profile hoạt động đồng thời và thứ tự ghi đè trong Spring Boot

## Mục tiêu

Spring Boot cho phép kích hoạt **nhiều profile trong cùng một lần chạy**. Một ứng dụng có thể đồng thời dùng profile **prod** để chọn cấu hình sản xuất, **eu** để chọn thông số theo khu vực và **metrics** để bật một nhóm bean quan sát hệ thống. Nhưng khi nhiều profile cùng khai báo một thuộc tính, người phát triển phải hiểu **thứ tự profile**, **thứ tự nguồn cấu hình (PropertySource)** và **cơ chế điều kiện tạo bean** để giải thích kết quả chính xác.

Ví dụ, hai lệnh sau có thể dẫn tới cấu hình khác nhau:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,live
java -jar demo.jar --spring.profiles.active=live,prod
~~~

Lý do là với **các file cấu hình theo profile có cùng độ ưu tiên**, Spring Boot áp dụng quy tắc **profile được liệt kê sau có thể ghi đè giá trị của profile đứng trước**. Tuy nhiên, quy tắc này chỉ là một phần của hệ thống ưu tiên cấu hình: tham số dòng lệnh, JVM system property, biến môi trường, vị trí file, import và tài liệu Config Data cũng có ảnh hưởng.

Sau bài học, người đọc có thể:

- Khai báo, quan sát và phân biệt danh sách profile đang hoạt động với profile mặc định.
- Giải thích trường hợp cùng một khóa xuất hiện trong application.yml, application-prod.yml và application-live.yml.
- Dự đoán tác động của việc đổi thứ tự **spring.profiles.active**.
- Phân biệt **spring.profiles.active**, **spring.profiles.include**, **spring.profiles.group** và **spring.config.activate.on-profile**.
- Hiểu cách **@Profile** chọn bean, khác với việc ghi đè thuộc tính.
- Kiểm tra cấu hình runtime khi một profile hoặc nguồn cấu hình khác thay đổi giá trị kỳ vọng.

## 1. Profile có hai vai trò cần phân biệt

Trong Spring Boot, profile thường tham gia vào hai cơ chế liên quan nhưng khác nhau.

**Vai trò thứ nhất: chọn cấu hình.** Khi profile **prod** hoạt động, Spring Boot có thể nạp file **application-prod.yml** bên cạnh file **application.yml**. Khi profile **eu** cũng hoạt động, nó có thể nạp thêm **application-eu.yml** và các tài liệu YAML có điều kiện phù hợp.

**Vai trò thứ hai: chọn bean.** Annotation **@Profile("prod")** có thể khiến một cấu hình hoặc bean chỉ được đăng ký khi profile prod có hiệu lực. Đây là quyết định về thành phần của ApplicationContext.

Một profile **không phải một ứng dụng độc lập**. Ví dụ prod và metrics có thể cùng hoạt động, vì một profile quy định môi trường triển khai còn profile kia quy định đặc tính bổ sung.

~~~text
Một tiến trình Spring Boot
  |
  +-- Active profiles: prod, eu, metrics
  |
  +-- Config Data:
  |     application.yml
  |     application-prod.yml
  |     application-eu.yml
  |     application-metrics.yml
  |
  +-- Bean conditions:
        @Profile("prod")
        @Profile("eu")
        @Profile("metrics")
        @Profile("prod & eu")
~~~

Sơ đồ cho thấy các nguồn có thể được xét. File không tồn tại thì không tự xuất hiện, và tài liệu theo profile còn chịu quy tắc tìm kiếm/import/location cụ thể của ứng dụng.

**Một nguyên tắc quan trọng:** thứ tự profile có ý nghĩa khi giải quyết **cấu hình trùng khóa** giữa các tài liệu theo profile ở cùng tầng ưu tiên. Thứ tự đó **không biến** @Profile("prod") thành ưu tiên tạo bean cao hơn @Profile("eu").

## 2. Kích hoạt nhiều profile bằng spring.profiles.active

Giá trị của **spring.profiles.active** có thể chứa danh sách tên profile phân tách bằng dấu phẩy:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu,metrics
~~~

Các nguồn thường dùng:

~~~properties
# application.properties (tài liệu không ràng buộc profile)
spring.profiles.active=prod,eu,metrics
~~~

~~~yaml
# application.yml (tài liệu nền)
spring:
  profiles:
    active: prod,eu,metrics
~~~

~~~bash
# Linux/macOS: biến môi trường được cấp cho tiến trình
SPRING_PROFILES_ACTIVE=prod,eu,metrics java -jar demo.jar
~~~

~~~bash
# JVM system property phải đứng trước -jar
java -Dspring.profiles.active=prod,eu,metrics -jar demo.jar
~~~

~~~powershell
# Windows PowerShell
$env:SPRING_PROFILES_ACTIVE = "prod,eu,metrics"
java -jar demo.jar
~~~

Danh sách là tập các tên profile hiệu lực theo thứ tự kích hoạt, **không phải một tên profile duy nhất có chứa dấu phẩy**. Các dấu phẩy là cú pháp phân tách.

Khi truyền qua Docker hoặc Kubernetes, vẫn dùng cùng tên thuộc tính logic:

~~~bash
docker run --rm -e SPRING_PROFILES_ACTIVE=prod,eu demo-image
~~~

~~~yaml
# Một phần cấu hình Pod
env:
  - name: SPRING_PROFILES_ACTIVE
    value: "prod,eu"
~~~

Việc profile được khai báo ở môi trường container không làm thay đổi quy tắc ưu tiên của Spring Boot; container chỉ cung cấp một nguồn đầu vào.

### 2.1. Khi cùng spring.profiles.active xuất hiện ở nhiều nơi

Giả sử:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Nhưng ứng dụng được chạy bằng:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu
~~~

Trong cấu hình nguồn thông thường, tham số dòng lệnh có độ ưu tiên cao hơn giá trị từ application.yml. Danh sách active lấy từ tham số có độ ưu tiên cao hơn, tức **prod,eu**. Không được tự động nối **dev** với **prod,eu** chỉ vì cả hai nguồn cùng khai báo **spring.profiles.active**.

Tương tự, nếu cùng lúc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=dev java -jar demo.jar --spring.profiles.active=prod,eu
~~~

Tham số command line thông thường thắng biến môi trường đối với thuộc tính **spring.profiles.active**, nên danh sách active từ nguồn này là **prod,eu**, trừ khi ứng dụng thay đổi cơ chế xử lý hoặc có nguồn ưu tiên cao hơn.

**Phân biệt hai ý nghĩa của dấu phẩy:**

- Dấu phẩy **bên trong một giá trị spring.profiles.active** tạo danh sách nhiều profile.
- Hai **giá trị spring.profiles.active ở hai PropertySource** thường chịu quy tắc ưu tiên nguồn, không mặc định được ghép danh sách.

## 3. Ví dụ cơ sở: profile nào ghi đè profile nào?

Tạo ba file cấu hình.

~~~yaml
# src/main/resources/application.yml
app:
  stage: base
  message: "Hello from base"
  timeout: 10s
  region: global
~~~

~~~yaml
# src/main/resources/application-prod.yml
app:
  stage: production
  message: "Hello from prod"
  timeout: 25s
~~~

~~~yaml
# src/main/resources/application-live.yml
app:
  message: "Hello from live"
  timeout: 40s
  region: primary
~~~

Chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,live
~~~

Khi các file được nạp theo cơ chế Config Data mặc định và không có nguồn ưu tiên cao hơn, **live** đứng sau **prod**, nên giá trị trùng khóa trong **application-live.yml** được chọn.

| Thuộc tính | Base | prod | live | Giá trị hiệu lực |
| --- | --- | --- | --- | --- |
| app.stage | base | production | Không có | **production** |
| app.message | Hello from base | Hello from prod | Hello from live | **Hello from live** |
| app.timeout | 10s | 25s | 40s | **40s** |
| app.region | global | Không có | primary | **primary** |

Hãy chú ý: file đứng sau **không xóa tất cả thuộc tính** của file đứng trước. Nó ghi đè những khóa trùng, còn các khóa không được khai báo ở file ưu tiên hơn có thể tiếp tục lấy giá trị từ file nền hoặc profile khác.

### 3.1. Đổi thứ tự profile

Chạy lại:

~~~bash
java -jar demo.jar --spring.profiles.active=live,prod
~~~

Với đúng ba file nói trên, ứng dụng có thể nhận:

| Thuộc tính | prod,live | live,prod |
| --- | --- | --- |
| app.stage | production | production |
| app.message | Hello from live | Hello from prod |
| app.timeout | 40s | 25s |
| app.region | primary | primary |

Đây là cách trực tiếp nhất để hiểu **last-wins** giữa các profile-specific config files cùng độ ưu tiên: đổi thứ tự danh sách khi có khóa trùng có thể đổi giá trị thắng.

Cần tránh kết luận cực đoan rằng “profile cuối luôn thắng toàn ứng dụng”. Nó chỉ thắng các giá trị trùng khóa trong **phạm vi các tài liệu profile được so sánh theo cùng quy tắc ưu tiên**; nguồn khác như CLI hoặc location ưu tiên hơn có thể quyết định kết quả cuối.

### 3.2. Trường hợp file theo profile không tồn tại

Nếu chỉ có application.yml và application-prod.yml, mà active là **prod,live**, Spring Boot vẫn có thể khởi động và dùng những tài liệu tìm được. Việc file **application-live.yml** không tồn tại trong cơ chế tìm kiếm theo profile thông thường không buộc phải khiến ứng dụng lỗi. Nó chỉ có nghĩa không có các thuộc tính từ file đó.

Tuy nhiên, nếu một tài liệu có **spring.config.import** tới location bắt buộc bị thiếu, quy tắc lỗi của import vẫn có thể khiến ứng dụng dừng. Đừng nhầm hai trường hợp “file profile tùy chọn không tồn tại” và “location import bắt buộc không tồn tại”.

## 4. Thứ tự profile là một phần của thứ tự PropertySource

Hãy mở rộng ví dụ có giá trị trùng ở biến môi trường, JVM property và tham số dòng lệnh:

~~~bash
APP_TIMEOUT=50s java -Dapp.timeout=60s -jar demo.jar   --spring.profiles.active=prod,live   --app.timeout=70s
~~~

Trong cú pháp Bash, dấu **\** cuối dòng chỉ dùng để nối lệnh. Trên các shell khác, nên nhập lệnh một dòng hoặc dùng cú pháp nối dòng phù hợp.

Với các nguồn đã nêu và hành vi Spring Boot thông thường:

| Nguồn | Giá trị app.timeout | Độ ưu tiên tương đối trong ví dụ |
| --- | --- | --- |
| application.yml | 10s | Nguồn nền |
| application-prod.yml | 25s | File profile prod |
| application-live.yml | 40s | File profile live, thắng prod |
| APP_TIMEOUT | 50s | Biến môi trường, thắng Config Data |
| -Dapp.timeout | 60s | JVM system property, thắng biến môi trường |
| --app.timeout | 70s | Command-line property, thắng các nguồn trên |

Kết quả **Environment.getProperty("app.timeout")** ở lần chạy này là **70s**. Đổi **prod,live** thành **live,prod** không làm thay đổi kết quả, vì tham số **--app.timeout=70s** vẫn có ưu tiên cao hơn.

Muốn quan sát rõ tác dụng của thứ tự profile, hãy bỏ các override bên ngoài, hoặc chọn một khóa chỉ được khai báo trong các file profile. Nếu chỉ nhìn một property đang bị CLI ghi đè, người học dễ kết luận sai rằng Spring Boot bỏ qua thứ tự profile.

Spring Boot có thêm các loại PropertySource khác như **SPRING_APPLICATION_JSON**, nguồn trong kiểm thử và nguồn của DevTools. Bảng trên chỉ trình bày các nguồn có mặt trong tình huống minh họa.

## 5. Active profiles khác default profiles

Khi không có active profile nào được kích hoạt, Spring sử dụng **default profile** cho các điều kiện phù hợp. Thông thường tên của default profile là **default**.

Có thể thay danh sách profile mặc định bằng thuộc tính:

~~~yaml
# application.yml
spring:
  profiles:
    default: local
~~~

Khi **không có active profile tường minh**, cấu hình/điều kiện ứng với profile mặc định **local** có thể được áp dụng. Nếu chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

thì profile **prod** đang hoạt động, vì vậy không áp dụng tập default profiles như khi không có active profile.

Đặc biệt, tên **default** không phải bí danh bắt buộc của **dev**, và cũng không phải trạng thái “không có cấu hình nào”. File nền **application.yml** vẫn có thể được nạp trong cả trường hợp có hoặc không có active profile.

Có thể cấu hình:

~~~properties
spring.profiles.default=none
~~~

Cách này vô hiệu hóa hành vi chọn profile mặc định thông thường bằng cách dùng tên đặc biệt **none**, thay vì mặc định kích hoạt profile mang tên **default**.

**Khi dạy hoặc vận hành**, hãy phân biệt:

- **Không có active profile tường minh**: ứng dụng có thể dùng default profiles.
- **Có active profiles**: ứng dụng xét các active profiles được cấp, không cần dựa vào default profiles.
- **Không có file application-default.yml**: không làm Spring mất khả năng tải application.yml nền.

## 6. spring.profiles.include bổ sung profile như thế nào?

Thuộc tính **spring.profiles.include** được dùng khi một cấu hình cần **bổ sung các profile phụ** bên cạnh những profile được kích hoạt qua **spring.profiles.active**.

Ví dụ:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - observability
      - audit
~~~

Chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Về mặt ý định, ứng dụng có tập profile hiệu lực bao gồm **prod** cùng **observability** và **audit**. Nhờ vậy không cần lặp lại observability,audit ở mọi lệnh khởi động.

**Include là thao tác thêm profile**, khác với việc khai báo trùng **spring.profiles.active** ở hai nguồn. Ngoài ra, Spring Boot xử lý **spring.profiles.include** theo từng PropertySource; không nên suy luận từ trường hợp một giá trị active thắng nguồn khác rằng include sẽ có quy tắc ghi đè giống hệt.

Ví dụ file theo profile:

~~~yaml
# application-observability.yml
management:
  metrics:
    tags:
      service: orders
~~~

~~~yaml
# application-audit.yml
app:
  audit:
    enabled: true
~~~

Cùng với prod, hai profile bổ sung có thể làm cấu hình của các file này được đưa vào môi trường.

### 6.1. Không đặt include trong tài liệu chỉ kích hoạt theo profile

Một cách viết dễ mắc lỗi:

~~~yaml
# application-prod.yml: ví dụ không nên dùng
spring:
  profiles:
    include: audit
~~~

Các thuộc tính điều khiển việc kích hoạt profile như **spring.profiles.active**, **spring.profiles.default** và **spring.profiles.include** có ràng buộc về nơi khai báo trong Config Data. Spring Boot yêu cầu chúng nằm trong **tài liệu không đặc thù theo profile**; không được dùng như một cơ chế kích hoạt profile dây chuyền trong tài liệu chỉ dành cho profile prod hoặc được kích hoạt bằng **spring.config.activate.on-profile**.

Nếu muốn “chọn prod thì tự kèm audit”, xem **profile group** ở phần tiếp theo. Đây là cơ chế thể hiện một profile ở mức nghiệp vụ mở rộng thành các profile cụ thể.

### 6.2. Thứ tự khi có include

Khi dùng include, các profile được bao gồm được thêm trước các active profiles theo quy tắc xử lý của Spring Boot. Nhưng thứ tự cấu hình cuối cùng có thể còn chịu ảnh hưởng của **location group**, nhiều tài liệu Config Data, import và những profile đã được mở rộng.

Vì vậy, với hệ thống phức tạp, không nên chỉ lấy chuỗi khai báo trong một file rồi tự tính toàn bộ precedence. Hãy kiểm tra tập profile hiệu lực và các PropertySource trong môi trường đang chạy. Điều này đặc biệt cần thiết khi nhiều profile cùng định nghĩa một property quan trọng như URL cơ sở dữ liệu, port hoặc timeout.

## 7. spring.profiles.group: tạo nhóm profile theo tên nghiệp vụ

Nếu muốn kích hoạt nhiều profile thường đi cùng nhau bằng một tên ngắn, có thể sử dụng **spring.profiles.group**.

~~~yaml
# application.yml, tài liệu không đặc thù theo profile
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - metrics
~~~

Khi chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=production
~~~

Spring Boot mở rộng nhóm để các profile thành viên **proddb**, **prodmq**, **metrics** cũng được kích hoạt. Điều đó giúp người vận hành biết đến một tên ổn định ở tầng triển khai, còn ứng dụng tự quản lý các thành phần cấu hình chi tiết.

Một ví dụ phân vai:

| Profile | Mục đích điển hình |
| --- | --- |
| production | Tên nhóm dùng trong lệnh triển khai |
| proddb | Cấu hình datasource sản xuất |
| prodmq | Cấu hình message broker |
| metrics | Cấu hình quan sát |

Có thể có các file tương ứng:

~~~text
src/main/resources/
  application.yml
  application-production.yml
  application-proddb.yml
  application-prodmq.yml
  application-metrics.yml
~~~

Trong thực tế, **profile group được mở rộng theo quy tắc xử lý profile của Spring Boot**. Khi một khóa có mặt ở nhiều tài liệu được kích hoạt do group, thứ tự nguồn cấu hình vẫn quyết định giá trị thắng. Group không tự động “gộp YAML” theo một luật riêng cho database hoặc metrics.

### 7.1. Group khác include và khác activate.on-profile

- **group**: tên profile được kích hoạt dẫn đến việc kích hoạt các profile thành viên.
- **include**: thêm profile vào tập profile hiệu lực từ một thuộc tính cấu hình.
- **activate.on-profile**: đặt điều kiện để **một tài liệu cấu hình** có hiệu lực khi một biểu thức profile phù hợp. Nó không tự kích hoạt profile trong biểu thức.

Ví dụ, nếu chỉ viết:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
~~~

thì **production** không tự trở thành active profile. Tài liệu này chỉ được kích hoạt khi điều kiện đã khớp với profile hiệu lực của ứng dụng.

Đừng đặt **spring.profiles.group** vào tài liệu chỉ theo profile; định nghĩa group phải thuộc tài liệu cấu hình không đặc thù theo profile.

## 8. YAML nhiều tài liệu và spring.config.activate.on-profile

Một file application.yml có thể chứa nhiều tài liệu, phân tách bằng **---**. Tài liệu sau có thể đặt điều kiện kích hoạt theo profile.

~~~yaml
# application.yml: tài liệu nền
app:
  client:
    timeout: 5s
    mode: local

---
spring:
  config:
    activate:
      on-profile: prod
app:
  client:
    timeout: 20s
    mode: secure

---
spring:
  config:
    activate:
      on-profile: eu
app:
  client:
    timeout: 25s
~~~

Trong ví dụ này:

- Tài liệu đầu không có điều kiện, nên là cấu hình cơ sở.
- Tài liệu thứ hai có hiệu lực khi profile **prod** khớp.
- Tài liệu thứ ba có hiệu lực khi profile **eu** khớp.

Nếu cả prod và eu đều đang hoạt động, cả hai tài liệu có điều kiện có thể tham gia quá trình nạp. Với những tài liệu cùng file được xử lý theo thứ tự thông thường, **tài liệu phía sau có thể ghi đè thuộc tính trùng**; ở đây app.client.timeout có thể là **25s**, còn app.client.mode vẫn là **secure**.

Điểm tinh tế: **thứ tự tài liệu YAML** cũng ảnh hưởng precedence; không thể áp dụng máy móc “tên profile cuối thắng” cho mọi tình huống nếu hai profile xuất hiện trong các tài liệu YAML nhiều đoạn hoặc qua location khác nhau.

### 8.1. Biểu thức profile

Điều kiện **spring.config.activate.on-profile** có thể là biểu thức profile:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod & eu"
app:
  tax:
    regime: eu-production
~~~

Tài liệu chỉ có hiệu lực khi **cả prod và eu** cùng hoạt động. Với **prod** nhưng không có **eu**, điều kiện không khớp.

Ví dụ OR:

~~~yaml
spring:
  config:
    activate:
      on-profile: "dev | test"
app:
  remote:
    mock: true
~~~

Tài liệu áp dụng nếu dev **hoặc** test hoạt động. Dấu **!** có thể biểu thị phủ định trong biểu thức profile, ví dụ **!prod**. Khi biểu thức phức tạp, dùng dấu nháy trong YAML và dấu ngoặc phù hợp để diễn đạt đúng logic.

**Phân biệt:** một tài liệu có **on-profile: "prod & eu"** không tạo hai profile đó; nó chỉ đọc trạng thái profile đã được xác định.

## 9. @Profile chọn bean, không quyết định nguồn cấu hình thắng

Giả sử có hai cách hiện thực dịch vụ:

~~~java
public interface PaymentGateway {
    String provider();
}
~~~

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
class FakePaymentGateway implements PaymentGateway {
    @Override
    public String provider() {
        return "fake";
    }
}
~~~

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("prod")
class RealPaymentGateway implements PaymentGateway {
    @Override
    public String provider() {
        return "real";
    }
}
~~~

Khi chỉ active **dev**, bean FakePaymentGateway có thể được đăng ký. Khi chỉ active **prod**, bean RealPaymentGateway có thể được đăng ký.

Nhưng nếu active **dev,prod**, **cả hai điều kiện @Profile đều khớp**. Nếu ứng dụng inject một PaymentGateway duy nhất mà không có cơ chế phân biệt, Spring có thể báo **NoUniqueBeanDefinitionException** (hoặc lỗi phụ thuộc tương đương) vì tồn tại hai bean phù hợp.

**Thứ tự dev,prod không tự động chọn RealPaymentGateway thay vì FakePaymentGateway.** Việc lựa chọn bean phụ thuộc điều kiện đăng ký và cơ chế phân giải phụ thuộc như **@Primary**, **@Qualifier**, tên bean hoặc thiết kế sao cho hai bean không cùng xuất hiện.

### 9.1. OR, AND và NOT trong @Profile

~~~java
@Profile({"dev", "test"})
class DevelopmentToolsConfiguration {
}
~~~

Một annotation với mảng **{"dev", "test"}** có nghĩa **dev hoặc test**, không phải bắt buộc cả hai.

Muốn yêu cầu cả hai:

~~~java
@Profile("prod & eu")
class EuProductionConfiguration {
}
~~~

Muốn chỉ áp dụng khi không có prod:

~~~java
@Profile("!prod")
class NonProductionConfiguration {
}
~~~

Lưu ý: chỉ có các annotation trên class/configuration hoặc method phù hợp mới kiểm soát việc đăng ký bean. Việc một file application-eu.yml được nạp **không tự động quyết định** bean nào có @Primary.

### 9.2. Profile là điều kiện khởi tạo, không phải công tắc thay đổi nóng

Các điều kiện @Profile thông thường được đánh giá trong quá trình xây dựng ApplicationContext. Thay giá trị hệ thống sau khi ứng dụng đã chạy không khiến Spring tự động gỡ bean cũ, tạo bean mới hoặc nạp lại toàn bộ Config Data theo danh sách profile mới.

Muốn thay đổi tập profile một cách đáng tin cậy, hãy thay cấu hình khởi động rồi khởi động lại ứng dụng theo quy trình triển khai thích hợp. Nếu ứng dụng có cơ chế refresh riêng, phải xét hợp đồng của cơ chế đó, không suy diễn từ @Profile mặc định.

## 10. Thứ tự ghi đè còn phụ thuộc vị trí cấu hình

Trong Spring Boot, các file theo profile nằm trong hệ thống **Config Data**. Ngoài thứ tự profile, Spring Boot còn có quy tắc ưu tiên về nơi file được tìm thấy.

Ví dụ một ứng dụng có:

~~~text
Trong JAR:
  classpath:/application.yml
  classpath:/application-prod.yml

Ngoài JAR:
  ./config/application.yml
  ./config/application-prod.yml
~~~

Tài liệu từ vị trí có độ ưu tiên cao hơn có thể ghi đè tài liệu ở vị trí thấp hơn. Vì vậy, nếu một khóa tồn tại trong cả file classpath và file cấu hình ngoài, chỉ xem tên profile chưa đủ để xác định giá trị cuối.

Có thể chỉ định:

~~~bash
java -jar demo.jar   --spring.profiles.active=prod,eu   --spring.config.additional-location=optional:file:./site-config/
~~~

Khi đó các file tại site-config có thể tham gia sau các vị trí mặc định theo thứ tự ưu tiên của location bổ sung. Nếu những file ấy trùng khóa với file đóng gói, kết quả có thể khác với việc chỉ chạy JAR.

### 10.1. Location và location group

**spring.config.location** thay thế tập vị trí tìm mặc định; **spring.config.additional-location** bổ sung vị trí tìm kiếm. Đặc biệt, dấu **,** và **;** trong danh sách location có vai trò tạo thứ tự và nhóm location.

Trong những trường hợp nhiều active profiles, vị trí của các file theo profile trong **location group** ảnh hưởng đến thứ tự xử lý. Hai lệnh có cùng **prod,eu** nhưng nhóm location khác nhau vẫn có thể tạo các PropertySource theo thứ tự khác nhau.

Ví dụ các khai báo location mang ý nghĩa khác nhau:

~~~text
classpath:/cfg/,file:./external/
classpath:/cfg/;file:./external/
~~~

Không suy luận một giá trị thắng chỉ từ tên profile nếu còn có nhiều location hoặc import. Để chẩn đoán, phải xác định **toàn bộ các tài liệu đã nạp và thứ tự ưu tiên**, rồi tìm nơi có giá trị của khóa cần kiểm tra.

### 10.2. spring.config.import cũng tạo precedence

File cấu hình có thể dùng:

~~~yaml
spring:
  config:
    import: "optional:file:./config/overrides.yml"
app:
  timeout: 15s
~~~

Theo quy tắc Config Data thông thường, file import có ưu tiên cao hơn tài liệu khai báo import. Nếu một profile-specific file khác hoặc file import cũng chứa app.timeout, cần xem quan hệ import, profile, location và thứ tự nguồn; không thể chỉ đọc chuỗi **spring.profiles.active** là đủ.

## 11. List và Map khi nhiều profile cùng khai báo cấu hình

Đối với một scalar như app.timeout, cách hiểu “nguồn ưu tiên hơn thắng” thường trực quan. Với cấu trúc **List** và **Map**, cách bind cần được xét riêng.

### 11.1. List thường được thay thế, không tự nối phần tử

Ví dụ:

~~~yaml
# application.yml
app:
  servers:
    - host: alpha.example.test
      port: 9001
    - host: beta.example.test
      port: 9002
~~~

~~~yaml
# application-prod.yml
app:
  servers:
    - host: production.example.test
      port: 9443
~~~

Khi bind danh sách từ nhiều PropertySource có độ ưu tiên khác nhau, Spring Boot thường sử dụng **danh sách từ nguồn ưu tiên cao**, chứ không nối thành ba phần tử. Với profile prod, có thể nhận danh sách chỉ gồm production.example.test.

Không nên tin rằng các phần tử ở index 1 của file nền sẽ luôn được giữ khi profile chỉ khai báo index 0. Nếu muốn một danh sách có đủ phần tử, hãy cung cấp danh sách đầy đủ tại nguồn thắng hoặc định nghĩa quy tắc hợp nhất rõ trong mã.

### 11.2. Map có thể kết hợp khóa

Ví dụ:

~~~yaml
# application.yml
app:
  labels:
    owner: platform
    region: global
~~~

~~~yaml
# application-prod.yml
app:
  labels:
    region: asia
    tier: critical
~~~

Khi bind thành **Map<String, String>**, Spring Boot có thể kết hợp các khóa khác nhau qua nguồn cấu hình: owner từ file nền, region từ nguồn ưu tiên hơn, tier từ profile prod. Các quy tắc này còn chịu ảnh hưởng của giá trị kiểu map/nested và tên key cụ thể.

| Key của map | Base | prod | Kết quả minh họa |
| --- | --- | --- | --- |
| owner | platform | Không có | platform |
| region | global | asia | asia |
| tier | Không có | critical | critical |

Không mang quy tắc ghi đè list áp dụng nguyên xi cho map; cũng không suy diễn từ một Map đơn giản sang tất cả các kiểu cấu trúc lồng nhau.

### 11.3. Giá trị rỗng và null không đồng nghĩa xóa nguồn thấp hơn

Một profile có thể khai báo **app.name: ""**, **app.name:** hoặc **app.name: null**. Chúng có ý nghĩa ở bước parse YAML và bước chuyển sang PropertySource khác nhau; không nên mặc định rằng null sẽ “xóa” mọi giá trị cấu hình trước đó.

Nếu mục đích là vô hiệu hóa chức năng theo profile, một cờ tường minh thường dễ hiểu hơn:

~~~yaml
# application-prod.yml
app:
  notifications:
    enabled: false
~~~

Khi xử lý giá trị bắt buộc, nên kết hợp **@ConfigurationProperties** với validation phù hợp để phát hiện missing hoặc blank sớm.

## 12. Quy tắc đặt spring.profiles.active trong Config Data

Có thể đặt **spring.profiles.active** trong tài liệu nền không đặc thù theo profile:

~~~yaml
# application.yml: tài liệu nền
spring:
  profiles:
    active: dev
~~~

Tuy nhiên, không nên viết:

~~~yaml
# application-prod.yml: cấu hình không hợp lệ về nơi khai báo
spring:
  profiles:
    active: metrics
~~~

Tương tự, trong một tài liệu YAML được kích hoạt bởi **spring.config.activate.on-profile**, không được dùng **spring.profiles.active** hoặc **spring.profiles.default** để điều khiển lại danh sách profile. Spring Boot có ràng buộc này để tránh quá trình profile activation tạo vòng hoặc phụ thuộc vào chính tài liệu chưa được kích hoạt.

Một ví dụ cần tránh:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: eu
~~~

Đoạn trên không phải cách hợp lệ để “khi prod thì bật eu”. Nếu muốn mở rộng một profile thành nhiều profile có quan hệ cố định, hãy định nghĩa **spring.profiles.group** trong tài liệu nền không đặc thù theo profile.

## 13. Phương án tổ chức profile khi dự án lớn dần

Một dự án có thể có ba chiều cấu hình độc lập:

- **Môi trường:** dev, staging, prod.
- **Khu vực:** eu, apac, us.
- **Tính năng vận hành:** metrics, tracing, audit.

Nếu tạo một profile kết hợp cho mọi tổ hợp, số lượng file và độ trùng lặp có thể tăng rất nhanh. Có thể khai báo các file theo vai trò, ví dụ:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
application-eu.yml
application-apac.yml
application-metrics.yml
application-audit.yml
~~~

Rồi kích hoạt:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu,metrics
~~~

Cách này hợp lý khi mỗi profile chứa các thuộc tính **không chồng lấn ngoài ý muốn**. Nếu các profile thường xuyên định nghĩa cùng một khóa nhạy cảm, cần có quy ước sở hữu:

| Loại khóa | Nơi nên quản lý rõ ràng |
| --- | --- |
| Địa chỉ database hoặc broker | Profile môi trường/nguồn triển khai được chỉ định |
| Regional endpoint, locale, khu vực dữ liệu | Profile khu vực |
| Bật/tắt quan sát hệ thống | Profile tính năng hoặc cấu hình vận hành |
| Mặc định an toàn, độc lập môi trường | application.yml |
| Secret, credential | Nguồn secret chuyên dụng và cơ chế cấp quyền phù hợp |

Đây là một cách tổ chức để giảm việc ghi đè ngoài ý muốn, không phải luật tự động do Spring Boot áp đặt. Dù phân chia đúng, một biến môi trường hoặc tham số khởi động vẫn có thể override các giá trị trong file theo thứ tự nguồn.

### 13.1. Không dùng profile thay cho mọi tính năng

Một profile rất phù hợp cho một nhóm cấu hình/bean được chọn lúc khởi động. Tuy nhiên, nếu một feature flag cần thay đổi khi ứng dụng đang chạy mà không khởi động lại, dựa vào @Profile có thể không đáp ứng yêu cầu. Khi đó nên cân nhắc cơ chế feature flag riêng với hành vi cập nhật được định nghĩa rõ ràng.

Profile cũng không phải cơ chế bảo vệ secret. Việc đặt password trong application-prod.yml và chỉ bật profile prod không ngăn thông tin đó bị lộ trong mã nguồn hoặc artifact.

## 14. Cách kiểm tra active profiles tại runtime

Đừng chỉ suy đoán từ tên file. Spring Environment có API cho biết danh sách profile đang hoạt động:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileInspector implements ApplicationRunner {

    private final Environment environment;

    ProfileInspector(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Active profiles: "
            + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("Default profiles: "
            + Arrays.toString(environment.getDefaultProfiles()));
        System.out.println("app.message: "
            + environment.getProperty("app.message"));
        System.out.println("app.timeout: "
            + environment.getProperty("app.timeout"));
    }
}
~~~

Ví dụ này giúp trả lời hai câu hỏi độc lập:

1. **Tập profile nào đang hiệu lực?** Đọc từ getActiveProfiles().
2. **Giá trị cấu hình cuối cùng là gì?** Đọc từ getProperty(...).

Không nên xem giá trị của một thuộc tính đơn lẻ là bằng chứng đầy đủ cho danh sách profile. Nếu một nguồn CLI override property, giá trị ấy có thể không phản ánh điều gì về profile được liệt kê cuối.

### 14.1. Hiển thị tên các PropertySource

Khi cần tìm lý do một giá trị thắng, có thể duyệt danh sách PropertySource của **ConfigurableEnvironment**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
class PropertySourceNames implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    PropertySourceNames(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Các tên nguồn thường giúp nhận diện file hoặc location đã nạp. Thứ tự PropertySource trong Environment thể hiện thứ tự tra cứu ở runtime. Khi truy nguyên một khóa cụ thể, cần chú ý relaxed binding và cách một PropertySource biểu diễn tên khóa, nên không phải mọi thao tác getProperty trực tiếp trên một source đều tương đương với Environment.getProperty(...).

**Không in toàn bộ giá trị của mọi PropertySource vào log**, vì file cấu hình có thể chứa mật khẩu, API token hoặc thông tin kết nối nhạy cảm.

### 14.2. Dùng Actuator khi đã được cấu hình phù hợp

Trong hệ thống có Spring Boot Actuator, endpoint env có thể giúp xem tên thuộc tính và nguồn cấu hình, còn endpoint conditions có thể hỗ trợ tìm điều kiện tạo bean. Các endpoint này cần được giới hạn quyền truy cập phù hợp; dữ liệu nhạy cảm có thể bị che.

Không mở công khai thông tin môi trường chỉ để xác minh thứ tự profile. Khi cần chẩn đoán, xem kết quả trong môi trường được bảo vệ hoặc dùng đoạn mã chỉ in những khóa không nhạy cảm.

## 15. Những lỗi thực tế dễ gặp

### 15.1. Đổi thứ tự profile nhưng không thấy giá trị đổi

**Nguyên nhân thường gặp:** khóa đang bị command-line property, JVM system property, biến môi trường hoặc Config Data từ location ưu tiên hơn ghi đè.

**Cách kiểm tra:** thử một khóa chỉ có ở các file profile; ghi lại Environment.getProperty(...); xem nguồn của property tại runtime.

### 15.2. Nghĩ profile cuối “tắt” bean của profile trước

**Nguyên nhân:** hiểu nhầm precedence của file config thành precedence của @Profile.

**Cách kiểm tra:** xem điều kiện @Profile của từng bean. Với **dev,prod**, cả bean @Profile("dev") và bean @Profile("prod") có thể cùng được tạo. Thiết kế điều kiện loại trừ hoặc phân giải bean rõ ràng nếu cần đúng một implementation.

### 15.3. Viết active profile trong application-prod.yml

**Nguyên nhân:** đặt **spring.profiles.active** trong tài liệu chỉ thuộc profile. Cấu hình này không đúng vị trí được hỗ trợ.

**Cách xử lý:** chuyển kích hoạt ra nguồn khởi động hoặc tài liệu nền; dùng profile group nếu cần tự động mở rộng prod thành các profile phụ.

### 15.4. Tưởng hai giá trị spring.profiles.active tự cộng với nhau

**Nguyên nhân:** nhầm cơ chế ưu tiên PropertySource với cơ chế include.

**Cách kiểm tra:** xem giá trị spring.profiles.active ở nguồn ưu tiên cao nhất, sau đó xem include/group và danh sách getActiveProfiles() thực tế.

### 15.5. Đặt profile group nhưng không thấy profile mong đợi

**Nguyên nhân:** nhóm được khai báo ở tài liệu sai vị trí, tên group không trùng tên profile được kích hoạt hoặc file của profile thành viên không tồn tại.

**Cách kiểm tra:** đặt group trong tài liệu nền, xác nhận tên group và getActiveProfiles(); sau đó xem các tài liệu cấu hình có thực sự được nạp không.

### 15.6. File YAML hợp lệ nhưng khóa biến mất khi có nhiều profile

**Nguyên nhân:** cấu trúc YAML thay đổi, sai thụt lề, hoặc danh sách bị thay thế thay vì hợp nhất.

**Cách kiểm tra:** so tên khóa đầy đủ và kiểu binding trong @ConfigurationProperties; phân biệt scalar, List và Map.

### 15.7. Môi trường production đang dùng profile default

**Nguyên nhân:** tham số SPRING_PROFILES_ACTIVE không thực sự được cấp cho tiến trình, launcher bỏ sót tham số hoặc tên biến sai.

**Cách kiểm tra:** quan sát getActiveProfiles() ngay khi khởi động và đối chiếu lệnh triển khai. Không suy luận chỉ từ tên namespace, tên container hoặc nhãn môi trường.

### 15.8. Phân tích thứ tự trong nhiều tài liệu YAML theo thứ tự profile

**Nguyên nhân:** tưởng rằng mọi tài liệu on-profile trong một file được ưu tiên lại theo chuỗi active profiles.

**Cách kiểm tra:** xem cả **thứ tự tài liệu YAML**, location group và import. Điều kiện on-profile quyết định tài liệu có tham gia hay không; precedence còn phụ thuộc vị trí tài liệu trong Config Data.

## 16. Bài thực hành: dự đoán và xác minh

### Bài 1 — Đổi thứ tự hai profile

Các file:

~~~properties
# application.properties
demo.value=base
demo.owner=core
~~~

~~~properties
# application-dev.properties
demo.value=dev
demo.log-level=verbose
~~~

~~~properties
# application-qa.properties
demo.value=qa
demo.owner=quality
~~~

Lần chạy A:

~~~bash
java -jar demo.jar --spring.profiles.active=dev,qa
~~~

Lần chạy B:

~~~bash
java -jar demo.jar --spring.profiles.active=qa,dev
~~~

Hãy dự đoán **demo.value**, **demo.owner**, **demo.log-level**.

| Khóa | dev,qa | qa,dev |
| --- | --- | --- |
| demo.value | qa | dev |
| demo.owner | quality | quality |
| demo.log-level | verbose | verbose |

**Giải thích:** demo.value nằm ở cả hai file profile nên đổi theo profile đứng sau; demo.owner chỉ được QA override; demo.log-level chỉ được dev khai báo. Một profile đứng sau không tự xóa khóa chưa khai báo.

### Bài 2 — Profile so với CLI override

File config:

~~~yaml
# application-prod.yml
app:
  timeout: 20s
~~~

~~~yaml
# application-eu.yml
app:
  timeout: 30s
~~~

Lệnh chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=prod,eu --app.timeout=90s
~~~

Hỏi: timeout hiệu lực là bao nhiêu nếu không có nguồn ưu tiên cao hơn? **90s**, vì CLI override. Bỏ **--app.timeout=90s** và chạy lại: **30s**, vì eu đứng sau prod trong ví dụ config data đơn giản.

### Bài 3 — OR và AND trong @Profile

~~~java
@Profile({"dev", "test"})
class ToolsConfiguration {
}

@Profile("prod & eu")
class EuProductionConfiguration {
}
~~~

- Active profiles **dev,test**: ToolsConfiguration khớp, EuProductionConfiguration không khớp.
- Active profiles **prod,eu**: EuProductionConfiguration khớp, ToolsConfiguration không khớp.
- Active profiles **dev,prod,eu**: cả hai cấu hình có thể khớp.

Đừng nhầm **@Profile({"dev", "test"})** với điều kiện AND.

### Bài 4 — Group và include

~~~yaml
spring:
  profiles:
    include:
      - audit
    group:
      production:
        - proddb
        - prodmq
~~~

Chạy:

~~~bash
java -jar demo.jar --spring.profiles.active=production
~~~

Hãy dùng Environment.getActiveProfiles() để quan sát danh sách hiệu lực, xác nhận **production**, các profile thành viên **proddb**, **prodmq**, và profile được include **audit**. Sau đó tạo file application-proddb.yml và application-audit.yml với cùng một khóa thử nghiệm để quan sát tác động của thứ tự PropertySource thực tế.

Mục đích là phân biệt **tên nhóm**, **cơ chế include** và **precedence của nguồn cấu hình**, thay vì đoán thứ tự từ tên file.

### Bài 5 — Thứ tự tài liệu YAML

~~~yaml
demo:
  mode: base
---
spring:
  config:
    activate:
      on-profile: prod
demo:
  mode: production
---
spring:
  config:
    activate:
      on-profile: eu
demo:
  mode: european
~~~

Với **prod,eu** và không có override khác, cả hai tài liệu có điều kiện đều khớp, và tài liệu cuối có thể quyết định **demo.mode=european** trong cách xử lý Config Data thông thường của ví dụ này.

Đổi vị trí hai tài liệu theo profile mà không đổi chuỗi active profile là một phép thử riêng để nhìn thấy ảnh hưởng của **thứ tự tài liệu**.

## 17. Quy trình xử lý khi cấu hình không khớp kỳ vọng

Thực hiện theo thứ tự sau để hạn chế đoán mò:

1. **Chọn đúng tên thuộc tính đang sai**, ví dụ app.timeout, và ghi lại giá trị kỳ vọng.
2. **Đọc active profiles thực tế** bằng Environment.getActiveProfiles() và nếu cần cả default profiles.
3. **Đọc lệnh khởi động và biến môi trường**, xác định nguồn nào cấp spring.profiles.active và có thêm include/group không.
4. **Liệt kê các tài liệu Config Data liên quan**, gồm application.yml, file theo profile, nhiều tài liệu YAML, location và import.
5. **Đánh dấu từng nơi có khai báo khóa**, và xét thứ tự ưu tiên nguồn thay vì chỉ nhìn tên file.
6. **Kiểm tra kiểu dữ liệu khi bind**, nhất là List, Map, Duration, boolean hoặc giá trị rỗng/null.
7. **Với lỗi bean**, xem điều kiện @Profile của từng bean và quy tắc chọn bean của Spring; không áp dụng quy tắc “profile cuối thắng” cho việc tạo bean.
8. **Xác nhận giá trị runtime** qua Environment, bean cấu hình hoặc công cụ quan sát được bảo vệ.

Nếu một thay đổi về profile khiến ứng dụng không khởi động, phân biệt lỗi **nạp Config Data**, lỗi **chuyển kiểu/validation** và lỗi **đăng ký/tiêm bean**. Những nhóm lỗi này có nguyên nhân và cách sửa khác nhau dù đều xuất hiện sau khi thay danh sách active profiles.

## 18. Ghi nhớ

- **spring.profiles.active** có thể kích hoạt nhiều profile bằng danh sách ngăn cách dấu phẩy, ví dụ **prod,eu,metrics**.
- Khi các **file cấu hình theo profile ở cùng mức ưu tiên** trùng một khóa, **profile được liệt kê sau có thể ghi đè giá trị từ profile đứng trước**.
- Quy tắc last-wins giữa profile **không vượt qua toàn bộ precedence của Spring Environment**. CLI, JVM properties, biến môi trường, location và import có thể thay đổi giá trị hiệu lực.
- **spring.profiles.include** thêm profile; **spring.profiles.group** mở rộng một tên profile thành nhiều thành viên; **spring.config.activate.on-profile** chỉ quyết định tài liệu Config Data có được kích hoạt hay không.
- **Default profiles** là cơ chế khi không có active profile; chúng khác với danh sách active được chỉ định.
- **@Profile** quyết định bean nào đủ điều kiện đăng ký. Hai bean có điều kiện profile khác nhau vẫn có thể cùng tồn tại khi cả hai profile hoạt động.
- **List** và **Map** có quy tắc binding khác nhau khi nhiều nguồn cấu hình cùng tham gia.
- Muốn biết điều gì xảy ra trong lần chạy thực tế, hãy đối chiếu **getActiveProfiles()**, **Environment.getProperty(...)** và **thứ tự PropertySource**.

Khi một ứng dụng sử dụng nhiều profile, cách suy nghĩ đáng tin cậy là **xác định profile nào đang hoạt động → xác định những tài liệu nào được nạp → áp dụng thứ tự ưu tiên nguồn cho từng khóa → kiểm tra điều kiện bean riêng**. Cách tiếp cận này giải thích được cả cấu hình bị ghi đè lẫn những trường hợp nhiều bean cùng được tạo ra.
