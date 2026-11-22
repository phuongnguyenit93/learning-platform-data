# Phân biệt resolve và resolveAndBind khi liên kết provider dịch vụ

Trong hệ thống Java sử dụng **Java Platform Module System (JPMS)**, một module có thể khai báo rằng nó **sử dụng** một dịch vụ mà không cần phụ thuộc trực tiếp vào module **cung cấp** dịch vụ. Điều đó có lợi cho plugin, codec, adapter, bộ xử lý và các extension point: phần lõi chỉ biết interface dịch vụ, còn provider được triển khai và phân phối riêng.

Tuy nhiên, ở bước tạo một **module configuration** cho plugin, có sự khác biệt rất quan trọng giữa hai API của `java.lang.module.Configuration`:

- **`resolve(...)`**: phân giải các module gốc cùng các phụ thuộc module theo quan hệ `requires`.
- **`resolveAndBind(...)`**: làm bước trên, **đồng thời service binding** để thêm vào đồ thị những module provider được tìm thấy cho các dịch vụ được `uses`.

Nếu chỉ gọi `resolve` với module consumer làm root, một provider có mặt trên module path nhưng không nằm trong chuỗi `requires` có thể **không được đưa vào configuration**. Sau đó tạo `ModuleLayer` từ configuration ấy thì `ServiceLoader` sẽ không tìm thấy provider đó trong layer. `resolveAndBind` xử lý tình huống này bằng việc đưa các module provider phù hợp vào kết quả phân giải.

Bài này tập trung vào cơ chế, điều kiện áp dụng, ranh giới của service binding và một ví dụ Java 17 thực sự chạy được với hai configuration đối chiếu.

## 1. Bốn khái niệm phải phân biệt trước

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Service type** | Interface hoặc abstract class mô tả hợp đồng | `demo.api.Greeting` |
| **Consumer module** | Module gọi dịch vụ, dùng `requires` để đọc API và `uses` để khai báo tiêu thụ | `demo.app` |
| **Provider module** | Module công bố implementation bằng `provides ... with ...` | `demo.provider` |
| **Module configuration** | Tập `ResolvedModule` và đồ thị readability do thuật toán resolution tạo ra | Kết quả `Configuration.resolve/resolveAndBind` |

Bổ sung hai khái niệm runtime:

- **`ModuleLayer`**: đưa một `Configuration` vào JVM thành các đối tượng `Module` thực, gắn chúng với class loader phù hợp. Việc **tạo configuration** và **định nghĩa module layer** là hai thao tác riêng biệt.
- **`ServiceLoader`**: khám phá và có thể khởi tạo provider ở runtime, ví dụ `ServiceLoader.load(layer, Greeting.class)`. Việc provider được đưa vào configuration **chưa có nghĩa instance provider đã được tạo**.

Vì vậy hãy tách ba mốc: **resolve module graph → define layer → discover/instantiate provider**. `resolveAndBind` nằm ở mốc đầu, còn `ServiceLoader` hoạt động tại mốc sau.

## 2. Quan hệ requires, uses và provides không giống nhau

Đặt ba module:

```text
demo.api
  exports demo.api;
  interface demo.api.Greeting

demo.app
  requires demo.api;
  uses demo.api.Greeting;

demo.provider
  requires demo.api;
  provides demo.api.Greeting with demo.provider.HelloGreeting;
```

Ý nghĩa:

1. `requires demo.api` trong `demo.app` là **phụ thuộc module** để compiler/runtime cho phép consumer đọc API `Greeting` (trong phạm vi exports).
2. `uses demo.api.Greeting` là **khai báo tiêu thụ dịch vụ**. Nó báo cho cơ chế service binding và `ServiceLoader` biết module này dùng service, nhưng **không tương đương `requires demo.provider`**.
3. `provides demo.api.Greeting with demo.provider.HelloGreeting` đăng ký implementation với JPMS. Provider module thường cần `requires demo.api` để biết service interface.
4. Consumer **không cần biết tên** module implementation tại thời điểm biên dịch. Việc thêm `requires demo.provider` vào consumer chỉ để “ép provider hiện diện” làm mất một phần khả năng thay thế plugin.

Sơ đồ:

```text
               requires (readability)
demo.app -------------------------------> demo.api
    |                                        ^
    | uses demo.api.Greeting                 | requires
    |                                        |
    +---- service-use relation ----> demo.provider
                     (provides demo.api.Greeting)

Không có requires demo.app -> demo.provider.
```

