# 5.4. Khác biệt về kiểm tra module readability giữa Reflection và `MethodHandles.Lookup`

Trong Java Platform Module System (JPMS), **readability** là quan hệ giữa hai module: module `M1` *reads* module `M2` khi `M1` được phép phụ thuộc vào các kiểu của `M2` theo quy tắc module. Tuy nhiên, không phải mọi cơ chế gọi phương thức lúc chạy đều xử lý readability giống nhau.

Điểm cần nhớ của bài này:

- **Core Reflection** (`java.lang.reflect.Method`, `Field`, `Constructor`, kế thừa `AccessibleObject`) **giả định quan hệ readability đã tồn tại khi thực hiện kiểm tra quyền truy cập phản chiếu**. Nó vẫn kiểm tra `public`, `exports`, `opens` và các điều kiện khác; sự giả định này **không thêm read edge** vào module graph.
- **`MethodHandles.lookup()`** tạo `Lookup` gắn với caller thực tế. Khi dùng các phương thức như `findStatic`, `findVirtual`, `findGetter`, `Lookup` thông thường **kiểm tra readability** trong quá trình tạo handle, cùng với accessibility và lookup modes.
- **`MethodHandles.publicLookup()` là ngoại lệ cần nhớ**: chế độ `UNCONDITIONAL` cũng giả định readability, nhưng chỉ cho phép truy cập public members của public types trong package được **export vô điều kiện**.
- **`MethodHandles.privateLookupIn(target, callerLookup)`** không được miễn readability: nếu target thuộc module khác, caller module **phải đọc** target module, **và** target package phải `opens` tới caller module; caller lookup còn phải có đủ quyền `PRIVATE` và `MODULE`.

Bài học sử dụng Java 17+ và một thí nghiệm có **hai named modules** để bạn thấy một lời gọi Reflection thành công trong khi một `Lookup` thông thường thất bại, dù chúng cùng nhắm vào một phương thức `public static`.

## 1. Tách bốn lớp điều kiện: resolution, readability, exports và opens

Trước khi phân tích lời gọi, hãy xác định chính xác điều kiện nào đang được hỏi.

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
| --- | --- | --- |
| **Resolution** | Module có được đưa vào module graph của lần chạy này không? | `--add-modules m.lib` buộc resolver chọn `m.lib` |
| **Readability** | Module người dùng có *reads* module đích không? | `module m.client { requires m.lib; }` hoặc runtime `--add-reads m.client=m.lib` |
| **Exports** | Package đích có công khai **public types/members** cho module gọi không? | `exports demo.lib;` hoặc `exports demo.lib to m.client;` |
| **Opens** | Package đích có cho phép **deep reflection** đối với module gọi không? | `opens demo.lib to m.client;` |

Đây là bốn điều kiện **khác nhau**. `exports` không tự tạo quan hệ `reads`. `opens` không tự tạo quan hệ `reads`. Một module được resolve cũng không có nghĩa một module bất kỳ tự động đọc nó.

Giả sử `m.client` và `m.lib` là hai **named modules**. `m.client` muốn dùng class `demo.lib.Service` của `m.lib`:

1. Runtime cần có cách nạp class đó, do vậy module đích phải được resolve và class loader phù hợp phải tìm được class.
2. Một phép truy cập Java thông thường hoặc `Lookup` thông thường sẽ cần các điều kiện readability và accessibility liên quan.
3. Nếu dùng Reflection, kiểm tra quyền truy cập qua `AccessibleObject` **giả định** bước readability, nhưng vẫn cần class/member `public` trong package được `exports` phù hợp để truy cập thông thường.
4. Nếu muốn gọi private method qua deep reflection, package phải `opens` phù hợp và cần bật quyền truy cập khi được phép; `exports` đơn thuần không đủ.
5. Nếu muốn `privateLookupIn` qua ranh giới module, cần **cả readability lẫn opens**, dù Reflection đã có thể truy cập private method bằng `trySetAccessible()`.

Có thể kiểm tra quan hệ đọc ở runtime:

```java
boolean readable = callerClass.getModule().canRead(targetClass.getModule());
```

