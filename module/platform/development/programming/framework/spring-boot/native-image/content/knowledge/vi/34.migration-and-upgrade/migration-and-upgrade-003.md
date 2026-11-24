# Xử lý dependency chưa tương thích bằng nâng cấp, hints hoặc thay cách tích hợp

Một dependency chạy tốt trên JVM nhưng lỗi khi biên dịch hoặc chạy GraalVM Native Image chưa chắc đã hoàn toàn không tương thích. Nhiều thư viện chỉ dùng reflection, đọc resource theo tên, tạo dynamic proxy, Java serialization hoặc JNI mà Native Image không thể suy ra đầy đủ bằng static analysis. Những trường hợp này thường khắc phục được bằng cách nâng cấp phiên bản có hỗ trợ native hoặc bổ sung reachability metadata.

Một số thư viện lại dựa vào hành vi runtime không phù hợp với mô hình closed-world, chẳng hạn nạp bytecode tùy ý sau khi executable đã tạo, cần Java Instrumentation agent hoặc phụ thuộc vào native library không có bản cho platform triển khai. Thêm hints không giải quyết được các giới hạn đó.

Bài này hướng dẫn cách tìm đúng dependency gây lỗi, kiểm tra mức hỗ trợ Native Image, ưu tiên nâng cấp, bổ sung metadata khi thiếu, và thay đổi ranh giới tích hợp khi thư viện thực sự không phù hợp. Các ví dụ dùng Spring Boot, GraalVM Native Image, Maven và Gradle.

## 1. Hiểu đúng phạm vi tương thích

Native Image thực hiện static analysis khi build. Builder xác định các class, method và field có thể được gọi từ entry point, rồi tạo executable chứa những thành phần cần thiết. Cách làm này giảm kích thước và thời gian khởi động, nhưng khác với JVM truyền thống, nơi class và resource có thể được nạp động trong suốt vòng đời process.

Các dependency thường cần metadata cho một hoặc nhiều khả năng sau:

| Khả năng của thư viện | Vì sao cần metadata |
| --- | --- |
| Java Reflection | Class, constructor, method hoặc field được truy cập bằng tên hoặc reflection API |
| Classpath resources | File được đọc bằng tên resource được tạo hoặc xác định lúc runtime |
| Dynamic proxy | Tập interface của proxy không được compiler suy ra |
| Java serialization | Kiểu dữ liệu cần được serialize/deserialize động |
| JNI | Native code tìm Java class/member theo tên |
| Resource bundles | Locale hoặc bundle được chọn động |
| FFM/native interop | Truy cập native function hoặc memory theo cơ chế cần đăng ký |

Thiếu metadata thường là vấn đề có thể sửa. Tuy nhiên, metadata chỉ khai báo những thành phần cần giữ lại và cách chúng được truy cập. Nó không làm cho một API runtime không được hỗ trợ trở thành API được hỗ trợ.

### Hai nhóm lỗi cần phân biệt

**Thiếu reachability metadata:** thư viện có thể chạy theo mô hình Native Image, nhưng builder chưa biết một class, method, resource, proxy hoặc JNI member sẽ được truy cập động. Hãy bổ sung metadata chính xác.

**Không tương thích về mô hình thực thi:** thư viện cần nạp code mới tùy ý sau khi executable đã build, thay đổi call site động theo dữ liệu runtime, hoặc cần một Java agent dựa trên Instrumentation/JVMTI. Cần thay cách tích hợp, thay thư viện hoặc tách phần đó thành process riêng.

## 2. Quy trình phân loại dependency gây lỗi

Không bắt đầu bằng việc thêm hints cho mọi package. Trước hết, xác định chính xác dependency và đường code gây lỗi.

~~~mermaid
flowchart TD
    A["JVM test pass, native build hoặc runtime fail"] --> B["Xác định exception và call stack"]
    B --> C["Xác định dependency, version và đường gọi"]
    C --> D{"Có phiên bản hỗ trợ Native Image?"}
    D -->|Có| E["Nâng cấp và kiểm tra dependency tree"]
    E --> F["Build và test native"]
    F -->|Pass| G["Giữ version đã xác minh"]
    F -->|Fail| H["Kiểm tra metadata còn thiếu"]
    D -->|Chưa có / chưa rõ| H
    H --> I{"Lỗi thuộc dynamic access có thể đăng ký?"}
    I -->|Có| J["Dùng repository, RuntimeHints hoặc JSON metadata"]
    J --> K["Test lại mọi code path trên native"]
    K -->|Pass| G
    K -->|Fail| L["Kiểm tra giới hạn thực thi và native dependency"]
    I -->|Không| L
    L --> M["Thay integration hoặc thay dependency"]
    M --> N["Cô lập qua adapter / process riêng"]
