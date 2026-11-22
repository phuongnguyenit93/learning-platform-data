# RuntimeHints và @ImportRuntimeHints cho reflection, resource và proxy trong Spring Boot Native Image

## 1. Vì sao Native Image cần Runtime Hints?

Trên JVM thông thường, nhiều thao tác động vẫn hoạt động vì runtime có thể tra cứu class và member khi chương trình đang chạy. Ví dụ:
- Gọi method bằng reflection sau khi chỉ biết tên method dưới dạng chuỗi.
- Đọc một file resource bằng đường dẫn classpath được tạo động.
- Tạo JDK dynamic proxy từ một danh sách interface.
- Dùng Java serialization hoặc JNI.

GraalVM Native Image phân tích ứng dụng ở build-time theo mô hình closed-world. Những class, method, resource hoặc proxy không được nhận diện là cần thiết có thể bị loại khỏi image. Khi code thực hiện thao tác động ở runtime, ứng dụng có thể gặp lỗi dù chạy tốt trên JVM.

Spring Framework cung cấp API `RuntimeHints` để mô tả những khả năng động mà native runtime cần giữ lại. Trong Spring Boot 3.3, thư viện có thể triển khai `RuntimeHintsRegistrar` và gắn registrar vào cấu hình bằng `@ImportRuntimeHints`.

**Runtime hints là metadata cho quá trình AOT/native build.** Chúng không tự tạo bean, không thay đổi logic nghiệp vụ, không biến một thao tác reflection thành thao tác trực tiếp và cũng không làm một thư viện vốn không tương thích native trở nên tương thích hoàn toàn.

## 2. Các nhóm hint trong RuntimeHints

Một đối tượng `RuntimeHints` gom các yêu cầu về khả năng truy cập lúc runtime:

| API | Mục đích | Ví dụ |
| --- | --- | --- |
| `hints.reflection()` | Cho phép truy cập type, constructor, field hoặc method bằng reflection | Một thư viện cũ gọi method theo tên |
| `hints.resources()` | Giữ resource hoặc resource pattern trong native image | File rules trong `src/main/resources` |
| `hints.proxies()` | Khai báo JDK interface proxy cần tạo | `Proxy.newProxyInstance(...)` |
| `hints.serialization()` | Hỗ trợ Java serialization | Đọc/ghi object qua `ObjectInputStream` |
| `hints.jni()` | Khai báo truy cập qua Java Native Interface | Tích hợp native library qua JNI |

Bài này tập trung vào reflection, resource và proxy. Serialization và JNI là các nhóm riêng; không nên nhầm Java serialization với JSON serialization của Jackson.

Một hint chỉ nên được đăng ký khi code thực sự cần hành vi đó. Đăng ký quá rộng làm native image giữ lại nhiều thành phần hơn, tăng kích thước và có thể che giấu một thiết kế phụ thuộc reflection không cần thiết.

## 3. Spring tự suy ra được những gì?

Không phải cứ thấy reflection hoặc JSON là phải tự viết registrar. Spring AOT tự tạo nhiều hint cho các trường hợp framework hiểu được, ví dụ:
- Kiểu dữ liệu request/response của các method trong `@RestController` thường được phân tích để tạo reflection hint cần thiết cho serialization.
- `@ConfigurationProperties` được Spring AOT xử lý để tạo reflection hint cho binding.
- Các cấu hình và proxy do Spring quản lý có thể được AOT engine xử lý dựa trên metadata mà framework quan sát được.

Một số trường hợp vẫn cần bổ sung:
- Thư viện gọi reflection bằng tên class/method lấy từ file cấu hình.
- Resource path được tạo động và không thể suy ra từ source.
- Ứng dụng tự tạo JDK proxy bằng danh sách interface động.
- DTO được bind hoặc serialize qua `WebClient`, `RestClient` hoặc `RestTemplate` theo cách Spring không thể suy ra type từ controller signature.
- Thư viện bên thứ ba thực hiện hành vi động mà Spring không có integration tương ứng.

Với DTO cần binding, hãy xem `@RegisterReflectionForBinding` trước khi tự đăng ký từng field/method. Với một thao tác reflection tùy biến, resource hoặc proxy mà framework không suy ra được, dùng `RuntimeHintsRegistrar`.

