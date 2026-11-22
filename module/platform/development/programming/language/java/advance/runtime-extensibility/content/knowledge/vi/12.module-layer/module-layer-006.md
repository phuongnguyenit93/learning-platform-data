# Provider trong layer hiện tại, layer tổ tiên và giới hạn với module không tên

## 1. Bối cảnh: ModuleLayer định nghĩa phạm vi tìm provider

Trong hệ plugin Java dùng **Java Platform Module System (JPMS)**, host có thể tạo một `ModuleLayer` mới để nạp các **named module** sau khi ứng dụng khởi động. Một layer chứa các module đã được giải quyết bằng một `Configuration` và được ánh xạ tới một hoặc nhiều `ClassLoader`. Các layer có quan hệ **cha/con (parent/child)**, giúp một plugin trong layer con sử dụng những module đã hiện diện ở layer tổ tiên.

Khi ứng dụng khám phá SPI, có hai câu hỏi khác nhau:

1. **Chọn điểm bắt đầu nào để tra cứu?** `ModuleLayer` được truyền vào, hay `ClassLoader` được truyền vào?
2. **Provider đã được đăng ký ở đâu?** Một named module trong layer, hay một unnamed module từ classpath?

Với API Java 17:

```java
ServiceLoader.load(layer, Service.class)
```

thì `ServiceLoader` tìm provider được khai báo trong các **named module thuộc layer đó và các layer tổ tiên**. Đặc tả nói rõ: **overload này không tìm provider trong unnamed module**. Thay đổi thread context classloader hoặc đưa thêm tệp `META-INF/services` vào classpath không biến unnamed provider thành một provider thuộc layer mà overload này tìm kiếm.

Đây là điểm khác biệt cốt lõi với:

```java
ServiceLoader.load(Service.class, loader)
```

Overload theo `ClassLoader` có thể tìm provider trong **cả named module và unnamed module** tùy các module/đường nạp mà loader nhìn thấy. Còn overload một tham số `ServiceLoader.load(Service.class)` dùng thread context classloader, nên thuộc họ tìm kiếm theo `ClassLoader`, không phải truy vấn riêng một `ModuleLayer`.

**Đừng đồng nhất “đã nạp được lớp” với “nằm trong tập provider của layer”.** Thư viện có thể mở được JAR bằng classloader riêng nhưng `ServiceLoader.load(layer, service)` vẫn không tìm provider classpath/unnamed.

## 2. Tầng hiện tại, tổ tiên, hậu duệ và nhánh khác

Một ứng dụng có thể tổ chức layer như sau:

```text
                       L0: ModuleLayer.boot()
                         |    demo.api
                         |
                       L1: parentLayer
                         |    demo.parent (provider P)
                         |
                       L2: childLayer
                              demo.child (provider C)

Classpath (unnamed module):
    demo.classpath.ClasspathGreeter (provider U)
    META-INF/services/demo.spi.Greeter
```

Giả sử cả P, C và U đều triển khai cùng dịch vụ `demo.spi.Greeter`, nhưng:

- P được **công bố bằng `provides ... with ...`** trong named module `demo.parent` thuộc L1.
- C được công bố tương tự trong named module `demo.child` thuộc L2.
- U chỉ được công bố qua tệp `META-INF/services` trong một JAR nằm trên **classpath**, thuộc unnamed module của classloader ứng dụng.

Kết quả về **phạm vi**, khi không có provider khác cho service này:

| Lời gọi | Tập provider có thể tìm thấy | Không được tìm |
|---|---|---|
| `ServiceLoader.load(L2, Greeter.class)` | C ở L2, P ở L1; thêm provider ở L0 nếu có | U ở unnamed module |
| `ServiceLoader.load(L1, Greeter.class)` | P ở L1; thêm provider ở L0 nếu có | C ở layer con L2 và U |
| `ServiceLoader.load(L0, Greeter.class)` | Các provider trong L0 | P/C ở layer hậu duệ và U |
| `ServiceLoader.load(Greeter.class, systemLoader)` | Provider trong named/unnamed modules mà cơ chế tìm kiếm qua systemLoader nhìn thấy; trong cấu hình ví dụ, U | Không có bảo đảm tự quét mọi layer con vừa tạo |

