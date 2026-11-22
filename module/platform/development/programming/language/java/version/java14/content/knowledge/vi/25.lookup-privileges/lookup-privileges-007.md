# Ủy quyền tối thiểu cho mã được tin cậy bằng `MethodHandles.Lookup` (Java 14+)

> **Mục tiêu:** hiểu vì sao `java.lang.invoke.MethodHandles.Lookup` là một **capability** (đối tượng mang khả năng truy cập thành viên Java), và cách một class có đặc quyền chỉ chuyển giao **đúng phạm vi** mà một thư viện, adapter hoặc framework đáng tin cậy cần dùng. Bài áp dụng các API ổn định `publicLookup()`, `lookup()`, `dropLookupMode(int)`, `in(Class<?>)`, `lookupModes()`, `hasFullPrivilegeAccess()` và `privateLookupIn(...)`; ưu tiên chuyển giao một `MethodHandle` cụ thể thay vì nguyên `Lookup` nếu chỉ cần một phép gọi. Giữ đúng **Special Note: chỉ kiến thức hiện hành**, không dựa vào `SecurityManager`/các biện pháp bypass nội bộ đã legacy. Chương trình chạy với **JDK 17+** và đã kiểm tra trên OpenJDK 21.

## 1. Quyền Lookup là gì và vì sao liên quan đến ủy quyền?

`MethodHandles.Lookup` là factory tạo ra `MethodHandle`, `VarHandle` hoặc tham chiếu đến thành viên khi cần kiểm tra quyền truy cập. Một `Lookup` mang theo **lookup class** (ngữ cảnh class được dùng để kiểm tra) và các **lookup mode bits** giới hạn quyền tìm kiếm. Nó không chỉ là một “công cụ tiện ích” vô hại.

Trong mã Java thông thường, class có thể gọi các phương thức private của chính nó, nhưng class bên ngoài không thể làm như vậy. Khi một class đáng tin cậy gọi:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

JVM tạo một `Lookup` mang khả năng truy cập tương đương những member mà **class trực tiếp gọi `lookup()`** được phép truy cập theo bytecode, bao gồm private của class và các nestmate thích hợp. `MethodHandles.lookup()` là **caller-sensitive**: gọi từ helper class khác thì ngữ cảnh quyền là helper đó, không phải tự động là class bạn muốn đại diện.

**Chuyển object `lookup` cho một component khác chính là chuyển khả năng dùng quyền truy cập được đóng gói trong object ấy.** Component nhận có thể tiếp tục tạo các handle mới trong giới hạn của Lookup. Nó không được nâng lên quyền của chính code đang gọi nó: kiểm tra do lookup class/modes gắn trong capability quyết định.

**Mốc kiểm tra rất quan trọng:**

1. `Lookup.findVirtual`, `findGetter`, `findStatic`, `unreflect` và các factory tương tự kiểm tra quyền **khi tạo handle**.
2. Một `MethodHandle` đã tạo thành công thường **không thực hiện lại kiểm tra ngôn ngữ access tại mỗi lần `invoke`/`invokeExact`**.
3. Vì thế **bản thân handle đã tạo cũng là một capability**; chuyển nó cho ai đó có thể cho họ thực hiện thao tác mà tự họ không có quyền tự tạo handle.
4. `Lookup` có quyền rộng có thể tạo **nhiều loại handle**; handle đã chọn/bind thường có phạm vi chức năng hẹp hơn, nhưng không mặc nhiên an toàn nếu chính thao tác đó tiết lộ dữ liệu hoặc sửa state nhạy cảm.

**Ví dụ tư duy:** một adapter chỉ cần gọi getter để lấy nhãn hiển thị thì không nên nhận `Lookup` có thể tìm bất kỳ private method/field nào trong module. Có thể chỉ cho nó một interface public hoặc một function/handle getter đã phê duyệt.

## 2. Chọn mức quyền thấp nhất cho nhu cầu

