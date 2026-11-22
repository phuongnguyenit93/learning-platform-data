# Định danh lớp gồm tên cùng class loader và lỗi trùng tên giữa các bộ nạp

## 1. Vì sao hai lớp cùng tên chưa chắc là một kiểu?

Trong Java, tên đầy đủ như `com.example.service.Order` **không đủ** để khẳng định hai đối tượng thuộc cùng một kiểu tại runtime. Theo Java Virtual Machine Specification (JVMS), **định danh runtime của một class/interface không phải mảng** được xác định bằng cặp:

**(binary name, defining class loader)**.

Hai loader khác nhau có thể **định nghĩa** hai class cùng tên nhị phân — thậm chí từ **cùng một mảng byte của tệp `.class`** — nhưng JVM xem đó là **hai kiểu khác nhau**. Ngược lại, hai loader gọi `loadClass("java.lang.String")` thường cùng nhận về **một** lớp do bootstrap loader định nghĩa; loader *khởi xướng yêu cầu* không nhất thiết là loader *định nghĩa class*.

Một hệ quả thực tế là lỗi tưởng như vô lý:

~~~text
ClassCastException: com.acme.Plugin cannot be cast to com.acme.Plugin
~~~

Nó có thể xảy ra khi hai tên in ra giống nhau, nhưng **defining loader không giống nhau**. Lỗi này đặc biệt phổ biến trong plugin system, application server, hot reload, OSGi, custom class loader, thư viện được đóng gói lặp lại và Java instrumentation có helper class.

Bài này phân biệt ba tình huống thường bị gọi chung là “trùng tên”: **hai loader khác nhau định nghĩa cùng tên (có thể hợp lệ)**, **một loader cố định nghĩa lại cùng tên (không hợp lệ)** và **xung đột khi JVM buộc các loader phải thống nhất kiểu qua ranh giới API (loader constraint violation)**.

## 2. Binary name, defining loader và initiating loader

### 2.1. Tên nhị phân khác tên file và tên nội bộ

Với nguồn Java:

~~~java
package example.plugin;
public final class Widget {}
~~~

Đây là **mảnh source riêng**, chỉ để minh họa quy tắc đặt tên; một file thực tế tương ứng là `example/plugin/Widget.java`.

| Dạng | Giá trị | Gặp ở đâu? |
| --- | --- | --- |
| **Binary name** | `example.plugin.Widget` | `Class.getName()`, `ClassLoader.loadClass(String)` và tham số `defineClass(String, ...)` |
| **Internal name** | `example/plugin/Widget` | Class-file constant pool, callback `ClassFileTransformer.transform` |
| **Tên tệp thông thường** | `example/plugin/Widget.class` | Đường dẫn resource hoặc entry trong JAR |
| **Tên mô tả kiểu mảng** | `[Lexample.plugin.Widget;` | `Class.getName()` cho `Widget[]`; là quy tắc tên mảng riêng |

Dấu chấm `.` và dấu slash `/` không hoán đổi tùy ý. Sai tên trong `defineClass` có thể dẫn tới `NoClassDefFoundError` do tên mong đợi không khớp với class bytes. Hai file đặt ở hai đường dẫn khác nhau **không tự động** tạo hai class runtime: phải xem loader nào thực sự định nghĩa chúng.

### 2.2. Defining loader: phần thứ hai của định danh

Khi JVM chấp nhận `defineClass("example.plugin.Widget", bytes, ...)` do một loader `L` thực hiện, class mới được định danh logic bằng:

~~~text
C = ("example.plugin.Widget", L)

("example.plugin.Widget", loaderA) !=
("example.plugin.Widget", loaderB)    nếu loaderA != loaderB
~~~

`Class.getClassLoader()` cho biết **defining loader** của class thông thường. Với class do **bootstrap loader** định nghĩa, Java phản ánh loader bằng giá trị `null`; `null` ở đây không đồng nghĩa lớp bị lỗi hoặc không có cơ chế loader.

Loader identity được so bằng **danh tính object**, không phải chỉ tên loader, tên package hay `toString()`. Hai instance của cùng một subclass `PluginLoader` vẫn là hai defining loaders khác nhau.

### 2.3. Initiating loader: người đề nghị nạp không nhất thiết là người định nghĩa

Giả sử `pluginLoader` gọi `loadClass("java.lang.String")` rồi ủy quyền thành công cho bootstrap. `pluginLoader` có thể được JVM ghi nhận là **initiating loader** của `String`, còn **defining loader** vẫn là bootstrap. Điều này không tạo ra thêm một định nghĩa `java.lang.String` nào.

~~~text
pluginLoader.loadClass("java.lang.String")
     |
     +-- hỏi parent/chuỗi delegation
                |
                v
           bootstrap định nghĩa java.lang.String
                |
                v
       pluginLoader nhận lại CHÍNH Class<?> đó
~~~

Vì vậy không được kết luận “hai loader đều gọi `loadClass` thì chắc chắn có hai class”. Chỉ khi có **hai defining loaders thực sự khác nhau** đối với cùng binary name, JVM mới có hai kiểu không đồng nhất.

Đặc tả có khái niệm **initiating loader** để quản lý resolution/loading constraints; việc một loader được ghi nhận là initiating không biến nó thành defining loader. API `Instrumentation.getInitiatedClasses(loader)` còn có phạm vi khác với `Class.getClassLoader()`: nó không có nghĩa mọi class trong kết quả do chính loader ấy định nghĩa.

