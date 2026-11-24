# Tái hiện lỗi reflection rồi bổ sung RuntimeHints tối thiểu

## 1. Mục tiêu thực hành

Trong bài này, ta tạo một tình huống Spring Boot chạy đúng trên JVM nhưng thất bại khi chạy bằng GraalVM Native Image. Nguyên nhân là ứng dụng tạo một object thông qua reflection: tên class và constructor chỉ được truy cập lúc runtime, nên phân tích reachability không thể luôn suy ra metadata cần giữ.

Sau khi tái hiện lỗi, ta dùng Spring AOT RuntimeHints để đăng ký đúng constructor được gọi. Mục tiêu là hiểu quy trình điều tra và sửa lỗi có căn cứ:

1. Tạo một đường chạy reflection có thể tái hiện.
2. Chạy cùng test trên JVM để xác nhận behavior mong đợi.
3. Build và chạy native executable để thấy lỗi.
4. Đọc exception và xác định class/member bị thiếu metadata.
5. Bổ sung RuntimeHints với phạm vi tối thiểu.
6. Kiểm tra hints và chạy lại native test.
7. Xác nhận các chức năng khác vẫn hoạt động.

Ví dụ dùng Java reflection để minh họa rõ cơ chế. Trong ứng dụng thực tế, hãy ưu tiên cơ chế Spring/framework hoặc thư viện đã cung cấp hints sẵn trước khi viết registrar riêng.

## 2. Bối cảnh: tạo plugin theo tên class

Giả sử service có một bộ chuyển đổi dữ liệu được chọn theo cấu hình. Ứng dụng nhận tên class từ cấu hình và tạo instance bằng reflection.

Tạo interface:

```java
package com.example.demo.plugin;

public interface PayloadFormatter {
    String format(String value);
}
```

Tạo implementation có constructor không tham số:

```java
package com.example.demo.plugin;

public class UppercaseFormatter implements PayloadFormatter {

    public UppercaseFormatter() {
    }

    @Override
    public String format(String value) {
        return value.toUpperCase();
    }
}
```

Tạo factory gọi reflection:

```java
package com.example.demo.plugin;

public class FormatterFactory {

    public PayloadFormatter create(String className) {
        try {
            Class<?> type = Class.forName(className);
            Object instance = type.getDeclaredConstructor().newInstance();
            return (PayloadFormatter) instance;
        } catch (ReflectiveOperationException ex) {
            throw new IllegalStateException(
                "Cannot create formatter: " + className, ex
            );
        }
    }
}
```

Tên class chỉ là ví dụ. Với hệ thống production, không nên nhận class name tùy ý từ request bên ngoài vì có thể tạo rủi ro bảo mật. Dùng allowlist hoặc registry có kiểm soát.

## 3. Gắn factory vào Spring Boot

Tạo service sử dụng factory:

```java
package com.example.demo;

import com.example.demo.plugin.FormatterFactory;
import com.example.demo.plugin.PayloadFormatter;
import org.springframework.stereotype.Service;

@Service
public class FormattingService {

    private final FormatterFactory factory;

    public FormattingService() {
        this.factory = new FormatterFactory();
    }

    public String format(String className, String value) {
        PayloadFormatter formatter = factory.create(className);
        return formatter.format(value);
    }
}
```

Tạo endpoint để có thể kiểm tra behavior qua HTTP:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/format")
public class FormattingController {

    private final FormattingService service;

    public FormattingController(FormattingService service) {
        this.service = service;
    }

    @GetMapping
    public String format(
            @RequestParam String formatter,
            @RequestParam String value) {
        return service.format(formatter, value);
    }
}
```

Request ví dụ:

```http
GET /format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello
```

Kết quả mong đợi là chuỗi `HELLO`.

## 4. Viết test xác nhận behavior trên JVM

Test factory hoặc service trước khi build native:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class FormattingServiceTest {

    private final FormattingService service = new FormattingService();

    @Test
    void createsFormatterThroughReflection() {
        String result = service.format(
            UppercaseFormatter.class.getName(),
            "hello"
        );

        assertThat(result).isEqualTo("HELLO");
    }
}
```

Chạy test bằng build tool của project, ví dụ Gradle:

```bash
./gradlew test
```

Hoặc Maven:

```bash
./mvnw test
```

Test này chứng minh code path hoạt động trên JVM. Nó chưa chứng minh Native Image đã có đủ reflection metadata.

## 5. Build và tái hiện lỗi trên Native Image