| Nhu cầu thật | Hướng nên ưu tiên | Những gì tránh trao thừa |
|---|---|---|
| Gọi API public thông thường | Interface/public method có kiểu tĩnh | Không cần `Lookup` nào |
| Tra cứu method public qua tên động | `MethodHandles.publicLookup()` nếu class/member public và package exported vô điều kiện | Không cung cấp full caller lookup |
| Framework tin cậy phải xử lý một số member package-level | `lookup().dropLookupMode(PRIVATE)` trong lớp sở hữu quyền, sau khi đánh giá quyền `MODULE`/`PACKAGE` vẫn còn | Không giả định đây là public-only |
| Chỉ cần gọi **một** private method đã phê duyệt | Code sở hữu private tạo **một `MethodHandle`**, cân nhắc `bindTo(receiver)`/wrapper | Không cho factory `Lookup` để tự tìm các private member khác |
| Adapter được kiểm toán thực sự cần private reflection vào một target | `MethodHandles.privateLookupIn(target, callerLookup)` với điều kiện module đúng, rồi **giới hạn phạm vi chuyển giao** | Không mở cả module vô điều kiện hoặc phát tán full Lookup |
| Chạy code không tin cậy/đối nghịch | Cách ly ở process/OS/container và thiết kế ranh giới dữ liệu/API | Không dùng `Lookup` bị giảm quyền như “Java sandbox” |

Hai câu hỏi phải được trả lời **trước khi ủy quyền**: đối tác cần truy cập **class nào/member nào**, và cần **tìm kiếm tự do** hay chỉ cần **thực hiện một thao tác đã định**? Phạm vi quyền nhỏ nhất thường là một operation có kiểm soát, không phải một lookup object.

### Vì sao `MethodHandles.lookup()` có độ nhạy cao?

Oracle JavaDoc mô tả lookup đầy đủ do caller tạo là một capability có thể chuyển cho **trusted agents**, nhưng không được đặt ở vị trí mà code không tin cậy có thể lấy được. Ngoài việc tra cứu private member, một lookup đủ quyền còn có những API nâng cao như `defineClass`/`defineHiddenClass` trong phạm vi runtime package/nest theo điều kiện API. Vì vậy việc lộ full lookup có thể tác động **lớn hơn chỉ đọc một field**.

Ví dụ cần tránh trong ứng dụng thực:

```java
// MẪU RỦI RO: public field mang khả năng private access.
public static final MethodHandles.Lookup LOOKUP =
    MethodHandles.lookup();
```

Đoạn trên là **snippet minh họa điều không nên làm**, không có đầy đủ import/class. `final` chỉ ngăn thay tham chiếu field, **không làm giảm quyền** của object `Lookup`. Dù đối tác được xem là trusted, lưu capability vào API public không cần thiết sẽ mở rộng tập code có thể dùng nó trong tương lai.

## 3. Các mode bit của `Lookup` và ý nghĩa

`Lookup.lookupModes()` trả về bitmask mô tả các giới hạn truy cập. Với Java SE hiện hành:

| Mode | Vai trò chính |
|---|---|
| `PUBLIC` | Cho phép tra cứu public member/class theo quy tắc accessibility/module |
| `PRIVATE` | Cho phép private access thích hợp trong phạm vi lookup class và nest |
| `PROTECTED` | Cho phép protected access tương ứng với ngữ cảnh class |
| `PACKAGE` | Cho phép package-private access trong phạm vi package liên quan |
| `MODULE` | Thể hiện ràng buộc module, tham gia kiểm tra member/type và full privilege |
| `UNCONDITIONAL` | Quyền public không phụ thuộc quan hệ reads của một lookup class, nhưng chỉ với package **exported vô điều kiện** |
| `ORIGINAL` | Đánh dấu lookup nguyên gốc do caller/VM tạo, có thêm khả năng dành cho caller-sensitive và class data; có từ Java 16 |

`PUBLIC` và `UNCONDITIONAL` **không giống nhau**: `publicLookup()` thông thường có `UNCONDITIONAL`, truy cập public member của public class trong package mà module công khai **exports không có mục tiêu**. Một lookup có `PUBLIC` theo ngữ cảnh module còn phải tuân quy tắc readability/qualified exports tùy lookup class và previous lookup class.

Một số mode có thể cùng tồn tại; nhìn `lookupModes()` thay vì chỉ suy từ class name. `ORIGINAL` có ý nghĩa khi xử lý caller-sensitive methods hoặc class data; nếu đối tác không cần những khả năng đó, không nên trao một object còn mang mode gốc.