~~~

Ghi lại các thông tin sau trước khi thay đổi:

- Exception đầy đủ, root cause và stack trace.
- Dependency trực tiếp và dependency bắc cầu liên quan.
- Phiên bản thực tế được resolve, không chỉ version khai báo trong file build.
- Code path đã chạy trước khi lỗi xuất hiện.
- Lỗi xảy ra lúc Spring AOT processing, Native Image compilation hay khi executable chạy.
- Platform, GraalVM/JDK version và Native Build Tools version.

Một lỗi lúc AOT processing có thể là vấn đề Spring context hoặc điều kiện bean. Lỗi lúc native compilation có thể là unsupported feature hoặc metadata không hợp lệ. Lỗi chỉ xuất hiện khi native executable xử lý request thường gợi ý một dynamic path chưa được kiểm thử hoặc chưa có metadata.

## 3. Xác định dependency và phiên bản thực tế

Dependency trực tiếp có thể kéo theo một phiên bản cũ của thư viện khác. Vì vậy, hãy kiểm tra dependency tree và nguồn version trước khi chỉnh sửa.

### Maven

Xem toàn bộ dependency tree:

~~~bash
./mvnw dependency:tree
~~~

Lọc một dependency cụ thể:

~~~bash
./mvnw dependency:tree -Dincludes=com.vendor:legacy-sdk
~~~

Nếu nhiều dependency cùng kéo một artifact, xem đường dẫn nào đưa phiên bản cũ vào. Kiểm tra dependencyManagement, Spring Boot BOM và các exclusion đang có.

### Gradle

Xem dependency được resolve:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm lý do một version được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency legacy-sdk \
  --configuration runtimeClasspath
~~~

Kiểm tra cả configuration dùng cho native build/test nếu chúng có dependency khác runtimeClasspath.

### Kiểm tra mức hỗ trợ Native Image

Tra cứu đúng group/artifact và phiên bản trong danh sách thư viện GraalVM đã kiểm thử và GraalVM Reachability Metadata Repository. Danh sách có thể phân biệt:

- **Tested:** maintainer của thư viện liên tục kiểm thử với Native Image.
- **Community-tested:** được kiểm thử qua repository metadata hoặc dự án cộng đồng.

Các nhãn này là tín hiệu hữu ích, không phải cam kết rằng mọi cấu hình ứng dụng đều tương thích. Hãy kiểm tra version range, JDK, GraalVM và các module mà ứng dụng thực sự sử dụng.

Native Build Tools hiện tích hợp việc lấy metadata từ GraalVM Reachability Metadata Repository. Nếu metadata đã được phát hành cho dependency/version đang dùng, plugin có thể đưa metadata đó vào native build mà không cần chép thủ công vào project.

## 4. Ưu tiên nâng cấp dependency có hỗ trợ native

Khi thư viện đã có phiên bản hỗ trợ Native Image, nâng cấp thường là cách dễ bảo trì nhất. Phiên bản mới có thể:

- Đóng gói reachability metadata cùng JAR.
- Thay reflection bằng code có thể phân tích tĩnh.
- Bổ sung Spring RuntimeHints hoặc GraalVM metadata.
- Sửa class initialization để không phụ thuộc môi trường build.
- Thay native library hoặc cung cấp binary tương thích với platform cần triển khai.
- Sửa lỗi chỉ xuất hiện trong native runtime.

### Maven: quản lý version có chủ đích

Nếu thư viện không được Spring Boot BOM quản lý, khai báo version rõ ràng:

~~~xml
<properties>
    <partner-sdk.version>VERSION_DA_XAC_MINH</partner-sdk.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.vendor</groupId>
        <artifactId>partner-sdk</artifactId>
        <version>${partner-sdk.version}</version>
    </dependency>
</dependencies>
~~~

Nếu thư viện được quản lý bởi BOM, ưu tiên dùng version tương thích trong BOM. Chỉ override version khi đã xác minh ma trận tương thích của các dependency liên quan.

### Gradle: khai báo version đã kiểm tra