## 4. RuntimeHintsRegistrar là gì?

`RuntimeHintsRegistrar` là callback mà Spring AOT gọi để thư viện đóng góp các hint vào đối tượng `RuntimeHints` do AOT engine quản lý.

Contract của interface:

~~~java
public interface RuntimeHintsRegistrar {
    void registerHints(RuntimeHints hints, ClassLoader classLoader);
}
~~~

Hai tham số:
- `hints` là nơi đăng ký reflection, resource, proxy, serialization hoặc JNI hint.
- `classLoader` là class loader của deployment unit. Nó có thể không có sẵn trong một số môi trường, vì vậy khi xử lý dependency tùy chọn, không nên giả định tham số này luôn khác `null`.

Implementation nên có constructor không tham số để Spring có thể khởi tạo trong AOT processing. Phương thức `registerHints` được gọi ở build-time, không phải callback được gọi lại mỗi khi người dùng thực hiện request.

## 5. Kết nối registrar bằng @ImportRuntimeHints

Với thư viện auto-configuration, cách khai báo dễ theo dõi là đặt `@ImportRuntimeHints` trên class `@AutoConfiguration`:

~~~java
package com.acme.catalog.autoconfigure;

import com.acme.catalog.aot.CatalogRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

Spring AOT phát hiện annotation này và gọi registrar trong quá trình xử lý cấu hình. Trong thư viện thật, `CatalogAutoConfiguration` vẫn phải được công bố theo cơ chế auto-configuration của Spring Boot, chẳng hạn qua `AutoConfiguration.imports`.

`@ImportRuntimeHints` cũng có thể được đặt trên Spring bean hoặc method factory `@Bean`. Với một nhóm hint thuộc về thư viện, gắn nó lên auto-configuration hoặc configuration class sở hữu tính năng đó thường làm rõ ownership và phạm vi hơn.

Luồng xử lý:

~~~mermaid
flowchart TD
    A["Spring Boot AOT processing"] --> B["Phân tích CatalogAutoConfiguration"]
    B --> C["Đọc @ImportRuntimeHints"]
    C --> D["Khởi tạo CatalogRuntimeHints"]
    D --> E["Gọi registerHints(...)"]
    E --> F["Gom reflection/resource/proxy hints"]
    F --> G["Sinh metadata cho native-image build"]
    G --> H["GraalVM phân tích và tạo native executable"]
~~~

Nếu chỉ chạy ứng dụng trên JVM thông thường mà không thực hiện AOT processing, annotation này không tự làm thay đổi cách code reflection/resource/proxy hoạt động trên JVM.

## 6. Đăng ký reflection cho method cụ thể

Giả sử một thư viện cũ chỉ biết tên method khi runtime:

~~~java
package com.acme.catalog.legacy;

public final class LegacyDecoder {

    public String decode(String value) {
        return value.trim();
    }
}
~~~

Ứng dụng gọi method bằng reflection:

~~~java
Method method = LegacyDecoder.class.getDeclaredMethod(
        "decode", String.class);

String decoded = (String) method.invoke(
        new LegacyDecoder(), "  item-42  ");
~~~

Trên JVM, method có thể được tìm thấy bằng reflection. Trong native image, cần khai báo quyền truy cập reflection tương ứng trước khi build.

Registrar:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;
import java.util.Objects;

import com.acme.catalog.legacy.LegacyDecoder;
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = Objects.requireNonNull(
                ReflectionUtils.findMethod(
                        LegacyDecoder.class, "decode", String.class));

        hints.reflection().registerMethod(
                decode, ExecutableMode.INVOKE);
    }
}
~~~

`ExecutableMode.INVOKE` khai báo method cần được gọi bằng reflection. Spring cũng phân biệt nhu cầu introspection với invocation; chỉ đăng ký quyền cần thiết cho thao tác thực tế.

Nếu cần truy cập constructor hoặc field, dùng các API tương ứng của `ReflectionHints`. Nếu cần nhiều member của cả type, có thể đăng ký theo `MemberCategory`, nhưng nên giới hạn danh mục thay vì bật mọi loại truy cập một cách mặc định.

### Khi nào dùng RegisterReflectionForBinding?

Nếu mục đích là để Spring bind hoặc serialize/deserialize một DTO, annotation chuyên dụng thường phù hợp hơn việc tự đăng ký từng method:

~~~java
@Component
@RegisterReflectionForBinding(CatalogPayload.class)
class CatalogHttpAdapter {
}
~~~

`@RegisterReflectionForBinding` tạo các reflection hint cần thiết cho binding, bao gồm constructor, field, property và các type được tham chiếu theo quy tắc của processor. Nó không thay thế hint cho một method tùy ý được gọi bằng reflection.

## 7. Giữ classpath resource bằng ResourceHints

Native Image không tự giữ mọi resource nằm trong JAR. Nếu thư viện đọc file theo tên hoặc pattern mà AOT không suy ra được, đăng ký resource:

~~~java
hints.resources().registerPattern(
        "catalog/catalog-rules.properties");
~~~

Giả sử resource nằm tại:

~~~text
src/main/resources/
└── catalog/
    └── catalog-rules.properties
~~~

Nội dung:

~~~properties
mode=strict
max-items=100
~~~

Ứng dụng có thể đọc file qua class loader:

~~~java
try (InputStream input = getClass().getClassLoader()
        .getResourceAsStream("catalog/catalog-rules.properties")) {

    if (input == null) {
        throw new IllegalStateException("Catalog rules not found");
    }

    Properties properties = new Properties();
    properties.load(input);
}
~~~

`registerPattern` nhận đường dẫn resource tương đối với classpath và hỗ trợ pattern. Nếu thư viện cần một nhóm file, có thể đăng ký pattern phù hợp thay vì từng file riêng lẻ.

Phân biệt hai trường hợp:
- Resource đóng gói trong classpath/JAR cần được giữ trong native image.
- File do người vận hành đặt bên ngoài trên filesystem là dữ liệu triển khai; không nên đăng ký nó như classpath resource. Hãy đọc từ đường dẫn filesystem và cấu hình mount/volume phù hợp.

## 8. Đăng ký JDK dynamic proxy

JDK proxy tạo một class proxy thực thi một hoặc nhiều interface. Ví dụ:

~~~java
public interface CatalogClient {
    String findById(String id);
}
~~~

Ứng dụng tạo proxy động:

~~~java
CatalogClient client = (CatalogClient) Proxy.newProxyInstance(
        CatalogClient.class.getClassLoader(),
        new Class<?>[] { CatalogClient.class },
        (proxy, method, args) -> "catalog:" + args[0]);
~~~

Native Image cần biết proxy interface này được sử dụng. Đăng ký bằng:

~~~java
hints.proxies().registerJdkProxy(CatalogClient.class);
~~~

Nếu proxy thực tế implement nhiều interface, truyền toàn bộ interface vào cùng một lần đăng ký và giữ đúng thứ tự tương ứng với proxy được tạo. Danh sách interface là một phần của mô tả proxy.

**Giới hạn API:** `registerJdkProxy` khai báo JDK interface-based proxy. Không dùng nó để mô tả CGLIB/class-based proxy. Proxy do Spring AOP hoặc framework khác tạo có thể đã được Spring AOT hỗ trợ; nếu tự tạo proxy theo cơ chế riêng, cần kiểm tra đúng loại proxy và hướng dẫn native tương ứng.

## 9. Ghép reflection, resource và proxy trong một registrar

Một thư viện thường cần nhiều loại hint cùng lúc. Có thể gom chúng trong một implementation:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;
import java.util.Objects;

import com.acme.catalog.api.CatalogClient;
import com.acme.catalog.legacy.LegacyDecoder;
import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public final class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = Objects.requireNonNull(
                ReflectionUtils.findMethod(
                        LegacyDecoder.class, "decode", String.class));

        // Method được gọi bằng reflection.
        hints.reflection().registerMethod(
                decode, ExecutableMode.INVOKE);

        // File được đọc từ classpath trong native runtime.
        hints.resources().registerPattern(
                "catalog/catalog-rules.properties");

        // Ứng dụng tạo JDK proxy cho interface này.
        hints.proxies().registerJdkProxy(CatalogClient.class);
    }
}
~~~

Gắn registrar vào auto-configuration:

~~~java
@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

Cấu trúc module có thể như sau:

~~~text
acme-catalog-autoconfigure/
├── src/main/java/com/acme/catalog/
│   ├── api/CatalogClient.java
│   ├── legacy/LegacyDecoder.java
│   ├── aot/CatalogRuntimeHints.java
│   └── autoconfigure/CatalogAutoConfiguration.java
└── src/main/resources/
    └── catalog/catalog-rules.properties
~~~

Một registrar nên mô tả đúng các hành vi mà module sở hữu. Nếu nhiều tích hợp độc lập cần hint khác nhau, có thể tách registrar nhỏ và gắn vào từng auto-configuration tương ứng để dễ review và bảo trì.

## 10. Kiểm thử registrar bằng RuntimeHintsPredicates

Không cần build native image cho mỗi thay đổi nhỏ trong registrar. Spring cung cấp `RuntimeHintsPredicates` để kiểm tra hint đã được đăng ký vào đối tượng `RuntimeHints` hay chưa.

Ví dụ JUnit 5 và AssertJ:

~~~java
package com.acme.catalog.aot;

import java.lang.reflect.Method;

import com.acme.catalog.api.CatalogClient;
import com.acme.catalog.legacy.LegacyDecoder;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogRuntimeHintsTests {

    @Test
    void registersReflectionResourceAndProxyHints() throws Exception {
        RuntimeHints hints = new RuntimeHints();

        new CatalogRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        Method decode = LegacyDecoder.class.getDeclaredMethod(
                "decode", String.class);

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(decode).invoke())
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("catalog/catalog-rules.properties"))
                .accepts(hints);

        assertThat(RuntimeHintsPredicates.proxies()
                .forInterfaces(CatalogClient.class))
                .accepts(hints);
    }
}
~~~

Chạy test trên JVM:

~~~bash
./gradlew test --tests "*CatalogRuntimeHintsTests"
~~~

Hoặc Maven:

~~~bash
./mvnw -Dtest=CatalogRuntimeHintsTests test
~~~

Test này kiểm tra ba hợp đồng của registrar:
- Method `LegacyDecoder.decode(String)` được đăng ký với mode invocation.
- Resource `catalog/catalog-rules.properties` có hint.
- JDK proxy cho `CatalogClient` có hint.

`RuntimeHintsPredicates` xác nhận metadata đã được khai báo. Nó không chứng minh toàn bộ native executable sẽ chạy thành công; vẫn cần AOT processing, native-image build và test trên executable đối với các luồng quan trọng.

## 11. Các cách đăng ký hint khác

`@ImportRuntimeHints` thường là lựa chọn dễ hiểu nhất khi hint gắn với một cấu hình cụ thể. Spring Framework còn hỗ trợ hai cách khác.

### 11.1. Đăng ký qua META-INF/spring/aot.factories

Có thể đăng ký registrar tĩnh trong resource:

`src/main/resources/META-INF/spring/aot.factories`

Nội dung:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=com.acme.catalog.aot.CatalogRuntimeHints
~~~

Cách này phù hợp khi thư viện muốn đóng góp hint mà không gắn registrar vào một configuration class cụ thể. Implementation cần constructor không tham số và phải nằm trên classpath lúc AOT processing.

Không nên đăng ký cùng một registrar qua nhiều cơ chế nếu không có lý do; tránh làm metadata bị lặp và khó truy dấu nguồn.

### 11.2. Native Image JSON metadata

GraalVM cũng hỗ trợ metadata tĩnh trong các file JSON dưới thư mục `META-INF/native-image`. Spring Boot 3.3 ghi nhận hints sinh tự động nằm trong thư mục theo `groupId/artifactId`; metadata bổ sung nên đặt ở thư mục riêng để tránh xung đột với output được sinh.

Cách JSON hữu ích khi:
- Thư viện không tích hợp Spring AOT.
- Cần chia sẻ metadata với nhiều ứng dụng native.
- Metadata được cung cấp bởi thư viện bên thứ ba.
- Một số hint không thuận tiện để diễn đạt bằng registrar.

Nếu đã dùng `RuntimeHintsRegistrar` cho một thư viện Spring, giữ hint trong code thường giúp type reference được kiểm tra khi compile và dễ viết unit test hơn.

## 12. Dùng tracing agent để tìm hint còn thiếu

Khi ứng dụng chạy tốt trên JVM nhưng lỗi trong native image, GraalVM tracing agent có thể ghi nhận các thao tác reflection, resource hoặc proxy thực sự diễn ra trên JVM.

