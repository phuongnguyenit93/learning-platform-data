# Module::canRead, isExported và isOpen

## 1. Mục tiêu

Trong Java Platform Module System (JPMS), mỗi module có thể đọc module khác, công khai một số package cho module khác, hoặc mở package để module khác truy cập sâu bằng reflection. Ba phương thức của lớp **java.lang.Module** giúp kiểm tra ba quan hệ này ở thời điểm chạy:

- **canRead(Module other)**: module hiện tại có đọc được module khác không?
- **isExported(String packageName)** và **isExported(String packageName, Module other)**: package có được export vô điều kiện hoặc export tới một module cụ thể không?
- **isOpen(String packageName)** và **isOpen(String packageName, Module other)**: package có được mở vô điều kiện hoặc mở cho một module cụ thể để deep reflection không?

Điểm quan trọng là hướng gọi phương thức:

- Gọi **consumer.canRead(provider)** để hỏi module sử dụng có đọc module cung cấp không.
- Gọi **provider.isExported(packageName, consumer)** để hỏi module cung cấp có export package cho module sử dụng không.
- Gọi **provider.isOpen(packageName, consumer)** để hỏi module cung cấp có mở package cho module sử dụng không.

Các phương thức này thuộc lớp **Module** trong package **java.lang**, có từ Java 9. Không cần import riêng lớp Module.

## 2. Module object đại diện cho điều gì?

**Module** là đối tượng runtime đại diện cho một module đã được JVM xác định. Mỗi class có thể cho biết module chứa nó bằng **Class.getModule()**:

~~~java
Module moduleOfCurrentClass = MyApplication.class.getModule();
Module moduleOfLibraryClass = LibraryApi.class.getModule();
~~~

Nếu chỉ biết tên module, có thể tra module trong boot layer:

~~~java
Module library = ModuleLayer.boot()
        .findModule("com.acme.library")
        .orElseThrow();

Module application = MyApplication.class.getModule();
~~~

Một named module có tên và module descriptor. Unnamed module không có tên; mỗi class loader có một unnamed module riêng cho các class không thuộc named module. Phần lớn ứng dụng chạy trên classpath sử dụng unnamed module.

Ba phương thức đang học kiểm tra quan hệ runtime giữa các Module object. Chúng không nhận tên module dạng String ở tham số **other**; hãy truyền đối tượng Module lấy từ **Class.getModule()** hoặc **ModuleLayer**.

## 3. canRead(Module other): kiểm tra readability

Cú pháp:

~~~java
boolean canRead(Module other)
~~~

Phương thức được gọi trên module cần kiểm tra. Kết quả là **true** khi module đó đọc module được truyền vào.

Ví dụ:

~~~java
Module application = MyApplication.class.getModule();
Module library = LibraryApi.class.getModule();

boolean readable = application.canRead(library);
~~~

Nếu **readable** là true, module application có quan hệ readability tới module library trong module graph runtime. Nếu false, application chưa đọc library.

### Readability hình thành như thế nào?

Với named module, quan hệ readability thường bắt đầu từ các chỉ thị **requires** trong module-info.java:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

Khi module graph được tạo, com.acme.application đọc com.acme.library. Chỉ thị **requires transitive** còn truyền readability tới các module phụ thuộc theo quy tắc của module system:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
}
~~~

Module khác đọc com.acme.library cũng có thể đọc com.acme.model thông qua cạnh transitive đó, nếu các module liên quan nằm trong graph tương ứng.

Một module luôn đọc chính nó. Đặc biệt, gọi **canRead** trên unnamed module luôn trả về true vì unnamed module đọc tất cả module.

### canRead không có nghĩa là truy cập được mọi package

Readability chỉ trả lời câu hỏi về quan hệ module. Nó không tự động công khai package của module đích.

Giả sử application đọc library, nhưng library không export package com.acme.internal cho application. Application vẫn không được sử dụng các public type trong package đó như API thông thường chỉ vì **application.canRead(library)** trả về true.

Để truy cập API public của một package trong named module, cần xem thêm quy tắc export và khả năng truy cập của type/member theo Java language.

## 4. isExported: kiểm tra package được export

Có hai overload:

~~~java
boolean isExported(String packageName)

boolean isExported(String packageName, Module other)
~~~

Tên package phải là tên đầy đủ theo dạng dấu chấm, ví dụ **com.acme.api**; không truyền đường dẫn thư mục với dấu gạch chéo.

### Export vô điều kiện

~~~java
boolean exportedToEveryone =
        library.isExported("com.acme.api");
