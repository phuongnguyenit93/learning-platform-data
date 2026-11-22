# Truyền cấu hình môi trường cho kiểm thử tích hợp trong Maven

## 1. Mục tiêu: kiểm thử đúng môi trường, không hardcode và không lộ bí mật

**Kiểm thử tích hợp (integration testing)** kiểm tra cách nhiều thành phần của hệ thống phối hợp với nhau: ứng dụng với HTTP API, cơ sở dữ liệu, hàng đợi, filesystem, service giả lập hoặc môi trường CI. Khác với unit test chỉ thử một hàm thuần, integration test thường cần biết **endpoint, database URL, profile/môi trường, timeout, feature flags và đôi khi credentials**.

Trong Maven, cấu hình này có thể đến từ nhiều nơi: `pom.xml`, parent POM, Maven profiles, CLI `-D`, environment variables của shell/CI, settings/secret manager và cấu hình của **Maven Failsafe Plugin**. Nếu không phân biệt các kênh, cùng test có thể pass trên laptop nhưng fail ở CI hoặc kết nối nhầm môi trường.

Bài học giúp trả lời:

1. **Failsafe chạy integration tests ở phase nào và vì sao nên dùng `mvn verify`?**
2. **Maven property**, **Java system property** và **OS environment variable** khác nhau ra sao?
3. Khi nào dùng `<systemPropertyVariables>`, khi nào dùng `<environmentVariables>`?
4. Cách map CLI `-D`, Maven profiles và CI environment vào JVM kiểm thử mà không hardcode?
5. Khi JVM test được fork, những giá trị nào thực sự được truyền vào?
6. Làm thế nào tránh lộ tokens trong POM, logs và test reports?
7. Cách kiểm thử một cấu hình từ Maven vào test process bằng project Java 17 + JUnit 5 **chạy được và có stdout dự kiến**.
8. Khi test cần database/service thật, phải quản lý startup/cleanup, ports và isolation như thế nào?

**Nguyên tắc cốt lõi:** test phải nhận **cấu hình có thể kiểm chứng**, được cấp đúng phạm vi, có giá trị mặc định an toàn khi hợp lý và **fail rõ ràng** khi thiếu đầu vào bắt buộc. Không được xem việc build báo xanh là đủ nếu test bị skip hoặc kết nối nhầm hệ thống.

## 2. Phân biệt unit test và integration test trong Maven

Hai plugin quen thuộc:

| Plugin | Mục đích điển hình | Phase tương ứng |
| --- | --- | --- |
| **Maven Surefire Plugin** | Unit tests, test classes theo naming convention như `AppConfigTest` | `test` |
| **Maven Failsafe Plugin** | Integration tests, thường có tên `AppConfigIT`, `ITDatabase` hoặc `DatabaseITCase` | `integration-test` và `verify` |

Trong `jar` packaging, Surefire thường đã có default binding cho phase `test`; **Failsafe thường cần được khai báo thêm execution** với hai goals `integration-test` và `verify`. Các tên file của Failsafe mặc định bao gồm họ bắt đầu bằng `IT`, kết thúc bằng `IT`, hoặc kết thúc bằng `ITCase`. Không nhất thiết phải tạo thư mục test source riêng chỉ vì đó là integration test.

Ví dụ cấu trúc project:

~~~text
it-environment-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/it/AppConfig.java
    └── test/java/com/example/it/
        ├── AppConfigTest.java
        └── AppConfigIT.java
~~~

- `AppConfigTest` là **unit test** được Surefire phát hiện.
- `AppConfigIT` là **integration test** được Failsafe phát hiện.
- Cả hai nằm trong `src/test/java`, đều được compile ở `test-compile`.
- Việc phân loại mặc định chủ yếu đến từ **naming convention và plugin configuration**, không phải một kiểu Java class đặc biệt.

**Tên `*IT` không tự làm test chạy** nếu POM chưa gắn Failsafe goals, plugin bị skip hoặc lifecycle chưa tới phase tương ứng.

## 3. Vì sao `mvn verify` quan trọng hơn gọi riêng `integration-test`?

Lifecycle Maven có các phase liên quan theo thứ tự:

~~~text
validate
   -> compile
   -> test-compile
   -> test
   -> package
   -> pre-integration-test
   -> integration-test
   -> post-integration-test
   -> verify
   -> install
   -> deploy
~~~

Đây là sơ đồ rút gọn, không liệt kê mọi phase trung gian. Ý nghĩa từng phase cuối:

- **pre-integration-test:** có thể chuẩn bị server, database, container hoặc tài nguyên cần cho integration test.
- **integration-test:** Failsafe thực thi tests và ghi kết quả/tổng hợp.
- **post-integration-test:** có thể dừng service, giải phóng tài nguyên, dọn môi trường.
- **verify:** Failsafe kiểm tra kết quả integration test, và Maven đánh dấu build thất bại nếu test fail.

Failsafe được thiết kế để **trì hoãn việc kết luận test assertion failure** cho tới goal `failsafe:verify`, giúp lifecycle có cơ hội chạy `post-integration-test` để dọn tài nguyên đã khởi động. Do đó **không nên dùng `mvn integration-test` như tiêu chí CI pass/fail hoàn chỉnh**, vì bạn có thể bỏ qua bước cleanup và verification.

Lệnh tiêu chuẩn:

~~~bash
mvn -B clean verify
~~~

Nếu build có `pre-integration-test` khởi động một server hoặc container, lệnh trên còn bảo đảm lifecycle **đi qua `post-integration-test`**. Lưu ý: không phải mọi lỗi hạ tầng xảy ra trước đó đều cho phép cleanup diễn ra đầy đủ; với tài nguyên đắt tiền, cần cơ chế cleanup ở CI hoặc hệ thống provision ngoài Maven nữa.

**Không chạy `mvn integration-test` để chứng minh integration tests đều đỗ.** Kiểm tra báo cáo Failsafe và kết quả của `verify`.

## 4. Ba kênh cấu hình: Maven property, Java system property, OS environment

### 4.1. Maven property

Một property trong POM:

~~~xml
<properties>
    <it.stage>local</it.stage>
    <it.serviceUrl>http://127.0.0.1:18080</it.serviceUrl>
    <it.timeoutMillis>2500</it.timeoutMillis>
</properties>
~~~

Maven dùng giá trị để nội suy các plugin parameters qua cú pháp `${it.stage}`, `${it.serviceUrl}`, `${it.timeoutMillis}`. CLI có thể đặt/ghi đè Maven user property:

~~~bash
mvn -Dit.stage=ci -Dit.timeoutMillis=4000 verify
~~~

Đặt `-D` **không tự tạo OS environment variable**. Một số plugin còn có cơ chế chuyển Maven user properties thành Java system properties trong test JVM; nhưng đó là **chính sách cụ thể của test plugin**, không phải quy luật cho mọi process do Maven khởi động.

### 4.2. Java system property

Trong Java test hoặc ứng dụng:

~~~java
String url = System.getProperty("it.serviceUrl");
~~~

