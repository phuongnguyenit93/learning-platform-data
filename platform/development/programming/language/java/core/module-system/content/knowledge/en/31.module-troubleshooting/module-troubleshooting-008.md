# NoSuchMethodError sau khi module version không khớp

Trong ứng dụng Java modular, một module có thể resolve thành công nhưng ứng dụng vẫn gặp lỗi khi gọi method lúc runtime. Một nguyên nhân thường gặp là consumer được biên dịch với một phiên bản API, trong khi runtime lại nạp một phiên bản module khác không còn method mà bytecode đang yêu cầu.

Lỗi thường thấy là:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.library.api.GreetingApi.greet(java.lang.String)'
~~~

Đây là lỗi liên kết nhị phân (binary linkage). JVM đã tìm thấy class nhưng không tìm được method có tên và descriptor mà bytecode gọi tới. JPMS quản lý module resolution, readability và quyền truy cập package; nó không tự kiểm tra semantic version compatibility giữa phiên bản thư viện lúc biên dịch và lúc chạy.

## 1. NoSuchMethodError xảy ra khi nào?

NoSuchMethodError là một lớp con của IncompatibleClassChangeError và LinkageError. Nó xuất hiện khi bytecode yêu cầu một method nhưng JVM không thể tìm thấy method tương ứng trong class hoặc interface được nạp.

Ví dụ, consumer được biên dịch với API:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Bytecode của consumer chứa lời gọi tới method có tên greet và descriptor tương ứng với tham số String, kiểu trả về String.

Nhưng runtime lại nạp một phiên bản cũ:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet() {
        return "Hello";
    }
}
~~~

Phiên bản runtime không có greet(String). Khi consumer thực hiện lời gọi đã được biên dịch, JVM không thể liên kết method và ném NoSuchMethodError.

Điểm quan trọng:

- Class có thể tồn tại và được nạp thành công.
- Module có thể resolve thành công.
- Module consumer có thể đọc module library.
- Package API có thể được export đúng.
- Nhưng method descriptor được bytecode yêu cầu vẫn có thể không tồn tại trong class runtime.

Vì vậy, lỗi này thường chỉ xuất hiện khi code đi tới call site bị ảnh hưởng, thay vì ngay tại bước khởi động JVM.

## 2. Vì sao module version không tự ngăn lỗi?

Module descriptor có thể chứa version metadata. Khi đóng gói module, công cụ JAR cho phép ghi version bằng tùy chọn --module-version. Runtime có thể đọc metadata này qua ModuleDescriptor.version().

Tuy nhiên, khai báo dependency trong module-info.java chỉ nêu tên module:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

Khai báo trên yêu cầu module có tên com.example.library. Nó không biểu diễn một version range như >= 2.0 và < 3.0, cũng không cam kết rằng method nào đó sẽ tồn tại.

JPMS thực hiện các nhiệm vụ chính:

- Tìm module observable trên các nguồn module đã cấu hình.
- Resolve module graph dựa trên tên module và các quan hệ requires.
- Xác định readability giữa các module.
- Áp dụng exports, opens và các quy tắc truy cập.

JPMS không phải dependency version manager. Module version là metadata mô tả phiên bản; bản thân metadata đó không tạo ra chính sách tương thích API.

Do đó, ứng dụng có thể được biên dịch với com.example.library phiên bản 2.0 nhưng khi chạy lại nạp module cùng tên phiên bản 1.0. Nếu phiên bản 1.0 thiếu method mà consumer cần, lỗi linkage có thể xảy ra.

## 3. Ví dụ tái hiện lỗi giữa hai phiên bản module

Ta tạo một thư viện có hai phiên bản. Cả hai dùng cùng tên module là com.example.library.

### Phiên bản 1.0

File module-info.java:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

File GreetingApi.java:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet() {
        return "Hello";
    }
}
~~~

Phiên bản 1.0 chỉ có method greet() không nhận tham số.

### Phiên bản 2.0

Module descriptor giữ cùng tên và package được export:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

GreetingApi.java của phiên bản 2.0:

~~~java
package com.example.library.api;

public class GreetingApi {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Phiên bản 2.0 cung cấp greet(String), là method mà consumer mới sẽ sử dụng.

### Module consumer

File module-info.java:

~~~java
module com.example.app {
    requires com.example.library;
}
~~~

File Main.java:

~~~java
package com.example.app;

import com.example.library.api.GreetingApi;

public class Main {

