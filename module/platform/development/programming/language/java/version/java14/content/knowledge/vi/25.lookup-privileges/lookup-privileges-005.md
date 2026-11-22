# Quan hệ giữa Lookup.in(), MethodHandles.privateLookupIn() và Lookup.dropLookupMode()

## 1. Mục tiêu: di chuyển ngữ cảnh, xin quyền hợp lệ và chủ động thu hẹp quyền

Trong Java, `java.lang.invoke.MethodHandle` đại diện cho một lời gọi hoặc thao tác truy cập thành viên đã được liên kết. Để tìm một method handle cho method, constructor hoặc field, ta thường bắt đầu với đối tượng **`MethodHandles.Lookup`**.

Một `Lookup` **không phải** công cụ bỏ qua Java access control. Nó mang **ngữ cảnh truy cập (lookup class)** và **một tập quyền truy cập (lookup modes)**; khi tạo handle bằng `findVirtual`, `findStatic`, `findGetter`, `findConstructor`... Java xét thành viên đó có được truy cập từ ngữ cảnh này hay không. Sau khi handle đã được tạo hợp lệ, mỗi lần gọi handle không làm lại phép kiểm tra quyền như mỗi lần gọi reflective `Method.invoke`.

Ba thao tác trọng tâm có mục đích khác nhau:

1. **`lookup.in(Target.class)`**: chuyển lookup class sang `Target`, nhưng **không cấp thêm quyền**; quyền có thể bị loại theo ranh giới nest, package và module.
2. **`MethodHandles.privateLookupIn(Target.class, callerLookup)`**: xin một lookup có quyền truy cập **private** trong class đích, **chỉ khi** caller đã có đủ quyền và điều kiện modules/`opens` cho phép. Đây là phép kiểm tra quyền rõ ràng, không phải “hack bypass private”.
3. **`lookup.dropLookupMode(mode)`**: tạo một lookup cùng lookup class nhưng **cố ý bỏ một phần khả năng**, thường để trao cho code khác một capability giới hạn.

**Tư duy đúng:** `in` = đổi điểm nhìn **không tăng quyền**; `privateLookupIn` = **chuyển ngữ cảnh có kiểm tra điều kiện cấp quyền private**; `dropLookupMode` = **giảm quyền có chủ ý**. Không thể gọi `in` sau khi đã hạ quyền rồi lấy lại những mode bị mất.

Các API này tiếp tục được tài liệu hóa trong **Java SE 17/21/25/26**. Ví dụ chính của bài biên dịch bằng **Java 17+**. Đặc biệt, bit `ORIGINAL` là chi tiết API được bổ sung từ **Java 16**; bài dùng semantics hiện đại thay vì sao chép mô hình mode chưa đầy đủ của JDK 14.

## 2. Lookup là một capability và quyền được xét khi tạo handle

Lấy lookup từ class đang gọi:

~~~java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

Đoạn trên là **mã minh họa bên trong class/method**, không phải file chạy độc lập. `MethodHandles.lookup()` là **caller-sensitive**: lookup class gắn với class thực sự gọi phương thức, không phải class mà code tình cờ nhắc tới trong một biểu thức.

Ví dụ trong `com.acme.Service`, một lookup được lấy bằng `MethodHandles.lookup()` có thể có quyền với những thành viên private của chính class đó (và nestmates theo quy tắc của Java). Nhưng nếu chuyển nó sang một class không liên quan, ta phải tôn trọng quyền Java và giới hạn module.

Một số thành phần quan trọng:

| API / thuộc tính | Ý nghĩa |
| --- | --- |
| `lookup.lookupClass()` | Class dùng làm ngữ cảnh chính khi kiểm tra khả năng truy cập |
| `lookup.previousLookupClass()` | Class nguồn trước đó khi lookup **được chuyển qua module khác**, hoặc `null` nếu chưa có nguồn module trước |
| `lookup.lookupModes()` | Bit mask mô tả các mode hiện có |
| `lookup.hasFullPrivilegeAccess()` | Cho biết lookup có **cả `PRIVATE` và `MODULE`**, thường gọi là full privilege access |
| `MethodHandles.lookup()` | Lookup xuất phát từ class gọi với tập quyền phù hợp với caller |
| `MethodHandles.publicLookup()` | Lookup tối thiểu cho các public type/member đủ điều kiện export vô điều kiện; có mode `UNCONDITIONAL` |

**Không dùng `hasPrivateAccess()` trong code mới:** phương thức đó đã bị **deprecated** vì kiểm tra riêng bit `PRIVATE` không có nghĩa lookup đồng thời còn quyền `MODULE` để được xem là full-privilege. Dùng `hasFullPrivilegeAccess()` và `lookupModes()` khi cần.

Các mode thường thấy:

| Mode | Vai trò khái quát |
| --- | --- |
| `PUBLIC` | Truy cập public members/types trong phạm vi rules về module readability/export |
| `MODULE` | Quyền truy cập gắn với **cùng module** của lookup class |
| `PACKAGE` | Quyền truy cập **cùng runtime package** |
| `PRIVATE` | Khả năng truy cập private trên lookup class / nestmates trong phạm vi hợp lệ |
| `PROTECTED` | Quyền cho protected members, kèm các ràng buộc class/package/receiver |
| `UNCONDITIONAL` | Public lookup: public types trong package được **unconditionally exported** |
| `ORIGINAL` | Lookup đến từ class gốc/VM bootstrap, thêm những khả năng đặc biệt liên quan caller-sensitive; **Java 16+** |

