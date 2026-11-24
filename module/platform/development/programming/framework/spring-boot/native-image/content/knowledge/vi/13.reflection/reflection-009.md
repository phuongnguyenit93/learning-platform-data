# Kiểm chứng đường truy cập thực tế thay vì đăng ký toàn bộ package

## 1. Vì sao phải xác định chính xác đường reflection?

Trên JVM, ứng dụng có thể dùng reflection để tìm class theo tên, tra cứu constructor hoặc method, đọc/ghi field và gọi method khi chương trình đang chạy. JVM thường có thể truy cập class metadata từ classpath, vì vậy một đoạn code reflection có thể hoạt động dù compiler không nhìn thấy một lời gọi trực tiếp tới class hoặc member đó.

Với **GraalVM Native Image**, phân tích reachability diễn ra ở thời điểm build. Những class/member được truy cập động nhưng không thể suy ra từ phân tích tĩnh cần có reachability metadata. Nếu đăng ký thiếu, ứng dụng có thể build thành công nhưng lỗi khi chạy đúng nhánh reflection. Nếu đăng ký quá rộng, native image phải giữ thêm class/member và metadata không cần thiết, làm giảm hiệu quả của phân tích thế giới đóng.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT và API `RuntimeHints` giúp khai báo những truy cập động mà ứng dụng thật sự cần. Bài học này tập trung vào một kỹ năng quan trọng: **lần theo thao tác reflection trong code và kiểm chứng bằng test/runtime evidence, sau đó chỉ đăng ký type/member tương ứng**.

Sau bài học, người học có thể:

- Phân biệt tra cứu class, tra cứu constructor/method, gọi method và truy cập field bằng reflection.
- Lập bảng ánh xạ giữa thao tác runtime và metadata cần thiết.
- Viết registrar chỉ cho phép đúng class, constructor và method được sử dụng.
- Dùng Spring RuntimeHints Agent hoặc GraalVM tracing agent để phát hiện đường truy cập đã được thực thi.
- Kiểm thử các nhánh quan trọng và giải thích giới hạn của dữ liệu tracing.

## 2. Hiểu chính xác code đang làm gì

Không phải mọi API thuộc package `java.lang.reflect` đều có cùng yêu cầu metadata. Hãy đọc chuỗi thao tác thay vì nhìn thấy chữ “reflection” rồi đăng ký toàn bộ package.

Ví dụ, một ứng dụng chọn exporter từ cấu hình:

```java
// Giá trị cấu hình chỉ được phép chọn một implementation đã đóng gói sẵn.
String implementationName = environment.getRequiredProperty("export.plugin.class");

Class<?> pluginType = ClassUtils.forName(implementationName, classLoader);
Constructor<?> constructor = pluginType.getDeclaredConstructor();
Object plugin = constructor.newInstance();

Method exportMethod = pluginType.getMethod("export", ExportRequest.class);
exportMethod.invoke(plugin, request);
```

Đoạn trên là phần thân rút gọn của method trong registry; các import, xử lý exception và validation cấu hình được lược bỏ để làm rõ chuỗi reflection.

Trong ví dụ, property `export.plugin.class` chỉ được cấu hình thành tên của `CsvExportPlugin` hoặc `PdfExportPlugin`; các class này đã có trên classpath khi build. Không cho phép property nhận tên class tùy ý từ request bên ngoài. Nếu tên class chỉ biết tại runtime, Native Image cần metadata cho từng class nằm trong tập được phép.

Đường truy cập thực tế gồm:

1. **Chọn một class name:** property cấu hình quyết định `CsvExportPlugin` hay `PdfExportPlugin`.
2. **Tìm class:** `ClassUtils.forName(...)` tra cứu type từ tên.
3. **Tìm constructor không tham số:** `getDeclaredConstructor()` yêu cầu metadata để introspect constructor.
4. **Tạo object qua reflection:** `newInstance()` yêu cầu khả năng invoke constructor.
5. **Tìm method cụ thể:** `getMethod("export", ExportRequest.class)` tra cứu method public có đúng tên và chữ ký.
6. **Gọi method:** `Method.invoke(...)` thực thi method qua reflection.