Ví dụ chạy ứng dụng AOT trên JVM cùng agent:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/my-application.jar
~~~

Sau đó:
1. Thực hiện các luồng ứng dụng có sử dụng reflection/resource/proxy.
2. Dừng ứng dụng để agent ghi các file cấu hình.
3. Kiểm tra các hint được sinh và xác định những entry thực sự thuộc ứng dụng.
4. Loại metadata chỉ phục vụ test infrastructure nếu không cần ở runtime.
5. Đưa các file cần thiết vào thư mục `src/main/resources/META-INF/native-image/` hoặc chuyển các entry cần thiết thành `RuntimeHintsRegistrar`.
6. Build native image lại và chạy regression test.

Tracing agent chỉ ghi những đường code đã được thực thi. Nếu không chạy một nhánh nghiệp vụ, agent không thể tự phát hiện hint của nhánh đó. Vì vậy agent hỗ trợ điều tra, không thay thế việc hiểu code và thiết kế test coverage.

## 13. Nested configuration properties và các hint có sẵn của Boot

Spring Boot tự tạo reflection hints cho `@ConfigurationProperties` trong AOT processing. Tuy nhiên, nested properties dùng một class riêng không phải inner class cần được đánh dấu `@NestedConfigurationProperty` để Spring nhận diện cấu trúc binding trong native image.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "catalog")
public class CatalogProperties {

    private String region;

    @NestedConfigurationProperty
    private final RetrySettings retry = new RetrySettings();

    // getters...
}
~~~

Nếu `RetrySettings` là class độc lập, annotation giúp Spring AOT nhận biết đây là nested configuration property. Với constructor binding hoặc record, cần đặt annotation lên field/parameter tương ứng theo hướng dẫn của Boot.

Đây là hint/binding metadata mà Spring Boot đã có quy tắc hỗ trợ. Đừng thêm một registrar reflection tổng quát cho toàn bộ properties chỉ để bù cho một nested type chưa được đánh dấu đúng.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Method chạy bằng reflection trên JVM nhưng lỗi trong native | Thiếu method invocation hint | Đăng ký đúng method bằng `registerMethod(..., ExecutableMode.INVOKE)` |
| Resource có trong JAR nhưng không đọc được trong native | Resource chưa được reachability metadata giữ lại | Đăng ký `resources().registerPattern(...)` và kiểm tra path |
| `Proxy.newProxyInstance` lỗi trong native | Thiếu JDK proxy hint hoặc danh sách interface không khớp | Đăng ký `registerJdkProxy` với đúng interface và thứ tự |
| Đã có proxy hint nhưng vẫn lỗi CGLIB | Đã dùng nhầm hint cho proxy class-based | Phân tích cơ chế proxy cụ thể; `registerJdkProxy` chỉ dành cho JDK interface proxy |
| DTO JSON lỗi reflection | AOT không nhận diện đường binding của DTO | Xem `@RegisterReflectionForBinding` hoặc hint binding tương ứng |
| Registrar không được gọi | Chưa gắn `@ImportRuntimeHints` hoặc chưa đăng ký `aot.factories` | Kiểm tra cấu hình được AOT phát hiện và build log |
| Hint chỉ hoạt động trong IDE | Resource hoặc registrar không được đóng gói vào module/JAR đúng | Kiểm tra source set, dependency và resource trong artifact |
| Native image vẫn thiếu hint sau khi sửa | Đang chạy binary cũ hoặc chưa thực hiện AOT/native rebuild | Chạy lại AOT processing, native compile và test executable mới |
| Native image phình to | Đăng ký quá rộng, giữ toàn bộ member/type không cần thiết | Giảm phạm vi reflection và resource pattern |
| Tracing agent tạo nhiều entry lạ | Agent đã ghi nhận test framework hoặc đường code không liên quan | Dùng access filter, review file và chỉ giữ hint cần thiết |
| Nested properties không bind trong native | Nested class độc lập chưa được nhận diện | Dùng `@NestedConfigurationProperty` đúng vị trí |
| Registrar phụ thuộc class optional gây lỗi compile/runtime | Tham chiếu type tùy chọn trực tiếp dù dependency vắng mặt | Dùng classloader-aware registration như `registerTypeIfPresent` khi phù hợp |

