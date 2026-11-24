# Đăng ký có điều kiện theo classpath và giữ phạm vi metadata cần thiết

## 1. Bài toán: dependency tùy chọn không phải lúc nào cũng có

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT chuẩn bị mã và metadata ở build time để GraalVM Native Image có thể phân tích và tạo executable. Một ứng dụng Spring Boot thường tích hợp nhiều thư viện tùy chọn: SDK lưu trữ, thư viện tạo PDF, driver, module quan sát hoặc adapter cho một dịch vụ bên ngoài. Có môi trường sử dụng dependency đó, có môi trường không.

Nếu đăng ký runtime hints cho mọi thư viện bất kể classpath, ứng dụng có thể:

- tham chiếu tới class không tồn tại và thất bại ngay khi xử lý AOT;
- đóng gói reflection metadata, proxy hoặc resource không cần thiết;
- làm native image lớn hơn và tăng thời gian phân tích;
- che giấu dependency thực sự của một tính năng, khiến cấu hình khó bảo trì.

Ngược lại, nếu dependency có mặt nhưng metadata cần cho reflection/resource không được đăng ký, ứng dụng JVM có thể chạy bình thường trong khi native executable lỗi ở nhánh nghiệp vụ ít được gọi.

Mục tiêu là **chỉ bật tích hợp khi dependency thực sự có mặt, chỉ đăng ký metadata cho những thao tác tích hợp đó thực sự sử dụng, và kiểm thử cả hai trạng thái classpath**.

## 2. Phân biệt ba khái niệm

Ba câu hỏi dưới đây liên quan nhưng không thay thế nhau:

| Khái niệm | Câu hỏi được trả lời | Cơ chế thường dùng |
| --- | --- | --- |
| Classpath condition | Thư viện tùy chọn có hiện diện trong ứng dụng build không? | `@ConditionalOnClass`, `ClassUtils.isPresent` |
| Runtime hints / reachability metadata | Native Image cần giữ khả năng truy cập động nào? | `RuntimeHintsRegistrar`, `RuntimeHints`, metadata của GraalVM |
| Runtime feature condition | Tính năng có được bật cho lần chạy này không? | Property, profile, điều kiện nghiệp vụ và cấu hình runtime |

Ví dụ: SDK PDF có thể nằm trên classpath nhưng tính năng xuất PDF bị tắt bằng property. Khi đó:

- classpath condition quyết định cấu hình tích hợp PDF có thể được nạp hay không;
- runtime hints mô tả constructor/resource/proxy mà native image cần giữ cho tích hợp đó;
- property runtime quyết định endpoint hoặc nghiệp vụ PDF có được bật trong môi trường hiện tại hay không, nếu cấu trúc bean đã được chuẩn bị tương ứng.

**Classpath condition không phải feature flag runtime.** Với native image, bean graph và điều kiện classpath được xử lý trong quá trình AOT; thêm một JAR mới sau khi executable đã được biên dịch không làm binary tự nạp thêm class đó.

## 3. Vì sao phải kiểm tra classpath trước khi đăng ký hints?

GraalVM Native Image sử dụng mô hình closed world. Công cụ phân tích những kiểu và đường gọi có thể được nhìn thấy ở thời điểm build. Một đoạn code tham chiếu trực tiếp tới class của thư viện tùy chọn có thể gây lỗi liên kết hoặc nạp class ngay cả khi tính năng đó không được dùng.

Ví dụ không an toàn trong một module có dependency tùy chọn:

~~~java
import com.vendor.pdf.PdfEngine;

