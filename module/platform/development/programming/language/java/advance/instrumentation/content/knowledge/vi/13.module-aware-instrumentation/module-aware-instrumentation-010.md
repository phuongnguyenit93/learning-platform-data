# Phân biệt thay module bằng Instrumentation với cấu hình --add-modules, --add-reads, --add-opens

Trong Java Platform Module System (JPMS), việc một Java agent muốn đọc lớp, gọi API hoặc truy cập private member thuộc một **named module** thường liên quan ít nhất ba vấn đề khác nhau: module đó **có được resolve vào module layer hay chưa**, module nguồn **có đọc được module đích hay không**, và package cần dùng **có được export/open cho caller hay không**. Nhìn chúng như một loại "quyền truy cập chung" sẽ dẫn tới cấu hình sai khi instrumentation.

Có hai thời điểm can thiệp chính:

- **Khi khởi động JVM:** dùng các tùy chọn launcher `--add-modules`, `--add-reads`, `--add-opens` (và khi cần `--add-exports`) để điều chỉnh việc resolve module và các quan hệ truy cập.
- **Khi JVM đã chạy và agent có đối tượng `Instrumentation`:** gọi `Instrumentation.redefineModule(...)` để **mở rộng** những quan hệ `reads`, `exports`, `opens` và khai báo sử dụng/cung cấp services cho một module **đã tồn tại**. Đây là cập nhật **module graph ở runtime**, không phải phương pháp tạo module mới hoặc nạp module root mới.

Đề bài nằm trong nhóm **Instrumentation và module**. Bài này trình bày nghĩa chính xác của từng cơ chế, khi nào dùng thay thế/bổ sung, mối quan hệ với class loaders, quyền truy cập bằng reflection và mã bytecode được agent chèn vào, cách kiểm tra kết quả qua `Module.canRead`/`Module.isOpen`, ví dụ **Java 17+ đã chạy thử** với ba cấu hình, những exception và giới hạn cần lưu ý.

> **Phiên bản:** JPMS và `Instrumentation.redefineModule` được giới thiệu từ Java 9. Ví dụ dùng `javac --release 17` và được biên dịch/chạy thành công trên OpenJDK 24; dùng JDK 17+ có hỗ trợ Java agents và named modules. Không dùng nội bộ JDK không có bảo đảm tương thích.

## 1. Bốn câu hỏi khác nhau về module

Hãy bắt đầu bằng sơ đồ:

~~~text
1. Module OBSERVABLE?
   | Có module trên --module-path / runtime image, có thể được tìm khi resolve?
   v
2. Module RESOLVED?
   | Có nằm trong boot module layer (hoặc một layer đã tạo) hay không?
   v
3. Module READS module đích?
   | m.canRead(other) có true không?
   v
4. Package được EXPORT / OPEN cho caller?
   | Public access và deep reflection có quyền tương ứng không?
   v
   MethodHandles / Reflection / bytecode linkage thực thi được?
~~~

Bốn lớp điều kiện này liên quan nhau nhưng **không thay thế nhau**.

| Khái niệm | Câu hỏi trọng tâm | Ví dụ kiểm tra |
| --- | --- | --- |
| **Module observable** | Hệ thống biết có module để có thể resolve không? | `--module-path mods` chỉ cung cấp đường tìm module |
| **Module resolved** | Module đã được chọn vào module graph/layer chưa? | `ModuleLayer.boot().findModule("demo.vault")` |
| **Readability** | Module nguồn được đọc module đích chưa? | `source.canRead(target)` |
| **Export** | Package công khai cho một module để truy cập kiểu/member public? | `source.isExported("p", target)` |
| **Open** | Package được mở để deep reflection vào non-public members? | `source.isOpen("p", target)` |
| **Modifiability** | Agent có thể dùng `redefineModule` với module này không? | `instrumentation.isModifiableModule(source)` |

Một module có thể đã **resolved** nhưng không có `requires java.logging`, nên chưa **read** `java.logging`. Một package có thể được **export** để cho phép gọi public method nhưng **chưa open** cho `setAccessible(true)` đối với private field/method. Và dù `isModifiableModule` trả `true`, nó **không** tự mở một package nào trước khi agent gọi API tương ứng.

## 2. So sánh nhanh ba tùy chọn launcher và `redefineModule`

| Cơ chế | Thời điểm | Thay đổi chính | Không làm được |
| --- | --- | --- | --- |
| `--add-modules M` | Startup JVM/module resolution | Bổ sung **root modules** cần resolve, cùng các phụ thuộc `requires` của chúng | Không tự thêm `reads` tùy ý giữa các module; không mở package |
| `--add-reads M=N` | Startup/module graph initialization | Bổ sung cạnh **M đọc N** (định hướng từ M → N) | Không resolve một module không tồn tại; không export/open package của N |
| `--add-opens M/p=N` | Startup/module graph initialization | Mở package `p` của module M cho N để làm **deep reflection** | Không thêm module root, không tự sửa toàn bộ package khác |
| `--add-exports M/p=N` | Startup/module access | Export package p để public API có thể được truy cập từ N | Không mở private members cho deep reflection |
| `Instrumentation.redefineModule(M,...)` | **Runtime**, từ Java agent có `Instrumentation` | Mở rộng `reads`, `exports`, `opens`, `uses`, `provides` trên **module hiện hữu** | Không tạo hoặc resolve module mới; không xóa các quan hệ đã cấp; không thay `module-info.class` trên đĩa |

**Phân biệt cốt lõi:**

- `--add-modules` nói **module nào tham gia resolution từ startup**.
- `--add-reads` nói **module nào đọc module nào**.
- `--add-opens` nói **package nào mở cho deep reflection của module nào**.
- `redefineModule` nói **agent cập nhật bổ sung các quan hệ của module đã tồn tại lúc runtime**.

Không có một lệnh duy nhất trong ba cờ launcher tương đương hoàn toàn với `redefineModule`: API runtime còn hỗ trợ `extraExports`, `extraUses` và `extraProvides`. Ngược lại, `redefineModule` không thay thế vai trò resolution/root selection của `--add-modules`.

## 3. `--module-path` và `--add-modules`: tìm module không đồng nghĩa resolve module

Một project có thể đặt `demo.vault` dưới thư mục module path:

~~~bash
java --module-path mods -cp app-out Main
~~~

Điều đó làm `demo.vault` **observable** nếu tổ chức thư mục/module hợp lệ; **không** tự bắt buộc nó xuất hiện trong boot layer của mọi chương trình chạy bằng classpath. Ứng dụng trên classpath thường nằm trong **unnamed module**, và tập root modules mặc định của launcher không nhất thiết bao gồm một application module chưa được yêu cầu.

Muốn yêu cầu resolve:

~~~bash
java --module-path mods --add-modules demo.vault -cp app-out Main
~~~

