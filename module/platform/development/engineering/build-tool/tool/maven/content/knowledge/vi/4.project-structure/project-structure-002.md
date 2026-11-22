# `src/main/java` và tổ chức package mã nguồn chính trong dự án Maven

## 1. `src/main/java` là gì và vì sao Maven cần cấu trúc này?

Trong dự án Java dùng Apache Maven, `src/main/java` là **thư mục gốc của mã nguồn Java thuộc sản phẩm chính** (main source root). Các lớp và giao diện ở đây được biên dịch để tạo chương trình hoặc thư viện mà dự án phát hành.

Maven theo nguyên tắc **convention over configuration**: nếu dự án đi theo bố cục chuẩn, không cần khai báo thủ công chỗ tìm mã Java trong `pom.xml`. Maven xác định đường dẫn tương đối từ **thư mục chứa `pom.xml` của module hiện tại**:

- `src/main/java`: mã nguồn Java chính, ví dụ `App.java`, `OrderService.java`.
- `src/main/resources`: tài nguyên chính, ví dụ file cấu hình và dữ liệu cần nằm trên classpath.
- `src/test/java`: mã nguồn test; tách biệt với mã nguồn sản phẩm.
- `src/test/resources`: tài nguyên phục vụ test.
- `target/classes`: tệp `.class` đã biên dịch từ mã Java chính và các tài nguyên chính đã được copy.
- `target/test-classes`: tệp `.class` của test và tài nguyên test (sau các pha build tương ứng).
- `target/*.jar` hoặc artifact tương ứng: sản phẩm của bước đóng gói, tùy `packaging`.

`src/main/java` là **đường dẫn tương đối trong cây dự án**, không phải tên Java package. `src`, `main` và `java` chỉ là phần của quy ước thư mục Maven; package thực sự bắt đầu ở **bên dưới** `src/main/java`.

Ví dụ cây thư mục:

```text
catalog-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/
│   │   │       └── example/
│   │   │           └── catalog/
│   │   │               ├── App.java
│   │   │               └── service/
│   │   │                   └── GreetingService.java
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
└── target/                     # Maven tạo sau khi build
```

Trong ví dụ, `App.java` mang package `com.example.catalog`, còn `GreetingService.java` mang package `com.example.catalog.service`. Hai package là **hai namespace khác nhau**, dù một tên có tiền tố của tên kia.

## 2. Maven tìm mã Java và tạo output như thế nào?

Với dự án có `packaging` là `jar` (hoặc mặc định là `jar`), Maven liên kết các goal của plugin với vòng đời build:

1. Ở pha `process-resources`, Maven xử lý/copy tài nguyên thuộc `src/main/resources` sang `target/classes`.
2. Ở pha `compile`, `maven-compiler-plugin` gọi trình biên dịch Java để biên dịch nguồn thuộc `src/main/java` và tạo tệp `.class` dưới `target/classes`.
3. Ở các pha tiếp theo, Maven có thể biên dịch test dưới `src/test/java`, chạy test và đóng gói sản phẩm.

Ví dụ `src/main/java/com/example/catalog/App.java` chứa lớp `com.example.catalog.App`. Tệp biên dịch thông thường là:

```text
target/classes/com/example/catalog/App.class
```

Khi tạo JAR thông thường, đường dẫn entry của lớp trong JAR giữ cấu trúc tương ứng:

```text
com/example/catalog/App.class
```

Không nhầm mã nguồn với output: **chỉnh sửa mã ở `src/main/java`**, không sửa `.class` tại `target/classes`; thư mục `target` được sinh lại và thường bị bỏ qua trong Git.

Đường dẫn nguồn và output mặc định có thể cấu hình qua `pom.xml`/plugin, nhưng chỉ thay đổi khi có yêu cầu thực tế. Dùng cấu trúc mặc định giúp công cụ, IDE và các thành viên dự án hiểu cùng một bố cục.

## 3. Quy tắc ánh xạ package Java sang cây thư mục

Dòng khai báo package ở đầu tệp xác định namespace của một kiểu Java:

```java
package com.example.catalog;
```

