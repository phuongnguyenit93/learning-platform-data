# Lookup.defineHiddenClass và mảng byte class file trong Java 15+

## 1. Mục tiêu

Từ **Java 15**, Java SE cung cấp API `MethodHandles.Lookup.defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` để tạo **hidden class** trực tiếp từ một mảng byte mang cấu trúc **JVM class file** hợp lệ. Đây là tính năng **chính thức** của Java (JEP 371), vẫn tồn tại trong Java hiện đại. Nó hữu ích cho framework, runtime ngôn ngữ, bộ sinh bytecode hoặc cơ chế triển khai động cần định nghĩa các lớp thực thi mà không công bố một **binary name** để các lớp khác có thể tra cứu như lớp thông thường.

Bài học giải thích:

1. `byte[]` mà API nhận vào phải chứa gì; có thể lấy nó từ đâu; cách phân biệt bytecode và mã nguồn.
2. `MethodHandles.Lookup` cung cấp ngữ cảnh quyền gì, và vì sao hidden class phải thuộc **cùng package** với lookup class.
3. Ý nghĩa tham số `initialize`, giá trị trả về, `Class.isHidden()`, cách dùng method handle để gọi phương thức của lớp mới.
4. Hai tùy chọn `NESTMATE` và `STRONG` cùng tác động lên quyền truy cập và vòng đời lớp.
5. Cách biên dịch và chạy ví dụ Java 15+ dùng hoàn toàn **thư viện chuẩn**, với stdout xác định.
6. Lỗi thường gặp: class bytes sai định dạng, phiên bản class file không hỗ trợ, package khác, lookup thiếu quyền, mất reference hoặc class initializer thất bại.

**Phạm vi hiện đại:** `defineHiddenClass` vẫn được hỗ trợ; không sử dụng các cơ chế nội bộ cũ như `Unsafe.defineAnonymousClass`. Java 15 là bản không LTS và không còn là runtime phù hợp cho triển khai mới; bạn có thể biên dịch ví dụ ở mức `--release 15` và chạy trên một JDK/JVM hiện đại còn được hỗ trợ, ví dụ Java 21.

## 2. Hidden class là gì?

Một **lớp thông thường** được định nghĩa với binary name có thể được các lớp khác tham chiếu trong constant pool và thường tra cứu bằng `Class.forName("package.Name")` hoặc `ClassLoader.loadClass(...)`.

Một **hidden class** được JVM tạo ra bằng `defineHiddenClass` thì khác:

- Nó vẫn là một **class/interface thật** trên JVM: có thể có phương thức, constructor, field, static initializer và `Class<?>` tương ứng; bytecode được xác minh, liên kết và có thể thực thi.
- `Class.isHidden()` trả `true`.
- Nó **không có binary name hợp lệ để các lớp khác tham chiếu theo tên** trong constant pool. `Class.getName()` có dạng tương tự `demo.HiddenTask/0x...`, có dấu `/` và suffix do JVM gán. Suffix là chi tiết triển khai, không được hard-code.
- Không thể lấy lại chính hidden class đó bằng `Class.forName`, `ClassLoader.loadClass` hoặc `Lookup.findClass` theo tên trả về từ `getName()`.
- Vẫn có thể giữ tham chiếu `Class<?>`, giữ `Lookup` do API trả về, tạo method handle, gọi phương thức hoặc tạo instance khi đúng quyền và loại constructor.
- Mặc định, hidden class **có thể được dỡ tải độc lập** với class loader đánh dấu là defining loader nếu không còn các tham chiếu cần thiết. Hành vi dỡ tải phụ thuộc khả năng reachability và GC, không có thời điểm bảo đảm.

**Hidden không có nghĩa là một ranh giới bảo mật.** Đừng dùng hidden class để chạy bytecode không tin cậy với kỳ vọng nó bị cách ly, hoặc coi nó là phương tiện giữ bí mật mã lệnh. Quyền trong `Lookup`, quyền module, class loader, protection domain và chính bytecode vẫn rất quan trọng.

### Khi nào dùng?

Các framework tạo code tại runtime, bộ thông dịch/JIT của ngôn ngữ hoặc công cụ triển khai động có thể cần định nghĩa nhiều lớp hỗ trợ vòng đời ngắn, không mong những lớp này trở thành API có tên để ứng dụng bên ngoài gọi. Đó là một tình huống phù hợp để cân nhắc hidden classes.

