# `--release`: đồng bộ luật ngôn ngữ, bytecode và API của phiên bản đích

Khi biên dịch một ứng dụng bằng JDK mới nhưng vẫn cần chạy trên JDK cũ hơn, chỉ đặt phiên bản source và target là chưa đủ. Ví dụ, nhóm có thể dùng JDK 21 để biên dịch nhưng muốn artifact chạy được trên Java 17. Nếu chỉ dùng `-source 17 -target 17`, compiler vẫn có thể nhìn thấy API của JDK 21 và cho phép mã nguồn gọi những method chưa tồn tại trong Java 17. Artifact khi chạy trên Java 17 có thể gặp lỗi liên kết dù bytecode đã được tạo ở mức Java 17.

Tùy chọn `--release` của `javac` giải quyết vấn đề này bằng cách đồng bộ ba yếu tố theo một phiên bản Java đích: luật ngôn ngữ được chấp nhận, định dạng bytecode được tạo và tập API Java SE mà mã nguồn được phép tham chiếu khi biên dịch. Đây là công cụ quan trọng để xác định baseline Java của một module và duy trì khả năng tương thích khi nâng cấp JDK dùng trong quá trình build.

## 1. Ba yếu tố cần đồng bộ khi biên dịch

Một lần biên dịch Java có ít nhất ba khía cạnh độc lập:

1. **Luật ngôn ngữ (source language level):** compiler chấp nhận cú pháp và tính năng ngôn ngữ Java ở phiên bản nào.
2. **Phiên bản bytecode (class-file target):** compiler tạo file `.class` theo định dạng mà JVM của phiên bản Java nào có thể đọc.
3. **API nền tảng (platform API):** mã nguồn được phép gọi những lớp và method tiêu chuẩn nào của JDK.

Ba yếu tố này cần thống nhất với baseline mà module công bố hỗ trợ. Nếu chỉ đồng bộ hai yếu tố đầu, mã nguồn vẫn có thể tham chiếu API mới hơn runtime mục tiêu.

Ví dụ, ứng dụng muốn hỗ trợ Java 17 nhưng build trên JDK 21:

| Yếu tố | Giá trị cần có |
|---|---|
| Luật ngôn ngữ | Java 17 |
| Bytecode | Java 17 (class-file major version 61) |
| API Java SE | Tập API của Java 17 |
| JDK chạy compiler | Có thể là JDK 21 |
| JDK tối thiểu để chạy artifact | Java 17, với điều kiện dependency và môi trường cũng tương thích |

JDK chạy compiler không nhất thiết phải trùng với JDK tối thiểu dùng để chạy ứng dụng. `--release` cho phép dùng compiler mới hơn để tạo artifact theo một release cũ hơn trong phạm vi release mà compiler đó hỗ trợ.

## 2. `-source`, `-target` và `--release` khác nhau thế nào?

### 2.1. `-source` chỉ định luật ngôn ngữ

`-source N` yêu cầu compiler áp dụng luật ngôn ngữ của Java N. Nó kiểm soát các cú pháp và tính năng ngôn ngữ được chấp nhận.

Ví dụ, compiler có thể từ chối cú pháp `record` khi source level thấp hơn phiên bản Java đưa tính năng này vào ngôn ngữ. Tuy nhiên, `-source` không tự giới hạn API mà compiler nhìn thấy.

### 2.2. `-target` chỉ định định dạng bytecode

`-target N` yêu cầu compiler tạo class file theo định dạng của Java N. JVM có thể từ chối nạp class file nếu phiên bản bytecode cao hơn mức JVM hỗ trợ.

`-target` không tự giới hạn API của JDK đang dùng để biên dịch. Nếu compiler chạy trên JDK 21, mã nguồn vẫn có thể nhìn thấy API Java 21 dù target bytecode được đặt thấp hơn.

### 2.3. `--release` đồng bộ cả ba yếu tố

`--release N` yêu cầu compiler:

- Áp dụng luật ngôn ngữ của Java N.
- Tạo bytecode tương thích với phiên bản Java N.
- Chỉ cho phép sử dụng API của Java SE được cung cấp trong release N.

Compiler sử dụng dữ liệu mô tả API nền tảng theo từng release, được phân phối cùng JDK (thường thông qua dữ liệu `ct.sym`), để kiểm tra việc tham chiếu API. Nhờ vậy, mã nguồn không thể vô tình gọi một API Java SE chỉ xuất hiện sau phiên bản mục tiêu.

Ví dụ:

```bash
javac --release 17 -d out src/main/java/com/example/App.java
```

Lệnh này dùng compiler đang được gọi để biên dịch theo luật Java 17, tạo bytecode Java 17 và giới hạn API Java SE ở mức Java 17.

| Tùy chọn | Luật ngôn ngữ | Bytecode | API nền tảng |
|---|---|---|---|
| `-source 17` | Java 17 | Theo cấu hình target/default riêng | Có thể nhìn thấy API của JDK chạy compiler |
| `-target 17` | Theo cấu hình source/default riêng | Java 17 | Có thể nhìn thấy API của JDK chạy compiler |
| `-source 17 -target 17` | Java 17 | Java 17 | Vẫn có thể nhìn thấy API mới của JDK compiler |
| `--release 17` | Java 17 | Java 17 | API Java SE của Java 17 |

`--release` không phải là một bước chuyển đổi bytecode sau khi biên dịch. Nó tác động ngay trong quá trình compiler kiểm tra và tạo class file.

## 3. Vì sao chỉ dùng `-source` và `-target` có thể gây lỗi?

Giả sử nhóm dùng JDK 21 để build một thư viện, nhưng thư viện phải chạy trên Java 17. Trong mã nguồn có lời gọi `Files.mismatch`, một API được bổ sung sau Java 17.

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class FileComparator {
    public long compare(Path left, Path right) throws Exception {
        return Files.mismatch(left, right);
    }
}
```

Nếu chỉ cấu hình:

```bash
javac -source 17 -target 17 FileComparator.java
```

compiler chạy trên JDK 21 có thể chấp nhận lời gọi API vì API đó tồn tại trong JDK 21. Bytecode được tạo ở mức Java 17, nhưng class vẫn chứa symbolic reference tới method không có trong Java 17. Khi chạy trên Java 17, JVM có thể phát sinh `NoSuchMethodError` khi code path gọi method đó.

Nếu dùng:

```bash
javac --release 17 FileComparator.java
```

compiler từ chối lời gọi `Files.mismatch` vì method này không thuộc API Java SE của release 17. Lỗi được phát hiện ngay trong quá trình build, trước khi artifact được phát hành.

Đây là khác biệt quan trọng giữa “bytecode có thể được JVM cũ đọc” và “mã nguồn chỉ sử dụng API mà JVM cũ cung cấp”. Một artifact chỉ thực sự phù hợp với baseline khi cả hai điều kiện được đáp ứng, cùng với các dependency và yêu cầu runtime khác.

## 4. Cách sử dụng `javac --release`

### 4.1. Xác định các release mà compiler hỗ trợ

```bash
javac --help
```

Trong phần tùy chọn chuẩn, xem mô tả `--release` và các release được hỗ trợ. Compiler chỉ có thể biên dịch cho release hiện tại hoặc một số release cũ hơn mà JDK đó còn cung cấp dữ liệu tương thích. Không thể dùng compiler Java 17 để tạo target Java 21.

Kiểm tra JDK thực tế:

```bash
java -version
javac -version
```

`java` và `javac` có thể đến từ các JDK khác nhau nếu `PATH` hoặc `JAVA_HOME` được cấu hình không nhất quán. Khi điều tra lỗi build, cần xác nhận cả hai và đường dẫn executable thực tế.

### 4.2. Biên dịch một source file

```bash
mkdir -p out
javac --release 17 -d out src/main/java/com/example/App.java
```

`-d out` chỉ định thư mục chứa class file. Tùy chọn `--release 17` kiểm soát source level, target bytecode và API nền tảng.

### 4.3. Biên dịch nhiều source file

Trên Linux/macOS có thể dùng:

```bash
mkdir -p out
find src/main/java -name '*.java' -print0 \
  | xargs -0 javac --release 17 -d out
