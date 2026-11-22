# sourceCompatibility, targetCompatibility và javac --release trong Gradle

## 1. Ba khía cạnh tương thích Java cần tách biệt

Khi triển khai một thư viện Java chạy trên nhiều máy, câu hỏi “dùng Java phiên bản nào?” chưa đủ rõ. Ít nhất cần phân biệt ba khía cạnh:

1. **Ngôn ngữ nguồn (source language level):** mã nguồn được phép sử dụng cú pháp Java phiên bản nào, ví dụ `record` (Java 16), `var` cho biến cục bộ (Java 10), hoặc các cú pháp cũ tương thích Java 8?
2. **Định dạng bytecode (class-file target):** trình biên dịch tạo file `.class` ở định dạng mà JVM phiên bản tối thiểu nào có thể đọc?
3. **Java platform APIs:** mã nguồn được phép tham chiếu tới các lớp, method và field của Java SE phiên bản nào, ví dụ `List.of(...)` (Java 9), `String.repeat(...)` (Java 11), `String.formatted(...)` (Java 15)?

Ba thuộc tính không hoàn toàn tương đương. Một chương trình có thể viết bằng **cú pháp Java 8**, được biên dịch thành **bytecode Java 8**, nhưng lại gọi **API chỉ có từ Java 9** nếu compiler dùng API của JDK mới và không bị ràng buộc. File `.class` có thể load được trên JVM 8, nhưng chương trình có thể phát sinh lỗi linkage khi gọi method không tồn tại.

**Khái niệm cốt lõi của bài:**

- `sourceCompatibility` trong Gradle điều khiển cấp độ cú pháp Java được phép dùng cho JavaCompile, tương ứng với ý tưởng `javac -source`.
- `targetCompatibility` điều khiển class-file target, tương ứng với `javac -target`.
- `javac --release N` (và Gradle `options.release.set(N)`) đồng thời định hướng **ngôn ngữ nguồn, bytecode và Java SE API đã được công bố ở release N**.
- **Java toolchain** chọn **JDK/javac thực sự dùng để biên dịch**, là một quyết định khác với release mục tiêu.

Mục tiêu sau bài: cấu hình Gradle sao cho máy build dùng JDK 17 vẫn tạo thư viện sử dụng API Java 11; hiểu vì sao chỉ dùng `sourceCompatibility`/`targetCompatibility` có thể chưa đủ; tự thực hiện các phép thử với `javac`, `java`, `javap` và biết giới hạn của cross-compilation.

## 2. Ví dụ trực quan: JDK 17, cú pháp 8, bytecode 8, API 9

Giả sử có source:

```java
import java.util.List;

public class ApiLeak {
    public static void main(String[] args) {
        System.out.println(List.of("A", "B").size());
    }
}
```

Đoạn code chỉ dùng một lời gọi method và một generic type không đòi cú pháp Java mới. Tuy nhiên, `List.of` **được bổ sung từ Java 9**.

Trên **JDK 17**, chạy:

```bash
javac -source 8 -target 8 ApiLeak.java
```

Lệnh có thể biên dịch thành công (có thể kèm cảnh báo về `bootstrap class path` hoặc system modules chưa được đặt cho target cũ). Vì `-source 8` chỉ kiểm tra ngôn ngữ nguồn, `-target 8` chỉ yêu cầu file `.class` tương thích định dạng Java 8; compiler vẫn có thể nhìn thấy API của **JDK 17** hiện tại khi không dùng cơ chế hạn chế API chuẩn.

Kết quả:

```text
ApiLeak.class
  class-file major version = 52 (Java 8)
  có tham chiếu tới java.util.List.of(...)
```

Nếu chạy file đó trên **Java 17**, ứng dụng in:

```text
2
```

Nhưng nếu thật sự chạy trên **Java 8**, lời gọi `List.of` có thể gây:

```text
java.lang.NoSuchMethodError
```

Lý do: runtime Java 8 có `java.util.List` nhưng **không có method `List.of`**. Bytecode format tương thích không bảo đảm API đã tồn tại ở runtime.

**Cách hạn chế đúng trong tình huống này:**

```bash
javac --release 8 ApiLeak.java
```

Dùng JDK 17 làm compiler nhưng yêu cầu Java SE 8 release, `javac` sẽ báo lỗi ở `List.of(...)` vì **API này không nằm trong Java 8**. Đây là bằng chứng rõ nhất cho sự khác biệt giữa cặp `-source/-target` với `--release`.

## 3. Bảng đối chiếu bốn quyết định

| Cơ chế | Quyết định chính | Có chọn JDK đang chạy compiler? | Có giới hạn Java SE API theo release cũ? |
| --- | --- | --- | --- |
| `sourceCompatibility = 11` | Cú pháp Java 11 được phép | Không | Không, nếu đứng riêng |
| `targetCompatibility = 11` | Định dạng `.class` cho Java 11 | Không | Không, nếu đứng riêng |
| `options.release.set(11)` | Cú pháp + bytecode + Java SE API của release 11 | Không; cần compiler đủ mới | **Có** |
| `java.toolchain.languageVersion.set(17)` | Chọn JDK 17 để compile/test theo toolchain | **Có** cho task tương ứng | Không tự giới hạn API xuống Java 11 |

**Chú ý:** “chọn JDK 17” và “cho phép Java 17” là hai khái niệm khác nhau. Một máy có thể sử dụng compiler từ JDK 17 để phát hành artifact phù hợp với **Java 11** nhờ `options.release.set(11)`.

Không đồng nhất những tùy chọn này với Gradle Wrapper. Wrapper quyết định **phiên bản Gradle** được chạy; Java toolchain quyết định **JDK thực thi công việc Java**; release target quyết định **mức Java SE mà artifact muốn hỗ trợ**. Chúng phối hợp nhưng không thay thế nhau.

