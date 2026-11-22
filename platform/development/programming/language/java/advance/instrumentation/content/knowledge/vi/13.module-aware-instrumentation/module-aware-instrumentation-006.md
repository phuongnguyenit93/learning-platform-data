# Bổ sung `uses`, `provides` và kiểm tra điều kiện dịch vụ trong Java Instrumentation

**Bối cảnh:** Khi một Java agent instrument ứng dụng chạy trên **Java Platform Module System (JPMS)**, đôi khi code mới cần gọi `ServiceLoader` từ một **named module** vốn không khai báo `uses`, hoặc công cụ muốn làm một provider trong **named module khác** được phát hiện mà không chỉnh sửa file `module-info.java` trên đĩa. Java Instrumentation cung cấp `Instrumentation.redefineModule(...)` với hai đối số đặc biệt: **`extraUses`** và **`extraProvides`**.

Hai đối số này giải quyết **hai phía khác nhau của hợp đồng dịch vụ**:

- **`extraUses`** bổ sung *service dependence* cho **module tiêu thụ dịch vụ** (*consumer*): module này được phép sử dụng một service type khi thực hiện `ServiceLoader.load(...)` từ code trong chính module đó.
- **`extraProvides`** bổ sung *service provider* cho **module chứa implementation** (*provider module*): công bố một hoặc nhiều lớp implementation **thuộc chính module ấy** cho một service type.
- **Hai điều kiện không thay thế nhau.** Consumer có `uses` mà chưa có provider có thể nhận danh sách rỗng; provider có `provides` mà consumer chưa có `uses` vẫn có thể bị `ServiceConfigurationError`.
- **Khả năng nhìn thấy service type và sự tồn tại của provider** còn phụ thuộc module resolution, `requires`/`reads`, package exports, class loaders và quy tắc khởi tạo provider.

Bài học này tập trung vào **`Instrumentation và module`**, không phải thay bytecode method. Nó giải thích điều kiện đúng của JPMS service, các hợp đồng API cần bảo toàn và một ví dụ **Java 17+ biên dịch/chạy được** với ba named modules cùng một Java agent, chứng minh **cả bốn trường hợp `none` / `uses` / `provides` / `both`**.

## 1. Service trong JPMS: có consumer và provider

Trong Java, service thường là một interface hoặc abstract class. Consumer không cần tạo trực tiếp implementation; thay vào đó sử dụng **`ServiceLoader`** để tìm provider phù hợp.

Ví dụ service:

~~~java
package svc.api;

public interface Greeting {
    String greet();
}
~~~

Provider:

~~~java
package svc.provider;

import svc.api.Greeting;

public final class FastGreeting implements Greeting {
    public FastGreeting() { }

    @Override
    public String greet() {
        return "hello";
    }
}
~~~

Consumer:

~~~java
ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
String message = loader.findFirst()
        .map(Greeting::greet)
        .orElse("<none>");
~~~

Các đoạn trên chưa phải toàn bộ dự án; service và implementation là các file `.java` độc lập, còn consumer fragment nằm trong một method đã import `java.util.ServiceLoader` và `svc.api.Greeting`.

Ở **named modules**, có ít nhất hai loại khai báo module descriptor khác nhau:

~~~java
// module tiêu thụ, ví dụ svc.consumer/module-info.java
module svc.consumer {
    requires svc.api;
    uses svc.api.Greeting;
}
~~~

~~~java
// module cung cấp, ví dụ svc.provider/module-info.java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.FastGreeting;
}
~~~

- `requires svc.api`: module đọc module chứa service type. Trong ví dụ API module **export** package `svc.api`.
- `uses svc.api.Greeting`: module có **service dependence** khi code trong module gọi `ServiceLoader`.
- `provides svc.api.Greeting with ...`: module thông báo một hoặc nhiều provider implementations cho cơ chế discovery.
- **`requires` khác `uses`**: một module có thể đọc interface nhưng chưa được phép gọi `ServiceLoader` cho interface đó.
- **`uses` khác `provides`**: module khai báo sử dụng không nhất thiết chứa implementation; module cung cấp không nhất thiết phải sử dụng service.

Việc provider class nằm trong một JAR trên module path **chưa đủ** nếu module chưa được resolve hoặc không có registration phù hợp. Ngược lại, `uses` là quyền/cam kết của **caller module**, không tự tạo provider nào.

## 2. `redefineModule`: năm nhóm bổ sung runtime

Chữ ký API của Java 9+:

~~~java
void redefineModule(
        Module module,
        Set<Module> extraReads,
        Map<String, Set<Module>> extraExports,
        Map<String, Set<Module>> extraOpens,
        Set<Class<?>> extraUses,
        Map<Class<?>, List<Class<?>>> extraProvides);
~~~

Đây là chữ ký API. `Instrumentation inst` được JVM truyền cho Java agent trong `premain` hoặc `agentmain`, chứ không phải do ứng dụng tự `new`.

| Tham số | Nội dung được bổ sung | Ví dụ |
|---|---|---|
| `module` | Module **được thay đổi runtime graph** | `svc.consumer` hoặc `svc.provider` |
| `extraReads` | Các module mà `module` được phép **đọc** | Thêm `svc.api` nếu chưa có cạnh đọc phù hợp |
| `extraExports` | Package của **chính `module`** export tới những module nhất định | Mở khả năng truy cập public types |
| `extraOpens` | Package của **chính `module`** open tới những module nhất định | Cho phép deep reflection có kiểm soát |
| `extraUses` | Service types mà **`module` sử dụng** | `Set.of(Greeting.class)` ở consumer |
| `extraProvides` | Bản đồ service type → danh sách provider classes **thuộc `module`** | `Map.of(Greeting.class, List.of(FastGreeting.class))` ở provider |

Các collection không được dùng có thể đưa **`Set.of()` / `Map.of()`**, nhưng **không được truyền `null`**. Phải hiểu rõ **đúng module được sửa**: `extraUses` thông thường gắn vào **consumer module**, còn `extraProvides` gắn vào **provider module**, không tự động gộp cả hai vào module chứa agent.

**Điều cốt lõi về bản chất thao tác:**

