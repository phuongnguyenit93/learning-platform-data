# Kiểm thử quyền truy cập Reflection trong cùng và khác module (Java 17+)

## 1. Mục tiêu kiểm thử

Java Reflection cho phép tìm metadata của class, field, method, constructor; **tìm thấy không đồng nghĩa được phép gọi**. Từ Java 9, Java Platform Module System (JPMS) bổ sung ranh giới module, đặc biệt quan trọng trên Java 17+ với strong encapsulation.

Một bộ kiểm thử quyền truy cập cần phân biệt:

1. **Quyền nhìn thấy kiểu ở mã nguồn:** Có thể import một public class từ package đó và biên dịch hay không?
2. **Quyền gọi public member thông thường:** Đường truy cập Java chuẩn vào public API có hợp lệ hay không?
3. **Khả năng lấy metadata:** Có lấy được đối tượng `Method`, `Field` hoặc `Constructor<?>` hay không?
4. **Khả năng sử dụng metadata:** Có gọi `Method.invoke`, `Field.get/set` hoặc `Constructor.newInstance` trực tiếp được không?
5. **Deep reflection:** Có được phép vô hiệu hóa kiểm tra truy cập thông thường bằng `trySetAccessible`/`setAccessible` hay không?
6. **Method handles:** Có tạo `Lookup` phù hợp bằng `privateLookupIn` rồi truy cập private member được không?
7. **Khác biệt môi trường chạy:** Classpath, named module, tùy chọn `opens` trong descriptor và `--add-opens` ở runtime có cho kết quả đúng với kỳ vọng không?

Đề bài “cùng và khác module” **không** chỉ là kiểm thử public/private. Java có thêm ranh giới **package, nest, class loader, module readability và package exports/opens**; không nên gom tất cả về một cờ `isPublic`.

## 2. Bốn khái niệm cần phân biệt: `public`, `requires`, `exports`, `opens`

Giả sử module `com.demo.client` gọi code của module `com.demo.domain`:

| Khái niệm | Vai trò |
| --- | --- |
| `public` trên class/member | Điều kiện visibility của ngôn ngữ Java; không một mình đủ để đi qua ranh giới module |
| `requires com.demo.domain;` | Thiết lập readability của client đối với domain khi biên dịch và chạy theo module graph |
| `exports com.demo.domain.api;` | Cho phép module khác truy cập public types và public members của package theo quy tắc Java thông thường |
| `opens com.demo.domain.internal to com.demo.client;` | Cho phép **deep reflection** vào package đích cho module client, gồm khả năng thử `setAccessible` và `privateLookupIn` theo điều kiện API |
| `open module com.demo.domain` | Mở mọi package trong module cho deep reflection; không đồng nghĩa tự động export chúng để import ở source |
| `--add-opens A/p=B` | Mở bổ sung package `p` của module `A` cho module `B` khi chạy, không sửa source/module-info |

**`exports` không tự cấp private access. `opens` không thay thế `exports` cho việc import public class từ module khác.** Có thể đồng thời export và open cùng package nếu vừa muốn public API vừa muốn deep reflection hợp lệ.

Cùng một **named module**, một caller có thể được phép dùng `setAccessible(true)` cho thành viên non-public của class khác trong module theo các điều kiện của Reflection. Điều đó **không có nghĩa mã nguồn Java thường được quyền gọi trực tiếp private member**; vẫn phải tuân thủ private/package/protected theo compiler.

Với **named module khác**, ngay cả private method của một public class trong package đã `exports` cũng không tự được deep reflection; cần package mở theo điều kiện thích hợp.

Trên **classpath**, ứng dụng thường thuộc unnamed module; các package của unnamed module được mở rộng cho deep reflection theo quy tắc JPMS. Đây là một trường hợp kiểm thử riêng, không phải bằng chứng rằng cùng code sẽ chạy khi chuyển sang named module.

## 3. Ma trận kỳ vọng khi kiểm thử

