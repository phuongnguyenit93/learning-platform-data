# Tên module ổn định và `Automatic-Module-Name`

Khi chuyển ứng dụng Java từ classpath sang Java Platform Module System (JPMS), một thư viện JAR không chỉ được nhận diện qua tên file hay tọa độ Maven/Gradle. Trên **module path**, mỗi module có một **tên module** được dùng trong `requires`, các tùy chọn dòng lệnh như `--add-reads`, `--add-opens`, `--add-exports`, cũng như khi công cụ phân tích và khởi chạy xây dựng module graph.

Tên module là một phần quan trọng của hợp đồng tích hợp. Nếu hôm nay một JAR được nhận diện là `billing.client`, nhưng phiên bản tiếp theo bị đổi thành `billing.sdk` chỉ vì nhà phát hành đổi tên artifact, ứng dụng đang khai báo `requires billing.client;` có thể không biên dịch hoặc khởi chạy được. **`Automatic-Module-Name`** là một thuộc tính trong JAR manifest giúp nhà phát triển đặt trước một tên module ổn định khi JAR chưa có `module-info.class`.

Bài học này tập trung vào cách tên module được chọn, cách công bố tên bằng manifest, cách cấu hình khi phát hành thư viện và những việc cần làm để giữ tương thích khi nâng cấp JDK, đổi tên artifact hoặc chuyển sang explicit module.

## 1. Vì sao tên module là một hợp đồng tương thích?

Một ứng dụng JPMS có thể khai báo phụ thuộc vào thư viện như sau:

```java
module com.example.checkout {
    requires com.example.billing.client;
}
```

Ở đây, `com.example.billing.client` là **tên module**. Nó không nhất thiết là tên package, tên JAR, Maven `artifactId` hoặc tên class.

Giả sử ứng dụng đang hoạt động với artifact:

```text
billing-client-1.4.0.jar
```

Một đợt migration đổi tên tệp thành:

```text
billing-sdk-2.0.0.jar
```

Nếu module name được suy ra tự động từ tên tệp, tên module có thể thay đổi theo artifact. Nhưng nếu cả hai JAR đều công bố cùng một `Automatic-Module-Name: com.example.billing.client`, ứng dụng tiếp tục khai báo cùng một `requires`.

Tính ổn định có giá trị ở nhiều tầng:

- **Source compatibility:** `module-info.java` của consumer tiếp tục tham chiếu đúng tên module khi biên dịch lại.
- **Build compatibility:** Maven/Gradle và công cụ JPMS không phải cập nhật mọi `requires` chỉ vì tên tệp phát hành thay đổi.
- **Deployment compatibility:** script dùng `--module-path` hoặc chỉ định module bằng `-m`/`--module` có tên nhất quán.
- **Tooling compatibility:** cấu hình `jlink`, `jdeps`, `jpackage`, kiểm tra module graph và module layer có thể tái sử dụng định danh module.
- **Migration compatibility:** khi thư viện chuyển từ automatic module sang explicit module, consumer có thể tiếp tục dùng tên đã công bố trước đó.

Tên ổn định không tự bảo đảm API, bytecode hoặc hành vi không thay đổi. Nó giúp ngăn **một loại breaking change do đổi định danh module**.

## 2. Ba cách JAR tham gia hệ thống module

Trước khi đặt tên, cần biết JAR đang được dùng ở chế độ nào.

| Trường hợp | Cách xác định module | Ảnh hưởng của `Automatic-Module-Name` |
|---|---|---|
| Explicit named module | Có `module-info.class` được JPMS nhận diện | Tên từ descriptor là nguồn chính; header không thay thế descriptor |
| Automatic named module | JAR thông thường, không có module descriptor, được đặt trên module path | Header, nếu có và hợp lệ, cung cấp tên module ổn định |
| Unnamed module | JAR hoặc class được nạp từ classpath | Header không biến JAR thành named module; code vẫn ở unnamed module |

### 2.1. Explicit module

Thư viện có thể khai báo tên bằng `module-info.java`:

```java
module com.example.billing.client {
    exports com.example.billing.api;
}
```

