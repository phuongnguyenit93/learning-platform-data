# Toolchain resolver và điều kiện tải JDK tự động trong Gradle

## 1. Vấn đề: vì sao khai báo Java 17 chưa chắc máy sẽ tự tải JDK 17?

Một project Java có thể yêu cầu Java 17 để biên dịch, trong khi developer đang dùng JDK 21 để khởi động Gradle và CI chỉ có JDK 17 hoặc 25. Nếu cấu hình không rõ ràng, hai máy có thể dùng compiler khác nhau, báo lỗi `invalid source release`, không nhận một API, hoặc chạy test bằng JVM khác phiên bản dự kiến.

Gradle **Java toolchains** cho phép khai báo yêu cầu cho JDK/JRE phục vụ **compiler, test, JavaExec và Javadoc**, độc lập ở mức phù hợp với JVM khởi chạy chính Gradle. Tuy nhiên:

> **Khai báo `java.toolchain.languageVersion = JavaLanguageVersion.of(17)` không tự bảo đảm JDK 17 sẽ được tải.** Gradle ưu tiên tìm installation phù hợp đã có. Chỉ khi không có bản phù hợp và **đầy đủ điều kiện auto-provisioning**, nó mới có thể gọi resolver để lấy một JDK từ nguồn tải đã cấu hình.

Bài học thuộc mục **JDK và toolchain**, tập trung vào **Toolchain Resolver**, **toolchain download repositories** và **điều kiện tải JDK tự động**, không nhầm với Maven dependency resolution. Bạn sẽ:

1. Phân biệt JVM chạy Gradle với JDK được một task chọn làm toolchain.
2. Hiểu mô hình `JavaToolchainSpec`, local auto-detection, precedence và auto-provisioning.
3. Biết cấu hình **Foojay resolver convention plugin** đúng trong `settings.gradle`.
4. Hiểu cách resolver được đăng ký, cấu hình theo `toolchainManagement.jvm.javaRepositories` và sự khác nhau giữa convention plugin với base plugin.
5. Xác định **điều kiện bắt buộc** để JDK được tải, cũng như trường hợp tuyệt đối không tải.
6. Chạy một project **Gradle Groovy DSL + Java 17** có output cụ thể, kiểm tra JDK được chọn qua `javaToolchains` và lỗi thường gặp.
7. Phân tích hành vi khi offline, bị chặn mạng, yêu cầu vendor/VM không được cung cấp, vô hiệu hóa auto-download hoặc dùng Gradle Wrapper/JVM chưa tương thích.
8. Thiết kế chính sách CI kiểm soát vendor, phiên bản, nguồn JDK, cache và bảo mật.

Các ví dụ dựa trên cơ chế của Gradle hiện đại (đặc biệt Gradle 8/9). Tên plugin Foojay trong ví dụ được cố định tại **1.0.0**, không phụ thuộc vào giá trị `latest.release`; Java cần chạy Gradle để load plugin 1.0.0 là **Java 17 trở lên**. Các build dùng Gradle cũ hơn phải đối chiếu yêu cầu tương thích trước khi copy.

## 2. Phân biệt ba đối tượng Java trước khi xem log

| Đối tượng | Do đâu quyết định? | Có bị `java.toolchain` thay đổi trực tiếp? |
| --- | --- | --- |
| **JVM chạy Gradle client/Daemon** | `JAVA_HOME`, `PATH`, `org.gradle.java.home` hoặc Daemon JVM criteria. | **Không.** Toolchain của project không tự thay JVM đang chạy Gradle. |
| **JDK/JRE để Gradle task sử dụng** | `java { toolchain { ... } }` hoặc yêu cầu riêng bằng `javaToolchains.compilerFor/launcherFor/javadocToolFor`. | **Có**, với những task/plugin có hỗ trợ toolchain. |
| **Mức ngôn ngữ/API của bytecode xuất ra** | `options.release`, hoặc một số thiết lập source/target compatibility. | **Không đồng nhất.** Compiler từ JDK 21 có thể được yêu cầu tạo bytecode/API Java 17 bằng `--release 17`. |

Ví dụ:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Đoạn trên yêu cầu toolchain Java **major 17** cho Java plugin. Nó không yêu cầu người chạy phải đặt `JAVA_HOME` về 17, không tự cấu hình source/target của mọi loại plugin tùy biến, và không nâng/hạ JVM Gradle Daemon. Có thể khởi động một phiên bản Gradle hỗ trợ bằng JDK 21 và vẫn compile/test Java 17 nếu toolchain phù hợp được chọn.

**Quan trọng:** một JDK 17 đúng major nhưng **khác vendor hoặc patch version** vẫn có thể được chọn nếu bạn chỉ giới hạn `languageVersion=17`. Toolchain specification không phải một cơ chế khóa chính xác checksum hay minor/patch release của toàn bộ JDK distribution.

### 2.1. `--release` không tải JDK

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

`options.release=17` hướng dẫn compiler kiểm tra ngôn ngữ và API Java 17; nó **không tự chọn/tải JDK 17**. Nếu Gradle đang dùng compiler của JDK quá cũ để hỗ trợ `--release 17`, compilation sẽ lỗi. Còn khi dùng JDK 21 để compile target 17, `--release` giúp hạn chế dùng API chỉ có ở Java 21.

Khi cần compiler Java 17 thực sự, cấu hình **toolchain**. Khi cần bảo đảm target API/bytecode Java 17 bất kể compiler, xem xét thêm `options.release=17`. Hai cơ chế có thể kết hợp; không dùng cái này thay cái kia.

### 2.2. `JAVA_HOME` không phải toolchain resolver

`JAVA_HOME` thường tác động lên cách script Wrapper khởi chạy Gradle, hoặc cách Gradle chọn Daemon khi chưa có override khác. Nó cũng là một đường mà Gradle auto-detection có thể xem xét khi dò các installation.

Dù vậy, nếu task yêu cầu Java 17 mà `JAVA_HOME` đang trỏ tới JDK 21, Gradle vẫn có thể chọn JDK 17 **ở nơi khác** hoặc tải một bản 17 hợp lệ. Thay `JAVA_HOME` mà không kiểm tra `java.toolchain` có thể chữa sai triệu chứng hoặc khiến Gradle bản hiện tại không khởi động được.

## 3. Toolchain specification quyết định thế nào là “phù hợp”?

Trong `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        // vendor = JvmVendorSpec.ADOPTIUM
        // implementation = JvmImplementation.J9
        // nativeImageCapable = true
    }
}
```

Các dòng comment là **các tùy chọn cần chọn có chủ đích**, không nhất thiết tương thích với nhau hoặc có distribution khả dụng trong môi trường của bạn.

| Thuộc tính | Nghĩa | Tác động lên auto-provisioning |
| --- | --- | --- |
| `languageVersion` | Major Java version: 17, 21... | Điều kiện cốt lõi. Gradle tìm bản đúng major. |
| `vendor` | Nhà cung cấp được yêu cầu, ví dụ `JvmVendorSpec.ADOPTIUM`. | Lọc installations và khả năng tải; không phải resolver nào cũng cung cấp vendor đó. |
| `implementation` | Ví dụ `JvmImplementation.J9` để chọn OpenJ9/IBM J9. | Thu hẹp choices; có thể không có archive phù hợp OS/arch/vendor. |
| `nativeImageCapable` | Yêu cầu JDK có GraalVM Native Image capability. | Chỉ chọn bản có khả năng đó; có thể không có trên nền tảng đang chạy. |

**Quy tắc hợp lệ:** theo Gradle 8+, toolchain specification chỉ hợp lệ khi **rỗng hoàn toàn**, hoặc đã có `languageVersion` rồi mới bổ sung các constraints khác. Chỉ đặt vendor/implementation mà quên major Java version sẽ là specification không hợp lệ.

