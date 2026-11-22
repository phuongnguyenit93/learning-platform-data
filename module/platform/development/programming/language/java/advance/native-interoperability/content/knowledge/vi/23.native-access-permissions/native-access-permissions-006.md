# Kiểm tra hoặc cấp quyền truy cập native cho module động trong phạm vi API cho phép

## 1. Mục tiêu: quyền native gắn với module, không chỉ với lời gọi hàm

Khi tích hợp Java với C/C++ bằng **Foreign Function & Memory API (FFM)** hoặc **Java Native Interface (JNI)**, một số thao tác vượt qua ranh giới quản lý của JVM. Ví dụ: gọi restricted FFM methods, mở native library, thực hiện downcall/upcall, hoặc dùng JNI native methods. Những thao tác này có thể gây hỏng bộ nhớ hoặc crash nếu code native, layout, con trỏ hay vòng đời tài nguyên được xử lý sai.

Java quản lý **native access** theo **module**. Một module có thể được runtime cho phép thực hiện các thao tác bị hạn chế (*restricted operations*), và chương trình có thể hỏi module đó đã được bật quyền chưa:

```java
Module current = MyClass.class.getModule();
boolean enabled = current.isNativeAccessEnabled();
```

Với module được tạo **động** bên trong một `ModuleLayer`, API còn cho phép **một chủ thể đã có quyền native** cấp quyền cho module đích trong layer mà nó điều khiển:

```java
ModuleLayer.Controller controller = ...; // do defineModules* trả về
Module plugin = ...;                     // thuộc đúng layer của controller

controller.enableNativeAccess(plugin);   // restricted API
```

Hai phương thức chính của bài:

- `Module.isNativeAccessEnabled()`: **kiểm tra** module có native access enabled hay không; có từ **JDK 22**; không tự cấp quyền.
- `ModuleLayer.Controller.enableNativeAccess(Module)`: **cấp quyền** cho module trong đúng layer của controller; **chính thao tác cấp quyền cũng là restricted**; có từ **JDK 22**.

**Kết luận cần nhớ:** một plugin động không được tự cấp quyền native cho chính mình bằng một setter tùy ý. Quyền này chỉ được bật bởi **launcher/runtime cấu hình cho module** hoặc được **ủy quyền có kiểm soát** qua `ModuleLayer.Controller`, từ code đang có native access. Controller không thể tùy tiện sửa mọi module trong JVM.

### Phiên bản và độ an toàn của ví dụ

- API `Module.isNativeAccessEnabled` và `ModuleLayer.Controller.enableNativeAccess` xuất hiện từ **Java 22**.
- Các ví dụ chạy độc lập trong bài sử dụng **JDK 24+**, vì chúng dùng `--illegal-native-access=deny` để tạo tình huống fail-closed có thể kiểm chứng. Mã module sử dụng API chuẩn JDK 22+, nhưng flag này được đưa vào JDK 24 qua JEP 472.
- Đã biên dịch và chạy trên **JDK 24**. Các output minh họa trạng thái ban đầu, việc restricted operation bị từ chối trước khi cấp quyền, và thành công sau khi cấp quyền.
- Từ JDK 24, mode mặc định đối với một số native access chưa được bật là `warn`; vì vậy “thiếu quyền” có thể **cảnh báo rồi cho thao tác tiếp tục** trong mode warn. Chương trình test **cố ý dùng `deny`** để phân biệt trạng thái đúng/sai và chuẩn bị cho chế độ hạn chế chặt hơn về sau.

### Sau bài này, bạn làm được gì?

1. Xác định module nào đang gọi restricted API, không nhầm class loader với module identity.
2. Kiểm tra quyền bằng `getModule().isNativeAccessEnabled()`.
3. Tạo một named module trong một **dynamic module layer** có controller.
4. Đảm bảo module chủ đã được launcher cấp native access trước khi ủy quyền.
5. Bật quyền đúng module trong layer thông qua `controller.enableNativeAccess(target)`.
6. Xử lý `IllegalCallerException` và `IllegalArgumentException` đúng ngữ cảnh.
7. Phân biệt native access với `exports`, `opens`, `reads` và Java reflection permissions.
8. Thiết kế plugin loader có chính sách tin cậy tối thiểu, không giao controller cho plugin không đáng tin.

## 2. Quyền native là gì và tại sao module cần nó?

Native access bảo vệ **ranh giới an toàn giữa Java runtime và code bên ngoài JVM**. Java không thể chứng minh một địa chỉ native đúng biên, một callback C đúng lifetime hoặc một C ABI declaration là hợp lệ ở mọi thời điểm.

Ví dụ restricted FFM operations từ tài liệu Java 24:

| API/hành động | Vì sao cần native access |
| --- | --- |
| `Linker.downcallHandle(...)` | Gọi function native có thể sử dụng sai prototype hoặc ABI |
| `Linker.upcallStub(...)` | Cho native code giữ/call Java callback; rủi ro lifecycle và signature |
| `MemorySegment.reinterpret(...)` | Có thể nới view vượt kích thước hoặc scope của actual allocation |
| `AddressLayout.withTargetLayout(...)` | Khai báo kích thước vùng mà một native pointer trỏ đến, có thể không thực sự tồn tại |
| `SymbolLookup.libraryLookup(...)` | Tải và tìm native symbols từ thư viện có quyền thực thi machine code |
| `System.load(...)`/`System.loadLibrary(...)` | Tải native code vào tiến trình JVM |
| `ModuleLayer.Controller.enableNativeAccess(...)` | Truyền một quyền restricted cho module khác |
| JNI native method declarations/calls theo chính sách JDK 24 | Chạm tới native runtime ngoài kiểm tra Java thuần |