## 4. Cấu hình Gradle `sourceCompatibility` và `targetCompatibility`

Trong project dùng plugin `java`, `java-library` hoặc `application`, Gradle cung cấp các thuộc tính tương thích.

### 4.1. Groovy DSL

**File `build.gradle` — ví dụ riêng:**

```groovy
plugins {
    id 'java'
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
```

### 4.2. Kotlin DSL

**File `build.gradle.kts` — ví dụ riêng:**

```kotlin
plugins {
    java
}

java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
```

Trong các trường hợp JavaCompile thông thường, Gradle dùng cấu hình này để biên dịch với các mức `-source 11` và `-target 11` tương ứng. Nó không tự làm JDK 17 biến thành môi trường API Java 11.

**Quan trọng:** một số thuộc tính có thể được plugin khác hoặc cấu hình task riêng ghi đè. Khi cần chắc chắn compiler đã nhận những cờ nào, hãy kiểm tra JavaCompile task, Gradle logs và output class file; đừng suy ra chỉ từ một đoạn settings đã chép vào root.

### 4.3. Nếu chỉ đặt một trong hai thuộc tính?

Đặt `sourceCompatibility` nhưng quên target có thể khiến target được Gradle suy ra theo quy tắc/plugin đang áp dụng; đặt target thấp nhưng vẫn cho phép source syntax cao có thể tạo tổ hợp không hợp lệ với javac.

Đừng dựa vào giá trị suy diễn ngầm trong build quan trọng. Nếu đang cố ý dùng bộ đôi `sourceCompatibility`/`targetCompatibility` thay vì release, hãy khai báo **cả hai** một cách nhất quán và nhận thức rằng **API của compiler JDK có thể vẫn cao hơn mức mong muốn**.

## 5. `javac --release` hoạt động như thế nào?

Từ JDK 9, `javac` hỗ trợ `--release N` để cross-compile cho một Java SE release cũ **được compiler đó hỗ trợ**. Với một target release, nó áp dụng ba mặt:

1. Quy tắc ngôn ngữ nguồn cho release đó.
2. Class-file format phù hợp với release đó.
3. **Tập API Java SE được công bố** ở release đó, thay vì vô tình dùng những API mới hơn của JDK compiler.

Ví dụ với **JDK 17**:

```bash
javac --release 11 -d out src/main/java/demo/Main.java
```

Lệnh có nghĩa: dùng compiler đang chạy để tạo output có hợp đồng Java 11. Nó **không khởi chạy JDK 11**, không tự tải JDK 11 và không chạy chương trình sau khi compile.

### 5.1. `--release` giới hạn Java SE APIs, không phải mọi thư viện bên ngoài

Nếu mã nguồn dùng một third-party library được biên dịch cho Java 17, `--release 11` **không tự biến JAR đó thành một phiên bản tương thích Java 11**. Compiler có thể không đọc được class file mới hơn nếu version quá cao trong một số tổ hợp; nhưng ngay cả khi compile thành công, ứng dụng cũng có thể gặp lỗi runtime do thư viện bắc cầu hoặc implementation sử dụng API/JVM mới.

Vì vậy để phát hành cho Java 11, phải đánh giá:

- Bytecode của chính module.
- Java SE APIs được gọi từ chính module.
- Phiên bản/bytecode/API của **các thư viện bên ngoài**.
- Code sinh tự động, annotation processors và toolchain cho các task.
- Runtime tests trên JDK 11 thực tế.

**`--release 11` là kiểm soát compile-time rất mạnh, nhưng không phải chứng thư tự động cho toàn bộ ứng dụng hay hệ sinh thái dependency.**

### 5.2. Không kết hợp `--release` với `-source`/`-target` trong cùng lệnh javac

Hai kiểu cấu hình là các phương án khác nhau:

```bash
# Cách hiện đại: một release target thống nhất.
javac --release 11 -d out src/main/java/demo/Main.java
```

```bash
# Cách cũ: chỉ điều khiển source và class-file target.
javac -source 11 -target 11 -d out src/main/java/demo/Main.java
```

Không viết:

```bash
# Sai: --release không dùng đồng thời với -source/-target.
javac --release 11 -source 11 -target 11 Main.java
```

Tương tự trong Gradle, hãy có **một chiến lược compile target rõ ràng**. `options.release` được thiết kế để Gradle dùng `--release` thay cho các cờ `-source`/`-target` khi biên dịch task. Tránh dựa vào plugin không rõ nguồn tạo thêm cờ mâu thuẫn.

### 5.3. Một compiler không hỗ trợ mọi release trong lịch sử

`javac --release N` chỉ hoạt động cho các target mà **phiên bản javac hiện tại** còn hỗ trợ. Ví dụ javac từ JDK 8 **không có** tùy chọn `--release`. Một JDK rất mới cũng có thể không còn hỗ trợ release quá cũ.

Kiểm tra help của compiler được dùng:

```bash
javac --help
```

Và kiểm tra compiler version:

```bash
javac -version
```

Đừng lấy danh sách release mà một JDK hỗ trợ để áp dụng nguyên xi cho tất cả JDK khác.

## 6. Gradle `options.release.set(...)`: tương đương cấu hình `--release`

Gradle cung cấp property `JavaCompile.options.release` để cấu hình `javac --release` một cách rõ ràng.

### 6.1. Groovy DSL

**Một project Java dùng JDK 17 nhưng tạo classes phù hợp Java 11:**

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Đây là file build hoàn chỉnh cho một project Java thông thường. Nó không có task `run` vì chỉ dùng plugin `java`. `options.release = 11` thiết lập release target cho các JavaCompile tasks của project, bao gồm compile của source set main/test khi các tasks đó thuộc loại JavaCompile.

