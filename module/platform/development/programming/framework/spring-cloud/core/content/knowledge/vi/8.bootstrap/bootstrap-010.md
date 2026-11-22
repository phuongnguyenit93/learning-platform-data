# Nhận diện việc đồng thời bật bootstrap và Config Data gây nạp lặp

> **Chương:** Bootstrap  
> **Module:** SPRING_CLOUD_CORE

Khi một ứng dụng Spring Boot dùng Spring Cloud Config, cấu hình từ xa có thể được nạp theo hai cơ chế: **bootstrap context kiểu cũ** và **Config Data API** của Spring Boot. Mỗi cơ chế có vòng đời và cách tích hợp riêng. Nếu dự án vô tình bật cả hai, Config Client có thể truy vấn Config Server qua hai đường khác nhau, làm xuất hiện nhiều lần nạp cùng bộ cấu hình, property source trùng lặp hoặc thứ tự ghi đè khó dự đoán.

Đây là vấn đề thường gặp khi nâng cấp ứng dụng Spring Cloud cũ. Dự án có thể vẫn giữ dependency `spring-cloud-starter-bootstrap` hoặc cờ `spring.cloud.bootstrap.enabled`, đồng thời đã thêm `spring.config.import=configserver:` theo cách cấu hình mới. Muốn xử lý đúng, cần nhận diện hai cơ chế, xác định đường nào đang hoạt động và chọn một cách nạp phù hợp với phiên bản Spring Boot/Spring Cloud.

## 1. Hai cơ chế nạp cấu hình từ xa

### 1.1. Legacy bootstrap context

Trong cơ chế bootstrap truyền thống, Spring Cloud tạo một **bootstrap context** trước ApplicationContext chính của ứng dụng. Context này có nhiệm vụ khởi tạo sớm một số thành phần và nguồn cấu hình dùng chung, chẳng hạn `PropertySourceLocator` của Spring Cloud Config Client.

Cấu hình thường được đặt trong `bootstrap.yml` hoặc `bootstrap.properties`. Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://config-server:8888
      name: order-service
      profile: production
~~~

Khi bootstrap được bật và Config Client được cấu hình theo chế độ legacy, bootstrap context có thể gọi Config Server để lấy property sources trước khi context ứng dụng chính hoàn tất khởi tạo.

Cơ chế legacy thường được bật qua dependency `spring-cloud-starter-bootstrap` hoặc cờ `spring.cloud.bootstrap.enabled=true` được cung cấp đủ sớm, ví dụ bằng system property hay biến môi trường trong các phiên bản hỗ trợ. Việc chỉ tạo file `bootstrap.yml` không bảo đảm file đó được nạp trong mọi cấu hình/version hiện đại; bootstrap phải thực sự được kích hoạt.

### 1.2. Config Data API

Từ Spring Boot 2.4, Spring Boot có cơ chế Config Data để nạp cấu hình sớm theo một quy trình thống nhất. Spring Cloud Config Client tích hợp với cơ chế này qua `spring.config.import`.

Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Với dependency Config Client tương thích, Spring Boot nhận diện location `configserver:` và yêu cầu Config Client nạp cấu hình từ Config Server trong giai đoạn xử lý Config Data.

Nếu Config Server là nguồn bắt buộc để ứng dụng hoạt động đúng, có thể bỏ tiền tố `optional:`:

~~~yaml
spring:
  config:
    import: "configserver:http://config-server:8888"
~~~

Khi location không có `optional:`, việc không thể nạp nguồn cấu hình bắt buộc có thể làm ứng dụng khởi động thất bại. `optional:` chỉ điều chỉnh cách xử lý khi nguồn không truy cập được; nó **không** tắt bootstrap legacy và cũng không ngăn Config Client được gọi từ một đường nạp khác.

### 1.3. So sánh hai cơ chế

