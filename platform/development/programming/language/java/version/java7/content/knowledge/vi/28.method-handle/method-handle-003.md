# MethodHandles.Lookup và kiểm tra quyền truy cập trong Java

**Chủ đề:** Java 7 — MethodHandle  
**Bài học:** `MethodHandles.Lookup` và kiểm tra quyền truy cập  
**Phiên bản sử dụng:** JDK 17 trở lên. `MethodHandle`, `MethodType` và `MethodHandles.Lookup` xuất hiện từ Java 7 và **vẫn là API hiện hành**. Một số công cụ quan trọng bổ sung sau Java 7, gồm `privateLookupIn`, `VarHandle`, Java Platform Module System (JPMS) và `Lookup.ORIGINAL`; bài sử dụng những API đang được hỗ trợ trong Java 17/21 và tránh mẹo truy cập nội bộ JDK đã lỗi thời.

## 1. Vấn đề: tìm một method chưa chắc có quyền gọi nó

Ở Java, một method có thể tồn tại nhưng không phải caller nào cũng được phép sử dụng:

```text
public class Account {
    private long balance;
    private void audit() { ... }
    public String id() { ... }
}

Caller ngoài Account:
    - Gọi id() nếu class/member/module cho phép.
    - Không tự động được gọi audit() hay đọc balance.
```

Cơ chế truy cập của ngôn ngữ gồm `public`, `protected`, package-private và `private`. Từ Java 9, JPMS còn áp dụng các ràng buộc **module readability**, `exports` và `opens`. Việc tìm method qua tên, signature hoặc reflection không có nghĩa có quyền thực thi nó.

`MethodHandles.Lookup` là **factory cho những `MethodHandle` đã được kiểm tra quyền truy cập**. Một `Lookup` lưu một **lookup class** (đại diện cho quyền của code tạo nó) cùng các **lookup modes**; các phương thức như `findStatic` và `findVirtual` sử dụng ngữ cảnh đó để quyết định có được tạo handle tới member hay không.

Sự khác biệt then chốt so với việc nghĩ về reflective invocation:

- **Tạo handle:** `Lookup` kiểm tra class/member/lookup modes/module tại thời điểm *lookup*.
- **Gọi handle:** một `MethodHandle` đã được tạo thành công không lặp lại kiểm tra Java access đối với từng caller ở mỗi lần gọi; thay vào đó nó kiểm tra **kiểu và các yêu cầu thực thi**.
- **Hệ quả:** handle là một **capability** có thể trao quyền gọi member. Đừng gửi handle private hoặc privileged `Lookup` cho code không đáng tin cậy.
- **Không có cách “đặt Lookup thành public” rồi gọi mọi private method.** Thao tác đổi ngữ cảnh có điều kiện bảo mật; thậm chí có thể làm **mất quyền**.
- **Một member tồn tại nhưng không thể truy cập** khác **một member không tồn tại**; các trường hợp thất bại có kiểu ngoại lệ khác nhau.

### 1.1. Hình dung dòng chảy

```text
Code trong lớp A gọi MethodHandles.lookup()
                  |
                  v
Lookup{lookupClass=A, modes=...}
                  |
                  +--- findStatic/findVirtual/findGetter/findConstructor
                  |                |
                  |       Kiểm tra class/member/module/quyền
                  |                |
                  |          +-----+------+
                  |          |            |
                  |      Allowed        Denied
                  |          |            |
                  |      MethodHandle  IllegalAccessException
                  |          |
                  |       invokeExact/invoke
                  |          |
                  v          v
           Không tự cấp quyền thêm khi gọi
```

## 2. Những khái niệm cần nắm

| Tên | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `MethodHandles` | Utility class để tạo lookup và tổ hợp handles | `MethodHandles.lookup()` |
| `MethodHandles.Lookup` | Ngữ cảnh/factory **mang quyền** khi tìm method/field/constructor | `Lookup lookup = MethodHandles.lookup()` |
| `MethodHandle` | Tham chiếu có kiểu đến một callable/method/field operation đã được cho phép | `lookup.findStatic(...)` |
| `MethodType` | Mô tả **kiểu trả về** và **các kiểu tham số** của method | `methodType(int.class,int.class,int.class)` |
| `lookupClass()` | Class mà `Lookup` lấy làm ngữ cảnh truy cập | Class của nơi gọi `MethodHandles.lookup()` |
| `lookupModes()` | Bitmask các mức quyền hiện hữu | `PRIVATE`, `PACKAGE`, `MODULE`, ... |
| `publicLookup()` | Factory quyền rất hạn chế cho public API | `Math.max`, `String.toUpperCase` |
| `Lookup.in(target)` | Chuyển lookup class trong giới hạn quyền cũ | Không phải nâng quyền |
| `privateLookupIn(target,caller)` | Tạo lookup có private capability **khi điều kiện deep reflection cho phép** | Target khác nest, trong module tương thích |
| `dropLookupMode(mode)` | Tạo lookup mới **đã giảm quyền** | Không còn private access |
| `findSpecial` | Tạo handle cho một lời gọi dạng `invokespecial`, cần ngữ cảnh rất cụ thể | Lời gọi tương tự `super.method()` |
| `VarHandle` | API Java 9 cho truy cập biến và các access modes, bao gồm atomic operations | `lookup.findVarHandle(...)` |

**`Lookup` không phải đối tượng thực thi SQL hay hệ thống đăng nhập.** “Quyền truy cập” ở đây là **quy tắc access của Java/JVM/JPMS đối với class members**, không phải quyền user account/OS hoặc quyền database.

### 2.1. Vì sao việc này vẫn hữu ích?

Method handles được dùng trong runtime frameworks, dynamic language runtimes, dependency injection, serializers, property binding, dynamic dispatch và những trình biên dịch dùng `invokedynamic`. Chúng cho phép tạo một operation có kiểu và tái sử dụng sau khi bước kiểm tra quyền thành công.

**Không nên dùng method handles chỉ để thay thế mọi lời gọi Java trực tiếp.** Nếu code đã biết method tại compile time, cú pháp `object.method()` thường đơn giản và an toàn kiểu hơn. `Lookup` đặc biệt có giá trị khi tên và signature chỉ được biết lúc runtime, nhưng vẫn phải tôn trọng quyền truy cập.

## 3. Lấy Lookup đúng ngữ cảnh bằng MethodHandles.lookup()

Phương thức:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

là **caller-sensitive**: nó xác định **class đang thực sự gọi `MethodHandles.lookup()`**. Quyền của lookup không tự trở thành quyền của bất kỳ code nào sau này cầm reference đó.

Một static helper ở class A gọi `MethodHandles.lookup()` rồi trả object cho B vẫn trả lookup có **ngữ cảnh A**, không tự biến thành ngữ cảnh B. Điều này có ý nghĩa bảo mật lớn nếu A có các members private.

### 3.1. Chương trình độc lập: lookup class và modes

Tạo `LookupIdentityDemo.java`:

```java
import java.lang.invoke.MethodHandles;
public class LookupIdentityDemo {
  static final class Nested {
    static MethodHandles.Lookup ownLookup() { return MethodHandles.lookup(); }
  }
  public static void main(String[] args) {
    MethodHandles.Lookup caller = MethodHandles.lookup();
    MethodHandles.Lookup nested = Nested.ownLookup();
    MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
    System.out.println("lookup-class=" + caller.lookupClass().getSimpleName());
    System.out.println("nested-lookup-class=" + nested.lookupClass().getSimpleName());
    System.out.println("caller-full-privilege=" + caller.hasFullPrivilegeAccess());
    System.out.println("public-has-private=" + ((publicOnly.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
    System.out.println("public-unconditional=" + ((publicOnly.lookupModes() & MethodHandles.Lookup.UNCONDITIONAL) != 0));
    System.out.println("previous-lookup-null=" + (caller.previousLookupClass() == null));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LookupIdentityDemo.java
java LookupIdentityDemo
```

**stdout đã kiểm thử:**

```text
lookup-class=LookupIdentityDemo
nested-lookup-class=Nested
caller-full-privilege=true
public-has-private=false
public-unconditional=true
previous-lookup-null=true
```

**Phân tích:** cả hai nơi gọi `lookup()` là hai class khác nhau. `lookupClass()` ghi lại khác biệt đó, không phụ thuộc ai gọi `Nested.ownLookup()`. `hasFullPrivilegeAccess()` là API hiện hành, nhưng không nên dùng nó như một cơ chế tự cấp quyền. `publicLookup()` có mode `UNCONDITIONAL`, **không phải một lookup “có mọi quyền vì public”**.

**Đặc điểm của demo:** chạy trên classpath/unnamed module không có flags đặc biệt. Kết quả về `lookupClass` và mức quyền của caller đúng với contract chuẩn của JDK 17+.

### 3.2. lookupModes là bitmask, không phải một cấp số nguyên