Build native executable bằng cấu hình project. Ví dụ với Spring Boot Gradle plugin có hỗ trợ native:

```bash
./gradlew clean nativeCompile
```

Với Maven, dùng goal/package configuration tương ứng Spring Boot Maven Plugin và Native Build Tools của dự án. Tên goal và cách bật native profile phụ thuộc version; kiểm tra task/goal thực tế thay vì áp dụng máy móc một lệnh cho mọi project.

Chạy executable được tạo:

```bash
./build/native/nativeCompile/api-app
```

Sau đó gọi endpoint:

```bash
curl "http://localhost:8080/format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello"
```

Nếu native build không có metadata cho class/constructor được gọi động, runtime có thể báo lỗi liên quan reflection, constructor hoặc class reachability. Exception cụ thể phụ thuộc GraalVM version và cấu hình build. Lưu toàn bộ stack trace, không chỉ dòng cuối.

Một số Native Image version có thể suy ra thêm metadata từ code hoặc dependency metadata. Nếu ví dụ vẫn chạy, hãy kiểm tra build output và thử một member/class được truy cập động theo đúng cách mà phân tích không thể suy ra; không cố tình thêm hints rộng chỉ để ép một lỗi giả tạo.

## 6. Đọc lỗi và xác định metadata thực sự thiếu

Khi native executable lỗi, ghi lại:

- Class được truyền vào Class.forName.
- Constructor hoặc method được gọi qua reflection.
- Access level của member.
- Exception type và cause.
- Native Image/GraalVM version.
- Build arguments và metadata đã nạp.
- Test input chính xác tái hiện lỗi.

Phân biệt các trường hợp:

| Lỗi | Hướng điều tra |
|---|---|
| Class không reachable/không được tìm thấy | Class có trong application runtime classpath và được đưa vào image chưa? |
| Constructor không được phép reflect | Đăng ký đúng constructor/access cần dùng |
| Method/field reflection fail | Xác định method/field cụ thể và quyền truy cập |
| ClassCastException | Implementation không implement interface hoặc classloader/type mismatch |
| ClassNotFoundException trên JVM | Dependency/classpath hoặc tên class sai, không phải chỉ thiếu hint |
| Bean không tồn tại | Kiểm tra Spring AOT bean graph/condition; RuntimeHints không tạo bean |

RuntimeHints chỉ mô tả metadata cho các thao tác runtime cần hỗ trợ. Nó không thêm dependency bị thiếu, không tạo Spring bean bị condition loại và không sửa sai logic cast.

## 7. Đăng ký constructor bằng RuntimeHints

Tạo registrar trong application:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class FormatterRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            UppercaseFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
```

Đăng ký registrar bằng annotation:

```java
package com.example.demo;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(FormatterRuntimeHints.class)
public class NativeHintsConfiguration {
}
```

Registrar khai báo constructor được gọi qua reflection. Nó không mở toàn bộ method/field của class và không đăng ký mọi class trong package.

API có thể thay đổi theo Spring Framework version. Dùng đúng package và method của version Spring Boot/Spring Framework mà project quản lý.

## 8. Vì sao hint phải tối thiểu?

Một hint rộng có thể khiến Native Image giữ nhiều metadata hoặc code hơn cần thiết. Điều này làm tăng kích thước binary, thời gian build và bề mặt cần kiểm tra.

Trong ví dụ, thao tác động là gọi constructor không tham số. Do đó, đăng ký declared constructors là phạm vi phù hợp để minh họa. Nếu code chỉ gọi public constructor, cân nhắc category hẹp hơn phù hợp với API/version và cách truy cập thực tế.

Không đăng ký public methods, fields hoặc all declared members nếu không có đường chạy nào cần chúng. Cũng không đăng ký cả package khi chỉ một implementation được dùng.

Nếu ứng dụng có nhiều formatter hợp lệ, có thể đăng ký từng type trong allowlist hoặc thiết kế registry tĩnh để compiler thấy các implementation trực tiếp.

## 9. Kiểm tra RuntimeHints bằng RuntimeHintsPredicates

Spring cung cấp test support để xác minh registrar đã đăng ký metadata mong đợi. Ví dụ:

```java
package com.example.demo;

