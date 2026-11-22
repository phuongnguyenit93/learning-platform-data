# Tạo health group và chọn thành viên bằng `include` hoặc `exclude`

> Phạm vi: Spring Boot Actuator 3.3.x. Ví dụ độc lập bên dưới dùng Java 21, Spring Boot 3.3.0 và Gradle 8.5. Các phép kiểm tra phụ thuộc được mô phỏng để tập trung vào cách chọn thành viên, không cần cài cơ sở dữ liệu hay cache.

## 1. Health group giải quyết câu hỏi nào?

Một ứng dụng có thể kiểm tra nơi lưu dữ liệu, cổng thanh toán và bộ nhớ đệm. Tuy nhiên, người vận hành không phải lúc nào cũng cần một câu trả lời chung cho cả ba. Nếu cache chỉ giúp tăng tốc và ứng dụng vẫn xử lý được yêu cầu bằng cách đọc nguồn dữ liệu chính, việc cache lỗi có thể cần cảnh báo riêng thay vì bị hiểu thành toàn bộ chức năng nghiệp vụ đã ngừng hoạt động.

**Nhóm kiểm tra sức khỏe (health group)** tạo một góc nhìn có tên trên các thành phần kiểm tra đã đăng ký. Bạn chọn thành viên của nhóm rồi truy vấn trạng thái tổng hợp dành cho đúng mục đích đó.

Trong tình huống của bài:

| Thành phần | Vai trò trong tình huống | Trạng thái mô phỏng ban đầu |
| --- | --- | --- |
| `primaryStore` | Nơi lưu dữ liệu chính | `UP` |
| `billingGateway` | Cổng thanh toán | `UP` |
| `optionalCache` | Cache có thể bỏ qua khi lỗi | `DOWN` |

Ta muốn quan sát ba câu hỏi:

- `business`: hai phụ thuộc nghiệp vụ đã chọn có khỏe không?
- `noncache`: các kiểm tra ngoài cache có khỏe không?
- `cacheOnly`: riêng cache có khỏe không?

`business` và `noncache` có thể trả `UP` trong khi `cacheOnly` và health tổng thể trả `DOWN`. Đây là các câu trả lời có phạm vi khác nhau; muốn diễn giải đúng phải biết mỗi nhóm chứa những thành viên nào.

### Những thuật ngữ cần phân biệt

- `HealthIndicator`: một kiểm tra cung cấp kết quả `Health`, chẳng hạn `UP` hoặc `DOWN`.
- `HealthContributor`: khái niệm bao quát thành phần cung cấp thông tin health; có thể là một indicator hoặc một cấu trúc gồm nhiều thành phần con.
- ID thành viên: tên mà Actuator dùng để nhận diện contributor, ví dụ `optionalCache`.
- Tên nhóm: tên bạn đặt để tập hợp contributor, ví dụ `business`.
- Trạng thái nhóm: kết quả tổng hợp từ những thành viên thuộc nhóm.

Với base path mặc định và không có context path hay cổng management riêng, nhóm `business` được truy vấn tại `/actuator/health/business`. Nó là một nhóm bên trong endpoint `health`; không cần viết Controller mới. [Tài liệu Health Groups của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.groups).

## 2. Cấu hình nằm ở đâu và chọn những gì?

Cấu hình một nhóm nằm dưới:

```text
management.endpoint.health.group.<tên-nhóm>
```

Ví dụ chọn cụ thể hai thành viên:

```yaml
management:
  endpoint:
    health:
      group:
        business:
          include:
            - primaryStore
            - billingGateway
```

`include` nhận ID của contributor đã đăng ký. Cấu hình trên không tự tạo `primaryStore` hay `billingGateway`; ứng dụng phải cung cấp hai contributor đó.

### `include`: chỉ đưa các thành viên được chọn vào nhóm

Dùng `include` khi bạn muốn diễn đạt một phạm vi rõ ràng: nhóm nghiệp vụ này gồm đúng những kiểm tra nào. Khi thêm một indicator mới vào ứng dụng, nhóm có danh sách `include` tường minh không tự nhận indicator đó.

