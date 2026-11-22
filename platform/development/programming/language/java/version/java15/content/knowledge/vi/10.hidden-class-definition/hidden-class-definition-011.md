# Định nghĩa hidden class: IllegalAccessException, IllegalArgumentException và lỗi liên kết

> **Phạm vi:** Java 15 giới thiệu hidden classes qua JEP 371 và API `MethodHandles.Lookup.defineHiddenClass`. Đây vẫn là API chính thức trong Java 17+ và các bản Java hiện đại. Bài này tập trung vào **ba nhóm lỗi khi định nghĩa class ẩn**: thiếu quyền `IllegalAccessException`; đầu vào không hợp lệ về package/loại class `IllegalArgumentException`; và các lỗi ở tầng JVM như `ClassFormatError`, `VerifyError`, `LinkageError`. Cần phân biệt thêm **lỗi khởi tạo class**, vì tham số `initialize` có thể kích hoạt chúng ngay tại lời gọi.

## 1. Định nghĩa hidden class thực chất làm gì?

API của Java:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classFileBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );
Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Đây là **mảnh mã minh họa**: giả định đã có `lookup` và `byte[] classFileBytes` hợp lệ; không phải chương trình độc lập.

`defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` nằm trong `java.lang.invoke.MethodHandles.Lookup`:

1. Nhận **bytes của một class file Java hợp lệ** (không phải chuỗi mã nguồn `.java`).
2. Xác thực **quyền** của `Lookup`, **package** của class trong bytes và những yêu cầu của định dạng class file.
3. JVM tạo một **hidden class** mới trong **cùng runtime package, module, defining loader và protection domain** theo hợp đồng API, rồi **link** class đó.
4. Nếu `initialize == true`, JVM **khởi tạo** class (chạy `<clinit>` nếu có).
5. Nếu thành công, API trả về `Lookup` mới có lookup class là hidden class; dùng `lookupClass()` để nhận `Class<?>`. `Class.isHidden()` sẽ là `true`.

Hidden class không có **binary name** để các lớp khác định danh qua constant pool như named class, nhưng vẫn có class object, instance, method handles và các member được truy cập theo quyền hợp lệ. Đây là đặc tính khác với các nhóm lỗi trong bài.

**Quan trọng:** có thể xảy ra lỗi ở các giai đoạn khác nhau. Việc `defineHiddenClass` đã tạo xong một class **không bảo đảm** mọi symbolic reference trong mọi phương thức sẽ phân giải thành công về sau, bởi JVM có thể thực hiện **một phần resolution theo nhu cầu**. Ngược lại, các lỗi bắt buộc khi tạo/link class có thể xuất hiện ngay ở lời gọi.

## 2. Sơ đồ phân loại lỗi

~~~text
Lookup.defineHiddenClass(bytes, initialize, options)
  |
  +-- Lookup không có full privilege access
  |     -> IllegalAccessException           [checked exception]
  |
  +-- Class trong bytes khác package với lookup,
  |   hoặc class file mang ACC_MODULE (module-info)
  |     -> IllegalArgumentException         [runtime exception]
  |
  +-- Bytes không có cấu trúc ClassFile hợp lệ
  |     -> ClassFormatError                 [LinkageError]
  |
  +-- Class-file version không được JVM hỗ trợ
  |     -> UnsupportedClassVersionError     [ClassFormatError]
  |
  +-- Bytecode không vượt qua verification
  |     -> VerifyError                      [LinkageError]
  |
  +-- Superclass/interface sai quan hệ kiểu,
  |   chu trình lớp hoặc không thể link vì nguyên nhân khác
  |     -> IncompatibleClassChangeError,
  |        ClassCircularityError, hoặc LinkageError tương ứng
  |
  +-- Tham số initialize=true
  |     -> Chạy class initializer
  |     -> Nếu <clinit> ném exception thông thường:
  |        ExceptionInInitializerError
  |        (một LinkageError, thường giữ exception gốc làm cause)
  |
  +-- Thành công
        -> Lookup mới trên hidden class
        -> returnedLookup.lookupClass().isHidden() == true
~~~

Đây là **sơ đồ chẩn đoán khái niệm**, không hàm ý mỗi lỗi xảy ra cố định theo trình tự hoặc một lỗi linker chỉ có thể xuất hiện tại đúng một thời điểm.

### Bảng quyết định nhanh

