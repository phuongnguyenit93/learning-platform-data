# Lookup.defineClass và ranh giới package

`MethodHandles.Lookup.defineClass(byte[])` được bổ sung trong Java 9 để định nghĩa một class thông thường từ bytecode đã có. Class mới được định nghĩa bằng **class loader, runtime package và protection domain của lookup class**. Đây là điểm làm cho API hữu ích khi tạo class cần tham gia cùng package với class hiện tại, bao gồm quyền truy cập các kiểu và thành viên có package access.

Ranh giới package là điều kiện bắt buộc của API: class file truyền vào phải khai báo tên class thuộc cùng package với lookup class, và lookup phải có quyền `PACKAGE`. `defineClass()` không phải API để tùy ý chọn package, class loader hoặc protection domain. Nếu bytecode thuộc package khác, lời gọi bị từ chối.

## Mục tiêu

- Hiểu vai trò của `MethodHandles.Lookup` trong việc định nghĩa class.
- Dùng `Lookup.defineClass(byte[])` với class file hợp lệ.
- Hiểu ranh giới giữa package name, runtime package và class loader.
- Nắm quyền `PACKAGE` cần thiết của lookup.
- Biết cách tạo lookup phù hợp trong cùng package hoặc qua `privateLookupIn()` khi module cho phép.
- Phân biệt `defineClass()`, `findClass()` và `ClassLoader.defineClass()`.
- Xử lý lỗi bytecode, sai package, thiếu quyền và định nghĩa trùng tên.
- Hiểu thời điểm class initializer chạy và cách quản lý lookup như một capability.

## 1. Lookup là gì?

`MethodHandles.Lookup` là đối tượng đại diện cho ngữ cảnh truy cập của một class. Nó được dùng để tạo method handle, VarHandle và thực hiện một số thao tác class-loading có kiểm tra quyền.

`MethodHandles.lookup()` là phương thức caller-sensitive: lookup class được xác định theo class đã gọi phương thức này. Lookup được tạo ngay bên trong một class thường có các quyền tương ứng với những truy cập mà class đó có thể thực hiện bằng bytecode, bao gồm package access và private access của chính class.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass().getName());
System.out.println(lookup.lookupModes());
~~~

`lookupClass()` cho biết class làm gốc cho quyền truy cập. `lookupModes()` trả bit mask các quyền hiện có, trong đó `MethodHandles.Lookup.PACKAGE` là quyền quan trọng đối với `defineClass()`.

Không nên lấy một lookup từ thư viện tiện ích rồi giả định nó đại diện cho package của class gọi thư viện. Nếu helper gọi `MethodHandles.lookup()` bên trong chính helper, lookup class là helper đó. Khi cần định nghĩa class trong package của caller, hãy để caller tạo lookup và truyền lookup đó cho thành phần được tin cậy.

## 2. Lookup.defineClass(byte[]) làm gì?

API:

~~~java
public Class<?> defineClass(byte[] bytes) throws IllegalAccessException
~~~

Phương thức nhận byte array chứa class file hợp lệ, định nghĩa class và trả về `Class<?>` tương ứng. Theo hợp đồng Java SE 9, class mới được định nghĩa với:

- Cùng class loader với lookup class.
- Cùng runtime package với lookup class.
- Cùng protection domain với lookup class.

Class name trong bytecode phải thuộc cùng package với lookup class. Ví dụ lookup class là `com.example.runtime.PluginHost`, class file hợp lệ có thể là `com.example.runtime.GeneratedPlugin`. Class file có tên `com.example.other.GeneratedPlugin` bị từ chối.

~~~java
byte[] classBytes = Files.readAllBytes(Paths.get("GeneratedPlugin.class"));
Class<?> generated = lookup.defineClass(classBytes);
~~~

Phương thức trả về một class đã được định nghĩa. Nó không tự gọi constructor và cũng không chạy class initializer tại thời điểm `defineClass()` trả về.

## 3. Package name và runtime package

Trong mã Java, package được khai báo ở đầu source file:

~~~java
package com.example.runtime;
~~~

Tên package trong class file phải khớp với package của lookup class. Tuy nhiên, khi xét quyền truy cập ở runtime, chỉ có cùng chuỗi package name là chưa đủ trong mọi tình huống: class loader cũng tham gia xác định runtime package.

