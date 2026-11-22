# Chọn tọa độ group, artifact, version và tên package cho dự án Spring Boot

## 1. Vì sao cần chọn đúng ngay khi khởi tạo?

Khi tạo dự án bằng Spring Initializr, bạn thường điền **Group**, **Artifact**, **Name**, **Description**, **Package name** và chọn một số phiên bản (Spring Boot, Java). Trong bốn thông tin trọng tâm của bài này:

- **group** định danh tổ chức hoặc không gian dự án trong hệ thống quản lý dependency (Maven/Gradle).
- **artifact** định danh sản phẩm phần mềm cụ thể trong group; thường cũng là tên file JAR được tạo.
- **version** định danh phiên bản phát hành của artifact.
- **package name** là không gian tên Java của các lớp trong mã nguồn, đồng thời ảnh hưởng đến phạm vi quét component mặc định của Spring Boot.

Bốn giá trị có quan hệ, nhưng **không đồng nhất**. Chẳng hạn, một ứng dụng có Maven coordinate `com.acme.platform:order-service:1.2.0` trong khi lớp chính nằm trong package `com.acme.orders`. Cấu hình này có thể hợp lệ; điều quan trọng là quy ước rõ ràng, nhất quán và tránh đụng tên.

## 2. Group: chọn namespace cho artifact

Với Maven, **groupId** cùng **artifactId** và **version** tạo thành tọa độ đầy đủ `groupId:artifactId:version`. Với Gradle, bộ ba `group:name:version` có chức năng tương đương; `name` là tên project, có thể được dùng làm module artifact name khi publish.

Quy ước khuyến nghị cho group là tên miền thuộc quyền tổ chức viết đảo ngược:

| Chủ thể | Ví dụ group | Ý nghĩa |
|---|---|---|
| Công ty sở hữu `acme.com` | `com.acme` | Namespace chung |
| Nền tảng nội bộ | `com.acme.platform` | Phân nhóm artifact theo mảng |
| Tổ chức có miền `example.org` | `org.example` | Namespace theo miền |
| Cá nhân/học tập | `io.github.username` | Có thể dùng khi phù hợp với danh tính xuất bản |

**Đừng tùy ý dùng tên miền của bên khác** nếu định phát hành artifact công khai. Với dự án nội bộ, áp dụng convention do tổ chức quản lý; group không nhất thiết trùng với package Java.

Group nên ổn định qua các lần phát hành của cùng sản phẩm. Đổi group làm thay đổi cách các dự án khác khai báo dependency, kể cả khi tên file hay API của ứng dụng không đổi.

## 3. Artifact: đặt tên đúng cho module/sản phẩm

**artifactId** của Maven thường dùng chữ thường và dấu gạch nối, ví dụ `order-service`, `payment-api`, `inventory-worker`. Nên đặt theo **chức năng hoặc boundary triển khai**, tránh những tên mơ hồ như `project1`, `backend` khi trong tổ chức có nhiều backend.

Ví dụ trong cùng group `com.acme.shop`:

- `catalog-api`: API danh mục.
- `order-service`: xử lý đơn hàng.
- `billing-worker`: worker thanh toán.
- `shared-contracts`: thư viện DTO/giao ước dùng chung.

Trong Spring Initializr, Artifact thường được đề xuất làm tên dự án và ảnh hưởng đến giá trị mặc định của Package name. Tuy nhiên, **artifact với tên package không được áp dụng cùng quy tắc ký tự**: `order-service` là artifact hợp lệ nhưng dấu `-` không hợp lệ trong một định danh package Java; package nên là `com.acme.shop.orders` hoặc `com.acme.shop.orderservice`.

Maven mặc định tạo file giống `order-service-1.2.0.jar` (tùy cấu hình `finalName`, classifier và plugin). Với Spring Boot executable JAR, việc repackaging có thể thay nội dung JAR để chạy bằng `java -jar` nhưng không làm mất ý nghĩa tọa độ Maven.

## 4. Version: phân biệt phiên bản ứng dụng và các phiên bản công cụ

**Project version** là phiên bản của artifact **của bạn**; không phải phiên bản Spring Boot hay Java. Ví dụ:

- `1.0.0-SNAPSHOT`: bản phát triển chưa phát hành ổn định theo quy ước Maven.
- `1.0.0`: bản được đặt mốc phát hành.
- `1.1.0`: bản mới có bổ sung tính năng theo cách đặt phiên bản của nhóm.
- `2.0.0`: một mốc major khi có thay đổi không tương thích theo quy ước Semantic Versioning.

Nếu áp dụng **Semantic Versioning**, cấu trúc phổ biến là `MAJOR.MINOR.PATCH`: major cho thay đổi không tương thích, minor cho chức năng tương thích ngược, patch cho sửa lỗi tương thích ngược. Đừng khẳng định mọi dự án bắt buộc dùng SemVer: đây là quy ước cần được nhóm thống nhất.

