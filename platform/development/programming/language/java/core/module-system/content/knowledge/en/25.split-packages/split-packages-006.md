# Nhận diện bằng jdeps và module resolution

> Phạm vi: Java Platform Module System (JPMS). Bài này hướng dẫn tìm và xác minh **split package** bằng cách kết hợp phân tích dependency ở mức package của **jdeps**, kiểm tra nội dung JAR và xác thực module graph bằng Java module resolver.

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết một package đang xuất hiện trong nhiều module.
- Dùng **jdeps** để xem quan hệ phụ thuộc giữa module, class và package.
- Phân biệt package được tham chiếu với package thực sự được chứa trong một JAR.
- Kiểm kê package trong các JAR bằng **jar --list** và **jar --describe-module**.
- Dùng **java --validate-modules** để phát hiện xung đột trong các module có thể quan sát.
- Dùng **--show-module-resolution** để xem module resolver chọn những module nào khi chạy ứng dụng.
- Chọn cách xử lý split package phù hợp với ranh giới module.

## 1. Split package là gì?

**Split package** xảy ra khi cùng một tên package được chứa trong nhiều module khác nhau. Ví dụ, hai JAR đều có class trong package **com.acme.shared**:

~~~text
acme-core.jar
└── com/acme/shared/DateParser.class

acme-extra.jar
└── com/acme/shared/DateFormatter.class
~~~

Nếu hai JAR được xem là hai named module, package **com.acme.shared** đang bị chia giữa hai module. Đây là một vấn đề thiết kế trong JPMS vì package là một phần của ranh giới module: module chịu trách nhiệm chứa và kiểm soát package, còn module khác truy cập package thông qua quan hệ readability và exports.

Trên class path truyền thống, nhiều JAR có thể cùng đóng góp class vào một package của unnamed module. Cách tổ chức này thường hoạt động trong ứng dụng cũ. Khi chuyển các JAR lên module path, mỗi JAR có thể trở thành một named module; các package trùng tên khi đó có thể tạo xung đột trong module configuration.

Mức độ xung đột phụ thuộc vào module graph và khả năng các module cùng được resolve, đọc hoặc export package đó. Module resolver có thể từ chối cấu hình khi phát hiện split package không hợp lệ. Vì vậy, không nên giả định rằng mọi package trùng tên trong mọi JAR luôn gây cùng một lỗi; hãy kiểm tra module graph thực tế.

Một ví dụ khác là hai module cùng chứa class có cùng fully qualified name:

~~~text
com.acme.shared.DateParser
~~~

Đây là trường hợp nghiêm trọng hơn vì cùng một tên lớp xuất hiện ở hai module. Dù tên class không trùng, chỉ cần package bị chia giữa các module cũng có thể làm module configuration không hợp lệ.

## 2. Vì sao cần kết hợp jdeps và module resolution?

Hai công cụ giải quyết hai phần khác nhau của việc điều tra:

| Công cụ/cơ chế | Câu hỏi trả lời |
|---|---|
| **jdeps** | Module, class hoặc package nào tham chiếu tới package nào? Dependency tĩnh đang đi qua những module nào? |
| **jar --list** | Một JAR thực sự chứa những class/resource nào? Package nào xuất hiện trong nội dung JAR? |
| **jar --describe-module** | JAR được nhận diện là module nào và descriptor công bố package/directive gì? |
| **java --validate-modules** | Các module có thể quan sát có tạo thành cấu hình hợp lệ không? Có xung đột module cần sửa không? |
| **java --show-module-resolution** | Khi khởi chạy một ứng dụng, module resolver chọn module gốc và resolve dependency nào? |

**jdeps là phân tích tĩnh.** Nó giúp nhìn thấy các dependency được thể hiện trong bytecode và descriptor. Nó không tự thay thế việc kiểm kê toàn bộ package trong từng JAR, cũng không phát hiện chắc chắn mọi dependency phát sinh do reflection, tên lớp tạo động, plugin hoặc cấu hình runtime.

**Module resolution là kiểm tra cấu hình thực tế của JPMS.** Nó cho biết các module có thể được resolve thành một module graph hợp lệ hay không. Kết quả này cần được đọc cùng với package inventory và dependency report để xác định đúng JAR gây xung đột.

## 3. Chuẩn bị ví dụ có split package

Giả sử có ba module:

- **com.acme.core**: chứa một phần package **com.acme.shared**.
- **com.acme.extra**: chứa phần còn lại của package **com.acme.shared**.
- **com.acme.app**: sử dụng các API từ hai module trên.

Cấu trúc JAR:

~~~text
mods/
├── com.acme.core.jar
├── com.acme.extra.jar
└── com.acme.app.jar
~~~

Nội dung hai thư viện:

~~~text
com.acme.core.jar
└── com/acme/shared/DateParser.class

com.acme.extra.jar
└── com/acme/shared/DateFormatter.class
~~~

Module descriptor của core:

~~~java
module com.acme.core {
    exports com.acme.shared;
}
~~~

Module descriptor của extra:

~~~java
module com.acme.extra {
    exports com.acme.shared;
}
~~~

Module descriptor của app:

~~~java
module com.acme.app {
    requires com.acme.core;
    requires com.acme.extra;
}
~~~

Trong ví dụ này, app đọc cả hai module và cả hai module đều export **com.acme.shared**. Đây là cấu hình cần điều tra: cùng package xuất hiện trong hai module mà một module tiêu thụ đọc đồng thời.

## 4. Dùng jar để kiểm kê package thực sự có trong JAR

Bước đầu tiên là kiểm tra nội dung từng JAR, không chỉ nhìn tên file hoặc tên module.

Liệt kê nội dung:

~~~bash
jar --list --file mods/com.acme.core.jar
jar --list --file mods/com.acme.extra.jar
~~~

Có thể dùng dạng rút gọn:

~~~bash
jar tf mods/com.acme.core.jar
jar tf mods/com.acme.extra.jar
~~~

Tìm các entry thuộc package đang nghi ngờ:

Linux/macOS:

~~~bash
jar tf mods/com.acme.core.jar | grep '^com/acme/shared/'
jar tf mods/com.acme.extra.jar | grep '^com/acme/shared/'
~~~

Windows PowerShell:

~~~powershell
jar tf mods/com.acme.core.jar | Select-String '^com/acme/shared/'
jar tf mods/com.acme.extra.jar | Select-String '^com/acme/shared/'
~~~

