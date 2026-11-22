# `privateLookupIn` và điều kiện truy cập qua mô-đun

`MethodHandles.privateLookupIn(targetClass, callerLookup)` được bổ sung trong Java 9 để tạo một `MethodHandles.Lookup` có quyền truy cập private vào một lớp đích. API này hữu ích khi một thư viện hoặc framework cần thao tác với thành viên private bằng Method Handle hoặc VarHandle, trong khi ứng dụng chạy trên Java Platform Module System (JPMS).

`privateLookupIn` tuân theo ranh giới mô-đun. Quyền truy cập private chỉ được cấp khi lookup gọi có đủ quyền, mô-đun gọi đọc được mô-đun đích và package chứa lớp đích được mở cho mô-đun gọi khi hai lớp nằm ở hai mô-đun khác nhau. Một package được `exports` chưa chắc đã được `opens`.

## 1. `MethodHandles.Lookup` là gì?

`MethodHandles.Lookup` là đối tượng đại diện cho quyền truy cập mà một đoạn mã có thể sử dụng để tìm hoặc tạo Method Handle. Nó hoạt động như một capability: quyền của lookup được xác định tại nơi lookup được tạo và được giới hạn bởi lớp, package, mô-đun cùng các lookup modes.

`MethodHandles.lookup()` tạo lookup gắn với lớp gọi hiện tại. Vì vậy, vị trí gọi phương thức này rất quan trọng:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

Nếu dòng trên nằm trong `com.example.Service`, lookup được gắn với `Service` và các quyền mà lớp đó có. Một helper ở mô-đun khác tạo `MethodHandles.lookup()` sẽ nhận quyền của helper, không tự động thừa hưởng quyền của nơi gọi helper.

`MethodHandles.publicLookup()` chỉ cung cấp quyền public rộng rãi. Nó không có quyền private để dùng làm caller lookup cho `privateLookupIn`.

## 2. `privateLookupIn` thực hiện điều gì?

Chữ ký:

```java
public static MethodHandles.Lookup privateLookupIn(
    Class<?> targetClass,
    MethodHandles.Lookup callerLookup
) throws IllegalAccessException
```

Phương thức tạo một lookup mới có `lookupClass()` là `targetClass`. Lookup mới cho phép truy cập các thành viên private của lớp đích, trong phạm vi các quyền mà Java module system cho phép.

Ví dụ khi lớp đích và lớp gọi nằm trong cùng một mô-đun:

```java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup());

VarHandle value = privateLookup.findVarHandle(
    Target.class, "value", int.class);
```

Trong trường hợp này, package không cần khai báo `opens` cho chính mô-đun của nó. Tuy vậy, caller lookup vẫn phải có cả quyền `PRIVATE` và `MODULE`.

Khi lớp đích nằm trong một mô-đun khác, các điều kiện bổ sung về readability và package openness sẽ được áp dụng.

## 3. Các điều kiện bắt buộc của caller lookup

Caller lookup truyền vào `privateLookupIn` phải có cả hai lookup modes:

- `MethodHandles.Lookup.PRIVATE`: cho phép lookup đại diện cho quyền truy cập private của lớp gọi.
- `MethodHandles.Lookup.MODULE`: cho phép lookup thực hiện việc chuyển quyền qua ranh giới mô-đun theo quy tắc của API.

Kiểm tra nhanh:

```java
MethodHandles.Lookup caller = MethodHandles.lookup();
int modes = caller.lookupModes();

boolean hasPrivate =
    (modes & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule =
    (modes & MethodHandles.Lookup.MODULE) != 0;
```

Nếu thiếu một trong hai quyền, `privateLookupIn` ném `IllegalAccessException`. `publicLookup()` không đáp ứng điều kiện này. Một lookup đã bị giảm quyền bằng `dropLookupMode(...)` cũng có thể không còn đủ điều kiện.

Không nên tạo caller lookup từ một vị trí không có quyền phù hợp rồi mong `privateLookupIn` nâng quyền cho nó. Phương thức này không phải cơ chế vượt qua access control.

## 4. Readability: mô-đun gọi phải đọc được mô-đun đích

Khi hai lớp nằm trong các named module khác nhau, mô-đun chứa caller lookup phải đọc được mô-đun chứa target class.

Thông thường, tạo quan hệ đọc bằng `requires` trong `module-info.java`:

```java
module caller.mod {
    requires target.mod;
}
```

