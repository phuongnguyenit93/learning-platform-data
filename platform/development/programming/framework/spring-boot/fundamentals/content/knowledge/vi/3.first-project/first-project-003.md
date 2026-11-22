# Group, artifact, package, phiên bản và lựa chọn build tool

Khi tạo **dự án Spring Boot đầu tiên**, một trong những màn hình quan trọng nhất là phần khai báo thông tin dự án: **Group**, **Artifact**, **Name**, **Package name**, **Version**, **Java**, **Spring Boot** và **Build tool**. Các trường này trông giống nhau vì đều là tên hoặc phiên bản, nhưng mỗi trường có trách nhiệm riêng. Chọn đúng từ đầu giúp mã nguồn có cấu trúc dễ hiểu, dependency được quản lý nhất quán và bản đóng gói có danh tính rõ ràng.

Bài học này giải thích ý nghĩa của từng trường, mối quan hệ giữa chúng, cách chọn Maven hoặc Gradle, và cách nhận diện các giá trị tương ứng trong dự án đã được tạo.

## 1. Một dự án Spring Boot có nhiều loại danh tính

Giả sử cần tạo dịch vụ quản lý danh mục sản phẩm cho công ty giả định Acme. Ta có thể khai báo:

| Trường | Giá trị ví dụ | Vai trò chính |
| --- | --- | --- |
| Group | `com.acme` | Nhóm/tổ chức sở hữu artifact trong hệ sinh thái build |
| Artifact | `catalog-service` | Định danh module hoặc sản phẩm được build |
| Name | `Catalog Service` | Tên mô tả dự án cho con người |
| Package name | `com.acme.catalog` | Không gian tên của các lớp Java |
| Version của dự án | `0.1.0-SNAPSHOT` | Phiên bản của artifact do dự án tạo ra |
| Packaging | `Jar` | Kiểu đóng gói ứng dụng |
| Java | `21` | Phiên bản Java mục tiêu của dự án ví dụ |
| Spring Boot | `3.3.5` | Phiên bản framework Boot dùng trong ví dụ |
| Build tool | `Maven` hoặc `Gradle` | Công cụ quản lý dependency, kiểm thử và đóng gói |

**Các con số phiên bản trong bài chỉ dùng để minh họa cấu hình nhất quán, không phải khẳng định đó là bản mới nhất.** Khi tạo một dự án thực tế, cần chọn bản Spring Boot còn được hỗ trợ và kiểm tra khả năng tương thích với Java, plugin và thư viện đang sử dụng.

Mối quan hệ quan trọng nhất là:

```text
Maven/Gradle project
  Group:    com.acme
  Artifact: catalog-service
  Version:  0.1.0-SNAPSHOT
        |
        +--> Tọa độ artifact: com.acme:catalog-service:0.1.0-SNAPSHOT
        |
        +--> Source code: src/main/java/com/acme/catalog/...
                               ^^^^^^^^^^^^^^^^
                            Package name riêng
        |
        +--> Ứng dụng được build và chạy bằng Java + Spring Boot
```

Trong ba phần đầu của tọa độ artifact, **group + artifact + version** xác định một bản của sản phẩm trong hệ quản lý dependency. **Package name** lại xác định namespace của mã nguồn Java. Hai khái niệm có thể liên quan theo quy ước đặt tên, nhưng không phải cùng một giá trị và không thay thế cho nhau.

## 2. Group: định danh nhóm sở hữu dự án

### 2.1. Group có ý nghĩa gì?

Trong Maven, group được khai báo bằng `groupId`; trong Gradle, thường khai báo bằng thuộc tính `group`. Group giúp phân biệt artifact của một tổ chức, đội hoặc hệ sản phẩm với artifact của đơn vị khác.

Quy ước thông dụng là viết theo tên miền đảo ngược:

- Công ty sở hữu `acme.com` có thể dùng `com.acme`.
- Một tổ chức sở hữu `example.org` có thể dùng `org.example`.
- Một nhóm sản phẩm có thể chọn group cụ thể hơn, chẳng hạn `com.acme.platform`.

Đây là **quy ước đặt tên**, không phải yêu cầu rằng project phải chạy trên tên miền đó. Mục đích là giảm khả năng trùng định danh giữa các thư viện và hệ thống.

Ví dụ một tổ chức phát triển ba module:

```text
com.acme:catalog-service:0.1.0-SNAPSHOT
com.acme:order-service:0.2.0-SNAPSHOT
com.acme:common-utils:1.0.0
```

Cả ba cùng group nhưng có artifact khác nhau. Nếu đưa các module lên Maven repository nội bộ, group giúp quản lý và tra cứu artifact theo nhóm sở hữu.

### 2.2. Chọn group cho dự án đầu tiên

