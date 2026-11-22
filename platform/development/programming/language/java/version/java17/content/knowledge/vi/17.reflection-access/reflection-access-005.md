# `MethodHandles.Lookup` và quyền của đối tượng lookup trong Java 17

`MethodHandles.Lookup` là đối tượng đại diện cho **ngữ cảnh truy cập** khi Java tạo các `MethodHandle` hoặc `VarHandle`. Một lookup object mang theo lớp làm điểm xuất phát của việc kiểm tra quyền truy cập và tập quyền mà nó được phép sử dụng.

Điều này quan trọng vì Method Handles không tự động bỏ qua quy tắc `private`, `protected`, package access hay ranh giới module. Khi gọi một phương thức như `findVirtual` hoặc `findGetter`, Java dùng quyền của lookup object để quyết định có cho phép tạo handle tới thành viên đó hay không.

Có thể hình dung:

```text
MethodHandles.Lookup
       |
       +-- lookupClass()      lớp làm ngữ cảnh truy cập
       |
       +-- lookupModes()      các quyền lookup đang có
       |
       +-- find... / unreflect...
                 |
                 v
            MethodHandle
                 |
                 v
        gọi thành viên đã được kiểm tra quyền
```

Ba ý cần nhớ:

- **Lookup object không phải một quyền truy cập toàn cục.** Nó đại diện cho quyền của một ngữ cảnh cụ thể.
- **Quyền được kiểm tra khi tạo handle.** Một `MethodHandle` hợp lệ có thể được truyền sang nơi khác và vẫn gọi được thành viên mà handle đại diện.
- **Lookup object có thể mang quyền mạnh.** Không nên tùy tiện chia sẻ lookup có private access cho code hoặc plugin không đáng tin cậy.

`MethodHandles.Lookup` thuộc package `java.lang.invoke` và có từ Java 7. Các API module-aware như `privateLookupIn` được bổ sung trong Java 9; chúng đều dùng được trong Java 17 mà không cần preview.

## 1. MethodHandle và Lookup giải quyết hai việc khác nhau

`MethodHandle` là một tham chiếu có kiểu tới phương thức, constructor, field hoặc một thao tác có thể gọi. `Lookup` là đối tượng dùng để **tìm và tạo** các handle đó theo quy tắc truy cập Java.

Ví dụ, một class có phương thức public:

```java
public class Greeter {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Ta có thể tìm method handle bằng lookup:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle greetHandle = lookup.findVirtual(
        Greeter.class,
        "greet",
        MethodType.methodType(String.class, String.class)
);
```

Sau khi handle được tạo, có thể gọi:

```java
Greeter greeter = new Greeter();

String message = (String) greetHandle.invokeExact(greeter, "An");
System.out.println(message);
```

Kết quả:

```text
Hello, An
```

Trong ví dụ này:

- `lookup` là đối tượng thực hiện việc kiểm tra quyền truy cập.
- `findVirtual` tìm phương thức instance `greet`.
- `MethodType` mô tả kiểu trả về và kiểu tham số của phương thức.
- `greetHandle` là handle có thể được gọi với receiver `Greeter` và tham số `String`.

Với `findVirtual`, `MethodType` mô tả tham số khai báo của phương thức và kiểu trả về; receiver được thêm vào kiểu gọi của handle. Do đó handle thực tế có dạng `(Greeter, String)String`.

**Lookup không phải handle.** Lookup là công cụ tạo handle; handle là kết quả có thể dùng để thực hiện thao tác.

## 2. Lookup object chứa những thông tin gì?

`MethodHandles.Lookup` là một class lồng tĩnh (static nested class) trong `MethodHandles`. Một lookup object gắn với:

1. **Lookup class:** lớp làm ngữ cảnh truy cập.
2. **Lookup modes:** các quyền truy cập mà lookup object đang sở hữu.
3. **Previous lookup class (nếu có):** thông tin về lookup trước đó trong một số trường hợp, đặc biệt khi dùng `privateLookupIn`.

Các phương thức quan sát quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `lookupClass()` | Trả về class làm ngữ cảnh truy cập của lookup |
| `lookupModes()` | Trả về bit mask biểu diễn các lookup mode hiện có |
| `hasFullPrivilegeAccess()` | Kiểm tra lookup có đầy đủ quyền truy cập mạnh hay không |
| `hasPrivateAccess()` | Kiểm tra lookup có private access; API này đã deprecated |
| `previousLookupClass()` | Trả về lookup class trước đó nếu có, nếu không thì `null` |

Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

System.out.println(lookup.lookupClass());
System.out.println(lookup.lookupModes());
System.out.println(lookup.hasFullPrivilegeAccess());
System.out.println(lookup.previousLookupClass());
```

Khi gọi `MethodHandles.lookup()` bên trong class `LookupInfo`, lookup class là `LookupInfo.class`. Nó không phải class của nơi gọi phương thức helper từ bên ngoài.

### 2.1. Lookup class quyết định ngữ cảnh truy cập

Giả sử:

```java
package com.example;

