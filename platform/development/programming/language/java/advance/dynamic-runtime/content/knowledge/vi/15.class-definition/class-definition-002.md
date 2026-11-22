# 15.2 `Lookup.defineClass` và quan hệ với package, bộ nạp lớp, module của lookup class

`MethodHandles.Lookup.defineClass(byte[] bytes)` (Java 9+) dùng một `Lookup` đã có quyền phù hợp để **định nghĩa và liên kết một class hoặc interface từ bytecode**, theo **ngữ cảnh của lookup class**. API này không nhận tham số `ClassLoader` hoặc `Module` tùy ý: lớp được định nghĩa sẽ thuộc **cùng defining class loader, cùng runtime package và cùng protection domain** với `lookup.lookupClass()`. Trong Java có module system (JPMS), kết quả cũng nằm trong **module tương ứng của lookup class**. Bytecode phải khai báo một tên class/interface nằm trong **cùng package** với lookup class, và `lookup.lookupModes()` phải có bit `PACKAGE`.

Điểm cốt lõi: **class bytes cung cấp định nghĩa lớp, còn `Lookup` cung cấp ngữ cảnh có quyền để đặt lớp đó vào runtime**. Việc ghi một `package` bất kỳ trong file `.java` hoặc đặt một `.class` ở thư mục bất kỳ **không** làm `defineClass` chuyển lớp sang package/module/class loader mới theo ý muốn.

Bài học thuộc nhóm **15. Định nghĩa lớp**, tập trung vào câu hỏi: tại sao `Lookup.defineClass` lại ràng buộc package, defining loader và module của `lookup class`, cùng cách dùng API này hợp lệ, có thể kiểm chứng bằng Java 17+.

Sau khi học, bạn có thể:

- Diễn giải chính xác hợp đồng của `Lookup.defineClass(byte[])` và các quyền `Lookup.PACKAGE`.
- Phân biệt **tên package trong bytecode** với **runtime package**, class identity, class loader và module.
- Hiểu `MethodHandles.lookup()`, `publicLookup()`, `dropLookupMode`, `Lookup.in`, `privateLookupIn` liên quan thế nào tới quyền định nghĩa lớp.
- Chứng minh lớp mới cùng loader/package/module/protection domain với lookup class, kể cả với **named module**.
- Giải thích `defineClass` **không chạy static initializer**; tạo class và khởi tạo class là hai giai đoạn khác nhau.
- Phân tích lỗi sai package, thiếu PACKAGE mode, duplicate definition, bytecode không hợp lệ và class-loading conflicts.
- Hiểu trường hợp ngoại lệ có chủ đích: `privateLookupIn` có thể tạo lookup trong package/module đích **khi JPMS cho phép**, không phải vượt qua JPMS.
- So sánh `Lookup.defineClass`, `ClassLoader.defineClass` và `Lookup.defineHiddenClass`; chọn API phù hợp.
- Chạy ba ví dụ độc lập: classpath, một named module và hai named modules có `opens`.

## 1. Hợp đồng chính xác của `Lookup.defineClass`

API:

```java
public Class<?> defineClass(byte[] bytes)
        throws IllegalAccessException
```

`bytes` phải là nội dung của **một class file hợp lệ** theo Java Virtual Machine Specification. Method định nghĩa và liên kết class/interface từ bytecode và trả về đối tượng `Class<?>` của lớp vừa được định nghĩa.

Có bốn ràng buộc cần kiểm tra cùng nhau:

| Thành phần | Nguồn quyết định | Yêu cầu / kết quả |
| --- | --- | --- |
| **Tên package trong bytecode** | `this_class` của class file | Phải cùng package name với `lookup.lookupClass()` |
| **Defining class loader** | `lookup.lookupClass().getClassLoader()` | Lớp mới được định nghĩa bởi **cùng loader** |
| **Runtime package và module** | Ngữ cảnh runtime của lookup class | Cùng runtime package và cùng module tương ứng; không chuyển lớp sang module khác tùy ý |
| **Protection domain** | `lookup.lookupClass().getProtectionDomain()` | Lớp mới dùng **cùng protection domain** theo hợp đồng API |
| **Quyền tạo** | `lookup.lookupModes()` | Phải có `MethodHandles.Lookup.PACKAGE` |
| **Khởi tạo (`<clinit>`)** | Quy tắc initialization của JVM | `defineClass` **không chạy static initializer** |

Hãy xem `Lookup` như một **capability** gắn với một vị trí và một tập quyền. Từ cùng `byte[]`, lời gọi `lookupA.defineClass(bytes)` và `lookupB.defineClass(bytes)` **không tương đương** nếu lookup classes khác loader, package, module hoặc quyền truy cập.

### 1.1. Công thức tư duy

```text
Class file bytes
    - binary class name: p.q.Generated
    - methods, fields, superclass, interfaces, attributes
                   |
                   v
        Lookup.defineClass(bytes)
                   |
        +----------+-----------+
        |                      |
    Lookup identity        Lookup permissions
    - lookupClass()        - PACKAGE required
    - its class loader     - restricted modes matter
    - its runtime package
    - its module
    - its protection domain
                   |
                   v
    Defined class with same context
    (not an arbitrary new loader/module/package)
```

Nếu bytes ghi `p.q.Generated` nhưng `lookup.lookupClass()` nằm ở package `x.y`, method **không** định nghĩa lớp vào `p.q` rồi “tự sửa lookup”: nó từ chối bằng `IllegalArgumentException` do sai package.

Nếu bytes ghi đúng package nhưng lookup thiếu `PACKAGE`, kết quả là `IllegalAccessException`. Hai lỗi khác nhau: **ràng buộc package của lớp đích** khác **quyền của người yêu cầu**.

### 1.2. API không chọn package qua một tham số

Chữ ký chỉ có `byte[]`; không có `String packageName`, `ClassLoader loader` hay `Module destination`. Đó là điểm khác biệt rõ với các API tùy biến class loading.

Ví dụ minh họa:

```java
// Trong class package demo.app:
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> c = lookup.defineClass(bytes);
```

Trong ví dụ này `c` phải được định nghĩa ở package `demo.app`, nếu thành công. Việc người gọi nhận một `byte[]` từ thư mục `other`, HTTP hay database **không** đổi điều kiện: chỉ nội dung class file và lookup context quyết định. Đoạn code là minh họa, cần imports, biến `bytes` và xử lý checked exceptions.

## 2. `lookupClass()` không nhất thiết là “class chứa dòng source” mãi mãi

`MethodHandles.lookup()` là caller-sensitive factory tạo lookup có quyền theo **class gọi nó**. Trong một method của `demo.app.Host`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass()); // class demo.app.Host
```

Một lookup có thể được **chuyển/giới hạn** bằng API khác như `lookup.in(SomeClass.class)` hoặc `MethodHandles.privateLookupIn(SomeClass.class, lookup)`. Sau đó `lookup.lookupClass()` có thể đổi, và quyền cũng có thể bị giảm hoặc được cấp theo điều kiện. Khi dùng `defineClass`, điều quan trọng là **lookup class thực sự của đối tượng Lookup tại thời điểm gọi**, không phải class nơi đang cầm biến lookup trong source.

Một ví dụ khái niệm:

```java
// Hai dòng minh họa, giả sử hostLookup đã tạo trong Host:
Class<?> effectiveContext = hostLookup.lookupClass();
int modes = hostLookup.lookupModes();
```

Nếu đối tượng lookup được truyền qua framework, plugin hoặc helper, bạn không thể suy ra nơi lớp mới sẽ nằm chỉ bằng cách nhìn helper class. Cần xác định `effectiveContext`, defining loader, package, module và `modes`.

### 2.1. Tại sao `Lookup.PACKAGE` bắt buộc?

Lớp mới được định nghĩa trong cùng runtime package với lookup class. Như vậy, nó có thể sử dụng những **package-private members** mà Java cho phép các lớp cùng runtime package truy cập. Nếu API cho phép một lookup chỉ có `PUBLIC` tạo class vào package mà nó không có quyền, caller có thể sinh một lớp mới để truy cập các thành viên package-private ngoài ý muốn.

Bit `PACKAGE` đóng vai trò xác nhận lookup đến từ hoặc được chuyển giao hợp lệ tới ngữ cảnh có quyền package access. Đây là **quy tắc access control**, không phải đơn thuần một cờ để tăng hiệu năng.

Kiểm tra:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean hasPackageAccess =
        (lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0;
```

Đoạn minh họa có imports thích hợp. Dùng phép `&` để kiểm tra bit; không mặc định mọi `Lookup` đều có đầy đủ modes.

