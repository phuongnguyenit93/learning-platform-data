# Kiểm tra quyền `Lookup` dựa trên lớp hiện tại và lớp tra cứu trước

## 1. Vấn đề: cùng một đối tượng `Lookup` có thể mang hai ngữ cảnh lớp

`java.lang.invoke.MethodHandles.Lookup` là đối tượng **mang năng lực tra cứu** (*capability*) của Java Method Handles. Một `Lookup` có thể tạo `MethodHandle` tới constructor, phương thức hoặc trường mà ngữ cảnh tra cứu được phép truy cập. Đây là cơ chế quan trọng của reflection hiệu năng cao, framework, thư viện serialization, dynamic language runtime và những ứng dụng có JPMS module.

Khi tạo method handle, Java **kiểm tra quyền tại thời điểm tra cứu**. Method handle đã được tạo thành công không liên tục kiểm tra lại quyền của từng người gọi khi `invoke`. Vì vậy, một `Lookup` có quyền mạnh là một capability đáng bảo vệ: chia sẻ tùy tiện có thể cho code nhận được quyền tạo handle tới member vốn không thể tự truy cập.

Từ **Java 14**, API có thêm `Lookup.previousLookupClass()` để phản ánh trường hợp `Lookup` từng **chuyển ngữ cảnh giữa các module** (*teleportation*). Khi điều này xảy ra, quyền đối với **public type và member** có thể phải được xét theo **cả hai lớp**:

- `lookup.lookupClass()`: **lớp tra cứu hiện tại** — nơi `Lookup` đang đại diện.
- `lookup.previousLookupClass()`: **lớp tra cứu trước** — lớp ở module khác mà `Lookup` đã chuyển từ đó sang; trả `null` nếu không có.
- `lookup.lookupModes()`: **bit mask giới hạn quyền** của `Lookup`, ví dụ `PUBLIC`, `PRIVATE`, `PACKAGE`, `MODULE`.
- **JPMS module graph**: module nào đọc được module nào (`requires`), package nào được `exports` cho module nào, hoặc được `opens` để truy cập sâu.

**Kết luận then chốt:** `lookupClass()` và `previousLookupClass()` **không chỉ là hai tên để ghi log**. Nếu có lớp tra cứu trước, việc kiểm tra truy cập qua ranh giới module phải tính đến **cả hai ngữ cảnh**. Một `Lookup` không thể có quyền lớn hơn chỉ vì đã được chuyển sang lớp khác.

**Phiên bản và tính hiện hành:** `previousLookupClass()` xuất hiện từ Java 14 và vẫn được tài liệu hóa trên Java 17/21/25. Các ví dụ dưới đây dùng **Java 17+**, không cần preview API, `setAccessible(true)` hay các kỹ thuật phá đóng gói module đã lỗi thời.

## 2. Phân biệt `lookupClass()`, `previousLookupClass()` và quyền thực tế

Ví dụ cơ bản khi chưa chuyển module:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass().getName());
System.out.println(lookup.previousLookupClass()); // null
```

Đây là **đoạn mã minh họa**, cần đặt trong một phương thức/lớp thích hợp. `MethodHandles.lookup()` trả `Lookup` đại diện **lớp gọi thực sự**; nó là factory *caller-sensitive*. Vì vậy, `lookupClass()` là tên lớp nơi `MethodHandles.lookup()` được gọi, không phải tự động là `MethodHandles` hay `Object`.

Một `Lookup` mới tạo bằng `MethodHandles.lookup()` có `previousLookupClass() == null`. Khi `Lookup` được chuyển sang lớp khác **trong cùng module**, lớp hiện tại có thể thay đổi nhưng lớp trước vẫn được giữ như cũ (thường là `null`). Khi chuyển từ module `M0` sang module `M1`, lớp tra cứu cũ được ghi lại như `previousLookupClass()`.

### Bảng phân biệt

| Khía cạnh | `lookupClass()` | `previousLookupClass()` |
| --- | --- | --- |
| Ý nghĩa | Lớp mà `Lookup` đang đại diện | Lớp cũ tại lần chuyển ngữ cảnh **khác module** gần nhất |
| Có thể `null`? | Không với `Lookup` hợp lệ | Có; thường là `null` khi mới tạo |
| Tác động kiểm tra quyền | Bối cảnh chính của access check | Bối cảnh bổ sung khi kiểm tra public access qua module |
| Có thay đổi sau `Lookup.in(...)`? | Thay theo lớp đích | Chỉ cập nhật theo quy tắc chuyển module |
| Có thể tự cấp thêm quyền? | Không | Không; chỉ tạo thêm giới hạn hoặc ghi lại nguồn gốc |

**Không nhầm “previous” với dòng code gọi trước đó.** `previousLookupClass` **không phải stack frame trước**, không phải superclass, không phải “đối tượng từng được gọi bằng reflection”, cũng không phải lịch sử đầy đủ mọi `Lookup.in(...)` từng thực hiện. Nó chỉ giữ **một ngữ cảnh lớp trước** theo quy tắc của Lookup API.

## 3. Các bit `lookupModes()` giới hạn phạm vi truy cập

`lookup.lookupModes()` trả về một số nguyên bit mask. Trong Java 17+ các mode quan trọng gồm:

| Mode | Khả năng tiêu biểu | Lưu ý |
| --- | --- | --- |
| `PUBLIC` | Tra cứu public member của public type phù hợp ngữ cảnh module | Còn phụ thuộc readability/exports và previous class |
| `PRIVATE` | Truy cập private member theo điều kiện nest/lookup | Không tự có nghĩa quyền qua mọi module |
| `PROTECTED` | Quyền truy cập protected theo ngữ cảnh phù hợp | Còn các giới hạn kế thừa/package |
| `PACKAGE` | Quyền theo package | Bị loại khi chuyển sang package khác |
| `MODULE` | Quyền đại diện ngữ cảnh của một module | Bị loại khi chuyển giữa các module |
| `UNCONDITIONAL` | Public access tới các package **export vô điều kiện**, giả định readability | Đặc trưng của `publicLookup()`, previous class luôn `null` |
| `ORIGINAL` | Lookup do lớp gốc tạo trực tiếp, dùng cho một số thao tác nhạy cảm | Có trong Java 16+; mất khi `lookupClass` thay đổi |

**Lưu ý:** Có bit `PUBLIC` **chưa đủ** để khẳng định sẽ truy cập được một public type bất kỳ. JPMS vẫn xét module đọc được nhau không, package export cho ai, và **lớp trước** nếu có.

Kiểm tra một bit đúng cách:

```java
boolean hasModule = (lookup.lookupModes()
        & MethodHandles.Lookup.MODULE) != 0;
