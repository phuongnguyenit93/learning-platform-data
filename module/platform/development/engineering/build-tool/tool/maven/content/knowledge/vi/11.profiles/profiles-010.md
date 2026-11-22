# Phân biệt cấu hình lúc build với cấu hình ứng dụng lúc chạy trong Maven

## 1. Hai giai đoạn khác nhau trong một ứng dụng Java

Khi dùng Maven để làm một ứng dụng Java, chúng ta gặp hai nhóm thiết lập dễ bị nhầm: **cấu hình tại thời điểm build** và **cấu hình tại thời điểm chạy chương trình**.

- **Build time:** Maven đọc `pom.xml`, parent POM, profiles, `settings.xml`, tham số CLI và môi trường build; sau đó chạy plugin để biên dịch, kiểm thử, xử lý resources, đóng gói JAR/WAR và tạo artifact.
- **Runtime:** Một tiến trình JVM thực thi mã Java đã được build. Ứng dụng có thể đọc JVM system properties, environment variables, tham số dòng lệnh, file bên ngoài JAR, dịch vụ cấu hình hoặc secret manager.

Hai hoạt động liên quan nhưng không đồng nhất: **`mvn -Pprod package` không tự khiến mọi chương trình Java chạy với runtime mode `prod`**, và **`java -Dapp.mode=qa ...` không chạy Maven hay biên dịch lại JAR**.

Bài này thuộc phần Maven Profile. Ta sẽ dùng Maven 3.x, JDK 17+ và một ứng dụng Java thuần để phân biệt hai giai đoạn bằng các lệnh và output có thể kiểm chứng. Sau khi học, bạn có thể xác định một giá trị nằm **bên trong artifact** hay đến từ **môi trường chạy**, biết khi nào cần rebuild/restart và tránh nhúng bí mật vào JAR.

## 2. Bảng so sánh build configuration và runtime configuration

| Tiêu chí | Cấu hình build | Cấu hình runtime |
| --- | --- | --- |
| Ai sử dụng? | Maven Core, Maven plugins, compiler, test plugins, CI. | JVM, mã Java và framework ứng dụng. |
| Nguồn thường gặp | `pom.xml`, `<profiles>`, `mvn -P...`, Maven user property `-D...`, `settings.xml`, build environment. | JVM `java -D...`, environment variables, arguments, file cấu hình ngoài JAR, config/secret service. |
| Tác động thường gặp | Java release, dependency, plugin execution, file resources được lọc, các lớp/đầu ra đã đóng gói. | URL dịch vụ, timeout, log level, cổng, feature flag, môi trường nghiệp vụ, credential. |
| Khi thay đổi | Có thể cần tạo lại artifact nếu thay đổi đầu ra build. | Thường có thể dùng cùng artifact ở lần chạy tiếp theo với thiết lập mới. |
| Cách xác minh | Maven log, active profiles, effective POM, `target/classes`, JAR. | Lệnh chạy JVM, startup validation, logs an toàn, process environment/config source. |
| Rủi ro nổi bật | Artifact khác nhau dưới cùng version, cấu hình môi trường bị đóng đinh, secret bị đưa vào JAR. | Giá trị bị thiếu, sai thứ tự ưu tiên, sai quyền đọc file/secret, nhầm phiên bản tiến trình. |

Cùng một tên thuộc tính có thể tồn tại ở hai nơi mà không có kết nối tự động. Ví dụ `app.mode` trong Maven POM và `app.mode` trong `System.getProperty("app.mode")` là hai nguồn dữ liệu khác nhau, dù cùng chuỗi ký tự.

### Sơ đồ cơ chế

~~~text
pom.xml + Maven profile + source/resource
                    │
                    ▼
           mvn -Pdev package
                    │
       compile / filter / package
                    │
                    ▼
   build-runtime-demo-1.0-SNAPSHOT.jar
                    │
           ┌────────┴─────────┐
           ▼                  ▼
java -Dapp.mode=local   java -Dapp.mode=cloud
           │                  │
           ▼                  ▼
  runtime mode=local   runtime mode=cloud
      cùng một JAR        cùng một JAR
~~~

Để hiểu kết quả, phải hỏi: giá trị đã được **ghi thành byte vào sản phẩm build** chưa, hay ứng dụng **đọc nó khi JVM khởi động**?