`--add-modules demo.vault` thêm `demo.vault` vào tập roots của resolution. Nếu descriptor của `demo.vault` có `requires` tới các modules khác, resolver còn xem xét các phụ thuộc ấy. Nhưng flag này **không** ngụ ý `demo.vault` đọc tất cả modules trong runtime image, và cũng không làm package `demo.vault` mở ra.

Có thể liệt kê nhiều roots:

~~~bash
java --module-path mods --add-modules demo.vault,java.logging -cp app-out Main
~~~

Các giá trị đặc biệt như `ALL-DEFAULT`, `ALL-SYSTEM` hoặc `ALL-MODULE-PATH` có ngữ nghĩa riêng trong launcher. Chúng có thể giải quyết số lượng lớn modules, nên dùng có chủ đích, tránh đưa vào production một cách tràn lan.

**Kiểm tra sau startup:**

~~~java
boolean present =
        ModuleLayer.boot().findModule("demo.vault").isPresent();
~~~

Snippet trên không phải chương trình độc lập; đặt vào một class có `main` như ví dụ ở mục 8. Khi `present=false`, đừng bắt đầu bằng việc gọi `redefineModule` trên một đối tượng module chưa có. Trước hết cần xác định module được đặt trên module path hợp lệ và đã được resolve vào layer mà ứng dụng đang xem.

### 3.1. `--add-modules` không phải `--add-reads`

Giả sử `demo.vault` không khai báo `requires java.logging;`. Ngay cả khi cả `demo.vault` và `java.logging` đã resolved, module `demo.vault` vẫn không mặc nhiên đọc `java.logging`. Thêm root module khác vào layer và thêm **read edge** giữa hai module là hai hành động khác nhau.

**Mẹo chẩn đoán:** dùng `ModuleLayer.boot().findModule(...)` để kiểm tra resolution; dùng `Module.canRead(...)` để kiểm tra readability. Không gộp hai câu hỏi thành "module có trên module path mà vẫn lỗi" vì chúng có thể có nguyên nhân khác nhau.

## 4. `--add-reads`: thêm cạnh readability một chiều

Cú pháp launcher:

~~~bash
java "--add-reads=demo.vault=java.logging" ...
~~~

Ý nghĩa: **module nguồn `demo.vault` được phép đọc module đích `java.logging`**. Chiều ngược lại **không** được suy ra. Nếu `java.logging` chưa đọc `demo.vault`, thêm cạnh `demo.vault → java.logging` không tự tạo `java.logging → demo.vault`.

Có thể chỉ định nhiều target modules trong một giá trị, khi launcher cho phép. Giá trị đặc biệt `ALL-UNNAMED` của `--add-reads` nghĩa là module nguồn được phép đọc các unnamed modules theo ngữ nghĩa launcher; trong khi API runtime `extraReads` nhận **những đối tượng `Module` cụ thể**, nên không có sentinel string `"ALL-UNNAMED"` trong chữ ký.

**Readability không phải quyền truy cập mọi package.** Nếu module đích không export package bạn cần, thêm `reads` vẫn không đủ để gọi một public class trong package bị encapsulate. Nếu muốn deep reflection vào private members, phải xem `opens`, không chỉ `reads`.

Cú pháp này hữu ích khi bytecode instrumentation chèn thêm lời gọi tới type của một module khác mà module chứa method bị sửa **chưa khai báo `requires` tới module ấy**. Nhưng compiler và runtime có giai đoạn kiểm tra khác nhau: `redefineModule` chạy lúc runtime **không** tự làm `javac` biên dịch source thiếu `requires` hợp lệ. Với source modules thực, dùng module descriptor/cờ compiler thích hợp, không chỉ thêm khả năng đọc vào runtime rồi kỳ vọng compile-time được bỏ qua.

**Lưu ý:** việc có read edge chưa bảo đảm bytecode đã instrument thực thi thành công. Class loader còn phải load được type, module đích phải export/open package phù hợp và helper phải có method descriptor đúng.

## 5. `--add-opens`: deep reflection, không phải tìm module

Cú pháp:

~~~bash
java "--add-opens=demo.vault/demo.vault=ALL-UNNAMED" ...
~~~

Phân tích:

- Phần đầu `demo.vault` là **module nguồn** chứa package cần mở.
- Phần sau dấu `/` là **tên package** `demo.vault` (có thể trùng chuỗi với tên module nhưng là hai khái niệm riêng).
- `ALL-UNNAMED` là target đặc biệt, nghĩa là package được mở cho **tất cả unnamed modules**, kể cả những unnamed modules được tạo về sau theo launcher semantics.

Khi package mở cho module caller, code ở caller có thể được cho phép dùng `AccessibleObject.setAccessible(true)` hoặc `MethodHandles.privateLookupIn` theo các điều kiện phù hợp, để truy cập members vốn bị strong encapsulation chặn. Nếu thiếu quyền opens, `setAccessible(true)` vào private method có thể ném `InaccessibleObjectException`.

`--add-opens` **không** tạo module `demo.vault` nếu nó chưa được resolve; cũng không thay thế `--add-reads` nếu code trong module nguồn cần đọc một module khác.

### 5.1. `--add-opens` so với `--add-exports`

| Tình huống | Thường cần |
| --- | --- |
| Code khác module muốn gọi **public** class/method từ package chưa export | `exports` và quan hệ `reads` phù hợp |
| Reflection vào **private** method/field của lớp trong package | `opens` đến module caller |
| Framework DI/ORM/serializer dùng deep reflection | `opens` cho framework module hoặc unnamed module tương ứng |
| Bytecode chèn `invokestatic Helper.method` từ module chưa đọc helper module | Read edge + export/access + visibility phù hợp |
| Agent chỉ lấy thông tin tên package hoặc module | Không mặc nhiên phải mở toàn bộ package |

**Điểm tinh tế khi đọc `Module.isExported`:** Javadoc `java.lang.Module` nói một package **đã được open đến một module thì được xem là exported đến module ấy ở runtime**. Vì vậy `isExported(package, target)` có thể trả `true` sau một lần `--add-opens` hoặc `extraOpens` dù không có thao tác `extraExports` riêng. Đừng dùng kết quả `isExported==true` để tự kết luận "đã có export tường minh nhưng package chưa open". Nếu muốn kiểm tra quyền deep reflection, dùng **`isOpen`**.

## 6. `Instrumentation.redefineModule`: cập nhật module graph lúc JVM đang chạy

Java agent nhận `Instrumentation` trong `premain` khi startup hoặc `agentmain` khi attach động (nếu JVM hỗ trợ). API:

~~~java
void redefineModule(
        Module module,
        java.util.Set<Module> extraReads,
        java.util.Map<String, java.util.Set<Module>> extraExports,
        java.util.Map<String, java.util.Set<Module>> extraOpens,
        java.util.Set<Class<?>> extraUses,
        java.util.Map<Class<?>, java.util.List<Class<?>>> extraProvides);
~~~

Chữ ký trên là để đối chiếu tham số, **không phải source độc lập**.

