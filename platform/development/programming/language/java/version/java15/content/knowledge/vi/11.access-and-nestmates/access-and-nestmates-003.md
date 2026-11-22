# Quan hệ giữa nest của lookup class và hidden class mới trong Java 15+

## 1. Mục tiêu

Trong Java, **nest** (tổ lớp cùng tổ) là nhóm các class/interface được JVM công nhận có thể truy cập `private` member của nhau. Nest có một **nest host** và các **nestmate**. Khi một thư viện sinh **hidden class** lúc chạy bằng `MethodHandles.Lookup.defineHiddenClass(...)` (API chính thức từ Java 15), câu hỏi quan trọng là: **hidden class đó thuộc nest nào?**

Câu trả lời phụ thuộc vào tùy chọn `MethodHandles.Lookup.ClassOption.NESTMATE`:

- **Không có `NESTMATE`:** hidden class mới có một nest chỉ gồm chính nó, bất kể metadata `NestHost` ban đầu trong file `.class`.
- **Có `NESTMATE`:** JVM thêm hidden class vào **nest của lookup class**. Nest host của lớp mới là **nest host của `lookup.lookupClass()`**, không nhất thiết là chính lookup class.
- Quan hệ này quyết định liệu bytecode của hidden class có quyền truy cập các thành viên `private` của những class khác trong cùng nest hay không.

Bài học giúp bạn xác định nest host, dự đoán quyền truy cập private, dùng `Class.getNestHost()`/`isNestmateOf()`, hiểu vì sao `getNestMembers()` không liệt kê hidden nestmates, và kiểm chứng bằng chương trình Java 15 chạy được.

**Giới hạn phạm vi:** Bài chỉ dùng các API hiện còn áp dụng trong Java hiện đại, không giới thiệu cơ chế định nghĩa lớp động đã lỗi thời. `NESTMATE` là tùy chọn có hiệu lực của hidden class, không phải kỹ thuật cũ cần thay thế.

## 2. Nền tảng: nest, nest host và lookup class

### 2.1. Nest là quan hệ được JVM xác nhận

Trong mã Java thông thường, các lớp lồng nhau về mặt khai báo được compiler đưa vào một nest. Ví dụ:

```java
public class Host {
    private static String secret() {
        return "hello";
    }

    static class Worker {
        static String read() {
            return Host.secret();
        }
    }
}
```

Đây là **đoạn mô tả cấu trúc**, không phải chương trình có `main`. `Host.Worker` có thể gọi private method `Host.secret()` vì compiler/JVM biết hai lớp là **nestmates**. Với mã này, `Host.class` thường là nest host của cả `Host` và `Host.Worker`. Quan hệ nest không phải là quan hệ kế thừa; một class không cần `extends` class khác để thành nestmate.

Các API `Class` hiện hành:

```java
Host.class.getNestHost();           // Host.class
Host.Worker.class.getNestHost();    // Host.class
Host.class.isNestmateOf(Host.Worker.class); // true
```

Đây là ví dụ trong ngữ cảnh lớp `Host` ở trên. `Class.getNestHost()` và `Class.isNestmateOf(...)` đã xuất hiện từ Java 11 và vẫn được hỗ trợ.

### 2.2. Lookup class là gì?

Một đối tượng `MethodHandles.Lookup` có **lookup class** và một tập quyền truy cập được phép. Nếu gọi `MethodHandles.lookup()` **bên trong phương thức của `Host.Worker`**, lookup class là `Host.Worker.class`:

```java
// Viết bên trong phương thức của Host.Worker:
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> lookupType = lookup.lookupClass(); // Host.Worker.class
Class<?> lookupHost = lookupType.getNestHost(); // Host.class
```

`lookup.lookupClass()` và `lookup.lookupClass().getNestHost()` trả **hai thông tin khác nhau** khi lookup class là một member class lồng trong host. Điều này là chìa khóa hiểu tùy chọn `NESTMATE`.