## 3. Ba dạng “trùng tên” phải phân biệt

| Tình huống | Kết quả nguyên tắc | Vì sao |
| --- | --- | --- |
| Loader A định nghĩa `p.Widget`; loader B độc lập cũng định nghĩa `p.Widget` | **Có thể hợp lệ**, tạo hai `Class<?>` khác nhau | Hai cặp (name, defining loader) khác nhau |
| Loader A gọi `loadClass("p.Widget")` lại sau lần đầu | Bình thường trả **cùng `Class<?>`** | Contract loader tốt và `findLoadedClass` tránh định nghĩa lại |
| Loader A gọi `defineClass("p.Widget", bytes)` hai lần | **`LinkageError`** | Cùng loader không thể định nghĩa lần hai cùng binary name |
| Loader B ủy quyền thành công cho A để nạp `p.Widget` | Cả hai thấy **một class do A định nghĩa** | B chỉ là initiating loader |
| `defineClass("p.Other", bytesOfPWidget)` | Thường **`NoClassDefFoundError`** | Binary name mong đợi khác tên nằm trong class bytes |
| Hai loader định nghĩa những phiên bản `p.Widget` khác nhau, rồi code ép kiểu trực tiếp giữa chúng | Có thể **`ClassCastException`** | Hai class runtime không cùng kiểu |
| Hai loader định nghĩa `p.Widget` khác nhau nhưng tham gia API có loading constraint buộc tên đó thống nhất | Có thể **`LinkageError: loader constraint violation`** | JVM bảo vệ type safety khi liên kết |
| Hai bản sao thư viện trùng tên nhưng đều được ủy quyền cho một loader chung | Không tự tạo hai class runtime | Resource/JAR trùng không đồng nghĩa duplicate definition |

**Không phải mọi trùng tên đều lỗi**, và **không phải mọi lỗi trùng tên đều `ClassCastException`**. Cần biết chính xác **ai đang định nghĩa**, **ai đang ủy quyền**, và **lỗi phát sinh tại loading, linking hay lúc cast**.

### 3.1. Vì sao lần thứ hai `loadClass` khác lần thứ hai `defineClass`?

Theo triển khai mặc định của `ClassLoader.loadClass(String, boolean)`, JVM đi theo logic:

~~~text
loadClass(name):
    nếu findLoadedClass(name) đã có -> trả về class cũ
    nếu chưa có -> hỏi parent (hoặc bootstrap khi parent null)
    nếu parent không tìm được -> gọi findClass(name)
    có class -> có thể resolveClass khi được yêu cầu
~~~

`findClass` do loader tùy biến có thể override để lấy bytes và gọi `defineClass` **lần đầu**. Còn gọi trực tiếp `defineClass` lần nữa với tên đã được loader ấy định nghĩa là một thao tác khác, không phải lookup/caching bình thường.

Một implementation cố định nghĩa lớp qua `findClass` mỗi lần mà bỏ qua contract `findLoadedClass` dễ gây lỗi, nhất là khi nhiều thread cùng request cùng tên. Thông thường hãy override `findClass` thay vì tùy tiện override toàn bộ `loadClass`; nếu thực sự dùng child-first, phải kiểm soát locking, giới hạn namespace và các lớp API chia sẻ.

## 4. Ví dụ Java 17+ chạy được: cùng bytes, hai loader, hai class

Ví dụ đầy đủ dùng **hai tệp nguồn**. Đầu tiên biên dịch một class thật thành bytes, sau đó tạo hai loader độc lập. Mỗi loader được yêu cầu **định nghĩa trực tiếp** class từ chính mảng bytes đó. Chúng có **cùng binary name và cùng nội dung**, nhưng khác defining loader.

### 4.1. `src/lab/plugin/Widget.java`

~~~java
package lab.plugin;

public final class Widget {
    public String message() {
        return "hello";
    }
}
~~~

### 4.2. `src/LoaderIdentityDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public final class LoaderIdentityDemo {
    private static final String BINARY_NAME = "lab.plugin.Widget";

    private static final class MemoryLoader extends ClassLoader {
        MemoryLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("out/lab/plugin/Widget.class"));
        MemoryLoader first = new MemoryLoader();
        MemoryLoader second = new MemoryLoader();

        Class<?> a = first.define(BINARY_NAME, bytes);
        Class<?> b = second.define(BINARY_NAME, bytes);
        Object one = a.getDeclaredConstructor().newInstance();
        Object two = b.getDeclaredConstructor().newInstance();

        System.out.println("sameName=" + a.getName().equals(b.getName()));
        System.out.println("sameClass=" + (a == b));
        System.out.println("differentDefiningLoader="
                + (a.getClassLoader() != b.getClassLoader()));
        System.out.println("firstRecognizesOwn=" + a.isInstance(one));
        System.out.println("firstRecognizesOther=" + a.isInstance(two));
        System.out.println("method=" + a.getMethod("message").invoke(one));
        System.out.println("cachedLoad=" + (first.loadClass(BINARY_NAME) == a));
        System.out.println("delegatedString="
                + (first.loadClass("java.lang.String")
                == second.loadClass("java.lang.String")));

        try {
            a.cast(two);
            System.out.println("crossCast=unexpected");
        } catch (ClassCastException expected) {
            System.out.println("crossCast=ClassCastException");
        }

        try {
            first.define(BINARY_NAME, bytes);
            System.out.println("doubleDefine=unexpected");
        } catch (LinkageError expected) {
            System.out.println("doubleDefine=LinkageError");
        }
    }
}
~~~