Đường service-use ở đây là **quan hệ để tìm provider khi binding**, không phải một cạnh `requires` hay bảo đảm module consumer tự động có quyền truy cập mọi package của implementation. Consumer thông thường chỉ cần API type và sử dụng `ServiceLoader`.

## 3. resolve(): từ roots tới đồ thị phụ thuộc module

Java 17 cung cấp instance method:

```java
Configuration child = parentConfiguration.resolve(
        beforeFinder, afterFinder, roots);
```

Và static overload để hỗ trợ nhiều parent configuration:

```java
Configuration child = Configuration.resolve(
        beforeFinder, parentConfigurations, afterFinder, roots);
```

Đây là **đoạn API minh họa**; các biến phải là `Configuration`, `ModuleFinder` và `Collection<String>` phù hợp.

Thuật toán lấy **root module names**, rồi tìm root và các phụ thuộc `requires` trực tiếp/gián tiếp. Khi tìm module, thứ tự lookup ở API trên là:

1. `beforeFinder`;
2. các parent configurations theo thứ tự;
3. `afterFinder` nếu chưa tìm thấy.

Những module được đáp ứng bởi parent configuration **không được đưa vào `child.modules()`** nữa; chúng thuộc configuration cha. Sau khi tìm và kiểm tra dependencies, resolver tạo đồ thị module readability. `Configuration.modules()` trả tập module phân giải trong **chính configuration đó**, còn `findModule(name)` có thể tìm tiếp trong các parent configurations.

Với `demo.app` là root:

```text
roots = {"demo.app"}

resolve:
  demo.app --requires--> demo.api
  demo.provider: không được yêu cầu bởi cạnh requires nào

Kết quả trong configuration mới:
  demo.app, demo.api
```

Chỉ vì `ModuleFinder` **có thể nhìn thấy** JAR `demo.provider` không có nghĩa `resolve` sẽ đưa JAR đó vào đồ thị. “Observable” và “resolved” là hai trạng thái khác nhau. `uses` tự nó không khiến `resolve` thu thập module provider.

## 4. resolveAndBind(): resolution có bổ sung service binding

Instance API có cùng kiểu đối số:

```java
Configuration child = parentConfiguration.resolveAndBind(
        beforeFinder, afterFinder, roots);
```

Static API có `List<Configuration>` làm parents:

```java
Configuration child = Configuration.resolveAndBind(
        beforeFinder, parentConfigurations, afterFinder, roots);
```

**Cơ chế thực chất** (Java 17):

1. Bắt đầu bằng việc resolve các root modules giống `resolve`, gồm các cạnh `requires`.
2. Xem những service được `uses` bởi các module vừa resolve **và các module trong parent configurations**.
3. Trong các module mà `beforeFinder`/`afterFinder` quan sát được, tìm module có `provides` implementation của các service đó.
4. **Thêm các provider modules** thích hợp vào đồ thị, rồi phân giải dependencies của chính provider module đó.
5. Nếu các module mới lại có `uses` dịch vụ khác, tiếp tục quá trình **lặp** đến khi không còn module mới cần thêm.

Với ví dụ:

```text
roots = {"demo.app"}

resolveAndBind:
  demo.app  --requires--> demo.api
      |                       ^
      | uses Greeting         | requires
      v                       |
  demo.provider --provides----+

Kết quả trong configuration mới:
  demo.app, demo.api, demo.provider
```

Điểm thường bị bỏ sót: service binding xét cả các `uses` trong **parent configurations**, không chỉ module root của lớp con. Nếu trước/after finder chứa nhiều provider hợp lệ, `resolveAndBind` có thể kéo vào **nhiều module hơn dự đoán**. Đừng coi đây là thuật toán “chọn đúng một implementation tốt nhất” hoặc “chỉ lấy provider được ứng dụng sử dụng trực tiếp”. Nó nhằm giải quyết **tính hiện diện của provider modules** trong graph.

### Bảng so sánh