Java system property có thể được cung cấp bằng JVM flag `-Dit.serviceUrl=...`, hoặc được Surefire/Failsafe đưa vào test JVM từ POM. Đây là không gian **properties của Java process**, khác OS environment.

### 4.3. OS environment variable

Trong Java:

~~~java
String stage = System.getenv("IT_STAGE");
~~~

Giá trị có thể đến từ shell/CI hoặc `<environmentVariables>` của Failsafe. Java `System.getenv` và `System.getProperty` là hai API khác nhau; **đừng mong `System.getenv("IT_STAGE")` nhận giá trị từ `-Dit.stage=ci` nếu không có bước mapping**.

### 4.4. Bảng so sánh

| Nguồn | Cách khai báo/truyền | Đọc trong test JVM | Lưu ý |
| --- | --- | --- | --- |
| Maven property | `<it.stage>local</it.stage>` | Không tự là env var | Dùng để nội suy POM và plugin config |
| Maven CLI property | `mvn -Dit.stage=ci verify` | Có thể được Failsafe promote thành JVM system property | Phụ thuộc plugin/version và property precedence |
| Failsafe `systemPropertyVariables` | `<it.serviceUrl>...</it.serviceUrl>` | `System.getProperty("it.serviceUrl")` | Giá trị được truyền vào test provider/JVM |
| Failsafe `environmentVariables` | `<IT_STAGE>...</IT_STAGE>` | `System.getenv("IT_STAGE")` | Có hiệu lực trên forked test process |
| CI environment | `IT_API_TOKEN` | `System.getenv("IT_API_TOKEN")` nếu được kế thừa | Không hardcode/công bố value |
| Failsafe `argLine` | `-Xmx512m`, JVM `-D...` | JVM process options/system props | Không thay thế env variables |
| Test method parameter | `@ValueSource` hoặc JUnit parameters | Giá trị do test provider cấp | Không phải Maven/OS environment |

**Định nghĩa rõ đường đi từ nguồn đến consumer** trước khi nói “truyền biến môi trường”. Nếu chương trình dùng `System.getenv`, cần environmental value; nếu dùng `System.getProperty`, cần Java property.

## 5. Cấu hình Failsafe: systemPropertyVariables và environmentVariables

Một mảnh cấu hình cơ bản:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <forkCount>1</forkCount>
        <environmentVariables>
            <IT_STAGE>${it.stage}</IT_STAGE>
        </environmentVariables>
        <systemPropertyVariables>
            <it.serviceUrl>${it.serviceUrl}</it.serviceUrl>
            <it.timeoutMillis>${it.timeoutMillis}</it.timeoutMillis>
            <it.expectedStage>${it.stage}</it.expectedStage>
        </systemPropertyVariables>
    </configuration>
    <executions>
        <execution>
            <id>run-integration-tests</id>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

**Đây là mảnh plugin**, phải đặt trong `<build><plugins>` của một POM hợp lệ. Phần thực hành sau sẽ có POM hoàn chỉnh.

Cách hoạt động:

1. Maven dựng effective POM và xác định `it.stage`, `it.serviceUrl` và `it.timeoutMillis`.
2. Failsafe chuẩn bị test provider và **forked JVM** cho tests.
3. `IT_STAGE` được đưa vào **environment** của JVM kiểm thử.
4. `it.serviceUrl`, `it.timeoutMillis`, `it.expectedStage` được đưa vào **Java system properties** của JVM kiểm thử.
5. Test đọc qua `System.getenv` và `System.getProperty`.
6. `failsafe:integration-test` ghi kết quả; `failsafe:verify` xác thực kết quả sau phase cleanup.

### 5.1. Khi nào dùng systemPropertyVariables?

Dùng khi API của ứng dụng hoặc framework đọc `System.getProperty`, ví dụ tên endpoint, timeout hoặc feature flag **không nhạy cảm**. Java properties có thể được framework configuration sử dụng, nhưng không phải mọi framework đều có cùng thứ tự ưu tiên.

### 5.2. Khi nào dùng environmentVariables?

Dùng khi code đọc `System.getenv` hoặc framework bắt buộc env var. Ví dụ `IT_STAGE=local`, `DB_HOST`, `SERVICE_URL` hoặc những tên được tài liệu hóa.

Nếu CI đã có `IT_STAGE=ci` nhưng POM viết:

~~~xml
<environmentVariables>
    <IT_STAGE>${it.stage}</IT_STAGE>
</environmentVariables>
~~~

thì giá trị Failsafe đặt **có thể ghi đè env được child kế thừa**. Nếu property `it.stage` vẫn là `local`, test thấy `local`, không phải `ci`. Muốn đổi phải truyền `-Dit.stage=ci` hoặc thiết kế POM đọc CI env qua `${env.IT_STAGE}` với validation/default phù hợp.

### 5.3. Forked JVM là điều kiện quan trọng

`<environmentVariables>` tạo **environment cho forked test process**, không làm thay đổi environment toàn cục của Maven JVM. Với:

~~~xml
<forkCount>1</forkCount>
<reuseForks>true</reuseForks>
~~~

Failsafe thường dùng một JVM fork và có thể tái sử dụng nó cho nhiều test classes. Không đặt `<forkCount>0</forkCount>` rồi kỳ vọng Failsafe biến OS environment của Maven JVM thành giá trị mới cho các tests: chạy in-process có giới hạn khác và không cung cấp cùng isolation.

Forked JVM cũng có system properties riêng, working directory và memory limits riêng. Nếu integration tests cần native library hoặc Java module flags, phải cấu hình đúng **test JVM**, thường qua `argLine`/toolchains và plugin parameters.

## 6. Chính sách precedence: `-D` có thể thắng POM systemPropertyVariables

Failsafe 3.x hợp nhất Java system properties từ nhiều nguồn, gồm `argLine`, những cấu hình system properties trước đây, `systemPropertiesFile`, `systemPropertyVariables` và Maven session user properties.

Ở các Failsafe phiên bản hỗ trợ `promoteUserPropertiesToSystemProperties` (được giới thiệu từ 3.4.0, mặc định `true` trong tài liệu hiện hành), các Maven user properties thường truyền bằng CLI `-D` có thể **được thêm vào Java system properties của test provider với ưu tiên cao**.

Điều này tạo bẫy:

~~~xml
<systemPropertyVariables>
    <it.timeoutMillis>2500</it.timeoutMillis>
</systemPropertyVariables>
~~~

Nhưng chạy:

~~~bash
mvn -Dit.timeoutMillis=4000 verify
~~~

thì test process có thể nhận **4000** do user properties được promote và có precedence lớn hơn. Đó là hành vi được chủ đích sử dụng khi cần CI override, không phải luôn là lỗi.

**Không cho rằng `argLine -D...` luôn thắng giá trị từ `systemPropertyVariables` hoặc CLI user property**. Hãy đọc thứ tự hợp nhất đúng version Failsafe bạn đang dùng. Một số JVM properties đặc biệt như `file.encoding` cần được đặt trước lúc JVM khởi động (qua `argLine`/cách khởi động), vì chúng có thể bị JVM cache khi bắt đầu.

