# Service provider và giới hạn phụ thuộc động khi tạo runtime trong Java 17

Java có cơ chế **service provider** để một module công bố implementation của một service, còn module khác chỉ phụ thuộc vào contract của service đó. Ứng dụng tìm implementation bằng `ServiceLoader` thay vì phải gọi trực tiếp constructor của từng provider.

Cơ chế này đặc biệt quan trọng khi đóng gói ứng dụng thành runtime image bằng `jlink`. Một provider được tìm thấy động lúc chạy vẫn phải có mặt trong module graph mà JVM có thể quan sát. `jlink` không thể đoán mọi plugin hoặc thư viện mà ứng dụng có thể tải trong tương lai. Khi tạo image, cần chỉ rõ các module gốc, cho phép liên kết provider bằng `--bind-services` và hiểu giới hạn của `--limit-modules`.

Các khái niệm chính:

- **Service:** contract, thường là interface hoặc abstract class mà ứng dụng cần.
- **Provider:** implementation cung cấp service đó.
- **`uses` / `provides`:** directive trong `module-info.java` khai báo module dùng service và module cung cấp implementation.
- **`ServiceLoader`:** API tìm và khởi tạo provider tại runtime.
- **Service binding trong `jlink`:** bổ sung provider modules cùng dependency của chúng vào runtime image khi tạo image.
- **Giới hạn phụ thuộc động:** provider chỉ được phát hiện nếu module hoặc class tương ứng nằm trong phạm vi runtime có thể nạp và được cấu hình để tìm.

## 1. Vì sao cần service provider?

Giả sử ứng dụng có nhiều cách đọc dữ liệu: JSON, XML và CSV. Nếu ứng dụng gọi trực tiếp từng implementation, module ứng dụng sẽ phụ thuộc vào tất cả implementation:

```java
JsonCodec json = new JsonCodec();
XmlCodec xml = new XmlCodec();
CsvCodec csv = new CsvCodec();
```

Cách này làm module ứng dụng biết tên và cách tạo từng provider. Khi thêm định dạng mới, phải sửa code điều phối và có thể phải sửa dependency của ứng dụng.

Thay vào đó, ứng dụng định nghĩa một service contract:

```java
package com.example.codec.api;

public interface Codec {
    String format();
    Object decode(byte[] input);
}
```

