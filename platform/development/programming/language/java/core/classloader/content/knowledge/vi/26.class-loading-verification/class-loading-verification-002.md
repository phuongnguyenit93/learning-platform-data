# Kiểm chứng thứ tự ủy quyền và định danh Class trong Java

Một class có tên `sample.Widget` xuất hiện ở **cả thư mục parent và thư mục child** thì Java sẽ nạp phiên bản nào? Nếu hai class loaders cùng tải `sample.Widget` từ cùng một file bytecode, hai kết quả có phải **cùng một `Class<?>`** không? Vì sao hai object có cùng tên class vẫn có thể gây `ClassCastException`?

Đây là ba câu hỏi khác nhau:

1. **Thứ tự ủy quyền (*delegation order*):** khi loader nhận yêu cầu nạp class, nó ưu tiên hỏi **parent** trước hay tự tìm trong nguồn của mình trước?
2. **Defining loader:** class thực tế được **loader nào định nghĩa** bằng hành vi JVM như `defineClass` hoặc cơ chế built-in?
3. **Định danh runtime của class:** một class không chỉ được xác định bởi binary name; theo JVMS, type identity gắn với **cặp (binary name, defining class loader)**.

Trong Java core – classloader, nhóm **Kiểm chứng hành vi**, bài này hướng dẫn kiểm chứng bằng **bằng chứng thực nghiệm**, không chỉ đoán từ classpath. Ta xây **hai phiên bản cùng binary name**, một loader parent-first mặc định, hai loaders chọn child-first có giới hạn; in nguồn method, defining loader, so `Class<?>` bằng `==`, và thử ép kiểu giữa hai namespace. Ví dụ chạy được trên **JDK 17+**, có lệnh biên dịch, stdout đã đối chiếu với kết quả thực tế, và phân tích những lỗi thiết kế thường gặp.

## 1. Quy tắc ủy quyền cần kiểm chứng

`ClassLoader.loadClass(name)` thông thường kiểm tra `findLoadedClass`, hỏi parent rồi mới gọi `findClass` của loader hiện tại. Vì vậy **parent-first** có thể trả bản `sample.Widget` từ parent, ngay cả khi child có file cùng tên. Đây là hành vi mặc định của `URLClassLoader` và `ClassLoader.loadClass`, **không phải điều kiện bắt buộc cho mọi custom loader**.

Bài này so trực tiếp parent-first với một **child-first có giới hạn theo namespace `sample.`**, thay vì đảo ưu tiên cho các lớp `java.*` hoặc shared API của host. Cách tổ chức hai JAR cùng tên từ đầu đã được minh họa ở bài fixture trước.

## 2. Defining loader và initiating loader không luôn giống nhau

Hai khái niệm theo JVMS:

- **Defining loader:** loader **đã thực sự định nghĩa** class. Runtime type identity dùng defining loader.
- **Initiating loader:** loader **khởi xướng** việc tải class, có thể tự định nghĩa hoặc delegate sang loader khác. JVM có thể ghi nhận một loader là initiating loader của class mà nó không define.

Ví dụ:

```text
Child.loadClass("sample.Widget")
            |
            v
      Parent.loadClass(...)
            |
            v
      Parent defines Widget
            |
            v
      Return Class<Widget> tới Child
```

Child có thể là initiating loader được ghi nhận, **nhưng** `Widget.class.getClassLoader()` trả **Parent** vì Parent mới là defining loader.

Điều này giải thích tại sao:

```java
Class<?> result = child.loadClass("sample.Widget");
System.out.println(result.getClassLoader() == child);
```

có thể in `false` dù **chính child đã nhận lời yêu cầu**. Đoạn trên là minh họa trong method, giả định `child` có sẵn và exception được xử lý.

Một chi tiết dễ bỏ sót: `ClassLoader.findLoadedClass(name)` không đơn thuần chỉ tìm classes do loader **tự define**; theo API Java 17, nó tìm class mà JVM đã ghi nhận loader này là **initiating loader**. Đó là lý do dùng `findLoadedClass` để chống định nghĩa trùng trong custom implementation, nhưng không được suy mọi kết quả nó trả đều do loader này define.

## 3. Định danh class khi đổi delegation policy

JVM phân biệt type bằng **(binary name, defining loader)**. Nếu `sample.Widget` do parent định nghĩa và được child trả về sau khi ủy quyền, `child.loadClass(...).getClassLoader()` là **parent**. Nếu custom child-first thực sự định nghĩa một bản cùng tên, hai `Class<?>` khác nhau dù cùng `getName()`; `Class.isInstance` và `Class.cast` cho thấy chúng không hoán đổi được.

Package name dạng chuỗi cũng chưa đủ làm hai classes thuộc cùng **runtime package**: defining loader khác nhau có thể thay đổi access control với package-private. Bài riêng về **Kiểm chứng package-private khi dùng hai loader** có thí nghiệm `IllegalAccessError`.

## 4. Tạo thí nghiệm: parent và child có class cùng tên, bytecode khác nhau

Ta viết:

**Bản ở parent:**

```java
package sample;

public class Widget {
    public String origin() {
        return "PARENT";
    }
}
```