Ví dụ yêu cầu **Adoptium JDK 17**:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Đây là **cấu hình thay thế cho `java.toolchain` trong lab**, không thêm cả hai block trùng nghĩa. Nếu máy có Oracle JDK 17 nhưng yêu cầu `ADOPTIUM`, bản Oracle **không thỏa điều kiện vendor**; Gradle có thể cần một bản Adoptium khác hoặc báo lỗi nếu không thể tải. Việc siết vendor chỉ nên làm khi dự án có nhu cầu thực.

### 3.1. Matching không giống version “càng mới càng tốt”

Khi yêu cầu Java 17, JDK 21 không phải bản nâng cấp thay thế hợp lệ, dù số lớn hơn. Gradle cần **major version 17**. Khi nhiều installations cùng thỏa yêu cầu, Gradle áp dụng **installation precedence** thay vì luôn chọn bản có patch lớn nhất ở bất kỳ vendor.

Theo tài liệu Gradle, trong tập JDK/JRE phù hợp Gradle ưu tiên:

1. Installation đang chạy Gradle (nếu nó phù hợp).
2. **JDK** hơn **JRE**.
3. Thứ tự ưu tiên vendor do Gradle định nghĩa.
4. Trong các trường hợp tiếp theo, version cao hơn theo các tiêu chí sắp xếp.
5. Các thông tin phụ như path được dùng để có thứ tự chọn ổn định.

Vì thế chỉ xem `java -version` từ terminal chưa đủ để khẳng định compiler mà `compileJava` dùng. Hãy dùng `./gradlew -q javaToolchains` và log task.

### 3.2. Toolchain JRE hay JDK?

Để biên dịch, task `JavaCompile` cần **javac**, thường có trong **JDK**. Task `Test` hoặc `JavaExec` chủ yếu cần **java launcher**. Gradle có thể phát hiện cả JRE/JDK, nhưng auto-provisioning được tài liệu mô tả ở dạng tải **JDK distribution**, không phải cứ gặp một JRE là thay thế được mọi nhu cầu compiler.

Trong môi trường CI nên cài sẵn hoặc cho phép tải **JDK đầy đủ** nếu các task sẽ compile Java.

## 4. Quy trình lựa chọn: local trước, resolver sau

```text
JavaCompile/Test/JavaExec yêu cầu một toolchain
                |
                v
     JavaToolchainSpec có hợp lệ?
           /           \
         Không          Có
          |             |
       BUILD FAIL        v
                 Dò JDK/JRE đã cài
                  (auto-detection,
                  paths, fromEnv,
                  Gradle User Home/jdks)
                         |
                  Có bản khớp?
                 /         \
               Có          Không
                |             |
            CHỌN LOCAL        v
                         Auto-download được bật?
                           /             \
                         Không            Có
                          |               |
                        FAIL              v
                                Có download repository
                                 & resolver được cấu hình?
                                    /             \
                                  Không            Có
                                   |               |
                                  FAIL             v
                                      Resolver có tìm được
                                      JDK hợp spec+OS/arch?
                                         /          \
                                       Không         Có
                                        |            |
                                       FAIL          v
                                         Network/TLS/permissions,
                                          download và giải nén OK?
                                              /           \
                                            Không         Có
                                             |           |
                                            FAIL         v
                                                   JDK được cài
                                                   trong Gradle User Home
                                                       |
                                                       v
                                                 Task dùng JDK
```

Một resolver không can thiệp vào các trường hợp Gradle đã có JDK phù hợp tại máy. Khi còn một bản địa phương thỏa yêu cầu, Gradle **không tự tải bản patch mới** chỉ vì repository có JDK bảo mật hơn. Auto-provisioning là **cơ chế đáp ứng nhu cầu thiếu installation**, không phải trình quản lý cập nhật JDK đang được dùng.

### 4.1. Checklist điều kiện tải JDK tự động

| Điều kiện | Nếu thiếu thì sao? |
| --- | --- |
| Có yêu cầu toolchain hợp lệ và task thực sự cần resolve công cụ. | Chỉ viết một đoạn `toolchain` nhưng không chạy task dùng JDK chưa chắc có download. |
| Không có installation local thỏa **toàn bộ spec**. | Gradle dùng JDK đã có, không tải thêm. |
| `org.gradle.java.installations.auto-download` không bị đặt `false`. | Gradle không provision JDK mới. |
| Có ít nhất một **toolchain download repository** được settings plugin cấu hình. | Gradle không có nơi hỏi URL tải JDK dù `auto-download=true`. |
| Resolver tìm được một **GA JDK release** phù hợp Java major, vendor, implementation, OS/arch. | Không có bản tương thích thì resolver trả no match; build fail. |
| Plugin/resolver tương thích Gradle và JVM đang chạy, truy cập được plugin repository. | Build có thể fail **ngay ở settings plugin resolution** trước khi lựa chọn JDK. |
| Có mạng hoặc JDK archive/endpoint được truy cập hợp lệ, TLS/credentials/proxy đúng. | Tải, giải nén hoặc xác minh installation thất bại. |
| Máy/CI có quyền ghi Gradle User Home và không chạy chế độ offline chặn fetch còn thiếu. | Không thể provision một JDK mới chưa có trong cache. |

**Default quan trọng:** tài liệu Gradle mô tả `org.gradle.java.installations.auto-download=true` là mặc định. **Nhưng default true không có nghĩa Gradle tự có nguồn tải.** Từ cơ chế resolver plugin hiện đại, phải **cấu hình download repository**, thường bằng settings plugin. Đây là chỗ nhiều người bỏ sót.

### 4.2. Không phải mọi phiên bản Java có thể tự tải

Gradle chỉ auto-provision **bản JDK GA (general availability)**, không tự tải các bản **early access** theo cơ chế này. Ngoài ra, dù Java 17/21 GA phổ biến, resolver cần tìm distribution hỗ trợ **hệ điều hành, kiến trúc CPU, vendor/implementation** và release cụ thể.

Một yêu cầu Java major chưa GA, một tổ hợp `GraalVM + J9` vô lý, hoặc vendor không được Foojay mapping cho platform đó có thể không tìm được download. Đừng kết luận plugin bị lỗi khi chính yêu cầu không có bản phân phối hợp lệ.

## 5. Resolver là gì, khác Maven repository như thế nào?

**JavaToolchainResolver** là một API Gradle dành cho **settings plugin**, dùng để ánh xạ yêu cầu toolchain (version/vendor/implementation/platform) thành một **download URI** hợp lệ. Khi không thể đáp ứng yêu cầu, resolver trả kết quả rỗng. Gradle chịu trách nhiệm các bước tải, giải nén và nhận diện installation dựa trên URI đó.

Đừng nhầm ba loại repository:

| Loại | Khai báo ở đâu? | Nó cung cấp gì? |
| --- | --- | --- |
| **Plugin repositories** | `pluginManagement { repositories { ... } }` trong `settings.gradle`. | Plugin Foojay và các Gradle plugins khác khi Gradle resolve `plugins { }`. |
| **Project dependency repositories** | `repositories { mavenCentral() }` trong `build.gradle`, hoặc `dependencyResolutionManagement` trong settings. | JAR, POM, Gradle Module Metadata và runtime/test libraries. |
| **Toolchain download repositories** | `toolchainManagement { jvm { javaRepositories { ... } } }` trong `settings.gradle`, thường do settings plugin tự cấu hình. | Resolver/endpoint tìm **JDK archive** khi cần. |

**Thêm `mavenCentral()` không tự tạo toolchain resolver.** Một JDK archive không giống Maven module `group:name:version`; pipeline tải và chính sách nguồn khác nhau. Tương tự, thêm `gradlePluginPortal()` không thay thế việc đăng ký JDK download repository.

### 5.1. Vì sao resolver chạy ở Settings?

Gradle cần biết các công cụ có thể provision cho **toàn build**, trước khi những project tasks yêu cầu toolchain. Vì vậy plugin resolver được áp dụng vào **`settings.gradle`**, không phải `build.gradle` của một subproject.

Cấu hình tự nhiên:

```text
settings.gradle
    |
    +-- plugins { toolchain resolver settings plugin }
    |
    +-- toolchainManagement.jvm.javaRepositories
             |
             v
      Resolver(s) cho toàn build
             |
      projects / tasks yêu cầu
      JavaCompiler / JavaLauncher / JavadocTool
```

Nếu một plugin được viết như `Plugin<Project>` thay vì `Plugin<Settings>`, nó không phù hợp với cơ chế đăng ký toolchain download repository này. Foojay cung cấp **settings plugin** đúng API.

## 6. Foojay Toolchains Resolver: hai cách cấu hình

Foojay là plugin do Gradle cung cấp, dùng **Foojay Disco API** để tìm JDK distribution phù hợp. Có hai plugin IDs liên quan:

- `org.gradle.toolchains.foojay-resolver-convention`: **mặc định nên dùng** cho project phổ thông. Nó vừa áp dụng resolver plugin vừa tự cấu hình repository `foojay`.
- `org.gradle.toolchains.foojay-resolver`: **base plugin**. Nó đăng ký resolver nhưng bạn phải tự khai báo `toolchainManagement.jvm.javaRepositories`.

Cả hai bản plugin **1.0.0** là phiên bản minh họa cố định, được ghi trong tài liệu Gradle và cổng plugin chính thức; bản này yêu cầu **Java 17+ để chạy plugin** và **Gradle 7.6+** theo README của plugin. Khi dùng project thực, kiểm tra tương thích với Wrapper đã pin, không thay bằng phiên bản bất kỳ chỉ vì “latest”.

### 6.1. Cách A — Foojay convention: ít cấu hình, khuyến nghị cho bài lab

**File `settings.gradle`**:

```groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}

rootProject.name = 'toolchain-resolver-lab'
```

Chỉ vậy là Foojay convention plugin đã cấu hình phần download resolver theo convention. **Không cần** thêm `toolchainManagement` bên dưới lần nữa cho Foojay mặc định.

**File `build.gradle`** sẽ khai báo yêu cầu toolchain cho Java plugin:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.ToolchainHello'
}
```

Lưu ý:

- `settings.gradle` quyết định **có resolver hay không**.
- `build.gradle` quyết định **project/task cần Java mấy**.
- Plugin `application` tích hợp `java`, tạo `compileJava` và `run`.
- Mẫu không khai báo Maven library bên ngoài, vì chỉ dùng Java chuẩn; tuy nhiên Gradle vẫn cần **lấy Foojay settings plugin** từ plugin repository nếu máy chưa có trong cache.
- Nếu máy đã có JDK 17 thỏa điều kiện, **không có download JDK**, dù resolver đang tồn tại.
- Nếu máy chỉ có JDK 21 (đủ chạy Gradle) nhưng task yêu cầu 17, Foojay resolver có thể tìm JDK 17 qua Disco API khi đáp ứng điều kiện khác.

**Lưu ý phân biệt:** việc plugin được tải từ Gradle Plugin Portal là **plugin resolution**. Việc nó tìm JDK mới qua Foojay là **toolchain provisioning**. Hai lần truy cập mạng này độc lập; build có thể hỏng ở bước đầu khi chưa kịp kiểm tra Java 17.

### 6.2. Cách B — Base Foojay resolver với khai báo repository thủ công

**Đây là phương án thay thế toàn bộ `settings.gradle` ở mục 6.1**, không dán chồng vào plugin convention:

```groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver' version '1.0.0'
}

toolchainManagement {
    jvm {
        javaRepositories {
            repository('foojay') {
                resolverClass =
                    org.gradle.toolchains.foojay.FoojayToolchainResolver
            }
        }
    }
}

rootProject.name = 'toolchain-resolver-lab'
```

`resolverClass` nối tên repository logical `foojay` với implementation mà settings plugin cung cấp. `toolchainManagement.jvm.javaRepositories` là DSL của **settings**, không phải `repositories` để tìm JAR thư viện.

Cách B hữu ích khi build cần tự sắp xếp nhiều resolvers, thêm repository riêng, credentials hoặc chính sách nguồn. Trong hầu hết project Java phổ thông, cách A đơn giản và ít lỗi hơn.

### 6.3. Thứ tự resolvers và repository naming

Khi có nhiều repositories toolchain:

```text
repository('approvedCorporateJdks') -> CorporateToolchainResolver
repository('foojay')               -> FoojayToolchainResolver
```

Đây là **sơ đồ logic**, không phải Groovy code chạy được (tên CorporateToolchainResolver chỉ là ví dụ). Gradle xét resolvers theo thứ tự cấu hình và lấy từ repository đầu tiên đáp ứng được yêu cầu.

Trong doanh nghiệp, thường nên **ưu tiên nguồn JDK đã được cho phép**, giới hạn vendor và mirror có chữ ký/checksum/chính sách riêng, rồi mới quyết định có cho phép fallback ra nguồn public không. **Không** dùng raw HTTP download URI chỉ để thử; resolver API chỉ chấp nhận các giao thức an toàn như **HTTPS**.

## 7. Lab chạy được: Java 17, Foojay resolver, command và stdout

Đây là **lab single-project có thể chạy** với Gradle Wrapper tương thích, JVM khởi chạy Gradle dùng Java 17+ và kết nối Plugin Portal; nếu chưa có JDK 17 cục bộ, còn cần Foojay API/download endpoint cho phép tải JDK.

### 7.1. Cây thư mục

```text
toolchain-resolver-lab/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/...
├── settings.gradle
├── build.gradle
├── gradle.properties        (tùy chọn)
└── src/
    └── main/
        └── java/
            └── example/
                └── ToolchainHello.java
```

Wrapper được tạo bằng `gradle wrapper` trên máy đã có Gradle phù hợp hoặc được thêm bởi quá trình tạo project; nó **không tự xuất hiện** khi bạn chỉ tạo hai file Gradle. Mọi lệnh sau chạy từ thư mục root của lab.

### 7.2. settings.gradle

```groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0'
}

rootProject.name = 'toolchain-resolver-lab'
```

Không đặt plugin này vào `build.gradle`. Đây là **settings plugin**, phải được áp dụng ở giai đoạn settings.

### 7.3. build.gradle

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.ToolchainHello'
}
```

Không cần `repositories { mavenCentral() }` cho ví dụ này vì Java source **không có external libraries**. Nếu bổ sung JUnit hoặc Commons Lang, lúc đó phải cấu hình repositories cho các dependencies đó; Maven Central vẫn **không thay thế** Foojay resolver.

### 7.4. src/main/java/example/ToolchainHello.java

```java
package example;

public final class ToolchainHello {
    private ToolchainHello() {
    }

    record Pair(int left, int right) {
        int sum() {
            return left + right;
        }
    }

    public static void main(String[] args) {
        Pair numbers = new Pair(20, 22);
        System.out.println(
                "java-feature=" + Runtime.version().feature());
        System.out.println("sum=" + numbers.sum());
    }
}
```

Code dùng **record** (đã có chính thức trong Java 16) và `Runtime.version().feature()`, đều hợp lệ trên Java 17. Nếu task `run` sử dụng toolchain Java 17 như cấu hình, stdout **do Java program in** là:

```text
java-feature=17
sum=42
```

Không khẳng định toàn bộ log Gradle chỉ có hai dòng này; Gradle có thể thêm thông tin task, daemon, thời gian. `-q` thường làm log Gradle gọn hơn nhưng không thay đổi output của ứng dụng.

