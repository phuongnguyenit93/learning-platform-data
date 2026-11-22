# Module version và main class metadata

> Phạm vi: modular JAR trong Java Platform Module System (JPMS). Khi đóng gói một modular JAR, công cụ **jar** có thể ghi phiên bản module và main class vào module descriptor bên trong JAR. Đây là metadata của module, khác với các thuộc tính implementation trong manifest và khác với metadata của một JAR chạy theo cơ chế class path.

## Mục tiêu

Sau bài này, bạn có thể:

- Ghi phiên bản module bằng tùy chọn **--module-version**.
- Ghi main class của modular JAR bằng **--main-class**.
- Phân biệt metadata trong module descriptor với metadata trong **META-INF/MANIFEST.MF**.
- Kiểm tra module version và main class bằng **jar --describe-module**.
- Đọc metadata tại runtime bằng **ModuleDescriptor**.
- Chạy module mà không cần chỉ rõ main class trong lệnh.
- Hiểu giới hạn của module version trong module resolution.

## 1. Module version và main class metadata là gì?

Một modular JAR có file **module-info.class** ở thư mục gốc. File này chứa module descriptor: tên module, các directive như **requires**, **exports**, **opens**, **uses**, **provides**, cùng một số metadata khác.

Hai metadata thường dùng khi phát hành modular JAR là:

- **Module version**: phiên bản được gắn với module descriptor.
- **Main class**: lớp khởi chạy mặc định của module.

Khi tạo JAR bằng công cụ **jar**, có thể đặt hai giá trị này bằng:

- **--module-version**: ghi phiên bản module.
- **--main-class**: ghi main class cho module.

Ví dụ, modular JAR có tên module **com.acme.app**, phiên bản **2.4.1**, và main class **com.acme.app.Main**. Metadata này giúp công cụ kiểm tra và launcher biết thông tin phiên bản và lớp khởi chạy mặc định.

Lưu ý: tên file JAR như **acme-app-2.4.1.jar** không tự động làm module có version 2.4.1. Module version là metadata riêng được ghi vào module descriptor.

## 2. Tạo modular JAR có module version và main class

Giả sử source đã được biên dịch thành exploded module:

~~~text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/Main.class
~~~

Module descriptor:

~~~java
module com.acme.app {
    exports com.acme.app;
}
~~~

Main class:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Acme application");
    }
}
~~~

Tạo modular JAR:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Ý nghĩa:

- **--create** tạo JAR mới.
- **--file** chỉ định file JAR đầu ra.
- **--module-version 2.4.1** ghi version vào module descriptor.
- **--main-class com.acme.app.Main** ghi main class mặc định của module.
- **-C mods/com.acme.app .** chuyển vào thư mục module đã biên dịch và đưa nội dung của thư mục đó vào JAR.

Kết quả là **mlib/com.acme.app.jar** có module descriptor chứa tên module, version và main class. Hai tùy chọn trên không thay thế module descriptor; JAR vẫn phải là modular JAR hợp lệ.

Có thể dùng tên phiên bản theo quy ước dự án, ví dụ **1.0**, **2.4.1** hoặc **3.0.0-RC1**, miễn giá trị được công cụ chấp nhận như một module version hợp lệ. Nên thống nhất quy tắc version trong toàn bộ quá trình build và phát hành.

## 3. Module version được lưu ở đâu?

Module version được lưu trong metadata của module descriptor trong **module-info.class**, không phải chỉ dựa trên tên file JAR.

Có thể kiểm tra bằng:

~~~bash
jar --describe-module --file mlib/com.acme.app.jar
~~~

Kết quả minh họa:

~~~text
com.acme.app@2.4.1 jar:file:///.../com.acme.app.jar!/module-info.class
exports com.acme.app
requires java.base mandated
main-class com.acme.app.Main
~~~

Dòng đầu thể hiện tên module và version. Dòng **main-class** thể hiện lớp khởi chạy mặc định được ghi trong descriptor.

Tên file có thể là **com.acme.app.jar**, **acme-app-2.4.1.jar** hoặc tên khác; module name và module version được lấy từ descriptor. Đừng suy ra module version chỉ từ filename.

Nếu JAR chưa có module descriptor tường minh và được dùng như automatic module, nó không có cùng metadata module version/main class được ghi bằng các tùy chọn trên. **Automatic-Module-Name** trong manifest chỉ cung cấp tên automatic module, không biến JAR thành explicit modular JAR.

## 4. Main class metadata và ModuleMainClass

Với modular JAR, **--main-class** của công cụ jar ghi main class vào thuộc tính **ModuleMainClass** trong module descriptor.

Ví dụ:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Khi module descriptor có main class, có thể chạy module mà không cần chỉ rõ tên lớp:

~~~bash
java --module-path mlib --module com.acme.app
~~~

Launcher tìm main class đã được ghi trong module descriptor và gọi phương thức **public static void main(String[] args)**.

Cũng có thể chỉ rõ main class trong lệnh:

~~~bash
java --module-path mlib \
     --module com.acme.app/com.acme.app.Main
~~~

Cú pháp **-m module/main-class** chỉ định rõ lớp cần chạy. Cách này hữu ích khi module có nhiều entry point hoặc khi muốn chọn một lớp khác với main class mặc định đã ghi trong descriptor.

Nếu bỏ phần **/main-class** nhưng descriptor không có main class, launcher không biết lớp nào cần chạy và sẽ báo lỗi. Vì vậy, nếu muốn dùng cú pháp **java -m com.acme.app**, hãy chắc chắn modular JAR đã được đóng gói với **--main-class**.

## 5. Phân biệt ModuleMainClass với Main-Class trong manifest

Không nhầm hai metadata sau:

| Metadata | Nơi lưu | Mục đích |
|---|---|---|
| **ModuleMainClass** | Module descriptor trong **module-info.class** | Main class mặc định khi chạy named module bằng **java -m module** |
| **Main-Class** | Main section của **META-INF/MANIFEST.MF** | Main class của executable JAR chạy theo cơ chế **java -jar** |

Với modular JAR, dùng **--main-class** khi tạo JAR để ghi main class vào module descriptor. Khi chạy như named module, dùng **--module-path** và **--module**.

Với executable JAR truyền thống không có module descriptor, manifest thường chứa:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
~~~

và chạy bằng:

~~~bash
java -jar app.jar
~~~

**java -jar** và **java --module-path ... --module ...** là hai cách khởi chạy khác nhau. Nếu mục tiêu là khởi chạy ứng dụng như một named module, hãy dùng module path và module name.

## 6. Manifest implementation metadata khác module version

Manifest vẫn có thể chứa metadata mô tả artifact hoặc package, ví dụ:

~~~text
Manifest-Version: 1.0
Implementation-Title: Acme Application
Implementation-Version: 2.4.1
Implementation-Vendor: Acme Corporation
Specification-Title: Acme Application API
Specification-Version: 2.0
Specification-Vendor: Acme Corporation
~~~

Các thuộc tính này mô tả implementation hoặc specification của JAR/package. Chúng không tự động trở thành module version trong module descriptor.

Có thể thêm manifest tùy chỉnh khi tạo modular JAR:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --manifest manifest.mf \
    --module-version 2.4.1 \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Ở đây:

- **--module-version** ghi version vào module descriptor.
- **--main-class** ghi main class vào module descriptor.
- **--manifest** đưa các main attributes từ file manifest vào JAR.

Không nên chỉ đặt **Implementation-Version** trong manifest rồi kỳ vọng **jar --describe-module** hiển thị đó là module version. Nếu cần module version, hãy dùng **--module-version**.

Đối với package được nạp từ JAR, API **Package** có thể cung cấp implementation/specification metadata thông qua các phương thức như **getImplementationVersion()** và **getSpecificationVersion()**, nếu manifest cung cấp các thuộc tính tương ứng. Đây là metadata package, không thay thế **ModuleDescriptor.version()**.

## 7. Đọc module version và main class tại runtime

Từ một class nằm trong named module, có thể lấy module hiện tại:

~~~java
Module module = Main.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();
~~~

Đọc tên module:

~~~java
String moduleName = descriptor.name();
System.out.println("Module: " + moduleName);
~~~

Đọc version:

~~~java
descriptor.version().ifPresent(version ->
        System.out.println("Version: " + version)
);
~~~

Đọc main class:

~~~java
descriptor.mainClass().ifPresent(mainClass ->
        System.out.println("Main class: " + mainClass)
);
~~~

Ví dụ hoàn chỉnh:

~~~java
package com.acme.app;

import java.lang.module.ModuleDescriptor;

public final class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Module: " + descriptor.name());

        descriptor.version().ifPresent(version ->
                System.out.println("Version: " + version)
        );

        descriptor.mainClass().ifPresent(mainClass ->
                System.out.println("Main class: " + mainClass)
        );
    }
}
~~~

Với modular JAR được đóng gói ở ví dụ trước, output có thể là:

~~~text
Module: com.acme.app
Version: 2.4.1
Main class: com.acme.app.Main
~~~

**ModuleDescriptor.version()** và **ModuleDescriptor.mainClass()** trả về **Optional**, vì module version và main class không bắt buộc phải được khai báo.

Một lưu ý: **Module.getDescriptor()** có thể trả về **null** với unnamed module. Ví dụ trên giả định class đang chạy trong một named module có descriptor.

## 8. Kiểm tra metadata bằng jar và javap

Có thể kiểm tra thông tin module mà không cần chạy ứng dụng:

~~~bash
jar --describe-module --file mlib/com.acme.app.jar
~~~

Để xem nội dung JAR:

~~~bash
jar --list --file mlib/com.acme.app.jar
~~~

Kiểm tra **module-info.class** bằng javap:

~~~bash
javap -v --module-path mlib --module com.acme.app module-info
~~~

