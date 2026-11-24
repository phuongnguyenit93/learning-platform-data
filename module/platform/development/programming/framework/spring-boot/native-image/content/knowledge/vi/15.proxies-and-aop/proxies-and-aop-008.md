# Thư viện sinh bytecode lúc chạy và yêu cầu tìm cách tích hợp tương thích

Nhiều framework Java tạo class mới trong lúc ứng dụng chạy để triển khai proxy, AOP, lazy loading, interception, serialization hoặc tối ưu lời gọi method. Trên JVM thông thường, thư viện có thể sinh bytecode rồi định nghĩa class qua class loader. Cách làm này linh hoạt, nhưng gây khó khăn cho **GraalVM Native Image** vì native executable được phân tích và biên dịch trước khi chạy.

Với Native Image, cần phân biệt hai việc:

- **Metadata cho dynamic access** mô tả class, method, field, resource hoặc tập interface proxy mà chương trình sẽ truy cập động.
- **Runtime bytecode generation** tạo ra một class file mới trong lúc chương trình đang chạy.

Reachability metadata có thể giải quyết trường hợp thứ nhất. Nó **không tự biến một thư viện sinh bytecode tùy ý thành thư viện tương thích native**. Muốn tích hợp thành công, cần dùng cơ chế AOT mà framework hỗ trợ, chuyển việc sinh class sang build time, thay đổi cách triển khai proxy hoặc dùng một tính năng đặc biệt có giới hạn của GraalVM.

## 1. Vì sao thư viện cần sinh bytecode?

Thư viện có thể tạo class mới thay vì viết sẵn mọi implementation. Ví dụ:

- Spring AOP tạo proxy để áp dụng transaction, security, cache hoặc advice.
- CGLIB tạo subclass để chặn method trên một class cụ thể.
- Byte Buddy tạo subclass, interceptor hoặc class phục vụ instrumentation.
- Javassist và ASM thao tác trực tiếp với class file hoặc bytecode.
- ORM có thể dùng proxy cho lazy loading hoặc enhancement để theo dõi thay đổi entity.
- Mocking framework có thể tạo implementation giả để kiểm thử.
- Thư viện RPC hoặc serializer có thể sinh adapter/proxy cho interface và schema.

Lợi ích của cách làm này là tạo implementation theo kiểu dữ liệu, annotation, cấu hình hoặc interface chỉ được biết khi runtime. Trên JVM, class loader có thể định nghĩa class mới và JVM sẽ xác minh, liên kết, nạp class đó khi cần.

Ví dụ khái quát:

~~~java
Class<?> proxyType = proxyGenerator.createProxyClass(
    PaymentService.class,
    interceptor
);

Object proxy = proxyType.getDeclaredConstructor()
    .newInstance();
~~~

`proxyGenerator` có thể dùng Byte Buddy, CGLIB, Javassist hoặc mã ASM để tạo class file. Vấn đề với Native Image là class mới này chưa tồn tại trong tập class được phân tích ở build time, nên compiler không thể mặc định đưa nó vào executable.

## 2. Phân biệt proxy, reflection và bytecode generation

Ba khái niệm thường đi cùng nhau nhưng không đồng nghĩa:

| Cơ chế | Việc thực hiện | Native Image cần gì? |
|---|---|---|
| Reflection | Tìm class/member hoặc gọi constructor/method/field | Reachability metadata khi phân tích không suy ra được |
| JDK dynamic proxy | Tạo implementation của một hoặc nhiều interface bằng `java.lang.reflect.Proxy` | Danh sách interface proxy phải xác định ở build time hoặc được đăng ký |
| Class-based proxy | Tạo subclass của class đích, thường bằng CGLIB hoặc Byte Buddy | Class proxy phải được framework tạo trước hoặc có cơ chế hỗ trợ phù hợp |
| Arbitrary bytecode generation | Sinh bytecode tùy dữ liệu rồi định nghĩa class mới qua class loader | Cần chuyển sang build time hoặc dùng tính năng đặc biệt được hỗ trợ; reflection hints đơn thuần không đủ |
| Instrumentation | Thay đổi class đã nạp hoặc gắn agent để biến đổi bytecode | Phụ thuộc khả năng của runtime; không thể mặc định hoạt động như HotSpot |