**Tìm kiếm từ con lên cha, không phải từ cha xuống con.** Host đang giữ một reference tới L1 có thể tìm P, nhưng không thể vì vậy mà tự động tìm C vừa được định nghĩa ở L2. Layer cũng không có “thư mục plugin toàn cục” chứa mọi module từng được tạo trong JVM.

### Thứ tự tìm trong nhiều layer cha

Theo `ServiceLoader.load(ModuleLayer, Class)` của Java 17:

1. Tìm provider trong **layer được truyền vào trước**.
2. Sau đó duyệt các **parent layer theo chiều sâu (depth-first)** và đúng thứ tự các parent được đăng ký.
3. Mỗi layer được ghé **tối đa một lần**.
4. **Thứ tự giữa các module trong cùng một layer không được xác định**. Nếu một module khai báo nhiều provider, thứ tự được khai báo trong module descriptor được bảo toàn đối với các provider đó.

Ví dụ hình kim cương có L3 là con của L1 rồi L2 (đều là con của L0): thứ tự thăm layer là **L3 → L1 → L0 → L2**. Không phải lúc nào cũng chỉ là một chuỗi L3 → L2 → L1 → L0, và không được ngầm hiểu thứ tự giữa các module cùng layer là cố định.

Trong hệ plugin, nếu cần ưu tiên provider theo phiên bản, cấu hình hoặc độ tin cậy, host nên **tự chọn/sắp xếp** theo metadata hoặc chính sách, không phụ thuộc hoàn toàn vào thứ tự tình cờ khi duyệt `ServiceLoader`.

## 3. Named module, unnamed module và automatic module

### 3.1. Named module được công bố bằng module descriptor

Một named module rõ ràng (*explicit named module*) có thể khai báo provider:

```java
// Bên trong module-info.java của module demo.child
module demo.child {
    requires demo.api;
    provides demo.spi.Greeter with demo.child.ChildGreeter;
}
```

Đoạn này là **toàn bộ nội dung ví dụ một file module-info.java**. `requires demo.api` làm module plugin phụ thuộc module hợp đồng, còn `provides ... with ...` ghi nhận lớp cung cấp dịch vụ. Trong quá trình định nghĩa module thuộc layer, JVM có thông tin đăng ký provider qua module descriptor.

Module tiêu thụ dịch vụ là **explicit named module** thường cần khai báo:

```java
// Bên trong module-info.java của một module tiêu thụ dịch vụ
module demo.consumer {
    requires demo.api;
    uses demo.spi.Greeter;
}
```

Đây là đoạn minh họa độc lập với chương trình thực hành ở mục 5. Quy tắc `uses` phục vụ tính hợp lệ của lời gọi ServiceLoader trong explicit module. Chương trình thực hành đặt host trên **classpath**, tức host thuộc unnamed module, nên không cần tự có `module-info.java` và `uses`.

**Phân biệt:** `requires` chỉ diễn tả khả năng đọc module API, không thay `uses` ở phía module tiêu thụ và không thay `provides` ở phía provider.

### 3.2. Unnamed module trên classpath

JAR trên classpath không có module descriptor được định nghĩa như một named module. Các lớp của nó thuộc **unnamed module** của classloader tương ứng. Đăng ký provider truyền thống dùng:

```text
META-INF/services/demo.spi.Greeter
```

với nội dung:

```text
demo.classpath.ClasspathGreeter
```

Đó là cách làm hợp lệ cho `ServiceLoader.load(Greeter.class, someLoader)` khi loader có thể thấy JAR và lớp provider. Nhưng `ServiceLoader.load(layer, Greeter.class)` **không quét unnamed module**, cho dù đường classpath có tệp này và classloader chứa lớp đó đang hoạt động.

### 3.3. Automatic module không đồng nghĩa unnamed module

Một JAR **đặt trên module path** nhưng không có `module-info.class` có thể được hệ thống coi là **automatic module** (named module khi được resolve). Tên module có thể được khai báo trong manifest (`Automatic-Module-Name`) hoặc suy ra từ tên JAR. Đối với automatic module, metadata `META-INF/services` có thể góp phần hình thành phần mô tả provider.