Output verbose cho biết các attribute trong class file, gồm module descriptor và metadata như **Module**, **ModuleMainClass** hoặc **ModuleTarget** nếu có.

Có thể dùng ba mức kiểm tra:

1. **jar --list** xác nhận JAR có **module-info.class** và main class.
2. **jar --describe-module** hiển thị module name, version, directives và main class.
3. **javap -v** hỗ trợ điều tra sâu nội dung attribute của module descriptor.

Khi kiểm tra artifact phát hành, hãy chạy lệnh trên đúng JAR được publish, không chỉ trên thư mục class đầu ra của compiler.

## 9. Module version có ảnh hưởng đến module resolution không?

Module version là metadata hữu ích cho quản lý phát hành và kiểm tra artifact, nhưng JPMS không dùng nó như một dependency constraint giống hệ thống quản lý package.

Ví dụ directive:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Directive **requires** tham chiếu module bằng tên **com.acme.lib**. Cú pháp này không chỉ định một version range như **requires com.acme.lib [2.0, 3.0)**.

Module resolver chủ yếu giải quyết module theo tên và module graph. Nó không tự chọn phiên bản cao nhất hoặc thỏa mãn một version range dựa trên **ModuleDescriptor.version()**.

Do đó:

- Module version giúp nhận diện và kiểm tra phiên bản module.
- Build tool hoặc dependency manager chịu trách nhiệm chọn phiên bản artifact trước khi chạy.
- Deployment phải bảo đảm module path chứa đúng bộ JAR mong muốn.
- Không nên đặt nhiều artifact cùng module name trong module path rồi kỳ vọng JPMS tự chọn version theo quy tắc semver.

Hãy quản lý dependency version bằng Maven, Gradle hoặc hệ thống phát hành của dự án; dùng module descriptor version như metadata bổ sung để quan sát và xác minh.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **jar --describe-module** không hiển thị version | Chưa tạo modular JAR với **--module-version** hoặc đang kiểm tra JAR khác | Kiểm tra đúng artifact và tạo lại bằng **--module-version** |
| Chạy **java -m module** báo không có main class | Module descriptor chưa có **ModuleMainClass** | Đóng gói với **--main-class** hoặc chỉ rõ **module/main-class** trong lệnh |
| **Main-Class** có trong manifest nhưng **java -m module** vẫn báo thiếu main class | Manifest Main-Class không thay thế ModuleMainClass của modular JAR | Dùng **jar --main-class** để ghi main class vào module descriptor |
| Filename có version nhưng descriptor không có version | Version chỉ nằm trong tên artifact | Dùng **--module-version** khi đóng gói |
| Manifest có **Implementation-Version** nhưng module version vẫn trống | Implementation metadata khác module descriptor version | Thêm **--module-version** |
| Runtime đọc được module name nhưng version rỗng | Version là metadata tùy chọn | Kiểm tra **descriptor.version()** và artifact đã publish |
| Không chạy được khi bỏ main class khỏi lệnh | Descriptor không khai báo main class | Dùng **--main-class** khi đóng gói hoặc chỉ rõ main class khi chạy |
| JAR không được nhận diện là explicit module | Thiếu **module-info.class** hoặc đang dùng automatic/class-path JAR | Kiểm tra JAR bằng **jar --describe-module** và cấu trúc nội dung |

Quy trình kiểm tra:

1. Dùng **jar --describe-module --file** để xác nhận JAR là module nào.
2. Kiểm tra version có hiển thị sau tên module hay không.
3. Kiểm tra dòng **main-class** có đúng tên lớp không.
4. Dùng **jar --list** để xác nhận main class và **module-info.class** có trong JAR.
5. Chạy bằng **java --module-path ... --module module-name**.
6. Thử cả cú pháp không chỉ rõ main class và cú pháp chỉ rõ **module/main-class**.
7. Nếu metadata runtime không như mong đợi, in **Module.getDescriptor()** của class đang chạy để xác định đúng module.

## 11. Ghi nhớ

- **--module-version** ghi version vào module descriptor của modular JAR.
- **--main-class** ghi main class mặc định vào module descriptor dưới dạng **ModuleMainClass**.
- **jar --describe-module** là cách nhanh để kiểm tra tên module, version và main class.
- **ModuleDescriptor.version()** và **mainClass()** cho phép đọc metadata tại runtime.
- **Implementation-Version** và **Specification-Version** trong manifest là package/implementation metadata; chúng không thay thế module version.
- **Main-Class** trong manifest phục vụ executable JAR truyền thống; **ModuleMainClass** phục vụ named module.
- **java -m module** dùng main class trong module descriptor; **java -m module/main-class** chỉ định rõ lớp chạy.
- JPMS không dùng module version để tự giải quyết version range; build/deployment tooling vẫn quản lý phiên bản dependency.

## Tài liệu tham khảo

- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The java Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [ModuleDescriptor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [ModuleDescriptor.Version — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.Version.html)
- [Package — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