import java.lang.invoke.MethodHandles;

public class LookupOwner {
    public static MethodHandles.Lookup createLookup() {
        return MethodHandles.lookup();
    }
}
```

Một class khác gọi `LookupOwner.createLookup()` sẽ nhận lookup object có lookup class là `LookupOwner`, vì lời gọi `lookup()` được thực hiện bên trong `LookupOwner`.

Điều này rất quan trọng: nếu muốn lấy lookup có quyền private của một class, lời gọi `MethodHandles.lookup()` phải được thực hiện trong ngữ cảnh class đó (hoặc dùng cơ chế phù hợp như `privateLookupIn` khi module cho phép). Gọi helper từ một class khác không tự biến lookup thành lookup của caller bên ngoài.

## 3. Các lookup mode và ý nghĩa quyền truy cập

Lookup object có thể mang một hoặc nhiều mode. Các mode phản ánh loại truy cập mà nó được phép thực hiện.

| Mode | Ý nghĩa khái quát |
|---|---|
| `PUBLIC` | Truy cập thành viên public theo các quy tắc module và kiểu |
| `PRIVATE` | Truy cập thành viên private trong ngữ cảnh được phép |
| `PROTECTED` | Truy cập thành viên protected theo quy tắc Java |
| `PACKAGE` | Truy cập thành viên package-private trong package phù hợp |
| `MODULE` | Quyền gắn với module của lookup class, cần thiết cho một số thao tác module-aware |
| `UNCONDITIONAL` | Quyền public đặc biệt của public lookup, áp dụng cho package được export vô điều kiện |

Các mode được biểu diễn bằng hằng số và bit mask. Không nên hard-code số nguyên của mode trong logic ứng dụng; dùng các phương thức kiểm tra như `hasFullPrivilegeAccess()` hoặc API tìm member phù hợp.

### 3.1. Full privilege access

Lookup được tạo trực tiếp bằng `MethodHandles.lookup()` thường có **full privilege access** trong ngữ cảnh class gọi. Theo API Java 17, full privilege access gồm các quyền cần thiết như private, protected, package và module access.

`hasFullPrivilegeAccess()` là cách rõ ràng để kiểm tra lookup có full privilege access:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

if (lookup.hasFullPrivilegeAccess()) {
    System.out.println("Lookup có full privilege access");
}
```

Không nhầm full privilege access với việc có thể truy cập mọi thành viên của mọi module. Module boundaries, package accessibility và các điều kiện của từng API vẫn áp dụng. Full privilege được xét tương đối với lookup class và module của nó.

### 3.2. Private access không đồng nghĩa full privilege

Một lookup có `PRIVATE` mode có thể truy cập private member theo ngữ cảnh được cấp, nhưng điều đó không nhất thiết có nghĩa nó có mọi quyền khác như `MODULE`.

Trong Java 17, `hasPrivateAccess()` đã deprecated. Nếu mục đích là kiểm tra lookup có đầy đủ quyền truy cập mạnh, dùng `hasFullPrivilegeAccess()`.

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

boolean fullPrivilege = lookup.hasFullPrivilegeAccess();
// Tránh dựa vào hasPrivateAccess() trong mã mới.
```

## 4. Ba cách tạo lookup thường gặp

Các factory method quan trọng nhất:

| API | Quyền khái quát | Khi nên dùng |
|---|---|---|
| `MethodHandles.lookup()` | Lookup gắn với class gọi, thường có full privilege access trong ngữ cảnh đó | Code cần tạo handle cho thành viên mà chính class có quyền truy cập |
| `MethodHandles.publicLookup()` | Public-only lookup | Chỉ cần truy cập API public được export vô điều kiện |
| `MethodHandles.privateLookupIn(target, caller)` | Tạo lookup có private access cho target khi đáp ứng điều kiện module/access | Framework hoặc thư viện cần truy cập sâu có kiểm soát vào class khác |

### 4.1. `MethodHandles.lookup()` — lookup của class hiện tại

Đây là cách thông dụng để lấy lookup object:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

Lookup class là class nơi lời gọi được thực hiện. Nó có quyền truy cập theo ngữ cảnh class đó, gồm private access của class và các quyền phù hợp với package/module.

Ví dụ private method:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class SecretBox {
    private String reveal() {
        return "classified";
    }

    public static MethodHandle revealHandle()
            throws NoSuchMethodException, IllegalAccessException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        return lookup.findVirtual(
                SecretBox.class,
                "reveal",
                MethodType.methodType(String.class)
        );
    }
}
```

Vì lời gọi `lookup()` nằm trong `SecretBox`, lookup có quyền private cần thiết để tìm `reveal`.

Một class khác có thể nhận handle đã tạo:

```java
SecretBox box = new SecretBox();
MethodHandle reveal = SecretBox.revealHandle();

String value = (String) reveal.invokeExact(box);
System.out.println(value);
```

Kết quả:

```text
classified
```

Điểm quan trọng: code gọi handle không cần tự có quyền private của `SecretBox`. Quyền đã được kiểm tra khi `revealHandle` tạo handle và handle được trao cho caller. Vì vậy, việc chia sẻ handle cũng là chia sẻ khả năng gọi thao tác đó.