boolean hasPrivate = (lookup.lookupModes()
        & MethodHandles.Lookup.PRIVATE) != 0;
```

Đoạn này minh họa với biến `lookup` đã tồn tại. Không nên so sánh `lookupModes() == MethodHandles.Lookup.PUBLIC` để hỏi có quyền public hay không, vì số bit mask có thể chứa **nhiều bit cùng lúc**.

### Full privilege

`lookup.hasFullPrivilegeAccess()` là API hiện hành trong Java 17+, trả `true` khi `Lookup` có cả hai quyền **`MODULE` và `PRIVATE`**. Quyền này cần thiết trong nhiều tình huống `MethodHandles.privateLookupIn`.

```java
boolean full = lookup.hasFullPrivilegeAccess();
```

**Có `PRIVATE` mà mất `MODULE` vẫn không phải full privilege.** Điều đó đặc biệt quan trọng sau `privateLookupIn` xuyên module.

## 4. Điều gì xảy ra khi `Lookup.in(Target.class)`?

`lookup.in(Target.class)` tạo một `Lookup` đại diện lớp `Target`, **không tăng quyền**. Các mode có thể giảm.

### 4.1. Chuyển lớp trong cùng module

Giả sử `Main` và `Helper` đều thuộc module `m.origin`. Khi gọi:

```java
MethodHandles.Lookup next = original.in(Helper.class);
```

- `next.lookupClass() == Helper.class`.
- Nếu `original.previousLookupClass() == null`, `next.previousLookupClass()` vẫn `null`.
- `MODULE` có thể **được giữ** vì chưa qua ranh giới module.
- `ORIGINAL` mất khi lớp tra cứu thay đổi.
- `PRIVATE` và `PACKAGE` còn hay mất tùy quan hệ nest/package giữa hai lớp, **không** tự do giữ mọi quyền.

### 4.2. Chuyển từ `M0` sang `M1`

Giả sử `Main` thuộc module `m.origin` và `Target` thuộc `m.target`:

```java
MethodHandles.Lookup across = original.in(Target.class);
```

Sau khi `Target` được xác nhận đủ điều kiện tiếp cận:

- `across.lookupClass() == Target.class`.
- `across.previousLookupClass() == Main.class`.
- `across` **mất `MODULE`, `PRIVATE`, `PACKAGE` và những mode không phù hợp** khi chuyển xuyên module.
- Trong ví dụ lớp public được export hợp lệ, `across` còn `PUBLIC`.
- Việc tạo handle tới public type/member ở một module khác có thể cần **cả `m.origin` và `m.target` cùng được quyền nhìn thấy**.

Gọi `in` với lớp đích **không phải API xin quyền**. Nếu ban đầu không có quyền, chuyển ngữ cảnh không “tẩy trắng” quyền cũ.

### 4.3. Chuyển tiếp sang module thứ ba

Giả sử `across` đã mang:

```text
lookupClass         = Target      (module m.target)
previousLookupClass = Main        (module m.origin)
```

Nếu tiếp tục gọi `across.in(SharedApi.class)`, trong đó `SharedApi` ở module thứ ba `m.shared`, các quyền của `Lookup` sẽ **bị loại toàn bộ** theo quy tắc teleportation qua ba module khác nhau. `previousLookupClass` trở thành `Target`, nhưng `lookupModes()` không còn mode cho phép tra cứu member.

**Đừng suy ra có quyền từ việc `lookupClass()` hiện bằng lớp mục tiêu:** tên lớp đại diện có thể đổi trong khi quyền đã mất hết. Luôn xem cả bit mode và access check của thao tác thực tế.

## 5. Kiểm tra quyền public qua hai lớp: lấy phần giao

Tài liệu `MethodHandles.Lookup` quy định: khi lookup có mode `PUBLIC` và `previousLookupClass()` khác `null` ở **module khác**, quyền truy cập public type được xét theo **phần giao** của những type mà:

1. **Module chứa `lookupClass()`** có thể truy cập.
2. **Module chứa `previousLookupClass()`** có thể truy cập.

Một public type chỉ được xem là khả dụng nếu **cả hai ngữ cảnh** đều có quyền tương ứng. Khi xét type ở **module thứ ba**, điều kiện thông dụng gồm:

- Cả hai module đều **đọc được** module đích.
- Package chứa type đích được **export đủ rộng tới cả hai** (hoặc export vô điều kiện).
- Type/member cần truy cập là `public` và `Lookup` vẫn giữ `PUBLIC`.

Nếu type nằm ngay trong module của `lookupClass`, module đó đương nhiên tiếp cận nội bộ, nhưng **module trước** vẫn cần quyền tiếp cận package được export. Với type trong module trước thì xét điều kiện đối xứng tương ứng.

**Ví dụ dễ nhớ:**

```text
m.origin (Main) --requires--> m.target (Target)
     |
     +--------------requires--> m.shared (SharedApi)

