# 6.8 Đổi ngữ cảnh bằng `Lookup.in`, `dropLookupMode` và `privateLookupIn`

**Ngữ cảnh:** Java Advance → dynamic-runtime → 6. MethodType và Lookup.

Trong `java.lang.invoke`, `MethodHandles.Lookup` quyết định một chương trình được **tạo `MethodHandle` tới thành viên nào**. Khi xây framework, plugin, dependency injection, serializer hoặc runtime adapter, ta thường cần chuyển ngữ cảnh tra cứu từ lớp này sang lớp khác hoặc trao một phần quyền tra cứu cho code khác. Ba API quan trọng là:

- `lookup.in(Target.class)`: đổi **lookup class**, đồng thời có thể giảm quyền theo ranh giới nest/package/module.
- `lookup.dropLookupMode(MODE)`: chủ động **loại bỏ quyền** khỏi một lookup.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)`: xin lookup có quyền **private trên target**, nhưng chỉ nếu quyền gốc và quy tắc module cho phép.

Ba API không đồng nghĩa nhau. **`in` không nâng quyền**, **`dropLookupMode` chỉ giảm quyền**, còn **`privateLookupIn` có thể tạo quyền private trong ngữ cảnh target sau khi kiểm tra tính hợp lệ**. Tất cả ví dụ ở đây dùng Java 17+ và tách biệt rõ code độc lập với snippet.

## 1. Vì sao phải hiểu `Lookup` như một capability?

`MethodHandles.lookup()` trả về một đối tượng mang ngữ cảnh và các quyền tra cứu gắn với **lớp gọi phương thức đó**. Đây là API **caller-sensitive**: gọi trong class `A` có kết quả khác với gọi trong class `B`. Không nên hiểu nó là một đối tượng tiện ích vô trạng thái hoặc một bộ tìm kiếm toàn JVM.

Một `Lookup` lưu các yếu tố chính:

- `lookupClass()`: lớp làm **chủ thể** của phép tra cứu; permission check sẽ dựa vào lớp này.
- `lookupModes()`: bit mask giới hạn các mức quyền mà lookup có thể sử dụng.
- `previousLookupClass()`: lớp tra cứu trước đó ở **module khác** khi lookup đã chuyển qua ranh giới module; có thể là `null`.
- `hasFullPrivilegeAccess()`: thể hiện lookup có cả `PRIVATE` và `MODULE`; đó là điều kiện thiết yếu khi dùng `privateLookupIn`.

Ví dụ, lookup tạo ngay trong `demo.a.LookupDemo` thường có quyền mạnh đối với các thành viên mà `LookupDemo` có quyền truy cập theo Java, kể cả private của chính lớp hoặc nestmates. Nếu giao nguyên lookup đó cho code không tin cậy, bên nhận có thể dùng chính capability đó để lấy handles tới thành viên nhạy cảm trong phạm vi quyền đã cấp.

**Khác với Core Reflection:** Với `MethodHandles.Lookup.findStatic`, `findVirtual`, `findGetter`... quyền truy cập được kiểm tra chủ yếu lúc **tạo direct method handle**. Sau khi handle được tạo hợp lệ, việc `invokeExact` không chạy lại cùng phép kiểm tra quyền theo caller như `java.lang.reflect.Method.invoke`. Vì thế giới hạn quyền phải đặt **trước khi phát hành `Lookup` hoặc `MethodHandle`**, không phải chỉ kiểm tra ở thời điểm gọi.

### Các lookup mode trên Java 17

| Bit | Tên | Ý nghĩa khái quát |
| --- | --- | --- |
| `PUBLIC` | Public mode | Cho phép tra cứu công khai theo visibility, khả năng đọc module và exports phù hợp |
| `PRIVATE` | Private mode | Khả năng truy cập private của lookup class/nestmates và thao tác đặc quyền tương ứng |
| `PROTECTED` | Protected mode | Khả năng protected phù hợp ngữ cảnh kế thừa, có ràng buộc receiver |
| `PACKAGE` | Package mode | Truy cập package-private trong runtime package phù hợp |
| `MODULE` | Module mode | Xác thực ngữ cảnh module gốc; hỗ trợ tìm public types cùng module và điều kiện cho deep lookup |
| `ORIGINAL` | Original mode | Đánh dấu lookup do caller gốc tạo (`lookup()`) hoặc bootstrap do JVM cấp; quyền đặc biệt, chẳng hạn caller-sensitive |
| `UNCONDITIONAL` | Unconditional mode | Đặc trưng của `publicLookup()`; truy cập public members của public types trong package được export **không điều kiện**, không cần module readability như lookup thông thường |

`PRIVATE` và `MODULE` là **hai quyền khác nhau**. Một lookup có `PRIVATE` nhưng mất `MODULE` vẫn có thể tạo handle tới private members trong một số ngữ cảnh đã được cấp, nhưng **không dùng chính lookup đó để xin deep lookup sang lớp khác qua `privateLookupIn`**.

`ORIGINAL` không phải là "một mức public cao hơn"; nó xác nhận nguồn gốc caller. `MethodHandles.publicLookup()` có `UNCONDITIONAL`, **không có `PUBLIC` bit** theo `lookupModes()`, dù vẫn tra cứu được nhiều phương thức public trong các package được export vô điều kiện. Vì vậy không kiểm tra "được gọi public hay không" bằng duy nhất biểu thức `(lookup.lookupModes() & PUBLIC) != 0` khi có `publicLookup()`.

## 2. `Lookup.in(Target.class)`: đổi lớp tra cứu, không tăng quyền

Chữ ký:

```java
MethodHandles.Lookup changed = original.in(Target.class);
```

`changed.lookupClass()` là `Target.class`, nhưng `changed` **không thể có nhiều capability hơn `original`**. JVM điều chỉnh các access modes dựa vào mối quan hệ giữa lookup class cũ và target:

| Quan hệ khi chuyển bằng `in` | Hệ quả cần nhớ |
| --- | --- |
| Gọi `in` trên chính lookup class hiện tại | Không thay đổi lớp; API có thể trả chính lookup ban đầu |
| Đổi sang class khác **trong cùng nest** | Có thể giữ `PRIVATE`; `ORIGINAL` bị mất khi không còn là lớp gốc |
| Đổi sang class cùng runtime package nhưng **khác nest** | Mất `PRIVATE`; có thể giữ `PACKAGE`, `MODULE` và public access |
| Đổi sang class ở package khác nhưng cùng module | Mất `PRIVATE` và `PACKAGE`; `MODULE` có thể còn; khả năng truy cập public vẫn được kiểm tra |
| Đổi sang class ở module khác | Mất `MODULE`; ghi nhận `previousLookupClass`; quyền public được kiểm tra theo cả hai module |
| Đổi sang class target mà lookup không được phép truy cập | Các access modes có thể về **0**, kể cả quyền public |

Bảng mô tả những trường hợp điển hình với lookup ban đầu đầy đủ; các mode đã bị drop trước đó không tự xuất hiện lại. Đặc biệt, chuyển sang subclass ở package khác **không tự cho lookup mới quyền private của subclass**.

### Nestmates, cùng package nhưng khác nest

Java 11+ định nghĩa nest: các class thuộc cùng nest có quyền truy cập private của nhau. Một nested class được tạo bên trong outer class thường là nestmate của outer class. Trong ví dụ ở mục 5, `LookupDemo` và `LookupDemo.NestedTarget` cùng nest, nên `root.in(NestedTarget.class)` **vẫn có `PRIVATE`**. Ngược lại, `Peer` là top-level class riêng trong cùng package: `root.in(Peer.class)` **mất `PRIVATE`** nhưng vẫn giữ `PACKAGE`.

Cần phân biệt nestmates với hai class chỉ dùng cùng tên package; **cùng runtime package chưa phải cùng nest**. Nếu code cần private access vào một class cùng package nhưng khác nest, hãy đánh giá `privateLookupIn` theo điều kiện ở mục 4.

### Di chuyển xuyên module và `previousLookupClass()`

Giả sử `Client` thuộc module `beta` và `Gateway` thuộc module `alpha`. Khi gọi `lookup.in(Gateway.class)`:

- Lookup class mới là `Gateway`.
- `MODULE` bị loại bỏ.
- `previousLookupClass()` ghi nhận `Client`, lớp xuất phát từ module `beta`.
- `PUBLIC` access (nếu còn) chịu điều kiện cả phía `alpha` và phía `beta` có thể truy cập công khai cùng loại tương ứng.

Nếu một lookup đã chuyển giữa hai module rồi lại chuyển sang **module thứ ba** không thuộc cặp trước đó, Java 17 có thể loại bỏ **toàn bộ access modes**. Việc gọi liên tiếp `in` **không phải** chuỗi để thu thêm quyền hoặc né điều kiện module. `Lookup.in` với `int.class`, `void.class` hoặc array class ném `IllegalArgumentException`; truyền `null` ném `NullPointerException`.

## 3. `dropLookupMode(MODE)`: giảm quyền có kiểm soát

Chữ ký:

```java
MethodHandles.Lookup restricted =
        original.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Phương thức giữ nguyên `lookupClass()` và trả lookup chỉ có thể có **ít quyền hơn**. Nó không can thiệp đến quyền của lookup gốc, không sửa modifier của class hoặc member và không xóa những `MethodHandle` đã cấp trước đó.