### 7.5. Chạy lab trên Linux/macOS

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean run --console=plain
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat clean run --console=plain
```

**Vai trò từng lệnh:**

- `--version` xem phiên bản Gradle/JVM dùng để chạy Gradle; nó **không chứng minh** JDK nào được task `compileJava` chọn.
- `javaToolchains` là task báo cáo installations Gradle **đang nhận diện**: path, language version, vendor, architecture, `Is JDK`, nguồn phát hiện và các tùy chọn auto-detect/auto-download. Task này chủ yếu **liệt kê những gì đang có**, không cần tự tạo tình huống thiếu JDK.
- `clean run` sẽ compile và chạy chương trình. Đây mới là lệnh có thể khiến một compiler/launcher cần được chọn, và do đó có thể **kích hoạt auto-provisioning** nếu thiếu toolchain phù hợp.
- Nếu project đã có JDK 17, không có JDK download mới; đây là hành vi đúng, không phải resolver không hoạt động.

### 7.6. Kiểm tra stdout mà không suy đoán vendor/path

Kỳ vọng từ phần Java chính là:

```text
java-feature=17
sum=42
```

Ta không dự đoán dòng `Installation path: ...` vì đường JDK được chọn phụ thuộc máy, Gradle User Home, daemon JVM, vendor/OS và installations đã có. Nếu output Java hiện `java-feature=21` trong khi `run` được dự kiến chạy trên 17, hãy kiểm tra plugin khác có override `javaLauncher`, task có thật sự là `application.run` của project này không và cấu hình Gradle được áp dụng ở đúng project.

### 7.7. Kiểm tra bằng javac/java độc lập (không thay Gradle toolchain)

Nếu môi trường có JDK 17 trong `PATH`, có thể tự kiểm chứng logic Java:

```bash
javac --release 17 -d out src/main/java/example/ToolchainHello.java
java -cp out example.ToolchainHello
```

Output của chương trình như trên. Nhưng **đây không phải thử nghiệm resolver**: `javac` và `java` ở shell dùng toolchain của terminal, không gọi JavaToolchainResolver Gradle. Dùng để kiểm tra code độc lập, không dùng làm bằng chứng JDK đã được auto-provision.

## 8. Thử nghiệm có kiểm soát: máy có JDK 17 so với thiếu JDK 17

Mục này là **hai kịch bản mô tả điều kiện**, không yêu cầu xóa JDK hệ thống hay tạo rủi ro cho máy đang dùng.

### 8.1. Kịch bản A: local JDK 17 đã có

Trạng thái:

```text
Gradle Daemon: JDK 21
Toolchain requested by app: Java 17
Local installations: JDK 17 + JDK 21
Auto-download: true
Foojay resolver: configured
```

Khi `compileJava` cần compiler 17, Gradle chọn **JDK 17 đã có**, không tải một JDK 17 khác chỉ vì Foojay có patch mới. Chạy `./gradlew -q javaToolchains` để nhìn đường dẫn, còn `run` dùng launcher 17 và in `java-feature=17`.

### 8.2. Kịch bản B: thiếu local JDK 17

Trạng thái:

```text
Gradle Daemon: JDK 21
Toolchain requested by app: Java 17
Local installations: only JDK 21
Auto-download: true
Foojay resolver: configured
Network: available
Foojay returns: compatible GA JDK 17 for OS/architecture
```

Lúc task resolve `JavaCompiler`/`JavaLauncher`, Gradle có thể tải JDK 17 tương ứng, giải nén và sử dụng. Trong lần build sau, installation đã provision xuất hiện trong Gradle User Home, và nếu còn thỏa spec thì Gradle dùng lại; **không tự tải lại chỉ vì có minor security update**.

**Đừng dùng cách “xóa JDK 17 hệ thống” chỉ để mô phỏng B.** Nếu cần chứng minh provisioning trên CI, dùng container/runner thử nghiệm có image JDK 21 để chạy Gradle, clean Gradle User Home và network policy xác định; hoặc chạy trên máy ảo cách ly. Việc đổi `JAVA_HOME` không có nghĩa Gradle ngừng phát hiện JDK 17 đã cài ở các đường khác.

### 8.3. Bảng kết quả theo điều kiện

| Local match | Resolver | Auto-download | Mạng khi cần tải | Kết quả dự kiến |
| --- | --- | --- | --- | --- |
| Có | Không | true/false | Bất kỳ | Dùng local JDK, không provision mới. |
| Có | Có | true | Offline | Dùng local JDK nếu plugin/build logic cần thiết đã có trong cache. |
| Không | Không | true | Online | FAIL: không có toolchain download repository. |
| Không | Có | false | Online | FAIL: auto-provisioning bị tắt. |
| Không | Có | true | Offline, JDK chưa có | FAIL: không thể tải JDK mới. |
| Không | Có | true | Online nhưng không có bản phù hợp spec/OS | FAIL: resolver không cung cấp matching JDK. |
| Không | Có | true | Online, endpoints/proxy/TLS/permissions OK | Tải/giải nén JDK rồi dùng cho task. |

**Phần ngoài phạm vi bảng:** ngay cả khi local JDK có, nếu **plugin Foojay settings chưa được cache** và chạy offline, **settings plugin resolution** vẫn có thể thất bại trước khi Gradle dùng JDK local. Cần phân biệt hai bước truy cập mạng.

## 9. Auto-download và auto-detection là hai công tắc khác nhau

### 9.1. Tắt tự tải nhưng vẫn nhận JDK cài sẵn

Trong `gradle.properties` của root build hoặc Gradle User Home:

```properties
org.gradle.java.installations.auto-download=false
```

Hoặc trong command line để thử nghiệm:

```bash
./gradlew -Dorg.gradle.java.installations.auto-download=false compileJava
```

Hành vi:

- Gradle vẫn **dò JDK local** nếu auto-detection đang bật.
- Không có bản local phù hợp thì task báo lỗi, kể cả `settings.gradle` đã cấu hình Foojay.
- `auto-download=false` **không tắt** việc Gradle phải resolve Foojay plugin nếu settings đang áp dụng plugin.
- Thay flag có thể cần restart daemon bằng `./gradlew --stop` để môi trường toolchain detection và config được tính lại như tài liệu Gradle khuyến nghị.

Trên PowerShell, giữ tham số là một token:

```powershell
.\gradlew.bat -Dorg.gradle.java.installations.auto-download=false compileJava
```

Đây là phép thử **tạm thời**; không khuyên developer tắt auto-download toàn cục nếu nhóm đang dựa vào provisioning. Với CI cần nguồn cài đặt được kiểm soát, việc tắt và preinstall JDK có thể là chính sách phù hợp.

### 9.2. Tắt auto-detection không đồng nghĩa bật/tắt download

```properties
org.gradle.java.installations.auto-detect=false
```

Khi đặt false, Gradle không chủ động quét các vị trí JVM auto-detection tiêu chuẩn. Nhưng có thể khai báo **đường JDK tùy biến**, và cơ chế provisioning có quy định riêng. Tránh hiểu `auto-detect=false` là tương đương `auto-download=false`.

Có thể dùng:

```properties
org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME
```

Các biến môi trường `JDK17_HOME`/`JDK21_HOME` phải trỏ đến **JDK installations hợp lệ**. Đây là cách chỉ rõ nguồn candidate local mà không hardcode paths trong build script.

Hoặc:

```properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
```

Đường dẫn minh họa cho Linux. Trên Windows, dùng paths hợp lệ với cú pháp Gradle properties/escaping phù hợp. Danh sách phải chỉ **trực tiếp tới JDK home**, không phải directory cha mà Gradle sẽ tự duyệt con.

### 9.3. Thứ tự chọn installation

Tài liệu Gradle ghi rõ các installations được sắp xếp theo precedence, không đơn giản theo thứ tự khai báo trong `paths`/`fromEnv`. Các sources phát hiện thêm là **additive**. Khi local installation đáp ứng yêu cầu, nó có thể được chọn thay vì provision JDK mới; đừng thử “ép download” bằng cách chỉ thêm một path không tồn tại.

Nếu cần một distribution được tổ chức phê duyệt, hãy thiết kế runner/image JDK chuẩn hoặc bộ lọc `vendor`, và kiểm tra bằng `javaToolchains`. Gradle không có nghĩa vụ tải một distribution mới nếu installation sẵn có đã thỏa **spec mà bạn thực sự khai báo**.

## 10. Offline, plugin cache và JDK cache

Gradle dùng nhiều loại cache khác nhau. Đối với bài này cần tách ít nhất ba lớp:

1. **Gradle Wrapper distribution**: Gradle binary/version theo `gradle/wrapper/gradle-wrapper.properties`. Nếu chưa tải Gradle distribution, Wrapper có thể cần mạng ngay trước khi build bắt đầu.
2. **Settings plugin dependencies**: Foojay resolver plugin và các dependency của nó được resolution từ plugin repositories/caches. Nếu chưa cache, `--offline` có thể khiến plugin không resolve.
3. **JDK installations đã provision**: Gradle tải và giải nén dưới `<GRADLE_USER_HOME>/jdks`, sau đó chúng được auto-detection nhận diện trong các build tiếp theo.

Thông thường, Gradle User Home là `~/.gradle` trên Linux/macOS và thư mục Gradle của user trên Windows; có thể override bằng biến `GRADLE_USER_HOME`. Không hardcode một đường cụ thể trong README như thể mọi máy đều có cùng home.

**`--offline` không sinh ra JDK chưa có**; nếu local matching JDK hoặc auto-provisioned installation đã tồn tại, task vẫn có thể chạy offline khi **mọi Gradle/plugin/dependency input khác** cũng có sẵn.

### 10.1. Dừng daemon sau thay đổi toolchain

Gradle Daemon cache thông tin build và Java installations. Khi đã sửa `gradle.properties`, thay JDK paths, cài thêm JDK hoặc xóa JDK provisioned, tài liệu khuyến nghị:

```bash
./gradlew --stop
./gradlew -q javaToolchains
./gradlew compileJava --info --console=plain
```

**Không nên xóa Gradle User Home/jdks trực tiếp khi daemon đang dùng installation đó.** Nếu tổ chức cần dọn toolchain cũ, dừng daemon, xác định đúng JDK archive được quản lý trong `jdks`, xóa có kiểm soát, rồi kiểm tra lại. Đừng xóa toàn bộ Gradle User Home hoặc JDK hệ thống như một bước chẩn đoán mặc định.

### 10.2. Auto-provisioning không tự cập nhật patch versions

Sau khi tải một bản Java 17, Gradle có thể dùng bản đó trong nhiều builds. **Cơ chế này không tự cập nhật JDK đã provision sang bản patch mới** dù nhà phát hành đã ra bản sửa CVE. Đây là khác biệt lớn với kỳ vọng “để auto-download bật là JDK luôn an toàn”.

Nhóm cần chủ động quản lý JDK runtime/patch level, đặc biệt trên CI. Những cách thường dùng: chọn approved CI base image, preinstall bản vá, quản lý installation cache lifecycle, hoặc thiết kế mirror JDK riêng với quy trình xác minh/checksum/promotion rõ ràng.

## 11. Gradle Daemon JVM criteria: cùng nền tảng phát hiện, mục đích khác

Gradle hỗ trợ **Daemon JVM criteria** để kiểm soát JVM chạy Daemon, tách biệt với `java.toolchain` phục vụ tasks. File liên quan có thể là:

```text
gradle/gradle-daemon-jvm.properties
```

Nó có thể chứa tiêu chí JVM daemon và các JDK download URLs theo nền tảng được task `updateDaemonJvm` quản lý. Cơ chế này **không biến `java.toolchain` thành cài đặt JVM daemon**, cũng không có nghĩa bạn bắt buộc phải dùng hai cơ chế cùng lúc.

**Lưu ý đặc biệt:** để tạo URLs cho các OS/architecture khác nhau, `updateDaemonJvm` có thể dùng toolchain download repositories đã cấu hình; nếu không có resolver mà cần tạo URLs, task có thể báo lỗi. Nhưng URL JDK theo daemon criteria có vòng đời riêng. Khi debug, hãy hỏi rõ: **Gradle chưa khởi động được Daemon**, hay **Gradle đã chạy nhưng không tìm được compiler Java 17**?

Nếu Gradle bản đang dùng không thể khởi động với JDK trong `JAVA_HOME`, resolver **chưa thể được thực thi**. Hãy dùng JDK tương thích để khởi động Gradle trước, rồi để toolchain chọn compiler/task JDK cần thiết.

## 12. Custom toolchain resolver: trường hợp công ty có JDK registry riêng

Đối với doanh nghiệp có mirror hoặc registry JDK đã được ký/kiểm soát, một resolver tùy biến có thể thay Foojay public hoặc xếp trước nó. Cơ chế có **hai phần**:

**Phần 1: JavaToolchainResolver implementation** nhận yêu cầu `JavaToolchainRequest` với spec và nền tảng, ánh xạ tới một JDK archive đã phê duyệt, trả về `Optional<JavaToolchainDownload>`. Nếu không có bản phù hợp, trả `Optional.empty()` để cho phép resolver sau trong danh sách được xét.

Dạng API rút gọn (chỉ minh họa **contract**, chưa phải một plugin đầy đủ chạy được):

```java
public abstract class CorporateResolver
        implements JavaToolchainResolver {

    @Override
    public Optional<JavaToolchainDownload> resolve(
            JavaToolchainRequest request) {
        // Phải kiểm tra languageVersion, vendor, platform...
        // Phải map tới HTTPS archive được công ty phê duyệt.
        return Optional.empty();
    }
}
```

Để compile đoạn trên cần imports cho các API Gradle và `java.util.Optional`, và project plugin hoàn chỉnh; **không** copy nó vào `src/main/java` của lab ứng dụng. Đây là sơ đồ contract của resolver, không giả làm Java application có `main`.

**Phần 2: settings plugin** `Plugin<Settings>` đăng ký implementation qua `JavaToolchainResolverRegistry` và áp dụng plugin nền `jvm-toolchain-management`. Sau khi đăng ký, trong `settings.gradle` cấu hình:

```groovy
toolchainManagement {
    jvm {
        javaRepositories {
            repository('approvedJdks') {
                resolverClass = CorporateResolver
                // credentials, authentication nếu resolver cần.
            }
        }
    }
}
```

`CorporateResolver` là một lớp giả định **phải được cung cấp bởi settings plugin công ty**. Đoạn trên không độc lập runnable. Đừng sửa thành `maven { url 'https://...' }` rồi chờ Gradle hiểu đó là JDK resolver: công ty phải cung cấp implementation ánh xạ yêu cầu toolchain tới download URI.

Tài liệu Gradle yêu cầu download URL dùng giao thức an toàn như HTTPS. Resolver nên thực thi policy theo OS/arch, Java release/vendor, phép đo integrity và các điều kiện phê duyệt; tránh trả bừa một binary cho mọi máy. Hệ thống nội bộ cũng phải xử lý authenticated endpoints mà không hardcode tokens vào Git.

### 12.1. Sắp xếp resolver và fallback

Nếu doanh nghiệp **cấm tải JDK từ public**, hãy chỉ đăng ký repository nội bộ; **không thêm Foojay fallback** rồi ngầm phá chính sách. Nếu tổ chức cho phép public fallback trong môi trường dev nhưng CI chỉ dùng approved mirror, phải thể hiện rõ profile/policy và xác minh thứ tự repository.

Khi resolver trả “không có bản phù hợp”, Gradle có thể xét resolver tiếp theo. Nhưng nếu có lỗi TLS/auth/download ở repository đã chọn, đừng tự khẳng định Gradle chắc chắn sẽ chuyển sang repository sau như một cách cứu; phải đọc log cụ thể và xử lý lỗi nguồn.

## 13. An toàn chuỗi cung ứng khi tự tải JDK

JDK là **một công cụ thực thi code** trong build, không chỉ là dependency thư viện. Tải và chạy một JDK từ nguồn không rõ ràng có thể rủi ro hơn tải một JAR bình thường. Một chính sách có thể kiểm toán nên xét:

- **Nhà phát hành/vendor** được tổ chức phê duyệt (ví dụ Adoptium/Temurin, Azul, Amazon Corretto, Microsoft... theo nhu cầu).
- **License và điều khoản redistribution/use** của distribution, đặc biệt với Oracle và các enterprise builds.
- **OS/arch** và loại package được tin cậy: Linux x86_64 khác Windows AArch64; không giả định một ZIP chạy được mọi nơi.
- **HTTPS, proxy, certificate trust chain**, không tắt TLS verification.
- **Checksum/chữ ký của JDK archive** theo quy trình nguồn phát hành hoặc mirror nội bộ, không lấy hash từ một response không đáng tin rồi tự coi là phê duyệt.
- **Patch/update policy** vì Gradle auto-provisioning không tự nâng installation.
- **Quyền ghi và cache JDK** trên CI; cache không nên được chia sẻ cho untrusted workloads có thể thay binary.
- **Phân quyền network egress**, đặc biệt trên CI có secrets; resolver có thể phải hỏi Disco API rồi tải từ một distribution host khác.
- **Version policy** cho plugin resolver và Gradle Wrapper, review khi nâng hai thành phần này.

**Không tự suy ra** rằng plugin Foojay 1.0.0 bảo đảm bit-for-bit identical JDK trên mọi máy. Nó tìm một **distribution tương thích điều kiện**, và có thể phụ thuộc vendor, OS, arch, thời điểm, patch availability, cài sẵn và thuật toán preference. Nếu cần tính tái lập nghiêm ngặt, pin CI image/digest và quản lý JDK archive đã kiểm tra ngoài việc dùng major Java languageVersion.

### 13.1. JDK auto-provisioning khác dependency verification

`gradle/verification-metadata.xml` phục vụ cơ chế kiểm tra **Gradle external dependency artifacts**. Đừng mặc định chỉ cần có file này là JDK được Foojay tải tự động đã được nhà cung cấp chính sách artifact của tổ chức phê duyệt. Cần xác minh **JDK distribution archive** bằng chính sách supply chain tương ứng.

Tương tự, phiên bản Gradle Wrapper nên được cố định và tải từ nguồn đáng tin, thường đi kèm distribution SHA-256 theo quy trình của tổ chức. Resolver không có nhiệm vụ sửa một Gradle Wrapper distribution sai.

## 14. Debugging: phân biệt đúng pha lỗi

### 14.1. Bốn lệnh nền tảng

Tại root có Wrapper hợp lệ:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava --info --stacktrace --console=plain
./gradlew run --console=plain
```