| Tiêu chí | `resolve` | `resolveAndBind` |
| --- | --- | --- |
| Root modules | Có | Có |
| Resolve `requires` transitively | Có | Có |
| Bổ sung module provider chỉ vì phù hợp `uses`/`provides` | Không | Có |
| Resolve dependencies của provider được bổ sung | Không có bước bổ sung này | Có |
| Xem service-use của parent configurations để binding | Không | Có |
| Có thể kéo vào nhiều provider cho cùng service | Chỉ khi đã được root/`requires` đưa vào | Có, theo các module quan sát được |
| Tạo một `ModuleLayer` | Không | Không |
| Nạp class hoặc tạo provider instance | Không | Không |
| Bảo đảm `ServiceLoader` tìm provider chưa có trong module graph | Không | Không; cần module khả kiến và cấu hình phù hợp |

Không nên hiểu `resolveAndBind` là thay thế `ServiceLoader`: binding tạo **module graph**, còn `ServiceLoader` tìm và khởi tạo instance dựa trên runtime layer hoặc class loader.

## 5. Ví dụ hoàn chỉnh: một provider chỉ xuất hiện khi service binding

Chúng ta tạo ba named modules:

- `demo.api`: công bố interface dịch vụ.
- `demo.app`: consumer có `uses` nhưng không `requires demo.provider`.
- `demo.provider`: triển khai và đăng ký service bằng `provides`.

Sau đó một launcher chạy trên classpath dùng cùng `ModuleFinder` và cùng roots để so sánh `resolve` với `resolveAndBind`. Launcher tạo **hai layer riêng biệt** và đếm provider mà `ServiceLoader.load(layer, serviceType)` tìm được. Ví dụ sử dụng Java 17+ và không cần thư viện ngoài JDK.

### 5.1. Cấu trúc thư mục

```text
module-binding-demo/
├── src/
│   ├── demo.api/
│   │   ├── module-info.java
│   │   └── demo/api/Greeting.java
│   ├── demo.app/
│   │   ├── module-info.java
│   │   └── demo/app/App.java
│   └── demo.provider/
│       ├── module-info.java
│       └── demo/provider/HelloGreeting.java
└── LayerResolutionDemo.java
```

### 5.2. Nội dung các module

**`src/demo.api/module-info.java`**

```java
module demo.api {
    exports demo.api;
}
```

**`src/demo.api/demo/api/Greeting.java`**

```java
package demo.api;

public interface Greeting {
    String greet(String name);
}
```

**`src/demo.app/module-info.java`**

```java
module demo.app {
    requires demo.api;
    uses demo.api.Greeting;
}
```

**`src/demo.app/demo/app/App.java`**

```java
package demo.app;

public final class App {}
```

Class `App` đơn giản là dấu mốc để module consumer có mã; điều quan trọng của ví dụ nằm ở `module-info.java`: consumer vừa `requires demo.api` để đọc interface, vừa `uses demo.api.Greeting` để tham gia service binding.

**`src/demo.provider/module-info.java`**

```java
module demo.provider {
    requires demo.api;
    provides demo.api.Greeting with demo.provider.HelloGreeting;
}
```

**`src/demo.provider/demo/provider/HelloGreeting.java`**

```java
package demo.provider;

import demo.api.Greeting;

public final class HelloGreeting implements Greeting {
    public HelloGreeting() {}

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`demo.provider` **không exports** package implementation. `ServiceLoader` vẫn có thể tạo provider hợp lệ theo quy tắc `provides`; consumer không cần gọi trực tiếp `new HelloGreeting()`. Constructor public không tham số hỗ trợ cơ chế provider constructor trong named module. Các dạng provider method khác cũng được `ServiceLoader` hỗ trợ, nhưng không cần cho ví dụ này.

### 5.3. Launcher so sánh cả hai nhánh

**`LayerResolutionDemo.java`** (nằm ở root project, chạy trên classpath):

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
import java.util.ServiceLoader;
import java.util.stream.Collectors;

public final class LayerResolutionDemo {
    private static String names(Configuration config) {
        return config.modules().stream()
                .map(m -> m.name())
                .sorted()
                .collect(Collectors.joining(","));
    }

    private static long providerCount(ModuleLayer layer) throws Exception {
        Class<?> type = layer.findLoader("demo.api")
                .loadClass("demo.api.Greeting");
        return ServiceLoader.load(layer, type).stream().count();
    }

    public static void main(String[] args) throws Exception {
        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration boot = ModuleLayer.boot().configuration();
        Set<String> roots = Set.of("demo.app");

        Configuration resolved =
                boot.resolve(finder, ModuleFinder.of(), roots);
        Configuration bound =
                boot.resolveAndBind(finder, ModuleFinder.of(), roots);

        System.out.println("resolve=" + names(resolved));
        System.out.println("resolveAndBind=" + names(bound));

        ModuleLayer plainLayer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                    resolved, ClassLoader.getSystemClassLoader());
        ModuleLayer boundLayer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                    bound, ClassLoader.getSystemClassLoader());

        System.out.println(
            "resolve providers=" + providerCount(plainLayer));
        System.out.println(
            "resolveAndBind providers=" + providerCount(boundLayer));
    }
}
```

