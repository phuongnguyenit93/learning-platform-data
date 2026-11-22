# Kiểm thử cùng một bộ hợp đồng với mọi provider được hỗ trợ

## 1. Vì sao phải dùng một bộ contract tests chung?

Trong hệ Java có khả năng mở rộng ở runtime, host định nghĩa một **service contract** (interface hoặc abstract class), còn nhiều nhà cung cấp (provider) viết các implementation. Ví dụ cùng một `Slugifier` có hai implementation: một xử lý bằng vòng lặp, một dùng regular expression. Host không nên cần biết thuật toán nào đang chạy; host cần tin rằng **mọi provider được hỗ trợ đều giữ lời hứa của service API**.

Một lỗi dễ mắc là kiểm thử rất kỹ provider mặc định, còn provider do plugin khác cung cấp chỉ được thử “khởi tạo được”. Nếu provider thứ hai xử lý dữ liệu trống khác, ném exception không đúng, hoặc không an toàn khi gọi đồng thời, host có thể hoạt động tốt ở môi trường A nhưng lỗi ở môi trường B.

**Contract testing** giải quyết bằng cách biến mô tả hành vi của service thành **một bộ assertions giống nhau** và chạy nó với **tất cả provider trong danh mục hỗ trợ**, độc lập với cách provider được cài đặt. Đây là lớp kiểm thử bổ sung cho unit test riêng của từng implementation; nó không thay thế kiểm thử nội bộ, integration hay security test.

Một công thức tổ chức:

~~~text
Shared service API + phiên bản hợp đồng
                |
                v
       Shared Contract Suite
       - input hợp lệ / kết quả
       - input không hợp lệ / lỗi
       - invariants / repeatability
       - concurrency nếu được hứa
       - lifecycle/resource semantics
                |
        +-------+-------+
        |       |       |
    Provider A  B       C ... (discovered/catalogued)
        |       |       |
       PASS    PASS    FAIL → không hỗ trợ deploy phiên bản C này
~~~

**Mục tiêu bài:** thiết kế hợp đồng có thể kiểm thử, chạy cùng một suite cho mọi provider, ngăn “test xanh” khi provider bị thiếu, chuẩn hóa fixture/lifecycle, phân biệt test áp dụng cho mọi provider với capability tùy chọn, và đưa kiểm thử vào CI/deployment gate.

## 2. Bắt đầu từ hợp đồng quan sát được, không từ thuật toán

Một interface chỉ nêu **chữ ký**, chưa mô tả đầy đủ hành vi:

~~~java
public interface Slugifier {
    String id();
    String slugify(String text);
}
~~~

Đoạn trên chỉ minh họa chữ ký; chưa có package hay chương trình chạy độc lập. Muốn mọi provider có thể được thay thế cho nhau, tài liệu API cần xác định **preconditions, postconditions, lỗi, state và concurrency**.

Ví dụ ta công bố hợp đồng `Slugifier` như sau:

| Khía cạnh | Hợp đồng bắt buộc |
| --- | --- |
| Input hợp lệ | Chuỗi gồm **ASCII letters** A–Z/a–z, digits 0–9 và các separator ASCII: dấu cách, `_`, `-` |
| Đầu ra | Chỉ còn ASCII lowercase letters/digits, nối các cụm bằng một dấu `-` |
| Chuẩn hóa | Gộp nhiều separator liền nhau; bỏ separator ở đầu/cuối |
| Input `null` | Ném `NullPointerException` |
| Input rỗng hoặc chỉ toàn separator | Ném `IllegalArgumentException` |
| Ký tự ngoài miền cho phép, kể cả Unicode ngoài ASCII hoặc dấu câu | Ném `IllegalArgumentException` |
| Repeatability | Cùng input và cùng trạng thái hợp lệ phải cho cùng kết quả |
| Thread safety | Các lời gọi `slugify` đồng thời trên **một instance** phải an toàn; implementation mẫu là stateless |
| `id()` | Trả về ID không rỗng, ổn định trong vòng đời instance, duy nhất giữa các provider trong catalog đang kiểm thử |

Đây là **hợp đồng của ví dụ**; ứng dụng thật có thể chọn quy tắc Unicode khác. Không tự đánh giá provider sai chỉ vì nó khác sở thích của người viết test: chuẩn hành vi phải đến từ tài liệu/chính sách API đã thống nhất.

### 2.1. Contract test khác implementation test

| Kiểu kiểm thử | Điều khẳng định | Phạm vi |
| --- | --- | --- |
| Contract | `slugify("Hello WORLD")` trả `"hello-world"` với **mọi** implementation | Mọi provider được hỗ trợ |
| Implementation unit | Hàm regex riêng dùng đúng pattern hoặc loop xử lý đúng nhánh nội bộ | Chỉ provider tương ứng |
| Discovery/packaging | Provider được tìm qua SPI/module layer, metadata và dependency đúng | Một artifact hoặc runtime catalog |
| Integration | Provider hoạt động với DB/network/config thực hoặc fake tương ứng | Môi trường host cụ thể |
| Compatibility | Provider build với API version X chạy trong host hỗ trợ X | Cặp host–provider versions |
| Performance/security | SLO, tài nguyên, trust boundary, input không đáng tin | Theo chính sách hệ thống |

**Đừng đưa chi tiết thuật toán** (dùng vòng lặp hay regex, cấu trúc private field, class name nội bộ) vào suite dùng chung. Chỉ assert những gì caller có quyền kỳ vọng từ contract.

### 2.2. Contract cần có khả năng đo được

Một câu chung như “provider xử lý nhanh và đúng” khó biến thành test ổn định. Thay bằng:
- ví dụ input/output chuẩn và edge cases;
- exception class/cause khi input không hợp lệ;
- invariants, ví dụ output không chứa separator trùng và có thể đưa qua bộ validate;
- semantics về trạng thái, idempotence/determinism khi đã cam kết;
- concurrency guarantee nếu thực sự là một phần API;
- resource/close contract khi service có lifecycle.