Ví dụ, khai báo reflection cho constructor của `PaymentService` không làm cho Byte Buddy tự sinh `PaymentServiceProxy`. Tương tự, khai báo proxy hint cho interface không đồng nghĩa GraalVM hỗ trợ mọi subclass được CGLIB tạo ra từ một class bất kỳ.

## 3. Mô hình mặc định của Native Image

Native Image phân tích tĩnh các đường đi có thể thực thi từ entry point và dependency. Các class, method và metadata cần thiết phải được nhận diện trước khi executable được tạo.

~~~mermaid
flowchart TD
    A["Source + dependencies"] --> B["Spring AOT / build plugins"]
    B --> C["Class files và proxy được tạo trước"]
    C --> D["GraalVM reachability analysis"]
    E["Runtime hints / proxy metadata"] --> D
    D --> F["Native executable"]
    F --> G["Chạy class và proxy đã chuẩn bị"]
    H["Sinh bytecode tùy ý lúc runtime"] -. "Không thuộc luồng mặc định" .-> I["Class loader / defineClass"]
    I -. "Không có class trong image" .-> G
~~~

Trong mô hình mặc định, native executable không có một JVM compiler đầy đủ để nhận và định nghĩa mọi bytecode tùy ý sau khi khởi động. Vì vậy, một thư viện gọi `ClassLoader.defineClass`, `MethodHandles.Lookup.defineClass`, `Enhancer.create()` hoặc `ByteBuddy.make().load()` trong runtime có thể thất bại, dù cùng mã chạy bình thường trên HotSpot.

GraalVM có các cơ chế riêng cho dynamic proxy, predefined classes và một số tính năng runtime class loading thử nghiệm. Chúng có phạm vi và điều kiện cụ thể; không nên xem chúng như một JVM tổng quát bên trong native executable.

## 4. JDK dynamic proxy: trường hợp có thể chuẩn bị trước

JDK proxy tạo class triển khai một tập interface đã cho:

~~~java
public interface PaymentOperations {
    Receipt charge(String orderId);
}

public final class PaymentInvocationHandler
        implements InvocationHandler {

    private final PaymentOperations target;

    public PaymentInvocationHandler(PaymentOperations target) {
        this.target = target;
    }

    @Override
    public Object invoke(
            Object proxy,
            Method method,
            Object[] args) throws Throwable {
        return method.invoke(target, args);
    }
}
~~~

Cách tạo proxy trên JVM:

~~~java
PaymentOperations proxy = (PaymentOperations) Proxy.newProxyInstance(
    PaymentOperations.class.getClassLoader(),
    new Class<?>[] { PaymentOperations.class },
    new PaymentInvocationHandler(target)
);
~~~

Native Image có thể phát hiện một số lời gọi `Proxy.newProxyInstance` và `Proxy.getProxyClass` khi tập interface có thể xác định ở build time. Khi đó proxy class được tạo trước và đưa vào image.

Nếu tập interface được quyết định bằng cấu hình runtime hoặc code path quá động, cần khai báo proxy metadata. Thứ tự interface cũng là một phần của định nghĩa proxy: cùng các interface nhưng khác thứ tự có thể tương ứng với proxy class khác nhau.

**JDK proxy phù hợp khi hợp đồng interface ổn định.** Đây thường là lựa chọn dễ tích hợp native hơn một thư viện phải sinh subclass tùy ý lúc runtime.

## 5. Spring AOT tạo bytecode trước khi native compilation

Spring AOT không chỉ sinh Java source và runtime hints. Kết quả AOT còn có thể chứa **bytecode, thường dùng cho các proxy động mà Spring cần**. Những class này được sinh trong build và trở thành đầu vào cho GraalVM.

Spring Boot ghi nhận các thư mục đầu ra thường gặp:

| Build tool | Thư mục class AOT thường gặp |
|---|---|
| Maven | `target/spring-aot/main/classes` |
| Gradle | `build/generated/aotClasses` |

Runtime hints được sinh ở các thư mục resource AOT tương ứng, chẳng hạn `target/spring-aot/main/resources` với Maven hoặc `build/generated/aotResources` với Gradle.

Có thể hình dung pipeline:

~~~text
@Configuration, @Bean, @Aspect, @Transactional
                    |
                    v
             Spring AOT processing
                    |
        +-----------+------------+
        |                        |
        v                        v
Generated Java source       Generated bytecode
        |                  (proxy classes, ...)
        |                        |
        +------------+-----------+
                     |
                     v
             GraalVM Native Image
                     |
                     v
              Native executable
~~~