class PdfHints {
    void register(RuntimeHints hints) {
        hints.reflection().registerType(
            PdfEngine.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
    }
}
~~~

Nếu `com.vendor.pdf.PdfEngine` không có trên classpath, class chứa tham chiếu đó có thể không tải được. Chỉ bọc lời gọi bằng một điều kiện Java ở bên trong method không luôn đủ: JVM có thể phải resolve kiểu khi nạp hoặc xác minh class.

Giải pháp là đặt phần tích hợp trong một cấu hình được bảo vệ bởi classpath condition, đồng thời tránh tham chiếu trực tiếp tới kiểu tùy chọn trong các class luôn được nạp.

## 4. Dùng @ConditionalOnClass để bật cấu hình tích hợp

Spring Boot cung cấp `@ConditionalOnClass` để chỉ áp dụng cấu hình khi class chỉ định có thể tìm thấy trên classpath.

Ví dụ một auto-configuration cho SDK PDF:

~~~java
package com.example.pdf;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
@ImportRuntimeHints(PdfRuntimeHints.class)
public class PdfAutoConfiguration {
    // Khai báo các bean tích hợp PDF ở đây.
}
~~~

Dùng thuộc tính `name` để kiểm tra tên class dưới dạng chuỗi khi dependency là tùy chọn. Nhờ đó class cấu hình không cần import SDK chỉ để biểu diễn điều kiện.

Nếu cấu hình này được công bố như một auto-configuration của thư viện, cần đăng ký tên class trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file là tên đầy đủ của lớp auto-configuration, mỗi dòng một lớp:

~~~text
com.example.pdf.PdfAutoConfiguration
~~~

Spring Boot sẽ đánh giá condition trước khi áp dụng cấu hình tương ứng. Nếu SDK không có, cấu hình PDF bị loại; các bean và hints được import từ cấu hình đó không nên được áp dụng.

### 4.1. Khi nào dùng class literal thay vì name?

Nếu dependency là bắt buộc và class luôn có trong compile classpath, có thể dùng:

~~~java
@ConditionalOnClass(PdfEngine.class)
~~~

Nhưng với thư viện tùy chọn, `name = "..."` giúp lớp cấu hình không phải liên kết trực tiếp tới class bên ngoài. Đặc biệt, không đặt method signature, field hoặc superclass trong cấu hình luôn được nạp mà tham chiếu tới kiểu tùy chọn. Nếu cần một bean dùng kiểu SDK, hãy giữ bean đó trong cấu hình có điều kiện hoặc dùng adapter tách biệt.

### 4.2. Đặt điều kiện trên class cấu hình riêng

Một cấu hình có điều kiện riêng dễ kiểm soát hơn khi classpath dependency vắng mặt:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
class PdfIntegrationConfiguration {

    @Bean
    PdfRenderer pdfRenderer() {
        return new VendorPdfRenderer();
    }
}
~~~

Không nên đặt method trả về trực tiếp kiểu SDK tùy chọn trong một cấu hình không có condition, vì Spring hoặc JVM có thể phải phân tích kiểu đó ngay cả khi bean không được tạo.

## 5. Đăng ký RuntimeHints có điều kiện

`@ImportRuntimeHints` cho phép một cấu hình Spring import một `RuntimeHintsRegistrar`. Khi cấu hình tích hợp đã qua classpath condition, registrar đóng góp metadata cho những thao tác mà SDK cần.

Ví dụ:

~~~java
package com.example.pdf;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ClassUtils;

final class PdfRuntimeHints implements RuntimeHintsRegistrar {

    private static final String OPTIONS_TYPE =
        "com.vendor.pdf.PdfOptions";

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        if (!ClassUtils.isPresent(OPTIONS_TYPE, classLoader)) {
            return;
        }

        Class<?> optionsType =
            ClassUtils.resolveClassName(OPTIONS_TYPE, classLoader);

        try {
            hints.reflection().registerConstructor(
                optionsType.getConstructor(),
                ExecutableMode.INVOKE
            );
        }
        catch (NoSuchMethodException ex) {
            throw new IllegalStateException(
                "The PDF SDK no longer exposes the expected public constructor",
                ex
            );
        }

        hints.resources().registerPattern("vendor/pdf/default-profile.json");
    }
}
~~~

Trong ví dụ:

- Tên kiểu được giữ dưới dạng chuỗi, nên registrar không có import tĩnh tới SDK tùy chọn.
- `ClassUtils.isPresent` kiểm tra class bằng classloader mà AOT cung cấp.
- Chỉ khi class tồn tại, registrar mới resolve kiểu và đăng ký reflection hints.
- Chỉ constructor public không tham số được đăng ký vì ví dụ giả định SDK tạo `PdfOptions` bằng constructor đó.
- Chỉ một resource cụ thể được đăng ký vì ví dụ giả định SDK đọc đúng file profile đó.