| Tham số | Cần đưa vào | Ý nghĩa |
| --- | --- | --- |
| `module` | Module **nguồn** đang được điều chỉnh | Đối tượng `Module` thực tế đã tồn tại |
| `extraReads` | `Set<Module>` | Thêm read edges từ nguồn tới các module trong set |
| `extraExports` | `Map<String, Set<Module>>` | Export thêm package thuộc module nguồn cho các module được chỉ định |
| `extraOpens` | `Map<String, Set<Module>>` | Open thêm package thuộc module nguồn cho các module được chỉ định |
| `extraUses` | `Set<Class<?>>` | Bổ sung service types mà module nguồn sử dụng |
| `extraProvides` | `Map<Class<?>, List<Class<?>>>` | Bổ sung các service providers mà module nguồn cung cấp |

`extraExports` và `extraOpens` có key là **tên package đầy đủ dạng dấu chấm**, ví dụ `"demo.vault"`, **không phải** internal JVM name `"demo/vault"`. Value phải là **set không trống** khi một key xuất hiện. Đối số toàn bộ không được null; khi không muốn chỉnh một loại quan hệ, truyền `Set.of()` hoặc `Map.of()` đúng kiểu.

### 6.1. Đây là phép mở rộng, không phải reset

Javadoc xác định `redefineModule` không thể giảm bớt read edges, exports, opens, uses hoặc provides đã tồn tại. Việc gọi nhiều lần có thể **bổ sung** quan hệ, không cung cấp nút "unread", "unexport" hoặc "close lại package" để hoàn tác.

Nếu gọi trên một **unnamed module**, API là **no-op**. `isModifiableModule(unnamed)` vẫn có thể trả `true` theo contract, nhưng không có lý do coi việc gọi API này sẽ đổi trạng thái module của classpath theo cùng cách như một named module.

Vì `redefineModule` bổ sung quyền runtime, đây là một **hành động có ảnh hưởng toàn tiến trình** tới module graph; không nên gọi tràn lan cho mọi module như một workaround cho cấu hình helper sai.

### 6.2. Không có khả năng "thêm root" của `--add-modules`

`redefineModule` yêu cầu một đối tượng `Module` và làm việc trên module đang có; nó **không** bổ sung module root vào boot layer. Nếu `ModuleLayer.boot().findModule("demo.vault")` trả `Optional.empty`, bạn không thể sửa chuyện đó bằng `redefineModule` trên một chuỗi tên chưa được resolve.

Có thể dùng API module-layer resolution để tạo layer mới trong thiết kế ứng dụng, nhưng đó là chủ đề và cơ chế **khác** `redefineModule`. Bài này tập trung vào khác biệt giữa root selection lúc startup và mở rộng runtime graph của module hiện hữu.

### 6.3. Cho phép agent làm điều module thường không tự làm được

API thông thường `Module.addReads`/`Module.addOpens` có ràng buộc **caller**: một module khác không thể tùy tiện mở module đích chỉ bằng việc gọi method `Module.addOpens` từ bên ngoài. `Instrumentation.redefineModule` được cung cấp cho agent để có thể cập nhật module graph khi cần instrumentation, trong phạm vi JVM cho phép.

Vì thế, nếu code chạy trong một **unnamed module của agent** gọi `vault.addOpens("demo.vault", app)`, đó không đương nhiên là phương án thay thế hợp lệ: có thể gặp `IllegalCallerException` vì caller không phải module `vault`. Agent dùng `Instrumentation.redefineModule` đúng contract sẽ rõ ràng và có thể kiểm thử hơn.

### 6.4. Kiểm tra trước khi sửa

~~~java
if (!inst.isModifiableModule(vault)) {
    throw new IllegalStateException("Module is not modifiable");
}
~~~

Đoạn này chỉ hợp lệ trong một method đã có `inst` và `vault`. `isModifiableModule` **khác** `isModifiableClass`: điều chỉnh module graph không đồng nghĩa redefine/retransform bytecode của một `Class<?>`.

## 7. Mô hình trước/sau trong một named module kín

Ta có module `demo.vault` với descriptor:

~~~java
module demo.vault {
}
~~~

Nó **không có `exports demo.vault;`**, **không có `opens demo.vault;`** và **không có `requires java.logging;`**. Bên trong module có lớp:

~~~java
package demo.vault;

public final class Secrets {
    private static String secret() { return "secret-value"; }
}
~~~

Lớp và method là hai thứ cần kiểm tra khác nhau: lớp có thể tồn tại và được JVM load, nhưng method private không thể được truy cập bằng deep reflection từ unnamed app khi package chưa open. Để quan sát, ứng dụng `Main` sẽ hỏi:

~~~java
Module vault = ModuleLayer.boot()
        .findModule("demo.vault")
        .orElseThrow();
Module app = Main.class.getModule(); // unnamed module trên classpath
Module logging = java.util.logging.Logger.class.getModule();

boolean reads = vault.canRead(logging);
boolean open = vault.isOpen("demo.vault", app);
~~~

Đây chỉ là một snippet được dùng đầy đủ trong `Main.java` ở mục 8.

Ba trạng thái ta muốn thấy:

~~~text
TRƯỚC KHI RESOLVE (không --add-modules):
demo.vault không nằm trong boot layer -> không có Module cần sửa

SAU --add-modules demo.vault,java.logging (chưa thêm quyền):
demo.vault đã resolved
reads java.logging = false
open demo.vault to unnamed app = false
deep reflection private method = blocked

SAU Instrumentation.redefineModule(...):
reads java.logging = true
open demo.vault to đúng unnamed app = true
deep reflection private method = allowed

VỚI FLAGS --add-reads và --add-opens TỪ LAUNCH:
read/open đã true trước khi agent gọi redefineModule
~~~

Thí nghiệm này **cố tình không chèn bytecode mới**, chỉ minh họa module graph. Để dùng với một transformer thực sự, bạn vẫn phải kiểm tra helper class/package/loader access và những lời gọi bytecode đã được tạo.

## 8. Demo Java 17+ chạy được: ba cấu hình, một agent

Bộ demo có **bốn source files** và một manifest:

~~~text
demo/
  src/
    demo.vault/
      module-info.java
      demo/
        vault/
          Secrets.java
  Agent.java
  Main.java
  MANIFEST.MF
~~~

**Kết quả mong muốn:**

1. Không yêu cầu thêm module root: `demo.vault` **chưa resolved** vào boot layer của chương trình mẫu.
2. Chỉ có `--add-modules`: module resolved nhưng quyền read/open vẫn thiếu, sau đó **agent cấp quyền ở runtime**.
3. Có đủ `--add-modules`, `--add-reads` và `--add-opens`: các quyền đã được cấu hình từ startup, nên agent không cần "chữa" lỗi ở lượt trước.

Đây là startup agent để tránh sự phụ thuộc vào Attach API và dynamic agent loading của từng JVM; `premain` nhận `Instrumentation` từ JVM khi khởi động. Build dùng plain classpath cho `Agent` và `Main`, đồng thời dùng module path cho `demo.vault`.