Điều này có nghĩa proxy được Spring nhận diện và hỗ trợ có thể được chuẩn bị ở build time. Nó **không có nghĩa mọi thư viện thứ ba gọi Byte Buddy hoặc CGLIB trong runtime đều tự động được Spring AOT chuyển đổi**. Mỗi thư viện cần có tích hợp AOT, runtime hints hoặc cơ chế thay thế tương ứng.

## 6. Spring AOP: JDK proxy và CGLIB proxy

Spring AOP sử dụng hai cơ chế phổ biến:

| Cơ chế | Cách tạo | Điều kiện và giới hạn |
|---|---|---|
| JDK dynamic proxy | Tạo implementation của interface | Target cần có interface; caller thường làm việc qua interface |
| CGLIB proxy | Tạo subclass của class target | Không thể override `final` method; không thể kế thừa `final` class; private method không thể được advice |

Trên JVM, Spring có thể tạo proxy lúc khởi động. Trong native build, Spring AOT cần chuẩn bị các proxy mà context đã xác định để GraalVM có thể đưa chúng vào image.

Ví dụ một service có interface:

~~~java
public interface InvoiceService {
    Invoice create(String customerId);
}

@Service
class DefaultInvoiceService implements InvoiceService {

    @Override
    public Invoice create(String customerId) {
        return new Invoice(customerId);
    }
}
~~~

Có thể cấu hình Spring AOP dùng interface proxy:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
class AopConfiguration {
}
~~~

Khi cần transaction hoặc các auto-proxy creator khác, hãy kiểm tra cấu hình proxy thống nhất của Spring và Spring Boot. Thuộc tính `spring.aop.proxy-target-class` cũng có thể ảnh hưởng lựa chọn proxy trong Spring Boot. Đừng giả định một annotation riêng lẻ luôn thắng mọi cấu hình auto-proxy khác.

Một số điểm thiết kế:

- Inject qua interface nếu muốn dùng JDK proxy.
- Tránh ép class-based proxy khi không cần.
- Không kỳ vọng CGLIB advice được `final` class hoặc `final` method.
- Nhớ rằng self-invocation (method trong cùng target gọi method khác qua `this`) không đi qua proxy Spring AOP theo mô hình proxy thông thường.
- Dùng `@Configuration(proxyBeanMethods = false)` khi các phương thức `@Bean` không gọi trực tiếp lẫn nhau; dependency nên được truyền qua tham số method để tránh nhu cầu subclass proxy cho configuration class.

## 7. CGLIB, Byte Buddy, Javassist và ASM

Các thư viện này đều có thể tạo hoặc biến đổi bytecode, nhưng API và mục tiêu khác nhau:

| Thư viện/công cụ | Khả năng thường dùng | Rủi ro khi chuyển native |
|---|---|---|
| CGLIB | Sinh subclass và method interceptor | `Enhancer` tạo class mới trong runtime |
| Byte Buddy | Tạo subclass, implement interface, advice, instrumentation | `DynamicType.Unloaded.load()` định nghĩa class trong class loader |
| Javassist | Tạo/sửa class bằng API cấp cao | `CtClass.toClass()` hoặc cơ chế định nghĩa class |
| ASM | Sinh và biến đổi bytecode cấp thấp | Tự ghi class bytes rồi gọi `defineClass` |
| Java Instrumentation | Agent và class transformer | Cần khả năng attach/retransform và runtime instrumentation phù hợp |

Ví dụ Byte Buddy trên JVM:

~~~java
Class<? extends InvoiceService> proxyType =
    new ByteBuddy()
        .subclass(InvoiceService.class)
        .name("com.example.generated.InvoiceServiceProxy")
        .make()
        .load(InvoiceService.class.getClassLoader())
        .getLoaded();
~~~

Đoạn mã này định nghĩa class mới trong class loader ở runtime. Reachability metadata cho `InvoiceService` không tự tạo class `InvoiceServiceProxy` trong native image.

**Cần xem hành vi thực tế của thư viện**, không chỉ tên dependency. Một thư viện có thể dùng Byte Buddy trong test hoặc JVM mode, nhưng có một implementation khác được chọn trong native mode. Ngược lại, một thư viện không nhắc tới bytecode generation trong API công khai vẫn có thể dùng nó bên trong.

## 8. Chiến lược tích hợp tương thích

