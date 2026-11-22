# Annotation áp dụng cho khai báo mô-đun

Annotation trên khai báo mô-đun là metadata gắn trực tiếp với một module được khai báo trong tệp `module-info.java`. Java hỗ trợ vị trí annotation này từ Java 9 thông qua `ElementType.MODULE`. Tính năng vẫn có trong các JDK hiện đại và hữu ích khi cần mô tả module cho annotation processor, công cụ build, công cụ kiểm tra kiến trúc hoặc mã chạy cần đọc metadata.

Điểm quan trọng là annotation chỉ cung cấp thông tin cho công cụ hoặc chương trình chủ động đọc nó. Annotation không thay đổi đồ thị module, không tự thêm dependency và không mở package cho reflection. Những hành vi đó vẫn được khai báo bằng các directive của JPMS.

## 1. Vị trí cú pháp của annotation

Một module được khai báo trong `module-info.java`. Annotation đặt ngay trước từ khóa `module` hoặc trước cặp từ khóa `open module`:

~~~java
@com.example.ModuleMetadata(owner = "platform-team")
module com.example.orders {
    requires java.logging;
    exports com.example.orders.api;
}
~~~

Với module mở:

~~~java
@com.example.ModuleMetadata(owner = "platform-team")
open module com.example.legacyadapter {
    requires java.sql;
}
~~~

Cả hai cách đều là annotation trên module declaration. Từ khóa `open` vẫn là modifier của JPMS; annotation không tạo ra trạng thái mở đó.

Một annotation type muốn chỉ áp dụng cho module nên khai báo:

~~~java
@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ModuleMetadata {
    String owner();
}
~~~

`ElementType.MODULE` được bổ sung trong Java 9. Nếu dùng annotation type có `@Target` không cho phép `MODULE`, trình biên dịch sẽ báo lỗi khi annotation được đặt trên module declaration. Khai báo target rõ ràng giúp giới hạn cách sử dụng và giúp người đọc hiểu ý nghĩa của annotation.

Các giá trị annotation phải là biểu thức hằng hợp lệ theo quy tắc của Java annotation, ví dụ primitive, String, enum constant, class literal, annotation lồng nhau hoặc mảng các giá trị hợp lệ. Không thể truyền một object được tạo lúc chạy, đọc trực tiếp biến môi trường hay gọi một phương thức để tính giá trị.

## 2. Retention quyết định annotation còn ở đâu

`@Retention` quyết định annotation được giữ đến giai đoạn nào. Quy tắc này áp dụng cho annotation trên module giống như annotation trên class, method hoặc field.

| Retention | Sau khi biên dịch | Đọc bằng reflection lúc chạy |
|---|---|---|
| `SOURCE` | Không được lưu trong file class | Không |
| `CLASS` | Được lưu trong file class; đây là mặc định nếu không khai báo `@Retention` | Không |
| `RUNTIME` | Được lưu trong file class | Có |

Chọn retention theo nơi cần dùng:

- Chọn `SOURCE` khi annotation chỉ phục vụ kiểm tra hoặc sinh mã trong lúc biên dịch và không cần giữ lại trong artifact.
- Chọn `CLASS` khi công cụ đọc bytecode cần metadata sau khi biên dịch nhưng ứng dụng không cần reflection lúc chạy.
- Chọn `RUNTIME` khi chương trình cần truy vấn metadata của module lúc chạy.

Annotation processor hoạt động trong quá trình biên dịch có thể đọc annotation từ mô hình mã nguồn; không cần đặt retention là `RUNTIME` chỉ để processor nhìn thấy annotation. Ngược lại, nếu chương trình gọi `Module.getAnnotation(...)`, annotation phải có retention `RUNTIME`.

## 3. Đọc annotation bằng annotation processor

Trong Java Compiler API, khai báo module được biểu diễn bằng `ModuleElement` thuộc package `javax.lang.model.element`. Một annotation processor có thể nhận diện module bằng `ElementKind.MODULE`, sau đó đọc annotation mirrors và các directive của module.

Ví dụ dưới đây là phần xử lý minh họa bên trong phương thức `process` của annotation processor; đây không phải chương trình độc lập:

~~~java
TypeElement marker = processingEnv.getElementUtils()
        .getTypeElement("com.example.ModuleMetadata");

if (marker != null) {
    for (Element element : roundEnv.getElementsAnnotatedWith(marker)) {
        if (element.getKind() == ElementKind.MODULE) {
            ModuleElement module = (ModuleElement) element;
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Processing module: " + module.getQualifiedName(),
                    module);
        }
    }
}
~~~

Processor cần được đăng ký và cấu hình trong quy trình biên dịch như các annotation processor khác. Khi xử lý module declaration, có thể dùng `ModuleElement.getQualifiedName()` để lấy tên module, `getDirectives()` để kiểm tra các directive, và `getAnnotationMirrors()` để đọc metadata đã khai báo.

