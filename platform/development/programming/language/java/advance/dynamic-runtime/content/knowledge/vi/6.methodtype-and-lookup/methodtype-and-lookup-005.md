# 6.5 lookup, publicLookup và các chế độ quyền của Lookup

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt `MethodHandles.lookup()` và `MethodHandles.publicLookup()` theo **lớp gọi** (caller), phạm vi quyền và ranh giới module.
- Đọc `Lookup.lookupClass()`, `lookupModes()`, `hasFullPrivilegeAccess()`; hiểu các cờ `PUBLIC`, `PRIVATE`, `PROTECTED`, `PACKAGE`, `MODULE`, `UNCONDITIONAL` và `ORIGINAL`.
- Hiểu tại sao `Lookup.in(...)` và `dropLookupMode(...)` chỉ **giảm** quyền, trong khi `privateLookupIn(...)` có thể tạo lookup vào một lớp khác nhưng phải đáp ứng điều kiện nghiêm ngặt.
- Tạo method handle cho phương thức public/private bằng Java 17+, giải thích lỗi `IllegalAccessException` và tách lỗi quyền khỏi lỗi chữ ký.
- Áp dụng đúng `exports`, `opens` và `requires` của Java Platform Module System (JPMS) khi cần truy cập xuyên module; tránh làm lộ quyền truy cập private của thư viện.

## 2. `Lookup` là gì, tại sao lại có quyền?

`java.lang.invoke.MethodHandles.Lookup` là đối tượng **ngữ cảnh tra cứu và kiểm tra quyền** để tạo `MethodHandle` (hoặc `VarHandle`) cho method, constructor, field và một số thao tác cấp JVM. Ví dụ:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle handle = lookup.findStatic(
        SomePublicClass.class,
        "someStaticMethod",
        MethodType.methodType(String.class));
```

Đoạn trên là **mã minh họa**, giả định `SomePublicClass.someStaticMethod()` là static và trả `String`; cần import `java.lang.invoke.*` và xử lý `NoSuchMethodException`, `IllegalAccessException`. `Lookup` không thực hiện lời gọi: nó **tạo** handle, sau đó handle mới được gọi bằng `invokeExact`, `invoke` hay một adapter khác.

Một lookup về cơ bản giữ ngữ cảnh:

- **Lookup class:** lớp mà lookup đại diện, có thể xem qua `lookup.lookupClass()`.
- **Access modes:** các loại truy cập còn được phép, xem qua `lookup.lookupModes()` (bit mask).
- **Module context:** module của lookup class và, khi lookup đã vượt module, có thể gồm **previous lookup class** để kiểm tra khả năng đọc module.

Về bảo mật, lookup là một **capability** (quyền có thể chuyển giao). Các phương thức như `findStatic`, `findVirtual`, `findConstructor` hoặc `findGetter` kiểm tra quyền **khi tạo** handle. Sau khi tạo thành công, handle có thể được gọi bởi bên nhận handle mà không kiểm tra quyền member lại theo caller ở mỗi lần gọi. Vì vậy, trao `Lookup` có quyền private hoặc một handle đến phương thức nhạy cảm cho mã không tin cậy là việc trao quyền thực sự.

**Phân biệt ba đối tượng:** `MethodType` mô tả kiểu tham số/kiểu trả về; `Lookup` quyết định **có được liên kết** đến member hay không; `MethodHandle` là phép gọi đã liên kết. Có `MethodType` đúng không có nghĩa là đủ quyền để tạo handle.

## 3. `MethodHandles.lookup()`: lấy quyền của lớp thực sự gọi API

`MethodHandles.lookup()` là phương thức **caller-sensitive**: JVM xác định class đang **thực thi lời gọi** `lookup()`. Nó tạo lookup với full privilege access của lớp đó, bao gồm truy cập private của chính lớp gọi và các nestmate hợp lệ.

Ví dụ, bên trong `OrderService`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean belongsToOrderService =
        lookup.lookupClass() == OrderService.class;
```

Đây là **mã minh họa bên trong `OrderService`**, không phải file độc lập. Với lời gọi đặt trực tiếp trong class này, biến `belongsToOrderService` là `true`. Nếu chuyển lời gọi `MethodHandles.lookup()` vào một helper rồi trả lookup từ helper, lookup class lúc đó là **helper**, không phải `OrderService`.

Hệ quả:

- `lookup()` có thể tìm private member của chính lớp gọi hoặc nestmate theo quy tắc Java, nhưng **không tự cho quyền private trên mọi lớp**.
- Khi thư viện đóng gói helper `getLookup()` rồi gọi `MethodHandles.lookup()` bên trong helper, nó trả về lookup với quyền của **helper**. Không thể dùng helper này như một lối đi vòng để lấy quyền private của caller bất kỳ.
- `lookup()` tạo đối tượng có bit `ORIGINAL` (nguồn gốc caller) và có `PRIVATE` + `MODULE`, vì thế `hasFullPrivilegeAccess()` trả `true`. Các mode còn lại chịu semantics cụ thể của JVM.

Đối với code được phát sinh hoặc bootstrap method, một lookup được JVM cấp vào ngữ cảnh gọi có ý nghĩa bảo mật; không nên tự tạo hoặc chuyển nhầm lookup có quyền cao hơn yêu cầu.

## 4. `MethodHandles.publicLookup()`: quyền public tối thiểu

`MethodHandles.publicLookup()` trả lookup dùng cho các member **public** của các class **public** nằm trong package được **export vô điều kiện** (unqualified export) tới mọi module. Đối tượng này không có quyền private, protected hoặc package-private, và không cung cấp full privilege access.

Điểm dễ nhầm nhất: trên Java 17, `publicLookup()` có mode **`UNCONDITIONAL`**, không phải bộ quyền của `lookup()` chỉ đơn giản bị trừ `PRIVATE`. `UNCONDITIONAL` cho phép kiểm tra public ở những package export vô điều kiện, theo ngữ cảnh giả định module có thể đọc được. Public lookup **không có quyền** nhìn sâu vào package bị đóng hoặc chỉ export có điều kiện cho module cụ thể.

Ví dụ thực dụng:

- `publicLookup().findVirtual(String.class, "toUpperCase", MethodType.methodType(String.class))` có thể tạo handle tới phương thức public của `String` trong package public đã export.
- `publicLookup()` **không** được gọi một `private static` method của class bất kỳ.
- Một class khai báo `public` nhưng nằm trong package **không export vô điều kiện** của named module vẫn không tự động truy cập được qua public lookup.
- Không thể truyền public lookup vào `privateLookupIn(...)` để “nâng” quyền private; public lookup thiếu cả `PRIVATE` và `MODULE`.

`publicLookup().lookupClass()` thường quy ước là `Object.class`, nhưng lookup class này **không trao đặc quyền** truy cập internals của `java.lang.Object`. Quyền vẫn do mode của lookup quyết định.

### 4.1. So sánh nhanh

| Thuộc tính | `MethodHandles.lookup()` | `MethodHandles.publicLookup()` |
| --- | --- | --- |
| Được gắn với | Class **đang gọi** `lookup()` | Ngữ cảnh public tối thiểu, lookup class quy ước là `Object` |
| Quyền private của class gọi / nestmate | Có khi Java access hợp lệ | Không |
| Method public thuộc public class trong package export vô điều kiện | Có nếu class và module tương ứng accessible trong ngữ cảnh caller | Có |
| Method public trong package chỉ export có điều kiện | Có **nếu** module caller được export tới và các điều kiện đọc module hợp lệ | Không nhờ unqualified export, vì package không export tới mọi module |
| Quyền package-private / protected | Có khi điều kiện Java access phù hợp | Không |
| `ORIGINAL` / `UNCONDITIONAL` | Có `ORIGINAL` khi tạo trực tiếp bằng `lookup()` | Có `UNCONDITIONAL` |
| `hasFullPrivilegeAccess()` | `true` với lookup gốc | `false` |
| Chia sẻ cho plugin không tin cậy | Rủi ro cao, vì cấp ngữ cảnh truy cập của caller | Ít quyền hơn, nhưng vẫn cần cân nhắc capability và dữ liệu có thể gọi |

**Lưu ý:** “public” trong Java không có nghĩa là bỏ qua JPMS. Một thành viên public của public class vẫn có thể không accessible từ module khác nếu package không được export đúng cách.

## 5. Các access mode của `Lookup`

Các hằng được khai báo trong `MethodHandles.Lookup`. `lookupModes()` trả về **bit mask**, không phải số thứ tự hay mức độ quyền tuyến tính. Một lookup có thể có nhiều bit; việc đọc từng bit phải dùng phép AND bitwise:

```java
boolean mayAccessPrivate =
        (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
```

Đây là đoạn minh họa bên trong code đã có biến `lookup`. Có bit `PRIVATE` là điều kiện về **loại quyền**, chưa đảm bảo một member private của lớp tùy ý accessible; còn phụ thuộc lookup class, nestmates, module, package và các kiểm tra liên quan.