| Tiêu chí | Legacy bootstrap | Config Data |
| --- | --- | --- |
| Điểm khởi tạo | Bootstrap context của Spring Cloud | Quy trình Config Data của Spring Boot |
| Cấu hình thường gặp | `bootstrap.yml`, `bootstrap.properties` | `application.yml` với `spring.config.import` |
| Cách bật | `spring-cloud-starter-bootstrap` hoặc cờ bootstrap sớm | `spring.config.import=configserver:` |
| Tích hợp nạp remote config | `PropertySourceLocator` trong bootstrap flow | Config Data resolver/loader của Config Client |
| Mục tiêu | Tương thích mô hình cấu hình Spring Cloud đời trước | Tích hợp nguồn ngoài vào cơ chế nạp cấu hình Boot hiện đại |
| Context riêng | Có bootstrap context đứng trước context ứng dụng | Không cần tạo bootstrap context legacy chỉ để nạp Config Data |
| Hướng dùng khi phát triển mới | Chỉ dùng khi có lý do tương thích cụ thể | Thường là lựa chọn ưu tiên với Boot 2.4+ và Cloud train hỗ trợ |

Hai cơ chế đều có thể nạp cấu hình từ cùng một Config Server, nhưng không nên bật đồng thời cho cùng mục đích nếu không có thiết kế rõ ràng.

## 2. Nạp lặp xảy ra như thế nào?

Giả sử một ứng dụng cũ có:

- Dependency `spring-cloud-starter-bootstrap`.
- `bootstrap.yml` cấu hình Config Server.
- `spring.cloud.bootstrap.enabled=true` được truyền từ môi trường chạy.

Sau đó dự án được nâng cấp và thêm vào `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu cả bootstrap legacy và Config Data đều hoạt động, hai luồng có thể cùng yêu cầu cấu hình từ xa:

~~~mermaid
flowchart TB
    A["Khởi động order-service"]
    A --> B["Legacy bootstrap được bật"]
    A --> C["Spring Boot Config Data xử lý import"]
    B --> D["Bootstrap context"]
    D --> E["Config Client: PropertySourceLocator"]
    C --> F["Config Client: Config Data resolver/loader"]
    E --> G["Yêu cầu Config Server"]
    F --> H["Yêu cầu Config Server"]
    G --> I["Remote property sources"]
    H --> I
    I --> J["Environment và các nguồn cấu hình"]
~~~

Sơ đồ minh họa hai **đường khởi tạo độc lập**. Tùy phiên bản, dependency, cách cấu hình và tích hợp cụ thể, chúng có thể tạo ra nhiều yêu cầu lấy cùng application/profile/label. Kết quả là cùng một tập thuộc tính từ xa có thể được đưa vào môi trường qua các property source khác nhau.

### 2.1. Điều gì có thể bị lặp?

Các biểu hiện thường gặp:

- Config Server ghi nhận nhiều request gần nhau từ cùng một instance client để lấy cùng application/profile/label.
- Log phía ứng dụng cho thấy bootstrap context khởi tạo và Config Data đồng thời xử lý `configserver:`.
- Environment có nhiều property source liên quan tới cấu hình từ xa hoặc nguồn bootstrap.
- Thời gian khởi động tăng vì ứng dụng thực hiện thêm lần gọi mạng.
- Một key xuất hiện ở nhiều property source và giá trị cuối cùng phụ thuộc thứ tự ưu tiên.
- Nếu cấu hình trên Config Server thay đổi giữa hai lần đọc, hai đường nạp có thể nhìn thấy hai trạng thái khác nhau.

Tên property source, cấu trúc log và số request chính xác có thể khác theo phiên bản Spring Boot/Spring Cloud. Vì vậy, không nên dựa vào một tên property source duy nhất để kết luận.

### 2.2. Nạp lặp không đồng nghĩa bean ứng dụng chắc chắn bị tạo hai lần

Cần phân biệt **nạp property source** và **đăng ký bean**. Việc Config Client lấy cùng dữ liệu hai lần không tự động chứng minh mọi bean nghiệp vụ bị khởi tạo hai lần. Bootstrap context là context riêng với vai trò khởi tạo sớm; Config Data là quy trình nạp cấu hình. Ảnh hưởng trực tiếp thường thấy là remote property source được lấy hoặc đưa vào môi trường qua nhiều luồng, còn việc bean nào được tạo phụ thuộc cấu trúc context và cấu hình ứng dụng.

Khi điều tra, hãy ghi rõ đang thấy hiện tượng nào:

1. Hai lần HTTP request tới Config Server.
2. Hai property source chứa cùng key.
3. Giá trị property cuối cùng khác dự kiến.
4. Bean hoặc auto-configuration thực sự bị tạo lặp.

Không gộp bốn hiện tượng này thành một kết luận duy nhất nếu chưa có bằng chứng.

## 3. Dấu hiệu nhận biết trong dự án

### 3.1. Kiểm tra dependency bootstrap

Tìm dependency `spring-cloud-starter-bootstrap` trong dependency khai báo trực tiếp hoặc dependency bắc cầu. Nếu dự án dùng Maven, có thể kiểm tra cây dependency:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-bootstrap
~~~

Với Gradle, có thể kiểm tra runtime classpath:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-bootstrap \
  --configuration runtimeClasspath
~~~

Nếu dependency xuất hiện gián tiếp, cần xác định thư viện nào kéo nó vào. Không nên xóa dependency bắc cầu một cách mù quáng; trước hết kiểm tra liệu một integration khác còn cần legacy bootstrap hay không.

### 3.2. Kiểm tra cờ bật bootstrap

Tìm các nguồn có thể cung cấp:

- `spring.cloud.bootstrap.enabled=true`
- `SPRING_CLOUD_BOOTSTRAP_ENABLED=true`
- `-Dspring.cloud.bootstrap.enabled=true`

Kiểm tra cả cấu hình triển khai, biến môi trường, JVM arguments, script chạy ứng dụng và cấu hình IDE. Cờ này cần được cung cấp đủ sớm cho quá trình bootstrap; khai báo muộn trong một nguồn chỉ được nạp sau bootstrap có thể không có tác dụng như mong đợi.

### 3.3. Kiểm tra Config Data import

Tìm các khai báo:

~~~yaml
spring:
  config:
    import:
      - "optional:configserver:http://config-server:8888"
~~~

`spring.config.import` có thể nằm trong `application.yml`, một tệp cấu hình ngoài hoặc nguồn được nạp sớm khác. Cần kiểm tra profile đang active và các file được nạp để không bỏ sót một import chỉ xuất hiện ở một môi trường.

### 3.4. Kiểm tra bootstrap config và application config

Một dấu hiệu dễ nhận ra là cùng ứng dụng vừa có cấu hình Config Server trong `bootstrap.yml`, vừa có `spring.config.import=configserver:` trong `application.yml`.

Ví dụ cấu hình dễ gây nhầm lẫn:

`bootstrap.yml`:

~~~yaml
spring:
  cloud:
    config:
      uri: http://config-server:8888
~~~

`application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu bootstrap legacy được kích hoạt, cả hai khối có thể tham gia vào hai cơ chế nạp. Cần xác định cơ chế nào là chủ đích và bỏ phần cấu hình dư thừa sau khi chuyển đổi.

