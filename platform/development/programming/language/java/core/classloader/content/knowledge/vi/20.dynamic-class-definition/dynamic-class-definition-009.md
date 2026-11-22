# Ràng buộc phiên bản, cấu trúc lớp và quyền truy cập khi tạo lớp động trong Java

**Tạo lớp động** (*dynamic class definition*) là việc JVM nhận một chuỗi bytecode class file tại runtime và tạo ra đối tượng `Class<?>` đại diện cho một kiểu mới trong namespace của class loader. Các API liên quan gồm `ClassLoader.defineClass(...)`, `ClassLoader.findClass(...)` và `MethodHandles.Lookup.defineClass(...)`. Bước này khác hẳn với `new SomeClass()`: **định nghĩa class tạo runtime type, không tự tạo instance của class ấy và không mặc định chạy static initializer**.

Một mảng byte có vẻ hợp lệ chưa đủ để JVM chấp nhận định nghĩa. JVM kiểm tra **phiên bản class file**, cấu trúc/bytecode, binary name, package, quan hệ với superclass/interfaces, quyền truy cập và các ràng buộc linking. Một số lỗi xảy ra ngay ở `defineClass`; lỗi khác có thể chỉ xuất hiện lúc `resolveClass`, reflective lookup, class initialization hoặc lần đầu gọi method.

Bài học này tập trung vào **“Ràng buộc phiên bản, cấu trúc lớp và quyền truy cập khi tạo lớp động”** thuộc nhóm **Định nghĩa lớp động** của **Java core – classloader**, sử dụng JDK 17+ làm nền tảng và ví dụ có thể biên dịch/chạy.

## 1. Năm tầng ràng buộc cần phân biệt

| Tầng | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Class-file version** | JVM hiện tại có hiểu format/feature của bytecode này không? | Major 65 của Java 21 trên JVM chỉ hỗ trợ đến 61 của Java 17 |
| **Class-file format / verification** | Bytes có cấu trúc `ClassFile`, constant pool, methods, bytecode, stack-map và invariants hợp lệ không? | Magic sai, constant pool hỏng, verification type mismatch |
| **Identity / name / linkage** | Binary name truyền vào có khớp class file? Loader có định nghĩa trùng? References có resolve hợp lệ? | `NoClassDefFoundError` do wrong name, duplicate-definition `LinkageError` |
| **Runtime package / module / access** | Class mới có quyền dùng target types/members hoặc module packages không? | Package-private member cùng tên package nhưng khác defining loader |
| **Protection domain / code source / package consistency** | Class thuộc security domain nào? Package có certificates/sealing rules tương thích không? | `SecurityException` khi chữ ký package không thống nhất |

**Không dồn mọi lỗi vào một `catch (Exception)`.** Phần lớn lỗi xác minh/liên kết thuộc họ `Error` (`LinkageError` và subclasses). Khi debug, phải phân biệt **không tìm ra bytes**, **bytes sai**, **bytes có thể định nghĩa nhưng truy cập sai**, và **class có thể nạp nhưng hoạt động sau đó lỗi**.

## 2. Runtime type identity: binary name chưa đủ

Trong JVM, hai classes có thể cùng `Class.getName()` nhưng khác runtime type nếu được **hai defining loaders khác nhau** định nghĩa:

```text
name = "plugins.Task"

(hostLoader defines plugins.Task)   → runtime Class A
(pluginLoader defines plugins.Task) → runtime Class B

A.getName().equals(B.getName()) → true
A == B                           → false
```

Một cách diễn giải thực dụng: runtime class identity phụ thuộc **binary name + defining class loader**. Điều này tác động trực tiếp tới:

- `instanceof`, ép kiểu và `Class.isAssignableFrom`;
- reflective lookup trên tham số/return types;
- package-private access;
- interfaces chia sẻ giữa host và plugin;
- static state và class initialization của mỗi runtime definition;
- loader constraints khi method descriptors đi qua nhiều loaders.

Khi triển khai plugin, nên để **host API/SPI/DTO classes** được định nghĩa một lần bởi loader chung, còn implementation/private dependencies có thể do loader riêng định nghĩa. Nếu cả hai bên tự định nghĩa `api.Plugin` có cùng source code, object của plugin vẫn có thể không cast được về API host.

## 3. `ClassLoader.defineClass` nhận gì, trả gì?

Overload thông dụng:

```java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length);

protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length,
        java.security.ProtectionDomain domain);
```

Đây là **chữ ký API rút gọn để đọc**, không phải các method phải tự khai báo (chúng đã có trong `ClassLoader`). `defineClass` là `protected final`: caller không phải subclass không gọi nó trực tiếp trên loader bất kỳ; subclass thường cung cấp nó qua `findClass`.

Các tham số:

- `name` là **binary name** được mong đợi, chẳng hạn `"demo.generated.DynamicHello"`; không truyền `"demo/generated/DynamicHello.class"`.
- `bytes` là toàn bộ hoặc một đoạn của **class-file bytes**, không phải Java source UTF-8.
- `offset` và `length` xác định đoạn hợp lệ trong mảng; offset âm hoặc vượt giới hạn có thể gây `IndexOutOfBoundsException`.
- `domain` xác định `ProtectionDomain` nếu dùng overload tường minh; `null` khiến default domain theo Javadoc.
- Kết quả là `Class<?>` mới được định nghĩa (nếu thành công), **chưa phải object instance**.

Javadoc khuyến nghị truyền **binary name không null** để đối chiếu với binary name thực sự có trong bytes và thực thi những ràng buộc liên quan. Overload cũ `defineClass(byte[], int, int)` không có tham số tên đã deprecated, không nên dùng cho code mới.

### `findClass` khác `defineClass`

`findClass(name)` là hook để **tìm bytes rồi gọi `defineClass`** nếu cần. `loadClass(name)` thông thường kiểm tra lớp đã có và thử parent trước rồi mới đến `findClass`.

```text
loadClass("demo.generated.DynamicHello")
      ├─ findLoadedClass(...)
      ├─ parent delegation
      └─ findClass(...)
            ├─ đọc /generated-out/demo/generated/DynamicHello.class
            └─ defineClass("demo.generated.DynamicHello", bytes, ...)
                       ↓
                    Class<?>
```

Nếu chỉ muốn thêm nguồn bytecode, thường **override `findClass` thay vì tự override `loadClass`** để giữ đúng synchronization, parent delegation và tránh duplicate definition.

## 4. Thực hành A — định nghĩa một class Java 17 từ file bytecode

Tạo hai source files **khác output folders** để host không vô tình thấy class động trên application classpath.

```text
define-lab/
├── src/
│   ├── generated/demo/generated/DynamicHello.java
│   └── host/demo/DefineDemo.java
├── generated-out/      (sinh bởi javac)
└── host-out/           (sinh bởi javac)
```