### `hasFullPrivilegeAccess()` thay vì API cũ

`Lookup.hasFullPrivilegeAccess()` (từ Java 14) trả `true` **chỉ khi có cả `PRIVATE` và `MODULE`**. Phương thức `hasPrivateAccess()` đã **deprecated từ Java 14**; nội dung hiện hành nên dùng `hasFullPrivilegeAccess()` để xác minh đủ full privilege, hoặc xét các mode cụ thể bằng bitmask.

```java
boolean privateMode =
    (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean fullPrivilege = lookup.hasFullPrivilegeAccess();
```

**Không nhầm “mode hiện diện” với “được phép tìm bất kỳ member ở bất kỳ module nào”.** Access còn phụ thuộc class/member, module reads/exports/opens, lookup class, class-loader/nest và chữ ký cần tìm. Những kiểm tra boolean chỉ là bước audit ban đầu; phép `find...` cụ thể mới chứng minh handle có thể được tạo.

## 4. Giảm quyền bằng `dropLookupMode(int)`

Phương thức:

```java
MethodHandles.Lookup reduced =
    original.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

tạo **Lookup mới** trên cùng lookup class nhưng **giảm mode**. Nó **không sửa object `original`**; nếu còn giữ bản gốc, code sở hữu bản gốc vẫn có quyền cũ. Quy tắc quan trọng: mode đã bị bỏ **không thể khôi phục từ chính bản Lookup bị giảm**.

JavaDoc quy định việc hạ mode có tác dụng dây chuyền, không chỉ xóa đúng một bit:

| Lời gọi từ lookup đầy đủ ban đầu | Mode còn lại (khái quát) | Điều cần lưu ý |
|---|---|---|
| `dropLookupMode(PRIVATE)` | `PUBLIC, PACKAGE, MODULE` | Bỏ `PRIVATE`, đồng thời mất `PROTECTED` và `ORIGINAL`; **không phải** public-only |
| `dropLookupMode(PACKAGE)` | `PUBLIC, MODULE` | Mất `PACKAGE, PRIVATE, PROTECTED, ORIGINAL` |
| `dropLookupMode(MODULE)` | `PUBLIC` | Mất `MODULE` và `PACKAGE/PRIVATE`, cũng không giữ `PROTECTED/ORIGINAL` |
| `dropLookupMode(PUBLIC)` | Không còn access mode | Không có quyền tạo handle vào member thường |
| `dropLookupMode(ORIGINAL)` | Không còn `ORIGINAL, PROTECTED`, có thể vẫn giữ `PRIVATE, PACKAGE, MODULE, PUBLIC` | **Mất original** không nhất thiết là mất full privilege |
| `publicLookup().dropLookupMode(UNCONDITIONAL)` | Không còn access mode | Đây là trường hợp hạ quyền public lookup |

Bảng mô tả trường hợp khởi đầu **`MethodHandles.lookup()` đầy đủ**. Đối với lookup đã mất một số bit hoặc đã “teleport” qua module, tập bit còn lại phụ thuộc trạng thái hiện tại; **đừng hard-code bảng trên để suy ra mọi trường hợp**.

Ví dụ giảm đủ để không trao private access nhưng vẫn cho adapter trong module truy cập thành viên package nếu quy tắc Java cho phép:

```java
MethodHandles.Lookup scoped = MethodHandles.lookup()
    .dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

Điểm cần lưu ý: `scoped` vẫn còn `PACKAGE` và `MODULE`, có thể cho phép tra cứu member không public trong package phù hợp. Nếu chỉ muốn public lookup, **chọn `publicLookup()`** hoặc đánh giá kỹ `dropLookupMode(MODULE)`. Hai lựa chọn ấy có ngữ nghĩa cross-module **khác nhau**; không nên coi mọi lookup chỉ có public-like access đều có capability hoàn toàn đồng nhất.

### Vì sao không dùng `dropLookupMode(PRIVATE)` như “hủy hết quyền nhạy cảm”?

Bởi vì package-private member có thể chứa thông tin nghiệp vụ nội bộ hoặc API không dành cho adapter bên ngoài. Tương tự `MODULE` là khả năng truy cập trong module mà một đối tác chỉ cần public API có thể không nên giữ. **Giảm quyền phải dựa trên mục tiêu**, không chỉ theo nhãn “private”.

