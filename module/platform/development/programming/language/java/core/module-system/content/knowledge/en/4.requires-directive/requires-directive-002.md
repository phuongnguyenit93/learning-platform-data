# requires java.base ngầm định

Trong Java Platform Module System (JPMS), mọi named module đều có quan hệ phụ thuộc trực tiếp tới module nền tảng `java.base`, ngoại trừ chính `java.base`. Nếu `module-info.java` không viết directive `requires java.base;`, Java compiler tự bổ sung directive này vào module descriptor đã biên dịch. Vì vậy, mã nguồn module thường không cần khai báo `java.base` một cách tường minh.

Đây là dependency nền tảng của hệ sinh thái Java. Các kiểu cơ bản như `Object`, `String`, `System`, `Class`, `Throwable`, các collection, I/O cơ bản, thời gian và nhiều API phổ biến đều nằm trong `java.base`. Mọi module đều cần khả năng đọc module này để sử dụng các kiểu nền tảng đó.

## 1. java.base là module nền tảng

`java.base` là module cốt lõi của Java SE. Nó chứa những package được dùng rộng rãi trong hầu hết chương trình, ví dụ:

| Package | Ví dụ API |
|---|---|
| `java.lang` | `Object`, `String`, `System`, `Math`, `Class`, `Throwable` |
| `java.util` | `List`, `Map`, `Set`, `Optional`, `Collections` |
| `java.io` | `InputStream`, `OutputStream`, `File`, `Serializable` |
| `java.nio` và `java.nio.file` | `ByteBuffer`, `Path`, `Files` |
| `java.time` | `LocalDate`, `Instant`, `Duration` |
| `java.math` | `BigInteger`, `BigDecimal` |
| `java.util.concurrent` | `ExecutorService`, `CompletableFuture`, `ConcurrentHashMap` |

Package `java.lang` còn được Java import ngầm vào mọi compilation unit, nên chương trình có thể dùng `String` hoặc `System` mà không cần viết câu lệnh `import`. Đây là quy tắc import của ngôn ngữ Java; nó khác với quy tắc module readability. Khả năng đọc `java.base` là điều kiện ở cấp module để mã trong module sử dụng các API thuộc module nền tảng.

## 2. Vì sao requires java.base được thêm ngầm định?

Một module thông thường có thể bắt đầu với descriptor rất ngắn:

```java
module com.acme.app {
}
```

Dù không có dòng `requires`, module `com.acme.app` vẫn đọc được `java.base`. Theo quy tắc của JPMS, nếu khai báo module không chứa `requires java.base;`, compiler ngầm thêm quan hệ phụ thuộc này khi tạo module descriptor. Trong file `module-info.class`, dependency được đánh dấu là `mandated` (bắt buộc theo quy tắc nền tảng).

Có thể hiểu hai hình thức sau có cùng ý nghĩa về khả năng đọc `java.base`:

```java
// Nguồn thông thường: không cần khai báo java.base
module com.acme.app {
}
```

```java
// Mô tả tường minh về quan hệ nền tảng
module com.acme.app {
    requires java.base;
}
```

Trong dự án thực tế, nên để compiler xử lý dependency ngầm định thay vì thêm một dòng thừa vào mọi `module-info.java`. Điểm quan trọng là dependency vẫn tồn tại trong module descriptor đã biên dịch, dù không xuất hiện trong mã nguồn.

Module `java.base` không thể tự khai báo phụ thuộc vào chính nó. Nó là nền móng mà các module Java SE khác dựa vào, tránh tạo vòng phụ thuộc ở tầng thấp nhất của nền tảng.

## 3. Ví dụ: dùng API java.base mà không khai báo requires

Cấu trúc dự án modular:

```text
src/
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
```

Descriptor:

```java
// src/com.acme.app/module-info.java
module com.acme.app {
}
```

Class sử dụng nhiều API thuộc `java.base`:

```java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import java.time.LocalDate;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        List<String> topics = List.of("String", "Collections", "Date");

        System.out.println("Today: " + LocalDate.now());
        System.out.println("Topics: " + topics);
        System.out.println("Runtime: " + System.getProperty("java.version"));
    }
}
```

Biên dịch và chạy từ thư mục dự án:

```shell
javac --module-source-path src -d out -m com.acme.app
java --module-path out -m com.acme.app/com.acme.app.Main
```

Mã nguồn không khai báo `requires java.base;` nhưng vẫn dùng được `List`, `LocalDate`, `String` và `System`. Các kiểu này đều thuộc `java.base`, và module `com.acme.app` đã đọc module nền tảng nhờ directive ngầm định.

## 4. Kiểm tra dependency ngầm định trong module descriptor

Có thể xem descriptor của module sau khi biên dịch bằng `javap`:

```shell
javap -v out/com.acme.app/module-info.class
```

Trong phần `Module:`, tìm mục `requires`. Kết quả sẽ thể hiện module `java.base` cùng cờ `mandated`, dù file nguồn `module-info.java` không có dòng tương ứng. Cờ này cho biết directive được bổ sung theo quy tắc của nền tảng.