### 2.2. `publicLookup()` không đủ

`MethodHandles.publicLookup()` chủ yếu phục vụ tra cứu public members theo các giới hạn Java module/export. Nó **không có `PACKAGE` access**, nên không thể dùng để định nghĩa class bằng `defineClass`:

```java
// Minh họa có bytes class file hợp lệ:
MethodHandles.publicLookup().defineClass(bytes);
// IllegalAccessException
```

Không nên khắc phục bằng cách đổi class được định nghĩa thành `public`. `public` là modifier của class; `PACKAGE` ở đây là **quyền của Lookup**, hai chuyện khác nhau.

### 2.3. `dropLookupMode(PACKAGE)` làm mất quyền

`Lookup.dropLookupMode` tạo lookup bị giới hạn quyền. Nếu bỏ `PACKAGE`, không thể tiếp tục dùng nó để `defineClass` trong package cũ:

```java
MethodHandles.Lookup restricted =
        lookup.dropLookupMode(MethodHandles.Lookup.PACKAGE);
restricted.defineClass(bytes); // IllegalAccessException
```

Đoạn minh họa giả sử có `lookup` và `bytes`. Khi bỏ `PACKAGE`, những mode phụ thuộc có thể cũng bị loại theo quy tắc Lookup; không nên coi API là “chỉ thay một bit tùy ý” mà bỏ qua cấu trúc quyền. Đây là ví dụ rõ ràng cho việc **lookup class vẫn có thể giữ nguyên nhưng khả năng định nghĩa lớp đã mất**.

## 3. Runtime package khác một chuỗi `package` đơn thuần

Trong source Java:

```java
package demo.app;
```

đây là tên package ở mức ngôn ngữ. Ở runtime, class identity và quan hệ package còn liên quan tới **defining class loader** và module. Hai class cùng có chuỗi tên package nhưng do **hai class loaders khác nhau** định nghĩa không mặc nhiên được coi là cùng một runtime package để truy cập package-private members.

Hãy phân biệt:

- **Binary name:** ví dụ `demo.app.Generated`, được mã hóa vào `this_class` của class file.
- **Defining loader:** `ClassLoader` thực sự định nghĩa class, không nhất thiết giống nơi file bytes đang được lưu trên đĩa.
- **Module:** `Class.getModule()` cho biết module runtime sở hữu class đó.
- **Runtime package:** quan hệ package ở runtime gắn với class identity/module/loader, không thể tự tạo bằng việc đặt hai files chung thư mục.
- **Protection domain:** đối tượng mô tả ngữ cảnh bảo vệ của class; `Lookup.defineClass` dùng domain của lookup class.

Vì thế, “đặt class file vào cùng package folder” chưa đủ để đảm bảo class được định nghĩa vào đúng nơi. Thư mục chỉ là cách tổ chức **đầu vào**; `Lookup` và class-loading context quyết định vị trí **đầu ra runtime**.

### 3.1. Class identity: tên và loader

JVM định danh class không chỉ bằng chuỗi `Class.getName()`, mà còn bởi **defining loader**. Hai lớp có cùng binary name nhưng được định nghĩa bởi **hai class loaders khác nhau** là hai classes khác nhau; không thể tự cast qua lại như cùng một kiểu.

Ngược lại, trong **cùng một defining loader**, định nghĩa lần thứ hai **cùng binary name** thường dẫn đến `LinkageError` do duplicate class definition. `Lookup.defineClass` **không phải** cơ chế reload cùng class name in-place. Muốn version mới trong loader tương tự, cân nhắc một tên class mới hoặc class loader đời mới theo kiến trúc đã thiết kế; không tái định nghĩa bytecode vào cùng tên/loader bằng cách gọi lại API.

### 3.2. Cùng defining loader không có nghĩa là bytes phải nằm trên classpath

`defineClass(bytes)` nhận nội dung `byte[]` do caller cung cấp. Bytes có thể do compiler chạy trước, một generator hoặc một nguồn dữ liệu khác tạo ra. Không cần đặt `Generated.class` trên runtime classpath để lookup có thể định nghĩa nó; chỉ cần bytes hợp lệ và các phụ thuộc của class có thể được giải quyết trong class-loading context tương ứng.

Ví dụ trong bài sẽ cố ý để `Generated.class` **ngoài runtime classpath**, nhưng đọc bytes qua `Files.readAllBytes` rồi định nghĩa bằng lookup của class trên runtime classpath. Điều này cho thấy **nơi lưu bytes** và **defining loader của class kết quả** là hai khái niệm độc lập.

### 3.3. Cùng loader không tự động tạo một module mới

Trong ứng dụng classpath bình thường, lookup class thường nằm trong một **unnamed module** của loader đó, và class mới cũng thuộc unnamed module ấy. Với named module, lookup class nằm trong một **named module** đã được tạo bởi module system; `defineClass` thêm class vào **module của lookup class**, không tạo module mới.

Một named module không tự xuất hiện chỉ vì bytes khai báo một package mới, và `defineClass` không phải API đọc `module-info.class` để tạo module tùy ý. Muốn tạo module/layer mới có lifecycle độc lập, dùng thiết kế module layer, loaders và các APIs phù hợp riêng.

## 4. Định nghĩa và khởi tạo: hai bước khác nhau

Đặc tả nói `Lookup.defineClass` **tạo và liên kết class**, nhưng **không chạy class initializer** `<clinit>`. Đây là một khác biệt quan trọng khi debug:

```text
đọc .class bytes
      |
      v
lookup.defineClass(bytes)
      |
      +--> Class<?> đã tồn tại
      +--> verification / linking theo JVM
      +--> static initializer CHƯA tự chạy chỉ vì defineClass
      |
      v
một active use của class
      |
      +--> JVM initialization (nếu chưa chạy)
      +--> chạy static initializer / static field initializers
      |
      v
thực thi logic được gọi
```

Một class có static block:

```java
static {
    System.out.println("Generated.<clinit>");
}
```

sẽ **không** in dòng này chỉ do `lookup.defineClass(bytes)`; nhưng gọi một static method lần đầu qua `MethodHandle` hoặc reflection có thể khiến JVM initialize class trước khi chạy method.

Cần phân biệt:

- **Load/define:** tạo đối tượng runtime biểu diễn class, đặt class trong loader và module phù hợp.
- **Link:** verification, preparation và các bước resolution theo JVMS; một số symbolic references có thể được resolve lười.
- **Initialize:** thực thi `<clinit>` theo quy tắc active use.

`defineClass` không đảm bảo mọi dependency sẽ được resolve và mọi lỗi sẽ xuất hiện ngay trong lời gọi này: một số lỗi linkage hoặc initialization có thể xuất hiện ở lúc sử dụng class. Nó cũng **không** gọi constructor hay tạo một object instance của class mới.

## 5. Ví dụ hoàn chỉnh 1 — classpath, cùng package, loader, module, domain

Ví dụ đầu tiên dùng ba file Java: một class chủ `LookupDefineClassDemo`, một class muốn định nghĩa `Generated` và một class cố ý **sai package** `WrongPackage`.

Sau biên dịch, chương trình chỉ đưa `LookupDefineClassDemo.class` và `PackagePeer.class` vào runtime classpath; class `Generated` được nạp từ byte array. Class `PackagePeer` có method **package-private** để chứng minh lớp mới được định nghĩa đúng runtime package và có thể truy cập hợp lệ.

### 5.1. Cấu trúc thư mục trước khi chạy

```text
src/
  sample/dynamic/
    LookupDefineClassDemo.java
    Generated.java
  other/
    WrongPackage.java

build/       # compiler output; chứa tất cả classes
runtime/     # classpath khi chạy; chỉ chứa host và PackagePeer
```

### 5.2. File `src/sample/dynamic/LookupDefineClassDemo.java`

