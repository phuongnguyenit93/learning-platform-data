# JPMS: Phân biệt tìm descriptor với định nghĩa class

Trong Java Platform Module System (JPMS), **tìm được module descriptor** chỉ có nghĩa là hệ thống đã tìm được thông tin mô tả một module. Điều đó **không đồng nghĩa** với việc JVM đã tìm, nạp hoặc định nghĩa bất kỳ class cụ thể nào trong module ấy. Đây là ranh giới quan trọng khi đọc luồng **module resolution** và khi chẩn đoán lỗi ở thời điểm chạy.

## 1. Hai câu hỏi hoàn toàn khác nhau

**Câu hỏi A — “Module này có descriptor không?”**

JPMS dùng các module finder để khám phá module có thể quan sát được. Từ một tên module, phương thức **ModuleFinder.find(String)** có thể trả về **ModuleReference**; từ reference đó có thể lấy **ModuleDescriptor**. Descriptor mô tả tên module, phụ thuộc requires, các package exports/opens, uses/provides, version và những thuộc tính khác.

Đây là thao tác ở **mức module và metadata**. Nó không yêu cầu tạo ra đối tượng **Class<?>**, không thực thi static initializer và không chứng minh rằng một tên class tùy ý có mặt.

**Câu hỏi B — “JVM đã định nghĩa class này chưa, hoặc có thể nạp nó không?”**

Ở mức class, JVM phối hợp với **ClassLoader** để tìm bytecode, kiểm tra định dạng, định nghĩa class và thực hiện các bước liên kết/khởi tạo khi được yêu cầu. Kết quả là đối tượng **Class<?>** gắn với một class loader và một module cụ thể. Một descriptor hợp lệ không bảo đảm rằng mọi class được chương trình nhắc đến sẽ nạp thành công.

Ví dụ: module **demo.catalog** có descriptor và export package **demo.catalog.api**; lời gọi nạp **demo.catalog.api.Missing** vẫn có thể thất bại vì file class không tồn tại.

## 2. Các khái niệm và API cần phân biệt

| Thành phần | Trả lời câu hỏi gì? | Kết quả điển hình | Có định nghĩa class không? |
|---|---|---|---|
| **ModuleFinder** | Có thể tìm module tên X từ nguồn đang xét không? | **Optional<ModuleReference>** | Không |
| **ModuleReference** | Module tìm được nằm ở nguồn nào, có descriptor nào? | Descriptor, location (nếu có), **ModuleReader** | Không |
| **ModuleDescriptor** | Module khai báo tên, requires, exports, opens, uses, provides, packages ra sao? | Metadata bất biến | Không |
| **Configuration** | Có thể giải quyết đồ thị phụ thuộc module theo các finder đã cho không? | Tập module đã resolve và các quan hệ readability | Không |
| **ModuleLayer** | Những module nào đã được định nghĩa vào một layer? | Các đối tượng **Module** và ánh xạ sang class loader | Không tự nạp tất cả class |
| **ClassLoader / JVM** | Có thể nạp, định nghĩa và liên kết class có tên xác định không? | **Class<?>** hoặc lỗi khi nạp/liên kết | Có, khi thực sự nạp |
| **Class.forName(Module, String)** | Có class tên Y được nạp từ module X không? | **Class<?>** hoặc **null** nếu không tìm được trong module đó | Có thể kích hoạt nạp class; không khởi tạo class |

Lưu ý: **exports** là quy tắc truy cập package cho module khác; **opens** phục vụ truy cập phản chiếu sâu. Cả hai đều không phải danh sách class. **ModuleDescriptor.packages()** là tập tên package, không phải danh mục đầy đủ các class thuộc package.

## 3. Vị trí của từng bước trong module resolution

Luồng khái quát của một ứng dụng modular:

~~~text
Nguồn module: runtime image, module path, ModuleFinder tùy biến
    |
    v
ModuleFinder.find("demo.catalog")
    |
    v