Vì thế, mệnh đề đúng là **“overload theo layer không tìm provider trong unnamed module”**, chứ không phải “chỉ module có file `module-info.java` mới có thể tham gia layer” hoặc “overload theo layer không bao giờ quan tâm `META-INF/services`”. Một automatic module đã được resolve và định nghĩa vào layer là **named module**, khác với cùng JAR ở classpath/unnamed module.

Cần kiểm tra **vị trí JAR, cách resolve module và layer mà module thực sự thuộc về**, không chỉ nhìn xem JAR có chứa tệp descriptor hay không.

## 4. Định nghĩa layer không đồng nghĩa đã kích hoạt plugin

Để tạo một layer động, host thường thực hiện:

1. Dùng `ModuleFinder` chỉ tới đường dẫn module, ví dụ thư mục biên dịch hoặc modular JAR.
2. Dùng `Configuration.resolve(...)` để giải quyết root module và phụ thuộc từ cấu hình layer cha.
3. Dùng `ModuleLayer.defineModulesWithOneLoader(...)` hoặc `defineModulesWithManyLoaders(...)` để tạo layer và các classloader phục vụ định nghĩa module.
4. Gọi `ServiceLoader.load(layer, Service.class)` để khám phá provider của layer và tổ tiên.
5. Duyệt provider và tạo instance khi cần; sau đó host mới gọi phương thức lifecycle nghiệp vụ như `start()` nếu hợp đồng có quy định.

`ModuleLayer` là **ranh giới tổ chức module và quan hệ cha/con**; nó không phải bản thân một plugin manager. `ServiceLoader` cũng không tự thực hiện xác thực tin cậy, rollback, giới hạn tài nguyên hay gỡ plugin.

Một lỗi thiết kế hay gặp là nghĩ rằng đã gọi `defineModulesWithOneLoader` thì mọi provider sẽ lập tức được tạo đối tượng. Trên thực tế, việc khai báo/provider discovery và việc khởi tạo provider có thể diễn ra tại những thời điểm khác nhau, tùy thao tác `ServiceLoader` và cách host duyệt kết quả.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai layer và một unnamed provider

Ví dụ này dùng **một dịch vụ trong named module demo.api ở boot layer**, hai plugin ở hai layer được tạo động, và một provider JAR trên classpath. Mục tiêu là chứng minh đồng thời:

- Truy vấn **parent layer** chỉ lấy provider từ parent/boot.
- Truy vấn **child layer** lấy cả provider trong child và trong parent.
- Cả hai truy vấn theo `ModuleLayer` đều **không lấy provider từ unnamed module**.
- Truy vấn bằng **application classloader** có thể lấy provider classpath, nhưng không vì thế tự quét mọi module trong hai layer con.

### 5.1. Sơ đồ tệp nguồn

```text
layer-demo/
├── api/
│   ├── module-info.java
│   └── demo/spi/Greeter.java
├── parent/
│   ├── module-info.java
│   └── demo/parent/ParentGreeter.java
├── child/
│   ├── module-info.java
│   └── demo/child/ChildGreeter.java
├── unnamed/
│   └── demo/classpath/ClasspathGreeter.java
├── unnamed-resources/
│   └── META-INF/services/demo.spi.Greeter
└── host/
    └── demo/host/Main.java
```

Các đường dẫn nguồn là **tương đối từ thư mục `layer-demo`**. Các module biên dịch được đặt trong những thư mục `mods/api`, `mods/parent` và `mods/child` riêng; file `module-info.class` nằm ở gốc từng thư mục module. Provider classpath được đóng gói thành một JAR độc lập.

### 5.2. Service API tại boot layer

**`api/module-info.java`**

```java
module demo.api {
    exports demo.spi;
}
```

**`api/demo/spi/Greeter.java`**

```java
package demo.spi;

public interface Greeter {
    String id();
}
```

`demo.api` xuất package để named module parent/child và host trên classpath cùng nhìn thấy **một định danh kiểu** `Greeter`. Lệnh chạy sẽ dùng `--add-modules demo.api` để đưa module API vào boot layer.