## 5. `Lookup.in(Class<?>)`: đổi ngữ cảnh mà không nâng quyền

`Lookup.in(Target.class)` tạo một lookup **cho class mục tiêu** nhưng bảo đảm capability của lookup kết quả **không lớn hơn lookup ban đầu**. Việc di chuyển ngữ cảnh có thể giảm quyền vì khác nest, package, module hoặc vì target không accessible.

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup sameNest = full.in(Vault.class);
MethodHandles.Lookup javaBase = full.in(String.class);
```

Đây là snippet nếu `Vault` là nested class cùng nest và `full` được tạo trong class sở hữu nó. Kết quả có thể khác:

- Khi `in` chuyển sang class khác **cùng nest**, `PRIVATE` có thể còn, mặc dù `ORIGINAL` luôn bị mất khi lookup class đổi.
- Khi chuyển sang **module khác**, `MODULE` bị mất; tùy quy tắc xuất package và readability, thường còn phạm vi public thích hợp.
- Khi chuyển sang package khác, `PACKAGE` và `PROTECTED` có thể bị mất.
- Nếu class đích không accessible, các quyền có thể bị mất hết.
- **Không bao giờ coi `in(Target.class)` là cách lấy private access của Target từ một lookup public.**

Điểm tinh tế: `in` **không đồng nghĩa public-only**. Nếu mục tiêu cùng nest, nó có thể vẫn có `PRIVATE`; nếu cần giảm quyền rõ ràng, phải gọi `dropLookupMode` và kiểm tra mode sau khi chuyển.

**Kiểm chứng riêng trên OpenJDK 21:** `full.in(Inner.class)` khi `Inner` là class lồng cùng nest giữ `PRIVATE=true` nhưng mất `ORIGINAL`; `full.in(String.class)` từ ứng dụng trong unnamed module sang `java.base` mất `PRIVATE`/`MODULE` và còn `PUBLIC`. Đây là **quan sát có điều kiện** của ví dụ cụ thể, không là khẳng định mọi mục tiêu đều cho các bit hệt nhau.

## 6. `privateLookupIn` chỉ dùng khi đã có quyền hợp lệ

Cú pháp:

```java
MethodHandles.Lookup targetLookup =
    MethodHandles.privateLookupIn(Target.class, callerLookup);
```

Nó **không phải cánh cửa mở mọi private field**. JavaDoc hiện hành yêu cầu `callerLookup` có cả `PRIVATE` và `MODULE` (full privilege), và target phải là class hợp lệ chứ không phải primitive hoặc array. Nếu **khác module**, cần thêm:

1. Module của caller (`M1`) **reads** module target (`M2`).
2. Module target **opens** package chứa Target tới ít nhất `M1`.
3. Kết quả `Lookup` chuyển sang target và mất `MODULE` khi hai module khác nhau, đồng thời không có `ORIGINAL`.

Trong **cùng module**, `privateLookupIn` có thể cho một lookup trên target với private access khi caller đủ quyền. Một lookup đã bỏ `PRIVATE` **không thể dùng để tạo lại full lookup** qua `privateLookupIn`; một lookup đã bỏ `MODULE` cũng vậy.

### `exports` khác `opens`

Với Java Platform Module System (JPMS):

- `exports com.example.api;` đưa **public types/members** của package vào API module cho module đọc được.
- `opens com.example.internal to com.example.adapter;` cho phép module `com.example.adapter` thực hiện deep reflection vào package tương ứng, theo các kiểm tra của API.
- `exports` **không tương đương** `opens` để truy cập private member.
- **`opens ... to ...` là quyền rộng ở cấp package cho module được nêu**, không phải grant cho một method duy nhất.

Mẫu `module-info.java` mang tính **minh họa kiến trúc** (không phải chương trình độc lập):

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.internal to com.example.adapter;
}
```

Nếu cần mở package, **ưu tiên qualified `opens ... to trusted.module`** thay cho `open module` hoặc `opens` vô điều kiện. Tuy vậy dù có qualified opens, hãy hỏi liệu adapter có thể nhận **một handle đã tạo sẵn hoặc public interface** thay cho toàn bộ private lookup không.

