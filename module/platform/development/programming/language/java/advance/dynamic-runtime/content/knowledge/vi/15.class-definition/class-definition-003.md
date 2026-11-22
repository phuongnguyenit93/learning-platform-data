# 15.3 `defineHiddenClass` và khác biệt với lớp có tên có thể tìm bằng `Class.forName`

Java có hai cơ chế dễ bị nhầm khi tạo class lúc runtime:

- **Lớp có tên (ordinary/named class)**: có **binary name** để class loader hoặc JVM có thể tìm theo tên như `java.lang.String`, `com.example.User` hoặc `com.example.Outer$Inner`. Khi lớp có thể truy cập được qua class loader phù hợp, `Class.forName("...")` có thể trả về `Class<?>` của nó. `MethodHandles.Lookup.defineClass(byte[])` là một cách định nghĩa loại lớp này.
- **Lớp ẩn (hidden class)**: được tạo bằng **`MethodHandles.Lookup.defineHiddenClass(byte[], boolean, ClassOption...)`**. Class vẫn tồn tại thật trong JVM và có object `Class<?>`, có bytecode, fields, methods, supertype, interfaces và có thể được gọi qua reflection/`MethodHandle`. Tuy nhiên tên runtime của nó **không phải binary name**; `Class.forName` và `ClassLoader.loadClass` **không thể tìm ra hidden class** bằng tên đó.

Đây không đơn giản là vấn đề `public` hay `private`. Một hidden class có thể có method `public` nhưng vẫn **không discoverable theo tên**, còn một named class có thể khó truy cập vì module/class loader nhưng vẫn có binary name. Mục đích của hidden class là cấp cho runtime framework một kiểu thực thi có thể được tạo theo nhu cầu, không cần thêm tên có thể discover vào không gian class thông thường.

> **Môi trường:** JDK 17+. API `defineHiddenClass` có từ Java 15 (JEP 371). Bốn ví dụ độc lập bên dưới biên dịch bằng `javac --release 17` và có stdout đã kiểm thử. `Class.getName()` của hidden class chứa suffix phụ thuộc runtime nên ví dụ chỉ kiểm tra đặc điểm ổn định (có dấu `/`), **không hard-code tên sinh ra**.

## 1. Cần nắm những gì?

Sau bài này, bạn có thể:

1. Phân biệt **định nghĩa lớp** (definition), **tìm lớp bằng tên** (discovery), **khởi tạo tĩnh** (initialization), và **hủy tải lớp** (unloading).
2. Giải thích tại sao `defineHiddenClass(...)` trả về một `Lookup` thay vì một binary name, và cách lấy `Class<?>` qua `lookup.lookupClass()`.
3. Hiểu vì sao `Class.forName(hidden.getName())` ném `ClassNotFoundException`, kể cả khi `hidden` đã tồn tại và có cùng class loader với lớp chủ.
4. So sánh `Lookup.defineClass(bytes)` với `Lookup.defineHiddenClass(bytes, initialize, options)` trên **chính cùng một chuỗi byte class file**.
5. Sử dụng `MethodHandle`/reflection để truy cập hidden class qua reference thật thay vì dựa vào chuỗi tên.
6. Hiểu ý nghĩa của tham số `initialize`: `false` có thể hoãn `<clinit>`, `true` khởi tạo ngay theo JVM.
7. Hiểu `NESTMATE` trong truy cập private và `STRONG` trong vòng đời của hidden class.
8. Nhận biết trường hợp có nhiều hidden classes được định nghĩa từ cùng bytecode, nhưng **khác identity và trạng thái static**, dù class loader chung.
9. Tránh các lỗi liên quan đến quyền `Lookup`, sai package, duplicate named definition, class loader, phản xạ và dùng tên hidden class làm tên binary chuẩn.

## 2. Mô hình tư duy: tạo một `Class<?>` không đồng nghĩa đăng ký một tên có thể tra cứu

Một JVM có thể chứa nhiều class objects có liên hệ khác nhau với cùng source/bytecode. Với named class, class loader quản lý danh tính theo **cặp binary name và defining loader** (cùng các quy tắc JVM liên quan). Với hidden class, JVM cho phép một class riêng **không có binary name bình thường** và không bị tra cứu bằng các API yêu cầu tên đó.

```text
Bytecode hợp lệ của một lớp "Host$Template"
                 |
          +------+------+
          |             |
          v             v
Lookup.defineClass  Lookup.defineHiddenClass
          |             |
          v             v
Named Class A      Hidden Class H
          |             |
name: "Host$Template" name: "Host$Template/0x..." (dạng minh họa)
binary name: CÓ    binary name: KHÔNG
isHidden(): false  isHidden(): true
          |             |
          v             v
Class.forName       giữ reference Class<?> H
("Host$Template")   hoặc Lookup/MethodHandle để sử dụng
  -> có thể A       Class.forName(H.getName()) -> thất bại
```

Hình trên diễn đạt một ví dụ trong cùng loader và package, với named class có thể truy cập. Suffix `/0x...` thường gặp khi in tên hidden class trên HotSpot, nhưng không dựa vào **nội dung hoặc độ dài suffix** để viết chương trình.

### 2.1. Lớp ẩn vẫn là class đầy đủ

Một hidden class có thể:

- Có `Class<?>` đại diện; gọi `isHidden()` để nhận diện.
- Có method, constructor, field, class initializer và superclass/interfaces theo các ràng buộc class file.
- Được JVM verify, link và tùy lựa chọn được initialize.
- Được truyền vào API chấp nhận `Class<?>`, ví dụ để dùng `MethodHandles.Lookup`, `Class.getDeclaredMethods()` hoặc reflection với quyền phù hợp.
- Tham gia polymorphism qua interfaces/supertypes có tên thông thường; một object có runtime class ẩn vẫn có thể được dùng dưới kiểu interface có tên.
- Được định nghĩa nhiều lần từ cùng bytecode để tạo những class identities độc lập.

Nhưng hidden class không thể **được đặt tên bằng binary name trong constant pool của một class khác** như một ordinary class. Vì vậy, code Java nguồn không thể viết một import hoặc field type bình thường chỉ tới tên runtime `Host$Template/0x...`; Java lexer và JVM symbolic linkage không xử lý đó là một binary name hợp lệ.

### 2.2. “Không tìm được theo tên” khác “không thể sử dụng”

Đừng hiểu hidden class là *vô hình tuyệt đối*. Nó có thể lộ qua `obj.getClass()`, `Lookup.lookupClass()`, stack traces, diagnostics, reflection hoặc instrumentation mà JVM cho phép. Nó chỉ cố ý **không nằm trong cơ chế tra cứu nominal bằng class binary name**.