| Mode | Ý nghĩa thực tế trong Java 17 | Điều **không** được suy ra |
| --- | --- | --- |
| `PUBLIC` | Khả năng truy cập member/type public trong ngữ cảnh module và access check của lookup. | Không bỏ qua `exports` / module readability. |
| `PRIVATE` | Truy cập private phù hợp với lookup class và nestmate; là thành phần của full privilege. | Không truy cập private của mọi class tùy ý. |
| `PROTECTED` | Truy cập protected trong phạm vi Java cho phép, kể cả một số trường hợp subclass. | Không được gọi protected của mọi class; method instance còn có ràng buộc kiểu receiver. |
| `PACKAGE` | Khả năng truy cập package-private trong **runtime package** phù hợp. | Cùng chuỗi tên package nhưng khác class loader/module không mặc nhiên là cùng runtime package. |
| `MODULE` | Giữ ngữ cảnh xác thực trong module của lookup class, có thể truy cập public type cùng module ngay cả khi package không export ra ngoài; kết hợp `PRIVATE` cho full privilege. | Không có nghĩa là private access của toàn bộ mọi class trong module. |
| `UNCONDITIONAL` | Quyền public theo quy tắc export vô điều kiện, giả định readability; là mode của `publicLookup()`. | Không bao gồm `PRIVATE` / `MODULE` và không đọc private member. |
| `ORIGINAL` | Dấu nguồn gốc lookup được tạo cho caller thực sự (hoặc bối cảnh VM đặc biệt), có vai trò ở các API đòi provenance. | Không phải “siêu quyền” để vượt mọi kiểm tra truy cập. |

### 5.1. Kiểm tra quyền đúng cách

- `lookupModes()` phù hợp khi cần giải thích/giới hạn capability. Luôn so sánh bằng **bit mask**, không so sánh một con số hardcode với “mức quyền”.
- `hasFullPrivilegeAccess()` kiểm tra lookup có **cả `PRIVATE` và `MODULE`**. Không đồng nhất với `ORIGINAL`: `privateLookupIn` có thể trả lookup có full privilege trong cùng module nhưng **không** có `ORIGINAL`.
- Xác định quyền thực tế bằng cách thử lookup **member chính xác** và xử lý `IllegalAccessException` đúng chỗ; chỉ nhìn bit `PRIVATE` chưa đủ cho một class bất kỳ.
- `lookupClass()` và `previousLookupClass()` giúp giải thích ngữ cảnh lookup, đặc biệt khi lookup đã chuyển qua các module khác nhau.

Không nên viết mã giả định `lookupModes()` của mọi JVM luôn là một giá trị nguyên nhất định rồi nhánh theo số đó. Các hằng `Lookup.PUBLIC`, v.v. mới là cách giao tiếp trực tiếp với API.

## 6. Ví dụ đầy đủ 1 — tra cứu public/private, `in`, `privateLookupIn` và giảm quyền

Ví dụ sau cố tình đặt `Vault` và `LookupAccessDemo` thành **hai top-level class khác nhau** trong cùng source file. Cả hai thuộc unnamed module khi chạy kiểu classpath, nhưng **không phải nestmate** của nhau; điều này giúp thấy rõ việc `Lookup.in(Vault.class)` không cấp private access cho `Vault`.

Tạo file **`LookupAccessDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

class Vault {
    private static String pin() {
        return "8246";
    }
}

public class LookupAccessDemo {
    private static String secret() {
        return "PRIVATE";
    }

    public static String greeting() {
        return "PUBLIC";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup local = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
        MethodType noArgsString = MethodType.methodType(String.class);

        System.out.println("caller is demo: "
                + (local.lookupClass() == LookupAccessDemo.class));
        System.out.println("caller has private: "
                + ((local.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        System.out.println("public has unconditional: "
                + ((publicOnly.lookupModes()
                        & MethodHandles.Lookup.UNCONDITIONAL) != 0));
        System.out.println("public has private: "
                + ((publicOnly.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));

        MethodHandle secretHandle = local.findStatic(
                LookupAccessDemo.class, "secret", noArgsString);
        System.out.println("own private: " + (String) secretHandle.invokeExact());

        try {
            publicOnly.findStatic(LookupAccessDemo.class, "secret", noArgsString);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("public lookup private: denied");
        }

        MethodHandle publicHandle = publicOnly.findStatic(
                LookupAccessDemo.class, "greeting", noArgsString);
        System.out.println("public method: " + (String) publicHandle.invokeExact());

        MethodHandles.Lookup moved = local.in(Vault.class);
        System.out.println("in(Vault) has private: "
                + ((moved.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        try {
            moved.findStatic(Vault.class, "pin", noArgsString);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("in(Vault) private: denied");
        }

        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(Vault.class, local);
        MethodHandle pin = deep.findStatic(Vault.class, "pin", noArgsString);
        System.out.println("privateLookupIn: " + (String) pin.invokeExact());

        MethodHandles.Lookup reduced =
                local.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        System.out.println("reduced has private: "
                + ((reduced.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        System.out.println("original retains private: "
                + ((local.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
    }
}
```