~~~kotlin
dependencies {
    implementation("com.vendor:partner-sdk:VERSION_DA_XAC_MINH")
}
~~~

Nếu project dùng version catalog hoặc platform/BOM, cập nhật ở đúng nơi quản lý version thay vì khai báo một version thứ hai ở module.

### Sau khi nâng cấp cần kiểm tra gì?

1. Chạy lại JVM unit và integration tests.
2. Kiểm tra dependency tree để chắc rằng version mới thực sự được resolve.
3. Build Spring AOT và native executable.
4. Chạy native smoke/integration tests trên các đường gọi thư viện.
5. Kiểm tra log, reflection/resource diagnostics và lỗi linkage.
6. Ghi lại version đã xác minh để các môi trường build dùng cùng dependency graph.

Đừng nâng cấp riêng một dependency mà bỏ qua yêu cầu version của Spring Boot, JDK hoặc các module đi kèm. Một bản SDK mới có thể yêu cầu API của thư viện khác hoặc thay đổi hành vi ở runtime.

## 5. Bổ sung metadata có sẵn từ GraalVM Reachability Metadata Repository

Trước khi tự viết hints, kiểm tra metadata cộng đồng đã tồn tại cho dependency chưa. Repository lưu metadata cho các thư viện JVM phổ biến để chúng có thể hoạt động với Native Image.

Native Build Tools Maven và Gradle có thể sử dụng repository này tự động. Vì vậy, nên dùng phiên bản Native Build Tools phù hợp và kiểm tra log native build để xác nhận metadata được tìm thấy và áp dụng.

Nếu metadata chưa có:

1. Kiểm tra đúng tọa độ dependency và version.
2. Xem thư viện có release mới tự đóng gói metadata không.
3. Xác định dynamic access nào còn thiếu.
4. Nếu có thể tái hiện bằng ứng dụng tối thiểu, chuẩn bị báo cáo và đóng góp metadata upstream.
5. Trong thời gian chờ, có thể bổ sung metadata ở application nếu quyền sở hữu và phạm vi sử dụng rõ ràng.

Không chép metadata của một version khác rồi mặc định nó đúng cho version đang dùng. API, class name và member có thể thay đổi giữa các release.

## 6. Dùng Spring RuntimeHintsRegistrar khi ứng dụng sở hữu phần tích hợp

Nếu ứng dụng Spring Boot gọi thư viện bên thứ ba theo một đường reflection/resource/proxy cụ thể, có thể đăng ký hints bằng `RuntimeHintsRegistrar`.

Ví dụ, SDK đọc method bằng reflection, nạp file cấu hình và tạo proxy cho interface:

~~~java
package com.example.orders.nativeconfig;

import java.lang.reflect.Method;

import com.vendor.sdk.VendorCodec;
import com.vendor.sdk.VendorService;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class VendorSdkHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = ReflectionUtils.findMethod(
                VendorCodec.class,
                "decode",
                String.class
        );

        if (decode != null) {
            hints.reflection().registerMethod(decode, ExecutableMode.INVOKE);
        }

        hints.resources().registerPattern("vendor/defaults.properties");
        hints.proxies().registerJdkProxy(VendorService.class);
    }
}
~~~

Kích hoạt registrar trong Spring context:

~~~java
package com.example.orders.nativeconfig;

import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(VendorSdkHints.class)
public class VendorNativeConfiguration {
}
~~~

Ví dụ trên đăng ký đúng ba loại truy cập đã biết:

- Method VendorCodec.decode(String) được gọi bằng reflection.
- Resource vendor/defaults.properties được nạp theo classpath.
- JDK proxy được tạo cho interface VendorService.

Nếu thư viện dùng Java serialization, Spring RuntimeHints cũng có API đăng ký kiểu serialization. Nếu DTO được bind bởi Jackson hoặc framework binding, ưu tiên annotation binding chuyên biệt như @RegisterReflectionForBinding khi phù hợp.

### Nguyên tắc viết hints

- Chỉ đăng ký class/member/resource thực sự được truy cập động.
- Ưu tiên method và constructor cụ thể thay vì mở toàn bộ member của package.
- Đặt hints cạnh adapter hoặc cấu hình tích hợp tương ứng.
- Viết test xác minh registrar đóng góp đúng hints.
- Kiểm tra native executable thực sự đi qua code path đó.