### 6.2. Kotlin DSL

```kotlin
plugins {
    java
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Kotlin DSL có typed property API: `options.release.set(11)`. Nếu script thiếu import trong bối cảnh không có accessor tương ứng, có thể dùng tên kiểu đầy đủ:

```kotlin
tasks.withType<org.gradle.api.tasks.compile.JavaCompile>().configureEach {
    options.release.set(11)
}
```

Đây là **cách viết thay thế** cho khối `tasks.withType<JavaCompile>()`, không phải một cấu hình bắt buộc phải thêm lần hai.

### 6.3. Vì sao dùng `configureEach`?

`tasks.withType<JavaCompile>().configureEach` áp dụng cấu hình cho những task JavaCompile phù hợp một cách lười, gồm cả task do plugin tạo sau. Nó không tự chạy compiler ở configuration phase.

Trong multi-project, khối trong `build.gradle.kts` của project `:core` chỉ cấu hình JavaCompile tasks của `:core`. Nếu muốn chính sách áp dụng cho mọi Java project, có thể đưa nó vào **convention plugin** rồi áp dụng plugin đó ở mỗi project phù hợp. Đừng lạm dụng `allprojects` để buộc những module không biên dịch Java cũng phải nhận release target.

### 6.4. Toolchain JDK 17 với release 11

Cấu hình này có chủ đích:

```text
JDK được dùng làm compiler: 17
Language features được phép: Java 11
Class-file target: Java 11, major version 55
Java SE platform API: Java 11
```

Nó giúp nhóm thống nhất compiler 17 trong CI, nhưng phát hành bytecode cho Java 11. **JDK 17 không tự động được chọn là mức API Java 17** khi `--release 11` đã được cấu hình.

Lưu ý nếu một task khác dùng compiler/plugin khác (Kotlin, Scala, Groovy, Android, code generation), nó **không tự nhận `JavaCompile.options.release`**. Các toolchains và bytecode targets của những ngôn ngữ khác phải được kiểm soát tương ứng.

## 7. Bài thực hành đầy đủ: Gradle Kotlin DSL + Java 17 toolchain → Java 11 release

Bài này không yêu cầu thư viện bên ngoài. Dự án sẽ:

1. Dùng plugin `application` để có task `run`.
2. Chọn **JDK 17** làm Java toolchain.
3. Biên dịch với `--release 11`.
4. Dùng một API được giới thiệu trong Java 11 (`String.repeat` và `String.strip`).
5. Kiểm tra class-file major version bằng `javap`.
6. Chạy trên JDK 11 thật nếu máy có, rồi thử một API mới hơn để thấy compiler từ chối.

### 7.1. Cấu trúc thư mục

```text
release-compat-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
```

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "release-compat-lab"
```

**File `build.gradle.kts`:**

```kotlin
plugins {
    application
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

application {
    mainClass.set("demo.Main")
}
```

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String prefix = "Java ".repeat(2);
        String message = (prefix + "11 API OK").strip();
        System.out.println(message);
    }
}
```

Đây là code Java 11 hợp lệ. `String.repeat(int)` và `String.strip()` có từ Java 11; không có dependency nào ngoài Java SE.

### 7.2. Chạy bằng Gradle Wrapper

Nếu project đã có Wrapper, dùng Wrapper. Nếu tạo một thư mục mới chưa có Wrapper, máy cần một bản Gradle tương thích để tạo Wrapper lần đầu:

```bash
gradle wrapper
```

Sau khi tạo Wrapper, trên Linux/macOS:

```bash
./gradlew --version
./gradlew --console=plain clean compileJava
./gradlew --quiet run
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat --console=plain clean compileJava
.\gradlew.bat --quiet run
```

**Stdout do chương trình Java tạo ra:**

```text
Java Java 11 API OK
```

Hai chữ `Java` là chủ ý: chuỗi `"Java "` được lặp hai lần rồi nối `"11 API OK"`. `strip()` không xóa dấu cách giữa các từ.

**Điều kiện:** bản Gradle phải chạy được trên JVM đang sử dụng và Gradle cần tìm được JDK 17 làm toolchain. Nếu không, build có thể lỗi trước khi compile. Việc Gradle tự tải JDK cho toolchain còn phụ thuộc cấu hình toolchain resolver; không nên giả định máy nào cũng có auto-download sẵn.

### 7.3. Đọc bytecode version

Sau `compileJava`:

```bash
javap -verbose build/classes/java/main/demo/Main.class
```

Tìm:

```text
major version: 55
```

`55` là class-file format tương ứng Java 11. Trong output dài của `javap -verbose` còn có constant pool, method descriptors và nhiều dòng khác; dòng trên chỉ là phần cần kiểm tra.

Một cách lọc trên Linux/macOS:

```bash
javap -verbose build/classes/java/main/demo/Main.class | grep "major version"
```

Trên Windows PowerShell:

```powershell
javap -verbose build\classes\java\main\demo\Main.class |
    Select-String "major version"