Nếu chỉ cần một lớp Java bình thường được các phần khác import, dùng `class`/`interface` thông thường. Nếu cần nạp plugin có tên được công bố và tra cứu bằng class loader, hidden class thường không phải mô hình phù hợp.

## 3. Chữ ký API: từng tham số có ý nghĩa gì?

```java
MethodHandles.Lookup hiddenLookup =
        callerLookup.defineHiddenClass(bytes, initialize, options);
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Trong đó:

| Thành phần | Kiểu dữ liệu | Vai trò |
| --- | --- | --- |
| `callerLookup` | `MethodHandles.Lookup` | Ngữ cảnh class/module/package và quyền của lời gọi định nghĩa |
| `bytes` | `byte[]` | **Toàn bộ cấu trúc class file** hợp lệ theo JVM Specification |
| `initialize` | `boolean` | Nếu `true`, JVM **khởi tạo lớp** (bao gồm static initialization) trong lời gọi; nếu `false`, không bắt buộc khởi tạo ngay |
| `options` | `ClassOption...` | Có thể bỏ trống; các tùy chọn chính là `NESTMATE` và `STRONG` |
| Giá trị trả về | `MethodHandles.Lookup` | Lookup mới có **lookup class chính là hidden class vừa định nghĩa** |

Khác với `Lookup.defineClass(byte[])` trả về một `Class<?>` thông thường, `defineHiddenClass` **trả về `Lookup` trên hidden class**. Để lấy đối tượng lớp, gọi `hiddenLookup.lookupClass()`; sau đó dùng `hiddenLookup.findStatic(...)`, `findConstructor(...)` hoặc các API truy cập khác nếu cần.

### 3.1. Yêu cầu về quyền và package

`defineHiddenClass` yêu cầu `Lookup` gọi phương thức phải có **full privilege access**; nếu không, có thể ném `IllegalAccessException`. Trong một class thông thường do bạn kiểm soát, `MethodHandles.lookup()` gọi trực tiếp từ class ấy thường là cách lấy Lookup phù hợp. `MethodHandles.publicLookup()` không có mức quyền cần thiết để định nghĩa hidden class.

Tên internal của lớp thể hiện trong `bytes` phải thuộc **cùng package** với **lookup class**. Với lookup bên trong `demo.HiddenClassDemo`, class file của `demo.HiddenTask` là ví dụ hợp lệ; bytes của `other.HiddenTask` bị từ chối (`IllegalArgumentException`). Đây là ràng buộc bảo vệ quyền truy cập: bạn không thể tùy tiện “bơm” lớp vào package bất kỳ bằng một Lookup không có quyền tại đó.

JVM định nghĩa hidden class có cùng **runtime package**, **module** và **protection domain** với lookup class; class loader của lookup class được đánh dấu là defining loader. Việc tạo hidden class **không** tương đương với gọi `ClassLoader.defineClass(...)` để thêm một lớp có tên vào bảng tra cứu thông thường của loader.

### 3.2. Mảng byte phải là class file thật

`bytes` phải chứa đúng **binary class file**, không phải văn bản Java UTF-8:

- Đúng: đọc file `.class` do `javac` tạo, lấy bytes của resource `.class` nằm trong JAR, hoặc tạo một class file hợp lệ bằng công cụ bytecode.
- Sai: `"class X {}".getBytes(UTF_8)`; đây là bytes của **mã nguồn**, không có cấu trúc JVM `ClassFile`.
- Một file `.class` hợp lệ bắt đầu bằng magic bytes **`CA FE BA BE`**, tiếp theo là phiên bản, constant pool, access flags, thông tin class, phương thức và attributes. Chỉ có magic bytes đúng **không bảo đảm** toàn bộ class file hợp lệ.
- Class file cần phiên bản major/minor mà JVM hiện tại hỗ trợ. Ví dụ biên dịch với `--release 15` cho **major version 59**.
- Bytecode và các tham chiếu mà nó sử dụng còn phải **verify/link** thành công. Dữ liệu tùy ý dù mang đuôi `.class` vẫn có thể ném lỗi.

Đừng convert binary class file qua `new String(bytes)` rồi `getBytes()`: chuỗi Unicode và encoding có thể làm thay đổi bytes. Dùng `Files.readAllBytes`, `InputStream.readAllBytes` hoặc một bytecode generator trả đúng `byte[]`.

## 4. Ví dụ hoàn chỉnh: lấy bytes của file `.class` và định nghĩa hidden class

Ví dụ sử dụng **hai file Java trong cùng package `demo`**. Ta biên dịch cả hai, nhưng chương trình chính **không sử dụng tên `HiddenTask` để tạo instance hoặc gọi phương thức**. Nó chỉ đọc file class dưới dạng **resource bytes**, truyền bytes vào `defineHiddenClass`, và dùng Lookup trả về để gọi một phương thức static.

### 4.1. Cấu trúc thư mục

```text
project/
└── src/
    └── demo/
        ├── HiddenTask.java
        └── HiddenClassDemo.java
