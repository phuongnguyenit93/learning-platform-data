# --patch-module thay nội dung module

> Phạm vi: Java Platform Module System (JPMS, từ Java 9). Tùy chọn **--patch-module** cho phép bổ sung hoặc ghi đè class và resource của một named module bằng nội dung nằm trong thư mục hoặc JAR bên ngoài module gốc.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích **--patch-module** dùng để làm gì và khi nào cần dùng.
- Viết đúng cú pháp khi chạy bằng **java** và khi biên dịch bằng **javac**.
- Chuẩn bị patch directory/JAR với cấu trúc package phù hợp.
- Hiểu cách nội dung patch được gắn vào module đích và được ưu tiên khi nạp lớp.
- Phân biệt việc patch nội dung với thay đổi module descriptor.
- Phân biệt **--patch-module** với **--add-exports**, **--add-opens**, **--add-reads** và **--upgrade-module-path**.
- Chẩn đoán trường hợp patch không được áp dụng hoặc gây lỗi lúc chạy.

## 1. --patch-module là gì?

**--patch-module** là tùy chọn của Java launcher và Java compiler để bổ sung hoặc ghi đè nội dung của một named module. Nội dung patch thường nằm trong một hoặc nhiều thư mục class đã biên dịch hoặc JAR.

Ví dụ, module **com.acme.lib** đã được đóng gói trong modular JAR. Bạn muốn thử một phiên bản mới của một class mà không cần sửa JAR gốc. Có thể đặt class thay thế trong thư mục patch rồi chạy:

~~~bash
java --patch-module com.acme.lib=build/patch \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Trong ví dụ:

- **com.acme.lib** là tên module cần patch.
- **build/patch** là thư mục chứa class/resource bổ sung hoặc thay thế.
- **mods** chứa module ứng dụng và module thư viện.
- **com.acme.app/com.acme.app.Main** là module chính và main class được khởi chạy.

Nội dung patch được xem là một phần của module đích trong runtime. Vì vậy, class được patch thuộc module đó, thay vì trở thành class của unnamed module như khi đặt một JAR trên class path.

Tùy chọn này hữu ích cho kiểm thử, debug, thử hotfix, thay thế implementation trong môi trường kiểm soát hoặc bổ sung class vào một module mà không đóng gói lại module gốc. Nó không phải cơ chế plugin tổng quát và cần được sử dụng có chủ đích.

## 2. Cú pháp của --patch-module

Cú pháp tổng quát:

~~~text
--patch-module <module>=<file>(<path-separator><file>)*
~~~

Trong đó:

- **module** là tên named module cần patch.
- **file** là đường dẫn tới thư mục hoặc JAR chứa class/resource patch.
- **path-separator** là dấu phân cách đường dẫn theo hệ điều hành.

Có thể chỉ định nhiều đường dẫn trong cùng một giá trị:

Linux/macOS:

~~~bash
--patch-module com.acme.lib=build/patch:build/extra-patch
~~~

Windows:

~~~powershell
--patch-module com.acme.lib=build/patch;build/extra-patch
~~~

Dấu phân cách là dấu hai chấm (**:**) trên Linux/macOS và dấu chấm phẩy (**;**) trên Windows. Khi đường dẫn có khoảng trắng, đặt toàn bộ giá trị module bằng đường dẫn trong dấu nháy phù hợp với shell:

~~~bash
java "--patch-module=com.acme.lib=build/patch files" ...
~~~

Có thể dùng tùy chọn nhiều lần để patch nhiều module khác nhau:

~~~bash
java \
  --patch-module com.acme.lib=build/patch-lib \
  --patch-module com.acme.util=build/patch-util \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Mỗi lần gọi nhắm đến một module. Không dùng tên package thay cho tên module và không bỏ phần tên module trước dấu bằng.

## 3. Chuẩn bị patch directory

Giả sử module thư viện có cấu trúc:

~~~text
mods/
└── com.acme.lib.jar
~~~

JAR chứa class:

~~~text
com/acme/lib/Message.class
~~~

Module descriptor trong JAR:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

Bạn muốn thay thế class **com.acme.lib.Message** bằng một phiên bản mới. Hãy chuẩn bị patch directory có cấu trúc package tương ứng:

~~~text
build/
└── patch/
    └── com/
        └── acme/
            └── lib/
                └── Message.class