Với bài tập cá nhân, có thể dùng `com.example`, `org.example` hoặc một group mang tính học tập. Với dự án dùng lâu dài, nên chọn group ổn định, thuộc tổ chức hoặc phạm vi bạn thực sự quản lý. Nếu nhóm đã có quy ước thì dùng đúng quy ước đó để tránh các module cùng sản phẩm mang group khác nhau.

**Group không quyết định ứng dụng lắng nghe cổng nào, URL của REST API là gì hoặc môi trường nào sẽ chạy ứng dụng.** Nó là thông tin phục vụ định danh và quản lý artifact.

## 3. Artifact: tên định danh sản phẩm được build

### 3.1. Artifact khác Group như thế nào?

Trong Maven, `artifactId` là tên của sản phẩm được build. Trong Gradle, tên project được khai báo qua `rootProject.name` đối với project đơn hoặc tên subproject trong bản build nhiều module; tên đó thường đảm nhiệm vai trò định danh artifact khi xuất bản.

Ví dụ:

```text
Group:    com.acme
Artifact: catalog-service
Version:  0.1.0-SNAPSHOT
```

Tọa độ Maven của artifact:

```text
com.acme:catalog-service:0.1.0-SNAPSHOT
```

Tên tệp JAR được tạo ra thường chứa artifact và version, chẳng hạn:

```text
catalog-service-0.1.0-SNAPSHOT.jar
```

Tuy nhiên, tên tệp đầu ra có thể được cấu hình lại. **Đừng dùng tên JAR quan sát được làm định nghĩa duy nhất của artifactId**; hãy đọc cấu hình build để biết danh tính dự án.

### 3.2. Quy ước đặt Artifact

Nên chọn tên ngắn, có nghĩa, dễ đọc, phản ánh trách nhiệm của module:

| Tên | Nhận xét |
| --- | --- |
| `catalog-service` | Mô tả rõ một dịch vụ danh mục |
| `billing-api` | Thể hiện một API liên quan tới thanh toán |
| `shared-validation` | Phù hợp với thư viện validation dùng chung |
| `project1` | Khó nhận biết mục đích khi có nhiều dự án |
| `spring-boot-demo-final-v2-new` | Chứa quá nhiều thông tin tạm thời, khó duy trì |

Dấu gạch nối `-` rất phổ biến trong artifactId. Nhưng dấu này **không hợp lệ trong tên package Java**. Vì vậy `catalog-service` là artifact phù hợp, còn `com.acme.catalog-service` không thể là một khai báo package Java.

### 3.3. Artifact và Name không đồng nghĩa

Trường `Name` thường là tên hiển thị hoặc mô tả dự án được công cụ tạo project dùng để sinh metadata. Ví dụ:

```text
Artifact = catalog-service
Name     = Catalog Service
```

Trong Maven, `<name>Catalog Service</name>` có thể xuất hiện trong `pom.xml`. Trong Gradle, tên project và phần mô tả là những thuộc tính có thể được cấu hình riêng. Thay đổi tên hiển thị không tự đổi tất cả Java package, tên artifact đã publish, URL hay cổng chạy.

Nếu có trường `Description`, có thể điền một câu mô tả như `Service for product catalog management`. Mô tả giúp người đọc hiểu dự án; nó không bổ sung tính năng nghiệp vụ.

## 4. Package name: không gian tên của mã Java

### 4.1. Package là gì?

Java sử dụng package để tổ chức class, tránh xung đột tên và hỗ trợ phạm vi truy cập giữa các thành phần. Ví dụ:

```java
package com.acme.catalog;

public class CatalogApplication {
}
```

Khai báo package ở đầu tệp cho biết class thuộc namespace `com.acme.catalog`. Vị trí đặt source thông thường tương ứng:

```text
src/main/java/com/acme/catalog/CatalogApplication.java
```

Tên package thường viết chữ thường, các phần ngăn cách bằng dấu chấm, và từng phần phải là định danh Java hợp lệ. Không dùng dấu gạch nối `-`, khoảng trắng hoặc một từ khóa Java làm tên phần package.

### 4.2. Vì sao Package name không nhất thiết giống Group + Artifact?

Nhiều công cụ khởi tạo đề xuất package dựa trên group và artifact. Chẳng hạn, nếu artifact là `catalog-service`, công cụ có thể biến phần chứa gạch nối thành một định danh Java hợp lệ. Nhưng nhóm phát triển có thể chủ động chọn:

```text
Group        com.acme
Artifact     catalog-service
Package name com.acme.catalog
```

Giá trị này hoàn toàn hợp lý. Đổi artifactId không bắt buộc đổi package; ngược lại, tái cấu trúc package cũng không tự đổi tọa độ artifact đã công bố. Cần xem chúng là **hai quyết định riêng**.

