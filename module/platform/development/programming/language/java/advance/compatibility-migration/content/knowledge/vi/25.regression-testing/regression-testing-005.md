# Kiểm thử hợp đồng API, SPI và plugin của bên thứ ba

Khi nâng cấp JDK, framework hoặc thư viện Java, hệ thống có thể khởi động bình thường nhưng một plugin được biên dịch từ nhiều năm trước chỉ thất bại khi người dùng gọi đúng một tính năng. Một thư viện public API thay đổi chữ ký method khiến client cũ báo `NoSuchMethodError`; một interface SPI thêm abstract method khiến provider cũ gặp `AbstractMethodError`; hoặc một provider được đăng ký bằng `META-INF/services` không được tìm thấy khi chuyển từ classpath sang module path.

Những sự cố như vậy thường **không được phát hiện bởi unit test chỉ chạy với các class được biên dịch lại cùng một phiên bản**. Bài học này tập trung vào **kiểm thử hợp đồng API, SPI và plugin của bên thứ ba** trong ngữ cảnh **Java Advance Compatibility Migration**: xác định ranh giới hợp đồng, lưu bản baseline, chạy ma trận giữa các artifact cũ và mới, kiểm tra cơ chế discovery/class loading, test hành vi và thiết kế rollout hoặc rollback khi không thể sửa mọi plugin cùng lúc.

Một nguyên tắc xuyên suốt: **“compile được” khác “binary cũ liên kết được” và cũng khác “hành vi vẫn đúng”**.

## 1. Phân biệt API, SPI và plugin

Ba thuật ngữ có liên quan nhưng vai trò không giống nhau.

### 1.1. API — Application Programming Interface

API là phần mà thư viện/nền tảng **cung cấp cho người gọi**: public types, methods, constructors, fields, annotations, exceptions, module exports và các hợp đồng dữ liệu.

Ví dụ một thư viện cung cấp:

~~~java
package com.acme.payments.api;

import java.math.BigDecimal;

public interface PriceCalculator {
    BigDecimal calculate(String productId, int quantity);
}
~~~

Ứng dụng bên ngoài gọi `PriceCalculator.calculate`. Nếu thư viện nâng cấp đổi kiểu trả về hoặc xóa method mà không có cầu nối nhị phân, những class client đã compile từ phiên bản cũ có thể không còn liên kết được ở runtime.

API cũng có thể là HTTP, gRPC, GraphQL hoặc event contract. Tuy nhiên trong hệ sinh thái Java, **binary API** còn bao gồm các tên class và JVM method descriptors không nhìn thấy hết từ JSON/OpenAPI schema.

### 1.2. SPI — Service Provider Interface

SPI là phần mà nền tảng **yêu cầu bên mở rộng phải triển khai**. Ví dụ:

~~~java
package com.acme.reports.spi;

public interface ReportPlugin {
    String id();
    byte[] render(byte[] request);
}
~~~

Host định nghĩa `ReportPlugin`; một nhà cung cấp bên thứ ba tạo class implement interface và đăng ký provider. SPI có vẻ giống API về cú pháp, nhưng thay đổi ở SPI gây tác động **ngược chiều**: host mới phải tiếp tục chạy plugin do bên ngoài biên dịch từ SPI cũ.

Một method mới trên SPI không thể tự coi là an toàn chỉ vì host đã được biên dịch lại.

### 1.3. Plugin — đơn vị mở rộng có vòng đời riêng

Plugin thường gồm:

- Implementation classes cho một hoặc nhiều SPI.
- Descriptor hoặc registration metadata.
- Dependencies riêng.
- Phiên bản plugin và version range hỗ trợ host.
- Cấu hình, resources, schema hoặc permissions.
- Cơ chế discovery/loading do host quyết định.
- Các callback như initialize, execute, shutdown.

Ví dụ: JDBC driver, Java logging provider, annotation processor, IDE extension, build tool plugin, authentication adapter, report generator hoặc hệ thống plugin nội bộ.

Một plugin có thể được phát hành, tải và nạp vào JVM **độc lập với host**. Đây là lý do test chỉ với plugin viết trong cùng repository chưa đủ.

### 1.4. So sánh các ranh giới

| Loại hợp đồng | Ai định nghĩa? | Ai thực hiện? | Lỗi nổi bật |
|---|---|---|---|
| Public Java API | Library/platform | Client/application | `NoSuchMethodError`, `IllegalAccessError` |
| SPI | Host/platform | Provider/plugin | `AbstractMethodError`, contract violation |
| Plugin packaging | Provider + host conventions | Plugin loader | `ClassNotFoundException`, `ServiceConfigurationError` |
| HTTP/event API | Service producer/provider | Consumer/client | Schema/semantic mismatch, status/data khác |
| JVM/module boundary | JDK + module author | Class/module loader | `ResolutionException`, reflective access failure |

Trong Java migration, nên test cả **API được gọi** và **SPI được implement**. Test chiều này không thay thế chiều kia.

## 2. Các chiều tương thích phải được kiểm thử

Ít nhất có năm chiều:

1. **Source compatibility:** mã nguồn của consumer/plugin cũ có compile lại với API mới không?
2. **Binary compatibility:** bytecode đã biên dịch với API/SPI cũ có link và chạy trên library/host mới không?
3. **Behavioral/semantic compatibility:** dù lời gọi thành công, kết quả, side effects và exception contract còn đúng không?
4. **Discovery/loading compatibility:** plugin cũ còn được tìm thấy và nạp trong môi trường mới không?
5. **Operational/security compatibility:** lifecycle, thread model, permissions, logging, resource limits và cấu hình còn hợp lệ không?

Một ví dụ: host thêm default method vào SPI. Plugin cũ có thể vẫn load và gọi method khác bình thường; nhưng default behavior mới có thể gây sai logic nghiệp vụ. Test binary có thể pass trong khi behavioral contract fail.

### 2.1. Cách gọi “compatible” phải có phạm vi

Không nên ghi chung chung:

~~~text
Plugin compatible: YES
~~~

Nên ghi:

~~~text
Provider old-plugin-1.4.2:
  - Loads on host 3.0 / JDK 21: PASS
  - Service discovery: PASS
  - Required callbacks: PASS
  - Optional capability negotiation: FAIL
  - Shutdown/reload: NOT TESTED
  - Binary/API diff: REVIEWED
~~~

Một kết luận tương thích có giá trị khi gắn với **artifact, class loader, JDK, host version, môi trường và các scenario đã được chạy**.

## 3. Ma trận phiên bản API và SPI

Đặt:

- `A1`: API/SPI contract version cũ.
- `A2`: API/SPI contract version mới.
- `P1`: plugin/consumer compile với A1.
- `P2`: plugin/consumer compile với A2.
- `H1`: host version cũ.
- `H2`: host version mới.

Ma trận quan trọng:

| Artifact plugin | Runtime host | Ý nghĩa |
|---|---|---|
| P1 | H1 | Baseline |
| P1 | H2 | **Backward runtime compatibility:** host mới chạy plugin cũ |
| P2 | H2 | Plugin mới chạy host mới |
| P2 | H1 | **Forward compatibility:** plugin mới chạy host cũ, quan trọng khi hỗ trợ downgrade/rollout lệch phiên bản |

Ở bước P1→H2, **không được biên dịch lại P1** trước khi test. Nếu rebuild plugin với API mới thì đã xóa mất điều kiện quan trọng nhất: binary thực tế đang được khách hàng dùng.

### 3.1. API client và SPI provider đi hai chiều khác nhau

Với API thông thường, library mới phải phục vụ client cũ.

Với SPI, host mới có thể phải sử dụng implementation cũ.

~~~text
API:
  Client v1 (caller) ----> Library API v2 (callee)

SPI:
  Host v2 (caller) ------> Plugin v1 (implementation)

Plugin runtime:
  Host v2 + SPI API v2 + Plugin v1 + Dependencies
~~~

Nếu chỉ kiểm tra client source compile lại, chưa chứng minh plugin cũ vẫn chạy.

## 4. Những thay đổi API có thể phá binary linkage

Java binary compatibility có quy tắc chi tiết. Một số thay đổi source trông nhỏ nhưng rất nguy hiểm với bytecode cũ.

### 4.1. Đổi kiểu trả về là thay method descriptor

API cũ:

~~~java
public interface PriceService {
    long priceInCents(String sku);
}
~~~

API mới:

~~~java
public interface PriceService {
    java.math.BigDecimal priceInCents(String sku);
}
~~~

Bytecode client cũ tham chiếu method descriptor với kết quả `long`; API mới chỉ cung cấp descriptor với kết quả `BigDecimal`. Khi lời gọi được liên kết ở runtime, có thể gặp `NoSuchMethodError`.

Nếu cần chuyển, phương án cầu nối có thể là giữ method cũ và thêm method mới tên khác:

~~~java
public interface PriceService {
    @Deprecated
    long priceInCents(String sku);

    java.math.BigDecimal precisePrice(String sku);
}
~~~

Sau đó lên kế hoạch deprecation qua nhiều release, có conversion và test precision/overflow. **Không giữ song song hai method cùng tên và cùng parameter list nhưng khác return type trong Java source thông thường**; Java không overload theo kiểu trả về.

### 4.2. Đổi static/instance có thể gây linkage error

Ví dụ thay một instance method thành static method giữ tên và parameters. Client cũ có instruction bytecode kỳ vọng instance invocation. Runtime có thể phát sinh `IncompatibleClassChangeError` hoặc lỗi linkage liên quan khi invocation semantics không còn phù hợp.

Test nguồn biên dịch lại không đủ; cần một binary fixture được compile trước khi đổi API.

### 4.3. Giảm visibility hoặc đổi owner type

Thay `public` thành package-private/protected, hoặc chuyển method sang nơi caller cũ không được phép truy cập, có thể gây `IllegalAccessError`. Một method bị xóa hoặc không còn được tìm trong hierarchy có thể gây `NoSuchMethodError`.

Với module path, package không còn được `exports` cho consumer còn có thể khiến code không đọc được API dù method vẫn `public`.

### 4.4. Thêm overload có thể làm source khác binary

API mới thêm overload:

~~~java
void send(String message);
void send(CharSequence message);
~~~

Bản thân thêm overload thường không bắt buộc phá bytecode đã compile với `send(String)`. Nhưng overload resolution khi **compile lại** có thể chọn method khác trong những tình huống liên quan `null`, varargs, generics hoặc các kiểu mới được thêm.

Nếu thêm hai overload không liên quan như `send(String)` và `send(byte[])`, lời gọi `send(null)` có thể trở nên ambiguous ở compile time. Đây là source incompatibility ngay cả khi binary cũ vẫn liên kết.

## 5. Thay đổi SPI interface: rủi ro chỉ xuất hiện khi gọi method

Giả sử SPI v1:

~~~java
package com.acme.spi;

public interface Exporter {
    byte[] export(String documentId);
}
~~~

Plugin v1:

~~~java
package com.thirdparty.plugin;

import com.acme.spi.Exporter;

