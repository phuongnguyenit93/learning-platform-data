# Cấu hình riêng cho tính năng preview, module incubator và tùy chọn experimental trong JDK 25

## 1. Vì sao cần cấu hình riêng?

Bài học thuộc chương **Thiết lập JDK 25** của module **JAVA_VERSION_JAVA25**. Java 25 là một bản LTS, thích hợp để tìm hiểu các khả năng vẫn hữu ích trong Java hiện đại: chương trình nguồn gọn (*compact source files*), khai báo import module, thân hàm khởi tạo linh hoạt, `ScopedValue`, API dẫn xuất khóa, AOT cache và quan sát bằng JFR.

Tuy nhiên, **không phải mọi khả năng mới trong Java 25 đều có cùng mức ổn định**. Một số đã là thành phần chính thức của Java/JDK, một số còn đang lấy phản hồi thiết kế (*preview*), một số là API đặt trong module ươm tạo (*incubator*), và một số thử nghiệm ở tầng JVM/JFR (*experimental*). Cách bật chúng khác nhau và ảnh hưởng trực tiếp đến quy trình build, test, chạy ứng dụng và nâng cấp JDK.

Bài này tập trung vào **những cơ chế còn áp dụng với JDK 25 ở thời điểm học**. Các tên JEP và tùy chọn được ghi rõ theo phiên bản để tránh dùng hướng dẫn từ các bản JDK cũ, nhất là với các tính năng đã chính thức trong Java 25.

Sau khi học, bạn có thể:

1. Phân loại tính năng Java 25 thành **final/product**, **preview**, **incubator**, **experimental**.
2. Biên dịch và chạy mã dùng preview với đúng cặp tùy chọn `javac` và `java`.
3. Thêm module `jdk.incubator.vector` cho Vector API mà không nhầm với preview.
4. Phân biệt công tắc mở khóa JVM experimental với một JFR event mang nhãn experimental.
5. Áp dụng cấu hình có chủ đích cho Gradle, Maven, IDE, test, container và CI.
6. Nhận diện các tùy chọn lỗi thời, tránh đem vào JDK 25, đồng thời lập kế hoạch chuyển đổi khi tính năng thay đổi trạng thái ở một JDK khác.

## 2. Bản đồ trạng thái tính năng trong Java 25

Bảng sau dùng trạng thái **đúng tại JDK 25**; ở các JDK mới hơn, cần kiểm tra lại JEP/release notes thay vì sao chép nhãn cũ.

| Nhóm | Ví dụ thuộc Java 25 | Cần bật bằng gì? | Cách đánh giá |
| --- | --- | --- | --- |
| **Final / permanent** | `ScopedValue` (JEP 506), module import (JEP 511), compact source files (JEP 512), flexible constructor bodies (JEP 513), KDF API (JEP 510) | Không cần `--enable-preview` | Dùng API/ngôn ngữ Java 25 bình thường; vẫn kiểm tra phiên bản tối thiểu của môi trường chạy |
| **Preview language** | Primitive types trong pattern, `instanceof` và `switch`, lần preview thứ ba (JEP 507) | `javac --enable-preview --release 25` và `java --enable-preview` | Phụ thuộc chặt vào JDK 25; có thể đổi đặc tả ở release khác |
| **Preview API** | `StructuredTaskScope` (JEP 505, lần preview thứ năm); `StableValue` (JEP 502); PEM encoding APIs (JEP 470) | Bật preview ở compile **và** runtime khi ứng dụng dùng API này | Không coi API là contract ổn định giữa các JDK |
| **Incubator module** | Vector API lần incubator thứ mười, `jdk.incubator.vector` (JEP 508) | Giải quyết module bằng `--add-modules jdk.incubator.vector` hoặc `requires` trong named module | API có thể đổi hoặc bị rút; kiểm tra module hiện diện trong runtime image |
| **Experimental JFR** | JFR CPU-Time Profiling (JEP 509), event `jdk.CPUTimeSample` trên Linux | Bật **event JFR** trong bản ghi; không phải bật `--enable-preview` | Thử nghiệm có kiểm soát, so sánh overhead và tính khả dụng |
| **Experimental HotSpot option** | Các cờ VM cụ thể có nhãn `experimental` trong build HotSpot đang chạy | Chỉ khi cờ cụ thể yêu cầu: `-XX:+UnlockExperimentalVMOptions` trước cờ đó | Chỉ dùng trong môi trường được kiểm soát; không mặc định mở khóa toàn ứng dụng |
| **Product VM feature** | Compact Object Headers (JEP 519), Generational Shenandoah (JEP 521) | Cờ product của từng tính năng; **không cần** mở khóa experimental trong JDK 25 | Đo hiệu năng và khả năng tương thích trước khi bật ở production |