**Rủi ro ở mức module:** JavaDoc cảnh báo lookup do `privateLookupIn` cấp có thể dùng định nghĩa class trong runtime package của target khi đủ điều kiện. Vì thế mở một package để deep reflection có thể cấp năng lực mạnh hơn việc gọi private method, đặc biệt nếu adapter được phép tự tạo class/handle. Hãy thu hẹp cả **module được mở** và **capability thực sự chuyển giao**.

## 7. Ví dụ Java 17+ hoàn chỉnh: giảm quyền rồi kiểm chứng

Ví dụ này tách hai vai trò:

- Class tin cậy `LookupLeastPrivilegeDemo` chứa nested class `Vault`. `Vault.reveal()` là private; outer class cùng nest có thể tìm nó bằng full lookup.
- Một `Lookup` giảm quyền hoặc public lookup thử tạo handle. Phép `findVirtual` thành công/thất bại đúng theo quyền đã cấp.
- Cuối cùng, class tin cậy tạo **một handle đã bind với một object cụ thể**, minh họa quyền hẹp hơn việc phát tán toàn bộ lookup.

**Lưu ý bảo mật của demo:** chuỗi `"example-only"` chỉ là giá trị giả dùng cho bài học. Trên hệ thống thực, **không chuyển handle tiết lộ secret** cho đối tác không được phép. Việc buộc handle vào một receiver làm nhỏ phạm vi thao tác, **không biến thao tác nhạy cảm thành an toàn**.

Tạo file **`LookupLeastPrivilegeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class LookupLeastPrivilegeDemo {
    public static final class Vault {
        private final String demoValue;

        public Vault(String demoValue) {
            this.demoValue = demoValue;
        }

        public String label() {
            return "demo";
        }

        private String reveal() {
            return demoValue;
        }
    }

    static boolean has(MethodHandles.Lookup l, int mode) {
        return (l.lookupModes() & mode) != 0;
    }

    static boolean canFind(MethodHandles.Lookup l, String method) {
        try {
            l.findVirtual(Vault.class, method,
                MethodType.methodType(String.class));
            return true;
        } catch (NoSuchMethodException | IllegalAccessException expected) {
            return false;
        }
    }

    static boolean canCreatePrivateLookup(MethodHandles.Lookup l) {
        try {
            MethodHandles.privateLookupIn(Vault.class, l);
            return true;
        } catch (IllegalAccessException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Throwable {
        Vault vault = new Vault("example-only");
        MethodHandles.Lookup full = MethodHandles.lookup();
        MethodHandles.Lookup withoutPrivate =
            full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        MethodHandles.Lookup withoutModule =
            full.dropLookupMode(MethodHandles.Lookup.MODULE);
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

        System.out.println("fullPrivate=" +
            has(full, MethodHandles.Lookup.PRIVATE));
        System.out.println("fullModule=" +
            has(full, MethodHandles.Lookup.MODULE));
        System.out.println("fullOriginal=" +
            has(full, MethodHandles.Lookup.ORIGINAL));
        System.out.println("reducedPrivate=" +
            has(withoutPrivate, MethodHandles.Lookup.PRIVATE));
        System.out.println("reducedModule=" +
            has(withoutPrivate, MethodHandles.Lookup.MODULE));
        System.out.println("reducedOriginal=" +
            has(withoutPrivate, MethodHandles.Lookup.ORIGINAL));
        System.out.println("noModulePrivate=" +
            has(withoutModule, MethodHandles.Lookup.PRIVATE));
        System.out.println("noModuleModule=" +
            has(withoutModule, MethodHandles.Lookup.MODULE));

        System.out.println("fullFindPrivate=" +
            canFind(full, "reveal"));
        System.out.println("reducedFindPrivate=" +
            canFind(withoutPrivate, "reveal"));
        System.out.println("reducedFindPublic=" +
            canFind(withoutPrivate, "label"));
        System.out.println("publicFindPublic=" +
            canFind(publicOnly, "label"));
        System.out.println("publicFindPrivate=" +
            canFind(publicOnly, "reveal"));

        System.out.println("reducedCanPrivateLookup=" +
            canCreatePrivateLookup(withoutPrivate));
        System.out.println("fullCanPrivateLookup=" +
            canCreatePrivateLookup(full));

        MethodHandle oneOperation = full.findVirtual(
            Vault.class, "reveal", MethodType.methodType(String.class))
            .bindTo(vault);
        System.out.println("singleHandleResult=" +
            (String) oneOperation.invokeExact());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 LookupLeastPrivilegeDemo.java
java LookupLeastPrivilegeDemo
```

