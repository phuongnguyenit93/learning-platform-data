# Tổ chức tệp nguồn, tài nguyên và mã kiểm thử

> Phạm vi: tổ chức một dự án Java hiện đại chạy trên JDK 27. Các ví dụ dùng quy ước nguồn phổ biến của Maven và Gradle; cấu trúc có thể điều chỉnh qua cấu hình build khi dự án có nhu cầu rõ ràng.

## 1. Vì sao phải tách mã nguồn, tài nguyên và mã kiểm thử?

Một chương trình Java thường gồm ba nhóm đầu vào có vòng đời khác nhau:

- **Mã nguồn** là các tệp `.java` được biên dịch thành bytecode. Chúng mô tả kiểu, hành vi và điểm vào của ứng dụng.
- **Tài nguyên** là dữ liệu được ứng dụng hoặc thư viện đọc khi chạy, chẳng hạn cấu hình mặc định, mẫu nội dung, thông điệp đa ngôn ngữ, schema, tệp SQL và metadata dịch vụ.
- **Mã kiểm thử** xác minh hành vi của mã nguồn. Test có thể cần dữ liệu riêng, thư viện riêng và cách chạy riêng với ứng dụng production.

Tách ba nhóm này giúp build tool biết phần nào được biên dịch, phần nào được đóng gói, phần nào chỉ tồn tại trong môi trường kiểm thử. Nhờ vậy, JAR phát hành không vô tình chứa test fixture hoặc phụ thuộc chỉ dành cho test; tài nguyên production được đưa vào artifact; và test có thể chạy lặp lại trên máy phát triển lẫn CI.

## 2. Cấu trúc thư mục chuẩn cho một dự án Java

Maven và Gradle đều hỗ trợ quy ước thư mục phổ biến sau:

```text
order-service/
├── pom.xml                         # hoặc build.gradle.kts
├── README.md
├── .gitignore
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   ├── module-info.java    # chỉ có khi dùng named module
│   │   │   └── com/acme/orders/
│   │   │       ├── OrderApplication.java
│   │   │       ├── api/
│   │   │       ├── domain/
│   │   │       ├── application/
│   │   │       └── infrastructure/
│   │   └── resources/
│   │       ├── application.properties
│   │       ├── config/
│   │       ├── templates/
│   │       └── META-INF/
│   └── test/
│       ├── java/
│       │   └── com/acme/orders/
│       │       ├── domain/
│       │       └── application/
│       └── resources/
│           └── fixtures/
└── target/                         # Maven tạo khi build
```

Với Gradle, thư mục đầu ra mặc định thường là `build/` thay cho `target/`. Không cần tạo sẵn các thư mục chưa dùng đến; build tool xử lý những source directory có tồn tại.

| Đường dẫn | Nội dung | Được đưa vào artifact production? |
| --- | --- | --- |
| `src/main/java` | Mã Java của ứng dụng hoặc thư viện | Có, sau khi biên dịch |
| `src/main/resources` | Tài nguyên cần khi ứng dụng chạy | Có, được sao chép vào output/JAR |
| `src/test/java` | Lớp kiểm thử | Không |
| `src/test/resources` | Fixture và tài nguyên chỉ dùng khi test | Không |
| `target/` hoặc `build/` | Bytecode, tài nguyên đã xử lý, báo cáo và artifact sinh ra | Là đầu ra build, không phải nguồn để sửa thủ công |

Maven gọi đây là *Standard Directory Layout*. Java Plugin của Gradle sử dụng hai source set mặc định là `main` và `test`, với các thư mục Java và resources tương ứng. Nếu cần cấu trúc khác, hãy khai báo rõ trong POM hoặc Gradle source sets để mọi máy build sử dụng cùng một quy tắc. (Xem tài liệu chính thức ở phần Nguồn.)

## 3. Tổ chức package và tệp Java

### 3.1. Đường dẫn phải khớp với package

Một tệp khai báo package:

```java
package com.acme.orders.domain;

public final class Order {
    // ...
}
```

nên nằm tại:

```text
src/main/java/com/acme/orders/domain/Order.java
```

Tên package viết thường, dùng tên miền đảo ngược của tổ chức hoặc một namespace ổn định mà nhóm kiểm soát. Tránh đặt lớp ứng dụng trong default package vì các lớp trong package có tên không thể được import từ package có tên và khó quản lý khi dự án lớn lên.

Đối với kiểu top-level public, tên tệp nên trùng với tên kiểu, ví dụ `Order.java` cho `public class Order`. Có thể đặt kiểu package-private hoặc kiểu phụ trợ nhỏ trong cùng tệp khi chúng thực sự gắn chặt với kiểu chính; không nên gom nhiều thành phần độc lập vào một tệp chỉ để giảm số lượng tệp.

### 3.2. Chọn ranh giới package theo trách nhiệm

Package là ranh giới tổ chức và truy cập ở cấp mã nguồn. Một số cách chia thường gặp:

- **Theo lớp kỹ thuật**: `api`, `application`, `domain`, `infrastructure`. Cách này phù hợp khi dự án có các lớp trách nhiệm rõ ràng và nhóm cần quy tắc phụ thuộc thống nhất.
- **Theo tính năng/nghiệp vụ**: `orders`, `customers`, `payments`, mỗi khu vực chứa các thành phần API, xử lý và persistence liên quan. Cách này giúp thay đổi một tính năng trong phạm vi gần nhau.
- **Kết hợp hai cách**: chia theo tính năng ở cấp cao, sau đó tách các lớp kỹ thuật bên trong tính năng khi số lượng mã đủ lớn.

Ví dụ một cấu trúc theo tính năng:

```text
com/acme/shop/
├── orders/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── customers/
│   ├── api/
│   ├── application/
│   └── domain/
└── payments/
    ├── application/
    └── domain/
```

Không có một cách chia package phù hợp cho mọi hệ thống. Hãy dùng tên phản ánh khái niệm nghiệp vụ hoặc trách nhiệm có thật; giữ các lớp thường thay đổi cùng nhau ở gần nhau; và tránh package chung chung như `misc`, `common` hoặc `utils` chứa mọi thứ không biết đặt ở đâu. Một package `common` chỉ nên tồn tại khi có một nhóm khái niệm dùng chung ổn định, có chủ sở hữu và API rõ ràng.

### 3.3. Giữ ranh giới phụ thuộc dễ hiểu

Ở một ứng dụng nhiều tầng, mã điều phối use case thường phụ thuộc vào mô hình nghiệp vụ và các abstraction cần thiết. Chi tiết lưu trữ, HTTP hoặc framework nên được giữ ở biên. Ví dụ, domain không nên cần import một controller web chỉ để biểu diễn một quy tắc tính giá.

Có thể kiểm soát ranh giới bằng quy ước package, kiểm tra kiến trúc tự động, hoặc Java Platform Module System (JPMS) khi hệ thống cần ranh giới module ở cấp runtime. Không nên tạo package hoặc module chỉ để phản ánh mọi thư mục vật lý; mỗi ranh giới cần có ý nghĩa về trách nhiệm, phụ thuộc hoặc triển khai.

## 4. Dự án nhiều module và Java Platform Module System

Từ góc nhìn build, **multi-project/multi-module build** là một nhóm project được quản lý chung bởi một build root. Mỗi module build thường có cấu hình và artifact riêng. Ví dụ:

```text
shop-platform/
├── pom.xml                 # parent POM
├── shop-domain/
│   ├── pom.xml
│   └── src/main/java/
├── shop-application/
│   ├── pom.xml
│   └── src/main/java/
└── shop-web/
    ├── pom.xml
    └── src/main/java/
```