**Quan trọng:** không phải **mọi** phương thức trong `java.lang.foreign` đều restricted. Chẳng hạn `MemorySegment.ofArray(...)` hoặc `Arena.ofConfined().allocate(...)` có thể được dùng theo Java API bình thường. Nhưng nếu muốn gọi `withTargetLayout` hoặc tạo downcall handle restricted, module gọi method cần native access theo chính sách runtime.

Native access **không phải** “quyền administrator hệ điều hành” và cũng không chứng minh native code lành tính. Nó là **thao tác xác nhận của application owner** rằng module được phép vượt một số ranh giới integrity của JVM. Hệ điều hành vẫn có ACL, sandbox/process permissions và dynamic loader rules riêng.

## 3. Module nào được kiểm tra?

Khi code gọi restricted API, quyền gắn với **module chứa caller**, không phải module của object được truyền vào, tên JAR ngẫu nhiên hay module chứa API của JDK.

```java
Module mine = Example.class.getModule();

System.out.println(mine.getName());              // tên module, có thể null
System.out.println(mine.isNamed());               // true/false
System.out.println(mine.isNativeAccessEnabled()); // true/false
```

Các khái niệm cần phân biệt:

- **Named module:** có module name, thường được định nghĩa từ `module-info.java` trong boot layer hoặc layer động. Ví dụ `demo.host`, `demo.plugin`.
- **Unnamed module:** thường chứa code trên **classpath**. Nhiều class loader có unnamed module riêng. Tùy flag, `--enable-native-access=ALL-UNNAMED` mở quyền cho **tất cả unnamed modules**.
- **ModuleLayer:** tập các named modules được định nghĩa từ một `Configuration` và một hoặc nhiều parent layers.
- **ModuleLayer.Controller:** object nhạy cảm cho phép chủ thể tạo layer thêm read/export/open edges và có `enableNativeAccess` cho modules của layer.
- **ClassLoader:** tải class; **không đồng nghĩa** module hay layer. Một class loader có thể quản lý nhiều named modules, còn một module nằm trong đúng một layer (hoặc những kiểu module đặc biệt ngoài layer).
- **Dynamic named module:** module được định nghĩa ở runtime, ví dụ plugin được đọc từ module path riêng và tạo bằng `ModuleLayer.defineModulesWithOneLoader(...)`.

`Module.getLayer()` trả layer cho named module nếu nó có layer; **unnamed module không nằm trong module layer**, nên không thể lấy một controller rồi tùy tiện enable native access cho unnamed module kiểu đó.

Không có phương thức public tổng quát kiểu `myModule.enableNativeAccess()` mà bất kỳ code nào cũng gọi được để tự nâng quyền. Mẫu có thật trong JDK là `ModuleLayer.Controller.enableNativeAccess(target)` với các giới hạn dưới đây.

## 4. Hai đường cấp quyền: launcher và controller

### 4.1. Cấp quyền ở thời điểm khởi động

Đối với một **named module** có tên `demo.host`:

```bash
java --enable-native-access=demo.host \
     --module-path mods \
     -m demo.host/demo.host.LayerHost
```

Trong module chủ:

```java
Module me = LayerHost.class.getModule();
System.out.println(me.isNativeAccessEnabled()); // true
```

Đối với code trên classpath:

```bash
java --enable-native-access=ALL-UNNAMED -cp out MyMain
```

Mọi unnamed module đều được bật quyền khi dùng `ALL-UNNAMED`. Điều này có thể **rộng hơn mức cần thiết**: một dependency không tin cậy nằm trên classpath cũng được quyền native nếu được nạp ở unnamed module.

**Khuyến nghị cho production:** nếu có thể, di chuyển thành phần cần JNI/FFM vào named module và dùng `--enable-native-access=tên.module` để hạn chế phạm vi; không bật `ALL-UNNAMED` chỉ vì dễ thao tác.

### 4.2. Module được tạo sau khi JVM chạy: controller

Nếu plugin module không được định nghĩa trong boot layer khi JVM khởi động mà chỉ xuất hiện khi plugin manager tạo layer mới, launcher của JVM không có sẵn một target module instance để cấp quyền qua object API.

Khi tạo dynamic layer, có thể giữ `ModuleLayer.Controller` do một trong các factory static methods trả về:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader());

ModuleLayer layer = controller.layer();
Module target = layer.findModule("demo.plugin").orElseThrow();

controller.enableNativeAccess(target);
```

**Tiền điều kiện của `enableNativeAccess`:**

1. Caller đang chạy trong module **đã có native access** (hoặc đang được runtime cho phép theo policy tương ứng; với `deny` thiếu quyền gây `IllegalCallerException`).
2. `target` phải là module **trong chính layer mà controller quản lý**; nếu không, `IllegalArgumentException`.
3. `enableNativeAccess` là **restricted method**, nên hành vi khi caller chưa được bật quyền còn phụ thuộc phiên bản và policy `--illegal-native-access`.
4. Mã chủ nên kiểm tra plugin đáng tin, phiên bản/nguồn artifacts và nhu cầu native trước khi cấp quyền, không làm ngay cho mọi plugin.

Controller có khả năng **ủy quyền** trong layer, không phải quyền “root cấp cho mọi module” của toàn JVM.

## 5. Luồng tin cậy của một plugin loader

Mô hình:

```text
                  JVM startup
                      |
             --enable-native-access=demo.host
                      |
                      v
           module demo.host (trusted)
             native access = true
                      |
              tạo child ModuleLayer
                      |
                      v
           module demo.plugin (new)
             native access = false
                      |
       Check trusted release / allowlist / checksum
                      |
            policy cho phép plugin dùng native?
             /                       \
           NO                         YES
           |                           |
     Không cấp quyền          controller.enableNativeAccess(
     từ chối tác vụ                     target)
     cần native                          |
                                        v
                                plugin native access = true
