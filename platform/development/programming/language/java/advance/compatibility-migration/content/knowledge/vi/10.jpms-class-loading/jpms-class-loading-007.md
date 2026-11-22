# ServiceLoader và khai báo `uses` hoặc `provides`

Khi một ứng dụng Java cần hỗ trợ nhiều cách triển khai cho cùng một chức năng, cách viết trực tiếp `new` cho một lớp cụ thể nhanh chóng tạo ra phụ thuộc chặt. Ví dụ, ứng dụng xuất báo cáo có thể cần thêm bộ xuất PDF, CSV hoặc JSON; hệ thống thanh toán có thể tích hợp nhiều cổng thanh toán; một thư viện có thể cho phép người dùng cài thêm plugin mà không biên dịch lại mã nghiệp vụ.

`java.util.ServiceLoader` cung cấp cơ chế khám phá các bản triển khai (*service providers*) theo một hợp đồng chung (*service*). Với Java Platform Module System (JPMS), hợp đồng này được mô tả thêm trong `module-info.java` bằng hai chỉ thị:

- `uses`: module **tiêu thụ** muốn tìm các provider của một service.
- `provides ... with ...`: module **cung cấp** đăng ký lớp hoặc factory triển khai service đó.

Sử dụng đúng `ServiceLoader`, `uses` và `provides` giúp một hệ thống được nâng cấp dần từ classpath sang module path, giữ ranh giới module rõ ràng và tránh việc consumer phải phụ thuộc trực tiếp vào mọi implementation.

## 1. Các vai trò trong cơ chế Service Provider Interface

Một hệ thống dùng ServiceLoader thường có ba thành phần:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Service API/SPI | Khai báo giao diện hoặc lớp trừu tượng mà provider phải đáp ứng. | `GreetingService` |
| Service provider | Triển khai service theo một công nghệ hoặc cách xử lý cụ thể. | `EnglishGreetingService`, `VietnameseGreetingService` |
| Service consumer | Tìm, lựa chọn và sử dụng một hoặc nhiều provider. | Ứng dụng `com.example.greeting.app` |

Đường phụ thuộc thường mong muốn:

```text
                 +---------------------------+
                 |      Service API/SPI      |
                 |      GreetingService      |
                 +---------------------------+
                      ^                ^
                      |                |
             implements/uses          uses
                      |                |
           +----------------+  +----------------+
           | Provider module|  | Consumer module|
           | English / Vi   |  | Main / business|
           +----------------+  +----------------+
                      ^                |
                      |                |
                      +--ServiceLoader-+
                         discovery
```

Consumer biết service type nhưng không cần `new EnglishGreetingService()` hay trực tiếp khai báo phụ thuộc vào module của provider. Provider cũng không phải biết consumer cụ thể nào sẽ dùng nó.

**Điểm phân biệt:** `ServiceLoader` là cơ chế tìm kiếm và khởi tạo provider. Nó không tự định nghĩa interface, không tự chọn provider tốt nhất theo nghiệp vụ, không bảo đảm mọi module trên ổ đĩa đều được nạp và cũng không tự cập nhật mọi plugin đang chạy.

## 2. `uses` và `provides` khác `requires` như thế nào?

Trong `module-info.java`, những chỉ thị này có ý nghĩa độc lập:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
```

- `requires com.example.greeting.api` tạo quan hệ đọc module để consumer có thể tham chiếu đến kiểu `GreetingService`.
- `uses com.example.greeting.api.GreetingService` khai báo consumer sử dụng service discovery cho kiểu đó.

Ở phía provider:

```java
module com.example.greeting.provider.en {
    requires com.example.greeting.api;
    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.en.EnglishGreetingService;
}
```

- `requires` cho phép provider tham chiếu đến service API.
- `provides ... with ...` đăng ký provider với JPMS.
- Không cần `exports` package implementation chỉ để ServiceLoader khởi tạo provider.

| Chỉ thị | Module nào khai báo? | Mục đích |
|---|---|---|
| `requires api.module` | Consumer và provider, nếu cần sử dụng API ở module khác. | Cho phép đọc module chứa kiểu service. |
| `exports api.package` | Module chứa service API. | Cho phép module khác dùng kiểu service public. |
| `uses api.Service` | Module gọi ServiceLoader để tìm service. | Công bố nhu cầu tiêu thụ một service. |
| `provides api.Service with impl.Provider` | Module chứa provider. | Đăng ký provider có thể được ServiceLoader khám phá. |
| `opens implementation.package` | Chỉ khi có yêu cầu deep reflection khác. | Không phải điều kiện bắt buộc để ServiceLoader dùng `provides`. |

Một `uses` không chỉ định provider cụ thể; một `provides` không tạo quan hệ phụ thuộc tường minh từ ứng dụng sang provider. Đây là hai ý chính của kiến trúc có thể thay thế plugin.

## 3. Ví dụ hoàn chỉnh với ba vai trò và nhiều provider

Ví dụ gồm bốn named module: một module công bố service, hai module cung cấp implementation và một module tiêu thụ.

### 3.1. Cấu trúc thư mục

```text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/api/GreetingService.java
├── com.example.greeting.provider.en/
│   ├── module-info.java
│   └── com/example/greeting/provider/en/EnglishGreetingService.java
├── com.example.greeting.provider.vi/
│   ├── module-info.java
│   └── com/example/greeting/provider/vi/VietnameseGreetingService.java
└── com.example.greeting.app/
    ├── module-info.java
    └── com/example/greeting/app/Main.java