Sau khi biên dịch, `module-info.class` nằm trong artifact modular. Tên `com.example.billing.client` đến từ module descriptor. Đây là cách khai báo chính thức và đầy đủ nhất, vì descriptor còn chỉ ra các quan hệ `requires`, `exports`, `opens`, `uses` và `provides`.

### 2.2. Automatic module

Một JAR truyền thống không có module descriptor vẫn có thể được đặt trên module path. JPMS có thể xem nó là **automatic module** và gán tên theo manifest hoặc, nếu manifest không chỉ định, suy ra tên từ filename.

Ví dụ:

```text
lib/
  billing-client-1.4.0.jar
```

Khi JAR không có descriptor và nằm trên module path, `Automatic-Module-Name` có thể ổn định định danh của nó cho consumer:

```text
Automatic-Module-Name: com.example.billing.client
```

Automatic module có cách xuất/đọc package nới lỏng nhằm hỗ trợ migration từ thư viện classpath. Nó là bước chuyển tiếp hữu ích, **không tương đương với việc đã thiết kế xong modular API**.

### 2.3. Unnamed module

Nếu vẫn đưa cùng JAR vào classpath:

```bash
java -cp "lib/*:app.jar" com.example.app.Main
```

thì thuộc tính `Automatic-Module-Name` không khiến nó tự động trở thành named module. Nó tiếp tục thuộc unnamed module tương ứng với class loader đó.

Cần phân biệt vị trí JAR trên **classpath** và **module path**. Chỉ thêm manifest entry mà không thay cách khởi chạy không thay đổi mô hình nạp class của ứng dụng hiện tại.

## 3. Tên module tự suy ra từ filename: tiện nhưng dễ thay đổi

Nếu JAR không có `module-info.class` và không khai báo `Automatic-Module-Name`, hệ thống có thể suy ra automatic module name từ tên file JAR.

Quy tắc suy ra bao gồm các bước như loại phần mở rộng `.jar`, bỏ phần version suffix phù hợp, chuyển một số ký tự phân tách thành dấu chấm và chuẩn hóa chuỗi thành tên module. Kết quả thực tế phải được kiểm tra bằng công cụ của đúng JDK mục tiêu, vì tên tệp phức tạp hoặc không hợp lệ có thể tạo ra lỗi nhận diện module.

Ví dụ minh họa:

| Filename | Tên thường được suy ra |
|---|---|
| `billing-client-1.4.0.jar` | `billing.client` |
| `commons-lang3-3.12.0.jar` | `commons.lang3` |
| `reporting_api-2.1.jar` | `reporting.api` |
| `example-core-2.0.0.jar` | `example.core` |

Nếu phiên bản sau đổi `billing-client-1.4.0.jar` thành `billing-sdk-2.0.0.jar`, tên được suy ra sẽ chuyển từ `billing.client` sang `billing.sdk`, dù các package bên trong không đổi.

Có những rủi ro khác:

- Tên tự suy ra không nhất thiết có namespace đủ riêng biệt, nên hai thư viện có thể trùng tên.
- Đổi convention đặt filename hoặc classifier có thể làm đổi tên module.
- Artifact có ký tự hoặc định dạng version bất thường có thể cho tên khó đoán.
- Module name dựa trên filename không nhất thiết trùng với tên mà nhà phát hành muốn dùng khi tạo `module-info.java` chính thức.
- Consumer có thể vô tình phụ thuộc vào tên suy ra rồi phải sửa hàng loạt khi thư viện đổi cách phát hành.

Vì vậy, **không nên coi tên suy ra từ filename là một API ổn định nếu nhà phát hành chưa cam kết**.

## 4. Khai báo `Automatic-Module-Name` trong manifest

JAR có một file manifest thông thường tại `META-INF/MANIFEST.MF`. Với thư viện chưa có module descriptor, có thể thêm header:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.billing.client