### `exclude`: bỏ các thành viên khỏi tập được chọn

Nếu không khai báo `include`, nhóm xét tất cả contributor rồi loại những ID nằm trong `exclude`:

```yaml
management:
  endpoint:
    health:
      group:
        noncache:
          exclude:
            - optionalCache
```

Trong tình huống ban đầu, nhóm còn `primaryStore` và `billingGateway`. Nếu sau này ứng dụng đăng ký thêm một contributor khác mà không bị loại, phạm vi của `noncache` có thể mở rộng.

### Kết hợp hai thuộc tính

```yaml
management:
  endpoint:
    health:
      group:
        narrowed:
          include:
            - primaryStore
            - billingGateway
          exclude:
            - billingGateway
```

`narrowed` chỉ còn `primaryStore`: ID xuất hiện trong cả hai danh sách sẽ bị loại. Có thể hiểu đây là hai bước: chọn tập ban đầu bằng `include`, sau đó trừ bằng `exclude`; thứ tự hai khóa trong YAML không quyết định độ ưu tiên.

Với các contributor phẳng trong bài, gọi `U` là tập ID thực sự đã đăng ký:

```text
Tập ban đầu = U                         nếu không khai báo include
            = U                         nếu include chọn "*"
            = các ID được include chọn   nếu có danh sách cụ thể

Thành viên nhóm = tập ban đầu trừ các ID bị exclude
```

Các ID cấu hình còn phải vượt qua bước kiểm tra tồn tại khi khởi động. Công thức này giúp suy luận việc chọn thành viên; nó không thay cho quy tắc tổng hợp trạng thái.

| Cấu hình trong tình huống có ba ID ban đầu | Thành viên được chọn |
| --- | --- |
| `include: [primaryStore, billingGateway]` | `primaryStore`, `billingGateway` |
| Chỉ `exclude: [optionalCache]` | `primaryStore`, `billingGateway` |
| `include: "*"` và `exclude: [optionalCache]` | `primaryStore`, `billingGateway` |
| `include: [primaryStore, billingGateway]` và `exclude: [billingGateway]` | `primaryStore` |

`"*"` có nghĩa chọn tất cả; trong YAML phải đặt nó trong dấu nháy để tránh bị hiểu theo cú pháp alias. Không suy diễn rằng các mẫu như `*Cache` hoặc `db*` là bộ lọc tên được hỗ trợ. Khi chọn một ID cụ thể, hãy dùng đúng tên và đúng chữ hoa/chữ thường.

## 3. ID của indicator khác tên nhóm như thế nào?

Với bean indicator có hậu tố `HealthIndicator`, Actuator bỏ hậu tố đó khi hình thành ID thông thường:

| Bean trong ví dụ | ID dùng trong `include`/`exclude` |
| --- | --- |
| `primaryStoreHealthIndicator` | `primaryStore` |
| `billingGatewayHealthIndicator` | `billingGateway` |
| `optionalCacheHealthIndicator` | `optionalCache` |

Vì vậy cấu hình `include: primaryStoreHealthIndicator` sẽ không chọn đúng ID `primaryStore` trong ví dụ này. Nếu có đặt tên bean tường minh, hãy xác minh ID thực tế thay vì suy ra chỉ từ tên lớp.

Các tên như `db` hay `redis` thường gặp trong ứng dụng có cấu hình tương ứng, nhưng việc cài Actuator không đảm bảo mọi ID đó đều tồn tại. Một profile không tạo `DataSource` thì không thể mặc định rằng `db` đã có sẵn.

`business` là tên nhóm còn `primaryStore` là ID contributor. Không dùng tên nhóm khác như một cách tái sử dụng danh sách thành viên; các nhóm có thể cùng chọn một contributor, nhưng `include`/`exclude` dùng contributor ID hoặc đường dẫn thành phần con.

## 4. Ví dụ độc lập: cùng một ứng dụng, ba phạm vi health

Ví dụ dùng ba indicator tự định nghĩa. Không có kết nối mạng đến phụ thuộc bên ngoài; `optionalCache` nhận trạng thái từ thuộc tính `demo.cache-up`.

