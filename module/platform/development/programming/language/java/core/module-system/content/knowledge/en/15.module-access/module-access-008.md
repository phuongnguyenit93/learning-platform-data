# Xác định module của class bằng getModule()

## 1. Mục tiêu

Trong Java Platform Module System (JPMS, từ Java 9), một class được gắn với một đối tượng `java.lang.Module` ở thời điểm chạy. Phương thức `Class.getModule()` cho biết **module thực sự đang chứa class đó** trong JVM.

Sau bài này, bạn có thể:

- Gọi `SomeClass.class.getModule()` để xác định module của class đang được tải.
- Phân biệt named module và unnamed module (classpath) bằng `isNamed()` và `getName()`.
- Hiểu kết quả với class thư viện JDK, class ứng dụng, primitive type và array type.
- Đọc `ModuleDescriptor`, `ModuleLayer` và class loader để phân tích bối cảnh runtime.
- Dùng `canRead()`, `isExported()` và `isOpen()` để tìm hiểu quyền truy cập giữa các module.
- Tránh nhầm lẫn giữa tên package, tên JAR, tên Maven artifact và tên JPMS module.

Các ví dụ sử dụng Java 11 trở lên; bản thân `Class.getModule()` đã xuất hiện từ Java 9.

## 2. Class.getModule() trả về gì?

Khai báo phương thức trong `java.lang.Class`:

~~~java
public Module getModule()
~~~

Kết quả là một đối tượng `java.lang.Module` thể hiện module mà lớp thuộc về ở runtime. Đối tượng `Module` giữ thông tin danh tính module, mối quan hệ với layer và class loader, đồng thời hỗ trợ kiểm tra khả năng đọc module khác và mức độ mở/export package.

Cách dùng cơ bản:

~~~java
Module module = String.class.getModule();

System.out.println(module.isNamed()); // true
System.out.println(module.getName());  // java.base
~~~

`String` thuộc module nền tảng `java.base`. Một class ứng dụng được chạy trên **classpath** thường thuộc **unnamed module** của class loader đã nạp nó:

~~~java
Module current = MyApp.class.getModule();

System.out.println(current.isNamed()); // false nếu MyApp chạy trên classpath
System.out.println(current.getName());  // null đối với unnamed module
~~~

Kết quả ví dụ phụ thuộc vào cách bạn **chạy** ứng dụng. Nếu `MyApp` được biên dịch và khởi chạy như named module, `isNamed()` sẽ là `true` và `getName()` trả tên module được khai báo.

**Phân biệt quan trọng:** package `com.example.demo` không nhất thiết là module `com.example.demo`. Cùng một package name có thể xuất hiện ở các bối cảnh module khác nhau; không thể xác định module chỉ từ `getPackageName()`.

## 3. Các phương thức Module thường đi cùng getModule()

| Phương thức | Ý nghĩa |
| --- | --- |
| `module.isNamed()` | `true` nếu là named module; `false` nếu là unnamed module. |
| `module.getName()` | Tên named module; **`null` đối với unnamed module**. |
| `module.getDescriptor()` | `ModuleDescriptor` của named module; `null` nếu unnamed. |
| `module.getLayer()` | Layer chứa module nếu có; có thể là `null`. |
| `module.getClassLoader()` | Class loader định nghĩa module; có thể là `null` đối với bootstrap loader. |
| `module.getPackages()` | Các package mà module biết mình chứa; không phải danh sách mọi class. |
| `module.canRead(other)` | Module hiện tại có quan hệ readability tới module khác hay không. |
| `module.isExported(pkg)` | Package có được export vô điều kiện không. |
| `module.isExported(pkg, target)` | Package có được export cho module đích không. |
| `module.isOpen(pkg, target)` | Package có được mở cho deep reflection từ module đích không. |

Không gọi thẳng `module.getName().equals(...)` khi chưa kiểm tra `isNamed()`, bởi `getName()` có thể là `null`. Tương tự, hãy kiểm tra `getDescriptor() != null` trước khi truy cập các chỉ thị của descriptor.

Một module có tên có thể ở boot layer hoặc layer tùy chỉnh. Một unnamed module không có `ModuleDescriptor` và không thuộc một `ModuleLayer`; `getLayer()` là `null`. Với named module được tạo động nhưng chưa được đặt vào layer, `getLayer()` cũng có thể là `null`, do đó không suy ra `isNamed()` từ riêng layer.