Hints không sửa lỗi logic của thư viện, không cài thêm native library bị thiếu và không làm cho API không được hỗ trợ trở nên hợp lệ.

## 7. Dùng reachability-metadata.json cho metadata độc lập với Spring

Nếu metadata chỉ cần cho Native Image và không phụ thuộc Spring, có thể khai báo JSON trong classpath.

Ví dụ đặt file:

`src/main/resources/META-INF/native-image/com.example/orders-api-additional/reachability-metadata.json`

Nội dung minh họa:

~~~json
{
  "reflection": [
    {
      "type": "com.vendor.sdk.VendorCodec",
      "allPublicMethods": true
    }
  ],
  "resources": [
    {
      "glob": "vendor/config/*.properties"
    }
  ]
}
~~~

Trong đó:

- `reflection` mô tả class hoặc member được truy cập động.
- `allPublicMethods` cho phép reflection trên các public method của kiểu đã nêu.
- `resources` đăng ký nhóm resource theo glob.

Ví dụ trên cố ý dùng allPublicMethods để minh họa. Trong ứng dụng thực tế, nếu chỉ gọi một hoặc hai method, hãy khai báo member cụ thể để giảm metadata và giới hạn bề mặt truy cập.

GraalVM đọc reachability-metadata.json trong META-INF/native-image/ trên classpath. Thư viện có thể đóng gói metadata riêng trong JAR của nó; ứng dụng cũng có thể cung cấp metadata bổ sung trong một thư mục có tọa độ riêng để tránh ghi đè tài nguyên do Spring AOT hoặc dependency khác sinh ra.

Dùng schema của GraalVM version đang build để xác minh JSON. Định dạng reachability metadata hiện đại gộp nhiều loại cấu hình vào một file; các file riêng lẻ cũ như reflect-config.json vẫn có thể xuất hiện trong dự án legacy nhưng không nên tạo mới nếu toolchain đang dùng schema mới.

## 8. Dùng Tracing Agent để tìm dynamic access bị bỏ sót

Khi chưa biết thư viện truy cập class hoặc resource nào bằng reflection, GraalVM Tracing Agent có thể quan sát ứng dụng chạy trên JVM và ghi metadata.

Với Spring Boot, chạy executable JAR cùng AOT mode và agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-api.jar
~~~

Gửi request qua những chức năng sử dụng SDK, bao gồm nhánh thành công, lỗi, cấu hình tùy chọn và các subtype có thể chọn. Khi dừng ứng dụng, agent ghi metadata vào thư mục output.

Có thể chạy lại để bổ sung các đường đi chưa được quan sát bằng config-merge-dir:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-merge-dir=target/native-agent \
  -jar target/orders-api.jar
~~~

Sau khi thu thập:

1. Đọc từng entry và xác định dependency/call path tạo ra nó.
2. Loại bỏ entry chỉ phục vụ test framework hoặc code không có trong production.
3. Kiểm tra class, method, resource và proxy có đúng với version dependency hiện tại không.
4. Đưa metadata cần thiết vào META-INF/native-image/ trong source hoặc module sở hữu tích hợp.
5. Build lại native executable và chạy cùng bộ test.

Tracing Agent chỉ ghi nhận những đường code đã được thực thi trên JVM. Nó không thể bảo đảm metadata đầy đủ cho mọi input, mọi plugin hoặc mọi nhánh runtime. Nếu test chạy cả Spring test infrastructure, metadata thu được có thể chứa nhiều entry không cần cho ứng dụng production. Hãy review và lọc trước khi commit.

## 9. Nhận biết trường hợp hints không đủ

Một số dependency dựa trên hành vi không thể giải quyết chỉ bằng metadata:

| Cách thư viện hoạt động | Vì sao hints có thể không đủ | Hướng xử lý |
| --- | --- | --- |
| Nạp class hoặc bytecode tùy ý sau khi executable đã tạo | Class/method mới không nằm trong tập code được phân tích | Dùng registry hữu hạn, code generation lúc build hoặc thay integration |
| Java agent cần Instrumentation/JVMTI ở runtime | Native executable không vận hành như HotSpot JVM với Java agent thông thường | Dùng SDK/integration dành cho native hoặc giữ thành phần ở JVM |
| Runtime plugin tự quét và nạp JAR không biết trước | Tập class không cố định tại build time | Chuyển sang plugin registry đóng hoặc process riêng |
| Phụ thuộc native library chỉ có cho một OS/architecture khác | Metadata không tạo ra binary native còn thiếu | Thay library hoặc cung cấp native build đúng platform |
| Dựa vào API/JDK internals đã bị thay đổi | Hints không khôi phục API không còn tồn tại | Nâng cấp thư viện hoặc thay API |
| Dùng call site động thay đổi target theo dữ liệu runtime | Không thể luôn suy ra target trong closed-world analysis | Thay bằng dispatch tường minh hoặc cơ chế được Native Image hỗ trợ |

