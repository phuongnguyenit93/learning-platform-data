# Import nhiều cây cấu hình và lựa chọn kiểu `String` hoặc `byte[]` trong Spring Boot

## 1. Mục tiêu bài học

Ứng dụng Spring Boot khi chạy trong container hoặc nền tảng như Kubernetes thường không nhận toàn bộ cấu hình dưới dạng một file `application.yaml`. Nền tảng có thể mount nhiều thư mục, mỗi thư mục chứa các file nhỏ: tên file biểu diễn khóa cấu hình, nội dung file biểu diễn giá trị. Spring Boot gọi cách tổ chức này là **configuration tree** (cây cấu hình).

Bài này hướng dẫn dùng `spring.config.import` với tiền tố `configtree:` để nhập **nhiều cây cấu hình**, dùng wildcard để tìm nhiều thư mục con và chọn kiểu dữ liệu **`String` hoặc `byte[]`** khi đọc giá trị. Cùng một ví dụ thực hành sẽ giúp bạn quan sát trường hợp dữ liệu văn bản và dữ liệu nhị phân được mount từ bên ngoài ứng dụng.

Sau khi học, bạn có thể:

- Phân biệt nhập một file `.properties`/`.yaml` với nhập một cây các file cấu hình.
- Giải thích đường dẫn trong cây biến thành tên property như thế nào.
- Nhập nhiều cây bằng `configtree:/path/*/` hoặc liệt kê nhiều import tường minh.
- Hiểu thứ tự xử lý khi các cây cung cấp cùng một khóa và cách chủ động kiểm soát ưu tiên.
- Đọc giá trị văn bản dưới dạng `String`, dữ liệu nhị phân dưới dạng `byte[]` trong `Environment` hoặc `@ConfigurationProperties`.
- Chạy một chương trình Spring Boot Java 21/Gradle sử dụng file ngoài JAR, thử nghiệm thay đổi cây, xem kết quả rồi xác định nguyên nhân khi cấu hình sai.
- Nhận biết ranh giới bảo mật khi cây cấu hình được dùng để mount Kubernetes Secrets, Docker secrets hoặc chứng chỉ.

**Ngữ cảnh:** Spring Boot 3.3.x và cơ chế Config Data của Spring Boot 2.4+. Các đường dẫn trong bài lab đều là đường dẫn giả lập, dùng giá trị không nhạy cảm. Phần hướng dẫn không yêu cầu có cụm Kubernetes để chạy thử.

## 2. Một file cấu hình và một cây cấu hình khác nhau ra sao?

Với cách quen thuộc, bạn có thể có một file:

```yaml
# application.yaml
payment:
  host: payment.internal
  port: 8443
```

Spring Boot đọc YAML và chuyển thành các thuộc tính như `payment.host`, `payment.port`.

Trong **configuration tree**, cùng dữ liệu có thể nằm trong hai file:

```text
/etc/config/payment/
├── host      (nội dung: payment.internal)
└── port      (nội dung: 8443)
```

Để đọc các file này thành properties, cần khai báo:

```properties
spring.config.import=optional:configtree:/etc/config/
```

Lúc đó đường dẫn tương đối so với thư mục gốc được import trở thành khóa:

```text
/etc/config/payment/host --> payment.host
/etc/config/payment/port --> payment.port
```

Nếu thay location bằng:

```properties
spring.config.import=optional:configtree:/etc/config/payment/
```

thì những file `host` và `port` nằm ngay dưới gốc import; tên property thu được là `host` và `port`.

Điểm cốt lõi:

- **File đơn:** một file hoàn chỉnh chứa nhiều khóa, dùng `file:` hoặc location phù hợp với định dạng file; ví dụ `optional:file:/etc/config/application.yaml`.
- **Config tree:** một thư mục chứa nhiều file; **đường dẫn/tên file** tạo khóa và **nội dung file** tạo giá trị; ví dụ `optional:configtree:/etc/config/`.
- File trong config tree **không cần** đuôi `.properties`, `.yaml`, `.txt`. Một file tên `payment.host` cũng có thể tạo property `payment.host`.
- Đặt `configtree:` trước đường dẫn giúp Spring Boot hiểu rằng phải đọc cây file theo quy tắc này; chỉ đặt một thư mục cạnh JAR không tự làm nó trở thành config tree.

Trường hợp điển hình là Kubernetes ConfigMap/Secret được mount thành một file cho mỗi key; Docker secrets cũng có thể được mount tương tự. Một ứng dụng còn có thể kết hợp config tree với cấu hình mặc định bên trong JAR, biến môi trường và đối số CLI.

## 3. `spring.config.import` nhập config tree như thế nào?

`spring.config.import` xuất hiện trong một tài liệu cấu hình đã được Spring Boot nạp, chẳng hạn `src/main/resources/application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
```

Ở đây:

- `spring.config.import` yêu cầu nạp thêm Config Data.
- `configtree:` là loại nguồn, thông báo rằng location là **cây thư mục**.
- `/etc/config/` là gốc cây file.
- `optional:` cho phép ứng dụng tiếp tục khởi động nếu location không có; bỏ `optional:` khi cây cấu hình là điều kiện bắt buộc.
- Những giá trị được import có thể ghi đè thuộc tính trùng tên trong tài liệu khai báo import. Khi nhiều nguồn tham gia, phải xét thứ tự Config Data và các PropertySource khác để biết giá trị hiệu lực.

Ví dụ, nếu `application.yaml` có:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
demo:
  title: packaged-default
```

và `/etc/config/demo/title` chứa `mounted-title`, giá trị `demo.title` đọc từ `Environment` có thể là `mounted-title`. Các khóa không trùng tên trong `application.yaml` vẫn còn được sử dụng.

Điểm khác với `spring.config.location` hoặc `spring.config.additional-location` là `spring.config.import` khai báo một **nguồn bổ sung ngay trong một tài liệu cấu hình được nạp**, phù hợp khi ứng dụng biết rõ thư mục cần import. Với một file YAML không có đuôi nhưng được mount từ nền tảng, đó vẫn là **file đơn**, nên cần cú pháp import file và extension hint thích hợp; đừng dùng `configtree:` chỉ vì tên file không có đuôi.

## 4. Nhập nhiều cây dưới cùng một thư mục cha

Giả sử nền tảng mount hai nhóm cấu hình độc lập:

```text
/etc/config/
├── dbconfig/
│   └── db/
│       ├── host
│       └── username
└── mqconfig/
    └── mq/
        ├── host
        └── username