~~~

Đường dẫn package phải bắt đầu từ thư mục gốc của patch path. Vì thế, nếu package là **com.acme.lib**, patch root phải là thư mục nằm ngay trước thư mục **com**.

Không đặt patch root ở sâu bên trong package, ví dụ **build/patch/com/acme/lib**, nếu trong thư mục đó không còn cây package **com/acme/lib**. Launcher sẽ tìm class theo đường dẫn package tương đối với patch root.

Patch path có thể là một thư mục class hoặc một JAR. Ví dụ:

~~~text
build/
├── patch-classes/
│   └── com/acme/lib/Message.class
└── patch.jar
~~~

Nếu dùng JAR, nội dung JAR phải có đường dẫn package tương tự:

~~~text
com/acme/lib/Message.class
~~~

## 4. Biên dịch class dành cho module được patch

Khi biên dịch source thuộc package của module đích, hãy dùng **javac --patch-module** để compiler hiểu các source đó là phần nội dung của module đang được patch.

Ví dụ source thay thế:

~~~text
src-patch/
└── com/acme/lib/Message.java
~~~

Nội dung:

~~~java
package com.acme.lib;

public class Message {
    public static String greet(String name) {
        return "[patched] Hello, " + name + "!";
    }
}
~~~

Biên dịch:

~~~bash
javac \
  --module-path mods \
  --patch-module com.acme.lib=src-patch \
  -d build/patch \
  src-patch/com/acme/lib/Message.java
~~~

Ý nghĩa:

- **--module-path mods** giúp compiler tìm module đích.
- **--patch-module com.acme.lib=src-patch** đưa source trong patch root vào ngữ cảnh module **com.acme.lib**.
- **-d build/patch** ghi class đã biên dịch vào patch root.
- Đường dẫn source cuối lệnh là file Java cần biên dịch.

Kết quả:

~~~text
build/patch/com/acme/lib/Message.class
~~~

Có thể dùng nhiều source directory hoặc JAR đã chuẩn bị, nhưng cần bảo đảm đường dẫn package đúng và class được biên dịch tương thích với phiên bản Java của runtime đích.

Nếu patch source tham chiếu tới type trong module đích, compiler cần nhìn thấy module đó trên module path. Không nên biên dịch patch như một source thông thường trên class path nếu mục đích là thêm hoặc thay thế nội dung của named module.

## 5. Chạy ứng dụng với module đã patch

Giả sử:

- **mods/com.acme.lib.jar** là module gốc.
- **mods/com.acme.app.jar** là module ứng dụng.
- **build/patch** chứa class mới cho **com.acme.lib**.

Chạy:

~~~bash
java \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Khi launcher tạo module configuration, nội dung từ patch path được gắn vào module đích. Class hoặc resource trùng tên trong patch có thể thay thế nội dung tương ứng trong module gốc; class/resource mới có thể bổ sung vào module.

Nếu chương trình gọi:

~~~java
System.out.println(Message.greet("Lan"));
~~~

và class patch đã được nạp, kết quả ví dụ sẽ là:

~~~text
[patched] Hello, Lan!
~~~

Thứ tự patch path cũng có ý nghĩa nếu nhiều patch path chứa cùng một class/resource. Hãy tránh để nhiều phiên bản trùng tên cùng xuất hiện trong danh sách patch; giữ patch set nhỏ và có thể tái tạo.

**--patch-module** phải được truyền cho chính lần chạy Java cần áp dụng patch. Việc chỉ thêm tùy chọn khi biên dịch không làm cho runtime tự động dùng class mới. Tương tự, patch path không được ghi ngược vào JAR gốc; nó là đầu vào riêng của lần chạy.

## 6. Patch module JDK

Có thể dùng **--patch-module** để patch một module hệ thống, ví dụ **java.base**, trong môi trường kiểm thử:

~~~bash
java \
  --patch-module java.base=build/patch-java-base \
  -version
~~~

Tên module phải là tên module hệ thống chính xác. Cây thư mục patch cần phản ánh package bên trong module đó.

Patch các module nền tảng có rủi ro cao: lớp JDK có thể được JVM và thư viện lõi sử dụng rất sớm, nhiều class có ràng buộc nội bộ và thay đổi không tương thích có thể khiến JVM khởi động thất bại. Chỉ dùng trong thử nghiệm có kiểm soát, kiểm tra trên đúng bản JDK và giữ cách khôi phục runtime gốc.