GraalVM có một số khả năng runtime class loading mang tính thử nghiệm ở các phiên bản nhất định. Không bật chúng như giải pháp mặc định cho một plugin framework cũ. Chỉ cân nhắc khi use case khớp giới hạn được tài liệu hóa, chấp nhận chi phí image/memory và có test cho class loading thực tế.

### Khi nào nên thay cách tích hợp?

Nếu thư viện có API tĩnh hoặc registry tường minh, hãy dùng đường đó thay cho reflection không giới hạn. Ví dụ:

- Thay class name trong cấu hình bằng một danh sách implementation được đăng ký lúc build.
- Dùng serializer/codec được khai báo trực tiếp thay cho tự dò class theo package.
- Dùng resource path cố định thay cho quét toàn bộ classpath.
- Dùng API HTTP/REST hoặc message contract thay cho nạp plugin trong cùng process.
- Thay thư viện không có native support bằng thư viện có cùng chức năng và đã được kiểm thử.
- Đưa phần phụ thuộc agent hoặc runtime class loading vào một JVM service riêng và gọi qua HTTP/gRPC.

## 10. Cô lập dependency bằng adapter để có thể thay thế

Không để API của thư viện không tương thích lan ra toàn bộ application. Tạo một interface thuộc domain/application và đặt SDK trong adapter.

Ví dụ:

~~~java
public interface DocumentRenderer {
    byte[] render(Document document);
}
~~~

Adapter dùng thư viện hiện tại:

~~~java
@Component
public class VendorDocumentRenderer implements DocumentRenderer {

    private final VendorSdk sdk;

    public VendorDocumentRenderer(VendorSdk sdk) {
        this.sdk = sdk;
    }

    @Override
    public byte[] render(Document document) {
        return this.sdk.render(document.toVendorRequest());
    }
}
~~~

Nếu SDK không thể chạy native, có thể thay adapter bằng một implementation khác:

- Một thư viện native-compatible.
- Một HTTP client gọi rendering service riêng.
- Một implementation tối giản cho các định dạng cần hỗ trợ.

Business service vẫn phụ thuộc DocumentRenderer. Nhờ vậy, thay đổi integration không bắt buộc phải sửa toàn bộ nghiệp vụ.

### Khi tách thành process riêng

Tách thư viện thành JVM sidecar/service khi nó thật sự cần Java agent, runtime plugin loading hoặc một JVM-only SDK không thể thay thế. Xác định rõ:

- Request/response contract và versioning.
- Timeout, retry, idempotency và circuit breaker.
- Authentication giữa hai process.
- Log, metrics và trace propagation.
- Chi phí vận hành thêm một service.
- Hành vi khi service phụ thuộc không sẵn sàng.

Đây là quyết định kiến trúc có chi phí. Chỉ áp dụng khi lợi ích của việc giữ thư viện hiện tại lớn hơn chi phí vận hành process riêng.

## 11. Lưu ý riêng với JNI và native library

Một dependency có JNI không mặc nhiên không tương thích Native Image. Native Image hỗ trợ JNI, nhưng class, method và field mà native code tra cứu theo tên cần được đăng ký trước.

Ngoài metadata, cần kiểm tra native library:

- Có binary đúng OS và CPU architecture không?
- Có đúng ABI và libc của runtime image không?
- Có phụ thuộc shared library khác không?
- Có CPU instruction requirement vượt baseline deployment không?
- Có được đóng gói hoặc tìm thấy qua java.library.path/System.loadLibrary không?

Nếu lỗi là UnsatisfiedLinkError, thiếu shared library hoặc sai ABI, thêm reflection hints thường không giải quyết được. Phải sửa native dependency hoặc runtime image.

JNI metadata có thể được thu thập bằng Tracing Agent trên JVM nếu test thực sự gọi native path. Sau đó vẫn cần native integration test để xác nhận việc load và gọi thư viện trên executable.