```

**Không nhầm `major version` của class file với phiên bản `javac`.** Dù compiler là JDK 17, major version vẫn là 55 vì chúng ta chủ động dùng release 11.

### 7.4. Chạy trên một runtime Java 11 thật

Nếu có cài JDK/JRE 11, hãy dùng `java` của phiên bản 11 để kiểm chứng. Trước hết:

```bash
java -version
```

Chỉ khi output cho biết đó là Java 11, chạy:

```bash
java -cp build/classes/java/main demo.Main
```

Kết quả mong đợi:

```text
Java Java 11 API OK
```

Nếu `java -version` cho Java 17, lệnh vẫn có thể chạy nhưng **chưa chứng minh chương trình chạy trên Java 11**. Muốn xác nhận yêu cầu tương thích, phải chạy trên runtime 11 thực hoặc môi trường kiểm thử được cấu hình rõ dùng Java 11.

Với ứng dụng có thư viện external, chỉ truyền `build/classes/java/main` vào classpath là không đủ; bài này không có external libraries nên lệnh trên độc lập được.

## 8. Thí nghiệm có chủ đích: code Java 15 không được vào release 11

Trong **bản sao** project ở mục 7, thay riêng phần thân `main` bằng:

```java
public static void main(String[] args) {
    String message = "Hello, %s".formatted("Gradle");
    System.out.println(message);
}
```

Đây là **mảnh phương thức để thay** bên trong `class Main`, không phải file Java độc lập. `String.formatted(Object...)` được đưa vào Java 15, nên khi task JavaCompile dùng `--release 11`, Gradle/javac phải từ chối lời gọi method này.

Chạy:

```bash
./gradlew --console=plain clean compileJava
```

Lỗi sẽ nêu không tìm thấy method `formatted` tương ứng trên `String` của API release 11. Nội dung thông báo cụ thể phụ thuộc javac/Gradle, không cần ghi nhớ chính xác từng ký tự.

Để hiểu hiện tượng:

- JDK 17 compiler **có** API `String.formatted` nếu compile cho Java 17.
- `--release 11` **cố ý ẩn API chưa tồn tại** trong Java 11.
- Đây là một **lỗi được mong đợi** của cơ chế bảo vệ tương thích, không phải Gradle bị hỏng.

Nếu đổi `options.release.set(17)`, đoạn Java 15 API này có thể compile được vì nằm trong API Java 17. Nhưng output giờ không còn được phát hành cho Java 11: target bytecode tương ứng sẽ khác và thiết kế tương thích đã thay đổi.

Sau thí nghiệm, **khôi phục code `Main.java` và `options.release.set(11)`** của mục 7.

## 9. Thí nghiệm thứ hai: `-source 8 -target 8` vẫn có thể làm lộ API Java 9

Để kiểm chứng bằng `javac` độc lập, ngoài Gradle, tạo file `ApiLeak.java` sau:

```java
import java.util.List;

public final class ApiLeak {
    private ApiLeak() {
    }

