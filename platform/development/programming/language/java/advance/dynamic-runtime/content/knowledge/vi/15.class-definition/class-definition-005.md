# 15.5. `NESTMATE`, `STRONG` và quan hệ vòng đời của hidden class với bộ nạp lớp

## 1. Bài toán: cùng một hidden class, hai quyết định độc lập

Java 15 giới thiệu `MethodHandles.Lookup.defineHiddenClass(...)` để tạo **hidden class** trực tiếp từ bytecode, không đăng ký một binary name có thể tìm bằng `Class.forName`. Hai tùy chọn `MethodHandles.Lookup.ClassOption` rất dễ bị hiểu lẫn:

- **`NESTMATE`**: cho hidden class **gia nhập nest của lookup class**, nhờ đó có thể truy cập các thành viên `private` của các class khác trong **cùng nest**, theo quy tắc nest-based access control.
- **`STRONG`**: cho hidden class có **quan hệ chặt với bộ nạp lớp được đánh dấu là defining loader** giống class thông thường. Hidden class có `STRONG` chỉ *có thể* unload nếu defining loader không còn reachable và có thể được GC thu hồi.
- **Không chọn `STRONG`**: hidden class mặc định **có thể unload ngay cả khi defining loader vẫn reachable**, nếu nó không còn được giữ sống bởi các đối tượng/capability liên quan và JVM quyết định thu hồi.
- **Hai option độc lập**. `NESTMATE` **không ngụ ý** `STRONG`; `STRONG` **không cấp** quyền truy cập `private`.

Trong phạm vi bài này, gọi “weak hidden class” là cách nói về **khả năng class unloading độc lập khỏi loader** mặc định. Điều đó **không** có nghĩa `Class.getClassLoader()` trả `null`, không đồng nghĩa class được tạo bởi `WeakReference`, và không bảo đảm có thể đo kết quả unload bằng một lần `System.gc()`.

Mục tiêu học tập:

1. Phân biệt quyền nest với chính sách unload của hidden class.
2. Hiểu cách `defineHiddenClass` gắn class mới với **cùng runtime package, module, protection domain và defining loader** của lookup class.
3. Đọc `Class.isHidden()`, `getNestHost()`, `isNestmateOf()`, `getClassLoader()` và hiểu giới hạn của `getNestMembers()`.
4. Chạy một ví dụ Java 17+ với cả **bốn tổ hợp** option, quan sát lời gọi private thành công/thất bại.
5. Thiết kế vòng đời cho code generation, framework, lambda-like runtime code và tránh giữ nhiều class không cần thiết trong loader sống lâu.

## 2. `defineHiddenClass`: không giống `ClassLoader.defineClass`

API tiêu biểu:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenType = hiddenLookup.lookupClass();
```

**Đoạn này là mã minh họa**, dùng `byte[] bytes` đã được cung cấp; cần import `java.lang.invoke.MethodHandles`.

Những tham số quan trọng:

| Đầu vào | Vai trò |
| --- | --- |
| `bytes` | Class file bytes hợp lệ; `this_class` chỉ đến một class trong cùng package với lookup class |
| `initialize` | `true`: JVM khởi tạo hidden class sau khi derive/link; `false`: cho phép trì hoãn initialization tới lần sử dụng phù hợp |
| `options` | Các `ClassOption` như `NESTMATE`, `STRONG`; có thể không truyền option nào |
| `hiddenLookup` | `Lookup` trả về mà `lookupClass()` chính là hidden class mới |
| `hiddenType` | `Class<?>` đại diện hidden class, dùng được với reflection và nhiều API nhận `Class<?>` |

`Lookup` dùng để tạo hidden class cần **full privilege access** theo hợp đồng Java SE 17. Không phải bất kỳ `publicLookup()` hoặc lookup đã bị giảm quyền nào cũng tạo được hidden class.

`defineHiddenClass` không gọi `ClassLoader.defineClass` để đăng ký một binary name thông thường. Thay vào đó, JVM **đánh dấu lookup class's loader là defining loader** của hidden class và tạo class có tên runtime riêng. Class mới dùng:

- **Cùng defining class loader** với lookup class.
- **Cùng module** và **cùng runtime package** với lookup class.
- **Cùng protection domain** với lookup class.
- Một **identity class riêng**, khác mọi lần define khác, kể cả khi bytes gốc giống hệt.

Cùng loader/package không có nghĩa mặc định được truy cập mọi `private` member của lookup class: phần quyền riêng tư do **nest relationship** điều khiển.

Không gọi nhầm `Lookup.defineClass(bytes)` (tạo **named class**) với `Lookup.defineHiddenClass(bytes, ...)`. Named class thường được tìm bằng binary name theo quy tắc loader; hidden class được thiết kế không có binary name có thể liên kết từ các class khác.

## 3. Bảng so sánh bốn cấu hình

Cùng một lookup đầy quyền, cùng bytecode và cùng loader:

| Cấu hình | Nest host của hidden class | Được quyền nest-based private access tới host? | Chính sách có thể unload khi loader vẫn reachable |
| --- | --- | --- | --- |
| Không option | Chính hidden class (nest riêng) | **Không** chỉ nhờ cùng loader/package | **Có thể**, nếu không còn nguồn giữ sống |
| `NESTMATE` | Nest host của lookup class | **Có**, với các member cùng nest | **Có thể**, vì chưa bật `STRONG` |
| `STRONG` | Chính hidden class (nest riêng) | **Không** chỉ vì `STRONG` | **Không**, nếu defining loader còn reachable |
| `NESTMATE, STRONG` | Nest host của lookup class | **Có** | **Không**, nếu defining loader còn reachable |

Cột unload nói về **điều kiện đủ để class đủ tư cách bị thu hồi**, không phải lời hứa JVM sẽ lập tức unload. Class vẫn có thể bị giữ bởi object instances, method handles, lookup references, class literals/references, callback registration hoặc code đang thực thi.

**`NESTMATE` là trục quyền truy cập. `STRONG` là trục vòng đời.** Việc kết hợp hai option chỉ đồng thời áp dụng hai chính sách này; thứ tự các option trong varargs không tạo thêm tính năng mới.

## 4. Nest và nestmate là gì?

Từ Java 11, các class/interface có thể nằm trong cùng **nest**. Một class đóng vai **nest host**, các class khác được JVM công nhận là **nestmates** của nhau và có thể truy cập `private` member của nhau theo nest-based access control.

Với Java source:

```java
public final class Owner {
    private static String secret() {
        return "secret";
    }