```java
package sample.dynamic;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class LookupDefineClassDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        byte[] otherPackage = Files.readAllBytes(Path.of(args[1]));

        System.out.println("lookup class: " + lookup.lookupClass().getSimpleName());
        System.out.println("PACKAGE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));

        Class<?> generated = lookup.defineClass(bytes);
        System.out.println("defined name: " + generated.getName());
        System.out.println("same loader: "
                + (generated.getClassLoader() == lookup.lookupClass().getClassLoader()));
        System.out.println("same runtime package: "
                + generated.getPackageName().equals(lookup.lookupClass().getPackageName()));
        System.out.println("same module: "
                + (generated.getModule() == lookup.lookupClass().getModule()));
        System.out.println("module named: " + generated.getModule().isNamed());
        System.out.println("same protection domain: "
                + (generated.getProtectionDomain()
                == lookup.lookupClass().getProtectionDomain()));
        System.out.println("class defined but not initialized");

        MethodHandle mh = lookup.findStatic(
                generated, "message", MethodType.methodType(String.class));
        System.out.println("message: " + (String) mh.invokeExact());

        try {
            lookup.defineClass(otherPackage);
        } catch (IllegalArgumentException e) {
            System.out.println("other package: IllegalArgumentException");
        }

        try {
            lookup.dropLookupMode(MethodHandles.Lookup.PACKAGE)
                    .defineClass(otherPackage);
        } catch (IllegalAccessException e) {
            System.out.println("without PACKAGE: IllegalAccessException");
        }

        try {
            MethodHandles.publicLookup().defineClass(bytes);
        } catch (IllegalAccessException e) {
            System.out.println("public lookup: IllegalAccessException");
        }

        try {
            lookup.defineClass(bytes);
        } catch (LinkageError e) {
            System.out.println("duplicate definition: "
                    + e.getClass().getSimpleName());
        }
    }
}

class PackagePeer {
    static String secret() {
        return "same-runtime-package";
    }
}
```

### 5.3. File `src/sample/dynamic/Generated.java`

```java
package sample.dynamic;

public class Generated {
    static {
        System.out.println("Generated.<clinit>");
    }

    public static String message() {
        return PackagePeer.secret();
    }
}
```

`PackagePeer.secret()` có package-private access. `Generated.message()` có thể gọi nó khi **được định nghĩa trong cùng runtime package** với `PackagePeer`, không chỉ vì hai files cùng tên package theo source code.

### 5.4. File `src/other/WrongPackage.java`

```java
package other;

public class WrongPackage {}
```

File này có bytes hoàn toàn hợp lệ nhưng khai báo package `other`, khác `sample.dynamic` của lookup class. `lookup.defineClass` với những bytes ấy sẽ ném `IllegalArgumentException` — đây là bài test ràng buộc package, không phải bài test lỗi class file.

### 5.5. Biên dịch và chuẩn bị runtime (shell Bash)

Chạy từ thư mục chứa `src`:

```bash
javac --release 17 -d build \
  src/sample/dynamic/LookupDefineClassDemo.java \
  src/sample/dynamic/Generated.java \
  src/other/WrongPackage.java

mkdir -p runtime/sample/dynamic
cp build/sample/dynamic/LookupDefineClassDemo.class runtime/sample/dynamic/
cp build/sample/dynamic/PackagePeer.class runtime/sample/dynamic/

java -cp runtime sample.dynamic.LookupDefineClassDemo \
  build/sample/dynamic/Generated.class \
  build/other/WrongPackage.class
```

Chú ý: runtime classpath **chỉ có thư mục `runtime`**, không có `build`. `Generated.class` được truyền dưới dạng **đường dẫn để đọc bytes**, không nằm trong classpath. Không đưa `Generated.class` vào `runtime` trước khi chạy: ví dụ muốn kiểm soát chính xác thời điểm class được định nghĩa bằng `lookup.defineClass`.

Nếu chạy trong **PowerShell trên Windows**, thay lệnh `mkdir -p`/`cp` bằng:

```powershell
New-Item -ItemType Directory -Force runtime/sample/dynamic
Copy-Item build/sample/dynamic/LookupDefineClassDemo.class runtime/sample/dynamic/
Copy-Item build/sample/dynamic/PackagePeer.class runtime/sample/dynamic/
java -cp runtime sample.dynamic.LookupDefineClassDemo build/sample/dynamic/Generated.class build/other/WrongPackage.class
```

Ba dòng PowerShell chỉ thay phần chuẩn bị/call runtime; lệnh `javac --release 17 -d build ...` vẫn dùng tương tự, nhưng viết trên một dòng hoặc tiếp dòng theo cú pháp PowerShell riêng.

### 5.6. Stdout đã kiểm chứng

```text
lookup class: LookupDefineClassDemo
PACKAGE mode: true
defined name: sample.dynamic.Generated
same loader: true
same runtime package: true
same module: true
module named: false
same protection domain: true
class defined but not initialized
Generated.<clinit>
message: same-runtime-package
other package: IllegalArgumentException
without PACKAGE: IllegalAccessException
public lookup: IllegalAccessException
duplicate definition: LinkageError
```

### 5.7. Phân tích kết quả

1. `MethodHandles.lookup()` được gọi trong `LookupDefineClassDemo`, nên `lookup.lookupClass()` là chính class này. Lookup có `PACKAGE`.
2. `defineClass(bytes)` thành công vì `Generated` cũng khai báo `package sample.dynamic`, và caller có quyền package.
3. Class mới có **cùng defining loader** và **cùng runtime package** với lookup class. Kết quả thử nghiệm cũng xác nhận **cùng module** và **cùng protection domain**.
4. `module named: false` là do chương trình chạy trên **classpath**, nơi class của ứng dụng thuộc unnamed module tương ứng.
5. Chuỗi `class defined but not initialized` xuất hiện **trước** `Generated.<clinit>`. Khi chuẩn bị gọi static method `message`, JVM mới chạy class initializer, sau đó in kết quả.
6. `Generated.message()` gọi `PackagePeer.secret()` thành công, chứng minh quan hệ package-private khi được định nghĩa trong đúng runtime package.
7. Bytes của `other.WrongPackage` có package khác nên `IllegalArgumentException`.
8. `dropLookupMode(PACKAGE)` khiến lookup không còn quyền định nghĩa lớp; `publicLookup()` cũng không có quyền ấy. Cả hai ném `IllegalAccessException` trong ví dụ.
9. `defineClass(bytes)` **lần hai** với cùng binary name và defining loader ném `LinkageError`, không định nghĩa đè class đã có.

Đừng dùng một kết quả `Class.getPackageName().equals(...)` **đơn lẻ** làm bằng chứng hai classes có cùng runtime package. Ở ví dụ, kết luận dựa trên **cùng package name + cùng defining loader + cùng module** và hợp đồng chính thức của `defineClass`.

## 6. Những lỗi thường gặp của `defineClass`

Theo Java 17 API, các trường hợp chính:

| Exception/Error | Giai đoạn/nguồn | Ví dụ nguyên nhân |
| --- | --- | --- |
| `IllegalAccessException` | Kiểm tra quyền của `Lookup` | `Lookup` thiếu `PACKAGE` |
| `IllegalArgumentException` | Kiểm tra tính hợp lệ của class type/package | Bytes mô tả class ở **package khác**, hoặc không phải class/interface được chấp nhận (ví dụ `ACC_MODULE`) |
| `ClassFormatError` | Phân tích cấu trúc class file | Bytes không phải cấu trúc classfile hợp lệ |
| `VerifyError` | Verification | Bytecode không đáp ứng các quy tắc verifier |
| `LinkageError` | Liên kết/class definition | Duplicate binary name trong cùng defining loader, hoặc lỗi linking khác |
| `NullPointerException` | Dữ liệu đầu vào | Truyền `null` thay vì `byte[]` |
| `SecurityException` | Security Manager legacy (nếu hiện diện) | Security Manager từ chối quyền được yêu cầu trong điều kiện được API quy định |
| `ExceptionInInitializerError` | **Sau đó**, khi lớp được initialize | Static initializer của lớp mới ném lỗi |

Hai sắc thái quan trọng:

- `defineClass` **không** nhận checked `ClassNotFoundException` cho chính tên lớp mới, vì caller đang cung cấp bytecode để định nghĩa. Nhưng class mới có thể cần các dependencies; lỗi khi giải quyết superclass, interface, method signatures hoặc các symbolic references có thể xảy ra khi định nghĩa/liên kết hoặc sử dụng, tùy hoàn cảnh.
- `ClassFormatError`, `VerifyError` và `LinkageError` là **`Error`**, không phải checked `Exception`. Catch `Exception` không đảm bảo bắt được chúng. Code production nên xác định boundary xử lý/giới hạn việc nhận bytecode không đáng tin, tránh nuốt các Error rồi chạy tiếp với trạng thái không rõ.

### 6.1. Khi thiếu PACKAGE, lỗi khác package thế nào?

Hai nguyên nhân độc lập:

```text
Lookup có PACKAGE?          no  -> IllegalAccessException
         |
        yes
         |
Bytes cùng package?         no  -> IllegalArgumentException
         |
        yes
         |
Class file và linking hợp lệ? no -> ClassFormatError/VerifyError/LinkageError...
         |
        yes
         |
     Class<?> result
```

