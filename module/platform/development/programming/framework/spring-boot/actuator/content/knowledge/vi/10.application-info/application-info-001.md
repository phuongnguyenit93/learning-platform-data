# Vai trò của endpoint info và các InfoContributor

## 1. Hiểu đúng câu hỏi mà info trả lời

Khi kiểm tra một ứng dụng đang chạy, người vận hành thường cần biết: đây là dịch vụ nào, bản phát hành nào, được tạo từ mã nguồn nào và có những đặc điểm triển khai gì. Endpoint `info` của Spring Boot Actuator là nơi tập hợp những thông tin mô tả đó.

Ví dụ, hai máy chủ đều phục vụ được yêu cầu nhưng một máy vẫn chạy bản cũ. Dữ liệu phiên bản hoặc mã commit trên `info` giúp đối chiếu hai bản triển khai. Bản thân việc trả về phiên bản không xác nhận cơ sở dữ liệu đang hoạt động hay ứng dụng sẵn sàng nhận lưu lượng.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Nhận diện ứng dụng và bản triển khai | `info` |
| Kiểm tra tình trạng hoạt động, mức sẵn sàng | `health` và các nhóm health phù hợp |
| Theo dõi số yêu cầu, thời gian xử lý, bộ nhớ | `metrics` hoặc hệ thống thu thập số liệu |
| Chẩn đoán nguồn cấu hình | `env`, trong phạm vi được phép truy cập |

Dữ liệu mô tả ứng dụng được gọi là siêu dữ liệu (metadata). Cần chọn lọc những trường hữu ích cho việc nhận diện, thay vì biến `info` thành bản sao của toàn bộ cấu hình.

Trong bài này, ví dụ dùng Java 21 và Spring Boot 3.3.0 để tái lập hành vi thuộc dòng 3.3.x. Đường dẫn HTTP mặc định là `/actuator/info`; khi đổi cổng hoặc đường dẫn quản trị thì URL thực tế cũng thay đổi.

## 2. Endpoint tổng hợp; contributor cung cấp từng phần dữ liệu

Ba thành phần cần phân biệt:

- `InfoContributor`: đối tượng đóng góp dữ liệu, được đăng ký thành bean trong Spring.
- `Info.Builder`: nơi các contributor cùng bổ sung các cặp khóa–giá trị.
- `InfoEndpoint`: gọi các contributor và trả về bản đồ thông tin đã tổng hợp.

Giao diện của contributor chỉ có một phương thức:

~~~java
void contribute(Info.Builder builder);
~~~

Phương thức trả về `void` vì dữ liệu được bổ sung vào builder được truyền vào. Contributor không tự gửi HTTP response và không cần khai báo `@RestController`. Đây cũng là một giao diện hàm nên có thể triển khai bằng lambda khi khai báo `@Bean`. Xem [hợp đồng InfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html).

Luồng xử lý có thể hình dung như sau:

~~~text
GET /actuator/info
        |
        v
Hạ tầng Actuator gọi InfoEndpoint.info()
        |
        v
Tạo Info.Builder
        |
        +--> contributor A bổ sung "app"
        +--> contributor B bổ sung "build"
        +--> contributor C bổ sung "release"
        |
        v
Tạo bản đồ thông tin và chuyển thành JSON
~~~

Các nhãn A/B/C chỉ minh họa quá trình đóng góp; không quy định thứ tự của các bean. Không có contributor nào đóng góp dữ liệu thì kết quả có thể là `{}`. Một đối tượng JSON rỗng vẫn là kết quả hợp lệ, không có nghĩa request bị lỗi.

Ở cấp API, `InfoEndpoint` nhận danh sách contributor và cung cấp phương thức đọc `info()`. Vì thế có thể kiểm tra cơ chế tổng hợp bằng Java mà không cần khởi động máy chủ HTTP. Xem [API InfoEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoEndpoint.html).

## 3. Những nguồn thông tin có sẵn

Spring Boot có các contributor được tự động cấu hình. Danh sách sau dành cho dòng 3.3.x:

| ID | Lớp | Dữ liệu chính | Điều kiện hoặc mặc định |
| --- | --- | --- | --- |
| `build` | `BuildInfoContributor` | Thông tin bản dựng | Có `BuildProperties`, thường từ `META-INF/build-info.properties`; bật mặc định khi đủ điều kiện |
| `git` | `GitInfoContributor` | Thông tin Git | Có `GitProperties`, thường từ `git.properties`; bật mặc định khi đủ điều kiện |
| `env` | `EnvironmentInfoContributor` | Các thuộc tính có tiền tố `info.` | Tắt mặc định |
| `java` | `JavaInfoContributor` | Môi trường Java đang chạy | Tắt mặc định |
| `os` | `OsInfoContributor` | Hệ điều hành | Tắt mặc định |
| `process` | `ProcessInfoContributor` | Tiến trình đang chạy | Tắt mặc định |

Các điều kiện tạo bean và thứ tự mặc định được mô tả trong [InfoContributorAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html).

Hai hệ quả thực tế:

1. Thêm dependency Actuator không đồng nghĩa tự có thông tin bản dựng và Git. Cần tạo các tài nguyên tương ứng trong quá trình build và đưa chúng vào classpath của ứng dụng.
2. Khai báo `spring.application.name` hay `<version>` trong Maven không tự biến chúng thành mọi trường mong muốn trên `info`. Phải có contributor đọc và đóng góp dữ liệu đó.

Bài này tập trung vào vai trò và cách phối hợp contributor. Việc thiết lập plugin sinh metadata bản dựng/Git là một công việc riêng; ví dụ phía dưới không phụ thuộc các tệp sinh đó.

## 4. Phân biệt ba lớp cấu hình

Một contributor có dữ liệu chưa đủ để người dùng đọc được qua HTTP. Cần xét ba lớp độc lập:

| Lớp | Ví dụ cấu hình Spring Boot 3.3.x | Ý nghĩa |
| --- | --- | --- |
| Cho phép endpoint tồn tại theo cơ chế Actuator | `management.endpoint.info.enabled=true` | Bật endpoint `info` |
| Công bố qua HTTP | `management.endpoints.web.exposure.include=health,info` | Đưa endpoint vào tập được công bố qua web |
| Cho phép truy cập | Quy tắc Spring Security, mạng hoặc proxy | Quyết định ai có thể gọi URL |

Trong Spring Boot 3.3.x, `info` được bật mặc định nhưng chỉ `health` được công bố qua HTTP mặc định. `include=info` không vượt qua quy tắc phân quyền và không khôi phục một endpoint đã bị tắt. Nếu cùng ID nằm trong `exclude`, quy tắc loại trừ được ưu tiên. Các quy tắc này được mô tả trong [bật và công bố Actuator endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Cấu hình nguồn dữ liệu lại dùng tiền tố khác:

~~~properties
management.info.env.enabled=true
~~~

Dòng này bật contributor `env`. Nó không công bố URL và cũng không bật endpoint `env`.

Phân biệt chính xác:

- `management.endpoint.info.enabled`: điều khiển endpoint.
- `management.endpoints.web.exposure.include`: điều khiển công bố qua web.
- `management.info.env.enabled`: điều khiển một contributor của `info`.

## 5. Ví dụ hoàn chỉnh: thông tin cấu hình kết hợp contributor tự viết

### 5.1. Cấu trúc dự án độc lập

Tạo một dự án Maven với các tệp sau:

~~~text
info-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/info/
    │   │   ├── InfoApplication.java
    │   │   └── ReleaseInfoContributor.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/example/info/
            └── InfoContributorTest.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>info-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là dự án thực hành độc lập. Maven cần truy cập kho dependency trong lần chạy đầu nếu máy chưa có đủ thư viện.

### 5.2. Khởi động ứng dụng

`src/main/java/example/info/InfoApplication.java`:

~~~java
package example.info;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InfoApplication {
    public static void main(String[] args) {
        SpringApplication.run(InfoApplication.class, args);
    }
}
~~~

### 5.3. Chọn dữ liệu cấu hình được công bố

`src/main/resources/application.properties`:

~~~properties
spring.application.name=info-demo
server.address=127.0.0.1
server.port=8080

management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info

management.info.env.enabled=true
management.info.build.enabled=false
management.info.git.enabled=false
management.info.java.enabled=false
management.info.os.enabled=false
management.info.process.enabled=false

info.app.name=info-demo
info.app.purpose=actuator-learning
~~~

Các contributor khác được tắt rõ ràng để JSON của bài thực hành có thể dự đoán được. Việc tắt `build` và `git` không bắt buộc nếu dự án không có metadata của chúng.

`EnvironmentInfoContributor` lấy nhóm thuộc tính `info.*` và bỏ tiền tố đó khi tạo cấu trúc kết quả. Hai thuộc tính cuối sẽ trở thành đối tượng `app` có `name` và `purpose`. Tên `env` ở đây nói đến nguồn cấu hình Spring `Environment`, không giới hạn ở biến môi trường của hệ điều hành.

### 5.4. Tự đóng góp thông tin phát hành

`src/main/java/example/info/ReleaseInfoContributor.java`:

~~~java
package example.info;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.stereotype.Component;

@Component
public class ReleaseInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        Map<String, Object> release = new LinkedHashMap<>();
        release.put("channel", "training");
        release.put("schemaVersion", 1);
        builder.withDetail("release", release);
    }
}
~~~

