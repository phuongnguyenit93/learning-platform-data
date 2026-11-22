# Vai trò nền tảng của `java.base`

`java.base` là module nền tảng của Java Platform Module System (JPMS), được giới thiệu từ Java 9. Module này định nghĩa những API cốt lõi của Java SE và nằm ở gốc của đồ thị module. Các chương trình Java dựa vào nó để dùng những kiểu và dịch vụ cơ bản như `Object`, `String`, collections, I/O, xử lý ngày giờ, số học, mạng, bảo mật và lập trình đồng thời.

Cần phân biệt hai khái niệm: `java.base` là **tên một module**, còn `java.lang` là **một package được module đó export**. `java.lang` chỉ là một phần của `java.base`; nó không đại diện cho toàn bộ module.

## 1. Vị trí của `java.base` trong đồ thị module

`java.base` là module gốc (primordial module) của nền tảng Java:

- Mọi named module khác đều có dependency ngầm định tới `java.base`.
- Khi viết `module-info.java`, bạn không cần khai báo `requires java.base;`. Trình biên dịch tự bổ sung dependency này vào module descriptor.
- Trong descriptor đã biên dịch, dependency ngầm định được đánh dấu bằng modifier `MANDATED`.
- Bản thân `java.base` không khai báo `requires` tới module nào khác. Nó là nền tảng để các module còn lại xây dựng dependency graph.

Dependency ngầm định giúp mọi named module đọc được các package API mà `java.base` export. Vì vậy, một module ứng dụng có thể sử dụng `String`, `List`, `Path` hoặc `LocalDate` mà không phải thêm `requires java.base`.

Với ứng dụng chạy trên classpath, mã nguồn thường không có `module-info.java` và được nạp vào unnamed module. Ứng dụng vẫn sử dụng các API của `java.base`; việc không khai báo module descriptor không làm mất vai trò nền tảng của module này.

## 2. Những nhóm API cốt lõi

`java.base` gom các package được dùng rộng rãi trong hầu hết ứng dụng Java. Một số nhóm tiêu biểu:

| Package | Vai trò | Ví dụ API |
| --- | --- | --- |
| `java.lang` | Kiểu và cơ chế nền tảng của ngôn ngữ | `Object`, `String`, `Class`, `System`, `Thread`, `Throwable` |
| `java.util` | Collection và tiện ích dùng chung | `List`, `Map`, `Set`, `Optional`, `Objects`, `ServiceLoader`, `Base64` |
| `java.io` | Luồng dữ liệu và I/O truyền thống | `InputStream`, `OutputStream`, `Reader`, `Writer`, `File` |
| `java.nio`, `java.nio.file` | Buffer, channel, charset và thao tác file hiện đại | `ByteBuffer`, `Path`, `Files`, `Charset` |
| `java.time` | Ngày giờ và khoảng thời gian | `LocalDate`, `Instant`, `Duration`, `DateTimeFormatter` |
| `java.math` | Số học độ chính xác tùy ý | `BigInteger`, `BigDecimal` |
| `java.net` | Các kiểu và thao tác mạng nền tảng | `URI`, `URL`, `Socket`, `InetAddress` |
| `java.util.concurrent` | Đồng bộ và xử lý tác vụ đồng thời | `ExecutorService`, `CompletableFuture`, `ConcurrentHashMap` |
| `java.util.function`, `java.util.stream` | Kiểu hàm và xử lý dữ liệu theo pipeline | `Function`, `Predicate`, `Stream`, `Collectors` |
| `java.security`, `javax.crypto` | API bảo mật và mật mã | `MessageDigest`, `Signature`, `Cipher` |

Các package trên là những ví dụ tiêu biểu, không phải danh sách đầy đủ. Có thể xem danh sách package được export trong tài liệu API của module `java.base` theo phiên bản JDK đang sử dụng.

### `java.base` không chứa mọi API của Java SE

Một số API quen thuộc thuộc các module riêng. Dependency ngầm định tới `java.base` không tự động cấp quyền đọc các module này:

| Module | Nhóm API |
| --- | --- |
| `java.sql` | JDBC và API truy cập cơ sở dữ liệu |
| `java.xml` | XML, DOM, SAX và JAXP |
| `java.desktop` | AWT, Swing, hình ảnh và in ấn |
| `java.logging` | Java Logging API |
| `java.net.http` | HTTP Client và WebSocket API |
| `java.compiler` | Compiler API và annotation processing |

Ví dụ, module dùng JDBC phải khai báo `requires java.sql;`. Việc dùng `java.base` không thay thế dependency tới `java.sql`.

## 3. Quan hệ với `requires`, `exports` và `opens`

JPMS quản lý hai chiều truy cập: module hiện tại đọc module khác thông qua dependency, và module cung cấp API cho bên ngoài thông qua package được export.

