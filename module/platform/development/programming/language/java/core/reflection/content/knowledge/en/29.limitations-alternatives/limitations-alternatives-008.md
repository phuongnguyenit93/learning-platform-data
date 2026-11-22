# So sánh Reflection với interface, Strategy, ServiceLoader và code generation trong Java

## 1. Cùng một bài toán, nhiều cách giải khác nhau

Giả sử một ứng dụng Java cần chọn cách biến đổi chuỗi, xử lý thanh toán hoặc tạo serializer dựa trên cấu hình. Có nhiều mức độ linh hoạt:

- **Interface và đa hình thông thường:** biết hợp đồng từ lúc biên dịch, gọi trực tiếp qua interface.
- **Strategy pattern:** đóng gói nhiều thuật toán cùng hợp đồng và chọn một thuật toán theo ngữ cảnh runtime.
- **`ServiceLoader`:** phát hiện các implementation của một **service interface/abstract class** được khai báo qua cơ chế provider của Java, không cần liệt kê từng implementation trong mã client.
- **Reflection:** truy vấn kiểu và thành viên tại runtime, có thể nạp lớp theo tên và tạo/gọi implementation khi cấu trúc được biết muộn.
- **Code generation:** tạo Java source, bytecode hoặc mã truy cập có kiểu theo schema/annotation/metadata, thường để giảm thao tác runtime lặp lại.

Đây không phải năm phương án hoàn toàn loại trừ nhau. Ví dụ: `ServiceLoader` trả về các implementation interface; ứng dụng có thể lưu chúng trong danh sách Strategy. Framework có thể dùng Reflection lúc khởi động rồi tạo mã hoặc cache dispatcher cho phần xử lý lặp lại.

**Nguyên tắc lựa chọn:** ưu tiên hợp đồng tường minh, kiểm tra được tại compile time; thêm dynamic discovery/introspection khi yêu cầu thực tế bắt buộc hoặc lợi ích vượt chi phí. Reflection giúp xử lý cấu trúc chưa biết trước, nhưng không nên dùng tên method dưới dạng chuỗi khi lời gọi có thể biểu diễn an toàn bằng interface.

## 2. Interface: hợp đồng ổn định và đa hình trực tiếp

Một interface quy định hành vi mà caller sử dụng. Ví dụ:

```java
public interface Transform {
    String apply(String input);
}
```

Implementation:

```java
public class UpperCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Client:

```java
Transform transform = new UpperCaseTransform();
System.out.println(transform.apply("Hi")); // HI
```

Ba đoạn trên là **các phần của ví dụ nhiều file** sẽ được trình bày đầy đủ ở phần 7; mỗi `public` top-level type nằm trong file cùng tên.

Lợi ích:

1. Trình biên dịch kiểm tra tên method, kiểu tham số và kiểu trả về.
2. IDE refactor/rename dễ tìm nơi sử dụng và báo lỗi compile khi đổi hợp đồng.
3. Caller chỉ cần biết `Transform`, không phải tìm `Method`, thực hiện `setAccessible` hay tự ép kết quả `Object`.
4. Gọi method thông thường có thể được JIT tối ưu theo đặc điểm runtime; không có chi phí tự tạo metadata Reflection cho từng lời gọi.
5. Có thể tiêm implementation bằng constructor injection, factory hoặc DI container.

Giới hạn của **interface đơn thuần**: ai đó vẫn phải quyết định tạo implementation nào. Nếu cần plugin tự xuất hiện mà mã client không biết tên lúc build, phải thêm cơ chế discovery như `ServiceLoader` hoặc cơ chế DI/registry thích hợp.

Không có lý do dùng Reflection chỉ để gọi `transform.apply(text)` nếu đối tượng đã triển khai `Transform` và hợp đồng đó đáp ứng nhu cầu.

## 3. Strategy pattern: chọn thuật toán runtime mà không phải gọi Reflection

**Strategy** là pattern thiết kế: đưa hành vi biến đổi thành các object cùng interface, rồi chọn object cần dùng khi chương trình chạy. Interface là phần hợp đồng; Strategy mô tả **cách tổ chức và hoán đổi thuật toán**.

Ví dụ registry:

```java
java.util.Map<String, Transform> strategies = java.util.Map.of(
        "upper", new UpperCaseTransform(),
        "lower", new LowerCaseTransform());