    public static void main(String[] args) {
        System.out.println(List.of("A", "B").size());
    }
}
```

### 9.1. Dùng compiler JDK 17 với `-source` và `-target`

Chạy trong thư mục chứa file, với `javac` thực sự từ JDK 17:

```bash
javac -source 8 -target 8 ApiLeak.java
javap -verbose ApiLeak.class
```

Có thể thấy cảnh báo về system modules/bootstrap classpath vì compile target cũ mà không ràng buộc Java 8 API. `javap` hiển thị:

```text
major version: 52
```

`52` là định dạng bytecode Java 8. Tuy nhiên code đã compile với `List.of`, vì API đó tồn tại trên JDK compiler 17. Trên Java 17:

```bash
java ApiLeak
```

Stdout:

```text
2
```

Trên **Java 8 thực tế**, method `java.util.List.of` không tồn tại, nên chương trình gặp lỗi khi thực hiện lời gọi. Đây là ví dụ “bytecode chạy trên JVM cũ nhưng API runtime quá mới” mà chỉ nhìn `major version` không phát hiện được.

### 9.2. Dùng `--release 8`

Xóa `ApiLeak.class` hoặc biên dịch sang một thư mục output khác, rồi chạy:

```bash
javac --release 8 -d checked ApiLeak.java
```

Compiler từ chối lời gọi `List.of(...)` vì Java SE 8 không có API đó. Nội dung lỗi thường cho biết `cannot find symbol` đối với `method of(...)`, nhưng đừng dựa vào một chuỗi stderr cố định giữa các JDK updates.

Không có lý do gọi `java ApiLeak` sau một lệnh `javac --release 8` thất bại rồi coi đó là kết quả của lệnh lỗi: nếu `ApiLeak.class` cũ còn trong thư mục, `java` có thể đang chạy **file cũ**. Hãy tách output directories hoặc kiểm tra file được tạo để tránh chẩn đoán sai.

### 9.3. Bảng kết quả dự kiến

| Lệnh chạy với JDK 17 | Cấp cú pháp | Bytecode | API Java được kiểm soát ở mức nào? | Kết quả với `List.of` |
| --- | --- | --- | --- | --- |
| `javac ApiLeak.java` | Mặc định theo compiler | Mặc định theo compiler | API JDK 17 | Compile thành công |
| `javac -source 8 -target 8 ApiLeak.java` | Java 8 | Java 8 (major 52) | Vẫn có thể thấy API JDK 17 | Có thể compile, gây lỗi runtime Java 8 |
| `javac --release 8 ApiLeak.java` | Java 8 | Java 8 (major 52) nếu compile được | **Giới hạn Java SE 8 API** | Compile thất bại |
| `javac --release 11 ApiLeak.java` | Java 11 | Java 11 (major 55) | Giới hạn Java SE 11 API | Compile thành công vì `List.of` có từ Java 9 |

Đây là cách học cụ thể sự khác nhau giữa **cú pháp**, **class-file version** và **platform APIs** mà Gradle đang điều phối.

## 10. Mối quan hệ giữa Gradle toolchain và Gradle runtime JVM

Có ít nhất ba “phiên bản Java” xuất hiện trong một build:

| Tên | Công việc | Kiểm tra/cấu hình |
| --- | --- | --- |
| JVM chạy Gradle | Chạy Gradle daemon, plugin/build logic | `./gradlew --version`, Gradle JVM của IDE, cấu hình môi trường |
| Java toolchain cho compiler | Cung cấp `javac` cho JavaCompile | `java.toolchain.languageVersion`; `javaToolchains` |
| Release target | Định hướng source/bytecode/Java SE API muốn hỗ trợ | `options.release`, kiểm tra `javap` |

Ví dụ Gradle chạy bằng JDK 21, nhưng Java toolchain chọn JDK 17 và `options.release.set(11)`. Nếu phiên bản Gradle hỗ trợ Java 21 làm runtime và có JDK 17 toolchain, đây vẫn có thể là một build hợp lệ. Trái lại, không phải Gradle cũ nào cũng chạy được trên JDK 21.

Các lệnh hữu ích:

```bash
./gradlew --version
./gradlew javaToolchains
./gradlew compileJava --info
```

- `--version` giúp xem phiên bản Gradle và JVM thực tế đang chạy công cụ.
- `javaToolchains` liệt kê những toolchain Gradle phát hiện/cấu hình.
- `compileJava --info` giúp kiểm tra compiler mà Gradle sử dụng và lý do task thực thi hoặc bị bỏ qua.

Nếu bạn gọi `javac -version` từ terminal, đó là `javac` trên `PATH`, **không chắc là compiler mà Gradle toolchain đã chọn**. Hãy xem JavaCompile task/toolchain thay vì suy luận từ terminal.

### 10.1. Toolchain không tự tải JDK ở mọi môi trường

Khi cấu hình:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

Gradle yêu cầu một JDK 17 đáp ứng spec. Nó có thể tìm JDK đã cài, hoặc sử dụng khả năng provisioning nếu môi trường đã cấu hình toolchain download resolver và mạng/permission phù hợp. Nếu không có JDK thỏa yêu cầu, Gradle có thể báo “No matching toolchains found”.

Đừng sửa lỗi đó bằng cách thay `options.release.set(17)` một cách ngẫu nhiên; release target không làm xuất hiện compiler JDK 17.

## 11. Nên đặt release ở extension hay trên JavaCompile task?

`JavaPluginExtension` thường cấu hình `sourceCompatibility` và `targetCompatibility` ở cấp project; `JavaCompile.options.release` đặt yêu cầu trực tiếp cho từng task JavaCompile.

**Kotlin DSL — cách ưu tiên khi muốn đảm bảo API mục tiêu:**

```kotlin
plugins {
    java
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Không cần đồng thời khai báo:

```kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
```

ở cùng project chỉ để nhắc lại release target đã được kiểm soát bằng `options.release.set(11)`. Mặc dù Gradle có logic để ưu tiên `options.release` trên các JavaCompile tasks, việc giữ **một nguồn cấu hình target** giúp người bảo trì đỡ nhầm và tránh plugin tùy chỉnh tự thêm compiler args không tương thích.

### 11.1. Không thêm `--release` thủ công vào compilerArgs khi đã dùng property

Ví dụ không nên:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
    options.compilerArgs.addAll(listOf("--release", "8"))
}
```

Một task không nên phát ra hai release target khác nhau. Hãy dùng typed property `options.release`, không ghi cờ trùng mâu thuẫn trong `compilerArgs`.

### 11.2. Cảnh giác với cấu hình ở root project

Trong multi-project, đặt `tasks.withType<JavaCompile>()` tại root chỉ tác động các task của root, không tự áp dụng vào `:api`, `:service` hoặc `:app`. Một lựa chọn tốt là tạo **convention plugin** cho Java và áp dụng ở các project cần compile:

```kotlin
// Mảnh cấu hình trong convention plugin đã áp dụng Java plugin.
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Đây là **mảnh mã**, không phải toàn bộ file plugin độc lập. Trong một convention plugin, cần đảm bảo Java plugin/extension đã sẵn có và DSL được compile đúng ngữ cảnh. Tránh áp đặt release 11 lên một project cần API Java 17 mà chưa có chính sách module rõ.

## 12. Test bằng Java 11: kiểm tra thật chứ không chỉ nhìn bytecode

`--release 11` giúp ngăn API Java SE mới trong source module, nhưng **không thay thế kiểm thử runtime thực tế**.

Một dự án có thể:

- Compile source chính thành class-file 55.
- Nhưng dependency thứ ba có class-file 61 (Java 17).
- Hoặc dùng reflection để gọi API mới chỉ khi chạy.
- Hoặc cần một native library/JNI mà JDK 11 không cung cấp.
- Hoặc sử dụng đường code không được test trên Java 11.
- Hoặc có plugin packaging/agent/runtime option không phù hợp JDK 11.

Vì vậy với thư viện cam kết hỗ trợ Java 11, nên kiểm tra ít nhất:

1. `compileJava` bằng JDK toolchain đã chọn với `options.release.set(11)`.
2. `javap` cho bytecode của module.
3. Dependency runtime graph và Java baseline của dependencies.
4. `test` chạy bằng Java 11 hoặc một JVM matrix gồm Java 11 và JDK phát triển.
5. Ứng dụng/JAR thực tế chạy trên Java 11.

### 12.1. Task test có thể dùng launcher Java 11

Nếu có cả JDK 17 (compiler) và JDK 11 (runtime test), Gradle có thể chọn Java launcher riêng cho `Test`:

```kotlin
val java11 = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(11))
}

tasks.withType<Test>().configureEach {
    javaLauncher.set(java11)
}
```

**Đây là mảnh cấu hình Kotlin DSL bổ sung** trong project đã áp dụng Java plugin. Nó không thể tự chạy nếu máy không có JDK 11 hoặc không có resolver phù hợp để provision nó. Đặt launcher 11 cho `Test` giúp kiểm thử Java 11 compatibility của code/test dependencies theo runtime thực.