### 4.3. Package gốc ảnh hưởng tới Spring Boot như thế nào?

Một ứng dụng Spring Boot thường đặt class có `@SpringBootApplication` ở package gốc. Cấu trúc minh họa:

```text
com.acme.catalog
├── CatalogApplication
├── product
│   ├── ProductService
│   └── ProductController
└── config
    └── CatalogConfiguration
```

```java
package com.acme.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Theo cách tổ chức thông thường, `@SpringBootApplication` bao gồm cơ chế component scan bắt đầu từ package của class này và các package con. Vì thế các component đặt dưới `com.acme.catalog.product` có thể được tìm thấy khi có annotation phù hợp. Một `@Service` nằm ở package anh em `com.acme.shared` **không tự nằm trong phạm vi scan mặc định** của `com.acme.catalog`.

Điểm này giúp hiểu vì sao vị trí class khởi động quan trọng. Khi cần thay đổi phạm vi scan, phải cấu hình rõ ràng theo cấu trúc dự án; không nên sửa group hoặc artifact với hy vọng component scan sẽ tự thay đổi.

### 4.4. Package có phải địa chỉ triển khai không?

Không. Ví dụ `com.acme.catalog` là tên Java package, không phải domain thật của API. Địa chỉ như `https://catalog.acme.com` thuộc cấu hình DNS, mạng, proxy và triển khai. Một dịch vụ có thể đổi domain nhưng giữ nguyên Java package; và nhiều dịch vụ có thể cùng convention package mà chạy trên các hostname khác nhau.

## 5. Phân biệt các loại phiên bản

Khi thấy nhiều con số như `0.1.0-SNAPSHOT`, `3.3.5`, `21` và `8.x`, hãy xác định chúng đang nói đến **sản phẩm nào**:

| Loại phiên bản | Ví dụ | Điều nó mô tả |
| --- | --- | --- |
| Project version | `0.1.0-SNAPSHOT` | Bản của chính `catalog-service` |
| Spring Boot version | `3.3.5` | Phiên bản Spring Boot plugin, parent/BOM và các thành phần Boot liên quan |
| Java version | `21` | Phiên bản Java mục tiêu/công cụ biên dịch theo cấu hình |
| Maven/Gradle version | Theo Maven hoặc Gradle Wrapper | Phiên bản của chương trình thực hiện build |
| Dependency version | Ví dụ một thư viện `x.y.z` | Phiên bản của một dependency cụ thể |

Những loại phiên bản này **không buộc phải bằng nhau**. Dự án version `0.1.0-SNAPSHOT` có thể dùng Spring Boot `3.3.5` và Java `21`. Khi nâng Spring Boot, version ứng dụng chỉ thay đổi nếu nhóm chủ động cập nhật. Khi phát hành ứng dụng bản `1.0.0`, không có yêu cầu phải đổi phiên bản Java lên `1.0.0`.

### 5.1. Project version và hậu tố SNAPSHOT

Một cách đặt phiên bản phổ biến là `MAJOR.MINOR.PATCH`, chẳng hạn:

- `0.1.0`: bản thử nghiệm ban đầu do nhóm đặt.
- `0.2.0`: bản có thêm tính năng theo quy ước của nhóm.
- `1.0.0`: bản ổn định theo chính sách phát hành đã chọn.
- `1.0.0-SNAPSHOT`: bản đang phát triển, chưa được coi là bản release cố định.

`-SNAPSHOT` có ý nghĩa đặc biệt trong hệ sinh thái Maven: cùng một tọa độ snapshot có thể tham chiếu các bản build đang thay đổi trong snapshot repository. Gradle cũng có thể sử dụng tọa độ mang `-SNAPSHOT` khi làm việc với Maven repository.

Quy tắc tăng phiên bản theo semantic versioning là **chính sách do nhóm áp dụng**, không phải hành vi Spring Boot tự kiểm chứng. Spring Boot không tự xem mã nguồn rồi tăng version giúp bạn. Việc build được `0.1.0` cũng không có nghĩa bản đó đã được xuất bản lên repository hoặc triển khai production.

### 5.2. Spring Boot version

Phiên bản Spring Boot quyết định các khả năng, yêu cầu tương thích và tập dependency được Boot quản lý theo từng dòng phát hành. Khi chọn phiên bản cần cân nhắc:

- Mức Java tối thiểu và các phiên bản Java mà dòng Boot đó hỗ trợ.
- Các thư viện/framework liên quan và khả năng tương thích.
- Tình trạng hỗ trợ bảo trì và chính sách nâng cấp của dự án.
- Yêu cầu từ team, template hoặc hệ thống build sẵn có.