**Giải thích:**

1. `--version` để biết Gradle/JVM runtime; xác minh Wrapper thực sự được chạy và Java có đủ phiên bản để khởi động Gradle.
2. `javaToolchains` để xem local/provisioned installations, major Java, vendor, nguồn phát hiện và auto-download flag.
3. `compileJava --info --stacktrace` để điều tra compiler và ngoại lệ nếu không tìm được toolchain.
4. `run` để xác minh launcher tương ứng; output Java trong lab phải cho `java-feature=17`.

Một lệnh `java -version` ngoài terminal không đủ; nó có thể trả JVM của `PATH`, trong khi Gradle Daemon và JavaCompile chọn installations khác.

### 14.2. Những lỗi thường thấy

Các câu dưới là **dạng thông báo minh họa**, không cam kết chính xác wording của mọi Gradle version:

```text
No matching toolchains found for requested specification ...
No locally installed toolchains match and toolchain download
repositories have not been configured.

Toolchain download failed ...
Could not find a Java installation matching ...
Plugin [id: 'org.gradle.toolchains.foojay-resolver-convention'] was not found ...
```

Hãy phân loại **đúng pha**:

| Triệu chứng | Pha lỗi | Việc cần làm |
| --- | --- | --- |
| Wrapper không chạy vì `JAVA_HOME` sai hoặc JVM quá cũ. | Trước settings/toolchain resolver. | Cài/chọn JDK đủ để chạy Gradle, kiểm tra `./gradlew --version`. |
| Foojay plugin không resolve từ Plugin Portal. | Settings plugin resolution. | Kiểm tra plugin ID/version, `pluginManagement.repositories`, network, proxy, offline/plugin cache. |
| Gradle không tìm thấy `javaToolchains` task. | Thiếu JVM toolchains plugin/không áp dụng Java plugin hoặc sai project/version. | Dùng `id 'java'` hoặc `application`; với project không có JVM plugin, cân nhắc `jvm-toolchains`. |
| `No matching toolchains`, không có repositories cấu hình. | Toolchain selection/provisioning. | Thêm settings resolver plugin đúng chỗ, không thêm `mavenCentral()` để chữa. |
| Matching JDK không có, auto-download false. | Provisioning bị chính sách chặn. | Preinstall JDK phù hợp hoặc bật flag nếu được phép. |
| Toolchain spec chỉ có vendor mà thiếu languageVersion. | Validate JavaToolchainSpec. | Bổ sung `languageVersion` đúng major Java. |
| Đòi vendor/J9/native-image/architecture không có distribution. | Resolver trả no match. | Kiểm tra tiêu chí, distro matrix và OS/architecture; chỉ nới điều kiện nếu dự án cho phép. |
| Download lỗi `401/403`, proxy hoặc TLS handshake. | Download/network policy. | Kiểm tra credentials/CA/proxy/egress, không hardcode secrets hoặc vô hiệu hóa TLS. |
| Gradle chạy `--offline` khi JDK chưa có. | Provisioning yêu cầu network. | Preinstall JDK trên runner hoặc chạy provisioning online có kiểm soát trước đó. |
| JDK đã tải nhưng không có `bin/javac` hoặc archive sai. | Install/validation. | Xác minh bản JDK đúng OS/arch, integrity, permissions; dọn installation hỏng có kiểm soát. |
| Đổi `JAVA_HOME` nhưng toolchain vẫn chọn installation khác. | Toolchain precedence. | Xem `javaToolchains` và yêu cầu `java.toolchain`, không chỉ biến môi trường. |
| Có JDK 17 nhưng bị yêu cầu vendor khác. | Spec không match local. | Kiểm tra `JvmVendorSpec`, plugin mapping và quyền tải bản đúng vendor. |
| Thêm `java.toolchain` nhưng ứng dụng vẫn chạy Java 21. | Một `JavaExec/Test` custom khác chưa dùng launcher của toolchain. | Cấu hình `javaLauncher` riêng cho task/plugin đó; kiểm tra task thực đang chạy. |
| Thấy `auto-download: Enabled` nhưng không download. | Không cần provision vì local có, hoặc chưa có yêu cầu task; cũng có thể chưa có repository. | Phân tích điều kiện, đừng coi là lỗi chỉ vì không có log download. |
| Update patch JDK nhưng Gradle vẫn dùng bản cũ trong `jdks`. | Auto-provision không auto-upgrade installation. | Thực hiện JDK patch rollout bằng policy, dừng daemon và kiểm tra precedence. |