**Quy tắc nhớ nhanh:** `--enable-preview` dành cho preview language/API; `--add-modules` dành cho module cần được đưa vào graph; `-XX:+UnlockExperimentalVMOptions` dành cho **các tùy chọn HotSpot được đánh dấu experimental**. Ba cờ này **không thay thế cho nhau**.

### 2.1. Các tính năng từng preview nhưng đã chính thức trong Java 25

Không đưa `--enable-preview` vào bài hướng dẫn chỉ vì gặp những tên sau:

- `ScopedValue` — đã final tại JDK 25 (JEP 506), không còn là preview trong Java 25.
- `import module java.base;` — module import declarations đã final (JEP 511).
- Compact source files và instance `main` methods — đã final (JEP 512).
- Flexible constructor bodies — đã final (JEP 513).
- Key Derivation Function API — API chính thức (JEP 510).

Ví dụ compact source file có thể dùng trực tiếp bằng JDK 25:

~~~java
// Hello.java — không cần --enable-preview trong Java 25
void main() {
    IO.println("Xin chào từ Java 25");
}
~~~

~~~bash
java Hello.java
~~~

Cách viết gọi `IO.println` là cách đúng cho JDK 25; không dùng ví dụ cũ coi `println(...)` là phương thức được tự động import trong compact source file.

## 3. Xác nhận đang dùng đúng JDK 25

Khi có nhiều JDK trong máy, cùng một terminal có thể chạy `java` từ JDK khác với `javac`. Trước khi bật tính năng tùy chọn, xác nhận cả compiler, launcher và đường dẫn mà build tool sử dụng.

~~~bash
java -version
javac -version
java --list-modules
~~~

Kỳ vọng `java -version` và `javac -version` cùng báo 25.x. Các dòng version patch/build có thể khác theo nhà phân phối (Temurin, Oracle, Corretto, Liberica...) nhưng **major version** phải khớp.

Trên Windows PowerShell:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
java -version
javac -version
java --list-modules | Select-String "jdk.incubator.vector"
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
java -version
javac -version
java --list-modules | grep '^jdk.incubator.vector@'
~~~

Nếu `jdk.incubator.vector` không có trong `--list-modules`, hãy kiểm tra **JDK distribution/runtime image** đang chạy; một runtime image rút gọn không nhất thiết chứa module này. Không tự sửa bằng cách tải JAR `jdk.incubator.vector` từ nơi không đáng tin cậy.

**Tách hai việc:** `JAVA_HOME`/toolchain quyết định JDK nào được dùng; các tùy chọn preview/incubator/experimental quyết định khả năng nào của **JDK đã chọn** được bật.

## 4. Preview: biên dịch và chạy đều phải bật

JEP 12 quy định preview feature phải được chọn rõ ràng. Với JDK 25, cú pháp chuẩn:

~~~bash
javac --enable-preview --release 25 -d out src/PrimitiveDemo.java
java --enable-preview -cp out PrimitiveDemo
~~~

- `--release 25` chọn ngôn ngữ, thư viện và bytecode target của JDK 25.
- `--enable-preview` cho phép sử dụng đặc tả preview của **đúng release 25**.
- `-d out` tách class files khỏi source files.
- Khi chạy class file phụ thuộc preview, `java` cũng phải có `--enable-preview` và dùng JDK 25 phù hợp.

Có thể viết `javac --enable-preview --source 25 ...` thay `--release 25`, nhưng với ứng dụng thông thường nên chọn `--release 25` để compiler kiểm tra API theo đúng target. Không dùng đồng thời `--release` và `--source`/`--target`.

### 4.1. Ví dụ JEP 507: switch với selector kiểu long

Tạo `src/PrimitiveDemo.java`:

~~~java
public class PrimitiveDemo {

    static String group(long value) {
        return switch (value) {
            case long v when v < 0L -> "âm";
            case 0L -> "bằng không";
            default -> "dương";
        };
    }

    public static void main(String[] args) {
        System.out.println(group(-8L));
        System.out.println(group(0L));
        System.out.println(group(12L));
    }
}
~~~

Điểm cần bật preview là `switch` nhận selector kiểu `long` và dùng primitive type pattern `case long v` — khả năng thuộc **JEP 507** của Java 25. Các đoạn Java bình thường như `System.out.println` không đòi preview.

Chạy:

~~~bash
javac --release 25 --enable-preview -Xlint:preview -d out src/PrimitiveDemo.java
java --enable-preview -cp out PrimitiveDemo
~~~

Kết quả kỳ vọng:

~~~text
âm
bằng không
dương
~~~

