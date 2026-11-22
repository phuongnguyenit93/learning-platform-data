# Nạp bí mật thử nghiệm từ configtree: với dữ liệu giả lập trong Spring Boot

## 1. Mục tiêu thực hành

Trong ứng dụng Spring Boot, thông tin nhạy cảm thường được cung cấp tại thời điểm triển khai thay vì được đóng gói trong JAR. Một số nền tảng như Kubernetes và Docker có thể đưa secret vào container thông qua **các file được mount**. Khi mỗi file đại diện cho một thuộc tính và nội dung file là giá trị, Spring Boot có thể nạp toàn bộ cây file bằng cơ chế Config Data với tiền tố `configtree:`.

Bài này thuộc nhóm **Thực hành tổng hợp** của Spring Boot Externalized Configuration. Mục tiêu là tái hiện cách ứng dụng production nhận bí mật từ mounted files **mà không cần dùng bất kỳ bí mật thật nào**. Toàn bộ ví dụ dùng token, mật khẩu, tên tài khoản và endpoint giả lập.

Kết quả học tập:

1. Phân biệt config tree với file YAML/properties bình thường và với biến môi trường.
2. Tạo thư mục chứa các file giả lập bằng Java, Bash hoặc công cụ test.
3. Nạp dữ liệu bằng `spring.config.import=configtree:...` trong đúng giai đoạn Config Data.
4. Liên kết các giá trị vào `@ConfigurationProperties` và kiểm tra bằng JUnit.
5. Hiểu cách tên thư mục/file trở thành property key, kể cả dot notation và cây thư mục lồng nhau.
6. Phân biệt thiếu **directory** với thiếu một **file/key** trong directory.
7. Kiểm thử import bắt buộc, import tùy chọn, precedence, secret dạng chuỗi và binary.
8. Hạn chế rò rỉ qua logs, exception, test reports, Git, CI và build artifacts.
9. Dọn dẹp tài nguyên tạm sau test, giữ các ca kiểm thử cô lập và lặp lại được.
10. Chuyển được mô hình test sang Docker/Kubernetes mà không dùng credential production.

**Nguyên tắc:** kiểm thử cơ chế **đọc và binding** bằng dữ liệu giả. Không đem token thật vào test chỉ để chứng minh config tree hoạt động.

## 2. Config tree là gì?

Một application config thường được viết như:

~~~properties
demo.client.api-key=FAKE_TOKEN_001
demo.client.username=demo-user
demo.client.password=FAKE_PASSWORD_001
~~~

Ở mô hình configuration tree, một số nền tảng không cấp một file tổng hợp như trên. Thay vào đó, mỗi key là **một file**:

~~~text
/tmp/demo-secrets/
├── demo.client.api-key
├── demo.client.username
└── demo.client.password
~~~

Nội dung file:

~~~text
demo.client.api-key   -> FAKE_TOKEN_001
demo.client.username  -> demo-user
demo.client.password  -> FAKE_PASSWORD_001
~~~

Với file Config Data:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

Spring Boot ánh xạ tên file thành property key, rồi nạp nội dung file làm value:

| File | Property trong Environment | Giá trị giả |
| --- | --- | --- |
| `demo.client.api-key` | `demo.client.api-key` | `FAKE_TOKEN_001` |
| `demo.client.username` | `demo.client.username` | `demo-user` |
| `demo.client.password` | `demo.client.password` | `FAKE_PASSWORD_001` |

Đây là cơ chế **Config Data import**, không phải lệnh đọc tất cả file tùy ý bằng `@Value` và cũng không phải một secret manager.

### 2.1. Sự khác biệt với một file properties

File properties tổng hợp:

~~~text
/tmp/demo-secrets/application.properties
~~~

cần được nạp như **một Config Data file**:

~~~properties
spring.config.import=file:/tmp/demo-secrets/application.properties
~~~

Trong khi cấu trúc **mỗi file là một key** dùng:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

Nếu dùng `configtree:` cho directory chứa một file tên `application.properties`, tên đó có thể được coi là **property key** thay vì tự parse nội dung file thành nhiều properties. Chọn đúng loại import dựa trên cách dữ liệu được trình bày.

### 2.2. Config tree không tự mã hóa giá trị

`configtree:` chỉ là cơ chế đọc dữ liệu từ filesystem và đưa vào `Environment`. Nó không mã hóa file, không tự cấu hình ACL, không xác nhận token còn hiệu lực và không xoay vòng secret.

Đối với production, trách nhiệm bảo vệ file thuộc về nền tảng mount, secret manager, quyền truy cập của container và quy trình vận hành. Trong bài test, chỉ sử dụng **giá trị giả vô hại**.

### 2.3. Cơ chế này thuộc Spring Boot 2.4+ Config Data

Những ví dụ dùng `spring.config.import` và `configtree:` dựa trên cơ chế Config Data được giới thiệu từ Spring Boot 2.4 và vẫn được dùng trong các phiên bản Boot hiện đại. Với dự án cũ hơn, cần kiểm tra đúng reference documentation của phiên bản đang chạy thay vì sao chép cú pháp không tương thích.

## 3. Kịch bản thực hành

Ta giả lập một ứng dụng gửi request tới một external client. Ứng dụng cần ba giá trị:

- `demo.client.api-key`: mã xác thực giả.
- `demo.client.username`: tên đăng nhập giả.
- `demo.client.password`: mật khẩu giả.

Không tạo network request thật. Mục tiêu là kiểm tra:

~~~text
Temporary directory
    |
    +-- demo.client.api-key  (FAKE_TEST_KEY_284)
    +-- demo.client.username (demo-user)
    +-- demo.client.password (FAKE_TEST_PASSWORD_284)
    |
    v
spring.config.import=configtree:<temporary-directory>/
    |
    v
Spring Boot Config Data
    |
    v
Environment
    |
    v
@ConfigurationProperties(prefix = "demo.client")
    |
    v
DemoClientSecrets bean
    |
    v
JUnit assertions
~~~

Điểm đáng chú ý là không hardcode secret giả vào `src/main/resources/application.yml` để mô phỏng runtime. Ta **tạo các file khi test chạy**, rồi khởi động application context sau khi directory đã sẵn sàng.

## 4. Điều kiện chuẩn bị

Ví dụ Java dùng:

- Java 17+.
- Spring Boot có cơ chế Config Data.
- Spring Boot Test và JUnit Jupiter.
- AssertJ (thường được kéo theo bởi `spring-boot-starter-test`).
- Một project có hỗ trợ Maven hoặc Gradle.
- Filesystem cho phép tạo temporary directory.

Nếu muốn dùng Bean Validation với `@NotBlank`, cần thêm một Jakarta Bean Validation provider; trong nhiều dự án Boot có thể dùng `spring-boot-starter-validation`.

Với Spring Boot 3.x/4.x, chú ý version cụ thể của Spring Framework, Java và các starter vì chi tiết dependency có thể thay đổi. Code dưới đây tập trung vào những API cơ bản: `SpringApplicationBuilder`, `@ConfigurationProperties`, `@EnableConfigurationProperties`, `@TempDir` và Java NIO.

### 4.1. Một cấu trúc project gợi ý

~~~text
demo-app/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/demo/config/
│   │   │   └── DemoClientSecrets.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/demo/
│           └── ConfigTreeSecretsIntegrationTest.java
└── .gitignore
~~~

Không cần thêm directory secret giả vào Git. JUnit có thể tạo nó tại temp directory của hệ điều hành khi mỗi test chạy.

## 5. Định nghĩa model cấu hình

Tạo `DemoClientSecrets.java`:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(
        String apiKey,
        String username,
        String password
) {
}
~~~

Đây là một record immutable nhận giá trị thông qua constructor binding được Spring Boot hỗ trợ cho configuration properties. Các component của record tương ứng với:

~~~text
apiKey    -> demo.client.api-key
username  -> demo.client.username
password  -> demo.client.password
~~~

Sử dụng canonical key dạng lowercase kebab-case. Spring Boot Binder sẽ ánh xạ `api-key` sang Java component `apiKey` theo relaxed binding.

### 5.1. Vì sao dùng record trong bài?

Record giúp tránh việc các test sửa credential sau khi context được tạo. Nó cũng minh họa type-safe configuration properties của Spring Boot.

**Cảnh báo:** record tự sinh `toString()` bao gồm các component. Do đó **không log nguyên object `DemoClientSecrets`** trong ứng dụng thật, vì nó có thể chứa token hoặc password. Bài test chỉ assert giá trị giả mà không in object ra log.

### 5.2. Có thể dùng JavaBean thay record

Với thư viện cũ hoặc object mutable, có thể dùng class:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public class DemoClientSecrets {

    private String apiKey;
    private String username;
    private String password;

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    public String getUsername() { return username; }
    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() { return password; }
    public void setPassword(String password) {
        this.password = password;
    }
}
~~~

Hai kiểu target đều có thể nhận dữ liệu từ `Environment` nhưng khác nhau về object construction và mutability. `configtree:` không yêu cầu riêng record hay JavaBean.

## 6. Tạo thư mục file giả lập bằng Bash

Trong Linux/macOS hoặc container shell:

~~~bash
mkdir -p /tmp/demo-configtree

printf '%s' 'FAKE_TEST_KEY_284' \
  > /tmp/demo-configtree/demo.client.api-key

printf '%s' 'demo-user' \
  > /tmp/demo-configtree/demo.client.username

printf '%s' 'FAKE_TEST_PASSWORD_284' \
  > /tmp/demo-configtree/demo.client.password
~~~

Bash ở đây chỉ tạo **dữ liệu giả**, không dùng bất kỳ hệ thống xác thực nào.

### 6.1. Vì sao dùng printf thay echo?

`echo` thường thêm một ký tự newline cuối nội dung. Với password/token, newline vô tình thêm vào có thể làm giá trị không như dự kiến, đặc biệt khi thư viện không trim.

~~~bash
printf '%s' 'FAKE_TEST_KEY_284'
~~~

ghi đúng chuỗi giả và không có newline kết thúc. Nếu một test cố ý cần kiểm tra trailing newline, tạo case riêng và assert rõ cách ứng dụng xử lý.

### 6.2. Không commit thư mục được tạo

`/tmp/demo-configtree` chỉ là ví dụ trên filesystem của máy local/container. Trong CI, dùng một temporary directory riêng cho từng test thay vì một path dùng chung; tránh tranh chấp khi test chạy song song.

Nếu file nằm trong workspace của project, đưa directory fixture chứa **giá trị thật** vào ignore và bảo đảm pipeline không copy vào JAR/image. Với giá trị giả, vẫn nên tạo runtime để mô phỏng chính xác cơ chế mounted secret.

### 6.3. Không sử dụng file tên application.properties cho tree này

Ví dụ:

~~~text
/tmp/demo-configtree/demo.client.api-key
~~~

là file có tên **property**, không phải file chứa `key=value`. Nếu bạn viết:

~~~text
demo.client.api-key=FAKE_TEST_KEY_284
~~~

bên trong file `demo.client.api-key`, Binder có thể nhận nguyên chuỗi gồm `demo.client.api-key=...` làm **value**. Chỉ ghi nội dung secret giả, không ghi lại tên property vào file.

## 7. Nạp Config Tree trong ứng dụng

Một file Config Data được Boot nạp có thể khai báo:

~~~properties
spring.config.import=configtree:/tmp/demo-configtree/
~~~

Hoặc YAML:

~~~yaml
spring:
  config:
    import: "configtree:/tmp/demo-configtree/"
~~~

Khi Spring Boot khởi động, cơ chế Config Data import sẽ đọc thư mục và tạo các properties:

~~~text
demo.client.api-key
demo.client.username
demo.client.password
~~~

Từ đó, `@ConfigurationProperties(prefix = "demo.client")` có thể bind ba giá trị vào `DemoClientSecrets`.

### 7.1. Dấu slash ở cuối directory

Ví dụ và tài liệu Boot dùng location có dấu `/` cuối cho directory:

~~~text
configtree:/tmp/demo-configtree/
~~~

Nên luôn viết rõ directory location, nhất là khi xây path động. Một location biểu diễn file đơn sẽ có semantic khác.

### 7.2. Tên import không phải path classpath

~~~properties
spring.config.import=configtree:/tmp/demo-configtree/
~~~

là filesystem tree trong môi trường chạy. Không nhầm nó với:

~~~properties
spring.config.import=classpath:/demo-configtree/
~~~

Một Config Tree điển hình đại diện cho volume được mount ngoài JAR. Muốn test mounted secrets, nên dùng external temporary directory hoặc fixture filesystem tách khỏi classpath artifacts.

### 7.3. Ví dụ khởi động qua command line

Giả sử ứng dụng đã đăng ký configuration properties. Có thể khởi động với:

~~~bash
java -jar demo.jar \
  --spring.config.import=configtree:/tmp/demo-configtree/
~~~

Cách này hữu ích cho thao tác thủ công với fake secrets. Với production, import location thường được khai báo trong Config Data phù hợp hoặc trong deployment bootstrap, còn file được mount bởi nền tảng.

Không đưa **secret value** vào command-line arguments. Ví dụ chỉ truyền **location**, không truyền password.

## 8. Test tích hợp dùng @TempDir và SpringApplicationBuilder

Phần này là bài thực hành chính. Ta không dựa vào một directory cố định có thể bị chia sẻ giữa test sessions.

JUnit Jupiter cung cấp `@TempDir` để mỗi test có một temporary directory. Ta:

1. Tạo file giả bằng `Files.writeString`.
2. Tính import location tương ứng.
3. Khởi động một Spring context **sau khi file đã có**.
4. Kiểm tra bean được binding.
5. Đóng context bằng try-with-resources.
6. Để JUnit quản lý cleanup của thư mục tạm.

### 8.1. Cấu hình tối thiểu dành cho test

~~~java
package com.example.demo;

import com.example.demo.config.DemoClientSecrets;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableConfigurationProperties(DemoClientSecrets.class)
public class FixtureApplication {
}
~~~

`@SpringBootConfiguration` đánh dấu một class cấu hình Boot. `@EnableConfigurationProperties` đăng ký bean được bind theo prefix. Đây là một test application nhỏ, không cần kết nối database hoặc gọi external service.

Chúng ta dùng `SpringApplicationBuilder` để đi qua quá trình Spring Boot bootstrap và xử lý Config Data, thay vì chỉ tạo `Environment` bằng tay.

### 8.2. Hàm dựng import location

~~~java
import java.nio.file.Path;

static String configTreeLocation(Path directory) {
    String absolute = directory
            .toAbsolutePath()
            .toString()
            .replace('\\', '/');

    return "configtree:" + absolute + "/";
}
~~~

Ở Linux/macOS, kết quả có dạng:

~~~text
configtree:/tmp/junit123456789/secret-tree/
~~~

Trên Windows, cần bảo đảm location được Boot xử lý đúng với drive/root và path đang sử dụng. Ví dụ dùng dấu slash thuận tiện cho nhiều môi trường, nhưng test harness thực tế nên được kiểm tra trên các OS dự án hỗ trợ.

### 8.3. JUnit test chính

~~~java
package com.example.demo;