Biên dịch với API Java 17+ và chạy:

```bash
javac -encoding UTF-8 --release 17 LookupAccessDemo.java
java LookupAccessDemo
```

Kết quả stdout:

```text
caller is demo: true
caller has private: true
public has unconditional: true
public has private: false
own private: PRIVATE
public lookup private: denied
public method: PUBLIC
in(Vault) has private: false
in(Vault) private: denied
privateLookupIn: 8246
reduced has private: false
original retains private: true
```

**Đọc kết quả theo từng bước:**

1. `local` được tạo ngay trong `LookupAccessDemo.main`, nên lookup class là `LookupAccessDemo` và có private access để tạo handle cho `secret()`.
2. `publicOnly` chỉ được tìm member public hợp lệ. Tìm `secret()` gây `IllegalAccessException` **khi tạo handle**, trước khi có lời gọi; tìm `greeting()` thành công.
3. `local.in(Vault.class)` đổi lookup class sang `Vault` nhưng **mất `PRIVATE`** vì `Vault` là top-level class khác. Nó không thể tạo handle tới `Vault.pin()`.
4. `privateLookupIn(Vault.class, local)` kiểm tra quyền của `local` và điều kiện module rồi tạo lookup mang quyền private trên `Vault`. Ở ví dụ cùng unnamed module này, việc đọc `pin()` hợp lệ.
5. `dropLookupMode(PRIVATE)` trả **lookup mới** ít quyền hơn. `local` ban đầu vẫn giữ quyền, minh họa tính bất biến của các capability lookup.

Trong mã thực tế, `throws Throwable` ở `main` để demo ngắn; khi tích hợp thư viện hãy phân loại `NoSuchMethodException`, `IllegalAccessException`, `WrongMethodTypeException` và ngoại lệ do method đích ném. `invokeExact` cần chữ ký tại call site **khớp chính xác** với kiểu của handle: ở đây method trả `String` và không nhận tham số, nên ép kiểu `(String)` trước `invokeExact()` giúp compiler xác định return type đúng.

## 7. `Lookup.in(target)`: thay ngữ cảnh nhưng không tự tăng quyền

`Lookup.in(Class<?> newLookupClass)` trả lookup mới có lookup class được chỉ định. Nó chỉ có thể **giữ nguyên hoặc giảm** khả năng truy cập từ lookup ban đầu. Quy tắc quan trọng theo Javadoc Java 17:

- Đổi sang class khác => mất `ORIGINAL`.
- Sang module khác => mất `MODULE`.
- Sang package khác => mất `PACKAGE` và `PROTECTED` theo quy tắc package.
- Sang class không cùng phạm vi **package member/nest** thích hợp => mất `PRIVATE` (không thể “mượn private” của class mới).
- Nếu class mới hoàn toàn không accessible với lookup cũ => có thể mất mọi mode.
- Khi chuyển qua nhiều module, `previousLookupClass()` giúp kiểm tra readability; “nhảy” sang module thứ ba có thể làm mất toàn bộ quyền.

**Điều quan trọng:** `in(target)` không phải cách mở private member trên class khác. Nó thay đổi **điểm nhìn**, đồng thời giảm quyền để tránh khuếch đại capability. Khi thực sự có nhu cầu truy cập private class khác, xem `privateLookupIn` và điều kiện JPMS ở mục 9.

### 7.1. Những lỗi khi dùng `in`

- Lấy `MethodHandles.lookup().in(Target.class)` rồi cho rằng có mọi quyền private của `Target`.
- So sánh class chỉ bằng tên package, bỏ qua class loader và module.
- Cho rằng `in` vào package exported sẽ khôi phục `PACKAGE`/`PRIVATE` từng mất. **Quyền đã mất không tự phục hồi** bằng một lần `in` khác.
- Xem `Lookup.in` là “chỉ đổi tên class” mà không kiểm tra lại `lookupModes()`; cách đổi context có thể thay đổi mức truy cập và kết quả `find...`.

## 8. `dropLookupMode(mode)`: giảm quyền có chủ đích

`dropLookupMode(int modeToDrop)` tạo lookup với ít quyền hơn, thuận tiện khi framework cần chuyển một phần capability cho code ít tin cậy hơn. Không cần tự lắp một `Lookup` bằng cách phản chiếu constructor nội bộ (JDK không cung cấp API public để làm việc này).