```

Hoặc dùng build tool như Gradle/Maven để quản lý source set, dependency, annotation processor và incremental compilation. Trong dự án thực tế, build tool thường là nơi thích hợp để đặt baseline thống nhất.

### 4.4. Không kết hợp `--release` với `-source` hoặc `-target`

Không cấu hình đồng thời:

```bash
javac --release 17 -source 17 -target 17 App.java
```

`--release` đã xác định cả source và target. `javac` không cho phép kết hợp `--release` với các tùy chọn `-source` hoặc `-target`; hãy chọn một cách cấu hình rõ ràng.

## 5. Cấu hình `--release` trong Gradle

Trong Gradle Java plugin, `JavaCompile.options.release` là cách khai báo release mục tiêu cho compiler. Có thể dùng JDK toolchain mới hơn để chạy compiler và đặt release thấp hơn cho artifact.

Ví dụ Kotlin DSL (`build.gradle.kts`):

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Trong ví dụ này:

- Toolchain yêu cầu compiler Java 21.
- `options.release` yêu cầu biên dịch theo baseline Java 17.
- Mã nguồn không được dùng cú pháp hoặc API Java SE chỉ có từ Java 18 trở lên.
- Class file được tạo theo định dạng Java 17.

Với Groovy DSL (`build.gradle`):

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Nên đặt cấu hình ở convention plugin hoặc nơi quản lý build chung nếu nhiều module phải tuân thủ cùng baseline. Nếu mỗi module có mục tiêu Java khác nhau, cấu hình theo module và ghi rõ lý do.

### 5.1. Phân biệt toolchain, `options.release` và runtime test

Ba cấu hình sau trả lời ba câu hỏi khác nhau:

| Cấu hình | Vai trò |
|---|---|
| Java toolchain | JDK/compiler nào được dùng để thực hiện task biên dịch hoặc task liên quan. |
| `options.release` | Mã nguồn được biên dịch theo luật, bytecode và API nền tảng của release nào. |
| Java launcher cho test/app | JVM nào thực sự chạy test hoặc ứng dụng. |

Đặt toolchain Java 21 và `options.release = 17` không tự động làm test chạy trên Java 17. Nếu cần chứng minh ứng dụng chạy được trên baseline Java 17, hãy cấu hình test launcher Java 17 và chạy integration/smoke test trên runtime đó.

Ví dụ Kotlin DSL cho task test chạy trên Java 17:

```kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
```

Đảm bảo JDK 17 có sẵn hoặc môi trường toolchain resolver có thể cung cấp nó. Trong pipeline thực tế, nên kiểm tra output phiên bản JVM của test worker để xác nhận runtime đúng như mong muốn.

### 5.2. Áp dụng cho cả source set cần thiết

`tasks.withType<JavaCompile>()` thường bao phủ các task biên dịch Java như main và test. Nếu dự án có source set tùy chỉnh, generated source hoặc module con với plugin riêng, hãy xác nhận task tương ứng thực sự nhận `options.release`.

Với build kết hợp Java, Kotlin, Scala, Android hoặc annotation processor, không nên giả định một cấu hình `JavaCompile` tự động kiểm soát mọi compiler. Mỗi ngôn ngữ/plugin có tùy chọn riêng để đặt language/API target và toolchain. Cần đồng bộ chúng theo cùng baseline.

## 6. Dùng Maven Compiler Plugin

Với Maven, có thể cấu hình release trong `maven-compiler-plugin`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Phiên bản plugin trong ví dụ chỉ minh họa cấu trúc cấu hình; dự án cần chọn phiên bản plugin phù hợp với Maven, JDK và chính sách dependency đã được quản lý. Với Maven Compiler Plugin hiện đại, `release` được chuyển thành tùy chọn `--release` của `javac` khi compiler hỗ trợ.

Không nên chỉ khai báo `source` và `target` trong khi mục tiêu là bảo đảm API Java SE của phiên bản đích. Nếu cần hỗ trợ một JDK quá cũ để có `--release`, phải áp dụng phương án tương thích riêng ở phần tiếp theo.

## 7. Khi nào `--release` không thể giải quyết toàn bộ tương thích?

`--release` giới hạn phần API nền tảng Java SE mà compiler dùng để kiểm tra mã nguồn. Nó không phải là bộ kiểm tra toàn bộ dependency hay runtime.

### 7.1. Không kiểm soát bytecode của dependency

Giả sử ứng dụng của nhóm được biên dịch bằng `--release 17`, nhưng một thư viện bên thứ ba chỉ được biên dịch cho Java 21. Mã nguồn ứng dụng có thể biên dịch thành công nếu dependency có API phù hợp với compiler, nhưng khi chạy trên Java 17, JVM có thể từ chối nạp class của dependency với lỗi như `UnsupportedClassVersionError`.

Vì vậy, cần kiểm tra baseline bytecode của toàn bộ dependency runtime, plugin, agent và module nội bộ. `--release` chỉ điều khiển class file do các task compiler đã được cấu hình tạo ra.

### 7.2. Không kiểm soát API của thư viện bên thứ ba

`--release 17` giới hạn API Java SE, không biết dependency bên ngoài có yêu cầu Java 21 hay không. Một thư viện có thể khai báo Java 8 bytecode nhưng ở runtime lại gọi API Java 21, hoặc phiên bản mới có metadata yêu cầu JDK cao hơn. Cần đọc metadata, tài liệu hỗ trợ và kiểm thử dependency trên runtime mục tiêu.

### 7.3. Không chọn JDK chạy ứng dụng

Artifact được biên dịch với `--release 17` có thể chạy trên Java 17 trở lên trong điều kiện dependency và môi trường tương thích. Tùy chọn này không đóng gói JVM, không chọn vendor distribution và không cấu hình container/production.

### 7.4. Không bảo đảm tương thích hành vi

Compiler kiểm tra cú pháp, class-file target và khả năng tham chiếu API. Nó không chứng minh chương trình có cùng kết quả, hiệu năng, thứ tự xử lý, hành vi concurrency hoặc cách xử lý lỗi trên mọi JDK.

### 7.5. Không bao phủ mọi API nội bộ và truy cập động

`--release` có thể ngăn nhiều tham chiếu tới API JDK không thuộc release đích, nhưng không thay thế việc kiểm tra dependency, reflection, JNI, dynamic loading hoặc các truy cập được thực hiện qua cấu hình chuỗi. Dùng thêm `jdeps --jdk-internals`, source search và test trên runtime mục tiêu.

## 8. Trường hợp dự án phải build trên JDK 8

`--release` được giới thiệu từ JDK 9. `javac` của JDK 8 không có tùy chọn này. Nếu phải duy trì build bằng JDK 8, có thể dùng `-source` và `-target` cho luật ngôn ngữ và bytecode, nhưng cần kiểm soát API Java 8 bằng một cơ chế khác.

Ví dụ:

```bash
javac -source 8 -target 8 -bootclasspath /path/to/jdk8/jre/lib/rt.jar \
  -d out src/main/java/com/example/App.java