### 4.3. Biên dịch và chạy

Từ thư mục chứa `src/`, dùng JDK 17 trở lên:

~~~bash
mkdir -p out
javac --release 17 -d out src/lab/plugin/Widget.java src/LoaderIdentityDemo.java
java -cp out LoaderIdentityDemo
~~~

Dòng `mkdir -p out` là cú pháp shell Unix. Trên **Windows PowerShell**, thay bằng `New-Item -ItemType Directory -Force out`; hai lệnh `javac` và `java` giữ nguyên. Chạy bằng **thư mục làm việc chứa `out`** vì ví dụ đọc `out/lab/plugin/Widget.class` bằng đường dẫn tương đối.

**Stdout chính xác** của ví dụ (đã biên dịch bằng `javac --release 17` và chạy trên JDK tương thích):

~~~text
sameName=true
sameClass=false
differentDefiningLoader=true
firstRecognizesOwn=true
firstRecognizesOther=false
method=hello
cachedLoad=true
delegatedString=true
crossCast=ClassCastException
doubleDefine=LinkageError
~~~

Ý nghĩa:

1. `sameName=true`: cả hai class trả `"lab.plugin.Widget"` từ `getName()`.
2. `sameClass=false`: `Class<?> a` và `Class<?> b` là **hai object class runtime khác nhau**, không phải hai reference đến cùng class.
3. `differentDefiningLoader=true`: `a.getClassLoader()` và `b.getClassLoader()` khác nhau. Đây là điều kiện giải thích sự khác biệt về identity.
4. `firstRecognizesOwn=true` nhưng `firstRecognizesOther=false`: object do loader B định nghĩa **không là instance của class do loader A định nghĩa**, mặc dù bytes giống.
5. `method=hello`: class của loader A hoạt động bình thường; lỗi không phải vì class bytes thiếu hợp lệ.
6. `cachedLoad=true`: sau khi loader A đã định nghĩa `Widget`, `first.loadClass(...)` trả lại chính class ấy thay vì định nghĩa thêm lần nữa.
7. `delegatedString=true`: cả hai loader cùng ủy quyền nạp `java.lang.String` tới lớp do bootstrap loader quản lý.
8. `crossCast=ClassCastException`: `Class.cast` kiểm tra *runtime type identity*, không chỉ tên in ra.
9. `doubleDefine=LinkageError`: **chính loader A** cố định nghĩa lại `Widget` và bị JVM từ chối.

**Vì sao constructor `MemoryLoader()` chọn platform loader làm parent?** Mục tiêu demo là kiểm soát việc định nghĩa `Widget` của hai loader độc lập, tránh việc một parent app loader trên classpath nhận thay class `Widget`. `first.define(...)` gọi `defineClass` có kiểm soát trực tiếp; còn các lớp nền như `String` vẫn được parent/bootstrap cung cấp. Đây là lựa chọn cho **demo cô lập**, không phải khuyến nghị bắt mọi plugin loader production phải dùng platform loader làm parent.

**Lưu ý:** file `Widget.class` trên đĩa chỉ là cách dễ lấy một mảng bytes để chạy thử. Hai lớp runtime khác nhau **không phải** vì có hai tệp `Widget.class` khác nhau — cả hai dùng **chính một mảng bytes**. Bản sắc runtime xuất hiện ở thao tác **định nghĩa bởi từng loader**.

### 4.4. Tại sao không ép kiểu về `Widget` trong mã ví dụ?

Chương trình chính không import `lab.plugin.Widget` để ép kiểu compile-time. Nếu import và dùng `(Widget) two`, tên `Widget` trong `LoaderIdentityDemo` sẽ được liên kết với class do **app loader** nhìn thấy, có thể tạo **một kiểu thứ ba** hoặc thay đổi tình huống thử. Demo cố ý sử dụng `Class.cast(Object)` trên đúng `Class<?>` của loader A, bảo đảm phép thử phản ánh sự khác biệt giữa A và B.

Trong hệ thống thật, việc `ClassCastException` báo “`X cannot be cast to X`” thường là dấu hiệu một interface/model/JAR đã được định nghĩa trùng ở các loader khác nhau. Đừng chữa bằng cách đổi tên biến Java hoặc ép kiểu nhiều lần.

## 5. Hai bản sao thư viện: khi nào chỉ là resource trùng, khi nào tạo ra class trùng?

Một ứng dụng có thể chứa `lib-a.jar` và `lib-b.jar`, cả hai đều chứa `com.vendor.Model.class`. Có vài kết quả khác nhau:

- **Một classpath, một application loader:** việc tra cứu resource theo thứ tự classpath/module path có thể chọn một bản để định nghĩa class. Không tự sinh hai `Class<?>` chỉ vì hai JAR trùng entry. Có nguy cơ **chọn nhầm version**.
- **Hai plugin loaders riêng, mỗi loader define cùng binary name:** có thể tạo hai class runtime khác nhau, **mỗi loader chỉ một định nghĩa**. Cô lập phiên bản có thể là chủ đích.
- **Một loader cố define cùng binary name hai lần:** `LinkageError`.
- **Hai plugin tưởng độc lập nhưng phải trao đối tượng của class trùng tên với nhau:** có thể nhận `ClassCastException` hoặc loader constraint violation, vì class ở ranh giới API không thống nhất.