Không dùng ví dụ patch **java.base** như một công thức thay thế để sửa JDK trong môi trường production. Nếu cần thay đổi hành vi một thư viện ứng dụng do mình quản lý, hãy ưu tiên cập nhật module/JAR và phát hành artifact mới.

## 7. --patch-module có thay đổi module-info.class không?

**Không.** Tùy chọn này bổ sung hoặc ghi đè class/resource trong nội dung module. Nó không thay đổi module descriptor của module đích.

Do đó, patch không tự thêm:

- Directive **requires** để tạo dependency mới.
- Directive **exports** để công bố package cho module khác.
- Directive **opens** để cho phép reflection sâu.
- Directive **uses** hoặc **provides** để thay đổi khai báo service.
- Tên module mới hoặc phiên bản mới của module descriptor.

Nếu patch thêm một package mới vào module, package đó thuộc module đích nhưng không tự động trở thành package được export. Nếu code ở module khác cần truy cập package không được export, phải điều chỉnh quyền truy cập bằng descriptor phù hợp hoặc tùy chọn launcher chuyên biệt khi kiểm thử.

Nếu cần sửa descriptor lâu dài, hãy cập nhật source **module-info.java** rồi build lại modular JAR. Đừng dùng patch path để giả định rằng bạn đã thay đổi dependency hoặc ranh giới API của module.

## 8. Phân biệt với các tùy chọn module khác

| Tùy chọn | Tác dụng | Có thay class/resource trong module không? |
|---|---|---|
| **--patch-module** | Bổ sung hoặc ghi đè class/resource của module | Có |
| **--add-exports** | Cho phép module đích export package tới module khác trong lần chạy | Không |
| **--add-opens** | Mở package cho deep reflection ở runtime | Không |
| **--add-reads** | Bổ sung quan hệ readability giữa các module | Không |
| **--upgrade-module-path** | Cung cấp module thay thế cho module hệ thống trong quá trình resolve | Thay module theo cơ chế upgrade, không phải chỉ patch class |

Ví dụ mở package để reflection:

~~~bash
java --add-opens com.acme.lib/com.acme.lib.internal=ALL-UNNAMED ...
~~~

Ví dụ export package cho module cụ thể:

~~~bash
java --add-exports com.acme.lib/com.acme.lib.internal=com.acme.app ...
~~~

Hai tùy chọn này chỉ điều chỉnh quyền truy cập trong module system; chúng không thay implementation của class. Nếu mục tiêu là thay nội dung class, dùng **--patch-module**.

Nếu mục tiêu là thay toàn bộ một module hệ thống bằng một phiên bản module khác, hãy tìm hiểu **--upgrade-module-path**. Patch module và upgrade module giải quyết hai bài toán khác nhau: patch thay nội dung bên trong module đang được chọn, còn upgrade cung cấp module thay thế theo cơ chế nâng cấp.

## 9. Patch khi biên dịch và patch khi chạy

Có hai giai đoạn riêng:

**Khi biên dịch**, dùng tùy chọn của javac:

~~~bash
javac \
  --module-path mods \
  --patch-module com.acme.lib=src-patch \
  -d build/patch \
  src-patch/com/acme/lib/Message.java
~~~

Compiler xử lý source patch trong ngữ cảnh module đích. Đây là cách phù hợp khi source patch nằm trong package của named module.

**Khi chạy**, dùng tùy chọn của java:

~~~bash
java \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Launcher gắn nội dung patch vào module đích trong runtime. Hai bước không thay thế nhau: javac tạo class file; java cần patch path chứa class file đó để sử dụng lúc chạy.

Trong một quy trình build có kiểm soát, hãy lưu source patch, class patch và lệnh chạy trong cấu hình riêng. Điều này giúp tránh nhầm lẫn giữa class file vừa biên dịch và class file cũ còn sót trong thư mục build.

## 10. Kiểm tra patch đã được áp dụng

Có thể kiểm tra theo nhiều lớp:

1. Xác nhận class file đã được tạo đúng vị trí package trong patch root.
2. Dùng **jar tf patch.jar** nếu patch được đóng gói thành JAR để kiểm tra entry.
3. Chạy ứng dụng bằng đúng lệnh có **--patch-module**.
4. Dùng một kết quả dễ nhận biết trong class đã patch, chẳng hạn chuỗi phiên bản hoặc hành vi kiểm thử riêng.
5. Khi cần xác định nguồn class được nạp, bật log nạp class.