Gradle multi-project build có cấu trúc tương tự với `settings.gradle.kts` ở root và các subproject. Mỗi module nên đại diện cho một đơn vị có trách nhiệm, dependency và cách kiểm thử có thể mô tả rõ ràng. Tránh chia module quá nhỏ khiến việc cấu hình, versioning và thay đổi liên module trở nên tốn kém.

Cần phân biệt module của build tool với **named module của JPMS**. Hai khái niệm có thể phối hợp nhưng không đồng nghĩa: một Maven module không tự động trở thành JPMS module. Một named module Java có module descriptor `module-info.java`, khai báo dependency bằng `requires`, API công khai bằng `exports`, và service bằng `uses`/`provides`.

Ví dụ descriptor tối giản:

```java
module com.acme.orders {
    requires java.net.http;

    exports com.acme.orders.api;
}
```

Khi build thành modular JAR, descriptor được biên dịch thành `module-info.class` ở gốc JAR. Khi chạy trên module path, runtime giải quyết dependency theo tên module và áp dụng quy tắc đóng gói của JPMS. Một JAR không có module descriptor vẫn có thể chạy trên class path; nó không trở thành explicit module chỉ vì nằm trong một thư mục tên là `module`.

Dùng JPMS khi hệ thống cần khai báo dependency rõ ràng, giới hạn package được truy cập hoặc cung cấp dịch vụ qua module. Với ứng dụng nhỏ hay thư viện chưa có nhu cầu đó, một cấu trúc package tốt cùng class path do build tool quản lý có thể đã đủ. Nếu dùng JPMS, hãy kiểm tra kỹ `exports`, `opens` và quyền truy cập resource; không mở toàn bộ package cho reflection nếu không có lý do.

## 5. Đặt và đọc tài nguyên

### 5.1. Tài nguyên production

Đặt dữ liệu tĩnh mà ứng dụng cần trong `src/main/resources`. Ví dụ:

```text
src/main/resources/
├── application.properties
├── config/
│   └── default-policy.json
├── templates/
│   └── order-confirmation.html
├── i18n/
│   ├── messages.properties
│   └── messages_vi.properties
└── META-INF/
    └── services/
        └── com.acme.orders.spi.PaymentProvider
```

Build tool sao chép nội dung resource vào output của source set và đưa vào JAR theo cấu trúc đường dẫn tương ứng. Vì vậy, `config/default-policy.json` được tra cứu bằng tên resource `config/default-policy.json`, không phải bằng đường dẫn tuyệt đối của thư mục dự án.

Dùng `META-INF/services/<fully-qualified-interface-name>` cho cấu hình provider của `ServiceLoader` khi triển khai theo cơ chế service provider trên class path. Với named module, khai báo provider trong `module-info.java` bằng `provides ... with ...` và khai báo điểm sử dụng bằng `uses` khi cần. Không tạo file service configuration theo cảm tính; hãy chọn cách khai báo tương ứng với cách đóng gói và triển khai.

### 5.2. Đọc resource qua API class loader

Một resource được đóng gói trong JAR không nhất thiết tồn tại như một tệp độc lập trên file system. Vì vậy, không nên ghép `user.dir` với đường dẫn tương đối rồi dùng `FileInputStream` để đọc resource mặc định của ứng dụng. Cách đó phụ thuộc thư mục làm việc và có thể chạy trên máy phát triển nhưng lỗi khi ứng dụng được chạy từ JAR.

Có thể dùng `Class.getResourceAsStream` để đọc resource gắn với class:

```java
package com.acme.orders;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class DefaultSettings {
    private DefaultSettings() {
    }

    public static Properties load() throws IOException {
        var properties = new Properties();

        try (InputStream input =
                     DefaultSettings.class.getResourceAsStream(
                             "/application.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing application.properties");
            }

            try (var reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {
                properties.load(reader);
            }
        }

        return properties;
    }
}
```

Hai quy tắc đường dẫn cần nhớ:

- Với `SomeClass.class.getResourceAsStream("/config/app.json")`, dấu `/` đầu tiên chỉ đường dẫn từ gốc resource.
- Với `SomeClass.class.getResourceAsStream("app.json")`, đường dẫn được tính tương đối với package của class đó.
- Với `SomeClass.class.getClassLoader().getResourceAsStream("config/app.json")`, tên resource không có dấu `/` ở đầu và được tính từ gốc class loader.

Nếu không tìm thấy resource, các API này có thể trả về `null`; hãy kiểm tra và báo lỗi có ngữ cảnh thay vì để lỗi null xuất hiện ở vị trí xa nơi đọc dữ liệu. Dùng try-with-resources để đóng stream. Ví dụ trên dùng `Properties.load(Reader)` với UTF-8 để xử lý nội dung Unicode; overload `Properties.load(InputStream)` có quy tắc đọc encoding riêng và không nên được dùng thay thế một cách vô thức cho tệp UTF-8.

Với named module, resource trong package chịu quy tắc encapsulation của JPMS. `Class.getResourceAsStream` có thể không truy cập được resource không phải class trong package chưa được mở cho module gọi. Hãy đặt resource ở vị trí phù hợp hoặc khai báo `opens` có phạm vi tối thiểu khi thật sự cần. Tài liệu Java SE 27 của `Class`, `ClassLoader` và `Module` là nguồn chuẩn cho quy tắc này.

### 5.3. Tách cấu hình mặc định khỏi cấu hình môi trường

Resource đóng gói thích hợp cho giá trị mặc định không nhạy cảm, schema và template. Những giá trị thay đổi theo môi trường triển khai như URL dịch vụ, giới hạn kết nối, feature flag hoặc thông tin xác thực nên được cung cấp qua cơ chế cấu hình runtime, biến môi trường hoặc hệ thống quản lý secret.

Không commit mật khẩu, token, private key hoặc dữ liệu production vào `src/main/resources`. Tệp được đóng gói trong JAR có thể được đọc bởi người nhận artifact. Nếu một cấu hình cần khác nhau giữa local, test, staging và production, hãy xác định rõ nguồn cấu hình và thứ tự ưu tiên; tránh tạo một bản JAR khác nhau cho mỗi môi trường nếu cùng artifact có thể được cấu hình lúc chạy.

Không dùng resource filtering để thay thế secret vào artifact. Nếu build có bước filtering, chỉ áp dụng cho placeholder không nhạy cảm và kiểm tra nội dung cuối cùng trong JAR.

## 6. Tổ chức mã kiểm thử và test fixture

### 6.1. Đặt test gần cấu trúc mã production

Test Java nằm trong `src/test/java`; tài nguyên chỉ dùng khi test nằm trong `src/test/resources`. Một quy ước dễ tìm là giữ package test tương ứng với package của mã production:

```text
src/
├── main/
│   ├── java/com/acme/orders/domain/PriceCalculator.java
│   └── resources/config/default-policy.json
└── test/
    ├── java/com/acme/orders/domain/PriceCalculatorTest.java
    └── resources/fixtures/prices.json
```

Test được biên dịch với test classpath, trong đó có output production và các dependency test. Test resources cũng được đưa vào test runtime classpath. Chúng không nên được đặt trong `src/main/resources`, vì như vậy dữ liệu dành riêng cho test có thể lọt vào artifact phát hành.

### 6.2. Viết test theo hành vi

Tên lớp test thường ghép tên thành phần với hậu tố `Test`; tên phương thức nêu điều kiện và kết quả mong đợi. Ví dụ với JUnit Jupiter:

```java
package com.acme.orders.domain;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PriceCalculatorTest {
    @Test
    void appliesDiscountToEligibleOrder() {
        var calculator = new PriceCalculator();

        var total = calculator.totalAfterDiscount(
                100, 10);

        assertEquals(90, total);
    }
}
```

Ví dụ chỉ minh họa cách tổ chức test; trong ứng dụng thực tế, kiểu tiền tệ nên dùng biểu diễn thập phân chính xác như `BigDecimal` cùng quy tắc scale/rounding đã được xác định trong nghiệp vụ.