### 5.3. Provider ở parent layer

**`parent/module-info.java`**

```java
module demo.parent {
    requires demo.api;
    provides demo.spi.Greeter with demo.parent.ParentGreeter;
}
```

**`parent/demo/parent/ParentGreeter.java`**

```java
package demo.parent;

import demo.spi.Greeter;

public final class ParentGreeter implements Greeter {
    public ParentGreeter() {
    }

    @Override
    public String id() {
        return "parent";
    }
}
```

`demo.parent` là named module khai báo provider ngay trong descriptor, không cần `META-INF/services` cho ví dụ này.

### 5.4. Provider ở child layer

**`child/module-info.java`**

```java
module demo.child {
    requires demo.api;
    provides demo.spi.Greeter with demo.child.ChildGreeter;
}
```

**`child/demo/child/ChildGreeter.java`**

```java
package demo.child;

import demo.spi.Greeter;

public final class ChildGreeter implements Greeter {
    public ChildGreeter() {
    }

    @Override
    public String id() {
        return "child";
    }
}
```

`demo.child` được resolve trong configuration có parent là configuration của `parentLayer`; sau đó mới được định nghĩa thành `childLayer`.

### 5.5. Provider ở unnamed module

**`unnamed/demo/classpath/ClasspathGreeter.java`**

```java
package demo.classpath;

import demo.spi.Greeter;

public final class ClasspathGreeter implements Greeter {
    public ClasspathGreeter() {
    }

    @Override
    public String id() {
        return "unnamed";
    }
}
```

**`unnamed-resources/META-INF/services/demo.spi.Greeter`**, chỉ có một dòng:

```text
demo.classpath.ClasspathGreeter
```

Lớp này được đóng gói trong JAR **chỉ đưa vào application classpath**, không resolve như module trong parent/child layer.

### 5.6. Host tạo layer và liệt kê provider

**`host/demo/host/Main.java`**

```java
package demo.host;

import demo.spi.Greeter;
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    private static String names(ServiceLoader<Greeter> services) {
        return services.stream()
                .map(provider -> provider.get().id())
                .sorted()
                .toList()
                .toString();
    }

    public static void main(String[] args) {
        ModuleLayer boot = ModuleLayer.boot();

        Configuration parentConfig =
                boot.configuration().resolve(
                        ModuleFinder.of(Path.of("mods/parent")),
                        ModuleFinder.of(),
                        Set.of("demo.parent"));

        ModuleLayer parentLayer =
                boot.defineModulesWithOneLoader(
                        parentConfig, ClassLoader.getSystemClassLoader());

        Configuration childConfig =
                parentLayer.configuration().resolve(
                        ModuleFinder.of(Path.of("mods/child")),
                        ModuleFinder.of(),
                        Set.of("demo.child"));

        ModuleLayer childLayer =
                parentLayer.defineModulesWithOneLoader(
                        childConfig, ClassLoader.getSystemClassLoader());

        System.out.println("parent=" + names(
                ServiceLoader.load(parentLayer, Greeter.class)));
        System.out.println("child=" + names(
                ServiceLoader.load(childLayer, Greeter.class)));
        System.out.println("classpath=" + names(
                ServiceLoader.load(
                        Greeter.class, ClassLoader.getSystemClassLoader())));
    }
}
```

**Giải thích mã host:**

- `boot` đã có `demo.api`; host dùng module này làm hợp đồng chung.
- `parentConfig` giải quyết `demo.parent` dựa trên cấu hình boot; `parentLayer` được tạo với boot là cha.
- `childConfig` giải quyết `demo.child` dựa trên cấu hình parent; `childLayer` có `parentLayer` là cha.
- Cả parent và child dùng overload `defineModulesWithOneLoader`: **mỗi layer có một loader cho các module trong chính layer đó**, không có nghĩa cả hai layer có cùng một loader.
- `names(...)` tạo provider instance bằng `Provider.get()`, lấy chuỗi định danh và **sắp xếp alphabet** để đầu ra xác định. Thứ tự sắp xếp này do ví dụ quyết định, không phải cam kết thứ tự của ServiceLoader.
- Host là lớp trên classpath, thuộc unnamed module, nhưng nó gọi được `ServiceLoader.load(layer, ...)` để khám phá provider từ **named modules trong layer**. Việc *caller là unnamed module* không đồng nghĩa *provider trong unnamed module* cũng được tìm bằng overload này.

