# IllegalAccessError do thiếu exports hoặc reads

Trong Java Platform Module System (JPMS), mã Java có thể biên dịch thành công nhưng thất bại lúc chạy với **java.lang.IllegalAccessError**. Một nguyên nhân quan trọng là quan hệ truy cập giữa các named module không còn hợp lệ ở runtime: module gọi **không đọc được** module chứa kiểu cần dùng, hoặc package chứa kiểu đó **không được export** cho module gọi.

IllegalAccessError thuộc nhóm **LinkageError**. JVM có thể phát hiện lỗi khi phân giải tham chiếu đến class, method hoặc field trong bytecode. Vì thế, lỗi thường xuất hiện khi lớp được nạp hoặc khi một đường thực thi lần đầu dùng thành viên, chứ không nhất thiết ngay lúc khởi động ứng dụng.

Bài này tập trung vào lỗi do **readability** và **exports**, cách tái hiện, cách đọc thông báo JVM, cách dùng requires, exports, --add-reads và --add-exports, cùng quy trình xử lý mà không mở rộng quyền truy cập quá mức.

## 1. Đọc module và truy cập package là hai điều kiện khác nhau

Để mã trong named module com.example.app sử dụng một public class nằm trong com.example.library, cần xem ít nhất ba tầng:

1. **Readability:** com.example.app có đọc com.example.library không? Thông thường điều này được khai báo bằng requires trong module-info.java.
2. **Package export:** com.example.library có export package chứa class đó cho com.example.app không?
3. **Java language access:** class, constructor, method hoặc field có mức truy cập phù hợp không?

Ví dụ module thư viện:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Module ứng dụng:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Với cấu hình này, com.example.app đọc com.example.library và có thể sử dụng các kiểu public của package com.example.library.api.

Nhưng nếu com.example.library cũng có package com.example.library.internal mà không export, ứng dụng không được dùng public class trong internal như API thông thường.

**requires cho phép đọc module; exports cho phép truy cập package.** Một điều kiện không thay thế điều kiện kia.

## 2. Vì sao lỗi có thể chỉ xuất hiện ở runtime?

Compiler javac thường phát hiện trước việc thiếu requires hoặc exports. Tuy nhiên vẫn có những tình huống compile-time và runtime sử dụng cấu hình khác nhau:

- Khi biên dịch có --add-exports nhưng khi chạy lại thiếu cờ tương ứng.
- Khi biên dịch có --add-reads nhưng runtime không có quan hệ đọc đó.
- Các JAR/module descriptor đã thay đổi giữa thời điểm build và triển khai.
- Bytecode được tạo hoặc biến đổi bởi công cụ instrumentation, proxy hoặc compiler khác.
- Một thư viện được biên dịch dựa trên API public nhưng runtime cung cấp phiên bản đã thay đổi visibility hoặc exports.
- Các module được nạp trong ModuleLayer tùy chỉnh với cấu hình không giống môi trường build.

Khi JVM liên kết một tham chiếu bytecode, nó kiểm tra quyền truy cập hiệu lực tại runtime. Nếu quyền không đáp ứng, có thể phát sinh IllegalAccessError.

Điều quan trọng là không kết luận “đã compile thì runtime chắc chắn có quyền”. JPMS còn phụ thuộc vào module graph và runtime configuration thực tế.

## 3. Phân biệt các lỗi dễ nhầm

| Lỗi | Thời điểm thường gặp | Nguyên nhân cần xem |
| --- | --- | --- |
| error: package ... is not visible | Biên dịch | Thiếu requires/readability hoặc package không export. |
| java.lang.module.FindException: Module ... not found | Resolve module khi khởi chạy | Module chưa tìm thấy trong nguồn mô-đun. |
| java.lang.module.ResolutionException | Resolve module graph | Xung đột cấu hình hoặc ràng buộc mô-đun không thể resolve. |
| IllegalAccessError | Runtime linking | JVM không cho phép tham chiếu class/member; có thể do reads, exports hoặc visibility. |
| IllegalAccessException | Reflective operation hoặc MethodHandles | Caller không đủ quyền truy cập khi thao tác reflection. |
| InaccessibleObjectException | Khi cố bật deep reflection | Package chưa open cho caller, thường tại setAccessible(true). |
| ClassNotFoundException | Tìm/nạp lớp theo tên | Class loader không tìm thấy class. |
| NoClassDefFoundError | Định nghĩa hoặc liên kết lớp ở runtime | Thiếu class hoặc một lỗi nền tảng liên quan đến class initialization/loading. |