```

Sau khi biên dịch với `-d out`, sẽ có `out/demo/HiddenTask.class` và `out/demo/HiddenClassDemo.class`.

### 4.2. File `src/demo/HiddenTask.java`

```java
package demo;

class HiddenTask {
    static {
        System.out.println("HiddenTask initialized");
    }

    public static String greet(String name) {
        return "Hello, " + name;
    }
}
```

Class này **chỉ là mẫu để compiler sinh bytes**. Khi gọi `defineHiddenClass` với bytes của nó, JVM định nghĩa một lớp **mới** có identity riêng và tên hidden. Class không phải `public`, và việc khai báo trong package `demo` đáp ứng quy tắc cùng package của lookup.

Static initializer in một dòng để quan sát tác dụng của `initialize = true`.

### 4.3. File `src/demo/HiddenClassDemo.java`

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDemo {
    public static void main(String[] args) throws Throwable {
        byte[] classBytes;

        // Resource name tuong doi voi package demo.
        try (InputStream in = HiddenClassDemo.class
                .getResourceAsStream("HiddenTask.class")) {
            if (in == null) {
                throw new IOException("Missing HiddenTask.class resource");
            }
            classBytes = in.readAllBytes();
        }

        MethodHandles.Lookup callerLookup = MethodHandles.lookup();

        // Define + initialize; khong can ClassOption cho vi du nay.
        MethodHandles.Lookup hiddenLookup =
                callerLookup.defineHiddenClass(classBytes, true);

        Class<?> hiddenType = hiddenLookup.lookupClass();

        System.out.println("isHidden=" + hiddenType.isHidden());
        System.out.println("samePackage="
                + hiddenType.getPackageName()
                    .equals(HiddenClassDemo.class.getPackageName()));
        System.out.println("nameHasSlash="
                + hiddenType.getName().contains("/"));

        MethodHandle greet = hiddenLookup.findStatic(
                hiddenType,
                "greet",
                MethodType.methodType(String.class, String.class));

        String result = (String) greet.invokeExact("Java");
        System.out.println("result=" + result);
    }
}
```

**Chú ý các dòng quan trọng:**

1. `getResourceAsStream("HiddenTask.class")` lấy bytes từ **classpath**, trong package `demo`; cách này cũng thuận tiện khi file được đóng gói trong JAR. Lệnh lấy resource **không phải lệnh nạp lớp theo tên**. `InputStream.readAllBytes()` có từ Java 9.
2. `MethodHandles.lookup()` được gọi bên trong `HiddenClassDemo`, tạo lookup hợp lệ trong package `demo` với quyền của class này.
3. `defineHiddenClass(classBytes, true)` định nghĩa **và khởi tạo** hidden class. Lệnh in trong static initializer vì thế chạy ngay, **trước** các dòng `isHidden`.
4. `hiddenLookup.lookupClass()` trả về `Class<?>` của hidden class. Kiểm tra `isHidden()` là cách chuẩn; `getName()` có dấu `/`, nhưng **không so sánh toàn bộ tên** vì suffix không ổn định.
5. `hiddenLookup.findStatic(...)` truy cập `greet(String)` của hidden class. `MethodType.methodType(String.class, String.class)` biểu diễn chữ ký **trả về `String`, nhận một `String`**.
6. `invokeExact` yêu cầu chữ ký tại vị trí gọi khớp chính xác kiểu của method handle; việc ép kiểu `(String)` ở kết quả là có chủ đích. `main` khai báo `throws Throwable` cho ví dụ vì `MethodHandle.invokeExact` có thể ném `Throwable`.