`@Component` đăng ký contributor thành bean. Lớp nằm trong gói con được quét từ `InfoApplication`, nên Spring Boot có thể tìm thấy nó.

`withDetail("release", release)` thêm một khóa cấp cao nhất là `release`; map bên trong trở thành đối tượng JSON lồng nhau. Giá trị `schemaVersion` là số nguyên nên được biểu diễn bằng số JSON. Các giá trị cố định trong ví dụ là nhãn phục vụ thực hành, không phải kết quả tự suy ra từ quy trình phát hành.

Không gọi `builder.build()` trong contributor. Việc hoàn tất bản đồ thuộc trách nhiệm của endpoint sau khi tất cả contributor đã có cơ hội đóng góp.

### 5.5. Chạy và quan sát

Từ thư mục chứa `pom.xml`, dùng JDK 21:

~~~shell
mvn spring-boot:run
~~~

Khi ứng dụng đã khởi động, mở terminal thứ hai:

~~~shell
curl -sS -H "Accept: application/json" http://127.0.0.1:8080/actuator/info
~~~

Trên Windows PowerShell, dùng `curl.exe` nếu tên `curl` đang là alias của một lệnh khác.

HTTP status mong đợi là `200`. Body có nội dung sau; khoảng trắng và thứ tự thuộc tính JSON có thể khác:

~~~json
{
  "app": {
    "name": "info-demo",
    "purpose": "actuator-learning"
  },
  "release": {
    "channel": "training",
    "schemaVersion": 1
  }
}
~~~

`app` do contributor `env` đóng góp; `release` do bean tự viết đóng góp. Không có trường `status` được tự thêm như ở `health`.

Ví dụ không thêm Spring Security và chỉ lắng nghe trên loopback để thực hành. Trong ứng dụng có Spring Security, quyền gọi endpoint phụ thuộc cấu hình bảo mật thực tế; không suy ra quyền truy cập chỉ từ `exposure.include`.

## 6. Ba phép thử để hiểu cơ chế thay vì chỉ sao chép cấu hình

Mỗi phép thử dưới đây bắt đầu từ cấu hình gốc ở mục 5. Dừng ứng dụng rồi khởi động lại sau khi thay đổi tệp.

### 6.1. Tắt contributor env

Đổi:

~~~properties
management.info.env.enabled=false
~~~

Kết quả chỉ còn:

~~~json
{
  "release": {
    "channel": "training",
    "schemaVersion": 1
  }
}
~~~

Các thuộc tính `info.app.*` vẫn tồn tại trong cấu hình nhưng không còn contributor `env` đưa chúng vào response. Bean tự viết vẫn hoạt động.

### 6.2. Tắt các contributor được bật mặc định

Thêm:

~~~properties
management.info.defaults.enabled=false
~~~

Vẫn giữ `management.info.env.enabled=true` như cấu hình gốc. Response vẫn có cả `app` và `release`: contributor `env` được bật tường minh, còn bean `ReleaseInfoContributor` không được gắn điều kiện tự động theo thuộc tính `management.info.defaults.enabled`.

