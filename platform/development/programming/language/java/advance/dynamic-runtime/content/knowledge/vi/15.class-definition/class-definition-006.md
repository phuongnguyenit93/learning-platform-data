# 15.6 defineHiddenClassWithClassData và truy xuất dữ liệu lớp bằng MethodHandles

Java có thể định nghĩa một **hidden class** trực tiếp từ bytecode và gắn một đối tượng dữ liệu riêng vào identity của class đó. Cặp API quan trọng là `MethodHandles.Lookup.defineHiddenClassWithClassData` để **tạo class và gắn data**, rồi `MethodHandles.classData` / `MethodHandles.classDataAt` để **đọc data** từ một `Lookup` có quyền thích hợp.

Cơ chế này hữu ích cho runtime compiler, lambda-like implementation, framework tạo serializer, DSL interpreter hoặc những thư viện cần sinh nhiều class từ cùng template với những cấu hình khác nhau. Nó không phải API thay thế mọi static field hay constructor trong Java thông thường.

Những điểm phải nắm:

- `defineHiddenClassWithClassData(bytes, classData, initialize, options...)` nhận **byte[] của class file đã hợp lệ** và **một object dữ liệu**; nó **không biên dịch Java source**.
- Kết quả là `MethodHandles.Lookup` trỏ đến **hidden class mới**, không phải `Class<?>` trực tiếp. Lấy `Class<?>` qua `hiddenLookup.lookupClass()`.
- `MethodHandles.classData(hiddenLookup, "_", List.class)` đọc **toàn bộ object**. Nếu object là `List`, `classDataAt(hiddenLookup, "_", String.class, 0)` đọc một phần tử.
- Tên của constant/data luôn là `"_"` (`ConstantDescs.DEFAULT_NAME`); không thể tùy ý dùng `"config"` hoặc tên field.
- Lookup dùng để đọc cần có **`Lookup.ORIGINAL` access**, cao hơn việc chỉ có một tham chiếu `Class<?>` hoặc quyền reflection thông thường.
- Class data có thể được đọc bằng cách gọi API trực tiếp hoặc thông qua **bootstrap của `CONSTANT_Dynamic`** trong bytecode được sinh động.
- Cần phân biệt **định nghĩa/link** class, **khởi tạo** class, **đọc dữ liệu**, **gọi method handle**, và **vòng đời/unloading**.

## 1. Bản đồ các đối tượng tham gia

| Đối tượng | Chức năng | Không đồng nghĩa với |
| --- | --- | --- |
| `byte[] bytes` | Class file bytes mô tả template JVM hợp lệ | File `.java` hoặc tên class |
| `Lookup host` | Quyền định nghĩa class trong đúng runtime package/module | Một class loader tùy ý |
| `classData` | Một object gắn với hidden class; có thể là `List.of(...)` hoặc cấu hình riêng | Static field Java có tên |
| `Lookup hiddenLookup` | Lookup được trả về, trỏ vào class mới, có `ORIGINAL` và full privilege | Lookup của host |
| `Class<?> hidden` | Identity của hidden class, `isHidden() == true` | Class template bình thường |
| `MethodHandles.classData` | Lấy nguyên object data, theo lookup class | `Class.getDeclaredField` |
| `MethodHandles.classDataAt` | Lấy một phần tử theo chỉ số trong List data | Indexed accessor cho bất kỳ Map/array nào |
| `MethodHandle` | Handle gọi một method/constructor của hidden class hoặc method khác | Class data tự nó |
| `CONSTANT_Dynamic` | Constant-pool entry được bootstrap tính giá trị | `invokedynamic` dùng `CallSite` để liên kết lời gọi |

Sơ đồ luồng:

~~~text
Framework (host, trusted)
  |
  +-- class file bytes của Template
  +-- data = List.of("prefix:", 2)
  |
  v
hostLookup.defineHiddenClassWithClassData(bytes, data, false, NESTMATE)
  |
  +----> hiddenLookup (ORIGINAL + full privilege)
            |
            +----> lookupClass() ----> Class<?> hidden; hidden.isHidden() == true
            |
            +----> MethodHandles.classData(hiddenLookup, "_", List.class)
            |                                 -> ["prefix:", 2]
            |
            +----> classDataAt(hiddenLookup, "_", String.class, 0)
            |                                 -> "prefix:"
            |
            +----> findStatic(hidden, "render", (String)String)
                                        |
                                        v
                                invokeExact("Go")
                                        |
                              code của hidden class dùng
                              MethodHandles.lookup() của nó
                                        |
                           classData + classDataAt theo ORIGINAL
                                        |
                                        v
                           "prefix:GoGo / entries=2"
~~~

**Lưu ý tách hai việc:** hidden class là code JVM mới, còn `classData` là **object dữ liệu** mà JVM gắn với class đó. Một class có thể nhận data chứa `MethodHandle`; nhưng nó không biến bản thân data thành lời gọi method. Cần xây dựng handle thực thi riêng khi muốn chạy logic.

## 2. Chữ ký API: định nghĩa class có dữ liệu

