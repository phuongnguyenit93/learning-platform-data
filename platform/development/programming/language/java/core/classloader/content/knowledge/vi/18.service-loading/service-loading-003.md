# `uses` và `provides` trong `module-info.java`: khai báo và nạp dịch vụ Java

## 1. Vấn đề cần giải quyết

Một ứng dụng Java thường cần mở rộng chức năng bằng nhiều cách cài đặt của **cùng một hợp đồng**: bộ định dạng dữ liệu, hệ lưu trữ, driver, công cụ chuyển đổi hoặc plugin. Nếu ứng dụng biết cứng tên mọi lớp triển khai rồi gọi `new` trực tiếp, nó bị gắn chặt với những triển khai cụ thể. **Service Provider Interface (SPI)** cùng `java.util.ServiceLoader` cho phép ứng dụng khai báo **mình sử dụng dịch vụ nào**, còn các thư viện triển khai **công bố khả năng cung cấp dịch vụ**.

Khi dùng **Java Platform Module System (JPMS)** từ Java 9, hai khai báo trọng tâm nằm trong `module-info.java`:

```java
uses com.example.spi.GreetingService;
```

và:

```java
provides com.example.spi.GreetingService
        with com.example.provider.EnglishGreeting;
```

Đây là **hai mảnh khai báo** trong hai module descriptor khác nhau, chưa phải chương trình chạy hoàn chỉnh.

- **`uses ServiceType;`** đặt trong **module sử dụng** dịch vụ. Nó công bố rằng mã của module có thể tìm provider cho service type đó bằng `ServiceLoader`.
- **`provides ServiceType with ProviderType1, ProviderType2;`** đặt trong **module cung cấp**. Nó đăng ký provider cho service type. `with` liệt kê tên provider class; đây là khai báo module, không phải lệnh tự động chạy constructor.
- **`ServiceLoader.load(ServiceType.class)`** là lời gọi runtime **khám phá và lấy provider** theo quy tắc module/class loader tương ứng.
- **`requires` và `exports`** hỗ trợ khả năng đọc, thấy **kiểu service API**, nhưng **không thay cho `uses` hoặc `provides`**.

Mục tiêu bài học là giải thích ngữ nghĩa, cơ chế resolution và class loading, code Java 17+ chạy được, cách bố trí file, lỗi thường gặp và sự khác biệt với cơ chế `META-INF/services` của classpath truyền thống.

## 2. Bốn vai trò trong kiến trúc dịch vụ

Giả sử có hợp đồng `GreetingService` và hai triển khai tiếng Anh, tiếng Việt:

```text
learning.services.api
    └── learning.services.api.GreetingService  (service interface)
                    ^
                    |
           công bố/triển khai
               /        \
              /          \
learning.services.en   learning.services.vi
provides ... with ...  provides ... with ...
              \          /
               \        /
                v      v
        learning.services.app
        requires API; uses API
        ServiceLoader.load(...)
```

Có bốn khái niệm cần giữ riêng:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Service** | Hợp đồng interface hoặc abstract class mà consumer muốn dùng | `GreetingService` |
| **Service consumer** | Module gọi `ServiceLoader` để lấy triển khai | `learning.services.app` |
| **Service provider** | Module đăng ký một/một số provider bằng `provides ... with ...` | `learning.services.en` |
| **Provider implementation** | Lớp thực hiện hợp đồng hoặc lớp cung cấp factory `provider()` hợp lệ | `EnglishGreeting` |

**Module provider** không đồng nghĩa **đối tượng provider**. Một module có thể đăng ký nhiều provider types, và một service có thể nhận nhiều provider từ các module khác nhau. Thứ tự phát hiện provider không nên được dùng làm chính sách ưu tiên ứng dụng.

### Phân biệt `requires`, `exports`, `uses`, `provides`

| Chỉ thị trong module-info.java | Ai khai báo? | Ý nghĩa |
| --- | --- | --- |
| `requires learning.services.api;` | Consumer và provider đều có thể cần | Cho module đọc module chứa kiểu API |
| `exports learning.services.api;` | Module API | Cho phép module khác truy cập các kiểu public trong package API |
| `uses learning.services.api.GreetingService;` | Module gọi `ServiceLoader` | Công bố quyền/hợp đồng sử dụng một loại service |
| `provides learning.services.api.GreetingService with ...;` | Module provider | Công bố một provider của service cho cơ chế khám phá |
| `opens package.name;` | Module cần reflective access theo quy tắc JPMS | Không tự động đăng ký service provider |
| `requires static ...;` | Module có dependency tùy chọn lúc runtime | Không thay cho đăng ký provider |

**Điểm cốt lõi:** `requires provider.module` không phải cơ chế thích hợp để “khám phá” provider khi consumer chỉ muốn biết service API. Consumer cần khai báo `uses` và duy trì hợp đồng SPI; provider được công bố qua `provides`, còn module resolution/service binding quyết định provider nào tham gia graph tại runtime.

## 3. Cú pháp và quy tắc cơ bản

### 3.1. `uses`

Trong module descriptor:

```java
module learning.services.app {
    requires learning.services.api;
    uses learning.services.api.GreetingService;
}
```

