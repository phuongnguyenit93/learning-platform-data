# 2.5 Định danh kiểu theo tên và bộ nạp lớp: vì sao cùng tên vẫn khác kiểu

**Bối cảnh:** Java Advance → dynamic-runtime → 2. Kiểu lúc chạy.

Khi đọc mã nguồn, ta thường nhận diện kiểu qua tên như `com.example.Plugin`. Nhưng trong JVM, chỉ biết tên chưa đủ để kết luận hai đối tượng có cùng kiểu. Điều này đặc biệt quan trọng với plugin, application server, hot reload, framework tự nạp class và các hệ thống dùng nhiều `ClassLoader`.

## 1. Quy tắc định danh kiểu lúc chạy

Với **class hoặc interface không phải array**, Java Virtual Machine Specification (JVMS `5.3) xác định một kiểu lúc chạy bằng **cặp**:

```text
Runtime type identity = (binary name, defining class loader)
```

- **Binary name**: tên nhị phân, ví dụ `com.example.Plugin`, hoặc `com.example.Outer$Inner` cho lớp thành viên.
- **Defining loader**: chính bộ nạp lớp đã gọi cơ chế định nghĩa kiểu từ bytecode (thường qua `defineClass`), không nhất thiết là bộ nạp đầu tiên được yêu cầu tìm kiểu đó.
- Hai class có **cùng binary name và cùng defining loader** là cùng một kiểu runtime; một defining loader không thể định nghĩa thành công hai class khác nhau cùng binary name.
- Hai class có **cùng binary name nhưng hai defining loader khác nhau** là **hai kiểu runtime khác nhau**, dù bytecode giống hệt, cùng phiên bản, cùng đường dẫn hoặc cùng JAR.

Có thể hình dung như hai người trùng họ tên nhưng mang hai định danh khác nhau. Tên biểu diễn một phần thông tin; loader định nghĩa mới hoàn thiện danh tính của kiểu.

Ví dụ với tên `com.example.Plugin`:

| Kiểu | Binary name | Defining loader | Kết luận |
| --- | --- | --- | --- |
| A | `com.example.Plugin` | đối tượng loader L1 | Kiểu A |
| B | `com.example.Plugin` | đối tượng loader L2 | Kiểu B, **khác A** nếu L1 ≠ L2 |
| C | `com.example.Plugin` | chính loader L1 | **Cùng kiểu A** |

Chú ý: phân biệt **đối tượng loader** chứ không chỉ tên lớp loader. Hai instance của cùng `URLClassLoader` vẫn là hai defining loader khác nhau khi mỗi instance tự định nghĩa một class.

## 2. Loading, defining loader và initiating loader

Quá trình JVM xử lý một kiểu thường gồm **loading → linking → initialization**. Trong phần *loading*, khi loader L nhận yêu cầu tải tên N, nó có thể:

1. Tự tìm bytecode và định nghĩa N: L là **defining loader** của N.
2. Ủy quyền cho loader khác (thường là parent) định nghĩa N: L có thể là **initiating loader**, còn loader được ủy quyền mới là **defining loader**.

Chiến lược thông dụng của `ClassLoader.loadClass` là **parent-first delegation**: kiểm tra class đã tải, hỏi parent trước, sau đó mới tìm ở loader hiện tại nếu cần. Tuy nhiên, các loader tùy biến có thể có quy tắc riêng; parent-first là hành vi thông dụng của cơ chế `ClassLoader`, không phải định nghĩa của danh tính kiểu.

```text
Request: load("com.example.Api") trên PluginLoader
             |
             v
      PluginLoader (initiating)
             |
       delegate to parent
             v
      AppLoader (defining)
             |
             v
      Class<?> của Api
```

Nếu hai child loader đều ủy quyền `com.example.Api` về cùng một parent, cả hai nhận **cùng một `Class<?>`**. Vì thế, câu "hai loader khác nhau luôn cho hai kiểu khác nhau" là sai: điều quyết định là **loader thực sự định nghĩa kiểu**.

Trong Java hiện đại thường gặp bootstrap, platform, application/system loader và loader tùy biến. Với nhiều lớp nền tảng, `Class.getClassLoader()` trả `null` để biểu thị bootstrap loader; `null` không có nghĩa là lớp chưa được tải.

## 3. Thí nghiệm Java 17+: cùng bytecode, cùng tên, nhưng khác kiểu

Tạo hai file **cùng thư mục**. Ở đây dùng lớp không khai báo package để ví dụ ngắn và chạy độc lập; trong dự án thật nên dùng package có tên rõ ràng.

**File `Sample.java`**

```java
public class Sample {
    public Sample() {
    }

    public String message() {
        return "hello";
    }
}
```

**File `TypeIdentityDemo.java`**

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class TypeIdentityDemo {
    static final class CopyLoader extends ClassLoader {
        CopyLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> defineCopy(byte[] bytecode) {
            return defineClass("Sample", bytecode, 0, bytecode.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("Sample.class"));

        CopyLoader loaderA = new CopyLoader();
        CopyLoader loaderB = new CopyLoader();

        Class<?> typeA = loaderA.defineCopy(bytes);
        Class<?> typeB = loaderB.defineCopy(bytes);

        Object a = typeA.getConstructor().newInstance();
        Object b = typeB.getConstructor().newInstance();

        System.out.println("sameName=" + typeA.getName().equals(typeB.getName()));
        System.out.println("sameClass=" + (typeA == typeB));
        System.out.println("sameLoader=" + (typeA.getClassLoader() == typeB.getClassLoader()));
        System.out.println("aAcceptsOwn=" + typeA.isInstance(a));
        System.out.println("aAcceptsB=" + typeA.isInstance(b));
        System.out.println("appAcceptsA=" + Sample.class.isInstance(a));

        try {
            Sample value = (Sample) a;
            System.out.println(value.message());
        } catch (ClassCastException expected) {
            System.out.println("ClassCastException");
        }

        ClassLoader child1 = new ClassLoader(Sample.class.getClassLoader()) {};
        ClassLoader child2 = new ClassLoader(Sample.class.getClassLoader()) {};
        boolean delegatedSame = Class.forName("Sample", false, child1)
                == Class.forName("Sample", false, child2);
        System.out.println("delegatedSame=" + delegatedSame);
    }
}
```

**Biên dịch và chạy từ thư mục chứa hai file:**

```bash
javac -encoding UTF-8 Sample.java TypeIdentityDemo.java
java TypeIdentityDemo
```

**Kết quả chuẩn:**

```text
sameName=true
sameClass=false
sameLoader=false
aAcceptsOwn=true
aAcceptsB=false
appAcceptsA=false
ClassCastException
delegatedSame=true
```

**Giải thích từng bước:**

1. `javac` tạo một file `Sample.class`. Chương trình đọc đúng **một mảng byte** từ file ấy rồi đưa cùng mảng byte cho hai instance `CopyLoader`.
2. `loaderA.defineCopy` và `loaderB.defineCopy` tạo hai đối tượng `Class<?>` khác nhau. Hai class đều có binary name `Sample`, nhưng mỗi class có defining loader riêng.
3. `a` được tạo từ `typeA`; `b` được tạo từ `typeB`. Vì thế `typeA.isInstance(a)` là `true`, còn `typeA.isInstance(b)` là `false`.
4. Cú ép `(Sample) a` dùng kiểu `Sample` mà **application loader** nhìn thấy khi biên dịch và chạy `TypeIdentityDemo`. Kiểu ấy không phải `typeA`, nên JVM ném `ClassCastException`. Tên giống nhau không tạo quan hệ kế thừa hoặc khả năng cast.
5. Hai child loader ở cuối dùng `loadClass` mặc định và đều ủy quyền về application loader. `Class.forName` vì vậy trả cùng đối tượng `Class<?>`, nên `delegatedSame=true`.

Ở ví dụ này, phương thức `defineCopy` **chủ động gọi `defineClass`** để chứng minh quy tắc; nó không phải bộ nạp plugin hoàn chỉnh. Một loader dùng trong sản phẩm cần quản lý việc nạp đồng thời, cache class đã nạp, phạm vi delegation và lifecycle chính xác. Không tự gọi `defineClass` lần thứ hai với cùng binary name trong cùng defining loader: thao tác định nghĩa trùng sẽ lỗi `LinkageError`.

## 4. Vì sao JVM không thể coi chúng là một?

JVM phải bảo đảm an toàn kiểu. Hai bản class cùng tên có thể có bytecode, trường, phương thức, ý nghĩa nghiệp vụ hoặc quyền truy cập **khác nhau**. Nếu coi chúng là một chỉ vì tên giống nhau, mã của plugin này có thể nhầm đối tượng của plugin kia thành đối tượng tương thích.

Nhìn từ các phép kiểm tra kiểu:

- `typeA == typeB` hoặc `typeA.equals(typeB)`: `false` khi hai đối tượng `Class` khác nhau.
- `typeA.isInstance(objectFromB)`: `false` nếu B không phải kiểu con/kiểu thực thi tương thích với A.
- `typeA.isAssignableFrom(typeB)`: `false` nếu không có quan hệ kế thừa hoặc thực thi interface tương thích.
- Cast sang một class trùng tên nhưng khác runtime identity: thường gây `ClassCastException`.
- Reflection có thể báo lỗi tham số không tương thích khi đối tượng được tạo từ bản class khác loader; so tên hiển thị trong log không đủ để suy ra kiểu bằng nhau.
- Khi JVM phải liên kết chữ ký field/method giữa các loader và phát hiện xung đột về kiểu trong descriptor, nó còn có thể phát sinh `LinkageError` liên quan **loader constraints** (`5.3.4). Không phải mọi sai lệch loader đều biểu hiện bằng `ClassCastException`.

Một ngoại lệ quan trọng: hai class khác loader **vẫn có thể cùng implement một interface được định nghĩa ở parent chung**. Trong trường hợp đó có thể cast cả hai đối tượng sang interface chung, vì interface là một kiểu runtime thống nhất.

## 5. Runtime package, array và module

**Runtime package** cũng phụ thuộc loader: về mặt JVM, nó được xác định bởi **(package name, defining loader)**. Hai class cùng khai báo `package com.example;` nhưng do hai loader riêng định nghĩa sẽ thuộc **hai runtime package khác nhau**. Hệ quả là quyền truy cập package-private (và các kiểm tra truy cập liên quan) không thể suy ra chỉ từ tên package viết trong source. Với Java Platform Module System (JPMS), khả năng đọc module và xuất/mở package còn là những kiểm tra quyền truy cập bổ sung; tên module **không thay thế** cặp định danh kiểu nói trên.

**Array** là trường hợp đặc biệt: JVM trực tiếp tạo lớp array khi cần, và lớp array của kiểu tham chiếu gắn với defining loader của kiểu phần tử. Vì thế `Sample[]` tạo từ hai bản `Sample` khác loader cũng là hai kiểu array không tương thích. Array có phần tử primitive không gắn với loader do người dùng tạo; `int[].class.getClassLoader()` trả `null`. Các primitive như `int.class` và `void.class` không được định nghĩa bằng bytecode qua custom loader như class thông thường.

Không nên hiểu `Class.getName()` của array giống binary name của class bình thường: chẳng hạn `String[].class.getName()` là `[Ljava.lang.String;`, và `int[].class.getName()` là `[I`.

## 6. Tình huống thực tế và cách thiết kế

### Plugin và container có loader cô lập

Một application server hoặc hệ plugin có thể dùng một loader riêng cho từng plugin, version hay lần hot reload. Hai plugin cùng đóng gói `com.example.model.Event` sẽ tạo hai `Event` không tương thích nếu mỗi loader tự định nghĩa class ấy. Chuyển một instance `Event` từ plugin A sang thành phần đang kỳ vọng `Event` của plugin B dễ gây lỗi cast.

Cách thiết kế ổn định hơn là chia phần hợp đồng (API) và phần triển khai (implementation):

```text
Application loader
  +-- com.example.api.PluginApi       (shared API: định nghĩa một lần)
        ^
        |
  +-----+---------------------------+
  |                                 |
PluginLoader A                    PluginLoader B
  +-- com.example.a.PluginImpl       +-- com.example.b.PluginImpl
      implements PluginApi               implements PluginApi
```

- Đưa **API/interface/DTO cần trao đổi xuyên ranh giới** vào parent hoặc một loader chung; bảo đảm các child đều delegate phần API ấy về cùng defining loader.
- Giữ **implementation và dependency riêng** trong loader của từng plugin khi cần cô lập. Tránh đóng gói lại bản API dùng chung vào từng plugin rồi tự định nghĩa nó.
- Khi trao đổi dữ liệu giữa hai vùng loader không có kiểu chung, dùng định dạng trung lập hoặc chuyển đổi rõ ràng (ví dụ JSON) với hợp đồng dữ liệu nhất quán; không ép cast mù.
- Hot reload tạo loader mới thường đồng nghĩa với **kiểu runtime mới**. Đối tượng cũ không tự biến thành instance của phiên bản mới, kể cả class có cùng tên; cần chính sách thay thế và giải phóng tham chiếu cũ.

### Reflection, SPI và thread context class loader

`Class.forName("com.example.Plugin")` không tự bảo đảm tìm đúng loader trong hệ thống plugin. Khi cần lựa chọn loader, dùng overload `Class.forName(name, initialize, loader)` hoặc API nạp class của framework phù hợp. **Loader được truyền vào có thể ủy quyền**, nên luôn xác minh `result.getClassLoader()` khi chẩn đoán.

Một số thư viện dùng **thread context class loader** qua `Thread.currentThread().getContextClassLoader()` để tìm provider hoặc tài nguyên. Context loader là một **cơ chế lựa chọn nơi bắt đầu tìm**, không phải thành phần tự động xác định danh tính của class đã được định nghĩa. Khi đổi context loader tạm thời, phải khôi phục nó theo lifecycle thích hợp để không ảnh hưởng tác vụ khác.

## 7. Quy trình chẩn đoán khi gặp lỗi trùng tên class

Khi gặp thông báo kiểu "X cannot be cast to X" hoặc `ClassCastException` khó hiểu, làm theo thứ tự:

1. Xác định **hai đối tượng `Class<?>` thực sự** của giá trị nguồn và kiểu đích, không chỉ hai chuỗi tên từ log.
2. Ghi `getName()`, `getClassLoader()`, `getModule()` và nơi bytecode được nạp (`getProtectionDomain().getCodeSource()` nếu có). `CodeSource` hoặc đường dẫn file cho biết nguồn khả dĩ, **không quyết định** danh tính kiểu.
3. So sánh class object bằng `==`, so defining loader của hai class, sau đó kiểm tra `isInstance`/`isAssignableFrom` nếu phù hợp.
4. Vẽ đường delegation: loader nào định nghĩa API chung, loader nào định nghĩa implementation? Có JAR chứa API bị copy/shade vào plugin không? Có instance loader mới sau redeploy không?
5. Sửa tại **ranh giới nạp lớp và hợp đồng API**; đừng dùng reflection hay cast ép để che sự bất tương thích.

Đoạn hỗ trợ quan sát sau là **method minh họa**, có thể đặt vào chương trình Java đang debug (không phải file độc lập):

```java
static void describeType(Object object) {
    Class<?> type = object.getClass();
    System.out.println("name   = " + type.getName());
    System.out.println("loader = " + type.getClassLoader());
    System.out.println("module = " + type.getModule());
}
```

Với HotSpot/JDK 17+, có thể bật nhật ký tải class khi chạy:

```bash
java -Xlog:class+load=info TypeIdentityDemo
```

Log thực tế nhiều dòng và tùy bản JDK; không coi chuỗi định dạng log là giao diện ổn định. Có thể dùng `jcmd <PID> VM.classloaders` trên HotSpot/JDK hỗ trợ để kiểm tra phân cấp loader; lệnh này cần một process đang chạy. Nhật ký tải class hỗ trợ điều tra nhưng **so sánh `Class<?>` và defining loader trong cùng JVM** vẫn là phép kiểm chứng trực tiếp nhất.

## 8. Những nhầm lẫn phổ biến

| Nhận định sai | Sửa lại |
| --- | --- |
| "Hai class có cùng fully-qualified name thì luôn là một kiểu." | Tên chỉ là một nửa; còn defining loader. |
| "Hai file `.class` byte-for-byte giống nhau nên cast qua lại được." | Bytecode giống nhau không bảo đảm runtime type identity. |
| "Hai object của cùng lớp `URLClassLoader` thì tương đương." | Hai **instance** loader định nghĩa riêng vẫn tạo kiểu riêng. |
| "Gọi tải qua hai child loader thì chắc chắn được hai kiểu." | Nếu cả hai delegate cho một parent, có thể nhận cùng `Class<?>`. |
| "`getClassLoader() == null` có nghĩa class không có loader." | Với nhiều kiểu nền tảng, giá trị ấy biểu thị bootstrap loader. |
| "Hai class cùng package name luôn truy cập package-private của nhau." | Runtime package còn phụ thuộc defining loader; JPMS có kiểm tra riêng. |
| "`ClassNotFoundException` và `ClassCastException` là một vấn đề." | Một lỗi về không tìm/nạp được kiểu theo ngữ cảnh, lỗi kia về không tương thích kiểu lúc cast; cần kiểm tra riêng. |

## 9. Tự kiểm tra

1. L1 và L2 đều tải `org.demo.Api` bằng cách delegate cho cùng parent P, trong khi P là loader định nghĩa class. Hai kết quả `Class<?>` có bằng nhau không? **Có**: cùng binary name và cùng defining loader P.
2. L1 và L2 tự định nghĩa hai bản `org.demo.Api` từ **cùng một mảng byte**. Hai kết quả có bằng nhau không? **Không**: hai defining loader khác nhau.
3. Một plugin reload và tạo loader mới nhưng giữ tên class và bytecode cũ. Có được cast instance trước reload sang bản sau reload không? **Không thể suy ra là được**; nếu mỗi loader tự định nghĩa kiểu, chúng khác runtime identity.
4. Hai implementation nằm ở hai plugin loader riêng nhưng đều thực thi interface `PluginApi` do parent định nghĩa. Có thể dùng kiểu `PluginApi` để gọi cả hai không? **Có**, với điều kiện mỗi plugin thực thi đúng **cùng Class của `PluginApi`** và các điều kiện truy cập/liên kết khác đều hợp lệ.

**Ghi nhớ:** Khi hỏi "Hai class Java này có phải cùng kiểu không?", hãy hỏi **"Tên nhị phân là gì, và loader nào đã định nghĩa từng class?"**; khi thiết kế ranh giới plugin hoặc hot reload, chia sẻ API ở cùng defining loader để tránh đứt gãy danh tính kiểu.

### Tài liệu chính thức

- [JVMS Java SE 21, `5.3 Creation and Loading, `5.3.3 Arrays, `5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html)
- [Java SE 21 API: `ClassLoader`, `loadClass` và `defineClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)