```

Mỗi thư mục ngay dưới `src` có tên trùng với tên module. Cấu trúc này tương thích với cách dùng `javac --module-source-path` trong ví dụ.

### 3.2. Khai báo Service API

Tệp `src/com.example.greeting.api/module-info.java`:

```java
module com.example.greeting.api {
    exports com.example.greeting.api;
}
```

Tệp `src/com.example.greeting.api/com/example/greeting/api/GreetingService.java`:

```java
package com.example.greeting.api;

public interface GreetingService {
    String languageTag();
    String greet(String person);
}
```

`GreetingService` là service type mà các provider sẽ triển khai. Package chứa interface được `exports` để consumer và provider có thể sử dụng nó.

### 3.3. Provider tiếng Anh

Tệp `src/com.example.greeting.provider.en/module-info.java`:

```java
module com.example.greeting.provider.en {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.en.EnglishGreetingService;
}
```

Tệp `src/com.example.greeting.provider.en/com/example/greeting/provider/en/EnglishGreetingService.java`:

```java
package com.example.greeting.provider.en;

import com.example.greeting.api.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    public EnglishGreetingService() {
    }

    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person + "!";
    }
}
```

Class có `public` no-argument constructor để ServiceLoader có thể tạo instance theo cơ chế constructor-based provider. Tên đầy đủ sau `with` phải là provider type nằm trong chính module cung cấp, theo quy tắc `provides` của JPMS.

Chú ý `module-info.java` của provider **không có** `exports com.example.greeting.provider.en`. Điều đó vẫn hợp lệ: ServiceLoader sử dụng cơ chế đăng ký service của module, không đòi hỏi toàn bộ implementation phải trở thành API công khai.

### 3.4. Provider tiếng Việt

Tệp `src/com.example.greeting.provider.vi/module-info.java`:

```java
module com.example.greeting.provider.vi {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.vi.VietnameseGreetingService;
}
```

Tệp `src/com.example.greeting.provider.vi/com/example/greeting/provider/vi/VietnameseGreetingService.java`:

```java
package com.example.greeting.provider.vi;

import com.example.greeting.api.GreetingService;

public final class VietnameseGreetingService implements GreetingService {
    public VietnameseGreetingService() {
    }

    @Override
    public String languageTag() {
        return "vi";
    }

    @Override
    public String greet(String person) {
        return "Xin chào, " + person + "!";
    }
}
```

Hai provider triển khai cùng một service interface. Consumer có thể chọn provider theo `languageTag()` mà không biết tên class thực thi.

### 3.5. Consumer đăng ký `uses`

Tệp `src/com.example.greeting.app/module-info.java`:

```java
module com.example.greeting.app {
    requires com.example.greeting.api;
    uses com.example.greeting.api.GreetingService;
}
```

Tệp `src/com.example.greeting.app/com/example/greeting/app/Main.java`:

```java
package com.example.greeting.app;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        String desiredLanguage = args.length == 0 ? "vi" : args[0];

        GreetingService selected = null;
        for (GreetingService candidate :
                ServiceLoader.load(GreetingService.class)) {
            if (desiredLanguage.equals(candidate.languageTag())) {
                selected = candidate;
                break;
            }
        }

        if (selected == null) {
            throw new IllegalStateException(
                    "No greeting provider for: " + desiredLanguage);
        }

        System.out.println(selected.greet("Java"));
    }
}
```

Consumer phụ thuộc trực tiếp vào `com.example.greeting.api`. Nó không import `EnglishGreetingService` hay `VietnameseGreetingService`, cũng không thêm `requires` cho hai provider module.

### 3.6. Biên dịch

Trong thư mục chứa `src`, dùng JDK 9 hoặc mới hơn:

```bash
javac --module-source-path src -d mods \
  -m com.example.greeting.api,com.example.greeting.provider.en,com.example.greeting.provider.vi,com.example.greeting.app
```

Trên Windows PowerShell, cùng lệnh có thể viết thành một dòng:

```powershell
javac --module-source-path src -d mods -m com.example.greeting.api,com.example.greeting.provider.en,com.example.greeting.provider.vi,com.example.greeting.app
```

Lệnh tạo class file vào các thư mục module bên dưới `mods`. Nếu hệ thống dùng Maven hoặc Gradle, cần cấu hình tương đương để biên dịch từng module với module path chính xác.

### 3.7. Chạy ứng dụng

```bash
java --module-path mods \
  --add-modules com.example.greeting.provider.en,com.example.greeting.provider.vi \
  --module com.example.greeting.app/com.example.greeting.app.Main vi