## 4. Chẩn đoán bằng log và property source

Không nên kết luận nạp lặp chỉ vì thấy hai dòng log có chữ `config`. Một lần khởi động có thể truy vấn nhiều profile, label hoặc application name hợp lệ. Hãy đối chiếu **thời điểm, instance client, application, profile, label và endpoint** của từng request.

### 4.1. Tăng mức log có mục tiêu

Có thể bật log chi tiết tạm thời trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
    org.springframework.cloud.config.client: DEBUG
    org.springframework.cloud.bootstrap: DEBUG
~~~

Các logger trên giúp quan sát Config Data, Config Client và bootstrap ở nhiều phiên bản. Tên logger hoặc lượng chi tiết có thể thay đổi theo release; nếu một logger không tạo thông tin hữu ích, kiểm tra package logger của phiên bản đang chạy.

Không nên giữ TRACE/DEBUG quá lâu ở production vì log có thể lớn và đôi khi chứa thông tin nhạy cảm trong metadata cấu hình. Không bật log payload chứa secret.

### 4.2. Đối chiếu log phía Config Server

Nếu có quyền xem log server, hãy nhóm request theo:

- Thời gian và khoảng cách giữa các request.
- Tên ứng dụng, ví dụ `order-service`.
- Profile, ví dụ `production`.
- Label/branch được yêu cầu.
- Địa chỉ nguồn hoặc định danh client instance.
- Kết quả trả về và thời gian xử lý.