`-Xlint:preview` giúp hiển thị các cảnh báo liên quan đến việc dùng preview. Tính năng đang preview vẫn có thể hữu ích để đánh giá ngôn ngữ, nhưng **không nên mặc định phát hành thư viện công cộng** chứa bytecode preview.

### 4.2. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Compiler nói preview feature bị vô hiệu | Thiếu `--enable-preview` ở `javac` | Thêm cờ compile và chọn `--release 25` |
| Compiler báo preview chỉ được dùng cho release hiện tại | Dùng JDK khác hoặc `--release` không phải phiên bản compiler | Dùng `javac` của JDK 25 và `--release 25` |
| Runtime báo class file phụ thuộc preview và không được bật | Có cờ khi compile nhưng thiếu ở `java` | Thêm `--enable-preview` cho launcher/test JVM |
| Runtime báo class file sai version hoặc minor version | Compiler và runtime dùng các JDK không khớp | Xác minh `java -version`, `javac -version` và toolchain/CI |
| IDE chạy được nhưng CI fail | IDE đã bật preview, task test/application trong CI chưa bật | Kiểm tra flags ở compile, test và JavaExec/JVM deploy |
| Code preview của JDK cũ không biên dịch với 25 | Preview API/cú pháp đã phát triển qua các phiên bản | Đọc đặc tả/JEP đúng JDK 25, cập nhật mã |

Class file thực sự dùng preview có thể mang minor version đặc biệt `65535`; vì vậy đừng suy luận rằng class file ấy sẽ chạy được trên mọi JDK mới hơn chỉ vì major version mới hơn. Preview luôn gắn với bản phát hành đã biên dịch.

### 4.3. Preview API cũng cần bật

Trong JDK 25, các API như:

~~~java
import java.lang.StableValue;                   // JEP 502 - preview
import java.util.concurrent.StructuredTaskScope; // JEP 505 - preview
import java.security.PEMDecoder;                // JEP 470 - preview
~~~

được đánh dấu preview trong Javadoc chính thức. Với mã sử dụng chúng, cấu hình compile/run cũng theo `--enable-preview` như trên; **không** tải một “preview JAR” riêng cho `java.base`.

Đặc biệt, `StructuredTaskScope` ở Java 25 là **preview lần thứ năm**, với API `StructuredTaskScope.open(...)`. Không copy ví dụ từ các lần preview trước rồi cho rằng class/method vẫn giữ nguyên. Dùng Javadoc Java 25 khi thử nghiệm; khi nâng lên JDK khác cần biên dịch/test lại theo API của release đó.

## 5. Cấu hình preview trong Gradle và Maven

Với dự án thực tế, thêm cờ vào từng lệnh thủ công sẽ dễ bị bỏ sót. Cần bảo đảm **compiler, test JVM và application JVM** đều nhận cùng chính sách.

### 5.1. Gradle Kotlin DSL — chỉ cho module cần preview

Ví dụ `build.gradle.kts` của một module học tập:

~~~kotlin
plugins {
    java
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
    options.compilerArgs.add("--enable-preview")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--enable-preview")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--enable-preview")
}
~~~

Mã cấu hình trên cần dự án có Gradle tương thích Java 25 và source Java phù hợp. Gradle Java toolchain hỗ trợ chọn JDK 25 để biên dịch/chạy task do Gradle quản lý; nó không tự thay thế JDK dùng bởi một câu lệnh `java` chạy ngoài Gradle trong container hoặc script deploy.

Các cấu hình `Test` và `JavaExec` là cần thiết vì chúng khởi chạy **JVM riêng**, không tự kế thừa `options.compilerArgs` của `JavaCompile`.

### 5.2. Maven Compiler và Surefire