Không mặc định lookup class luôn là class có `main`, class gọi gián tiếp qua một thư viện, class được dùng làm mẫu bytecode, hoặc một class trùng tên với class sinh ra. Lookup class là danh tính thật được ghi trong đối tượng `Lookup` đang được dùng. Khi quyền của lookup bị hạn chế bởi các thao tác tạo/chuyển lookup, khả năng định nghĩa hidden class cũng phụ thuộc vào các quyền thực có; cùng tên package là chưa đủ.

## 3. Quy tắc xác định nest của hidden class mới

API `MethodHandles.Lookup.defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` nhận bytecode hợp lệ, cờ khởi tạo và danh sách tùy chọn; trả về một **Lookup có lookup class là hidden class vừa định nghĩa**.

Trước tiên, một `Lookup` hợp lệ phải có đủ quyền (full privilege access theo hợp đồng của API) và bytecode phải mô tả một class/interface trong cùng runtime package như lookup class. Việc cung cấp bytecode không hợp lệ hoặc lookup thiếu quyền có thể thất bại trước cả khi bạn quan sát nest của lớp mới.

### 3.1. Không truyền `NESTMATE`

```java
MethodHandles.Lookup result = lookup.defineHiddenClass(bytes, false);
Class<?> hiddenType = result.lookupClass();
```

Đây là mã trong ngữ cảnh đã có `Lookup lookup` và `byte[] bytes` thích hợp. Hidden class được tạo trong nest của **chính nó**:

```java
hiddenType.isHidden();                 // true
hiddenType.getNestHost() == hiddenType; // true
hiddenType.isNestmateOf(lookup.lookupClass()); // false
```

Quy tắc mặc định này **không lấy nest host từ thuộc tính `NestHost` của classfile nguồn**, kể cả nếu bytecode được lấy từ một lớp con/lớp lồng đã biên dịch. Vì vậy, mặc dù một lớp mẫu thông thường có thể đọc private member của class bao ngoài, bản sao hidden mặc định không tự được cấp quyền đó.

### 3.2. Truyền `ClassOption.NESTMATE`

```java
MethodHandles.Lookup result = lookup.defineHiddenClass(
        bytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
Class<?> hiddenType = result.lookupClass();
```

Khi `NESTMATE` có mặt, JVM xác định nest host `H` của **lookup class** và gán `H` làm nest host của hidden class mới:

```java
Class<?> host = lookup.lookupClass().getNestHost();
boolean sameHost = hiddenType.getNestHost() == host; // true
boolean sameNest = hiddenType.isNestmateOf(lookup.lookupClass()); // true
```

Nếu `lookup.lookupClass() == Host.Worker.class`, hidden class mới có nest host là **`Host.class`**, không phải `Host.Worker.class`. Những thành viên đã thuộc nest ấy (ví dụ `Host`, `Host.Worker`, các nested classes đã được JVM xác nhận) và hidden class mới có quan hệ nestmate lẫn nhau.

Javadoc `ClassOption.NESTMATE` nêu rõ hidden nestmate có quyền truy cập private members của các class/interface trong cùng nest. **Quyền này do JVM kiểm tra**, không phải một hiệu ứng của `setAccessible(true)`.

### 3.3. Bảng so sánh ngắn

| Thuộc tính | Hidden class không `NESTMATE` | Hidden class có `NESTMATE` |
| --- | --- | --- |
| `isHidden()` | `true` | `true` |
| Nest host | Chính hidden class | Nest host của lookup class |
| `isNestmateOf(lookup.lookupClass())` | `false` | `true` |
| Đọc private member của host qua bytecode trực tiếp | Không được phép chỉ nhờ cùng package | Được phép theo quy tắc nestmate, nếu lời gọi phù hợp |
| Có thể tìm bằng `Class.forName(hidden.getName())` | Không | Không |
| Xuất hiện trong `host.getNestMembers()` | Không liên quan, vì nest riêng | **Không**: danh sách không liệt kê hidden class thêm động |

