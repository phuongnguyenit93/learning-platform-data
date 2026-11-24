# Những lời gọi reflection mà GraalVM có thể hoặc không thể suy ra

Java Reflection cho phép chương trình tìm class, constructor, method, field và gọi chúng khi chạy. Cơ chế này hữu ích với framework, dependency injection, serializer, plugin và thư viện mở rộng. Trên JVM thông thường, ứng dụng có thể nạp class từ tên chuỗi và truy cập thành viên mà không cần biết tất cả đích cụ thể khi biên dịch.

**GraalVM Native Image** hoạt động theo mô hình phân tích tĩnh ở build time. Compiler phải xác định trước những class và thành viên nào có thể được sử dụng để đưa mã máy cùng metadata cần thiết vào executable. Vì thế, một số lời gọi reflection có thể được suy ra khi đích truy cập rõ ràng từ mã; những lời gọi phụ thuộc dữ liệu chỉ biết lúc runtime thường cần reachability metadata.

Điểm quan trọng không phải là “Native Image không hỗ trợ reflection”. Native Image hỗ trợ reflection, nhưng **không thể tự đoán mọi đích reflection được chọn từ dữ liệu runtime**. Bài học này giúp phân biệt hai trường hợp, đọc các dấu hiệu của mã có thể phân tích tĩnh, bổ sung metadata đúng phạm vi và kiểm thử những đường đi động trong ứng dụng Spring Boot.

## 1. Vì sao reflection cần được mô tả trước?

Một lời gọi trực tiếp như:

~~~java
CsvExporter exporter = new CsvExporter();
exporter.export(report);
~~~

cho compiler thấy rõ class và method được sử dụng. Đường gọi có thể được lần theo từ bytecode và đưa vào đồ thị reachability.

Trong khi đó:

~~~java
String className = configuration.getProperty("report.exporter");
Class<?> type = Class.forName(className);
Object exporter = type.getDeclaredConstructor().newInstance();
~~~

để tên class được quyết định bởi cấu hình. Giá trị có thể là com.example.CsvExporter trong môi trường này nhưng là com.example.XmlExporter trong môi trường khác. Nếu chỉ dựa trên mã tĩnh, compiler không thể biết đầy đủ tập tên có thể xuất hiện.

Trên JVM, class loader có thể nạp class khi tên được cung cấp ở runtime, miễn là class có trên classpath và điều kiện nạp phù hợp. Với Native Image, các class và metadata cần thiết phải được chuẩn bị trong executable từ trước. Nếu không có thông tin đó, một đường đi chạy được trên JVM có thể thất bại trong native executable.

~~~mermaid
flowchart TD
    A["Lời gọi reflection trong bytecode"] --> B{"Đích và đối số có xác định ở build time?"}
    B -->|Có, theo mẫu API được hỗ trợ| C["Phân tích tĩnh có thể suy ra phần tử đích"]
    B -->|Không, phụ thuộc dữ liệu runtime| D["Compiler không biết đầy đủ đích"]
    C --> E["Đưa phần tử cần thiết vào image"]
    D --> F["Cần reachability metadata hoặc thiết kế lại"]
    F --> G["RuntimeHints / JSON / metadata từ agent"]
    G --> E
    E --> H["Native executable"]
~~~

**Reachability metadata** mô tả các thành phần được truy cập động mà phân tích tĩnh không thể xác định chắc chắn. Với reflection, metadata có thể khai báo class, constructor, method hoặc field cần truy cập; tùy mục đích, khai báo chỉ cho phép introspection hoặc cho phép invocation/truy cập giá trị.

## 2. Native Image có thể suy ra những lời gọi nào?

GraalVM có cơ chế nhận diện một số API reflection tiêu chuẩn, đặc biệt các lời gọi trên java.lang.Class. Khi **đối số có thể được rút gọn thành hằng số ở build time** và phần tử đích tồn tại trên classpath, phân tích có thể xác định phần tử được truy cập.

Các dạng API tiêu biểu được tài liệu GraalVM mô tả gồm:

- Class.forName(...) với tên class có thể xác định.
- Class.getField(String) và Class.getDeclaredField(String).
- Class.getMethod(String, Class[]) và Class.getDeclaredMethod(String, Class[]).
- Class.getConstructor(Class[]) và Class.getDeclaredConstructor(Class[]).
- Một số dạng truy cập class thông qua class loader hoặc MethodHandles.Lookup, theo các quy tắc metadata của phiên bản GraalVM.