```

Các điểm cần hiểu đúng:

1. Thuộc tính là một manifest header, không phải Java annotation hoặc thuộc tính trong `module-info.java`.
2. Giá trị là tên module đầy đủ; không chứa version hoặc tên file `.jar`.
3. Header có ý nghĩa khi JAR là automatic module trên module path.
4. Header không định nghĩa `requires`, `exports` hoặc `opens` riêng lẻ; automatic module vẫn có đặc tính chuyển tiếp của nó.
5. Khi JAR đã có module descriptor được JPMS sử dụng, tên trong descriptor quyết định tên explicit module.
6. Phải kiểm tra **JAR phát hành cuối cùng** vì quá trình shade, repackage hoặc tạo executable JAR có thể thay đổi manifest.

Tên `com.example.billing.client` nên là tên dự định sử dụng lâu dài, không phải tên tạm chỉ để vượt qua một lỗi compiler.

### 4.1. Tên module không phải version

Không nên khai báo:

```text
Automatic-Module-Name: com.example.billing.client.v2
```

chỉ vì artifact tăng từ 1.x lên 2.x. Version của artifact cần được quản lý bằng Maven/Gradle coordinates, metadata phát hành và chính sách versioning riêng.

Cùng một tên module có thể được dùng qua nhiều phiên bản:

```text
billing-client-1.4.0.jar  -> com.example.billing.client
billing-client-1.5.0.jar  -> com.example.billing.client
billing-sdk-2.0.0.jar     -> com.example.billing.client
```

Điều đó không có nghĩa được đặt đồng thời nhiều phiên bản trùng tên trên một module path: module resolution phải xác định một định nghĩa module nhất quán. Nếu có hai bản JAR cùng module name trong cùng phạm vi tìm kiếm, JPMS có thể từ chối vì trùng định danh.

## 5. Quy ước đặt tên module ổn định

Với thư viện công khai hoặc nhiều nhóm sử dụng, nên quản lý tên module như một phần của public API.

### 5.1. Dùng namespace riêng biệt

Một quy ước dễ quản lý là tên dạng domain đảo ngược:

```text
com.example.billing.client
com.example.billing.api
com.example.platform.logging
org.example.analytics.core
```

Nên chọn các thành phần tên hợp lệ theo quy tắc module name của Java. Tránh dấu gạch ngang, khoảng trắng, tên quá ngắn dễ xung đột, từ khóa hoặc cấu trúc không hợp lệ.

Tên module có thể gần với package chính, nhưng không cần trùng tên package. Một module thường chứa nhiều package và chỉ một tên module.

### 5.2. Độc lập với tên artifact và repository

Ví dụ, ba thông tin sau phục vụ ba mục đích khác nhau:

| Loại định danh | Ví dụ | Dùng ở đâu |
|---|---|---|
| Maven group/artifact | `com.example.billing:billing-client` | Resolve dependency trong Maven/Gradle |
| Filename | `billing-client-1.4.0.jar` | Phân phối, lưu trữ, module path |
| JPMS module name | `com.example.billing.client` | `requires`, module graph, launcher và tooling |

Đổi repository, chuyển nhóm quản lý hoặc đổi tên artifact không buộc phải đổi JPMS name.

### 5.3. Định nghĩa quyền sở hữu tên

Một thư viện dùng chung nên có bản ghi về:

- Tên module chính thức.
- Artifact và repository phát hành.
- Chủ sở hữu hoặc nhóm duy trì.
- Phiên bản đầu tiên có header `Automatic-Module-Name`.
- Trạng thái: automatic module hay explicit module.
- Định hướng khi chuyển sang `module-info.java`.
- Các tên cũ đã từng được công bố hoặc suy ra và kế hoạch hỗ trợ consumer.

Quy ước này đặc biệt cần thiết ở hệ thống nhiều module, nhiều repository hoặc khi thư viện được phát hành ra ngoài tổ chức.

### 5.4. Tránh trùng tên module

JPMS xác định module theo tên trong module layer. Hai artifact khác nhau không nên công bố cùng tên module. Nếu cả hai cùng được đưa vào module path, resolution có thể thất bại; nếu chỉ một bản được chọn tùy môi trường, kết quả chạy cũng có thể không nhất quán.

Không dùng tên `java.*` hoặc những tên dễ nhầm với module nền tảng. Hãy chọn namespace thuộc quyền quản lý thực sự của thư viện.

## 6. Cấu hình Maven để phát hành JAR có tên module cố định

Với Maven, có thể cấu hình Maven JAR Plugin để thêm manifest entry trong JAR của thư viện:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifestEntries>
                        <Automatic-Module-Name>com.example.billing.client</Automatic-Module-Name>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Sau đó package:

```bash
mvn clean package
```

Kiểm tra artifact tạo ra:

```bash
jar --describe-module --file target/billing-client-1.4.0.jar
```

Lệnh `jar --describe-module` từ JDK hỗ trợ JPMS cho biết JAR có explicit descriptor hay là automatic module, cùng tên module nhận diện được.

Nếu dự án dùng parent POM, `pluginManagement` hoặc nhiều profile, cần đảm bảo cấu hình được áp dụng cho đúng packaging goal và artifact phát hành.

### 6.1. Maven Shade Plugin và manifest cuối cùng

Khi dùng `maven-shade-plugin` để tạo uber JAR, artifact cuối có thể sử dụng manifest khác với JAR do `maven-jar-plugin` sinh ra. Cần đặt hoặc bảo tồn `Automatic-Module-Name` ở **shaded artifact thực tế**.

Ví dụ có thể khai báo `ManifestResourceTransformer`:

```xml
<transformers>
    <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
        <manifestEntries>
            <Automatic-Module-Name>com.example.billing.client</Automatic-Module-Name>
        </manifestEntries>
    </transformer>
