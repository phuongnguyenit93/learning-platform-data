# Access tới JDK internal API

Java Development Kit (JDK) không chỉ chứa các API công khai được lập trình viên sử dụng, mà còn có nhiều lớp, package và module phục vụ **chi tiết triển khai** của JVM, compiler, thư viện chuẩn và các công cụ JDK. Những thành phần này thường được gọi là *JDK internal API*. Trong hệ thống Java cũ, một số ứng dụng hoặc thư viện có thể đã truy cập chúng trực tiếp; khi chuyển sang Java Platform Module System (JPMS) hoặc nâng cấp JDK, truy cập ấy có thể bị chặn.

Trọng tâm của bài học là phân biệt **module readability**, **package exports** và **opens cho reflection** khi truy cập thành phần nội bộ của JDK; hiểu vì sao các tùy chọn `--add-exports` và `--add-opens` có thể giải quyết một lỗi cụ thể nhưng không biến internal API thành API được hỗ trợ ổn định.

## 1. JDK internal API là gì?

Internal API là những lớp, method, field hoặc package được JDK dùng cho công việc triển khai bên trong, thay vì làm hợp đồng API ổn định cho ứng dụng bên ngoài. Chúng có thể liên quan đến:

- Cơ chế quản lý bộ nhớ, class loading và runtime metadata.
- Reflection, method handles, xử lý bytecode hoặc compiler internals.
- Các thuật toán và cấu trúc dữ liệu phục vụ thư viện chuẩn.
- Hạ tầng bảo mật, định dạng chứng thư và giao tiếp JVM.
- Tối ưu hóa cấp thấp được quyền thay đổi giữa các bản JDK.

Các tên package như `jdk.internal.*`, `sun.*` và một số `com.sun.*` thường là dấu hiệu cần kiểm tra. Tuy nhiên, **không nên kết luận chỉ dựa trên tiền tố**. Chẳng hạn, có những API JDK-specific được tài liệu hóa, và cũng có những API thuộc `com.sun.*` được công bố trong phạm vi hỗ trợ nhất định. Hãy kiểm tra tài liệu chính thức và module descriptor của phiên bản JDK đang dùng.

Có thể phân biệt ba mức:

| Loại API | Ví dụ | Cần hiểu |
|---|---|---|
| Java SE API công khai | `java.util.List`, `java.nio.ByteBuffer` | Được đặc tả và có cam kết tương thích theo nền tảng Java |
| API JDK-specific được tài liệu hóa | Một số API trong `jdk.jfr`, `jdk.httpserver` | Có tài liệu và chính sách hỗ trợ của JDK, nhưng không nhất thiết thuộc Java SE |
| JDK internal implementation API | `jdk.internal.misc.*`, nhiều kiểu trong `sun.security.*` | Chi tiết triển khai, không nên coi là hợp đồng ổn định |

Điểm quan trọng là: **“Có thể nhìn thấy một class trong JDK” không đồng nghĩa “Ứng dụng được khuyến nghị sử dụng class đó.”**

## 2. Vì sao ứng dụng cũ từng truy cập được internal API?

Trước Java 9, nhiều ứng dụng chạy trên classpath. Các package nội bộ của JDK đôi khi vẫn có thể được import hoặc truy cập bằng reflection, dù không được hỗ trợ như API công khai. Một số thư viện tận dụng điều này để:

- Gọi `sun.misc.Unsafe` cho thao tác bộ nhớ cấp thấp.
- Đọc hoặc sửa private field trong lớp JDK.
- Sử dụng lớp xử lý chứng thư, mã hóa hoặc class loader nội bộ.
- Tối ưu serialization, object allocation hoặc proxy generation.
- Sử dụng API compiler/runtime không thuộc contract public.

Những kỹ thuật này thường dựa vào **chi tiết hiện hữu của một phiên bản JDK**. Khi JPMS được đưa vào từ Java 9, ranh giới truy cập của các named modules được mô hình hóa rõ ràng. Các bản JDK mới cũng tăng cường đóng gói những package nội bộ.

Vì vậy, ứng dụng có thể gặp lỗi khi:

1. Nâng từ Java 8 lên Java 11, 17 hoặc phiên bản mới hơn.
2. Chuyển một thư viện từ classpath sang module path.
3. Chuyển code từ unnamed module sang explicit named module.
4. Thay đổi JDK vendor, bản cập nhật hoặc runtime image.
5. Chạy framework reflection với ranh giới JPMS chặt hơn.