1. `redefineModule` **chỉ mở rộng** reads/exports/opens/uses/provides, **không xóa bớt** những quan hệ đã có.
2. Một lần gọi với collection rỗng cho mọi phần bổ sung không tạo thay đổi nào đáng kể.
3. Gọi đối với **unnamed module** là **no-op**. `isModifiableModule(unnamed)` vẫn luôn `true`, nhưng điều đó **không có nghĩa** bạn có thể bổ sung provider qua `redefineModule` trên unnamed module và trông chờ nó hoạt động.
4. API có thể được gọi đồng thời bởi nhiều agent; cần thiết kế để không phụ thuộc giả định mọi agent sửa module theo thứ tự bạn mong muốn.
5. Đây là thay đổi **động của Module runtime**, không biên dịch lại hay sửa file `module-info.class` trên đĩa. Đừng dùng `Module.getDescriptor()` như nguồn duy nhất để hỏi tình trạng `uses` đã bổ sung động.
6. Không cần khai báo `Can-Retransform-Classes` hoặc `Can-Redefine-Classes` chỉ để gọi `redefineModule`; những manifest capabilities đó dành cho thao tác lớp. Tuy vậy module đích phải **modifiable**.

## 3. `extraUses`: cho consumer có service dependence

Giả sử consumer module `svc.consumer` có:

~~~java
module svc.consumer {
    requires svc.api;
    // Chưa có uses svc.api.Greeting;
}
~~~

Từ code bên trong `svc.consumer`, gọi:

~~~java
ServiceLoader.load(Greeting.class);
~~~

có thể ném **`ServiceConfigurationError`** vì module caller **không tuyên bố sử dụng service**. Vấn đề không được giải quyết chỉ bằng `requires svc.api`; `requires` làm module đọc được API, còn `uses` biểu thị service dependence.

Agent có thể thêm `uses` cho consumer:

~~~java
inst.redefineModule(
        consumerModule,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(serviceClass),
        Map.of());
~~~

Đoạn trên là fragment trong callback agent, với `Instrumentation inst`, `Module consumerModule`, `Class<?> serviceClass` đã được xác định. Đây **không phải đoạn độc lập có thể chạy ngay**.

Sau lời gọi hợp lệ, kiểm tra bằng:

~~~java
boolean allowed = consumerModule.canUse(serviceClass);
System.out.println(allowed);
~~~

`Module.canUse(Class<?>)` phản ánh **service dependence ở runtime**; đây là phép kiểm tra đúng để xác nhận module có quyền dùng service. Nó hữu ích hơn việc chỉ nhìn file `module-info.java` trên đĩa, vì runtime graph đã được bổ sung.

**Cẩn thận với module caller:** `ServiceLoader.load(Greeting.class)` phải được gọi **từ code của named module tiêu thụ** để bài kiểm tra `uses` phản ánh đúng module đó. Nếu đem cùng câu lệnh vào Java agent chạy trong **unnamed module**, `ServiceLoader` kiểm tra **module của caller là agent**, không phải consumer đang instrument. Unnamed module được phép dùng service theo quy tắc khác, nên phép thử có thể báo thành công và che mất việc thiếu `uses` của consumer.

### `extraUses` không tự làm service type accessible

Đặc tả `Instrumentation.redefineModule` nói rõ **agent phải tự đảm bảo service type được truy cập hợp lệ tại mỗi instrumentation site**. API **không tự kiểm tra** service type nằm trong module được sửa hay ở package đã export từ module mà consumer có thể đọc.

Ví dụ consumer có `extraUses = Set.of(Greeting.class)` nhưng không đọc module định nghĩa `Greeting` hoặc package `svc.api` không export phù hợp. Khi instrumentation chèn lời gọi tới `Greeting` trong bytecode consumer, JVM vẫn có thể gặp lỗi **readability, class resolution hoặc accessibility**.

**Điều kiện hợp lệ cho ví dụ cuối bài:**

- `svc.api` được resolve và định nghĩa `svc.api.Greeting`.
- `svc.api/module-info.java` có `exports svc.api;`.
- `svc.consumer/module-info.java` có `requires svc.api;`.
- Agent gọi `extraUses` với **đúng đối tượng `Class<?>` của `svc.api.Greeting`**.
- Consumer gọi `ServiceLoader` trong chính module `svc.consumer`.

`extraUses` không tự thêm `requires`, không tự `extraReads`, và không tự export package. Khi cần bổ sung reads/exports, hãy làm trên **đúng module/đúng phía** sau khi phân tích phụ thuộc.

## 4. `extraProvides`: công bố provider thuộc chính provider module

Với `svc.provider`, agent bổ sung:

~~~java
inst.redefineModule(
        providerModule,
        Set.of(),
        Map.of(),
        Map.of(),
        Set.of(),
        Map.of(serviceClass, List.of(implementationClass)));
~~~

Trong đó:

- `providerModule` là **module mà `implementationClass` thực sự thuộc về**.
- Key `serviceClass` là `Class<?>` của service type (`Greeting`).
- Value là **danh sách không rỗng** các implementation classes, ví dụ `FastGreeting`.
- Mỗi implementation phải **thuộc module đang được redefine** và **là một implementation của service type**.
- Tham số `extraProvides` cho phép **bổ sung provider registration** vào module đã resolve, không tạo class mới từ source, không tự đưa một JAR chưa resolve vào module graph.

**Kiểm tra membership và type trước khi gọi** là thực hành tốt:

~~~java
if (implementationClass.getModule() != providerModule) {
    throw new IllegalArgumentException(
            "implementation is not in provider module");
}
if (!serviceClass.isAssignableFrom(implementationClass)) {
    throw new IllegalArgumentException(
            "implementation does not implement service");
}
~~~

Đây là fragment, các biến được agent xác định từ module/class objects thực tế.

Theo hợp đồng `redefineModule`, `IllegalArgumentException` có thể xảy ra nếu:

- Danh sách provider cho một key **rỗng**.
- Class được đưa vào `extraProvides` **không thuộc module được sửa**.
- Class đó **không phải implementation** của service type.

Không được hiểu `Map.of(Greeting.class, List.of(FastGreeting.class))` là câu lệnh “đưa FastGreeting từ module khác vào consumer”. Phải gọi trên **module `svc.provider`**.

### Provider cần khả năng được ServiceLoader tạo instance

Ngay cả khi `redefineModule` chấp nhận registration, `ServiceLoader` còn có quy tắc **tải và khởi tạo provider**. Với provider class thông thường như `FastGreeting`:

- Nó thực thi service `Greeting`.
- Nó có **public constructor không tham số**.
- Implementation module đã được **resolve trong module layer cần tìm**.
- Lớp có class file version hợp lệ và có thể khởi tạo không lỗi.

Một số kiểu provider trong named modules có thể dùng một **public static provider method** hợp lệ thay vì public no-arg constructor, theo hợp đồng `ServiceLoader`; phần thực hành chọn constructor công khai để dễ xác minh.

**Không cần export package implementation ra công khai chỉ để ServiceLoader tìm provider trong named module**. ServiceLoader có cơ chế truy cập provider theo hợp đồng module service. Export packages là câu chuyện về khả năng code khác tham chiếu trực tiếp tới type, không phải điều kiện bắt buộc để provider được tìm qua ServiceLoader.

## 5. Ma trận điều kiện: không, chỉ `uses`, chỉ `provides`, cả hai

Giả sử có **một service `Greeting`**, một consumer module `svc.consumer` và một provider module `svc.provider` đã được JVM resolve. Cả hai đọc API module `svc.api` và API package được export.

| Agent bổ sung | `consumer.canUse(Greeting.class)` | `ServiceLoader` từ consumer | Kết quả |
|---|---|---|---|
| Không bổ sung gì | `false` | Không được gọi hợp lệ để dùng service | `ServiceConfigurationError` |
| **Chỉ `extraUses`** | `true` | Được gọi, nhưng chưa đăng ký provider nào | Danh sách provider rỗng |
| **Chỉ `extraProvides`** | `false` | Consumer vẫn thiếu service dependence | `ServiceConfigurationError` |
| **Cả `extraUses` và `extraProvides`** | `true` | Consumer có quyền dùng; provider được công bố và tìm thấy | Tìm được `FastGreeting` |

Đây chính là lý do bài học có tên **“Bổ sung uses, provides và kiểm tra điều kiện dịch vụ”**: một kiểm tra boolean `canUse == true` là **điều kiện cho consumer**, nhưng **không chứng minh** đã có provider để thực thi. Ngược lại, một provider hợp lệ chưa bảo đảm mọi named consumer đều có quyền yêu cầu service.

Mô hình điều kiện:

~~~text
Consumer code gọi ServiceLoader.load(Greeting.class)
                        │
                        ▼
 Module caller có service dependence? ── Không ─► ServiceConfigurationError
             │ Có
             ▼
 Service type có accessible tại site gọi? ── Không ─► lỗi truy cập/service
             │ Có
             ▼
 Provider module đã được resolve trong layer phù hợp?
             │ Không ─► không tìm được provider ở layer đó
             ▼
 Provider đã được công bố trong descriptor hoặc extraProvides?
             │ Không ─► provider list có thể rỗng
             ▼
 Class provider đúng module, đúng service, khởi tạo hợp lệ?
             │ Không ─► ServiceConfigurationError
             ▼
        Có thể lấy instance từ ServiceLoader
~~~

Đây là **sơ đồ điều kiện logic**, không phải lời khẳng định rằng JVM luôn kiểm tra các điều kiện theo đúng thứ tự hiển thị cho mọi overload `ServiceLoader.load`.

## 6. Thực hành Java 17+: ba named modules và một agent

Ví dụ sẽ tạo **ba named modules**:

- `svc.api`: khai báo service `Greeting`.
- `svc.consumer`: đọc API nhưng **không có dòng `uses`**.
- `svc.provider`: đọc API, chứa provider `FastGreeting` nhưng **không có dòng `provides`**.

Một **Java agent riêng** sẽ bổ sung `extraUses`/`extraProvides` tại `premain`, tùy option `none`, `uses`, `provides`, `both`. Vì đây là thí nghiệm runtime, **không sửa `module-info.java` sau mỗi lượt**, và mỗi lượt chạy trên một JVM mới để kết quả độc lập.

Cây thư mục:

~~~text
module-service-lab/
├── src/
│   ├── svc.api/
│   │   ├── module-info.java
│   │   └── svc/api/Greeting.java
│   ├── svc.consumer/
│   │   ├── module-info.java
│   │   └── svc/consumer/Client.java
│   └── svc.provider/
│       ├── module-info.java
│       └── svc/provider/FastGreeting.java
├── src-agent/
│   └── Agent.java
├── AGENT.MF
└── out/
    ├── mods/                  các module đã biên dịch
    ├── agent-classes/         agent class
    └── agent.jar
~~~

### 6.1. `src/svc.api/module-info.java`

~~~java
module svc.api {
    exports svc.api;
}
~~~

**`exports svc.api` quan trọng** vì consumer và provider đều phải truy cập interface công khai `Greeting` từ module khác.

### 6.2. `src/svc.api/svc/api/Greeting.java`

~~~java
package svc.api;

public interface Greeting {
    String greet();
}
~~~

Service type được xác định bằng **đối tượng `Class<?>`** chứ không chỉ tên text `"svc.api.Greeting"`; trong runtime có class loaders, cùng tên mà khác defining loader không nhất thiết là cùng service type.

### 6.3. `src/svc.consumer/module-info.java`

~~~java
module svc.consumer {
    requires svc.api;
}
~~~

Cố ý **không có** `uses svc.api.Greeting;`. Điều này vẫn cho phép biên dịch một class trong module consumer có import `Greeting`, nhưng gọi `ServiceLoader` từ module này sẽ **không hợp lệ** nếu runtime chưa được agent bổ sung service dependence.

### 6.4. `src/svc.consumer/svc/consumer/Client.java`

~~~java
package svc.consumer;

import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;
import svc.api.Greeting;

