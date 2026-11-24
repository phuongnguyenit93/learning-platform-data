# Kiểm thử hợp đồng cho các tích hợp có reflection, service loading hoặc JNI

## 1. Vì sao cần contract test cho thư viện ngoài?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành GraalVM Native Image. Những thư viện ngoài có thể hoạt động tốt trên JVM nhưng thất bại khi chạy native nếu chúng dựa vào reflection, `ServiceLoader`, resource được tìm động hoặc JNI.

Một unit test chỉ mock SDK thường kiểm tra được logic của adapter nhưng không xác nhận thư viện thật có thể:

- tìm constructor, method hoặc field qua reflection;
- tìm provider qua `ServiceLoader` và resource `META-INF/services`;
- nạp shared library đúng hệ điều hành/kiến trúc;
- gọi native method hoặc callback từ C/C++ về Java;
- đọc resource và cấu hình cần thiết trong native executable.

**Contract test** kiểm tra hành vi quan sát được tại ranh giới tích hợp. Cùng một bộ kiểm thử nên chạy với implementation thật trên JVM và native executable. Nhờ vậy, nhóm phát triển phát hiện sớm sự khác biệt về discovery, reachability metadata, resource, lỗi và đóng gói.

## 2. Contract test kiểm tra điều gì?

Contract của một tích hợp mô tả các cam kết mà ứng dụng dựa vào:

| Nhóm cam kết | Ví dụ cần xác nhận |
| --- | --- |
| Input/output | Dữ liệu được ghi và đọc giữ nguyên nội dung, encoding và định dạng |
| Error mapping | Timeout, dữ liệu không hợp lệ và lỗi từ SDK được chuyển thành lỗi ứng dụng có thể xử lý |
| Discovery | Provider hoặc plugin cần thiết được tìm thấy đúng cách |
| Reflection | Các constructor/method mà thư viện gọi động có thể truy cập trong native |
| Resource | Schema, template hoặc file cấu hình hợp lệ được tìm thấy |
| JNI | Native library được nạp và lời gọi native trả kết quả đúng |
| Lifecycle | Tài nguyên được đóng, callback không bị giữ sau khi hoàn tất |
| Runtime behavior | Timeout, concurrency và cấu hình runtime được tôn trọng |

Contract test không cần kiểm tra mọi method nội bộ của vendor. Hãy tập trung vào các hành vi mà ứng dụng thực sự sử dụng và các rủi ro có thể thay đổi khi chuyển từ JVM sang Native Image.

## 3. Tách thư viện ngoài sau một adapter

Một thiết kế dễ kiểm thử là đặt thư viện bên thứ ba sau một interface do ứng dụng sở hữu. Ví dụ dịch vụ lưu trữ hồ sơ:

~~~java
public interface DocumentArchive {
    void save(String documentId, byte[] content);
    byte[] load(String documentId);
    boolean exists(String documentId);
}
~~~

Adapter triển khai interface bằng SDK thật:

~~~java
public final class VendorDocumentArchive implements DocumentArchive {

    private final VendorArchiveClient client;

    public VendorDocumentArchive(VendorArchiveClient client) {
        this.client = client;
    }

    @Override
    public void save(String documentId, byte[] content) {
        client.put(documentId, content);
    }

    @Override
    public byte[] load(String documentId) {
        return client.get(documentId);
    }

    @Override
    public boolean exists(String documentId) {
        return client.contains(documentId);
    }
}
~~~

`VendorArchiveClient` là kiểu minh họa; thay bằng API thực tế của thư viện đang dùng. Adapter có thể chuyển đổi kiểu dữ liệu, map lỗi vendor sang exception của ứng dụng và áp dụng timeout. Không nên để controller hoặc domain service phụ thuộc trực tiếp vào SDK nếu không cần.

Lợi ích của interface:

- Contract test có thể chạy trên mọi implementation.
- Có thể thay SDK hoặc nâng version mà không đổi hợp đồng ứng dụng.
- Test JVM có thể dùng implementation giả cho logic không cần vendor.
- Native integration test vẫn có thể chạy với adapter và dependency thật để xác nhận metadata.