m.target  KHÔNG requires m.shared

Lookup gốc:             Main / previous=null
Lookup sau .in(Target): Target / previous=Main
```

`Main` vốn đọc được cả `m.target` và `m.shared`. Tuy nhiên `Target` thuộc `m.target`, mà `m.target` **không đọc `m.shared`**. Do đó:

- `original.findStatic(SharedApi.class, ...)` có thể thành công.
- `across.findStatic(Target.class, ...)` có thể thành công.
- `across.findStatic(SharedApi.class, ...)` **bị từ chối** dù `SharedApi` và phương thức của nó đều `public`.

Đây là ví dụ trực tiếp của **kiểm tra theo cả lớp hiện tại và lớp tra cứu trước**. Không được nhìn thấy `SharedApi` từ `Main` rồi kết luận `Lookup` đã chuyển sang `Target` vẫn giữ quyền ấy.

### `exports` có điều kiện cũng quan trọng

Trong JPMS, một module có thể:

```java
exports com.example.api to m.origin;
```

Đây là **một directive minh họa trong `module-info.java`**, không phải chương trình hoàn chỉnh. Nó chỉ cho `m.origin` quyền nhìn thấy public type của package, **không nhất thiết** cho `m.target`. Khi `Lookup` mang cả hai module làm bối cảnh, một qualified export chỉ tới **một** trong hai có thể không đủ.

Tương tự, `Module.canRead(...)` hoặc `Module.isExported(...)` hữu ích để chẩn đoán nhưng **không thay thế** access check của `Lookup`. Cần xét mode, member modifier, các package được export và cả hai lớp khi có previous.

## 6. Chương trình JPMS Java 17+ hoàn chỉnh: ba module, quyền thay đổi có kiểm chứng

Ví dụ cố ý dùng ba module để khiến sự khác biệt về quyền **quan sát được**, thay vì chỉ in `lookupClass()` và `previousLookupClass()`.

### 6.1. Cấu trúc mã nguồn

Tạo những file sau trong dự án:

```text
src/
├── m.origin/
│   ├── module-info.java
│   └── origin/
│       └── Main.java
├── m.target/
│   ├── module-info.java
│   └── target/
│       └── Target.java
└── m.shared/
    ├── module-info.java
    └── shared/
        └── SharedApi.java
```

Đây là cấu trúc cho `javac --module-source-path src`. Tên thư mục ngay dưới `src` trùng với tên module.

### 6.2. Module nguồn `m.origin`

File **`src/m.origin/module-info.java`**:

```java
module m.origin {
    requires m.target;
    requires m.shared;
}
```

`m.origin` là nơi chạy `Main` và tạo `MethodHandles.lookup()`. Nó đọc được **cả `m.target` và `m.shared`**.

File **`src/m.origin/origin/Main.java`**:

```java
package origin;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import shared.SharedApi;
import target.Target;