Đừng so `lookupModes()==1` rồi suy ra “public”. Quyền có nhiều bits tương tác và JPMS còn bổ sung kiểm tra module. Kiểm tra từng flag bằng phép `&`:

```java
boolean canPrivate = (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
```

Đây là snippet. **Có `PRIVATE` bit không tự chứng minh được truy cập mọi private member của mọi class**. Lookup class, nest, package, module readability/opens và các access rules vẫn quyết định.

## 4. Các access modes trong Java 17+

Các constants:

| Mode | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `PUBLIC` | Truy cập public members theo các quy tắc class/module | Không đồng nghĩa toàn bộ mã nguồn đều truy cập được |
| `PRIVATE` | Khả năng truy cập private ở phạm vi lookup class/nest đủ điều kiện | Không phải global private access |
| `PROTECTED` | Hỗ trợ truy cập protected theo JVM rules | Có thêm ràng buộc receiver ở khác package |
| `PACKAGE` | Truy cập package-private khi cùng runtime package phù hợp | Không bỏ qua JPMS |
| `MODULE` | Lookup gắn với module ngữ cảnh theo quy tắc module | Cần thiết cùng `PRIVATE` cho `privateLookupIn` |
| `ORIGINAL` | Đánh dấu lookup gốc tạo bởi `lookup()` hoặc bootstrap context hợp lệ | Mode hiện hành từ Java 16, không phải privilege setter |
| `UNCONDITIONAL` | Quyền public có tính đọc mọi module theo điều kiện package exported unconditionally | `publicLookup()` thường có mode này |

**Không gộp `PUBLIC` và `UNCONDITIONAL`** thành một flag giống nhau. `publicLookup()` được định nghĩa là tối thiểu về quyền, nhưng mode `UNCONDITIONAL` cho phép truy cập **public class trong package được export vô điều kiện** từ các modules.

### 4.1. Những mode không nói hết câu chuyện

Ví dụ một lookup có `PUBLIC`:

- Có thể tìm public method của **public class** trong một package exported phù hợp.
- Có thể thất bại khi class chứa method là **package-private**.
- Có thể thất bại nếu package của một named module **không exported** tới module của lookup class.
- Không tự tìm private members chỉ vì tên và chữ ký đúng.

Một lookup có `PRIVATE` trong A cũng không tự động truy cập private members của class B khác nest. Nếu cần và có quyền, sử dụng `privateLookupIn(B.class,lookup)`, tuân theo module opens.

### 4.2. Tra quyền khi nào?

Factory methods của Lookup như `findVirtual`, `findStatic`, `findGetter`, `findConstructor` kiểm tra access **lúc tạo handle**. Nếu thành công, handle có thể được gọi lại theo kiểu của nó.

**Không suy rằng mọi method-handle transformation như `asType` cũng thực hiện một vòng Java access checking mới**. `asType` chỉ chỉnh/adapt type theo phép chuyển đổi được hỗ trợ; nó không biến một lookup bất hợp pháp thành hợp pháp.

## 5. publicLookup để truy cập những public APIs thông thường

Nếu một framework chỉ cần public classes và public methods của APIs được export, một `publicLookup()` thường là lựa chọn có **quyền nhỏ hơn** so với truyền full caller lookup.

```java
MethodHandles.Lookup pub = MethodHandles.publicLookup();
MethodHandle max = pub.findStatic(
    Math.class, "max", MethodType.methodType(int.class, int.class, int.class));
```

Đây là snippet cần các imports. `Math` thuộc `java.base` và public methods của nó được phép truy cập.

### 5.1. Chương trình: findStatic, findVirtual và findConstructor

Tạo `PublicMembersDemo.java`:

```java
import java.lang.invoke.*;
public class PublicMembersDemo {
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup pub = MethodHandles.publicLookup();
    MethodHandle max = pub.findStatic(Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));
    MethodHandle upper = pub.findVirtual(String.class, "toUpperCase",
        MethodType.methodType(String.class));
    MethodHandle make = pub.findConstructor(StringBuilder.class,
        MethodType.methodType(void.class, String.class));
    int biggest = (int) max.invokeExact(7, 12);
    String greeting = (String) upper.invokeExact("hello");
    StringBuilder buffer = (StringBuilder) make.invokeExact("start");
    System.out.println("max=" + biggest);
    System.out.println("upper=" + greeting);
    System.out.println("constructor=" + buffer);
    System.out.println("virtual-parameter-count=" + upper.type().parameterCount());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PublicMembersDemo.java
java PublicMembersDemo
```

**stdout đã kiểm thử:**

```text
max=12
upper=HELLO
constructor=start
virtual-parameter-count=1
```

### 5.2. MethodType cần mô tả gì?

`MethodType.methodType(int.class,int.class,int.class)` biểu diễn method trả int và nhận hai int.

Với `findVirtual(String.class,"toUpperCase",methodType(String.class))`, kiểu method được cung cấp **không gồm receiver**. Nhưng handle tạo ra có một tham số receiver `String`, nên `upper.type().parameterCount()` là **1**. Đây là điểm hay nhầm khi tạo `MethodType`.

Với `findConstructor(StringBuilder.class,methodType(void.class,String.class))`, type được cung cấp mô tả constructor với **return type void**, nhưng **handle kết quả** trả object được tạo, là `StringBuilder`. Đừng đặt return type của input constructor là `StringBuilder.class` chỉ vì `new StringBuilder(...)` cho ra object.

### 5.3. Cần kiểm tra cả class lẫn member

Một method khai báo `public` bên trong một **package-private class** không tự có thể được `publicLookup()` tìm thấy. Tương tự, nếu module chứa class không `exports` package cần thiết, public keyword chưa đủ.

## 6. Lookup có quyền truy cập private trong cùng nest

Java 11+ biểu diễn nestmates rõ trong class files: outer và static nested class có thể là nestmates. `MethodHandles.lookup()` ở outer class có thể tạo handle tới các members private của nested class trong cùng nest, theo access rules chuẩn.

**Không đồng nghĩa** một class khác có tên giống hoặc nằm chung package sẽ được xem là nestmate. Nest relation là thuộc tính JVM/bytecode, không phải quy tắc đặt tên.

### 6.1. Chương trình: đọc private field và gọi private method của nestmate

Tạo `NestmatePrivateDemo.java`:

```java
import java.lang.invoke.*;
public class NestmatePrivateDemo {
  private static final class Vault {
    private String code = "internal";
    private String reveal(int n) { return code + "-" + n; }
  }
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup lookup = MethodHandles.lookup();
    MethodHandle getter = lookup.findGetter(Vault.class, "code", String.class);
    MethodHandle reveal = lookup.findVirtual(Vault.class, "reveal",
        MethodType.methodType(String.class, int.class));
    Vault vault = new Vault();
    String read = (String) getter.invokeExact(vault);
    String result = (String) reveal.invokeExact(vault, 7);
    System.out.println("nestmates=" + NestmatePrivateDemo.class.isNestmateOf(Vault.class));
    System.out.println("private-field=" + read);
    System.out.println("private-method=" + result);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all NestmatePrivateDemo.java
java NestmatePrivateDemo
```

**stdout đã kiểm thử:**

```text
nestmates=true
private-field=internal
private-method=internal-7
```

**Giải thích:** lookup gốc của outer class có quyền phù hợp trong nest. Nó tạo handle `findGetter` cho `code` và `findVirtual` cho `reveal(int)`. Khi gọi handle, kiểu receiver `Vault` phải khớp; `String` nhận về được cast đúng kiểu.

Một class **không cùng nest** nhưng cùng package thường không thể tự gọi private method kiểu này. Đừng nhầm một lớp package-private với một lớp private nested.

### 6.2. Access rule khác reflection setAccessible

Với method handles, nên **tạo Lookup đúng quyền** và dùng factory method tương ứng. Việc cố mở quyền reflection bằng `setAccessible(true)` không phải một “lối tắt” an toàn chung khi JPMS khóa deep reflection. Đặc biệt, JDK hiện đại **không** mở mọi package `java.base` cho ứng dụng chỉ vì một class có tên đúng.

Nếu một framework có quyền hợp lệ để dùng `privateLookupIn`, nó nên dùng cơ chế đó thay vì cậy vào unsupported internal APIs hoặc flags nới quyền cho toàn bộ JVM.

## 7. privateLookupIn: truy cập private của một class khác khi được phép

Từ Java 9, API:

```java
MethodHandles.Lookup deep =
    MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup());
```

cho phép tạo một lookup lấy `Target` làm class ngữ cảnh và có private capability **nếu điều kiện truy cập deep reflection thỏa mãn**.

Điều kiện cốt lõi:

1. Caller lookup có **cả `PRIVATE` và `MODULE` access**.
2. Nếu target trong cùng module, deep lookup được phép theo access rules.
3. Nếu target ở module khác, module của caller cần **reads** target module, và target module phải **opens** package chứa class tới caller module (hoặc mở unqualified).
4. `privateLookupIn` **không tự vượt qua module encapsulation** và không phải “bypass mọi private”.
5. Lookup sau khi chuyển sang module khác có thể **mất `MODULE` mode**, nên không thể dùng nó tùy ý để tiếp tục tạo private lookups ở module thứ ba.

### 7.1. Chương trình: một top-level class khác, cùng unnamed module

Tạo `PrivateLookupInDemo.java` (một file chứa một public class và một package-private class):

```java
import java.lang.invoke.*;
class DeepTarget {
  private static String hidden() { return "deep-ok"; }
}
public class PrivateLookupInDemo {
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup caller = MethodHandles.lookup();
    boolean denied = false;
    try {
      caller.findStatic(DeepTarget.class, "hidden", MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { denied = true; }
    MethodHandles.Lookup deep = MethodHandles.privateLookupIn(DeepTarget.class, caller);
    MethodHandle handle = deep.findStatic(DeepTarget.class, "hidden",
        MethodType.methodType(String.class));
    String result = (String) handle.invokeExact();
    System.out.println("ordinary-denied=" + denied);
    System.out.println("private-lookup-result=" + result);
    System.out.println("target-lookup-class=" + (deep.lookupClass() == DeepTarget.class));
    System.out.println("deep-private-mode=" + ((deep.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PrivateLookupInDemo.java
java PrivateLookupInDemo
```

**stdout đã kiểm thử:**

```text
ordinary-denied=true
private-lookup-result=deep-ok
target-lookup-class=true
deep-private-mode=true
```

**Phân tích:** `PrivateLookupInDemo` và `DeepTarget` là hai top-level classes **khác nest**, nên caller lookup ban đầu không đọc được `DeepTarget.hidden()` dù chúng cùng package. `privateLookupIn` tạo lookup sâu trên `DeepTarget` vì chúng ở cùng unnamed module. Sau đó có thể tìm được private static method.

Đây **không** phải bằng chứng rằng có thể làm tương tự trên mọi class trong một named module bất kỳ. Khi code chạy dưới JPMS, `opens` và readability quyết định.

### 7.2. Khi không nên dùng privateLookupIn

- Bạn đã có public API đúng ý nghĩa.
- Quyền truy cập private không được thiết kế/documented như một extension point.
- Target module không mở package cho caller module.
- Dữ liệu nhạy cảm không nên lộ cho plug-in hoặc consumer code.
- Bạn chỉ muốn “chạy qua lỗi illegal access” mà không hiểu hợp đồng.
- Kết quả phụ thuộc chi tiết internal implementation có thể thay đổi giữa JDK/vendor versions.

**Quyền được phép không đồng nghĩa API private ổn định.** Dù private lookup thành công, member private có thể đổi tên/signature qua phiên bản thư viện; cần versioning, tests, integration contracts.

## 8. Vì sao publicLookup không chạm được private class/member?

`publicLookup()` phù hợp cho public API, không phải full privileged lookup. Cần kiểm tra **tính accessible của class chứa member** bên cạnh modifier của member.

### 8.1. Chương trình: class package-private có public method vẫn bị từ chối

Tạo `PublicLookupDenialDemo.java`:

```java
import java.lang.invoke.*;
class PackagePrivateLibrary {
  public static String exposedMethod() { return "method-is-public"; }
}
public class PublicLookupDenialDemo {
  private static String secret() { return "hidden"; }
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
    boolean classDenied = false;
    try {
      publicOnly.findStatic(PackagePrivateLibrary.class, "exposedMethod",
          MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { classDenied = true; }
    boolean memberDenied = false;
    try {
      publicOnly.findStatic(PublicLookupDenialDemo.class, "secret",
          MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { memberDenied = true; }
    MethodHandle parse = publicOnly.findStatic(Integer.class, "parseInt",
        MethodType.methodType(int.class, String.class));
    int value = (int) parse.invokeExact("42");
    System.out.println("package-private-class-denied=" + classDenied);
    System.out.println("private-method-denied=" + memberDenied);
    System.out.println("public-parse-int=" + value);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all PublicLookupDenialDemo.java
java PublicLookupDenialDemo
```

**stdout đã kiểm thử:**

```text
package-private-class-denied=true
private-method-denied=true
public-parse-int=42
```

Lời gọi tới `PackagePrivateLibrary.exposedMethod` bị từ chối **dù method là public**, vì class chứa nó không public. `PublicLookupDenialDemo.secret` là private method của public class nên cũng không accessible cho public lookup. Ngược lại, `Integer.parseInt` là public API trong package được export.

**Đừng thay bằng một lời gọi `setAccessible(true)` vô điều kiện**. Giải pháp bền vững thường là thiết kế public API có contract rõ, hoặc (nếu đúng use case framework) dùng `privateLookupIn` sau khi module owner có chủ ý mở package.

## 9. Lookup.in không phải privateLookupIn

`Lookup.in(Class<?> newLookupClass)` tạo lookup mới với **lookup class khác**, nhưng **không cấp thêm quyền**. Khi đi sang class không cùng nest, lookup có thể **mất `PRIVATE`**; khi qua package, có thể mất `PACKAGE`; khi qua module, có thể mất `MODULE` và còn các kiểm tra cross-module khác.

**Cách hiểu đúng:**

```text
MethodHandles.lookup() trong A có quyền của A
              |
              +-- lookup.in(B.class)
              |      chuyển ngữ cảnh, có thể mất quyền; KHÔNG elevate
              |
              +-- privateLookupIn(B.class, lookup)
                     có thể tạo private lookup B
                     CHỈ NẾU access và module opens cho phép
```

### 9.1. Chương trình: sang sibling cùng package mất PRIVATE

Tạo `LookupInRestrictionDemo.java`:

```java
import java.lang.invoke.*;
class SiblingAccess {
  private static String privateMethod() { return "private"; }
  static String packageMethod() { return "package-ok"; }
}
public class LookupInRestrictionDemo {
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup original = MethodHandles.lookup();
    MethodHandles.Lookup moved = original.in(SiblingAccess.class);
    boolean privateLost = (moved.lookupModes() & MethodHandles.Lookup.PRIVATE) == 0;
    boolean packageRetained = (moved.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0;
    boolean denied = false;
    try {
      moved.findStatic(SiblingAccess.class, "privateMethod",
          MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { denied = true; }
    MethodHandle inPackage = moved.findStatic(SiblingAccess.class, "packageMethod",
        MethodType.methodType(String.class));
    String result = (String) inPackage.invokeExact();
    System.out.println("private-mode-lost=" + privateLost);
    System.out.println("package-mode-preserved=" + packageRetained);
    System.out.println("private-lookup-denied=" + denied);
    System.out.println("package-method=" + result);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LookupInRestrictionDemo.java
java LookupInRestrictionDemo
```

**stdout đã kiểm thử:**

```text
private-mode-lost=true
package-mode-preserved=true
private-lookup-denied=true
package-method=package-ok
```

`SiblingAccess` là top-level class khác nest nhưng cùng package/module với main demo. `Lookup.in` chuyển ngữ cảnh, giữ được package access thích hợp, nhưng **không giữ `PRIVATE`** cho class không cùng nest. Kết quả là package-private method có thể tìm, private method không thể.

### 9.2. Chuyển qua nhiều modules phức tạp hơn

Theo Java SE 17/21, lookup teleport qua module có thể ghi `previousLookupClass()`. Việc kiểm tra public access lúc đó có thể phụ thuộc **cả lookup class hiện tại lẫn previous lookup class**, và có trường hợp teleport sang module thứ ba làm mất mọi quyền. Vì vậy, không viết một helper tổng quát kiểu “lookup.in(anyClass) luôn truy cập được mọi public method” mà không test readability/exports.

**Không tự tối giản cross-module access thành phép so cùng package name.** Hai packages có tên giống nhau nhưng nằm trong modules/classloaders khác nhau có thể là các runtime packages không tương đương.

## 10. dropLookupMode: giảm quyền trước khi chuyển cho thành phần khác

`Lookup.dropLookupMode(int)` tạo **một lookup mới** đã bỏ mode được chỉ định (và có thể thêm các modes phụ thuộc theo quy tắc API). Nó không sửa `Lookup` gốc.

Các ví dụ:

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup reduced =
    full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Đây là snippet. `reduced` không thể tạo private handles chỉ nhờ `PRIVATE` của `full` trước đó. Nhưng **những `MethodHandle` đã được tạo** trước khi giảm quyền **không bị thu hồi**.

### 10.1. Chương trình: giảm quyền không thu hồi handle đã cấp

Tạo `DropModesDemo.java`:

```java
import java.lang.invoke.*;
public class DropModesDemo {
  private static String secret() { return "already-authorized"; }
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup full = MethodHandles.lookup();
    MethodHandle alreadyFound = full.findStatic(DropModesDemo.class, "secret",
        MethodType.methodType(String.class));
    MethodHandles.Lookup restricted = full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
    boolean privateGone = (restricted.lookupModes() & MethodHandles.Lookup.PRIVATE) == 0;
    boolean denied = false;
    try {
      restricted.findStatic(DropModesDemo.class, "secret", MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { denied = true; }
    String oldResult = (String) alreadyFound.invokeExact();
    MethodHandles.Lookup noModule = full.dropLookupMode(MethodHandles.Lookup.MODULE);
    System.out.println("restricted-private-gone=" + privateGone);
    System.out.println("new-private-lookup-denied=" + denied);
    System.out.println("existing-handle=" + oldResult);
    System.out.println("module-and-package-gone=" +
        ((noModule.lookupModes() & (MethodHandles.Lookup.MODULE | MethodHandles.Lookup.PACKAGE)) == 0));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all DropModesDemo.java
java DropModesDemo
```

**stdout đã kiểm thử:**

```text
restricted-private-gone=true
new-private-lookup-denied=true
existing-handle=already-authorized
module-and-package-gone=true
```

### 10.2. Vì sao không dùng dropLookupMode như một revoke mechanism?

Giảm quyền trên **factory mới** chỉ giới hạn các handles **được tạo trong tương lai bằng factory đó**. `alreadyFound` đã là capability gọi private method; nó vẫn hoạt động.

Nếu ứng dụng có yêu cầu **thu hồi quyền runtime**, cần cơ chế authorization ở chính target operation/proxy, revocable switchpoints hoặc control plane thích hợp; **chỉ bỏ mode của Lookup không thu hồi handle đã phát tán**.

### 10.3. Cẩn thận với mode dependencies

Theo JavaDoc:

- Drop `PRIVATE` có thể loại các modes phụ thuộc như `PROTECTED`/`ORIGINAL`.
- Drop `PACKAGE` loại cả package/private access.
- Drop `MODULE` loại module/package/private access.
- Drop `PUBLIC` có thể làm lookup không còn quyền truy cập.

Đừng hard-code kết quả bitmask số nguyên như bất biến bất chấp JDK context; nếu code thực sự dựa vào quyền nào, hãy đọc lại `lookupModes()` và kiểm thử đúng operation được phép.

## 11. Phân biệt lỗi không tìm thấy và lỗi không được phép

Nhóm ngoại lệ khi tạo handle:

| Operation | Đối tượng không tồn tại/không khớp | Đối tượng có nhưng bị từ chối |
| --- | --- | --- |
| `findStatic` | `NoSuchMethodException` | `IllegalAccessException` |
| `findVirtual` | `NoSuchMethodException` | `IllegalAccessException` |
| `findConstructor` | `NoSuchMethodException` | `IllegalAccessException` |
| `findGetter`/`findSetter` | `NoSuchFieldException` | `IllegalAccessException` |
| `findVarHandle` | `NoSuchFieldException` | `IllegalAccessException` |
| `privateLookupIn` | Target object/class không phải thứ cần lookup; lỗi argument theo API | `IllegalAccessException` khi không đủ quyền |
| `invokeExact` | Đã có handle, nhưng call-site descriptor không đúng | `WrongMethodTypeException` |
| Invocation target tự ném lỗi | Không phải lỗi lookup | Lỗi target có thể truyền ra trực tiếp dưới `Throwable` |

**Cần phân biệt:** không phải mọi `IllegalAccessException` đều có nghĩa member là `private`. Class không accessible, module không exported, thiếu package mode, protected receiver restrictions hoặc lookup mode bị drop cũng có thể khiến lookup thất bại.

### 11.1. Chương trình: lỗi tên, lỗi chữ ký và lỗi quyền

Tạo `LookupFailuresDemo.java`:

```java
import java.lang.invoke.*;
public class LookupFailuresDemo {
  private static String secret() { return "secret"; }
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup pub = MethodHandles.publicLookup();
    boolean inaccessible = false, missing = false, wrongSignature = false;
    try {
      pub.findStatic(LookupFailuresDemo.class, "secret", MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { inaccessible = true; }
    try {
      pub.findStatic(Math.class, "thisMethodDoesNotExist",
          MethodType.methodType(int.class, int.class, int.class));
    } catch (NoSuchMethodException ex) { missing = true; }
    try {
      pub.findStatic(Math.class, "max", MethodType.methodType(String.class, int.class, int.class));
    } catch (NoSuchMethodException ex) { wrongSignature = true; }
    MethodHandle max = pub.findStatic(Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));
    System.out.println("denied-member-illegal-access=" + inaccessible);
    System.out.println("missing-name-no-such-method=" + missing);
    System.out.println("wrong-type-no-such-method=" + wrongSignature);
    System.out.println("known-method-result=" + (int)max.invokeExact(4, 9));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LookupFailuresDemo.java
java LookupFailuresDemo
```

**stdout đã kiểm thử:**

```text
denied-member-illegal-access=true
missing-name-no-such-method=true
wrong-type-no-such-method=true
known-method-result=9
```

**Tình huống thứ ba:** tên method `Math.max` có tồn tại nhưng không có overload **trả String với hai int**. `findStatic` cần match `MethodType` chính xác theo method resolution; JVM không coi “String cũng có thể chứa chữ số” là match.

### 11.2. Xử lý lỗi đúng nơi

- Với tên/signature đến từ cấu hình: kiểm tra contract phiên bản, log class + method signature an toàn.
- Với `IllegalAccessException`: xem lookup class, modes, visibility, module exports/opens, không tự động bật JVM `--add-opens` cho mọi package.
- Với `NoSuchMethodException`: xác nhận return/parameter types và static vs virtual.
- Với `NoSuchFieldException`: xác nhận tên/kiểu field; Java không tự chuyển static field thành instance field.
- Với `WrongMethodTypeException` khi invoke: kiểm tra method handle `type()` và call-site descriptor.
- Không bắt rộng `Throwable` rồi trả `null`, che mất lỗi của ứng dụng.

## 12. invokeExact và invoke: cùng handle, mức thích ứng kiểu khác nhau

`MethodHandle.invokeExact` yêu cầu **call-site descriptor** khớp chính xác `MethodHandle.type()`, gồm cả kiểu trả về. Nó không tự widening/narrowing hoặc convert boxing như người lập trình tưởng.

`MethodHandle.invoke` có thể dùng các conversions tương thích `asType`, nhưng **không có nghĩa mọi kiểu đều chuyển đổi được**. Nếu conversion không tồn tại hoặc runtime cast thất bại, vẫn có ngoại lệ.

### 12.1. Chương trình: mismatch khi invokeExact

Tạo `InvokeTypeDemo.java`:

```java
import java.lang.invoke.*;
public class InvokeTypeDemo {
  public static void main(String[] args) throws Throwable {
    MethodHandle max = MethodHandles.publicLookup().findStatic(Math.class, "max",
        MethodType.methodType(int.class, int.class, int.class));
    int valid = (int) max.invokeExact(5, 9);
    boolean wrongType = false;
    try {
      int unused = (int) max.invokeExact(5L, 9L);
      System.out.println("unexpected=" + unused);
    } catch (WrongMethodTypeException ex) { wrongType = true; }
    MethodHandle upper = MethodHandles.publicLookup().findVirtual(String.class, "toUpperCase",
        MethodType.methodType(String.class));
    String adapted = (String) upper.invoke((Object) "hello");
    System.out.println("exact-result=" + valid);
    System.out.println("exact-long-args-rejected=" + wrongType);
    System.out.println("invoke-adapts-object=" + adapted);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeTypeDemo.java
java InvokeTypeDemo
```

**stdout đã kiểm thử:**

```text
exact-result=9
exact-long-args-rejected=true
invoke-adapts-object=HELLO
```

**Tại sao khác?** `max` mang type `(int,int)int`. Callsite với hai `long` không khớp dù cả hai đều là kiểu số nguyên. `upper` mang type `(String)String` và `invoke((Object)"hello")` cho phép runtime chuyển tham số `Object` sang `String` hợp lệ trong trường hợp này.

**Không dùng `invokeWithArguments` cho mọi call trong hot path**: method này thuận tiện khi dynamic arguments, nhưng conversions/boxing và varargs overhead có thể đáng kể. Chọn dạng invocation theo đúng yêu cầu runtime và performance benchmark thực tế.

### 12.2. Cast kết quả là một phần của callsite signature

Với `invokeExact`, biểu thức:

```java
int result = (int) max.invokeExact(5, 9);
```

có call-site return type `int`. Nếu vô ý dùng return type `Object` hoặc bỏ qua return với method non-void, có thể tạo `WrongMethodTypeException` ngay cả khi arguments đúng. Tại biên code có type information dynamic, inspect `handle.type()` trước.

