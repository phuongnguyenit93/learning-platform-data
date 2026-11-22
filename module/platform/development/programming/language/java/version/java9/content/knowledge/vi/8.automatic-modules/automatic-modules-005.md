# Quan hệ giữa mô-đun có tên với mã trên class path

## 1. Bức tranh tổng thể

Từ Java 9, Java Platform Module System (JPMS) phân biệt mã được tổ chức thành **named module** và mã chạy theo mô hình class path truyền thống.

Khi chạy ứng dụng modular, các lớp trên class path thuộc **unnamed module** của class loader đã nạp chúng. Unnamed module không có tên module để khai báo trong `module-info.java`. Nó là cách JPMS biểu diễn phần mã vẫn sử dụng class path.

Hai chiều truy cập giữa named module và class path không đối xứng:

- Mã trên class path thuộc unnamed module và có thể đọc các named module đã được phân giải. Mã này truy cập được các kiểu public trong package mà named module đã export.
- Named module không đọc unnamed module theo mặc định. Vì vậy, mã trong named module không thể trực tiếp import và sử dụng kiểu nằm trong một thư viện chỉ có trên class path.
- Có thể tạm bổ sung quan hệ readability từ named module tới unnamed module bằng tùy chọn `--add-reads`.
- Một JAR không có `module-info.class` được đặt trên module path có thể trở thành **automatic module**. Automatic module là named module với descriptor tự động, không phải unnamed module.

Đây là các quy tắc quan trọng khi chuyển ứng dụng từ class path sang JPMS hoặc khi một hệ thống cần phối hợp mã modular với thư viện cũ.

## 2. Unnamed module là gì?

Mỗi class loader có một unnamed module tương ứng. Những lớp mà class loader đó nạp từ class path thuộc unnamed module của nó.

Các đặc điểm chính:

- Unnamed module không có tên module.
- Không có file `module-info.java` hoặc module descriptor tường minh.
- Không thể viết `requires unnamed` trong module descriptor, vì unnamed module không có tên để tham chiếu.
- Unnamed module đọc các named module.
- Các package của unnamed module được export, vì vậy mã thuộc module khác có thể truy cập các kiểu public của chúng nếu có quan hệ readability phù hợp.
- Các lớp trên class path vẫn chịu quy tắc truy cập Java thông thường như `public`, `protected`, package-private và `private`.

Nếu ứng dụng dùng nhiều class loader, mỗi class loader có unnamed module riêng. Vì vậy, hai nhóm lớp cùng đến từ class path nhưng được nạp bởi hai class loader khác nhau không nhất thiết thuộc cùng một unnamed module.

## 3. Quan hệ truy cập giữa hai mô hình

| Chiều truy cập | Mặc định | Điều kiện chính |
|---|---|---|
| Class path / unnamed module → named module | Có thể | Named module phải được phân giải; package cần dùng phải được export |
| Named module → class path / unnamed module | Không | Cần thêm readability bằng `--add-reads` hoặc dùng một module bridge phù hợp |
| Named module → automatic module trên module path | Có thể | Named module khai báo `requires` tới tên automatic module |
| Class path → package không export của named module | Không | Có thể mở rộng export tạm bằng `--add-exports` |
| Reflection sâu vào thành viên không public | Không mặc nhiên | Cần quyền mở package bằng `opens` hoặc `--add-opens` phù hợp |

Có ba khái niệm không nên nhầm lẫn:

- **Readability:** module hiện tại có quyền đọc module kia trong module graph hay không.
- **Exports:** package có được công khai để module khác truy cập các kiểu public hay không.
- **Opens:** package có được mở cho reflection, đặc biệt là deep reflection, hay không.

Có readability không tự động làm mọi package trở nên public. Package vẫn phải được export để truy cập thông thường.

## 4. Chiều thứ nhất: class path sử dụng API của named module

Unnamed module đọc các named module trong môi trường chạy. Vì vậy, mã trên class path có thể sử dụng API public của named module nếu package chứa API đó đã được export.

Có hai điều kiện:

1. Named module phải có mặt trong module path và được phân giải.
2. Package chứa API phải được export trong module descriptor.

### 4.1. Module API

Cấu trúc:

~~~text
src/
└── com.example.api/
    ├── module-info.java
    └── com/example/api/Greeting.java
~~~

File `src/com.example.api/module-info.java`:

~~~java
module com.example.api {
    exports com.example.api;
}
~~~