Đây là **mô hình chẩn đoán**, không khẳng định JVM bắt buộc thực hiện tất cả phép kiểm tra theo thứ tự mô phỏng đó trong mọi trường hợp. Trọng tâm là **phân biệt loại lỗi** và việc không “sửa” `IllegalAccessException` bằng cách đổi bytes mà không hiểu lookup modes.

### 6.2. Duplicate definition không phải reloading

Nếu loader đã định nghĩa `sample.dynamic.Generated`, gọi lại `lookup.defineClass(bytes)` với cùng name/loader có thể ném `LinkageError`. Thay bytes thành phiên bản code khác **không** cho phép tái định nghĩa class đó trong cùng loader bằng `defineClass`.

Để chạy hai phiên bản cùng binary name, một kỹ thuật là dùng **hai defining class loaders khác nhau** với ranh giới cách ly cụ thể, nhưng khi đó class identity khác nhau; phải quản lý interfaces/serialization/casts/module layers đúng cách. Những cơ chế như Instrumentation class redefinition cũng là API khác, không phải thao tác `Lookup.defineClass`.

## 7. Module của lookup class: unnamed và named

Đối với Java 9+ module system, `Class.getModule()` là phép kiểm chứng trực tiếp class thuộc module nào.

### 7.1. Trên classpath: unnamed module

Ở ví dụ đầu, `LookupDefineClassDemo` chạy từ `runtime` trên classpath. `Generated` định nghĩa qua lookup của Host vì vậy thuộc **cùng unnamed module**. Kết quả:

```text
same module: true
module named: false
```

Điều này **không** biến tất cả classpath classes thành một module toàn cục duy nhất: unnamed module gắn với class loader. Với các class loaders khác nhau, các unnamed modules/không gian class khác nhau có thể cùng tồn tại.

### 7.2. Trong named module: không phải tự thêm `module-info` vào bytes

Nếu lookup class ở named module `m.runtime`, class mới định nghĩa từ bytes cùng package và loader sẽ nằm trong **`m.runtime`**. Nó **không** trở thành một unnamed-module class chỉ vì bytes được đọc từ đường dẫn ngoài module path.

Để chứng minh, ví dụ thứ hai sẽ có một named module không `exports` package; Host và Generated vẫn có thể tương tác qua package-private class vì ở **cùng runtime package trong cùng module**. Public export ra bên ngoài không phải điều kiện để code **nội bộ** module định nghĩa class bằng lookup có PACKAGE access.

### 7.3. `exports` khác `opens`

- `exports p.foo;` hoặc `exports p.foo to m.bar;` chủ yếu cho **truy cập public types/members ở compile/link time** từ các modules khác.
- `opens p.foo;` hoặc `opens p.foo to m.bar;` cho phép **deep reflection / private lookup** theo đúng đối tượng được cấp quyền, trong những điều kiện JPMS tương ứng.
- Nếu chỉ cần `MethodHandles.lookup()` ngay trong một package của chính module, không cần mở package đó ra bên ngoài để dùng `defineClass` vào **chính package/module**.
- Nếu code ở module A muốn lấy **private lookup của class trong module B**, phải thỏa điều kiện của `privateLookupIn`, bao gồm quyền của caller lookup và package đích được mở thích hợp. `exports` đơn thuần không bảo đảm đủ để lấy private access.

**Mấu chốt:** Bạn không có tham số `Module target` trong `defineClass`. Muốn định nghĩa vào module đích theo cách được phép, cần **một Lookup thực sự có lookup class trong package/module đích** và có `PACKAGE` mode. Không thể chỉ ghi package đích vào bytes rồi dùng một lookup bất kỳ từ module khác.

## 8. Ví dụ hoàn chỉnh 2 — định nghĩa class trong một named module

Ta dùng module `m.runtime`, package `sample.runtime`. Class `ModuleGenerated` được biên dịch cùng module để có class bytes hợp lệ, nhưng **không** đặt `ModuleGenerated.class` vào runtime module directory. Chương trình đọc bytes và định nghĩa qua lookup của `ModuleDefineDemo`.

### 8.1. Cấu trúc thư mục

```text
src/
  m.runtime/
    module-info.java
    sample/runtime/
      ModuleDefineDemo.java
      ModuleGenerated.java

build/
  m.runtime/
    module-info.class
    sample/runtime/
      ModuleDefineDemo.class
      PackageAccess.class
      ModuleGenerated.class

runtime/
  m.runtime/
    module-info.class
    sample/runtime/
      ModuleDefineDemo.class
      PackageAccess.class
```

### 8.2. File `src/m.runtime/module-info.java`

```java
module m.runtime {
}
```

Module không khai báo `exports`/`opens` vì lớp chạy chính và lớp mới đều thuộc cùng module. Điều này minh họa rằng **định nghĩa class nội bộ** không đòi mở package ra ngoài.

### 8.3. File `src/m.runtime/sample/runtime/ModuleDefineDemo.java`

```java
package sample.runtime;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class ModuleDefineDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        Class<?> defined = lookup.defineClass(bytes);
        System.out.println("module named: " + defined.getModule().isNamed());
        System.out.println("same module: "
                + (defined.getModule() == ModuleDefineDemo.class.getModule()));
        System.out.println("same loader: "
                + (defined.getClassLoader() == ModuleDefineDemo.class.getClassLoader()));
        System.out.println("same package: "
                + defined.getPackageName().equals(
                ModuleDefineDemo.class.getPackageName()));
        MethodHandle call = lookup.findStatic(
                defined, "read", MethodType.methodType(String.class));
        System.out.println("value: " + (String) call.invokeExact());
    }
}

class PackageAccess {
    static String message() {
        return "named-module-package-access";
    }
}
```

### 8.4. File `src/m.runtime/sample/runtime/ModuleGenerated.java`

```java
package sample.runtime;

public class ModuleGenerated {
    public static String read() {
        return PackageAccess.message();
    }
}
```

### 8.5. Biên dịch và chạy

Chạy từ thư mục chứa `src` trong Bash:

```bash
javac --release 17 \
  -d build \
  --module-source-path src \
  -m m.runtime

mkdir -p runtime/m.runtime/sample/runtime
cp build/m.runtime/module-info.class runtime/m.runtime/
cp build/m.runtime/sample/runtime/ModuleDefineDemo.class runtime/m.runtime/sample/runtime/
cp build/m.runtime/sample/runtime/PackageAccess.class runtime/m.runtime/sample/runtime/

java --module-path runtime \
  --module m.runtime/sample.runtime.ModuleDefineDemo \
  build/m.runtime/sample/runtime/ModuleGenerated.class
```

Với Windows PowerShell, dùng `New-Item -ItemType Directory -Force` và `Copy-Item` tương đương để chuẩn bị các file đúng đường dẫn; lệnh `java --module-path runtime --module m.runtime/sample.runtime.ModuleDefineDemo build/m.runtime/sample/runtime/ModuleGenerated.class` có thể viết trên một dòng.

**Stdout đã kiểm chứng:**

```text
module named: true
same module: true
same loader: true
same package: true
value: named-module-package-access
```

Chương trình chứng minh:

1. `ModuleDefineDemo` thuộc named module `m.runtime`, và lookup được tạo ngay bên trong class ấy.
2. `lookup.defineClass(bytes)` định nghĩa `ModuleGenerated` trong **cùng named module** chứ không phải unnamed module.
3. `getClassLoader()` giống nhau; `getPackageName()` giống nhau.
4. `ModuleGenerated.read()` gọi `PackageAccess.message()` dù method là package-private, vì module/package/loader phù hợp.
5. Module không cần `exports` package ra bên ngoài chỉ để tự định nghĩa class vào package nội bộ của mình.

Một điều quan trọng: `ModuleGenerated.class` tồn tại trong `build` chỉ để đọc bytes; nó được **cố ý không copy vào `runtime`** nhằm tránh việc lớp bị nạp trước và gây duplicate definition.

## 9. `privateLookupIn`: có thể chuyển đúng ngữ cảnh khi module cho phép

Không phải mọi lời gọi `defineClass` đều phải được viết trong source của package đích. Ví dụ framework ở module `m.tool` có thể được **cấp quyền deep access** tới một package trong module `m.target`. Khi đó, `MethodHandles.privateLookupIn(Anchor.class, callerLookup)` có thể trả `Lookup` mới có **lookup class `Anchor` của module đích** và `PACKAGE` access, rồi dùng `defineClass` trên lookup mới.