Đây là **đoạn mã minh họa** sử dụng `callerClass` và `targetClass` đã có; nó không tự biên dịch thành chương trình độc lập. `Module.canRead` cho biết quan hệ đọc trong graph ở thời điểm kiểm tra; nó không tự suy ra package đã được `exports` hoặc `opens`.

> Không nên thử thí nghiệm này chỉ với classpath: code classpath nằm trong unnamed module, có quy tắc readability đặc biệt đối với các module đã resolve. Hai named modules không có `requires` tạo tình huống rõ ràng hơn.

## 2. Core Reflection vì sao có thể vượt qua thiếu readability?

`Method`, `Field` và `Constructor` đều là các reflected objects kế thừa `AccessibleObject`. Theo hợp đồng Java SE 17, khi reflected object kiểm tra Java language access, nó có **một khác biệt** so với kiểm tra thông thường: **module của code sử dụng reflected object được xem như có thể đọc module chứa member được phản chiếu**.

Ví dụ, nếu class và method đích đều `public`, package đích được `exports` tới caller, và caller đã có một `Class<?>` hay `Method` hợp lệ, thì `method.invoke(...)` có thể thành công **dù** `callerModule.canRead(targetModule)` trả về `false`.

Điểm giới hạn:

- Giả định readability áp dụng trong **access checks của reflected objects**, không tự thực hiện `callerModule.addReads(targetModule)`, không chỉnh sửa `module-info.class` và không biến mọi module chưa resolve thành có sẵn.
- **Visibility** vẫn quan trọng: một private method không trở thành public chỉ nhờ giả định readability.
- **`exports`/`opens`** vẫn quan trọng: một `public` method trong package không được export thích hợp có thể bị chặn; để dùng deep reflection vượt visibility khi ở module khác, package phải mở cho caller theo chính sách tương ứng.
- Lấy metadata (`getMethod`, `getDeclaredMethod`) và thực sự gọi (`invoke`), đọc/ghi (`Field.get`/`set`) hoặc tạo instance (`Constructor.newInstance`) là các bước khác nhau. Tìm được metadata không đủ chứng minh member có thể truy cập.
- `setAccessible(true)` hoặc `trySetAccessible()` không phải quyền toàn năng. Nếu package không `opens` phù hợp, việc yêu cầu bỏ kiểm tra quyền cho non-public member xuyên module có thể thất bại.

Tính chất này làm Core Reflection hữu ích cho công cụ, framework và code cần truy cập kiểu được phát hiện động. Nó **không nên** được hiểu là mọi API runtime đều ngầm bỏ qua module readability.

## 3. `MethodHandles.Lookup`: quyền gắn với lookup class

`MethodHandles.lookup()` là API caller-sensitive: `Lookup` trả về lưu **lookup class** là class gọi API. Các phương thức như:

```java
lookup.findStatic(targetClass, "run", methodType(void.class));
lookup.findVirtual(targetClass, "name", methodType(String.class));
lookup.findGetter(targetClass, "count", int.class);
```

là **đoạn minh họa** dùng biến `lookup` và `targetClass` có sẵn. Các lệnh này tạo `MethodHandle` sau khi kiểm tra quyền của lookup class, `Lookup.lookupModes()`, class/member accessibility và quan hệ module áp dụng. Không nên hiểu các ví dụ là ba lệnh luôn thành công.

Với `Lookup` thông thường có `PUBLIC` mode và không có previous lookup class, khi truy cập class `public` ở module khác, module của lookup class phải **đọc được** module đích; package đích cũng phải được `exports` tối thiểu tới module của lookup class.

`Lookup` có các đặc điểm quan trọng:

- **Quyền được kiểm tra lúc tạo method handle.** Khi đã tạo hợp lệ, method handle không chạy lại cùng một kiểm tra truy cập mỗi lần `invoke`/`invokeExact`. Core Reflection thì kiểm tra quyền khi mỗi caller sử dụng reflected object theo quy tắc của API.
- `MethodHandles.lookup()` tạo một capability đại diện cho quyền của caller. Chuyển nó cho code khác nghĩa là trao quyền tạo handle trên phạm vi mà lookup đó cho phép; không nên công khai một full-privilege lookup bừa bãi.
- `lookup.in(Other.class)` không tự cấp thêm quyền: khi đổi lookup class, các mode có thể **bị giảm**; qua biên giới module, previous lookup class có thể khiến các kiểm tra giới hạn hơn.
- `Lookup.lookupModes()` cho thấy các bit quyền, nhưng riêng việc có `PUBLIC` bit **không bảo đảm** module đích có thể được đọc hay package được export.