```

Mỗi file có một giá trị; ví dụ `dbconfig/db/host` chứa `db.internal` và `mqconfig/mq/host` chứa `mq.internal`.

Bạn có thể khai báo:

```properties
spring.config.import=optional:configtree:/etc/config/*/
```

Hoặc YAML:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/*/"
```

Wildcard `*/` mở rộng **các thư mục con trực tiếp** của `/etc/config/`. Spring Boot nhập từng thư mục con như một cây riêng. Vì gốc của mỗi import là `dbconfig/` hoặc `mqconfig/`, các key thu được là:

| File gốc | Property trong `Environment` | Giá trị minh họa |
| --- | --- | --- |
| `dbconfig/db/host` | `db.host` | `db.internal` |
| `dbconfig/db/username` | `db.username` | `reader` |
| `mqconfig/mq/host` | `mq.host` | `mq.internal` |
| `mqconfig/mq/username` | `mq.username` | `consumer` |

**Sự khác biệt cần nhớ:** nếu bạn import trực tiếp `configtree:/etc/config/` mà không có wildcard, các thư mục `dbconfig` và `mqconfig` nằm **bên dưới gốc cây**, vì vậy tên khóa có thể mang thêm những đoạn đường dẫn này, chẳng hạn `dbconfig.db.host`. Với `configtree:/etc/config/*/`, mỗi thư mục con trực tiếp là một gốc riêng, nên property là `db.host`, `mq.host`.

Wildcard không phải quét vô hạn tất cả thư mục con để coi chúng là các gốc riêng. Nó chỉ mở rộng một cấp thư mục ngay bên dưới cha. Tuy nhiên, sau khi tìm được một gốc config tree, các file nằm sâu hơn **bên trong chính cây đó** vẫn tạo property theo những đoạn đường dẫn tương ứng. Đây là hai việc khác nhau: **mở rộng danh sách gốc** và **đọc các file bên trong mỗi gốc**.

### 4.1. Thứ tự khi dùng wildcard

Các thư mục được wildcard mở rộng được sắp xếp **theo thứ tự chữ cái của đường dẫn tuyệt đối**. Ví dụ:

```text
/etc/config/
├── 10-common/
├── 20-service/
└── 30-overrides/
```

Nếu nhiều cây cùng khai báo một khóa, thứ tự import có thể quyết định nguồn nào được ưu tiên; với những import được xử lý sau, giá trị trùng khóa có thể ghi đè nguồn trước đó. Đừng xây logic quan trọng dựa trên tên thư mục bất ngờ do một hệ thống bên ngoài tạo ra.

Cách an toàn nhất là dùng khóa tách namespace như `db.*`, `mq.*`, `smtp.*` để các cây không cần tranh nhau cùng khóa. Nếu cố ý muốn một cây ghi đè cây khác, hãy khai báo vị trí rõ ràng và thử nghiệm với dữ liệu giả lập.

### 4.2. Liệt kê nhiều cây tường minh

Khi cần thứ tự có chủ đích, bạn có thể viết:

```yaml
spring:
  config:
    import:
      - "optional:configtree:/etc/config/common/"
      - "optional:configtree:/etc/config/service/"
      - "optional:configtree:/etc/config/overrides/"
```

Các import trong một danh sách được xử lý theo thứ tự khai báo; **import sau có độ ưu tiên cao hơn import trước** khi cùng cung cấp một khóa ở cùng cơ chế này. Bằng cách liệt kê, bạn kiểm soát được thứ tự mà không phải dựa vào tên thư mục wildcard.

Một nguồn có thể được khai báo lặp nhưng Config Data chỉ import một lần theo quy tắc Spring Boot. Cũng không nên dùng cùng một cây vừa qua wildcard vừa qua danh sách tường minh nếu không có lý do rõ ràng; ví dụ học này chọn một trong hai cách cho mỗi lần chạy.

## 5. Vì sao cần chọn kiểu `String` hoặc `byte[]`?

Trong configuration tree, nội dung file có thể là:

- **Văn bản:** URL, hostname, username giả lập, nhãn môi trường, chuỗi cấu hình hoặc giá trị mà thư viện mong đợi ở dạng text.
- **Dữ liệu nhị phân:** bytes của một key, certificate/key blob, file nhị phân hoặc payload mà thành phần tiêu thụ mong đợi dưới dạng byte nguyên trạng.

Spring Boot cho phép binding giá trị configuration tree vào cả `String` và `byte[]`, tùy loại dữ liệu bạn mong đợi.

| Trường hợp | Kiểu nên chọn | Lý do |
| --- | --- | --- |
| Hostname `db.internal` | `String` | Giá trị là text |
| Nhãn `welcome-from-tree` | `String` | Ứng dụng cần hiển thị hoặc so sánh chuỗi |
| Payload `[0, 1, 127, 255]` | `byte[]` | Có byte không thể giả định là ký tự UTF-8 hợp lệ |
| Khối dữ liệu mã hóa hoặc key nhị phân | `byte[]` | Tránh chuyển đổi qua charset gây thay đổi dữ liệu |
| PEM text cần thư viện đọc chuỗi | `String` hoặc `byte[]` theo API tiêu thụ | Cần rõ encoding, định dạng và hợp đồng dữ liệu |

**Không dùng `new String(bytes)` mà bỏ charset** để xử lý file nhị phân. Nếu dữ liệu được xác định là UTF-8 text, chuyển đổi tường minh bằng `new String(bytes, StandardCharsets.UTF_8)` khi thực sự cần. Nếu đó là bytes thuần, giữ `byte[]`, không cố hiển thị chúng như chuỗi.

Một cảnh báo khác: shell `echo` thường thêm ký tự xuống dòng vào cuối file. Trong config tree, nội dung file là giá trị nên ký tự newline ngoài ý muốn có thể ảnh hưởng đến chuỗi hoặc bytes được đọc. Khi thử nghiệm dữ liệu nhị phân, dùng thao tác ghi bytes rõ ràng; khi thử text, dùng lệnh không tự thêm newline.

Dù có thể bind key bảo mật thành `String`, một `String` là immutable và không thể xóa byte nhạy cảm khỏi bộ nhớ theo ý muốn. Với API nhận bytes và yêu cầu giữ dữ liệu nguyên trạng, `byte[]` là lựa chọn phù hợp hơn. Lựa chọn kiểu dữ liệu không thay thế việc kiểm soát quyền đọc file, secret lifecycle và chính sách không ghi log bí mật.

## 6. Ứng dụng mẫu: Multi Config Tree Observer

Ta sẽ tạo một ứng dụng Spring Boot console để **quan sát nhiều cây cùng lúc**. Ứng dụng nhận hai loại dữ liệu:

1. `demo.welcome`: chuỗi text để in ra màn hình.
2. `demo.payload`: bốn byte nhị phân thử nghiệm, chương trình chỉ hiển thị độ dài, không in nội dung.
3. `db.host` và `mq.host`: chuỗi từ hai cây khác nhau để chứng minh import wildcard tạo các namespace riêng.

Cấu trúc dự án:

```text
multi-config-tree/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── src/main/java/dev/example/tree/
│   ├── MultiConfigTreeApplication.java
│   └── DemoProperties.java
├── src/main/resources/
│   └── application.yaml
└── run/
    └── trees/
        ├── 10-app/
        │   └── demo/
        │       └── welcome
        ├── 20-binary/
        │   └── demo/
        │       └── payload
        ├── 30-db/
        │   └── db/
        │       └── host
        └── 40-mq/
            └── mq/
                └── host
```

Đường dẫn `run/trees` nằm ngoài `src/main/resources`, vì vậy các giá trị file không được đóng gói vào JAR. Nó mô phỏng mount ngoài container. Các file có tên `welcome`, `payload`, `host` **không cần phần mở rộng**.

### 6.1. Gradle và Java 21

`settings.gradle`:

```groovy
rootProject.name = 'multi-config-tree'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng Gradle Wrapper từ một project Gradle Spring Boot đã khởi tạo, hoặc tạo bộ khung tương ứng qua Spring Initializr. Nếu bài được làm trong một repository có convention và version catalog riêng, giữ nguyên quy ước dependency của repository thay vì tạo thêm cơ chế quản lý phiên bản.

### 6.2. Khai báo import

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none
  config:
    import: "optional:configtree:./run/trees/*/"

