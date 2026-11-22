# Đặt active, default, include và group ở tài liệu hợp lệ

Spring Boot dùng **profile** để chọn những phần cấu hình và bean phù hợp với ngữ cảnh chạy, chẳng hạn `dev`, `test`, `staging` hoặc `prod`. Có bốn nhóm thuộc tính rất dễ nhầm: `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group.*`. Chúng đều liên quan đến tập profile được xét, nhưng **không có cùng ý nghĩa** và **không thể được khai báo tùy tiện trong mọi tài liệu cấu hình**.

Bài học này tập trung vào một quy tắc cốt lõi của Spring Boot Config Data: **các thuộc tính quyết định profile được kích hoạt phải được đặt ở tài liệu không đặc thù profile (non-profile-specific document), hoặc ở nguồn khởi động hợp lệ**. Một tài liệu chỉ được nạp sau khi profile đã được quyết định không phải nơi phù hợp để tự chọn lại active/default/include/group.

## 1. Bốn khái niệm cần phân biệt

| Thuộc tính | Mục đích | Ví dụ | Khi nào ảnh hưởng |
| --- | --- | --- | --- |
| `spring.profiles.active` | Chọn một hoặc nhiều profile hoạt động | `dev`, `prod` | Kích hoạt profile được chỉ định |
| `spring.profiles.default` | Chỉ định profile mặc định khi không có active profile | `local`, `none` | Chỉ có vai trò fallback nếu chưa có active profile |
| `spring.profiles.include` | Bổ sung các profile luôn cần đi cùng cấu hình này | `common`, `metrics` | Thêm profile bên cạnh những profile active khác |
| `spring.profiles.group.<name>` | Định nghĩa tên nhóm đại diện cho nhiều profile | `production → proddb, prodmq` | Khi tên nhóm được kích hoạt, các thành viên của nhóm được kích hoạt theo |

Ví dụ một ứng dụng có profile `prod` cho môi trường production, `proddb` cho cấu hình cơ sở dữ liệu production, `prodmq` cho message broker, và `metrics` cho một số bean giám sát. Bạn có thể đặt `spring.profiles.active=production` rồi dùng một **profile group** biến `production` thành tập profile liên quan. Hoặc cấu hình một profile `common` cần đi kèm mọi môi trường qua `include`.

Tuy cùng liên quan đến việc kích hoạt profile, chúng có ba câu hỏi khác nhau:

1. **Tôi đang chủ động chạy môi trường nào?** — `active`.
2. **Nếu chưa ai chỉ định môi trường thì dùng môi trường nào?** — `default`.
3. **Ngoài môi trường chính, có những profile đi kèm cố định hoặc theo nhóm nào?** — `include` và `group`.

## 2. Thế nào là một tài liệu cấu hình “hợp lệ” cho bốn thuộc tính này?

Trong cơ chế Config Data hiện đại, cần phân biệt hai loại tài liệu.

**Tài liệu không đặc thù profile (non-profile-specific document)** là tài liệu được xét mà không cần một profile cụ thể phải active trước đó. Ví dụ thông dụng:

~~~properties
# application.properties — phần cơ sở
spring.application.name=order-service
spring.profiles.active=dev
~~~

Hoặc một tài liệu YAML cơ sở:

~~~yaml
# application.yml — tài liệu cơ sở
spring:
  application:
    name: order-service
  profiles:
    active: dev
~~~

Tại phần cơ sở như trên, bạn có thể khai báo `active`, `default`, `include` và `group` theo mục đích, dù thực tế thường để `active` cho môi trường triển khai quyết định.

**Tài liệu đặc thù profile (profile-specific document)** là tài liệu chỉ được áp dụng sau khi profile liên quan đã được xác định. Hai dạng điển hình là:

- Tệp theo profile: `application-dev.properties`, `application-prod.yml`.
- Tài liệu được bật bằng `spring.config.activate.on-profile=dev` hoặc điều kiện tương đương trong YAML.

Chúng **không được dùng để khai báo `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` hoặc `spring.profiles.group.*`** theo quy tắc Config Data dành cho các thuộc tính chọn profile.

Quy tắc vị trí:

| Vị trí khai báo | `active` | `default` | `include` | `group.*` |
| --- | --- | --- | --- | --- |
| Phần cơ sở của `application.properties` | Được | Được | Được | Được |
| Phần cơ sở của `application.yml` | Được | Được | Được | Được |
| Tài liệu Config Data không đặc thù profile được import | Được, theo quy tắc ưu tiên nguồn | Được | Được | Được |
| `application-dev.properties` | Không | Không | Không | Không |
| `application-prod.yml` | Không | Không | Không | Không |
| Tài liệu được kích hoạt bởi `spring.config.activate.on-profile` | Không | Không | Không | Không |
| Command-line argument hoặc nguồn khởi động thích hợp | Có thể chỉ định tùy thuộc thuộc tính | Có thể | Có thể | Có thể |

Lý do của ràng buộc này rất thực tế: việc quyết định profile là một bước cần thiết để **biết tài liệu nào sẽ được nạp**. Nếu một tài liệu chỉ có hiệu lực sau khi `dev` active lại tự thêm hoặc thay profile ngay tại bước này, logic khởi động sẽ trở nên vòng lặp hoặc phụ thuộc thứ tự nạp khó đoán.