### 14.3. Quy trình 8 bước xác định nguyên nhân

1. **Xác định task** đang yêu cầu Java: `compileJava`, `test`, `javadoc`, `run`, custom task hoặc daemon.
2. **Kiểm tra Gradle/JVM startup** bằng `./gradlew --version`. Nếu chưa vào settings, Foojay không thể chữa được.
3. **Đọc toolchain spec** ở đúng project: languageVersion, vendor, implementation, nativeImageCapable; lưu ý toolchain override ở task/plugin khác.
4. **Liệt kê installations** qua `./gradlew -q javaToolchains`. Chú ý local, đã provision và source `Detected by`.
5. **Xác định hai flag** `auto-detect` / `auto-download`, các paths/fromEnv.
6. **Đọc settings.gradle**: plugin Foojay convention có được áp dụng không, hay base plugin đã có `toolchainManagement.jvm.javaRepositories`? Kiểm tra plugin resolution có thông không.
7. **Kiểm tra kết nối và khả năng đáp ứng**: GA version, vendor/OS/architecture, TLS/HTTP status/credentials/proxy, offline.
8. **Thay một nguyên nhân**, dừng daemon nếu cần, chạy lại `javaToolchains` và task gốc; xác minh kết quả biên dịch/chạy, không đánh giá từ log “download started” riêng lẻ.

