# Dùng stream, Provider.type và Provider.get để tách xem kiểu khỏi tạo đối tượng

## 1. Vấn đề: khám phá provider mà chưa muốn khởi tạo tất cả

Trong một ứng dụng Java có điểm mở rộng, **service** là hợp đồng mà mã chủ (host) biết trước, thường là interface hoặc abstract class. **Service provider** là triển khai được đăng ký và có thể được tìm thấy khi ứng dụng chạy. Chẳng hạn một ứng dụng xử lý văn bản có hợp đồng TextTransformer, còn các provider bổ sung cách viết hoa, đảo chuỗi hoặc chuẩn hóa.

Đôi khi host chỉ muốn **xem provider nào có khả năng đáp ứng yêu cầu**, rồi mới tạo đối tượng của provider phù hợp. Việc khởi tạo provider có thể kéo theo kiểm tra cấu hình, mở kết nối, cấp phát tài nguyên, đăng ký listener hoặc lỗi do phụ thuộc thiếu. Nếu dùng cách duyệt tạo instance ngay, host có thể phải khởi tạo cả những provider cuối cùng không được chọn.

Từ **Java 9**, ServiceLoader có phương thức **stream()** trả về các mô tả provider, cho phép **xem kiểu trước, tạo instance sau**:

~~~java
ServiceLoader<TextTransformer> loader =
        ServiceLoader.load(TextTransformer.class);

ServiceLoader.Provider<TextTransformer> selected = loader.stream()
        .filter(p -> p.type().isAnnotationPresent(Preferred.class))
        .findFirst()
        .orElseThrow();

TextTransformer transformer = selected.get();
~~~

Đây là **mảnh mã minh họa**, giả định TextTransformer và annotation Preferred đã được định nghĩa. Ý nghĩa cốt lõi là:

1. **stream()** cho một Stream các **ServiceLoader.Provider<TextTransformer>**, không phải Stream<TextTransformer>.
2. **p.type()** cho thông tin kiểu **Class<? extends TextTransformer>** để phân loại, lọc, đọc annotation hoặc lấy tên class mà chưa gọi constructor/provider factory để lấy instance.
3. **p.get()** thực sự yêu cầu một instance TextTransformer từ mô tả provider đã chọn.

Cách tách này còn gọi là **discovery/selection trước, instantiation sau**. Nó hữu ích khi các provider có metadata ở cấp class (ví dụ annotation) và host có thể quyết định bằng metadata ấy.

## 2. Ba API và kiểu dữ liệu cần nhớ

| API | Kết quả | Có tạo service instance ngay không? | Dùng để |
|---|---|---|---|
| **ServiceLoader.load(ServiceType.class)** | ServiceLoader<ServiceType> | Không phải thao tác tạo tất cả instance | Tạo bộ nạp theo service và class loader/module context |
| **loader.stream()** | Stream<ServiceLoader.Provider<ServiceType>> | Không | Duyệt mô tả provider theo nhu cầu khi chạy terminal operation |
| **provider.type()** | Class<? extends ServiceType> | Không gọi provider constructor/provider method để tạo service instance | Xem kiểu, tên, annotation, metadata kiểu |
| **provider.get()** | ServiceType | Có yêu cầu tạo/lấy một instance | Bắt đầu sử dụng provider |
| **loader.iterator()** hoặc vòng **for-each** | Các ServiceType | Có, khi tiến tới phần tử | Duyệt trực tiếp các instance provider |

Provider ở đây là **java.util.ServiceLoader.Provider<S>**, một nested interface kế thừa **Supplier<S>** và bổ sung **type()**. Không nhầm nó với interface do chính ứng dụng đặt tên *PluginProvider* hay *Factory*: chúng có thể phục vụ cùng mục đích thiết kế, nhưng là những abstraction khác nhau.

Sơ đồ luồng xử lý:

~~~text
ServiceLoader.load(TextTransformer.class)
               |
               v
         loader.stream()
               |
               v
       Stream<Provider<TextTransformer>>
               |
        filter(p.type())
               |
               v
        Provider được chọn
               |
             p.get()
               |
               v
       TextTransformer instance
               |
          transform(text)
~~~