**Stdout đã kiểm chứng trên OpenJDK 21:**

```text
fullPrivate=true
fullModule=true
fullOriginal=true
reducedPrivate=false
reducedModule=true
reducedOriginal=false
noModulePrivate=false
noModuleModule=false
fullFindPrivate=true
reducedFindPrivate=false
reducedFindPublic=true
publicFindPublic=true
publicFindPrivate=false
reducedCanPrivateLookup=false
fullCanPrivateLookup=true
singleHandleResult=example-only
```

### Phân tích kết quả

- `fullPrivate=true`, `fullModule=true`, `fullOriginal=true`: `MethodHandles.lookup()` gọi ngay trong class demo cung cấp full caller lookup.
- `reducedPrivate=false` nhưng `reducedModule=true`: `dropLookupMode(PRIVATE)` chặn private member nhưng **không tự bỏ mọi quyền trong module**.
- `reducedOriginal=false`: khi giảm quyền, lookup mới không còn original capability của caller.
- `noModulePrivate=false`, `noModuleModule=false`: `dropLookupMode(MODULE)` cũng loại `PRIVATE`; không còn full privilege.
- `fullFindPrivate=true` nhưng `reducedFindPrivate=false`: full lookup trong cùng nest tạo handle tới private method, còn lookup đã bỏ `PRIVATE` thì không.
- `reducedFindPublic=true` và `publicFindPublic=true`: ví dụ chọn class `Vault` khai báo `public` để hai lookup đều có thể tìm public method `label()`.
- `publicFindPrivate=false`: `publicLookup()` không lấy được private method.
- `reducedCanPrivateLookup=false`, `fullCanPrivateLookup=true`: `privateLookupIn` cần `PRIVATE + MODULE`, không thể “nâng lại” reduced lookup.
- `singleHandleResult=example-only`: handle đã được class có quyền tạo, bind vào `vault` và gọi `invokeExact()`. Thành công **không có nghĩa** mọi component được phép tự tạo handle tương tự; nó chứng tỏ handle là capability được chuyển giao sau khi kiểm tra access lúc tạo.

**Vì sao không kiểm tra bằng `SecurityManager`?** Hành vi `Lookup` được JVM và JPMS bảo đảm theo các quy tắc API. `SecurityManager` đã bị vô hiệu hóa vĩnh viễn từ Java 24, không còn là giải pháp bảo vệ plugin hiện đại; đây cũng là lý do bài chỉ hướng dẫn các API còn hiệu lực.

### Điểm lưu ý về `invokeExact()`

`invokeExact()` cần **kiểu call site chính xác**. Trong ví dụ, handle của `reveal()` có kiểu `()String` sau `bindTo(vault)`, nên ép kiểu rõ `(String) oneOperation.invokeExact()` là đúng. Nếu gọi với chữ ký Java không khớp, sẽ gặp `WrongMethodTypeException`, **không phải** `IllegalAccessException`. Quyền được xét ở `findVirtual`; type checking khi invoke là vấn đề khác.

## 8. Mẫu ủy quyền có kiểm soát trong thiết kế thư viện

### 8.1. Ưu tiên interface hoặc wrapper hẹp

Nếu plugin cần nhãn của đối tượng:

```java
public interface LabelProvider {
    String label();
}
```

Đây là **mẫu interface độc lập**. Một API có kiểu tĩnh thường dễ audit hơn việc phát một factory dùng reflection. Thêm validation/authorization nghiệp vụ vào wrapper nếu dữ liệu tùy user/tenant.

**Đặc quyền Java không thay thế quyền nghiệp vụ.** Dù method public, adapter có thể vẫn không được phép đọc dữ liệu của người dùng khác; cần kiểm tra tenant, ownership, role hoặc phạm vi session trong code ứng dụng.

### 8.2. Chỉ trao một operation đã tạo

Mẫu minh họa (snippet trong class được quyền truy cập private của `Vault`):

