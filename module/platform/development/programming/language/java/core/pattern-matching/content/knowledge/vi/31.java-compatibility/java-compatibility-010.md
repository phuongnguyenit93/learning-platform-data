# Chiến lược hỗ trợ nhiều JDK trong Java Pattern Matching

## 1. Bài toán tương thích Java và mục tiêu kiến trúc

Một thư viện Java có thể được dùng bởi khách hàng còn chạy **JDK 17**, trong khi các dịch vụ nội bộ đã chuyển sang **JDK 21** và muốn dùng record patterns cùng pattern matching cho `switch`. Nếu nâng compiler mà không thiết kế rõ ràng, nhóm phát triển có thể vô tình đưa bytecode mới, API mới hoặc cú pháp chỉ hợp lệ ở Java 21 vào artifact được tuyên bố hỗ trợ Java 17.

Bài toán **hỗ trợ nhiều JDK** không đơn thuần là “code biên dịch được ở máy lập trình viên”. Một bản phát hành tương thích phải xét:

- **Source compatibility:** Cú pháp/tính năng ngôn ngữ có hợp lệ với source level đã cam kết?
- **Binary compatibility:** File `.class` và dependency có thể được runtime mục tiêu nạp?
- **API compatibility:** Mã có gọi Java SE APIs hoặc thư viện chỉ xuất hiện ở bản Java mới?
- **Runtime compatibility:** Ứng dụng có thực sự khởi động, chạy đúng hành vi và tích hợp đúng trên mỗi JVM được hỗ trợ?
- **Behavior parity:** Nếu cung cấp hai implementation theo JDK, chúng có thực thi cùng một contract nghiệp vụ?

Ví dụ xuyên suốt có ba loại sự kiện `Login`, `Logout`, `Failure`. Bản Java 17 sẽ dùng `sealed interface`, `record` và type patterns với `instanceof`; bản Java 21 biểu đạt cùng logic bằng record patterns, `switch` expression và guard `when`. Hai chương trình có thể chạy độc lập và xuất cùng tám dòng kết quả.

**Mục tiêu:** Biết chọn baseline JDK, dùng `javac --release`, tổ chức module/source sets, hiểu multi-release JAR, xây ma trận CI và xử lý các lỗi phiên bản thường gặp. Ví dụ dùng **JDK 17 và JDK 21** vì đây là hai mức tính năng pattern matching khác nhau, không phải quy tắc mọi sản phẩm chỉ nên hỗ trợ hai phiên bản đó.

## 2. Ma trận tính năng: Java 17 làm được gì, Java 21 bổ sung gì?

| Tính năng | Bản Java chính thức | Source baseline Java 17 |
| --- | --- | --- |
| `switch` trên hằng và enum | Có từ lâu | Có |
| `switch expression` | Java 14, JEP 361 | Có, nhưng chưa có type patterns trong `case` |
| `instanceof SomeType value` | Java 16, JEP 394 | Có |
| `record` | Java 16, JEP 395 | Có |
| `sealed class` / `sealed interface` | Java 17, JEP 409 | Có |
| Record patterns `Point(int x, int y)` | Java 21, JEP 440 | **Không** |
| Pattern matching trong `switch` | Java 21, JEP 441 | **Không** |
| Guard `when` của pattern `switch` | Java 21, JEP 441 | **Không** |

Java 17 đủ để xây một domain model đóng kín với records, và dùng type patterns qua `instanceof`. Nhưng cú pháp:

```java
// Ví dụ Java 21, giả định biến event và các subtype đã có:
return switch (event) {
    case Login(String name, int attempts) when attempts >= 3 ->
        "REVIEW:" + name;
    case Login(String name, int attempts) ->
        "LOGIN:" + name;
    default -> "OTHER";
};
```

không hợp lệ khi biên dịch với `--release 17`.

**Đừng nhầm feature final với preview:** Java 17–20 từng có những phiên bản preview liên quan pattern `switch` hoặc record patterns. Syntax và quy tắc có thể thay đổi qua các preview. `when` và record patterns trong bài là **cú pháp chính thức Java 21**, không cần bật `--enable-preview`. Bật preview cũng không làm chương trình Java 21 chạy được trên JVM17.

## 3. Phân biệt JDK compiler, source, target, API và runtime

Cùng một dự án có thể sử dụng **JDK 21 để biên dịch** nhưng yêu cầu **file class phải chạy trên JVM 17**. Cần phân biệt năm trục sau.

### 3.1. Compiler JDK

Đây là công cụ `javac` thực hiện compile. Kiểm tra:

```bash
javac -version
java -version
```

