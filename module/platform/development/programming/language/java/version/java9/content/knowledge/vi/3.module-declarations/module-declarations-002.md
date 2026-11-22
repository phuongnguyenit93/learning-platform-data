# Quy tắc đặt tên mô-đun và tổ chức thư mục trong Java (JPMS)

Java Platform Module System (JPMS) được đưa vào Java 9 và vẫn là cơ chế mô-đun chuẩn của các JDK hiện hành. Một named module được khai báo bằng tệp `module-info.java`; tên trong khai báo này là định danh mà các module khác dùng trong `requires` và công cụ Java dùng khi phân giải module. Vì vậy, tên module và cấu trúc thư mục cần rõ ràng, ổn định và nhất quán.

## 1. Phân biệt module, package và module của build tool

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| JPMS module | Nhóm package có ranh giới phụ thuộc và truy cập được khai báo trong `module-info.java`. | `com.acme.catalog.api` |
| Java package | Namespace chứa class/interface; tên package được ánh xạ thành các thư mục con. | `com.acme.catalog.api.Book` |
| Maven/Gradle subproject | Đơn vị cấu hình và xây dựng trong một build nhiều dự án. | `catalog-api`, `:catalog-api` |

Ba khái niệm có thể liên quan nhưng không đồng nhất. Một Maven artifact có `artifactId` là `catalog-api`, thư mục dự án tên `catalog-api`, còn JPMS module có thể tên `com.acme.catalog.api`. Tên JPMS được khai báo trong `module-info.java`; tên thư mục, tên project và tên JAR không tự quyết định tên đó. Một subproject chỉ trở thành named module khi đầu ra của nó có module descriptor phù hợp.

## 2. Quy tắc đặt tên JPMS module

### Cú pháp và cách chọn tên

Tên module là một tên định danh gồm một hoặc nhiều thành phần, phân cách bằng dấu chấm. Mỗi thành phần phải là một Java identifier hợp lệ. Ví dụ:

```java
module com.acme.catalog.api {
    exports com.acme.catalog.api;
}
```

JLS khuyến nghị tên module tương ứng với tên package chính mà module export. Nếu module không có một package export chính, hãy bắt đầu tên bằng dạng đảo ngược của tên miền Internet gắn với tổ chức hoặc tác giả. Quy ước reverse-DNS giúp giảm xung đột tên giữa các thư viện độc lập:

- `com.acme.catalog.api` — API của hệ thống catalog thuộc `acme.com`.
- `com.acme.catalog.persistence` — phần lưu trữ nếu được tách thành một module riêng.
- `org.example.reporting` — module báo cáo của tổ chức dùng miền `example.org`.

### Các quy tắc nên tuân theo

1. **Dùng chữ thường cho các thành phần tên.** Tên package và module thường dùng chữ thường; tên class/interface dùng `UpperCamelCase`. Ví dụ `com.acme.orders.api` và `OrderService`.
2. **Chọn tên duy nhất và có ý nghĩa.** Ưu tiên reverse-DNS, sau đó là tên sản phẩm hoặc trách nhiệm. Tránh tên quá chung như `common`, `utils` hoặc `core` nếu chúng không đủ phân biệt trong hệ thống.
3. **Không dùng `java` làm thành phần đầu tiên.** Các tên package/module bắt đầu bằng `java` được dành riêng cho nền tảng Java SE. Module ứng dụng nên dùng namespace của tổ chức, chẳng hạn `com.acme...` hoặc `org.example...`.
4. **Không dùng dấu gạch ngang, khoảng trắng hoặc dấu phân cách của đường dẫn.** Dấu chấm phân tách thành phần tên; `com.acme.order-service` không phải tên module hợp lệ. Dùng `com.acme.order_service` hoặc, tốt hơn, một tên thành phần ngắn gọn không cần dấu gạch dưới.
5. **Chuẩn hóa thành phần lấy từ tên miền khi cần.** Nếu thành phần có dấu gạch ngang hoặc ký tự không hợp lệ, đổi thành dấu gạch dưới; nếu trùng từ khóa Java, thêm dấu gạch dưới; nếu bắt đầu bằng chữ số, thêm dấu gạch dưới ở đầu. Ví dụ miền `my-company.example` có thể tạo prefix `example.my_company`.
6. **Giữ tên module ổn định và không gắn phiên bản phát hành vào tên.** Tránh các tên như `com.acme.catalog.v2` chỉ để biểu thị bản phát hành. Quản lý phiên bản trong cấu hình build và phiên bản artifact; tên module nên tiếp tục mô tả API hoặc trách nhiệm của nó.
7. **Đặt tên theo ranh giới trách nhiệm.** Tách module khi có ranh giới API, quyền truy cập, phụ thuộc hoặc vòng đời phát hành rõ ràng. Không tạo nhiều module nhỏ chỉ để chia thư mục.