</transformers>
```

Đây là fragment trong cấu hình `maven-shade-plugin`, không phải một POM hoàn chỉnh. Với shaded JAR, phải đánh giá thêm package relocation, trùng package, resource service provider và descriptor có thể đến từ các dependency; chỉ sửa manifest không tự xử lý những vấn đề đó.

### 6.2. Không đưa nhiều manifest header trùng lặp

Nếu có nhiều plugin chỉnh manifest, cần kiểm tra output cuối thay vì chỉ xem POM. Một header tồn tại trong cấu hình chưa chứng minh nó đã xuất hiện đúng trong JAR phát hành.

Đối với một thư viện, nên có một nguồn cấu hình rõ ràng cho tên module và quy trình đóng gói có thể lặp lại.

## 7. Cấu hình Gradle

Với Gradle Groovy DSL, có thể thêm thuộc tính cho tác vụ `jar`:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.example.billing.client'
        )
    }
}
```

Đối với một build multi-project, mỗi thư viện cần tên riêng. Không đặt cùng một tên cố định cho mọi subproject nếu từng subproject phát hành JAR riêng.

Ví dụ ở module `:billing-client`:

```groovy
project(':billing-client') {
    tasks.named('jar', Jar) {
        manifest {
            attributes(
                'Automatic-Module-Name': 'com.example.billing.client'
            )
        }
    }
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.named<Jar>("jar") {
    manifest {
        attributes["Automatic-Module-Name"] = "com.example.billing.client"
    }
}
```

Có thể build JAR bằng:

```bash
./gradlew :billing-client:jar
```

Sau đó dùng `jar --describe-module --file` trên đường dẫn artifact thực tế trong `build/libs`.

Nếu module sử dụng Shadow plugin, Spring Boot `bootJar` hoặc packaging plugin khác, chúng có thể tạo một JAR khác tác vụ `jar`. Cần xác định artifact nào là thư viện JPMS thực sự được phát hành, rồi kiểm tra manifest của artifact đó.

## 8. Ví dụ consumer dùng automatic module ổn định

Giả sử thư viện `billing-client-1.4.0.jar` chứa:

```text
META-INF/MANIFEST.MF
com/example/billing/api/BillingClient.class
com/example/billing/model/Invoice.class
```

Manifest:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.billing.client

```

Ứng dụng consumer là explicit module:

```java
module com.example.checkout {
    requires com.example.billing.client;
}
```

Code ứng dụng:

```java
package com.example.checkout;

import com.example.billing.api.BillingClient;