Ví dụ một request cho `order-service/production` và một request cho `order-service/production,observability` không nhất thiết là nạp lặp; chúng có thể đại diện cho hai tập profile khác nhau. Tương tự, retry do lỗi mạng hoặc failover Config Server cũng tạo thêm request hợp lệ.

Nghi vấn nạp lặp mạnh hơn khi cùng một client trong cùng lần khởi động gửi hai yêu cầu tương đương qua hai giai đoạn bootstrap và Config Data mà không có lý do về profile, label, retry hoặc refresh.

### 4.3. Kiểm tra Environment và Actuator

Nếu ứng dụng có Spring Boot Actuator và endpoint được cấu hình an toàn, endpoint `env` có thể giúp xem property source nào cung cấp một key. Endpoint `configprops` có thể cho biết cấu hình đã bind vào `@ConfigurationProperties` ra sao.

Khi kiểm tra:

- So sánh tên property source và origin nếu phiên bản cung cấp thông tin này.
- Xem cùng key có xuất hiện ở nhiều nguồn không.
- Xác định giá trị nào thực sự được bind vào bean.
- Chỉ expose endpoint trong phạm vi quản trị cần thiết; bật sanitization và bảo vệ bằng authentication/authorization.
- Không gửi hoặc lưu lại giá trị secret khi chia sẻ log hay báo cáo.

Property source trùng tên hoặc cùng chứa key không tự chứng minh hai lần gọi Config Server; cần đối chiếu với log request và cách các source được tạo.

## 5. Chọn một cơ chế nạp làm đường chính

Với ứng dụng hiện đại dùng Spring Boot 2.4+ và Spring Cloud release train tương thích, **Config Data thường là hướng nên chọn**. Legacy bootstrap chỉ nên giữ khi ứng dụng có yêu cầu tương thích hoặc integration cụ thể phụ thuộc vào bootstrap context.

### 5.1. Hướng A: dùng Config Data