Nếu ứng dụng chỉ gọi `Class.forName()` rồi đọc `getName()`, không có lý do để đăng ký mọi constructor và method của class. Nếu ứng dụng gọi constructor và một method duy nhất, metadata cần phản ánh đúng hai thao tác đó.

### Bảng ánh xạ thao tác và metadata

| Thao tác trong code | Điều cần được Native Image hỗ trợ | Phạm vi nên đăng ký |
|---|---|---|
| `Class.forName(name)` hoặc `ClassLoader.loadClass(name)` | Tra cứu type theo tên ở runtime | Đúng class có thể được chọn |
| `getDeclaredConstructor(...)` | Introspect constructor với chữ ký tương ứng | Constructor có đúng danh sách parameter types |
| `Constructor.newInstance(...)` | Invoke constructor | Constructor được gọi |
| `getDeclaredMethod(name, types...)` | Introspect method có tên và chữ ký đó | Method cụ thể |
| `Method.invoke(...)` | Invoke method qua reflection | Method cụ thể và đúng chữ ký |
| `getDeclaredField(name)` | Introspect field | Field cụ thể |
| `Field.get(...)` / `Field.set(...)` | Truy cập giá trị field qua reflection | Field thực sự được đọc/ghi |
| `getDeclaredMethods()` / `getDeclaredFields()` | Liệt kê một tập member | Chỉ dùng metadata cho introspection nếu code thật sự cần danh sách |
| `getAnnotations()` / `getAnnotation(...)` | Đọc annotation metadata | Kiểm tra yêu cầu của thư viện/framework và type/member cụ thể |

Một type được đăng ký để tra cứu không tự động đồng nghĩa mọi member của nó có thể được gọi bằng reflection. Ngược lại, đăng ký một method để invoke không phải lý do để mở toàn bộ field hoặc mọi method còn lại.

### Phân biệt INTROSPECT và INVOKE

Spring mô hình hóa nhu cầu của executable reflection bằng `ExecutableMode`:

- `INTROSPECT`: cần tra cứu/kiểm tra thông tin executable như constructor hoặc method.
- `INVOKE`: cần gọi executable đó qua reflection.

Nếu code chỉ lấy method để đọc tên hoặc kiểm tra chữ ký, hãy đánh giá nhu cầu introspection. Nếu code tiếp tục gọi `Method.invoke()` hoặc `Constructor.newInstance()`, đường đi cần khả năng invoke. Đối với một method được gọi qua reflection, chỉ đăng ký tên method mà bỏ sót parameter types có thể không khớp overload thực tế.

## 3. Bắt đầu từ bằng chứng, không bắt đầu từ package name

Khi gặp lỗi native do reflection, hãy xác định **điểm gọi cụ thể** bằng các nguồn bằng chứng:

1. **Đọc code ứng dụng:** tìm `Class.forName`, `loadClass`, `getDeclaredConstructor`, `getDeclaredMethod`, `Method.invoke`, `Field.get/set`, `MethodHandles.Lookup` và các helper của framework.
2. **Đọc stack trace:** xác định thư viện nào gọi reflection, method nào tạo class/method handle và giá trị tên class lấy từ đâu.
3. **Kiểm tra dependency:** xem thư viện đã cung cấp reachability metadata hoặc Spring RuntimeHintsRegistrar chưa. Không đăng ký lại nếu metadata của thư viện đã đáp ứng use case.
4. **Kiểm tra luồng cấu hình:** xác định tập class có thể được chọn tại runtime có cố định khi build không, hay được nạp từ plugin bên ngoài.
5. **Tái hiện bằng input cụ thể:** chạy đúng format, profile, request hoặc nhánh gây lỗi. Một endpoint chạy được không chứng minh mọi plugin/serializer đã được kiểm thử.
6. **Ghi lại chuỗi truy cập:** class nào được tra cứu, member nào được tìm, member nào được gọi và dữ liệu nào quyết định lựa chọn.

Một bảng điều tra hữu ích:

| Câu hỏi | Ví dụ câu trả lời |
|---|---|
| Class name đến từ đâu? | Property `export.plugin.class` chọn một class trong allow-list |
| Có bao nhiêu implementation hợp lệ? | CSV và PDF, đều có mặt trong classpath khi build |
| Constructor nào được gọi? | Constructor public không tham số |
| Method nào được gọi? | `export(ExportRequest)` |
| Có đọc/ghi field qua reflection không? | Không |
| Có gọi method overload khác không? | Không |
| Framework đã cung cấp hints chưa? | Kiểm tra AOT output/dependency metadata |
| Nhánh nào đã được test? | CSV và PDF; các nhánh lỗi chưa test |

Từ bảng này, có thể xác định một tập metadata nhỏ, có thể kiểm tra được. Không suy luận “package `com.example.plugin` dùng reflection” rồi bật mọi member của mọi class trong package.

## 4. Ví dụ registrar chỉ đăng ký constructor và method cần gọi

Giả sử ứng dụng có hai plugin được đóng gói sẵn: `CsvExportPlugin` và `PdfExportPlugin`. Cả hai đều có constructor không tham số và method `export(ExportRequest)`.

Ví dụ registrar:

```java
package com.example.export;

import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;

public final class ExportPluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        registerExportPlugin(hints, CsvExportPlugin.class);
        registerExportPlugin(hints, PdfExportPlugin.class);
    }

    private void registerExportPlugin(RuntimeHints hints, Class<?> pluginType) {
        hints.reflection().registerType(pluginType, typeHint -> typeHint
            .withConstructor(List.of(), ExecutableMode.INVOKE)
            .withMethod(
                "export",
                List.of(TypeReference.of(ExportRequest.class)),
                ExecutableMode.INVOKE
            )
        );
    }
}
```

Đoạn code thể hiện rõ phạm vi:

- Chỉ hai implementation có thể được chọn mới được đăng ký.
- Chỉ constructor không tham số được invoke.
- Chỉ method `export(ExportRequest)` được invoke.
- Không đăng ký tất cả declared methods, public methods, fields hoặc constructors của package.

`TypeHint.Builder.withConstructor` nhận danh sách parameter types; `withMethod` nhận tên method, danh sách parameter types và mode. Nếu method có overload, từng chữ ký được khai báo riêng. Cách này tránh việc một tên method chung làm metadata rộng hơn use case.

Gắn registrar vào bean sử dụng plugin:

```java
package com.example.export;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

@Component
@ImportRuntimeHints(ExportPluginRuntimeHints.class)
public class ExportPluginRegistry {
    // Chứa method export() với chuỗi truy cập minh họa ở mục 2.
}
```

`@ImportRuntimeHints` khiến Spring AOT phát hiện registrar trong quá trình build. Đặt annotation gần bean dùng reflection giúp metadata đi cùng tính năng; nếu bean không được đóng góp vào BeanFactory trong cấu hình AOT, hints gắn với bean đó cũng không được đóng góp.

## 5. Vì sao đăng ký rộng làm giảm chất lượng metadata?

Một số cách đăng ký tiện lợi nhưng có phạm vi lớn hơn đường gọi thực tế:

```java
// Đăng ký toàn bộ declared methods của một type
hints.reflection().registerType(
    CsvExportPlugin.class,
    MemberCategory.INVOKE_DECLARED_METHODS
);
```

Cách này cho phép invoke nhiều method được khai báo trong `CsvExportPlugin`, trong khi use case ở trên chỉ gọi `export(ExportRequest)`. Nếu tiếp tục áp dụng cho mọi class trong package plugin, metadata sẽ phình to và khó biết method nào thật sự được ứng dụng dùng.

So sánh:

| Cách khai báo | Phạm vi | Khi nào cân nhắc |
|---|---|---|
| `withMethod("export", List.of(TypeReference.of(ExportRequest.class)), INVOKE)` | Một method với chữ ký xác định | Mặc định ưu tiên khi code chỉ gọi method này |
| `withConstructor(List.of(), INVOKE)` | Một constructor không tham số | Khi code tạo instance bằng constructor đó |
| `MemberCategory.INVOKE_DECLARED_METHODS` | Tất cả declared methods của một type | Chỉ khi thư viện thật sự invoke nhiều method không thể liệt kê trước |
| `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` | Tất cả declared constructors của một type | Chỉ khi nhiều constructor thực sự được chọn động |
| `allDeclaredMethods` trong reachability JSON | Tất cả declared methods của type được khai báo | Tránh dùng nếu chỉ có vài method cụ thể |