public class Main {
    public static void main(String[] args) {
        BillingClient client = new BillingClient();
        System.out.println(client);
    }
}
```

Để biên dịch ứng dụng modular, JAR phải có trên module path và các dependency cần thiết cũng phải được phân giải:

```bash
javac --module-path lib \
  -d out \
  src/com.example.checkout/module-info.java \
  src/com.example.checkout/com/example/checkout/Main.java
```

Ví dụ lệnh trên giả định module source có bố cục đường dẫn như thể hiện, và `lib` chứa JAR có tên module đúng. Nếu `BillingClient` có constructor hoặc API khác, hãy thay phần code minh họa bằng API thư viện thực tế.

Chạy consumer modular:

```bash
java --module-path "lib:out" \
  --module com.example.checkout/com.example.checkout.Main
```

Trên Windows, dấu phân tách các mục path thường là dấu chấm phẩy thay vì dấu hai chấm. Cần dùng cú pháp phù hợp với shell và hệ điều hành.

Nếu thư viện đổi filename ở phiên bản tiếp theo nhưng giữ `Automatic-Module-Name`, dòng `requires com.example.billing.client;` của consumer vẫn giữ nguyên.

## 9. Đặc điểm của automatic module: thuận tiện và giới hạn

Một automatic module là cầu nối giữa JAR truyền thống và hệ thống module tường minh.

Trong mô hình automatic module, JPMS cho phép nhiều hành vi rộng rãi để hỗ trợ thư viện chưa được modularize:

- Các package trong automatic module được xuất và mở theo cơ chế automatic module.
- Automatic module có quan hệ đọc rộng với các module khác, nhằm giảm rào cản migration của thư viện cũ.
- Nó không khai báo chính xác API public nào cần `exports` hoặc package nào cần `opens` cho reflection.
- Nó không biểu đạt các dependency bắt buộc bằng `requires` theo cách của explicit descriptor.
- JAR vẫn có thể chứa class, resource và cơ chế classpath cũ mà chưa có thiết kế module boundary rõ ràng.

Điều này làm `Automatic-Module-Name` rất hữu ích để **ổn định định danh**, nhưng không biến một thư viện thành fully modular library.

### 9.1. Không nhầm automatic module với named module được encapsulate chặt

Một explicit module có thể chỉ export package API:

```java
module com.example.billing.client {
    exports com.example.billing.api;
}
```

Các package implementation như `com.example.billing.internal` có thể bị encapsulate, tùy cấu hình `opens` và khả năng truy cập khác.

Trong khi đó, automatic module không có khả năng khai báo chọn lọc `exports`/`opens` theo cách trên. Vì vậy, consumer đang truy cập package nội bộ khi JAR còn automatic có thể bị lỗi khi thư viện chuyển thành explicit module.

### 9.2. Vấn đề phụ thuộc classpath

Automatic module được thiết kế để hỗ trợ migration và có khả năng đọc rộng, kể cả tương tác với code còn trên classpath theo quy tắc JPMS. Tuy nhiên, **explicit named module không thể đơn giản `requires` một thư viện chỉ nằm trên classpath**, bởi classpath tạo unnamed module không có tên cho `requires`.

Khi dự án chuyển từ classpath sang module path, cần phân loại chính xác những dependency nào đã có explicit descriptor, là automatic module hay vẫn ở unnamed module.

### 9.3. Tên ổn định không sửa split package

JPMS có các quy tắc hạn chế khi nhiều named module chứa cùng package. Ví dụ:

```text
billing-api.jar      -> com.example.billing.api.Account
billing-impl.jar     -> com.example.billing.api.InternalHelper
```

Nếu hai JAR được coi là hai named module và chứa chung package `com.example.billing.api`, module graph hoặc compiler có thể báo xung đột split package.

Thêm `Automatic-Module-Name` vào cả hai artifact không giải quyết vấn đề. Cần tái tổ chức package, gộp thành phần phù hợp hoặc điều chỉnh cách đóng gói.

## 10. Từ automatic module sang explicit module

Một lộ trình phổ biến cho thư viện muốn duy trì hỗ trợ Java cũ trong khi bắt đầu hỗ trợ JPMS:

1. Giữ JAR truyền thống và thêm `Automatic-Module-Name` để công bố tên ổn định.
2. Phát hành và để consumer bắt đầu dùng tên này trong `module-info.java`.
3. Rà soát public API, dependency, reflection, service provider và package boundaries.
4. Tạo `module-info.java` với **đúng tên đã công bố trước đó**.
5. Kiểm thử các consumer đang dùng cả module path lẫn classpath.
6. Phát hành explicit module theo chính sách versioning của thư viện.

Ví dụ manifest ở phiên bản đầu:

```text
Automatic-Module-Name: com.example.billing.client
```

Sau khi modularize:

```java
module com.example.billing.client {
    requires java.net.http;