Điều kiện `spring.config.activate.on-profile` không phải là `spring.profiles.active`. Một cái **chọn tài liệu khi profile phù hợp**, cái kia **khởi động profile**. Phân biệt được hai vai trò này là chìa khóa để đặt thuộc tính đúng nơi.

## 3. spring.profiles.active: chọn profile hoạt động

`spring.profiles.active` xác định danh sách profile mà ứng dụng sẽ kích hoạt. Cấu hình trong tài liệu cơ sở:

~~~properties
# application.properties
spring.profiles.active=dev
~~~

Tương đương trong YAML:

~~~yaml
# application.yml
spring:
  profiles:
    active: dev
~~~

Bạn cũng có thể đưa nhiều profile:

~~~properties
spring.profiles.active=dev,metrics
~~~

Khi khởi động, Spring Boot dùng tập active profile để xét cấu hình theo profile và điều kiện trên bean. Nếu có `application-dev.yml` hoặc `application-metrics.properties` thuộc vị trí Config Data được nạp, những tài liệu tương ứng có thể được xét.

### Kích hoạt profile từ command-line

Trong triển khai thực tế, một JAR thường được chạy ở nhiều môi trường. Khi đó có thể để tệp cơ sở không cố định active profile và chỉ định lúc khởi động:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Hoặc:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,metrics
~~~

Có thể dùng Java system property:

~~~bash
java -Dspring.profiles.active=prod -jar order-service.jar
~~~

Hay biến môi trường được process nhận:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

Lệnh xuất biến môi trường trên theo cú pháp Unix-like shell. Trên Windows PowerShell, có thể dùng:

~~~powershell
$env:SPRING_PROFILES_ACTIVE="prod"
java -jar order-service.jar
~~~

Ví dụ này cho thấy active profile là **đầu vào khởi động** chứ không nhất thiết phải hardcode trong source. Nếu cùng một thuộc tính xuất hiện ở nhiều nguồn, thứ tự ưu tiên `PropertySource` của Spring Boot quyết định giá trị hiệu lực; thông thường command-line có thể ghi đè cấu hình từ `application.yml`.

### Một ví dụ có tài liệu theo profile

~~~text
src/main/resources/
  application.yml
  application-dev.yml
  application-prod.yml
~~~

Tệp cơ sở:

~~~yaml
# application.yml
app:
  client:
    connect-timeout: 3s
~~~

Tệp dev:

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8081
    connect-timeout: 500ms
~~~

Tệp prod:

~~~yaml
# application-prod.yml
app:
  client:
    base-url: https://internal-api.example.test
    connect-timeout: 2s
~~~

Khi chạy `--spring.profiles.active=dev`, Spring Boot xét cấu hình cho `dev`. Khi chạy `--spring.profiles.active=prod`, cấu hình `prod` được xét. **Các tệp theo profile chứa giá trị nghiệp vụ phù hợp**, không dùng để viết lại `spring.profiles.active`.

## 4. spring.profiles.default: fallback khi không có active profile

Spring có khái niệm **default profiles**. Nếu bạn không kích hoạt profile cụ thể, Spring dùng profile mặc định; theo thiết lập thông thường, profile mặc định có tên `default`.

Bạn có thể chọn một tên khác trong tài liệu cơ sở:

~~~properties
# application.properties
spring.profiles.default=local
~~~

Hoặc YAML:

~~~yaml
spring:
  profiles:
    default: local
~~~

Khi không có active profile do cấu hình hoặc khởi động chỉ định, Spring Boot có thể dùng `local` làm profile mặc định để xét cấu hình và bean liên quan. Ví dụ `application-local.yml` có thể được áp dụng theo profile mặc định.

Nếu chạy với:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

thì `prod` là active profile đã được chọn; `local` không được kích hoạt **chỉ vì** nó là giá trị của `spring.profiles.default`. Ý nghĩa của `default` là dự phòng, không phải “luôn thêm profile này”.

### Khi không muốn profile mặc định có tên default

Spring Boot cho phép đặt:

~~~properties
spring.profiles.default=none
~~~

Giá trị `none` là cách cấu hình được tài liệu Spring Boot mô tả để không dùng profile mặc định thông thường khi chưa có active profile. Tuy nhiên, điều này không làm biến mất toàn bộ cấu hình cơ sở: `application.properties` hoặc phần không đặc thù profile trong `application.yml` vẫn được nạp theo cơ chế Config Data.

### Đọc active và default từ Environment

Trong mã Java, hai khái niệm có API riêng:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ProfileReporter {
    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    public String describeProfiles() {
        return "active=" + Arrays.toString(environment.getActiveProfiles())
            + ", default=" + Arrays.toString(environment.getDefaultProfiles());
    }
}
~~~

`getActiveProfiles()` phản ánh tập profile đang active. `getDefaultProfiles()` phản ánh tập profile mặc định. Đừng kết luận “không có profile được dùng” chỉ vì danh sách active profile trống; default profile vẫn có ý nghĩa với điều kiện bean hoặc tài liệu profile-specific.