Tên module không bắt buộc phải giống tên thư mục chứa mã nguồn. Thư mục mang tên module là quy ước hữu ích khi dùng `javac --module-source-path`, nhưng build tool có thể tổ chức source root theo cấu trúc riêng.

## 3. Quy tắc đặt tên package và ánh xạ sang thư mục

Package nên dùng chữ thường và thường bắt đầu bằng reverse-DNS giống namespace của module. Mỗi thành phần sau dấu chấm tương ứng với một thư mục con. Ví dụ:

| Khai báo package | Đường dẫn bên dưới source root |
|---|---|
| `com.acme.catalog` | `com/acme/catalog/` |
| `com.acme.catalog.api` | `com/acme/catalog/api/` |
| `com.acme.catalog.internal` | `com/acme/catalog/internal/` |

Nếu tệp khai báo `package com.acme.catalog.api;`, tệp `Book.java` nên nằm tại `com/acme/catalog/api/Book.java` bên dưới source root. Tên thư mục phải khớp chính xác với package, bao gồm chữ hoa/chữ thường; điều này đặc biệt quan trọng khi dự án chạy trên hệ điều hành có phân biệt hoa thường.

Không đặt class của named module trong default package. Cũng không chia cùng một package đầy đủ cho nhiều named module trong cùng ứng dụng/module layer; cách tổ chức đó tạo split package và gây lỗi hoặc xung đột khi JPMS phân giải module.

Package con là package độc lập. Export `com.acme.catalog.api` không tự động export `com.acme.catalog.api.internal` hoặc các package con khác. Hãy khai báo rõ package nào là API công khai.

## 4. Cấu trúc source cho nhiều JPMS module

Với `javac`, một cách tổ chức dễ hiểu là đặt mỗi module trong một thư mục riêng dưới module source root. Tên thư mục thường trùng tên module, bên trong có `module-info.java` và cây thư mục package:

```text
workspace/
├── src/
│   ├── com.acme.greeting/
│   │   ├── module-info.java
│   │   └── com/acme/greeting/GreetingService.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── out/
```

`module-info.java` nằm ở module source root, cùng cấp với thư mục package đầu tiên; không đặt nó bên trong `com/acme/...`. Tệp này khai báo tên module và các package/phụ thuộc cần thiết. Cách đặt thư mục module trong ví dụ là quy ước cho module source hierarchy, không phải yêu cầu rằng mọi dự án Java đều phải có thư mục mang đúng tên module.

**Module `com.acme.greeting` — `src/com.acme.greeting/module-info.java`:**

```java
module com.acme.greeting {
    exports com.acme.greeting;
}
```

**Package được export — `src/com.acme.greeting/com/acme/greeting/GreetingService.java`:**

```java
package com.acme.greeting;

public final class GreetingService {
    public String message() {
        return "Hello from JPMS";
    }
}
```

**Module ứng dụng — `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.greeting;
}
```

**Lớp chạy — `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.greeting.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(new GreetingService().message());
    }
}
```

Chạy các lệnh sau từ thư mục `workspace/` bằng JDK 17 trở lên:

```shell
javac --module-source-path src -d out -m com.acme.greeting,com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
```

Kết quả stdout:

```text
Hello from JPMS
```

`--module-source-path` chỉ vị trí source của các module; `-d out` chỉ thư mục đầu ra; `-m` chọn các module cần biên dịch. Khi chạy, `--module-path out` cung cấp các module đã biên dịch và `-m module/class` chỉ định module cùng lớp main. Thư mục `out/` là sản phẩm build, không phải source.

## 5. Cấu trúc dự án với Maven và Gradle

Maven và Gradle thường đặt source code trong `src/main/java`, tài nguyên trong `src/main/resources`, kiểm thử trong `src/test/java` và `src/test/resources`. Với một subproject tạo named module, đặt `module-info.java` trực tiếp trong `src/main/java`, còn package nằm bên dưới:

```text
catalog-platform/
├── pom.xml
├── catalog-api/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/
│       │   │   ├── module-info.java
│       │   │   └── com/acme/catalog/api/
│       │   └── resources/
│       └── test/
│           ├── java/
│           └── resources/
└── catalog-app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                ├── module-info.java
                └── com/acme/catalog/app/
```