| Chiến lược | Khi phù hợp | Việc cần thực hiện |
|---|---|---|
| Dùng tích hợp AOT có sẵn của framework | Spring, ORM hoặc thư viện đã hỗ trợ native/AOT | Pin phiên bản được hỗ trợ, bật đúng plugin và làm theo hướng dẫn |
| Sinh class ở build time | Tập class và cấu trúc proxy biết trước | Chạy generator trước AOT/native compilation, đưa class file vào output |
| Dùng JDK dynamic proxy | Có interface ổn định, tập interface biết trước | Đăng ký proxy hints hoặc để phân tích tĩnh nhận diện |
| Thay proxy bằng decorator/registry tĩnh | Số implementation hữu hạn | Viết class tĩnh, composition hoặc method dispatch rõ ràng |
| Dùng metadata do thư viện cung cấp | Vấn đề là reflection, resource, serialization hoặc JDK proxy | Cập nhật dependency/reachability metadata và kiểm thử |
| Dùng predefined classes | Hệ thống legacy sinh class có bytecode ổn định và khớp chính xác | Thu thập class bytes theo tính năng GraalVM thử nghiệm, đánh giá giới hạn |
| Dùng runtime class loading thử nghiệm | Ứng dụng thật sự phải định nghĩa class mới sau khi khởi động | Chỉ áp dụng sau khi kiểm tra phiên bản GraalVM, giới hạn và chi phí |
| Tách thành JVM service | Plugin/class phải thay đổi tùy ý sau khi triển khai | Chạy phần dynamic trên JVM riêng, giao tiếp qua HTTP/gRPC/message |

Đừng bắt đầu bằng cách thêm hàng loạt reflection hints. Trước tiên hãy xác định thư viện cần **truy cập class đã tồn tại** hay cần **tạo class mới**. Hai vấn đề này có cách giải quyết khác nhau.

## 9. Sinh bytecode trước AOT bằng build task

Nếu tập proxy có thể biết ở build time, hãy chuyển việc sinh class sang một task riêng:

1. Build generator chạy bằng JVM trong môi trường build.
2. Generator dùng Byte Buddy, ASM hoặc thư viện tương ứng để ghi `.class` vào thư mục output.
3. Thư mục output được thêm vào main source set/classpath của ứng dụng.
4. Task `classes` và task Spring AOT phụ thuộc vào generator để class đã tồn tại trước khi AOT chạy.
5. Native compilation nhận class đã sinh cùng với các class ứng dụng khác.
6. Những class được chọn qua reflection vẫn cần metadata tương ứng nếu phân tích không suy ra được.

Ví dụ về thao tác sinh subclass bằng Byte Buddy ở **build process**:

~~~java
new ByteBuddy()
    .subclass(InvoiceService.class)
    .name("com.example.generated.InvoiceServiceProxy")
    .make()
    .saveIn(generatedClassesDirectory);
~~~

Đây là ví dụ minh họa bước ghi class file. Muốn tạo proxy có advice thực tế, generator còn phải định nghĩa method interception/delegation và các helper mà bytecode sinh ra sẽ gọi. Generator không cần chạy trong native application; nó chỉ cần chạy trong build.

Với Gradle, cấu hình task generator và khai báo thư mục generated output là đầu ra của source set; bảo đảm task AOT/native phụ thuộc task generator. Với Maven, gắn generator vào phase phù hợp trước `process-aot` và native compilation, rồi đưa thư mục class đã sinh vào output artifact.

**Thứ tự task rất quan trọng.** Nếu AOT chạy trước generator, Spring có thể không nhìn thấy class hoặc không thể xác định bean/proxy cần thiết. Nếu file `.class` chỉ nằm trong một thư mục không thuộc classpath build, GraalVM cũng không phân tích được class đó.

## 10. Dùng JDK proxy và đăng ký RuntimeHints

Khi thư viện chủ động gọi `Proxy.newProxyInstance` với danh sách interface không thể suy ra tĩnh, Spring có thể đăng ký proxy hint:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

public class PaymentProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.proxies().registerJdkProxy(PaymentOperations.class);
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentProxyHints.class)
class NativeProxyConfiguration {
}
~~~

Nếu proxy triển khai nhiều interface, đăng ký đúng tập interface theo thứ tự mà ứng dụng yêu cầu:

~~~java
hints.proxies().registerJdkProxy(
    PaymentOperations.class,
    Serializable.class
);
~~~