Điểm khác nhau giữa “bỏ một bit” và “giảm theo quy tắc”:

- `dropLookupMode(PRIVATE)` cũng làm mất `ORIGINAL` và `PROTECTED`; thông thường còn `PUBLIC`, `MODULE`, `PACKAGE`.
- `dropLookupMode(PACKAGE)` làm mất cả `PACKAGE` và `PRIVATE` (cùng với `ORIGINAL`/`PROTECTED`), vì private access không thể giữ hợp lệ khi bỏ package access theo quy tắc API.
- `dropLookupMode(MODULE)` còn loại `MODULE`, `PACKAGE` và `PRIVATE`; lookup thông thường chỉ còn public có kiểm tra module.
- `dropLookupMode(PUBLIC)` từ lookup thông thường làm mất mọi access mode.
- `publicLookup().dropLookupMode(UNCONDITIONAL)` cũng tạo lookup không còn quyền truy cập.

Với lookup không phải public lookup, thao tác `dropLookupMode` luôn làm mất `ORIGINAL` và `PROTECTED`, kể cả khi mode yêu cầu bỏ là mode khác. Vì vậy **đừng tự dự đoán kết quả bằng biểu thức `oldModes & ~mode`**; Javadoc định nghĩa các quy tắc phụ thuộc giữa các mode.

Chỉ được truyền **một hằng mode hợp lệ** (`PUBLIC`, `MODULE`, `PACKAGE`, `PROTECTED`, `PRIVATE`, `ORIGINAL` hoặc `UNCONDITIONAL`). Dùng giá trị không hợp lệ hay cố truyền tập hợp OR nhiều mode có thể gây `IllegalArgumentException`. Có thể gọi liên tiếp nhiều lần nếu muốn giảm nhiều loại quyền, nhưng phải chấp nhận các quy tắc phụ thuộc này.

**Lưu ý về least privilege:** ngay cả lookup đã giảm quyền cũng là capability. Nếu framework chỉ cần cho extension gọi một method được cho phép, cách thường rõ ràng hơn là **giữ Lookup trong trusted code và trao riêng một `MethodHandle` đã kiểm soát** hoặc một interface hẹp. Đừng chuyển lookup rộng chỉ để tiết kiệm vài dòng mã kết nối.

## 9. `privateLookupIn(target, caller)` và JPMS

`MethodHandles.privateLookupIn(Target.class, callerLookup)` tạo lookup mới hướng vào `Target`, **có khả năng private access** của target sau khi xác minh điều kiện. Đây là API cho thư viện/framework cần deep access hợp pháp, không phải “bypass” không điều kiện.

### 9.1. Điều kiện cần

Với `callerLookup`:

1. Lookup caller phải có **cả `PRIVATE` và `MODULE`** — tức `hasFullPrivilegeAccess()` là `true`.
2. `Target.class` phải là class/interface phù hợp, không phải kiểu primitive, `void` hoặc array.
3. Nếu target và caller nằm **cùng module**, API có thể trả lookup có full privilege trên target (nhưng **không** có `ORIGINAL`).
4. Nếu target nằm **module khác**, module của caller phải **reads** target module và module target phải **opens** package chứa target tới module caller.
5. Sau khi chuyển qua module khác, lookup thu được có `PRIVATE` nhưng **không có `MODULE`**; vì vậy không thể tái sử dụng nó để thực hiện lần deep lookup xuyên module tiếp theo theo cách tương tự.

Nếu quyền không đủ, `privateLookupIn` ném `IllegalAccessException`. Không nên “sửa” bằng cách tự động bật thêm `--add-opens` trên mọi package trong production; thay vào đó, thiết kế interface public, exported/opened package theo hợp đồng hoặc module integration rõ ràng.

### 9.2. Khác nhau giữa `exports` và `opens`

| Khai báo trong `module-info.java` | Ý nghĩa chính | Tác động |
| --- | --- | --- |
| `exports api;` | Mở API public của package cho **mọi module** để truy cập thông thường. | Phù hợp cho publicLookup nếu class và member public và các điều kiện khác thỏa mãn. |
| `exports api to consumer;` | Chỉ export public API tới các module được nêu. | Public lookup theo `UNCONDITIONAL` **không** xem đây là unqualified export. |
| `opens internal to tool;` | Cho phép **deep reflection** tới package đối với module `tool`. | Có thể cho phép `privateLookupIn` xuyên module nếu có readability và quyền caller. |
| `opens internal;` | Deep reflection tới package cho các module khác, không giới hạn theo danh sách cụ thể. | Rộng hơn mức cần thiết nếu chỉ một tool/framework phải đọc private member. |
| `requires core;` | Module caller khai báo khả năng đọc module `core`. | Cần thiết cho cross-module `privateLookupIn` cùng `opens` của target. |