Mỗi mode là một **bit**, xem bằng:

~~~java
boolean hasPrivate =
        (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
~~~

Có một mode trong bit mask **không thay thế** các kiểm tra về class visibility, nestmates, package, module `exports/opens` hoặc kiểu member. Không nên đọc một bit rồi kết luận lookup truy cập được “bất kỳ private member ở bất kỳ đâu”.

## 3. `Lookup.in(Target.class)`: đổi lookup class mà không nâng quyền

Cú pháp:

~~~java
MethodHandles.Lookup moved = lookup.in(Target.class);
~~~

Kết quả (thông thường) là một lookup dùng `Target.class` làm **lookup class mới**, nhưng **không bao giờ có nhiều quyền hơn** lookup ban đầu. Việc chuyển target qua các ranh giới có thể mất quyền:

| Quan hệ giữa class nguồn và class đích | Quyền có thể bị mất |
| --- | --- |
| **Cùng chính lookup class** | Không thay đổi; có thể trả lại chính lookup ban đầu |
| Class khác nhưng **cùng nest** | Mất `ORIGINAL`; `PRIVATE` có thể giữ theo quan hệ nestmate |
| Class khác, **khác nest** nhưng cùng runtime package | Mất `PRIVATE` (và các quyền đặc biệt như `ORIGINAL`); vẫn có thể giữ `PACKAGE`/`MODULE` |
| **Khác runtime package**, cùng module | Mất `PACKAGE` và khả năng private do cùng nest/package không còn; `MODULE` có thể giữ |
| **Khác module** | Mất `MODULE`; thường chỉ còn các khả năng public chung trong phạm vi truy cập liên module |
| Target không accessible từ lookup gốc | Lookup kết quả có thể **không còn mode nào**, kể cả public |

Lưu ý: khi chuyển class, `PROTECTED` cũng chịu quy tắc riêng về inheritance/package; không nên coi nó được giữ nguyên chỉ vì tên thành viên là `protected`.

### Cùng nest và cùng package không phải là một

Java **nestmates** cho phép những class cùng một nest được truy cập private của nhau theo quy tắc ngôn ngữ/JVM. Hai class **cùng package** nhưng **khác nest** thì không tự được đọc private của nhau.

Vì vậy:

~~~java
MethodHandles.Lookup nest =
        MethodHandles.lookup().in(Outer.Nested.class);
~~~

có thể còn `PRIVATE` khi `Nested` là nestmate của class gọi và lookup gốc có đầy đủ quyền. Ngược lại, chuyển sang một **top-level class khác** dù ở cùng package sẽ không tự có quyền private.

**Quan trọng:** `in` không phải API “lấy private lookup của bất kỳ class”. Khi cần private access hợp lệ trên class đích ngoài nest, dùng **`MethodHandles.privateLookupIn`** và chấp nhận điều kiện bảo mật của nó.

### Chuyển module bằng `in` và `previousLookupClass()`

Khi `lookup.in(Target.class)` chuyển từ class C trong module M1 sang class T trong module M2 khác M1:

- Lookup mới ghi **T là lookup class** và **C là previous lookup class**.
- Quyền `MODULE` bị loại, các quyền truy cập không-public có thể bị thu hẹp mạnh.
- Public type/member được phép truy cập phải thỏa các điều kiện **đối với cả lookup class và previous lookup class** khi previous có mặt.
- Chuyển qua một **module thứ ba** không phải module hiện tại hay module trước đó có thể loại **tất cả** các quyền.

Quy tắc này ngăn code được trao một lookup public liên module sử dụng việc `in(A).in(B).in(C)` để vượt qua yêu cầu về module readability hoặc exports. Đặc biệt, **chuyển ngược về class ban đầu không khôi phục quyền private đã mất**.

## 4. `privateLookupIn(Target.class, caller)`: cấp lookup private có kiểm tra điều kiện

Cú pháp đầy đủ:

~~~java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup privateOnTarget =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

Đây là phương thức **static của `MethodHandles`**, không phải instance method `callerLookup.privateLookupIn(...)`. `Target.class` phải là class/interface hợp lệ, không phải primitive, void hoặc array class.

### Điều kiện bắt buộc ở lookup nguồn

`callerLookup` cần có **cả hai mode**:

- `PRIVATE`, và
- `MODULE`.

Đó chính là khái niệm **full privilege access** cho phép chứng minh nguồn gốc lookup và thực hiện các kiểm tra về module. Một lookup chỉ còn `MODULE` nhưng không `PRIVATE`, hoặc chỉ còn `PRIVATE` nhưng không `MODULE`, **không đủ** để gọi `privateLookupIn` thành công.

Hệ quả thực tế:

~~~java
MethodHandles.Lookup base = MethodHandles.lookup();
MethodHandles.Lookup limited =
        base.dropLookupMode(MethodHandles.Lookup.PRIVATE);

// Không đủ PRIVATE để xin lookup private khác:
MethodHandles.privateLookupIn(Target.class, limited); // IllegalAccessException
~~~

Đoạn này là **minh họa lỗi có chủ đích**, không phải file độc lập. Phần ví dụ chạy được bên dưới sẽ bắt `IllegalAccessException` đúng cách.

### Trường hợp class đích trong **cùng module**

Nếu caller có `PRIVATE` + `MODULE` và target thuộc **cùng module**, `privateLookupIn` có thể tạo một lookup có `PRIVATE` trên target. Kết quả có full privilege access đối với class đích, nhưng **không có `ORIGINAL`**.

Điều này có thể hợp lệ cả khi target ở package khác trong cùng module: điều kiện `opens` giữa các module **không phát sinh** nếu ta không vượt module boundary. Dù vậy quyền nguồn vẫn phải hợp lệ.

### Trường hợp class đích thuộc **module khác**

Giả sử caller ở module **M1**, target ở module **M2**. Cần đồng thời:

1. Lookup nguồn có **`PRIVATE` và `MODULE`**.
2. Module M1 **`reads` M2** (thường qua `requires m2;` hoặc quan hệ readability được thiết lập hợp lệ).
3. Module M2 **`opens` package chứa target** cho M1 (`opens p;` hoặc `opens p to m1;` / cơ chế mở package hợp lệ).

`exports` **không thay thế** `opens` khi yêu cầu **deep private access**. Một public class nằm trong package được export cho M1 vẫn có thể **không cho** M1 nhận private lookup nếu package đó không được mở.

Khi thành công **qua module khác**:

- `lookupClass()` của kết quả là target.
- `previousLookupClass()` ghi caller class trước khi chuyển.
- Kết quả có `PRIVATE` trên target, nhưng **mất `MODULE`**.
- Vì thiếu `MODULE`, kết quả **không có full privilege access** và **không thể dùng tiếp làm nguồn để `privateLookupIn` lần thứ hai**.

Đây là khác biệt dễ bỏ sót: *private lookup* khác với *full privilege lookup*. **Có quyền PRIVATE trong module đích** không tự động có quyền MODULE để cấp tiếp một private lookup khác.

### Thiết lập module-info (ví dụ kiến trúc)

Giả sử ứng dụng modular có hai module:

~~~java
// module-info.java của module m.vault:
module m.vault {
    exports vault.api;
    opens vault.api to m.client;
}
~~~

~~~java
// module-info.java của module m.client:
module m.client {
    requires m.vault;
}
~~~

Các khối trên là **hai file module-info khác nhau ở hai module**, không phải một file Java duy nhất. Module `m.vault` cho client đọc API công khai thông qua `exports` và cho phép deep reflection trên package cụ thể qua `opens ... to m.client`. Đây là thiết lập minh họa **giới hạn mở package cho đúng module cần thiết**, không nên mặc định `open module m.vault` để phơi toàn bộ package.

Trong class ở `m.client`:

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(SecretBox.class, caller);

boolean hasPrivate =
        (deep.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule =
        (deep.lookupModes() & MethodHandles.Lookup.MODULE) != 0;

// Sau một lần chuyển thành công qua module khác:
// hasPrivate == true, hasModule == false.
~~~

Đây là **mã minh họa trong class** có class `SecretBox` hợp lệ thuộc package `vault.api`. Những kết luận về quyền dựa trên **Javadoc của Java 17/25**, không phải số đo từ một file modular đã được chạy thử trong bài này.

**Cảnh báo phân quyền:** việc `opens` một package cho module khác trao quyền rất mạnh. Javadoc lưu ý lookup này còn có thể định nghĩa classes trong runtime package đích theo điều kiện tương ứng. Chỉ mở package cho những module đáng tin và cần thiết, không thêm `--add-opens ...=ALL-UNNAMED` một cách máy móc để “chữa” mọi lỗi truy cập.

## 5. `dropLookupMode(mode)`: bỏ quyền có chủ ý và có thể kéo theo nhiều mode

Cú pháp:

~~~java
MethodHandles.Lookup restricted =
        lookup.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Method tạo ra một lookup cùng lookup class như đầu vào, nhưng **không còn** mode được yêu cầu. Điều quan trọng là một số mode có quan hệ phụ thuộc, vì vậy **có thể mất thêm các mode khác**. Đặc tả Java 17+ nêu:

| Gọi trên lookup thông thường | Hiệu ứng |
| --- | --- |
| `dropLookupMode(PRIVATE)` | Mất `PRIVATE`; **`PROTECTED` và `ORIGINAL` cũng luôn bị loại** |
| `dropLookupMode(PACKAGE)` | Mất `PACKAGE` **và `PRIVATE`**; đồng thời mất `PROTECTED`, `ORIGINAL` |
| `dropLookupMode(MODULE)` | Mất `MODULE`, `PACKAGE` và `PRIVATE`; đồng thời mất `PROTECTED`, `ORIGINAL` |
| `dropLookupMode(PUBLIC)` | Trên lookup thông thường, **không còn quyền truy cập** |
| `dropLookupMode(PROTECTED)` | Bỏ `PROTECTED` và `ORIGINAL`; có thể giữ `PRIVATE` và `MODULE` |
| `dropLookupMode(ORIGINAL)` | Bỏ `ORIGINAL` (và `PROTECTED` do quy tắc chung), giữ các mode khác nếu đủ điều kiện |
| `dropLookupMode(UNCONDITIONAL)` | Trên `publicLookup()` (vốn chỉ có `UNCONDITIONAL`), kết quả **không còn quyền** |

Với các lookup không phải public lookup, **`PROTECTED` và `ORIGINAL` luôn bị xóa** khi gọi `dropLookupMode`, bất kể mode được yêu cầu là gì. Điều này là **quy tắc API**, không phải một tác dụng phụ ngẫu nhiên trên JVM.

**Quan trọng:** chỉ được truyền **một trong các hằng số mode hợp lệ**. Truyền giá trị không hợp lệ vào `dropLookupMode` ném `IllegalArgumentException`; không dùng OR nhiều mode rồi giả định nó sẽ “xóa hết các mode được OR”.

### Tại sao `dropLookupMode(PRIVATE)` không giống `dropLookupMode(MODULE)`?

Một lookup được hạn chế bằng:

~~~java
MethodHandles.Lookup packageScoped =
        MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

vẫn có thể giữ `PACKAGE` và `MODULE`. Code được trao `packageScoped` có thể nhận những access hợp lệ trong package mà **không** được truy cập private. Ngược lại:

~~~java
MethodHandles.Lookup publicOnly =
        MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.MODULE);
~~~

mất cả `PRIVATE` lẫn `PACKAGE`; nó không còn quyền truy cập nội bộ theo module/package như lookup trước.

Javadoc mô tả rõ mẫu cấp quyền: một lookup **có `PACKAGE` nhưng không `PRIVATE`** là capability phù hợp để ủy quyền **package access** mà không trao private. Một lookup **có `MODULE` nhưng không `PACKAGE`** có thể phục vụ **public access trong module** mà không trao quyền package.

Đây là lý do các hệ thống plugin, framework, serializers hoặc dependency injection đôi khi cần chia sẻ **lookup đã được giảm quyền**, thay vì đưa toàn bộ `MethodHandles.lookup()` có full privilege.

## 6. So sánh ba thao tác: kết quả và khả năng gọi tiếp

| Tiêu chí | `in(Target.class)` | `privateLookupIn(Target.class, caller)` | `dropLookupMode(mode)` |
| --- | --- | --- | --- |
| Loại method | Instance của `Lookup` | Static của `MethodHandles` | Instance của `Lookup` |
| Có đổi lookup class? | **Có** (trừ target trùng hiện tại) | **Có**, thành target | **Không** |
| Có thể có thêm `PRIVATE` trên target? | **Không tự cấp thêm** | **Có, nếu đáp ứng điều kiện** | **Không** |
| Có tự kiểm tra module `opens`? | Chuyển public rights, không cấp deep private | **Có** khi vượt module | Không chuyển module |
| Có thể làm giảm mode? | **Có**, do ranh giới class/package/module | **Có hoặc đổi tập quyền**, đặc biệt mất `MODULE` khi vượt module | **Luôn chủ động giảm** theo rule |
| Có giữ `previousLookupClass`? | Tùy có chuyển module hay không | Target khác module ghi nguồn trước | Giữ thông tin ngữ cảnh trước nếu có |
| Có thể nâng lại quyền sau khi mất mode? | Không | Chỉ bằng một **lookup nguồn độc lập đủ quyền** và điều kiện truy cập hợp lệ | Không |
| Mục đích điển hình | Chuyển ngữ cảnh nhưng không nâng quyền | Adapter/framework cần private member hợp lệ | Delegation theo nguyên tắc ít quyền nhất |

Mẫu quan hệ dễ nhớ:

~~~text
MethodHandles.lookup() trong C
              |
              +-- .in(D.class)
              |       -> context D, quyền không tăng
              |
              +-- MethodHandles.privateLookupIn(D.class, original)
              |       -> context D, quyền PRIVATE nếu đủ điều kiện
              |       -> qua module khác: mất MODULE
              |
              +-- .dropLookupMode(PRIVATE)
                      -> context C, quyền đã bị thu hẹp
                      -> không dùng .in(C.class) để lấy lại PRIVATE
~~~

Cần tránh một suy luận sai: `privateLookupIn` không có nghĩa “bất kỳ ai cũng có thể nâng quyền”, vì **lookup nguồn và module declaration là những điều kiện bảo mật**. Nó tạo capability theo quyền được ủy quyền, không mở lối phá vỡ Java access checks.

## 7. Chương trình Java 17+ hoàn chỉnh: kiểm chứng cả ba phương thức

Ví dụ được thiết kế để có:

- `LookupRelationshipsDemo` và class lồng nhau `NestVault` thuộc **cùng nest**.
- `PackageSibling` là **top-level class khác nest** nhưng cùng unnamed package.
- Một lookup private trong `PackageSibling` được tạo bằng `privateLookupIn` có điều kiện hợp lệ.
- Các lookup bị `dropLookupMode` để quan sát quyền bị mất.
- Chuyển thử tới `java.lang.String` thuộc module `java.base` để thấy ranh giới liên module.

Tạo file **`LookupRelationshipsDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupRelationshipsDemo {
    static class NestVault {
        private String secret() { return "nested-secret"; }
    }

    static boolean has(MethodHandles.Lookup lookup, int mode) {
        return (lookup.lookupModes() & mode) != 0;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup base = MethodHandles.lookup();
        MethodHandles.Lookup nest = base.in(NestVault.class);
        MethodHandles.Lookup sibling = base.in(PackageSibling.class);
        MethodHandles.Lookup privileged = MethodHandles.privateLookupIn(
                PackageSibling.class, base);

        System.out.println("baseFull=" + base.hasFullPrivilegeAccess());
        System.out.println("nestPrivate=" + has(nest, MethodHandles.Lookup.PRIVATE));
        System.out.println("nestOriginal=" + has(nest, MethodHandles.Lookup.ORIGINAL));
        System.out.println("siblingPackage=" + has(sibling, MethodHandles.Lookup.PACKAGE));
        System.out.println("siblingPrivate=" + has(sibling, MethodHandles.Lookup.PRIVATE));
        System.out.println("privilegedPrivate="
                + has(privileged, MethodHandles.Lookup.PRIVATE));

        MethodHandle nestedRead = nest.findVirtual(NestVault.class,
                "secret", MethodType.methodType(String.class));
        System.out.println("nestSecret=" + (String) nestedRead.invoke(new NestVault()));

        MethodHandle siblingRead = privileged.findVirtual(PackageSibling.class,
                "secret", MethodType.methodType(String.class));
        System.out.println("siblingSecret="
                + (String) siblingRead.invoke(new PackageSibling()));

        try {
            sibling.findVirtual(PackageSibling.class,
                    "secret", MethodType.methodType(String.class));
            throw new AssertionError("sibling.in() unexpectedly got private access");
        } catch (IllegalAccessException expected) {
            System.out.println("inDidNotElevate=true");
        }

        MethodHandles.Lookup noPrivate =
                base.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        MethodHandles.Lookup noPackage =
                base.dropLookupMode(MethodHandles.Lookup.PACKAGE);
        MethodHandles.Lookup noModule =
                base.dropLookupMode(MethodHandles.Lookup.MODULE);

        System.out.println("dropPrivateHasModule="
                + has(noPrivate, MethodHandles.Lookup.MODULE));
        System.out.println("dropPrivateHasPrivate="
                + has(noPrivate, MethodHandles.Lookup.PRIVATE));
        System.out.println("dropPackageHasPrivate="
                + has(noPackage, MethodHandles.Lookup.PRIVATE));
        System.out.println("dropPackageHasModule="
                + has(noPackage, MethodHandles.Lookup.MODULE));
        System.out.println("dropModuleHasPackage="
                + has(noModule, MethodHandles.Lookup.PACKAGE));
        System.out.println("dropModuleHasPrivate="
                + has(noModule, MethodHandles.Lookup.PRIVATE));
        System.out.println("dropModuleHasPublic="
                + has(noModule, MethodHandles.Lookup.PUBLIC));

        try {
            MethodHandles.privateLookupIn(PackageSibling.class, noPrivate);
            throw new AssertionError("privateLookupIn should fail without PRIVATE");
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookupNeedsPrivateAndModule=true");
        }

        MethodHandles.Lookup roundTrip =
                sibling.in(LookupRelationshipsDemo.class);
        System.out.println("roundTripRestoresPrivate="
                + has(roundTrip, MethodHandles.Lookup.PRIVATE));

        MethodHandles.Lookup inJavaBase = base.in(String.class);
        System.out.println("jdkPublic="
                + has(inJavaBase, MethodHandles.Lookup.PUBLIC));
        System.out.println("jdkModule="
                + has(inJavaBase, MethodHandles.Lookup.MODULE));
        System.out.println("jdkPreviousClassIsOriginal="
                + (inJavaBase.previousLookupClass() == LookupRelationshipsDemo.class));

        try {
            MethodHandles.privateLookupIn(String.class, base);
            throw new AssertionError("java.base/java.lang should not be open");
        } catch (IllegalAccessException expected) {
            System.out.println("javaLangNotOpenByDefault=true");
        }
    }
}

class PackageSibling {
    private String secret() { return "sibling-secret"; }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 LookupRelationshipsDemo.java
java LookupRelationshipsDemo
~~~

**Stdout đã kiểm chứng trên OpenJDK với `javac --release 17`:**

~~~text
baseFull=true
nestPrivate=true
nestOriginal=false
siblingPackage=true
siblingPrivate=false
privilegedPrivate=true
nestSecret=nested-secret
siblingSecret=sibling-secret
inDidNotElevate=true
dropPrivateHasModule=true
dropPrivateHasPrivate=false
dropPackageHasPrivate=false
dropPackageHasModule=true
dropModuleHasPackage=false
dropModuleHasPrivate=false
dropModuleHasPublic=true
privateLookupNeedsPrivateAndModule=true
roundTripRestoresPrivate=false
jdkPublic=true
jdkModule=false
jdkPreviousClassIsOriginal=true
javaLangNotOpenByDefault=true
~~~

### Điều gì được chứng minh?

1. **`baseFull=true`:** lookup lấy trực tiếp trong class gọi có `PRIVATE` + `MODULE`.
2. **`nestPrivate=true`, `nestOriginal=false`:** khi chuyển tới nestmate khác, có thể **giữ private** nhưng **mất `ORIGINAL`**; đổi lookup class không còn là lookup gốc.
3. **`siblingPackage=true`, `siblingPrivate=false`:** class cùng package nhưng khác nest có thể chia sẻ quyền package, không được truy cập private chỉ bằng `in`.
4. **`privilegedPrivate=true`:** `privateLookupIn(PackageSibling.class, base)` thành công trong cùng module vì nguồn có đủ quyền; handle đọc được method private trả `sibling-secret`.
5. **`inDidNotElevate=true`:** cố tạo handle đến private method từ `sibling` sau khi gọi `in` thất bại với `IllegalAccessException`, đúng luật bảo vệ thành viên.
6. **Các dòng `drop...`:** bỏ `PRIVATE` không tự bỏ `MODULE`; bỏ `PACKAGE` kéo theo mất `PRIVATE`; bỏ `MODULE` kéo theo mất cả `PACKAGE`/`PRIVATE`, nhưng có thể còn `PUBLIC`.
7. **`privateLookupNeedsPrivateAndModule=true`:** `privateLookupIn` từ nguồn đã mất `PRIVATE` không được cấp quyền.
8. **`roundTripRestoresPrivate=false`:** quay lại class cũ bằng `in` không lấy lại quyền đã mất.
9. **`jdkPublic=true`, `jdkModule=false`, `jdkPreviousClassIsOriginal=true`:** chuyển sang `String.class` trong `java.base` mang ngữ cảnh previous class và mất `MODULE`.
10. **`javaLangNotOpenByDefault=true`:** default `java.base` không mở `java.lang` cho deep reflection từ ứng dụng unnamed module, nên `privateLookupIn(String.class, base)` bị từ chối. Đây không phải lỗi vì method private không tồn tại, mà là **giới hạn module access**.

Ví dụ chạy trong unnamed module với các class đặt chung file để minh họa nest/package. Trong dự án named module, luật `reads`/`opens` bổ sung vẫn có hiệu lực như phần 4.

## 8. Quy tắc kiểm tra các lỗi khi liên kết MethodHandle

Khi gọi:

~~~java
MethodHandle handle =
        lookup.findVirtual(Target.class, "work", MethodType.methodType(void.class));
~~~

có một số loại lỗi khác nhau:

| Lỗi / hiện tượng | Khả năng nguyên nhân |
| --- | --- |
| `IllegalAccessException` khi `findVirtual/findGetter` | Thành viên hoặc class không accessible theo lookup class/modes/module |
| `NoSuchMethodException` | Method name hoặc `MethodType` không khớp chữ ký mong muốn |
| `NoSuchFieldException` | Field name hoặc field type không đúng |
| `IllegalAccessException` từ `privateLookupIn` | Nguồn không đủ `PRIVATE+MODULE`, hoặc module `reads/opens` chưa cho phép |
| `IllegalArgumentException` khi dùng `in` với array/primitive/void | Class không hợp lệ làm lookup class mới |
| `IllegalArgumentException` khi `dropLookupMode` nhận mode không hợp lệ | Phải truyền đúng một mode được API định nghĩa |
| `WrongMethodTypeException` lúc invoke | Cách gọi handle không khớp type của handle |
| `NullPointerException` khi truyền target/lookup null | Cần kiểm tra đối số trước khi tạo lookup |

Trong ví dụ ở phần 7, `IllegalAccessException` là **kết quả kỳ vọng** ở những bước thử bảo vệ private và JPMS. Trong code thật, không nên catch `IllegalAccessException` rồi tự động bật một cờ mở toàn bộ module hoặc làm cho mọi package thành `open`.

### Cách debug theo thứ tự

1. In **`lookup.lookupClass()`** và **`lookup.previousLookupClass()`** (nếu cần).
2. Đọc **`lookup.lookupModes()`** bằng phép AND với các hằng số mode, không suy diễn từ `toString()` của lookup.
3. Xác minh **class target có accessible** với ngữ cảnh lookup không.
4. Nếu cùng package nhưng khác nest, đừng nhầm `PACKAGE` với `PRIVATE`.
5. Nếu chuyển module, kiểm tra **module reads**, **exports** cho public access và **opens** cho deep private access.
6. Nếu đã gọi `dropLookupMode`, xác minh những mode bị mất **do quy tắc kéo theo**, không chỉ mode truyền vào.
7. Kiểm tra chữ ký **`MethodType`** và kiểu return/parameters chính xác trước khi kết luận lỗi do access.
8. Viết test chỉ bao quanh thao tác có thể ném lỗi, không cho exception ngoài ý muốn ở setup làm test pass giả.

## 9. Mẫu thiết kế quyền hạn an toàn cho thư viện và framework

### Mẫu A: chỉ cần public API

Nếu framework chỉ cần gọi public method ở class nằm trong package export phù hợp, dùng `MethodHandles.publicLookup()` hoặc lookup giới hạn bằng các mode, tránh đòi private access.

~~~java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
MethodHandle trim = publicOnly.findVirtual(
        String.class, "trim", MethodType.methodType(String.class));
~~~

Đây là đoạn minh họa trong phương thức, yêu cầu import `MethodHandle`, `MethodType`. Không nên dùng `privateLookupIn` để thực hiện một việc public lookup đã đáp ứng.

### Mẫu B: chỉ ủy quyền package access

Thay vì đưa toàn bộ lookup thu được từ `MethodHandles.lookup()` cho code không cần private, bạn có thể **giảm quyền**:

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup packageCapability =
        caller.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

`packageCapability` vẫn có thể thực hiện một số thao tác package/module hợp lệ nhưng không còn `PRIVATE`. Không được gọi nó là “lookup public duy nhất” vì `PACKAGE`/`MODULE` có thể vẫn còn.

### Mẫu C: private access đúng ranh giới được ủy quyền

Nếu một framework có yêu cầu hợp lệ đọc private member của class đích, dùng lookup nguồn do thành phần **có quyền thực** cung cấp, và gọi:

~~~java
MethodHandles.Lookup privateTarget =
        MethodHandles.privateLookupIn(Target.class, trustedCallerLookup);
~~~

Ở đây `trustedCallerLookup` phải có `PRIVATE` + `MODULE`, target hợp lệ, và nếu vượt module, cấu hình `reads/opens` phải cho phép. Đây là **capability mạnh**. Không chuyển nó đến plugin không tin cậy nếu plugin chỉ cần quyền đọc public methods.

**Không lạm dụng `--add-opens`:** nếu một package được mở cho module khác, module nhận quyền có thể sử dụng deep reflection trên nội bộ package. Cấu hình cần hẹp, có kiểm soát, và thống nhất với người sở hữu module.

### Mẫu D: hiểu rằng đã tạo MethodHandle thì quyền không được kiểm lại mỗi lần gọi

Điểm rất quan trọng về bảo mật: **quyền được kiểm tra khi tạo handle**, còn việc gọi handle sau đó không tự kiểm tra lại toàn bộ quyền `Lookup`. Do vậy:

- Không giao một handle truy cập private cho code không nên có khả năng đó.
- `dropLookupMode(...)` tạo **lookup khác**, không tước quyền từ lookup gốc hoặc tự thu hồi các method handles đã cấp trước.
- Nếu cần thu hồi/giới hạn hành động của plugin, hãy quản lý vòng đời và cơ chế ủy quyền của chính API/framework; không hiểu `dropLookupMode` là phương tiện “revoke tất cả handle đã phát hành”.

## 10. Những hiểu lầm thường gặp

**Lỗi 1 — “`lookup.in(Target.class)` tương đương `privateLookupIn(Target.class, lookup)`.”**  
Sai. `in` không cấp thêm quyền; `privateLookupIn` có thể cấp quyền private trong ngữ cảnh khác nhưng chỉ khi đủ điều kiện.

**Lỗi 2 — “Cùng package là xem được private của nhau.”**  
Sai. Quy tắc private gắn với class/nestmates, khác với package access.

**Lỗi 3 — “Chuyển qua module khác bằng `in` vẫn có quyền `MODULE`.”**  
Sai. Chuyển module làm mất `MODULE` và điều chỉnh public access theo cả lookup/previous lookup.

**Lỗi 4 — “Một lookup có `PRIVATE` thì gọi tiếp `privateLookupIn` ở đâu cũng được.”**  
Sai. Cần **cả `PRIVATE` và `MODULE`**. Lookup private từ **module khác** thường đã mất `MODULE`.

**Lỗi 5 — “Chỉ cần `exports` package là có quyền private.”**  
Sai. Cross-module private lookup cần **`opens`** package đích cho module nguồn, ngoài điều kiện readability.

**Lỗi 6 — “Gọi `dropLookupMode(PACKAGE)` chỉ xóa PACKAGE.”**  
Sai. Nó còn xóa `PRIVATE` và các mode `PROTECTED/ORIGINAL` theo quy tắc.

**Lỗi 7 — “Gọi `dropLookupMode(MODULE)` chỉ xóa MODULE.”**  
Sai. Nó xóa luôn `PACKAGE` và `PRIVATE` (cùng `PROTECTED/ORIGINAL`).

**Lỗi 8 — “Có thể gọi `in(Original.class)` để lấy lại `PRIVATE`.”**  
Sai. Các bit đã mất không được tự khôi phục từ lookup hạ quyền.

**Lỗi 9 — “`dropLookupMode` thu hồi các MethodHandles tạo trước đó.”**  
Sai. Nó tạo lookup giới hạn; handles được tạo hợp lệ trước đó không tự bị revoke.

**Lỗi 10 — “Dùng `hasPrivateAccess()` để xác nhận full privilege.”**  
Không nên. API đã deprecated; dùng `hasFullPrivilegeAccess()` và xem `lookupModes()`.

**Lỗi 11 — “Có `ORIGINAL` là bắt buộc để gọi `privateLookupIn`.”**  
Sai. Điều kiện trực tiếp là `PRIVATE` và `MODULE`. `ORIGINAL` cung cấp các khả năng khác và chỉ áp dụng trong mô hình Java 16+.

**Lỗi 12 — “`publicLookup()` và lookup chỉ còn `PUBLIC` giống hệt nhau.”**  
Không hẳn. `publicLookup()` có `UNCONDITIONAL`, trong khi lookup có `PUBLIC` chịu các quy tắc module readability/export, nhất là khi có previous lookup class.

**Lỗi 13 — “Một tên method tìm thất bại luôn là do quyền access.”**  
Không. Cũng có thể sai chữ ký `MethodType`, tên hoặc kiểu member.

**Lỗi 14 — “`--add-opens ALL-UNNAMED` là giải pháp mặc định cho bất kỳ private lookup nào.”**  
Không nên. Mở package là quyết định ủy quyền sâu. Cần cấu hình đúng module mục tiêu, giảm phạm vi và có lý do bảo mật rõ ràng.

## 11. Quy trình thực hành nhanh

Trước khi dùng `Lookup` trên một target class, trả lời lần lượt:

1. Mục tiêu chỉ cần **public** hay phải có private?
2. Lookup gốc được tạo **ở class nào**? Có `PRIVATE`, `MODULE` và quyền mà caller thực sự sở hữu không?
3. Target là **cùng class, nestmate, cùng package, cùng module hay khác module**?
4. Nếu chỉ đổi ngữ cảnh, `in(Target.class)` có đủ không? Nó có làm rơi một mode đang cần?
5. Nếu cần private ở target **ngoài nest**, có đủ quyền để dùng `privateLookupIn` không?
6. Nếu khác module, M1 có **reads M2** và M2 có **opens package của target tới M1** không?
7. Nếu đang chia sẻ lookup cho thành phần khác, có thể dùng `dropLookupMode` để giới hạn đúng khả năng họ cần không?
8. Sau khi hạ quyền, **đừng dựa vào `in` để phục hồi**; nếu cần quyền cao hơn, chỉ một thành phần **độc lập có quyền phù hợp** mới có thể cấp lookup mới qua quy trình hợp lệ.
9. Kiểm tra `lookupClass()`, `previousLookupClass()` và `lookupModes()` rồi thử tạo **handle thực tế**.
10. Bảo vệ các capability mạnh: đừng phát tán lookup private hoặc handle truy cập private cho code không đáng tin.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Lookup.in(Target.class)` có tự cấp quyền private của Target không?  
**Đáp án:** Không. Nó chuyển ngữ cảnh nhưng không tăng quyền.

**Câu 2.** Hai class cùng package nhưng khác nest, gọi `lookup.in(Other.class)` có giữ `PRIVATE` không?  
**Đáp án:** Thông thường không. `PACKAGE` có thể giữ, còn `PRIVATE` bị mất.

**Câu 3.** `privateLookupIn` yêu cầu hai mode nào ở lookup nguồn?  
**Đáp án:** `PRIVATE` và `MODULE`.

**Câu 4.** Qua module khác, chỉ `exports package` có đủ cho private access không?  
**Đáp án:** Không. Cần nguồn `reads` module đích và module đích `opens` package tới module nguồn.

**Câu 5.** `privateLookupIn(Target, caller)` thành công qua module khác sẽ còn `MODULE` ở lookup kết quả không?  
**Đáp án:** Không. Lookup có thể có `PRIVATE` nhưng mất `MODULE`, nên không có full privilege.

**Câu 6.** `dropLookupMode(PACKAGE)` có thể làm mất PRIVATE không?  
**Đáp án:** Có. Cả `PACKAGE`, `PRIVATE` và hai mode `PROTECTED/ORIGINAL` theo quy tắc chung.

**Câu 7.** Nếu gọi `base.dropLookupMode(MODULE)`, kết quả có còn PACKAGE hoặc PRIVATE không?  
**Đáp án:** Không, cả hai bị loại theo bậc thang.

**Câu 8.** `lookup.in(Other.class).in(Original.class)` có tự phục hồi private nếu đã mất không?  
**Đáp án:** Không.

**Câu 9.** Một handle private đã tạo hợp lệ có tự mất quyền sau khi ta gọi `dropLookupMode` trên lookup khác không?  
**Đáp án:** Không. Quyền được kiểm tra khi handle được tạo; không có cơ chế revoke handle tự động do drop mode.

**Câu 10.** API nào nên dùng thay `hasPrivateAccess()` khi muốn biết lookup có full privilege?  
**Đáp án:** `hasFullPrivilegeAccess()`.

**Câu 11.** Khi chuyển từ một class unnamed module sang `String.class` trong `java.base`, `previousLookupClass()` có ý nghĩa gì?  
**Đáp án:** Nó ghi class nguồn trước khi chuyển module; quyền public sau chuyển được đánh giá theo ngữ cảnh các module liên quan.

**Câu 12.** Nếu `privateLookupIn(String.class, caller)` từ ứng dụng thường bị `IllegalAccessException`, nên mặc định mở toàn bộ `java.base` không?  
**Đáp án:** Không. Dùng API công khai của `String` nếu có thể; chỉ mở package khi có lý do được chủ sở hữu nền tảng cho phép và đã đánh giá bảo mật.

## 13. Nguồn Java chính thức

- **Oracle Java SE 17 — `MethodHandles.Lookup`:** mô tả `in`, `dropLookupMode`, bit mask, `previousLookupClass`, cross-module access, quyền khi tạo MethodHandle. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Oracle Java SE 25 — `MethodHandles.Lookup`:** các quy tắc vẫn còn áp dụng ở JDK hiện đại, đặc biệt drop mode kéo theo và chuyển qua module. https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- **Oracle Java SE 17 — `MethodHandles.privateLookupIn`:** yêu cầu `PRIVATE` + `MODULE`, `reads/opens` khi vượt module, kết quả có private nhưng mất module. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)
- **Oracle Java SE 25 — `MethodHandles.privateLookupIn`:** tài liệu cập nhật điều kiện deep reflection và khả năng giới hạn module. https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)
- **Oracle Java SE 17 — `Module`:** phân biệt readability, exported packages và opened packages. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- **JLS 17 §6.6 Access Control:** private/package/protected và các quy tắc Java access. https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6