Các provider triển khai contract:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public Object decode(byte[] input) {
        return new String(input, java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Ứng dụng chỉ cần tìm các `Codec`:

```java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.format());
}
```

Ứng dụng phụ thuộc vào contract `Codec`. Việc provider nào được cài đặt và có thể được phát hiện là quyết định của môi trường triển khai.

### 1.1. Service provider không phải dependency injection framework

`ServiceLoader` là cơ chế chuẩn của Java để tìm provider theo service contract. Nó không tự cung cấp toàn bộ chức năng của một dependency injection container:

- Không tự quản lý vòng đời ứng dụng của mọi provider.
- Không tự inject dependency tùy ý vào constructor.
- Không tự chọn provider theo business priority.
- Không tạo sandbox cho code provider.
- Không tự tải thư viện từ Internet.

Nếu cần chọn implementation theo cấu hình, quản lý scope hoặc dependency graph phức tạp, ứng dụng có thể xây dựng lớp điều phối phía trên `ServiceLoader` hoặc dùng framework phù hợp.

## 2. Khai báo service trong module API

Với JPMS, service contract thường nằm trong module riêng và package chứa contract được export.

Cấu trúc ví dụ:

```text
modules/
├── com.example.codec.api/
│   ├── module-info.java
│   └── com/example/codec/api/Codec.java
├── com.example.codec.json/
│   ├── module-info.java
│   └── com/example/codec/json/JsonCodec.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
```

Module API:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

`exports` cho phép module khác truy cập kiểu public trong package service contract.

Service API không cần biết provider nào sẽ được sử dụng. Nhờ vậy, module API có thể được dùng bởi nhiều provider độc lập.

### 2.1. Vì sao tách service API thành module riêng?

Một module API nhỏ tạo ranh giới dependency rõ ràng:

```text
                com.example.app
                       |
                       | requires
                       v
               com.example.codec.api
                       ^
                       | requires
                       |
              com.example.codec.json
```

- Ứng dụng đọc contract từ module API.
- Provider cũng đọc contract từ module API.
- Ứng dụng không cần `requires` trực tiếp provider nếu provider được phát hiện qua service binding.
- Provider có thể được thay thế hoặc bổ sung mà không sửa service contract, miễn là tương thích.

Nếu service interface nằm bên trong module ứng dụng, provider bên ngoài có thể khó phụ thuộc vào contract mà không tạo dependency vòng. Tách API giúp tránh vấn đề đó.

## 3. Directive `uses` trong module tiêu thụ service

Module gọi `ServiceLoader` cần khai báo service mà nó sử dụng bằng directive `uses`.

```java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

Ý nghĩa:

- `requires com.example.codec.api` tạo readability tới module chứa kiểu `Codec`.
- `uses com.example.codec.api.Codec` khai báo module app cần tìm provider cho service đó.

`uses` không khai báo module provider cụ thể. Nó cũng không có nghĩa mọi provider đều tự động được đóng gói vào runtime image.

Nếu code trong named module gọi `ServiceLoader.load(Codec.class)` mà module descriptor không khai báo `uses Codec`, service loading có thể thất bại với `ServiceConfigurationError`. Hãy đặt directive `uses` trong module thực hiện việc tìm service.

### 3.1. Một module có thể dùng nhiều service

```java
module com.example.app {
    requires com.example.codec.api;
    requires com.example.storage.api;

    uses com.example.codec.api.Codec;
    uses com.example.storage.api.Storage;
}
```

Mỗi service được khai báo bằng một directive riêng. Tên trong `uses` là tên đầy đủ của kiểu service, không phải tên module.

### 3.2. uses không thay thế requires

Nếu `Codec` nằm trong module `com.example.codec.api`, app vẫn cần đọc module API:

```java
module com.example.app {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Chỉ có `uses` không tự tạo readability tới module chứa service type. Hai directive giải quyết hai việc khác nhau: `requires` cho phép đọc kiểu; `uses` khai báo nhu cầu service.

## 4. Directive `provides ... with ...` trong module provider

Module provider khai báo implementation bằng `provides`:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Trong đó:

- `com.example.codec.api.Codec` là service type.
- `com.example.codec.json.JsonCodec` là provider implementation.
- Provider module cần đọc module chứa service type, thường bằng `requires`.
- Package implementation không nhất thiết phải export cho module tiêu thụ.

Class provider truyền thống phải là class public và có public no-argument constructor để `ServiceLoader` tạo instance.

Ví dụ:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public Object decode(byte[] input) {
        return new String(input, java.nio.charset.StandardCharsets.UTF_8);
    }
}
```

Không cần khai báo `exports com.example.codec.json` chỉ để `ServiceLoader` tìm provider. Module system dùng provider declaration để định vị implementation. Việc export package implementation chỉ cần thiết nếu đó là API công khai mà module khác cần import trực tiếp.

### 4.1. Provider method

JPMS còn cho phép khai báo provider bằng một class có public static method tên `provider`, không tham số, trả về service type hoặc subtype:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodecProvider {
    private JsonCodecProvider() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
```

Module descriptor:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodecProvider;
}
```

Trong dạng này, class được liệt kê trong `provides` là provider class có method `provider()`. Nó không bắt buộc phải chính là implementation class của service; method trả về instance thực hiện contract.

Provider method hữu ích khi implementation cần được tạo theo cách riêng hoặc khi muốn ẩn class implementation cụ thể khỏi API.

### 4.2. Provider implementation không cần export

Ví dụ:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.internal.JsonCodec;
}
```

Package `com.example.codec.json.internal` có thể không export. ServiceLoader vẫn có thể tạo provider theo metadata module đã khai báo.

Đây là một ưu điểm của service provider: ứng dụng phụ thuộc vào service contract, không phụ thuộc package implementation.

## 5. Tìm provider bằng ServiceLoader

`ServiceLoader` thuộc `java.util`. Cách sử dụng phổ biến:

```java
import com.example.codec.api.Codec;

import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println(codec.format());
        }
    }
}
```

`ServiceLoader.load` tạo một service loader để tìm provider phù hợp với service type. Việc phát hiện và khởi tạo provider là lazy: provider thường được tạo khi iterator hoặc stream được tiêu thụ, không nhất thiết ngay tại thời điểm gọi `load`.

### 5.1. Lấy provider đầu tiên

```java
Codec codec = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No Codec provider found"));
```

Cách này phù hợp khi ứng dụng chỉ cần một provider và môi trường bảo đảm chỉ có một implementation phù hợp.

Nếu có nhiều provider, không nên mặc định provider đầu tiên luôn là provider mong muốn. Thứ tự phát hiện không nên được dùng như business priority. Hãy chọn theo cấu hình hoặc thuộc tính rõ ràng như `format()`.

### 5.2. Duyệt metadata provider bằng stream

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

loader.stream()
        .map(ServiceLoader.Provider::type)
        .forEach(System.out::println);
```

`Provider.type()` cho biết class provider mà không cần gọi `get()` để lấy instance. Khi cần tạo instance:

```java
Codec codec = loader.stream()
        .filter(provider ->
                provider.type().getName().contains("Json"))
        .map(ServiceLoader.Provider::get)
        .findFirst()
        .orElseThrow();
```

Đây là ví dụ minh họa cách lọc metadata; trong ứng dụng thực tế, nên chọn theo contract hoặc cấu hình ổn định thay vì phụ thuộc tên class implementation.

### 5.3. Cache và reload

Một `ServiceLoader` có cache các provider đã được phát hiện. `reload()` xóa cache để lần duyệt tiếp theo phát hiện lại provider theo cơ chế loader hiện tại:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// Sử dụng loader...
loader.reload();
```

`reload()` không tự cài module mới vào runtime image, không tự thêm JAR vào module path và không tự tạo module layer. Nếu tập module có thể quan sát không thay đổi, reload không làm xuất hiện provider nằm ngoài phạm vi đó.

### 5.4. Chọn module layer tường minh

Khi ứng dụng dùng module layer riêng cho plugin, có thể gọi:

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(pluginLayer, Codec.class);
```

Overload này tìm provider trong module layer được chỉ định và các layer cha theo quy tắc của API. Nó hữu ích khi provider không nằm trong boot layer mặc định.

Trong named module, module thực hiện lời gọi service loading vẫn phải khai báo `uses` cho service type.

## 6. Service provider trên classpath và module path

Java hỗ trợ service loading trong cả mô hình classpath và JPMS.

| Môi trường | Cách khai báo provider |
|---|---|
| Classpath | File `META-INF/services/<tên-service>` trong JAR |
| Named module | Directive `provides Service with Provider` trong `module-info.java` |
| Automatic module | Có thể suy ra provider từ file service configuration trong JAR theo quy tắc automatic module |

Ví dụ cấu hình classpath:

```text
META-INF/services/com.example.codec.api.Codec
```

Nội dung file có tên class provider:

```text
com.example.codec.json.JsonCodec
```

Cơ chế này vẫn hữu ích cho thư viện cần chạy trên classpath. Trong named module được thiết kế theo JPMS, khai báo `uses` và `provides` trong descriptor làm dependency service rõ ràng hơn.

### 6.1. Không trộn nhầm module name với provider class name

Trong `module-info.java`:

```java
uses com.example.codec.api.Codec;

provides com.example.codec.api.Codec
    with com.example.codec.json.JsonCodec;
```

`uses` và `provides` nhận tên kiểu Java đầy đủ. `requires` mới nhận tên module.

Ví dụ:

```java
requires com.example.codec.api;
```

Đây là module name; nó không nhất thiết bằng package name của service type.

## 7. Service provider và module graph

Service provider tạo một kiểu liên kết khác với `requires` thông thường.

Sơ đồ:

```text
             com.example.app
                    |
                    | requires
                    v
            com.example.codec.api
                    ^
                    | requires
                    |
           com.example.codec.json

com.example.app:
    uses com.example.codec.api.Codec

com.example.codec.json:
    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec
```

App không cần viết `requires com.example.codec.json` nếu chỉ muốn tìm provider thông qua service contract. Provider module được phát hiện qua service binding.

Điều này giúp module app tránh phụ thuộc compile-time vào implementation cụ thể. Tuy nhiên, provider module vẫn phải được tìm thấy và đưa vào module graph tại runtime hoặc trong runtime image.

### 7.1. Service binding không phải tải module từ xa

`ServiceLoader` không tự tìm mọi JAR trên máy và cũng không tải module từ Internet. Nó chỉ phát hiện provider trong phạm vi class loader/module layer mà service loader đang sử dụng.

Provider cần:

- Có mặt trên classpath hoặc module path phù hợp.
- Có service declaration tương ứng.
- Có thể được module resolver/class loader tìm thấy.
- Có dependency cần thiết.
- Tương thích với service API mà consumer sử dụng.

Nếu provider JAR không được triển khai, ServiceLoader không thể tự tạo ra implementation còn thiếu.

## 8. jlink và runtime image tùy chỉnh

`jlink` tạo một runtime image tùy chỉnh từ tập module được phân giải. Image thường chứa launcher, runtime libraries và các module được chọn để ứng dụng chạy mà không cần cài một JDK đầy đủ trên máy đích.

Ví dụ:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output runtime
```

Trong đó:

- `--module-path` chỉ nơi tìm module của JDK và module ứng dụng.
- `--add-modules` chọn module gốc cần đưa vào graph.
- `--output` chỉ thư mục runtime image được tạo.

Các module được yêu cầu bằng `requires` và dependency của chúng được phân giải theo module graph. Tuy nhiên, provider chỉ được tìm động qua service có thể không thuộc dependency graph `requires` thông thường.

Đó là lý do cần hiểu `--bind-services`.

### 8.1. Runtime image không phải bản sao toàn bộ JDK

`jlink` chỉ liên kết các module cần thiết theo cấu hình. Runtime image có thể nhỏ hơn JDK đầy đủ và không nhất thiết chứa các module JDK không nằm trong graph, provider module không được liên kết, thư viện ứng dụng chỉ nằm trên classpath, plugin sẽ được tải từ thư mục ngoài trong tương lai hoặc native library/resource không được triển khai cùng ứng dụng.

Vì vậy, ứng dụng chạy tốt trên JDK đầy đủ chưa chắc chạy được trên runtime image tối giản. Cần kiểm tra cả module dependency tĩnh và dependency động qua service/reflection.

## 9. `jlink --bind-services` liên kết provider modules

Option:

```bash
--bind-services
```

yêu cầu `jlink` liên kết các service provider modules và dependency của chúng khi tạo runtime image.

Ví dụ:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

Giả sử:

- `com.example.app` khai báo `uses com.example.codec.api.Codec`.
- `com.example.codec.json` khai báo `provides com.example.codec.api.Codec with ...`.
- Provider module và các dependency của nó có mặt trên module path.

`--bind-services` cho phép jlink tìm provider tương ứng và thêm module provider cùng dependency cần thiết vào image.

### 9.1. Nếu không có --bind-services

Nếu provider module không nằm trong graph do `requires` và cũng không được chọn trực tiếp bằng `--add-modules`, nó có thể không được đưa vào runtime image.

Khi ứng dụng chạy trong image đó, ServiceLoader có thể không tìm thấy provider. Điều này không có nghĩa `ServiceLoader` bị hỏng; provider đơn giản là không có trong phạm vi runtime image/module layer đang chạy.

### 9.2. Khi provider đã được thêm trực tiếp

Nếu biết rõ provider module, có thể thêm nó thành root:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,com.example.codec.json \
  --output runtime
```

Khi provider được thêm trực tiếp, `jlink` sẽ phân giải module đó cùng dependency của nó. Cách này hữu ích khi muốn đóng gói chính xác một tập provider đã biết.

`--bind-services` thuận tiện hơn khi muốn liên kết provider theo service contract mà không phải liệt kê từng implementation bằng tay.

### 9.3. bind-services không phải include-all

`--bind-services` không có nghĩa đưa tất cả module hoặc mọi JAR trong thư mục vào runtime. Nó liên kết provider cho service được sử dụng trong module graph và có thể quan sát trên module path.

Nếu provider không khai báo service, không có mặt trên module path hoặc bị giới hạn khỏi module universe, jlink không thể tự phát hiện nó.

## 10. Các option jlink ảnh hưởng tới phụ thuộc động

Ba option cần hiểu cùng nhau:

| Option | Vai trò |
|---|---|
| `--add-modules` | Chọn module gốc để phân giải và đưa vào image |
| `--bind-services` | Liên kết service provider modules và dependency của chúng |
| `--limit-modules` | Giới hạn tập module mà module resolver có thể quan sát |

### 10.1. --add-modules

Ví dụ:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,java.logging \
  --bind-services \
  --output runtime
```

`com.example.app` và `java.logging` được chọn làm root. Các dependency của chúng được phân giải; `--bind-services` bổ sung provider phù hợp.

Dùng `--add-modules` khi ứng dụng cần một module nhưng dependency tĩnh không kéo module đó vào graph, hoặc khi cần đưa một provider module đã biết vào image.

### 10.2. --limit-modules

`--limit-modules` giới hạn universe module có thể quan sát khi phân giải:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --limit-modules java.base,java.logging,com.example.app,com.example.codec.api,com.example.codec.json \
  --bind-services \
  --output runtime
```

Ví dụ trên chỉ mang tính minh họa: tập module được giới hạn phải bao gồm dependency cần thiết và provider muốn liên kết. Nếu provider bị loại khỏi tập module có thể quan sát, service binding không thể thêm provider đó.

Không nên dùng `--limit-modules` quá sớm chỉ để giảm dung lượng image. Hãy xác định module cần thiết, provider đang dùng và dependency của provider trước.

### 10.3. --suggest-providers

`jlink` có thể gợi ý provider cho service type được dùng bởi module:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --suggest-providers com.example.app
```

Option này hữu ích khi kiểm tra các provider có thể liên quan trước khi tạo image. Nó là công cụ hỗ trợ khám phá, không thay thế việc kiểm tra module descriptor và xác nhận provider thực sự được đưa vào image.

### 10.4. Thứ tự suy nghĩ khi cấu hình jlink

1. Chọn module ứng dụng làm root bằng `--add-modules`.
2. Xác định module service API mà ứng dụng `uses`.
3. Kiểm tra provider module có `provides` đúng service type.
4. Đảm bảo provider và dependency có mặt trên module path.
5. Dùng `--bind-services` nếu muốn jlink liên kết provider tự động.
6. Chỉ dùng `--limit-modules` khi đã biết tập module được phép quan sát.
7. Kiểm tra image sau khi tạo bằng `--list-modules` và chạy thử service loading.

## 11. Ví dụ hoàn chỉnh: tạo runtime image có JSON provider

### 11.1. Module API

```java
// modules/com.example.codec.api/module-info.java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

```java
// modules/com.example.codec.api/com/example/codec/api/Codec.java
package com.example.codec.api;

public interface Codec {
    String format();
    String decode(byte[] input);
}
```

### 11.2. Module provider

```java
// modules/com.example.codec.json/module-info.java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

```java
// modules/com.example.codec.json/com/example/codec/json/JsonCodec.java
package com.example.codec.json;

import com.example.codec.api.Codec;
import java.nio.charset.StandardCharsets;

public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String decode(byte[] input) {
        return new String(input, StandardCharsets.UTF_8);
    }
}
```

### 11.3. Module ứng dụng

```java
// modules/com.example.app/module-info.java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

```java
// modules/com.example.app/com/example/app/Main.java
package com.example.app;

import com.example.codec.api.Codec;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

        for (Codec codec : loader) {
            System.out.println("Provider: " + codec.getClass().getName());
            System.out.println("Format: " + codec.format());
        }
    }
}
```

### 11.4. Biên dịch các module

Từ thư mục dự án:

```bash
javac --module-source-path modules \
  -d out \
  -m com.example.codec.api,com.example.codec.json,com.example.app