- `requires` khai báo module mà mã hiện tại cần đọc. Riêng `java.base` đã được yêu cầu ngầm định.
- `exports` công bố package cho module khác sử dụng ở thời điểm biên dịch và chạy. `java.base` export các package API công khai như `java.lang`, `java.util`, `java.io` và `java.time`.
- `opens` cho phép truy cập phản chiếu ở runtime vào các kiểu và thành viên trong package. `opens` không giống `exports`; export một package không đồng nghĩa mọi thành viên `private` bên trong đều có thể bị truy cập phản chiếu sâu.

Không nên phụ thuộc vào package nội bộ như `sun.*` hoặc `jdk.internal.*`. Chúng không phải API công khai được bảo đảm ổn định và có thể bị module encapsulation chặn. Hãy dùng API được tài liệu hóa và export chính thức.

## 4. Ví dụ: kiểm tra dependency ngầm định

Ví dụ dưới đây tạo một named module nhỏ. `module-info.java` chỉ export package của ứng dụng và cố ý không khai báo `requires java.base`.

### Cấu trúc thư mục

```text
src/
└── com.example.basics/
    ├── module-info.java
    └── com/example/basics/Main.java
```

### `src/com.example.basics/module-info.java`

```java
module com.example.basics {
    exports com.example.basics;
}
```

### `src/com.example.basics/com/example/basics/Main.java`

```java
package com.example.basics;

import java.lang.module.ModuleDescriptor;

public class Main {
    public static void main(String[] args) {
        Module app = Main.class.getModule();
        Module base = Object.class.getModule();

        System.out.println("java.base = " + base.getName());
        System.out.println("java.lang exported = " + base.isExported("java.lang"));
        System.out.println("app reads java.base = " + app.canRead(base));

        ModuleDescriptor descriptor = app.getDescriptor();
        descriptor.requires().stream()
                .filter(requirement -> requirement.name().equals("java.base"))
                .findFirst()
                .ifPresent(requirement -> System.out.println(
                        "java.base modifiers = " + requirement.modifiers()));
    }
}
```

### Biên dịch và chạy

Chạy từ thư mục chứa `src/` bằng JDK 17 trở lên:

```bash
javac -d out --module-source-path src -m com.example.basics
java --module-path out -m com.example.basics/com.example.basics.Main
```

Kết quả:

```text
java.base = java.base
java.lang exported = true
app reads java.base = true
java.base modifiers = [MANDATED]
```

Kết quả cho thấy module ứng dụng đọc được `java.base`, package `java.lang` được export và descriptor đã biên dịch ghi dependency ngầm định với modifier `MANDATED`. Mã nguồn không cần viết `requires java.base;`.

## 5. Cách tự kiểm tra trong JDK

Có thể dùng các lệnh sau để quan sát module nền tảng và descriptor của ứng dụng:

```bash
# Liệt kê các module trong runtime image
java --list-modules

# Xem mô tả và các package export của java.base
java --describe-module java.base

# Xem module attribute của descriptor đã biên dịch
javap -v out/com.example.basics/module-info.class
```

Trong kết quả `javap -v`, tìm dependency `java.base` có cờ `ACC_MANDATED`. Tên hiển thị ở mức class-file là `ACC_MANDATED`; API `ModuleDescriptor` biểu diễn modifier tương ứng là `MANDATED`.

## 6. Những nhầm lẫn thường gặp

1. **Cho rằng phải tự khai báo `requires java.base`.** Dependency này đã được JPMS thêm ngầm định cho mọi named module khác `java.base`.
2. **Cho rằng `java.base` chứa toàn bộ Java SE.** JDBC, XML, Swing, Logging và HTTP Client nằm trong các module riêng; ứng dụng phải khai báo dependency phù hợp.
3. **Đồng nhất module với package.** `java.base` là module; `java.lang` và `java.util` là các package bên trong module đó.
4. **Cho rằng mọi package của JDK đều là API công khai.** Chỉ sử dụng các package và kiểu được tài liệu hóa, export chính thức; tránh package nội bộ.
5. **Đồng nhất `exports` với `opens`.** Export phục vụ truy cập API công khai; opens phục vụ truy cập phản chiếu ở runtime theo ranh giới package.

## 7. Ghi nhớ khi thiết kế module

- Xem `java.base` là nền tảng mặc định của mọi named module; không cần thêm dependency tường minh tới nó.
- Khai báo `requires` cho từng module khác mà ứng dụng thực sự sử dụng, chẳng hạn `java.sql` hoặc `java.net.http`.
- Chỉ xây API công khai trên package mà module chủ động export.
- Khi một thư viện cần reflection, xác định đúng package cần mở và phạm vi module nhận quyền; tránh mở rộng quyền truy cập không cần thiết.
- Ưu tiên API công khai của Java SE thay vì phụ thuộc vào implementation nội bộ của JDK.

## Tài liệu tham khảo

- [Java SE 26 API — Module `java.base`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/module-summary.html)
- [Java Language Specification — §7.7.1 Dependences](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7.1)
- [Java Virtual Machine Specification — Module attribute](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.7.25)