## 13. findSpecial và protected access

`Lookup.findSpecial(refc,name,type,specialCaller)` tạo handle tương đương lời gọi kiểu `invokespecial`, bỏ qua một số quy tắc virtual overriding để gọi trực tiếp method trên superclass/interface theo context được phép.

**Không phải “hack gọi superclass private method từ bất kỳ class nào”.** JavaDoc yêu cầu `specialCaller` phải phù hợp với lookup class và private capability; các JVM verification/access checks vẫn áp dụng.

### 13.1. Chương trình: virtual dispatch vs gọi implementation ở Parent

Tạo `FindSpecialDemo.java`:

```java
import java.lang.invoke.*;
public class FindSpecialDemo {
  static class Parent {
    public String hello() { return "parent"; }
  }
  static class Child extends Parent {
    @Override public String hello() { return "child"; }
    String callParent() throws Throwable {
      MethodHandles.Lookup fromChild = MethodHandles.lookup();
      MethodHandle base = fromChild.findSpecial(Parent.class, "hello",
          MethodType.methodType(String.class), Child.class);
      return (String) base.invokeExact(this);
    }
  }
  public static void main(String[] args) throws Throwable {
    Child child = new Child();
    System.out.println("virtual-dispatch=" + child.hello());
    System.out.println("special-parent=" + child.callParent());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all FindSpecialDemo.java
java FindSpecialDemo
```

**stdout đã kiểm thử:**

```text
virtual-dispatch=child
special-parent=parent
```

`child.hello()` sử dụng virtual dispatch tới override của Child. Ngược lại, `findSpecial(Parent.class,...,Child.class)` được gọi **từ trong Child** với một Lookup có ngữ cảnh Child; handle tạo ra gọi implementation của Parent như một lời gọi `super.hello()`.

**Nếu bạn chuyển `MethodHandles.lookup()` ra một helper class không có quyền tương ứng**, `specialCaller`/access check có thể thất bại. Đừng đặt nó ở một utility toàn cục rồi nghĩ sẽ giữ semantics của `super` cho mọi class.

### 13.2. Protected across packages: thêm ràng buộc receiver

Với member `protected` ở package khác, lookup class thường cần là subclass hợp lệ; JavaDoc còn quy định type của receiver trong handle có thể được **thu hẹp** về lookup subclass hoặc subtype. Vì vậy một handle có thể không chấp nhận receiver là mọi instance của superclass, dù method declaration nằm ở superclass đó.

**Không dùng `findVirtual(Base.class,"protectedMethod",...)` với arbitrary Base instance để vượt qua protected access.** Kiểu receiver của handle sẽ phản ánh các ràng buộc JVM trong ngữ cảnh lookup.

## 14. VarHandle và quyền truy cập field

Java 9 bổ sung `VarHandle`, phù hợp cho các thao tác đọc/ghi field và một số atomic operations. `Lookup.findVarHandle` cũng áp dụng **kiểm tra class/member access** khi tạo VarHandle.

`findVarHandle(Target.class,"field",int.class)` khác `findGetter` ở tập operations mà VarHandle hỗ trợ: ví dụ `getVolatile`, `setVolatile`, `compareAndSet` khi field/mode/variable type phù hợp.

### 14.1. Chương trình: private volatile field và CAS

Tạo `LookupVarHandleDemo.java`:

```java
import java.lang.invoke.*;
public class LookupVarHandleDemo {
  private static final class Counter {
    private volatile int value = 5;
  }
  public static void main(String[] args) throws Exception {
    MethodHandles.Lookup full = MethodHandles.lookup();
    VarHandle field = full.findVarHandle(Counter.class, "value", int.class);
    Counter counter = new Counter();
    int before = (int) field.getVolatile(counter);
    boolean changed = field.compareAndSet(counter, 5, 9);
    int after = (int) field.getVolatile(counter);
    boolean publicDenied = false;
    try {
      MethodHandles.publicLookup().findVarHandle(Counter.class, "value", int.class);
    } catch (IllegalAccessException ex) { publicDenied = true; }
    System.out.println("initial=" + before);
    System.out.println("cas-success=" + changed);
    System.out.println("after=" + after);
    System.out.println("public-access-denied=" + publicDenied);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LookupVarHandleDemo.java
java LookupVarHandleDemo
```

**stdout đã kiểm thử:**

```text
initial=5
cas-success=true
after=9
public-access-denied=true
```

Đây là private field của nested class cùng nest nên lookup gốc có quyền tạo `VarHandle`. Public lookup không có đủ quyền để truy cập cả private nested class và member. `compareAndSet` kiểm tra/sửa atomically theo variable access semantics; **không** biến mọi object chứa field này thành thread-safe cho các operations nghiệp vụ không đồng bộ khác.

### 14.2. Field type là một phần của lookup

Nếu field khai báo `int`, gọi `findVarHandle(Target.class,"value",long.class)` không phải cách yêu cầu JVM tự chuyển int sang long. Việc lookup variable cần đúng name/type; lỗi khác kiểu thường được báo như không tìm thấy field đúng signature.

### 14.3. Final fields

Không thể tự tạo một setter hợp pháp tới mọi `final` field chỉ vì có private lookup. Java/JVM bảo vệ finality; `findSetter` thường từ chối final field và VarHandle setter trên read-only variable có thể báo unsupported access mode. Đừng dựa vào unsafe mutation of final fields để xây serialization/runtime system mới.

## 15. JPMS: export cho public API, opens cho deep reflection

Đây là phần cực kỳ quan trọng trong Java hiện đại.

### 15.1. Hai câu hỏi khác nhau

- **`exports package`:** cho phép module khác truy cập **public types/members** trong package theo rules của JPMS. Đây là điều kiện dành cho Java code và public method-handle lookup.
- **`opens package`:** cho phép **deep reflection** trên non-public members của package từ những modules được chỉ định, trong phạm vi module readability/lookup permissions tương ứng. Đây là điều kiện quan trọng cho cross-module `privateLookupIn`.

**`exports` không tự tương đương `opens`.** Một library có public API vẫn có thể giữ encapsulation chặt cho private implementation.

### 15.2. Ví dụ module-info.java có chủ ý mở đúng package

Module thư viện:

```java
module library.core {
    exports com.example.api;
    opens com.example.internal to client.app;
}
```

Module ứng dụng:

```java
module client.app {
    requires library.core;
}
```

**Đây là hai snippets thuộc hai file `module-info.java` khác nhau**, không phải một chương trình Java standalone ghép chung. `client.app` có thể truy cập public API từ `com.example.api`. Để có deep lookup của một class tại `com.example.internal`, ứng dụng còn cần lấy `Class<?>` của target theo cơ chế hợp lệ, có caller lookup với đầy đủ quyền và tuân theo `opens` đã chỉ định.

Ví dụ pseudocode cho framework **được owner cho phép**:

```java
Class<?> target = Class.forName("com.example.internal.Widget");
MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup deep = MethodHandles.privateLookupIn(target, caller);
// Sau đây mới tìm member private với tên/signature đúng.
```

Đây là **snippet** giả định module, class và dependency hợp lệ, không phải một shortcut tự động hoạt động chỉ vì `Class.forName` load được class. Cross-module `privateLookupIn` cần **module reads + opens + caller modes**.

### 15.3. JDK modules không mở private APIs tự do

`java.base` export các public Java APIs như `java.lang.String`, nhưng **không mở toàn bộ `java.lang`** cho mọi module chạy trên classpath theo mặc định. Vì vậy `publicLookup()` có thể tìm `String.isEmpty()`, trong khi `privateLookupIn(String.class,MethodHandles.lookup())` có thể bị từ chối nếu không có explicit opening.

### 15.4. Chương trình runnable: export không đồng nghĩa open

Tạo `JpmsOpensDemo.java`:

```java
import java.lang.invoke.*;
public class JpmsOpensDemo {
  public static void main(String[] args) throws Throwable {
    Module javaBase = String.class.getModule();
    Module thisModule = JpmsOpensDemo.class.getModule();
    boolean namedBase = javaBase.isNamed();
    boolean callerUnnamed = !thisModule.isNamed();
    boolean exported = javaBase.isExported("java.lang", thisModule);
    boolean opened = javaBase.isOpen("java.lang", thisModule);
    boolean privateDenied = false;
    try {
      MethodHandles.privateLookupIn(String.class, MethodHandles.lookup());
    } catch (IllegalAccessException ex) { privateDenied = true; }
    MethodHandle isEmpty = MethodHandles.publicLookup().findVirtual(String.class, "isEmpty",
        MethodType.methodType(boolean.class));
    boolean empty = (boolean) isEmpty.invokeExact("");
    System.out.println("java-base-named=" + namedBase);
    System.out.println("caller-unnamed=" + callerUnnamed);
    System.out.println("java-lang-exported=" + exported);
    System.out.println("java-lang-not-open=" + !opened);
    System.out.println("deep-lookup-denied=" + privateDenied);
    System.out.println("public-string-method=" + empty);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all JpmsOpensDemo.java
java JpmsOpensDemo
```