## 3. Module access gồm những cơ chế nào?

JPMS kiểm soát việc truy cập giữa các module theo nhiều lớp, không chỉ qua access modifier `public`.

**Readability:** module tiêu thụ phải đọc được module chứa kiểu cần sử dụng. Quan hệ này thường đến từ `requires` trong `module-info.java`.

**Exports:** package chứa kiểu phải được export cho module tiêu thụ nếu dùng truy cập Java thông thường. Một lớp `public` trong package chưa export vẫn không trở thành public API cho module bên ngoài.

**Opens:** module có thể mở package cho **deep reflection**, như truy cập private field hoặc method qua `setAccessible(true)`.

**Java access control:** kể cả khi module và package cho phép, modifier của class/member (`public`, `protected`, package-private, `private`) vẫn có hiệu lực.

Ví dụ một descriptor:

```java
module com.example.library {
    exports com.example.library.api;

    opens com.example.library.model
        to com.example.serializer;
}
```

Module này export package API cho các module có readability phù hợp, nhưng chỉ mở sâu package model cho module serializer cụ thể.

Một module khác **không thể bỏ qua encapsulation** chỉ bằng cách tìm được tên class, có reference tới `ClassLoader`, hoặc gọi `Class.forName`.

## 4. Vì sao import public class trong JDK vẫn bị chặn?

Giả sử mã muốn dùng một kiểu nằm trong package nội bộ:

```java
import jdk.internal.misc.Unsafe;
```

Kiểu này thuộc package `jdk.internal.misc` bên trong module `java.base`. Mọi named module đều đọc `java.base` ngầm định, nhưng điều đó **không có nghĩa** `java.base` export mọi package cho ứng dụng.

Compiler có thể báo lỗi tương tự:

```text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to the current module)
```

Vấn đề không phải thiếu `requires java.base;`, mà là package nội bộ không được export cho module đang biên dịch.

Đây là ví dụ cho quy tắc:

```text
Có readability tới module
          +
Package được export phù hợp
          +
Kiểu và thành viên truy cập được
          =
Truy cập Java thông thường hợp lệ
```

Thiếu một điều kiện, truy cập có thể bị chặn. Sự tồn tại của file `.class` trên máy không cấp quyền truy cập.

## 5. Strong encapsulation trong JDK hiện đại

JPMS đưa ra cơ chế đóng gói package của các named modules từ Java 9. Trong giai đoạn đầu, nền tảng có những cơ chế tương thích để các ứng dụng cũ còn truy cập được một số thành phần nội bộ bằng reflection.

Các mốc đáng nhớ:

- **Java 9:** JPMS xuất hiện. Nhiều internal packages không được export cho code ứng dụng thông thường; một số trường hợp truy cập reflection cũ được nới lỏng trong giai đoạn migration.
- **Java 16:** strong encapsulation trở thành mặc định rộng hơn theo hướng siết quyền truy cập vào các thành phần nội bộ.
- **Java 17:** JEP 403 tiếp tục tăng cường đóng gói nội bộ JDK. Cơ chế nới lỏng rộng qua `--illegal-access` không còn là phương án khôi phục truy cập theo kiểu trước đây.

Vì vậy, một framework dùng reflection vào `java.lang.String` hoặc các package JDK khác có thể chạy trên môi trường cũ nhưng thất bại trên JDK 17+.

Điều này không phải lỗi ngẫu nhiên của JDK; đó là hệ quả của việc giữ ranh giới API rõ ràng để đội ngũ phát triển JDK có thể thay đổi cách triển khai mà ít làm vỡ ứng dụng sử dụng API được hỗ trợ.

## 6. --add-exports: ngoại lệ cho truy cập API thông thường

Đôi khi một dự án legacy chưa thể loại bỏ ngay import internal API. Tùy chọn `--add-exports` có thể cấp quyền truy cập bổ sung cho một package thuộc module nguồn.

Cú pháp:

```text
--add-exports=<source-module>/<package>=<target-module>
```

Trong đó:

- `source-module`: module đang sở hữu package, ví dụ `java.base`.
- `package`: package nội bộ cần truy cập, ví dụ `jdk.internal.misc`.
- `target-module`: module được phép truy cập, ví dụ `com.example.internaldemo`.