Trong ví dụ Maven, `pom.xml` ở gốc có thể khai báo các subproject; mỗi subproject có `pom.xml` riêng. Với Gradle, file gốc tương ứng thường là `settings.gradle.kts`, mỗi subproject có `build.gradle.kts`. Cấu trúc source của từng subproject vẫn theo quy ước `src/main/java` và `src/test/java`.

Đừng nhầm tên subproject với tên JPMS module: `catalog-api` có thể là tên thư mục và `artifactId`, trong khi `module-info.java` khai báo `com.acme.catalog.api`. Nếu subproject không có module descriptor, việc nó là một Maven/Gradle subproject không tự biến nó thành named module.

Thư mục `target/` của Maven và `build/` của Gradle chứa đầu ra do build tool tạo. Không đặt mã nguồn thủ công trong các thư mục này và không đưa file `.class` hoặc output build vào source tree.

## 6. Tổ chức package theo API và phần triển khai

Trong một module, hãy nhóm package theo trách nhiệm và giữ API công khai nhỏ, ổn định. Ví dụ:

```text
com.acme.catalog.api/          # kiểu dữ liệu và dịch vụ công khai
com.acme.catalog.application/  # điều phối use case
com.acme.catalog.persistence/  # triển khai lưu trữ
com.acme.catalog.internal/     # chi tiết nội bộ
```

Trong `module-info.java`, `exports` công bố package cho module khác; chỉ export package mà người dùng module thực sự cần. Package triển khai hoặc `internal` thường không export. Dùng `opens` khi một thư viện cần reflection truy cập sâu vào package ở runtime; chỉ mở đúng package và đúng module cần thiết. Không dùng `open module` cho toàn bộ module nếu không có yêu cầu cụ thể.

Ví dụ, nếu API chính là `com.acme.catalog.api`, module có thể khai báo:

```java
module com.acme.catalog.api {
    exports com.acme.catalog.api;
}
```

`exports` nhận tên package; `requires` nhận tên module. Nhầm hai loại tên này là lỗi cấu hình phổ biến. Việc đặt class trong một thư mục tên `internal` không tự làm package trở thành nội bộ; ranh giới truy cập do module descriptor quyết định.

## 7. Lỗi tổ chức thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Đặt `module-info.java` bên trong thư mục package. | Công cụ không nhận diện đúng module source root. | Đưa tệp lên root của source set/module. |
| Tên package không khớp đường dẫn thư mục. | Compiler không tìm thấy hoặc phân loại source không đúng. | Đồng bộ `package` với từng thư mục từ source root. |
| Dùng dấu `-` trong tên module. | Tên không phải chuỗi Java identifier hợp lệ. | Dùng dấu chấm giữa các thành phần và tên thành phần hợp lệ. |
| Đặt module ứng dụng dưới namespace `java.*`. | Vi phạm namespace dành riêng cho Java SE. | Dùng reverse-DNS của tổ chức. |
| Nghĩ rằng export package cha sẽ export cả package con. | Module khác không truy cập được package con. | Export riêng từng package cần công khai. |
| Chia một package cho nhiều named module. | Phát sinh split package khi phân giải module. | Đưa toàn bộ package về một module hoặc đổi ranh giới package. |
| Dùng tên thư mục hoặc `artifactId` làm căn cứ duy nhất để tìm JPMS name. | `requires` trỏ sai module. | Đọc tên trong `module-info.java` hoặc descriptor của artifact. |
| Đặt class vào default package trong named module. | Không phù hợp với cấu trúc package của named module. | Khai báo package có tên và tạo đúng cây thư mục. |

## 8. Checklist trước khi hoàn tất

- Tên module là các Java identifier phân cách bằng dấu chấm, viết chữ thường và có namespace đủ duy nhất.
- Thành phần đầu tiên của tên không phải `java`; tên module không chứa phiên bản phát hành.
- Tên module phù hợp với package export chính hoặc dùng reverse-DNS khi không có package export chính.
- Mỗi named module có `module-info.java` tại module source root.
- Đường dẫn package khớp chính xác với khai báo `package` trong mã nguồn.
- `requires` tham chiếu tên module; `exports` và `opens` tham chiếu tên package.
- Không chia cùng package giữa các named module và không dựa vào việc export package cha để mở package con.
- Source, test, resources và output build nằm ở các thư mục đúng vai trò của build tool.

## Tài liệu tham khảo

- [Java Language Specification — Names, Package Names and Module Names (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-6.html)
- [The `javac` Command — Arrangement of Source Code and Module Source Path (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