**stdout đã kiểm thử trên mặc định classpath, không dùng `--add-opens`:**

```text
java-base-named=true
caller-unnamed=true
java-lang-exported=true
java-lang-not-open=true
deep-lookup-denied=true
public-string-method=true
```

**Lưu ý quan trọng:** Output về `java-lang-not-open` và `deep-lookup-denied` được kiểm chứng trong **cấu hình không có flags mở module**. Nếu một ứng dụng có chủ ý chạy với `--add-opens java.base/java.lang=ALL-UNNAMED`, các câu trả lời liên quan tới openness có thể khác. Bài không khuyến nghị bật flag đó làm giải pháp mặc định.

### 15.5. Tại sao tránh --add-opens tràn lan?

Mở các package nội bộ chỉ để tránh sửa code gọi private members có thể:

- Làm tăng bề mặt truy cập của các libraries/plugins khác trong cùng module target audience.
- Khiến chương trình phụ thuộc implementation details không ổn định.
- Che giấu việc thiếu hợp đồng extension point rõ ràng.
- Tạo lỗi khi deploy sang môi trường khác thiếu flags.
- Vi phạm nguyên tắc least privilege.

**Ưu tiên public API và module `opens ... to specific.module;`** khi thật sự cần deep reflection trong một architecture có chủ đích. Không phải package nào của thư viện cũng cần opens.

## 16. Lookup như một capability: bảo vệ khỏi rò rỉ quyền

Một lookup gốc được tạo **trong class có quyền cao** có thể được truyền sang code khác. JavaDoc mô tả việc chia sẻ lookup tương đương giao quyền **tạo method handles** theo khả năng của lookup class gốc. Đây là lý do cần cẩn trọng trong plugin systems hoặc metadata frameworks.

### 16.1. Chương trình: lộ privileged Lookup cho phép lấy private handle

Tạo `LookupCapabilityDemo.java`:

```java
import java.lang.invoke.*;
public class LookupCapabilityDemo {
  private static final class Vault {
    private static String secret() { return "sensitive"; }
    static MethodHandles.Lookup privileged() { return MethodHandles.lookup(); }
  }
  public static void main(String[] args) throws Throwable {
    MethodHandles.Lookup leaked = Vault.privileged();
    MethodHandle secret = leaked.findStatic(Vault.class, "secret",
        MethodType.methodType(String.class));
    String output = (String) secret.invokeExact();
    MethodHandles.Lookup reduced = leaked.dropLookupMode(MethodHandles.Lookup.PRIVATE);
    boolean prevented = false;
    try {
      reduced.findStatic(Vault.class, "secret", MethodType.methodType(String.class));
    } catch (IllegalAccessException ex) { prevented = true; }
    System.out.println("privileged-lookup-exposes-private=" + output.equals("sensitive"));
    System.out.println("restricted-lookup-blocks-new-private=" + prevented);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all LookupCapabilityDemo.java
java LookupCapabilityDemo
```

**stdout đã kiểm thử:**

```text
privileged-lookup-exposes-private=true
restricted-lookup-blocks-new-private=true
```

Trong ví dụ, `Vault` cố ý trao Lookup có quyền private cho code khác cùng JVM. Code nhận được dùng lookup để tạo method handle tới private method. Việc giảm mode trên **một lookup mới** chặn private lookup mới, nhưng không thu hồi handle đã tạo từ lookup có quyền.

**Thông điệp security:** không expose `MethodHandles.lookup()` qua public API cho dữ liệu nội bộ nếu không có một trust boundary rõ ràng. Truyền **specific handles** tới những operations đã kiểm soát, hoặc chỉ public/restricted lookup; validate caller/authorization ở tầng ứng dụng.

### 16.2. Những bảo vệ nên có trong frameworks

1. **Capability minimization:** cung cấp đúng method handles cần thiết thay vì full privileged Lookup.
2. **Trust boundary:** chỉ nội bộ được nhận private Lookup.
3. **Module boundaries:** export public API, opens deep reflection đúng modules cần thiết.
4. **Validation:** tên class/member và MethodType từ metadata phải được kiểm tra.
5. **No secret leaks:** không log method handles dẫn tới secrets hoặc phản chiếu private values.
6. **Operation authorization:** đừng coi quyền truy cập JVM là quyền user cuối; target method vẫn cần kiểm tra business permissions.
7. **Lifecycle:** handle không tự bị revoke khi bạn drop một Lookup khác.
8. **Compatibility:** private members không phải stable extension contracts.
9. **Error classification:** tách missing member, access denied, wrong method type.
10. **Test:** có tests xác minh cả cases được phép và bị từ chối trong đúng modules của production.

## 17. Những nhầm lẫn trong API

### 17.1. findStatic vs findVirtual

- `findStatic` tạo handle cho static method, không nhận receiver.
- `findVirtual` tạo handle cho instance method, có receiver ở **đầu handle.type()**.
- Cùng tên/signature nhưng dùng nhầm factory có thể khiến lookup bị từ chối, thường qua `IllegalAccessException` hoặc lỗi resolution tùy trường hợp.

**Ví dụ:** `Math.max(int,int)` là static, nên `findStatic(Math.class,"max",methodType(int,int,int))` phù hợp. `String.toUpperCase()` là instance, nên `findVirtual(String.class,"toUpperCase",methodType(String))` phù hợp.

### 17.2. findConstructor

`findConstructor(Class<?> refc,MethodType type)` cần MethodType có return type **void**, trong khi handle kết quả trả target object. Một constructor private chỉ được tìm khi Lookup có quyền private trong context thích hợp.

### 17.3. findGetter/findSetter

Hai factory kiểm tra field name/type và static-vs-instance. `findGetter` cho instance field khác `findStaticGetter` cho static field. `findSetter` bị từ chối đối với nhiều trường hợp field `final`, kể cả khi bạn biết tên field.

### 17.4. findVarHandle

`VarHandle` cho phép truy cập variables với multiple memory/atomic access modes; nó có type/coordinate requirements riêng, không cùng chữ ký invocation như `MethodHandle`. Việc tạo VarHandle vẫn chịu quy tắc Java access.

### 17.5. unreflect

`Lookup.unreflect(Method)` tạo handle từ một `java.lang.reflect.Method`. Đây không phải quyền truy cập tự do: các access checks theo lookup/reflection accessible flag vẫn áp dụng. Khi một non-public Method đã được mở quyền một cách hợp lệ, JavaDoc có những nuance riêng; đừng thay vì hiểu chúng mà dùng setAccessible everywhere.

### 17.6. caller-sensitive methods

Một số APIs dựa vào identity của caller, ví dụ `Class.forName` trong các trường hợp thích hợp. Lookup có mode `ORIGINAL` và access privileges đúng mới có thể tạo handles tới caller-sensitive methods. Public/reduced Lookup không tự có quyền làm điều đó. Đừng tưởng một transformed lookup có quyền giống factory gốc khi đã mất `ORIGINAL`.

## 18. Quy trình xử lý IllegalAccessException khi dùng MethodHandles.Lookup

Khi `findVirtual`/`findStatic`/`findGetter` thất bại vì access:

```text
IllegalAccessException
         |
         v
(1) Class chứa member có accessible từ lookup class?
         |
         +-- No -> public class? package exports? module reads?
         |
         +-- Yes
                |
                v
(2) Member modifier là gì? public/private/protected/package?
                |
                v
(3) lookup.lookupClass() + lookupModes() có quyền thích hợp?
                |
                v
(4) Cùng nest/package/runtime module hay qua module?
                |
                v
(5) Nếu deep reflection: opens target package tới caller module?
                |
                v
(6) Nếu dùng in/drop: lookup đã tự bị hạn chế quyền chưa?
                |
                v
(7) Nếu handle đã tạo: callsite MethodType/invokeExact có khớp không?
                |
                v
Dùng public API, đúng Lookup, hoặc thiết kế module openness có chủ ý
```

**Không sửa theo kiểu thêm `--add-opens` cho toàn bộ packages khi chưa phân loại lỗi.** Có thể nguyên nhân chỉ là bạn dùng sai `findStatic` thay vì `findVirtual`, sai return type, sai receiver, hoặc member thật sự không tồn tại.

### 18.1. Kiểm tra code đã có handle thì sao?

Sau khi handle đã tạo, `WrongMethodTypeException` lúc gọi là **vấn đề kiểu callsite**, không phải `IllegalAccessException` của lookup. Sửa `MethodType` và cách cast kết quả, hoặc dùng `asType`/`invoke` theo conversion contract đã tài liệu hóa.

### 18.2. Kiểm tra NoSuchMethodException thì sao?