Một `Lookup` thông thường hoạt động gần với ngữ nghĩa truy cập Java/bytecode hơn là quy tắc ưu tiên tiện lợi của Core Reflection.

## 4. Ngoại lệ: `publicLookup()` có `UNCONDITIONAL`

Không được khái quát rằng **mọi** `MethodHandles.Lookup` đều từ chối nếu thiếu readability.

`MethodHandles.publicLookup()` trả một lookup quyền hạn tối thiểu có `UNCONDITIONAL` mode. Theo API Java SE 17, mode này **giả định readability**, vì vậy nó có thể tạo handle tới:

- public member
- thuộc public type
- nằm trong package được **exports vô điều kiện** (`exports some.package;`) từ module đích.

Ví dụ:

```java
MethodHandles.Lookup openPublic = MethodHandles.publicLookup();
```

Đây chỉ là một khai báo minh họa; class chạy độc lập ở phần 6 sẽ thể hiện đầy đủ.

`publicLookup()` không phải cách vượt quyền. Nếu package chỉ `exports p to m.client` (qualified export), thì `UNCONDITIONAL` **không** được hưởng quyền export đó như một lookup bình thường gắn với `m.client`. Nó cũng không thể đột nhiên truy cập `private` member, và không có quyền cần thiết để dùng `privateLookupIn` chỉ bằng chính `publicLookup()`.

Nói chính xác hơn:

| Lựa chọn | Kiểm tra readability với module đích | Điều kiện khác cần chú ý |
| --- | --- | --- |
| Core Reflection qua `AccessibleObject` | **Giả định có** trong access check của reflected object | Visibility và `exports`/`opens` vẫn áp dụng |
| `MethodHandles.lookup()` + `find*` | **Có kiểm tra**, theo module của lookup class (và previous lookup class nếu có) | Lookup modes và accessibility |
| `MethodHandles.publicLookup()` + `find*` | `UNCONDITIONAL` **giả định có** | Chỉ public types/members trong package export vô điều kiện |
| `MethodHandles.privateLookupIn(target, caller)` xuyên module | **Bắt buộc** caller module reads target module | Target package **opens** tới caller; caller có `PRIVATE` và `MODULE` modes |

Bảng này mô tả các API thông dụng. Một số biến thể `Lookup.unreflect*` còn có quy tắc riêng khi nhận một reflected object đã bật accessible flag; xem mục 9 để tránh suy diễn máy móc.

## 5. Deep reflection và `privateLookupIn`: vì sao `opens` chưa đủ?

Giả sử `m.lib` khai báo:

```java
module m.lib {
    opens demo.lib to m.client;
}
```

Đoạn này **chưa** cho biết `m.client` đọc được `m.lib`, và cũng không phải lệnh `exports demo.lib` cho truy cập Java thông thường. Nhưng nếu `m.client` đã nạp được class phù hợp và được `opens` cấp quyền deep reflection, thì `trySetAccessible()` trên private member có thể thành công.

Trái lại, để chạy:

```java
MethodHandles.Lookup privateAccess =
        MethodHandles.privateLookupIn(targetClass, MethodHandles.lookup());
```

khi `targetClass` ở module khác, Java SE 17 yêu cầu:

1. Lookup truyền vào có **`PRIVATE` và `MODULE` modes** thích hợp (full-privilege lookup).
2. Target là class hợp lệ (không phải primitive/array/`void`).
3. Caller module **reads** target module.
4. Target module **opens** package chứa target class tối thiểu tới caller module.
5. Những kiểm tra bảo mật khác (nếu môi trường có) không từ chối.

