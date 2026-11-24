# Dependency dùng sinh bytecode hoặc tải lớp động ngoài khả năng hỗ trợ

## 1. Vì sao dependency chạy trên JVM nhưng lỗi trên Native Image?

Một số thư viện Java tạo class mới trong lúc ứng dụng chạy, định nghĩa class qua classloader hoặc tìm class theo tên từ cấu hình. Trên HotSpot JVM, các kỹ thuật này thường dựa vào khả năng nạp class và sinh bytecode động. GraalVM Native Image phân tích tập code có thể truy cập ở build time và tạo executable cho tập đó. Runtime không có toàn bộ khả năng compiler/classloader linh hoạt như JVM truyền thống.

Vì vậy, một dependency có thể hoạt động bình thường khi chạy JAR nhưng lỗi khi chạy native executable. Các trường hợp thường gặp gồm proxy/code generation, bytecode enhancement, plugin loading, script engine, classpath scanning và tên class chỉ biết lúc runtime.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần phân biệt rõ cơ chế nào được Spring AOT hoặc Native Image hỗ trợ, cơ chế nào cần metadata, và cơ chế nào thực sự phụ thuộc vào việc tạo/nạp class tùy ý sau khi build. Bài này hướng dẫn nhận diện dependency, đọc lỗi, tìm native support chính thức, chọn thiết kế thay thế và kiểm thử trên executable native.

## 2. Phân biệt reflection, proxy và runtime bytecode generation

Ba cơ chế thường bị gọi chung là “dynamic” nhưng yêu cầu khác nhau:

| Cơ chế | Ví dụ | Vấn đề native thường gặp |
|---|---|---|
| Reflection | `Class.forName`, `Method.invoke`, constructor lookup | Type/member cần được reachability metadata mô tả |
| Dynamic proxy | `Proxy.newProxyInstance` hoặc framework proxy | Tổ hợp interface cần được biết và đăng ký trước trong các trường hợp yêu cầu |
| Bytecode generation | ASM, Byte Buddy, CGLIB, Javassist | Tạo class bytecode mới khi process chạy có thể không được hỗ trợ như JVM |
| Dynamic class loading | `URLClassLoader`, plugin JAR, `defineClass` | Class/resource không nằm trong build-time universe có thể không được nạp |
| Script/eval | Engine biên dịch script thành class/bytecode | Engine có thể phụ thuộc compiler hoặc class definition runtime |
| Classpath scanning | Quét package/JAR để tìm implementation | Tập class không được biết hoặc resource metadata không đầy đủ |

Reflection và proxy có các cơ chế hỗ trợ Native Image cụ thể. Không nên kết luận rằng mọi API có chữ “dynamic” đều không dùng được. Ngược lại, thêm reflection hints cũng không biến một runtime bytecode compiler tùy ý thành khả năng được hỗ trợ.

## 3. Native Image hoạt động theo mô hình closed-world

Native Image phân tích reachable code và dữ liệu tại build time. Các class và đường truy cập cần thiết phải được compiler biết đến qua code tĩnh, Spring AOT, metadata hoặc cơ chế hỗ trợ của framework.

Điều này có nghĩa:
- Class đã nằm trên classpath build có thể được đưa vào executable nếu reachable và được mô tả đúng.
- Reflection trên class đã biết có thể hoạt động khi type/member hints đầy đủ.
- Dynamic proxy có thể được hỗ trợ khi interface set được biết trước và metadata tương ứng được cung cấp.
- Class mới được tải từ plugin JAR xuất hiện sau khi executable đã build không tự động nằm trong image.
- Bytecode được tạo tùy ý lúc runtime không thể mặc nhiên được compiler phân tích trước.

Closed-world không có nghĩa mọi tên class phải được hard-code thủ công. Spring AOT, library reachability metadata và Native Image tracing có thể cung cấp nhiều thông tin tự động. Nhưng những cơ chế tạo code/class mới ở runtime cần được đánh giá riêng.

## 4. Nhận diện dependency sinh bytecode