### 4.1. Khai báo dự án

Tạo thư mục dự án riêng với bốn tệp sau:

```text
health-group-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/HealthGroupDemo.java
    └── resources/application.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'health-group-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là phiên bản cố định cho thí nghiệm. Nếu áp dụng vào ứng dụng Spring Boot 3.3.x đang có, giữ cấu hình build của ứng dụng và bảo đảm đã có hai starter cần thiết.

### 4.2. Cung cấp các kiểm tra

`src/main/java/demo/HealthGroupDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class HealthGroupDemo {
    public static void main(String[] args) {
        SpringApplication.run(HealthGroupDemo.class, args);
    }

    @Bean
    HealthIndicator primaryStoreHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    HealthIndicator billingGatewayHealthIndicator() {
        return () -> Health.up().build();
    }

    @Bean
    HealthIndicator optionalCacheHealthIndicator(
            @Value("${demo.cache-up:false}") boolean cacheUp) {
        return () -> cacheUp ? Health.up().build() : Health.down().build();
    }
}
```

Hai lambda đầu luôn báo `UP`; lambda cuối báo theo giá trị cấu hình tại lúc tạo bean. Đổi thuộc tính rồi khởi động lại ứng dụng để đổi tình huống. Đây không phải kiểm tra database, cổng thanh toán hay cache thật; trong ứng dụng thực, phần thân indicator phải thực hiện phép kiểm tra phù hợp.

### 4.3. Tạo các nhóm

`src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  health:
    defaults:
      enabled: false
  endpoint:
    health:
      show-components: always
      group:
        business:
          include:
            - primaryStore
            - billingGateway
        noncache:
          exclude:
            - optionalCache
        cacheOnly:
          include:
            - optionalCache

demo:
  cache-up: false
```

Giải thích các lựa chọn của thí nghiệm:

- `management.health.defaults.enabled: false` tắt những indicator mặc định do Boot tự cấu hình để kết quả chỉ phụ thuộc ba bean mẫu. Nó không tắt các bean `HealthIndicator` tự định nghĩa ở trên. Không cần sao chép lựa chọn này vào hệ thống thật chỉ để tạo nhóm.
- `show-components: always` giúp nhìn được tên và trạng thái thành viên khi học. Việc hiện thành phần và việc hiện chi tiết là hai lựa chọn khác nhau; khi triển khai cần chọn chính sách hiển thị và quyền truy cập phù hợp.
- `business` dùng danh sách cho phép tường minh; `noncache` dùng danh sách loại; `cacheOnly` cho thấy một contributor có thể thuộc nhiều góc nhìn health.
- `management.endpoints.web.exposure.include: health` công bố endpoint `health`, không định nghĩa thành viên của nhóm.

### 4.4. Chạy và quan sát

Tại thư mục dự án, với JDK 21 và Gradle 8.5:

```shell
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper tương ứng, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. Những tệp Java ở trên cần dependency của Spring Boot; không thể chạy bằng `javac HealthGroupDemo.java` với classpath trống.

Chờ ứng dụng khởi động xong rồi mở terminal khác. Các lệnh dưới dùng `curl.exe` trên Windows; trên Linux/macOS dùng `curl`:

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/business
```

Kết quả JSON và mã HTTP:

```text
{"status":"UP","components":{"billingGateway":{"status":"UP"},"primaryStore":{"status":"UP"}}}
HTTP 200
```

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/noncache
```