Ví dụ hai class cùng khai báo `package com.example.runtime;` nhưng được định nghĩa bởi hai class loader khác nhau không tự động thuộc cùng runtime package. Vì vậy, package-private class hoặc member của class loader này không trở thành accessible đối với class cùng tên package do loader khác định nghĩa.

`Lookup.defineClass()` xử lý ranh giới này bằng cách luôn dùng class loader của lookup class. Class được định nghĩa sẽ tham gia runtime package tương ứng với lookup class, thay vì tạo một loader mới.

### 3.1. Vì sao cùng runtime package quan trọng?

Java có bốn mức truy cập thường gặp:

| Modifier | Phạm vi truy cập khái quát |
| --- | --- |
| `public` | Các nơi được phép truy cập kiểu theo module/accessibility rules |
| `protected` | Cùng package hoặc subclass theo quy tắc Java |
| Không ghi modifier (package-private) | Các class thuộc cùng runtime package |
| `private` | Bên trong class khai báo và các ngữ cảnh được Java cho phép như nestmates |

`defineClass()` hữu ích khi class được tạo cần gọi package-private class hoặc method hiện có. Nếu định nghĩa class bằng một class loader khác, chỉ việc dùng cùng package name không đủ để có package access.

### 3.2. Protection domain

Protection domain là một phần ngữ cảnh bảo mật gắn với class. `Lookup.defineClass()` dùng protection domain của lookup class; caller không truyền một protection domain khác vào phương thức này.

Vì thế, API phù hợp khi class mới cần được định nghĩa cùng ngữ cảnh loader/package/protection domain của class đang cấp lookup. Nếu cần một loader riêng hoặc protection domain riêng, hãy chọn cơ chế class loading được thiết kế cho mục tiêu đó.

## 4. Quyền PACKAGE của lookup