**Các mode không hoàn toàn độc lập khi bị loại bỏ.** Trên Java 17, với lookup thường (không phải `publicLookup()`), việc drop một bit có thể kéo theo drop các bit khác. Ngoài bit được yêu cầu, `PROTECTED` và `ORIGINAL` **luôn bị xóa** trong kết quả của `dropLookupMode`:

| Yêu cầu | Bit còn lại điển hình từ lookup đầy đủ |
| --- | --- |
| `dropLookupMode(PROTECTED)` | `PRIVATE + PACKAGE + MODULE + PUBLIC` |
| `dropLookupMode(PRIVATE)` | `PACKAGE + MODULE + PUBLIC` |
| `dropLookupMode(PACKAGE)` | `MODULE + PUBLIC` |
| `dropLookupMode(MODULE)` | `PUBLIC` |
| `dropLookupMode(PUBLIC)` | Không còn access mode |
| `dropLookupMode(ORIGINAL)` | `PRIVATE + PACKAGE + MODULE + PUBLIC` |

Đây là các trạng thái điển hình khi **bắt đầu từ lookup đầy đủ**; nếu lookup đã suy giảm, không có phép biến đổi nào "khôi phục" bit đã mất. Trường hợp đặc biệt: `publicLookup()` chỉ có `UNCONDITIONAL`; `dropLookupMode(UNCONDITIONAL)` từ lookup ấy tạo lookup không còn quyền tra cứu.