File `src/com.example.api/com/example/api/Greeting.java`:

~~~java
package com.example.api;

public final class Greeting {
    public static String message() {
        return "named API";
    }
}
~~~

Biên dịch module:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.example.api
~~~

Sau lệnh này, thư mục `mods/com.example.api` chứa `module-info.class` và `Greeting.class`.

### 4.2. Chương trình trên class path

File `cp-src/com/example/client/Main.java`:

~~~java
package com.example.client;

import com.example.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println("classpath -> " + Greeting.message());
    }
}
~~~

Biên dịch mã class path và cho javac biết named module cần được phân giải:

~~~bash
javac --release 17 --module-path mods --add-modules com.example.api -d cp-out cp-src/com/example/client/Main.java
~~~

Chạy ứng dụng:

~~~bash
java --module-path mods --add-modules com.example.api --class-path cp-out com.example.client.Main
~~~

Kết quả:

~~~text
classpath -> named API
~~~

Trong ví dụ:

- `com.example.api` là named module.
- `com.example.client.Main` thuộc unnamed module vì được chạy từ class path.
- `--add-modules com.example.api` đưa module API vào tập root để nó được phân giải.
- `exports com.example.api` cho phép mã class path truy cập kiểu public `Greeting`.

Nếu package API không được export, class path không thể sử dụng các kiểu public trong package đó theo cách truy cập thông thường, dù module đã có mặt trên module path.

## 5. Chiều thứ hai: named module sử dụng mã trên class path

Mặc định, named module không đọc unnamed module. Ví dụ một thư viện cũ `legacy.jar` nằm trên class path:

~~~text
legacy.jar
└── com/example/legacy/LegacyHelper.class
~~~

Named module không thể khai báo:

~~~java
module com.example.app {
    requires unnamed;
}
~~~

Cú pháp này không hợp lệ vì unnamed module không có tên. Nếu named module import trực tiếp `com.example.legacy.LegacyHelper`, javac không thể phân giải package đó thành dependency mà module đọc được.

Để hỗ trợ một bước chuyển đổi, có thể thêm quan hệ readability bằng `--add-reads`.

### 5.1. Mã nguồn thư viện class path

File `legacy-src/com/example/legacy/LegacyHelper.java`:

~~~java
package com.example.legacy;

public final class LegacyHelper {
    public static String value() {
        return "classpath library";
    }
}
~~~

Biên dịch và đóng gói thư viện:

~~~bash
javac --release 17 -d legacy-out legacy-src/com/example/legacy/LegacyHelper.java
jar --create --file legacy.jar -C legacy-out .
~~~

### 5.2. Named module gọi thư viện class path

File `named-src/com.example.named/module-info.java`:

~~~java
module com.example.named {
}
~~~

File `named-src/com.example.named/com/example/named/Main.java`:

~~~java
package com.example.named;

public final class Main {
    public static void main(String[] args) {
        System.out.println(com.example.legacy.LegacyHelper.value());
    }
}
~~~

Biên dịch với `--add-reads`:

~~~bash
javac --release 17 --class-path legacy.jar --module-source-path named-src --add-reads com.example.named=ALL-UNNAMED -d named-out -m com.example.named
~~~

Chạy với cùng quan hệ readability:

~~~bash
java --class-path legacy.jar --module-path named-out --add-reads com.example.named=ALL-UNNAMED -m com.example.named/com.example.named.Main
~~~

Kết quả:

~~~text
classpath library
~~~

`ALL-UNNAMED` chỉ tất cả unnamed module. Tùy chọn này tạo một quan hệ readability bổ sung cho named module được chỉ định.

Cần truyền `--add-reads` ở cả giai đoạn biên dịch và chạy:

- Khi biên dịch, javac cần biết named module được phép đọc kiểu trong unnamed module.
- Khi chạy, JVM cần cùng quan hệ readability để kiểm tra truy cập module.

Nếu chỉ thêm ở một giai đoạn, ứng dụng có thể biên dịch hoặc khởi chạy không thành công ở giai đoạn còn lại.

### 5.3. Khi nào dùng --add-reads?

`--add-reads` là một biện pháp tương thích khi đang di chuyển ứng dụng cũ. Nó không sửa module descriptor và không biến thư viện class path thành named module.

Nên giới hạn phạm vi:

~~~bash
--add-reads com.example.named=ALL-UNNAMED
~~~