Trong cấu hình thực tế, condition ở auto-configuration đã ngăn registrar được import khi SDK vắng mặt. Kiểm tra `ClassUtils.isPresent` bên trong registrar là lớp bảo vệ bổ sung, hữu ích khi registrar được tái sử dụng hoặc được gọi trực tiếp trong test.

**Không nên dùng một condition classpath rộng cho cả module nếu từng phần tích hợp có dependency khác nhau.** Hãy tách cấu hình/hints theo capability để mỗi phần chỉ được nạp khi dependency tương ứng có mặt.

## 6. Đăng ký đúng phạm vi reflection metadata

Reflection hints mô tả thành viên nào cần được giữ để truy cập động. Chọn category theo đúng cách code gọi SDK.

| Thao tác thực tế | Metadata nên cân nhắc |
| --- | --- |
| Gọi constructor public qua reflection | `MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS` |
| Gọi constructor khai báo (kể cả non-public) | `MemberCategory.INVOKE_DECLARED_CONSTRUCTORS` |
| Gọi method public qua reflection | `MemberCategory.INVOKE_PUBLIC_METHODS` |
| Gọi method khai báo qua reflection | `MemberCategory.INVOKE_DECLARED_METHODS` |
| Chỉ introspect method, không invoke | `MemberCategory.INTROSPECT_PUBLIC_METHODS` hoặc category declared tương ứng |
| Truy cập field qua reflection | `MemberCategory.PUBLIC_FIELDS` hoặc `MemberCategory.DECLARED_FIELDS` |
| Kiểu được cấp phát qua cơ chế đặc biệt | `MemberCategory.UNSAFE_ALLOCATED` khi thực sự cần |

Nếu SDK chỉ tạo đối tượng bằng một constructor public không tham số, có thể đăng ký riêng constructor đó:

~~~java
void registerOptions(RuntimeHints hints, Class<?> optionsType)
        throws NoSuchMethodException {
    hints.reflection().registerConstructor(
        optionsType.getConstructor(),
        ExecutableMode.INVOKE
    );
}
~~~

Nếu cần gọi một method cụ thể qua reflection, có thể đăng ký riêng method đó bằng `registerMethod(...)` cùng `ExecutableMode.INVOKE`; nếu chỉ cần introspection, dùng chế độ `INTROSPECT`. Cách đăng ký từng constructor/method cụ thể có phạm vi hẹp hơn việc bật một `MemberCategory` cho toàn bộ thành viên cùng loại. Không cần đăng ký toàn bộ declared methods, fields và constructors nếu ứng dụng không sử dụng.

Nếu ứng dụng chỉ introspect annotation hoặc method signature, không đăng ký quyền invoke khi không cần. Nếu framework cần gọi method private, hãy ghi nhận chính xác yêu cầu đó và kiểm tra khả năng tương thích với native image.

### 6.1. Không đăng ký type chỉ vì nó nằm trên classpath

Một dependency có hàng trăm class nhưng ứng dụng chỉ gọi một API nhỏ. Không có lý do giữ toàn bộ package qua reflection chỉ vì dependency hiện diện. Hãy lần theo call path:

1. Class nào thực sự được tạo qua reflection?
2. Constructor nào được gọi?
3. Method nào được gọi động?
4. Field nào được truy cập?
5. Có kiểu nào chỉ cần introspection mà không cần invocation?

Đăng ký từng type/thành viên cần thiết. Nếu một thư viện đã cung cấp reachability metadata tương thích, ưu tiên metadata của thư viện thay vì tạo một bộ hints trùng lặp trong ứng dụng.

## 7. Resource hints cũng cần có điều kiện và phạm vi hẹp

SDK có thể đọc schema, template hoặc profile từ classpath. Native Image không nhất thiết đóng gói mọi resource chỉ vì chúng có trong JAR. Hãy đăng ký resource thực sự được đọc.

Đăng ký một file:

~~~java
hints.resources().registerPattern("vendor/pdf/default-profile.json");
~~~

Đăng ký một nhóm file có quy ước rõ:

~~~java
hints.resources().registerPattern("vendor/pdf/templates/*.json");
~~~