```text
{"status":"UP","components":{"billingGateway":{"status":"UP"},"primaryStore":{"status":"UP"}}}
HTTP 200
```

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health/cacheOnly
```

```text
{"status":"DOWN","components":{"optionalCache":{"status":"DOWN"}}}
HTTP 503
```

Thứ tự các khóa JSON không phải hợp đồng cần dựa vào; hãy đối chiếu tên thành viên, trạng thái và mã HTTP. Mẫu này không thêm Spring Security. Nếu áp dụng vào ứng dụng đã có bảo mật, quyền truy cập thực tế còn phụ thuộc cấu hình của ứng dụng.

Kiểm tra health tổng thể:

```shell
curl.exe -s -w "\nHTTP %{http_code}\n" http://localhost:8080/actuator/health
```

Trong điều kiện của ví dụ, kết quả tổng thể có `status: DOWN`, ba thành phần ban đầu và mã `503`. Nó vẫn thấy `optionalCache`; việc loại cache khỏi `noncache` không loại cache khỏi health tổng thể.

### 4.5. Đổi cache sang trạng thái khỏe

Dừng tiến trình đang chạy rồi khởi động lại:

```shell
gradle bootRun --args="--demo.cache-up=true"
```

Gọi lại bốn URL và đối chiếu:

| URL | `cache-up=false` | `cache-up=true` |
| --- | --- | --- |
| `/actuator/health` | `DOWN`, HTTP `503` | `UP`, HTTP `200` |
| `/actuator/health/business` | `UP`, HTTP `200` | `UP`, HTTP `200` |
| `/actuator/health/noncache` | `UP`, HTTP `200` | `UP`, HTTP `200` |
| `/actuator/health/cacheOnly` | `DOWN`, HTTP `503` | `UP`, HTTP `200` |

Tập thành viên không đổi khi cache chuyển trạng thái. Chỉ kết quả của những góc nhìn chứa cache thay đổi. Bảng này giả định chính sách tổng hợp và ánh xạ HTTP mặc định, không có indicator hay tùy biến bổ sung.

## 5. Chọn thành viên khác với tổng hợp và hiển thị

Đọc một phản hồi health theo các bước:

1. Nhóm chọn contributor nào bằng `include`/`exclude`?
2. Các contributor đó trả trạng thái gì ở lần kiểm tra?
3. Bộ tổng hợp trạng thái (`StatusAggregator`) của nhóm quyết định kết quả chung thế nào?
4. Kết quả được ánh xạ thành mã HTTP nào, và người gọi được xem đến mức nào?

Nhóm mặc định kế thừa các thiết lập tổng hợp và ánh xạ HTTP từ health tổng thể nếu không có tùy chỉnh riêng. `include`/`exclude` quyết định đầu vào, không tự định nghĩa lại ý nghĩa của `DOWN` hay thay đổi quyền xem dữ liệu. [Cách dựng cấu hình nhóm trong Spring Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

Ví dụ: ẩn `components` không làm một thành viên `DOWN` ngừng ảnh hưởng đến nhóm. Ngược lại, loại cache khỏi `noncache` khiến kết quả của cache không tham gia tổng hợp cho nhóm đó, nhưng không sửa bean cache hay trạng thái của nhóm `cacheOnly`.

## 6. Khi nào dùng `include`, khi nào dùng `exclude`?

| Điều cần diễn đạt | Lựa chọn dễ hiểu | Hệ quả cần dự tính |
| --- | --- | --- |
| Nhóm phục vụ một quyết định cụ thể, chỉ dựa vào vài phụ thuộc đã xác định | Danh sách `include` tường minh | Thêm indicator mới không tự mở rộng nhóm |
| Nhóm chẩn đoán muốn theo dõi tất cả, trừ một số thành phần đã biết | `exclude`, hoặc `include: "*"` kèm `exclude` | Indicator mới có thể tự trở thành thành viên |
| Một cấu hình chung cần chọn tập rộng rồi loại một phần | Dùng cả hai và kiểm tra kết quả cuối | ID bị `exclude` loại ngay cả khi đã được `include` chọn |

Trong ví dụ, `business` và `noncache` đang có cùng hai thành viên. Nếu thêm `searchIndex` vào registry thì:

- `business` vẫn chỉ chứa hai ID đã liệt kê.
- `noncache` nhận thêm `searchIndex`, vì chỉ `optionalCache` bị loại.

Nếu `searchIndex` báo lỗi, hai nhóm có thể bắt đầu trả trạng thái khác nhau. Vì vậy hai cấu hình cho cùng kết quả hôm nay chưa chắc có cùng ý nghĩa khi ứng dụng thay đổi. Khi chọn cách cấu hình, hãy nói rõ nhóm trả lời câu hỏi vận hành nào.

Health group cũng không tự biến thành probe của hạ tầng. Người triển khai phải chọn đúng URL và chính sách phản ứng. Đặc biệt, trước khi dùng một nhóm làm tín hiệu liveness hay readiness, cần cân nhắc tác động của việc thêm phụ thuộc bên ngoài; bài này chỉ xây dựng tập thành viên.

## 7. ID sai, thành viên có điều kiện và nhóm rỗng

### 7.1. Kiểm tra tồn tại lúc khởi động

Mặc định Spring Boot kiểm tra cả các ID được `include` lẫn `exclude` khai báo. Nếu ID không tồn tại, quá trình khởi động thất bại. Ví dụ thêm hoặc đổi:

```yaml
management:
  endpoint:
    health:
      group:
        business:
          include:
            - primaryStoreTypo