IllegalAccessError không chỉ do JPMS: các thay đổi private/public, class hierarchy hoặc binary incompatibility cũng có thể gây lỗi này. Hãy đọc **toàn bộ thông báo** để xác định lỗi đang nói về package/module hay về member visibility.

## 4. Ví dụ tái hiện lỗi thiếu exports

Giả sử thư viện có một class public nằm trong package internal. Nó có thể được dùng trong cùng module, nhưng không phải public API cho module khác.

Cấu trúc:

~~~text
src/
├── com.example.library/
│   ├── module-info.java
│   └── com/example/library/internal/InternalFormatter.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Descriptor của library:

~~~java
module com.example.library {
    // Không exports com.example.library.internal.
}
~~~

Lớp internal:

~~~java
package com.example.library.internal;

public final class InternalFormatter {
    private InternalFormatter() {
    }

    public static String format(String text) {
        return "[" + text + "]";
    }
}
~~~

Descriptor của app:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Mã app:

~~~java
package com.example.app;

import com.example.library.internal.InternalFormatter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(InternalFormatter.format("JPMS"));
    }
}
~~~

Nếu biên dịch bình thường, javac sẽ từ chối import vì package internal không được export cho com.example.app. Đó là kết quả đúng của JPMS.

Tuy nhiên, ta có thể cố ý cấp quyền chỉ tại compile-time để tái hiện sự khác biệt với runtime.

## 5. Compile có --add-exports nhưng chạy không có

Giả sử thư mục src như ví dụ và đang sử dụng JDK có hỗ trợ JPMS, có thể biên dịch bằng:

~~~bash
javac --module-source-path src \
    --add-exports com.example.library/com.example.library.internal=com.example.app \
    -d out \
    -m com.example.library,com.example.app
~~~

Tùy chọn --add-exports cho compiler biết com.example.library.internal có thể được dùng từ com.example.app trong lần biên dịch này.

Sau đó chạy **không có** quyền export bổ sung:

~~~bash
java --module-path out \
    -m com.example.app/com.example.app.Main
~~~

JVM có thể ném IllegalAccessError, với thông báo tương tự:

~~~text
java.lang.IllegalAccessError:
class com.example.app.Main (in module com.example.app)
cannot access class com.example.library.internal.InternalFormatter
(in module com.example.library)
because module com.example.library does not export
com.example.library.internal to module com.example.app
~~~

Thông báo chỉ rõ module nguồn, module đích và package thiếu exports. Đây là lỗi runtime linking, không phải lỗi thiếu file JAR.

## 6. Sửa ví dụ bằng --add-exports ở runtime

Để cấp cùng quyền trong JVM runtime, truyền:

~~~bash
java --module-path out \
    --add-exports com.example.library/com.example.library.internal=com.example.app \
    -m com.example.app/com.example.app.Main
~~~

Đầu ra mong đợi:

~~~text
[JPMS]
~~~

Cú pháp:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Ý nghĩa:

- SOURCE_MODULE là module sở hữu package.
- PACKAGE là package cần export.
- TARGET_MODULE là module muốn truy cập public API trong package đó.

Tùy chọn này giúp xử lý tương thích, nhưng không biến internal package thành hợp đồng API ổn định. Nếu bạn quản lý thư viện và muốn consumer chính thức dùng lớp đó, nên thiết kế lại package API và descriptor thay vì yêu cầu mọi consumer truyền cờ.

## 7. Sửa bền vững bằng module-info.java

Nếu package thực sự chứa API công khai, module sở hữu có thể export nó:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Giả sử định nghĩa lại lớp thành:

~~~java
package com.example.library.api;

public final class Formatter {
    private Formatter() {
    }

    public static String format(String text) {
        return "[" + text + "]";
    }
}
~~~

Consumer import Formatter từ package api, khai báo requires và không cần --add-exports.

Nếu chỉ một module tích hợp được phép dùng package đặc thù, có thể sử dụng qualified exports:

~~~java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.integration
        to com.example.app;
}
~~~