Đây là metadata cho **JDK interface proxy**. Nó không phải metadata để GraalVM sinh một subclass CGLIB bất kỳ hoặc chạy Byte Buddy trong runtime.

Spring Boot cũng cho phép khai báo proxy metadata trực tiếp trong các JSON hint file của GraalVM. Khi dùng file tĩnh, hãy đặt chúng trong vùng `META-INF/native-image` phù hợp và tránh ghi đè thư mục output do Spring AOT sinh ra.

## 11. Thư viện có hỗ trợ native cần cung cấp gì?

Một thư viện muốn hỗ trợ Spring AOT/Native Image nên làm rõ các yêu cầu động của nó:

- Reflection cần class/member nào?
- Có tạo JDK proxy không, và tập interface có thể xác định thế nào?
- Có tạo subclass hoặc class mới bằng CGLIB/Byte Buddy/Javassist không?
- Class được sinh ở build time hay runtime?
- Có resource, serialization, JNI hoặc instrumentation không?
- Có cách thay thế khi chạy native không?

Với thư viện Spring, các extension point có thể gồm:

- `RuntimeHintsRegistrar` để đóng góp reflection, resource, serialization và JDK proxy hints.
- `BeanFactoryInitializationAotProcessor` để đóng góp mã khôi phục bean factory.
- `BeanRegistrationAotProcessor` để đóng góp cách tạo/đăng ký bean.
- Các cơ chế AOT riêng của framework hoặc plugin build.

Một thư viện chỉ cung cấp reflection metadata mà vẫn gọi `new ByteBuddy().make().load()` khi runtime thì chưa giải quyết được vấn đề class generation. Nếu cần proxy, thư viện nên sinh proxy trong AOT/build hoặc cung cấp implementation tĩnh tương thích native.

Đối với thư viện bên thứ ba, kiểm tra reachability metadata repository và tài liệu native support của đúng phiên bản. Metadata repository có thể cung cấp hint cho các dynamic feature phổ biến; không thay thế một cơ chế runtime code generation mà Native Image không hỗ trợ.

## 12. Predefined classes: phương án chuyển tiếp cho một số hệ thống legacy

GraalVM có hỗ trợ **predefined classes** thông qua Native Image Tracing Agent trong một số phiên bản. Agent có thể ghi lại bytecode của class được định nghĩa động khi ứng dụng chạy trên JVM. Khi build native, các class bytes đã thu thập được chuẩn bị trước; runtime có thể cung cấp class tương ứng nếu tên và bytecode khớp với class đã quan sát.

Ví dụ chạy JVM với agent và tùy chọn experimental:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent,experimental-class-define-support \
  -jar target/application.jar
~~~

Sau khi chạy đủ các luồng cần thiết, thư mục cấu hình có thể chứa metadata và thư mục bytecode của predefined classes. Dùng đầu ra này trong native build theo hướng dẫn đúng phiên bản GraalVM.

Đây là **phương án best-effort cho legacy**, không phải cách biến mọi thư viện sinh class tùy ý thành tương thích native:

- Class phải được quan sát trong các lần chạy trên JVM.
- Khi runtime yêu cầu, tên class và bytecode phải khớp với class đã ghi nhận.
- Tên class hoặc bytecode thay đổi theo request, số thứ tự, timestamp hoặc dữ liệu ngẫu nhiên thường không thể khớp ổn định.
- Giới hạn class loader và số lần nạp class có thể áp dụng tùy phiên bản.
- Metadata không thể làm class mới xuất hiện nếu bytecode không được thu thập trước.

Agent thường không tự kiểm tra mọi nhánh nghiệp vụ. Thiếu test coverage có thể khiến một proxy class cần thiết không được ghi nhận.

## 13. Runtime class loading thử nghiệm

Một số bản GraalVM mới có tài liệu về tùy chọn thử nghiệm cho phép định nghĩa class từ bytecode khi native executable chạy. Tùy chọn được mô tả trong tài liệu phát triển hiện hành là `-H:+RuntimeClassLoading`, mở khóa bằng `-H:+UnlockExperimentalVMOptions`.

Ví dụ về dạng cấu hình build:

~~~text
-H:+UnlockExperimentalVMOptions
-H:+RuntimeClassLoading
-H:-UnlockExperimentalVMOptions
~~~

Đây là tính năng **experimental**, không phải chế độ mặc định của Native Image. Các giới hạn được tài liệu nêu có thể gồm:

- Không hỗ trợ parallel class loading.
- Cần chú ý class loader và tên class vì một class loader không thể định nghĩa lại cùng binary name.
- Class được nạp động có thể tham chiếu tới class build-time mà một số method hoặc field đã bị loại khỏi image; có thể cần cấu hình bảo toàn package/type.
- Có thể làm tăng kích thước image và mức sử dụng bộ nhớ.
- Không kết hợp được với predefined classes trong các cấu hình được tài liệu mô tả.
- Cần kiểm tra thêm theo API, class loader và thư viện cụ thể; bật cờ không bảo đảm mọi framework dynamic đều hoạt động.

Chỉ cân nhắc tính năng này khi ứng dụng thực sự cần định nghĩa class sau khi khởi động và không thể chuyển sang build-time generation hoặc kiến trúc tĩnh. Trước khi dùng production, kiểm tra tính năng có trong bản GraalVM được pin, chính sách hỗ trợ của nhà cung cấp, các giới hạn và kết quả kiểm thử của chính thư viện.

## 14. Khi nào nên dùng decorator thay cho proxy sinh động?

Nếu chỉ cần thêm logging, metrics, validation hoặc kiểm tra quyền trước/sau một lời gọi, một decorator tĩnh có thể đáp ứng mà không cần sinh bytecode:

~~~java
public interface PaymentOperations {
    Receipt charge(String orderId);
}

final class DefaultPaymentOperations implements PaymentOperations {

    @Override
    public Receipt charge(String orderId) {
        return new Receipt(orderId);
    }
}

final class AuditedPaymentOperations implements PaymentOperations {

    private final PaymentOperations delegate;

    AuditedPaymentOperations(PaymentOperations delegate) {
        this.delegate = delegate;
    }

    @Override
    public Receipt charge(String orderId) {
        // Ghi nhận trước khi gọi nghiệp vụ.
        Receipt receipt = delegate.charge(orderId);
        // Ghi nhận kết quả sau khi gọi nghiệp vụ.
        return receipt;
    }
}
~~~

Đăng ký qua Spring:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentOperations paymentOperations() {
        PaymentOperations target = new DefaultPaymentOperations();
        return new AuditedPaymentOperations(target);
    }
}
~~~

Ví dụ đơn giản hóa phần logging để tập trung vào cấu trúc. Trong dự án thật, có thể dùng decorator cho một số chức năng và vẫn dùng Spring AOP cho transaction/security ở những điểm được hỗ trợ.

Decorator có các ưu điểm:

- Class tồn tại từ build time, không cần class loader định nghĩa class mới.
- Dependency và hành vi có thể được kiểm tra bằng unit test.
- Không cần proxy metadata nếu không dùng reflection/proxy khác.
- Dễ nhìn thấy luồng gọi và thứ tự xử lý.
- Phù hợp khi số lớp bọc hữu hạn và không cần intercept mọi method tự động.

## 15. Những thư viện/framework cần kiểm tra kỹ

| Nhóm | Ví dụ | Câu hỏi cần đặt ra |
|---|---|---|
| DI/AOP | Spring AOP, AspectJ, CGLIB | Framework có AOT processor để tạo proxy trước không? |
| Bytecode toolkit | Byte Buddy, Javassist, ASM | Có thể chạy generator trong build và đóng gói class không? |
| ORM | Hibernate lazy proxies, enhancement | Phiên bản ORM có native integration và enhancement mode nào? |
| Mocking | Mockito và các mock maker | Test chạy trên JVM hay native? Mock maker có cần inline instrumentation không? |
| Serialization/RPC | Jackson, RPC stub generators | Class adapter được sinh ở build hay runtime? DTO/proxy hints có đầy đủ không? |
| Instrumentation/agent | Java agent, attach API, class transformer | Runtime native có hỗ trợ API và thao tác biến đổi đó không? |
| Scripting/plugin | Plugin classloader, script compiler | Có nạp bytecode mới từ bên ngoài sau khi image đã build không? |

Không thể kết luận toàn bộ thư viện trong một nhóm đều tương thích hoặc không tương thích. Cần kiểm tra đúng version, module, code path và cấu hình. Một ORM có thể dùng proxy cho một trường hợp nhưng cung cấp bytecode enhancement build-time cho trường hợp khác.

Đặc biệt, kiểm tra scope của native support: thư viện có thể hỗ trợ native cho ứng dụng production nhưng không hỗ trợ một mocking extension hoặc plugin tùy chọn.