```

Có hai ranh giới:

- **Ranh giới quyền caller:** host phải có quyền native trước. Plugin **không được dùng controller của host để tự leo thang** khi không được tin tưởng.
- **Ranh giới layer:** controller chỉ có thể quản lý module thuộc **layer do nó tạo**. Nó không thể dùng để thay đổi `java.base` hoặc một arbitrary module trong boot layer.

Với plugin cần native code, cấp quyền là một **quyết định tin cậy** tương tự cho phép native library chạy trong cùng process. Kiểm file signature/hash, nguồn cung ứng, version và thư viện có thể được tải; không trông chờ chỉ một flag bảo vệ trước mã C/C++ độc hại.

## 6. Ví dụ hoàn chỉnh JDK 24+: host có tên tạo và cấp quyền cho plugin động

Ví dụ này dùng **hai named modules**:

- `demo.host`: module chạy trước, được JVM cấp native access bằng launcher flag.
- `demo.plugin`: module được host nạp vào **dynamic layer**, ban đầu không được cấp native access.
- Plugin gọi restricted method `ValueLayout.ADDRESS.withTargetLayout(JAVA_INT)` chỉ để **kiểm tra quyền**; không dereference pointer nên không cần thư viện C hoặc nguy cơ đọc native memory sai.
- Host cố gọi plugin trước khi cấp quyền trong mode `deny`, bắt `IllegalCallerException` qua `InvocationTargetException`, sau đó cấp quyền và gọi lại.

### 6.1. Cây thư mục

```text
native-module-lab/
  src/
    demo.host/
      module-info.java
      demo/host/LayerHost.java
    demo.plugin/
      module-info.java
      demo/plugin/PluginNative.java
  mods/                        # javac tạo
```

Không cần JNI C compiler hay external library, chỉ cần JDK 24+.

### 6.2. File `src/demo.host/module-info.java`

```java
module demo.host {
    // Host không phải requires demo.plugin ở compile time.
    // Plugin chỉ được resolve trong layer tạo tại runtime.
}
```

Việc không thêm `requires demo.plugin` là **có chủ đích**. Nếu host đòi module plugin ngay từ lúc start, plugin có thể bị giải quyết vào boot layer thay vì child layer như mục tiêu bài học.

### 6.3. File `src/demo.plugin/module-info.java`

```java
module demo.plugin {
    exports demo.plugin;
}
```

`exports demo.plugin` cho phép host gọi public method của `demo.plugin.PluginNative` qua reflection bình thường. Native access và Java module exports là **hai cơ chế độc lập**; mở export **không** cấp quyền native.

### 6.4. File `src/demo.plugin/demo/plugin/PluginNative.java`

```java
package demo.plugin;

import java.lang.foreign.ValueLayout;

public final class PluginNative {
    public static long safeProbe() {
        return ValueLayout.ADDRESS
                .withTargetLayout(ValueLayout.JAVA_INT)
                .targetLayout()
                .orElseThrow()
                .byteSize();
    }
}
```

`withTargetLayout` là restricted FFM method; nó gắn layout cho pointer type. `targetLayout().orElseThrow().byteSize()` sẽ là 4 vì `JAVA_INT` biểu diễn giá trị 4 byte.

**Không có dereference** trong demo này; nó chứng minh tính có/không có quyền native, chứ không phải một bài thực hành về native pointer safety.

### 6.5. File `src/demo.host/demo/host/LayerHost.java`

```java
package demo.host;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class LayerHost {
    public static void main(String[] args) throws Exception {
        Module self = LayerHost.class.getModule();

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration config = ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.plugin"));

        ModuleLayer.Controller ctrl =
                ModuleLayer.defineModulesWithOneLoader(
                        config,
                        List.of(ModuleLayer.boot()),
                        ClassLoader.getSystemClassLoader());

        Module target = ctrl.layer()
                .findModule("demo.plugin")
                .orElseThrow();

        Class<?> clazz = ctrl.layer()
                .findLoader("demo.plugin")
                .loadClass("demo.plugin.PluginNative");

        System.out.println("Host access: "
                + self.isNativeAccessEnabled());
        System.out.println("Plugin before: "
                + target.isNativeAccessEnabled());

        // Vì JVM chạy --illegal-native-access=deny,
        // plugin chưa được phép thực hiện restricted operation.
        try {
            clazz.getMethod("safeProbe").invoke(null);
            throw new AssertionError(
                    "Plugin operation unexpectedly succeeded");
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalCallerException)) {
                throw expected;
            }
            System.out.println("Before grant: denied");
        }

        // Host trusted module đã có native access.
        // target thuộc đúng layer của ctrl.
        ctrl.enableNativeAccess(target);

        System.out.println("Plugin after: "
                + target.isNativeAccessEnabled());
        System.out.println("Probe target bytes: "
                + clazz.getMethod("safeProbe").invoke(null));
    }
}
```

Đây là **chương trình đầy đủ**. Nó dùng `ModuleFinder.of(path)` để tìm modular classes, `Configuration.resolve` giải quyết graph, `ModuleLayer.defineModulesWithOneLoader` tạo child layer và trả controller, sau đó tìm **module thật trong child layer**.

**Cần phân biệt:** `LayerHost.class.getModule()` là module chủ, được cấp quyền lúc JVM khởi động; `target` là module `demo.plugin` được tạo động. Nếu chỉ đặt `--enable-native-access=demo.host` mà không có lời gọi controller, **plugin vẫn không được tự động thừa kế** quyền native của host.

### 6.6. Biên dịch

Từ thư mục `native-module-lab`:

```bash
javac --module-source-path src -d mods -m demo.host,demo.plugin
```

Nếu dùng PowerShell trên Windows, cùng lệnh `javac` có thể chạy trực tiếp trong terminal Java/JDK đã cấu hình. Cấu trúc `src/demo.host`, `src/demo.plugin` phải đúng quy tắc `--module-source-path`.

### 6.7. Chạy có quyền của host và policy deny

```bash
java \
  --enable-native-access=demo.host \
  --illegal-native-access=deny \
  --module-path mods \
  -m demo.host/demo.host.LayerHost \
  mods