```

Kết quả dự kiến:

```text
Xin chào, Java!
```

Khi thay `vi` bằng `en`, ứng dụng sẽ in:

```text
Hello, Java!
```

Ở đây `--add-modules` đưa hai provider module vào cấu hình module được phân giải một cách tường minh. Trong môi trường có service binding của module resolver, provider còn có thể được đưa vào graph thông qua quan hệ `uses`/`provides`. Với một runtime hoặc cách tạo layer tùy chỉnh, cần bảo đảm các provider module thực sự nằm trong **resolved module graph**; chỉ đặt file JAR trên module path chưa phải là bằng chứng mọi provider sẽ được nạp.

## 4. Quy tắc của `uses`

Chỉ thị `uses` có dạng:

```java
uses com.example.greeting.api.GreetingService;
```

Nó phải nằm trong `module-info.java` của **explicit named module** có code tiêu thụ service bằng ServiceLoader. Một module khác khai báo `uses` không tự thay thế cho module thực sự gọi ServiceLoader.

Ví dụ, nếu module `com.example.plugin.manager` chứa phương thức:

```java
public ServiceLoader<GreetingService> discover() {
    return ServiceLoader.load(GreetingService.class);
}
```

thì `com.example.plugin.manager` phải có `uses com.example.greeting.api.GreetingService;` trong descriptor của chính nó nếu đây là explicit named module. Việc ứng dụng gọi `discover()` từ bên ngoài không xóa nghĩa vụ khai báo của module thực hiện lời gọi `ServiceLoader.load`.

Quy tắc liên quan:

- Service type phải truy cập được từ module khai báo `uses`.
- Nếu service interface ở module khác, thường cần `requires` module chứa service và module đó phải `exports` package thích hợp.
- Không khai báo lặp lại cùng một service trong nhiều chỉ thị `uses` của một module.
- `uses` công bố service dependency, nhưng không bắt buộc bất kỳ provider cụ thể nào phải tồn tại.
- Nếu không tìm được provider, duyệt `ServiceLoader` chỉ cho kết quả rỗng; việc xử lý fallback là trách nhiệm của consumer.

Với unnamed module và automatic module, cơ chế service-use dependency có quy tắc riêng; chúng không có yêu cầu khai báo `uses` tường minh giống explicit named module.

## 5. Quy tắc của `provides ... with ...`

Một module cung cấp có thể đăng ký một hoặc nhiều provider cho cùng một service:

```java
module com.example.greeting.provider {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.FastGreetingService,
             com.example.greeting.provider.FormalGreetingService;
}
```

Cú pháp gồm service type, từ khóa `with` và danh sách tên đầy đủ của các provider. Nếu cần công bố hai service khác nhau, sử dụng hai chỉ thị `provides` khác nhau.

Các điểm quan trọng:

1. Provider type được khai báo phải thuộc module cung cấp; không thể đăng ký một implementation nằm ở module khác bằng một `provides` tùy ý.
2. Provider class phải có mức truy cập thích hợp để JPMS xác minh cấu hình; thông thường là `public`.
3. Provider được khởi tạo qua public no-arg constructor, hoặc qua provider method hợp lệ trong explicit named module.
4. Nếu dùng constructor, provider class phải tương thích với service type (implements interface hoặc extends class phù hợp).
5. Package implementation không nhất thiết phải `exports` hay `opens` cho consumer.
6. Module cung cấp phải đọc được module có service API khi service type nằm ở module khác.

**Không nên thêm `exports` chỉ để sửa lỗi ServiceLoader**. Nếu provider không được tìm thấy, hãy kiểm tra `provides`, module resolution và constructor/provider method trước. Mở rộng export có thể làm lộ API implementation ngoài ý định.

## 6. Hai cách khởi tạo provider trong named module

### 6.1. Provider constructor

Cách phổ biến nhất là một class implements service và có constructor `public` không tham số:

```java
public final class BasicGreeting implements GreetingService {
    public BasicGreeting() {
    }

    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String person) {
        return "Hello, " + person;
    }
}
```

Đây là mô hình được dùng trong ví dụ chạy ở phần trước. Provider có thể dùng dependency riêng trong constructor, nhưng cần lưu ý constructor được gọi trong quá trình duyệt provider, vì vậy lỗi khởi tạo có thể xảy ra tại thời điểm consumer thực sự truy cập service.

### 6.2. Provider method

Trong explicit named module, ServiceLoader còn hỗ trợ một phương thức factory tên chính xác là `provider`, với đặc điểm:

- `public static`;
- không có tham số;
- trả về đối tượng có kiểu tương thích với service type.

Ví dụ:

```java
package com.example.greeting.provider.factory;

import com.example.greeting.api.GreetingService;

public final class GreetingFactory {
    private GreetingFactory() {
    }

    public static GreetingService provider() {
        return new CachedGreetingService();
    }
}
```

Đăng ký trong module:

```java
module com.example.greeting.provider.factory {
    requires com.example.greeting.api;

    provides com.example.greeting.api.GreetingService
        with com.example.greeting.provider.factory.GreetingFactory;
}
```

`GreetingFactory` không cần implements `GreetingService`, vì `provider()` tạo và trả về đối tượng triển khai. `CachedGreetingService` ở đây là implementation minh họa, được định nghĩa riêng trong module provider.

Provider method đặc biệt hữu ích khi cần kiểm soát cách tạo instance, ví dụ thực hiện factory setup hoặc chọn implementation dựa trên cấu hình. Tuy nhiên, factory không nên có side effect khó kiểm soát, và method không được trả về `null`.

**Giới hạn migration:** Provider method chỉ được hỗ trợ cho provider trong explicit named module. Provider trong automatic module hoặc trên classpath theo cấu hình `META-INF/services` phải sử dụng public no-arg constructor và là subtype phù hợp của service.

## 7. Sử dụng ServiceLoader từ consumer

### 7.1. `load(Class<S>)`

Đây là dạng thường dùng nhất:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}
```

