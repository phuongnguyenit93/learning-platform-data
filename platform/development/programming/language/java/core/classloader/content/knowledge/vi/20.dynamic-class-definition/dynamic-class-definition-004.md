# Hidden class và giới hạn khám phá bằng tên trong Java

## 1. Vấn đề: tạo được lớp tại runtime nhưng không thể gọi lại bằng tên?

Một số thư viện Java cần **tạo lớp động** để thực thi code được biên dịch, triển khai lambda, proxy, bộ chuyển đổi dữ liệu hoặc một đoạn logic có vòng đời ngắn. Những lớp này không nhất thiết cần được **công bố bằng tên** cho tất cả code khác trong JVM. Nếu đăng ký mọi lớp sinh ra vào namespace nạp lớp thông thường, việc nạp lại nhiều bản cùng tên, giữ metadata hoặc quản lý bộ nhớ có thể trở nên khó khăn.

Từ **Java 15**, nền tảng Java có cơ chế **hidden class** (JEP 371). API chủ đạo là:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, false);
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

**Hidden class vẫn là một class thật do JVM tạo và liên kết (link), nhưng không thể được tìm lại bằng các API tra lớp dựa trên tên như `Class.forName(String)` hoặc `ClassLoader.loadClass(String)`.** Bởi vậy, “ẩn” trong tên gọi không có nghĩa không thể lấy `Class<?>` hoặc gọi method của nó; nó có nghĩa class đó **không tham gia cơ chế khám phá bằng binary name thông thường**.

Đây là điểm khác biệt của chủ đề **Định nghĩa lớp động**:

- Ordinary class thường có **binary name** để loader lookup có thể tìm lại.
- Hidden class có **runtime name mang hậu tố định danh**, nhưng **không có binary name** dùng được như nominal reference trong constant pool của class khác.
- JVM có thể đặt hidden class vào **cùng loader, runtime package và protection domain** với lookup class, nhưng vẫn **không đăng ký tên đó như một ordinary class có thể `loadClass`**.
- Với hidden class, code tạo nên giữ `MethodHandles.Lookup`, `Class<?>` hoặc `MethodHandle`/instance để sử dụng thay vì lưu chuỗi name và cố tìm lại.
- Hidden class được tạo và **linked ngay**, còn việc **initialized** hay không phụ thuộc cờ `initialize` hoặc lần active use sau đó.
- Mặc định hidden class có quan hệ “weak” với defining loader để có thể được unload độc lập khi không còn tham chiếu cần thiết; `STRONG` thay đổi quy tắc giữ lớp.

### Mục tiêu của bài

Bạn sẽ hiểu khái niệm, API `defineHiddenClass`, lý do `getName()` không giúp tra lại class, khác biệt giữa hidden class và ordinary dynamic class, cách định nghĩa một hidden class từ bytecode Java 17, cách dùng method handle, các tùy chọn `NESTMATE`/`STRONG`, vòng đời, tính an toàn và giới hạn chẩn đoán.

## 2. Hai cách định nghĩa lớp động: ordinary và hidden

### 2.1. Ordinary class qua ClassLoader

Một loader tùy chỉnh có thể tạo ordinary class từ bytes bằng protected API:

~~~java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length);
~~~

Lời gọi thật cần nằm **trong subclass của `ClassLoader`** có bytecode hợp lệ, đúng namespace và các điều kiện JVM. Với ordinary class:

- Class được định nghĩa với **binary name**, ví dụ `demo.dynamic.Task`.
- Việc load theo `ClassLoader.loadClass("demo.dynamic.Task")` có thể trả class đã được loader này hoặc parent định nghĩa, tùy loader policy.
- Một loader không thể định nghĩa **lại** class khác cùng tên đã được ghi nhận cho loader đó: cố define trùng có thể gây `LinkageError`.
- Ordinary class có quan hệ tồn tại mạnh với defining loader: class có thể được unload khi đủ điều kiện JVM và loader không còn reachable.

### 2.2. Hidden class qua MethodHandles.Lookup

Phương thức:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

Khác biệt:

- Lời gọi nhận một class-file representation, **không** gọi `ClassLoader.defineClass` thông thường.
- Hidden class có **cùng defining loader**, **runtime package** và **protection domain** với **lookup class**.
- Lookup phải có **full privilege access** và bytecode class cần thuộc **cùng package** với lookup class. Không dùng một lookup ngẫu nhiên để inject class vào package tùy ý.
- Lớp được **tạo và liên kết**; cờ `initialize=true` yêu cầu initialization ngay sau đó, còn `false` thì không yêu cầu initializer chạy ngay.
- Phương thức trả **`Lookup` của chính hidden class**, không trực tiếp trả `Class<?>`. Muốn có class object dùng `hiddenLookup.lookupClass()`.
- Kết quả không được khai báo làm class mang binary name có thể khám phá bằng `loadClass`/`Class.forName`.
- Khi gọi `defineHiddenClass` nhiều lần với cùng bytes, bạn có thể thu được **nhiều hidden classes riêng**; không xảy ra cùng loại duplicate-definition theo binary name như ordinary class.

Bảng đối chiếu:

| Tiêu chí | Ordinary dynamic class | Hidden class |
|---|---|---|
| API điển hình | `ClassLoader.defineClass` / `Lookup.defineClass` | `Lookup.defineHiddenClass` |
| Có binary name dùng cho symbolic lookup | **Có** | **Không** |
| Có object `Class<?>` | Có | **Có** |
| `Class.isHidden()` | `false` | `true` |
| Gọi `Class.forName(name)` để tìm đúng class | Có thể, nếu loader thấy ordinary class | **Không thể** tìm hidden class theo name |
| `ClassLoader.loadClass(name)` | Có thể trả ordinary class phù hợp | Không tìm hidden class |
| Được gán defining loader | Có | Có, dựa trên lookup class |
| Có thể khởi tạo đối tượng/gọi method | Có | Có qua handle/`Class<?>` thích hợp |
| Có thể tạo nhiều class từ cùng bytes trong cùng loader | Tên trùng thường bị cấm | Có thể tạo nhiều hidden class độc lập |
| Unloading | Gắn với lifetime của defining loader | Mặc định có thể unload độc lập; `STRONG` thay đổi |
| Dùng làm loại được nhắc từ constant pool của class khác | Có thể khi accessible | Không thể tham chiếu hidden class bằng nominal type name |

**Không nhầm “hidden” với “private”.** `private` là modifier về quyền truy cập Java, còn `hidden class` là loại class đặc biệt về **cách định nghĩa và khả năng được tham chiếu bằng tên**. Hidden class không biến toàn bộ method của nó thành private, cũng không tự cho caller quyền đọc private member bất kỳ.

## 3. Hidden class có tên, nhưng không có binary name

### 3.1. Tại sao `getName()` vẫn trả String?

Một hidden class có thể tạo từ bytecode ban đầu mang tên `demo.HiddenTask`. JVM gắn hậu tố độc nhất vào runtime name, ví dụ **hình thức minh họa**:

~~~text
demo.HiddenTask/0x00007fxxxxxxxxxx
~~~

Hậu tố thực tế thay đổi theo phiên bản JVM/lượt chạy. Không được hardcode, serialize rồi coi nó là một tên có thể tra lại.

Các API liên quan:

~~~java
Class<?> hidden = hiddenLookup.lookupClass();

System.out.println(hidden.isHidden());          // true
System.out.println(hidden.getName());           // chứa runtime suffix
System.out.println(hidden.descriptorString());  // có dạng riêng cho hidden type
System.out.println(hidden.describeConstable()); // Optional.empty()
~~~

**Điểm dễ nhầm:** `Class.getName()` trả một **chuỗi mô tả runtime class**, không phải lời hứa mọi chuỗi trả về đều là **binary name hợp lệ** để dùng với `Class.forName`. Với hidden class, chuỗi `getName()` chứa dấu `/` ngăn original name và suffix, nên không phải binary name thông thường.

`Class.descriptorString()` của hidden class cũng có dạng đặc biệt chứa suffix, **không phải nominal field descriptor** có thể ghi trong constant pool của class khác. `Class.describeConstable()` trả `Optional.empty()` vì hidden class không có mô tả danh nghĩa để được resolve bằng tên trong constant pool.

### 3.2. Những API tìm bằng tên không tìm hidden class

Theo Javadoc của `Lookup.defineHiddenClass`, hidden class không được khám phá bằng:

- `Class.forName(String)`, cũng như `Class.forName(String, boolean, ClassLoader)`.
- `ClassLoader.loadClass(String)` / `loadClass(String, boolean)`.
- `MethodHandles.Lookup.findClass(String)`.

Lý do **không phải** loader không có reference đến hidden class, hay class chưa initialized. JVM cố ý **không đặt hidden class trong bảng tìm ordinary classes bằng binary name**.

Sơ đồ:

~~~text
bytes từ demo/HiddenTask.class
   |
   v
hostLookup.defineHiddenClass(bytes, false)
   |
   +--> hiddenLookup.lookupClass() -> Class<?> (isHidden=true)
   |         |
   |         +--> findStatic / findVirtual / findConstructor
   |         +--> reflection khi có Class<?> và quyền phù hợp
   |
   +--> Class.forName(hidden.getName()) -----------> KHÔNG TÌM THẤY
   +--> hostLoader.loadClass(hidden.getName()) ----> KHÔNG TÌM THẤY
~~~

**Không nên dùng `ClassNotFoundException` làm bằng chứng hidden class chưa từng tồn tại.** Class có thể đã được tạo, được linked và đã được một `MethodHandle` gọi thành công — chỉ là không có đường tra từ tên.

### 3.3. Cũng không phải superclass/type trong chữ ký danh nghĩa của class khác

Vì hidden class không có binary name có thể ghi vào constant pool, class khác **không thể nhắc trực tiếp hidden class** bằng symbolic reference như một superclass, field type, parameter type hoặc return type. Đây là giới hạn cố ý của hidden class, không phải lỗi Java reflection.

Code có `Object obj` trỏ đến instance của hidden class vẫn hợp lệ. Code cũng có thể dùng **interface/ordinary type** làm contract, miễn bytecode và access rules cho phép. Điều bị giới hạn là **tham chiếu danh nghĩa đến hidden type**, chứ không phải mọi cách trao đổi object.

### 3.4. Không nhầm với anonymous class, local class và lambda