Module consumer đọc module API và khai báo mình dùng service type đó. Cú pháp `uses` nhận **tên kiểu** (*type name*), không nhận tên file, tên JAR hay object instance.

Nếu named module gọi cơ chế `ServiceLoader.load(...)` cho một service type mà module này **không khai báo `uses`**, quá trình tải có thể thất bại bằng `ServiceConfigurationError` nêu việc module caller không khai báo dùng service đó (theo API `ServiceLoader`). Không nên bỏ qua `uses` chỉ vì module đã `requires` module API.

### 3.2. `provides ... with ...`

Trong module cung cấp:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

Provider type cần đáp ứng điều kiện đăng ký hợp lệ. Trường hợp thông thường là một **public provider class** triển khai service interface và có **public no-argument constructor**.

Đối với **explicit named module**, `ServiceLoader` còn hỗ trợ **provider factory method** có tên `provider` theo quy tắc API, thay vì bắt buộc lớp provider được khai báo trực tiếp implements service. Ta sẽ phân biệt hai cách ở phần nâng cao.

### 3.3. Có bắt buộc `exports` package implementation không?

**Không.** Module `learning.services.en` có thể đặt `EnglishGreeting` trong package `learning.services.en.internal` và **không export package này**. ServiceLoader có cơ chế hỗ trợ nạp provider được module descriptor khai báo hợp lệ mà không cần consumer truy cập trực tiếp lớp implementation. Consumer chỉ lập trình theo interface public được export từ module API.

Nếu consumer cố import/call trực tiếp `learning.services.en.internal.EnglishGreeting`, trình biên dịch hoặc module access checks sẽ từ chối khi package không được export; đây không phải lỗi của `ServiceLoader`.

## 4. Demo Java 17 hoàn chỉnh: 1 service, 2 providers, 1 consumer

Ví dụ sử dụng bốn **explicit named modules**:

1. `learning.services.api` định nghĩa hợp đồng `GreetingService`.
2. `learning.services.en` cung cấp provider tiếng Anh.
3. `learning.services.vi` cung cấp provider tiếng Việt.
4. `learning.services.app` khai báo `uses` và gọi `ServiceLoader`.

Không cần dependency ngoài JDK, Maven hay Gradle. Dùng JDK 17+ có `javac` và `java`.

### 4.1. Cấu trúc thư mục

```text
src/
├── learning.services.api/
│   ├── module-info.java
│   └── learning/services/api/GreetingService.java
├── learning.services.en/
│   ├── module-info.java
│   └── learning/services/en/internal/EnglishGreeting.java
├── learning.services.vi/
│   ├── module-info.java
│   └── learning/services/vi/internal/VietnameseGreeting.java
└── learning.services.app/
    ├── module-info.java
    └── learning/services/app/Main.java
```

Tên thư mục dưới `src` tương ứng tên module; `javac --module-source-path src` sử dụng quy ước layout này.

### 4.2. Service API module

File `src/learning.services.api/module-info.java`:

```java
module learning.services.api {
    exports learning.services.api;
}
```

File `src/learning.services.api/learning/services/api/GreetingService.java`:

```java
package learning.services.api;

public interface GreetingService {
    String code();
    String greet(String name);
}
```

`exports` cho phép consumer và provider **sử dụng kiểu public** `GreetingService` ở package API. Nếu thiếu export (và không có cơ chế truy cập khác), module khác không thể viết `implements GreetingService` theo cách này.

### 4.3. Provider tiếng Anh

File `src/learning.services.en/module-info.java`:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

File `src/learning.services.en/learning/services/en/internal/EnglishGreeting.java`:

```java
package learning.services.en.internal;

import learning.services.api.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {}

    @Override
    public String code() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Lớp provider public, implements interface, có public constructor không tham số. Package `internal` **không export** từ provider module, nhưng `provides ... with ...` vẫn hợp lệ.

### 4.4. Provider tiếng Việt

File `src/learning.services.vi/module-info.java`:

```java
module learning.services.vi {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.vi.internal.VietnameseGreeting;
}
```

File `src/learning.services.vi/learning/services/vi/internal/VietnameseGreeting.java`:

```java
package learning.services.vi.internal;

import learning.services.api.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {}

    @Override
    public String code() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

Một service interface có thể có nhiều provider; mỗi provider được đăng ký trong module descriptor của module chứa provider đó.

### 4.5. Consumer module

File `src/learning.services.app/module-info.java`:

```java
module learning.services.app {
    requires learning.services.api;
    uses learning.services.api.GreetingService;
}
```

File `src/learning.services.app/learning/services/app/Main.java`:

```java
package learning.services.app;

import java.util.ServiceLoader;
import java.util.SortedMap;
import java.util.TreeMap;
import learning.services.api.GreetingService;

public final class Main {
    public static void main(String[] args) {
        SortedMap<String, String> results = new TreeMap<>();

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {
            results.put(provider.code(), provider.greet("Java"));
        }

        System.out.println("providers=" + results.size());
        results.forEach((code, message) ->
                System.out.println(code + "=" + message));
    }
}
```