    exports com.example.billing.api;
    exports com.example.billing.model;
}
```

Điểm quan trọng là tên trong descriptor giữ nguyên `com.example.billing.client`. Nếu đổi thành `com.example.billing.sdk`, consumer có `requires com.example.billing.client;` sẽ phải cập nhật ngay cả khi các class public không đổi.

### 10.1. Vấn đề mới khi chuyển thành explicit module

Trước đây, automatic module có thể để lộ nhiều package. Khi thêm descriptor, quyền truy cập trở nên chọn lọc:

- Consumer import package không được export có thể không còn biên dịch.
- Framework dùng deep reflection vào package chưa được mở có thể ném `InaccessibleObjectException`.
- Dependency từng được tự động đọc có thể phải được khai báo bằng `requires` hoặc `requires transitive`.
- Service provider discovery có thể cần `uses`/`provides` hoặc metadata thích hợp.
- Cách nạp resource và native library phải được kiểm tra trên module path.
- Tên package trùng giữa các module có thể bị phát hiện rõ ràng hơn.

Vì vậy, **giữ tên module ổn định là điều kiện hữu ích, nhưng chưa đủ để bảo đảm migration sang explicit module không phá tương thích**.

### 10.2. Multi-release JAR cho thư viện hỗ trợ cả Java 8 và JPMS

Một thư viện muốn tiếp tục phát hành bytecode Java 8 nhưng cung cấp descriptor từ Java 9 có thể sử dụng multi-release JAR, chẳng hạn:

```text
META-INF/MANIFEST.MF
com/example/billing/api/BillingClient.class
META-INF/versions/9/module-info.class
```

Manifest cần khai báo multi-release đúng cách:

```text
Manifest-Version: 1.0
Multi-Release: true
Automatic-Module-Name: com.example.billing.client