**Chú ý:** `NESTMATE` thay đổi quan hệ nest; nó **không** làm hidden class có binary name công khai, không làm `Class.forName` tìm được nó, và không biến một lời gọi API ở nơi bất kỳ thành đặc quyền toàn hệ thống.

## 4. Hình dung khi lookup class là lớp lồng nhau

Giả sử cấu trúc lúc biên dịch là:

```text
Nest host: Host
  ├─ Host
  ├─ Host.Bridge      <- lookup class của Lookup
  └─ Host.Payload     <- class mẫu cung cấp bytes

Lookup của Host.Bridge gọi defineHiddenClass(bytes, ..., NESTMATE)

Nest host sau khi định nghĩa: Host
  ├─ Host
  ├─ Host.Bridge
  ├─ Host.Payload
  └─ Hidden Payload (được thêm động, không liệt kê từ NestMembers)
```

Mặc dù `Bridge` là lookup class, JVM **không tạo nest mới do Bridge làm host**. Nếu `Bridge.getNestHost() == Host.class`, lớp mới được gắn vào nest có host là `Host.class`. Lớp mẫu `Payload` chỉ cung cấp bytecode; quan hệ nest của lớp mới được xác định bởi **lookup class và tùy chọn**, không bởi việc classfile mẫu từng được compiler đặt vào nest nào.

Không có `NESTMATE`, hidden class mới tự làm host và không thể dựa vào quan hệ nest của `Payload` để đọc private members của `Host`.

## 5. Chương trình hoàn chỉnh: chứng minh quan hệ và quyền truy cập

Ví dụ này có **một private method ở host**, **một lớp Bridge chứa MethodHandles.lookup()**, và **một lớp Payload gọi thẳng private method**. Ta định nghĩa **hai hidden classes từ cùng bytecode**:

- Lần thứ nhất **không** truyền `NESTMATE`.
- Lần thứ hai truyền **`ClassOption.NESTMATE`**.

Sau đó in nest host, kiểm tra quan hệ nest và gọi method `Payload.call()` của từng hidden class.

Lưu đúng tên file **`HiddenNestDemo.java`**:

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;

public final class HiddenNestDemo {
    private static String secret() {
        return "private-ok";
    }

    private static final class Bridge {
        static MethodHandles.Lookup define(byte[] bytes, boolean nestmate)
                throws IllegalAccessException {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            return nestmate
                    ? lookup.defineHiddenClass(bytes, true,
                            MethodHandles.Lookup.ClassOption.NESTMATE)
                    : lookup.defineHiddenClass(bytes, true);
        }
    }

    public static final class Payload {
        public static String call() {
            return secret();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = HiddenNestDemo.class.getResourceAsStream(
                "HiddenNestDemo$Payload.class")) {
            if (in == null) {
                throw new IllegalStateException("Payload bytecode missing");
            }
            bytes = in.readAllBytes();
        }

        Class<?> defaultHidden = Bridge.define(bytes, false).lookupClass();
        Class<?> nestmateHidden = Bridge.define(bytes, true).lookupClass();

        System.out.println("lookupClass: " + Bridge.class.getSimpleName());
        System.out.println("lookupNestHost: " +
                Bridge.class.getNestHost().getSimpleName());
        System.out.println("defaultIsHidden: " + defaultHidden.isHidden());
        System.out.println("defaultSelfHost: " +
                (defaultHidden.getNestHost() == defaultHidden));
        System.out.println("defaultIsNestmate: " +
                defaultHidden.isNestmateOf(Bridge.class));
        System.out.println("newIsHidden: " + nestmateHidden.isHidden());
        System.out.println("newHostMatchesOuter: " +
                (nestmateHidden.getNestHost() == HiddenNestDemo.class));
        System.out.println("newIsNestmateOfBridge: " +
                nestmateHidden.isNestmateOf(Bridge.class));
        System.out.println("newIsNestmateOfPayload: " +
                nestmateHidden.isNestmateOf(Payload.class));
        System.out.println("inGetNestMembers: " +
                Arrays.asList(HiddenNestDemo.class.getNestMembers())
                        .contains(nestmateHidden));