Transform selected = strategies.get("lower");
if (selected == null) {
    throw new IllegalArgumentException("Unsupported transform");
}
System.out.println(selected.apply("Hi")); // hi
```

Đoạn minh họa giả định `Transform`, `UpperCaseTransform` và `LowerCaseTransform` đã được định nghĩa. Ví dụ chạy độc lập phía dưới cung cấp đủ file.

Ưu điểm:

- Có thể thay đổi thuật toán ở runtime dựa vào request, config hoặc feature flag mà vẫn giữ lời gọi qua interface.
- Mỗi strategy có test riêng, phụ thuộc có thể tiêm bằng constructor, dễ mô tả ownership và vòng đời.
- Có thể tập trung kiểm tra tên strategy, chính sách fallback và khả năng truy cập ở một điểm chọn.
- Logic điều phối không cần `Class.forName` hoặc `getMethod`.

Giới hạn:

- Registry `Map.of(...)` tĩnh biết trước những class có thể chọn tại build time. Nếu muốn thêm plugin JAR mà không sửa danh sách, cần cơ chế cung cấp/đăng ký strategy động.
- String key của registry vẫn có nguy cơ sai chính tả tại runtime; ứng dụng có thể dùng enum/key có kiểm tra hoặc validate config khi khởi động.
- Chiến lược có thể có state mutable; việc tái sử dụng cùng instance cho nhiều thread đòi hỏi thiết kế thread safety phù hợp.

**Strategy không tự động phát hiện implementation.** Bạn có thể kết hợp Strategy + `ServiceLoader` để thu nhận các nhà cung cấp từ classpath/module path, rồi chọn theo một ID ổn định.

## 4. ServiceLoader: tìm implementation được đăng ký qua SPI

`java.util.ServiceLoader<S>` là cơ chế **Service Provider Interface (SPI)** của JDK. Ứng dụng xác định service contract `S`; một hoặc nhiều provider công bố rằng chúng có thể cung cấp implementation của `S`. Client duyệt và sử dụng provider qua service type, thay vì cần biết tên implementation trước.

```java
java.util.ServiceLoader<Transform> loader =
        java.util.ServiceLoader.load(Transform.class);

for (Transform provider : loader) {
    System.out.println(provider.apply("Hi"));
}
```

Đây là mảnh minh họa. **Thứ tự provider không nên được dùng làm hợp đồng nghiệp vụ**; ví dụ đầy đủ sẽ sắp xếp kết quả để stdout xác định.

### 4.1. Classpath: đăng ký ở META-INF/services

Với ứng dụng chạy trên **classpath** (không phải module có tên), nếu service interface là `Transform` trong unnamed package, resource cần có đường dẫn:

```text
META-INF/services/Transform
```

Nội dung:

```text
UpperCaseTransform
LowerCaseTransform
```

Tên mỗi provider phải là **tên lớp nhị phân** của implementation. Trong dự án thực, nếu interface là `com.example.spi.Transform`, tên file phải là:

```text
META-INF/services/com.example.spi.Transform
```

và từng dòng bên trong ghi tên đầy đủ, ví dụ `com.example.impl.UpperCaseTransform`. Đăng ký provider ở một file cấu hình tự đặt tên sẽ không làm `ServiceLoader` tự nhận ra.

Với provider được triển khai trên **classpath**, dạng đơn giản nhất là public concrete class implement service type và có public constructor không tham số. Provider phải nhìn thấy được từ class loader có trách nhiệm đọc cấu hình. Lỗi package/classpath, thiếu public constructor, sai tên hoặc provider không đúng service type có thể dẫn tới `ServiceConfigurationError` khi duyệt.

### 4.2. Module path: uses và provides

Với Java Platform Module System (JPMS), cú pháp ví dụ (trích đoạn **module descriptors**, không ghép trực tiếp vào chương trình classpath ở phần 7):

```java
// Trong module client, ví dụ: module client.app
uses com.example.spi.Transform;
```

```java
// Trong module provider, ví dụ: module provider.impl
provides com.example.spi.Transform
    with com.example.impl.UpperCaseTransform;