Ví dụ một runtime có thể trả object triển khai `Runnable` có hidden runtime class. Client không biết/không tìm ra tên class runtime, nhưng vẫn có thể gọi `((Runnable) object).run()` vì `Runnable` là interface có tên hợp lệ. Một framework cũng có thể giữ `MethodHandle` tới method trên hidden class mà không dùng `Class.forName`.

## 3. Bảng so sánh `defineClass`, `defineHiddenClass` và `Class.forName`

| Câu hỏi | `Lookup.defineClass(bytes)` | `Lookup.defineHiddenClass(bytes, init, opts)` | `Class.forName(name)` |
| --- | --- | --- | --- |
| Đây là thao tác nào? | **Định nghĩa** một named class từ bytecode | **Định nghĩa** một hidden class từ bytecode | **Tìm/nạp và có thể khởi tạo** named class qua tên |
| Có cần `byte[]` class file? | Có | Có | Không; nhận chuỗi tên và dùng class loader |
| Kết quả trả về | `Class<?>` | `MethodHandles.Lookup` mới trên hidden class | `Class<?>` tìm được |
| Binary name có thể dùng để tra cứu? | Có, qua loader phù hợp | **Không** | Bắt buộc đầu vào là tên mà loader có thể resolve |
| `Class.isHidden()` | `false` | `true` | `false` với lớp bình thường tìm được |
| Đăng ký tên trong không gian named classes? | Có, chịu quy tắc uniqueness theo loader | Không theo cơ chế named class | Không tự định nghĩa một hidden class |
| Cùng bytecode định nghĩa lần nữa? | Cùng loader + cùng binary name có thể `LinkageError` | Có thể tạo nhiều hidden class identities | Không phải phương thức tự định nghĩa một bản sao |
| Khởi tạo tĩnh | `defineClass` không tự yêu cầu initialize ngay | Boolean `initialize` quyết định có initialize ngay không | `forName(name)` mặc định initialize; overload có `boolean` |
| Khả năng tìm bằng `Class.forName` | Có, nếu chọn đúng loader và các điều kiện tra cứu | **Không** | Chính là API tra cứu |
| Có `ClassOption.NESTMATE` / `STRONG`? | Không | Có | Không |
| Chế độ unloading | Gắn với defining loader theo quy tắc named class | Mặc định cho phép weak relationship; `STRONG` đổi sang strong loader relationship | Không quyết định unloading policy của lớp được tìm |

**Điểm dễ nhầm:** `Class.forName` không định nghĩa lại một hidden class chỉ vì tên trong `getName()` có hình thức gần giống Java class name. Khi caller đưa `hidden.getName()` (có `/`), JVM không chuyển nó thành reference tới hidden class đang tồn tại.

### 3.1. `Class.forName` có điều kiện với named classes

Nói "lớp có tên tìm được bằng `Class.forName`" không phải cam kết rằng **mọi named class đều tìm được từ mọi class loader**. Những nguyên nhân có thể làm tìm thất bại gồm:

- Caller sử dụng loader khác, không nhìn thấy class tương ứng.
- Class thực tế chưa có trên class path/module path mà loader sử dụng.
- Tên binary sai (ví dụ nested class dùng `$` chứ không phải dấu `.` giữa outer/inner trong binary name).
- Module/readability hay class loading/linkage thất bại theo ngữ cảnh.

Với named class, chỉ cần **chọn đúng loader** để có cơ hội resolve:

```java
// Fragment minh họa với named class có binary name và loader phù hợp.
Class<?> type = Class.forName(
        "com.example.Plugin", false, appropriateLoader);
```

Đoạn trên không chạy độc lập vì `appropriateLoader` chưa được định nghĩa. Tham số `false` trong overload 3 tham số chỉ điều khiển khởi tạo (initialization), không thay đổi lớp có tên thành hidden class.

### 3.2. Lớp ẩn không tìm được kể cả dùng đúng loader

Với hidden class:

```java
// Fragment: hidden là Class<?> của hidden class đã được tạo.
Class.forName(hidden.getName());                   // ClassNotFoundException
hidden.getClassLoader().loadClass(hidden.getName());// ClassNotFoundException
```

Hai lời gọi trên có thể ném checked exception và sẽ được test trong chương trình hoàn chỉnh ở mục 6. `getClassLoader()` cho thấy hidden class **được đánh dấu có một defining loader**, nhưng loader **không dùng `loadClass` để trả ra hidden class theo tên**.

## 4. API trung tâm: `MethodHandles.Lookup.defineHiddenClass`

Khai báo khái niệm từ Java 17+:

```java
public MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
```

Đây là **chữ ký API**, không phải đoạn cần tự viết trong chương trình.

Cách dùng phổ biến:

```java
// Fragment: bytes là byte[] chứa class file hợp lệ.
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Sau lời gọi, `hiddenLookup` là một Lookup có **lookup class là hidden class mới**, thuận tiện cho việc tìm method/constructor/field bằng quyền tương ứng. `hiddenClass` là `Class<?>` định danh chính xác loại ẩn đã tạo.

Tham số:

1. **`bytes`:** mảng byte class file hợp lệ (ví dụ bytecode do compiler hoặc ASM sinh). Không được truyền nội dung file `.java`, chuỗi tên, hay bytes của thư viện JAR không giải nén.
2. **`initialize`:** `true` yêu cầu JVM initialize hidden class sau khi link; `false` hoãn initialize đến khi Java/JVM thực sự kích hoạt theo quy tắc khởi tạo.
3. **`options`:** danh sách `ClassOption`, trong Java 17 gồm `NESTMATE` và `STRONG`; có thể không truyền tùy chọn nào.

### 4.1. `Lookup` cần có quyền phù hợp

`defineHiddenClass` là một API có kiểm tra quyền, **không phải class-loader escape hatch**:

- Lookup cần **full privilege access** theo hợp đồng `java.lang.invoke`; một lookup yếu (chẳng hạn `MethodHandles.publicLookup()`) không đủ.
- Class bytes phải định nghĩa class có package phù hợp với **lookup class**.
- Việc định nghĩa class cùng package/module và quyền truy cập không tự bỏ qua ràng buộc Java module security.
- Một class file không hợp lệ có thể gây `ClassFormatError`, `VerifyError` hoặc lỗi khác ở bước tạo/link.
- `NESTMATE` không phải lệnh cấp quyền tùy ý cho một class ở package/module khác; nó gắn hidden class vào nest của **lookup class** theo quy tắc API.

API này hữu ích khi framework đã có một `Lookup` được cấp quyền hợp lệ, cần định nghĩa lớp runtime có thể thực thi nhưng không muốn công bố một nominal binary name.

### 4.2. Package, module và defining loader

Trong định nghĩa hidden class, JVM dùng package của class được mô tả bởi bytes và đặt hidden class trong ngữ cảnh runtime của lookup class (loader/module phù hợp). Khi bytes chỉ tới một package khác package lookup class, `defineHiddenClass` sẽ từ chối, thường bằng `IllegalArgumentException`. Không nên đổi package của bytecode bằng cách đơn thuần đổi chuỗi trong tên file resource; package được chứa trong class file.

Cụ thể, ví dụ bên dưới đặt class host và nested template trong cùng **unnamed package** để không cần cấu hình module path. Với dự án thực tế có package `com.example.runtime`, các class template cần khai báo đúng package đó hoặc bytecode generator phải tạo internal name phù hợp.

### 4.3. Hidden class có thể khởi tạo riêng và nhiều lần

Mỗi lần `defineHiddenClass` thành công tạo một class mới. Nếu class file chứa `static int count`, thì hai hidden class định nghĩa từ cùng bytes có **hai static fields độc lập**; khởi tạo một class không khiến static initializer của class kia bị coi là đã chạy.

Điều này khác với named class trong cùng loader: một binary name không thể định nghĩa hai lần mà vẫn là hai named classes độc lập trong cùng namespace của loader. Nếu muốn hai named class có cùng binary name, chúng thường phải do **hai defining class loaders khác nhau** định nghĩa.

## 5. Vì sao `hidden.getName()` không dùng được với `Class.forName`?

Để trả lời chính xác, cần phân biệt **name được trả bởi Reflection** và **binary name có thể ghi trong class file constant pool**.

### 5.1. Tên hidden class có phần suffix không thuộc binary name

Ở hidden class, `Class.getName()` chứa dấu `/` phân tách một tên dạng classfile `N` và suffix do JVM chọn. Tên quan sát được trên HotSpot thường có dạng:

```text
HiddenClassNamesDemo$Template/0x0000000800...
```

Dấu `...` ở ví dụ này biểu diễn phần rút gọn; **không có giá trị suffix cố định** để ứng dụng dựa vào. Đối với named nested class tương ứng, `getName()` chỉ là:

```text
HiddenClassNamesDemo$Template
```

Chỉ dòng thứ hai mới là **binary name** phù hợp cho `Class.forName` trong trường hợp lớp ấy được định nghĩa trong loader có thể thấy nó.

`Class.getCanonicalName()` của hidden class là `null`. `Class.descriptorString()` có thể chứa dấu `.` ở phần suffix sau tên gốc, khiến nó **không phải type descriptor chuẩn có thể dùng làm symbolic field type** trong JVMS. Vì vậy đừng coi `hidden.getName()` hoặc `hidden.descriptorString()` là định dạng có thể parse lại bằng các API chỉ nhận nominal names như với ordinary classes.

### 5.2. `Class.forName` sử dụng binary name, không nhận object identity

`Class.forName("X")` về cơ bản là yêu cầu JVM/class loader tìm lớp được định danh bằng một **chuỗi** trong môi trường truy cập. Nó không có cách chuyển `"X/0x..."` thành object `Class<?>` đang tồn tại của hidden class. Ngay cả khi:

- Hidden class và host có **cùng class loader**;
- Tên gốc `X` giống tên một named class khác;
- Method trên hidden class là `public`;
- Ứng dụng có đầy đủ quyền reflection;

… thì khả năng **truy xuất từ string name** vẫn không được bổ sung.

Ngược lại, `Class<?> hidden` và `MethodHandles.Lookup hiddenLookup` là **references thật**; giữ lại các reference này cho phép thao tác trực tiếp với hidden class. Điều này là nguyên tắc thiết kế quan trọng của API.

### 5.3. Nếu tên gốc cũng tồn tại thì sao?

Giả sử class bytes có tên gốc `HiddenClassNamesDemo$Template`. Có thể bạn vừa tạo **hidden class** từ bytes ấy, đồng thời cũng định nghĩa **ordinary class** có cùng original binary name.

```text
Class.forName("HiddenClassNamesDemo$Template")
    -> tìm ORDINARY class (nếu có và loader phù hợp)

Class.forName(hidden.getName())
    -> không thể tìm hidden class

hidden == named
    -> false