Để giảm bất ngờ:

- Dùng tên property nhất quán, ví dụ `it.serviceUrl`, không đồng thời duy trì `service.url`, `serviceUrl`, `it.service_url`.
- Đặt defaults trong `<properties>`.
- Map tường minh vào Failsafe.
- Ghi lại nguồn override được phép (CLI, profile, CI).
- Dùng một test cấu hình nhỏ xác nhận **giá trị thực tế trong test JVM**.
- Không để một script vô tình truyền các `-D` trùng tên với cấu hình quan trọng.

## 7. Không nhầm cấu hình Failsafe với Surefire

Surefire và Failsafe có nhiều options giống nhau, nhưng **mỗi plugin có configuration riêng**. Nếu bạn chỉ đặt:

~~~xml
<plugin>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <environmentVariables>
            <IT_STAGE>ci</IT_STAGE>
        </environmentVariables>
    </configuration>
</plugin>
~~~

thì cấu hình đó phục vụ **Surefire tests**, không tự truyền vào những tests do **Failsafe** chạy. Tương tự, đặt property vào Failsafe không bảo đảm unit test ở phase `test` thấy nó.

Một số dự án muốn cả unit và integration tests nhận cùng config có thể cấu hình ở parent/pluginManagement hoặc khai báo rõ cho cả hai plugin. Tuy nhiên, **test unit tốt thường không cần endpoint thật hay credentials**; truyền môi trường integration vào tất cả unit tests có thể làm test thiếu isolation và chạy chậm.

### Tên test ảnh hưởng việc plugin nào chạy

- `AppConfigTest.java`: mặc định thường do Surefire chạy.
- `AppConfigIT.java`: mặc định thường do Failsafe chạy.
- `ITDatabase.java`: thường phù hợp pattern của Failsafe.
- `DatabaseITCase.java`: thường phù hợp pattern của Failsafe.

Nếu đổi tên `AppConfigIT` thành `AppConfigTest`, nó có thể chạy ở phase `test` mà **chưa có Failsafe environment**. Không dựa vào `@Test` của JUnit để suy luận plugin nào đang chạy; hãy kiểm tra báo cáo và plugin goals.

### Bài toán unit vs integration environment

Một cách tổ chức dễ kiểm soát:

- Unit tests chỉ dùng input/mocks và Java properties cố định trong test hoặc test fixtures.
- Integration tests dùng Failsafe với endpoint, stage, timeout đã map từ Maven/CI.
- Test cần service thật có explicit readiness check, isolation và cleanup.
- CI release chỉ chấp nhận `verify` thành công, không chấp nhận “tests bị skip nhưng build xanh”.

## 8. Profiles: local, CI, staging và sự phân biệt với runtime profile

Maven profile có thể thay đổi properties dùng cho integration tests. Ví dụ mảnh POM sau có thể được thêm **ngoài `<build>`**:

~~~xml
<profiles>
    <profile>
        <id>it-ci</id>
        <properties>
            <it.stage>ci</it.stage>
            <it.serviceUrl>http://127.0.0.1:18080</it.serviceUrl>
            <it.timeoutMillis>4000</it.timeoutMillis>
        </properties>
    </profile>
    <profile>
        <id>it-staging</id>
        <properties>
            <it.stage>staging</it.stage>
            <it.serviceUrl>https://staging.example.invalid</it.serviceUrl>
            <it.timeoutMillis>6000</it.timeoutMillis>
        </properties>
    </profile>
</profiles>
~~~

Kích hoạt:

~~~bash
mvn -Pit-ci clean verify
mvn -Pit-staging clean verify
~~~

`staging.example.invalid` là domain minh họa, **không phải một dịch vụ có thật**. Project demo không thực hiện kết nối mạng tới endpoint nên profile này có thể dùng để kiểm tra việc truyền cấu hình; còn một integration test thật sẽ cần endpoint đã được cấp phát và có thể truy cập.

**Maven profile không đồng nhất với application runtime profile.** Ví dụ `-Pit-ci` chỉ active Maven profile. Nó có thể tạo property hoặc env cho tests qua plugin configuration, nhưng không tự bật `spring.profiles.active=ci` hoặc `QUARKUS_PROFILE=ci` trừ khi bạn map đúng tên/cơ chế mà framework sử dụng.

### CI nên ưu tiên cấu hình rõ và an toàn

Một pipeline có thể chạy:

~~~bash
mvn -B -Pit-ci -Dit.serviceUrl=http://127.0.0.1:18080 clean verify
~~~

Các giá trị không nhạy cảm như stage/endpoint có thể ở POM/profile. **Không commit passwords, API tokens, private keys hoặc connection secrets vào POM/profile**.

Với cấu hình chứa secret, tham khảo phần bảo mật dưới đây; không dùng `-Dsecret=...` trên command line nếu có khả năng bị lộ qua process list, job logs hoặc Maven reports.

## 9. Project thực hành Java 17 hoàn chỉnh

Ví dụ kiểm thử **đường truyền cấu hình Maven → Failsafe → forked JVM → Java code**. Nó dùng một endpoint giả định để không phụ thuộc database/service bên ngoài. Đây là **integration smoke test của cấu hình và ranh giới JVM**, chưa phải một kiểm thử network/database thật. Phần 14 chỉ cách mở rộng cho service integration có provision/cleanup.

### 9.1. Cấu trúc thư mục

~~~text
it-environment-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/it/AppConfig.java
    └── test/
        └── java/com/example/it/
            ├── AppConfigTest.java
            └── AppConfigIT.java
~~~

Có một project Maven `packaging=jar`, **không cần parent**. Yêu cầu Maven 3.9+, JDK 17+, repository cho các plugins và JUnit 5.

### 9.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>it-environment-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>

        <it.stage>local</it.stage>
        <it.serviceUrl>http://127.0.0.1:18080</it.serviceUrl>
        <it.timeoutMillis>2500</it.timeoutMillis>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>

                    <environmentVariables>
                        <IT_STAGE>${it.stage}</IT_STAGE>
                    </environmentVariables>

                    <systemPropertyVariables>
                        <it.serviceUrl>${it.serviceUrl}</it.serviceUrl>
                        <it.timeoutMillis>${it.timeoutMillis}</it.timeoutMillis>
                        <it.expectedStage>${it.stage}</it.expectedStage>
                    </systemPropertyVariables>
                </configuration>
                <executions>
                    <execution>
                        <id>run-integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Các điểm không thể bỏ qua:**