Ma trận sau giả định caller có quyền đọc module đích, không có cơ chế truy cập đặc quyền bổ sung, và target là một public class với public hoặc private method.

| Nơi gọi / cấu hình package đích | Gọi public member bằng Java thông thường | Deep reflection vào private method từ module khác |
| --- | --- | --- |
| Cùng named module | Có nếu thỏa visibility/package của Java | Thường được phép suppression đối với member trong cùng module |
| Khác module; package `exports`, không `opens` | Có đối với public type và public member | **Không** chỉ vì export |
| Khác module; package `opens ... to client`, không `exports` | Không thể import package đó như public API bình thường | **Có thể** nếu lookup/access phù hợp |
| Khác module; package `exports` và `opens` | Có đối với public API | Có thể deep-reflect nếu thỏa điều kiện |
| Khác module; không `exports`, không `opens` | Không thể truy cập trực tiếp từ source | Deep reflection thường bị từ chối |
| Trên classpath/unnamed module | Tuân theo visibility/package bình thường | Khác named module; cần kiểm thử riêng |

Bảng là **mô hình quyền** chứ không phải cam kết mọi lời gọi sẽ thành công. Ví dụ một receiver null không đúng chỗ, sai method signature, constructor ném exception hoặc hạn chế đối với final field vẫn gây lỗi độc lập với JPMS.

### API nào kiểm tra điều gì?

- `getDeclaredMethod("secret")`: tìm method khai báo trực tiếp, kể cả private, thường có thể trả metadata dù việc gọi bị cấm.
- `method.canAccess(receiver)`: kiểm tra quyền truy cập hiện tại cho member với receiver phù hợp, **không tự thay đổi** flag accessible. Với method static, dùng receiver `null`.
- `method.trySetAccessible()`: thử bật suppression, trả `true` hoặc `false` nếu access không được cho phép theo hợp đồng; có thể ném lỗi khác trong một số tình huống.
- `method.setAccessible(true)`: có thể ném `InaccessibleObjectException` khi không thể bật suppression, thay vì trả boolean.
- `method.invoke(receiver, args...)`: có thể ném `IllegalAccessException` nếu không có quyền, còn exception từ method đích thường được bọc bằng `InvocationTargetException`.
- `MethodHandles.privateLookupIn(target, callerLookup)`: có thể ném `IllegalAccessException` nếu caller không có quyền cần thiết, thiếu readability hoặc package ở module khác không mở phù hợp; có thêm ràng buộc lookup modes.
- `lookup.findVirtual(...)` hoặc `lookup.unreflect(method)`: có kiểm tra quyền với `Lookup` tương ứng; lấy `Method` trước đó không tạo đặc quyền.

Một test tốt ghi rõ **đối tượng, module của caller, module của target, package, mode và API được thử**. Đừng chỉ assert rằng có hoặc không ném exception nhưng bỏ mất nguyên nhân.

## 4. Bài thực hành: hai named module, cùng một chương trình kiểm thử

Ta tạo đúng hai module:

- `com.demo.domain` chứa public API được export và một class nội bộ **không export, không open** ban đầu.
- `com.demo.client` có `requires com.demo.domain` và kiểm tra cả việc gọi qua public API, Reflection từ bên ngoài, cùng một phép thử private Reflection chạy **bên trong** domain.

Cấu trúc thư mục:

```text
src/
├── com.demo.domain/
│   ├── module-info.java
│   └── com/demo/domain/
│       ├── api/Entry.java
│       └── internal/
│           ├── Hidden.java
│           └── Probe.java
└── com.demo.client/
    ├── module-info.java
    └── com/demo/client/Main.java
```

Đây là ví dụ Java 17+ độc lập, không cần thư viện bên ngoài. Các file bên dưới phải giữ đúng path/package.

### 4.1. Module domain chưa mở package nội bộ

Tạo `src/com.demo.domain/module-info.java`:

```java
module com.demo.domain {
    exports com.demo.domain.api;
}
```

