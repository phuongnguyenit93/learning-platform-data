# Vai trò của reflection, proxy và method handle tại ranh giới tích hợp

Trong Java, phần lõi của hệ thống có thể phải làm việc với plugin, adapter, thư viện của nhà cung cấp hoặc thành phần được nạp sau khi ứng dụng đã biên dịch. **Ranh giới tích hợp** là nơi hợp đồng ổn định của ứng dụng gặp các thành phần có thể thay đổi ở runtime. Reflection, dynamic proxy và method handle thường xuất hiện tại đây, nhưng mỗi cơ chế trả lời một câu hỏi khác nhau:

- **Reflection:** ở runtime có những lớp, phương thức và annotation nào; đâu là extension point hợp lệ?
- **Dynamic proxy:** khi lời gọi đi qua một interface, cần chặn, kiểm soát hoặc chuyển tiếp nó như thế nào?
- **MethodHandle:** khi đã biết đích gọi, làm sao liên kết và thực thi lời gọi có chữ ký rõ ràng?

Chúng **có thể phối hợp**, nhưng không phải cứ tích hợp Java là phải dùng đủ cả ba. Bài này đi từ vị trí kiến trúc tới API, một chương trình Java 17 chạy được, các điểm dễ sai và cách lựa chọn khi xây dựng adapter.

## 1. Nhìn tổng thể ranh giới tích hợp

Giả sử hệ thống muốn cung cấp phương thức ổn định `GreetingGateway.greet(String)`, còn nhà cung cấp chỉ có `VendorPlugin.say(String)`. Bên gọi không nên phụ thuộc trực tiếp vào tên lớp, tên method và cách nạp plugin của nhà cung cấp. Ta có thể bố trí:

```text
Mã nghiệp vụ
    |
    v
Interface/port ổn định của ứng dụng (GreetingGateway)
    |
    v
Proxy: audit, policy, metrics, tracing (nếu cần)
    |
    v
Adapter / registry tích hợp
    |-- Reflection: khám phá metadata, xác minh extension point
    |-- MethodHandle: liên kết và thực thi target đã chọn
    |
    v
Plugin / thư viện bên ngoài
```

Đây là sơ đồ trách nhiệm, không phải trình tự bắt buộc của mọi dự án. Nếu plugin đã triển khai trực tiếp một interface chung, lời gọi Java thông thường hoặc `ServiceLoader` có thể là đủ.

| Cơ chế | Giá trị cốt lõi | Điểm thường đặt trong tích hợp | Giới hạn |
| --- | --- | --- | --- |
| `java.lang.reflect` | Khám phá cấu trúc runtime, kiểm tra annotation/chữ ký, gọi động | Discovery và validation khi đăng ký plugin | Không tự tạo hợp đồng nghiệp vụ ổn định; lỗi kiểu có thể lộ ra muộn |
| `java.lang.reflect.Proxy` | Chặn các lời gọi tới interface bằng `InvocationHandler` | Wrapper/adapter cho kiểm soát truy cập, log, metrics | JDK dynamic proxy chỉ triển khai interface, không tự proxy mọi class |
| `java.lang.invoke.MethodHandle` | Lưu lời gọi có kiểu và điều chỉnh chữ ký khi cần | Target invocation đã liên kết, thường được cache | Không khám phá ý nghĩa API hoặc vượt quyền truy cập tự động |
| Interface/`ServiceLoader` | Hợp đồng tĩnh và discovery theo SPI | Lựa chọn đầu tiên khi cả hai phía dùng chung API | Cần thỏa thuận interface và class loader |

## 2. Reflection: từ metadata tới extension point

Reflection sử dụng `Class<?>`, `Method`, `Constructor`, `Field` và annotation để xem một đối tượng hoặc lớp cung cấp khả năng gì trong lúc chạy.

Ở ranh giới plugin, một quy trình hợp lý gồm:

1. Nhận đối tượng provider hoặc nạp lớp từ nguồn và class loader được phép.
2. Dùng reflection tìm method/constructor hoặc annotation được coi là extension point.
3. Kiểm tra cả **tên, tính public, kiểu tham số, kiểu trả về, version và số lượng kết quả**.
4. Tạo adapter hoặc đối tượng gọi đã kiểm tra; chỉ sau đó công bố nó cho phần lõi.

Sự khác biệt giữa các API thường gây lỗi:

- `getMethod("say", String.class)` chỉ tìm phương thức **public**, kể cả public method được kế thừa.
- `getDeclaredMethod("say", String.class)` tìm khai báo **tại chính lớp đó**, có thể là private, không tự động được phép gọi nó.
- `getMethods()` trả các public method có thể truy cập theo quy tắc Java; lọc annotation qua `isAnnotationPresent(...)`.
- `Method.invoke(receiver, args...)` thực hiện lời gọi, trả `Object`. Với method instance cần receiver thích hợp; primitive được boxing/unboxing. Với static method, receiver không cần mang instance.

**Xử lý ngoại lệ:** nếu chính method của plugin ném lỗi, `Method.invoke` thường bọc lỗi đích trong `InvocationTargetException`. Muốn giữ đúng lỗi gốc hãy đọc `getCause()`. `IllegalAccessException` phản ánh vấn đề truy cập; `NoSuchMethodException` phản ánh lookup không thấy chữ ký yêu cầu. Không nên gộp mọi lỗi vào một thông báo “reflection failed” vì vận hành sẽ khó phân biệt lỗi cấu hình với lỗi nghiệp vụ.

**Thời điểm sử dụng:** discovery và signature validation thường thực hiện **một lần khi đăng ký/khởi tạo provider**, sau đó cache `Method` hoặc tạo adapter. Việc quét `getMethods()` và annotation ở mọi request làm ranh giới khó kiểm soát và tăng chi phí.

**Không nên:** lấy class/method name tùy ý từ input của người dùng rồi gọi bằng reflection. Cần allowlist, quy tắc extension point, kiểm tra quyền và tham số; reflection trong cùng JVM không tạo sandbox cho mã không tin cậy.

## 3. Dynamic proxy: kiểm soát những lời gọi đi qua interface

`Proxy.newProxyInstance(classLoader, interfaces, invocationHandler)` tạo instance runtime triển khai một hoặc nhiều interface. Khi caller gọi method thông qua instance này, handler nhận:

- `proxy`: chính đối tượng proxy;
- `method`: metadata `Method` của lời gọi;
- `args`: đối số, có thể `null` nếu không có tham số.

Handler có thể kiểm tra quyền, bắt đầu trace, đếm metrics, đo latency, chuyển tiếp tới implementation và ánh xạ lỗi. Phần lõi vẫn chỉ nhìn thấy interface.

```text
caller.greet("An")
    -> proxy / InvocationHandler
       -> kiểm tra chính sách
       -> chuyển tiếp sang adapter/plugin
       -> ghi audit hoặc metrics, hoàn tất
    -> caller
```

Những giới hạn cần tính trước:

1. **Interface-only:** JDK `Proxy` không tự tạo subclass cho một class bất kỳ. Nếu provider không có interface, hãy viết adapter hoặc dùng công cụ sinh bytecode phù hợp khi thật sự cần.
2. **Đường gọi:** chỉ lời gọi qua *instance proxy* mới bị chặn. Nếu target tự gọi phương thức nội bộ bằng `this`, lời gọi đó không qua proxy.
3. **Các method của `Object`:** `equals`, `hashCode` và `toString` cũng có thể đến handler. Phải chọn chính sách nhất quán; đừng vô tình gọi lại proxy và gây đệ quy.
4. **Default methods:** nếu interface có default method, handler cần quyết định dùng triển khai mặc định hay xử lý riêng. Java 17 hỗ trợ `InvocationHandler.invokeDefault(...)` khi muốn gọi default implementation.
5. **Checked exception:** checked exception mà handler ném nhưng không được interface khai báo có thể bị bọc thành `UndeclaredThrowableException`. Hợp đồng lỗi cần được thiết kế có chủ đích.
6. **Class loader:** loader dùng để tạo proxy phải nhìn thấy interface chính xác mà caller sử dụng; hai interface trùng tên do hai loader định nghĩa vẫn là hai kiểu khác nhau.