Cách này chỉ cấp export cho com.example.app. Nhưng nó vẫn là một phần hợp đồng của module library, nên cần cân nhắc compatibility nếu đổi hoặc xóa về sau.

Không nên export toàn bộ package internal chỉ để sửa một lỗi khi chưa xác định ý nghĩa của API.

## 8. Trường hợp thiếu readability: module không reads module khác

Module graph sử dụng quan hệ **reads** có hướng. Nếu com.example.app đọc com.example.library, điều đó không có nghĩa com.example.library cũng đọc com.example.app.

Descriptor thông thường:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Khai báo requires tạo readability từ app tới library. Khi một class của app tham chiếu class public thuộc package đã export của library, JVM vẫn cần thấy quan hệ đọc phù hợp tại runtime.

Có thể quan sát bằng API:

~~~java
Module appModule = Main.class.getModule();
Module libraryModule = SomePublicApi.class.getModule();

System.out.println(
        appModule.canRead(libraryModule));
~~~

Trong ví dụ, SomePublicApi là một class public thuộc package đã export của library mà chương trình có thể tham chiếu hợp lệ.

Nếu canRead trả về false, quan hệ đọc từ module app tới module library chưa tồn tại trong cấu hình hiện tại.

Lưu ý: Java tự cung cấp readability tới java.base cho mọi named module. Với các module khác, cần quan hệ được tạo qua requires, requires transitive hoặc các cơ chế hợp lệ tương ứng.

## 9. Cú pháp --add-reads và tính có hướng

Khi cần bổ sung readability mà không thể chỉnh descriptor, có thể dùng:

~~~text
--add-reads SOURCE_MODULE=TARGET_MODULE
~~~

Ví dụ:

~~~bash
java --module-path out \
    --add-reads com.example.app=com.example.library \
    -m com.example.app/com.example.app.Main
~~~

Câu lệnh có nghĩa com.example.app đọc com.example.library. Nó không có nghĩa library đọc app.

Tuy nhiên, đây chỉ là quan hệ readability. Nếu library không export package cho app, thêm --add-reads đơn thuần vẫn không đủ.

Vì vậy, khi chẩn đoán:

- Nếu thông báo nói module A does not read module B: kiểm tra requires và, khi có lý do chuyển tiếp, --add-reads.
- Nếu thông báo nói module B does not export package p to module A: kiểm tra exports hoặc --add-exports.
- Nếu cả hai điều kiện không tồn tại, cần xử lý riêng cả hai.

Việc đặt --add-reads không tự tải một module chưa có trong module graph. Module đích cần được tìm thấy và resolve thích hợp trước khi quan hệ đọc bổ sung có ý nghĩa.

## 10. Reproducer cho readability: tách compile-time và runtime

Một tình huống để nghiên cứu:

- Module thư viện com.example.library export package com.example.library.api.
- Module com.example.app sử dụng public class trong package này.
- Module descriptor của app không khai báo requires com.example.library.
- Trong lần biên dịch, công cụ được cấp thêm readability tới library.
- Khi chạy, quan hệ đọc bổ sung không còn.

Descriptor của library:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Descriptor của app:

~~~java
module com.example.app {
    // Cố ý thiếu requires com.example.library.
}
~~~

Để javac có đủ dữ liệu trong một môi trường minh họa, có thể dùng:

~~~bash
javac --module-source-path src \
    --add-reads com.example.app=com.example.library \
    -d out \
    -m com.example.library,com.example.app
~~~

Với runtime, library có thể cần được resolve như một root bổ sung vì app không requires library:

~~~bash
java --module-path out \
    --add-modules com.example.library \
    -m com.example.app/com.example.app.Main
~~~

Nếu bytecode của app được biên dịch để tham chiếu public class từ library, nhưng runtime không có readability, JVM có thể từ chối liên kết bằng IllegalAccessError.

Cách sửa bền vững là khai báo:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Nếu đặc thù môi trường buộc phải giữ dependency ở ngoài descriptor, phải giải thích lý do và cung cấp --add-reads ở đúng giai đoạn cần thiết. Không biến sự thiếu nhất quán compile/run thành thiết kế mặc định.

## 11. --add-reads tới ALL-UNNAMED

Một trường hợp phổ biến là named module phải tham chiếu tới thư viện legacy trên classpath.