- `maven.compiler.release=17`: bytecode/Java APIs của demo dùng Java 17.
- JUnit Jupiter là **test-scoped dependency**.
- Surefire 3.5.2 chạy unit test `AppConfigTest`.
- Failsafe 3.5.2 có goals `integration-test` và `verify`; goals có default phase phù hợp nên trong ví dụ **không cần ghi `<phase>` thủ công**.
- Failsafe dùng **forkCount=1** để environmental values áp dụng vào test JVM riêng.
- Child env `IT_STAGE` đến từ Maven property `it.stage`.
- Java properties `it.serviceUrl`, `it.timeoutMillis` và `it.expectedStage` được Failsafe đưa tới test JVM.
- `it.expectedStage` là một giá trị đối chứng: integration test có thể xác minh môi trường thực trong `System.getenv` trùng stage mà Maven mong đợi.
- Không có URL thật hoặc secret; endpoint loopback chỉ là dữ liệu cấu hình, demo **không gửi network request**.
- Chỉ cần gọi `mvn verify`, không thêm Failsafe goal trực tiếp vào CLI nếu đã bind trong lifecycle.

### 9.3. AppConfig.java: tiêu thụ cấu hình bằng hai Java APIs

Tạo file `src/main/java/com/example/it/AppConfig.java`:

~~~java
package com.example.it;

import java.net.URI;
import java.util.Set;

public final class AppConfig {
    private static final Set<String> ALLOWED_STAGES =
            Set.of("local", "ci", "staging");

    private AppConfig() {
    }

    public static String stage() {
        String value = System.getenv("IT_STAGE");
        if (value == null || !ALLOWED_STAGES.contains(value)) {
            throw new IllegalStateException(
                    "IT_STAGE must be local, ci or staging");
        }
        return value;
    }

    public static URI serviceUrl() {
        String raw = System.getProperty("it.serviceUrl");

        if (raw == null || raw.isBlank()) {
            throw new IllegalStateException(
                    "Missing Java property it.serviceUrl");
        }

        URI uri;
        try {
            uri = URI.create(raw);
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException(
                    "Invalid it.serviceUrl", ex);
        }

        String scheme = uri.getScheme();
        if (uri.getHost() == null
                || scheme == null
                || !(scheme.equals("http") || scheme.equals("https"))) {
            throw new IllegalStateException(
                    "it.serviceUrl must be HTTP(S) URL with host");
        }

        return uri;
    }

    public static int parseTimeoutMillis(String raw) {
        final int timeout;
        try {
            timeout = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "it.timeoutMillis must be integer", ex);
        }

        if (timeout < 1 || timeout > 60000) {
            throw new IllegalArgumentException(
                    "it.timeoutMillis must be from 1 to 60000");
        }

        return timeout;
    }

    public static int timeoutMillis() {
        return parseTimeoutMillis(
                System.getProperty("it.timeoutMillis"));
    }

    public static String summary() {
        return "stage=" + stage()
                + ";url=" + serviceUrl()
                + ";timeoutMs=" + timeoutMillis();
    }

    public static void main(String[] args) {
        System.out.println(summary());
    }
}
~~~

**Cách class hoạt động:**

1. `System.getenv("IT_STAGE")` đọc OS environment của **process đang chạy AppConfig**, không đọc Maven POM.
2. `System.getProperty("it.serviceUrl")` đọc Java property của process.
3. `URI.create(...)` phân tích URL; code chỉ chấp nhận `http` hoặc `https` và host không rỗng.
4. `parseTimeoutMillis` chấp nhận số nguyên trong khoảng 1 đến 60000, từ chối giá trị lỗi/số âm/quá lớn.
5. `summary()` kết hợp stage, URL và timeout để integration test xác minh.
6. `main` cho phép chạy độc lập với cấu hình rõ ràng.
7. Không có secrets trong output; **không áp dụng mẫu log trực tiếp này cho password/token**.

Không khai báo Java global static cache cho cấu hình trong ví dụ, để `System.getProperty` và `System.getenv` được đọc khi method được gọi. Với ứng dụng thật, một số frameworks đọc và cache config ở lúc khởi tạo; khi đó thay đổi property sau bootstrap có thể không còn tác dụng.

### 9.4. AppConfigTest.java: unit test không phụ thuộc môi trường

Tạo `src/test/java/com/example/it/AppConfigTest.java`:

~~~java
package com.example.it;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppConfigTest {

    @Test
    void parsesValidTimeout() {
        assertEquals(2500, AppConfig.parseTimeoutMillis("2500"));
    }

    @Test
    void rejectsInvalidTimeout() {
        assertThrows(IllegalArgumentException.class,
                () -> AppConfig.parseTimeoutMillis("0"));
        assertThrows(IllegalArgumentException.class,
                () -> AppConfig.parseTimeoutMillis("abc"));
    }
}
~~~

Unit test **không truy cập `IT_STAGE` hoặc service URL**. Nó có thể chạy riêng bằng Surefire ở phase `test` mà không cần Failsafe environment.

### 9.5. AppConfigIT.java: kiểm tra giá trị đã truyền qua forked JVM

Tạo `src/test/java/com/example/it/AppConfigIT.java`:

~~~java
package com.example.it;

import java.net.URI;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AppConfigIT {

    @Test
    void receivesConfigurationFromMavenFailsafe() {
        String expectedStage =
                System.getProperty("it.expectedStage");

        assertTrue(expectedStage != null
                && Set.of("local", "ci", "staging")
                        .contains(expectedStage));

        assertEquals(expectedStage, AppConfig.stage());

        URI expectedUri = URI.create(
                System.getProperty("it.serviceUrl"));

        assertEquals(expectedUri, AppConfig.serviceUrl());

        int expectedTimeout = Integer.parseInt(
                System.getProperty("it.timeoutMillis"));

        assertEquals(expectedTimeout, AppConfig.timeoutMillis());
        assertTrue(AppConfig.timeoutMillis() > 0);

        System.out.println("IT_CONFIG " + AppConfig.summary());
    }
}
~~~

Test này không mở HTTP connection. Nó xác minh **đường đi cấu hình vào forked JVM** và logic đọc config của application.

Khi default properties được sử dụng, dòng stdout do test in là:

~~~text
IT_CONFIG stage=local;url=http://127.0.0.1:18080;timeoutMs=2500
~~~

Tùy Failsafe report/output routing, dòng này có thể xuất hiện trong terminal hoặc ở report files, không bảo đảm terminal chỉ in đúng một dòng trên.

Vì class tên `AppConfigIT`, nó được Failsafe mặc định chọn. Nếu developer đổi tên thành `AppConfigTest`, Surefire có thể chạy class ở phase `test` **trước lúc Failsafe env được cấp**, dẫn đến lỗi. Đừng bỏ qua naming convention.

### 9.6. Chạy build và xác minh reports

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -version
mvn -B clean verify
~~~

Dự kiến khi JDK/Maven/dependencies tương thích:

- Surefire chạy **2 unit tests** trong `AppConfigTest`.
- Failsafe chạy **1 integration test** trong `AppConfigIT`.
- `failsafe:verify` kiểm tra kết quả integration test.
- Maven kết thúc với **BUILD SUCCESS** nếu tất cả checks qua.
- Reports xuất hiện trong `target/surefire-reports/` và `target/failsafe-reports/`.

Các tên tệp reports điển hình:

~~~text
target/
├── surefire-reports/
│   └── com.example.it.AppConfigTest.txt
└── failsafe-reports/
    ├── com.example.it.AppConfigIT.txt
    └── failsafe-summary.xml
~~~

Đây là **những report paths tiêu biểu**, không liệt kê mọi file XML/log có thể phát sinh.

Để kiểm chứng Java process độc lập với Maven/Failsafe, trên Bash:

~~~bash
IT_STAGE=local java -Dit.serviceUrl=http://127.0.0.1:18080 -Dit.timeoutMillis=2500 -cp target/classes com.example.it.AppConfig
~~~

Khi project đã compile, **stdout chính xác** của lệnh này:

~~~text
stage=local;url=http://127.0.0.1:18080;timeoutMs=2500
~~~

Trên Windows PowerShell, có thể đặt `IT_STAGE` trong shell hiện hành rồi chạy:

~~~powershell
$env:IT_STAGE = "local"
java -Dit.serviceUrl=http://127.0.0.1:18080 -Dit.timeoutMillis=2500 -cp target/classes com.example.it.AppConfig
~~~

Lưu ý gán `$env:IT_STAGE` làm thay đổi environment của **PowerShell session** cho các lệnh sau; hãy khôi phục giá trị trước đó nếu dùng chung terminal. Khác với Failsafe `environmentVariables`, thao tác PowerShell này không tự giới hạn cho một lần forked test.

### 9.7. Override qua CLI cho chế độ CI

~~~bash
mvn -B -Dit.stage=ci -Dit.timeoutMillis=4000 clean verify
~~~

Plugin nội suy:

~~~text
Maven user property it.stage=ci
     |
     +-- Failsafe environmentVariables
     |       -> IT_STAGE=ci
     |
     +-- Failsafe systemPropertyVariables
             -> it.expectedStage=ci

Maven user property it.timeoutMillis=4000
     |
     +-- Failsafe systemPropertyVariables
             -> it.timeoutMillis=4000
~~~

Integration test sẽ in dòng:

~~~text
IT_CONFIG stage=ci;url=http://127.0.0.1:18080;timeoutMs=4000
~~~

Tính chất quan trọng: override **không cần sửa code Java**, không cần commit một `pom.xml` mới, không cần gán environment của cả Maven JVM theo cách thủ công.

Nếu CLI truyền `-Dit.serviceUrl=https://...`, Failsafe sẽ nhận URL mới theo chính sách property interpolation/precedence. Demo không thực hiện HTTP request nên sự thay đổi URL chỉ thử cấu hình, không chứng minh endpoint hoạt động.

### 9.8. Thử lỗi có chủ đích

Thử một cấu hình stage không được chấp nhận:

~~~bash
mvn -B -Dit.stage=production clean verify
~~~

`AppConfigIT` yêu cầu stage thuộc `local`, `ci`, `staging`, nên test bị fail. **`failsafe:integration-test` ghi nhận failure, `failsafe:verify` làm build fail**. Không dùng `mvn integration-test` riêng để kết luận vì nó không hoàn tất phase verify.

Thử timeout sai:

~~~bash
mvn -B -Dit.timeoutMillis=0 clean verify
~~~

`AppConfig.parseTimeoutMillis` từ chối 0. Test không thể pass nếu logic đọc cấu hình đã được thực thi đúng.

**Không dùng `-DtestFailureIgnore=true` hay skip flags để biến lỗi cấu hình thành build xanh** trong pipeline release.

## 10. Tại sao test có thể không nhận được biến dù CI đã đặt?

Những nguyên nhân thường gặp:

1. **CI đặt OS env khác tên** (ví dụ `APP_ENV`, trong khi test đọc `IT_STAGE`).
2. POM `environmentVariables` đặt `IT_STAGE=${it.stage}` với `it.stage=local`, ghi đè env `IT_STAGE=ci` được kế thừa.
3. Test chạy qua **Surefire** chứ không phải Failsafe do tên `*Test`.
4. Failsafe có `forkCount=0`, không có forked environment như cấu hình mong đợi.
5. Test chạy trực tiếp từ IDE bằng JUnit runner, **không có Failsafe plugin** để inject config.
6. Test code đọc **`System.getProperty`** nhưng giá trị được đặt ở **environment**, hoặc ngược lại.
7. Property từ `-D` không được map tới tên mà test thực sự đọc.
8. Active Maven profile không đúng hoặc profile bị override bởi parent/settings/CLI.
9. OS case sensitivity: trên Linux `IT_STAGE` khác `it_stage`; không dùng tên mơ hồ.
10. Process fork được tái sử dụng, framework đã cache config từ lúc bootstrap.
11. CI wrapper hoặc container không forward environment như mong đợi.
12. Parallel jobs chia sẻ cổng/file hoặc một service đang chạy từ job khác.

Cách tiếp cận: in **tên khóa, nguồn cấu hình và giá trị không nhạy cảm** để xác nhận đường đi, nhưng **không in secrets**. Dùng một smoke test kiểu `AppConfigIT` để chặn build trước khi gọi database hay API thật.

## 11. `argLine`, forked test process và Java options

Failsafe có thể cấu hình JVM args, chẳng hạn:

~~~xml
<configuration>
    <forkCount>1</forkCount>
    <argLine>-Xmx512m -Dapp.feature=it</argLine>
</configuration>
~~~

Ở đây:

- `-Xmx512m`: giới hạn heap của **forked test JVM**.
- `-Dapp.feature=it`: Java system property được đặt **khi JVM fork khởi động**.
- Đây không phải OS environment variable; `System.getenv("app.feature")` không đọc được nó.
- Nếu `forkCount=0`, các cơ chế `argLine` dành cho forked JVM không có cùng hiệu lực.
- Với một số Java system properties được JVM xử lý rất sớm (như encoding), cấu hình lúc fork khởi động có ý nghĩa khác với gọi `System.setProperty` sau đó.

**Không cần dùng `argLine` cho mọi giá trị cấu hình thông thường.** Khi không cần JVM flags đặc biệt, `systemPropertyVariables` rõ ràng và dễ review hơn. Nếu dùng JaCoCo, `argLine` có thể chứa phần agent options được plugin khác chuẩn bị; cần hợp nhất đúng để không vô tình bỏ instrumentation.

Đặc biệt chú ý: Maven `${argLine}` và Surefire/Failsafe late property evaluation có cú pháp riêng; đừng thay đổi từ một tutorial khác nếu chưa kiểm tra cấu hình JaCoCo của project thực tế.

## 12. Secrets và credentials: khác dữ liệu cấu hình thông thường

Một integration test thật có thể cần DB username/password, API key hoặc JWT. Những dữ liệu này **không được đối xử như `it.stage` hay `it.timeoutMillis`**.

### Điều không nên làm

~~~xml
<properties>
    <db.password>my-production-password</db.password>
</properties>
~~~

Không commit secret trong POM, test source, test fixtures, hoặc resource được đóng gói. Không để pipeline in secrets bằng:

~~~bash
mvn -Ddb.password=my-production-password verify
~~~

CLI arguments có thể bị lưu trong process listing, build logs, job history, test reports hoặc diagnostic tools. Việc `${env.DB_PASSWORD}` được nội suy vào plugin configuration cũng có thể bị lộ nếu effective POM/config/logs bị ghi đầy đủ.

### Phương án an toàn hơn

- Dùng **CI secret manager** hoặc secret injection mechanism có quyền hạn hẹp.
- Cấp credential riêng cho **test environment**, không dùng production secret.
- Nếu test cần đọc environment, cho phép forked JVM **kế thừa** đúng biến từ CI; không lưu giá trị trong POM.
- Hạn chế quyền network, database schema và token scopes.
- Xóa tài nguyên/test data sau test, kể cả khi test fail.
- Hạn chế log config dumps, debug outputs, test reports chứa system properties.
- Không gọi `System.out.println(System.getenv("IT_API_TOKEN"))`.
- Không nhúng secret vào generated artifacts, screenshots hoặc test attachments.
- Thu hồi/rotate secret nếu bị lộ.

Ví dụ trong test (mảnh code, không phải chương trình Java độc lập):

~~~java
String token = System.getenv("IT_API_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "Missing IT_API_TOKEN in integration-test environment");
}
// Dùng token qua client được cấu hình an toàn; không log token.
~~~

Nếu Failsafe chạy forked JVM và OS env có `IT_API_TOKEN`, token có thể được kế thừa. Chỉ khi cần override mới đưa vào `environmentVariables`, và nên tránh cách làm nào khiến secret hiện rõ trong effective POM hoặc build logs.

**Khi thiếu secret bắt buộc, nên fail test rõ ràng hoặc phân tách suite không yêu cầu credential**. Không nên mặc định skip tất cả integration tests rồi công bố build đã được xác minh với backend thật.

## 13. CI matrix và nhiều môi trường

Có nhiều cách cấp non-secret configuration:

| Môi trường | Stage | Service URL | Gợi ý |
| --- | --- | --- | --- |
| Local test | `local` | `http://127.0.0.1:18080` | Service giả lập hoặc local container |
| CI ephemeral | `ci` | URL service do CI provision | Cấp ở CI, dọn sau job |
| Shared staging | `staging` | URL staging được duyệt | Tránh ghi đè dữ liệu chung |
| Production | Không nên là target của suite integration mặc định | Hệ thống thật | Cần chính sách riêng nếu có smoke tests hạn chế |

Ví dụ CI script **không chứa secrets**:

~~~bash
mvn -B -Pit-ci \
  -Dit.stage=ci \
  -Dit.serviceUrl=http://127.0.0.1:18080 \
  -Dit.timeoutMillis=4000 \
  clean verify
~~~

Backslash cuối dòng ở đây là cú pháp **shell POSIX**. Trên Windows PowerShell, viết cùng lệnh một dòng hoặc dùng cách continuation tương ứng; không copy nguyên multiline shell khác OS rồi coi là lỗi Maven.

Nếu CI dùng multiple parallel jobs (Java 17/21, OS Linux/Windows, DB versions...), mỗi job phải có environment values và backend instance tương ứng. Đừng để cả hai jobs cùng sửa một schema `integration_test` chung hoặc cùng ghi một file tạm cố định.

### Không hardcode endpoint staging để “cho test có nơi chạy”

Nếu test thực sự gửi request, URL sai hoặc thiếu quyền có thể khiến suite vô tình tác động hệ thống không dành cho test. Với backend thật nên:
1. Chỉ cho phép host/URL theo allow-list.
2. Cấp credentials read-only hoặc scope test phù hợp.
3. Dùng unique namespace/data cho mỗi CI run.
4. Fail nếu endpoint không sẵn sàng, không chuyển sang production URL làm fallback.
5. Có timeout và cleanup có thể chạy độc lập khi job fail.

## 14. Mở rộng thành integration test HTTP/database thực sự

Demo ở phần 9 chỉ xác nhận **wiring cấu hình**. Một integration test đúng nghĩa đối với dịch vụ cần thực sự kiểm tra tương tác. Ví dụ một test HTTP có thể:

1. Đọc `it.serviceUrl` và `it.timeoutMillis`.
2. Dựng Java 17 `HttpClient` với timeout.
3. Gửi request đến một **endpoint test** đã được provision.
4. Assert HTTP status/body theo hợp đồng test.
5. Dọn dữ liệu đã tạo và kết thúc resource.

Một mảnh Java 17 minh họa ý tưởng (chỉ hoạt động khi có HTTP test service phù hợp, **không phải full test runnable của demo**):

~~~java
java.net.http.HttpClient client =
        java.net.http.HttpClient.newBuilder()
                .connectTimeout(java.time.Duration.ofMillis(
                        AppConfig.timeoutMillis()))
                .build();

java.net.http.HttpRequest request =
        java.net.http.HttpRequest.newBuilder(
                AppConfig.serviceUrl().resolve("/health"))
                .timeout(java.time.Duration.ofMillis(
                        AppConfig.timeoutMillis()))
                .GET()
                .build();

java.net.http.HttpResponse<String> response =
        client.send(request,
                java.net.http.HttpResponse.BodyHandlers.ofString());
~~~

Mảnh này cần nằm trong method có xử lý `IOException` và `InterruptedException`, thêm assertions về response status, và **endpoint test có `/health`**. Nó không được gọi trong project demo để tránh phụ thuộc network.

Với database:
- Tạo database/schema riêng cho từng suite hoặc job.
- Chạy migrations/fixtures trước tests.
- Truyền JDBC URL và credentials qua kênh cấu hình phù hợp.
- Chặn test chạy nhầm production.
- Rollback/cleanup dữ liệu; không chia sẻ state giữa các parallel tests.
- Không lưu connection string có secret trong logs.

Tùy dự án, **Testcontainers**, Docker Compose, Maven plugin khởi động server hoặc script CI có thể quản lý infrastructure. Nếu resource khởi động trong `pre-integration-test`, phải có cleanup ở `post-integration-test` và một cơ chế dự phòng khi build bị ngắt trước lúc cleanup.

## 15. Profiles, settings.xml và cấu hình nhiều module

Maven properties có thể đến từ:

- `pom.xml` của module.
- Parent POM, `dependencyManagement` và plugin configuration được kế thừa.
- Maven profiles active trong POM hoặc settings.
- Maven CLI `-D...`.
- Environment variables được tham chiếu qua `${env.NAME}`.
- Các thuộc tính Maven do CI/tooling cấp.

**settings.xml chủ yếu dành cho repository, mirrors, servers và profiles**, không phải nơi mặc định để lưu mọi cấu hình ứng dụng. Server credentials trong Maven settings phục vụ repository authentication; không tự trở thành credentials để integration test kết nối một ứng dụng khác.