Đối với code trên classpath, target đặc biệt là `ALL-UNNAMED`, có nghĩa cấp quyền cho các unnamed modules.

**Quan trọng:** `--add-exports` mở quyền truy cập tới các kiểu và thành viên đủ điều kiện theo access modifiers thông thường, nhưng **không tự cấp quyền truy cập private member bằng deep reflection**.

### 6.1. Ví dụ named module

Tạo cấu trúc:

```text
internal-demo/
└── src/
    ├── module-info.java
    └── com/example/internaldemo/Main.java
```

`module-info.java`:

```java
module com.example.internaldemo {
}
```

`Main.java`:

```java
package com.example.internaldemo;

import jdk.internal.misc.Unsafe;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Unsafe.class.getName());
    }
}
```

Đoạn code **chỉ minh họa quy tắc truy cập**, không sử dụng primitive bộ nhớ không an toàn. Không nên lấy ví dụ này làm dependency production.

Thử biên dịch bình thường:

```shell
javac -d out src/module-info.java     src/com/example/internaldemo/Main.java
```

Với JDK có strong encapsulation, compiler sẽ chặn import do package chưa export.

Nếu dự án buộc phải có ngoại lệ để migration, có thể biên dịch với:

```shell
javac --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -d out     src/module-info.java     src/com/example/internaldemo/Main.java
```

Chạy với ngoại lệ tương ứng:

```shell
java --module-path out     --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -m com.example.internaldemo/com.example.internaldemo.Main
```

Kết quả kỳ vọng trong các JDK có kiểu này:

```text
jdk.internal.misc.Unsafe
```

Nếu chỉ mở exports ở compile time mà không cấp tương ứng ở runtime, bytecode có thể vẫn bị chặn khi cố truy cập class hoặc member trong package đó. Cả môi trường build và launcher cần được kiểm soát rõ ràng.

Lưu ý: internal API có thể thay đổi hoặc bị bỏ theo phiên bản JDK; ví dụ này không phải cam kết rằng class và member cụ thể luôn có mặt trong mọi JDK tương lai.

### 6.2. Ví dụ code trên classpath

Một ứng dụng chưa có `module-info.java` thường chạy trong unnamed module. Có thể thấy cách dùng:

```shell
javac --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED     -d out src/com/example/internaldemo/Main.java
```

Và:

```shell
java --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED     --class-path out     com.example.internaldemo.Main
```

`ALL-UNNAMED` mở package cho các unnamed modules, **không** đồng nghĩa với mọi named module. Nếu chuyển sang named module, cần chỉ rõ tên target module phù hợp.

## 7. --add-opens: ngoại lệ dành cho deep reflection

Lỗi access khác thường gặp là reflection vào thành viên không public. Ví dụ:

```java
import java.lang.reflect.Field;

public final class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
```

Ở JDK hiện đại, lệnh `setAccessible(true)` có thể ném `InaccessibleObjectException`, bởi package `java.lang` trong `java.base` không được mở cho deep reflection từ module gọi.