**Lưu ý:** nếu bạn đã áp dụng `options.release.set(11)` cho **tất cả** JavaCompile tasks, mã test cũng cần phù hợp Java 11. Một framework test/version chạy bằng Java 17 sẽ không thể được dùng nguyên trên launcher Java 11 nếu bytecode hoặc yêu cầu runtime quá cao. Nên chọn test libraries phù hợp baseline.

### 12.2. `JavaExec`/`run` có thể cần cấu hình launcher riêng

Trong project `application`, task `run` của Gradle dùng Java runtime do task/Java toolchain cung cấp theo cấu hình. Chỉ vì compiler dùng `--release 11` **không tự chứng minh** task `run` đang chạy JDK 11. Nếu cần kiểm chứng chắc, hãy chạy với `java -version` của JDK 11 hoặc chỉ định Java launcher 11 rõ ràng cho task run/JavaExec.

## 13. Thư viện bên ngoài, annotation processors và code generation

Giả sử dự án muốn phát hành cho Java 11 nhưng dùng dependency:

```kotlin
dependencies {
    implementation("com.example:library:2.0.0")
}
```

Đây là ví dụ tọa độ giả, không phải artifact Maven đã được xác nhận tồn tại. Nếu `library:2.0.0` được biên dịch thành bytecode Java 17 và được đưa vào runtime, việc `Main.class` của bạn là major 55 cũng **không kéo thư viện về Java 11**.

Hãy kiểm tra:

- Các `compileClasspath`/`runtimeClasspath` của module.
- Những Java target/JVM variants mà Gradle chọn cho dependency.
- Tài liệu Java baseline của thư viện.
- Test runtime thật ở Java 11.
- Nội dung JAR nếu cần (`javap`, `jar tf`, metadata của artifact).

### 13.1. Annotation processors chạy ở compiler JDK, không phải target runtime

Một annotation processor thường được thực thi trong **quá trình biên dịch** và có thể cần JDK mới để chạy; phần generated Java source của nó vẫn phải thỏa release target khi được biên dịch bởi task đó. Không nên nhầm phiên bản Java mà annotation processor **cần để chạy** với Java phiên bản tối thiểu của **mã được sinh ra**.

Nếu generated source gọi `String.formatted` nhưng target là `--release 11`, compiler có thể phát hiện lỗi. Nếu generated bytecode được tạo bằng một công cụ riêng thay vì JavaCompile, cần kiểm tra target của công cụ ấy độc lập.

### 13.2. Không áp dụng `JavaCompile.options.release` cho mọi loại ngôn ngữ

Kotlin/JVM có `jvmTarget` hoặc compiler options riêng. Scala/Groovy/Android toolchains có những ràng buộc khác. `options.release.set(11)` trên `JavaCompile` không tự đổi class-file version cho Kotlin classes.

Trong một module trộn Java/Kotlin, cần quản lý cả `JavaCompile` và `KotlinCompile` JVM target/compiler theo chính sách thống nhất. Nếu hai nhóm class được biên dịch cho baseline khác nhau, cả artifact vẫn có thể không chạy được trên runtime cũ.

## 14. Bảng major version của class file thông dụng

| Java SE | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |

Các giá trị dùng để đọc lỗi dạng `UnsupportedClassVersionError`. Ví dụ một JAR chứa class major `61` sẽ không được JVM Java 11 (hiểu tối đa major 55) chạy như class Java 11. Dù code source nhìn “đơn giản”, class-file version vẫn quyết định JVM tối thiểu có thể load nó.

Đừng suy ra Java SE API compatibility **chỉ** từ bảng major: major 52 không ngăn class tham chiếu API chưa có ở Java 8, như `List.of` trong mục 9.

### 14.1. Đọc `UnsupportedClassVersionError`

Một lỗi có thể có nội dung tương đương:

```text
class file version 61.0
this version of the Java Runtime only recognizes class file versions up to 55.0
```

Thông điệp cho biết **bytecode Java 17** đang được tải trên **runtime Java 11**. Hướng xử lý tùy hợp đồng:

- Nếu chương trình phải hỗ trợ Java 11: build lại toàn bộ artifact liên quan bằng target Java 11, kiểm tra dependencies.
- Nếu ứng dụng thực sự yêu cầu Java 17: chạy bằng Java 17 tương thích.
- Nếu lỗi ở plugin Gradle chứ không phải app: kiểm tra JVM chạy Gradle và plugin compatibility, không chỉ thay JavaCompile target của app.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| `invalid source release: 17` | Compiler thực tế quá cũ để hiểu source level 17 | Kiểm tra JDK toolchain, `compileJava --info` |
| `release version 17 not supported` | `javac` được chọn không hỗ trợ release 17 | Chọn compiler JDK đủ mới hoặc target phù hợp |
| `--release 11` báo không có method `formatted` | API thuộc Java 15, không có ở Java 11 | Dùng API Java 11 hoặc đổi baseline có chủ đích |
| `-source 8 -target 8` compile nhưng Java 8 runtime lỗi `NoSuchMethodError` | Dùng API mới của compiler JDK | Dùng `--release 8` và runtime test |
| Runtime báo class file major 61 trên Java 11 | Artifact có bytecode Java 17 | Rebuild với target 11 hoặc nâng runtime |
| Gradle không tìm thấy JDK 17 toolchain | JDK chưa cài/resolver không có | Cài JDK phù hợp hoặc cấu hình resolver được phê duyệt |
| `javac -version` là 17 nhưng Gradle dùng 11 | PATH không phải Gradle toolchain | Xem `javaToolchains` và JavaCompile info |
| `java -version` là 17 nhưng app phải hỗ trợ 11 | Chưa test runtime 11 | Chạy bằng JVM 11 thật, kiểm tra transitive deps |
| `options.release` được đặt nhưng Kotlin classes target 17 | JavaCompile không điều khiển Kotlin compiler | Cấu hình Kotlin JVM target riêng |
| Annotation processor báo lỗi API/JDK | Processor được chạy bằng JDK compiler và có yêu cầu riêng | Kiểm tra version processor/JDK, generated source |
| Build fail khi kết hợp `-source`, `-target`, `--release` | Compiler args mâu thuẫn | Chọn một chiến lược, loại cờ trùng |
| Class major 55 nhưng app vẫn lỗi khi chạy Java 11 | Dependency/reflective API/native code quá mới | Xem toàn bộ runtime graph, test trên JVM 11 |
| Root build đặt release mà subproject không nhận | Phạm vi task configuration chỉ ở root | Đưa vào convention plugin/applied per project |
| Đổi sourceCompatibility mà không đổi target | Bộ source/target không nhất quán hoặc bị suy ra | Kiểm tra JavaCompile task và cấu hình tập trung |
| Gradle Plugin báo lỗi runtime JVM | Plugin chạy trên JVM Gradle, không phải Java target của app | Xem Gradle Wrapper/JVM/plugin compatibility |
| Test chạy JDK 17 nên không phát hiện lỗi Java 11 | Test launcher không phải baseline runtime | Cấu hình launcher 11 hoặc CI matrix |
| `javap` xem file class cũ | Không clean hoặc đọc output directory sai | Xóa output cũ trong vùng build, compile lại và kiểm tra đường dẫn |