```

Ứng dụng thường thêm `requires` để đọc module chứa service interface. Hai directive `uses` và `provides ... with ...` tham gia liên kết service/provider theo cơ chế module; ví dụ JPMS cũng đòi hỏi khai báo module và cấu trúc package hợp lệ, nên các fragment trên **không phải project độc lập**.

ServiceLoader hỗ trợ named-module provider theo hợp đồng riêng, bao gồm khả năng dùng provider method `public static provider()` trong provider class khi thỏa quy tắc tương ứng; không đồng nhất toàn bộ quy tắc named modules với yêu cầu constructor không tham số của classpath provider.

### 4.3. Discovery, lazy loading và vòng đời

- `ServiceLoader.load(Transform.class)` dùng thread context class loader trong overload phổ biến này; overload `load(service, classLoader)` cho phép chỉ định class loader.
- Việc phát hiện/cài đặt provider thường **lười**; một số lỗi cấu hình chỉ lộ ra khi duyệt iterator hoặc stream/lấy instance, không nhất thiết ngay tại lời gọi `load(...)`.
- ServiceLoader lưu cache provider đã khám phá; `reload()` xóa cache của loader để cho phép tra cứu lại. Không suy rằng mọi JAR mới tự được phát hiện nếu class loader không thấy nó.
- `ServiceLoader` **không thread-safe**; khi nhiều thread dùng cùng một instance, ứng dụng phải đồng bộ hoặc tổ chức loader/registry phù hợp.
- Không dùng “provider đầu tiên” để suy thứ tự ưu tiên khi hệ thống không có quy tắc ordering tường minh; nếu cần, đọc metadata/priority riêng rồi sắp xếp.
- `ServiceConfigurationError` là một `Error`, không phải `Exception`. Vì vậy `catch (Exception)` không phải biện pháp xử lý đầy đủ cho provider config hỏng.

**Ranh giới:** ServiceLoader tìm implementation **đã đăng ký cho service contract**, chứ không tự scan mọi class trong classpath rồi lựa chọn theo tên method/annotation bất kỳ. Khi cần xử lý cấu trúc trường/method chưa có interface chung, Reflection có thể vẫn cần.

## 5. Reflection: khi không có đủ cấu trúc ở compile time

Reflection (`java.lang.Class`, `java.lang.reflect.Method`, `Field`, `Constructor`, ...) cho phép đọc metadata và thực hiện thao tác trên class/member lúc runtime.

Ví dụ cấu hình chứa tên implementation:

```java
String configuredClassName = "UpperCaseTransform";
Class<? extends Transform> implementation =
        Class.forName(configuredClassName).asSubclass(Transform.class);