Proxy không tự phát hiện plugin nào đúng. Nó là nơi áp dụng **chính sách quanh một interface**; phương thức thật có thể được gọi trực tiếp, bằng reflection hoặc bằng method handle ở bên trong handler/adapter.

## 4. MethodHandle: lời gọi động nhưng có kiểu

`MethodHandle` từ package `java.lang.invoke` là tham chiếu tới một thao tác có thể gọi. Mỗi handle có `MethodType` chỉ rõ kiểu tham số và giá trị trả về; tạo handle thông qua `MethodHandles.Lookup`, chẳng hạn:

- `findVirtual`: method instance;
- `findStatic`: method static;
- `findConstructor`: constructor;
- `unreflect(Method)`: biến một `Method` tìm bằng reflection thành handle.

Ví dụ ý tưởng với `public VendorPlugin.say(String)`:

```java
MethodType signature = MethodType.methodType(String.class, String.class);
MethodHandle unbound = MethodHandles.publicLookup()
    .findVirtual(VendorPlugin.class, "say", signature);

// Cố định receiver để lời gọi sau chỉ cần đối số String.
MethodHandle bound = unbound.bindTo(plugin);
String result = (String) bound.invokeExact("An");
```

Đây là đoạn minh họa sử dụng các biến/lớp trong ví dụ đầy đủ bên dưới.

Một handle tạo từ `findVirtual` cho method `String say(String)` có kiểu lời gọi chứa receiver, tương đương `(VendorPlugin, String) -> String`. Sau `bindTo(plugin)`, nó còn `(String) -> String`. Các khái niệm quan trọng:

- `invokeExact` yêu cầu chữ ký **tĩnh tại vị trí gọi** khớp chính xác với `handle.type()`, gồm cả kiểu trả về. Vì vậy phép ép `(String)` trong ví dụ giúp xác định kiểu call site; không khớp có thể gây `WrongMethodTypeException`.
- `invoke` cho phép một số thích nghi kiểu theo quy tắc của method handle; `asType(...)` tạo handle thích nghi chữ ký một cách tường minh. Không phải mọi cast/conversion đều hợp lệ.
- `invokeWithArguments(...)` tiện cho lời gọi linh hoạt qua danh sách `Object`, đổi lại ít ràng buộc kiểu tĩnh và có thêm chuyển đổi.
- `invokeExact` và `invoke` khai báo `throws Throwable`; ngoại lệ của method đích truyền ra qua đường gọi này, không tự tạo `InvocationTargetException` như `Method.invoke`.
- `MethodHandle` không tự “nhớ” phải cache đúng lifecycle. Nếu liên kết lại target mỗi request, lợi ích tiềm năng của đường gọi đã chuẩn hóa có thể bị triệt tiêu.

Khả năng truy cập của handle dựa trên `Lookup` và quy tắc Java/JPMS. `publicLookup()` chỉ truy cập thành viên public đủ điều kiện; `privateLookupIn` cũng cần quyền thích hợp, không phải cách tự do vượt mọi đóng gói.

## 5. Ví dụ Java 17 chạy độc lập: kết hợp đủ ba

Bối cảnh: lõi cung cấp `GreetingGateway.greet(String)`, nhưng plugin nhà cung cấp lại công bố method `say(String)` đánh dấu `@EntryPoint`. Reflection tìm đúng method, method handle liên kết target và dynamic proxy thêm audit trước lời gọi. Mọi lớp đặt trong một file để thử trực tiếp; thực tế chúng có thể nằm ở các module khác nhau.