Đối với project dùng Maven, trong `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>25</release>
                <enablePreview>true</enablePreview>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <argLine>--enable-preview</argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là trích đoạn cấu hình cần đặt vào một project Maven đầy đủ với phiên bản plugin đủ mới và chạy trên JDK 25. Nếu project đã có `argLine` phục vụ JaCoCo/agent khác, **phải ghép cờ preview vào argLine hiện có**, không ghi đè làm mất Java agents. Với `maven-failsafe-plugin` cho integration test, áp dụng cấu hình runtime tương tự.

Build chạy được chưa chứng minh JAR runtime chạy được. Lệnh deploy/launcher vẫn phải có:

~~~bash
java --enable-preview -jar build/app.jar
~~~

Đường dẫn JAR chỉ mang tính minh họa. Với Spring Boot, chỉnh `bootRun` hoặc cấu hình JVM của container/service tương ứng; không coi cờ Maven Surefire là cờ chạy ứng dụng production.

**Khuyến nghị:** bật preview trong module thử nghiệm hoặc ứng dụng đã chấp nhận rủi ro, không thêm `--enable-preview` mặc định cho mọi thư viện trong workspace khi chúng không cần.

## 6. Incubator module: Vector API cần module resolution

Trong JDK 25, **JEP 508 — Vector API (Tenth Incubator)** đưa API vào module `jdk.incubator.vector`. Incubator khác preview:

- Phần API nằm trong một **module JDK riêng**, thay vì là phần chuẩn của `java.base`.
- Cần đưa module vào graph của app: `--add-modules jdk.incubator.vector` hoặc khai báo `requires jdk.incubator.vector;` trong named module.
- **Không cần `--enable-preview`** chỉ vì dùng Vector API incubator.
- Compiler/launcher có thể cảnh báo “using incubating module(s)” — đó là thông báo có chủ đích.
- API có thể thay đổi giữa các JDK; cần test và đánh giá khi nâng JDK.

### 6.1. Ví dụ tính tổng hai mảng bằng Vector API

Tạo `src/VectorDemo.java`:

~~~java
import java.util.Arrays;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorDemo {

    static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static float[] add(float[] left, float[] right) {
        if (left.length != right.length) {
            throw new IllegalArgumentException("Khác độ dài");
        }

        float[] result = new float[left.length];
        int i = 0;
        int limit = SPECIES.loopBound(left.length);

        for (; i < limit; i += SPECIES.length()) {
            FloatVector a = FloatVector.fromArray(SPECIES, left, i);
            FloatVector b = FloatVector.fromArray(SPECIES, right, i);
            a.add(b).intoArray(result, i);
        }

        // Phần còn lại khi độ dài mảng không chia hết số lane.
        for (; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }

        return result;
    }

    public static void main(String[] args) {
        float[] result = add(
            new float[] {1, 2, 3, 4, 5},
            new float[] {10, 20, 30, 40, 50}
        );
        System.out.println(Arrays.toString(result));
    }
}
~~~

Biên dịch và chạy bằng **JDK 25 đầy đủ**:

~~~bash
javac --add-modules jdk.incubator.vector -d out src/VectorDemo.java
java --add-modules jdk.incubator.vector -cp out VectorDemo
~~~

Kết quả kỳ vọng (độc lập với việc phần cứng có SIMD tương ứng hay không):

~~~text
[11.0, 22.0, 33.0, 44.0, 55.0]
~~~

Chương trình vẫn nên có đường xử lý scalar cho phần mảng còn lại; hiệu quả vector hóa phụ thuộc CPU, JIT và workload. Khi benchmark cần warmup và công cụ đo thích hợp, không suy “Vector API luôn nhanh hơn” chỉ từ ví dụ một lần chạy.

### 6.2. Named module

Nếu mã nằm trong một Java module có `module-info.java`, có thể khai báo:

~~~java
module demo.vector {
    requires jdk.incubator.vector;
}
~~~

Khi build module thật, dùng `--module-path` và cách chạy `--module` tương ứng. Với chương trình không có `module-info.java`, ví dụ `--add-modules` ở mục trước là cách rõ ràng để đưa module incubator vào graph.

Đừng nhầm hai loại import:

- `import module java.base;` là **cú pháp ngôn ngữ đã final** ở Java 25 (JEP 511), không tự bật incubator.
- `requires jdk.incubator.vector;` là **module dependency** trong `module-info.java`, giải quyết API ở module incubator.

### 6.3. Gradle cho Vector API

Kotlin DSL cho source set của một module đang thử Vector API:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(25))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
    options.compilerArgs.addAll(
        listOf("--add-modules", "jdk.incubator.vector")
    )
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules=jdk.incubator.vector")
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--add-modules=jdk.incubator.vector")
}
~~~

Đối với **các named module**, `requires` và cấu hình module path có thể đã giải quyết module; hãy chọn cấu hình phù hợp để tránh thêm cờ trùng vô ích. Nếu ứng dụng đồng thời dùng preview và incubator, có thể cần **cả hai** nhóm cờ, vì chúng xử lý hai cơ chế khác nhau.

Đối với image tạo bằng `jlink`, cần xác minh image có chứa `jdk.incubator.vector` nếu ứng dụng phụ thuộc vào nó. Không chỉ thử trên JDK đầy đủ ở máy phát triển rồi giả định runtime tối giản có cùng module.

## 7. Experimental: hiểu rõ đối tượng được đánh dấu thử nghiệm

Từ “experimental” có thể áp dụng cho **tùy chọn HotSpot** hoặc **một event JFR**. Hai cơ chế không giống nhau.

### 7.1. Cờ HotSpot experimental

Với một VM option có nhãn `experimental`, HotSpot có thể từ chối sử dụng trừ khi mở khóa trước:

~~~bash
java -XX:+UnlockExperimentalVMOptions <VM-option-specific> -jar app.jar
~~~

`<VM-option-specific>` chỉ là **placeholder**: phải thay bằng tên cờ thực sự có trong build HotSpot đang dùng, đã kiểm tra tài liệu và rủi ro cụ thể. **Không copy cả dòng nguyên dạng để chạy.**

Để kiểm tra danh mục cờ (và version VM) trong một môi trường được phép thử:

~~~bash
java -XX:+UnlockExperimentalVMOptions -XX:+PrintFlagsFinal -version
~~~

Đầu ra dài, có thể lọc theo **tên cờ đã biết**; không bật thử các cờ không rõ tác dụng. Không dùng `UnlockExperimentalVMOptions` chỉ vì muốn cấu hình `--enable-preview` hoặc `--add-modules` — chúng là các cơ chế độc lập.

Nhớ phân biệt `-XX:+UnlockDiagnosticVMOptions` (nhóm diagnostic) và `-XX:+UnlockExperimentalVMOptions` (nhóm experimental). Cả hai đều là lựa chọn nâng cao của HotSpot, không phải API ổn định dành cho nghiệp vụ.

### 7.2. JFR CPU-Time Profiling trong JDK 25

**JEP 509 — JFR CPU-Time Profiling (Experimental)** đưa event `jdk.CPUTimeSample` vào JDK 25 nhằm quan sát thời gian CPU chính xác hơn trên **Linux**, kể cả trường hợp thread chạy mã native. Event **không bật mặc định**.

Một ví dụ ghi JFR khi chạy chương trình:

~~~bash
java -XX:StartFlightRecording=jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr \
     -cp out CpuWorkload
~~~

Sau khi chương trình kết thúc hoặc recording được dump, dùng `jfr` của JDK 25 để phân tích:

~~~bash
jfr summary cpu-time.jfr
jfr view cpu-time-hot-methods cpu-time.jfr
~~~

`CpuWorkload` là tên chương trình mẫu cần chuẩn bị; trên Windows lệnh nhiều dòng với dấu `\` như trên không dùng nguyên dạng, nhưng tính năng thử nghiệm CPU-time profiling này vốn nhắm **Linux**. Cấu hình và chi phí sampling cần được đo riêng trên môi trường Linux mục tiêu.

**Điểm khác biệt rất quan trọng:** dù `jdk.CPUTimeSample` mang nhãn experimental, tài liệu JDK 25 không yêu cầu đặt `-XX:+UnlockExperimentalVMOptions` để bật event JFR này. Bạn bật **event JFR** bằng cấu hình recording. Không suy rằng mọi thứ được ghi “Experimental” đều phải đi qua HotSpot experimental option unlock.

### 7.3. Compact Object Headers đã là product option trong Java 25

JDK 24 từng yêu cầu cách bật experimental cho compact object headers. Từ **JDK 25, JEP 519** đưa tính năng này sang **product feature**. Cách bật ở JDK 25:

~~~bash
java -XX:+UseCompactObjectHeaders -jar app.jar
~~~

**Không cần `-XX:+UnlockExperimentalVMOptions` cho cờ này trong JDK 25.** Mặc định JDK 25 vẫn chưa bật compact headers. Hãy đo hiệu năng, heap, GC và tương thích trước khi áp dụng vào production.

Tương tự, Generational Shenandoah là tính năng product của JDK 25 (JEP 521), có cấu hình GC riêng, không nên mang hướng dẫn experimental của các bản JDK trước sang nguyên xi. Đây là minh họa cho nguyên tắc **kiểm tra trạng thái tính năng ở JDK đang chạy**, không phải một yêu cầu phải bật GC mới cho mọi ứng dụng.

## 8. Quản trị cấu hình trên IDE, test, CI và container

### 8.1. Tách rõ thời điểm và tiến trình nhận cờ

~~~mermaid
flowchart LR
    S["Source Java 25"] --> C["javac (compiler flags)"]
    C --> B["Class files / JAR"]
    B --> T["Test JVM (test flags)"]
    B --> A["App JVM (runtime flags)"]
    A --> O["JFR / metrics / logs"]
    T --> R["Test result"]
~~~

Không phải mọi công cụ tự chia sẻ cùng cờ:

| Bước | Preview | Incubator | Experimental |
| --- | --- | --- | --- |
| `javac` | `--enable-preview --release 25` | `--add-modules jdk.incubator.vector` hoặc `requires` trong module | Không bật HotSpot VM option chỉ để biên dịch |
| `java` khi chạy | `--enable-preview` | `--add-modules jdk.incubator.vector` khi cần | Chỉ cờ JVM cụ thể theo tài liệu của VM |
| JUnit/Surefire/Gradle Test | JVM của test phải có `--enable-preview` nếu dùng preview | JVM test phải resolve incubator module | Bật event/flag chỉ khi test thực sự yêu cầu |
| IDE Run/Debug | Chọn JDK 25 và thêm VM option | Chọn module path/VM option đúng | Tách riêng run configuration thử nghiệm |
| Docker/Kubernetes | Đảm bảo image JDK/JRE là 25 và entrypoint có cờ | Đảm bảo runtime image chứa incubator | Không đẩy cờ thử nghiệm vào deployment mặc định |
| CI/CD | Build và test trên cùng JDK 25 | Kiểm tra module có mặt | Chạy job/benchmark riêng, lưu thông tin VM, OS và flags |

**Không nhầm với `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`:** hai biến này có thể ảnh hưởng nhiều tiến trình Java và làm khó truy nguyên. Với bài thực hành, ưu tiên cấu hình tường minh tại đúng task hoặc entrypoint và ghi lại lệnh chạy trong log CI. Đừng set `--enable-preview` toàn máy chỉ để một module thử nghiệm hoạt động.

### 8.2. Các trường hợp cần đặc biệt chú ý

- **IDE:** Language level chọn 25 và Project SDK chọn JDK 25. Cấu hình compiler preview phải khớp Run/Debug VM options.
- **Gradle:** Toolchain JDK 25 quyết định JDK cho compile/test/JavaExec theo task; Java chạy ngoài Gradle vẫn phải được kiểm tra riêng. Kiểm tra bản Gradle tương thích với JDK 25.
- **Maven:** Maven chạy bằng một JDK, `maven-toolchains-plugin` có thể chọn JDK khác để biên dịch; `mvn -version` và cấu hình compiler/test cần được đối chiếu. Không để Surefire chạy JVM thiếu preview flag.
- **Spring Boot:** Khi đóng gói fat JAR, `java --enable-preview -jar app.jar` cần đúng version. `bootRun` cũng phải được cấu hình nếu source có preview.
- **Native image / AOT:** Không giả định các JVM flag, module incubator hoặc API preview của HotSpot sẽ hoạt động giống nhau trên GraalVM Native Image. Kiểm tra tài liệu cụ thể của công cụ.
- **jlink/jpackage:** Nếu tạo runtime image rút gọn, bảo đảm có đủ module phục vụ ứng dụng, đặc biệt là incubator `jdk.incubator.vector`.
- **Bảo mật:** Không dùng các cờ như `--add-opens` hoặc `--add-exports` để che lỗi thiếu preview/module một cách tùy tiện; chúng liên quan đến encapsulation nội bộ, là vấn đề khác.

### 8.3. Liên hệ với các tính năng Java 25 đã ổn định

`ScopedValue` đã final trong JDK 25 và được thiết kế để truyền dữ liệu theo phạm vi thực thi, đặc biệt có giá trị khi làm việc với virtual threads và structured concurrency. Bản thân `ScopedValue` không cần preview, nhưng **API Structured Concurrency trong JDK 25 vẫn là preview**, vì vậy chương trình kết hợp cả hai vẫn cần cờ preview nếu dùng `StructuredTaskScope`.

AOT cache và JFR là các cơ chế quan sát/tối ưu runtime riêng. **Không gắn `--enable-preview` cho AOT cache** chỉ vì đây là một cải tiến đáng chú ý của Java 25. Các cờ AOT từ JEP 514/515 cần được đọc theo tài liệu lệnh `java` JDK 25 và xác minh bằng benchmark.

API dẫn xuất khóa (KDF, JEP 510) là API chính thức, không phải incubator và không cần `--add-modules jdk.incubator.vector`. Các cơ chế này có thể đồng thời xuất hiện trong cùng ứng dụng nhưng phải được cấu hình theo vai trò thực tế.

## 9. Ma trận chẩn đoán nhanh

| Lỗi / cảnh báo | Nguyên nhân thường gặp | Cách xác minh / sửa |
| --- | --- | --- |
| `preview features are disabled by default` | Compiler chưa bật preview | `javac --release 25 --enable-preview ...` |
| `UnsupportedClassVersionError` có nhắc preview | Runtime thiếu preview hoặc không dùng JDK 25 phù hợp | Kiểm tra `java -version`, thêm `--enable-preview` ở launcher |
| `invalid source release: 25` | `javac` không phải JDK 25 hoặc cao hơn | Chọn đúng toolchain/JAVA_HOME/PATH |
| `package jdk.incubator.vector is not visible` | Module chưa được resolve | `--add-modules jdk.incubator.vector` khi compile |
| `Module jdk.incubator.vector not found` | Runtime image/JDK thiếu module | `java --list-modules`, đổi image hoặc cấu hình jlink |
| `WARNING: Using incubator modules` | Incubator đã được resolve | Đây là cảnh báo dự kiến; theo dõi JEP khi nâng JDK |
| `VM option ... is experimental and must be enabled via -XX:+UnlockExperimentalVMOptions` | Cờ HotSpot experimental chưa mở khóa | Chỉ thêm unlock nếu cờ có chủ đích và được kiểm chứng |
| `Unrecognized VM option` | Cờ không tồn tại ở build/JDK đang chạy, hoặc bị xóa | Xem tài liệu lệnh `java` đúng JDK 25, ngừng dùng cờ cũ |
| Không có `jdk.CPUTimeSample` trong JFR | Chưa bật event, chạy ngoài Linux, JFR chưa có dữ liệu hoặc build không hỗ trợ | Xem OS, recording config, `jfr summary` |
| Ứng dụng chạy nhưng CI fail | Test JVM khác JDK, thiếu runtime flags | So toolchain, Surefire/Gradle test settings, container entrypoint |
| Compact object headers vẫn đòi unlock theo bài cũ | Đang dùng hướng dẫn JDK 24 | Ở JDK 25 dùng `-XX:+UseCompactObjectHeaders` không cần unlock |
| Flag preview làm runtime cũ fail | Đang cố chạy bytecode preview Java 25 trên JDK khác | Pin Java 25 cho build/runtime hoặc bỏ preview API |

Không “chữa” lỗi module thiếu bằng cách tắt Java module system. Cần xác định application đang dùng class path hay module path và module cần thiết có trong runtime image không.

## 10. Bài thực hành tổng hợp

**Tình huống:** nhóm phát triển muốn thử primitive pattern trong `switch` và Vector API trên Java 25, đồng thời đo CPU của một workload trên Linux. Yêu cầu là giữ ứng dụng production thông thường ổn định.

Thực hiện theo ba nhánh cấu hình độc lập:

### Nhánh A — Preview language

1. Chọn `java` và `javac` JDK 25.
2. Viết `PrimitiveDemo.java` ở mục 4.
3. Biên dịch với `--release 25 --enable-preview`; chạy với `--enable-preview`.
4. Bỏ riêng cờ khi compile và khi run để quan sát hai lỗi khác nhau.
5. Đưa cờ vào task test/JavaExec của một module thử nghiệm, không bật cho toàn workspace.

**Đạt** khi chương trình in ba nhóm giá trị đúng, compiler/runtime cùng là JDK 25 và test JVM chạy được không cần cài thêm JAR lạ.

### Nhánh B — Incubator Vector API

1. Kiểm tra `java --list-modules` có `jdk.incubator.vector`.
2. Tạo `VectorDemo.java` như mục 6.
3. Biên dịch/chạy bằng `--add-modules jdk.incubator.vector`, không cần `--enable-preview`.
4. Quan sát cảnh báo incubator và so kết quả mảng với phép cộng scalar.
5. Thử runtime image tối giản chỉ khi đã kiểm tra module được đóng gói.

**Đạt** khi kết quả mảng là `[11.0, 22.0, 33.0, 44.0, 55.0]` và có thể giải thích vì sao không cần cờ preview.

### Nhánh C — Experimental JFR

1. Trên Linux với JDK 25, tạo một workload CPU phù hợp (ví dụ vòng tính toán có thời gian chạy đủ dài).
2. Bật JFR recording với `jdk.CPUTimeSample#enabled=true`.
3. Đọc `jfr summary` và báo cáo CPU time hotspots bằng `jfr view cpu-time-hot-methods`.
4. So sánh với JFR profile thông thường và ghi lại sampling/overhead.
5. Giải thích vì sao không cần `UnlockExperimentalVMOptions` để bật event JFR này.