`ServiceLoader.load(Class)` sử dụng *thread context class loader* để bắt đầu tìm provider. Trong ứng dụng modular, nó cũng có thể tìm các provider thuộc named module được nhìn thấy qua cơ chế module/class loader. Muốn kiểm soát rõ nguồn provider, cần xem xét overload có ClassLoader hoặc ModuleLayer.

### 7.2. `load(Class<S>, ClassLoader)`

Có thể truyền class loader chủ động:

```java
ClassLoader pluginLoader = Thread.currentThread()
        .getContextClassLoader();

ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class, pluginLoader);
```

Overload này hữu ích trong môi trường ứng dụng server, plugin manager hoặc khi có nhiều class loader. Nó không cho phép tìm provider ở bất kỳ nơi nào tùy ý; provider vẫn phải có mặt và truy cập được trong phạm vi nạp lớp/module tương ứng.

### 7.3. `load(ModuleLayer, Class<S>)`

Khi ứng dụng tạo các `ModuleLayer` riêng để cô lập plugin, có thể tìm provider trong một layer cụ thể:

```java
ModuleLayer pluginLayer = obtainPluginLayer();
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
```

`obtainPluginLayer()` là hàm minh họa: ứng dụng cần tự tạo hoặc nhận một layer hợp lệ trước khi gọi. Overload này tìm trong layer được chỉ định và các parent layer, **không** tìm provider trong unnamed modules của classpath.

ModuleLayer giúp quản lý module configuration và class loader theo nhóm plugin, nhưng không tự giải quyết các vấn đề phiên bản, quyền truy cập, hoặc xung đột lớp khi plugin và host dùng những bản service API khác nhau.

### 7.4. `findFirst()`, `iterator()` và `stream()`

Từ Java 9, ServiceLoader có `findFirst()` và `stream()`:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

GreetingService first = loader.findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "No greeting provider installed"));
```

`findFirst()` có ích khi ứng dụng chỉ cần một provider, nhưng **không nên** dựa vào nó để quyết định thứ tự ưu tiên nghiệp vụ giữa các module độc lập. Thứ tự module providers không được bảo đảm ổn định.

Với `stream()` có thể xem thông tin provider và khởi tạo khi cần:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
        .map(ServiceLoader.Provider::get)
        .filter(service -> "vi".equals(service.languageTag()))
        .findFirst()
        .ifPresent(service ->
                System.out.println(service.greet("Java")));
```

`Provider.get()` có thể gây khởi tạo thực sự. `Provider.type()` trả về thông tin kiểu provider theo hợp đồng API; với provider method, kiểu này không nhất thiết trùng với class factory được liệt kê sau `with`. Đừng dùng chi tiết class implementation làm tiêu chí chính nếu ứng dụng đã có metadata/capability riêng.

## 8. Lazy loading, cache và `reload()`

`ServiceLoader` khám phá và khởi tạo provider theo nhu cầu. Việc gọi `load` tạo một service loader; duyệt iterator hoặc tiêu thụ stream mới làm quá trình tìm/khởi tạo diễn ra dần.

Mỗi instance ServiceLoader giữ cache những provider instance đã được tải. Khi tiếp tục duyệt, provider đã cache có thể được trả lại trước những provider mới. Điều này giúp tránh khởi tạo lặp không cần thiết trong vòng đời của một loader.

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}

loader.reload();

for (GreetingService service : loader) {
    System.out.println(service.languageTag());
}
```

`reload()` xóa cache nội bộ của loader để lần duyệt tiếp theo khám phá/khởi tạo lại. Nó **không** tự tải lại bytecode đã được một class loader nạp, không tự thêm module chưa được phân giải vào layer, và không phải cơ chế hot deployment toàn diện. Muốn thêm plugin modular mới khi ứng dụng đang chạy, thường cần quy trình tạo layer và class loader phù hợp.

ServiceLoader không bảo đảm an toàn khi cùng một instance được nhiều thread thao tác đồng thời. Nếu dùng trong luồng xử lý nhiều request, nên quản lý đồng bộ hoặc tải danh sách provider vào một cấu trúc bất biến sau khi khởi tạo.

## 9. Thứ tự provider và cách chọn implementation

Không nên phụ thuộc vào thứ tự trả về của các provider trong những module khác nhau. Thứ tự giữa các module nằm trong cùng class loader/layer không được định nghĩa như một hợp đồng ổn định.

Khi sản phẩm có nhiều provider, nên đưa quy tắc lựa chọn vào API hoặc cấu hình rõ ràng:

- Theo capability như ngôn ngữ, loại file, mã thanh toán hoặc driver.
- Theo tên/cấu hình người quản trị đã chọn.
- Theo version/capability được công bố bởi provider.
- Theo priority tự định nghĩa, có xử lý trường hợp bằng điểm.
- Theo chính sách fallback khi provider không có hoặc không khởi tạo được.

Ví dụ, service có thể công bố `languageTag()` và consumer chọn đúng `vi` thay vì dùng provider đầu tiên. Nếu hệ thống yêu cầu chọn duy nhất một provider cho một mã, hãy phát hiện cấu hình trùng lặp thay vì âm thầm chọn một provider theo thứ tự tình cờ.

Ngoài ra, provider constructor hoặc factory có thể tốn tài nguyên. Không nên lặp lại `ServiceLoader.load` ở mọi request nếu ứng dụng chỉ cần tạo plugin một lần lúc khởi động.

## 10. Từ classpath cũ sang JPMS: `META-INF/services`

Trước Java 9, ServiceLoader hoạt động với provider configuration file trong JAR:

```text
provider.jar
├── com/example/greeting/provider/en/EnglishGreetingService.class
└── META-INF/
    └── services/
        └── com.example.greeting.api.GreetingService