Package `api` được export; package `internal` không được export cũng không được open cho client.

Tạo `src/com.demo.domain/com/demo/domain/internal/Hidden.java`:

```java
package com.demo.domain.internal;

public final class Hidden {
    public String publicMethod() {
        return "public-inside";
    }

    private String secret() {
        return "inside";
    }
}
```

`Hidden` là public **trong package không export**. Client không import được class này như public API chỉ vì nó có modifier `public`.

Tạo `src/com.demo.domain/com/demo/domain/internal/Probe.java`:

```java
package com.demo.domain.internal;

import java.lang.reflect.Method;

public final class Probe {
    private Probe() {}

    public static String sameModulePrivateCall()
            throws ReflectiveOperationException {
        Hidden target = new Hidden();
        Method method = Hidden.class.getDeclaredMethod("secret");

        if (!method.trySetAccessible()) {
            throw new AssertionError("Same-module access denied");
        }
        return (String) method.invoke(target);
    }
}
```

`Probe` gọi Reflection từ **cùng module** với `Hidden` (và trong ví dụ còn cùng package). Private method không được gọi trực tiếp trong mã nguồn của `Probe`, nhưng việc thử suppression bằng Reflection có thể được cho phép. Không cần `opens` chỉ để hai class trong cùng module thực hiện đường Reflection này.

Tạo `src/com.demo.domain/com/demo/domain/api/Entry.java`:

```java
package com.demo.domain.api;

import com.demo.domain.internal.Hidden;
import com.demo.domain.internal.Probe;

public final class Entry {
    private Entry() {}

    public static String ping() {
        return "pong";
    }

    public static Object newHidden() {
        return new Hidden();
    }

    public static String probeInside()
            throws ReflectiveOperationException {
        return Probe.sameModulePrivateCall();
    }
}
```

`Entry` là cửa ngõ public thuộc package đã export. Nó có thể dùng `Hidden`/`Probe` của package nội bộ vì cùng module. Client nhận object qua kiểu `Object` mà không import class nội bộ.

### 4.2. Module client và chương trình kiểm thử

Tạo `src/com.demo.client/module-info.java`:

```java
module com.demo.client {
    requires com.demo.domain;
}
```

Tạo `src/com.demo.client/com/demo/client/Main.java`:

```java
package com.demo.client;

import com.demo.domain.api.Entry;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public final class Main {
    public static void main(String[] args) throws Throwable {
        boolean expectOpen = args.length == 1
                && "open".equals(args[0]);

        System.out.println("same-module private="
                + Entry.probeInside());
        System.out.println("exported public=" + Entry.ping());

        Object target = Entry.newHidden();
        Class<?> targetClass = target.getClass();
        Method method = targetClass.getDeclaredMethod("secret");

        System.out.println("cross canAccess="
                + method.canAccess(target));

        boolean enabled = method.trySetAccessible();
        System.out.println("cross trySetAccessible=" + enabled);

        String reflectionResult;
        try {
            reflectionResult = (String) method.invoke(target);
        } catch (IllegalAccessException denied) {
            reflectionResult = "DENIED";
        }
        System.out.println("cross invoke=" + reflectionResult);

        String lookupResult;
        try {
            MethodHandles.Lookup privateLookup =
                    MethodHandles.privateLookupIn(
                            targetClass, MethodHandles.lookup());
            MethodHandle handle = privateLookup.findVirtual(
                    targetClass,
                    "secret",
                    MethodType.methodType(String.class));
            lookupResult = (String) handle.invoke(target);
        } catch (IllegalAccessException denied) {
            lookupResult = "DENIED";
        }
        System.out.println("privateLookupIn=" + lookupResult);

        boolean actualOpen = enabled
                && "inside".equals(reflectionResult)
                && "inside".equals(lookupResult);

        if (actualOpen != expectOpen) {
            throw new AssertionError(
                    "Expected open=" + expectOpen
                            + ", actual=" + actualOpen);
        }

        System.out.println("PASS " + (expectOpen ? "open" : "closed"));
    }
}
```