### 15.1. Checklist debug theo từng lớp

**Lớp 1 — compiler toolchain**

```bash
./gradlew --version
./gradlew javaToolchains
./gradlew compileJava --info
```

Xác nhận Gradle chạy trên JVM nào, task JavaCompile có compiler JDK nào và nó có thực thi hay bị up-to-date.

**Lớp 2 — target/source/Java SE API**

Đọc `java.sourceCompatibility`, `java.targetCompatibility` hoặc `options.release`; đảm bảo không có compiler args tùy biến mâu thuẫn. Nếu lỗi “cannot find symbol” với một method JDK, kiểm tra method đó ra đời từ Java mấy.

**Lớp 3 — class-file output**

```bash
javap -verbose build/classes/java/main/demo/Main.class
```

Tìm major version. Nếu path không có file, kiểm tra source package, project path và output directory thật.

**Lớp 4 — runtime**

Chạy `java -version` với JVM được chọn, kiểm tra các JAR được đưa vào runtime. Không dựa vào một lớp của chính app khi còn dependencies có target cao hơn.

**Lớp 5 — CI**

So sánh Gradle Wrapper, JDK toolchains, Java runtime tests, architecture và các dependencies được resolve. Một laptop dùng JDK 17 làm runtime sẽ không tự phát hiện mọi vấn đề khi sản phẩm phải chạy trên Java 11.

## 16. Khi nào dùng `sourceCompatibility`/`targetCompatibility`, khi nào dùng `options.release`?

### Trường hợp A — bài học về compiler flags cũ hoặc build legacy

Nếu build cần dùng toolchain/compile flags theo cơ chế cũ vì một plugin hoặc cấu trúc đặc biệt, có thể cấu hình rõ:

```kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_11
    targetCompatibility = JavaVersion.VERSION_11
}
```

Nhưng phải hiểu nó **không tương đương đầy đủ** với kiểm soát Java SE APIs của `--release`. Nếu compiler có JDK mới, cần thêm biện pháp đáng tin để tránh API leak khi target cũ.

### Trường hợp B — phát hành thư viện Java 11 nhưng biên dịch bằng JDK 17

Nên ưu tiên:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Vì nó thể hiện rõ “compiler JDK 17; Java SE baseline 11”. Kết hợp với tests chạy Java 11, kiểm soát dependencies/runtime graph và CI matrix.

### Trường hợp C — project chỉ hỗ trợ Java 17

Có thể chọn toolchain 17 và release 17 khi muốn công bố một target rõ ràng:

```kotlin
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Khi source target bằng toolchain JDK và dùng Java SE API cùng release, cấu hình `--release 17` vẫn mang ý nghĩa làm target rõ ràng; nó không hạ mức tương thích xuống 11. Đừng đặt 11 chỉ vì “phiên bản thấp chạy được nhiều nơi” nếu project thực sự cần Java 17 API/feature.

### Trường hợp D — phải chạy Java 8 trong hệ thống cũ

Có thể dùng JDK mới hỗ trợ `--release 8` để compile Java 8 source/bytecode/API. Nhưng Java 8 runtime phải được kiểm thử thực tế và third-party libraries phải tương thích. Nếu compiler được chọn không hỗ trợ release 8 hoặc plugin build đã yêu cầu Java mới, cần một kế hoạch tương thích đầy đủ, không sửa một biến `targetCompatibility` đơn lẻ.

## 17. Bộ lệnh đối chiếu Gradle với `javac`

| Việc cần kiểm tra | Lệnh hoặc cấu hình |
| --- | --- |
| Gradle và JVM chạy Gradle | `./gradlew --version` |
| Những Java toolchains Gradle thấy | `./gradlew javaToolchains` |
| Compiler và task JavaCompile | `./gradlew compileJava --info` |
| Release target trong Gradle | `options.release.set(11)` |
| Cú pháp Java 11 bằng javac | `javac -source 11` |
| Class-file Java 11 bằng javac | `javac -target 11` (trong cặp cấu hình phù hợp) |
| Cú pháp + bytecode + Java SE 11 API | `javac --release 11` |
| Xem major version của output | `javap -verbose <đường-dẫn-class>` |
| Kiểm tra Java runtime | `java -version` |
| Chạy ứng dụng Gradle | `./gradlew run` nếu plugin application đã áp dụng |
| Chạy với Java 11 thật | Dùng `java` của JDK/JRE 11 đã được kiểm chứng |
| Xác định lỗi API mới | Tài liệu Java API + release tối thiểu có method/class đó |

Trong bảng, cụm `<đường-dẫn-class>` là mô tả cú pháp chung; ở bài thực hành có đường dẫn thực `build/classes/java/main/demo/Main.class`. Không hiểu các ký hiệu minh họa là tên file phải có trên máy.

## 18. Bài tập thực hành

**Bài tập A — dự đoán tương thích.** Cho JDK 17, `-source 8 -target 8` và mã gọi `List.of`. Dự đoán compile, class-file major, kết quả khi chạy trên Java 17 và Java 8. Giải thích vì sao kết quả runtime khác nhau.

**Bài tập B — xác minh `--release`.** Tạo `ApiLeak.java` ở mục 9. Chạy lần lượt `javac -source 8 -target 8` và `javac --release 8` (sử dụng output dirs tách biệt). Ghi lại khác biệt thông báo lỗi.

**Bài tập C — build Gradle Java 11.** Tạo project mục 7, chạy `./gradlew clean compileJava run`, đọc stdout `Java Java 11 API OK` và dùng `javap` xác nhận major 55.

**Bài tập D — dùng một API mới hơn Java 11.** Trong bản sao project, đổi `main` gọi `String.formatted`. Vì sao `--release 11` từ chối dù compiler là JDK 17? Khi đổi sang release 17, điều gì xảy ra với bytecode target?

**Bài tập E — chuyển đổi DSL.** Chuyển `build.gradle.kts` của ví dụ sang Groovy DSL. Bảo đảm có `plugins { id 'application' }`, `toolchain.languageVersion = JavaLanguageVersion.of(17)` theo cú pháp Groovy phù hợp, `options.release = 11` và `mainClass = 'demo.Main'`. Dự đoán output có thay đổi không.

**Bài tập F — test Java 11 thật.** Trên một máy có JDK 11 và 17, kiểm tra `java -version` rồi chạy `Main.class` được build bằng release 11 trên Java 11. Tại sao chạy trên Java 17 chưa đủ để công bố hỗ trợ Java 11?

**Bài tập G — bytecode của dependencies.** Thêm một JAR được build cho Java 17 vào một ứng dụng Java 11 (ở môi trường thử nghiệm). Vì sao class của app major 55 không bảo đảm cả ứng dụng chạy được trên Java 11?

**Bài tập H — phạm vi multi-project.** Có `:api` dùng Java 11 và `:app` dùng Java 17. Hãy mô tả cách viết convention plugin hoặc cấu hình riêng theo từng project để không vô tình đặt release 11 cho mọi JavaCompile task.

**Bài tập I — toolchain không tìm thấy.** Cấu hình Java toolchain 17 trên máy chỉ có JDK 11. Quan sát thông báo và giải thích tại sao đổi `sourceCompatibility`/`targetCompatibility` không cài thêm compiler JDK 17.

**Bài tập J — phân biệt plugin và runtime.** Giả sử plugin Gradle chỉ chạy trên Java 17 nhưng thư viện của bạn nhắm Java 11. Hai mục tiêu có mâu thuẫn không? Bạn cần kiểm tra JVM chạy Gradle, compiler toolchain và runtime tests riêng thế nào?

### Câu hỏi tự kiểm tra

1. `sourceCompatibility` kiểm soát cú pháp hay Java SE API?
2. `targetCompatibility` kiểm soát điều gì trong file `.class`?
3. Vì sao target bytecode 52 không đảm bảo một ứng dụng dùng API Java 8?
4. `javac --release 11` áp dụng những ràng buộc nào cùng lúc?
5. Tại sao không nên kết hợp `--release` và `-source/-target` trên cùng javac invocation?
6. Gradle `options.release.set(11)` có tự chọn compiler JDK 11 không?
7. Java toolchain 17 có tự quyết định app được chạy trên Java 11 không?
8. Java 11 class-file major version là bao nhiêu? Java 17 là bao nhiêu?
9. `List.of` thuộc Java 9: điều gì xảy ra khi compile với `--release 8`?
10. `String.formatted` thuộc Java 15: có dùng được khi build `--release 11` không?
11. Vì sao phải kiểm tra dependency runtime graph của thư viện Java 11?
12. Vì sao `javac -version` trên shell có thể khác Gradle JavaCompile compiler?
13. Gradle Wrapper khác Java toolchain ở điểm nào?
14. Có thể dùng JDK 21 làm Gradle runtime, JDK 17 làm compiler và release 11 làm target không, với điều kiện gì?
15. Làm sao đảm bảo test task thực sự chạy trên Java 11?
16. `JavaCompile.options.release` có tự điều khiển KotlinCompile/JVM target không?
17. Khi gặp `UnsupportedClassVersionError`, nên kiểm tra bytecode của đối tượng nào?
18. Vì sao chạy `java ApiLeak` ngay sau một lần javac thất bại dễ dẫn đến kết luận sai?
19. Khi nào cần dùng source/target legacy và khi nào ưu tiên release?
20. Những kiểm tra nào cần bổ sung ngoài `--release` để cam kết hỗ trợ Java 11?

**Tài liệu tham khảo chính thức:** [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html), [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html), [Oracle javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html), [Java class file format (JVMS)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).

**Ghi nhớ:** `sourceCompatibility` là **mức cú pháp Java**, `targetCompatibility` là **mức bytecode**, còn `options.release` / `javac --release` là cách phù hợp để **giới hạn đồng thời cú pháp, bytecode và API Java SE theo release mục tiêu** khi cross-compile. Java toolchain chọn JDK compiler; kiểm thử runtime cũ và kiểm tra third-party dependencies vẫn cần thiết để bảo đảm tương thích thực sự.