```

Tên file đúng bằng tên nhị phân đầy đủ của service type. Nội dung file là danh sách tên đầy đủ của provider classes, mỗi dòng một tên:

```text
com.example.greeting.provider.en.EnglishGreetingService
```

File này được mã hóa UTF-8, có thể chứa dòng trống và comment bắt đầu bằng `#`. Ví dụ:

```text
# English implementation
com.example.greeting.provider.en.EnglishGreetingService
```

Khi provider JAR nằm trên classpath, ServiceLoader tìm các file `META-INF/services/<service-name>` và đọc các tên class để khởi tạo. Class provider cần có public no-arg constructor, là subtype phù hợp của service, và có thể được tìm thấy bằng class loader.

### 10.1. Khác biệt khi đặt JAR lên module path

| Cách đóng gói | Provider registration | Lưu ý |
|---|---|---|
| JAR trên classpath (unnamed module) | `META-INF/services` | Cơ chế ServiceLoader truyền thống. |
| Automatic module trên module path | Thường được suy ra từ `META-INF/services` | Không hỗ trợ provider method factory; cần provider constructor. |
| Explicit named module có `module-info.class` | `provides Service with Provider` | Không cần `META-INF/services` để đăng ký provider của module đó. |

Khi chuyển một provider JAR từ classpath sang explicit named module, chỉ giữ `META-INF/services` mà không khai báo `provides` có thể khiến ServiceLoader không nhìn thấy provider trong module đó. Với explicit named module, hãy chuyển đăng ký sang `module-info.java`.

Nếu một JAR explicit named module đồng thời có `provides` và file `META-INF/services`, ServiceLoader không dùng file cũ để đăng ký trùng provider đã có trong named module. Giữ file cũ có thể phục vụ cấu hình chạy trên classpath, nhưng cần kiểm tra bản phát hành thực tế và cách JAR được sử dụng.

### 10.2. Chuyển đổi từng bước

Một lộ trình thường gặp:

1. Đưa service interface vào một artifact/API ổn định mà cả consumer và provider dùng chung.
2. Kiểm tra nội dung `META-INF/services` và tất cả class implementation hiện có.
3. Nếu chuyển provider thành named module, thêm `requires api.module` và `provides ... with ...`.
4. Nếu chuyển consumer thành named module, thêm `requires api.module` và `uses api.Service`.
5. Biên dịch, chạy trên module path và kiểm tra resolved module graph.
6. Nếu vẫn hỗ trợ classpath, kiểm thử riêng chế độ classpath và giữ service configuration file phù hợp.
7. Ghi rõ các combination được hỗ trợ trong tài liệu phát hành: classpath, module path, automatic module và custom runtime image.

Đây là giai đoạn dễ phát sinh khác biệt giữa môi trường cũ và mới vì classpath, automatic module và explicit named module có cách đăng ký và phân giải provider không hoàn toàn giống nhau.

## 11. Provider phải được phân giải trước khi tìm thấy

Một nhầm lẫn thường gặp là coi `--module-path` tương đương “nạp tất cả module trong thư mục”. Thực tế, module path đưa ra tập module có thể quan sát (*observable*); module system còn phải giải quyết (*resolve*) những module sẽ tham gia một configuration/module layer.

Các quan hệ `requires` và service binding có thể khiến module bổ sung được đưa vào graph. Với cấu hình khác, provider có thể không được phân giải dù file JAR đang nằm trong thư mục.

Để thêm provider một cách tường minh khi chạy ứng dụng mẫu:

```bash
java --module-path mods \
  --add-modules com.example.greeting.provider.vi \
  --module com.example.greeting.app/com.example.greeting.app.Main
```

Để xem module resolution:

```bash
java --show-module-resolution \
  --module-path mods \
  --module com.example.greeting.app/com.example.greeting.app.Main
```

Hãy kiểm tra output để xác định provider module có tham gia graph hay không. Trong các ứng dụng tạo `ModuleLayer` riêng, có thể dùng các API cấu hình có service binding như `Configuration.resolveAndBind` nếu muốn tự động bổ sung module cung cấp service; `Configuration.resolve` thông thường chỉ giải quyết các quan hệ module theo yêu cầu của cấu hình.

Nếu service không tìm thấy provider, cần phân biệt **provider chưa được resolve** với **provider đã resolve nhưng đăng ký sai**. Hai lỗi này có hướng xử lý khác nhau.

## 12. Tương tác với `jlink` và runtime image tối giản

