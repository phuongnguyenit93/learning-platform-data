# Sử dụng cơ chế up-to-date và biên dịch tăng dần của Gradle

## Mục tiêu

Trong dự án Spring Boot, mỗi lần thay một vài dòng Java hoặc một file `application.properties`, ta không muốn Gradle biên dịch lại tất cả mã nguồn, chạy mọi bước không cần thiết hoặc đóng gói lại một JAR giống hệt bản cũ. Gradle cung cấp các cơ chế **work avoidance** và **incremental execution** để rút ngắn chu trình chỉnh sửa → kiểm tra → chạy.

Bài học tập trung vào hai cơ chế chính:

- **Up-to-date checking:** Gradle **bỏ qua toàn bộ task** khi đầu vào, đầu ra và trạng thái thực thi liên quan chưa đổi kể từ lần chạy thành công.
- **Incremental Java compilation:** khi `compileJava` **thật sự cần thực thi**, Gradle có thể chọn biên dịch **chỉ các Java class bị ảnh hưởng**, thay vì compile toàn bộ source set.

Những khái niệm liên quan nhưng khác nhau gồm **compilation avoidance** (tránh compile lại module phụ thuộc khi ABI không đổi), **build cache** (khôi phục output task có cache key tương đương), **configuration cache** (khôi phục cấu hình/task graph) và **dependency cache** (tái sử dụng thư viện tải về).

Sau bài này, bạn sẽ:

1. Đọc đúng các trạng thái `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` và task chạy bình thường.
2. Giải thích Gradle dùng input/output fingerprint, classpath, task implementation và execution history để quyết định chạy task.
3. Dựng một ứng dụng Spring Boot Java 17+, build hai lần, thay đổi Java/resource có kiểm soát và giải thích kết quả `compileJava`/`processResources`/`test`/`bootJar`.
4. So sánh sửa **thân phương thức** với sửa **API/ABI công khai**, cũng như ảnh hưởng của annotation processor.
5. Khai báo đầu vào/đầu ra đầy đủ cho custom task và giá trị dùng khi resource filtering.
6. Đo hiệu quả tăng dần bằng log `--info` mà không nhầm lẫn với `clean`, `--rerun-tasks` hoặc bỏ qua test.
7. Khắc phục những build luôn chạy lại hoặc báo up-to-date sai, giữ đúng nội dung artifact phát hành.

**Bối cảnh ví dụ:** Spring Boot **3.3.13**, Java **17**, Gradle **8.x** tương thích, chủ yếu Groovy DSL. Các tính năng được đối chiếu với tài liệu Gradle Java Plugin/Incremental Build chính thức; cú pháp cụ thể cần kiểm tra với đúng Gradle Wrapper của dự án. Đây là bài thực hành, không yêu cầu thay phiên bản hoặc chỉnh sửa repository đang chạy production.

---

## 1. Bốn câu hỏi khác nhau trong một lần build

Một project có thể có các task:

```text
src/main/java/*.java --> compileJava ------------> build/classes/java/main/
src/main/resources/  --> processResources -------> build/resources/main/
                                  \                  /
                                   +--- classes ----+
                                            |
                                            +-- bootJar --> build/libs/*-SNAPSHOT.jar

src/test/java/      --> compileTestJava
src/test/resources/ --> processTestResources
                                  |
                                  v
                                 test
                                  |
                                  v
                                 check

                         assemble + check --> build
```

Đây là **sơ đồ khái niệm**: task graph thực phụ thuộc plugins và cấu hình. `bootJar` được Spring Boot Gradle plugin bổ sung khi có Java plugin; `compileJava` và `processResources` đến từ Gradle Java plugin.

Khi nhìn một dòng task trong console, hãy hỏi:

1. **Task có được chọn vào graph không?** Ví dụ chạy `classes` khác chạy `build`.
2. **Task có thực thi actions không?** `UP-TO-DATE` nghĩa là không cần làm lại.
3. **Nếu có thực thi, nó xử lý toàn bộ hay tăng dần?** `compileJava` có thể chạy incremental.
4. **Nếu không thực thi, output đến từ đâu?** Local execution history khác build cache.

Ví dụ chạy:

```bash
./gradlew build --console=plain --info
```

Lần đầu thường phải thực thi nhiều task; lần thứ hai nếu không đổi source/resources/config, Gradle có thể skip nhiều task. Nhưng khi sửa một Java file, `compileJava` **không còn up-to-date**, song compiler vẫn có thể biên dịch một phần rất nhỏ. Đây là mục tiêu tối ưu chính.

## 2. Đọc đúng outcome của task

| Nhãn console | Định nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `UP-TO-DATE` | Task không thực thi vì Gradle xác định outputs hiện có còn hợp lệ với inputs/history. | Không phải "compiler chạy tăng dần"; task đã được bỏ qua. |
| `FROM-CACHE` | Gradle lấy task outputs từ build cache thay vì thực thi actions. | Không nhất thiết có history local từ lượt trước. |
| `NO-SOURCE` | Task nguồn không có file phù hợp để xử lý. | Không phải task đã dịch một source rồi skip vì không đổi. |
| `SKIPPED` | Task bị bỏ qua do điều kiện như `onlyIf` hoặc loại khỏi graph bằng cách khác. | Không đồng nghĩa test đã chạy/đã pass. |
| Không có nhãn | Task được thực thi. | Không đồng nghĩa full recompilation; có thể incremental. |
| `FAILED` | Task lỗi. | Phải đọc nguyên nhân thật, không gán ngay cho cơ chế caching. |

Ví dụ đầu ra **minh họa, không phải log thực tế**:

```text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :bootJar UP-TO-DATE
> Task :test UP-TO-DATE
BUILD SUCCESSFUL
```

Không yêu cầu mọi Gradle version/plugin đều tạo đúng những dòng này. `processResources` có thể `NO-SOURCE` nếu không có file nguồn; một lifecycle task có thể không có actions. Tập task được hiển thị còn thay đổi khi bạn gọi `bootJar` thay cho `build`.

**Điểm phân biệt thiết yếu:**

- `compileJava UP-TO-DATE` → **không biên dịch class nào**.
- `compileJava` chạy vì một file `.java` đổi → **có thể** chỉ biên dịch class bị ảnh hưởng.
- `compileJava FROM-CACHE` → output được **khôi phục**, không cần compiler thực thi.
- `compileJava SKIPPED` → bị bỏ qua bởi điều kiện khác, không đủ cơ sở kết luận output mới nhất.

## 3. Up-to-date checking: đầu vào, đầu ra và lịch sử

### 3.1 Cách hoạt động

Mỗi task đáng tối ưu có các thông tin:

- **Inputs:** file nguồn, dependency classpath, task option, giá trị cấu hình có ảnh hưởng đến output.
- **Outputs:** file/thư mục mà task tạo hoặc cập nhật.
- **Task implementation:** logic của task và classpath chứa implementation/plugin.
- **Execution history:** fingerprints của input/output sau lượt chạy thành công trước đó.

Với `compileJava`, inputs có thể gồm `.java`, compile classpath, Java toolchain và compiler flags. Outputs gồm `.class` và dữ liệu build có liên quan. Gradle fingerprint các input/output; lần sau nếu phù hợp, task có thể được đánh dấu `UP-TO-DATE` và bỏ qua actions.

```text
Lần 1: Java source A.java, B.java + compile classpath X
        --> compileJava thực thi --> A.class, B.class
        --> Gradle ghi fingerprints

Lần 2: input/output giữ nguyên
        --> compileJava UP-TO-DATE, không gọi javac

Lần 3: B.java đổi
        --> compileJava phải thực thi
        --> incremental compiler xét class nào bị ảnh hưởng

Lần 4: code không đổi, compile classpath thay đổi
        --> có thể khiến compilation task cần chạy
```

Khi **output bị xóa hoặc sửa từ ngoài**, Gradle có thể cần chạy lại vì output fingerprint không còn hợp lệ. Tuy nhiên, nếu output có trong build cache và cache bật, nó có thể được khôi phục `FROM-CACHE` mà không chạy compiler.

Không nên giả lập thay đổi bằng cách sửa byte tệp rồi cố tình giữ nguyên cả `lastModified` và file size: Gradle có thể tận dụng metadata file để tối ưu hashing. Hãy thực hiện các chỉnh sửa thường gặp, kiểm tra nội dung và logs.

### 3.2 Input không được khai báo: lỗi thường gặp

Giả sử task sinh `build-info.properties` từ biến môi trường `BUILD_LABEL` nhưng chỉ khai báo một file nguồn, không khai báo giá trị môi trường. Khi `BUILD_LABEL` thay, Gradle có thể cho rằng task vẫn `UP-TO-DATE` và giữ output cũ.

**Sửa:** khai báo giá trị đó làm task input, ví dụ `inputs.property('buildLabel', ...)` hoặc property có annotation `@Input` trong custom task type. Nếu output không được khai báo, Gradle cũng không có cơ sở đầy đủ để up-to-date/cache task.

**Không lạm dụng input:** nếu đặt timestamp hiện tại hoặc random value làm input dù output không cần, task sẽ bị invalidated mỗi lần. Mỗi input nên có quan hệ thật tới output.

### 3.3 Output directory, file đích và task phụ thuộc

Gradle theo dõi declared task outputs và có thể suy ra một số task dependencies khi task khác tiêu thụ output qua provider/task object. Nếu một custom task ghi đè `build/classes/java/main` mà không khai báo quan hệ với `compileJava`, có thể tạo race condition và corrupted up-to-date state.

Trong build đúng:

- Một task nên **sở hữu output của nó**.
- Task tiêu thụ output của task khác nên dùng TaskProvider/Provider hoặc `dependsOn` hợp lý.
- Không để hai task tùy biến ghi cùng một đường dẫn mà không có thiết kế rõ ràng.
- Đừng sửa file trong `build/libs` sau `bootJar` rồi cho rằng Gradle vẫn biết artifact đã hợp lệ.

Phép tối ưu phải bảo đảm **tính đúng đắn của sản phẩm trước**.

## 4. Incremental Java compilation và ABI

### 4.1 Incremental compile khác task skip

JavaCompile trong Gradle hiện đại có **incremental compilation bật mặc định**. Khi task cần chạy, Gradle phân tích những class bị ảnh hưởng bởi thay đổi của mã/ABI.

Ví dụ:

```text
DemoApplication  ----uses----> Calculator
Unrelated           (không dùng Calculator)
```

Nếu chỉ thay **thân phương thức** trong `Calculator` nhưng chữ ký và API công khai không đổi, compiler có thể tránh biên dịch `DemoApplication` hoặc `Unrelated`. Nếu thay API công khai, consumer có thể bị ảnh hưởng.

Nói "**biên dịch tăng dần**" không có nghĩa "**đúng một tệp class được biên dịch**": một source file có thể tạo nhiều class files, inner classes, generated code; annotation processor và thay đổi classpath có thể mở rộng phạm vi.

### 4.2 Thân method vs API/ABI

Ví dụ trước:

```java
public int add(int left, int right) {
    return left + right;
}
```

Đổi phần thân nhưng giữ signature:

```java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
```

Trong nhiều trường hợp đây là thay đổi **không ảnh hưởng ABI**, vì consumer vẫn gọi `int add(int,int)`. `Calculator.java` đã đổi nên `compileJava` có thể cần thực thi, nhưng không phải mọi consumer đều cần biên dịch.

Đổi signature:

```java
public long add(int left, int right) {
    return (long) left + right;
}
```

Kiểu trả về công khai đổi từ `int` sang `long`, là thay đổi ABI. Consumer phải được kiểm tra/biên dịch theo chữ ký mới. Một số thay đổi public method có thể làm compilation error nếu call site không tương thích; ví dụ đổi tên `add` thành `sum` mà không sửa caller.

**ABI** bao gồm nhiều thông tin ngoài "có public hay không": signature accessible, superclass/interfaces, constants có thể được inline, các thành phần mà consumer cần để liên kết ở compile time. Quy tắc cụ thể còn tùy bytecode và compiler.

### 4.3 Compile avoidance giữa các project

Trong Gradle multi-project:

```text
:core:compileJava  --> :core:jar
                            |
                            v
                   :app:compileJava --> :app:bootJar
```

Nếu implementation module `:core` đổi nhưng ABI không đổi, `:app:compileJava` **có thể vẫn UP-TO-DATE** nhờ compile avoidance. Tuy nhiên, `:app:bootJar` **có thể phải chạy lại** vì runtime JAR của `:core` có byte mới cần đưa vào executable Spring Boot archive.

Vì vậy:

> "Không compile lại app" **không có nghĩa** "không đóng gói lại app".

Nếu `:core` thay public interface hoặc compile classpath ABI, consumer compile task có thể cần chạy lại. Đây là lý do Gradle `java-library` với `api` và `implementation` giúp giữ ranh giới giữa public API và dependency nội bộ, giảm invalidation không cần thiết.

### 4.4 Khi incremental compilation không còn hẹp

Những trường hợp cần điều tra:

- Public ABI đổi theo cách ảnh hưởng consumer.
- Compile-time constants như `public static final int LIMIT = 10` được inline vào class consumer; thay constant có thể khiến Gradle phải recompile rộng hơn.
- Annotation processor không incremental, hoặc processor đọc input không khai báo.
- Source-retention annotation khó được suy từ bytecode.
- Compiler flags, Java toolchain hoặc classpath thay đổi lớn.
- Lần compile trước thất bại, chưa có lịch sử phù hợp hoặc compile state mới bị xóa.
- Dùng custom `javaHome`/`executable` thay vì Java toolchains làm một số tối ưu khó áp dụng.
- Mã nguồn/package layout bất thường hoặc plugin khác biến đổi compiler inputs.

Không nên thấy full recompilation rồi ngay lập tức viết `options.incremental=true` vào mọi task; Gradle JavaCompile hiện đại đã hỗ trợ mặc định. Hãy đọc `--info` để xác định **nguyên nhân thực**.

## 5. Dự án Spring Boot Java 17+ thực hành được

### 5.1 Cấu trúc

```text
gradle-incremental-demo/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat                 (nếu đã tạo Wrapper)
├── gradle/wrapper/...
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── Calculator.java
    │   │   └── Unrelated.java
    │   └── resources/build-info.properties
    └── test/java/com/example/demo/CalculatorTest.java
```

Dùng một project **lab**, không cần thêm module khác để bắt đầu. Nếu project chưa có Wrapper, có thể tạo bằng Gradle tương thích: `gradle wrapper --gradle-version 8.5`. Các lệnh `./gradlew` sau đây chỉ chạy nếu Wrapper đã có; trên Windows PowerShell dùng `.\gradlew.bat`.

### 5.2 `settings.gradle`

```groovy
rootProject.name = 'gradle-incremental-demo'
```

### 5.3 `build.gradle` đầy đủ (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `java` cung cấp `compileJava`, `processResources`, `classes`, `test` và task archive thường.
- `org.springframework.boot` kết hợp Java tạo `bootJar`/`bootRun`.
- `io.spring.dependency-management` import BOM được Spring Boot plugin hỗ trợ; nó **không phải** cơ chế biên dịch tăng dần.
- Java toolchain hướng Gradle dùng Java 17 thích hợp cho compilation/test; JDK chạy Gradle daemon và compiler toolchain có thể khác nhau.
- `test` được cấu hình JUnit Platform.

Không cần ép `options.incremental=true`; dùng default của Gradle Java plugin để làm bài.

### 5.4 `Calculator.java`

Đường dẫn `src/main/java/com/example/demo/Calculator.java`:

```java
package com.example.demo;

public final class Calculator {

    public int add(int left, int right) {
        return left + right;
    }
}
```

Đây là mã Java thuần, không phụ thuộc Spring. Lớp `DemoApplication` bên dưới sử dụng nó.

### 5.5 `DemoApplication.java`

Đường dẫn `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
        System.out.println("SUM=" + new Calculator().add(2, 3));
    }
}
```

Project có một main class nên `bootJar` có thể xác định startup class trong cấu hình chuẩn. Sau `java -jar` trên Boot JAR hợp lệ, ứng dụng in dòng do chính mã tạo:

```text
SUM=5
```

Ngoài dòng đó còn có thể có banner/log của Spring Boot. Không gọi `javac DemoApplication.java` độc lập khi chưa cấp Spring Boot dependencies; hãy dùng Gradle.

### 5.6 `Unrelated.java`

```java
package com.example.demo;

public final class Unrelated {

    public String message() {
        return "unrelated";
    }
}
```

Lớp này không tham chiếu `Calculator`, giúp minh họa incremental compiler có thể tránh tác động tới những class không liên quan.

### 5.7 `CalculatorTest.java`

Đường dẫn `src/test/java/com/example/demo/CalculatorTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void addsTwoIntegers() {
        assertEquals(5, new Calculator().add(2, 3));
    }
}
```

Test JUnit 5 kiểm tra kết quả. `./gradlew test` chạy test bằng cấu hình Gradle ở trên; **test pass không chứng minh JAR executable đã đúng**, cần build và kiểm tra artifact riêng.

### 5.8 `build-info.properties`

Đường dẫn `src/main/resources/build-info.properties`:

```properties
app.label=demo
```

Đây là tài nguyên đơn giản để quan sát `processResources`. Chưa có filtering; Gradle mặc định copy sang `build/resources/main/build-info.properties`.

## 6. Thực nghiệm 1 – Hai lượt build không đổi input

Chạy trên macOS/Linux:

```bash
./gradlew --version
./gradlew build --console=plain --info
./gradlew build --console=plain --info
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat build --console=plain --info
.\gradlew.bat build --console=plain --info
```

**Cách đo đúng:**

1. Lượt đầu có thể chạy `compileJava`, `processResources`, `compileTestJava`, `test` và `bootJar`.
2. Không sửa source, resources, Gradle script, dependency hoặc cấu hình môi trường giữa hai lượt.
3. Lượt hai thường có các task `UP-TO-DATE` nếu outputs còn nguyên và execution history hợp lệ.
4. Nếu task nào vẫn chạy, đọc dòng giải thích với `--info`, không mặc định Gradle bị lỗi.
5. Ghi Gradle/JDK version, command, outcome, thời gian nếu cần benchmark.

Có thể lưu log trên workspace thực hành:

```bash
./gradlew build --console=plain --info > first-build.log 2>&1
./gradlew build --console=plain --info > second-build.log 2>&1
```

Những file log có thể chứa đường dẫn máy, repository URL hoặc cấu hình nội bộ; kiểm tra trước khi chia sẻ.

**Kết quả minh họa có điều kiện**:

```text
# Lượt đầu (có source)
> Task :compileJava
> Task :processResources
> Task :test
> Task :bootJar

# Lượt sau (không thay đổi input)
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :test UP-TO-DATE
> Task :bootJar UP-TO-DATE
```

Đây không phải stdout đã thực thi trong môi trường người học. Trạng thái `classes`/`build` hay test task có thể khác vì task lifecycle và task inputs.

## 7. Thực nghiệm 2 – Một Java source đổi nhưng không đổi ABI

Trong `Calculator.java`, chỉ sửa thân method:

```java
public int add(int left, int right) {
    int result = left + right;
    return result;
}
```

Chạy:

```bash
./gradlew compileJava --console=plain --info
```

Lần sửa này làm `Calculator.java` khác source trước, nên `compileJava` thường phải chạy; khác `UP-TO-DATE`. Tuy nhiên, signature public `int add(int,int)` không đổi, nên incremental compiler có thể chỉ xử lý lớp bị ảnh hưởng, tránh recompile consumer không cần thiết.