Tìm các thư viện hoặc API có khả năng tạo class động:

- CGLIB và Spring AOP class-based proxy.
- Byte Buddy.
- ASM.
- Javassist.
- Hibernate bytecode enhancement/proxy.
- Mocking framework tạo subclass/proxy.
- Serialization/mapper framework có code generation runtime.
- Expression/script engine biên dịch code lúc chạy.
- Dependency injection hoặc RPC framework tự tạo stub.
- Plugin framework nạp module/JAR ngoài classpath build.

Có thể tìm dependency trong Maven/Gradle graph và source usages. Tuy nhiên, tên dependency chưa đủ để kết luận có vấn đề. Một thư viện có thể cung cấp chế độ AOT/pre-generated implementation hoặc chỉ dùng bytecode generation ở JVM test scope.

Phân loại theo đường đi production thực sự: class nào được tạo, thời điểm tạo, API nào tạo class và feature nào gọi nó.

## 5. CGLIB và Spring AOP

Spring AOP có thể dùng JDK dynamic proxy hoặc class-based proxy. JDK proxy dựa trên interface; class-based proxy thường liên quan CGLIB/subclass generation.

Ví dụ cấu hình class-based proxy:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
@Configuration
class AopConfiguration {
}
```

Trong native application, Spring AOT có thể xử lý nhiều proxy cần thiết cho bean graph đã biết. Tuy nhiên, không thể giả định mọi proxy tùy ý được tạo theo dữ liệu runtime đều đã được chuẩn bị.

Khi lỗi:
1. Xác định proxy là JDK interface proxy hay class-based proxy.
2. Kiểm tra bean và advisor có được phát hiện trong AOT context không.
3. Xác minh Spring Framework/Spring Boot version có native support cho đường proxy đó.
4. Kiểm tra class/interface final, constructor và method visibility.
5. Chạy native integration test gọi method qua proxy thật.

Không thêm JDK proxy hints để sửa lỗi CGLIB subclass generation; hai cơ chế khác nhau.

## 6. Byte Buddy, ASM và Javassist

Byte Buddy, ASM và Javassist là các công cụ thao tác bytecode. Trên JVM, ứng dụng có thể tạo byte array đại diện class mới, sau đó định nghĩa class qua classloader. Một số chế độ Native Image không hỗ trợ việc định nghĩa class tùy ý theo cách HotSpot thực hiện.

Cần xem xét cách dependency sử dụng thư viện:
- Chỉ đọc/viết bytecode trong build plugin?
- Sinh code trước khi biên dịch native?
- Tạo class khi test chạy?
- Tạo class mới trong production request path?
- Dùng agent/instrumentation attach vào JVM?
- Định nghĩa class từ byte array bằng custom classloader?

Nếu code generation diễn ra ở build time, generated classes có thể được compile và đưa vào native build như class thông thường. Nếu generation chỉ diễn ra lúc runtime, cần kiểm tra Native Image có hỗ trợ chính xác API/feature đó hay không; không suy ra từ việc thư viện compile được.

## 7. ClassLoader và plugin architecture

Ứng dụng plugin thường tải JAR hoặc class từ vị trí bên ngoài:

```java
URLClassLoader loader = new URLClassLoader(
        pluginUrls,
        getClass().getClassLoader());

Class<?> pluginType =
        loader.loadClass(configuredClassName);
```

Trên JVM, cách này có thể nạp plugin mới sau khi process khởi động. Với Native Image, plugin class không nằm trong build-time universe không tự xuất hiện trong executable. Việc thêm JAR vào filesystem sau build không làm Native Image compiler phân tích và đưa class đó vào binary.

Nếu plugin set cố định, có thể đưa tất cả implementation vào build classpath và chọn implementation bằng registry/factory tĩnh. Nếu plugin phải được cài đặt độc lập sau khi phát hành, cần xem xét giữ module đó chạy trên JVM hoặc tách thành service/process riêng có runtime phù hợp.

Không hứa hẹn khả năng “drop-in plugin JAR” chỉ bằng cách thêm reflection hints. Hints mô tả truy cập tới class đã có trong image; chúng không đóng gói code tùy ý xuất hiện sau build.

## 8. Class.forName với tên class từ cấu hình

Đoạn code sau có thể gây lỗi native nếu tên class chỉ biết lúc runtime:

```java
String implementation =
        environment.getRequiredProperty("handler.class");

