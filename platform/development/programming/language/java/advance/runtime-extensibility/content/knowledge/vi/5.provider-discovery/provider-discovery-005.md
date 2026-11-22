# Ý nghĩa kiểu trả về của `ServiceLoader.Provider.type()` khi dùng phương thức `provider()`

Khi xây dựng cơ chế khám phá provider trong Java 9+ (đặc biệt là Java 17 với Java Platform Module System – JPMS), một chi tiết dễ gây nhầm lẫn là: **`ServiceLoader.Provider<S>.type()` không nhất thiết trả về lớp được khai báo trong `provides ... with ...`, và cũng không nhất thiết là lớp thực tế của đối tượng do `get()` tạo ra**.

Nếu một provider trong **explicit named module** sử dụng phương thức factory `public static provider()`, giá trị `type()` chính là **kiểu trả về được khai báo tĩnh của phương thức `provider()`**, miễn kiểu đó hợp lệ với service. Đây là điều khoản API của Java, không phải kết quả suy đoán từ tên lớp hay kiểm tra runtime object.

Bài học giải thích chính xác ba lớp/kiểu thường bị đánh đồng, cách `ServiceLoader` tạo provider, hệ quả khi lọc provider và một ví dụ Java 17 chạy được để quan sát sự khác biệt.

## 1. Ba khái niệm phải phân biệt

Giả sử ta có service `TextService` và một module khai báo:

~~~java
provides demo.api.TextService with demo.plugins.PublicFactory;
~~~

Trong lớp `PublicFactory`:

~~~java
public static TextService provider() {
    return new HiddenFormatter();
}
~~~

Ở đây có **ba khái niệm khác nhau**:

| Khái niệm | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| **Provider class** ghi trong `provides ... with ...` | `demo.plugins.PublicFactory` | Lớp được JPMS đăng ký làm nơi cung cấp service; Java tìm phương thức factory trên lớp này |
| **Declared return type** của `public static provider()` | `demo.api.TextService` | Hợp đồng kiểu tĩnh của giá trị factory trả về; **đây là giá trị `Provider.type()` báo cáo** |
| **Runtime implementation class** của instance | `demo.plugins.HiddenFormatter` | Kiểu thực tế của object trả về sau `Provider.get()`; có thể khác declared return type |

`PublicFactory` có thể **không implement `TextService`**. Ngược lại, `HiddenFormatter` phải cung cấp một đối tượng gán được cho `TextService`, nhưng lớp này không nhất thiết xuất hiện trong descriptor `provides` hoặc được export từ module.

Với provider có **provider constructor** thay cho `provider()`, kết quả lại khác: `Provider.type()` trả về lớp triển khai được đăng ký trực tiếp, ví dụ `DirectFormatter.class`.

## 2. API `ServiceLoader.Provider<S>` thực sự cam kết điều gì?

Java khai báo API ở dạng:

~~~java
public static interface ServiceLoader.Provider<S>
        extends java.util.function.Supplier<S> {
    Class<? extends S> type();
    S get();
}
~~~

- `type()` trả về một `Class<? extends S>` mô tả **provider type**. Khi dùng provider method, tài liệu JDK 17 quy định rõ đó là *return type của public static provider()*.
- `get()` cung cấp **instance** của `S`. Với provider method, `ServiceLoader` gọi factory để lấy instance; factory trả về `null` hoặc ném exception có thể dẫn đến `ServiceConfigurationError`.
- `ServiceLoader.load(ServiceType.class).stream()` trả về luồng `ServiceLoader.Provider<ServiceType>`, cho phép đọc metadata `type()` trước khi yêu cầu tạo instance bằng `get()`.
- Chữ ký generic `Class<? extends S>` chỉ ràng buộc tính tương thích kiểu với `S`, **không hứa rằng đối tượng Class đó là implementation cuối cùng** hoặc là class có thể gọi constructor.

Ví dụ, cả `TextService.class` và `DirectFormatter.class` đều có thể xuất hiện hợp lệ như `Provider<TextService>.type()`. Lớp đầu tiên là interface nên không thể khởi tạo trực tiếp bằng constructor; không có mâu thuẫn nào với khai báo `Class<? extends TextService>`.