Hai lệnh không nhất thiết dùng cùng bản JDK nếu `PATH` hoặc `JAVA_HOME` cấu hình lệch. Trong CI phải log cả compiler lẫn runtime của task test, không chỉ log `JAVA_HOME`.

### 3.2. Source language level

Source level xác định cú pháp được chấp nhận. Ví dụ sealed interfaces và records đều có thể biên dịch với source17, trong khi `case Login(String ...) when ...` cần Java21.

Không thể đưa Java21 source vào Java17 compiler chỉ bằng cách đổi tên file, thêm cast hoặc chuyển sang thư mục `java21` mà vẫn dùng compiler17.

### 3.3. Bytecode/class-file target

JVM phải hiểu phiên bản class-file được biên dịch:

| Java target | Class-file major | Runtime tối thiểu tương ứng |
| --- | --- | --- |
| Java 17 | **61** | Java 17 |
| Java 21 | **65** | Java 21 |

JVM17 không đọc được một class-file major65 bình thường. Lỗi thường thấy là `UnsupportedClassVersionError`. Ngay cả mã không dùng Java21 APIs vẫn gặp lỗi nếu đã compile với target21.

Kiểm tra class sau biên dịch bằng:

```bash
javap -verbose CompatibilityBaselineDemo
```

Tìm dòng `major version`. Cẩn thận classpath và thư mục output để tránh đọc nhầm file cũ.

### 3.4. Java SE API level

Một source dùng cú pháp Java17 có thể vô tình gọi một API chỉ có trên Java21 nếu biên dịch trên JDK21 mà không giới hạn thư viện chuẩn. Nó có thể compile nhưng gặp `NoSuchMethodError` ở runtime17.

**Giải pháp mặc định:** `javac --release 17` thay vì chỉ ghép `-source 17 -target 17`. `--release` phối hợp source language level, bytecode version và API Java SE phù hợp với release được chỉ định.

Tuy vậy, `--release` **không** kiểm tra thay bạn tất cả dependency bên ngoài JDK, native libraries và class được nạp động.

### 3.5. Runtime JVM và dependency

Đây là JVM thật khi ứng dụng hoạt động. Tương thích có thể bị phá bởi:
- JAR phụ thuộc có class-file version quá mới.
- Method của dependency thay đổi giữa lúc compile và lúc chạy.
- Reflection hoặc ServiceLoader nạp class implementation chỉ có trên Java21.
- Thay đổi module boundary, JVM flags, TLS/security provider hoặc native integration.
- Artifact được build phù hợp nhưng Docker image dùng JVM cũ.

Vì thế, **“build trên JDK21 thành công” không đủ để khẳng định chạy trên JDK17**. Phải chạy bài test trên runtime17 thực nếu sản phẩm cam kết hỗ trợ.

## 4. Chiến lược A: một source baseline Java 17

Khi đa số khách hàng phải chạy Java17 và lợi ích cú pháp Java21 chưa đủ lớn, phương án dễ bảo trì nhất là:

1. Chọn **minimum supported runtime = 17**.
2. Viết core source dùng tối đa những tính năng final đến Java17.
3. Dùng `javac --release 17` trong CI, kể cả khi compiler đang là JDK21 hay mới hơn.
4. Chạy test trên **JVM17** và một hoặc nhiều JVM mới hơn.
5. Không đưa pattern `switch` Java21 vào module baseline.

### 4.1. Chương trình Java 17 hoàn chỉnh

Tạo file **`CompatibilityBaselineDemo.java`**:

```java
public class CompatibilityBaselineDemo {
    sealed interface Event permits Login, Logout, Failure {}

    record Login(String user, int attempts) implements Event {}
    record Logout(String user) implements Event {}
    record Failure(int code) implements Event {}

    static String describe(Event event) {
        if (event == null) return "NONE";

        if (event instanceof Login login) {
            if (login.user() == null || login.user().isBlank())
                return "LOGIN_INVALID";
            if (login.attempts() >= 3)
                return "LOGIN_REVIEW:" + login.user();
            return "LOGIN:" + login.user();
        }

        if (event instanceof Logout logout)
            return "LOGOUT:" + logout.user();

        if (event instanceof Failure failure) {
            if (failure.code() >= 500)
                return "FAIL_CRITICAL:" + failure.code();
            return "FAIL:" + failure.code();
        }

        throw new IllegalStateException("Unknown event subtype");
    }

    public static void main(String[] args) {
        Event[] events = {
            new Login("Lan", 0), new Login("Lan", 3),
            new Login("", 1), new Login(null, 1),
            new Logout("Minh"), new Failure(404),
            new Failure(503), null
        };

        for (Event event : events)
            System.out.println(describe(event));
    }
}
```