Hậu tố `-SNAPSHOT` là convention quan trọng của Maven repository, thường cho phép bản snapshot được cập nhật theo quá trình phát triển; đối với bản release, cần chính sách xuất bản artifact rõ ràng để tránh ghi đè những version đã phát hành. Gradle cũng có thể dùng chuỗi version có `-SNAPSHOT`, nhưng ngữ nghĩa cập nhật phụ thuộc repository và cấu hình resolution.

**Phân biệt bốn phiên bản:**

| Thuộc tính | Ví dụ | Vai trò |
|---|---|---|
| Version dự án | `1.0.0-SNAPSHOT` | Phiên bản của `order-service` |
| Spring Boot version | `3.x.y` | Version framework/plugin/dependency management đã chọn |
| Java version | `17` hoặc `21` | Phiên bản Java mục tiêu được công cụ build sử dụng |
| Dependency version | Theo BOM hoặc khai báo riêng | Version thư viện mà dự án sử dụng |

Chọn bản Spring Boot cụ thể theo yêu cầu tương thích, chính sách hỗ trợ và môi trường triển khai tại thời điểm tạo dự án; không chọn chỉ vì con số cao nhất. Tương tự, Java 17/21 là ví dụ LTS quen thuộc, nhưng phải kiểm tra yêu cầu Java tối thiểu của **phiên bản Spring Boot thực tế** đang dùng.

## 5. Package name: không gian tên và nơi đặt lớp ứng dụng

Package Java thường gồm các đoạn chữ thường, phân cách bằng dấu chấm: `com.acme.shop.orders`. Các đoạn là **định danh Java hợp lệ**, không được chứa dấu gạch nối, khoảng trắng hoặc bắt đầu bằng chữ số; tránh từ khóa Java và tên quá chung. Dùng các tên có nghĩa, thống nhất quy ước tổ chức.

Trong Spring Boot, vị trí lớp gắn `@SpringBootApplication` đặc biệt quan trọng. Theo mặc định, annotation này bao gồm component scan bắt đầu từ **package chứa lớp chính và các package con**. Vì thế hãy đặt lớp chính tại package gốc của phần ứng dụng được Spring quản lý:

```text
src/main/java/
└── com/acme/shop/orders/
    ├── OrdersApplication.java          // @SpringBootApplication
    ├── web/
    │   └── OrderController.java
    ├── service/
    │   └── OrderService.java
    └── repository/
        └── OrderRepository.java
```

Với cách tổ chức này, `com.acme.shop.orders.web` và `com.acme.shop.orders.service` nằm dưới package `com.acme.shop.orders` nên được component scan mặc định xem xét. Một `@Service` đặt ở package anh em `com.acme.shop.billing` **không tự động được quét** chỉ nhờ lớp chính ở `com.acme.shop.orders`. Có thể cấu hình phạm vi scan thủ công khi thật sự cần, nhưng đặt lớp chính đúng chỗ thường đơn giản và dễ bảo trì hơn.

Package name cũng **không phải tên ứng dụng hiển thị khi chạy**, không quyết định `spring.application.name`, và không bắt buộc phải giống `groupId` hay `artifactId`. Chẳng hạn, có thể cấu hình `spring.application.name=order-service` riêng trong `application.properties`.

## 6. Ví dụ chọn bốn giá trị trong Spring Initializr

Giả sử nhóm phát triển một dịch vụ đơn hàng độc lập của công ty Acme, dùng Maven:

| Trường | Giá trị chọn | Lý do |
|---|---|---|
| Group | `com.acme.shop` | Group do tổ chức sở hữu |
| Artifact | `order-service` | Nêu rõ trách nhiệm triển khai |
| Version | `0.1.0-SNAPSHOT` | Bản đầu đang phát triển; thay bằng version chính sách của nhóm |
| Package name | `com.acme.shop.orders` | Định danh Java hợp lệ và gọn; lớp chính nằm tại gốc |
| Name (tùy chọn) | `order-service` | Tên dự án thân thiện |
| Java | `17` | Ví dụ cho một baseline tương thích với Spring Boot 3.x |

**Lưu ý:** `version` của project đôi khi không có ô điền trong giao diện Initializr; hãy sửa trong `pom.xml` hoặc `build.gradle` sau khi sinh project. Giao diện Initializr có thể thay đổi theo phiên bản.

Một `pom.xml` Maven minh họa phần tọa độ của module:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.shop</groupId>
    <artifactId>order-service</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>