~~~

Overload một tham số trả về true khi package được export vô điều kiện. Trong module-info.java, trường hợp điển hình là:

~~~java
module com.acme.library {
    exports com.acme.api;
}
~~~

Package com.acme.api được export cho các module khác, thay vì chỉ một danh sách module được chỉ định.

### Export tới một module cụ thể

~~~java
boolean exportedToApplication =
        library.isExported("com.acme.spi", application);
~~~

Overload hai tham số trả về true nếu package được export tới ít nhất module được truyền vào. Một qualified export có dạng:

~~~java
module com.acme.library {
    exports com.acme.spi to com.acme.plugin;
}
~~~

Trong ví dụ này, package com.acme.spi được export cho com.acme.plugin. Một module khác không tự động nhận quyền export đó.

Phương thức cũng trả về true khi kiểm tra package đối với chính module chứa package. Khi gọi trên unnamed module, các overload export luôn trả về true.

### Lưu ý quan trọng về package được mở

Theo hợp đồng API runtime của **Module.isExported**, package được mở cho module đích cũng được xem là exported đối với module đó. Vì vậy, **isExported(packageName, other)** có thể trả về true do package đã được mở, kể cả khi module-info.java không có chỉ thị exports tương ứng.

Tương tự, overload một tham số trả về true nếu package được mở vô điều kiện. Vì thế, không nên dùng riêng kết quả **isExported** để suy luận chính xác module descriptor có khai báo chỉ thị **exports** hay không. Nếu cần đọc các khai báo tĩnh trong descriptor, xem **Module.getDescriptor()** và các tập **ModuleDescriptor.exports()** / **ModuleDescriptor.opens()**.

Các overload của **isExported** không kiểm tra xem module đích có đọc module hiện tại hay không. Hãy kiểm tra readability riêng bằng **canRead** khi câu hỏi cần cả hai quan hệ.

## 5. isOpen: kiểm tra package mở cho deep reflection

Có hai overload:

~~~java
boolean isOpen(String packageName)

boolean isOpen(String packageName, Module other)
~~~

**opens** cho phép module đích thực hiện deep reflection lên các type và member trong package, bao gồm member không public, thông qua những API hỗ trợ truy cập sâu như **AccessibleObject.setAccessible**, **trySetAccessible** hoặc **MethodHandles.privateLookupIn** khi các điều kiện liên quan được đáp ứng.

### Mở vô điều kiện

~~~java
boolean openToEveryone =
        library.isOpen("com.acme.model");
~~~

Khai báo tương ứng trong module-info.java:

~~~java
module com.acme.library {
    opens com.acme.model;
}
~~~

Package com.acme.model được mở cho mọi module để deep reflection.

Một cách khai báo rộng hơn là **open module**:

~~~java
open module com.acme.library {
    // Các package trong module được mở cho deep reflection.
}
~~~

Với open module, **isOpen(packageName)** trả về true cho package thuộc module đó.

### Mở cho một module cụ thể

~~~java
boolean openToJson =
        library.isOpen("com.acme.model", jsonFramework);
~~~

Qualified opens chỉ cấp quyền mở package cho module được nêu:

~~~java
module com.acme.library {
    opens com.acme.model to com.acme.json;
}
~~~

Module com.acme.json có thể thực hiện deep reflection trên các type và member trong com.acme.model. Module khác không được hưởng quyền mở này chỉ vì cùng đọc com.acme.library.

Khi gọi **isOpen** để kiểm tra chính module chứa package, kết quả là true. Khi gọi trên unnamed module, các overload open luôn trả về true. Overload một tham số cũng trả về true cho package thuộc một open module.

### isOpen không kiểm tra readability

**isOpen(packageName, other)** chỉ kiểm tra quan hệ mở package; nó không kiểm tra module other có đọc module hiện tại hay không.

API Java ghi rõ một package mở cho module M cho phép code trong M deep reflection lên các type và member của package. Nếu M cần lấy một **Lookup** có quyền định nghĩa class trong package đó bằng **MethodHandles.privateLookupIn**, M còn phải đọc module chứa package.

Do đó, khi chẩn đoán lỗi reflection, cần xác định API reflection đang dùng, kiểm tra package có mở cho đúng module gọi hay không, và kiểm tra thêm readability nếu thao tác yêu cầu.

## 6. Phân biệt readability, exports và opens