Đọc đầy đủ return/parameter types; method có thể overloaded, bridge methods hoặc generic erasure. `MethodType` sử dụng **runtime classes** chứ không phải tên source generic types. Với Java generics, erased type có thể khác trực giác từ source code.

Không tự mặc định tên method là unique; overloads khác tham số phải chọn đúng signature.

## 19. Những rủi ro production khi tạo handles động

### 19.1. Lookup không thay thế authorization nghiệp vụ

Một handle cho `Account.withdraw(...)` có thể gọi được theo Java access rules, nhưng method vẫn phải kiểm tra quyền của user thực tế, giới hạn giao dịch và audit. Java access modifiers chỉ là một lớp encapsulation trong JVM.

### 19.2. Dynamic names có thể bị lợi dụng

Nếu framework nhận từ người dùng tên class/method rồi tự tạo handles theo privileged Lookup, một attacker có thể yêu cầu truy cập member không nằm trong business API. **Allowlist class/member/method signatures**, giảm capability của lookup và không để user gửi arbitrary `privateLookupIn` requests.

### 19.3. Không cho plug-in nhận original Lookup của host

`Lookup` là capability. Nếu plug-in chỉ cần gọi một public method, cung cấp `publicLookup` hoặc một handle cụ thể đã được host phê duyệt; không trả `MethodHandles.lookup()` trong host privileged class.

### 19.4. Module access khác class loader isolation

JPMS và Java access control không phải một sandbox bảo đảm an toàn trước arbitrary untrusted bytecode trong cùng process. Nếu threat model gồm code độc hại, cần process isolation, OS permissions, runtime constraints và thiết kế bảo mật phù hợp, không chỉ dựa vào `Lookup`.

### 19.5. Đừng dùng undocumented JDK internals

Các cách truy cập sâu `jdk.internal.*` hoặc `sun.misc.*` để tránh `IllegalAccessException` thường phụ thuộc implementation details và có thể không hoạt động ở JDK mới. Theo Special Note, bài tập trung vào public APIs của Java 17/21 và explicit `opens` khi hợp lệ; không khuyến nghị hack encapsulation.

## 20. Hiệu năng và caching

### 20.1. Tạo handle thường không nên lặp vô ích

`Lookup` có thể perform class/member resolution và access checking khi tạo handle. Trong runtime framework, một handle tới method được sử dụng lặp đi lặp lại thường nên **cache theo Class + MethodType + operation kind + classloader/module context**.

Tuy nhiên caching sai có thể gây:

- Giữ classloader sống lâu không cần (leak trong app server/plugin reload).
- Truyền nhầm handle của classloader khác dù class name giống nhau.
- Lưu sensitive MethodHandle vượt thời gian cần thiết.
- Không phân biệt lookup có quyền private và public.
- Bỏ qua module openness/privilege boundaries.
- Cache lỗi lookup cũ sau khi module/classloading context thay đổi.

### 20.2. Không benchmark bằng một lần System.nanoTime

Hiệu năng `invokeExact` có thể tốt khi JVM tối ưu callsite ổn định, nhưng không có bảo đảm luôn nhanh hơn direct Java calls hoặc reflection với mọi workload.

Benchmark chuyên nghiệp (ví dụ JMH):

1. Khởi tạo handle ngoài measured hot loop nếu đo invocation.
2. Tách cost lookup creation vs invocation.
3. Warm up JIT và chạy nhiều forks/iterations.
4. Dùng đúng MethodType và avoid boxing không cần thiết.
5. So cùng operation semantics giữa direct call/reflection/method handle.
6. Đảm bảo consumer dùng kết quả, tránh compiler dead-code elimination.
7. Benchmark trong runtime/module/classloader thực tế.
8. Không hy sinh access validation để tăng throughput.
9. Đo cả memory/caching costs.
10. Không khẳng định kết quả cho mọi JVM architecture.

## 21. So sánh Reflection, MethodHandle và VarHandle

| Đặc điểm | Core Reflection | MethodHandle + Lookup | VarHandle + Lookup |
| --- | --- | --- | --- |
| API | `java.lang.reflect.Method`/`Field`/`Constructor` | `java.lang.invoke.MethodHandle` | `java.lang.invoke.VarHandle` |
| Kiểm tra quyền | Reflection checks tại invocation hoặc accessible override theo rules | Lookup kiểm tra khi tạo handle | Lookup kiểm tra khi tạo VarHandle |
| Kiểu khi gọi | `Method.invoke` dùng Object/varargs và conversions | `invokeExact`/`invoke` có MethodType và callsite signatures | Coordinates + access modes |
| Phương thức ảo | Reflection invokes method tùy receiver theo rules | `findVirtual`, `findSpecial` | Không là factory cho method calls |
| Truy cập private qua modules | `opens`/accessible rules | `privateLookupIn` + module rules | `findVarHandle` với lookup phù hợp |
| Mutation atomic | Không tự có CAS API phổ thông | Có thể gọi method cung cấp CAS | `compareAndSet` và access modes được hỗ trợ |
| Dùng khi | Framework metadata/annotations/inspection | Dynamic method invocation, linkage, adapters | Variable access semantics, atomics, memory ordering |

**Không đánh giá công cụ nào “mạnh hơn” chỉ bằng việc nó có thể gọi private method.** Mục tiêu là thiết kế đúng contract, access control và performance/memory trade-offs của ứng dụng.

## 22. Các lỗi thường gặp và cách sửa

| Anti-pattern | Sai ở đâu | Cách sửa |
| --- | --- | --- |
| `publicLookup().findStatic` gọi private method | Public lookup không có private quyền | API public hoặc lookup có quyền được phép |
| Method public nhưng class package-private | Class không accessible | Thiết kế public class/API, hoặc dùng lookup hợp lệ |
| `lookup.in(Target.class)` để “nâng quyền” | in chỉ chuyển context, thường giảm quyền | `privateLookupIn` nếu module cho phép |
| `privateLookupIn` trên module chưa opens | JPMS chặn deep reflection | Owner cấu hình `opens ... to ...` có chủ ý |
| `MethodHandles.lookup()` ở utility class rồi tưởng lấy quyền caller | lookupClass là nơi gọi thực tế | Tạo lookup ở đúng class/trust boundary |
| Đưa Lookup private cho plug-in không tin cậy | Rò capability | Public/restricted lookup hoặc specific safe handle |
| `dropLookupMode` rồi nghĩ mọi handles cũ bị thu hồi | Existing handles không bị revoke | Quản lý capability lifecycle/auth guard |
| Chỉ kiểm tra `lookupModes() & PRIVATE` | Chưa xét nest/package/module/class visibility | Kiểm tra toàn bộ access rules |
| Tạo `findVirtual` với type gồm receiver | `MethodType` của findVirtual **không** chứa receiver | Chỉ khai báo tham số của method |
| findConstructor type trả object type | Input `MethodType` constructor phải trả void | `methodType(void.class,...)` |
| Tạo `findStatic` cho instance method | Sai operation kind | `findVirtual` |
| Tạo `findGetter` cho static field | Sai operation kind | `findStaticGetter` |
| Sai return type trong MethodType | Lookup không match method | Dùng đúng signature runtime |
| `invokeExact` nhận long thay int | Callsite không exact | Sửa kiểu/cast hoặc chủ ý adapt |
| Bắt `NoSuchMethodException` cho mọi access failure | Bỏ qua `IllegalAccessException` | Phân loại rõ failure |
| Nghĩ `invoke` luôn convert được mọi Object | Không phải mọi adaptation hợp lệ | Đọc `MethodHandle.asType` rules |
| Dùng `findSpecial` với arbitrary specialCaller | Cần lookup/private context đúng | Tạo lookup trong class hợp lệ |
| Protected cross-package với arbitrary superclass receiver | JVM receiver constraint | Receiver phải phù hợp lookup subclass |
| Dùng setter trên final field | Finality là access restriction | Thiết kế immutable/constructor |
| Khẳng định `exports` là `opens` | Public API khác deep reflection | Modules declares phù hợp |
| Dùng `--add-opens` đại trà | Tăng quyền và rủi ro compatibility | Public API hoặc qualified opens |
| Dùng JDK internal APIs không được hỗ trợ | Dễ vỡ ở JDK mới | Java 17+ public APIs |
| Cache handle bằng tên class dạng String duy nhất | Classloader/module collision | Key theo Class identity/signature/context |
| Chỉ dựa vào Java private để chặn request user | Không phải business auth | Authorization ở tầng nghiệp vụ |
| Log private method arguments và secrets | Lộ dữ liệu | Redact logs và quản lý quyền |
| Dynamic privateLookupIn theo user input | Bề mặt tấn công lớn | Strict allowlist/deny-by-default |
| Assert module open trên môi trường có --add-opens | Flags làm khác kết quả | Test đúng JVM configuration |

## 23. Checklist code review