Quan trọng: đây là **đổi ngữ cảnh Lookup bằng API kiểm soát quyền**, không phải một tham số chọn module tùy ý của `defineClass`. Nếu module đích không mở package phù hợp, hoặc caller lookup thiếu quyền, `privateLookupIn` thất bại; bạn không thể vượt qua chỉ bằng cách truyền bytes.

Ở trường hợp chuyển qua module khác, lookup mới có thể **mất `MODULE` access** mà vẫn giữ **`PACKAGE`** và quyền khác trong phạm vi được phép. Đây là hai bit riêng; `defineClass` yêu cầu `PACKAGE`, **không trực tiếp yêu cầu `MODULE`**.

### 9.1. Ví dụ hoàn chỉnh 3 — hai named modules với `opens` có chủ đích

Cấu trúc file:

```text
src/
  m.tool/
    module-info.java
    tool/CrossModuleDemo.java
  m.target/
    module-info.java
    p/target/Anchor.java
    p/target/GeneratedPlugin.java

build/     # tất cả compiled output
runtime/   # chỉ module-info, tool, Anchor và PackagePeer
```

#### File `src/m.tool/module-info.java`

```java
module m.tool {
    requires m.target;
}
```

#### File `src/m.target/module-info.java`

```java
module m.target {
    opens p.target to m.tool;
}
```

`opens p.target to m.tool` là **quyền có chủ đích** cho module `m.tool`; không công bố package cho toàn bộ modules khác. Đồng thời `m.tool` đọc `m.target` qua `requires`.

#### File `src/m.target/p/target/Anchor.java`

```java
package p.target;

public class Anchor {}

class PackagePeer {
    static String value() {
        return "package-opened";
    }
}
```

#### File `src/m.target/p/target/GeneratedPlugin.java`

```java
package p.target;

public class GeneratedPlugin {
    public static String answer() {
        return PackagePeer.value();
    }
}
```

#### File `src/m.tool/tool/CrossModuleDemo.java`

```java
package tool;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class CrossModuleDemo {
    public static void main(String[] args) throws Throwable {
        Class<?> anchor = Class.forName("p.target.Anchor");
        MethodHandles.Lookup lookup =
                MethodHandles.privateLookupIn(anchor, MethodHandles.lookup());
        System.out.println("lookup class: " + lookup.lookupClass().getName());
        System.out.println("PACKAGE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));
        System.out.println("MODULE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0));

        Class<?> generated = lookup.defineClass(Files.readAllBytes(Path.of(args[0])));
        System.out.println("same target module: "
                + (generated.getModule() == anchor.getModule()));
        System.out.println("same loader: "
                + (generated.getClassLoader() == anchor.getClassLoader()));
        System.out.println("caller module different: "
                + (generated.getModule() != CrossModuleDemo.class.getModule()));

        MethodHandle mh = lookup.findStatic(
                generated, "answer", MethodType.methodType(String.class));
        System.out.println("answer: " + (String) mh.invokeExact());
    }
}
```

### 9.2. Biên dịch và chạy

Từ thư mục chứa `src`, trong Bash:

```bash
javac --release 17 \
  -d build \
  --module-source-path src \
  -m m.tool,m.target

mkdir -p runtime/m.tool/tool
mkdir -p runtime/m.target/p/target

cp build/m.tool/module-info.class runtime/m.tool/
cp build/m.tool/tool/CrossModuleDemo.class runtime/m.tool/tool/

cp build/m.target/module-info.class runtime/m.target/
cp build/m.target/p/target/Anchor.class runtime/m.target/p/target/
cp build/m.target/p/target/PackagePeer.class runtime/m.target/p/target/

java --module-path runtime \
  --module m.tool/tool.CrossModuleDemo \
  build/m.target/p/target/GeneratedPlugin.class
```

Trong PowerShell, thay lệnh `mkdir -p` bằng `New-Item -ItemType Directory -Force` và `cp` bằng `Copy-Item` như ở ví dụ trước. Không copy `GeneratedPlugin.class` vào `runtime` trước khi chạy.

**Stdout đã kiểm chứng:**

```text
lookup class: p.target.Anchor
PACKAGE mode: true
MODULE mode: false
same target module: true
same loader: true
caller module different: true
answer: package-opened
```

### 9.3. Vì sao kết quả trên không mâu thuẫn?

Vị trí của dòng source gọi `defineClass` nằm trong `tool.CrossModuleDemo` của `m.tool`, nhưng đối tượng `lookup` được dùng **không còn** có lookup class `tool.CrossModuleDemo`. `privateLookupIn` đã tạo lookup mới với **lookup class `p.target.Anchor`** trong `m.target`, với `PACKAGE` access được cấp theo điều kiện.

Do vậy, khi `lookup.defineClass(bytes)` chạy:

- Package đích là `p.target`, vì đó là package của `lookup.lookupClass()`.
- Defining loader là loader của `p.target.Anchor`.
- Module của class mới là **`m.target`**, cùng module với `Anchor`, **không** phải module của class đang giữ biến lookup (`m.tool`).
- `MODULE mode: false` minh họa sự hạn chế quyền khi lookup vượt ranh giới module; nhưng `PACKAGE mode: true` vẫn đủ cho `defineClass`.
- Method `GeneratedPlugin.answer()` truy cập được `PackagePeer.value()` vì lớp mới thực sự ở cùng runtime package của `Anchor`/`PackagePeer`.

Nếu bỏ `opens p.target to m.tool` trong `module-info.java` của `m.target` rồi build lại, `privateLookupIn` có thể ném `IllegalAccessException` do package không mở cho `m.tool`. **Không** có fallback mặc định “thử public lookup rồi vẫn định nghĩa class”; đó là sự từ chối truy cập theo JPMS.

### 9.4. Không dùng `Lookup.in` để nâng quyền trái phép

`lookup.in(Other.class)` chuyển lookup class nhưng **không nâng quyền**; nó có thể làm mất `PACKAGE` khi chuyển package và mất `MODULE` khi chuyển module. Nếu bạn đang giữ lookup chỉ có public access trong module A, gọi `in(Anchor.class)` không tự tạo quyền định nghĩa class trong package private của module B.

`privateLookupIn` cũng không vô điều kiện nâng quyền: caller phải có quyền thích hợp (bao gồm `PRIVATE` và `MODULE` trong ngữ cảnh yêu cầu), và JPMS phải cho phép deep access tới package đích. Ví dụ hai modules chỉ thành công nhờ **cấu hình `opens` minh bạch**.

## 10. So sánh `Lookup.defineClass`, `ClassLoader.defineClass` và `defineHiddenClass`

| Tiêu chí | `Lookup.defineClass(bytes)` | `ClassLoader.defineClass(...)` | `Lookup.defineHiddenClass(...)` |
| --- | --- | --- | --- |
| Công việc | Định nghĩa một class/interface **thông thường** từ bytes | Định nghĩa class bằng loader cụ thể | Định nghĩa **hidden class** không có tên binary bình thường để liên kết từ bên ngoài |
| Ai quyết định defining loader? | Loader của **lookup class** | Object `ClassLoader` thực hiện define (theo API/caller) | Gắn với ngữ cảnh lookup, có quy tắc riêng |
| Giới hạn package? | **Phải cùng package** với lookup class | Theo cách loader/module được cấu hình và quy tắc ClassLoader | Hidden class cũng có ràng buộc package với lookup class |
| Đòi PACKAGE mode? | **Có** | Không dùng `Lookup` modes theo cách đó | Đòi **full privilege access**, không chỉ PACKAGE |
| Trả về | `Class<?>` | `Class<?>` | `Lookup` trên hidden class |
| Tên class có thể tham chiếu thông thường? | Có, theo quy tắc của ordinary class | Có, theo quy tắc của ordinary class | Không như một named class thông thường |
| Có tự chạy `<clinit>` khi define? | **Không** | Không tự chạy chỉ vì định nghĩa | API có tham số `initialize` quyết định initialization |
| Đối tượng dùng điển hình | Trusted framework bổ sung class vào đúng package/module hiện có | Hệ thống class loader/plugin isolation có kiến trúc loader riêng | Lambdas/runtime code được sinh làm implementation details, khi hidden semantics phù hợp |

**Đừng nhầm:** `ClassLoader.defineClass` cũng chịu các quy tắc về package/module/protection domain, classfile verification và bảo mật. Nó không phải API “được phép định nghĩa bất cứ class nào vào bất cứ module nào” chỉ vì người viết có thể tạo subclass `ClassLoader`.

### 10.1. Khi nào dùng ordinary defined class?