</project>
```

Đây là **đoạn POM tối giản để minh họa tọa độ**, không phải project Spring Boot chạy độc lập: để build ứng dụng Spring Boot thực tế cần thêm cấu hình parent hoặc dependency management, các dependency và plugin thích hợp. Với Maven project sinh bởi Initializr, hãy giữ cấu hình Boot đã sinh rồi chỉnh đúng ba trường trên.

Tương đương trong Gradle Groovy DSL, `build.gradle` có thể chứa:

```groovy
group = 'com.acme.shop'
version = '0.1.0-SNAPSHOT'
```

Và `settings.gradle`:

```groovy
rootProject.name = 'order-service'
```

Các đoạn Gradle trên chỉ thể hiện danh tính project; chúng cần nằm trong dự án đã khai báo plugin và dependency Spring Boot phù hợp. Khi publish, artifact name có thể được tùy chỉnh bằng cấu hình publication, nên hãy kiểm tra tọa độ thực tế của publication.

Đối với Java, tạo file `src/main/java/com/acme/shop/orders/OrdersApplication.java` trong project Spring Boot đã sinh:

```java
package com.acme.shop.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Lớp này chạy khi các dependency Spring Boot thích hợp đã có trong project. Không thể `javac OrdersApplication.java` chỉ với JDK trần vì nó import các lớp từ thư viện Spring Boot.

## 7. Cách kiểm tra sau khi tạo dự án

1. Mở `pom.xml` (Maven) hoặc `build.gradle` và `settings.gradle` (Gradle) để đối chiếu group, artifact/project name, version.
2. Kiểm tra dòng `package ...;` trong lớp `*Application.java` và vị trí thư mục `src/main/java` tương ứng.
3. Xác nhận các controller/service/repository dự định quét nằm dưới package của lớp `@SpringBootApplication` hoặc có cấu hình scan tường minh.
4. Kiểm tra Java runtime/toolchain và version Spring Boot có tương thích với nhau và với hạ tầng chạy.
5. Trong dự án đã sinh đầy đủ, chạy `./mvnw clean package` (macOS/Linux), `mvnw.cmd clean package` (Windows) hoặc `./gradlew build` / `gradlew.bat build` theo build tool. Tên file output, test và khả năng tạo executable JAR phụ thuộc cấu hình project.

Maven còn có thể kiểm tra coordinate bằng `./mvnw help:evaluate -Dexpression=project.groupId -q -DforceStdout` (tương tự `project.artifactId`, `project.version`) nếu plugin hỗ trợ và dependencies đã được resolve; không cần dùng lệnh này để xác nhận package Java.

## 8. Những lỗi thường gặp và cách sửa

**Dùng artifact có dấu gạch nối trực tiếp làm package.** `com.acme.order-service` không hợp lệ trong Java. Giữ artifact `order-service` và dùng `com.acme.orders` cho package.

**Nhầm project version với Boot version.** Đổi `<version>` ở mức project không tự nâng Spring Boot. Tìm phiên bản Spring Boot tại `spring-boot-starter-parent` hoặc plugin/version catalog và cấu hình dependency management của build.

**Đặt main class quá sâu trong package.** Nếu main class ở `com.acme.shop.orders.bootstrap` thì component scan mặc định không bao phủ `com.acme.shop.orders.service`. Đưa main class lên `com.acme.shop.orders` hoặc chủ động cấu hình scan.

**Đổi group/artifact sau khi đã có consumer.** Phụ thuộc của các module khác vẫn trỏ đến tọa độ cũ. Khi đổi cần cập nhật build, publication, registry, CI/CD và tài liệu triển khai; cân nhắc chính sách chuyển tiếp.

**Tên artifact quá chung hoặc trùng trong cùng group.** `com.acme:service:1.0.0` khó phân biệt nếu hệ thống có nhiều dịch vụ. Chọn tên theo chức năng và kiểm tra registry của tổ chức trước khi publish.

**Đồng nhất package với Spring application name.** Package Java có dấu chấm trong khi `spring.application.name` thường là tên dịch vụ như `order-service`; cấu hình hai trường độc lập.

## 9. Checklist quyết định trước khi nhấn Generate

- Có namespace group thuộc quyền tổ chức và đúng convention repository?
- Artifact có thể nhận diện chức năng, không trùng sản phẩm khác trong cùng group?
- Version ban đầu phù hợp chu kỳ phát triển và chính sách snapshot/release?
- Package là Java identifier hợp lệ, dễ mở rộng và chứa main class ở gốc phù hợp?
- Đã phân biệt version của artifact, Spring Boot và Java?
- Tên project, coordinate phát hành, package Java và tên dịch vụ runtime có nhất quán về **ý nghĩa**, dù không nhất thiết giống hệt nhau?

**Ví dụ hoàn chỉnh để ghi nhớ:** `com.acme.shop:order-service:0.1.0-SNAPSHOT` là tọa độ Maven, còn `com.acme.shop.orders` là package Java chứa lớp `OrdersApplication`. Chọn mỗi giá trị vì đúng vai trò của nó, rồi kiểm tra build đã sinh trước khi bắt đầu viết chức năng.