Không nên chọn phiên bản chỉ vì nó có con số lớn nhất, rồi mặc định rằng mọi dependency cũ vẫn hoạt động. Khi nâng từ một dòng Boot sang dòng khác, cần đọc hướng dẫn di chuyển và chạy bộ kiểm thử phù hợp.

### 5.3. Java version

Giá trị Java trong công cụ tạo project thường dùng để cấu hình mục tiêu biên dịch hoặc toolchain. Ví dụ chọn Java `21` nghĩa là dự án ví dụ được định hướng dùng bộ công cụ Java 21.

Điều này **khác** với phiên bản Java đang thực sự được dùng để chạy Maven/Gradle hay ứng dụng trên máy:

```bash
java -version
```

Lệnh trên cho biết Java executable hiện được chọn trên môi trường chạy lệnh. Muốn build ổn định, cần đảm bảo JDK phù hợp cho công cụ build, toolchain và ứng dụng theo yêu cầu của Spring Boot đã chọn. Nếu chọn Java mục tiêu cao hơn khả năng của JDK đang dùng hoặc không có toolchain tương thích, quá trình build có thể lỗi.

### 5.4. Phiên bản dependency và BOM

Một Spring Boot project thường sử dụng dependency management từ `spring-boot-starter-parent`/`spring-boot-dependencies` (Maven) hoặc cơ chế tương đương trong Gradle. BOM (*Bill of Materials*) xác định một tập phiên bản thư viện đã được phối hợp cho dòng Boot đó.

Ví dụ dependency thường không cần chỉ rõ version riêng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Trong dự án có dependency management phù hợp, phiên bản sẽ được quản lý tập trung. Không phải mọi thư viện bên ngoài đều nằm trong BOM; với thư viện không được quản lý, có thể cần chọn version rõ ràng. Tự ghi đè nhiều version có sẵn trong BOM mà không kiểm tra tương thích có thể tạo ra xung đột.

## 6. Build tool: Maven hay Gradle?

**Build tool** là công cụ đọc cấu hình dự án, giải dependency, biên dịch source, chạy test, xử lý tài nguyên và tạo artifact. Spring Boot có thể làm việc với cả Maven lẫn Gradle; chọn một công cụ không làm thay đổi ý nghĩa của `@SpringBootApplication` hay cách DI hoạt động.

### 6.1. Maven

Maven dùng `pom.xml` để mô tả project metadata, dependency, plugin và quá trình build theo các phase/lifecycle quen thuộc. Những lệnh phổ biến gồm:

```bash
./mvnw test
./mvnw package
./mvnw spring-boot:run
```

Một số đặc điểm:

- File cấu hình XML rõ ràng về cấu trúc; nhiều dự án Java doanh nghiệp có sẵn conventions và hệ thống publish bằng Maven.
- Các phase chuẩn như `compile`, `test`, `package`, `verify` giúp chia sẻ cách chạy tác vụ.
- Plugin Maven thực hiện các chức năng như compile, test, package và đóng gói executable Boot JAR.
- Cấu hình có thể dài hơn khi dự án cần nhiều quy tắc build đặc biệt.

Maven phù hợp khi nhóm đã dùng Maven, muốn cấu hình mang tính quy ước cao, hoặc học các khái niệm build Java theo lifecycle của Maven.

### 6.2. Gradle