ModuleReference -> ModuleDescriptor
    |
    v
Configuration.resolve(...) / resolveAndBind(...)
    |  Kiểm tra các module cần thiết và quan hệ phụ thuộc
    v
ModuleLayer được tạo hoặc boot layer đã được JVM thiết lập
    |  Liên kết module với class loader tương ứng
    v
Mã chương trình tham chiếu một class hoặc yêu cầu nạp class
    |
    v
ClassLoader / JVM tìm bytecode, define class, link, initialize khi cần
~~~

Các điểm cần nhớ:

1. **Discovery**: ModuleFinder tìm một module có thể quan sát được từ nguồn được cấu hình. Nó có thể thấy một module mà ứng dụng hiện tại chưa resolve.
2. **Resolution**: bộ giải quyết dựa trên descriptor để tạo đồ thị module, xử lý requires và những ràng buộc ở mức module. Tìm được descriptor là điều kiện đầu vào, nhưng chưa đủ để khẳng định resolve thành công.
3. **Layer definition**: một configuration được dùng để định nghĩa module trong layer, lựa chọn class loader và thiết lập quan hệ module.
4. **Class loading**: class cụ thể thường chỉ được JVM nạp theo nhu cầu. Không có quy tắc rằng resolve xong module phải nạp toàn bộ class của module.
5. **Initialization**: kể cả sau khi class đã được nạp/định nghĩa, static initializer có thể vẫn chưa chạy. Khởi tạo là một thời điểm khác với việc tìm descriptor.

**ModuleFinder.ofSystem()** quan sát các module trong runtime image; **ModuleFinder.of(Path...)** quan sát module trên các đường dẫn được cung cấp. Việc finder tìm được tên module không chứng minh module đó nằm trong **ModuleLayer.boot()**.

## 4. Ví dụ Java có thể chạy

Ví dụ gồm hai module. Module thư viện có class **Widget** nhưng không có class **Missing**; module ứng dụng bắt buộc phụ thuộc vào thư viện.

Cấu trúc thư mục:

~~~text
src/
  demo.catalog/
    module-info.java
    demo/catalog/api/Widget.java
  demo.app/
    module-info.java
    demo/app/Main.java
~~~

**src/demo.catalog/module-info.java**

~~~java
module demo.catalog {
    exports demo.catalog.api;
}
~~~

**src/demo.catalog/demo/catalog/api/Widget.java**

~~~java
package demo.catalog.api;

public class Widget {
    public static String label() {
        return "JPMS";
    }
}
~~~

**src/demo.app/module-info.java**

~~~java
module demo.app {
    requires demo.catalog;
}
~~~

**src/demo.app/demo/app/Main.java**

~~~java
package demo.app;

import java.lang.module.ModuleDescriptor;
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class Main {
    public static void main(String[] args) {
        // (1) Tìm metadata ở đường dẫn chứa các module đã biên dịch.
        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        ModuleReference reference =
                finder.find("demo.catalog").orElseThrow();
        ModuleDescriptor descriptor = reference.descriptor();

        System.out.println("Finder thấy: " + descriptor.name());
        System.out.println("Package có trong descriptor: "
                + descriptor.packages().contains("demo.catalog.api"));

        // (2) Ứng dụng cần demo.catalog nên module có trong boot layer.
        Module catalog = ModuleLayer.boot()
                .findModule("demo.catalog").orElseThrow();
        System.out.println("Layer có: " + catalog.getName());

        // (3) Kiểm tra hai tên class bên trong cùng một module.
        Class<?> existing =
                Class.forName(catalog, "demo.catalog.api.Widget");
        Class<?> absent =
                Class.forName(catalog, "demo.catalog.api.Missing");

        System.out.println("Widget nạp được: " + (existing != null));
        System.out.println("Missing nạp được: " + (absent != null));
        System.out.println("Module sở hữu Widget: "
                + existing.getModule().getName());
    }
}
~~~