`defineClass()` yêu cầu lookup có `PACKAGE` access. Quyền này chứng thực rằng lookup được tạo bởi code trong runtime package tương ứng, hoặc được dẫn xuất từ một lookup đủ quyền tới class trong package đó.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean canDefineInPackage =
    (lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0;

if (!canDefineInPackage) {
    throw new IllegalAccessException("Lookup has no PACKAGE access");
}
~~~

Lookup được tạo bằng `MethodHandles.lookup()` bên trong class phù hợp thường có PACKAGE access. Ngược lại, `MethodHandles.publicLookup()` chỉ có quyền public/unconditional tối thiểu, không đủ để định nghĩa class bằng `defineClass()`.

### 4.1. Lookup.in() không nâng quyền

`lookup.in(SomeClass.class)` tạo lookup mới với lookup class khác. Phương thức này không thể cấp thêm quyền so với lookup ban đầu. Nếu class đích thuộc package khác, quyền `PACKAGE` và `PROTECTED` bị loại bỏ.

~~~java
MethodHandles.Lookup narrowed = lookup.in(OtherPackageType.class);
~~~

Không dùng `Lookup.in()` như cách vượt qua ranh giới package. Một lookup đã mất PACKAGE access không thể tự khôi phục quyền đó bằng cách tiếp tục gọi `in()`.

### 4.2. privateLookupIn() trong Java 9

Java 9 bổ sung `MethodHandles.privateLookupIn(targetClass, callerLookup)` để tạo lookup có ngữ cảnh của class đích khi caller được phép truy cập sâu vào class đó.

~~~java
MethodHandles.Lookup targetLookup = MethodHandles.privateLookupIn(
    TargetType.class,
    MethodHandles.lookup()
);

Class<?> generated = targetLookup.defineClass(targetBytes);
~~~

Bytecode truyền vào vẫn phải khai báo class trong package của `TargetType`, và `targetLookup` phải giữ PACKAGE access.

Với hai class thuộc các named module khác nhau, các điều kiện truy cập của `privateLookupIn()` bao gồm:

- Module của caller phải đọc được module chứa class đích.
- Module đích phải mở package chứa class đích cho module caller.
- Lookup của caller phải có MODULE access.

Nếu điều kiện module không thỏa, `privateLookupIn()` ném `IllegalAccessException`. `privateLookupIn()` không phải cách bỏ qua module boundary; nó yêu cầu module khai báo quyền mở package theo quy tắc của Java Platform Module System.

## 5. Byte array phải là class file hợp lệ

`defineClass()` không nhận Java source code. Nó nhận bytecode của một class hoặc interface hợp lệ theo định dạng class file của JVM.

Byte array thường đến từ:

- Class file đã được biên dịch bởi `javac`.
- Bytecode do một thư viện sinh mã tạo ra.
- Một công cụ biến đổi class file rồi xuất byte array.
- Một hệ thống build/plugin đã tạo class file trước đó.

Trước khi gọi API, cần bảo đảm:

1. Byte array không null và chứa một class file hợp lệ.
2. Class name trong class file thuộc đúng package của lookup class.
3. Class version và bytecode tương thích với runtime đang chạy.
4. Các superclass, interface, field type và dependency cần thiết có thể được resolve bởi class loader tương ứng.
5. Class name chưa được định nghĩa trước đó trong cùng namespace của class loader.

Đổi tên file `.class` trên đĩa không thay đổi binary name nằm trong bytecode. Ranh giới package được kiểm tra dựa trên tên class trong class file, không dựa trên tên đường dẫn file truyền vào `Files.readAllBytes()`.

## 6. Định nghĩa class không đồng nghĩa khởi tạo class

`Lookup.defineClass()` định nghĩa class nhưng không chạy class initializer (`<clinit>`). Static initializer chỉ chạy khi có thao tác active use theo quy tắc khởi tạo class của JVM.

Ví dụ:

~~~java
Class<?> generated = lookup.defineClass(bytes);

// Class đã được định nghĩa; static initializer chưa nhất thiết chạy.
Object instance = generated.getDeclaredConstructor().newInstance();
~~~

Việc tạo instance qua constructor là một thao tác có thể kích hoạt khởi tạo class. Các thao tác đọc/ghi static field hoặc gọi static method cũng có thể kích hoạt khởi tạo theo quy tắc JVM.

Đừng đặt side effect quan trọng vào static initializer với giả định nó chạy ngay khi `defineClass()` được gọi. Nếu cần khởi tạo, thực hiện một active use có chủ đích sau khi định nghĩa.

## 7. Các lỗi có thể gặp

| Tình huống | Kết quả thường gặp | Cách xử lý |
| --- | --- | --- |
| Lookup không có PACKAGE access | `IllegalAccessException` | Tạo lookup từ code đủ quyền trong package hoặc dùng `privateLookupIn()` khi module cho phép |
| Bytecode thuộc package khác | `IllegalArgumentException` | Sinh/biên dịch class vào package của lookup class |
| Byte array null | `NullPointerException` | Kiểm tra nguồn bytecode trước khi gọi |
| Bytecode sai định dạng | `ClassFormatError` hoặc lỗi linkage tương ứng | Kiểm tra bytecode generator và class-file version |
| Bytecode không qua verifier | `VerifyError` | Sửa bytecode để thỏa quy tắc verifier của JVM |
| Tên class đã được định nghĩa trong loader đó | `LinkageError` | Tránh định nghĩa trùng binary name; dùng tên duy nhất hoặc loader khác nếu thiết kế yêu cầu |
| Dependency không resolve được | Lỗi linkage khi resolve hoặc sử dụng class | Bảo đảm dependency có thể được tìm thấy bởi loader phù hợp |
| Dùng `publicLookup()` | Không có PACKAGE access | Dùng lookup có quyền phù hợp từ package đích |
| Dùng `lookup.in()` sang package khác | PACKAGE access bị mất | Không dùng `in()` để nâng quyền; tạo lookup đúng ngữ cảnh |
| Module không mở package cho caller | `privateLookupIn()` thất bại bằng `IllegalAccessException` | Cấu hình module readability/opens theo đúng nhu cầu |

Không bắt mọi `LinkageError` rồi tiếp tục như thể class đã được định nghĩa thành công. Các lỗi format, verify, duplicate definition hoặc dependency thường cho biết bytecode hay môi trường class loading đang sai.

## 8. So sánh defineClass(), findClass() và ClassLoader.defineClass()

Ba API có mục đích khác nhau:

| API | Mục đích | Loader/package |
| --- | --- | --- |
| `Lookup.defineClass(bytes)` | Định nghĩa class từ bytecode | Cùng loader, runtime package và protection domain của lookup class |
| `Lookup.findClass(name)` | Tìm và load class đã có theo ngữ cảnh lookup | Dùng loader/ngữ cảnh truy cập của lookup; không nhận byte array để định nghĩa |
| `ClassLoader.defineClass(...)` | Định nghĩa class trong một class loader | Do class loader triển khai quyết định; phù hợp khi cần namespace/loader riêng |

`findClass()` không phải biến thể khác của `defineClass()`: nó tìm class theo tên và thực hiện access check, còn `defineClass()` nhận bytecode mới.

Nếu mục tiêu là tạo class nằm cạnh class hiện tại về runtime package và quyền truy cập package-private, `Lookup.defineClass()` thể hiện đúng ý định. Nếu cần một class loader độc lập, một namespace riêng hoặc protection domain khác, hãy thiết kế một class loader phù hợp thay vì cố dùng `Lookup.defineClass()` ngoài ranh giới của nó.

## 9. Ví dụ hoàn chỉnh chạy trên Java 9

Ví dụ có ba source file:

- `LookupDefineClassDemo.java` nằm trong package `demo.lookup` và tạo lookup.
- `GeneratedGreeting.java` cũng thuộc `demo.lookup`; method của nó gọi package-private class `PackagePeer`.
- `OtherGreeting.java` thuộc package `demo.other` để kiểm tra ranh giới package.

Chương trình đọc bytecode của hai class đã biên dịch. Nó định nghĩa `GeneratedGreeting` bằng lookup của `LookupDefineClassDemo`, tạo object và gọi method. Sau đó, nó thử định nghĩa bytecode của `OtherGreeting` và xác nhận API từ chối class thuộc package khác.

### 9.1. LookupDefineClassDemo.java

~~~java
package demo.lookup;

import java.lang.invoke.MethodHandles;
import java.nio.file.Files;
import java.nio.file.Paths;

public class LookupDefineClassDemo {
    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        byte[] samePackageBytes = Files.readAllBytes(Paths.get(args[0]));
        Class<?> defined = lookup.defineClass(samePackageBytes);
        Object instance = defined.getDeclaredConstructor().newInstance();
        Object message = defined.getMethod("message").invoke(instance);

        System.out.println("message: " + message);
        System.out.println("package: " + defined.getPackage().getName());
        System.out.println("same loader: "
            + (defined.getClassLoader() == LookupDefineClassDemo.class.getClassLoader()));
        System.out.println("same protection domain: "
            + defined.getProtectionDomain().equals(
                LookupDefineClassDemo.class.getProtectionDomain()));

        byte[] otherPackageBytes = Files.readAllBytes(Paths.get(args[1]));
        try {
            lookup.defineClass(otherPackageBytes);
            throw new AssertionError("A class from another package was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("other package rejected: "
                + expected.getClass().getSimpleName());
        }
    }
}

