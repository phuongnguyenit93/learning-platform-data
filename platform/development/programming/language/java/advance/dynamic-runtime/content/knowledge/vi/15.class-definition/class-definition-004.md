# 15.4 Quyền full-privilege Lookup và kiểm soát cờ initialize

Java cho phép một framework tạo lớp trực tiếp từ bytecode trong runtime bằng `MethodHandles.Lookup`. Tuy nhiên, việc **định nghĩa một hidden class** trong module của caller không phải thao tác mà mọi `Lookup` đều được làm: `Lookup.defineHiddenClass(...)` và `defineHiddenClassWithClassData(...)` đòi hỏi **full-privilege access**. Đồng thời, đối số `boolean initialize` cho phép quyết định có **khởi tạo lớp ngay khi định nghĩa** hay trì hoãn đến một hoạt động chủ động về sau.

Hai vấn đề phải được suy nghĩ **độc lập**:

1. **Ai có quyền đưa một lớp mới vào runtime package/module này?** Đây là vấn đề danh tính, quyền truy cập và giới hạn của `Lookup`.
2. **Khi nào các static initializers và static field initializers của lớp mới được chạy?** Đây là vấn đề vòng đời *class initialization*, không phải quyền truy cập.

Bài học nằm trong chủ đề **15. Định nghĩa lớp**, áp dụng cho Java 17+. Nội dung bao gồm `hasFullPrivilegeAccess()`, `lookupModes()`, `PRIVATE`/`MODULE`/`ORIGINAL`, `defineHiddenClass`, `defineHiddenClassWithClassData`, so sánh với `defineClass`, cờ `initialize`, `ensureInitialized`, các lựa chọn `NESTMATE`/`STRONG`, nguyên tắc module, lỗi và bảo mật. Ba ví dụ Java 17 có thể biên dịch và chạy; mỗi ví dụ đều có output được kiểm tra thực tế.

## 1. Mô hình Lookup: danh tính và quyền là hai thứ khác nhau

`java.lang.invoke.MethodHandles.Lookup` là một đối tượng mang **ngữ cảnh kiểm tra truy cập**. Nó chứa thông tin về `lookupClass()` (lớp mà thay mặt nó ta tra cứu) cùng các *lookup modes*. Không nên hiểu `Lookup` là “công cụ Reflection không giới hạn” hoặc chỉ là một cách khác để gọi `Class.forName`.

`MethodHandles.lookup()` là phương thức **caller-sensitive**: khi gọi từ lớp nào, Lookup mới được tạo mang ngữ cảnh của lớp đó. Nếu một hàm utility nằm trong `FrameworkHelper` tự gọi `MethodHandles.lookup()`, nó có Lookup của **FrameworkHelper**, không tự có quyền của mọi lớp ứng dụng được truyền vào làm đối số.

Một số access bits trong Java 17:

| Mode | Ý nghĩa chủ yếu |
| --- | --- |
| `PUBLIC` | Truy cập public theo quy tắc module và khả năng nhìn thấy |
| `PACKAGE` | Truy cập package-private trong runtime package hợp lệ |
| `PROTECTED` | Quyền truy cập protected theo điều kiện của lookup class |
| `PRIVATE` | Quyền truy cập private (kể cả nestmates theo hợp đồng) |
| `MODULE` | Bằng chứng lookup mang quyền trong module của lookup class |
| `ORIGINAL` | Lookup nguyên gốc được tạo bởi caller thực hoặc bootstrap do VM gọi; thêm một số quyền đặc biệt |
| `UNCONDITIONAL` | Kiểu quyền truy cập public không phụ thuộc readability thông thường, như `publicLookup()` |

`lookupModes()` trả **bitmask**, không phải thứ tự ưu tiên. Vì vậy, để kiểm tra có `PRIVATE` hay `MODULE`:

```java
MethodHandles.Lookup l = MethodHandles.lookup();
boolean hasPrivate = (l.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule = (l.lookupModes() & MethodHandles.Lookup.MODULE) != 0;
boolean full = l.hasFullPrivilegeAccess();
```

Đây là đoạn minh họa cần import `java.lang.invoke.MethodHandles`. Với Java 17, **full-privilege access = có đồng thời `PRIVATE` và `MODULE`**, không phải “có riêng `PRIVATE`”. Dùng `hasFullPrivilegeAccess()` thay vì chỉ nhìn một bit, hoặc dùng `hasPrivateAccess()` vốn đã deprecated từ Java 14.

### 1.1. Full privilege không đồng nghĩa ORIGINAL

`ORIGINAL` phân biệt một lookup có nguồn gốc trực tiếp từ lớp caller hoặc bootstrap do VM gọi. Nó quan trọng cho những thao tác nhạy cảm theo danh tính caller hoặc lấy *class data*; không nên nhầm với cặp `PRIVATE` + `MODULE`.