```

Trong ứng dụng mẫu, thông báo lỗi có phần:

```text
Included health contributor 'primaryStoreTypo' in group 'business' does not exist
```

Điều này khác với một contributor đã tồn tại nhưng trả `DOWN`: cấu hình sai có thể khiến ứng dụng không khởi động; phụ thuộc lỗi là kết quả kiểm tra của ứng dụng đã chạy.

Với contributor chỉ được tạo trong một profile, hãy đặt cấu hình nhóm tương ứng trong đúng profile hoặc bảo đảm contributor tồn tại ở môi trường cần dùng. Đừng thêm tên một dịch vụ dự kiến triển khai rồi mặc định rằng Actuator sẽ tự tạo kiểm tra cho nó.

### 7.2. Tắt validation không tạo thành viên

Boot cho phép tắt kiểm tra tồn tại bằng:

```properties
management.endpoint.health.validate-group-membership=false
```

Thuộc tính này không tạo contributor bị thiếu và không chứng minh phạm vi nhóm đã đúng. Nó chỉ bỏ cổng kiểm tra cấu hình. Dùng nó để che lỗi chính tả có thể khiến người vận hành tin rằng một phụ thuộc đang được theo dõi trong khi thực tế không có kiểm tra nào.

Quy tắc validation được thực hiện tại lúc khởi tạo singleton; cần chú ý thời điểm đăng ký nếu ứng dụng quản lý contributor động. [Mã nguồn kiểm tra thành viên của Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/HealthEndpointConfiguration.java).

### 7.3. Không để nhóm rỗng rồi mặc định là khỏe

Ví dụ `include: [primaryStore]` đi kèm `exclude: [primaryStore]` làm mất toàn bộ thành viên. Một cấu hình như vậy không trả lời được câu hỏi sức khỏe mà bạn định hỏi.

Với triển khai HTTP của Boot 3.3, khi không còn đóng góp health nào trong nhóm, truy vấn có thể không có kết quả health và trả `404`; không được suy luận rằng nhóm rỗng sẽ luôn trả `UP`. Cần kiểm tra cả tập thành viên lẫn phản hồi thực tế. [Luồng tập hợp các đóng góp health](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

## 8. Trường hợp contributor có thành phần con

Contributor có thể là một cây thay vì một kiểm tra đơn lẻ. Ví dụ ứng dụng đã đăng ký cấu trúc sau:

```text
stores
├── primary
└── reporting
```

Để chọn riêng thành phần con `primary`, dùng đường dẫn đầy đủ:

```yaml
management:
  endpoint:
    health:
      group:
        writepath:
          include:
            - stores/primary
```

Hoặc chọn cây `stores` rồi loại một nhánh:

```yaml
management:
  endpoint:
    health:
      group:
        writepath:
          include:
            - stores
          exclude:
            - stores/reporting