Thư viện nằm trên classpath thuộc unnamed module; không thể viết requires với một tên module cụ thể cho nó. Với một số cấu hình kiểm thử hoặc migration, có thể dùng:

~~~text
--add-reads com.example.app=ALL-UNNAMED
~~~

Tùy chọn này cho phép com.example.app đọc unnamed modules trong runtime phù hợp.

Nhưng nó không chuyển JAR legacy thành named module và không thêm JAR đó vào classpath. Thư viện vẫn phải có mặt ở đúng đường dẫn và được class loader tìm thấy.

Nếu thư viện hỗ trợ automatic module hoặc có descriptor, một hướng thiết kế khác là đặt JAR trên module path và dùng module name đã xác minh bằng jar --describe-module.

Khi chọn ALL-UNNAMED, hãy ghi rõ vì sao cần quan hệ rộng này và phạm vi sử dụng là test, migration hay production.

## 12. exports có thể là qualified

Module library có thể export package chỉ cho một số module:

~~~java
module com.example.library {
    exports com.example.library.api
        to com.example.app;
}
~~~

Trong trường hợp này:

- com.example.app có thể truy cập các kiểu public của api nếu có readability phù hợp.
- com.example.another không tự có quyền truy cập api chỉ vì module library được resolve.
- Những module khác cần một thiết kế hợp đồng hoặc qualified export phù hợp.

Ở runtime, một class nằm trong module khác với tên dự kiến có thể gặp IllegalAccessError dù import giống nhau, vì qualified export nhắm tới module name cụ thể.

Chẩn đoán nên kiểm tra module name thực tế của caller. Tên file JAR, Maven artifactId và module name không nhất thiết trùng nhau.

Để kiểm tra thông tin module:

~~~bash
jar --describe-module --file libs/library.jar
~~~

Và:

~~~bash
java --describe-module com.example.library
~~~

Lệnh thứ hai cần module tương ứng được tìm thấy trong cấu hình lệnh chạy; với module trên đường dẫn bổ sung, cung cấp --module-path khi cần.

## 13. Dùng Module API để kiểm tra reads và exports

Một công cụ diagnostic có thể hỏi trực tiếp trạng thái runtime:

~~~java
public final class AccessReport {
    public static void show(Class<?> callerClass,
                            Class<?> targetClass) {
        Module caller = callerClass.getModule();
        Module owner = targetClass.getModule();

        String pkg = targetClass.getPackageName();

        System.out.println("Caller: " + caller.getName());
        System.out.println("Owner: " + owner.getName());

        System.out.println("Reads: "
                + caller.canRead(owner));
        System.out.println("Exported: "
                + owner.isExported(pkg, caller));
        System.out.println("Open: "
                + owner.isOpen(pkg, caller));
    }
}
~~~

Đây là API quan sát trạng thái, không sửa module graph.

Chiều gọi đúng là:

~~~java
caller.canRead(owner)
~~~

để hỏi caller có đọc owner không.

Và:

~~~java
owner.isExported(packageName, caller)
~~~

để hỏi package của owner có export cho caller không.

Nếu class mục tiêu không thể tham chiếu trực tiếp, bạn cần một con đường hợp lệ để lấy Class<?> trước khi kiểm tra, hoặc dùng descriptor/module tooling để quan sát cấu hình mà không cố liên kết kiểu không được phép.

## 14. Phân biệt ModuleDescriptor và trạng thái runtime

ModuleDescriptor lưu các chỉ thị mô-đun được công bố trong artifact:

~~~java
ModuleDescriptor descriptor =
        SomePublicApi.class.getModule().getDescriptor();
~~~

Có thể đọc:

~~~java
descriptor.requires();
descriptor.exports();
descriptor.opens();
~~~

Nhưng module graph runtime có thể chịu ảnh hưởng của các tùy chọn --add-reads/--add-exports và các API được phép thêm quan hệ.

Vì vậy:

- Descriptor cho biết hợp đồng và cấu hình tĩnh đã được khai báo.
- Module.canRead và Module.isExported phản ánh quan hệ hiệu lực của hai Module tại runtime.

Một báo cáo kỹ thuật có thể sử dụng cả hai. Nếu descriptor không có requires nhưng canRead trả true, có thể tồn tại quyền đọc được bổ sung hoặc quan hệ ngầm định phù hợp. Đừng xem đây là mâu thuẫn chắc chắn trước khi kiểm tra cách JVM khởi chạy.