Một cách khác là đóng gói module thành JAR rồi xem descriptor:

```shell
jar --create --file com.acme.app.jar -C out/com.acme.app .
jar --describe-module --file com.acme.app.jar
```

Kết quả mô tả module sẽ liệt kê dependency `java.base` là `mandated`. Bạn cũng có thể xem module nền tảng của JDK đang sử dụng:

```shell
java --describe-module java.base
```

Những lệnh này hữu ích khi kiểm tra artifact thực tế, đặc biệt khi cấu hình build tạo ra module descriptor khác với điều người đọc suy ra từ mã nguồn.

## 5. java.base không chứa toàn bộ Java SE

Không nên hiểu `java.base` là toàn bộ thư viện chuẩn của Java. Java SE được chia thành nhiều module để phân tách chức năng. Một số API quen thuộc nằm ngoài `java.base`:

| Module | Chức năng tiêu biểu |
|---|---|
| `java.sql` | JDBC và API truy cập cơ sở dữ liệu |
| `java.desktop` | AWT, Swing và đồ họa desktop |
| `java.xml` | API xử lý XML |
| `java.logging` | Java Logging API |
| `java.net.http` | HTTP Client API |

Nếu module ứng dụng sử dụng các API thuộc module khác, cần khai báo dependency tương ứng. Ví dụ:

```java
module com.acme.reporting {
    requires java.sql;
}
```

Ở đây, `requires java.sql;` là cần thiết nếu mã trong module sử dụng API JDBC. Dependency ngầm định tới `java.base` không tự động làm ứng dụng đọc mọi module của JDK.

Cũng cần phân biệt package có tên gần nhau: `java.net` cơ bản thuộc `java.base`, trong khi HTTP Client hiện đại nằm trong module riêng `java.net.http`. Hãy tra module sở hữu package thay vì suy luận chỉ từ tiền tố tên package.

## 6. Dependency ngầm định không phải exports hay requires transitive

Directive ngầm định `requires java.base` tạo quan hệ readability từ module hiện tại tới `java.base`. Nó không thực hiện những việc sau:

- Không export package của module ứng dụng cho module khác.
- Không khiến module hiện tại tự động đọc tất cả module còn lại trong JDK.
- Không thay thế `requires` cho dependency như `java.sql`, `java.desktop` hoặc `java.xml`.
- Không có nghĩa các module phụ thuộc vào ứng dụng sẽ tự động đọc mọi dependency của ứng dụng.

`requires` và `exports` giải quyết hai hướng khác nhau: `requires` khai báo module hiện tại cần đọc module nào; `exports` công bố package nào để module khác có thể truy cập. Dependency ngầm định tới `java.base` không làm thay đổi ranh giới API của module ứng dụng.

## 7. Những hiểu nhầm thường gặp

**“Không có requires trong module-info.java thì module không dùng được String.”**

Sai. Mọi named module thông thường đều có dependency ngầm định tới `java.base`, nơi chứa `String`.

**“java.base chứa tất cả class trong JDK.”**

Sai. Nhiều API được tách thành các module như `java.sql`, `java.desktop`, `java.xml` và `java.net.http`. Các module này vẫn cần được khai báo khi ứng dụng sử dụng chúng.

**“Compiler không ghi requires java.base vì dependency không tồn tại.”**

Sai. Dependency được thêm vào module descriptor đã biên dịch và có thể quan sát bằng `javap -v` hoặc `jar --describe-module`.

**“Có thể bỏ java.base để tạo runtime nhỏ hơn.”**

Không thể loại bỏ module nền tảng khỏi một Java runtime hợp lệ. Khi tạo runtime image bằng `jlink`, `java.base` là module gốc bắt buộc; việc tối ưu image tập trung vào các module bổ sung mà ứng dụng thực sự cần.

## 8. Cách áp dụng khi thiết kế module

- Để `module-info.java` ngắn gọn; không cần khai báo `requires java.base;` trong module thông thường.
- Khai báo rõ các module JDK khác khi dùng API của chúng, chẳng hạn `java.sql` hoặc `java.logging`.
- Khi gặp lỗi `module ... does not read ...`, xác định module chứa package đang dùng và bổ sung `requires` phù hợp; đừng mặc định mọi API đều thuộc `java.base`.
- Khi kiểm tra artifact, xem module descriptor đã biên dịch thay vì chỉ đọc file nguồn.
- Khi tạo runtime image bằng `jlink`, giữ `java.base` và chỉ đưa thêm các module cần thiết cho ứng dụng.

`requires java.base` ngầm định giúp mọi module Java có sẵn nền tảng ngôn ngữ và thư viện cốt lõi. Nhờ quy tắc này, người viết module có thể tập trung khai báo các dependency đặc thù của ứng dụng, còn quan hệ nền tảng luôn được đảm bảo bởi JPMS.