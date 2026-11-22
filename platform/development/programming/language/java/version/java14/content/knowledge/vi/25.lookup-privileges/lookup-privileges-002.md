# hasFullPrivilegeAccess: kết hợp quyền PRIVATE và MODULE của MethodHandles.Lookup

## Mục tiêu học tập

Trong Java, `java.lang.invoke.MethodHandles.Lookup` là một **đối tượng mang quyền truy cập** (*capability object*) dùng để tìm và tạo `MethodHandle`/`VarHandle`. Hai lookup trỏ tới cùng một class vẫn có thể có khả năng truy cập khác nhau vì chúng mang các **lookup modes** khác nhau. Một API quan trọng là:

```java
boolean full = lookup.hasFullPrivilegeAccess();
```

Phương thức này xuất hiện từ **Java 14** và vẫn được hỗ trợ trong JDK hiện hành. Nó chỉ trả `true` nếu lookup có **đồng thời**:

- Quyền `MethodHandles.Lookup.PRIVATE`.
- Quyền `MethodHandles.Lookup.MODULE`.

Không phải chỉ một trong hai, không phải chỉ `PUBLIC`, và cũng **không** phải “quyền quản trị của JVM” hay quyền truy cập mọi field trong toàn bộ ứng dụng.

Sau bài này, bạn sẽ hiểu:

1. Bản chất của `Lookup` và các mode `PRIVATE`, `MODULE`, `ORIGINAL`.
2. Cách kiểm tra quyền bằng `hasFullPrivilegeAccess()` và `lookupModes()`.
3. Vì sao `dropLookupMode(PROTECTED)` có thể **vẫn full privilege**, trong khi bỏ `PRIVATE` hoặc `MODULE` làm mất full privilege.
4. Vì sao `Lookup.in(...)`, `privateLookupIn(...)`, `publicLookup()` cho kết quả khác nhau.
5. Điều kiện mở package và module readability khi lấy lookup riêng tư **qua ranh giới module**.
6. Cách chạy chương trình Java 17+ có kiểm chứng quyền thực tế bằng `findStatic`, không chỉ so sánh bitmask.
7. Cách tránh dùng `hasPrivateAccess()` đã bị deprecated và tránh rò rỉ lookup mạnh cho code không đáng tin.

**Phạm vi hiện hành:** Tất cả ví dụ sử dụng **JDK 17 trở lên**, API chính thức trong `java.base`, không cần `--enable-preview`. Những phần chỉ có mục đích mô tả mô hình module được ghi rõ là ví dụ minh họa, không giả làm chương trình có thể biên dịch độc lập.

## 1. Lookup không phải Java reflection không kiểm soát

Trong `java.lang.invoke`, một lookup đại diện cho **class nhân danh nó thực hiện tra cứu member** cùng với những quyền đã được cấp. Chẳng hạn:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
```

`MethodHandles.lookup()` là phương thức **caller-sensitive**: quyền và `lookupClass()` được xác định từ **class gọi nó**, không phải một “siêu quyền” tự do dùng để mở mọi class khác.

Lookup tạo được `MethodHandle` như:

```java
MethodHandle handle = lookup.findVirtual(
        String.class,
        "length",
        MethodType.methodType(int.class));
```

Đây là đoạn mã **trong một method** với import `java.lang.invoke.MethodHandle` và `java.lang.invoke.MethodType`. `findVirtual` kiểm tra quyền tại lúc tạo handle. Khi handle đã được tạo thành công, mỗi lần gọi handle không lặp lại toàn bộ kiểm tra truy cập như lần tạo ban đầu.

Điểm này rất quan trọng: một object `Lookup` có quyền riêng tư phải được coi như một **capability nhạy cảm**. Chuyển nó sang thư viện/plugin không tin cậy có thể cho phép code đó tạo handle truy cập những member mà nó vốn không tự tìm được.

## 2. Công thức của hasFullPrivilegeAccess()

Theo Javadoc, định nghĩa của phương thức là:

```java
boolean full = lookup.hasFullPrivilegeAccess();
```

Nó tương đương về điều kiện logic với:

```java
int modes = lookup.lookupModes();