### 8.1. `src/demo.vault/module-info.java`

~~~java
module demo.vault {
}
~~~

Descriptor có chủ đích **không export/open package** và **không yêu cầu java.logging**. Module tự động đọc `java.base` theo JPMS, nhưng điều đó không kéo theo đọc `java.logging`.

### 8.2. `src/demo.vault/demo/vault/Secrets.java`

~~~java
package demo.vault;

public final class Secrets {
    private static String secret() {
        return "secret-value";
    }
}
~~~

`Secrets` là class public trong package chưa exported. Method `secret` là private. Code ở unnamed module có thể lấy `Class<?>` bằng tên theo điều kiện runtime, nhưng `setAccessible(true)` không được bỏ qua quy tắc `opens`. Trong demo, gọi reflection **sau khi** package được mở mới lấy được `secret-value`.

### 8.3. `Agent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

public final class Agent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void grant(Module source, Module app, Module logging) {
        if (!instrumentation.isModifiableModule(source)) {
            throw new IllegalStateException("Module is not modifiable");
        }

        instrumentation.redefineModule(
                source,
                Set.of(logging),
                Map.of(),
                Map.of("demo.vault", Set.of(app)),
                Set.of(),
                Map.of());
    }
}
~~~

Giải thích lần lượt:

- `premain` nhận và lưu `Instrumentation`; ví dụ không gọi `new Instrumentation()`.
- `isModifiableModule(source)` kiểm tra khả năng sửa module của JVM trước khi thực hiện.
- `Set.of(logging)` tương ứng **thêm read edge** `demo.vault → java.logging`.
- `Map.of()` cho `extraExports` nghĩa là demo **không yêu cầu export riêng**.
- `Map.of("demo.vault", Set.of(app))` cho `extraOpens` nghĩa là mở **chính xác package `demo.vault`** của module nguồn cho **đúng unnamed Module object của `Main`**.
- Hai đối số cuối `Set.of()` và `Map.of()` nghĩa là **không bổ sung uses/provides**.
- Gọi API ở startup hay runtime đều tuân cùng hợp đồng: nó chỉ thêm quyền, không xóa quyền trước có.

**Khác biệt đáng chú ý với launcher:** `--add-opens=demo.vault/demo.vault=ALL-UNNAMED` tác động tới **mọi unnamed module** theo launcher, còn `Set.of(app)` chỉ mở cho **một module object cụ thể**. Nếu runtime có nhiều class loaders, mỗi unnamed module của chúng có thể là đối tượng khác nhau; không mặc định lần `extraOpens` cho app có hiệu lực với tất cả.

### 8.4. `Main.java`

~~~java
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;
import java.util.logging.Logger;

public final class Main {
    public static void main(String[] args) throws Exception {
        var found = ModuleLayer.boot().findModule("demo.vault");
        System.out.println("MODULE_RESOLVED=" + found.isPresent());
        if (found.isEmpty()) return;

        Module vault = found.orElseThrow();
        Module app = Main.class.getModule();
        Module logging = Logger.class.getModule();

        System.out.println("READS_LOGGING_BEFORE=" + vault.canRead(logging));
        System.out.println("OPEN_TO_APP_BEFORE=" + vault.isOpen("demo.vault", app));
        System.out.println("REFLECTION_BEFORE=" + reflection());

        Agent.grant(vault, app, logging);

        System.out.println("READS_LOGGING_AFTER=" + vault.canRead(logging));
        System.out.println("OPEN_TO_APP_AFTER=" + vault.isOpen("demo.vault", app));
        System.out.println("REFLECTION_AFTER=" + reflection());
    }

    private static String reflection() throws Exception {
        Class<?> type = Class.forName("demo.vault.Secrets");
        Method method = type.getDeclaredMethod("secret");
        try {
            method.setAccessible(true);
        } catch (InaccessibleObjectException ex) {
            return "BLOCKED";
        }
        return (String) method.invoke(null);
    }
}
~~~

Các điểm chủ đích:

1. `ModuleLayer.boot().findModule("demo.vault")` phân biệt **module chưa resolved** với **module resolved nhưng quyền còn thiếu**. Nếu chưa resolved, chương trình in `MODULE_RESOLVED=false` rồi kết thúc; không tự suy rằng `redefineModule` có thể resolve module đó.
2. `Logger.class.getModule()` cung cấp đối tượng module `java.logging` để đo readability và làm đích của `extraReads`. Hai lệnh chạy có module `demo.vault` đều yêu cầu `--add-modules demo.vault,java.logging` để bảo đảm các module đó được resolve.
3. `Main.class.getModule()` là unnamed module của classpath app trong demo; nó là **target của `extraOpens`** ở runtime.
4. `vault.canRead(logging)` và `vault.isOpen("demo.vault", app)` cho hai boolean **khác mục đích**.
5. `Class.forName(...)` tìm class `Secrets` theo tên đã biết. `getDeclaredMethod("secret")` lấy method metadata; `setAccessible(true)` mới là nơi deep reflection bị chặn khi package chưa open.
6. Chỉ bắt `InaccessibleObjectException` quanh `setAccessible(true)`, rồi trả chuỗi `BLOCKED` để demo có stdout rõ. Ví dụ không coi mọi `ReflectiveOperationException` hay module-resolution failure là "đã chặn đúng"; các lỗi khác được cho nổi lên để test báo sai.
7. Gọi `Agent.grant(...)` **sau lần đo BEFORE**; vì thế có thể quan sát runtime mutation thật sự thay vì bắt đầu ở trạng thái đã cấp mọi quyền.
8. Không cần truy cập nội dung private bằng compiler ở `Main`, nhờ vậy app có thể biên dịch dù package chưa export/open. Đây là kỹ thuật **quan sát khả năng reflection**, không phải lời khuyên viết toàn bộ ứng dụng bằng reflection.

### 8.5. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

Tệp manifest cần newline kết thúc và dòng trống sau main section. Không cần `Can-Retransform-Classes` hay `Can-Redefine-Classes` vì demo này **không gọi `retransformClasses`/`redefineClasses`**. `redefineModule` có API `isModifiableModule` riêng; đừng nhầm quyền chỉnh module với quyền sửa class bytecode.

### 8.6. Lệnh biên dịch và đóng gói

Từ thư mục `demo/`:

~~~bash
javac --release 17 -d mods/demo.vault src/demo.vault/module-info.java src/demo.vault/demo/vault/Secrets.java
javac --release 17 -d agent-out Agent.java
javac --release 17 -cp agent-out -d app-out Main.java
jar --create --file agent.jar --manifest MANIFEST.MF -C agent-out .
~~~

`mods/demo.vault` sau đó chứa `module-info.class` và `demo/vault/Secrets.class`. Đây là một **exploded named module** trên module path `mods`. `agent-out` có `Agent.class`, `app-out` có `Main.class`, còn `agent.jar` có `Premain-Class: Agent`.

