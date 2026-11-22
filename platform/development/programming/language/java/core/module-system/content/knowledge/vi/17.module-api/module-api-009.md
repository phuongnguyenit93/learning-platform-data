# Dùng Reflection để quan sát Module mà không phá vỡ Encapsulation

Từ Java 9, Java Platform Module System (JPMS) đặt mỗi module vào một ranh giới rõ ràng: module nào được đọc, package nào được công khai và package nào cho phép truy cập sâu bằng reflection. Khi debug hoặc xây dựng công cụ kiểm tra runtime, ta thường cần biết một class thuộc module nào và module đó cho phép những kiểu truy cập nào.

Có thể quan sát các thông tin này bằng Reflection API kết hợp với Module API. Việc đọc metadata không đồng nghĩa với việc mở quyền truy cập vào field hoặc method private. Mục tiêu của bài này là kiểm tra cấu trúc và quyền truy cập hiện hành mà không gọi setAccessible, không thay đổi module graph và không đọc dữ liệu nội bộ.

## 1. Từ Class đến Module

Mỗi đối tượng Class có thể cho biết module chứa class đó thông qua Class.getModule():

~~~java
Module module = String.class.getModule();

System.out.println(module.getName()); // java.base
System.out.println(module.isNamed()); // true
~~~

Một số API thường dùng:

| API | Ý nghĩa |
| --- | --- |
| Class.getModule() | Lấy module chứa một class |
| Module.getName() | Lấy tên module; trả về null nếu là unnamed module |
| Module.isNamed() | Kiểm tra module có tên hay không |
| Module.getDescriptor() | Lấy bản mô tả module; có thể trả về null với unnamed module |
| Module.getPackages() | Lấy các package thuộc module |
| Module.getLayer() | Lấy ModuleLayer chứa module; có thể trả về null |
| Module.canRead(other) | Kiểm tra module hiện tại có đọc được module other hay không |
| Module.isExported(package, other) | Kiểm tra package có được export tới module other hay không |
| Module.isOpen(package, other) | Kiểm tra package có được mở cho deep reflection từ module other hay không |

Module API là API runtime. Nó cho biết module mà JVM gắn với class đang chạy, kể cả khi class được nạp từ classpath hoặc từ một module layer.

### Named module và unnamed module

- **Named module** có tên và thường được mô tả bởi file module-info.java. Ví dụ: java.base.
- **Unnamed module** thường chứa các class được nạp từ classpath. Nó không có tên và Module.getDescriptor() trả về null.
- **Automatic module** thường được tạo khi đưa một JAR lên module path nhưng JAR không khai báo module-info.java. Nó vẫn là named module; ModuleDescriptor.isAutomatic() cho biết trường hợp này.

Vì vậy, không nên giả định mọi class đều thuộc một module có tên hoặc đều có ModuleDescriptor.

## 2. Đọc ModuleDescriptor để xem cấu trúc module

Với named module, Module.getDescriptor() trả về một ModuleDescriptor. Descriptor phản ánh các khai báo trong module-info.java, chẳng hạn:

- requires: module này phụ thuộc và đọc module nào.
- exports: package nào được công khai để module khác sử dụng các kiểu public.
- opens: package nào cho phép module khác truy cập sâu bằng reflection.
- uses và provides: các khai báo liên quan đến Java ServiceLoader.
- packages: danh sách package được ghi nhận trong descriptor.

Có thể đọc các khai báo mà không cần mở package:

~~~java
Module module = String.class.getModule();
ModuleDescriptor descriptor = module.getDescriptor();

if (descriptor != null) {
    descriptor.requires().forEach(requirement ->
        System.out.println("requires " + requirement.name())
    );

    descriptor.exports().forEach(export ->
        System.out.println("exports " + export.source())
    );

    descriptor.opens().forEach(open ->
        System.out.println("opens " + open.source())
    );
}
~~~