**Vì sao launcher lấy `Class<?>` từ layer?** Launcher không yêu cầu compile-time dependency vào `demo.api`; nó lấy đúng service type được định nghĩa bởi loader của `demo.api` trong từng layer. Đây cũng là cách tránh nhầm lẫn class identity khi tạo module layer động. Dù hai layer dùng cùng tên module và interface, các class được tạo bởi loader riêng của từng layer không nên bị ép kiểu qua lại.

**Vì sao dùng `ServiceLoader.load(layer, type)`?** API này tìm provider trong **layer được chỉ định và các ancestor layers**, thay vì dựa vào thread context class loader ngầm. Nó không quét provider trong unnamed modules. Việc gọi `stream().count()` ở đây đếm provider descriptor được phát hiện, **không bắt buộc tạo instance service**, nên kết quả so sánh tập provider mà layer công bố.

### 5.4. Biên dịch và chạy

Tại thư mục `module-binding-demo`, chạy bằng PowerShell trên Windows:

```powershell
New-Item -ItemType Directory -Force mods, launcher | Out-Null

javac --release 17 --module-source-path src -d mods --module demo.api,demo.app,demo.provider

javac --release 17 -d launcher LayerResolutionDemo.java

java -cp launcher LayerResolutionDemo mods
```

Có thể dùng các lệnh `javac` và `java` tương tự trên macOS/Linux sau khi tạo hai thư mục đầu ra `mods`, `launcher` bằng `mkdir -p mods launcher`. Lệnh `--module-source-path src` chỉ nơi chứa thư mục nguồn của các named modules; `-d mods` xuất mỗi module vào `mods/demo.api`, `mods/demo.app`, `mods/demo.provider`; `ModuleFinder.of(Path.of(args[0]))` đọc các module đó trực tiếp từ thư mục `mods`.

**Stdout chính xác, đã biên dịch bằng `javac --release 17` và chạy bằng `java`:**

```text
resolve=demo.api,demo.app
resolveAndBind=demo.api,demo.app,demo.provider
resolve providers=0
resolveAndBind providers=1
```

Những số và tên này có ý nghĩa rõ:

1. Khi `roots = Set.of("demo.app")`, `resolve` thêm `demo.api` do `requires`; provider không phải root và không được yêu cầu bởi module nào trong nhánh đó.
2. `resolveAndBind` quan sát `uses demo.api.Greeting` của `demo.app` và `provides ... with ...` của `demo.provider`, nên đưa thêm `demo.provider` vào `Configuration`.
3. `defineModulesWithOneLoader` tạo runtime layer từ từng graph. Hai lớp layer này khác nhau, dù cùng dùng boot layer làm parent và module files giống nhau.
4. `ServiceLoader.load(plainLayer, type)` không tìm thấy provider vì `demo.provider` không hiện diện trong layer đó hay tổ tiên của nó.
5. `ServiceLoader.load(boundLayer, type)` tìm thấy một provider trong named module đã được service binding đưa vào.

**Giới hạn ví dụ:** thư mục `mods` chỉ có đúng ba module và boot layer không chứa provider cho `demo.api.Greeting`. Ở hệ thống thật, một provider có thể đã được resolve vì nó là root, vì một cạnh `requires` khác, hoặc đã nằm trong parent layer; khi đó `resolve` cũng có thể dẫn đến provider khả dụng. Do đó không kết luận “`resolve` luôn trả 0 provider”.

## 6. Trường hợp nào resolve vẫn tìm được provider?

So sánh hai API dễ dẫn đến kết luận quá mức rằng **`resolve` không tương thích với `ServiceLoader`**. Thực tế nó vẫn hoạt động khi provider đã được đưa vào cấu hình bằng một cơ chế khác.