**Phân biệt hai kiểu duyệt:**

~~~java
// Mảnh minh họa: thao tác trên instance, mỗi phần tử được tạo khi duyệt đến.
for (TextTransformer service : ServiceLoader.load(TextTransformer.class)) {
    // Đã có instance để gọi nghiệp vụ.
}

// Mảnh minh họa: thao tác trên mô tả provider trước.
ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> p.type().getSimpleName().contains("Upper"))
        .map(ServiceLoader.Provider::get)
        .forEach(service -> System.out.println(service.transform("java")));
~~~

Trong pipeline thứ hai, thao tác **map(Provider::get)** đứng **sau filter**, nên chỉ các provider đi qua bộ lọc mới bị yêu cầu tạo instance. Lưu ý: ngay cả khi chưa tạo instance, việc khám phá, nạp lớp, đọc metadata và liên kết lớp vẫn có thể phát sinh chi phí hoặc lỗi; “lazy” không đồng nghĩa với “không làm bất kỳ công việc nào”.

## 3. Tính lazy chính xác là gì?

**ServiceLoader** khám phá provider **theo nhu cầu**. Việc gọi **stream()** chỉ tạo stream; khi một **terminal operation** như **findFirst()**, **toList()**, **forEach()** hay **collect()** chạy, ServiceLoader mới tiến hành khám phá/nạp provider mà pipeline cần.

- **filter(p -> ...)** là intermediate operation: riêng câu lệnh filter chưa xử lý provider nào.
- **findFirst()** có thể dừng sau khi gặp provider phù hợp, nên thường không cần duyệt hết mọi provider.
- **toList()** duyệt toàn bộ phần tử đầu vào; nó lưu các đối tượng Provider trong danh sách, **không tự gọi get()**.
- **sorted(...)** thường phải quan sát mọi provider để sắp xếp, có thể làm mất lợi thế dừng sớm của findFirst; tuy vậy, sắp xếp theo **p.type()** vẫn không tự tạo service instance.
- Chỉ khi **get()** được gọi thì ServiceLoader mới yêu cầu đối tượng service (qua constructor hoặc factory method tương ứng).

Ví dụ:

~~~java
// Mảnh minh họa: đọc tên class của mọi provider, chưa gọi get().
List<String> providerNames = ServiceLoader.load(TextTransformer.class)
        .stream()
        .map(p -> p.type().getName())
        .sorted()
        .toList();

// Mảnh minh họa: chỉ tạo/lấy instance của provider được chọn.
TextTransformer chosen = ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> p.type().getSimpleName().equals("UppercaseTransformer"))
        .findFirst()
        .orElseThrow()
        .get();
~~~

**Quan trọng:** Việc chỉ dùng **type()** giúp tránh **khởi tạo đối tượng service**, nhưng không bảo đảm không nạp class, không kiểm tra service configuration, không đọc annotation hoặc không xảy ra ServiceConfigurationError. Trong một vài môi trường có classloader tùy biến, các bước đó vẫn tốn thời gian.

## 4. Ví dụ Java 17 chạy được: chọn provider theo annotation

Ví dụ sau chạy trên **classpath**, có hai provider hợp lệ nhưng chỉ khởi tạo provider được chọn. Ta gắn annotation **@PluginKind** lên lớp provider. Khi xem **Provider.type()**, host đọc annotation rồi chọn **upper**, sau đó mới gọi **Provider.get()**.

Cấu trúc thư mục:

~~~text
provider-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   ├── TextTransformer.java
│       │   └── PluginKind.java
│       ├── plugins/
│       │   ├── UppercaseTransformer.java
│       │   └── ReverseTransformer.java
│       └── Demo.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.spi.TextTransformer
~~~

**Tệp src/demo/spi/TextTransformer.java** — service contract:

~~~java
package demo.spi;

public interface TextTransformer {
    String transform(String text);
}
~~~

**Tệp src/demo/spi/PluginKind.java** — annotation metadata giữ được ở runtime:

~~~java
package demo.spi;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface PluginKind {
    String value();
}
~~~

Không có **RetentionPolicy.RUNTIME** thì lời gọi **Class.getAnnotation(PluginKind.class)** không đọc được annotation bằng reflection lúc chạy; khi đó bộ lọc dựa vào annotation sẽ không tìm thấy provider.

