# Truy vết phiên bản đang chạy mà không công bố bí mật hoặc dữ liệu cá nhân

## 1. Cần biết điều gì khi hỏi “máy này đang chạy bản nào?”

Khi vừa triển khai bản vá, người vận hành cần xác nhận tiến trình đang phục vụ yêu cầu đã nhận đúng bản phát hành. Tên nhánh `main` hoặc thông báo “triển khai thành công” chưa trả lời đầy đủ: nhánh có thể đã tiến thêm, một máy có thể chưa được thay thế, hoặc cùng một commit đã được build nhiều lần với đầu vào khác nhau.

Trong chương thông tin ứng dụng của Spring Boot Actuator, `/actuator/info` có thể cung cấp một tập metadata nhỏ để nối tiến trình đang chạy với hồ sơ phát hành. Mục tiêu là trả lời được:

1. Đây là dịch vụ nào?
2. Dịch vụ tự nhận đang chạy phiên bản phát hành nào?
3. Mã nguồn tương ứng là commit nào?
4. Gói chạy đến từ lần build nào?

Dữ liệu phục vụ đối chiếu phải được chọn trước. Không cần đính kèm tên người tạo commit, email, nội dung commit, URL kho mã, biến môi trường hoặc thông tin người dùng để trả lời bốn câu hỏi trên.

### Các định danh liên quan nhưng không thay thế nhau

| Trường | Ý nghĩa | Giới hạn khi dùng để đối chiếu |
| --- | --- | --- |
| Phiên bản phát hành, ví dụ `2.4.1` | Tên phiên bản do quy trình phát hành quản lý | Có thể bị dùng lại nếu quy trình cho phép build đè |
| Commit đầy đủ | Xác định một ảnh chụp mã nguồn trong kho mã | Chưa mô tả mọi dependency, cấu hình build hay thay đổi chưa commit |
| Định danh lần build, ví dụ `7318` | Khóa tra cứu một lần tạo gói trong hệ thống CI | Chỉ có ý nghĩa trong phạm vi hệ thống đã quy ước |
| SHA-256 của gói hoặc digest ảnh container | Đối chiếu nội dung gói/ảnh đã lưu trong kho phát hành | Phải lấy từ hồ sơ đáng tin và xác định đúng đối tượng được băm |
| Thời điểm build | Hỗ trợ sắp xếp, điều tra | Không phải thời điểm khởi động hay triển khai; không bảo đảm duy nhất |

Commit rút gọn tiện đọc nhưng có thể trùng tiền tố. Khi cần tra cứu chính xác, dùng commit đầy đủ trong kênh vận hành đã kiểm soát hoặc tra bằng định danh build. Ví dụ trong bài dùng Git SHA-1 dài 40 ký tự; kho dùng định dạng khác cần hợp đồng xác thực tương ứng.

Một chuỗi suy luận hữu ích là:

```text
Tiến trình đang chạy
  -> metadata đóng gói cùng ứng dụng
  -> service + version + revision + buildId
  -> hồ sơ phát hành trong CI/kho artifact
  -> commit, dependency đã chốt, checksum/digest và lịch sử triển khai
```

Đây là thiết kế truy vết đề xuất. Phản hồi HTTP tự nó không chứng minh tính xác thực của gói: một ứng dụng có thể khai sai metadata. Muốn xác minh nguồn gốc mạnh hơn, đối chiếu checksum, chữ ký/chứng thực phát hành và trạng thái triển khai từ hệ thống đáng tin.

## 2. Actuator lấy thông tin từ đâu?

`InfoEndpoint` tổng hợp thông tin do các bean `InfoContributor` đóng góp. Một contributor có thể thêm một mục vào đối tượng JSON, chẳng hạn `release`. Vì vậy, cần kiểm soát cả tập contributor tham gia và dữ liệu mỗi contributor đưa ra. Cơ chế tổng hợp thể hiện trực tiếp trong [mã nguồn InfoEndpoint của Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoEndpoint.java).