ModuleDescriptor là mô tả bất biến của cấu hình module. Nếu ứng dụng thay đổi quyền truy cập lúc runtime bằng các API như addOpens hoặc addExports, descriptor không phải nơi để xác nhận trạng thái hiệu lực sau thay đổi đó. Khi cần kiểm tra quyền truy cập hiện hành, hãy dùng các phương thức trên Module như isOpen và isExported.

## 3. Phân biệt requires, exports và opens

Ba khái niệm này giải quyết ba câu hỏi khác nhau:

| Khai báo/API | Câu hỏi được trả lời | Tác động |
| --- | --- | --- |
| requires / canRead | Module gọi có đọc được module đích không? | Xác lập quan hệ readability |
| exports / isExported | Package có công khai API public cho module gọi không? | Cho phép sử dụng public types và public members theo quy tắc truy cập Java |
| opens / isOpen | Package có cho phép deep reflection từ module gọi không? | Cho phép reflection vượt qua một số kiểm tra truy cập thông thường khi được mở |

Ví dụ module khai báo:

~~~java
module inventory {
    requires java.sql;

    exports com.example.inventory.api;

    opens com.example.inventory.model
        to com.fasterxml.jackson.databind;
}
~~~

Trong ví dụ này:

- Module khác có thể sử dụng public API trong package com.example.inventory.api nếu module đó đọc được inventory.
- Package com.example.inventory.model được mở cho module Jackson để framework có thể thực hiện deep reflection.
- Export một package không tự động mở package đó. Một package có thể được export nhưng vẫn không mở cho việc truy cập field private.
- Opens không thay thế exports. Mở package cho reflection không đồng nghĩa với việc công khai package đó như API Java thông thường.

Từ phía module gọi, hãy kiểm tra theo đúng chiều:

~~~java
Module caller = MyApplication.class.getModule();
Module target = SomeLibrary.class.getModule();
String packageName = SomeLibrary.class.getPackageName();

boolean readable = caller.canRead(target);
boolean exported = target.isExported(packageName, caller);
boolean open = target.isOpen(packageName, caller);
~~~

Lưu ý: canRead được gọi trên module gọi; isExported và isOpen được gọi trên module đích, với module gọi làm đối số. Chỉ một trong các điều kiện trên là chưa đủ để kết luận mọi thao tác reflection đều được phép. Các modifier public, private, protected, package-private và quy tắc truy cập của Java vẫn có hiệu lực.

## 4. Ví dụ: viết công cụ quan sát module tại runtime

Ví dụ sau nhận một Class, in ra module chứa class, kiểm tra quan hệ giữa module gọi và module đích, đọc các khai báo trong descriptor, rồi liệt kê tên field. Phần liệt kê field chỉ đọc metadata như tên và modifier; chương trình không đọc giá trị field.

~~~java
import java.lang.module.ModuleDescriptor;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Comparator;
import java.util.Objects;

public class ModuleInspector {

    public static void main(String[] args) {
        inspect(String.class);
        inspect(ModuleInspector.class);
        listBootLayerModules();
    }

    private static void inspect(Class<?> type) {
        Module target = type.getModule();
        Module caller = ModuleInspector.class.getModule();
        String packageName = type.getPackageName();

        System.out.printf("%nClass: %s%n", type.getName());
        System.out.printf(
            "Module: %s (named=%s)%n",
            Objects.toString(target.getName(), "<unnamed>"),
            target.isNamed()
        );

        System.out.printf(
            "Caller reads target: %s%n",
            caller.canRead(target)
        );
        System.out.printf(
            "Package exported to caller: %s%n",
            target.isExported(packageName, caller)
        );
        System.out.printf(
            "Package open to caller: %s%n",
            target.isOpen(packageName, caller)
        );

        ModuleDescriptor descriptor = target.getDescriptor();

        if (descriptor == null) {
            System.out.println(
                "No ModuleDescriptor: this is an unnamed module."
            );
        } else {
            System.out.printf(
                "Automatic module: %s%n",
                descriptor.isAutomatic()
            );
            System.out.printf(
                "Open module: %s%n",
                descriptor.isOpen()
            );

            System.out.println("Requires:");
            descriptor.requires().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Requires::name
                ))
                .forEach(requirement ->
                    System.out.printf(
                        "  %s %s%n",
                        requirement.name(),
                        requirement.modifiers()
                    )
                );