Dùng `Lookup.defineClass` khi bạn cần một **ordinary, named class** mới trong cùng runtime package/module của lookup class, có thể được dùng theo các quy tắc Java thông thường. Ví dụ framework sinh accessor/helper bytecode để truy cập hợp lệ vào package-private API của chính package tin cậy.

Nếu class mới được định nghĩa với tên public hợp lệ, nó mang binary name bình thường và chịu class identity thông thường. Hãy bảo đảm **không xung đột tên** với class đã tồn tại trong defining loader.

### 10.2. Khi nào dùng hidden class?

`Lookup.defineHiddenClass` phù hợp cho runtime-generated implementation không cần một binary name bình thường để được các lớp khác liên kết trực tiếp. Nó có quy tắc riêng về nest membership, lifetime và initialization; trả về một `Lookup` trên hidden class. Hidden classes không tự trở thành ordinary classes có thể tìm theo tên bằng `Class.forName`.

Không nên dùng `defineClass` chỉ vì muốn làm code “ẩn”; ordinary class và hidden class có hợp đồng khác nhau. Ngược lại, không dùng hidden class khi bạn cần một named public API class để client code tham chiếu như class thông thường.

### 10.3. API này không đồng nghĩa `Class.forName` hoặc reflection

- `Class.forName(name)` tìm/nạp class theo tên trong class-loading context và có thể initialize tùy overload; nó **không** nhận bytes để định nghĩa một class mới.
- `Class.getDeclaredMethod` hay `MethodHandles.lookup().findStatic` dùng để tra member trên **class đã tồn tại**.
- `Lookup.defineClass` nhận bytecode và tạo **class mới** nếu hợp lệ, rồi bạn có thể dùng Reflection/MethodHandle để gọi members của class đó.

Một lỗi thường gặp là định nghĩa class rồi lại gọi `Class.forName` với một loader khác, dẫn tới `ClassNotFoundException` hoặc class identity mismatch. Trong framework, tốt nhất giữ và dùng ngay `Class<?>` mà `defineClass` trả về, hoặc truyền đúng loader/module context đến bước sau.

## 11. Đừng hiểu lầm “cùng package” là cùng nest

Hai class cùng runtime package có thể truy cập các thành viên **package-private**, nhưng điều đó không khiến chúng trở thành **nestmates** để truy cập **private members** của nhau.

Ví dụ:

```java
package sample.dynamic;

class Host {
    private static int secret = 7;
    static int shared = 8;
}
```

Một class khác được định nghĩa cùng package/loader/module có thể truy cập `Host.shared` theo package-private access, nhưng **không tự được phép truy cập `Host.secret`**. Private access cần điều kiện nest membership/access phù hợp và các quy tắc Java khác.

Lưu ý khi tạo classfile động:

- Khai báo `package` giống nhau không tự tạo `NestHost`/`NestMembers` relationships.
- `Lookup.defineClass` không tự gắn class mới vào nest của lookup class.
- `defineHiddenClass` có `ClassOption.NESTMATE` trong những trường hợp cho phép; đó là API/hợp đồng khác, không nên suy rộng sang ordinary `defineClass`.
- Nếu framework cần private access, ưu tiên API chính thức và thiết kế module/access phù hợp, thay vì nghĩ một class mới cùng package có thể đọc mọi private field.

## 12. Tên, loader, module và package: các trường hợp đối chiếu

| Tình huống | Bytes class | Lookup context | Kết quả mong đợi |
| --- | --- | --- | --- |
| Classpath host trong `a.b`; bytes `a.b.Generator`; lookup có PACKAGE | `a.b.Generator` | Unnamed module của Host loader | Định nghĩa trong cùng loader/unnamed module/package |
| Named-module host trong `m.core/a.b`; bytes `a.b.Generator` | `a.b.Generator` | Lookup của Host trong `m.core` | Định nghĩa trong `m.core`, không cần exports package ra ngoài |
| Host trong `a.b`; bytes `x.y.Generator` | `x.y.Generator` | Lookup vẫn ở `a.b` | `IllegalArgumentException` do khác package |
| Host trong `a.b`; bytes `a.b.Generator` | `a.b.Generator` | `publicLookup()` | `IllegalAccessException` do thiếu PACKAGE |
| Host trong `a.b`; bytes `a.b.Generator` | `a.b.Generator` | `lookup.dropLookupMode(PACKAGE)` | `IllegalAccessException` |
| Bytes cùng tên đã define trong cùng loader | `a.b.Generator` | Lookup có quyền | `LinkageError` do duplicate definition |
| Tool module A có private lookup vào class Anchor ở module B, B mở package đúng quyền | `p.b.Generator` | Lookup **của Anchor** trong B, có PACKAGE | Định nghĩa trong module/loader/package của Anchor |
| Tool module A chỉ có public lookup vào class B | `p.b.Generator` | Lookup thiếu PACKAGE | Không được phép defineClass |
| Bytes invalid/corrupt | Không phải classfile hợp lệ | Lookup có quyền | Có thể `ClassFormatError` hoặc verifier/linker errors |

Bảng là hướng dẫn về các trường hợp điển hình; kết quả lỗi cụ thể khi nhiều điều kiện đồng thời sai phụ thuộc vào điều kiện được kiểm tra trước và giai đoạn JVM xử lý. Với test có chủ đích, nên làm từng lỗi **một nguyên nhân** để thông điệp rõ.

## 13. Quyền truy cập và bảo mật

`Lookup.defineClass` là một capability có sức ảnh hưởng lớn: nó tạo class mới **bên trong runtime package của lookup class**, có thể truy cập package-private members theo rules của JVM. Vì vậy:

1. **Không phát tán Lookup có PACKAGE access** tới code không tin cậy nếu việc tạo class trong package ấy không được cho phép.
2. Không nhận bytes từ nguồn không tin cậy rồi define trực tiếp mà thiếu sandbox/process isolation phù hợp. Một classfile hợp lệ có thể chứa static initializer, method bodies hoặc references gây side effects khi được initialize/invoke.
3. Kiểm tra signature, origin, version và policy nếu framework nhận generated bytecode từ bên ngoài. `ClassFormatError`/`VerifyError` chỉ loại được các bytecode **không hợp lệ**; một class hợp lệ vẫn có thể thực hiện hành vi nguy hiểm.
4. Với JPMS, cấp `opens` theo package/module cần thiết. Không mở cả module hoặc dùng các JVM flags cấp deep access tràn lan chỉ để né thiết kế quyền.
5. `ProtectionDomain` của class mới theo **lookup class**; không giả định định nghĩa từ bytes của plugin đồng nghĩa dùng protection domain của một nguồn plugin riêng. Điều này càng quan trọng trong hệ thống có policy hoặc class-loading isolation.
6. Đừng dựa vào Security Manager như sandbox hiện đại: Java Security Manager đã bị deprecated trong các JDK hiện đại. Cần lựa chọn isolation/security architecture phù hợp môi trường runtime thực tế.

Một câu trả lời chính xác cho “làm sao định nghĩa class vào package private của người khác?” là: chỉ khi bạn có **Lookup được trao quyền hợp lệ** cho package đó; nếu không, hãy dùng public API, một SPI hoặc một module/package design cho phép extension một cách chủ đích.

## 14. Class initialization, lỗi trễ và lifecycle

### 14.1. `defineClass` không chạy `<clinit>` nhưng có thể tạo sự kiện linking

Lời gọi `defineClass` có thể phát sinh verification, preparation, linking, loading những types liên quan và các errors tương ứng. Nhưng phương thức này **không chạy static initializer của class mới**. Lúc dùng class lần đầu theo quy tắc initialization, JVM chạy `<clinit>` nếu cần.

Nếu static block ném lỗi, lỗi có thể xuất hiện **sau khi `defineClass` đã trả về thành công**, ví dụ trong lần gọi static method đầu tiên. Đừng kiểm thử thành công chỉ bằng `Class<?> c = lookup.defineClass(bytes)` rồi kết luận “đã khởi tạo, đã gọi được tất cả methods”.

### 14.2. Class mới không tự tạo instance

`Class<?>` trả về là metadata/runtime class object; `defineClass` không gọi constructor. Nếu cần tạo object, phải dùng constructor hợp lệ:

```java
// Đoạn minh họa: dynamicClass là Class<?> đã định nghĩa.
Object instance = dynamicClass.getConstructor().newInstance();
```