## 15. Kiểm tra module graph khi khởi chạy

Một số lệnh JDK hữu ích:

~~~bash
java --list-modules
~~~

Liệt kê những module có thể quan sát trong cấu hình launcher.

~~~bash
java --module-path mods --list-modules
~~~

Cho biết những module được nhận diện trong module path hiện tại và các module hệ thống thích hợp.

~~~bash
java --show-module-resolution \
    --module-path mods \
    -m com.example.app/com.example.app.Main
~~~

Hiển thị quá trình resolve các module trước khi ứng dụng chạy. Đây là cách quan sát root module và dependency của module graph.

Để đọc module descriptor của JAR:

~~~bash
jar --describe-module --file libs/example.jar
~~~

Với named module có trong runtime configuration, có thể dùng:

~~~bash
java --module-path mods \
    --describe-module com.example.library
~~~

Những lệnh này giúp xác định module thực tế và quan hệ khai báo. Chúng không tự cấp quyền truy cập một package chưa export.

## 16. Khi build và runtime dùng module path khác nhau

Một dự án có thể compile với các JAR trong thư mục libs nhưng deploy một bộ artifact khác. Khi đó module name, descriptor hoặc version có thể không đồng nhất.

Ví dụ tình huống:

~~~text
Compile:
  com.example.library-1.0.jar
  - exports com.example.library.api

Runtime:
  com.example.library-2.0.jar
  - chỉ exports package khác
~~~

Consumer có thể được biên dịch dựa trên API của version cũ, nhưng JVM runtime kiểm tra module descriptor của version mới.

Cách xử lý:

1. Xác định chính xác version của JAR ở compile-time.
2. Ghi lại JAR được JVM tìm thấy trên module path runtime.
3. Đọc descriptor của cả hai artifact bằng jar --describe-module.
4. Kiểm tra API đã đổi package, đổi visibility hoặc bỏ export không.
5. Đồng bộ dependency management và artifact triển khai.
6. Chạy lại test modular với đúng cấu hình production.

Không sửa bằng một loạt --add-exports nếu nguyên nhân thật sự là một bản JAR không tương thích. Hãy đồng bộ dependency trước.

## 17. Lỗi do thay đổi quyền Java member cũng có thể là IllegalAccessError

IllegalAccessError không riêng JPMS. Ví dụ:

- Một public method ở version cũ bị đổi thành private ở version mới.
- Một public class bị giảm visibility.
- Một superclass/interface hoặc field bị thay đổi làm bytecode cũ tham chiếu không còn hợp lệ.

Giả sử consumer đã compile với:

~~~java
public class Feature {
    public void run() {
    }
}
~~~

Nhưng runtime cung cấp một version khác:

~~~java
public class Feature {
    private void run() {
    }
}
~~~

Bytecode consumer vẫn gọi run() theo giả định method public. JVM có thể phát sinh IllegalAccessError hoặc một linkage error liên quan khi xác minh/liên kết lời gọi.

Trong trường hợp này, thêm --add-reads hoặc --add-exports có thể không sửa được, vì vấn đề là mức truy cập của thành viên Java chứ không phải module graph.

Do đó, luôn đọc tên class/member và mô tả lỗi trong stacktrace trước khi chọn giải pháp.

## 18. Không nhầm với deep reflection

Với mã reflection:

~~~java
Field field = SomeType.class.getDeclaredField("secret");
field.setAccessible(true);
~~~

Nếu SomeType nằm trong named module khác và package chưa open cho caller, lỗi thường là InaccessibleObjectException.

Trường hợp này cần xem xét opens hoặc --add-opens, không phải --add-exports đơn thuần.

| Nhu cầu | Cơ chế thường liên quan |
| --- | --- |
| Gọi public method của class trong package export | requires/readability và exports. |
| Import class public từ package không export | exports hoặc --add-exports; kèm readability. |
| Gọi private method bằng reflection sâu | opens hoặc --add-opens cho caller. |
| Module chưa đọc module khác | requires hoặc --add-reads. |
| Class không có trong runtime | Kiểm tra module path/classpath và class loader. |

Đừng thêm --add-opens để sửa một IllegalAccessError chỉ rõ module không export package ở thao tác liên kết bình thường. Đọc loại truy cập thực tế trước khi chọn cờ.