demo:
  welcome: fallback-from-jar
```

Ứng dụng chạy không mở web server. `demo.welcome` có giá trị nền bên trong JAR khi không tìm thấy các cây. Cấu hình `optional:` cho phép chạy trong trường hợp thư mục lab chưa tồn tại, rất tiện để so sánh trước và sau khi tạo file.

Ở thí nghiệm này, ta chạy từ **thư mục gốc project**, nên đường dẫn tương đối `./run/trees/` trỏ tới thư mục đã vẽ trong sơ đồ. Nếu chuyển working directory, phải tính lại đường dẫn; file ở `./run/trees` không tự đi theo vị trí file JAR.

### 6.3. Binding có kiểu với `@ConfigurationProperties`

`src/main/java/dev/example/tree/DemoProperties.java`:

```java
package dev.example.tree;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String welcome,
        byte[] payload
) {}
```

Property `demo.welcome` đến từ nội dung file `10-app/demo/welcome`; `demo.payload` đến từ nội dung file `20-binary/demo/payload`. Prefix `demo` được binding vào record Java. Trường `byte[]` giữ kiểu dữ liệu dự kiến của payload nhị phân.

### 6.4. Dùng `Environment` và bean đã binding

`src/main/java/dev/example/tree/MultiConfigTreeApplication.java`:

```java
package dev.example.tree;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MultiConfigTreeApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiConfigTreeApplication.class, args);
    }

    @Bean
    ApplicationRunner observe(
            ConfigurableEnvironment environment,
            DemoProperties demo) {
        return args -> {
            String welcome =
                    environment.getProperty("demo.welcome", String.class);
            byte[] payload =
                    environment.getProperty("demo.payload", byte[].class);

            System.out.println("=== MULTI CONFIG TREE ===");
            System.out.println("workingDir = "
                    + System.getProperty("user.dir"));
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("demo.welcome (String) = " + welcome);
            System.out.println("demo.welcome bound = " + demo.welcome());
            System.out.println("demo.payload (byte[]) length = "
                    + lengthOrMissing(payload));
            System.out.println("demo.payload bound length = "
                    + lengthOrMissing(demo.payload()));

            System.out.println("db.host = "
                    + environment.getProperty("db.host", "<missing>"));
            System.out.println("mq.host = "
                    + environment.getProperty("mq.host", "<missing>"));

            System.out.println("Sources containing demo.welcome:");
            for (PropertySource<?> source
                    : environment.getPropertySources()) {
                if ("configurationProperties".equals(source.getName())) {
                    continue;
                }
                if (source.getProperty("demo.welcome") != null) {
                    System.out.println(" - " + source.getName());
                }
            }
        };
    }

    private static String lengthOrMissing(byte[] bytes) {
        return bytes == null ? "<missing>"
                : Integer.toString(bytes.length);
    }
}
```

Chương trình cố ý chỉ in độ dài của bytes. Trong bài lab payload là dữ liệu giả, nhưng khi áp dụng cho secret thật, không nên in raw bytes, hex, base64 hoặc nội dung key ra log.

`environment.getProperty("demo.welcome", String.class)` yêu cầu giá trị được biểu diễn như text; `environment.getProperty("demo.payload", byte[].class)` yêu cầu byte array. `@ConfigurationProperties` thể hiện cách binding cùng tập khóa vào một kiểu Java có cấu trúc.

Lưu ý: hiển thị tên `PropertySource` phục vụ quan sát trong bài học. Tên chi tiết có thể phụ thuộc cách chạy và phiên bản; công cụ này không phải bộ chứng minh nguồn gốc đầy đủ cho mọi kiểu binding hoặc placeholder.

## 7. Chuẩn bị bốn cây dữ liệu

### 7.1. Trên Linux hoặc macOS dùng Bash

Đứng ở thư mục gốc `multi-config-tree`:

```bash
mkdir -p run/trees/10-app/demo
mkdir -p run/trees/20-binary/demo
mkdir -p run/trees/30-db/db
mkdir -p run/trees/40-mq/mq

printf '%s' 'welcome-from-tree' > run/trees/10-app/demo/welcome
printf '\x00\x01\x7f\xff' > run/trees/20-binary/demo/payload
printf '%s' 'db.lab.internal' > run/trees/30-db/db/host
printf '%s' 'mq.lab.internal' > run/trees/40-mq/mq/host
```

Ví dụ dùng `printf` trong Bash để tạo payload gồm bốn byte `00 01 7F FF`. Cách viết `\x` phụ thuộc shell nên ví dụ nêu rõ Bash; không nên giả định mọi trình thông dịch `/bin/sh` đều diễn giải giống nhau.

### 7.2. Trên Windows PowerShell

Đứng ở thư mục gốc `multi-config-tree`:

```powershell
New-Item -ItemType Directory -Force 'run/trees/10-app/demo' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/20-binary/demo' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/30-db/db' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/40-mq/mq' | Out-Null