Đăng ký rộng không nhất thiết làm binary tăng theo một tỷ lệ cố định: compiler còn phân tích reachability và tối ưu hóa. Tuy nhiên, metadata thừa làm giảm tính chính xác, có thể giữ thêm code/member và khiến việc chẩn đoán thiếu hint khó hơn. GraalVM khuyến nghị cung cấp metadata đúng và đủ cho các truy cập động để bảo đảm tính đúng đắn và khả năng tương thích.

### “Đăng ký toàn bộ package” có nghĩa gì?

Native Image metadata mô tả type và member cụ thể; không nên coi tên package là bằng chứng rằng mọi class trong đó đều cần reflection. Một số framework có cơ chế scan package để tìm phần tử đã đánh dấu annotation. Ví dụ `@ReflectiveScan` của Spring quét package trong quá trình AOT để tìm các phần tử mang `@Reflective` (trực tiếp hoặc qua meta-annotation). Cơ chế đó **không đồng nghĩa** với bật reflection cho mọi member của mọi class trong package.

Nếu dự án dùng `@RegisterReflection` hoặc `MemberCategory`, hãy đọc phạm vi của annotation/category ở đúng phiên bản Spring Framework. Một category như `INVOKE_PUBLIC_METHODS` vẫn có nghĩa là cho phép nhiều method của một type, không phải chỉ method mà test vừa gọi.

## 6. Kiểm thử metadata bằng RuntimeHintsPredicates

Với những đường truy cập đã biết, có thể kiểm tra registrar bằng `RuntimeHintsPredicates` mà không cần build native image. Ví dụ xác nhận một type có hint cho category constructor cần thiết:

```java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class ExportPluginRuntimeHintsTests {

    @Test
    void shouldRegisterConstructorAccessForCsvPlugin() {
        RuntimeHints hints = new RuntimeHints();

        new ExportPluginRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
            .onType(CsvExportPlugin.class))
            .accepts(hints);
    }
}
```

Test trên chỉ xác nhận type đã có reflection hint; nó chưa chứng minh constructor hay method cụ thể được đăng ký. Để kiểm tra từng executable, có thể dùng predicate theo member. Với Spring Framework 7, API là `onConstructorInvocation(Constructor)` và `onMethodInvocation(Method)`. Với Spring Framework 6, các API tương ứng là `onConstructor(Constructor)` và `onMethod(Method)`; chúng được đánh dấu deprecated từ Framework 7. Nếu muốn kiểm tra toàn bộ chuỗi lời gọi đã chạy, dùng RuntimeHints Agent ở phần tiếp theo.


Ví dụ predicate kiểm tra constructor và method trên Spring Framework 7:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

Constructor<?> constructor = CsvExportPlugin.class.getDeclaredConstructor();
Method method = CsvExportPlugin.class.getMethod("export", ExportRequest.class);

assertThat(RuntimeHintsPredicates.reflection()
    .onConstructorInvocation(constructor))
    .accepts(hints);

assertThat(RuntimeHintsPredicates.reflection()
    .onMethodInvocation(method))
    .accepts(hints);