```java
MethodHandle permitted = MethodHandles.lookup()
    .findVirtual(Vault.class, "reveal",
                 MethodType.methodType(String.class))
    .bindTo(approvedVault);
```

Nếu chỉ muốn đối tác gọi **một thao tác trên một instance cụ thể**, handle đã `bindTo` có phạm vi nhỏ hơn việc trao full `Lookup` cho phép tìm nhiều thành viên. Tuy vậy nó vẫn có thể bị gọi **nhiều lần**, có thể gây side effect hoặc leak dữ liệu. Nếu cần giới hạn thời gian, đối tượng, số lần hoặc tài khoản, hãy đưa logic xác thực vào **wrapper/facade**, không nghĩ `bindTo` tự tạo cơ chế revocation.

Lưu ý: biến `approvedVault` và import `MethodHandle/MethodType` là thành phần của ngữ cảnh snippet, **không phải** một file Java độc lập. Phần demo mục 7 là chương trình hoàn chỉnh có thể chạy.

### 8.3. Nếu bắt buộc phải chuyển một `Lookup`

Một nguyên tắc audit ngắn:

1. Tạo lookup **trong class thực sự sở hữu quyền** bằng `MethodHandles.lookup()`.
2. Liệt kê chính xác các member mà adapter cần tra cứu; nếu chỉ cần public, dùng `publicLookup()`.
3. Nếu cần package/module, hạ `PRIVATE` hoặc `MODULE` theo phạm vi thật, và ghi nhận **quyền vẫn còn**.
4. Xem `lookupModes()`, `lookupClass()`, `previousLookupClass()` và kết quả thử `find...` cho những case hợp lệ/không hợp lệ.
5. Tránh đưa full lookup vào public static field, global registry, serialized content hoặc extension API không kiểm soát.
6. Với module khác, không thêm `opens` vô điều kiện nếu chỉ cần một API public hoặc một operation đã tạo.
7. Coi `MethodHandle`/`VarHandle`/reflective `Method` đã cấp là capability cần quản lý, không chỉ `Lookup`.
8. Review và test lại khi module graph, package exports/opens hoặc JDK thay đổi.

### 8.4. Không coi reduced lookup là cơ chế sandbox code đối nghịch

`Lookup` có giới hạn chỉ hạn chế **những handle mà object ấy có thể tạo**. Nó **không tước** các API mà code nhận có thể tự gọi, không ngăn I/O, network, JNI hoặc reflection theo quyền khác đã có và không bảo vệ khỏi dependency/plugin độc hại có quyền chạy trong **cùng tiến trình**. Vì `SecurityManager` đã bị vô hiệu hóa từ Java 24, muốn chạy code thực sự không tin cậy thì phải đánh giá **process isolation, permissions, container/OS sandboxing và giao thức trao đổi**. Đây là biện pháp bảo vệ hệ thống, không phải một khả năng của `dropLookupMode`.

## 9. Lỗi phổ biến và cách tránh