Thiếu readability sẽ khiến `privateLookupIn` ném `IllegalAccessException` **kể cả khi** `Method.trySetAccessible()` cho private method cùng class đã trả `true`. Khi truy cập qua module khác thành công, `Lookup` mới có quyền private trên target nhưng mất `MODULE` mode; không được giả định có thể mang lookup này đi để nhảy qua nhiều module tiếp theo.

Điểm cốt lõi: **`opens` giải quyết quyền deep access; `reads` giải quyết khả năng module tham chiếu tới module kia theo cơ chế Lookup.** Một điều kiện không thay thế điều kiện còn lại.

## 6. Thực hành Java 17+: cùng một method, hai hành vi kiểm tra khác nhau

Tạo thư mục/tệp với cấu trúc chính xác:

```text
src/
├── m.lib/
│   ├── module-info.java
│   └── demo/lib/Service.java
└── m.client/
    ├── module-info.java
    └── demo/client/Main.java
```

Đây là **một chương trình nhiều module**. Tất cả các tệp dưới đây phải được tạo đúng đường dẫn rồi mới chạy lệnh `javac` ở thư mục cha của `src`.

**Tệp `src/m.lib/module-info.java`:**

```java
module m.lib {
    exports demo.lib;
    opens demo.lib to m.client;
}
```

- `exports demo.lib;` cho phép truy cập công khai, vô điều kiện, vào public types của package.
- `opens demo.lib to m.client;` cho phép code của `m.client` yêu cầu deep reflection đối với package, trong giới hạn API.
- Hai dòng này **không** làm `m.client` đọc `m.lib`.

**Tệp `src/m.lib/demo/lib/Service.java`:**

```java
package demo.lib;

public class Service {
    public static String hello() {
        return "hello-from-library";
    }

    private static String hidden() {
        return "hidden";
    }
}
```

**Tệp `src/m.client/module-info.java`:**

```java
module m.client {
}
```

Cố ý **không** khai báo `requires m.lib;`, nhờ vậy module client chưa có read edge tới module library. Main sẽ tìm class bằng chuỗi tên runtime, tránh tham chiếu trực tiếp tới kiểu `Service` trong mã nguồn client.

**Tệp `src/m.client/demo/client/Main.java`:**

```java
package demo.client;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        Class<?> target = Class.forName("demo.lib.Service");

        System.out.println("readable="
                + Main.class.getModule().canRead(target.getModule()));

        // Core Reflection: access check giả định readability.
        System.out.println("reflection="
                + target.getMethod("hello").invoke(null));

        // Deep Reflection: phụ thuộc opens, không đòi read edge.
        var privateMethod = target.getDeclaredMethod("hidden");
        System.out.println("open=" + privateMethod.trySetAccessible());
        System.out.println("deepReflection=" + privateMethod.invoke(null));

        var lookup = MethodHandles.lookup();
        try {
            var handle = lookup.findStatic(
                    target, "hello", MethodType.methodType(String.class));
            System.out.println("lookup=" + (String) handle.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("lookup=denied");
        }

        // UNCONDITIONAL: public API + unqualified export.
        var publicHandle = MethodHandles.publicLookup().findStatic(
                target, "hello", MethodType.methodType(String.class));
        System.out.println("publicLookup="
                + (String) publicHandle.invokeExact());

        // privateLookupIn: cần cả reads và opens.
        try {
            var privileged = MethodHandles.privateLookupIn(target, lookup);
            var handle = privileged.findStatic(
                    target, "hidden", MethodType.methodType(String.class));
            System.out.println("privateLookup=" + (String) handle.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookup=denied");
        }
    }
}
```

Chương trình `Main` cố ý bắt **riêng** `IllegalAccessException` cho các phép lookup có thể bị từ chối, rồi in `denied`. Các exception khác được để lộ ra qua `throws Throwable` để tránh che giấu lỗi thiết lập bài thực hành.

### 6.1. Biên dịch cả hai module

Trong thư mục chứa `src`, chạy:

```bash
javac --release 17 -d mods --module-source-path src src/m.lib/module-info.java src/m.lib/demo/lib/Service.java src/m.client/module-info.java src/m.client/demo/client/Main.java
```