## 12. Kiểm thử sau khi nâng cấp hoặc bổ sung hints

Một dependency chỉ được xem là đã xử lý khi native executable chạy qua các luồng có sử dụng dependency đó. Build thành công chưa đủ.

### Bộ kiểm thử đề xuất

| Kiểm thử | JVM | Native executable |
| --- | --- | --- |
| Unit test cho adapter | Có | Có thể chạy native test nếu cần |
| Khởi tạo Spring ApplicationContext | Có | Có |
| Reflection path của SDK | Có | Bắt buộc |
| Đọc resource động | Có | Bắt buộc |
| Dynamic proxy/serialization | Có | Bắt buộc nếu dependency sử dụng |
| JNI/native library | Có | Bắt buộc |
| Các nhánh cấu hình và plugin | Có | Bắt buộc cho nhánh được hỗ trợ |
| Error handling khi dependency lỗi | Có | Có |

Với GraalVM mới hỗ trợ, bật exact reachability metadata để phát hiện missing registration sớm:

~~~bash
native-image --exact-reachability-metadata ...
~~~

Có thể dùng chế độ cảnh báo khi chạy executable:

~~~bash
./target/orders-api -XX:MissingRegistrationReportingMode=Warn
~~~

Trong test nghiêm ngặt, dùng chế độ thoát ngay khi phát hiện lỗi missing registration:

~~~bash
./target/orders-api -XX:MissingRegistrationReportingMode=Exit
~~~

Exit đặc biệt hữu ích nếu ứng dụng có đoạn code bắt Throwable, vì lỗi thiếu registration không bị nuốt và biến thành hành vi fallback khó phát hiện.

Các option và hành vi reporting phụ thuộc GraalVM version. Kiểm tra tài liệu đúng toolchain nếu option chưa được hỗ trợ.

### Không bỏ qua lỗi bằng catch rộng

Một thư viện có thể bắt Throwable rồi âm thầm bỏ qua lỗi reflection. Trên JVM, thao tác đó có thể thành công; trên native, missing registration có thể bị che đi và tạo kết quả sai. Trong test native, bật reporting mode phù hợp và xác minh output nghiệp vụ, không chỉ kiểm tra process có exit code 0.

## 13. Quản lý hints theo version dependency

Hints gắn với cấu trúc cụ thể của thư viện. Khi nâng cấp dependency, cần review metadata cũ:

- Class có bị đổi package hoặc đổi tên không?
- Method/constructor có đổi signature không?
- Resource path có thay đổi không?
- Thư viện đã tự đóng gói metadata ở phiên bản mới chưa?
- Có thể xóa hints do ứng dụng tự khai báo vì dependency đã cung cấp không?

Giữ metadata dư thừa có thể làm executable lớn hơn, giữ thêm member không cần thiết và khiến người bảo trì hiểu nhầm rằng ứng dụng còn cần đường truy cập cũ.

Nên tổ chức metadata theo dependency/integration và ghi chú lý do:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        orders-api-additional/
          reachability-metadata.json
~~~

Khi cập nhật dependency, chạy native test và review diff của metadata. Nếu metadata được đóng gói trong library, ưu tiên sửa hoặc nâng cấp library thay vì duy trì bản sao thủ công trong mọi application.

## 14. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Việc nên làm trước |
| --- | --- | --- |
| JVM chạy, native báo MissingReflectionRegistrationError | Thiếu class/member reflection | Kiểm tra metadata repository, nâng cấp hoặc đăng ký member cụ thể |
| Resource tồn tại trong JAR nhưng native không đọc được | Resource không được đăng ký hoặc pattern không khớp | Đăng ký resource chính xác và kiểm tra path/case |
| Proxy hoạt động JVM nhưng native lỗi | Interface proxy chưa được khai báo | Dùng RuntimeHints hoặc metadata proxy |
| Serialization lỗi trên native | Kiểu serialize chưa được đăng ký hoặc thư viện dùng cơ chế không hỗ trợ | Kiểm tra metadata serialization, cân nhắc JSON/codec tường minh |
| Lỗi JNI lookup | Thiếu JNI metadata hoặc native library | Đăng ký JNI member và kiểm tra binary native |
| UnsupportedFeatureError | Code path dùng API hoặc hành vi không được hỗ trợ/cấu hình sai | Đọc thông báo đầy đủ; xác định có thể thay API hay phải thay dependency |
| ClassNotFoundException chỉ trên native | Class được chọn bằng tên động hoặc không reachable | Xác minh class có trong classpath và metadata |
| UnsatisfiedLinkError | Thiếu library, sai ABI hoặc không tìm thấy shared object | Kiểm tra native binary và runtime image |
| Nâng version làm lỗi Spring context | Version dependency không tương thích BOM/API Spring | Kiểm tra dependency tree và version matrix |
| Native test pass nhưng production lỗi | Agent chưa quan sát nhánh production hoặc config khác | Mở rộng test theo profile, input, resource và integration thực tế |