        Method callJoined = nestmateHidden.getDeclaredMethod("call");
        System.out.println("joinedCall: " + callJoined.invoke(null));

        Method callDefault = defaultHidden.getDeclaredMethod("call");
        try {
            callDefault.invoke(null);
            System.out.println("defaultCall: unexpected-success");
        } catch (InvocationTargetException e) {
            System.out.println("defaultCause: " +
                    e.getCause().getClass().getSimpleName());
        }
    }
}
```

### 5.1. Biên dịch/chạy

Dùng JDK hiện đại **có hỗ trợ đích Java 15**:

```bash
javac --release 15 HiddenNestDemo.java
java HiddenNestDemo
```

**Stdout chính xác đã được đối chiếu bằng chạy thực tế** với `javac --release 15`:

```text
lookupClass: Bridge
lookupNestHost: HiddenNestDemo
defaultIsHidden: true
defaultSelfHost: true
defaultIsNestmate: false
newIsHidden: true
newHostMatchesOuter: true
newIsNestmateOfBridge: true
newIsNestmateOfPayload: true
inGetNestMembers: false
joinedCall: private-ok
defaultCause: IllegalAccessError
```

Khi biên dịch file, `javac` tạo ra ít nhất các file `HiddenNestDemo.class`, `HiddenNestDemo$Bridge.class`, `HiddenNestDemo$Payload.class`. **Phải giữ file `Payload.class` được tạo với tên chứa dấu `$` đúng như chương trình** trong classpath; phương thức `getResourceAsStream(...)` đọc bytecode của nó. Nếu tự đổi tên file class hoặc chỉ đóng gói lớp ngoài, phép đọc resource sẽ thất bại.

Ví dụ này chạy với **bytecode đáng tin cậy do chính chương trình biên dịch**; trong ứng dụng thực tế, việc chấp nhận bytecode của bên thứ ba là một quyết định thiết kế và kiểm soát quyền riêng.

### 5.2. Phân tích kết quả theo từng nhóm

**Danh tính lookup và host.** `Bridge.define` gọi `MethodHandles.lookup()` ngay trong body của `Bridge`, do đó lookup class thật là `Bridge.class`. Nhưng `Bridge.class.getNestHost()` là `HiddenNestDemo.class`. Vì thế hidden class có `NESTMATE` nhận host `HiddenNestDemo.class`.

**Lớp không có NESTMATE.** `defaultHidden.isHidden() == true` và `defaultHidden.getNestHost() == defaultHidden`, vì thế `isNestmateOf(Bridge.class)` trả `false`. Mặc dù bytecode gốc là của `Payload`, thuộc tính NestHost của mẫu không cho hidden class mặc định quyền đọc private method của `HiddenNestDemo`.

**Lớp có NESTMATE.** `nestmateHidden.getNestHost() == HiddenNestDemo.class` và `isNestmateOf(Bridge.class) == true`. Quan hệ đó cũng đúng với `Payload.class` vì `Payload` là member thông thường của cùng nest. Gọi `call()` trả `"private-ok"`: hidden class đã truy cập private method `secret()` của host theo quy tắc nestmate.

**Thất bại ở lớp mặc định.** `defaultHidden.getDeclaredMethod("call")` vẫn trả metadata của method public. Nhưng khi thực thi bytecode bên trong `call()` để gọi `HiddenNestDemo.secret()`, JVM kiểm tra private access và báo **`IllegalAccessError`**. Vì ta gọi method qua reflection, `Method.invoke` bọc lỗi phát sinh bên trong thành `InvocationTargetException`; chương trình in loại của `e.getCause()` là `IllegalAccessError`. Đây là khác biệt **quyền của bytecode đang thực thi**, không phải lỗi `getDeclaredMethod` không tìm ra method.

**Việc liệt kê nest members.** `inGetNestMembers: false` **không mâu thuẫn** với `newIsNestmateOfBridge: true`. `Class.getNestMembers()` chỉ liệt kê các thành viên được ghi trong metadata `NestMembers` của host (và được xác minh thành công); nó **không liệt kê hidden classes được thêm động** qua `defineHiddenClass(..., NESTMATE)`.

## 6. Các API giúp kiểm tra quan hệ đúng

| API | Câu hỏi trả lời | Ghi chú quan trọng |
| --- | --- | --- |
| `lookup.lookupClass()` | Class nào làm lookup class của Lookup này? | Đây là gốc để xác định nest với NESTMATE |
| `lookup.lookupClass().getNestHost()` | Nest host của lookup class là ai? | Có thể là outer class, không phải lookup class |
| `hidden.getNestHost()` | Nest host của hidden class mới là ai? | Với NESTMATE sẽ trùng host của lookup class |
| `hidden.isNestmateOf(lookup.lookupClass())` | Hai class có chung nest không? | Cách kiểm chứng trực tiếp, chính xác hơn suy tên |
| `hidden.isHidden()` | Đây có phải hidden class không? | Không cần suy từ dấu `/` trong tên |
| `host.getNestMembers()` | Host ghi nhận những static nest members nào? | **Không liệt kê hidden nestmates thêm động** |
| `hidden.getName()` | Tên runtime của hidden class là gì? | Có hậu tố JVM sinh, không phải binary name để tìm lại |
| `lookup.defineHiddenClass(bytes, initialize, NESTMATE)` | Tạo hidden class thuộc nest của lookup class | Phải có quyền lookup và bytes phù hợp |

Một phép xác nhận ngắn phù hợp với chương trình đã có `Lookup sourceLookup` và `Class<?> generated`:

```java
boolean joinsLookupNest = generated.isNestmateOf(sourceLookup.lookupClass());
boolean sameHost = generated.getNestHost()
        == sourceLookup.lookupClass().getNestHost();