**Đừng kết luận từ nhãn task đơn lẻ**: khi task chạy, console chỉ cho thấy nó đã execute. Muốn biết có incremental hay full compilation, đọc `--info` và quan sát những source/class được Gradle xử lý theo log của phiên bản đó. Thông điệp cụ thể có thể thay đổi giữa Gradle versions.

### 7.1 Thay public API

Trên bản sao/nhánh thử nghiệm, thay signature bằng:

```java
public long add(int left, int right) {
    return (long) left + right;
}
```

Consumer `DemoApplication` phải thấy hợp đồng nhị phân mới; phạm vi compilation có thể lớn hơn. Java vẫn nối được long vào chuỗi, nên lệnh `java -jar` với kết quả cộng 2+3 vẫn có thể in `SUM=5`. Nếu thay tên `add` thành `sum` mà không đổi caller, compiler báo method không tồn tại; đó là lỗi hợp lệ vì call site đã sai.

Sau thử nghiệm, hoàn nguyên `Calculator.java` về phiên bản trả `int` để tiếp tục bài.

### 7.2 Thay lớp không liên quan

Sửa `Unrelated.message()` từ `"unrelated"` thành `"independent"` rồi chạy `compileJava --info`. Task chạy vì file đó đổi; incremental compiler có thể tránh xử lý `Calculator` và `DemoApplication` khi chúng không bị ảnh hưởng. Không hứa "luôn chỉ một .class" vì inner classes, annotation processors, state history và các yếu tố khác.

### 7.3 Chỉ build task cần quan sát

Khi kiểm tra compiler, chọn `./gradlew compileJava` thay vì `build` để không trộn thời gian test và packaging. Khi muốn xác minh sản phẩm, chạy thêm `bootJar` hoặc `build` rồi dùng `java -jar`. Một lần `compileJava` thành công **chưa chứng minh executable JAR đã cập nhật**.

## 8. Thực nghiệm 3 – Đổi resource, Java compiler có chạy lại?

Sửa `src/main/resources/build-info.properties`:

```properties
app.label=release-candidate
```

Sau đó:

```bash
./gradlew classes --console=plain --info
./gradlew bootJar --console=plain --info
```

Dự đoán có điều kiện:

- `processResources` chạy lại vì resource input đổi.
- `compileJava` vẫn có thể `UP-TO-DATE` vì Java source và compiler classpath không đổi.
- `bootJar` có thể đóng gói lại vì classpath output có resource mới.
- File sau xử lý nằm ở `build/resources/main/build-info.properties`; trong executable Spring Boot JAR thông thường nó nằm ở `BOOT-INF/classes/build-info.properties`.

Có thể kiểm tra:

```bash
jar tf build/libs/gradle-incremental-demo-0.0.1-SNAPSHOT.jar
```

Đường dẫn theo `rootProject.name`/`version` của ví dụ. Nếu đã đổi archive basename/classifier, dùng tên thực trong `build/libs`.

**Không khai báo mọi resource thành input của JavaCompile** khi compiler không dùng chúng. Làm vậy gây biên dịch lại không cần thiết mỗi lần sửa ảnh hoặc file Spring config. Nếu annotation processor đọc resource để sinh code thì phải khai báo đầu vào phù hợp; đó là trường hợp khác.

## 9. Khai báo input cho `processResources` để tránh stale output

Một tình huống phổ biến là đưa `project.version` vào resource khi build. Nếu Gradle không biết giá trị nào làm thay đổi file, task có thể bị đánh dấu up-to-date sai.

### 9.1 File resource template

Đổi `src/main/resources/build-info.properties` thành:

```properties
app.version=${appVersion}
```

Thêm vào **cuối `build.gradle`** ở phần 5:

```groovy
def appVersionValue = project.version.toString()

tasks.named('processResources') {
    inputs.property('appVersion', appVersionValue)

    filesMatching('build-info.properties') {
        expand(appVersion: appVersionValue)
    }
}
```

- `filesMatching` chọn đúng file template cần mở rộng.
- `expand` dùng Groovy template syntax để thay token `${appVersion}` bằng chuỗi version.
- `inputs.property` đăng ký giá trị này là input của task; nếu version thay, Gradle có lý do chạy lại.
- Các resource khác tiếp tục được copy theo default; không xử lý hàng loạt mọi file như PNG hay Spring runtime config.

Với `version='0.0.1-SNAPSHOT'`, file `build/resources/main/build-info.properties` sau `processResources` kỳ vọng:

```properties
app.version=0.0.1-SNAPSHOT
```

**Cẩn trọng Spring placeholder:** file `application.properties` có thể chứa `server.port=${PORT:8080}` để Spring resolve khi chạy. Gradle `expand` cũng xử lý syntax `${...}`, có thể xung đột. Vì vậy chỉ mở rộng file `build-info.properties` hoặc escape đúng nếu phải filter Spring config. Không gọi `expand(project.properties)` trên mọi resource.

### 9.2 Kotlin DSL tương đương

Trích đoạn cho `build.gradle.kts` của project đã có Java plugin:

```kotlin
val appVersionValue = project.version.toString()

tasks.processResources {
    inputs.property("appVersion", appVersionValue)

    filesMatching("build-info.properties") {
        expand(mapOf("appVersion" to appVersionValue))
    }
}
```

Không ghép cú pháp Groovy `expand(appVersion: appVersionValue)` vào Kotlin DSL. Đây chỉ là phần tùy chỉnh processResources, các dòng plugins/dependencies/toolchain của toàn bộ dự án phải được cấu hình riêng.

### 9.3 Thử up-to-date và giá trị version thay

```bash
./gradlew processResources --console=plain --info
./gradlew processResources --console=plain --info
```

Nếu không đổi input, lần hai có thể `UP-TO-DATE`. Trong nhánh thử nghiệm, sửa `version` thành `0.0.2-SNAPSHOT` rồi chạy lại. Vì appVersion có trong input, Gradle nên tạo:

```properties
app.version=0.0.2-SNAPSHOT
```

Khi dự án thật thay version, các task khác như `bootJar` có thể cũng cần chạy vì tên và nội dung archive đổi. Không chỉ xem task outcome: **mở file output thật** để kiểm chứng nội dung được thay.

## 10. Custom task: input/output và Provider API

### 10.1 Ví dụ tạo file với input môi trường

Thêm vào cuối `build.gradle`:

```groovy
def buildChannel = providers.environmentVariable('BUILD_CHANNEL')
    .orElse('local')

def outputFile = layout.buildDirectory.file('generated/build-channel.txt')

tasks.register('writeBuildChannel') {
    inputs.property('buildChannel', buildChannel)
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(buildChannel.get() + '\n', 'UTF-8')
    }
}
```