Transform transform = implementation.getDeclaredConstructor().newInstance();
System.out.println(transform.apply("Hi")); // HI
```

Đây là mảnh code minh họa nằm trong phương thức có `throws ReflectiveOperationException` hoặc catch hợp lệ. Mã dùng `asSubclass(Transform.class)` để kiểm tra class đã nạp thực sự có thể dùng như `Transform`. Sau khi tạo instance, caller lại gọi qua interface bình thường.

### Điểm mạnh

1. Không cần biết trước **tất cả** class cụ thể tại compile time.
2. Hữu ích khi đọc annotation, xác định constructor/method/field, triển khai serializer/mapper, diagnostic tooling hoặc framework injection.
3. Có thể chọn class loader phù hợp với plugin, phân tích cấu trúc ở runtime và xây adapter cho các kiểu không cùng interface.
4. Có thể kết hợp cache metadata như `ClassValue<T>` để tránh tính toán lặp lại.

### Chi phí và giới hạn

- Tên class/method truyền bằng String thường chỉ được xác minh khi chạy; đổi tên API dễ làm hỏng cấu hình khi runtime.
- `getMethod`/`getDeclaredMethod` yêu cầu đúng tên và parameter types; sai overload/visibility sẽ ném checked lookup exception.
- `Method.invoke`, `Constructor.newInstance` có hợp đồng kiểm tra argument, access và wrapper exception (`InvocationTargetException` với lỗi do mã đích ném).
- Phân tích metadata và gọi gián tiếp có overhead; mức độ so với lời gọi trực tiếp phụ thuộc JDK, JIT, số lần gọi, khả năng caching. **Không gán một hệ số chậm cố định** cho mọi trường hợp.
- Các giới hạn JPMS về visibility/`opens` vẫn tồn tại; `setAccessible(true)` không bảo đảm thành công.
- Nạp/khởi tạo class dựa trên tên do người dùng không tin cậy nhập có thể kích hoạt code không mong muốn. Khi tạo plugin, cần allowlist, hợp đồng interface, class loader và chính sách phân quyền phù hợp.
- Với closed-world/native image, Reflection động có thể cần metadata cấu hình/đăng ký trước build; phải theo quy tắc của runtime/compiler đang dùng.

Dùng Reflection tốt khi nó phục vụ **khả năng khám phá/cấu trúc động**. Nếu sau khi nạp xong đã biết một interface, hãy chuyển sang gọi interface để đơn giản hóa phần còn lại.

## 6. Code generation: chuyển việc phân tích sang lúc build hoặc tạo bộ thực thi chuyên biệt

**Code generation** là nhóm kỹ thuật, không phải một API duy nhất:

- **Compile time source generation:** annotation processor (JSR 269), schema compiler hoặc build task sinh ra `.java`/resource trước hoặc trong quá trình compile. Client sau đó gọi generated code có kiểu.
- **Build time bytecode generation:** một công cụ sinh bytecode/class ở bước build trước khi ứng dụng chạy; đôi khi là augmentation của framework.
- **Runtime bytecode generation:** thư viện tạo class/adapter/proxy ở runtime từ metadata đã biết; ví dụ hệ proxy/mock/interceptor. Cách này có thể vẫn cần Reflection/MethodHandle trong giai đoạn phân tích và vẫn phụ thuộc class loader.
- **Ahead-of-time metadata/index generation:** build lập bảng descriptor hoặc index của annotation/type để phần runtime không phải scan rộng. Đây là hướng bổ trợ Reflection chứ không luôn thay thế việc Reflection dùng để gọi.

Ví dụ trước–sau mang tính **ý tưởng thiết kế**, không phải một code generator hoàn chỉnh:

```java
// Trước: runtime tìm method và invoke qua Reflection.
Method method = type.getMethod("apply", String.class);
String value = (String) method.invoke(instance, "Hi");

// Sau: nếu generator biết class/interface và tạo adapter ở build time,
// client gọi qua interface có kiểu. Adapter được generator tạo sẵn.
Transform adapter = generatedFactory.create(config);
String value2 = adapter.apply("Hi");
```

Đoạn trên chỉ minh họa phương án thay thế và giả định có `generatedFactory`, `type`, `instance`, `config` và `Transform` phù hợp. Không phải chương trình Java độc lập.

### Ưu điểm khi generated code phù hợp

- Nhiều lỗi mismatch được phát hiện sớm hơn khi compile generated code.
- Giảm việc quét annotation/Reflection hoặc tìm member động lặp lại khi khởi động/xử lý request.
- Có thể tạo dispatcher/serializer/mapper tối ưu cho schema cố định.
- Dễ kiểm tra những type/member cần dùng trong môi trường AOT khi generator tạo ra registration/metadata có kiểm soát.

### Đổi lại

- Có build step, processor/plugin/compiler và generated artifacts cần quản lý.
- Thay đổi schema hoặc annotation đòi hỏi regenerate và compile lại; cần test tính tái tạo/incremental build.
- Mã sinh có thể khó đọc stack trace, debug, map source hoặc quản lý phiên bản.
- Nếu class thật sự chỉ biết sau khi đã build và runtime cần tạo hành vi mới, source generation lúc build **không tự giải quyết** dynamic runtime discovery.
- Runtime bytecode generation có overhead tạo/lưu class và vẫn có ràng buộc loader/module/security; nó không làm mọi lời gọi tự nhiên nhanh hơn.

**Phân biệt:** `ServiceLoader` phát hiện implementation đã có; code generation **tạo mã** hoặc metadata; Reflection **quan sát/gọi cấu trúc runtime**; Strategy **điều phối thuật toán**. Các nhiệm vụ này có thể bổ trợ nhau trong một kiến trúc.

## 7. Ví dụ Java 17 chạy đầy đủ: bốn cách cho một service

Ví dụ sau minh họa **interface, Strategy, Reflection và ServiceLoader** cùng sử dụng `Transform`. Code generation không được chạy trong ví dụ vì nó cần thêm công cụ build/processor; phần 6 giải thích kiến trúc đó.

Tạo cấu trúc thư mục:

```text
demo/
├── Transform.java
├── UpperCaseTransform.java
├── LowerCaseTransform.java
├── ChoiceDemo.java
└── META-INF/
    └── services/
        └── Transform