`requires target.mod` tạo quan hệ readability từ `caller.mod` đến `target.mod`. Nếu không có quan hệ đọc, `privateLookupIn` ném `IllegalAccessException`, ngay cả khi package đích đã được mở cho caller.

Có thể quan sát quan hệ này bằng API mô-đun:

```java
Module callerModule = caller.lookupClass().getModule();
Module targetModule = targetClass.getModule();

boolean canRead = callerModule.canRead(targetModule);
```

Ở runtime, có thể thêm một read edge bằng tùy chọn:

```bash
--add-reads caller.mod=target.mod
```

Tùy chọn này chỉ bổ sung readability. Nó không tự mở package private của mô-đun đích.

## 5. Package openness: `opens` khác `exports`

Đây là điểm dễ nhầm nhất khi dùng `privateLookupIn` qua mô-đun.

| Khai báo | Cho phép | Không tự cho phép |
| --- | --- | --- |
| `exports p` | Mô-đun khác truy cập các kiểu public và thành viên public được export trong package `p`, theo quy tắc truy cập Java. | Truy cập private vào lớp trong package. |
| `opens p` | Mở package `p` cho deep reflection/runtime access của các mô-đun khác. | Làm package trở thành package có thể import ở compile time. |
| `opens p to caller.mod` | Chỉ mở package `p` cho mô-đun `caller.mod`. | Mở package cho mọi mô-đun. |
| `open module target.mod` | Mở tất cả package của mô-đun cho deep reflection. | Tự động export tất cả package ở compile time. |

Ví dụ một mô-đun export API công khai nhưng chỉ mở package nội bộ cho một caller:

```java
module target.mod {
    exports target.api;
    opens target.internal to caller.mod;
}
```

Trong ví dụ này:

- Caller có thể import các kiểu public trong `target.api`.
- Caller không được truy cập private trong `target.api` chỉ vì package đã export.
- Caller có thể dùng `privateLookupIn` với lớp thuộc `target.internal` nếu caller có readability và đủ lookup modes.
- `target.internal` vẫn không trở thành package có thể import trực tiếp từ mã nguồn của `caller.mod`, vì nó chưa được export.

Vì vậy, một package có thể được mở cho private lookup nhưng không được export. Khi không thể import kiểu đích, ứng dụng có thể nhận `Class<?>` bằng cơ chế tải lớp phù hợp, rồi dùng lookup để tìm constructor hoặc thành viên.

## 6. Điều kiện đầy đủ khi đi qua ranh giới mô-đun

Với caller và target ở hai named module khác nhau, cần đồng thời thỏa mãn:

1. Caller lookup có `PRIVATE` và `MODULE` modes.
2. Mô-đun của caller lookup đọc được mô-đun chứa target class.
3. Mô-đun đích mở package chứa target class cho mô-đun caller.

Nếu một điều kiện không thỏa, `privateLookupIn` ném `IllegalAccessException`.

Package openness có thể được kiểm tra bằng:

```java
String packageName = targetClass.getPackageName();
boolean isOpen = targetModule.isOpen(packageName, callerModule);
```

Đừng dùng `targetModule.isExported(packageName, callerModule)` để thay thế phép kiểm tra `isOpen`. Export và open là hai quyền khác nhau.

## 7. Quyền của lookup trả về

`privateLookupIn` trả về một lookup mới gắn với lớp đích. Lookup của caller không bị thay đổi.

Khi hai lớp ở cùng mô-đun, lookup mới có full privilege access trong mô-đun đó, nếu caller lookup đáp ứng điều kiện.

Khi chuyển qua mô-đun khác, lookup mới giữ quyền `PRIVATE` đối với lớp đích nhưng mất quyền `MODULE`. Vì vậy:

- `lookupClass()` là lớp đích.
- `PRIVATE` mode vẫn hiện diện.
- `MODULE` mode không còn hiện diện.
- `hasFullPrivilegeAccess()` trả `false` cho lookup cross-module.

Điều này có nghĩa lookup mới có thể truy cập thành viên private của lớp đích, nhưng không có toàn bộ quyền đặc biệt mà một lookup full-privilege trong mô-đun đích có. Không nên nhầm private access vào một lớp với full privilege access trong toàn bộ mô-đun.

Kiểm tra:

```java
System.out.println(privateLookup.lookupClass());
System.out.println(
    (privateLookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0);
System.out.println(
    (privateLookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0);
System.out.println(privateLookup.hasFullPrivilegeAccess());
```