Tạo `BoundaryDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.invoke.*;
import java.lang.reflect.*;
import java.util.*;

public final class BoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface EntryPoint {}

    public interface GreetingGateway {
        String greet(String name);
    }

    public static final class VendorPlugin {
        @EntryPoint
        public String say(String name) {
            return "Hello, " + name + "!";
        }
    }

    public static void main(String[] args) throws Throwable {
        VendorPlugin plugin = new VendorPlugin();

        // Reflection: tìm extension point và xác minh chữ ký.
        Method selected = Arrays.stream(VendorPlugin.class.getMethods())
            .filter(m -> m.isAnnotationPresent(EntryPoint.class))
            .filter(m -> m.getName().equals("say"))
            .filter(m -> m.getReturnType() == String.class)
            .filter(m -> Arrays.equals(
                m.getParameterTypes(), new Class<?>[] {String.class}))
            .findFirst()
            .orElseThrow();

        // Một lời gọi trực tiếp qua reflection để so sánh.
        String viaReflection = (String) selected.invoke(plugin, "An");

        // Chuyển Method đã tìm thành handle và bind receiver.
        MethodHandle bound = MethodHandles.publicLookup()
            .unreflect(selected)
            .bindTo(plugin);

        // Proxy công bố interface ổn định cho phía ứng dụng.
        GreetingGateway gateway = (GreetingGateway) Proxy.newProxyInstance(
            GreetingGateway.class.getClassLoader(),
            new Class<?>[] {GreetingGateway.class},
            (proxy, method, arguments) -> {
                if (method.getDeclaringClass() == Object.class) {
                    return switch (method.getName()) {
                        case "toString" -> "GreetingGatewayProxy";
                        case "hashCode" -> System.identityHashCode(proxy);
                        case "equals" -> proxy == arguments[0];
                        default -> throw new UnsupportedOperationException(
                            method.getName());
                    };
                }
                if (!method.getName().equals("greet")) {
                    throw new UnsupportedOperationException(method.getName());
                }

                System.out.println("audit: " + method.getName());
                // Handle đã bind có kiểu (String) -> String.
                return (String) bound.invokeExact((String) arguments[0]);
            }
        );

        System.out.println("reflection: " + viaReflection);
        System.out.println("proxy: " + gateway.greet("Binh"));
        System.out.println("toString: " + gateway);
    }
}
```

Biên dịch với JDK 17+ và chạy:

```bash
javac --release 17 BoundaryDemo.java
java BoundaryDemo
```

Stdout chính xác:

```text
reflection: Hello, An!
audit: greet
proxy: Hello, Binh!
toString: GreetingGatewayProxy
```

**Giải thích đường đi của chương trình:**

1. `@Retention(RUNTIME)` giữ annotation tại runtime. `getMethods()` trả public methods; các `filter` bảo đảm chọn đúng annotation, tên và chữ ký. Ví dụ có một kết quả duy nhất; registry production phải báo lỗi rõ khi không có hoặc có nhiều entry point hợp lệ, tránh `findFirst()` phụ thuộc thứ tự duyệt.
2. `selected.invoke(plugin, "An")` minh họa reflection: biết `Method` ở runtime, gọi với receiver và tham số rồi ép kiểu `String`. Vì method không ném lỗi nên ví dụ không có `InvocationTargetException`.
3. `unreflect(selected).bindTo(plugin)` biến metadata đã chọn thành handle có chữ ký `(String) -> String` và cố định provider instance. Việc tạo handle diễn ra một lần trước các lời gọi từ gateway.
4. `Proxy.newProxyInstance(...)` cung cấp đối tượng triển khai `GreetingGateway`. Khi `gateway.greet("Binh")` được gọi, handler nhận `method=greet`, ghi audit rồi chuyển `arguments[0]` cho handle. Phép ép `(String)` ở cả argument và return cho `invokeExact` là có chủ ý.
5. `toString` được xử lý riêng trong handler; `hashCode` và `equals` dùng identity để nhất quán với wrapper minh họa. `main throws Throwable` giúp ví dụ gọn, còn mã production phải chuẩn hóa contract ngoại lệ và cleanup phù hợp.

Ví dụ chứng minh cách phối hợp, **không phải khuyến nghị luôn dùng cả ba**. Nếu plugin đã triển khai `GreetingGateway`, mã lõi có thể gọi interface trực tiếp hoặc dùng decorator/proxy khi cần audit, không cần reflection hay method handle.