Ví dụ **cấu hình module minh họa**, gồm **hai tệp `module-info.java` riêng**, không phải một file compile độc lập:

```java
// Module core.inventory:
module core.inventory {
    exports inventory.api;
    opens inventory.internal to tools.reader;
}

// Module tools.reader:
module tools.reader {
    requires core.inventory;
}
```

Phần logic của `tools.reader` khi đã có đối tượng `Class<?> targetType` biểu thị class trong package `inventory.internal`:

```java
// Đoạn minh họa bên trong một class thuộc module tools.reader:
MethodHandles.Lookup own = MethodHandles.lookup();
MethodHandles.Lookup target =
        MethodHandles.privateLookupIn(targetType, own);
```

Trong đoạn trên, `MethodHandles` cần import `java.lang.invoke.MethodHandles`. Với target class public nhưng package không exported, module reader có thể nhận `Class<?>` qua cơ chế khám phá phù hợp mà không cần code import trực tiếp class của package internal. Điều kiện **reads + opens** quyết định khả năng deep lookup; chỉ có `requires` hoặc chỉ có `exports` không thay thế cho `opens`.

Khi ứng dụng chạy trên **classpath/unnamed module**, nhiều thao tác cùng module có thể thành công mà trong named-module deployment lại bị chặn. Vì vậy phải kiểm thử đúng cách đóng gói, module path, opens/export thực tế. Tùy trường hợp, `--add-opens target.module/pkg=caller.module` có thể hỗ trợ chẩn đoán hoặc tương thích, nhưng không nên coi là thiết kế quyền mặc định.

### 9.3. Khi nào KHÔNG dùng privateLookupIn?

- Nếu member đã **public** và package exported, có thể tạo handle từ lookup hiện có phù hợp mà không cần thêm quyền private.
- Nếu thư viện có API hoặc factory chính thức, nên dùng API đó thay vì buộc package phải `opens`.
- Nếu caller lookup đã bị `dropLookupMode(MODULE)` hoặc `dropLookupMode(PRIVATE)`, `privateLookupIn` sẽ thất bại; nó không phải cách phục hồi quyền đã bỏ.

## 10. Ví dụ đầy đủ 2 — ngữ cảnh `lookup()` nằm ở helper, không nằm ở caller của helper

Một lỗi thiết kế thường gặp là viết phương thức tiện ích trả một lookup rồi cho rằng lookup tự có quyền của lớp **đang gọi phương thức tiện ích**. Ví dụ sau chứng minh sai khác bằng kiểm tra thật.

Tạo file **`CallerContextDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

class LookupFactory {
    static MethodHandles.Lookup provide() {
        return MethodHandles.lookup();
    }
}

public class CallerContextDemo {
    private static String hidden() {
        return "hidden";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup own = MethodHandles.lookup();
        MethodHandles.Lookup fromFactory = LookupFactory.provide();

        System.out.println("own context: "
                + (own.lookupClass() == CallerContextDemo.class));
        System.out.println("factory context: "
                + (fromFactory.lookupClass() == LookupFactory.class));

        MethodType type = MethodType.methodType(String.class);
        System.out.println("own hidden: " + (String) own
                .findStatic(CallerContextDemo.class, "hidden", type)
                .invokeExact());

        try {
            fromFactory.findStatic(CallerContextDemo.class, "hidden", type);
            System.out.println("unreachable");
        } catch (IllegalAccessException expected) {
            System.out.println("factory hidden: denied");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CallerContextDemo.java
java CallerContextDemo
```

Stdout:

```text
own context: true
factory context: true
own hidden: hidden
factory hidden: denied
```

**Giải thích:** `LookupFactory.provide()` tự gọi `MethodHandles.lookup()`, nên kết quả có `LookupFactory` là lookup class, không phải `CallerContextDemo`. Hai lớp cùng package trong ví dụ nhưng khác top-level class và **không phải nestmate**; helper không được mặc nhiên truy cập private method của `CallerContextDemo`.

Muốn một framework truy cập private member của một user class, framework phải có **ngữ cảnh lookup được trao hợp lệ** hoặc dùng `privateLookupIn` với các điều kiện đúng, thay vì giả định helper có thể tự lấy mọi quyền.

## 11. Access check, lỗi kiểu và quyền khác nhau ra sao?

Xét lời gọi:

```java
MethodHandle mh = lookup.findVirtual(
        String.class,
        "substring",
        MethodType.methodType(String.class, int.class));
String result = (String) mh.invokeExact("hello", 2);
```