```

Kết quả tạo các module đã biên dịch dưới thư mục `out`.

### 11.5. Chạy trên JDK đầy đủ

```bash
java --module-path out \
  --module com.example.app/com.example.app.Main
```

Ở môi trường này, cả ba module được đặt trên module path. Provider JSON có thể được tìm thấy bởi ServiceLoader vì provider module hiện diện và có service declaration.

### 11.6. Tạo runtime image bằng bind-services

Trên Linux/macOS:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:out" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

Trên Windows PowerShell, module path dùng dấu chấm phẩy:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;out" --add-modules com.example.app --bind-services --output runtime
```

### 11.7. Kiểm tra runtime image

```bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.example.codec.json
runtime/bin/java --module com.example.app/com.example.app.Main
```

Trên Windows, launcher nằm ở `runtime\bin\java.exe`.

Kết quả ứng dụng dự kiến:

```text
Provider: com.example.codec.json.JsonCodec
Format: json
```

Nếu provider không xuất hiện, kiểm tra app đã khai báo `uses` chưa, provider descriptor có `provides ... with ...` chưa, provider module có trên module path khi chạy jlink không, có dùng `--bind-services` hoặc thêm provider bằng `--add-modules` không, `--limit-modules` có loại provider khỏi universe không và service API có cùng module/type identity giữa app và provider không.