## 19. Các module tự tạo trong ModuleLayer

Ứng dụng plugin có thể tạo ModuleLayer mới từ Configuration và ModuleFinder. Ở đây, module graph không nhất thiết giống boot layer của ứng dụng.

Một plugin có thể:

- Được resolve trong layer con nhưng thiếu readability tới module mà nó tham chiếu.
- Đọc module phù hợp nhưng package của module kia không export cho nó.
- Sử dụng bytecode được build trên cấu hình khác.
- Bị nạp bởi class loader khác, dẫn đến lỗi class identity hoặc lỗi liên kết.

Khi gặp IllegalAccessError trong plugin:

1. Xác định Class.getModule() của caller và target nếu có thể lấy được hợp lệ.
2. Kiểm tra Module.getLayer() và Module.getClassLoader().
3. Dùng caller.canRead(owner) để xem readability thực tế.
4. Dùng owner.isExported(packageName, caller) để xem export thực tế.
5. Xem ModuleDescriptor của hai module.
6. So sánh module graph của layer con và các layer cha.

Một class loader tìm thấy bytecode không có nghĩa JPMS cho phép liên kết mọi kiểu trong package chưa export.

## 20. Vai trò của --add-modules

Module trên module path có thể **observable** nhưng chưa **resolved** vào module graph. Nếu module mục tiêu chưa được đưa vào cấu hình, một --add-reads trỏ tới nó có thể không giải quyết được vấn đề.

Khi cần đưa module thành root bổ sung:

~~~bash
java --module-path mods \
    --add-modules com.example.library \
    -m com.example.app/com.example.app.Main
~~~

Trong ứng dụng modular bình thường, module app có requires com.example.library thì dependency này đã là một phần của quá trình phân giải theo chỉ thị requires.

--add-modules cần được dùng theo nhu cầu, chẳng hạn plugin/service provider hoặc dependency được chọn động. Nó không thay thế requires cho mọi tình huống và không tự export package.

Nếu lỗi gốc là java.lang.module.FindException, ưu tiên sửa module path hoặc tên module trước khi kiểm tra IllegalAccessError.

## 21. --add-exports cho ALL-UNNAMED

Khi ứng dụng chạy trên classpath, mã thuộc unnamed module. Nếu nó cần truy cập một package từ named module không được export thông thường, có thể dùng đích đặc biệt:

~~~bash
java --add-exports \
    com.example.library/com.example.library.internal=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

Ví dụ giả định module library được resolve vào cấu hình runtime và app.jar chứa main class trong classpath. Khi cần, thêm --module-path và --add-modules để đảm bảo library hiện diện trong graph.

ALL-UNNAMED có nghĩa export package cho các unnamed module thích hợp, phạm vi rộng hơn một named module cụ thể.

Nếu consumer có module name ổn định, ưu tiên:

~~~text
--add-exports com.example.library/com.example.library.internal=com.example.app
~~~

để không mở quyền cho nhiều unnamed module không liên quan.

## 22. Maven và Gradle: tách compiler arguments và JVM arguments

Một lỗi dễ gặp là thêm --add-exports vào compiler arguments rồi nghĩ rằng JVM runtime tự kế thừa.

Trong thực tế:

- javac nhận các tùy chọn khi biên dịch.
- java launcher nhận các tùy chọn lúc chạy.
- Test runner có thể khởi chạy một JVM khác với JVM của ứng dụng.
- IDE có thể bổ sung module flags riêng mà CLI không có.

Với Gradle Groovy DSL, cách cấu hình minh họa:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.library/com.example.library.internal=com.example.app'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-exports',
        'com.example.library/com.example.library.internal=com.example.app'
    )
}
~~~

Đây chỉ là ví dụ vị trí tham số. Nếu test runner chạy trong unnamed module, đích flag thực tế có thể khác; hãy xác định module caller của tiến trình test trước khi áp dụng.

Với Maven, compiler plugin và Surefire/Failsafe/runtime launcher dùng cấu hình riêng. Tránh đưa cờ chỉ phục vụ test vào production nếu production không cần.

Nếu có thể sửa source và descriptor, ưu tiên requires/exports hợp lý hơn các cờ tạm thời.

## 23. Cách đọc một stacktrace IllegalAccessError