**`src/generated/demo/generated/DynamicHello.java`:**

```java
package demo.generated;

public final class DynamicHello {
    static {
        System.out.println("DynamicHello initialized");
    }

    public DynamicHello() {
        System.out.println("DynamicHello constructed");
    }

    public String say() {
        return "Hello from dynamically defined class";
    }
}
```

**`src/host/demo/DefineDemo.java`:**

```java
package demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class DefineDemo {
    static final class ByteFileLoader extends ClassLoader {
        ByteFileLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            Path file = Path.of("generated-out",
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ByteFileLoader loader = new ByteFileLoader();

        Class<?> type =
                loader.loadClass("demo.generated.DynamicHello");

        System.out.println("defined by child=" +
                (type.getClassLoader() == loader));
        System.out.println("type=" + type.getName());
        System.out.println("before constructor");

        Object instance = type.getDeclaredConstructor().newInstance();
        String greeting =
                (String) type.getMethod("say").invoke(instance);

        System.out.println("result=" + greeting);
    }
}
```

Từ thư mục `define-lab`, biên dịch và chạy bằng JDK 17+:

```sh
javac --release 17 -d generated-out src/generated/demo/generated/DynamicHello.java
javac --release 17 -d host-out src/host/demo/DefineDemo.java
java -cp host-out demo.DefineDemo
```

**Stdout với cấu trúc đã nêu:**

```text
defined by child=true
type=demo.generated.DynamicHello
before constructor
DynamicHello initialized
DynamicHello constructed
result=Hello from dynamically defined class
```

**Các dấu mốc quan trọng:**

1. `ByteFileLoader` có parent là platform loader, không tự nhìn thấy classes trong `generated-out`.
2. `loader.loadClass` gọi `findClass` của child vì parent không tìm được binary name.
3. `Files.readAllBytes` lấy bytecode do `javac` đã sinh; `defineClass` tạo runtime class và trả `Class<?>`.
4. Lúc in `defined by child` và `type`, static initializer **chưa chạy**.
5. `getDeclaredConstructor().newInstance()` tạo object và yêu cầu class initialization nếu chưa xong: static block in trước constructor.
6. `getMethod("say").invoke(instance)` gọi instance method, không phải định nghĩa class lần nữa.

**Cực kỳ quan trọng:** lệnh `java` **không** có `generated-out` trên `-cp`. Nếu bạn thêm thư mục ấy vào application classpath rồi dùng system loader làm parent, parent-first có thể định nghĩa `DynamicHello` trước; `type.getClassLoader() == loader` khi đó không còn chắc `true`. Đây là lý do thực hành chủ động tách output directories.

`Path.of("generated-out", ...)` dùng đường dẫn tương đối working directory; các lệnh phải chạy từ `define-lab`. Ví dụ đọc file để học về bytecode, không phải một loader dùng trực tiếp cho nguồn untrusted.

## 5. Giới hạn class-file version: major/minor

Đầu mỗi file class có cấu trúc cơ bản:

```text
u4 magic            = 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
... constant_pool
... access_flags, this_class, super_class
... interfaces, fields, methods, attributes
```

**Major version** cho biết định dạng class file thuộc thời Java version nào. Những mốc thường gặp:

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Một JVM chỉ hỗ trợ những class-file versions nằm trong phạm vi mà nó nhận biết. Với **Java 17**, một class có major version **65** (Java 21) hoặc cố tình đặt **100** không thể được định nghĩa bình thường: thường báo **`UnsupportedClassVersionError`**.

**Đừng suy từ tên file `.class`, tên JAR hoặc property `sourceCompatibility`** rằng bytes đã có đúng version. Hãy kiểm tra thực tế:

```sh
javac --release 17 -d generated-out src/generated/demo/generated/DynamicHello.java
javap -verbose -classpath generated-out demo.generated.DynamicHello
```

Trong output `javap -verbose`, tìm dòng:

```text
major version: 61
```

`javac --release 17` vừa nhắm ngôn ngữ/bytecode Java 17 vừa giới hạn public APIs thích hợp với release đã chọn. Chỉ bật `-source` mà quên target/release không phải lúc nào cũng đủ để tránh phụ thuộc nhầm API phiên bản mới.

### Preview features cũng có điều kiện

Không chỉ major version: có các quy tắc riêng với **preview class files** dùng minor version đặc biệt. Những bytes được build bằng preview features có thể chỉ chạy khi JVM hỗ trợ đúng release với `--enable-preview`, không phải cứ major version nằm trong khoảng là hợp lệ. Khi gặp `UnsupportedClassVersionError`, đọc cả **major/minor**, compiler flags và JVM version.

## 6. Thực hành B — wrong binary name, bytes sai và version quá mới

Dùng lại `generated-out/demo/generated/DynamicHello.class` từ thực hành A, không cần chạy `DefineDemo`. Tạo tệp **`src/host/demo/ClassBytesCheckDemo.java`**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

public final class ClassBytesCheckDemo {
    static final class Definer extends ClassLoader {
        Definer() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> put(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] correct = Files.readAllBytes(Path.of(
                "generated-out/demo/generated/DynamicHello.class"));

        try {
            new Definer().put("demo.generated.WrongName", correct);
        } catch (NoClassDefFoundError error) {
            System.out.println("wrong name: " +
                    error.getClass().getSimpleName());
        }

        try {
            new Definer().put("demo.generated.Bad", 
                    "not a class".getBytes(StandardCharsets.UTF_8));
        } catch (ClassFormatError error) {
            System.out.println("bad bytes: " +
                    error.getClass().getSimpleName());
        }

        byte[] tooNew = correct.clone();
        tooNew[6] = 0;
        tooNew[7] = 100; // major = 100, không được Java 17 hỗ trợ