Biên dịch trên JDK17 hoặc JDK mới hơn có hỗ trợ target17:

```bash
javac --release 17 CompatibilityBaselineDemo.java
java CompatibilityBaselineDemo
```

**Stdout chính xác:**

```text
LOGIN:Lan
LOGIN_REVIEW:Lan
LOGIN_INVALID
LOGIN_INVALID
LOGOUT:Minh
FAIL:404
FAIL_CRITICAL:503
NONE
```

**Giải thích:**
- `Event` là sealed interface, các subtype record được permit là những type final; đây đều là tính năng final trước hoặc tại Java17.
- `event instanceof Login login` kiểm tra type và ràng buộc biến đã có kiểu `Login`.
- `login.user()` và `login.attempts()` là record accessors; chưa dùng record deconstruction pattern.
- `if` xử lý các điều kiện nghiệp vụ tương ứng với guard `when` ở bản Java21.
- `event == null` cần xử lý rõ ràng vì `null instanceof Login` luôn false.
- Fallback `IllegalStateException` dành cho subtype không được handler xử lý. **Chuỗi `if/else` không được compiler chứng minh exhaustive**, ngay cả khi `Event` là sealed.

**Đánh đổi:** Giữ một implementation và một artifact dễ deploy, nhưng không dùng được cú pháp record patterns/switch patterns Java21 và không có compile-time exhaustiveness từ enhanced switch.

## 5. Chiến lược B: Java 17 contract và Java 21 implementation riêng

Một dự án có thể giữ domain API ở Java17 nhưng bổ sung implementation tối ưu cho độ rõ ràng bằng cú pháp Java21.

Tổ chức gợi ý:

```text
compat-api/        -- compile --release 17
    Event, Login, Logout, Failure, EventDescriber

compat-impl17/     -- compile --release 17
    Java17EventDescriber

compat-impl21/     -- compile --release 21
    Java21EventDescriber

application/       -- chọn implementation hợp lệ theo deployment
```

**Lưu ý:** Đây là sơ đồ kiến trúc. Hai demo độc lập trong bài khai báo riêng nested types để dễ biên dịch một file. Trong một sản phẩm multi-module thực tế, các domain types nên ở **một module API chung**, không copy định nghĩa `Event` vào hai JAR gây trùng tên class.

Contract có thể là một interface target17 như:

```java
// Đoạn minh họa trong compat-api, đã có Event:
interface EventDescriber {
    String describe(Event event);
}
```

Cả hai implementation thực hiện cùng contract, nhưng khác ngôn ngữ nguồn được phép dùng.

### 5.1. Chương trình Java 21 hoàn chỉnh

Tạo file **`CompatibilityPatternDemo.java`** ở **source set riêng của Java21**:

```java
public class CompatibilityPatternDemo {
    sealed interface Event permits Login, Logout, Failure {}

    record Login(String user, int attempts) implements Event {}
    record Logout(String user) implements Event {}
    record Failure(int code) implements Event {}

    static String describe(Event event) {
        return switch (event) {
            case Login(String user, int attempts)
                    when user == null || user.isBlank() ->
                "LOGIN_INVALID";

            case Login(String user, int attempts) when attempts >= 3 ->
                "LOGIN_REVIEW:" + user;

            case Login(String user, int attempts) ->
                "LOGIN:" + user;

            case Logout(String user) ->
                "LOGOUT:" + user;

            case Failure(int code) when code >= 500 ->
                "FAIL_CRITICAL:" + code;

            case Failure(int code) ->
                "FAIL:" + code;

            case null -> "NONE";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Login("Lan", 0), new Login("Lan", 3),
            new Login("", 1), new Login(null, 1),
            new Logout("Minh"), new Failure(404),
            new Failure(503), null
        };

        for (Event event : events)
            System.out.println(describe(event));
    }
}
```

Biên dịch và chạy **chỉ trên JDK 21 trở lên**:

```bash
javac --release 21 CompatibilityPatternDemo.java
java CompatibilityPatternDemo
```

**Stdout chính xác, trùng bản Java17:**

```text
LOGIN:Lan
LOGIN_REVIEW:Lan
LOGIN_INVALID
LOGIN_INVALID
LOGOUT:Minh
FAIL:404
FAIL_CRITICAL:503
NONE
```