**Class file path là dữ liệu truy xuất, không phải tiêu chí định danh JVM.** In ra `getProtectionDomain().getCodeSource()` có thể hữu ích để biết vị trí JAR (khi có), nhưng hai class từ cùng vị trí vẫn có thể khác identity nếu được định nghĩa bởi loader khác nhau; ngược lại một class có thể được định nghĩa từ bytes trong bộ nhớ mà không có code source URL hữu ích.

## 6. Loader constraints: vì sao hai lớp cùng tên được phép tồn tại nhưng có lúc lại gây `LinkageError`?

JVM cho phép hai loader độc lập định nghĩa cùng một binary name nếu chúng thật sự ở các namespace tách biệt. Tuy nhiên, khi một class gọi method/field của class được loader khác định nghĩa, **descriptor** có thể nhắc tới những kiểu mà cả hai phía phải hiểu **giống nhau** để đảm bảo type safety.

Ví dụ khái niệm:

~~~text
api.Contract            định nghĩa bởi loader P (shared parent)
  method: process(api.Message) : api.Message

plugin.Impl             định nghĩa bởi loader C (child)
  implements api.Contract
  process(api.Message) : api.Message

Nếu loader P và C hiểu api.Message thành hai Class<?> KHÁC NHAU,
JVM có thể áp đặt loading constraint và từ chối liên kết.
~~~

Đây là **mô hình khái niệm**, không phải ví dụ lập trình tự chạy. Khi implementation override một method ở API cha, các kiểu trong parameter và return descriptor phải phù hợp với các **loading constraints** áp dụng. Nếu cùng tên `api.Message` được gắn với hai class khác nhau nhưng JVM bắt chúng phải tương đương, linking có thể ném **`LinkageError`**; thông báo trên HotSpot có thể chứa cụm `loader constraint violation`.

Điều đó **không có nghĩa** cứ có hai định nghĩa cùng tên từ hai loader thì JVM lập tức ném lỗi. Lỗi liên quan constraints thường chỉ nảy sinh khi quá trình **preparation/resolution hoặc ghi nhận initiating loader** tạo ra xung đột thực sự. JVM còn có quyền trì hoãn resolution; lỗi có thể xuất hiện ở lần đầu sử dụng một method/field, không nhất thiết ngay khi loader được tạo.

### 6.1. Vì sao JVM cần cơ chế này?

Nếu phía gọi nghĩ tham số là class `api.Message` do loader P định nghĩa, nhưng phía nhận nghĩ đó là class khác cùng tên do loader C định nghĩa, chữ ký bytecode nhìn theo tên có vẻ khớp mà object type thực tế không khớp. JVM áp đặt loader constraints để ngăn phá vỡ **tính an toàn kiểu** qua ranh giới method/field.

Một nguyên tắc thiết kế mạnh: **các kiểu xuất hiện trong API được chia sẻ giữa plugin và host phải được định nghĩa bởi loader chung** (thường parent/host loader) và plugin loaders **ủy quyền** đúng những package đó. Tách phần implementation vào loader riêng, không duplicate contract types.

## 7. Runtime package cũng phụ thuộc defining loader

Hai class có cùng `package example.bridge;` trong source nhưng được định nghĩa bởi hai loader khác nhau **không mặc nhiên thuộc cùng runtime package**.

Theo JVMS, *runtime package* được xác định bởi **tên package và defining loader**. Vì vậy:

- Việc cùng dòng `package` trong source **không đảm bảo** package-private access qua hai loader.
- Các quy tắc access, nest/module, protection domain và sealed packages vẫn phải được JVM kiểm tra phù hợp; “trùng package string” không phải công cụ cấp quyền.
- Reflection hoặc `setAccessible` không phải giải pháp mặc định để sửa lỗi identity; trong Java module system còn có ràng buộc `exports` và `opens` riêng.
- `Class.getPackageName()` trùng nhau **không chứng minh** hai class cùng runtime package.

Điều này đặc biệt quan trọng cho **agent helper** được inject vào loader khác với class nghiệp vụ. Helper và target đều khai báo `package com.app;` nhưng nếu chúng được định nghĩa bởi hai loader khác nhau thì vẫn không có quan hệ package-private hợp lệ chỉ nhờ chuỗi tên ấy.

**Các kiểu mảng và primitive:** primitive như `int.class` có `getClassLoader() == null`. Class mảng được JVM tạo, và `getClassLoader()` của mảng phản ánh loader của kiểu phần tử reference (hoặc `null` cho primitive array). Chúng có quy tắc tạo riêng trong JVMS; không nên lấy demo định nghĩa class thường rồi suy `defineClass` cũng được gọi trực tiếp cho `int[]`.

## 8. Liên hệ thực tế với Java instrumentation và helper class

Một agent thường gồm hai nhóm bytecode:

- **Logic của agent:** `premain`/`agentmain`, transformer, registry, logger, exporter.
- **Helper/advice được gọi từ mã ứng dụng sau khi instrument:** ví dụ `ProbeBridge.onEnter()` và `ProbeBridge.onExit()` do bytecode được chèn gọi trực tiếp.