**Tệp src/demo/plugins/UppercaseTransformer.java** — provider mục tiêu:

~~~java
package demo.plugins;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;
import java.util.Locale;

@PluginKind("upper")
public final class UppercaseTransformer implements TextTransformer {
    public UppercaseTransformer() {
        System.out.println("Construct: UppercaseTransformer");
    }

    @Override
    public String transform(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

**Tệp src/demo/plugins/ReverseTransformer.java** — provider không được chọn:

~~~java
package demo.plugins;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;

@PluginKind("reverse")
public final class ReverseTransformer implements TextTransformer {
    public ReverseTransformer() {
        System.out.println("Construct: ReverseTransformer");
    }

    @Override
    public String transform(String text) {
        return new StringBuilder(text).reverse().toString();
    }
}
~~~

**Tệp resources/META-INF/services/demo.spi.TextTransformer** — service provider configuration file trên classpath:

~~~text
demo.plugins.ReverseTransformer
demo.plugins.UppercaseTransformer
~~~

Tên tệp phải đúng **tên binary đầy đủ của service**; nội dung là các tên class provider, mỗi tên một dòng, mã hóa UTF-8. Hai class phải tìm được từ class loader phù hợp, **public**, có constructor **public không tham số**, và triển khai TextTransformer. Classpath configuration này **không sử dụng static provider() factory method**; cơ chế static method áp dụng cho provider được khai báo trong **named module** (giải thích ở phần 6).

**Tệp src/demo/Demo.java** — host xem metadata và chỉ tạo instance sau khi chọn:

~~~java
package demo;

import demo.spi.PluginKind;
import demo.spi.TextTransformer;
import java.util.List;
import java.util.ServiceLoader;
import java.util.ServiceLoader.Provider;
import java.util.stream.Collectors;

public final class Demo {
    public static void main(String[] args) {
        ServiceLoader<TextTransformer> loader =
                ServiceLoader.load(TextTransformer.class);

        // Khám phá tất cả provider descriptors; chưa gọi constructor service.
        List<Provider<TextTransformer>> providers = loader.stream().toList();

        System.out.println("Discovered: " + providers.size());
        String names = providers.stream()
                .map(p -> p.type().getSimpleName())
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println("Types: " + names);

        Provider<TextTransformer> chosen = providers.stream()
                .filter(p -> {
                    PluginKind kind =
                            p.type().getAnnotation(PluginKind.class);
                    return kind != null && "upper".equals(kind.value());
                })
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No upper provider"));

        System.out.println("Selected: " + chosen.type().getSimpleName());
        System.out.println("Before get");

        TextTransformer transformer = chosen.get();
        System.out.println("Result: " + transformer.transform("java"));
    }
}
~~~

**Biên dịch và chạy từ thư mục provider-demo** với JDK 17 trở lên.

Trên macOS/Linux (bash):

~~~bash
mkdir -p out
javac -encoding UTF-8 -d out \
  src/demo/spi/TextTransformer.java \
  src/demo/spi/PluginKind.java \
  src/demo/plugins/UppercaseTransformer.java \
  src/demo/plugins/ReverseTransformer.java \
  src/demo/Demo.java
cp -R resources/META-INF out/
java -cp out demo.Demo
~~~

Trên Windows (PowerShell):

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/spi/TextTransformer.java src/demo/spi/PluginKind.java src/demo/plugins/UppercaseTransformer.java src/demo/plugins/ReverseTransformer.java src/demo/Demo.java
Copy-Item -Recurse -Force resources/META-INF out/
java -cp out demo.Demo
~~~

**Stdout trong môi trường chỉ có hai provider của ví dụ:**

~~~text
Discovered: 2
Types: ReverseTransformer, UppercaseTransformer
Selected: UppercaseTransformer
Before get
Construct: UppercaseTransformer
Result: JAVA
~~~

Cách tự xác minh cơ chế:

1. Lúc in số lượng, tên và kiểu provider, chưa thấy dòng **Construct:** nào; danh sách chứa các Provider descriptor chứ chưa chứa hai TextTransformer instance.
2. **type()** trên từng descriptor cho class tương ứng; bộ lọc đọc **@PluginKind("upper")** mà chưa cần gọi phương thức transform.
3. Chỉ sau dòng **Before get** mới xuất hiện **Construct: UppercaseTransformer**, do **chosen.get()**.
4. Không có **Construct: ReverseTransformer** vì chương trình không gọi get() của provider bị loại.
5. Danh sách tên được **sorted()** để stdout không phụ thuộc thứ tự khám phá. Trong môi trường có thêm provider cùng service trên classpath, kết quả có thể khác; ở ví dụ cô lập này có đúng hai.

**Để thấy lỗi thường gặp:** thử chuyển **.map(Provider::get)** lên *trước* filter bằng metadata. Khi ấy pipeline đang làm việc với **TextTransformer instance** chứ không còn **Provider**, và việc lọc sẽ cần khởi tạo các instance trước. Vì vậy giữ bộ lọc metadata trên Provider và chỉ **get() sau khi chọn**.

## 5. Các kiểu lựa chọn provider bằng type()

Không phải mọi lựa chọn đều cần annotation. Nếu metadata được công bố ở cấp class, có thể lọc theo:

### 5.1. Annotation của lớp provider

~~~java
// Mảnh minh họa: @Preferred cần @Retention(RUNTIME).
Provider<TextTransformer> p = loader.stream()
        .filter(d -> d.type().isAnnotationPresent(Preferred.class))
        .findFirst()
        .orElseThrow();
TextTransformer service = p.get();
~~~

Phù hợp khi cần metadata tĩnh như loại thuật toán, version/capability, mức ưu tiên hoặc trạng thái thử nghiệm. Đảm bảo annotation có ý nghĩa ổn định và không gắn host vào package implementation nếu có thể.

### 5.2. Tên class hoặc package

~~~java
// Mảnh minh họa: dùng tên class để kiểm tra hay chẩn đoán.
List<String> names = loader.stream()
        .map(d -> d.type().getName())
        .sorted()
        .toList();
~~~

Tên class hữu ích cho log/diagnostic, nhưng **không phải định danh nghiệp vụ bền vững**. Refactor, shading JAR hoặc thay implementation có thể đổi tên class dù chức năng giữ nguyên. Nếu cấu hình người dùng chọn theo ID, ưu tiên ID có hợp đồng công khai thay vì so khớp tên class cụ thể.

### 5.3. Điều kiện về kiểu

~~~java
// Mảnh minh họa: MarkerCapability là một interface khác.
List<Provider<TextTransformer>> advanced = loader.stream()
        .filter(d -> MarkerCapability.class.isAssignableFrom(d.type()))
        .toList();
~~~

Dùng khi hợp đồng cho phép provider triển khai một capability/marker khác; không nên lạm dụng downcast để gọi các phương thức chỉ tồn tại ở implementation. Nếu host cần nghiệp vụ bổ sung, hãy mô hình hóa rõ bằng một interface capability hoặc API mở rộng.

### 5.4. Metadata chỉ có ở instance

Nếu lựa chọn đòi hỏi gọi **service.supports(format)**, đọc cấu hình động hoặc kiểm tra kết nối, **type() không thể cung cấp** thông tin đó. Khi ấy phải khởi tạo đối tượng cần thiết hoặc thiết kế service là **factory/descriptor service** có API metadata rõ ràng, để chính đối tượng provider nhẹ có thể quyết định có tạo đối tượng nghiệp vụ nặng hay không.

**Ranh giới thiết kế:** type() cho thông tin **class**, get() cho **instance**. Không suy diễn mọi capability động từ Class, cũng không cố gọi constructor qua reflection từ **type()**.

## 6. Sự khác biệt quan trọng giữa classpath và named module

Mục này đặc biệt cần nhớ khi dùng **Provider.type()** để lọc annotation.

### 6.1. Provider đăng ký qua META-INF/services trên classpath

Trong ví dụ runnable phía trên, provider class **trực tiếp implements TextTransformer**, và ServiceLoader tạo đối tượng bằng **public no-arg constructor**.

- **Provider.type()** thường chính là class triển khai đăng ký trong tệp cấu hình.
- Đọc annotation đặt trên class đó bằng reflection có thể phục vụ lựa chọn.
- **Provider.get()** thực hiện khởi tạo qua constructor do ServiceLoader quản lý.
- Tệp cấu hình service và class provider phải có mặt trên classpath/class loader mà host sử dụng.

### 6.2. Provider khai báo bằng provides ... with ... trong module-info.java

Trong named module, provider có thể được khởi tạo theo **hai cách**:

1. **Provider constructor:** class triển khai service và có public no-arg constructor.
2. **Provider method:** provider class khai báo phương thức **public static provider()** không tham số, trả về kiểu gán được cho service. Bản thân provider class có thể **không implements service**.

Ví dụ khai báo module (mảnh minh họa, không thuộc chương trình classpath chạy ở phần 4):

~~~java
// module-info.java của module cung cấp service API
module text.spi {
    exports demo.spi;
}
~~~

~~~java
// module-info.java của module triển khai
module text.plugins {
    requires text.spi;
    provides demo.spi.TextTransformer
        with demo.plugins.UppercaseTransformer;
}
~~~

~~~java
// module-info.java của module host
module text.app {
    requires text.spi;
    uses demo.spi.TextTransformer;
}
~~~

Các provider được khai báo trong named module với **provides**. Host khai báo **uses**. Việc khai báo module không có nghĩa host cần **requires** trực tiếp module triển khai; provider nên có thể được thay thế mà host không phải phụ thuộc vào implementation module. Trong deployment module path, cần bảo đảm module provider được resolve vào module graph hoặc layer thích hợp.

**Trường hợp provider factory method:**

~~~java
// Mảnh minh họa cho named module, không phải provider classpath.
package demo.plugins;

import demo.spi.TextTransformer;

public final class TransformerSupplier {
    public static TextTransformer provider() {
        return new UppercaseTransformer();
    }
}
~~~

Với cấu hình **provides demo.spi.TextTransformer with demo.plugins.TransformerSupplier**, ServiceLoader gọi phương thức **provider()** để lấy instance; factory class không cần implements TextTransformer.

**Điểm dễ nhầm:** trong trường hợp provider factory method, **Provider.type() trả về kiểu return đã khai báo của phương thức public static provider()**, *không nhất thiết là TransformerSupplier.class hay class runtime cụ thể của object được trả về*. Nếu chữ ký return là **TextTransformer**, type() có thể chỉ là **TextTransformer.class**. Vì vậy bộ lọc dựa trên annotation đặt ở class implementation thực tế sẽ **không còn hoạt động như trong ví dụ classpath**.

Để chọn theo metadata trong cả hai cơ chế, nên cân nhắc dùng một **service contract cho descriptor/factory** với các thông tin capability được công bố rõ, hoặc một registry metadata do host quản lý. Không dựa vào phỏng đoán rằng **type() luôn cho class của đối tượng cuối cùng**. Tài liệu API cũng không bảo đảm type() công khai/accessible hoặc có public no-arg constructor; dùng **get()** để lấy service, không tự **newInstance()** từ type().

### 6.3. Không nhầm type() với getClass()

| Biểu thức | Đối tượng được mô tả | Khi nào dùng |
|---|---|---|
| **descriptor.type()** | Kiểu provider do ServiceLoader công bố, có thể là return type của provider() | Chọn/lọc theo metadata trước khi khởi tạo |
| **descriptor.get().getClass()** | Class runtime của instance nhận được | Khi thực sự cần inspect object sau khi khởi tạo |
| **descriptor.type().getDeclaredConstructor().newInstance()** | Tự thử khởi tạo bằng reflection | **Không nên dùng**: bỏ qua quy tắc provider() và encapsulation, có thể thất bại |

Với named module, package của provider thường **không export** cho host để giữ tính đóng gói. ServiceLoader có thể khởi tạo qua cơ chế quy định, trong khi mã host không có quyền trực tiếp tạo object từ class provider.

## 7. Stream, lựa chọn một provider và tránh khởi tạo thừa

Một pipeline tốt đặt các phép toán theo thứ tự:

~~~java
// Mảnh minh họa với @PluginKind và TextTransformer từ ví dụ.
TextTransformer selected = ServiceLoader.load(TextTransformer.class)
        .stream()
        .filter(p -> {
            PluginKind kind = p.type().getAnnotation(PluginKind.class);
            return kind != null && "upper".equals(kind.value());
        })
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("Provider not found"))
        .get();
~~~

Đối chiếu những cấu trúc dễ làm sai:

~~~java
// Mảnh minh họa: get() trước filter nên có thể tạo mọi instance
// bị duyệt, dù chỉ chọn được một provider cuối cùng.
TextTransformer eager = ServiceLoader.load(TextTransformer.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(s -> s.getClass().getSimpleName().contains("Upper"))
        .findFirst()
        .orElseThrow();
~~~

Trong ví dụ eager, Stream chỉ tạo các instance *khi được duyệt*, không phải tất cả ngay lúc gọi map; tuy nhiên mỗi phần tử được duyệt để kiểm tra đều phải qua **get()**, kể cả phần tử không được chọn. Nếu cần tìm provider theo loại cố định, việc lọc metadata trước get() tiết kiệm khởi tạo đáng kể.

Lưu ý các lựa chọn khác:

- **findFirst()** phụ thuộc thứ tự provider được khám phá. Ở named modules, thứ tự giữa các module/layer nhất định không được bảo đảm; không nên dựa vào “provider đầu tiên” để quyết định ưu tiên nghiệp vụ.
- Nếu có nhiều provider phù hợp, hãy dùng tiêu chí lựa chọn tường minh, ví dụ ID, version/capability hoặc priority rõ ràng, đồng thời định nghĩa cách giải quyết trùng ID/tie.
- **sorted(Comparator.comparing(p -> p.type().getName()))** tạo thứ tự chẩn đoán ổn định theo tên class nhưng có thể phải duyệt hết các provider; điều đó vẫn khác với tạo hết instance.
- Khi cần khởi tạo nhiều provider đã chọn, dùng **filter(...).map(Provider::get)**; khi chỉ cần một, **filter(...).findFirst().orElseThrow().get()** diễn đạt ý định rõ hơn.
- Một **Stream** chỉ được tiêu thụ một lần. Muốn làm hai phép duyệt riêng, tạo stream mới hoặc lưu các **Provider** descriptor vào collection như ví dụ.

## 8. Cache, reload và vòng đời instance

**ServiceLoader** quản lý cơ chế tìm/ghi nhớ những provider đã được nạp theo nhu cầu. Tuy nhiên cần tách ba khái niệm:

1. **Cache của ServiceLoader:** giúp quá trình duyệt tiếp theo xử lý các provider đã được nạp trước đó theo quy tắc của ServiceLoader.
2. **Provider descriptor:** mô tả khả năng tạo/lấy service instance; nó không phải chính service instance.
3. **Vòng đời của instance:** ServiceLoader.Provider.get() chỉ cam kết trả về một instance hợp lệ. Không được tự suy luận rằng mỗi lần get() luôn trả cùng một singleton, cũng không tự suy luận rằng mọi provider đều luôn tạo object mới.

Nếu cần singleton, per-request, per-session hoặc pool, chính **hợp đồng service/provider** phải quy định. Đặc biệt, provider method của named module có thể trả đối tượng được cache theo chính sách riêng; mã host không nên dựa vào số lần constructor chạy trong môi trường khác với ví dụ.

**reload()** xóa cache provider của ServiceLoader để việc tìm/nạp có thể thực hiện lại theo cấu hình khả kiến lúc đó. Sau khi gọi **reload()**, cần **bỏ stream/iterator đã tạo trước đó và tạo mới**, vì nguồn của chúng có thể ném **ConcurrentModificationException**. Reload **không tự unload class**, không tự đóng các instance cũ, không bảo đảm tải phiên bản JAR đã thay nếu classloader/module layer không đổi.

Nếu plugin giữ tài nguyên, host cần chính sách dừng/đóng riêng. ServiceLoader không thay thế lifecycle manager.

## 9. Lỗi, class loader và tính an toàn

### 9.1. ServiceConfigurationError có thể xuất hiện trước và sau get()

**ServiceConfigurationError** có thể xảy ra khi:

- Tệp META-INF/services sai định dạng, class được khai báo không tồn tại, không visible hoặc không triển khai service.
- Named module có khai báo provider sai quy tắc constructor/provider method.
- Khi **get()** gọi constructor hoặc static provider() mà phương thức ném exception hoặc provider() trả về null.
- Quá trình khám phá/nạp service gặp lỗi liên quan đến môi trường/module/classloader.

Với stream, một terminal operation có thể phát lỗi **ngay trong giai đoạn khám phá/type()**, dù chưa gọi get(). Vì vậy cách hiểu “chỉ get() mới có lỗi” là sai.

**ServiceConfigurationError kế thừa Error.** Thường nên xử lý nó tại **ranh giới tải plugin** để báo đúng service, provider và cấu hình lỗi; tránh nuốt lỗi rồi âm thầm coi như không có provider. Không có bảo đảm rằng cứ bỏ qua một provider lỗi là có thể duyệt tiếp toàn bộ provider còn lại một cách ổn định.

~~~java
// Mảnh minh họa tại ranh giới plugin loading.
try {
    ServiceLoader.load(TextTransformer.class)
            .stream()
            .forEach(p -> System.out.println(p.type().getName()));
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException("Invalid TextTransformer provider setup", error);
}
~~~

### 9.2. Chọn đúng class loader hoặc module layer

- **ServiceLoader.load(ServiceType.class)** dùng **thread context class loader**.
- **ServiceLoader.load(ServiceType.class, someClassLoader)** dùng class loader chỉ định làm điểm bắt đầu tìm provider.
- **ServiceLoader.load(moduleLayer, ServiceType.class)** tìm provider trong layer được chỉ định và các layer cha theo quy tắc của API.

Nếu API tìm được **0 provider** dù file cấu hình tồn tại, cần kiểm tra service name, classpath/module path, context classloader, resource visibility, **uses/provides** và module resolution. Trong plugin host chạy nhiều ứng dụng/module độc lập, không nên cache một ServiceLoader dùng toàn JVM khi context classloader có thể khác nhau.

**ServiceLoader instance không thread-safe.** Không cho nhiều thread cùng thao tác trên một ServiceLoader mà không điều phối. Cũng không dùng **parallel()** trên stream của loader như một cách tăng tốc mặc định; thứ tự, cache và cấu hình provider cần được xử lý an toàn theo hợp đồng.

### 9.3. Không coi việc “chỉ xem kiểu” là sandbox

Không tạo service instance trước khi chọn giúp giảm side effects của **constructor/provider()**, nhưng việc nạp class/đọc metadata vẫn liên quan tới mã và phụ thuộc bên ngoài. Khi **get()** được gọi, code provider thực thi trong process của host. **ServiceLoader không cung cấp cách ly bảo mật**, timeout, hạn ngạch tài nguyên hay tự động rollback plugin lỗi. Nếu cần chạy plugin không tin cậy, thiết kế cơ chế cách ly/giám sát phù hợp bên ngoài ServiceLoader.

## 10. Trường hợp lựa chọn nào nên dùng type() và trường hợp nào nên dùng get()?

| Nhu cầu | Cách đề xuất | Lý do |
|---|---|---|
| Liệt kê tên các provider được khai báo để hiển thị/log | **stream().map(p -> p.type().getName())** | Chưa cần service instance |
| Chọn provider bằng annotation RUNTIME trên provider type | **stream().filter(p -> p.type().getAnnotation(...))** | Lọc trước, get sau |
| Chọn một provider theo ID ở cấp metadata | **stream + metadata/registry + findFirst + get** | Không khởi tạo provider không được chọn |
| Chọn theo khả năng động, ví dụ supports(input) trên service | Có thể phải **get()** rồi gọi capability; hoặc thiết kế descriptor/factory service | type() không đại diện trạng thái runtime |
| Chạy tất cả provider được khám phá | **loader.iterator()** hoặc **stream().map(Provider::get)** | Mỗi provider cần instance để thực thi |
| Named module có static provider() trả về interface chung | Tránh suy luận class implementation từ **type()** | type() trả declared return type của provider() |
| Cần đóng/mở plugin, quản lý scope hoặc unload | Bổ sung lifecycle manager/registry/classloader policy | ServiceLoader chỉ giải quyết khám phá và lấy provider |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Lệnh sau có tạo tất cả service instance không?

~~~java
List<Class<? extends TextTransformer>> types =
        ServiceLoader.load(TextTransformer.class)
                .stream()
                .map(ServiceLoader.Provider::type)
                .toList();
~~~

**Trả lời:** Không chủ động yêu cầu tạo service instance. Nó duyệt và đọc kiểu của các provider, có thể nạp/kiểm tra class và ném lỗi cấu hình, nhưng không gọi Provider.get().

**Câu 2.** Vì sao lọc **p.type().isAnnotationPresent(...)** có thể sai khi named module sử dụng **public static provider()**?

**Trả lời:** type() trả về **kiểu trả về đã khai báo** của provider(), có thể chỉ là service interface hoặc một kiểu chung khác. Annotation đặt trên factory class hay class runtime do factory trả về không nhất thiết xuất hiện ở kiểu ấy.

**Câu 3.** Dùng **findFirst().get().transform(...)** có nghĩa là provider luôn là một singleton không?

**Trả lời:** Không. Ở đây **get()** là lời gọi trên Provider để nhận một service instance. Hợp đồng singleton/multiple instances thuộc chính sách provider; không suy đoán chỉ từ đoạn code.

**Câu 4.** Gọi **reload()** có khiến stream tạo trước đó tự động cập nhật danh sách provider không?

**Trả lời:** Không. Stream/iterator cũ phải được bỏ; chúng có thể ném **ConcurrentModificationException** sau khi cache được xóa. Tạo stream mới từ ServiceLoader sau reload và tự quản lý vòng đời các instance cũ.

**Câu 5.** Trong ví dụ hoàn chỉnh, vì sao ReverseTransformer không in dòng Construct?

**Trả lời:** Chương trình chỉ duyệt **Provider descriptor** của cả hai class và đọc annotation; chỉ **chosen.get()** trên UppercaseTransformer tạo service instance. Không có lệnh get() cho ReverseTransformer.

## 12. Checklist triển khai thực tế

Khi thiết kế một điểm mở rộng có nhiều provider, hãy kiểm tra:

1. **Service contract** nhỏ và rõ; phương thức, exception, đồng thời và vòng đời được mô tả cụ thể.
2. **Registration** đúng: tên service file và provider class trên classpath, hoặc **uses/provides** và module resolution cho named modules.
3. **Metadata dùng để chọn** thực sự có sẵn qua **type()** trong cơ chế provider đang sử dụng; có annotation **RUNTIME** nếu lọc bằng reflection.
4. **Pipeline** đặt filter/sort bằng metadata trước **Provider.get()** và chỉ tạo instance sau khi quyết định.
5. **Không dựa vào thứ tự** provider ngẫu nhiên cho chính sách ưu tiên; xử lý provider không có, trùng ID và lỗi cấu hình một cách tường minh.
6. **Không tự khởi tạo từ type()**: sử dụng **get()** để ServiceLoader thực hiện đúng cơ chế constructor/provider method và module encapsulation.
7. **Không chia sẻ ServiceLoader đồng thời**; sau **reload()**, tạo stream/iterator mới và quản lý instance cũ đúng vòng đời.
8. **Kiểm thử tối thiểu:** hai provider, chỉ một được chọn, constructor của provider bị loại không chạy, thiếu provider tạo lỗi phù hợp, trường hợp ServiceConfigurationError và named-module factory method được giải thích/test riêng.

**Điểm cần ghi nhớ:** **stream()** đưa ra các descriptor, **Provider.type()** cho phép xem/lọc thông tin kiểu trước khi khởi tạo, còn **Provider.get()** là thời điểm host yêu cầu service instance. Thiết kế chính sách lựa chọn bằng metadata sẽ tận dụng được sự tách biệt này, nhưng luôn phải chú ý sự khác nhau giữa classpath provider và named-module provider factory.

### Tài liệu chuẩn để đối chiếu

- Oracle Java SE 17 API — **java.util.ServiceLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17 API — **java.util.ServiceLoader.Provider**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