## 12. Giới hạn phụ thuộc động khi tạo runtime

Đây là phần cần hiểu kỹ nhất khi đóng gói ứng dụng modular.

### 12.1. jlink chỉ liên kết module có thể quan sát lúc build

`jlink` chạy ở thời điểm build/deployment. Nó phân giải module graph từ module path và các option được cung cấp. Nó không biết một plugin sẽ được tải từ Internet, ổ đĩa khác hoặc hệ thống quản trị plugin sau nhiều tháng.

Nếu provider chỉ xuất hiện sau khi runtime image đã được tạo, provider đó không thể tự nhiên nằm trong image đã build.

Muốn dùng provider được cài thêm sau này, phải triển khai module/JAR cùng dependency của nó và nạp bằng module path hoặc module layer phù hợp.

### 12.2. Service binding chỉ xử lý provider được khai báo và có thể tìm

`--bind-services` không phải phép quét mọi class để đoán implementation. Provider cần được khai báo theo service mechanism:

- Named module dùng `provides`.
- Classpath service provider dùng `META-INF/services`.
- Provider module phải nằm trong module path có thể quan sát tại thời điểm link.
- Service type phải được module trong graph sử dụng qua `uses`.

Nếu provider không khai báo service hoặc không có mặt trong module path, service binding không thể thêm nó vào image.