```

Hai predicate này kiểm tra đúng executable được yêu cầu. Khi dùng Spring Framework 6, thay bằng `onConstructor(constructor)` và `onMethod(method)` theo API của version đó. Spring Framework 7 thay các predicate cũ bằng tên rõ nghĩa hơn để phân biệt invocation.

## 7. Ghi nhận đường reflection đã chạy bằng Spring RuntimeHints Agent

Unit test kiểm tra một hint đã khai báo là tốt, nhưng đôi khi nhóm không chắc thư viện đang thực hiện những thao tác reflection nào. Spring Framework cung cấp RuntimeHints Agent trong module `org.springframework:spring-core-test`. Agent ghi nhận những lời gọi liên quan đến runtime hints trong đoạn code được chạy, rồi cho phép so sánh các lời gọi đó với `RuntimeHints`.

Đây là cách kiểm tra theo **hành vi thực thi**:

1. Chạy đúng nghiệp vụ trong một lambda được recorder theo dõi.
2. Agent ghi lại các thao tác cần metadata đã diễn ra.
3. Tạo `RuntimeHints` bằng registrar thật của ứng dụng.
4. So sánh tập lời gọi được ghi với tập hints đã đăng ký.
5. Nếu có thao tác chưa được bao phủ, test cung cấp thông tin về invocation cần bổ sung.

Ví dụ:

```java
import org.junit.jupiter.api.Test;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.test.agent.EnabledIfRuntimeHintsAgent;
import org.springframework.aot.test.agent.RuntimeHintsInvocations;
import org.springframework.aot.test.agent.RuntimeHintsRecorder;

import static org.assertj.core.api.Assertions.assertThat;

@EnabledIfRuntimeHintsAgent
class ExportPluginRuntimeHintsAgentTests {

