# Phân biệt điều kiện classpath với khai báo khả năng truy cập trong native image

## Mục tiêu học tập

Khi phát triển auto-configuration cho một thư viện Spring Boot, hai câu hỏi thường bị nhầm lẫn:

1. **Thư viện hoặc class tùy chọn có mặt trên classpath để cấu hình này được kích hoạt không?**
2. **Nếu ứng dụng chạy dưới GraalVM Native Image, những class, method, resource hoặc proxy nào phải được giữ và cho phép truy cập động?**

Câu hỏi thứ nhất thuộc về **điều kiện auto-configuration**, chẳng hạn \`@ConditionalOnClass\`. Câu hỏi thứ hai thuộc về **reachability metadata/runtime hints**, chẳng hạn \`RuntimeHintsRegistrar\`. Hai cơ chế có thể cùng xuất hiện trong một integration, nhưng chúng giải quyết hai giai đoạn và hai vấn đề khác nhau.

Bài học này dùng Spring Boot 3.3, Spring Framework 6.1 và Java 17+ để giải thích:

- Cách \`@ConditionalOnClass\` kiểm tra dependency có trên classpath hay không.
- Vì sao Spring AOT đánh giá condition ở build time và tạo bean graph cố định cho native image.
- Cách GraalVM Native Image phân tích reachability theo closed-world assumption.
- Những trường hợp cần khai báo reflection, resource, serialization, JDK proxy và JNI hints.
- Cách đăng ký hints bằng \`RuntimeHintsRegistrar\`, \`@ImportRuntimeHints\` và metadata JSON.
- Cách kiểm thử condition và runtime hints, rồi xác minh bằng native executable.

## 1. Hai câu hỏi khác nhau trong vòng đời build

Giả sử thư viện Acme có một integration dành cho SDK codec tùy chọn của nhà cung cấp:

- Ứng dụng chỉ thêm Acme core: không có SDK codec.
- Ứng dụng thêm SDK codec: Acme có thể tạo adapter codec.
- Adapter dùng reflection để gọi một method của DTO do SDK tạo.
- Adapter đọc template từ resource có tên được ghép động theo locale.

Có hai quyết định:

**Quyết định A — Có nên đăng ký adapter không?**

Nếu SDK codec không nằm trên classpath, auto-configuration codec không được áp dụng. Đây là công việc của \`@ConditionalOnClass\`.

**Quyết định B — Nếu adapter được đưa vào native image, những truy cập động nào phải còn dùng được?**

Static analysis của Native Image có thể không suy ra được method được gọi qua reflection hoặc resource được tìm bằng tên tạo lúc runtime. Đây là công việc của runtime hints/reachability metadata.

| Tiêu chí | Classpath condition | Native-image reachability declaration |
| --- | --- | --- |
| Câu hỏi | Dependency/class có hiện diện để bật cấu hình không? | Phần tử động nào cần được giữ và truy cập trong executable? |
| Cơ chế Spring thường dùng | \`@ConditionalOnClass\`, \`@ConditionalOnMissingClass\` | \`RuntimeHints\`, \`RuntimeHintsRegistrar\`, \`@ImportRuntimeHints\` |
| Đầu vào | Classpath và metadata của cấu hình | Những thao tác động mà ứng dụng/thư viện thực hiện |
| Thời điểm trong JVM thông thường | Khi Spring xử lý configuration | Khi Spring AOT tạo hints và khi Native Image build |
| Vai trò trong native build | Định hình cấu hình/bean graph ở AOT build time | Hướng dẫn Native Image giữ phần tử cần thiết cho truy cập động |
| Không làm được | Không cấp quyền reflection hoặc đưa method vào metadata | Không thêm JAR/class còn thiếu và không tự bật auto-configuration |

Một class có thể có mặt trong JAR nhưng không cần reflection. Ngược lại, một class được khai báo trong reflection hints vẫn phải có trong dependency graph nếu ứng dụng cần dùng class đó. Vì vậy, hai khái niệm không thể thay thế cho nhau.

## 2. Điều kiện classpath với @ConditionalOnClass

\`@ConditionalOnClass\` là annotation điều kiện của Spring Boot. Nó chỉ khớp khi class được chỉ định tồn tại trên classpath đang được Spring sử dụng.

Ví dụ:

~~~java
package com.acme.codec.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
public class AcmeCodecAutoConfiguration {

    @Bean
    CodecAdapter codecAdapter() {
        return new CodecAdapter();
    }
}
~~~

Trong ví dụ này:

- Nếu JAR chứa \`com.vendor.codec.Codec\` có trên classpath, condition có thể khớp.
- Nếu dependency không có, configuration class không được áp dụng.
- \`@ConditionalOnClass\` không tạo bean codec và không đăng ký reflection metadata.
- Điều kiện chỉ quyết định cấu hình có đủ điều kiện tham gia quá trình đăng ký bean hay không; các condition khác vẫn có thể loại cấu hình.

### 2.1. Dùng class name khi dependency là tùy chọn

Có thể khai báo class bằng tên chuỗi:

~~~java
@ConditionalOnClass(name = "com.vendor.codec.Codec")
~~~

Cách này hữu ích khi module autoconfigure không muốn tham chiếu trực tiếp kiểu của dependency tùy chọn. Nó cũng giúp tránh phải resolve kiểu đó chỉ để đọc annotation.

Spring Boot có thể đọc metadata annotation trên configuration class bằng ASM trước khi class được load. Tuy nhiên, cần cẩn thận với \`@Bean\` method có return type hoặc parameter type đến từ SDK tùy chọn: JVM có thể phải resolve method signature trước khi condition trên method được đánh giá. Nếu cả một nhóm bean cần SDK, đặt \`@ConditionalOnClass\` ở cấp configuration class và cô lập integration vào class riêng.

### 2.2. Classpath condition không kiểm tra reachability

Giả sử class Codec có trong JAR, condition khớp và Spring đăng ký CodecAdapter. Điều đó vẫn chưa chứng minh mọi method mà adapter gọi qua reflection sẽ có mặt trong native executable.

Classpath condition không hỏi:

- Method có được gọi trực tiếp từ entry point không?
- GraalVM có nhìn thấy đường gọi đến method không?
- Resource có được tìm bằng một chuỗi hằng hay tên được ghép lúc runtime?
- JDK proxy có được tạo bằng danh sách interface động không?

Đó là các câu hỏi của Native Image static analysis và reachability metadata.

## 3. Spring AOT đánh giá condition ở build time

Ứng dụng Spring Boot trên JVM thường tạo bean graph khi khởi động. Spring Boot có thể phản ứng với classpath, profile, property và bean definitions tại thời điểm đó.

Khi bật Spring AOT cho native image, Spring phải tạo trước các asset cần thiết để GraalVM phân tích. Quá trình AOT khởi tạo ApplicationContext đến giai đoạn bean definitions đã sẵn sàng, đánh giá các condition và sinh mã/metadata tương ứng.

**Các condition được đánh giá dựa trên Environment ở build time.** Classpath của native executable cũng được cố định khi build. Vì vậy:

- Dependency có mặt trong classpath lúc AOT: nhánh \`@ConditionalOnClass\` có thể được đưa vào bean graph.
- Dependency không có lúc AOT: nhánh đó không được đưa vào bean graph được tạo.
- \`@ConditionalOnProperty\` và profile ảnh hưởng việc tạo bean cũng được đánh giá trong môi trường build.
- Thay đổi property/profile lúc chạy native executable không thể bật một bean đã bị loại khỏi AOT bean graph hoặc tắt một bean đã được tạo sẵn trong graph.

Điều này **không có nghĩa mọi property đều bị đóng băng**. Property được đọc bởi logic nghiệp vụ sau khi bean đã được tạo vẫn có thể ảnh hưởng hành vi runtime. Giới hạn nằm ở property/condition quyết định bean nào được đăng ký trong ApplicationContext.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.codec",
        name = "enabled",
        havingValue = "true")
class AcmeCodecAutoConfiguration {
    // Các bean của codec integration.
}
~~~

Nếu \`acme.codec.enabled=true\` trong môi trường chạy AOT, nhánh cấu hình được xử lý ở build time. Nếu property chỉ được đặt thành true sau khi native executable đã được tạo, ứng dụng không thể dựa vào property đó để tạo nhánh bean mới.

### 3.1. Vì sao AOT phải cố định bean graph?

Native Image dùng closed-world assumption: nó phân tích chương trình từ entry point và chỉ đưa phần tử mà static analysis xác định cần thiết vào executable, cùng với phần tử được mô tả bằng metadata.

Nếu cho phép Spring tùy ý tạo bean graph mới theo property hoặc classpath lúc runtime, GraalVM không thể biết đầy đủ những class/method nào cần được giữ. AOT chuyển phần lớn quyết định cấu hình sang build time để tạo một graph có thể phân tích.

### 3.2. Lựa chọn thiết kế khi cần thay đổi ở runtime

Nếu ứng dụng cần lựa chọn một strategy theo property runtime, hãy cân nhắc đăng ký trước các strategy cần thiết trong bean graph rồi để một service chọn implementation theo cấu hình runtime.

Ví dụ, cả hai strategy đều được đóng gói và có hints cần thiết:

~~~java
@Service
class CodecSelector {

    private final Map<String, CodecAdapter> adapters;

    CodecSelector(Map<String, CodecAdapter> adapters) {
        this.adapters = adapters;
    }

    CodecAdapter select(String mode) {
        CodecAdapter adapter = adapters.get(mode);
        if (adapter == null) {
            throw new IllegalArgumentException("Unsupported codec mode: " + mode);
        }
        return adapter;
    }
}
~~~

Đây là lựa chọn giữa các bean đã có. Nó không yêu cầu Spring tạo thêm bean sau AOT. Nếu một strategy phụ thuộc SDK không được đóng gói trong native executable, selector không thể làm dependency đó xuất hiện.

## 4. Native Image reachability và closed-world assumption

GraalVM Native Image thực hiện static analysis từ entry point của ứng dụng. Các lời gọi trực tiếp thường tạo thành đường reachability mà compiler có thể theo dõi.

Ví dụ:

~~~java
public class Application {

    public static void main(String[] args) {
        new Greeter().sayHello();
    }
}

class Greeter {

    void sayHello() {
        System.out.println("Hello native image");
    }
}
~~~

Đường gọi từ \`main\` tới \`Greeter.sayHello()\` có thể được phân tích tĩnh. Nếu không có đường nào cần một class/method, Native Image có thể loại nó khỏi executable.

Khó khăn xuất hiện với hành vi chỉ được xác định khi chạy:

~~~java
String className = configuration.getImplementationClass();
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Tên class đến từ configuration. Static analysis không thể luôn suy ra class và constructor nào sẽ được dùng. Nếu ứng dụng cần kiểu truy cập này, phải cung cấp metadata thích hợp hoặc thay đổi thiết kế để compiler nhìn thấy đường gọi tĩnh.

### 4.1. Các loại truy cập động thường cần khai báo

| Loại | Ví dụ | Hints tương ứng |
| --- | --- | --- |
| Reflection | \`Class.forName\`, \`Method.invoke\`, gọi constructor bằng reflection | Reflection hints |
| Resource động | \`ClassLoader.getResource(name)\` với tên ghép từ property | Resource hints |
| Serialization | Đọc/ghi object bằng Java serialization | Serialization hints |
| JDK dynamic proxy | \`Proxy.newProxyInstance\` với interface list | Proxy hints |
| JNI | Native code tra cứu class, field hoặc method Java | JNI hints |

Không phải mọi reflection/resource access đều cần khai báo thủ công. Native Image có thể nhận ra một số thao tác có tham số hằng; Spring AOT cũng suy luận hints cho nhiều contract quen thuộc. Chỉ bổ sung metadata cho những truy cập mà toolchain không thể suy ra.

### 4.2. Có class trên classpath không đồng nghĩa class sẽ tự được giữ

Một thư viện có thể nằm trên classpath nhưng phần lớn code của nó không được tham chiếu từ entry point. Static analysis có thể loại phần không reachable. Nếu code cần dùng class đó chỉ qua reflection, phải khai báo phần tử cần thiết.

Ngược lại, một hint không thay thế dependency. Nếu JAR không được đóng gói, khai báo reflection cho class đó không tự tải JAR hoặc thêm class vào ứng dụng.

## 5. Spring RuntimeHints: API khai báo khả năng truy cập

Spring Framework cung cấp API \`RuntimeHints\` để mô tả các truy cập động cần có trong native image. API này gom các nhóm:

- \`hints.reflection()\`: class, constructor, method và field cần reflection.
- \`hints.resources()\`: resource pattern và resource bundle.
- \`hints.serialization()\`: kiểu cần Java serialization.
- \`hints.proxies()\`: JDK dynamic proxy.
- \`hints.jni()\`: truy cập Java từ native code qua JNI.

Spring AOT chuyển các hints này thành metadata mà GraalVM có thể sử dụng.

Ví dụ đăng ký resource:

~~~java
hints.resources().registerPattern("acme/templates/*.txt");
~~~

Ví dụ đăng ký method reflection:

~~~java
Method method = ReflectionUtils.findMethod(
        AcmePayload.class, "encode", String.class);

hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
~~~

Chỉ đăng ký đúng quyền cần thiết. Nếu code chỉ cần introspect method, không nên khai báo quyền invoke rộng hơn. Hints càng rộng thì executable có thể càng lớn và phạm vi reflection càng khó kiểm soát.

## 6. Viết RuntimeHintsRegistrar cho thư viện

Một thư viện có thể đóng gói các hints cần thiết trong một lớp triển khai \`RuntimeHintsRegistrar\`.

**Tệp:** \`src/main/java/com/acme/codec/AcmeCodecRuntimeHints.java\`

~~~java
package com.acme.codec;

import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class AcmeCodecRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method encode = ReflectionUtils.findMethod(
                AcmePayload.class, "encode", String.class);

        if (encode == null) {
            throw new IllegalStateException(
                    "Expected AcmePayload.encode(String) to exist");
        }

        hints.reflection().registerMethod(encode, ExecutableMode.INVOKE);
        hints.resources().registerPattern("acme/templates/*.txt");
        hints.proxies().registerJdkProxy(AcmeCodecPlugin.class);
        hints.serialization().registerType(AcmeSnapshot.class);
    }
}
~~~

Các kiểu AcmePayload, AcmeCodecPlugin và AcmeSnapshot là API của thư viện trong ví dụ:

- AcmePayload có method encode(String) được gọi bằng reflection.
- AcmeCodecPlugin là interface được dùng để tạo JDK dynamic proxy.
- AcmeSnapshot là kiểu được ghi/đọc bằng Java serialization.
- Các file template được tìm theo tên có thể thay đổi ở runtime.

Ví dụ trên cố ý đăng ký bốn nhóm hints để minh họa API. Trong thư viện thực tế, chỉ giữ những dòng phù hợp với cách code hoạt động. Nếu AcmeSnapshot không dùng Java serialization, bỏ đăng ký serialization; nếu không tạo JDK proxy, bỏ proxy hint.

### 6.1. Gắn registrar bằng @ImportRuntimeHints

Đặt registrar gần configuration hoặc bean sử dụng các truy cập động:

~~~java
package com.acme.codec.autoconfigure;

import com.acme.codec.AcmeCodecRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ImportRuntimeHints(AcmeCodecRuntimeHints.class)
public class AcmeCodecAutoConfiguration {
}
~~~

\`@ImportRuntimeHints\` cho phép Spring xử lý registrar khi component hoặc bean method được đăng ký. Khi configuration có condition và không được đưa vào BeanFactory, hints gắn với configuration đó cũng không được đóng góp. Đây là lý do nên đặt hints gần phần code cần chúng.

Nếu cần đăng ký registrar tĩnh cho toàn deployment unit, Spring Framework hỗ trợ file:

~~~text
META-INF/spring/aot.factories
~~~

Với nội dung properties:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=com.acme.codec.AcmeCodecRuntimeHints
~~~

Registrar cần constructor không tham số để được khởi tạo theo cơ chế này. Khi có thể, ưu tiên \`@ImportRuntimeHints\` vì nó gắn vòng đời hints với component/bean thực sự được đóng góp.

### 6.2. Hints cho dependency tùy chọn

Nếu registrar có thể được dùng trong nhiều classpath khác nhau, không giả định class tùy chọn luôn có mặt. Dùng API hỗ trợ kiểm tra class theo tên và class loader, ví dụ \`registerTypeIfPresent\`, hoặc đặt registrar trong integration artifact chỉ được nạp khi SDK tương ứng có mặt.

Ví dụ theo hướng class name:

~~~java
hints.reflection().registerTypeIfPresent(
        classLoader,
        "com.vendor.codec.OptionalPayload",
        typeHint -> typeHint.withMethod(
                "decode",
                java.util.List.of(
                        org.springframework.aot.hint.TypeReference.of(String.class)),
                ExecutableMode.INVOKE));
~~~

Cách này cho phép đăng ký hint có điều kiện theo class loader mà không buộc code trực tiếp tham chiếu kiểu tùy chọn. Tuy nhiên, nếu integration không có trên classpath thì không nên đưa adapter của integration đó vào bean graph.

## 7. Hints tự động và những trường hợp cần bổ sung

Spring AOT đã tự suy luận nhiều nhu cầu phổ biến. Ví dụ, khi Spring nhận diện kiểu trả về của controller cần serialize thành JSON, framework có thể thêm reflection hints cần thiết. Một số annotation như \`@EventListener\` được thiết kế để báo cho Spring biết method cần được gọi qua reflection.

Trước khi tự đăng ký hints, hãy kiểm tra xem framework đã hỗ trợ trường hợp đó chưa.

### 7.1. @RegisterReflectionForBinding

Khi một DTO cần reflection cho binding hoặc serialization/deserialization mà Spring không tự suy luận được, có thể dùng annotation tiện ích:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;

@RegisterReflectionForBinding(AcmePayload.class)
@Configuration
class AcmeJsonConfiguration {
}
~~~

Annotation này phù hợp cho reflection cần thiết khi bind object, bao gồm constructor, field, property và kiểu lồng nhau theo quy tắc của registrar binding. Nó không thay thế resource hints, proxy hints hoặc JNI hints.

### 7.2. Đừng đăng ký toàn bộ reflection một cách tùy tiện

Ví dụ, việc bật mọi field/method/constructor của một class có thể làm tăng metadata và bề mặt truy cập. Ưu tiên:

- Chỉ đăng ký method/constructor thực sự được gọi.
- Chỉ đăng ký field nếu code thực sự đọc/ghi bằng reflection.
- Dùng binding hints cho DTO binding thay vì mở toàn bộ class một cách thủ công.
- Đăng ký resource pattern hẹp, không đưa toàn bộ classpath resources vào executable.
- Chỉ đăng ký proxy với đúng danh sách interface và đúng thứ tự cần dùng.

## 8. Metadata JSON trực tiếp cho GraalVM

Ngoài Spring RuntimeHints, có thể cung cấp metadata JSON tĩnh. Spring Boot 3.3 mô tả các file hint được tạo hoặc sử dụng trong thư mục:

~~~text
META-INF/native-image/{groupId}/{artifactId}/
~~~

Các loại file cấu hình quen thuộc trong toolchain của Boot 3.3 gồm:

- \`reflect-config.json\`
- \`resource-config.json\`
- \`serialization-config.json\`
- \`proxy-config.json\`
- \`jni-config.json\`

Ví dụ một resource cần được đóng gói:

**Tệp:** \`src/main/resources/META-INF/native-image/com.acme/acme-codec-additional/resource-config.json\`

~~~json
{
  "resources": {
    "includes": [
      {
        "pattern": "\\\\Qacme/templates/default.txt\\\\E"
      }
    ]
  }
}
~~~

Đây là dạng cấu hình JSON Native Image truyền thống dùng trong toolchain tương ứng. Cấu trúc metadata JSON có thể thay đổi theo phiên bản GraalVM; hãy kiểm tra schema mà phiên bản native-image đang dùng hỗ trợ. Spring Boot khuyến nghị đặt file hint tĩnh trong một thư mục con riêng dưới META-INF/native-image để tránh trùng với thư mục do Spring AOT sinh.

Với thư viện Spring Boot, RuntimeHints thường dễ tích hợp và kiểm thử hơn vì hints được biểu diễn bằng Java API. JSON tĩnh vẫn hữu ích khi:
- Metadata đến từ thư viện bên thứ ba không có registrar.
- Cần khai báo một số cấu hình Native Image cụ thể.
- Dự án đã có metadata được kiểm chứng và muốn đóng gói cùng artifact.

### 8.1. Reachability Metadata Repository và tracing agent

GraalVM có Reachability Metadata Repository chứa metadata do cộng đồng cung cấp cho nhiều thư viện. Native Build Tools có thể lấy metadata phù hợp với dependency/version trong quá trình build.

Tracing agent có thể chạy cùng ứng dụng JVM hoặc test suite để ghi nhận reflection, resource, proxy và các truy cập động được thực sự thực hiện. Agent giúp phát hiện các entry còn thiếu, nhưng chỉ ghi nhận những đường code được chạy trong lần thu thập đó.

Khi dùng agent:
1. Chạy các kịch bản nghiệp vụ quan trọng.
2. Chạy test cho những nhánh có reflection/resource động.
3. Dùng access filter nếu output chứa nhiều truy cập của test framework.
4. Review metadata được sinh và loại entry không cần thiết.
5. Chạy lại native build và native tests.

Agent là công cụ khám phá, không phải bằng chứng mọi đường code đã được bao phủ. Kịch bản chưa chạy có thể vẫn thiếu metadata.

## 9. Kiểm thử classpath condition và runtime hints riêng biệt

Hai cơ chế phải có test riêng vì chúng bảo vệ hai hợp đồng khác nhau.

### 9.1. Kiểm thử @ConditionalOnClass với FilteredClassLoader

**Tệp:** \`src/test/java/com/acme/codec/OptionalCodecConditionTests.java\`

~~~java
package com.acme.codec;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalCodecConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(OptionalCodecAutoConfiguration.class));

    @Test
    void createsAdapterWhenOptionalCodecClassIsPresent() {
        runner.run(context ->
                assertThat(context).hasSingleBean(CodecAdapter.class));
    }

    @Test
    void skipsAdapterWhenOptionalCodecClassIsAbsent() {
        runner.withClassLoader(new FilteredClassLoader(OptionalCodecApi.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean(CodecAdapter.class));
    }

    @AutoConfiguration
    @ConditionalOnClass(name = "com.acme.codec.OptionalCodecApi")
    static class OptionalCodecAutoConfiguration {

        @Bean
        CodecAdapter codecAdapter() {
            return new CodecAdapter();
        }
    }
}

interface OptionalCodecApi {
}

class CodecAdapter {
}
~~~

Test thứ nhất xác nhận class có trên test classpath nên condition khớp. Test thứ hai dùng FilteredClassLoader để mô phỏng classpath thiếu API tùy chọn; bean adapter không được đăng ký.

Test này chỉ xác minh điều kiện classpath. Nó **không** chứng minh reflection/resource metadata đủ cho native executable.

### 9.2. Kiểm thử RuntimeHintsRegistrar bằng RuntimeHintsPredicates

**Tệp:** \`src/test/java/com/acme/codec/AcmeCodecRuntimeHintsTests.java\`

~~~java
package com.acme.codec;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeCodecRuntimeHintsTests {

    @Test
    void registersReflectionAndResourceHints() {
        RuntimeHints hints = new RuntimeHints();

        new AcmeCodecRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(AcmePayload.class, "encode")
                .invoke())
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("acme/templates/default.txt"))
                .accepts(hints);
    }
}
~~~

Giả sử AcmeCodecRuntimeHints đăng ký method encode và pattern resource như ví dụ ở phần trước. Test dùng \`RuntimeHintsPredicates\` để kiểm tra registrar có khai báo đúng hints hay không.

Có thể mở rộng kiểm thử cho serialization và proxy bằng các predicate tương ứng. Không nên chỉ assert rằng registrar đã chạy; hãy assert chính xác method/resource/type mà ứng dụng cần.

### 9.3. Unit test hints chưa đủ

RuntimeHintsPredicates kiểm tra metadata Spring tạo ra. Nó không tự chạy GraalVM Native Image và không chứng minh executable thực tế khởi động được.

Một pipeline native nên có:
- Test JVM cho business logic và auto-configuration.
- Test classpath condition cho optional dependency.
- Unit test cho RuntimeHintsRegistrar.
- AOT processing ở build time.
- Native compilation.
- Smoke/integration test chạy chính native executable và thực hiện đường reflection/resource/proxy quan trọng.

## 10. Quy trình kiểm tra từ dependency đến native executable

Một quy trình thực tế:

1. **Kiểm tra dependency graph:** SDK tùy chọn có thực sự được thêm vào module/starter cần thiết không?
2. **Kiểm tra classpath condition:** dùng FilteredClassLoader hoặc test context để xác nhận nhánh có/không có SDK.
3. **Chạy AOT processing:** dùng đúng profile/task của Spring Boot plugin để condition được đánh giá với build-time Environment dự định.
4. **Kiểm tra generated assets:** xem source/bytecode và hints được tạo dưới output AOT của build tool.
5. **Kiểm tra custom hints:** chạy RuntimeHintsPredicates tests.
6. **Build native image:** dùng GraalVM Native Image hoặc native build plugin phù hợp với JDK/Boot version.
7. **Chạy native executable:** thực hiện các đường code sử dụng reflection, resource, proxy, serialization hoặc JNI.
8. **Điều tra lỗi missing registration:** xem thông báo của Native Image, bổ sung hint chính xác rồi lặp lại test.

Với Spring Boot 3.3, tài liệu mô tả output AOT thường nằm trong:
- Maven: \`target/spring-aot/main/resources\`.
- Gradle: \`build/generated/aotResources\`.

Các đường dẫn có thể thay đổi theo plugin/build layout. Kiểm tra output thực tế của dự án thay vì giả định một thư mục cố định.

## 11. Ví dụ tình huống kết hợp cả hai cơ chế

Giả sử Acme cung cấp Vendor Codec integration:

**Classpath condition**

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.Codec")
@ImportRuntimeHints(AcmeCodecRuntimeHints.class)
class AcmeVendorCodecAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CodecAdapter.class)
    CodecAdapter codecAdapter() {
        return new CodecAdapter();
    }
}
~~~

**Khi ứng dụng JVM chạy thông thường:**

- SDK có trên classpath: classpath condition khớp và bean adapter có thể được tạo.
- SDK không có: configuration class bị bỏ qua.

**Khi ứng dụng được AOT/native build:**

- SDK có trên classpath tại thời điểm AOT: nhánh cấu hình có thể được đưa vào bean graph.
- SDK không có tại thời điểm AOT: nhánh không được tạo trong AOT bean graph.
- Registrar được xử lý khi configuration được đóng góp; các hints được chuyển sang metadata native.
- GraalVM dùng static analysis cùng metadata để giữ những truy cập động mà adapter cần.

**Khi native executable chạy:**

- Classpath không thể thay đổi để thêm SDK khác.
- Bean graph đã được cố định theo AOT build.
- Reflection/resource/proxy được khai báo có thể hoạt động theo hints đã đóng gói.
- Property runtime không thể bật một auto-configuration đã bị loại trong quá trình AOT.

Ví dụ này cho thấy condition và hints phối hợp theo chuỗi: condition quyết định integration có tham gia AOT; hints mô tả những truy cập động mà integration cần khi đã được đưa vào executable.

## 12. Lỗi thường gặp khi nhầm hai cơ chế

1. **Cho rằng @ConditionalOnClass tự đăng ký reflection.** Condition chỉ kiểm tra classpath; thêm RuntimeHints khi có truy cập động cần thiết.
2. **Cho rằng reflection hint sẽ thêm dependency còn thiếu.** Hints không thay dependency management; SDK vẫn phải nằm trên classpath lúc build.
3. **Chỉ test classpath condition rồi kết luận native image tương thích.** Test condition không kiểm tra reflection/resource/proxy metadata.
4. **Chỉ test RuntimeHintsRegistrar rồi kết luận bean được kích hoạt.** Hint test không xác minh auto-configuration condition hoặc dependency graph.
5. **Thay đổi property để bật bean sau native build.** AOT đã đánh giá condition và cố định bean graph; chọn profile/property phù hợp khi build.
6. **Dùng property condition như công tắc bật/tắt bean động trong native executable.** Hãy đăng ký sẵn các strategy và chọn hành vi runtime bên trong bean khi yêu cầu chỉ là đổi cách xử lý.
7. **Đặt @ConditionalOnClass trên method có return type thuộc SDK tùy chọn.** JVM có thể resolve method signature trước condition; bảo vệ ở class-level và tách integration.
8. **Khai báo reflection cho cả class dù chỉ một method được gọi.** Metadata quá rộng làm tăng bề mặt truy cập và có thể tăng kích thước image; đăng ký chính xác.
9. **Quên resource có tên được ghép động.** Native Image không thể luôn suy ra tên resource; đăng ký pattern đủ hẹp.
10. **Cho rằng Spring AOT luôn tự tìm được mọi truy cập động.** Framework tự suy luận nhiều contract nhưng không thể biết mọi reflection/resource lookup do thư viện thực hiện.
11. **Đăng ký hints ở cấu hình không liên quan.** Hints có thể bị đóng gói ngay cả khi feature không được dùng; đặt @ImportRuntimeHints gần component cần chúng.
12. **Dùng tracing agent nhưng không chạy đủ kịch bản.** Agent chỉ ghi nhận những đường code đã thực thi; bổ sung test cho nhánh ít gặp.
13. **Giữ nguyên toàn bộ output tracing agent của test suite.** Test framework có thể tạo nhiều metadata không cần cho runtime; review và lọc output.
14. **Dùng JSON metadata theo schema khác phiên bản GraalVM.** Kiểm tra định dạng và schema mà toolchain dự án hỗ trợ.
15. **Chỉ chạy JVM test sau khi thêm hints.** Phần lớn JVM không cần các hints đó; phải chạy AOT/native build và native executable để kiểm tra tác dụng.

## 13. Checklist review cho thư viện Spring Boot hỗ trợ native image

### Classpath và auto-configuration

- [ ] Mỗi optional integration có dependency và classpath condition rõ.
- [ ] Optional class được bảo vệ ở class-level nếu method signature tham chiếu nó.
- [ ] Điều kiện property/profile ảnh hưởng bean graph được cung cấp ở build-time AOT.
- [ ] Auto-configuration có test khi dependency hiện diện và khi bị loại khỏi classpath.
- [ ] Không dựa vào việc thay classpath hoặc bean graph sau native build.

### Runtime hints

- [ ] Đã xác định các thao tác reflection, resource, serialization, JDK proxy và JNI.
- [ ] Đã kiểm tra phần nào Spring AOT tự suy luận.
- [ ] Registrar chỉ đăng ký phần tử cần thiết.
- [ ] Hints được gắn gần component bằng @ImportRuntimeHints khi phù hợp.
- [ ] Resource pattern đủ cụ thể.
- [ ] Class tùy chọn được xử lý theo class loader hoặc tách artifact phù hợp.
- [ ] RuntimeHintsPredicates tests xác nhận metadata cần thiết.

### Native verification

- [ ] AOT processing chạy với đúng profile/property build.
- [ ] Generated AOT assets được kiểm tra khi cần chẩn đoán.
- [ ] Native image build thành công.
- [ ] Native executable được chạy trong CI hoặc môi trường xác minh.
- [ ] Test đi qua các đường reflection/resource/proxy quan trọng.
- [ ] Metadata tracing agent đã được review, không sao chép mù quáng.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** \`@ConditionalOnClass(name = "com.vendor.codec.Codec")\` trả lời câu hỏi gì?

**Đáp án:** Nó kiểm tra class Codec có trên classpath để auto-configuration có đủ điều kiện áp dụng hay không. Nó không đăng ký reflection hoặc resource hints.

**Câu 2.** SDK có trên classpath khi AOT build nhưng method được gọi bằng reflection không xuất hiện trong native image. Cần xem cơ chế nào?

**Đáp án:** Reachability metadata/runtime hints. Condition đã xác nhận dependency hiện diện; vấn đề nằm ở truy cập động mà static analysis không suy ra được.

**Câu 3.** Nếu \`acme.codec.enabled=false\` lúc AOT build rồi đổi thành true khi chạy native executable, bean codec có được tạo không?

**Đáp án:** Không. Condition ảnh hưởng bean graph đã được đánh giá ở build time; property runtime không thể tạo thêm bean đã bị loại.

**Câu 4.** Một resource được đọc bằng tên ghép từ locale. Nên khai báo gì?

**Đáp án:** Resource hint với pattern đủ hẹp, ví dụ \`acme/templates/*\`, hoặc cách đăng ký resource tương đương qua RuntimeHints.

**Câu 5.** RuntimeHintsPredicates test pass có chứng minh native executable hoạt động không?

**Đáp án:** Không. Nó xác minh Spring registrar đã khai báo hints. Vẫn cần AOT processing, native compilation và test chạy executable trên các đường code quan trọng.

**Câu 6.** Khi SDK tùy chọn không có trên classpath, có nên vẫn đăng ký hints cho mọi class của SDK không?

**Đáp án:** Không nên đưa integration đó vào build graph khi dependency vắng mặt. Tách registrar theo integration hoặc dùng classloader-aware registration; classpath condition và hints cần cùng phản ánh cấu trúc dependency thực tế.

## 15. Ghi nhớ

Hãy phân biệt hai lớp quyết định:

- **Classpath condition** quyết định một auto-configuration có được tham gia hay không. Trong native build, Spring AOT đánh giá condition với classpath và Environment tại build time, rồi tạo bean graph cố định.
- **Reachability metadata/runtime hints** mô tả các truy cập động mà GraalVM không thể suy ra đầy đủ bằng static analysis, chẳng hạn reflection, resource lookup, serialization, JDK proxy hoặc JNI.

Một dependency có mặt không tự động được phép truy cập qua reflection. Một hint không tự thêm dependency hoặc tạo bean. Khi thiết kế native-friendly starter, hãy test cả hai hợp đồng riêng: test condition với classpath thay đổi và test hints bằng RuntimeHintsPredicates; sau đó xác minh bằng native build và native executable.

### Tài liệu Spring Boot, Spring Framework và GraalVM chính thức

- [Spring Boot 3.3 — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot 3.3 — Advanced Native Image Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot 3.3 — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/how-to/aot.html)
- [Spring Framework 6.1 — Ahead-of-Time Optimizations and Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework 6.1 — RuntimeHintsRegistrar Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html)
- [Spring Framework 6.1 — ImportRuntimeHints Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ImportRuntimeHints.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/)