Theo quy ước chuẩn, các dấu chấm `.` trong package chuyển thành các cấp thư mục, tính từ **source root**:

| Khai báo trong nguồn | Đường dẫn tệp từ gốc dự án |
| --- | --- |
| `package com.example.catalog;` | `src/main/java/com/example/catalog/App.java` |
| `package com.example.catalog.service;` | `src/main/java/com/example/catalog/service/GreetingService.java` |
| `package com.example.catalog.model;` | `src/main/java/com/example/catalog/model/Item.java` |
| `package org.acme.billing.api;` | `src/main/java/org/acme/billing/api/BillingApi.java` |

Phần cuối tên tệp còn phải tuân thủ quy tắc Java: nếu một tệp khai báo một lớp top-level `public class App` thì tên file phải là `App.java`, đúng chữ hoa/chữ thường. Trên hệ thống phân biệt chữ hoa, `app.java` và `App.java` là hai tên khác nhau.

**Ví dụ đúng:**

```text
src/main/java/com/example/catalog/service/GreetingService.java
```

```java
package com.example.catalog.service;

public class GreetingService {
}
```

**Ví dụ sai về tổ chức dự án (dù một số lệnh biên dịch thủ công có thể chấp nhận vị trí khác):**

```text
src/main/java/com/example/catalog/GreetingService.java
```

```java
package com.example.catalog.service;
```

Java package được xác định bởi câu lệnh `package`, không được suy ra trực tiếp từ vị trí file như một quy tắc ngôn ngữ tuyệt đối. Tuy vậy, để Maven/IDE và các công cụ tìm nguồn hoạt động nhất quán, **hãy đặt đường dẫn trùng với cấu trúc package**. Không cần khai báo mỗi folder là một source root riêng.

Ngoài ra, hãy tránh bỏ dòng `package`: lớp sẽ thuộc **unnamed/default package**, khó tổ chức, khó import từ lớp thuộc named package và không phù hợp dự án Java lớn.

## 4. Chọn tên package: gọn, hợp lệ, dễ phát triển

Quy ước Java thường dùng **tên miền đảo ngược** để giảm xung đột:

- Tổ chức sở hữu tên miền `example.com` → tiền tố minh họa `com.example`.
- Ứng dụng catalog → `com.example.catalog`.
- Mã xử lý nghiệp vụ → `com.example.catalog.service`.
- Mô hình dữ liệu → `com.example.catalog.model`.
- API công khai → `com.example.catalog.api`.

Quy ước quan trọng:

- Dùng chữ thường cho các thành phần package, ví dụ `com.example.order`; tránh `com.Example.Order`.
- Mỗi thành phần phải là một định danh Java hợp lệ; tránh dấu gạch nối (`order-service`), dấu cách, ký tự đầu là chữ số và keyword Java.
- Tên package nên phản ánh **quyền sở hữu và phạm vi nghiệp vụ**, không cần chứa tên mọi công cụ sử dụng.
- Có thể chia theo tính năng (`catalog`, `customer`, `billing`) hoặc vai trò (`service`, `repository`, `api`) tùy quy mô và kiến trúc; giữ cách chia nhất quán.
- Tránh đẩy tất cả lớp vào `com.example.util` hoặc chia quá nhiều tầng khi chưa có ranh giới rõ ràng.
- Tránh sử dụng tiền tố nền tảng dành riêng như `java.*` cho ứng dụng.

Đừng nhầm tên package với Maven coordinates. `groupId`, `artifactId`, `version` xác định **artifact Maven**, còn câu lệnh `package` xác định **namespace Java**. Chẳng hạn, artifact `com.example:catalog-demo:1.0.0` có thể chứa lớp `com.example.catalog.App`; `artifactId` không nhất thiết phải trùng một phần tên package.

## 5. Ví dụ hoàn chỉnh Java 17: hai package trong một module Maven

Tạo một thư mục `catalog-demo` và lưu **đúng ba tệp** sau. Ví dụ không cần thư viện bên ngoài; yêu cầu JDK 17+ và Apache Maven phù hợp.