            System.out.println("Exports:");
            descriptor.exports().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Exports::source
                ))
                .forEach(export ->
                    System.out.printf(
                        "  %s -> %s%n",
                        export.source(),
                        export.isQualified()
                            ? export.targets()
                            : "ALL"
                    )
                );

            System.out.println("Opens:");
            descriptor.opens().stream()
                .sorted(Comparator.comparing(
                    ModuleDescriptor.Opens::source
                ))
                .forEach(open ->
                    System.out.printf(
                        "  %s -> %s%n",
                        open.source(),
                        open.isQualified()
                            ? open.targets()
                            : "ALL"
                    )
                );
        }

        System.out.println("Declared fields (metadata only):");
        for (Field field : type.getDeclaredFields()) {
            System.out.printf(
                "  %s %s%n",
                Modifier.toString(field.getModifiers()),
                field.getName()
            );
        }
    }

    private static void listBootLayerModules() {
        System.out.println("%nModules in the boot layer:");

        ModuleLayer.boot().modules().stream()
            .sorted(Comparator.comparing(
                module -> Objects.toString(module.getName(), "")
            ))
            .forEach(module ->
                System.out.println("  " + module.getName())
            );
    }
}
~~~

Nếu chạy trên classpath, ModuleInspector thường thuộc unnamed module nên descriptor của nó là null. String.class thuộc named module java.base. Nếu đóng gói ứng dụng thành named module, ModuleInspector.class sẽ cho biết tên module ứng dụng.

ModuleLayer.boot().modules() liệt kê các module trong boot layer. Ứng dụng có thể tạo thêm module layer riêng, vì vậy danh sách này không đại diện cho mọi module layer tồn tại trong JVM.

## 5. Quan sát member metadata mà không đọc dữ liệu private

Reflection cho phép lấy danh sách member đã khai báo trên class:

~~~java
Field[] fields = SomeClass.class.getDeclaredFields();

for (Field field : fields) {
    System.out.println(field.getName());
    System.out.println(
        Modifier.toString(field.getModifiers())
    );
}
~~~

getDeclaredFields(), getDeclaredMethods() và getDeclaredConstructors() giúp quan sát cấu trúc class, kể cả member có modifier private. Việc lấy metadata này không đồng nghĩa với quyền đọc hoặc gọi member đó.

Nếu cần kiểm tra quyền truy cập đối với một member cụ thể, AccessibleObject.canAccess(target) có thể kiểm tra khả năng truy cập hiện tại mà không bật cờ override. Với field hoặc method instance, truyền object tương ứng; với member static, truyền null.

~~~java
Field field = SomeClass.class.getDeclaredField("status");
Object instance = new SomeClass();

boolean accessible = field.canAccess(instance);
System.out.println("Can access now: " + accessible);
~~~

Đoạn kiểm tra trên không đọc giá trị field và không thay đổi chính sách truy cập. Nếu member là static, hãy dùng field.canAccess(null).

## 6. Vì sao setAccessible(true) có thể thất bại?

Trước JPMS, nhiều thư viện thường gọi setAccessible(true) để đọc field private. Với named module, hành vi này chịu sự kiểm soát của module:

- Nếu package không mở cho module gọi, JVM có thể từ chối deep reflection.
- setAccessible(true) có thể ném InaccessibleObjectException.
- trySetAccessible() trả về false khi không thể bật quyền truy cập.
- Một package được exports nhưng không opens vẫn có thể từ chối truy cập sâu vào member private.