Lệnh trên tạo các compiled modules ở `mods/m.lib` và `mods/m.client`; nó chỉ cần JDK 17 trở lên. Các tệp không có ký tự phụ thuộc shell, nên tham số tường minh hoạt động cả trong Bash và PowerShell.

### 6.2. Chạy KHÔNG có read edge

```bash
java --module-path mods --add-modules m.lib -m m.client/demo.client.Main
```

Kết quả:

```text
readable=false
reflection=hello-from-library
open=true
deepReflection=hidden
lookup=denied
publicLookup=hello-from-library
privateLookup=denied
```

`--add-modules m.lib` **resolve** module library để class có thể được nạp; nó **không** thêm `requires`/`reads` từ `m.client` sang `m.lib`. `Class.forName` có thể nạp class trong cấu hình class loader của thí nghiệm. Điều này không có nghĩa một module chưa resolve hoặc class loader bất kỳ luôn tìm được class đó.

Phân tích chính xác từng dòng:

- `readable=false`: `m.client` chưa đọc `m.lib` theo module graph.
- `reflection=hello-from-library`: public method trong public class của package được export vô điều kiện; **Core Reflection giả định readability trong access check**.
- `open=true`: package `demo.lib` mở cho `m.client`, nên `trySetAccessible()` cho private method thành công. Mở package vẫn không tạo read edge.
- `deepReflection=hidden`: sau khi bật access hợp lệ, private method có thể được invoke phản chiếu.
- `lookup=denied`: `MethodHandles.lookup()` gắn với class `Main` trong `m.client`; `findStatic` không thể tạo handle vì module của lookup class không reads `m.lib`.
- `publicLookup=hello-from-library`: lookup `UNCONDITIONAL` được truy cập public member trong package `exports` vô điều kiện, mặc dù không có read edge.
- `privateLookup=denied`: `privateLookupIn` không chấp nhận thiếu readability, dù `opens` đã có.

### 6.3. Chạy CÓ read edge

Không cần sửa source; chỉ thêm một runtime read edge để cô lập đúng biến đang thử:

```bash
java --module-path mods --add-modules m.lib --add-reads m.client=m.lib -m m.client/demo.client.Main
```

Kết quả:

```text
readable=true
reflection=hello-from-library
open=true
deepReflection=hidden
lookup=hello-from-library
publicLookup=hello-from-library
privateLookup=hidden
```

So với lần chạy trước, chỉ ba dòng chính thay đổi: `readable` từ `false` thành `true`, `lookup` từ `denied` thành kết quả public method, và `privateLookup` từ `denied` thành kết quả private method. Hai phép Reflection và `publicLookup` vẫn thành công như trước.

Cả hai lượt chạy trên được xây dựng và kiểm tra với `javac --release 17` trong môi trường JDK hỗ trợ Java 17+. Những giá trị được in không phụ thuộc số hash, danh sách module ngẫu nhiên hay địa chỉ bộ nhớ.

Trong ứng dụng có phụ thuộc module thật sự, cách diễn đạt source thông thường là:

```java
module m.client {
    requires m.lib;
}
```

Đây là **phương án chỉnh sửa ví dụ để tạo read edge bằng module descriptor**. Nó không còn là bản thử nghiệm “thiếu readability” ở lượt đầu; khi thay `module-info.java`, phải biên dịch lại.

## 7. Bảng quyết định khi debug lỗi qua module

Giữ đúng cấu hình `m.lib` đã dùng trong ví dụ: package `demo.lib` vừa `exports` vô điều kiện, vừa `opens` cho `m.client`, target class và method public ở nhánh `hello`.

| API | `m.client` **không reads** `m.lib` | Có `reads` |
| --- | --- | --- |
| `Module.canRead` | `false` | `true` |
| `target.getMethod("hello").invoke(null)` | Thành công | Thành công |
| `target.getDeclaredMethod("hidden").trySetAccessible()` | `true` | `true` |
| `lookup.findStatic(target, "hello", ...)` với `MethodHandles.lookup()` | `IllegalAccessException` | Thành công |
| `MethodHandles.publicLookup().findStatic(...)` | Thành công | Thành công |
| `MethodHandles.privateLookupIn(target, lookup)` | `IllegalAccessException` | Thành công |