Một test tốt xác minh hành vi quan sát được, có dữ liệu đầu vào rõ ràng và kết quả mong đợi. Tránh kiểm tra chi tiết private hoặc thứ tự gọi nội bộ nếu đó không phải hợp đồng của thành phần. Khi dùng test parameterized, có thể gom các trường hợp dữ liệu tương tự vào một test có nhiều input để giảm lặp mà vẫn giữ được tên từng trường hợp.

### 6.3. Dùng fixture và thư mục tạm đúng mục đích

Dữ liệu mẫu dùng chung cho test có thể được đặt trong `src/test/resources/fixtures`. Đọc fixture qua class loader tương tự resource production, nhưng neo vào class test:

```java
try (var input = PriceCalculatorTest.class
        .getResourceAsStream("/fixtures/prices.json")) {
    if (input == null) {
        throw new IllegalStateException("Missing test fixture");
    }
    // Parse and assert the fixture content.
}
```

Dữ liệu mà test tạo ra trong lúc chạy nên được ghi vào thư mục tạm do test framework cấp, ví dụ JUnit Jupiter `@TempDir`. Không ghi file test vào thư mục làm việc của repository hoặc dùng một đường dẫn tuyệt đối phụ thuộc máy cá nhân. Mỗi test nên tự chuẩn bị dữ liệu và dọn tài nguyên cần thiết, không dựa vào thứ tự thực thi hoặc trạng thái do test trước để lại.

Đối với fixture lớn, dữ liệu nhạy cảm hoặc dữ liệu phải tạo theo kịch bản, cân nhắc factory/builder hoặc bộ tạo dữ liệu thay vì lưu nhiều bản sao JSON/CSV khó đồng bộ. Fixture nên nhỏ, có tên mô tả và chỉ giữ các trường cần cho tình huống kiểm thử.

### 6.4. Phân biệt các cấp kiểm thử

| Loại test | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Unit test | Kiểm tra một lớp hoặc một quy tắc nghiệp vụ trong phạm vi nhỏ | Tính tổng đơn hàng, kiểm tra validation |
| Integration test | Kiểm tra tương tác giữa nhiều thành phần thật | Repository với database test, HTTP client với server thử nghiệm |
| Contract test | Kiểm tra hợp đồng giao tiếp giữa consumer và provider | Schema, status code và payload API |
| End-to-end test | Kiểm tra luồng quan trọng qua hệ thống gần với cách triển khai | Tạo đơn hàng từ API đến persistence và xác nhận kết quả |

Không cần biến mọi test thành end-to-end. Unit test nên chạy nhanh và ổn định; integration test cần tài nguyên bên ngoài được quản lý rõ; end-to-end test nên tập trung vào các luồng có giá trị cao vì chi phí và độ nhạy môi trường thường lớn hơn.

Nếu integration test cần classpath, dependency hoặc lifecycle khác unit test, hãy tách thành source set/task riêng. Gradle hỗ trợ khai báo source set bổ sung và task test tương ứng. Với Maven, cấu hình plugin kiểm thử phù hợp để phân biệt giai đoạn unit và integration; đừng giả định một thư mục tùy ý sẽ tự động được build tool chạy.

## 7. Để build tool quản lý source set và artifact

### 7.1. Maven

Maven nhận các thư mục chuẩn mà không cần cấu hình thêm. Build thường chạy qua Maven Wrapper của repository để nhóm và CI dùng cùng phiên bản Maven:

```bash
./mvnw test
./mvnw package
```

Trên Windows, dùng `mvnw.cmd`. Lệnh `test` chạy test được cấu hình cho giai đoạn test; `package` tiếp tục đóng gói artifact. Phiên bản Java đích nên được khai báo nhất quán trong cấu hình compiler, ví dụ thuộc tính `maven.compiler.release` đặt bằng `27`, và CI cần dùng JDK/toolchain phù hợp.