## 3. Maven profile là cơ chế của build, không phải runtime profile

Trong `pom.xml`, một Maven profile có thể định nghĩa properties hoặc điều chỉnh cách Maven giải quyết dependency, plugin và resource. Ví dụ **mảnh XML đặt dưới `<project>`**:

~~~xml
<profiles>
    <profile>
        <id>dev</id>
        <properties>
            <build.channel>dev</build.channel>
        </properties>
    </profile>
    <profile>
        <id>prod</id>
        <properties>
            <build.channel>prod</build.channel>
        </properties>
    </profile>
</profiles>
~~~

Khi chọn:

~~~bash
mvn -Pdev clean package
mvn -Pprod clean package
~~~

Maven xây dựng model hiệu lực tương ứng với profile đã kích hoạt. **Nhưng việc định nghĩa property chưa chắc làm thay đổi artifact:** một plugin, bước filtering hay cấu hình build phải thực sự sử dụng `build.channel`.

Điều Maven **không tự thực hiện** chỉ vì bạn gọi `-Pprod`:

1. Tự chuyển một ứng dụng Java sang chế độ production.
2. Tự truyền `-Dapp.mode=prod` hoặc `-Dspring.profiles.active=prod` cho JVM được chạy sau đó.
3. Tự tạo/đọc file application config ở runtime.
4. Tự cấp quyền vào database, repository hoặc dịch vụ production.
5. Tự bảo đảm nội dung JAR từ profile `prod` giống JAR từ profile `dev`.

### Profile trong POM và trong settings khác nhau

| Vị trí profile | Thường dùng để làm gì? | Phạm vi cấu hình |
| --- | --- | --- |
| `pom.xml` / parent POM | Điều chỉnh build chia sẻ cho dự án: properties, plugin/dependencies và các cấu hình hợp lệ của POM profile. | Theo project, đi cùng source code. |
| `settings.xml` | Cung cấp property/repository/pluginRepository theo môi trường Maven của người dùng/CI. | Theo người dùng, máy hoặc CI, không thay thế đầy đủ build/plugins trong POM. |

`settings.xml` còn có `activeProfiles` để chọn profile cần áp dụng, hoặc có thể chọn qua `-P`. Settings profile có phạm vi cấu hình hạn chế hơn POM profile. Cả hai đều là cơ chế **Maven build**; không nên đồng nhất với Spring profiles hay runtime environment của Java.

## 4. Thực hành: một giá trị nhúng vào JAR và một giá trị lấy từ JVM

Ta tạo dự án `build-runtime-demo` có hai giá trị độc lập:

- **`build.channel`** do Maven profile quyết định và được **resource filtering** ghi vào file `build-info.properties` bên trong JAR.
- **`app.mode`** do JVM system property hoặc biến môi trường `APP_MODE` cung cấp khi chạy. Nếu thiếu cả hai, chương trình chọn `local`.

Cây thư mục:

~~~text
build-runtime-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── App.java
        └── resources/
            └── build-info.properties
~~~

Tạo thư mục bằng IDE hoặc terminal. Ví dụ Bash:

~~~bash
mkdir -p build-runtime-demo/src/main/java/com/example
mkdir -p build-runtime-demo/src/main/resources
cd build-runtime-demo
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "build-runtime-demo\src\main\java\com\example" | Out-Null
New-Item -ItemType Directory -Force -Path "build-runtime-demo\src\main\resources" | Out-Null
Set-Location build-runtime-demo
~~~

Lưu nội dung ba tệp theo các đoạn dưới đây bằng UTF-8. Các lệnh tạo thư mục không tự tạo nội dung tệp.