Ví dụ:

~~~java
Class<?> type = Class.forName("java.lang.Integer");

Method method = Integer.class.getDeclaredMethod(
    "bitCount",
    int.class
);

Constructor<String> constructor =
    String.class.getConstructor(String.class);
~~~

Tên class, tên method và kiểu tham số trong các lời gọi trên đều xác định từ mã. GraalVM có thể tính trước đích truy cập đối với những API và mẫu được hỗ trợ.

Tuy nhiên, **không nên suy rộng rằng mọi reflection có chuỗi hằng đều tự động hoàn tất**. Khả năng xử lý còn phụ thuộc API cụ thể, class có trong classpath hay không, các kiểu tham số có xác định hay không, quyền truy cập, phiên bản GraalVM và chế độ metadata. Một số thao tác truy vấn class/member vẫn cần đăng ký metadata theo quy tắc của phiên bản hoặc chế độ kiểm tra nghiêm ngặt đang bật.

## 3. Đối số hằng số là gì?

Một đối số được xem là có thể xác định ở build time khi compiler chứng minh được giá trị của nó. Các trường hợp thường gặp:

- String literal, số literal hoặc class literal.
- Truy cập static field đã được khởi tạo ở build time.
- Biến effectively final mà giá trị có thể được chứng minh.
- Mảng có độ dài cố định và mọi phần tử đều xác định.
- Phép tính đơn giản từ các giá trị hằng, ví dụ nối hai chuỗi hằng.

Ví dụ tên class được tạo từ các chuỗi hằng:

~~~java
String packageName = "com.example.export.";
String simpleName = "CsvExporter";
String className = packageName + simpleName;

Class<?> type = Class.forName(className);
~~~

Compiler có thể rút gọn phép nối trên thành một tên xác định nếu toàn bộ giá trị đầu vào được chứng minh là hằng số.

Mảng kiểu tham số cũng có thể được phân tích khi độ dài và phần tử đều xác định:

~~~java
Class<?>[] parameterTypes = {
    String.class,
    int.class
};

Method method = ReportFormatter.class.getDeclaredMethod(
    "format",
    parameterTypes
);
~~~

Một số cách tạo và gán phần tử mảng theo các bước tuần tự cũng có thể được phân tích nếu compiler theo dõi chắc chắn mọi lần ghi trước khi mảng được truyền vào lời gọi reflection. Mảng lấy từ static field hoặc bị thay đổi qua các nhánh điều khiển phức tạp khó được chứng minh là hằng hơn. Đặc biệt, một mảng `static final` không đồng nghĩa nội dung bất biến: field không thể trỏ sang mảng khác nhưng các phần tử vẫn có thể bị ghi lại.

Không có cú pháp Java nào bảo đảm một giá trị trở thành hằng số đối với mọi phiên bản GraalVM. Hãy xem khả năng constant folding là một hỗ trợ phân tích, không phải hợp đồng ngôn ngữ để dựa vào cho mọi trường hợp.

## 4. Trường hợp có thể suy ra: class và member được chỉ rõ

Xét một ứng dụng có interface định dạng báo cáo:

~~~java
public interface ReportExporter {
    byte[] export(String reportId);
}

public final class CsvExporter implements ReportExporter {

    @Override
    public byte[] export(String reportId) {
        return ("report_id," + reportId).getBytes(StandardCharsets.UTF_8);
    }
}
~~~

Một đoạn reflection có đích cố định:

~~~java
Class<?> type = Class.forName("com.example.CsvExporter");
Constructor<?> constructor = type.getDeclaredConstructor();
Object instance = constructor.newInstance();

Method method = type.getMethod("export", String.class);
byte[] result = (byte[]) method.invoke(instance, "R-100");
~~~

Phân tích có thể suy ra class name, constructor không tham số, method export(String) và kiểu tham số nếu các đối số thực sự được chứng minh là hằng. Việc có thể suy ra lookup không có nghĩa mọi chế độ metadata của mọi phiên bản đều cho phép invocation mà không cần khai báo; hãy kiểm tra log và chạy native test.

Khi class, constructor và method đã xác định rõ, một thiết kế gọi trực tiếp thường còn đơn giản hơn:

~~~java
ReportExporter exporter = new CsvExporter();
byte[] result = exporter.export("R-100");
~~~