```

**File `Transform.java`:**

```java
public interface Transform {
    String apply(String input);
}
```

**File `UpperCaseTransform.java`:**

```java
public class UpperCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

**File `LowerCaseTransform.java`:**

```java
public class LowerCaseTransform implements Transform {
    @Override
    public String apply(String input) {
        return input.toLowerCase(java.util.Locale.ROOT);
    }
}
```

**File `ChoiceDemo.java`:**

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.ServiceLoader;

public class ChoiceDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Transform viaInterface = new UpperCaseTransform();
        System.out.println("interface: " + viaInterface.apply("Hi"));

        Map<String, Transform> strategies = Map.of(
                "upper", new UpperCaseTransform(),
                "lower", new LowerCaseTransform());
        System.out.println("strategy: " + strategies.get("lower").apply("Hi"));

        Class<? extends Transform> implementation =
                Class.forName("UpperCaseTransform").asSubclass(Transform.class);
        Transform viaReflection = implementation.getDeclaredConstructor().newInstance();
        System.out.println("reflection: " + viaReflection.apply("Hi"));

        List<String> providers = ServiceLoader.load(Transform.class)
                .stream()
                .sorted(Comparator.comparing(p -> p.type().getName()))
                .map(p -> p.type().getSimpleName() + "=" + p.get().apply("Hi"))
                .toList();
        System.out.println("ServiceLoader: " + providers);
    }
}
```

**Resource `META-INF/services/Transform`** (văn bản UTF-8, không phải mã Java):

```text
UpperCaseTransform
LowerCaseTransform
```

Biên dịch ở thư mục `demo/`:

```bash
javac --release 17 Transform.java UpperCaseTransform.java LowerCaseTransform.java ChoiceDemo.java
java -cp . ChoiceDemo
```

Kết quả stdout đã kiểm tra:

```text
interface: HI
strategy: hi
reflection: HI
ServiceLoader: [LowerCaseTransform=hi, UpperCaseTransform=HI]
```

**Tại sao bốn dòng này khác nhau?**

1. **`interface`:** client tự tạo `UpperCaseTransform` và gọi `apply`; tên method được kiểm tra khi compile.
2. **`strategy`:** client chọn `"lower"` từ map chứa các đối tượng `Transform`. Cơ chế chọn dựa vào string key của registry, còn thực thi vẫn là lời gọi interface.
3. **`reflection`:** client biết `"UpperCaseTransform"` dưới dạng tên class runtime, kiểm tra `asSubclass`, tạo instance qua constructor rồi gọi interface. Không cần `Method.invoke` cho `apply` vì sau khi có `Transform`, lời gọi trực tiếp là đủ.
4. **`ServiceLoader`:** JDK tìm các provider được khai báo trong resource, tạo các instance và chạy qua interface. Ví dụ dùng `ServiceLoader.stream()` để truy vấn `Provider.type()`, sắp xếp theo tên class nhằm ổn định stdout, rồi `Provider.get()` mới lấy instance.

**Phạm vi ví dụ:** đây là dự án classpath trong **unnamed package** để có thể copy/chạy nhanh, không phải cấu trúc được khuyến nghị cho ứng dụng lớn. Trong dự án thực nên dùng package và cập nhật tên file `META-INF/services/<fully.qualified.ServiceInterface>` tương ứng. Chạy đúng thư mục root để resource `META-INF/services/Transform` nằm trên classpath; chỉ biên dịch các file Java mà quên resource sẽ làm danh sách provider rỗng.

Nếu đổi sang JPMS named modules, cần thêm `module-info.java`, package hợp lệ và directive `uses/provides` như đã trình bày ở phần 4; không trộn hai cách khai báo tùy tiện.

## 8. Bảng so sánh theo nhu cầu kiến trúc

| Tiêu chí | Interface trực tiếp | Strategy | ServiceLoader | Reflection | Code generation |
|---|---|---|---|---|---|
| Hợp đồng dùng ở client | Interface/kiểu compile time | Interface chung của thuật toán | Service interface/abstract class | Có thể chỉ biết tên/metadata runtime | Kiểu/adapter do generator tạo |
| Chọn implementation | Gắn cứng, inject hoặc factory | Registry/context/runtime policy | Provider registration và discovery | Tên class, metadata, loader, quy tắc tự xây | Build/schema/processor hoặc runtime generator |
| Có phát hiện plugin JAR tự đăng ký? | Không tự có | Không tự có | Có, khi JAR/module và provider config hiển thị đúng | Có thể tự xây logic discovery, nhưng `Class.forName` riêng lẻ không scan plugin | Không tự có nếu chỉ generation build time |
| Refactor-safe | Cao | Cao ở API, registry key cần quản lý | Cao ở interface, provider config phải đúng | Dễ lỗi runtime khi dùng string | Cao với generated typed API, tùy chất lượng generator |
| Metadata tùy ý | Hạn chế ở contract | Hạn chế ở contract | Có thể dùng metadata ngoài để chọn | Mạnh: fields/methods/annotations | Có thể trích ở build time hoặc generate index |
| Lỗi điển hình | Compile/type mismatch | Sai key/cấu hình, logic thuật toán | `ServiceConfigurationError`, provider không thấy | `ClassNotFoundException`, `NoSuchMethodException`, `IllegalAccessException`... | Generator/build mismatch, output lỗi thời |
| Hiệu năng | Lời gọi đa hình thông thường | Lời gọi interface + chọn strategy | Chi phí discovery/provider creation, sau đó gọi interface | Lookup/invoke động, có thể cache | Build cost hoặc runtime generation cost; thường giảm xử lý lặp |
| Linh hoạt sau build | Phụ thuộc wiring | Đổi giữa strategy có sẵn | Thêm provider qua cấu hình/module/class loader phù hợp | Có thể xử lý class/metadata chưa biết trước | Build generation cần rebuild; runtime generation linh hoạt hơn |
| Độ phức tạp vận hành | Thấp | Thấp đến vừa | Resource/module/loader/provider lifecycle | Access, lỗi runtime, security, module, classloader | Build pipeline, generated code, debug, versioning |

**Không có thứ hạng hiệu năng hay tính linh hoạt tuyệt đối.** Một ServiceLoader có thể dùng Reflection/constructor nội bộ để tạo provider, trong khi lời gọi sau đó qua interface. Một framework codegen có thể tạo class vào runtime và dùng Reflection để discover metadata ở bước đầu. Đo đúng phần việc người dùng quan tâm trước khi thay kiến trúc.

## 9. Chọn giải pháp qua các câu hỏi thực tế

### 9.1. “Tôi đã biết method cần gọi ở compile time”

**Chọn interface/lời gọi Java trực tiếp.** Nếu có nhiều implementation đổi được, dùng Strategy với factory/registry hoặc DI. Reflection chỉ để gọi một method cố định thường làm mất type safety mà không đem lại khả năng hữu ích.

### 9.2. “Tôi có nhiều thuật toán, mỗi request chọn một cái”

**Chọn Strategy** với interface chung, registry ID có kiểm tra và chính sách fallback. Nếu thuật toán được tiêm bởi framework, vẫn là cùng ý tưởng đa hình. Không cần tạo class dựa theo tên bất kỳ từ user input.

### 9.3. “Người viết plugin đóng gói JAR riêng, app chỉ biết service interface”

**Chọn ServiceLoader** hoặc một plugin framework tương đương. Định nghĩa rõ contract, provider metadata, version compatibility và class loader. Dùng Strategy registry phía trên nếu cần chọn provider theo ID, priority hoặc quyền người dùng.

### 9.4. “Tôi cần đọc field/method/annotation của những class không có interface chung”

**Chọn Reflection** khi cần inspect runtime class, kết hợp cache `ClassValue` hoặc các descriptor đã phân tích khi thao tác lặp lại. Tách bước khám phá khỏi hot path và kiểm soát quyền truy cập/module.

### 9.5. “Tôi có schema/type ổn định, throughput cao, xử lý Reflection lặp lại nhiều”

**Cân nhắc code generation** cho accessor/mapper/serializer/dispatcher nếu profiling xác nhận bottleneck. Đảm bảo generator kiểm tra schema, build tái tạo được artifact và có test tương thích. Nếu lớp chỉ xuất hiện sau build, cân nhắc runtime generation, metadata caching hoặc giải pháp hỗn hợp.

### 9.6. “Tôi phải chạy native image hoặc môi trường đóng”

Ưu tiên thiết kế có **danh sách dependency/type có thể phân tích trước**. Interface và generated code thường dễ kiểm soát; Reflection và dynamic loading có thể cần khai báo metadata/registration bổ sung theo runtime. `ServiceLoader` có thể được hỗ trợ bởi native-image tooling theo cách riêng; phải kiểm thử build thực tế, không mặc định cứ dùng SPI là tự hoạt động như JVM truyền thống.

## 10. Kết hợp các kỹ thuật cho đúng ranh giới

Kiến trúc plugin thực tế có thể đi qua các bước:

```text
Client -> Transform interface (hợp đồng ổn định)
                 |
                 v
          Strategy registry
                 |
      +----------+----------+
      |                     |
  built-in               ServiceLoader
 implementations              |
                                v
                        registered providers
                                |
                                v
                       Transform.apply(...)