## 16. Kiểm tra output Spring AOT và class proxy đã sinh

Sau khi chạy AOT, có thể xem generated classes:

~~~bash
# Gradle
./gradlew processAot
Get-ChildItem -Recurse build/generated/aotClasses

# Maven
./mvnw spring-boot:process-aot
Get-ChildItem -Recurse target/spring-aot/main/classes
~~~

Lệnh `Get-ChildItem` là PowerShell; trên Linux/macOS có thể dùng `find`. Đường dẫn output phụ thuộc phiên bản Spring Boot và cấu hình build.

Nếu muốn xem class file cụ thể, dùng `javap`:

~~~bash
javap -classpath build/generated/aotClasses -p com.example.generated.SomeProxy
~~~

Thay tên package/class bằng class thực tế. `javap` giúp quan sát superclass, interface, method và bytecode signature; nó không chứng minh mọi đường đi runtime đã được đưa vào image.

Có thể kiểm tra thêm:

- Class proxy có trong output AOT chưa?
- Bean definition có tham chiếu đúng class hoặc supplier không?
- Các interface của JDK proxy có được đăng ký không?
- Class generated có phụ thuộc helper class nào chưa được đóng gói?
- Code advice/interceptor có sử dụng reflection hoặc resource cần hints riêng không?

## 17. Quy trình chẩn đoán lỗi proxy hoặc bytecode generation

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `UnsupportedFeatureError` khi gọi `defineClass` | Thư viện đang định nghĩa class mới ở runtime | Chuyển generator sang build time, thay proxy hoặc đánh giá tính năng experimental |
| `ClassNotFoundException` với tên proxy sinh động | Class chưa có trong image hoặc predefined class không khớp | Kiểm tra output build, classpath, bytecode và metadata |
| `MissingReflectionRegistrationError` trong proxy | Proxy/interceptor dùng reflection chưa có hints | Đăng ký member cần thiết, không nhầm với class generation |
| `IllegalArgumentException` khi tạo JDK proxy | Interface list không hợp lệ hoặc metadata không khớp | Kiểm tra interface, thứ tự và class loader |
| CGLIB báo không thể subclass class | Class `final`, constructor/visibility hoặc method không thể override | Dùng interface proxy hoặc thay đổi thiết kế target |
| AOP advice không chạy trên native | Proxy không được tạo, method không đi qua proxy hoặc self-invocation | Kiểm tra AOT output, loại proxy và luồng gọi |
| Class generated có trên disk nhưng native không thấy | Generated output chưa nằm trong classpath khi AOT/native build | Sửa task dependency và source set |
| Chạy JVM được nhưng native build fail | Dynamic generation/instrumentation không được hỗ trợ hoặc thiếu metadata | Xác định API tạo class, chọn cách tích hợp khác |
| Native chạy nhưng một plugin proxy lỗi | Test chưa bao phủ tập interface/nhánh tạo proxy | Mở rộng test và hint theo từng trường hợp |

Khi debug, hãy tìm stack trace tới API thực sự tạo class: `Proxy.newProxyInstance`, `ClassLoader.defineClass`, `Lookup.defineClass`, `Enhancer`, `ByteBuddy`, `CtClass.toClass` hoặc API instrumentation. Tên lỗi ở tầng Spring đôi khi chỉ là wrapper cho nguyên nhân ở thư viện thấp hơn.

## 18. Thực hành: thay runtime proxy bằng proxy có thể chuẩn bị trước

Giả sử một ứng dụng thanh toán dùng thư viện tạo subclass `PaymentServiceProxy` khi runtime để ghi metrics.

### Bước 1 — Xác định yêu cầu

Ghi lại:

- Class/interface nào được proxy.
- Method nào cần intercept.
- Tập target có cố định trong ứng dụng không.
- Proxy class có phụ thuộc cấu hình runtime hay dữ liệu tenant không.
- Thư viện có cung cấp AOT plugin hoặc native integration không.

### Bước 2 — Chọn phương án

Nếu service có interface và tập interface cố định, thử JDK proxy. Nếu Spring AOP có thể quản lý proxy, để Spring AOT chuẩn bị proxy theo cấu hình đã biết. Nếu cần subclass cụ thể, chuyển generator sang build task và đóng gói class.

### Bước 3 — Đưa generated output vào AOT

Bảo đảm task generator chạy trước `processAot`. Kiểm tra file `.class` xuất hiện trong output và có mặt trong classpath mà native compilation sử dụng.