## 5. spring.profiles.include: thêm profile đi kèm

Giả sử nhóm bean `metrics` hoặc `common` cần được bật ở hầu hết tình huống chạy. Có thể dùng `spring.profiles.include` trong **tài liệu cơ sở**:

~~~properties
# application.properties
spring.profiles.include=common,metrics
~~~

YAML:

~~~yaml
# application.yml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

Nếu ngoài ra lúc chạy chỉ định `--spring.profiles.active=dev`, Spring Boot có thể kích hoạt `dev` cùng các profile được include. Tệp `application-common.yml` hoặc các bean `@Profile("metrics")` khi phù hợp sẽ được xét.

Điểm phân biệt:

- `active` là danh sách profile chính được chọn.
- `include` là các profile thêm vào, **không phải danh sách thay thế `active`**.
- `include` nên được dùng cho nhóm profile có tính chất đi kèm rộng rãi, không nên dựa vào một tài liệu `application-prod.yml` để chỉ include một profile theo `prod`.

### Quy tắc vị trí bắt buộc với include

Đây là cách viết **không hợp lệ** trong Config Data theo profile:

~~~properties
# application-prod.properties — KHÔNG HỢP LỆ
spring.profiles.include=metrics
~~~

Tương tự, không khai báo include trong tài liệu YAML bị điều kiện `spring.config.activate.on-profile` chi phối:

~~~yaml
# application.yml — ví dụ SAI
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics  # Không hợp lệ ở tài liệu profile-specific
~~~

Nếu mục đích thực sự là “**mỗi khi `prod` được bật, tự bật `metrics`**”, hãy dùng **profile group** ở tài liệu cơ sở, thay vì include trong tài liệu `prod`.

### Vì sao include không phải key override thông thường?

`spring.profiles.include` được Spring Boot xử lý khi xây dựng các profile đang hoạt động. Tài liệu Spring Boot nêu rằng include được xử lý theo từng `PropertySource`, khác với cách chỉ chọn một giá trị cuối cho một property nghiệp vụ thông thường. Vì thế, đừng thiết kế ứng dụng dựa trên giả định “ghi một include ở nguồn ưu tiên cao sẽ luôn xóa được toàn bộ profile đã include ở nguồn khác”.

Khi cần tính toán chính xác tập profile trong một triển khai, hãy xem các nguồn có thể đưa `spring.profiles.include` vào môi trường khởi động và kiểm tra kết quả active profiles thực tế.

## 6. spring.profiles.group: một tên đại diện nhiều profile

Đôi khi ứng dụng cần nhiều profile kỹ thuật luôn đi cùng một ngữ cảnh triển khai. Ví dụ khi chạy production cần cấu hình database production, message broker production và audit production.

Thay vì yêu cầu mọi người nhập:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod,proddb,prodmq,prodaudit
~~~

có thể định nghĩa **profile group** trong tài liệu cơ sở:

~~~properties
# application.properties — hợp lệ
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
spring.profiles.group.production[2]=prodaudit
~~~

Sau đó kích hoạt tên nhóm:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

Khi tên `production` được kích hoạt, Spring Boot mở rộng nhóm để các profile `proddb`, `prodmq` và `prodaudit` cũng được xét. Tên nhóm ở đây là `production`; nó không bắt buộc phải bằng `prod`.

Trong YAML:

~~~yaml
# application.yml — phần cơ sở
spring:
  profiles:
    group:
      production:
        - proddb
        - prodmq
        - prodaudit
~~~

Mẫu trên có thể sử dụng với các tệp cấu hình:

~~~text
src/main/resources/
  application.yml
  application-proddb.yml
  application-prodmq.yml
  application-prodaudit.yml
~~~

Khi dùng `--spring.profiles.active=production`, những tài liệu theo profile được kích hoạt từ nhóm có thể bổ sung giá trị phù hợp.

### Group không phải include vô điều kiện

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Chỉ có group `production` được định nghĩa; chạy `--spring.profiles.active=dev` | Không tự kích hoạt các member của `production` |
| Có group `production`; chạy `--spring.profiles.active=production` | Kích hoạt các member được khai báo trong nhóm |
| Có `spring.profiles.include=metrics` ở tài liệu cơ sở | `metrics` được bổ sung theo include, kể cả khi chạy profile khác |
| Không có active profile và đã đặt `spring.profiles.default=local` | Dùng profile mặc định theo cơ chế default; không tự bật `production` chỉ vì group tồn tại |

**Group là định nghĩa quan hệ giữa các profile; bản thân khai báo group không phải lệnh kích hoạt group ngay lập tức.** Điều kiện kích hoạt group là tên group xuất hiện trong tập profile được bật theo cơ chế hợp lệ.

### Vị trí khai báo group

Những khai báo sau **không hợp lệ** nếu nằm trong `application-prod.yml`:

~~~yaml
# application-prod.yml — SAI VỊ TRÍ
spring:
  profiles:
    group:
      prod:
        - proddb
        - prodmq
~~~