**Vì sao chọn `TreeMap`?** `ServiceLoader` có thể tìm nhiều provider và không nên coi thứ tự cung cấp của chúng là thứ tự ưu tiên nghiệp vụ. `TreeMap` sắp xếp theo `code()`, giúp **stdout có thứ tự ổn định** `en` trước `vi`, miễn mỗi provider trả một mã riêng.

**Vì sao không import EnglishGreeting trong Main?** Consumer chỉ phụ thuộc vào exported service interface; lớp implementation nằm trong package không export và có thể thay đổi độc lập.

### 4.6. Biên dịch theo module-source-path

Đặt terminal tại thư mục chứa `src`:

```bash
javac -encoding UTF-8 --release 17 --module-source-path src -d mods -m learning.services.api,learning.services.en,learning.services.vi,learning.services.app
```

Lệnh biên dịch các module cùng những source files theo layout `--module-source-path` vào `mods/<module-name>/...`. `-encoding UTF-8` giúp source tiếng Việt được giải mã nhất quán khi trình biên dịch chạy trên hệ điều hành có charset mặc định khác.

### 4.7. Chạy với các provider module được resolve

```bash
java --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

Giải thích:

- `--module-path mods` chỉ vị trí các module được biên dịch.
- `--module learning.services.app/learning.services.app.Main` chỉ định module và main class.
- `--add-modules learning.services.en,learning.services.vi` yêu cầu hai provider module được đưa vào root set và giải quyết trong module graph, để demo không phụ thuộc vào suy đoán về service binding mặc định của môi trường launcher.
- Consumer vẫn **không import** bất kỳ provider implementation nào; `ServiceLoader` khám phá chúng qua descriptor.

**Stdout dự kiến khi chạy trong môi trường JDK 17+ bình thường:**

```text
providers=2
en=Hello, Java
vi=Xin chào, Java
```

Thứ tự ở đây đến từ `TreeMap`; không phải lời hứa về thứ tự nguyên bản của `ServiceLoader`.

### 4.8. Những gì đã xảy ra tại runtime

1. Module graph chứa `learning.services.api`, `learning.services.app` và hai provider modules.
2. Consumer đọc kiểu `GreetingService` từ API module nhờ `requires` + `exports`.
3. `uses` của consumer công bố service mà consumer có quyền khám phá.
4. `provides` trong các provider module đăng ký các lớp implement.
5. `ServiceLoader.load(GreetingService.class)` tạo công cụ khám phá; khi lặp provider, Java tìm rồi khởi tạo các provider thích hợp.
6. `GreetingService.code()/greet()` được gọi qua interface; không cần API truy cập trực tiếp các package `internal`.
7. Kết quả được sort và in ra; không có cam kết về ưu tiên của provider bên trong `ServiceLoader`.

**Lưu ý:** việc có provider module trên module path **chưa đủ** để mọi API khám phá nhìn thấy; module phải được đưa vào cấu hình module layer/graph thích hợp. `--add-modules` trong demo là cách làm rõ điều kiện này. Trong các launcher thực tế, dịch vụ cũng có thể được bind bởi module resolution hoặc application framework.

## 5. `ServiceLoader` có thực hiện việc gì ngay tại load()?

`ServiceLoader.load(ServiceType.class)` tạo một đối tượng `ServiceLoader<ServiceType>`; provider được tìm/khởi tạo **theo cơ chế lazy** khi iterator hoặc stream được sử dụng. Đây không phải cú pháp thay thế của `new EnglishGreeting()` và không bảo đảm ngay lúc gọi `load(...)` đã tạo tất cả provider objects.

Ví dụ snippet trong consumer có `uses GreetingService`:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.getClass().getName());
}
```

Đây là snippet **không độc lập** (cần import, service module và provider phù hợp).

Một số API quan trọng:

| API | Công dụng |
| --- | --- |
| `ServiceLoader.load(Service.class)` | Dùng context class loader thích hợp theo API và quyền module caller |
| `ServiceLoader.load(Service.class, loader)` | Tra với class loader được chỉ định theo semantics API; vẫn có kiểm tra module caller |
| `ServiceLoader.load(layer, Service.class)` | Khám phá provider trong module layer được chỉ định và các layer cha theo hợp đồng |
| `iterator()` hoặc vòng `for` | Lần lượt lấy/khởi tạo provider instances |
| `stream()` | Truy cập `ServiceLoader.Provider<S>` để xem type và lấy instance thông qua `get()` |
| `reload()` | Xóa cache provider của ServiceLoader; lần lặp sau tìm lại theo cơ chế API |
| `ServiceConfigurationError` | Lỗi cấu hình service/provider, lớp không hợp lệ hoặc lỗi khi tìm/khởi tạo provider |

`reload()` **không** gỡ các lớp đã được JVM định nghĩa hoặc tự thay đổi mọi runtime class từ JAR cũ. Nếu plugin được cập nhật, có thể còn phải tạo module layer/class loader mới và quản lý reference vòng đời.

**TCCL:** `Thread.currentThread().getContextClassLoader()` có thể ảnh hưởng các overload của `ServiceLoader` sử dụng context loader, nhất là provider trên classpath hay framework tùy chỉnh. Nhưng thay TCCL không “cấp” `uses` cho named module caller, cũng không đổi defining loader của lớp đã được nạp.