Trong multi-module build, mỗi module có thể có Failsafe plugin và test suites khác nhau. Nếu parent đặt Failsafe execution trong `<build><plugins>`, child có thể **kế thừa và chạy tests** dù không tự khai báo execution. Nếu chỉ muốn quản lý plugin version/config, dùng `pluginManagement` có chủ đích; nếu muốn chạy IT tại module cụ thể, khai báo plugin ở module đó.

Một profile active ở parent có thể thay thuộc tính `it.stage` cho nhiều modules. Đừng giả định tên property global là đúng cho mọi service; tốt hơn dùng tên phân biệt module khi các endpoints khác nhau.

## 16. Reports và cách kiểm tra tests thật sự đã chạy

Sau `mvn clean verify`, xem:

~~~text
target/surefire-reports/
target/failsafe-reports/
target/failsafe-reports/failsafe-summary.xml
~~~

Báo cáo Failsafe có thể chứa số tests, failures, errors, skips và các stdout/stderr captured. Khi QA một pipeline:

1. Xác nhận **Failsafe `integration-test` goal** đã chạy.
2. Xác nhận số integration tests đúng kỳ vọng.
3. Xác nhận **`verify` goal** đã chạy và kết luận thành công.
4. Kiểm tra suite có bị skip không.
5. Kiểm tra không có hidden test failures bằng ignore flags.
6. Xem report của module cụ thể, không chỉ tổng log reactor.
7. Với test thật, kiểm tra endpoint/data/test fixtures là đúng môi trường.

**BUILD SUCCESS không chứng minh IT đã được chạy**, nếu POM không bind Failsafe hoặc pipeline đã skip. Tự động kiểm số tests và tình trạng reports sẽ tăng độ tin cậy hơn chỉ nhìn dòng màu xanh cuối log.

### Report directory không phải nơi cất secrets

JUnit XML reports và test diagnostics có thể ghi các Java system properties hoặc stdout/stderr tùy cấu hình. Không dùng chúng để in token/password; nên hạn chế quyền truy cập report artifacts và áp dụng redaction theo quy trình tổ chức.

## 17. Skip flags: phân biệt tạm bỏ qua với kiểm thử hoàn chỉnh

Một số lệnh hay gặp:

~~~bash
mvn -DskipITs clean verify
mvn -Dmaven.test.skip=true clean package
~~~

- `-DskipITs`: Failsafe hỗ trợ bỏ qua integration tests/verification tương ứng; **không phù hợp làm tiêu chí CI release hoàn chỉnh**.
- `-Dmaven.test.skip=true`: skip tests theo cơ chế Maven test plugins, có thể skip cả test compilation; dễ che lỗi Java tests.
- `-DskipTests`: thường được Surefire hỗ trợ để skip unit tests, nhưng Failsafe có semantics/parameter binding riêng; không dùng nó thay cho `skipITs` khi muốn quyết định chính xác IT.
- `-DtestFailureIgnore=true` hoặc `-Dmaven.test.failure.ignore=true` có thể làm pipeline không fail như mong đợi; tránh ở release gate.

**Đừng tự động đánh dấu integration testing đã PASS khi sử dụng skip flags.** Báo cáo phải phân biệt PASS, SKIPPED và NOT_RUN.

### Test theo yêu cầu

Khi cần chọn một test IT để debug, Failsafe hỗ trợ thuộc tính `it.test` trong các version hiện đại. Ví dụ:

~~~bash
mvn -B -Dit.test=AppConfigIT clean verify
~~~

Tuy nhiên naming, wildcard, inclusion/exclusion và provider behavior còn phụ thuộc plugin/JUnit version. Không thay đổi default suite selection trong CI release trừ khi mục đích đã rõ.

## 18. Failure modes khi cấu hình môi trường

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
| --- | --- | --- |
| Unit test pass, IT báo `IT_STAGE missing` | Chỉ cấu hình Surefire hoặc chạy IT ngoài Failsafe | Kiểm tra Failsafe execution, forkCount và env |
| IT nhận `local` thay vì `ci` | POM `<environmentVariables>` ghi đè env kế thừa | Truyền `-Dit.stage=ci` hoặc sửa mapping |
| `System.getenv` trả null nhưng `-D` đã đặt | Nhầm Maven property với OS env | Map Failsafe `environmentVariables` |
| `System.getProperty` trả null | Chỉ cấp environment variable, không cấp Java property | Dùng systemPropertyVariables/argLine phù hợp |
| `mvn test` không chạy IT | `test` phase chỉ chạy Surefire theo cấu hình thường gặp | Dùng `mvn verify` |
| `mvn integration-test` exit 0 dù test failed | Chưa chạy Failsafe verify | Dùng `mvn verify` |
| IT trống, không có tests | Tên test không khớp pattern hoặc plugin chưa bind | Kiểm tra AppConfigIT, Failsafe reports |
| CI báo xanh nhưng backend chưa được kiểm | IT bị skip hoặc chỉ chạy config smoke test | Kiểm số tests và loại assertions |
| Khi dùng `forkCount=0`, env không áp dụng | Test chạy in-process | Dùng forkCount lớn hơn 0 cho env injection |
| `-Dit.timeoutMillis=foo` làm test lỗi | Input bị parse/validate fail | Giữ fail-fast; sửa config CI |
| Một test thay System properties khiến test khác fail | Shared JVM state khi reuseForks | Tránh mutation hoặc isolate/restart fork |
| Fail chỉ trên Windows | Case sensitivity, path/quote, shell differences | Ghi config OS-neutral, kiểm tra logs |
| Parent profile làm module con dùng endpoint sai | Property global bị kế thừa/override | Dùng tên property riêng, xem effective POM |
| Shared staging bị xóa dữ liệu | IT thiếu namespace/cleanup isolation | Dùng fixtures riêng/least privilege |
| Token xuất hiện trong report | Test log secret hoặc provider capture props | Cắt logs/rotate token, dùng secret policy |
| IT test timeout không đúng | Sai hệ đơn vị, value rỗng, library override | Kiểm tra system properties và client config |
| Test gửi request production ngoài ý muốn | URL default không an toàn | Host allow-list, explicit stage, fail nếu production |
| Test chỉ pass trong IDE | IDE tự cấp env, Maven CLI không | So IntelliJ run configuration với Failsafe |
| Failsafe report từ lần trước đánh lừa | Không `clean`, stale reports/artifacts | Chạy clean verify và kiểm report mới |
| `-DskipTests` không skip đúng như tưởng | Surefire/Failsafe skip semantics khác | Dùng skipITs khi thực sự cần, kiểm log |

## 19. Quy trình debug có cấu trúc

**Bước 1 — Xác nhận Maven/JDK và plugin version**

~~~bash
mvn -version
java -version
~~~

Xác nhận Java chạy Maven và test JVM/toolchain nếu khác. Đừng chỉ tin `maven.compiler.release` là test JVM chắc chắn đúng Java runtime.

**Bước 2 — Xem effective POM và active profiles**

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