`jlink` cho phép đóng gói runtime image chứa những module được chọn. Để giữ image nhỏ, `jlink` mặc định không thực hiện service binding. Vì vậy, một provider tự động tìm thấy trong lúc chạy với JDK đầy đủ có thể bị thiếu trong custom runtime image nếu không được chọn khi link.

Ví dụ tạo image từ các module ứng dụng và JDK:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.greeting.app,com.example.greeting.provider.vi \
  --output greeting-runtime
```

Ví dụ trên dành cho Linux/macOS, nơi dấu `:` ngăn cách các phần tử module path; Windows dùng dấu `;`. Khi dùng `jlink` thực tế, cần cung cấp các modular JAR/JMOD hợp lệ hoặc cấu trúc input được phiên bản công cụ hỗ trợ.

Nếu muốn đưa các service provider module quan sát được vào image theo quan hệ service, có thể dùng:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.greeting.app \
  --bind-services \
  --output greeting-runtime
```

`--bind-services` liên kết provider modules và dependency liên quan. Tập module có thể tăng đáng kể, nên cần xem kích thước image và thực hiện kiểm thử sau khi link. Trong môi trường có plugin tùy chọn, thường nên chọn provider tường minh để kiểm soát image tốt hơn.

Có thể dùng `jlink --suggest-providers <service-type>` khi tìm module cung cấp một service quan sát được. Runtime image đã tạo cần được kiểm thử với các đường chạy thật, bởi ServiceLoader chỉ là một phần trong hệ thống plugin có thể còn phụ thuộc reflection, resource, native library hoặc cấu hình bên ngoài.

## 13. Lỗi thường gặp và cách chẩn đoán

### 13.1. Consumer thiếu `uses`

Với explicit named module gọi ServiceLoader mà không khai báo service-use dependence, khi chạy có thể nhận `ServiceConfigurationError` thông báo module không khai báo `uses` cho service đó.

**Cách xử lý:** Thêm `uses com.example.greeting.api.GreetingService;` vào `module-info.java` của đúng module chứa code gọi ServiceLoader, sau đó biên dịch lại module.

### 13.2. Provider thiếu `provides`

Consumer duyệt ServiceLoader nhưng không thấy provider, dù module provider đã xuất hiện trong module path.

**Cách xử lý:** Kiểm tra module provider có `provides ... with ...`, provider module có được resolve và class sau `with` có đúng tên đầy đủ không.

### 13.3. Provider chỉ nằm trên module path nhưng chưa được resolve

Đường dẫn module chỉ mô tả nơi tìm module, không bảo đảm provider nằm trong module graph.

**Cách xử lý:** Xem `--show-module-resolution`, dùng `--add-modules` khi cần, hoặc kiểm tra chính sách service binding của module configuration/module layer.

### 13.4. Provider class không hợp lệ

Ví dụ provider constructor không `public`, thiếu constructor không tham số, không implements service type, hoặc provider factory trả về kiểu sai. Khi ServiceLoader thực sự tìm/khởi tạo provider, nó có thể ném `ServiceConfigurationError`.

**Cách xử lý:** Đối chiếu quy tắc constructor/provider method và kiểm tra lỗi gốc do factory/constructor ném ra.

### 13.5. Sai file `META-INF/services` trong classpath

Tên service file hoặc tên provider class sai, resource không được đưa vào JAR, hoặc tool đóng gói làm mất file services.

**Cách xử lý:** Kiểm tra nội dung JAR:

```bash
jar --list --file provider.jar
```

Đảm bảo file `META-INF/services/com.example.greeting.api.GreetingService` thực sự có trong JAR và chứa đúng tên provider.

### 13.6. `exports` không đúng nơi

Service interface nằm trong package mà module API không `exports`. Consumer và provider có thể không truy cập được service type khi biên dịch.

**Cách xử lý:** Export package chứa API từ module định nghĩa service. Không export package implementation nếu không có mục đích công bố API.

### 13.7. Provider class và service interface được tải bởi hai class loader khác nhau

Một plugin có thể mang bản sao riêng của service API. Dù tên class giống nhau, JVM xem các kiểu được nạp bằng class loader khác nhau là những kiểu khác nhau. Provider không còn assignable tới service type mà host dùng.

**Cách xử lý:** Thiết kế cơ chế chia sẻ API giữa host và plugin, kiểm tra class loader delegation và tránh đóng gói trùng service API ở những class loader không tương thích.

### 13.8. `findFirst()` chọn sai implementation

Ứng dụng chạy đúng ở máy A nhưng lại chọn provider khác ở máy B vì dựa vào thứ tự discovery.

**Cách xử lý:** Xác định tiêu chí lựa chọn tường minh trong service contract hoặc cấu hình; không coi thứ tự module là thứ tự ưu tiên.

## 14. Các công cụ hỗ trợ quan sát JPMS

Để kiểm tra descriptor trong một modular JAR:

```bash
jar --describe-module --file greeting-provider.jar
```

Để xem descriptor của module có trên module path:

```bash
java --module-path mods --describe-module com.example.greeting.provider.vi
```

Thông tin cần quan sát bao gồm tên module, `requires`, `uses` và `provides`. Nếu descriptor không phản ánh thay đổi gần đây, có thể pipeline đang đóng gói class file cũ hoặc sử dụng một JAR khác với file vừa biên dịch.