Cách này hữu ích khi nhóm muốn áp dụng quy tắc kiến trúc tự động, ví dụ kiểm tra mọi module sản phẩm đều khai báo owner, xác nhận tên module tuân theo quy ước, hoặc sinh tài liệu module từ metadata. Annotation không tự chạy processor; build phải cấu hình processor và nhóm phải viết logic xử lý tương ứng.

## 4. Đọc annotation lúc chạy bằng Module API

Từ Java 9, `java.lang.Module` triển khai `java.lang.reflect.AnnotatedElement`. Vì vậy, mã chạy có thể lấy module của một class rồi đọc annotation có retention `RUNTIME`:

~~~java
Module module = SomeService.class.getModule();
ModuleMetadata metadata = module.getAnnotation(ModuleMetadata.class);
~~~

Các phương thức thường dùng gồm:

- `getAnnotation(Class<T>)`: lấy annotation được chỉ định, hoặc trả về `null` nếu không có annotation phù hợp.
- `getAnnotations()`: lấy các annotation runtime có trên module.
- `getDeclaredAnnotations()`: lấy các annotation được khai báo trực tiếp trên module.

Hãy kiểm tra kết quả `null` trước khi sử dụng. Nếu annotation type nằm trong một module khác, module chứa mã đọc annotation phải có khả năng đọc module đó và truy cập được package chứa annotation type. Trong ví dụ ở phần sau, annotation type nằm cùng module với class đọc nó nên không cần dependency bổ sung.

Lưu ý: `Class.getAnnotations()` trả về annotation của class, không phải annotation của module chứa class. Muốn đọc metadata module, phải truy vấn `SomeService.class.getModule()` rồi gọi API trên đối tượng `Module`.

## 5. Annotation không thay thế directive của JPMS

Annotation và module directive giải quyết hai mục đích khác nhau:

| Thành phần | Vai trò |
|---|---|
| Annotation trên module | Metadata do processor, build tool hoặc ứng dụng chủ động đọc |
| `requires` | Khai báo dependency và quan hệ đọc module |
| `exports` | Cho module khác truy cập các kiểu public trong package được export |
| `opens` | Cho phép truy cập phản chiếu sâu vào package được mở theo phạm vi khai báo |
| `open module` | Mở tất cả package của module cho deep reflection |
| `uses` / `provides` | Khai báo nhu cầu và implementation của Java Service Provider |

Ví dụ, `@OpenModule` tự định nghĩa không làm module trở thành open module. Nếu cần mở toàn bộ package, phải dùng từ khóa `open module`. Nếu chỉ cần mở một package cho một module framework cụ thể, dùng directive `opens package.name to framework.module;`.

Tương tự, annotation tên `@Requires` không thêm dependency vào đồ thị module. Dependency phải được khai báo bằng directive `requires` trong `module-info.java`. JPMS chỉ áp dụng các directive hợp lệ của module descriptor; nó không suy diễn hành vi từ tên hoặc nội dung tùy ý của annotation.

## 6. Ví dụ hoàn chỉnh: gắn metadata và đọc lúc chạy

Ví dụ tạo một module có annotation mô tả nhóm sở hữu và mục đích. Annotation dùng `RUNTIME` để chương trình đọc được sau khi chạy.

Cấu trúc thư mục:

~~~text
src/
  module-info.java
  demo/
    ModuleMetadata.java
    Main.java
~~~