Vấn đề không chỉ là agent **có thể load** `ProbeBridge`, mà còn là **class được transform có resolve được chính xác class helper phù hợp hay không**.

~~~text
               JVM
AgentLoader -> Agent/Transformer -> tạo bytecode gọi probe.Helper.enter()
                                          |
                                          v
                                App class do PluginLoader định nghĩa
                                          |
                                          v
                               resolve "probe.Helper" dưới
                               cơ chế loader/module phù hợp
~~~

Nếu helper chỉ được agent/system loader định nghĩa nhưng plugin loader có parent cô lập không thể tìm thấy helper, code đã transform có thể gặp **`NoClassDefFoundError`** khi JVM cần resolve tham chiếu. Nếu hai loader định nghĩa **hai bản `probe.Helper` cùng tên**, static state/counter của chúng cũng **tách biệt**: transformer tưởng đang đọc một counter chung, trong khi app code cập nhật counter ở bản helper khác.

### 8.1. Cẩn thận với hai bản helper cùng tên

Giả sử:

~~~text
agent's system loader:
    probe.Helper  -> static counter A

isolated plugin loader:
    probe.Helper  -> static counter B
~~~

Dù source/bytes của `probe.Helper` giống nhau, `counter A` và `counter B` thuộc hai **class runtime riêng**, mỗi class có static fields riêng. Đây có thể làm metric “mất số” hoặc ghi vào sai exporter mà không có exception ngay lập tức.

Nếu bytecode instrumented gọi `Helper.enter(Model)` và `Model` ở các loader không thống nhất, JVM có thể gặp **loader constraint** hoặc lỗi liên kết khác, không chỉ `ClassNotFoundException`. Đưa helper vào đúng classpath chưa chắc đủ: phải hiểu **defining loader**, **module visibility**, **package access**, **dependency loader** và **version** của helper.

### 8.2. Những cách bố trí helper

| Phương án | Khi hữu ích | Điều phải kiểm tra |
| --- | --- | --- |
| Helper ở **shared parent/API loader** | Nhiều plugin con cần dùng một contract/bridge | Plugin loaders thực sự delegate tên đó; package và version nhất quán |
| Helper được định nghĩa trong **từng plugin loader** | Muốn cô lập state/version cho mỗi plugin | Chấp nhận mỗi loader có `Helper.class` và static state riêng; không cast/trao đổi helper type qua loader |
| Helper ở **bootstrap search** bằng `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` | Probe được gọi từ nhiều loader, cần helper tối thiểu có khả năng hiển thị rộng | Chỉ append JAR đã kiểm định; tránh xung đột tên/package; không giả định tự động giải quyết mọi module access |
| Helper trong **system class-loader search** | Target có thể resolve qua system parent | Loader của target có thể không ủy quyền tới system; plugin có thể cô lập |
| Biến đổi bytecode để gọi bridge đã định nghĩa sẵn ở loader phù hợp | Muốn kiểm soát quyền truy cập và compatibility | Chọn API signature chỉ dùng kiểu được chia sẻ, đúng JPMS reads/exports/opens |

`appendToBootstrapClassLoaderSearch` **thêm JAR vào đường tìm kiếm của bootstrap**, không tự động “chuyển” các class đã được định nghĩa ở loader khác sang bootstrap và cũng không làm mọi module mở package. Thực tế helper ở bootstrap nên rất nhỏ, tránh tham chiếu ngược tới API chỉ tồn tại ở application loader, vì bootstrap không tự nhìn xuống mọi child loader.

Nếu agent dùng thư viện ASM/Byte Buddy/metrics, hãy tách **engine của agent** khỏi những class **runtime helper** thật sự cần được gọi từ mã ứng dụng; tránh chèn cả thư viện lớn vào bootstrap khi không có lý do. Namespace helper nên được đặt tên có tính đặc thù, tránh va chạm với thư viện của ứng dụng hoặc agent khác.

### 8.3. Loader trong callback transformer là thông tin quan trọng

Mảnh code trong một `ClassFileTransformer` (không phải chương trình độc lập):

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] bytes) {

    // className thường là internal name, ví dụ lab/plugin/Widget.
    // loader là defining loader của class mà JVM đang xử lý.
    if (className == null || !className.startsWith("lab/plugin/")) {
        return null;
    }
    // Phải xét loader/module/helper visibility trước khi weave.
    // Không chạm vào bytes đầu vào khi chỉ muốn quan sát.
    return null;
}
~~~

Không dùng **tên class đơn thuần** làm key duy nhất cho trạng thái instrument nếu nhiều loader có cùng `lab/plugin/Widget`. Cặp tên nội bộ + defining-loader identity (và context phiên bản nếu cần) tốt hơn. Với class đã loaded, dùng chính `Class<?>` để nhận diện chính xác: `Instrumentation.isModifiableClass(theClass)` và `retransformClasses(theClass)` cũng làm việc trên **đúng một class object**, không nhận chuỗi tên để JVM tự chọn tùy tiện.

Đối với loader bootstrap, tham số `loader` có thể `null`; không được gọi `loader.toString()` vô điều kiện trong transformer. Cũng không nên log/scan classpath phức tạp trong callback: có thể kích hoạt thêm class loading của chính agent và gây reentrancy.