```

Một dòng cho PowerShell/Windows:

```powershell
java --enable-native-access=demo.host --illegal-native-access=deny --module-path mods -m demo.host/demo.host.LayerHost mods
```

**Stdout đã thực thi trên JDK 24:**

```text
Host access: true
Plugin before: false
Before grant: denied
Plugin after: true
Probe target bytes: 4
```

### 6.8. Đọc kết quả theo thứ tự

1. `Host access: true` vì module `demo.host` được chỉ định ở launcher.
2. `Plugin before: false` vì plugin nằm trong dynamic layer mới, chưa được controller cấp quyền.
3. Trong mode `deny`, restricted `withTargetLayout` từ plugin chưa có native access ném `IllegalCallerException`; reflection bọc nó thành `InvocationTargetException`, host bắt **đúng nguyên nhân**.
4. `ctrl.enableNativeAccess(target)` được gọi từ module chủ đã có quyền; module `target` là thành viên layer này nên grant thành công.
5. `Plugin after: true` phản ánh trạng thái native access vừa được bật cho plugin module.
6. Gọi `safeProbe` lần hai hoạt động, trả 4 bytes theo `JAVA_INT` layout.

Với trường hợp kiểm tra quyền thật, có thể đặt logic `isNativeAccessEnabled` **ngay trong plugin** để chẩn đoán thân thiện trước khi gọi FFM:

```java
Module me = PluginNative.class.getModule();
if (!me.isNativeAccessEnabled()) {
    throw new IllegalStateException("Native access is not enabled");
}
```

Snippet này cần đặt **trong class PluginNative**, không chạy độc lập. Một phép check như vậy cung cấp thông điệp tốt nhưng **không tự cấp quyền**.

## 7. Điều gì xảy ra nếu host không có quyền native?

Hãy bỏ flag `--enable-native-access=demo.host` nhưng giữ `--illegal-native-access=deny`:

```bash
java --illegal-native-access=deny \
  --module-path mods \
  -m demo.host/demo.host.LayerHost \
  mods
```

Trong trường hợp đó:

- `LayerHost.class.getModule().isNativeAccessEnabled()` là `false`.
- `demo.plugin` cũng chưa được cấp quyền.
- Plugin restricted probe bị từ chối.
- Khi code host gọi `ctrl.enableNativeAccess(target)`, **bản thân grant là restricted**, và caller không được bật native access; dưới mode `deny`, nó ném `IllegalCallerException`.

Không thể dùng controller của plugin để tạo “đường vòng” cấp quyền khi module chủ bị từ chối. Đây là cách giữ nguyên mô hình ủy quyền: **chủ thể chưa được cho phép không thể hợp lệ cấp quyền cho chủ thể khác** trong chế độ nghiêm ngặt.

**Lưu ý về JDK 24 mode `warn`:** tài liệu JEP 472 cho biết restricted operations chưa được cấp quyền có thể chỉ cảnh báo và vẫn thực thi. Trong thử nghiệm với JDK 24 `--illegal-native-access=warn`, một lời gọi `enableNativeAccess` từ module chủ chưa bật quyền **đã phát warning nhưng vẫn hoàn tất**. Vì vậy **đừng lấy hành vi warn làm cơ chế cấp quyền an toàn trong production**. Dùng `deny` trong CI để bắt thiếu quyền và lên kế hoạch chuyển sang mode nghiêm ngặt trong các bản JDK về sau.

### 7.1. Phân biệt ba trạng thái khác nhau

| Tình trạng | `isNativeAccessEnabled()` | Restricted operation ở JDK 24 mode `deny` |
| --- | --- | --- |
| Host có quyền qua launcher | `true` | Có thể gọi `Controller.enableNativeAccess` cho đúng target |
| Plugin chưa được grant | `false` | Ném `IllegalCallerException` khi tự gọi restricted FFM method |
| Plugin đã được grant qua controller | `true` | Có thể thực hiện restricted method, nhưng vẫn phải tuân thủ ABI/lifetime |

Trong mode `warn`, một module có thể vẫn báo `false` và restricted operation có thể được thực thi kèm cảnh báo. Do vậy `isNativeAccessEnabled()` phản ánh **cấp quyền chính thức**, không phải dự đoán tuyệt đối rằng lệnh kế tiếp có bị fail hay không dưới tất cả warning policies.

## 8. Giới hạn layer: không được cấp quyền cho module ngoài controller

Theo API `ModuleLayer.Controller.enableNativeAccess(Module)`:

- Nếu `target` không nằm trong layer mà controller quản lý: `IllegalArgumentException`.
- Nếu caller chưa có native access và restricted operation bị từ chối: `IllegalCallerException`.
- Nếu `target == null`: `NullPointerException` theo contract chung của controller.
- Một controller của layer plugin **không** phải controller của boot layer và không thể cấp quyền cho arbitrary boot modules, ví dụ `java.base`.

Ví dụ kiểm tra sai layer:

```java
Module javaBase = Object.class.getModule();