## 15. Bài thực hành: xử lý một SDK không tương thích native

Giả sử dịch vụ orders-api dùng SDK của đối tác để giải mã payload. SDK chạy trên JVM nhưng native executable lỗi khi gọi method VendorCodec.decode, đồng thời không đọc được file vendor/defaults.properties.

### Phần A — tìm dependency

1. Dùng Maven dependency:tree hoặc Gradle dependencyInsight xác định version SDK được resolve.
2. Kiểm tra version đó trong danh sách thư viện GraalVM đã kiểm thử và Reachability Metadata Repository.
3. Kiểm tra release note của SDK để tìm native support hoặc metadata mới.
4. Nếu có version hỗ trợ, nâng cấp theo BOM/version catalog và chạy lại test.

### Phần B — thêm metadata nếu thiếu

Nếu SDK có thể chạy native và chỉ thiếu dynamic access:

1. Dùng Tracing Agent trên JVM với spring.aot.enabled=true.
2. Gửi request qua cả đường giải mã thành công và lỗi.
3. Kiểm tra agent có ghi nhận VendorCodec và resource hay không.
4. Nếu metadata ghi nhận đúng, đưa entry cần thiết vào reachability-metadata.json hoặc RuntimeHintsRegistrar.
5. Bật --exact-reachability-metadata nếu toolchain hỗ trợ.
6. Build native và chạy lại test.

### Phần C — quyết định thay integration

Nếu SDK tự nạp plugin bytecode không biết trước hoặc yêu cầu Java agent runtime:

1. Xác định API nghiệp vụ tối thiểu mà ứng dụng cần.
2. Tạo interface adapter thuộc application.
3. Tìm SDK khác có native support hoặc thay bằng giao thức HTTP tới service riêng.
4. Chạy contract test để bảo đảm request/response và error semantics không đổi.
5. So sánh chi phí latency, vận hành và bảo trì trước khi chọn.

### Câu hỏi tự kiểm tra

1. Vì sao JVM test pass không chứng minh dependency tương thích Native Image?
2. Reachability metadata giải quyết những loại dynamic access nào?
3. Khi nào nên nâng cấp dependency trước khi tự viết hints?
4. GraalVM Reachability Metadata Repository giúp gì cho ứng dụng?
5. RuntimeHintsRegistrar và JSON metadata khác nhau ở điểm nào?
6. Vì sao Tracing Agent không thể chứng minh metadata đầy đủ cho mọi code path?
7. Khi nào Java agent hoặc runtime class loading là dấu hiệu cần thay integration?
8. Vì sao JNI dependency cần kiểm tra cả metadata lẫn native binary/ABI?
9. Tại sao không nên đăng ký toàn bộ member của mọi class trong package?
10. Vì sao cần review và xóa hints cũ sau khi nâng cấp thư viện?

**Tiêu chí đạt:** xác định được dependency/version thực tế gây lỗi; phân biệt thiếu metadata với giới hạn closed-world; ưu tiên nâng cấp khi có bản native-compatible; bổ sung đúng reflection/resource/proxy/serialization/JNI hints khi cần; dùng Tracing Agent có kiểm soát; thay adapter hoặc tách process nếu thư viện không thể chạy native; cuối cùng xác minh mọi code path trên native executable.

## Tài liệu chính thức

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Framework — Runtime Hints and AOT: https://docs.spring.io/spring-framework/reference/core/aot.html
- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- GraalVM — Native Image Compatibility Guide: https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/
- GraalVM — Collect Metadata with the Tracing Agent: https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM — Java Native Interface in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/
- GraalVM — Libraries and Frameworks Tested with Native Image: https://www.graalvm.org/native-image/libraries-and-frameworks/
- GraalVM — Reachability Metadata Repository: https://github.com/oracle/graalvm-reachability-metadata