```

Trong quá trình khởi động, chương trình:

1. Tạo registry từ implementation sẵn có.
2. Dùng `ServiceLoader` tìm provider mới, kiểm tra ID và capability, tránh trùng key.
3. Đưa provider vào registry dưới interface chung.
4. Khi request tới, chọn strategy theo ID đã được allowlist và gọi interface.
5. Nếu framework còn cần đọc annotation/schema của provider, dùng Reflection **một lần ở bước khám phá**, lưu metadata đã kiểm tra, không bắt mọi request scan lại.

Nếu serialization/model binding là tác vụ nặng theo schema cố định, build tool có thể tạo adapter rồi đăng ký adapter như một provider. Như vậy **code generation và ServiceLoader không mâu thuẫn**, và Reflection có thể đóng vai trò discovery/validation thay vì nằm trên mọi invocation.

## 11. Rủi ro thường gặp và cách xử lý

**Lỗi 1 — Dùng `Class.forName(userInput)` như registry plugin.** Có thể nạp/khởi tạo class ngoài ý muốn và làm khó kiểm soát phiên bản. Nên định nghĩa contract, kiểm tra ID implementation được phép, thực hiện discovery tường minh và bảo vệ class loader.

**Lỗi 2 — Nghĩ interface tự có dynamic discovery.** Interface chỉ là hợp đồng. Muốn plugin được phát hiện, cần `ServiceLoader`, DI/container registration hoặc cơ chế riêng.

**Lỗi 3 — Nghĩ Strategy bắt buộc có Reflection.** Strategy chỉ cần các object implement interface chung. Ví dụ Map registry không dùng Reflection để gọi method.

**Lỗi 4 — Quên `META-INF/services` hoặc ghi sai binary name.** `ServiceLoader` không đọc ngẫu nhiên mọi file cấu hình. Xác minh tên file service, mỗi dòng provider, package, classpath/module path và cấu trúc JAR sau build.

**Lỗi 5 — Giả định ServiceLoader luôn trả một provider duy nhất/theo thứ tự xác định.** Nó có thể thấy nhiều provider. Nếu ứng dụng cần quyết định một provider, phải tự định nghĩa priority/ID/fallback có kiểm tra.

**Lỗi 6 — Dùng `Method.invoke` dù đã có interface.** Sau khi kiểm tra `asSubclass` hoặc ServiceLoader trả `Transform`, cứ gọi `transform.apply(...)` để có type safety.

**Lỗi 7 — Đánh đồng code generation với hiệu năng luôn tốt hơn.** Nếu workload nhỏ, chi phí thêm processor/build/debug có thể vượt lợi ích; cần benchmark đúng môi trường.

**Lỗi 8 — Bỏ qua API và class loader compatibility.** Plugin có thể compile theo một version contract khác runtime; ServiceLoader có thể ném `ServiceConfigurationError`, Reflection `ClassCastException` hoặc `LinkageError`. Quy định version/compatibility và test integration.

**Lỗi 9 — Tưởng Reflection có thể vượt mọi access rule.** `getDeclaredMethod` tìm private member nhưng khả năng gọi vẫn phụ thuộc Java access control và module openness. Không thiết kế plugin contract dựa vào việc ép mở private method của thư viện bất kỳ.

**Lỗi 10 — Để generated code thành nguồn sự thật khó cập nhật.** Định nghĩa schema/annotation contract rõ ràng, để build tạo code tái lập, không sửa tay generated files rồi hy vọng build sau giữ nguyên.

## 12. Checklist quyết định và đo lường

Trước khi chọn, trả lời:

1. Cần biết **hành vi** hay cần biết **cấu trúc class**?
2. Contract có ổn định ở compile time không?
3. Implementation là built-in, lựa chọn sẵn có, hay plugin sẽ xuất hiện động?
4. Cần discovery theo service ID hay theo cấu trúc annotation/field tùy ý?
5. Startup time, hot-path latency, throughput và class loader unloading quan trọng thế nào?
6. Ứng dụng chạy JVM thường, JPMS modular, native image hay container plugin?
7. Ai sở hữu versioning, config validation, fallback và audit lỗi?
8. Có profiling hoặc benchmark chứng minh Reflection là bottleneck cần thay bằng codegen không?

Một cách triển khai kiểm soát được là bắt đầu từ **interface + Strategy**, mở discovery bằng **ServiceLoader** khi có plugin contract, dùng **Reflection** để xử lý metadata thật sự động, và chỉ chuyển phần ổn định/tốn chi phí sang **code generation** sau khi có số đo và test phù hợp.

## 13. Câu hỏi tự kiểm tra

1. **Interface và Strategy khác nhau thế nào?** — Interface quy định hợp đồng; Strategy là cách tổ chức nhiều thuật toán theo hợp đồng và chọn implementation runtime.
2. **ServiceLoader có thay thế hoàn toàn Reflection được không?** — Không. Nó phát hiện provider của service contract, không tự phân tích cấu trúc field/method của class bất kỳ.
3. **Có cần `Method.invoke` sau khi đã tạo được `Transform` bằng `Class.forName`?** — Không. Gọi `transform.apply(...)` qua interface.
4. **Một provider ở classpath nhưng không có file `META-INF/services/<service binary name>` có tự được load không?** — Không theo cơ chế cấu hình classpath của ServiceLoader.
5. **Code generation build time có tự nạp plugin class chỉ tồn tại sau khi đã đóng gói bản build không?** — Không. Nó phải biết schema/type ở build time, hoặc cần cơ chế khác ở runtime.
6. **Nếu `ServiceLoader` provider bị lỗi cấu hình, có chắc `catch (Exception)` bắt được không?** — Không. `ServiceConfigurationError` là `Error`.
7. **Nếu dùng Reflection để đọc metadata ở startup rồi cache adapter, lời gọi hot path phải luôn qua Reflection?** — Không. Có thể chuyển sang interface, generated adapter hoặc cấu trúc đã phân tích.
8. **Vì sao benchmark quan trọng?** — Chi phí load provider, build cache, Reflection invoke và generated adapter khác nhau theo tình huống/JDK; không thể suy hiệu năng chỉ từ tên kỹ thuật.

## 14. Ghi nhớ

- **Interface** là hợp đồng compile time; **Strategy** chọn thuật toán theo hợp đồng đó ở runtime.
- **ServiceLoader** thực hiện discovery các **provider được đăng ký**, không tự scan mọi class.
- **Reflection** cho introspection và invocation linh hoạt khi cấu trúc chưa biết trước, đổi lại phải quản lý runtime name/signature, access, loader và exception.
- **Code generation** tạo mã/metadata chuyên biệt ở build time hoặc runtime; đánh đổi tính linh hoạt, thời gian build, chi phí startup và khả năng debug.
- **Kết hợp có kiểm soát** thường là phương án tốt: giao tiếp qua interface, dùng Strategy cho lựa chọn, ServiceLoader cho extension, Reflection cho khám phá metadata và codegen cho đoạn đã ổn định, có lợi ích đã đo.