```

Hai điều kiện phù hợp khi định nghĩa lớp với `NESTMATE`, nhưng **không nên dùng kết quả `host.getNestMembers()` để quyết định hidden class có là nestmate hay không**. API trả danh sách không bao gồm thành viên hidden mới thêm động.

## 7. Điều gì thực sự tạo ra quyền đọc private?

Trong Java, quyền private giữa các nestmates được JVM thiết lập theo quan hệ nest đã xác nhận. Vì thế:

1. `NESTMATE` đưa lớp mới vào cùng nest với lookup class (theo nest host), qua đó cho phép truy cập private members của các class/interface trong nest.
2. Không có `NESTMATE`, hidden class mới tự làm nest host; cùng **package**, cùng **bytecode mẫu** hoặc cùng **class loader** không đủ để đọc private members của class khác.
3. `getDeclaredMethod(...)` có thể xem metadata của method bất kể khả năng gọi thành công. JVM thực hiện access check khi bytecode hoặc cơ chế reflection/method handles truy cập thành viên.
4. Với reflection từ caller bên ngoài, việc cho hidden class quyền đọc private members của nest **không tự cho caller bên ngoài quyền tương đương**. Ví dụ `Class.getDeclaredField("secret")` có thể tìm metadata, nhưng `Field.get(...)` vẫn bị kiểm tra truy cập của caller.
5. `ClassOption.NESTMATE` không phải cách bypass quyền tùy tiện. Quy trình tạo hidden class vẫn đòi hỏi một Lookup có đủ quyền và bytecode trong runtime package cho phép.

Ví dụ, nếu framework tạo hidden class trong nest có `Host` làm host, bytecode hidden class có thể gọi `Host.privateMethod()` theo luật nestmate. Điều đó **không đồng nghĩa** bất kỳ class bên ngoài nest nào cũng có thể gọi private method của Host qua reflection mà không xét module/access policy.

### Khi muốn lấy private member bằng MethodHandles

Một `Lookup` có đủ quyền ở class phù hợp có thể tạo MethodHandle cho các member truy cập được. Trong JDK hiện hành, access check của method handles xảy ra **khi tạo handle** theo quyền của Lookup; khác với `Method.invoke` vốn có mô hình kiểm tra quyền của reflection.

Đây là lựa chọn khác cho framework cần gọi động và có lookup quyền hợp lệ; nội dung cốt lõi của bài vẫn là **nest host của lookup class**. Đừng cố gửi một lookup nhiều quyền qua API công khai khi bên nhận không được phép dùng quyền đó.

## 8. Phân biệt NESTMATE với STRONG và initialize

`Lookup.defineHiddenClass(bytes, initialize, options...)` có các thành phần độc lập:

- **`ClassOption.NESTMATE`:** quyết định hidden class mới **có tham gia nest của lookup class hay không**.
- **`ClassOption.STRONG`:** quyết định quan hệ mạnh với defining class loader và các đặc tính unload; không chọn nest host, không cấp quyền private.
- **`initialize`:** chọn có thực hiện khởi tạo lớp lúc định nghĩa không; không quyết định quan hệ nest.

Ví dụ ba lời gọi (giả định `lookup` đủ quyền và `bytes` hợp lệ):

```java
// Hidden class mặc định: nest riêng, không yêu cầu khởi tạo ngay.
lookup.defineHiddenClass(bytes, false);

