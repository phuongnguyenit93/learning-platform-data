# Kiểm thử quyền `MethodHandles.Lookup` trong cùng mô-đun và qua mô-đun khác

> **Ngữ cảnh:** Java 14 → **Quyền Lookup** → *Kiểm thử quyền trong cùng mô-đun và qua mô-đun khác*. Bài này giải thích cơ chế kiểm tra quyền của `java.lang.invoke.MethodHandles.Lookup` trong **Java Platform Module System (JPMS)**, dùng các API và quy tắc **còn hiệu lực với JDK 17+**. JPMS và `privateLookupIn` không phải tính năng mới của Java 14; chúng đã tồn tại từ Java 9 và tiếp tục là nền tảng cho Java hiện đại. Kể từ Java 17, cơ chế đóng gói mạnh (*strong encapsulation*) càng khiến việc phân biệt `exports` với `opens` trở nên quan trọng. Không dựa vào `--illegal-access`, `sun.misc.Unsafe` hoặc các cơ chế legacy để vượt quyền.

## 1. Bài toán thực tế

Một thư viện có hai package trong cùng một **named module**:

- `demo.api`: API công khai được khai báo `exports` cho mô-đun sử dụng.
- `demo.internal`: triển khai nội bộ có phương thức `private`, không được xuất ra.

Ta cần kiểm thử ba câu hỏi **khác nhau**:

1. Một class ở `demo.internal` có thể tạo `Lookup` để truy cập thành viên `private` của class khác trong **cùng module** không?
2. Một module `client.check` đọc module `library.core` có thể gọi **API public đã export** không?
3. Module `client.check` có thể dùng `privateLookupIn` để truy cập thành viên `private` trong `demo.internal` không, và khi nào được phép?

Kết quả cần học: **Cùng module** có thể tạo một lookup riêng với quyền thích hợp để truy cập private của target dù target ở package khác, trong khi **khác module** còn yêu cầu quan hệ `reads` và target module **`opens` package chứa target** cho caller module. Chỉ có `exports` chưa đủ cho **private access**.

~~~text
                   MODULE library.core
            +-------------------------------+
            |  demo.api                     |
            |    LibraryApi                 |
            |     public visible()          |
            |                               |
            |  demo.internal                |
            |    Secret                     |
            |     private answer()          |
            |    SameModuleProbe            |
            |     privateLookupIn(Secret)   |
            +---------------+---------------+
                            |
                    requires / reads
                            |
                   MODULE client.check
            +---------------+---------------+
            | CrossModuleProbe              |
            | - gọi LibraryApi.visible()    |
            | - thử privateLookupIn(Secret) |
            +-------------------------------+

Chưa opens demo.internal to client.check:
    public API xuất ra:       ĐƯỢC
    private trong same module: ĐƯỢC (với privateLookupIn)
    private từ other module:  BỊ TỪ CHỐI
~~~

Đây là **kiểm thử ranh giới quyền**, không phải đề xuất cho code sản xuất cố tình đọc dữ liệu mật của thư viện. Trong sản phẩm thật, ưu tiên API được thư viện **chủ động công khai**, chỉ dùng deep reflection khi thật sự cần và có hợp đồng rõ ràng.

## 2. `Lookup` là một capability, không phải “reflection được cấp toàn quyền”

`MethodHandles.Lookup` là đối tượng dùng để tạo **`MethodHandle` hoặc `VarHandle`** với kiểm tra quyền ở **thời điểm tạo handle**. Khi có handle hợp lệ, việc gọi handle **không thực hiện lại đầy đủ kiểm tra quyền thành viên** ở mỗi lần invoke; vì thế không nên vô tình đưa một lookup có quyền cao hoặc một private handle cho code không đáng tin.

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandle;

// Đoạn trong method, giả định Target là class có thể truy cập.
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findStatic(
        Target.class, "hello", MethodType.methodType(String.class));
~~~

Đây là đoạn **minh họa không độc lập** (phải có `Target`), dùng để giới thiệu ba API:

- `MethodHandles.lookup()`: tạo `Lookup` với quyền ứng với **class thực sự gọi `lookup()`**; nó là *caller-sensitive*, không tự nhận quyền của nơi sau đó truyền đối tượng `Lookup` tới.
- `lookup.findStatic(refc, name, methodType)`: yêu cầu tìm một phương thức `static` có **tên, kiểu trả về, tham số và quyền phù hợp**.
- `MethodHandles.privateLookupIn(targetClass, callerLookup)`: khi đáp ứng điều kiện quyền, tạo một `Lookup` có **private access trong ngữ cảnh target class**. Đây **không phải** tự động mở package hay bỏ qua JPMS.

### 2.1. Các mức quyền của `Lookup`

| Quyền/mode | Ý nghĩa khái quát |
| --- | --- |
| `PUBLIC` | Truy cập các public members/types mà ngữ cảnh lookup và mô-đun cho phép |
| `MODULE` | Truy cập các public types trong **cùng module**, kể cả package không export, với những điều kiện khác vẫn áp dụng |
| `PACKAGE` | Truy cập các thành viên theo mức package của **runtime package** phù hợp |
| `PRIVATE` | Truy cập private theo quyền phù hợp của lookup class/nest; cần khi xin private lookup |
| `PROTECTED` | Quyền đối với protected members theo quy tắc Java tương ứng |
| `ORIGINAL` | Mode chỉ thị lookup xuất phát trực tiếp từ lời gọi có quyền gốc (JDK hiện đại) |
| `UNCONDITIONAL` | Mode của `publicLookup()`, chỉ cho quyền công khai **tối thiểu** trên package được export vô điều kiện |