### 4.1. POM hoàn chỉnh cho Java 17

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>build-runtime-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <build.channel>dev</build.channel>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <includes>
                    <include>**/*.properties</include>
                </includes>
                <filtering>true</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <properties>
                <build.channel>dev</build.channel>
            </properties>
        </profile>
        <profile>
            <id>prod</id>
            <properties>
                <build.channel>prod</build.channel>
            </properties>
        </profile>
    </profiles>
</project>
~~~

POM này có các chi tiết đáng chú ý:

- `maven.compiler.release=17` chốt Java target, tránh phụ thuộc vào phiên bản compiler plugin mặc định.
- `build.channel=dev` cấp giá trị **dự phòng ở model gốc**. Profile `prod` thay giá trị đó khi active.
- Resource filtering được bật **chỉ cho file `.properties`**. Với `<resources>` đã tùy chỉnh, các loại tài nguyên khác cần được khai báo nếu muốn copy vào artifact.
- Các plugin có phiên bản cụ thể để ví dụ dễ đối chiếu; không ngụ ý đây là những phiên bản mới nhất.
- `mvn -Pprod` thay dữ liệu đầu vào cho Maven Resources Plugin, chứ bản thân profile không trực tiếp sửa file Java.

### 4.2. Tệp resource để lọc lúc build

Tạo `src/main/resources/build-info.properties`:

~~~properties
build.channel=@build.channel@
~~~

`@build.channel@` là placeholder Maven Resources Plugin có thể thay bằng property `build.channel`. Sau khi build bằng profile `dev`, kết quả tại `target/classes/build-info.properties` dự kiến:

~~~properties
build.channel=dev
~~~

Sau khi build bằng profile `prod`:

~~~properties
build.channel=prod
~~~

**Tệp nguồn vẫn là** `build.channel=@build.channel@`. Maven thay placeholder **trong bản sao output**, và bản sao này được đóng gói vào JAR.

### 4.3. Java 17 đọc cả hai nguồn dữ liệu

Tạo `src/main/java/com/example/App.java`:

~~~java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        Properties info = new Properties();

        try (InputStream input =
                     App.class.getResourceAsStream("/build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing build-info.properties on classpath");
            }
            info.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }

        String mode = System.getProperty("app.mode");
        if (mode == null || mode.isBlank()) {
            mode = System.getenv("APP_MODE");
        }
        if (mode == null || mode.isBlank()) {
            mode = "local";
        }

        System.out.println("Build channel: "
                + info.getProperty("build.channel"));
        System.out.println("Runtime mode: " + mode);
    }
}
~~~

Chương trình hợp lệ với Java 17 và không cần dependency bên ngoài JDK.

- `getResourceAsStream("/build-info.properties")` đọc tài nguyên classpath dù chạy từ `target/classes` hay JAR. Nếu không tồn tại, chương trình báo lỗi rõ ràng.
- `InputStreamReader(..., UTF_8)` đọc resource với charset được chỉ định. Cách này tránh nhầm `Properties.load(InputStream)` là API tự nhận diện mọi file UTF-8.
- `System.getProperty("app.mode")` đọc JVM system property lúc chạy.
- `System.getenv("APP_MODE")` đọc environment variable cấp cho tiến trình Java.
- `isBlank()` giúp bỏ qua giá trị rỗng/toàn khoảng trắng.
- **Thứ tự ưu tiên là do mã của ứng dụng định nghĩa:** JVM property > environment variable > `local`. Đây **không phải** precedence mặc định của mọi thư viện Java hoặc Spring.

Không có lời gọi `mvn`, `settings.xml` hoặc `-P` trong class `App`. Thông tin build đến từ resource đã được đóng gói, còn runtime mode đến từ JVM/process hiện tại.

## 5. Thử nghiệm A: build `dev`, thay runtime mode mà không rebuild

Trong thư mục dự án, kiểm tra công cụ và build:

~~~bash
mvn --version
java -version
mvn -Pdev clean package
~~~

Khi Maven hoàn tất, `target/` thường có:

~~~text
target/
├── classes/
│   ├── com/example/App.class
│   └── build-info.properties
└── build-runtime-demo-1.0-SNAPSHOT.jar
~~~

Đây là cây rút gọn. Kiểm tra file `target/classes/build-info.properties` để thấy `build.channel=dev`.

Chạy lần đầu với system property tường minh:

~~~bash
java -Dapp.mode=local -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Build channel: dev
Runtime mode: local
~~~

Vì đã truyền JVM property tường minh, kết quả không phụ thuộc `APP_MODE` còn tồn tại trong shell hay không. POM chưa khai báo manifest `Main-Class`, nên lệnh được chạy bằng `-cp` thay vì giả định `java -jar` hoạt động.

Bây giờ **giữ nguyên JAR**, đổi JVM property:

~~~bash
java -Dapp.mode=staging -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Build channel: dev
Runtime mode: staging
~~~

`Build channel` không thay vì đã ghi vào JAR lúc build. `Runtime mode` thay vì một tiến trình Java mới nhận giá trị `staging`.

### Dùng environment variable

Trên Bash (Linux/macOS), không truyền `java -Dapp.mode`:

~~~bash
APP_MODE=cloud java -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout:**

~~~text
Build channel: dev
Runtime mode: cloud
~~~

Trên Windows PowerShell:

~~~powershell
$env:APP_MODE = "cloud"
java -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
Remove-Item Env:APP_MODE
~~~

Nếu `APP_MODE` có giá trị trước khi thử, hãy lưu lại giá trị đó để khôi phục thay vì xóa. Đặc điểm của ví dụ: khi truyền **cả** `java -Dapp.mode=local` và `APP_MODE=cloud`, kết quả runtime là `local`, vì Java code kiểm tra system property trước.

### Vị trí chính xác của `-D` với Java launcher

Cú pháp hợp lệ:

~~~bash
java -Dapp.mode=qa -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Nếu viết:

~~~bash
java -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App -Dapp.mode=qa
~~~

chuỗi `-Dapp.mode=qa` ở sau tên class chính sẽ trở thành **tham số trong `String[] args`**; nó **không tự đặt JVM system property**. Chương trình `App` không xử lý `args`, nên mode vẫn lấy từ nguồn khác hoặc mặc định.

## 6. Thử nghiệm B: build `prod`, giữ runtime `local`

Chạy lại Maven với profile khác:

~~~bash
mvn -Pprod clean package
~~~

Giờ file `target/classes/build-info.properties` chứa:

~~~properties
build.channel=prod
~~~

Chạy:

~~~bash
java -Dapp.mode=local -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout chính xác:**

~~~text
Build channel: prod
Runtime mode: local
~~~

Build profile đã đổi thông tin nhúng vào JAR, nhưng runtime mode vẫn là `local`. Nếu chạy tiếp:

~~~bash
java -Dapp.mode=production -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

**Stdout:**

~~~text
Build channel: prod
Runtime mode: production
~~~

Hai build có thể tạo tệp **cùng đường dẫn** `target/build-runtime-demo-1.0-SNAPSHOT.jar` nhưng byte khác nhau. Lần build sau có thể thay thế sản phẩm cũ trong workspace. Khi phát hành artifact thật, không nên để **cùng tọa độ release** trỏ tới hai nội dung tùy môi trường: hãy cố định quy trình build, lưu provenance/checksum và quản lý phiên bản nhất quán.

## 7. `mvn -D...` và `java -D...` không phải cùng một property

Hai công cụ cùng chấp nhận dạng tham số có tiền tố `-D`, nhưng mục đích khác:

| Lệnh | Ai xử lý `-D`? | Kết quả |
| --- | --- | --- |
| `mvn -Dbuild.channel=test clean package` | Maven CLI/user property trong build. | Có thể được Maven plugin/resource filtering dùng khi tạo artifact. |
| `mvn -Pprod clean package` | Maven chọn profile rồi dựng model. | Profile có thể thay các property và plugin execution của build. |
| `java -Dapp.mode=qa -cp ... com.example.App` | Java launcher/JVM. | `System.getProperty("app.mode")` trong Java đọc được `qa`. |
| `APP_MODE=qa java -cp ... com.example.App` | Shell cấp biến môi trường cho Java process. | `System.getenv("APP_MODE")` đọc được `qa`. |

Ví dụ sai kỳ vọng:

~~~bash
mvn -Dapp.mode=qa package
java -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Không có cơ chế nào trong chương trình mẫu chuyển Maven property `app.mode` thành JVM system property. Lệnh `mvn` chạy trước và quá trình Java chạy sau là **hai invocation khác nhau**.

Có thể cấu hình plugin như Surefire hoặc Exec truyền properties khi chạy test/chương trình qua Maven, hoặc dùng filtering nhúng property vào artifact. Nhưng đó là **cầu nối được thiết kế và cấu hình**, không phải quy tắc tự động giữa mọi lệnh Maven và Java.

Một Maven property được nhúng qua resource filtering cũng **không còn tự thay đổi** khi bạn truyền `java -Dbuild.channel=prod`, trừ khi Java code chủ động đọc system property cùng tên để override resource.

## 8. Maven profile `prod` và Spring profile `prod` khác nhau

Trong ứng dụng dùng Spring Boot, có cơ chế cấu hình ứng dụng riêng, thường liên quan `spring.profiles.active`, `SPRING_PROFILES_ACTIVE` và các nguồn cấu hình Spring Environment. Nó chủ yếu phục vụ **runtime configuration** của Spring.

So sánh về ý nghĩa:

~~~bash
mvn -Pprod clean package
~~~

Lệnh này kích hoạt **Maven POM profile** `prod` nếu dự án định nghĩa nó. Còn:

~~~bash
java -Dspring.profiles.active=prod -jar spring-app.jar
~~~

là một lệnh minh họa khởi động **Spring Boot executable JAR đã được đóng gói đúng** và cung cấp JVM system property cho Spring. Tệp `spring-app.jar` ở đây chỉ là tên ví dụ, không phải artifact của project `build-runtime-demo`.

**Không có ánh xạ bắt buộc:** Maven `-Pprod` không tự biến thành Spring `spring.profiles.active=prod`. Một nhóm có thể thiết kế cơ chế nối hai cấu hình, nhưng phải nêu rõ plugin, resources, thứ tự ưu tiên và kiểm thử. Sự trùng tên `dev`/`prod` không có ý nghĩa kỹ thuật nếu thiếu cầu nối.

Tương tự, một số framework khác có quy ước profile/environment riêng. Hãy kiểm tra đúng tài liệu framework và phiên bản, không áp dụng mặc định cơ chế Maven cho chương trình ứng dụng.

## 9. Cấu hình nào nên quyết định ở build, cấu hình nào để runtime?

Một nguyên tắc hữu ích là: **những thứ quyết định cấu trúc artifact thường là build-time; những thứ phụ thuộc nơi triển khai nên ưu tiên runtime**.

| Tham số | Thời điểm thường phù hợp | Lý do |
| --- | --- | --- |
| Java target release, compiler flags | Build | Quyết định bytecode/compatibility. |
| Dependency version, plugin version | Build | Ảnh hưởng nội dung và tính tái hiện. |
| Test/report/annotation processing | Build | Chạy trong pipeline tạo artifact. |
| Commit SHA, build version | Build | Metadata truy vết artifact. |
| Maven dependency repository/proxy | Build | Phục vụ download dependency/plugin. |
| URL database hoặc downstream API | Runtime | Khác theo dev/staging/prod. |
| Timeout, pool size, log level | Runtime nếu app hỗ trợ | Có thể tinh chỉnh theo môi trường. |
| Feature flag triển khai | Runtime nếu được thiết kế an toàn | Tránh build JAR khác cho từng môi trường. |
| Password, API token, private key | Runtime qua secret management | Không nhúng vào artifact hoặc log build. |

**Khuyến nghị phổ biến:** build một lần, triển khai **cùng artifact** qua staging và production, cung cấp runtime config riêng tại nơi triển khai. Cách này giúp giảm nguy cơ “đã test một JAR nhưng deploy một JAR khác”. Nếu hệ thống thực sự cần artifact riêng theo nền tảng/cấu hình build, phải quản lý version, classifier hoặc nguồn gốc artifact rõ ràng.

Đừng nhầm “runtime configuration” với “tự thay đổi trong tiến trình đang chạy”: nhiều ứng dụng đọc cấu hình **một lần lúc khởi động**. Thay biến môi trường ở shell khác không nhất thiết thay đổi giá trị trong JVM đã chạy. Có thể cần restart hoặc cơ chế hot-reload được thiết kế rõ.

## 10. Resource filtering và rủi ro đóng đinh cấu hình môi trường

Trong ví dụ, Maven Resources Plugin xử lý:

~~~text
src/main/resources/build-info.properties
    build.channel=@build.channel@
                 │
                 │ mvn -Pprod process-resources
                 ▼
target/classes/build-info.properties
    build.channel=prod
                 │
                 │ mvn package
                 ▼
JAR entry: build-info.properties
~~~

Đây là **build-time transformation**. JVM ở máy khác không quay lại POM hay resource nguồn để tính lại property.

Các lỗi thường gặp:

- Quên bật `<filtering>true</filtering>` nên placeholder nằm nguyên trong JAR.
- Profile chưa active hoặc property sai tên nên không được thay.
- Build chưa chạy lại sau khi đổi property.
- File không khớp `<includes>` hoặc bị exclude.
- Bật filtering cho file nhị phân khiến ảnh, file nén, font hoặc PDF bị hỏng.
- Charset không nhất quán giữa file nguồn, Maven Resources Plugin và cách Java đọc.
- Nhúng thông tin chỉ đúng trong môi trường staging vào JAR rồi dùng chính JAR đó cho production.

**Bí mật là trường hợp đặc biệt nghiêm trọng.** Không viết:

~~~properties
database.password=@database.password@
~~~

nếu Maven có thể thay chuỗi đó bằng mật khẩu thật. Một file JAR thường có thể được giải nén, sao chép, cache và lưu trong artifact repository; bí mật có thể tồn tại ở đó lâu sau khi build. Hãy dùng secret manager, môi trường runtime, quyền truy cập file an toàn hoặc cơ chế cấp bí mật đã được phê duyệt.

Không đưa token vào `pom.xml`, `settings.xml` được commit lên Git, stdout, báo cáo công khai hay log `mvn -X`.

## 11. File cấu hình ở ngoài JAR: runtime config thực sự

Nhiều hệ thống cung cấp YAML/JSON/properties ở máy triển khai thay vì gắn mọi giá trị vào JAR. Java thuần không tự đọc một file `application.properties` nằm cạnh JAR; bạn hoặc framework phải viết/cấu hình cơ chế nạp.

Ví dụ **đoạn mã minh họa, không phải chương trình độc lập**, đặt trong một phương thức xử lý `IOException`:

~~~java
String path = System.getProperty("app.config");
if (path != null && !path.isBlank()) {
    java.nio.file.Path configFile = java.nio.file.Path.of(path);
    String text = java.nio.file.Files.readString(
            configFile, java.nio.charset.StandardCharsets.UTF_8);
    // Phân tích nội dung text theo định dạng ứng dụng hỗ trợ.
}
~~~

Khi ứng dụng thực sự tích hợp logic tương ứng, người vận hành có thể dùng dạng lệnh:

~~~bash
java -Dapp.config=/etc/example/app.properties -cp app.jar com.example.App
~~~

Đường dẫn và JAR ở lệnh này chỉ minh họa. **Class `App` hoàn chỉnh ở mục 4 không có tính năng đọc `app.config`**, nên thêm `-Dapp.config` vào demo ban đầu không tạo ra hiệu ứng nào. Cần code parser, xử lý file không tồn tại, validation dữ liệu và kiểm soát quyền mới có chức năng đó.

Một chính sách cấu hình runtime có thể chọn thứ tự như: **JVM property > environment variable > external config file > safe default**. Nhưng thứ tự **không mặc định giống nhau** ở mọi framework; hãy viết rõ trong tài liệu dự án và kiểm tra bằng test.

### Cấu hình được đọc lúc startup hay cập nhật liên tục?

Chương trình mẫu đọc `System.getenv` và `System.getProperty` trong `main` khi tiến trình khởi động. Nếu bạn cần đổi cấu hình của một process Java đang chạy, không thể chỉ sửa file hoặc biến môi trường trong terminal khác rồi mặc định JVM cập nhật. Ứng dụng phải hỗ trợ reload, polling, watch hoặc dịch vụ dynamic configuration. “Không cần build lại” **không đồng nghĩa** “không cần restart”.

## 12. CI/CD: một artifact và nhiều môi trường

Mô hình triển khai thường được ưa chuộng:

~~~text
Git commit
    │
    ▼
CI: mvn clean verify
    │ kiểm tra compiler/dependencies/tests
    ▼
Artifact JAR + metadata nguồn gốc/checksum
    │
    ├─ deploy staging: APP_MODE=staging + staging endpoints/secrets
    │
    └─ deploy production: APP_MODE=production + prod endpoints/secrets
~~~

Trong sơ đồ này, **cùng artifact đã kiểm thử** được đưa tới các môi trường. Maven profile như `ci` có thể điều chỉnh test/report cho pipeline, nhưng không trở thành runtime profile nếu thiếu cầu nối.

Để tránh sai lệch:

1. Ghi commit, JDK, Maven, dependency và plugin versions cho build.
2. Ghi nhận active Maven profiles dùng trong CI; tránh thay profile giữa kiểm thử và tạo release nếu không được thiết kế.
3. Xác minh artifact, checksum và metadata nguồn gốc.
4. Để endpoint, port, log level, secret phụ thuộc môi trường ở runtime khi thích hợp.
5. Kiểm tra startup validation: thiếu config bắt buộc thì lỗi rõ nhưng không lộ dữ liệu nhạy cảm.
6. Viết test cho cách đọc runtime settings và thứ tự ưu tiên.
7. Cân nhắc cách restart/reload để thay đổi runtime settings an toàn.

Nếu cùng version release có thể sinh hai JAR khác nhau chỉ vì CI chạy `-Pdev` rồi `-Pprod`, tính bất biến và việc truy vết bản phát hành sẽ yếu đi. Hãy quyết định một quy trình artifact nhất quán trước khi deploy.

## 13. Công cụ kiểm tra cấu hình của hai thời điểm

### 13.1. Xem Maven profile, property và effective POM

~~~bash
mvn -Pprod help:active-profiles
mvn -Pprod help:evaluate -Dexpression=build.channel -q -DforceStdout
mvn -Pprod help:effective-pom -Doutput=effective-pom.xml
~~~

Lệnh `help:evaluate` ở giữa trên POM mẫu dự kiến trả:

~~~text
prod
~~~

Lệnh `help:active-profiles` liệt kê các profile thực sự active. `help:effective-pom` cho thấy model đã kết hợp từ POM, parent và profiles. Chúng là các lệnh riêng; output có thể có log Maven khác nhau. Maven Help Plugin có thể cần tải về lần đầu nếu cache chưa có.

Nếu Maven dùng `settings.xml` của doanh nghiệp, repository mirror, active profiles hoặc properties từ settings cũng có thể tác động đến kết quả. Cần kiểm tra settings đúng môi trường nhưng không chia sẻ credential hay log nhạy cảm lên nơi công cộng.

### 13.2. Xem artifact thực tế

~~~bash
mvn -Pdev clean package
jar tf target/build-runtime-demo-1.0-SNAPSHOT.jar
~~~

`jar tf` liệt kê entry; nó **không cho biết nội dung resource**. Hãy xem `target/classes/build-info.properties` để xác nhận đã filtering. Nếu muốn kiểm tra nội dung trong JAR, dùng công cụ giải nén có kiểm soát vào thư mục riêng, tránh `jar xf` vô tình ghi đè tệp nguồn cùng tên.

### 13.3. Xem runtime process

Sau khi tạo artifact với profile `prod`:

~~~bash
java -Dapp.mode=qa -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App
~~~

Output chính xác:

~~~text
Build channel: prod
Runtime mode: qa
~~~

Nếu không truyền JVM property và không có `APP_MODE`, code mẫu dùng fallback `local`. Đây là default **do ta lập trình**, không phải mặc định của Maven, Java hay hệ điều hành.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `mvn -Pprod package` nhưng `Runtime mode: local` | Profile Maven không đặt JVM runtime property. | Truyền `java -Dapp.mode=production` hoặc `APP_MODE` theo cơ chế app. |
| Đặt `APP_MODE=cloud` nhưng Java vẫn in `local` | Có system property `-Dapp.mode=local` đang ưu tiên; hoặc chạy tiến trình/JAR khác. | Kiểm tra đúng lệnh, nguồn config và process. |
| `build.channel=@build.channel@` không được thay | Filtering chưa bật, property thiếu, profile chưa active hoặc file bị loại. | Kiểm tra `<resources>`, `help:evaluate`, `target/classes`. |
| `-Pdev` và `-Pprod` cho kết quả giống nhau | Property chưa được plugin sử dụng hoặc đang chạy JAR cũ. | Kiểm tra resource output và artifact path sau clean build. |
| Maven báo không nhận diện profile | ID trong `-P` không tồn tại/không được đọc. | Kiểm tra `pom.xml`, settings, `help:active-profiles`. |
| `java -D...` viết sau tên main class | Đây là argument của ứng dụng, không phải option JVM. | Đặt `-D` trước main class. |
| `mvn -Dapp.mode=qa` không đổi chế độ JVM | Hai lệnh hoạt động trong hai process khác nhau. | Tạo cầu nối nếu cần hoặc truyền runtime settings riêng. |
| Resource file nguồn vẫn chứa placeholder | Filtering tạo bản sao output, không sửa file nguồn. | Xem `target/classes` và nội dung JAR. |
| Secret bị lộ trong JAR | Build đã nhúng secret vào resource. | Thu hồi/rotate secret và thay pipeline để cấp tại runtime. |
| JAR khác nhau dù cùng tọa độ | Khác build profile, dependency hoặc môi trường build. | Cố định quy trình release, kiểm tra provenance/checksum. |
| File runtime config thay đổi nhưng JVM không cập nhật | Chương trình chỉ đọc tại startup, không có hot reload. | Restart hoặc triển khai refresh mechanism được kiểm chứng. |
| Chạy Java không tìm thấy resource | Resource không được đóng gói hoặc truy cập filesystem path của source. | Kiểm tra `jar tf` và dùng classpath stream. |

Khi gặp lỗi, đừng sửa ngẫu nhiên cả POM và JVM flags. Hãy truy theo chiều:

~~~text
Giá trị không đúng
     │
     ├─ Nằm trong artifact?
     │    └─ Kiểm tra Maven profile, filtering, plugin, target/classes, JAR.
     │
     └─ Được đọc khi ứng dụng chạy?
          └─ Kiểm tra JVM -D, env vars, file ngoài, precedence, process.
~~~

Đây là cách tìm đúng **thời điểm cấu hình** và tránh xử lý sai lớp.

## 15. Bài tập tự đánh giá

1. Tạo `build-runtime-demo` với POM, `App.java` và `build-info.properties` đúng ví dụ.
2. Chạy `mvn -Pdev clean package`, xác nhận `target/classes/build-info.properties` chứa `build.channel=dev`.
3. Chạy `java -Dapp.mode=local -cp target/build-runtime-demo-1.0-SNAPSHOT.jar com.example.App`; kiểm tra hai dòng stdout.
4. Không rebuild, đổi sang `-Dapp.mode=staging` khi chạy Java. Giải thích vì sao Build channel không đổi.
5. Chạy `mvn -Pprod clean package`, sau đó Java với `-Dapp.mode=local`. Giải thích vì sao Build channel đổi thành prod nhưng Runtime mode vẫn local.
6. Dùng `APP_MODE=cloud` mà không truyền JVM `-Dapp.mode`; chứng minh thứ tự ưu tiên do Java code quy định.
7. Chạy `mvn -Pprod help:evaluate -Dexpression=build.channel -q -DforceStdout` và kiểm tra resource đã được lọc.
8. Thử `java -cp ... com.example.App -Dapp.mode=qa`, giải thích vì sao cách viết sau main class không tự tạo system property.
9. Phân loại các tham số: JDK target, dependency version, database host, API password, timeout và build commit vào build-time/runtime, giải thích lý do.

**Câu hỏi tổng kết:** `mvn -Pprod` có tự chọn Spring profile prod không? `mvn -Dfoo=bar` có tự truyền `-Dfoo=bar` cho JVM lần chạy sau không? Khi nào cần build lại? Tại sao nên giữ secret ngoài JAR? Thay runtime config có nhất thiết cập nhật ngay trong process đã chạy không?

### Ghi nhớ

**Build time quyết định artifact được tạo như thế nào; runtime quyết định artifact hoạt động ra sao trong môi trường triển khai.** Profile và user property của Maven phục vụ quá trình build; system properties, environment variables và external files chỉ ảnh hưởng tới ứng dụng khi chương trình/framework thực sự đọc chúng.

Với từng tham số, hãy tài liệu hóa **nguồn giá trị, thứ tự ưu tiên, thời điểm đọc, mức độ nhạy cảm và yêu cầu rebuild/restart**. Làm rõ những điều này quan trọng hơn việc đặt tên cả Maven profile lẫn runtime mode giống nhau.

## Tài liệu chính thức

- Apache Maven — Introduction to Build Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Maven Help Plugin — Active Profiles: https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html
- Java SE 17 — System properties and environment: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