## 6. Áp dụng vào các kiểu tích hợp thực tế

### A. Plugin có hợp đồng SPI chung

Tạo module API chứa interface, để provider triển khai nó, sau đó đăng ký bằng `ServiceLoader` hoặc một registry rõ ràng. Adapter có thể chỉ cần forward trực tiếp. Cách này dễ compile, test, refactor và kiểm soát version. Dynamic proxy chỉ thêm khi cần chính sách bao quanh interface.

### B. Plugin được khám phá qua annotation hoặc protocol

Khi class/method chỉ xuất hiện ở runtime, registry kiểm tra annotation, loại tham số, kiểu trả về và capability bằng reflection. Sau xác minh, registry tạo adapter về interface chung. Adapter có thể dùng `Method.invoke` đã cache hoặc `MethodHandle` đã bind; proxy bên ngoài áp dụng tracing, metrics và policy cho tất cả provider.

Điều kiện tiên quyết là **hợp đồng runtime được mô tả rõ**, gồm annotation, signature, version, kiểu lỗi và cách xử lý nhiều ứng viên. Cùng tên method không bảo đảm cùng ngữ nghĩa.

### C. Gọi nhiều lần cùng một target động

Khi target đã được chọn, cache `Method` hoặc method handle. Có thể dùng `asType`, `filterArguments`, `guardWithTest` để xây adapter lời gọi khi cần, nhưng giữ chúng ở lớp tích hợp và test kỹ. Không đưa `invokeExact` rải rác vào nghiệp vụ. Chọn hướng đơn giản nhất đáp ứng hợp đồng; tối ưu động chỉ nên dựa trên kết quả đo.

## 7. Quyền truy cập, JPMS và class loader

**Reflection không xóa quy tắc truy cập.** `getDeclaredMethod` có thể nhìn thấy metadata của thành viên private, nhưng không đồng nghĩa được gọi nó. `setAccessible(true)` không được bảo đảm thành công, đặc biệt với Java 17 và đóng gói mạnh của JPMS.

Trong named modules:

- `exports` công bố API public theo quy tắc module;
- `opens` cho phép deep reflection đối với package được mở;
- `MethodHandles.Lookup` có quyền phù hợp với nơi nó được tạo; `privateLookupIn` vẫn phải thỏa điều kiện quyền truy cập/module;
- cờ `--add-opens` có thể giúp chuyển đổi hệ thống cũ nhưng không nên trở thành thiết kế tích hợp mặc định.

**Class identity gồm cả class loader.** Hai bản `com.example.GreetingGateway` do hai loader khác nhau nạp không phải cùng một type. Để proxy và cast hoạt động, core và plugin phải cùng nhìn thấy API chung từ loader/layer thích hợp. Khi reload plugin, cache `Class`/`Method`/`MethodHandle` hoặc instance ở nơi sống quá lâu có thể giữ class loader cũ và làm rò rỉ bộ nhớ.

**Ranh giới tin cậy:** validate input/output, allowlist provider, kiểm soát capability/version, ghi audit vừa đủ và không để nội dung chưa tin cậy tùy ý chỉ định class/method. Code chạy trong cùng JVM không được sandbox chỉ vì nó đi qua proxy hay reflection. Với plugin không tin cậy, cần cân nhắc tách tiến trình và protocol có kiểm soát.

## 8. Lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | Sai tên hoặc parameter types ở lookup | Xác thực contract/version lúc đăng ký |
| `IllegalAccessException` / `InaccessibleObjectException` | Thành viên/package không đủ quyền hoặc chưa `opens` | Sửa API/module declaration với phạm vi tối thiểu |
| `InvocationTargetException` | Method của provider được gọi qua reflection ném lỗi | Lấy `getCause()` và giữ thông tin nguyên nhân |
| `WrongMethodTypeException` | Chữ ký handle hoặc call site `invokeExact` sai | Kiểm tra `handle.type()`, receiver, input và return |
| `UndeclaredThrowableException` | Handler ném checked exception không được interface khai báo | Định nghĩa hợp đồng lỗi, ánh xạ ngoại lệ có chủ đích |
| `ClassCastException` khi nhận proxy/provider | Interface bị nạp từ loader khác hoặc kiểu trả về sai | Thống nhất API class loader, validate kiểu |
| Không thấy audit của proxy | Caller gọi thẳng target hoặc target self-invocation | Bảo đảm caller sử dụng instance proxy |
| Lookup đúng nhưng hành vi sai | Provider đổi version hoặc ngữ nghĩa dù signature giống | Contract test trên hành vi, không chỉ metadata |