**Không suy ra “có bit PRIVATE thì có quyền private của mọi class”.** Lookup gắn với **lookup class**, có thể có **previous lookup class**, và quyền còn phụ thuộc class/package/module đích, đọc module và chính sách export/open. Các mode có thể được kiểm tra bằng `lookup.lookupModes()`, nhưng **bitmask không phải kết luận toàn bộ** về khả năng truy cập class khác.

### 2.2. Tại sao cần `privateLookupIn` dù cùng module?

Hai class **khác nhau** trong cùng module vẫn chịu quy tắc `private`: bình thường một class không thể đọc private member của class khác, trừ quan hệ nestmate/điều kiện Java thích hợp. Cùng **package** cũng không tự được quyền private.

Trong một module, lookup có đủ `MODULE` và `PRIVATE` có thể gọi:

~~~java
var privileged = MethodHandles.privateLookupIn(
        Secret.class, MethodHandles.lookup());

var handle = privileged.findStatic(
        Secret.class,
        "answer",
        MethodType.methodType(String.class));
~~~

Đây là đoạn đặt **trong lớp có quyền phù hợp**, không phải file độc lập. `privateLookupIn` thực hiện kiểm tra capability của caller, sau đó tạo lookup có thể tìm private member của `Secret`. Việc nó thành công **không có nghĩa** rằng cách gọi `MethodHandles.lookup().findStatic(Secret.class,"answer",...)` thông thường từ một class khác cũng thành công.

## 3. JPMS: `requires`, `exports` và `opens` là ba câu hỏi riêng

Các từ khóa trong `module-info.java` giải quyết ba khía cạnh:

| Khai báo | Tác dụng | Không tự cấp |
| --- | --- | --- |
| `requires library.core;` trong `client.check` | `client.check` **reads** `library.core` | Không tự cho phép truy cập package không exported/opened hoặc private |
| `exports demo.api;` trong `library.core` | Cho phép những module đọc nó truy cập **public API** của package `demo.api` | Không cấp private access vào `demo.api` |
| `exports demo.internal to client.check;` | Export **có giới hạn** các public types/members của package cho `client.check` | Không cấp deep private lookup |
| `opens demo.internal to client.check;` | Cho phép **deep reflection tại runtime** từ `client.check` vào package nội bộ | Không biến package thành API import public khi compile |
| `opens demo.internal;` | Mở package cho tất cả modules ở runtime | Không giới hạn được bên nhận; thường rộng hơn cần thiết |
| `open module library.core { ... }` | Mở tất cả package của module cho deep reflection | Rộng, làm suy yếu ranh giới đóng gói nếu không có yêu cầu rõ |

**Quy tắc chính xác của `MethodHandles.privateLookupIn(target, caller)` khi khác module:** giả sử caller ở `M1` và target ở `M2`, cần **đồng thời** có:

1. `caller` có **`MODULE` và `PRIVATE` access** (full privilege theo yêu cầu API).
2. `M1` **reads** `M2`.
3. `M2` **opens package chứa target class** cho `M1`, có thể qua `opens ... to M1`, `opens` không giới hạn hoặc override được cấp rõ.
4. Target là một class hợp lệ; không dùng primitive, void hoặc array làm `targetClass`.

Thiếu một điều kiện, phép xin private lookup **bị từ chối**. Nếu cùng module, yêu cầu `opens` qua ranh giới module không áp dụng; caller vẫn cần capability đầy đủ.

### `exports` khác `opens` trong thực tế

`exports` là **hợp đồng truy cập API công khai**, có ý nghĩa cho compile-time lẫn runtime. `opens` cho phép **runtime deep reflection**, không tự hợp pháp hóa một câu `import demo.internal.Secret;` trong module khác. Ở bài này, chương trình phía client cố ý sử dụng `Class.forName` để lấy `Class<?>` của target ẩn khi không thể import nó trực tiếp.

**Quan trọng:** `Class.forName("demo.internal.Secret")` có thể trả về một `Class<?>` dù package không export. Việc **tải/nhìn thấy lớp** không đồng nghĩa có **quyền tạo private method handle**. Bước `privateLookupIn` tiếp theo vẫn phải kiểm tra đủ điều kiện.

## 4. Bài thực hành hoàn chỉnh: hai named modules

Dưới đây là project nhỏ có thể chạy với **JDK 17+**, không cần Maven/Gradle/JUnit để quan sát các ranh giới quyền. Chọn một thư mục làm việc sạch, tạo **đúng cấu trúc**:

~~~text
lookup-lab/
  src/
    library.core/
      module-info.java
      demo/
        api/
          LibraryApi.java
        internal/
          Secret.java
          SameModuleProbe.java
    client.check/
      module-info.java
      demo/
        client/
          CrossModuleProbe.java
~~~