public final class Client {
    public static void main(String[] args) {
        System.out.println("clientCanUse="
                + Client.class.getModule().canUse(Greeting.class));

        try {
            ServiceLoader<Greeting> loader =
                    ServiceLoader.load(Greeting.class);

            System.out.println("providers=" + loader.stream()
                    .map(p -> p.type().getName())
                    .sorted()
                    .toList());

            System.out.println("first=" + loader.findFirst()
                    .map(Greeting::greet)
                    .orElse("<none>"));
        } catch (ServiceConfigurationError error) {
            System.out.println("lookupError="
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

`Client` chạy **trong named module `svc.consumer`**, vì vậy `ServiceLoader` kiểm tra đúng service dependence của consumer. Chúng ta dùng:

- `Module.canUse(Greeting.class)` để hiển thị điều kiện **uses** tại runtime.
- `ServiceLoader.load(Greeting.class)` để kiểm tra hợp đồng service ngay trong caller module.
- `loader.stream().map(p -> p.type().getName())` để quan sát **tên provider type** theo API `ServiceLoader.Provider`, không nhất thiết cần tạo instance ở bước liệt kê.
- `findFirst().map(Greeting::greet)` để thực sự **khởi tạo và sử dụng** provider; nếu thiếu provider, in `<none>`.
- `.sorted()` để thứ tự hiển thị ổn định nếu demo mở rộng nhiều provider. **Không suy luận thứ tự provider across modules là bảo đảm từ JVM**.

**`ServiceConfigurationError` là một `Error`, không phải `Exception`**. `catch` ở đây chỉ dành cho bài thực hành có chủ đích để cả bốn case đều in output dễ so sánh. Trong production phải coi lỗi cấu hình service là vấn đề cần chẩn đoán, không nên nuốt lỗi rồi âm thầm tiếp tục.

### 6.5. `src/svc.provider/module-info.java`

~~~java
module svc.provider {
    requires svc.api;
}
~~~

Cố ý **không có** `provides svc.api.Greeting with svc.provider.FastGreeting;`. Cũng không cần export package `svc.provider` để ServiceLoader tìm provider **trong named module**.

### 6.6. `src/svc.provider/svc/provider/FastGreeting.java`

~~~java
package svc.provider;

import svc.api.Greeting;

public final class FastGreeting implements Greeting {
    public FastGreeting() { }

    @Override
    public String greet() {
        return "hello";
    }
}
~~~

Provider **thực thi đúng service**, nằm trong `svc.provider`, và có public constructor không tham số.

### 6.7. `src-agent/Agent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class Agent {
    public static void premain(String mode, Instrumentation inst)
            throws Exception {
        Module consumer = ModuleLayer.boot()
                .findModule("svc.consumer").orElseThrow();
        Module provider = ModuleLayer.boot()
                .findModule("svc.provider").orElseThrow();

        Class<?> service =
                Class.forName("svc.api.Greeting");
        Class<?> implementation =
                Class.forName("svc.provider.FastGreeting");

        if (!inst.isModifiableModule(consumer)
                || !inst.isModifiableModule(provider)) {
            throw new IllegalStateException("module not modifiable");
        }

        if (mode.equals("uses") || mode.equals("both")) {
            inst.redefineModule(
                    consumer,
                    Set.of(),
                    Map.of(),
                    Map.of(),
                    Set.of(service),
                    Map.of());
        }

        if (mode.equals("provides") || mode.equals("both")) {
            inst.redefineModule(
                    provider,
                    Set.of(),
                    Map.of(),
                    Map.of(),
                    Set.of(),
                    Map.of(service, List.of(implementation)));
        }

        System.out.println("agentMode=" + mode);
        System.out.println("agentConsumerCanUse="
                + consumer.canUse(service));
    }
}
~~~

**Đọc từng quyết định trong agent:**

1. `ModuleLayer.boot().findModule(...)` lấy **Module objects** đúng với named modules đã resolve trong boot layer. Nếu module chưa được resolve, `orElseThrow()` sẽ báo lỗi thay vì giả định module nào cũng sẵn có.
2. `Class.forName(...)` lấy hai **Class objects** đang được định nghĩa trong runtime. Với ví dụ này class có public API và các modules nằm trong boot layer, nên lookup thành công. Trong agent thực tế, nên cân nhắc `Class.forName(name, false, loader)` để tránh khởi tạo class sớm ngoài ý muốn và chọn đúng loader.
3. `isModifiableModule` kiểm tra cả consumer và provider trước khi sửa graph. Method này **không kiểm tra** class có thể retransform hay không.
4. Mode `uses`: gọi `redefineModule` trên **consumer**, chỉ truyền `extraUses = Set.of(service)`.
5. Mode `provides`: gọi `redefineModule` trên **provider**, chỉ truyền `extraProvides = Map.of(service, List.of(implementation))`.
6. Mode `both`: thực hiện **cả hai thay đổi** trong cùng `premain` trước khi consumer gọi `ServiceLoader`.
7. Mode `none`: không gọi `redefineModule` (dùng làm đối chứng).

Agent đang cố ý **không chỉnh `extraReads`, `extraExports`, `extraOpens`**, vì các module descriptors đã có đủ `requires svc.api` và `exports svc.api`. Nếu bỏ những khai báo này, bài kiểm tra cần được đánh giá lại; `extraUses`/`extraProvides` không tự sửa mọi lỗi module access.

Trong thí nghiệm, `mode` luôn được truyền qua `-javaagent:...=none|uses|provides|both`. Đây là protocol đơn giản của demo; production cần validate agent arguments trước khi dùng chúng.

### 6.8. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

Bảo đảm có dòng trống kết thúc. Không có `Can-Redefine-Classes` hay `Can-Retransform-Classes` vì demo **không redefine/retransform class**, mà chỉ dùng `redefineModule`.

## 7. Biên dịch và chạy bốn case

Mở terminal tại `module-service-lab`. Tạo thư mục output.

Bash/Git Bash:

~~~bash
mkdir -p out/mods out/agent-classes
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/mods, out/agent-classes | Out-Null
~~~

**Biên dịch ba named modules** với JDK 17+:

~~~bash
javac --release 17 -d out/mods --module-source-path src -m svc.api,svc.consumer,svc.provider
~~~

Cấu trúc `src/<module-name>/module-info.java` phải đúng như hướng dẫn, vì `--module-source-path src` yêu cầu source root của từng module nằm trong `src`.

**Biên dịch agent không thuộc named module** và đóng JAR:

~~~bash
javac --release 17 -d out/agent-classes src-agent/Agent.java
jar --create --file out/agent.jar --manifest AGENT.MF -C out/agent-classes .
~~~

**Bốn lệnh chạy trên bốn JVM riêng:**

~~~bash
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=none -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=uses -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=provides -m svc.consumer/svc.consumer.Client
java --module-path out/mods --add-modules svc.provider -javaagent:out/agent.jar=both -m svc.consumer/svc.consumer.Client
~~~

Đã kiểm chứng các lệnh này với **JDK 24**, biên dịch bằng `--release 17`; source không dùng API mới hơn Java 17.

### Vì sao bắt buộc có `--add-modules svc.provider`?

Chỉ đặt `svc.provider` vào `--module-path` **không bảo đảm** module ấy được **resolve trong boot layer** khi main module là `svc.consumer`. Trong demo, `svc.consumer` chỉ `requires svc.api`, không `requires svc.provider`; do đó `--add-modules svc.provider` đưa provider module vào tập root module cần giải quyết.

Nếu thiếu, `ModuleLayer.boot().findModule("svc.provider")` có thể rỗng, và agent không có **Module object** mục tiêu để công bố provider. `redefineModule` **không phải API để resolve/lắp module mới vào layer**.

Đây là một trong những điều kiện quan trọng của bài: **công bố provider trong module đã resolve** và **làm module trở nên resolved** là hai thao tác khác nhau.

### Case 1 — `none`: thiếu `uses`, thiếu `provides`

**Stdout kiểm chứng:**

~~~text
agentMode=none
agentConsumerCanUse=false
clientCanUse=false
lookupError=ServiceConfigurationError
~~~

`ServiceLoader` không được phép dùng service từ named module chưa có service dependence. Đây **không phải** lỗi class `Greeting` bị mất: consumer vẫn compile thành công và đã `requires svc.api`.

### Case 2 — `uses`: được dùng service nhưng chưa có provider

~~~text
agentMode=uses
agentConsumerCanUse=true
clientCanUse=true
providers=[]
first=<none>
~~~

Đây là bằng chứng **`extraUses` không tự tạo provider**. Consumer qua được điều kiện `ServiceLoader`, nhưng provider module chưa công bố `FastGreeting` qua `module-info` hoặc `extraProvides`.

### Case 3 — `provides`: có provider nhưng consumer chưa có `uses`

~~~text
agentMode=provides
agentConsumerCanUse=false
clientCanUse=false
lookupError=ServiceConfigurationError
~~~

Việc công bố provider không tự sửa service dependence cho mọi named consumer. Consumer vẫn thiếu `uses`, vì vậy `ServiceLoader.load` ở caller này thất bại.

### Case 4 — `both`: đủ `uses` và `provides`

~~~text
agentMode=both
agentConsumerCanUse=true
clientCanUse=true
providers=[svc.provider.FastGreeting]
first=hello
~~~

Đây là đường đi thành công:

- `extraUses` thêm service dependence vào `svc.consumer`.
- `extraProvides` công bố `FastGreeting` thuộc `svc.provider`.
- Cả hai module đọc được `svc.api` và service type được export.
- `svc.provider` đã được resolve trong boot layer nhờ `--add-modules`.
- `ServiceLoader` tìm được provider type, tạo instance và gọi `greet()` trả `"hello"`.

**Lưu ý:** Trong hệ thống có nhiều providers, thứ tự discovery có quy tắc riêng; không nên lấy “provider đầu tiên” làm cam kết nghiệp vụ nếu nhiều implementation có thể tham gia. Demo có đúng một provider nên `findFirst()` có kết quả xác định.

## 8. Khi nào nên dùng module descriptors thay vì `redefineModule`?

Nếu bạn **sở hữu source của modules** và quan hệ service là một phần thiết kế bình thường, nên khai báo trong `module-info.java`:

~~~java
// Consumer
module svc.consumer {
    requires svc.api;
    uses svc.api.Greeting;
}
~~~

~~~java
// Provider
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.FastGreeting;
}
~~~

Điều này giúp build, module tools và người đọc source hiểu quan hệ ngay từ đầu. Không cần agent sửa runtime graph cho một feature đã được xác định từ compile-time.

`Instrumentation.redefineModule` hữu ích khi:

- Một **Java agent** chèn thêm code gọi `ServiceLoader` vào named module ban đầu không có `uses`.
- Một framework/agent cần đăng ký provider **đã nằm trong module hợp lệ** mà module descriptor tĩnh chưa công bố.
- Cần điều chỉnh quan hệ runtime của một module do ứng dụng hoặc framework quản lý mà không sửa class/module descriptor trên đĩa.
- Có thể chứng minh ranh giới truy cập dịch vụ phù hợp và module đích modifiable.

Không dùng `redefineModule` như công cụ “vá tất cả classpath/module-path lỗi”; mục đích là **mở rộng các quan hệ đã được API cho phép** ở những module đang tồn tại.

## 9. Kiểm tra đúng các điều kiện trước khi thêm `uses` và `provides`

Một quy trình kiểm tra an toàn:

1. **Xác định caller thực tế.** Code nào sẽ gọi `ServiceLoader` sau instrumentation? `callerClass.getModule()` là consumer module; không suy từ module của agent.
2. **Xác định chính xác service type** bằng `Class<?>`, cùng runtime/class loader thích hợp. Kiểm tra nó có public/accessibility phù hợp ở vị trí gọi.
3. **Kiểm tra module resolution và layer.** `ModuleLayer.boot().findModule(...)` áp dụng cho ví dụ boot layer; với custom layers phải dùng đúng layer mà consumer/provider nằm trong.
4. **Kiểm tra đọc/exports.** Nếu service nằm trong `svc.api`, consumer cần đọc module API và package API phải export phù hợp. `Module.canRead` và `Module.isExported` giúp xem runtime graph.
5. **Kiểm tra `consumer.canUse(service)`** trước/sau khi bổ sung `extraUses`. Đây là phép hỏi service dependence.
6. **Kiểm tra implementation và membership.** `implementation.getModule() == providerModule`, `service.isAssignableFrom(implementation)`, cùng kiểm tra construction/provider method theo `ServiceLoader`.
7. **Kiểm tra `inst.isModifiableModule(target)`** trước mỗi `redefineModule`. Chú ý unnamed module luôn trả `true` nhưng redefine là no-op.
8. **Chỉ bổ sung những quan hệ cần thiết.** Dùng immutable `Set.of`, `Map.of`, `List.of` và tránh thêm exports/opens rộng ngoài mục tiêu.
9. **Kiểm tra kết quả qua `ServiceLoader` tại đúng caller.** `canUse=true` không chứng minh provider tồn tại. Dùng một loader mới hoặc `reload()` khi đã đổi registrations.
10. **Quan sát lỗi.** Nếu `ServiceLoader` không tìm thấy provider, phân biệt “không có provider”, “module chưa resolve”, “provider không khởi tạo được”, “service type không accessible” và “caller chưa có `uses`”.

### Mẫu preflight rút gọn trong agent

~~~java
static void checkProvider(
        Module targetProviderModule,
        Class<?> service,
        Class<?> implementation) {
    if (implementation.getModule() != targetProviderModule) {
        throw new IllegalArgumentException(
                "provider belongs to another module");
    }
    if (!service.isAssignableFrom(implementation)) {
        throw new IllegalArgumentException(
                "provider does not implement service");
    }
}
~~~

Đây là method hoàn chỉnh để đặt trong một class tiện ích; không tự chạy độc lập. **Chưa đủ** để xác nhận provider có public no-arg constructor, provider factory hợp lệ, module service type có readable/accessibility đúng, hoặc `ServiceLoader` sẽ được gọi trong layer phù hợp.

Có thể kiểm tra thêm:

~~~java
Module apiModule = service.getModule();
boolean readable = consumerModule.canRead(apiModule);
boolean exported = apiModule.isExported(
        service.getPackageName(), consumerModule);
boolean canUse = consumerModule.canUse(service);

System.out.println(readable);
System.out.println(exported);
System.out.println(canUse);
~~~

Đây là fragment giả định `service` và `consumerModule` đã tồn tại. Đối với API module có unqualified export, `isExported(..., consumerModule)` trả `true` khi quan hệ phù hợp. Nếu service nằm trong cùng module với caller, cách phân tích access có thể khác; mục tiêu ở đây là xác nhận **đúng trường hợp service interface thuộc module API riêng**.

## 10. Những ràng buộc của `extraProvides` dễ bỏ sót

**Không thể gắn một implementation thuộc module khác vào provider module** chỉ bằng giá trị `Map<Class<?>, List<Class<?>>>`. API kiểm tra membership và loại quan hệ.

Những ví dụ **không hợp lệ**:

~~~java
// Sai: providerList rỗng.
Map<Class<?>, List<Class<?>>> invalid1 =
        Map.of(serviceClass, List.of());

// Sai: implementation ở module khác
// nhưng truyền vào extraProvides của providerModule.
Map<Class<?>, List<Class<?>>> invalid2 =
        Map.of(serviceClass, List.of(classFromAnotherModule));
~~~

Các fragment trên giả định các biến đã được cung cấp; **không gọi thật** `redefineModule` với những map này trong ứng dụng production.

Hậu quả thường là `IllegalArgumentException`, theo đặc tả Instrumentation:

- Map `extraProvides` chứa value list **rỗng**.
- Lớp provider **không phải thành viên module đang được redefine**.
- Lớp provider **không thực thi service type**.

Trong demo, điều kiện được bảo đảm bằng `FastGreeting implements Greeting` và `FastGreeting.class.getModule()` là `svc.provider`.

Ngoài ba điều kiện API kiểm tra trực tiếp, `ServiceLoader` còn có thể báo lỗi khi **lớp provider không thể được nạp/khởi tạo**: constructor thiếu hoặc không hợp lệ, static provider method sai hợp đồng, dependency của provider lỗi, provider method ném exception hoặc trả `null`.

**Provider implementation không cần export package để các consumer khởi tạo qua ServiceLoader**, nhưng nếu consumer muốn gọi trực tiếp một class concrete như `new FastGreeting()`, đó là một quan hệ truy cập khác và cần exports/reads tương ứng.

## 11. `ServiceLoader`: discovery, instantiation, cache và lỗi

`ServiceLoader` có hai giai đoạn cần phân biệt:

- **Discovery:** tìm các providers được khai báo/công bố trong các module/layer và những nguồn thích hợp khác.
- **Instantiation:** tạo instance provider khi người dùng lấy phần tử, gọi `findFirst()`, duyệt iterator, v.v.

Ví dụ:

~~~java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);

loader.forEach(greeting ->
        System.out.println(greeting.greet()));
~~~

Đây là fragment bên trong class thuộc named consumer có `uses` tương ứng. `stream().map(Provider::type)` giúp truy cập provider types; `forEach` trên `loader` thực sự lấy instances.

`ServiceLoader` **cache các provider** đã load trên một loader instance. Nếu agent bổ sung `extraProvides` sau khi code ứng dụng đã duyệt một `ServiceLoader` cũ, đừng giả định cache đó tự được refresh theo cách bạn cần. Có thể tạo **`ServiceLoader` mới** tại đúng caller/layer hoặc gọi **`loader.reload()`** để xóa cache trước khi tìm lại.

`reload()` **không tự resolve module mới**, cũng không biến một module chưa có `uses` thành consumer hợp lệ. Nó chỉ quản lý cache/discovery của đối tượng loader.

Đặc tả còn mô tả providers do instrumentation agents bổ sung **được tìm sau các providers đã khai báo trong module descriptor** (khi xét các providers của module đó). Thứ tự **giữa các modules trong cùng layer** không phải một hợp đồng ổn định để lựa chọn “provider ưu tiên nhất”. Dùng explicit priority/configuration khi thứ tự ảnh hưởng nghiệp vụ.

### `ServiceLoader.load(...)` và `load(ModuleLayer, ...)`

- `ServiceLoader.load(Greeting.class)` dùng **thread context class loader** theo API tiện ích, và kiểm tra service dependence của **caller module**.
- `ServiceLoader.load(layer, Greeting.class)` tìm providers trong **module layer đã chỉ định và các layer cha**, không tìm providers trong unnamed modules theo cách của overload này. Caller trong named module vẫn phải có quyền sử dụng service.
- `ServiceLoader.loadInstalled(Greeting.class)` dùng platform class loader và có **phạm vi discovery khác**; không thay thế mặc định cho named providers trên application module path.

Demo chọn overload một tham số và `ModuleLayer.boot()` vì cả ba named modules ở boot layer và thread context loader mặc định phù hợp. Trong ứng dụng có custom layers, hãy chọn overload/layer đúng, không lấy `ModuleLayer.boot()` theo thói quen.

## 12. Ba lỗi khác nhau nhưng thường bị gom thành “ServiceLoader hỏng”

| Hiện tượng | Điều thực sự thiếu |
|---|---|
| `ServiceConfigurationError` nói module không declare `uses` | **Consumer thiếu service dependence** |
| `ServiceLoader` trả danh sách rỗng | Caller hợp lệ nhưng **không phát hiện provider nào trong phạm vi tìm kiếm** |
| Provider được liệt kê nhưng `findFirst`/iterator ném `ServiceConfigurationError` | **Provider bị lỗi khi load/kiểm tra/khởi tạo** |

Điều này lý giải tại sao **chỉ nhìn `Module.canUse()` là chưa đủ**. Nó xác nhận khả năng *sử dụng service* của module, không xác nhận provider availability hay constructor.

Các lỗi khác cần phân biệt:

| Lỗi/hiện tượng | Nguyên nhân và kiểm tra |
|---|---|
| `UnmodifiableModuleException` | Module không thể sửa bằng `redefineModule`; kiểm tra `isModifiableModule` |
| `IllegalArgumentException` lúc `redefineModule` | `extraProvides` chứa provider sai module/không implement service/danh sách rỗng, hoặc `extraExports`/`extraOpens` không hợp lệ |
| `NullPointerException` lúc `redefineModule` | Một trong các đối số hoặc key/value collection là `null` |
| `NoSuchElementException` ở `findModule(...).orElseThrow()` | Module chưa được resolve trong layer đang tìm; kiểm tra `--add-modules`, graph và layer |
| `NoClassDefFoundError` / `ClassNotFoundException` | Type không được loader phù hợp tìm thấy; kiểm tra module resolution và defining loader |
| `IllegalAccessError` / lỗi module access | Named module không đọc được module cần thiết hoặc package không export phù hợp |
| `InaccessibleObjectException` ở deep reflection | Package chưa được **open** cho caller; khác với `uses`/`provides` |
| `ServiceConfigurationError` lúc instantiate | Provider constructor/factory hoặc dependency lỗi; xem cause và module/class identity |
| `ClassCastException` | Dùng type trùng tên ở class loaders khác nhau, provider không cùng danh tính service class |
| Không thể tìm provider sau khi bổ sung | Module chưa resolved, ServiceLoader dùng layer/loader khác hoặc cache chưa reload |

Đừng dùng `--add-opens` để chữa một lỗi thiếu `uses`: mở package cho reflection **không** thêm service dependence. Ngược lại, `extraUses` không chữa lỗi truy cập reflective.

## 13. `Module.addUses` và `Instrumentation.redefineModule` khác nhau

Java `Module` có phương thức:

~~~java
Module addUses(Class<?> service);
~~~

Nhưng `Module.addUses` có ràng buộc về **caller module**: với named module, caller phải nằm trong chính module đang thêm service dependence, nếu không có thể nhận **`IllegalCallerException`**. Nó được thiết kế cho framework hoặc code phù hợp thao tác từ bên trong module.

Java agent ở một module khác không nên đơn giản gọi:

~~~java
consumerModule.addUses(serviceClass);
~~~

rồi nghĩ đã có quyền sửa mọi named module. Để agent sửa consumer module **từ bên ngoài**, `Instrumentation.redefineModule(consumerModule, ..., extraUses, ...)` là API phù hợp.

Một điểm khác: `Module.addUses` **không kích hoạt lại `resolveAndBind`**, và bản thân nó không kéo một module provider mới chưa resolve vào layer. `Instrumentation.redefineModule` cũng không phải công cụ tự xây mới layer và resolve tất cả modules trên module path.

## 14. Modules, class loaders và điều kiện khả dụng của service

Điều kiện service không chỉ có hai cờ `uses` và `provides`. Khi tích hợp vào hệ thống thực tế, cần xét **module graph và class loader identity**:

~~~text
                  svc.api (export svc.api)
                  /                     \
           requires                     requires
             /                             \
        svc.consumer                    svc.provider
        extraUses(Greeting)             extraProvides(Greeting → FastGreeting)
             |                             |
             | ServiceLoader call          | registration
             └───────── discover ──────────┘
                       (khi provider module
                        đã resolved và lookup
                        dùng đúng layer)
~~~

Đối với named consumer/module providers trên **boot layer** như bài tập:

- Cả consumer và provider có **`requires svc.api`**, đủ để tham chiếu service interface.
- `svc.api` có **`exports svc.api`**, bảo đảm interface public có thể được dùng từ các module khác.
- `svc.provider` có mặt trong **resolved boot layer**, nhờ `--add-modules svc.provider` lúc khởi động.
- `extraUses` thêm quan hệ consumer → service type, nhưng **không** thay `requires`.
- `extraProvides` đăng ký implementation class thực sự nằm trong `svc.provider`, nhưng **không** chuyển class từ loader khác vào provider module.
- `ServiceLoader.load` chạy trong caller module tiêu thụ, dùng đúng loader/layer để tìm provider.

Trong một ứng dụng có container hoặc plugin loader, việc chỉ so **tên nhị phân của class** có thể gây nhầm. Hãy log `service.getModule()`, `service.getClassLoader()`, `implementation.getModule()`, và module layer của chúng. Một `Class<?>` do loader A định nghĩa không tự bằng class cùng tên do loader B định nghĩa.

## 15. Vì sao không nên dùng `extraUses` / `extraProvides` tùy tiện?

`redefineModule` có thể **mở rộng khả năng tương tác giữa các modules**. Đây là hành động có ý nghĩa với bảo mật/đóng gói ứng dụng, dù không thay class file.

Các nguyên tắc:

1. **Chỉ thay module thực sự cần instrument**. Đừng bổ sung `uses` vào hàng loạt modules chỉ vì ServiceLoader không tìm được một provider.
2. **Chọn đúng service type** và kiểm tra rằng consumer được phép đọc/truy cập type đó; API không tự xác nhận khả năng truy cập ở mọi site.
3. **Provider chỉ đăng ký cho module chứa implementation**, không gán một class đến từ module bất kỳ.
4. **Không mở package rộng ngoài nhu cầu** để chữa lỗi service discovery; extraExports/extraOpens là các quyền truy cập khác, cần đánh giá riêng.
5. **Hiểu tính cộng dồn:** `redefineModule` không có thao tác rút `uses`/`provides` đã bổ sung trong JVM hiện tại theo API này. Tránh coi nó là một cấu hình dễ bật/tắt tức thì.
6. **Không coi module-path là tất cả đã loaded.** Chỉ những module được resolve trong đúng layer mới có `Module` object để đăng ký runtime.
7. **Theo dõi lifecycle của `ServiceLoader`.** Có cache và lazy loading, nên cần test lại với loader mới hoặc `reload`.
8. **Bảo vệ provider constructor/factory.** Instance có thể được tạo vào lúc không ngờ tới, do một module khác yêu cầu service.
9. **Kiểm tra trên cùng JDK và cùng module topology** sẽ dùng ở production. Nạp module với custom loader, automatic/unnamed modules hoặc khi một agent khác cùng sửa graph có thể dẫn đến hành vi khác ví dụ tối giản.
10. **Không nuốt lỗi cấu hình dịch vụ**. Ghi đủ tên service, caller module, provider module và nguyên nhân để chẩn đoán.

Với một kiến trúc bạn sở hữu từ source, cách ổn định nhất thường vẫn là khai báo `uses` và `provides` trong `module-info.java`, rồi dùng instrumentation chỉ khi thực sự cần bổ sung quan hệ runtime.

## 16. Một quy trình QA service sau instrumentation

Dưới đây là checklist áp dụng sau khi agent bổ sung `extraUses` hoặc `extraProvides`:

| Kiểm tra | Phép hỏi/công cụ |
|---|---|
| Đúng consumer module? | `callerClass.getModule()` |
| Module đã được resolve? | `ModuleLayer` tương ứng, `findModule` |
| Service type đúng class identity? | `service.getName()`, `service.getModule()`, `service.getClassLoader()` |
| Consumer đọc module service? | `consumer.canRead(service.getModule())` |
| Package service được export phù hợp? | `service.getModule().isExported(service.getPackageName(), consumer)` |
| Consumer được phép dùng service? | `consumer.canUse(service)` |
| Provider thuộc provider module? | `implementation.getModule() == provider` |
| Provider thực thi service? | `service.isAssignableFrom(implementation)` |
| Provider có thể được tạo? | `ServiceLoader` instantiate thành công; constructor/factory hợp lệ |
| Có provider trong discovery scope? | `ServiceLoader.load(...)` / `load(layer, ...)`, `stream()` |
| Có cache stale? | Tạo loader mới hoặc `reload()` |
| Module cho phép agent cập nhật? | `inst.isModifiableModule(module)` |
| API có trả lỗi khi đăng ký không? | Bắt/log `IllegalArgumentException`, `UnmodifiableModuleException` đúng chỗ |

Với instrumentation site có service type từ một module khác, hãy kiểm tra **cả `canUse` lẫn `canRead` và package export**. Một trường `true` đơn lẻ không chứng minh tất cả điều kiện thành công.

Đừng kiểm thử `ServiceLoader` từ agent unnamed module rồi xem kết quả đó là proof rằng named consumer đã có quyền; **đúng caller module** mới là yếu tố quyết định.

## 17. Câu hỏi tự kiểm tra

1. **`requires svc.api` có thay được `uses svc.api.Greeting` không?** Không. `requires` là quan hệ module reading; `uses` là service dependence.
2. **`extraUses` nên thêm vào module nào?** Module **thực hiện lời gọi sử dụng service** (consumer).
3. **`extraProvides` nên thêm vào module nào?** Module **chứa lớp implementation** (provider).
4. **`extraUses` đã thành công, `consumer.canUse(service)==true`. Có nhất thiết `ServiceLoader` tìm được provider?** Không. Provider có thể chưa được công bố/resolve hoặc nằm ngoài discovery scope.
5. **`extraProvides` đã công bố `FastGreeting`, consumer thiếu `uses`. `ServiceLoader.load` từ consumer sẽ thế nào?** Có thể ném `ServiceConfigurationError` do thiếu service dependence.
6. **`extraProvides` có được chứa implementation từ module khác với module đang redefine không?** Không. API kiểm tra membership và service implementation.
7. **Giá trị map `extraProvides` là `List.of()` rỗng có hợp lệ không?** Không; `IllegalArgumentException`.
8. **Có cần export package implementation cho mọi consumer chỉ để dùng `ServiceLoader`?** Không đối với provider thuộc named module và được đăng ký đúng.
9. **Vì sao demo dùng `--add-modules svc.provider`?** Để provider module được **resolve**, không chỉ xuất hiện trên module path.
10. **`redefineModule` có thể loại bỏ `uses`/`provides` đã có không?** Không; API chỉ mở rộng.
11. **`isModifiableModule(unnamedModule)` luôn true. Có thể dùng `redefineModule` để sửa unnamed module không?** Lời gọi là **no-op** đối với unnamed module.
12. **Làm sao xác nhận service dependence runtime đã bổ sung?** `Module.canUse(serviceClass)`.
13. **Làm sao xác nhận provider được dùng thực tế?** Chạy `ServiceLoader` từ đúng consumer, tìm provider và tạo instance thành công.
14. **`ServiceLoader.load` từ agent unnamed module thành công có chứng minh consumer named module hợp lệ?** Không; caller module khác nhau.
15. **Khi service type không accessible ở site instrument, `extraUses` có tự sửa?** Không; agent phải đảm bảo đọc module và truy cập type.
16. **Khi provider module chưa resolved, `redefineModule` tự thêm nó vào boot layer?** Không.
17. **Provider có thể bị phát hiện nhưng lỗi khi khởi tạo?** Có; `ServiceConfigurationError` vẫn có thể xuất hiện.
18. **Có nên dùng `Module.getDescriptor().uses()` thay cho `Module.canUse` sau runtime modification?** Không nếu cần trạng thái runtime; `Module.canUse` là phép hỏi hợp đồng service dependence.

### Tài liệu chính thức

- [Java SE 21 — `Instrumentation.redefineModule` và `isModifiableModule`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): hợp đồng `extraUses`, `extraProvides`, điều kiện membership, danh sách nonempty, giới hạn additive-only.
- [Java SE 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canUse`, `canRead`, `isExported`, `addUses`, module layer và caller restriction.
- [Java SE 21 — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): named-module caller `uses`, provider discovery, `Provider`, cache/reload và các lỗi.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): resolved modules và layers.
- [Java SE 21 — `ModuleDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html): khai báo `requires`, `uses` và `provides` ở descriptor.
- [JLS Java SE 21 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): cú pháp và ngữ nghĩa `module-info.java`.

**Ghi nhớ:** **`extraUses` cấp service dependence cho consumer**, còn **`extraProvides` công bố implementation thuộc provider module**. Hai bước là độc lập. Để gọi dịch vụ thành công, còn phải có **service type accessible, provider module đã resolve, provider hợp lệ, `ServiceLoader` chạy ở đúng caller/layer và kết quả đã được kiểm tra bằng runtime thực tế**.