Gradle dùng `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL), trong khi `settings.gradle`/`settings.gradle.kts` thường xác định tên và cấu trúc project. Lệnh phổ biến:

```bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
```

Một số đặc điểm:

- Hỗ trợ mô hình task linh hoạt, thuận tiện khi dự án có bước build tùy chỉnh.
- Có cơ chế incremental build, cache và cấu hình cho nhiều project; hiệu quả thực tế phụ thuộc plugin và cấu hình.
- Có hai DSL để chọn; ví dụ Groovy và Kotlin có cú pháp khác nhau dù có thể cấu hình cùng chức năng.
- Cần hiểu task, plugin và dependency configuration khi tùy chỉnh quá trình build.

Gradle phù hợp khi team đã chuẩn hóa Gradle, dự án có nhiều module hoặc cần thiết kế build logic riêng. **Không có kết luận phổ quát rằng Maven hay Gradle luôn nhanh hơn hoặc luôn tốt hơn**; một bản build cụ thể phụ thuộc vào quy mô, dependency, cache, plugin và máy chạy.

### 6.3. Bảng lựa chọn thực dụng

| Tiêu chí | Maven | Gradle |
| --- | --- | --- |
| File build cơ bản | `pom.xml` | `build.gradle` hoặc `build.gradle.kts` |
| Cách mô tả | XML và mô hình lifecycle/plugin | DSL và mô hình task/plugin |
| Lệnh build thường gặp | `./mvnw package` | `./gradlew build` hoặc `./gradlew bootJar` |
| Chạy Boot lúc phát triển | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Quản lý dependency | `<dependencies>`, parent/BOM | `dependencies { ... }`, platform/plugin |
| Công việc build tùy biến | Qua plugin và cấu hình | Qua task và plugin |
| Hướng chọn cho người mới | Tốt khi muốn bám vào vòng đời Maven hoặc template của team | Tốt khi muốn học task DSL hoặc theo hệ Gradle sẵn có |

Khi làm dự án đầu tiên, lựa chọn tốt nhất thường là **công cụ đang được tài liệu, nhóm hoặc kho mã mục tiêu sử dụng**. Chỉ cần nắm chắc một công cụ trước; hoàn toàn có thể học công cụ còn lại sau. Đừng trộn `pom.xml` và `build.gradle` rồi cho rằng hai file sẽ tự đồng bộ dependency.

## 7. Thực hành tạo dự án với Spring Initializr

<https://start.spring.io/> là một công cụ tạo bộ khung Spring Boot project. Trong một lần khởi tạo, ta có thể chọn:

| Tùy chọn | Giá trị ví dụ | Lý do |
| --- | --- | --- |
| Project | Maven | Bắt đầu với `pom.xml` |
| Language | Java | Dùng Java làm ngôn ngữ nguồn |
| Spring Boot | Một bản tương thích với Java đã chọn | Cố định nền tảng Boot cho ví dụ |
| Group | `com.acme` | Định danh tổ chức |
| Artifact | `catalog-service` | Định danh artifact |
| Name | `Catalog Service` | Tên mô tả |
| Description | `Learning Spring Boot project metadata` | Giải thích mục đích |
| Package name | `com.acme.catalog` | Package gốc để chứa source |
| Packaging | Jar | Dạng đóng gói thông dụng cho ứng dụng độc lập |
| Java | 21 | Java mục tiêu của ví dụ |
| Dependencies | Spring Web (nếu muốn thử HTTP) | Có web starter để chạy ứng dụng HTTP |

Các lựa chọn trong giao diện phụ thuộc phiên bản mà Initializr đang cung cấp. Để đọc hai file cấu hình cụ thể ở phần tiếp theo, bài sử dụng **Spring Boot 3.3.5 và Java 21 làm bộ ví dụ nhất quán**.

Sau khi nhấn Generate và giải nén, bạn sẽ có một dự án với file build, script wrapper, thư mục source và class ứng dụng. Công cụ tạo project giúp chuẩn bị **bộ khung**; nó chưa tự viết quy trình nghiệp vụ cho sản phẩm.

### 7.1. Nhận diện cấu trúc sau khi tạo

Một dự án Maven có thể trông như sau:

```text
catalog-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/com/acme/catalog/
│   │   │   └── CatalogServiceApplication.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/com/acme/catalog/
│           └── CatalogServiceApplicationTests.java
└── ...
```

Với Gradle, thường thay `pom.xml` bằng `build.gradle` hoặc `build.gradle.kts` và file settings tương ứng; wrapper là `gradlew`, `gradlew.bat` cùng thư mục `gradle/wrapper/`.

Tên chính xác của class khởi động có thể do công cụ khởi tạo sinh ra từ artifact hoặc name; nó **không bị buộc phải là** `CatalogServiceApplication`. Quy tắc quan trọng là package/class khai báo hợp lệ và class chứa `@SpringBootApplication` được định vị đúng.

### 7.2. Packaging: Jar hay War?

Với ứng dụng Spring Boot mới, `Jar` thường là lựa chọn phù hợp để khởi chạy độc lập bằng `java -jar` khi project được cấu hình đóng gói executable JAR. Các starter web thông dụng có thể cung cấp máy chủ nhúng, nên ứng dụng web có thể chạy độc lập.

`War` thường được xem xét khi cần triển khai ứng dụng Servlet vào application server tương thích theo yêu cầu môi trường. Chọn WAR có thể kéo theo điều chỉnh dependency và cấu hình khởi tạo. **Packaging là quyết định về cách phân phối ứng dụng**, không phải một cách đặt tên khác của group, artifact hay package.

## 8. Xem cùng một dự án dưới dạng Maven

Đây là một ví dụ `pom.xml` rút gọn nhưng thể hiện đầy đủ các trường chính của project Maven với Spring Web:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-service</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>Catalog Service</name>
    <description>Learning Spring Boot project metadata</description>

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
```

Phân tích từng lớp thông tin:

1. Phần `<parent>` nói dự án dùng Spring Boot starter parent phiên bản `3.3.5`. Parent này hỗ trợ plugin configuration và dependency management để khai báo project gọn hơn.
2. `<groupId>`, `<artifactId>` và `<version>` ngay dưới `<project>` tạo nên danh tính của **ứng dụng đang viết**. Không được nhầm chúng với tọa độ `org.springframework.boot:spring-boot-starter-parent:3.3.5` của parent.
3. `<java.version>21</java.version>` khai báo mục tiêu Java theo quy ước của parent Boot; JDK thực tế vẫn phải phù hợp khi build/chạy.
4. `spring-boot-starter-web` cung cấp nhóm dependency cho ứng dụng web; không có `<version>` riêng vì phần quản lý phiên bản đã được parent xử lý.
5. `spring-boot-starter-test` được khai báo với scope `test` vì phục vụ mã kiểm thử.
6. `spring-boot-maven-plugin` hỗ trợ tác vụ Boot như khởi chạy và đóng gói ứng dụng executable.

Điểm dễ nhầm: có nhiều `<version>` trong cùng một POM. `<parent><version>...` là phiên bản parent, còn `<project><version>...` của project con là phiên bản artifact do bạn xây dựng.

### 8.1. Chạy dự án Maven

Trên macOS/Linux, tại thư mục gốc dự án:

```bash
./mvnw test
./mvnw spring-boot:run
./mvnw package
java -jar target/catalog-service-0.1.0-SNAPSHOT.jar
```

Trên Windows PowerShell, script wrapper tương ứng là:

```powershell
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
.\mvnw.cmd package
java -jar target\catalog-service-0.1.0-SNAPSHOT.jar
```

`test` chạy các bài kiểm thử theo cấu hình Maven. `spring-boot:run` chạy ứng dụng ở chế độ phát triển. `package` tạo bản đóng gói trong `target/`; với cấu hình Spring Boot Maven plugin phù hợp, file JAR được repackage để chạy bằng `java -jar`.

Nếu chọn Spring Web nhưng chưa viết controller, ứng dụng có thể khởi động HTTP server thành công trong khi truy cập `/` vẫn nhận phản hồi 404. **Khởi động thành công không đồng nghĩa đã có endpoint nghiệp vụ.**

## 9. Xem cùng một dự án dưới dạng Gradle

Nếu chọn **Gradle - Groovy** ở Initializr, các thông tin tương đương có thể xuất hiện như sau.

`settings.gradle`:

```groovy
rootProject.name = 'catalog-service'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.acme'
version = '0.1.0-SNAPSHOT'
description = 'Learning Spring Boot project metadata'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở đây:

- `rootProject.name` là tên project, tương ứng với `catalog-service`.
- `group` và `version` có vai trò tương tự `groupId` và `version` của ứng dụng Maven.
- Plugin `org.springframework.boot` mang phiên bản Boot trong cấu hình Gradle.
- Plugin `io.spring.dependency-management` ở ví dụ giúp áp dụng quản lý dependency phù hợp với plugin Boot. Gradle còn có cách sử dụng BOM bằng `platform(...)`; không cần kết hợp nhiều cách quản lý version nếu chưa hiểu chúng.
- `java.toolchain` đặt ngôn ngữ Java mục tiêu cho các tác vụ sử dụng toolchain; Gradle có thể cần JDK tương ứng hoặc cơ chế cung cấp toolchain phù hợp.
- `implementation` và `testImplementation` phân biệt dependency được dùng bởi mã ứng dụng với dependency phục vụ mã kiểm thử.
- `bootRun` và `bootJar` là task do Spring Boot Gradle plugin cung cấp.

`1.1.6` trong ví dụ là **phiên bản plugin dependency-management**, không phải project version hay Spring Boot version. Với dự án thật, hãy sử dụng cặp plugin và phiên bản được bộ khung/đội dự án xác nhận là tương thích.

### 9.1. Chạy dự án Gradle

Trên macOS/Linux:

```bash
./gradlew test
./gradlew bootRun
./gradlew bootJar
java -jar build/libs/catalog-service-0.1.0-SNAPSHOT.jar
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
.\gradlew.bat bootJar
java -jar build\libs\catalog-service-0.1.0-SNAPSHOT.jar
```

Với cấu hình ví dụ, `bootJar` tạo executable Boot JAR trong `build/libs/`. `build` thường chạy một vòng đời task rộng hơn, bao gồm các bước kiểm tra thích hợp; `bootJar` tập trung tạo artifact có thể thực thi. Đường dẫn và tên JAR ở trên là kết quả điển hình, có thể thay đổi khi build configuration được tùy chỉnh.

### 9.2. Maven và Gradle tạo được cùng ứng dụng không?

Có. Nếu group, project version, package, Java, Spring Boot và dependency được cấu hình tương đương, cả hai công cụ có thể tạo ứng dụng với cùng ý nghĩa nghiệp vụ. Điều khác nhau chủ yếu là **cách định nghĩa và thực hiện build**.

Không nên tạo cả hai bản build rồi chỉnh một bên mà bỏ quên bên còn lại. Khi phải đổi công cụ cho một repository, đó là công việc chuyển đổi build cần quản lý rõ ràng, không chỉ đổi phần đuôi tên file.

## 10. Wrapper: vì sao nên dùng khi làm dự án đầu tiên?

Trong dự án Initializr, Maven Wrapper hoặc Gradle Wrapper là tập script và cấu hình cho phép nhóm khởi chạy một phiên bản build tool nhất định mà không phải dựa hoàn toàn vào một bản Maven/Gradle được cài toàn cục.

| Build tool | Script macOS/Linux | Script Windows | Cấu hình wrapper thường gặp |
| --- | --- | --- | --- |
| Maven | `mvnw` | `mvnw.cmd` | `.mvn/wrapper/` |
| Gradle | `gradlew` | `gradlew.bat` | `gradle/wrapper/gradle-wrapper.properties` |

Ví dụ, khi dùng `./gradlew bootJar`, wrapper chọn Gradle distribution theo cấu hình wrapper của dự án. Khi dùng `gradle bootJar`, hệ thống thường dùng Gradle được cài và tìm thấy trong môi trường hiện tại. Sự khác biệt này có thể khiến hai máy build theo hai phiên bản Gradle khác nhau.

Wrapper giúp lặp lại build ổn định hơn, nhưng **không tự giải quyết mọi yếu tố môi trường**: JDK, kết nối mạng lần tải đầu tiên, các repository cần truy cập, credential và hệ điều hành vẫn có thể ảnh hưởng kết quả. Với dự án nhóm, cần lưu các file wrapper cần thiết trong repository và chỉ dùng nguồn tải đáng tin cậy.

## 11. Tên project khi build, khi chạy và khi triển khai

Một điểm dễ gây nhầm là **artifactId không tự trở thành mọi tên của ứng dụng trong hệ thống**. Xem ví dụ:

| Ngữ cảnh | Giá trị có thể gặp | Cấu hình/ý nghĩa |
| --- | --- | --- |
| Tọa độ dependency | `com.acme:catalog-service:0.1.0-SNAPSHOT` | Group, artifact và version |
| Tệp executable JAR | `catalog-service-0.1.0-SNAPSHOT.jar` | Quy tắc tên artifact của build |
| Java main class | `com.acme.catalog.CatalogApplication` | Package và class Java |
| Spring application name | `catalog-service` | Có thể khai báo qua `spring.application.name` |
| HTTP port | `8080`, hoặc cổng khác | Cấu hình web server/môi trường |
| Hostname production | `catalog.acme.com` | DNS và hạ tầng triển khai |
| Container image | Ví dụ `registry.example/catalog-service:0.1.0` | Quy ước registry/container, cấu hình riêng |

Có thể đặt Spring application name trong `application.yml`:

```yaml
spring:
  application:
    name: catalog-service