### 5.7. Biên dịch và chạy trên Windows PowerShell với JDK 17+

Chạy các lệnh từ thư mục `layer-demo`, nơi có đúng cấu trúc ở trên:

```powershell
New-Item -ItemType Directory -Force -Path mods\api,mods\parent,mods\child,out\host,out\unnamed,lib | Out-Null

javac -d mods\api api\module-info.java api\demo\spi\Greeter.java

javac --module-path mods\api -d mods\parent parent\module-info.java parent\demo\parent\ParentGreeter.java

javac --module-path mods\api -d mods\child child\module-info.java child\demo\child\ChildGreeter.java

javac --module-path mods\api --add-modules demo.api -d out\unnamed unnamed\demo\classpath\ClasspathGreeter.java

Copy-Item -Path unnamed-resources\META-INF -Destination out\unnamed -Recurse
jar --create --file lib\unnamed-provider.jar -C out\unnamed .

javac --module-path mods\api --add-modules demo.api -d out\host host\demo\host\Main.java

java --module-path mods\api --add-modules demo.api -cp "out\host;lib\unnamed-provider.jar" demo.host.Main
```

Đầu ra chuẩn:

```text
parent=[parent]
child=[child, parent]
classpath=[unnamed]
```

Ví dụ này chủ động chỉ có ba provider nêu trên; không cài thêm module/provider cùng service. `parent` không lấy `child` vì L2 là hậu duệ của L1. `child` lấy được cả hai named providers trong L2 và L1. Cả hai truy vấn theo layer **bỏ qua** provider classpath. Truy vấn theo system classloader đọc descriptor của unnamed JAR và tìm `unnamed`; systemLoader trong cấu hình này không phải classloader đã định nghĩa các module của hai layer động.

**Ghi chú hệ điều hành:** trên macOS/Linux, dùng `/` cho đường dẫn, `:` làm dấu phân cách classpath và dùng lệnh shell tạo thư mục/sao chép tương đương. Bộ lệnh trên dành riêng cho PowerShell, tránh nhập nguyên xi vào Bash.

**Không chạy với module path chứa cả `mods/parent` hoặc `mods/child` ở thời điểm khởi động** nếu muốn quan sát việc tạo layer động. Chỉ `demo.api` phải có mặt ở boot layer; hai module provider được tìm qua `ModuleFinder.of(...)` khi host chạy.

### 5.8. Thử nghiệm thay đổi một điều kiện

**Thử A — gọi từ parent:**

```java
ServiceLoader.load(parentLayer, Greeter.class)
```

Không tìm provider `child`. Vì vậy, nếu host chỉ có parentLayer nhưng muốn tìm plugin mới ở childLayer, host phải giữ và sử dụng chính reference của childLayer (hoặc một cơ chế registry chủ động).

**Thử B — bỏ unnamed JAR khỏi classpath:** giá trị `classpath=[]`, trong khi `parent=[parent]` và `child=[child, parent]` không đổi. Nếu bỏ cả `META-INF/services` nhưng vẫn đặt class `ClasspathGreeter` trong JAR, lookup theo classloader cũng không tự phát hiện provider này.

**Thử C — chỉ đổi TCCL:** trong mô hình trên, thay `Thread.currentThread().setContextClassLoader(...)` không thay đổi **tập layer** của `ServiceLoader.load(childLayer, Greeter.class)`; tham số layer quyết định phạm vi. Tuy nhiên, TCCL có thể ảnh hưởng mã của thư viện hoặc provider dùng các API tra cứu khác trong lúc thực thi. Khi phải thay TCCL, luôn khôi phục bằng `finally`.

**Thử D — thêm provider khác vào parent module:** khi provider được khai báo hợp lệ bằng `provides`, cả parent và child lookup có thể thấy provider mới này. Không nên dựa vào vị trí của nó trong danh sách nếu có nhiều provider ở cùng layer; hãy sắp xếp theo chính sách ứng dụng.