Các nguồn thường gặp:

- `META-INF/build-info.properties`: metadata của gói được tạo ở giai đoạn build; Spring Boot có thể nạp thành `BuildProperties`.
- `git.properties` tại gốc classpath: metadata Git được đóng gói sẵn; không có nghĩa ứng dụng truy vấn kho Git đang sống mỗi lần nhận HTTP.
- `info.*` trong cấu hình: có thể được đưa ra bởi `EnvironmentInfoContributor` khi contributor đó được bật.
- Bean `InfoContributor` do ứng dụng viết: tự quyết định nội dung xuất.

Trong Spring Boot 3.3, endpoint được bật và endpoint được đưa ra HTTP là hai điều kiện riêng. Mặc định chỉ `health` được đưa ra HTTP; muốn đọc `info` phải cấu hình exposure phù hợp. Contributor `build` và `git` có thể được tự cấu hình khi có metadata tương ứng; `env` không được bật mặc định. Xem [tài liệu endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

### Ba lối rò rỉ dễ bị bỏ qua

**Metadata build có trường mở rộng.** `BuildInfoContributor` của dòng 3.3 dùng chế độ `FULL`. Nếu bổ sung một trường vào build-info rồi để contributor này xuất tự động, trường đó có thể trở thành một phần của JSON. Không nên coi file build-info là nơi lưu bí mật. Xem [BuildInfoContributor 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/BuildInfoContributor.java).

**Git ở chế độ đầy đủ.** Chế độ `simple` chọn nhánh, commit rút gọn và thời điểm commit nếu có; `full` dùng toàn bộ các thuộc tính Git đã cung cấp. File do công cụ build tạo có thể chứa thêm danh tính, thông tin máy build hoặc URL remote. Ngay cả tên nhánh cũng có thể chứa tên người, mã khách hàng hoặc nội dung sự cố. Xem [GitInfoContributor](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/GitInfoContributor.java) và [cách chọn FULL/SIMPLE](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoPropertiesInfoContributor.java).

**Cấu hình `info.*`.** Khi bật contributor môi trường, những thuộc tính nằm dưới `info` có thể đi vào phản hồi. Đổi tên `DB_PASSWORD` thành `info.database.password` không làm giá trị an toàn hơn; nội suy bí mật vào `info.*` vẫn tạo ra dữ liệu nhạy cảm. Xem [EnvironmentInfoContributor](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.java).

Không suy rộng cơ chế che giá trị của `/env` và `/configprops` sang `/info`. Tài liệu mô tả việc che giá trị cho các endpoint có cơ chế đó; đối với dữ liệu tự đóng góp vào `info`, hãy thiết kế ngay từ đầu rằng giá trị sẽ được trả về. Không có một thuộc tính `show-values` dùng chung để tự lọc mọi JSON của contributor.

## 3. Thiết kế hợp đồng dữ liệu trước khi viết mã

Ví dụ này chọn một đối tượng duy nhất:

```json
{
  "release": {
    "service": "order-service",
    "version": "2.4.1",
    "revision": "8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b",
    "buildId": "7318"
  }
}
```

Tất cả giá trị trên là dữ liệu minh họa. Bốn trường là danh sách được phép xuất của ví dụ, không phải một danh sách an toàn áp dụng cho mọi tổ chức. Nếu mã nguồn là riêng tư hoặc chính sách không cho lộ commit, có thể chỉ công bố một mã phát hành không mang thông tin và tra ánh xạ trong hệ thống nội bộ.

| Chọn xuất trong ví dụ | Giữ trong hồ sơ CI/kho phát hành |
| --- | --- |
| Mã dịch vụ theo quy ước | Tên người build, người commit, email |
| Phiên bản phát hành | Nội dung commit, tên nhánh có thông tin cá nhân |
| Commit đầy đủ đã được duyệt cho kênh này | URL remote có tài khoản/token, đường dẫn máy build |
| Định danh build dạng số | Biến môi trường, thuộc tính hệ thống, cấu hình kết nối |
| Không có dữ liệu người dùng | Hồ sơ khách hàng, định danh phiên, request/response nghiệp vụ |

Không dùng cách “xuất mọi trường rồi xóa các khóa có tên `password`”. Danh sách từ cấm dễ bỏ sót tên mới như `credential` hoặc một cấu trúc lồng nhau. Chọn từng trường cần thiết giúp hợp đồng ổn định khi nguồn metadata xuất hiện trường mới.

Một mã build ngẫu nhiên hoặc dạng số vẫn có thể được nối với danh tính trong hệ thống khác. Giới hạn người xem và phạm vi tra cứu vẫn cần phù hợp với ngữ cảnh sử dụng.

## 4. Ví dụ tích hợp Spring Boot 3.3.x, Java 21

Các đoạn sau dành cho một ứng dụng Spring Boot 3.3.x đã có Java 21, Gradle wrapper, Spring Boot Gradle plugin, `spring-boot-starter-web` và `spring-boot-starter-actuator`. Ứng dụng đã có lớp `@SpringBootApplication`. Đây là mã tích hợp với Spring và các thư viện của nó; file contributor không phải chương trình chạy riêng bằng `java ReleaseInfoContributor`.

Trong bài thực hành độc lập, đặt tên Gradle project là `order-service`. Nếu tích hợp vào dự án khác, giữ quy ước artifact của dự án và cập nhật giá trị kỳ vọng tương ứng.

### 4.1. Đóng gói metadata từ lần build

Phần cấu hình bổ sung trong `build.gradle`, dùng Groovy DSL:

```groovy
version = '2.4.1'

springBoot {
    buildInfo {
        excludes = ['group', 'name', 'time']
        properties {
            additional = [
                'revision': providers.gradleProperty('sourceRevision').get(),
                'buildId': providers.gradleProperty('buildId').get()
            ]
        }
    }
}
```

`buildInfo` tạo task `bootBuildInfo` để sinh `META-INF/build-info.properties`. Ví dụ bỏ các trường không sử dụng và lấy hai định danh từ tham số build bắt buộc; nếu thiếu tham số, Gradle không tự thay bằng dữ liệu cũ. Cách tạo, bổ sung và loại trường được mô tả trong [tài liệu Gradle plugin 3.3](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html).

Chạy ở gốc ứng dụng thực hành trên PowerShell:

```powershell
.\gradlew.bat clean bootJar -PsourceRevision=8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b -PbuildId=7318
java -jar build/libs/order-service-2.4.1.jar
```

Ở đây `order-service` là tên artifact mặc định của project thực hành. Nếu đã tùy chỉnh tên JAR, dùng đúng file `bootJar` tạo ra.

Với cấu hình và dữ liệu trên, nội dung metadata về mặt khóa/giá trị sẽ gồm:

```properties
build.artifact=order-service
build.version=2.4.1
build.revision=8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b
build.buildId=7318
```

Thứ tự dòng và chú thích của file do Gradle sinh có thể khác. Khi đã nạp thành `BuildProperties`, truy cập `artifact`, `version`, `revision`, `buildId` mà không lặp tiền tố `build.`.

Trong CI thật, lấy commit từ checkout thực sự đã build, kiểm soát nguồn tham số và từ chối cây mã nguồn có thay đổi chưa commit theo chính sách phát hành. Không lấy “commit mới nhất của main” tại lúc triển khai để gắn cho một JAR đã tạo trước đó. Build xong thì chuyển nguyên gói đó qua các môi trường; hồ sơ CI lưu ánh xạ buildId tới checksum/digest, cấu hình build và đầu vào đã chốt.

Không ghi checksum của toàn bộ JAR vào chính file nằm trong JAR rồi kỳ vọng đó là checksum cuối cùng của JAR: thêm trường làm nội dung gói đổi. Lưu checksum cuối ở hồ sơ phát hành bên ngoài gói hoặc dùng cơ chế chứng thực phù hợp.

### 4.2. Chỉ cho phép một contributor xuất hợp đồng đã định

File `src/main/java/com/example/info/ReleaseInfoContributor.java`; đặt dưới phạm vi quét component của ứng dụng:

```java
package com.example.info;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.info.BuildProperties;
import org.springframework.stereotype.Component;

@Component
public final class ReleaseInfoContributor implements InfoContributor {

    private final Map<String, Object> release;

    public ReleaseInfoContributor(BuildProperties build) {
        Map<String, Object> selected = new LinkedHashMap<>();
        selected.put("service", required(
                "artifact", build.getArtifact(), "[a-z][a-z0-9-]{0,62}"));
        selected.put("version", required(
                "version", build.getVersion(),
                "[0-9]+\\.[0-9]+\\.[0-9]+(?:-[A-Za-z0-9.-]+)?"));
        selected.put("revision", required(
                "revision", build.get("revision"), "[0-9a-f]{40}"));
        selected.put("buildId", required(
                "buildId", build.get("buildId"), "[0-9]{1,18}"));
        this.release = Collections.unmodifiableMap(selected);
    }

    private static String required(String field, String value, String pattern) {
        if (value == null || !value.matches(pattern)) {
            throw new IllegalStateException("Invalid release field: " + field);
        }
        return value;
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("release", this.release);
    }
}
```

Bốn thao tác `selected.put` chính là danh sách được phép xuất. Contributor không duyệt mọi thuộc tính trong `BuildProperties`, không gọi `System.getenv()`, không đọc thuộc tính JVM hay đối tượng người dùng. Một khóa mở rộng mới trong build-info không tự đi vào đối tượng `release`.

Các biểu thức chính quy là hợp đồng hẹp của ví dụ: version gồm ba số và tùy chọn hậu tố, commit Git SHA-1 chữ thường, buildId tối đa 18 chữ số. Nếu dự án dùng phiên bản có metadata `+...`, Git SHA-256 hoặc định danh build khác, cần sửa hợp đồng có chủ đích cùng phép kiểm tra. Khớp biểu thức chính quy chỉ xác minh hình thức; CI vẫn phải bảo đảm giá trị đúng nguồn và được phép công bố.

Việc xác thực diễn ra khi tạo bean. Thiếu hoặc sai metadata sẽ làm khởi động ứng dụng không thành công với hợp đồng mẫu này, thay vì trả một phiên bản đoán được. Đây là lựa chọn có chủ đích cho gói phát hành. Nếu cần chế độ phát triển thiếu metadata, thiết kế cấu hình riêng và phép kiểm tra riêng; không âm thầm dùng phiên bản cũ làm giá trị dự phòng.

Thông báo lỗi chỉ nêu tên trường, không ghép giá trị đầu vào vào exception. `Collections.unmodifiableMap` giữ tập trường cố định sau khi khởi tạo.

### 4.3. Kiểm soát contributor và HTTP riêng biệt

`application.yml` cho bài thực hành cục bộ:

```yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
    build:
      enabled: false
    git:
      enabled: false
    env:
      enabled: false
```

`management.info.defaults.enabled=false` tắt các contributor tự cấu hình vốn được bật theo mặc định. Các dòng `build/git/env.enabled=false` làm rõ ý định đối với ba nguồn vừa thảo luận. Cấu hình này không tắt bean `ReleaseInfoContributor` do ứng dụng đăng ký; bean đó vẫn đóng góp mục `release`.

Tắt contributor build không đồng nghĩa xóa metadata hoặc tắt việc nạp bean `BuildProperties`. Mã mẫu vẫn cần bean đó để chọn bốn trường. Nếu không có file build-info hay bean tương ứng, constructor không được thỏa mãn và ứng dụng không khởi động được.

Cũng không hiểu `defaults.enabled=false` là cơ chế cấm mọi contributor: một nguồn được bật rõ ràng ở cấu hình khác, hoặc một bean tự viết khác, vẫn cần được kiểm kê. Chỉ thêm contributor mới sau khi xem xét dữ liệu nó xuất và cập nhật hợp đồng kiểm thử.

Trong ví dụ, HTTP chỉ được đưa ra cho `health` và `info`. Không cần thêm `env`, `configprops` hay dùng `include: "*"` để truy vết phiên bản.

### 4.4. Quan sát kết quả

Nếu ứng dụng thực hành không có lớp xác thực bổ sung, đang dùng cổng mặc định và đường dẫn mặc định:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:8080/actuator/info
```

Phần thân JSON có dữ liệu như hợp đồng ở mục 3; thứ tự khóa và khoảng trắng không phải cam kết của HTTP. Các log khởi động JVM/Spring là luồng riêng, không phải nội dung JSON.

Trên PowerShell, có thể kiểm tra các khóa của đối tượng đã phân tích:

```powershell
$info = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/info'
$info.PSObject.Properties.Name | Sort-Object
$info.release.PSObject.Properties.Name | Sort-Object
```

Với cấu hình mẫu không có contributor khác, đầu ra của hai lệnh liệt kê lần lượt là:

```text
release
buildId
revision
service
version
```

Nếu dự án đã dùng Spring Security hay gateway, giữ cơ chế xác thực hiện có và gọi bằng tài khoản vận hành phù hợp. `exposure.include` không cấp quyền truy cập. Không tắt lớp bảo vệ để làm cho lệnh minh họa trả về `200`.

## 5. Kiểm tra cả dữ liệu đúng lẫn dữ liệu không được xuất

Một lần `curl` thành công chưa chứng minh hợp đồng dữ liệu đã kín. Cần kiểm tra tập khóa chính xác và trường hợp nguồn có thêm thuộc tính.

Ví dụ kiểm tra đơn vị sau dùng JUnit Jupiter, có Spring Boot Actuator trên test classpath; đặt cùng package `com.example.info` trong `src/test/java`:

```java
package com.example.info;

import java.util.Map;
import java.util.Properties;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.info.BuildProperties;

import static org.junit.jupiter.api.Assertions.*;

class ReleaseInfoContributorTest {

    private static Properties metadata() {
        Properties properties = new Properties();
        properties.setProperty("artifact", "order-service");
        properties.setProperty("version", "2.4.1");
        properties.setProperty(
                "revision", "8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b");
        properties.setProperty("buildId", "7318");
        return properties;
    }

    @Test
    void publishesOnlyApprovedFieldsEvenWhenSourceHasMore() {
        Properties properties = metadata();
        properties.setProperty("password", "FAKE_SECRET_FOR_TEST");
        properties.setProperty("commit.user.email", "person@example.invalid");

        ReleaseInfoContributor contributor =
                new ReleaseInfoContributor(new BuildProperties(properties));
        Info.Builder builder = new Info.Builder();
        contributor.contribute(builder);
        Map<String, Object> details = builder.build().getDetails();

        assertEquals(Set.of("release"), details.keySet());
        Map<?, ?> release = (Map<?, ?>) details.get("release");
        assertEquals(
                Set.of("service", "version", "revision", "buildId"),
                release.keySet());
        assertEquals("order-service", release.get("service"));
        assertEquals("2.4.1", release.get("version"));
        assertEquals(properties.getProperty("revision"), release.get("revision"));
        assertEquals("7318", release.get("buildId"));
    }

    @Test
    void refusesMissingRevisionWithoutEchoingItsValue() {
        Properties properties = metadata();
        properties.remove("revision");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> new ReleaseInfoContributor(new BuildProperties(properties)));
        assertEquals("Invalid release field: revision", error.getMessage());
    }

    @Test
    void refusesSensitiveTextInRevision() {
        Properties properties = metadata();
        properties.setProperty("revision", "FAKE_SECRET_FOR_TEST");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> new ReleaseInfoContributor(new BuildProperties(properties)));
        assertEquals("Invalid release field: revision", error.getMessage());
    }
}
```

Trong test, `Properties` đưa vào `BuildProperties` dùng tên khóa đã bỏ tiền tố `build.`. Tất cả giá trị giống bí mật hoặc email ở đây đều là dữ liệu giả.

Test này kiểm tra thuật toán chọn trường của contributor, chưa chứng minh rằng toàn ứng dụng chỉ đăng ký contributor đó. Sau khi chạy `.\gradlew.bat test`, cần kiểm tra thêm HTTP của gói đã build với cấu hình phát hành thực tế:

- Tập khóa gốc đúng là `release`; tập khóa bên trong đúng bốn trường, không chỉ kiểm tra “không có password”.
- Giá trị version/revision/buildId khớp hồ sơ phát hành; không còn dữ liệu của lần build trước.
- Các cấu hình ngoài gói và profile triển khai không bật lại contributor xuất rộng hơn.
- Vai trò vận hành hợp lệ đọc được; người ngoài phạm vi không đọc được theo chính sách đã chọn.
- File đóng gói, log, hệ thống thu thập log và lịch sử CI cũng không chứa dữ liệu nhạy cảm ngoài hợp đồng của từng kênh.

Contributor chỉ lọc phản hồi. Nếu một bí mật đã được ghi vào build-info hoặc git.properties, việc không thấy nó trên HTTP không xóa bí mật đó khỏi JAR. Cần ngăn đưa bí mật vào đầu vào build và kiểm tra gói trước khi phát hành.

## 6. Đưa vào vận hành

### Đặt việc tra cứu vào đúng kênh

Với metadata vận hành nội bộ, giới hạn tuyến quản trị bằng mạng riêng, gateway hoặc cơ chế xác thực/phân quyền của ứng dụng. Có thể dùng cổng quản trị riêng nếu kiến trúc triển khai hỗ trợ. Cổng riêng chỉ tách điểm nghe; địa chỉ bind, firewall, proxy và quyền truy cập mới quyết định ai tới được.

Cấu hình mẫu đang bind ứng dụng vào loopback để thực hành trên máy cá nhân. Đây không phải cấu hình triển khai áp dụng nguyên xi cho mọi container: loopback trong container thuộc không gian mạng của container. Khi đổi địa chỉ/cổng, kiểm tra đường truy cập thực tế từ bên ngoài và dùng HTTPS trên kênh mạng cần bảo vệ.

Không truyền token trong query string để đọc metadata. Tránh log nguyên header xác thực hoặc đưa dữ liệu trả về lên trang công khai khi hợp đồng chỉ cho phép truy cập nội bộ.

### Đối chiếu đúng tiến trình trong triển khai nhiều bản sao

Giả sử bản `2.4.1` tương ứng build `7318`. Trong cập nhật cuốn chiếu, một số bản sao có thể vẫn chạy `2.4.0`. Gọi qua load balancer hai lần có thể nhận hai tập định danh khác nhau; đây có thể là trạng thái chuyển tiếp cần kiểm tra, không nhất thiết là lỗi `InfoContributor`.

Quy trình xác nhận:

1. Lấy hồ sơ bản phát hành mục tiêu từ CI/kho phát hành.
2. Gọi từng bản sao qua kênh quản trị được kiểm soát hoặc đối chiếu qua nền tảng triển khai.
3. So service/version/revision/buildId với hồ sơ của gói được triển khai.
4. Nếu lệch, kiểm tra image/JAR thực tế, rollout, cấu hình ghi đè và cache HTTP.
5. Chỉ kết luận đã cập nhật toàn bộ khi mọi bản sao thuộc phạm vi đều đạt trạng thái mong muốn.

Không cần thêm hostname chứa tên người hoặc mã khách hàng vào `/info` để thực hiện việc này. Có thể tra định danh bản sao trong hệ thống điều phối nội bộ. Nếu proxy có cache phản hồi, cấu hình chính sách cache thích hợp và xác nhận dữ liệu đang đọc tới đúng backend.

Khi rollback, bộ định danh phải trở về đúng gói cũ đã phát hành. Không sửa riêng version trong cấu hình để tạo cảm giác bản vá mới đã chạy. Phân biệt “gói đang chạy” với “cấu hình triển khai hiện tại”; cùng một gói có thể chạy với cấu hình khác nhau mà bộ metadata build không đổi.

## 7. Các lỗi thường gặp và hướng xử lý

| Quan sát | Điều cần kiểm tra |
| --- | --- |
| `404` tại `/actuator/info` | Exposure, endpoint có bị tắt không, base path, context path, cổng quản trị và định tuyến proxy; mã HTTP có thể do proxy tạo |
| `401/403` | Cơ chế xác thực/phân quyền và lớp proxy; không chữa bằng cách bỏ bảo vệ |
| JSON rỗng `{}` | Không có contributor đóng góp hoặc contributor mẫu chưa được quét; kiểm tra cấu hình/bean |
| Không khởi động, thiếu `BuildProperties` | Task sinh metadata có chạy không, resource có trong gói đang chạy không; IDE có thể chưa chạy task Gradle |
| `Invalid release field: revision` | Tham số build thiếu/sai hợp đồng; sửa nguồn metadata rồi build lại |
| JSON xuất thêm `build`, `git` hoặc khóa khác | Contributor khác hoặc cấu hình ngoài đã được bật; kiểm tra toàn ứng dụng |
| Commit đúng nhưng hành vi khác | Đối chiếu artifact/digest, dependency và cấu hình; commit chưa đủ định danh mọi đầu vào |
| Hai lần gọi trả hai phiên bản | Kiểm tra backend phía load balancer, rollout và cache trước khi kết luận |

Tránh hardcode phiên bản trong Java rồi quên đổi ở lần phát hành sau. Tránh đọc nhãn triển khai có thể thay đổi để giả làm metadata của gói. Tạo metadata từ chính lần build và dùng mã build làm khóa tra hồ sơ giúp giảm hai loại sai lệch này.

## 8. Thực hành

1. Build ứng dụng với bộ định danh mẫu; gọi `/actuator/info` và đối chiếu bốn trường với metadata đóng gói.
2. Thêm một thuộc tính giả chưa được duyệt vào nguồn build-info; xác nhận `release` vẫn chỉ có đúng bốn khóa. Sau thử nghiệm, bỏ dữ liệu giả khỏi cấu hình build.
3. Bỏ `sourceRevision` khỏi lệnh build: build phải thất bại vì thiếu tham số bắt buộc. Chỉ kết luận dựa trên lần build mới, không chạy nhầm JAR cũ còn trong thư mục.
4. Cấp revision sai định dạng: nếu build tạo được gói, gói đó phải bị hợp đồng của contributor từ chối khi khởi động.
5. Chạy hai gói với bộ định danh khác nhau trên hai cổng cục bộ, đọc từng gói và giải thích vì sao đọc qua một địa chỉ cân bằng tải không đủ xác nhận mọi bản sao đã được cập nhật.
6. Với một trường mới được đề xuất, trả lời: trường này giúp tra cứu việc gì, có chứa dữ liệu cá nhân/bí mật không, ai được xem và có thể giữ nó chỉ trong hồ sơ nội bộ hay không?

Kết quả cần đạt là khả năng nối tiến trình với đúng hồ sơ phát hành bằng một hợp đồng metadata nhỏ, kiểm chứng được, cùng phạm vi truy cập đã xác định.