Tài liệu `application-prod.yml` đã là tài liệu profile-specific. Hãy chuyển khối `spring.profiles.group` lên tài liệu cơ sở `application.yml`, hoặc nguồn cấu hình không đặc thù profile phù hợp.

## 7. Bảng quyết định: dùng active, default, include hay group?

| Nhu cầu | Cơ chế đề xuất | Nơi đặt |
| --- | --- | --- |
| Chạy JAR ở production | `spring.profiles.active=prod` | Command-line, biến môi trường hoặc nguồn khởi động thích hợp |
| Máy lập trình chưa chỉ định active profile thì dùng cấu hình local | `spring.profiles.default=local` | Phần cơ sở của Config Data |
| Mọi ngữ cảnh chạy cần có một profile chung | `spring.profiles.include=common` | Phần cơ sở của Config Data |
| Bật một profile đồng thời kéo theo 3 profile kỹ thuật | `spring.profiles.group.production[...]` | Phần cơ sở của Config Data |
| Chỉ áp dụng timeout khi `prod` đã active | `spring.config.activate.on-profile=prod` | Tài liệu theo điều kiện, chỉ đặt key nghiệp vụ |
| Bean chỉ tồn tại trong `prod` | `@Profile("prod")` | Khai báo bean hoặc lớp cấu hình |
| Địa chỉ DB khác ở môi trường dev và prod | `application-dev.yml` và `application-prod.yml` | Các tài liệu profile-specific, chứa key nghiệp vụ |

Có thể kết hợp các cơ chế, nhưng cần tránh đặt tên profile khó hiểu. Ví dụ `prod` cho môi trường chính và `proddb` cho hạ tầng là những vai trò khác nhau; tên nhóm `production` có thể diễn đạt rõ đây là một tổ hợp.

## 8. Ví dụ cấu trúc dự án hoàn chỉnh

Giả sử ứng dụng cần:

- Mặc định dùng `local` khi developer không truyền active profile.
- Luôn có `common` cho các thiết lập dùng chung.
- Khi chạy production, kích hoạt `proddb` và `prodmq`.
- Cấu hình thời gian chờ thay đổi theo môi trường mà không điều khiển active profile trong file theo profile.

Cấu trúc:

~~~text
order-service/
  src/main/resources/
    application.yml
    application-local.yml
    application-common.yml
    application-production.yml
    application-proddb.yml
    application-prodmq.yml
~~~

**Tệp cơ sở `application.yml` — nơi đặt các thuộc tính chọn profile:**

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    default: local
    include:
      - common
    group:
      production:
        - proddb
        - prodmq

app:
  client:
    connect-timeout: 3s
    max-retries: 2
~~~

**`application-local.yml` — chỉ chứa giá trị dành cho local:**

~~~yaml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 700ms

logging:
  level:
    com.example.orders: DEBUG
~~~

**`application-common.yml` — cấu hình dùng chung:**

~~~yaml
app:
  feature:
    audit-enabled: true
~~~

**`application-production.yml` — giá trị nghiệp vụ của ngữ cảnh production:**

~~~yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s

logging:
  level:
    com.example.orders: INFO
~~~

**`application-proddb.yml` — thông số database production:**

~~~yaml
app:
  database:
    pool-size: 20
~~~

**`application-prodmq.yml` — thông số message broker production:**

~~~yaml
app:
  messaging:
    consumers: 8
~~~

Lưu ý ở ví dụ này, các key `app.database.*` và `app.messaging.*` là ví dụ thuộc tính tùy biến; ứng dụng cần bean hoặc mã thực sự đọc chúng. Chúng không tự thay đổi datasource hay message broker chỉ vì xuất hiện trong YAML.

### Trường hợp A — không truyền active profile

~~~bash
java -jar order-service.jar
~~~

Do cấu hình cơ sở chỉ định `spring.profiles.default=local`, `local` đóng vai trò default khi không có active profile khác. `common` được thêm qua include. Trong giả định không có nguồn khác ghi đè, các key local như `app.client.base-url` có giá trị từ `application-local.yml`.

### Trường hợp B — chạy production

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

Khi đó `production` được kích hoạt từ command-line, nên nhóm mở rộng thêm `proddb` và `prodmq`. `common` vẫn là profile include. `local` không được dùng như fallback vì đã có active profile.

### Trường hợp C — chạy development nhưng cần common

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Nếu có `application-dev.yml` ở phạm vi tìm Config Data, nó được xét theo `dev`. `common` vẫn được include từ tài liệu cơ sở. Group `production` không tự kích hoạt vì không có yêu cầu bật group.

## 9. Phiên bản dùng application.properties thay vì YAML

Cùng một ý tưởng có thể viết dưới dạng properties:

~~~properties
# application.properties
spring.application.name=order-service
spring.profiles.default=local
spring.profiles.include=common
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq

app.client.connect-timeout=3s
app.client.max-retries=2
~~~

File profile-specific hợp lệ:

~~~properties
# application-production.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=2s
~~~

~~~properties
# application-proddb.properties
app.database.pool-size=20
~~~

~~~properties
# application-prodmq.properties
app.messaging.consumers=8
~~~