## 15. Quy trình triển khai và review Runtime Hints

1. **Tái hiện lỗi:** xác định thao tác nào hoạt động trên JVM nhưng thiếu trong native.
2. **Kiểm tra hỗ trợ tự động:** xem Spring AOT đã suy ra hint cho controller, configuration properties, binding hoặc proxy chưa.
3. **Chọn đúng loại hint:** reflection, resource, JDK proxy, serialization hay JNI.
4. **Giới hạn quyền truy cập:** chỉ đăng ký method/member/resource/interface thực sự cần.
5. **Đóng góp hint:** triển khai `RuntimeHintsRegistrar` và kết nối bằng `@ImportRuntimeHints`.
6. **Viết unit test:** dùng `RuntimeHintsPredicates` để xác nhận từng hint.
7. **Chạy AOT/native build:** xác nhận registrar được xử lý và metadata có mặt trong artifact.
8. **Chạy native regression test:** thực thi đúng đường code từng gây lỗi.
9. **Review kích thước và phạm vi:** bỏ các hint thừa, pattern resource quá rộng hoặc reflection access không cần thiết.
10. **Ghi lại lý do:** giải thích vì sao mỗi hint tồn tại để người bảo trì biết khi nào có thể loại bỏ.

Luồng review:

~~~mermaid
flowchart TD
    A["Xác định thao tác động"] --> B{"Spring AOT đã suy ra hint?"}
    B -->|"Có"| C["Dùng hint tự động"]
    B -->|"Không"| D{"Loại truy cập cần thiết"}
    D --> E["Reflection"]
    D --> F["Resource"]
    D --> G["JDK Proxy"]
    E --> H["RuntimeHintsRegistrar"]
    F --> H
    G --> H
    H --> I["@ImportRuntimeHints"]
    I --> J["RuntimeHintsPredicates test"]
    J --> K["AOT và native build"]
    K --> L["Native regression test"]
~~~

## 16. Tự kiểm tra kiến thức

1. `RuntimeHints` dùng để làm gì? **Mô tả các khả năng động cần được giữ trong native image.**
2. `RuntimeHintsRegistrar` được gọi ở giai đoạn nào? **Trong quá trình AOT processing tại build-time.**
3. Annotation nào kết nối registrar với configuration? **`@ImportRuntimeHints`.**
4. API nào đăng ký một method được gọi bằng reflection? **`hints.reflection().registerMethod(method, ExecutableMode.INVOKE)`.**
5. API nào giữ một classpath resource? **`hints.resources().registerPattern(...)`.**
6. API nào khai báo JDK dynamic proxy? **`hints.proxies().registerJdkProxy(...)`.**
7. `registerJdkProxy` có đăng ký CGLIB class proxy không? **Không; API này dành cho JDK interface proxy.**
8. Annotation nào hỗ trợ reflection hint cho DTO binding? **`@RegisterReflectionForBinding`.**
9. Dùng API nào để kiểm tra hint trong unit test? **`RuntimeHintsPredicates`.**
10. Unit test RuntimeHintsPredicates có chứng minh native executable hoạt động không? **Không; vẫn cần AOT/native build và regression test trên image.**
11. Resource nằm ngoài filesystem của ứng dụng có cần classpath resource hint không? **Không; cần cấu hình đường dẫn/mount filesystem phù hợp.**
12. Vì sao không nên đăng ký toàn bộ reflection member mặc định? **Làm image lớn hơn và cấp quyền truy cập rộng hơn nhu cầu thực tế.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html): custom hints, `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, testing hints, tracing agent và static metadata.
- [Spring Framework 6.1 — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): mô hình AOT và Runtime Hints.
- [Spring Framework 6.1 — `RuntimeHintsRegistrar` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/RuntimeHintsRegistrar.html): contract và cách đăng ký registrar.
- [Spring Framework 6.1 — `ProxyHints` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/aot/hint/ProxyHints.html): JDK proxy hint và danh sách interface.
- [Spring Framework 6.1 — `RuntimeHintsPredicates` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.22/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html): kiểm thử reflection, resource và proxy hints.
- [Spring Framework 6.1 — `@RegisterReflectionForBinding` JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html): reflection hints dành cho data binding và serialization.