Ví dụ:

~~~text
Exception in thread "main" java.lang.IllegalAccessError:
class com.example.app.Main (in module com.example.app)
cannot access class com.example.library.internal.InternalFormatter
(in module com.example.library)
because module com.example.library does not export
com.example.library.internal to module com.example.app
    at com.example.app/com.example.app.Main.main(Main.java:8)
~~~

Trích các thành phần:

| Dữ liệu | Ý nghĩa |
| --- | --- |
| com.example.app.Main | Class trong bytecode đang cố truy cập. |
| com.example.app | Module caller. |
| InternalFormatter | Class mục tiêu. |
| com.example.library | Module owner. |
| com.example.library.internal | Package cần export nhưng đang đóng. |
| Main.java:8 | Vị trí gọi trong mã nguồn để điều tra. |

Khi thông báo có cụm does not export, cần kiểm tra export thay vì thử opens.

Nếu thông báo có cụm does not read, cần kiểm tra readability và module graph. Nếu nói về private member hoặc protected member, cần kiểm tra Java visibility, chứ không phải mặc định giả định lỗi module.

## 24. Quy trình chẩn đoán ngắn và có thứ tự

Khi ứng dụng báo IllegalAccessError:

1. **Giữ nguyên thông báo gốc.** Ghi stacktrace đầy đủ, đặc biệt dòng class/module caller và owner.
2. **Phân loại.** Lỗi do does not export, does not read hay không liên quan module?
3. **Xác nhận module name.** Dùng jar --describe-module hoặc java --describe-module.
4. **Xác nhận runtime graph.** Kiểm tra lệnh java, --module-path, -m, --add-modules và --show-module-resolution.
5. **Kiểm tra descriptor.** Xem requires của caller, exports của owner, qualified exports và version artifact.
6. **Kiểm tra quyền hiệu lực.** Khi có Class<?> hợp lệ, gọi caller.canRead(owner) và owner.isExported(packageName, caller).
7. **Đối chiếu compile và runtime.** So sánh các cờ --add-reads, --add-exports và đường dẫn artifact của hai giai đoạn.
8. **Sửa đúng tầng.** Sử dụng requires, exports hoặc cờ bổ sung phù hợp với nguyên nhân.
9. **Giới hạn phạm vi.** Không mở package internal cho mọi module chỉ vì một consumer cần.
10. **Chạy lại trên môi trường triển khai thật.** Xác nhận lỗi liên kết biến mất mà không phát sinh dependency mismatch mới.

Không nên sửa hàng loạt cờ rồi thử lại ngẫu nhiên. Một thay đổi có mục tiêu và readback/log rõ ràng giúp phát hiện nguyên nhân thực sự.

## 25. Giải pháp thiết kế thay vì phụ thuộc flag

Nếu consumer phải dùng một class internal của library, hãy tự hỏi:

- Class đó có phải API chính thức dành cho consumer không?
- Có thể công khai một interface/factory trong package api thay thế không?
- Có thể trả về DTO hoặc record công khai thay vì kiểu internal không?
- Có thể thêm requires transitive khi public API cần type của một module dependency khác không?
- Có thể tách integration API ra package riêng với qualified exports không?

Ví dụ kiến trúc ổn định:

~~~text
com.example.library.api
    Formatter interface
    Formatters factory
    FormatResult DTO

com.example.library.internal
    DefaultFormatter
    Cache
    ParserHelper
~~~

Descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Consumer dùng API package thay vì import DefaultFormatter trong internal. Điều này giảm phụ thuộc vào implementation và tránh phải giữ --add-exports qua nhiều phiên bản.

Nếu gặp lỗi thiếu reads do module descriptor thiếu requires, hãy thêm requires rõ ràng thay vì dùng --add-reads như cấu hình bắt buộc vĩnh viễn, trừ khi kiến trúc có lý do đặc biệt.

## 26. Những sai lầm phổ biến

**Chỉ thêm requires khi lỗi là thiếu exports:** readability không làm package nội bộ thành public API.

**Chỉ thêm exports khi module caller không reads owner:** export không thay thế quan hệ đọc.

**Dùng --add-opens để sửa lỗi liên kết class public:** opens phục vụ deep reflection, không phải quyền import/bytecode access thông thường.