## 6. Service provider có cần export package implementation?

Không. Một mục tiêu của JPMS service mechanism là **che implementation detail nhưng cho phép service discovery**.

Ví dụ:

```java
module learning.services.en {
    requires learning.services.api;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

Chỉ thị trên **không export** `learning.services.en.internal`. Consumer gọi interface `GreetingService`, không cần nhìn thấy implementation package.

Cần tránh cách sửa sai:

```java
module learning.services.en {
    requires learning.services.api;
    exports learning.services.en.internal;
    provides learning.services.api.GreetingService
        with learning.services.en.internal.EnglishGreeting;
}
```

Đây là **đoạn cấu hình có thể biên dịch nhưng không cần thiết** nếu chỉ export package nhằm giúp ServiceLoader nhận provider. `exports` làm mở rộng public surface cho compile/runtime module access; không nên làm khi không có nhu cầu API trực tiếp.

### Public constructor và phạm vi truy cập

Với kiểu provider được **khởi tạo qua constructor**, thông thường provider class phải là `public`, không abstract và có **public no-args constructor**. Cơ chế dịch vụ có khả năng tạo instance theo mô hình đăng ký module; không yêu cầu consumer được truy cập trực tiếp package implementation qua `exports`.

Nếu constructor đòi hỏi đối số, ném exception hoặc không thể khởi tạo, discovery/iteration có thể thất bại bằng `ServiceConfigurationError`; cần xem `Caused by` để biết nguyên nhân gốc.

## 7. Provider factory method (nâng cao)

Đối với provider trong **explicit named module**, `ServiceLoader` hỗ trợ khai báo một **provider class có public static no-arg method tên `provider`** trả về kiểu có thể gán cho service. Điều này cho phép sử dụng factory và che constructor/implementation:

```java
package example.provider.internal;

import example.api.Compressor;

public final class CompressorFactory {
    private CompressorFactory() {}

    public static Compressor provider() {
        return new FastCompressor();
    }
}
```

Đây là **mã minh họa**, không phải ví dụ runnable độc lập: `Compressor` và `FastCompressor` phải được định nghĩa trong module thích hợp.

Module descriptor:

```java
module example.provider {
    requires example.api;
    provides example.api.Compressor
        with example.provider.internal.CompressorFactory;
}
```

- Trong phương án factory, lớp được liệt kê sau `with` có thể là class **cung cấp đối tượng dịch vụ**, không nhất thiết chính lớp đó implements service; method `provider()` trả về đối tượng thích hợp.
- Provider method phải đáp ứng điều kiện Java ServiceLoader API; nếu có nhiều overload/khai báo factory không hợp lệ, có thể gây `ServiceConfigurationError`.
- Cách factory provider method này áp dụng cho **explicit modules**, không phải cấu hình `META-INF/services` trên classpath theo kiểu cũ; với provider class trong unnamed module/automatic module, quy tắc constructor-based tương ứng vẫn quan trọng.
- Không nhầm factory method `provider()` của SPI với annotation injection framework hay Java method reflection phổ thông; nó có một hợp đồng riêng trong `ServiceLoader`.

### Vì sao factory method hữu ích?

Factory có thể quyết định implementation phù hợp dựa trên cấu hình hoặc tạo đối tượng service với dependencies mà không cần public no-arg constructor của implementation thật. Tuy nhiên, provider module chịu trách nhiệm factory không được tự ý tạo các class/plugin không tin cậy trong JVM chính mà không có cơ chế an toàn thích hợp.

## 8. JPMS service binding và module resolution

Từ khóa `uses`/`provides` nằm trong descriptor; nhưng **module graph** tại runtime mới quyết định những module provider nào sẵn sàng cho service discovery.

Trong Java launcher:

- Named module được chỉ định làm main module là root quan trọng.
- `requires` kéo các module được đọc vào graph theo module resolution.
- `--add-modules` cho phép thêm modules làm roots.
- Có cơ chế **service binding** trong quá trình resolution để liên kết consumer dùng service với provider modules được quan sát; hành vi còn phụ thuộc cách launcher/layer được xây dựng và các tập module có thể quan sát.
- Không nên suy luận “chỉ cần JAR provider nằm trên module path chắc chắn sẽ được load” ở mọi ứng dụng.

Bài demo dùng `--add-modules learning.services.en,learning.services.vi` nên provider modules chắc chắn hiện diện trong resolved graph khi các descriptor và dependency đúng. Khi triển khai, có thể thay thế bằng module resolution có service binding được cấu hình chủ đích.

### Lệnh chẩn đoán có ích

```bash
java --show-module-resolution --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

Phần `--show-module-resolution` cho biết các module được resolve và nguồn/quan hệ tham gia, giúp phát hiện module provider vắng mặt hoặc chọn sai artifact. Output chẩn đoán thay đổi theo JDK và graph nên bài không gán cố định toàn bộ các dòng log.

Nếu chạy:

```bash
java --module-path mods --add-modules learning.services.en --module learning.services.app/learning.services.app.Main
```