import com.example.demo.plugin.UppercaseFormatter;
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class FormatterRuntimeHintsTest {

    @Test
    void registersConstructorInvocationHint() {
        RuntimeHints hints = new RuntimeHints();
        new FormatterRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(UppercaseFormatter.class)
                .withMemberCategory(
                    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
                )
                .test(hints)
        ).isTrue();
    }
}
```

Import MemberCategory trong test:

```java
import org.springframework.aot.hint.MemberCategory;
```

Test predicate xác nhận registrar khai báo đúng hint. Nó không chứng minh mọi runtime path đều hoạt động; native executable vẫn phải được test.

## 10. Chạy lại AOT và Native Image build

Sau khi thêm registrar:

1. Chạy unit test và RuntimeHints test.
2. Chạy Spring AOT processing.
3. Build lại native executable từ clean state nếu cần loại output cũ.
4. Xác nhận compiler hoàn tất và không bỏ qua registrar.
5. Chạy executable mới.
6. Gọi đúng endpoint/request fixture đã làm lỗi.
7. Chạy thêm test cho các formatter hợp lệ khác.

Ví dụ Gradle:

```bash
./gradlew clean test nativeCompile
```

Build output path và task phụ thuộc cấu hình Spring Boot/Native Build Tools. Dùng executable vừa tạo từ đúng commit, không chạy nhầm binary cũ.

## 11. Kiểm tra qua native integration test

Nếu project hỗ trợ native test execution, tạo integration test chạy application native hoặc dùng native test task của plugin. Một lựa chọn khác là khởi chạy executable trong CI rồi gọi HTTP endpoint bằng test script.

Ví dụ smoke test:

```bash
./build/native/nativeCompile/api-app &
APP_PID=$!
trap 'kill "$APP_PID" 2>/dev/null || true' EXIT

for attempt in $(seq 1 30); do
  if curl --fail --silent http://localhost:8080/actuator/health; then
    break
  fi
  sleep 1
done

curl --fail   "http://localhost:8080/format?formatter=com.example.demo.plugin.UppercaseFormatter&value=hello"
```

Ví dụ cần endpoint health phù hợp, port đúng và process cleanup phù hợp shell/CI. Trong pipeline thật, kiểm tra readiness status rõ ràng và fail nếu timeout; không để vòng lặp kết thúc mà vẫn báo pass khi app chưa sẵn sàng.

## 12. Kiểm tra nhiều implementation và allowlist

Nếu có hai implementation, thêm type thứ hai:

```java
public class LowercaseFormatter implements PayloadFormatter {
    public LowercaseFormatter() {
    }

    @Override
    public String format(String value) {
        return value.toLowerCase();
    }
}
```

Nếu cả hai được chọn bằng cấu hình runtime, đăng ký constructor của cả hai type hợp lệ:

```java
hints.reflection().registerType(
    UppercaseFormatter.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
);
hints.reflection().registerType(
    LowercaseFormatter.class,
    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
);
```

Danh sách này nên đến từ cấu hình/registry đáng tin cậy. Không nhận class name bất kỳ từ query parameter hoặc request body để instantiate tùy ý. Một registry map từ key nghiệp vụ sang supplier thường an toàn và dễ phân tích reachability hơn reflection.

## 13. Khi nào nên thay reflection bằng registry tĩnh?

Nếu số implementation nhỏ và biết trước lúc compile, registry tĩnh có thể đơn giản hơn:

```java
@Component
public class FormatterRegistry {

    private final Map<String, PayloadFormatter> formatters;

    public FormatterRegistry() {
        this.formatters = Map.of(
            "upper", new UppercaseFormatter(),
            "lower", new LowercaseFormatter()
        );
    }