### Provider nằm trong roots

Nếu người vận hành chủ động chọn plugin:

```java
Set<String> roots = Set.of("demo.app", "demo.provider");
Configuration explicit = boot.resolve(
    finder, ModuleFinder.of(), roots);
```

Đây là snippet sử dụng các biến `boot` và `finder` từ ví dụ. `resolve` lúc này có thể đưa cả consumer và provider vào graph vì `demo.provider` là **root rõ ràng**, không cần suy ra từ `uses`. Cách làm này phù hợp khi sản phẩm cần danh sách provider cố định hoặc do administrator phê duyệt.

### Provider đã có trong parent layer

Một provider có thể đã được resolve trong `ModuleLayer.boot()` hoặc layer cha. `ServiceLoader.load(layer, type)` duyệt layer chỉ định và các ancestor, nên vẫn có thể thấy provider dù configuration con không chứa tên provider trong `modules()`. `Configuration.findModule(...)` cũng tìm được module từ parent configurations nếu phù hợp, còn `modules()` chỉ liệt kê module mới.

### Provider là dependency tường minh

Nếu một root khác có `requires demo.provider`, thuật toán `resolve` sẽ phân giải dependency đó. Tuy nhiên, đối với plugin architecture, ép consumer compile-time phụ thuộc vào provider cụ thể thường làm mất tính thay thế. Chỉ dùng cạnh `requires` khi thật sự có quan hệ API/module dependency, không phải để bù cho service binding còn thiếu.

Điểm phân biệt: **`resolveAndBind` là cơ chế tự động kéo những provider có thể quan sát được theo `uses`/`provides`; `resolve` chỉ làm công việc này nếu có đường phụ thuộc/root khác khiến module đó được phân giải.**

## 7. “Có mặt trên module path” chưa đủ: vai trò của ModuleFinder

`ModuleFinder` xác định những **module definitions có thể được quan sát** để giải quyết dependencies và services. Khi sử dụng:

```java
ModuleFinder before = ModuleFinder.of(Path.of("plugins"));
ModuleFinder after = ModuleFinder.of();
Configuration result = ModuleLayer.boot().configuration()
        .resolveAndBind(before, after, Set.of("demo.app"));
```

Đây là snippet độc lập về ý tưởng: thư mục `plugins` phải chứa module files phù hợp; nếu không có `demo.app` hoặc dependencies, resolution có thể thất bại.

Phải hiểu các giới hạn:

- Nếu provider JAR **không nằm trong bất cứ finder phù hợp nào**, `resolveAndBind` không thể tự tưởng tượng ra nó.
- Resolver tra root/dependency theo thứ tự `before` → parent configurations → `after`; cấu hình/đường dẫn sai có thể chọn module/version khác mong muốn.
- Khi cùng tên module xuất hiện trong các nguồn, cần biết luật finder/parent và kiểm tra artifact/version đã chọn. `resolveAndBind` **không phải bộ giải xung đột dependency**.
- Binding có thể kéo vào **tất cả các module cung cấp một service liên quan mà finder tìm được**; nó không đảm bảo chỉ có một provider hoặc có thứ tự ưu tiên ổn định giữa các module.
- Resolver cũng phải thỏa yêu cầu readability, package consistency và constraints; service binding đưa thêm module nên có thể xuất hiện lỗi cấu hình mà `resolve` không gặp.

Nếu có nhiều plugin, đừng dựa vào việc service binding chọn “provider đầu tiên”. Đưa policy lựa chọn (capability, version, provider ID, quyền, thứ tự ưu tiên) vào registry và kiểm tra `ServiceLoader.Provider.type()`/metadata theo hợp đồng. Khi chỉ được phép một provider, hãy kiểm tra số lượng và báo lỗi cấu hình nếu không đúng.

### Service binding không làm bỏ qua encapsulation

Module consumer nên `requires` module xuất service API, đồng thời `uses` service. Module provider cần `provides` service hợp lệ. Các rule `exports`, accessibility và package/module consistency vẫn được kiểm tra; việc module provider được resolve không biến toàn bộ package của nó thành public API cho consumer.

## 8. Khi nào dùng resolve, khi nào dùng resolveAndBind?