| Loại | Có thể là hidden class? | Khám phá bằng tên |
|---|---|---|
| Nested class biên dịch thông thường `Outer$Inner` | Không chỉ vì nó nested | Ordinary binary name thường dùng `$` |
| Anonymous/local class do `javac` tạo | Thường là ordinary class trong bytecode | Có binary name theo quy tắc compiler; tên không nên coi là API ổn định |
| Lambda implementation | JVM/compiler có thể dùng hidden classes như chi tiết triển khai | Không nên phụ thuộc tên/số lượng lớp phát sinh |
| Hidden class do `defineHiddenClass` | **Có** theo định nghĩa | Không thể tra lại qua `Class.forName`/`loadClass` |

Không lấy cách một bản JDK hiện thực lambda làm hợp đồng bảo đảm mọi Java runtime/phiên bản dùng đúng cùng tên hay class shape. `Hidden class` là cơ chế JVM/API, không phải đồng nghĩa mọi nested/anonymous types đều hidden.

## 4. Điều kiện để tạo hidden class đúng

### 4.1. Dùng Lookup có đủ đặc quyền

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup generated =
        lookup.defineHiddenClass(bytes, false);
~~~

Nếu gọi `MethodHandles.lookup()` từ một method của class bình thường, kết quả thường có full privilege access với chính lookup class đó. Nhưng một `publicLookup()` không có toàn bộ quyền tương ứng để dùng `defineHiddenClass`.

Nếu `Lookup` thiếu full privilege access, phương thức có thể ném **`IllegalAccessException`**. Việc cố dùng `privateLookupIn` qua module boundaries cũng chịu kiểm tra `opens`/access và không tự cấp đặc quyền không được phép.

### 4.2. Bytecode phải thuộc cùng package với lookup class

Nếu lookup class là `demo.HiddenHost`, class bytes đầu vào phải khai báo class trong package `demo` (ví dụ `demo.HiddenTask`). Đừng truyền classfile mang tên `other.pkg.Task` và mong `defineHiddenClass` tạo hidden class ở package khác: API sẽ từ chối theo điều kiện package.

Hidden class nhận:

- **Defining ClassLoader** của lookup class.
- **Runtime package** phù hợp lookup class.
- **ProtectionDomain** của lookup class.
- Runtime **module** tương ứng; nó không tự tạo named module mới.

Tất cả vẫn phải tuân theo kiểm tra class-file format, package/access/module và các quy tắc verification/linking.

### 4.3. Class bytes thật, không phải tên/đường dẫn

`defineHiddenClass` nhận **`byte[]` biểu diễn một class file**, không nhận:

~~~text
"demo.HiddenTask"
"src/demo/HiddenTask.java"
"demo/HiddenTask.class"
~~~

Các chuỗi trên là tên/path, không phải nội dung classfile. Bạn có thể đọc từ file đã biên dịch hoặc tạo bytes bằng bytecode generator phù hợp. Khi tự sinh bytecode, phải bảo đảm **classfile version**, format và các constant pool entries hợp lệ.

### 4.4. Link và initialize là hai thời điểm khác nhau

Hai lời gọi:

~~~java
lookup.defineHiddenClass(bytes, false);
lookup.defineHiddenClass(bytes, true);
~~~

đều **tạo và link** hidden classes (hai definition riêng nếu gọi hai lần). Cờ boolean:

- `false`: không yêu cầu chạy `<clinit>` ngay. Hidden class sẽ initialize khi có active use sau đó.
- `true`: JVM initialize hidden class sau khi link, theo hợp đồng phương thức.

Phân biệt với `Class.forName(Module, String)` vốn có quy tắc **không tự link hoặc initialize** trong overload theo module. Đừng suy từ một API sang mọi cách định nghĩa lớp động.

## 5. Ví dụ Java 17+ độc lập: định nghĩa được nhưng tra theo tên thất bại

Thực hành được thiết kế để **loại hoàn toàn class template khỏi runtime application classpath**. `HiddenHost` sẽ đọc bytes của `HiddenTask.class` như dữ liệu, gọi `defineHiddenClass`, giữ kết quả và gọi method bằng `MethodHandle`.

### 5.1. Cây thư mục

~~~text
demo/
  src/
    template/
      demo/
        HiddenTask.java
    app/
      demo/
        HiddenHost.java
  build/
    template/
      demo/
        HiddenTask.class
    app/
      demo/
        HiddenHost.class
~~~

**Quy tắc để demo chính xác:** lệnh `java` chỉ dùng `-cp build/app`. Không thêm `build/template` vào classpath; nếu có, `Class.forName("demo.HiddenTask")` có thể tìm được **ordinary template class**, gây hiểu nhầm rằng nó đã tìm thấy hidden class.

### 5.2. Tệp `src/template/demo/HiddenTask.java`

~~~java
package demo;

class HiddenTask {
    static {
        System.out.println("TASK_INITIALIZED");
    }

    static String message() {
        return "HELLO_HIDDEN";
    }
}
~~~

Lớp template là package-private. `static {}` giúp quan sát thời điểm initialization; `message()` trả kết quả dễ kiểm tra.

Dù source ở một cây khác, package vẫn là `demo` để thỏa điều kiện cùng package với lookup class của `HiddenHost`.

### 5.3. Tệp `src/app/demo/HiddenHost.java`