    public PayloadFormatter get(String name) {
        PayloadFormatter formatter = formatters.get(name);
        if (formatter == null) {
            throw new IllegalArgumentException(
                "Unsupported formatter: " + name
            );
        }
        return formatter;
    }
}
```

Registry tĩnh giúp compiler thấy constructor calls trực tiếp và tránh metadata reflection cho đường chạy này. Tuy nhiên, nếu ứng dụng thực sự cần plugin discovery động, giữ reflection và đăng ký metadata đúng cách. Chọn kiến trúc theo yêu cầu extensibility, security và deployment.

## 14. Dùng Native Image tracing agent khi cần

Tracing agent có thể quan sát một lần chạy trên JVM và ghi lại một phần thao tác động như reflection, resource, proxy hoặc serialization. Dữ liệu agent có thể giúp tìm hints bị thiếu, nhưng chỉ bao phủ những đường chạy đã được thực thi trong lần quan sát.

Quy trình tổng quát:

1. Chạy ứng dụng JVM với tracing agent theo hướng dẫn GraalVM version đang dùng.
2. Thực hiện test scenarios đại diện.
3. Thu metadata agent sinh ra.
4. Review và loại metadata không cần thiết.
5. Chuyển sang cơ chế metadata/hints phù hợp với Spring và dependency.
6. Build native và test lại.

Không đưa output agent vào production một cách mù quáng. Agent có thể tạo metadata dư thừa và bỏ sót nhánh hiếm chưa chạy.

## 15. Các lỗi thường gặp khi thêm RuntimeHints

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Registrar không được áp dụng | Configuration chứa annotation chưa được phát hiện | Kiểm tra component/config import và AOT output |
| Hint có nhưng native vẫn lỗi | Đăng ký sai type/member hoặc binary cũ | Đọc stack trace, clean build và xác minh executable |
| Constructor hint không đủ | Code còn gọi method/field qua reflection | Xác định member thực tế và đăng ký tối thiểu |
| Class không có trong image | Dependency hoặc classpath thiếu | Sửa dependency/application module |
| Bean không tồn tại | Profile/condition loại bean khi AOT | Sửa build-time profile/property |
| Resource không tìm thấy | Thiếu resource hint hoặc resource không nằm trong artifact | Kiểm tra resource path/pattern |
| JVM test pass nhưng native fail | Test chưa chạy native hoặc thiếu metadata | Thêm native regression test |
| Hint quá rộng | Đăng ký toàn bộ type/package không cần | Thu hẹp type và member categories |

## 16. Bài tập mở rộng

Thực hiện các bài tập sau trên project:

1. Thêm formatter thứ hai và chỉ đăng ký constructor của implementation đó.
2. Thử đổi constructor thành private; xác minh access category cần thiết và cân nhắc thiết kế lại.
3. Chuyển tên class thành key registry và so sánh native metadata/build size.
4. Thêm một method được gọi qua reflection, tái hiện lỗi và chỉ đăng ký method đó.
5. Thêm resource template được chọn theo tên runtime và đăng ký resource pattern hẹp.
6. Chạy tracing agent với test scenarios rồi review metadata được sinh.
7. Xóa hint vừa thêm, chạy lại native test để xác nhận test thực sự phát hiện regression.
8. Đưa native smoke test vào CI và lưu log khi thất bại.

Với mỗi thay đổi, lưu request/test fixture, stack trace trước sửa, diff RuntimeHints và kết quả sau sửa.

## 17. Checklist hoàn thành thực hành

- Có một class được tạo qua reflection trong code path rõ ràng.
- JVM test xác nhận behavior mong đợi.
- Native executable được build và test để tái hiện lỗi.
- Exception đã được phân tích tới class/member cụ thể.
- Đã kiểm tra dependency/classpath và phân biệt với bean graph issue.
- RuntimeHintsRegistrar đăng ký đúng type/member tối thiểu.
- Registrar được import/đăng ký vào Spring AOT context.
- RuntimeHints predicate test pass.
- Native Image build mới hoàn tất.
- Native regression test/smoke test pass với fixture cũ.
- Không đăng ký reflection rộng hơn nhu cầu.
- Input chọn implementation được giới hạn bằng allowlist/registry.
- Log và artifact identity được lưu để tái hiện build.

## 18. Câu hỏi tự kiểm tra

1. Vì sao code dùng Class.forName có thể chạy trên JVM nhưng fail trong Native Image?
2. Reachability analysis liên quan thế nào tới reflection metadata?
3. RuntimeHintsRegistrar dùng để khai báo điều gì?
4. Vì sao đăng ký constructor không đồng nghĩa cần đăng ký mọi method và field?
5. RuntimeHintsPredicates xác minh được điều gì và không chứng minh được điều gì?
6. Làm sao phân biệt thiếu reflection hint với thiếu dependency hoặc bean?
7. Khi nào registry tĩnh phù hợp hơn reflection?
8. Vì sao tracing agent không thể bảo đảm bao phủ mọi nhánh?
9. Sau khi sửa hints, vì sao cần clean native build và test đúng executable mới?
10. Vì sao không nên nhận class name tùy ý từ request để tạo object?

**Ghi nhớ:** tái hiện lỗi bằng test cụ thể, xác định chính xác class/member được truy cập động rồi đăng ký RuntimeHints hẹp nhất đáp ứng code path. Kiểm tra registrar, build lại native executable và chạy regression test trên đúng binary trước khi chấp nhận thay đổi.