Chỉ nên dùng pattern rộng khi ứng dụng thực sự cần toàn bộ tập file. Tránh những pattern như `**/*` hoặc đăng ký toàn bộ resource của dependency nếu chỉ cần một schema cụ thể.

Nếu resource chỉ cần khi SDK tùy chọn hiện diện, đăng ký nó bên trong registrar được import bởi auto-configuration có `@ConditionalOnClass`. Nếu resource được ứng dụng sử dụng độc lập với SDK, hãy đăng ký ở cấu hình riêng phù hợp với tính năng đó.

Một hint resource không tạo ra file còn thiếu. File phải tồn tại trong input classpath trước khi Native Image đóng gói. Vì vậy cần kiểm tra cả:

- file có trong dependency/application JAR hay không;
- resource path có khớp với đường dẫn classpath không;
- hint có được AOT/native build nhìn thấy không;
- native executable có đọc được file khi chạy không.

## 8. Proxy và serialization: chỉ khai báo khi đường chạy cần

Reflection không phải loại metadata duy nhất. Runtime hints còn có thể mô tả JDK dynamic proxy và serialization.

### 8.1. JDK dynamic proxy

Nếu SDK tạo proxy cho một tập interface cụ thể, đăng ký đúng interface:

~~~java
hints.proxies().registerJdkProxy(
    PdfCallback.class,
    ProgressListener.class
);
~~~

Ví dụ này giả định hai interface là kiểu có mặt trong ứng dụng hoặc dependency bắt buộc. Nếu một interface thuộc thư viện tùy chọn, không tham chiếu trực tiếp nó từ class luôn được nạp; đặt đăng ký trong cấu hình có điều kiện hoặc resolve theo classloader như phần reflection.

Danh sách interface và thứ tự của chúng là một phần định nghĩa proxy. Không đăng ký proxy cho mọi interface trong package nếu chỉ có một tổ hợp được dùng.

### 8.2. Serialization

Nếu một kiểu được serialize/deserialze bằng cơ chế cần metadata native, đăng ký đúng kiểu:

~~~java
hints.serialization().registerType(PdfJobState.class);
~~~

Không mặc định rằng mọi thư viện JSON đều cần serialization hints giống nhau. Jackson binding, Java serialization và các serializer riêng có cơ chế khác nhau. Dùng lỗi thực tế, hướng dẫn của thư viện và test native để quyết định metadata cần thiết.

## 9. Điều kiện theo classpath trong Spring AOT diễn ra khi nào?

Spring AOT xử lý ApplicationContext ở build time. Vì thế, `@ConditionalOnClass` được đánh giá trên classpath của **quá trình build/AOT**. Nếu SDK có trong build dependency, cấu hình tích hợp có thể được xử lý và đóng góp hints. Nếu SDK vắng mặt, cấu hình bị loại.

Điều này dẫn đến các quy tắc:

- Dependency tùy chọn phải có trong build classpath khi muốn đưa tích hợp vào native executable.
- Không thể thêm dependency mới sau khi executable đã được tạo và kỳ vọng binary tự nạp class.
- Cấu hình runtime có thể bật/tắt một bean hoặc một tính năng nếu bean graph và logic cần thiết đã được chuẩn bị.
- Nếu build AOT với dependency không có, không thể chỉ bật một property lúc runtime để tạo lại mã/hints của tích hợp đó.

Sơ đồ:

~~~mermaid
flowchart TB
    A["Classpath khi chạy Spring AOT"] --> C{"Có optional SDK?"}
    C -->|Không| X["Bỏ qua auto-configuration và hints của SDK"]
    C -->|Có| R["Nạp auto-configuration có điều kiện"]
    R --> H["Registrar thêm metadata tối thiểu"]
    H --> N["Native Image phân tích classpath + hints"]
    N --> E["Executable có tích hợp SDK"]
    X --> E2["Executable không có tích hợp SDK"]
    E --> T["Runtime: property quyết định cách dùng tính năng"]
~~~

Hai executable có thể có cấu trúc bean graph khác nhau nếu được build từ classpath khác nhau. Đây là đặc tính của closed-world native compilation, không phải lỗi của Binder hay runtime property.

## 10. Khi nào dùng RuntimeHintsRegistrar, khi nào dùng metadata JSON?