### 4.4. Biên dịch và chạy

Tại thư mục `project` (thư mục chứa `src`), dùng một JDK hiện đại có compiler hỗ trợ `--release 15`, ví dụ JDK 21:

```bash
javac --release 15 -encoding UTF-8 -d out src/demo/HiddenTask.java src/demo/HiddenClassDemo.java
java -cp out demo.HiddenClassDemo
```

**Stdout chính xác:**

```text
HiddenTask initialized
isHidden=true
samePackage=true
nameHasSlash=true
result=Hello, Java
```

Dòng đầu do `initialize = true`. Sau đó `Class.isHidden()` xác nhận lớp tạo động, hai dòng tiếp theo xác nhận package và quy tắc tên hidden, cuối cùng method handle gọi `greet` và trả chuỗi `Hello, Java`.

**Tại sao không in trực tiếp `hiddenType.getName()` trong expected output?** Suffix của tên hidden class có thể thay đổi theo JVM/lần chạy. Nếu in toàn bộ tên, bạn sẽ thấy dạng tương tự `demo.HiddenTask/0x...`, nhưng không có một chuỗi suffix cố định để đưa vào test.

**Kiểm tra version:** từ cùng thư mục, chạy:

```bash
javap -verbose -classpath out demo.HiddenTask
```

Trong output tìm `major version: 59`. Đó là version của class file do `--release 15` tạo, **không phải** Java version của JVM đang chạy. Các API sử dụng trong ví dụ đều có ở Java 15 hoặc sớm hơn. Nếu JDK compiler của bạn không hỗ trợ target 15, kiểm tra `javac --help` và chọn phiên bản hỗ trợ thay vì bỏ tùy chọn tương thích một cách vô thức.

## 5. Vì sao cần giữ `Lookup` trả về?

Hidden class **không có binary name có thể tra cứu thông thường**, nên không thể dựa vào `Class.forName(hiddenType.getName())` để tìm lại nó. Bạn cần giữ một reference thích hợp:

- `MethodHandles.Lookup` trả về để tiếp tục tra cứu constructor, method, field trong hidden class.
- `Class<?>` của hidden class để đọc metadata và các API cần class object.
- `MethodHandle` hoặc instance của hidden class nếu bạn muốn gọi behavior sau khi hàm tạo kết thúc.

Một class file tên `demo.HiddenTask` có thể đồng thời được class loader nạp như **lớp thông thường**, nhưng điều đó sẽ tạo `Class<?>` **khác** với hidden class lấy từ cùng class bytes. Đừng dùng tên nguồn `HiddenTask` để giả định bạn có thể truy cập trực tiếp hidden class đã định nghĩa.

Nếu framework tạo hàng nghìn hidden classes, cần quản lý reference để tránh giữ các class/method handle lâu hơn cần thiết. Khi không còn strongly reachable, hidden class không dùng `STRONG` có thể đủ điều kiện để GC dỡ tải; **không** có cam kết rằng JVM phải dỡ ngay hoặc theo thứ tự cụ thể.

## 6. `initialize` là true hay false?

### `initialize = true`

Lớp được định nghĩa, liên kết và **khởi tạo** ngay trong lời gọi `defineHiddenClass`. Nếu class có static initializer, nó thực thi trước khi lời gọi trả về. Nếu static initializer ném lỗi, lời gọi có thể thất bại do lỗi khởi tạo lớp. Ví dụ mục 4 dùng `true` để dễ quan sát dòng `HiddenTask initialized`.

### `initialize = false`

Lớp được định nghĩa và liên kết nhưng **không được khởi tạo ngay chỉ vì lời gọi `defineHiddenClass`**. Khi sau đó có hoạt động thuộc các tác nhân kích hoạt class initialization theo Java Language Specification, ví dụ lần gọi đầu tới một phương thức static thích hợp, JVM có thể khởi tạo lớp. Tạo một `MethodHandle` thường không có nghĩa static initializer đã chạy; gọi handle mới có thể kích hoạt.