thì **không nên khẳng định chắc chắn chỉ có một provider** trong mọi cơ chế service binding. Điều chắc chắn là module `learning.services.en` được thêm trực tiếp; các module khác có thể được resolve bởi service binding hoặc cấu hình launcher/layer. Khi cần kiểm thử loại trừ `learning.services.vi`, hãy dùng module path/graph chỉ cung cấp những module mong muốn hoặc cấu hình layer rõ ràng.

## 9. ClassLoader và module layer trong ServiceLoader

Trong classpath truyền thống, các plugin đôi khi được tải bằng `URLClassLoader` riêng. Trong JPMS, hệ thống có thể có **ModuleLayer** chứa các module, mỗi module được định nghĩa với một class loader phù hợp.

Những điều cần phân biệt:

1. **Module path** là đầu vào để resolver tìm module artifact; nó không tự là “parent của class loader”.
2. **Module graph** cho biết modules nào đã được resolve và quan hệ đọc/export tương ứng.
3. **Class loader** thực sự định nghĩa class provider và service interface; cùng binary name nhưng khác defining loader là hai runtime types khác nhau.
4. **ModuleLayer** là một cấu trúc runtime chứa resolved modules (có thể được tạo thêm cho plugin).
5. **ServiceLoader** có các overload tra provider theo class loader hoặc theo module layer.

Snippet nếu đã có layer và service type tương ứng:

```java
ServiceLoader<GreetingService> providers =
        ServiceLoader.load(pluginLayer, GreetingService.class);
```

Đây là **snippet**, không phải chương trình độc lập: `pluginLayer` cần được tạo đúng và caller named module cần có quyền sử dụng service theo hợp đồng. Overload theo `ModuleLayer` có thể tìm provider trong layer chỉ định và các layer cha theo API; nó không tự tạo layer từ tên module.

### Một ràng buộc dễ bỏ sót: SPI identity

Nếu host dùng `learning.services.api.GreetingService` định nghĩa ở loader H, nhưng một plugin loader khác **tự định nghĩa lại** class/interface cùng tên, provider thực hiện “bản SPI” của plugin sẽ không được xem là implementation của đúng service type host đang truyền cho `ServiceLoader`.

Vì vậy với kiến trúc plugin:

- Đưa API/SPI dùng chung vào một module/loader chung.
- Để provider modules đọc service API đó thay vì đóng gói bản sao.
- Kiểm tra module layer và defining loader của service interface/provider.
- Tránh cấu hình child-first nhân đôi SPI dùng chung.
- Khi thấy `ServiceConfigurationError: not a subtype` hoặc class-cast kỳ lạ, kiểm tra runtime type identity chứ không chỉ tên package.

## 10. So sánh `module-info.java` với `META-INF/services` trên classpath

Trước JPMS và hiện nay khi triển khai trên classpath, provider có thể được công bố bằng resource text:

```text
META-INF/services/learning.services.api.GreetingService
```

Nội dung file ví dụ:

```text
learning.services.en.internal.EnglishGreeting
learning.services.vi.internal.VietnameseGreeting
```

Trên **classpath**, đây là danh sách tên class provider. Người viết library phải đặt file resource trong JAR/classes đúng chỗ, public provider classes phải có constructor phù hợp theo cơ chế provider cũ, và loader phù hợp phải tìm được resource qua `getResources`.

Trong **explicit named modules**, mô hình chuẩn là **`provides ... with ...` trong module descriptor**. Việc lấy provider từ named module do thông tin module descriptor và module resolution quyết định; không cần đặt `META-INF/services` để đăng ký chính provider đó theo mẫu ví dụ.

| Chủ đề | Explicit named module | Unnamed module / classpath truyền thống |
| --- | --- | --- |
| Consumer declaration | `uses ServiceType;` trong `module-info.java` | Không có `module-info.java`; gọi API ServiceLoader phù hợp |
| Provider registration | `provides ServiceType with Provider;` | `META-INF/services/<fully.qualified.Service>` |
| API visibility | `requires` + `exports` khi thích hợp | Classpath/type visibility và defining loader |
| Provider package export | Không phải export chỉ để ServiceLoader instantiate provider | Không có export kiểu JPMS từ unnamed module |
| Provider factory `provider()` | Hỗ trợ theo quy tắc explicit named module | Không áp dụng như kiểu đăng ký file cũ |
| Discovery boundary | Resolved modules, module layers, class loaders | Resource lookup/class loaders |
| Khi trùng provider | Phụ thuộc định danh provider trong descriptor/resolution | Phụ thuộc cấu hình nhiều JAR/resource; ServiceLoader xử lý quy tắc duplicate hợp lệ |

Nếu chuyển library từ classpath lên module path, không nên giả định file descriptor cũ là đủ cho **explicit modular JAR**. Hãy kiểm tra descriptor, cách khai báo service và launcher/module graph thực tế.

### Automatic modules

Một JAR không có `module-info.class` có thể được xem là **automatic module** khi đặt trên module path. Automatic module có các quy tắc suy diễn metadata và provider service khác explicit named module; có thể lấy service-provider declarations từ `META-INF/services` theo JPMS. Đừng gọi mọi JAR trên module path là explicit module hoặc mặc nhiên áp dụng hỗ trợ provider factory method cho automatic module.