// Thêm vào nest của lookup class, không yêu cầu khởi tạo ngay.
lookup.defineHiddenClass(bytes, false,
        MethodHandles.Lookup.ClassOption.NESTMATE);

// Thêm vào nest của lookup class và gắn quan hệ mạnh với loader.
lookup.defineHiddenClass(bytes, false,
        MethodHandles.Lookup.ClassOption.NESTMATE,
        MethodHandles.Lookup.ClassOption.STRONG);
```

Ba đoạn này minh họa **cách gọi API**, không phải chương trình Java độc lập. Chúng không nên được diễn giải là mọi bytecode đều định nghĩa thành công: vẫn cần classfile hợp lệ, version được hỗ trợ, package phù hợp, quyền của Lookup và các ràng buộc liên kết.

Theo hợp đồng hiện hành, hidden classes mặc định có thể được JVM unload độc lập với defining class loader khi không còn tham chiếu sống; `STRONG` làm quan hệ vòng đời giống class thông thường hơn. **Đừng chọn `STRONG` chỉ để sửa lỗi private access**. Nếu thiết kế cần tương tác private trong nest, thành phần quyết định là `NESTMATE` và quyền lookup phù hợp.

## 9. Các bẫy thường gặp

### Bẫy 1: Nhầm lookup class là nest host

Nếu `lookup.lookupClass() == Host.Worker.class`, không được kết luận hidden class có NESTMATE sẽ có host `Host.Worker.class`. Cần lấy `Host.Worker.class.getNestHost()`. Trong ví dụ chạy được, host thực tế là `HiddenNestDemo.class`.

### Bẫy 2: Tin NestHost của bytecode mẫu

Một file `Payload.class` được compiler tạo như nested member có thể chứa metadata nest. Khi định nghĩa hidden class, **nest của hidden class được quyết định bởi tùy chọn**. Nếu không có NESTMATE, mặc định nó có nest chỉ gồm bản thân; có NESTMATE, host là host của lookup class.

### Bẫy 3: Dùng getNestMembers để phủ nhận nestmate

`host.getNestMembers()` có thể không chứa `hidden` dù `hidden.isNestmateOf(host)` trả `true`. Đây là **hợp đồng API**, không phải dấu hiệu lớp mới bị JVM thêm sai vào nest.

### Bẫy 4: Tưởng cùng package là đủ để đọc private

Package-private access và private nestmate access là hai phạm vi khác nhau. `NESTMATE` thiết lập quan hệ nestmate; không phải cách đổi `private` sang package-private hoặc public.

### Bẫy 5: Tưởng mọi IllegalAccessException giống IllegalAccessError

`defineHiddenClass` có thể ném **`IllegalAccessException`** khi Lookup thiếu full privilege; `Method.invoke` có thể ném `IllegalAccessException` khi caller thiếu quyền reflection. Nhưng khi *bytecode của hidden class* cố truy cập private member trái luật, JVM có thể báo **`IllegalAccessError`**. Trong ví dụ, `Method.invoke` bọc lỗi này thành `InvocationTargetException`, và `getCause()` là `IllegalAccessError`.

### Bẫy 6: Dùng tên hidden class để tìm lại

Hidden class không thể discover bằng `Class.forName(hidden.getName())` vì nó không có binary name bình thường. Hãy giữ `Class<?>`, `Lookup`, instance hoặc MethodHandle từ API đã tạo ra class.

### Bẫy 7: Thử private access bằng reflection từ class khác

Nếu một class không thuộc nest cố đọc private member của Host qua reflection, lỗi có thể phát sinh từ **access của caller**, ngay cả khi hidden class thật sự là nestmate của Host. Để kiểm thử nest access, dùng **mã thực thi bên trong hidden class** như `Payload.call()` trong bài, không nhầm nó với quyền của người gọi reflection.

### Bẫy 8: Xem hidden class là ranh giới sandbox

Hidden class giới hạn khả năng tham chiếu và khám phá theo tên, nhưng không tự cấp hoặc cô lập toàn bộ đặc quyền. Quyền lookup, private access, module boundaries, bytecode đầu vào và quyền của code sinh class vẫn cần được thiết kế, kiểm soát phù hợp.

## 10. Kiểm thử trường hợp biên theo hai chế độ

Khi viết test cho một cơ chế sinh hidden class, nên kiểm tra ít nhất:

| Kiểm thử | Không NESTMATE | Có NESTMATE |
| --- | --- | --- |
| `hidden.isHidden()` | `true` | `true` |
| `hidden.getNestHost() == hidden` | `true` | `false` nếu lookup class thuộc một nest khác |
| `hidden.getNestHost() == lookup.lookupClass().getNestHost()` | Thường `false` | `true` |
| `hidden.isNestmateOf(lookup.lookupClass())` | `false` | `true` |
| Code ẩn gọi private method của host | Bị từ chối nếu không có quyền khác | Được phép theo quan hệ nestmate |
| `host.getNestMembers().contains(hidden)` | Không áp dụng như phép test của nest riêng | Không đáng tin để kiểm tra hidden nestmate; danh sách loại trừ các lớp ẩn thêm động |

Dòng thứ hai có điều kiện: nếu tình cờ host của lookup class là chính hidden class ấy thì biểu thức có thể khác, nhưng trong một lần `defineHiddenClass` từ lookup class khác đã tồn tại như ví dụ, hai Class object khác nhau. Trong thực hành, **ưu tiên kiểm `isNestmateOf` và so sánh nest hosts thực tế**.

Kiểm thử an toàn nên kiểm tra cả:
- **Lookup class lồng nhau**: đảm bảo nest host lấy từ `getNestHost()` chứ không tự lấy lookup class.
- **Classfile có thuộc tính NestHost**: xác minh không được kế thừa ngầm khi không dùng `NESTMATE`.
- **Private access**: gọi thành viên thực sự từ bên trong hidden code; đọc chính xác nguyên nhân khi lời gọi reflection bọc ngoại lệ.
- **Định danh lớp**: so sánh `Class<?>`, tránh hard-code hậu tố tên hidden class.
- **Vòng đời**: nếu hệ thống cache các Class/Lookup/MethodHandle sinh động, xác định rõ khi nào giải phóng tham chiếu.

## 11. Câu hỏi ôn tập có đáp án

**Câu 1.** `lookup.lookupClass()` là `Host.Helper.class`, `Host.Helper.class.getNestHost()` là `Host.class`. Khi gọi `defineHiddenClass(bytes, false, NESTMATE)`, nest host của lớp mới là ai?

**Đáp án:** **`Host.class`**, vì JVM lấy nest host của lookup class, không lấy lookup class làm host mới theo mặc định.

**Câu 2.** Bytecode lấy từ một lớp nested có metadata NestHost của host. Định nghĩa hidden class **không** có NESTMATE thì có tự đọc private của host không?

**Đáp án:** **Không**. Hidden class mặc định có nest chỉ gồm chính nó; metadata NestHost của bytecode mẫu không quyết định nest của hidden class.

**Câu 3.** `newHidden.isNestmateOf(Host.class)` là true nhưng `Arrays.asList(Host.class.getNestMembers()).contains(newHidden)` là false. Mâu thuẫn không?

**Đáp án:** **Không**. Hidden classes thêm động không được `getNestMembers()` liệt kê theo hợp đồng API.

**Câu 4.** Trong demo, tại sao `callDefault.invoke(null)` thất bại trong khi `getDeclaredMethod("call")` thành công?

**Đáp án:** Tra metadata method là việc khác quyền chạy bytecode. Khi method của hidden class không cùng nest cố gọi `HiddenNestDemo.secret()` private, JVM báo `IllegalAccessError`, còn reflection bọc nó trong `InvocationTargetException`.

**Câu 5.** Truyền `STRONG` có thay thế `NESTMATE` khi cần truy cập private không?

**Đáp án:** **Không.** `STRONG` liên quan vòng đời/unloading với class loader; `NESTMATE` quyết định class mới tham gia nest của lookup class.

**Câu 6.** Có nên dựa vào chuỗi `hidden.getName()` để khôi phục hidden class sau khi khởi động lại không?

**Đáp án:** **Không.** Tên hidden class không phải binary name mà `Class.forName` có thể dùng. Giữ Class/Lookup/handle được cung cấp từ cơ chế sinh lớp nếu cần thao tác trong vòng đời runtime.

**Tiêu chí hoàn thành:** Bạn phân biệt chính xác ba khái niệm **lookup class**, **nest host của lookup class** và **hidden class mới**, chỉ ra điều gì đổi khi có NESTMATE, dự đoán private access và tự viết được test dùng `getNestHost()` + `isNestmateOf()` mà không dựa vào `getNestMembers()`.

## 12. Tài liệu chuẩn và còn áp dụng

- [Java SE 15 API – `MethodHandles.Lookup#defineHiddenClass`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quy tắc tạo hidden class, yêu cầu quyền lookup, package, tùy chọn NESTMATE và vòng đời.
- [Java SE 15 API – `Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` và `STRONG`, hai ý nghĩa riêng biệt.
- [Java SE 15 API – `Class`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/Class.html): `getNestHost()`, `isNestmateOf()`, `getNestMembers()` và `isHidden()`.
- [Java SE 26 API – `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): đối chiếu API và hợp đồng vẫn còn hiệu lực trên JDK hiện đại.
- [Java SE 26 API – `Class`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): hợp đồng getNestMembers loại trừ hidden class thêm động.
- [OpenJDK JEP 371 – Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế hidden classes, khả năng tham gia nest và quan hệ với class loading.
- [JVMS §5.4.4 – Access Control](https://docs.oracle.com/javase/specs/jvms/se15/html/jvms-5.html#jvms-5.4.4): kiểm tra quan hệ nest và quyền truy cập private ở JVM.

**Ghi nhớ:** Với `defineHiddenClass(bytes, ..., NESTMATE)`, **nest host của class mới = nest host của lookup class**. Không có `NESTMATE`, hidden class tự làm host; `getNestMembers()` không phải phép liệt kê toàn bộ hidden nestmates được thêm động.