**Các khác biệt cú pháp:**
- `case Login(String user, int attempts)` là record pattern, ràng buộc component trực tiếp.
- `when user == null || user.isBlank()` là guard; toán tử `||` giúp tránh gọi `isBlank()` trên null.
- Guard `attempts >= 3` đứng trước case `Login` không guard; đảo thứ tự sẽ bị lỗi *dominated case*.
- `case Failure(int code)` không guard và các case khác bao phủ mọi subtype của sealed `Event`. Compiler Java21 kiểm tra switch expression exhaustive; không cần `default`.
- `case null` dành cho **selector null**, còn `user == null` dành cho **record component null**. Ở vị trí component `String`, type pattern unconditional có thể ràng buộc null.

### 5.2. Vì sao hai bản tương đương?

Trong Java17, `if (event instanceof Login login)` nhận một `Login` rồi lấy component bằng accessor. Trong Java21, `case Login(String user, int attempts)` kết hợp type check và record deconstruction. Cả hai áp dụng cùng điều kiện `attempts >= 3`, `code >= 500` và quy tắc null.

Đầu ra giống nhau là bằng chứng **parity trên tám ca đã thử**, không chứng minh mọi input luôn tương đương. Ứng dụng thật cần bổ sung dữ liệu biên, validation, exception và test khi thêm subtype.

### 5.3. Không để class target21 nạp vào JVM17

Một implementation đã compile `--release 21` tạo class-file major65; JVM17 không thể nạp nó. Việc code chỉ gọi implementation Java21 sau một `if` chưa chắc đủ nếu hệ thống đã load class đó ở bước khởi tạo, reflection, scanning hoặc dependency injection.

**Thiết kế an toàn:**
- API baseline không phụ thuộc trực tiếp vào class cần Java21.
- Ở deployment runtime17, không đưa implementation21 vào codepath cần load.
- Chọn implementation bằng module packaging, cấu hình triển khai hoặc cơ chế loading có kiểm soát.
- Nếu dùng `Runtime.version().feature()` hoặc reflection để chọn, điều kiện phải áp dụng **trước khi load class21**.
- Test class loading trên JVM17 thật, không giả định classpath “có cả hai bản” là tự động an toàn.

Reflection không làm bytecode65 chạy được trên JVM17. Nếu cần **một artifact** tự chọn bản implementation theo runtime, xem multi-release JAR.

## 6. Chiến lược C: multi-release JAR (MR-JAR)

**Multi-release JAR** (JEP 238) chứa class cơ sở và những bản class thay thế nằm dưới `META-INF/versions/<number>/`. Runtime hỗ trợ MR-JAR chọn phiên bản phù hợp khi manifest đánh dấu đúng.

Cấu trúc ví dụ:

```text
compat.jar
├── example/
│   └── EventFormatter.class                 # baseline 17
└── META-INF/
    ├── MANIFEST.MF                         # Multi-Release: true
    └── versions/
        └── 21/
            └── example/
                └── EventFormatter.class     # implementation 21
```

Hai `EventFormatter.class` có **cùng binary name** và phải giữ public API tương thích. Java17 chọn bản root; Java21 có thể chọn bản version21. Điểm khác với “đóng cả class Java21 vào một JAR thường” là cơ chế bố trí phiên bản được JVM và `jar` hiểu.

### 6.1. Quy trình đóng gói minh họa

Giả sử dự án có hai nguồn **cùng class `example.EventFormatter`**, nằm tại `src/java17` và `src/java21`, với API nhất quán. Chúng là source của phương án MR-JAR, **không phải hai chương trình standalone có tên khác nhau** ở phần 4 và phần 5.

```bash
javac --release 17 -d build/java17 src/java17/example/EventFormatter.java
javac --release 21 -d build/java21 src/java21/example/EventFormatter.java

jar --create --file compat.jar --manifest MANIFEST.MF \
  -C build/java17 . --release 21 -C build/java21 .

jar --list --file compat.jar
jar --validate --file compat.jar
```