Từ thư mục chứa **src**, biên dịch và chạy với JDK 9 trở lên:

~~~sh
javac --module-source-path src -d mods -m demo.catalog,demo.app
java --module-path mods -m demo.app/demo.app.Main
~~~

Kết quả dự kiến:

~~~text
Finder thấy: demo.catalog
Package có trong descriptor: true
Layer có: demo.catalog
Widget nạp được: true
Missing nạp được: false
Module sở hữu Widget: demo.catalog
~~~

**Giải thích:** ModuleFinder tìm được descriptor **demo.catalog**. Configuration đã resolve module vì **demo.app requires demo.catalog**. Khi chương trình yêu cầu nạp **Widget**, JVM tìm được class. Với **Missing**, **Class.forName(Module, String)** trả về **null**; descriptor vẫn tồn tại và graph resolution vẫn hợp lệ.

Nếu xóa class **Widget** và sửa mã Main để không phụ thuộc trực tiếp vào class đó tại biên dịch, metadata của module vẫn có thể được tìm thấy; nhưng lúc chạy, yêu cầu nạp tên Widget sẽ không thành công. Ngược lại, một class có file bytecode trên đĩa cũng không mặc nhiên truy cập được từ mọi module.

## 5. Descriptor còn khác với kiểm tra tài nguyên .class

Từ **ModuleReference**, API **ModuleReader** cho phép kiểm tra tài nguyên của một module:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.lang.module.ModuleReader;
import java.nio.file.Path;

ModuleReference ref = ModuleFinder.of(Path.of("mods"))
        .find("demo.catalog").orElseThrow();

try (ModuleReader reader = ref.open()) {
    boolean hasBytes = reader
            .find("demo/catalog/api/Widget.class")
            .isPresent();
    System.out.println("Có resource Widget.class: " + hasBytes);
}
~~~

Ba mức chứng cứ cần tách rõ:

- **Tìm được ModuleDescriptor**: có metadata mô tả module.
- **Tìm được resource Widget.class**: nguồn module cung cấp một resource với đường dẫn tương ứng; bước này chưa chứng minh nội dung bytecode hợp lệ hoặc class đã được định nghĩa.
- **Có được Class<?>**: runtime đã nạp class qua cơ chế class loading; việc dùng class vẫn có thể phát sinh lỗi liên kết, truy cập hoặc khởi tạo tùy thời điểm.

Không nên dùng **descriptor.packages().contains("demo.catalog.api")** làm phép thử sự tồn tại của **demo.catalog.api.Widget**. Nó chỉ kiểm tra tên package.

## 6. Vì sao “descriptor tìm được” nhưng “class không nạp được”?

| Hiện tượng | Nguyên nhân có thể | Cách phân tích |
|---|---|---|
| Finder có ModuleReference, layer không có module | Module được quan sát nhưng không nằm trong đồ thị đã resolve/layer đang xét | Phân biệt tập observable modules với tập resolved modules |
| Descriptor có exports của package, tên class không có | Module không đóng gói class đó, tên sai hoặc class nằm ở nơi khác | Kiểm tra tên fully qualified và nội dung module |
| Resource .class có mặt, nạp class lỗi | Bytecode lỗi, phụ thuộc lúc liên kết thiếu, hoặc vấn đề loader | Xem loại exception/error và chuỗi nguyên nhân |
| Class có mặt nhưng code từ module khác không truy cập được | Thiếu exports, readability hoặc điều kiện truy cập Java | Kiểm tra requires/exports/opens và mức truy cập |
| Module đúng tên nhưng class được định nghĩa bởi module/loader khác | Dùng sai loader, sai layer hoặc môi trường có nhiều bản phân phối | Kiểm tra **clazz.getModule()** và **clazz.getClassLoader()** |
| Class nạp được nhưng lỗi khi dùng lần đầu | Lỗi khởi tạo hoặc lỗi phát sinh khi liên kết/thực thi | Phân biệt class loading, linking và initialization |