Để chạy, **không** đặt `mods/demo.vault` trực tiếp vào classpath. Nó được tìm nhờ `--module-path mods` và resolve nhờ `--add-modules`. Đây chính là ranh giới module path/classpath mà demo muốn kiểm tra.

### 8.7. Lượt 1 — module observable nhưng chưa resolved

~~~bash
java --module-path mods -javaagent:agent.jar -cp app-out Main
~~~

**Standard output thực nghiệm (OpenJDK 24, Java 17 class files):**

~~~text
MODULE_RESOLVED=false
~~~

Với cấu hình demo `demo.vault` không được yêu cầu làm root và cũng không là dependency của module đã chọn. Vì thế nó chưa nằm trong boot layer dù thư mục module path chứa đầy đủ class file. `Main` trả về ngay, không gọi `Agent.grant`.

Không suy ra rằng **mọi** named module được đặt trên module path trong mọi chương trình đều chưa resolved: nếu module là main module hoặc được yêu cầu bởi `requires`/các root options khác, nó có thể đã được resolve. Lượt này minh họa một module cụ thể **không có lý do resolution khác**.

### 8.8. Lượt 2 — thêm `--add-modules`, agent cấp quyền ở runtime

~~~bash
java --module-path mods --add-modules demo.vault,java.logging -javaagent:agent.jar -cp app-out Main
~~~

**Standard output đã được biên dịch và chạy thực tế:**

~~~text
MODULE_RESOLVED=true
READS_LOGGING_BEFORE=false
OPEN_TO_APP_BEFORE=false
REFLECTION_BEFORE=BLOCKED
READS_LOGGING_AFTER=true
OPEN_TO_APP_AFTER=true
REFLECTION_AFTER=secret-value
~~~

Điểm cần phân tích:

- `MODULE_RESOLVED=true` chứng minh `demo.vault` đã vào boot layer nhờ `--add-modules`.
- `READS_LOGGING_BEFORE=false` vì descriptor `demo.vault` không `requires java.logging` và chưa có read edge bổ sung.
- `OPEN_TO_APP_BEFORE=false` vì package `demo.vault` chưa open cho unnamed app.
- `REFLECTION_BEFORE=BLOCKED` do `setAccessible(true)` chưa được phép với private member.
- Sau `Agent.grant`, `extraReads` tạo cạnh tới `java.logging`, `extraOpens` mở package cho `app`; các kiểm tra cùng đối tượng `Module` lập tức chuyển sang `true`.
- `REFLECTION_AFTER=secret-value` chứng minh deep reflection giờ được phép, method private trả về chuỗi như thiết kế.

Điều này chứng minh **không cần restart** để thêm quyền đối với module đã tồn tại, khi agent dùng `redefineModule` thành công. Tuy nhiên, không thể áp dụng logic ấy để tạo module root mới hoặc để rollback quyền vừa cấp.

### 8.9. Lượt 3 — cấu hình `--add-reads` và `--add-opens` ngay từ startup

~~~bash
java --module-path mods --add-modules demo.vault,java.logging "--add-reads=demo.vault=java.logging" "--add-opens=demo.vault/demo.vault=ALL-UNNAMED" -javaagent:agent.jar -cp app-out Main
~~~

Đặt dấu quote quanh toàn bộ tham số có dấu `=` giúp giữ nguyên JVM arguments trên các shell phổ biến, đặc biệt khi dùng Windows PowerShell. Đặt **tất cả JVM options trước tên class `Main`**; nếu đưa ra sau tên Main, chúng trở thành application arguments.

**Standard output đã đối chiếu trên OpenJDK 24:**

~~~text
MODULE_RESOLVED=true
READS_LOGGING_BEFORE=true
OPEN_TO_APP_BEFORE=true
REFLECTION_BEFORE=secret-value
READS_LOGGING_AFTER=true
OPEN_TO_APP_AFTER=true
REFLECTION_AFTER=secret-value
~~~

Kết luận từ phép so sánh:

- `--add-modules` làm module resolved ở startup.
- `--add-reads` làm `canRead(java.logging)` true **trước khi agent thay đổi graph**.
- `--add-opens` làm `isOpen("demo.vault", app)` true, nên reflection private member thành công **ngay ở lần BEFORE**.
- Gọi lại `redefineModule` chỉ thêm các quan hệ vốn đã có; API additive nên trạng thái AFTER vẫn true. Nó không phải thao tác hoàn tác hay thay thế flags.

Lượt 2 và lượt 3 có **trạng thái cuối** tương đồng cho đúng đối tượng app module, nhưng **thời điểm quyền có hiệu lực khác**. Lượt 3 áp dụng từ startup cho tất cả unnamed modules; lượt 2 cấp quyền khi gọi agent cho một unnamed module cụ thể. Đừng nhầm hai điều đó là tương đương hoàn toàn.

## 9. Đọc kết quả bằng `Module` API, không chỉ đoán từ JVM flags

Cách quan sát nên dùng:

| Phép kiểm | Đang hỏi điều gì? | Lưu ý |
| --- | --- | --- |
| `ModuleLayer.boot().findModule("demo.vault")` | Module đã nằm trong boot layer chưa? | Không tự suy ra readability hoặc openness |
| `vault.canRead(logging)` | Vault có đọc logging không? | Cạnh này một chiều; không chỉ do launcher flag |
| `vault.isExported("demo.vault", app)` | Public access có được xem là exported tới app không? | Có thể true do package **open** tới app |
| `vault.isOpen("demo.vault", app)` | Deep reflection được mở cho app chưa? | Gắn với package và target module cụ thể |
| `inst.isModifiableModule(vault)` | Agent có thể cập nhật module này không? | Không đồng nghĩa class bytes modifiable |
| `Main.class.getModule()` | Unnamed/named module **của Main** | Không bắt buộc trùng unnamed module ở custom loader khác |
| `ClassLoader.getSystemClassLoader()` | Loader system hiện tại | Không trả lời được mọi module relationship |

**Điều `Module.isOpen` không chứng minh:** code không được bảo đảm chạy đúng chỉ vì package đã mở. Module còn phải resolved, class loader phải tìm class, method signature phải đúng, quyền access vào members phải hợp lệ và logic thực thi không ném lỗi. Trong demo, các điều kiện ấy được kiểm tra thực tế qua `Method.invoke`.

### 9.1. Runtime module graph và descriptor không phải cùng một đối tượng cấu hình

Một module descriptor trong `module-info.class` có thể không đổi trên đĩa sau khi JVM áp dụng flags hoặc `redefineModule`. Do đó đọc `module.getDescriptor().requires()` hoặc mở lại file `module-info.java` **không phải** cách duy nhất xác định read edges runtime. Hãy dùng `Module.canRead`, `isExported`, `isOpen` và thử access thật trong JVM.

Không sửa file `module-info.java` ở runtime bằng `redefineModule`. API không viết lại source, không biên dịch hay thay đổi JAR trên đĩa; nó cập nhật quan hệ module được JVM sử dụng trong tiến trình hiện tại.

## 10. Khi bytecode instrumentation cần helper ở module khác