Một thuộc tính như `management.info.release.enabled=false` cũng không tự tắt mọi bean có tên liên quan đến `release`. Muốn có công tắc cho contributor tự viết, chính ứng dụng phải gắn một điều kiện thích hợp, chẳng hạn `@ConditionalOnProperty`, hoặc điều khiển việc đăng ký bean.

### 6.3. Bỏ công bố qua HTTP

Đổi:

~~~properties
management.endpoints.web.exposure.include=health
~~~

Với đúng dự án mẫu, URL `/actuator/info` không còn được công bố và trả `404`. Điều này khác với response `200` có body `{}`: `404` cho thấy không có tài nguyên tương ứng ở URL đang gọi, còn `{}` cho thấy thao tác đọc đã chạy nhưng chưa có dữ liệu đóng góp.

Trong hệ thống thực tế, khi gặp `404` còn phải kiểm tra cổng, base path và context path; không kết luận chỉ từ status rằng contributor bị lỗi.

## 7. Kiểm tra tổng hợp và va chạm khóa bằng Java

Một lỗi thiết kế dễ gặp là hai contributor cùng dùng một khóa cấp cao nhất. `Info.Builder` lưu các mục vào map; ghi lại cùng một khóa thay thế giá trị trước đó, không tự hợp nhất sâu hai map con.

Ví dụ: một contributor ghi `release.channel` bằng map dưới khóa `release`, contributor khác ghi map chứa `release.region` cũng dưới khóa `release`. Hai map đó không tự trở thành một đối tượng có cả hai trường.

Tạo `src/test/java/example/info/InfoContributorTest.java`:

~~~java
package example.info;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InfoContributorTest {

    @Test
    void combinesDifferentTopLevelKeys() {
        InfoContributor app = builder ->
                builder.withDetail("app", Map.of("name", "info-demo"));

        InfoEndpoint endpoint = new InfoEndpoint(
                List.of(app, new ReleaseInfoContributor()));

        assertEquals(
                Map.of(
                        "app", Map.of("name", "info-demo"),
                        "release", Map.of(
                                "channel", "training",
                                "schemaVersion", 1)),
                endpoint.info());
    }

    @Test
    void laterContributorReplacesTheSameTopLevelKey() {
        InfoContributor first = builder ->
                builder.withDetail("release", Map.of("channel", "training"));
        InfoContributor second = builder ->
                builder.withDetail("release", Map.of("region", "lab"));

        InfoEndpoint endpoint = new InfoEndpoint(List.of(first, second));

        assertEquals(
                Map.of("release", Map.of("region", "lab")),
                endpoint.info());
    }

    @Test
    void noContributorsProducesAnEmptyMap() {
        InfoEndpoint endpoint = new InfoEndpoint(List.of());

        assertEquals(Map.of(), endpoint.info());
    }
}
~~~

Chạy:

~~~shell
mvn test
~~~

Ba bài kiểm tra phải đạt: ghép các khóa khác nhau, thay thế giá trị khi trùng khóa và trả map rỗng khi không có contributor. Không cần khởi động Spring hay HTTP server vì đây là kiểm tra trực tiếp hợp đồng tổng hợp.

Ở bài kiểm tra thứ hai, thứ tự được cố định bằng `List.of(first, second)`. Trong ứng dụng thật, đừng dựa vào tên lớp hoặc thứ tự quét component để quyết định ai được ghi sau. Nếu thật sự cần thứ tự, Spring hỗ trợ cơ chế sắp thứ tự bean; tuy nhiên thiết kế bền vững hơn là dành một chủ sở hữu cho mỗi khóa cấp cao nhất.

Ví dụ phân vùng khóa rõ ràng:

~~~text
app       -> thông tin định danh lấy từ cấu hình
build     -> metadata của bản dựng
git       -> metadata mã nguồn
release   -> nhãn phát hành do ứng dụng đóng góp
~~~

Nếu nhiều nguồn cần cùng nằm trong `release`, hãy tổng hợp chúng có chủ đích trong một contributor thay vì để các bean ghi đè lẫn nhau.

## 8. Độ tin cậy và dữ liệu nên công bố