Đây là **custom task chạy được trong một project Gradle Groovy DSL** có Java hoặc không có Java. Nó nhận input `BUILD_CHANNEL` qua Provider và mặc định `local`; tạo một output riêng ở `build/generated/build-channel.txt`.

Chạy:

```bash
./gradlew writeBuildChannel --console=plain --info
./gradlew writeBuildChannel --console=plain --info
```

Lượt hai có thể `UP-TO-DATE`. Trong Bash có thể chạy `BUILD_CHANNEL=qa ./gradlew writeBuildChannel`; Windows PowerShell đặt `$env:BUILD_CHANNEL = 'qa'` rồi chạy `.\gradlew.bat writeBuildChannel`. Khi input đổi, file output cần đổi thành `qa` và newline.

Đây là output custom task **độc lập**, không tự nằm trong JAR. Nếu muốn cho file generated vào `processResources`, phải nối task output bằng TaskProvider/`from(taskProvider)` hoặc cơ chế tương ứng, bảo đảm dependency được suy ra hoặc khai báo. Không tự ghi file vào `src/main/resources` mỗi lần build rồi nghĩ Gradle tự biết đó là output.

### 10.2 Vì sao không đọc biến môi trường trong `doLast` mà không khai báo?

Sai lầm thường gặp:

```groovy
tasks.register('badTask') {
    outputs.file(layout.buildDirectory.file('bad.txt'))

    doLast {
        file("$buildDir/bad.txt")
            .text = System.getenv('BUILD_CHANNEL')
    }
}
```

Đây là **phản ví dụ cần tránh**, không dùng trong build release: task dùng environment làm dữ liệu cho output nhưng không khai báo input; cũng dùng API/đường dẫn ít phù hợp với Provider/configuration cache. Kết quả có thể stale hoặc không có thông tin đầy đủ để Gradle kiểm tra. **Sửa nguồn input/output**, không dùng `--rerun-tasks` lâu dài để che vấn đề.

### 10.3 InputChanges cho custom task xử lý tăng dần

Một task có input/output đầy đủ có thể đạt **UP-TO-DATE**, nhưng khi một file đầu vào đổi và task **chạy**, chưa chắc task chỉ xử lý file đó. Để có **incremental execution bên trong custom task**, task type có thể dùng:

- `@InputFiles` hoặc `@InputDirectory` cho tập nguồn.
- `@Incremental` với file input property hỗ trợ.
- `@PathSensitive` để định nghĩa cách đường dẫn ảnh hưởng fingerprint.
- `@OutputDirectory` hoặc `@OutputFile` cho đầu ra.
- Tham số `InputChanges` trong `@TaskAction` và `getFileChanges(...)` để đọc những file `ADDED`, `MODIFIED`, `REMOVED`.

Task phải xử lý cả thay đổi **REMOVED** (xóa output tương ứng), và xử lý trường hợp `InputChanges.isIncremental()` là false bằng **full rebuild** hợp lệ. Đây là một API dành cho **tác giả custom task/plugin**, không phải thứ bắt buộc thêm vào `compileJava`: JavaCompile đã có engine incremental của Gradle.

Ví dụ xử lý file riêng lẻ không nên tự viết nếu một task `Copy`/`Sync` có sẵn đã đáp ứng đúng yêu cầu. Với custom generator, thiết kế incremental output mapping trước khi tối ưu.

### 10.4 Tính quyết định của output

Task đọc thời gian thực, random value, network không ổn định hay secret ngoài mà không mô hình hóa sẽ gây cache sai. Muốn task cacheable, **output phải được xác định đầy đủ bởi declared inputs và task implementation**; không phải cứ thêm `outputs.file` là an toàn cho remote cache.

Không thêm timestamp hiện tại thành input của mọi task chỉ để "buộc build tạo bản mới". Cách đó làm mất lợi ích Gradle tối ưu và có thể gây artifact không reproducible.

## 11. Multi-project: tránh biên dịch lại module consumer khi ABI không đổi

### 11.1 Mô hình đơn giản

```text
multi-project/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/com/example/core/Formatter.java
└── app/
    ├── build.gradle
    └── src/main/java/com/example/app/AppApplication.java
```

`settings.gradle`:

```groovy
rootProject.name = 'multi-project'
include 'core', 'app'
```

`core/build.gradle`:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

`core/src/main/java/com/example/core/Formatter.java`:

```java
package com.example.core;

public final class Formatter {

    public String format(String value) {
        return "message=" + value;
    }
}
```

`app/build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

`app/src/main/java/com/example/app/AppApplication.java`:

```java
package com.example.app;