Nếu transformer chèn vào module `M` một lời gọi tới helper `H`, hãy phân tách đường đi:

~~~text
JVM dùng class loader xác định helper class H
        |
        v
Module M có read edge tới module chứa H?
        |
        v
Package của H export/open hợp lệ cho M?
        |
        v
Method owner/name/descriptor/opcode trong bytecode đúng?
        |
        v
Hook thực thi, không gây recursion/exception nguy hiểm?
~~~

Một tình huống:

~~~text
Module demo.app có method process()
  -> agent chèn invokestatic demo.agent.helper.Probe.record(...)
     -> Probe nằm trong module demo.agent.helper, khác demo.app
     -> demo.app chưa requires helper module
     -> có thể cần mở rộng reads từ demo.app tới helper module
     -> helper package cần export cho demo.app
     -> defining class loader của process() phải thấy Probe
~~~

Nếu dùng `Instrumentation.redefineModule` lúc agent đã khởi động, ví dụ ý tưởng:

~~~java
inst.redefineModule(
        applicationModule,
        Set.of(helperModule),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**Snippet này không độc lập:** `inst`, `applicationModule` và `helperModule` phải là những đối tượng đã được xác định ở ngữ cảnh agent. Nó chỉ thêm **read edge**. Nếu package của helper chưa export cho application module, cần sửa quan hệ ở **phía module helper**, ví dụ gọi `redefineModule(helperModule, Set.of(), Map.of("helper.pkg", Set.of(applicationModule)), ...)`, không phải mở package của application module một cách tùy tiện.

Với helper được nạp từ JAR vào **unnamed module** trên classpath/system loader, đối tượng đích của `extraReads` là unnamed `Module` phù hợp; không có literal `ALL-UNNAMED` làm đối số cho `Set<Module>`. Cấu hình `--add-reads M=ALL-UNNAMED` ở startup là cách khác với phạm vi khác.

Nếu mục tiêu là **deep reflection** của agent vào private field trong module M, cần **extraOpens** của **M tới module của caller**, không phải một read edge bổ sung theo hướng tùy ý. Đây là hai use cases khác nhau dù đều có thể xuất hiện trong cùng agent.

### 10.1. Đặt `redefineModule` ở thời điểm nào?

- Với startup agent, có thể cập nhật module graph trong `premain` trước khi đăng ký transformer và trước khi ứng dụng vào đường code cần helper.
- Với dynamic attach agent, có thể cập nhật graph trong `agentmain` sau khi JVM đã chạy; nhưng phải kiểm tra lớp/bytecode đã được load và lỗi linking đã xảy ra trước khi agent can thiệp.
- Khi thay đổi module graph sau khi bytecode đã tạo symbolic references, cần thận trọng với những resolution failures đã xảy ra. Một số lỗi resolution có thể bị JVM ghi nhớ cho cùng symbolic reference; cấp quyền muộn không bảo đảm mọi invocation cũ sẽ tự hồi phục.
- Nếu có nhiều threads/agents cùng thay đổi module, `redefineModule` được Javadoc cho phép dùng đồng thời nhưng vẫn cần lập kế hoạch phạm vi quyền và theo dõi thay đổi.
- Chỉ mở những packages/target modules cần thiết để giảm vùng ảnh hưởng bảo mật.

Một ngoại lệ đến từ việc **chèn bytecode hợp lệ hay không**, ví dụ `VerifyError` do operand stack sai, **không tự được sửa** chỉ bằng `--add-opens` hoặc `redefineModule`. Module access và bytecode verifier là các lớp kiểm tra khác nhau.

## 11. `extraExports` và `extraOpens` có phạm vi như thế nào?

Xem hai đoạn snippet (đều **trong ngữ cảnh đã có `Instrumentation inst`**):

**Export một package tới module consumer:**

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of("com.example.api", Set.of(consumerModule)),
        Map.of(),
        Set.of(),
        Map.of());
~~~

**Open một package để reflection vào private members:**

~~~java
inst.redefineModule(
        sourceModule,
        Set.of(),
        Map.of(),
        Map.of("com.example.internal", Set.of(reflectionModule)),
        Set.of(),
        Map.of());
~~~

Điểm dễ sai: `sourceModule` phải **sở hữu package** được nhắc trong map. `extraExports`/`extraOpens` với tên package không thuộc module nguồn sẽ dẫn đến `IllegalArgumentException` theo contract. Set target modules cho từng package không được rỗng. Nếu không biết module ownership, hãy tra từ `Class.getModule()` trên type thật sự (ở nơi load an toàn), không đoán từ chuỗi package.

Về ý nghĩa, "export" là cho **public access**, "open" là cho **deep reflective access**. Khi package open tới một module, `Module.isExported(package, target)` cũng trả true ở runtime; nhưng vẫn nên chọn đúng thao tác để thể hiện **chủ đích least privilege**. Đừng dùng `extraOpens` toàn diện chỉ vì code cần gọi một public method.

### 11.1. Các service parameters

`extraUses` và `extraProvides` không có cơ chế tương đương trực tiếp trong ba cờ `--add-modules`, `--add-reads`, `--add-opens`. Chúng giúp agent bổ sung quan hệ use/provide service theo contract của JPMS. Tuy nhiên:

- `extraUses` chứa service types dạng `Class<?>`; không phải chuỗi tên service.
- `extraProvides` map service type sang danh sách provider classes hợp lệ. Một provider phải đúng module và phù hợp service contract, không phải class tùy ý.
- Javadoc nêu trách nhiệm của agent trong việc đảm bảo service type accessible tại instrumentation sites; API không tự làm mọi package/export/readability hợp lệ chỉ vì khai báo use/provide.
- Bài thực hành không cần service relationships, nên hai tham số cuối truyền collections rỗng. Không nên thêm chúng chỉ để "cho đủ sáu tham số".

## 12. `--add-modules` không phải `--patch-module` và không phải `redefineModule`

Ba cơ chế có tên gần giống:

- `--add-modules` chọn thêm root modules để **resolve**.
- `--patch-module M=path` cho phép launcher **override hoặc augment nội dung của module** bằng class/resource files tại path (theo các ràng buộc module/launcher).
- `Instrumentation.redefineModule` bổ sung **quan hệ truy cập/service** cho module hiện hữu ở runtime.

Không được nhầm `redefineModule` với `redefineClasses`. Hai method đều bắt đầu bằng `redefine` nhưng **mục tiêu khác nhau**:

| API | Sửa cái gì? | Có thay bytecode method không? |
| --- | --- | --- |
| `Instrumentation.redefineModule` | Reads/exports/opens/uses/provides của Module | **Không** |
| `Instrumentation.redefineClasses` | Định nghĩa class, bằng classfile bytes mới | Có, trong giới hạn JVM |
| `Instrumentation.retransformClasses` | Chạy lại transformer pipeline trên loaded classes | Có thể, nếu transformer trả bytes mới |
| `--patch-module` | Class/resource content được đưa vào module ở startup | Có thể ảnh hưởng những class definitions được JVM chọn lúc load |
| `--add-modules` | Root module resolution | Không trực tiếp thay class bytes |