    static class Helper {
        static String read() {
            return secret();
        }
    }
}
```

Đây là **mảnh mã minh họa**, không phải ví dụ chính. `javac` thông thường tạo metadata `NestHost`/`NestMembers` trong class files để `Helper` và `Owner` là nestmates. Truy cập `private static Owner.secret()` từ `Helper` là hợp lệ khi cả hai thực sự cùng nest.

Khi dùng `defineHiddenClass`, JVM không đơn giản giữ nguyên `NestHost` ghi trong class-file bytes:

- **Mặc định**: hidden class có **nest riêng**, với chính nó làm nest host.
- **Có `NESTMATE`**: JVM đặt nest host của hidden class thành **nest host của lookup class** được dùng để define.
- Nest được quyết định lúc tạo hidden class, không dựa vào `NestHost` attribute ban đầu của bytes.
- Việc gia nhập nest **không viết lại `NestMembers` attribute** của host class file, và class host có thể đã được nạp từ rất lâu.

Vì thế, cùng một file class được compiler tạo thành nested class nhưng khi được **define lại như hidden** mà không dùng `NESTMATE`, nó **không tự kế thừa** quyền private đối với outer host.

### Những phép hỏi quan trọng

```java
Class<?> host = hiddenType.getNestHost();
boolean canAccessAsNestmate = hiddenType.isNestmateOf(Owner.class);
```

Đây là **mã minh họa** sử dụng `hiddenType` và `Owner` đã có. `getNestHost()` cho biết nest host thực tế tại runtime. `isNestmateOf` so sánh nest hosts, là phép hỏi phù hợp để kiểm tra nest relationship.

`Class.getNestMembers()` có một giới hạn tinh tế: **mảng trả về chỉ bao gồm các nest members được ghi trong `NestMembers` attribute của host**, không thêm các hidden classes mới được gắn vào nest thông qua `Lookup.defineHiddenClass`. Vì vậy:

```text
hiddenClass.isNestmateOf(hostClass) == true
```

**không mâu thuẫn** với việc bạn không thấy `hiddenClass` trong `hostClass.getNestMembers()`.

## 5. `NESTMATE` cho quyền private, nhưng không phải quyền vô hạn

Khi hidden class là nestmate của lookup class, nó có thể truy cập `private` methods, fields và constructors của các classes thực sự thuộc cùng nest; JVM vẫn xác minh bytecode, class accessibility và những điều kiện khác.

Không nên suy rộng:

- `NESTMATE` **không** cho quyền vào mọi private member của **mọi class cùng package**.
- `NESTMATE` **không** tạo quan hệ đọc tới module bất kỳ, mở package khác, hay tự sửa JPMS `exports/opens`.
- `NESTMATE` **không** biến hidden class thành subclass của host; nest và inheritance là **hai quan hệ khác nhau**.
- `NESTMATE` **không** có nghĩa hidden class được tìm theo tên bằng `Class.forName`.
- `NESTMATE` **không** khiến hidden class buộc phải sống tới lúc loader bị thu hồi; đó là công việc của `STRONG`.

Ngược lại, một hidden class **không là nestmate** vẫn có quyền truy cập những public/package-private members mà Java access control thực sự cho phép. Khi method riêng tư của host bị gọi bất hợp pháp từ bytecode của hidden class, JVM có thể ném **`IllegalAccessError` tại thời điểm liên kết/giải quyết lời gọi**. Điều này **khác** với `IllegalAccessException` khi một `Lookup.find*` factory không thể tạo method handle.

Ví dụ ở mục 8 minh họa sự khác biệt bằng cùng một `Payload.class` được define thành bốn class khác nhau.

## 6. `STRONG` là quan hệ lifecycle với loader, không phải keyword “giữ mãi mãi”

Theo Java SE 17, một class thông thường có quan hệ mạnh với **defining class loader**: class có thể unload **khi và chỉ khi** loader ấy không còn reachable để GC có thể thu hồi. `ClassOption.STRONG` yêu cầu hidden class tuân theo quan hệ này.

Điều đó không có nghĩa:

- `STRONG` làm class **bất tử** đến lúc JVM tắt trong mọi ứng dụng. Loader có thể không còn reachable, và class có thể unload cùng loader.
- `STRONG` tự ghim class loader vĩnh viễn. Cần xét các đường tham chiếu và tài nguyên thực tế.
- `STRONG` cho quyền truy cập private hoặc giúp kiểm tra nestmate.
- `STRONG` bắt buộc dùng cho tất cả hidden classes.
- `Class.getClassLoader()` trả một loại loader khác giữa strong và default hidden class. Trong ví dụ, cả bốn biến thể dùng **cùng defining loader**.

**Nếu defining loader luôn reachable** (ví dụ app class loader của tiến trình server còn sống), class ẩn dùng `STRONG` có chính sách unload giống class thường trong loader đó. Việc liên tục generate nhiều strong hidden classes có thể làm tăng tiêu thụ metaspace, vì chúng không thể được unload độc lập trong khi loader vẫn sống.

**Nếu không chọn `STRONG`**, hidden class mặc định có thể unload độc lập với loader khi không còn được giữ sống; đây là lợi thế cho runtime tạo nhiều class ngắn hạn, ví dụ những implementation cho lambda-like constructs, DSL, adapters hoặc generated functions.

### Có `NESTMATE` nhưng không có `STRONG` thì sao?

Hidden class được thêm vào nest không buộc JVM phải giữ nó sống mãi với nest host. `NESTMATE` quyết định quyền kiểm tra truy cập. Hidden class vẫn có **lifecycle mặc định** nếu không bật `STRONG`, nên có thể unload trong khi host và loader vẫn reachable khi không còn những references khác giữ nó sống.

### Có `STRONG` nhưng không có `NESTMATE` thì sao?

Hidden class được gắn lifecycle vào defining loader, nhưng nest host vẫn là **chính hidden class**. Nó không được truy cập private member của lookup class chỉ vì cùng loader, cùng package hoặc vì tồn tại lâu hơn.

## 7. Bộ nạp lớp nào thực sự “sở hữu” hidden class?

`Lookup.defineHiddenClass` không nhận đối số `ClassLoader` như `Proxy.newProxyInstance`. Nó dùng **defining class loader của lookup class** hiện tại.

Ví dụ minh họa:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
ClassLoader expected = lookup.lookupClass().getClassLoader();

MethodHandles.Lookup hidden = lookup.defineHiddenClass(
        bytes, false, MethodHandles.Lookup.ClassOption.STRONG);

boolean sameLoader =
        hidden.lookupClass().getClassLoader() == expected;
```