try {
    ctrl.enableNativeAccess(javaBase);
    throw new AssertionError("Unexpected grant");
} catch (IllegalArgumentException expected) {
    System.out.println("Other layer: rejected");
}
```

Snippet giả định `ctrl` đang là controller của **dynamic child layer**, caller **đã có** native access. Nếu caller cũng thiếu quyền, policy và thứ tự kiểm tra có thể ảnh hưởng exception trước tiên; không dùng code đó làm phép thử khi cả hai điều kiện đều sai.

**Đã kiểm chứng trên JDK 24** với host có quyền: truyền `Object.class.getModule()` (thuộc `java.base` ở boot layer) vào controller của child layer bị từ chối và in:

```text
Other layer: rejected
```

Nhờ vậy, có thể thiết kế plugin manager rõ ownership: controller cho layer A không thể được dùng để cập nhật layer B chỉ vì tên module tương tự.

## 9. Ví dụ thứ hai: host chạy trên classpath và ca kiểm thử không có quyền

Trong ví dụ named host, việc cấp quyền chọn lọc là tối ưu. Để test trực tiếp tình huống **caller chưa được launcher cấp quyền**, có thể chạy một host thuộc unnamed module rồi so sánh hai modes.

Ở classpath, module chủ có `getName() == null`. Nếu dùng:

```bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny ...
```

thì host có quyền native, còn dynamic named plugin vẫn có thể **chưa** có quyền. Đây là bằng chứng native access **không tự kế thừa qua classloader hoặc parent layer**.

Trên JDK 24, một test host classpath với module plugin động đã cho hai kết quả:

**Có `--enable-native-access=ALL-UNNAMED`:**

```text
Host native access: true
Actual module matches: true
Dynamic before: false
Before grant: denied
Dynamic after: true
Restricted target bytes: 4
Other layer: rejected
```

**Không có `--enable-native-access`, giữ `--illegal-native-access=deny`:**

```text
Host native access: false
Actual module matches: true
Dynamic before: false
Before grant: denied
Grant denied: caller has no native access
Other layer: rejected
```

Hai transcript trên là kết quả test Java 24 với host code dùng `ModuleLayer.defineModulesWithOneLoader` và cùng restricted `withTargetLayout` ở plugin; chúng là **biến thể của ví dụ**, không phải stdout của `LayerHost` named module ở mục 6.

**Không nhầm:** `--enable-native-access=ALL-UNNAMED` mở cho tất cả code classpath, chứ **không** tự bật native access của `demo.plugin` có tên nằm trong dynamic layer. Với production nhiều dependencies, hãy ưu tiên `demo.host` named module thay vì ALL-UNNAMED.

## 10. Tương tác với chế độ hạn chế native trên các phiên bản JDK

### 10.1. Java 22 và 23

`Module.isNativeAccessEnabled` và `Controller.enableNativeAccess` có từ JDK 22. FFM chuẩn được hoàn thiện trong cùng JDK. Tuy nhiên option `--illegal-native-access` và cảnh báo JNI được phát triển trong JDK 24 theo JEP 472; không chạy nguyên lệnh ví dụ JDK 24 có `--illegal-native-access=deny` trên JDK 22/23 rồi tưởng chương trình lỗi do source Java.

Trên JDK 22/23, kiểm tra behavior phù hợp với policy được tài liệu hóa cho phiên bản đang dùng; việc cấp quyền native qua `--enable-native-access` vẫn là cơ chế launcher chủ đạo.

### 10.2. Java 24: warn/deny rõ ràng

JEP 472 thống nhất việc hạn chế JNI và FFM:

- `--illegal-native-access=allow`: cho restricted operation chưa có quyền tiếp tục.
- `--illegal-native-access=warn`: cho thực thi nhưng cảnh báo; mặc định ở JDK 24.
- `--illegal-native-access=deny`: từ chối bằng `IllegalCallerException`, thích hợp cho test fail-closed và phát hiện module thiếu quyền.

Tài liệu mô tả `deny` trở thành mặc định trong một bản phát hành tương lai; **không tự kết luận mặc định của mọi JDK mới chỉ từ hành vi JDK 24**. Kiểm tra document cho đúng Java runtime đang triển khai.

### 10.3. Có thể cấu hình ở đâu?

Ví dụ với named module:

```bash
java --enable-native-access=demo.host -m demo.host/demo.host.LayerHost
```

Có thể chuyển option vào launcher arguments, `JDK_JAVA_OPTIONS`, argument file, hoặc cấu hình `jlink` runtime image. Manifest `Enable-Native-Access: ALL-UNNAMED` có trong kịch bản executable JAR, nhưng là **phạm vi rộng**. Không tự sửa command line của khách hàng hoặc cấu hình runtime chỉ để dập cảnh báo mà không đánh giá rủi ro.

**Không trộn với `--enable-preview`:** native access và preview language/API features là hai cơ chế khác nhau.

## 11. Phân biệt native access với opens, exports và reads

Module system có những quyền riêng:

| API/flag | Mục đích | Có cấp quyền restricted native? |
| --- | --- | --- |
| `requires`/`Module.addReads` | Thiết lập readability edge giữa modules | Không |
| `exports`/`Module.addExports` | Cho module khác truy cập public types của package | Không |
| `opens`/`Module.addOpens` / `--add-opens` | Cho phép deep reflection tới package trong điều kiện nhất định | Không |
| `--add-exports` | Export package cụ thể tại launcher | Không |
| `--enable-native-access` | Bật native access cho module(s) được chỉ định | Có |
| `ModuleLayer.Controller.enableNativeAccess` | Bật native access cho target module trong dynamic layer đúng phạm vi | Có, nhưng chính method bị restricted |
| `Module.isNativeAccessEnabled` | Đọc trạng thái native access | Không thay đổi quyền |

Ví dụ `module demo.plugin { exports demo.plugin; }` cho phép host gọi `PluginNative.safeProbe()` qua reflection, nhưng lần đầu vẫn bị `IllegalCallerException` ở `withTargetLayout` khi policy là deny.

Ngược lại, bật native access **không tự mở** private fields hoặc packages của plugin cho host. Nếu host gặp `IllegalAccessException` khi reflection, sửa module exports/opens theo chính sách kiến trúc thay vì thêm `--enable-native-access`.

Tương tự, `controller.addReads` và `controller.addOpens` có thể có tác dụng riêng trong plugin loader, nhưng **không thay thế** `enableNativeAccess`.

## 12. Kiểm tra quyền trong plugin trước khi thực hiện native operation

Một wrapper có thể chủ động cung cấp diagnostic:

```java
public static void requireNativeAccess(Class<?> owner) {
    Module module = owner.getModule();

    if (!module.isNativeAccessEnabled()) {
        String name = module.isNamed()
                ? module.getName()
                : "ALL-UNNAMED";

        throw new IllegalStateException(
                "Native access is not enabled for " + name);
    }
}
```

Đây là **method minh họa**, cần đặt trong class của ứng dụng. `owner` nên là class thực sự chứa code gọi restricted FFM/JNI operation. Không tin vào một tên module do user nhập chỉ vì nó giống module cần quyền.

Quy trình đúng:

1. Kiểm tra chính xác module của caller.
2. Nếu chưa được bật, dừng theo chính sách sản phẩm hoặc yêu cầu host cấp quyền chính thức.
3. Với dynamic module đã xác minh tin cậy, host đã có native access mới gọi `controller.enableNativeAccess`.
4. Sau cấp quyền, có thể gọi `isNativeAccessEnabled` lại để xác nhận trạng thái.
5. Native operation thực tế vẫn phải xử lý library load, FFM descriptor, exceptions, ABI, memory lifetime và ownership.

Đừng gọi một restricted operation rồi bất chấp mọi warnings/`IllegalCallerException` bằng cách lặp lại hoặc reflection hack. Hướng sửa là **cấp đúng quyền cho đúng module bằng kênh chính thức**.

### 12.1. isNativeAccessEnabled không chứng minh native code an toàn

Một module có `isNativeAccessEnabled() == true` vẫn có thể:

- Dùng `MemorySegment.reinterpret` sai kích thước và truy cập vùng nhớ đã free.
- Tạo `Linker.downcallHandle` với sai C calling convention.
- Nạp DLL/so không đúng kiến trúc hoặc phiên bản.
- Gọi JNI native code phá heap.
- Có quyền OS không đủ để mở file, socket, thiết bị hay attach debugger.

Native access là **authorization to perform risky operations**, không phải chứng nhận ABI, provenance hoặc lifecycle correctness.

## 13. Tại sao không đưa Controller cho code không tin cậy?

Javadoc `ModuleLayer.Controller` có API note: cần cẩn trọng và **không chia sẻ Controller với untrusted code**. Lý do gồm:

- `enableNativeAccess` có khả năng lan truyền quyền restricted từ caller được ủy quyền.
- `addReads`/`addExports`/`addOpens` thay đổi module graph, có thể vô tình mở API nội bộ.
- Một plugin được cung cấp chính controller có thể yêu cầu host tạo/cấp quyền cho modules mà chính sách sản phẩm không duyệt.
- Cấp quyền native theo **module**, không theo từng phương thức. Một khi được bật, mọi code trong module đó có khả năng gọi restricted methods theo điều kiện runtime, không chỉ một entrypoint.

Mẫu kiến trúc tốt:

```text
Trusted PluginManager
  - giữ controller private
  - xác minh plugin identity / release manifest
  - duyệt allowlist native permissions
  - xác định target Module từ controller.layer()
  - gọi enableNativeAccess chính nó
  - chỉ trả interface đã giới hạn cho plugin