Hãy phân loại riêng **lỗi thiết lập tích hợp** (không tìm thấy entry point, sai module, sai loader, sai version) và **lỗi thực thi** (provider lỗi dữ liệu, timeout, nghiệp vụ). Lỗi thiết lập thường nên fail fast hoặc vô hiệu hóa provider khi đăng ký; lỗi runtime cần được biểu diễn qua contract và có ngữ cảnh vận hành.

## 9. Hiệu năng và tính bảo trì

Không có quy tắc “MethodHandle luôn nhanh hơn reflection” hay “dynamic proxy luôn chậm”. Chi phí phụ thuộc kiểu call site, độ ổn định target, JIT, boxing, conversion, phần việc trong handler và workload. Nhiều tích hợp mất thời gian chủ yếu ở I/O, serialization hoặc mạng chứ không phải bản thân lệnh invoke.

Các nguyên tắc thực dụng:

- **Tách discovery khỏi invocation:** chỉ scan annotation và chọn method khi khởi tạo/đăng ký, không scan mỗi request.
- **Cache đúng vòng đời:** cache metadata/handle sau validation; loại bỏ khi thay/reload provider để tránh giữ class loader cũ.
- **Chọn kiểu nhất quán:** với `invokeExact`, truyền nhận theo đúng `MethodType`; `asType` chỉ khi thực sự cần chuyển đổi hợp lệ.
- **Thiết kế handler tối giản:** xử lý `Object` methods, default methods và exceptions có chủ đích; tránh log dữ liệu nhạy cảm hay side effect bất ngờ.
- **Đo khi tối ưu:** nếu invocation thực sự nóng, dùng benchmark thích hợp như JMH cùng đo end-to-end latency. Benchmark không thay thế kiểm thử chức năng, quyền truy cập và module.
- **Kiểm thử trường hợp biên:** sai signature, nhiều entry point, checked/unchecked exception, plugin reload, JPMS, proxy caller và thay đổi version.

## 10. Quy tắc chọn nhanh

| Nhu cầu | Nên dùng |
| --- | --- |
| Hai phía chia sẻ interface từ trước | Gọi Java trực tiếp qua interface |
| Nhà cung cấp có SPI đăng ký chuẩn | `ServiceLoader` với interface |
| Chưa biết lớp/method/annotation tới runtime | Reflection cho discovery và validation |
| Cần audit, metrics, policy ở interface | Dynamic proxy hoặc decorator viết tay |
| Đã chọn target động và gọi lặp nhiều lần | `MethodHandle` hoặc `Method` được cache, tùy trường hợp |
| Cần chạy mã plugin không tin cậy | Ranh giới tiến trình/protocol; không coi reflection/proxy/handle là sandbox |

Trước khi hoàn thiện adapter, hãy kiểm tra: interface chung có ổn định không; metadata có xác minh đầy đủ signature và version không; module/loader có cho phép truy cập không; proxy có xử lý chính xác đường gọi và lỗi không; method handle có đúng receiver, tham số và return type không; cache có được giải phóng khi reload không; lỗi tích hợp có dễ chẩn đoán không.

**Điểm cốt lõi:** reflection giúp *khám phá và kiểm tra* thành phần động; dynamic proxy giúp *kiểm soát lời gọi qua hợp đồng interface*; method handle giúp *liên kết và thực thi* đích gọi đã được xác định. Đặt chúng trong registry/adapter tại ranh giới tích hợp giúp phần lõi giữ API rõ ràng dù plugin hay thư viện phía ngoài thay đổi.