Ví dụ:

~~~bash
java -Xlog:class+load=info \
  --patch-module com.acme.lib=build/patch \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Log class loading có thể giúp xác định lớp nào được nạp và nguồn nạp mà JVM báo cáo. Không nên chỉ dựa vào **java --describe-module** để xác nhận patch đã thay class: lệnh đó mô tả module descriptor, trong khi patch không sửa descriptor.

Có thể kiểm tra module descriptor sau khi chạy hoặc dùng:

~~~bash
java --describe-module com.acme.lib --module-path mods
~~~

Kết quả mô tả module gốc, không phải danh sách class patch. Muốn chứng minh class mới đang được dùng, hãy kiểm tra hành vi thực tế hoặc log nạp class.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chạy vẫn dùng class cũ | Patch root sai, package path sai hoặc launcher không nhận tùy chọn | Kiểm tra class nằm dưới đúng package từ patch root; truyền **--patch-module** vào lệnh java thực tế |
| Compiler báo package thuộc module khác | Source patch được biên dịch như source thông thường, không dùng ngữ cảnh patch | Biên dịch bằng **javac --patch-module module=source-root** |
| Module không tìm thấy | Sai tên module hoặc module đích không có trên module path/configuration | Kiểm tra tên bằng **jar --describe-module** và module path |
| Class mới gây lỗi linkage | Patch class không tương thích với API, field, method hoặc binary contract mà module khác mong đợi | Biên dịch với đúng API/runtime; kiểm tra chữ ký và dependency |
| Package mới không truy cập được từ module khác | Patch thêm package nhưng module descriptor không export package đó | Cập nhật descriptor nếu cần công bố API; dùng **--add-exports** chỉ cho thử nghiệm |
| Reflection vẫn bị chặn | Patch không tự mở package | Dùng **--add-opens** phù hợp hoặc thiết kế lại quyền truy cập |
| Patch không có hiệu lực khi chạy bằng service/launcher khác | Tùy chọn được đặt ở lệnh build hoặc một tiến trình khác, không nằm trong JVM thực tế | Truyền patch option vào đúng lệnh java/launcher khởi chạy ứng dụng |
| JVM khởi động thất bại khi patch module hệ thống | Class lõi không tương thích hoặc patch làm hỏng giả định nội bộ của JDK | Bỏ patch, tái tạo môi trường sạch và chỉ thử trên JDK đúng phiên bản |

Một trình tự debug thực tế:

1. Xác định tên module đích chính xác.
2. Xác nhận module đích có thể được resolve từ module path hoặc là module hệ thống.
3. Kiểm tra patch path là thư mục/JAR hợp lệ và tồn tại.
4. Kiểm tra đường dẫn package tương đối với patch root.
5. Biên dịch lại patch bằng **javac --patch-module** nếu source vừa thay đổi.
6. Kiểm tra lệnh java thực tế có **--patch-module** đúng module và đường dẫn.
7. Bật log class loading hoặc chạy kiểm thử có kết quả phân biệt rõ bản gốc và bản patch.

## 12. Ghi nhớ

- **--patch-module module=path** bổ sung hoặc ghi đè class/resource của một named module.
- Patch path có thể là thư mục hoặc JAR; cấu trúc package tính từ gốc patch path.
- Dùng **javac --patch-module** khi biên dịch source patch và **java --patch-module** khi chạy.
- Patch content được gắn vào module đích; class patch thuộc module đó.
- Patch không sửa **module-info.class**, không tự thêm **requires**, **exports**, **opens**, **uses** hoặc **provides**.
- **--add-exports**, **--add-opens** và **--add-reads** thay đổi quyền truy cập/readability, không thay class.
- **--upgrade-module-path** thay thế module theo cơ chế upgrade; **--patch-module** chỉ patch nội dung.
- Ưu tiên dùng cho kiểm thử và debug có kiểm soát; phát hành chính thức nên cập nhật module/JAR đã build và kiểm thử đầy đủ.

## Tài liệu tham khảo

- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Module System — Java Platform Module System](https://openjdk.org/projects/jigsaw/spec/)