### 5.1. `pom.xml` ở thư mục gốc

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>catalog-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`maven.compiler.release=17` yêu cầu trình biên dịch tạo bytecode/API mục tiêu Java 17; bản thân lệnh Maven vẫn phải chạy trên JDK đáp ứng yêu cầu. Phiên bản plugin `3.14.1` được ghi cố định ở đây để ví dụ có thể lặp lại; không có nghĩa dự án luôn phải dùng phiên bản đó. Thuộc tính `project.build.sourceEncoding` đặt encoding nguồn (ví dụ này dùng UTF-8).

### 5.2. `src/main/java/com/example/catalog/service/GreetingService.java`

```java
package com.example.catalog.service;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Lớp nằm trong package `com.example.catalog.service`, có phương thức `public` để mã từ package khác gọi. Đây là một lớp Java chính thức sẽ được Maven biên dịch.

### 5.3. `src/main/java/com/example/catalog/App.java`

```java
package com.example.catalog;

import com.example.catalog.service.GreetingService;

public class App {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Maven"));
    }
}
```

`App` nằm trong package khác `GreetingService`, vì vậy dùng `import` kèm tên đầy đủ để gọi lớp. Java cũng cho phép viết `new com.example.catalog.service.GreetingService()` trực tiếp, nhưng `import` giúp mã dễ đọc.

### 5.4. Biên dịch và chạy

Trong terminal ở thư mục chứa `pom.xml`:

```bash
mvn -B -ntp clean package
java -cp target/classes com.example.catalog.App
```

**Stdout của riêng lệnh `java` thứ hai:**

```text
Hello, Maven!
```

Lệnh `mvn` thứ nhất còn hiển thị log Maven; không nên nhầm log đó với stdout của chương trình. Sau khi compile, ta có thể thấy:

```text
target/classes/com/example/catalog/App.class
target/classes/com/example/catalog/service/GreetingService.class
```

Một cách chạy tương đương sau pha `package`:

```bash
java -cp target/catalog-demo-1.0.0.jar com.example.catalog.App
```

Vì POM mẫu **chưa khai báo `Main-Class` trong manifest**, `java -jar target/catalog-demo-1.0.0.jar` không phải lệnh chạy phù hợp với ví dụ này. Dùng `-cp` và tên lớp đầy đủ (fully qualified class name) như trên.

Nếu dự án đã cung cấp Maven Wrapper, có thể thay `mvn` bằng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows), nhưng không phải dự án Maven nào cũng có sẵn Wrapper.

## 6. Hiểu `import`, phạm vi truy cập và package con

Các lớp thuộc **cùng một package** có thể tham chiếu nhau bằng tên ngắn mà không cần `import`. Lớp thuộc package khác thường cần `import` hoặc tên lớp đầy đủ.

Điểm dễ nhầm: `com.example.catalog` và `com.example.catalog.service` là **hai package độc lập**. Việc package thứ hai có tên bắt đầu bằng package thứ nhất **không có nghĩa** chúng chia sẻ quyền truy cập package-private.

Ví dụ:

```java
package com.example.catalog.service;