        try {
            new Definer().put("demo.generated.DynamicHello", tooNew);
        } catch (UnsupportedClassVersionError error) {
            System.out.println("too new: " +
                    error.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy với **JDK 17**:

```sh
javac --release 17 -d host-out src/host/demo/ClassBytesCheckDemo.java
java -cp host-out demo.ClassBytesCheckDemo
```

**Stdout dự kiến trên Java 17/HotSpot với bytes đã biên dịch như trên:**

```text
wrong name: NoClassDefFoundError
bad bytes: ClassFormatError
too new: UnsupportedClassVersionError
```

**Phân tích ba trường hợp:**

- **Wrong name:** `defineClass("demo.generated.WrongName", correctBytes, ...)` nhưng `this_class` thực tế của file là `demo.generated.DynamicHello`. Javadoc `ClassLoader.defineClass` nêu rõ mismatch dẫn tới `NoClassDefFoundError`. Đó không đơn thuần là `ClassNotFoundException`.
- **Bad bytes:** chuỗi `"not a class"` không phải một `ClassFile` hợp lệ (magic/cấu trúc sai), nên ném `ClassFormatError`.
- **Too new:** byte thứ 6–7 biểu diễn **major version** trong header class file (đếm từ 0). Ta sửa từ 61 lên 100; Java 17 không hiểu version này nên `UnsupportedClassVersionError`.
- Mỗi phép thử dùng một **Definer instance mới** để ranh giới identity/duplicate-definition không ảnh hưởng lẫn nhau.
- `UnsupportedClassVersionError` kế thừa `ClassFormatError`, vì vậy **catch subclass trước superclass** nếu cùng một try-block.

**Không bao giờ patch class bytes tùy tiện trong sản phẩm thật.** Sửa version header không “chuyển đổi” các bytecode instructions/attributes của class file đời mới thành code có thể chạy trên JVM cũ. Muốn chạy trên Java 17, phải compile/transform bằng tool hỗ trợ và loại bỏ những features/APIs không tương thích.

## 7. Class-file structure không chỉ có version

Cấu trúc `ClassFile` theo JVMS `4.1` gồm:

- **`magic`**: nhận dạng file class.
- **`minor_version` và `major_version`**: phiên bản định dạng.
- **`constant_pool`**: các symbol references, UTF-8 strings, type/method/field descriptors, method handles và metadata liên quan.
- **`access_flags`**: modifiers như public, final, interface, abstract, enum, annotation, module.
- **`this_class`/`super_class`**: tên class đang định nghĩa và superclass.
- **`interfaces`**: những interface mà class khai báo.
- **`fields`** và **`methods`**: signatures và metadata.
- **`attributes`**: `Code`, `StackMapTable`, annotations, `NestHost`/`NestMembers`, `Record`, `PermittedSubclasses`, v.v.

JVM phải đảm bảo **format checking** và **verification** theo JVMS. Một transformer/sinh bytecode tự động có thể tạo:

- constant-pool index vượt giới hạn hoặc tag sai;
- descriptor sai cú pháp;
- mã lệnh không hợp lệ, stack types không nhất quán;
- class khai báo mâu thuẫn như final nhưng bị extends;
- `StackMapTable` không khớp bytecode;
- names/inheritance cycles không hợp lệ;
- attribute không phù hợp version hoặc class kind.

Một số vấn đề gây **`ClassFormatError`**, một số gây **`VerifyError`**, **`ClassCircularityError`** hoặc các `LinkageError` khác theo giai đoạn. **Không dự đoán mọi lỗi bytecode đều ném tại đúng lệnh `defineClass`.** JVM có thể thực hiện một số resolution lazily; lỗi có thể xuất hiện lúc `resolveClass` hoặc khi instruction thực sự cần reference.

### `javap` là công cụ kiểm tra, không phải verifier thay JVM

```sh
javap -verbose -classpath generated-out demo.generated.DynamicHello
javap -c -p -classpath generated-out demo.generated.DynamicHello
```

`-verbose` hiển thị header/constant pool/attributes; `-c -p` hiển thị bytecode kể cả members non-public. Lệnh `javap` đọc class file và **không chứng minh** JVM runtime đã nạp class qua đúng loader, liên kết thành công với mọi dependency hay chạy initializer.

## 8. Binary name, package name và path phải nhất quán

Với source:

```java
package demo.generated;

public class DynamicHello { }
```

Các tên khác nhau là:

| Khái niệm | Giá trị |
| --- | --- |
| Java source name | `demo.generated.DynamicHello` |
| Binary name | `demo.generated.DynamicHello` |
| Class-file relative path | `demo/generated/DynamicHello.class` |
| Internal JVM class name | `demo/generated/DynamicHello` |
| Descriptor dùng khi tham chiếu type | `Ldemo/generated/DynamicHello;` |

Khi gọi `loader.loadClass` hoặc `defineClass(name, ...)`, truyền **binary name** có dấu chấm. Khi xác định file bytes từ thư mục, có thể chuyển dấu `.` sang `/`. Không chuyển mọi dấu `$` thành `/`: tên binary của nested class như `demo.Outer$Inner` chứa dấu `$` là một phần tên binary.

**Lưu ý về mảng:** `ClassLoader.defineClass` không dùng để định nghĩa array class bằng một class-file `ClassFile` mang tên kiểu `[L...;`. JVM tạo array classes theo cơ chế riêng; `Class.getClassLoader()` của array class phản ánh element-type loader (hoặc bootstrap cho primitive arrays).

### Điều gì xảy ra nếu name không khớp bytes?

`defineClass("demo.generated.WrongName", correctBytes, ...)` báo `NoClassDefFoundError` (đã kiểm chứng trong ví dụ B), thay vì tự sửa tên bytecode. Không nên truyền `name=null` chỉ để bỏ qua vấn đề: làm mất một số kiểm tra và làm code khó đảm bảo định danh, source và package chính xác.

## 9. Một runtime package phụ thuộc defining loader

Trong Java source, hai class ghi cùng:

```java
package shared;
```

Nhưng package-private access ở runtime không chỉ phụ thuộc dòng `package`. JVM xác định **runtime package** bằng package name cùng **defining loader**. Vì vậy:

```text
AppLoader defines shared.Token           → runtime package P1
PluginLoader defines shared.DynamicAccess → runtime package P2

Text package name: shared == shared
Runtime package:    P1 != P2
```

Kết quả: `DynamicAccess` có thể không được phép truy cập package-private `Token` hay package-private method `Token.value()` của parent, dù chúng cùng viết `package shared;` trong source.

Đây là điểm quan trọng khi class sinh động dùng **ByteBuddy/ASM/JavaCompiler/custom ClassLoader** để “inject” class vào package có sẵn. **Cùng tên package không đủ để có quyền private/package access**.

Trong named modules, JPMS còn có các quy tắc readability/exports/opens; không xem defining-loader identity là cách tự vượt module restrictions.

## 10. Thực hành C — cùng tên package nhưng bị từ chối package-private access

Cấu trúc project:

```text
access-lab/
├── src/
│   ├── host/shared/Token.java
│   ├── host/shared/AccessDemo.java
│   └── plugin/shared/DynamicAccess.java
├── host-out/
└── plugin-out/
```

**`src/host/shared/Token.java`:**

```java
package shared;

final class Token {
    static String value() {
        return "host-private-package";
    }
}
```

**`src/plugin/shared/DynamicAccess.java`:**

```java
package shared;

public final class DynamicAccess {
    public static String call() {
        return Token.value();
    }
}
```

Source trên hợp lệ khi compiler được cấp `host-out` làm compile classpath, vì Java compiler nhìn hai source types trong cùng package `shared`. Nhưng ở runtime chúng có **defining loaders khác nhau**.

**`src/host/shared/AccessDemo.java`:**

```java
package shared;

import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class AccessDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader() {
            super(AccessDemo.class.getClassLoader());
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals("shared.DynamicAccess")) {
                throw new ClassNotFoundException(name);
            }
            try {
                byte[] bytes = Files.readAllBytes(Path.of(
                        "plugin-out/shared/DynamicAccess.class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("host call=" + Token.value());

        PluginLoader child = new PluginLoader();
        Class<?> dynamic = child.loadClass("shared.DynamicAccess");

        System.out.println("same textual package=" +
                dynamic.getPackageName().equals(
                        Token.class.getPackageName()));
        System.out.println("different defining loaders=" +
                (dynamic.getClassLoader()
                        != Token.class.getClassLoader()));

        try {
            dynamic.getMethod("call").invoke(null);
            System.out.println("unexpected success");
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println("cause=" +
                    cause.getClass().getSimpleName());
        }
    }
}
```

Biên dịch từ `access-lab`:

```sh
javac --release 17 -d host-out src/host/shared/Token.java src/host/shared/AccessDemo.java
javac --release 17 -cp host-out -d plugin-out src/plugin/shared/DynamicAccess.java
java -cp host-out shared.AccessDemo
```

**Stdout trên OpenJDK/HotSpot 17 theo cấu hình này:**

```text
host call=host-private-package
same textual package=true
different defining loaders=true
cause=IllegalAccessError
```

**Lý giải:** `Token` là package-private do app loader định nghĩa. Class `DynamicAccess` được plugin loader tự define dù cùng `package shared`. Khi bytecode `DynamicAccess.call()` cố gọi `Token.value()`, JVM kiểm tra runtime accessibility; hai types không thuộc cùng runtime package, gây `IllegalAccessError`. Reflection ở đây chỉ gọi một public static method `call`; lỗi thực sự sinh **bên trong method body**, vì vậy `Method.invoke` bọc thành `InvocationTargetException` và `getCause()` trả `IllegalAccessError`.

Nếu JVM thực hiện resolution sớm, thời điểm báo một lỗi liên kết có thể thay đổi; thông điệp/stacktrace chi tiết cũng phụ thuộc implementation. **Nguyên tắc access không thay đổi:** hai defining loaders riêng không cấp quyền package-private chỉ dựa vào tên package.

**Cách sửa kiến trúc:** chuyển API cần dùng sang một **public shared contract**, hoặc dùng cơ chế được ủy quyền như `MethodHandles.Lookup.defineClass` với lookup hợp lệ trong **cùng runtime package** khi thật sự cần tạo class được truy cập package-private. Không thêm `setAccessible(true)` một cách tùy tiện để bỏ qua JVM linking/access rules.

## 11. `MethodHandles.Lookup.defineClass`: một lựa chọn có giới hạn cụ thể

Từ Java 9, `MethodHandles.Lookup.defineClass(byte[])` có thể định nghĩa class mới bằng **cùng defining loader, cùng runtime package và cùng protection domain** với **lookup class**.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> generated = lookup.defineClass(bytes);
```

Đây là **snippet**: cần import `java.lang.invoke.MethodHandles`, biến `bytes` chứa class-file bytes hợp lệ, và method phải xử lý `IllegalAccessException`/linkage errors. Khi gọi `MethodHandles.lookup()` từ `demo.Host`, class bytes phải khai báo một class có **cùng package** với `demo.Host`; không thể dùng lookup đó để tùy ý định nghĩa `another.package.Generated`.

Điều kiện chính:

- Lookup phải có **`PACKAGE` access mode**, chứng tỏ caller có quyền thao tác trong runtime package tương ứng.
- Bytes phải mang **class name thuộc cùng package** với lookup class, nếu không sẽ thất bại theo contract.
- Runtime class mới được định nghĩa trong loader/module/package mà lookup cho phép, không phải tùy ý gắn vào một loader object khác.
- Lookup.defineClass **không chạy class initializer** ngay; initialization có thể xảy ra khi class được active-use sau đó.
- Class name mới không được trùng với class đã định nghĩa trong cùng defining loader.
- Không tự cấp quyền truy cập private members của unrelated classes; private access/nestmates phải tuân thủ quy tắc riêng.

### Phân biệt `Lookup.defineClass` và `Lookup.defineHiddenClass`

`defineHiddenClass` (Java 15+) tạo **hidden classes** phục vụ framework/runtime code generation. Hidden class không phải class bình thường mà `Class.forName(binaryName)` có thể khám phá theo cách thông dụng; tên/identity và lifecycle khác. API có các options như `NESTMATE` và có tham số yêu cầu initialization.

Không dùng hidden class như drop-in replacement cho plugin public API cần discover bằng binary name. Chọn `Lookup.defineClass` khi cần **class có tên, cùng package/loader với lookup**, và `defineHiddenClass` khi thực sự cần một runtime implementation class không dựa trên name-based discovery.

## 12. Thực hành D — `Lookup.defineClass` trong cùng runtime package

Ví dụ sau tạo một file class đã biên dịch trong package `lookupdemo`, rồi nạp bytes đó bằng lookup của host class **cùng package**.

Cấu trúc:

```text
lookup-lab/
├── src/
│   ├── generated/lookupdemo/GeneratedGreeter.java
│   └── host/lookupdemo/LookupDemo.java
├── generated-out/
└── host-out/
```

**`src/generated/lookupdemo/GeneratedGreeter.java`:**

```java
package lookupdemo;

public final class GeneratedGreeter {
    public String message() {
        return "defined with Lookup";
    }
}
```

**`src/host/lookupdemo/LookupDemo.java`:**

```java
package lookupdemo;

import java.lang.invoke.MethodHandles;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LookupDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of(
                "generated-out/lookupdemo/GeneratedGreeter.class"));

        Class<?> type = MethodHandles.lookup().defineClass(bytes);

        System.out.println("same defining loader=" +
                (type.getClassLoader()
                        == LookupDemo.class.getClassLoader()));
        System.out.println("same package=" +
                type.getPackageName()
                        .equals(LookupDemo.class.getPackageName()));

        Object object = type.getDeclaredConstructor().newInstance();
        System.out.println("message=" +
                type.getMethod("message").invoke(object));
    }
}
```

Biên dịch/chạy trên JDK 17:

```sh
javac --release 17 -d generated-out src/generated/lookupdemo/GeneratedGreeter.java
javac --release 17 -d host-out src/host/lookupdemo/LookupDemo.java
java -cp host-out lookupdemo.LookupDemo
```

**Stdout:**

```text
same defining loader=true
same package=true
message=defined with Lookup
```

Lệnh `java` chỉ cho application loader thấy `host-out`; `GeneratedGreeter.class` chỉ ở thư mục riêng, do đó `Lookup.defineClass(bytes)` mới là hành động định nghĩa class trong app loader. Nếu bạn đưa `generated-out` lên application classpath rồi một code path khác đã nạp `lookupdemo.GeneratedGreeter`, `defineClass` sẽ không được dùng để định nghĩa trùng class.

**Lưu ý access:** ví dụ này chỉ dùng public class/method. Để thực hành package-private access, bạn có thể thêm class/member package-private cùng package và kiểm tra khi chúng thực sự được định nghĩa bởi **cùng loader**; không suy từ việc có cùng package name trong source.

## 13. Java access modifiers và JVM linking checks

Có ít nhất ba dạng access phải phân biệt:

1. **Java language access** khi biên dịch source: `public`, `protected`, package-private, `private`; compiler dùng packages và module visibility.
2. **Runtime access checking** khi liên kết hoặc invoke references: JVM xét **runtime package identity**, class/interface access, member accessibility và receiver rules phù hợp.
3. **Reflection/MethodHandles access** khi caller tra cứu/invoke members: phụ thuộc caller class, lookup modes, `AccessibleObject` và JPMS `exports/opens`.

Một class định nghĩa động không có “quyền truy cập mọi thứ” chỉ vì bytes do host sinh ra. Nếu runtime class nằm trong loader khác, nó không có package-private privileges của host. Nếu nằm trong named module không đọc được module khác, bytecode references có thể gặp access/linking errors.

### `public` không luôn đủ

Một public class thuộc package **không exported** của named module không tự trở thành accessible với arbitrary modules bên ngoài. `public` là điều kiện của Java type access, còn JPMS module readability/exports là điều kiện khác.

`opens` cho phép những dạng deep reflection nhất định; nó không có nghĩa compile-time/public access qua mọi modules đều hợp lệ. Named modules quản lý bằng module graph, không tự được “mở rộng” chỉ vì class loader tự định nghĩa thêm class.

**Không đánh đồng** `IllegalAccessError` (lỗi linking/runtime access trong bytecode) với `IllegalAccessException` (checked exception từ reflection/Lookup) hoặc `InaccessibleObjectException` (deep reflection bị JPMS ngăn). Chúng xuất hiện ở những APIs/giai đoạn khác nhau.

## 14. JPMS: module ownership của class sinh động

Khi dùng `ClassLoader.defineClass` với loader trên classpath thông thường, class được định nghĩa thường thuộc **unnamed module** gắn với defining loader. Việc đặt tên JAR hoặc nhúng `module-info.class` vào URL không tự biến class thành một named module có `requires`/`exports` được resolve hợp lệ.

Muốn tạo named-module plugin ecosystem, cần xem:

- `ModuleFinder` để xác định modular artifacts;
- `Configuration.resolve(...)` để resolve module graph;
- `ModuleLayer.defineModulesWithOneLoader(...)` hoặc các API tương ứng để thiết lập layer/loader;
- `uses`, `provides`, `requires`, `exports`, `opens` của module descriptors;
- package uniqueness/visibility và loader ownership trong layer.

`MethodHandles.Lookup.defineClass` có phạm vi loader/package/module từ lookup class; nó không phải API “inject class tùy ý vào mọi named module”. Không dùng reflective access để cố bypass module boundaries một cách ngẫu nhiên; module openness và lookup privileges phải được cấp hợp lệ.

### Không nhầm `module-info.class` với Java class thường

Class file mang `ACC_MODULE` có cấu trúc đặc biệt của module descriptor theo JVMS `4`. Nó không phải Java class để tạo instance bằng `new` hoặc `ClassLoader.defineClass("module-info", bytes,...)` theo cách plugin implementation thông thường. Module resolution là một cơ chế riêng.

## 15. Bảo vệ package `java.*` và tên namespace nhạy cảm

Javadoc `ClassLoader.defineClass` xác định restriction cho các names bắt đầu bằng `"java."`. Custom application loader thông thường không được `defineClass("java.lang.MyString", ...)` để giả mạo namespace nền tảng: hệ thống có thể ném **`SecurityException`**.

Tương tự, khi class đã nằm trong package có một bộ **signer certificates** nhất định, việc define class mới với certificates khác có thể gây `SecurityException`. Rule này ngăn kết hợp tùy tiện bytes có trạng thái ký khác nhau trong cùng package của một defining loader.

**Các ràng buộc này không phải “gợi ý” cho transformer**. Khi xây code generation library, hãy:

- chọn namespace hợp pháp và riêng của ứng dụng;
- không tạo class vào package `java.*`;
- giữ nhất quán CodeSource/ProtectionDomain khi cần;
- kiểm tra package sealing khi dùng `URLClassLoader`/JAR manifests;
- tránh định nghĩa thêm class vào package do dependency signed/sealed quản lý nếu không thật sự hiểu hậu quả.

## 16. ProtectionDomain và CodeSource: nói đúng về quyền

Overload `defineClass(name, bytes, off, len, ProtectionDomain)` cho caller tường minh một **protection domain**. `ProtectionDomain` có thể gắn với `CodeSource`, certificates và các thành phần security policy lịch sử.

Trên JDK 17, **Security Manager** đã bị deprecated for removal, và không nên coi việc chọn domain là một sandbox đầy đủ cho code không tin cậy. Ranh giới class loader/module visibility khác với **quyền truy cập file/network/process**.

Ví dụ snippet tường minh nguồn bytecode:

```java
CodeSource source = new CodeSource(
        new URL("file:/plugins/example.jar"),
        (java.security.cert.Certificate[]) null);

ProtectionDomain domain = new ProtectionDomain(source, null);
Class<?> type = defineClass(name, bytes, 0, bytes.length, domain);
```

Đây là **snippet bên trong subclass `ClassLoader`**, cần imports `java.net.URL`, `java.security.CodeSource`, `java.security.ProtectionDomain`, biến `name` và `bytes`; không phải Java standalone program. Thực tế protection domain/permissions/certificates cần được cấu hình đúng theo runtime. Đừng copy đoạn này rồi nghĩ mọi permissions đều bị vô hiệu hóa hoặc đã an toàn trước malicious bytecode.

**Nếu đầu vào không tin cậy**, cân nhắc isolation ở cấp **process/container** và kiểm soát nguồn bytecode, signature/allowlist, API/IO permissions và resource quotas; `defineClass` chỉ định nghĩa JVM type chứ không cung cấp isolation đầy đủ.

## 17. Package signing và sealing: hai cơ chế khác nhau

**Signer certificate consistency:**

- Khi một defining loader define class trong package, chứng chỉ ký có thể đặt ràng buộc nhất quán cho những classes khác trong package.
- Nếu bytes/class definition tiếp theo dùng certificate set khác, `defineClass` có thể ném `SecurityException`.
- `ProtectionDomain.getCodeSource()` có thể cung cấp code source/certificates trong những điều kiện phù hợp.

**Package sealing:**

- JAR manifest có thể khai báo package `Sealed: true`; một package sealed được gắn với nguồn code theo rules của loader.
- `URLClassLoader` và package metadata hỗ trợ kiểm tra sealing khi định nghĩa package.
- Việc tự dùng `ClassLoader.defineClass` trong loader tùy biến không có nghĩa hệ thống tự động áp y hệt chính sách sealing của `URLClassLoader` nếu loader không quản lý `definePackage`, code source và nguồn JAR như URLClassLoader.
- Đừng giả định “cùng package name thì có thể ghép các JAR bất kỳ”, nhất là signed/sealed packages.

Những ràng buộc signing/sealing là **consistency và integrity mechanisms**, không phải bằng chứng class file có thể chạy hay có business-level authorization.

## 18. Quan hệ superclass/interfaces và loading constraints

Một class được define thành công có thể vẫn chưa dùng được nếu **superclass/interface** hoặc các symbolic references vi phạm quy tắc JVM.

Ví dụ tình huống:

```text
Host loader defines api.Message → runtime type M1
Plugin loader defines api.Message → runtime type M2

HostInterface.accept(api.Message) expects M1
Plugin implementation uses M2

JVM method descriptors có thể dẫn tới
loader constraint violation / LinkageError
```

Không thể “ép” type M2 thành M1 bằng cách chỉ đổi tên package/class trên source hoặc reflection. Cần bảo đảm các shared API types được parent/delegation về **một defining loader chung**, hoặc dùng serialization/protocol DTO qua ranh giới.

Một số ràng buộc khác:

- Class không được mở rộng một `final class`.
- Một class không thể trực tiếp implement một type không phải interface.
- Superclass/interface references phải truy cập được và conform với JVM inheritance constraints.
- Sealed types giới hạn permitted direct subclasses/implementations; check có thể dẫn tới `IncompatibleClassChangeError` nếu class động vi phạm hierarchy.
- Bytecode tham chiếu method/field có descriptor khác runtime API có thể dẫn tới `NoSuchMethodError` / `NoSuchFieldError`.

**Đừng khẳng định mọi lỗi xuất hiện ngay tại `defineClass`:** một số checks xảy ra trong loading/linking, những checks khác được JVM trì hoãn đến lần đầu resolve/invoke references.

## 19. Sealed classes, records và nestmates trong Java 17+

### Sealed classes

Java 17 hỗ trợ `sealed` và `permits`. Bytecode class file lưu danh sách permitted subclasses qua `PermittedSubclasses` attribute. Một class động **không thể tùy ý `extends` sealed superclass** chỉ bằng cách đặt đúng tên trong source. JVM phải kiểm tra permitted direct subclasses phù hợp, module/package constraints và type identity.

Một `sealed` superclass do parent loader định nghĩa không nhất thiết cho child loader định nghĩa subclass trực tiếp từ một package nhìn như cùng package. Hãy xem cả constraints của sealed hierarchy và defining loaders; đừng dựa vào tên type hay attribute được copy thủ công.

### Records

`record` sinh methods/fields/construction contract riêng, với `Record` attribute. Nếu biến đổi bytecode của record, cần giữ đúng `java.lang.Record` superclass, component metadata, canonical constructor semantics và verifier rules. Một class file có attribute lạ không tự thành record hợp lệ.

### Nests và private access

`NestHost` / `NestMembers` attributes biểu thị **nestmates**, cho phép một số private accesses giữa các classes trong cùng nest. JVM xác thực những ràng buộc này; không thể chèn attribute giả để cấp private access từ arbitrary loader. `Lookup.defineHiddenClass(..., NESTMATE)` là API có kiểm soát quyền truy cập; không tương đương gắn binary name tùy ý vào một nest.

## 20. Định nghĩa class thành công chưa đảm bảo constructor/method chạy thành công

Xem lại các giai đoạn:

```text
đọc/generate bytes
        │
        ▼
defineClass(name, bytes, ...)
        │
        ├─ class-file format + identity checks
        ▼
Class<?> type
        │
        ├─ resolveClass(type) / JVM linking
        │     └─ có thể phát hiện verifier/loader errors
        │
        ├─ getDeclaredConstructor(), getMethod()
        │     └─ reflection metadata/access checks
        │
        ├─ newInstance / static method active use
        │     └─ JVM class initialization; <clinit> có thể lỗi
        │
        └─ invoke/field access
              └─ method/field resolution và access checks
```

**Một số việc có thể được JVM làm sớm hơn** sơ đồ, nhưng những observable errors tuân thủ các điểm chương trình cần reference theo đặc tả.

Không được coi `getDeclaredConstructor()` đã chạy constructor. `Constructor.newInstance()` mới tạo object và thực hiện constructor body. Khi body constructor ném exception, reflective call thường bọc trong `InvocationTargetException`; còn `ClassFormatError` hay `IllegalAccessError` là lỗi khác, không nhất thiết do constructor body ném.

### Lỗi static initialization

Nếu `<clinit>` ném exception, lần active use đầu có thể nhận `ExceptionInInitializerError`, và những lần sau với **cùng runtime class** có thể nhận `NoClassDefFoundError` do class erroneous. Gọi lại `loadClass` không tự reset initialization state. Nếu thật sự cần định nghĩa class version khác, thường cần một loader instance mới và lifecycle phù hợp.

## 21. Duplicate definition và an toàn đồng thời khi sinh class

Một custom loader không thể define cùng binary name hai lần trong cùng defining loader. Nếu two threads cùng chạy:

```java
byte[] bytes = /* class-file bytes của generated.Task */;
defineClass("generated.Task", bytes, 0, bytes.length);
```

Đây là **snippet minh họa** trong subclass, không phải Java standalone code. Nếu không phối hợp đúng, một lần define có thể thất bại với `LinkageError` duplicate definition.

Dùng `ClassLoader.loadClass` mặc định giúp bảo vệ thông qua `getClassLoadingLock(name)` và `findLoadedClass(name)`. Nếu override `loadClass` vì child-first, phải xử lý loaded-cache và synchronization chính xác.

### Cần tạo nhiều phiên bản cùng tên?

Không thể “ghi đè Class<?> cũ” bằng `defineClass` trong **cùng loader instance**. Thay vì vậy:

- Tạo **new defining loader** cho generation mới của plugin.
- Giữ shared API ở parent ổn định để cast/contract đúng.
- Ngắt hoạt động cũ, unregister callbacks, dọn threads/`ThreadLocal` và đóng resources.
- Bỏ strong references tới provider instances/`Class<?>`/loader cũ khi muốn JVM có cơ hội unload.
- Không kỳ vọng `URLClassLoader.close()` hoặc GC diễn ra tức thì hay giúp rewrite class đã định nghĩa.

Nếu cần thay code trong cùng JVM mà không đổi loader, có những cơ chế instrumentation/redefinition với giới hạn nghiêm ngặt; **không** giả định chúng có thể tùy ý sửa hierarchy, fields và method signatures.

## 22. Bảng lỗi — phân loại theo thời điểm và nguyên nhân

| Lỗi | Tình huống điển hình | Gợi ý chẩn đoán |
| --- | --- | --- |
| `ClassNotFoundException` | Loader không tìm được bytes cho binary name | Kiểm tra lookup path, parent, JAR/classpath |
| `NoClassDefFoundError` | `name` truyền vào không khớp `this_class`, hoặc dependency/class init thất bại | Phân biệt wrong name với class erroneous/missing dependency |
| `ClassFormatError` | Bytes không tuân `ClassFile` format | Kiểm tra magic, pool, attributes, generator |
| `UnsupportedClassVersionError` | Major/minor version không được JVM hỗ trợ | `javap -verbose`, `java -version`, `javac --release` |
| `VerifyError` | Bytecode vi phạm verification/type-flow constraints | Kiểm tra stack, locals, `StackMapTable`, generator |
| `ClassCircularityError` | Hierarchy có vòng bất hợp lệ | Kiểm tra superclass/interface references |
| `LinkageError` duplicate class | Define cùng name/loader lần thứ hai | `findLoadedClass`, synchronization, loader identity |
| `SecurityException` | Define `java.*` sai loader, package signing/certificates không đồng nhất | Binary name, `ProtectionDomain`, signer set |
| `IllegalAccessError` | Runtime class/member access hoặc package/module restrictions không phù hợp | Defining loaders, runtime package, JPMS |
| `IncompatibleClassChangeError` | Không đúng class/interface/final/sealed/inheritance/linkage contract | Compare binaries, hierarchy, class file version |
| `NoSuchMethodError` / `NoSuchFieldError` | Caller bytecode references không khớp runtime library | Method descriptors, classpath order, version skew |
| `ClassCastException` | Hai runtime types cùng tên nhưng khác defining loader | `getClassLoader()`, `isAssignableFrom` |
| `ExceptionInInitializerError` | Static initializer ném exception | Cause/stacktrace từ lần active use đầu |
| `IllegalAccessException` | Reflection hoặc Lookup không có quyền truy cập | Caller, lookup modes, JPMS exports/opens |
| `InaccessibleObjectException` | Deep reflection bị module encapsulation từ chối | `opens`, target module và caller module |

Một số lỗi có thể xuất hiện nhiều giai đoạn và có dạng phụ thuộc JVM; bảng mô tả **nguyên nhân thường gặp**, không hứa “mỗi lỗi chỉ xảy ra tại một dòng cố định”.

## 23. Chẩn đoán đúng bytecode, đúng loader và đúng runtime

### Công cụ kiểm tra class file

```sh
javap -verbose -classpath generated-out demo.generated.DynamicHello
javap -c -p -classpath generated-out demo.generated.DynamicHello
java -version
```

Quan sát `major version`, `this_class`, superclass/interfaces, method descriptors và attributes. Nếu có Java 21 class mà deployment là Java 17, build phải dùng `--release 17` hoặc chạy trên runtime mới tương thích với artifact đó — **không chỉ đổi header bytes**.

### Quan sát runtime defining loader

Snippet hợp lệ khi đặt trong một class và gọi:

```java
static void describe(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("package=" + type.getPackageName());
}
```

`getClassLoader() == null` thường biểu diễn bootstrap loader. `type.getModule().getName() == null` thường là unnamed module, không phải class không thuộc module object nào.

### HotSpot Unified Logging

```sh
java -Xlog:class+load=info -cp host-out demo.DefineDemo
java -Xlog:help
```

Class loading log giúp thấy nguồn bytecode theo runtime, nhưng có nhiều dòng phụ thuộc implementation; không có stdout chuẩn cố định cho log JVM. `-Xlog` không chứng minh class đã initialized hay constructor đã chạy. Để kiểm tra `<clinit>`, quan sát hành vi program hoặc log class initialization nếu JDK/runtime có hỗ trợ.

### Khi lỗi phát sinh sau defineClass

In **exception type**, **cause chain**, **target binary name**, **defining loader identity**, **module/package** và **class-file version**. Đừng log toàn bộ bytes hoặc path chứa secrets vào log public. Với nhiều plugins, thêm plugin ID/generation để phân biệt hai loaders có cùng class name.

## 24. Quy trình phát hành class động an toàn hơn

1. **Chọn namespace và hợp đồng:** class mới cần public API nào, package nào? Những types nào phải được host/plugin dùng chung?
2. **Quyết định defining loader hoặc Lookup:** chọn `ClassLoader.defineClass` cho namespace riêng hoặc `Lookup.defineClass` khi cần đúng same-package/same-loader privileges.
3. **Chốt Java target runtime:** dùng `javac --release 17` nếu production chạy Java 17; kiểm tra major/minor version khi build.
4. **Sinh/đọc bytes chuẩn:** dùng compiler/bytecode generator có hỗ trợ class-file version, stack maps và attributes liên quan; không chỉnh byte tùy tiện.
5. **Đối chiếu binary name:** `defineClass(name, bytes,...)` dùng tên đúng với `this_class`.
6. **Kiểm tra structural constraints:** superclass, interfaces, final/sealed/record attributes, nest metadata.
7. **Kiểm tra runtime access:** runtime package + defining loader, module readability/exports/opens, package-private/nestmate rules.
8. **Kiểm tra security metadata:** package signer consistency, code source/protection domain, sealing nếu loader áp dụng.
9. **Đồng bộ hóa:** tránh duplicate definitions, dùng loader locking nếu nhiều threads tạo class cùng tên.
10. **Validate ứng dụng:** resolve, instantiate/invoke trong test, kiểm tra missing dependencies, binary signatures và static initializer errors.
11. **Đóng vòng đời:** dùng loader mới cho generation khác, quản lý references và callbacks khi hot-reload.
12. **Bảo vệ môi trường:** nếu bytes đến từ bên thứ ba không tin cậy, dùng isolation/security controls độc lập; class loader không phải sandbox.

### Điều nên kiểm thử tự động

- Version lớn hơn runtime target bị từ chối đúng loại lỗi.
- Corrupt class-file bytes bị từ chối.
- Tên truyền `defineClass` không khớp `this_class` bị báo wrong-name error.
- Trùng class cùng loader không được redefine.
- Cùng Java package text nhưng khác defining loaders không tự có quyền package-private.
- Shared API type identity đúng khi provider/plugin được nạp.
- Class mới ở module/package được quyền truy cập những APIs cần dùng.
- Không có static constructor side effects trước active use nếu thiết kế không yêu cầu.
- Hai generations của plugin có lifecycle/reference cleanup đúng, không giữ classloader cũ không cần thiết.

## 25. Các nhầm lẫn thường gặp

- **“`defineClass` là `new`.”** Sai: nó tạo runtime `Class<?>`, không tạo instance.
- **“Chỉ cần mảng byte bắt đầu bằng CAFEBABE.”** Sai: cả format, pool, descriptors, attributes và verification phải hợp lệ.
- **“Có thể chạy class Java 21 trên JVM Java 17 bằng cách sửa major 65 thành 61.”** Sai: các instructions/APIs/attributes có thể không tương thích.
- **“`name` của `defineClass` chỉ để log.”** Sai: API đối chiếu binary name với bytes và áp ràng buộc namespace.
- **“Hai class cùng `package shared` luôn truy cập package-private của nhau.”** Sai: runtime package còn có defining loader.
- **“`Lookup.defineClass` có thể inject class vào bất cứ loader/module nào.”** Sai: quyền được ràng buộc bởi lookup class và PACKAGE mode.
- **“`setAccessible(true)` sửa được mọi `IllegalAccessError`.”** Sai: runtime bytecode linking checks và module restrictions là chuyện khác.
- **“`ClassFormatError` và `VerifyError` đều là `ClassNotFoundException`.”** Sai: chúng là những lỗi JVM khác nhau.
- **“Class define thành công tức là tất cả method references đã resolve.”** Không chắc; một số resolution có thể lazy.
- **“Đã nạp class, constructor chắc chắn chạy.”** Sai: class initialization và object creation là bước sau.
- **“Có thể define lại cùng class name trong cùng loader khi sửa JAR.”** Không; cần loader mới hoặc một cơ chế redefinition chuyên biệt với giới hạn.
- **“ProtectionDomain làm plugin sandbox tuyệt đối.”** Sai; không thay thế process isolation và security model.
- **“Một JAR chứa `module-info.class` tự trở thành named module khi URLClassLoader đọc.”** Không; JPMS resolution/layers là cơ chế khác.
- **“`IllegalAccessError` luôn xuất hiện ngay ở `defineClass`.”** Không bảo đảm thời điểm nếu symbolic references được resolve về sau.

## 26. Câu hỏi tự kiểm tra

**1. `defineClass` trả gì và chưa làm gì?** Nó trả `Class<?>` của runtime type mới; không tự trả instance, không bắt buộc chạy class initializer.

**2. Với `--release 17`, major version class file là bao nhiêu?** 61.

**3. Class major 65 có chạy được trên Java 17 không?** Không; phiên bản vượt mức hỗ trợ, thường báo `UnsupportedClassVersionError`.

**4. Tại sao `defineClass("a.Other", bytes của a.Widget)` lỗi?** Vì binary name không khớp `this_class`; có thể nhận `NoClassDefFoundError`.

**5. Magic CAFEBABE có đủ để xác nhận class hợp lệ không?** Không. Cần structure/constant-pool/method/attribute/bytecode verification hợp lệ.

**6. `UnsupportedClassVersionError` thuộc họ nào?** Nó kế thừa `ClassFormatError`, thuộc `LinkageError`.

**7. Cùng `package shared` trong source có cho phép package-private access giữa hai defining loaders khác nhau không?** Không; runtime package phụ thuộc defining loader.

**8. Vì sao `Lookup.defineClass` chỉ dùng bytes cùng package với lookup class?** Vì API xác thực PACKAGE lookup privileges và đặt class trong cùng runtime package/loader.

**9. `defineClass` có tự chạy `<clinit>` không?** Không theo mặc định; class initialization được yêu cầu ở active use thích hợp.

**10. Parent-first giúp gì khi plugin dùng host API?** Giúp provider/host dùng cùng `Class<?>` của interface/DTO do parent định nghĩa.

**11. Cùng tên class có thể tồn tại hai phiên bản trong một JVM không?** Có nếu khác defining loaders; không thể định nghĩa cùng binary name hai lần trong cùng defining loader.

**12. `IllegalAccessError` khác `IllegalAccessException` ở đâu?** `IllegalAccessError` thường là linking/runtime access error, còn `IllegalAccessException` là checked exception từ reflection/Lookup API.

**13. `ClassLoader.defineClass` có thể tự inject class vào named module bất kỳ không?** Không; loader/module/Lookup access và JPMS restrictions vẫn áp dụng.

**14. Vì sao `NoClassDefFoundError` không nhất thiết có nghĩa file `.class` mất?** Nó có thể do wrong binary name, lỗi resolution hoặc class đã initialization thất bại.

**15. Cách an toàn để cập nhật implementation class đã được định nghĩa trong plugin loader?** Tạo plugin class loader/generation mới, dùng shared API identity và quản lý vòng đời cũ; không gọi define trùng.

## 27. Tài liệu chuẩn

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `defineClass` overloads, `findClass`, parent delegation, name/package/certificate checks, ProtectionDomain và linking errors.
- [Java SE 17 `MethodHandles.Lookup` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineClass`/`defineHiddenClass`, lookup modes, same-package/loader restrictions.
- [JVMS Java SE 17 — Chapter 4, The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): version numbers, `ClassFile` layout, verification, `Record` và `PermittedSubclasses` attributes.
- [JVMS Java SE 17 — Chapter 5, Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime identity, class loader constraints, access/linking/initialization.
- [JLS Java SE 17 — Chapter 6, Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html): binary names, packages và access rules.
- [Java SE 17 `ProtectionDomain` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): protection domains và code source.
- [JDK 17 `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra major version, pool và bytecode.

**Kết luận:** Khi tạo class động, JVM không chỉ “đọc được bytecode là chạy”. Class file phải có **version và cấu trúc hợp lệ**, binary name/loader identity phải nhất quán, superclass/interfaces/attributes đáp ứng quy tắc linking, và mọi truy cập vẫn chịu **runtime package, JPMS và ProtectionDomain**. Hãy dùng đúng `ClassLoader.defineClass` hoặc `Lookup.defineClass`, kiểm chứng class-file bytes và runtime access ở từng bước, thay vì xử lý mọi thất bại như một lỗi classpath chung.