| Nhu cầu | Lựa chọn hợp lý | Lý do |
| --- | --- | --- |
| Tạo graph từ các roots đã chọn và module dependencies tường minh | `resolve` | Chính xác phạm vi module theo roots/`requires` |
| Nạp extension providers qua `uses`/`provides` mà consumer không biết module implementation | `resolveAndBind` | Gắn service-use vào bước phân giải module |
| Plugin deployment đã có allowlist và root modules do operator chọn | `resolve` với roots tường minh, hoặc `resolveAndBind` trên finder đã giới hạn | Giữ policy lựa chọn trong tầng quản lý plugin |
| Cần tự động thấy nhiều provider khả dụng trong plugin repository | `resolveAndBind` | Bổ sung provider modules và dependencies theo services |
| Muốn phát hiện/khởi tạo instance dịch vụ | `ServiceLoader` sau khi layer đã tồn tại | Resolution không tự khởi tạo provider |
| Muốn thay plugin đang chạy | Tạo configuration/layer/snapshot mới theo lifecycle | Reload `ServiceLoader` không tự thêm module chưa được resolve vào layer cũ |

**Cân nhắc khả năng mở rộng:** trong hệ thống nhiều plugin không tin cậy, không nên dùng `resolveAndBind` với một finder quá rộng chỉ để “auto scan toàn bộ”. Service binding có thể đưa thêm modules/dependencies vào graph; phải kiểm tra artifact nguồn, API compatibility, version, quyền và việc khởi tạo provider. Nếu cần giới hạn plugin, cấu hình finder/roots/policy có kiểm soát.

## 9. Các lỗi và ngộ nhận dễ gặp

### “Đã có JAR provider nhưng ServiceLoader trả về rỗng”

Đặt câu hỏi theo thứ tự:

1. JAR là **named module** hợp lệ với `module-info.java` khai báo `provides` chưa?
2. Consumer named module khai báo `uses` service chưa, và có `requires` tới module xuất service API chưa?
3. `ModuleFinder` có thực sự thấy JAR provider không?
4. Configuration được tạo bằng `resolve` hay `resolveAndBind`, provider có phải root/dependency khác không?
5. `Configuration.modules()` có provider không? Provider có nằm ở parent layer không?
6. Runtime `ModuleLayer` có được tạo từ đúng configuration không?
7. `ServiceLoader.load(layer, serviceType)` có nhận **đúng service Class** thuộc layer/module identity phù hợp không?

Với named module, `uses` không có ở module gọi `ServiceLoader` có thể gây `ServiceConfigurationError`; với API module layer, unnamed launcher như trong ví dụ có thể gọi dịch vụ hợp lệ. Ngoài ra, provider phải khởi tạo được hoặc cung cấp provider method hợp lệ; lỗi khởi tạo được phát hiện **khi ServiceLoader thực sự load/instantiate**, không phải tại bước resolve.

### “resolveAndBind sẽ tự tạo các provider object”

Sai. Binding chỉ bổ sung **module definitions** vào graph. Sau khi định nghĩa layer, `ServiceLoader` mới xử lý discovery và lazy instantiation. Với `stream()`, có thể đọc `Provider.type()` mà chưa gọi `Provider.get()`; với `iterator()`, iteration sẽ khởi tạo provider. Đừng dựa vào side effect trong constructor provider tại bước resolve/configuration.

### “ServiceLoader sẽ tự tìm plugin vừa thêm vào thư mục”

Không phải trong một layer cố định. `ServiceLoader.reload()` làm sạch cache của loader đó, không tự sửa `Configuration` hay định nghĩa named module mới. Với plugin mới không có trong graph, thường cần ModuleFinder/configuration/layer mới, cùng quy trình cutover và quản lý vòng đời.

### “resolveAndBind buộc consumer đọc trực tiếp implementation”

Sai. Khả năng đưa provider vào graph và khả năng **đọc package/class qua module readability** là hai quan hệ khác nhau. Consumer thường giữ `requires demo.api` và `uses demo.api.Greeting`; không cần `requires demo.provider`, không cần export implementation package.

### “resolveAndBind luôn thêm đúng một provider”

Sai. Binding phụ thuộc **service-use của modules mới và parents**, cùng tập provider trong finder. Có thể không có provider; có thể có nhiều provider; quá trình có thể lặp và kéo thêm module do dependency/service khác. Hãy kiểm tra kết quả và chính sách lựa chọn ở registry.