### 12.3. jlink không đóng gói automatic module hoặc thư viện classpath tùy ý

`jlink` tạo runtime image từ module có thể liên kết theo module system. Automatic module và JAR chỉ chạy trên classpath không thể được dùng như module thông thường để link trực tiếp vào custom runtime image.

Nếu thư viện vẫn là classpath-only:

- Có thể triển khai JAR bên cạnh runtime image và chạy bằng classpath nếu ứng dụng được thiết kế theo cách đó.
- Hoặc chuyển thư viện thành named module phù hợp trước khi link.
- Nếu thư viện là automatic module, cần kiểm tra khả năng modular hóa hoặc dùng phương án triển khai khác; không giả định jlink sẽ tự biến nó thành explicit module.

Không nhầm việc một JAR có thể chạy trên module path dưới dạng automatic module với việc nó có thể được jlink đóng gói như explicit module.

### 12.4. Reflection và tên class động có thể không xuất hiện trong requires

Một ứng dụng có thể tải class bằng:

```java
Class.forName("com.example.plugin.CustomPlugin");
```

Tên class được tạo từ cấu hình hoặc dữ liệu bên ngoài có thể không được công cụ phân tích dependency tĩnh phát hiện đầy đủ. Tương tự, JNI, resource lookup, service loading và plugin discovery có thể tạo phụ thuộc không thể suy ra chỉ từ các lệnh import.

Khi tạo runtime image, hãy lập danh sách dependency động đã biết và xác nhận chúng được đưa vào image hoặc triển khai ngoài image theo thiết kế.

### 12.5. --limit-modules có thể loại bỏ provider

Nếu provider module không nằm trong module universe được phép quan sát, resolver không thể chọn provider đó. Một image quá tối giản có thể chạy được đường code chính nhưng không có provider mà ứng dụng mong đợi.

Khi dùng `--limit-modules`, kiểm tra lại service binding sau khi link. Đừng chỉ kiểm tra module app và module API; hãy kiểm tra provider module cũng có mặt.

### 12.6. Module layer chỉ nạp được module đã triển khai và phân giải được

`ModuleLayer` cho phép tạo module layer mới lúc runtime, nhưng module finder vẫn cần tìm được module và dependency của nó. Đây không phải cơ chế tự tải dependency từ xa hoặc bỏ qua module resolution.

