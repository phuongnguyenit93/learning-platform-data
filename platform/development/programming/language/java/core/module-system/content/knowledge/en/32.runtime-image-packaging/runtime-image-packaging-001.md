# jlink và custom runtime image

> Phạm vi: Java Platform Module System (JPMS). **jlink** là công cụ của JDK dùng để liên kết một tập named module cùng các dependency cần thiết thành một runtime image tùy chỉnh. Image này có thể được phân phối cùng ứng dụng để chạy trên máy đích mà không cần cài một JDK đầy đủ.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích custom runtime image và vai trò của **jlink**.
- Chuẩn bị các explicit module làm đầu vào cho quá trình link.
- Phân tích dependency để chọn module gốc bằng **--add-modules**.
- Tạo image từ module JDK và module ứng dụng.
- Tích hợp service provider bằng **--bind-services** khi cần.
- Tạo launcher riêng cho ứng dụng bằng **--launcher**.
- Giảm kích thước image bằng các tùy chọn đóng gói phù hợp.
- Chạy và kiểm tra ứng dụng bằng chính runtime image đã tạo.

## 1. Custom runtime image là gì?

Một **runtime image** là cây thư mục chứa Java runtime và các module được đóng gói để chạy chương trình. Một JDK đầy đủ thường chứa cả công cụ phát triển như **javac**, **javadoc**, **jlink** và các thư viện phục vụ build. Custom runtime image do **jlink** tạo tập trung vào tập module cần cho ứng dụng, vì vậy thường nhỏ hơn JDK đầy đủ.

Cấu trúc image có thể tương tự:

~~~text
runtime-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── legal/
├── lib/
│   ├── modules
│   ├── security/
│   └── ...
└── release
~~~

Tên và số lượng file cụ thể phụ thuộc JDK, nền tảng và tùy chọn link. Trên Windows, launcher Java thường là **bin/java.exe**; launcher ứng dụng có thể được tạo dưới dạng file thực thi hoặc script trong **bin**.

Một số điểm cần phân biệt:

- Custom runtime image có Java runtime để chạy ứng dụng, nhưng không mặc nhiên có compiler và các công cụ phát triển của JDK.
- Image chỉ chứa các module được chọn cùng dependency đã resolve, không phải toàn bộ module của JDK.
- Image chứa thư viện native và thành phần phụ thuộc hệ điều hành/kiến trúc CPU.
- Image là artifact có thể phân phối cùng ứng dụng; nó không tự đóng gói mọi file cấu hình, dữ liệu, native library bên ngoài hoặc tài nguyên riêng của ứng dụng.

## 2. Điều kiện đầu vào của jlink

**jlink** liên kết các module có module descriptor tường minh. Nguồn module có thể là:

- Các module JDK trong thư mục **$JAVA_HOME/jmods**.
- Modular JAR có **module-info.class**.
- Exploded module đã biên dịch, có **module-info.class** ở thư mục gốc module.
- Các module JMOD được tạo cho ứng dụng hoặc thư viện.

**Automatic module không thể được link trực tiếp bằng jlink.** Nếu ứng dụng phụ thuộc vào một thư viện JAR chỉ có **Automatic-Module-Name** hoặc tên automatic module suy từ filename, cần chuyển thư viện đó thành explicit module trước. Việc thêm Automatic-Module-Name chỉ đặt tên automatic module; nó không tạo ra descriptor tường minh.

Có thể kiểm tra JDK đang dùng:

~~~bash
java --version
jlink --version
~~~

Trên Windows PowerShell:

~~~powershell
java.exe --version
jlink.exe --version
~~~

Nên dùng **jlink** từ JDK tương thích với phiên bản Java mục tiêu và kiểm tra module đầu vào có thể resolve trên module path. JDK cung cấp các module hệ thống trong thư mục **jmods**.

## 3. Ví dụ ứng dụng gồm hai module

Giả sử ứng dụng có module thư viện **com.acme.lib** và module chính **com.acme.app**.

Cấu trúc source:

~~~text
project/
└── src/
    ├── com.acme.lib/
    │   ├── module-info.java
    │   └── com/acme/lib/Message.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Module thư viện, file **src/com.acme.lib/module-info.java**:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

Class API, file **src/com.acme.lib/com/acme/lib/Message.java**:

~~~java
package com.acme.lib;

public final class Message {
    private Message() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module ứng dụng, file **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Main class, file **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.lib.Message;

public final class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greet(name));
    }
}
~~~