## 9. Chẩn đoán lỗi: xác định class nào, loader nào, ở bước nào

### 9.1. Bộ thông tin tối thiểu

Khi một exception nói “cùng tên nhưng cast không được”, hãy thu (theo kênh chẩn đoán an toàn):

- **Tên nhị phân:** `type.getName()`.
- **Defining loader:** `type.getClassLoader()`; in kèm **loader class** và một ID mang tính nhận diện object khi cần, không dùng loader name như khóa duy nhất.
- **Module:** `type.getModule()` để nhận ra ranh giới JPMS.
- **Nguồn mã nếu có:** `type.getProtectionDomain().getCodeSource()`; có thể null hoặc không truy cập được, không coi URL là identity.
- **Mối quan hệ:** hai `Class<?>` có thực sự `==` không? `typeA.isInstance(objectB)` là true hay false?
- **Ngữ cảnh lỗi:** xảy ra lúc tìm class, define, link, invoke, cast hay plugin reload?

Mảnh mã minh họa khi đã có `Class<?> type`:

~~~java
System.out.println("binaryName=" + type.getName());
System.out.println("definingLoader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

Không phải chương trình độc lập. Một output loader dạng `SomeLoader@5a3a1b` chỉ là biểu diễn triển khai; không ổn định giữa các lần chạy. Đối chiếu **object identity** hoặc lưu một định danh nội bộ do diagnostic layer tạo ra; không so chuỗi `toString()` làm căn cứ type equality.

### 9.2. Ma trận lỗi và nguyên nhân

| Triệu chứng | Giải thích khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `ClassCastException: X cannot be cast to X` | Hai bản `X` do loader khác nhau định nghĩa | In hai `Class<?>`/defining loader; thống nhất shared API hoặc tránh cast |
| `LinkageError: attempted duplicate class definition` | Một loader định nghĩa **lại** cùng binary name | Sửa `findClass`/`loadClass`, caching và concurrency |
| `LinkageError: loader constraint violation` | Hai loader trả các class khác nhau cho một kiểu mà JVM buộc phải thống nhất ở boundary | Chuyển contract model/type lên shared parent; kiểm tra descriptors và delegation |
| `NoClassDefFoundError` sau khi agent chèn lời gọi helper | Target loader không resolve được helper hoặc dependency | Cấp helper ở loader mà target nhìn thấy, kiểm tra modules và dependencies |
| `ClassNotFoundException` từ `loadClass`/`Class.forName` | Loader được hỏi không tìm được tên | Xem classpath/parent/delegation và binary name |
| `NoClassDefFoundError` do tên không khớp | `defineClass` dùng tên dự kiến khác tên trong bytes | So binary name với class-file `this_class` |
| `IllegalAccessError` | Quyền truy cập/runtime package/module không cho phép | Kiểm tra defining loader của hai class, module exports/opens và access flags |
| `NoSuchMethodError` hoặc `AbstractMethodError` | API binary compatibility/version giữa các loader hoặc JAR không đồng nhất | Kiểm tra chữ ký method/descriptor và bản dependency được resolve |
| `ClassCircularityError` | Quan hệ loading/supertype vòng, hoặc loader tạo chuỗi định nghĩa vòng không hợp lệ | Xem stack loading, thứ tự/tính đệ quy của custom loader |
| `SecurityException` trong `defineClass` | Ví dụ class trong package `java.*`, certificate/package policy không hợp lệ | Không vượt chính sách JVM; chọn namespace phù hợp |

**Đừng gộp tất cả thành “classloader conflict”.** `NoSuchMethodError` có thể thuần túy do API version mismatch mà không cần hai loader khác nhau. `ClassNotFoundException` có thể là lookup failure bình thường. Luôn dùng exception class, stack trace, loader identity và tình huống tái hiện làm bằng chứng.

### 9.3. Tại sao lỗi có thể xuất hiện muộn?

JVM có thể trì hoãn một số thao tác **symbolic reference resolution**. Một class có thể được load/define trước, nhưng chỉ khi một method khác được invoke hoặc field được resolve mới phát hiện sự không khớp. Vì vậy “agent đã load được helper” **không chứng minh** mọi call site chèn vào sẽ liên kết đúng.

Chẩn đoán tốt nên tái hiện **đúng call site** và ranh giới loader, không chỉ kiểm tra `Class.forName("probe.Helper")` từ thread/tool loader bất kỳ: `Class.forName` với loader khác có thể kiểm tra **một bản helper khác** so với bản mà target bytecode sẽ resolve.

## 10. Kiến trúc plugin an toàn: chia contract và implementation

Một thiết kế phổ biến:

~~~text
Host/Application loader
    -> api.Plugin (interface)
    -> api.Request, api.Result (DTO/contract)

PluginLoader A (parent = Host)
    -> pluginA.Implementation
    -> dependency-private A

PluginLoader B (parent = Host)
    -> pluginB.Implementation
    -> dependency-private B

Cả A/B DELEGATE api.* đến Host.
~~~

Điều có thể chia sẻ:

- Các đối tượng `api.Plugin`, `api.Request`, `api.Result` được định nghĩa **một lần** ở shared host loader.
- Mỗi plugin giữ class implementation và thư viện private của nó trong loader riêng; hai plugin có thể dùng các phiên bản dependency khác nhau **nếu không lộ những type đó qua shared API**.
- Host cast implementation sang `api.Plugin` thành công **khi implementation thật sự implements đúng `Class<?> api.Plugin` do host định nghĩa**, không phải một interface cùng tên được plugin tự định nghĩa.

Nếu plugin đóng gói bản sao `api.Plugin` trong child và dùng child-first load cho `api.*`, host và plugin có thể nhìn thấy **hai interface cùng tên khác identity**; cast thất bại dù chữ ký source và JAR giống. Cách sửa là **quy hoạch namespace delegation** và dependency packaging, không phải chỉ viết `(Plugin)(Object) obj`.

Đối với dữ liệu trao đổi qua boundary, dùng interface/DTO do host định nghĩa, hoặc serialization/structured data với schema/version rõ nếu cần thực sự cô lập. Đừng chuyển raw `Class<?>`, implementation object hoặc generated helper class giữa plugin loaders rồi ép kiểu bằng binary name.

### 10.1. Parent-first không phải quy luật tuyệt đối

`ClassLoader.loadClass` mặc định thường ưu tiên parent, nhưng custom loaders có thể xây **child-first** cho các namespace riêng để cô lập dependency. Điều quan trọng không phải “parent-first luôn đúng”, mà là **có quy tắc nhất quán cho shared API**.

Thực tế có thể dùng chính sách:

~~~text
java.*, javax.* cần theo quy định platform/runtime
api.host.*      -> luôn delegate về host
probe.bridge.*   -> delegate về shared helper loader
plugin.private.* -> child-first có kiểm soát
các tên khác     -> chiến lược rõ ràng, có fallback
~~~

Đây là bảng **chính sách khái niệm**, không phải bộ luật class loading áp dụng máy móc cho mọi JDK/JVM. Với JPMS layer, module reader, OSGi hoặc ứng dụng enterprise, còn có cơ chế resolution/visibility riêng; một `ClassLoader` custom không nên bỏ qua bảo đảm JVM về package sealing và concurrent loading.

## 11. Bộ nhớ, vòng đời class loader và cache

Hai loader khác nhau không chỉ tạo hai class identity: chúng còn có thể giữ **hai bản static state**, metadata và code cần thiết. Với plugin reload, tạo một loader mới cho cùng tên có thể là cách hợp lệ để nạp phiên bản code mới mà không cố định nghĩa lại cùng tên trong loader cũ.

Nhưng **unloading** loader/class không tự xảy ra chỉ vì bạn gọi `plugin.close()` hoặc xóa file JAR:

- Nếu thread, `ThreadLocal`, callback, MBean, scheduled task, registry, static field hoặc agent transformer còn giữ reference tới class/loader/instance, chúng có thể giữ loader sống.
- Cache toàn cục `Map<String, Class<?>>` không phân biệt loader, dễ trả **nhầm class** khi đổi plugin version.
- Cache `Map<ClassLoader, Map<String, ...>>` phân biệt được identity nhưng có thể giữ loader sống nếu map không có chiến lược vòng đời.
- `ClassValue<T>` là một công cụ JVM dành cho giá trị gắn theo `Class<?>`, có thể hữu ích để cache metadata theo đúng class identity. Cần hiểu lifecycle/concurrency của giá trị và tránh vòng reference làm tăng giữ bộ nhớ.
- Không “sửa” vấn đề reload bằng cách cố gọi lại `defineClass` trên cùng loader; nó không thay thế một kiểu đã định nghĩa.

Trong Java instrumentation, một weak-key cache hoặc `ClassValue` có thể phù hợp hơn việc lưu `Class<?>` vô hạn trong static map của agent; nhưng còn phải kiểm tra **value** có giữ ngược class/loader không, tránh vô tình phá khả năng GC.

## 12. Checklist triển khai và kiểm thử

### Trước khi đưa helper vào ứng dụng

1. Liệt kê **tên binary** của helper, advice, bridge và các type xuất hiện trong public method descriptors.
2. Xác định **loader thực tế định nghĩa target class** và **loader định nghĩa từng helper**.
3. Kiểm tra target có khả năng resolve helper sau khi bytecode được chèn: parent delegation, isolation, module reads/exports/opens, dependency của helper.
4. Quyết định helper chia sẻ **một bản** hay **mỗi plugin một bản**, bao gồm chính sách static counters/registry.
5. Giữ shared API trong **một loader chung** nếu object phải được cast/trao đổi qua boundary.
6. Loại trừ package của agent/helper/logger khỏi transformer khi cần, tránh agent tự instrument.
7. Thiết kế cache bằng **class identity**, không chỉ `getName()`.
8. Xác minh namespace không va chạm với các agent hoặc JAR của ứng dụng; dùng package riêng và đóng gói phụ thuộc cẩn thận.
9. Kiểm thử lần load đầu tiên, lần load lặp lại, hot reload, hai plugins cùng tên và concurrency trong cùng loader.
10. Chạy thử **đúng call site đã instrument**, không chỉ kiểm tra loader từ bên ngoài.

### Bộ kiểm tra thực nghiệm tối thiểu

- **A/B cùng bytes:** hai loader định nghĩa `p.Type` riêng phải tạo hai `Class<?>` không đồng nhất.
- **A nạp lần nữa:** `loadClass` trả class cũ, không tự định nghĩa thêm.
- **A cố define lại:** nhận `LinkageError`.
- **A/B cùng delegate JDK class:** cả hai nhận một `Class<?>` do bootstrap định nghĩa.
- **Object từ A cast sang class B:** không thành công chỉ vì cùng tên.
- **Shared interface:** implementation do plugin loader định nghĩa nhưng implements contract từ host loader phải cast được sang đúng interface chung.
- **Helper thiếu:** test xử lý `NoClassDefFoundError`/resolution trong môi trường cô lập.
- **Helper được định nghĩa hai lần:** xác minh static metrics/registry không bị phân tách ngoài dự định.
- **Loading constraints:** thử các method boundary có descriptor kiểu được load từ nhiều loader và kiểm tra linking.
- **Cleanup:** sau khi bỏ plugin, kiểm tra reference giữ loader sống và giới hạn cache/ThreadLocal.

## 13. Các hiểu nhầm cần tránh

1. **“`Class.getName()` bằng nhau thì hai `Class<?>` bằng nhau.”** Sai: phải xét defining loader.
2. **“Cứ có hai tệp `p/Foo.class` thì JVM tạo hai class.”** Sai: phụ thuộc class loader nào định nghĩa.
3. **“Hai loader khác nhau cùng gọi `loadClass` chắc chắn có hai class.”** Sai: delegation có thể trả chung class.
4. **“Trùng binary name ở hai loader luôn ném `LinkageError`.”** Sai: có thể là hai namespace hợp lệ, chưa cần cast hay linking qua boundary.
5. **“Gọi `defineClass` lần hai chỉ làm reload class.”** Sai: cùng loader định nghĩa lại cùng tên gây `LinkageError`.
6. **“Sửa cast bằng cách ép về `Object` rồi ép lại.”** Không: runtime type identity không đổi.
7. **“Chỉ cần đặt helper có cùng package với target.”** Sai: runtime package còn phụ thuộc defining loader.
8. **“`appendToBootstrapClassLoaderSearch` giải quyết mọi vấn đề.”** Sai: không tự giải quyết module/loader constraints hoặc dependency đi ngược chiều.
9. **“`ClassNotFoundException` và `NoClassDefFoundError` là một.”** Sai: lookup từ API và linkage/definition failure có bối cảnh khác nhau.
10. **“`getClassLoader() == null` là lỗi.”** Sai: bootstrap class loader thường được biểu diễn bằng null.
11. **“Một cache theo tên là đủ cho agent dùng nhiều plugin loaders.”** Sai: cùng tên có nhiều class/runtime versions.
12. **“Tên package giống nhau nên có package-private access.”** Sai: còn phải cùng runtime package theo JVMS.
13. **“Load thành công helper nghĩa mã đã weave chắc chắn gọi được.”** Sai: cần resolve đúng helper và các method/types của nó từ target loader.
14. **“Bỏ hết reference đến byte[] là class được unload.”** Sai: classloader và object reachability mới là trọng tâm.

## 14. Câu hỏi tự kiểm tra

1. JVMS dùng những thành phần nào để xác định runtime identity của một class thông thường?
2. `defining loader` khác `initiating loader` ở chỗ nào? Cho ví dụ với `java.lang.String`.
3. Vì sao hai `Class<?>` tạo từ **cùng** `Widget.class` có thể không bằng nhau?
4. Vì sao `first.loadClass(BINARY_NAME)` thành công lần hai, còn `first.define(BINARY_NAME, bytes)` lại ném `LinkageError`?
5. Khi nào việc hai loader định nghĩa cùng `api.Message` hợp lệ, và khi nào JVM có thể áp đặt loader constraint gây lỗi?
6. Trong plugin architecture, bạn sẽ đặt `api.Plugin` ở loader nào để host có thể cast implementation?
7. Vì sao hai bản `probe.Helper` cùng tên có thể đếm metric vào hai static counters khác nhau?
8. Đặt agent helper cùng `package` với app class nhưng khác loader có tự cấp package-private access không?
9. Nếu class được định nghĩa trong plugin loader mà helper nằm ở system loader, những điều kiện nào khiến target resolve helper thành công hoặc thất bại?
10. Vì sao `Class.getProtectionDomain().getCodeSource()` và tên file JAR không phải key thay thế cho runtime type identity?
11. Vì sao lỗi liên kết có thể chỉ xuất hiện khi method lần đầu được gọi?
12. Khi reload plugin, tại sao tạo loader mới có ý nghĩa khác với định nghĩa lại một class trong loader cũ?

**Ghi nhớ:** Đối với class/interface không phải mảng, **runtime identity = binary name + defining class loader**. Hai loader độc lập có thể định nghĩa hai class cùng tên; việc ép kiểu qua lại không tự hợp lệ. Cùng một loader không thể định nghĩa lại cùng tên, và JVM còn áp đặt **loading constraints** ở các ranh giới liên kết để bảo vệ type safety. Khi thiết kế Java agent/helper hoặc plugin, hãy thống nhất các **shared contract types** ở loader thích hợp, kiểm tra đúng loader/module của target và không dùng riêng tên class để định danh hay cache.

### Tài liệu chính thức

- [JVMS Java 17 — `5.3 Creation and Loading, `5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java 17 — ClassLoader, loadClass và defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java 17 — Class, getName/getClassLoader/isInstance/cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java 17 — Instrumentation: bootstrap/system search và getInitiatedClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JLS Java 17 — Class Loader Consistency](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