Đoạn này chỉ hoạt động khi class có **public no-arg constructor** và caller có quyền truy cập. Các checked/reflection exceptions cũng cần xử lý. Nếu constructor không có hoặc không public, hãy dùng appropriate declared constructor/Lookup và quyền hợp lệ; không suy diễn `defineClass` tự cho quyền gọi constructor.

### 14.3. Ordinary class thường không được unload riêng lẻ

Một ordinary class thường tồn tại chừng nào defining loader và các references liên quan còn reachable theo runtime rules. Bạn không thể “xóa” class riêng rồi định nghĩa lại cùng binary name vào cùng loader chỉ bằng `defineClass`. Muốn quản lý unloadability cho nhiều phiên bản, nên thiết kế class loader lifecycle ngay từ đầu hoặc xem hidden classes nếu phù hợp mục đích.

### 14.4. Race khi hai threads định nghĩa cùng class name

Nếu hai threads cùng cố gắng gọi `defineClass` với bytes có cùng binary name và cùng defining loader, không nên giả định cả hai sẽ thành công rồi JVM trả lại một `Class<?>` duy nhất. Ràng buộc class identity và duplicate definition vẫn áp dụng; một lần định nghĩa có thể thất bại vì class đã được define.

Các thư viện sinh class nên sử dụng **naming strategy**, coordination và cache Class objects theo loader/context để tránh race. Nếu chọn reuse class đã tồn tại, hãy xây API riêng để tìm và kiểm tra class đó theo loader chính xác; `defineClass` không phải `computeIfAbsent` cho class definitions.

## 15. Quy trình debug `Lookup.defineClass`

Khi lỗi xuất hiện trong runtime framework, dùng checklist theo thứ tự:

### Bước 1 — Xác định ngữ cảnh lookup

```java
// Đoạn minh họa trong nơi có biến lookup:
Class<?> lc = lookup.lookupClass();
System.out.println("lookupClass = " + lc.getName());
System.out.println("loader = " + lc.getClassLoader());
System.out.println("module = " + lc.getModule());
System.out.println("package = " + lc.getPackageName());
System.out.println("modes = " + lookup.lookupModes());
System.out.println("has PACKAGE = "
        + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));
```

Đừng log raw bytecode hoặc bí mật của plugin nếu không cần; logs nên cung cấp context đủ để chẩn đoán mà không làm lộ dữ liệu nhạy cảm.

### Bước 2 — Kiểm tra classfile bytes, không đoán từ tên file

Chạy công cụ như:

```bash
javap -v -classpath build sample.dynamic.Generated
```

Cần kiểm tra binary name, classfile major version và các constant-pool references. Trong classfile, `this_class` quyết định tên class, không phải path nơi bytes được tải từ. Một file được đặt tên `Generated.class` có thể chứa class khác; `defineClass` dựa vào **bytes thật**.

### Bước 3 — So sánh package và loader

Đảm bảo package trong bytes **bằng** package của `lookup.lookupClass()`; kết quả có cùng defining loader. Nếu bạn đang muốn dùng class loader khác, cần thay thiết kế chứ không thể ép một `Lookup` thuộc loader A định nghĩa class vào loader B bằng tham số không tồn tại.

### Bước 4 — Kiểm tra PACKAGE access

Với `IllegalAccessException`, xem `lookup.lookupModes()`. `publicLookup()` và lookup bị drop PACKAGE không đủ. Nếu code đã dùng `Lookup.in` để đổi class/package, khả năng PACKAGE đã bị giảm. Nếu dùng `privateLookupIn`, kiểm tra caller access và `opens` của module đích.

### Bước 5 — Kiểm tra JPMS và module đích

Chạy `lookup.lookupClass().getModule()`. Nếu class mới có tên package của module B nhưng lookup class ở module A, code thiếu một bước **cấp lookup đúng ngữ cảnh**, không phải chỉ thiếu tham số cho `defineClass`.

Với named modules, xem `module-info.java` hoặc descriptor runtime: module nào `requires` module nào, package nào `exports` cho compile access, package nào `opens` cho deep lookup. Trong trường hợp chỉ cần define nội bộ cùng module, `opens` ra ngoài không phải điều kiện.

### Bước 6 — Kiểm tra duplicate name và lifecycle

Nếu `LinkageError` chứa nội dung duplicate definition, xác định binary name + defining loader và xem class đó đã được định nghĩa trước chưa. Đừng retry y nguyên bytes vào cùng loader như một phương pháp chữa lỗi.

### Bước 7 — Phân biệt lỗi define, link, initialize, invoke

- Define/verify/link: `ClassFormatError`, `VerifyError`, `LinkageError`.
- Lookup permission/package: `IllegalAccessException` hoặc `IllegalArgumentException`.
- Initialize: `ExceptionInInitializerError` hoặc lỗi initialization phù hợp, có thể xảy ra sau khi định nghĩa thành công.
- Method lookup/invoke: `NoSuchMethodException`, `WrongMethodTypeException`, ngoại lệ target hoặc reflection wrappers theo API được dùng.

Không gom tất cả thành “class loader failed” mà bỏ qua giai đoạn thật.

## 16. Khi nào nên dùng API này trong một ứng dụng?

**Trường hợp phù hợp:**

- Framework đáng tin tạo một helper ordinary class thuộc **cùng runtime package/module** để truy cập package-private API hợp lệ.
- Runtime hoặc tooling sinh bytecode từ compiler/generator đã kiểm soát rồi đưa vào package đã được chủ sở hữu cho phép.
- Một hệ thống sử dụng `privateLookupIn` được module đích **cấp `opens` hợp lệ** và cần định nghĩa class mới trong package/module đích.

**Trường hợp không phù hợp:**

- Tạo plugin sandbox độc lập có class loader riêng: xem custom `ClassLoader`, module layers và process isolation.
- Muốn reload một ordinary class đang tồn tại cùng name/loader: `defineClass` không cho overwrite.
- Muốn một hidden implementation class không có tên bình thường: xem `defineHiddenClass` với quyền và lifetime riêng.
- Chỉ cần gọi method/constructor động trên class đã có: dùng `MethodHandle` hoặc Reflection, không cần tạo class mới.
- Muốn vượt giới hạn JPMS hoặc private access của module khác: `defineClass` không phải công cụ bypass.

### 16.1. Thiết kế bytecode generation an toàn hơn

Nếu đã quyết định dùng `defineClass`:

1. Đặt **binary name duy nhất** theo defining loader và lifecycle.
2. Sinh bytecode theo classfile version runtime hỗ trợ; Java 17 ví dụ dùng `javac --release 17`.
3. Kiểm tra package/class name **trước** khi gọi `defineClass` và giữ lookup đúng ngữ cảnh.
4. Cache `Class<?>` đã định nghĩa nếu cần dùng lại; không gọi define lại bytes cho cùng name/loader.
5. Cân nhắc exception boundaries: Error từ verifier/linker khác checked lookup errors.
6. Giữ lookup có PACKAGE access trong phạm vi tin cậy, không chia sẻ ra plugin không đáng tin.
7. Kiểm thử trên **classpath và module path** khi framework được phép chạy ở cả hai môi trường.
8. Test tình huống module không `opens` để đảm bảo hệ thống từ chối deep access đúng như thiết kế.

## 17. Lỗi hiểu nhầm thường gặp

**1. “`defineClass` tự chọn class loader dựa vào nơi lưu file bytes.”** Sai. Defining loader là loader của **lookup class**, không phải đường dẫn file.

**2. “Chỉ cần bytes có `package p.q` thì lookup ở package nào cũng define được.”** Sai. Package trong bytes phải khớp package lookup class; sai bị `IllegalArgumentException`.

**3. “`publicLookup` có thể define public classes.”** Sai. `public` modifier không thay thế `Lookup.PACKAGE`; `publicLookup` thiếu quyền này.

**4. “`Lookup.in` chuyển sang class/package khác thì quyền tự tăng.”** Sai. `Lookup.in` không tăng quyền và có thể drop PACKAGE/MODULE.

**5. “`privateLookupIn` bỏ qua `opens` của JPMS.”** Sai. Nó cần điều kiện caller access và module openness tương ứng. Ví dụ hai modules thành công **vì** `opens p.target to m.tool`.

**6. “Class mới sẽ vào module của caller Java code.”** Không nhất thiết. Nó vào module của **lookup class** của Lookup đang dùng, như ví dụ CrossModuleDemo.

**7. “Class mới luôn ở unnamed module.”** Sai. Named-module lookup sẽ định nghĩa class vào named module ấy.

**8. “`defineClass` khởi tạo ngay class mới.”** Sai. Nó không chạy `<clinit>`; initialization có thể diễn ra khi active use sau đó.