Set-Content -NoNewline -Encoding UTF8 'run/trees/10-app/demo/welcome' 'welcome-from-tree'
Set-Content -NoNewline -Encoding UTF8 'run/trees/30-db/db/host' 'db.lab.internal'
Set-Content -NoNewline -Encoding UTF8 'run/trees/40-mq/mq/host' 'mq.lab.internal'

$binaryPath = Join-Path (Get-Location) 'run/trees/20-binary/demo/payload'
[System.IO.File]::WriteAllBytes($binaryPath, [byte[]](0, 1, 127, 255))
```

`WriteAllBytes` giúp lưu chính xác bốn byte mà không phụ thuộc quy tắc encoding hay newline của lệnh ghi văn bản.

Với file text chỉ chứa ASCII trong bài lab, các công cụ ghi UTF-8 là phù hợp. Khi xử lý dữ liệu thực tế, xác định rõ encoding của file trước khi quyết định dùng `String` hoặc `byte[]`.

## 8. Chạy thử và quan sát

### 8.1. Chạy khi chưa có các cây

Để xem giá trị nền, tạm đổi tên thư mục `run/trees` hoặc chạy trên bản làm việc chưa tạo các file ở mục 7.

macOS/Linux:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Kỳ vọng chính:

```text
demo.welcome (String) = fallback-from-jar
demo.payload (byte[]) length = <missing>
db.host = <missing>
mq.host = <missing>
```

Ứng dụng vẫn khởi động vì import có `optional:`.

### 8.2. Chạy sau khi tạo các cây

Sau khi đã tạo đủ bốn cây, chạy `bootRun` từ thư mục gốc project. Kết quả minh họa:

```text
=== MULTI CONFIG TREE ===
workingDir = .../multi-config-tree
activeProfiles = []
demo.welcome (String) = welcome-from-tree
demo.welcome bound = welcome-from-tree
demo.payload (byte[]) length = 4
demo.payload bound length = 4
db.host = db.lab.internal
mq.host = mq.lab.internal
Sources containing demo.welcome:
 - ...10-app...
 - ...application.yaml...
```

Tên `PropertySource` được rút gọn để minh họa. Ở máy bạn, dùng kết quả thực tế để xác định các location.

Từ kết quả này, bạn thấy một file văn bản được đọc thành `String`, một file nhị phân trở thành `byte[]` và hai cây khác cung cấp hai nhóm property riêng. Chuỗi `fallback-from-jar` có trong YAML nhưng không thắng giá trị `welcome-from-tree` nhập từ cấu hình bên ngoài.

### 8.3. Đóng gói JAR

```bash
./gradlew bootJar
java -jar build/libs/multi-config-tree-0.0.1-SNAPSHOT.jar
```

Trên PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\multi-config-tree-0.0.1-SNAPSHOT.jar
```

Hai cách chạy chỉ tương đương khi working directory trỏ đúng về project và các nguồn ghi đè khác không khác nhau. JAR vẫn dùng được trên máy không có thư mục lab nhờ import `optional:`, nhưng khi thiếu cây thì giá trị sẽ về mặc định hoặc không có.

Nếu đưa JAR sang thư mục khác, đường dẫn tương đối `./run/trees/` phụ thuộc thư mục chạy lúc đó. Trong container, nên dùng đường dẫn mount tuyệt đối ổn định như `/etc/config/`, đồng thời đảm bảo quyền đọc của tiến trình.

## 9. Bốn thí nghiệm mở rộng để hiểu ưu tiên và dữ liệu

### Thí nghiệm A — thay text trong một cây

Sửa file `run/trees/10-app/demo/welcome` thành `second-value`, giữ nguyên payload. Khởi động ứng dụng mới:

```text
demo.welcome (String) = second-value
demo.payload (byte[]) length = 4
```

Chỉ thay text không làm dữ liệu ở cây nhị phân thay đổi. Trường hợp này minh họa mỗi file trong tree là một nguồn giá trị độc lập.

### Thí nghiệm B — hai cây cùng cung cấp một khóa

Tạo thêm cây:

```text
run/trees/50-overrides/demo/welcome
```

Nội dung:

```text
overridden-by-later-tree
```

Wildcard sẽ mở rộng thêm thư mục `50-overrides`. Trong tình huống này, các thư mục con theo tên có tiền tố `10-`, `20-`, `30-`, `40-`, `50-` được sắp theo thứ tự chữ cái và cùng khai báo `demo.welcome` ở `10-app` và `50-overrides`; giá trị trùng trong import sau có thể ghi đè import trước:

```text
demo.welcome (String) = overridden-by-later-tree
```

Để tránh kết quả khó dự đoán khi hệ thống mount thêm thư mục ngoài ý muốn, đừng dùng cấu trúc trùng khóa này như mặc định vận hành. Nếu cần override chủ ý, chuyển sang danh sách `spring.config.import` tường minh với thứ tự đã quyết định.

### Thí nghiệm C — đổi vị trí gốc tree

Thay import thành:

```yaml
spring:
  main:
    web-application-type: none
  config:
    import: "optional:configtree:./run/trees/"
```

Sau đó thử truy cập:

```text
10-app.demo.welcome
20-binary.demo.payload
30-db.db.host
40-mq.mq.host
```

Vì gốc import là `run/trees/`, những segment tên thư mục `10-app`, `20-binary` ... nay là một phần của key. `demo.welcome` sẽ không còn có cùng cách ánh xạ từ thư mục `10-app` như trong import wildcard. Với code ví dụ đang mong `demo.welcome`, lúc này nó có thể trở về `fallback-from-jar`.

Thí nghiệm này giải thích vì sao lựa chọn import **một cây cha** hay **nhiều cây con** làm thay đổi namespace của property. Khi đổi import, cần cập nhật tên property hoặc cấu trúc thư mục cho phù hợp, không chỉ đổi một chuỗi đường dẫn.

### Thí nghiệm D — thay đổi kích thước payload nhị phân

Ghi lại file payload thành `[10, 20, 30, 40, 50]` bằng cách ghi bytes, khởi động lại:

```text
demo.payload (byte[]) length = 5
demo.payload bound length = 5
```

Bài tập này không cần nhìn giá trị bí mật. Nó chứng minh file được nạp dưới dạng bytes và ứng dụng nhận đúng chiều dài dữ liệu mong đợi.

**Lưu ý vòng đời:** import configuration tree là một phần của quá trình nạp cấu hình lúc Spring Boot khởi động. Thay nội dung file đang mount không mặc nhiên cập nhật các bean `@ConfigurationProperties` trong tiến trình đang chạy; các cơ chế refresh động cần được thiết kế, cấu hình và kiểm tra riêng. Trong bài lab, luôn chạy một tiến trình mới sau mỗi thay đổi.

## 10. Khi nào dùng wildcard, khi nào dùng danh sách tường minh?

| Tình huống | Cách dùng hợp lý | Giới hạn cần cân nhắc |
| --- | --- | --- |
| Nhiều mount độc lập, mỗi cây có namespace không trùng | `optional:configtree:/etc/config/*/` | Wildcard chỉ mở rộng thư mục con trực tiếp |
| Một volume chứa cả namespace dưới một gốc | `optional:configtree:/etc/config/` | Tên thư mục dưới gốc là một phần property name |
| Nhiều cây chủ ý ghi đè cùng khóa | Liệt kê các `configtree:` imports theo thứ tự | Thứ tự sau có thể thắng trong import cùng loại |
| Một YAML hoàn chỉnh được mount thành file | `optional:file:/etc/config/application.yaml` | Đây là file, không phải cây |
| Một file YAML thiếu phần mở rộng | Import file có extension hint như `file:/etc/config/myconfig[.yaml]` | Không dùng `configtree:` cho một file YAML đơn |
| Thiếu mount là lỗi cấu hình nghiêm trọng | Import không có `optional:` | Ứng dụng có thể không khởi động khi location vắng mặt |
| File binary cần giữ nguyên bytes | Bind `byte[]` | Không log, không vô tình decode bằng charset mặc định |
| File chứa text được tiêu thụ như chuỗi | Bind `String` | Quy ước encoding và newline cần được xác định |

Một bài toán vận hành tốt thường dùng wildcard khi **các cây độc lập và có tên khóa riêng**, liệt kê tường minh khi **thứ tự ghi đè là hợp đồng vận hành**. Cả hai vẫn phải có đường dẫn mount ổn định và quyền đọc thích hợp.

## 11. Kubernetes và Docker: ý nghĩa trong triển khai

Trên Kubernetes, ConfigMap và Secret có thể mount thành volume. Thông thường mỗi key trong nguồn dữ liệu xuất hiện thành một file ở đường dẫn mount. Spring Boot không cần biết dữ liệu ấy ban đầu đến từ ConfigMap hay Secret: với `configtree:` nó đọc cấu trúc file hiện hữu trong container.

Ví dụ hai volume mount:

```text
/etc/config/
├── configmap/
│   └── service/
│       └── region
└── secret/
    └── service/
        └── token
```

Khai báo:

```yaml
spring:
  config:
    import: "configtree:/etc/config/*/"
```

thì hai file có thể cấp `service.region` và `service.token`. `service.region` thường được sử dụng như text; `service.token` có thể được đọc như `String` hoặc `byte[]` tùy giao diện của thư viện tiêu thụ.