**Đạt** khi recording có dữ liệu phù hợp, người học phân biệt được experimental **event** với experimental **VM option**, và không mang cờ thử nghiệm vào production ngoài quyết định đã được đánh giá.

### Bảng tổng hợp bằng chứng

| Nhánh | Compile cần | Runtime cần | Bằng chứng |
| --- | --- | --- | --- |
| Preview `PrimitiveDemo` | `--release 25 --enable-preview` | `--enable-preview` | Output ba dòng, compiler/runtime cùng JDK 25 |
| Incubator `VectorDemo` | `--add-modules jdk.incubator.vector` | `--add-modules jdk.incubator.vector` | Cảnh báo incubator và output mảng đúng |
| JFR CPU sample | Không có compile flag đặc biệt | JFR recording bật `jdk.CPUTimeSample` trên Linux | `cpu-time.jfr` và kết quả `jfr view` |
| Compact object headers (tùy chọn) | Không có compile flag | `-XX:+UseCompactObjectHeaders` | Số đo heap/GC/latency để đánh giá trước và sau |

## 11. Khi nào nên sử dụng trong dự án thật?

**Preview:** phù hợp cho thử nghiệm tính năng ngôn ngữ/API hoặc ứng dụng đã chấp nhận ràng buộc JDK 25. Cần có test, kế hoạch sửa code khi đổi JDK và phải tránh phát hành library preview làm SDK công cộng nếu không có hợp đồng tương thích rõ ràng.