### 4.2. `MethodHandles.publicLookup()` — chỉ truy cập public

`publicLookup()` trả về lookup có quyền public hạn chế. Nó phù hợp khi thư viện chỉ cần truy cập các thành viên public của public class trong package được export vô điều kiện.

```java
MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();

MethodHandle handle = publicLookup.findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class)
);
```

Gọi handle:

```java
int length = (int) handle.invokeExact("Java 17");
System.out.println(length); // 8
```

Public lookup không có private access và không phải cách để vượt qua module encapsulation. Nó không thể truy cập private method hoặc package nội bộ chưa được export phù hợp.

### 4.3. Vì sao publicLookup có giới hạn export vô điều kiện?

Module có thể export package cho tất cả module hoặc chỉ cho một số module cụ thể:

```java
module com.example.library {
    exports com.example.api;
    exports com.example.spi to com.example.framework;
}
```

`com.example.api` được export vô điều kiện. `com.example.spi` chỉ được export cho `com.example.framework`.

`publicLookup()` là lookup public phổ quát, không đại diện cho một module client cụ thể để thỏa qualified export. Vì thế, không nên giả định nó có thể truy cập package chỉ export cho một module được chỉ định.

## 5. Quyền được kiểm tra khi tạo MethodHandle

Các phương thức như `findVirtual`, `findStatic`, `findConstructor`, `findGetter` và `findSetter` thực hiện kiểm tra truy cập dựa trên lookup object.

Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findStatic(
        Integer.class,
        "parseInt",
        MethodType.methodType(int.class, String.class)
);
```

Nếu lookup có quyền phù hợp, handle được tạo. Nếu không, phương thức tìm kiếm có thể ném `IllegalAccessException`; nếu không tìm thấy member hoặc kiểu mô tả không phù hợp, có thể ném `NoSuchMethodException`, `NoSuchFieldException` hoặc lỗi tương ứng.

Sau khi handle đã được tạo, việc gọi handle không thực hiện lại toàn bộ kiểm tra truy cập Java như lúc tìm member. Handle là một đối tượng có khả năng thực hiện thao tác đã được cấp. Khi gọi, JVM vẫn kiểm tra các ràng buộc kiểu, receiver, argument và các điều kiện runtime khác.

### 5.1. Quyền của handle không phải quyền của nơi gọi

Ví dụ `SecretBox` ở mục trước cho thấy caller có thể dùng handle tới private method mà caller không thể tự tìm bằng lookup của chính mình.

Điều này tạo ra một nguyên tắc bảo mật:

> Chỉ truyền một MethodHandle khi muốn trao cho bên nhận khả năng thực hiện chính thao tác mà handle đại diện.

Không nên công khai một handle tới thao tác nhạy cảm chỉ vì nó tiện cho việc tích hợp. Đặc biệt, không trao lookup full privilege cho plugin hoặc code bên ngoài nếu không có chủ đích.

## 6. Tìm các loại member khác nhau

`Lookup` cung cấp nhiều phương thức `find...`. Mỗi phương thức tương ứng một loại thành viên.

| Phương thức | Member được tìm | Ví dụ |
|---|---|---|
| `findVirtual` | Phương thức instance gọi theo dispatch ảo | `toString()` |
| `findStatic` | Phương thức static | `Integer.parseInt(String)` |
| `findSpecial` | Phương thức gọi đặc biệt theo ngữ nghĩa JVM, như super invocation | Gọi implementation của superclass/default method |
| `findConstructor` | Constructor | `new Widget(String)` |
| `findGetter` | Getter handle cho instance field | Đọc `object.name` |
| `findSetter` | Setter handle cho instance field | Ghi `object.name` |
| `findStaticGetter` | Đọc static field | Đọc `Config.VERSION` |
| `findStaticSetter` | Ghi static field | Ghi static field nếu được phép |
| `findVarHandle` | VarHandle cho instance field | Truy cập field với memory access modes |
| `findStaticVarHandle` | VarHandle cho static field | Truy cập static field |

Các phương thức này không tự bỏ qua modifier. Quyền của lookup phải đủ cho member được yêu cầu.

### 6.1. findStatic

```java
class MathOps {
    static int doubleIt(int value) {
        return value * 2;
    }
}

MethodHandle doubleIt = MethodHandles.lookup().findStatic(
        MathOps.class,
        "doubleIt",
        MethodType.methodType(int.class, int.class)
);

int result = (int) doubleIt.invokeExact(21);
```

Vì `doubleIt` là static nên handle không cần receiver object.

### 6.2. findConstructor

```java
class Widget {
    private final String name;