import com.example.demo.config.DemoClientSecrets;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigTreeSecretsIntegrationTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void loadsFakeSecretsFromConfigTree() throws IOException {
        Path secrets = Files.createDirectory(
                temporaryDirectory.resolve("secrets")
        );

        Files.writeString(
                secrets.resolve("demo.client.api-key"),
                "FAKE_TEST_KEY_284",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                secrets.resolve("demo.client.username"),
                "demo-user",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                secrets.resolve("demo.client.password"),
                "FAKE_TEST_PASSWORD_284",
                StandardCharsets.UTF_8
        );

        String path = configTreeLocation(secrets);

        try (ConfigurableApplicationContext context =
                new SpringApplicationBuilder(FixtureApplication.class)
                    .web(WebApplicationType.NONE)
                    .properties(
                        "spring.config.import=" + path,
                        "spring.main.banner-mode=off"
                    )
                    .run()) {

            DemoClientSecrets credentials =
                    context.getBean(DemoClientSecrets.class);

            assertThat(credentials.apiKey())
                    .isEqualTo("FAKE_TEST_KEY_284");
            assertThat(credentials.username())
                    .isEqualTo("demo-user");
            assertThat(credentials.password())
                    .isEqualTo("FAKE_TEST_PASSWORD_284");
        }
    }

    private static String configTreeLocation(Path directory) {
        return "configtree:"
            + directory.toAbsolutePath()
                .toString()
                .replace('\\', '/')
            + "/";
    }
}
~~~

Bài test minh họa cách dùng `SpringApplicationBuilder.properties(...)` để đưa **đường dẫn import** vào default properties trước khi gọi `run()`; sau đó Spring Boot Config Data processing có cơ hội xử lý import. Điều này khác với việc chỉ thêm ba key fake vào context sau khi bootstrap.

**Lưu ý về project:** mã ví dụ cần nằm cùng package hoặc import được `FixtureApplication` và `DemoClientSecrets`; phải có starter test cùng phiên bản Boot. Nếu project có application config khác được nạp theo default locations, cần cô lập test app hoặc test environment để tránh source không mong đợi.

### 8.4. Mục đích của từng lệnh

- `@TempDir`: cung cấp directory riêng cho test.
- `Files.createDirectory`: tạo directory thực để import.
- `Files.writeString`: ghi đúng dữ liệu giả, không thêm newline.
- `configtree:.../`: chỉ rõ đây là **directory tree**.
- `SpringApplicationBuilder(...).run()`: khởi động Boot context sau khi files tồn tại.
- `getBean(DemoClientSecrets.class)`: kiểm tra bean được đăng ký/bind.
- `assertThat(...)`: xác nhận chính xác values ở test.
- `try (...)`: đóng context sau test; JUnit lo cleanup temp directory.

Không có dòng nào cần gọi external API, giải mã secret hoặc in credential vào log.

## 9. Phân biệt test đúng import với test chỉ bind values

Giả sử test viết:

~~~java
new ApplicationContextRunner()
    .withPropertyValues(
        "demo.client.api-key=FAKE_TEST_KEY_284"
    )
    .run(context -> { /* assertions */ });
~~~

Test này có thể chứng minh Binder nhận một property value, nhưng **không chứng minh Boot đã đọc file từ configtree**. Nguồn được đưa trực tiếp vào context, bỏ qua bước import file.

Tương tự:

~~~java
@TestPropertySource(properties =
    "demo.client.api-key=FAKE_TEST_KEY_284")
~~~

có thể kiểm tra binding, nhưng không mô phỏng file mounted.

Để kiểm tra configtree thật, bài test cần:

1. Có directory và file trên filesystem.
2. Đưa `spring.config.import=configtree:<directory>/` vào Boot ở đúng giai đoạn.
3. Khởi động Boot Config Data processing.
4. Đọc bean/property sau khi context đã được tạo.
5. Không đồng thời cấp cùng key qua inline test property ưu tiên cao hơn, vì giá trị inline có thể che mất lỗi import.

### 9.1. Tránh false positive do default values

Nếu class có default token bằng chính chuỗi fake mà test đang mong đợi, test có thể pass dù file không được đọc. Hãy chọn fake value chỉ nằm trong file test được tạo và assert nó.

### 9.2. Một marker property riêng

Có thể tạo thêm file:

~~~text
demo.client.fixture-source
~~~

chứa:

~~~text
temporary-config-tree
~~~

Rồi assert:

~~~java
assertThat(context.getEnvironment()
    .getProperty("demo.client.fixture-source"))
    .isEqualTo("temporary-config-tree");
~~~

Marker này giúp xác định dữ liệu có thật sự đến từ directory test. Không dùng marker có giá trị nhạy cảm.

## 10. Tên file và cấu trúc thư mục quyết định property key

Spring Boot ánh xạ folder/file names trong config tree thành key.

Cách thứ nhất — dot notation ở tên file:

~~~text
secrets/
└── demo.client.api-key
~~~

Cho property:

~~~text
demo.client.api-key
~~~

Cách thứ hai — directories lồng nhau:

~~~text
secrets/
└── demo/
    └── client/
        └── api-key
~~~

Cũng biểu diễn property theo prefix:

~~~text
demo.client.api-key
~~~

### 10.1. Root import thay đổi tên property

Nếu directory:

~~~text
/tmp/testmount/
└── demo/
    └── client/
        └── api-key
~~~

thì:

~~~properties
spring.config.import=configtree:/tmp/testmount/
~~~

có thể cung cấp `demo.client.api-key`.

Nhưng:

~~~properties
spring.config.import=configtree:/tmp/testmount/demo/client/
~~~

thường chỉ cung cấp key `api-key`, vì phần `demo/client` đã nằm **trên root import**.

Đây là lỗi phổ biến: file có nội dung đúng nhưng `@ConfigurationProperties(prefix="demo.client")` vẫn nhận null vì import root quá sâu.

### 10.2. Không nhầm Secret object name với property key

Một Kubernetes Secret có tên `gateway-credentials` không tự tạo property `gateway.credentials.*`. Cấu trúc file **sau khi mount** mới quyết định names mà configtree nhìn thấy. Deployment có thể map key từ Secret object thành filename khác để khớp tên cấu hình Java.

### 10.3. Nên dùng tên key canonical

Đối với configuration properties, nên chọn tên lowercase kebab-case:

~~~text
demo.client.api-key
demo.client.username
demo.client.password
~~~

Từ đó Binder liên kết đến Java fields `apiKey`, `username`, `password` theo relaxed binding. Không đặt tên file là một biến môi trường tùy ý `DEMO_CLIENT_API_KEY` rồi mong nó tự trở thành key dotted chuẩn, trừ khi đã kiểm tra cách source đó được xử lý.

## 11. Missing directory và missing property: hai lỗi khác nhau

Đây là phần quan trọng của thực hành.

### 11.1. Directory import bắt buộc không tồn tại

~~~properties
spring.config.import=configtree:/path/not-exists/
~~~

Nếu location Config Data bắt buộc không có, Spring Boot có thể ném `ConfigDataLocationNotFoundException` và startup thất bại.

Thông điệp vận hành nên nói location/loại source đang thiếu ở mức không nhạy cảm, không dump nội dung secret.

### 11.2. Optional directory không tồn tại

~~~properties
spring.config.import=optional:configtree:/path/not-exists/
~~~

Với `optional:`, Boot có thể tiếp tục khi **location** không tồn tại. Điều này không có nghĩa mọi property bắt buộc được tự tạo.

Nếu ứng dụng vẫn cần `demo.client.api-key`, nó có thể nhận null/blank và cần validation riêng.

### 11.3. Directory có nhưng thiếu file api-key

~~~text
secrets/
├── demo.client.username
└── demo.client.password
~~~

Import:

~~~properties
spring.config.import=configtree:/tmp/demo-secrets/
~~~

Location tồn tại nên import có thể thành công. Nhưng property `demo.client.api-key` không xuất hiện. `optional:` có hay không **không giải quyết missing key**; cần `@NotBlank`, required-property check hoặc validation ở tầng ứng dụng.

### 11.4. File tồn tại nhưng rỗng