import com.example.core.Formatter;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AppApplication {

    public static void main(String[] args) {
        SpringApplication.run(AppApplication.class, args);
        System.out.println(new Formatter().format("ok"));
    }
}
```

Chạy:

```bash
./gradlew :app:bootJar --console=plain --info
```

Với app console và dependency đã phân giải, chương trình khi chạy đúng executable JAR sẽ in dòng do mã tạo:

```text
message=ok
```

Không phải toàn bộ stdout (Spring Boot còn có thể in log).

### 11.2 Đổi implementation của `:core`

Đổi thân hàm:

```java
public String format(String value) {
    String result = "message=" + value;
    return result;
}
```

Nếu ABI `Formatter` không đổi, Gradle có thể:

- Chạy `:core:compileJava` vì source đã thay.
- Giữ `:app:compileJava UP-TO-DATE` nhờ compilation avoidance.
- Chạy lại `:app:bootJar` vì runtime library `core` cần được đóng vào archive với byte mới.

**Đó là ba quyết định riêng biệt**, không mâu thuẫn. Nếu đổi method signature hoặc public interface trong `:core`, `:app:compileJava` có thể bị invalidated và compile lại.

### 11.3 Ranh giới `api`/`implementation`

Trong module `java-library`, khai báo dependency là `api` nếu type của dependency xuất hiện trong public API cần consumer biên dịch; dùng `implementation` cho các thư viện chỉ dùng nội bộ. Thu hẹp compile classpath downstream có thể giúp compile avoidance tốt hơn khi internal dependency đổi.

Đừng chuyển tất cả thành `implementation` nếu public method thực sự dùng type của thư viện; consumer có thể thiếu class cần ở compile time. Tối ưu phải nhất quán với kiến trúc API.

## 12. Annotation processors và tác động lên incremental compilation

### 12.1 Cấu hình riêng processor classpath

Ví dụ Lombok:

```groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
```

Đây là **trích đoạn** của project có `repositories` và những dependency phù hợp. `compileOnly` cung cấp annotation API cho compiler; `annotationProcessor` cấp processor để sinh code. Đừng thêm processor vào `implementation` chỉ để "compiler tìm được" nếu nó không cần ở runtime.

### 12.2 Isolating, aggregating và non-incremental

Gradle hỗ trợ incremental annotation processing khi processor tuân thủ contract:

- **Isolating:** generated file phụ thuộc một annotated element, có thể xử lý thay đổi hẹp.
- **Aggregating:** một generated file tổng hợp thông tin từ nhiều annotated elements, nên có thể phải tái xử lý rộng hơn.
- **Non-incremental/không khai báo đúng:** có thể buộc full recompilation.
- **Processor đọc resource ngoài:** cần khai báo resource làm input. Khi resource đó đổi, Gradle có thể full recompile tùy loại input/processor.

Chạy `./gradlew compileJava --info` để xem Gradle có báo processor nào không hỗ trợ incremental hay không. **Không suy từ bảng hỗ trợ processor trên mạng rằng chính version đang dùng chắc chắn incremental**, vì khả năng có thể đổi theo Gradle/JDK/processor version.

### 12.3 Một số điều kiện buộc recompile rộng hơn

Thay compile-time constant, source-retention annotations, compiler options, Java home/executable custom, mất history do clean hoặc compile trước lỗi đều có thể giảm hiệu quả incremental compiler. Khi thấy compile chậm, đọc log cụ thể trước khi thử nâng memory/disable processor.

Nếu dự án có Kotlin/Groovy/Scala bên cạnh Java, các task `compileKotlin`, `compileGroovy` hay `compileScala` có compiler state riêng. Không lấy kết quả `compileJava UP-TO-DATE` làm bằng chứng tối ưu của những ngôn ngữ còn lại.

## 13. Build cache, configuration cache và dependency cache khác nhau

### 13.1 Build cache và `FROM-CACHE`

**Up-to-date** dựa trên trạng thái output/lịch sử execution trước đó của **workspace hiện tại**. **Build cache** giữ output của task cacheable theo cache key, có thể reuse giữa build khác hoặc agent khác nếu cấu hình cache chia sẻ.

Thử local cache:

```bash
./gradlew build --build-cache --console=plain
./gradlew clean
./gradlew build --build-cache --console=plain
```

Sau `clean`, một số task **có thể `FROM-CACHE`**, không phải vì source chưa từng thay mà vì cache có output tương ứng. Không hứa tất cả task như `test`/`bootJar` đều được cache ở mọi plugin/version; cacheability và inputs quyết định kết quả thực.

**`clean` không bảo đảm full recompile từ đầu** khi build cache còn bật. Nếu muốn tách hai cơ chế, thử `--no-build-cache`; khi đó local `UP-TO-DATE` vẫn có thể xuất hiện.

### 13.2 Configuration cache

Gradle có initialization, configuration và execution phases. **Configuration cache** lưu task graph/cấu hình để tránh chạy lại cấu hình nếu inputs cho configuration không đổi. Nó **không** thay thế up-to-date checking hay Java incremental compiler.

```bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
```

Với plugin/build logic tương thích, lần sau có thể reuse configuration cache. Nếu custom task truy cập `Project` từ task action theo cách không hỗ trợ, Gradle có thể báo configuration cache problem. Trên Gradle 8.x, dùng cờ này có chủ đích; đối chiếu đúng tài liệu Gradle version.

### 13.3 Dependency cache

Gradle dependency cache (như các artifacts/metadata trong `GRADLE_USER_HOME/caches/modules-2`) giảm tải thư viện từ Maven repositories. Nó khác task output build cache và khác execution history local.

| Cơ chế | Phạm vi | Dấu hiệu |
| --- | --- | --- |
| Up-to-date | Bỏ qua task trên workspace hiện tại | `UP-TO-DATE` |
| Incremental Java compile | Khi JavaCompile chạy, dịch những class bị ảnh hưởng | Compiler diagnostics/log `--info` |
| Compilation avoidance | Không chạy compile ở module tiêu thụ nếu ABI upstream không đổi | Consumer `compileJava UP-TO-DATE` |
| Build cache | Khôi phục outputs task cacheable | `FROM-CACHE` |
| Configuration cache | Bỏ qua tính lại cấu hình/task graph | Log configuration cache reused |
| Dependency cache | Dùng lại dependency artifacts/metadata | Dependency resolution/download logs |

`--offline`/`--refresh-dependencies` liên quan dependency resolution, không phải "bật/tắt Java incremental compiler". Cần phân biệt đúng mục tiêu khi khắc phục vấn đề.

## 14. Cờ Gradle để chẩn đoán, không phải để dùng bừa

### 14.1 `--info --console=plain`

```bash
./gradlew compileJava --info --console=plain
./gradlew processResources --info --console=plain
./gradlew bootJar --info --console=plain
```

Giúp xem lý do task chạy/skip, inputs, compiler diagnostic và logs một cách dễ so sánh. Thông điệp cụ thể thay đổi giữa Gradle versions.

### 14.2 `--rerun-tasks`

```bash
./gradlew compileJava --rerun-tasks --console=plain --info
```

Ép thực thi lại các task liên quan để chẩn đoán nghi ngờ stale output/up-to-date sai. Thường làm build chậm hơn, không phải cải thiện hiệu năng. Nếu chỉ chạy đúng khi thêm cờ này, phải sửa **task input/output model**.

### 14.3 `--no-build-cache`

```bash
./gradlew build --no-build-cache --console=plain
```

Không lấy kết quả task từ build cache. Tuy nhiên `compileJava UP-TO-DATE` vẫn có thể xuất hiện vì local up-to-date checking là cơ chế khác.

### 14.4 `clean`

```bash
./gradlew clean build
```

Xóa outputs ở `build/` (theo project/config), tạo baseline từ trạng thái output trống; **không mặc định dùng trong mỗi edit-build cycle** vì làm mất lợi ích incremental history. Cache có thể vẫn khôi phục output. Chỉ dùng trên workspace có quyền làm sạch; không can thiệp thư mục build đang được job khác sử dụng.

### 14.5 `--dry-run`

```bash
./gradlew build --dry-run
```

Hiển thị kế hoạch task graph mà không chạy actions thông thường. **Không** dùng dry-run để kết luận `compileJava` sẽ up-to-date/incremental khi thực thi thật; dùng build bình thường để kiểm tra outcome.

### 14.6 `--debug` và build scan

`--debug` tạo logs rất dài có thể lộ đường dẫn/repository/configuration; chỉ dùng khi thực sự cần và xử lý dữ liệu. Build scans/profiling có thể cải thiện quan sát hiệu năng nhưng không nên tự đăng tải thông tin nội bộ lên dịch vụ ngoài khi chưa có quyền; log `--info` local đã đủ cho bài học.

## 15. Tác động riêng tới Spring Boot task

### 15.1 `bootJar` có thể chạy lại dù `compileJava` không

Spring Boot `bootJar` đóng gói **classes + processed resources + runtime dependencies** vào executable JAR. Do đó:

- Đổi Java source: `compileJava` có thể incremental, `bootJar` có thể cập nhật.
- Đổi `application.properties`: `processResources` đổi, `compileJava` có thể up-to-date, `bootJar` cập nhật.
- Đổi runtime dependency version: `compileJava` chưa chắc đổi nếu compile ABI không đổi, nhưng `bootJar` phải đóng nested dependency mới.
- Chỉ thay test source: `compileTestJava` và `test` có thể chạy, `bootJar` thường không cần đổi nếu main artifact inputs giữ nguyên.
- Đổi version/classifier/manifest: archive inputs/naming có thể đổi, task đóng gói có thể bị invalidated.

**Không sửa sai bằng cách viết `bootJar.outputs.upToDateWhen { true }` để ép bỏ qua mọi build**, vì có thể phát hành JAR cũ. Khai báo inputs và output chính xác để Gradle tự quyết định.

### 15.2 `bootRun` không phải `bootJar`

`bootRun` chạy app từ compiled classes, resources và development runtime classpath; với web server, task còn giữ JVM sống. Nó không nhất thiết sinh executable JAR. Một app chạy được bằng `bootRun` chưa chứng minh file trong `build/libs` còn mới hoặc đủ dependency cho `java -jar`.

Nếu mục đích tối ưu vòng lặp lập trình, `classes`/`bootRun` phù hợp; nếu mục đích xác minh sản phẩm release, phải build `bootJar` và kiểm tra chính artifact.

### 15.3 `test` có trạng thái up-to-date nhưng chất lượng test phải được bảo đảm

Test task input có thể gồm test bytecode, runtime classpath, JVM args/properties đã khai báo và file fixtures. Nếu test phụ thuộc network/database/thời gian/ngẫu nhiên mà đầu vào không được mô hình hóa, caching/up-to-date có thể tạo kết quả **không phản ánh lần chạy mới**.

Đừng bật cache bừa cho integration tests có side effects; thay vào đó làm chúng deterministic, cô lập hoặc định nghĩa chính sách chạy lại riêng cho integration stage. `test SKIPPED` do `-x test` không phải unit tests pass.

### 15.4 Tối ưu metadata archive

Nếu build script gắn timestamp hiện tại vào manifest hoặc file generated mỗi lần, archive có thể bị invalidated liên tục dù source không đổi. Trong quy trình release, cân nhắc dùng version, SCM commit id ổn định và cơ chế reproducible archives thích hợp. Không dùng output ngẫu nhiên để "chứng minh build có chạy".

## 16. Các lỗi phổ biến và chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `compileJava` luôn chạy dù source không đổi | Classpath/toolchain/plugin/options thay đổi, missing outputs/history | Chạy `--info` hai lần liên tục, so inputs |
| `compileJava` chạy sau một sửa đổi nhỏ | Bình thường: source đổi nên task out-of-date | Xem incremental compiler có xử lý hẹp hay full |
| `compileJava` full recompilation | ABI/constant/processor thay, compiler error, mất state | `--info`, annotationProcessor, toolchain |
| `:app:compileJava` chạy sau thay thân hàm ở `:core` | ABI khác thực tế, compile classpath hoặc custom inputs bị ảnh hưởng | So public API, dependency graph, `--info` |
| Resource đổi nhưng Java task up-to-date | File resource không ảnh hưởng compiler | Xem `processResources` và `bootJar` |
| Resource `build-info.properties` vẫn chứa version cũ | Value expansion chưa khai báo input, filter sai file | Kiểm tra `inputs.property`, output thực |
| `processResources NO-SOURCE` | Không có resources đúng sourceSet | Kiểm tra `src/main/resources`, include/exclude |
| `test SKIPPED` nhưng CI báo xanh | Loại test bằng `-x test`/onlyIf | Xem CI/task configuration, không coi SKIPPED là PASS |
| `test FROM-CACHE` sau clean | Build cache lưu outputs trước đó | Xem cache settings, test determinism |
| `bootJar` UP-TO-DATE nhưng kỳ vọng class mới | Chỉnh sai module hoặc file không vào sourceSet, input thiếu | Kiểm tra task input, archive và `jar tf` |
| `bootJar` chạy mọi lượt | Timestamp/manifest/property/random version/runtime deps đổi | Xem `--info`, archive config |
| Sau `clean` vẫn `FROM-CACHE` | Build cache hoạt động độc lập | Dùng `--no-build-cache` nếu muốn tách hiện tượng |
| `--no-build-cache` vẫn `UP-TO-DATE` | Local task history còn hợp lệ | Đây là hành vi đúng, không phải bug |
| Custom task sinh output stale | Thiếu `@Input`/`inputs.property` hoặc output declaration | Sửa model task, chạy lại test |
| Java compile không tăng dần khi có annotation processor | Processor không hỗ trợ isolating/aggregating hoặc đọc file ngoài | `--info`, tài liệu processor version |
| CI agent mới thường compile nhiều | Không có local history, chưa dùng shared build cache | Đánh giá remote cache theo chính sách |
| Build cache output lỗi | Task non-deterministic/missing inputs hoặc cache key không đủ | Sửa task, tắt caching cho task lỗi trong lúc điều tra |
| Có source cũ sau thay file | Output stale, task dependency sai, artifact cũ được chọn | Kiểm tra sourceSets, output, archive; dùng clean lab để đối chiếu |
| Dùng Gradle 8 và đọc tài liệu Gradle 9 mới | Khác biệt syntax/task/plugin behavior | Đối chiếu docs version và Wrapper thật |
| Build xanh nhưng không có Java classes | `compileJava NO-SOURCE` do sai source path | Kiểm tra `src/main/java` và module |
| Gradle build chậm ở configuration | Plugins/configuration nặng | Đo riêng config phase, xét configuration cache |
| Compile avoidance không hiệu quả ở multi-project | Export dependency quá rộng bằng `api`, ABI hay đổi | Rà ranh giới java-library, compile classpath |

### Quy trình 7 bước để giải quyết

1. Xác định đúng task đang chậm và module chứa nó.
2. Ghi lại lệnh, Gradle Wrapper version, JDK/toolchain và plugin version.
3. Chạy cùng task **hai lần không sửa input** với `--info --console=plain`.
4. Phân biệt outcome `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED`/executed.
5. Nếu `compileJava` executed, xem compiler incremental hay full và vì sao.
6. Nếu `bootJar` executed, xem class/resource/dependency/manifest input nào đổi.
7. Sửa nguồn bất ổn hoặc input/output declaration, chạy test và xác minh archive trước khi kết luận cải thiện.

Không bắt đầu bằng việc xóa mọi thư mục cache hoặc thêm `--rerun-tasks` vào CI vô thời hạn. Những cách đó thường làm mất lợi ích tối ưu mà không giải quyết nguyên nhân.

## 17. Benchmark: đo ba kiểu build khác nhau

| Kịch bản | Điều kiện | Quan sát cần ghi |
| --- | --- | --- |
| Build đầu tiên | Workspace chưa có outputs; build cache có thể bật/tắt rõ ràng | Task executed, `FROM-CACHE`, thời gian |
| Rebuild không sửa gì | Cùng lệnh/inputs/outputs | Những task `UP-TO-DATE` và tổng thời gian |
| Sửa một Java method body | ABI không đổi | `compileJava` chạy incremental thế nào |
| Sửa public API | ABI có thay đổi | Consumer/module nào phải compile |
| Chỉ sửa resource | Không thay Java | `processResources`/`bootJar`, `compileJava` |
| Sau `clean` + build cache | Outputs mất, cache còn | Task nào `FROM-CACHE` |
| Đổi version build time | `appVersion` là declared input | Output properties và archive có cập nhật không |

**Không có số giây cố định cho mọi máy.** Đo ít nhất vài lượt trong điều kiện giống nhau, phân biệt daemon/JVM warm-up, download dependencies, filesystem cache, config cache và mức tải CPU. Nếu sử dụng `--profile` hoặc profiling tools, kiểm tra tính sẵn có trên version Gradle hiện tại.

Chỉ tính một build "nhanh" khi **output đúng, test cần thiết được chạy hoặc xác thực hợp lệ, và artifact cuối phản ánh đúng source/dependency**. Bỏ qua test hoặc reuse JAR cũ có thể nhanh nhưng không đạt yêu cầu.

## 18. Bài thực hành có kết quả kiểm chứng

### A. Chứng minh `UP-TO-DATE`

Dựng project phần 5, chạy `./gradlew build --info` hai lần, không sửa gì. Ghi task outcome và giải thích vì sao compiler không thực thi ở lần thứ hai nếu `compileJava` up-to-date.

### B. Chứng minh incremental compiler

Chỉ sửa thân `Calculator.add`, chạy `compileJava --info`, xem task chạy nhưng Gradle có thể biên dịch phạm vi hẹp. Thử đổi chữ ký trên nhánh lab, so log và kết quả compile. Hoàn nguyên sau bài.

### C. Tách resource và class compilation

Chỉ sửa `build-info.properties`, gọi `classes` và `bootJar`. Dùng `jar tf` kiểm tra `BOOT-INF/classes/build-info.properties`. Giải thích vì sao resource thay không bắt buộc Java compile lại.

### D. Khai báo input đúng

Dùng `inputs.property('appVersion', appVersionValue)` cùng `filesMatching/expand`. Đổi version trên nhánh thử nghiệm và xác nhận output từ `0.0.1-SNAPSHOT` thành `0.0.2-SNAPSHOT`. Trả lời vì sao không lọc toàn bộ `application.properties` chứa Spring runtime placeholder.

### E. So cache với up-to-date

Bật `--build-cache`, build, clean, build lại. Ghi task nào `FROM-CACHE` nếu có. Dùng `--no-build-cache` trong lượt khác và giải thích vì sao `UP-TO-DATE` vẫn có thể xuất hiện.

### F. Multi-project compile avoidance

Dựng `:core`/`:app` ở phần 11. Sửa body trong `Formatter` mà giữ ABI, quan sát `:core:compileJava`, `:app:compileJava`, `:app:bootJar`. Đổi public method signature trên bản sao để thấy phạm vi invalidation khác.

### G. Phản biện một cách sửa lỗi sai

Một đồng nghiệp viết:

```groovy
tasks.named('bootJar') {
    outputs.upToDateWhen { true }
}
```

và nói "đã tối ưu nên không còn build JAR nữa". Hãy giải thích vì sao điều này có thể tạo artifact stale và không phải cơ chế incremental chính thống. Nếu resource/compiled class thay, task đóng gói phải nhận thay đổi và cập nhật.

### H. Tạo báo cáo tái hiện

Ghi ít nhất:

```text
Gradle Wrapper version:
JDK/toolchain version:
Spring Boot plugin version:
Task command:
Lần chạy 1 outcome / thời gian:
Lần chạy 2 outcome / thời gian:
Một thay đổi source được thực hiện:
File nào được sửa:
compileJava executed hay UP-TO-DATE:
Nếu executed, incremental hay full và bằng chứng:
processResources outcome:
bootJar outcome:
Nội dung artifact/build output sau đổi:
Bài học về cache/input-output:
```

Đây là **mẫu để người học ghi bằng chứng thật**, không phải report đã chạy. Tiêu chí đạt: phân biệt **skip toàn task** với **compile tăng dần bên trong task**, hiểu ABI và compilation avoidance, phân biệt `FROM-CACHE`, biết sử dụng `--info` và xác minh output Spring Boot cập nhật chính xác.

## 19. Tài liệu tham khảo chính thức

- Gradle – Incremental Build (task inputs/outputs, fingerprints, up-to-date checks): https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle – Java Plugin (Incremental Java compilation, compilation avoidance và annotation processing): https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle – Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
- Gradle – Advanced Tasks / InputChanges: https://docs.gradle.org/current/userguide/custom_tasks.html
- Gradle – Gradle Optimizations & Task Outcome Labels: https://docs.gradle.org/current/userguide/gradle_optimizations.html
- Gradle – Improve the Performance of Gradle Builds: https://docs.gradle.org/current/userguide/performance.html
- Gradle – Java Library Plugin, `api` vs `implementation`: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Spring Boot 3.3 – Gradle Plugin, Packaging Executable Archives (`bootJar`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Gradle Plugin, Running Your Application (`bootRun`): https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html

**Ghi nhớ:** `UP-TO-DATE` = **không chạy task**; incremental Java compilation = **task `compileJava` chạy, nhưng có thể dịch lại chỉ phần bị ảnh hưởng**; compilation avoidance = **không compile lại downstream nếu ABI không đổi**; `FROM-CACHE` = **lấy output từ build cache**. Với Spring Boot, kiểm tra từng task `compileJava`/`processResources`/`test`/`bootJar` và luôn xác nhận executable artifact chứa thay đổi đúng thay vì hy sinh tính đúng đắn để có một nhãn cache đẹp.