Đoạn này là **mã minh họa trong phương thức khai báo `lookup`**, giả định đã import `MethodHandle`, `MethodType` và xử lý ngoại lệ. `findVirtual` tạo handle có **receiver đầu tiên** là `String`; kiểu đầy đủ của handle là `(String, int)String`. Kết quả là `"llo"`.

Lưu ý ba tầng độc lập:

1. **Member có tồn tại và chữ ký tìm kiếm đúng?** `findVirtual`/`findStatic` có thể ném `NoSuchMethodException` nếu không tìm thấy method với kiểu phù hợp. `findGetter`/`findSetter` có thể ném `NoSuchFieldException`.
2. **Lookup có quyền tạo handle?** Nếu class/member không accessible trong ngữ cảnh lookup, `find...` ném `IllegalAccessException`; đây là lỗi **tạo handle**, không phải lỗi gọi.
3. **Call site có kiểu khớp handle?** `invokeExact` yêu cầu kiểu chính xác; mismatch có thể ném `WrongMethodTypeException`. `invoke` có thể áp dụng chuyển đổi được hỗ trợ, nhưng không làm mất kiểm tra kiểu cơ bản. Exception do chính method đích ném được truyền qua handle như lỗi thực thi.

**Không nên dùng `catch (Exception) { ... }` rồi coi mọi trường hợp là lỗi quyền.** Tách lỗi cấu hình/tên member, lỗi chính sách truy cập và lỗi kiểu thực thi để dễ chẩn đoán.

## 12. Các tình huống dùng `Lookup` trong framework và plugin

### 12.1. Framework cần gọi public API của provider

Một plugin interface có các method public thuộc module exported. Framework có thể tìm `MethodHandle` bằng lookup đủ quyền public mà không cần mở private API. Tránh khởi đầu bằng `privateLookupIn` khi public API đã đáp ứng yêu cầu.

### 12.2. Serializer/ORM cần đọc private field

Nếu bắt buộc truy cập field private, framework có thể nhận quyền từ module ứng dụng (qualified `opens`) và tạo lookup bằng `privateLookupIn`. Tốt hơn nữa, nếu public accessor hoặc code generation theo hợp đồng khả dụng, có thể giảm nhu cầu deep reflection. Cache `VarHandle`/`MethodHandle` sau khi kiểm tra quyền; không thử mở quyền nhiều lần trong mỗi request.

### 12.3. DSL/dynamic language runtime

Runtime có thể liên kết một tên thao tác lúc chạy thành method handle. `MethodType` biểu diễn chữ ký, `Lookup` xác minh ngữ cảnh và `CallSite`/`invokedynamic` có thể giữ liên kết động. Điều kiện quyền vẫn có hiệu lực; một runtime động không tự được phép gọi private member.

### 12.4. Chia sẻ capability cho extension

Không đưa trực tiếp lookup đầy quyền của core vào API plugin không tin cậy. Dùng lookup ít quyền hơn khi phù hợp, hoặc một interface/handle hẹp chỉ cho phép tác vụ được chấp thuận. Nhớ rằng **đã tạo được private handle thì người nhận handle thường dùng được nó**, ngay cả khi sau đó core dùng một lookup khác ít quyền hơn.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`publicLookup` có bit `PUBLIC` và tất cả public member đều gọi được” | Java 17 publicLookup dùng mode `UNCONDITIONAL`, bị giới hạn bởi unqualified exported packages. | Kiểm tra class public, member public, và JPMS exports. |
| “`lookup()` là quyền admin toàn JVM” | Quyền gắn với class thực sự gọi API và quy tắc truy cập Java. | Xem `lookupClass()`, member target, module. |
| “`lookup.in(Target.class)` lấy được private Target” | `in` chỉ giữ/giảm quyền; khác class có thể mất PRIVATE. | Dùng `privateLookupIn` khi đủ điều kiện hoặc public API. |
| “Bỏ mode chỉ là `mask & ~bit`” | `dropLookupMode` có cascade, làm mất ORIGINAL/PROTECTED và các mode phụ thuộc. | Gọi API chính thức và kiểm tra mode kết quả. |
| “`hasFullPrivilegeAccess()` cho phép đọc private mọi module” | Full privilege gắn ngữ cảnh caller; cross-module còn cần `reads` + `opens`. | Định nghĩa module hợp lệ và xử lý `IllegalAccessException`. |
| “`exports` và `opens` giống nhau” | `exports` phục vụ ordinary public API access; `opens` cho deep reflection. | Chọn khai báo module theo loại truy cập cần thiết. |
| “Đổi `Lookup` quyền sau khi đã phát handle sẽ thu hồi handle cũ” | Access được kiểm tra khi handle được tạo; handle đã phát là capability độc lập. | Bảo vệ/thu hồi ở tầng ứng dụng; không phát hành handle nhạy cảm tùy ý. |
| “Sai kiểu `invokeExact` là lỗi permission” | Sai chữ ký gây `WrongMethodTypeException`, khác với `IllegalAccessException` lúc tra cứu. | Kiểm tra `handle.type()` và caller descriptor. |
| “Factory trả lookup có quyền của code gọi factory” | `lookup()` caller-sensitive theo nơi **thực sự gọi `lookup()`**. | Truyền lookup hợp lệ từ caller nếu API tin cậy yêu cầu. |