`hasFullPrivilegeAccess()` có trong các JDK hiện hành như Java 17. Khi viết mã tương thích với Java 9, cần lưu ý API kiểm tra quyền đã thay đổi qua các phiên bản JDK.

## 8. Ví dụ hoàn chỉnh với ba mô-đun

Ví dụ này tạo ba mô-đun:

- `target.mod` chứa lớp có field private. Package `target.internal` được mở có chọn lọc cho `caller.mod` và `caller.noread`, nhưng không export.
- `caller.mod` có `requires target.mod`, nên đọc được mô-đun đích.
- `caller.noread` không khai báo `requires target.mod`, nên không có readability.

Cấu trúc thư mục:

```text
src/
  target.mod/
    module-info.java
    target/api/PublicBox.java
    target/api/SameModuleProbe.java
    target/internal/SecretBox.java
  caller.mod/
    module-info.java
    caller/app/Main.java
  caller.noread/
    module-info.java
    caller/noread/Main.java
```

**`src/target.mod/module-info.java`**

```java
module target.mod {
    exports target.api;
    opens target.internal to caller.mod, caller.noread;
}
```

**`src/target.mod/target/api/PublicBox.java`**

```java
package target.api;

public class PublicBox {
    private String secret = "public-but-not-open";
    public PublicBox() {}
}
```

**`src/target.mod/target/internal/SecretBox.java`**

```java
package target.internal;

public class SecretBox {
    private int value = 7;
    public SecretBox() {}
}
```

**`src/target.mod/target/api/SameModuleProbe.java`**

```java
package target.api;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import target.internal.SecretBox;

public class SameModuleProbe {
    private SameModuleProbe() {}

    public static void run() throws Exception {
        MethodHandles.Lookup lookup = MethodHandles.privateLookupIn(
            SecretBox.class, MethodHandles.lookup());
        VarHandle value = lookup.findVarHandle(
            SecretBox.class, "value", int.class);

        SecretBox instance = new SecretBox();
        value.set(instance, 42);
        System.out.println("same-module private access: " + value.get(instance));
        System.out.println(
            "same-module full privilege: " + lookup.hasFullPrivilegeAccess());
    }
}
```

Đoạn mã này chạy bên trong `target.mod`, vì vậy nó có thể mở private lookup vào package khác cùng mô-đun mà không cần khai báo `opens target.internal` cho chính nó.

**`src/caller.mod/module-info.java`**

```java
module caller.mod {
    requires target.mod;
}
```

**`src/caller.mod/caller/app/Main.java`**

```java
package caller.app;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import target.api.PublicBox;
import target.api.SameModuleProbe;

public class Main {
    public static void main(String[] args) throws Throwable {
        SameModuleProbe.run();

        MethodHandles.Lookup caller = MethodHandles.lookup();
        Class<?> targetClass = Class.forName("target.internal.SecretBox");
        MethodHandles.Lookup privateLookup =
            MethodHandles.privateLookupIn(targetClass, caller);
        VarHandle value = privateLookup.findVarHandle(
            targetClass, "value", int.class);

        Object instance = privateLookup.findConstructor(
            targetClass, MethodType.methodType(void.class)).invoke();

        System.out.println("cross-module before: " + value.get(instance));
        value.set(instance, 42);
        System.out.println("cross-module after: " + value.get(instance));
        System.out.println("cross-module PRIVATE mode: "
            + ((privateLookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
        System.out.println("cross-module MODULE mode: "
            + ((privateLookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
        System.out.println("cross-module full privilege: "
            + privateLookup.hasFullPrivilegeAccess());

        try {
            MethodHandles.privateLookupIn(PublicBox.class, caller);
            throw new AssertionError("exported but unopened package was accepted");
        } catch (IllegalAccessException expected) {
            System.out.println("exported but not opened: IllegalAccessException");
        }

        try {
            MethodHandles.privateLookupIn(targetClass, MethodHandles.publicLookup());
            throw new AssertionError("public lookup gained private access");
        } catch (IllegalAccessException expected) {
            System.out.println("lookup without PRIVATE: IllegalAccessException");
        }
    }
}
```

Caller không import `target.internal.SecretBox`, vì package đó không export. `Class.forName` lấy `Class<?>`; lookup có quyền private sau đó tìm constructor và field.

**`src/caller.noread/module-info.java`**

```java
module caller.noread {
}
```

**`src/caller.noread/caller/noread/Main.java`**