Module **com.acme.app** khai báo **requires com.acme.lib** vì nó sử dụng API được export từ module thư viện. Đây là quan hệ dependency mà module resolver sẽ dùng khi tạo runtime image.

## 4. Biên dịch module ứng dụng

Đứng tại thư mục **project**, biên dịch cả hai module:

~~~bash
javac --module-source-path src -d mods -m com.acme.lib,com.acme.app
~~~

Giải thích:

- **--module-source-path src** chỉ định cây thư mục source theo module.
- **-d mods** đặt output đã biên dịch trong thư mục **mods**.
- **-m com.acme.lib,com.acme.app** yêu cầu compiler biên dịch hai module.

Sau khi biên dịch, cấu trúc có dạng:

~~~text
mods/
├── com.acme.lib/
│   ├── module-info.class
│   └── com/acme/lib/Message.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Các thư mục **mods/com.acme.lib** và **mods/com.acme.app** là exploded modules. Chúng có thể được đặt trên module path làm đầu vào cho jlink.

Trong dự án thực tế, module có thể được đóng gói thành modular JAR trước khi link. Dù dùng exploded module hay JAR, điều kiện quan trọng là module descriptor và dependency phải hợp lệ.

## 5. Phân tích dependency trước khi link

Không nên chọn module theo phỏng đoán. Hãy phân tích dependency tĩnh của ứng dụng và các module thư viện.

Ví dụ:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.app
~~~

Kết quả liệt kê các module dependency mà công cụ nhận diện được từ bytecode/module metadata. Có thể dùng thêm:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.app
~~~

**jdeps** hỗ trợ tìm dependency tĩnh; các class được nạp qua reflection, tên lớp tạo động, plugin hoặc cấu hình ngoài có thể không được nhận diện đầy đủ. Vì vậy, hãy kết hợp kết quả với module descriptor, cấu hình runtime và kiểm thử thực tế.

Khi dùng **--add-modules com.acme.app**, jlink resolve module gốc này cùng các dependency bắt buộc theo module graph. Thông thường không cần liệt kê thủ công từng dependency đã được khai báo bằng **requires**. Có thể thêm nhiều module gốc nếu ứng dụng cần chúng:

~~~bash
--add-modules com.acme.app,com.acme.tools
~~~

Nếu một module chỉ được nạp động hoặc cần được resolve dù không nằm trong dependency graph thông thường, hãy xác định rõ module đó và thêm làm root khi phù hợp.

## 6. Tạo custom runtime image bằng jlink

Module JDK nằm trong **$JAVA_HOME/jmods**; các module ứng dụng đã biên dịch nằm trong **mods**. Tạo image:

Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --output runtime-image
~~~

Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods;mods" --add-modules com.acme.app --output runtime-image
~~~

Ý nghĩa các tùy chọn:

- **--module-path** chỉ định nơi jlink tìm module. Ví dụ gồm thư mục JMOD của JDK và thư mục exploded module của ứng dụng.
- **--add-modules** chỉ định module gốc cần đưa vào image.
- jlink resolve dependency của module gốc và liên kết module cần thiết vào image.
- **--output** chỉ định thư mục image đầu ra.

Thư mục output cần chưa tồn tại hoặc phải rỗng theo yêu cầu của công cụ. Hãy chọn một đường dẫn build riêng cho mỗi lần tạo image để tránh ghi đè một artifact đang được sử dụng.

Sau khi lệnh hoàn tất, **runtime-image** là runtime tùy chỉnh. Image này có thể chạy module ứng dụng bằng Java launcher nằm trong chính thư mục image.

## 7. Liên kết service provider bằng --bind-services

Một ứng dụng có thể sử dụng ServiceLoader để tìm implementation của một service. Ví dụ module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.GreetingService;
}
~~~

Provider module khai báo:

~~~java
module com.acme.provider {
    requires com.acme.spi;
    provides com.acme.spi.GreetingService
        with com.acme.provider.EnglishGreetingService;
}
~~~

Nếu muốn jlink tìm và liên kết các provider module cho service được dùng bởi các module đang link, thêm **--bind-services**:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --bind-services --output runtime-image
~~~

Tùy chọn này mở rộng quá trình resolve để đưa provider module phù hợp cùng dependency của chúng vào image. Điều này hữu ích khi provider không được app khai báo bằng **requires** trực tiếp mà được tìm thông qua service binding.