Plugin phải có module descriptor hợp lệ hoặc dạng triển khai được hỗ trợ, module name duy nhất trong phạm vi cấu hình, dependency cần thiết trên module path, service provider declaration đúng nếu muốn tìm bằng `ServiceLoader` và service API tương thích với module cha mà plugin đọc.

## 13. Nạp provider bên ngoài runtime image bằng ModuleLayer

Một ứng dụng có thể giữ runtime image gọn và triển khai plugin modular ở một thư mục riêng. Khi chạy, ứng dụng tạo module layer cho plugin.

Giả sử:

```text
runtime/
plugins/
└── com.example.codec.xml.jar
```

Plugin module khai báo:

```java
module com.example.codec.xml {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.xml.XmlCodec;
}
```

Ứng dụng đã có service API trong boot layer. Có thể tìm module plugin từ thư mục ngoài:

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;

ModuleFinder finder = ModuleFinder.of(Path.of("plugins"));

Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolve(
                        finder,
                        ModuleFinder.of(),
                        Set.of("com.example.codec.xml")
                );

ModuleLayer pluginLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader()
                );
```

Sau đó tìm service provider trong layer:

```java
ServiceLoader<Codec> plugins =
        ServiceLoader.load(pluginLayer, Codec.class);

for (Codec codec : plugins) {
    System.out.println(codec.format());
}
```

Ví dụ này giả định app module đã khai báo `uses com.example.codec.api.Codec`, plugin JAR là named module hợp lệ, plugin đọc được service API từ parent layer, tất cả dependency của plugin đều có thể được phân giải và plugin được triển khai trong thư mục `plugins`.

`defineModulesWithOneLoader` tạo một class loader cho các module trong layer mới. Nếu cần loader riêng cho từng module, có thể cân nhắc `defineModulesWithManyLoaders`.

### 13.1. ModuleLayer không tự giải quyết mọi xung đột plugin

Nếu hai plugin mang module name trùng nhau hoặc yêu cầu các phiên bản API không tương thích, module resolution có thể thất bại hoặc việc triển khai không thể đáp ứng cùng một graph.

JPMS không cung cấp cơ chế version selection giống dependency manager. Cần quản lý version, module name, dependency và compatibility ở quy trình build/deploy.

### 13.2. Provider bên ngoài không nằm trong image

`--bind-services` khi tạo runtime image chỉ liên kết provider có thể quan sát tại thời điểm link. Plugin được triển khai sau đó cần được nạp qua module path hoặc layer mới.

| Mô hình | Ưu điểm | Giới hạn |
|---|---|---|
| Link provider vào image bằng `--bind-services` | Image tự chứa provider; runtime đơn giản | Muốn thêm provider thường phải tạo image mới |
| Triển khai plugin ngoài image và tạo ModuleLayer | Có thể cài/thay plugin độc lập | Phải quản lý dependency, compatibility và module resolution lúc chạy |

## 14. Dùng jdeps và công cụ JDK để tìm dependency

`jdeps` phân tích dependency ở mức package/module từ class hoặc JAR. Nó hữu ích để tìm dependency tĩnh, nhưng không thể thay thế việc kiểm tra service declaration, reflection hoặc plugin configuration.

Ví dụ:

```bash
jdeps --module-path out \
      --print-module-deps \
      --module com.example.app
```

Output có thể dùng làm đầu vào để hiểu các module dependency cần thiết. Tuy nhiên, hãy xem module descriptor và service provider riêng.

Để xem descriptor trong JAR:

```bash
jar --describe-module --file out/com.example.codec.json.jar
```

Để xem module trong runtime image:

```bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.example.codec.json
```

Để gợi ý provider:

```bash
jlink --module-path "$JAVA_HOME/jmods:out" \
      --suggest-providers com.example.app
```

Các lệnh này trả lời những câu hỏi khác nhau:

- `jdeps`: bytecode/module có dependency tĩnh nào?
- `jar --describe-module`: JAR khai báo module/service thế nào?
- `jlink --suggest-providers`: có provider nào cho service được dùng?
- `java --list-modules`: runtime image có module nào?
- `java --describe-module`: descriptor module đang có trong runtime ra sao?

Không dùng riêng một lệnh để kết luận toàn bộ dependency động đã được đóng gói đầy đủ.

## 15. Lỗi thường gặp khi tạo runtime có service provider

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ServiceLoader không tìm thấy provider trong JDK đầy đủ | Thiếu `uses` hoặc provider không có `provides`/service metadata đúng | Kiểm tra consumer và provider descriptor |
| Chạy trên JDK đầy đủ được nhưng image không tìm thấy provider | Provider không được link vào image | Dùng `--bind-services` hoặc thêm provider bằng `--add-modules` |
| jlink báo module not found | Module API/provider hoặc dependency không có trên module path | Kiểm tra module path và module name |
| Provider không được phát hiện sau khi dùng --limit-modules | Module provider bị loại khỏi observable universe | Điều chỉnh tập module được giới hạn |
| Provider class không khởi tạo được | Thiếu public no-arg constructor/provider method hoặc dependency runtime | Kiểm tra provider declaration và lỗi ServiceConfigurationError |
| Plugin ngoài image không load | Plugin/dependency chưa được đưa vào module finder/layer | Triển khai đầy đủ module path và resolve layer |
| JAR chạy trên classpath nhưng jlink không link được | JAR không phải explicit module phù hợp | Modular hóa hoặc triển khai theo mô hình classpath bên ngoài image |
| Có nhiều provider nhưng chọn sai | Dựa vào thứ tự provider | Chọn theo cấu hình hoặc thuộc tính contract rõ ràng |
| Image chạy được nhưng tính năng tùy chọn lỗi | Dependency động qua reflection/service chưa được đóng gói | Liệt kê và kiểm tra dependency động |
| Hai plugin không tương thích | Trùng module name hoặc dependency/API không cùng phiên bản | Quản lý module name và compatibility ở build/deploy |

### 15.1. ServiceLoader trả rỗng không nhất thiết là lỗi JVM

`ServiceLoader.load` có thể trả loader hợp lệ dù không có provider. Nếu không có provider, iterator không có phần tử và `findFirst()` trả `Optional.empty()`.

Ứng dụng cần quyết định service có bắt buộc hay tùy chọn:

```java
Codec codec = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException(
                        "No codec provider is installed"
                ));