Để khảo sát các module dependency trong archive:

```bash
jdeps --print-module-deps --module-path mods greeting-app.jar
```

`jdeps` là công cụ phân tích tĩnh, không bảo đảm tìm ra mọi provider được nạp động. Kết hợp với `--show-module-resolution` và các bài kiểm thử chạy ứng dụng để biết provider thật sự được tìm thấy khi runtime hoạt động.

## 15. Bảo trì khả năng tương thích giữa các phiên bản

Một hệ thống plugin còn phải giữ tương thích giữa service API và các provider phát hành độc lập. Những thay đổi sau cần cân nhắc:

| Thay đổi | Rủi ro đối với provider cũ | Hướng xử lý |
|---|---|---|
| Thêm abstract method vào service interface | Provider cũ có thể không biên dịch lại được; lời gọi mới có thể gặp lỗi runtime. | Dùng default method hợp lý, API mới hoặc lộ trình nâng cấp provider. |
| Đổi tên hoặc xóa service type | `uses`, `provides` và file service configuration cũ mất hiệu lực. | Duy trì adapter hoặc phát hành API có version rõ ràng. |
| Đổi tên package implementation | Descriptor `provides ... with ...` có thể trỏ tới tên class không tồn tại. | Cập nhật descriptor và kiểm tra artifact đã đóng gói. |
| Tách module API | `requires` và `exports` có thể thay đổi; phải cập nhật module graph. | Kiểm tra biên dịch, package accessibility và resolution. |
| Đổi cách đóng gói provider (classpath → named module) | File `META-INF/services` không thay thế `provides` của explicit module. | Bổ sung descriptor và kiểm thử cả hai chế độ nếu còn hỗ trợ. |
| Tạo custom runtime image nhỏ hơn | Module provider có thể bị loại khi link. | Chọn provider tường minh hoặc dùng `--bind-services` có kiểm soát. |

Với API plugin có tuổi thọ dài, nên công bố quy tắc tương thích và baseline JDK. Nếu service interface cần thay đổi mạnh, một chiến lược là giữ interface phiên bản cũ cùng adapter trong giai đoạn chuyển tiếp, thay vì phá vỡ tất cả provider trong cùng một lần cập nhật.

## 16. Kiểm thử service discovery trong dự án

Kiểm thử chỉ khởi tạo implementation bằng `new` không xác nhận cơ chế ServiceLoader hoạt động. Cần có kiểm thử sử dụng chính module path và descriptor sẽ được phát hành.

Ví dụ với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.greeting.api.GreetingService;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;