**--bind-services** không thay thế khai báo service:

- Consumer module vẫn cần **uses**.
- Provider module vẫn cần **provides ... with ...**.
- Provider phải có mặt trên module path và đáp ứng quy tắc service provider.
- Ứng dụng cần chạy thử luồng ServiceLoader trên image sau khi link.

Nếu ứng dụng tự nạp plugin từ thư mục bên ngoài hoặc tạo module layer riêng lúc chạy, hãy thiết kế và kiểm thử cơ chế đó riêng. jlink không tự đóng gói mọi plugin tùy ý nằm ngoài module graph.

## 8. Tạo launcher riêng bằng --launcher

Có thể yêu cầu jlink tạo launcher mang tên ứng dụng thay vì bắt người dùng gõ đầy đủ **java --module ...**.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --output runtime-image
~~~

Cú pháp:

~~~text
--launcher <launcher-name>=<module-name>/<main-class>
~~~

Trong ví dụ:

- **app** là tên launcher được tạo.
- **com.acme.app** là module chứa chương trình.
- **com.acme.app.Main** là main class.

Sau khi link, chạy launcher:

Linux/macOS:

~~~bash
./runtime-image/bin/app
~~~

Windows:

~~~powershell
.\runtime-image\bin\app.bat
~~~

Tên và định dạng launcher thực tế phụ thuộc nền tảng. Hãy kiểm tra thư mục **bin** của image sau khi link.

Có thể tạo nhiều launcher trong cùng một image nếu ứng dụng có nhiều entry point:

~~~bash
--launcher app=com.acme.app/com.acme.app.Main
--launcher admin=com.acme.app/com.acme.app.AdminMain
~~~

Mỗi launcher trỏ tới module và main class tương ứng. Module chứa main class phải nằm trong image.

## 9. Tối ưu kích thước runtime image

jlink cung cấp các tùy chọn giúp giảm kích thước image:

| Tùy chọn | Tác dụng |
|---|---|
| **--strip-debug** | Loại bỏ thông tin debug trong các module được link |
| **--no-header-files** | Không đưa header file native vào image |
| **--no-man-pages** | Không đưa man page vào image |
| **--compress=0** | Không dùng mức nén resource |
| **--compress=1** | Nén constant string sharing |
| **--compress=2** | Nén resource bằng ZIP |

Ví dụ kết hợp:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime-image
~~~

Nén và loại bỏ debug/header/man page có thể giảm dung lượng phân phối. Tuy nhiên, hãy đo kích thước image và kiểm thử thời gian khởi động, hiệu năng và hành vi ứng dụng trên môi trường đích. Không nên bật mọi tùy chọn chỉ vì mục tiêu tạo image nhỏ nhất; giữ lại thành phần cần cho vận hành, chẩn đoán hoặc chính sách phân phối.

Có thể dùng **--limit-modules** để giới hạn tập module có thể quan sát trong quá trình resolve. Đây là tùy chọn kiểm soát module universe, không phải cách thay thế việc phân tích dependency. Nếu giới hạn quá chặt, module cần thiết có thể không resolve được.

## 10. Chạy ứng dụng từ custom runtime image

Nếu image có launcher Java, có thể chạy module chính trực tiếp:

Linux/macOS:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main
~~~

Windows:

~~~powershell
.\runtime-image\bin\java.exe --module com.acme.app/com.acme.app.Main
~~~

Truyền đối số cho chương trình sau phần module/main class:

~~~bash
./runtime-image/bin/java --module com.acme.app/com.acme.app.Main Lan
~~~

Ứng dụng nhận **Lan** trong **String[] args**.

Nếu đã tạo launcher riêng:

~~~bash
./runtime-image/bin/app
~~~

Hãy chạy bằng executable trong image đã tạo, không chỉ chạy Java trên PATH của máy build. Điều này xác nhận ứng dụng đang dùng đúng tập module đã đóng gói.

Custom runtime image thường không có **javac**. Thực hiện compile và đóng gói bằng JDK trước; image được phân phối phục vụ runtime.

## 11. Kiểm tra image sau khi tạo

Có thể xác minh image bằng chính Java launcher trong image:

~~~bash
./runtime-image/bin/java --version
./runtime-image/bin/java --list-modules
./runtime-image/bin/java --describe-module com.acme.app
~~~

Các lệnh này giúp xác nhận phiên bản Java, module được cung cấp và descriptor của module ứng dụng.