- `MethodHandles.lookup()` tại chính lớp caller thường có `ORIGINAL` **và** full privilege.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)` trong **cùng module** có thể tạo Lookup có full privilege trên Target nhưng **không có `ORIGINAL`**.
- `defineHiddenClass(...)` trả về một Lookup mới trên hidden class, có full privilege **và `ORIGINAL`** theo đặc tả.
- Không kết luận cứ có `ORIGINAL` mới được gọi `defineHiddenClass`; API yêu cầu **full privilege**. Ngược lại, một API như `MethodHandles.classData` yêu cầu **ORIGINAL** trên Lookup được truyền vào.

Đây là lý do hai hàm `hasFullPrivilegeAccess()` và phép kiểm tra bit `ORIGINAL` không thay thế cho nhau.

### 1.2. Cách Lookup mất hoặc thay đổi quyền

| Cách tạo/chuyển Lookup | Kỳ vọng quyền truy cập |
| --- | --- |
| `MethodHandles.lookup()` | Full privilege tương ứng **caller thực sự** |
| `MethodHandles.publicLookup()` | Quyền public tối thiểu, **không** full privilege |
| `lookup.dropLookupMode(Lookup.PRIVATE)` | Bỏ PRIVATE, vì thế **không** full privilege |
| `lookup.in(AnotherClass.class)` | Chuyển lookup class; quyền **không được nâng lên**, có thể mất ORIGINAL/PRIVATE/PACKAGE/MODULE tùy quan hệ |
| `MethodHandles.privateLookupIn(T, lookup)` cùng module | Nếu điều kiện hợp lệ, cấp full privilege trên T, thường không ORIGINAL |
| `privateLookupIn` qua hai module khác nhau | Có thể có PRIVATE trên T nếu package mở hợp lệ, nhưng mất MODULE nên **không** full privilege |

**Cảnh báo đặc biệt cho plugin:** `privateLookupIn` không phải “nâng mọi lookup từ ngoài module lên full privilege”. Với target ở module khác, kể cả package đã `opens` cho module của caller, Lookup kết quả **mất `MODULE`**. Nó có thể truy cập private members theo quyền được cấp, nhưng không đáp ứng điều kiện `defineHiddenClass` trên target. Muốn định nghĩa hidden class trong module của plugin, hãy thiết kế một **điểm hỗ trợ bên trong chính module đó** để lớp tin cậy của plugin tạo/cấp Lookup phù hợp; không truyền quyền tùy ý cho người gọi không đáng tin cậy.

## 2. Ba API định nghĩa lớp và điều kiện quyền

| API | Điều kiện Lookup | Kết quả | Có tham số `initialize`? |
| --- | --- | --- | --- |
| `lookup.defineClass(bytes)` | Cần `PACKAGE` | `Class<?>` của **lớp có tên thông thường** | **Không**; method này không chạy `<clinit>` |
| `lookup.defineHiddenClass(bytes, initialize, options...)` | Cần **full privilege (`PRIVATE` + `MODULE`)** | `Lookup` trên **hidden class** mới | **Có** |
| `lookup.defineHiddenClassWithClassData(bytes, classData, initialize, options...)` | Cần **full privilege** | `Lookup` trên hidden class có class data kèm theo | **Có** |

Tất cả các phương thức trên yêu cầu bytecode class file hợp lệ, và **lớp trong bytes phải ở cùng runtime package** với lookup class thích hợp. Với hidden class, runtime package/module/protection domain được thiết lập dựa trên lookup class theo định nghĩa API. Không thể dùng `publicLookup()` để đưa class tùy ý vào `java.base` hoặc package không liên quan.

### 2.1. Vì sao defineClass chỉ cần PACKAGE?

`defineClass(byte[])` tạo một lớp có tên thông thường trong cùng runtime package và class loader của lookup class, theo cách tương tự `ClassLoader.defineClass`. Quyền `PACKAGE` chứng minh Lookup được cấp cho một caller có quan hệ đúng với package đó. Một Lookup không còn PRIVATE nhưng vẫn có PACKAGE **vẫn có thể gọi `defineClass`**, như ví dụ phần 5.

Ngược lại, `defineHiddenClass` đưa lớp mới vào cùng **module** với lookup class, trả lại Lookup có đặc quyền rất mạnh trên lớp ấy. JDK bắt buộc caller có cả PRIVATE và MODULE, không cho phép chỉ dựa vào PACKAGE.

### 2.2. Hidden class có gì khác lớp thường?

Một hidden class được JVM tạo mà không cần đi qua `ClassLoader.defineClass` theo lối đặt tên thông thường. Khi inspect:

- `hiddenClass.isHidden()` là `true`.
- `hiddenClass.getName()` có phần hậu tố đặc biệt (thường chứa dấu `/` và định danh VM), **không phải một binary class name ổn định**. Đừng lưu kết quả này để tự `Class.forName` lại.
- `Class.forName`, `ClassLoader.loadClass` và `Lookup.findClass(String)` không dùng để tìm hidden class bằng tên đã sinh.
- Mỗi lần `defineHiddenClass` hợp lệ từ cùng bytes tạo **một `Class<?>` riêng**; static state và lịch sử khởi tạo của chúng không phải một singleton chung theo tên bytes.
- Hidden class không được phép được nhắc tới từ constant pool của một lớp khác như một supertype hoặc field descriptor có binary name bình thường.
- Mặc định, hidden class có thể được unload độc lập với tuổi thọ class loader đánh dấu là defining loader, nếu không còn các tham chiếu cần giữ nó sống. `ClassOption.STRONG` thay đổi chính sách này.

Tên file `HiddenPayload.class` chỉ là **nguồn bytes** trong ví dụ; tên class `HiddenPayload` trong source ban đầu không có nghĩa JVM sẽ dùng tên đó như named class sau khi tạo hidden variant.

## 3. Hai giai đoạn không được nhầm: define/link và initialize

Java phân biệt **loading/derivation**, **linking** và **initialization**. Class file có thể đã được load/verify/link nhưng body của `static { ... }` và các static field initializers chưa chạy.

Với `Lookup.defineHiddenClass(bytes, initialize, ...)`:

- `initialize = true`: JVM định nghĩa, liên kết, **và khởi tạo** hidden class trước khi method trả về thành công. Nếu `<clinit>` có side effect, side effect này có thể xảy ra **ngay trong lời gọi defineHiddenClass**.
- `initialize = false`: JVM định nghĩa và liên kết, nhưng **không chủ động khởi tạo class tại thời điểm đó**. Việc khởi tạo có thể diễn ra ở một *active use* về sau.
- Không có API `initialize=false` cho `Lookup.defineClass(byte[])`; API đó **không chạy class initializer**.
- `Class<?>` hoặc `Lookup` đã được tạo không đồng nghĩa class initializer đã chạy.

**`false` là hoãn khởi tạo, không phải vô hiệu hóa `<clinit>` vĩnh viễn.** Khi gọi static method, truy cập static field không phải compile-time constant theo điều kiện active use, tạo instance, hoặc gọi `Lookup.ensureInitialized(cls)`, lớp có thể được khởi tạo.

Sơ đồ:

```text
class bytes (đúng format và package)
       |
       v
defineHiddenClass(bytes, false)
       |
       +-- tạo hidden Class, linked
       +-- trả Lookup (full privilege + original)
       +-- chưa chủ động chạy <clinit>
       |
       v  sau đó:
ensureInitialized(hiddenClass)
hoặc một active use hợp lệ
       |
       v
<clinit> được thực hiện một lần cho Class đó
       |
       v