| Nhóm | Kiểu lỗi | Điều kiện điển hình | Hướng xử lý |
| --- | --- | --- | --- |
| **Quyền** | `IllegalAccessException` | `Lookup` không có **full privilege access** | Cấp/nhận đúng lookup trong lớp có quyền; không cố vượt module boundary |
| **Đầu vào, ngữ cảnh** | `IllegalArgumentException` | Class trong bytes thuộc package khác lookup; bytes mô tả module thay vì class/interface | Sửa package hoặc nguồn class file |
| **Định dạng file** | `ClassFormatError` | Bytes không mô tả cấu trúc class file hợp lệ | Kiểm tra nguồn bytes, tệp, sinh bytecode và checksum |
| **Phiên bản** | `UnsupportedClassVersionError` | Class file có major/minor version JDK hiện tại không hỗ trợ | Dùng runtime tương thích hoặc biên dịch đúng `--release` |
| **Verification** | `VerifyError` | Bytecode vi phạm quy tắc an toàn/kiểu dữ liệu JVM | Sửa bytecode generator, stack map frames, descriptor, control flow |
| **Linking** | `LinkageError` (và lớp con) | JVM không liên kết được class hoặc phụ thuộc | Xem classpath/module path, version nhị phân, superclass/interfaces và cause |
| **Initialization** | `ExceptionInInitializerError` | `initialize=true`, static initializer ném ngoại lệ không phải `Error` | Sửa logic `static` và nguyên nhân gốc; không hiểu nhầm là thiếu quyền |

Ba kiểu đầu tiên trong đề bài **không đồng cấp**: `IllegalAccessException` là checked exception; `IllegalArgumentException` là unchecked runtime exception; còn `LinkageError` kế thừa `Error`, biểu diễn lỗi cấp VM/linking và thường không nên coi là sự kiện nghiệp vụ có thể khôi phục đơn giản.

## 3. `IllegalAccessException`: quyền của Lookup chưa đủ

### Điều kiện chính xác

Theo hợp đồng `Lookup.defineHiddenClass`, lookup được dùng để gọi method phải có **full privilege access**. Việc đó cần thiết vì JVM đặt hidden class mới vào module của lookup class.

Một lookup được lấy bằng:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

thông thường có full privilege access đối với **lớp gọi hợp lệ** tại nơi thực hiện lời gọi. Trong khi đó:

~~~java
MethodHandles.Lookup publicOnly =
        MethodHandles.publicLookup();
~~~

chỉ mang quyền truy cập công khai tối thiểu; **không đủ** để định nghĩa hidden class.

Ví dụ minh họa (giả sử `bytes` hợp lệ):

~~~java
// Đoạn mã trong phương thức khai báo throws IllegalAccessException:
MethodHandles.publicLookup().defineHiddenClass(bytes, false);
~~~

Kết quả là **`IllegalAccessException`**, vì quyền không đủ — **không** có nghĩa `bytes` sai và **không** nhất thiết do class trong bytes khai báo `private`.

### Vì sao không chỉ gọi `publicLookup()` hoặc `lookup.in(...)`?

`Lookup` là một **capability** mang ngữ cảnh class/module cùng tập quyền. Những phương thức biến đổi như `in(...)` hay `dropLookupMode(...)` có thể **làm mất** quyền, không tự khôi phục full privilege. Đặc biệt:

- `MethodHandles.publicLookup()` không có full privilege.
- `MethodHandles.lookup()` cần được gọi từ đúng **lớp có thẩm quyền** tạo hidden class.
- `MethodHandles.privateLookupIn(target, callerLookup)` là API khác, có kiểm tra quyền truy cập module và package riêng. Không giả định **mọi** lookup mà nó trả về đều đủ full privilege để `defineHiddenClass`, đặc biệt khi liên quan module khác và lookup bị hạn chế.
- Nếu muốn tạo class trong một package/module khác, cách đúng là thiết kế một **điểm định nghĩa đáng tin cậy** bên trong package/module đích hoặc dùng cơ chế được chủ thể đó cho phép, không cố tạo một “lookup toàn quyền” từ mã không được ủy quyền.

Có thể kiểm tra:

~~~java
// Mảnh mã minh họa:
System.out.println(MethodHandles.lookup().hasFullPrivilegeAccess());
System.out.println(MethodHandles.publicLookup().hasFullPrivilegeAccess());
~~~

Trong trường hợp gọi `MethodHandles.lookup()` từ mã ứng dụng thông thường hợp lệ, lần lượt nhận `true` và `false`. API `hasFullPrivilegeAccess()` phản ánh quyền của lookup; thay vì dựa vào tên lớp hay access modifier một cách phỏng đoán, hãy kiểm tra đối tượng lookup thật.

### Chẩn đoán khi gặp lỗi

1. Xác định **lệnh nào** thật sự ném `IllegalAccessException`. `defineHiddenClass`, `privateLookupIn` và `findConstructor` đều có thể ném cùng tên exception nhưng với điều kiện khác nhau.
2. In thông tin ngữ cảnh của lookup như `lookup.lookupClass()`, `lookup.lookupModes()` và `lookup.hasFullPrivilegeAccess()` trong log nội bộ phù hợp, không log bí mật.
3. Kiểm tra lookup đã đi qua `in(...)`, `dropLookupMode(...)` hoặc được truyền từ plugin khác chưa.
4. Di chuyển bước định nghĩa class về thành phần đáng tin cậy có full privilege và package phù hợp; đừng khắc phục bằng việc tắt kiểm soát module.