**9. “`defineClass` tạo sẵn object instance.”** Sai. Nó trả `Class<?>`; constructor được gọi riêng khi cần.

**10. “Cùng package name nghĩa là cùng runtime package.”** Sai nếu defining loader/module khác nhau; phải so đúng runtime context.

**11. “Class mới cùng package có thể đọc mọi private member của Host.”** Sai. Package-private khác private; nest membership không tự xuất hiện.

**12. “Có thể định nghĩa lại cùng name/loader bằng cách gọi `defineClass` thêm lần nữa.”** Sai. Duplicate definition dẫn tới `LinkageError`.

**13. “`defineClass` đã thành công thì mọi method đều gọi được.”** Sai. Initialization và lazy resolution có thể phát sinh lỗi về sau.

**14. “`Lookup.defineHiddenClass` và `defineClass` chỉ khác tên method.”** Sai. Hidden classes có naming/discoverability, initialization, access và lifetime semantics riêng.

**15. “`exports` và `opens` tương đương nhau.”** Sai. Public type/method accessibility và deep private lookup là hai loại quyền khác nhau.

**16. “`ProtectionDomain` của generated class mặc định theo nơi bytes xuất phát.”** Sai với `Lookup.defineClass`: domain dựa trên lookup class theo API.

**17. “Không cần quản lý class name collisions khi nhiều threads sinh class.”** Sai. Duplicate names trong cùng defining loader vẫn là xung đột; cần coordination và naming.

## 18. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `lookup.lookupClass()` nằm trong package `app.core`; bytes ghi `plugin.impl.Proxy`. Có thể gọi `lookup.defineClass(bytes)` thành công không?

**Đáp án:** Không theo hợp đồng thường thấy vì package khác nhau. `defineClass` yêu cầu binary name trong bytes cùng package với lookup class; nếu lookup có PACKAGE nhưng package bytes sai, ném `IllegalArgumentException`.

**Câu 2.** `lookup` có `PUBLIC` nhưng không có `PACKAGE`; class bytes thuộc đúng package. Kết quả?

**Đáp án:** `IllegalAccessException` vì quyền PACKAGE bắt buộc. Đúng tên package không thay thế access mode.

**Câu 3.** Code ở module A nhận `Lookup` có lookup class ở module B và PACKAGE access, sau đó gọi `defineClass`. Lớp mới ở module nào?

**Đáp án:** Module **B**, vì ngữ cảnh được quyết định bởi **lookup class** của chính đối tượng Lookup, không phải class đang chứa dòng Java source gọi method.

**Câu 4.** Vì sao `Generated.class` không nằm trong runtime classpath mà vẫn define được?

**Đáp án:** Caller đọc bytes bằng `Files.readAllBytes` rồi cung cấp cho `lookup.defineClass`. Defining loader lấy từ lookup class; đường dẫn bytes không quyết định runtime class identity.

**Câu 5.** `Generated` và `Host` cùng package name nhưng khác defining class loaders. Chúng có mặc nhiên truy cập package-private của nhau?

**Đáp án:** Không. Runtime package/access còn ràng buộc classloader/module; cùng tên trong source là chưa đủ.

**Câu 6.** Gọi `defineClass` trên class có static initializer in một dòng, nhưng chưa invoke bất cứ method nào. Dòng đó đã in chưa?

**Đáp án:** Chưa chỉ do `defineClass`, vì API không chạy initializer. Một active use sau đó có thể gây initialization.

**Câu 7.** Định nghĩa lại cùng bytes với cùng binary name vào cùng loader sẽ làm hot reload?

**Đáp án:** Không. Việc định nghĩa trùng tên/loader bị từ chối bởi linkage rules, thường là `LinkageError`. Cần kiến trúc versioning/class loader khác.

**Câu 8.** Khi dùng `privateLookupIn` sang module khác, lookup mới mất `MODULE` nhưng vẫn có `PACKAGE`. Có thể dùng `defineClass` không?

**Đáp án:** Có thể, **nếu** lookup mới đã được cấp hợp lệ và bytes cùng package của lookup class. `defineClass` yêu cầu PACKAGE; không đòi MODULE riêng. Mất MODULE không đồng nghĩa tự mất PACKAGE.

**Câu 9.** Vì sao `m.runtime` trong ví dụ named module không có `exports` mà vẫn gọi được package-private method từ generated class?

**Đáp án:** Cả hai classes ở cùng runtime package/module và loader. `exports` dành cho các use cases public access **từ module khác**; không cần xuất package ra ngoài để các classes nội bộ truy cập nhau theo Java package rules.

**Câu 10.** `Lookup.in(Anchor.class)` và `privateLookupIn(Anchor.class, callerLookup)` có giống nhau về quyền không?

**Đáp án:** Không. `Lookup.in` không nâng quyền và có thể drop PACKAGE/PRIVATE/MODULE; `privateLookupIn` có thể tạo lookup với private/package access trong ngữ cảnh target nếu các điều kiện caller và JPMS `opens` được thỏa mãn.

**Câu 11.** Một classfile hợp lệ nhưng chứa method body truy cập dữ liệu nhạy cảm. Class verifier có chặn vì method làm việc nguy hiểm không?

**Đáp án:** Không thể dựa vào verifier như sandbox nghiệp vụ. Verifier kiểm tra tính hợp lệ của bytecode và type safety; class có thể thực hiện hành vi được cấp quyền khi initialize/invoke. Cần boundary bảo mật riêng.

**Câu 12.** Khi nào chọn `ClassLoader.defineClass` thay vì `Lookup.defineClass`?

**Đáp án:** Khi bạn chủ động quản lý một defining loader/lifecycle riêng, ví dụ plugin isolation, và cần class-loading architecture tùy biến. `Lookup.defineClass` phù hợp hơn khi muốn thêm class vào **đúng package/module/loader của lookup class đã có**.

**Câu 13.** Khi nào chọn `defineHiddenClass`?

**Đáp án:** Khi cần implementation class sinh động không cần binary name bình thường để clients link trực tiếp; phải tuân theo ràng buộc full privilege và semantics của hidden class.

**Câu 14.** Class mới cùng package với Host có tự là nestmate của Host không?

**Đáp án:** Không. Package membership khác nest membership; định nghĩa ordinary class bằng `Lookup.defineClass` không tự cấp private nest access.

**Câu 15.** Một class được define thành công nhưng lúc gọi static method lại ném `ExceptionInInitializerError`. Tại sao không mâu thuẫn?

**Đáp án:** Define/link và initialize là các giai đoạn khác nhau. `defineClass` không chạy `<clinit>`; lần active use sau đó mới khởi tạo class và có thể thất bại.

**Câu 16.** Muốn chẩn đoán đúng ba ràng buộc chính, nên in những gì?

**Đáp án:** `lookup.lookupClass().getName()`, `getPackageName()`, `getClassLoader()`, `getModule()`, `lookup.lookupModes()`; đồng thời kiểm tra class binary name và classfile validity từ bytes.

## 19. Tài liệu tham khảo chuẩn

- **Java SE 17 — `MethodHandles.Lookup.defineClass`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — đặc tả về same loader/runtime package/protection domain, PACKAGE access, class initialization, thrown exceptions.
- **Java SE 17 — `MethodHandles.privateLookupIn`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — điều kiện lấy lookup trong class/package/module đích.
- **Java SE 17 — `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html — defining loader, loading và defineClass API.
- **Java SE 17 — `Class`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — `getName`, `getModule`, `getClassLoader`, reflection.
- **Java SE 17 — `Module`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html — runtime module identity, exports/opens.
- **Java SE 17 — `MethodHandle`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — typed invocation sau khi định nghĩa class.
- **Java Virtual Machine Specification 17 — chương 5:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html — loading, linking, resolution và initialization.
- **Java Language Specification 17 — chương 12:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html — execution và class initialization.
- **Java Virtual Machine Specification 17 — chương 4:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html — `ClassFile`, constant pool, `this_class` và classfile versions.

**Kết luận:** `Lookup.defineClass` không chỉ “nạp một mảng bytes”. Nó định nghĩa ordinary class với **package, defining class loader, module và protection domain thuộc ngữ cảnh lookup class**, dưới sự kiểm soát của quyền `Lookup.PACKAGE`. Muốn chọn một context khác phải có **Lookup hợp lệ trong context đó**, chứ không phải chỉ đổi tên package trong bytes. Phân biệt các giai đoạn define/link/initialize, quản lý duplicate names và tôn trọng JPMS là chìa khóa để xây runtime code generation đúng và an toàn.