Class<?> type = Class.forName(implementation);
Object handler = type.getDeclaredConstructor().newInstance();
```

Nếu danh sách implementation là hữu hạn và biết ở build time, các lựa chọn nên được mô hình hóa rõ:

```java
@Component
class HandlerRegistry {

    private final Map<String, OrderHandler> handlers;

    HandlerRegistry(List<OrderHandler> discoveredHandlers) {
        this.handlers = discoveredHandlers.stream()
                .collect(Collectors.toUnmodifiableMap(
                        OrderHandler::name,
                        Function.identity()));
    }

    OrderHandler get(String name) {
        OrderHandler handler = handlers.get(name);
        if (handler == null) {
            throw new IllegalArgumentException(
                    "Unknown handler: " + name);
        }
        return handler;
    }
}
```

Spring có thể phát hiện bean implementation trong AOT context và registry chọn bean theo key lúc runtime. Tập implementation đã biết trước, còn lựa chọn cấu hình có thể thay đổi mà không cần nạp class mới.

Nếu thật sự cần reflection theo tên class, đăng ký type/member metadata cho toàn bộ tập class hợp lệ và xác minh AOT/native path. Không nhận tên class tùy ý từ request hoặc config không được kiểm soát.

## 9. Phân biệt class reachability với class definition

Đây là điểm quan trọng khi xử lý lỗi:

- **Reachability:** class đã có trong build inputs và compiler cần giữ lại.
- **Reflection metadata:** mô tả cách truy cập type/member đã biết theo reflection.
- **Proxy metadata:** mô tả tổ hợp interface cần cho proxy được hỗ trợ.
- **Class definition:** tạo một class mới từ bytecode trong lúc runtime.
- **Class loading:** tìm và nạp class từ nguồn có thể xuất hiện sau build.

Reachability metadata không tự biến bytecode mới thành reachable class. Reflection hints cũng không tương đương khả năng chạy một compiler Java/bytecode tùy ý trong native process.

Khi thấy lỗi `ClassNotFoundException`, `NoClassDefFoundError`, `UnsupportedFeatureError` hoặc lỗi define class, xác định nó thuộc nhóm nào trước khi thay metadata.

## 10. Script engine và eval

Một số ứng dụng cho phép người dùng hoặc quản trị viên cung cấp script. Engine có thể parse, compile hoặc sinh bytecode trong runtime.

Cần phân biệt:
- Engine chỉ diễn giải AST/interpreter thuần.
- Engine compile script thành JVM bytecode.
- Engine dùng classloader để nạp generated classes.
- Engine chạy trên runtime riêng như GraalVM Polyglot.
- Engine phụ thuộc native libraries hoặc external runtime.

Không mặc định mọi JavaScript/Groovy/Kotlin scripting engine đều hoạt động giống nhau trong Native Image. Ví dụ, việc một engine chạy trên HotSpot không chứng minh compiler/runtime mode của engine đó có thể được đóng gói native.

Nếu script set hữu hạn và biết trước, cân nhắc compile script thành artifact ở build time. Nếu script phải thay đổi tùy ý sau deploy, kiểm tra engine có native-compatible interpreter/runtime được hỗ trợ; nếu không, tách execution sang JVM hoặc service chuyên biệt.

## 11. Hibernate enhancement và proxy

Hibernate có các cơ chế proxy/lazy loading và bytecode enhancement. Cách dùng phụ thuộc Hibernate version, build-time enhancement plugin, runtime provider và cấu hình entity.

Phân biệt:
- Build-time enhancement: class được biến đổi trước khi Native Image compilation.
- Runtime proxy generation: class proxy được tạo khi process chạy.
- Lazy association: provider có thể dùng proxy/interceptor để trì hoãn load.
- Entity materialization: tạo entity từ dữ liệu qua constructor/property access.

Spring Boot/Hibernate có các mức hỗ trợ Native Image theo phiên bản; cần dùng tài liệu tương ứng. Nếu lỗi xảy ra ở lazy proxy, không kết luận mọi Hibernate đều không hỗ trợ. Xác minh provider version, enhancement mode, proxy strategy và native test trên association thực tế.

Một lựa chọn thiết kế là tránh lazy loading ngoài transaction và dùng projection/query rõ ràng ở API boundary. Điều này cải thiện cả tính dự đoán của data access lẫn khả năng tương thích native.

## 12. Mocking và bytecode generation chỉ trong test scope

Mocking framework có thể tạo subclass/proxy runtime. Test chạy trên JVM có thể hoạt động dù production executable không dùng framework đó. Không nên đưa test-only dependency vào native application chỉ để xử lý mock.

Nếu native test executable cần framework mocking, xác minh native support riêng của framework/version. Có thể thay mock động bằng fake implementation tĩnh cho test hoặc kiểm tra production behavior qua black-box integration test.

Phân biệt:
- Dependency chỉ có trong test scope.
- Dependency được đóng gói production.
- Test code được đưa vào native test executable.
- Production code path tạo proxy/bytecode lúc runtime.

Một native test fail do mocking framework không nhất thiết chứng minh production application fail. Nhưng nếu production dependency cũng sinh bytecode, cần test đúng đường đó.

## 13. Build-time code generation là hướng thay thế thường phù hợp

Nếu tập code cần tạo được biết trước, chuyển generation sang build time:

1. Đọc schema/configuration trong build.
2. Sinh Java source hoặc class files.
3. Compile generated output cùng application.
4. Để Spring AOT phân tích ApplicationContext.
5. Build Native Image từ generated classes và metadata.
6. Test executable với cùng contract.

Ví dụ OpenAPI/protobuf/mapper generator thường tạo source trong build lifecycle. Generated source trở thành code bình thường để compiler phân tích, khác với việc sinh class mới từ request trong production.

Đảm bảo generated output là deterministic, được lưu trong build artifact hoặc có thể tái sinh từ source/schema đã version hóa. Không chỉnh trực tiếp file generated nếu build tool sẽ ghi đè.

## 14. Chọn registry/factory thay cho nạp plugin tùy ý

Nếu implementation set cố định, registry là thiết kế dễ phân tích:

```java
interface PaymentProcessor {
    String provider();
    PaymentResult process(PaymentCommand command);
}