**Không nhầm:** `IllegalAccessException` (checked) khác với `IllegalAccessError` (một dạng lỗi ở quá trình resolution/linking/runtime). Lỗi thứ hai có thể xuất hiện khi bytecode cố truy cập member không còn cho phép ở runtime; cách điều tra là symbolic access/module/ABI, không chỉ thay đối tượng `Lookup`.

## 4. `IllegalArgumentException`: bytes và lookup không cùng package

### Điều kiện chính xác của API

`Lookup.defineHiddenClass` yêu cầu **class được khai báo trong class-file bytes** thuộc **cùng package** với lookup class. Nếu không, method ném `IllegalArgumentException`. API còn nêu trường hợp bytes không mô tả class/interface thông thường, chẳng hạn `ACC_MODULE` (cấu trúc `module-info.class`).

Ví dụ:

~~~text
app.Host                    (lookup class; package app)
other.GeneratedTask         (class được ghi trong bytes; package other)

Host.lookup().defineHiddenClass(bytesOfOtherGeneratedTask, false)
  -> IllegalArgumentException
~~~

Không giải quyết vấn đề bằng cách **đổi đường dẫn file bytes** thành `app/GeneratedTask.class` trong khi class file vẫn mã hóa tên `other/GeneratedTask`. Package được quyết định bởi **tên class thực trong class file**, không phải nơi bạn đặt tệp trên filesystem.

### Phân biệt ba yếu tố hay bị nhầm

- **Source package:** dòng `package app;` trong `.java`.
- **Class-file internal name:** dạng `app/GeneratedTask` nằm trong `CONSTANT_Class_info` của `this_class` trong class file đã biên dịch.
- **Runtime package:** chịu ảnh hưởng của package name và defining class loader/module; `defineHiddenClass` dùng ngữ cảnh của lookup class và định nghĩa hidden class cùng runtime package theo hợp đồng.

Nếu bytecode generator sửa tên class, cần bảo đảm **tất cả thông tin class file liên quan đều hợp lệ**, không chỉ thay đoạn văn bản `this_class` một cách thủ công. Việc sai bytes có thể chuyển thành `ClassFormatError` hoặc `VerifyError` thay vì `IllegalArgumentException`.

### Vì sao `public` không giải quyết được?

Một class được biên dịch với modifier `public` trong package `other` vẫn **khác package** với `app.Host`. `public` không làm thay đổi điều kiện package của `defineHiddenClass`. Tương tự, option `NESTMATE`/`STRONG` không phải công tắc bỏ qua yêu cầu này.

### Các trường hợp đầu vào khác

- `bytes == null` hoặc `options == null`: API quy định `NullPointerException`.
- Bytes bị hỏng không đúng định dạng class file: `ClassFormatError`, **không nên gom** vào `IllegalArgumentException`.
- Bytes được biên dịch bằng class-file version mới hơn JVM hỗ trợ: `UnsupportedClassVersionError`, **không** phải lỗi package.
- Lookup chưa đủ quyền: `IllegalAccessException` ngay cả khi class bytes có package đúng.

Không thay đổi package module hoặc bỏ qua quyền truy cập một cách tùy tiện chỉ để “chạy được”.

## 5. Lỗi liên kết: phân biệt tạo class, verification, resolution và initialization

### 5.1. `ClassFormatError` — class file sai cấu trúc

JVM phải đọc một cấu trúc `ClassFile` hợp lệ: magic bytes, constant pool, field/method tables, attributes và các ràng buộc định dạng. Nếu nhận mảng byte bất kỳ không phải class file, `defineHiddenClass` có thể ném `ClassFormatError` theo hợp đồng API.

~~~java
byte[] notAClass = {0x01, 0x02, 0x03};
~~~

Đây không phải class file hợp lệ. **`ClassFormatError` là một lớp con của `LinkageError`**; không nên bắt `IllegalArgumentException` với kỳ vọng nó sẽ xử lý mọi bytes sai.

Trong thực tế, kiểm tra lại công đoạn đọc bytes (không đọc nhầm source `.java`/text/JSON), việc sinh bytecode, độ dài tệp và checksum của class file.

### 5.2. `UnsupportedClassVersionError` — phiên bản class file không được hỗ trợ

Class file có **major/minor version**. Nếu runtime không hỗ trợ phiên bản trong bytes, API có thể ném `UnsupportedClassVersionError`, một nhánh của `ClassFormatError`/`LinkageError`.