Vì sao `dropLookupMode(PACKAGE)` cũng xóa `PRIVATE`? Giữ private access với ngữ cảnh đã mất package access có thể làm rò rỉ capability không mong đợi. Tương tự, drop `MODULE` phải bỏ các mode mang quyền từ module/package/private. Đây là **hạ quyền theo nhóm** mà API cam kết, không phải bug về toán bit.

### Ví dụ an toàn khi cấp quyền cho một thành phần

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup publicOnly =
        full.dropLookupMode(MethodHandles.Lookup.MODULE);
```

Trong snippet trên, `publicOnly` giữ `lookupClass` của caller nhưng mất `PRIVATE`, `PACKAGE`, `MODULE`, `PROTECTED` và `ORIGINAL`. Nó hữu ích khi một subsystem chỉ nên tìm members công khai phù hợp. Nếu chỉ muốn cho code khác tra cứu public API được export **vô điều kiện** mà không mang ngữ cảnh module của caller, cân nhắc `MethodHandles.publicLookup()`.

**Lưu ý:** Dropping bit không thu hồi các method handle **đã được tạo**. Nếu trước đó `full.findStatic(Secret.class, "hidden", ...)` đã trả một `MethodHandle` hợp lệ, handle ấy vẫn có thể gọi được sau khi một lookup khác đã bị giảm quyền. Cần kiểm soát cả những **handle** và những **lookup** được chia sẻ.

## 4. `MethodHandles.privateLookupIn(Target.class, callerLookup)`

Chữ ký:

```java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
```

API này cấp một lookup mà `lookupClass()` là `Target` và có `PRIVATE` trên target, **sau khi** kiểm tra các điều kiện. Trên Java 17, caller lookup phải có cả `PRIVATE` và `MODULE` (full privilege access), và target phải là class/interface hợp lệ, **không** phải primitive, void hoặc array.

### Trong cùng module

Nếu caller lookup có full privilege và target nằm trong **cùng module**, `privateLookupIn` có thể trả lookup có private capability trên target, ngay cả khi target ở package khác hoặc khác nest. Không cần `opens` sang module khác trong trường hợp này. Kết quả có thể có `PRIVATE`, `PACKAGE`, `MODULE`, `PUBLIC` và `PROTECTED`, nhưng không có `ORIGINAL`.

Ở ví dụ mục 5, `root.in(Peer.class)` mất `PRIVATE`, còn `MethodHandles.privateLookupIn(Peer.class, root)` nhận lại **lookup được cấp private access riêng trên `Peer`**, bởi vì `root` là lookup đầy đủ và cả hai class nằm trong unnamed module.

### Khác module

Khi target nằm ở module khác, cần đồng thời:

1. Caller lookup có `PRIVATE` **và** `MODULE`.
2. Module của caller **reads** module của target.
3. Module của target **opens** package chứa target đến module của caller (không chỉ `exports` public API).
4. Target là class/interface hợp lệ; khi có môi trường SecurityManager áp dụng, kiểm tra bảo mật phải cho phép.

Khi cấp thành công xuyên module, lookup kết quả có `PRIVATE` trên target và ghi `previousLookupClass()` là lớp nguồn, nhưng **mất `MODULE`**. Vì thế không thể tiếp tục gọi `privateLookupIn` từ chính lookup kết quả để chuyển quyền sang target khác: thiếu `MODULE`. Đây là một ranh giới chống chuyển tiếp quyền sâu không kiểm soát.

`privateLookupIn` ném `IllegalAccessException` khi điều kiện quyền/module không thỏa. Truyền primitive, void hoặc array làm target gây `IllegalArgumentException`; truyền `null` có thể gây `NullPointerException`. Gọi `privateLookupIn` bằng `MethodHandles.publicLookup()` sẽ thất bại vì thiếu `PRIVATE` và `MODULE`.

### `exports` và `opens` không tương đương

- `exports p`: cho phép module khác biên dịch/truy cập **public API** của package `p` (với module readability phù hợp).
- `opens p to m`: cho phép module `m` truy cập sâu bằng reflection vào package `p` theo điều kiện API; không biến mọi private member thành public API Java.
- `--add-opens alpha/alpha.internal=beta`: tùy chọn khởi chạy có thể mở package của module `alpha` cho module `beta` để chẩn đoán hoặc tích hợp. Dự án thực tế nên ưu tiên `opens ... to ...` được thiết kế có chủ đích.
- `exports` đơn thuần **không đủ** để `privateLookupIn` sang một public class thuộc module khác khi package chưa mở. Thí nghiệm mục 6 chứng minh trường hợp này.

## 5. Demo Java 17 độc lập: đổi lớp, drop quyền và mở quyền trong cùng module

**Mục tiêu:** so sánh cùng nest với cùng package khác nest; kiểm tra `PRIVATE`, `PACKAGE`, `MODULE`, `PUBLIC`, `ORIGINAL`; khẳng định lookup đã drop không thể cấp private access; xác minh handle đã tạo trước khi drop vẫn gọi được.

Tạo ba file:

```text
lookup-demo/
└── demo/
    ├── a/
    │   ├── LookupDemo.java
    │   └── Peer.java
    └── b/
        └── PublicPeer.java
```

Ba class nằm trên **classpath** (unnamed module). Đặc biệt, `NestedTarget` là nested static class của `LookupDemo`, còn `Peer` là một top-level class riêng trong `demo.a`.

### File `demo/a/LookupDemo.java`

```java
package demo.a;

import demo.b.PublicPeer;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles.Lookup;

import static java.lang.invoke.MethodHandles.Lookup.*;