Không đưa nội dung file token vào endpoint chẩn đoán hay log. Cấu hình actuator như `/actuator/env` và `/actuator/configprops` cần quyền truy cập và chính sách che giá trị phù hợp. Kubernetes Secrets là cơ chế phân phối dữ liệu nhạy cảm, không tự bảo đảm bí mật tuyệt đối nếu quyền truy cập cluster, mount, logs hoặc process memory bị lộ.

Với Docker Swarm secrets, một secret có tên `db.password` có thể được mount thành file:

```text
/run/secrets/db.password
```

Khi đó có thể import bằng:

```properties
spring.config.import=optional:configtree:/run/secrets/
```

và truy cập property `db.password`.

Các file nhạy cảm trong môi trường thật phải được tạo và quản lý bằng cơ chế triển khai phù hợp; không commit nội dung secret hoặc key thật vào repository. Nếu cần rotate secret trong một tiến trình đang chạy, phải thiết kế hành vi tái nạp hoặc khởi động lại, đồng bộ với cách nền tảng cập nhật volume. Không mặc định rằng Spring Boot tự refresh ngay khi file đổi.

## 12. Lỗi thường gặp và cách xử lý

**Đã mount cả thư mục nhưng không thấy property.** Kiểm tra `spring.config.import` đã dùng `configtree:` thay vì `file:` hay chưa, đường dẫn có trỏ đúng vào cây không, và tiến trình có quyền đọc file không. Với tên không trùng mong đợi, xem lại gốc cây nhập và các segment thư mục tạo key.

**Import wildcard không tìm thấy một cây con.** Wildcard `*/` chỉ mở rộng các thư mục con trực tiếp dưới thư mục cha. Nếu dữ liệu nằm ở một tầng sâu hơn, dùng đường dẫn cha phù hợp hoặc liệt kê vị trí rõ ràng.

**Tên property xuất hiện thêm prefix lạ.** Nếu import `configtree:/etc/config/`, thư mục `mysql/` nằm dưới gốc sẽ xuất hiện trong tên key như `mysql.username`. Nếu import `configtree:/etc/config/*/`, `mysql/` là gốc riêng và key bên trong có thể là `username`. Chọn root dựa trên namespace muốn tạo.

**Giá trị từ cây bị ghi đè ngoài dự kiến.** Kiểm tra cây khác có cùng khóa, thứ tự sắp xếp wildcard, danh sách import, profile, biến môi trường, Java system property, CLI và các nguồn khác. Kết luận từ giá trị cuối và cấu hình thực tế, không chỉ từ tên file vừa sửa.

**Ứng dụng không khởi động khi thiếu cây.** Nếu location là tùy chọn, thêm `optional:` vào trước `configtree:`. Nếu đây là volume bắt buộc, giữ lỗi khởi động để phát hiện triển khai thiếu mount sớm.

**Đọc bytes cho ra ký tự lạ hoặc lỗi decode.** Kiểm tra bạn có đang xử lý payload nhị phân như text không. `byte[]` dùng cho dữ liệu raw; nếu phải chuyển bytes thành chuỗi, chỉ làm với dữ liệu thật sự có encoding hợp lệ và chỉ rõ charset.

**Độ dài dữ liệu nhị phân lớn hơn dự kiến.** Kiểm tra file có BOM, newline, ký tự kết thúc hoặc encoding do công cụ ghi tạo ra. Tránh dùng `echo` khi cần đúng byte. Dùng `WriteAllBytes` hoặc công cụ tạo nhị phân phù hợp.

**Code binding `DemoProperties` nhận `null`.** Xác định import có thực sự nạp file, tên key có đúng `demo.payload`, và `@ConfigurationPropertiesScan` có quét package chứa record. Với ứng dụng khởi động trước khi mount có mặt, cần chạy lại sau khi tạo mount.

**Đã sửa file trong volume mà ứng dụng đang chạy vẫn giữ giá trị cũ.** Config Data thông thường được nạp khi khởi động. Kiểm tra tiến trình đã restart hay chưa, và nếu dùng cơ chế refresh thì phải kiểm tra riêng hành vi của cơ chế đó.

**Không thấy dữ liệu trong Actuator.** Endpoint có thể không được expose, người dùng thiếu quyền hoặc giá trị bị che đúng chủ đích. Không tắt bảo vệ để đọc secret; trong lab chỉ cần nhìn các khóa giả lập và độ dài payload.

## 13. Checklist thực hành theo thứ tự