Chỉ thêm timeout hoặc throughput vào common contract khi có ngân sách và môi trường đo cụ thể. Benchmark trên CI không ổn định có thể tạo false failures; performance thường cần tier riêng.

## 3. Danh mục provider: không được “test xanh” khi không tìm thấy ai

Một anti-pattern:

~~~java
// Minh họa code sai về coverage:
ServiceLoader.load(Slugifier.class).forEach(provider -> {
    // verify(provider)
});
// Nếu không tìm thấy provider nào, không có assertion nào chạy mà job vẫn xanh.
~~~

Một suite đúng phải chứng minh:
1. **Có provider** được tìm thấy.
2. **Tập provider tìm thấy đúng với tập hỗ trợ mong đợi**, hoặc tuân thủ policy rõ ràng về required/optional.
3. Mỗi provider có **ID hợp lệ, duy nhất**, đúng API/version/capability metadata.
4. **Mọi provider mong đợi đều được instantiate và chạy cùng suite**; lỗi của bất kỳ provider nào làm job fail.
5. Provider không mong đợi không được im lặng bỏ qua khi điều đó vi phạm deployment catalog.

Ví dụ build fixture hỗ trợ hai ID `loop` và `regex`; test phải fail nếu chỉ phát hiện một hoặc có thêm provider không được duyệt theo chính sách.

### 3.1. ServiceLoader có phạm vi tìm kiếm

- Với class path: provider đăng ký trong `META-INF/services/<binary-name-service>`; dùng `ServiceLoader.load(Service.class, classLoader)` và bảo đảm resource/JAR ở đúng lookup scope.
- Với named JPMS modules: consumer khai báo `uses demo.api.Slugifier;`; provider khai báo `provides demo.api.Slugifier with ...;`; có thể dùng `ServiceLoader.load(layer, Slugifier.class)`.
- `ServiceLoader.load(service)` dùng **thread context class loader (TCCL)** tại thời điểm tạo loader. Nếu test runner TCCL khác runtime plugin, có thể bỏ sót provider.
- Layer-based discovery tìm provider ở layer và parent layers; classloader-based discovery cũng có thể thấy cấu hình ở parent. Vì thế “đã tìm thấy hai provider” chưa chắc là hai provider **thuộc đúng generation** cần kiểm thử.

Nên tạo một **test catalog** từ bản kê artifact/version được deploy, rồi so sánh chính xác tập provider thực tế với catalog kỳ vọng. Đừng dùng `findFirst()`: nó chỉ chứng minh provider đầu tiên hoạt động, không cho coverage toàn bộ.

### 3.2. Metadata trước, instance sau

`ServiceLoader.stream()` trả `Stream<ServiceLoader.Provider<S>>`, nên có thể kiểm tra `Provider.type()`, module/class metadata trước khi gọi `Provider.get()`. Cần lưu ý:
- `Provider.type()` không đồng nghĩa provider instance đã được khởi tạo.
- `Provider.get()` không có cam kết luôn trả cùng object identity cho mọi lần gọi; đừng dùng nó như API singleton.
- Với named module dùng static `provider()` factory method, `Provider.type()` là return type của method, không nhất thiết là implementation holder class.
- `ServiceConfigurationError` có thể phát sinh khi tìm/instantiate provider; **phải làm test fail** chứ không bỏ qua provider lỗi.
- `ServiceLoader` không được công bố là thread-safe; không chia sẻ chính đối tượng loader để discovery song song mà không điều phối. Contract về provider concurrency khác với thread safety của `ServiceLoader`.

## 4. Lab Java 17+: hai provider, cùng một contract suite, không cần JUnit

Lab này chạy được bằng JDK 17+, không cần dependency ngoài. Hai provider hiện thực **cùng một interface** theo hai thuật toán khác nhau. `ContractSuite` khám phá toàn bộ provider bằng `ServiceLoader`, xác nhận chính xác catalog được hỗ trợ, rồi gọi **cùng một phương thức `verifyContract`** cho từng provider.

### 4.1. Cấu trúc thư mục

~~~text
provider-contract-demo/
├── src/
│   ├── demo/
│   │   ├── api/Slugifier.java
│   │   ├── providers/LoopSlugifier.java
│   │   ├── providers/RegexSlugifier.java
│   │   └── test/ContractSuite.java
│   └── META-INF/
│       └── services/
│           └── demo.api.Slugifier
└── out/                     # tạo khi biên dịch
~~~

Các đường dẫn và package names dưới đây phải khớp **từng ký tự**. File `META-INF/services/demo.api.Slugifier` là resource SPI, không phải source Java.

### 4.2. Tệp src/demo/api/Slugifier.java

~~~java
package demo.api;

/**
 * Chỉ nhận ASCII letters, digits và separators ' ', '_' hoặc '-'.
 * Null -> NullPointerException.
 * Empty, chỉ separator, ký tự ngoài miền -> IllegalArgumentException.
 * Trả slug lowercase, gộp separator thành '-', bỏ separator ở hai đầu.
 * slugify an toàn khi gọi đồng thời trên cùng instance.
 */
public interface Slugifier {
    String id();
    String slugify(String text);
}
~~~

JavaDoc mô tả **hành vi quan sát được**. Implementation không bắt buộc dùng cùng regex/vòng lặp, miễn đạt contract.

### 4.3. Provider A — vòng lặp: src/demo/providers/LoopSlugifier.java

~~~java
package demo.providers;

import demo.api.Slugifier;
import java.util.Objects;

public final class LoopSlugifier implements Slugifier {
    @Override
    public String id() {
        return "loop";
    }