**Đừng ngoại suy bảng này sang cấu hình khác.** Nếu bỏ `exports`, public lookup và Reflection public access có thể thay đổi; nếu bỏ `opens`, deep Reflection và private lookup bị giới hạn. Nếu module library không được resolve, `Class.forName` có thể thất bại ngay từ đầu. Kết quả bảng phụ thuộc đúng những điều kiện đã được nêu.

Cách chẩn đoán ở runtime khi có tham chiếu `Class<?>`:

```java
Module from = Main.class.getModule();
Module to = target.getModule();
String packageName = target.getPackageName();

System.out.println("reads=" + from.canRead(to));
System.out.println("exportedToClient=" + to.isExported(packageName, from));
System.out.println("openedToClient=" + to.isOpen(packageName, from));
```

Đây là **đoạn minh họa trong ngữ cảnh `Main`**, dùng `target` từ chương trình đã có, không phải một chương trình chạy độc lập. `isExported(..., from)` và `isOpen(..., from)` có thể trả `true` do export/open vô điều kiện hoặc do qualified directive áp dụng cho caller. Chúng không tự tạo readability.

## 8. Những khác biệt dễ bị bỏ qua

### 8.1. `exports` không thay `requires`, `opens` không thay `--add-reads`

- `requires m.lib` ở `module m.client` cung cấp read edge theo module descriptor.
- `--add-reads m.client=m.lib` cung cấp read edge bổ sung lúc chạy, hữu ích cho chẩn đoán hoặc tích hợp cần điều chỉnh.
- `exports demo.lib` mở public API của package cho mọi module, nhưng không bắt một module bất kỳ phải đọc `m.lib`.
- `opens demo.lib to m.client` cho deep reflection có kiểm soát, không tạo read edge.
- `--add-opens m.lib/demo.lib=m.client` là điều chỉnh openness lúc chạy; **không** tự giải quyết điều kiện `reads` của `privateLookupIn`.
- `--add-exports m.lib/demo.lib=m.client` điều chỉnh export tại runtime; **không** tự tạo read edge.

Để `privateLookupIn` thành công từ một named module khác, hãy kiểm tra **readability + opens + lookup privileges** theo đúng thứ tự, thay vì chỉ thêm một trong các flags.

### 8.2. `publicLookup()` không phải “root lookup”

`publicLookup()` có ít quyền, mặc dù vượt qua phép kiểm tra readability ở mức `UNCONDITIONAL`. Nó chỉ chấp nhận public types/members thuộc package **export vô điều kiện**. `MethodHandles.lookup()` có thể có nhiều quyền hơn trong chính module của caller, nhưng khi qua module khác thì phải xét quan hệ đọc.

Một qualified export như `exports demo.lib to m.client;` có thể cho `m.client` dùng public API thông qua lookup phù hợp **khi có read edge**; nhưng `publicLookup()` không đại diện cho `m.client` để hưởng một quyền export chỉ dành cho `m.client`.

### 8.3. `Lookup.in(...)` không phải cách “dịch chuyển để lấy quyền”

Ví dụ:

```java
MethodHandles.Lookup relocated = MethodHandles.lookup().in(targetClass);
```

Đoạn này chỉ là minh họa sử dụng `targetClass` đã có. Nó không thể tăng quyền vượt capability gốc; đổi lookup class có thể loại bỏ các lookup modes. Khi lookup được chuyển qua module, `previousLookupClass()` có thể tham gia kiểm tra phạm vi được phép. Một lookup đã đi qua module khác không thể được tự động dùng làm “vé đi tiếp” để lấy private access của module thứ ba.

### 8.4. `unreflect` có quy tắc riêng đối với reflected object đã accessible

`Lookup.unreflect(Method)` và các API `unreflect*` nhận `Method`, `Field` hoặc `Constructor` đã được tạo bằng Core Reflection. Theo đặc tả Java SE 17, **nếu accessible flag của reflected object chưa được bật**, API `unreflect` thực hiện access check ngay theo lookup class. Khi flag đã được bật hợp lệ, một số API `unreflect*` có thể dựa trên quyền đã được cấp cho reflected object.