**Các điểm quan trọng:**

1. `Entry.probeInside()` thực hiện private Reflection **bên trong domain** và trả chuỗi `inside`. Đây là phép thử cùng module.
2. `Entry.ping()` gọi public API qua `exports`, không cần `opens`.
3. `target.getClass().getDeclaredMethod("secret")` minh họa việc tìm metadata non-public từ client; không suy ra quyền gọi.
4. `canAccess(target)` được gọi **trước** `trySetAccessible`. Vì client không có direct language access vào private method, kết quả là `false` trong cả hai kịch bản.
5. `trySetAccessible` sau đó phụ thuộc package `internal` có được mở cho module client hay không.
6. `privateLookupIn` được thử riêng. Nó không lấy quyền từ việc `method.trySetAccessible()` đã bật; nó dựa trên `Lookup` của caller và cấu hình module.
7. Dòng `PASS` chỉ xuất hiện nếu kết quả mở/đóng đúng như tham số chạy. Nếu quyền ngoài dự kiến, chương trình kết thúc bằng `AssertionError` (khác mã exit thành công).

**Phân biệt lỗi:** Các khối `catch` chỉ bắt `IllegalAccessException` để biểu diễn việc bị từ chối như `DENIED`. Không dùng `catch (Throwable ignored)` vì có thể vô tình nuốt lỗi chương trình không liên quan đến access. `main throws Throwable` chỉ nhằm đơn giản hóa ví dụ MethodHandle của bài thực hành.

## 5. Biên dịch và chạy trường hợp 1: module đóng

Từ thư mục chứa `src`, tạo thư mục output:

```bash
mkdir out
```

Biên dịch cả hai module (lệnh viết một dòng để dùng trên shell phổ biến, kể cả PowerShell):

```bash
javac -d out --module-source-path src src/com.demo.domain/module-info.java src/com.demo.domain/com/demo/domain/api/Entry.java src/com.demo.domain/com/demo/domain/internal/Hidden.java src/com.demo.domain/com/demo/domain/internal/Probe.java src/com.demo.client/module-info.java src/com.demo.client/com/demo/client/Main.java
```

Chạy **không bổ sung quyền mở package**:

```bash
java --module-path out -m com.demo.client/com.demo.client.Main closed
```

Stdout mong đợi:

```text
same-module private=inside
exported public=pong
cross canAccess=false
cross trySetAccessible=false
cross invoke=DENIED
privateLookupIn=DENIED
PASS closed
```

Giải thích: public API thuộc package `api` được export nên gọi được; test private Reflection chạy **bên trong domain** thành công. Nhưng từ client, package `internal` không được open, vì vậy `trySetAccessible` trả `false`; `Method.invoke` không được phép gọi private method; `privateLookupIn` không được cấp private lookup sang package đóng.

Nếu thay `trySetAccessible()` bằng `setAccessible(true)` ở client, tình huống package không mở có thể ném `InaccessibleObjectException`. Đó là một tín hiệu lỗi khác với `IllegalAccessException` của `Method.invoke`/`privateLookupIn`.

## 6. Chạy trường hợp 2: mở package có chọn lọc bằng `--add-opens`

Không sửa source hoặc build. Chạy lại **cùng file class** với một quyền mở bổ sung:

```bash
java --module-path out --add-opens com.demo.domain/com.demo.domain.internal=com.demo.client -m com.demo.client/com.demo.client.Main open
```

Stdout mong đợi:

```text
same-module private=inside
exported public=pong
cross canAccess=false
cross trySetAccessible=true
cross invoke=inside
privateLookupIn=inside
PASS open
```

Tại sao `canAccess` vẫn in `false`? Lời gọi được thực hiện **trước khi bật accessible override** và kiểm tra quyền gọi Java thông thường. `--add-opens` làm deep reflection **có thể được phép khi yêu cầu**, không biến private member thành public trong source.