~~~java
package demo;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public final class HiddenHost {
    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/template/demo/HiddenTask.class"));
        MethodHandles.Lookup hostLookup = MethodHandles.lookup();

        MethodHandles.Lookup hiddenLookup =
                hostLookup.defineHiddenClass(bytes, false);
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println("hidden=" + hidden.isHidden());
        System.out.println("sameLoader="
                + (hidden.getClassLoader()
                    == HiddenHost.class.getClassLoader()));
        System.out.println("samePackage="
                + hidden.getPackageName().equals(
                    HiddenHost.class.getPackageName()));
        System.out.println("nameHasSlash="
                + hidden.getName().contains("/"));
        System.out.println("descriptorHasSlash="
                + hidden.descriptorString().contains("/"));
        System.out.println("noNominalDescriptor="
                + hidden.describeConstable().isEmpty());

        try {
            Class.forName(hidden.getName());
            System.out.println("forNameFound=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("forNameFound=false");
        }

        try {
            HiddenHost.class.getClassLoader().loadClass(hidden.getName());
            System.out.println("loadClassFound=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("loadClassFound=false");
        }

        Class<?> another =
                hostLookup.defineHiddenClass(bytes, false).lookupClass();
        System.out.println("twoDefinitionsDistinct="
                + (another != hidden));

        MethodHandle mh = hiddenLookup.findStatic(
                hidden, "message", MethodType.methodType(String.class));

        System.out.println("beforeInvoke");
        String value = (String) mh.invokeExact();
        System.out.println("result=" + value);
    }
}
~~~

**Vì sao có `throws Throwable`?** `MethodHandle.invokeExact` có thể ném `Throwable` theo signature. Việc khai báo ở `main` nhằm giữ demo rõ, không phải khuyến nghị mọi application entry point production đều `throws Throwable`.

### 5.4. Biên dịch/chạy trên Linux và macOS

Đứng tại thư mục `demo`:

~~~sh
mkdir -p build/template build/app

javac --release 17 -d build/template \
    src/template/demo/HiddenTask.java

javac --release 17 -d build/app \
    src/app/demo/HiddenHost.java

java -cp build/app demo.HiddenHost
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/template, build/app | Out-Null
javac --release 17 -d build/template src/template/demo/HiddenTask.java
javac --release 17 -d build/app src/app/demo/HiddenHost.java
java -cp build/app demo.HiddenHost
~~~

Không dùng cùng một output folder cho template và app: hai cây biên dịch khác nhau giúp chứng minh **ordinary class không xuất hiện trên runtime classpath**.

### 5.5. Stdout chính xác đã kiểm chứng

~~~text
hidden=true
sameLoader=true
samePackage=true
nameHasSlash=true
descriptorHasSlash=true
noNominalDescriptor=true
forNameFound=false
loadClassFound=false
twoDefinitionsDistinct=true
beforeInvoke
TASK_INITIALIZED
result=HELLO_HIDDEN
~~~

Đây là stdout của chương trình được biên dịch với `javac --release 17` và chạy trên một JDK có hỗ trợ Java 17.

### 5.6. Ý nghĩa từng kết quả

| Output | Diễn giải |
|---|---|
| `hidden=true` | `Class.isHidden()` nhận diện class do `defineHiddenClass` tạo |
| `sameLoader=true` | Hidden class gắn với defining loader của `HiddenHost` |
| `samePackage=true` | Hidden class thuộc package `demo` của lookup class |
| `nameHasSlash=true` | `getName()` có hậu tố runtime, **không phải binary name** |
| `descriptorHasSlash=true` | Descriptor của hidden class có dấu phân tách đặc biệt, không dùng như nominal descriptor |
| `noNominalDescriptor=true` | `describeConstable()` trống, không có nominal constant description |
| `forNameFound=false` | Không thể tìm lại hidden class bằng `Class.forName(hidden.getName())` |
| `loadClassFound=false` | `ClassLoader.loadClass(hidden.getName())` cũng không tìm được nó |
| `twoDefinitionsDistinct=true` | Cùng byte array tạo hai hidden classes **khác identity** |
| `beforeInvoke` | Mốc thời gian sau create/link với `initialize=false` |
| `TASK_INITIALIZED` | Method handle invoke static method đã tạo active use, kích hoạt initialization |
| `result=HELLO_HIDDEN` | Hidden class vẫn thực thi code bình thường khi có handle phù hợp |

**Điều không nên suy luận:** `forNameFound=false` không có nghĩa `HiddenTask.class` bytes không được đọc hoặc class chưa linked. Chúng ta đã có `Class<?>`, tìm được method handle và chạy method.

### 5.7. Tại sao `Class.forName("demo.HiddenTask")` có thể gây hiểu sai?

Nếu bạn vô tình để `build/template` trong application classpath:

~~~sh
java -cp "build/app:build/template" demo.HiddenHost
~~~

trên Linux/macOS (Windows dùng `;`), JVM có thể nạp **ordinary class** `demo.HiddenTask` bằng tên. Tuy nhiên ordinary class đó **khác** hidden class được `defineHiddenClass` tạo từ cùng bytes. Đừng dùng phép thử `Class.forName("demo.HiddenTask")` để khẳng định hidden class đã trở nên khám phá được.

Phép thử đúng nhất là sử dụng chính `hidden.getName()` rồi chứng minh API tra tên thông thường vẫn thất bại; hoặc so trực tiếp `ordinaryClass != hiddenClass` nếu cả hai tồn tại.

### 5.8. Các biến thể để tự kiểm chứng

**Biến thể A — `initialize=true`:** thay `defineHiddenClass(bytes, false)` đầu tiên thành `defineHiddenClass(bytes, true)`. Dòng `TASK_INITIALIZED` xuất hiện trong lời gọi define, **trước** chuỗi output `hidden=true`; sau đó invocation không initialize lại class.

**Biến thể B — Không invoke method handle:** bỏ dòng `mh.invokeExact()`. Với `initialize=false`, nếu không có active use khác, `TASK_INITIALIZED` không xuất hiện trong demo.

**Biến thể C — Thêm nhiều lượt define:** tạo thêm nhiều hidden classes từ cùng bytes, so `Class<?>` identities. Chúng độc lập ngay cả khi cùng lookup class, original classfile name và defining loader.

**Biến thể D — Sai package:** biên dịch template thuộc `foreign.HiddenTask` nhưng giữ `HiddenHost` ở `demo`. `defineHiddenClass` sẽ từ chối input không cùng package; không dùng tên động để đi vòng điều kiện access.

**Biến thể E — Không có full privilege lookup:** thử `MethodHandles.publicLookup().defineHiddenClass(bytes, false)`. Đây là ví dụ về lookup thiếu đặc quyền, dự kiến thất bại bằng `IllegalAccessException` theo hợp đồng API.

## 6. Các tùy chọn ClassOption: NESTMATE và STRONG

API nhận varargs của enum `MethodHandles.Lookup.ClassOption`:

~~~java
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.NESTMATE;
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.STRONG;

MethodHandles.Lookup hiddenNestmate =
        MethodHandles.lookup().defineHiddenClass(bytes, false, NESTMATE);
MethodHandles.Lookup hiddenStrong =
        MethodHandles.lookup().defineHiddenClass(bytes, false, STRONG);
~~~

Đây là **snippet minh họa trong class/method phù hợp**, cần `bytes` có sẵn và điều kiện access/package hợp lệ. Hai lượt define tạo hai hidden classes riêng, không biến class đầu thành nestmate/strong sau khi tạo.

### 6.1. `NESTMATE`: được đưa vào nest của lookup class

Java nestmates là các class/interface cùng một **nest** được phép truy cập private members theo quy tắc JVM.

Nếu truyền `NESTMATE`, hidden class được thêm vào nest của lookup class. Vì vậy hidden class có thể truy cập private members của các class/interface cùng nest **theo access rules của nestmate**.

Nếu **không** chọn `NESTMATE`, hidden class mặc định có nest của riêng nó dù cùng package/loader. Do đó:

~~~text
Same package + same defining loader
    ≠ tự động được truy cập private member của HiddenHost.

NESTMATE
    => hidden class tham gia nest phù hợp để áp dụng nestmate private access.
~~~

Đừng hiểu `NESTMATE` cho phép mở tùy ý private members của module/lớp khác. Nest membership và lookup privileges vẫn bị kiểm tra.

### 6.2. `STRONG`: liên kết vòng đời mạnh với defining loader

Thông thường ordinary class giữ quan hệ mạnh với defining loader; class chỉ được unload khi loader có thể bị thu gom theo điều kiện JVM.

Hidden class **mặc định** có thể được unload ngay cả khi defining loader vẫn reachable, **nếu không còn tham chiếu giữ hidden class đó sống**. Lý do: các framework có thể tạo nhiều lớp tạm trong một loader sống lâu.

Nếu chọn `STRONG`:

- Hidden class được gắn quan hệ mạnh với defining loader **giống ordinary class**.
- Nó thường không được unload độc lập khi loader vẫn reachable.
- Điều này hữu ích với hidden class cần cùng vòng đời với lớp/loader host, nhưng có thể làm **metadata retention** cao hơn nếu tạo rất nhiều definitions.
- Chọn lúc define, không thể đổi chế độ sau khi đã tạo class.

**Không có bảo đảm GC sẽ unload một hidden class ngay khi bạn bỏ `Class<?>` reference.** Cơ chế class unloading phụ thuộc reachability, handles, instances, threads, JVM và các tham chiếu khác. `STRONG` điều chỉnh khả năng unload chứ không phải là lệnh trực tiếp gọi GC.

### 6.3. Kết hợp options

~~~java
MethodHandles.Lookup lk = MethodHandles.lookup().defineHiddenClass(
        bytes, false, NESTMATE, STRONG);
~~~

Có thể kết hợp để hidden class vừa tham gia nest của lookup class, vừa có strong relationship với loader. Chỉ dùng khi cần đúng hai thuộc tính đó; không bật mặc định chỉ vì muốn “khỏi lỗi không tìm thấy theo tên” — `STRONG` và `NESTMATE` **không** làm hidden class trở thành ordinary class khám phá được.

## 7. Sử dụng hidden class mà không cần tên

### 7.1. Giữ `Lookup` do API trả về

Đây là con đường thường rõ nhất:

~~~java
MethodHandles.Lookup hiddenLookup =
        hostLookup.defineHiddenClass(bytes, false);
Class<?> hiddenClass = hiddenLookup.lookupClass();

MethodHandle run = hiddenLookup.findStatic(
        hiddenClass, "message", MethodType.methodType(String.class));
String value = (String) run.invokeExact();
~~~

Đây là snippet cần nằm trong method có xử lý checked exceptions và `Throwable` phù hợp. `hiddenLookup` là lookup trên chính hidden class, nên có khả năng thực hiện các `find...` operations theo quyền của lookup đó.

Không lập “registry bằng `getName()` rồi `Class.forName`” để truy xuất hidden class. Nếu framework cần registry, lưu **tham chiếu class/lookup/method handle hoặc object** với lifecycle được quản lý. Chú ý rằng giữ tham chiếu mạnh cũng ngăn class được unload theo kỳ vọng.

### 7.2. Truyền object qua ordinary interface

Hidden class có thể triển khai một interface thông thường được host biết. Host nhận và dùng object qua interface đó mà **không cần biết tên hidden class**.

~~~java
public interface Operation {
    String run(String input);
}
~~~

Snippet trên là khai báo interface minh họa. Để triển khai bằng hidden class phải có bytecode thỏa contract, lookup/module/package/access thích hợp và logic khởi tạo instance. Đây là hướng phù hợp cho generated adapters hoặc lambda-like runtime objects.

Khi dùng module/classloader boundaries, interface contract vẫn cần giữ đúng runtime type identity; hidden class không loại bỏ các quy tắc định danh kiểu của JVM.

### 7.3. Reflection vẫn có thể dùng nếu có Class object

`Class.isHidden() == true` không có nghĩa Java reflection bị cấm hoàn toàn. Nếu code đang giữ `Class<?> hidden`, nó có thể gọi:

~~~java
java.lang.reflect.Method method = hidden.getDeclaredMethod("message");
~~~

và dùng reflection khi Java/JPMS access checks cho phép. Tuy nhiên `getDeclaredMethod` lấy metadata khác với khả năng setAccessible/invoke. Việc cố tìm `hidden` từ một string name bằng `Class.forName` mới là điều không được hỗ trợ.

Nói ngắn: **hidden class là non-discoverable by name, không phải invisible to all reflection**.

### 7.4. Class data khi cần state dành riêng cho class

Java còn có:

~~~java
MethodHandles.Lookup defineHiddenClassWithClassData(
        byte[] bytes, Object classData, boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
~~~

API này tạo hidden class kèm class data, hữu ích cho frameworks cần truyền metadata/state để bytecode sinh ra truy cập theo cơ chế method handles/class data. Nó khác với việc gắn tên/JAR path cho class, và không biến hidden class thành ordinary class. Cần đọc hợp đồng của `MethodHandles.classData`/`classDataAt` trước khi thiết kế, nhất là khi state mutable.

Phạm vi bài chính là **khám phá bằng tên**, nên API class data được nhắc như một khả năng mở rộng chứ không thay ví dụ cơ bản.

## 8. Vòng đời, memory và cách tổ chức framework

### 8.1. Tại sao JVM thiết kế hidden class có khả năng unload riêng?

Các framework có thể sinh rất nhiều implementations rất nhỏ: adapters cho từng kiểu call site, serializer/deserializer theo schema, proxies hoặc lambda implementations. Nếu mỗi class phải tồn tại tới khi application ClassLoader dài hạn được thu hồi, metaspace có thể giữ nhiều class không còn dùng nữa.

Với hidden class mặc định, JVM được phép unload khi không còn reference cần thiết dù loader vẫn sống. Đây là lợi thế trong môi trường nạp lớp động quy mô lớn. Nhưng nếu framework cache mọi `Lookup`/`Class<?>` trong static map vĩnh viễn, lợi thế ấy gần như mất đi.

### 8.2. Những tham chiếu giữ class sống

Một hidden class có thể vẫn reachable qua:

- `Class<?>` object hoặc `MethodHandles.Lookup` giữ reference.
- `MethodHandle`, `MethodType`, `CallSite` và các cấu trúc liên quan.
- Instance của hidden class.
- Callback/caches/static registries trong framework.
- Thread đang thực thi code hoặc đang giữ object liên quan.
- Các internal references còn được JVM duy trì theo hoạt động runtime.

**Đừng cố dự đoán thời điểm unload chỉ dựa vào lời gọi `System.gc()`**. Không có output cố định đáng tin cho phép thử unload bằng GC ở một chương trình nhỏ.

### 8.3. Hidden class không thay thế custom ClassLoader trong mọi bài toán

Hidden class phù hợp với implementation **nội bộ**, cần giữ handle và không cần external symbolic discoverability. Nếu bạn muốn:

- Plugin class được nạp từ JAR bằng binary name.
- Framework tìm class từ classpath/service descriptor.
- Class được export, tham chiếu trong bytecode của class khác như type thông thường.
- Quản lý nhiều module/plugin boundaries với đầy đủ classpath/module path.

thì ordinary class, URLClassLoader, ServiceLoader hoặc module layer có thể thích hợp hơn. Hidden class không thay thế SPI/plugin architecture tiêu chuẩn chỉ bằng đổi API define.

### 8.4. Bảo mật và mã không tin cậy

`defineHiddenClass` yêu cầu `Lookup` đủ quyền và ràng buộc package/module. Tuy nhiên, “hidden” **không có nghĩa sandbox** cho bytecode không tin cậy. Code vẫn có thể chạy trong process với quyền của ứng dụng, tạo tác dụng phụ khi initialize hoặc invoke, dùng CPU/memory, gọi API được phép.

Nếu bytecode đến từ nguồn bên ngoài, phải xác thực/protect inputs, giới hạn artifact provenance và cân nhắc process isolation; không giao privileged lookup tùy ý cho plugin không tin cậy.

## 9. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Hướng kiểm tra |
|---|---|---|
| `Class.forName(hidden.getName())` ném `ClassNotFoundException` | **Đúng bản chất hidden class**: không discoverable by name | Giữ `Lookup`/`Class<?>`/MethodHandle, đừng cố tra lại |
| `ClassLoader.loadClass(hidden.getName())` thất bại | Hidden class không có binary name để loader lookup | Không coi việc có loader giống nhau là đủ |
| `defineHiddenClass` ném `IllegalAccessException` | Lookup không có full privilege access | Kiểm tra `lookupModes`, nguồn tạo `Lookup`, JPMS permissions |
| `defineHiddenClass` ném `IllegalArgumentException` | Bytecode class không cùng package hoặc argument/option không hợp lệ | Kiểm tra internal classfile name và lookup package |
| `ClassFormatError` hoặc `VerifyError` | Bytecode classfile không hợp lệ hoặc sai verify rules | Kiểm tra bytes, constant pool, classfile version và generator |
| `UnsupportedClassVersionError` | Bytes được biên dịch cho JVM mới hơn runtime | `java -version`, `javac --release` |
| `LinkageError` khi liên kết | Dependency/loading constraints/verification linkage | Ghi cause; không mặc định do “tên hidden trùng” |
| `ExceptionInInitializerError` khi `initialize=true` hoặc active use | `<clinit>` thực thi và thất bại | Kiểm tra static initializer và stack trace gốc |
| Method handle lookup bị `NoSuchMethodException` | Method name/signature không khớp | Kiểm tra `MethodType` và declared method |
| Method handle access bị `IllegalAccessException` | Lookup không có quyền tương ứng | Dùng lookup hợp lệ, không tự mở quyền |
| `ClassCastException` khi truyền qua boundary | Sai interface identity/loader hoặc cast logic | So `Class<?>` của API chung |
| Metaspace/class retention tăng | Cache vô hạn, `STRONG` không phù hợp hoặc objects giữ class | Review references, handles và lifecycle |
| Reflection thấy class nhưng `Class.forName` vẫn fail | Reflection có sẵn `Class<?>`; name lookup không thể tìm hidden | Đây là hai cơ chế khác nhau |
| Code phụ thuộc suffix `/0x...` bị hỏng khi đổi JDK | Suffix runtime không phải format persistence chuẩn | Không dùng suffix làm stable identifier |

### 9.1. Phân biệt three layers of failure

~~~text
(1) File/bytes:
    source .java -> compiled .class byte[]
    có thể IOException / ClassFormatError / UnsupportedClassVersionError

(2) Define/link:
    MethodHandles.Lookup.defineHiddenClass(...)
    có thể IllegalAccessException / IllegalArgumentException / LinkageError

(3) Sử dụng:
    Lookup/Class<?>/MethodHandle/instance
    có thể NoSuchMethodException / IllegalAccessException
    hoặc lỗi khi initialize/invoke
~~~

**Không tạo thêm bước bắt buộc `Class.forName` ở giữa (2) và (3).** Hidden class được trả trực tiếp bằng lookup — name-based lookup không phải cách để lấy reference.

### 9.2. Cách ghi log phù hợp

Có thể ghi:

~~~java
System.out.println("hidden=" + type.isHidden());
System.out.println("runtimeName=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

Đây là snippet minh họa, cần `type` có sẵn. Log về runtime name hữu ích để chẩn đoán nhưng không phải identifier bền vững. Khi cần chứng minh tính tương thích hoặc danh tính runtime, so `Class<?>` reference, defining loader, module và thông tin nguồn bytecode tin cậy.

## 10. Những ngộ nhận cần tránh

1. **“Hidden class không có `Class<?>` object.”** Sai: `hiddenLookup.lookupClass()` trả về class.
2. **“Vì có `getName()` nên có thể `Class.forName`.”** Sai: runtime name không phải binary name.
3. **“Cứ thêm classfile vào classpath thì `Class.forName(hidden.getName())` sẽ tìm được hidden class.”** Sai: nếu có ordinary class template, nó là class khác.
4. **“Hidden class không được khởi tạo/chạy code.”** Sai: có thể initialize và invoke bình thường.
5. **“`initialize=false` nghĩa là không link class.”** Sai: defineHiddenClass tạo và link; chỉ hoãn initialization.
6. **“Hidden class có thể dùng trực tiếp làm superclass được class khác tham chiếu bằng tên.”** Sai: không có binary name cho nominal symbolic reference.
7. **“Cùng defining loader nghĩa là cùng class identity.”** Sai: hidden classes được tạo riêng bằng cùng bytes vẫn là các `Class<?>` riêng.
8. **“Nếu không chọn NESTMATE thì hidden class vẫn tự truy cập private fields của host.”** Sai: cùng package không đủ quyền private.
9. **“Chọn STRONG sẽ làm `Class.forName` tìm hidden class.”** Sai: STRONG ảnh hưởng lifecycle, không ảnh hưởng discoverability.
10. **“Hidden class luôn bị unload ngay khi code thoát khỏi method.”** Sai: các references và GC quyết định.
11. **“Hidden class có thể được dùng thay mọi plugin class bằng tên.”** Sai: plugin discovery/SPI có contract riêng.
12. **“`isHidden()` sẽ true với mọi anonymous/local/nested class.”** Sai: những classes thường là ordinary types; phải xét API JVM tạo class.
13. **“Hidden class là biện pháp bảo mật code untrusted.”** Sai: lookup privilege và name hiding không tạo security sandbox.
14. **“Đọc một chuỗi suffix duy nhất là cách lưu identity lâu dài.”** Sai: runtime name không có ngữ nghĩa persistence ổn định.
15. **“Reflection tuyệt đối không thể xem hidden class.”** Sai nếu code đang có `Class<?>` và đủ quyền.
16. **“`Class.forName(Module, name)` có thể tìm hidden class vì đã truyền đúng module.”** Sai: named-module lookup không phá giới hạn non-discoverable by name của hidden class.

## 11. Câu hỏi và bài tập tự kiểm tra

1. `Lookup.defineHiddenClass` được đưa vào Java từ phiên bản nào? Nó trả `Lookup` hay `Class<?>`?
2. Tại sao `Class.getName()` của hidden class có giá trị nhưng `Class.forName` vẫn không tìm được?
3. Sự khác nhau giữa **runtime name** và **binary name** trong trường hợp hidden class là gì?
4. `Class.isHidden()` trả gì cho ordinary class và hidden class?
5. Tại sao `Class.describeConstable()` của hidden class là `Optional.empty()`?
6. `Class.descriptorString()` của hidden class có thể dùng làm nominal descriptor được ghi vào constant pool của class khác không?
7. Hidden class có defining ClassLoader không? Nó lấy loader và runtime package từ đâu?
8. Vì sao bytecode đưa vào `defineHiddenClass` phải khai báo cùng package với lookup class?
9. `MethodHandles.publicLookup()` có đủ quyền định nghĩa hidden class không?
10. `defineHiddenClass(bytes, false)` có tự link class không? Nó có chạy `<clinit>` ngay không?
11. Tại sao dòng `TASK_INITIALIZED` trong demo xuất hiện sau `beforeInvoke`?
12. Vì sao `Class.forName("demo.HiddenTask")` đôi lúc vẫn có thể thành công nếu vô tình để template trên app classpath, nhưng không chứng minh hidden class được tìm?
13. Hai lần defineHiddenClass với cùng bytes có tạo cùng object `Class<?>` không?
14. `NESTMATE` làm thay đổi điều gì về quyền private access?
15. `STRONG` ảnh hưởng discoverability hay vòng đời class?
16. Vì sao hidden class mặc định có thể unload khi defining loader vẫn sống?
17. Làm sao gọi static method của hidden class nếu không thể tìm class lại bằng string name?
18. Phân biệt dùng `MethodHandle` và dùng Java reflection khi đã có `Class<?>` của hidden class.
19. Khi thiết kế generated adapters, vì sao cần giữ interface API chung thay vì cố xuất hidden type ra toàn hệ?
20. Một plugin loader cần tìm class theo binary name để nạp extension từ JAR: hidden class có phải lựa chọn mặc định phù hợp không? Vì sao?
21. Nếu `defineHiddenClass` ném `IllegalAccessException`, vấn đề thường nằm ở lookup privileges hay ở tên class không tồn tại trong classpath?
22. Tại sao `ClassNotFoundException` từ `loadClass(hidden.getName())` không chứng minh hidden class chưa từng chạy?
23. Việc giữ mọi `MethodHandle` trong static cache vĩnh viễn có thể ảnh hưởng gì tới unloading?
24. Cần làm gì nếu bytecode do bên thứ ba không tin cậy cung cấp?

**Tiêu chí hoàn thành:** chạy đúng ví dụ Java 17 và giải thích đủ 12 dòng stdout; nắm rõ giới hạn tra cứu bằng tên, biết giữ `Lookup`/`Class<?>`/`MethodHandle`; phân biệt ordinary/hidden classes, initialize/link, NESTMATE/STRONG và vòng đời class.

## 12. Tài liệu chính thức

- [Java SE 21 — `MethodHandles.Lookup#defineHiddenClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): nguồn chuẩn về cách định nghĩa hidden class, name lookup, initialize, access, unload.
- [Java SE 21 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [Java SE 21 — `Class.isHidden()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isHidden()): phát hiện hidden class.
- [Java SE 21 — `Class.descriptorString()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#descriptorString()): descriptor string dành cho runtime type.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): động lực thiết kế và giới hạn non-discoverable classes.
- [JVMS Java SE 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): creation, loading, linking, initialization và runtime identity.

**Kết luận:** hidden class không biến mất khỏi JVM và cũng không đồng nghĩa “private class”. Nó là một class động **không có binary name để khám phá theo tên**. Hãy giữ một handle/reference để sử dụng, thiết kế lifetime hợp lý và dùng ordinary class khi hệ thống thực sự cần nạp hoặc tham chiếu class bằng binary name.