## 11. Nếu thiếu `uses` hoặc `provides` sẽ xảy ra gì?

### Trường hợp 1: Consumer quên `uses`

Module consumer vẫn có thể `requires` API và compile mã dùng `GreetingService`. Nhưng lúc gọi `ServiceLoader.load(GreetingService.class)` từ named module không khai báo `uses GreetingService`, Java ServiceLoader có thể ném `ServiceConfigurationError` vì caller module không khai báo nhu cầu dùng service này.

**Khắc phục:** thêm `uses learning.services.api.GreetingService;` vào descriptor consumer. Không chữa lỗi bằng cách export package provider implementation.

### Trường hợp 2: Provider quên `provides`

Module provider có một class implements `GreetingService` nhưng descriptor không công bố provider. Với cơ chế explicit named module, `ServiceLoader` **không tự quét mọi class** để đoán class nào implements interface.

**Khắc phục:** đăng ký `provides ... with ...` trong module provider, bảo đảm class/provider method đúng hợp đồng, module có mặt trong resolved graph.

### Trường hợp 3: Provider module không được resolve

JAR module nằm trong thư mục `mods` nhưng không tham gia module layer được truy vấn. Consumer không thấy provider ấy qua ServiceLoader dùng layer/class loader đó.

**Khắc phục:** xem module graph bằng `--show-module-resolution`; đưa provider vào resolution bằng `--add-modules`, service binding phù hợp hoặc tạo plugin layer có provider modules theo kiến trúc.

### Trường hợp 4: Interface API bị định nghĩa hai lần

Host và plugin đóng gói hai định nghĩa `GreetingService` có cùng binary name nhưng khác defining loader. Một provider implements SPI của plugin có thể không phải subtype của SPI host.

**Khắc phục:** thống nhất service API về module/loader chia sẻ, tránh shadowing API ở plugin.

### Trường hợp 5: Constructor/provider factory sai

Một provider class không đúng tính hợp lệ, thiếu public no-arg constructor (trong trường hợp constructor-based), provider() method sai chữ ký hoặc constructor ném lỗi.

**Khắc phục:** đọc `ServiceConfigurationError` cùng cause, kiểm tra chữ ký và module descriptor; không bắt hết mọi exception rồi âm thầm bỏ qua provider không đáng tin.

## 12. Các lỗi thường gặp và chẩn đoán

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `ServiceConfigurationError: module ... does not declare uses` | Consumer named module thiếu uses | Thêm uses vào module-info của module gọi |
| Không tìm thấy provider, vòng lặp rỗng | Provider module không resolved, chưa có provides hoặc tìm sai layer/loader | Kiểm tra module graph, provides, `--add-modules` |
| `ServiceConfigurationError: Provider ... not found` | Tên provider sai, provider class/dependency không load được | Binary name, JAR/module path, class loader |
| `ServiceConfigurationError: ... not a subtype` | Provider không thực hiện đúng service type, có thể do duplicate SPI | So sánh defining loader của SPI/provider |
| Lỗi constructor/provider method | Cấu hình provider class/factory không hợp lệ hoặc ném exception | Public constructor, factory method, cause |
| `IllegalAccessError` / `InaccessibleObjectException` | Module access, exports/opens hoặc reflection chưa hợp lệ | Xem module descriptors/caller module |
| `NoClassDefFoundError` | Provider class tham chiếu dependency vắng mặt hoặc initializer trước đó lỗi | Đọc cause và runtime dependencies |
| `NoSuchMethodError` | Compile/runtime API thư viện khác phiên bản | Kiểm tra defining loader, JAR, method descriptor |
| `ClassCastException` | Provider đưa qua ranh giới loại SPI bị nhân đôi | Thống nhất định nghĩa API interface |
| Provider thấy khi chạy IDE nhưng mất ở JAR | Module graph/packaging khác, quên descriptor hoặc services resource | Kiểm tra artifact thực tế và lệnh khởi động |
| Reload không phát hiện phiên bản class mới | ServiceLoader cache hay loader/module layer cũ giữ classes | Xem lifecycle, `reload()` và layer/class loader mới |

### Kiểm tra artifact thực tế

Nếu đã đóng gói module JAR (file JAR thực sự tồn tại):

```bash
jar --describe-module --file provider.jar
jar tf provider.jar
```

`jar --describe-module` giúp thấy descriptor với provides/exports/requires, còn `jar tf` liệt kê entry thực. Tên `provider.jar` ở đây là ví dụ, không phải file sinh bởi lệnh demo chưa có bước đóng gói.

Dùng:

```bash
java --show-module-resolution --module-path mods --add-modules learning.services.en,learning.services.vi --module learning.services.app/learning.services.app.Main
```

để kiểm tra modules nào tham gia resolution. Không dựa hoàn toàn vào log `ServiceLoader`: lỗi provider có thể nằm trong class loading/linking hoặc constructor lúc iteration.

### Quan sát type identity

Nếu có đối tượng `GreetingService provider`:

```java
System.out.println(GreetingService.class.getClassLoader());
System.out.println(provider.getClass().getClassLoader());
System.out.println(provider.getClass().getModule());
```

Đây là snippet, không phải chương trình độc lập. Service interface và provider **không bắt buộc cùng defining loader**, nhưng provider phải thực sự implements **định nghĩa SPI mà consumer đang dùng**. Khi phụ thuộc vào nhiều plugin loaders, kiểm tra interface identity theo `Class<?>` thực tế.

## 13. Hiệu năng, thread-safety và vòng đời

`ServiceLoader` có cache provider theo instance để tránh một số thao tác khám phá/khởi tạo lại. Tuy nhiên, **bản thân đối tượng `ServiceLoader` không an toàn khi được sử dụng đồng thời bởi nhiều thread nếu không có đồng bộ phù hợp**. Điều này khác với việc các provider implementations có thể hoặc không thể thread-safe tùy hợp đồng riêng.

Những lưu ý vận hành:

- **Không tự suy thứ tự provider:** nếu cần chọn một provider theo vùng/độ ưu tiên, dùng metadata hoặc policy riêng; trong ví dụ mã `code()` được sắp xếp để in kết quả.
- **Xử lý provider errors có chủ đích:** một provider lỗi có thể khiến iteration thất bại, không nên im lặng che giấu.
- **Đóng tài nguyên của provider:** ServiceLoader không thay thế trách nhiệm đóng kết nối, thread, stream của implementation. Nếu provider là AutoCloseable thì ứng dụng/framework phải quản lý lifecycle phù hợp.
- **Cẩn thận với TCCL trong thread pool:** nếu tạm đặt context loader để tra plugin, khôi phục bằng `finally` sau đó.
- **`reload()` không tự thay class identity:** cùng class loader/module layer cũ có thể vẫn dùng cùng runtime class đã định nghĩa.
- **Không coi modular service provider là sandbox:** code provider vẫn chạy với quyền của tiến trình theo mô hình bảo mật thực tế; phải xác minh nguồn plugin và cân nhắc cô lập tiến trình cho code không tin cậy.

### Một kịch bản lựa chọn provider có kiểm soát

Ví dụ khi ứng dụng cần ưu tiên service code `vi`:

```java
GreetingService chosen = null;
for (GreetingService item : ServiceLoader.load(GreetingService.class)) {
    if ("vi".equals(item.code())) {
        chosen = item;
        break;
    }
}
if (chosen == null) {
    throw new IllegalStateException("Vietnamese provider unavailable");
}
System.out.println(chosen.greet("Java"));
```

Đây là **snippet** bên trong consumer module đã khai báo `uses`. Output khi có provider tiếng Việt như demo:

```text
Xin chào, Java
```

Không dùng `iterator().next()` mà không kiểm tra khi thứ tự provider có thể thay đổi giữa môi trường triển khai.

## 14. Những hiểu nhầm phổ biến

**“`requires` module provider đã đủ để ServiceLoader nhận ra dịch vụ.”** Sai. Consumer phải khai báo `uses` phù hợp, provider phải công bố `provides` hoặc dùng cơ chế đăng ký khác theo loại module.

**“Module có `provides` tức provider constructor đã chạy lúc startup.”** Sai. Discovery/khởi tạo provider thường lazy khi API được sử dụng; descriptor chỉ công bố đăng ký.

**“Provider package phải `exports` để ServiceLoader gọi constructor.”** Không. Provider được khai báo đúng trong explicit module có thể ở package không export; consumer chỉ cần service API public phù hợp.

**“ServiceLoader tự quét mọi class implements interface trên module path.”** Không. Nó dùng cấu hình dịch vụ/module metadata/classpath descriptor đúng hợp đồng, không classpath-scan tùy ý.

**“Hai provider phải ở cùng module.”** Không. Một service có thể do nhiều module riêng biệt cung cấp.

**“ServiceLoader sẽ luôn ưu tiên provider đứng đầu theo alphabet.”** Không. Thứ tự discovery không phải chính sách ưu tiên; ứng dụng nên chọn có chủ đích.

**“Có provider JAR trên đĩa nghĩa là chắc chắn module đã được resolve.”** Không. Cần kiểm tra module layer/graph và cách loader được gọi.

**“`reload()` tự cập nhật class mới trong loader cũ.”** Không. Nó xử lý cache provider của ServiceLoader; không tự định nghĩa lại class cùng binary name trong cùng loader.

**“`META-INF/services` và `provides` phải luôn viết cả hai mới chạy trên module path.”** Không. Explicit named module có đăng ký `provides` chuẩn; classpath/automatic module có hình thức khác.

**“Dùng `ServiceLoader` thì provider luôn an toàn vì JVM kiểm tra bytecode.”** Sai. Bytecode hợp lệ vẫn có thể gây tác động theo quyền runtime của tiến trình.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `uses` đặt ở module nào? Có bắt buộc đưa vào provider module không?

**Đáp án:** `uses ServiceType` thuộc module **gọi ServiceLoader để tiêu thụ service**. Provider module dùng `provides ServiceType with Provider;`. Một module có thể vừa dùng vừa cung cấp các dịch vụ khác nhau, nhưng không phải mọi provider tự nhiên phải có `uses`.