Một số loại lỗi thường gặp ở những giai đoạn khác nhau:

- **FindException** hoặc **ResolutionException**: lỗi liên quan đến tìm hoặc giải quyết cấu hình module; tùy trường hợp có thể xảy ra trước khi chạy mã ứng dụng.
- **ClassNotFoundException**: thường gặp với **Class.forName(String)** hoặc thao tác nạp class theo tên thông qua class loader.
- **NoClassDefFoundError**: runtime cần một định nghĩa class nhưng không thể tìm/hoàn tất định nghĩa đó (hoặc class trước đó không khởi tạo thành công).
- **IllegalAccessError** và những lỗi liên kết khác: class tồn tại nhưng quy tắc truy cập hoặc liên kết không thỏa mãn.
- **ExceptionInInitializerError**: lỗi xảy ra trong quá trình khởi tạo class; không phải là kết quả của việc đọc descriptor.

Đừng đánh đồng hai overload **Class.forName**:

~~~java
Class<?> a = Class.forName("demo.catalog.api.Widget");
// Tìm theo loader của caller và mặc định khởi tạo class nếu thành công.

Module module = ModuleLayer.boot()
        .findModule("demo.catalog").orElseThrow();
Class<?> b = Class.forName(module, "demo.catalog.api.Widget");
// Tìm class trong module đã chỉ định; không khởi tạo class.
// Trả về null nếu không tìm được class trong module đó.
~~~

Việc tìm class theo module không tự động chứng minh caller được phép truy cập mọi thành viên của class đó. Quy tắc access của Java và JPMS vẫn được áp dụng khi sử dụng class.

## 7. Cách tự kiểm tra khi chẩn đoán module

Trước tiên xác định đang thất bại ở cấp nào:

1. **Quan sát module**: dùng ModuleFinder phù hợp và kiểm tra **find(name)**; với JAR modular có thể dùng **jar --describe-module --file path/to/library.jar** để đọc descriptor.
2. **Resolve module**: chạy ứng dụng với **--show-module-resolution** để quan sát đồ thị module được giải quyết. Kiểm tra requires, tên module trên module path và layer thực tế.
3. **Tìm class/resource**: kiểm tra đúng đường dẫn class trong artifact, đúng package và đúng tên fully qualified; nếu phù hợp, thử ModuleReader.
4. **Nạp class**: dùng **Class.forName(module, fqcn)** khi đã có đối tượng Module đích và cần biết class có nạp được từ chính module đó không. Nếu thành công, kiểm tra **getModule()** và **getClassLoader()**.
5. **Truy cập/khởi tạo**: nếu class đã nạp nhưng chương trình vẫn lỗi, xem yêu cầu readability/exports/opens, kiểm tra lỗi liên kết và static initializer.

Lệnh quan sát resolution của ví dụ:

~~~sh
java --show-module-resolution --module-path mods -m demo.app/demo.app.Main
~~~

Những phép kiểm tra này trả lời các câu hỏi ở **các tầng khác nhau**; không thay phép kiểm tra class bằng phép kiểm tra descriptor.

## 8. Kết luận cần ghi nhớ

**Module resolution giải quyết đồ thị module dựa trên descriptor; class loading định nghĩa class cụ thể khi runtime cần.** Descriptor xác nhận thông tin của module, không phải bảo đảm rằng một tên class tồn tại, truy cập được, liên kết được hoặc đã được khởi tạo.

Công thức suy luận đúng:

~~~text
Finder tìm thấy descriptor
    != module đã được resolve vào layer hiện tại
    != class cụ thể đã tồn tại hoặc được nạp
    != class truy cập được từ mọi module
    != class đã được khởi tạo thành công
~~~

Khi debug JPMS, hãy xác định rõ mình đang hỏi về **module metadata**, **module graph**, **class file**, **Class<?>**, hay **quyền truy cập/khởi tạo**.