**Đừng đặt khối `spring.profiles.group.production[...]` vào `application-production.properties`.** Mặc dù tên tệp có vẻ là chỗ hợp lý để “mô tả production”, nó chỉ được xét sau khi production đã là profile đang hoạt động. Định nghĩa group thuộc phần chọn profile, cần nằm trong tài liệu không đặc thù profile.

## 10. Multi-document YAML: đặt điều kiện ở đâu?

Một tệp YAML có thể chứa nhiều tài liệu, phân cách bởi `---`. Tài liệu đầu tiên không có điều kiện có thể định nghĩa các profile policy; tài liệu sau chứa giá trị theo một profile:

~~~yaml
# application.yml — tài liệu cơ sở, HỢP LỆ
spring:
  profiles:
    default: local
    group:
      production:
        - proddb
        - prodmq

app:
  client:
    connect-timeout: 3s

---
# Tài liệu chỉ dùng khi production đang active
spring:
  config:
    activate:
      on-profile: production

app:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
~~~

Ở đây, `spring.config.activate.on-profile` là **điều kiện nạp tài liệu**. Phần dưới `---` không thay đổi tập active/default/include/group; nó chỉ cung cấp key nghiệp vụ khi điều kiện đúng.

### Cách viết sai: active trong tài liệu điều kiện

~~~yaml
# KHÔNG HỢP LỆ
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: dev
  profiles:
    active: metrics
~~~

Tài liệu thứ hai chỉ được xét khi `dev` active; nó lại cố khai báo `spring.profiles.active`, là thuộc tính điều khiển profile. Spring Boot có thể từ chối bằng lỗi dạng `InvalidConfigDataPropertyException` vì khóa này không được phép trong tài liệu profile-specific.

**Sửa đúng:** nếu `metrics` luôn đi cùng mọi profile, dùng `spring.profiles.include=metrics` ở tài liệu cơ sở. Nếu chỉ khi `dev` active mới cần `metrics`, dùng group ở tài liệu cơ sở:

~~~yaml
spring:
  profiles:
    group:
      dev:
        - metrics

---
spring:
  config:
    activate:
      on-profile: dev

app:
  diagnostics:
    verbose: true
~~~

Khi `dev` được kích hoạt, group `dev` làm `metrics` được xét. Giá trị `app.diagnostics.verbose` thuộc tài liệu condition và vẫn hợp lệ.

## 11. Multi-document properties: ranh giới #---

Spring Boot cũng hỗ trợ nhiều tài liệu trong một `application.properties` thông qua dấu phân cách tài liệu đặc biệt `#---`:

~~~properties
# application.properties — tài liệu cơ sở
spring.profiles.default=local
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
app.client.connect-timeout=3s

#---
spring.config.activate.on-profile=production
app.client.connect-timeout=2s
app.client.base-url=https://api.example.test
~~~

Tài liệu đầu tiên có thể quyết định default và group; tài liệu thứ hai chỉ mô tả giá trị được sử dụng khi `production` đã hoạt động.

Tương tự YAML, không được cố đưa `spring.profiles.include`, `spring.profiles.active` hoặc `spring.profiles.default` vào tài liệu bên dưới `#---` nếu nó đã được kích hoạt bởi `spring.config.activate.on-profile`.

Dấu `#---` có ý nghĩa đặc biệt trong cơ chế multi-document properties của Spring Boot; đây không phải cách nói rằng mọi trình đọc `java.util.Properties` sẽ tự hiểu và phân tách nhiều tài liệu. Để tránh lỗi, hãy dùng cú pháp phân cách tài liệu được Spring Boot quy định thay vì sáng tạo dấu phân cách tùy ý.

## 12. Khi một tài liệu được import có được khai báo active/default/include/group không?

`spring.config.import` cho phép nhập một tài liệu Config Data từ `classpath:`, `file:` hoặc một dạng location khác mà Spring Boot hỗ trợ. **Điều quan trọng không phải chỉ là import từ đâu, mà tài liệu được import có phải profile-specific hay không.**

Ví dụ tài liệu cơ sở:

~~~properties
# application.properties
spring.config.import=classpath:config/profile-policy.properties
~~~

Tài liệu được import:

~~~properties
# config/profile-policy.properties — tài liệu không đặc thù profile
spring.profiles.default=local
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Đây là cách tổ chức có thể hợp lệ trong cơ chế Config Data: các thuộc tính được khai báo trong một tài liệu không đặc thù profile dù tệp nằm ở đường dẫn phụ.

Ngược lại, nếu một import chỉ xuất hiện trong một tài liệu `on-profile: dev` và tài liệu được import chứa `spring.profiles.active` hoặc thuộc tính chọn profile khác, Spring Boot có thể coi dữ liệu đó không hợp lệ do nó thuộc chuỗi nạp đặc thù profile. Không nên dùng import để lách quy tắc tài liệu profile-specific.

Cần phân biệt với trường hợp import một file có cấu trúc multi-document: chỉ phần dữ liệu không đặc thù profile phù hợp mới là nơi hợp lệ cho thuộc tính chọn profile; phần bị điều kiện `on-profile` ràng buộc vẫn phải tuân theo hạn chế.

## 13. @Profile quyết định bean, không quyết định active profile