**Incubator:** phù hợp khi ứng dụng có lợi ích đáng đo từ Vector API và đội phát triển chấp nhận thay đổi module/API qua các JDK. Cần benchmark thực, kiểm tra CPU và runtime image.

**Experimental:** phù hợp để quan sát/tối ưu trong lab hoặc môi trường đo có kiểm soát. Chỉ bật từng cờ/event đã được xác minh. Luôn có baseline và phương án tắt. Experimental không phải là mức ổn định mặc định của production.

**Final/product:** ưu tiên khi đáp ứng bài toán. Với Java 25, dùng `ScopedValue`, module import, compact source files, flexible constructor bodies hoặc KDF API mà **không gắn nhãn preview cũ**. Tính năng product như compact object headers vẫn là lựa chọn cấu hình cần đo lường hiệu quả chứ không bắt buộc bật.

Khi nâng JDK lên bản khác, hãy đối chiếu lại trạng thái của từng JEP. Ví dụ API primitive patterns có thể tiếp tục được preview với các thay đổi trong các release sau JDK 25; **code dùng preview không có bảo đảm tương thích nhị phân hoặc nguồn mã qua các phiên bản**. Kiến thức bền vững là **cách phân loại và cấu hình đúng theo release**, không phải thuộc lòng các cờ của một bản cũ.