### “Resolve thành công thì chắc chắn layer tạo được và provider chạy được”

Chưa đủ. `resolve`/`resolveAndBind` có thể ném `FindException` hay `ResolutionException` khi graph không hợp lệ; **định nghĩa layer** có thể thất bại vì lỗi loader/package; **ServiceLoader** có thể ném `ServiceConfigurationError` khi tìm hoặc khởi tạo provider. Cần log nguyên nhân theo đúng giai đoạn.

## 10. Chẩn đoán theo từng bước, không nhầm ba thời điểm

```text
ModuleFinder
   |
   | discovers module definitions
   v
Configuration.resolve / resolveAndBind
   |
   | graph: roots, requires, [service binding]
   | potential: FindException / ResolutionException
   v
ModuleLayer.defineModulesWithOneLoader / WithManyLoaders
   |
   | runtime modules and class loader mapping
   | potential: layer/class loader errors
   v
ServiceLoader.load(layer, Service.class)
   |
   | lazy discover and instantiate providers
   | potential: ServiceConfigurationError
   v
Registry / application uses service instance
```

Gợi ý quan sát:

- Trước resolution, ghi **tên root**, đường finder và danh sách module version đã chấp thuận; tránh tự động log đường dẫn nhạy cảm.
- Sau resolution, kiểm tra `configuration.modules().stream().map(ResolvedModule::name)` và đồ thị `reads()` khi cần; nhớ `modules()` không bao gồm parent configurations.
- Sau khi tạo layer, kiểm tra `layer.modules()` và `layer.findModule(name)`; phải phân biệt “module được resolve” với “module nằm trong layer thực tế”.
- Với `ServiceLoader`, dùng `stream().map(ServiceLoader.Provider::type)` để xem provider types trước khi chọn và gọi `get()`. Đừng dùng số lượng từ `ServiceLoader.load(Class)` theo TCCL khác với layer định kiểm tra.
- Nếu việc thêm service binding gây lỗi, xem những provider modules mới nào được chọn và dependencies nào của chúng thiếu hoặc xung đột; đừng quy kết ngay cho interface.

Trong cấu hình runtime có reload/hot deployment, **đừng dùng lại class và provider instance từ layer cũ như thể chúng thuộc layer mới**: cùng fully qualified class name có thể là kiểu khác nhau nếu được định nghĩa bởi loader khác. Quản lý snapshot/provider ownership, requests đang chạy và tài nguyên khi chuyển layer.

## 11. Checklist trước khi đưa vào production

- [ ] Consumer khai báo `requires` cho service API và `uses` cho service được tiêu thụ.
- [ ] Provider có `provides ... with ...` chính xác và dependency tới API service.
- [ ] Xác định rõ roots và phạm vi `ModuleFinder`; provider phải observable.
- [ ] Chọn `resolve` nếu muốn chỉ giữ roots/requirements; chọn `resolveAndBind` nếu muốn module provider được thêm qua service binding.
- [ ] Nhớ service binding cũng xét `uses` ở parent configurations và có thể bổ sung nhiều modules theo vòng lặp.
- [ ] Xác minh `configuration.modules()`, parent configurations và phiên bản module trước khi define layer.
- [ ] Define layer từ đúng configuration, chọn class loader phù hợp và dùng đúng `Class<S>` service trong context ấy.
- [ ] Kiểm tra provider bằng `ServiceLoader` tại đúng layer; xử lý trường hợp 0, 1 hoặc nhiều provider theo policy.
- [ ] Bắt và phân loại lỗi resolution, layer definition, service discovery/instantiation riêng.
- [ ] Với plugin động, quản lý phiên bản layer, tài nguyên và in-flight calls khi thay provider.

### Tài liệu chính thức Java 17

- [`Configuration.resolve` và `Configuration.resolveAndBind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html)
- [`ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [`ServiceLoader.load(ModuleLayer, Class)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [`ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html)

**Ghi nhớ:** `resolve` đi theo **roots + requires**, còn `resolveAndBind` mở rộng kết quả bằng **service-use/service-provider binding**; cả hai chỉ tạo `Configuration`. Sau đó vẫn phải **định nghĩa layer và dùng ServiceLoader** để có provider thực sự. Phân biệt đúng các bước giúp việc thiết kế plugin linh hoạt, dễ kiểm soát phạm vi và dễ tìm lỗi khi provider không xuất hiện.