    @Override
    public String slugify(String text) {
        Objects.requireNonNull(text, "text");

        StringBuilder result = new StringBuilder();
        boolean pendingSeparator = false;

        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            boolean asciiLetter = c >= 'A' && c <= 'Z'
                    || c >= 'a' && c <= 'z';
            boolean digit = c >= '0' && c <= '9';

            if (asciiLetter || digit) {
                if (pendingSeparator && result.length() > 0) {
                    result.append('-');
                }
                result.append(Character.toLowerCase(c));
                pendingSeparator = false;
            } else if (c == ' ' || c == '_' || c == '-') {
                if (result.length() > 0) {
                    pendingSeparator = true;
                }
            } else {
                throw new IllegalArgumentException("Unsupported character");
            }
        }

        if (result.length() == 0) {
            throw new IllegalArgumentException("No letters or digits");
        }
        return result.toString();
    }
}
~~~

Implementation A có local `StringBuilder`/flag cho từng lời gọi, không giữ mutable state trong instance. Những dấu phân tách đầu/cuối bị bỏ; nhiều dấu giữa hai cụm chỉ thành một `-`.

### 4.4. Provider B — regex: src/demo/providers/RegexSlugifier.java

~~~java
package demo.providers;

import demo.api.Slugifier;
import java.util.Locale;
import java.util.Objects;

public final class RegexSlugifier implements Slugifier {
    @Override
    public String id() {
        return "regex";
    }

    @Override
    public String slugify(String text) {
        Objects.requireNonNull(text, "text");
        if (!text.matches("[A-Za-z0-9 _-]+")) {
            throw new IllegalArgumentException("Unsupported character");
        }

        String result = text
                .replaceAll("^[ _-]+|[ _-]+$", "")
                .replaceAll("[ _-]+", "-")
                .toLowerCase(Locale.ROOT);

        if (result.isEmpty()) {
            throw new IllegalArgumentException("No letters or digits");
        }
        return result;
    }
}
~~~

Implementation B dùng cách tiếp cận khác nhưng cam kết cùng kết quả và loại exception. `Locale.ROOT` ngăn output thay đổi theo locale của máy, còn miền ký tự được giới hạn ASCII nên không có giả định không rõ ràng về Unicode. Cả hai class đều public và có public no-argument constructor ngầm định, phù hợp class-path SPI.

### 4.5. Tệp SPI đăng ký hai provider

Nội dung chính xác của `src/META-INF/services/demo.api.Slugifier`:

~~~text
demo.providers.LoopSlugifier
demo.providers.RegexSlugifier
~~~

Không đặt dấu ngoặc kép hay tên JAR trong file. Resource phải được copy vào **runtime class path**. Trong sản phẩm thực tế, mỗi provider có thể được đóng gói ở một JAR riêng; lab dùng một output directory để dễ chạy và kiểm chứng.

### 4.6. Tệp src/demo/test/ContractSuite.java

~~~java
package demo.test;

import demo.api.Slugifier;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ContractSuite {
    private static void equal(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    private static void throwsType(
            Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    "wrong exception: " + actual.getClass().getName(),
                    actual);
        }
        throw new AssertionError(
                "expected exception: " + expected.getName());
    }

    // Mọi provider phải chạy chính xác CÙNG bộ luật.
    private static void verifyContract(Slugifier provider) throws Exception {
        equal("hello-world", provider.slugify(" Hello  WORLD "));
        equal("xml-parser", provider.slugify("XML_parser"));
        equal("a-b", provider.slugify("a--b"));
        equal("hello-there", provider.slugify("__HELLO--there__"));
        equal("abc123", provider.slugify("abc123"));
        equal("a-b", provider.slugify("A B"));
        equal("same-value", provider.slugify("Same_Value"));

        String once = provider.slugify("ALPHA_BETA");
        equal(once, provider.slugify("ALPHA_BETA"));
        equal(provider.id(), provider.id());

        throwsType(NullPointerException.class,
                () -> provider.slugify(null));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify(""));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("  "));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("___"));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("café"));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("hello!"));

        // Chạy song song trên CHÍNH provider instance; là yêu cầu contract.
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                tasks.add(() -> provider.slugify("  Hello__WORLD  "));
            }
            for (Future<String> result : pool.invokeAll(tasks)) {
                equal("hello-world", result.get());
            }
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Slugifier> discovered =
                ServiceLoader.load(
                        Slugifier.class, ContractSuite.class.getClassLoader())
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        if (discovered.isEmpty()) {
            throw new AssertionError("No providers discovered");
        }

        Set<String> ids = new HashSet<>();
        for (Slugifier provider : discovered) {
            String id = provider.id();
            if (id == null || id.isBlank() || !ids.add(id)) {
                throw new AssertionError("Invalid or duplicate provider id");
            }
        }

        // Danh mục hỗ trợ này độc lập với kết quả ServiceLoader.
        Set<String> expectedIds = Set.of("loop", "regex");
        equal(expectedIds, ids);

        for (Slugifier provider : discovered.stream()
                .sorted(Comparator.comparing(Slugifier::id)).toList()) {
            verifyContract(provider);
            System.out.println("PASS " + provider.id());
        }

        System.out.println("providers=" + discovered.size());
        System.out.println("ALL CONTRACTS PASSED");
    }
}
~~~

**Cơ chế của bộ test:**