```

Nếu service là tính năng tùy chọn, có thể hiển thị trạng thái phù hợp hoặc bỏ qua chức năng đó. Nếu service bắt buộc, fail-fast lúc khởi động giúp phát hiện lỗi đóng gói sớm.

### 15.2. ServiceConfigurationError

`ServiceLoader` có thể ném `ServiceConfigurationError` khi provider metadata sai, provider không thể khởi tạo hoặc provider không thỏa contract.

Không nên bắt lỗi rồi âm thầm tiếp tục như thể provider đã được nạp. Hãy ghi tên service, provider type và nguyên nhân để phát hiện lỗi cấu hình.

## 16. Thiết kế runtime image cho ứng dụng có plugin

Trước khi link image, cần quyết định provider nào thuộc ứng dụng cốt lõi và provider nào là plugin tùy chọn.

### 16.1. Provider cốt lõi

Nếu ứng dụng luôn cần JSON provider, hãy đảm bảo nó được link vào image:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output runtime
```

Sau khi link, chạy kiểm thử trong chính image vừa tạo. Không chỉ chạy trên JDK đầy đủ rồi kết luận image hoạt động.

### 16.2. Provider tùy chọn

Nếu XML provider chỉ có trên một số deployment, có thể triển khai nó ngoài image và nạp bằng module layer. Ứng dụng phải xử lý trường hợp plugin không có mặt hoặc dependency không thể resolve.

### 16.3. Tách API khỏi implementation

Đặt service contract trong module API ổn định. Provider phụ thuộc API; app cũng phụ thuộc API. Tránh để API phụ thuộc implementation hoặc để nhiều provider phụ thuộc vòng nhau.

### 16.4. Xác định policy khi có nhiều provider

Không dựa vào thứ tự provider. Có thể thêm metadata vào contract:

```java
public interface Codec {
    String format();
    int priority();
    String decode(byte[] input);
}
```

Sau đó chọn rõ ràng:

```java
Codec selected = ServiceLoader.load(Codec.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(codec -> codec.format().equals("json"))
        .max(java.util.Comparator.comparingInt(Codec::priority))
        .orElseThrow();
```

Cách chọn cần được quy định trong ứng dụng. Nếu hai provider có cùng priority, hãy định nghĩa tie-breaker ổn định hoặc báo cấu hình mơ hồ.

## 17. Service provider không tạo sandbox bảo mật

Module system cung cấp encapsulation và readability, nhưng không phải sandbox để chạy code provider không đáng tin cậy.

Khi ServiceLoader khởi tạo provider, constructor hoặc provider method có thể chạy code tùy ý trong quyền của process. Vì vậy:

- Chỉ triển khai provider từ nguồn đáng tin cậy.
- Kiểm tra chữ ký, checksum hoặc provenance của plugin theo quy trình phát hành.
- Giới hạn quyền hệ điều hành/container của process.
- Không coi package không export là biện pháp cô lập mã độc.
- Không cho plugin giữ secret hoặc quyền hệ thống vượt quá nhu cầu.
- Có chính sách cập nhật và rollback provider.

Một provider được liên kết vào runtime image là code có thể được thực thi bởi ứng dụng. Service declaration chỉ mô tả khả năng cung cấp contract, không chứng minh provider an toàn.

## 18. Quy trình thực tế khi tạo custom runtime