    public static void main(String[] args) {
        GreetingApi api = new GreetingApi();
        System.out.println(api.greet("Ada"));
    }
}
~~~

Consumer được biên dịch với module library phiên bản 2.0:

~~~shell
javac --module-path artifacts/com.example.library-2.0.jar -d build/app src/app/module-info.java src/app/com/example/app/Main.java
~~~

Sau khi biên dịch, bytecode của Main chứa lời gọi tới greet(String).

### Chạy nhầm phiên bản 1.0

Giả sử runtime được cấu hình với library phiên bản 1.0:

~~~shell
java --module-path "build/app;artifacts/com.example.library-1.0.jar" --module com.example.app/com.example.app.Main
~~~

Trên Windows, dấu chấm phẩy phân cách các phần tử module path. Trên Linux hoặc macOS, thay dấu chấm phẩy bằng dấu hai chấm:

~~~shell
java --module-path "build/app:artifacts/com.example.library-1.0.jar" --module com.example.app/com.example.app.Main
~~~

Kết quả sẽ có dạng:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.library.api.GreetingApi.greet(java.lang.String)'
    at com.example.app/com.example.app.Main.main(Main.java:...)
~~~

Module com.example.library phiên bản 1.0 vẫn có đúng tên mà app yêu cầu. Vì thế module resolution có thể thành công. Nhưng class GreetingApi của phiên bản 1.0 không chứa greet(String), nên lời gọi trong bytecode thất bại.

Đây là ví dụ điển hình của việc module name khớp nhưng binary API không tương thích.

## 4. Phân biệt lỗi module resolution và lỗi linkage

Hai lỗi có thể xuất hiện trong cùng một ứng dụng nhưng xảy ra ở các giai đoạn khác nhau.

| Tình huống | Giai đoạn | Dấu hiệu thường gặp |
| --- | --- | --- |
| Không tìm thấy module được yêu cầu | Module resolution | FindException hoặc lỗi module not found |
| Module không đọc được module khác | Kiểm tra readability / truy cập | Compilation error hoặc lỗi truy cập tương ứng |
| Package không được export | Truy cập API giữa module | Compilation error hoặc lỗi truy cập lúc runtime |
| Package không mở cho deep reflection | Reflection | InaccessibleObjectException hoặc trySetAccessible() trả về false |
| Method không tồn tại trong class runtime | Binary linkage | NoSuchMethodError |

NoSuchMethodError không có nghĩa là module path sai trong mọi trường hợp. Module path có thể tìm đúng một module cùng tên, nhưng artifact được nạp lại không tương thích với consumer.

Cũng cần phân biệt NoSuchMethodError với một số lỗi linkage khác:

- NoClassDefFoundError: class cần thiết không thể được tìm thấy hoặc khởi tạo theo tình huống tương ứng.
- NoSuchFieldError: field mà bytecode yêu cầu không tồn tại.
- IllegalAccessError: member tồn tại nhưng truy cập vi phạm quy tắc access.
- AbstractMethodError: lời gọi cần implementation cụ thể nhưng class runtime không cung cấp implementation phù hợp.
- IncompatibleClassChangeError: cấu trúc hoặc cách sử dụng class đã thay đổi theo hướng không tương thích, ví dụ một số trường hợp thay đổi static/instance.

Đừng sửa exports hoặc opens chỉ vì thấy một lỗi liên quan đến module. Những tùy chọn đó không thể tạo lại method đã bị xóa hoặc thay đổi descriptor.

## 5. Kiểm tra module và artifact thực tế đang được nạp

Khi gặp lỗi, hãy xác định class runtime đến từ đâu. Đừng chỉ dựa vào version trong file build hoặc tên file JAR.

### Kiểm tra module của class

Với một class thuộc named module:

~~~java
import java.lang.module.ModuleDescriptor;

public class ModuleDiagnostics {

    public static void print(Class<?> type) {
        Module module = type.getModule();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());

        ModuleDescriptor descriptor = module.getDescriptor();

        if (descriptor != null) {
            System.out.println(
                "Module version: "
                    + descriptor.version()
                        .map(Object::toString)
                        .orElse("<not recorded>")
            );
        }

        ModuleLayer layer = module.getLayer();

        if (layer != null) {
            layer.configuration()
                .findModule(module.getName())
                .ifPresent(resolved -> System.out.println(
                    "Module location: "
                        + resolved.reference().location()
                            .map(Object::toString)
                            .orElse("<unknown>")
                ));
        }

        var codeSource = type.getProtectionDomain().getCodeSource();

        System.out.println(
            "Class code source: "
                + (codeSource == null
                    ? "<unknown>"
                    : codeSource.getLocation())
        );
    }
}
~~~

Gọi phương thức chẩn đoán với class thực sự gây lỗi:

~~~java
ModuleDiagnostics.print(GreetingApi.class);
~~~

Thông tin này giúp xác định:

- Tên module mà class thuộc về.
- Version metadata nếu module có ghi nhận.
- Module layer đang chứa module.
- Vị trí module reference trong configuration.
- Code source của class nếu class loader cung cấp thông tin này.