Tại sao `privateLookupIn` thành công? Client đọc domain qua `requires`; domain đã mở `com.demo.domain.internal` **cho module client** nên lookup có thể được cấp quyền theo hợp đồng `privateLookupIn`.

### 6.1. Mở package bằng descriptor thay cho command line

Cũng có thể thay file `src/com.demo.domain/module-info.java` bằng:

```java
module com.demo.domain {
    exports com.demo.domain.api;
    opens com.demo.domain.internal to com.demo.client;
}
```

Đây là **phiên bản thay thế** của cùng một file, không được tạo hai `module-info.java` cho module domain. Biên dịch lại bằng lệnh ở mục 5, sau đó chạy mà không cần `--add-opens`:

```bash
java --module-path out -m com.demo.client/com.demo.client.Main open
```

Kết quả dự kiến giống kịch bản `open` ở trên. Qualified opens chỉ cấp deep reflection cho module được liệt kê; module thứ ba không tự nhận quyền ấy. Đối với môi trường production, khai báo `opens` có chọn lọc thường rõ ràng hơn việc mở toàn bộ module.

**Lưu ý thực hành:** Sau khi sửa descriptor thành `opens`, muốn kiểm tra lại trường hợp `closed` thật sự phải trở về phiên bản module-info ban đầu và build lại. Nếu không, việc chạy tham số `closed` có thể thất bại ở assertion vì bạn đang thử một module đã mở.

## 7. Ba phép thử bổ sung giúp tránh kết luận sai

### 7.1. `--add-exports` không tương đương `--add-opens`

Với phiên bản domain **chưa open** ở mục 4, thử:

```bash
java --module-path out --add-exports com.demo.domain/com.demo.domain.internal=com.demo.client -m com.demo.client/com.demo.client.Main closed
```

`--add-exports` giúp client có quyền truy cập **public API** của package đó theo quy tắc export, nhưng **không mở private member cho deep reflection**. Vì test `secret()` là private, kết quả kỳ vọng vẫn là kịch bản `closed`. Không dùng `--add-exports` để “sửa” thất bại của `privateLookupIn`.

### 7.2. Metadata có mặt không đồng nghĩa member gọi được

Trong cả hai kịch bản, `getDeclaredMethod("secret")` trả về `Method`. Nó chứng minh metadata có thể được truy xuất, không chứng minh truy cập trực tiếp hợp lệ.

Ngược lại, nếu gọi nhầm tên/signature:

```java
Method missing = targetClass.getDeclaredMethod("unknown");
```

Đoạn trên minh họa lỗi trong ngữ cảnh client, ném `NoSuchMethodException` chứ **không** phải lỗi JPMS. Một bộ test nên tách case “không tìm thấy” khỏi “tìm thấy nhưng bị từ chối”.

### 7.3. `public` trong package không export vẫn bị ràng buộc

`Hidden.publicMethod()` là method `public` của class `public`, nhưng package chứa nó không export. Bản thân hai modifier `public` ấy không cho client quyền compile-time import `Hidden`. Có thể lấy metadata của method qua `target.getClass().getMethod("publicMethod")`, song thao tác `invoke` từ client còn phải tuân thủ quyền của declaring class/package; không thể thay thế `exports` bằng việc chỉ kiểm tra `Modifier.isPublic(...)`.

Nếu package được `opens` mà chưa `exports`, deep reflection sau khi bật override có thể hoạt động, nhưng điều đó vẫn không biến package thành public API để client import trong source.

## 8. Dùng `canAccess`, `trySetAccessible` và `setAccessible` đúng cách

| API | Trạng thái thay đổi? | Kết quả/biểu hiện quan trọng |
| --- | --- | --- |
| `canAccess(receiver)` | Không | `boolean` về khả năng access với trạng thái hiện tại |
| `trySetAccessible()` | Có thể bật accessible override nếu được phép | `true` nếu bật được; `false` khi không thể suppress access |
| `setAccessible(true)` | Cố bật accessible override | Có thể ném `InaccessibleObjectException` nếu JPMS không cho |
| `setAccessible(false)` | Tắt override trên đối tượng metadata được thao tác | Không đổi module graph |
| `Method.invoke(...)` | Thực thi member khi có quyền | `IllegalAccessException` nếu bị chặn; code đích có thể bọc lỗi bằng `InvocationTargetException` |