1. Mục đích có cần MethodHandle động, hay direct Java call đơn giản hơn?
2. Lookup được tạo từ **đúng caller class** chưa?
3. `lookupClass()` và `lookupModes()` đã được hiểu đúng chưa?
4. Code có phân biệt `publicLookup()` với `lookup()` không?
5. Có hiểu `UNCONDITIONAL` khác `PUBLIC` mode không?
6. Có kiểm tra visibility của **class chứa member** và của member không?
7. Member đang ở cùng nest, package hoặc module nào?
8. Nếu target ở module khác, module reads/exports/opens đã đúng chưa?
9. Có tránh dùng `Lookup.in` như phép nâng private access không?
10. `privateLookupIn` chỉ được gọi khi caller có `PRIVATE` + `MODULE` và module cho phép chứ?
11. Có biết cross-module lookup sau teleport có thể mất quyền không?
12. Có tránh public API lộ full privileged Lookup không?
13. Có giảm quyền bằng `dropLookupMode` khi chuyển cho code ít tin cậy không?
14. Có biết handle đã tạo **không bị revoke** khi tạo reduced lookup sau đó không?
15. Có đúng `MethodType` của static/virtual/constructor không?
16. Có tính receiver vào `MethodHandle.type()` nhưng **không** tính trong input `findVirtual` không?
17. Có xử lý field static-vs-instance đúng factory không?
18. Có biết final fields không luôn có writable setter không?
19. Có phân biệt `NoSuchMethodException`, `NoSuchFieldException` và `IllegalAccessException` không?
20. Có xử lý `WrongMethodTypeException` khi `invokeExact` callsite không khớp không?
21. Có không bắt rộng Throwable rồi che lỗi target không?
22. Nếu dùng `findSpecial`, caller context có hợp lệ không?
23. Nếu protected ở khác package, receiver có đúng subclass restrictions không?
24. Nếu dùng VarHandle, access modes và coordinate types có đúng không?
25. Có không dùng reflection accessible override để bypass modules vô tội vạ không?
26. Có tránh phụ thuộc JDK internal APIs đã bị encapsulate không?
27. Có dùng Java 17+ APIs hiện hành, không lỗi thời, theo Special Note không?
28. Có unit tests cho cả allowed và denied lookups không?
29. Có chạy tests trong đúng module/classloader/JVM flags của production không?
30. Có phân tách security boundary ứng dụng khỏi JVM member access không?
31. Có tránh caches làm leak classloaders/privileged handles không?
32. Có code review mọi đường phơi lộ Lookup hoặc private MethodHandle không?

## 24. Bài tập thực hành

**Bài 1 — Lookup identity.** Chạy `LookupIdentityDemo`, tạo một nested class nữa với static method gọi `MethodHandles.lookup()` và so `lookupClass()`. Điều gì quyết định class ghi lại trong lookup?

**Bài 2 — Mode flags.** Với lookup() và publicLookup(), in từng bit `PUBLIC`, `PRIVATE`, `PACKAGE`, `MODULE`, `UNCONDITIONAL`. Không dùng so sánh numeric equality để đoán mức quyền.

**Bài 3 — Public operations.** Chạy `PublicMembersDemo`; thay `Math.max` bằng `Math.min` với đúng MethodType và verify stdout.

**Bài 4 — Virtual receiver.** Tạo handle tới `String.substring(int)` bằng findVirtual và xem `handle.type()`. Vì sao có `String` receiver trong type nhưng không đưa vào MethodType lookup?

**Bài 5 — Constructor.** Dùng `findConstructor` tạo `StringBuilder("hello")` và append. Hãy giải thích vì sao input MethodType trả `void`.

**Bài 6 — Nestmates.** Chạy `NestmatePrivateDemo`, chuyển Vault thành một unrelated top-level class. Điều gì thay đổi về quyền private?

**Bài 7 — privateLookupIn.** Chạy `PrivateLookupInDemo` và giải thích vì sao caller lookup gốc không thấy private member của unrelated top-level class.

**Bài 8 — Public denial.** Chạy `PublicLookupDenialDemo`, đổi package-private class thành public top-level class trong file riêng rồi so behavior. Không chuyển private method thành public chỉ để qua test mà không xét API contract.

**Bài 9 — in vs privateLookupIn.** Chạy `LookupInRestrictionDemo`, so mode của original/moved và kiểm `privateLookupIn` theo các điều kiện module.

**Bài 10 — Drop rights.** Chạy `DropModesDemo` và thử drop `PACKAGE`, `MODULE`, `PUBLIC`. Quan sát hiệu ứng cascade trên bits.

**Bài 11 — No revocation.** Giải thích vì sao handle đã tạo trước `dropLookupMode` vẫn callable. Thiết kế một API có revocation/authorization guard nếu business cần.

**Bài 12 — Failure taxonomy.** Chạy `LookupFailuresDemo`, bổ sung findGetter không tồn tại để catch `NoSuchFieldException` riêng.

**Bài 13 — invokeExact.** Chạy `InvokeTypeDemo`, thử thay kiểu return bằng `Object` và xác định `WrongMethodTypeException`. So với `invoke`.

**Bài 14 — findSpecial.** Chạy `FindSpecialDemo`, chuyển MethodHandles.lookup() ra helper class khác và xem kiểm tra access thất bại ở đâu; không thay đổi code production để bypass rules.

**Bài 15 — VarHandle.** Chạy `LookupVarHandleDemo`, thêm `getAndAdd` với field phù hợp; kiểm tra CAS và memory access semantics.

**Bài 16 — Module export/open.** Chạy `JpmsOpensDemo` mặc định. Viết hai module-info.java snippets với `exports` và qualified `opens`, giải thích deep lookup khác public lookup như thế nào.

**Bài 17 — Secure capability sharing.** Chạy `LookupCapabilityDemo`, thay privileged Lookup bằng publicLookup và giải thích vì sao private access bị chặn.

**Bài 18 — Lookup cache.** Thiết kế cache key theo `Class<?>` identity, method name, MethodType, operation kind, lookup authority context; nêu classloader leak/privilege leak risks.

**Bài 19 — Framework architecture.** Thiết kế một plugin host chỉ cho phép plugins gọi tập public methods được allowlist; không trả Lookup gốc hoặc arbitrary private handles.

**Bài 20 — Review modules.** Tạo một module library có public API exported và private implementation không opened. Viết integration test xác nhận public lookup PASS, deep lookup FAIL; sau đó thêm qualified opens cho test module và so behavior.

## 25. Tóm tắt

- `MethodHandles.Lookup` là **factory giữ ngữ cảnh access checking**, còn `MethodHandle` là một operation có kiểu đã được cấp quyền ở thời điểm tạo.
- `MethodHandles.lookup()` là **caller-sensitive**: lookup class là nơi gọi thực sự, không phải caller tương lai của helper.
- `publicLookup()` mang quyền thấp, truy cập public types/members của packages exported theo contract; không thể gọi mọi private member.
- `findStatic`, `findVirtual`, `findConstructor`, `findGetter`/`findSetter` và `findVarHandle` đều phụ thuộc lookup authority.
- `Lookup.in(target)` **không nâng quyền**; có thể giảm private/package/module access.
- `privateLookupIn(target,lookup)` có thể cấp private lookup khi **caller modes, module readability và opens** cho phép; không bypass JPMS.
- `dropLookupMode` tạo lookup giảm quyền, **không thu hồi method handles đã phát hành**.
- `IllegalAccessException` báo access fail; `NoSuchMethodException`/`NoSuchFieldException` báo không tìm được member đúng signature; `WrongMethodTypeException` thường xuất hiện lúc invoke sai callsite descriptor.
- `findSpecial` yêu cầu đúng calling class và private authority; protected cross-package còn ràng buộc receiver.
- Java 17+ có `ORIGINAL`, `VarHandle`, JPMS; tất cả đều còn phù hợp, không dựa vào kỹ thuật lỗi thời.
- **Không expose privileged Lookup/private MethodHandle cho untrusted code**, và không dùng JVM member access thay business authorization.

## Tài liệu chính thức (API hiện hành)

- [MethodHandles.Lookup — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access checking, modes, public/private lookup, findStatic/findVirtual/findSpecial, cross-module teleport, dropLookupMode, member resolution failures.
- [MethodHandles.Lookup — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): bảo đảm API chạy trên baseline Java 17.
- [MethodHandles — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, `privateLookupIn` và caller-sensitive contracts.
- [MethodHandle — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `invoke`, `asType` và quyền khi handle đã tạo.
- [MethodType — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): method signatures và callsite type descriptors.
- [VarHandle — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html): variable access modes và memory ordering.
- [WrongMethodTypeException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): sai kiểu callsite method handles.
- [Module — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `isExported`, `isOpen`, `canRead`.
- [Java Language Specification `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.6): access control Java.
- [Java Virtual Machine Specification `5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.4): JVM access rules.