**Hai module có tên cố định** `library.core` và `client.check`; tên module không nhất thiết phải trùng tên package. Để dùng các lệnh bên dưới, đứng trong thư mục `lookup-lab`.

### 4.1. `src/library.core/module-info.java`

~~~java
module library.core {
    exports demo.api;
    // Chưa opens demo.internal cho client.check.
}
~~~

Chỉ `demo.api` là package public API của `library.core`. Module không export/open `demo.internal` cho bên ngoài trong phép thử đầu.

### 4.2. `src/library.core/demo/internal/Secret.java`

~~~java
package demo.internal;

public final class Secret {
    private static String answer() {
        return "secret-ok";
    }
}
~~~

Class `Secret` tuy khai báo `public` nhưng **package của nó không export** sang module khác. Method `answer()` là `private static`; `private` không bị biến thành public chỉ vì tên class được load qua `Class.forName`. Chuỗi `secret-ok` là giá trị **minh họa**, không phải dữ liệu mật thật.

### 4.3. `src/library.core/demo/internal/SameModuleProbe.java`

~~~java
package demo.internal;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;

public final class SameModuleProbe {
    public static String read() throws Throwable {
        var privileged = MethodHandles.privateLookupIn(
                Secret.class, MethodHandles.lookup());

        MethodHandle mh = privileged.findStatic(
                Secret.class,
                "answer",
                MethodType.methodType(String.class));

        return (String) mh.invokeExact();
    }
}
~~~

- Cả `SameModuleProbe` và `Secret` nằm **trong cùng module `library.core`**.
- `MethodHandles.lookup()` được gọi **bên trong class `SameModuleProbe`**, do đó caller lookup có quyền gốc ở `library.core`.
- `privateLookupIn(Secret.class, caller)` được phép tạo lookup riêng vào `Secret`.
- `mh.invokeExact()` trả về `String` với **signature chính xác** là `()String`. Ép kiểu `(String)` tại call site giúp `invokeExact` có kiểu trả về khớp.
- Phương thức mẫu khai báo `throws Throwable` vì lời gọi `MethodHandle.invokeExact` có thể ném `Throwable`. Trong ứng dụng thực tế nên xử lý ngoại lệ theo hợp đồng, không mặc định mọi exception là lỗi quyền.

Dù hai class cùng package trong ví dụ, **cơ chế same-module còn áp dụng khi hai class thuộc hai package khác nhau của cùng module**, nếu caller có đầy đủ `MODULE` và `PRIVATE`. Nên giữ quyền truy cập private tập trung ở nơi được kiểm soát, không rải `privateLookupIn` tùy tiện.

### 4.4. `src/library.core/demo/api/LibraryApi.java`

~~~java
package demo.api;

public final class LibraryApi {
    public static String visible() {
        return "public-ok";
    }

    public static String sameModule() throws Throwable {
        return demo.internal.SameModuleProbe.read();
    }
}
~~~

`LibraryApi.visible()` thể hiện public API mà client có thể gọi. `sameModule()` **chỉ là cầu nối phục vụ bài kiểm thử** để quan sát phép private lookup diễn ra bên trong `library.core`. Nó **chủ động trả lại** một giá trị minh họa; trong hệ thống thật, không dùng thiết kế này để tiết lộ secrets hoặc nội bộ chỉ vì private lookup có thể tạo được.

### 4.5. `src/client.check/module-info.java`

~~~java
module client.check {
    requires library.core;
}
~~~

`requires` cho phép `client.check` đọc module `library.core`. Đây là điều kiện quan trọng cho cả public API call và cross-module `privateLookupIn`. Nó **không tự mở** package `demo.internal`.

### 4.6. `src/client.check/demo/client/CrossModuleProbe.java`

~~~java
package demo.client;

import demo.api.LibraryApi;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;

public final class CrossModuleProbe {
    public static void main(String[] args) throws Throwable {
        // (1) Public API trong package đã export.
        System.out.println("public=" + LibraryApi.visible());

        // (2) Private lookup thực hiện BÊN TRONG library.core.
        System.out.println(
                "sameModule=" + LibraryApi.sameModule());

        // (3) Client dùng tên để tìm lớp ở package không export.
        Class<?> target = Class.forName(
                "demo.internal.Secret");

        try {
            // Caller ở client.check, target ở library.core.
            var privileged = MethodHandles.privateLookupIn(
                    target, MethodHandles.lookup());

            MethodHandle mh = privileged.findStatic(
                    target,
                    "answer",
                    MethodType.methodType(String.class));

            System.out.println(
                    "crossModule=" + (String) mh.invokeExact());

        } catch (IllegalAccessException ex) {
            // Chỉ bắt lỗi quyền dự kiến; không che các lỗi khác.
            System.out.println("crossModule=DENIED");
        }
    }
}
~~~

Vì package target chưa `opens`, `privateLookupIn` từ `client.check` sẽ ném **`IllegalAccessException`** ở phép thử đầu. Chương trình **không đoán hay in toàn bộ exception message** vì thông báo có thể thay đổi giữa phiên bản JDK; chỉ khẳng định loại kết quả dự kiến.

## 5. Biên dịch và chạy phép thử âm tính: chưa mở package