**Receiver hợp lệ rất quan trọng:**

- `Method.canAccess(instance)`: dùng instance phù hợp với instance method.
- `Method.canAccess(null)`: dùng `null` cho static method.
- `Field.canAccess(instance)`: field instance cần receiver đúng kiểu; field static dùng `null`.
- `Constructor.canAccess(null)`: constructor dùng receiver `null`.

Receiver sai có thể khiến `canAccess` ném `IllegalArgumentException`. Không coi mọi exception trong phép kiểm tra quyền là bằng chứng JPMS từ chối.

Các cách thay đổi accessible override chỉ nên dùng khi hợp đồng framework yêu cầu; tránh gọi `setAccessible(true/false)` liên tục trên cùng một `AccessibleObject` được cache và chia sẻ giữa thread. Việc này gây khó lập luận về quyền và trạng thái truy cập. Một test có thể dùng metadata riêng và chủ động ghi lại ai đã bật override.

## 9. Kiểm thử `MethodHandles.Lookup` và `privateLookupIn`

`MethodHandles.lookup()` tạo lookup với các quyền theo lớp caller. `publicLookup()` giới hạn hơn. `privateLookupIn(targetClass, callerLookup)` không hoạt động chỉ nhờ có `Class<?>` của target: phải đáp ứng **lookup modes**, khả năng đọc module và quyền mở package.

Hai câu hỏi kiểm thử nên tách rời:

1. **Tìm được method bằng Reflection không?** `getDeclaredMethod` có thể trả metadata.
2. **Có quyền tạo handle với private lookup không?** `privateLookupIn` và `findVirtual` cần permission riêng.

Trong ví dụ, dù `method.trySetAccessible()` thành công ở kịch bản open, `privateLookupIn` **không** được cấp quyền do đối tượng `Method` đó đổi cờ; nó xét quyền của `Lookup` và module graph. Nếu dùng `Lookup` không có đầy đủ quyền cần thiết, open package vẫn chưa bảo đảm thành công.

Không nên cache một `Lookup` có quyền private rồi đưa tùy ý qua plugin hoặc người dùng không đáng tin. Module boundaries là một phần của chính sách truy cập code; quyền truy cập nghiệp vụ và xác thực người dùng là lớp kiểm soát bổ sung.

Ngoài `findVirtual`, cách unreflect như `lookup.unreflect(method)` cũng phải chịu kiểm tra quyền của lookup. Đừng giả định method handle “bỏ qua” encapsulation.

## 10. Kiểm thử field, constructor và các kiểu lỗi

Cùng tư duy có thể mở rộng từ method tới field/constructor:

| Member | Metadata lookup | Thử quyền và thực thi |
| --- | --- | --- |
| Private instance field | `getDeclaredField("value")` | `canAccess(instance)`, `trySetAccessible()`, `get(instance)`/`set(instance, value)` |
| Private static field | `getDeclaredField("COUNT")` | `canAccess(null)`, `trySetAccessible()`, `get(null)` |
| Private constructor | `getDeclaredConstructor(types...)` | `canAccess(null)`, `trySetAccessible()`, `newInstance(args...)` |
| Private instance method | `getDeclaredMethod(name, types...)` | `canAccess(instance)`, `trySetAccessible()`, `invoke(instance, args...)` |

**Không ghi thử vào `final` field chỉ để chứng minh quyền.** Một field final có hạn chế ghi riêng, và thành công khi đọc hoặc suppress access không đồng nghĩa ghi hợp lệ. `VarHandle` đối với final field có thể chỉ hỗ trợ các access mode đọc. Với constructor, có thể có side effect từ việc tạo object; dùng class fixture đơn giản không tương tác mạng/file/hệ thống.