```

Đường dẫn `rt.jar` là ví dụ cho JDK 8 tiêu chuẩn; cách cài đặt cụ thể có thể khác theo vendor. Phải dùng boot class path đúng phiên bản mục tiêu. Không thể lấy một `rt.jar` tương đương từ JDK 21 vì cấu trúc runtime đã thay đổi.

Một phương án khác là dùng compiler/toolchain JDK 8 để biên dịch source và API Java 8, hoặc dùng công cụ kiểm tra API signature như Animal Sniffer với signature tương ứng. Cần kiểm tra cách tích hợp vào build và độ bao phủ của công cụ.

Nếu mục tiêu là Java 8 nhưng tổ chức có thể nâng JDK dùng để build lên 9 trở lên, dùng `--release 8` từ một compiler hiện đại thường rõ ràng và ít rủi ro hơn việc tự duy trì boot class path cũ.

## 9. `--release` và preview features

Preview feature được cung cấp để thử nghiệm trong một feature release cụ thể. Chúng không nên được xem như API/ngôn ngữ ổn định có thể mang sang release khác mà không thay đổi. Việc bật preview yêu cầu compiler và runtime phù hợp với release cung cấp tính năng; class file sử dụng preview feature phải được chạy với cơ chế preview tương ứng.

Nếu module dùng preview feature, hãy ghi rõ feature release thử nghiệm, cách bật preview khi biên dịch/chạy và kế hoạch loại bỏ hoặc chuyển sang API ổn định. Đọc quy tắc tương thích của đúng `javac` mục tiêu vì preview có những giới hạn riêng khi kết hợp với các tùy chọn source/release.

Với module cần phát hành thư viện hoặc ứng dụng có baseline dài hạn, nên tránh để preview feature trở thành một phần không được quản lý của hợp đồng công khai.

## 10. Xác minh bytecode và API sau khi biên dịch

### 10.1. Kiểm tra class-file version

`javap -verbose` hiển thị major version của class file:

```bash
javap -verbose -classpath build/classes/java/main com.example.App
```

Một số giá trị major version thường gặp:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu baseline là Java 17, class file của mã nguồn cần ở major version 61. Kiểm tra này xác nhận định dạng bytecode, nhưng không xác nhận tập API mà mã nguồn đã sử dụng. Vì vậy, cần kết hợp với việc cấu hình `--release` và test trên Java 17.

### 10.2. Kiểm tra API mới hơn baseline

Tạo một thử nghiệm nhỏ có sử dụng API chỉ có ở phiên bản mới hơn, ví dụ `Files.mismatch` khi target Java 17. Khi compiler được cấu hình đúng `--release 17`, đoạn code đó phải bị từ chối ở compile time.

Thử nghiệm này giúp xác nhận build thực sự truyền `--release` tới compiler. Không nên chỉ nhìn cấu hình trong build file; cần xem log compiler hoặc thực hiện compile test trong CI.

### 10.3. Chạy test trên JDK tối thiểu

Biên dịch với `--release 17` nhưng chỉ chạy test trên JDK 21 vẫn chưa chứng minh runtime Java 17 hoạt động. Hãy chạy ít nhất smoke test và integration test trên JDK tối thiểu được hỗ trợ, cùng các test quan trọng trên runtime production đã chọn.

### 10.4. Kiểm tra dependency

Đối với từng dependency runtime:

- Xác định class-file major version của artifact.
- Đọc yêu cầu JDK tối thiểu trong metadata/tài liệu của thư viện.
- Kiểm tra dependency bắc cầu và native library.
- Chạy ứng dụng trên JDK tối thiểu để phát hiện lỗi nạp lớp hoặc gọi API không tồn tại.

Không nên suy ra mức tương thích của toàn ứng dụng chỉ từ class file của module chính.

## 11. Thiết lập baseline nhất quán trong CI

Để tránh local build thành công nhưng CI hoặc production có kết quả khác, nên ghi nhận baseline ở các lớp sau:

| Lớp cấu hình | Giá trị cần quản lý |
|---|---|
| Gradle/Maven runtime | JDK chạy build tool và phiên bản build tool tương thích. |
| Compiler toolchain | Vendor và feature release của compiler. |
| Compiler release | Giá trị `--release` áp dụng cho từng source set/module. |
| Test launcher | JDK dùng để chạy unit/integration test. |
| Runtime artifact | JDK tối thiểu được hỗ trợ và distribution production. |
| Dependencies | Baseline Java của từng thư viện, plugin và agent. |
| Container/OS | Image, digest, OS, architecture và native packages. |

Nên dùng build convention hoặc cấu hình tập trung để mọi module cùng baseline nhận được thiết lập thống nhất. Nếu module có baseline khác nhau, cần thể hiện rõ trong metadata hoặc tài liệu của module, tránh cấu hình rải rác khó truy vết.

CI nên có các bước:

1. In phiên bản JDK, vendor và Gradle/Maven trước khi build.
2. Kiểm tra compiler task có nhận `--release` đúng giá trị.
3. Build và test trên compiler toolchain đã chọn.
4. Chạy test runtime trên JDK tối thiểu được hỗ trợ.
5. Kiểm tra dependency bytecode/API và artifact cuối cùng.
6. Lưu log, artifact và thông tin môi trường để có thể tái lập kết quả.

## 12. Checklist khi thiết lập hoặc thay đổi `--release`

- [ ] Đã xác định rõ JDK tối thiểu mà module cam kết hỗ trợ.
- [ ] Đã chọn compiler JDK đủ mới để hỗ trợ release mục tiêu.
- [ ] Đã dùng `--release` thay cho cặp `-source`/`-target` khi compiler hỗ trợ.
- [ ] Đã kiểm tra tất cả JavaCompile task và source set liên quan nhận cùng cấu hình.
- [ ] Đã đồng bộ Kotlin/Scala/Android compiler hoặc plugin khác nếu dự án sử dụng.
- [ ] Đã xác nhận test runtime trên JDK tối thiểu, không chỉ trên JDK compiler.
- [ ] Đã kiểm tra baseline bytecode và API của dependency runtime.
- [ ] Đã xác minh class-file major version của artifact.
- [ ] Đã có compile test chứng minh API mới hơn release bị từ chối.
- [ ] Đã ghi nhận giới hạn với preview feature, annotation processor và native dependency nếu có.
- [ ] Đã lưu phiên bản JDK, vendor, build tool và log CI.

## Kết luận

`--release N` là cách trực tiếp để đồng bộ luật ngôn ngữ, bytecode và API Java SE theo release N. Nó giúp compiler mới phát hiện sớm việc mã nguồn vô tình sử dụng API chỉ có ở JDK mới hơn, điều mà chỉ `-source` và `-target` không bảo đảm. Tuy nhiên, `--release` chỉ kiểm soát mã nguồn được biên dịch bởi compiler đã cấu hình; nó không tự kiểm tra bytecode/API của dependency, chọn runtime production hay chứng minh tương thích hành vi. Một baseline Java đáng tin cậy cần kết hợp compiler release, toolchain, test trên JDK tối thiểu, kiểm tra dependency và cấu hình CI nhất quán.