Theo Javadoc, `type()` **không bảo đảm lớp trả về có thể truy cập từ module gọi hoặc có public no-arg constructor**. Vì vậy, *muốn lấy service instance, hãy gọi `get()`*, không thay bằng reflection như `type().getDeclaredConstructor().newInstance()`.

## 3. Hai cách tạo provider và sự khác biệt của `type()`

Trong một **explicit named module**, câu lệnh:

~~~java
provides demo.api.TextService
        with demo.plugins.PublicFactory, demo.plugins.DirectFormatter;
~~~

có thể đăng ký hai dạng provider:

| Đặc điểm | Provider constructor | Provider method |
| --- | --- | --- |
| Khai báo trên provider class | Lớp triển khai service; public no-arg constructor | Public static `provider()` không tham số, kiểu trả về gán được cho service |
| Có bắt buộc provider class implement service? | Có | **Không** |
| Cách `ServiceLoader` lấy instance | Gọi provider constructor | Gọi `provider()` |
| `Provider.type()` | Chính provider implementation class đã đăng ký | **Kiểu trả về khai báo của `provider()`** |
| `Provider.get()` | Trả về instance được xây dựng bởi constructor | Trả về instance do factory cung cấp |
| Có thể che giấu implementation cụ thể? | Thấp hơn: lớp triển khai xuất hiện trong descriptor | Cao hơn: factory có thể trả về interface, superclass hoặc instance được chọn động |

**Ví dụ quan trọng:**

~~~java
// Factory nằm trong explicit named module:
public final class PublicFactory {
    private PublicFactory() {}

    public static TextService provider() {
        return new HiddenFormatter();
    }
}
~~~

Ở tình huống này:

~~~text
Provider class (trong module-info): PublicFactory
Provider.type():                 TextService.class
Provider.get().getClass():       HiddenFormatter.class
~~~

Còn với provider constructor:

~~~java
public final class DirectFormatter implements TextService {
    public DirectFormatter() {}

    @Override
    public String process(String input) {
        return input;
    }
}
~~~

thì `Provider.type()` là `DirectFormatter.class`, và một instance bình thường được tạo bằng constructor đó có `getClass()` là `DirectFormatter.class`.

**Lưu ý điều kiện áp dụng:** provider method thuộc cơ chế service provider được khai báo bởi **explicit named module** qua `module-info.java`. Với class path và file `META-INF/services/<service binary name>`, provider phải là lớp triển khai có public no-arg constructor hợp lệ; không sử dụng cơ chế provider factory này. **Automatic module** trên module path cũng không hỗ trợ provider method, mà cần provider constructor. Đừng áp dụng quy tắc “trả về kiểu khai báo của factory” cho mọi cách đóng gói service.

## 4. Ví dụ Java 17 đầy đủ: `type()` không bằng lớp factory hoặc lớp runtime

Ta tạo ba module:

- `demo.api`: định nghĩa service `TextService`.
- `demo.plugins`: khai báo một provider bằng factory và một provider bằng constructor.
- `demo.app`: khám phá provider, in `type()`, rồi gọi `get()` và quan sát lớp thực tế.

Cấu trúc thư mục:

~~~text
src/
├── demo.api/
│   ├── module-info.java
│   └── demo/api/TextService.java
├── demo.plugins/
│   ├── module-info.java
│   └── demo/plugins/
│       ├── PublicFactory.java
│       └── DirectFormatter.java
└── demo.app/
    ├── module-info.java
    └── demo/app/Main.java
~~~

### 4.1. Module service

`src/demo.api/module-info.java`:

~~~java
module demo.api {
    exports demo.api;
}
~~~

`src/demo.api/demo/api/TextService.java`:

~~~java
package demo.api;

public interface TextService {
    String process(String input);
}
~~~

Module API export package chứa service để cả host và provider module có thể sử dụng cùng một kiểu service.

### 4.2. Module chứa provider