```

Đây là cấu hình minh họa bổ sung, không ghép thẳng vào ứng dụng ba indicator ở trên vì ứng dụng đó không đăng ký composite `stores`. Dấu `/` mô tả đường dẫn contributor con, không phải tên một health group khác. Khi kiểm tra, quan sát cấu trúc `components` tương ứng; đừng mặc định cây sẽ được biến thành một danh sách phẳng.

## 9. Những nhầm lẫn thường gặp

| Hiện tượng hoặc suy nghĩ | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Khởi động lỗi vì thành viên không tồn tại | Sai ID, sai chữ hoa/thường, bean không được tạo trong profile đang chạy | Đối chiếu contributor thực tế và cấu hình đúng profile |
| `business` không xuất hiện khi thêm vào web exposure | Nhầm tên nhóm với endpoint ID | Công bố `health`; đặt nhóm dưới `management.endpoint.health.group` |
| Loại cache khỏi một nhóm rồi tưởng cache bị tắt toàn cục | Nhầm chọn thành viên với vô hiệu hóa indicator | Kiểm tra health tổng thể và nhóm còn chứa cache |
| `noncache` thay đổi sau khi thêm một starter hoặc indicator mới | Phạm vi chọn theo kiểu tất cả trừ danh sách loại | Kiểm tra lại thành viên; dùng `include` tường minh nếu cần phạm vi cố định |
| JSON chỉ có trạng thái nên tưởng nhóm không có thành viên | Chính sách hiển thị che thành phần | Kiểm tra `show-components` và quyền truy cập bằng chính sách phù hợp |
| Chỉ nhìn HTTP `200` rồi kết luận đúng mọi thứ | Chưa kiểm tra đúng URL, đúng nhóm và nội dung health | Đối chiếu thành viên và trạng thái nghiệp vụ cần quan sát |
| Cấu hình YAML báo lỗi với dấu `*` | `*` không được đặt trong dấu nháy | Viết `include: "*"` |
| Nhóm không cho kết quả health mong đợi sau khi loại hết ID | Tập thành viên cuối rỗng | Giữ ít nhất một kiểm tra có ý nghĩa và kiểm tra lại phản hồi |

Cũng cần phân biệt các cấu hình gần tên nhau:

```text
management.endpoint.health.group.<name>.include/exclude
  → chọn contributor của một nhóm

management.endpoints.web.exposure.include/exclude
  → chọn endpoint được công bố qua HTTP

management.health.<key>.enabled
  → điều khiển indicator tự cấu hình tương ứng, khi có hỗ trợ
```

Chuyển một ID từ danh sách nhóm sang danh sách exposure không phải cách sửa lỗi membership.

## 10. Thực hành tự kiểm tra

Thực hiện lần lượt trên ví dụ độc lập:

1. Giữ `cache-up=false`, dự đoán trạng thái của bốn URL trước khi gọi.
2. Thay `noncache.exclude` bằng `noncache.include: [primaryStore, billingGateway]`. Kết quả ban đầu có thay đổi không?
3. Thêm một bean `searchIndexHealthIndicator` trả `Health.down().build()`. So sánh nhóm `noncache` dùng `exclude` với nhóm dùng `include` tường minh.
4. Thêm nhóm `narrowed` chứa hai ID nghiệp vụ rồi loại `billingGateway`. Kiểm tra nhóm còn đúng một thành viên.
5. Cố ý viết sai một ID trong `exclude` rồi khởi động lại. Xác định đây là lỗi cấu hình hay một phản hồi health `DOWN`.

Kết quả cần giải thích được:

- Ở bước 2, tập thành viên hiện tại bằng nhau nên trạng thái giống nhau.
- Ở bước 3, nhóm dùng danh sách loại nhận thêm `searchIndex`; nhóm chỉ bao gồm hai ID nghiệp vụ thì không.
- Ở bước 4, `exclude` thắng khi một ID đồng thời được chọn và bị loại.
- Ở bước 5, validation mặc định chặn khởi động vì ID không tồn tại; đó không phải một phép kiểm tra phụ thuộc đã chạy rồi thất bại.

Một cấu hình nhóm đạt mục đích khi bạn có thể nêu rõ câu hỏi nó trả lời, liệt kê tập thành viên cuối cùng và dự đoán được kết quả khi từng thành viên đổi trạng thái.