## 6. Các giới hạn thiết yếu khi thiết kế hệ plugin theo ModuleLayer

### 6.1. Không tìm xuống child/sibling layer

Nếu một host có nhiều lớp plugin như L1, L2a, L2b là các layer cùng cha, `ServiceLoader.load(L2a, Service.class)` không tự khám phá provider của L2b chỉ vì chúng là “anh em”. Tương tự, tìm từ L1 không khám phá provider thuộc L2a hoặc L2b. Hãy xác định rõ **layer nào là context** cho từng lần tìm.

### 6.2. “Named” là điều kiện cần nhưng vẫn phải có khai báo provider

Một named module có class `MyProvider implements Service` không có nghĩa ServiceLoader tự quét tất cả class để tìm implementation. Explicit module cần `provides ... with ...` (hoặc cơ chế đăng ký tương ứng được đặc tả). Automatic module là trường hợp khác đã nói ở mục 3. Nạp được class không đồng nghĩa module đã **công bố service provider**.

### 6.3. Yêu cầu về module tiêu thụ và khả năng truy cập dịch vụ

- Explicit module có mã gọi `ServiceLoader.load(...)` phải khai báo `uses` cho service; nếu không, có thể nhận `ServiceConfigurationError`.
- Nếu service type nằm trong module khác, module tiêu thụ cũng cần `requires` thích hợp và khả năng truy cập package mà type được xuất từ đó.
- Provider module cần `requires` service API và khai báo `provides ... with ...` hợp lệ. Lớp provider phải thỏa quy tắc về kiểu, constructor/factory và khả năng tải theo JPMS.
- Trong ví dụ, host là unnamed module; nó đọc được `demo.api` sau khi `--add-modules demo.api` giải quyết API vào boot layer. Lệnh startup cụ thể là một phần của ví dụ, không thể bỏ tùy tiện.

**Không suy đoán chỉ dựa trên classloader visibility.** Trong JPMS, module readability, exports/opens, tên module và cách resolve Configuration đều ảnh hưởng khả năng dùng kiểu và tài nguyên.

### 6.4. Cảnh giác với định danh lớp và trùng API

Nếu plugin đóng gói một bản riêng của `demo.spi.Greeter` và bộ nạp của nó thực sự định nghĩa bản đó, JVM có thể coi hai kiểu `demo.spi.Greeter` là khác nhau dù tên giống hệt. Provider lúc ấy có thể không được ServiceLoader chấp nhận như subtype của service mà host chờ đợi. Mọi provider nên thống nhất **module API và định danh lớp của hợp đồng**; sửa lỗi này không đơn giản bằng cách đổi TCCL.

### 6.5. Không coi layer là sandbox hoặc hot-reload hoàn chỉnh

Tạo layer mới không tự cô lập I/O, mạng, thread hoặc mã không tin cậy. Đóng file/JAR hay bỏ reference tới một `ModuleLayer` cũng không bảo đảm class được unload ngay. Thread, cache, `ServiceLoader`, instance hoặc callback còn giữ classloader có thể làm tài nguyên sống lâu hơn mong muốn. Host phải quản lý vòng đời plugin và tài nguyên.

### 6.6. Thứ tự và cache

`ServiceLoader` tải provider lười khi duyệt và có cache provider theo **đối tượng ServiceLoader**. Nếu thay đổi cấu hình layer hoặc phát hành phiên bản plugin mới, đừng giả định một đối tượng ServiceLoader đã tạo tự động thấy layer mới. Thông thường muốn nạp module/version mới cần **tạo configuration/layer phù hợp**, sau đó tạo ServiceLoader mới với layer mới và giải phóng tham chiếu vòng đời cũ. `reload()` chỉ đặt lại cache provider của cùng ServiceLoader, không tự thay đổi cấu trúc module layer.

### 6.7. Lỗi thường gặp và cách khoanh vùng