Ví dụ, Java 17 thường dùng class-file major version 61; Java 15 dùng major version 59. Đây chỉ là các **mốc giải thích**; trong môi trường thực tế, nên xác định bằng `javap -verbose` hoặc metadata của công cụ build.

Không sửa bằng cách đổi 2 byte version của một file mới thành version cũ một cách tùy tiện. **Giải pháp đúng** là dùng JDK hỗ trợ class file hoặc biên dịch lại với `javac --release <target>` và bộ API tương thích target.

### 5.3. `VerifyError` — bytecode không đáp ứng verification

Một class file có thể hợp lệ về **cấu trúc** nhưng không hợp lệ theo các quy tắc kiểm tra kiểu và luồng thực thi của JVM, ví dụ stack manipulation, method descriptor, access/type constraints hoặc stack map frames không khớp.

Khi JVM verification thất bại, có thể xuất hiện `VerifyError`. Đây là **lỗi bytecode/runtime**, không phải một checked exception của `Lookup`. Công cụ sinh bytecode cần được sửa và kiểm tra bằng JDK mục tiêu.

### 5.4. `IncompatibleClassChangeError` và `ClassCircularityError`

Đặc tả `defineHiddenClass` nêu các tình huống điển hình:

- `IncompatibleClassChangeError` khi type được khai báo làm **superclass** lại thực sự là interface, hoặc type được khai báo làm **superinterface** lại không phải interface.
- `ClassCircularityError` khi có quan hệ kế thừa/triển khai vòng bất hợp lệ trong quá trình xác định kiểu.

Đây là lỗi tính nhất quán của cấu trúc lớp và các dependency được link. Chúng không được sửa chỉ bằng cách cấp quyền full privilege cho lookup.

### 5.5. Lỗi resolution/linkage do dependency

Một số symbolic reference trong class file có thể cần đến superclass, interface, field, method hoặc class khác. Khi thiếu dependency hoặc phiên bản nhị phân không tương thích, JVM có thể ném các lỗi thuộc họ `LinkageError`, chẳng hạn:

- `NoClassDefFoundError`: class được yêu cầu không thể được tìm/định nghĩa tại runtime hoặc đã bị đánh dấu khởi tạo lỗi.
- `NoSuchMethodError` / `NoSuchFieldError`: bytecode viện dẫn thành viên không tồn tại trong định nghĩa runtime thực tế.
- `IllegalAccessError`: symbolic access không được phép ở runtime.
- `IncompatibleClassChangeError`: hợp đồng type/member thay đổi theo cách không tương thích.

**Lưu ý quan trọng:** một số symbolic reference được phân giải **muộn**. Vì thế, `defineHiddenClass(bytes, false)` trả về thành công **không chứng minh** rằng mọi method của hidden class sẽ thực thi thành công. Lỗi có thể nổ ở `find...`/khi invoke hoặc lúc class được dùng thực sự, tùy dependency và cơ chế resolution của JVM.

### 5.6. Khởi tạo class: `ExceptionInInitializerError` là lỗi khác verification

Nếu `initialize=true`, `defineHiddenClass` còn yêu cầu JVM **khởi tạo** hidden class mới. Code trong static field initializers hoặc khối `static { ... }` có thể ném exception.

~~~java
public class BrokenInitializer {
    static {
        if (System.nanoTime() != Long.MIN_VALUE) {
            throw new IllegalStateException("init failed");
        }
    }
}
~~~

Đây là **mã minh họa**, chưa phải chương trình chạy đầy đủ. Đoạn `if` bảo đảm compiler chấp nhận initializer có thể hoàn tất theo đường đi kiểm tra tĩnh; khi điều kiện đúng ở runtime, nó ném exception.

Nếu static initializer ném một exception không phải `Error`, JVM thường bọc nó trong **`ExceptionInInitializerError`**. Đây là một lớp con của `LinkageError` và chứa nguyên nhân gốc qua `getCause()`. Nếu initializer ném một `Error`, quy tắc lan truyền khác; không hứa mọi lỗi initializer đều là `ExceptionInInitializerError`.

Nếu `initialize=false`, JVM **không chủ động chạy `<clinit>` ngay tại lúc định nghĩa**. Tuy nhiên class vẫn được link, và lần sử dụng về sau có thể kích hoạt initialization lỗi. Sau khi initialization thất bại, những lần dùng lại class runtime cùng định danh có thể dẫn đến `NoClassDefFoundError`.

### 5.7. Không dùng `catch (Exception e)` để mong bắt mọi linkage error

Cấu trúc phân cấp đơn giản:

~~~text
Throwable
├── Exception
│   ├── RuntimeException
│   │   └── IllegalArgumentException
│   └── IllegalAccessException
└── Error
    └── LinkageError
        ├── ClassFormatError
        │   └── UnsupportedClassVersionError
        ├── VerifyError
        ├── IncompatibleClassChangeError
        │   └── IllegalAccessError
        ├── ClassCircularityError
        ├── NoClassDefFoundError
        └── ExceptionInInitializerError
~~~

Do đó:

- `catch (IllegalAccessException e)` xử lý lỗi quyền được khai báo.
- `catch (IllegalArgumentException e)` xử lý trường hợp đầu vào/package không hợp lệ.
- `catch (LinkageError e)` có thể dùng tại **ranh giới sinh class** để log và chuyển lỗi lên tầng điều phối, nhưng không nên **nuốt lỗi** rồi tiếp tục như class đã được tạo thành công.
- `catch (Exception e)` **không bắt** `LinkageError`, `VerifyError`, `ClassFormatError`, v.v.
- `catch (Throwable e)` cũng bắt cả các tình trạng nghiêm trọng như `OutOfMemoryError`; tránh dùng bừa bãi để “tự phục hồi”.

## 6. Demo chạy được: phân biệt quyền, package, class-file lỗi và initializer

Ví dụ sau được thiết kế để dùng **JDK 17+** và tạo những tình huống lỗi **chủ động, có kiểm soát**. Không yêu cầu thư viện sinh bytecode ngoài JDK.

Tạo cây file:

~~~text
project/
├── HiddenErrorsDemo.java
├── ValidTemplate.java
├── FailingInitTemplate.java
└── foreign/
    └── ForeignTemplate.java
~~~

Chạy các lệnh biên dịch bên dưới trong thư mục `project/`.

### File 1 — `ValidTemplate.java`

~~~java
public class ValidTemplate {
    public static String message() {
        return "ready";
    }
}
~~~

Đây là class file hợp lệ trong **unnamed package**. Demo đọc bytes của `ValidTemplate.class` để tạo một hidden class mới; nó không cần tạo instance của named class `ValidTemplate`.

### File 2 — `FailingInitTemplate.java`

~~~java
public class FailingInitTemplate {
    static {
        if (shouldFail()) {
            throw new IllegalStateException("init failed");
        }
    }

    private static boolean shouldFail() {
        return true;
    }
}
~~~

Đây là class file hợp lệ trong unnamed package nhưng `<clinit>` ném `IllegalStateException` ở runtime. Compiler chấp nhận khối `static` vì điều kiện không phải biểu thức hằng tại compile time.

### File 3 — `foreign/ForeignTemplate.java`

~~~java
package foreign;

public class ForeignTemplate {
    public static void work() {
    }
}
~~~

Class này thuộc **package foreign**, khác package của `HiddenErrorsDemo`. Chỉ dùng bytes của nó để tái hiện `IllegalArgumentException`.