public class Main {
    static String name(Class<?> type) {
        return type == null ? "null" : type.getSimpleName();
    }
    static boolean has(MethodHandles.Lookup lookup, int mode) {
        return (lookup.lookupModes() & mode) != 0;
    }
    static String call(MethodHandles.Lookup lookup, Class<?> type, String method)
            throws Throwable {
        MethodHandle handle = lookup.findStatic(
                type, method, MethodType.methodType(String.class));
        return (String) handle.invokeExact();
    }
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup original = MethodHandles.lookup();
        MethodHandles.Lookup sameModule = original.in(Helper.class);
        MethodHandles.Lookup across = original.in(Target.class);
        System.out.println("originalLookup=" + name(original.lookupClass()));
        System.out.println("originalPrevious=" +
                name(original.previousLookupClass()));
        System.out.println("originalFull=" +
                original.hasFullPrivilegeAccess());
        System.out.println("sameModulePrevious=" +
                name(sameModule.previousLookupClass()));
        System.out.println("sameModuleHasModule=" +
                has(sameModule, MethodHandles.Lookup.MODULE));

        System.out.println("acrossLookup=" + name(across.lookupClass()));
        System.out.println("acrossPrevious=" +
                name(across.previousLookupClass()));
        System.out.println("acrossPublic=" +
                has(across, MethodHandles.Lookup.PUBLIC));
        System.out.println("acrossModule=" +
                has(across, MethodHandles.Lookup.MODULE));
        System.out.println("acrossPrivate=" +
                has(across, MethodHandles.Lookup.PRIVATE));
        System.out.println("targetHello=" +
                call(across, Target.class, "hello"));
        System.out.println("originalShared=" +
                call(original, SharedApi.class, "hello"));
        try {
            call(across, SharedApi.class, "hello");
            System.out.println("acrossShared=ALLOWED");
        } catch (IllegalAccessException expected) {
            System.out.println("acrossShared=DENIED");
        }

        MethodHandles.Lookup third = across.in(SharedApi.class);
        System.out.println("thirdLookup=" + name(third.lookupClass()));
        System.out.println("thirdPrevious=" +
                name(third.previousLookupClass()));
        System.out.println("thirdPublic=" +
                has(third, MethodHandles.Lookup.PUBLIC));

        MethodHandles.Lookup privateTarget =
                MethodHandles.privateLookupIn(Target.class, original);
        System.out.println("deepLookup=" +
                name(privateTarget.lookupClass()));
        System.out.println("deepPrevious=" +
                name(privateTarget.previousLookupClass()));
        System.out.println("deepPrivate=" +
                has(privateTarget, MethodHandles.Lookup.PRIVATE));
        System.out.println("deepModule=" +
                has(privateTarget, MethodHandles.Lookup.MODULE));
        System.out.println("deepSecret=" +
                call(privateTarget, Target.class, "secret"));
        try {
            MethodHandles.privateLookupIn(
                    SharedApi.class, privateTarget);
            System.out.println("secondPrivate=ALLOWED");
        } catch (IllegalAccessException expected) {
            System.out.println("secondPrivate=DENIED");
        }
    }
}
class Helper {}
```

**Đặc điểm của ví dụ:**

- `call(...)` dùng `Lookup.findStatic` với chữ ký chính xác `String hello()` hoặc `String secret()`, trả về một `MethodHandle` và gọi `invokeExact()`.
- `name(...)` chỉ dùng tên lớp ngắn cho đầu ra dễ nhìn; trong ứng dụng thật nên xem **module + tên lớp đầy đủ** để tránh trùng tên giữa package.
- `has(...)` kiểm tra từng bit mode riêng, không so sánh nguyên mask với một hằng số.
- `IllegalAccessException` được bắt **chỉ ở những phép tra cứu cố ý bị từ chối**. Một phương thức bị thiếu tên/chữ ký thường gây `NoSuchMethodException`, không nên coi mọi lỗi là “thiếu quyền”.
- `main throws Throwable` làm ví dụ nhỏ gọn để có thể gọi `MethodHandle.invokeExact()`; ứng dụng thực cần xử lý exception theo yêu cầu nghiệp vụ.

### 6.3. Module đích `m.target`

File **`src/m.target/module-info.java`**:

```java
module m.target {
    exports target;
    opens target to m.origin;
}
```

- `exports target;` cho phép truy cập public type trong package `target`.
- `opens target to m.origin;` cho phép `m.origin` truy cập sâu vào package `target` theo cơ chế reflection có kiểm soát, để minh họa `privateLookupIn`.
- `m.target` **không** khai báo `requires m.shared;` — điều này **cố ý** để tạo tình huống “module gốc đọc được, module hiện tại không đọc được” ở phần 6.5.
- Không dùng `open module m.target` chỉ để đơn giản hóa demo: mở nguyên module thường **quá rộng** so với mức quyền cần thiết.

File **`src/m.target/target/Target.java`**:

```java
package target;