boolean hasPrivate =
        (modes & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule =
        (modes & MethodHandles.Lookup.MODULE) != 0;

boolean fullByBits = hasPrivate && hasModule;
```

Hai code fence này là **đoạn minh họa đặt trong method**, với biến/import đã được thiết lập; chương trình chạy đầy đủ nằm ở mục 7.

**Bảng chân trị:**

| Có `PRIVATE` | Có `MODULE` | `hasFullPrivilegeAccess()` | Ý nghĩa |
| --- | --- | --- | --- |
| `false` | `false` | `false` | Không có cả hai quyền bắt buộc |
| `false` | `true` | `false` | Có ngữ cảnh module nhưng không có quyền private |
| `true` | `false` | `false` | Có quyền private của lookup class nhưng đã mất quyền module |
| `true` | `true` | `true` | Đủ điều kiện *full privilege access* |

**Điểm đặc biệt:** Hai mode `PRIVATE` và `MODULE` **độc lập về khái niệm**. Chúng không có quan hệ “có `PRIVATE` thì đương nhiên có `MODULE`” ở mọi lookup. Một lookup được dịch qua module khác bằng `privateLookupIn` có thể có `PRIVATE` mà **không** có `MODULE`.

**Không suy ra sai:** `full == true` **không** chứng minh được truy cập tất cả member private trong toàn JVM. Các bước tra cứu cụ thể vẫn bị ràng buộc bởi `lookupClass`, nest, module readability, exports/opens, tên member và chữ ký của method/field.

## 3. PRIVATE là quyền gì?

`Lookup.PRIVATE` đại diện cho khả năng truy cập member `private` **trong phạm vi mà lookup class được Java cho phép**, gồm các member private của lookup class và **nestmates** liên quan.

Ví dụ với hai class nằm cùng một **nest**:

```java
public final class Outer {
    private static String token() {
        return "outer";
    }

    static final class Inner {
        private static String token() {
            return "inner";
        }
    }
}
```

Đoạn này chỉ minh họa cách class lồng nhau cùng nest có thể được kiểm tra quyền private phù hợp. Nó **không** có `main` độc lập. Một lookup đầy đủ từ `Outer` có khả năng tìm member private mà Java cho phép trong nest; tuy nhiên một lookup đã bị `dropLookupMode(PRIVATE)` thì không còn quyền private tương ứng.

**Không nhầm:** `Lookup.PRIVATE` là **bit quyền của lookup**, còn modifier `private` là **mức hiển thị khai báo của member**. Member private không tự trở nên public chỉ vì có một lookup nào đó trong ứng dụng có bit `PRIVATE`.

Một lookup chỉ có `PRIVATE` nhưng thiếu `MODULE` có thể xuất hiện sau khi thực hiện deep reflection hợp lệ xuyên module; nó có thể tra cứu member private của **target lookup class** nhưng vẫn **không được xem là full-privilege lookup** theo tiêu chí của API.

## 4. MODULE là quyền gì?

`Lookup.MODULE` xác nhận quan hệ đặc biệt giữa nguồn gốc quyền truy cập và **module của lookup class hiện tại**. Javadoc mô tả lookup mang mode này là lookup mà original creator có thể được xác thực thuộc cùng module với lookup class.

Nó hữu ích vì Java Platform Module System (JPMS) phân biệt:

- Module nào **reads** module nào.
- Package nào được **exports** để truy cập public API ở nơi khác.
- Package nào được **opens** để cho phép *deep reflection* trong phạm vi cần thiết.

Có `MODULE` **không có nghĩa** có quyền private của mọi class trong cùng module. Ngược lại, lookup có `MODULE` nhưng thiếu `PRIVATE` không đủ để được dùng làm nguồn cho `MethodHandles.privateLookupIn(...)`.

Vì thế việc kiểm tra **cả hai** mode mới đủ điều kiện “full privilege”. Quy tắc này bảo vệ khả năng chứng minh nguồn gốc quyền trong trường hợp một lookup đi qua ranh giới module.

### Ví dụ MODULE còn nhưng PRIVATE đã mất

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup moduleOnlyRelative =
        full.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

`moduleOnlyRelative` **không nhất thiết chỉ chứa đúng một bit MODULE**: nó thường còn các mode như `PUBLIC` và `PACKAGE`. Tên biến chỉ nhằm nhấn mạnh **MODULE vẫn còn, PRIVATE đã mất**. Dù vậy:

```java
moduleOnlyRelative.hasFullPrivilegeAccess(); // false
```

Không thể tạo lại bit `PRIVATE` từ chính lookup đã bị downgrade chỉ bằng `in(...)`. Muốn có lookup mạnh hơn phải đi qua **nguồn quyền hợp lệ**, ví dụ gọi `MethodHandles.lookup()` từ đúng caller hoặc `privateLookupIn` với một lookup nguồn còn đủ quyền và đáp ứng điều kiện module.

## 5. Các mode khác không thay thế cặp PRIVATE + MODULE

`Lookup.lookupModes()` trả một **bitmask**. Các mode được JDK 17 hỗ trợ gồm:

| Mode | Vai trò tóm tắt | Có bắt buộc cho `hasFullPrivilegeAccess()`? |
| --- | --- | --- |
| `PUBLIC` | Truy cập các member/type public theo kiểm tra module | Không phải điều kiện được kiểm tra trực tiếp |
| `PRIVATE` | Khả năng truy cập private trong đúng lookup context | **Có** |
| `PROTECTED` | Quyền liên quan protected member phù hợp Java access rules | Không |
| `PACKAGE` | Quyền package-private trong runtime package | Không |
| `MODULE` | Quyền xác thực module của lookup class | **Có** |
| `UNCONDITIONAL` | Truy cập public type trong package export vô điều kiện, điển hình `publicLookup()` | Không |
| `ORIGINAL` | Lookup gốc từ caller/VM bootstrap; có năng lực bổ sung với caller-sensitive methods | Không |

Vì các mode được biểu diễn bằng **bit** chứ không phải thứ tự cấp bậc đơn giản, không nên dùng so sánh số học như `lookupModes() >= Lookup.PRIVATE` để suy ra mức quyền.

Cũng không nên chỉ kiểm tra `lookupModes() != 0`: có một mode `PUBLIC` không tự tạo quyền private và module.

**Khi cần điều kiện full-privilege:** ưu tiên gọi trực tiếp `hasFullPrivilegeAccess()`. Việc kiểm tra bitmask nên dùng trong bài học, chẩn đoán hoặc khi cần phân biệt cụ thể mode nào đang hiện diện.

## 6. ORIGINAL khác full privilege access

Từ Java 16, JDK có mode `Lookup.ORIGINAL`. Mode này đánh dấu lookup gốc được tạo từ `MethodHandles.lookup()` của caller (hoặc một bootstrap do VM tạo) và cho phép một số năng lực bổ sung, chẳng hạn tạo method handle cho một số **caller-sensitive methods**.

**Điểm dễ nhầm:** `hasFullPrivilegeAccess()` chỉ đòi hỏi `PRIVATE` + `MODULE`; **không đòi `ORIGINAL`**.

Ví dụ:

```java
MethodHandles.Lookup original = MethodHandles.lookup();
MethodHandles.Lookup withoutProtected =
        original.dropLookupMode(MethodHandles.Lookup.PROTECTED);
```

`dropLookupMode(PROTECTED)` theo Javadoc làm mất `PROTECTED` và `ORIGINAL`, nhưng vẫn có thể **giữ cả PRIVATE và MODULE**, nên:

```java
withoutProtected.hasFullPrivilegeAccess(); // true
```

Việc không còn `ORIGINAL` có thể giới hạn hành vi với caller-sensitive methods dù `hasFullPrivilegeAccess()` vẫn là `true`. Điều này cho thấy “full privilege access” là **thuật ngữ có định nghĩa riêng của API**, không có nghĩa bitmask chứa tất cả mode có thể có.

Trong chương trình mục 7, bạn sẽ thấy một dòng `ORIGINAL=false` nhưng `FULL=true`. Đây không phải lỗi của JDK.

## 7. Chương trình Java 17+ chạy độc lập với stdout chính xác

Ví dụ kiểm chứng cả **bitmask** và **hành vi tra cứu member private**. Chúng ta dùng hai top-level class nằm trong **cùng package mặc định và cùng unnamed module** nhưng **khác nest**; nhờ đó `Lookup.in(...)` sẽ mất quyền `PRIVATE` khi chuyển từ class này sang class kia, còn `privateLookupIn(...)` có thể tạo lookup private mới với những điều kiện hợp lệ.

**Tạo một file duy nhất tên `LookupPrivilegeDemo.java`**, chứa cả hai top-level class như sau:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;
import java.lang.invoke.MethodType;

public final class LookupPrivilegeDemo {
    private LookupPrivilegeDemo() {
    }

    private static String secret() {
        return "main-secret";
    }

    private static void show(String name, Lookup lookup) {
        int modes = lookup.lookupModes();
        boolean privateMode = (modes & Lookup.PRIVATE) != 0;
        boolean moduleMode = (modes & Lookup.MODULE) != 0;
        boolean originalMode = (modes & Lookup.ORIGINAL) != 0;
        boolean full = lookup.hasFullPrivilegeAccess();

        if (full != (privateMode && moduleMode)) {
            throw new AssertionError("Invalid privilege calculation");
        }

        System.out.printf(
                "%s PRIVATE=%s MODULE=%s ORIGINAL=%s FULL=%s%n",
                name, privateMode, moduleMode, originalMode, full);
    }

    private static void expectDenied(
            String name, Lookup lookup, Class<?> target)
            throws NoSuchMethodException {

        try {
            lookup.findStatic(
                    target,
                    "secret",
                    MethodType.methodType(String.class));
            throw new AssertionError("Access unexpectedly granted");
        } catch (IllegalAccessException expected) {
            System.out.println(name + "=true");
        }
    }

    public static void main(String[] args) throws Throwable {
        Lookup original = MethodHandles.lookup();
        Lookup dropProtected =
                original.dropLookupMode(Lookup.PROTECTED);
        Lookup dropPrivate =
                original.dropLookupMode(Lookup.PRIVATE);
        Lookup dropModule =
                original.dropLookupMode(Lookup.MODULE);
        Lookup publicLookup = MethodHandles.publicLookup();

        Lookup inOtherNest = original.in(Vault.class);
        Lookup privateForVault =
                MethodHandles.privateLookupIn(Vault.class, original);

        show("original", original);
        show("drop-protected", dropProtected);
        show("drop-private", dropPrivate);
        show("drop-module", dropModule);
        show("public", publicLookup);
        show("in-other-nest", inOtherNest);
        show("private-lookup-in", privateForVault);

        MethodHandle own = original.findStatic(
                LookupPrivilegeDemo.class,
                "secret",
                MethodType.methodType(String.class));
        System.out.println("own-secret=" + (String) own.invokeExact());

        expectDenied(
                "drop-private-denied",
                dropPrivate,
                LookupPrivilegeDemo.class);

        expectDenied(
                "in-other-nest-denied",
                inOtherNest,
                Vault.class);

        MethodHandle target = privateForVault.findStatic(
                Vault.class,
                "secret",
                MethodType.methodType(String.class));
        System.out.println("vault-secret=" + (String) target.invokeExact());

        try {
            MethodHandles.privateLookupIn(Vault.class, dropModule);
            throw new AssertionError("Downgraded lookup accepted");
        } catch (IllegalAccessException expected) {
            System.out.println("drop-module-privateLookupIn-denied=true");
        }
    }
}

final class Vault {
    private Vault() {
    }

    private static String secret() {
        return "vault-secret";
    }
}
```

### Biên dịch/chạy bằng JDK 17 trở lên

Tại thư mục chứa file:

```bash
javac --release 17 LookupPrivilegeDemo.java
java LookupPrivilegeDemo
```

**Stdout mong đợi chính xác** khi chạy đúng chương trình bằng JDK 17+:

```text
original PRIVATE=true MODULE=true ORIGINAL=true FULL=true
drop-protected PRIVATE=true MODULE=true ORIGINAL=false FULL=true
drop-private PRIVATE=false MODULE=true ORIGINAL=false FULL=false
drop-module PRIVATE=false MODULE=false ORIGINAL=false FULL=false
public PRIVATE=false MODULE=false ORIGINAL=false FULL=false
in-other-nest PRIVATE=false MODULE=true ORIGINAL=false FULL=false
private-lookup-in PRIVATE=true MODULE=true ORIGINAL=false FULL=true
own-secret=main-secret
drop-private-denied=true
in-other-nest-denied=true
vault-secret=vault-secret
drop-module-privateLookupIn-denied=true
```

### Tại sao từng kết quả như vậy?

1. **`original`:** `MethodHandles.lookup()` gọi ngay trong `LookupPrivilegeDemo` tạo lookup gốc của class này, chứa `PRIVATE`, `MODULE` và `ORIGINAL`. Nó có quyền tạo handle truy cập chính method private `secret()` của mình.
2. **`drop-protected`:** `dropLookupMode(PROTECTED)` loại `PROTECTED` và `ORIGINAL` nhưng không loại `PRIVATE` hoặc `MODULE`. Vì vậy `FULL=true` dù `ORIGINAL=false`.
3. **`drop-private`:** khi mất `PRIVATE`, `MODULE` vẫn còn, nhưng điều kiện *hai bit* không còn đúng. `FULL=false`. Tra cứu method private của `LookupPrivilegeDemo` qua lookup này ném `IllegalAccessException`.
4. **`drop-module`:** bỏ `MODULE` đồng thời kéo theo việc mất `PACKAGE` và `PRIVATE` theo quy tắc `dropLookupMode`. Vì vậy hai bit đều false và lookup này **không** được dùng làm input thành công cho `privateLookupIn(Vault.class, ...)`.
5. **`public`:** `MethodHandles.publicLookup()` là lookup có quyền public/unconditional phù hợp, không có `PRIVATE` hay `MODULE`. Nó không phải lựa chọn để truy cập member private.
6. **`in-other-nest`:** `Lookup.in(Vault.class)` chuyển lookup class sang `Vault` ở **cùng unnamed module, cùng package**, nhưng hai top-level class là **hai nest khác nhau**. Vì vậy `PRIVATE` bị mất, `MODULE` còn, `FULL=false`; method private `Vault.secret()` vẫn bị từ chối.
7. **`private-lookup-in`:** `MethodHandles.privateLookupIn(Vault.class, original)` được phép do caller lookup có đủ quyền và `Vault` ở cùng module. Kết quả có `PRIVATE` + `MODULE`, nên `FULL=true`; nó **không** có `ORIGINAL`, nhưng vẫn tạo được method handle cho method private của `Vault`.
8. `expectDenied` kiểm tra quyền thật bằng việc thử `findStatic` và chỉ in `...=true` khi xảy ra **`IllegalAccessException`**. Nếu quyền bị cấp ngoài dự kiến, chương trình ném `AssertionError` thay vì giả vờ QA đạt.
9. `MethodHandle.invokeExact()` cần đúng chữ ký; cast `(String)` giúp chỉ rõ expected return type. Nếu method không tồn tại hoặc sai chữ ký, code không tự diễn giải thành “không có private access”.

**Đây là một chương trình chạy độc lập**, không phụ thuộc module-info, file JAR bên ngoài hay cấu hình mở package của hệ thống. Nó sử dụng **hai top-level class trong cùng một file** đúng quy tắc Java (chỉ `LookupPrivilegeDemo` khai báo `public`).

## 8. Lookup.in() không phải cách nâng quyền

`lookup.in(Target.class)` chuyển **ngữ cảnh lookup class** sang `Target`, nhưng theo tài liệu nó **không bao giờ tăng quyền** so với lookup cũ.

Các tình huống thường gặp:

| Chuyển lookup class sang... | Quyền có thể mất | Kết quả với `hasFullPrivilegeAccess()` |
| --- | --- | --- |
| Chính class hiện tại | Có thể giữ nguyên | Thường `true` nếu nguồn full |
| Class **cùng nest**, lookup nguồn còn private | Có thể giữ `PRIVATE` và `MODULE`; `ORIGINAL` bị mất khi đổi class | Có thể `true` |
| Class **khác nest, cùng package/module** | Mất `PRIVATE` và quyền phụ thuộc nest | `false` |
| Class **khác package, cùng module** | Mất `PRIVATE`/`PACKAGE` | `false` |
| Class ở **module khác** | Mất `MODULE` và các quyền nội bộ | `false` |
| Class không truy cập được | Các quyền có thể bị rút hết | `false` |

Bảng mô tả những biến đổi thông thường từ một **lookup nguồn full**; kết quả chính xác còn phụ thuộc `lookupClass`, nest, khả năng truy cập target và các mode nguồn.

**Một nhầm lẫn phổ biến:** Đặt target vào cùng **package** không tự biến hai class thành **cùng nest**. Hai top-level class như `LookupPrivilegeDemo` và `Vault` là khác nest, dù cùng file và cùng package, nên `Lookup.in(Vault.class)` không giữ private access.

Nếu muốn tiếp cận member private của một class khác ngoài nest, **không** cố “lách” bằng `in(...)`. Dùng API `privateLookupIn(...)` khi có quyền hợp lệ và được mô-đun đích cho phép, hoặc thiết kế API công khai phù hợp.

## 9. privateLookupIn() cần đầu vào full privilege

Chữ ký API:

```java
MethodHandles.Lookup targetLookup =
        MethodHandles.privateLookupIn(
                Target.class, callerLookup);
```

Đây là đoạn minh họa: `Target` và `callerLookup` phải được định nghĩa ở scope thực tế.

Để làm deep reflection bằng `privateLookupIn(Target.class, caller)`, **caller lookup phải có cả `PRIVATE` và `MODULE`**. Nói cách khác, `caller.hasFullPrivilegeAccess()` phải `true`. Ngoài ra, target phải là một class hợp lệ, và quyền đọc/mở package theo module graph phải được thỏa mãn.

Một phương án defensive:

```java
if (!callerLookup.hasFullPrivilegeAccess()) {
    throw new IllegalArgumentException(
            "Caller lookup must have PRIVATE and MODULE");
}

MethodHandles.Lookup access =
        MethodHandles.privateLookupIn(
                Target.class, callerLookup);
```

Đây là **mã minh họa trong một method**, không tự đảm bảo lời gọi `privateLookupIn` sẽ thành công: còn phải thỏa điều kiện target class, module readability/opens, và API vẫn có thể ném `IllegalAccessException`. Trong thư viện chung, không nên ném exception tùy ý mà cần chọn cách xử lý lỗi phù hợp contract của ứng dụng.

### Target cùng module

Giả sử caller và target ở **cùng module**, và caller lookup có full privilege. `privateLookupIn` có thể tạo target lookup với:

- `PRIVATE=true`.
- `MODULE=true`.
- `hasFullPrivilegeAccess()=true`.
- `ORIGINAL=false`, vì đây không phải lookup gốc tạo bởi `MethodHandles.lookup()` trong target class.

Chương trình `LookupPrivilegeDemo` thể hiện chính xác tình huống đó với `Vault`.

### Target khác module

Giả sử caller nằm trong named module `m.client`, target nằm trong `m.provider`. Để private lookup vào class target, **ít nhất** cần:

1. `m.client` **reads** `m.provider` (ví dụ `requires m.provider;` trong module descriptor phía client).
2. `m.provider` **opens** package chứa target cho `m.client`, có thể qua `opens pkg.name to m.client;` hoặc cấu hình mô-đun tương đương được hệ thống cho phép.
3. Lookup nguồn của caller có `PRIVATE` và `MODULE`.

Khi quyền deep reflection được phép, `privateLookupIn` qua ranh giới module thường tạo lookup **có `PRIVATE` nhưng không có `MODULE`**. Vì vậy:

```text
Cross-module private lookup:
PRIVATE=true
MODULE=false
hasFullPrivilegeAccess()=false
```

Dòng trên là **mô hình kết quả của trường hợp được phép xuyên module**, không phải stdout của chương trình mục 7. Đây chính là ví dụ thực tế cho việc `PRIVATE` và `MODULE` **không đồng nhất**. Lookup trả về vẫn có thể truy cập member private của **target class**, nhưng do thiếu `MODULE` nên không thể tiếp tục dùng làm nguồn tạo một private lookup sâu hơn thông qua `privateLookupIn` ở bước khác.

**Quan trọng:** `exports` và `opens` không thay thế nhau. `exports` thường cung cấp khả năng truy cập các type/member public; `opens` phục vụ deep reflection trong những điều kiện được quy định. Không tự mở `java.base` hay toàn bộ module bằng cờ launcher chỉ để làm một bài demo: ví dụ chính ở cùng module nên không cần thao tác này.

## 10. dropLookupMode() và nguyên tắc không tự khôi phục quyền

`Lookup.dropLookupMode(int modeToDrop)` tạo **lookup mới, giảm quyền**. Nó không sửa đổi lookup nguồn. Đây là cơ sở để thư viện cấp một lookup hẹp hơn cho plugin hoặc thành phần ít tin cậy.

| Thao tác trên lookup đầy đủ | Trạng thái liên quan | Full privilege? |
| --- | --- | --- |
| Không drop gì | `PRIVATE` và `MODULE` vẫn còn | `true` |
| `dropLookupMode(PROTECTED)` | Bỏ `PROTECTED` và `ORIGINAL`, giữ `PRIVATE` + `MODULE` | `true` |
| `dropLookupMode(PRIVATE)` | Mất `PRIVATE`, còn `MODULE` | `false` |
| `dropLookupMode(PACKAGE)` | Mất `PACKAGE` và `PRIVATE`, còn `MODULE` | `false` |
| `dropLookupMode(MODULE)` | Mất `MODULE`, `PACKAGE` và `PRIVATE` | `false` |
| `dropLookupMode(PUBLIC)` | Mất mọi quyền tra cứu thông thường | `false` |

Lưu ý quan hệ mode: khi bỏ `MODULE`, Javadoc quy định kéo theo mất `PACKAGE` và `PRIVATE`. Bỏ `PACKAGE` cũng kéo theo mất `PRIVATE`. Ngược lại, **bỏ `PROTECTED` không bắt buộc mất PRIVATE/MODULE**, nên `hasFullPrivilegeAccess()` vẫn có thể đúng.

Các mode bị bỏ **không thể được nâng lại** bằng cách gọi `in(...)` hay bỏ một mode khác trên lookup đã giảm quyền. Tuy nhiên, nếu **code được tin cậy vẫn giữ reference đến lookup nguồn mạnh**, code đó vẫn có thể dùng nguồn để tạo lookup khác. Vì thế việc downgrade chỉ an toàn khi bạn **không đồng thời rò rỉ nguồn mạnh** cho component không đáng tin.

**Không nhập bitmask tuỳ ý:** `dropLookupMode(mode)` nhận **một mode hợp lệ** trong tập do API quy định, không phải một tổ hợp arbitrary như `PRIVATE | MODULE` để xóa nhiều bit cùng lúc. Muốn giảm nhiều quyền, gọi API theo quy tắc riêng (và hiểu các quyền bị kéo theo).

## 11. hasFullPrivilegeAccess khác hasPrivateAccess

Java 14 bổ sung `hasFullPrivilegeAccess()` để làm rõ ý nghĩa **PRIVATE + MODULE**. Trong JDK hiện hành, `Lookup.hasPrivateAccess()` đã được **`@Deprecated(since="14")`** và tài liệu khuyên dùng `hasFullPrivilegeAccess()` thay thế.

Lý do: tên `hasPrivateAccess` dễ khiến lập trình viên tưởng nó chỉ hỏi có mode `PRIVATE`. Theo Javadoc hiện hành, phương thức deprecated này vẫn có lịch sử/ngữ nghĩa kiểm tra cả `PRIVATE` và `MODULE`, nhưng **không nên dùng để viết code mới**.

Cần phân biệt hai câu hỏi:

- “Lookup này có bit `PRIVATE` không?” → `(lookup.lookupModes() & Lookup.PRIVATE) != 0`.
- “Lookup này có **full privilege access** không?” → `lookup.hasFullPrivilegeAccess()`.

Hai câu hỏi **không tương đương** khi một private lookup đã teleport xuyên module: nó có thể có `PRIVATE` nhưng không còn `MODULE`.

### Cũng không lấy ORIGINAL làm thay thế

`(lookup.lookupModes() & Lookup.ORIGINAL) != 0` kiểm tra một quyền **khác**, liên quan nguồn gốc lookup. Một target lookup do `privateLookupIn` tạo trong cùng module có thể **không có ORIGINAL nhưng vẫn full**. Khi viết code yêu cầu `privateLookupIn`, hãy kiểm tra tiêu chí API thực sự dùng thay vì tự yêu cầu mode mạnh hơn cần thiết.

## 12. Cách diễn giải security và module encapsulation

Tên `hasFullPrivilegeAccess` nghe như một dạng “root access”, nhưng đây là **quyền tương đối với lookup class** theo quy tắc ngôn ngữ và module.

Cụ thể:

1. Một lookup full của `MyClass` **không** thể tự ý đọc mọi private field của `java.lang.String`. Package `java.lang` trong `java.base` bị encapsulate theo module rules.
2. Nếu muốn deep reflection sang module khác, phải có **readability** và package được **opens** cho caller module, cùng những điều kiện API khác.
3. Kể cả khi full privilege, tra cứu bằng `findVirtual`, `findStatic`, `findGetter` hay `findVarHandle` còn phụ thuộc **đúng loại member, tên và chữ ký**. Sai tên có thể ném `NoSuchMethodException`/`NoSuchFieldException`; sai quyền có thể ném `IllegalAccessException`.
4. `Lookup` là một **capability**: không nên xuất một full-privilege lookup qua public API vô điều kiện. Một thư viện có thể cung cấp API thao tác cụ thể, hoặc cung cấp lookup đã giảm quyền khi cần.
5. Trong hệ thống modular, **đừng tự mở tất cả packages bằng `--add-opens`** như một biện pháp mặc định. Điều đó làm rộng bề mặt deep reflection và có thể làm che lỗi thiết kế module.
6. Việc một lookup đã tạo `MethodHandle` thành công có ý nghĩa bảo mật khác với việc gửi **lookup factory** ra ngoài: factory có thể tạo nhiều handle khác nhau trong phạm vi quyền của nó.
7. Không dựa vào `Lookup.toString()` để quyết định quyền. Chuỗi đó hữu ích debug nhưng không thay thế `lookupModes()` và `hasFullPrivilegeAccess()`.

Nếu một framework như serializer, DI container, bytecode enhancer hoặc runtime linker cần truy cập private member, hãy xác định rõ **vì sao** cần quyền đó và từ module nào. Chỉ kiểm tra `hasFullPrivilegeAccess` không đủ để đảm bảo `privateLookupIn(Target, lookup)` sẽ thành công: vẫn phải xử lý `IllegalAccessException` theo chính sách của hệ thống.

## 13. Các lỗi thường gặp và cách sửa

### Lỗi 1 — Chỉ kiểm tra PRIVATE rồi kết luận full

`(modes & Lookup.PRIVATE) != 0` chỉ kiểm tra **một bit**. Khi lookup đã đi qua module khác, `MODULE` có thể bị rút. Hãy dùng `hasFullPrivilegeAccess()` để xác định tiêu chí full.

### Lỗi 2 — Chỉ kiểm tra MODULE rồi kết luận có quyền private

`MODULE` xác thực ngữ cảnh module, **không** tự cấp quyền member private. Ví dụ `dropLookupMode(PRIVATE)` còn `MODULE` nhưng không thể tìm method private.

### Lỗi 3 — Tưởng mọi bit phải còn mới có full

`dropLookupMode(PROTECTED)` có thể loại `PROTECTED` và `ORIGINAL` mà `hasFullPrivilegeAccess()` vẫn `true`. Điều kiện là PRIVATE + MODULE, **không** phải “mọi bit đều bật”.

### Lỗi 4 — Tưởng cùng package luôn là cùng nest

Hai top-level class cùng package thường **khác nest**. `Lookup.in(Target.class)` có thể làm mất PRIVATE dù MODULE vẫn còn.

### Lỗi 5 — Dùng in(Target) như cách lấy private access

`in(...)` **không nâng quyền**. Với class khác nest, dùng `privateLookupIn(...)` nếu quyền cho phép, hoặc API public phù hợp.

### Lỗi 6 — Truyền lookup thiếu PRIVATE/MODULE cho privateLookupIn

`privateLookupIn(Target.class, downgradedLookup)` có thể bị từ chối trước khi xét chi tiết target khi nguồn không full. Không thể phục hồi quyền bằng cách chuyển lookup class.

### Lỗi 7 — Đổi module mà nghĩ MODULE vẫn giữ nguyên

Lookup teleport sang module khác bị rút `MODULE`. Ngay cả khi `PRIVATE` của target còn sau một `privateLookupIn` thành công, `FULL` vẫn false.

### Lỗi 8 — Viết code mới với hasPrivateAccess()

`hasPrivateAccess()` đã deprecated từ Java 14. Đối với nhu cầu kiểm tra **full privilege**, dùng `hasFullPrivilegeAccess()`; nếu cần chỉ một mode, kiểm tra bit rõ ràng.

### Lỗi 9 — Tưởng full nghĩa là bỏ qua mọi module opens

`hasFullPrivilegeAccess()==true` chỉ cho biết khả năng của lookup nguồn. Từ chối truy cập member ở module khác vẫn có thể hợp lệ do thiếu `opens` hoặc module readability.

### Lỗi 10 — So sánh nguyên số lookupModes()

`lookupModes() == 15` hoặc `== 31` rất dễ sai vì tập mode thay đổi theo JDK, đặc biệt có `ORIGINAL`. Dùng phép mask hoặc API ngữ nghĩa thay vì phụ thuộc con số magic.

### Lỗi 11 — Truyền full lookup cho mã không tin cậy

Lookup là capability mạnh, có thể được dùng để tạo nhiều handles. Giảm quyền có chủ đích, không giữ một bản nguồn mạnh dễ truy cập công khai.

### Lỗi 12 — Thử quyền bằng method signature sai

`NoSuchMethodException` do tên/chữ ký không khớp không chứng minh permission thiếu. Đọc đúng loại exception, xác định class/lookup class/modes và test với member chắc chắn tồn tại.

## 14. Bảng QA và bài thực hành

### Checklist đánh giá quyền

| Tình huống | PRIVATE | MODULE | FULL | Kết quả cần giải thích |
| --- | --- | --- | --- | --- |
| `MethodHandles.lookup()` trong caller bình thường | Có | Có | True | Full tương đối với caller class |
| `publicLookup()` | Không | Không | False | Chỉ public/unconditional phù hợp |
| `dropLookupMode(PROTECTED)` từ full | Có | Có | True | Không đòi ORIGINAL |
| `dropLookupMode(PRIVATE)` từ full | Không | Có | False | Không còn private |
| `dropLookupMode(MODULE)` từ full | Không | Không | False | Mất module và quyền phụ thuộc |
| `in(OtherTopLevel.class)` cùng package nhưng khác nest | Không | Có | False | Không nâng/giữ private tùy tiện |
| `privateLookupIn(OtherTopLevel.class, full)` cùng module | Có | Có | True | Deep access hợp lệ trong module |
| `privateLookupIn(Target.class, full)` qua module khác nếu opens/reads hợp lệ | Có | Không | False | Private ở target nhưng không có full privilege |

### Bài 1 — Chứng minh công thức

Chạy `LookupPrivilegeDemo.java`, kiểm tra mọi dòng có `FULL` khớp `PRIVATE && MODULE`. Giải thích vì sao dòng `drop-protected` in `FULL=true` dù `ORIGINAL=false`.

### Bài 2 — Kiểm tra quyền thực tế

Thay method `Vault.secret()` bằng một method private khác và sửa đúng `MethodType`. Kiểm tra `inOtherNest` không tạo được handle, nhưng `privateForVault` tạo và gọi được. Phân biệt `IllegalAccessException` với `NoSuchMethodException`.

### Bài 3 — Thử dropLookupMode(PACKAGE)

Thêm một lookup `original.dropLookupMode(Lookup.PACKAGE)`, in PRIVATE/MODULE/FULL. Dự đoán: `PRIVATE=false`, `MODULE=true`, `FULL=false`. So sánh với `dropLookupMode(PROTECTED)`.

### Bài 4 — So sánh in() với privateLookupIn()

Dùng hai class khác nest trong cùng module. Xác định `lookupClass()` của hai lookup kết quả; ghi lại bitmask `PRIVATE/MODULE`. Giải thích vì sao `in(...)` không thể thay cho `privateLookupIn(...)`.

### Bài 5 — Nhận diện trường hợp xuyên module

Thiết kế sơ đồ hai module `m.client`, `m.provider` với `m.client` đọc `m.provider` và package target được mở có chủ đích cho `m.client`. Dự đoán mode của lookup sau `privateLookupIn`: `PRIVATE=true`, `MODULE=false`, `FULL=false`. Phân biệt **khả năng đọc member private của target** với **khả năng tạo thêm private lookup ở nơi khác**.

### Bài 6 — Thiết kế API ít quyền

Bạn viết một thư viện chỉ cần gọi một public static method. Nên chuyển `MethodHandles.publicLookup()`, một `MethodHandle` đã kiểm tra hay cả full-privilege lookup ra plugin? Phân tích principle of least privilege và nguy cơ nếu để lộ lookup gốc.

**Tiêu chí hoàn thành:** Người học diễn giải chính xác `hasFullPrivilegeAccess()` là **cả PRIVATE lẫn MODULE**; phân biệt với `ORIGINAL` và `hasPrivateAccess()` deprecated; biết quyền bị rút qua `dropLookupMode`, `in`, `privateLookupIn`; và kiểm chứng được hành vi truy cập private bằng ví dụ Java hiện hành.

## 15. Tài liệu chính thức

- [Oracle Java SE 17 — MethodHandles.Lookup API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `hasFullPrivilegeAccess`, `lookupModes`, `dropLookupMode`, quyền `PRIVATE` và `MODULE`, `hasPrivateAccess` deprecated.
- [Oracle Java SE 26 — MethodHandles.Lookup API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): xác nhận các quy tắc vẫn hiện hành và bảng quyền lookup trong JDK mới.
- [Oracle Java SE 17 — MethodHandles API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup` và `privateLookupIn`.
- [Oracle Java SE 17 — MethodHandle API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact` và các lưu ý về đúng method type.
- [Java Platform Module System — JLS, Programs and Compilation Units](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): khai báo `requires`, `exports`, `opens` trong named modules.

**Ghi nhớ:** `lookup.hasFullPrivilegeAccess()` trả `true` **chỉ khi lookup có đồng thời hai mode `PRIVATE` và `MODULE`**. Nó không đòi `ORIGINAL` và không trao quyền truy cập toàn bộ JVM. Khi làm việc với method handles, hãy hiểu nguồn gốc lookup, module/nest của target, giới hạn sau khi downgrade và nguyên tắc **chỉ trao đúng quyền cần thiết**.