### 7.2. Gradle

Java Plugin định nghĩa source set `main` và `test`, các tác vụ biên dịch và xử lý resource tương ứng. Có thể chạy:

```bash
./gradlew test
./gradlew build
```

Trên Windows, dùng `gradlew.bat`. Với Kotlin DSL, có thể khai báo JDK toolchain như sau:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}
```

Cấu hình toolchain giúp build yêu cầu JDK phù hợp thay vì ngầm phụ thuộc JDK đầu tiên tìm thấy trong `PATH`. Hãy kiểm tra thêm cấu hình CI, IDE và các tác vụ chạy test để tránh biên dịch bằng một JDK nhưng thực thi bằng JDK khác.

Gradle cho phép tạo source set bổ sung khi có nhu cầu, ví dụ integration test hoặc mã benchmark. Source set có Java source, resources, compile classpath và runtime classpath riêng. Chỉ tạo thêm khi có khác biệt thực sự về dependency hoặc lifecycle; nếu không, quy ước `main`/`test` đơn giản sẽ dễ bảo trì hơn.

### 7.3. Mã nguồn sinh tự động

Một số dự án dùng annotation processor hoặc generator để tạo Java source. Đầu ra nên được đặt trong thư mục generated source do build tool quản lý, ví dụ dưới `target/generated-sources` hoặc `build/generated`, rồi đăng ký với source set tương ứng.

Không chỉnh sửa thủ công tệp sinh tự động vì lần build sau có thể ghi đè. Hãy sửa schema, template, annotation hoặc cấu hình đầu vào của generator. Chỉ commit generated source khi quy trình phát hành hoặc yêu cầu tái lập của dự án quy định rõ điều đó.

## 8. Đóng gói và xác minh resource trong JAR

Khi build artifact, lớp đã biên dịch và resource production được đặt trong JAR. Có thể kiểm tra nội dung archive bằng JDK 27:

```bash
jar --list --file target/order-service.jar
```

Với Gradle, thay đường dẫn bằng JAR nằm trong thư mục `build/libs`. Kiểm tra rằng:

- Các lớp production và resource cần thiết có mặt.
- Test class và test fixture không lọt vào JAR production.
- Không có file secret, log, dữ liệu máy cá nhân hoặc output build thừa.
- Đường dẫn resource bên trong JAR khớp với tên mà mã nguồn đang tra cứu.

Nếu artifact là modular JAR, có thể dùng `jar --describe-module --file path/to/app.jar` để kiểm tra module descriptor được nhận diện. Một modular JAR được đặt trên module path; nếu đặt trên class path, nó được xử lý như một JAR không modular. Chọn class path hay module path phải thống nhất với cách ứng dụng được build và khởi chạy.

## 9. Chạy một tệp Java độc lập trong giai đoạn thử nghiệm

JDK hiện đại hỗ trợ source-file mode, ví dụ:

```bash
java HelloWorld.java
```

Launcher biên dịch tệp nguồn trong bộ nhớ rồi chạy lớp được khai báo trong tệp. Chế độ này hữu ích cho ví dụ nhỏ, thử API, bài tập hoặc tiện ích ngắn không cần cấu trúc build đầy đủ. Khi chương trình phát triển thành ứng dụng có nhiều lớp, resource, dependency hoặc test, hãy chuyển sang một dự án có source set và build configuration rõ ràng. Source-file mode không thay thế quy trình quản lý dependency, test và đóng gói của Maven/Gradle.

## 10. Ví dụ áp dụng: dịch vụ quản lý đơn hàng

Một nhóm xây dựng dịch vụ quản lý đơn hàng có thể tổ chức như sau:

1. `Order`, `OrderLine` và các quy tắc tính tổng nằm trong package domain dưới `src/main/java`.
2. Use case tạo đơn hàng nằm trong package application và điều phối domain với các cổng cần thiết.
3. Adapter HTTP và persistence nằm ở package infrastructure hoặc module tương ứng.
4. `application.properties` chứa giá trị mặc định không nhạy cảm; endpoint database và secret được cung cấp từ môi trường triển khai.
5. Test cho quy tắc tính tổng nằm trong package test tương ứng. Fixture JSON dùng để kiểm tra import/export nằm trong `src/test/resources/fixtures`.
6. Test tích hợp repository chạy với database thử nghiệm được khởi tạo riêng, sau đó đóng tài nguyên khi kết thúc.
7. CI chạy test, đóng gói JAR, kiểm tra nội dung artifact và chạy smoke test trên đúng JDK 27 đã khai báo.

Khi thêm tính năng thanh toán, nhóm có thể tạo package hoặc module `payments` nếu ranh giới nghiệp vụ và phụ thuộc đủ độc lập. Không nên tách module chỉ vì có thêm vài lớp; hãy xem xét quyền sở hữu dữ liệu, API công khai, dependency và cách triển khai trước.

## 11. Checklist rà soát cấu trúc dự án

- [ ] Mã production, resource production, mã test và test fixture nằm trong source set phù hợp.
- [ ] Đường dẫn thư mục khớp với package; package có tên rõ ràng và không dùng default package.
- [ ] Tên tệp public top-level type nhất quán với tên kiểu.
- [ ] Package phản ánh tính năng hoặc trách nhiệm; dependency giữa các khu vực có hướng rõ ràng.
- [ ] Maven/Gradle dùng quy ước thư mục nhất quán hoặc khai báo source set tùy chỉnh rõ ràng.
- [ ] Resource được đọc qua class/module/class loader thay vì giả định nó là file trong working directory.
- [ ] Resource UTF-8 được đọc bằng API có chỉ định encoding phù hợp.
- [ ] Secret và cấu hình riêng từng môi trường không được đóng gói vào artifact.
- [ ] Test có dữ liệu riêng, độc lập với thứ tự chạy và không ghi vào thư mục máy cá nhân.
- [ ] Unit, integration, contract và end-to-end test được phân loại theo chi phí và mục tiêu.
- [ ] Generated source được quản lý bởi build tool và không bị chỉnh sửa thủ công.
- [ ] Build và test dùng toolchain JDK 27 nhất quán.
- [ ] JAR được kiểm tra để xác nhận resource cần thiết có mặt và test fixture/secret không bị đóng gói.
- [ ] Nếu dùng JPMS, module descriptor, exports, opens, requires và service declarations phản ánh đúng ranh giới cần thiết.

## 12. Nguồn tài liệu chính thức

- [Maven: Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html) — thư mục source, resource, test và output mà Maven nhận mặc định.
- [Maven: Getting Started Guide](https://maven.apache.org/guides/getting-started/index) — cấu trúc dự án Maven và cách khởi tạo.
- [Gradle: The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — source set, thư mục mặc định, tác vụ compile/resource/test và cấu hình tùy chỉnh.
- [Gradle: Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html) — tổ chức source set và dự án Java nhiều phần.
- [Java SE 27 API: Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html) — `getResourceAsStream` và quy tắc tên resource theo package/module.
- [Java SE 27 API: ClassLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassLoader.html) — resource path, class loader và cơ chế tìm resource.
- [Java SE 27 Tool Specifications: javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — source path, class path, module path và module source path.
- [Java SE 27 Tool Specifications: jar](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — tạo, liệt kê và mô tả JAR/module.
- [JUnit 6 User Guide](https://docs.junit.org/6.1.0/user-guide/) — JUnit Platform, Jupiter programming model và cách tổ chức test hiện đại.

Khi chọn phiên bản Maven, Gradle hoặc JUnit cho dự án, hãy đối chiếu ma trận tương thích với JDK 27 và khóa phiên bản trong cấu hình build/wrapper. Cấu trúc thư mục là quy ước có thể dùng lâu dài; phiên bản plugin và thư viện cần được cập nhật theo vòng đời hỗ trợ của từng công cụ.