~~~java
MethodHandles.Lookup defineHiddenClassWithClassData(
        byte[] bytes,
        Object classData,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
~~~

Phương thức được gọi **trên một `Lookup`**, ví dụ `MethodHandles.lookup()` tạo tại code host trusted. Nó yêu cầu lookup có **full privilege access** (`PRIVATE` và `MODULE` access); `publicLookup()` thường không đủ quyền.

| Tham số | Vai trò | Điều kiện/lưu ý |
| --- | --- | --- |
| `bytes` | Mảng byte của một `ClassFile` hợp lệ | Class file version được hỗ trợ, verifier hợp lệ, **cùng package** với lookup class |
| `classData` | Đối tượng đã chuẩn bị trước khi định nghĩa | Có thể gói nhiều giá trị vào `List.of(...)`; nên bất biến |
| `initialize` | `true` để yêu cầu khởi tạo ngay; `false` để trì hoãn | `classData`/`classDataAt` có thể chủ động kích hoạt `<clinit>` sau đó |
| `options` | `NESTMATE`, `STRONG`, hoặc không có option | Ảnh hưởng quyền nest và vòng đời hidden class |
| Kết quả | `Lookup` trên hidden class vừa định nghĩa | Có `ORIGINAL` và **full privilege** trên class mới |

So với `Lookup.defineHiddenClass(bytes, initialize, options...)`, biến thể `WithClassData` còn gắn một **object data**. `defineHiddenClass` thường không gắn data; khi đọc bằng `MethodHandles.classData` trên một hidden class không có data, kết quả là `null`.

### Vì sao API trả `Lookup`, không trả trực tiếp `Class<?>`?

Framework cần một capability để tiếp tục lookup method/constructor của class mới và, nếu hợp lệ, đọc class data. `Lookup` vừa được trả có `lookupClass()` trả `Class<?>`; nó cũng mang quyền ban đầu cho chính class mới. Bạn có thể gọi `hiddenLookup.findStatic(hiddenClass,...)` hoặc `hiddenLookup.findConstructor(...)` theo chữ ký, không cần tìm class bằng tên qua `Class.forName`.

Tuy nhiên, **không nên công khai toàn bộ original Lookup** cho thành phần không đáng tin. Capability này có thể làm được nhiều việc hơn một method handle chuyên biệt; hãy chỉ truyền cho phía tiêu thụ thứ họ thực sự cần.

## 3. `MethodHandles.classData`: đọc trọn object, không đọc field

Chữ ký chuẩn:

~~~java
public static <T> T classData(
        MethodHandles.Lookup caller,
        String name,
        Class<T> type) throws IllegalAccessException
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| `caller` | `Lookup` có `ORIGINAL`; `caller.lookupClass()` là class mà JVM đọc class data |
| `name` | Bắt buộc đúng `"_"` (hằng `ConstantDescs.DEFAULT_NAME`), không phải một key tùy chọn |
| `type` | Kiểu yêu cầu khi lấy data, như `List.class`, `String.class`, `MethodHandle.class` |

Ví dụ data là `List.of("prefix:", 2)`:

~~~java
List<?> all = MethodHandles.classData(hiddenLookup, "_", List.class);
~~~

Đây là snippet **không độc lập**, giả sử `hiddenLookup` đã trỏ tới hidden class có data List. `List<?>` cho thấy erasure ở Java runtime: không có `List<String>.class`. Nếu type yêu cầu không tương thích với object thật, API ném `ClassCastException`. Nếu class không có data, trả `null`.

Nếu gọi:

~~~java
MethodHandles.classData(hostLookup, "_", List.class);
~~~

thì API đọc dữ liệu của **`hostLookup.lookupClass()`**, không tự động đọc hidden class nào từng được host tạo. Với host class bình thường không có data, kết quả `null`. Đây là lỗi tư duy khá phổ biến: `Lookup` xác định **đích**, không phải object `Class<?>` bạn đang nghĩ tới trong scope.

**Điều kiện truy cập:** `ORIGINAL` là một mode đặc biệt. Một `Lookup` có thể truy cập được private methods theo access rules nhưng vẫn **không có `ORIGINAL`**, do đó không thể đọc class data. `MethodHandles.lookup()` được gọi ngay bên trong code hidden class tạo lookup original của chính nó; returned hidden Lookup từ factory cũng có original access.

## 4. `MethodHandles.classDataAt`: dữ liệu dạng List

Chữ ký:

~~~java
public static <T> T classDataAt(
        MethodHandles.Lookup caller,
        String name,
        Class<T> type,
        int index) throws IllegalAccessException
~~~

Phương thức này dành cho **List class data**, đọc từng phần tử theo `index`. Tham số `type` là **kiểu của phần tử**, không phải type của List.

Ví dụ:

~~~java
String prefix = MethodHandles.classDataAt(
        hiddenLookup, "_", String.class, 0);
Integer repeat = MethodHandles.classDataAt(
        hiddenLookup, "_", Integer.class, 1);
~~~

Nếu class data là `List.of("prefix:", 2)`, kết quả tương ứng là `"prefix:"` và `Integer.valueOf(2)`.

| Vấn đề | Hành vi |
| --- | --- |
| `name` khác `"_"` | `IllegalArgumentException` |
| Lookup không có `ORIGINAL` | `IllegalAccessException` |
| Class data không phải `List` | `ClassCastException` khi cần đọc như List |
| Phần tử có kiểu không phù hợp với `Class<T>` | `ClassCastException` |
| Index âm hoặc lớn hơn kích thước List | `IndexOutOfBoundsException` |
| Dữ liệu class không tồn tại | Trả `null` theo hợp đồng API |
| Một phần tử `null` trong tình huống cần unboxing primitive | Có thể gặp `NullPointerException` |

`List.of(...)` không chấp nhận phần tử null và không cho phép sửa cấu trúc List; đây là lựa chọn phù hợp khi dữ liệu được dùng như thông tin cố định của một hidden class. Nếu muốn truyền một object đơn lẻ, **không cần tạo List**: `classData` đọc object đó trực tiếp, còn `classDataAt` chỉ dùng khi có List.

### `classData` không phải API theo “tên nhiều biến”

Một hidden class gắn **một object dữ liệu**. Bạn không thể gọi `classData(hiddenLookup,"name1",...)` và `classData(hiddenLookup,"name2",...)` để đọc hai trường tách biệt. Giải pháp là tạo một **record/config object** hoặc một **List** rồi truy cập theo phần tử/schema. Ký tự `"_"` là tên chuẩn hóa của constant-dynamic bootstrap, không phải khóa lưu trữ do người dùng đặt.

## 5. Quyền truy cập: `full privilege` để định nghĩa, `ORIGINAL` để đọc

Hai thao tác cần quyền khác nhau:

1. **Định nghĩa:** `hostLookup.defineHiddenClassWithClassData(...)` đòi `hostLookup.hasFullPrivilegeAccess()` đúng. Bytes phải mô tả class hoặc interface cùng package.
2. **Đọc:** `MethodHandles.classData(hiddenLookup,"_",...)` đòi `hiddenLookup.lookupModes()` chứa `Lookup.ORIGINAL`. Quyền `PRIVATE`/`MODULE` ở một lookup chuyển ngữ cảnh không tự động thay thế `ORIGINAL`.

Bảng:

| `Lookup` | Có thể làm gì? |
| --- | --- |
| `MethodHandles.lookup()` trong host trusted | Có thể định nghĩa hidden class cùng package khi đủ full privilege |
| Lookup trả từ `defineHiddenClassWithClassData` | Trỏ tới hidden class mới, có `ORIGINAL` và full privilege |
| `MethodHandles.lookup()` gọi trong method của hidden class | Original Lookup của chính hidden class; dùng để đọc class data |
| `MethodHandles.publicLookup()` | Không đủ full privilege để định nghĩa hidden class, không có `ORIGINAL` để đọc class data |
| `lookup.in(otherClass)` | Có thể mất modes; không phải cách cấp `ORIGINAL` |
| `MethodHandles.privateLookupIn(...)` | Chịu access/JPMS checks, không phải lệnh tạo tùy ý quyền `ORIGINAL` |
| `hiddenLookup.dropLookupMode(PRIVATE)` | Trong ví dụ, làm mất quyền cần thiết, `classData` báo `IllegalAccessException` |

Trong chương trình sau, kiểm tra:

~~~java
(hiddenLookup.lookupModes() & MethodHandles.Lookup.ORIGINAL) != 0
~~~

trả `true`. Điều này chứng minh lookup do factory cấp mang mode cần dùng; một `Class<?>` đơn thuần không có thông tin capability tương đương.

**Không gọi `Class.forName(hidden.getName())` để khôi phục quyền.** Hidden class không được tìm lại theo tên thông thường, và dù có class reference, bạn cũng không tự nhiên nhận được original Lookup của nó.

## 6. Class bytes, cùng package và identity

`defineHiddenClassWithClassData` nhận **class file bytes**. Bạn có thể lấy từ:

- Một class template biên dịch trước, đọc resource `.class` qua `Class.getResourceAsStream`.
- Bytecode generator/library phù hợp và đã kiểm chứng class file.
- Code generator của một DSL/runtime compiler, sau đó pass `byte[]` vào Lookup.

Không truyền đường dẫn file `.java`, source string hay binary name. Khi tự dùng class template, **bytecode phải nằm trong cùng runtime package** với lookup class. Đường resource chỉ là cách lấy bytes của template đã biên dịch; hidden class thực tế được JVM tạo riêng.

Ví dụ:

~~~java
String resource =
        "/" + Template.class.getName().replace('.', '/') + ".class";
byte[] bytes;
try (InputStream input = Template.class.getResourceAsStream(resource)) {
    if (input == null) throw new IOException("Missing: " + resource);
    bytes = input.readAllBytes();
}
~~~

Snippet cần `InputStream`, `IOException` và một nested class `Template` trong chương trình thật. Nếu source đặt vào package `example.runtime`, đảm bảo cả host và Template cùng package, đồng thời resource path được dựng từ binary name như trên.

**Kết quả là class identity mới.** Dù bytes được lấy từ `Template.class`, hidden class tạo ra **khác** với template bình thường. `Class.isHidden()` trả `true`, tên runtime có dạng chứa hậu tố do JVM quản lý, và không được tìm bằng `Class.forName(...)` theo cách tra tên thông thường. Mỗi lần gọi factory với cùng bytes thường tạo **một hidden class mới**, có class data riêng.

## 7. Java 17+ đầy đủ: tạo hidden class có List data, gọi method và kiểm tra lỗi

Tạo file **`HiddenClassDataDemo.java`**. Chương trình không cần thư viện ngoài, vì nó tái sử dụng bytes của nested class template. Method `Template.render` được thực thi **trong hidden class**, nên `MethodHandles.lookup()` bên trong nó trỏ về hidden class, không về host.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.List;

public final class HiddenClassDataDemo {
    public static class Template {
        static {
            System.out.println("hidden template initialized");
        }
        public static String render(String input) throws IllegalAccessException {
            MethodHandles.Lookup self = MethodHandles.lookup();
            List<?> all = MethodHandles.classData(self, "_", List.class);
            String prefix = MethodHandles.classDataAt(self, "_", String.class, 0);
            Integer repeat = MethodHandles.classDataAt(self, "_", Integer.class, 1);
            return prefix + input.repeat(repeat) + " / entries=" + all.size();
        }
    }
    public static void main(String[] args) throws Throwable {
        String resource = "/" + Template.class.getName().replace('.', '/') + ".class";
        byte[] bytes;
        try (InputStream input = Template.class.getResourceAsStream(resource)) {
            if (input == null) throw new IOException("Missing class resource: " + resource);
            bytes = input.readAllBytes();
        }

        List<Object> data = List.of("prefix:", 2);
        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup hiddenLookup = host.defineHiddenClassWithClassData(
                bytes, data, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println("hidden = " + hidden.isHidden());
        System.out.println("hidden name has slash = " + hidden.getName().contains("/"));
        System.out.println("original access = " +
                ((hiddenLookup.lookupModes() & MethodHandles.Lookup.ORIGINAL) != 0));
        System.out.println("class data not ordinary field = " +
                (hidden.getDeclaredFields().length == 0));
        System.out.println("before reading class data");
        List<?> received = MethodHandles.classData(hiddenLookup, "_", List.class);
        System.out.println("class data = " + received);
        System.out.println("element 0 = " +
                MethodHandles.classDataAt(hiddenLookup, "_", String.class, 0));
        MethodHandle call = hiddenLookup.findStatic(hidden, "render",
                MethodType.methodType(String.class, String.class));
        System.out.println("handle type = " + call.type());
        System.out.println("render = " + (String) call.invokeExact("Go"));

        try {
            MethodHandles.classData(hiddenLookup, "wrongName", List.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong name = " + ex.getClass().getSimpleName());
        }
        try {
            MethodHandles.classData(hiddenLookup, "_", String.class);
        } catch (ClassCastException ex) {
            System.out.println("wrong type = " + ex.getClass().getSimpleName());
        }
        try {
            MethodHandles.classDataAt(hiddenLookup, "_", String.class, 9);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("wrong index = " + ex.getClass().getSimpleName());
        }
        MethodHandles.Lookup reduced = hiddenLookup.dropLookupMode(
                MethodHandles.Lookup.PRIVATE);
        try {
            MethodHandles.classData(reduced, "_", List.class);
        } catch (IllegalAccessException ex) {
            System.out.println("reduced lookup = " + ex.getClass().getSimpleName());
        }
        System.out.println("host data absent = " +
                (MethodHandles.classData(MethodHandles.lookup(), "_", Object.class) == null));

        try {
            Class.forName(hidden.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("Class.forName hidden = " + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy từ thư mục chứa file với **JDK 17 trở lên**:

~~~bash
javac --release 17 HiddenClassDataDemo.java
java HiddenClassDataDemo
~~~

**`stdout` đã kiểm tra chính xác trên JDK 24 với `javac --release 17`:**

~~~text
hidden = true
hidden name has slash = true
original access = true
class data not ordinary field = true
before reading class data
hidden template initialized
class data = [prefix:, 2]
element 0 = prefix:
handle type = (String)String
render = prefix:GoGo / entries=2
wrong name = IllegalArgumentException
wrong type = ClassCastException
wrong index = IndexOutOfBoundsException
reduced lookup = IllegalAccessException
host data absent = true
Class.forName hidden = ClassNotFoundException
~~~

Demo được **biên dịch thành công ở mức ngôn ngữ/API Java SE 17** với `--release 17` và **chạy trên JVM JDK 24**. Đây không phải khẳng định chương trình đã chạy riêng trên một máy JDK 17; tuy nhiên các API được sử dụng đều có từ Java 16 và toàn bộ output trên đã được đối chiếu từ lần chạy thật.

### 7.1. Vì sao `hidden.isHidden()` là `true`?

`host.defineHiddenClassWithClassData` không tìm lại hay sửa `Template.class`, mà tạo một hidden class identity mới từ bytes. Trong JVM được dùng để test, tên của class này chứa `/` và suffix đặc biệt, và `Class.forName(hidden.getName())` ném `ClassNotFoundException`. Điều này minh họa **không thể coi hidden class như class public tra cứu được theo tên**; giữ `hiddenLookup`/`Class<?>`/`MethodHandle` mà factory cung cấp khi cần sử dụng tiếp.

### 7.2. Vì sao class data không xuất hiện như field thông thường?

Template trong demo không khai báo field dữ liệu. Kết quả `hidden.getDeclaredFields().length == 0` là `true` trong lần test, trong khi `MethodHandles.classData(hiddenLookup,"_",List.class)` vẫn lấy được `[prefix:,2]`. API class data có mô hình JVM riêng; không cần và không nên giả định một static field public/private với tên `"classData"` tồn tại để đọc.

### 7.3. Vì sao static initializer chạy ở giữa output?

`defineHiddenClassWithClassData(..., false, ...)` **định nghĩa và liên kết** class nhưng chưa tự yêu cầu khởi tạo. Sau khi in `before reading class data`, câu `MethodHandles.classData(...)` **bảo đảm khởi tạo class** nếu chưa khởi tạo. Vì vậy thứ tự:

~~~text
before reading class data
hidden template initialized
class data = [prefix:, 2]
~~~

không phải ngẫu nhiên. Nếu truyền `initialize=true`, initialization được yêu cầu trong khi định nghĩa class, nên static initializer có thể chạy sớm hơn.

### 7.4. Vì sao `render` có thể đọc data từ chính hidden class?

`Template.render` khi được thực thi trên **hidden class** sẽ gọi `MethodHandles.lookup()` ở ngữ cảnh của hidden class. Lookup này có `ORIGINAL`, nên `classData` đọc List và `classDataAt` đọc prefix/repeat. `"Go".repeat(2)` là `"GoGo"`; kết quả `prefix:GoGo / entries=2`. `hiddenLookup.findStatic` tạo handle type `(String)String`, và `invokeExact` được gọi với kiểu argument/return trùng chính xác.

### 7.5. Vì sao lỗi name/type/index/access khác nhau?

- `wrongName` khác `"_"` → `IllegalArgumentException`.
- Yêu cầu `String.class` cho toàn bộ data `List` → `ClassCastException`.
- Lấy index `9` của List hai phần tử → `IndexOutOfBoundsException`.
- `dropLookupMode(PRIVATE)` làm mất `ORIGINAL` của lookup này → `IllegalAccessException`.
- Gọi `classData` với lookup của **host class bình thường** trả `null`, không phải class data của hidden class vừa tạo.

Những ngoại lệ xuất hiện ở **bước đọc**, không phải lỗi Java compiler vì sử dụng kiểu generic List hay lỗi `MethodHandle.invokeExact`.

## 8. `CONSTANT_Dynamic` (condy): đọc class data trong bytecode như một hằng động

`MethodHandles.classData` và `classDataAt` được thiết kế để có thể dùng làm **bootstrap methods** cho một **dynamically computed constant** trong JVM constant pool. Runtime framework có thể sinh một hidden class với bytecode có `CONSTANT_Dynamic_info` trỏ tới các bootstrap này. Khi constant được resolve, JVM cung cấp lookup của class chứa vị trí resolution cùng tên/loại hằng, rồi nhận kết quả từ class data.

Ví dụ **sơ đồ bytecode/constant-pool**, không phải Java source độc lập:

~~~text
Hidden class data = List.of("PREFIX:", methodHandle, schemaObject)
                                  |
                                  v
Constant-pool entry CONSTANT_Dynamic
  name               = "_"
  descriptor          = Ljava/lang/invoke/MethodHandle;
  bootstrap reference = MethodHandles.classDataAt
  static argument     = index 1
                                  |
                         JVM resolve constant
                                  |
             classDataAt(originalLookup, "_", MethodHandle.class, 1)
                                  |
                                  v
                     MethodHandle từ List data
                                  |
                 constant-dynamic entry đã resolve
~~~

Phân biệt `classData` và `classDataAt` khi là bootstrap:

| Bootstrap | Giá trị nhận |
| --- | --- |
| `MethodHandles.classData(caller, "_", DesiredType.class)` | Toàn bộ object data, đã cast/chuyển theo kiểu yêu cầu |
| `MethodHandles.classDataAt(caller, "_", ItemType.class, index)` | Một item của List; `index` là **static bootstrap argument** |

**Condy không phải invokedynamic.** `CONSTANT_Dynamic` liên kết một **giá trị constant** và có descriptor là kiểu giá trị đó; `invokedynamic` liên kết một **lời gọi** qua `CallSite` và có method descriptor. Cả hai có thể dùng bootstrap Lookup, nhưng semantics/loại kết quả khác nhau.

Java source thuần thường không có cú pháp để khai báo tùy ý một `CONSTANT_Dynamic` với bootstrap do mình chọn. Muốn hiện thực sơ đồ này, framework cần **sinh class file đúng chuẩn** (có thể bằng bytecode library hoặc API class-file phù hợp), sau đó định nghĩa hidden class từ bytes đã sinh. Chương trình ở mục 7 minh họa **đọc class data trực tiếp**, không giả vờ rằng một lời gọi Java bình thường đã sinh custom condy.

### Vì sao condy được nhắc tới trong tài liệu class data?

Class data được thiết kế để dữ liệu chỉ sẵn có với **Lookup có `ORIGINAL`**. Khi code của hidden class cần một `MethodHandle` hoặc class metadata gắn cùng class, bootstrap constant-dynamic có thể giúp nạp trực tiếp giá trị cần thiết mà không đưa dữ liệu vào một static field có tên. Điều này hỗ trợ các framework cần giới hạn phạm vi truy cập. Tuy vậy, nếu code chủ động xuất bản dữ liệu hoặc original Lookup cho bên ngoài, cơ chế hidden không tự ngăn rò rỉ.

## 9. `NESTMATE` và `STRONG` là hai lựa chọn khác nhau

| `Lookup.ClassOption` | Nghĩa | Khi nào dùng |
| --- | --- | --- |
| Không dùng `NESTMATE` | Không yêu cầu hidden class là nestmate của lookup class | Khi không cần private access giữa những class trong nest |
| `NESTMATE` | Hidden class được gắn vào nest tương ứng theo JVM rules | Khi code được sinh cần quyền nest access hợp lệ |
| Không dùng `STRONG` | Hidden class có thể được unloading khi không còn references giữ class sống | Khi muốn hidden class có vòng đời tạm |
| `STRONG` | Hidden class được giữ mạnh theo class loader gần với class thông thường | Khi cần lớp tồn tại ổn định cho tới lúc class loader không còn |

**Điểm cần nhớ:** `NESTMATE` **không làm mọi nestmate được đọc class data**. Quyền đọc data vẫn yêu cầu `ORIGINAL` của lookup class đúng đích. Tương tự, `STRONG` không tác động tới kiểu data hay quyền truy cập data; nó liên quan tới **vòng đời class**.

Nếu tạo nhiều hidden classes mà vẫn giữ toàn bộ `Class<?>`, `Lookup` và `MethodHandle` trong một cache toàn cục, bạn có thể khiến chúng tồn tại lâu hơn dự kiến ngay cả khi không dùng `STRONG`. Hãy thiết kế cache/class loader lifecycle rõ ràng, đo metaspace và loại bỏ references không còn dùng.

## 10. Khởi tạo lớp: `initialize=false` không có nghĩa “không bao giờ chạy `<clinit>`”

Quá trình:

~~~text
defineHiddenClassWithClassData(bytes, data, false, options)
  -> class được định nghĩa + liên kết
  -> chưa bắt buộc khởi tạo tại chính factory
  -> hiddenLookup.lookupClass() có thể lấy Class object

Sau đó:
MethodHandles.classData(hiddenLookup, "_", Type.class)
  -> bảo đảm khởi tạo hidden class nếu chưa khởi tạo
  -> trả data sau khi checks hợp lệ

Hoặc:
defineHiddenClassWithClassData(bytes, data, true, options)
  -> định nghĩa + liên kết + chủ động yêu cầu initialization
~~~

Khi đọc class data, JVM có thể thực thi static initializer, và initializer có thể làm I/O, cấp phát hoặc ném lỗi. Nên giữ `<clinit>` gọn, tránh vòng phụ thuộc class initialization và hiểu rằng `ExceptionInInitializerError` là lỗi khởi tạo, không phải lỗi do `classDataAt` sai index.

Javadoc mô tả class data được chuẩn bị như thể có một private static final unnamed field được thiết lập từ đầu initializer. Đó là **mô hình ngữ nghĩa**; không được viết code giả định có field tên `CONFIG` hay `classData` mà reflection có thể tìm.

## 11. Thiết kế data: bất biến và schema rõ ràng

Một hidden class có **một object class data**, nên nếu cần nhiều giá trị, hãy gói bằng List/record:

~~~java
List<Object> data = List.of(
        "prefix:",
        Integer.valueOf(2),
        methodHandle);
~~~

Đây là snippet giả sử `methodHandle` đã được tạo an toàn. `List.of(...)` bất biến về cấu trúc và không cho phép phần tử `null`. Tuy nhiên, điều này **không biến từng item thành immutable**: một object mutable đặt bên trong List vẫn có thể thay đổi.

Javadoc cảnh báo thay đổi object được dùng làm class data sau khi class được liên kết có thể dẫn tới hành vi khó dự đoán, đặc biệt nếu dữ liệu được xem như constant hoặc được JIT tối ưu. Vì vậy:

1. Chọn immutable/effectively immutable data khi có thể.
2. Chuẩn hóa thứ tự và type item: `0 = String prefix`, `1 = Integer count`, v.v.
3. Bảo vệ original Lookup; tránh đưa nó vào API public tùy tiện.
4. Không dùng class data như shared mutable map thay cho state có đồng bộ rõ ràng.
5. Với dữ liệu cần update runtime, cân nhắc state object và concurrency contract riêng hoặc `MutableCallSite`/`VolatileCallSite` khi mục tiêu là đổi behavior.
6. Không log token hoặc secret gắn với class data. “Hidden” không có nghĩa dữ liệu là bí mật tuyệt đối.

## 12. Khi nào dùng class data thay vì static/instance field?

| Khía cạnh | Class data | Static field | Instance field |
| --- | --- | --- | --- |
| Gắn với | Hidden class identity | Class | Từng instance |
| Nhiều giá trị | Một object tổng hợp, ví dụ `List` | Nhiều fields | Nhiều fields |
| Đọc | Original Lookup + `classData`/`classDataAt` | Field access/VarHandle/reflection hợp lệ | Receiver + field access |
| Có tên field Java? | Không như một field khai báo bình thường | Có | Có |
| Quyền nestmate | Không tự mở class data cho mọi nestmate | Private field có thể được nestmates truy cập | Private field có thể được nestmates truy cập |
| Khởi tạo | Gắn khi định nghĩa hidden class | Thường qua `<clinit>` | Qua constructor/initializer |
| Dùng cho condy | Có, bootstrap `classData`/`classDataAt` | Không phải thay thế trực tiếp | Không phải thay thế trực tiếp |

Nếu ứng dụng chỉ có vài object với cấu hình đơn giản, **constructor injection + instance field** thường dễ đọc, dễ test và ít ràng buộc JVM hơn. Hidden class class data có giá trị khi chính **mã thực thi được sinh động** và bạn muốn dữ liệu liên kết với class đó.

## 13. Bảng lỗi theo từng giai đoạn

| Giai đoạn | Lỗi/hiện tượng | Nguyên nhân điển hình |
| --- | --- | --- |
| Định nghĩa bytes | `IllegalAccessException` | Host lookup không có full privilege |
| Định nghĩa bytes | `IllegalArgumentException` | Template bytes ở package khác hoặc class file type không phù hợp |
| Định nghĩa bytes | `ClassFormatError` | Mảng bytes không phải ClassFile hợp lệ |
| Định nghĩa bytes | `UnsupportedClassVersionError` | Bytecode version không được JVM chạy hỗ trợ |
| Định nghĩa/link | `VerifyError` / `LinkageError` | Invalid bytecode/stack map hoặc resolution lỗi |
| Định nghĩa | `NullPointerException` | Bytes hoặc đối số bắt buộc `null` |
| Đọc data | `IllegalArgumentException` | `name` không bằng `"_"` |
| Đọc data | `IllegalAccessException` | Lookup không có `ORIGINAL` |
| Đọc data | `ClassCastException` | Toàn bộ data hoặc item List không phù hợp với requested type |
| Đọc data | `IndexOutOfBoundsException` | `classDataAt` có `index` ngoài phạm vi |
| Đọc data | `NullPointerException` | `caller`/`type` null hoặc primitive unboxing cần item không null |
| Đọc data | Trả `null` | Lookup class không có class data |
| Gọi handle | `NoSuchMethodException` | `findStatic` sai method name/descriptor |
| Gọi handle | `WrongMethodTypeException` | `invokeExact` call-site type không bằng `MethodHandle.type()` |
| Tra hidden theo tên | `ClassNotFoundException` | Hidden class không có cơ chế tìm thông thường bằng `Class.forName` |
| Khởi tạo class | `ExceptionInInitializerError` | Logic `<clinit>` ném lỗi |
| Vòng đời | Không unload như mong đợi | Giữ strong references qua cache/loader hoặc dùng `STRONG` |

Nên tách **lỗi bytecode**, **lỗi access**, **lỗi schema data**, **lỗi method handle** và **lỗi initialization**. Nếu bắt mọi `Throwable` rồi trả `null`, bạn sẽ che mất nguyên nhân khiến class không được định nghĩa hoặc logic runtime sai.

## 14. Các nhầm lẫn thường gặp

### “Có `Class<?>` là đọc được class data?”

Không. `MethodHandles.classData` nhận `Lookup`, không nhận `Class<?>` tùy ý. Lookup phải có `ORIGINAL` và phải trỏ vào **đúng hidden class**. `publicLookup().in(hidden)` không tạo quyền này.

### “Có `PRIVATE` là đủ?”

Không. `Lookup.ORIGINAL` là mode riêng cần cho `classData` và `classDataAt`. Ví dụ `dropLookupMode(PRIVATE)` làm lookup mất điều kiện đọc. Các cơ chế `in(...)`/`privateLookupIn(...)` không phải cách cấp phát tùy ý original access.

### “`classDataAt` có thể lấy item từ mảng hay Map?”

Không theo hợp đồng API. Nó được định nghĩa cho class data là **`List`**. Với array/Map, gọi `classData` để lấy object rồi truy cập theo API của object đó (nếu policy của ứng dụng cho phép).

### “`initialize=false` ngăn static initializer mãi mãi?”

Không. Các thao tác đòi initialization như `classData`/`classDataAt` hoặc invocation thích hợp vẫn có thể kích hoạt `<clinit>`. Kết quả demo chỉ rõ thời điểm này.

### “NESTMATE làm class data có thể đọc từ host?”

Không. `NESTMATE` thay đổi nest membership/khả năng truy cập private members, **không thay thế lookup original**. Host trusted đọc được nhờ giữ returned `hiddenLookup`, chứ không vì ngẫu nhiên là nestmate.

### “Có thể gọi `Class.forName(hidden.getName())` rồi invoke?”

Không như với class Java thông thường. Giữ reference `Class<?>`/`Lookup`/`MethodHandle` được trả khi tạo hidden class.

### “Muốn một đối tượng classData cho mỗi request, cứ sửa List mỗi lần?”

Không nên. Dùng class data cho thông tin cấu hình cố định gắn với class identity. Với state thay đổi theo request, truyền argument qua handle hoặc thiết kế instance/state object thay vì mutate dữ liệu được coi là constant.

## 15. Checklist triển khai và test

- Bytecode đã được biên dịch/sinh đúng phiên bản Java, cùng package với lookup class.
- Host lookup có full privilege, không lấy từ `publicLookup()`.
- Data được chuẩn hóa, ưu tiên immutable, schema item type/index nhất quán.
- Class options `NESTMATE`/`STRONG` được chọn do yêu cầu thực, không theo thói quen.
- `initialize` được thiết kế để tránh side effects bất ngờ của `<clinit>`.
- Returned original Lookup được giữ an toàn; tránh trả nguyên capability cho code không tin cậy.
- Bên trong hidden class dùng `MethodHandles.lookup()` của chính nó nếu cần đọc data.
- Gọi `classData(...,"_",Type.class)` với đúng class/type; dùng `classDataAt` chỉ cho List.
- Gọi method của hidden class bằng `findStatic`/`findVirtual`/... theo đúng `MethodType`.
- Test tên sai, kiểu sai, index sai, reduced lookup, data absent, và khởi tạo trễ.
- Kiểm tra memory/class unloading nếu sinh nhiều hidden classes; không giữ cache vô hạn.
- Khi sinh condy thực, kiểm tra constant pool, bootstrap descriptor và type khi resolve thay vì giả định đoạn Java gọi `classData` đã tự sinh condy.

## 16. Tự kiểm tra

**1.** `defineHiddenClassWithClassData` trả gì?  
**Đáp án:** Một `MethodHandles.Lookup` original/full privilege trên hidden class mới; lấy `Class<?>` bằng `lookupClass()`.

**2.** `classData(hiddenLookup, "settings", List.class)` hợp lệ không?  
**Đáp án:** Không; `name` bắt buộc là `"_"` (hằng `ConstantDescs.DEFAULT_NAME`). Tên sai gây `IllegalArgumentException`.

**3.** Với `List.of("A", 3)`, làm sao lấy `Integer` ở index 1?  
**Đáp án:** `MethodHandles.classDataAt(hiddenLookup, "_", Integer.class, 1)`.

**4.** `initialize=false` có đảm bảo đọc class data không chạy `<clinit>`?  
**Đáp án:** Không. `classData`/`classDataAt` bảo đảm khởi tạo lookup class nếu cần.

**5.** Có `Class<?> hidden` và private reflection rồi có thể đọc tùy ý class data không?  
**Đáp án:** Không. API cần `Lookup.ORIGINAL` đúng hidden class, không chỉ quyền reflection.

**6.** `CONSTANT_Dynamic` và `invokedynamic` khác nhau điều gì?  
**Đáp án:** Condy liên kết một giá trị constant; invokedynamic liên kết một vị trí gọi thông qua CallSite. Cả hai có thể sử dụng bootstrap và MethodHandles.

**7.** Một hidden class tạo với `NESTMATE` có phải mọi nestmate đều được phép đọc class data?  
**Đáp án:** Không. Quyền `ORIGINAL` là ràng buộc riêng.

**8.** Vì sao không nên mutate class data dạng ArrayList sau linkage?  
**Đáp án:** Javadoc cảnh báo hành vi khó dự đoán nếu dữ liệu vốn được dùng như constant bị thay đổi; nên dùng immutable/effectively immutable data hoặc thiết kế state riêng.

**9.** Class data là List nhưng `classData(hiddenLookup,"_",String.class)` trả gì?  
**Đáp án:** Ném `ClassCastException` vì object toàn phần là List, không phải String.

**10.** Định nghĩa cùng template bytes hai lần có cho một class duy nhất không?  
**Đáp án:** Không. Mỗi lần định nghĩa thành công tạo một hidden class identity riêng, có dữ liệu gắn riêng.

## Tài liệu chuẩn

- [Java SE 17 — Lookup.defineHiddenClassWithClassData, defineHiddenClass và access](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — MethodHandles.classData và classDataAt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html)
- [Java SE 17 — Lookup.ClassOption NESTMATE và STRONG](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html)
- [Java SE 17 — MethodHandle, MethodType và invokeExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — Class.isHidden](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden())
- [JVMS SE 17 — CONSTANT_Dynamic_info](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10)
- [JVMS SE 17 — Dynamic Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371)