~~~text
secrets/
└── demo.client.api-key  (zero bytes)
~~~

Đây là tình huống khác với missing file. Bản thân Binder có thể bind một chuỗi rỗng; validation mới quyết định nó có được chấp nhận hay không.

### 11.5. Bảng phân loại

| Hiện tượng | Config Data import | Value của field | Cách xử lý |
| --- | --- | --- | --- |
| Directory bắt buộc thiếu | Có thể fail bootstrap | Chưa bind | Sửa mount/location |
| Directory optional thiếu | Có thể tiếp tục | Không có key từ tree | Validate nếu bắt buộc |
| Directory tồn tại, key thiếu | Import có thể thành công | Null hoặc không được cung cấp | Validate missing key |
| Key tồn tại, file rỗng | Import có dữ liệu rỗng | Blank theo target | Validate non-blank |
| Key tồn tại, file có newline | Import có ký tự thêm | Có thể chứa newline | Test/định nghĩa trimming |
| Key có ở nguồn cao hơn | Import vẫn có thể thành công | Source cao hơn thắng | Xác định precedence |
| Filename không khớp prefix | Import file thành key khác | Target field không nhận | Sửa tên file/root |

## 12. Bổ sung Bean Validation cho secret bắt buộc

Nếu application thực sự yêu cầu cả ba trường, có thể khai báo:

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(
        @NotBlank String apiKey,
        @NotBlank String username,
        @NotBlank String password
) {}
~~~

Trong Spring Boot 3.x với Jakarta Validation, provider phù hợp phải có trên classpath, thường qua `spring-boot-starter-validation`. Lúc đó, thiếu/blank field có thể được phát hiện sớm khi binding/validation bean.

### 12.1. Validation message cần an toàn

Nếu một field chứa token, không tạo message bằng cách nối giá trị thực:

~~~java
throw new IllegalStateException(
    "Invalid API key: " + secrets.apiKey()
);
~~~

Nên mô tả hợp đồng:

~~~java
throw new IllegalStateException(
    "demo.client.api-key must be present and non-blank"
);
~~~

Đừng giả định mọi conversion error hoặc framework failure report luôn được redacted; cần có kiểm thử log với fake canary.

### 12.2. Không hardcode fallback credential

Không nên:

~~~properties
demo.client.api-key=${DEMO_API_KEY:production-password}
~~~

Với secret bắt buộc, việc dùng password mặc định có thể khiến ứng dụng chạy trong trạng thái sai. Bài này dùng fake token chỉ ở test fixture, không làm default của production.

### 12.3. Fail fast hay optional theo nghiệp vụ

- Nếu client không thể hoạt động thiếu credential, startup failure có thông điệp an toàn thường phù hợp.
- Nếu feature được tắt trong một profile, credential có thể không cần thiết; khi đó dùng một điều kiện và validation đúng phạm vi.
- Đừng thêm `optional:` chỉ để vượt qua lỗi triển khai mà không thay đổi hợp đồng của feature.

## 13. Test trường hợp thiếu file

Dùng cùng `@TempDir` nhưng chỉ tạo hai file:

~~~java
@Test
void missingApiKeyDoesNotAppearInEnvironment(
        @TempDir Path temp
) throws IOException {

    Path secrets = Files.createDirectory(
            temp.resolve("secrets")
    );

    Files.writeString(
            secrets.resolve("demo.client.username"),
            "demo-user",
            StandardCharsets.UTF_8
    );

    Files.writeString(
            secrets.resolve("demo.client.password"),
            "FAKE_TEST_PASSWORD_284",
            StandardCharsets.UTF_8
    );

    try (ConfigurableApplicationContext context =
            new SpringApplicationBuilder(FixtureApplication.class)
                .web(WebApplicationType.NONE)
                .properties(
                    "spring.config.import="
                      + configTreeLocation(secrets)
                )
                .run()) {

        assertThat(context.getEnvironment()
            .containsProperty("demo.client.api-key"))
            .isFalse();
    }
}
~~~

Ví dụ này giả định `DemoClientSecrets` **chưa được gắn ràng buộc validation bắt buộc**, để context có thể khởi động và test sự hiện diện của property. Nếu dùng version có `@NotBlank`, context có thể fail trước khi assertion chạy; lúc đó cần test failure riêng.

### 13.1. Test validation failure một cách có chủ đích

Có thể viết một test với configuration class đã đăng ký bean có validation và không tạo file api-key. Kỳ vọng quá trình tạo context thất bại.

Không khóa test vào một chuỗi exception message dài, vì thông điệp nội bộ và lớp wrapper có thể khác giữa phiên bản Spring Boot. Nên xác minh **kiểu nhóm lỗi phù hợp**, key vi phạm nếu được báo an toàn và không xuất hiện fake secret trong logs.

### 13.2. Test directory không tồn tại

Khác với thiếu file:

~~~java
Path missingDirectory = temp.resolve("not-created");
String importLocation =
        configTreeLocation(missingDirectory);
~~~

Nếu location bắt buộc, thử khởi động Boot và assert failure. Nếu có `optional:configtree:...`, Boot có thể tiếp tục khi thiếu location; test phải phân biệt hai hợp đồng.

### 13.3. Không nuốt lỗi bằng ignore-on-not-found

Spring Boot có một số cơ chế bỏ qua missing Config Data location. Không sử dụng toàn cục chỉ để khiến test pass; việc đó có thể che lỗi mount nghiêm trọng trong production.

## 14. Optional import không có nghĩa secret optional

Một file test:

~~~properties
spring.config.import=optional:configtree:./secrets/
~~~

chỉ cho phép Boot bỏ qua **location** bị thiếu theo cơ chế Config Data.

Nếu class ứng dụng cần:

~~~java
@NotBlank String apiKey;
~~~

thì validation vẫn có thể thất bại. Đó là behavior đúng: vị trí import được phép thiếu, nhưng một tính năng đang bật có thể vẫn yêu cầu credential.

Khi thiết kế test, hãy đặt tên rõ:

- `missingLocationIsAllowedWhenOptional`: tập trung vào Config Data.
- `missingRequiredKeyFailsValidation`: tập trung vào contract của bean.
- `disabledFeatureDoesNotRequireKey`: tập trung vào business condition, nếu được thiết kế.

Đừng gộp ba trường hợp thành một test “configtree is optional” mơ hồ.

## 15. Text files, newline và encoding

Với secret được mount, nội dung file là dữ liệu, không phải lời khai `key=value`. Các thay đổi nhỏ trong file có thể làm credential sai.

### 15.1. Tránh newline ngoài ý muốn

~~~bash
echo FAKE_TEST_KEY_284 > demo.client.api-key
~~~

thường thêm newline. Trong khi:

~~~bash
printf '%s' 'FAKE_TEST_KEY_284' > demo.client.api-key
~~~

không thêm newline. Một số client/authentication libraries không trim; khi đó token chứa newline có thể bị remote service từ chối.

### 15.2. Test whitespace theo hợp đồng

Nếu yêu cầu là phải giữ chính xác bytes, đừng tự động gọi `String.trim()` trên mọi secret. Với password, trailing spaces đôi khi có thể là một phần của credential. Nếu hệ thống muốn strip newline do platform mount, phải có một rule rõ, chỉ áp cho loại secret đó và có test.

### 15.3. UTF-8 và dữ liệu đa byte

`Files.writeString(..., UTF_8)` tạo file test có encoding xác định. Với secret text cần đọc thành `String`, hãy xác nhận encoding của nguồn cấp phù hợp với consumer.

Không giả định mọi secret đều là text: certificate, private key, keystore và binary tokens có thể cần được xử lý dưới dạng bytes hoặc file resource.

### 15.4. Không log bytes như chuỗi

Một lỗi debug thường gặp:

~~~java
log.info("Loaded key bytes: {}", new String(keyBytes));
~~~

Trong ứng dụng thật đây là cách làm lộ secret, và còn có nguy cơ phá dữ liệu nhị phân. Log loại key, trạng thái presence hoặc mã lỗi; không log nội dung.

## 16. Bind config tree value sang byte[]

Spring Boot hỗ trợ bind configuration tree values sang `String` hoặc `byte[]` tùy target type.

Ví dụ class:

~~~java
package com.example.demo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.signing")
public record SigningProperties(byte[] keyMaterial) {}
~~~

Test tạo file:

~~~java
byte[] fakeBytes = new byte[] {
    0x01, 0x23, 0x45, 0x67
};

Files.write(
    secrets.resolve("demo.signing.key-material"),
    fakeBytes
);
~~~

Sau Config Data import, Bean có thể nhận dữ liệu bytes. Kiểm tra:

~~~java
assertThat(signingProperties.keyMaterial())
    .containsExactly(0x01, 0x23, 0x45, 0x67);
~~~

Để test compile trong Java với AssertJ, giá trị byte literals trong `containsExactly` cần phù hợp type; có thể dùng `(byte) 0x01`... khi API overload đòi byte values.

### 16.1. Không dùng binary test để chứa private key thật

Dù muốn test parsing keystore/TLS, dùng generated test key không có quyền production hoặc fake bytes thích hợp. Không copy keystore production vào `src/test/resources` chỉ để test bind.

### 16.2. Phân biệt bytes với base64 string

Một file chứa các ký tự base64 là **text encoding**, không tự động giống file chứa bytes gốc. Hãy xác định class target, converter và cách secret provider cung cấp dữ liệu trước khi assert.

### 16.3. Tránh String khi dữ liệu cần giữ nguyên bytes

Nếu consumer đòi exact bytes, sử dụng `byte[]` hoặc đọc file resource bằng API phù hợp thường rõ hơn việc chuyển qua `String` rồi encode lại.

## 17. Quy tắc đặt tên file và relaxed binding

Model Java:

~~~java
@ConfigurationProperties(prefix = "demo.client")
public record DemoClientSecrets(String apiKey) {}
~~~

Tên property canonical:

~~~text
demo.client.api-key
~~~

Tên file trong config tree:

~~~text
demo.client.api-key
~~~

Đó là tên rõ ràng nhất để test. Với tên nested directory:

~~~text
demo/client/api-key
~~~

cũng có thể sinh property phù hợp.

### 17.1. Không nhầm với OS environment variable

Nếu dùng biến môi trường, canonical `demo.client.api-key` thường tương ứng `DEMO_CLIENT_APIKEY`, theo quy tắc Boot dành cho OS environment variables.

Nhưng trong config tree, **tên file là property key** và có thể chứa dấu chấm/gạch nối. Đừng tạo file `DEMO_CLIENT_APIKEY` rồi nghĩ chắc chắn nó sẽ được diễn giải như OS environment property source. Hai nguồn có quy tắc khác nhau.

### 17.2. Filename có dots

Tài liệu Boot xác nhận file có tên dot notation như `myapp.username` được map sang cùng tên property. Đó là cơ sở cho pattern:

~~~text
demo.client.api-key
demo.client.password
~~~

### 17.3. Case sensitivity của filesystem

Linux và Windows có thể khác nhau về case sensitivity. Để test portable, dùng tên canonical lowercase, tránh hai file chỉ khác chữ hoa/chữ thường. Nếu test chạy song song nhiều OS, bảo đảm tên file không dựa trên behavior riêng của filesystem.

## 18. Các nguồn khác có thể ghi đè secret trong tree

Khi khởi động, một property có thể có mặt trong nhiều nguồn:

~~~text
classpath application.yml
external application.yml
configtree directory
OS environment
Java system properties
command line arguments
test-specific overrides
~~~

Spring Boot định nghĩa thứ tự ưu tiên nguồn. Thông thường, biến môi trường hoặc command-line options có thể ghi đè một key đến từ Config Data.

Ví dụ đã có file:

~~~text
demo.client.api-key -> FAKE_TEST_KEY_284
~~~

nhưng khởi động:

~~~bash
java -jar demo.jar \
  --spring.config.import=configtree:/tmp/demo-configtree/ \
  --demo.client.api-key=FAKE_OVERRIDE_284
~~~

Trong trường hợp Boot command-line property source được bật, value từ `--demo.client.api-key` có thể thắng và bean nhận `FAKE_OVERRIDE_284`.

### 18.1. Đừng test import bằng một source cao hơn

Nếu test có:

~~~java
@SpringBootTest(properties =
    "demo.client.api-key=FAKE_OVERRIDE_284")
~~~

và config tree cũng chứa key đó, assertion về `FAKE_OVERRIDE_284` **không chứng minh config tree được đọc**. Nguồn test-specific có thể che mất file source.

Để xác minh import, chọn một canary chỉ xuất hiện trong file, hoặc thêm marker property riêng không được cung cấp ở đâu khác.

### 18.2. Đừng dump toàn bộ Environment để tìm source thắng

`Environment` có thể chứa password/database URLs/token của cả ứng dụng. Chỉ xem tên nguồn và sự hiện diện của một key allowlisted. Với test giá trị giả, có thể assert exact value nhưng không đưa dữ liệu thật vào log.

### 18.3. Nếu cần kiểm thử precedence

Tạo một test **riêng**, có fake values khác nhau ở hai sources và assert source thắng theo tài liệu version của Boot. Đừng để một test vừa kiểm chứng import vừa kiểm chứng precedence mà không làm rõ mục đích.

## 19. Config tree wildcard cho nhiều volume

Spring Boot cho phép import nhiều configuration trees từ các thư mục con trực tiếp bằng wildcard:

~~~properties
spring.config.import=optional:configtree:/tmp/config/*/
~~~

Giả sử:

~~~text
/tmp/config/
├── database/
│   └── demo/
│       └── db/
│           ├── username
│           └── password
└── messaging/
    └── demo/
        └── mq/
            ├── username
            └── password
~~~

Import wildcard có thể tạo các properties:

~~~text
demo.db.username
demo.db.password
demo.mq.username
demo.mq.password
~~~

Directory con trong wildcard được xử lý theo thứ tự tên alphabetically theo quy tắc Boot. Nếu cần một precedence khác, chỉ định rõ từng location thay vì dựa vào thứ tự wildcard.

### 19.1. Wildcard chỉ lấy children trực tiếp

Cú pháp `*/` dùng để chọn các **immediate subdirectories**. Đừng giả định nó tự tìm mọi directory bất kể độ sâu. Cấu trúc file lồng nhau trong mỗi child có thể tạo nested property keys.

### 19.2. Không dùng wildcard khi muốn cấp riêng đúng một secret

Đọc toàn bộ directory lớn có thể vô tình đưa thêm các values không liên quan vào Environment. Với secret, thường nên mount và import **chỉ những locations ứng dụng cần**.

### 19.3. Không dựa vào wildcard để giải quyết collision

Nếu hai trees cùng định nghĩa `demo.client.api-key`, kết quả phụ thuộc precedence của imports. Một cách đặt tên tốt hơn là tách rõ prefix hoặc chỉ cho một source có quyền sở hữu key đó.

## 20. Áp dụng với Kubernetes Secret mount

Trong Kubernetes, Secret có thể được gắn vào container dưới dạng volume và project một key thành file có tên phù hợp.

Ví dụ một phần Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo-client
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo-client
  template:
    metadata:
      labels:
        app: demo-client
    spec:
      containers:
        - name: app
          image: registry.example.test/demo-client:1.0
          volumeMounts:
            - name: credentials
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: credentials
          secret:
            secretName: demo-client-credentials
            items:
              - key: api-key
                path: demo.client.api-key
~~~

Giả sử `Secret/demo-client-credentials` đã được cấp bởi một quy trình triển khai an toàn, key `api-key` được project thành file:

~~~text
/run/secrets/demo.client.api-key
~~~

Ứng dụng có Config Data:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Khi Boot khởi động, nó có thể bind `demo.client.api-key` vào record `DemoClientSecrets`.

**Không đưa Secret value thật vào manifest trong Git.** Nếu test yêu cầu một manifest, sử dụng giả lập hoặc namespace sandbox. Dữ liệu base64 trong Kubernetes Secret không phải phương thức mã hóa bí mật.

### 20.1. Mô phỏng volume bằng @TempDir

Mục tiêu chính của bài là làm mô phỏng filesystem ở local bằng `@TempDir`. Nhờ vậy, unit/integration test không cần quyền tạo Kubernetes Secret thật, không cần kubectl và không cần cluster production.

### 20.2. Secret mount và Config Tree là hai lớp riêng

Kubernetes chịu trách nhiệm cấp file vào container; Spring Boot chỉ đọc file và tạo configuration property. Nếu file không được mount, lỗi nằm ở runtime platform hoặc deployment; nếu file đã có nhưng Java bean không nhận, cần kiểm tra import root, filename, prefix và Binder.

### 20.3. Rotation không tự cập nhật mọi bean

Một Kubernetes Secret volume có thể được cập nhật theo cơ chế của platform, nhưng `@ConfigurationProperties` bean thông thường được bind lúc startup. Không tự suy rằng file mới đồng nghĩa client đang chạy đã dùng credential mới. Cần restart/redeploy hoặc cơ chế reload có chủ đích, được kiểm thử.

## 21. Áp dụng với Docker Compose secrets

Docker Compose có thể cấp file secret cho container.

Ví dụ:

~~~yaml
services:
  demo-client:
    image: registry.example.test/demo-client:1.0
    secrets:
      - source: demo_api_key
        target: demo.client.api-key

secrets:
  demo_api_key:
    file: ./local-fake-secrets/api-key.txt
~~~

Container thường nhận secret tại:

~~~text
/run/secrets/demo.client.api-key
~~~

Ứng dụng dùng:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Để chạy local, file ở `./local-fake-secrets/api-key.txt` chỉ chứa **fake token**. Không commit local secret thật hoặc copy nó vào Docker image.

### 21.1. Không nhầm Docker build với runtime secrets

Docker `ARG` và `ENV` không phải kênh an toàn để bake secret vào image. Runtime secret được cấp sau build, giảm số bản sao credential trong artifact và registry.

### 21.2. Một Docker image, nhiều môi trường

Image không chứa API key có thể dùng ở local/staging/production; mỗi deployment mount secret khác nhau. Đây là mục tiêu vận hành của Externalized Configuration, và bài test bằng `@TempDir` giúp kiểm tra phần Spring Boot mà không phụ thuộc secret backend.

## 22. So sánh env var, Config Data file và configtree

| Cách cấp | Dạng dữ liệu | Thời điểm | Khi phù hợp |
| --- | --- | --- | --- |
| `demo.client.api-key=...` trong application.yml | Value trong file cấu hình | Build hoặc runtime file | Chỉ dùng secret giả trong test; không nên đặt secret thật trong classpath |
| `DEMO_CLIENT_APIKEY=...` | Environment variable | Runtime process | Cấu hình đơn giản do platform inject |
| `configtree:/run/secrets/` | File-per-property | Boot Config Data | Mounted secret volumes |
| `file:/etc/app/secret.yml` | Một file YAML/properties tổng hợp | Boot Config Data | Platform cấp một config file |
| Secret manager integration | API/backend bên ngoài | Phụ thuộc integration | Quản lý version/rotation/audit |
| `@TestPropertySource(properties=...)` | Inline test key/value | TestContext | Chỉ test binding/override, không chứng minh configtree import |
| `ApplicationContextRunner.withPropertyValues(...)` | Inline runner values | Test runner | Test binding/validation nhỏ, không tự kiểm tra full Config Data |

Điểm quan trọng là xác định **mục tiêu bài test**. Nếu chỉ muốn test logic dùng API key, fake value inline có thể đủ. Nếu muốn học đúng cơ chế `configtree:`, cần tạo file và đi qua Config Data.

## 23. Tái hiện lỗi tên import root

Directory:

~~~text
/tmp/secrets/
└── demo/
    └── client/
        └── api-key
~~~

Sai nếu target cần `demo.client.api-key`:

~~~properties
spring.config.import=configtree:/tmp/secrets/demo/client/
~~~

Vì khi import quá sâu, key có thể chỉ là `api-key`.

Đúng:

~~~properties
spring.config.import=configtree:/tmp/secrets/
~~~

Hoặc đổi cấu trúc thành một file tên `demo.client.api-key` dưới root đã import.

### 23.1. Cách chẩn đoán

1. Xem chính xác import root.
2. Xem đường dẫn tương đối từ root đến file.
3. Xác định tên property hình thành.
4. So sánh với prefix trong `@ConfigurationProperties`.
5. Test trên một file giả, không cần đọc nội dung secret thật.

### 23.2. Không sửa bằng cách đổi Java field tùy tiện

Nếu property đúng theo contract là `demo.client.api-key`, đừng đổi record thành `@ConfigurationProperties(prefix = "")` chỉ để “nhận được”. Hãy sửa mount filename hoặc import root để thống nhất hợp đồng.

## 24. Tái hiện lỗi nội dung file không đúng

Một người tạo file:

~~~text
demo.client.api-key
~~~

và ghi:

~~~properties
demo.client.api-key=FAKE_TEST_KEY_284
~~~

Điều này **khác** với yêu cầu file chỉ chứa value:

~~~text
FAKE_TEST_KEY_284
~~~

Trong config tree, filename đã là key. Không lặp key/value syntax trong file.

### 24.1. Chẩn đoán bằng fake canary

Nếu test nhận một chuỗi bắt đầu bằng `demo.client.api-key=`, kiểm tra cách fixture được tạo. Test nên assert exact fake value để phát hiện.

### 24.2. Chẩn đoán newline

Nếu nhận `FAKE_TEST_KEY_284\n` thay vì `FAKE_TEST_KEY_284`, xem lệnh tạo file có dùng `echo` không. Sửa fixture theo hợp đồng thực; không âm thầm trim mọi secret trong production.

## 25. Test isolation và cleanup

Một bài test tốt không tạo dependency giữa các lượt chạy.

### 25.1. Mỗi test một directory riêng

`@TempDir` giúp mỗi test có directory tạm. Đừng dùng cố định `/tmp/app-secrets` khi nhiều CI jobs cùng chạy, vì test A có thể ghi đè dữ liệu của test B.

### 25.2. Khởi động context sau khi tạo file

Nếu Spring Boot đã xử lý Config Data trước khi test tạo file, context sẽ không tự load lại directory sau đó. Vì vậy các bước đúng là:

~~~text
Create @TempDir
   -> Write fake files
   -> Construct import location
   -> Run SpringApplication
   -> Assert values
   -> Close context
   -> Cleanup temp files
~~~

Không đổi thứ tự thành “run context rồi mới write fake file” mà vẫn mong `@ConfigurationProperties` tự cập nhật.

### 25.3. Đóng context sau test

`try (ConfigurableApplicationContext ... )` giúp đóng context. Điều này quan trọng nếu application context có resources hoặc background threads. JUnit có thể dọn `@TempDir` khi test hoàn tất.

### 25.4. Không ghi temp file vào source repo

Một số test dùng `src/test/resources/secrets`; nếu chỉ có fake values thì có thể chấp nhận, nhưng các file này vẫn nằm trong Git và test classpath. Temp directory làm rõ mô hình file runtime và giảm nguy cơ accidentally ship credential.

### 25.5. Test chạy song song

Mỗi test nên có unique directory và unique context. Tránh static global system properties chứa `spring.config.import` vì có thể ảnh hưởng test khác trong cùng JVM. Dùng bootstrap per-test để cấp import location.

## 26. Bảo mật logs và assertion

Fake data là vô hại, nhưng nên luyện **thói quen an toàn tương tự production**.

### 26.1. Không in toàn bộ Environment

Sai:

~~~java
environment.getPropertySources()
        .forEach(source -> log.info("{}", source));
~~~

Một số PropertySource hoặc diagnostic có thể chứa thông tin nhạy cảm. Chỉ kiểm tra từng key được phép trong test, dùng assertions thay vì dump toàn environment.

### 26.2. Không log nguyên configuration record

Sai:

~~~java
log.info("Secrets: {}", credentials);
~~~

Record có thể in `apiKey` và `password` qua `toString()`. Một test nhận fake values có thể không nguy hiểm, nhưng code này sẽ nguy hiểm nếu bị sao chép vào runtime.

### 26.3. Test lỗi startup cũng cần canary

Khi Binder/conversion/validation thất bại, framework có thể đưa rejected value vào exception message. Nếu có test cho secret thật, không nên sử dụng raw exception output. Dùng fake canary và xác minh pipeline logs nếu bảo mật là mục tiêu của bài.

### 26.4. Không đưa raw secret vào metric hoặc trace

Đừng tạo attribute kiểu `config.value=FAKE_TEST_KEY_284` trong test với ý định về sau thay bằng token thật. Dùng error code, component, type hoặc trạng thái.

### 26.5. Test secret phải thật sự giả

Không lấy token sandbox có quyền gọi dịch vụ thật và gọi nó là “fake”. Một fake value như `FAKE_TEST_KEY_284` không được hệ thống bên ngoài công nhận mới là dữ liệu giả thực sự.

## 27. Khác biệt giữa secret store và configtree

Có ba vấn đề độc lập:

1. **Lưu trữ và cấp quyền:** secret manager, Kubernetes Secret, Docker secret hoặc hệ thống nội bộ quyết định ai được đọc.
2. **Phân phối tới runtime:** environment injection, mounted volume, sidecar, CSI driver hoặc API client.
3. **Nạp vào Spring Boot:** `configtree:`, file Config Data, env vars hoặc custom integration.

`configtree:` chỉ giải quyết lớp **thứ ba** nếu dữ liệu đã sẵn trên filesystem.

### 27.1. Không giả định Kubernetes Secret luôn được mã hóa

Base64 encoding của `Secret.data` không phải encryption. Quyền đọc API, quyền mount volume và encryption at rest cần được cấu hình ở nền tảng.

### 27.2. Không giả định file read-only nghĩa là an toàn tuyệt đối

Một container có quyền đọc file vẫn có thể vô tình log nội dung. Read-only volume ngăn sửa qua mount nhưng không ngăn code có quyền đọc secret.

### 27.3. Không dùng random.value thay secret manager

Spring Boot có random property source tiện cho một số giá trị test, nhưng nó không cung cấp đầy đủ lifecycle, rotation, backup và quản trị của một signing/encryption key production.

## 28. Kịch bản kiểm thử acceptance

Một bộ bài test nên gồm những trường hợp sau:

| ID | Dữ liệu fixture | Điều cần kiểm tra |
| --- | --- | --- |
| CT-01 | Ba file fake, đúng tên | Bean nhận đúng ba values |
| CT-02 | Chỉ file api-key | Property đó có mặt; các field khác thiếu nếu không có default |
| CT-03 | Root import quá sâu | Prefix dự kiến không nhận property |
| CT-04 | File tên dot notation | Tên property khớp |
| CT-05 | Cây nested demo/client/api-key | Cùng semantic với dot-name |
| CT-06 | Directory bắt buộc không tồn tại | Bootstrap failure |
| CT-07 | Directory optional không tồn tại | Config Data bỏ qua missing location |
| CT-08 | Directory có, thiếu api-key | Validation/required check từ chối khi bắt buộc |
| CT-09 | File rỗng | Non-blank validation thất bại khi bật |
| CT-10 | File có trailing newline | Assert chính sách xử lý chính xác |
| CT-11 | Byte file | Bind đúng `byte[]` |
| CT-12 | CLI fake override | Hiểu precedence, test riêng |
| CT-13 | Hai cây wildcard | Nhận đủ keys, không collision |
| CT-14 | Test chạy đồng thời | Không dùng chung temp directory |
| CT-15 | Không secret ở source/artifact | Kiểm tra pipeline phù hợp |
| CT-16 | Context khởi động sau khi file tạo | Import thực sự được chạy |

Mỗi case có một mục tiêu rõ. Không cần chạy tất cả trong một `@SpringBootTest` khổng lồ.

### 28.1. Khi nào assert context failure?

Nếu đang test missing directory, hãy assert lỗi Config Data từ bootstrap. Nếu đang test missing key, hãy assert validation failure hoặc required-property check. Hai kiểu lỗi khác nhau, đừng chỉ có một assertion “context không khởi động” rồi coi chúng tương đương.

### 28.2. Test hậu quả của sai prefix

Khi import location trỏ vào `.../demo/client/`, key có thể là `api-key`. Để chứng minh nguyên nhân, assert presence của `api-key` và absence của `demo.client.api-key` trong một context không bắt buộc bean đó, rồi sửa root.

## 29. Một ví dụ command-line để tự kiểm chứng

Với project Spring Boot đã có `DemoClientSecrets` và đăng ký bean:

~~~bash
mkdir -p /tmp/demo-secret-fixture

printf '%s' 'FAKE_TEST_KEY_284' \
  > /tmp/demo-secret-fixture/demo.client.api-key

printf '%s' 'demo-user' \
  > /tmp/demo-secret-fixture/demo.client.username

printf '%s' 'FAKE_TEST_PASSWORD_284' \
  > /tmp/demo-secret-fixture/demo.client.password

java -jar target/demo-app.jar \
  --spring.config.import=configtree:/tmp/demo-secret-fixture/
~~~

Ví dụ này chỉ minh họa cách khởi động; tên JAR và entrypoint cần đúng project thực tế. Đừng sửa code ứng dụng để log credential. Có thể tạo một test-only bean kiểm tra sự hiện diện hoặc dùng JUnit assertions ở phần trước.

### 29.1. Windows PowerShell

Trong PowerShell, có thể tạo directory và file bằng lệnh phù hợp. Ví dụ:

~~~powershell
$root = Join-Path $env:TEMP "demo-configtree-fixture"
New-Item -ItemType Directory -Force -Path $root | Out-Null

[System.IO.File]::WriteAllText(
    (Join-Path $root "demo.client.api-key"),
    "FAKE_TEST_KEY_284"
)
~~~

Việc tạo file bằng .NET `WriteAllText` trong ví dụ không tự thêm newline. Cần truyền root path vào Config Data import dưới định dạng location mà Spring Boot version và hệ điều hành xử lý đúng. Với automated tests đa nền tảng, ưu tiên Java NIO/`@TempDir` để giảm phụ thuộc shell.

### 29.2. Dọn file sau thử nghiệm thủ công

Khi xong, chỉ xóa **đúng directory fixture** đã tạo. Không dùng một lệnh recursive delete dựa trên biến chưa kiểm tra. Test `@TempDir` được quản lý tự động thường an toàn hơn thao tác thủ công.

## 30. Những lỗi thường gặp

### 30.1. Import một file thay vì directory tree

~~~properties
spring.config.import=configtree:/tmp/secrets/application.properties
~~~

không đúng mục tiêu khi đang muốn parse một file properties tổng hợp. Dùng `file:` với file hoặc chuyển sang per-file tree.

### 30.2. Nội dung file chứa lại key=value

Trong config tree, filename đã là key. Nội dung file phải là value.

### 30.3. Import root quá sâu

Nếu prefix `demo.client` nằm trong folder tree bên trên root, property không còn đầy đủ prefix. Chọn root đúng.

### 30.4. Dùng optional nhưng không validate

`optional:` chỉ xử lý missing location, không tự đảm bảo field bắt buộc tồn tại. Dùng validation.

### 30.5. Dùng @TestPropertySource để mong configtree import chạy

`@TestPropertySource` đưa giá trị vào test Environment theo cơ chế TestContext; không nên coi nó là cách tự động kiểm tra toàn bộ early Config Data import. Khởi động Boot sau khi tạo directory và assert marker.

### 30.6. Tạo file sau khi context đã khởi động

Bean đã bind không tự được làm mới. Tạo file trước khi gọi `run()`.

### 30.7. Test pass do một override khác

Nếu một inline test property có cùng key, nó có thể che config tree. Dùng fake canary chỉ tồn tại ở file hoặc kiểm tra một marker.

### 30.8. Ghi file bằng echo và thêm newline

Một số clients xem newline là một phần credential. Sử dụng `printf '%s'` hoặc `Files.writeString` với chuỗi chính xác.

### 30.9. Lấy credential thật vào test fixture

Dùng dữ liệu giả không có quyền truy cập thật. Một token sandbox còn hiệu lực vẫn phải được đối xử như credential nhạy cảm.

### 30.10. Đưa secret vào Git để test tiện hơn

Nếu project cần dữ liệu thật cho một integration environment, cấp qua runtime secret store/CI phù hợp; không commit credential vào `src/test/resources`.

### 30.11. Quên đóng application context

Một context có thể giữ resource, thread hoặc port. Dùng try-with-resources và dọn temp directory.

### 30.12. Chỉ kiểm tra Environment mà không kiểm tra bean

Property có mặt không đảm bảo prefix, binding hoặc validation đúng. Assert cả property marker và bean values.

### 30.13. Nhầm filename với OS environment name

`demo.client.api-key` là tên file canonical; `DEMO_CLIENT_APIKEY` là dạng biến OS environment. Đừng coi hai nguồn có cùng cú pháp tên.

### 30.14. Dùng wildcard không kiểm soát nhiều secret

Wildcard có thể import nhiều trees hơn cần thiết và tạo collision/precedence khó hiểu. Chỉ mount/import những dữ liệu ứng dụng cần.

### 30.15. Nghĩ configtree mã hóa dữ liệu

Config tree chỉ đọc file. Bảo mật volume thuộc về nền tảng và quyền runtime.

## 31. Checklist trước khi kết thúc bài thực hành

- [ ] Dùng Spring Boot có hỗ trợ Config Data và `configtree:`.
- [ ] Dùng 100% fake token/password, không có credential thật.
- [ ] Temporary directory được tạo riêng cho test.
- [ ] File được tạo **trước** khi khởi động context.
- [ ] Filename khớp canonical property name.
- [ ] Nội dung file chỉ có value, không ghi thêm `key=value`.
- [ ] Import location dùng `configtree:<directory>/` và đúng root.
- [ ] Không dùng đường dẫn classpath khi mục tiêu là mô phỏng mounted secret.
- [ ] `@ConfigurationProperties` bean được đăng ký đúng.
- [ ] Java target type phù hợp `String` hoặc `byte[]`.
- [ ] Assertions kiểm tra chính xác fake values.
- [ ] Marker property có thể chứng minh import thực sự chạy.
- [ ] Missing directory được kiểm tra riêng missing property.
- [ ] Có validation nếu credential bắt buộc.
- [ ] Test optional import không che lỗi thiếu secret.
- [ ] Không có source ưu tiên cao hơn vô tình override fake value.
- [ ] Test không in object cấu hình hoặc Environment ra log.
- [ ] Không có file fake/real được copy nhầm vào production JAR.
- [ ] Context được đóng; temp files được dọn.
- [ ] Test chạy độc lập giữa nhiều JVM/CI jobs.
- [ ] Có thể giải thích khác biệt giữa config tree, YAML import và secret manager.
- [ ] Có kế hoạch reload/restart khi secret runtime đổi.

## 32. Bài tập mở rộng

### Bài A — Dot filename và nested directories

Tạo hai fixture riêng:

~~~text
fixture-one/demo.client.api-key
fixture-two/demo/client/api-key
~~~

Import mỗi root và assert đều tạo property `demo.client.api-key`. Không cùng lúc tạo hai key trùng nhau trong một tree nếu bạn chưa định nghĩa precedence.

### Bài B — Optional directory

Với directory không tồn tại, so sánh:

~~~properties
spring.config.import=configtree:/not-found/
~~~

và:

~~~properties
spring.config.import=optional:configtree:/not-found/
~~~

Giải thích tại sao một trường hợp có thể fail ở Config Data bootstrap, còn trường hợp kia có thể tiếp tục nhưng vẫn thiếu credential.

### Bài C — Validation

Thêm `@Validated` và `@NotBlank` vào record. Tạo fixture thiếu `demo.client.api-key`. Assert context khởi động thất bại vì required property. Không đưa password vào thông điệp lỗi.

### Bài D — Newline

Tạo một file bằng `Files.writeString(path, "FAKE_TEST_KEY_284\n")` và một file không newline. So sánh value mà Binder cung cấp, sau đó xác định contract mà ứng dụng thật cần.

### Bài E — Precedence

Tạo file chứa `FAKE_FILE_KEY`. Khởi động test với một command-line property fake khác cho cùng key. Assert giá trị hiệu lực trong Boot context và giải thích tại sao test này phải tách khỏi test import thuần.

### Bài F — Binary

Tạo bốn bytes giả, bind sang `byte[]` và assert exact bytes. Tránh chuyển nội dung sang String để log.

### Bài G — Wildcard

Tạo:

~~~text
config/dbsource/demo/db/password
config/mqsource/demo/mq/password
~~~

Import `configtree:<root>/*/` và assert có cả `demo.db.password` và `demo.mq.password`. Giải thích thứ tự alphabetically và rủi ro key trùng.

## 33. Kết luận

Bài thực hành **“Nạp bí mật thử nghiệm từ configtree: với dữ liệu giả lập”** minh họa một cách dùng quan trọng của Spring Boot Externalized Configuration: **tách giá trị nhạy cảm khỏi JAR/source code** bằng cách đọc các file được cấp từ môi trường runtime.

Quy trình cốt lõi:

1. Tạo directory tạm với mỗi file là **một property name**.
2. Ghi dữ liệu **giả** vào từng file, không ghi thêm cú pháp `key=value`.
3. Dùng `spring.config.import=configtree:<directory>/` trong đúng giai đoạn Boot Config Data.
4. Khởi động context **sau khi** file tồn tại.
5. Bind vào `@ConfigurationProperties`, assert chính xác values và marker.
6. Kiểm thử missing directory, missing key, empty file, newline và precedence riêng biệt.
7. Dọn tài nguyên, không log raw secrets và không đưa credential thật vào test/artifact.

Cần nhớ rằng **`configtree:` là cơ chế nạp dữ liệu**, không phải vault, encryption engine hay hot-reload system. Spring Boot chịu trách nhiệm chuyển file thành properties; nền tảng triển khai chịu trách nhiệm cấp và bảo vệ secret. Viết test bằng `@TempDir` và fake canary giúp xác nhận ranh giới này mà không cần truy cập Kubernetes cluster hoặc credential production.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Using Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing-configuration-trees)
- [Spring Boot Reference — Importing Additional Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot API — SpringApplicationBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [JUnit Jupiter — @TempDir](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory)
- [Kubernetes Documentation — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Docker Documentation — Manage Secrets](https://docs.docker.com/engine/swarm/secrets/)