Annotation `@Profile` ở Spring Framework dùng để điều kiện hóa việc đăng ký bean hoặc lớp cấu hình. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class ClientTransportConfig {

    @Bean
    @Profile("dev")
    ClientTransport localTransport() {
        return new LocalClientTransport();
    }

    @Bean
    @Profile("production")
    ClientTransport productionTransport() {
        return new RemoteClientTransport();
    }
}
~~~

Trong ví dụ minh họa này, `ClientTransport`, `LocalClientTransport` và `RemoteClientTransport` là các kiểu do ứng dụng tự định nghĩa. Khi profile `production` active, bean có `@Profile("production")` đủ điều kiện được đăng ký.

Có thể dùng biểu thức profile theo cú pháp Spring, ví dụ `@Profile("production & proddb")` hoặc `@Profile("!dev")` khi muốn điều kiện theo nhóm profile. Nhưng hãy tránh tạo tổ hợp bean mơ hồ: việc một bean có tồn tại hay không nên có logic rõ ràng cho các tổ hợp profile có thể hoạt động.

**Đặt profile ở hai tầng khác nhau:**

- `spring.profiles.active/default/include/group`: chính sách xây dựng tập profile ở giai đoạn khởi động.
- `@Profile(...)` hoặc `spring.config.activate.on-profile`: điều kiện xem bean hay tài liệu có áp dụng với tập profile đã được xác định không.

Không có hành vi “thấy `@Profile("prod")` thì Spring tự bật `prod`”. Annotation chỉ kiểm tra điều kiện; nó không kích hoạt tên profile.

## 14. Bẫy khi có nhiều active profile

Có thể khai báo nhiều profile:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev,metrics
~~~

Nếu cả `application-dev.yml` và `application-metrics.yml` cùng chứa `app.logging.level`, giá trị hiệu lực được quyết định bởi quy tắc Config Data precedence, thứ tự profile và những nguồn ưu tiên khác. Đừng lấy một biểu thức `@Profile` hay một dòng trên file để kết luận luôn biết giá trị thắng.

Trong trường hợp cần ghi đè dữ liệu giữa nhiều profile, Spring Boot hỗ trợ thứ tự profile trong cơ chế Config Data; khi nhiều tài liệu theo profile cùng định nghĩa một property, thứ tự kích hoạt có thể ảnh hưởng đến tài liệu thắng. Tuy nhiên, còn cần xét xem key nằm trong tệp nào, có import hay không và có command-line override hay không.

Nếu dùng group `production`, nhóm member góp thêm profile vào tập hoạt động. Điều đó cũng ảnh hưởng đến các tệp có hậu tố `-proddb` hoặc `-prodmq`. Nên hạn chế định nghĩa cùng một key nghiệp vụ trong nhiều tệp kỹ thuật nếu không có lý do rõ ràng.

### Nhóm profile lồng nhau và tên profile

Về mặt thiết kế, các group nên nhỏ và rõ chức năng. Không nên dựng graph nhóm nhiều tầng hoặc quan hệ vòng mà không có yêu cầu cụ thể. Các tên `dev`, `prod`, `proddb`, `metrics` nên được định nghĩa nhất quán trong tài liệu của dự án để tránh nhầm “profile chủ” và “profile thành viên”.

## 15. Trường hợp khởi động: active, default, include, group kết hợp

Giả sử `application.properties` (phần cơ sở) có:

~~~properties
spring.profiles.default=local
spring.profiles.include=common
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Các tình huống:

| Khởi động | Profile chủ đạo | Các profile được thêm | Điều cần nhớ |
| --- | --- | --- | --- |
| Không chỉ định `spring.profiles.active` | `local` thông qua default | `common` qua include | Default chỉ có vai trò khi chưa có active profile |
| `--spring.profiles.active=dev` | `dev` | `common` qua include | Group production không tự mở |
| `--spring.profiles.active=production` | `production` | `proddb`, `prodmq` qua group; `common` qua include | Group mở rộng khi tên group active |
| `--spring.profiles.active=prod` | `prod` | `common` qua include | Không tự kích hoạt group tên `production` |
| `--spring.profiles.active=production,metrics` | `production` và `metrics` | `proddb`, `prodmq`, `common` | Có thể kết hợp nhiều active profile |

Bảng này diễn tả **các mối quan hệ cấu hình** trong ví dụ. Khi triển khai thật, dùng `Environment.getActiveProfiles()` để quan sát active profile thực tế; không nên đoán máy đang chạy profile nào chỉ từ tên hostname hoặc thư mục.

## 16. Hai lỗi phổ biến nhất do đặt sai vị trí

### Lỗi A: active trong application-dev.yml

~~~yaml
# application-dev.yml — SAI
spring:
  profiles:
    active: metrics
~~~

**Vì sao sai?** `application-dev.yml` là tài liệu profile-specific; nó chỉ được xét khi `dev` phù hợp. Tài liệu đó không được dùng để xác định lại `spring.profiles.active`.

**Cách sửa nếu `metrics` luôn đi cùng `dev`:**

~~~yaml
# application.yml — tài liệu cơ sở
spring:
  profiles:
    group:
      dev:
        - metrics