## 12. Câu hỏi tự đánh giá

1. Tại sao `ScopedValue` không cần `--enable-preview` trong Java 25, nhưng `StructuredTaskScope` cần?
2. `--release 25` và `--enable-preview` giải quyết hai vấn đề khác nhau như thế nào?
3. Vì sao phải thêm `--enable-preview` cho cả `javac` và `java` nếu ứng dụng dùng preview?
4. Một class file preview được biên dịch trên JDK 25 có được bảo đảm chạy trên JDK 26/27 không? Vì sao?
5. Khi dùng `jdk.incubator.vector`, vì sao `--add-modules` là cờ thích hợp hơn `--enable-preview`?
6. Nếu `VectorDemo` chạy trên JDK 25 đầy đủ nhưng thất bại trên image `jlink`, cần kiểm tra điều gì?
7. Sự khác nhau giữa experimental HotSpot flag và experimental JFR event là gì?
8. Vì sao dùng `-XX:+UnlockExperimentalVMOptions` cho `UseCompactObjectHeaders` trên Java 25 là cách làm thừa?
9. Những tiến trình nào trong Gradle/Maven/CI cần nhận cờ preview riêng?
10. Tại sao không nên bật `--enable-preview` toàn bộ workspace chỉ vì một module thử nghiệm dùng JEP 507?
11. Khi dùng cả API chính thức KDF, Vector API incubator và JFR CPU profiling, tính năng nào yêu cầu cơ chế mở khóa nào?
12. Những bằng chứng nào cần lưu lại trước khi đưa một tùy chọn JVM experimental vào môi trường vận hành?