public class LookupDemo {
    public static class NestedTarget {
        private static String hidden() { return "nested-secret"; }
        static String packageValue() { return "nested-package"; }
        public static String shown() { return "nested-public"; }
    }

    private static boolean has(Lookup l, int bit) {
        return (l.lookupModes() & bit) != 0;
    }

    private static void show(String label, Lookup l) {
        System.out.println(label + " class=" + l.lookupClass().getSimpleName()
            + " PRI=" + has(l, PRIVATE)
            + " PAC=" + has(l, PACKAGE)
            + " MOD=" + has(l, MODULE)
            + " PUB=" + has(l, PUBLIC)
            + " ORI=" + has(l, ORIGINAL));
    }

    private static void probe(String label, Lookup l, Class<?> owner, String name) {
        try {
            MethodHandle m = l.findStatic(owner, name, MethodType.methodType(String.class));
            System.out.println(label + "=" + (String) m.invokeExact());
        } catch (IllegalAccessException ex) {
            System.out.println(label + "=IllegalAccessException");
        } catch (NoSuchMethodException ex) {
            System.out.println(label + "=NoSuchMethodException");
        } catch (Throwable ex) {
            throw new RuntimeException(ex);
        }
    }

    public static void main(String[] args) throws Throwable {
        Lookup root = MethodHandles.lookup();
        Lookup sameNest = root.in(NestedTarget.class);
        Lookup samePackage = root.in(Peer.class);
        Lookup otherPackage = root.in(PublicPeer.class);
        Lookup hiddenTarget = root.in(PublicPeer.hiddenClass());
        Lookup noPrivate = root.dropLookupMode(PRIVATE);
        Lookup noPackage = root.dropLookupMode(PACKAGE);
        Lookup noModule = root.dropLookupMode(MODULE);
        Lookup noPublic = root.dropLookupMode(PUBLIC);

        show("root", root);
        show("same-nest", sameNest);
        show("same-package", samePackage);
        show("other-package", otherPackage);
        show("in-inaccessible", hiddenTarget);
        show("drop-private", noPrivate);
        show("drop-package", noPackage);
        show("drop-module", noModule);
        show("drop-public", noPublic);

        MethodType str = MethodType.methodType(String.class);
        MethodHandle acquiredBeforeDrop = root.findStatic(NestedTarget.class, "hidden", str);
        probe("same-nest private", sameNest, NestedTarget.class, "hidden");
        probe("same-package peer-private", samePackage, Peer.class, "hidden");
        probe("same-package peer-package", samePackage, Peer.class, "packageValue");
        probe("other-package public", otherPackage, PublicPeer.class, "shown");
        probe("other-package peer-package", otherPackage, PublicPeer.class, "packageValue");
        probe("dropped-private secret", noPrivate, NestedTarget.class, "hidden");
        System.out.println("existing-handle=" + (String) acquiredBeforeDrop.invokeExact());

        Lookup delegated = MethodHandles.privateLookupIn(Peer.class, root);
        show("privateLookupIn-peer", delegated);
        probe("privateLookupIn peer-private", delegated, Peer.class, "hidden");
        try {
            MethodHandles.privateLookupIn(Peer.class, noPrivate);
        } catch (IllegalAccessException ex) {
            System.out.println("privateLookupIn after drop-private=IllegalAccessException");
        }
        try {
            MethodHandles.privateLookupIn(Peer.class, noModule);
        } catch (IllegalAccessException ex) {
            System.out.println("privateLookupIn after drop-module=IllegalAccessException");
        }
        try {
            root.in(int.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("in-primitive=IllegalArgumentException");
        }

        Lookup publicLookup = MethodHandles.publicLookup();
        System.out.println("publicLookup UNCOND=" + has(publicLookup, UNCONDITIONAL)
            + " PUB=" + has(publicLookup, PUBLIC));
        probe("publicLookup nested", publicLookup, NestedTarget.class, "shown");
        probe("publicLookup peer-package", publicLookup, Peer.class, "packageValue");
    }
}
```

### File `demo/a/Peer.java`

```java
package demo.a;

public class Peer {
    private static String hidden() { return "peer-secret"; }
    static String packageValue() { return "peer-package"; }
}
```

### File `demo/b/PublicPeer.java`

```java
package demo.b;

class HiddenClass {
    public static String shown() { return "hidden-public"; }
}

public class PublicPeer {
    public static String shown() { return "other-public"; }
    static String packageValue() { return "other-package"; }
    public static Class<?> hiddenClass() { return HiddenClass.class; }
}
```

**Biên dịch và chạy** từ thư mục `lookup-demo/`. Dùng explicit file paths để lệnh cũng dễ chạy trong Windows PowerShell:

```bash
javac --release 17 -encoding UTF-8 -d out demo/a/LookupDemo.java demo/a/Peer.java demo/b/PublicPeer.java
java -cp out demo.a.LookupDemo
```

**Stdout chính xác:**

```text
root class=LookupDemo PRI=true PAC=true MOD=true PUB=true ORI=true
same-nest class=NestedTarget PRI=true PAC=true MOD=true PUB=true ORI=false
same-package class=Peer PRI=false PAC=true MOD=true PUB=true ORI=false
other-package class=PublicPeer PRI=false PAC=false MOD=true PUB=true ORI=false
in-inaccessible class=HiddenClass PRI=false PAC=false MOD=false PUB=false ORI=false
drop-private class=LookupDemo PRI=false PAC=true MOD=true PUB=true ORI=false
drop-package class=LookupDemo PRI=false PAC=false MOD=true PUB=true ORI=false
drop-module class=LookupDemo PRI=false PAC=false MOD=false PUB=true ORI=false
drop-public class=LookupDemo PRI=false PAC=false MOD=false PUB=false ORI=false
same-nest private=nested-secret
same-package peer-private=IllegalAccessException
same-package peer-package=peer-package
other-package public=other-public
other-package peer-package=IllegalAccessException
dropped-private secret=IllegalAccessException
existing-handle=nested-secret
privateLookupIn-peer class=Peer PRI=true PAC=true MOD=true PUB=true ORI=false
privateLookupIn peer-private=peer-secret
privateLookupIn after drop-private=IllegalAccessException
privateLookupIn after drop-module=IllegalAccessException
in-primitive=IllegalArgumentException
publicLookup UNCOND=true PUB=false
publicLookup nested=nested-public
publicLookup peer-package=IllegalAccessException
```

**Giải thích kết quả theo cơ chế:**

1. `root` tạo bằng `MethodHandles.lookup()` ngay trong `LookupDemo`. Nó có đầy đủ `PRI`/`PAC`/`MOD`/`PUB`/`ORI`, ngoài bit `PROTECTED` không được in trong bảng.
2. `sameNest` chuyển đến `NestedTarget`, vốn là nestmate của `LookupDemo`. Nó giữ `PRIVATE` và truy cập thành công `NestedTarget.hidden()`; do đổi lookup class, `ORIGINAL=false`.
3. `samePackage` chuyển đến `Peer`: không cùng nest nên `PRI=false`, nhưng cùng runtime package nên `PAC=true`. `Peer.hidden()` bị `IllegalAccessException`; `Peer.packageValue()` được gọi.
4. `otherPackage` cùng unnamed module nhưng khác package, nên `PAC=false` và `MOD=true`. Nó tìm được `PublicPeer.shown()` công khai, nhưng không tìm được method package-private.
5. `in-inaccessible` là lookup hướng về `HiddenClass` package-private thuộc package khác. Target không thể truy cập bằng ngữ cảnh lookup ấy nên tất cả modes thành `false`. `in` không ném `IllegalAccessException` ở đây; nó trả một lookup bị giới hạn.
6. `drop-private`, `drop-package`, `drop-module` và `drop-public` cho thấy bit cascade khi hạ quyền. Sau drop `PRIVATE`, lookup không thể tìm `NestedTarget.hidden()` dù root gốc đã có thể.
7. `existing-handle=nested-secret`: `acquiredBeforeDrop` được tạo bằng root **trước** bước hạ quyền. Việc tạo lookup mới đã giảm quyền không thu hồi handle cũ.
8. `privateLookupIn-peer` thu được `PRI=true` trên `Peer` vì root có `PRIVATE` và `MODULE`, target ở cùng module. Ngược lại, dùng `noPrivate` hoặc `noModule` để gọi `privateLookupIn` thất bại.
9. `in-primitive=IllegalArgumentException`: API không chấp nhận primitive làm lookup class.
10. `publicLookup UNCOND=true PUB=false` không phải một mâu thuẫn: `UNCONDITIONAL` cấp public access trong các package xuất công khai vô điều kiện theo quy tắc riêng.

## 6. Demo Java 17 độc lập: `privateLookupIn` qua ranh giới named module

Demo thứ hai mô phỏng framework ở module `beta` muốn truy cập private method trong module `alpha`. `alpha` chỉ export API công khai `alpha.api`, còn target private nằm ở package `alpha.internal` chưa mở.

Tạo năm file:

```text
modules-demo/
└── src/
    ├── alpha/
    │   ├── module-info.java
    │   └── alpha/
    │       ├── api/Gateway.java
    │       └── internal/Hidden.java
    └── beta/
        ├── module-info.java
        └── beta/Client.java
```

### File `src/alpha/module-info.java`

```java
module alpha {
    exports alpha.api;
}
```

### File `src/alpha/alpha/api/Gateway.java`

```java
package alpha.api;

public class Gateway {
    public static String hello() { return "api-public"; }
    public static Class<?> hiddenClass() { return alpha.internal.Hidden.class; }
}
```

### File `src/alpha/alpha/internal/Hidden.java`

```java
package alpha.internal;

public class Hidden {
    private static String secret() { return "deep-secret"; }
}
```

### File `src/beta/module-info.java`

```java
module beta {
    requires alpha;
}
```

### File `src/beta/beta/Client.java`

```java
package beta;

import alpha.api.Gateway;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles.Lookup;

import static java.lang.invoke.MethodHandles.Lookup.*;

public class Client {
    private static boolean has(Lookup l, int bit) {
        return (l.lookupModes() & bit) != 0;
    }