~~~

Tệp `application-dev.yml` chỉ giữ giá trị của `dev`:

~~~yaml
app:
  diagnostics:
    verbose: true
~~~

### Lỗi B: include trong tài liệu on-profile

~~~yaml
# application.yml — SAI ở tài liệu thứ hai
spring:
  application:
    name: order-service

---
spring:
  config:
    activate:
      on-profile: production
  profiles:
    include: proddb
~~~

**Vì sao sai?** Tài liệu có `spring.config.activate.on-profile` là tài liệu theo điều kiện profile, không được khai báo `spring.profiles.include`.

**Cách sửa nếu muốn production kéo theo proddb:**

~~~yaml
# application.yml — HỢP LỆ
spring:
  profiles:
    group:
      production:
        - proddb

---
spring:
  config:
    activate:
      on-profile: production

app:
  client:
    connect-timeout: 2s
~~~

### Lỗi C: default trong application-local.properties

~~~properties
# application-local.properties — SAI
spring.profiles.default=local
~~~

Đây cũng là thuộc tính quyết định profile. Hãy đặt `spring.profiles.default=local` trong `application.properties` hoặc ở nguồn khởi động phù hợp. Không nên dùng chính tệp `application-local.properties` để cố định nghĩa fallback cho việc chọn tệp local.

### Lỗi D: group được định nghĩa sau dấu #--- ở tài liệu đã bị ràng buộc profile

~~~properties
# application.properties — SAI ở tài liệu thứ hai
spring.application.name=order-service

#---
spring.config.activate.on-profile=production
spring.profiles.group.production[0]=proddb
~~~

Dù nằm trong cùng tệp vật lý `application.properties`, dòng group thuộc **tài liệu logic thứ hai** đã bị ràng buộc profile. Nó vẫn không hợp lệ. Khi xác định vị trí được phép, hãy phân biệt **tài liệu logic** với **tệp vật lý**.

## 17. Cách tổ chức chính sách profile để dễ bảo trì

Một cách tổ chức rõ ràng là giữ “chính sách profile” ở đầu luồng cấu hình và chỉ đặt “giá trị nghiệp vụ” trong các tài liệu chuyên biệt:

~~~text
application.yml
  ├─ spring.profiles.default
  ├─ spring.profiles.include
  ├─ spring.profiles.group.*
  └─ key nghiệp vụ mặc định

application-dev.yml
  └─ giá trị nghiệp vụ cho dev

application-production.yml
  └─ giá trị nghiệp vụ cho production

application-proddb.yml
  └─ giá trị DB production

application-prodmq.yml
  └─ giá trị broker production

Command line / environment
  └─ spring.profiles.active=...
~~~

Nếu một dự án có nhiều service, có thể chọn quy ước thống nhất: `active` do môi trường triển khai quyết định; `default` phục vụ developer; `include` dành cho profile thực sự luôn đi kèm; `group` mô tả thành phần bắt buộc của một ngữ cảnh vận hành.

Khi tên profile quá rộng, như `production` vừa đại diện môi trường vừa đại diện hạ tầng, có thể tách tên member để tránh trùng mục đích. Dù dùng cấu trúc nào, hãy mô tả ý nghĩa tên profile để người vận hành biết chỉ cần kích hoạt group name hay phải liệt kê từng member.

## 18. Quy trình đọc lỗi liên quan đến profile

Khi ứng dụng không khởi động hoặc giá trị config thay đổi bất ngờ:

**Bước 1 — Xác định thông điệp lỗi.** Nếu thấy thông báo kiểu `InvalidConfigDataPropertyException` hoặc nội dung nói `spring.profiles.active` / `spring.profiles.include` không hợp lệ trong profile-specific resource, ưu tiên kiểm tra **vị trí khai báo**.

**Bước 2 — Kiểm tra nguồn chứa thuộc tính.** Dòng nằm trong `application.yml` phần đầu, trong `application-prod.yml`, hay trong đoạn dưới `---` có `on-profile`? Cùng một file vật lý nhưng khác tài liệu logic có thể cho kết quả khác.

**Bước 3 — Xác định active profile được đặt từ đâu.** Kiểm tra command-line, system property, biến môi trường và Config Data không đặc thù profile. Với nguồn có cùng `spring.profiles.active`, cần xét quy tắc ưu tiên; không giả định giá trị trong file luôn thắng.

**Bước 4 — Kiểm tra default.** Nếu không có active profile do người dùng cấp, `spring.profiles.default` có thể làm một tài liệu theo profile được áp dụng. Đừng nhầm default với một profile luôn active.

**Bước 5 — Kiểm tra include và group.** Tên nhóm được kích hoạt chưa? Include nằm trong tài liệu cơ sở chưa? Group member có tệp cấu hình hoặc bean tương ứng không? Tên profile có nhất quán về chính tả không?

**Bước 6 — Kiểm tra key nghiệp vụ và thứ tự nguồn.** Sau khi xác định tập profile, nếu `app.client.connect-timeout` vẫn khác dự kiến, hãy xét precedence giữa các tệp Config Data, import, command-line và những nguồn cấu hình liên quan.