Cú pháp `\` nối dòng ở lệnh `jar` trên dùng cho Unix-like shell. Trong Windows PowerShell, viết thành **một dòng** hoặc dùng quy tắc nối dòng riêng của PowerShell.

Một manifest mẫu:

```text
Manifest-Version: 1.0
Multi-Release: true
```

Cần tạo file manifest theo đúng định dạng manifest JAR, bao gồm dấu kết thúc dòng cần thiết. `jar --validate` giúp kiểm tra consistency của public API trong MR-JAR; `jar --list` giúp xem entries đã nằm đúng versioned path. Các thao tác này **không thay thế** kiểm thử runtime17 và runtime21.

### 6.2. Khi nào chọn MR-JAR?

Phù hợp khi:
- Cần phát hành **một thư viện** cho cả runtime cũ và mới.
- Chỉ một phần nhỏ implementation cần tính năng JDK mới.
- Contract/public API gần như không đổi.
- Build system, shading, annotation processing, coverage và runtime tests có thể xử lý MR-JAR chuẩn.

Không phù hợp nếu:
- Hai implementation có API/kiến trúc quá khác nhau.
- Build/deploy chain chưa kiểm chứng cách xử lý versioned classes.
- Chỉ có một backend nội bộ đã có thể nâng toàn bộ lên Java21.
- Chi phí duy trì hai codepaths vượt quá lợi ích của cú pháp hoặc tối ưu.

**Lưu ý:** Không dùng MR-JAR chỉ để che việc dependency Java21 bắt buộc bị kéo vào classpath Java17. Dependency của base17 vẫn cần tương thích runtime17. Cần kiểm tra cả package thực tế, class loader và framework.

## 7. Chiến lược D: nâng minimum runtime lên Java21

Một phương án đơn giản hơn nhiều là ngừng hỗ trợ runtime17 sau một mốc nâng cấp được công bố. Khi mọi môi trường có thể chạy Java21+, có thể biên dịch một source set dùng đầy đủ feature final Java21.

Quá trình chuyển đổi thường đi theo thứ tự:

1. Đánh giá **runtime thực tế** của khách hàng, service, CI agents và Docker images.
2. Kiểm tra compatibility của dependency, monitoring agent, native libraries.
3. Chạy artifact baseline17 trên JVM21 trước để phân tách lỗi runtime upgrade khỏi lỗi source upgrade.
4. Nâng compiler target sang `--release 21` sau khi không còn runtime17 cần hỗ trợ.
5. Bổ sung pattern switch/record patterns có chủ đích; chạy regression và benchmark theo workload thật.
6. Công bố minimum runtime mới và kế hoạch rollback.

**Ba trạng thái khác nhau:**

| Build/runtime | Ý nghĩa |
| --- | --- |
| Compiler JDK21, `--release 17`, runtime17 | Vẫn có thể giữ baseline17 nếu deps và test đạt |
| Compiler JDK21, `--release 17`, runtime21 | Một bước kiểm tra runtime mới trước khi nâng source |
| Compiler JDK21, `--release 21`, runtime17 | **Không tương thích** |
| Compiler JDK21, `--release 21`, runtime21 | Hợp lệ về phiên bản; vẫn cần test chức năng |

Quyết định hỗ trợ/không hỗ trợ JDK nào là **hợp đồng sản phẩm**, không chỉ sở thích của người viết Java.

## 8. Cờ biên dịch: ưu tiên --release

### 8.1. Cấu hình đáng dùng

Với compiler JDK21 hoặc mới hơn:

```bash
# Source và bytecode Java17, kiểm tra API Java SE 17:
javac --release 17 CompatibilityBaselineDemo.java

# Source và bytecode Java21, cho phép record/switch patterns:
javac --release 21 CompatibilityPatternDemo.java
```

`--release` giúp tránh ba loại lỗi:
- Dùng cú pháp không có ở baseline.
- Sinh class-file cho runtime cao hơn dự kiến.
- Dùng Java SE API không thuộc release đã chọn.

### 8.2. Vì sao -source và -target riêng có thể chưa đủ?

```bash
javac -source 17 -target 17 SomeClass.java
```

Cách này đặt source và bytecode version, nhưng không tự tạo cùng một giới hạn Java SE API như `--release 17`. Nếu compile trên JDK mới, source trông hợp lệ vẫn có nguy cơ link tới API không tồn tại trên runtime cũ.

**Không kết luận** chỉ dùng `--release` là hết việc. Nó không khóa được phiên bản dependency Maven/Gradle, không kiểm tra mọi thư viện native, không tự chạy test trên JVM17 và không kiểm soát reflection.

### 8.3. Preview không phải phương án hạ cấp

Cờ `--enable-preview` dành cho preview features ở release tương ứng. Không nên dùng nó để “làm cho record patterns Java21 chạy trên Java17”.

Trong các preview JDK cũ, pattern switch từng có những thay đổi về syntax/semantics. Khi nâng lên Java21, chuyển sang feature **final** và cú pháp `when` đúng chuẩn, không giữ preview flags theo quán tính.

## 9. Maven: tách compiler target theo module

Đối với module baseline, thuộc tính thường dùng trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Với module chỉ dành Java21, đặt `maven.compiler.release` là `21` ở đúng module hoặc cấu hình `maven-compiler-plugin` riêng. Không đổi global property của cả reactor sang21 nếu vẫn muốn phát hành module baseline có class-file version61.

**Maven Toolchains** hỗ trợ chọn JDK dùng cho công đoạn build; nó không thay thế cấu hình target. Một build chạy Maven bằng JDK21 vẫn có thể cần toolchain17 để test hoặc thực hiện tác vụ đặc thù. Kiểm tra log thực tế để biết compiler và release nào đang được dùng.

### Một cấu trúc module gợi ý

```text
parent-pom
  ├── compat-api         release 17
  ├── compat-impl17      release 17
  ├── compat-impl21      release 21
  └── compatibility-tests