class GreetingDiscoveryTest {
    @Test
    void discoversVietnameseProvider() {
        boolean found = ServiceLoader.load(GreetingService.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .anyMatch(service -> "vi".equals(service.languageTag()));

        assertTrue(found);
    }
}
```

Test cần được chạy trong môi trường có `uses`, `provides` và provider module đã resolve đúng. Nếu đặt test trong một module riêng, cần xét module nào thực sự gọi ServiceLoader và khai báo `uses` tương ứng; test runner có thể dùng classloader/module layer khác ứng dụng production.

Các trường hợp nên được kiểm thử:

1. Không có provider: consumer xử lý kết quả rỗng ra sao?
2. Có một provider: consumer tìm thấy và gọi được service?
3. Có nhiều provider: consumer chọn dựa trên capability và không phụ thuộc thứ tự?
4. Provider constructor hoặc factory ném lỗi: hệ thống ghi nhận lỗi có đủ thông tin?
5. Provider class ở module chưa resolve: log/giám sát cho thấy nguyên nhân?
6. Chạy từ classpath và module path (nếu cả hai được hỗ trợ): file service và descriptor đều đúng?
7. Chạy trong custom runtime image: provider module có thực sự hiện diện?
8. Chạy sau khi nâng service API: provider cũ còn tương thích nguồn, nhị phân và hành vi?

Khi ứng dụng triển khai nhiều plugin do bên thứ ba cung cấp, một bài kiểm thử contract cho provider là cần thiết: kiểm tra những method và invariant mà mọi implementation phải tuân thủ. ServiceLoader chỉ bảo đảm cơ chế khám phá/khởi tạo theo quy tắc cấu hình, không bảo đảm plugin thực hiện đúng yêu cầu nghiệp vụ.

## 17. Một quy trình migration có thể áp dụng

Giả sử thư viện cũ chứa `PaymentPlugin` và nhiều provider đăng ký qua `META-INF/services`. Để chuyển sang JPMS:

### Bước 1: Kiểm kê service types và providers

Liệt kê từng service interface, provider class, bản phân phối JAR và cách được nạp. Xác định các plugin ngoài repository hoặc chỉ được cài trong production.

### Bước 2: Tách service API ổn định

Đưa service contract vào một module chuyên trách và `exports` package chứa API. Provider phụ thuộc module API; consumer cũng phụ thuộc module API.

### Bước 3: Thêm khai báo module

Ở consumer, khai báo `uses`. Ở mỗi provider explicit named module, khai báo `provides ... with ...`. Chọn constructor hoặc provider method phù hợp.

### Bước 4: Kiểm tra module resolution

Build đúng modular artifact, xem descriptor, chạy `--show-module-resolution` và xác nhận provider module tham gia graph. Nếu dùng runtime image, kiểm tra bước `jlink`.

### Bước 5: Kiểm thử tương thích hai chiều cần hỗ trợ

Chạy trên classpath nếu vẫn cần hỗ trợ hệ thống cũ, chạy trên module path cho hệ thống mới, và kiểm thử cả consumer mới với provider đã phát hành trước đó.

### Bước 6: Tách chính sách chọn provider

Không dựa vào thứ tự discovery; thêm cơ chế chọn theo định danh, capability hoặc cấu hình. Định nghĩa rõ khi không có provider hoặc có nhiều provider cùng đáp ứng.

### Bước 7: Quan sát production

Ghi log một lần lúc khởi động về service đang dùng, provider được chọn, tên module và version plugin khi có metadata. Tránh ghi dữ liệu nhạy cảm; lỗi provider phải được đưa vào cơ chế giám sát của ứng dụng.

## 18. Câu hỏi thường gặp

**Module consumer đã `requires` API rồi, có cần `uses` nữa không?**

Có, nếu đây là explicit named module gọi ServiceLoader để tìm provider cho service. `requires` tạo quyền đọc type, còn `uses` khai báo phụ thuộc service discovery.

**Provider module có cần `exports` package chứa implementation không?**

Không. Provider class có thể được ServiceLoader khởi tạo thông qua `provides` dù package implementation không export. Đây là một lợi ích của encapsulation trong JPMS.

**Có cần consumer `requires` tất cả provider module không?**

Không. Consumer nên phụ thuộc vào service API. Module resolution hoặc bước cấu hình khi chạy/link đảm bảo các provider cần thiết có mặt.

**ServiceLoader có bảo đảm phát hiện provider trong mọi JAR trên ổ đĩa không?**

Không. Nó tìm trong phạm vi class loader hoặc module layer/configuration liên quan. JAR chưa được đưa vào classpath/module graph thích hợp sẽ không tự trở thành provider có thể sử dụng.

**Có thể đăng ký provider bằng cả `provides` và `META-INF/services` không?**

Có thể duy trì cả hai dạng metadata trong một JAR nhằm phục vụ các chế độ chạy khác nhau, nhưng explicit named module dùng khai báo `provides` cho service provider của nó. Cần kiểm tra đóng gói và tránh dựa vào registration trùng lặp.

**Có thể dùng ServiceLoader làm plugin manager hoàn chỉnh không?**

ServiceLoader tập trung vào discovery và instantiation. Quản lý version, phụ thuộc, vòng đời, cô lập lỗi, cấp quyền, nâng cấp tại runtime và chính sách chọn plugin vẫn cần thiết kế thêm.

## 19. Checklist khi thiết kế và phát hành module service

- [ ] Service interface hoặc abstract service class đã được công bố trong package phù hợp.
- [ ] Module chứa service API `exports` đúng package cho consumer và provider.
- [ ] Explicit named module gọi ServiceLoader đã khai báo `uses` cho đúng service.
- [ ] Provider module có `requires` service API và `provides ... with ...` đúng tên lớp.
- [ ] Provider dùng public no-arg constructor hoặc provider method hợp lệ.
- [ ] Package implementation chỉ `exports`/`opens` khi thật sự cần.
- [ ] Provider module đã được đưa vào resolved module graph.
- [ ] `META-INF/services` được đóng gói đúng nếu hệ thống còn hỗ trợ classpath/automatic module.
- [ ] Chính sách chọn provider không phụ thuộc vào thứ tự discovery.
- [ ] Đã xác định hành vi khi không có provider, có nhiều provider hoặc provider khởi tạo lỗi.
- [ ] Không chia sẻ một ServiceLoader instance giữa nhiều thread mà không kiểm soát truy cập.
- [ ] Đã kiểm thử trên module path, classpath và runtime image trong những cấu hình được hỗ trợ.
- [ ] Đã kiểm thử tương thích với service API và provider từ các bản phát hành trước.

## Tài liệu tham khảo

- [Java API — ServiceLoader (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): định nghĩa service/provider, lazy loading, registration và các overload của `load`.
- [JLS 7.7 — Module Declarations](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html#jls-7.7): cú pháp và quy tắc `requires`, `exports`, `uses`, `provides`.
- [Module API — `canUse` và `addUses`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): truy vấn và điều chỉnh service dependency trong trường hợp framework phù hợp.
- [Configuration — `resolveAndBind`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/module/Configuration.html): phân giải module graph kết hợp service binding.
- [Oracle jlink Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html): các tùy chọn `--bind-services` và `--add-modules`.

## Kết luận

`ServiceLoader` là cơ chế kết nối giữa service API, consumer và provider mà không cần phụ thuộc trực tiếp vào implementation. Trong JPMS, consumer explicit named module khai báo `uses` để tìm service, provider module khai báo `provides ... with ...` để đăng ký implementation, còn `requires` và `exports` điều khiển quyền đọc module và khả năng truy cập service type. Khi migration từ classpath sang module path, hãy kiểm tra metadata `META-INF/services`, module resolution, điều kiện khởi tạo provider và chính sách chọn implementation. Các bài kiểm thử discovery trên artifact thực tế và custom runtime image giúp phát hiện những lỗi mà việc gọi `new` trực tiếp không thể thấy.