## 4. Ví dụ 1: quan sát class của JDK và ứng dụng trên classpath

Tạo file `ModuleInspector.java`:

~~~java
import java.lang.module.ModuleDescriptor;

public class ModuleInspector {

    private static void inspect(Class<?> type) {
        Module module = type.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Class: " + type.getTypeName());
        System.out.println("  named: " + module.isNamed());
        System.out.println("  name: " +
                (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("  descriptor: " +
                (descriptor == null ? "<none>" : descriptor.name()));
        System.out.println("  layer: " +
                (module.getLayer() == null ? "<none>" : "present"));
        System.out.println();
    }

    public static void main(String[] args) {
        inspect(String.class);
        inspect(java.util.ArrayList.class);
        inspect(ModuleInspector.class);
        inspect(int.class);
        inspect(String[].class);
        inspect(ModuleInspector[].class);
    }
}
~~~

Biên dịch và chạy ở chế độ classpath:

~~~sh
javac ModuleInspector.java
java ModuleInspector
~~~

Những kết quả chính có thể quan sát:

| Class | Module ở runtime |
| --- | --- |
| `String.class` | Named module `java.base`. |
| `java.util.ArrayList.class` | Named module `java.base`. |
| `ModuleInspector.class` | Unnamed module của class loader nạp ứng dụng, khi chạy bằng classpath. |
| `int.class` | `java.base` dù đây là primitive type. |
| `String[].class` | Cùng module với kiểu phần tử `String`, tức `java.base`. |
| `ModuleInspector[].class` | Cùng module với kiểu phần tử `ModuleInspector`, tức unnamed module khi chạy bằng classpath. |

Với primitive type hoặc `void.class`, `getModule()` trả về `java.base`. Với array type, kết quả là module của **element type**. Java không gắn một module độc lập chỉ dành cho mảng.

Lưu ý: `getModule()` trả về đối tượng module, không phải chỉ chuỗi tên; `Module.toString()` hữu ích cho log nhưng không nên dùng làm API để phân tích tên module. Hãy gọi `isNamed()` và `getName()` trực tiếp.

## 5. Ví dụ 2: cùng mã nguồn, chạy như named module

Để thấy sự khác biệt giữa classpath và module path, tạo cấu trúc dự án:

~~~text
src/
  com.example.modulecheck/
    module-info.java
    com/example/modulecheck/Main.java
~~~

**`src/com.example.modulecheck/module-info.java`**

~~~java
module com.example.modulecheck {
    exports com.example.modulecheck;
}
~~~

**`src/com.example.modulecheck/com/example/modulecheck/Main.java`**

~~~java
package com.example.modulecheck;

public class Main {
    public static void main(String[] args) {
        print(Main.class);
        print(String.class);
    }

    private static void print(Class<?> type) {
        Module module = type.getModule();
        System.out.printf(
                "%s -> named=%s, module=%s%n",
                type.getName(),
                module.isNamed(),
                module.getName()
        );
    }
}
~~~

Biên dịch dạng module:

~~~sh
javac --module-source-path src -d out -m com.example.modulecheck
~~~

Sau đó chạy qua **module path** với module root rõ ràng:

~~~sh
java --module-path out -m com.example.modulecheck/com.example.modulecheck.Main
~~~

Kết quả mong đợi:

~~~text
com.example.modulecheck.Main -> named=true, module=com.example.modulecheck
java.lang.String -> named=true, module=java.base
~~~

Class `Main` ở một named module bởi JVM đã resolve và nạp `com.example.modulecheck` vào một module layer. Lệnh `-m` chỉ rõ module và main class. Thư mục `out` chứa exploded module tại `out/com.example.modulecheck`.

Nếu chạy trực tiếp class ứng dụng ấy bằng classpath:

~~~sh
java -cp out/com.example.modulecheck com.example.modulecheck.Main
~~~

thì `Main.class.getModule()` sẽ phản ánh **unnamed module**, kể cả khi thư mục class có `module-info.class`. Việc hiện diện của file descriptor trên ổ đĩa không tự làm class chạy trên classpath trở thành named module.

Vì vậy, hãy kiểm tra **cách khởi chạy thực tế** trước khi kết luận class đang ở module nào.

## 6. Kết hợp reflection và getModule()

Khi chỉ biết tên đầy đủ của một class tại runtime, có thể tải/tra cứu `Class<?>` trước, rồi hỏi module của nó:

~~~java
public class LookupModule {
    public static void main(String[] args) throws ClassNotFoundException {
        String className = "java.util.ArrayList";

        Class<?> type = Class.forName(className);
        Module module = type.getModule();

        System.out.println("Class: " + type.getName());
        System.out.println("Module: " + module.getName());
        System.out.println("Named: " + module.isNamed());
    }
}
~~~

`Class.forName(String)` mặc định thực hiện khởi tạo class khi phù hợp. Nếu chỉ cần thông tin class mà không muốn yêu cầu khởi tạo, có thể dùng overload:

~~~java
Class<?> type = Class.forName(
        "java.util.ArrayList",
        false,
        ClassLoader.getSystemClassLoader()
);
Module module = type.getModule();
~~~

Đây là ví dụ với class JDK vốn có thể được tìm bởi loader được dùng. Với một class plugin tùy biến, cần đưa đúng class loader và đảm bảo named module đã được resolve/nằm trong layer thích hợp; nếu không, `Class.forName` có thể ném `ClassNotFoundException`.

Cần phân biệt:

- `Class.forName(...)` tìm/tải class theo cơ chế class loader.
- `type.getModule()` lấy module đã gắn với đối tượng `Class<?>` ấy.
- `ModuleFinder.find(name)` tìm **định nghĩa module** trên các đường dẫn/module source, chưa bảo đảm module đó đã được resolve, tải class hay đưa vào layer.

`getModule()` không tự tìm một JAR trên module path hoặc tải một class bất kỳ từ tên module. Trước hết phải có đối tượng `Class<?>` tương ứng.

## 7. Kiểm tra readability, exports và opens

Biết class thuộc module nào mới là bước đầu. Khi phân tích lỗi truy cập giữa các module, hãy xem riêng ba quan hệ:

1. **Readability:** module gọi có đọc được module chứa class không? Dùng `caller.canRead(target)`.
2. **Exports:** package chứa public type có được export tới module gọi không? Dùng `target.isExported(packageName, caller)`.
3. **Opens:** package có được mở cho deep reflection từ module gọi không? Dùng `target.isOpen(packageName, caller)`.

Ví dụ:

~~~java
public class CheckAccess {
    public static void main(String[] args) {
        Class<?> targetType = java.util.ArrayList.class;

        Module caller = CheckAccess.class.getModule();
        Module target = targetType.getModule();
        String pkg = targetType.getPackageName();

        System.out.println("Caller module: " +
                (caller.isNamed() ? caller.getName() : "<unnamed>"));
        System.out.println("Target module: " + target.getName());
        System.out.println("Package: " + pkg);

        System.out.println("Can read: " + caller.canRead(target));
        System.out.println("Exported to caller: " +
                target.isExported(pkg, caller));
        System.out.println("Open to caller: " +
                target.isOpen(pkg, caller));
    }
}
~~~

Chạy với:

~~~sh
javac CheckAccess.java
java CheckAccess
~~~

`java.util` thuộc `java.base` và được export cho ứng dụng thông thường, nên ví dụ có thể dùng các public class như `ArrayList`. Tuy nhiên, điều đó **không đồng nghĩa** mọi thành viên private của `ArrayList` đều có thể bị truy cập bằng reflection.

### Exports khác opens thế nào?

Giả sử một module có descriptor:

~~~java
module com.example.library {
    exports com.example.library.api;
    opens com.example.library.internal;
}
~~~

- `exports com.example.library.api` cho phép các module đọc được thư viện sử dụng những public type trong package API ở mức truy cập thông thường.
- `opens com.example.library.internal` cho phép deep reflection đối với package internal theo quy tắc của JPMS, nhưng không tự biến package internal thành API import công khai để biên dịch.
- Có thể dùng `exports ... to ...` hoặc `opens ... to ...` để chỉ định các module đích.

Nếu một package chỉ được export mà không open, việc gọi `setAccessible(true)` vào thành viên private qua reflection có thể bị chặn, ví dụ `InaccessibleObjectException`. Bản thân `getModule()` không vượt qua quy tắc encapsulation.

**Giới hạn diễn giải:** `canRead` phản ánh quan hệ readability hiện hành giữa các đối tượng module; `isExported` và `isOpen` phản ánh các điều kiện của package đối với module đích. Những giá trị đó là đầu mối phân tích, nhưng khả năng truy cập một member còn phụ thuộc visibility của class/member và các quy tắc reflection khác.

## 8. ModuleDescriptor, ModuleLayer và class loader

Khi cần phân tích vì sao cùng một class name có hành vi khác nhau trong hai môi trường chạy, đừng chỉ log `getName()`. Hãy ghi lại các dữ kiện liên quan:

~~~java
import java.lang.module.ModuleDescriptor;

public class DescribeModule {
    public static void main(String[] args) {
        Module module = DescribeModule.class.getModule();
        ModuleDescriptor descriptor = module.getDescriptor();

        System.out.println("Name: " +
                (module.isNamed() ? module.getName() : "<unnamed>"));
        System.out.println("Descriptor: " +
                (descriptor == null ? "<none>" : descriptor.name()));
        System.out.println("Layer: " +
                (module.getLayer() == null
                        ? "<none>"
                        : module.getLayer().toString()));
        System.out.println("Class loader: " +
                (module.getClassLoader() == null
                        ? "<bootstrap>"
                        : module.getClassLoader().getClass().getName()));
    }
}
~~~

`ModuleDescriptor` là mô tả cấu trúc module, gồm tên, `requires`, `exports`, `opens`, `uses` và `provides`. Đối với unnamed module không có descriptor, vì vậy chương trình cần xử lý `null`.

`ModuleLayer` là nhóm module đã được resolve và định nghĩa để chạy cùng các class loader. Các module hệ thống đã được nạp thường thuộc boot layer; ứng dụng hoặc hệ plugin có thể định nghĩa module trong layer riêng.

`ClassLoader` quyết định việc định nghĩa class. Với các class nền tảng như `String`, loader có thể là bootstrap loader và được biểu diễn bởi `null`. Với class ứng dụng, giá trị phụ thuộc môi trường và cách nạp.

Hai module cùng tên xuất hiện trong **hai layer/class loader khác nhau** không nhất thiết là cùng một đối tượng `Module`. Tương tự, hai class có cùng binary name được định nghĩa bởi hai loader khác nhau là những `Class<?>` khác nhau, và kết quả `getModule()` cũng có thể khác. Khi debug plugin hoặc ứng dụng nhiều layer, ghi log cả module, layer lẫn class loader sẽ giúp nhận diện bối cảnh chính xác hơn.

## 9. Các tình huống thực tế

### 9.1. Class thư viện nằm trên classpath

Một JAR thư viện đặt trên classpath không tự trở thành named module. Class của JAR ấy thường thuộc unnamed module của loader nạp nó. Nếu cùng JAR được dùng như một automatic module trên module path và thực sự được resolve, class thuộc named automatic module. Xem trạng thái bằng:

~~~java
Module m = SomeLibraryClass.class.getModule();
System.out.println(m.isNamed());
System.out.println(m.getName());
~~~

Nếu là named module, có thể kiểm tra descriptor:

~~~java
if (m.isNamed() && m.getDescriptor() != null) {
    System.out.println(m.getDescriptor().isAutomatic());
}
~~~

Không suy ra tên module từ Maven `groupId:artifactId` hoặc filename của JAR. Automatic-module name có thể được khai báo qua manifest hoặc suy ra từ filename; kết quả runtime từ `getModule()` là nguồn phù hợp để xác nhận class đã được nạp.

### 9.2. Class có tên package giống module

Ví dụ class `org.example.api.Service` không đương nhiên nằm trong module `org.example.api`. Descriptor có thể đặt tên module là `org.example.service`, hoặc class có thể thuộc unnamed module. Chỉ `Service.class.getModule()` mới phản ánh module của class ở runtime.

### 9.3. Không thể import public class dù tìm thấy ở JAR

Kiểm tra class có thực sự nằm trong named module được resolve không, module gọi có đọc được module đích không và package đã export chưa. Một class public trong package không export vẫn có thể không được module khác truy cập hợp lệ.

### 9.4. Reflection bị từ chối

Dùng `targetType.getModule()` để xác định module chứa class, tiếp tục kiểm tra `isOpen(pkg, caller)` cho đúng package và module gọi. Nếu package không open, cần thiết kế API/public access phù hợp hoặc khai báo opens có chủ đích; tránh coi `setAccessible(true)` là giải pháp luôn thành công.

### 9.5. Class nằm trong module nhưng không có layer

Một named module mới được tạo qua cơ chế runtime và chưa được gán vào layer có thể có `getLayer() == null`. Vì vậy, khi viết chẩn đoán, dùng `isNamed()` để quyết định named/unnamed, rồi coi layer là thuộc tính bổ sung.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xem xét | Cách kiểm tra |
| --- | --- | --- |
| `getName()` trả `null` | Class đang thuộc unnamed module. | Gọi `isNamed()`, xem lệnh chạy `-cp`/`--module-path`. |
| `getDescriptor()` là `null` | Unnamed module không có descriptor. | Kiểm tra `isNamed()` trước khi truy cập descriptor. |
| Class mong đợi module X nhưng kết quả khác | Class được nạp từ classpath, loader khác hoặc layer khác. | In `type.getModule()`, loader và layer; xem cách khởi chạy. |
| `Class.forName` ném `ClassNotFoundException` | Loader không nhìn thấy class hoặc module chưa được resolve/cấu hình. | Kiểm tra class loader, module resolution và đường dẫn đã cung cấp. |
| `IllegalAccessError` hoặc lỗi truy cập khi liên kết | Readability/exports/visibility không đáp ứng yêu cầu. | Kiểm tra `canRead`, `isExported` và quyền truy cập của class/member. |
| `InaccessibleObjectException` khi deep reflection | Package chưa được open phù hợp hoặc quyền truy cập bị hạn chế. | Kiểm tra `isOpen` và khai báo `opens`/tùy chọn runtime liên quan. |
| Tên class trùng nhưng kết quả module khác | Nhiều loader/layer định nghĩa các class riêng. | So sánh `Class<?>`, module, layer và loader thay vì chỉ so tên chuỗi. |

## 11. Bài tập thực hành

1. Chạy `ModuleInspector` ở mục 4. Dự đoán kết quả của `String.class`, `int.class` và `ModuleInspector[].class` trước khi quan sát.
2. Biên dịch ví dụ `com.example.modulecheck`. Chạy lần lượt bằng `--module-path ... -m ...` và `-cp ...`, giải thích vì sao `Main.class.getModule()` thay đổi.
3. Trong chương trình named module, in `module.getDescriptor().requires()` và `module.getLayer()`. So sánh với unnamed module.
4. Tạo module `com.example.library` có package public được `exports`. Viết module `com.example.client` với `requires com.example.library;`. Từ client, kiểm tra `canRead` và `isExported(pkg, clientModule)` cho package thư viện.
5. Trong bài 4, thử thêm một package internal không export/open. Giải thích khác biệt giữa việc compiler không cho import public type của package internal và reflection không thể mở thành viên private.
6. Nếu có thư viện chạy trên classpath và module path, quan sát `isNamed()`, `getDescriptor()` và `getName()` cho class thư viện ở cả hai chế độ.

Gợi ý câu hỏi tự kiểm tra: `Class.getModule()` có trả `null` không? `Module.getName()` khi nào trả `null`? Class trên classpath khác gì class trong named module? Vì sao `canRead() == true` chưa đủ để deep reflection? Primitive type và array type thuộc module nào?

## 12. Ghi nhớ

`Class.getModule()` trả về **module gắn với class đang tồn tại ở runtime**. Đối với named module, dùng `isNamed()` và `getName()` để biết tên. Đối với unnamed module, `getName()` là `null` và `getDescriptor()` cũng là `null`. `String.class`, primitive type và những mảng có phần tử thuộc JDK có thể trả `java.base`, còn class ứng dụng trên classpath thường thuộc unnamed module.

Để đánh giá khả năng truy cập giữa module, tiếp tục xét `canRead`, `isExported` và `isOpen`. Để xử lý khác biệt giữa môi trường khởi chạy, quan sát thêm layer và class loader. Quan trọng nhất, **module của class được xác định bởi cách class được nạp**, không đơn thuần từ tên package hay vị trí JAR trên ổ đĩa.