### File 4 — `HiddenErrorsDemo.java`

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class HiddenErrorsDemo {
    public static void main(String[] args) throws Throwable {
        byte[] valid = Files.readAllBytes(
                Path.of("ValidTemplate.class"));
        byte[] foreign = Files.readAllBytes(
                Path.of("foreign", "ForeignTemplate.class"));
        byte[] failingInit = Files.readAllBytes(
                Path.of("FailingInitTemplate.class"));

        MethodHandles.Lookup trusted = MethodHandles.lookup();

        // 1. Lookup công khai không có full privilege access.
        try {
            MethodHandles.publicLookup()
                    .defineHiddenClass(valid, false);
        } catch (IllegalAccessException expected) {
            System.out.println("ACCESS: IllegalAccessException");
        }

        // 2. Class bytes thuộc package foreign, lookup ở unnamed package.
        try {
            trusted.defineHiddenClass(foreign, false);
        } catch (IllegalArgumentException expected) {
            System.out.println("PACKAGE: IllegalArgumentException");
        }

        // 3. Bytes không phải ClassFile hợp lệ.
        try {
            trusted.defineHiddenClass(
                    new byte[]{0x01, 0x02, 0x03}, false);
        } catch (ClassFormatError expected) {
            System.out.println("FORMAT: ClassFormatError");
        }

        // 4. Major version 32767 vượt ngoài các JDK hiện hành.
        byte[] futureVersion = valid.clone();
        futureVersion[6] = (byte) 0x7f;
        futureVersion[7] = (byte) 0xff;
        try {
            trusted.defineHiddenClass(futureVersion, false);
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("VERSION: UnsupportedClassVersionError");
        }

        // 5. Lỗi khởi tạo khi initialize=true.
        try {
            trusted.defineHiddenClass(failingInit, true);
        } catch (ExceptionInInitializerError expected) {
            System.out.println(
                    "INIT: " + expected.getCause()
                            .getClass().getSimpleName());
        }

        // 6. Trường hợp thành công.
        MethodHandles.Lookup hiddenLookup =
                trusted.defineHiddenClass(valid, false);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        MethodHandle message = hiddenLookup.findStatic(
                hiddenType,
                "message",
                MethodType.methodType(String.class));

        System.out.println("HIDDEN: " + hiddenType.isHidden());
        System.out.println("CALL: " + (String) message.invokeExact());
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac ValidTemplate.java FailingInitTemplate.java foreign/ForeignTemplate.java HiddenErrorsDemo.java
java HiddenErrorsDemo
~~~

**Stdout dự kiến, theo đúng các điều kiện chủ động của chương trình:**

~~~text
ACCESS: IllegalAccessException
PACKAGE: IllegalArgumentException
FORMAT: ClassFormatError
VERSION: UnsupportedClassVersionError
INIT: IllegalStateException
HIDDEN: true
CALL: ready
~~~

Giải thích:

1. `publicLookup()` không đủ full privilege, nên API trả `IllegalAccessException`.
2. `ForeignTemplate` là một class file hợp lệ nhưng thuộc package `foreign`, nên điều kiện **same package** không thỏa, dẫn đến `IllegalArgumentException`.
3. Mảng ba byte không phải một `ClassFile`, nên JVM báo `ClassFormatError`, một loại `LinkageError`.
4. Class bytes ban đầu hợp lệ; ta chỉ đổi **major version** sang `0x7fff` (32767), không được các JDK hiện đại hỗ trợ, nên có `UnsupportedClassVersionError`. Chỉnh byte này chỉ để **minh họa lỗi**, tuyệt đối không phải cách tương thích hóa production bytecode.
5. `FailingInitTemplate` có initializer ném `IllegalStateException`; với `initialize=true` JVM chạy initializer của **bản hidden class mới** và báo `ExceptionInInitializerError` có cause `IllegalStateException`. Code chỉ in tên cause.
6. `trusted.defineHiddenClass(valid, false)` tạo một hidden class hợp lệ. API `findStatic` nhận `Class<?>` đã tạo thay vì dùng binary name từ class khác, và method handle gọi phương thức `message()` trả `ready`.

**Điều kiện chạy:** thư mục làm việc phải có các file `.class` như lệnh `javac` sinh ra. Nếu chạy từ thư mục khác, lỗi `NoSuchFileException` chỉ là lỗi đường dẫn file; không phải lỗi của `defineHiddenClass`. Bộ mã này không dùng preview feature. Không có giả định về hậu tố tên động của hidden class.

Một phép kiểm tra tương thích Java 15 (với JDK có hỗ trợ `--release 15`) là:

~~~bash
javac --release 15 ValidTemplate.java FailingInitTemplate.java foreign/ForeignTemplate.java HiddenErrorsDemo.java
~~~

Ví dụ không yêu cầu runtime Java 15 cũ; hãy chạy với một JDK hiện đại được dự án bảo trì và cập nhật.

## 7. Đọc stack trace đúng giai đoạn

### Trường hợp A — thiếu quyền

~~~text
java.lang.IllegalAccessException: ...
    at java.base/java.lang.invoke.MethodHandles$Lookup.defineHiddenClass(...)
~~~

Điểm cần kiểm tra là **nguồn `Lookup`**: ai tạo, có `hasFullPrivilegeAccess()` không, và đã bị hạn chế bởi `in`/`dropLookupMode` chưa. Đây không nhất thiết là lỗi class-file bytes.

### Trường hợp B — class bytes khác package

~~~text
java.lang.IllegalArgumentException: ...
    at java.base/java.lang.invoke.MethodHandles$Lookup.defineHiddenClass(...)
~~~

Kiểm tra internal class name trong bytes, package thực của lookup class và loader/module liên quan. Không sửa sai bằng việc đổi path tên file.

### Trường hợp C — lỗi định dạng/verification/linking

~~~text
java.lang.VerifyError: ...
    at ...
~~~

Hoặc:

~~~text
java.lang.NoClassDefFoundError: ...
    at ...
Caused by: ...
~~~

Cần đọc **loại error cụ thể** và chuỗi cause, không chỉ thấy có chữ `Error` rồi quy về `IllegalArgumentException`. Tùy giai đoạn, lỗi có thể xuất hiện lúc `defineHiddenClass` hoặc tại lời gọi method về sau.

### Trường hợp D — initializer

~~~text
java.lang.ExceptionInInitializerError
    at ...
Caused by: java.lang.IllegalStateException: init failed
    at ...
~~~

Đối với trường hợp này, phải tìm code của **static initializer**/static field initialization và cause gốc. `initialize=false` có thể dời thời điểm phát sinh lỗi, chứ **không làm cho code initializer lỗi trở nên hợp lệ**.

**Cách trình bày stack trace trên là mẫu định hướng**, không phải dự đoán nguyên văn mọi dòng. Số dòng, tên module và thứ tự stack frames thay đổi theo JDK và cách class được sinh.

## 8. Hướng điều tra trong dự án sử dụng generated class

Một checklist có thể áp dụng:

1. **Đóng khung thời điểm lỗi:** khi đọc file, gọi `defineHiddenClass`, gọi `find...`, invoke method handle, hay lần đầu dùng class?
2. **Ghi exception chính xác:** `IllegalAccessException`, `IllegalArgumentException`, hay một **lớp con của `LinkageError`**? Đối với initializer, xem `getCause()`.
3. **Kiểm tra Lookup:** `lookupClass()`, `lookupModes()`, `hasFullPrivilegeAccess()`; đừng ghi lại dữ liệu nhạy cảm. Nhớ quyền full privilege là yêu cầu riêng cho `defineHiddenClass`, nghiêm hơn một số thao tác lookup khác.
4. **Kiểm tra bytes:** nguồn bytes phải là **class file**, không phải source/zip/file text; kiểm tra độ dài, magic `CAFEBABE`, class-file version và file bị cắt cụt.
5. **Kiểm tra đúng package:** đọc `this_class` bằng `javap -v` hoặc công cụ bytecode có tin cậy; so package với lookup class.
6. **Kiểm tra lớp phụ thuộc:** superclass/interface phải tồn tại và có type đúng; binary version và module graph không mâu thuẫn.
7. **Kiểm tra verification:** nếu `VerifyError`, xem generator, stack frames, descriptor và control-flow.
8. **Kiểm tra initialize flag:** `true` chạy static initialization ở giai đoạn định nghĩa; `false` trì hoãn cho tới khi cần. Không thay đổi flag chỉ để che lỗi.
9. **Cô lập trong môi trường test:** tái hiện một class file tối thiểu như demo, không tải và chạy bytes không tin cậy trong production.
10. **Đối chiếu công cụ/build:** đảm bảo compiler/bytecode generator phát class-file version phù hợp JDK đang chạy.

Có thể kiểm tra file class trước khi thực thi:

~~~bash
javap -v ValidTemplate.class
javap -v foreign/ForeignTemplate.class
~~~

Trong output, chú ý `major version`, `this_class`, tên internal class, superclass và interfaces. Đây là bước kiểm tra class file **ngoài môi trường runtime**; nó không thay thế kiểm tra `Lookup` hoặc việc JVM resolution khi chạy thật.

### Xử lý lỗi trong framework

Tại ranh giới **plugin/code generation** được giám sát, có thể phân loại:

~~~java
// Minh họa bên trong một phương thức, giả định có lookup và bytes.
try {
    MethodHandles.Lookup created =
            lookup.defineHiddenClass(bytes, false);
    // Lưu created hoặc created.lookupClass() để sử dụng.
} catch (IllegalAccessException e) {
    // Sai capability/lookup; báo lỗi cấu hình quyền.
    throw new IllegalStateException("Lookup lacks full privilege", e);
} catch (IllegalArgumentException e) {
    // Sai package/type class-file; báo lỗi đầu vào/generator.
    throw new IllegalStateException("Invalid hidden-class context", e);
} catch (LinkageError e) {
    // Lỗi class file, VM verification hoặc binary dependencies.
    // Ghi thông tin chẩn đoán rồi để lỗi lan truyền.
    throw e;
}
~~~

Chú ý đoạn trên **không phải một ứng dụng chạy độc lập**; nó cho thấy cách phân loại ở ranh giới đã tin cậy. Với lỗi `Error`, khuyến nghị **báo cáo và dừng operation liên quan** thay vì nuốt lỗi để chạy tiếp với trạng thái class chưa chắc hợp lệ.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| “`IllegalAccessException` là do class bytes khai báo `private`” | Thường là lookup thiếu **full privilege** | Kiểm tra `hasFullPrivilegeAccess()` và nguồn lookup |
| “`publicLookup()` là đủ để tạo class public” | `defineHiddenClass` không dùng điều kiện public-only | Dùng lookup toàn quyền được cấp hợp lệ |
| “`IllegalArgumentException` có nghĩa mọi bytes đều sai định dạng” | Sai package/type khác `ClassFormatError` | Tách lỗi validation package và cấu trúc bytecode |
| “Đặt file vào cùng thư mục là cùng package” | Package được ghi trong bytes và ngữ cảnh lookup | Kiểm tra package khai báo/internal name |
| “`UnsupportedClassVersionError` chỉ cần sửa số version trên class file” | Bytecode/API mới có thể không tương thích | Biên dịch lại đúng target hoặc nâng JDK |
| “`VerifyError` là lỗi Java source thông thường” | Có thể do generator phát bytecode sai dù source ứng dụng biên dịch | Kiểm tra classfile/stack maps/descriptor |
| “`catch (Exception)` bắt mọi LinkageError” | `LinkageError` thuộc nhánh `Error` | Có thể bắt `LinkageError` tại ranh giới để log, nhưng không nuốt |
| “`initialize=false` bảo đảm class không bao giờ khởi tạo lỗi” | Initialization vẫn xảy ra khi class được sử dụng | Sửa static initializer và dependency |
| “`NESTMATE` tự cấp full privilege” | Option không khắc phục lookup thiếu quyền | Nhận lookup full privilege trước khi gọi |
| “Thành công ở `defineHiddenClass` nghĩa là mọi reference đã resolve” | Resolution có thể bị trì hoãn | Kiểm tra lời gọi runtime và dependency |
| “Dùng tên hidden class để tự giải quyết lỗi liên kết” | Hidden class không có binary name tìm bằng loader thông thường | Dùng runtime `Lookup`/`Class<?>`/method handles theo hợp đồng |

## 10. Bài tập thực hành

**Bài 1.** Cùng `byte[]` class file hợp lệ, tại sao `MethodHandles.publicLookup().defineHiddenClass(bytes, false)` có thể thất bại dù class file khai báo `public`?

**Đáp án:** `defineHiddenClass` cần **full privilege access** của `Lookup`. `publicLookup()` không có đặc quyền này, nên ném checked `IllegalAccessException`.

**Bài 2.** `Host` nằm trong package `com.app`. Bytecode generator tạo class `com.runtime.Task`. Đâu là nhóm lỗi trực tiếp do package khác?

**Đáp án:** `IllegalArgumentException` nếu lookup của `com.app.Host` có quyền hợp lệ nhưng class bytes mô tả class ở package khác. Cần tạo bytes cùng package với lookup hoặc dùng điểm định nghĩa đáng tin cậy ở package đúng, không chỉ di chuyển tệp.

**Bài 3.** Một class file bắt đầu bằng bytes bất kỳ thay vì cấu trúc `ClassFile`, nên bắt `IllegalArgumentException` hay `ClassFormatError`?

**Đáp án:** `ClassFormatError` là lỗi đặc tả cho bytes không phải class file; nó thuộc `LinkageError`.

**Bài 4.** Hai phiên bản của một thư viện khác nhau khiến runtime không tìm được method mà bytecode viện dẫn. Đây có phải `IllegalAccessException` của `defineHiddenClass` không?

**Đáp án:** Không. Đây thường là **lỗi liên kết/resolution**, ví dụ `NoSuchMethodError` khi resolution xảy ra. Cần kiểm tra binary compatibility/classpath/module path, không chỉ quyền lookup.

**Bài 5.** Một hidden class có static initializer ném `IllegalStateException`. Sự khác nhau giữa `initialize=true` và `initialize=false` là gì?

**Đáp án:** `true` kích hoạt initialization ngay ở `defineHiddenClass`, có thể ném `ExceptionInInitializerError`; `false` không chủ động chạy initializer ngay, nhưng lỗi vẫn có thể xảy ra khi class được sử dụng lần đầu.

**Bài 6.** Vì sao không nên khắc phục mọi lỗi bằng `catch (Throwable) { }`?

**Đáp án:** Vì sẽ che lỗi VM/LinkageError/OutOfMemoryError và để hệ thống tiếp tục trong trạng thái không hợp lệ. Nên phân loại cụ thể, ghi log có nguyên nhân và để lỗi nghiêm trọng được xử lý ở ranh giới thích hợp.

## 11. Nguồn chính thức và kiến thức còn sử dụng

- **JEP 371 — Hidden Classes (Java 15):** https://openjdk.org/jeps/371
- **Oracle Java SE 17 — MethodHandles.Lookup.defineHiddenClass():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)
- **Oracle Java SE 17 — Class.isHidden():** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden()
- **Oracle Java SE 17 — LinkageError và lớp con:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- **JVM Specification — Linking:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **JVM Specification — Class file format:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html

**Kết luận:** hãy phân biệt **lỗi quyền của `Lookup`** (`IllegalAccessException`), **class bytes không thuộc ngữ cảnh hợp lệ để định nghĩa** (`IllegalArgumentException`), và **lỗi class file/JVM linking hoặc initialization** (`ClassFormatError`, `VerifyError`, `LinkageError`, `ExceptionInInitializerError`). Xác định chính xác giai đoạn và loại lỗi sẽ đưa bạn đến giải pháp đúng: cấp capability hợp lệ, tạo bytes đúng package, sửa bytecode/dependency hoặc sửa static initializer.