class PackagePeer {
    static String marker() {
        return "package-private access works";
    }
}
~~~

### 9.2. GeneratedGreeting.java

~~~java
package demo.lookup;

public class GeneratedGreeting {
    public String message() {
        return PackagePeer.marker();
    }
}
~~~

### 9.3. OtherGreeting.java

~~~java
package demo.other;

public class OtherGreeting {
    public String message() {
        return "other package";
    }
}
~~~

Biên dịch từ thư mục chứa ba source file:

~~~text
javac --release 9 -d out LookupDefineClassDemo.java GeneratedGreeting.java OtherGreeting.java
~~~

Chạy:

~~~text
java -cp out demo.lookup.LookupDefineClassDemo out/demo/lookup/GeneratedGreeting.class out/demo/other/OtherGreeting.class
~~~

Output:

~~~text
message: package-private access works
package: demo.lookup
same loader: true
same protection domain: true
other package rejected: IllegalArgumentException
~~~

### 9.4. Giải thích kết quả

1. `MethodHandles.lookup()` được gọi từ `LookupDefineClassDemo`, nên lookup class là `demo.lookup.LookupDefineClassDemo`.
2. Bytecode `GeneratedGreeting` khai báo package `demo.lookup`, trùng package với lookup class.
3. `lookup.defineClass()` định nghĩa class bằng loader và protection domain của lookup class.
4. `GeneratedGreeting.message()` gọi được `PackagePeer.marker()`, dù `PackagePeer` không phải public, vì hai class thuộc cùng runtime package.
5. `getClassLoader()` và `getProtectionDomain()` xác nhận class mới dùng cùng loader và protection domain với lookup class.
6. `OtherGreeting` khai báo package `demo.other`; khi truyền bytecode này cho lookup trong `demo.lookup`, API ném `IllegalArgumentException`.