Spring cung cấp API Java `RuntimeHintsRegistrar` để đăng ký metadata trong quá trình AOT. Đây là lựa chọn tự nhiên khi hints gắn với một cấu hình Spring hoặc một tích hợp cụ thể.

Reachability metadata dạng JSON phù hợp khi:

- thư viện muốn phân phối metadata độc lập với một ứng dụng Spring cụ thể;
- metadata đã được cung cấp bởi thư viện hoặc repository chính thức;
- cần khai báo metadata theo schema của GraalVM mà không viết registrar Java.

Với metadata JSON có hỗ trợ condition, có thể giới hạn áp dụng theo khả năng reachability của một kiểu thay vì áp dụng vô điều kiện. Cần tuân thủ đúng schema và phiên bản GraalVM/Native Build Tools đang dùng; không sao chép metadata từ một version khác mà không kiểm tra.

Hai cách không nên đăng ký trùng lặp một tập thành viên nếu không có lý do. Trùng lặp thường không làm ứng dụng đúng hơn; nó làm việc kiểm toán phạm vi metadata khó hơn.

## 11. Kiểm thử cả khi dependency có và không có

Một tích hợp tùy chọn phải có test cho **hai trạng thái classpath**.

### 11.1. Kiểm thử cấu hình khi SDK hiện diện

Nếu SDK được thêm vào test classpath, có thể kiểm tra auto-configuration tạo bean mong đợi:

~~~java
class PdfAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(PdfAutoConfiguration.class)
            );

    @Test
    void createsPdfIntegrationWhenSdkIsPresent() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(PdfRenderer.class);
        });
    }
}
~~~

Test này giả định test runtime có SDK và bean implementation cần thiết. Điều chỉnh runner theo dependency thực tế.

### 11.2. Kiểm thử khi SDK vắng mặt

Spring Boot test cung cấp `FilteredClassLoader` để mô phỏng dependency không có:

~~~java
@Test
void skipsPdfIntegrationWhenSdkIsAbsent() {
    contextRunner
        .withClassLoader(new FilteredClassLoader("com.vendor.pdf"))
        .run(context -> {
            assertThat(context).doesNotHaveBean(PdfRenderer.class);
        });
}
~~~

Ngoài việc không tạo bean, test phải bảo đảm ApplicationContext vẫn khởi động mà không có `NoClassDefFoundError` hoặc `ClassNotFoundException`. Nếu một class luôn được nạp vẫn tham chiếu tới SDK tùy chọn, test này sẽ giúp phát hiện sớm.

### 11.3. Kiểm thử nội dung RuntimeHints

Có thể kiểm tra registrar trực tiếp bằng `RuntimeHintsPredicates`:

~~~java
RuntimeHints hints = new RuntimeHints();
new PdfRuntimeHints().registerHints(hints, getClass().getClassLoader());

assertThat(
    RuntimeHintsPredicates.reflection()
        .onType(PdfOptions.class)
        .withMemberCategory(MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS)
        .test(hints)
).isTrue();
~~~

Đoạn kiểm thử này cần SDK có trên test classpath. Có thể thêm test với classloader lọc dependency để xác nhận registrar không resolve type khi class không có, nếu registrar được thiết kế để hỗ trợ trường hợp đó.

### 11.4. Native integration test

Cuối cùng, build và chạy native executable cho biến thể có SDK. Kiểm tra đúng luồng dùng reflection/resource/proxy/serialization, vì test ApplicationContext trên JVM không thể chứng minh Native Image đã giữ đủ metadata.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Import optional class trong config luôn được nạp | Lỗi khi dependency vắng mặt | Dùng class name trong condition và tách config riêng |
| Registrar luôn đăng ký hints cho mọi SDK | Metadata thừa, hoặc lỗi class không tồn tại | Đặt registrar sau condition và kiểm tra classloader |
| Dùng `allDeclaredMethods`/mọi constructors cho mọi type | Giữ quá nhiều thành viên | Chọn đúng `MemberCategory` theo thao tác |
| Đăng ký toàn bộ resource của dependency | Binary lớn và khó kiểm soát | Đăng ký file hoặc pattern hẹp |
| Nghĩ `@ConditionalOnClass` tự tạo reflection hints | Native có thể thiếu constructor/method được gọi động | Bổ sung hints riêng cho hành vi reflection thực sự |
| Nghĩ RuntimeHints là feature flag | Nhầm metadata build với cấu hình runtime | Tách classpath condition, metadata và feature property |
| Chỉ test khi dependency có mặt | Không phát hiện class loading lỗi khi thiếu SDK | Test cả present và absent |
| Chỉ test JVM | Bỏ sót lỗi reachability native | Chạy native integration test trên luồng có truy cập động |
| Thêm dependency sau khi binary đã build | Binary không có class mới | Build lại native với dependency trên build classpath |