```java
package caller.noread;

import java.lang.invoke.MethodHandles;

public class Main {
    public static void main(String[] args) throws Exception {
        Class<?> target = Class.forName("target.internal.SecretBox");
        try {
            MethodHandles.privateLookupIn(target, MethodHandles.lookup());
            throw new AssertionError("module without readability was accepted");
        } catch (IllegalAccessException expected) {
            System.out.println("module without readability: IllegalAccessException");
        }
    }
}
```

Biên dịch cả ba mô-đun bằng JDK 17:

```bash
javac --release 17 -Xlint:all -d out --module-source-path src -m target.mod,caller.mod,caller.noread
```

Chạy mô-đun có readability:

```bash
java --module-path out -m caller.mod/caller.app.Main
```

Chạy mô-đun không có readability:

```bash
java --module-path out --add-modules target.mod -m caller.noread/caller.noread.Main
```

Stdout chính xác:

```text
same-module private access: 42
same-module full privilege: true
cross-module before: 7
cross-module after: 42
cross-module PRIVATE mode: true
cross-module MODULE mode: false
cross-module full privilege: false
exported but not opened: IllegalAccessException
lookup without PRIVATE: IllegalAccessException
module without readability: IllegalAccessException
```

Ví dụ xác nhận ba điểm: cùng mô-đun không cần `opens`; khác mô-đun cần cả readability và qualified `opens`; package chỉ `exports` không đủ cho private lookup.

## 9. Mở package bằng tùy chọn runtime

Nếu không thể sửa `module-info.java` của mô-đun đích, môi trường chạy có thể mở package cụ thể bằng `--add-opens`: 

```bash
java --module-path out --add-opens target.mod/target.internal=caller.mod -m caller.mod/caller.app.Main
```

Nếu caller cũng chưa đọc mô-đun đích, có thể bổ sung read edge:

```bash
java --module-path out --add-reads caller.mod=target.mod --add-opens target.mod/target.internal=caller.mod -m caller.mod/caller.app.Main
```

`--add-opens` và `--add-reads` giải quyết hai điều kiện khác nhau. `--add-exports` chỉ mở quyền truy cập public ở cấp package; nó không thay thế `--add-opens` khi cần private lookup.

Với ứng dụng production, ưu tiên khai báo `opens p to caller.mod` rõ ràng trong module descriptor nếu mô-đun đích do mình kiểm soát. Dùng tùy chọn command line khi cần cấu hình triển khai, kiểm thử hoặc tích hợp với mô-đun bên ngoài.

## 10. Phân biệt lỗi truy cập với lỗi tìm thành viên

`privateLookupIn` có thể thành công nhưng thao tác tìm thành viên sau đó vẫn thất bại. Cần phân biệt các bước:

| Bước | Lỗi có thể gặp | Ý nghĩa |
| --- | --- | --- |
| Tạo private lookup | `IllegalAccessException` | Thiếu PRIVATE/MODULE, thiếu readability hoặc package chưa mở. |
| Tìm field/method/constructor | `NoSuchFieldException`, `NoSuchMethodException` | Tên hoặc kiểu thành viên không khớp. |
| Tìm thành viên nhưng không có quyền tương ứng | `IllegalAccessException` | Lookup không đủ quyền đối với thành viên đó. |
| Gọi MethodHandle với descriptor sai | `WrongMethodTypeException` | Kiểu đối số hoặc kiểu trả về không khớp MethodType. |
| Gọi handle với object runtime sai kiểu | `ClassCastException` | Reference cast thất bại tại runtime. |

Ví dụ, `privateLookupIn` mở quyền vào lớp đích nhưng không tự xác nhận tên field `value` tồn tại. `findVarHandle(targetClass, "value", int.class)` vẫn cần đúng tên và đúng kiểu field.

## 11. Chẩn đoán `IllegalAccessException`

Khi `privateLookupIn` ném `IllegalAccessException`, kiểm tra lần lượt:

1. `callerLookup.lookupModes()` có cả `PRIVATE` và `MODULE` không?
2. `callerLookup.lookupClass().getModule()` có đọc được `targetClass.getModule()` không?
3. Package của `targetClass` có được mở cho chính mô-đun của caller lookup không?
4. Tên package trong `opens` có đúng package của target class không?
5. Qualified `opens` có chỉ đúng tên mô-đun caller không?
6. Nếu dùng `--add-opens` hoặc `--add-reads`, các tùy chọn có được truyền vào đúng tiến trình JVM đang chạy không?

Đoạn chẩn đoán:

```java
MethodHandles.Lookup caller = MethodHandles.lookup();
Class<?> targetClass = Target.class;
Module callerModule = caller.lookupClass().getModule();
Module targetModule = targetClass.getModule();
String packageName = targetClass.getPackageName();

System.out.println("caller modes: " + caller.lookupModes());
System.out.println("caller reads target: " + callerModule.canRead(targetModule));
System.out.println("target package open: "
    + targetModule.isOpen(packageName, callerModule));
```

Không chỉ nhìn vào `exports` khi chẩn đoán. Một package có thể export public API nhưng vẫn đóng đối với private lookup.

## 12. Nguyên tắc thiết kế và bảo mật

- **Tạo lookup ở đúng ranh giới tin cậy:** gọi `MethodHandles.lookup()` trong lớp có quyền hợp lệ và truyền lookup đến đúng thành phần cần dùng.
- **Không phát tán private lookup tùy tiện:** lookup là capability; người nhận có thể dùng nó để tìm các thành viên private mà lookup cho phép.
- **Mở package có chọn lọc:** ưu tiên `opens package.name to trusted.module` thay vì mở toàn bộ mô-đun.
- **Giữ module descriptor rõ ràng:** ghi lại mô-đun nào cần đọc và package nào được mở cho nó.
- **Không coi `exports` là quyền deep reflection:** public API và private access có mục đích khác nhau.
- **Kiểm tra quyền trước khi tạo handle:** phân biệt lỗi tại bước lookup với lỗi lúc gọi handle.
- **Không dùng private lookup để thay thế thiết kế API:** nếu nhiều mô-đun thường xuyên cần truy cập trạng thái private, cân nhắc cung cấp API công khai có hợp đồng ổn định.
- **Tránh lưu lookup quyền cao trong vùng dùng chung không tin cậy:** giới hạn vòng đời và phạm vi chia sẻ của capability.

`privateLookupIn` là công cụ cho framework, adapter và tích hợp cần truy cập có kiểm soát. Nó không nên trở thành cách truy cập nội bộ mặc định giữa mọi mô-đun.

## 13. Lỗi thường gặp

1. **Nhầm `exports` với `opens`.** Export public API không cho phép private lookup; cần mở package.
2. **Chỉ khai báo `opens` mà quên readability.** Mô-đun caller vẫn phải đọc được mô-đun đích.
3. **Chỉ thêm `--add-reads`.** Readability không tự mở package; cần `opens` hoặc `--add-opens`.
4. **Dùng `publicLookup()`.** Lookup này không có `PRIVATE` và `MODULE` modes cần thiết.
5. **Tạo lookup trong helper không có quyền.** Quyền gắn với lớp thực hiện `MethodHandles.lookup()`, không tự động lấy từ caller bên ngoài.
6. **Cho rằng private lookup cross-module có full privilege.** Lookup trả về mất `MODULE`, nên `hasFullPrivilegeAccess()` là `false`.
7. **Import package chỉ được mở.** `opens` cho phép deep access ở runtime nhưng không cho phép import package ở compile time.
8. **Cho rằng `privateLookupIn` sửa caller lookup.** Phương thức trả về lookup mới; lookup ban đầu không bị thay đổi.
9. **Nhầm lỗi tạo lookup với lỗi tìm field.** `IllegalAccessException` tại `privateLookupIn` khác `NoSuchFieldException` từ `findVarHandle`.
10. **Mở toàn bộ module khi chỉ cần một package.** Dùng qualified `opens` để giới hạn quyền.

## 14. Ghi nhớ

1. `MethodHandles.privateLookupIn` được giới thiệu trong Java 9 để tạo lookup có quyền private vào một lớp đích.
2. Caller lookup cần cả `PRIVATE` và `MODULE` modes.
3. Khi caller và target khác mô-đun, caller module phải đọc target module.
4. Package chứa target class phải được mở cho caller module; `exports` không thay thế `opens`.
5. Cùng mô-đun không cần mở package cho chính nó, nhưng caller lookup vẫn cần đủ modes.
6. Lookup cross-module giữ `PRIVATE` nhưng mất `MODULE`, vì vậy `hasFullPrivilegeAccess()` trả `false`.
7. `--add-opens` mở package; `--add-reads` thêm readability; hai tùy chọn không thay thế nhau.
8. Lookup là capability nhạy cảm; chỉ chia sẻ cho thành phần tin cậy và mở package ở phạm vi cần thiết.