Điều đó có nghĩa không được kết luận mọi `unreflect*` hoạt động giống hệt `findStatic` hoặc `privateLookupIn`. Ví dụ ở mục 6 cố ý dùng `findStatic` để kiểm tra sự khác biệt về readability mà không bị trộn lẫn với accessible flag. Riêng `unreflectVarHandle` luôn thực hiện access check theo lookup class bất kể accessible flag của `Field`.

### 8.5. Lookup thất bại khi tạo, không phải mọi lần gọi handle

`MethodHandles.Lookup.findStatic` có thể ném `IllegalAccessException` **ngay lúc tìm/khởi tạo handle**. Nếu tạo handle thành công, việc gọi `handle.invokeExact()` không lặp lại cùng một access check cho từng caller. Ngược lại, `Method.invoke` thực hiện access checks khi phương thức được invoke, trừ trường hợp quyền đã được suppress hợp lệ.

Sự khác biệt thời điểm kiểm tra có ý nghĩa khi thiết kế framework cache các method handle. Một `MethodHandle` có quyền truy cập là một capability cần được giữ và chia sẻ có kiểm soát; đừng chuyển full-privilege `Lookup` cho thành phần không tin cậy.

## 9. Sai lầm thường gặp và cách xử lý

| Hiểu nhầm / lỗi | Vì sao sai | Cách kiểm tra |
| --- | --- | --- |
| “Không `requires` thì Reflection chắc chắn lỗi” | Access checks của Core Reflection giả định readability | In `Module.canRead`, rồi phân biệt lỗi `exports`/`opens` |
| “Reflection gọi được nên `lookup.findStatic` cũng gọi được” | Lookup thông thường vẫn áp dụng module readability | Kiểm tra read edge và lookup modes |
| “`opens` đã đủ cho `privateLookupIn`” | Cross-module `privateLookupIn` còn yêu cầu **reads** | `from.canRead(to)` và `to.isOpen(pkg, from)` |
| “`publicLookup` kiểm tra reads y hệt `lookup()`” | `UNCONDITIONAL` giả định readability | Kiểm tra package có **unqualified export** và public API |
| “`publicLookup` có thể gọi private method đã mở package” | `UNCONDITIONAL` không có `PRIVATE`/`MODULE` modes | Dùng `privateLookupIn` với lookup có quyền phù hợp |
| “`Class.forName` thành công thì module đã readable” | Class loading/discovery và module access checks là khác nhau | So `Class.forName` với `Module.canRead` |
| “`getDeclaredMethod` tìm thấy là chắc chắn invoke được” | Metadata discovery không đồng nghĩa quyền invoke | Thử `canAccess`, `trySetAccessible` phù hợp và xử lý lỗi |
| “`--add-opens` sửa được mọi `IllegalAccessException`” | Nó không tự thêm read edge hoặc quyền lookup mode | Chẩn đoán riêng `reads`, `exports`, `opens`, lookup modes |
| “Một `Lookup` được chuyển module có thể tăng quyền” | Các lookup modes có thể bị giảm, previous lookup class bị xét | `lookupClass()`, `previousLookupClass()`, `lookupModes()` |

Khi gặp exception, chú ý nơi lỗi phát sinh:

- `ClassNotFoundException`: có thể class/module chưa được resolve hoặc class loader không tìm thấy class.
- `NoSuchMethodException`/`NoSuchFieldException`: member không tồn tại theo tên/chữ ký được tìm.
- `IllegalAccessException` từ `Lookup.find*` hoặc `privateLookupIn`: có thể thiếu reads, thiếu exports/opens, sai Java visibility hoặc lookup privileges.
- `InaccessibleObjectException` từ `setAccessible(true)`: package/module không cho phép suppress access checks.
- `InvocationTargetException` từ `Method.invoke`: bản thân method được invoke ném exception; đây là lỗi khác với lookup permission.
- `WrongMethodTypeException` hoặc lỗi kiểu khi `invokeExact`: signature của invocation không khớp với `MethodType` của handle; không phải bằng chứng thiếu readability.