1. **Xác định module root:** module khởi chạy ứng dụng và các module cốt lõi.
2. **Kiểm tra service API:** package contract được export và module app khai báo `uses`.
3. **Kiểm tra provider:** module provider có `requires` API và `provides` đúng service type.
4. **Kiểm tra dependency tĩnh:** dùng `jdeps`, module descriptor và module path.
5. **Khám phá provider:** dùng `jlink --suggest-providers` và xem descriptor.
6. **Chọn chiến lược:** provider cốt lõi được link bằng `--bind-services`; plugin tùy chọn được triển khai ngoài image.
7. **Giới hạn module có chủ đích:** nếu dùng `--limit-modules`, bảo đảm provider và dependency vẫn quan sát được.
8. **Tạo image:** chạy `jlink` với module path, roots, service binding và output path.
9. **Kiểm tra image:** dùng `--list-modules`, `--describe-module` và chạy service discovery.
10. **Kiểm tra trường hợp thiếu provider:** xác nhận ứng dụng fail-fast hoặc xử lý optional service đúng hợp đồng.
11. **Kiểm tra môi trường đích:** runtime image gắn với nền tảng/kiến trúc được tạo; build image riêng cho từng target phù hợp.
12. **Lưu danh sách module:** ghi lại module root, provider, module version/build và cách tái tạo image.

## 19. Bài tập tự luyện

### Bài 1 — uses hay requires?

Module app cần gọi `ServiceLoader.load(Codec.class)`. Service interface nằm trong module `com.example.codec.api`.

**Đáp án:** App cần `requires com.example.codec.api` để đọc service type và `uses com.example.codec.api.Codec` để khai báo nhu cầu service.

### Bài 2 — Provider có cần export package implementation?

Module provider khai báo `provides Codec with JsonCodec`. Package chứa `JsonCodec` không được export.

**Đáp án:** Không cần export chỉ để ServiceLoader tạo provider. Provider declaration trong module descriptor cho phép module system xử lý service implementation.

### Bài 3 — Vì sao JDK đầy đủ chạy được nhưng runtime image không chạy?

App tìm provider trên JDK đầy đủ, nhưng image chỉ có module app và service API.

**Đáp án:** Provider module không được đưa vào image. Dùng `--bind-services` nếu provider được khai báo và có thể quan sát, hoặc thêm module provider bằng `--add-modules`.

### Bài 4 — --bind-services có thêm mọi plugin không?

**Đáp án:** Không. Nó liên kết các provider module có thể tìm thấy cho service được dùng trong module graph và dependency của chúng. Plugin không có trên module path lúc link hoặc không khai báo service sẽ không tự được thêm.

### Bài 5 — --limit-modules ảnh hưởng thế nào?

**Đáp án:** Nó giới hạn module universe có thể quan sát. Nếu provider bị loại khỏi phạm vi đó, service binding không thể chọn provider.

### Bài 6 — JAR có META-INF/services có thể được jlink đóng gói trực tiếp không?

**Đáp án:** Không nên giả định. JAR chỉ dùng classpath hoặc automatic module không phải explicit module có thể link trực tiếp bằng jlink. Cần modular hóa hoặc triển khai JAR theo mô hình runtime/classpath phù hợp.

### Bài 7 — Có thể cài plugin sau khi runtime image đã tạo không?

**Đáp án:** Có thể nếu ứng dụng được thiết kế để nạp plugin bên ngoài image. Triển khai module và dependency trên module path, resolve thành ModuleLayer và gọi `ServiceLoader.load(layer, service)`. Plugin đó không nằm trong image ban đầu.

### Bài 8 — ServiceLoader có đảm bảo provider đầu tiên là tốt nhất?

**Đáp án:** Không. Không dựa vào thứ tự phát hiện làm business priority. Hãy chọn theo cấu hình hoặc metadata contract rõ ràng.

## 20. Ghi nhớ

- Service provider tách service contract khỏi implementation.
- Module tiêu thụ khai báo `uses ServiceType`; module provider khai báo `provides ServiceType with ProviderType`.
- Consumer cần `requires` module chứa service type; provider cũng cần đọc service API.
- Package implementation của provider không nhất thiết phải export.
- `ServiceLoader` phát hiện provider trong phạm vi class loader/module layer có thể quan sát.
- Provider có thể dùng public no-arg constructor hoặc provider method phù hợp.
- `jlink --bind-services` liên kết provider modules và dependency khi tạo runtime image.
- `--add-modules` chọn module root; `--limit-modules` giới hạn module universe.
- `--bind-services` không phải include-all và không tải plugin từ xa.
- jlink không biến classpath JAR hoặc automatic module thành explicit module có thể link trực tiếp.
- Reflection, service loading và plugin discovery có thể tạo dependency động mà phân tích tĩnh không tìm đủ.
- Plugin triển khai ngoài image có thể được resolve vào ModuleLayer nếu module và dependency đầy đủ.
- Service provider là code được thực thi trong process; module system không tạo sandbox bảo mật.
- Luôn kiểm tra service discovery trong chính runtime image cuối cùng.

## Tài liệu tham khảo chính thức cho Java 17

- [Java SE 17 API — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).
- [Java SE 17 API — `java.lang.module.ModuleFinder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html).
- [Java SE 17 API — `java.lang.ModuleLayer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html).
- [Java SE 17 API — `java.lang.module.Configuration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/Configuration.html).
- [Java Language Specification 17 — `7.7.4`: Service Providers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.4).
- [Java SE 17 — `jlink` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html).
- [Java SE 17 — `jdeps` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html).
- [Java SE 17 — `jar` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html).
- [JEP 261 — Module System](https://openjdk.org/jeps/261).