Chọn `false` khi runtime cần điều khiển thời điểm initialization; chọn `true` khi muốn lớp sẵn sàng với các static state đã khởi tạo. Không dùng `false` như một phương thức bỏ qua hoàn toàn initialization: nếu cần chạy code của lớp, initialization vẫn tuân theo quy tắc JVM.

**Lưu ý:** tạo hidden class **khác** việc chỉ tạo một đối tượng Java hoặc gọi constructor. Việc khởi tạo lớp (*class initialization*) và việc khởi tạo instance (*instance construction*) là hai công đoạn khác nhau.

## 7. `ClassOption.NESTMATE` và `ClassOption.STRONG`

`ClassOption` là enum nằm trong `MethodHandles.Lookup`. Có thể truyền không tùy chọn nào, hoặc một/nhiều tùy chọn:

```java
MethodHandles.Lookup hidden = lookup.defineHiddenClass(
        classFileBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE
);
```

Đây là **mảnh mã minh họa** cần có `lookup` và `classFileBytes` đã được khởi tạo trong một phương thức.

| Tùy chọn | Mặc định nếu không truyền | Khi truyền tùy chọn |
| --- | --- | --- |
| `NESTMATE` | Hidden class có nest riêng gồm chính nó | Hidden class được thêm vào **cùng nest** với lookup class, có thể tiếp cận các private members theo quyền nestmate |
| `STRONG` | Hidden class có thể dỡ tải độc lập dù loader còn reachable | Hidden class có liên kết **mạnh** với defining class loader, như lớp thông thường; vòng đời dài hơn khi loader còn reachable |

### 7.1. Nestmate không có nghĩa bỏ qua mọi kiểm tra truy cập

Java hỗ trợ **nest-based access control**: các lớp trong cùng nest có thể truy cập private members của nhau. `NESTMATE` đặt hidden class vào nest của **lookup class**, hữu ích cho generated bytecode cần làm việc với implementation private của một host.

Điều kiện để gọi được thành công vẫn bao gồm **bytecode hợp lệ**, reference đúng, lookup có quyền và các bước verify/link. Đừng nghĩ truyền `NESTMATE` tự sửa được một class file sai package hay cho phép truy cập private ở **mọi** class tùy ý.

### 7.2. `STRONG` và vòng đời bộ nhớ

Không dùng `STRONG` theo thói quen. Hidden classes thường có ích vì có thể được dỡ tải khi framework không còn cần đến chúng. `STRONG` khiến chúng gắn chặt với lifecycle của loader, có thể kéo dài việc giữ metadata/classes và góp phần gây áp lực bộ nhớ nếu tạo nhiều lớp.

Ngược lại, nếu một hidden class phải tồn tại cùng một runtime component trong suốt thời gian loader tồn tại, `STRONG` có thể phù hợp. Hãy xác định nhu cầu vòng đời rõ ràng, đo việc sử dụng bộ nhớ trong môi trường thật và không giả định GC sẽ chạy vào một thời điểm cụ thể.

## 8. So sánh `defineHiddenClass` với cách định nghĩa lớp thông thường

| Thuộc tính | `Lookup.defineClass(bytes)` | `Lookup.defineHiddenClass(bytes, initialize, ...)` |
| --- | --- | --- |
| Kết quả | `Class<?>` | `Lookup` trên hidden class |
| Tên để tìm bằng class loader | Lớp thông thường có binary name | Hidden class **không thể tra cứu bằng tên** theo cách thông thường |
| Dữ liệu đầu vào | Mảng byte của class file | Mảng byte của class file |
| Package | Cùng package với lookup class | Cùng package với lookup class |
| Yêu cầu quyền | Lookup có quyền `PACKAGE` phù hợp | Lookup có **full privilege access** |
| Khởi tạo trong lời gọi | `defineClass` không tự chạy initializer | Điều khiển bằng `initialize` |
| Nestmate động | Dùng metadata của class file và quy tắc lớp thông thường | Có tùy chọn `NESTMATE` |
| Unloading | Theo ràng buộc loader của lớp thông thường | Mặc định có thể dỡ độc lập; `STRONG` thay đổi ràng buộc |
| Phù hợp | Lớp cần tên/được các phần khác liên kết | Lớp triển khai runtime cần identity riêng và không cần tên public |