| Quan hệ | Câu hỏi | Cấu hình thường gặp | API kiểm tra |
|---|---|---|---|
| Readability | Module A có đọc module B không? | A khai báo requires B | A.canRead(B) |
| Export | Package của B có được công khai cho A để dùng API public không? | B khai báo exports package [to A] | B.isExported(package, A) |
| Open | Package của B có mở cho A để deep reflection không? | B khai báo opens package [to A] hoặc là open module | B.isOpen(package, A) |

Ví dụ module descriptor:

~~~java
module com.acme.library {
    exports com.acme.api;
    exports com.acme.spi to com.acme.plugin;
    opens com.acme.model to com.acme.json;
}
~~~

Module sử dụng API thông thường cần khai báo dependency:

~~~java
module com.acme.application {
    requires com.acme.library;
}
~~~

Có thể diễn giải ba quan hệ theo hướng:

1. **application.canRead(library)** hỏi application có đọc library không.
2. **library.isExported("com.acme.api", application)** hỏi package API có được export tới application không.
3. **library.isOpen("com.acme.model", jsonFramework)** hỏi package model có mở cho framework JSON để deep reflection không.

### exports và opens không thay thế cho nhau

- **exports** công khai API của package theo quy tắc truy cập thông thường: các public type và public member của chúng có thể được module đọc sử dụng khi các điều kiện Java khác cũng thỏa mãn.
- **opens** cấp quyền deep reflection vào package. Chỉ thị opens không tự biến package thành API có thể được import và sử dụng trực tiếp khi biên dịch.
- Một package có thể vừa được export vừa được mở, nhưng hai khai báo phục vụ hai mục đích khác nhau.
- Ở runtime, **Module.isExported** có quy tắc đặc biệt coi package đã mở cho module đích là exported cho module đó. Hãy ghi nhớ điều này khi đọc kết quả API.

## 7. Ví dụ chạy được: kiểm tra module java.sql

Ví dụ sau có thể chạy trên Java 9 trở lên. Khi chạy class này trên classpath, Module của ModuleApiDemo là unnamed module.

~~~java
public class ModuleApiDemo {
    public static void main(String[] args) {
        Module application = ModuleApiDemo.class.getModule();
        Module sql = java.sql.Driver.class.getModule();

        System.out.println(application.canRead(sql));
        System.out.println(sql.isExported("java.sql", application));
        System.out.println(sql.isOpen("java.sql", application));
    }
}
~~~

Kết quả khi chạy trên classpath với JDK tiêu chuẩn:

~~~text
true
true
false
~~~

Giải thích:

- Unnamed module đọc mọi module nên **application.canRead(sql)** là true.
- Module java.sql export package java.sql, do đó **sql.isExported("java.sql", application)** là true.
- Package java.sql không được mở cho deep reflection trong ví dụ này, do đó **sql.isOpen("java.sql", application)** là false.

Nếu chạy ứng dụng trong named module, kết quả readability phụ thuộc module graph và các chỉ thị requires của ứng dụng.

## 8. Ví dụ kiểm tra một thư viện theo tên module

Khi cần kiểm tra một named module mà không tham chiếu trực tiếp tới class trong package đang kiểm tra, có thể lấy Module từ boot layer:

~~~java
import java.util.Optional;

public class InspectLibrary {
    public static void main(String[] args) {
        Module application = InspectLibrary.class.getModule();

        Module library = ModuleLayer.boot()
                .findModule("com.acme.library")
                .orElseThrow();

        boolean readable = application.canRead(library);
        boolean apiExported =
                library.isExported("com.acme.api", application);
        boolean modelOpen =
                library.isOpen("com.acme.model", application);

        System.out.println("Readable: " + readable);
        System.out.println("API exported at runtime: " + apiExported);
        System.out.println("Model open: " + modelOpen);
    }
}
~~~

Tên module truyền cho **findModule** phải là tên module thực tế đã được định nghĩa trong module graph của layer. Nếu module không có trong boot layer, Optional sẽ rỗng; module có thể thuộc một layer khác được tạo riêng.

Kết quả **apiExported** ở đây là trạng thái export theo hợp đồng runtime của Module API. Nếu package được mở cho application, phương thức này cũng có thể trả về true. Muốn xác định chính xác các chỉ thị được khai báo trong descriptor, hãy kiểm tra descriptor riêng.

## 9. Kiểm tra khai báo trong ModuleDescriptor

**Module.getDescriptor()** trả về descriptor của named module; với unnamed module, kết quả là null.

~~~java
var descriptor = library.getDescriptor();