class InternalFormatter {
    String normalize(String value) {
        return value.trim();
    }
}
```

`InternalFormatter` không có modifier `public` và phương thức `normalize` cũng có phạm vi package-private. Một lớp ở `com.example.catalog` không thể sử dụng chúng trực tiếp, dù cùng nằm dưới cây thư mục `com/example/catalog`. Đây là đặc tính của Java, không phải giới hạn riêng của Maven.

Ở chiều ngược lại, đặt mọi lớp thành `public` chỉ để tiện gọi cũng có thể tạo API rộng không cần thiết. Khi thiết kế package, nên xác định lớp nào thực sự cần công khai, lớp nào chỉ là chi tiết triển khai trong package của nó.

## 7. Phân biệt mã chính, tài nguyên và mã test

`src/main/java` chỉ dành cho **mã Java chính**. Các nội dung liên quan nằm ở các vùng khác:

| Thư mục | Nội dung điển hình | Vai trò khi build |
| --- | --- | --- |
| `src/main/java` | `.java` ứng dụng/thư viện | Biên dịch thành `target/classes`, được đóng gói tùy loại artifact |
| `src/main/resources` | `.properties`, `.xml`, tài nguyên text, template | Copy/đưa vào main classpath, thường cùng JAR |
| `src/test/java` | Unit test, integration-oriented test code tùy plugin | Biên dịch riêng thành `target/test-classes` |
| `src/test/resources` | Dữ liệu test và cấu hình test | Đưa vào test classpath, thường không nằm trong JAR sản phẩm |
| `target/` | Lớp đã biên dịch, report, JAR và file trung gian | Output sinh tự động; không là nguồn sửa chính |

Ví dụ `src/main/resources/com/example/catalog/messages.properties` sẽ được copy tương đối vào `target/classes/com/example/catalog/messages.properties`. Code có thể tải tài nguyên qua classpath, không nên dùng đường dẫn tuyệt đối của máy lập trình.

Test cho `GreetingService` thường nằm tại:

```text
src/test/java/com/example/catalog/service/GreetingServiceTest.java
```

Nó có thể khai báo cùng package `com.example.catalog.service` để tổ chức dễ đối chiếu, nhưng vẫn ở **source root test**; package giống nhau không làm mã test tự động trở thành mã sản phẩm. Test framework như JUnit cần dependency/test plugin thích hợp; bài ví dụ ở trên không tự nhận đã cung cấp bộ test hoàn chỉnh.

## 8. Tổ chức nhiều package khi dự án lớn dần

Không bắt buộc mọi dự án dùng một mô hình cố định. Ví dụ với phạm vi ứng dụng catalog:

```text
src/main/java/com/example/catalog/
├── api/
│   └── CatalogApi.java
├── model/
│   └── Item.java
├── service/
│   └── CatalogService.java
└── persistence/
    └── ItemRepository.java
```

Cách chia theo vai trò giúp định vị nhanh API, model, nghiệp vụ và lưu trữ. Với ứng dụng nhiều tính năng độc lập, cũng có thể chia theo feature:

```text
src/main/java/com/example/shop/
├── catalog/
│   ├── CatalogService.java
│   └── Item.java
├── ordering/
│   ├── OrderService.java
│   └── Order.java
└── customer/
    └── CustomerService.java
```

Các tên lớp trên **chỉ là minh họa tổ chức**, không phải một chương trình có thể biên dịch độc lập. Đừng nhầm cấu trúc thư mục đẹp với ranh giới module hay kiểm soát dependency: Java package là namespace/ranh giới truy cập; **module Maven** được xác định bởi `pom.xml` và quan hệ module/dependency. Thiết kế phụ thuộc vẫn phải được quản lý bằng code, API và Maven dependencies.

Trong **dự án Maven đa module**, mỗi module Java thông thường có một `pom.xml` và **`src/main/java` riêng**:

```text
shop-parent/
├── pom.xml                       # POM aggregator, thường packaging=pom
├── catalog-service/
│   ├── pom.xml
│   └── src/main/java/...
└── ordering-service/
    ├── pom.xml
    └── src/main/java/...