Nếu bug là "package không open cho reflection", `redefineClasses` không phải giải pháp phù hợp. Nếu bug là "method body instrument sai", mở package bằng `redefineModule` không sửa nổi operand stack hoặc logic. Phân biệt được câu hỏi sẽ tiết kiệm nhiều vòng debug.

## 13. Những giới hạn và exception khi gọi `redefineModule`

Theo Javadoc Java 17, API có thể ném:

| Loại | Nguyên nhân tiêu biểu |
| --- | --- |
| `UnmodifiableModuleException` | Module được chỉ định không thể điều chỉnh bằng `redefineModule` |
| `IllegalArgumentException` | Key package không thuộc module; map chứa set rỗng; extraProvides có provider không hợp lệ |
| `NullPointerException` | Một đối số hoặc key/value trong các tập/maps là null |

**Lưu ý:** `isModifiableModule` trả true cho unnamed module, nhưng gọi `redefineModule` trên unnamed module là **no-op**. Vì vậy chỉ kiểm tra `isModifiableModule` chưa đủ để đảm bảo có tác động quan sát được. Thực hành trên named module và xác minh `canRead`/`isOpen` sau lời gọi.

Không có API "unopen" hoặc "remove extraReads" qua `redefineModule`. Nếu đã cấp quyền runtime, việc bỏ cấu hình agent sau đó không tự thu hồi các quyền đã thêm. Khi test nhiều lần trong cùng JVM, trạng thái "AFTER" của lượt trước có thể còn hiệu lực; muốn kiểm tra trạng thái "BEFORE" thật, chạy **một JVM mới** như các lệnh trong demo.

### 13.1. Runtime và compiler báo các lỗi khác nhau

- **Compiler:** package không visible hoặc module nguồn không `requires` module đích khi biên dịch source có direct reference. Cần sửa `module-info.java` hoặc cấu hình compiler phù hợp.
- **Runtime loader:** class không được tìm thấy (`ClassNotFoundException` / `NoClassDefFoundError`), dù module graph có thể đã được mở.
- **Runtime access:** `IllegalAccessError` khi bytecode linkage sai quyền module/package, hoặc `InaccessibleObjectException` khi deep reflection bị chặn.
- **Bytecode validity:** `VerifyError`, `ClassFormatError` do transform sai bytecode, không liên quan trực tiếp flag opens/reads.
- **Agent API:** `UnmodifiableModuleException`/`IllegalArgumentException` khi truyền sai mô-đun/packages/targets.

Đừng bắt một `Exception` chung rồi log "module inaccessible" cho mọi trường hợp. Ghi rõ **giai đoạn** (resolve, load, link, reflect, redefineModule) và kiểu lỗi.

## 14. Quy tắc least privilege khi mở module

Khả năng thay runtime module graph hữu ích cho monitoring/tracing, nhưng đồng thời làm giảm tính encapsulation nếu dùng không kiểm soát. Những điểm nên thực hiện:

1. **Chỉ mở đúng package cần thiết.** Không mở toàn bộ modules hoặc package tree khi chỉ cần một API.
2. **Chọn đúng target module.** Dùng `Set.of(agentModule)`/`Set.of(helperModule)` thay vì mở rộng không kiểm soát cho mọi unnamed modules nếu phạm vi runtime cho phép.
3. **Phân biệt export và open.** Chỉ cần public linkage thì export và read; deep reflection mới cần opens.
4. **Kiểm tra loader/module thực tế.** Hai classes cùng package string có thể thuộc modules/loaders khác nhau; target bằng `Main.class.getModule()` chỉ đúng với app của ví dụ.
5. **Đừng cấp quyền cho một module không cần quyền.** Một `extraReads` dư có thể thay đổi coupling giữa modules; một `extraOpens` dư có thể cho phép truy cập private state.
6. **Audit thay đổi do agent.** Ghi module nguồn, package, target, thời điểm, lý do và phiên bản agent; không lộ private data trong diagnostics.
7. **Không nhầm runtime patch với chính sách build lâu dài.** Nếu ứng dụng kiểm soát được source, ưu tiên khai báo `requires`/`exports`/`opens` hợp lệ trong module descriptor thay vì lạm dụng flag/agent workaround.
8. **Đảm bảo mô-đun đã resolved và helper có thể load.** Quyền module không thay thế thiết lập module path, classpath và dependency packaging.

Ở những JVM được nhiều agent dùng, các phép mở rộng do từng agent thực hiện có thể kết hợp; nên kiểm tra trạng thái thực tế của module graph, không giả định chỉ cấu hình agent của mình quyết định mọi quyền.

## 15. Khi nào dùng cờ khởi động, khi nào dùng `redefineModule`?

| Nhu cầu | Ưu tiên hợp lý | Vì sao |
| --- | --- | --- |
| Chắc chắn module M cần hiện diện từ startup | `--module-path` + `--add-modules M` | Module phải được resolve trước khi lấy đối tượng Module |
| Cần read edge ổn định giữa hai named modules ngay từ startup | `--add-reads M=N` hoặc `requires` trong descriptor | Định cấu hình trước khi code chạy |
| Framework được biết trước cần deep reflection | `--add-opens M/p=N` hoặc `opens` phù hợp | Package đã open trước lần reflection đầu tiên |
| Agent attach muộn, cần đọc thêm module từ code instrumented | `Instrumentation.redefineModule` nếu module đã tồn tại | Không cần restart để mở rộng graph |
| Agent cần mở package hẹp cho module của helper cụ thể | `extraOpens` tới `Set.of(helperModule)` | Target scoped theo Module object |
| Thiếu module root chưa resolve trong boot layer | Launcher `--add-modules` hoặc thiết kế layer | `redefineModule` không giải quyết resolution |
| Muốn cập nhật method body của class | `retransformClasses` hoặc `redefineClasses` theo contract | Không phải nhiệm vụ của redefineModule |
| Chỉ cần public API trong package bị encapsulate | Read + exports, không mở private members | Giảm vùng quyền cấp |
| Cần service uses/providers mới cho instrumentation | `redefineModule` với `extraUses`/`extraProvides` | Launcher flags nêu trên không trực tiếp mang cùng dữ liệu |

Một quy tắc thực dụng: **nếu điều kiện biết trước và có quyền sửa JVM startup, khai báo từ startup dễ tái hiện hơn**. Nếu điều kiện chỉ xuất hiện khi agent đang chạy và module đã resolved, `redefineModule` có thể phù hợp hơn. Nhưng không dùng runtime API để che giấu một sự cố module resolution hoặc packaging.