Từ thư mục `lookup-lab`, chạy các lệnh sau với **JDK 17+**. Các lệnh một dòng dùng được trong **Bash và PowerShell** khi `java`/`javac` đã ở `PATH`:

~~~bash
javac --release 17 --module-source-path src -d mods -m library.core,client.check

java --module-path mods -m client.check/demo.client.CrossModuleProbe
~~~

**Stdout chính xác đã kiểm chứng trên JDK 21:**

~~~text
public=public-ok
sameModule=secret-ok
crossModule=DENIED
~~~

Giải thích **từng dòng**:

| Dòng | Đường gọi | Kết luận |
| --- | --- | --- |
| `public=public-ok` | `client.check` gọi `LibraryApi.visible()` trong package `demo.api` có `exports` | Public contract hoạt động |
| `sameModule=secret-ok` | `LibraryApi` gọi `SameModuleProbe.read()`; lookup private được tạo **trong `library.core`** | Same-module private lookup thành công |
| `crossModule=DENIED` | `client.check` gọi `privateLookupIn` cho `Secret` nằm trong `demo.internal` chưa `opens` | Cross-module private lookup bị chặn |

Đây là **negative test thành công**, không phải build thất bại. Lỗi bị **bắt có chủ đích và khẳng định chính xác**; JDK đang bảo vệ encapsulation như mong đợi.

### Vì sao cả cùng-module và khác-module không mâu thuẫn?

Ở `SameModuleProbe`, `Lookup` do **class thuộc `library.core`** tạo ra và target cũng ở module đó. Ở `CrossModuleProbe`, `Lookup` do **class thuộc `client.check`** tạo ra, còn target ở module khác. Quyền **không đi theo thread** cũng không đi theo “ai là người gọi method cuối cùng” một cách tùy ý: identity của lookup gắn với **lớp được JVM xác định khi tạo capability**.

Nếu bạn truyền một `Lookup` đầy đủ từ thư viện sang client rồi để client sử dụng, **đó có thể trở thành việc ủy quyền capability nguy hiểm**. Không xuất public factory trả `MethodHandles.lookup()` hoặc private lookup/handle trừ khi thiết kế API đã chủ động cho phép hành vi ấy.

## 6. Phép thử dương tính: mở đúng package cho đúng module

### 6.1. Cách ưu tiên khi bạn kiểm soát mã nguồn thư viện

Thay nội dung `src/library.core/module-info.java` bằng:

~~~java
module library.core {
    exports demo.api;
    opens demo.internal to client.check;
}
~~~

`opens demo.internal to client.check;` là **qualified open**: mở đúng package nội bộ cho **một mô-đun được chỉ định**, chứ không mở tất cả package hoặc mọi mô-đun.

Biên dịch lại các module và chạy:

~~~bash
javac --release 17 --module-source-path src -d mods -m library.core,client.check
java --module-path mods -m client.check/demo.client.CrossModuleProbe
~~~

**Stdout:**

~~~text
public=public-ok
sameModule=secret-ok
crossModule=secret-ok
~~~

Điểm khác duy nhất về cơ chế quyền: `library.core` đã chủ động cho phép `client.check` **deep reflection** vào `demo.internal`. `requires library.core;` vẫn cần có trong module sử dụng; riêng `opens` không thay thế module readability.

### 6.2. Phép thử bằng launcher override khi không muốn chỉnh descriptor

Giữ lại `module-info.java` ban đầu **không có `opens`** (hoặc biên dịch lại từ descriptor ban đầu), sau đó chạy:

~~~bash
java --add-opens library.core/demo.internal=client.check --module-path mods -m client.check/demo.client.CrossModuleProbe
~~~

**Stdout kỳ vọng và đã kiểm chứng:**

~~~text
public=public-ok
sameModule=secret-ok
crossModule=secret-ok
~~~

`--add-opens library.core/demo.internal=client.check` mở **đúng package** cho **đúng module** tại runtime của lần chạy. Nó là công cụ chẩn đoán/triển khai có chủ đích, không phải biện pháp tự động “cấp mọi quyền”. Trong test integration có thể dùng để chứng minh **nguyên nhân bị từ chối là module openness**.

**Khuyến nghị:** khi sở hữu mã nguồn của thư viện và có nhu cầu sâu hợp lệ, cấu hình `opens package to trusted.module` trong descriptor thường dễ kiểm soát hơn so với cài `--add-opens` rộng cho mọi môi trường. Nếu nhu cầu là gọi chức năng bình thường, ưu tiên bổ sung hoặc sử dụng **API public ổn định** thay vì mở nội bộ.

### 6.3. Tại sao `exports` đơn thuần chưa đủ?

Nếu đổi descriptor thành:

~~~java
module library.core {
    exports demo.api;
    exports demo.internal to client.check;
}
~~~

thì `client.check` có thêm quyền đối với **public classes/public members** trong `demo.internal`, nhưng **`privateLookupIn` vào `Secret.answer()` vẫn bị từ chối** khi package chưa `opens`. Trên JDK 21, biến thể `exports`-only của chương trình vẫn in:

~~~text
public=public-ok
sameModule=secret-ok
crossModule=DENIED
~~~