```

Không cho `compat-api` import class chỉ có trong `compat-impl21`; dependency nên đi từ implementation về contract, không ngược lại.

## 10. Gradle: toolchain không phải release

Trong `build.gradle.kts` của module baseline:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

**Ý nghĩa:**
- Java toolchain 21: sử dụng compiler JDK21 cho task compile.
- `options.release.set(17)`: phát hành bytecode/source/API theo Java17.

Trong module Java21 có thể đặt `options.release.set(21)`, nhưng class đó không tự dùng được ở runtime17.

**Quan trọng:** Test JVM không nhất thiết trùng target compile. Nếu `test` được chạy trên JVM21, việc test xanh **không** chứng minh runtime17 tương thích. Cần cấu hình Java launcher/test task hoặc CI matrix chạy trên JVM17 thực.

Tùy phiên bản Gradle/JDK, cần kiểm tra tính tương thích của chính build tool, plugins và dependency trước khi nâng.

## 11. Ma trận CI tối thiểu và parity tests

Một bảng phù hợp cho phạm vi runtime17/21:

| Artifact | Compile | JVM17 | JVM21 |
| --- | --- | --- | --- |
| `compat-api` + `compat-impl17` | `--release 17` | **Bắt buộc PASS** | **Bắt buộc PASS** |
| `compat-impl21` | `--release 21` | Không hỗ trợ/load | **Bắt buộc PASS** |
| MR-JAR base17 + version21 | Compile từng phần tương ứng | Test dùng base17 | Test dùng version21 |
| Java21 source nhưng ép target17 | **Không biên dịch hợp lệ** | Không có artifact | Không có artifact |

### 11.1. Tổ chức jobs

```text
compile-baseline:
    build api + impl17 với --release 17

test-java17:
    chạy artifact baseline trên JVM 17 thật

test-java21:
    chạy artifact baseline trên JVM 21 thật

compile-impl21:
    build implementation21 bằng --release 21

test-impl21:
    chạy Java21 implementation trên JVM21
    so kết quả với baseline

validate-package:
    kiểm class major version,
    manifest và MR-JAR nếu dùng,
    dependency graph và khả năng load class