Contributor có thể tính dữ liệu khi thao tác đọc được thực thi; không nên mặc định rằng mọi `contribute()` chỉ chạy một lần lúc khởi động. Cơ chế cache của endpoint, nếu được cấu hình, có thể làm giảm số lần thực thi và khiến dữ liệu có độ trễ.

Với metadata nhận diện, ưu tiên dữ liệu nhỏ, rẻ và ổn định: nhãn dịch vụ, phiên bản schema, định danh bản dựng đã chọn lọc. Nếu cần gọi dịch vụ bên ngoài để lấy thông tin, hãy cân nhắc chuẩn bị sẵn ảnh chụp dữ liệu có giới hạn thời gian và cách xử lý lỗi rõ ràng. Không nên để việc đọc một nhãn phát hành phụ thuộc vào một chuỗi request chậm.

Ở cơ chế tổng hợp của Spring Boot 3.3.0, một contributor ném ngoại lệ không được `InfoEndpoint` tự chuyển thành mục `UNKNOWN` rồi tiếp tục an toàn với mọi contributor khác. Nó có thể làm hỏng lần đọc thông tin; lỗi HTTP cuối cùng còn phụ thuộc tầng xử lý lỗi. Không dùng contributor để kiểm tra kết nối cơ sở dữ liệu thay cho `HealthIndicator`.

Chỉ đóng góp trường đã chủ động cho phép công bố. Đừng đưa mật khẩu, token, chuỗi kết nối chứa thông tin đăng nhập hay dữ liệu người dùng vào `info.*` hoặc `withDetail`. Không dựa vào cơ chế che giá trị của endpoint `env` để bảo vệ dữ liệu do `info` trả về: đây là hai endpoint khác nhau.

Ví dụ, tên cấu hình `info.app.password` vẫn nằm trong nhóm `info.*` mà contributor `env` đọc. Tên có chữ “password” không phải là lý do để coi dữ liệu đó an toàn trên endpoint `info`.

## 9. Chẩn đoán theo triệu chứng

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| `404` khi gọi URL mẫu | Kiểm tra endpoint có được bật/công bố, đúng cổng và đúng đường dẫn không |
| `401` hoặc `403` | Kiểm tra xác thực và quy tắc phân quyền của ứng dụng hoặc proxy |
| `200` với `{}` | Kiểm tra contributor được tạo và có dữ liệu để đóng góp không |
| Có `release` nhưng thiếu `app` | Kiểm tra `management.info.env.enabled` và các thuộc tính `info.app.*` |
| Có `app` nhưng thiếu `release` | Kiểm tra contributor có phải bean và nằm trong phạm vi component scan không |
| Thiếu `build` hoặc `git` | Kiểm tra tài nguyên metadata, bean tương ứng và công tắc contributor |
| Một nhóm dữ liệu làm mất nhóm trước cùng tên | Kiểm tra va chạm khóa cấp cao nhất, không giả định map được ghép sâu |
| Request chậm hoặc lỗi sau khi thêm contributor | Kiểm tra tính toán, I/O và ngoại lệ trong `contribute()` |

## 10. Tự thực hành

1. Thêm `info.app.owner=learning-team`. Dự đoán trường mới nằm ở đâu rồi kiểm tra bằng HTTP.
2. Đổi tên khóa `release` trong `withDetail` thành `deployment`. Quan sát cấu trúc JSON thay đổi theo khóa dữ liệu, không theo tên lớp.
3. Thử ghi hai map khác nhau vào cùng khóa bằng bài kiểm tra thứ hai; giải thích vì sao dữ liệu đầu tiên biến mất.
4. Tắt `env` rồi bỏ công bố `info` qua HTTP ở hai lần chạy riêng. Giải thích sự khác nhau giữa thiếu một nhóm dữ liệu và mất URL.
5. Chọn ba trường nhận diện phù hợp với một ứng dụng của bạn. Với mỗi trường, xác định nguồn dữ liệu, contributor sở hữu và người được phép đọc.

Sau các phép thử, cần giải thích được mối liên hệ: contributor quyết định dữ liệu đóng góp; endpoint tổng hợp; cấu hình công bố và phân quyền quyết định khả năng truy cập.