**Bước 7 — Đọc Environment.** Sử dụng `getActiveProfiles()` và `getDefaultProfiles()`, hoặc công cụ chẩn đoán cấu hình được bảo vệ phù hợp. Không in bí mật hoặc cho truy cập công khai endpoint chỉ để gỡ lỗi profile.

## 19. Bài thực hành: xác định hợp lệ hay không

### Bài 1 — active ở tài liệu cơ sở

~~~properties
# application.properties
spring.profiles.active=dev
~~~

**Đáp án:** hợp lệ về vị trí. Tuy nhiên, vì active đã được hardcode trong artifact, khi triển khai nhiều môi trường nên cân nhắc truyền từ command-line hoặc biến môi trường.

### Bài 2 — active trong file dev

~~~properties
# application-dev.properties
spring.profiles.active=prod
~~~

**Đáp án:** không hợp lệ với Config Data profile-specific. Không dùng tệp được bật bởi `dev` để tự chọn lại `prod`. Chọn profile từ nguồn khởi động thích hợp.

### Bài 3 — include trong file cơ sở

~~~properties
# application.properties
spring.profiles.include=common,metrics
~~~

**Đáp án:** hợp lệ về vị trí. Mục đích là thêm các profile `common` và `metrics` bên cạnh những profile active khác.

### Bài 4 — include theo điều kiện

~~~yaml
# application.yml
spring:
  application:
    name: order-service
---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    include: metrics
~~~

**Đáp án:** không hợp lệ vì include nằm trong tài liệu được điều kiện profile kích hoạt. Dùng group ở phần cơ sở nếu muốn `metrics` gắn với `prod`.

### Bài 5 — group chỉ định nghĩa, chưa kích hoạt

~~~properties
# application.properties
spring.profiles.group.production[0]=proddb
spring.profiles.group.production[1]=prodmq
~~~

Ứng dụng được chạy với `--spring.profiles.active=dev`. **Đáp án:** những member của group `production` không tự active chỉ vì group được định nghĩa. Cần kích hoạt tên group `production` hoặc profile thành viên qua một nguồn hợp lệ.

### Bài 6 — default và active cùng có mặt

~~~properties
# application.properties
spring.profiles.default=local
~~~

Chạy bằng:

~~~bash
java -jar order-service.jar --spring.profiles.active=production
~~~

**Đáp án:** ứng dụng có active profile `production`, nên `local` không được chọn chỉ với tư cách default. Nếu group `production` hợp lệ được định nghĩa trong tài liệu cơ sở, các member của group cũng được xét.

### Bài 7 — group trong tài liệu YAML thứ hai

~~~yaml
spring:
  application:
    name: order-service
---
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    group:
      prod:
        - proddb
~~~

**Đáp án:** không hợp lệ. Group được khai báo trong tài liệu thứ hai đã có điều kiện `on-profile`. Chuyển khai báo group lên tài liệu cơ sở, còn phần dưới `---` chỉ để giá trị áp dụng cho `prod`.

### Bài 8 — properties có tài liệu tách bởi #---

~~~properties
spring.profiles.default=local
spring.profiles.group.prod[0]=proddb

#---
spring.config.activate.on-profile=prod
app.database.pool-size=20
~~~

**Đáp án:** hợp lệ về vị trí. `default` và `group` ở tài liệu đầu tiên không đặc thù profile; tài liệu thứ hai chỉ đặt key nghiệp vụ có điều kiện. Nếu kích hoạt `prod`, `proddb` được xét; giá trị `app.database.pool-size` được áp dụng khi điều kiện phù hợp.

## 20. Bảng ghi nhớ cuối bài

| Bạn muốn làm gì? | Đặt ở đâu? | Không đặt ở đâu? |
| --- | --- | --- |
| Chỉ định profile chạy ứng dụng bằng `active` | Nguồn khởi động hoặc tài liệu cơ sở | `application-dev.yml` / tài liệu `on-profile` |
| Đặt profile dự phòng bằng `default` | Tài liệu cơ sở không đặc thù profile | File/profile document đặc thù |
| Thêm profile chung bằng `include` | Tài liệu cơ sở không đặc thù profile | File/profile document đặc thù |
| Khai báo profile group | Tài liệu cơ sở không đặc thù profile | File/profile document đặc thù |
| Chọn key nghiệp vụ cho `dev` | `application-dev.yml` hoặc tài liệu `on-profile: dev` | Không cần đưa policy active vào đây |
| Chọn bean cho `prod` | `@Profile("prod")` | Không cần tự đổi active trong annotation |
| Xem profile được bật thật | `Environment.getActiveProfiles()` | Không kết luận từ tên file đơn lẻ |

Có thể ghi nhớ một quy tắc thực hành: **những gì làm thay đổi tập profile được quyết định ở tài liệu không đặc thù profile hoặc ở nguồn khởi động; những gì phụ thuộc tập profile được đặt trong tài liệu đặc thù profile và điều kiện trên bean**. Với quy tắc này, `active`, `default`, `include` và `group` có chỗ đứng rõ ràng; các file `application-{profile}.yml` chỉ tập trung mô tả điều gì thay đổi khi profile đã được chọn.