public final class LegacyExporter implements Exporter {
    @Override
    public byte[] export(String documentId) {
        return documentId.getBytes(
            java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Plugin v1 đã compile thành `legacy-exporter.jar` và được khách hàng triển khai nhiều tháng trước.

### 5.1. Host v2 thêm abstract method

SPI v2:

~~~java
public interface Exporter {
    byte[] export(String documentId);

    boolean supportsFormat(String format);
}
~~~

Plugin cũ không có `supportsFormat`. Trong một số tình huống, class cũ vẫn có thể được nạp và method `export` vẫn chạy, vì cơ chế binary compatibility của interface evolution cho phép trì hoãn một số lỗi. Nhưng nếu host v2 gọi:

~~~java
Exporter plugin = loadPlugin();
boolean supported = plugin.supportsFormat("pdf");
~~~

thì có thể xuất hiện:

~~~text
java.lang.AbstractMethodError
~~~

**Điểm mấu chốt:** test chỉ khởi tạo plugin hoặc gọi `export` không phát hiện method SPI mới chưa được implementation cũ cung cấp. Cần test từng capability và callback mà host mới dự kiến gọi.

### 5.2. Dùng default method có thể tạo cầu nối

SPI v2 có thể khai báo:

~~~java
public interface Exporter {
    byte[] export(String documentId);

    default boolean supportsFormat(String format) {
        return "plain-text".equals(format);
    }
}
~~~

Plugin cũ không bắt buộc phải thêm source implementation chỉ để có method này. Tuy nhiên:

- Default behavior có thể không phù hợp plugin thực tế.
- Một implementor có interface hierarchy phức tạp có thể gặp conflict giữa các default methods.
- Một default method có thể thay ý nghĩa method resolution ở runtime.
- Không dùng default để “tự báo hỗ trợ” cho tính năng mà plugin thực tế không xử lý.

Trong một số cấu trúc interface inheritance, khi hai default methods không liên quan trở nên xung đột, lời gọi có thể dẫn đến `IncompatibleClassChangeError`. Cần kiểm tra các class triển khai thực tế, không chỉ SPI độc lập.

### 5.3. Nhiều version SPI có thể cần adapter

Nếu thay đổi quá lớn, một lựa chọn là tạo interface mới thay vì sửa phá vỡ contract cũ:

~~~java
public interface ExporterV1 {
    byte[] export(String documentId);
}

public interface ExporterV2 {
    String id();
    byte[] export(ExportRequest request);
    java.util.Set<String> supportedFormats();
}
~~~

Host mới có thể hỗ trợ cả hai loại trong một cửa sổ chuyển đổi và dùng adapter để chuyển `ExporterV1` sang model nội bộ. Tuy nhiên adapter chỉ đúng nếu semantic của dữ liệu cũ có thể được bảo toàn.

Không mặc định tên có hậu tố `V2` là đủ: còn cần plugin discovery, dependency isolation, lifecycle và policy loại bỏ V1.

## 6. Thêm method, constructor, field: test binary, không chỉ compile

Một số trường hợp thường gặp:

| Thay đổi | Source compatibility | Binary/runtime risk |
|---|---|---|
| Thêm public method mới vào class | Thường ổn | Có thể ảnh hưởng method resolution/inheritance ở trường hợp đặc biệt |
| Xóa public method | Client cũ fail khi compile lại | `NoSuchMethodError` khi runtime sử dụng |
| Đổi descriptor của method | Client source cần sửa | Binary reference cũ không còn |
| Đổi static ↔ instance | Source invocation thay | Linkage/ICCE khi runtime |
| Giảm access visibility | Client mới không compile | `IllegalAccessError` |
| Thêm abstract method vào SPI interface | Implementor source phải triển khai | `AbstractMethodError` khi gọi trên plugin cũ |
| Thêm default method vào SPI | Thường giảm gánh nặng implementor | Default conflict/semantic change |
| Đổi public constructor | Consumer source phải đổi | `NoSuchMethodError` khi khởi tạo |
| Đổi field public thành method | Source client phải đổi | `NoSuchFieldError` |
| Đổi class thành interface hoặc ngược lại | Có thể phá toàn bộ consumer | `IncompatibleClassChangeError` |
| Đổi generic parameterization | Có thể đổi source type checking | Erasure/bridge/binary descriptor cần xem riêng |

Các quy tắc thực tế phức tạp hơn bảng tóm tắt. Khi nâng thư viện có nhiều consumers, nên dùng công cụ so sánh binary API và **chạy binary fixtures** để chứng minh đúng tổ hợp.

## 7. Generics, erasure và bridge methods

Java generics được thực thi chủ yếu bằng **type erasure**; JVM method descriptors thường phản ánh erased types, còn generic signatures có thể lưu trong metadata.

Ví dụ:

~~~java
public interface Store<T> {
    T load(String id);
}
~~~

Một implementation:

~~~java
public final class StringStore implements Store<String> {
    @Override
    public String load(String id) {
        return id;
    }
}
~~~

Compiler có thể sinh bridge method để giữ polymorphism với erased interface signature. Nếu nâng library làm đổi hierarchy, bounds hoặc covariant return types, có thể thay bridge methods và binary linkage.

Cần kiểm tra cả:

- Reflection-based tools đọc generic signatures.
- Binary method descriptors (gồm kiểu trả về).
- Bridge/synthetic methods.
- Interface dispatch.
- Source compilation của plugin bên thứ ba.
- Kotlin/Scala/Groovy plugins nếu hệ thống mở rộng không chỉ bằng Java source.

Công cụ:

~~~bash
javap -classpath api.jar -p -s com.acme.spi.Store
javap -classpath plugin.jar -p -v com.thirdparty.StringStore
~~~

`javap -s` cho phép xem descriptor; `-v` hiển thị thông tin bytecode chi tiết. Kết quả chỉ là một phần của bằng chứng; không thay thế runtime dispatch test.

## 8. Hợp đồng exception và behavioral semantics

API có thể vẫn binary-compatible nhưng thay đổi contract:

~~~java
PaymentResult authorize(PaymentRequest request);
~~~

Version cũ trả `PaymentResult.rejected` cho input không hợp lệ, version mới ném `IllegalArgumentException`. Mọi class vẫn compile và link, nhưng consumer có thể không bắt exception hoặc bỏ lỡ trạng thái giao dịch.

Cần kiểm tra:

- Loại exception checked/unchecked và thời điểm phát sinh.
- Mapping lỗi thành HTTP status hoặc plugin error callback.
- Có retry được không; có nguy cơ side effect lặp không.
- Nullable result hay `Optional`.
- Thứ tự callback và transaction boundaries.
- Encoding, timezone, number precision và enum values.
- Thread-safety, reentrancy và blocking behavior.
- Resource ownership: ai mở/đóng stream, connection, executor.
- Timeout/cancellation behavior và shutdown.

Một **contract test** nên encode các điều kiện này thành assertions, không chỉ xác minh class/method tồn tại.

## 9. Thiết kế một SPI dễ kiểm thử

Xét ví dụ plugin tạo báo cáo:

~~~java
package com.acme.reports.spi;

public interface ReportPlugin {
    String id();

    byte[] render(ReportRequest request);

    default boolean supports(String outputFormat) {
        return "text/plain".equals(outputFormat);
    }
}
~~~

`ReportRequest` nên là một DTO/hợp đồng được version hóa rõ, ví dụ:

~~~java
package com.acme.reports.spi;

public final class ReportRequest {
    private final String reportId;
    private final String outputFormat;

    public ReportRequest(String reportId, String outputFormat) {
        this.reportId = reportId;
        this.outputFormat = outputFormat;
    }

    public String getReportId() {
        return reportId;
    }

    public String getOutputFormat() {
        return outputFormat;
    }
}
~~~

SPI cần quy định bằng tài liệu:

1. `id()` có được trả `null` không? Có yêu cầu unique không?
2. `render()` có thể block lâu không; timeout do ai quản lý?
3. Input có immutable không và plugin được phép giữ reference không?
4. Khi không hỗ trợ format, plugin ném exception hay trả kết quả nào?
5. Resource tạo ra phải được close bởi host hay plugin?
6. Plugin instance có được gọi đồng thời từ nhiều thread không?
7. Có thể gọi `render` trước `initialize` hoặc sau `close` không?
8. Host có cam kết binary compatibility trong bao nhiêu major/minor?
9. Có những JDK versions nào được hỗ trợ?
10. Service discovery dùng `ServiceLoader`, module descriptor, registry hay loader tùy chỉnh?

Một SPI không có behavioral contract khiến mỗi plugin tự diễn giải khác nhau; migration sẽ rất khó xác nhận “tương thích”.

## 10. Kiểm thử provider contract bằng bộ test dùng chung

Thay vì chỉ kiểm tra plugin của nhóm mình, có thể xây một **provider conformance test suite** mà mọi plugin cần pass.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

abstract class ReportPluginContract {

    protected abstract ReportPlugin createPlugin();

    @Test
    void pluginHasStableId() {
        ReportPlugin plugin = createPlugin();
        assertNotNull(plugin.id());
        assertFalse(plugin.id().isBlank());
    }

    @Test
    void supportsTextFormat() {
        ReportPlugin plugin = createPlugin();
        assertTrue(plugin.supports("text/plain"));
    }

    @Test
    void rendersNonNullPayloadForValidRequest() {
        ReportPlugin plugin = createPlugin();
        ReportRequest request =
            new ReportRequest("R-100", "text/plain");

        byte[] bytes = plugin.render(request);
        assertNotNull(bytes);
        assertTrue(bytes.length > 0);
    }
}
~~~

`String.isBlank` yêu cầu Java 11+, nên nếu contract test module phải chạy trên Java 8, thay bằng logic tương đương. Test bên trên minh họa cách viết trên Java mới, không áp dụng cho mọi baseline.

Implementation test:

~~~java
class LegacyReportPluginTest extends ReportPluginContract {
    @Override
    protected ReportPlugin createPlugin() {
        return new LegacyReportPlugin();
    }
}
~~~

Bộ test này chỉ có ý nghĩa khi plugin test được compile/run với versions được chọn rõ. Nếu `LegacyReportPlugin` được recompile cùng test trên SPI v2, ta chưa chứng minh binary artifact v1 tương thích. Đối với migration, cần thêm **test load JAR đã compile từ SPI cũ**.

### 10.1. Contract test không nên dựa vào implementation internals

Chỉ assert những điều mà SPI thật sự cam kết:

- Output format và semantic.
- Required callback order.
- Input validation và failure mode.
- Resource ownership.
- Thread-safety khi contract có quy định.
- Execution timeout nếu có SLA.

Không assert thứ tự internal method calls, tên private field hay class loader implementation detail nếu chúng không phải hợp đồng. Nếu test buộc plugin làm đúng một cách triển khai duy nhất, bộ test trở thành implementation test chứ không còn contract test.

## 11. Binary fixture: nguyên tắc quan trọng nhất

Để test binary compatibility của Java API/SPI, giữ **JAR do compiler cũ tạo ra** làm fixture.

~~~text
fixtures/
  api-v1.jar
  old-plugin-v1.jar       # Compile sẵn với api-v1.jar
  old-client-v1.jar       # Compile sẵn với api-v1.jar
target/
  api-v2.jar
  host-v2.jar
~~~

Quy trình:

1. Compile `old-plugin-v1.jar` với `api-v1.jar`, lưu artifact nguyên vẹn.
2. Compile `host-v2.jar` và `api-v2.jar` theo target.
3. Chạy một process mới trên JDK target với `api-v2.jar + host-v2.jar + old-plugin-v1.jar`.
4. Đảm bảo `api-v1.jar` không vô tình nằm trong classpath.
5. Load plugin bằng đúng cơ chế production.
6. Gọi các method/callback hiện tại và mới mà host thực sự sử dụng.
7. Assert cả kết quả, exception, resource cleanup và thread behavior.
8. Lưu log class loading khi cần chẩn đoán.

Nếu test tự compile lại old plugin với api-v2.jar, nó có thể báo compile error hoặc được auto-fixed và không còn đại diện cho plugin thực tế đang deploy.

### 11.1. Vì sao cần một JVM process riêng?

Nếu JUnit runner đang nạp `api-v1.jar` từ test classpath trước rồi test cố nạp `api-v2.jar`, class loader và cached classes có thể làm kết quả sai. Một subprocess với classpath được dựng minh bạch giúp mô phỏng packaging/runtime tốt hơn.

Lưu binary fixture trong kho artifact hoặc repository theo chính sách; ghi checksum, compiler JDK, release target và dependency list để có thể tái tạo.

## 12. Ví dụ test matrix chạy artifact cũ trên host mới

Giả sử:

~~~text
report-api-v1.jar
report-plugin-v1.jar
report-api-v2.jar
report-host-v2.jar
~~~

Một lệnh khởi chạy minh họa trên Linux/macOS:

~~~bash
java -cp "report-api-v2.jar:report-host-v2.jar:report-plugin-v1.jar" \
  com.acme.reports.host.PluginContractRunner
~~~

Trên Windows, dùng dấu `;` thay `:` trong classpath. Trong dự án thật còn cần dependencies của plugin và host.

Không đặt cả `report-api-v1.jar` lẫn `report-api-v2.jar` trên cùng **flat classpath** rồi suy luận class nào sẽ được nạp. Việc nạp class đầu tiên theo loader/order có thể che lỗi compatibility hoặc tạo phiên bản bất định.

### 12.1. Biến thể cần chạy

- Old host + old plugin: baseline.
- New host + old plugin: backward compatibility.
- New host + new plugin: target.
- Old host + new plugin: chỉ khi có yêu cầu rollback/forward compatibility.
- New host + plugin bị thiếu dependency: error handling.
- New host + plugin có duplicate API JAR: loader isolation.
- New host + plugin phát exception trong init: cleanup.
- New host + plugin không hỗ trợ capability mới: graceful fallback.

Khi cập nhật JDK, lặp lại những tổ hợp thực sự được cam kết trên từng JDK runtime được hỗ trợ.

## 13. ServiceLoader và META-INF/services

Java `ServiceLoader` là một cơ chế service provider discovery phổ biến.

Giả sử SPI:

~~~java
package com.acme.spi;

public interface TextFilter {
    String apply(String input);
}
~~~

Plugin:

~~~java
package com.thirdparty.filters;

import com.acme.spi.TextFilter;

public final class UppercaseFilter implements TextFilter {

    public UppercaseFilter() {
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Trong provider JAR tạo file:

~~~text
META-INF/services/com.acme.spi.TextFilter
~~~

Nội dung:

~~~text
com.thirdparty.filters.UppercaseFilter
~~~

Host có thể tìm providers:

~~~java
ServiceLoader<TextFilter> loader =
    ServiceLoader.load(TextFilter.class);

for (TextFilter filter : loader) {
    System.out.println(filter.apply("sample"));
}
~~~

Để code compile, thêm import `java.util.ServiceLoader` phù hợp.

### 13.1. Điều kiện discovery thành công

- Provider JAR thực sự nằm trong classpath/module path phù hợp.
- Service descriptor nằm đúng entry path và chứa provider class name hợp lệ.
- Provider class có thể được nạp/khởi tạo theo quy tắc của `ServiceLoader`.
- Provider thực sự là subtype của service interface **được host nhìn thấy**.
- Dependencies của provider đủ và tương thích.
- Class loader/module layer dùng để discovery có thể nhìn thấy provider.
- Không có lỗi trong static initialization/constructor/factory.

Provider được thấy trong `jar tf` không đồng nghĩa host tìm được nó qua `ServiceLoader`.

### 13.2. Những thay đổi có thể phá descriptor

- Rename package/class của provider.
- Đổi tên SPI package.
- Chuyển từ classpath sang JPMS mà không cập nhật module declarations.
- Shading mà không merge `META-INF/services`.
- Plugin bundle bị tái đóng gói làm mất metadata.
- Provider không còn public/no-arg constructor trong tình huống classpath cần nó.
- Provider JAR bị load bởi class loader không thấy shared SPI.

### 13.3. Test lỗi ServiceLoader

Nên có fixture cho:

- Descriptor thiếu.
- Class name không tồn tại.
- Provider không implement SPI.
- Constructor lỗi.
- Static initializer lỗi.
- Thiếu dependency transitive.
- Nhiều providers với thứ tự không đảm bảo.
- Provider bị trùng registration.
- Provider `id()` trùng business identity.

`ServiceConfigurationError` là một dạng lỗi cần test riêng; không nên nuốt hoàn toàn lỗi chỉ để host tiếp tục chạy mà không biết mất chức năng.

## 14. JPMS service contracts: uses/provides

Với named modules, service registration có thể nằm trong `module-info.java`.

API module:

~~~java
module com.acme.text.api {
    exports com.acme.spi;
}
~~~

Provider module:

~~~java
module com.thirdparty.filter {
    requires com.acme.text.api;
    provides com.acme.spi.TextFilter
        with com.thirdparty.filters.UppercaseFilter;
}
~~~

Host module:

~~~java
module com.acme.text.host {
    requires com.acme.text.api;
    uses com.acme.spi.TextFilter;
}
~~~

Đây là ví dụ cấu trúc module; bản triển khai thực tế cần đủ source/module path và đáp ứng các quy tắc provider của phiên bản Java mục tiêu.

### 14.1. Migration classpath → module path không chỉ đổi option

Khi chuyển sang named modules, cần xét:

- Module names có ổn định không.
- `requires`/`exports`/`opens` và readability.
- `uses`/`provides` declarations.
- Module graph resolution và root modules.
- Automatic modules và những giới hạn của chúng.
- Split packages gây conflict.
- Reflection/framework injection cần mở package.
- Provider visibility trong module layer phù hợp.
- Thay đổi behavior của context class loader.

Một JAR có descriptor `META-INF/services` có thể hoạt động trên classpath, nhưng tổ hợp module path với named modules có yêu cầu discovery khác. Hãy test đúng launch mode được dùng trong production.

### 14.2. Không nhầm public class với exported package

Trong JPMS, một class `public` trong named module chưa chắc được module khác truy cập nếu package không được export. Với reflection sâu, `opens` và access rules có ý nghĩa khác `exports`. Đừng thêm `--add-opens ...=ALL-UNNAMED` toàn cục nếu có thể sửa module descriptor hoặc library theo hướng phù hợp hơn.

## 15. Class loader là một phần của plugin contract

Trong JVM, định danh của class không chỉ là binary name; **defining class loader** cũng tham gia xác định class identity.

Giả sử host nạp:

~~~text
com.acme.spi.TextFilter (HostClassLoader)
~~~

Plugin loader lại nạp bản riêng:

~~~text
com.acme.spi.TextFilter (PluginClassLoader)
~~~

Hai class có cùng tên nguồn nhưng không nhất thiết là cùng runtime type. Plugin có thể implement interface thuộc class loader riêng, khiến phép cast ở host thất bại:

~~~text
java.lang.ClassCastException
~~~

hoặc `ServiceLoader` báo provider không phải subtype hợp lệ.

### 15.1. Parent-first và child-first

Một plugin system có thể dùng:

- **Parent-first:** ưu tiên API/classes của parent, thường hữu ích để chia sẻ SPI contract.
- **Child-first:** ưu tiên dependencies/plugin classes riêng, có thể giảm xung đột dependency.
- **Selective delegation:** chia sẻ SPI/API ở parent, cô lập implementation libraries ở child.

Không có mô hình nào tự đúng cho mọi plugin platform. Nhưng **SPI API mà host và plugin cùng cast/gọi phải có chính sách loader identity rõ ràng**.

Ví dụ sơ đồ:

~~~text
Boot/Platform Classes
          |
          v
Host ClassLoader
  +-- report-api.jar      <---- shared SPI types
  +-- host-core.jar
          |
          +----------------------------+
          |                            |
          v                            v
 PluginClassLoader A            PluginClassLoader B
  +-- plugin-A.jar                 +-- plugin-B.jar
  +-- dependency-A.jar             +-- dependency-B.jar
~~~

Nếu plugin A và B dùng hai phiên bản khác nhau của cùng library nội bộ, class loader isolation có thể cần thiết. Nếu cả hai mang bản sao SPI API không tương thích, sự cố identity vẫn xảy ra.

### 15.2. Thread Context Class Loader

Một số library và `ServiceLoader` có thể dựa vào thread context class loader (TCCL). Khi host đổi executor/thread model hoặc module configuration, service discovery/resource lookup có thể bị ảnh hưởng.

Ví dụ quan sát:

~~~java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println(contextLoader);
~~~

Contract nên quy định plugin được gọi dưới class loader context nào, ai restore TCCL sau callback và liệu plugin có được tạo thread riêng hay không. Nếu set TCCL tạm thời, phải restore trong `finally` để không làm rò context sang task khác.

## 16. Plugin lifecycle cũng phải được kiểm thử

Một plugin thường có nhiều hơn một method xử lý:

~~~text
DISCOVERED
    |
    v
VALIDATED
    |
    v
INITIALIZED
    |
    v
ACTIVE ----> QUIESCING ----> STOPPED
    |
    +----> FAILED / DISABLED
~~~

Các callback có thể là:

- `initialize(PluginContext)`.
- `start()`.
- `execute(request)`.
- `onConfigurationChanged(...)`.
- `stop()` / `close()`.
- `health()`.

Hợp đồng cần rõ:

- Callback nào chạy đúng một lần, callback nào có thể lặp?
- Có được gọi song song không?
- Context có còn hợp lệ sau `stop` không?
- Init lỗi thì host có gọi cleanup không?
- Thread/executor do plugin tạo sẽ được dừng thế nào?
- Plugin có được reload/upgrade không cần restart JVM?
- Resource files, sockets, classloaders có được đóng để tránh memory leak không?
- Một plugin chậm/hỏng có làm toàn host bị treo không?

Một unit test `new Plugin().execute()` không kiểm tra những điều này. Test upgrade phải đi qua **cùng lifecycle manager** đang dùng trong production.

## 17. Cấp phát, timeout và thread-safety của plugin

Một API có thể giữ nguyên chữ ký nhưng host mới thay concurrency policy. Ví dụ host v1 gọi mỗi plugin từ một thread; host v2 gọi đồng thời để tăng throughput.

Nếu SPI không cam kết thread-safe mà host thay đổi cách gọi, plugin cũ có thể lỗi race condition dù không có binary incompatibility.

Cần test:

- Concurrent calls tới cùng plugin instance.
- Reentrancy/callback nested.
- Cancellation/interruption semantics.
- Timeout và retry.
- Shared mutable state.
- Backpressure và resource quotas.
- JDBC pool, network client hoặc file descriptor limits.
- Proper shutdown và executor lifecycle.

Nếu hệ thống dùng virtual threads hoặc async/reactive framework sau Java migration, coi đó là **thay đổi concurrency contract** cần test riêng, không mặc định plugin cũ tương thích vì tất cả method signatures vẫn giữ nguyên.

## 18. Java agents và bytecode instrumentation là plugin đặc biệt

Một Java agent có thể được nạp lúc startup:

~~~bash
java -javaagent:/opt/agents/monitoring-agent.jar \
  -jar application.jar
~~~

Agent được viết theo cơ chế Instrumentation API, có thể hook vào class loading, redefine/transform classes và phụ thuộc bytecode libraries.

Khi nâng JDK:

- Agent cũ có thể không hiểu classfile version mới.
- JVM encapsulation hạn chế reflective access.
- Transformer có thể không tương thích implementation của JDK/framework mới.
- Agent config hoặc startup options có thể khác.
- Performance và observability có thể thay đổi.

Test agent không chỉ là chạy `java -version`. Cần chạy **cùng agent artifact** với application artifact/JDK target, thực hiện các luồng bị instrument và kiểm tra startup, tracing, classloading, latency, shutdown.

Không tắt agent production để “làm green” migration mà không có kế hoạch observability/security thay thế.

## 19. Build tool plugins cũng có hợp đồng SPI

Maven plugin, Gradle plugin và annotation processor là những mở rộng của build ecosystem. Nâng JDK/Maven/Gradle có thể phá plugin mặc dù business code không đổi.

### 19.1. Maven plugin

Một Maven plugin phụ thuộc Maven APIs, Plexus/classloading và lifecycle/configuration. Test cần xác minh:

- Plugin goal thực sự được thực thi.
- Tên/kiểu parameters và default values còn đúng.
- Plugin dependencies được resolve.
- Java runtime chạy Maven phù hợp.
- Generated sources/resources/output layout không đổi ngoài chủ đích.
- Exit code và warning/error behavior.
- Plugin có dùng JDK internal API hoặc bytecode library cũ không.

Một lệnh `./mvnw --version` pass không chứng minh các plugin goals quan trọng pass.

### 19.2. Gradle plugin

Gradle plugin phụ thuộc Gradle API và đôi khi Groovy/Kotlin DSL, configuration cache, task inputs/outputs, Java toolchain. Khi nâng Gradle Wrapper/JDK, cần chạy chính những tasks plugin đăng ký, không chỉ `help`.

Kiểm tra:

- Plugin application và extension configuration.
- Task names, inputs/outputs và cacheability.
- Gradle API/deprecated APIs.
- Provider/property lazy configuration.
- Configuration phase vs execution phase.
- Test task behavior, generated code và packaging.
- Plugin version support matrix cho Gradle/JDK.

Không giả định một third-party Gradle plugin hỗ trợ JDK mới chỉ vì project dùng Gradle distribution có hỗ trợ JDK đó.

### 19.3. Annotation processor là compile-time plugin

Processor được gọi khi biên dịch:

~~~java
@SupportedAnnotationTypes("com.acme.annotations.AutoGenerate")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CodegenProcessor extends AbstractProcessor {
    // ...
}
~~~

Đây là minh họa API annotation processing, không phải processor hoàn chỉnh. Một processor cũ có thể phụ thuộc AST/Javac internal APIs hoặc `SourceVersion` chỉ biết release cũ.

Test cần biên dịch source sample bằng compiler target thật, kiểm tra generated output, incremental behavior, diagnostics và runtime classfile compatibility.

## 20. API của bên thứ ba: thay đổi behavior ngoài JVM

Một plugin có thể gọi API bên ngoài như REST, gRPC, database procedure hoặc message broker. Nếu host nâng HTTP client, JSON serializer hay TLS provider cùng JDK, contract ngoài JVM cũng có thể thay đổi.

Ví dụ REST:

~~~http
POST /v1/payments
Content-Type: application/json

{"orderId":"O-100","amount":"125000.00","currency":"VND"}
~~~

Consumer contract gồm:

- URL, HTTP method và status codes.
- Headers/authentication, mTLS, token scopes.
- Field names/types, optional/default/null behavior.
- Timestamp, number precision và ordering.
- Retry/idempotency semantics.
- Timeout, rate-limit và error responses.

Dùng OpenAPI/gRPC schema compatibility checks, consumer-driven contract tests, mock server và staging integration với đối tác khi thích hợp. Không chỉ test Java method signatures.

### 20.1. Mock không đủ cho mọi contract

Một fake API server có thể được viết giống assumptions của client nên test pass dù API thật đã thay. Cần có:

- Contract được đồng thuận hoặc versioned specification.
- Kiểm thử với implementation thật trong môi trường thử nghiệm.
- Fixture phản ánh response/error cũ và mới.
- Theo dõi API provider release notes/version.
- Negative cases: auth failure, timeout, rate-limit, malformed message.

Ở chiều SPI/plugin, một mock provider viết cùng version host cũng không thay thế binary plugin fixture cũ.

## 21. Kiểm thử compatibility ở nhiều tầng

Một chương trình test hợp đồng đáng tin cậy có các tầng khác nhau.

| Tầng | Kiểm tra | Phát hiện loại lỗi |
|---|---|---|
| Static API diff | Signature và public surface | Method/field/class bị xóa/đổi |
| Source compilation | Plugin/client source cũ compile với API mới | Source incompatibility |
| Binary fixture | Old JAR chạy với API/host mới | Linkage errors |
| Provider contract suite | Semantic/lifecycle của SPI | Behavior violations |
| Discovery integration | ServiceLoader, JPMS, descriptors | Provider không tìm thấy |
| Loader isolation | Flat/plugin classpath, TCCL | Class identity/duplicate dependencies |
| Integration test | DB, HTTP, broker, filesystem | External contract regressions |
| Load/concurrency test | Thread safety, latency, cleanup | Race, resource leaks |
| Deployment smoke | Artifact/launcher/JDK/agent | Packaging và runtime mismatch |
| Rollback test | Host/plugin/data cũ sau nâng | Forward compatibility gaps |

Không có một công cụ tự động duy nhất bao quát đầy đủ tất cả các tầng trên.

## 22. Static API diff bằng công cụ phù hợp

Các công cụ như **Revapi** hoặc **japicmp** có thể giúp so Java API surface giữa hai artifact. Với JDK tools, `javap` và `jdeps` cũng hữu ích.

Ví dụ:

~~~bash
javap -classpath api-v1.jar -public com.acme.spi.ReportPlugin
javap -classpath api-v2.jar -public com.acme.spi.ReportPlugin

javap -classpath api-v1.jar -s com.acme.spi.ReportPlugin
javap -classpath api-v2.jar -s com.acme.spi.ReportPlugin
~~~

Dùng tooling API diff trong CI để phân loại binary/source incompatibilities theo release policy. Cấu hình và khả năng phát hiện của từng tool cần tham chiếu đúng phiên bản tool.

Các giới hạn của static diff:

- Không biết hành vi business có còn đúng không.
- Không chứng minh ServiceLoader/JPMS loader có thấy plugin không.
- Không kiểm tra external files/config/secrets.
- Không tự biết một method bị bỏ là intentional breaking change đã phê duyệt hay bug.
- Không quan sát callback order, thread-safety, retry hoặc resource cleanup.

### 22.1. jdeps có ích nhưng không phải bộ giải quyết động

~~~bash
jdeps --summary plugin.jar
jdeps --jdk-internals plugin.jar
~~~

`jdeps` phân tích những dependency có thể quan sát tĩnh, giúp phát hiện một số phụ thuộc vào JDK internals. Nó có thể không thấy lớp tải bằng reflection, SPI, resource path hoặc plugin-specific loaders.

Do đó cần kết hợp static scanning với **runtime integration** sử dụng artifact thật.

## 23. Compatibility gate cho public API release

Một thư viện public Java API có thể có quy trình:

1. Build artifact v2.
2. So sánh API v1 và v2 bằng tool.
3. Phân loại changes: compatible, binary breaking, source breaking, semantic.
4. Kiểm tra exclusions đã được phê duyệt theo chính sách version.
5. Biên dịch sample source client cũ với v2.
6. Chạy old-client.jar (compile với v1) trên classpath chỉ chứa api-v2.jar.
7. Kiểm tra các hành vi public contracts quan trọng.
8. Chạy smoke trên JDK versions được cam kết.
9. Xuất compatibility report gắn với commit và artifact hash.
10. Chỉ publish release sau khi tất cả breaking changes được xử lý hoặc công bố.

Nếu thư viện cam kết SemVer, có thể dùng breaking change gate cho minor/patch. Tuy nhiên, SemVer chỉ là chính sách version; nó **không tự đảm bảo** một dependency mang version 2.3.4 tương thích với 2.3.3.

## 24. Contract gate cho SPI/plugin host release

Với host được nâng từ H1 lên H2:

1. Ghi danh sách SPI methods và callback semantics.
2. Giữ những plugin JAR đã phát hành (old binaries).
3. Chạy ServiceLoader/module discovery.
4. Khởi tạo plugin bằng lifecycle manager thật.
5. Gọi mọi callbacks mà H2 sử dụng, kể cả capability mới.
6. Test thiếu capability và fallback được định nghĩa.
7. Kiểm tra plugin không mang bản API duplicate được ưu tiên nạp.
8. Test multiple plugins và dependency version conflicts.
9. Test shutdown/reload, concurrent calls và lỗi plugin.
10. Thử rollback H2→H1 khi host/plugin mix có thể xảy ra.

Nếu một plugin không tương thích, quyết định có thể là:

- Giữ adapter compatibility.
- Dùng capability negotiation.
- Yêu cầu plugin owner nâng version theo lộ trình.
- Cô lập plugin trong process riêng.
- Chặn plugin không hỗ trợ ở preflight với thông báo rõ.
- Thay đổi release support policy với kế hoạch truyền thông.

Không để một plugin lỗi chỉ được phát hiện sau khi traffic production gọi một chức năng ít dùng.

## 25. Capability negotiation và versioned SPI

Trong plugin ecosystem, câu hỏi thường không chỉ “plugin version là bao nhiêu?” mà “plugin có hỗ trợ capability X không?”.

Một hợp đồng:

~~~java
public interface ReportPlugin {
    String id();
    byte[] render(ReportRequest request);

    default boolean supports(String format) {
        return "text/plain".equals(format);
    }
}
~~~

Host có thể kiểm tra:

~~~java
if (!plugin.supports("application/pdf")) {
    throw new UnsupportedOperationException(
        "Plugin does not support PDF");
}
~~~

Không nên tự suy ra một plugin hỗ trợ PDF chỉ vì host đã nâng JDK hoặc SPI có default method trả `true`.

### 25.1. Version negotiation khác binary compatibility

Một descriptor khai báo:

~~~properties
plugin.id=thirdparty.report
plugin.version=1.4.0
host.api.range=[2.0,3.0)
capabilities=text/plain
~~~

Đây là **ví dụ định dạng metadata do hệ thống tự định nghĩa**, không phải chuẩn Java chung. Host có thể dùng để reject trước khi nạp. Nhưng metadata không thay thế binary tests: một plugin khai báo version range rộng vẫn có thể bị thiếu method hoặc thư viện ở runtime.

### 25.2. Đừng dựa duy nhất vào class name hoặc version string

Các hệ sinh thái có thể đặt tên artifact và version không nhất quán. Ưu tiên:

- Explicit API/SPI contract version.
- Capability declarations.
- Host compatibility range.
- Artifact checksum và nguồn phát hành.
- Runtime verification test.
- Error messages nêu khả năng/phiên bản không hỗ trợ.

## 26. Phân biệt API compatibility với serialization compatibility

Một plugin có thể giao tiếp với host qua Java objects hoặc persist state. Thay public class từ POJO sang record hoặc đổi package tên class có thể làm hỏng binary code và dữ liệu serialized cũ.

Cần test:

- Java native serialization `serialVersionUID`, class names và field evolution.
- JSON/Avro/Protobuf schemas.
- DTO constructors/getters/record accessors.
- Cache entries và sessions được tạo trước deploy.
- Messages trong broker, retries và DLQ.
- Plugin state files hoặc database tables.
- Data do host/plugin version mới ghi có đọc ngược được không.

Ví dụ client cũ gọi:

~~~java
String id = customerDto.getId();
~~~

Nếu v2 thay bằng:

~~~java
public record CustomerDto(String id) {}
~~~

record tự có accessor `id()`, không tự tạo `getId()`. Binary consumer cũ có thể lỗi `NoSuchMethodError` nếu `getId()` đã bị xóa. Đây là breaking API change dù JSON serializer có thể vẫn tạo field `id` giống trước.

Không gộp source modernization vào compatibility release khi data/API consumer chưa được kiểm tra.

## 27. Lỗi runtime: đọc đúng loại và thời điểm

Một bảng chẩn đoán thực tế:

| Lỗi | Nguyên nhân cần xem | Khi nào thường lộ |
|---|---|---|
| `NoSuchMethodError` | Binary method descriptor không còn | Khi gọi method liên quan |
| `NoSuchFieldError` | Field binary reference bị xóa/đổi | Khi bytecode truy cập field |
| `AbstractMethodError` | Implementation cũ thiếu concrete method được gọi | Khi host gọi method SPI mới |
| `IncompatibleClassChangeError` | Thay class/interface/static dispatch/default conflict | Linkage/dispatch |
| `IllegalAccessError` | Access/binary visibility không phù hợp | Resolution/linkage khi truy cập |
| `ClassNotFoundException` | Loader tìm class theo tên không thấy | Dynamic load, reflection |
| `NoClassDefFoundError` | Class cần ở runtime không thể định nghĩa/khởi tạo phù hợp | Load/resolve/initialize |
| `ClassCastException` | Sai runtime type/class loader identity | Khi cast/check kiểu |
| `ServiceConfigurationError` | SPI provider descriptor/constructor/type fail | Khi ServiceLoader iterate/instantiate |
| `ExceptionInInitializerError` | Static initialization thất bại | Lần khởi tạo class |
| `LayerInstantiationException` hoặc resolution error | Module graph/layer không hợp lệ | JPMS resolution/layer creation |
| `InaccessibleObjectException` | Reflection deep access bị chặn | Khi sử dụng reflective API |

**Lỗi có thể xuất hiện muộn.** `ClassNotFoundException` trong một plugin chỉ dùng khi export PDF có thể không xuất hiện trong smoke test login. Vì vậy test nên exercise các callback và provider classes thực tế, không chỉ load host startup.

### 27.1. Đừng nuốt LinkageError bừa bãi

Một số hệ thống plugin muốn host tiếp tục chạy khi một plugin hỏng. Có thể cách ly lỗi và disable plugin có kiểm soát. Tuy nhiên không nên catch `Throwable` rồi log một dòng chung chung và tiếp tục coi plugin thành công, vì có thể che cả những lỗi nghiêm trọng khác.

Thiết kế error boundary theo plugin lifecycle và failure policy: xác định plugin thất bại, chuyển sang trạng thái disabled, giải phóng resources, báo metric/alert và không trả kết quả giả.

## 28. Plugin sandbox và bảo mật sau JDK migration

Plugin bên thứ ba thường chạy code có cùng quyền process, trừ khi hệ thống có cơ chế cách ly thực sự. **ClassLoader isolation không phải security sandbox hoàn chỉnh**.

Trong các JDK hiện đại, không nên dựa vào Java Security Manager như một cơ chế sandbox lâu dài cho plugin không tin cậy; vòng đời và khả năng sử dụng Security Manager đã thay đổi mạnh qua các phiên bản Java. Nếu thực sự phải chạy code không tin cậy, cân nhắc process/container isolation, OS permissions, network policies và các biện pháp bảo mật phù hợp.

Kiểm thử còn cần:

- Plugin package có nguồn/chữ ký/checksum hợp lệ.
- Plugin có tải executable code từ nguồn ngoài không.
- Secrets và credentials được cung cấp theo least privilege.
- Plugin có được quyền đọc filesystem/network nào.
- Classpath poisoning hoặc dependency substitution.
- Deserialization of untrusted data.
- Resource exhaustion, infinite loops và unbounded threads.
- Logs không chứa tokens/PII.
- Policy disable/revoke plugin khi có lỗ hổng.

Đừng “sửa” lỗi reflective access bằng cách mở toàn bộ JDK internals hoặc chạy host dưới tài khoản có nhiều quyền hơn nếu nguyên nhân là plugin không còn được hỗ trợ.

## 29. Cơ chế phát hiện plugin không tương thích trước khi khởi động

Một quy trình preflight:

~~~text
Plugin artifact
       |
       v
Xác minh nguồn và checksum
       |
       v
Đọc plugin descriptor / API version / capabilities
       |
       v
Kiểm tra host + JDK version ranges
       |
       v
Resolve plugin dependencies
       |
       v
Classloader/module resolution
       |
       v
Provider discovery và contract smoke
       |
       v
Enable plugin hoặc quarantine có thông báo
~~~

Preflight có thể không chạy được mọi nghiệp vụ, nhưng giúp phát hiện sớm missing class, descriptor sai hoặc API version không hợp lệ. Kết hợp preflight với integration test, load test và rollback simulation.

Nếu plugin không được nạp, host nên báo rõ:

~~~text
Plugin thirdparty.report 1.4.0 disabled:
requires Host SPI [1.0,2.0), found Host SPI 3.0
~~~

Đây là ví dụ thông báo mong muốn, không phải định dạng chuẩn của JDK. Tốt hơn nhiều so với một `NoClassDefFoundError` xuất hiện ngẫu nhiên khi người dùng nhấn Export.

## 30. Thiết kế test fixture cho plugin ecosystem

Một bộ fixtures có thể chứa:

~~~text
compat-fixtures/
  api/
    api-v1.jar
    api-v2.jar
  plugins/
    legacy-plugin-v1.jar
    new-plugin-v2.jar
    missing-dependency-plugin.jar
    invalid-service-descriptor.jar
    duplicate-api-plugin.jar
    failing-init-plugin.jar
  configs/
    legacy-plugin.properties
    current-plugin.properties
  expected/
    outputs-v1.json
    lifecycle-events.json
~~~

Artifacts cần metadata:

- Source commit/version.
- Compiler JDK và `--release`.
- API/SPI artifact version compile against.
- Dependencies và checksums.
- Signature/provenance nếu có.
- Expected supported host/JDK range.
- Dữ liệu fixture đã loại bỏ PII/secrets.

Không giả tạo old-plugin.jar bằng cách compile source cũ với current API; như vậy không còn là old binary fixture.

## 31. Test không tương thích nên fail có kiểm soát

Mục tiêu của regression tests không phải mọi plugin đều pass trong mọi major version. Một số plugin có thể **không còn được hỗ trợ có chủ đích**.

Ví dụ test:

~~~text
Given:
  - Host 3.0
  - Plugin 1.0 declares max Host API 2.x

Expect:
  - Plugin bị reject trước khi nhận traffic.
  - Có thông báo không tương thích.
  - Host còn hoạt động với các plugin khác.
  - Plugin resources không bị giữ lại.
  - Metrics/alerts ghi đúng plugin ID.
  - Không có fallback giả danh plugin thành công.
~~~

Một test cho tình huống không hỗ trợ là một phần của contract testing. Không cần ép một plugin cũ chạy được bằng cách mở module quá rộng hoặc đưa lẫn API JAR cũ lên classpath toàn hệ thống.

## 32. Performance và resource lifecycle là hợp đồng vận hành

Plugin v1 có thể hoạt động trong host v2 nhưng tiêu thụ CPU/memory gấp nhiều lần vì host thay cách gọi hoặc JDK GC behavior.

Test nên có:

- Tốc độ initialize/startup.
- Per-call latency và p95/p99 dưới workloads.
- Throughput và memory allocations.
- Number of active threads.
- Open file descriptors/sockets.
- Classloader retention khi reload/uninstall.
- Shutdown time và resource cleanup.
- Retry/backoff behavior khi plugin lỗi.
- Queue saturation và concurrency limits.

Khi so sánh JDK cũ/mới, giữ cùng plugin artifact, workload và constraints khi có thể. Nếu đồng thời nâng plugin implementation, hiệu năng thay đổi không còn chỉ do JDK.

## 33. Contract tests cho HTTP/event plugin integrations

Một plugin có thể là consumer của Kafka topic hoặc client của payment service. Test Java SPI thành công nhưng event schema ngoài hệ thống thay đổi sẽ khiến plugin hỏng khi production chạy.

Ví dụ event:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 2,
  "eventId": "evt-100",
  "payload": {
    "orderId": "O-100",
    "amount": "125000.00",
    "currency": "VND"
  }
}
~~~

Cần xác minh:

- Consumer v1 xử lý được message v2 không, nếu cùng tồn tại.
- Consumer v2 đọc được backlog/DLQ v1 không.
- Unknown enum/field được xử lý rõ.
- Idempotency keys không mất trong migration.
- Retries và manual replay có giữ schema version không.
- Producer mới chỉ phát schema khi các consumer đã sẵn sàng.

Với REST integration, kiểm tra status code, headers, auth/TLS, response schema và error semantics; với gRPC/Protobuf cần kiểm tra schema evolution của field numbers, enum và generated stubs.

Hợp đồng bên ngoài có thể tồn tại lâu hơn một deploy JDK/framework; không được chỉ test plugin mới với dữ liệu mới.

## 34. CI pipeline cho API/SPI/plugin compatibility

Một pipeline minh họa:

~~~text
Stage 1 — Build library/host trên JDK target
Stage 2 — Static API difference report
Stage 3 — Compile existing source clients
Stage 4 — Run precompiled old-client.jar against new API
Stage 5 — Load old-plugin.jar into new host
Stage 6 — ServiceLoader/JPMS/classloader contract tests
Stage 7 — Provider lifecycle/behavior tests
Stage 8 — DB/HTTP/broker integration tests
Stage 9 — Multi-JDK runtime matrix nếu được cam kết
Stage 10 — Packaging and rollback simulation
~~~

Với Maven/Gradle:

~~~bash
# Maven sử dụng Wrapper của repository
./mvnw -B clean verify

# Gradle sử dụng Wrapper của repository
./gradlew clean test
~~~

Đây là ví dụ lệnh cho người học, không phải bước chạy build trong nhiệm vụ viết Markdown. Một pipeline thực tế phải khai báo cụ thể các tasks/tests tương ứng, dependencies, JDK và JAR fixtures.

### 34.1. Lưu artifacts và báo cáo

Cần xuất:

- Host/API SPI version, git commit và build digest.
- JDK vendor/version, OS/architecture.
- Plugin artifact name, version, checksum.
- Compatibility matrix result.
- API diff report.
- Discovery/class loader logs ở mức cần thiết.
- Test failures với callback/contract rõ.
- Bằng chứng các breaking changes được phê duyệt.

Không công bố “0 breaking changes” chỉ vì CI compile toàn bộ source trong một monorepo: plugin của đối tác có thể không nằm trong monorepo và tồn tại dưới binary artifact cũ.

## 35. Case study: host báo cáo nâng JDK và SPI

Giả sử:

~~~text
Host H1 / JDK 11
  SPI ReportPlugin v1
  Old plugin 1.2 đã được phân phối tới đối tác

Mục tiêu:
Host H2 / JDK 21
  SPI ReportPlugin v2
  Nhiều plugin do đối tác chưa được build lại
~~~

Đội phát triển muốn thêm khả năng hỏi định dạng báo cáo:

~~~java
boolean supports(String format);
~~~

### 35.1. Cách làm gây rủi ro

1. Thêm `supports` thành abstract method trong SPI v2.
2. Recompile host và plugin do nhóm mình quản lý.
3. Chạy unit tests trên các implementation mới.
4. Release H2.
5. Khi gọi plugin của đối tác cũ, runtime gặp `AbstractMethodError`.

Bài test “build xanh” không chứng minh binary provider cũ tương thích, vì implementation cũ chưa được test.

### 35.2. Quy trình có kiểm soát

**Bước 1 — Inventory:** liệt kê các plugin version đang dùng, API/SPI cũ, JDK target và phụ thuộc của plugin.

**Bước 2 — Golden binaries:** lấy JAR plugin thật được compile với SPI v1; lưu checksum và metadata.

**Bước 3 — Thiết kế backward compatibility:** cân nhắc default method có fallback an toàn, interface mới, adapter hoặc capability negotiation.

**Bước 4 — Static diff:** chạy API compatibility checks trên spi-v1.jar và spi-v2.jar.

**Bước 5 — Binary test:** chạy old-plugin-v1.jar trong host H2/JDK 21 mà không rebuild.

**Bước 6 — Discovery test:** xác nhận ServiceLoader/descriptor/class loader vẫn chọn provider cũ.

**Bước 7 — Behavior test:** gọi `id`, `render`, `supports` và lifecycle callbacks, test unsupported formats.

**Bước 8 — Integration test:** chạy plugin với dữ liệu/report thực tế, DB/HTTP/queue theo nhu cầu.

**Bước 9 — Failure isolation:** plugin không tương thích phải được disable có thông báo, không gây mất toàn bộ host.

**Bước 10 — Rollout:** canary với danh mục plugin thực tế và theo dõi callback failures, retries, latency.

**Bước 11 — Rollback:** xác nhận các plugin/descriptor/data state do H2 tạo không làm H1 bị lỗi nếu quay về.

### 35.3. Bằng chứng cần có

| Hợp đồng | Bằng chứng |
|---|---|
| Binary API/SPI | API diff + precompiled plugin fixture |
| Provider discovery | ServiceLoader/modules test |
| Behavioral SPI | Contract test suite, callback semantics |
| Dependencies | Runtime resolved classpath + ClassLoader logging |
| Runtime JDK | Test trên JDK 21 thật |
| Data/external integration | Historical fixtures và staging integrations |
| Failure policy | Incompatible plugin disabled/reporting |
| Rollback | Host H1 với trạng thái sau H2 nếu được yêu cầu |

Chỉ sau các kiểm tra này mới có cơ sở kết luận rằng “host mới vẫn chạy được plugin cũ” trong phạm vi đã test.

## 36. Các câu hỏi cần hỏi nhà cung cấp plugin

Khi bên thứ ba giữ code nguồn, host team thường không thể tự sửa plugin. Nên có checklist giao tiếp:

1. Plugin version nào đã được xác minh với JDK/host target?
2. Plugin được build bằng JDK/`--release` nào?
3. Có phụ thuộc API nội bộ JDK hoặc library bytecode không?
4. Có dùng class loading, reflection hoặc Java agent không?
5. API/SPI version range được hỗ trợ?
6. Các callback mới có implementation/fallback nào?
7. Có plan cho namespace `javax`→`jakarta` khi framework thay không?
8. Có custom JDBC/HTTP clients, TLS/keystore không?
9. Có signed artifacts và checksum để xác minh không?
10. Có test fixture/môi trường staging để host chạy lại không?
11. Có thời hạn cung cấp bản tương thích và support lifecycle không?
12. Khi plugin lỗi, có thể tắt/hạ version an toàn không?

Không giả định “phiên bản plugin mới nhất” đồng nghĩa tương thích với JDK mục tiêu; cần bằng chứng từ release notes/support matrix và kiểm thử thật.

## 37. Các nhận định dễ sai

**“Build xanh thì API tương thích.”** Không. Client/plugin đã compile cũ có thể chưa xuất hiện trong build hiện tại.

**“SPI chỉ là interface nên thêm method an toàn.”** Không. Thêm abstract method có thể chỉ lỗi khi host gọi trên provider cũ.

**“Thêm default method luôn an toàn.”** Không. Default conflict và semantic fallback vẫn có thể phá behavior.

**“ServiceLoader thấy class trong JAR là đủ.”** Không. Descriptor, class loader, provider type identity và constructor/module declarations cũng quan trọng.

**“ClassLoader isolation giúp tránh mọi xung đột.”** Không. Shared SPI type phải có cùng identity; child-first loaders có thể nạp bản sao API gây cast failure.

**“Plugin version trong descriptor tự bảo đảm compatible.”** Không. Metadata chỉ là tín hiệu; cần binary/runtime tests.

**“Chỉ cần kiểm thử plugin viết trong cùng repo.”** Không. Phải dùng binary JAR của đối tác từ bản đã phát hành.

**“Plugin chạy được lúc startup thì mọi tính năng sẽ chạy.”** Không. Lỗi linkage/callback có thể xuất hiện rất muộn.

**“Có thể chuyển classpath sang JPMS mà không cần test discovery.”** Không. Module graph, `uses/provides` và visibility có thể thay.

**“Chỉ cần chạy lại unit tests sau nâng JDK.”** Không. Agents, class loader, SPI registration, TLS, native libraries và integrations cần test riêng.

**“Nếu plugin hỏng thì catch Throwable và tiếp tục.”** Không. Phải có policy isolation/cleanup, không che lỗi nguy hiểm hoặc báo thành công giả.

**“Plugin đã dùng Java 21 nghĩa là chạy được mọi host hỗ trợ Java 21.”** Không. Host SPI/framework/dependencies có contract riêng.

## 38. Checklist trước khi phát hành Java compatibility migration

- [ ] Đã ghi JDK, host, API/SPI, framework và plugin versions chính xác.
- [ ] Đã phân biệt source, binary, behavioral và discovery compatibility.
- [ ] Đã inventory plugins của bên thứ ba đang sử dụng.
- [ ] Đã lưu JAR cũ được biên dịch trước migration, không rebuild đè.
- [ ] Đã chạy static API diff với baseline artifact.
- [ ] Đã kiểm tra removed/changed methods, fields, constructors và visibility.
- [ ] Đã kiểm tra abstract/default methods, inheritance và method dispatch.
- [ ] Đã kiểm tra generics erasure/bridge methods khi SPI phức tạp.
- [ ] Đã test old client với new library và old plugin với new host.
- [ ] Đã có conformance tests cho behavioral SPI contracts.
- [ ] Đã kiểm tra callback order, resource ownership và exception semantics.
- [ ] Đã kiểm tra ServiceLoader descriptors, provider visibility và initialization.
- [ ] Đã kiểm tra JPMS module declarations nếu dùng module path.
- [ ] Đã kiểm tra class loader identity và duplicate API JARs.
- [ ] Đã test thiếu dependency, invalid descriptor, conflict và init failure.
- [ ] Đã test thread-safety, timeout, shutdown/reload và cleanup.
- [ ] Đã test Java agents, annotation processors và build plugins liên quan.
- [ ] Đã test HTTP/event/database contracts mà plugin sử dụng.
- [ ] Đã dùng fixtures chứa dữ liệu được viết bởi phiên bản trước.
- [ ] Đã xác minh plugin artifact checksum/provenance và security permissions.
- [ ] Đã có failure isolation và cảnh báo khi plugin bị disable.
- [ ] Đã chạy tests trên JDK runtime và packaging production-like.
- [ ] Đã có ma trận host/plugin/JDK được hỗ trợ hoặc phương án từ chối an toàn.
- [ ] Đã kiểm tra rollback với các plugin và dữ liệu đã tồn tại sau nâng cấp.
- [ ] Đã ghi rõ các breaking changes được phê duyệt và thời gian deprecation.

## 39. Kết luận

**Kiểm thử hợp đồng API, SPI và plugin của bên thứ ba** là phần quan trọng của kiểm thử hồi quy trong Java Advance Compatibility Migration. API thay đổi ảnh hưởng các client gọi thư viện; SPI thay đổi ảnh hưởng plugin implement; còn hệ thống plugin có thêm ranh giới descriptor, ServiceLoader, JPMS, class loader, lifecycle, dependency isolation và security.

Một chương trình kiểm thử đáng tin cậy phải giữ **binary artifacts cũ**, chạy chúng với host/library/JDK mới, và kiểm tra không chỉ khả năng load mà cả method dispatch, hành vi, callback order, thread safety, dữ liệu và các integrations bên ngoài. Static API diff giúp phát hiện nhiều thay đổi về signature nhưng không thay thế behavioral/runtime contract tests.

Khi không thể giữ mọi plugin tương thích, cần **capability negotiation, adapter hoặc chính sách từ chối/disable an toàn**, cùng với version range, thông báo rõ ràng và lộ trình nâng plugin từ nhà cung cấp. Chỉ gọi một migration là thành công khi những plugin thực tế được cam kết hỗ trợ **vẫn được nạp, gọi, vận hành và dừng đúng trên môi trường mới**, không phải chỉ khi host build xanh.