**Câu 2.** `exports learning.services.api;` có thay cho `uses GreetingService;` không?

**Đáp án:** Không. `exports` là khả năng truy cập kiểu ở package; `uses` công bố nhu cầu tìm provider theo hợp đồng ServiceLoader của named module.

**Câu 3.** Vì sao consumer demo không import `EnglishGreeting` nhưng vẫn nhận được instance?

**Đáp án:** Provider được đăng ký bằng `provides ... with ...`, module có mặt trong graph và ServiceLoader khám phá/khởi tạo theo service API. Consumer chỉ phụ thuộc SPI.

**Câu 4.** Nếu bỏ `provides` khỏi `learning.services.vi` mà vẫn giữ class `VietnameseGreeting` trong JAR, có chắc ServiceLoader nhận được provider này không?

**Đáp án:** Không theo cơ chế explicit named module đã trình bày; chỉ có class implements SPI chưa đủ để được tự động đăng ký.

**Câu 5.** `--add-modules learning.services.en,learning.services.vi` trong lệnh demo giải quyết điều gì?

**Đáp án:** Đưa cả hai provider modules vào root set của resolution; đó là cách kiểm soát chúng xuất hiện trong runtime module graph để ServiceLoader có thể tìm được.

**Câu 6.** Vì sao output demo dùng `TreeMap`?

**Đáp án:** Vì ServiceLoader không phải API đảm bảo sắp xếp theo mã provider; TreeMap giúp hiển thị theo khóa `en`, `vi` ổn định và tránh kết luận sai về thứ tự discovery.

**Câu 7.** Có thể đăng ký provider class trong package `internal` không export không?

**Đáp án:** Có, với explicit named module và khai báo/provider hợp lệ. ServiceLoader được thiết kế để khám phá provider không buộc consumer phụ thuộc implementation package.

**Câu 8.** `ServiceLoader.reload()` có thay bytecode class cũ bằng một bản mới trong cùng ClassLoader không?

**Đáp án:** Không. `reload()` xóa cache ServiceLoader, không thay thế định nghĩa runtime class đã được JVM nạp.

**Câu 9.** Một provider module ở module path nhưng ServiceLoader trả rỗng. Cần kiểm tra gì?

**Đáp án:** Provider descriptor có `provides` chưa, module có được resolve vào layer/graph đang dùng chưa, consumer có `uses` chưa, service API có cùng runtime identity không, và phương thức ServiceLoader được gọi dùng loader/layer nào.

**Câu 10.** Khi nào cân nhắc provider factory `provider()`?

**Đáp án:** Khi explicit named module cần một factory để tạo service instance theo hợp đồng mà không muốn provider class trực tiếp implements SPI với public no-arg constructor; phải tuân thủ chữ ký phương thức và kiểm tra bằng compiler/runtime.

## 16. Checklist triển khai

- [ ] Thiết kế service interface hoặc abstract class ổn định trong module API riêng.
- [ ] Module API `exports` package chứa service type cho module cần dùng.
- [ ] Consumer `requires` API khi cần và khai báo `uses ServiceType;`.
- [ ] Provider `requires` API và đăng ký đúng `provides ServiceType with Provider;`.
- [ ] Provider class có constructor hoặc factory method hợp lệ; các phụ thuộc runtime hiện diện.
- [ ] Không export implementation package chỉ vì muốn ServiceLoader truy cập.
- [ ] Module provider được resolve vào đúng runtime graph/layer.
- [ ] Không đóng gói trùng service API type trong nhiều loader.
- [ ] Dùng `ServiceLoader` thích hợp; xử lý provider errors và thứ tự có chủ đích.
- [ ] Nếu cần reload plugin, quản lý module layer/ClassLoader và vòng đời provider rõ ràng.
- [ ] Với classpath, kiểm tra `META-INF/services/<service binary name>` đúng đường và tên provider.
- [ ] Test bằng artifact, module path và lệnh khởi động sát môi trường triển khai.

## 17. Kết luận và nguồn tham khảo

Trong JPMS, `uses` và `provides` là **hai phía của một hợp đồng nạp dịch vụ**. Consumer khai báo loại service sẽ sử dụng; provider module công bố lớp cung cấp; `ServiceLoader` tìm provider từ các module/resource phù hợp theo graph và loader thực tế. `requires` và `exports` vẫn cần thiết cho type accessibility nhưng **không phải cơ chế đăng ký provider**.

Cách xây dựng bền vững là đặt SPI chung ở module/loader được chia sẻ, giữ triển khai trong provider module không cần export, kiểm tra provider được resolved, sử dụng ServiceLoader với chính sách chọn provider rõ ràng và không phụ thuộc vào thứ tự khám phá không được bảo đảm.

### Tài liệu chuẩn

- Java SE 17 `ServiceLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS 17 §7.7.1, *Module Directives* (`requires`, `exports`, `uses`, `provides`): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.1
- Java SE 17 `java` launcher, module path/add-modules/show-module-resolution: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Java SE 17 `javac`, module-source-path: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 `ModuleLayer` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 `ClassLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