`src/demo.plugins/module-info.java`:

~~~java
module demo.plugins {
    requires demo.api;
    provides demo.api.TextService
            with demo.plugins.PublicFactory, demo.plugins.DirectFormatter;
}
~~~

Lưu ý `module demo.plugins` **không export** `demo.plugins`. Điều đó phù hợp với ý định đóng gói provider: client dùng service interface, không cần phụ thuộc trực tiếp vào lớp triển khai.

`src/demo.plugins/demo/plugins/PublicFactory.java`:

~~~java
package demo.plugins;

import demo.api.TextService;

public final class PublicFactory {
    private PublicFactory() {}

    public static TextService provider() {
        System.out.println("factory-called");
        return new HiddenFormatter();
    }
}

// Package-private implementation, không export.
final class HiddenFormatter implements TextService {
    @Override
    public String process(String input) {
        return "hidden:" + input.toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`PublicFactory` không triển khai `TextService`; lớp đó chỉ chứa factory hợp lệ. **Kiểu trả về được khai báo của `provider()` là `TextService`**, nên metadata `Provider.type()` sẽ là `TextService.class`. Object thực tế lại là `HiddenFormatter`.

`src/demo.plugins/demo/plugins/DirectFormatter.java`:

~~~java
package demo.plugins;

import demo.api.TextService;

public final class DirectFormatter implements TextService {
    public DirectFormatter() {}

    @Override
    public String process(String input) {
        return "direct:" + input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

`DirectFormatter` không có phương thức factory `provider()`. Đây là nhánh constructor: `ServiceLoader` khởi tạo provider trực tiếp và `type()` sẽ báo `DirectFormatter.class`.

### 4.3. Module ứng dụng tiêu thụ service

`src/demo.app/module-info.java`:

~~~java
module demo.app {
    requires demo.api;
    uses demo.api.TextService;
}
~~~

`uses` cho JPMS biết module này khám phá `TextService`; module app không cần `requires demo.plugins` vì nó chỉ biết service API.

`src/demo.app/demo/app/Main.java`:

~~~java
package demo.app;

import demo.api.TextService;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<ServiceLoader.Provider<TextService>> providers =
                ServiceLoader.load(TextService.class).stream().toList();

        for (ServiceLoader.Provider<TextService> provider : providers) {
            System.out.println("type=" + provider.type().getName());
        }
        for (ServiceLoader.Provider<TextService> provider : providers) {
            TextService instance = provider.get();
            System.out.println("instance=" + instance.getClass().getName());
            System.out.println("result=" + instance.process("Java"));
        }
    }
}
~~~

Vòng lặp đầu chỉ lấy `Provider.type()`. Vòng thứ hai mới gọi `get()`, nhờ đó dễ quan sát ranh giới giữa **khám phá metadata** và **tạo instance**. Trong tình huống mẫu chỉ có hai provider trong cùng một module, thứ tự hai provider tuân theo thứ tự khai báo `provides` của module này; **đừng suy ra thứ tự cố định giữa nhiều module**.

### 4.4. Biên dịch và chạy

Từ thư mục chứa `src/`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 --module-source-path src -d out -m demo.app,demo.plugins
java --module-path out --add-modules demo.plugins -m demo.app/demo.app.Main
~~~

`--add-modules demo.plugins` bảo đảm module provider được resolve trong lần chạy này, giúp ví dụ độc lập với cách khởi chạy và lựa chọn root modules của môi trường. Lệnh `javac` biên dịch các module được chỉ định cùng những phụ thuộc cần thiết, bao gồm `demo.api`.

Stdout:

~~~text
type=demo.api.TextService
type=demo.plugins.DirectFormatter
factory-called
instance=demo.plugins.HiddenFormatter
result=hidden:java
instance=demo.plugins.DirectFormatter
result=direct:JAVA
~~~

**Giải thích kết quả:**

1. Dòng `type=demo.api.TextService` thuộc `PublicFactory`. Dù descriptor đăng ký `PublicFactory`, `type()` vẫn lấy **return type của phương thức factory**.
2. Dòng `type=demo.plugins.DirectFormatter` thuộc nhánh constructor; ở đây provider type chính là lớp triển khai trực tiếp.
3. `factory-called` xuất hiện **sau cả hai dòng `type=`** vì code chưa gọi `get()` ở vòng lặp đầu. Trong ví dụ này, việc đọc `type()` không gọi factory.
4. `instance=demo.plugins.HiddenFormatter` chứng minh **runtime class không cần trùng với metadata `type()`**. Dù `HiddenFormatter` không public, instance vẫn sử dụng được thông qua giao diện `TextService`.
5. Hai dòng `result=` xác minh cả hai instance thực thi được API chung.

Ví dụ đã dùng hai mô hình provider song song để so sánh; ngoài ứng dụng thực tế, có thể chọn một mô hình nhất quán cho từng extension point.

## 5. Vì sao Java trả về kiểu khai báo của factory?

Một provider method là **ranh giới tạo đối tượng**. Chữ ký:

~~~java
public static TextService provider()
~~~

công bố rằng mỗi lần nhà cung cấp factory thực thi thành công, kết quả tương thích với `TextService`, nhưng không hứa sẽ luôn trả về cùng lớp runtime. Factory có thể lựa chọn implementation theo cấu hình, môi trường hoặc phiên bản mà vẫn bảo đảm chữ ký.

Nếu `Provider.type()` phải trả về kiểu runtime, hệ thống sẽ phải tạo một instance để kiểm tra `getClass()`. Điều đó phá vỡ lợi ích chính của `ServiceLoader.stream()`: **có thể xem và lọc thông tin kiểu provider mà chưa yêu cầu khởi tạo service instance**. Với factory, kiểu tĩnh của `provider()` là thông tin sẵn có và được công bố trong bytecode.

Vì vậy, phân biệt hai câu hỏi:

- `provider.type()` trả lời: “**Kiểu provider được công bố cho ServiceLoader là gì?**”
- `provider.get().getClass()` trả lời: “**Instance cụ thể tôi vừa nhận có lớp runtime nào?**”

Câu trả lời thứ hai có thể khác giữa các lần gọi `get()`. Đừng dựa vào `get()` luôn trả cùng một instance hoặc luôn trả một lớp runtime duy nhất trừ khi chính hợp đồng provider bảo đảm điều đó.

## 6. Hệ quả khi lọc provider bằng `stream()`

Một ví dụ quen thuộc:

~~~java
ServiceLoader<TextService> loader = ServiceLoader.load(TextService.class);

List<ServiceLoader.Provider<TextService>> selected = loader.stream()
        .filter(p -> p.type().getSimpleName().contains("Formatter"))
        .toList();
~~~

Cách này lọc theo **tên của declared provider type**, không phải tên factory và cũng không chắc là tên lớp runtime.

Trong ví dụ của bài:

- Provider dùng `PublicFactory.provider(): TextService` báo `TextService.class`: điều kiện có thể loại bỏ nó dù runtime class là `HiddenFormatter`.
- Provider constructor báo `DirectFormatter.class`: điều kiện phù hợp.
- Nếu hai factory khác nhau đều có return type `TextService`, `type()` có thể **giống nhau**, khiến việc chọn provider theo loại implementation không đủ thông tin.

Với điều kiện kiểu:

~~~java
boolean matches = SomeSubtype.class.isAssignableFrom(provider.type());
~~~

phép kiểm tra **đúng về quan hệ kế thừa của kiểu khai báo**, nhưng có thể cho **false negative** nếu `provider()` khai báo trả về một supertype tổng quát trong khi implementation runtime thực tế thuộc `SomeSubtype`. Do đó phải xác định từ đầu có cần lọc theo **hợp đồng công khai**, hay cần metadata mô tả **tính năng cụ thể**.

### Chọn chiến lược lọc phù hợp

| Nhu cầu | Cách dùng phù hợp |
| --- | --- |
| Chọn provider theo declared type/cấu trúc kế thừa được công bố | Dùng `Provider.type()`; hiểu giới hạn với provider method trả về interface |
| Chọn theo annotation đặt trên **declared return type** | `provider.type().isAnnotationPresent(...)` phù hợp nếu annotation thực sự ở kiểu đó |
| Đọc annotation đặt trên **factory class** | `Provider.type()` không bảo đảm trả về factory class; cần metadata đăng ký riêng nếu cần |
| Phân loại theo **implementation runtime** | Phải có instance (gọi `get()` rồi kiểm tra `instance.getClass()` hoặc capability của instance), cân nhắc chi phí/side effect |
| Chọn theo id, version, priority, capability, vùng hỗ trợ | Thiết kế descriptor/annotation/metadata của extension point; đừng suy đoán từ `Class.getName()` |
| Chỉ cần thực thi service | Gọi `Provider.get()` rồi làm việc qua interface `S` |

Một hướng thiết kế tốt là yêu cầu provider công bố metadata rõ ràng (ví dụ `id()`, `capabilities()`) qua API service hoặc descriptor độc lập. Nếu metadata phải đọc **trước khi khởi tạo instance**, nên đặt ở nơi tra cứu được mà không cần gọi factory; tránh lệ thuộc vào tên implementation mà factory cố ý che giấu.

## 7. Ba nhầm lẫn về reflection, annotation và quyền truy cập

**Nhầm lẫn 1: `type()` trả về lớp được đăng ký trong `provides`.** Với constructor provider, thường trùng. Với provider method, `provides ... with PublicFactory` nhưng `type()` là `TextService.class` khi `provider()` khai báo trả `TextService`.

**Nhầm lẫn 2: có `Class<? extends S>` thì có thể tự tạo instance.** `type()` có thể trả về interface/abstract class, lớp không export hoặc lớp không có public no-arg constructor. Tự dùng `newInstance()` hoặc reflection không tương đương với gọi `ServiceLoader.Provider.get()`, vì có thể bỏ qua cả factory, điều kiện cấu hình và cơ chế khởi tạo hợp lệ.

**Nhầm lẫn 3: annotation trên factory hoặc runtime class đều thấy qua `type()`.** Khi factory trả về interface, `type()` trỏ đến interface. Annotation chỉ đặt trên `PublicFactory` hoặc `HiddenFormatter` không tự xuất hiện trên `TextService.class`. Với annotation `@Inherited`, cũng không thể suy rằng annotation sẽ lan từ lớp khác sang interface hay từ factory sang lớp kết quả; các đối tượng `Class` này khác nhau.

Thậm chí `provider.type().getName()` trùng với một tên lớp đã biết **không đủ** để kết luận hai kiểu có cùng định danh runtime nếu chúng đến từ class loader hoặc module layer khác nhau. Nếu cần so sánh kiểu Java thực sự, dùng đối tượng `Class`/quan hệ kiểu sau khi đã xác định đúng môi trường nạp lớp.

## 8. Điều kiện hợp lệ và lỗi liên quan

Với **explicit named module** dùng `provider()`, cần bảo đảm:

1. Module khai báo `provides ServiceType with ProviderClass;`, trong đó provider class được định nghĩa trong chính module đó.
2. Provider class có phương thức `public static provider()` không tham số, với **kiểu trả về gán được cho service**; chỉ có một phương thức như vậy được chọn hợp lệ theo quy định.
3. Factory cung cấp giá trị không `null` và tương thích với kiểu trả về; không dựa vào public no-arg constructor của factory.
4. Module tiêu thụ service khai báo `uses ServiceType;` và đọc service API thông qua `requires` tương ứng.
5. Module provider được resolve ở runtime, thông qua service binding/module configuration hoặc được chỉ định phù hợp, ví dụ `--add-modules` trong mẫu.
6. Khi muốn dùng `Provider.type()` để phân loại, hãy ghi rõ chính sách return type của provider factory: trả service interface, một subtype công bố hay interface riêng cho nhóm capability.

Các trường hợp sai cấu hình có thể khiến `ServiceLoader` ném **`ServiceConfigurationError`** khi khám phá hoặc tạo provider, tùy vị trí lỗi. Ví dụ: provider method có return type không tương thích với service, có nhiều provider method công khai không tham số cùng tên, provider không nạp được, hoặc factory trả `null`/ném lỗi. Lỗi có thể xảy ra khi xử lý `stream()`, **không chỉ lúc gọi `get()`**.

Riêng explicit named module còn có kiểm tra cú pháp/ngữ nghĩa của `provides` tại thời điểm biên dịch; không nên coi mọi cấu hình sai đều chỉ được phát hiện khi chạy.

Nếu chuyển `PublicFactory` sang class path rồi liệt kê nó trong `META-INF/services/demo.api.TextService`, cách làm sẽ không tương đương: class-path provider được trông đợi là subtype trực tiếp có constructor phù hợp. Việc có một phương thức tĩnh tên `provider` không tự kích hoạt cơ chế factory của JPMS.

## 9. Checklist kiểm thử và xử lý sự cố

Khi gặp hiện tượng `Provider.type()` “khác lớp mong đợi”, hãy kiểm tra theo thứ tự:

1. Module đang là **explicit named module**, automatic module hay class path? Cơ chế provider method chỉ áp dụng nơi được hỗ trợ.
2. Trong `module-info.java`, tên ở `provides ... with ...` là **provider class** nào?
3. Provider class có `public static provider()` không tham số không? **Kiểu trả về khai báo chính xác** là interface, abstract class hay implementation cụ thể?
4. `Provider.type().getName()` là gì **trước khi gọi `get()`**? Đừng thêm giả định rằng type là factory class.
5. `Provider.get().getClass().getName()` là gì **sau khi gọi `get()`**? Kết quả này mô tả instance cụ thể, không sửa metadata do `type()` báo.
6. Có đang dùng `type().isAnnotationPresent(...)` hoặc `type().getSimpleName()` để lọc và vô tình bỏ qua factory có return type rộng hơn không?
7. Nếu gặp `ServiceConfigurationError`, xác minh descriptor, phương thức factory, return type, quyền nạp module và lỗi phát sinh từ factory. Không dùng reflection tự khởi tạo để “né” lỗi của hợp đồng service.

Khi viết kiểm thử đơn vị/tích hợp cho extension discovery, nên có ít nhất hai provider: **một provider constructor trả về implementation class** và **một provider method khai báo trả về service interface nhưng tạo implementation khác**. Khẳng định đồng thời giá trị `type()`, kiểu `get()`, và việc factory chỉ được yêu cầu khi gọi `get()` trong kịch bản kiểm thử. Kiểm thử thêm nhánh factory trả `null` hoặc lỗi nếu hệ thống cần xử lý provider không hợp lệ.

## 10. Kết luận áp dụng

Đối với phương thức provider trong explicit named module, quy tắc chính xác là:

~~~text
provides S with FactoryClass
               |
               +-- public static DeclaredReturnType provider()
                                      |
ServiceLoader.Provider<S>.type() -----+--> DeclaredReturnType.class
ServiceLoader.Provider<S>.get()  --------> instance được provider() trả về
                                                 |
                                                 +--> instance.getClass()
                                                       (runtime implementation)
~~~

**`Provider.type()` mô tả kiểu trả về được công bố của provider factory; `Provider.get()` mới cấp object thực tế**. Vì vậy, thiết kế bộ lọc hoặc cơ chế lựa chọn plugin phải dựa vào metadata đáp ứng mục đích thay vì giả định `type()` luôn là factory class hoặc implementation runtime.

### Tài liệu tham khảo chính thức

- [JDK 17 – `ServiceLoader.Provider<S>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): mô tả `type()`, `get()` và trường hợp provider factory.
- [JDK 17 – `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider constructor, provider method, named/automatic module, class path, stream và lỗi cấu hình.
- [Dev.java – Decoupling Modules with Services](https://dev.java/learn/modules/services/): mô hình `uses`/`provides` và đăng ký service trong JPMS.