Tùy chọn này áp dụng cho mọi unnamed module. Nếu hệ thống dùng nhiều class loader, cần hiểu rằng `ALL-UNNAMED` có phạm vi rộng hơn một thư viện hoặc một class loader cụ thể.

Khi có thể, nên chuyển dependency sang modular JAR hoặc automatic module để named module có thể khai báo dependency rõ ràng bằng `requires`.

## 6. Phân biệt class path với automatic module

Một JAR không có `module-info.class` có thể tham gia hai mô hình khác nhau tùy vị trí đặt:

| Vị trí JAR | Cách JPMS nhìn nhận |
|---|---|
| Trên class path | Các lớp thuộc unnamed module của class loader |
| Trên module path | Có thể được xem là automatic module |

Automatic module là một named module có descriptor tự động:

- Có tên module.
- Có thể được named module khác yêu cầu bằng `requires`.
- Tên có thể được xác định từ thuộc tính `Automatic-Module-Name` trong manifest hoặc suy ra từ tên JAR.
- Tự động export các package của nó.
- Có quan hệ readability rộng với các module khác theo quy tắc automatic module.

Automatic module hữu ích khi đưa một thư viện cũ lên module path trước khi thư viện đó có module descriptor tường minh.

### 6.1. Ví dụ sử dụng automatic module

Giả sử `legacy.jar` không có `module-info.class` và không có `Automatic-Module-Name`. Khi tên file là `legacy.jar`, JDK có thể suy ra tên automatic module là `legacy`.

Named module có thể khai báo:

~~~java
module com.example.app {
    requires legacy;
}
~~~

Biên dịch:

~~~bash
javac --release 17 --module-path legacy.jar --module-source-path src -d out -m com.example.app
~~~

Chạy trên Windows:

~~~powershell
java --module-path "legacy.jar;out" -m com.example.app/com.example.app.Main
~~~

Trên Linux hoặc macOS, dấu phân cách module path là dấu hai chấm:

~~~bash
java --module-path legacy.jar:out -m com.example.app/com.example.app.Main
~~~

Trong dự án lâu dài, nên đặt thuộc tính `Automatic-Module-Name` ổn định trong manifest của thư viện thay vì phụ thuộc vào tên file JAR được suy ra. Khi thư viện hỗ trợ JPMS đầy đủ, module descriptor tường minh giúp kiểm soát dependency và package export tốt hơn.

**Automatic module không phải unnamed module.** JAR trên class path thuộc unnamed module; cùng JAR đó trên module path có thể trở thành automatic module.

## 7. Các tùy chọn mở rộng quyền truy cập

Ba tùy chọn thường gặp xử lý ba vấn đề khác nhau:

| Tùy chọn | Thay đổi | Trường hợp dùng |
|---|---|---|
| `--add-reads` | Bổ sung quan hệ readability | Named module cần đọc unnamed module hoặc một module khác |
| `--add-exports` | Export thêm một package cho module đích | Mã cần truy cập kiểu public trong package vốn không được export |
| `--add-opens` | Mở package cho reflection ở runtime | Framework cần deep reflection vào thành viên không public |

Ví dụ mở package nội bộ cho class path:

~~~bash
--add-exports com.example.api/com.example.api.internal=ALL-UNNAMED
~~~

Tùy chọn này có thể dùng trong javac và java để cho phép mã thuộc unnamed module truy cập các kiểu public trong package được chỉ định.

Ví dụ mở package cho reflection:

~~~bash
--add-opens com.example.api/com.example.api.internal=ALL-UNNAMED
~~~

`--add-opens` là tùy chọn runtime dành cho reflection. Nó không cho phép import package ở thời điểm biên dịch và không thay thế `--add-reads`.

Không nên dùng các tùy chọn này để mở toàn bộ nội bộ của ứng dụng nếu không cần thiết. Chúng là các điểm điều chỉnh cấu hình, hữu ích khi tích hợp hoặc chuyển đổi, nhưng có thể làm giảm ranh giới encapsulation của JPMS.

## 8. Sơ đồ chọn mô hình tích hợp

~~~text
Thư viện / mã cũ
       |
       v
Đặt trên class path?
       |
       +-- Có --> Thuộc unnamed module
       |             |
       |             +-- Classpath client gọi named API:
       |             |      named module được resolve
       |             |      + package đã exports
       |             |
       |             +-- Named module gọi classpath:
       |                    cần --add-reads ...=ALL-UNNAMED
       |
       +-- Không, đặt trên module path
                     |
                     +-- Có module-info.class:
                     |      named module tường minh
                     |
                     +-- Không có module-info.class:
                            automatic module