**Không đồng nhất** “đã export” với “đã mở cho deep reflection”. Tương tự, `opens`-only **không tự cho phép câu `import demo.internal.Secret;` ở mã nguồn client được biên dịch** khi package không export. Hai từ khóa giải quyết **hai bề mặt truy cập khác nhau**.

## 7. Ma trận kiểm thử quyền tối thiểu

Với các file source trên, giữ nguyên `requires library.core` trong `client.check` rồi thay **duy nhất descriptor của `library.core`**.

| Cấu hình của `library.core` đối với `demo.internal` | Public API `demo.api` từ client | `privateLookupIn` trong cùng module | `privateLookupIn` từ `client.check` |
| --- | --- | --- | --- |
| Không `exports`/`opens` package internal | PASS | PASS | **DENIED** |
| `exports demo.internal to client.check;` | PASS | PASS | **DENIED** |
| `opens demo.internal to client.check;` | PASS | PASS | **PASS** |
| `exports` và `opens` internal cho client | PASS | PASS | **PASS** |

Cần tách loại test:

- **Compile-time public API:** có thể import và gọi `demo.api.LibraryApi` nhờ `exports demo.api;`.
- **Runtime same-module private:** `SameModuleProbe` tạo private lookup; không cần thư viện tự mở package cho module khác.
- **Runtime cross-module private:** kiểm tra thêm `reads` và `opens`, bảo đảm positive/negative.
- **Negative compile test:** thử import `demo.internal.Secret` khi package chỉ `opens` nhưng không `exports`; việc import không được phép chứng minh `opens` không biến thành public compile-time API.
- **Negative runtime test:** giữ `exports` internal nhưng bỏ `opens`; public access và private access phải được phân biệt.

**Không cần cho test thật gọi dữ liệu bảo mật.** Thay thành viên private bằng một marker tĩnh vô hại như `"secret-ok"`, đảm bảo test không tiết lộ secrets.

## 8. Kiểm chứng có chủ đích bằng `Module` và `Lookup` API

Khi bài kiểm thử ngoài đời gặp `IllegalAccessException`, trước khi thêm bất kỳ option mở quyền nào, hãy **đọc trạng thái** hiện tại.

### 8.1. Từ bên trong `CrossModuleProbe.main`

~~~java
// Đoạn minh họa đặt sau khi đã có Class<?> target.
Module callerModule = CrossModuleProbe.class.getModule();
Module targetModule = target.getModule();

System.out.println(
        "reads=" + callerModule.canRead(targetModule));
System.out.println(
        "opens=" + targetModule.isOpen(
                "demo.internal", callerModule));
System.out.println(
        "exports=" + targetModule.isExported(
                "demo.internal", callerModule));
~~~

Với descriptor ban đầu, kết quả đáng mong đợi:

~~~text
reads=true
opens=false
exports=false
~~~

Khi chỉ thêm `opens demo.internal to client.check;` thì `opens=true` **và** `exports=true` tại runtime theo overload `Module.isExported(String, Module)`: package được mở cho caller cũng được xem là exported cho caller trong phép kiểm tra runtime này. Tuy nhiên `opens` **không thay thế** khai báo `exports` trong `module-info.java`, nên module khác vẫn **không thể** `import demo.internal.*` khi biên dịch nếu chỉ có `opens`. Vì vậy phải phân biệt tính hiển thị tại compile-time với trạng thái xuất/mở package ở runtime. Khi chỉ thêm `exports demo.internal to client.check;` thì `exports=true`, còn `opens=false`. Những giá trị này giúp khoanh vùng **thiếu reads** hay **thiếu opens** thay vì thử ngẫu nhiên các JVM flags.

Trong quy trình thực tế, `Module.isOpen` và `isExported` phản ánh trạng thái runtime, bao gồm những thay đổi có chủ đích qua launcher/module APIs. Chúng **không thay thế** việc thử `privateLookupIn` thực sự.

### 8.2. Nhìn vào quyền của lookup

~~~java
MethodHandles.Lookup caller = MethodHandles.lookup();