```

Trên JVM hỗ trợ multi-release/module descriptor, JAR có thể được nhận diện như explicit module theo descriptor được chọn. Trên JVM cũ không hỗ trợ JPMS, class Java 8 thông thường vẫn có thể được nạp theo classpath, nếu artifact và dependency khác thực sự tương thích.

Đây là kỹ thuật đóng gói nâng cao: cần kiểm tra quy tắc multi-release, manifest, compiler options và output của plugin thực tế. Không nên tự chèn `module-info.class` vào một vị trí bất kỳ rồi giả định JDK sẽ tự nhận diện đúng.

## 11. Các lỗi thường gặp khi tên module không ổn định

### 11.1. `module not found`

Một consumer có:

```java
requires com.example.billing.client;
```

nhưng module path chỉ chứa JAR được nhận diện là `billing.sdk`. Compiler hoặc launcher có thể báo không tìm được module `com.example.billing.client`.

Cần kiểm tra tên module mà JDK thực sự đọc từ JAR và các mục trên module path.

### 11.2. Tên trùng giữa hai JAR

Hai JAR khác nhau cùng khai báo:

```text
Automatic-Module-Name: com.example.shared
```

Nếu cùng nằm trên module path, hệ thống có thể báo duplicate module trong quá trình tìm và phân giải module.

Cần giải quyết ownership/name collision; không nên dùng thứ tự classpath để che giấu vấn đề vì module path có quy tắc định danh khác.

### 11.3. Tên trong manifest khác `module-info.java`

Trong một quá trình nâng cấp, nhóm phát triển thêm descriptor:

```java
module com.example.billing.sdk { }
```

nhưng các phiên bản trước đã công bố:

```text
Automatic-Module-Name: com.example.billing.client
```

Lúc này consumer phải đổi `requires` khi chuyển phiên bản. Tên trong explicit descriptor nên được giữ nhất quán với tên ổn định đã công bố.

### 11.4. Header không xuất hiện trong JAR cuối

Build script có thể khai báo manifest entry nhưng JAR deploy được tạo bởi tác vụ hoặc plugin khác. Kết quả là `jar --describe-module` trên JAR phát hành lại hiển thị tên suy ra từ filename.

Cần kiểm tra artifact cuối sau mọi bước shade, repackage, sign hoặc copy; không chỉ kiểm tra cấu hình nguồn.

### 11.5. Header có tên không hợp lệ

Một tên như `billing-client` chứa dấu gạch ngang và không phù hợp với tên module Java. Chọn tên có các thành phần identifier hợp lệ, ví dụ `com.example.billing.client`, và xác nhận bằng công cụ JDK.

### 11.6. Đặt tên ổn định nhưng thư viện vẫn không modularize được

Nếu JAR chứa split packages, phụ thuộc các API nội bộ bị đóng, service provider metadata không đúng hoặc code dựa quá nhiều vào reflection, việc thêm manifest entry không giải quyết các vấn đề đó.

Nên tách lỗi **định danh module** với lỗi **module graph, encapsulation hoặc runtime behavior** để sửa đúng nguyên nhân.

## 12. Kiểm tra tên module trong artifact đã phát hành

### 12.1. Xem tên mà JDK nhận diện

Dùng công cụ `jar` từ JDK có JPMS:

```bash
jar --describe-module --file build/libs/billing-client-1.4.0.jar
```

Kết quả giúp nhận diện automatic module hoặc explicit module, cùng tên module mà JDK sử dụng.

Với Maven:

```bash
jar --describe-module --file target/billing-client-1.4.0.jar
```

Đường dẫn cần trùng artifact phát hành cuối cùng. Nếu file là executable JAR có nested dependencies, không nên giả định cấu trúc đó tương đương một tập module chuẩn trên module path.

### 12.2. Xem module graph

Khi có nhiều dependency trên module path:

```bash
java --module-path libs --list-modules
```

Lệnh cho thấy các module mà launcher nhìn thấy trong cấu hình hiện tại. Với một ứng dụng modular có entrypoint, có thể chạy trực tiếp để kiểm tra resolution thực tế.

### 12.3. Kiểm tra xung đột module path

Có thể dùng:

```bash
java --module-path libs --validate-modules
```

Tùy chọn này hỗ trợ phát hiện một số vấn đề module path và phân giải trước khi chạy ứng dụng. Cần chạy với tập artifact tương ứng môi trường triển khai, không chỉ vài JAR đơn lẻ.

### 12.4. Phân tích dependency

`jdeps` hỗ trợ quan sát dependency ở mức bytecode/module:

```bash
jdeps --module-path libs --print-module-deps app.jar
```

Phân tích tĩnh không nhìn thấy mọi dependency được tạo bằng reflection, configuration hoặc code generation. Kết hợp với compile/run test và việc xem module descriptor của từng artifact.

### 12.5. Lưu bằng chứng trong CI

Một pipeline phát hành thư viện có thể lưu:

- Artifact name và checksum.
- Tên module được công cụ `jar --describe-module` nhận diện.
- JDK vendor/release dùng để kiểm tra.
- `Automatic-Module-Name` hoặc module descriptor version.
- Danh sách artifact trên module path khi chạy integration test.
- Kết quả consumer compile và smoke test.

Nếu tên module thay đổi ngoài dự kiến giữa hai phiên bản, CI có thể phát hiện trước khi phát hành chính thức.

## 13. Chiến lược migration cho hệ thống nhiều thư viện

Với một sản phẩm có nhiều module và dependency nội bộ, việc chuyển sang JPMS nên có một **module name registry** đơn giản:

| Artifact | Tên JPMS cam kết | Trạng thái | Consumer tiêu biểu |
|---|---|---|---|
| `billing-client` | `com.example.billing.client` | Automatic | Checkout Service |
| `shared-contracts` | `com.example.shared.contracts` | Automatic | Billing, Checkout |
| `inventory-core` | `com.example.inventory.core` | Explicit | Inventory API |
| `reporting-sdk` | `com.example.reporting.sdk` | Automatic | Reporting Job |

Các giá trị là ví dụ minh họa, không mô tả dự án thực tế.

Quy trình có thể triển khai theo từng giai đoạn:

**Giai đoạn 1 — Kiểm kê.** Xác định JAR trên classpath/module path, phiên bản đã resolve, tên module hiện tại và dependency. Dùng `jar --describe-module` để lấy kết quả thực tế.

**Giai đoạn 2 — Chọn tên chính thức.** Ưu tiên namespace rõ, ít thay đổi, không chứa version và không trùng với module khác. Công bố cùng đội ngũ sở hữu artifact.

**Giai đoạn 3 — Phát hành automatic module ổn định.** Thêm `Automatic-Module-Name` vào từng JAR truyền thống có kế hoạch hỗ trợ JPMS. Kiểm tra artifact cuối cùng sau packaging.

**Giai đoạn 4 — Đưa consumer lên module path.** Bổ sung `requires` theo tên ổn định; xử lý dependency chưa modularize, split packages và vấn đề classpath/module path.

**Giai đoạn 5 — Modularize từng thư viện.** Bổ sung `module-info.java` với cùng tên đã cam kết. Khai báo `requires`, `exports`, `opens` và dịch vụ một cách có chủ đích.

**Giai đoạn 6 — Kiểm thử chéo.** Build lại consumer, chạy binary hiện có khi cần giữ binary compatibility, xác minh reflection/service provider và chạy smoke test trên runtime mục tiêu.

Không cần đưa mọi thư viện lên explicit module trong một release. Automatic module với tên ổn định cho phép từng nhóm migration theo lộ trình riêng, miễn là các giới hạn của mô hình tạm thời được hiểu rõ.

## 14. Checklist trước khi công bố tên module

- [ ] Đã xác định artifact phát hành cuối và module path thực tế.
- [ ] Tên JPMS đã được chọn có namespace rõ ràng và hợp lệ.
- [ ] Tên không gắn version, filename, classifier hoặc repository name có thể đổi.
- [ ] Không có hai artifact trong cùng phạm vi dùng chung tên module.
- [ ] JAR chưa có descriptor được gắn đúng `Automatic-Module-Name` trong manifest.
- [ ] Maven/Gradle shade, repackage hoặc custom packaging không làm mất header.
- [ ] `jar --describe-module --file` xác nhận đúng tên ở artifact cuối.
- [ ] Consumer dùng `requires` theo tên đã công bố.
- [ ] Đã rà soát split packages và dependency trên classpath/module path.
- [ ] Nếu thư viện chuyển thành explicit module, tên trong `module-info.java` vẫn giữ nguyên.
- [ ] Đã kiểm tra quyền `exports`/`opens`, service loading và reflection khi modularize.
- [ ] CI lưu tên module và phát hiện thay đổi ngoài dự kiến.
- [ ] Có hướng dẫn migration nếu từng phiên bản trước đã công bố một tên khác.

## 15. Kết luận

Tên module là định danh mà consumer JPMS sử dụng để thiết lập dependency và khởi chạy trên module path. Nếu để tên được suy ra từ filename, việc đổi artifact hoặc quy ước đóng gói có thể vô tình trở thành breaking change. `Automatic-Module-Name` cho phép thư viện JAR truyền thống công bố tên module ổn định ngay khi chưa có `module-info.class`.

Cách tiếp cận bền vững là chọn tên theo namespace rõ ràng, công bố nó trong manifest của artifact cuối, xác minh bằng công cụ JDK và giữ nguyên tên đó khi chuyển sang explicit module. Sau bước đặt tên, cần tiếp tục xử lý module graph, encapsulation, reflection, service provider và kiểm thử consumer để bảo đảm Java Compatibility Migration thành công.