public class Target {
    public static String hello() { return "TARGET"; }
    private static String secret() { return "SECRET"; }
}
```

Có hai member đối chiếu: `hello()` là `public`, `secret()` là `private`.

### 6.4. Module thứ ba `m.shared`

File **`src/m.shared/module-info.java`**:

```java
module m.shared {
    exports shared;
}
```

File **`src/m.shared/shared/SharedApi.java`**:

```java
package shared;

public class SharedApi {
    public static String hello() { return "SHARED"; }
}
```

Module `m.shared` export public package. `m.origin` đọc được nó do `requires m.shared;`, nhưng `m.target` **không có** cạnh đọc module này. Việc package được export **không tự tạo `requires`** ở các module bên ngoài.

### 6.5. Biên dịch và chạy

Đứng tại thư mục chứa `src`, dùng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -d out --module-source-path src -m m.origin
java --module-path out --module m.origin/origin.Main
```

**Stdout đã được kiểm chứng bằng JDK hỗ trợ Java 17:**

```text
originalLookup=Main
originalPrevious=null
originalFull=true
sameModulePrevious=null
sameModuleHasModule=true
acrossLookup=Target
acrossPrevious=Main
acrossPublic=true
acrossModule=false
acrossPrivate=false
targetHello=TARGET
originalShared=SHARED
acrossShared=DENIED
thirdLookup=SharedApi
thirdPrevious=Target
thirdPublic=false
deepLookup=Target
deepPrevious=Main
deepPrivate=true
deepModule=false
deepSecret=SECRET
secondPrivate=DENIED
```

Đầu ra đến từ **một ứng dụng modular chạy thật**, không phải dữ liệu đoán theo lý thuyết. Quan sát từng nhóm:

| Dòng output | Điều được chứng minh |
| --- | --- |
| `originalLookup=Main`, `originalPrevious=null` | `MethodHandles.lookup()` tạo `Lookup` ban đầu với lớp hiện tại và không có previous |
| `originalFull=true` | Lớp tạo `Lookup` có đủ `MODULE` và `PRIVATE` |
| `sameModulePrevious=null`, `sameModuleHasModule=true` | Đổi lớp trong cùng module không tự phát sinh previous và giữ `MODULE` |
| `acrossLookup=Target`, `acrossPrevious=Main` | Chuyển từ `m.origin` sang `m.target` khiến previous là `Main` |
| `acrossPublic=true`, `acrossModule=false`, `acrossPrivate=false` | Teleportation thường chỉ giữ public access thích hợp; không được khôi phục đặc quyền cũ |
| `targetHello=TARGET` | Public member trong module đích có thể được truy cập bởi cả hai ngữ cảnh |
| `originalShared=SHARED` | `Main` ban đầu được phép gọi public method của module `m.shared` |
| `acrossShared=DENIED` | Sau khi chuyển sang `Target`, module hiện tại `m.target` không đọc `m.shared` nên phép tra cứu bị từ chối |
| `thirdLookup=SharedApi`, `thirdPrevious=Target`, `thirdPublic=false` | Chuyển tiếp sang module thứ ba làm mất tất cả lookup modes |
| `deepLookup=Target`, `deepPrevious=Main` | `privateLookupIn` xuyên module cũng lưu previous class |
| `deepPrivate=true`, `deepModule=false` | Có quyền private đối với target nhưng không còn quyền module/full privilege |
| `deepSecret=SECRET` | `opens target to m.origin` cho phép tạo handle tới private method trong module đích |
| `secondPrivate=DENIED` | Không thể dùng lookup đã mất `MODULE` để gọi `privateLookupIn` vượt module tiếp |

**Điểm đặc biệt:** Ví dụ `acrossShared=DENIED` **không phải vì `SharedApi.hello()` là private**. Phương thức đó là `public`, package được `exports` vô điều kiện, nhưng **module hiện tại của `Lookup` không đọc được `m.shared`**. Chính điều kiện kiểm tra quyền của **cả lookup class và previous lookup class** tạo nên khác biệt này.

### 6.6. Tại sao kết quả không cần cờ `--add-opens`?

Module `m.target` đã chủ động khai báo:

```java
opens target to m.origin;
```

Điều này trao quyền cần thiết cho `privateLookupIn` trong ví dụ. Không cần mở package bằng cờ launcher. Trong ứng dụng production, chỉ dùng `opens` hoặc `--add-opens` khi có lý do được chủ sở hữu module chấp thuận; **không coi `--add-opens` là mẹo tự động giải quyết mọi lỗi quyền**.

## 7. `privateLookupIn`: quyền private vẫn chịu kiểm soát module

Ngoài `Lookup.in(...)`, Java còn có:

```java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
```