Với unnamed module, Module.getDescriptor() trả về null và module không có tên. Trong ứng dụng có custom class loader hoặc custom ModuleLayer, hãy kiểm tra đúng class được sử dụng tại call site.

### Kiểm tra module resolution lúc khởi động

Có thể thêm tùy chọn:

~~~shell
java --show-module-resolution --module-path mods --module com.example.app/com.example.app.Main
~~~

Tùy chọn này hiển thị thông tin về quá trình resolve module. Nó hữu ích để xem module nào được đưa vào graph và dependency nào được tìm thấy.

Tuy nhiên, output resolution không chứng minh mọi method của phiên bản API mà consumer cần đều tồn tại. Vẫn phải kiểm tra artifact và binary signature.

### Kiểm tra descriptor của JAR

Dùng công cụ jar:

~~~shell
jar --describe-module --file artifacts/com.example.library-1.0.jar
jar --describe-module --file artifacts/com.example.library-2.0.jar
~~~

So sánh tên module, package được export và version metadata. Nếu hai JAR có cùng module name nhưng khác version, hãy kiểm tra xem runtime thực sự đang chọn artifact nào.

## 6. So sánh method descriptor ở compile time và runtime

JVM liên kết method dựa trên thông tin nhị phân, bao gồm tên method và descriptor. Descriptor thể hiện kiểu tham số và kiểu trả về.

Dùng javap để xem class trong từng JAR:

~~~shell
javap -classpath artifacts/com.example.library-1.0.jar -p -s com.example.library.api.GreetingApi

javap -classpath artifacts/com.example.library-2.0.jar -p -s com.example.library.api.GreetingApi
~~~

Kết quả của phiên bản 1.0 có thể cho thấy:

~~~text
public java.lang.String greet();
  descriptor: ()Ljava/lang/String;
~~~

Phiên bản 2.0:

~~~text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
~~~

Hai descriptor khác nhau. Một lời gọi tới greet(String) không thể được liên kết với greet().

Có thể kiểm tra cả bytecode của consumer:

~~~shell
javap -classpath build/app -c -s com.example.app.Main
~~~

Tìm lệnh invokevirtual hoặc invokeinterface liên quan tới GreetingApi.greet. Phần constant pool và descriptor cho biết bytecode đang yêu cầu method nào.

Nếu consumer được biên dịch với API phiên bản 2.0, nhưng class runtime chỉ có method của phiên bản 1.0, nguyên nhân đã được xác định.

## 7. Những nguyên nhân thường gặp trong dự án thực tế

**Compile-time và runtime dependency khác nhau.** Gradle hoặc Maven chọn một artifact khi biên dịch nhưng runtime packaging lại chứa phiên bản khác. Kiểm tra cả compile classpath và runtime classpath.

**JAR cũ còn sót trong thư mục triển khai.** Ứng dụng được build lại nhưng container, thư mục libs, application server hoặc thư mục deploy vẫn giữ artifact cũ.

**Dependency bắc cầu chọn phiên bản ngoài dự kiến.** Một thư viện khác kéo theo phiên bản library cũ hơn. Build tool có thể giải quyết xung đột theo quy tắc riêng; cần xem dependency graph thực tế.

**Nhiều module hoặc class loader.** Một ứng dụng có thể dùng boot layer, custom ModuleLayer, plugin class loader hoặc classpath bổ sung. Class được nạp tại call site có thể đến từ artifact khác với artifact mà người vận hành đang kiểm tra.

**Module patch hoặc upgrade path.** Các tùy chọn như --patch-module và --upgrade-module-path có thể thay đổi nội dung hoặc nguồn module runtime. Cần đưa chúng vào quá trình kiểm tra nếu ứng dụng có sử dụng.

**API thay đổi không tương thích.** Method bị xóa, đổi tên, đổi kiểu tham số hoặc đổi kiểu trả về. Consumer vẫn giữ bytecode cũ và gọi method không còn tồn tại.

**Đóng gói sai dependency.** Build tạo một JAR đúng nhưng thư mục phân phối, image container hoặc script khởi chạy lại tham chiếu đến một file JAR khác.

## 8. Quy trình xử lý theo thứ tự

Khi gặp NoSuchMethodError sau khi nâng version module, hãy thực hiện theo trình tự sau:

1. Đọc đầy đủ stack trace để xác định class và call site phát sinh lỗi.
2. Xác định method name và descriptor trong thông báo lỗi.
3. Kiểm tra compile-time dependency mà consumer đã sử dụng.
4. Kiểm tra runtime classpath và module path thực tế trong lệnh khởi chạy hoặc môi trường triển khai.
5. In module name, module version và code source của class runtime.
6. Dùng jar --describe-module để so sánh module descriptor.
7. Dùng javap -p -s để so sánh method signature giữa artifact compile-time và runtime.
8. Kiểm tra dependency tree để tìm phiên bản bị kéo theo hoặc bị override.
9. Kiểm tra custom layer, class loader, --patch-module và --upgrade-module-path nếu ứng dụng có dùng.
10. Sau khi xác định đúng artifact, đồng bộ dependency và build lại consumer nếu API chủ đích đã thay đổi.

### Gradle

Xem dependency tree của runtime classpath:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một dependency cụ thể được chọn:

~~~shell
./gradlew dependencyInsight --dependency com.example.library --configuration runtimeClasspath
~~~

Kiểm tra compile classpath tương ứng:

~~~shell
./gradlew dependencies --configuration compileClasspath
~~~

So sánh kết quả để xác định phiên bản build đang biên dịch và phiên bản được đưa vào runtime.

### Maven

Xem dependency tree:

~~~shell
mvn dependency:tree -Dincludes=com.example:library
~~~

Kiểm tra dependency mediation, dependency được khai báo trực tiếp và dependency bắc cầu.

### Đồng bộ artifact

Sau khi xác định nguyên nhân:

- Khóa hoặc quản lý version dependency tập trung để compile và runtime dùng cùng phiên bản mong muốn.
- Loại bỏ JAR cũ khỏi thư mục deploy hoặc image container.
- Kiểm tra script khởi chạy và biến môi trường có bổ sung module path khác hay không.
- Clean và build lại consumer khi API đã thay đổi có chủ đích.
- Triển khai đồng bộ các module liên quan, tránh trộn artifact của nhiều lần build.
- Nếu cần giữ tương thích, phát hành lại library với method cũ hoặc cung cấp migration path phù hợp.

## 9. Cách phòng tránh trong quá trình phát triển module

**Giữ binary compatibility cho public API.** Tránh xóa hoặc đổi descriptor của method đã công khai trong một minor release nếu dự án cam kết tương thích nhị phân.

**Quản lý version nhất quán.** Dùng dependency constraints, version catalog, platform/BOM hoặc dependency locking phù hợp với build tool. Module name trong JPMS không thay thế việc quản lý version của artifact.

**Kiểm thử trên artifact đã đóng gói.** Kiểm tra JAR, runtime image hoặc container thực tế thay vì chỉ chạy bằng classpath của IDE.

**Có kiểm thử tương thích.** Chạy consumer đã biên dịch với phiên bản API trước trên library mới nếu dự án yêu cầu binary compatibility. Có thể bổ sung API compatibility checker trong CI.

**Tránh nhiều nguồn class không rõ ràng.** Kiểm soát module path, classpath, custom class loader và module layer. Ghi lại nguồn artifact khi cần chẩn đoán.

**Công bố thay đổi API có lộ trình.** Nếu method cần bị loại bỏ hoặc đổi chữ ký, đánh dấu deprecated trước, cung cấp method thay thế và hướng dẫn migration. Thay đổi phá vỡ tương thích nên được quản lý theo versioning policy của thư viện.

## 10. Những nhầm lẫn cần tránh

1. **Tên module giống nhau nghĩa là API tương thích:** tên module chỉ xác định module dependency; nó không bảo đảm method signature giống nhau.
2. **Module version tự động được JPMS kiểm tra:** version metadata không phải version range và không tự ngăn runtime resolve phiên bản không tương thích.
3. **Module đã resolve thì không thể có linkage error:** resolution không xác minh mọi method mà consumer đã biên dịch sẽ tồn tại.
4. **NoSuchMethodError luôn do exports:** exports quyết định quyền truy cập package, không tạo method bị thiếu.
5. **Thêm --add-reads sẽ sửa method bị thiếu:** readability không sửa bytecode hoặc class definition.
6. **Clean build luôn đủ:** nếu runtime vẫn nạp JAR cũ từ thư mục deploy hoặc container, lỗi vẫn tiếp tục.
7. **Chỉ nhìn tên file JAR để biết version đang chạy:** hãy kiểm tra class code source, module descriptor và module configuration thực tế.

## Kết luận

NoSuchMethodError trong ứng dụng JPMS thường cho thấy consumer và class runtime không thống nhất về binary API. Module resolution có thể thành công vì module name vẫn khớp, trong khi method mà bytecode yêu cầu đã bị xóa hoặc thay đổi descriptor. Hãy xác định class runtime thực sự được nạp, so sánh method descriptor bằng javap, kiểm tra dependency graph và đồng bộ artifact compile-time với runtime. JPMS bảo vệ module boundary; quản lý version và tương thích API vẫn là trách nhiệm của quy trình build và phát hành.