Thông báo có thể tương tự:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang"
to unnamed module ...
```

Nếu code cũ bắt buộc cần ngoại lệ tạm thời, có thể cấu hình:

```shell
java --add-opens=java.base/java.lang=ALL-UNNAMED     --class-path out ReflectionDemo
```

Cú pháp tổng quát:

```text
--add-opens=<source-module>/<package>=<target-module>
```

`--add-opens` dành cho **runtime deep reflection**; nó không tự khiến một `import jdk.internal.misc.Unsafe;` hợp lệ ở compile time. Không dùng `--add-opens` thay cho `--add-exports` khi lỗi thuộc truy cập Java thông thường.

Đối với named module, chỉ rõ tên module cần reflection:

```shell
java --add-opens=java.base/java.lang=com.example.reflector     --module-path mods     -m com.example.reflector/com.example.reflector.Main
```

Không nên mở các package JDK rộng rãi trong production chỉ vì một framework cũ còn phụ thuộc vào private fields. Cách bền vững là nâng framework hoặc sửa thiết kế để dùng public API.

## 8. Phân biệt requires, add-reads, add-exports và add-opens

Đây là một trong những điểm dễ nhầm khi sửa lỗi module access.

| Cơ chế | Thay đổi điều gì? | Không làm được điều gì? |
|---|---|---|
| `requires` | Khai báo module dependency/readability | Không export package nội bộ của module khác |
| `--add-reads` | Bổ sung readability vào một lần build/chạy | Không mở quyền truy cập package chưa export |
| `exports` | Module sở hữu công khai package theo descriptor | Không tự cấp deep reflection vào private members |
| `--add-exports` | Bổ sung exports cho target module | Không tự mở deep reflection |
| `opens` | Module sở hữu mở package cho reflection | Không phải hợp đồng API public |
| `--add-opens` | Mở package cho deep reflection ở runtime | Không làm package trở thành exported API ở compile time |

Ví dụ:

- Lỗi “module X does not read module Y”: xem `requires` hoặc `--add-reads`.
- Lỗi “module Y does not export package P to X”: xem `exports` hoặc ngoại lệ `--add-exports`.
- Lỗi “module Y does not opens package P to X”: xem `opens` hoặc `--add-opens`.
- Lỗi `NoClassDefFoundError` vì class đã bị loại bỏ: thêm quyền access không thể tự khôi phục class không còn trong JDK.

**Flags mở access không thay thế nhau.** Việc thêm nhiều flags “để thử” mà không đọc thông báo lỗi có thể làm tăng quyền truy cập không cần thiết và che giấu dependency nội bộ.

## 9. Khi nào cần --add-exports ở cả javac và java?

Nếu source code import trực tiếp một class nội bộ không export, compiler cần quyền đọc package để biên dịch. Nếu bytecode sau đó tiếp tục tham chiếu tới class ấy, runtime cũng cần quyền tương ứng để liên kết và thực thi.

Một ví dụ gồm hai bước:

```shell
javac --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -d out src/module-info.java src/com/example/internaldemo/Main.java
```

```shell
java --add-exports=java.base/jdk.internal.misc=com.example.internaldemo     -p out -m com.example.internaldemo/com.example.internaldemo.Main
```

Nếu framework chỉ dùng reflection từ runtime, thường cần `--add-opens` tại runtime chứ không cần `--add-exports` ở compile time.

Trong Maven/Gradle, compiler, test launcher và application launcher có thể sử dụng **các bộ JVM arguments khác nhau**. Đặt một flag vào bước build không có nghĩa nó được tự động truyền tới runtime production. Tương tự, dùng flag trong IDE mà quên CI có thể khiến test chỉ chạy được trên máy lập trình viên.

Một số tổ hợp `javac --release` và việc mở exports cho system modules có thể bị compiler hạn chế; không nên coi các tùy chọn này là tương thích với mọi chế độ cross-compilation. Cần kiểm tra JDK mục tiêu và ưu tiên loại bỏ internal dependency thay vì duy trì build flags vĩnh viễn.

## 10. Internal API và module jdk.unsupported

Một trường hợp cần hiểu riêng là `jdk.unsupported`. Module này được JDK dùng để cung cấp một số API không nằm trong tập Java SE API chuẩn, chủ yếu nhằm tương thích với ứng dụng và thư viện cũ.

Ví dụ nổi tiếng là `sun.misc.Unsafe`. Trong một số JDK, `jdk.unsupported` có exports cho package `sun.misc`, nhờ đó code legacy có thể tiếp tục truy cập kiểu này theo chính sách triển khai.

Có thể kiểm tra:

```shell
java --describe-module jdk.unsupported
```

Nếu ứng dụng thực sự sử dụng một API trong module này, một named module có thể cần khai báo dependency tương ứng:

```java
module com.example.legacy {
    requires jdk.unsupported;
}
```

Nhưng cần phân biệt:

- `jdk.unsupported` cho thấy nhà cung cấp JDK có cơ chế tương thích cho một số API cũ.
- Khả năng import từ package được export **không biến API thành Java SE API công khai**.
- Không nên suy ra rằng `jdk.internal.misc.Unsafe` và `sun.misc.Unsafe` có cùng chính sách access.
- Các class/field/method ở nhóm này vẫn có rủi ro tương thích và cần kế hoạch thay thế.

Nếu module `jdk.unsupported` không có trong runtime image rút gọn, code phụ thuộc vào nó có thể không chạy. Vì vậy, không xem tính sẵn có trên một JDK đầy đủ là bảo đảm cho mọi runtime environment.

## 11. Qualified exports của các JDK modules

Một module JDK có thể export một package cho **một số module JDK khác**, chứ không export cho mọi module.

Ví dụ descriptor khái niệm:

```java
module some.jdk.module {
    exports some.internal.package to another.jdk.module;
}
```

Ở đây `another.jdk.module` có quyền sử dụng public types của package theo ranh giới được định nghĩa, nhưng module ứng dụng tùy ý không có quyền đó.

Có thể dùng:

```shell
java --describe-module java.base
```

để xem descriptor của module nền tảng, bao gồm những directive exports/opens được công bố theo định dạng tool.

Điều này giải thích vì sao một package có thể được dùng trong source code của JDK nhưng ứng dụng không thể import trực tiếp. **JDK internals được chia sẻ giữa các module JDK không phải lời mời cho application code sử dụng.**

## 12. Xác định module sở hữu API nội bộ

Nếu thấy import như:

```java
import sun.security.x509.X500Name;
```

hãy bắt đầu bằng việc xác định package thuộc module nào ở JDK mục tiêu, ví dụ thông qua JDK documentation, `jdeps` hoặc descriptor của module JDK.

Một workflow tổng quát:

1. Ghi lại fully qualified class name.
2. Xác định package, chẳng hạn `sun.security.x509`.
3. Xác định module sở hữu package trên JDK đang chạy.
4. Xem package có được export cho module tiêu thụ không.
5. Kiểm tra loại truy cập: import/static link hay deep reflection.
6. Kiểm tra API đó có được tài liệu hóa/hỗ trợ cho mục đích sử dụng không.
7. Nếu là internal API, ưu tiên giải pháp thay thế trước khi cân nhắc flags.

Không nên suy ra module sở hữu chỉ từ prefix của package. Một số package cũ được di chuyển hoặc thay đổi giữa các phiên bản JDK.

## 13. Phát hiện JDK internal API bằng jdeps

JDK cung cấp công cụ `jdeps` để phân tích dependency trong bytecode. Khi chuyển từ classpath sang module path, một trong các lệnh hữu ích nhất là:

```shell
jdeps --jdk-internals build/libs/application.jar
```

Tùy chọn `--jdk-internals` tập trung vào những phụ thuộc tới API nội bộ JDK mà công cụ có thể nhận diện từ bytecode.

Nếu ứng dụng cần các dependency bên ngoài để phân tích, cung cấp classpath:

```shell
jdeps --jdk-internals     --class-path "libs/*"     build/libs/application.jar
```

Có thể phân tích các dependency sâu hơn:

```shell
jdeps --jdk-internals     --recursive     --class-path "libs/*"     build/classes
```

Kết quả thường giúp xác định:

- Class ứng dụng hoặc thư viện nào phụ thuộc internal API.
- Internal package/class nào đang được dùng.
- Dependency có nằm trong code của mình hay thư viện bên thứ ba.
- Một số gợi ý API thay thế, khi công cụ có thông tin phù hợp.

**Giới hạn:** `jdeps` phân tích bytecode và không thấy đầy đủ việc truy cập tạo ra động từ chuỗi, reflection, JNI, code generation hoặc plugin được nạp trong tương lai. Vì vậy, không có warning từ `jdeps` chưa phải bằng chứng chắc chắn rằng ứng dụng không còn internal dependency.

## 14. Tìm reflection vào thành phần JDK

Reflection có thể làm internal dependency khó nhìn thấy hơn import trực tiếp.

Ví dụ:

```java
Class<?> type = Class.forName("java.lang.String");
var field = type.getDeclaredField("value");
field.setAccessible(true);
```

Một số dấu hiệu cần tìm trong source:

- `Class.forName(...)`.
- `getDeclaredField(...)`, `getDeclaredMethod(...)`, `getDeclaredConstructor(...)`.
- `setAccessible(true)` hoặc `trySetAccessible()`.
- `MethodHandles.privateLookupIn(...)`.
- `Unsafe` hoặc thư viện wrapper quanh memory access cấp thấp.
- Framework serialization/ORM/DI dùng private-field injection.

Đừng chỉ tìm import nội bộ. Một thư viện có thể ghép tên `sun.*` hoặc `jdk.internal.*` từ chuỗi, dùng reflection và không để lộ import tĩnh.

Nếu framework gây lỗi, việc nâng phiên bản framework thường là giải pháp ít rủi ro hơn so với tự thêm `--add-opens` cho nhiều package của JDK.

## 15. Phân biệt các lỗi thường gặp

### 15.1. Compile error: package is not visible

Ví dụ:

```text
package jdk.internal.misc is not visible
```

Nguyên nhân phổ biến: package nằm trong named module nhưng không được export cho module đang biên dịch.

Cần xử lý:

1. Xác định module sở hữu package.
2. Kiểm tra có API public thay thế không.
3. Chỉ khi migration bất khả kháng, cân nhắc `--add-exports` cho đúng target module.
4. Ghi rõ nơi đặt compiler flag và runtime flag.

### 15.2. Runtime IllegalAccessError

Ứng dụng có thể đã biên dịch bằng cấu hình nới access nhưng khi chạy không được cấp quyền tương ứng. Trong lúc liên kết hoặc sử dụng bytecode, JVM có thể ném `IllegalAccessError`.

Kiểm tra **cả lệnh javac và lệnh java thực tế**, đặc biệt khi các lệnh đến từ IDE, CI, Maven Surefire hoặc Gradle.

### 15.3. Runtime InaccessibleObjectException

Thường xuất hiện khi framework dùng deep reflection vào package chưa open:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang"
```