**Cho rằng public class trong internal package luôn truy cập được:** modifier public không vượt qua JPMS exports.

**Đổi classpath/module path mà không xem module name:** cùng artifact có thể chuyển giữa unnamed, automatic và explicit module tùy vị trí và descriptor.

**Thêm cờ ở compile rồi quên runtime:** đây là nguồn rất phổ biến của lỗi chỉ xuất hiện khi chạy.

**Bỏ qua binary incompatibility:** IllegalAccessError có thể do class/member thay đổi visibility, không chỉ do module graph.

**Đặt tất cả dependency ở --add-modules:** nó chỉ giải quyết một phần của resolution, không tự cấp mọi quan hệ reads và exports.

## 27. Nguyên tắc duy trì cấu hình rõ ràng

- Giữ module-info.java là nơi thể hiện dependency và API thực sự.
- Chỉ export package chứa những kiểu public được phép dùng lâu dài.
- Dùng qualified exports khi quyền chỉ dành cho một số module rõ ràng.
- Chỉ dùng --add-reads hoặc --add-exports khi cần tương thích, migration hoặc cấu hình test có kiểm soát.
- Ghi rõ mục đích, caller, owner, package và phiên bản JDK cho từng flag.
- Đảm bảo lệnh compile, test, IDE và runtime dùng cùng tập dependency thích hợp.
- Không nhầm exports với opens.
- Dùng Module API và công cụ JDK để quan sát thay vì đoán từ tên JAR.
- Luôn xét khả năng binary incompatibility khi thay dependency.
- Kiểm thử trên đúng module path/runtime sẽ được triển khai.

IllegalAccessError do thiếu exports hoặc reads là dấu hiệu rằng **bytecode đang yêu cầu một quan hệ truy cập mà module graph runtime không cho phép**. Phân biệt rõ quan hệ đọc module và quyền export package giúp sửa đúng nguyên nhân, giữ strong encapsulation và tránh tạo những đường phụ thuộc khó bảo trì.

## 28. Tự kiểm tra

**Tình huống 1:** App khai báo requires library nhưng gọi public class trong package internal không export. Có đủ quyền truy cập không?

Không. requires chỉ cấp readability; library còn phải export package cho app nếu đây là truy cập thông thường.

**Tình huống 2:** Javac được truyền --add-exports, nhưng JVM runtime không được truyền cờ. Điều gì có thể xảy ra?

Ứng dụng có thể biên dịch thành công nhưng JVM ném IllegalAccessError khi liên kết tham chiếu class trong package không được export ở runtime.

**Tình huống 3:** JVM báo module app does not read module library. Dùng --add-exports có tự khắc phục không?

Không. Cần readability qua requires, requires transitive hoặc --add-reads phù hợp. Nếu package cũng chưa export thì phải xử lý điều kiện đó riêng.

**Tình huống 4:** Qualified exports khai báo exports p to app, nhưng module tool khác cần sử dụng p. Tool có tự truy cập được không?

Không. Export có đích chỉ cấp cho các module được chỉ định; tool cần một hợp đồng export riêng hoặc một API công khai thích hợp.

**Tình huống 5:** Khi reflection vào private field bị InaccessibleObjectException, có nên thêm --add-reads thay vì --add-opens?

Không. Đây thường là lỗi deep reflection; cần xem xét opens cho đúng package/caller nếu nhu cầu chức năng chính đáng.

**Tình huống 6:** Nếu chạy ứng dụng với JAR library khác version so với compile, nên kiểm tra gì trước khi thêm cờ?

Đối chiếu module descriptor, exports, visibility, version của API và artifact thật sự nằm trên module path. Có thể vấn đề là binary incompatibility.

**Tình huống 7:** Class thuộc unnamed module của classpath; named module cần đọc nó. Dạng đích nào của --add-reads có thể hữu ích trong một số cấu hình migration?

Có thể dùng --add-reads named.module=ALL-UNNAMED, đồng thời bảo đảm classpath chứa thư viện và class loader có thể tìm thấy lớp.

**Tình huống 8:** Một lớp được class loader nạp thành công có bảo đảm mọi module có thể sử dụng nó không?

Không. Khả năng nạp bytecode và quyền liên kết/truy cập class theo JPMS là hai điều khác nhau. JVM vẫn kiểm tra readability, exports và Java visibility.