@Component
class PaymentProcessorRegistry {

    private final Map<String, PaymentProcessor> processors;

    PaymentProcessorRegistry(List<PaymentProcessor> processors) {
        this.processors = processors.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentProcessor::provider,
                        Function.identity()));
    }

    PaymentProcessor get(String provider) {
        PaymentProcessor result = processors.get(provider);
        if (result == null) {
            throw new IllegalArgumentException(
                    "Unsupported provider: " + provider);
        }
        return result;
    }
}
```

Spring AOT nhìn thấy các bean implementation được đăng ký trong context. Runtime chỉ chọn một bean từ registry; không cần load class từ tên tùy ý.

Nếu provider cần được thêm độc lập sau khi deploy, registry tĩnh không đáp ứng yêu cầu đó. Khi ấy cần kiến trúc plugin/service riêng hoặc giữ phần mở rộng trên JVM. Hãy lựa chọn theo yêu cầu sản phẩm thay vì cố ép Native Image vào mô hình runtime class loading không được hỗ trợ.

## 15. Kiểm tra native support của dependency

Trước khi thêm workaround, tìm hiểu:
- Dependency version có tài liệu Native Image không.
- Có reachability metadata chính thức hoặc repository metadata không.
- Spring Boot/Spring Data starter có AOT contribution không.
- Dependency dùng reflection hay runtime bytecode generation.
- Có chế độ build-time generation/precompiled proxy không.
- Có issue/limitation đã biết cho đúng version/architecture không.
- License/edition có điều kiện riêng không.

Ưu tiên metadata do thư viện/vendor cung cấp và tích hợp theo cơ chế Native Image được hỗ trợ. Không copy file reflect-config/proxy-config từ một version khác nếu chưa kiểm tra API, class names và runtime behavior.

Một dependency có thể hỗ trợ Native Image một phần. Hãy xác định feature cụ thể mà ứng dụng sử dụng thay vì đánh giá toàn bộ thư viện chỉ bằng một nhãn “compatible”.

## 16. Dùng tracing agent để phát hiện truy cập động — đúng phạm vi

Native Image tracing agent có thể quan sát một số hoạt động như reflection, resource, proxy và serialization trong các lần chạy JVM, rồi tạo metadata gợi ý. Agent hữu ích khi dependency truy cập động tới class/member đã tồn tại trong classpath.

Tuy nhiên, tracing agent không giải quyết mọi runtime code generation:
- Nó không biến class plugin xuất hiện sau build thành class có sẵn trong image.
- Nó không bảo đảm mọi nhánh logic đã được thực thi trong quá trình trace.
- Nó không tự chứng minh API defineClass hoặc instrumentation được Native Image hỗ trợ.
- Nó có thể tạo metadata quá rộng nếu workload trace không được kiểm soát.

Dùng agent để phát hiện metadata access thiếu, sau đó review file được tạo và viết tests. Nếu lỗi là dependency tạo bytecode mới lúc runtime, cần tìm chế độ AOT/pre-generation hoặc thay đổi kiến trúc, không chỉ chạy agent thêm lần nữa.

## 17. Đọc lỗi native để tìm dependency gây ra vấn đề

Một số dấu hiệu:

| Lỗi | Hướng điều tra |
|---|---|
| `ClassNotFoundException` | Tên class có nằm trong build classpath/image không? Có đang tải plugin JAR ngoài không? |
| `NoClassDefFoundError` | Dependency/class bị thiếu, initialization fail hoặc reachability issue? |
| `UnsupportedFeatureError` | Native Image chặn API/feature nào? Đọc stack trace và version docs |
| Lỗi `defineClass` | Dependency có đang tạo class runtime từ bytecode không? |
| Lỗi CGLIB/Byte Buddy/ASM | Proxy/code generation mode nào được gọi và ở thời điểm nào? |
| Proxy interface error | Interface combination có được biết/đăng ký đúng không? |
| Script compilation error | Engine có yêu cầu JVM compiler/classloader không? |
| Plugin load failure | Plugin có nằm trong image lúc build hay chỉ xuất hiện sau deploy? |

Lấy stack trace đầy đủ và xác định frame đầu tiên thuộc dependency. Ghi dependency coordinates/version và feature đang được gọi. Không thêm hints trước khi biết lỗi là reflection, proxy, class loading hay bytecode definition.

## 18. Quy trình xử lý theo mức độ can thiệp

Đi theo thứ tự:

1. **Nâng cấp dependency** lên version có Native Image support chính thức nếu phù hợp.
2. **Bật chế độ AOT/pre-generated** mà dependency cung cấp.
3. **Sinh code tại build time** nếu input/schema có thể biết trước.
4. **Đăng ký metadata** cho reflection/resource/proxy trên class đã biết.
5. **Thay runtime discovery** bằng registry/factory tĩnh khi tập implementation hữu hạn.
6. **Tách thành JVM service/process** nếu yêu cầu thật sự là nạp plugin hoặc bytecode tùy ý sau deploy.
7. **Giữ module trên JVM** nếu dependency cốt lõi chưa có phương án native tương thích.

Sau mỗi thay đổi, chạy JVM regression, Spring AOT, native build và native integration test cho đúng feature. Không thay đổi nhiều lớp cùng lúc vì khó xác định nguyên nhân.

## 19. Chẩn đoán và xử lý theo ví dụ

| Tình huống | Kết luận ban đầu | Hướng xử lý |
|---|---|---|
| Jackson reflection thiếu constructor | Metadata access tới class đã biết | Dùng support/hints phù hợp và test payload |
| Spring AOP proxy fail | Có thể sai proxy type hoặc AOT discovery | Kiểm tra JDK/CGLIB proxy và Spring version |
| Plugin JAR mount sau deploy không load | Class không nằm trong build-time image | Prepackage plugin hoặc chạy plugin trên JVM |
| Byte Buddy define class lúc request | Runtime bytecode generation | Tìm AOT mode hoặc thay thiết kế |
| Hibernate lazy proxy lỗi | Provider/proxy/enhancement compatibility | Kiểm tra Hibernate support và association test |
| Mock test fail native | Test framework code generation | Fake/black-box test hoặc native support của test framework |
| Script engine compile source runtime | Engine cần compiler/classloader | Interpreter/native runtime được hỗ trợ hoặc tách JVM |

Các kết luận trên là hướng phân loại, không phải chẩn đoán tự động. Luôn dựa vào stack trace, dependency version và test có thể tái hiện.

## 20. Bài thực hành: thay plugin class loading bằng implementation registry

**Bối cảnh:** Order API đọc tên class processor từ property rồi dùng `Class.forName` để tạo processor. JAR JVM chạy được, nhưng native executable lỗi khi khởi động hoặc xử lý request.

**Bước 1 — Xác định implementation.** Liệt kê các processor production được hỗ trợ và nơi chúng được khai báo.

**Bước 2 — Kiểm tra dependency path.** Xem class được tạo bằng reflection, CGLIB, Byte Buddy hay custom classloader; xác định thời điểm tạo.

**Bước 3 — Thiết kế registry.** Đăng ký processor thành Spring beans hoặc factory implementations có type rõ ràng.

**Bước 4 — Cố định build structure.** Bảo đảm tất cả implementation hợp lệ nằm trong classpath và ApplicationContext khi AOT chạy.

**Bước 5 — Giữ runtime selection.** Chọn processor bằng key/property đã validate, không load tên class tùy ý.

**Bước 6 — Chạy JVM tests.** Kiểm tra từng provider, provider không tồn tại và default behavior.

**Bước 7 — Chạy AOT/native.** Xác nhận bean graph, generated context và native executable xử lý các provider được hỗ trợ.

**Bước 8 — Kiểm tra yêu cầu plugin thật sự.** Nếu sản phẩm bắt buộc cài plugin JAR sau deploy, đánh giá tách plugin host thành JVM process/service thay vì giả định registry đáp ứng yêu cầu đó.

Tiêu chí hoàn thành: dependency gây dynamic behavior được xác định; đường code generation/class loading được phân loại; lựa chọn native support hoặc thay thế được kiểm chứng; native executable chạy được các implementation đã cam kết hỗ trợ; giới hạn plugin/runtime extension được ghi rõ.

## 21. Kết luận

Dependency dùng sinh bytecode hoặc tải class động có thể chạy tốt trên HotSpot nhưng không phù hợp với mô hình build-time reachability của Native Image. Cần phân biệt reflection, proxy, runtime class definition và plugin loading: metadata có thể mô tả truy cập tới class đã biết, nhưng không tự đóng gói class mới xuất hiện sau build hoặc cung cấp một JVM bytecode compiler đầy đủ trong executable.

Hãy tìm đúng API và dependency gây lỗi, kiểm tra Native Image support theo version, ưu tiên AOT/pre-generated code và registry tĩnh khi implementation set hữu hạn. Nếu yêu cầu sản phẩm thực sự cần nạp plugin hoặc sinh bytecode tùy ý sau deploy, giữ phần đó trong JVM hoặc tách thành process/service riêng. Quyết định phải được xác nhận bằng native build và test trên chính đường code production.