## 13. Quy trình thực hành

Giả sử ứng dụng có tích hợp tùy chọn với SDK PDF. SDK chỉ được dùng trong một số deployment, và chỉ cần constructor public của `PdfOptions` cùng resource `vendor/pdf/default-profile.json`.

**Bước 1 — xác định dependency và điểm tích hợp**

- Xác định artifact Maven/Gradle chứa SDK.
- Xác định class nào chỉ có khi dependency hiện diện.
- Tìm chính xác constructor/method/resource/proxy mà code thực sự dùng.
- Không đăng ký metadata dựa trên toàn bộ API của thư viện.

**Bước 2 — tách auto-configuration**

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.pdf.PdfEngine")
@ImportRuntimeHints(PdfRuntimeHints.class)
class PdfAutoConfiguration {
}
~~~

Đảm bảo lớp được công bố qua auto-configuration imports hoặc được import theo cơ chế Spring Boot phù hợp.

**Bước 3 — đăng ký hints có phạm vi hẹp**

~~~java
final class PdfRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        String typeName = "com.vendor.pdf.PdfOptions";
        if (!ClassUtils.isPresent(typeName, classLoader)) {
            return;
        }
        Class<?> type = ClassUtils.resolveClassName(typeName, classLoader);
        hints.reflection().registerType(
            type,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );
        hints.resources().registerPattern("vendor/pdf/default-profile.json");
    }
}
~~~

Ví dụ giả định SDK chỉ cần public constructor và đúng một resource. Nếu SDK thực tế gọi public method bằng reflection hoặc tạo proxy, bổ sung đúng metadata cho các thao tác đó.

**Bước 4 — kiểm thử hai classpath**

- Test với SDK có mặt: bean tích hợp xuất hiện và hints được đăng ký.
- Test với SDK vắng mặt: ApplicationContext khởi động bình thường, bean và hints của SDK không được áp dụng.

**Bước 5 — build native và chạy nghiệp vụ**

Build bằng Maven hoặc Gradle theo cấu hình module. Chạy native executable có SDK và gọi luồng tạo PDF. Xác minh resource được đọc, constructor reflection hoạt động và các endpoint không liên quan vẫn chạy.

**Bước 6 — đánh giá metadata**

Đọc lại registrar và reachability metadata, loại bỏ thành viên/resource không được dùng. So sánh log build, thời gian native compilation và kích thước executable khi cần đánh giá ảnh hưởng.

## 14. Checklist trước khi hoàn tất tích hợp

- [ ] Dependency tùy chọn được kiểm tra bằng classpath condition.
- [ ] Auto-configuration chứa tham chiếu tới SDK được tách riêng.
- [ ] Registrar không import trực tiếp kiểu tùy chọn ở nơi luôn được nạp.
- [ ] Hints chỉ giữ constructor/method/field/proxy/resource thực sự cần.
- [ ] Resource hint trỏ tới file có trong input classpath.
- [ ] Không trùng metadata đã được thư viện cung cấp.
- [ ] Test khi dependency có mặt và khi dependency vắng mặt.
- [ ] Native test chạy được luồng reflection/resource/proxy quan trọng.
- [ ] Binary được build lại khi classpath dependency hoặc metadata thay đổi.

**Ghi nhớ:** condition trả lời *thư viện có hiện diện để bật tích hợp không*; runtime hints trả lời *Native Image cần giữ những truy cập động nào*; cấu hình runtime trả lời *tính năng được sử dụng ra sao ở môi trường đang chạy*. Đăng ký metadata có điều kiện và tối thiểu giúp native executable tương thích mà vẫn giữ classpath và footprint ở phạm vi cần thiết.