## 16. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Cần kiểm tra trước |
| --- | --- |
| `ModuleLayer.boot().findModule("M")` trả empty | `--module-path`, root selection `--add-modules`, descriptor `requires` |
| `M.canRead(N)==false` | `requires`, `--add-reads M=N` hoặc `extraReads` |
| `M.isOpen("pkg", caller)==false` | `opens` trong descriptor, `--add-opens M/pkg=caller` hoặc `extraOpens` |
| Public type không truy cập được | Read edge **và** export/access từ module chứa package |
| `setAccessible(true)` ném `InaccessibleObjectException` | Package có open cho **module caller thực sự** không |
| `NoClassDefFoundError` dù `canRead` true | Loader có thể tìm helper class không; module target đã resolved chưa |
| `IllegalArgumentException` trong `redefineModule` | Package key có thuộc module không; set/list values hợp lệ không |
| `UnmodifiableModuleException` | `isModifiableModule(module)`, loại module/JVM |
| Thêm `--add-opens` nhưng module vẫn not found | Chưa giải quyết root/observable module |
| Agent sửa module nhưng compiler vẫn từ chối source | Runtime redefine không thay module descriptor hay compile-time checks |
| `isExported` true nhưng `isOpen` cũng true | Package open được xem là exported at runtime, không suy ra export tường minh |
| Lượt chạy thứ hai có BEFORE=true | Đã cấu hình launcher flags khác, hoặc đang tái sử dụng JVM/agent state |
| Một unnamed module gọi được còn plugin loader khác không | Runtime extraOpens có thể chỉ cấp quyền cho **một Module object**, không phải ALL-UNNAMED |

## 17. Checklist QA cho agent sử dụng JPMS

- [ ] Xác định chính xác **module nguồn** cần thay, module đích và package thuộc module nguồn.
- [ ] Xác định module đã **resolved** hay mới **observable**; đừng gọi `redefineModule` trên tên string.
- [ ] Dùng `Module.canRead` để đo read edge, `isOpen` để đo deep reflection; nhớ opens có thể làm `isExported` true ở runtime.
- [ ] Nếu muốn module root có từ startup, dùng `--add-modules` và module path đúng; không dùng `extraReads` thay cho resolution.
- [ ] Nếu chỉ cần public access, kiểm tra export/read trước khi mở private access.
- [ ] Với runtime mutation, kiểm tra `isModifiableModule` và dùng sets/maps không null, package keys hợp lệ.
- [ ] Tách quyền giữa unnamed module của agent, app và từng custom class loader.
- [ ] Chuẩn bị helper visibility/bytecode contract trước khi instrument class ở hot path.
- [ ] Không gọi reflection phức tạp hoặc logging đồng bộ ngay trong `ClassFileTransformer.transform`.
- [ ] So sánh một JVM **sạch** không flags với JVM có flags và JVM chỉ được agent sửa lúc runtime.
- [ ] Đo behavior thực tế, không chỉ một số giá trị boolean; test cả module resolution, reflection/linkage và exception.
- [ ] Ghi nhận runtime quyền đã được cấp nhưng không tự thu hồi được bằng `redefineModule`.

## 18. Câu hỏi tự kiểm tra

1. Module M đã nằm trên `--module-path` nhưng `ModuleLayer.boot().findModule("M")` trả empty. Nên sửa `--add-reads` hay `--add-modules` trước?
2. M cần gọi public class của N nhưng M chưa đọc N. `--add-modules N` có tự tạo read edge M → N không?
3. `--add-reads M=N` có tự export hoặc open package của N cho M không?
4. Vì sao `--add-opens M/p=ALL-UNNAMED` có phạm vi khác với `extraOpens=Map.of("p", Set.of(Main.class.getModule()))`?
5. Khi `isExported("p", app)` trả true do một package đã mở, phải dùng method nào để đo riêng quyền deep reflection?
6. Tại sao chỉ thêm `--add-opens` không giải quyết một module chưa resolved?
7. `redefineModule` có làm một module mới xuất hiện trong boot layer không? Có xóa một read edge từng cấp không?
8. `extraExports` và `extraOpens` nhận key dạng `"demo.vault"` hay `"demo/vault"`?
9. Hai tham số `extraUses` và `extraProvides` dùng để làm gì? Có liên quan trực tiếp tới ba launcher flags được nêu không?
10. Vì sao không thể thay `redefineModule` bằng `redefineClasses` để sửa lỗi module access?
11. Tại sao demo `Main` không import trực tiếp `demo.vault.Secrets` mà dùng reflection?
12. Trong lượt 2, vì sao `REFLECTION_BEFORE=BLOCKED` nhưng `REFLECTION_AFTER=secret-value`?
13. Trong lượt 3, tại sao `READS_LOGGING_BEFORE=true` và `OPEN_TO_APP_BEFORE=true` trước khi agent sửa gì?
14. Nếu một plugin loader có unnamed module riêng, runtime `Set.of(app)` có cấp quyền cho nó không?
15. Khi dùng agent đã attach vào JVM chạy lâu, vì sao phải xét cả lỗi resolution đã xảy ra trước khi cấp quyền?
16. Cần những kiểm thử nào để đảm bảo bytecode helper có thể link thực tế dù module graph đã được cập nhật?

## 19. Kết luận

**Đừng nhầm ba điều kiện độc lập: module đã được resolve, module nguồn được đọc module đích, và package được export/open cho module caller.** `--add-modules` giải quyết **root module selection lúc khởi động**; `--add-reads` bổ sung **readability**; `--add-opens` mở **deep reflection** cho package cụ thể. Chúng là ba cờ khác mục đích, không thay thế cho nhau.

`Instrumentation.redefineModule` là công cụ bổ sung dành cho agent: nó thay đổi **động và theo hướng mở rộng** read/exports/opens/uses/provides của module **đã tồn tại**. Nó không tự tạo/resolve module, không sửa file `module-info.class`, không biến symbolic references hoặc code không hợp lệ thành bytecode đúng, và không cho phép gỡ các quyền đã thêm.

Thí nghiệm ba cấu hình minh họa rõ điều đó: không thêm roots thì module `demo.vault` chưa resolved; khi thêm roots nhưng chưa thêm quyền, agent có thể mở read/open ở runtime; khi cung cấp launcher flags từ startup, các quyền đã có trước khi agent gọi API. Nắm được ranh giới này sẽ giúp triển khai instrumentation trên named modules chính xác và tránh mở quyền quá rộng.

### Tài liệu chính thức

- [Oracle JDK 17 — Instrumentation.redefineModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineModule(java.lang.Module,java.util.Set,java.util.Map,java.util.Map,java.util.Set,java.util.Map)): sáu tham số, nguyên tắc additive, no-op cho unnamed module và exceptions.
- [Oracle JDK 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--add-modules`, `--add-reads`, `--add-opens` và `--add-exports`.
- [Oracle JDK 17 — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và những giới hạn caller của `Module.addReads`/`Module.addOpens`.
- [Oracle JDK 17 — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): lỗi khi không thể enable suppressed Java access checks.
- [Oracle JDK 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): các layers đã resolve modules và tìm kiếm `findModule`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): cơ chế module resolution và các launcher options được giới thiệu trong Java 9.