**Bản ở child:**

```java
package sample;

public class Widget {
    public String origin() {
        return "CHILD";
    }
}
```

Cả hai có cùng binary name `sample.Widget`, cùng public method `origin():String`, nhưng phần thân method cố ý trả về giá trị khác để **quan sát class nào được thực thi**.

Không compile hai file trên trong **cùng một source directory** vì sẽ có duplicate class definition. Ta biên dịch riêng parent/child vào hai output directories, rồi host tạo loaders bằng `URLClassLoader`.

### Cấu trúc project

```text
delegation-lab/
├── src-parent/
│   └── sample/
│       └── Widget.java          # trả "PARENT"
├── src-child/
│   └── sample/
│       └── Widget.java          # trả "CHILD"
├── src-host/
│   └── VerifyDelegation.java
├── parent-classes/              # output riêng của parent
├── child-classes/               # output riêng của child
└── host-classes/                # output của application host
```

Tạo ba thư mục output trước khi chạy lệnh. Host **không import trực tiếp `sample.Widget`**, nên có thể compile độc lập với hai bản. Khi chạy, chỉ đưa `host-classes` vào application classpath; nếu thêm parent/child output vào `-cp` của host, kết quả có thể bị thay đổi do system loader định nghĩa class trước.

## 5. Host tạo loader mặc định và loader child-first có giới hạn