Untrusted plugin
  - không giữ controller
  - không quyết định cấu hình native của module khác
  - không tự thay đổi loader policy
```

**Đừng nhầm với sandbox mạnh:** một plugin đã được cấp native access có thể thực thi native code phá vỡ memory safety của JVM. Với plugin thật sự không đáng tin, module boundary/Controller không thay thế **cách ly process hoặc hệ thống sandbox OS**. Hãy chạy code không tin cậy ở process riêng với quyền hạn hạn chế nếu cần cách ly nghiêm ngặt.

### 13.1. Có revoke native access sau khi đã bật không?

`ModuleLayer.Controller` có `enableNativeAccess(Module)` nhưng **không công bố phương thức đảo ngược để revoke ngay** trong API JDK 24. Đừng xây plugin manager với giả định có thể “enable một lúc rồi disable lại” cho cùng module.

Nếu cần quyền native chỉ trong một giai đoạn ngắn, cân nhắc kiến trúc process riêng và lifecycle process, hoặc chỉ load các plugins được duyệt cố định. Không dựa vào `ModuleLayer` GC làm cơ chế bảo mật/revocation.

### 13.2. Không cấp quyền cho nhiều modules chỉ vì chung classloader

Một controller có thể định nghĩa nhiều modules trong cùng loader. Gọi `enableNativeAccess(pluginA)` **không phải** một lệnh mở quyền cho toàn bộ loader hoặc module layer. Cấp cho module **cụ thể** sau khi kiểm tra:

```java
Module selected = ctrl.layer().findModule("demo.plugin")
        .orElseThrow();