**Tệp `src/demo/ModuleMetadata.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.MODULE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ModuleMetadata {
    String owner();
    String purpose();
}
~~~

**Tệp `src/module-info.java`:**

~~~java
@demo.ModuleMetadata(
        owner = "platform-team",
        purpose = "Attach metadata to the module descriptor"
)
module demo.module {
    exports demo;
}
~~~

**Tệp `src/demo/Main.java`:**

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        Module module = Main.class.getModule();
        ModuleMetadata metadata = module.getAnnotation(ModuleMetadata.class);

        if (metadata == null) {
            throw new IllegalStateException("Module metadata is missing");
        }

        System.out.println("Module: " + module.getName());
        System.out.println("Owner: " + metadata.owner());
        System.out.println("Purpose: " + metadata.purpose());
    }
}
~~~

Biên dịch bằng JDK 17 trở lên. Tạo thư mục output nếu chưa có, sau đó chạy từ thư mục gốc của dự án:

~~~bash
mkdir out
javac --release 17 -d out src/module-info.java src/demo/ModuleMetadata.java src/demo/Main.java
java --module-path out -m demo.module/demo.Main
~~~

Nếu thư mục `out` đã tồn tại, có thể dùng lại thư mục đó. Kết quả chương trình:

~~~text
Module: demo.module
Owner: platform-team
Purpose: Attach metadata to the module descriptor
~~~

Ở ví dụ này, `Main.class.getModule()` trả về module chứa class `Main`. `Module.getAnnotation(ModuleMetadata.class)` đọc metadata được giữ lại nhờ `RetentionPolicy.RUNTIME`. Nếu bỏ `@Retention(RetentionPolicy.RUNTIME)`, retention mặc định là `CLASS`; chương trình không thể đọc annotation bằng reflection và nhánh kiểm tra sẽ báo lỗi.

## 7. Lưu ý khi thiết kế và bảo trì

- **Dùng annotation có mục đích rõ ràng.** Chỉ tạo annotation module khi có processor, build tool, tài liệu hoặc mã chạy thực sự tiêu thụ metadata đó. Annotation không có consumer chỉ làm descriptor khó đọc hơn.
- **Chọn retention theo nhu cầu.** Không mặc định dùng `RUNTIME` cho mọi annotation. Metadata chỉ dùng lúc biên dịch nên cân nhắc `SOURCE`; metadata dành cho bytecode tooling có thể dùng `CLASS`.
- **Giữ annotation type ổn định.** Nếu nhiều module cùng dùng một annotation, đặt nó trong một thư viện metadata nhỏ, có version và API rõ ràng. Khi đổi tên package hoặc element, kiểm tra các module và processor phụ thuộc.
- **Cấu hình toolchain đúng phiên bản.** Module declaration và `ElementType.MODULE` yêu cầu Java 9 trở lên. Build cần dùng JDK phù hợp; không thể biên dịch source này với `--release 8`.
- **Không lưu bí mật hoặc cấu hình môi trường.** Giá trị annotation được đóng gói trong artifact và có thể được đọc từ bytecode hoặc lúc chạy. Chỉ lưu metadata không nhạy cảm, ổn định theo bản build.
- **Không dùng annotation làm ranh giới bảo mật.** Quyền đọc module, export package và mở reflection phải được kiểm soát bằng JPMS và cấu hình runtime thích hợp.
- **Kiểm tra module thực tế khi chạy.** Code trong classpath thuộc unnamed module; module annotation cần được khai báo trên named module có `module-info.java`.
- **Kiểm thử processor như một phần của build.** Kiểm tra module không có annotation, annotation sai giá trị, module name không hợp lệ và nhiều module cùng được xử lý. Với reflection, kiểm tra annotation thiếu hoặc annotation type không khả dụng ở runtime.

## 8. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler từ chối annotation trên module | Annotation type không cho phép `ElementType.MODULE` hoặc toolchain quá cũ | Thêm `@Target(ElementType.MODULE)` và biên dịch bằng JDK 9+ |
| `getAnnotation` trả về `null` | Annotation không có retention `RUNTIME`, hoặc annotation không được khai báo trên module đang truy vấn | Kiểm tra `@Retention`, `module-info.java` và class dùng để lấy module |
| Processor không thấy module annotation | Processor chưa được cấu hình, chưa hỗ trợ annotation hoặc chỉ xử lý loại element khác | Kiểm tra cấu hình processor, `ElementKind.MODULE` và `ModuleElement` |
| Package vẫn không mở cho reflection | Nhầm annotation metadata với directive `opens` hoặc `open module` | Khai báo đúng directive trong `module-info.java` |
| Annotation type không tải được ở runtime | Module đọc annotation thiếu dependency hoặc package chứa annotation type không truy cập được | Bảo đảm annotation type có mặt và module chứa mã đọc có quyền đọc/truy cập nó |
| Metadata chứa giá trị cũ sau khi đổi cấu hình | Annotation được đóng gói tại thời điểm biên dịch | Build lại artifact với metadata mới; không xem annotation là cấu hình runtime |

## 9. Checklist áp dụng

- [ ] Annotation type có `@Target(ElementType.MODULE)`.
- [ ] `@Retention` phù hợp với nơi sử dụng metadata.
- [ ] Annotation được đặt trước `module` hoặc `open module` trong đúng `module-info.java`.
- [ ] Build toolchain và annotation processor hỗ trợ Java 9+.
- [ ] Processor hoặc mã chạy có consumer cụ thể cho metadata.
- [ ] Nếu dùng reflection, annotation có retention `RUNTIME` và annotation type khả dụng lúc chạy.
- [ ] Các yêu cầu dependency, export và reflection vẫn được khai báo bằng module directive.
- [ ] Metadata không chứa bí mật hoặc dữ liệu thay đổi theo môi trường.

## 10. Tài liệu tham khảo

- [Java Language Specification — Module Declarations (JLS §7.7)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
- [Java SE API — ElementType.MODULE](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Java SE API — Retention and RetentionPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE API — java.lang.Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html)
- [Java SE API — ModuleElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ModuleElement.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