1. Tạo project Spring Boot, khai báo import wildcard và chạy khi chưa có cây để thấy giá trị nền.
2. Tạo `10-app` chứa text, khởi động lại và quan sát `demo.welcome`.
3. Tạo `20-binary` chứa payload bốn byte, khởi động lại và quan sát hai độ dài bytes.
4. Tạo `30-db` và `40-mq` để thấy `db.host` và `mq.host` từ hai namespace.
5. Thêm `50-overrides`, dự đoán rồi xác nhận giá trị trùng khóa khi có nhiều cây.
6. Thử đổi import từ `*/` sang một cây cha, ghi nhận khác biệt về tên property.
7. So sánh import tùy chọn với import bắt buộc khi đường dẫn không tồn tại.
8. Khôi phục cấu hình lab ban đầu và chỉ sử dụng dữ liệu giả lập, tránh tạo file nhạy cảm trong project.

Bảng ghi kết quả:

| Lần chạy | Import/cây được thay đổi | Kỳ vọng | Kết quả trên máy |
| --- | --- | --- | --- |
| 1 | Không có cây, có `optional:` | `fallback-from-jar` | Tự ghi |
| 2 | Thêm cây text | `welcome-from-tree` | Tự ghi |
| 3 | Thêm payload bốn byte | Length = 4 | Tự ghi |
| 4 | Thêm cây DB và MQ | Hai host độc lập | Tự ghi |
| 5 | Thêm cây ghi đè | Giá trị từ cây override được ưu tiên | Tự ghi |
| 6 | Đổi gốc import | Tên property thay đổi | Tự ghi |
| 7 | Thiếu cây bắt buộc | Lỗi nạp location | Tự ghi |

## 14. Câu hỏi tự kiểm tra

**1. Vì sao cần `configtree:` khi mount một file trên mỗi khóa?** Vì Spring Boot cần biết đọc cả cây thư mục, lấy đường dẫn tương đối làm property name và nội dung từng file làm value; cú pháp đọc một file YAML đơn không mô tả được kiểu dữ liệu này.

**2. `configtree:/etc/config/` và `configtree:/etc/config/*/` có luôn cho cùng tên property không?** Không. Cách thứ nhất chọn cả `config` làm gốc, cách thứ hai chọn từng thư mục con trực tiếp làm gốc, nên segment tên thư mục có thể xuất hiện hoặc biến mất trong key.

**3. Có thể import nhiều cây mà không dùng wildcard không?** Có. Dùng danh sách `spring.config.import` với các `configtree:` location tường minh, nhất là khi muốn xác định thứ tự override.

**4. Nếu payload có byte `FF`, nên dùng `String` hay `byte[]`?** Với payload nhị phân cần giữ chính xác bytes, dùng `byte[]`. Không giả định byte `FF` là ký tự UTF-8 hợp lệ.

**5. Vì sao không dùng `System.out.println(Arrays.toString(secretBytes))` để debug production?** Vì nó có thể làm lộ toàn bộ dữ liệu nhạy cảm trong log. Độ dài hoặc trạng thái có/không với dữ liệu thử nghiệm thường đủ để xác nhận import hoạt động.

**6. Nếu đổi nội dung file secret khi app đang chạy, bean cấu hình có tự đổi ngay không?** Không mặc định. Cơ chế nạp ban đầu xảy ra khi khởi động; refresh động là thiết kế riêng cần đánh giá.

**7. Khi nhiều cây chứa cùng khóa, bạn cần xem những yếu tố nào?** Thứ tự import, thứ tự wildcard, location group nếu có, profile và các nguồn cấu hình ưu tiên cao hơn. Muốn kết quả ổn định, giảm trùng khóa hoặc liệt kê location rõ ràng.

**8. Nếu không mount cây trong môi trường production mà volume đó bắt buộc thì sao?** Không dùng `optional:` để che sự vắng mặt. Để ứng dụng báo lỗi và sửa cấu hình triển khai thay vì âm thầm dùng giá trị ngoài dự kiến.

## 15. Áp dụng vào dự án thực tế

Cây cấu hình hữu ích khi một nền tảng triển khai phân phối **nhiều nhóm thuộc tính bằng filesystem**, đặc biệt mỗi ứng dụng dùng một số ConfigMap hoặc Secret khác nhau. Chọn `configtree:` thay vì cấu hình đường dẫn tới YAML khi một file tương ứng một khóa; chọn wildcard khi cần nhập các cây con độc lập, và dùng thứ tự import tường minh khi có quy tắc ghi đè được thiết kế trước.

Giữ các khóa nghiệp vụ có namespace rõ ràng, sử dụng kiểu Java đúng với nội dung file, kiểm soát encoding và newline, không xuất secret ra log và không mặc định có refresh động. Với sự cố cấu hình, hãy bắt đầu từ đường dẫn mount thực tế, gốc import, tên property sinh ra, thứ tự các cây và kiểu đích của giá trị. Khi từng yếu tố được quan sát riêng, việc kết hợp nhiều nguồn cấu hình của Spring Boot trở nên có thể dự đoán và kiểm soát.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), đặc biệt các mục *Importing Additional Data* và *Using Configuration Trees*.