Mã minh họa này cần `bytes` hợp lệ và `Lookup` đầy quyền; không chạy độc lập. Kết quả `sameLoader` là `true` theo contract `defineHiddenClass`.

**Cẩn thận với tên gọi “class loader”:**

- **Defining loader**: loader được JVM gắn cho class.
- **Initiating loader**: loader có thể được ghi nhận khi `loadClass` khởi tạo quá trình nạp class thông thường.
- Với hidden class, JVM gắn defining loader của lookup class nhưng **không ghi nhận initiating loader** theo cách một class thông thường được discover bằng binary name.

`Thread.currentThread().getContextClassLoader()` **không tự quyết định** defining loader cho hidden class nếu bạn không dùng ngữ cảnh ấy để chọn lookup class. Vì vậy, muốn hidden class sống cùng một plugin có loader riêng, phải **lấy một Lookup có quyền hợp lệ trong module/package của plugin**, không chỉ đổi thread context class loader.

Khi plugin loader bị giữ bởi một static registry ở app class loader, việc plugin bị “disable” ở UI không đủ chứng minh loader đã unreachable. Cần xét cache và các references xuyên loader; `STRONG` còn tăng mức giữ các hidden classes cùng loader.

## 8. Chương trình Java 17+ đầy đủ: bốn tùy chọn và private access

Lưu toàn bộ file sau với tên chính xác **`HiddenClassOptionsDemo.java`**. Chương trình không cần ASM hoặc dependency bên ngoài; nó dùng **một nested class được `javac` biên dịch thành `.class`** như template bytes để định nghĩa lại thành hidden class.

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

import static java.lang.invoke.MethodHandles.Lookup.ClassOption.NESTMATE;
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.STRONG;

public final class HiddenClassOptionsDemo {
    private static String secret() {
        return "private-ok";
    }

    public static class Payload {
        public static String callHostSecret() {
            return HiddenClassOptionsDemo.secret();
        }
    }