| Dấu hiệu | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| `load(parentLayer, service)` không có provider từ child | Tra cứu chỉ đi tới tổ tiên, không đi xuống hậu duệ | Gọi với `childLayer` nếu muốn thấy child và ancestors |
| Provider ở classpath không xuất hiện từ `load(layer, service)` | Unnamed module bị loại trừ theo đặc tả overload này | Dùng overload theo classloader cho provider classpath hoặc đưa module vào layer đúng nghĩa |
| `ResolutionException` khi resolve | Module phụ thuộc không tìm thấy hoặc xung đột cấu hình | Kiểm tra module path, root modules, `requires` và cấu hình cha |
| `LayerInstantiationException` khi định nghĩa layer | Không thể định nghĩa module/classloader theo ràng buộc JPMS | Kiểm tra package trùng, module tên trùng trong loader hoặc ánh xạ loader |
| `ServiceConfigurationError` khi tìm/khởi tạo | `uses` thiếu, provider sai hoặc không thể khởi tạo | Kiểm tra descriptor, class constructor/factory và `cause` |
| `ClassCastException` hoặc “not a subtype” | API/SPI được định nghĩa thành nhiều kiểu khác nhau | Kiểm tra nguồn của service type và loader định nghĩa provider |
| Danh sách provider thay đổi thứ tự | Thứ tự giữa module cùng layer không xác định | Sắp xếp theo metadata/ưu tiên trước khi lựa chọn |
| Không thấy plugin sau thay JAR | Layer/loader/ServiceLoader cũ còn được dùng | Xác định lại layer, quản lý cache và lifecycle |

## 7. Câu hỏi tự kiểm tra

1. **ServiceLoader.load(childLayer, Service.class) có tìm provider trong parentLayer không?** Có, nếu chúng được công bố trong named modules hợp lệ ở layer cha và thỏa điều kiện khám phá.
2. **ServiceLoader.load(parentLayer, Service.class) có tìm provider trong childLayer không?** Không; tìm kiếm đi theo layer hiện tại và tổ tiên, không duyệt hậu duệ.
3. **Tại sao provider JAR có `META-INF/services` trên classpath không được tìm từ overload theo layer?** Vì provider đó thuộc unnamed module; overload `load(ModuleLayer, Class)` loại trừ unnamed modules.
4. **Một automatic module có phải unnamed module không?** Không; automatic module là named module khi đã được resolve vào layer. Không thể chỉ nhìn việc có/không có `module-info.java` mà quyết định.
5. **Vì sao phải có `uses` và `provides`?** Chúng nêu rõ nhu cầu sử dụng SPI và quan hệ cung cấp implementation cho JPMS; `requires` không thay thế hai khai báo này.
6. **Có bảo đảm provider trong layer con luôn đứng trước mọi provider layer cha?** Có về thứ tự thăm *layer* theo đặc tả. Nhưng thứ tự giữa các module trong cùng một layer không xác định; không nên thiết kế ưu tiên nghiệp vụ dựa hoàn toàn vào iterator.
7. **TCCL có biến classpath provider thành provider của layer không?** Không. Nó tham gia lựa chọn classloader đối với API dùng classloader, không thay đổi tập module của overload theo layer.
8. **Vì sao cần sắp xếp `names(...)` trong ví dụ?** Để stdout ổn định và minh họa rõ phạm vi; đó là quy tắc của ví dụ chứ không phải bảo đảm thứ tự provider từ ServiceLoader.

**Bài tập:** thêm một named module `demo.sibling` vào layer anh em của `childLayer`, khai báo cùng dịch vụ. Hãy dự đoán và kiểm tra rằng tìm từ `childLayer` không tự thấy provider trong sibling. Sau đó thêm hai provider cùng một layer, đối chiếu `ServiceLoader.stream()` với kết quả đã sắp xếp để thấy sự khác nhau giữa thứ tự discovery và chính sách chọn provider.

## Tài liệu tham khảo

- Oracle Java SE 17, `ServiceLoader` — đặc biệt overload `load(ModuleLayer, Class)` và `load(Class, ClassLoader)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17, `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Oracle Java SE 17, `Configuration` và `ModuleFinder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html
- Java Language Specification 17, Chương 7 — modules và service directives: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