static method/field/instance tiếp tục vận hành
```

### 3.1. Những thao tác nào không nên mặc định khởi tạo?

Một số thao tác chỉ khám phá hoặc liên kết **không nhất thiết** kích hoạt khởi tạo, ví dụ lấy `Class<?>`, đọc `isHidden()`, `getName()`, `getDeclaredMethods()` hoặc tra cứu MethodHandle bằng `Lookup.findStatic(...)`. Khi **gọi** method handle trỏ tới static method chưa được khởi tạo, JVM cần bảo đảm initialization theo quy tắc active use.

Điểm này rất hữu ích khi framework muốn:

1. đọc metadata, kiểm tra type, chuẩn bị call sites;
2. lắp adapter hoặc registry một cách không gây side effect sớm;
3. chỉ khởi tạo sau khi tất cả bước kiểm tra đã thành công.

Tuy nhiên, bước metadata có thể gián tiếp kích hoạt class khác; và gọi helper có static logic trong lúc validate có thể làm **chính hidden class** khởi tạo. Thiết kế cần dựa vào các quy tắc active use thật, không đoán chỉ bằng việc thấy có từ khóa “lookup”.

### 3.2. ensureInitialized rõ nghĩa hơn một mẹo kích hoạt side effect

`Lookup.ensureInitialized(Class<?>)` bảo đảm class đã khởi tạo nếu chưa, với các ràng buộc quyền **accessClass** của Lookup đối với target class. Nó trả lại `Class<?>` đã được khởi tạo.

```java
Class<?> c = hiddenLookup.lookupClass();
hiddenLookup.ensureInitialized(c);
```

Đây là đoạn minh họa, không phải chương trình độc lập. Dùng `hiddenLookup` được `defineHiddenClass` trả về là cách tự nhiên để có quyền truy cập phù hợp tới hidden class. API có thể ném `IllegalAccessException` nếu target không accessible; nếu initialization failure, có thể thấy `ExceptionInInitializerError` hoặc những lỗi liên kết/khởi tạo liên quan.

**Không có** `Class.isInitialized()` public trong API Java tiêu chuẩn để đọc ngay “đã init chưa”. Đừng dùng một lượt gọi static method “kiểm tra” rồi quên rằng chính nó có thể kích hoạt khởi tạo.

## 4. Ví dụ đầy đủ Java 17+: full privilege, hidden class lazy/eager và NESTMATE

Ví dụ gồm **hai file trong cùng package**. Để tạo hidden class, ta biên dịch `HiddenPayload.java` ra một class file hợp lệ, sau đó `HiddenClassInitDemo` **đọc bytes** bằng resource stream. Việc đọc `.class` qua stream không thực thi `<clinit>` của payload. Không sử dụng thư viện bytecode bên ngoài.

Tạo thư mục `runtime/lesson/` và tệp **`runtime/lesson/HiddenPayload.java`**:

```java
package runtime.lesson;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

final class HiddenPayload {
    static {
        System.out.println("Payload.<clinit>");
    }

    static int answer() {
        return 42;
    }