```

Giá trị này là metadata Spring nhận khi chạy, không phải thao tác đổi artifactId trong `pom.xml` hoặc `build.gradle`. Dù ta thường chọn các tên giống nhau để dễ truy vết, **mỗi giá trị có vòng đời và nơi cấu hình riêng**.

## 12. Những lỗi phổ biến khi khai báo dự án

### Lỗi 1: dùng dấu gạch nối trong Java package

```text
Group        com.acme
Artifact     catalog-service
Package name com.acme.catalog-service  <- không hợp lệ trong Java
```

Cách sửa: giữ artifact `catalog-service` và chọn package `com.acme.catalog` hoặc `com.acme.catalogservice`.

### Lỗi 2: tưởng version của project là version Spring Boot

```text
Project version     0.1.0-SNAPSHOT
Spring Boot version 3.3.5
Java version        21
```

Ba con số này có nhiệm vụ riêng. Thay version ứng dụng không tự nâng Spring Boot; thay phiên bản Boot không tự sửa project release policy.

### Lỗi 3: đổi package trong giao diện nhưng source đặt ở package khác

Nếu class có `@SpringBootApplication` nằm trong `com.acme.catalog.app`, còn các component khác ở `com.acme.catalog.service`, cơ chế scan mặc định từ class ứng dụng có thể không tìm thấy chúng. Hãy đặt class khởi động ở package gốc phù hợp, ví dụ `com.acme.catalog`, hoặc chủ động định nghĩa phạm vi scan với lý do rõ ràng.

### Lỗi 4: chọn plugin/dependency mà không xem khả năng tương thích

Một dự án có thể khai báo Java version, Spring Boot version và Gradle/Maven plugin không tương thích. Khi đó lỗi build thường xuất hiện trước khi mã nghiệp vụ được chạy. Cần xác định **cặp phiên bản công cụ và framework được hỗ trợ**, thay vì đổi ngẫu nhiên một version cho tới khi build được.

### Lỗi 5: tin rằng một starter tự tạo đầy đủ tính năng

Thêm `spring-boot-starter-web` cung cấp stack web thông dụng, nhưng vẫn cần controller để có API hữu ích. Thêm một starter truy cập dữ liệu không tự tạo database hoặc dữ liệu nghiệp vụ. Build tool kéo dependency vào project; tính năng thực tế còn cần cấu hình và mã nguồn.

### Lỗi 6: đổi Group/Artifact như đổi tên thư mục đơn giản

Trong dự án đã xuất bản thư viện hay có module khác phụ thuộc, group/artifact/version là một phần của **hợp đồng dependency**. Đổi một trong các giá trị này có thể khiến consumer cần cập nhật tọa độ. Đổi tên thư mục local không nhất thiết sửa metadata publish, và sửa metadata publish không nhất thiết di chuyển Java package.

### Lỗi 7: làm việc với tool toàn cục mà bỏ qua wrapper

Một người dùng Maven/Gradle cài trên máy, người khác dùng wrapper, dẫn tới phiên bản công cụ khác nhau. Với dự án dùng chung, thực hiện các lệnh qua wrapper nhất quán giúp tái lập quy trình build dễ hơn.

## 13. Bài tập áp dụng

### Bài tập A: đọc tọa độ artifact

Cho khai báo:

```text
Group        org.school.learning
Artifact     student-api
Version      0.2.0-SNAPSHOT
Package name org.school.student
```

Hãy xác định:

1. Tọa độ artifact.
2. Tên JAR điển hình nếu dùng quy tắc mặc định.
3. Đường dẫn Java source cho class `StudentApplication`.
4. Vì sao `org.school.student-api` không phù hợp làm package.

**Gợi ý đối chiếu:** tọa độ là `org.school.learning:student-api:0.2.0-SNAPSHOT`; JAR thường có tên `student-api-0.2.0-SNAPSHOT.jar`; class nằm trong `src/main/java/org/school/student/StudentApplication.java`; dấu gạch nối không hợp lệ trong tên package.

### Bài tập B: tìm nơi thay đổi cấu hình

Bạn muốn:

- Đổi phiên bản phát hành của ứng dụng sang `0.3.0-SNAPSHOT`.
- Giữ nguyên Java package đang dùng.
- Đổi tên hiển thị/logical name của ứng dụng khi chạy thành `student-catalog`.
- Chỉ chuyển từ Maven sang Gradle nếu team có lý do rõ ràng.

Hãy chỉ ra file cần xem. **Gợi ý:** version artifact nằm ở `pom.xml` hoặc `build.gradle`; tên Spring application có thể nằm ở `application.properties`/`application.yml`; Java package nằm trong các khai báo `package` ở mã nguồn. Việc đổi build tool là chuyển đổi cấu hình build, không phải thay project version.

### Bài tập C: so sánh hai lựa chọn

Nhóm 1 có repository Maven, CI đã chạy `./mvnw verify` và các thành viên quen `pom.xml`. Nhóm 2 có nhiều module Gradle, dùng chung convention plugin và đã chuẩn hóa `./gradlew build`. Với cùng một chức năng Spring Boot, chọn build tool nào cho mỗi nhóm? Giải thích lựa chọn dựa trên **cấu trúc và quy trình hiện có**, không dựa trên nhận định mơ hồ rằng một công cụ luôn nhanh hoặc hiện đại hơn.

## 14. Tự kiểm tra kiến thức trước khi viết tính năng

Sau bài này, bạn nên giải thích được:

- Vì sao `Group` + `Artifact` + `Version` tạo ra danh tính artifact, còn `Package name` xác định namespace Java.
- Vì sao tên artifact có thể chứa `-` nhưng package không thể chứa dấu đó.
- Điểm khác nhau giữa phiên bản ứng dụng, Spring Boot, Java, plugin build và các dependency.
- Sự khác biệt giữa `pom.xml` và `build.gradle`/`settings.gradle`, cùng một số lệnh build tương ứng.
- Vì sao wrapper quan trọng khi các thành viên sử dụng các máy khác nhau.
- Lý do một ứng dụng build/chạy thành công không mặc nhiên đã có chức năng HTTP, database hay cấu hình triển khai production.

Khi những danh tính và lựa chọn build này đã rõ ràng, việc thêm controller, service, repository, test hoặc các bước đóng gói tiếp theo sẽ dễ quản lý hơn: mỗi thay đổi được đặt vào đúng **tầng mã nguồn, metadata, dependency hoặc môi trường chạy**.