Không nên mặc định mọi `IllegalAccessException` đều do một nguyên nhân duy nhất. Thực tế phải xem module graph, khai báo module và kiểu lookup cụ thể.

## 10. Quy trình chẩn đoán một lỗi access trên Java 17+

1. **Xác định hai module**: caller module và target module. Xác định class khai báo member, package, `public`/`private` và API thực sự được dùng.
2. **Kiểm tra module resolution và class loader**: target `Class<?>` đã thực sự được nạp chưa? Nếu chưa, xử lý bước này trước.
3. **In `canRead`** để biết caller có read edge không. Đừng suy ra quan hệ này từ việc Reflection thành công.
4. **Kiểm tra `exports` và `opens`**: public access thường cần export phù hợp; deep reflection/private lookup cần openness khi qua module khác.
5. **Phân loại lời gọi**:
   - Core Reflection: readability được giả định trong access check của reflected object; vẫn kiểm tra visibility, exports/opens.
   - `lookup().find*`: kiểm tra readability theo lookup context.
   - `publicLookup().find*`: `UNCONDITIONAL`, chỉ public API export vô điều kiện.
   - `privateLookupIn`: khi khác module phải có `reads` + `opens` + `PRIVATE`/`MODULE` modes.
6. **Xem thời điểm ném lỗi**: khi tìm member, khi tạo method handle, khi bật `accessible`, hay khi invoke thật. Phân biệt lỗi access với lỗi method body.
7. **Sửa theo đúng hợp đồng**: bổ sung `requires` trong module descriptor khi có phụ thuộc thật; cung cấp `exports`/`opens` phù hợp khi cần; chỉ dùng runtime flags `--add-reads`/`--add-opens`/`--add-exports` khi mục tiêu triển khai yêu cầu và có kiểm soát.

### Câu hỏi tự kiểm tra

1. `m.client` không reads `m.lib`, nhưng `m.lib` exports một public package. Core Reflection trên public method có thể thành công không? **Có**, nếu class/member access và điều kiện khác đều thỏa.
2. Nếu `m.client` không reads `m.lib`, còn package đã opens cho `m.client`, `privateLookupIn` qua module có luôn thành công không? **Không**, vẫn cần reads và lookup privileges.
3. `publicLookup()` có thật sự bỏ qua readability không? **Có theo `UNCONDITIONAL`**, nhưng chỉ với public API export vô điều kiện.
4. `--add-opens` có giống `--add-reads` không? **Không**. Một cái mở quyền deep reflection, cái kia tạo quan hệ đọc.
5. Khi gọi `lookup.findStatic(...)`, kiểm tra quyền xảy ra lúc nào? **Khi tạo handle**; handle được tạo hợp lệ có thể được gọi lại mà không kiểm tra truy cập theo caller mỗi lần.
6. `getDeclaredMethod(...)` tìm được private method có chứng minh `setAccessible(true)` sẽ thành công không? **Không**; JPMS có thể chặn.
7. Tại sao thí nghiệm dùng hai named modules? **Để mô tả rõ read edge bị thiếu**; unnamed module trên classpath có quy tắc readability đặc biệt.
8. `publicLookup()` có giúp gọi public member trong package chỉ `exports p to m.client` không? **Không chỉ dựa trên qualified export đó**, vì lookup `UNCONDITIONAL` đòi unqualified export.

## 11. Tài liệu chuẩn để đối chiếu

- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): quy tắc **assume readability** và `setAccessible`/`trySetAccessible`.
- [Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, và điều kiện của `privateLookupIn`.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): module access checks, `UNCONDITIONAL`, `Lookup.in`, các factory/unreflect methods.
- [Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, `addReads` và module graph.

**Nguyên tắc kết luận:** khi so sánh quyền truy cập trên Java module, hãy hỏi đồng thời **“module có được resolve không?”, “caller có reads không?”, “package có exports/opens không?”, “cơ chế gọi dùng Reflection, regular Lookup, public Lookup hay private lookup?”**. Chỉ khi trả lời đủ bốn câu hỏi này mới giải thích chính xác vì sao cùng một method có thể được gọi bằng Core Reflection nhưng bị `MethodHandles.lookup()` từ chối.