`ClassLoader.defineClass` là cơ chế khác với `Lookup.defineClass` nhưng cùng hướng tới định nghĩa lớp bình thường bằng binary name. Với hidden classes, quyền tạo được kiểm soát thông qua `Lookup` và lớp được đánh dấu hidden ngay khi JVM định nghĩa.

## 9. Xử lý lỗi thực tế

| Lỗi / triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `ClassFormatError` | `byte[]` không tạo thành cấu trúc `ClassFile` hợp lệ | Đọc đúng file `.class` ở chế độ binary, không truyền text source, không dùng decode/re-encode |
| `UnsupportedClassVersionError` | Major/minor version của class file vượt mức JVM hỗ trợ | Dùng `javap -verbose` để xem major version, kiểm tra `java -version`, biên dịch đúng target/runtime |
| `IllegalArgumentException` | Class file khai báo internal name thuộc package khác lookup class, hoặc bytes không mô tả class/interface hợp lệ | Đối chiếu `package` trong source/class file với package của lookup class; kiểm tra đúng file |
| `IllegalAccessException` | Lookup không có **full privilege access** | Lấy lookup trong lớp hợp lệ, kiểm tra `hasFullPrivilegeAccess()`; tránh `publicLookup()` |
| `VerifyError` | Bytecode vi phạm quy tắc verifier | Kiểm tra bytecode generator, stack maps và chữ ký method |
| `LinkageError` và các lớp con | Không liên kết được lớp, supertype không hợp lệ, thiếu dependency hoặc xung đột liên kết | Kiểm tra classpath/module path, supertype và dependencies của class bytes |
| `ExceptionInInitializerError` | Class initializer ném lỗi khi khởi tạo | Kiểm tra static initializer, tham số `initialize` và exception cause |
| `NoSuchMethodException` trong `findStatic` | Tên, kiểu tham số hoặc kiểu trả về truyền vào `MethodType` không khớp | Dùng `javap`, kiểm tra chữ ký `findStatic` |
| `WrongMethodTypeException` tại `invokeExact` | Chữ ký Java tại vị trí gọi không khớp **chính xác** với method handle | Khai báo cast/argument types cho đúng; dùng `invoke` nếu muốn chuyển đổi có kiểm soát |
| `NullPointerException` hoặc lỗi resource | Không tìm thấy class file resource; code xử lý `in == null` chưa đúng | Kiểm tra resource có thật trong classpath/JAR và đường dẫn tương đối |
| `ClassNotFoundException` khi tra hidden name | Hidden class không thể được ClassLoader/`Class.forName` tìm lại theo tên | Giữ `Lookup`, `Class<?>` hoặc `MethodHandle` từ khi định nghĩa |

Đừng bắt `Exception` rồi trả `null` để “bỏ qua” lỗi bytecode. Lỗi verify/link cho biết class bytes hoặc dependency không phù hợp, cần sửa gốc. Những lỗi ở nhóm `Error` không phải tất cả đều nằm dưới `Exception`; cần hiểu loại lỗi và giới hạn phục hồi của runtime.

### Lưu ý đối với dữ liệu không tin cậy

Định nghĩa một class từ bytes nghĩa là bạn cho phép **mã lệnh** có thể được JVM thực thi trong ngữ cảnh quyền của lớp đó. **Không nhận class-file bytes tùy ý từ khách hàng hoặc plugin chưa được tin cậy rồi gọi `defineHiddenClass` trực tiếp** như thể đây là parser dữ liệu vô hại. Hidden class không cung cấp sandbox, không tự giới hạn I/O, mạng hay quyền thực thi.

Nếu ứng dụng cần plugin không tin cậy, phải có mô hình tin cậy và cách ly phù hợp ở cấp tiến trình/hệ thống; hidden class không thay thế kiểm soát đó.

## 10. Dùng byte[] ngoài thư mục build

Trong ví dụ, resource `HiddenTask.class` nằm trong `out/demo`. Nhưng chính `defineHiddenClass` **không quan tâm** bạn lấy bytes ở đâu, miễn toàn bộ mảng byte là class file hợp lệ cùng package:

- **Trên đĩa:** `Files.readAllBytes(Path.of("out", "demo", "HiddenTask.class"))` lấy bytes trực tiếp; cách này phụ thuộc thư mục chạy và đường dẫn build.
- **Trong JAR:** `HiddenClassDemo.class.getResourceAsStream("HiddenTask.class")` lấy bytes từ classpath, như ví dụ; thích hợp hơn khi đóng gói.
- **Từ bytecode generator:** thư viện/công cụ sinh ra byte array cấu trúc `ClassFile`; bạn phải bảo đảm tên nội bộ, version, constant pool, stack map và dependencies hợp lệ.
- **Từ compiler tại runtime:** có thể dùng Java Compiler API nếu môi trường có compiler (JDK); nhưng nó tạo class file bytes, không biến trực tiếp chuỗi source thành hidden class qua `defineHiddenClass`. Cần thiết kế trình lưu output vào bộ nhớ đúng chuẩn khi không muốn tạo file tạm.

Trong JDK hiện đại, **Class-File API** là một lựa chọn được chuẩn hóa để thao tác class files trên phiên bản Java có hỗ trợ nó. Tuy nhiên API đó **không thuộc Java 15**, nên nếu mục tiêu là biên dịch `--release 15`, dùng bytes do `javac` tạo như ví dụ hoặc thư viện bytecode tương thích và được bảo trì. Tránh công cụ nội bộ `sun.*` hoặc các phương thức đã bị loại bỏ.

**Không dùng `Class.forName` hay `ClassLoader.loadClass` như cách lấy lại hidden class mới tạo.** Nếu thực sự cần nạp cùng một lớp theo binary name thông thường, đó là nhu cầu khác và có thể phải dùng cơ chế định nghĩa class bình thường.

## 11. Checklist trước khi ứng dụng vào dự án

1. **Dữ liệu đầu vào:** `bytes` là toàn bộ JVM `ClassFile` hợp lệ, được đọc/sinh ở dạng binary; đã kiểm tra phiên bản class file chưa?
2. **Package:** internal name của class bytes cùng package với lookup class chưa?
3. **Quyền:** Lookup có **full privilege access** và đúng module/trust context chưa?
4. **Khởi tạo:** `initialize` đúng nhu cầu? Static initializer có side effects hoặc lỗi có thể xảy ra không?
5. **Truy cập:** đã giữ `hiddenLookup` hoặc reference thích hợp và dùng `findStatic`/`findConstructor` đúng chữ ký chưa?
6. **Vòng đời:** có thực sự cần `STRONG`, hay muốn hidden class có thể được GC dỡ tải độc lập?
7. **Nestmate:** chỉ bật `NESTMATE` nếu generated bytecode cần quyền của nest và thiết kế thực sự cho phép?
8. **An toàn:** class-file bytes có đến từ nguồn đáng tin cậy? Có giám sát số lớp sinh ra, lỗi verify và bộ nhớ JVM không?
9. **Kiểm chứng:** đã biên dịch bằng JDK/compiler phù hợp, chạy trên JVM được hỗ trợ và đối chiếu `Class.isHidden()`, output, method signature, trạng thái initialization chưa?
10. **Tương thích:** tránh phụ thuộc hidden name suffix, `Class.forName`, loader discovery hoặc giả định JVM sẽ unload lớp ngay lập tức.

## 12. Tài liệu chính thức

- **Java SE 15 — `MethodHandles.Lookup.defineHiddenClass`**: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Java SE 25 — `MethodHandles.Lookup`**, để đối chiếu sự tồn tại của API trong JDK hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Java SE 15 — `MethodHandles.Lookup.ClassOption`** (`NESTMATE` và `STRONG`): https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- **Java SE 25 — `Class.isHidden()`**, `Class.getName()` và metadata: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html
- **OpenJDK JEP 371 — Hidden Classes**: https://openjdk.org/jeps/371
- **JVM Specification — `ClassFile` format, magic, version và attributes**: https://docs.oracle.com/javase/specs/jvms/se15/html/jvms-4.html

Những kiến thức ở đây vẫn áp dụng trong Java hiện đại. Với ứng dụng mới, chọn JDK/JVM còn được nhà cung cấp hỗ trợ, giữ class bytes và Lookup trong phạm vi tin cậy, đồng thời kiểm thử đúng môi trường runtime dự kiến.