## 15. Quy trình CI: lựa chọn preinstall hay auto-provision?

### 15.1. CI đã cài JDK chuẩn

Một runner được kiểm soát có JDK 17 đã được security team phê duyệt:

```text
CI image:
  Gradle-compatible runtime JVM: JDK 17 hoặc mới hơn
  Project JDK 17: đã cài và được Gradle nhận diện
  Auto-download: có thể tắt để enforce policy
  Toolchain build.gradle: languageVersion=17
```

Ưu điểm: không phụ thuộc Foojay API/download endpoint ở mọi build, dễ kiểm soát JDK patch/digest. Nhược điểm: phải bảo trì CI image/JDK. Nếu tắt auto-download mà project yêu cầu toolchain khác, build fail rõ ràng thay vì âm thầm tải distribution không được duyệt.

### 15.2. CI cho phép auto-provisioning

Một runner có JDK đủ để khởi động Gradle, toolchain khác chưa có. Cần:

- Resolver/settings plugin **đã được resolve** và có quyền truy cập.
- JDK download endpoints/phương thức authentication/HTTPS được phép.
- Có dung lượng disk và quyền ghi Gradle User Home.
- Cache JDK được quản lý, không dùng chung với untrusted builds và có lịch cập nhật patch.
- Report JDK installation đã chọn trong build logs/metadata; không chỉ record “build success”.
- Kiểm tra plugin version và Wrapper compatibility, không tự thay bằng latest.
- Thông tin về license/vulnerability của JDK distribution và nguồn tải được phê duyệt.

**Không** mặc định mọi CI có Internet. Nếu runner air-gapped, preinstall JDK hoặc dùng mirror nội bộ được giải quyết bằng custom resolver, không dùng một URL ngẫu nhiên và tắt TLS.

### 15.3. Kịch bản local vs CI: build reproducibility

| Yếu tố | Máy developer | CI |
| --- | --- | --- |
| Gradle Wrapper | Cùng `gradle-wrapper.properties` | Cùng file đã commit. |
| JVM chạy Gradle | Có thể Java 21 | Có thể Java 17/21 theo policy. |
| Toolchain yêu cầu | `languageVersion=17` | Cùng yêu cầu. |
| JDK được chọn | JDK 17 local hoặc đã provision. | JDK 17 preinstalled hoặc provision. |
| Vendor/patch | Phụ thuộc restrictions/local availability. | Nên được kiểm soát và ghi nhận. |
| Download | Chỉ khi thiếu và được phép. | Theo network/JDK policy. |
| Java compile target | `options.release` theo yêu cầu. | Cùng target/API level. |

Toolchain giúp ổn định **major Java version**, nhưng để bit-for-bit reproducible artifacts còn cần quản lý Gradle version, environment variables, locale/timezone, dependencies, build logic, annotation processors, timestamps, compiler settings và output normalization. Đừng gán hết sự ổn định build cho một settings resolver plugin.

## 16. Các bẫy và ngộ nhận cần nhớ

1. **Chỉ khai báo `languageVersion=17` rồi chắc chắn tải JDK:** thiếu local matching JDK và resolver repository mới là tình huống có thể provision.
2. **Đặt Foojay resolver plugin trong `build.gradle`:** đây là settings plugin; đặt trong `settings.gradle`.
3. **Bật `org.gradle.java.installations.auto-download=true` nhưng không có resolver:** flag không tự tạo download endpoint.
4. **Thêm `mavenCentral()` để chữa lỗi JDK:** Maven dependencies và toolchain download repositories khác nhau.
5. **Đánh đồng plugin được tải với JDK được tải:** hai pha riêng và có network/cache requirements riêng.
6. **Dùng `JAVA_HOME` làm bằng chứng task compile chọn JDK nào:** hãy xem `javaToolchains` và task toolchain settings.
7. **Dùng `java -version` ngoài shell thay thế chẩn đoán Gradle:** nó phản ánh terminal Java, không nhất thiết Gradle toolchain.
8. **Cho rằng `--release 17` sẽ tải JDK 17:** nó chỉ giới hạn compile target/APIs.
9. **Chọn Java 17 với yêu cầu vendor/implementation không có trong repository:** resolver không thể tạo distribution không tồn tại.
10. **Nhầm early access với GA release:** Gradle auto-provision không tải EA JDK theo cơ chế chính thức.
11. **Tưởng luôn tải patch Java mới nhất:** auto-provisioned installations không được tự cập nhật.
12. **Tắt auto-detect để “ép download” mà không biết precedence:** có thể làm build khó dự đoán; dùng spec và runner policy rõ.
13. **Dùng `--offline` khi JDK/plugin chưa cache:** offline không tự tải được binary.
14. **Xóa toàn bộ `~/.gradle` để chữa lỗi mismatch:** làm mất nhiều cache, không giải quyết spec/credentials/TLS.
15. **Hardcode JDK paths vào custom task:** không portable; dùng `JavaLauncher`/`JavaCompiler` Providers khi plugin hỗ trợ.
16. **Gọi `.get()` của compiler/launcher providers quá sớm lúc configuration:** có thể gây eager toolchain resolution/download và làm giảm tính lazy/configuration-cache friendliness.
17. **Tin JDK mới tải là an toàn chỉ vì dùng HTTPS:** còn phải quản lý nguồn, license, checksum/signature, patch cycle.
18. **Trộn Foojay convention với base resolver config trùng lặp:** dễ thêm repositories không cần thiết hoặc sắp xếp sai nguồn; chọn một mô hình.
19. **Dùng JDK resolver để chữa Java API compile failure do code:** cần phân biệt code đang dùng API quá mới, `options.release`, compiler JDK và module dependencies.
20. **Không dừng daemon sau khi đổi JDK paths/tắt provisioning:** Gradle có thể giữ metadata cũ; chạy `./gradlew --stop` trước khi xác minh lại khi cần.

## 17. Bài tập thực hành và đáp án định hướng

### Bài 1 — Đọc ba lớp JVM

Trên máy có Gradle chạy bằng JDK 21 nhưng project khai báo toolchain 17, `./gradlew --version` có thể hiện version 21 trong thông tin JVM Gradle, còn `run` của lab in `java-feature=17`. Có mâu thuẫn không? **Không**: đó là hai vai trò JVM khác nhau.

### Bài 2 — Không có resolver

Trên môi trường **cách ly** chỉ có JDK 21, lab yêu cầu Java 17. Loại bỏ Foojay settings plugin, giữ auto-download true. Task `compileJava` có thể thất bại dù `auto-download` bật. Tại sao? **Không có toolchain download repositories**, nên Gradle không biết nguồn nào cung cấp JDK.

### Bài 3 — Convention so với base plugin

Viết hai phiên bản `settings.gradle`: (A) áp dụng `org.gradle.toolchains.foojay-resolver-convention` đơn giản; (B) dùng `org.gradle.toolchains.foojay-resolver` kèm `toolchainManagement.jvm.javaRepositories.repository('foojay')` và `resolverClass`. Tại sao chỉ cần **một** phiên bản cho lab?

### Bài 4 — Tắt auto-download

Đặt `org.gradle.java.installations.auto-download=false` và yêu cầu một JDK không có local. Dự đoán kết quả. Nếu máy đã có JDK matching, kết quả có khác không? **Có:** matching local JDK vẫn có thể được chọn vì tắt provision không tắt auto-detection.

### Bài 5 — Vendor filter

Yêu cầu `languageVersion=17`, `vendor=JvmVendorSpec.ADOPTIUM`. Máy có Oracle JDK 17, không có Adoptium. Vì sao Gradle không mặc nhiên dùng Oracle? Hướng xử lý: provision bản Adoptium khi được phép, preinstall bản phù hợp, hoặc nới constraint **nếu policy chấp nhận**.