if (descriptor != null) {
    descriptor.exports().forEach(export -> {
        System.out.println("exports " + export.source());
    });

    descriptor.opens().forEach(open -> {
        System.out.println("opens " + open.source());
    });
}
~~~

Cách này hữu ích khi cần phân biệt cấu hình khai báo trong module-info.java với trạng thái runtime đã chịu tác động của các thao tác điều chỉnh module graph. Descriptor mô tả metadata của module; các phương thức **canRead**, **isExported** và **isOpen** trả lời câu hỏi về quan hệ runtime.

## 10. Quan hệ với addReads, addExports và addOpens

Lớp **Module** còn có các phương thức thay đổi một số quan hệ runtime:

- **addReads(other)** bổ sung cạnh readability từ module hiện tại tới other.
- **addExports(packageName, other)** export package cho other.
- **addOpens(packageName, other)** mở package cho other để deep reflection.

Các phương thức này chịu giới hạn caller: với named module, module gọi phải đáp ứng điều kiện API để cập nhật chính module đó; nếu không, có thể nhận **IllegalCallerException**. **addOpens** còn yêu cầu package đã được mở cho module caller theo hợp đồng API.

Đây là các thao tác runtime dành cho framework, container hoặc hạ tầng module có lý do cụ thể. Với ứng dụng thông thường, nên thiết kế dependency và module-info.java rõ ràng trước khi cân nhắc thay đổi quan hệ động.

Sau khi một quan hệ runtime được cập nhật hợp lệ, các phương thức kiểm tra tương ứng phản ánh trạng thái runtime mới.

## 11. Các lỗi hiểu nhầm thường gặp

### Gọi ngược chiều

Sai hướng:

~~~java
library.canRead(application);
~~~

Dòng này hỏi library có đọc application hay không. Nếu muốn biết application có đọc library, phải gọi:

~~~java
application.canRead(library);
~~~

Tương tự, export và open được kiểm tra trên module sở hữu package:

~~~java
library.isExported("com.acme.api", application);
library.isOpen("com.acme.model", application);
~~~

### Nghĩ canRead đồng nghĩa với package đã public

**canRead** không thay thế **exports**. Một module có thể đọc module khác nhưng không được truy cập package nội bộ của module đó theo quy tắc thông thường.

### Nghĩ exports cho phép reflection vào private member

Export package không đồng nghĩa với mở package để deep reflection. Nếu framework cần truy cập private field hoặc private constructor, hãy xem xét **opens** cho đúng module framework.

### Dùng isExported để xác nhận chắc chắn có khai báo exports

Một package được mở cho module đích cũng được xem là exported ở runtime theo hợp đồng **Module.isExported**. Muốn biết module descriptor khai báo exports hay opens, hãy đọc **ModuleDescriptor.exports()** và **ModuleDescriptor.opens()**.

### Nghĩ isOpen tự động bao gồm mọi điều kiện reflection

**isOpen** xác nhận quan hệ mở package với module đích. Từng thao tác reflection vẫn phải tuân theo hợp đồng API được sử dụng. Chẳng hạn, **privateLookupIn** còn có điều kiện về readability; hãy đọc thông báo lỗi và hợp đồng của API cụ thể.

### Truyền sai tên package

Tên package là tên Java đầy đủ, dùng dấu chấm:

~~~java
library.isOpen("com.acme.model", application);
~~~

Không dùng **com/acme/model** hoặc tên class như **com.acme.model.User**.

## 12. Quy tắc và trường hợp biên cần nhớ

1. Module luôn đọc chính nó; **module.canRead(module)** trả về true.
2. Unnamed module đọc mọi module; **canRead** trên unnamed module luôn trả về true.
3. Các overload **isExported** và **isOpen** trả về true khi được gọi trên unnamed module.
4. Kiểm tra package đối với chính module chứa package cũng trả về true theo hợp đồng của các overload có tham số Module.
5. Package được mở cho module đích cũng được xem là exported cho module đó ở runtime.
6. **isExported** và **isOpen** không kiểm tra readability; kiểm tra riêng bằng **canRead** khi cần.
7. **isOpen** trên open module trả về true với package thuộc module đó.
8. Tên package truyền vào là tên đầy đủ, ví dụ **java.sql** hoặc **com.acme.model**.
9. Truyền null vào tham số bắt buộc của các phương thức này gây **NullPointerException**.
10. Các phương thức này kiểm tra trạng thái runtime; đừng nhầm kết quả với việc đọc nguyên văn chỉ thị trong module-info.java.