### Bước 4 — Kiểm tra hints

Nếu proxy dùng reflection, đăng ký đúng constructor/method. Nếu dùng JDK proxy, đăng ký tập interface. Không thêm reflection hints để thay thế class file chưa được tạo.

### Bước 5 — Chạy native

~~~bash
./gradlew processAot
./gradlew nativeCompile
~~~

Khởi chạy executable và gọi tất cả method có advice. So sánh với kết quả JVM: logic nghiệp vụ, metrics, transaction, security và xử lý exception phải được bảo toàn.

### Bước 6 — Ghi lại lựa chọn

| Tiêu chí | Trước | Sau |
|---|---|---|
| Thời điểm sinh proxy | Runtime | Build time hoặc JDK proxy được chuẩn bị |
| Phụ thuộc class loader | Định nghĩa class mới lúc chạy | Class có sẵn trong image |
| Metadata | Không rõ/thiếu | Hint đúng phạm vi |
| Tính tương thích native | Có thể thất bại | Được kiểm thử trên executable |
| Thay đổi cấu hình | Có thể sinh proxy tùy ý | Giới hạn theo cấu hình build đã biết |

## 19. Checklist đánh giá một thư viện sinh bytecode

Trước khi chọn thư viện cho Spring Boot Native Image, hãy xác minh:

1. **Nó sinh bytecode lúc nào?** Build time, AOT time, startup runtime hay theo từng request?
2. **Nó định nghĩa class bằng API nào?** JDK Proxy, CGLIB, Byte Buddy, `defineClass`, Javassist, ASM hay instrumentation?
3. **Tập class có xác định không?** Tên class, interface, superclass và method có biết trước khi build?
4. **Thư viện có native/AOT integration không?** Tìm release notes, tài liệu, reachability metadata và sample native.
5. **Có thể pre-generate không?** Có Maven/Gradle plugin, annotation processor hoặc AOT extension?
6. **Có thể thay bằng interface/decorator không?** Nếu có, thiết kế tĩnh thường dễ kiểm soát hơn.
7. **Metadata có đúng loại không?** Reflection hint, JDK proxy hint và class bytecode là ba thứ khác nhau.
8. **Có giới hạn của GraalVM không?** Predefined classes/runtime class loading có thể experimental và có điều kiện.
9. **Đã test đúng đường đi chưa?** Build thành công chưa đủ; phải gọi method/proxy/plugin thật trên native executable.
10. **Phiên bản nào được hỗ trợ?** Ghi rõ Spring Boot, Spring Framework, GraalVM, JDK và thư viện sinh bytecode.

## 20. Ghi nhớ

Native Image có thể xử lý nhiều dạng reflection và JDK dynamic proxy khi tập đích được xác định hoặc có metadata phù hợp. Spring AOT còn có thể sinh bytecode proxy ở build time cho những trường hợp Spring hỗ trợ. Những cơ chế này cho phép giữ nhiều lợi ích của proxy/AOP mà không cần định nghĩa class mới trong lúc native application chạy.

Với thư viện sinh bytecode tùy ý, hãy ưu tiên tích hợp AOT hoặc chuyển generation sang build time, đưa class file vào classpath trước khi AOT/native compilation diễn ra. Nếu tập interface cố định, JDK proxy cùng proxy hints có thể là lựa chọn phù hợp. Nếu tập implementation hữu hạn, decorator hoặc registry tĩnh giúp giảm độ phức tạp.

Predefined classes và runtime class loading là các phương án đặc biệt có giới hạn, cần kiểm tra đúng phiên bản và không nên coi là thay thế tổng quát cho thiết kế tương thích native. **Reflection metadata không tạo class file mới**; luôn phân biệt yêu cầu truy cập class đã có với yêu cầu sinh class mới.

### Tài liệu tham khảo

- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot — Introducing GraalVM Native Images: https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html
- Spring Boot — Advanced Native Image Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- GraalVM — Reachability Metadata: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/
- GraalVM — Run-Time Class Loading (experimental): https://www.graalvm.org/dev/reference-manual/native-image/runtime-class-loading/

API và khả năng hỗ trợ phụ thuộc phiên bản. Khi áp dụng, hãy đối chiếu release notes và tài liệu của đúng Spring Boot, Spring Framework, GraalVM, JDK và thư viện bytecode generation được pin trong dự án.