    public static void main(String[] args) throws Throwable {
        Lookup base = MethodHandles.lookup();
        MethodType str = MethodType.methodType(String.class);
        MethodHandle publicApi = base.findStatic(Gateway.class, "hello", str);
        System.out.println("public-api=" + (String) publicApi.invokeExact());

        Lookup moved = base.in(Gateway.class);
        System.out.println("in-exported PUB=" + has(moved, PUBLIC)
                + " MOD=" + has(moved, MODULE)
                + " previous=" + moved.previousLookupClass().getSimpleName());

        Lookup blind = base.in(Gateway.hiddenClass());
        System.out.println("in-unexported modes=" + blind.lookupModes());

        try {
            MethodHandles.privateLookupIn(Gateway.class, base);
            System.out.println("privateLookupIn-exported=success");
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookupIn-exported=IllegalAccessException");
        }

        try {
            Lookup deep = MethodHandles.privateLookupIn(Gateway.hiddenClass(), base);
            System.out.println("privateLookupIn-hidden PRI=" + has(deep, PRIVATE)
                    + " MOD=" + has(deep, MODULE)
                    + " previous=" + deep.previousLookupClass().getSimpleName());
            MethodHandle secret = deep.findStatic(Gateway.hiddenClass(), "secret", str);
            System.out.println("secret=" + (String) secret.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookupIn-hidden=IllegalAccessException");
        }

        try {
            MethodHandles.privateLookupIn(Gateway.hiddenClass(), moved);
            System.out.println("reteleport=success");
        } catch (IllegalAccessException expected) {
            System.out.println("reteleport=IllegalAccessException");
        }
    }
}
```

**Biên dịch** từ thư mục `modules-demo/` với Java 17:

```bash
javac --release 17 --module-source-path src -d out src/alpha/module-info.java src/alpha/alpha/api/Gateway.java src/alpha/alpha/internal/Hidden.java src/beta/module-info.java src/beta/beta/Client.java
```

**Chạy lần thứ nhất**, không mở package:

```bash
java --module-path out -m beta/beta.Client
```

Kết quả:

```text
public-api=api-public
in-exported PUB=true MOD=false previous=Client
in-unexported modes=0
privateLookupIn-exported=IllegalAccessException
privateLookupIn-hidden=IllegalAccessException
reteleport=IllegalAccessException
```

**Chạy lần thứ hai**, chỉ mở package nội bộ `alpha.internal` cho `beta`:

```bash
java --module-path out --add-opens alpha/alpha.internal=beta -m beta/beta.Client
```

Kết quả:

```text
public-api=api-public
in-exported PUB=true MOD=false previous=Client
in-unexported modes=1
privateLookupIn-exported=IllegalAccessException
privateLookupIn-hidden PRI=true MOD=false previous=Client
secret=deep-secret
reteleport=IllegalAccessException
```

**Điểm quan sát quan trọng:**

1. `beta` khai báo `requires alpha` và `alpha` có `exports alpha.api` nên có thể lấy MethodHandle cho `Gateway.hello()` bằng lookup thông thường.
2. `base.in(Gateway.class)` đổi lookup class sang module `alpha`. Kết quả chỉ giữ public access, mất `MODULE`; `previousLookupClass` là `Client` ở module `beta`.
3. Khi chưa mở `alpha.internal`, `base.in(Hidden.class)` trả lookup có mode 0. Sau `--add-opens`, cùng phép `in` trên **public `Hidden`** có thể giữ `PUBLIC` (numeric mode 1), nhưng **không có `PRIVATE`**. Vì vậy `in` vẫn không thay thế được `privateLookupIn`.
4. `privateLookupIn(Gateway.class, base)` **vẫn thất bại** sau khi mở `alpha.internal`, bởi vì package `alpha.api` là package khác, chỉ `exports` và chưa `opens`. Có `public class` và `exports` không đồng nghĩa cấp deep private access.
5. `privateLookupIn(Hidden.class, base)` thất bại khi package đóng, nhưng thành công sau khi mở đúng `alpha.internal`. Lookup mới có `PRI=true`, `MOD=false` và `previousLookupClass=Client`; handle cho private method `Hidden.secret()` trả `deep-secret`.
6. `privateLookupIn(Hidden.class, moved)` luôn thất bại trong demo: `moved` đã mất `MODULE` do `Lookup.in` chuyển từ `beta` sang `alpha`. Dù mở package, lookup bị hạ quyền không tự lấy lại full privilege.

**Thiết kế ứng dụng:** Nếu module của framework cần private access có kiểm soát, module đích có thể khai báo `opens alpha.internal to beta;` trong `module-info.java` khi phù hợp với cấu trúc dự án, thay vì thêm JVM flag. Khi làm vậy, hãy biên dịch module graph đầy đủ và chỉ mở đúng những package cần thiết. Đừng tự động mở toàn bộ module hoặc dùng private lookup khi public API đã đáp ứng nhu cầu.

## 7. Bảng so sánh nhanh ba API

| Tình huống | `Lookup.in` | `dropLookupMode` | `privateLookupIn` |
| --- | --- | --- | --- |
| Đổi lookup class sang target | **Có** | Không | **Có** |
| Giữ nguyên lookup class | Khi target là chính class hiện tại | **Có** | Khi target chính là class hiện tại |
| Có thể làm mất `PRIVATE`/`PACKAGE`/`MODULE` | **Có**, theo ranh giới | **Có**, theo bit và cascade | Có thể mất `MODULE` khi chuyển qua module khác |
| Có thể cấp `PRIVATE` trên class target khác | Không nâng quyền | Không | **Có**, sau khi kiểm tra quyền đầu vào và module |
| Cần lookup gốc `PRIVATE + MODULE` | Không | Không | **Có** |
| Cần `opens` khi deep lookup xuyên named module | Không xin deep access | Không | **Có**, nếu target module khác |
| Có thể tạo `previousLookupClass` khác `null` | Có khi vượt module | Giữ ngữ cảnh trước đó | Có khi vượt module |
| Cách thất bại thường gặp | Trả lookup ít hoặc không có mode; primitive target ném `IllegalArgumentException` | Hạ quyền theo cascade; mode không hợp lệ ném `IllegalArgumentException` | `IllegalAccessException` nếu quyền/reads/opens không đủ |

**Phân biệt với `MethodHandles.publicLookup()`:** đây là factory tạo lookup quyền public tối thiểu (`UNCONDITIONAL`) theo quy tắc các package được export vô điều kiện. Nó hữu ích cho API public nhưng **không thể nâng lên private** bằng `in` hay `privateLookupIn` vì bản thân nó thiếu `PRIVATE` và `MODULE`.

## 8. Thiết kế và debug an toàn

### 8.1 Áp dụng nguyên tắc cấp đúng capability

Một lookup đầy đủ cho phép tạo handles tới thành viên private và other access theo ngữ cảnh caller. Khi tích hợp plugin hoặc template engine:

- Xác định trước **target** và **member** cần cho integration, rồi cấp một `MethodHandle` cụ thể nếu đó là hợp đồng duy nhất cần chia sẻ.
- Nếu cần cấp lookup cho bên nhận, chủ động dùng `dropLookupMode` để giới hạn quyền; đảm bảo kiểm tra cả **khả năng tìm members của lookup class**.
- Tránh phát tán `MethodHandles.lookup()` đầy đủ qua public API, shared registry hay plugin hooks không tin cậy. Lookup là **capability**, không chỉ metadata.
- Không cho rằng `dropLookupMode` thu hồi được method handles đã phát hành; nếu cần thay đổi quyền sử dụng ở runtime, thiết kế thêm lớp API kiểm soát invocation/application authorization.
- Không tự động thêm `--add-opens` rộng hoặc `opens p;` tràn lan. Chỉ mở package có chủ đích cho module thực sự cần deep reflection.
- Nếu một public API đủ dùng, dùng normal exported API; deep private lookup nên là ngoại lệ có lý do rõ ràng.

### 8.2 Khi `findStatic` / `findVirtual` hoặc `privateLookupIn` thất bại

Điều tra theo thứ tự:

1. **Lớp tra cứu hiện tại là ai?** In `lookup.lookupClass()`. Code đặt trong helper method có thể có caller khác code ứng dụng gọi helper đó.
2. **Các mode còn lại là gì?** In `lookup.lookupModes()` dưới dạng mask/bit flags. Kiểm tra `PRIVATE`, `PACKAGE`, `MODULE` và `UNCONDITIONAL` theo ngữ cảnh.
3. **Có previous lookup class không?** In `lookup.previousLookupClass()`. Nếu đã dịch chuyển xuyên module, quyền public còn phải đáp ứng điều kiện của nhiều module.
4. **Target class có truy cập được từ lookup không?** `lookup.in(Target.class)` có thể trả mode 0 khi target inaccessible. Kiểm tra public visibility, loader, package/module, `requires`/readability, `exports` và `opens`.
5. **Lookup có đã mất quyền trước đó không?** `dropLookupMode(PRIVATE)` hoặc `in(otherPackage.class)` không thể được đảo ngược bằng việc gọi `in` thêm lần nữa.
6. **Nếu dùng `privateLookupIn`**, caller phải có cả `PRIVATE` và `MODULE`; khác module thì cần reads + opens đúng target package.
7. **Member/signature có đúng không?** Với `findStatic` và `findVirtual`, `MethodType` phải mô tả chính xác return type và parameter types; sai chữ ký có thể gây `NoSuchMethodException` thay vì lỗi access.
8. **Invoke có đúng kiểu không?** `invokeExact` yêu cầu kiểu lời gọi khớp chính xác method handle; nếu không sẽ gây `WrongMethodTypeException`. Điều này **khác** `IllegalAccessException` lúc tạo handle.

Đoạn hỗ trợ quan sát sau là **snippet**, thêm vào nơi đang có biến `Lookup lookup` (không phải chương trình độc lập):

```java
System.out.println("lookup class: " + lookup.lookupClass().getName());
System.out.println("previous class: " + lookup.previousLookupClass());
System.out.println("modes mask: " + lookup.lookupModes());
System.out.println("has PRIVATE: " +
        ((lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
System.out.println("has MODULE: " +
        ((lookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
System.out.println("has full privilege: " + lookup.hasFullPrivilegeAccess());
```

Snippet cần `import java.lang.invoke.MethodHandles;` và một `Lookup` được tạo hợp lệ. Khi log môi trường thực tế, lưu ý `lookupClass()`/`previousLookupClass()` có thể lộ tên implementation; tránh in thông tin chi tiết ở kênh công khai.

### 8.3 Nhận diện đúng loại exception

| Ngoại lệ | Ví dụ |
| --- | --- |
| `IllegalAccessException` | `findStatic` bị chặn bởi access checks; hoặc `privateLookupIn` không đủ `PRIVATE/MODULE` hay module chưa `opens` |
| `NoSuchMethodException` | `findStatic` tìm sai tên hoặc sai `MethodType`, tìm instance như static hoặc ngược lại |
| `IllegalArgumentException` | `lookup.in(int.class)`; `dropLookupMode` nhận mode không được hỗ trợ; `privateLookupIn` nhận primitive/array |
| `NullPointerException` | Truyền `null` cho `Lookup.in` hoặc cho target/caller của `privateLookupIn` |
| `WrongMethodTypeException` | Gọi `MethodHandle.invokeExact` với signature không đúng |
| Exception do target ném | Khi handle hợp lệ được thực thi, exception thường được ném trực tiếp từ target; **không** có lớp bọc `InvocationTargetException` tự động như `Method.invoke` |

Nếu không phân biệt **lookup/access** với **invoke/type** và **exception trong target**, rất dễ sửa nhầm thành "hãy dùng privateLookupIn" trong khi vấn đề thực chất là sai `MethodType`.

## 9. Bài tập tự kiểm tra

**Câu 1.** Một `Lookup` đầy đủ được tạo trong class `A`. `A` và `A.Nested` là nestmates. `A` gọi `lookup.in(A.Nested.class)`. Lookup mới có thể giữ quyền `PRIVATE` không?

**Đáp án:** Có. Cùng nest cho phép giữ private access, dù `ORIGINAL` không còn khi lookup class thay đổi.

**Câu 2.** Class `A` và class `B` cùng runtime package, nhưng khác nest. `lookupFromA.in(B.class)` có tự tạo private access vào `B` không?

**Đáp án:** Không. `PRIVATE` bị drop khi chuyển sang khác nest; `PACKAGE` có thể còn. Với lookup đầy đủ ở cùng module, `privateLookupIn(B.class, lookupFromA)` là cách xin lookup private phù hợp sau access checks.

**Câu 3.** Sau `dropLookupMode(PACKAGE)`, có thể giữ `PRIVATE` trên Java 17 không?

**Đáp án:** Không. Drop `PACKAGE` cũng loại bỏ `PRIVATE`, `PROTECTED` và `ORIGINAL`. Từ lookup đầy đủ còn `MODULE` và `PUBLIC`.

**Câu 4.** Sau `dropLookupMode(MODULE)`, có thể dùng lookup kết quả gọi `privateLookupIn` đến class khác cùng module không?

**Đáp án:** Không. Nó không còn `MODULE` (và cũng mất `PRIVATE`).

**Câu 5.** Module `beta` đọc module `alpha`, `alpha` export package `api` nhưng không open. `privateLookupIn(Api.class, lookupFromBeta)` có luôn thành công khi `Api` là `public`?

**Đáp án:** Không. Muốn deep lookup giữa hai named module, package chứa target phải được mở cho caller module. `exports` một mình không đáp ứng điều kiện `opens`.

**Câu 6.** Với `--add-opens alpha/alpha.internal=beta`, private lookup từ `beta` vào class target trong `alpha.internal` thành công. Lookup kết quả có thể tiếp tục xin private lookup sang module thứ ba không?

**Đáp án:** Không. Lookup đã teleport qua module mất `MODULE`; `privateLookupIn` yêu cầu caller có cả `PRIVATE` và `MODULE`.

**Câu 7.** Lookup đã tạo handle cho private method, sau đó gọi `dropLookupMode(PRIVATE)` trên lookup để tạo bản giảm quyền. Method handle cũ có bị thu hồi không?

**Đáp án:** Không. Permission đã được kiểm khi handle được tạo, và hạ quyền của lookup mới không thu hồi capability cũ.

**Câu 8.** Vì sao `MethodHandles.publicLookup().lookupModes()` không nhất thiết chứa bit `PUBLIC`, nhưng vẫn có thể tìm public members?

**Đáp án:** `publicLookup()` hoạt động theo mode `UNCONDITIONAL` riêng, chỉ tới public members của public types trong package được export không điều kiện. Trạng thái `UNCONDITIONAL` không phải sự kết hợp tùy ý với bit `PUBLIC`.

**Câu 9.** Lỗi `WrongMethodTypeException` khi đã có handle hợp lệ có chỉ ra vấn đề với `opens`/`PRIVATE` không?

**Đáp án:** Không. Thường là call-site `invokeExact` có signature không khớp `MethodType` của handle; access checks đã diễn ra khi tạo handle.

**Câu 10.** Có nên gọi `MethodHandles.lookup()` trong helper rồi giả sử nó đại diện cho code gọi helper không?

**Đáp án:** Không. `lookup()` là caller-sensitive, lấy chính lớp gọi trực tiếp nó làm lookup class. Nếu muốn chuyển capability từ caller hợp lệ sang helper, phải truyền lookup phù hợp và kiểm soát quyền được ủy quyền.

## 10. Ghi nhớ

- `Lookup` vừa mang **lookup class**, **lookup modes** và đôi khi **previous lookup class**; nó là capability cần quản lý cẩn thận.
- `Lookup.in` **đổi class nhưng không tăng quyền**. Cùng nest có thể giữ private, cùng package khác nest mất private, đổi package mất package, xuyên module mất module.
- `dropLookupMode` **hạ quyền một chiều** và có **cascade**; không khôi phục bit bằng `in`.
- `privateLookupIn` cần caller có **`PRIVATE + MODULE`**. Sang named module khác còn phải có **reads + opens** phù hợp.
- Lookup thu được qua `privateLookupIn` xuyên module vẫn có private access ở target nhưng **không có MODULE** để chuyển tiếp deep lookup.
- `MethodHandle` đã tạo hợp lệ **không tự mất quyền** vì lookup khác bị drop; kiểm soát cả handle lẫn lookup khi ủy quyền.
- `exports` hỗ trợ public API; `opens` cho phép deep reflection theo phạm vi được cấp.
- Kiểm tra quyền khi **tạo handle**, kiểm tra đúng kiểu khi **invokeExact**, và phân biệt rõ exception của hai giai đoạn.

### Tài liệu chuẩn (Java SE 17)

- [`MethodHandles.Lookup` — Access checking, Cross-module lookups, Access modes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [`MethodHandles.Lookup.in(Class)`, `dropLookupMode(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#in(java.lang.Class))
- [`MethodHandles.privateLookupIn(Class, Lookup)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup))
- [`MethodHandle.invokeExact`, `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [JLS 17 — Module declarations (`exports`, `opens`)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)