    static String hostSecret() throws Throwable {
        MethodHandle m = MethodHandles.lookup().findStatic(
                HiddenClassInitDemo.class,
                "secret",
                MethodType.methodType(String.class));
        return (String) m.invokeExact();
    }
}
```

Tệp này **không có public class** và được biên dịch cùng file host. `hostSecret()` dùng MethodHandle để kiểm tra quyền gọi `private static` method của host tại runtime; khi nó được định nghĩa như hidden **nestmate**, quyền private trong cùng nest có thể được sử dụng. Không dùng mã nguồn `HiddenPayload` để trực tiếp gọi `HiddenClassInitDemo.secret()` vì compiler của hai class ban đầu không coi chúng là nestmates.

Tệp **`runtime/lesson/HiddenClassInitDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassInitDemo {
    private static String secret() {
        return "host-secret";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup host = MethodHandles.lookup();
        byte[] bytes;
        try (InputStream in = HiddenClassInitDemo.class
                .getResourceAsStream("HiddenPayload.class")) {
            if (in == null) {
                throw new IllegalStateException("HiddenPayload.class not found");
            }
            bytes = in.readAllBytes();
        }

        System.out.println("hostFull=" + host.hasFullPrivilegeAccess());

        MethodHandles.Lookup lazy = host.defineHiddenClass(
                bytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> cls = lazy.lookupClass();

        System.out.println("lazyHidden=" + cls.isHidden());
        System.out.println("returnedFull=" + lazy.hasFullPrivilegeAccess());
        System.out.println("nestmate="
                + (cls.getNestHost() == HiddenClassInitDemo.class));
        System.out.println("after define(false)");

        MethodHandle answer = lazy.findStatic(
                cls, "answer", MethodType.methodType(int.class));
        System.out.println("after findStatic");

        lazy.ensureInitialized(cls);
        System.out.println("answer=" + (int) answer.invokeExact());

        MethodHandle reveal = lazy.findStatic(
                cls, "hostSecret", MethodType.methodType(String.class));
        System.out.println("secret=" + (String) reveal.invokeExact());

        MethodHandles.Lookup eager = host.defineHiddenClass(bytes, true);
        System.out.println("after define(true)");
        System.out.println("eagerHidden=" + eager.lookupClass().isHidden());

        MethodHandles.Lookup restricted =
                host.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        System.out.println("restrictedFull="
                + restricted.hasFullPrivilegeAccess());
        try {
            restricted.defineHiddenClass(bytes, false);
        } catch (IllegalAccessException e) {
            System.out.println("restricted=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch hai tệp từ thư mục cha chứa `runtime/lesson/` và chạy bằng Java 17+:

```bash
javac --release 17 -d out runtime/lesson/HiddenPayload.java runtime/lesson/HiddenClassInitDemo.java
java -cp out runtime.lesson.HiddenClassInitDemo
```

`stdout` đã kiểm tra:

```text
hostFull=true
lazyHidden=true
returnedFull=true
nestmate=true
after define(false)
after findStatic
Payload.<clinit>
answer=42
secret=host-secret
Payload.<clinit>
after define(true)
eagerHidden=true
restrictedFull=false
restricted=IllegalAccessException
```

### 4.1. Phân tích chính xác thứ tự xuất hiện

1. `hostFull=true`: `MethodHandles.lookup()` bên trong `HiddenClassInitDemo` có full privilege đối với chính caller.
2. `lazyHidden=true`: bytes đã được định nghĩa thành một hidden class mới, không phải lớp có tên bình thường.
3. `returnedFull=true`: Lookup từ `defineHiddenClass` có full privilege trên hidden class được tạo.
4. `nestmate=true`: cờ `NESTMATE` gắn hidden class với nest host của lookup class.
5. Sau `after define(false)` và `after findStatic` **chưa có** dòng `Payload.<clinit>`: chỉ định nghĩa và tìm MethodHandle không khởi tạo payload.
6. `lazy.ensureInitialized(cls)` chủ động chạy `<clinit>` của hidden class thứ nhất. Sau đó gọi `answer()` trả `42` mà không chạy initializer lần hai.
7. `hostSecret()` có thể dùng `MethodHandles.lookup()` từ trong hidden class đã được gắn `NESTMATE` để tìm private method của host; kết quả `host-secret` chứng minh quyền nestmate được áp dụng.
8. Lần `host.defineHiddenClass(bytes, true)` tạo một **hidden class mới** từ cùng bytes. Vì initialize true, dòng `Payload.<clinit>` **thứ hai** xuất hiện trước `after define(true)`. Đây không phải khởi tạo lại class thứ nhất.
9. Sau `dropLookupMode(PRIVATE)`, `restrictedFull=false` và `defineHiddenClass` bị từ chối bằng `IllegalAccessException`.

**Không copy một chuỗi tên lớp hidden rồi dùng `Class.forName` để tái tìm nó.** Hãy giữ tham chiếu `Class<?>`, `Lookup` hoặc `MethodHandle` thích hợp trong suốt vòng đời mà framework cần; đồng thời kiểm soát cache để không giữ hidden classes sống mãi ngoài ý muốn.

### 4.2. Vì sao NESTMATE quan trọng?

`ClassOption.NESTMATE` bổ sung hidden class vào nest của lookup class, cho phép cùng quy tắc private access giữa nestmates. Nó **không bắt buộc** khi chỉ tạo một hidden class có method public/package-private của riêng nó. Nếu bỏ `NESTMATE` trong chương trình trên, hidden class thường có nest host là chính nó; lời gọi tìm private `HiddenClassInitDemo.secret` từ trong `HiddenPayload.hostSecret` không còn thỏa điều kiện private nestmate.

**Không nhầm `NESTMATE` với `STRONG`**: một cờ quyết định quan hệ nest/access; cờ kia quyết định lifetime/unloading cùng defining loader. Chúng có thể được kết hợp khi cần, và đều là `ClassOption` truyền qua varargs `options`.

## 5. Ví dụ đầy đủ: defineClass chỉ cần PACKAGE và không chạy <clinit>

Để phân biệt quyền **PACKAGE** với full privilege, tạo hai file khác (vẫn package `runtime.lesson`). Ví dụ này cố ý **drop PRIVATE**, sau đó dùng `defineClass` để định nghĩa một **named class**. Vì class có tên thông thường, định nghĩa **trùng tên lần hai** trong cùng loader sẽ gây lỗi.

Tệp **`runtime/lesson/NamedPayload.java`**:

```java
package runtime.lesson;

final class NamedPayload {
    static {
        System.out.println("NamedPayload.<clinit>");
    }

    static String ping() {
        return "named";
    }
}
```

Tệp **`runtime/lesson/NamedClassDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class NamedClassDemo {
    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup packageLookup = MethodHandles.lookup()
                .dropLookupMode(MethodHandles.Lookup.PRIVATE);

        byte[] bytes;
        try (InputStream in = NamedClassDemo.class
                .getResourceAsStream("NamedPayload.class")) {
            if (in == null) {
                throw new IllegalStateException("NamedPayload.class not found");
            }
            bytes = in.readAllBytes();
        }

        System.out.println("packageAccess="
                + ((packageLookup.lookupModes()
                  & MethodHandles.Lookup.PACKAGE) != 0));
        System.out.println("full=" + packageLookup.hasFullPrivilegeAccess());

        Class<?> named = packageLookup.defineClass(bytes);
        System.out.println("namedHidden=" + named.isHidden());
        System.out.println("after defineClass");

        packageLookup.ensureInitialized(named);
        System.out.println("after ensureInitialized");

        try {
            packageLookup.defineClass(bytes);
        } catch (LinkageError e) {
            System.out.println("duplicate=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong một JVM/process mới:

```bash
javac --release 17 -d out runtime/lesson/NamedPayload.java runtime/lesson/NamedClassDemo.java
java -cp out runtime.lesson.NamedClassDemo
```

`stdout`:

```text
packageAccess=true
full=false
namedHidden=false
after defineClass
NamedPayload.<clinit>
after ensureInitialized
duplicate=LinkageError
```

**Giải thích:**

- `dropLookupMode(PRIVATE)` bỏ full privilege nhưng giữ `PACKAGE` trong ví dụ. Nó đủ cho `defineClass`; không đủ cho `defineHiddenClass`.
- `namedHidden=false` vì đây là class thông thường, có binary name trong runtime package.
- `after defineClass` xuất hiện **trước** `NamedPayload.<clinit>`: `defineClass` không khởi tạo.
- `ensureInitialized(named)` chủ động chạy static initializer một lần.
- Gọi `defineClass` với bytes mang **cùng binary name** thêm lần nữa trên cùng loader gây `LinkageError`; ngược lại, hidden class có tên hậu tố riêng do JVM tạo, nên ví dụ phần 4 định nghĩa hai hidden classes từ cùng bytes được.

**Điều kiện kiểm thử:** tệp `NamedPayload.class` phải tồn tại để host đọc bytes, nhưng không được có một đường thực thi đã chủ động load/define cùng tên trong process trước khi `defineClass` chạy. Vì vậy, chạy `NamedClassDemo` bằng lệnh `java` như trên trong process riêng, không gọi `NamedPayload.ping()` trước đó.

## 6. defineHiddenClassWithClassData cũng cần full privilege và cùng cờ initialize

`Lookup.defineHiddenClassWithClassData(bytes, classData, initialize, options...)` là phiên bản định nghĩa hidden class **kèm một object class data**. Nó có cùng điều kiện full privilege và cờ initialize như `defineHiddenClass`, nhưng runtime kết hợp object được cung cấp với hidden class theo cơ chế class data. API có từ **Java 16**.

Class data phù hợp khi một runtime linker muốn cấp metadata, `MethodHandle`, cấu hình hoặc danh sách giá trị cho hidden class mà không phải tạo static field public hoặc đưa dữ liệu vào constant pool dưới dạng literal. Đối tượng `classData` có thể là một object hay `List`. Dùng dữ liệu bất biến khi có thể; mutable object bị sửa đồng thời có thể làm behavior khó dự đoán.

Để đọc class data, JDK cung cấp:

- `MethodHandles.classData(lookup, "_", T.class)` lấy object toàn phần.
- `MethodHandles.classDataAt(lookup, "_", T.class, index)` lấy một element nếu class data là `List`.

**Một giới hạn dễ bị bỏ quên:** việc đọc class data yêu cầu Lookup có bit `ORIGINAL`, không chỉ PRIVATE/MODULE. Cả `classData` lẫn `classDataAt` cũng **có thể chủ động khởi tạo lookup class nếu chưa khởi tạo**; vì vậy cờ `initialize=false` không có nghĩa API đọc class data sẽ mãi không chạy `<clinit>`.

### 6.1. Ví dụ Java 17+: truy xuất class data và thời điểm khởi tạo

Tệp **`runtime/lesson/DataCarrier.java`**:

```java
package runtime.lesson;

import java.lang.invoke.MethodHandles;

final class DataCarrier {
    static {
        System.out.println("DataCarrier.<clinit>");
    }

    static String read() throws IllegalAccessException {
        return MethodHandles.classData(
                MethodHandles.lookup(), "_", String.class);
    }
}
```

Tệp **`runtime/lesson/HiddenClassDataDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDataDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = HiddenClassDataDemo.class
                .getResourceAsStream("DataCarrier.class")) {
            if (in == null) {
                throw new IllegalStateException("DataCarrier.class not found");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup newLookup = MethodHandles.lookup()
                .defineHiddenClassWithClassData(
                        bytes, "config-v1", false);

        System.out.println("full=" + newLookup.hasFullPrivilegeAccess());
        System.out.println("original="
                + ((newLookup.lookupModes()
                  & MethodHandles.Lookup.ORIGINAL) != 0));
        System.out.println("after defineWithClassData(false)");

        MethodHandle read = newLookup.findStatic(newLookup.lookupClass(),
                "read", MethodType.methodType(String.class));
        System.out.println("after findStatic");

        System.out.println("data="
                + MethodHandles.classData(newLookup, "_", String.class));
        System.out.println("viaMethod=" + (String) read.invokeExact());
    }
}
```

```bash
javac --release 17 -d out runtime/lesson/DataCarrier.java runtime/lesson/HiddenClassDataDemo.java
java -cp out runtime.lesson.HiddenClassDataDemo
```

`stdout`:

```text
full=true
original=true
after defineWithClassData(false)
after findStatic
DataCarrier.<clinit>
data=config-v1
viaMethod=config-v1
```

Dòng `DataCarrier.<clinit>` chạy khi host gọi `MethodHandles.classData(newLookup,"_",String.class)`, mặc dù hidden class trước đó được định nghĩa với `initialize=false`. Gọi `read.invokeExact()` sau đó **không chạy lại initializer** và vẫn trả đúng class data.

**Đừng nhầm cờ initialize của factory với tính bất biến của class data**: `initialize=false` không làm object dữ liệu bị “đóng băng” hoặc cô lập khỏi thread khác. Nếu truyền `List`, nên cân nhắc `List.of(...)` hoặc snapshot bất biến; không dùng một mảng mutable chia sẻ với code không đáng tin cậy mà không có bảo vệ.

## 7. Quan hệ với module và privateLookupIn

Trong hệ thống JPMS, khái niệm “package giống nhau” chưa đủ nếu **runtime module** hoặc loader khác nhau. Điều kiện đặc tả của `defineHiddenClass` là bytes phải định nghĩa một lớp có **package phù hợp lookup class**; hidden class sẽ nằm trong cùng runtime package/module/protection domain của lookup class mà không tự động vào module khác.

### 7.1. Chuyển Lookup sang lớp khác trong cùng module

Khi `hostLookup = MethodHandles.lookup()` có full privilege, `MethodHandles.privateLookupIn(Target.class, hostLookup)` (nếu hợp lệ) có thể cấp một Lookup có full privilege trên target trong cùng module. Từ đó có thể định nghĩa hidden class có bytes phù hợp package của Target.

```java
MethodHandles.Lookup onTarget =
        MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup());

if (!onTarget.hasFullPrivilegeAccess()) {
    throw new IllegalStateException("Need full privilege");
}

MethodHandles.Lookup hidden =
        onTarget.defineHiddenClass(classBytes, false);
```

Đoạn này là **mẫu minh họa**, giả định `Target` và `classBytes` đã được cung cấp hợp lệ; không phải chương trình độc lập. Không dùng để vượt qua ranh giới module một cách mặc định.

### 7.2. Cross-module deep reflection không tự bằng quyền define

Giả sử code framework trong module `framework.core` cố truy cập một type thuộc `plugin.module`:

- Framework phải đọc được module đích; module đích phải `opens` package phù hợp cho module framework để `privateLookupIn` hợp lệ.
- Lookup kết quả ở module **khác** có thể mang `PRIVATE` nhưng **mất `MODULE`**, vì nó còn lưu `previousLookupClass()` để kiểm tra cross-module access.
- `hasFullPrivilegeAccess()` khi đó là `false`, và `defineHiddenClass` sẽ từ chối bằng `IllegalAccessException`.
- Dùng `--add-opens` hoặc sửa `module-info.java` có thể cho phép **deep reflection**, nhưng không tự làm Lookup “full privilege” trong module đích.

Đây là một ranh giới an ninh có chủ ý. Hướng kiến trúc phù hợp là: module/plugin sở hữu package cung cấp **một factory tin cậy** thực hiện định nghĩa lớp trong chính module đó và trả về một interface/handle tối thiểu cho phần mềm sử dụng, thay vì đưa raw full-privilege Lookup cho bên thứ ba.

### 7.3. Không dựa vào tên module và package bằng chuỗi

Nếu bytes định nghĩa class mang package khác lookup class, `defineHiddenClass` có thể ném `IllegalArgumentException`. Nếu bytes hỏng hoặc không phải class file hợp lệ, có thể thấy `ClassFormatError` hoặc `VerifyError`. Nếu class file version mới hơn JVM hỗ trợ, có thể thấy `UnsupportedClassVersionError`. Kiểm tra **Class<?>/Module/ClassLoader thật**, không chỉ so sánh binary name dạng chuỗi, trước khi đưa một bộ sinh bytecode vào pipeline.

## 8. initialize=true không phải một bước “không có tác dụng phụ”

Class initialization có thể chạy:

- Các static field initializers (trừ compile-time constants theo quy tắc liên quan).
- Body `static { ... }`.
- Các helper được gọi từ static initializers.
- Tác dụng phụ I/O, thread creation, đăng ký registry, nạp cấu hình hoặc ném exception.

Nếu framework đang tạo class từ dữ liệu bên ngoài, `initialize=true` có nghĩa nó có thể chạy **mã của lớp vừa được tạo ngay trong lệnh define**. Không được coi đây là một thao tác chỉ “đăng ký metadata”.

### 8.1. Chọn initialize=true khi nào?

Chọn true khi:

- Class bytes và mã `<clinit>` được tin cậy, đã được validate.
- Cần sẵn sàng trạng thái static ngay sau khi hàm define trả về.
- Có thể xử lý lỗi initialization tại thời điểm tạo class.
- Thứ tự khởi tạo giữa nhiều class phụ thuộc đã được thiết kế.

Chọn false khi:

- Muốn tách bước define/link/validate metadata khỏi bước thực thi initializer.
- Muốn tạo nhiều hidden classes rồi quyết định sẽ dùng class nào.
- Muốn trì hoãn chi phí initialization và side effects đến lúc thực sự cần gọi đích.
- Có lifecycle rõ ràng để gọi `ensureInitialized` hoặc dựa vào active use hợp lệ về sau.

**Nhưng** initialize=false **không phải sandbox**. Một khi caller gọi static method hoặc một API kích hoạt initialization, code `<clinit>` vẫn chạy với quyền bình thường của class đó. Nếu bytes không đáng tin cậy, phải đánh giá/cô lập nguồn bytes theo chính sách bảo mật trước khi định nghĩa, chứ không chỉ truyền false.

### 8.2. Side effect và cạnh tranh giữa thread

JVM phối hợp initialization của **mỗi Class object** theo các quy tắc JLS/JVMS. Nếu hai thread cùng active-use một hidden class, không có nghĩa cả hai được phép chạy `<clinit>` song song cho cùng Class: initialization được điều phối. Nhưng nếu bạn gọi `defineHiddenClass` **hai lần** với cùng bytes, bạn nhận hai Class objects độc lập; **mỗi class** có thể có `<clinit>` của riêng nó.

Điều này rất quan trọng với framework:

- Không tự đặt một global business registration trong static initializer rồi coi nó “mỗi bytes chỉ chạy một lần”.
- Nếu tạo hai hidden classes khác identity, registration có thể bị lặp.
- Nếu `<clinit>` có side effect ngoài JVM, chú ý idempotency và ownership, kể cả khi chỉ có một thread đang thao tác.
- Không dùng `initialize=false` như cách tránh deadlock nếu sau đó chương trình có chu trình class initialization; hãy phân tích dependency và khóa ở những nơi active use.

## 9. ClassOption.NESTMATE, STRONG và lifetime

Hai `Lookup.ClassOption` liên quan đến định nghĩa hidden class:

| Cờ | Tác động | Điều không tự cung cấp |
| --- | --- | --- |
| `NESTMATE` | Gắn hidden class vào nest của lookup class; có thể truy cập private members của các nestmates theo quy định | Không biến class thành public API; không tự quản lý class initialization |
| `STRONG` | Tạo quan hệ unloading với defining class loader như lớp có tên thông thường | Không ép initialize ngay; không tăng quyền Lookup; không bảo đảm memory leak-free |

Mặc định **không có STRONG**, hidden class có thể được unload dù defining loader còn reachable, nếu không còn những tham chiếu khiến hidden class cần sống. Nếu thêm `STRONG`, hidden class thường chỉ unload cùng khi defining loader không còn reachable; trong ứng dụng sinh hàng nghìn classes động, giữ quá nhiều strong hidden classes có thể tăng áp lực metaspace.

Một method handle, `Class<?>`, Lookup hoặc object sinh từ hidden class có thể làm cho class còn reachable. Cache toàn cục chứa những object này có thể giữ class loader và class lâu hơn dự kiến. Dùng cache có vòng đời, weak references hoặc `ClassValue` nơi phù hợp, đồng thời xác minh lại điều kiện unload thực tế. **Không dựa vào thứ tự/lúc GC để bảo đảm logic**.

### 9.1. Access private giữa nestmates không tự cho phép mọi điều

Trong ví dụ phần 4, hidden `HiddenPayload` được định nghĩa với NESTMATE và có thể dùng Lookup của chính nó để tìm method private của `HiddenClassInitDemo`. Nhưng một class bình thường ở package khác, hoặc mã plugin chưa được tin cậy, không thể được xem là nestmate chỉ vì giữ string tên tương tự.

NESTMATE là quyết định **nâng khả năng truy cập trong nest**, nên chỉ áp dụng cho bytes đã được tin cậy. Nếu muốn chỉ public API, có thể không dùng NESTMATE, trả về handle/instance với interface hạn chế, không chia sẻ Lookup đầy đủ.

## 10. Bảo mật: Lookup là một capability cần kiểm soát

Việc đưa một `Lookup` full-privilege cho code không đáng tin cậy giống như trao khả năng thao tác trên các private members mà Lookup có thể truy cập và thậm chí định nghĩa hidden classes trong module tương ứng. Một framework không nên:

- Lưu `MethodHandles.lookup()` nguyên vẹn vào registry công khai mà mọi plugin lấy được.
- Truyền trực tiếp Lookup full privilege từ bootstrap tin cậy vào callbacks của bên thứ ba khi chỉ cần gọi một method đã chọn.
- Gọi `defineHiddenClass(userSuppliedBytes, true)` trên bytes không kiểm tra mà hy vọng JVM package check đủ để làm sandbox.
- Dùng `setAccessible(true)` hoặc `--add-opens` như “giải pháp” cho việc thiếu full privilege mà bỏ qua chính sách module.
- Cho phép code tùy ý cung cấp static initialization có side effect vào môi trường cùng module với thành phần lõi đáng tin cậy.

**Nguyên tắc least privilege:** nếu người dùng của framework chỉ cần chạy một implementation, trả về một `MethodHandle` cụ thể, một interface chức năng hoặc một service object đã hạn chế. Không trao luôn quyền tạo tùy ý phương thức/class mới. Nếu phải chuyển Lookup, cân nhắc `dropLookupMode` cho nhiệm vụ chỉ tra package/public members; ghi rõ rằng **sau khi drop mode không thể khôi phục đặc quyền từ chính Lookup đã bị hạ quyền**.

### 10.1. Kiểm soát nguồn bytecode và lỗi

Trước khi định nghĩa class:

1. Xác thực nguồn bytes (trusted code generator, checksum/signature, policy allowlist).
2. Xác minh class file version JVM hỗ trợ và runtime package dự kiến.
3. Biết rõ Lookup xuất phát từ lớp/module nào, có full privilege hay chỉ PACKAGE.
4. Kiểm tra cờ `initialize` và các static initializers có thể chạy.
5. Chọn `NESTMATE`/`STRONG` theo nhu cầu đã chứng minh, không bật đại.
6. Phân loại lỗi: `IllegalAccessException`, `IllegalArgumentException`, `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError` và những `LinkageError` khác.
7. Quản lý lifecycle, cache, resource và cleanup nếu initialization thành công một phần rồi thất bại.

Thông thường việc kiểm tra class bytes hoàn toàn trước khi chạy là bài toán khó; một class hợp lệ vẫn có thể thực thi hành vi không mong muốn. Đừng coi JVM verifier hay package check là chính sách sandbox độc lập.

## 11. Các lỗi hay gặp và cách phân tích

| Lỗi/hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalAccessException` ở `defineHiddenClass` | Lookup không có cả PRIVATE và MODULE | Gọi `hasFullPrivilegeAccess()`; chỉ lấy Lookup đáng tin trong đúng module |
| `defineClass` được nhưng `defineHiddenClass` thất bại | Lookup có PACKAGE nhưng không full privilege | Phân biệt hai mức quyền; không suy ra quyền hidden từ quyền named |
| `privateLookupIn` qua module khác vẫn không định nghĩa được hidden class | MODULE bị bỏ khi teleport cross-module | Để factory đáng tin bên trong target module thực hiện define |
| `ClassFormatError` | Bytes không phải class file hợp lệ | Kiểm tra generator và class file structure |
| `UnsupportedClassVersionError` | Major/minor class file không tương thích JVM | Biên dịch đúng `--release 17` hoặc dùng JVM hỗ trợ |
| `IllegalArgumentException` | Package trong bytes khác lookup class, hoặc input không hợp lệ | Xác minh internal class name/runtime package trước khi define |
| `VerifyError` / `LinkageError` | Bytecode không hợp lệ về type system hoặc lỗi liên kết | Dùng verifier, bytecode QA và kiểm tra dependencies |
| Không thấy `<clinit>` sau `initialize=false` | Class chỉ được định nghĩa/liên kết, chưa active use | Gọi `ensureInitialized` khi đã sẵn sàng cho side effects |
| `<clinit>` chạy trong `defineHiddenClass(true)` | Đây đúng là ý nghĩa cờ true | Dùng false nếu muốn tách thời điểm, không quên active use sau đó |
| `<clinit>` chạy khi đọc class data | `MethodHandles.classData` chủ động init lookup class | Ghi nhận trigger initialization trong thiết kế class-data |
| Hidden class không tìm được bằng `Class.forName` | Hidden class không có binary name thông thường | Giữ `Class<?>` hoặc `MethodHandle` được trả về |
| Từ cùng bytes thấy `<clinit>` chạy hai lần | Hai hidden Class objects riêng được định nghĩa | Không nhầm mỗi-class initialization với mỗi-source-file |
| `ExceptionInInitializerError` tại điểm active use | Static initializer ném exception khi chạy | Xử lý nguyên nhân; không giả định class có thể retry initialization an toàn |
| Lần sau gặp `NoClassDefFoundError` | Class từng thất bại initialization và ở trạng thái erroneous | Sửa lỗi nguồn, dùng class mới/class loader mới theo lifecycle hợp lệ |
| Class bị giữ sống quá lâu | Cache `STRONG`, `Class`, Lookup hoặc MH giữ tham chiếu | Xây cache có lifecycle, test metaspace/class unloading |
| `MethodHandles.lookup()` từ helper có quyền sai | Lookup được tạo theo **caller helper**, không phải target class | Đưa trusted factory vào đúng module/class hoặc dùng `privateLookupIn` hợp lệ |
| `hasPrivateAccess()` gây nhầm | API đã deprecated; PRIVATE không tự bao hàm MODULE | Dùng `hasFullPrivilegeAccess()` trong bài toán định nghĩa hidden class |

### 11.1. Tách ba loại lỗi theo giai đoạn

**Giai đoạn định nghĩa/liên kết:** class bytes không hợp lệ, package sai, thiếu lookup privilege, không link được dependency. Lỗi thường phát sinh ngay trong lời gọi `defineHiddenClass` hoặc `defineClass`.

**Giai đoạn khởi tạo:** static initializer hoặc static field initializer chạy, có thể ném exception; với `initialize=true` lỗi này thường hiển thị tại phương thức define. Với `false`, lỗi có thể chỉ xuất hiện khi gọi `ensureInitialized`, static method, hoặc một active use khác.

**Giai đoạn thực thi:** code bên trong method đích ném exception, kể cả sau khi class đã khởi tạo. Không đánh đồng lỗi method body với lỗi class initialization. MethodHandle khi gọi còn có thể ném `WrongMethodTypeException` do call site signature không khớp, không liên quan cờ initialize.

## 12. Workflow thực tế cho framework sinh bytecode

Khi thiết kế runtime code generation hoặc dynamic proxy bằng hidden classes, áp dụng pipeline:

```text
[1] Trusted source/generator tạo classfile bytes
     |
[2] Kiểm tra package/module/name, version, policy
     |
[3] Lấy Lookup đúng caller; kiểm tra hasFullPrivilegeAccess
     |
[4] Chọn flags: NESTMATE? STRONG? classData?
     |
[5] Chọn initialize:
       false -> muốn liên kết rồi kiểm tra/chuẩn bị trước
       true  -> chấp nhận static initializer chạy ngay
     |
[6] defineHiddenClass / defineHiddenClassWithClassData
     |
[7] Nhận hidden Lookup; lấy hiddenClass = lookupClass()
     |
[8] Lấy method handles, kiểm tra MethodType, quyền
     |
[9] Khi đã sẵn sàng: ensureInitialized hoặc active use
     |
[10] Giao ra API/handle tối thiểu, không lộ full Lookup
     |
[11] Theo dõi lifetime, cache, cleanup và lỗi init
```

Một khung kiểm tra rõ ràng:

```java
static MethodHandles.Lookup defineTrustedHidden(
        byte[] classBytes,
        MethodHandles.Lookup host,
        boolean initialize) throws IllegalAccessException {

    if (!host.hasFullPrivilegeAccess()) {
        throw new IllegalAccessException("Full privilege required");
    }
    // Chỉ truyền bytes đã được kiểm tra nguồn và package phù hợp.
    return host.defineHiddenClass(classBytes, initialize);
}
```

Đây là **method minh họa** cần import `MethodHandles`; không tự là một ứng dụng runnable và không thay thế bytecode validation. Đặc biệt, câu `hasFullPrivilegeAccess()` là kiểm tra điều kiện quyền, **không phải kiểm tra nội dung bytes có an toàn**.

Với nhu cầu chỉ tạo class có tên và không cần quyền private/module, một `Lookup` có PACKAGE có thể thích hợp cho `defineClass`; đừng tự ép dùng hidden class khi hệ thống lại cần `Class.forName` bằng tên ổn định.

## 13. Bài tập tự kiểm tra

**Bài 1 — điều kiện full privilege.** Một Lookup có `PRIVATE` nhưng đã bị drop `MODULE`. Có thể dùng `defineHiddenClass` không?

**Đáp án:** Không. Full privilege trên Java 17 cần cả `PRIVATE` và `MODULE`; nếu thiếu một trong hai, `hasFullPrivilegeAccess()` là false.

**Bài 2 — quyền named class.** Lookup có `PACKAGE` và `MODULE` nhưng không có `PRIVATE`. `defineClass(bytes)` và `defineHiddenClass(bytes,false)` khác gì?

**Đáp án:** Khi bytes hợp lệ và cùng package, `defineClass` có thể thành công vì chỉ cần PACKAGE; `defineHiddenClass` thất bại vì thiếu full privilege.

**Bài 3 — khi nào initializer chạy?** `hiddenLookup = host.defineHiddenClass(bytes,false)`; sau đó gọi `hiddenLookup.findStatic(cls,"run",methodType(void.class))` nhưng chưa invoke. Có thể khẳng định `<clinit>` đã chạy chưa?

**Đáp án:** Không thể khẳng định đã chạy chỉ vì tạo MethodHandle. Trong ví dụ runnable, `findStatic` không khởi tạo; initializer chạy khi `ensureInitialized` hoặc khi invocation static tạo active use.

**Bài 4 — hai hidden classes.** Gọi `defineHiddenClass(bytes,true)` hai lần trong một JVM với cùng bytes có static initializer tăng counter toàn cục. Có thể thấy counter tăng hai lần không?

**Đáp án:** Có, vì hai calls tạo **hai hidden Classes khác nhau**, mỗi class chạy initializer riêng. Mỗi class khởi tạo một lần không có nghĩa mỗi byte array chỉ được khởi tạo một lần.

**Bài 5 — ORIGINAL.** `privateLookupIn(Target.class, caller)` trong cùng module trả Lookup có full privilege nhưng thường không có ORIGINAL. Dùng Lookup đó gọi `defineHiddenClass` thì thế nào? Có dùng làm đối số `MethodHandles.classData` tương đương Lookup trên hidden class được tạo không?

**Đáp án:** Full privilege là đủ cho `defineHiddenClass` nếu bytes đúng package và các điều kiện khác hợp lệ. Nhưng `MethodHandles.classData` yêu cầu ORIGINAL của Lookup truyền vào; nên không tự thay Lookup của hidden class bằng một Lookup khác thiếu ORIGINAL.

**Bài 6 — cross-module.** Một framework mở package của plugin bằng `opens` và gọi thành công `privateLookupIn(Plugin.class, frameworkLookup)`. Vì sao `defineHiddenClass` vẫn có thể ném IllegalAccessException?

**Đáp án:** Lookup teleport sang module khác **mất MODULE mode**, không có full privilege. Framework cần cơ chế factory đáng tin trong module đích.

**Bài 7 — phát hiện hidden class.** Vì sao `Class.forName(hiddenClass.getName())` không phải cách đáng tin để tìm lại lớp?

**Đáp án:** Hidden class không có binary name thông thường để class loader tìm theo tên; hãy dùng `Class<?>` và Lookup/MethodHandle trả về.

**Bài 8 — STRONG.** Bật `ClassOption.STRONG` có khiến class tự initialized không?

**Đáp án:** Không. STRONG liên quan unloading/lifetime. Thời điểm initialization vẫn do boolean initialize và active use kiểm soát.

**Bài 9 — security.** Đưa Lookup full privilege và bytes do người dùng cung cấp vào `defineHiddenClass(bytes,false)` có an toàn chỉ nhờ false không?

**Đáp án:** Không. False chỉ hoãn initializers; class có thể được khởi tạo ở active use, và hidden class vẫn có quyền trong module/package theo các cơ chế Java. Cần xác thực nguồn bytes, phạm vi cấp quyền, và policy chạy code.

## 14. Tài liệu chính thức

- [Oracle JDK 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `hasFullPrivilegeAccess`, `lookupModes`, `defineClass`, `defineHiddenClass`, `defineHiddenClassWithClassData`, `ensureInitialized`, `dropLookupMode`.
- [Oracle JDK 17 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`.
- [Oracle JDK 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn`, `classData`, `classDataAt`.
- [Java Language Specification SE 17 `12.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): initialization of classes and interfaces, active use, initialization errors.
- [Java Virtual Machine Specification SE 17 `5.3.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.5): deriving a class from its class file representation.
- [Java Virtual Machine Specification SE 17 `5.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization tại cấp JVM.
- [Oracle JDK 17 — `Class.isHidden`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden()): nhận biết hidden class.

**Ghi nhớ:** `defineHiddenClass` và `defineHiddenClassWithClassData` cần Lookup **full-privilege = PRIVATE + MODULE**; `defineClass` chỉ cần **PACKAGE**. `initialize=true` thực hiện `<clinit>` trước khi define trả về; `false` chỉ **hoãn**, không ngăn initialization khi active use hay khi gọi `ensureInitialized`/các API có yêu cầu. Luôn tách bài toán **quyền định nghĩa lớp**, **thời điểm thực thi initializer** và **vòng đời của hidden class** — đồng thời không tiết lộ full Lookup khi một handle với quyền hẹp là đủ.