~~~

Sơ đồ nhấn mạnh rằng vị trí triển khai JAR ảnh hưởng đến module mà các lớp thuộc về. Chỉ đổi class path thành module path đã có thể làm thay đổi cách JPMS phân giải dependency và kiểm tra truy cập.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Classpath code không tìm thấy named module | Module chưa được phân giải | Thêm module vào module path và dùng `--add-modules` khi cần |
| Classpath code không truy cập được API | Package API chưa export | Export package cần thiết trong module descriptor |
| Named module không import được lớp trên class path | Named module không đọc unnamed module mặc định | Thêm `--add-reads module=ALL-UNNAMED` ở compile và runtime trong giai đoạn chuyển đổi |
| `requires unnamed` không hợp lệ | Unnamed module không có tên | Dùng `--add-reads` hoặc chuyển dependency thành automatic/named module |
| Dùng `--add-exports` nhưng vẫn thiếu readability | Nhầm export với read edge | Kiểm tra cả readability và exports; dùng `--add-reads` khi named module cần đọc unnamed module |
| Dùng `--add-opens` để sửa lỗi import | Nhầm reflection với truy cập mã nguồn | Dùng exports/readability phù hợp; opens chỉ phục vụ reflection |
| JAR chạy được trên class path nhưng không resolve trên module path | Tên automatic module hoặc dependency khác với dự kiến | Kiểm tra `jar --describe-module`, manifest và tên module |
| Chương trình chạy được trong IDE nhưng lỗi khi triển khai | IDE và lệnh chạy cấu hình class path/module path khác nhau | Kiểm tra cấu hình compile, runtime, module path và các tùy chọn bổ sung |
| Nhiều class loader có unnamed module khác nhau | Giả định tất cả lớp class path thuộc cùng một module | Kiểm tra class loader thực tế và phạm vi `ALL-UNNAMED` |

## 10. Nguyên tắc chuyển đổi ứng dụng cũ sang JPMS

- Xác định những thư viện còn trên class path và những module đã có descriptor.
- Ưu tiên xác định API public rõ ràng trong named module và export đúng package.
- Cho mã class path gọi named API trong giai đoạn chuyển đổi bằng cách resolve module phù hợp.
- Nếu named module phải gọi thư viện chỉ nằm trên class path, xem `--add-reads` là giải pháp tạm thời và giới hạn phạm vi sử dụng.
- Nếu thư viện cũ có thể đặt trên module path, cân nhắc automatic module và khai báo `requires` tường minh.
- Khi có thể kiểm soát thư viện, thêm module descriptor để định nghĩa dependency và exports chính xác.
- Chỉ dùng `--add-exports` cho package nội bộ thực sự cần tích hợp; tránh phụ thuộc vào package không được hỗ trợ.
- Chỉ dùng `--add-opens` khi framework cần reflection sâu và không có API công khai phù hợp.
- Kiểm thử cả compile-time lẫn runtime với đúng lệnh triển khai.
- Loại bỏ các tùy chọn `--add-reads`, `--add-exports` hoặc `--add-opens` không còn cần thiết sau khi hoàn tất chuyển đổi.

## 11. Checklist kiểm tra

- Xác định lớp đang nằm trên class path hay module path.
- Xác định class loader và unnamed module sở hữu lớp class path.
- Kiểm tra named module đã được phân giải hay chưa.
- Kiểm tra package API có được export hay không.
- Nếu named module gọi class path, kiểm tra quan hệ readability và tùy chọn `--add-reads`.
- Phân biệt JAR trên class path với automatic module trên module path.
- Dùng `jar --describe-module` để xem descriptor hoặc automatic module name.
- Kiểm tra `--add-exports` và `--add-opens` đúng mục đích.
- Chạy lại cả lệnh javac và java trong môi trường triển khai thực tế.

## 12. Tài liệu tham khảo

- [Java Language Specification — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7.5) — quy tắc về unnamed module.
- [Java Language Specification — Automatic Modules](https://docs.oracle.com/javase/specs/jls/se24/html/jls-7.html#jls-7.7.6) — quy tắc về automatic module.
- [Java Compiler — javac](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html) — `--add-reads`, `--add-exports`, module path và module source path.
- [Java Launcher — java](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html) — tùy chọn runtime cho module graph và quyền truy cập.