Các entry có đường dẫn **com/acme/shared/** cho thấy JAR chứa class/resource trong package đó. Khi đối chiếu, chú ý:

- File **.class** cho biết class thuộc package.
- File resource cũng có thể nằm trong package path.
- **module-info.class** nằm ở gốc modular JAR và không phải class trong package ứng dụng.
- Tên package trong Java dùng dấu chấm; đường dẫn entry trong JAR dùng dấu gạch chéo.

Có thể mô tả module của từng JAR:

~~~bash
jar --describe-module --file mods/com.acme.core.jar
jar --describe-module --file mods/com.acme.extra.jar
~~~

Kết quả giúp xác nhận tên module và các package/directive mà công cụ suy ra hoặc đọc từ descriptor. Với explicit modular JAR, descriptor tường minh là nguồn khai báo module. Với automatic module, tên và danh sách package được suy ra theo quy tắc automatic module.

**jar --describe-module** hữu ích để kiểm tra danh tính module, còn **jar --list** hữu ích để kiểm tra entry thực tế. Dùng cả hai khi cần truy vết package trùng tên.

## 5. Dùng jdeps để xem dependency ở mức module

Trước hết, liệt kê dependency module của ứng dụng:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

Lệnh này phân tích dependency mà module app tham chiếu và liệt kê các module liên quan. Kết quả có thể cho thấy **com.acme.core**, **com.acme.extra** và các module JDK như **java.base**.

Có thể xuất danh sách dependency dạng comma-separated:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.app
~~~

Kết quả hữu ích khi chuẩn bị cấu hình module path hoặc tập module đầu vào cho công cụ như **jlink**.

Nếu muốn xem dependency bắc cầu, dùng tùy chọn recursive:

~~~bash
jdeps --module-path mods --recursive --list-deps --module com.acme.app
~~~

Khi có nhiều thư viện, hãy bảo đảm tất cả module cần phân tích đều nằm trong module path được truyền vào **jdeps**. Nếu thiếu một dependency, báo cáo có thể không đầy đủ hoặc xuất hiện cảnh báo không phân giải được.

## 6. Dùng jdeps để xem dependency ở mức package

Để xem package nào phụ thuộc vào package nào, dùng mức verbose package:

~~~bash
jdeps --module-path mods -verbose:package --module com.acme.app
~~~

Tùy chọn **-verbose:package** hiển thị dependency ở mức package. Nó giúp lần theo quan hệ như:

~~~text
com.acme.app -> com.acme.shared
com.acme.shared -> java.lang
~~~

Tên và cách trình bày chính xác trong output phụ thuộc JAR/module được phân tích. Hãy chú ý module chứa package đích trong phần output để biết dependency đang được resolve từ module nào.

Có thể phân tích trực tiếp một JAR:

~~~bash
jdeps --module-path mods -verbose:package mods/com.acme.app.jar
~~~

Hoặc xem ở mức class khi cần biết lớp nào tạo ra dependency:

~~~bash
jdeps --module-path mods -verbose:class mods/com.acme.app.jar
~~~

Các mức verbose:

- **-verbose:module**: quan hệ ở mức module.
- **-verbose:package**: quan hệ ở mức package.
- **-verbose:class**: quan hệ ở mức class.

Đối với split package, **-verbose:package** giúp nhận diện các package được tham chiếu và module mà dependency đi qua. Tuy nhiên, nếu một JAR chứa package mà không có class nào trong module đang phân tích tham chiếu tới, báo cáo dependency của app có thể không hiển thị package đó. Vì thế, hãy dùng **jar --list** để kiểm kê nội dung JAR khi tìm package trùng tên.

## 7. Dùng jdeps --check để xem module descriptor và dependency

Tùy chọn **--check** giúp phân tích dependency module và kiểm tra descriptor của các module được chỉ định:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Có thể kiểm tra nhiều module:

~~~bash
jdeps --module-path mods --check com.acme.core,com.acme.extra,com.acme.app
~~~

Output của **--check** giúp xem:

- Module đang khai báo những dependency nào.
- Dependency nào được sử dụng trong bytecode.
- Module descriptor có thể được tinh giản ra sao.
- Những dependency được khai báo nhưng không được dùng hoặc quan hệ module cần xem xét lại.

Tùy phiên bản JDK và module được phân tích, nội dung output có thể khác nhau. Đọc phần module descriptor hiện tại và phần gợi ý descriptor nếu công cụ cung cấp.

**--check không phải một phép kiểm kê đầy đủ mọi class/package trong mọi JAR.** Nó hỗ trợ phân tích dependency và descriptor; muốn xác nhận hai JAR có cùng package, vẫn phải kiểm tra package inventory hoặc dùng công cụ/module resolver để xác minh cấu hình.

## 8. Xác minh module graph bằng java --validate-modules

Sau khi kiểm tra nội dung JAR và dependency, dùng module resolver của Java để xác thực module path:

~~~bash
java --module-path mods --validate-modules
~~~

Tùy chọn **--validate-modules** yêu cầu launcher xác thực các module có thể quan sát được trong cấu hình hiện tại rồi kết thúc. Nó hữu ích để phát hiện lỗi module descriptor, module trùng tên, package conflict và các vấn đề khác trong module path.

Nếu có split package không hợp lệ trong tập module được kiểm tra, launcher có thể báo lỗi dạng:

~~~text
Error occurred during initialization of boot layer
java.lang.module.ResolutionException: ...
~~~

Thông báo cụ thể có thể nêu tên hai module hoặc package gây xung đột. Dùng chính tên module/package trong lỗi để quay lại kiểm tra hai JAR bằng **jar --list** và **jar --describe-module**.

Đây là bước quan trọng vì jdeps chỉ phân tích dependency tĩnh; module resolver kiểm tra tính hợp lệ của cấu hình JPMS mà launcher đang dùng.

Khi chạy lệnh, dùng đúng JDK/runtime tương ứng với dự án và truyền module path chứa các JAR cần kiểm tra. Nếu module path có nhiều thư mục hoặc JAR, hãy bảo đảm chúng thực sự là tập đầu vào muốn xác thực.

## 9. Quan sát module resolver khi khởi chạy ứng dụng

Để xem module nào được resolve khi chạy một ứng dụng modular, dùng:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Tùy chọn **--show-module-resolution** in thông tin module resolver khi launcher tạo module configuration. Output thường cho biết module gốc và các dependency được resolve.

Lệnh này giúp trả lời:

- Module chính nào được khởi chạy?
- Module nào được resolve do directive **requires**?
- Module hệ thống nào được đưa vào module graph?
- Provider module nào được liên kết khi có service binding?

Nếu ứng dụng thất bại trước khi chạy main class do split package, module resolution error thường chỉ ra xung đột cần xử lý. Nếu ứng dụng khởi chạy được nhưng module path khác với mong đợi, output resolution giúp xác định module thực tế được chọn.

**--show-module-resolution** chỉ hiển thị cấu hình được resolve cho lần chạy đó. Nó không thay thế **--validate-modules** khi cần kiểm tra module path tổng thể và cũng không tự liệt kê mọi package có trong từng JAR.

## 10. Quy trình điều tra split package hoàn chỉnh

Giả sử ứng dụng báo lỗi liên quan đến package **com.acme.shared**. Có thể điều tra theo trình tự:

1. Ghi lại tên package và các module được nêu trong thông báo lỗi.
2. Dùng **jar --describe-module --file** để xác nhận tên module của từng JAR.
3. Dùng **jar --list --file** để tìm các entry thuộc đường dẫn **com/acme/shared/** trong từng JAR.
4. Dùng **jdeps --list-deps** để hiểu module dependency của ứng dụng.
5. Dùng **jdeps -verbose:package** để xem package dependency của module/class đang gây ra vấn đề.
6. Dùng **jdeps --check** để xem descriptor và các dependency được khai báo.
7. Chạy **java --module-path mods --validate-modules** để xác nhận lỗi trong module configuration.
8. Chạy ứng dụng với **--show-module-resolution** để biết tập module thực tế được resolve.
9. Sửa cấu trúc thư viện/module, sau đó chạy lại các lệnh xác minh.

Ví dụ, nếu cả **com.acme.core.jar** và **com.acme.extra.jar** đều chứa entry thuộc **com/acme/shared/**, hãy xác định package này nên thuộc module nào. Không nên chỉ thêm **requires** hoặc **exports** để che lỗi; những directive đó không hợp nhất package đang nằm trong hai module.

## 11. Cách xử lý khi phát hiện split package

Các hướng xử lý thường dùng:

### Hợp nhất package vào một module

Nếu hai JAR là các phần của cùng một thư viện, có thể hợp nhất package vào một module duy nhất. Điều này tạo ra một chủ sở hữu rõ ràng cho package và giúp module descriptor phản ánh đúng ranh giới API.

### Di chuyển package sang namespace riêng

Nếu hai thư viện có thể được thay đổi, chuyển một phần package sang tên package riêng, chẳng hạn **com.acme.extra.shared**. Sau đó cập nhật import, API và cấu hình liên quan.

### Relocate package khi đóng gói

Với thư viện bên thứ ba, có thể dùng shading/relocation trong build để đổi package của một dependency trước khi phát hành artifact. Cần kiểm tra reflection, serialization, service configuration, native integration và API công khai vì đổi package có thể ảnh hưởng tương thích.

### Giữ thư viện legacy trên class path khi phù hợp

Một số ứng dụng có thể giữ thư viện cũ trên class path để chúng thuộc unnamed module, thay vì chuyển tất cả thành named module ngay lập tức. Đây là lựa chọn chuyển tiếp; cần kiểm tra tương tác giữa named module và unnamed module, cũng như tính đóng gói và khả năng bảo trì.

### Dùng --patch-module chỉ khi nội dung thuộc cùng một module

**--patch-module** có thể bổ sung class/resource vào một module đích. Nó phù hợp khi chủ đích là patch một module, ví dụ test hoặc hotfix có kiểm soát. Nó không phải cách chung để ghép hai thư viện độc lập đang khai báo thành hai named module vào cùng một module graph.

Không dùng **--add-exports**, **--add-reads** hoặc **--add-opens** như cách sửa split package. Những tùy chọn này thay đổi quyền truy cập/readability; chúng không chuyển package từ module này sang module khác.

## 12. Những giới hạn cần nhớ khi dùng jdeps

- jdeps phân tích bytecode và module metadata có thể quan sát; dependency phát sinh từ reflection hoặc tên lớp tạo động có thể bị bỏ sót.
- **-verbose:package** hiển thị package dependency, không phải danh sách đầy đủ package được chứa trong mỗi JAR.
- **--list-deps** và **--print-module-deps** tập trung vào module dependency, không xác định duy nhất JAR nào chứa một package.
- **--check** giúp xem descriptor/dependency và gợi ý điều chỉnh; không thay thế kiểm kê JAR.
- Kết quả phân tích phụ thuộc module path và phiên bản JDK dùng để chạy jdeps.
- Module resolution chỉ xác thực các module và root/configuration được launcher đưa vào phạm vi kiểm tra; hãy xác nhận lệnh đang dùng đúng module path và tập module mục tiêu.

Vì vậy, quy trình đáng tin cậy là kết hợp **jdeps để hiểu dependency**, **jar để kiểm kê package**, và **java module resolver để xác thực module graph**.

## 13. Ghi nhớ

- Split package là cùng một package xuất hiện trong nhiều module.
- **jar --list** cho biết JAR thực sự chứa class/resource nào; dùng nó để so sánh package inventory.
- **jar --describe-module** xác nhận module name và descriptor.
- **jdeps --list-deps** xem dependency ở mức module.
- **jdeps -verbose:package** xem dependency ở mức package; **-verbose:class** đi sâu tới class.
- **jdeps --check** hỗ trợ phân tích module descriptor và dependency.
- **java --validate-modules** kiểm tra tính hợp lệ của các module có thể quan sát.
- **--show-module-resolution** hiển thị module được resolve khi khởi chạy ứng dụng.
- jdeps không thay thế module resolver và cũng không tự liệt kê mọi package trong từng JAR.
- Cách sửa bền vững là tạo một module sở hữu package rõ ràng, di chuyển hoặc relocate package khi cần.

## Tài liệu tham khảo

- [The jdeps Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Java Platform Module System — OpenJDK Project Jigsaw](https://openjdk.org/projects/jigsaw/spec/)