## 13. Tài liệu tham khảo chính thức và thực hành

- [Oracle Java SE 25 — Preview Language and VM Features](https://docs.oracle.com/en/java/javase/25/language/preview-language-vm-features.html): nguyên tắc compile/run cùng `--enable-preview`.
- [Oracle Java SE 25 — Preview API List](https://docs.oracle.com/en/java/javase/25/docs/api/preview-list.html): danh sách API `StableValue`, `StructuredTaskScope` và `PEMDecoder`.
- [Oracle Java SE 25 — Type Patterns with Primitive Types](https://docs.oracle.com/en/java/javase/25/language/type-patterns.html): ví dụ JEP 507.
- [Oracle JDK 25 — javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `--enable-preview` và `--add-modules`.
- [Oracle JDK 25 — java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): launcher, module options và HotSpot experimental flags.
- [Oracle — Significant Changes in JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): trạng thái các JEP 470/502/505/507/508/509, JEP 519 và nhiều tính năng final.
- [Oracle — JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): các thay đổi sản phẩm và công cụ.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): cấu hình preview cho JavaCompile, Test và JavaExec.
- [OpenJDK JEP 12 — Preview Features](https://openjdk.org/jeps/12): vòng đời và giới hạn tương thích.
- [OpenJDK JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508): trạng thái incubator trong Java 25.
- [OpenJDK JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): cơ chế CPU-time sampling trên Linux.
- [OpenJDK JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): product option trong JDK 25.