Ví dụ chỉ đọc bytecode của `GeneratedGreeting` và `OtherGreeting`; nó không load `GeneratedGreeting` trước khi gọi `defineClass()`. Nếu class cùng binary name đã được định nghĩa trong loader đó, lần định nghĩa tiếp theo sẽ gặp `LinkageError`.

## 10. Quản lý lookup như một capability

`Lookup` không chỉ là một object tiện ích. Nó đại diện cho quyền truy cập của lookup class. Một lookup đủ quyền có thể tạo method handle cho thành viên private và có thể định nghĩa class trong runtime package nếu có PACKAGE access.

Vì vậy:

- Chỉ tạo lookup từ class có đúng quyền cần thiết.
- Không để lookup đầy đủ quyền lọt vào nơi code không tin cậy có thể lấy được.
- Nếu cần chia sẻ lookup, chỉ chia sẻ cho thành phần đáng tin và hiểu rõ quyền mà nó được trao.
- Không dùng `publicLookup()` rồi kỳ vọng nó có quyền package/private.
- Không coi `Lookup.in()` là cơ chế nâng quyền.

Quyền được giữ trong lookup xuất phát từ class đã tạo nó; code nhận lookup không thể tự biến một lookup hạn chế thành lookup có quyền cao hơn.

## 11. Quy tắc thực hành

1. Tạo lookup từ class trong package nơi class mới cần được định nghĩa.
2. Kiểm tra lookup có `MethodHandles.Lookup.PACKAGE` access.
3. Sinh bytecode với binary package name khớp package của lookup class.
4. Nhớ class mới dùng class loader, runtime package và protection domain của lookup class.
5. Dùng `privateLookupIn()` khi cần lookup của class đích và module rules cho phép.
6. Không dùng `Lookup.in()` để cố vượt ranh giới package hoặc khôi phục quyền đã mất.
7. Kiểm tra class-file version, verifier và dependencies trước khi định nghĩa class.
8. Tránh định nghĩa trùng binary name trong cùng class loader.
9. Nhớ `defineClass()` không chạy static initializer và không gọi constructor.
10. Giữ lookup có quyền cao trong phạm vi code tin cậy.
11. Dùng `findClass()` khi cần tìm class đã tồn tại theo lookup context.
12. Dùng custom class loader khi cần namespace, loader hoặc protection domain riêng.

## 12. Tự kiểm tra

- `Lookup.defineClass()` nhận gì? Byte array chứa class file hợp lệ.
- Class mới dùng class loader nào? Class loader của lookup class.
- Class mới thuộc package nào? Runtime package của lookup class; binary package trong class file phải khớp.
- Quyền lookup nào là bắt buộc? `PACKAGE`.
- Bytecode thuộc package khác gây lỗi gì? `IllegalArgumentException`.
- Lookup thiếu PACKAGE access gây lỗi gì? `IllegalAccessException`.
- `Lookup.in()` có thể nâng quyền không? Không; nó chỉ giữ hoặc làm giảm quyền.
- Khi nào dùng `privateLookupIn()`? Khi cần lookup trong ngữ cảnh class đích và điều kiện module/access cho phép.
- `defineClass()` có chạy static initializer ngay không? Không.
- Hai class cùng package name nhưng loader khác nhau có cùng runtime package không? Không.
- `Lookup.defineClass()` có cho chọn protection domain khác không? Không; dùng protection domain của lookup class.
- Nếu class đã được định nghĩa trong cùng loader thì sao? Có thể nhận `LinkageError` do định nghĩa trùng.

## Tài liệu API Java SE 9

- [MethodHandles.Lookup — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.Lookup.html)
- [MethodHandles.privateLookupIn — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/lang/invoke/MethodHandles.html)

Điểm cốt lõi: **`Lookup.defineClass()` định nghĩa bytecode trong runtime package của lookup class và yêu cầu PACKAGE access.** Class file phải thuộc đúng package; class mới dùng cùng loader và protection domain, nhờ đó có thể tham gia quyền truy cập package-private của runtime package đó.