Đây là một **API khác**, không chỉ đổi lookup class như `in`. Nó có thể tạo `Lookup` có `PRIVATE` đối với target **nếu điều kiện deep reflection được đáp ứng**.

### Điều kiện với hai module khác nhau

Cho lớp gọi ở module `M0` và target ở module `M1`, tài liệu chính thức yêu cầu:

1. `callerLookup` có cả `MODULE` và `PRIVATE` — tức full privilege.
2. `M0` **đọc được `M1`**.
3. `M1` **opens package chứa target** cho ít nhất `M0`.
4. `Target` là một lớp hợp lệ cho yêu cầu, không phải primitive, void hay array class.

Nếu thỏa, `privateLookupIn` tạo `Lookup` với:

- `lookupClass() == Target.class`.
- `previousLookupClass()` là lớp gọi ở `M0`.
- `PRIVATE` được giữ theo quyền deep reflection tương ứng.
- **`MODULE` bị bỏ**, nên kết quả **không** có full privilege.
- Không thể dùng kết quả ấy để tiếp tục gọi `privateLookupIn` trên một class khác nhằm “leo thang” đặc quyền.

**Phân biệt `exports` và `opens`:**

| Directive | Vai trò |
| --- | --- |
| `exports target;` | Cho phép các module khác đọc module này truy cập **public API** trong `target` |
| `exports target to m.origin;` | Export public API chỉ cho `m.origin` |
| `opens target to m.origin;` | Mở package cho **deep reflection** của `m.origin` (đủ điều kiện), không thay `requires` |
| `open module m.target` | Mở rộng khả năng reflection cho toàn module; thường quá rộng nếu chỉ cần một package |

**Không khuyến nghị** mở toàn bộ module cho thư viện không tin cậy. Một `Lookup` có quyền private là capability nhạy cảm: chỉ cấp cho code cần thiết và được tin cậy.

### Nếu `privateLookupIn` thất bại

Thường có `IllegalAccessException` khi thiếu full privilege, module không đọc được target, hoặc package chưa `opens` tới module gọi. `IllegalArgumentException` có thể xuất hiện với target class không hợp lệ. Một số phương thức lookup riêng có thể thất bại do member không tồn tại hoặc sai chữ ký; cần phân biệt **lỗi access** với **lỗi API name/signature**.

## 8. `publicLookup()` và `dropLookupMode(...)` không thay quyền của previous class

Nếu chỉ cần tra cứu API công khai, `MethodHandles.publicLookup()` tạo `Lookup` ít quyền với mode `UNCONDITIONAL`. Nó có `previousLookupClass() == null` và cho phép truy cập public type trong package được **export vô điều kiện** (unqualified exports), với quy tắc readability riêng của `UNCONDITIONAL`.

```java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
System.out.println(publicOnly.previousLookupClass()); // null
```

**`publicLookup()` không có quyền gọi private member** và không được dùng để vượt qua một package chỉ export có điều kiện hoặc package chưa export. Nó cũng không tự động mang `PRIVATE` hay `MODULE`.

Để giảm quyền của một `Lookup` đã có, dùng `dropLookupMode(...)`:

```java
MethodHandles.Lookup reduced =
        original.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Đây là đoạn minh họa yêu cầu `original` hợp lệ. `dropLookupMode` tạo lookup **ít hoặc bằng quyền ban đầu**; không bao giờ thêm mode bị mất. Nếu drop `MODULE`, quy tắc còn có thể kéo theo mất `PACKAGE`/`PRIVATE`; nếu drop `PUBLIC` thì lookup không còn khả năng truy cập member theo mode đó.

**Đừng lạm dụng `publicLookup()` để che lỗi module configuration.** Nếu một thư viện được phép truy cập public API qua `requires` và `exports` nhưng `Lookup` đang dùng không đủ quyền, hãy xem lại **nguồn gốc và quá trình chuyển lookup**, không chỉ thay tùy tiện thành `publicLookup()`.

## 9. Cách kiểm tra quyền an toàn trong code thực tế

Khi một lời gọi `findVirtual`, `findStatic`, `findGetter` hoặc `privateLookupIn` bất ngờ thất bại, nên chẩn đoán theo thứ tự:

1. **Xem `lookup.lookupClass()`** và module của lớp đó: `lookup.lookupClass().getModule().getName()`.
2. **Xem `lookup.previousLookupClass()`**; nếu khác `null`, lấy module của lớp trước.
3. **Xem `lookup.lookupModes()`** bằng phép bit mask; hỏi có `PUBLIC`, `PRIVATE`, `MODULE` đúng yêu cầu không.
4. **Đối chiếu module graph:** cả hai module có đọc được module chứa type đích không? Có `requires` ở descriptor phù hợp không?
5. **Đối chiếu export/open:** target package có `exports` tới đúng module không? Nếu cần private reflection, package có `opens` cho module gốc không?
6. **Đối chiếu modifier và chữ ký:** member có thật, đúng tên, `static` hay instance, đúng tham số/return type của `MethodType`?
7. **Thử phép tra cứu thực tế** và xử lý `IllegalAccessException`, `NoSuchMethodException` theo tình huống; **không chỉ đoán** từ quyền ở mức module.
8. **Theo dõi `Lookup.in(...)` và `privateLookupIn(...)`** trong luồng truyền lookup; quyền đã bị giảm không tự phục hồi khi tiếp tục chuyển.
9. **Không ghi log những `Lookup` nhạy cảm hay cung cấp chúng cho code không tin cậy** nếu có thể tránh; cung cấp handle cần thiết hoặc API giới hạn hơn.

Một hàm chẩn đoán chỉ báo thông tin, **không quyết định thay access check**:

```java
static void inspect(MethodHandles.Lookup lookup) {
    Class<?> current = lookup.lookupClass();
    Class<?> previous = lookup.previousLookupClass();

    System.out.println("current=" + current.getName());
    System.out.println("currentModule=" +
            current.getModule().getName());
    System.out.println("previous=" +
            (previous == null ? "null" : previous.getName()));
    System.out.println("modes=" + lookup.lookupModes());
}
```

Đoạn này cần đặt trong lớp và import `java.lang.invoke.MethodHandles`. Trong **unnamed module**, `getModule().getName()` có thể là `null`; nếu cần, hiển thị tên đại diện của module không tên thay vì cho rằng metadata bị hỏng.

Một số method-handle factory nhận `Class<?>` đã biết. Lớp có thể tồn tại và có `public` modifier nhưng vẫn **không truy cập được** từ lookup vì package/module restriction. Ngược lại, cùng một target và chữ ký, dùng hai lookup khác nhau có thể cho kết quả khác nhau.

### Access check diễn ra khi tạo handle

```java
MethodHandle handle = lookup.findStatic(
        SomeType.class, "action", MethodType.methodType(void.class));