```

Đây là sơ đồ CI, không phải YAML chạy sẵn của một nhà cung cấp. Với hệ thống build thực, cần chuyển thành jobs hoặc matrix theo cú pháp của GitHub Actions, GitLab, Jenkins, v.v.

### 11.2. Tám ca parity đã kiểm chứng

Hai chương trình phần 4–5 dùng cùng dữ liệu và output:

| Dữ liệu | Kết quả |
| --- | --- |
| `Login("Lan", 0)` | `LOGIN:Lan` |
| `Login("Lan", 3)` | `LOGIN_REVIEW:Lan` |
| `Login("", 1)` | `LOGIN_INVALID` |
| `Login(null, 1)` | `LOGIN_INVALID` |
| `Logout("Minh")` | `LOGOUT:Minh` |
| `Failure(404)` | `FAIL:404` |
| `Failure(503)` | `FAIL_CRITICAL:503` |
| `null` | `NONE` |

Cặp `Login("", 1)` và `Login(null, 1)` kiểm tra dữ liệu không hợp lệ trong component. `null` ở hàng cuối là **selector null**, khác với component null.

Cần mở rộng test để so ở hai phía ngưỡng, chẳng hạn `attempts=2/3` và `code=499/500`, cũng như trường hợp ngoại lệ. Một codepath thay `>= 500` thành `> 500` có thể vẫn qua các test chung chung nhưng sai ở biên500.

### 11.3. Khi sealed hierarchy được mở rộng

Nếu thêm:

```java
// Minh họa thay đổi model, không thêm vào hai chương trình
// khi chưa sửa phép xử lý tương ứng:
record Locked(String user) implements Event {}
```

phải cập nhật `permits` của `Event`. Khi đó:

- Chuỗi `if/else` Java17 có thể **vẫn biên dịch**, nhưng sẽ rơi vào `IllegalStateException` nếu chưa có logic cho `Locked`.
- `switch` Java21 đang exhaustive trên ba subtype cũ có thể **báo lỗi biên dịch** nếu thiếu `case Locked(...)` và không có fallback thích hợp.
- Test phải bổ sung case mới cho cả hai implementation và kiểm tra parity.

Exhaustiveness hữu ích ở Java21, nhưng không thay thế **test nghiệp vụ**; compiler biết tập subtype chứ không biết chuỗi output nào mới là đúng.

## 12. Phụ thuộc, reflection và nạp class

### 12.1. Dependency transitive có thể nâng baseline ngoài ý muốn

Ngay cả khi mã project đều compile với `--release 17`, một thư viện phiên bản mới có thể chứa class-file major65. Triệu chứng có thể xuất hiện ở runtime khi sử dụng một API cụ thể, không nhất thiết khi khởi động.

Cần kiểm:
- `dependency:tree`/dependency graph hoặc công cụ tương đương.
- Minimum JDK được công bố của từng dependency quan trọng.
- Artifact cuối cùng sau shading/packaging.
- Đường đi runtime thật, nhất là chức năng ít chạy.

### 12.2. Reflection không vượt được giới hạn class file

`Class.forName("example.Java21Impl")` vẫn yêu cầu runtime có khả năng nạp bytecode của class đích. JVM17 không thể “bỏ qua” version65 nhờ reflection.

Nếu cần lựa chọn implementation theo runtime, hãy làm ở boundary:
- Kiểm tra runtime trước khi nạp class mới.
- Tách classpath/modulepath theo deployment.
- Dùng MR-JAR nếu một artifact tự thay thế theo version là yêu cầu thực.
- Không tạo static reference khiến class mới bị load trong đường code baseline.

### 12.3. Khả năng chạy trên JDK mới không tuyệt đối

Một class target17 thường có thể nạp trên runtime21, nhưng ứng dụng vẫn có thể gặp thay đổi về JVM flags, module encapsulation, security provider, native integrations hay dependency. Vì vậy **forward runtime compatibility** cần được kiểm thử, không chỉ suy từ class-file version.

## 13. Troubleshooting các lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Class-file mới hơn JVM đang chạy | Kiểm major 61/65, target release, dependency và runtime |
| `switch patterns are not supported in -source 17` hoặc diagnostic tương đương | Cú pháp Java21 nằm trong module source17 | Chuyển sang `instanceof` hoặc tách source target21 |
| Diagnostic về `when`/record patterns | Compiler/source level không đúng hoặc code preview cũ | Kiểm `javac -version`, `--release`, syntax Java21 final |
| `NoSuchMethodError` | Runtime API/dependency khác với lúc compile | Khóa API qua `--release`, kiểm dependency binary versions |
| `NoClassDefFoundError` | Class cần thiết không có/không thể load | Kiểm classpath/modulepath, runtime và dependency isolation |
| `IncompatibleClassChangeError` | Binary definitions không tương thích với lúc compile | Đồng bộ module/dependency, rà API changes |
| `switch expression does not cover all possible input values` | Thêm subtype sealed nhưng thiếu case | Thêm case và test, tránh default che thiếu xử lý |
| `this case label is dominated` | Pattern rộng đứng trước pattern cụ thể | Đặt case có guard/cụ thể trước |
| MR-JAR chọn sai bản | Manifest hoặc versioned path không đúng | Kiểm layout, `jar --list`, `jar --validate` và runtime tests |
| Build pass trên JDK21, fail ở production JDK17 | Không test runtime thấp nhất | Thêm job JVM17 thật, xem artifact và dependency |

Không chỉ xem stack trace cuối cùng rồi kết luận source mới sai. Nếu `UnsupportedClassVersionError` nhắc tên class trong dependency, cần kiểm tra **dependency đó**, không chỉ mã của project.

### Anti-pattern thường gặp

- Đổi mọi module lên `--release 21` vì compiler của CI vừa được nâng.
- Chạy một test duy nhất trên JVM21 rồi công bố hỗ trợ JDK17.
- Copy Java21 source vào shared module target17 và dùng `--enable-preview` để thử “sửa”.
- Đóng class Java21 vào JAR thường rồi mong JVM17 không bao giờ nhìn thấy.
- Để API baseline phụ thuộc trực tiếp implementation21.
- Dùng `default` rộng để tránh cập nhật subtype của sealed hierarchy.
- Giả định MR-JAR tự giữ API parity mà không test.
- Bỏ qua dependency min-JDK hoặc container images.
- Dùng `-source/-target` thay vì `--release` rồi quên giới hạn API.
- Nâng minimum JDK mà không cập nhật tài liệu và kế hoạch rollout.

## 14. Quy trình ra quyết định cho dự án thật

**Bước 1 — Chốt hỗ trợ.** Ghi rõ JDK thấp nhất, các runtime/vend​or thực sự được cam kết, thời hạn hỗ trợ, khách hàng/điểm triển khai liên quan.

**Bước 2 — Kiểm kê mã.** Tìm feature Java21-only (record patterns, pattern `switch`, `when`) và APIs/dependency chỉ có ở runtime mới. Phân biệt các tính năng đã final ở Java17 với preview của những đời trước.

**Bước 3 — Chọn cấu trúc:**
- Phải chạy Java17 rộng rãi, nhu cầu cú pháp mới nhỏ → **một baseline17**.
- Chỉ vài module cần Java21 → **API17 + implementation21**.
- Phải có một artifact thư viện nhưng muốn tối ưu riêng theo JDK → cân nhắc **MR-JAR**.
- Có thể nâng toàn bộ runtime → **nâng baseline21**, giảm số codepath.

**Bước 4 — Chốt compile target.** Ghi nhận `--release` trên từng module; pin toolchains và không vô tình compile toàn bộ source target21.

**Bước 5 — Xây runtime matrix.** Dùng JVM17 thật cho baseline, JVM21 thật cho cả baseline và implementation21; thêm runtime/version khác nếu hợp đồng hỗ trợ yêu cầu.

**Bước 6 — Bổ sung parity tests.** Cùng input phải có kết quả/exception đúng contract trên hai implementation, gồm subtype mới, null và guard boundaries.

**Bước 7 — Kiểm binary/package.** Kiểm major versions, dependency graph, service loading, MR-JAR manifest/layout và runtime class selection.

**Bước 8 — Triển khai có kiểm soát.** Upgrade JVM, kiểm tra vận hành, rồi mới nâng source features nếu runtime thấp hơn không còn được cam kết. Chuẩn bị rollback và công bố minimum JDK thay đổi.

## 15. Bài tập thực hành

**Bài tập 1 — Kiểm tra class-file version.** Trên JDK21+, compile `CompatibilityBaselineDemo.java` bằng `--release 17`, dùng `javap -verbose` và quan sát major61. Chạy artifact bằng Java17 thật nếu có.

**Bài tập 2 — Từ chối source21 trên target17.** Thử `javac --release 17 CompatibilityPatternDemo.java`. Giải thích vì sao lỗi là cú pháp/feature chứ không phải thiếu import. Biên dịch lại bằng `--release 21` và kiểm major65.

**Bài tập 3 — Parity theo giá trị biên.** Thêm `Login("An", 2)`, `Login("An", 4)`, `Failure(499)` và `Failure(500)` vào cả hai chương trình. So output. Đổi một implementation từ `>=500` sang `>500` để xác nhận test biên phát hiện sai lệch.

**Bài tập 4 — Thêm subtype.** Thêm `Locked(String user)` vào `Event`. So sánh lỗi compile-time ở Java21 exhaustive switch với hành vi runtime của Java17 `if/else` nếu quên case. Sửa hai bản và mở rộng test.

**Bài tập 5 — CI matrix.** Thiết kế jobs build target17, chạy runtime17, chạy runtime21, build/test implementation21. Nêu job nào kiểm source, binary, API và runtime.

**Bài tập 6 — Thiết kế MR-JAR.** Tạo sơ đồ root class17 và versioned class21 cùng FQCN. Giải thích tại sao `Multi-Release: true` và API parity quan trọng, cũng như cách dùng `jar --validate` và runtime tests.

## 16. Tổng kết

**Chiến lược nhiều JDK là chiến lược về source, bytecode, API, dependency và runtime — không chỉ phiên bản `javac`.** Java17 đã hỗ trợ sealed hierarchy, records và type patterns trong `instanceof`; Java21 chuẩn hóa record patterns, pattern `switch` và guard `when`.

Khi cần hỗ trợ runtime17, chọn source baseline17 và dùng `--release 17` thường là phương án đơn giản nhất. Khi cần tính năng Java21, tách implementation21, dùng MR-JAR nếu thật sự cần một artifact chung, hoặc nâng minimum runtime nếu hợp đồng sản phẩm cho phép. Trong mọi trường hợp phải kiểm thử bằng JVM thấp nhất được cam kết và bảo đảm behavior parity khi tồn tại nhiều implementation.

Không có compiler flag nào thay thế được việc test **đúng artifact**, **đúng dependency** và **đúng JDK runtime**.

## Tài liệu tham khảo

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — `javac` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 — `jar` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- OpenJDK JEP 238 — Multi-Release JAR Files: https://openjdk.org/jeps/238
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