## 13. Bài tập tự kiểm tra và đáp án

### Bài 1 — Chọn đúng chiều gọi

Module app muốn biết mình có đọc module lib không. Nên gọi biểu thức nào?

A. **lib.canRead(app)**

B. **app.canRead(lib)**

**Đáp án:** B. Phương thức được gọi trên module cần kiểm tra readability.

### Bài 2 — Readability và export

Nếu **app.canRead(lib)** trả về true, app có chắc chắn sử dụng được mọi public class trong mọi package của lib không?

**Đáp án:** Không. Package vẫn phải được export cho app và type/member phải thỏa các quy tắc truy cập Java. Readability không công khai toàn bộ package.

### Bài 3 — Qualified export

Module lib khai báo:

~~~java
module com.acme.library {
    exports com.acme.spi to com.acme.plugin;
}
~~~

Giả sử không có khai báo opens liên quan. Khi kiểm tra từ module plugin, overload nào phù hợp để hỏi package có được export tới plugin không?

**Đáp án:**

~~~java
lib.isExported("com.acme.spi", plugin);
~~~

Overload hai tham số kiểm tra quan hệ với module đích cụ thể.

### Bài 4 — Export hay open?

Một framework cần đọc private field của class trong package com.acme.model. Chỉ khai báo **exports com.acme.model** đã đủ để cấp deep reflection chưa?

**Đáp án:** Chưa. Cần mở package cho module framework bằng opens hoặc một cơ chế runtime hợp lệ tương ứng. Export phục vụ truy cập API thông thường.

### Bài 5 — Vì sao isExported trả về true?

Module lib có khai báo:

~~~java
module com.acme.library {
    opens com.acme.model to com.acme.json;
}
~~~

Vì sao **lib.isExported("com.acme.model", json)** có thể trả về true dù module-info.java không có dòng exports cho package này?

**Đáp án:** Module API quy định package được mở cho module đích cũng được xem là exported đối với module đó ở runtime.

### Bài 6 — isOpen có kiểm tra canRead không?

Nếu **lib.isOpen("com.acme.model", app)** trả về true, kết quả này có chứng minh app đọc lib không?

**Đáp án:** Không. isOpen không kiểm tra readability. Dùng **app.canRead(lib)** để kiểm tra riêng. Một số thao tác như privateLookupIn còn yêu cầu caller đọc target module.

### Bài 7 — Unnamed module

Một ứng dụng chạy trên classpath lấy được Module của chính nó. Kết quả **app.canRead(anyNamedModule)** có thể là false không?

**Đáp án:** Không. Unnamed module đọc tất cả module, nên canRead trả về true.

### Bài 8 — Kiểm tra descriptor

Muốn biết module-info.java khai báo package trong exports hay opens, chỉ gọi **isExported** có đủ không?

**Đáp án:** Không. isExported có thể trả true do package được mở ở runtime. Hãy kiểm tra **module.getDescriptor().exports()** và **module.getDescriptor().opens()** để xem các khai báo trong descriptor.

## 14. Checklist khi sử dụng ba phương thức

- Đã xác định đúng module sở hữu package và module cần truy cập chưa?
- Đã gọi **canRead** trên module consumer và truyền module provider chưa?
- Đã gọi **isExported** / **isOpen** trên module provider và truyền module consumer chưa?
- Mục tiêu là truy cập API public hay deep reflection?
- Đã phân biệt exports với opens trong module-info.java chưa?
- Có nhớ **isExported** coi package mở cho module đích là exported ở runtime không?
- Có cần đọc descriptor để biết chính xác khai báo tĩnh không?
- Có kiểm tra readability riêng khi thao tác cần nó không?
- Có truyền đúng tên package đầy đủ và Module object hợp lệ không?
- Có xét trường hợp unnamed module và open module khi diễn giải kết quả không?

**Ghi nhớ:** **canRead** kiểm tra cạnh readability từ consumer tới provider; **isExported** kiểm tra trạng thái export runtime của package; **isOpen** kiểm tra quyền deep reflection. Hãy xác định đúng hướng quan hệ trước khi gọi phương thức và đừng coi ba kết quả này là một loại quyền duy nhất.

## Tài liệu tham khảo

- Oracle Java SE 21 API — **java.lang.Module**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html
- Oracle Java SE 21 API — **java.lang.module.ModuleDescriptor**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html
- Java Language Specification, Java SE 21 — **Chapter 7: Packages and Modules**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
- OpenJDK JEP 261 — **Module System**: https://openjdk.org/jeps/261
