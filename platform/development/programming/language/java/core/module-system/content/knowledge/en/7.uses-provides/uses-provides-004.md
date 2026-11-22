# ServiceLoader tìm provider theo module graph

Trong Java, một ứng dụng có thể cần sử dụng một dịch vụ mà không muốn phụ thuộc trực tiếp vào lớp triển khai cụ thể. Ví dụ, ứng dụng cần mã hóa dữ liệu nhưng có thể chọn giữa nhiều bộ mã hóa; một hệ thống thanh toán có thể thay đổi cổng thanh toán; hoặc ứng dụng cần tìm các plugin được cài đặt ở runtime.

Java cung cấp `ServiceLoader` để tìm và khởi tạo các implementation của một service. Khi dùng Java Platform Module System (JPMS), cơ chế này kết hợp với hai directive trong module descriptor:

- `uses` khai báo module tiêu thụ cần một service.
- `provides ... with ...` khai báo module cung cấp implementation của service.

Các directive này giúp module system biết quan hệ dịch vụ. Quá trình resolution có thể dùng thông tin đó để đưa provider module vào module graph. Sau khi các module đã được định nghĩa trong một `ModuleLayer`, `ServiceLoader` mới tìm và khởi tạo provider trong phạm vi loader hoặc layer được chỉ định.

## 1. Service, provider và ServiceLoader

Một **service** là một kiểu được ứng dụng biết trước, thường là interface hoặc abstract class. Service định nghĩa hợp đồng mà các implementation phải tuân theo.

Một **provider** là implementation cụ thể của service. Một service có thể có không, một hoặc nhiều provider. Ứng dụng chỉ cần biết service interface; nó không nhất thiết phải biết provider được đóng gói trong JAR nào hoặc nằm trong module nào.

Ví dụ, service mô tả bộ chuyển đổi định dạng:

```java
package com.example.codec.api;

public interface Codec {
    String format();
    byte[] encode(byte[] input);
}
```

Các provider có thể là bộ mã hóa JSON, XML hoặc định dạng nhị phân. Mỗi provider triển khai cùng hợp đồng nhưng có cách xử lý riêng.

`ServiceLoader` là API trong `java.util` dùng để tìm provider có sẵn trong môi trường runtime:

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.format());
}
```

Ứng dụng duyệt các provider mà loader tìm được. Nó có thể chọn provider dựa trên đặc tính của provider, cấu hình ứng dụng hoặc yêu cầu nghiệp vụ. Không nên giả định rằng luôn có ít nhất một provider; ứng dụng cần xử lý trường hợp không tìm thấy provider phù hợp.

## 2. Hai phía của service trong JPMS

Một mô hình service modular có ba thành phần:

1. Module chứa service interface.
2. Module tiêu thụ service.
3. Một hoặc nhiều module cung cấp provider.

Ví dụ cấu trúc:

```text
codec-api/
└── module com.example.codec.api
    └── com.example.codec.api.Codec

application/
└── module com.example.application
    └── com.example.application.Main

codec-json/
└── module com.example.codec.json
    └── com.example.codec.json.JsonCodec