    private static String invoke(MethodHandles.Lookup lk) throws Throwable {
        MethodHandle mh = lk.findStatic(
                lk.lookupClass(), "callHostSecret",
                MethodType.methodType(String.class));
        return (String) mh.invokeExact();
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream stream =
                     HiddenClassOptionsDemo.class.getResourceAsStream(
                             "HiddenClassOptionsDemo$Payload.class")) {
            if (stream == null) {
                throw new IllegalStateException("Payload class resource missing");
            }
            bytes = stream.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();

        MethodHandles.Lookup plain =
                host.defineHiddenClass(bytes, true);
        MethodHandles.Lookup nest =
                host.defineHiddenClass(bytes, true, NESTMATE);
        MethodHandles.Lookup strong =
                host.defineHiddenClass(bytes, true, STRONG);
        MethodHandles.Lookup both =
                host.defineHiddenClass(bytes, true, NESTMATE, STRONG);

        Class<?> p = plain.lookupClass();
        Class<?> n = nest.lookupClass();
        Class<?> s = strong.lookupClass();
        Class<?> b = both.lookupClass();

        System.out.println("hidden=" + p.isHidden());
        System.out.println("sameLoader=" +
                (p.getClassLoader() ==
                        HiddenClassOptionsDemo.class.getClassLoader()));
        System.out.println("sameModule=" +
                (p.getModule() == HiddenClassOptionsDemo.class.getModule()));
        System.out.println("samePackage=" +
                p.getPackageName().equals(
                        HiddenClassOptionsDemo.class.getPackageName()));
        System.out.println("defaultNestSelf=" + (p.getNestHost() == p));
        System.out.println("strongNestSelf=" + (s.getNestHost() == s));
        System.out.println("nestHostIsOwner=" +
                (n.getNestHost() == HiddenClassOptionsDemo.class));
        System.out.println("bothNestHostIsOwner=" +
                (b.getNestHost() == HiddenClassOptionsDemo.class));
        System.out.println("ownerIsNestmate=" +
                HiddenClassOptionsDemo.class.isNestmateOf(n));
        System.out.println("strongOnlyNotNestmate=" +
                !HiddenClassOptionsDemo.class.isNestmateOf(s));

        try {
            System.out.println("plainPrivate=" + invoke(plain));
        } catch (IllegalAccessError expected) {
            System.out.println("plainPrivate=denied");
        }

        System.out.println("nestPrivate=" + invoke(nest));

        try {
            System.out.println("strongPrivate=" + invoke(strong));
        } catch (IllegalAccessError expected) {
            System.out.println("strongPrivate=denied");
        }

        System.out.println("bothPrivate=" + invoke(both));
        System.out.println("distinctClasses=" +
                (p != n && n != s && s != b));

        try {
            Class.forName(n.getName(), false, n.getClassLoader());
            System.out.println("byName=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("byName=unavailable");
        }

        System.out.println("enumeratedNest=" +
                Arrays.asList(HiddenClassOptionsDemo.class.getNestMembers())
                        .contains(n));
    }
}
```

### 8.1. Biên dịch và chạy

Ở thư mục chứa file, dùng JDK 17 trở lên:

```bash
javac --release 17 HiddenClassOptionsDemo.java
java HiddenClassOptionsDemo
```

`javac` tạo ít nhất:

```text
HiddenClassOptionsDemo.class
HiddenClassOptionsDemo$Payload.class
```

Code lấy bytes của tệp thứ hai qua `getResourceAsStream` và đưa **cùng bytes** vào bốn lệnh `defineHiddenClass`. Cả bốn lệnh tạo **các class identities riêng**, không sửa `Payload.class` trên ổ đĩa.

### 8.2. Stdout chính xác đã kiểm tra

```text
hidden=true
sameLoader=true
sameModule=true
samePackage=true
defaultNestSelf=true
strongNestSelf=true
nestHostIsOwner=true
bothNestHostIsOwner=true
ownerIsNestmate=true
strongOnlyNotNestmate=true
plainPrivate=denied
nestPrivate=private-ok
strongPrivate=denied
bothPrivate=private-ok
distinctClasses=true
byName=unavailable
enumeratedNest=false
```

Đây là output được xác minh khi biên dịch bằng `javac --release 17` và chạy trên JDK hỗ trợ Java 17. Chương trình cố ý **không in tên hidden class đầy đủ**, vì hậu tố được JVM sinh không cố định giữa các lần chạy.

## 9. Phân tích đầu ra: `NESTMATE` khác `STRONG` ở chỗ nào?

### 9.1. Bốn class khác nhau, cùng loader/module/package

```text
hidden=true
sameLoader=true
sameModule=true
samePackage=true
```

`isHidden()` xác minh `plain` là hidden class. Các phép so sánh tiếp theo chứng minh JVM gắn nó vào môi trường nạp của lookup class theo API. Nếu class host nằm trong một named module, hidden class cùng module đó; ví dụ chạy trên classpath nên cả hai nằm trong unnamed module.

`distinctClasses=true` nghĩa là **mỗi lần `defineHiddenClass` tạo identity mới**. Cùng bytes hay cùng tên `this_class` trong file gốc không làm bốn lần define trả về một class duy nhất.

### 9.2. Quyền nest có thể quan sát trực tiếp

```text
defaultNestSelf=true
strongNestSelf=true
nestHostIsOwner=true
bothNestHostIsOwner=true
ownerIsNestmate=true
strongOnlyNotNestmate=true
```

Mặc dù `Payload` là nested class trong source Java (và compiler có thể ghi `NestHost` trong bytecode), hidden class tạo **không có `NESTMATE`** trở thành nest riêng. Điều đó xảy ra với cả `plain` và `strong`.

Ngược lại, `nest` và `both` được thêm vào nest của `HiddenClassOptionsDemo` nhờ option `NESTMATE`. `getNestHost()` phản ánh đúng nest host runtime, không dựa vào việc nội dung bytes gốc trông giống nested class.

### 9.3. `IllegalAccessError` chứng minh quyền private bị từ chối

```text
plainPrivate=denied
nestPrivate=private-ok
strongPrivate=denied
bothPrivate=private-ok
```

Phương thức `Payload.callHostSecret()` có code gọi:

```java
HiddenClassOptionsDemo.secret();
```

Đó là private static method của host. Cùng lệnh gọi ấy:

- **Không có `NESTMATE`**: hidden class không ở cùng nest, nên JVM từ chối lời gọi private. Chương trình bắt đúng `IllegalAccessError`.
- **Có `NESTMATE`**: hidden class được coi là nestmate, nên lời gọi private thành công và trả `private-ok`.
- **Chỉ `STRONG`**: không thay đổi nest rights; vẫn bị từ chối.
- **Có cả hai**: cùng quyền private như `NESTMATE`, đồng thời có lifecycle policy của `STRONG`.

Đây là thí nghiệm quan trọng nhất của bài: **`STRONG` không phải cơ chế cấp quyền**.

Hàm `invoke(lk)` ở phía host dùng `lk.findStatic(...)` để lấy handle tới **public method `callHostSecret` của hidden class**. Lệnh tạo handle ấy thành công vì lookup trả từ `defineHiddenClass` gắn với chính hidden class. Sau đó, khi `invokeExact()` làm method chạy và bytecode cố gọi `secret()` private ở host, JVM mới phát hiện lỗi nest access.

Vì vậy **lỗi quan sát được là `IllegalAccessError` trong bytecode của hidden class**, không phải `IllegalAccessException` do chính `findStatic` từ chối. Hai loại lỗi xuất hiện ở hai bước khác nhau; điều này cần phân biệt khi debug.

### 9.4. Tên hidden không phải binary name tra cứu được

```text
byName=unavailable
```

Hidden class có tên runtime mà `Class.getName()` thường có dạng như:

```text
HiddenClassOptionsDemo$Payload/0x0000... 
```

Đây chỉ là **hình dạng minh họa**, không phải tên cố định để copy. Phần sau dấu `/` do JVM tạo, có thể khác giữa hai lần chạy, và tên đó không có tính chất của một binary name hợp lệ cho class loading bình thường.

`Class.forName(hiddenClass.getName(), false, loader)` không tìm được hidden class theo hợp đồng API. Nhưng bạn **vẫn có** thể giữ `Class<?>` lấy từ `lookup.lookupClass()`, dùng reflection trên class đó, tạo `MethodHandle`, hoặc tạo instances khi bytecode/class phù hợp.

**“Hidden” không có nghĩa class không ai truy cập được**, chỉ là nó không được link và discover theo nominal binary name thông thường.

### 9.5. Vì sao `getNestMembers()` không liệt kê hidden nestmate?

```text
enumeratedNest=false
```

`HiddenClassOptionsDemo.class.getNestMembers()` phản ánh các classes được ghi trong `NestMembers` attribute của host. Một hidden class gia nhập nest **động** không được thêm vào attribute đã tồn tại trong class file. Do đó output `false` không làm sai sự thật `ownerIsNestmate=true`.

Theo Java SE 17, **`getNestMembers()` không bao gồm hidden classes được thêm bằng `defineHiddenClass`**, nên muốn kiểm tra một hidden class cụ thể, dùng `hiddenType.getNestHost()` hoặc `hiddenType.isNestmateOf(hostType)`.

## 10. Vì sao `Payload.class` có `NestHost` mà hidden mặc định vẫn không cùng nest?

Dùng lệnh:

```bash
javap -v -p 'HiddenClassOptionsDemo$Payload'
```

Trong Bash và PowerShell, dấu nháy đơn quanh tên class giúp tránh shell xử lý ký tự `$`. `javap` ở thí nghiệm xác nhận:

```text
major version: 61
NestHost: class HiddenClassOptionsDemo
```

Đoạn này **trích yếu thông tin**, không phải toàn bộ output `javap`. File template được `javac` biên dịch từ nested class và có `NestHost` ghi đúng host của class **mang tên bình thường**.

Nhưng `Lookup.defineHiddenClass(bytes, ..., options)` là một cơ chế class derivation **khác**. Với hidden class, JVM **không dùng `NestHost` attribute trong bytes để quyết định nest host**. `NESTMATE` mới là yếu tố yêu cầu JVM thêm class mới vào nest của lookup class.

Sự khác nhau:

```text
Tên class thông thường:
  compiler metadata NestHost -> xác nhận nest của named Payload

Hidden class được define lại từ cùng bytes:
  không NESTMATE  -> nest của chính hidden class
  có NESTMATE     -> nest của lookup class
```

Đây là lý do thí nghiệm có giá trị: có thể kiểm chứng mà không cần dùng bytecode emitter bên ngoài. Đồng thời, nó nhắc rằng **class file giống nhau không luôn dẫn tới các quy tắc runtime giống nhau** nếu cách định nghĩa class khác nhau.

## 11. Quan hệ reachability, class unloading và GC

Trọng tâm của `STRONG` không phải output của một API boolean như `getNestHost()`, mà là **quy tắc JVM xác định liệu hidden class có thể unload khi loader còn reachable hay không**.

### 11.1. Default hidden class — có thể unload độc lập

Theo hợp đồng Java SE 17, khi không có `STRONG`, JVM **có thể** unload một hidden class dù defining loader vẫn còn reachable. Điều đó đặc biệt hữu ích nếu:

- Một framework generate hàng nghìn handler/adapters ngắn hạn.
- Các generated functions được gắn với một request, expression tree hoặc một đoạn script ngắn hạn.
- Một library tạo implementation classes cho nhiều cấu hình rồi bỏ chúng khi không còn consumer.
- Bạn không muốn mọi hidden class tồn tại đến tận khi application/plugin class loader được thu hồi.

**Tuy vậy, “có thể unload” không phải “chắc chắn unload”.** Nếu có strong reference tới `Class<?>` của hidden class, một live instance, một `MethodHandle` liên kết tới method của nó, hoặc một `Lookup` đang được giữ, JVM có thể vẫn coi class ấy là reachable. Các metadata/call-site caches cũng có thể duy trì đường tham chiếu liên quan.

Sử dụng `WeakReference<Class<?>>` để quan sát class sau GC là một công cụ **quan sát**, không thay đổi mặc định unload policy của JVM. Không được gắn kết quả `ref.get() != null` của một thời điểm với kết luận “không thể unload”.

### 11.2. Strong hidden class — cùng điều kiện unload với class bình thường

Có `STRONG`, hidden class có strong relationship với **defining loader**. Nếu loader vẫn reachable thì class **không đủ điều kiện** unload độc lập, ngay cả khi ứng dụng đã bỏ mọi reference trực tiếp tới `Class<?>` và objects của hidden class.

Nếu loader không còn reachable, hidden class `STRONG` *có thể* unload cùng loader, nhưng GC/JVM quyết định thời điểm thực tế; **không bảo đảm ngay lập tức**.

Ứng dụng server nạp tất cả hidden classes qua app class loader, rồi tạo thêm strong classes liên tục, có thể giữ nhiều class metadata cho tới khi tiến trình kết thúc. Đây là một lý do phải lựa chọn `STRONG` dựa trên lifecycle yêu cầu, không bật mặc định để “an toàn hơn”.

### 11.3. Những reference thường vô tình giữ hidden class sống

Hãy xem các nơi có thể lưu lại class/capability:

- `Class<?>` được đặt trong `static final` map/list.
- `MethodHandles.Lookup` mà `lookupClass()` là hidden class.
- `MethodHandle`/`VarHandle` tham chiếu tới members của hidden class.
- Instances của hidden class hoặc wrappers nắm giữ chúng.
- Callback registrations, global event buses, scheduled tasks và threads đang thực thi code của hidden class.
- Framework caches, static field của một class sống lâu, hoặc những cấu trúc object graph xuyên class loader.
- Một call site đã liên kết tới target handle của hidden class và bản thân call site còn sống.

Đây là **các đường giữ sống có thể xảy ra**, không phải danh sách khẳng định mọi JVM tạo cùng graph đối tượng nội bộ. Cần đo trong hệ thống thật bằng profiler/heap dump/class unloading events.

Trong trường hợp có `STRONG`, ngay cả việc xóa một số references trên **không làm class đủ điều kiện unload** nếu defining loader vẫn reachable. Trong trường hợp mặc định, loại bỏ những references ấy **có thể** mở đường cho unload, nhưng không ra lệnh cho JVM phải làm ngay.

## 12. Không đo unload bằng một lần `System.gc()` rồi coi là chân lý

Một đoạn thử nghiệm phổ biến:

```java
WeakReference<Class<?>> ref = ...;   // sau khi tạo hidden class
System.gc();
System.out.println(ref.get() == null);
```

Đây là **mã minh họa không chạy độc lập**. Kết quả phụ thuộc JVM, GC configuration, reachability thực, timing, JIT và các references mà code vẫn giữ. `System.gc()` chỉ là lời gợi ý, có thể bị bỏ qua hoặc không thu hồi class ngay.

**Đặc biệt:** code đang ở giữa method còn giữ local `hiddenLookup`, `hiddenClass` hoặc handle sẽ có thể khiến hidden class vẫn reachable. Thậm chí khi lập trình viên cho rằng biến đã “hết sử dụng”, compiler/JIT có thể có liveness/lifetime khác với suy luận từ source.

Khi cần nghiên cứu vòng đời:

1. Tạo hidden class trong một scope/factory riêng, tránh giữ `Lookup`/`Class<?>`/instances trong caches lâu.
2. Trả ra `WeakReference<Class<?>>` cùng `ReferenceQueue<Class<?>>` nếu cần theo dõi.
3. Thả toàn bộ strong references ngoài probe; xác minh không có registry hoặc target handle khác giữ class.
4. Quan sát qua nhiều GC cycles/điều kiện bộ nhớ trong môi trường kiểm soát.
5. Với HotSpot, có thể bổ sung unified logging, ví dụ `-Xlog:class+unload=info` để xem class unloading events (nếu có).
6. So sánh nhiều runs, không dựa vào một số đo đơn lẻ.
7. Không viết unit test đòi “phải được GC trong N mili-giây” làm điều kiện pass.

Một **test hợp đồng đáng tin** cho `STRONG`/default phải kiểm đúng lựa chọn option và các quy tắc tài liệu; không nên dùng GC nondeterminism làm assertion bắt buộc.

### Liên quan `ReferenceQueue`

`ReferenceQueue` có thể thông báo rằng một reference đã bị clear/enqueued khi GC thực sự thu hồi referent theo chính sách của VM. Nó không phải bộ điều khiển class unloading. Nếu không có sự kiện trong một khoảng thời gian, không thể kết luận class đã trở thành strong hidden class. Với `STRONG`, thậm chí reference tới `Class<?>` trong Java có thể bị loại khỏi app object graph nhưng class vẫn được VM giữ theo quan hệ mạnh với loader.

## 13. Vòng đời class loader trong plugin và hot reload

Giả sử một ứng dụng có:

```text
Application loader (sống rất lâu)
    |
    +-- Plugin loader #1 -> plugin classes -> hidden classes
    |
    +-- Plugin loader #2 -> plugin classes -> hidden classes
```

Chính **lookup class** quyết định defining loader. Nếu generator dùng lookup từ code application loader, hidden class có defining loader của application, **không** tự chuyển sang plugin loader chỉ vì plugin gọi generator.

Khi muốn hidden classes thuộc vòng đời của plugin:

- Lấy lookup có quyền hợp lệ trong class/module/package của plugin.
- Verify `hiddenClass.getClassLoader() == pluginClass.getClassLoader()` theo thiết kế.
- Đảm bảo không có registry hoặc callback từ application giữ reference tới plugin loader/classes/handles sau khi unload plugin.
- Chỉ dùng `STRONG` nếu hidden class **cần** có cùng lifetime coupling với plugin loader; nếu muốn nhiều generated classes được thu hồi riêng trong khi plugin chạy, bỏ `STRONG`.
- Phân biệt **class unloading** với thao tác xóa file JAR hoặc đóng `URLClassLoader`: `close()` giải phóng một số tài nguyên, **không** bảo đảm loader và classes đã unreachable/unloaded.
- Tránh kiểm thử bằng cách “thay ContextClassLoader rồi gọi `defineHiddenClass`” nếu lookup class vẫn thuộc application loader; kết quả vẫn gắn với defining loader của lookup class.

Nếu một plugin loader được reference bởi application static map, chưa thể unload plugin dù bạn đặt mọi generated class thành weak hidden class. `STRONG` không phải nguyên nhân duy nhất của memory leak; cần kiểm tra toàn bộ object graph.

## 14. `initialize` là tham số độc lập với cả `NESTMATE` lẫn `STRONG`

`defineHiddenClass(bytes, boolean initialize, ClassOption... options)` có `initialize` riêng:

- `initialize=true`: JVM khởi tạo class sau khi derive/link, trước khi API trả lookup.
- `initialize=false`: cho phép hoãn khởi tạo, theo quy tắc class initialization khi method/field/constructor được sử dụng.

Nó **không** làm thay đổi:

- Nest host.
- Strong/weak unloading policy.
- Defining loader.
- Khả năng tra cứu bằng `Class.forName`.

Ví dụ minh họa trong code có static initializer:

```java
static {
    System.out.println("Hidden class initialized");
}
```

Đây chỉ là **một đoạn khai báo trong class template**, không phải chương trình độc lập. Nếu dùng `initialize=true`, output initializer xuất hiện khi định nghĩa hidden class. Nếu `false`, việc gọi một static method hoặc truy cập static field phù hợp có thể kích hoạt initialization sau đó.

**Không nên dùng số lần initializer in log để suy ra unload policy**. Một class đã khởi tạo có thể vẫn unload nếu chính sách và reachability cho phép; một class chưa khởi tạo không tự có quyền private.

Với template có tác dụng phụ ở `<clinit>`, bật `initialize=true` cần cân nhắc vì lỗi initialization có thể xuất hiện ngay trong `defineHiddenClass` và để lại trạng thái lỗi theo quy tắc JVM. Thí nghiệm chính dùng template không có static initializer để output ổn định.

## 15. `Lookup` trả về và quyền của hidden class

Khi `defineHiddenClass` thành công, API trả một `MethodHandles.Lookup` có **lookup class là hidden class mới**, với quyền phù hợp theo đặc tả. Đối tượng này là một **capability**:

```java
MethodHandles.Lookup hidden = hostLookup.defineHiddenClass(bytes, true);
Class<?> c = hidden.lookupClass();
MethodHandle mh = hidden.findStatic(
        c, "run", MethodType.methodType(String.class));
```

Đây là **mã minh họa**, `hostLookup` và `bytes` phải có sẵn; hidden class phải khai báo `static String run()`. Lookup được trao có thể tra cứu members của chính hidden class, kể cả private members trong phạm vi quyền của lookup đó.

Rủi ro thiết kế:

- Nếu vô tình chia sẻ full-privilege hidden lookup cho plugin khác, plugin có thể tìm thêm members của hidden class mà nhà cung cấp không muốn phơi bày.
- Nếu hidden class là `NESTMATE`, việc chia sẻ lookup phù hợp còn có thể mang **quyền truy cập trong nest** theo Java access checks; đây là capability nhạy cảm.
- Một `MethodHandle` tới một operation cụ thể thường là capability **hẹp hơn** một Lookup đầy quyền.
- Việc giữ `Lookup`, `Class<?>` hay `MethodHandle` trong một cache sống lâu còn ảnh hưởng **reachability** của hidden class mặc định.

Từ góc nhìn bảo mật và tài nguyên, phải thiết kế **cả hai**: quyền gọi/truy cập và vòng đời references. `STRONG` không phải cách cấp quyền, còn `NESTMATE` không phải policy GC.

## 16. Tên hidden class và cách truy cập sau khi định nghĩa

Đặc tả Java SE 17 nói `Class.getName()` của hidden class có thêm hậu tố runtime, ví dụ:

```text
com.example.Generated/0x0000000800123456
```

Đây là **ví dụ hình dạng**, không phải tên cố định từ code đã chạy. Ký tự `/` và suffix khiến tên này **không phải binary name thông thường** có thể đem tới:

```java
Class.forName(hiddenType.getName(), false, hiddenType.getClassLoader());
```

Đoạn này sẽ không resolve hidden class theo cơ chế lookup nominal bình thường. Điều đó **không** có nghĩa `hiddenType` không thể dùng:

- `hiddenType.isHidden()` xác nhận là hidden.
- `hiddenType.getNestHost()` và `hiddenType.isNestmateOf(...)` kiểm tra quan hệ nest.
- `hiddenType.getClassLoader()` trả defining loader gắn với class.
- `hiddenType.getDeclaredMethods()` có thể quan sát members.
- `MethodHandles.Lookup`/reflection với quyền thích hợp có thể gọi members.
- Một instance có `getClass()` trả lại `Class<?>` hidden class.

Do hidden class không có binary name, những cơ chế đòi tự tái tạo nominal name, như Java serialization mặc định, không phải lúc nào hoạt động. Việc dùng hidden class trong framework cần lưu ý **khả năng lưu/reconstruct bằng tên**, chứ không chỉ quyền private.

### `Class.getNestMembers()` không phải registry cho các hidden nestmates

Một framework muốn “tìm tất cả class được `NESTMATE` thêm vào nest” không thể chỉ gọi `getNestMembers()`. API này phản ánh `NestMembers` attribute được ghi trong class file, không phải toàn bộ các hidden classes được thêm động. Nếu cần quản lý/cleanup các generated hidden classes, framework phải quản lý references/metadata riêng, nhưng hãy chọn **weak tracking** phù hợp để tránh vô tình ngăn unload.

## 17. Cách chọn option cho tình huống thực tế

| Nhu cầu | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| Generated helper cần truy cập private members của host | `NESTMATE` | Tham gia cùng nest để có quyền private |
| Generated helper chỉ dùng public/package members | Không cần `NESTMATE` | Quyền tối thiểu, giới hạn private access |
| Hàng loạt generated classes ngắn hạn trong app loader sống lâu | **Không `STRONG`**, trừ khi có yêu cầu rõ | Mở khả năng unload độc lập để giảm áp lực metaspace |
| Generated class phải còn theo vòng đời của một normal class loader | `STRONG` | Có chính sách unload gắn với loader |
| Helper cần cả private access và loader-coupled lifetime | `NESTMATE, STRONG` | Hai option bổ sung cho hai trục khác nhau |
| Sandbox/plugin untrusted code | Tránh phát full-privilege Lookup và cân nhắc quyền của bytes | `NESTMATE` có thể mở private access nhạy cảm |
| Plugin reload với custom loader ngắn hạn | Chọn lookup/loader đúng; có thể dùng `STRONG` nếu lifetime gắn với plugin loader | Cần đảm bảo loader được thu hồi và không bị static cache giữ |
| Lambda-like runtime tạo vô số classes | Default hidden class thường hợp lý | Có thể unload từng class nếu không còn reference |
| Cần tìm class bằng binary name qua classloader | **Không dùng hidden class** cho yêu cầu ấy | Hidden class không có binary name discoverable |

Không có cấu hình “luôn tốt nhất”. Đưa ra quyết định dựa trên **chính sách truy cập private** và **dự kiến vòng đời loader/generated code**, rồi đo memory/behavior dưới workload thực.

## 18. Những lỗi thường gặp

### 18.1. Có `NESTMATE` nên tin rằng hidden class sẽ sống cùng host

Sai. Nest relationship không xác định policy unload. Nếu không có `STRONG`, hidden class vẫn có thể được thu hồi trong khi loader/host reachable, khi không còn nguồn giữ sống và JVM quyết định unload.

### 18.2. Có `STRONG` nên tin rằng hidden class có quyền đọc private field

Sai. `STRONG` chỉ áp dụng quan hệ lifecycle. Nếu bytes gọi private method của host mà hidden class không là nestmate, JVM có thể phát `IllegalAccessError`, như thí nghiệm.

### 18.3. `NestHost` từ bytes đã đủ cho hidden class

Sai. Hidden class không kế thừa nest từ `NestHost` attribute của bytes. Muốn gia nhập nest của lookup class, phải chọn `NESTMATE` rõ ràng.

### 18.4. `getNestMembers()` không liệt kê nên `isNestmateOf` phải false

Sai. API `getNestMembers()` không liệt kê hidden classes mới được thêm; `getNestHost()` và `isNestmateOf()` thể hiện quan hệ runtime.

### 18.5. Loader giống nhau thì hai class identities giống nhau

Sai. Mỗi lần `defineHiddenClass` tạo class mới. `getClassLoader()` bằng nhau chỉ nói cùng defining loader, không nói `Class<?>` bằng nhau. Source bytes giống nhau cũng không hợp nhất identities.

### 18.6. Gọi `System.gc()` mà không thấy unload nghĩa là default hidden class strong

Sai. JVM có thể chưa chạy GC phù hợp, references vẫn còn, hoặc cách quan sát chưa đúng. Hợp đồng chỉ nói default hidden **có thể** unload khi loader còn reachable, không có SLA thời gian.

### 18.7. `STRONG` đồng nghĩa giữ object/instance sống mãi

Sai. Đối tượng instance bình thường vẫn được GC theo reachability của nó. `STRONG` tác động đến **class unloading**, không làm mọi instance của class trở thành GC root.

### 18.8. Thread context class loader tự quyết định nơi hidden class được định nghĩa

Sai. `defineHiddenClass` dùng defining loader của **lookup class**. Hãy kiểm tra `lookup.lookupClass().getClassLoader()` và `hidden.lookupClass().getClassLoader()`.

### 18.9. Hidden class không thể bị dùng từ bên ngoài vì không `Class.forName`

Sai. Người nhận `Class<?>`, instance, `Lookup` hoặc `MethodHandle` hợp lệ vẫn có thể thao tác với hidden class trong giới hạn quyền. “Hidden” chủ yếu nói về nominal linking/discovery.

### 18.10. Bắt `IllegalAccessException` sẽ giải quyết mọi lỗi private access

Không. Tạo handle bằng Lookup có thể ném `IllegalAccessException`, nhưng bytecode trong hidden class khi được chạy và cố vi phạm Java access control có thể ném `IllegalAccessError`. Phải xác định **lỗi phát sinh ở factory/define hay tại lời gọi trong bytecode**.

## 19. Checklist debug class definition và lifecycle

1. **Đang dùng API nào?** `ClassLoader.defineClass`, `Lookup.defineClass`, hay `Lookup.defineHiddenClass`? Ba cơ chế không đồng nghĩa.
2. **Lookup class là gì?** In `lookup.lookupClass()` hoặc xác định bằng vị trí gọi `MethodHandles.lookup()`.
3. **Lookup đủ quyền không?** `defineHiddenClass` cần full-privilege lookup; không dùng `publicLookup()` làm thay thế.
4. **Bytes hợp lệ không?** Class file version được hỗ trợ, `this_class` cùng package, bytecode verifier chấp nhận.
5. **Defining loader có đúng không?** So `getClassLoader()`, module và runtime package của hidden class với lookup class.
6. **Option có đúng mục tiêu không?** `NESTMATE` cho private nest access, `STRONG` cho loader-coupled unload policy.
7. **Runtime nest đúng không?** Xem `getNestHost()` và `isNestmateOf()`; không phụ thuộc vào `getNestMembers()` như registry.
8. **Lỗi phát sinh ở đâu?** Khi define/link/init class, khi `Lookup.findStatic`, hay khi code hidden thực thi `invokestatic` private member?
9. **Có vòng đời cache nào giữ reference không?** Class/Lookup/MethodHandle/instances/registries/call sites.
10. **Loader còn reachable không?** Hãy xem toàn bộ object graph, không chỉ một biến local hoặc file JAR đã đóng.
11. **Nếu muốn quan sát GC**: dùng heap dump, class loading/unloading logs, weak references và lặp nhiều runs; đừng coi một kết quả `System.gc()` là tiêu chuẩn.
12. **Nếu dùng `STRONG` với loader sống lâu**: tính khả năng tích lũy metaspace khi generate nhiều classes.
13. **Có nhu cầu lookup bằng tên không?** Nếu có, hidden class có thể không phù hợp.
14. **Có vấn đề quyền truy cập bảo mật không?** Xem bytecode được nạp có đáng tin và liệu `NESTMATE`/Lookup có trao private access không mong muốn.
15. **Có self-invocation trong bytes không?** Do hidden class có tên runtime đặc biệt, class-file references tới `this_class` được JVM xử lý theo quy tắc hidden class; không tự suy ra sẽ nạp một named class khác cùng template name.

## 20. Bài tập tự kiểm tra có đáp án

1. **Hai option giải quyết hai câu hỏi nào?** `NESTMATE` giải quyết *nest-based private access*; `STRONG` giải quyết *class unloading liên hệ với defining loader*.
2. **Default hidden class có phải strong theo loader không?** Không. Nó có thể unload khi loader vẫn reachable.
3. **`STRONG` có bảo đảm class không bao giờ unload?** Không. Loader có thể không còn reachable và JVM có thể unload.
4. **`NESTMATE` có đồng nghĩa class sẽ sống cùng nest host?** Không.
5. **`NESTMATE` có cho quyền private trong mọi class cùng package?** Không; chỉ trong cùng nest theo Java access rules.
6. **`STRONG` có giúp method trong hidden class gọi `private` method của host không?** Không, nếu thiếu nest relationship thích hợp.
7. **Nếu nested template class đã có `NestHost`, define hidden không option có giữ nest cũ không?** Không; hidden class mặc định có nest riêng.
8. **Cách kiểm tra nest host của hidden class?** `hiddenType.getNestHost()`.
9. **Cách xác định hidden class có là nestmate của host?** `hiddenType.isNestmateOf(hostType)`.
10. **Vì sao `host.getNestMembers()` có thể thiếu hidden nestmate?** Nó chỉ liệt kê nest members ghi trong `NestMembers` attribute, không bao gồm hidden additions.
11. **Có thể nạp hidden class bằng `Class.forName(hidden.getName())` không?** Không theo nominal class loading thông thường.
12. **Mỗi lần `defineHiddenClass` với cùng bytes có tạo class riêng không?** Có.
13. **Defining loader của hidden class đến từ đâu?** Defining loader của `lookup.lookupClass()`.
14. **Đổi thread context class loader có tự đổi defining loader không?** Không.
15. **`initialize=true` có bật `STRONG` ngầm không?** Không; initialization là một tham số độc lập.
16. **Nếu có `Lookup` đến hidden class, class có chắc có thể unload ngay không?** Không; lookup reference có thể giữ class reachable.
17. **Vì sao `System.gc()` không thích hợp làm assertion về unload?** GC không có bảo đảm về thời điểm/độ bao phủ và code có thể còn references.
18. **Khi app loader sống lâu, dùng `STRONG` cho hàng vạn generated classes có rủi ro gì?** Tích lũy class metadata/metaspace vì class không unload độc lập.
19. **Nếu muốn generated helper nhìn thấy private của host nhưng vẫn có thể unload khi loader còn sống, chọn gì?** `NESTMATE` **không có** `STRONG`.
20. **Nếu muốn đồng thời private nest access và unload theo loader, chọn gì?** `NESTMATE, STRONG`.
21. **Vì sao `plainPrivate=denied` là `IllegalAccessError` chứ không phải lỗi compiler?** Bytes hợp lệ được derive thành hidden class có nest mới; lỗi truy cập private xuất hiện khi runtime resolve/thực thi lời gọi trong hidden bytecode.
22. **Có nên chia sẻ full-privilege hidden `Lookup` cho plugin không tin cậy?** Không, trừ khi đã đánh giá và chủ động ủy quyền capability với phạm vi truy cập phù hợp.
23. **Hidden class có thể có cùng module và protection domain với host không?** Có; đây là contract khi define từ Lookup.
24. **Có cần ASM để chạy bài thực hành chính không?** Không. Chỉ cần `javac` tạo nested template `.class`, rồi đọc bytes bằng `getResourceAsStream`.

## 21. Tài liệu chuẩn Java SE 17

- [Java SE 17 — `MethodHandles.Lookup.defineHiddenClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): quyền của lookup, điều kiện cùng package, tên hidden, loader, nest, unloading, class verification và các exceptions.
- [Java SE 17 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): mô tả chính thức `NESTMATE` và `STRONG`.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isHidden`, `getNestHost`, `isNestmateOf`, `getNestMembers`, `getClassLoader`.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): động cơ thiết kế và khả năng loại bỏ hidden classes không còn cần thiết.
- [JVMS Java SE 17 — §5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): ngữ nghĩa nest-based access.
- [JLS Java SE 17 — §12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): điều kiện class unloading với class loaders.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xác minh `NestHost`/class file metadata của template.

**Kết luận:** Hãy chọn `NESTMATE` **chỉ khi hidden class thực sự cần quyền private trong cùng nest**; chọn `STRONG` **chỉ khi muốn lifecycle của hidden class gắn với defining class loader**. Mặc định, hidden class có thể unload độc lập với loader. Hai tùy chọn không thay thế nhau; kiểm tra `getNestHost()` và `isNestmateOf()` cho quyền, còn class unloading phải được đánh giá theo reachability và chính sách GC, không bằng một lần gọi `System.gc()`.