Mock không thay thế contract test với SDK thật. Dùng fake/mock cho unit test nhanh, sau đó dùng contract suite với implementation thật ở bước tích hợp.

## 4. Xây dựng contract suite có thể tái sử dụng

JUnit 5 cho phép đặt các test chung trong abstract base class. Mỗi implementation cung cấp factory tạo adapter và tài nguyên kiểm thử:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

abstract class DocumentArchiveContractTests {

    protected abstract DocumentArchive createArchive();
    protected abstract void cleanUp();

    @AfterEach
    void releaseResources() {
        cleanUp();
    }

    @Test
    void savesAndLoadsTheSameBytes() {
        DocumentArchive archive = createArchive();
        byte[] content = new byte[] { 0, 1, 2, 10, 127, -1 };

        archive.save("contract-doc-001", content);

        assertThat(archive.exists("contract-doc-001")).isTrue();
        assertThat(archive.load("contract-doc-001"))
            .containsExactly(content);
    }

    @Test
    void reportsMissingDocument() {
        DocumentArchive archive = createArchive();
        assertThat(archive.exists("does-not-exist")).isFalse();
    }
}
~~~

Implementation test cho SDK thật:

~~~java
class VendorDocumentArchiveContractTests
        extends DocumentArchiveContractTests {

    private VendorArchiveClient client;

    @Override
    protected DocumentArchive createArchive() {
        client = VendorArchiveClient.connect(testEndpoint());
        return new VendorDocumentArchive(client);
    }

    @Override
    protected void cleanUp() {
        if (client != null) {
            client.close();
        }
    }

    private String testEndpoint() {
        return System.getenv("ARCHIVE_TEST_ENDPOINT");
    }
}
~~~

Đây là khung minh họa; trong dự án thật cần kiểm tra endpoint và credential trước khi tạo client, tạo document ID duy nhất cho mỗi test và xóa dữ liệu thử sau khi chạy. Nếu SDK có API `AutoCloseable`, ưu tiên quản lý lifecycle bằng try-with-resources hoặc fixture phù hợp.

Contract suite nên được chạy với adapter vendor trên JVM và native executable, cùng các implementation khác nếu ứng dụng hỗ trợ nhiều provider. Không đưa secret thật vào source hoặc test report. Dùng test credential giới hạn quyền, secret store của CI và endpoint sandbox.

## 5. Tích hợp dựa trên reflection

### 5.1. Reflection làm thay đổi reachability

Thư viện có thể tìm class hoặc method bằng tên tại runtime:

~~~java
Class<?> type = Class.forName("com.vendor.codec.JsonCodec");
Object codec = type.getDeclaredConstructor().newInstance();

Method encode = type.getMethod("encode", Object.class);
String json = (String) encode.invoke(codec, payload);
~~~

Trên JVM, classloader và reflection có thể tìm kiểu trong classpath. Native Image phân tích theo mô hình closed world; class/member chỉ được truy cập động có thể bị loại nếu không có reachability metadata phù hợp.

Khi đó, ứng dụng có thể build thành công nhưng lỗi ở runtime như:

- `ClassNotFoundException` hoặc `NoClassDefFoundError`;
- `NoSuchMethodException`;
- `IllegalAccessException`;
- lỗi reflection của Native Image cho constructor/method chưa được đăng ký.

### 5.2. Test đúng đường reflection mà ứng dụng sử dụng

Một test contract nên gọi API công khai của adapter, để thư viện thực hiện đường reflection thật. Không chỉ kiểm tra `Class.forName()` trong một test riêng rồi kết luận tích hợp hoạt động.

~~~java
@Test
void vendorCodecCanEncodeAndDecodeInTheApplicationFlow() {
    PayloadCodec codec = codecFactory.create("com.vendor.codec.JsonCodec");
    Payload input = new Payload("doc-01", "invoice");

    byte[] encoded = codec.encode(input);
    Payload decoded = codec.decode(encoded, Payload.class);

    assertThat(decoded).isEqualTo(input);
}
~~~