    @Test
    void shouldCoverReflectiveCallsUsedByCsvExport() {
        RuntimeHints hints = new RuntimeHints();
        new ExportPluginRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        RuntimeHintsInvocations invocations = RuntimeHintsRecorder.record(() -> {
            ExportPluginRegistry registry = testExportPluginRegistry();
            registry.export("csv", sampleExportRequest());
        });

        assertThat(invocations).match(hints);
    }
}
```

`testExportPluginRegistry()` và `sampleExportRequest()` là helper của test cần được triển khai trong dự án. Ví dụ minh họa cách tổ chức test; nó không phải một class hoàn chỉnh có thể copy chạy độc lập.

### Thiết lập và giới hạn của agent

- Thêm `org.springframework:spring-core-test` vào test dependencies với version được Spring Boot/Spring Framework dependency management hỗ trợ.
- Cấu hình Java agent cho test task theo hướng dẫn của Spring Framework và build tool đang dùng.
- `@EnabledIfRuntimeHintsAgent` giúp đánh dấu test chỉ chạy khi agent được nạp.
- Theo tài liệu Spring Framework, agent mặc định instrument package `org.springframework`. Để ghi nhận lời gọi reflection trong package ứng dụng như `com.example.export`, cần cấu hình phạm vi instrumentation cho package đó.
- Chạy test với các nhánh cần kiểm tra. Nếu chỉ chạy CSV, test không thể chứng minh đường PDF đã được bao phủ.

**Giới hạn quan trọng:** agent chỉ ghi nhận thao tác **đã thực sự chạy**. Một nhánh chưa được test sẽ không xuất hiện trong bản ghi. Vì vậy, phải kết hợp agent với danh sách tính năng, test cases và kiểm thử các cấu hình/implementation hợp lệ.

## 8. Dùng GraalVM tracing agent khi cần tạo metadata từ ứng dụng JVM

GraalVM Native Image tracing agent có thể chạy cùng ứng dụng JVM hoặc test suite để thu thập các truy cập động, rồi tạo cấu hình JSON metadata. Đây là một nguồn bằng chứng hữu ích khi thư viện bên thứ ba sử dụng reflection mà code ứng dụng không gọi trực tiếp.

Quy trình tổng quát:

1. Khởi chạy ứng dụng/test trên JVM cùng tracing agent theo hướng dẫn của đúng phiên bản GraalVM.
2. Thực thi các request, plugin, serializer, profile và nhánh nghiệp vụ cần hỗ trợ.
3. Thu thập metadata agent tạo ra.
4. Đọc từng entry: type nào được tra cứu, constructor/method/field nào được truy cập, có phải đường gọi còn cần thiết không.
5. Loại bỏ entry không thuộc phạm vi phát hành hoặc đã được Spring/library cung cấp sẵn; giữ lại những truy cập động cần thiết.
6. Build Native Image và test lại các đường truy cập trên binary.

Tracing agent không phải bộ phân tích mọi đường có thể chạy. Nó chỉ quan sát những gì đã được thực thi trong phiên chạy có instrument. Một test suite thiếu nhánh plugin PDF, chẳng hạn, có thể sinh metadata cho CSV nhưng không ghi nhận PDF.

Không nên sao chép toàn bộ file JSON do agent tạo ra vào sản phẩm mà không review. Agent có thể quan sát các thao tác của test framework, thư viện phụ trợ hoặc đường code chỉ dùng trong môi trường test. Metadata đầu ra và cách đặt file thay đổi theo phiên bản GraalVM; hãy dùng định dạng/schema của toolchain dự án. Các phiên bản mới hỗ trợ reachability metadata dạng `reachability-metadata.json` dưới `META-INF/native-image/<groupId>/<artifactId>/`.

## 9. Kiểm tra thiếu metadata trên Native Image

Sau khi unit test registrar và agent test đã pass, vẫn phải build và chạy native executable. Test JVM không thể thay thế bước này vì môi trường native áp dụng quy tắc metadata và reachability khác.

Với phiên bản GraalVM hỗ trợ các tùy chọn tương ứng, có thể bật chế độ kiểm tra reachability metadata chính xác khi build:

```text
--exact-reachability-metadata
```

Khi chạy ứng dụng hoặc test native, tùy phiên bản GraalVM có thể dùng:

```text
-XX:MissingRegistrationReportingMode=Warn
```

Chế độ `Warn` giúp ghi nhận lỗi thiếu đăng ký thay vì chỉ để lỗi bộc lộ khi người dùng gọi nhánh tương ứng. Khi cần kiểm tra nghiêm ngặt trong CI, GraalVM có thể cung cấp chế độ `Exit` để báo lỗi và kết thúc tiến trình ngay khi phát hiện thiếu registration. Hãy xác nhận tùy chọn và hành vi cụ thể với version Native Image đang dùng; không sao chép flags từ một release khác mà chưa kiểm tra.

Quy trình kiểm tra:

1. Build native với cấu hình metadata chính xác theo phiên bản GraalVM.
2. Chạy smoke test và toàn bộ test nghiệp vụ trên native executable.
3. Bật reporting mode phù hợp để phát hiện các truy cập động thiếu registration.
4. Kích hoạt cả CSV, PDF và những trường hợp lỗi/biên.
5. Sửa registrar tại nguồn, build lại và lặp lại test.

Không nên xử lý `MissingReflectionRegistrationError` bằng cách bắt rồi bỏ qua `Error` hoặc thêm `catch (Throwable)` để tiếp tục nghiệp vụ. Lỗi này báo rằng chương trình đang thực hiện một truy cập reflection chưa được khai báo đầy đủ cho native image. Cần sửa metadata hoặc thiết kế lại đường truy cập.

## 10. Khi nào nên bỏ reflection thay vì đăng ký thêm?

Nếu tập implementation đã biết và Spring có thể quản lý chúng như bean, hãy cân nhắc bỏ việc nạp class theo tên. Ví dụ, inject các plugin vào một registry:

```java
@Component
public class ExportPluginRegistry {

    private final Map<String, ExportPlugin> plugins;

    public ExportPluginRegistry(List<ExportPlugin> availablePlugins) {
        this.plugins = availablePlugins.stream()
            .collect(Collectors.toUnmodifiableMap(
                ExportPlugin::format,
                Function.identity()
            ));
    }