```

Service interface nên nằm trong package mà module tiêu thụ có thể truy cập. Module provider phụ thuộc vào module chứa service để triển khai đúng kiểu interface.

### 2.1. Module service công khai interface

Descriptor của module API:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

Directive `exports` cho phép module khác tham chiếu kiểu `Codec` theo quy tắc truy cập Java thông thường.

### 2.2. Module tiêu thụ khai báo uses

Descriptor của ứng dụng:

```java
module com.example.application {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

Hai directive có vai trò khác nhau:

- `requires com.example.codec.api` cho phép module application đọc module chứa service interface.
- `uses com.example.codec.api.Codec` khai báo rằng application cần tìm provider cho service này.

Một module named dùng `ServiceLoader` phải khai báo `uses` cho service tương ứng. Nếu thiếu directive này, việc lấy hoặc sử dụng service loader từ module tường minh có thể thất bại với `ServiceConfigurationError`.

### 2.3. Module provider khai báo provides

Descriptor của provider JSON:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Directive `provides` xác định service được cung cấp và lớp provider tương ứng.

Lớp triển khai:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {
    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(byte[] input) {
        // Minh họa: phần mã hóa thực tế phụ thuộc định dạng.
        return input.clone();
    }
}
```

Module provider cần đọc module chứa interface để biên dịch implementation. Package chứa lớp provider không cần export chỉ để `ServiceLoader` tìm provider đã khai báo trong descriptor. Thực tế, tài liệu Java khuyến nghị module provider không export package triển khai nếu không có API khác cần công khai.

## 3. Module graph liên quan gì đến việc tìm provider?

Module graph là đồ thị biểu diễn các module đã được phân giải và quan hệ đọc giữa chúng. Các directive `requires` tạo dependency thông thường. Với service, JPMS có thêm thông tin từ `uses` và `provides` để thực hiện **service binding** trong quá trình resolution.

Cần tách ba việc:

1. **ModuleFinder tìm module có thể quan sát:** ví dụ các modular JAR nằm trên module path.
2. **Resolution xây dựng configuration:** từ các root module, hệ thống theo các directive `requires` để xác định module cần thiết và khả năng đọc.
3. **Service binding có thể bổ sung provider module:** nếu các module đã phân giải khai báo `uses`, hệ thống tìm module có `provides` service tương ứng, đưa provider module và dependency của nó vào configuration, rồi tiếp tục kiểm tra các service dependency mới phát sinh.

Vì vậy, `provides` tự nó không phải lệnh tải và khởi tạo provider. Nó ghi metadata cho biết module nào có thể cung cấp implementation. Provider phải được tìm thấy và hiện diện trong module layer hoặc phạm vi class loader mà `ServiceLoader` sử dụng.

### 3.1. Resolution thông thường và resolution có service binding

API `java.lang.module.Configuration` có hai phương thức thường được nhắc đến:

- `resolve(...)` phân giải các module theo quan hệ dependency `requires`.
- `resolveAndBind(...)` thực hiện resolution kèm service binding.

`resolveAndBind` trước tiên phân giải các root module như resolution thông thường. Sau đó, nó xem xét service dependency của các module đã phân giải và các parent configuration. Những module có thể quan sát và cung cấp implementation cho service được yêu cầu sẽ được bổ sung vào module graph. Quá trình lặp lại nếu provider module mới lại sử dụng service khác.

Mô tả khái quát:

```text
Root modules
     |
     v
Resolve requires dependencies
     |
     v
Read uses directives
     |
     v
Find modules with matching provides
     |
     v
Add provider modules and their dependencies
     |
     v
Check new service dependencies
     |
     v
Final Configuration / module graph
```

Đây là cơ sở để provider module có thể được đưa vào cấu hình runtime mà module tiêu thụ không cần khai báo `requires` trực tiếp tới từng provider.

Nếu chỉ dùng resolution thông thường, một module không được đưa vào configuration chỉ vì nó có `provides`. Khi đó, `ServiceLoader` không thể tìm provider từ module chưa được định nghĩa trong layer mà loader đang tìm kiếm.

## 4. Vì sao ứng dụng không nên requires trực tiếp provider?

Một lợi ích quan trọng của service binding là tách module tiêu thụ khỏi module triển khai.

Giả sử application khai báo:

```java
module com.example.application {
    requires com.example.codec.api;
    uses com.example.codec.api.Codec;
}
```

Nếu application còn khai báo:

```java
requires com.example.codec.json;
```

thì application đã phụ thuộc trực tiếp vào một provider cụ thể. Khi thay JSON bằng XML hoặc cài thêm provider khác, module tiêu thụ có thể phải thay đổi descriptor và build configuration.

Thiết kế service thường khuyến nghị module tiêu thụ:

- Yêu cầu module API chứa service interface.
- Khai báo `uses` cho service.
- Không yêu cầu trực tiếp các module chỉ đóng vai trò provider, nếu mục tiêu là để service binding tìm provider.

Cách này giữ dependency chính ở abstraction. Provider có thể được thêm, thay thế hoặc lựa chọn theo môi trường triển khai mà không cần biến từng implementation thành dependency trực tiếp của application.

Điều đó không có nghĩa provider tự xuất hiện từ bất kỳ nơi nào. Provider module vẫn phải có thể được tìm thấy, được đưa vào configuration/layer phù hợp và đáp ứng đúng service contract.

## 5. ServiceLoader tìm provider trong ModuleLayer

`ModuleLayer` là lớp runtime chứa một tập hợp module đã được định nghĩa từ một `Configuration`. Một ứng dụng có thể có boot layer và tạo thêm layer con để tải plugin hoặc nhóm module độc lập.

Có hai cách sử dụng `ServiceLoader` đáng chú ý:

**Dùng class loader hiện tại**

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(Codec.class);
```

Overload này dùng context class loader của thread hiện tại. Việc tìm provider bao gồm các named module liên quan tới class loader/module layer và provider trong unnamed module thông qua file cấu hình service trên classpath.

Nếu caller nằm trong explicit named module, descriptor của caller phải có `uses` cho service.

**Chỉ định ModuleLayer**

```java
ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);
```

Overload này tìm provider trong module layer được truyền vào và các parent layer của nó. Nó không tìm provider trong unnamed module.

Cách thứ hai hữu ích khi ứng dụng tự tạo plugin layer và muốn giới hạn việc tìm provider trong đúng layer cùng hệ thống cha của layer đó.

### 5.1. Boot layer và layer con

Khi JVM khởi chạy ứng dụng modular, các module nền tảng và module ứng dụng đã được định nghĩa trong các layer tương ứng; boot layer là layer khởi đầu quan trọng của ứng dụng.

Một hệ thống plugin có thể tạo layer mới từ configuration được phân giải từ thư mục plugin:

```java
Configuration configuration =
        ModuleLayer.boot()
                .configuration()
                .resolveAndBind(
                        ModuleFinder.of(),
                        pluginFinder,
                        Set.of()
                );

ModuleLayer pluginLayer =
        ModuleLayer.boot()
                .defineModulesWithOneLoader(
                        configuration,
                        ClassLoader.getSystemClassLoader()
                );

ServiceLoader<Codec> codecs =
        ServiceLoader.load(pluginLayer, Codec.class);
```

Đoạn mã minh họa ý tưởng: dùng configuration có service binding, định nghĩa module thành layer con của boot layer, rồi yêu cầu `ServiceLoader` tìm service trong layer đó và các parent. Trong ứng dụng thực tế, `pluginFinder` cần được tạo từ vị trí chứa các module plugin; các module service và provider cũng phải có dependency hợp lệ.

Một layer có thể dùng một class loader chung cho tất cả module hoặc một class loader riêng cho từng module. `ServiceLoader.load(layer, service)` vẫn tìm provider trong các module của layer theo API layer, không đòi hỏi tất cả module phải dùng cùng một class loader.

## 6. Vòng đời tìm và khởi tạo provider

Tạo `ServiceLoader` không có nghĩa tất cả provider lập tức được khởi tạo. Việc tìm và khởi tạo thường diễn ra lười, khi ứng dụng duyệt kết quả.

### 6.1. Duyệt bằng iterator

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

for (Codec codec : loader) {
    System.out.println(codec.format());
}
```

Vòng lặp gọi iterator của loader. Provider được tìm và khởi tạo khi cần lấy phần tử tiếp theo. Nếu không có provider, vòng lặp kết thúc mà không có phần tử nào.

### 6.2. Dùng stream để xem provider trước khi khởi tạo

```java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

loader.stream()
        .filter(provider -> provider.type().getSimpleName()
                .contains("Json"))
        .map(ServiceLoader.Provider::get)
        .forEach(codec -> System.out.println(codec.format()));
```

`stream()` cung cấp các đối tượng `ServiceLoader.Provider`. Ta có thể xem kiểu provider qua `type()` và lọc trước khi gọi `get()` để lấy instance.

Điều này hữu ích khi ứng dụng muốn kiểm tra metadata hoặc đặc tính của provider trước khi khởi tạo implementation. Tuy vậy, việc xử lý stream cũng có thể kích hoạt quá trình tìm và tải provider khi pipeline được thực thi.

### 6.3. Cache và reload

Một `ServiceLoader` giữ cache các provider đã được tải. Những lần duyệt tiếp theo có thể trả lại provider đã cache trước khi tìm các provider còn lại.

Nếu môi trường cho phép cài đặt provider mới trong lúc JVM đang chạy, có thể gọi:

```java
loader.reload();
```

Lệnh này xóa cache để các lần duyệt sau tìm lại provider. Các iterator hoặc stream cũ nên được bỏ đi sau khi reload. Một instance `ServiceLoader` không an toàn để nhiều thread sử dụng đồng thời; nếu cần truy cập song song, ứng dụng phải tự quản lý cách chia sẻ và đồng bộ phù hợp.

## 7. Provider module cần tuân thủ điều kiện nào?

Với provider được khai báo trong named module:

- Directive `provides` phải chỉ rõ service type và provider type.
- Provider type phải là kiểu hợp lệ theo quy tắc ServiceLoader và phải public, không phải inner class.
- Nếu không có provider method, provider cần có public constructor không tham số và phải triển khai hoặc kế thừa service type.
- Nếu có provider method, method phải là `public static`, tên `provider`, không có tham số và trả về kiểu tương thích với service. Khi đó chính provider class không nhất thiết phải triển khai service interface.
- Module provider cần đọc module chứa service type để tham chiếu service.
- Package triển khai provider không cần export chỉ để ServiceLoader phát hiện provider trong descriptor.

Ví dụ provider thông qua constructor:

```java
public final class JsonCodec implements Codec {
    public JsonCodec() {
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public byte[] encode(byte[] input) {
        return input.clone();
    }
}
```

Ví dụ provider thông qua provider method:

```java
public final class JsonCodecFactory {
    private JsonCodecFactory() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
```

Descriptor có thể khai báo factory class:

```java
provides com.example.codec.api.Codec
    with com.example.codec.json.JsonCodecFactory;
```

Provider method cho phép module kiểm soát cách tạo instance, chẳng hạn trả về implementation được cấu hình hoặc được tạo qua factory. Nếu không có provider method, ServiceLoader khởi tạo provider class thông qua public no-argument constructor.

## 8. Provider trên classpath và provider trong named module

ServiceLoader hỗ trợ cả provider theo cơ chế truyền thống trên classpath và provider được khai báo trong module descriptor.

| Cách triển khai | Nơi khai báo provider | Cách tìm |
|---|---|---|
| Provider trong named module | `provides Service with Provider` trong `module-info.java` | Theo module/class loader hoặc ModuleLayer |
| Provider trong unnamed module trên classpath | `META-INF/services/<tên đầy đủ của service>` | Đọc file cấu hình service qua class loader |
| Provider trong automatic module | File cấu hình service trong JAR theo quy tắc automatic module | Được tìm như named module trên module path; provider cần provider constructor |

Với classpath, file cấu hình có tên là tên nhị phân đầy đủ của service, nằm trong thư mục `META-INF/services`. File chứa tên đầy đủ của từng provider, mỗi tên trên một dòng.

Ví dụ:

```text
META-INF/services/com.example.codec.api.Codec
```

Nội dung:

```text
com.example.codec.json.JsonCodec
```

Khi JAR được dùng trên module path dưới dạng automatic module, ServiceLoader hỗ trợ provider được khai báo theo file cấu hình này, nhưng không hỗ trợ provider method trong automatic module. Provider cần có constructor phù hợp.

Với explicit named module, nên dùng directive `provides` thay cho file cấu hình truyền thống. Nếu cùng một provider được khai báo cả trong descriptor và file cấu hình, provider được triển khai trong named module sẽ không bị tính lặp từ file cấu hình.

## 9. Thứ tự provider và việc lựa chọn implementation

ServiceLoader không phải một cơ chế tự động chọn implementation tốt nhất. Nó tìm các provider có thể quan sát được; ứng dụng quyết định dùng provider nào.

Không nên dựa vào thứ tự giữa các module trong cùng một layer, vì thứ tự đó không được đảm bảo. Nếu một module khai báo nhiều provider cho cùng service, thứ tự provider trong descriptor được giữ khi tìm các provider của module đó, nhưng không thể suy ra một thứ tự tổng thể ổn định giữa mọi module.

Ứng dụng nên lựa chọn rõ ràng theo đặc tính nghiệp vụ:

```java
Optional<Codec> jsonCodec =
        ServiceLoader.load(Codec.class)
                .stream()
                .filter(p -> p.type().getSimpleName().contains("Json"))
                .map(ServiceLoader.Provider::get)
                .findFirst();
```

Ví dụ trên minh họa lọc theo kiểu provider. Trong hệ thống thực tế, nên dùng metadata hoặc phương thức của service để đánh giá capability, version, thuật toán hỗ trợ hoặc chính sách cấu hình, thay vì phụ thuộc vào tên lớp.

Cũng cần xử lý trường hợp không có provider. Có thể dùng implementation mặc định, báo lỗi cấu hình hoặc vô hiệu hóa chức năng tùy theo yêu cầu ứng dụng.

## 10. Lỗi thường gặp khi tìm provider

### Thiếu uses

Nếu module tiêu thụ là explicit named module nhưng descriptor không khai báo `uses` cho service, ServiceLoader có thể ném `ServiceConfigurationError`. Hãy kiểm tra module gọi `ServiceLoader.load` và bổ sung đúng service type vào descriptor.

### Provider module không được phân giải

Một module có `provides` nhưng không có trong module layer mà loader đang tìm kiếm thì provider sẽ không xuất hiện trong kết quả. Hãy kiểm tra module finder, module path, root modules và cách configuration được tạo. Với plugin hoặc service binding, cân nhắc `resolveAndBind`.

### Sai tên module hoặc service type

Tên service trong `uses` và `provides` phải trỏ tới cùng service type. Provider phải tương thích với service đó. Kiểm tra package, tên đầy đủ và dependency của module provider.

### Package service không được export

Module tiêu thụ cần tham chiếu service interface. Module sở hữu interface phải export package chứa service cho module tiêu thụ, và module tiêu thụ phải khai báo `requires` tới module đó.

### Provider không thể khởi tạo

Provider class có thể thiếu public no-argument constructor, không tương thích với service hoặc constructor/provider method ném exception. Kiểm tra lỗi `ServiceConfigurationError` và nguyên nhân gốc trong quá trình khởi tạo.

### Tìm sai ModuleLayer

`ServiceLoader.load(layer, service)` chỉ tìm provider trong layer được chỉ định và các parent layer; nó không tìm provider trong unnamed module. Nếu provider nằm ở layer khác, cần truyền đúng layer hoặc dùng overload phù hợp với class loader.

## 11. Quy trình thiết kế và kiểm tra service binding

Khi xây dựng một hệ thống plugin bằng JPMS, có thể tiến hành theo thứ tự:

1. **Định nghĩa service interface:** đặt interface hoặc abstract class trong module API ổn định.
2. **Export package service:** cho phép module tiêu thụ và provider tham chiếu service type.
3. **Khai báo uses:** module tiêu thụ khai báo đúng service type trong descriptor.
4. **Khai báo provides:** mỗi provider module khai báo service và provider implementation.
5. **Kiểm tra khả năng quan sát:** bảo đảm provider module có thể được tìm từ module finder hoặc module path phù hợp.
6. **Phân giải có service binding:** dùng cơ chế resolution có binding khi cần tự động đưa provider module vào configuration.
7. **Định nghĩa ModuleLayer:** tạo runtime layer từ configuration đã phân giải.
8. **Tạo ServiceLoader:** dùng class loader hoặc layer đúng với cách ứng dụng triển khai plugin.
9. **Duyệt và lựa chọn:** xử lý trường hợp nhiều provider hoặc không có provider.
10. **Xử lý lỗi:** quan sát `ServiceConfigurationError`, kiểm tra provider constructor/provider method và dependency runtime.

Có thể kiểm tra descriptor của từng JAR:

```shell
jar --describe-module --file libs/codec-api.jar
jar --describe-module --file libs/codec-json.jar
jar --describe-module --file libs/application.jar
```

Đối chiếu các directive `uses`, `provides`, `requires` và `exports` với cấu hình build. Một provider được khai báo đúng vẫn cần có mặt trong phạm vi module graph hoặc loader được dùng để tìm nó.

## Kết luận

ServiceLoader tìm implementation của một service dựa trên các provider có thể quan sát được trong môi trường runtime. Với JPMS, module tiêu thụ khai báo `uses`, module cung cấp khai báo `provides ... with ...`, và service binding trong quá trình resolution có thể đưa provider module cùng dependency của nó vào module graph.

Sau khi module được định nghĩa trong ModuleLayer, `ServiceLoader.load(layer, service)` tìm provider trong layer đó và các parent layer. Việc tạo loader và duyệt provider diễn ra lười; ứng dụng cần chủ động chọn implementation và xử lý trường hợp không có provider hoặc provider không thể khởi tạo.

Điểm quan trọng là `provides` mô tả nơi có implementation, module graph xác định module nào đã được phân giải trong runtime, còn `ServiceLoader` thực hiện việc tìm và khởi tạo provider trong phạm vi loader/layer phù hợp. Nhờ tách service contract khỏi implementation, ứng dụng có thể mở rộng bằng plugin mà không phải phụ thuộc trực tiếp vào từng provider cụ thể.