Khi mục tiêu chỉ là quan sát, không gọi setAccessible(true), trySetAccessible() hoặc dùng tùy chọn --add-opens. Các thao tác đó thay đổi hoặc cố gắng thay đổi khả năng truy cập, khiến phép quan sát không còn thuần túy.

Nếu ứng dụng thực sự cần deep reflection, hãy yêu cầu module sở hữu package mở đúng package cho đúng module gọi, ví dụ bằng một opens có đích cụ thể. Chỉ mở rộng phạm vi khi yêu cầu kiến trúc thực sự cần thiết.

## 7. Chạy ví dụ

Có thể chạy ví dụ đơn giản trên classpath bằng JDK 9 trở lên:

~~~shell
javac ModuleInspector.java
java ModuleInspector
~~~

Để quan sát ứng dụng như một named module, đặt file sau tại src/module-info.java:

~~~java
module app {
}
~~~

Giữ ModuleInspector trong package com.example.app, sau đó biên dịch và chạy:

~~~shell
javac -d out src/module-info.java src/com/example/app/ModuleInspector.java
java --module-path out --module app/com.example.app.ModuleInspector
~~~

Khi chạy theo cách này, ModuleInspector.class thuộc module app. Module gọi là app và module đích của String.class là java.base.

## 8. Những nhầm lẫn thường gặp

1. **Nhầm exports với opens:** exports công khai API public; opens cho phép deep reflection. Hai khai báo có mục đích khác nhau.
2. **Gọi canRead trên module đích:** chiều kiểm tra phải là caller.canRead(target), vì câu hỏi là module gọi có đọc module đích không.
3. **Cho rằng có thể đọc private field vì đã lấy được Field:** lấy metadata và đọc giá trị là hai thao tác khác nhau.
4. **Cho rằng descriptor luôn tồn tại:** unnamed module không có ModuleDescriptor.
5. **Cho rằng boot layer chứa mọi module:** ứng dụng có thể tạo module layer khác.
6. **Dùng setAccessible để kiểm tra quyền:** thao tác này can thiệp vào cơ chế truy cập. Dùng canAccess và Module.isOpen để quan sát trạng thái.
7. **Chỉ nhìn module-info.java để kết luận trạng thái runtime:** descriptor thể hiện khai báo ban đầu; các truy vấn trên Module phù hợp hơn khi cần kiểm tra quyền truy cập đang có hiệu lực.

## 9. Quy trình kiểm tra đề xuất

Khi một thư viện reflection không truy cập được class hoặc member, có thể kiểm tra theo thứ tự:

1. Lấy module của class đích bằng Class.getModule().
2. Lấy module của code gọi bằng Class.getModule().
3. Kiểm tra caller.canRead(target).
4. Kiểm tra target.isExported(packageName, caller) nếu cần sử dụng public API.
5. Kiểm tra target.isOpen(packageName, caller) nếu framework cần deep reflection.
6. Đọc ModuleDescriptor để hiểu các khai báo requires, exports và opens.
7. Dùng getDeclaredFields hoặc getDeclaredMethods để xem metadata; dùng canAccess để kiểm tra quyền trên member cụ thể.

Cách tiếp cận này giúp xác định module boundary và nguyên nhân bị từ chối truy cập mà không cần mở encapsulation hoặc đọc dữ liệu nội bộ của class.

## Kết luận

Reflection kết hợp với Module API cung cấp đủ thông tin để quan sát class thuộc module nào, module graph cho phép đọc ra sao, package nào được export và package nào được mở cho deep reflection. Hãy ưu tiên Class.getModule(), Module, ModuleDescriptor, ModuleLayer, isExported(), isOpen() và canRead() cho việc kiểm tra. Chỉ thay đổi quyền truy cập khi đó là yêu cầu có chủ đích của thiết kế ứng dụng.