```

Đừng suy luận “`Class.forName` trả về một class có code giống” là “`Class.forName` đã tìm được chính hidden class”. Class identity quyết định type checking, static state và method dispatch, không chỉ code byte-for-byte.

## 6. Thực hành 1 — Cùng bytes: named class tìm được, hidden class không

Tạo **`HiddenClassNamesDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenClassNamesDemo {
    static class Template {
        public static String greet(String name) {
            return "Hello, " + name;
        }
    }

    private static byte[] templateBytes() throws IOException {
        try (InputStream in = HiddenClassNamesDemo.class.getResourceAsStream(
                "HiddenClassNamesDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Template bytecode resource not found");
            }
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = templateBytes();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup hiddenLookup = host.defineHiddenClass(bytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();
        Class<?> named = host.defineClass(bytes);
        MethodType type = MethodType.methodType(String.class, String.class);
        MethodHandle hiddenMethod = hiddenLookup.findStatic(hidden, "greet", type);
        MethodHandle namedMethod = host.findStatic(named, "greet", type);

        System.out.println("hidden isHidden: " + hidden.isHidden());
        System.out.println("named isHidden: " + named.isHidden());
        System.out.println("different classes: " + (hidden != named));
        System.out.println("hidden has slash: " + hidden.getName().contains("/"));
        System.out.println("hidden canonical name null: "
                + (hidden.getCanonicalName() == null));
        System.out.println("hidden descriptor has dot suffix: "
                + hidden.descriptorString().contains("."));
        System.out.println("named forName works: "
                + (Class.forName(named.getName()) == named));
        try {
            Class.forName(hidden.getName());
            System.out.println("unexpected Class.forName result");
        } catch (ClassNotFoundException expected) {
            System.out.println("hidden forName: ClassNotFoundException");
        }
        try {
            hidden.getClassLoader().loadClass(hidden.getName());
            System.out.println("unexpected loadClass result");
        } catch (ClassNotFoundException expected) {
            System.out.println("hidden loadClass: ClassNotFoundException");
        }
        System.out.println("hidden invoke: "
                + (String) hiddenMethod.invokeExact("Ada"));
        System.out.println("named invoke: "
                + (String) namedMethod.invokeExact("Ada"));
    }
}
```

Biên dịch và chạy trong cùng thư mục, để compiler tạo cả class file cho nested template:

```bash
javac --release 17 HiddenClassNamesDemo.java
java HiddenClassNamesDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
hidden isHidden: true
named isHidden: false
different classes: true
hidden has slash: true
hidden canonical name null: true
hidden descriptor has dot suffix: true
named forName works: true
hidden forName: ClassNotFoundException
hidden loadClass: ClassNotFoundException
hidden invoke: Hello, Ada
named invoke: Hello, Ada
```

### 6.1. Vì sao chương trình có thể định nghĩa cả hai?

File `HiddenClassNamesDemo$Template.class` đã được `javac` tạo dưới dạng resource. Chương trình dùng `getResourceAsStream(...)` để lấy **bytes** của nested class mà không cần gọi `Template.class` trong code trước khi `host.defineClass(bytes)`.

- `host.defineHiddenClass(bytes, true)` tạo hidden class riêng với tên runtime được VM thêm suffix.
- `host.defineClass(bytes)` định nghĩa một **named class** có binary name gốc vào cùng lookup loader (trước đó named class này chưa được JVM định nghĩa trong lần chạy ví dụ).
- Khi `Class.forName(named.getName())` chạy, named class đã được định nghĩa nên tìm lại được.
- Khi `Class.forName(hidden.getName())` chạy, API không có đường name lookup để tìm hidden class.
- Vì `hidden` và `named` là **hai class objects khác nhau**, `hidden != named` dù body của `greet` giống nhau.

### 6.2. Gọi được hidden method mà không tìm bằng tên

`hiddenLookup.findStatic(hidden, "greet", type)` tạo `MethodHandle` dùng trực tiếp `Class<?>` của hidden class. Đây là lý do dòng `hidden invoke: Hello, Ada` vẫn xuất hiện dù `Class.forName` thất bại.

`findStatic` kiểm tra quyền/kiểu method theo `Lookup` phù hợp; chính việc hidden class có thể được sử dụng qua handle **không** đồng nghĩa mọi class khác có quyền gọi method private của nó. Hãy tách **khả năng reference** khỏi **quyền truy cập**.

### 6.3. Vì sao tránh in nguyên tên hidden class?

Suffix được JVM chọn động, thường liên quan đến identity và hoàn cảnh runtime; nếu in nguyên `hidden.getName()`, stdout không đáng tin để ghi cố định giữa các lần chạy. Demo chỉ in các **đặc điểm chuẩn**: `isHidden`, dấu `/`, `getCanonicalName()==null` và `descriptorString` chứa dạng suffix khác chuẩn binary descriptor.

Ngoài ra, `javac --release 17` mới chỉ yêu cầu khả năng build API Java 17; JVM chạy ứng dụng phải hỗ trợ class file Java 17 và API đã dùng.

## 7. `initialize=false` khác `Class.forName(name,false,loader)` thế nào?

Đây là điểm quan trọng khi làm class loading động.

### 7.1. `defineHiddenClass(bytes,false)` đã tạo class; chỉ hoãn khởi tạo

Trạng thái khái niệm:

```text
bytes
  |
  | defineHiddenClass(bytes, false)
  v
hidden Class<?> H đã được derive + link
  |
  | chưa bắt buộc chạy static initializer <clinit>
  |
  | gọi Lookup.ensureInitialized(H)
  | hoặc một hoạt động tạo kích hoạt initialization
  v
static initializer <clinit> của H chạy
```

Boolean `initialize` không có nghĩa "chưa tạo class". Hidden class và `Class<?>` đã tồn tại; JVM chỉ hoãn **initialization** của class đó. `Lookup.ensureInitialized(...)` cho phép buộc chạy class initialization với quyền phù hợp.

### 7.2. Với `Class.forName` của named class

- `Class.forName("com.example.Foo")` có ngữ nghĩa yêu cầu **initialize** named class nếu cần.
- `Class.forName("com.example.Foo", false, loader)` cố tìm/nạp named class mà **không yêu cầu initialize ngay**.
- Cả hai cách trên vẫn dựa vào **tên của named class**, không phải một hidden class.
- `ClassLoader.loadClass("...")` thường thực hiện loading mà không initialize ngay; không chuyển thành lookup cho hidden class.

Bốn khái niệm **definition, loading, linking, initialization** có thể có thời điểm khác nhau. Hãy gọi đúng tên giai đoạn khi đọc log class initializer.

### 7.3. Thực hành 2 — Hai hidden classes và một named class initialize độc lập

Tạo **`HiddenInitializationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public final class HiddenInitializationDemo {
    static class Payload {
        static {
            System.out.println("Payload <clinit>");
        }

        public static int value() {
            return 42;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenInitializationDemo.class.getResourceAsStream(
                "HiddenInitializationDemo$Payload.class")) {
            if (in == null) throw new IOException("missing template class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = code();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup lazy = host.defineHiddenClass(bytes, false);
        System.out.println("after define(false)");
        lazy.ensureInitialized(lazy.lookupClass());
        System.out.println("after ensureInitialized");

        MethodHandles.Lookup eager = host.defineHiddenClass(bytes, true);
        System.out.println("after define(true)");
        System.out.println("distinct hidden classes: "
                + (lazy.lookupClass() != eager.lookupClass()));

        Class<?> named = Class.forName(
                "HiddenInitializationDemo$Payload",
                false, HiddenInitializationDemo.class.getClassLoader());
        System.out.println("named is hidden: " + named.isHidden());
        Class.forName(named.getName());
        System.out.println("after named Class.forName");
    }
}
```

```bash
javac --release 17 HiddenInitializationDemo.java
java HiddenInitializationDemo
```

**Stdout chính xác:**

```text
after define(false)
Payload <clinit>
after ensureInitialized
Payload <clinit>
after define(true)
distinct hidden classes: true
named is hidden: false
Payload <clinit>
after named Class.forName
```

**Phân tích:**

1. `defineHiddenClass(bytes,false)` tạo hidden class thứ nhất nhưng chưa in `Payload <clinit>`. Dòng `after define(false)` được in trước khi class initializer của class ấy chạy.
2. `lazy.ensureInitialized(lazy.lookupClass())` khiến initializer chạy một lần cho hidden class thứ nhất.
3. `defineHiddenClass(bytes,true)` tạo **hidden class thứ hai** và initialize ngay. Một dòng `Payload <clinit>` nữa xuất hiện trước `after define(true)`.
4. Hai hidden classes có identity khác nhau dù bytes giống; do đó `<clinit>` của mỗi class chạy riêng.
5. `Class.forName(name,false,loader)` tìm named `Payload` nhưng không initialize nó. `Class.forName(named.getName())` sau đó initialize named class và in dòng `Payload <clinit>` **thứ ba**.
6. Cả ba class ở ví dụ có code initializer cùng một nội dung, nhưng không phải cùng một class. Vì thế in ba lần là kết quả hợp lệ, không phải một initializer bị chạy lặp trái quy tắc.

Lưu ý: nếu class named đã initialize trước đó trong cùng JVM, `Class.forName` không chạy initializer lại. Ví dụ giữ trình tự tự chủ để stdout xác định.

## 8. `ClassOption.NESTMATE`: hidden class có thể truy cập private của host

Một lớp nested bình thường có thể là **nestmate** của class chứa nó. Từ Java 11, nestmates là cơ chế JVM cho phép các class trong cùng nest có quyền truy cập private của nhau mà không cần synthetic accessor trong nhiều trường hợp.

Khi định nghĩa hidden class từ bytes:

- **Mặc định (không `NESTMATE`):** hidden class là nest của chính nó, **không được tự động thừa hưởng nest** của classfile template hay của host Lookup. `NestHost`/`NestMembers` trong bytes không tự cấp cho hidden class quyền giống class gốc.
- **Có `NESTMATE`:** hidden class được thêm làm nestmate của **lookup class**. Nếu lookup class có nest host là một outer class, hidden class trở thành thành viên của nest đó.
- Nestmate cho phép truy cập private **theo quy tắc nest membership**, không phải khả năng truy cập mọi member riêng tư của mọi class trong JVM.
- Hidden class vẫn **không có binary name**; thêm `NESTMATE` không làm `Class.forName` có thể tìm nó.

### 8.1. Tại sao đây là đặc tính quan trọng?

Framework sinh code có thể cần trực tiếp gọi một private helper của host một cách an toàn, theo quyền của lookup class. Nếu chỉ tạo hidden class không có nestmate, bytecode truy cập private sẽ bị kiểm tra và có thể ném `IllegalAccessError` lúc resolve thao tác. Có `NESTMATE` và quyền hợp lệ, truy cập có thể thành công.

### 8.2. Thực hành 3 — Cùng bytes, có/không `NESTMATE`

Tạo tệp **`HiddenNestmateDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenNestmateDemo {
    private static String secret = "sealed";
    static class Reader {
        public static String read() {
            return secret;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenNestmateDemo.class.getResourceAsStream(
                "HiddenNestmateDemo$Reader.class")) {
            if (in == null) throw new IOException("missing class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = code();
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup nested = host.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> allowed = nested.lookupClass();
        MethodHandle reader = nested.findStatic(
                allowed, "read", MethodType.methodType(String.class));

        System.out.println("nestmate hidden: " + allowed.isHidden());
        System.out.println("nest host matches outer: "
                + (allowed.getNestHost() == HiddenNestmateDemo.class));
        System.out.println("nestmate reads: " + (String) reader.invokeExact());

        MethodHandles.Lookup isolated = host.defineHiddenClass(bytes, false);
        Class<?> denied = isolated.lookupClass();
        System.out.println("default nest host is self: "
                + (denied.getNestHost() == denied));
        try {
            MethodHandle deniedMethod = isolated.findStatic(
                    denied, "read", MethodType.methodType(String.class));
            String result = (String) deniedMethod.invokeExact();
            System.out.println("unexpected: " + result);
        } catch (IllegalAccessError expected) {
            System.out.println("without NESTMATE: IllegalAccessError");
        }
    }
}
```

```bash
javac --release 17 HiddenNestmateDemo.java
java HiddenNestmateDemo
```

**Stdout chính xác:**

```text
nestmate hidden: true
nest host matches outer: true
nestmate reads: sealed
default nest host is self: true
without NESTMATE: IllegalAccessError
```

Vì sao?

1. `Reader.read()` được compiler biên dịch để đọc field private `HiddenNestmateDemo.secret`, thông thường nhờ quan hệ nestmate giữa nested class và outer class.
2. Khi bytes `Reader.class` được định nghĩa **ẩn với `NESTMATE`**, hidden class mới trở thành nestmate của lookup class `HiddenNestmateDemo`, nên đọc được private field.
3. `allowed.getNestHost()` trả đúng `HiddenNestmateDemo.class`.
4. Khi dùng cùng bytes để tạo hidden class **không có `NESTMATE`**, class ấy tự tạo nest riêng. Dù bytes gốc thuộc nested `Reader`, hidden copy **không tự kế thừa quyền private** từ nó.
5. Khi invoke method có thao tác truy cập field private của outer class, JVM từ chối bằng `IllegalAccessError`. Điều này cho thấy quyền nest phụ thuộc vào **cách hidden class được định nghĩa**, không phụ thuộc duy nhất vào tên hoặc code template.
6. `defineHiddenClass(bytes,false)` trong nhánh không-nestmate không initialize ngay. Lỗi xuất hiện khi method thử truy cập member bị cấm; không nên nhầm với `ClassNotFoundException` do `Class.forName`.

**Lưu ý:** `NESTMATE` không thay đổi chính sách module, không cho phép bỏ qua quyền lookup, và không làm hidden class có thể được tra cứu nominal.

## 9. `ClassOption.STRONG`: vòng đời lớp, không phải khả năng tìm theo tên

Mặc định, hidden class có liên hệ với defining loader theo kiểu **weak**: JVM có thể unload hidden class dù loader của nó vẫn còn reachable, miễn là không còn những reference cần giữ class tồn tại. Điều này có ích cho runtime sinh nhiều lớp tạm thời.

`MethodHandles.Lookup.ClassOption.STRONG` thay đổi **unloading relationship**:

- Hidden class `STRONG` có mối liên hệ mạnh với defining loader như ordinary class.
- Về nguyên tắc, lớp STRONG có thể unload khi và chỉ khi defining loader không còn reachable và có thể được thu hồi theo quy tắc tương ứng.
- Một hidden class **không STRONG** vẫn có thể tồn tại lâu nếu ứng dụng giữ `Class<?>`, `Lookup`, `MethodHandle` hoặc instance liên quan có tác dụng giữ class reachable.
- Không có `STRONG` **không có nghĩa** JVM bắt buộc phải unload ngay khi bạn gán `Class<?> = null`; GC và class unloading không bảo đảm thời điểm.
- Có `STRONG` **không có nghĩa** hidden class trở thành named class hoặc được đăng ký vào bảng lookup theo binary name.

Chọn `STRONG` khi lifecycle cần gắn chặt với loader; không chọn chỉ vì muốn `Class.forName` hoạt động. Để kiểm tra chính sách unloading thật sự cần công cụ GC/class unloading và quy trình đo phù hợp; **không thể chứng minh lifecycle chỉ bằng một lần `System.gc()`**.

### 9.1. Cùng bytes, nhiều hidden classes có static state độc lập

Nếu hai hidden classes có cùng bytecode `static int count; static int next(){return ++count;}`, mỗi class có **bản sao static field riêng**. Chúng có thể cùng loader, cùng package và cùng nominal name gốc nhưng identity và state vẫn khác.

### 9.2. Thực hành 4 — Một hidden class bình thường và một `STRONG`

Tạo tệp **`HiddenIsolationDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class HiddenIsolationDemo {
    static class Counter {
        private static int count;
        public static int next() {
            return ++count;
        }
    }

    static byte[] code() throws IOException {
        try (InputStream in = HiddenIsolationDemo.class.getResourceAsStream(
                "HiddenIsolationDemo$Counter.class")) {
            if (in == null) throw new IOException("missing class bytes");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup host = MethodHandles.lookup();
        byte[] bytes = code();
        MethodHandles.Lookup first = host.defineHiddenClass(bytes, true);
        MethodHandles.Lookup second = host.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.STRONG);
        Class<?> a = first.lookupClass();
        Class<?> b = second.lookupClass();
        MethodType signature = MethodType.methodType(int.class);
        MethodHandle nextA = first.findStatic(a, "next", signature);
        MethodHandle nextB = second.findStatic(b, "next", signature);
        System.out.println("distinct: " + (a != b));
        System.out.println("first call A: " + (int) nextA.invokeExact());
        System.out.println("second call A: " + (int) nextA.invokeExact());
        System.out.println("first call B: " + (int) nextB.invokeExact());
        System.out.println("both hidden: " + (a.isHidden() && b.isHidden()));
        System.out.println("same loader: " + (a.getClassLoader() == b.getClassLoader()));
        try {
            Class.forName(b.getName());
            System.out.println("unexpected Class.forName result");
        } catch (ClassNotFoundException expected) {
            System.out.println("STRONG still undiscoverable: ClassNotFoundException");
        }
    }
}
```

```bash
javac --release 17 HiddenIsolationDemo.java
java HiddenIsolationDemo
```

**Stdout chính xác:**

```text
distinct: true
first call A: 1
second call A: 2
first call B: 1
both hidden: true
same loader: true
STRONG still undiscoverable: ClassNotFoundException
```

**Giải thích:**

1. `first` và `second` được định nghĩa hai lần từ **cùng bytes**, nhưng `a != b`.
2. Lời gọi tới `nextA` tăng counter riêng của `a`: `1` rồi `2`.
3. Lời gọi tới `nextB` lần đầu trả `1` vì `b` có counter riêng.
4. `a` và `b` đều thuộc cùng defining loader, và `isHidden()` đều đúng.
5. Lựa chọn `STRONG` cho `b` **không** làm `Class.forName(b.getName())` tìm được nó. Dòng `ClassNotFoundException` là minh chứng cụ thể.

**Không suy diễn từ stdout:** Bài test này không chứng minh class `a` đã unload hoặc class `b` chắc chắn còn ở memory mãi. Nó chỉ chứng minh **type identity, state và khả năng tra cứu**; unloading policy được giải thích theo đặc tả API.

## 10. Reflection và `MethodHandle`: lấy class reference thay vì cố đoán tên

### 10.1. Không tự tạo class name rồi gọi `Class.forName`

Một cách sai khi xây dynamic runtime:

```java
// Chống ví dụ: hiddenClass.getName() không phải binary name.
// Class<?> lookedUp = Class.forName(hiddenClass.getName());
```

Phương pháp đúng: giữ object `Class<?>` hoặc `Lookup` trả về từ quá trình định nghĩa.

```java
// Fragment: bytes là class file hợp lệ trong cùng package.
MethodHandles.Lookup generatedLookup =
        privilegedLookup.defineHiddenClass(bytes, true);
Class<?> generatedType = generatedLookup.lookupClass();
// Tra cứu method bằng generatedLookup và generatedType, không Class.forName.
```

Đây là fragment minh họa, `privilegedLookup` chưa được định nghĩa độc lập. Các chương trình trên dùng `MethodHandles.lookup()` từ host có quyền phù hợp để cung cấp một ví dụ tự chứa.

### 10.2. Có thể dùng Reflection nhưng vẫn chịu quyền

Ví dụ với `Class<?> hidden` đã biết:

```java
// Fragment: hidden là Class<?> của một hidden class.
java.lang.reflect.Method[] methods = hidden.getDeclaredMethods();
for (java.lang.reflect.Method method : methods) {
    System.out.println(method.getName());
}
```

`getDeclaredMethods()` có thể liệt kê method khai báo trên hidden class. Việc **invoke** method private hoặc member nhạy cảm vẫn cần quyền reflection/module/nest phù hợp. `Class.isHidden()` không phải điều kiện cấm mọi reflection.

### 10.3. Tương tác với `Class::getName` và logging

Trong logging/metrics, bạn có thể in `hidden.getName()` để hỗ trợ chẩn đoán. Nhưng không nên:

- Lưu tên này vào cấu hình rồi hy vọng sau restart `Class.forName` resolve lại.
- Dùng tên sinh tự động làm khóa business ổn định.
- Parse suffix bằng regex rồi phụ thuộc vào layout nội bộ của JVM.
- Tự ghép string từ tên gốc để tìm hidden class khác có code giống.
- Gọi `ClassDesc.of(hidden.getName())` như thể đây là binary name hợp lệ.
- Coi `descriptorString()` của hidden class là field descriptor JVMS chuẩn để ghi vào class file của một class khác.

Khi cần identity runtime, giữ `Class<?>` hoặc một ID do ứng dụng tự quản lý. Một string phục vụ quan sát không thể thay thế reference thật.

## 11. Hidden class, class loader và unloading: các tầng trách nhiệm

### 11.1. Cùng loader không đồng nghĩa có cùng tên lookup

Một named class và hidden class có thể trả cùng `getClassLoader()` nhưng chỉ named class có binary name để loader resolve qua `loadClass`. Cùng class loader là **ngữ cảnh định nghĩa**, không phải bằng chứng rằng mọi class của loader đều tra cứu được bằng string.

### 11.2. Hai loader khác nhau có thể chứa named classes cùng tên

Ngay cả với named classes, tên như `com.example.Plugin` không đủ để xác định một class identity độc nhất trên toàn JVM. `Plugin` do loader A định nghĩa có thể **khác** `Plugin` do loader B định nghĩa, dù binary name giống. `Class.forName(name, initialize, loader)` có đối số loader vì identity gắn với loader và lookup environment.

Với hidden class, danh tính còn đặc thù hơn: tạo lại từ cùng bytes trong **cùng loader** cũng tạo một class object khác. Do đó:

```text
Named class identity ≈ (binary name, defining loader)
Hidden class identity = một định nghĩa riêng biệt do JVM tạo

Cùng code/loader không bảo đảm cùng class identity.
```

Dòng trên là mô hình học tập. Identity thực tế còn tuân theo quy tắc module/nest/method resolution của JVM, nhưng có thể kiểm tra ngay bằng so sánh reference `Class<?>` bằng `==`.

### 11.3. Khi nào class unloading quan trọng?

Runtime có thể tạo hàng nghìn hidden classes cho expressions, call-site adapters, dynamic proxies hoặc helper methods. Nếu mỗi class bắt buộc gắn sống tới loader suốt thời gian loader tồn tại, memory metadata có thể tăng đáng kể. Weak relationship mặc định cho phép VM reclaim hidden classes nếu không còn reachable theo quy tắc GC.

Tuy nhiên giữ một `MethodHandle` hoặc `Class<?>` trong cache toàn cục có thể giữ hidden class sống lâu hơn dự kiến. Vì vậy:

- Đặt cache theo lifecycle phù hợp; tránh giữ mọi generated class vô thời hạn.
- Không dựa vào `System.gc()` để đo đúng/sai của class unloading.
- Chỉ chọn `STRONG` khi cần mô hình lifetime gắn với loader.
- Không dùng `Class.forName` làm công cụ kiểm tra hidden class còn sống hay đã unload; API này **luôn không tìm hidden class**, kể cả khi class vẫn sống.

### 11.4. Mục đích thiết kế: không cần name-based linkage cho implementation tạm thời

Nhiều runtime generator chỉ muốn **một implementation có thể invoke**, không muốn lớp mới được tham chiếu nominal từ class code khác. Hidden class phục vụ mục tiêu đó; nhận biết loại này giúp giải thích vì sao một lambda runtime implementation đôi lúc có class name không gọi lại được bằng `Class.forName`.

Nhưng **đừng khẳng định mọi lambda trên mọi JVM nhất thiết là hidden class**. Đây là khả năng triển khai của JVM/runtime; ngôn ngữ Java chỉ đặt hợp đồng functional interface và hành vi lambda. Hãy dùng `obj.getClass().isHidden()` nếu bạn thực sự cần quan sát runtime đang sử dụng.

## 12. Các lỗi và ngoại lệ thường gặp

| Hiện tượng / exception | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException` khi `Class.forName(hidden.getName())` | Hidden class **không có binary name** tra cứu được | Giữ `Class<?>`/`Lookup`/`MethodHandle`; không tìm bằng string |
| `ClassNotFoundException` khi `Class.forName(namedName)` | Class loader/class path/module context hoặc binary name không khớp | Kiểm tra defining loader, tên binary (nested dùng `$`), khả năng hiển thị |
| `LinkageError` khi gọi `defineClass(bytes)` hai lần | Đã định nghĩa named class với cùng binary name trong cùng defining loader | Tránh duplicate; dùng loader riêng hoặc hidden classes nếu nhu cầu là implementation động |
| `IllegalAccessException` ở `defineHiddenClass` | `Lookup` thiếu full privilege | Cấp lookup đúng quyền từ caller; không dùng `publicLookup` |
| `IllegalArgumentException` khi bytes có package khác | Hidden class phải thuộc package phù hợp của lookup class | Sửa internal name/package trong generator, hoặc dùng lookup đúng package |
| `ClassFormatError`/`VerifyError` | Bytes không tạo class file hợp lệ hoặc bytecode không thỏa quy tắc verify | Kiểm chứng compiler/generator, phiên bản classfile, constant pool/stack frames |
| `IllegalAccessError` khi hidden code đọc private host field | Thiếu `NESTMATE` hoặc nest/private access không hợp lệ | Dùng `NESTMATE` khi đúng quyền và mục đích, kiểm tra `getNestHost()` |
| `NoSuchMethodException` khi `Lookup.findStatic` | Tên/type method tra cứu sai | Kiểm tra `MethodType`, return type, static vs instance |
| `WrongMethodTypeException` khi `invokeExact` | Call-site type khác handle type (cả return type) | Xem `handle.type()`, cast kết quả chính xác hoặc dùng adapter hợp lệ |
| `ExceptionInInitializerError` | `<clinit>` ném exception khi initialize hidden hoặc named class | Xem cause, phân biệt lúc define/link và lúc initialize |
| `NullPointerException` khi đọc bytecode resource | `getResourceAsStream(...)` trả `null` do thiếu `.class` | Kiểm tra path/resource; xử lý missing resource trước khi define |
| GC không unload hidden class như mong đợi | Còn reference giữ class, dùng `STRONG` hoặc GC chưa quyết định unload | Kiểm tra cache/lifecycle/loader, dùng công cụ quan sát class unloading |
| Tên trong stacktrace có `/0x...` | Runtime method thuộc hidden class | Đây là dấu hiệu có thể gặp, không dùng suffix để định vị bằng Class.forName |
| Named `Class.forName` tìm được class khác với hidden | Cùng class bytes nhưng **hai definitions** | So sánh `Class<?>` identity, loader và `isHidden()` |

### 12.1. `ClassNotFoundException` không có nghĩa hidden class chưa được định nghĩa

Nếu bạn đã có `Class<?> hidden` và `hidden.isHidden()==true`, việc `Class.forName(hidden.getName())` thất bại là **hành vi thiết kế**, không phải lỗi nạp thiếu class file. Không nên thử thêm classpath entries để “sửa” lookup đó. Bạn cần truyền class reference/Lookup tương ứng thay vì tên.

### 12.2. Chú ý loại API khi debug

- `Lookup.defineHiddenClass`: định nghĩa và link hidden class theo bytes.
- `Lookup.defineClass`: định nghĩa named class theo bytes.
- `Class.forName`: tìm/nạp một class theo binary name (và initialize theo overload).
- `ClassLoader.loadClass`: cơ chế tìm/nạp named class theo tên.
- `Class.getName`: báo tên runtime; **không bảo đảm** mọi tên trả về đều có thể được nạp lại bằng `Class.forName`.
- `Class.isHidden`: kiểm tra loại ẩn trực tiếp trên `Class<?>`.
- `Lookup.ensureInitialized`: yêu cầu initialize class, khi quyền phù hợp.
- `MethodHandles.Lookup.ClassOption.NESTMATE`: thay nest membership khi define hidden class.
- `MethodHandles.Lookup.ClassOption.STRONG`: thay unloading relationship khi define hidden class.

Không nên gộp mọi thao tác này thành một từ mơ hồ “load class”.

## 13. Thiết kế ứng dụng dùng hidden class đúng mục đích

### 13.1. Trả về interface có tên, giấu implementation runtime

Một API công khai có thể trả đối tượng implement `Runnable`, `Callable<R>` hoặc một domain interface có tên. Implementation được runtime tạo bằng hidden class có thể được gọi qua interface mà client không cần tên implementation.

```text
Client code:
    Task task = factory.createTask();  // Task là named interface
    task.run();                         // gọi hợp đồng interface

Runtime factory:
    bytes của hidden implementation
       |
    defineHiddenClass(..., options)
       |
    Lookup + Class<?> hidden
       |
    tạo instance / MethodHandle / constructor thích hợp
       |
    trả Task cho client
```

Đây là **sơ đồ**, không phải một chương trình Java độc lập. Mục tiêu là giữ API ổn định dưới dạng named interface, trong khi code implementation có thể sinh và thu hồi linh hoạt.

### 13.2. Truy cập private host với quyền có kiểm soát

Nếu framework cần triển khai một private helper trên host, `NESTMATE` phù hợp khi host tự cung cấp lookup đủ quyền. Không nên coi `NESTMATE` là cách tự ý nâng quyền cho bytecode không tin cậy; bytes được định nghĩa sẽ chạy code với quyền theo ngữ cảnh đã cấp.

Điều này đặc biệt quan trọng nếu input đến từ user/plugin không tin cậy. Trước khi gọi `defineHiddenClass`, cần biết nguồn bytes, classfile validation và mô hình sandbox/permission của ứng dụng. Hidden class **không phải sandbox**; “không tìm được theo tên” không có nghĩa “an toàn khi chạy mã tùy ý”.

### 13.3. Bộ nhớ và hoạt động lâu dài

Nếu runtime tạo hidden class mới cho từng expression:

- Cân nhắc cache keyed theo expression semantics thay vì tạo trùng vô hạn.
- Không giữ class references trong static collection không giới hạn.
- Dùng weak/strong lifecycle có chủ ý và quan sát memory.
- Nếu cần discover/persist một lớp ổn định theo binary name trên nhiều lần chạy, hidden class **không phù hợp**; hãy dùng named class cùng class loader/packaging tương ứng.
- Khi thiết kế serialization/protocol, đừng phụ thuộc vào hidden runtime class name để deserialize qua `Class.forName`.

## 14. Câu hỏi tự kiểm tra

1. `defineHiddenClass` nhận những tham số chính nào và trả gì?
2. Vì sao `Class.forName(hidden.getName())` thất bại dù `hidden.isHidden()==true` và hidden class đang sống?
3. Một named class và hidden class được tạo từ cùng bytes có nhất thiết là cùng `Class<?>` không?
4. `Class.forName("Host$Template")` tìm ra một named class có nghĩa nó tìm được hidden copy của `Host$Template` không?
5. `Class.getName()` của hidden class chứa dấu đặc biệt nào khiến nó không là binary name?
6. Có thể dùng `MethodHandle` để gọi method trên hidden class khi `Class.forName` không tìm được không?
7. `initialize=false` nghĩa là class chưa được tạo, hay đã tạo nhưng chưa bắt buộc chạy `<clinit>`?
8. `defineHiddenClass(bytes,true)` và `Class.forName(name)` giống/khác nhau ở chỗ nào?
9. `NESTMATE` thay đổi điều gì? Vì sao cùng bytes có thể đọc private field khi có option, nhưng `IllegalAccessError` khi không có?
10. `STRONG` có cho phép `ClassLoader.loadClass(hidden.getName())` không?
11. Nếu hai hidden classes dùng cùng bytes và same loader, static fields có chung dữ liệu không?
12. Vì sao không thể dựa vào `System.gc()` để kiểm định hidden class đã unload?
13. `MethodHandles.publicLookup()` có thể tùy ý `defineHiddenClass` vào package của bất kỳ class nào không?
14. Hidden class có thể được nhìn thấy bởi code thông qua `obj.getClass()` không?
15. Khi nào nên dùng named class thay hidden class để hỗ trợ discovery?
16. Nếu một named nested class có binary name `com.example.Outer$Inner`, `Class.forName("com.example.Outer.Inner")` có phải tên phù hợp không?

### Gợi ý đáp án

1. `byte[] bytes`, `boolean initialize`, tùy chọn `ClassOption...`; trả `Lookup` trên hidden class mới.
2. Hidden class không có binary name; `Class.forName` là nominal lookup, không tìm được nó.
3. Không; mỗi định nghĩa class tạo identity riêng.
4. Không; đó là named class theo binary name, không phải hidden copy.
5. Dấu `/` và suffix VM-sinh; không là binary name hợp lệ.
6. Có; dùng `hiddenLookup.findStatic(...)`, `findVirtual(...)` hoặc reflection với `Class<?>` đã giữ và quyền phù hợp.
7. Đã tạo/link class, nhưng initialization có thể hoãn.
8. Cùng có thể dẫn đến initialize, nhưng một bên **định nghĩa hidden class từ bytes**, bên kia **tìm/nạp named class theo tên**.
9. Thêm hidden class vào nest của lookup class, cho phép private access hợp lệ; không có NESTMATE thì mặc định self-nest.
10. Không; STRONG chỉ ảnh hưởng unloading relationship.
11. Không; `Class<?>` identity và static state riêng.
12. JVM/GC quyết định thời điểm; references có thể giữ class, GC không có lịch bảo đảm.
13. Không; `defineHiddenClass` yêu cầu full privilege và package/module phù hợp.
14. Có; hidden không đồng nghĩa vô hình đối với Reflection.
15. Khi cần tham chiếu nominal, `Class.forName`, cấu hình class names hoặc ABI ổn định.
16. Không; nested binary name dùng `$`.

## 15. Tài liệu gốc để tra cứu

- [Java SE 21 API — `MethodHandles.Lookup.defineHiddenClass` và `Lookup.defineClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): bytecode, package, quyền full privilege, initialize, hidden name, NESTMATE/STRONG và các lỗi thường gặp.
- [Java SE 21 API — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): hai giá trị `NESTMATE` và `STRONG`, truy cập private và vòng đời.
- [Java SE 21 API — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isHidden`, `getName`, `getCanonicalName`, `descriptorString` và vì sao `Class.forName` không tìm hidden classes.
- [Java SE 21 API — `MethodHandles`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): cách tạo Lookup và các phương thức tìm method handle.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): động cơ thiết kế, non-discoverability, lifecycle, không có binary name và thay thế cơ chế anonymous-class cũ.
- [JVMS Java SE 21 — `5.3.5 Deriving a Class from a class File Representation`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5): lớp thông thường, phân biệt cách VM derive class.
- [Java SE 21 JLS — `12.4 Initialization of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): thời điểm chạy `<clinit>`.
- [Java SE 21 JLS — `12.7 Unloading of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7): nguyên tắc class unloading.
- [Oracle JDK 15 Release Notes — JEP 371 impacts](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): `Class.getName` của hidden class có dấu `/` và descriptorString chứa suffix đặc biệt.

**Kết luận:** `defineHiddenClass` tạo **một class thật nhưng không có binary name để tra cứu nominal**; vì vậy `Class.forName(hidden.getName())` không thể phục hồi `Class<?>` ấy. Khi muốn sử dụng hidden implementation, giữ reference `Lookup`, `Class<?>` hoặc `MethodHandle`. Nếu bạn cần class có tên để tìm bằng `Class.forName`, dùng cơ chế **named class** và đúng class loader. Tham số `initialize`, lựa chọn `NESTMATE`/`STRONG` và cơ chế class unloading là các trục thiết kế khác với việc lớp có thể được tìm theo tên hay không.