Tìm `maven-failsafe-plugin`, `forkCount`, `environmentVariables`, `systemPropertyVariables`, `argLine`, plugin executions và các property `it.*`. Với multi-module, xem module cụ thể.

**Bước 3 — Chạy clean verify và đọc reports**

~~~bash
mvn -B clean verify
~~~

Xem mục `target/failsafe-reports`. Đọc test case name, số tests/failures/errors/skips và message, không chỉ grep tổng dòng BUILD SUCCESS.

**Bước 4 — In giá trị không nhạy cảm từ test**

Dùng `AppConfigIT` để hiển thị stage, URL giả định và timeout. Không in user/password/token. Nếu test báo expected stage khác actual stage, xác định lại nguồn override.

**Bước 5 — Phân lập từng tầng**

- Maven property có đúng không?
- Plugin XML đã nội suy đúng không?
- JVM test có fork không?
- Test đọc getenv hay getProperty?
- Plugin nào thực sự chạy test?
- Framework có cache/override configuration không?
- Endpoint thật có đang được provision không?

**Bước 6 — Thử override có chủ đích**

~~~bash
mvn -B -Dit.stage=ci -Dit.timeoutMillis=4000 clean verify
~~~

Nếu test config smoke pass nhưng test HTTP/DB vẫn fail, chuyển sang kiểm tra DNS, ports, firewall, credentials, schema, fixtures, TLS và readiness của external service.

**Bước 7 — Khôi phục môi trường**

Dọn resources trong `post-integration-test` hoặc CI finally/after step. Không chạy lại test có side effects trên shared/prod system khi chưa xác minh scope và quyền.

## 20. Bài tập tự kiểm tra

**Câu 1.** Đặt `mvn -Dit.stage=ci verify` có tự tạo `System.getenv("IT_STAGE") == "ci"` không?

**Đáp:** Không. Cần mapping trong Failsafe `environmentVariables` hoặc kênh OS env khác. Trong POM demo, mapping đó đã có.

**Câu 2.** `systemPropertyVariables` và `environmentVariables` có cùng đối tượng nhận?

**Đáp:** Không. Một cái cung cấp Java system properties, một cái cung cấp OS environment variables cho forked test process.

**Câu 3.** Unit test tên `AppConfigTest` có mặc định được Failsafe chạy cùng `AppConfigIT` không?

**Đáp:** Thông thường không. Surefire chọn unit test; Failsafe chọn IT naming patterns. Có thể thay đổi bằng cấu hình includes/excludes.

**Câu 4.** Tại sao dùng `mvn verify` thay vì chỉ `mvn integration-test`?

**Đáp:** Verify đi qua cleanup và `failsafe:verify`, nơi test failures được kiểm tra để quyết định build thất bại.

**Câu 5.** CI có `IT_STAGE=ci` nhưng test thấy `local`, tại sao?

**Đáp:** Failsafe `environmentVariables` có thể ghi đè env kế thừa bằng Maven property `it.stage=local`. Cần điều chỉnh mapping hoặc override property rõ ràng.

**Câu 6.** `forkCount=0` có thích hợp nếu muốn inject một OS env mới chỉ vào test JVM?

**Đáp:** Không. Cần forked process để tạo environment riêng; dùng `forkCount>0`.

**Câu 7.** `-DskipITs` có chứng minh integration suite đã pass?

**Đáp:** Không. Nó skip IT; phải báo SKIPPED/NOT_RUN thay vì PASS.

**Câu 8.** Có nên commit password test DB vào `<properties>` nếu chỉ là staging?

**Đáp:** Không. Dùng secret management, quyền tối thiểu, tránh logs/reports.

**Câu 9.** Plugin Failsafe đã chạy nhưng không có test nào, khả năng nào cần xem trước?

**Đáp:** Naming convention/`includes`, plugin executions, active profiles, skip flags, reports và compiled test classes.

**Câu 10.** Một integration test chỉ xác minh `IT_STAGE` và URL được truyền có đủ kiểm tra database đang hoạt động?

**Đáp:** Không. Đó là config wiring smoke test; muốn kiểm tra database phải thực sự kết nối, thao tác/khẳng định dữ liệu và cleanup trên môi trường test.

**Câu 11.** Khi `AppConfig.summary()` in URL, có nên in nguyên JDBC URL chứa user/password?

**Đáp:** Không. Không log secrets; cần tách/redact sensitive information.

**Câu 12.** Nếu source và POM không đổi nhưng CI dùng profile khác, kết quả IT có thể thay đổi không?

**Đáp:** Có. Profile/env/CLI properties và external services là một phần đầu vào của integration testing.

## 21. Checklist triển khai trong CI

1. Chọn rõ **Surefire cho unit** và **Failsafe cho integration**, không dựa vào tên `@Test` để quyết định.
2. Pin Maven Compiler/Surefire/Failsafe/JUnit versions đã kiểm thử.
3. Bind cả `integration-test` và `verify` của Failsafe.
4. Dùng `mvn clean verify` cho quality gate IT.
5. Xác định tên test đúng pattern, ví dụ `AppConfigIT`.
6. Phân biệt Maven property, Java system property, OS environment.
7. Truyền `System.getProperty` bằng `systemPropertyVariables`/JVM args thích hợp.
8. Truyền `System.getenv` bằng OS env hoặc Failsafe `environmentVariables`.
9. Giữ `forkCount>0` nếu cần environment riêng trong test JVM.
10. Xác định precedences khi có CLI `-D` và profiles.
11. Không để POM ghi đè env CI mà không chủ đích.
12. Không hardcode credentials hoặc đưa secrets vào CLI/diagnostics.
13. Dùng per-job backend/schema/namespace và quyền hạn chế.
14. Có startup, readiness, teardown và cleanup dự phòng cho external services.
15. Dùng timeout có đơn vị rõ và không tự retry thao tác có side effects.
16. Kiểm tra reports, số tests thực chạy và status SKIPPED.
17. Không bỏ qua failure bằng `skipITs`, `testFailureIgnore` ở release gate.
18. Kiểm tra multi-module inheritance và active profiles.
19. Tránh test thay đổi system properties/env được share trong reusable forks.
20. Dùng test configuration smoke trước suite backend nặng.
21. Bảo đảm endpoint allow-list và chặn test chạy nhầm production.
22. Đưa vào release report những cấu hình không nhạy cảm cần tái hiện, không ghi secrets.

## Tài liệu tham khảo chính thức

- [Apache Maven Failsafe Plugin — Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/usage.html)
- [Apache Maven Failsafe Plugin — integration-test goal parameters](https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html)
- [Apache Maven Failsafe Plugin — verify goal parameters](https://maven.apache.org/surefire/maven-failsafe-plugin/verify-mojo.html)
- [Apache Maven Failsafe Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Failsafe Plugin — System Properties](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/system-properties.html)
- [Apache Maven Failsafe Plugin — Fork Options and Parallel Execution](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/fork-options-and-parallel-execution.html)
- [Apache Maven Surefire Plugin — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [JUnit 5 — User Guide](https://docs.junit.org/5.11.4/user-guide/)