boolean hasPrivate =
        (caller.lookupModes()
                & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule =
        (caller.lookupModes()
                & MethodHandles.Lookup.MODULE) != 0;

System.out.println("privateMode=" + hasPrivate);
System.out.println("moduleMode=" + hasModule);
~~~

Đây là đoạn trong một method. `lookupModes()` trả các bit mode; trên một lookup gốc thông thường ở class ứng dụng đang gọi `MethodHandles.lookup()`, hai điều kiện trên là true. **Hai bit đó chưa đủ** để truy cập private một module khác: vẫn cần `reads` và `opens`.

JDK hiện đại còn có `hasFullPrivilegeAccess()`. Dùng phương thức này để kiểm tra capability nếu phù hợp, nhưng không đánh đồng “full privilege lookup hiện tại” với “tự động có quyền private của bất cứ target nào”.

### 8.3. Không dùng `publicLookup()` để xin quyền private

~~~java
// Đoạn trong method; target là Class<?> đã tìm được.
try {
    MethodHandles.privateLookupIn(
            target, MethodHandles.publicLookup());
} catch (IllegalAccessException expected) {
    System.out.println("publicLookup=DENIED");
}
~~~

`publicLookup()` chỉ mang quyền public bị giới hạn (với `UNCONDITIONAL`), không có `MODULE` và `PRIVATE`. Nó không thể là caller đủ quyền của `privateLookupIn`, **ngay cả khi package đã opens**. Do đó không thể thay `MethodHandles.lookup()` bằng `publicLookup()` chỉ để “sửa” một lỗi access.

### 8.4. `Lookup.in(...)` và `dropLookupMode(...)` không nâng quyền

- `lookup.in(Target.class)` chuyển *lookup class* theo quy tắc và có thể **mất** quyền `PRIVATE`/`PACKAGE`/`MODULE`, đặc biệt khi đi qua package hoặc module khác. Nó **không** tự nâng quyền lên private target.
- `lookup.dropLookupMode(MethodHandles.Lookup.PRIVATE)` chủ động giảm quyền; sau đó không còn là caller có đầy đủ `PRIVATE` để dùng `privateLookupIn`.
- `lookup.dropLookupMode(MethodHandles.Lookup.MODULE)` làm mất nhiều capability phụ thuộc module, không chỉ một bit độc lập.
- `privateLookupIn` từ module `M1` tới `M2` trả lookup có `PRIVATE` cho target **nhưng không còn `MODULE`**; không thể dùng tiếp đối tượng ấy để xin private lookup khác bằng `privateLookupIn` như thể nó là lookup toàn quyền mới.

**Nguyên tắc capability:** Java cung cấp thao tác *giảm* quyền và ủy quyền có điều kiện, không cho phép một lookup yếu tự biến thành lookup mạnh chỉ bằng cách đổi tên lookup class.

## 9. Chẩn đoán lỗi: quyền hay lỗi tên/phương thức?

Mọi lỗi trong chuỗi `findStatic → invokeExact` **không phải** đều là lỗi module.

| Lỗi/hiện tượng | Nguyên nhân hay gặp | Kiểm tra |
| --- | --- | --- |
| `IllegalAccessException` tại `privateLookupIn` | Caller thiếu `MODULE`/`PRIVATE`, M1 không đọc M2, hoặc package target chưa `opens` | `lookupModes`, `Module.canRead`, `Module.isOpen` |
| `IllegalAccessException` tại `findStatic` | Lookup không được phép truy cập class/member theo context | Kiểm tra class/public/private/package và quyền lookup đang dùng |
| `NoSuchMethodException` | Sai tên, `static`/instance, parameter types hoặc return type trong `MethodType` | So sánh signature chính xác, không đổi module opens tùy tiện |
| `ClassNotFoundException` tại `Class.forName` | Sai tên lớp, module/path/loader không có target | Kiểm tra module path, module graph và class name |
| `WrongMethodTypeException` tại `invokeExact` | Kiểu call site không đúng **chính xác** `MethodHandle.type()` | Dùng đúng cast/`MethodType` hoặc `invoke` có chuyển đổi được phép |
| `IllegalArgumentException` tại `privateLookupIn` | `targetClass` là primitive/void/array, hoặc đối số không hợp lệ theo API | Chọn target class đúng loại |
| Compile `package ... is not visible` | Target package chưa export cho module biên dịch | Dùng API public/export hoặc đừng import package nội bộ |
| Test khác kết quả giữa chạy classpath/module-path | Một lần chạy trong unnamed module, lần khác trong named modules | Dùng `--module-path` và `-m` nhất quán |

**Trong chương trình mẫu chỉ bắt `IllegalAccessException`** ở cross-module private lookup. Nếu viết `catch (Exception ignored) { System.out.println("DENIED"); }`, bạn có thể đánh dấu PASS sai khi file/module bị thiếu, signature nhầm hoặc lỗi nghiệp vụ. Một negative test tốt phải **chỉ chấp nhận đúng loại lỗi dự kiến**, còn lỗi khác nên làm test fail.

### Test riêng trong cùng module

Nếu bạn cố dùng:

~~~java
// Đoạn trong SameModuleProbe, không phải phần của file chạy.
MethodHandles.lookup().findStatic(
        Secret.class, "answer",
        MethodType.methodType(String.class));
~~~

thì bạn đang xin private method của class **khác** bằng lookup gốc của `SameModuleProbe`. Không nên mặc định lệnh này được phép chỉ vì hai class cùng package/module. Dùng `privateLookupIn(Secret.class, ...)` như chương trình hoàn chỉnh để thể hiện rõ ranh giới private access.

### Trường hợp “khác package nhưng cùng module”

Trong JPMS, **module boundary và package boundary độc lập**. Các class thuộc các package khác nhau nhưng nằm trong `library.core` vẫn được phép truy cập **public types của cùng module** theo mode `MODULE`, không cần `exports` nội bộ. Khi cần **private member** của class khác, dùng `privateLookupIn` từ lookup đầy đủ; đừng nhầm với quyền private trực tiếp của mọi class trong module.

## 10. Strong encapsulation của JDK hiện đại

Từ **JDK 17**, các nội bộ JDK được đóng gói mạnh theo **JEP 403**. Việc cố truy cập internal packages của JDK bằng reflection/MethodHandles **không được phép mặc định** chỉ vì ứng dụng từng chạy được trên JDK cũ.

- `--illegal-access` là **tùy chọn lỗi thời**: Java 17+ không dùng nó như cách mở quyền. Không đưa vào quy trình kiểm thử hiện đại.
- `--add-exports module/package=target` cấp khả năng dùng **public types/members** theo phạm vi quy định; **không** phải thay cho `opens` nếu mục tiêu là deep reflection vào private.
- `--add-opens module/package=target` mở **runtime reflective access** cho target. Chỉ sử dụng phạm vi tối thiểu và có tài liệu hóa; không mở hàng loạt `java.base/*` để che lỗi thiết kế.
- `setAccessible(true)` từ reflection API cũng không tự bỏ qua ranh giới module; khi bị chặn có thể ném `InaccessibleObjectException`. Với `MethodHandles.privateLookupIn`, trường hợp không đủ quyền được báo bằng **`IllegalAccessException`**.
- Nếu một framework/library cần truy cập private fields của module bạn sở hữu, cân nhắc cung cấp **qualified opens** riêng cho framework; nếu nhu cầu có thể giải quyết bằng public API, không nên mở internal package.

**Điều khoản bảo mật:** Tạo private lookup cho module khác là **ủy quyền sâu**. Javadoc lưu ý lookup ấy có khả năng định nghĩa class trong runtime package của target theo một số cơ chế, do vậy package `opens` cho module khác phải được cân nhắc như một quyết định cấp quyền, không chỉ mẹo để test qua.

## 11. Kế hoạch test tự động cho CI

Để tránh kiểm thử thủ công chỉ nhìn console, hãy tổ chức test thành **hai cấu hình được kiểm soát**:

**Case A — DENY theo mặc định**

- Descriptor của `library.core` chỉ có `exports demo.api;`.
- Biên dịch hai module trên `--module-source-path`.
- Chạy `client.check/demo.client.CrossModuleProbe` **không** có `--add-opens`.
- Assert mã thoát bằng 0 **và** stdout đúng ba dòng:
  `public=public-ok`, `sameModule=secret-ok`, `crossModule=DENIED`.
- Không bắt lỗi rộng khiến test vô tình báo PASS.

**Case B — ALLOW có chủ đích**

- Giữ nguồn ứng dụng không đổi; thêm `opens demo.internal to client.check;` trong descriptor **hoặc** dùng đúng `--add-opens` ở lệnh chạy.
- Biên dịch lại nếu thay descriptor; với launcher override thì không cần sửa source.
- Assert mã thoát bằng 0 **và** `crossModule=secret-ok`.
- Nếu kết quả vẫn DENIED, dùng `Module.canRead`/`isOpen` và ngoại lệ gốc để phân tích, đừng thêm một `opens ...` rộng hơn ngay.

**Case C — chỉ EXPORT không OPEN**

- Thử `exports demo.internal to client.check;` nhưng **không** `opens`.
- Assert client vẫn **không** tạo private lookup để gọi `Secret.answer()`.
- Dùng case này để phòng ngừa regression khi ai đó nhầm exports với opens.

**Case D — caller capability bị suy giảm**

- Gọi `privateLookupIn(target, MethodHandles.publicLookup())` hoặc truyền lookup đã `dropLookupMode(PRIVATE)`.
- Dù target mở package, API vẫn không cho private lookup vì caller thiếu capability.
- Bắt đúng `IllegalAccessException` và kiểm tra không có quyền private được cấp ngoài ý muốn.

### Những nguyên tắc làm test ổn định

1. **Không assert nguyên văn exception message**: thông báo access có thể đổi giữa JDK 17/21/25; assert loại ngoại lệ và kết quả quyền.
2. **Không chạy vô tình trên classpath**: named-module boundaries cần `module-info.java`, `--module-path` và `-m`.
3. **Không đặt thử nghiệm này trong cùng module với target** nếu bạn muốn kiểm tra cross-module DENY; nếu không, phép thử có thể PASS vì cùng module mà bạn không nhận ra.
4. **Không đặt `opens` quá rộng trong cấu hình baseline**: phải có case negative thực sự.
5. **Không chia sẻ lookup đặc quyền** từ thư viện vào test client một cách vô ý: như vậy test đo quyền được ủy quyền, không đo quyền gốc của client.
6. **Mỗi case cần môi trường cách ly**: nếu thêm `--add-opens` bằng launcher trong một case, đừng để flags đó tự chui vào case DENY qua `JAVA_TOOL_OPTIONS` hoặc cấu hình CI.
7. **Lưu JDK version, module descriptors và launcher args** cùng kết quả test để có thể tái lập.

### Gợi ý khung kiểm tra bằng Bash

~~~bash
# Case A, descriptor chưa opens:
javac --release 17 --module-source-path src -d mods -m library.core,client.check
java --module-path mods -m client.check/demo.client.CrossModuleProbe

# Case B, cùng compiled modules nhưng override runtime:
java --add-opens library.core/demo.internal=client.check \
  --module-path mods -m client.check/demo.client.CrossModuleProbe
~~~

Các lệnh là **hành vi integration test**; để tự động assert có thể dùng JUnit/Gradle/Maven test task khởi chạy một JVM mới cho mỗi case, so sánh stdout và exit code. Tránh tái sử dụng một JVM đã mở module bằng runtime API cho case DENY.

## 12. Checklist review quyền Lookup

- [ ] Xác định **lookup class** thật sự gọi `MethodHandles.lookup()` và module của nó.
- [ ] Xác định **target class/package/module** và quyền Java của thành viên.
- [ ] Biết test đang chạy **named modules trên module path**, không phải toàn bộ classpath.
- [ ] Kiểm tra `requires` / `canRead` giữa caller module và target module.
- [ ] Phân biệt `exports` cho public API và `opens` cho deep reflection.
- [ ] Cùng module: caller có đủ capability `MODULE` + `PRIVATE` nếu gọi `privateLookupIn`.
- [ ] Khác module: có **`reads` + `opens package to caller`**, không chỉ `exports`.
- [ ] Test DENY và ALLOW được thiết kế bằng **hai cấu hình rõ ràng**, không vô tình thừa launcher flags.
- [ ] Biết `publicLookup()` và `Lookup.in()` không phải lối đi tắt để nâng private access.
- [ ] Chỉ bắt `IllegalAccessException` cho negative permission test; để lỗi khác làm test fail.
- [ ] Thử đúng signature `findStatic`/`MethodType` và kiểu `invokeExact`.
- [ ] Không dùng `--illegal-access` hoặc nội bộ JDK đã legacy.
- [ ] Không mở vô điều kiện package nội bộ trong production chỉ vì test fail.
- [ ] Không leak full-power lookup hay private method handle tới code không đáng tin.
- [ ] Ghi nhận JDK version, module descriptors, JVM args và kết quả kiểm thử.

## 13. Bài tập tự luyện

1. Giữ nguyên descriptor ban đầu (không opens) và dự đoán ba dòng stdout. Giải thích vì sao `sameModule=secret-ok` nhưng `crossModule=DENIED`.
2. Đổi `opens demo.internal to client.check;` rồi biên dịch lại. Vì sao chỉ dòng `crossModule` thay đổi?
3. Giữ `exports demo.api;` nhưng **xóa `requires library.core;`** ở client. Lần này việc `import demo.api.LibraryApi;` có còn biên dịch không? Vì sao?
4. Chỉ thêm `exports demo.internal to client.check;`. Dự đoán kết quả private lookup. Kiểm tra xem exports có tự mở deep reflection hay không.
5. Thử đổi `MethodType.methodType(String.class)` thành `MethodType.methodType(int.class)`. Phân biệt lỗi không tìm thấy method hợp kiểu với lỗi thiếu quyền.
6. Thay `MethodHandles.lookup()` trong cross-module probe bằng `publicLookup()`. Khi đã `opens`, còn được privateLookupIn không?
7. Tạo `Lookup weak = MethodHandles.lookup().dropLookupMode(MethodHandles.Lookup.PRIVATE);`. Thử `privateLookupIn(target, weak)` và giải thích tại sao không thành công.
8. Bổ sung đoạn in `Module.canRead`, `isOpen` và `isExported` của caller/target; so sánh các cấu hình baseline, qualified opens và qualified exports.
9. Đổi `module library.core { exports demo.api; opens demo.internal to client.check; }` thành `open module library.core { exports demo.api; }`, rồi chỉ ra vì sao cách thứ hai có phạm vi quyền rộng hơn và rủi ro hơn.
10. Viết một integration test chạy **hai tiến trình Java mới**: một không `--add-opens` và một có đúng override; assert kết quả, exit code và không có lỗi ngoài dự kiến.
11. Chuyển `SameModuleProbe` sang **package khác trong cùng module** rồi cập nhật imports cần thiết. `privateLookupIn` có còn thành công khi đủ quyền không?
12. Giải thích tại sao phép tải `Class.forName("demo.internal.Secret")` không đồng nghĩa chương trình được quyền đọc `Secret.answer()`.

## 14. Tài liệu chuẩn còn hiệu lực

- [Oracle Java SE 25 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access modes, cross-module lookup, `Lookup.in`, `dropLookupMode` và `hasFullPrivilegeAccess`.
- [Oracle Java SE 25 – MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)): yêu cầu caller có `MODULE` + `PRIVATE`, quy tắc module readability và package opens.
- [Oracle Java SE 25 – Module](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`.
- [Oracle Java SE 17 – MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): đối chiếu API hiện diện ở baseline Java 17.
- [OpenJDK JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): thay đổi bảo vệ nội bộ JDK từ Java 17.
- [Dev.java – Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/): phân biệt exports/opens, ý nghĩa của named modules và launcher overrides.

**Ghi nhớ:** `MethodHandles.Lookup` là **quyền được JVM cấp theo caller class**, không phải lệnh bỏ qua access control. **Trong cùng mô-đun**, một lookup đầy đủ có thể dùng `privateLookupIn` để lấy quyền private target; **qua mô-đun khác**, phải có **đọc module + mở đúng package**. `exports` phục vụ public API, `opens` phục vụ runtime deep reflection. Kiểm thử đáng tin phải có cả **DENY trước khi mở** lẫn **PASS sau khi mở**, chạy bằng module path và xác nhận đúng loại lỗi — không “chữa” bằng cơ chế Java đã lỗi thời.