```

Nếu `lookup` không đủ quyền, việc tạo handle sẽ thất bại trước khi gọi `invokeExact()`. **Đừng kết luận rằng phương thức không tồn tại chỉ vì access check từ lookup này thất bại.** Nếu một handle đã được tạo và chuyển cho nơi khác, việc gọi handle thường không phải kiểm tra lại quyền truy cập member theo lookup class của người nhận. Đây là lý do **không chia sẻ handle đặc quyền ngoài phạm vi tin cậy**.

## 10. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao không đúng? | Cách xử lý |
| --- | --- | --- |
| Chỉ xem `lookupClass()` rồi kết luận có quyền | Có thể còn `previousLookupClass()` và mode đã giảm | Xem cả hai lớp, module và mask |
| Cho rằng `previousLookupClass()` là lớp cha Java | Đây là ngữ cảnh module cũ của lookup, không phải inheritance | Hiểu teleportation theo JPMS |
| Cho rằng `previousLookupClass() != null` chỉ mang tính log | Nó bổ sung điều kiện access check qua module | Xem phần giao public access của hai module |
| Cho rằng `PUBLIC` là được gọi mọi phương thức `public` | Có thể thiếu `requires` hoặc `exports` đúng target | Xác minh graph và cả previous class |
| Cho rằng `Lookup.in` nâng quyền cho lớp đích | `in` chỉ giữ hoặc giảm quyền | Không dùng `in` như bypass module |
| Chuyển tiếp qua ba module và mong giữ `PUBLIC` | Quyền bị loại khi teleport sang module thứ ba | Tạo lookup hợp lệ từ module gốc đủ quyền |
| Chỉ kiểm tra `hasFullPrivilegeAccess()` rồi bỏ qua target package | Full privilege ở nguồn chưa đủ mở deep reflection | Cần `reads` và `opens` phù hợp |
| Có `PRIVATE` mà không có `MODULE` rồi gọi tiếp `privateLookupIn` | Không còn full privilege | Không chain deep lookup xuyên module |
| Nhầm `exports` với `opens` | Export public API khác deep reflection | Dùng directive tối thiểu đúng mục đích |
| Dùng `--add-opens` như giải pháp mặc định mọi lỗi | Có thể mở package quá rộng và không khắc phục thiếu mode | Sửa cấu hình/luồng capability, mở có chủ đích |
| So sánh `lookupModes() == PUBLIC` | Có nhiều bit đồng thời | Dùng `(lookupModes() & PUBLIC) != 0` |
| Lỗi `NoSuchMethodException` bị gọi là lỗi quyền | Có thể sai tên, static/instance hoặc `MethodType` | Kiểm tra chữ ký member riêng |
| Chia sẻ lookup gốc có `PRIVATE` với plugin tùy ý | Trao capability truy cập nhạy cảm | Hạn chế scope, drop mode hoặc chỉ chuyển handle cần thiết |
| `publicLookup()` được cho là truy cập mọi class công khai | Vẫn bị giới hạn bởi export vô điều kiện và public member | Hiểu `UNCONDITIONAL` và JPMS |
| Viết `opens toàn module` chỉ để một package được đọc | Mở rộng diện deep reflection ngoài nhu cầu | Dùng `opens package to module` có chọn lọc |

## 11. Bài tập có đáp án

**Câu 1.** `lookupClass()` và `previousLookupClass()` khác nhau thế nào?  
**Đáp án:** Một cái là lớp hiện tại đại diện cho lookup, một cái là lớp gốc ở module khác được ghi lại khi lookup chuyển ngữ cảnh. Previous có thể `null`.

**Câu 2.** `previousLookupClass()` xuất hiện từ bản Java nào và còn dùng trong Java 17+ không?  
**Đáp án:** Từ Java 14; API vẫn hiện hành trong Java 17/21/25.

**Câu 3.** Vì sao `original.in(Target.class)` có thể còn `PUBLIC` nhưng mất `MODULE`?  
**Đáp án:** `in` chuyển lookup sang một module khác, nên mất các quyền gắn với module cũ. Public access còn nếu đáp ứng điều kiện, nhưng bị giới hạn bởi hai module.

**Câu 4.** Trong ví dụ ba module, tại sao `originalShared=SHARED` nhưng `acrossShared=DENIED`?  
**Đáp án:** `m.origin` đọc `m.shared`, còn `m.target` không đọc nó. Sau khi chuyển sang `Target`, quyền cần hợp lệ từ cả current module và previous module.

**Câu 5.** `across.in(SharedApi.class)` chuyển qua module thứ ba dẫn tới điều gì?  
**Đáp án:** Mọi lookup mode bị loại; `lookupClass` mới là `SharedApi`, previous là `Target` và `PUBLIC` không còn.

**Câu 6.** Có `PRIVATE` là đủ để gọi tiếp `privateLookupIn` ở module khác chưa?  
**Đáp án:** Chưa. Cần cả `MODULE` và `PRIVATE` (full privilege), cùng `reads` và `opens` thích hợp.

**Câu 7.** `opens target to m.origin;` khác `exports target;` ra sao?  
**Đáp án:** `opens` cho deep reflection tới module được chỉ định; `exports` cho phép truy cập public API từ module đọc được nó.

**Câu 8.** `publicLookup()` có previous lookup class không?  
**Đáp án:** Không; `previousLookupClass()` trả `null`. Lookup này có `UNCONDITIONAL` nhưng chỉ truy cập public API trong package export vô điều kiện.

**Câu 9.** Vì sao không nên giữ và chia sẻ `MethodHandles.lookup()` có full privilege trong singleton chung cho plugin tùy ý?  
**Đáp án:** Đó là capability được phép tạo handle tới member nhạy cảm của ngữ cảnh gốc; việc chuyển quyền tùy tiện có thể làm mất an toàn đóng gói.

**Câu 10.** Java kiểm tra access của method handle vào lúc tạo hay mỗi lần `invoke`?  
**Đáp án:** Chủ yếu khi tạo method handle bằng factory của `Lookup`; handle đã tạo không tự kiểm tra lại quyền thành viên theo người gọi ở mỗi lần invoke.

## 12. Tổng kết và tài liệu chuẩn

**Quy tắc nhớ nhanh:**

```text
Một Lookup khi tra cứu:
    lookupClass()
  + previousLookupClass() (nếu có)
  + lookupModes()
  + module readability / package exports / opens
  + modifier và chữ ký của member
  => khả năng tạo method handle
```

- `previousLookupClass()` là dấu vết của việc **chuyển lookup qua ranh giới JPMS module**.
- Khi có previous class, public access qua module là **phần giao** của những gì hai ngữ cảnh có thể tiếp cận.
- `Lookup.in(...)` **không nâng quyền**, và chuyển qua module thứ ba có thể làm mất mọi mode.
- `privateLookupIn(...)` có các quy tắc **full privilege + reads + opens** riêng; kết quả vượt module có `PRIVATE` nhưng không có `MODULE`.
- Bằng chứng đáng tin nhất là **thử đúng phép `find...` / `accessClass` trong cấu hình module thực**, không chỉ xem tên lớp.

**Nguồn tham khảo chính thức, còn áp dụng cho Java 17+:**

- [Oracle Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `lookupClass`, `previousLookupClass`, `lookupModes`, `in` và quy tắc cross-module.
- [Oracle Java SE 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): quy tắc lookup/access trong Java hiện đại.
- [Oracle Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn` và điều kiện full privilege.
- [Oracle Java SE 17 — JPMS module descriptors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens` và khai báo module.
- [Oracle Java SE 17 — Java access control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): quyền `public`/`private`/`protected`/package.