if (policyAllowsNative(selected)) { // pseudocode policy của ứng dụng
    ctrl.enableNativeAccess(selected);
}
```

`policyAllowsNative` là hàm ứng dụng tự viết; đoạn code trên là **pseudocode**, không phải chương trình Java tự chạy. Mọi quyết định cần dựa trên identity thực của module và artifact được xác thực, không chỉ tên string nếu tên có thể bị plugin giả mạo.

## 14. Phân biệt module động, proxy động và unnamed module

Cụm từ “module động” thường bị hiểu sai:

- **Dynamic module layer:** dùng `ModuleFinder`/`Configuration`/`ModuleLayer.defineModules*` để tạo **named module** ở runtime. Đây là trường hợp hỗ trợ bởi `ModuleLayer.Controller.enableNativeAccess`.
- **Dynamic proxy class:** `Proxy.newProxyInstance` có thể tạo class trong dynamic module, nhưng quyền native không thể được cấp tùy ý cho một module do runtime quản lý mà controller của bạn không sở hữu. Không assume bất kỳ “module động” nào cũng có controller của application.
- **Unnamed classpath module:** không có tên/layer như named module. Cấp quyền qua launcher `ALL-UNNAMED`, không thông qua controller layer của plugin.
- **Boot layer module:** do JVM launcher resolve; native access thường cấp từ launcher options. Không lấy controller của một child layer để thay đổi boot layer.

Một module có tên `demo.plugin` trong child layer và một module cùng tên ở layer khác (nếu cấu hình cho phép) **không phải cùng Module object**. Đừng lookup bằng string trên layer A rồi dùng controller B.

## 15. Lỗi thường gặp khi viết plugin loader

| Triệu chứng | Nguyên nhân phổ biến | Cách sửa |
| --- | --- | --- |
| `Plugin before: false` dù host có native access | Quyền không tự kế thừa sang dynamic named module | Host gọi `enableNativeAccess` cho đúng target |
| `IllegalCallerException` ở `enableNativeAccess` | Caller chưa enabled và runtime đang deny | Cấp quyền cho host bằng launcher, không bypass |
| `IllegalCallerException` ở FFM restricted method trong plugin | Plugin chưa được enabled | Cấp cho plugin qua đúng controller trước khi gọi |
| `IllegalArgumentException` ở `enableNativeAccess` | Target không thuộc layer do controller quản lý | Lấy module từ `controller.layer()` |
| `NoSuchElementException` khi `findModule` | Plugin không được resolve vào layer hoặc sai tên | Kiểm `ModuleFinder`/`Configuration` |
| `FindException` / `ResolutionException` | Module descriptor/dependencies lỗi | Sửa module graph hoặc module path |
| `LayerInstantiationException` | Lỗi định nghĩa layer, loader/packages | Kiểm ModuleLayer factory constraints |
| `ClassNotFoundException` khi load class plugin | Sai class name/module path/class loader | `layer.findLoader(moduleName)` |
| `IllegalAccessException` khi reflect | Package của plugin chưa export/open phù hợp | Sửa `exports`/`opens`, không nhầm native access |
| Mở `--add-opens` nhưng native vẫn denied | Deep reflection != native access | Dùng `--enable-native-access`/controller |
| Chạy JDK 22 và JVM không hiểu `--illegal-native-access` | Flag này là JDK 24+ | Đọc docs theo JDK, dùng đúng command line |
| JDK 24 mặc định chỉ warning khi thiếu quyền | `warn` mode vẫn có thể thực thi | Test với `--illegal-native-access=deny` |
| Bật `ALL-UNNAMED` nhưng named plugin vẫn chưa có quyền | ALL-UNNAMED chỉ dành cho unnamed modules | Dùng controller với dynamic named module |
| Module đã bật native nhưng vẫn `UnsatisfiedLinkError` | Library không tìm thấy, arch/deps sai | Kiểm OS loader, native library path/ABI |
| Module đã bật native nhưng C code crash | ABI, pointer hoặc lifetime không đúng | Kiểm FFM/JNI và native code, không chỉ flag |
| Controller bị lộ ra ngoài host | Untrusted code có thể yêu cầu thay đổi module graph/quyền | Giữ controller private và duyệt policy |
| Muốn revoke sau khi enable | API không công bố revoke | Dùng process isolation/lifecycle khác |

## 16. Checklist để review một lời gọi enableNativeAccess

1. Caller nằm trong module nào? Có dùng `callerClass.getModule()` để xác minh chính xác?
2. `isNativeAccessEnabled()` của host có true ở mode **deny** sau launcher configuration?
3. Module plugin là **named module mới** trong đúng dynamic layer? Có trùng tên/hệ lớp khác không?
4. Controller có được giữ bởi trusted host, không trả cho plugin hoặc user code?
5. `target` lấy từ `controller.layer().findModule(...)` hay một module object ở layer khác?
6. `ModuleFinder` và `Configuration` có đọc đúng plugin binary/JAR và dependency graph không?
7. Plugin artifact có signature/checksum hoặc allowlist được kiểm chứng trước khi cấp quyền?
8. Có chắc plugin thực sự **cần** FFM/JNI native access, không phải chỉ Java reflection/export?
9. Quyền chỉ bật cho module được duyệt, không tự bật mọi module trong layer?
10. CI có chạy `--illegal-native-access=deny` để phát hiện lỗi ẩn bởi warning mode?
11. Có bài test negative cho host thiếu quyền, target sai layer, plugin chưa được cấp quyền?
12. Native libraries cũng được kiểm provenance/ABI/ownership và không phải các file DLL/so ngẫu nhiên?
13. Tài liệu triển khai có ghi rõ `--enable-native-access=host.module` và các JDK versions?
14. Có phương án nếu muốn thu hồi quyền? Đừng nhầm module-unload/GC với secure revoke.

## 17. Bài tập tự kiểm tra

**Câu 1.** `Module::isNativeAccessEnabled` có tự cấp quyền không?

**Đáp án:** Không. Nó chỉ trả trạng thái native access của module hiện tại, không thay đổi quyền. Cấp quyền cho dynamic named module dùng `ModuleLayer.Controller.enableNativeAccess` theo điều kiện của API.

**Câu 2.** Host được cấp `--enable-native-access=demo.host` và tạo module `demo.plugin` trong child layer. Plugin được bật sẵn không?

**Đáp án:** Không. Module mới không tự thừa kế native access của host; trong ví dụ đã thực thi `Plugin before: false`.

**Câu 3.** Caller không có native access, gọi `enableNativeAccess` trong JDK 24 mode `deny` thì sao?

**Đáp án:** `IllegalCallerException`. Phải được launcher cấp quyền trước; controller không phải đường tự nâng quyền hợp lệ.

**Câu 4.** Controller của layer plugin có thể cấp native access cho `java.base` trong boot layer không?

**Đáp án:** Không. `target` không nằm trong layer, nên `IllegalArgumentException` trong trường hợp caller đã có quyền.

**Câu 5.** `--enable-native-access=ALL-UNNAMED` có bật một named plugin trong dynamic layer không?

**Đáp án:** Không tự động. Flag ấy áp dụng cho unnamed modules, còn named plugin phải được cấp quyền riêng theo cơ chế phù hợp.

**Câu 6.** JDK 24 ở mode `warn` có thể thực thi restricted operation dù `isNativeAccessEnabled()==false` không?

**Đáp án:** Có. Đó là chế độ cho phép illegal native access cùng warning. Không dùng mode warn để kết luận plugin đã được ủy quyền chính thức; CI nên dùng `deny`.

**Câu 7.** Tại sao plugin `safeProbe` chỉ dùng `withTargetLayout` mà không gọi native C function?

**Đáp án:** Vì `withTargetLayout` đã là restricted API, đủ để kiểm tra quyền native; không cần tải C library hoặc dereference một pointer nguy hiểm. Kết quả target bytes 4 là kết quả layout hợp lệ.

**Câu 8.** Cho phép `--add-opens=demo.plugin/demo.plugin=demo.host` đã cấp native access cho plugin chưa?

**Đáp án:** Chưa. `opens` chỉ điều chỉnh reflection access tới package; native access là cơ chế riêng.

**Câu 9.** Có nên đưa `ModuleLayer.Controller` cho plugin không tin cậy tự cấu hình?

**Đáp án:** Không. Controller cho phép chỉnh module graph và cấp native access. Giữ trong host và áp dụng allowlist/provenance trước khi grant.

**Câu 10.** Nếu đã bật native access, JVM có bảo đảm một `MemorySegment.reinterpret` với sai lifetime an toàn không?

**Đáp án:** Không. Quyền native chỉ cho phép restricted operation; người viết vẫn chịu trách nhiệm memory safety, alignment, size và lifetime.

**Câu 11.** Sau khi cấp quyền native cho module plugin, có API `disableNativeAccess` tương ứng để thu hồi ngay không?

**Đáp án:** Không có revoke tương ứng trong `ModuleLayer.Controller` JDK 24. Nếu yêu cầu cách ly hoặc thu hồi mạnh, dùng process boundary và lifecycle quản lý phù hợp.

**Câu 12.** Nếu `java -m demo.host/...` fail khi không thấy plugin class, có nên thêm native access flag để sửa?

**Đáp án:** Không. Kiểm module path, resolver, class loader, `exports`/`opens`. Chỉ cấp native access nếu lỗi thực sự liên quan restricted JNI/FFM operation.

## 18. Tổng kết

- `Module.isNativeAccessEnabled()` **kiểm tra** trạng thái quyền native của một module; có từ JDK 22.
- `ModuleLayer.Controller.enableNativeAccess(target)` **cấp quyền** cho module **trong đúng layer của controller**, nhưng **chính nó cũng restricted**.
- **Caller phải có native access** để cấp quyền một cách hợp lệ trong chế độ fail-closed; dùng launcher `--enable-native-access=demo.host` cho trusted host, rồi controller grant vào child layer.
- Module plugin mới **không tự kế thừa quyền native** của host, dù dùng class loader liên quan. `ALL-UNNAMED` cũng không tự mở cho named plugin.
- Trong **JDK 24**, mode mặc định `warn` có thể cho illegal operation chạy kèm warning; đặt `--illegal-native-access=deny` để phát hiện lỗi và kiểm thử đúng ranh giới ủy quyền.
- Native access **khác** `reads/exports/opens` và không thay thế kiểm chứng native library, ABI, memory lifetime hay sandbox.
- Controller là object nhạy cảm; chỉ trusted host giữ quyền cấp, **không chia sẻ với plugin không tin cậy**. Không có revoke tương ứng trong API controller JDK 24.

## Tài liệu tham khảo chính thức

- [Java SE 24 — Module.isNativeAccessEnabled](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Module.html#isNativeAccessEnabled())
- [Java SE 24 — ModuleLayer.Controller.enableNativeAccess](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.Controller.html#enableNativeAccess(java.lang.Module))
- [Java SE 24 — ModuleLayer và các factory định nghĩa layer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 24 — Restricted Methods và native-access configuration](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html)
- [Java SE 24 — Danh sách restricted methods](https://docs.oracle.com/en/java/javase/24/docs/api/restricted-list.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454)
- [Java SE 24 — java launcher options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)

**Ghi nhớ:** quyền native cho module động được **kiểm tra qua Module**, và khi cần được **cấp bằng Controller của chính layer** từ **caller đã được ủy quyền**. Không nhầm cảnh báo trong JDK 24 với quyền chính thức, không lạm dụng ALL-UNNAMED và không coi quyền native là bằng chứng mã C/JNI/FFM an toàn.