File `src-host/VerifyDelegation.java` (độc lập, có thể biên dịch với JDK 17+):

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class VerifyDelegation {

    static final class SelectiveChildFirst extends URLClassLoader {
        SelectiveChildFirst(
                String name, URL[] urls, ClassLoader parent) {
            super(name, urls, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {

            // Chỉ đảo thứ tự với namespace ứng dụng chủ động sở hữu.
            if (!name.startsWith("sample.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> c = findLoadedClass(name);

                if (c == null) {
                    try {
                        c = findClass(name);       // Child thử trước.
                    } catch (ClassNotFoundException missing) {
                        c = super.loadClass(name, false); // Fallback.
                    }
                }

                if (resolve) {
                    resolveClass(c);
                }
                return c;
            }
        }
    }

    static Object create(Class<?> type) throws Exception {
        return type.getConstructor().newInstance();
    }

    static String origin(Class<?> type, Object instance)
            throws Exception {
        return (String) type.getMethod("origin").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL[] parentUrls = {
            Path.of("parent-classes").toUri().toURL()
        };
        URL[] childUrls = {
            Path.of("child-classes").toUri().toURL()
        };

        try (URLClassLoader parent = new URLClassLoader(
                     "parent", parentUrls,
                     ClassLoader.getPlatformClassLoader());

             URLClassLoader normal = new URLClassLoader(
                     "normal", childUrls, parent);

             SelectiveChildFirst first = new SelectiveChildFirst(
                     "child-first-A", childUrls, parent);

             SelectiveChildFirst second = new SelectiveChildFirst(
                     "child-first-B", childUrls, parent)) {

            Class<?> p = parent.loadClass("sample.Widget");
            Class<?> n = normal.loadClass("sample.Widget");
            Class<?> a = first.loadClass("sample.Widget");
            Class<?> b = second.loadClass("sample.Widget");

            System.out.println("normal chose parent=" + (n == p));
            System.out.println("normal defining loader="
                    + n.getClassLoader().getName());
            System.out.println("normal origin="
                    + origin(n, create(n)));

            System.out.println("child-first chose child=" + (a != p));
            System.out.println("child-first defining loader="
                    + a.getClassLoader().getName());
            System.out.println("child-first origin="
                    + origin(a, create(a)));

            System.out.println("same binary name="
                    + a.getName().equals(b.getName()));
            System.out.println("distinct Class objects=" + (a != b));

            System.out.println("repeat stable="
                    + (first.loadClass("sample.Widget") == a));

            System.out.println("bootstrap String="
                    + (first.loadClass("java.lang.String")
                        == String.class));

            try {
                a.cast(create(b));
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast="
                        + expected.getClass().getSimpleName());
            }
        }
    }
}
```

Đọc kỹ các quyết định:

- `parent` có URLs trỏ tới `parent-classes` và parent là **platform loader**.
- `normal` có URLs trỏ `child-classes` nhưng **parent = parent loader**. Đây là một `URLClassLoader` bình thường, không override `loadClass`, nên hành vi parent-first.
- `first` và `second` đều dùng các bytes ở `child-classes`, nhưng là **hai objects loader độc lập**, mỗi instance có name riêng.
- `SelectiveChildFirst` chỉ đảo thứ tự cho những binary names bắt đầu bằng `sample.`. Các tên ngoài namespace ấy, bao gồm `java.lang.String`, vẫn đi qua default parent-first.
- `findLoadedClass` kiểm tra trước khi define lại, tránh trùng định nghĩa `sample.Widget` trong cùng initiating namespace.
- `getClassLoadingLock(name)` bảo vệ đường load khi nhiều threads yêu cầu cùng class. Java ClassLoader có những ràng buộc đồng bộ/parallel capable; đoạn này phục vụ demo, **không tự được xem như fully production-safe parallel loader**.
- `findClass` được thử **trước** parent đối với `sample.`; chỉ khi child không có file mới gọi `super.loadClass(name, false)`.
- `resolveClass(c)` được gọi khi `resolve` được yêu cầu; method này không chạy `static initializer` như `Class.forName(name, true, loader)`.

**Lưu ý về fallback:** không bao `LinkageError`/`ClassFormatError`/`SecurityException` vào catch rồi âm thầm thử parent. Đoạn demo chỉ bắt `ClassNotFoundException`, vì **file không tồn tại ở child** là tình huống fallback hợp lý; bytes bị hỏng, package sai, tên không khớp hoặc bytecode có vấn đề là lỗi cần xử lý, không phải “coi như child không có class”.

## 6. Biên dịch và chạy

Từ thư mục `delegation-lab`:

```bash
javac --release 17 -d parent-classes src-parent/sample/Widget.java
javac --release 17 -d child-classes src-child/sample/Widget.java
javac --release 17 -d host-classes src-host/VerifyDelegation.java
java -cp host-classes VerifyDelegation
```

Các lệnh không chứa nhiều classpath entries nên giống nhau trên Windows/Linux/macOS.

Stdout **đã kiểm chứng sau khi compile với `javac --release 17` và chạy JVM**:

```text
normal chose parent=true
normal defining loader=parent
normal origin=PARENT
child-first chose child=true
child-first defining loader=child-first-A
child-first origin=CHILD
same binary name=true
distinct Class objects=true
repeat stable=true
bootstrap String=true
cross-loader cast=ClassCastException
```

Kết quả này **không phải suy đoán**: host đã được biên dịch độc lập, class parent và child được compile thành hai outputs khác nhau, JVM đã chạy và stdout khớp.

### Thử nghiệm A: parent-first chọn class của parent

```text
normal.loadClass("sample.Widget")
      |
      +-- parent.loadClass(...) -> sample.Widget từ parent-classes
      |
      +-- normal.findClass(...) KHÔNG CẦN GỌI
```

Các dòng:

```text
normal chose parent=true
normal defining loader=parent
normal origin=PARENT
```

chứng minh `normal.loadClass` trả **chính `Class<?>` do parent define**. Parent loader trỏ tới code trả `PARENT`, dù child cũng có `sample.Widget.class` trả `CHILD`.

**Không nói normal “nạp cả hai bản rồi chọn bản parent”.** Nó trả class mà parent đã tìm, không cần tự define bản child.

### Thử nghiệm B: child-first chọn class của child

```text
first.loadClass("sample.Widget")
      |
      +-- first.findLoadedClass(...) -> null lần đầu
      |
      +-- first.findClass(...) -> sample.Widget từ child-classes
      |
      +-- không cần fallback sang parent
```

Các dòng:

```text
child-first chose child=true
child-first defining loader=child-first-A
child-first origin=CHILD
```

chứng minh `first` tự định nghĩa `sample.Widget` mặc dù parent có class cùng tên.

### Thử nghiệm C: hai loader child-first độc lập định nghĩa hai types

```text
first  -> sample.Widget (child-first-A)
second -> sample.Widget (child-first-B)

getName() đều "sample.Widget"
Class<?> identity khác nhau
```

Dòng:

```text
same binary name=true
distinct Class objects=true
```

đặt **bằng chứng trực tiếp** cho JVMS runtime identity. **Cùng đường dẫn `child-classes` và cùng class-file bytes** không hợp nhất hai class đã được hai loader khác nhau define.

### Thử nghiệm D: cache/ổn định trong cùng một loader

```text
repeat stable=true
```

Lần thứ hai `first.loadClass("sample.Widget")` trả **cùng `Class<?>`**. Một loader hoạt động đúng không được tự ý liên tục define class mới cùng binary name trong cùng namespace; JVM có ràng buộc và có thể phát `LinkageError: attempted duplicate class definition` nếu subclass gọi `defineClass` trùng.

### Thử nghiệm E: không đảo thứ tự platform classes

```text
bootstrap String=true
```

Vì child-first policy chỉ áp dụng `sample.`, `java.lang.String` dùng default delegation. `String.class` thường do bootstrap loader định nghĩa, và `Class.getClassLoader()` của bootstrap-defined class biểu diễn bằng `null`.

Dòng này **không chứng minh mọi loader platform luôn parent-first**; nó chứng minh **policy do ví dụ viết** tránh tự define `java.*` hoặc can thiệp class nền tảng.

### Thử nghiệm F: ép kiểu chéo dẫn đến lỗi

```text
cross-loader cast=ClassCastException
```

Trong demo, `a` là `sample.Widget` do loader A define; object `create(b)` thuộc `sample.Widget` do loader B define. `a.cast(objectOfB)` ném `ClassCastException` dù source-level tên class giống nhau. Đây là lỗi **type identity**, không phải tên class viết sai.

**Không chữa bằng cách cast qua `Object` rồi cast lại**; object vẫn thuộc type của loader B. Cần giao tiếp qua contract/interface chung hoặc serialize dữ liệu sang DTO/API boundary phù hợp.

## 7. Bằng chứng mạnh hơn: Class object, loader, CodeSource và resource

Một phương pháp kiểm chứng đầy đủ gồm:

| Quan sát | API/lệnh | Giúp xác nhận |
| --- | --- | --- |
| Binary class name | `clazz.getName()` | Hai class có cùng tên hay không |
| Defining loader | `clazz.getClassLoader()` | **Ai định nghĩa** runtime class |
| Loader name | `clazz.getClassLoader().getName()` | Nhận diện loader đã đặt tên (không phải unique ID) |
| Class identity | `clazzA == clazzB` | Hai references có cùng `Class<?>` object không |
| Object/type identity | `clazzA.isInstance(objectB)`, `clazzA.cast(objectB)` | Instance của type A hay B |
| Origin behavior | Reflective invoke `origin()` | Bytecode đã chọn chạy bản parent hay child |
| Parent chain | `loader.getParent()` | Quan hệ delegation, **không phải inheritance** |
| Code source | `clazz.getProtectionDomain().getCodeSource()` | Nơi class binary có thể đến (nếu runtime cung cấp) |
| JVM class load | `-Xlog:class+load=info` trên HotSpot | Dòng load, loader/source khi có |
| Loader hierarchy | `jcmd PID VM.classloaders` | Parent tree trong JVM chạy thật |

Trong example, `getClassLoader().getName()` dễ quan sát vì constructors đặt tên `parent`/`child-first-A`/`child-first-B`. Tuy nhiên **name của loader không phải global unique identifier**: hai instance `URLClassLoader` có thể được đặt cùng name. Muốn biết có thực sự là một loader, so **object identity** của loader bằng `==`.

### In CodeSource khi cần điều tra JAR precedence

Một đoạn code minh họa:

```java
Class<?> type = first.loadClass("sample.Widget");

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource source =
        pd == null ? null : pd.getCodeSource();

System.out.println(
        source == null ? "<unknown>" : source.getLocation());
```

Đây **không phải file biên dịch độc lập**, giả định `first` đã được tạo và method xử lý `ClassNotFoundException`. Với URLClassLoader thông thường, location có thể là file URL của `child-classes`; với bootstrap, byte-array loader, generated class hoặc một số custom loader, CodeSource có thể `null`.

**Không suy từ URL path duy nhất rằng class đã được nạp:** resource `getResource("sample/Widget.class")` có thể đọc file từ URL, nhưng class resolution có thể delegate và chọn class của loader khác.

## 8. Đổi parent-first sang child-first trong ứng dụng thật: khi nào nên làm?

Child-first có thể hữu ích khi plugin cần dùng phiên bản implementation dependency riêng, ví dụ hai plugin cùng dùng hai phiên bản thư viện JSON. Nhưng **không child-first mọi package**.

Thiết kế thường gặp:

```text
Host/System loader
  +-- api.Plugin
  +-- api.Message
  +-- shared interfaces, DTOs và framework contracts
          ^
          | parent-first (bắt buộc thống nhất shared API identity)
          |
Plugin loader A
  +-- plugin.impl.*
  +-- private dependencies version A
          ^
          |
Plugin loader B
  +-- plugin.impl.*
  +-- private dependencies version B
```

Trong mô hình đúng:

- **`java.*` và platform API:** để runtime/platform loader phụ trách; không tìm cách tự define.
- **`api.*` shared contracts:** parent-first để host và plugin cùng nhận **một `Class<?>`**.
- **`plugin.*` hoặc namespace tư hữu:** có thể áp dụng child-first có giới hạn để tránh parent che class phiên bản plugin.
- **Native libraries/JNI:** có lifecycle/loader restrictions riêng; child-first không tự cô lập native state trong cùng process.
- **JPMS named modules:** còn phải xét module resolution, exports/opens/readability; chỉ đảo classpath search không vượt được JPMS access controls.
- **Security:** classloader isolation **không phải sandbox** đủ để chạy bytecode không tin cậy.

Nếu parent đã define `api.Plugin` và child lại tự define `api.Plugin` bằng child-first, object implementation của child có thể **không cast được** sang interface host mặc dù cùng fully qualified name. Vì vậy allowlist child-first phải chừa namespace shared API.

## 9. Một custom loader an toàn cần chú ý điều gì?

Trong ví dụ `SelectiveChildFirst`, đoạn quan trọng:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> result = findLoadedClass(name);
    if (result == null) {
        try {
            result = findClass(name);
        } catch (ClassNotFoundException missing) {
            result = super.loadClass(name, false);
        }
    }
    if (resolve) resolveClass(result);
    return result;
}
```

Đây là **đoạn trích** của file `VerifyDelegation.java`, không phải chương trình độc lập.

Các yêu cầu thiết kế:

1. **Tránh duplicate define:** kiểm tra `findLoadedClass` trước khi gọi `findClass`/`defineClass`.
2. **Dùng lock đúng:** `getClassLoadingLock(name)` liên quan concurrency; chú ý `registerAsParallelCapable` nếu muốn parallel capable loader và hiểu ràng buộc JVM cho loader hierarchy.
3. **Đừng child-first `java.*`:** loader không được tự define classes thuộc restricted `java.*` package, và có thể tạo xung đột nghiêm trọng với platform classes.
4. **Giữ shared API parent-first:** tránh tạo hai runtime interfaces cùng tên.
5. **Fallback chỉ khi class không tìm thấy:** không nuốt `LinkageError`/`SecurityException` và dùng parent sai phiên bản một cách âm thầm.
6. **Giữ cùng object class cho cùng binary name trong cùng loader:** không define trùng trong một loader.
7. **Quản lý `Package`:** custom loader dùng `defineClass` phải tuân protection domain, package definition/sealing và các ràng buộc classloader.
8. **Quản lý lifecycle:** `URLClassLoader.close()` không unload class ngay; tránh đóng trong lúc còn task lazy-load class/resource.
9. **Giữ debugging information:** đặt loader name, log binary name, selected defining loader và source khi phù hợp.
10. **Rà class dependencies:** type được child define có thể phụ thuộc class do parent define, nên phải bảo đảm loader constraints và version compatibility.

### Về resolveClass

`resolveClass(c)` **liên kết** class theo định nghĩa ClassLoader API; nó không bảo đảm mọi referenced class đã được resolve hoặc static initializer đã chạy theo thứ tự mà application suy đoán. Không thay `resolveClass` bằng lời gọi `Class.forName(name, true, loader)` một cách tùy tiện trong override `loadClass`, vì điều đó đổi thời điểm initialization và dễ sinh recursion/side effects.

### Về lỗi name mismatch

Nếu custom loader tự đọc bytes và gọi:

```java
defineClass("sample.Widget", bytes, 0, bytes.length);
```

thì bytes phải biểu diễn class có binary name phù hợp. Nếu chứa `sample.Other` hoặc package không hợp lệ, JVM có thể ném `NoClassDefFoundError`/linkage error. Với `URLClassLoader.findClass` trong demo, Java xử lý file lookup và định nghĩa theo quy tắc URL source.

## 10. Resource lookup cần một phép thử riêng

`loadClass` xác định một runtime class; `getResource` và `getResources` tìm một hay nhiều URL tài nguyên, còn `META-INF/services` có thể chứa nhiều provider descriptors. Custom child-first class lookup **không tự động đổi** chính sách resource lookup nếu không override các phương thức liên quan. Bài về resource/SPI thực hành toàn bộ chuỗi lookup và instantiation; ở đây chỉ kết luận về class identity từ `loadClass`.

## 11. Cách tự kiểm chứng class identity bằng reflection

Trong ví dụ chính:

```java
Class<?> a = first.loadClass("sample.Widget");
Class<?> b = second.loadClass("sample.Widget");

System.out.println(a.getName());
System.out.println(b.getName());
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
```

Đây là **đoạn minh họa** thêm vào method `main` khi `first`/`second` tồn tại. Output kỳ vọng:

```text
sample.Widget
sample.Widget
false
false
```

So sánh:

- `getName()` chỉ kiểm tra binary names.
- `==` so `Class<?>` objects đúng runtime identity.
- `getClassLoader()` so defining-loader identity.
- `Class.getModule()` còn thêm góc nhìn Java 9+ về named/unnamed modules, nhưng module name không thay JVM pair binary name + defining loader.

### ClassCastException và reflection

```java
Object fromB = b.getConstructor().newInstance();
System.out.println(a.isInstance(fromB));
Object fromA = a.cast(fromB);
```

Đoạn minh họa trên sẽ in `false` rồi ném `ClassCastException`, nên dòng `Object fromA = ...` không hoàn thành. Không phải vì constructor trả object sai, mà vì A và B là **hai types runtime riêng**.

Nếu cần host giao tiếp với hai plugin implementations, định nghĩa interface `api.Plugin` ở parent rồi cho cả hai class child implement **chính interface parent**. Khi đó host có thể cast về `api.Plugin` mà không đòi hai implementation classes giống hệt nhau.

## 12. Phải chỉ rõ loader ở bước dùng reflection

`Class.forName(name, false, loader)` cho phép chọn loader cụ thể khi tìm type mà chưa yêu cầu initialization. Thay Thread Context ClassLoader (TCCL) **không tự đổi** defining loader mà overload một đối số `Class.forName(name)` sử dụng theo quy tắc caller. Với plugin cần tra `sample.Widget` của child, truyền đúng child loader và xác minh `type.getClassLoader()`; xem bài kiểm chứng `loadClass`/`forName` cho stdout tương ứng.

## 13. Những lỗi hay gặp khi quan sát kết quả

| Triệu chứng | Nguyên nhân có thể | Phép kiểm tra đúng |
| --- | --- | --- |
| Mong chọn CHILD nhưng in PARENT | Loader vẫn parent-first và parent có cùng class name | `clazz.getClassLoader()`, `origin()` và parent URL |
| Mong parent-first nhưng in CHILD | Parent không thấy class hoặc loader override `loadClass` | Parent `loadClass` trực tiếp và inspect policy |
| Hai loaders trả cùng `Class<?>` | Cả hai delegate về cùng parent defining loader | `clazzA == clazzB` và `getClassLoader()` |
| Hai loaders dùng cùng file nhưng trả class khác | Hai loaders **tự define** cùng binary name | `getName()` giống, `==` false, defining loader khác |
| `ClassCastException` dù tên class giống | Runtime class identity khác nhau | Shared parent interface hoặc cùng defining loader |
| `LinkageError: duplicate class definition` | Loader định nghĩa lại cùng name | `findLoadedClass` và locking trước `defineClass` |
| `NoClassDefFoundError` cho dependency | Child class được define nhưng dependency không tìm được hoặc initialization trước đó lỗi | Stack trace, runtime path và loader của caller |
| `NoSuchMethodError` giữa plugin/host | Version skew với shared API, parent che bản mới | Bytecode descriptors, defining loader và CodeSource |
| `IllegalAccessError` package-private | Tên package giống nhưng runtime package khác do loader | Package + defining loader, module access |
| `getResource` trả config của parent | Resource delegation khác policy class | In resource URL và loader lookup |
| Lỗi chỉ xảy ra khi callback chạy | TCCL/caller loader hoặc dependency load muộn | In loader/context tại callback |
| Sau `close()` class đã nạp vẫn chạy | Close không tương đương class unloading | Resource/lifecycle check, không suy từ method call |

Cần phân biệt **ClassNotFoundException** khi một API gọi `loadClass` không thấy binary name với **NoClassDefFoundError** lúc VM resolve dependency thiếu/initialization fail, và **ClassCastException** khi hai runtime types không tương thích. Ba lỗi này không thể chữa cùng một cách.

## 14. Không bỏ quên khóa class loading

Trong custom loader override `loadClass(name, resolve)`, việc kiểm tra `findLoadedClass` và `findClass` phải giữ vùng tới hạn thích hợp (`getClassLoadingLock(name)`). Nếu hai thread cùng tự `defineClass` cho một binary name trong **cùng loader**, lần định nghĩa trùng có thể bị `LinkageError`. Bài **Kiểm chứng nạp đồng thời và xử lý tên lớp trùng** dành riêng cho parallel-capable, per-name locks và bài thử dùng latch.

## 15. Chẩn đoán bằng JVM tools ngoài printf

Khi code đã chạy trong server lớn và không tiện in debug ở mọi điểm, có thể dùng:

**HotSpot class loading log:**

```bash
java -Xlog:class+load=info -cp host-classes VerifyDelegation
```

Tìm `sample.Widget` trong log. Dòng load có thể cho biết source/loader tùy runtime/logging level. Cảnh báo: source chỉ cho biết nơi bytecode đến nếu được báo; nó không thay phép so defining loader trong code.

**jcmd class loader tree:**

```bash
jcmd <PID> VM.classloaders
jcmd <PID> VM.classloaders show-classes=true fold=false
```

Thay `<PID>` bằng PID thật của JVM đang chạy, ví dụ từ `ProcessHandle.current().pid()`. Ví dụ main rất ngắn có thể kết thúc trước khi `jcmd` attach; nếu muốn thử, dùng server chạy lâu hoặc thêm khoảng chờ có chủ đích **trong mã test**.

**jcmd statistics/hierarchy:**

```bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.class_hierarchy sample.Widget
```

- `VM.classloader_stats` giúp nhìn số class và loader-data.
- `VM.class_hierarchy` hiển thị **class inheritance**, không phải parent delegation.
- `VM.classloaders` mới là **parent loader hierarchy**.
- Cùng tên class nhưng do loader khác định nghĩa có thể gắn với `ClassLoaderData` khác trong diagnostics.

**`javap`** đọc class files trên đĩa, không đo trực tiếp JVM lựa chọn class version nào. Khi nghi `NoSuchMethodError` hay API mismatch, phối hợp `javap -s -p` trên các **binaries được runtime thực sự nạp** với `CodeSource` và classloading logs.

## 16. Bài tập thực hành có hướng giải

### Bài 1 — Chuyển normal loader sang platform parent trực tiếp

Thay:

```java
new URLClassLoader("normal", childUrls, parent)
```

bằng:

```java
new URLClassLoader(
        "normal", childUrls, ClassLoader.getPlatformClassLoader())
```

Đây là **đoạn minh họa thay constructor**, không phải chương trình hoàn chỉnh. Vì platform loader **không có `sample.Widget` trong thí nghiệm**, URLClassLoader `normal` có thể tự tìm bản CHILD khi parent lookup thất bại. **Parent-first vẫn là parent-first**, chỉ khác parent không có class cần tìm.

Bài học: “Kết quả origin=CHILD” **không đủ để suy classloader là child-first**; còn phải kiểm tra parent có cùng class và chính sách lookup.

### Bài 2 — Loại file class child

Giữ normal và child-first loaders nhưng bỏ `child-classes/sample/Widget.class` trước khi chạy (đảm bảo parent còn bản PARENT).

Kết quả kỳ vọng: `SelectiveChildFirst.findClass` không tìm thấy child, bắt `ClassNotFoundException` rồi fallback parent, trả bản **PARENT**. Bài học: child-first cũng có thể trả class của parent.

**Đây là bài tập dự đoán có điều kiện**, không phải stdout chính của demo đã kiểm chứng; khi bỏ child file, những so sánh trong main như `child-first chose child`/`cross-loader cast` cũng thay đổi.

### Bài 3 — Đặt shared API ở parent

Tạo `api.Plugin` interface trong parent output, rồi để hai child implementations khác nhau implement API đó. Kiểm tra:

```java
api.Plugin.class.isAssignableFrom(pluginAClass)
api.Plugin.class.isAssignableFrom(pluginBClass)
```

Đây là **biểu thức minh họa**, giả định đã tạo `api.Plugin` trong classpath/loader phù hợp. Nếu implementations delegate `api.Plugin` về cùng defining loader parent, cả hai assignable; nếu child tự define bản sao API, có thể không assignable với `api.Plugin.class` của host.

### Bài 4 — Không dùng `getName()` để quyết định identity

In:

```java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
```

Trong ví dụ chính, dòng đầu `true`, dòng sau `false`. Mục tiêu là nhắc rằng **class name equality ≠ class identity**.

### Bài 5 — Tạo loader mới từ cùng thư mục

Sau khi loader A và B đóng, tạo một loader C cũng trỏ `child-classes`. C có thể tự define thêm một `sample.Widget` thứ ba. Không suy rằng `URLClassLoader.close()` của A/B đã unload type cũ; class unloading phụ thuộc reachability/GC và không diễn ra ngay.

## 17. Những hiểu lầm cần tránh

| Phát biểu sai | Đính chính |
| --- | --- |
| “Child gọi loadClass nghĩa child nhất định define class.” | Sai. Parent có thể define class rồi trả về. |
| “Nếu class file nằm trong child directory thì child sẽ ưu tiên bản ấy.” | Không khi parent-first và parent có class trùng tên. |
| “Hai `Class<?>` có cùng `getName()` chắc chắn là một type.” | Sai. Cần xét defining loader. |
| “Hai loaders đọc cùng bytes thì JVM coi là cùng class.” | Sai nếu cả hai tự define class. |
| “Một loader có thể define lại cùng binary name mỗi lần gọi.” | Sai; duplicate definition có thể phát `LinkageError`. |
| “TCCL làm Class.forName(String) tự dùng child loader.” | Sai; overload một tham số dùng caller defining loader. |
| “ClassLoader.getResource và loadClass chắc chắn cùng thứ tự.” | Không, resource lookup policy cần xét độc lập. |
| “`resolveClass` chạy static initializer.” | Không; linking khác class initialization. |
| “Package names bằng nhau đồng nghĩa package-private access xuyên loaders.” | Sai; runtime package còn phụ thuộc defining loader. |
| “ClassCastException giữa plugins là do compiler không hiểu tên package.” | Không; type identity trong JVM có loader component. |
| “Chỉ cần bật child-first cho mọi package sẽ sửa dependency conflicts.” | Có thể phá shared API/platform classes và gây linkage errors. |
| “Đóng URLClassLoader là xoá Class identity cũ ngay.” | Không; JVM có thể còn giữ loader/class/instances. |

## 18. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Trong demo, cả parent và child đều có `sample.Widget`. Vì sao `normal` chọn bản PARENT?

**Đáp án:** `normal` là `URLClassLoader` mặc định theo parent-first. Nó delegate `parent.loadClass` trước và nhận class do parent define; vì vậy không cần `normal.findClass`.

**Câu 2.** Vì sao `first` chọn CHILD dù parent có class cùng tên?

**Đáp án:** `SelectiveChildFirst` override `loadClass` cho namespace `sample.`, gọi `findClass` ở child trước rồi chỉ fallback parent nếu child không có class.

**Câu 3.** `a.getName().equals(b.getName())` trả true, `a == b` trả false. Mâu thuẫn không?

**Đáp án:** Không. Cùng binary name nhưng defining loaders khác nhau, nên đó là hai runtime types riêng theo JVMS.

**Câu 4.** `a.cast(objectOfB)` ném lỗi gì và vì sao?

**Đáp án:** `ClassCastException`, vì objectOfB có runtime class được loader B define, không phải `Class<?> a` của loader A.

**Câu 5.** Initiating loader khác defining loader thế nào?

**Đáp án:** Initiating loader khởi xướng việc nạp (có thể delegate); defining loader thực sự định nghĩa type. Runtime identity dựa defining loader.

**Câu 6.** Vì sao gọi `first.loadClass("sample.Widget")` lần hai trả lại class cũ?

**Đáp án:** Loader duy trì namespace/ghi nhận class đã load, và implementation kiểm tra `findLoadedClass` trước khi define. Điều đó tránh duplicate definition cùng binary name trong một loader.

**Câu 7.** Vì sao chỉ in method `origin()` không đủ để xác minh loader policy?

**Đáp án:** Nếu parent không có class, ngay cả loader parent-first cũng fallback child và in CHILD. Cần thử với **hai bản cùng tên** ở cả parent và child, đồng thời in defining loader.

**Câu 8.** Nếu hai plugins cần giao tiếp với host qua `api.Plugin`, nên define API ở đâu?

**Đáp án:** Ở parent/shared loader, để host và plugin nhận **cùng runtime interface type**. Implementation riêng ở child loaders vẫn có thể khác nhau.

**Câu 9.** `Class.getClassLoader() == null` thường biểu thị điều gì?

**Đáp án:** Class do bootstrap loader định nghĩa (ví dụ `String` trong JVM thông dụng). Nó không có nghĩa class không tồn tại hoặc bị unload.

**Câu 10.** Dùng `VM.class_hierarchy` để đọc parent loader chain đúng không?

**Đáp án:** Không. Nó là class inheritance hierarchy; parent loader tree xem bằng `VM.classloaders`.

**Câu 11.** Tại sao `findLoadedClass` và locking cần có khi override `loadClass`?

**Đáp án:** Tránh nạp/định nghĩa lặp cùng binary name và race giữa nhiều threads. Cần hiểu parallel-capable loader rules nếu muốn triển khai concurrent production.

**Câu 12.** `Class.forName("sample.Widget")` trong host helper có chắc dùng loader child-first đang nằm ở TCCL?

**Đáp án:** Không. Overload một tham số dùng defining loader của host caller; muốn dùng loader cụ thể, truyền vào overload ba tham số.

**Câu 13.** Nếu `a.getClassLoader() != b.getClassLoader()` thì chắc `a != b` với class bình thường không?

**Đáp án:** Có, vì một runtime class có defining loader xác định; hai defining loader khác nhau thì không cùng một runtime class definition.

**Câu 14.** Loader child-first có thể fallback parent được không?

**Đáp án:** Có. Child-first chỉ thay đổi **ưu tiên**; nếu child không tìm thấy, implementation có thể hỏi parent, như demo `SelectiveChildFirst`.

## 19. Checklist kiểm chứng trên dự án thực

1. **Tạo hai bản cùng binary name** ở parent/child outputs độc lập để phân biệt thứ tự.
2. **Kiểm tra runtime classpath của host** không vô tình chứa cả hai bản qua application loader.
3. **In loader parent** bằng `getParent()` và xác nhận URL của parent/child.
4. **In `getClassLoader()` của kết quả**, không chỉ name của loader nhận yêu cầu.
5. **So `Class<?>` bằng `==`** khi đánh giá class identity.
6. **Gọi method khác output** giữa hai bản để chứng minh bytes phiên bản nào được thực thi.
7. **Lặp `loadClass`** để kiểm tra reuse, không duplicate define.
8. **Kiểm tra namespace allowlist** cho child-first, giữ shared API/platform parent-first.
9. **Dùng reflection `Class.cast` / `isInstance`** khi muốn chứng minh tách types.
10. **Xem CodeSource và classloading logs** khi điều tra JAR/classpath precedence.
11. **Đọc `ClassLoader.loadClass` contract** trước khi override và không bắt nhầm linkage errors làm fallback.
12. **Kiểm tra TCCL riêng** nếu framework/SPI dùng context lookup.
13. **Phân biệt `load`, `link`, `initialize`**, không suy static initializer chạy chỉ vì `loadClass`.
14. **Không hiểu `getResource` như bằng chứng class đã define**; resource policy có thể khác.
15. **Trong plugin thực tế**, giữ loader mở trong suốt lifecycle cần lazy loading và cleanup callbacks/tasks trước close.
16. **Khi dùng JPMS**, bổ sung module exports/opens/readability vào phân tích.
17. **Kiểm thử concurrent loading** và classloader constraints nếu viết custom loader production.
18. **Ghi kết quả có kiểm chứng**: tên class, loader object, defining loader, origin output, equality/cast và runtime version.

## Kết luận

**Thứ tự ủy quyền** quyết định **loader nào có cơ hội tìm class trước**, còn **định danh runtime của `Class<?>`** phụ thuộc **binary name + defining loader**. Trong thí nghiệm, loader `normal` parent-first trả đúng class của `parent`; loader `child-first-A` tự define bản CHILD; hai loaders child-first khác nhau tự define **hai runtime types** dù cùng tên, và ép kiểu chéo phát `ClassCastException`.

Muốn kiểm chứng đúng, không chỉ dựa vào một dòng `System.out.println(clazz.getName())`. Hãy kiểm tra **parent chain → loader policy → defining loader → `Class<?>` equality → method origin → instance assignability**. Đây cũng là nền tảng để thiết kế plugin isolation mà vẫn chia sẻ ổn định interfaces giữa host và plugins.

**Tài liệu chính thức Java 17:**

- [ClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — `loadClass`, `findLoadedClass`, `findClass`, `getClassLoadingLock`, parent delegation và loader name.
- [URLClassLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html) — URL classpath, constructors named loader, `close`.
- [JVMS 17 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3) — defining/initiating loader, runtime type identity, loader constraints.
- [JLS 17 12 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html) — loading, linking, initialization, unloading.
- [Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `getName`, `getClassLoader`, `cast`, `isInstance`.