Giữ Config Client dependency phù hợp và cấu hình import trong `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu Config Server là bắt buộc, bỏ `optional:` để lỗi kết nối được phát hiện ngay khi khởi động.

Khi chuyển sang hướng này, kiểm tra và loại bỏ những thành phần legacy không còn cần:

- Bỏ `spring-cloud-starter-bootstrap` nếu không còn integration nào cần bootstrap context.
- Bỏ `spring.cloud.bootstrap.enabled=true` khỏi biến môi trường/JVM arguments.
- Bỏ cấu hình Config Server trùng lặp trong `bootstrap.yml` nếu file đó chỉ phục vụ đường nạp legacy.
- Giữ lại các thuộc tính ứng dụng và profile phù hợp trong `application.yml` hoặc nguồn Config Data khác.
- Kiểm tra lại Config Client version theo Spring Cloud BOM tương thích với Spring Boot.

Không xóa `bootstrap.yml` chỉ dựa trên tên file nếu nó còn chứa cấu hình cho một integration legacy khác. Hãy kiểm tra chủ sở hữu và mục đích từng thuộc tính trước khi dọn.

### 5.2. Hướng B: giữ legacy bootstrap có chủ đích

Nếu dự án phải dùng một integration chỉ hỗ trợ bootstrap legacy ở phiên bản hiện tại, có thể giữ bootstrap context:

- Dùng `spring-cloud-starter-bootstrap` hoặc cách bật bootstrap được phiên bản hỗ trợ.
- Đặt cấu hình bootstrap cần thiết trong `bootstrap.yml`/`bootstrap.properties`.
- Giữ Config Client theo cơ chế legacy mà dự án đang sử dụng.
- Gỡ `spring.config.import=configserver:` nếu import này đang gọi lại cùng Config Server cho cùng mục đích.
- Ghi rõ lý do giữ legacy và kế hoạch chuyển đổi khi integration hỗ trợ Config Data.

Không bật đồng thời `spring-cloud-starter-bootstrap` và `spring.config.import=configserver:` chỉ để “chắc chắn” cấu hình được nạp. Điều đó có thể khiến cùng một nguồn remote được gọi qua hai luồng.

### 5.3. Bảng quyết định

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Ứng dụng mới, Spring Boot 2.4+ và Cloud train hỗ trợ Config Data | Ưu tiên `spring.config.import=configserver:` |
| Ứng dụng đã dùng Config Data, không còn integration legacy | Bỏ starter/cờ bootstrap legacy |
| Integration cũ bắt buộc dùng bootstrap context | Giữ legacy, tránh import Config Server lần hai |
| Có cả bootstrap và Config Data do migration dở dang | Chọn một đường chính, loại bỏ cấu hình dư thừa sau khi kiểm tra |
| Chưa rõ dependency nào kích hoạt bootstrap | Kiểm tra dependency tree và startup logs trước khi thay đổi |

## 6. Quy trình chuyển từ bootstrap legacy sang Config Data

Thực hiện chuyển đổi theo từng bước để dễ so sánh kết quả:

1. **Ghi nhận trạng thái hiện tại:** phiên bản Spring Boot, Spring Cloud release train, dependency Config Client, dependency bootstrap và các nguồn cấu hình đang hoạt động.
2. **Xác định mục đích của bootstrap:** kiểm tra `bootstrap.yml`, `spring.cloud.bootstrap.enabled` và các integration dùng `PropertySourceLocator`.
3. **Chọn đường nạp đích:** với Config Server tiêu chuẩn trên nền tảng hỗ trợ, chọn Config Data; nếu integration bắt buộc legacy, ghi rõ lý do giữ bootstrap.
4. **Chuyển cấu hình:** đưa `spring.config.import=configserver:` vào cấu hình được nạp đúng thời điểm; kiểm tra application name, profile, label và URI.
5. **Gỡ đường nạp trùng:** bỏ starter/cờ bootstrap hoặc Config Data import tương ứng với lựa chọn, không để hai đường cùng truy vấn cùng Config Server.
6. **Kiểm thử ở local/test:** xác nhận ứng dụng lấy được property mong đợi và không còn request dư.
7. **Kiểm thử profile:** xác nhận remote config đúng với `application/profile/label` của môi trường.
8. **Triển khai có kiểm soát:** kiểm tra startup time, log, property source và giá trị bean sau khi khởi động.
9. **Dọn cấu hình cũ:** chỉ xóa file và dependency không còn được sử dụng sau khi xác nhận không có integration khác phụ thuộc.

Không thay đổi đồng thời nhiều yếu tố như phiên bản Boot, Cloud, Config Server và cơ chế bootstrap nếu chưa có kiểm thử tương ứng. Khi nâng cấp lớn, hãy tách thay đổi dependency và thay đổi cơ chế nạp thành các bước có thể so sánh.

## 7. Những điều có thể trông giống nạp lặp nhưng là bình thường

Một ứng dụng có thể gửi nhiều request Config Server mà không phải do bật cả bootstrap lẫn Config Data:

- Có nhiều profile active và Config Client cần lấy các phần cấu hình tương ứng.
- Ứng dụng yêu cầu nhiều label hoặc dùng cấu hình theo branch.
- Config Client retry khi kết nối lỗi hoặc dùng nhiều địa chỉ/failover.
- Một refresh event yêu cầu tải cấu hình mới sau khi ứng dụng đã khởi động.
- Nhiều instance ứng dụng cùng khởi động; mỗi instance có request riêng.
- Một integration khác cũng truy vấn nguồn cấu hình từ xa.
- Test suite tạo nhiều ApplicationContext.

Vì vậy, số request tổng cộng không đủ để xác định lỗi. Cần nhóm request theo instance và lần khởi động, so sánh application/profile/label, rồi liên hệ với log bootstrap và Config Data.

### 7.1. Ví dụ phân loại

| Quan sát | Nhận định ban đầu |
| --- | --- |
| Một instance gửi hai request cùng application/profile/label: một trong bootstrap phase, một trong Config Data phase | Nghi vấn hai cơ chế cùng hoạt động |
| Một instance gửi request cho `production` và `production,observability` | Có thể là các profile/config set khác nhau |
| Hai pod khác nhau cùng lấy `order-service/production` | Có thể là mỗi instance khởi động bình thường |
| Một request ban đầu và một request sau refresh event | Có thể là hành vi refresh dự kiến |
| Nhiều request sau lỗi kết nối, có backoff | Có thể là retry |
| Cùng key xuất hiện trong hai property source | Cần kiểm tra nguồn tạo và thứ tự; chưa đủ kết luận request lặp |

## 8. Kiểm thử sau khi xử lý

Sau khi chọn một cơ chế, kiểm tra cả quá trình nạp và kết quả cuối cùng.

### 8.1. Kiểm tra cấu hình thực tế

Ví dụ cấu hình mong đợi:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Config Server trả về `catalog.client.base-url` cho profile `local`. Một test có thể xác nhận bean nhận đúng giá trị:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("local")
class RemoteConfigurationTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsRemoteCatalogConfiguration() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:8090");
    }
}
~~~

Test này cần môi trường Config Server hoặc cấu hình test tương ứng. Nếu muốn test thuần không phụ thuộc server, có thể dùng property override hoặc mock property source riêng; nhưng test đó không chứng minh kết nối Config Server hoạt động.

### 8.2. Checklist xác nhận không còn hai đường nạp

- [ ] Xác định rõ ứng dụng đang dùng Config Data hay legacy bootstrap.
- [ ] Không còn dependency/cờ bootstrap ngoài chủ đích.
- [ ] Không còn Config Data import trùng với Config Server nếu giữ legacy.
- [ ] Log khởi động thể hiện một luồng lấy remote config dự kiến.
- [ ] Request server được đối chiếu theo instance, application, profile và label.
- [ ] Giá trị cuối cùng trong Environment/bean đúng với môi trường.
- [ ] Profile-specific configuration vẫn hoạt động.
- [ ] Hành vi khi Config Server không truy cập được phù hợp với `optional:` hay bắt buộc.
- [ ] Dependency Boot/Cloud tương thích theo release train đang dùng.

## 9. Lỗi thường gặp và cách tránh

1. **Giữ `spring-cloud-starter-bootstrap` sau khi chuyển sang Config Data:** kiểm tra xem starter còn cần thiết không; nếu không, gỡ để tránh khởi tạo legacy bootstrap.
2. **Đặt `spring.config.import=configserver:` nhưng vẫn bật bootstrap Config Client:** hai luồng có thể cùng truy vấn remote config.
3. **Cho rằng `optional:` tắt Config Server:** `optional:` chỉ thay đổi hành vi khi nguồn không truy cập được; nó không vô hiệu hóa một đường nạp khác.
4. **Xóa toàn bộ `bootstrap.yml` mà không kiểm tra:** file có thể còn cấu hình legacy cho integration khác.
5. **Kết luận nạp lặp từ số request:** cần loại trừ nhiều profile, retry, label, refresh và nhiều instance.
6. **Cho rằng property source trùng là bean bị tạo trùng:** phải kiểm tra riêng context/bean nếu nghi ngờ vấn đề bean lifecycle.
7. **Chuyển cơ chế mà không kiểm tra compatibility:** dùng Spring Cloud BOM/release train được hỗ trợ với phiên bản Spring Boot.
8. **Không kiểm tra profile khi chuyển đổi:** Config Server trả cấu hình theo application/profile/label; sai profile có thể làm ứng dụng nhận bộ giá trị khác.
9. **Bật log TRACE lâu dài ở production:** chỉ dùng chẩn đoán có kiểm soát, tránh lộ thông tin nhạy cảm và tăng dung lượng log.

## 10. Kết luận

Bootstrap legacy và Config Data đều là cách đưa cấu hình từ xa vào ứng dụng, nhưng chúng tham gia vào hai giai đoạn khởi tạo khác nhau. Nếu ứng dụng vừa bật bootstrap context vừa khai báo `spring.config.import=configserver:` cho cùng Config Server, có nguy cơ nạp remote config qua hai đường, tạo request dư hoặc property source trùng lặp.

Để chẩn đoán chính xác, cần kiểm tra dependency, cờ bootstrap, `bootstrap.yml`, Config Data import, log ở cả phía client và Config Server, đồng thời đối chiếu application/profile/label. Với ứng dụng mới trên phiên bản hỗ trợ, ưu tiên Config Data; chỉ giữ legacy bootstrap khi có yêu cầu tương thích cụ thể. **Mục tiêu là có một đường nạp cấu hình từ xa rõ ràng, có thể quan sát và kiểm thử được**, đồng thời bảo đảm profile, thứ tự ưu tiên và hành vi khi Config Server lỗi vẫn đúng với yêu cầu vận hành.