Chạy test này trên JVM và native executable. Test phải đi qua factory/adapter thật để xác nhận class name, constructor, method và mapping thực tế được sử dụng.

### 5.3. Bổ sung metadata đúng phạm vi

Trước khi tự viết hints:

1. Kiểm tra thư viện có cung cấp GraalVM reachability metadata hay không.
2. Kiểm tra metadata đó có trong version dependency đang dùng không.
3. Xác định class, constructor, method hoặc field thực sự được truy cập động.
4. Chạy native test để xác nhận đường gọi đó.

Với Spring, có thể đăng ký các kiểu cần reflection bằng `RuntimeHintsRegistrar` hoặc annotation `@RegisterReflectionForBinding` khi phù hợp. Ví dụ minh họa đăng ký một constructor và method cụ thể:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(VendorCodecHints.class)
class VendorCodecConfiguration {
}

class VendorCodecHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        try {
            Class<?> codecType = ClassUtils.forName(
                "com.vendor.codec.JsonCodec", classLoader
            );
            hints.reflection().registerConstructor(
                codecType.getDeclaredConstructor(),
                ExecutableMode.INVOKE
            );
            hints.reflection().registerMethod(
                codecType.getMethod("encode", Object.class),
                ExecutableMode.INVOKE
            );
        }
        catch (ClassNotFoundException | NoSuchMethodException ex) {
            throw new IllegalStateException(
                "The configured vendor codec is unavailable", ex
            );
        }
    }
}
~~~

Ví dụ giả định dependency có mặt khi cấu hình được xử lý. Nếu dependency là tùy chọn, đặt cấu hình trong auto-configuration có `@ConditionalOnClass(name = "...")` và tránh import trực tiếp kiểu vendor ở class luôn được nạp.

Đăng ký constructor/method cụ thể hẹp hơn việc bật toàn bộ declared methods/fields cho cả package. Nếu vendor đã phát hành metadata, ưu tiên dùng metadata tương ứng thay vì tạo cấu hình trùng lặp.

## 6. Tích hợp dựa trên ServiceLoader

### 6.1. ServiceLoader tìm provider như thế nào?

Java `ServiceLoader` tìm implementation của một service interface. Với classpath thông thường, provider có thể được khai báo trong file:

~~~text
META-INF/services/com.example.compression.CompressionProvider
~~~

Nội dung là tên đầy đủ của provider:

~~~text
com.vendor.compression.FastCompressionProvider
~~~

Nếu dùng Java module system, provider cũng có thể được khai báo bằng `provides ... with ...` trong `module-info.java`.

Ví dụ service interface:

~~~java
public interface CompressionProvider {
    String id();
    byte[] compress(byte[] input);
    byte[] decompress(byte[] input);
}
~~~

Ứng dụng tìm provider:

~~~java
CompressionProvider provider =
    ServiceLoader.load(CompressionProvider.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(candidate -> candidate.id().equals("fast"))
        .findFirst()
        .orElseThrow(() ->
            new IllegalStateException("No 'fast' compression provider found")
        );
~~~

Chọn provider theo ID hoặc cấu hình rõ ràng. Không dựa vào `findFirst()` mà không có tiêu chí nếu classpath có thể chứa nhiều provider; thứ tự discovery không nên trở thành hợp đồng nghiệp vụ.

### 6.2. Vì sao ServiceLoader cần test native?

Native Image có thể phân tích service provider ở build time, nhưng discovery còn phụ thuộc service descriptor, module declaration, classpath và cách ứng dụng nạp provider. Nếu descriptor hoặc provider không được đưa vào executable, ứng dụng có thể không tìm thấy implementation dù JVM test chạy tốt.

Contract test nên xác nhận:

- provider có mặt được phát hiện;
- provider ID đúng và duy nhất theo cấu hình ứng dụng;
- provider có thể khởi tạo;
- chức năng nén/giải nén giữ nguyên dữ liệu;
- trường hợp provider không có được xử lý bằng lỗi rõ ràng hoặc fallback đã định nghĩa.

~~~java
@Test
void discoversAndUsesConfiguredCompressionProvider() {
    List<CompressionProvider> providers =
        ServiceLoader.load(CompressionProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .toList();

    assertThat(providers)
        .extracting(CompressionProvider::id)
        .contains("fast");

    CompressionProvider provider = providers.stream()
        .filter(candidate -> candidate.id().equals("fast"))
        .findFirst()
        .orElseThrow();

    byte[] input = "native-image-contract".getBytes(StandardCharsets.UTF_8);
    assertThat(provider.decompress(provider.compress(input)))
        .containsExactly(input);
}
~~~

Test trên phải chạy trong classpath có provider thật. Với native executable, chạy cùng test logic hoặc một smoke endpoint/command gọi đúng provider.

### 6.3. Kiểm tra service descriptor

Xác minh dependency JAR có file `META-INF/services/...`:

~~~bash
jar tf target/application.jar | grep 'META-INF/services'
~~~

Spring Boot executable JAR có cấu trúc nested JAR; cần kiểm tra descriptor trong dependency JAR bên trong nếu lệnh trên chỉ hiển thị các entry của outer JAR. Có thể trích xuất dependency cụ thể hoặc kiểm tra artifact của thư viện trước khi đóng gói.

Nếu provider được tạo bởi module system, kiểm tra `module-info.class`/module descriptor và cấu hình module path của build.

Không thêm resource hint một cách máy móc nếu Native Image hoặc thư viện đã xử lý service provider metadata. Trước tiên kiểm tra output và log native build; chỉ bổ sung metadata theo hướng dẫn của GraalVM/Native Build Tools phiên bản đang dùng.

## 7. Tích hợp sử dụng JNI

### 7.1. JNI có hai chiều tương tác

JNI cho phép Java gọi mã native và cho phép mã native tương tác ngược với Java object. Ví dụ Java khai báo native method:

~~~java
public final class NativeChecksum {

    static {
        System.loadLibrary("checksum");
    }

    private NativeChecksum() {
    }

    public static native int checksum(byte[] input);
}
~~~

Trong ứng dụng JVM, `System.loadLibrary` tìm shared library theo tên và cơ chế nạp thư viện của hệ điều hành. Với native executable, shared library vẫn phải tương thích với OS/CPU đích và được đặt ở vị trí loader có thể tìm thấy.

JNI cũng có thể gọi ngược vào Java bằng `JNIEnv`, `FindClass`, `GetMethodID`, `GetFieldID` hoặc tạo object. Những truy cập động từ native code tới Java class/member cần metadata JNI phù hợp trong Native Image.

### 7.2. Những gì contract test cần xác nhận

Với thư viện JNI, contract suite nên kiểm tra:

- shared library được nạp trong môi trường target;
- native method trả kết quả đúng với input đã biết;
- dữ liệu byte array/string được truyền đúng encoding và boundary;
- lỗi từ native code được chuyển thành exception hoặc result theo hợp đồng;
- tài nguyên native được giải phóng đúng cách;
- callback từ native về Java hoạt động nếu thư viện có sử dụng;
- chạy đồng thời không làm hỏng state hoặc chia sẻ buffer không an toàn.

~~~java
class NativeChecksumContractTests {

    @Test
    void computesExpectedChecksum() {
        byte[] input = "abc".getBytes(StandardCharsets.UTF_8);
        assertThat(NativeChecksum.checksum(input))
            .isEqualTo(knownChecksumForAbc());
    }
}
~~~

`knownChecksumForAbc()` là giá trị kiểm thử được tính độc lập theo thuật toán của thư viện. Không gọi chính `NativeChecksum.checksum()` để tính expected value vì như vậy test sẽ lặp lại cùng lỗi.

### 7.3. JNI metadata và Native Image

Nếu native library gọi ngược vào Java qua JNI, Native Image cần biết class/member mà mã native sẽ truy cập. Có thể cung cấp metadata JNI theo cơ chế được GraalVM hỗ trợ hoặc đăng ký bằng runtime hints khi Spring Framework API phù hợp với kiểu truy cập.

Phân biệt:

- Java gọi một `native` method đã khai báo: cần thư viện native đúng nền tảng và cách nạp library hoạt động trong executable.
- C/C++ gọi ngược vào Java class/method/field bằng JNI: cần khai báo reachability cho những kiểu và thành viên được truy cập động.
- Thư viện dùng reflection từ Java code: cần reflection metadata, không tự động được giải quyết chỉ bằng JNI metadata.

Không giả định rằng thêm một `jni-config.json` chung sẽ sửa mọi lỗi. Metadata phải khớp package, class, method signature, field và version của thư viện. Nếu vendor cung cấp reachability metadata, dùng đúng bản đi kèm dependency.

### 7.4. Native library và nền tảng triển khai

Shared library thường khác nhau theo:

- hệ điều hành: Linux, Windows, macOS;
- kiến trúc: x86_64, AArch64/ARM64;
- ABI, libc và phiên bản hệ thống;
- cách liên kết static/dynamic và dependency hệ thống.

Một `.dll` không thể thay cho `.so`; một thư viện macOS không chạy trong Linux container. Build và test native image trên môi trường tương thích với nền tảng triển khai, hoặc dùng builder/runner đã được cấu hình cho target đó.

## 8. Một contract suite cho nhiều loại tích hợp

Có thể tổ chức test theo lớp:

| Lớp test | Kiểm tra | Môi trường |
| --- | --- | --- |
| Unit test adapter | Mapping input/output, lỗi, timeout, close | JVM, dùng fake khi phù hợp |
| Library contract test | Hành vi SDK thật, reflection và provider discovery | JVM với dependency thật |
| Native contract test | Cùng hành vi qua native executable | Native Image target |
| Deployment test | Library path, resource, env, permission và container | Container/OS đích |
| Compatibility test | Nâng version dependency/GraalVM/JDK | CI theo ma trận phiên bản được hỗ trợ |

Ví dụ ma trận:

| Tích hợp | JVM test | Native test | Deployment test |
| --- | --- | --- | --- |
| Reflection codec | Encode/decode bằng SDK thật | Cùng payload qua executable | Chạy với metadata đóng gói |
| ServiceLoader provider | Provider được phát hiện và chọn đúng | Provider được tìm thấy trong binary | Kiểm tra provider descriptor/dependency |
| JNI checksum | Nạp library và so expected value | Native method và callback (nếu có) | Shared library đúng OS/CPU |
| SDK lưu trữ | Save/load, timeout, error mapping | Cùng contract với native binary | Sandbox endpoint, credential và network |

Không cần chạy mọi test ở mọi stage. Unit test nhanh có thể chạy thường xuyên; native contract test chạy ở pipeline build/release; deployment test chạy trong môi trường target hoặc container tương thích.

## 9. Dùng reachability metadata do thư viện cung cấp

Trước khi tự thêm reflection, resource, proxy, serialization hoặc JNI hints, hãy kiểm tra dependency có cung cấp metadata không.

Metadata có thể nằm trong thư viện theo cấu trúc mà Native Image nhận diện, hoặc được cung cấp qua GraalVM Reachability Metadata Repository/Native Build Tools. Phiên bản thư viện rất quan trọng: metadata của version mới có thể không mô tả chính xác API của version cũ.

Quy trình:

1. Ghi lại tọa độ và version dependency.
2. Kiểm tra release notes/native support của vendor.
3. Kiểm tra metadata có trong artifact thực tế.
4. Build native với đúng dependency.
5. Chạy contract test trên đường reflection, service loading hoặc JNI.
6. Chỉ bổ sung hints ứng dụng khi có bằng chứng metadata còn thiếu.

Tránh copy một cấu hình reflection rộng từ bài viết cũ mà không biết class/member nào cần giữ. Metadata thừa làm tăng footprint và che khuất thay đổi API của thư viện.

## 10. Optional dependency và hai trạng thái classpath

Một số tích hợp chỉ có trong một biến thể ứng dụng. Hãy test cả khi dependency có mặt và khi nó vắng mặt.

Spring Boot có thể bảo vệ auto-configuration bằng `@ConditionalOnClass`. Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.JsonCodec")
@ImportRuntimeHints(VendorCodecHints.class)
class VendorCodecAutoConfiguration {
}
~~~

Khi SDK không có trong build classpath, cấu hình và hints của SDK không nên được áp dụng. Khi SDK có mặt, AOT xử lý cấu hình và native build phải giữ metadata cần thiết.

Test JVM có thể mô phỏng dependency vắng mặt bằng `FilteredClassLoader`:

~~~java
contextRunner
    .withClassLoader(new FilteredClassLoader("com.vendor.codec"))
    .run(context -> {
        assertThat(context).doesNotHaveBean(PayloadCodec.class);
    });
~~~

Với native image, classpath là một phần của executable. Không thể thêm SDK sau khi binary đã build rồi chỉ bật property runtime để tạo lại bean, provider hoặc metadata bị loại.

## 11. Kiểm thử lỗi và tính ổn định

Contract test cần bao gồm tình huống lỗi, không chỉ happy path:

- provider không tồn tại hoặc có nhiều provider cùng ID;
- reflection target class/method không tồn tại sau khi nâng SDK;
- native library không tìm thấy hoặc sai kiến trúc;
- thư viện trả lỗi dữ liệu, timeout, permission hoặc network;
- input rỗng, rất lớn, sai encoding hoặc dữ liệu biên;
- resource/configuration không có;
- concurrent calls và đóng tài nguyên nhiều lần.

Ví dụ kiểm tra lỗi provider:

~~~java
assertThatThrownBy(() -> compressionFactory.create("unknown"))
    .isInstanceOf(UnsupportedCompressionProviderException.class);
~~~

Ứng dụng nên chuyển lỗi thư viện ngoài thành exception/domain error có ý nghĩa, đồng thời giữ nguyên cause để chẩn đoán. Không để thông tin nhạy cảm trong exception message hoặc test report.

Đối với JNI, cần test cả input rỗng, buffer lớn và lỗi native. Nếu API có ownership của buffer/handle, contract phải nói rõ ai cấp phát, ai giải phóng và liệu có thể gọi `close()` nhiều lần hay không.

## 12. Chạy contract test trong Maven và Gradle

### 12.1. Maven

Chạy unit và JVM integration tests:

~~~bash
./mvnw test
~~~

Tạo native executable với cấu hình profile/plugin của dự án:

~~~bash
./mvnw -Pnative native:compile
~~~

Sau đó chạy native contract suite qua executable hoặc test harness được dự án cấu hình. Nếu dự án đã cấu hình native test execution của GraalVM Native Build Tools, có thể gọi goal/test phase tương ứng. Không giả định `mvn test` mặc định tự chạy test trên native image.

### 12.2. Gradle

Chạy JVM tests:

~~~bash
./gradlew test
~~~

Nếu plugin và dự án đã cấu hình native test task:

~~~bash
./gradlew nativeTest
~~~

Build native executable:

~~~bash
./gradlew nativeCompile
~~~

Tên task phụ thuộc plugin và cấu hình. Kiểm tra task list và cấu hình Native Build Tools trước khi đưa lệnh vào pipeline. Với JNI, build phải chạy trên runner có shared library đúng OS/CPU và đường dẫn loader phù hợp.

## 13. Pipeline CI cho tích hợp ngoài

Một pipeline có thể tổ chức như sau:

~~~mermaid
flowchart TB
    D["Resolve dependency versions"] --> J["JVM unit + contract tests"]
    J --> A["Spring AOT"]
    A --> N["Build Native Image"]
    N --> R["Native contract tests"]
    R --> C["Container / target OS tests"]
    C --> P["Publish artifact"]
    J --> F["Fail: fix adapter or dependency"]
    N --> F
    R --> F
    C --> F
~~~

Giữ các đầu vào có thể truy vết:

- version JDK, Spring Boot, GraalVM và Native Build Tools;
- tọa độ/version của SDK và provider;
- OS/CPU architecture của runner;
- checksum native library;
- reachability metadata đi kèm dependency;
- kết quả contract suite JVM/native.

Khi nâng version thư viện ngoài, chạy lại contract suite trước khi publish. Nếu vendor thay đổi constructor, service descriptor, native ABI hoặc metadata, test sẽ giúp phát hiện thay đổi ở ranh giới tích hợp.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| JVM pass, native báo thiếu constructor/method | Reflection metadata chưa đủ | Xem stack trace, metadata vendor và đúng member được gọi |
| `ServiceConfigurationError` hoặc không tìm thấy provider | Service descriptor/module declaration/provider không có trong build input | Kiểm tra `META-INF/services`, module descriptor và native output |
| `UnsatisfiedLinkError` | Shared library thiếu, sai tên, sai ABI hoặc loader path | Kiểm tra OS/CPU, loader path và package image |
| JNI callback không tìm thấy Java method | Thiếu JNI reachability metadata hoặc signature thay đổi | Kiểm tra class/member/signature trong JNI metadata |
| Native chạy nhưng không có resource của SDK | Resource không được đóng gói hoặc hint sai | Kiểm tra dependency JAR, resource path và metadata |
| Contract test chỉ fail trong container | Thiếu library hệ thống, quyền file, network hoặc biến môi trường | So sánh runtime image với runner và kiểm tra cấu hình triển khai |
| Test phụ thuộc thứ tự provider | Code chọn provider đầu tiên không có tiêu chí | Chọn bằng ID/priority và kiểm tra trường hợp trùng |
| Nâng SDK làm native build lỗi | API, metadata hoặc ABI thay đổi | Pin version, đọc release notes và chạy lại contract suite |

Khi điều tra, giữ lại stack trace và phiên bản dependency nhưng loại bỏ token, password, URL có credential và dữ liệu khách hàng trước khi chia sẻ log.

## 15. Checklist trước khi phát hành

- [ ] Tích hợp thư viện ngoài được đặt sau adapter/interface của ứng dụng.
- [ ] Contract mô tả input/output, lỗi, timeout và lifecycle.
- [ ] Test chạy với dependency thật, không chỉ mock SDK.
- [ ] Reflection path được gọi qua API tích hợp thực tế trên native.
- [ ] ServiceLoader tìm đúng provider và không dựa vào thứ tự ngẫu nhiên.
- [ ] JNI library đúng OS/CPU/ABI và được nạp trong môi trường đích.
- [ ] JNI callback có metadata cho Java class/member được native code truy cập.
- [ ] Resource/service descriptor cần thiết có trong artifact.
- [ ] Đã kiểm tra reachability metadata của đúng version thư viện.
- [ ] Contract suite chạy trên JVM và native executable.
- [ ] Đã kiểm tra dependency có mặt/vắng mặt nếu là optional.
- [ ] Đã chạy deployment test trong container hoặc target OS phù hợp.
- [ ] Version JDK, Spring Boot, GraalVM, SDK và native library được ghi nhận.
- [ ] Log/test report không chứa credential hoặc dữ liệu nhạy cảm.

**Ghi nhớ:** contract test xác nhận thư viện ngoài đáp ứng đúng hành vi mà ứng dụng cần. JVM test kiểm tra hợp đồng cơ bản; native contract test xác nhận reflection, service loading, JNI và resource hoạt động sau AOT/Native Image; deployment test xác nhận shared library và môi trường target phù hợp. Hãy kiểm thử đường tích hợp thật, dùng metadata đúng version và giữ phạm vi hints ở mức cần thiết.

## Tài liệu tham khảo

- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata cho reflection, resource, proxy, serialization và JNI.
- [GraalVM Native Image — JNI](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): hỗ trợ JNI và các yêu cầu metadata khi native code truy cập Java.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): tích hợp Maven/Gradle, native test và reachability metadata.
- [Java ServiceLoader API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): cơ chế tìm và nạp provider theo service interface.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): API runtime hints và tích hợp Spring AOT.