Các exception cần phân loại:

- `ClassNotFoundException`: không tìm được type theo tên/loader.
- `NoSuchMethodException`, `NoSuchFieldException`: metadata không có member theo tiêu chí tìm kiếm.
- `IllegalAccessException`: thao tác Reflection hoặc Lookup không có quyền tương ứng.
- `InaccessibleObjectException` (unchecked): không thể bật suppression qua `setAccessible(true)` theo chính sách module/access.
- `InvocationTargetException`: method/constructor đích được gọi qua Reflection ném exception; đọc `getCause()` để xem lỗi thực.
- `IllegalArgumentException`: đối số, receiver hoặc kiểu truyền cho Reflection không phù hợp.
- `WrongMethodTypeException`: kiểu lời gọi `MethodHandle.invokeExact` không đúng với `MethodType`.
- `ExceptionInInitializerError` và lỗi nạp/liên kết class: độc lập với quyền truy cập member; cần điều tra riêng.

Một bộ test tốt không được bắt tất cả lỗi rồi “PASS blocked”: như vậy có thể biến lỗi lập trình thành kết quả giả đúng.

## 11. Đảm bảo test đúng module, không vô tình rơi về classpath

Các lỗi cấu hình chạy test thường gặp:

- Chạy `java -cp ...` thay vì `--module-path ... -m ...`, khiến class nằm trong unnamed module và hành vi deep reflection khác dự kiến.
- Thiếu `requires` hoặc không resolve module đích, dẫn tới lỗi module graph, nhầm là lỗi private access.
- Thêm `--add-opens` trong cấu hình IDE/JUnit mà quên rằng production không có, khiến test xanh giả.
- Build tool đưa test code vào **cùng module** với code đích, trong khi mục tiêu là mô phỏng caller ở **module khác**.
- Phép thử dùng một public class trong package được export mà quên xác minh package private/closed thật sự, khiến không bao giờ kiểm tra strong encapsulation.
- Dùng `setAccessible(true)` hoặc `trySetAccessible` từ code trong target module rồi kết luận module bên ngoài cũng có quyền.
- Dùng version JDK, launcher flags và plugin/module path khác nhau giữa CI và môi trường chạy thật.

Khi cần chẩn đoán, có thể in ra module thực tế của caller và target bằng đoạn minh họa sau:

```java
System.out.println(Main.class.getModule().getName());
System.out.println(target.getClass().getModule().getName());
System.out.println(target.getClass().getModule().isOpen(
        target.getClass().getPackageName(),
        Main.class.getModule()));
```

Đặt snippet này trong `Main.main` của ví dụ. Với cấu hình gốc, hai tên module là `com.demo.client` và `com.demo.domain`; dòng cuối phản ánh việc package nội bộ có mở cho client tại runtime hay không. Với `--add-opens`, một kiểm tra `Module.isOpen(package, clientModule)` có thể giúp xác nhận module đã được mở đúng đối tượng.

Để test JUnit tích hợp có ý nghĩa, hãy dùng **hai fixture chạy ở module boundaries thực** hoặc một harness fork process với các launcher flags kiểm soát được. Không nhất thiết phải nhúng mọi trường hợp trong một JUnit test chạy trên classpath.

## 12. Bộ tiêu chí PASS/FAIL và negative tests

Một bộ kiểm thử tối thiểu nên bao gồm cả case được phép và bị chặn:

| Ca kiểm thử | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Same-module private reflection | Thành công trong fixture `Probe` | Xác nhận quyền suppression nội bộ |
| Cross-module public exported API | Thành công với `Entry.ping()` | Xác nhận `requires` + `exports` |
| Cross-module private trong package đóng | `trySetAccessible=false`; gọi không override bị từ chối | Xác nhận strong encapsulation |
| Cross-module `privateLookupIn` khi package đóng | Bị từ chối | Xác nhận lookup không tự vượt JPMS |
| Cross-module private với `--add-opens`/qualified `opens` | Deep reflection thành công | Xác nhận mở đúng module đích |
| Cross-module chỉ `--add-exports` | Private deep reflection vẫn bị từ chối | Phân biệt exports/opens |
| Sai method signature | `NoSuchMethodException` | Phân biệt lookup error và access error |
| Receiver sai/null khi member instance | Exception phù hợp | Xác nhận không nhầm input error với quyền |
| Constructor/field private | Có case allowed/denied tương ứng | Mở rộng rule sang member khác |
| Chạy CI thật qua module path | PASS cả positive và negative tests | Tránh false positive classpath |

Nên để test in/ghi log **cấu hình module**, actual exception type và trạng thái `trySetAccessible`. Với các phép thử negative, assert **đúng kiểu lỗi hoặc giá trị boolean**, không chỉ assert “bất kỳ exception nào cũng được”.

Nếu test thay đổi `module-info.java`, hãy biên dịch lại sạch và chạy lại từ trạng thái module graph đã xác định. Nếu test chạy bằng `--add-opens`, ghi rõ launcher flag để CI và môi trường khác có thể lặp lại chính xác.

## 13. Checklist trước khi dùng Reflection xuyên module trong sản phẩm

1. Xác định chính xác **caller module**, **target module**, package đích và member cần truy cập.
2. Hỏi liệu public API có đủ không. Nếu đủ, dùng `exports` và API public thay vì deep reflection.
3. Nếu cần private reflection, chỉ mở đúng package cho module đáng tin; ưu tiên qualified `opens` thay vì mở toàn cục.
4. Tách kiểm tra metadata có tồn tại khỏi kiểm tra quyền thực thi; không dùng `isPublic` làm kết luận duy nhất.
5. Kiểm thử `canAccess`, `trySetAccessible`, `Method.invoke` và `privateLookupIn` trong **đúng** bối cảnh caller.
6. Không lạm dụng `setAccessible` hoặc launcher `--add-opens` để che đi một thiết kế API sai.
7. Không tùy tiện gọi method/constructor chỉ để kiểm tra quyền nếu chúng có side effect; dùng fixture an toàn.
8. Đưa cả case thành công và bị từ chối vào CI, kiểm tra module path/JDK/VM flags, và ghi nhận trạng thái thực.
9. Khi dùng cached `Method`/`Field`/`Lookup`, phải đánh giá thêm quyền và điều kiện thread-safety; quyền/module không tự biến thành chính sách bảo mật của người dùng.

### Tự kiểm tra

1. Vì sao `getDeclaredMethod("secret")` vẫn có thể thành công trong module client dù `invoke` bị từ chối?
2. `exports` và `opens` khác nhau thế nào? Một package được export có cho phép đọc private field từ module khác không?
3. Vì sao `canAccess` được gọi **trước** `trySetAccessible` trong bài thực hành?
4. Vì sao kịch bản open vẫn in `cross canAccess=false` nhưng sau đó `Method.invoke` lại thành công?
5. Khi nào `privateLookupIn` không thành công dù đã lấy được `Method` bằng Reflection?
6. Nếu chạy thử trên classpath rồi chuyển sang module path, vì sao quyền deep reflection có thể thay đổi?
7. Vì sao test âm tính nên kiểm tra `IllegalAccessException` hoặc `false` thay vì bắt mọi `Throwable`?
8. Làm sao chứng minh quyền được mở cho module client mà không mở cho mọi module khác?

**Ghi nhớ:** Kiểm thử quyền Reflection phải chạy trong **module graph và nơi gọi thực tế**. `public` và `exports` giải quyết public API; `opens` và `privateLookupIn` liên quan tới deep reflection. Việc **tìm metadata**, **công bố quyền truy cập** và **thực thi member** là ba bước khác nhau; muốn test đáng tin, cần kiểm tra cả trường hợp được phép lẫn bị từ chối.