Xem stack trace để biết module nào đang cố reflection; không mặc định target là `ALL-UNNAMED`. Nếu framework chạy trong named module, `--add-opens` có thể cần chỉ định tên module đó.

### 15.4. ClassNotFoundException / NoClassDefFoundError

Class có thể không còn ở JDK mới, bị chuyển vị trí hoặc runtime image không chứa module cần thiết. Trong trường hợp đó, **mở access không khôi phục bytecode thiếu**.

Cần xác định class có thực sự còn trong JDK target không, không chỉ sửa module flags.

### 15.5. NoSuchMethodError / NoSuchFieldError

Đây thường là dấu hiệu binary compatibility: bytecode tham chiếu tới method/field không còn giữ chữ ký mong đợi. Với internal API, rủi ro này cao vì implementation có thể thay đổi.

`--add-exports` hoặc `--add-opens` không sửa được chữ ký đã thay đổi.

## 16. API được hỗ trợ để thay thế internal API

Khi phát hiện dependency nội bộ, hãy tìm API public hoặc API được tài liệu hóa giải quyết **nhu cầu thực sự** thay vì tìm một class có tên gần giống.

| Nhu cầu | API nên xem xét |
|---|---|
| Mã hóa/giải mã Base64 | `java.util.Base64` |
| Thao tác biến nguyên tử và đồng bộ | `java.util.concurrent.atomic` |
| Truy cập biến theo memory ordering phù hợp | `java.lang.invoke.VarHandle` |
| Dữ liệu nhị phân, buffer | `java.nio.ByteBuffer`, NIO |
| Quản lý cleanup cho tài nguyên | `java.lang.ref.Cleaner` |
| Theo dõi stack | `java.lang.StackWalker` |
| Thông tin process | `java.lang.ProcessHandle` |
| Native memory và native calls | Foreign Function & Memory API nếu JDK mục tiêu hỗ trợ |
| Thao tác khóa/bảo mật | Các API Java Security/JCA/JCE và thư viện được hỗ trợ |
| Logging, metrics, JVM monitoring | `java.lang.management`, JFR hoặc API được tài liệu hóa |