1. `ServiceLoader.load(Slugifier.class, testClassLoader)` dùng một loader tường minh, tránh phụ thuộc TCCL tình cờ.
2. `stream().map(Provider::get).toList()` **buộc khám phá và instantiate tất cả providers** nhìn thấy được, chứ không chỉ `findFirst()`.
3. Nếu không có provider, ID null/trống/trùng, hoặc tập ID khác catalog `{"loop","regex"}`, test fail **trước khi** đánh dấu toàn bộ contract đạt.
4. Dùng `sorted(Comparator.comparing(Slugifier::id))` chỉ để **ổn định thứ tự hiển thị**. Không dựa vào discovery order làm thứ tự ưu tiên nghiệp vụ.
5. `verifyContract` chứa **chung một bộ** input/output, exception, repeatability và concurrent calls. Nó không rẽ nhánh “nếu regex thì test ít hơn”.
6. Provider nào không giữ contract sẽ ném `AssertionError` hoặc lỗi test, khiến process trả exit code khác zero; CI có thể chặn phát hành.
7. Pool dùng cho kiểm thử concurrency được đóng ở `finally`. Demo provider không nắm tài nguyên cần stop; nếu service API có lifecycle, fixture phải đóng từng provider theo policy.

**Không suy diễn:** chương trình chỉ kiểm tra thread safety của `slugify` theo các cuộc gọi trong test; nó không chứng minh tuyệt đối an toàn trong mọi interleaving. Unit/concurrency stress test nên có thêm workload dài hơn, repeat runs và công cụ chuyên dụng nếu đây là yêu cầu trọng yếu.

### 4.7. Biên dịch và chạy

Chạy tại thư mục `provider-contract-demo` bằng PowerShell với JDK 17+:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out src/demo/api/Slugifier.java src/demo/providers/LoopSlugifier.java src/demo/providers/RegexSlugifier.java src/demo/test/ContractSuite.java

Copy-Item -Recurse -Force src/META-INF out

java -cp out demo.test.ContractSuite
~~~

**Stdout dự kiến chính xác** khi chỉ có hai provider của demo ở class path:

~~~text
PASS loop
PASS regex
providers=2
ALL CONTRACTS PASSED
~~~

Tại sao `PASS loop` trước `PASS regex`? Vì test **sort theo ID** trước khi in; `ServiceLoader` không được coi là có discovery order ổn định trong mọi cấu hình/module.

Có thể kiểm tra thêm việc đóng gói SPI file:

~~~powershell
jar --create --file demo-all.jar -C out .
jar tf demo-all.jar
java -cp demo-all.jar demo.test.ContractSuite
~~~

Lệnh `jar tf` in nhiều file, không có stdout cố định được nêu ở đây. Hãy kiểm tra file `META-INF/services/demo.api.Slugifier` thật sự nằm trong JAR; lệnh `java` sau đó sẽ cho cùng bốn dòng PASS ở trên khi JAR chứa đúng các class và resources.

### 4.8. Thử tạo lỗi để thấy suite bắt được gì

- Bỏ `demo.providers.RegexSlugifier` khỏi file `META-INF/services/demo.api.Slugifier`, copy lại resource, chạy suite. Provider list có thể vẫn không rỗng nhưng phép so `expectedIds` sẽ fail vì thiếu `regex`. Đây là bảo vệ **không false green**.
- Sửa `RegexSlugifier` để `slugify("  ")` trả chuỗi rỗng thay vì ném `IllegalArgumentException`. Suite fail ở case lỗi; implementation test nào cũng không được phép tự bỏ case này.
- Thay `RegexSlugifier.id()` thành `"loop"`. Suite fail vì **trùng ID**.
- Thêm provider mới vào SPI nhưng không cập nhật catalog dự kiến. Suite fail, buộc chủ sở hữu review và công nhận provider mới trước khi tuyên bố được hỗ trợ.
- Cho `LoopSlugifier` giữ một mutable `StringBuilder` trong field rồi tái sử dụng không đồng bộ giữa các lời gọi. Test concurrent có khả năng phát hiện race, nhưng race không phải lúc nào cũng tái hiện; cần stress và review thiết kế để bảo đảm chắc chắn.

## 5. Chuyển sang JUnit Jupiter mà vẫn giữ chung một bộ contract

Ví dụ thuần JDK ở trên hoạt động tốt làm smoke gate. Trong dự án thật, JUnit Jupiter giúp CI có báo cáo từng provider/từng case và tích hợp build tool. Hai cách thường dùng là:
- **Parameterized tests** (`@ParameterizedTest` + `@MethodSource`): mỗi provider/fixture trở thành một invocation của cùng test.
- **Dynamic tests** (`@TestFactory` + `DynamicTest`): tạo danh sách test dựa trên provider runtime catalog.

Ví dụ **minh họa dùng JUnit Jupiter, không chạy độc lập nếu chưa thêm dependency `junit-jupiter`, test engine và các provider vào test runtime classpath**:

~~~java
import demo.api.Slugifier;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SlugifierJupiterTest {
    @TestFactory
    Stream<DynamicTest> eachProviderRunsSharedExample() {
        List<Slugifier> all = ServiceLoader.load(Slugifier.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        assertFalse(all.isEmpty(), "No providers discovered");
        return all.stream().map(provider -> DynamicTest.dynamicTest(
                provider.id() + " / normalization",
                () -> assertEquals(
                        "hello-world",
                        provider.slugify("Hello WORLD"))));
    }
}
~~~

Đây chỉ minh họa **cách sinh test theo provider**, không thay thế toàn bộ suite. Trong production, hãy đưa assertions chung vào `SlugifierContract.assertAll(provider)` hoặc, tốt hơn, sinh dynamic test **cho từng contract rule** với tên dễ tìm trên CI: `providerId/empty-input`, `providerId/concurrency`, `providerId/normalization` v.v. Vẫn cần **expected provider catalog check**, vì `assertFalse(all.isEmpty())` không phát hiện trường hợp còn một nhưng thiếu ba providers.

**Cẩn thận lifecycle của dynamic tests:** với JUnit Jupiter, callback `@BeforeEach`/`@AfterEach` áp dụng cho lần chạy **factory method**, không tự động chạy trước/sau từng dynamic test được tạo ra. Nếu mỗi test cần instance mới, transaction rollback, temp directory hoặc resource close, hãy quản lý fixture trong lambda hoặc dùng parameterized test với lifecycle tương ứng. Đừng chia sẻ một provider mutable giữa nhiều dynamic tests chạy parallel nếu contract không hứa thread safety.

### 5.1. Thiết kế fixture bằng provider factory

Với service có state mutable, cùng một instance cho tất cả case có thể tạo lỗi phụ thuộc thứ tự (test A sửa trạng thái rồi test B fail). Contract suite nên nhận một **factory tạo fixture hợp lệ**, ví dụ:

~~~java
// Sơ đồ API minh họa, chưa độc lập:
interface ProviderFixture<S> extends AutoCloseable {
    String id();
    S createFreshService() throws Exception;
    void resetExternalState() throws Exception;
    @Override void close() throws Exception;
}
~~~

Mỗi invocation:
1. tạo fixture/provider theo lifecycle đã định;
2. chuẩn bị fake/stub/external test resource;
3. chạy assertion dùng chung;
4. dọn resource bằng `finally`/`AutoCloseable` dù test pass/fail.

**Không giả định `ServiceLoader.Provider.get()` luôn trả instance mới.** API cho phép các cơ chế provider khác nhau, đặc biệt khi module dùng factory method; nếu cần fresh service per case, contract/fixture factory phải đảm bảo điều đó theo cách rõ ràng.

## 6. Thiết kế bộ hợp đồng theo nhóm quy tắc

Một suite tốt không chỉ có vài “happy path” examples. Tối thiểu nên phân nhóm:

| Nhóm | Nội dung assert | Ví dụ cho Slugifier |
| --- | --- | --- |
| Khám phá | Provider tồn tại, đúng danh mục, đúng loader/layer/API | `loop`, `regex` được tìm; không trùng ID |
| Chuẩn hóa hợp lệ | Đúng output trên tập mẫu chuẩn | `"Hello WORLD" → "hello-world"` |
| Biên/empty | Chuỗi trống, chỉ separator, có separator đầu/cuối | `"___"` bị từ chối; `"__A__" → "a"` |
| Miền ký tự | ASCII vs Unicode/punctuation | `"café"` và `"hello!"` ném lỗi |
| Exception contract | Lỗi đúng kiểu, không phát sinh side effect | `null → NullPointerException` |
| Invariant | Output lowercase, không có separator trùng | Output phù hợp `[a-z0-9]+(-[a-z0-9]+)*` |
| Repeatability | Cùng input → cùng output | Lặp nhiều lần trên cùng instance |
| Concurrency | Nhiều thread cùng gọi khi API hứa thread-safe | Các concurrent calls cho cùng kết quả |
| Lifecycle | `start`, `close`, idempotence/ownership theo API | Chỉ nếu service định nghĩa hooks |
| Compatibility | Provider triển khai đúng API version và capabilities | Catalog/API compatibility matrix |

**Đừng lạm dụng exact output** với contract cố tình cho phép nhiều đáp án. Ví dụ một service tìm kiếm có thể không hứa thứ tự kết quả; khi ấy assert **tập kết quả/invariant** thay vì ép một thứ tự. Tương tự, test exception class phải phản ánh hợp đồng: nếu API chỉ hứa subtype `RuntimeException`, không tự siết thành một class cụ thể.

### 6.1. Contract invariants và property-based testing

Với slugifier có thể viết invariant:

~~~text
valid input → slug không rỗng
slug matches "[a-z0-9]+(-[a-z0-9]+)*"
slug không bắt đầu/kết thúc bằng '-'
slug không chứa "--"
same input → same output
invalid input → documented exception
~~~

Có thể tạo input ngẫu nhiên **có seed cố định** để kiểm tra trên tất cả provider, và khi fail log seed cùng input để tái hiện. Chọn generator đúng miền đầu vào; tránh một test fuzz chỉ sinh dữ liệu quá dễ. Nếu sinh Unicode/invalid input, phải phân tách expected behavior theo contract.

Không dùng một provider cụ thể làm **oracle tuyệt đối** nếu cả hai có thể sai cùng một cách. Expected results nên dựa trên chuẩn API, reference implementation được review hoặc một specification-independent oracle.

### 6.2. Metamorphic tests

Khi khó biết output chính xác với mọi input, có thể kiểm tra quan hệ giữa các lần gọi. Ví dụ cho Slugifier:
- với một input hợp lệ, thêm separator ở đầu/cuối không đổi slug;
- thay ASCII uppercase thành lowercase không đổi slug;
- thay một chuỗi nhiều separator bằng một separator duy nhất không đổi slug.

Đây là các **tính chất chỉ đúng vì hợp đồng đã công bố chúng**; không tự áp dụng cho service khác như mã hóa/băm/chữ ký số nếu chưa xác định toán học tương ứng.

## 7. Contract baseline và tính năng tùy chọn

Trong hệ plugin thực tế, không phải mọi provider đều có cùng capabilities. Ví dụ một `StorageProvider` có contract tối thiểu `put/get/delete` nhưng một số plugin hỗ trợ transaction, streaming hoặc server-side encryption.

Nên chia:
- **Core contract:** mọi provider được tuyên bố hỗ trợ service đều phải pass; không có `assumeTrue(provider.supports...)` để âm thầm bỏ core cases.
- **Capability contracts:** chỉ provider **tự khai báo và được catalog xác nhận** hỗ trợ capability X mới chạy test X. Nếu khai báo `supportsTransactions=true` mà test transaction fail, phải fail job.
- **Environment constraints:** kiểm thử phụ thuộc external service (cloud credentials, container runtime, hardware) nằm ở tier riêng, nhưng cần có release gate thích hợp. Một provider chưa test không thể tự động được coi là “supported”.

Một cách biểu diễn catalog minh họa:

~~~text
provider loop:
  apiVersion: 1
  required: true
  capabilities: [ascii-slug, thread-safe]
provider regex:
  apiVersion: 1
  required: true
  capabilities: [ascii-slug, thread-safe]
~~~

Đây là **metadata minh họa**, không phải cú pháp tiêu chuẩn của `ServiceLoader`. `ServiceLoader` không tự cung cấp provider ID, semantic version hay capabilities. Host/plugin platform phải định nghĩa metadata/registry riêng, validate nó và gắn với artifact digest.

### 7.1. Không dùng skip để che thiếu provider

Một báo cáo kiểu “12 passed, 8 skipped” chưa chứng minh 20 providers đã đạt. Phải biết **8 skipped vì sao**, dựa trên capability hay vì discovery bị lỗi. Các trạng thái nên phân biệt:
- `PASS`: provider đã chạy và đạt core contract;
- `FAIL`: đã chạy nhưng vi phạm;
- `MISSING`: catalog yêu cầu nhưng không tìm thấy;
- `UNEXPECTED`: tìm thấy nhưng không nằm trong bản kê được phê duyệt;
- `NOT_APPLICABLE`: capability contract không áp dụng theo metadata được xác thực;
- `BLOCKED`: môi trường test không đủ điều kiện, không được báo thành pass.

## 8. Kiểm thử ServiceLoader và packaging riêng với business contract

Một implementation có thể tự pass `verifyContract` khi tạo bằng `new` nhưng thất bại khi được triển khai qua SPI vì sai metadata, sai public constructor, classloader visibility hoặc xung đột phiên bản. Vì vậy cần **hai lớp kiểm thử**:

1. **Direct fixture contract test:** provider factory tạo instance được rồi kiểm thử hành vi. Tập trung business semantics.
2. **Packaged discovery test:** nạp artifact phát hành **thực** trong môi trường host/layer tương đương production, verify catalog, instantiate rồi chạy lại core suite.

Với classpath SPI:
- resource tên chính xác `META-INF/services/demo.api.Slugifier`;
- mỗi dòng chứa fully-qualified provider class;
- provider class phải visible và assignable vào service API dùng chung;
- public no-arg constructor cho classpath provider thông thường;
- fat JAR/shading phải merge service files thay vì ghi đè;
- trong nhiều plugin JAR, kiểm tra cả tình huống nhiều service files được tìm.

Với JPMS:
- consumer module khai báo `uses`;
- provider module khai báo `provides ... with ...` và `requires` tới API;
- test bằng `ModuleLayer`/`Configuration` đúng với module path release;
- nếu nhiều sibling layers chứa cùng module name/version khác, không gộp những providers vào cùng catalog một cách vô ý;
- `Provider.type()` và `Provider.get()` có semantics riêng với provider factory method.

**Tuyệt đối không nuốt `ServiceConfigurationError`** rồi bỏ provider đó khỏi danh sách để suite “xanh”. Đó là lỗi discovery/deployment cần được CI phát hiện.

### 8.1. Isolation theo generation

Một provider có thể hoạt động khi chạy trong application class loader nhưng lỗi khi nạp qua plugin loader riêng vì API JAR trùng hoặc thiếu transitive dependency. Test host thực tế nên dùng **chính classloader/module-layer boundary dự kiến trong production**:
- shared API được define ở parent;
- implementation/dependency-private ở child;
- expected provider metadata được ràng buộc với generation/artifact digest;
- kiểm tra class identity, missing class, `NoSuchMethodError`, `ClassCastException`;
- tạo generation mới cho v2, không chỉ gọi `ServiceLoader.reload()` trên loader v1.

Một job có thể chạy toàn bộ core contracts **cho mỗi generation candidate trước khi publish**. Nếu tất cả pass, host mới cho request dùng version ấy; request cũ và provider cũ vẫn theo lifecycle của thế hệ trước.

## 9. Fixture sạch, lifecycle và tránh test nhiễm chéo

Trong một suite đa-provider, test không được phụ thuộc thứ tự provider A rồi B, hoặc thời điểm một provider cũ để lại state.

### 9.1. Những biến gây nhiễm

- mutable static singleton dùng chung trong class loader;
- provider cache, transaction hoặc database table không reset;
- file/resource temporary path bị chia sẻ;
- TCCL không restore trên thread pool;
- listener/logging registry chưa unregister;
- timing/randomness/network service không ổn định;
- stateful provider instance được reuse giữa test;
- thread/executor do provider tạo không được shutdown.

Đối với service stateful, hãy tạo **namespace test riêng mỗi provider** (tenant/database schema/tmp directory/prefix), reset state theo contract và dọn bằng `try/finally`. Nếu chạy provider A và B song song, không dùng cùng database key mà không cách ly.

### 9.2. Test lifecycle của AutoCloseable

Nếu contract có `close()`, phải định nghĩa:
- gọi khi nào và ai sở hữu;
- có được gọi nhiều lần không;
- operation sau close ném gì;
- có chờ in-flight operations không;
- thread/resource còn tồn tại sau close có được phép không.

Chỉ test **điều đã cam kết**; đừng giả định mọi provider có `AutoCloseable` giống nhau. Với plugin có loader riêng, sau khi hoàn thành fixture: stop service, đóng resources, restore TCCL, đóng `URLClassLoader` khi an toàn, bỏ strong refs và kiểm tra leak bằng test tier riêng. `URLClassLoader.close()` không ép class unload ngay lập tức.

### 9.3. Test exception và cancellation

Không chỉ assert kết quả thành công. Kiểm tra input xấu hoặc dependency fail có:
- exception type/status theo contract;
- dữ liệu không bị ghi một phần ngoài policy;
- resource/transaction được dọn;
- retry/idempotence đúng nếu API hứa;
- timeout/cancellation xử lý thống nhất.

Với provider gọi network, dùng fake HTTP server/test database và fault injection để chủ động tạo timeout, 5xx, partial result hoặc connection reset. Đừng chạy lỗi mạng thật ngẫu nhiên làm suite chập chờn.

## 10. Cross-provider comparison: có ích nhưng không được dùng làm chuẩn duy nhất

Khi output của các provider là hoàn toàn tương đương theo contract, **differential testing** có thể gửi cùng input tới A/B/C rồi so kết quả:

~~~text
Input vector X
  ├── provider A → output A
  ├── provider B → output B
  └── provider C → output C

Nếu contract hứa kết quả canonical giống nhau:
  assert(output A == output B == output C)
~~~

Nó có thể phát hiện một provider lệch khi test vectors chưa bao hết. Nhưng nếu cả ba sai giống nhau, phép so vẫn pass. Vì thế giữ **specification-based tests** (known expected outputs/invariants) làm nguồn tin cậy.

Nếu contract chỉ cho phép **tương đương về ý nghĩa**, cần canonicalize theo đúng đặc tả trước khi so:
- `Set` equality thay vì array order;
- numeric tolerance chỉ khi API có error bound;
- normalized timestamp/timezone theo contract;
- không so internal IDs, logging hoặc nondeterministic metadata nếu API không hứa chúng ổn định.

**Không so performance giữa providers bằng yêu cầu output giống nhau**; throughput/latency là tier khác với SLO/hardware test policy riêng.

## 11. Chạy cùng một suite qua ma trận phiên bản và môi trường

Một provider “hỗ trợ” không chỉ là source code; cần xác định artifact và compatibility matrix.

| Chiều test | Ví dụ | Mục đích |
| --- | --- | --- |
| Provider ID/artifact digest | loop v1, regex v1, provider ngoài | Bao phủ toàn bộ bản hỗ trợ |
| Service API version | API 1.x/2.x | Binary/semantic compatibility |
| Host version | host current và bản còn hỗ trợ | Tránh regression với host cũ |
| JDK target/runtime | compile `--release 17`; chạy các JDK được hỗ trợ | Bytecode, module, runtime behavior |
| ClassLoader scope | application, per-plugin loader | Phát hiện API/private dependency collision |
| JPMS layer | boot/custom/sibling layers | Phát hiện `uses/provides/requires` sai |
| Config/capability profile | baseline, optional modes | Không bỏ qua contract optional đã khai báo |
| OS/locale/charset/timezone | các môi trường quan trọng | Phát hiện phụ thuộc môi trường ngầm |
| Concurrency/workload | single, multithread, repeated | State, race, resource lifecycle |
| Artifact packaging | exploded classes, JAR, shaded JAR | SPI metadata và dependency completeness |

Không nhất thiết chạy **mọi tổ hợp tích Descartes** trên mỗi commit nếu chi phí quá cao. Có thể chia CI tiers:
- PR: nhanh, core contract suite trên mỗi provider artifact đang thay.
- Merge/release: full supported-provider catalog và packaged discovery.
- Nightly: multi-JDK/OS, concurrency/stress, compatibility matrix rộng.
- Pre-deploy/canary: candidate generation trong host tương đương production, health + core contract subset đủ mạnh; failure dừng rollout.

Quan trọng: dù chia tier, **không được công bố một provider là được hỗ trợ** nếu artifact tương ứng chưa vượt qua release gate đã định.

## 12. CI/CD: điều kiện để kết quả có giá trị

Một pipeline phù hợp:

~~~text
Build host API and provider artifacts
           |
Resolve exact supported-provider catalog
           |
Package SPI/module metadata and dependencies
           |
Discover providers in intended loader/layer scope
           |
Assert expected IDs, versions, counts, uniqueness
           |
Run shared core contract suite for EACH provider
           |
Run capability tests for declared capabilities
           |
Run lifecycle/isolation/integration compatibility tests
           |
Aggregate result by provider ID + artifact digest
           |
All mandatory gates PASS?
   ├── No → block release, attach per-provider failures
   └── Yes → mark candidate READY; allow deploy/canary
~~~

### 12.1. Báo cáo theo provider, không chỉ tổng số test

Nên có report dạng:

~~~text
service=demo.api.Slugifier contractVersion=1
expectedProviders=[loop, regex]
discoveredProviders=[loop, regex]
loop:  core=PASS  discovery=PASS  concurrency=PASS
regex: core=PASS  discovery=PASS  concurrency=PASS
missing=[] unexpected=[] duplicateIds=[]
releaseGate=PASS
~~~

Đây là **mẫu báo cáo thiết kế**, không phải stdout của chương trình demo; chương trình mẫu chỉ in bốn dòng `PASS`/`providers`/`ALL CONTRACTS PASSED`. Nếu một provider fail, CI nên in **provider ID, contract rule, test input, expected vs actual, exception cause, artifact digest**, không chỉ “ServiceLoader error”.

### 12.2. Tiêu chí fail rõ ràng

Release gate phải fail khi:
- expected provider thiếu, duplicate ID, sai API version;
- unexpected provider làm vi phạm catalog/trust policy;
- SPI/resource/module descriptor không load được;
- provider vi phạm core rule hoặc khai báo capability mà không pass capability contract;
- fixture/resource cleanup fail theo release policy;
- test bị skipped/blocked không có chứng nhận cho phép;
- compatibility test bắt buộc hoặc JDK platform test fail.

Một test suite “không chạy được vì môi trường thiếu credentials” phải được ghi **BLOCKED**, không được tự xem là pass. Có thể dùng mocks cho PR và test integration có credentials trong môi trường CI an toàn.

## 13. Những lỗi phổ biến và cách khắc phục

### 13.1. Chỉ kiểm `findFirst()`

Provider đầu tiên pass không nói gì về những provider còn lại. **Duyệt toàn bộ catalog**, buộc instantiate và chạy cùng suite. Validate tập IDs kỳ vọng, không chỉ đếm số.

### 13.2. Kiểm thử bằng `new MyDefaultProvider()` nhưng không test packaging

Provider source code đúng nhưng plugin JAR có thể thiếu `META-INF/services` hoặc `provides`. Dùng cả direct fixture test **và** packaged ServiceLoader test với artifact thực.

### 13.3. Hardcode nhánh theo class implementation

~~~java
// Anti-pattern minh họa:
if (provider instanceof SomeConcreteProvider) {
    // Chỉ provider này mới chạy đầy đủ case.
}
~~~

Hãy dùng interface/capability hợp đồng; core suite áp dụng cho mọi provider. Một test không thể “chung” nếu có nhánh bỏ các quy tắc bắt buộc của provider ít được dùng.

### 13.4. Bỏ qua provider lỗi bằng catch-all

~~~java
// Anti-pattern minh họa:
try {
    // ServiceLoader ... instantiate
} catch (Throwable ignored) {
    // tiếp tục với những provider còn lại, job vẫn thành công
}
~~~

Đây là cách **che lỗi discovery**. Với release test, fail và ghi cause. Trong production host có thể có policy cô lập provider lỗi để service vẫn chạy, nhưng kết quả test phải phản ánh provider ấy **không đạt hỗ trợ**.

### 13.5. Test output quá cụ thể hoặc không đủ cụ thể

Đối với API không hứa thứ tự, assert list exact order là test sai. Ngược lại, nếu contract yêu cầu normalization chính xác, chỉ assert output “không null” là quá yếu. Mức assertion phải bám đúng đặc tả quan sát được.

### 13.6. Dùng shared state khiến test phụ thuộc thứ tự

Một provider pass khi chạy riêng nhưng fail sau provider khác có thể do database/static cache/timer/TCCL. Tạo fixture/namespace riêng, reset state và dọn theo lifecycle; khi CI chạy parallel, kiểm soát cả instance và external state.

### 13.7. Cho rằng concurrency pass một lần là chứng minh thread-safe

Race có thể không tái hiện. Dùng stress/repeat/specialized concurrent tests nếu contract thread-safe quan trọng, đồng thời review khả năng chia sẻ mutable state. Không tự thêm yêu cầu thread-safe nếu API thực sự chỉ hứa single-threaded use.

### 13.8. Dùng thứ tự discovery để xác định provider quan trọng

Thứ tự provider phụ thuộc cách lookup module/classpath resources. Test và host nên dùng provider ID/priority metadata rõ ràng; sort ID cho báo cáo deterministic, không ép thứ tự file SPI thành business priority.

### 13.9. Trộn API classes giữa các loader

Một implementation và host có thể chứa hai bản service interface cùng binary name nhưng khác defining loader, gây `ClassCastException` hoặc `ServiceConfigurationError`. Đặt shared API ở parent/layer chung, kiểm tra artifact không nhúng bản sao ngoài chủ ý.

### 13.10. Quên test version mới trước khi chuyển traffic

Candidate plugin v2 có thể load thành công nhưng vi phạm một edge case của core contract. Chạy suite với candidate **loader/layer generation thật** trước publish, dùng health/canary bổ sung và giữ rollback policy. `ServiceLoader.reload()` không thay thế kiểm thử hoặc tạo classloader generation mới.

## 14. Checklist triển khai contract suite dùng chung

1. **Định nghĩa contract** độc lập implementation, kèm input domain, output semantics, exception, state, concurrency và lifecycle.
2. **Version hóa contract** và quy tắc compatibility với host/provider.
3. **Duy trì supported-provider catalog** có ID, artifact digest, version, capabilities, loader/layer scope.
4. **Không cho false green:** fail khi catalog rỗng/thiếu/ngoài dự kiến/trùng ID; đừng chỉ thử provider đầu tiên.
5. **Dùng cùng assertion set** cho mọi provider, không có nhánh bypass core rules.
6. **Tạo fixture sạch** cho provider stateful; reset external state và dọn resource kể cả khi assertion fail.
7. **Chạy packaged discovery** qua SPI/module layer bên cạnh unit tests trực tiếp.
8. **Tách capability contracts** dựa trên metadata được xác thực; skipped ≠ passed.
9. **Kiểm thử non-happy paths**, property-based/invariants, concurrency và resource lifecycle đúng theo API.
10. **Báo cáo theo provider/rule** để biết chính xác implementation nào vi phạm.
11. **Gắn vào release gate** của CI và candidate generation trước triển khai.
12. **Lặp lại theo compatibility matrix** JDK/API/host/config/artifact cho những môi trường được công bố hỗ trợ.

**Kết luận:** một plugin platform đáng tin không chỉ có interface chung mà còn có **bộ bằng chứng hành vi chung**. Mỗi provider được tuyên bố hỗ trợ phải được tìm thấy trong đúng phạm vi loader/layer, được định danh rõ và chạy **cùng contract assertions**. Sự khác biệt thuật toán là quyền của provider; sự tương đương về kết quả, lỗi và lifecycle theo đặc tả là nghĩa vụ để host có thể thay thế provider một cách an toàn.

## 15. Tài liệu tham khảo

- Java SE 17 — `ServiceLoader`, `ServiceLoader.Provider`, `iterator()`, `stream()` và lỗi discovery: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `ModuleLayer` và provider discovery trong named modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 — `ClassLoader` và class identity/delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JUnit 5 User Guide — Dynamic Tests (`@TestFactory`) và Parameterized Tests: https://docs.junit.org/5.13.1/user-guide/index.html
- Java SE 17 — `ExecutorService` và `Future` trong concurrency test: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