Nếu không có yêu cầu plugin hoặc framework bắt buộc dùng reflection, lời gọi trực tiếp giảm metadata cần duy trì và giúp compiler theo dõi đường gọi rõ ràng hơn.

## 5. Trường hợp khó suy ra: tên class lấy từ runtime

Ví dụ sau phụ thuộc vào cấu hình:

~~~java
public ReportExporter createExporter(Environment environment)
        throws ReflectiveOperationException {

    String className = environment.getProperty("report.exporter");
    Class<?> type = Class.forName(className);

    return (ReportExporter) type.getDeclaredConstructor()
        .newInstance();
}
~~~

Giá trị report.exporter có thể đến từ:

- Environment variable.
- application.yml hoặc application.properties được mount khi chạy.
- Config Server hoặc secret/configuration service.
- Bản ghi trong database.
- Request HTTP.
- Metadata tenant hoặc registry plugin.
- File được người vận hành thay đổi sau khi executable đã build.

Compiler không thể biết đầy đủ những giá trị này chỉ từ lời gọi Class.forName(className). Nếu muốn giữ kiến trúc reflection, phải khai báo tất cả class và thành viên mà ứng dụng có thể dùng trong image.

Ví dụ, nếu chỉ cho phép hai exporter:

~~~text
com.example.CsvExporter
com.example.XmlExporter
~~~

thì metadata cần bao phủ cả hai class, constructor và các method được gọi động. Nếu một class chỉ được thêm vào thư mục plugin sau khi image đã build, metadata không thể làm cho bytecode mới tự xuất hiện trong executable. Native Image yêu cầu class cần dùng đã có trong build input và được chuẩn bị phù hợp.

## 6. Reflection lookup và reflection invocation là hai nhu cầu khác nhau

Metadata reflection không chỉ trả lời “có thể tìm thấy method này không?”. Nó còn phân biệt việc **liệt kê/tra cứu** với việc **gọi method hoặc constructor**, cũng như đọc/ghi giá trị field.

| Thao tác | Ví dụ | Nhu cầu metadata |
|---|---|---|
| Lấy class theo tên | Class.forName(name) | Class phải được nhận diện/đăng ký nếu tên không thể suy ra |
| Tra cứu method | type.getDeclaredMethod(name, params) | Member cần được phép introspection theo quy tắc metadata |
| Gọi method | method.invoke(target, args) | Cần invocation metadata cho method tương ứng |
| Tra cứu constructor | type.getDeclaredConstructor(params) | Constructor cần được nhận diện/đăng ký |
| Tạo instance | constructor.newInstance(args) | Cần metadata cho phép invocation constructor |
| Tra cứu field | type.getDeclaredField(name) | Field cần được nhận diện/đăng ký |
| Đọc/ghi field | field.get(obj), field.set(obj, value) | Cần metadata cho phép truy cập giá trị field |

Một số định dạng metadata phân biệt queriedMethods/queryAllDeclaredMethods với methods/allDeclaredMethods, hoặc các chế độ tương đương trong schema mới. Phần query chỉ cung cấp thông tin để introspection; nó không tự cấp quyền gọi method bằng reflection.

Vì vậy, khi gặp lỗi ở Method.invoke hoặc Constructor.newInstance, chỉ đăng ký khả năng tìm method có thể chưa đủ. Phải xác định ứng dụng cần tra cứu, gọi method, tạo object hay truy cập giá trị field.

## 7. Ví dụ reachability metadata cho reflection động

Với GraalVM hiện hành, định dạng reachability metadata mới có thể được đặt trong META-INF/native-image/{groupId}/{artifactId}/reachability-metadata.json. Ví dụ minh họa:

~~~json
{
  "reflection": [
    {
      "type": "com.example.CsvExporter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "export",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    },
    {
      "type": "com.example.XmlExporter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "export",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

Metadata trên cho phép Native Image chuẩn bị constructor và method được nêu cho các class. Trong ứng dụng thực tế, hãy thu hẹp phạm vi tới đúng constructor/method cần thiết. Không bật allDeclaredMethods hoặc allDeclaredFields cho một thư viện lớn chỉ để thử cho hết lỗi.

Ở các phiên bản GraalVM cũ hơn, cấu hình reflection thường dùng reflect-config.json với schema dạng name, methods, fields và các cờ allDeclared.... Spring Boot/Spring AOT cũng có thể sinh các file cấu hình tương ứng trong output build. **Không trộn schema của reachability-metadata.json mới với schema reflect-config.json cũ**; hãy dùng đúng định dạng mà native-image toolchain của dự án hỗ trợ.

Một metadata entry có thể được đặt điều kiện theo type reachable để tránh đưa metadata vào image khi phần code liên quan không được sử dụng. Với schema mới, trường condition có thể dùng typeReached theo định nghĩa của phiên bản. Điều kiện giúp giảm metadata thừa và giữ image gọn hơn.

## 8. Đăng ký bằng Spring RuntimeHintsRegistrar

Trong ứng dụng Spring Boot, cách tích hợp gần với mã nguồn nhất thường là dùng RuntimeHintsRegistrar. Spring AOT thu thập các hint này và chuyển thành cấu hình mà GraalVM cần.

Ví dụ:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

public class ExporterRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            CsvExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.reflection().registerType(
            XmlExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ExporterRuntimeHints.class)
class ExporterNativeConfiguration {
}
~~~

Trong ví dụ, hai class exporter được biết khi build và constructor cùng public method cần invocation. Nếu chỉ cần introspection hoặc chỉ cần constructor, hãy chọn member category hẹp hơn. Các API category có thể thay đổi giữa phiên bản Spring Framework; ví dụ này dùng các category phổ biến trong Spring Framework 6.x.

Nếu exporter cần method không public, hãy xác định rõ method và quyền truy cập thực tế. Không tự động mở toàn bộ thành viên private chỉ vì một thư viện đang dùng reflection.

## 9. Dùng annotation cho các trường hợp phổ biến

Spring cung cấp annotation để diễn tả nhu cầu reflection ngay tại vị trí liên quan.

**@RegisterReflection** cho phép khai báo class và member category cần thiết:

Annotation `@RegisterReflection` có từ Spring Framework 6.2. Nếu dự án dùng Spring Framework cũ hơn, hãy dùng `RuntimeHintsRegistrar` hoặc API hint phù hợp với phiên bản đó.

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflection(
    classes = CsvExporter.class,
    memberCategories = {
        MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
        MemberCategory.INVOKE_PUBLIC_METHODS
    }
)
class ExporterConfiguration {
}
~~~

**@RegisterReflectionForBinding** phù hợp với kiểu dữ liệu cần binding/serialization, thường gặp khi Jackson xử lý DTO trong các API lập trình như WebClient hoặc RestClient mà Spring không thể suy ra từ signature controller.

`@RegisterReflectionForBinding` có từ Spring Framework 6.0 và đăng ký các constructor, field, property, record component cùng kiểu được tham chiếu cần thiết cho data binding. Nó không phải cách tổng quát để mở mọi method tùy ý của plugin.

~~~java
@Component
class ReportClient {

    @RegisterReflectionForBinding(ReportPayload.class)
    ReportPayload decode(String json) {
        // Gọi ObjectMapper hoặc client theo cấu hình ứng dụng.
        return objectMapper.readValue(json, ReportPayload.class);
    }
}
~~~

Ví dụ giả định objectMapper đã được inject và xử lý exception phù hợp. Annotation binding không thay thế metadata cho mọi method plugin tùy ý; nó nhắm tới nhu cầu introspection/binding của kiểu dữ liệu.

Với các controller nhận/trả DTO qua Spring MVC, Spring AOT thường có thể suy ra một số hint từ kiểu dữ liệu và signature. Nhưng khi kiểu chỉ xuất hiện trong một lời gọi client lập trình hoặc được chọn động, hãy kiểm tra và bổ sung hint khi cần.

## 10. Khi nào nên thay reflection bằng registry tĩnh?

Nếu tập plugin hữu hạn và biết trước, có thể tránh dùng tên class do người dùng cung cấp. Ví dụ:

~~~java
public enum ExportFormat {
    CSV,
    XML
}

@Component
class ExporterRegistry {

    private final Map<ExportFormat, Supplier<ReportExporter>> exporters =
        Map.of(
            ExportFormat.CSV, CsvExporter::new,
            ExportFormat.XML, XmlExporter::new
        );

    ReportExporter get(ExportFormat format) {
        Supplier<ReportExporter> supplier = exporters.get(format);
        if (supplier == null) {
            throw new IllegalArgumentException(
                "Unsupported export format: " + format
            );
        }
        return supplier.get();
    }
}
~~~

Các method reference CsvExporter::new và XmlExporter::new tạo đường gọi tĩnh rõ ràng. Compiler nhìn thấy các implementation và constructor được tham chiếu. Ứng dụng vẫn chọn format từ request/runtime nhưng việc lựa chọn diễn ra trên registry đã biết, không phải nạp tùy ý class từ chuỗi.

Ưu điểm:

- Không phải duy trì tên class trong cấu hình.
- Giảm metadata reflection và rủi ro thiếu đăng ký.
- Giới hạn rõ tập plugin được hỗ trợ.
- Dễ kiểm thử, phân quyền và kiểm soát đầu vào.
- Dễ phân tích reachability và loại bỏ implementation không dùng nếu không có đường gọi.

Nếu kiến trúc yêu cầu plugin do bên thứ ba cung cấp sau khi build, Native Image không thể đơn giản nạp một JAR tùy ý như JVM. Cần thay đổi kiến trúc, ví dụ tách plugin thành process/service riêng hoặc xác định tập plugin tại build và tạo image tương ứng.

## 11. Reflection trong các thư viện/framework phổ biến

Không phải mọi reflection đều do code ứng dụng gọi trực tiếp. Framework có thể dùng reflection bên trong:

- Jackson tìm constructor, record component, getter/setter hoặc field để serialize/deserialize.
- ORM tìm entity metadata, constructor và accessor.
- Dependency injection framework tìm annotation và injection point.
- Validation framework tìm constraint annotation và method.
- Logging, scripting hoặc plugin framework có thể dò class, method và resource theo tên.
- Thư viện mapping có thể tạo proxy hoặc class adapter động.

Spring AOT và các thư viện có reachability metadata có thể tự cung cấp phần lớn hint cần thiết. Tuy nhiên, các đường đi không tiêu chuẩn, API lập trình, DTO chỉ xuất hiện trong method body hoặc kiểu được chọn từ dữ liệu runtime có thể cần bổ sung.

Khi một thư viện đã cung cấp metadata trong artifact của nó, không nên sao chép thêm cấu hình trùng lặp vào ứng dụng nếu không có lý do. Trước hết kiểm tra phiên bản thư viện và reachability metadata đi kèm.

## 12. Tracing Agent: thu thập metadata từ các luồng chạy thật

GraalVM cung cấp Native Image Tracing Agent để quan sát các dynamic feature khi chạy ứng dụng trên JVM. Agent có thể ghi nhận các thao tác reflection, proxy, JNI, serialization và resource đã được thực thi.

Ví dụ chạy ứng dụng JVM với agent:

~~~bash
java -agentlib:native-image-agent=config-output-dir=target/native-agent-config -jar target/application.jar
~~~

Sau khi ứng dụng kết thúc, thư mục output có thể chứa các file cấu hình metadata. Có thể xem xét và đưa các entry cần thiết vào classpath build native theo cấu trúc được toolchain hỗ trợ.

Agent chỉ ghi nhận những đường đi đã thực sự chạy trong phiên quan sát. Nếu test chưa gọi format XML, chưa xử lý DTO đặc biệt hoặc chưa bật profile production, metadata cho những đường đi đó có thể không xuất hiện. Vì vậy:

1. Chạy test với nhiều input và cấu hình.
2. Bao phủ tất cả plugin, profile và nhánh nghiệp vụ được hỗ trợ.
3. Kiểm tra metadata agent sinh ra; loại bỏ entry không cần thiết.
4. Build native bằng metadata đã rà soát.
5. Chạy lại test native để phát hiện trường hợp còn thiếu.

**Metadata do agent sinh ra là dữ liệu quan sát, không phải bằng chứng bao phủ đầy đủ.** Không đưa nguyên bộ metadata khổng lồ vào production mà chưa kiểm tra nguồn gốc và phạm vi.

## 13. Chẩn đoán lỗi reflection khi chạy native

Một số dấu hiệu thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ClassNotFoundException với class name từ config | Class không có trong image hoặc tên runtime không thuộc tập đã đăng ký | Kiểm tra classpath, class name và reflection metadata |
| NoSuchMethodException chỉ trên native | Method/constructor không được đưa vào metadata hoặc signature sai | Xác nhận tên, kiểu tham số và member category |
| MissingReflectionRegistrationError | Dynamic access thiếu reachability metadata | Đọc stack trace và đăng ký đúng class/member |
| IllegalAccessException | Quyền truy cập Java hoặc module access không phù hợp | Kiểm tra visibility, package/module và thiết kế truy cập |
| Jackson deserialize thất bại trên native | DTO hoặc constructor/property cần binding hint | Dùng RegisterReflectionForBinding hoặc RuntimeHints |
| Plugin hoạt động trên JVM nhưng không chạy native | Tên class được chọn động hoặc plugin không có trong image | Đăng ký tập plugin tại build hoặc chuyển sang registry tĩnh |
| Method.invoke() lỗi dù getMethod() tìm được | Có metadata truy vấn nhưng chưa có metadata invocation | Đăng ký invocation cho đúng method signature |
| MethodHandles lookup thất bại | Thiếu metadata cho type/member được truy cập qua lookup | Kiểm tra metadata và API MethodHandles cụ thể |

Không nên bắt Throwable rồi bỏ qua lỗi thiếu đăng ký. Một số lỗi registration là Error để báo rằng image không chứa thông tin bắt buộc. Nuốt lỗi có thể khiến ứng dụng tiếp tục chạy ở trạng thái sai và làm test không phát hiện được thiếu metadata.

## 14. Kiểm tra metadata nghiêm ngặt trong GraalVM

Các phiên bản GraalVM mới cung cấp chế độ kiểm tra reachability metadata chính xác hơn. Có thể bật --exact-reachability-metadata khi build để phát hiện thiếu đăng ký sớm hơn. Một số phiên bản cho phép giới hạn theo package.

Khi chạy ứng dụng, các chế độ báo cáo missing registration có thể giúp quan sát lỗi:

~~~bash
# Báo cáo các vị trí thiếu đăng ký khi chạy test native
./application -XX:MissingRegistrationReportingMode=Warn
~~~

~~~bash
# Thoát ngay khi gặp missing registration trong các bài test
./application -XX:MissingRegistrationReportingMode=Exit
~~~

Các cờ này phụ thuộc phiên bản GraalVM Native Image. Hãy xác nhận qua tài liệu/toolchain đang dùng trước khi thêm vào pipeline. Chế độ Warn hữu ích khi khảo sát; chế độ Exit giúp test thất bại ngay cả khi code vô tình bắt Throwable và che mất lỗi.

Trong quá trình phát triển, có thể bật chế độ exact metadata cho package ứng dụng trước, sau đó mở rộng phạm vi. Không nhất thiết bật cho mọi dependency cùng lúc nếu việc chuyển đổi gây quá nhiều cảnh báo khó xử lý.

## 15. Bài thực hành: so sánh reflection hằng và reflection động

Mục tiêu: quan sát hai cách chọn exporter và xác định trường hợp nào cần metadata.

### Bước 1 — Tạo hai exporter

~~~java
public interface ReportExporter {
    byte[] export(String id);
}

public final class CsvExporter implements ReportExporter {
    public CsvExporter() {
    }

    @Override
    public byte[] export(String id) {
        return ("csv:" + id).getBytes(StandardCharsets.UTF_8);
    }
}

public final class XmlExporter implements ReportExporter {
    public XmlExporter() {
    }

    @Override
    public byte[] export(String id) {
        return ("<report>" + id + "</report>")
            .getBytes(StandardCharsets.UTF_8);
    }
}
~~~

### Bước 2 — Thử tên class hằng

~~~java
Class<?> type = Class.forName("com.example.CsvExporter");
Constructor<?> constructor = type.getDeclaredConstructor();
ReportExporter exporter =
    (ReportExporter) constructor.newInstance();
~~~

Build native và chạy thử. Quan sát log của GraalVM và kiểm tra hành vi theo phiên bản metadata đang dùng. Nếu compiler có thể xử lý các đối số hằng theo API được hỗ trợ, đích class/constructor sẽ được xác định tại build time.

### Bước 3 — Thử tên class từ property

~~~java
String className = environment.getProperty("report.exporter");
Class<?> type = Class.forName(className);
Constructor<?> constructor = type.getDeclaredConstructor();
ReportExporter exporter =
    (ReportExporter) constructor.newInstance();
~~~

Chạy JVM với từng giá trị CSV và XML. Sau đó build native và chạy lại. Nếu thiếu metadata, một hoặc cả hai đường đi có thể thất bại.

### Bước 4 — Bổ sung metadata

Đăng ký hai class và constructor bằng Spring RuntimeHints hoặc reachability metadata. Nếu method được gọi bằng Method.invoke, đăng ký cả method signature với quyền invocation.

### Bước 5 — Thử registry tĩnh

Thay tên class bằng enum ExportFormat và registry Supplier. Build native lại rồi so sánh lượng metadata cần duy trì, tính rõ ràng của cấu hình và khả năng test.

### Bảng ghi nhận

| Ca thử | Cách chọn class | Dữ liệu đích biết khi nào? | Cần kiểm tra |
|---|---|---|---|
| A | CsvExporter.class | Build time | Đường gọi trực tiếp |
| B | Class.forName("com.example.CsvExporter") | Hằng số trong source | API có được phân tích và metadata invocation |
| C | Class.forName(className) từ property | Runtime | Metadata cho mọi class/member được phép |
| D | Supplier registry | Tập implementation cố định trong source | Reachability từ method reference |
| E | Plugin JAR được thêm sau build | Sau khi image đã tạo | Không thể chỉ thêm reflection metadata để nạp bytecode mới |

## 16. Quy trình xử lý một lời gọi reflection trong dự án

Khi tìm thấy reflection, hãy đi theo trình tự:

1. **Xác định API:** Class.forName, getDeclaredMethod, Constructor.newInstance, Field.get/set, MethodHandles hay proxy.
2. **Xác định dữ liệu đầu vào:** literal, class literal, static field, property, environment, request hay database.
3. **Kiểm tra tính hằng:** class name, member name và mảng parameter types có thể xác định ở build time không?
4. **Xác định mục đích:** chỉ tra cứu/introspection hay thực sự invoke constructor/method, đọc/ghi field?
5. **Kiểm tra classpath:** class và tất cả kiểu tham số đã có trong build input chưa?
6. **Tìm metadata sẵn có:** Spring AOT, thư viện hoặc reachability metadata repository đã cung cấp hint chưa?
7. **Chọn cách bổ sung:** RuntimeHints, annotation, JSON metadata hoặc tracing agent.
8. **Thu hẹp phạm vi:** chỉ đăng ký class/member cần dùng, dùng conditional metadata khi phù hợp.
9. **Kiểm thử native:** chạy đủ các tên class, profile, kiểu dữ liệu và nhánh runtime.
10. **Cân nhắc thiết kế lại:** nếu tập đích hữu hạn, registry tĩnh thường đơn giản và an toàn hơn reflection tùy ý.

## 17. Ghi nhớ

GraalVM Native Image có thể suy ra một số lời gọi reflection khi API được hỗ trợ và đối số có thể xác định chắc chắn ở build time. Tên class, tên member và kiểu tham số dạng hằng là tín hiệu tốt; dữ liệu đến từ environment, request, database hoặc plugin registry thường khiến đích truy cập chỉ biết ở runtime.

Ngay cả khi lookup được suy ra, hãy phân biệt metadata cho introspection với metadata cho invocation. getDeclaredMethod tìm được method không tự động chứng minh Method.invoke có đủ quyền truy cập trong image. Tương tự, class được đăng ký không có nghĩa mọi constructor, method và field của nó đều được mở.

Với Spring Boot, ưu tiên hint do Spring AOT và thư viện cung cấp; bổ sung RuntimeHintsRegistrar, annotation hoặc reachability metadata cho các đường đi riêng của ứng dụng. Tracing Agent giúp tìm những đường đi đã chạy nhưng cần test bao phủ rộng. Khi tập plugin hữu hạn, registry tĩnh giúp giảm reflection và làm reachability rõ ràng hơn.

### Tài liệu tham khảo

- GraalVM — Reachability Metadata: https://www.graalvm.org/reference-manual/native-image/metadata/
- GraalVM — Reflection in Native Image: https://www.graalvm.org/reference-manual/native-image/dynamic-features/Reflection/
- GraalVM — Collect Metadata with the Tracing Agent: https://www.graalvm.org/reference-manual/native-image/Agent/
- Spring Boot — Advanced Native Image Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html

Cú pháp metadata và các tùy chọn kiểm tra có thể thay đổi theo phiên bản GraalVM. Khi triển khai, hãy đối chiếu schema và flags với toolchain được pin trong dự án.