Không có quy tắc thay thế một-một cho mọi internal API. Một thư viện từng gọi `Unsafe` để thao tác dữ liệu cấp thấp có thể cần thiết kế lại với `VarHandle`, `ByteBuffer`, các lớp atomic, hoặc một abstraction phù hợp.

Đối với API đã được chuẩn hóa ở JDK mới nhưng không có trong JDK cũ, cần cân nhắc phiên bản Java tối thiểu mà dự án cam kết hỗ trợ.

## 17. Ví dụ migration: bỏ dependency vào bộ mã hóa cũ

Giả sử code cũ dùng một API nội bộ hoặc implementation riêng để thực hiện Base64. Không nên tiếp tục phụ thuộc vào lớp nội bộ chỉ để mã hóa một mảng byte.

Dùng public API:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class Encoder {
    public static String encode(String input) {
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public static String decode(String encoded) {
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
```

Ví dụ test:

```java
String encoded = Encoder.encode("Java JPMS");
System.out.println(encoded);
System.out.println(Encoder.decode(encoded));
```

Ưu điểm:

- Không cần `--add-exports`.
- Không phụ thuộc vào package nội bộ.
- Dễ chạy trong named module vì `java.base` đã được đọc ngầm định.
- Có API và hành vi được tài liệu hóa.

Đây là ví dụ cho phương pháp migration: **thay đúng nhu cầu nghiệp vụ**, không “giữ nguyên cách gọi cũ bằng mọi giá”.

## 18. Khi dependency nội bộ đến từ thư viện bên thứ ba

Nhiều lỗi không nằm trong source code của ứng dụng. Chúng xuất phát từ JSON library, ORM, bytecode manipulation, instrumentation, test framework hoặc thư viện network được chọn từ nhiều năm trước.

Hướng xử lý ưu tiên:

1. Dùng `jdeps --jdk-internals` hoặc stack trace để xác định artifact/class gây phụ thuộc.
2. Kiểm tra phiên bản thư viện và các bản release mới hơn.
3. Đọc release notes và tài liệu Java compatibility của thư viện.
4. Nâng lên phiên bản dùng API được hỗ trợ, nếu có.
5. Chạy test trên JDK mục tiêu, gồm integration tests có reflection.
6. Chỉ giữ `--add-exports`/`--add-opens` như workaround được ghi rõ thời hạn, scope và người chịu trách nhiệm.

Không nên sao chép class nội bộ của JDK vào package của ứng dụng để tránh module system. Việc đó thường tạo rủi ro pháp lý/kỹ thuật, binary compatibility và bảo trì hơn nữa.

## 19. Kiểm tra module access ở runtime

Một số phương thức của `java.lang.Module` giúp chẩn đoán quyền truy cập giữa module.

Ví dụ:

```java
Module base = Object.class.getModule();
Module app = MyApplication.class.getModule();

System.out.println(base.getName());
System.out.println(app.getName());

System.out.println(app.canRead(base));
System.out.println(base.isExported("java.lang", app));
System.out.println(base.isExported("jdk.internal.misc", app));
System.out.println(base.isOpen("java.lang", app));
```

Các kết quả phản ánh configuration và các thay đổi access có hiệu lực tại runtime. Với một ứng dụng thông thường:

- App có thể đọc `java.base`.
- Package `java.lang` được export rộng rãi.
- Package `jdk.internal.misc` không được export rộng rãi như API ứng dụng.
- `java.lang` thường không open cho deep reflection tùy ý trong strong encapsulation.

Nếu launcher truyền `--add-exports` hoặc `--add-opens`, quyền truy cập được cấp có thể thay đổi kết quả tương ứng.

Tuy nhiên, kể cả khi `Module.isExported` trả về `true`, điều đó chỉ trả lời câu hỏi **quyền truy cập module**, không bảo đảm API được hỗ trợ hoặc giữ nguyên trong tương lai.

## 20. Access flags không phải biện pháp bảo mật hay tương thích dài hạn

Cần hiểu hai rủi ro khác nhau:

**Rủi ro tương thích:** internal API có thể đổi tên, đổi chữ ký, thay hành vi hoặc biến mất. Flags không ngăn điều đó.

**Rủi ro mở rộng quyền truy cập:** một option như `--add-opens java.base/java.lang=ALL-UNNAMED` mở package cho mọi unnamed module trong tiến trình. Đây có thể là phạm vi rộng hơn điều một thư viện thực sự cần.

Một số nguyên tắc:

- Dùng tên target module cụ thể thay vì `ALL-UNNAMED` nếu code nằm trong named module.
- Chỉ mở đúng package, không mở hàng loạt package JDK không liên quan.
- Tách compiler flags, test flags và production runtime flags.
- Ghi mục đích mỗi flag trong tài liệu triển khai.
- Có test xác nhận chương trình chạy được sau khi bỏ workaround.
- Xem các flags là nợ kỹ thuật cần loại bỏ, không phải hợp đồng API.

Đặc biệt, **class loader riêng, signed JAR, automatic module hoặc khả năng nạp class bằng reflection không tạo sandbox**. Nếu ứng dụng xử lý mã không tin cậy, cần có mô hình cách ly phù hợp ngoài các tùy chọn truy cập của JPMS.

## 21. Quy trình xử lý lỗi access tới JDK internal API

Khi nâng cấp JDK và thấy lỗi, có thể theo quy trình:

1. **Ghi nhận môi trường:** phiên bản JDK, vendor, lệnh chạy, module path/classpath, build tool.
2. **Chụp stack trace hoặc compiler message:** lấy đầy đủ module nguồn, package và target module.
3. **Xác định API gây lỗi:** import trực tiếp, bytecode liên kết hay reflection.
4. **Kiểm tra module sở hữu:** dùng `java --describe-module <module>` và thông tin JDK mục tiêu.
5. **Quét dependency:** chạy `jdeps --jdk-internals` trên artifact của ứng dụng và những thư viện có liên quan.
6. **Tìm API thay thế:** ưu tiên Java SE API hoặc API JDK được tài liệu hóa.
7. **Nâng thư viện:** nếu dependency nội bộ đến từ thư viện bên thứ ba.
8. **Dùng workaround giới hạn nếu cần:** chỉ định đúng `--add-exports` hoặc `--add-opens`, phân biệt compile/runtime.
9. **Kiểm thử nhiều tầng:** unit test, integration test, reflection/serialization/ServiceLoader, startup và packaging.
10. **Loại bỏ workaround:** khi code hoặc thư viện không còn phụ thuộc internal API.

Ví dụ bảng theo dõi:

| Thành phần | Internal API | Loại truy cập | Workaround tạm thời | Hướng loại bỏ |
|---|---|---|---|---|
| Legacy serializer | Package nội bộ JDK | Reflection | `--add-opens` có phạm vi | Nâng thư viện |
| Runtime helper cũ | `jdk.internal.misc` | Import/linkage | `--add-exports` có phạm vi | Chuyển sang public API |
| Code cấp thấp | `sun.misc.Unsafe` | Direct API | Phụ thuộc `jdk.unsupported` | Refactor bằng `VarHandle` hoặc API khác |

Không nên dùng một workaround “cho toàn bộ JDK” mà thiếu danh sách dependency và kế hoạch migration.

## 22. Checklist trước khi phát hành

- [ ] Đã kiểm tra tất cả JAR liên quan bằng `jdeps --jdk-internals`.
- [ ] Đã tìm các reflection calls và tên class dạng chuỗi có thể bị `jdeps` bỏ sót.
- [ ] Đã xác định chính xác module/package/target bị access failure.
- [ ] Đã phân biệt cần `requires`, `exports` hay `opens`.
- [ ] Đã ưu tiên API công khai thay cho internal API.
- [ ] Đã nâng thư viện bên thứ ba nếu có bản tương thích.
- [ ] Các `--add-exports` và `--add-opens` còn lại đều có lý do và phạm vi rõ.
- [ ] Compiler, test runtime, CI và production không dùng cấu hình mâu thuẫn.
- [ ] Đã kiểm thử trên đúng JDK target và runtime image được phân phối.
- [ ] Có kế hoạch loại bỏ các cờ migration trong những bản phát hành tiếp theo.

## Kết luận

**Access tới JDK internal API** là trường hợp đặc biệt của module access: một class có thể tồn tại trong JDK và thậm chí mang modifier `public`, nhưng package của nó không được export cho ứng dụng. Tương tự, reflection vào private fields trong package JDK có thể bị từ chối nếu package không open.

`--add-exports` bổ sung quyền truy cập Java thông thường tới một package, còn `--add-opens` mở quyền deep reflection tại runtime. Chúng là công cụ tương thích có phạm vi, **không phải** cách biến internal API thành API ổn định. Những thay đổi mạnh về encapsulation từ Java 9 đến Java 17 khiến các dependency nội bộ vốn chạy được trước đây dễ lộ lỗi khi nâng cấp.

Cách giải quyết bền vững là kiểm kê bằng `jdeps`, đọc rõ stack trace và module descriptor, nâng các thư viện đã được sửa, rồi chuyển sang API Java/JDK được tài liệu hóa. Khi một ngoại lệ access vẫn chưa thể bỏ, hãy giữ nó tối thiểu, nhất quán giữa build và runtime, đồng thời có kế hoạch xóa bỏ trong quá trình migration.