### Bài 6 — GA và Early Access

Project yêu cầu một JDK early-access chưa GA. Foojay plugin đã cấu hình và network online, tại sao resolver có thể không cung cấp được? **Gradle auto-provisioning chính thức chỉ tải GA releases**. Không nên tự coi mọi missing download là lỗi proxy.

### Bài 7 — Java compile vs runtime

Thử đổi toolchain của lab thành Java 21 và đặt `options.release = 17` cho JavaCompile. Runtime `run` có còn in `java-feature=17` không? **Không nhất thiết**: run task có thể dùng Java 21, trong khi compiled classes được nhắm API/bytecode Java 17. Phải phân biệt compiler, output target và launcher.

### Bài 8 — Offline build

Máy đã cache Foojay plugin, có JDK 17 trong `GRADLE_USER_HOME/jdks`. Chạy `--offline` có cần tải JDK không? Không, nếu installation còn hợp lệ. Nhưng nếu settings plugin hoặc Gradle distribution chưa có, vẫn có thể fail trước khi chạy task. Giải thích cả hai trường hợp.

### Bài 9 — CI chuẩn

Thiết kế pipeline cho project Java 17 theo hai chiến lược: (A) preinstalled JDK 17 đã được approved + auto-download false; (B) resolver nội bộ có mirror HTTPS, cache/patch policy rõ và egress được giới hạn. So sánh bảo mật, độ lặp lại, tốc độ và vận hành.

### Bài 10 — Chẩn đoán error

Log báo “No matching toolchains found ... download repositories have not been configured”. Developer vừa thêm `mavenCentral()` trong `build.gradle`. Vì sao vẫn fail? Cần sửa **settings resolver configuration**, không phải project library repository.

### Bài 11 — Daemon JVM

Nếu Wrapper cần JDK 17+ để khởi động nhưng `JAVA_HOME` trỏ JDK quá cũ, Foojay có cứu được không? **Không**: settings plugin chưa được chạy. Khắc phục Gradle JVM startup trước, rồi mới dùng resolver chọn project toolchain.

### Bài 12 — Patch update

CI đã provision JDK 17 từ hai tháng trước. Có một bản patch mới sửa lỗ hổng. Vì sao `auto-download=true` không tự cập nhật installation? Trình bày cách dùng policy CI image/cache, kiểm tra vendor/patch và rollout có kiểm soát.

### Câu hỏi nhanh

1. **Resolver nằm ở `build.gradle` hay `settings.gradle`?** Ở settings plugin.
2. **Foojay convention có tự cấu hình download repository không?** Có.
3. **Foojay base plugin có tự đủ cấu hình repository không?** Không, phải thêm `toolchainManagement.jvm.javaRepositories`.
4. **Auto-download mặc định bật có bảo đảm tải được không?** Không.
5. **Có JDK phù hợp local thì Gradle có phải tải mới không?** Không.
6. **`javaToolchains` dùng để làm gì?** Xem installations, vendor, major version, nguồn phát hiện, trạng thái flags.
7. **`JAVA_HOME` khác `java.toolchain` ở đâu?** Startup/default Gradle JVM so với compiler/launcher task được chọn.
8. **`options.release=17` có làm auto-provision JDK 17 không?** Không.
9. **Gradle tự tải JDK early access không?** Không theo cơ chế auto-provisioning được tài liệu mô tả.
10. **JDK tải về được cất ở đâu?** Thư mục `jdks` bên trong Gradle User Home.
11. **Toolchain đã provision có tự nâng patch?** Không.
12. **Tại sao offline có thể fail trước khi chọn JDK?** Foojay settings plugin chưa được cache hoặc Wrapper distribution chưa sẵn sàng.
13. **Bản Gradle chạy trên JDK 21 có thể compile bằng JDK 17 không?** Có, nếu Gradle/toolchain hỗ trợ và JDK 17 được chọn.
14. **Gradle download URI của custom resolver phải dùng gì?** Giao thức an toàn như HTTPS.
15. **Resolver không tìm được distribution phù hợp nên làm gì?** Đọc yêu cầu/spec và policy; không tự dùng bản khác major hoặc vendor sai.
16. **Trong môi trường bảo mật nghiêm, có nên tự fallback ra public Foojay không?** Chỉ nếu policy được phê duyệt.
17. **Đâu là công cụ đối chiếu Java thực sự chạy task?** `javaToolchains` cùng task log và runtime output.
18. **Có nên gọi `.get()` trên `JavaCompiler` provider ngay ở configuration không?** Tránh; giữ lazy và nối Providers vào task.
19. **Toolchain resolver có tự làm JDK đã provision không còn CVE không?** Không, cần patch update policy.
20. **Nếu task custom bỏ qua toolchain API thì sao?** Task có thể chạy JVM khác; cần cấu hình JavaLauncher/JavaCompiler đúng.

## 18. Tài liệu tham khảo và lộ trình đọc

Các nguồn sau là **tài liệu chính thức**; code Groovy trong bài áp dụng theo cơ chế Gradle 8/9, cụ thể bản Foojay 1.0.0 đang được trang plugin Gradle cung cấp:

1. **Gradle — Toolchains for JVM projects:** cấu hình Java version, spec, local detection, auto-provisioning, download repositories, precedence, `javaToolchains`, `auto-download`: https://docs.gradle.org/current/userguide/toolchains.html
2. **Gradle — Toolchain Resolver Plugins:** `JavaToolchainResolver`, `JavaToolchainRequest`, `JavaToolchainDownload`, `JavaToolchainResolverRegistry` và Settings plugin: https://docs.gradle.org/current/userguide/toolchain_plugins.html
3. **Gradle — JVM Toolchains Plugins:** `jvm-toolchain-management`, `jvm-toolchains` và settings DSL: https://docs.gradle.org/current/userguide/jvm_toolchains_plugins.html
4. **Gradle Plugin Portal — Foojay resolver convention 1.0.0:** plugin ID, version, mô tả và cách áp dụng: https://plugins.gradle.org/plugin/org.gradle.toolchains.foojay-resolver-convention
5. **Gradle Foojay Toolchains Plugin (official Gradle GitHub):** convention vs base plugin, vendor/implementation mapping và hạn chế: https://github.com/gradle/foojay-toolchains
6. **Gradle — Build Environment Configuration:** các properties `org.gradle.java.installations.auto-detect`, `auto-download`, `paths`, `fromEnv`: https://docs.gradle.org/current/userguide/build_environment.html
7. **Gradle — Gradle Daemon and Daemon JVM criteria:** JVM chạy Gradle và cơ chế Daemon JVM provisioning khác project toolchain: https://docs.gradle.org/current/userguide/gradle_daemon.html
8. **Gradle — Declaring Repositories:** plugin repositories khác project repositories: https://docs.gradle.org/current/userguide/declaring_repositories_basics.html
9. **Gradle — Java Plugin:** JavaCompile/Test/Javadoc tasks và toolchain integration: https://docs.gradle.org/current/userguide/java_plugin.html
10. **Gradle — Java Toolchain DSL:** public API của specs/compiler/launcher: https://docs.gradle.org/current/dsl/org.gradle.jvm.toolchain.JavaToolchainSpec.html

**Kết luận:** Toolchain resolver là thành phần trong **settings** dùng ánh xạ yêu cầu Java version/vendor/platform thành **nguồn tải JDK**. Auto-download chỉ xảy ra khi **task cần một JDK phù hợp nhưng không có local match**, feature được bật, repository/resolver đã khai báo và có GA distribution cho OS/arch/vendor với network/quyền truy cập hợp lệ. `JAVA_HOME`, `options.release`, Maven repositories và Gradle Daemon JVM criteria là những cơ chế khác nhau. Một cấu hình tốt phải vừa chọn đúng JDK cho task, vừa kiểm soát nguồn tải, bảo mật, patch updates và tính tái lập trên CI.