```

Đặt mã dưới `shop-parent/src/main/java` không tự khiến chúng thuộc cả hai module con. Tương tự, hai module khác nhau có package tên giống nhau không làm Maven tự tạo dependency giữa chúng.

## 9. Đổi tên package và di chuyển nguồn an toàn

Khi đổi `com.example.catalog.service` sang `com.example.catalog.application`, phải cập nhật **cả đường dẫn nguồn và khai báo `package`**, sau đó sửa mọi `import`/tham chiếu tương ứng. Nếu dùng IDE, ưu tiên thao tác **Refactor > Move/Rename** có khả năng cập nhật tham chiếu.

Một quy trình bảo trì hợp lý:

1. Xác định package hiện tại và các nơi tham chiếu lớp đó, kể cả test.
2. Di chuyển tệp `.java` sang thư mục ứng với package mới.
3. Cập nhật `package`, `import` và chuỗi tên lớp đầy đủ được dùng trong cấu hình/reflection nếu có.
4. Kiểm tra tài nguyên liên quan bằng classpath và các test trong `src/test/java`.
5. Chạy `mvn clean verify` (hoặc Wrapper tương ứng); đánh giá lỗi biên dịch/test trước khi commit.

Không di chuyển mã nguồn vào `target` để chữa lỗi đường dẫn; Maven có thể xóa `target` trong bước `clean`. Không sửa mã `.class` sau build.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Điều cần kiểm tra | Cách sửa |
| --- | --- | --- |
| `No sources to compile` | File nằm ngoài `src/main/java` hoặc đang chạy Maven từ POM/module khác; source root bị cấu hình lệch. | Đặt nguồn đúng root của module, chạy `mvn compile` từ đúng POM. |
| `package ... does not exist` | Import sai tên, file thuộc package khác, dependency thiếu hoặc nguồn ở module khác chưa được khai báo. | So khớp `package`/`import`, kiểm tra dependency Maven và đường dẫn nguồn. |
| `cannot find symbol` | Sai tên lớp/phương thức, chưa import, class chưa được compile hoặc thiếu dependency. | Đọc lỗi cụ thể, kiểm tra tên đúng chữ hoa/chữ thường và phạm vi `public`. |
| `class App is public, should be declared in a file named App.java` | Tên file và top-level public class không trùng. | Đổi tên file thành `App.java`. |
| `Could not find or load main class` | Dùng tên lớp thiếu package hoặc classpath sai. | Chạy `java -cp target/classes com.example.catalog.App` sau `mvn compile`. |
| `java -jar ...` báo thiếu main manifest | JAR không được cấu hình `Main-Class`. | Với ví dụ này dùng `java -cp ... com.example.catalog.App`; cấu hình manifest khi có yêu cầu executable JAR. |
| Test không tìm thấy code chính | Nguồn test/production đặt sai root; build/IDE chưa cập nhật. | Kiểm tra `src/test/java`, `src/main/java` và chạy lại lifecycle phù hợp. |
| Code bị mất sau `mvn clean` | Vô tình đặt/sửa mã trong `target`. | Chuyển bản nguồn chính vào `src/main/java` và dùng Git để quản lý. |
| Package con không truy cập được package-private | Xem package con như cùng một package với package cha. | Chọn API `public` cần thiết hoặc tái tổ chức mã có chủ đích. |

Nếu build thất bại, hãy đọc **lỗi Maven/Java đầu tiên có liên quan** và đường dẫn file được báo. Việc xóa cache hoặc thay đổi cấu hình POM hàng loạt thường không giải quyết lỗi package/source root.

## 11. Checklist tự kiểm tra

Sau khi tạo hoặc chỉnh sửa module Maven, tự xác nhận:

- `pom.xml` nằm tại gốc của module cần build; đang chạy Maven từ đúng thư mục.
- Mã Java chính nằm dưới `src/main/java`, tài nguyên dưới `src/main/resources`, test dưới `src/test/java`.
- Mỗi file Java có `package` phù hợp cấu trúc thư mục và tên file phù hợp top-level public class.
- Khi gọi lớp từ package khác, `import` đúng và quyền truy cập cho phép.
- Tên package viết thường và phản ánh ranh giới có ích; không nhầm với `groupId`/`artifactId`.
- `mvn clean compile` hoặc `mvn clean verify` chạy đúng JDK; `target/classes` được sinh, không sửa thủ công.
- Trong dự án đa module, mỗi nguồn thuộc đúng module và dependency giữa các module được khai báo rõ.

**Kết quả cần hiểu:** `src/main/java` giúp Maven xác định **nguồn nào thuộc ứng dụng/thư viện chính**; câu lệnh `package` giúp Java xác định **lớp thuộc namespace nào**. Phối hợp đúng hai quy ước tạo dự án dễ biên dịch, import, kiểm thử, đóng gói và bảo trì.

## Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout)
- [Apache Maven — Getting Started Guide](https://maven.apache.org/guides/getting-started/)
- [Apache Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/)
- [Oracle — Naming a Package](https://docs.oracle.com/javase/tutorial/java/package/namingpkgs.html)