Kiểm tra cấu trúc image:

~~~text
runtime-image/
├── bin/
├── conf/
├── legal/
├── lib/
└── release
~~~

Nếu cần xác minh nội dung JIMAGE, dùng công cụ **jimage** từ JDK tương thích để xem file **runtime-image/lib/modules**. jimage không nhất thiết có trong image tối giản.

Cuối cùng, chạy ứng dụng và các luồng quan trọng trên image. Một module xuất hiện trong **--list-modules** chưa đủ chứng minh mọi class/resource/native library cần thiết đã được đóng gói hoặc ứng dụng không cần module nạp động.

## 12. Runtime image phụ thuộc nền tảng

Runtime image chứa thành phần native nên gắn với nền tảng và kiến trúc mà nó được tạo cho. Image tạo trên Linux x64 không phải là artifact có thể chạy trực tiếp trên Windows hoặc macOS.

Khi phát hành cho nhiều nền tảng:

- Tạo image riêng cho từng hệ điều hành và kiến trúc CPU được hỗ trợ.
- Dùng JDK/JMOD phù hợp với nền tảng mục tiêu.
- Kiểm thử trên máy đích hoặc môi trường tương đương.
- Kiểm tra native library, file cấu hình, quyền thực thi và đường dẫn.
- Đảm bảo image được phân phối cùng các thông báo license/legal cần thiết.

Không nên chỉ đổi tên thư mục image để giả định nó tương thích với nền tảng khác. Hãy coi mỗi image là một artifact nền tảng riêng và quản lý phiên bản/build tương ứng.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **jlink: Module ... not found** | Module ứng dụng hoặc dependency không nằm trong module path | Kiểm tra **--module-path**, tên module và JMOD/JAR đầu vào |
| **Automatic module cannot be used with jlink** | Dependency chỉ là automatic module | Chuyển thư viện thành explicit module có **module-info.class** |
| **Module ... not found, required by ...** | Dependency trong **requires** không được resolve | Thêm module cần thiết vào module path và kiểm tra descriptor |
| Output directory không hợp lệ | Thư mục output đã tồn tại và không rỗng | Dùng thư mục output mới hoặc rỗng theo yêu cầu của jlink |
| Provider không có trong image | Provider module không được resolve hoặc chưa dùng service binding | Kiểm tra **uses/provides**, module path và cân nhắc **--bind-services** |
| Launcher riêng không chạy | Sai module/main class hoặc module không được link | Kiểm tra **--launcher** và xác nhận module có trong image |
| Chạy được trên JDK nhưng lỗi trên image | JDK có module/công cụ mà custom image đã lược bỏ | Chạy thử bằng Java trong image và bổ sung dependency thật sự cần |
| Image không chạy trên máy đích | Image được tạo cho OS/CPU khác hoặc thiếu thành phần native | Tạo image theo nền tảng đích và kiểm thử trên môi trường tương ứng |

Quy trình xử lý cơ bản:

1. Chạy **jdeps --print-module-deps** để xem dependency tĩnh.
2. Kiểm tra descriptor và module name của các dependency.
3. Xác nhận mọi module đầu vào là explicit module.
4. Chọn module gốc bằng **--add-modules**.
5. Thêm **--bind-services** nếu cần service provider.
6. Tạo image vào thư mục output sạch.
7. Chạy **--list-modules** và khởi chạy ứng dụng từ image.
8. Thử các tính năng sử dụng reflection, service, native library hoặc cấu hình ngoài.

## 14. Ghi nhớ

- **jlink** tạo custom runtime image từ named module có descriptor tường minh.
- **--module-path** cung cấp module JDK và module ứng dụng; **--add-modules** chọn module gốc.
- jlink tự resolve dependency trong module graph.
- Automatic module không thể được link trực tiếp.
- **--bind-services** giúp đưa service provider phù hợp vào image.
- **--launcher** tạo launcher riêng cho module/main class.
- **--strip-debug**, **--no-header-files**, **--no-man-pages** và **--compress** hỗ trợ tối ưu image.
- Image là artifact phụ thuộc OS/CPU; cần tạo và kiểm thử theo nền tảng đích.
- Luôn chạy thử ứng dụng bằng Java launcher nằm trong chính image sẽ phân phối.

## Tài liệu tham khảo

- [The jlink Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282)
- [Java Platform Module System — OpenJDK Project Jigsaw](https://openjdk.org/projects/jigsaw/spec/)