Ngoài quyền member, class loading/class visibility, module readability và cấu trúc nestmate đều có thể tác động đến kết quả. Nếu test classpath pass nhưng module path fail, hãy đối chiếu module descriptor trước khi thêm workaround mở rộng quyền.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Khi viết `MethodHandles.lookup()` trong `ServiceA`, lookup có thể gọi private method của `ServiceB` không?

**Đáp:** Không mặc định. Lookup ban đầu thuộc `ServiceA`; private access chỉ theo quan hệ hợp lệ như chính class/nestmates. Nếu `ServiceB` ngoài phạm vi, phải dùng cơ chế khác như `privateLookupIn` và đáp ứng điều kiện.

**Câu 2.** Vì sao `publicLookup()` có thể gọi public method của `String` nhưng không gọi public method của một public class trong package không export?

**Đáp:** Public lookup bị giới hạn vào public classes và members trong package export **vô điều kiện**. Class/member public chưa đủ nếu JPMS chặn package.

**Câu 3.** `lookup.in(Target.class)` khác `privateLookupIn(Target.class, lookup)` ở đâu?

**Đáp:** `in` chuyển ngữ cảnh và chỉ giữ/giảm quyền. `privateLookupIn` cấp lookup mới với private access trên target sau khi kiểm tra full privilege và điều kiện module/opens; nó không phải tự động thành công.

**Câu 4.** Nếu `dropLookupMode(PRIVATE)`, vì sao `ORIGINAL` và `PROTECTED` cũng mất?

**Đáp:** `dropLookupMode` có quy tắc quyền phụ thuộc, không đơn thuần xóa bit được yêu cầu. Javadoc Java 17 xác định việc mất thêm các mode ấy.

**Câu 5.** Trong named module, `privateLookupIn` sang module khác cần gì?

**Đáp:** Caller lookup có `PRIVATE` và `MODULE`; caller module **reads** target module; target module **opens** package chứa target tới caller. Lookup sau khi vượt module không còn `MODULE` hay `ORIGINAL`.

**Câu 6.** Nếu handle private đã được tạo rồi đem gửi sang code khác, việc gọi nó có kiểm tra quyền riêng tư của caller mới nữa không?

**Đáp:** Quyền member đã được kiểm tra ở lúc tạo handle. Người nhận handle có thể gọi trong giới hạn kiểu và hành vi handle; vì vậy không trao private handle hoặc lookup có quyền cao cho code không tin cậy.

## 15. Ghi nhớ

- **`lookup()`:** caller-sensitive, gắn với class thực sự gọi API; lookup gốc có `ORIGINAL` và full privilege trong phạm vi hợp lệ.
- **`publicLookup()`:** capability tối thiểu, mode `UNCONDITIONAL`, chỉ dùng public API của public class trong package export vô điều kiện.
- **Chế độ quyền không phải cấp bậc số học:** `lookupModes()` là bit mask; `PRIVATE`, `PACKAGE`, `PROTECTED`, `MODULE`, `PUBLIC`, `UNCONDITIONAL` và `ORIGINAL` có ý nghĩa riêng.
- **`in` / `dropLookupMode` chỉ giảm quyền.** `privateLookupIn` cấp lookup tới target khi và chỉ khi các điều kiện quyền/module phù hợp.
- **Kiểm tra quyền ở lúc tạo handle**, bảo vệ cả lookup và handle đã tạo. Với module, phân biệt `exports` và `opens`, ưu tiên API ít quyền cần thiết.

### Tài liệu chính thức Java SE 17

- [`MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn` và quy tắc full privilege.
- [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access modes, `in`, `dropLookupMode`, lookupClass/previousLookupClass và module access.
- [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): kiểm tra access khi tạo, kiểu lời gọi, `invokeExact` và `invoke`.
- [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): biểu diễn chữ ký của method handle.
- [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): cấu trúc module, khả năng đọc và quan hệ `exports`/`opens`.