    public void export(String format, ExportRequest request) {
        ExportPlugin plugin = this.plugins.get(format);
        if (plugin == null) {
            throw new IllegalArgumentException("Unsupported format: " + format);
        }
        plugin.export(request);
    }
}
```

Trong ví dụ này, Spring tạo bean cho các plugin và registry gọi qua interface bằng Java invocation thông thường. Nếu không còn code nào khác dùng reflection, không cần đăng ký constructor/method của plugin cho use case này. Spring AOT có thể phân tích quan hệ bean và sinh mã khởi tạo tương ứng.

Cách này phù hợp khi:

- Danh sách plugin cố định tại build time.
- Mỗi plugin có thể là Spring bean.
- Việc lựa chọn chỉ cần một key như `csv` hoặc `pdf`.
- Không cần nạp class/JAR mới sau khi native executable đã phát hành.

Nếu sản phẩm thực sự cần tải plugin mới từ file JAR hoặc classpath mở rộng sau khi build, đó là một mô hình khác với closed-world Native Image. Chỉ thêm reflection hints không thể đưa bytecode tùy ý chưa có khi build vào native executable. Cần thiết kế extension boundary phù hợp, ví dụ tiến trình plugin riêng hoặc một cơ chế triển khai khác.

## 11. Những lỗi thường gặp khi xác định phạm vi reflection

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đã đăng ký class nhưng `newInstance()` vẫn lỗi | Thiếu hint cho constructor cụ thể | Kiểm tra parameter types và `ExecutableMode.INVOKE` |
| Đăng ký method nhưng overload vẫn lỗi | Hint không khớp chữ ký tham số thực tế | Đối chiếu tên method và toàn bộ parameter types |
| Một method chạy được nhưng method khác lỗi | Chỉ method đã đăng ký mới có metadata | Bổ sung đúng method được gọi, không bật toàn bộ type |
| Field đọc được trên JVM nhưng lỗi native | Thiếu field reflection hint hoặc framework binding metadata | Xác định code dùng `Field.get/set`, rồi đăng ký field cụ thể |
| Đã thêm hint nhưng native không thay đổi | Registrar không được AOT phát hiện hoặc build đang dùng output cũ | Kiểm tra bean/`@ImportRuntimeHints`, profile AOT và clean build |
| Test agent không ghi nhận code ứng dụng | Agent chỉ instrument package mặc định | Cấu hình package instrumentation cho package ứng dụng |
| Test agent pass nhưng production vẫn lỗi | Test chưa chạy nhánh production hoặc input khác | Bổ sung test theo format/profile/feature thực tế |
| GraalVM tracing agent tạo JSON rất lớn | Agent quan sát cả test framework, thư viện và nhánh không dùng trong production | Review, loại metadata test-only và thu hẹp từng type/member |
| Metadata trùng với dependency | Thư viện đã cung cấp reachability metadata/hints | Kiểm tra dependency metadata trước khi tự đăng ký lại |
| Package scan khiến người học nghĩ mọi class đều được mở reflection | Nhầm `@ReflectiveScan` với đăng ký tất cả member | Hiểu scan chỉ tìm các phần tử được đánh dấu `@Reflective` |
| Native executable vẫn không tải plugin mới | Plugin JAR không có trong classpath lúc build | Giữ tập plugin cố định hoặc thiết kế extension qua tiến trình khác |

## 12. Quy trình thực hành từ lỗi đến metadata tối thiểu

Khi một nhánh reflection thất bại, thực hiện theo thứ tự:

1. **Tái hiện lỗi:** lưu request, property, profile và stack trace cụ thể.
2. **Lần theo caller:** xác định API reflection nào đã được gọi và class/member nào là đích.
3. **Kiểm tra metadata sẵn có:** xem Spring AOT, Spring/third-party hints và metadata trên classpath đã bao phủ chưa.
4. **Ghi bảng truy cập:** class lookup, constructor lookup/invoke, method lookup/invoke, field read/write.
5. **Đăng ký tối thiểu:** thêm đúng class/member với chữ ký và mode cần thiết.
6. **Unit test registrar:** kiểm tra hint bằng `RuntimeHintsPredicates`.
7. **Test theo hành vi:** dùng Spring RuntimeHints Agent để so các invocation thực tế với hints.
8. **Build và chạy native:** kiểm tra chính nhánh đã lỗi, cộng các nhánh còn lại trong danh sách chức năng.
9. **Review kích thước/phạm vi:** bỏ những đăng ký dư thừa khi xác định được chúng không còn cần thiết.

Một thay đổi metadata tốt phải giải thích được: **lỗi phát sinh từ lời gọi nào, member nào thiếu hint, và tại sao entry vừa thêm là phạm vi nhỏ nhất đáp ứng lời gọi đó**.

## 13. Bài tập thực hành

### Bài tập A — Kiểm kê đường gọi của plugin

Cho ứng dụng có hai plugin CSV/PDF. Đọc code registry và liệt kê mọi lời gọi reflection theo thứ tự. Với mỗi lời gọi, ghi class, constructor/method/field, parameter types và mode cần thiết.

**Tiêu chí hoàn thành:** tạo được bảng đường gọi, chỉ ra class nào được chọn và vì sao class đó phải có mặt trên classpath khi build.

### Bài tập B — So sánh hint hẹp và hint rộng

Viết hai registrar: một registrar dùng `withConstructor` và `withMethod` cho chữ ký cụ thể; một registrar dùng `INVOKE_DECLARED_METHODS`. Kiểm tra hai tập hints và giải thích tập nào phản ánh đúng use case hơn, tập nào có thể cho phép nhiều truy cập không cần thiết.

### Bài tập C — Dùng RuntimeHints Agent

Cấu hình `spring-core-test` và RuntimeHints Agent cho package ứng dụng. Chạy test CSV, sau đó bổ sung test PDF. Quan sát khác biệt trong invocation records và kiểm tra cả hai tập đều được hints bao phủ.

**Câu hỏi:** tại sao test chỉ chạy CSV không thể chứng minh PDF đã có đủ reflection metadata?

### Bài tập D — Thử tracing agent và native image

Chạy test suite với GraalVM tracing agent, review metadata JSON và so sánh với registrar đang có. Build native với chế độ exact reachability metadata phù hợp phiên bản, chạy các test quan trọng và ghi lại mọi missing-registration report.

**Tiêu chí hoàn thành:** có log test, danh sách metadata được giữ lại và bằng chứng native executable chạy được cả hai plugin.

## 14. Checklist trước khi bàn giao

- [ ] Đã tìm được các API reflection thực sự được gọi trong code/dependency.
- [ ] Đã xác định class name đến từ đâu và tập class có thể được chọn.
- [ ] Đã liệt kê constructor/method/field cùng chữ ký và thao tác cần thiết.
- [ ] Đã kiểm tra hints có sẵn của Spring và thư viện.
- [ ] Registrar chỉ đăng ký các type/member cần thiết.
- [ ] Không dùng package-wide scan như cách thay thế cho việc xác định access path.
- [ ] Unit test xác nhận registrar tạo hints mong muốn.
- [ ] RuntimeHints Agent hoặc tracing agent đã chạy trên các nhánh cần hỗ trợ.
- [ ] Đã nhớ rằng agent chỉ quan sát code path được thực thi.
- [ ] Native executable đã được build và test trực tiếp với các nhánh reflection.

## Tài liệu tham khảo

- [Spring Framework Reference — Ahead of Time Optimizations, Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): API `RuntimeHints`, `@Reflective`, `@ReflectiveScan`, `@RegisterReflection`, RuntimeHints Agent và kiểm thử invocation.
- [Spring Boot Reference — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): đăng ký custom reflection hints bằng `RuntimeHintsRegistrar`.
- [Spring Framework Javadoc — TypeHint.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/TypeHint.Builder.html): `withConstructor`, `withMethod`, `withField` và `withMembers`.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): metadata cho reflection, các member được truy cập động, tracing agent và exact reachability metadata.

## Kết luận

Để Native Image hỗ trợ reflection ổn định, hãy bắt đầu từ **đường truy cập thật**: class nào được tìm, constructor nào được tạo, method nào được gọi và field nào được đọc/ghi. Spring `RuntimeHints` cho phép khai báo đúng type/member và chữ ký; `RuntimeHintsPredicates`, Spring RuntimeHints Agent và GraalVM tracing agent giúp kiểm chứng metadata dựa trên các thao tác đã chạy. Các công cụ tracing không chứng minh những nhánh chưa được thực thi, vì vậy phải kết hợp chúng với test cases bao phủ nghiệp vụ. Khi tập plugin đã cố định, cân nhắc thay reflection bằng Spring bean registry để Spring AOT có thể xử lý quan hệ trực tiếp và giảm nhu cầu metadata thủ công.