| Nhầm lẫn | Vì sao sai | Hướng xử lý |
|---|---|---|
| `MethodHandles.lookup()` gọi trong helper trả quyền của class nghiệp vụ | Lookup ghi nhận **class trực tiếp gọi** | Tạo trong class sở hữu quyền, chỉ trao capability cần thiết |
| `Lookup` chỉ là object tiện ích, có thể công khai | Nó có thể tạo handle tới private member và các hoạt động nhạy cảm | Không expose full lookup không kiểm soát |
| `dropLookupMode(PRIVATE)` đồng nghĩa public-only | Nó có thể còn `PACKAGE` và `MODULE` | Kiểm tra modes và dùng `publicLookup` nếu chỉ cần public |
| `dropLookupMode(MODULE)` vẫn gọi được `privateLookupIn` | Đã mất `MODULE` và `PRIVATE` | Chỉ gọi từ lookup có full privilege và module access hợp lệ |
| `in(Target.class)` luôn nâng quyền theo Target | `in` không tăng quyền; với same nest có thể còn private | Kiểm tra class/modes sau khi chuyển ngữ cảnh |
| `publicLookup()` truy cập mọi public class trên mọi module | Còn phụ thuộc package **unconditionally exported** | Kiểm tra JPMS exports và visibility |
| `exports` đủ cho private deep reflection | `exports` không có nghĩa mở private | Khi thật cần deep reflection, dùng qualified `opens`, `privateLookupIn` và review quyền |
| Chuyển một handle thì không có rủi ro bảo mật | Handle được phép gọi operation đã cấp, kể cả private/nhạy cảm | Giới hạn operation, receiver, dữ liệu, use-case và lifecycle |
| Sau khi tạo handle, giảm quyền Lookup gốc sẽ “thu hồi” handle | Access đã được kiểm tra lúc tạo handle | Thiết kế wrapper có thể revoke hoặc kiểm tra tại mỗi lần gọi |
| `hasPrivateAccess()` là API kiểm tra hiện đại nên dùng | Đã deprecated từ Java 14 | Dùng `hasFullPrivilegeAccess()` hoặc `lookupModes()` |
| Thấy `PRIVATE` bit là có thể truy cập mọi private class | Còn module reads/opens, lookup class và target visibility | Kiểm tra quyền trên từng target, không suy luận từ bitmask đơn lẻ |
| Dùng `SecurityManager` để cô lập plugin ở Java mới | Tính năng này bị vô hiệu hóa từ Java 24 | Dùng process/OS isolation và API boundary phù hợp |
| Cố ép `setAccessible(true)` để vượt JPMS | Không phải thay thế an toàn, còn chịu module encapsulation | Thiết kế `exports`/`opens` phù hợp hoặc tránh deep reflection |
| `invokeExact` lỗi `WrongMethodTypeException` nghĩa là lookup thiếu quyền | Lỗi kiểu call site, không phải factory access check | Đối chiếu `MethodType`, kiểu đối số và kiểu trả về |

## 10. Checklist cấp quyền tối thiểu

1. **Xác định trust boundary:** class/module nào là chủ sở hữu dữ liệu, adapter nào thật sự đáng tin cậy.
2. **Chọn API typed trước:** liệu một public interface hoặc callback có đủ thay cho reflection?
3. **Nếu cần Lookup, định nghĩa danh sách member được phép**; không phát full factory chỉ vì “cho tiện”.
4. **Tạo lookup đúng class:** `MethodHandles.lookup()` là caller-sensitive.
5. **Hạ quyền có chủ đích:** `publicLookup()` cho public exported types, `dropLookupMode` nếu cần một ngữ cảnh được giảm riêng.
6. **Audit modes:** xem `lookupModes()` và `hasFullPrivilegeAccess()`, không dùng `hasPrivateAccess()` deprecated.
7. **Cẩn trọng `in(Class)`:** với same nest có thể còn private; đổi class **không tự bảo đảm** hạ xuống public.
8. **`privateLookupIn` cần full privilege**, cùng các điều kiện `reads`/`opens` khi khác module; không mở package bừa bãi.
9. **Ưu tiên method handle đã chọn/bind** khi chỉ cần một operation; handle cũng phải được coi là capability và bảo vệ đúng.
10. **Kiểm thử cả quyền được phép và bị từ chối:** `findVirtual`/`findGetter` thành công ở case hợp lệ, `IllegalAccessException` ở case thiếu quyền.
11. **Không phụ thuộc việc giảm quyền để sandbox code đối nghịch**; dùng process/OS isolation khi cần.
12. **Review lại khi nâng JDK hoặc đổi module topology**, đặc biệt các API hidden class/class data, caller-sensitive và `opens`.

## Tài liệu tham khảo chính thức

- Oracle Java SE 25, `MethodHandles.Lookup` — access modes, `dropLookupMode`, `in`, `privateLookupIn`, `hasFullPrivilegeAccess`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle Java SE 25, `MethodHandles` — `lookup`, `publicLookup`, `privateLookupIn` và lời nhắc không tiết lộ full lookup: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Oracle Java SE 17, `MethodHandles.Lookup` — API ổn định trên bản JDK LTS: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle Java SE 25, `MethodHandle` — kiểm tra kiểu gọi `invokeExact` và quyền truy cập tại lúc tạo: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Oracle, `Secure Coding Guidelines for Java SE` — cách bảo vệ `MethodHandle`, `Lookup` và ranh giới với code không tin cậy; cập nhật 2025: https://www.oracle.com/java/technologies/javase/seccodeguide.html