    Widget(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

MethodHandle constructor = MethodHandles.lookup().findConstructor(
        Widget.class,
        MethodType.methodType(void.class, String.class)
);

Widget widget = (Widget) constructor.invokeExact("panel");
```

Đối với `findConstructor`, `MethodType` được truyền vào có kiểu trả về `void.class` và các kiểu tham số của constructor. Handle kết quả trả về instance mới được tạo.

Trong ví dụ, constructor package-private và code tìm handle ở cùng package. Nếu constructor là private, lookup cần private access phù hợp.

### 6.3. findGetter và findSetter

```java
class Profile {
    private String nickname;

    Profile(String nickname) {
        this.nickname = nickname;
    }
}

MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter = lookup.findGetter(
        Profile.class,
        "nickname",
        String.class
);

MethodHandle setter = lookup.findSetter(
        Profile.class,
        "nickname",
        String.class
);
```

Nếu đoạn code này nằm ngoài `Profile` và không cùng package, lookup thông thường không có quyền truy cập private field `nickname`. Cần thực hiện tìm handle từ ngữ cảnh có quyền hoặc dùng `privateLookupIn` khi module cho phép.

### 6.4. VarHandle

`VarHandle` là API typed để đọc/ghi field, phần tử mảng hoặc vùng nhớ theo nhiều memory access mode. Lookup cũng là cách chuẩn để tìm VarHandle:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Counter {
    int value;
}

MethodHandles.Lookup lookup = MethodHandles.lookup();

VarHandle valueHandle = lookup.findVarHandle(
        Counter.class,
        "value",
        int.class
);

Counter counter = new Counter();
valueHandle.set(counter, 10);

int current = (int) valueHandle.get(counter);
```

Ví dụ trên dùng field package-private trong cùng package. Với field private, vẫn phải có lookup access phù hợp. VarHandle không phải cách bỏ qua encapsulation; nó tuân theo quy tắc quyền khi được tạo.

## 7. `unreflect`: tạo handle từ đối tượng Reflection

Ngoài `find...`, `Lookup` có thể tạo MethodHandle từ đối tượng reflection:

- `unreflect(Method)`
- `unreflectConstructor(Constructor<?>)`
- `unreflectGetter(Field)`
- `unreflectSetter(Field)`
- Các biến thể liên quan tới VarHandle.

Ví dụ:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;

Method method = String.class.getMethod("substring", int.class);

MethodHandle handle = MethodHandles.lookup().unreflect(method);
```

`getMethod` ở đây lấy public method `substring(int)`. `unreflect` chuyển Method đã có thành MethodHandle, nhưng vẫn áp dụng quy tắc truy cập liên quan tới lookup và trạng thái accessibility của đối tượng reflection.

Không nên nghĩ rằng chỉ cần có một đối tượng `Method` là có thể tạo handle tới bất kỳ private member nào. Quyền truy cập của reflection và lookup vẫn phải được thỏa mãn.

### 7.1. Khi nào dùng find và khi nào dùng unreflect?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Biết trước class, tên member và MethodType | `findVirtual`, `findStatic`, `findGetter`... |
| Đã có `Method` hoặc `Constructor` từ reflection | `unreflect` hoặc `unreflectConstructor` |
| Đã có `Field` và muốn đọc/ghi qua handle | `unreflectGetter` / `unreflectSetter` |
| Cần access mode cho field hoặc biến đồng bộ | `findVarHandle` / `unreflectVarHandle` |

`find...` mô tả trực tiếp member muốn tìm. `unreflect...` hữu ích khi một phần khác của chương trình đã làm bước discovery bằng reflection.

## 8. `Lookup.in` — đổi lookup class và thu hẹp quyền

`Lookup.in(Class<?>)` tạo một lookup object mới với lookup class được yêu cầu. Quyền truy cập của lookup mới được điều chỉnh theo quan hệ giữa lookup cũ và class mới.

Ví dụ:

```java
MethodHandles.Lookup original = MethodHandles.lookup();

MethodHandles.Lookup narrowed = original.in(String.class);

System.out.println(original.lookupClass());
System.out.println(narrowed.lookupClass());
System.out.println(narrowed.lookupModes());
```

Điều quan trọng:

- `in` không phải cách xin thêm quyền.
- Khi chuyển sang lookup class khác, các mode không còn phù hợp có thể bị loại bỏ.
- Lookup mới không tự nhận private access của class đích chỉ vì ta truyền `String.class` hoặc một class khác.
- Quyền chỉ có thể được giữ lại hoặc thu hẹp theo quy tắc API.

Do đó, `in` hữu ích khi muốn tạo một lookup có ngữ cảnh khác và quyền hẹp hơn. Nó không thay thế `privateLookupIn`.

### 8.1. Ví dụ về việc không thể dùng in để lấy private access tùy ý

Giả sử:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup another = lookup.in(SomeOtherClass.class);
```

Không thể kết luận `another` có quyền truy cập private vào `SomeOtherClass`. `in` không biến caller thành chính class đích và không cấp quyền vượt qua module boundary.

Nếu cần private access tới class khác, phải đáp ứng điều kiện của `privateLookupIn`.

## 9. `dropLookupMode` — chủ động loại bỏ quyền

`dropLookupMode(int)` tạo lookup object mới bằng cách loại bỏ một mode khỏi tập quyền hiện có. Đây là cách **giảm quyền** theo nguyên tắc least privilege.

Ví dụ:

```java
MethodHandles.Lookup full = MethodHandles.lookup();

MethodHandles.Lookup publicOnly =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);

System.out.println(full.lookupModes());
System.out.println(publicOnly.lookupModes());
```

Việc loại bỏ một mode có thể kéo theo việc loại bỏ các mode phụ thuộc theo quy tắc của API. Không nên tự giả định bit mask sau khi drop chỉ khác đúng một bit; nếu cần biết quyền còn lại, kiểm tra bằng `lookupModes()` hoặc các phương thức predicate thích hợp.

Một số lưu ý:

- Không thể dùng `dropLookupMode` để thêm lại quyền.
- Phương thức nhận một mode hợp lệ được định nghĩa bởi `Lookup`.
- Nếu mode không có trong lookup, kết quả có thể giữ nguyên lookup hiện tại.
- Lookup trả về là đối tượng riêng với tập quyền bị giới hạn.

### 9.1. Tạo lookup ít quyền trước khi chia sẻ

Ví dụ một thành phần chỉ cần public access:

```java
MethodHandles.Lookup internal = MethodHandles.lookup();

MethodHandles.Lookup apiOnly =
        internal.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Đây là minh họa ý tưởng giảm quyền. Khi thiết kế thực tế, cần hiểu các mode liên quan và xác nhận kết quả; nếu chỉ cần public access phổ quát, `MethodHandles.publicLookup()` có thể diễn đạt ý định rõ hơn.

## 10. `privateLookupIn` — xin lookup có private access cho class khác

`MethodHandles.privateLookupIn` là API quan trọng khi làm framework, mapper hoặc thư viện cần truy cập thành viên private của class khác.

Cú pháp:

```java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(targetClass, callerLookup);
```

Trong đó:

- `targetClass` là class mà lookup mới sẽ dùng làm lookup class.
- `callerLookup` là lookup hiện có, đại diện cho quyền của code yêu cầu.
- Lookup mới có private access tới target nếu các điều kiện về quyền và module được đáp ứng.

### 10.1. Điều kiện truy cập

Trong Java 17, caller lookup cần có các quyền phù hợp, đặc biệt là `PRIVATE` và `MODULE`. Nếu target class thuộc module khác, package chứa target class phải được **open tới module của caller**.

Nếu điều kiện không đáp ứng, lời gọi có thể ném `IllegalAccessException`.

Một số điểm cần nhớ:

1. `privateLookupIn` không phải API cấp private access vô điều kiện.
2. Module của target cần mở package cho module caller khi hai class nằm ở module khác nhau.
3. `opens` là cơ chế module descriptor dùng cho deep reflection/access.
4. Lookup kết quả có target class làm lookup class và giữ thông tin previous lookup class.
5. Khi chuyển qua module boundary, quyền `MODULE` bị loại khỏi lookup kết quả; không nên coi nó tương đương lookup full privilege được tạo ngay bên trong target module.

Nếu target và caller cùng module, không cần mở package qua ranh giới module, nhưng caller lookup vẫn phải có các mode cần thiết theo API.

### 10.2. Ví dụ module descriptor với qualified opens

Module chứa class cần truy cập:

```java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.internal
            to com.example.framework;
}
```

Module framework:

```java
module com.example.framework {
    requires com.example.domain;
}
```

`opens com.example.domain.internal to com.example.framework` cho phép module framework thực hiện deep reflection/private lookup vào package nội bộ này theo quy tắc module system.

Nếu chỉ có `exports`, framework có thể truy cập API public trong package đã export, nhưng không có quyền deep reflection vào private member chỉ nhờ export.

### 10.3. Tạo private lookup và tìm private method

Giả sử framework đã nhận được `Class<?> targetClass` từ cơ chế đăng ký model hoặc reflection:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

MethodHandles.Lookup caller = MethodHandles.lookup();

MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(targetClass, caller);

MethodHandle handle = targetLookup.findVirtual(
        targetClass,
        "internalValue",
        MethodType.methodType(String.class)
);
```

Nếu package của target được mở cho module framework và caller lookup đủ quyền, framework có thể tạo handle tới private method `internalValue`.

Việc lấy được `Class<?>` và việc được phép truy cập private member là hai việc khác nhau. Có class object không tự động đồng nghĩa có quyền truy cập mọi thành viên của class đó.

### 10.4. Tại sao không mở toàn bộ module?

Có thể dùng `opens` không kèm danh sách module để mở mọi package của module cho deep reflection, nhưng điều đó làm giảm tính đóng gói.

Ưu tiên qualified opens khi biết rõ framework nào cần truy cập:

```java
opens com.example.domain.internal to com.example.framework;
```

Chỉ mở đúng package và đúng module cần thiết. Không dùng một khai báo mở rộng chỉ để làm biến mất lỗi truy cập mà chưa hiểu nguyên nhân.

## 11. `exports` và `opens` ảnh hưởng tới Lookup ra sao?

Hai directive này có ý nghĩa khác nhau:

- `exports` công khai package cho truy cập thông thường tới các kiểu public.
- `opens` cho phép deep reflection vào package, bao gồm khả năng truy cập private qua những API như `privateLookupIn` khi các điều kiện còn lại được đáp ứng.

| Module directive | Public API access | Deep reflection/private lookup |
|---|---|---|
| Không export, không open | Module khác không truy cập package như API thông thường | Không được mở cho deep reflection từ module khác |
| `exports package` | Cho phép truy cập kiểu public trong package theo quy tắc module | Không tự cho phép private lookup |
| `opens package` | Không tự công khai package cho import/compile-time API thông thường | Cho phép deep reflection có kiểm soát |
| `exports package to M` | Chỉ module M được truy cập API public của package | Không tự cho private lookup |
| `opens package to M` | Không tự export API public | Module M có thể thực hiện deep reflection |

`privateLookupIn` cần package open khi target ở module khác. Chỉ thêm `requires` ở module caller không đủ để truy cập private member.

### 11.1. Dùng --add-opens khi chạy

Trong một số tình huống vận hành hoặc chẩn đoán, JVM hỗ trợ option `--add-opens` để mở package ở runtime:

```bash
java --add-opens com.example.domain/com.example.domain.internal=com.example.framework \
     --module-path mods \
     -m com.example.framework/com.example.framework.Main
```

Option này điều chỉnh quyền mở package trong runtime module graph. Nó không phải thay thế mặc định cho thiết kế module descriptor. Với ứng dụng do mình kiểm soát, khai báo qualified `opens` trong module descriptor thường thể hiện rõ hợp đồng hơn.

## 12. Lookup và reflection: giống và khác

Reflection và Method Handles đều có thể tìm và thao tác với thành viên class, nhưng mô hình sử dụng khác nhau.

| Reflection | Method Handles |
|---|---|
| Dùng `Class`, `Method`, `Field`, `Constructor` | Dùng `Lookup`, `MethodHandle`, `VarHandle` |
| Có thể bật access override qua `setAccessible`/`trySetAccessible` nếu module cho phép | Tạo handle qua lookup với quyền truy cập phù hợp |
| Gọi method qua `Method.invoke` | Gọi handle qua `invoke`/`invokeExact` |
| API phản chiếu mô tả member và metadata | Handle là đối tượng thao tác có kiểu |
| Kiểm tra access có thể gắn với trạng thái accessible của reflection object | Quyền được kiểm tra khi lookup tạo handle |

### 12.1. Lookup không phải cách né strong encapsulation

Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findVirtual(
        SomeLibraryClass.class,
        "privateOperation",
        MethodType.methodType(void.class)
);
```

Nếu class hiện tại không có quyền truy cập private và module không mở package phù hợp, việc tìm handle sẽ thất bại. Method Handles vẫn tuân thủ module access control.

### 12.2. trySetAccessible và privateLookupIn

Với reflection, `trySetAccessible()` yêu cầu điều kiện module phù hợp để bật quyền truy cập sâu. Với Method Handles, `privateLookupIn` tạo lookup object có private access theo điều kiện tương ứng.

Cả hai đều chịu ảnh hưởng của module encapsulation. Đừng coi một API là lối tắt để truy cập implementation detail của JDK hoặc thư viện bên thứ ba.

## 13. Lookup object như một capability bảo mật

Trong thiết kế bảo mật, một **capability** là đối tượng đại diện cho quyền thực hiện một hành động cụ thể. Lookup object và các handle được tạo từ nó có đặc tính gần với capability:

- Lookup full privilege có thể tạo handle tới nhiều thành viên trong phạm vi quyền của nó.
- Một handle tới private method có thể cho phép người nhận gọi method đó dù người nhận không thể tự tìm method.
- Một lookup được thu hẹp chỉ có thể tạo các handle trong phạm vi quyền còn lại.
- Truyền lookup hoặc handle ra ngoài đồng nghĩa chia sẻ quyền tương ứng.

Ví dụ, một framework cần đọc một field private để ánh xạ dữ liệu. Thay vì trao lookup full privilege của module ứng dụng cho framework, ứng dụng có thể chỉ tạo handle cho field cần thiết rồi trao handle đó:

```java
MethodHandle nameReader = targetLookup.findGetter(
        Customer.class,
        "name",
        String.class
);

// Chỉ trao nameReader cho thành phần cần đọc tên.
```

Bên nhận có thể đọc đúng field được handle đại diện; nó không tự có lookup để tìm mọi private member khác của `Customer`.

### 13.1. Không chia sẻ lookup mạnh nếu không cần

Tránh:

```java
// Thiết kế rủi ro nếu recipient không được tin cậy.
plugin.initialize(MethodHandles.lookup());
```

Lookup này được tạo từ class gọi và có thể có full privilege access. Nếu plugin giữ lookup, nó có thể tạo các handle trong phạm vi quyền của lookup đó.

Nên cân nhắc:

- Chỉ truyền MethodHandle cụ thể cần dùng.
- Dùng `publicLookup()` nếu chỉ cần API public.
- Tạo lookup hẹp bằng cách loại bỏ mode không cần.
- Không để module mở package rộng hơn yêu cầu.
- Đặt ranh giới rõ giữa code tin cậy và plugin.

Không phải mọi plugin đều không đáng tin; đây là nguyên tắc thiết kế quyền theo nhu cầu tối thiểu.

## 14. Quyền của Lookup và các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `IllegalAccessException` khi gọi `findVirtual` | Lookup không có mode hoặc package access phù hợp | Kiểm tra lookup class, mode, package export/open và module |
| `NoSuchMethodException` | Sai tên method hoặc `MethodType` | Kiểm tra tên, kiểu tham số và kiểu trả về |
| `NoSuchFieldException` | Sai tên field hoặc kiểu field | Kiểm tra field declaration và type chính xác |
| `privateLookupIn` ném `IllegalAccessException` | Caller thiếu PRIVATE/MODULE hoặc target package chưa open | Kiểm tra caller lookup và qualified opens |
| Dùng `publicLookup` nhưng không truy cập được package qualified export | Public lookup không đại diện module client cụ thể | Dùng lookup phù hợp của caller/module được export hoặc thiết kế API public rõ ràng |
| `in(targetClass)` không truy cập được private member | `in` không cấp thêm private access | Dùng `privateLookupIn` khi module cho phép |
| Handle tìm được nhưng gọi bị lỗi kiểu | Kiểu receiver/argument không khớp handle type | Kiểm tra `MethodType` và chữ ký call site |
| Plugin gọi được private method sau khi nhận handle | Handle đã mang quyền truy cập khi được tạo | Chỉ trao handle khi thực sự muốn cấp capability đó |

### 14.1. Phân biệt lỗi tìm member và lỗi gọi handle

Có hai thời điểm có thể phát sinh lỗi:

**Khi tìm member:**

```java
MethodHandle handle = lookup.findVirtual(
        Greeter.class,
        "missing",
        MethodType.methodType(String.class)
);
```

Nếu không tồn tại method phù hợp, việc tìm handle thất bại, thường với `NoSuchMethodException`.

**Khi gọi handle:**

```java
String result = (String) handle.invokeExact("wrong receiver");
```

Nếu call site không khớp chính xác kiểu handle, `invokeExact` có thể ném `WrongMethodTypeException`. Nếu receiver không hợp lệ, có thể phát sinh lỗi kiểu runtime tương ứng.

Không quy mọi lỗi Method Handle về lỗi quyền truy cập. Hãy xác định lỗi xuất hiện ở bước lookup hay bước invocation.

### 14.2. Kiểm tra lookup modes khi debug

Có thể in thông tin lookup:

```java
static void describe(MethodHandles.Lookup lookup) {
    System.out.println("Lookup class: " + lookup.lookupClass().getName());
    System.out.println("Modes: " + lookup.lookupModes());
    System.out.println(
            "Full privilege: " + lookup.hasFullPrivilegeAccess()
    );
    System.out.println(
            "Previous lookup class: " + lookup.previousLookupClass()
    );
}
```

Thông tin này giúp biết lookup đang đại diện class nào và còn quyền gì. Không nên ghi log hoặc chia sẻ lookup object mạnh trong hệ thống production chỉ để debug; các thông tin về quyền truy cập cũng cần được quản lý phù hợp.

## 15. Ví dụ hoàn chỉnh: tạo lookup hẹp và gọi handle

Ví dụ sau minh họa public lookup, lookup của class hiện tại và handle đã được tạo.

Tạo file `LookupDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupDemo {
    public static class Calculator {
        public int add(int left, int right) {
            return left + right;
        }

        private int secretMultiply(int value) {
            return value * 10;
        }

        public static MethodHandle secretHandle()
                throws NoSuchMethodException, IllegalAccessException {
            MethodHandles.Lookup ownLookup = MethodHandles.lookup();

            return ownLookup.findVirtual(
                    Calculator.class,
                    "secretMultiply",
                    MethodType.methodType(int.class, int.class)
            );
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle addHandle = lookup.findVirtual(
                Calculator.class,
                "add",
                MethodType.methodType(int.class, int.class, int.class)
        );

        Calculator calculator = new Calculator();

        int sum = (int) addHandle.invokeExact(calculator, 10, 20);
        System.out.println("Sum: " + sum);

        MethodHandle secretHandle = Calculator.secretHandle();

        int secretResult =
                (int) secretHandle.invokeExact(calculator, 7);

        System.out.println("Private result: " + secretResult);

        MethodHandles.Lookup publicLookup = MethodHandles.publicLookup();

        MethodHandle lengthHandle = publicLookup.findVirtual(
                String.class,
                "length",
                MethodType.methodType(int.class)
        );

        int length = (int) lengthHandle.invokeExact("Java 17");
        System.out.println("Length: " + length);

        System.out.println("Lookup class: " + lookup.lookupClass().getName());
        System.out.println(
                "Full privilege: " + lookup.hasFullPrivilegeAccess()
        );
    }
}
```

Biên dịch và chạy trên JDK 17:

```bash
javac --release 17 LookupDemo.java
java LookupDemo
```

Kết quả:

```text
Sum: 30
Private result: 70
Length: 8
Lookup class: LookupDemo
Full privilege: true
```

Phân tích:

1. `lookup` được tạo trong `LookupDemo.main` nên lookup class là `LookupDemo`.
2. `add` là public method; lookup hiện tại có thể tạo handle.
3. `secretMultiply` là private method. `Calculator.secretHandle` gọi `lookup()` từ bên trong `Calculator`, nên có private access phù hợp.
4. Handle private được trả về cho `main`; caller có thể gọi handle đã tạo.
5. `publicLookup` tìm được `String.length` vì đây là public method của public class trong package được export vô điều kiện.
6. Không cần trao lookup full privilege của `Calculator` cho `main`; chỉ trao handle cần thiết.

## 16. Bài tập tự luyện

### Bài 1 — Lookup class là class nào?

```java
class Service {
    static MethodHandles.Lookup lookup() {
        return MethodHandles.lookup();
    }
}

class Client {
    void run() {
        MethodHandles.Lookup lookup = Service.lookup();
    }
}
```

**Câu hỏi:** `lookup.lookupClass()` trả về `Service.class` hay `Client.class`?

**Đáp án:** `Service.class`. Lời gọi `MethodHandles.lookup()` diễn ra bên trong phương thức `Service.lookup`.

### Bài 2 — publicLookup có tìm được private method không?

```java
MethodHandles.Lookup lookup = MethodHandles.publicLookup();
```

**Đáp án:** Không. `publicLookup` chỉ có public access theo phạm vi được API quy định; nó không có private access.

### Bài 3 — requires có đủ cho privateLookupIn không?

Một module framework khai báo `requires com.example.domain`. Module domain không mở package chứa class target cho framework.

**Câu hỏi:** Framework có thể gọi `privateLookupIn` để truy cập private member không?

**Đáp án:** Không chỉ nhờ `requires`. Khi target ở module khác, package của target cần được mở cho module framework; caller lookup cũng phải có các quyền cần thiết.

### Bài 4 — in hay privateLookupIn?

Bạn có lookup của class A và muốn tạo lookup có private access tới class B ở module khác, package B đã mở cho module A.

**Đáp án:** Dùng `MethodHandles.privateLookupIn(B.class, lookupA)` nếu lookup A thỏa điều kiện. `lookupA.in(B.class)` không phải cách xin thêm private access.

### Bài 5 — Handle có mang quyền truy cập không?

Class A tạo handle tới private method của A rồi truyền handle cho class B.

**Đáp án:** Có. B có thể gọi handle đã nhận dù B không tự có quyền tìm private method đó. Vì thế, truyền handle là trao khả năng thực hiện thao tác.

### Bài 6 — `requires transitive` có mở private member không?

**Đáp án:** Không. `requires transitive` truyền readability giữa module. Muốn deep reflection/private lookup qua module boundary, package target phải được mở phù hợp bằng `opens` hoặc cơ chế runtime tương ứng.

### Bài 7 — Tìm lỗi kiểu handle

Một handle có kiểu `(Greeter, String)String`. Call site dùng `invokeExact` với đối số `(Object, String)String`.

**Đáp án:** Kiểu call site không khớp chính xác kiểu handle; có thể phát sinh `WrongMethodTypeException`. Với `invokeExact`, kiểu tĩnh tại call site rất quan trọng.

## 17. Ghi nhớ

- `MethodHandles.Lookup` đại diện cho **ngữ cảnh và quyền truy cập** dùng để tìm MethodHandle/VarHandle.
- `lookupClass()` cho biết class làm ngữ cảnh; nó phụ thuộc nơi gọi `MethodHandles.lookup()`.
- `lookupModes()` cho biết tập mode; `hasFullPrivilegeAccess()` kiểm tra full privilege access.
- `MethodHandles.lookup()` tạo lookup gắn với class gọi.
- `MethodHandles.publicLookup()` chỉ cung cấp public access theo phạm vi export vô điều kiện.
- `Lookup.in` đổi lookup class và có thể thu hẹp quyền; nó không cấp thêm private access.
- `dropLookupMode` chủ động giảm quyền.
- `privateLookupIn` tạo lookup có private access cho target khi caller đủ quyền và package target được mở nếu đi qua module boundary.
- `requires` tạo readability; `exports` công khai API public; `opens` cho phép deep reflection.
- Quyền được kiểm tra khi tạo handle; handle sau đó có thể được truyền cho code khác và vẫn thực hiện thao tác đã được cấp.
- Lookup và handle có quyền mạnh nên được quản lý như capability; chỉ chia sẻ đúng quyền mà thành phần nhận cần.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `java.lang.invoke.MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Java SE 17 API — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 17 API — `java.lang.invoke.MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 17 API — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html).
- [Java SE 17 API — `java.lang.Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
- [Java Language Specification 17 — `7.7`: Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).

