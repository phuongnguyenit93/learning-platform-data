# Annotation processing và khai báo processor đúng configuration trong Gradle

**Annotation processing** là một phần của quá trình biên dịch Java: `javac` có thể nạp những chương trình nhỏ gọi là *annotation processors*, cho chúng phân tích các kiểu/annotation trong source và tạo thêm mã Java, tài nguyên hoặc metadata. Gradle điều phối việc đó qua các task `JavaCompile`, đặc biệt là `compileJava` và `compileTestJava`. Bài toán thường gây lỗi không phải vì annotation viết sai, mà vì **annotation API** và **mã processor** được khai báo ở **nhầm Gradle configuration**.

Ví dụ với **MapStruct**: mã nguồn import `@Mapper` từ `org.mapstruct:mapstruct`, còn công việc tạo class `PersonMapperImpl` do `org.mapstruct:mapstruct-processor` thực hiện. Hai artifact có vai trò khác nhau:

```kotlin
dependencies {
    implementation("org.mapstruct:mapstruct:1.6.3")
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}
```

Hoặc với **Lombok**, cùng một artifact chứa annotation types và logic processor, nên thường khai báo **hai lần ở hai phạm vi**:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.48")
    annotationProcessor("org.projectlombok:lombok:1.18.48")
}
```

Hai dòng Lombok không phải khai báo thừa: dòng đầu phục vụ **biên dịch source**, dòng sau phục vụ **thực thi processor**. Bỏ một dòng có thể khiến `@Getter` không được nhận diện hoặc getter không được sinh.

Bài học này nằm trong phần **Biên dịch và tài nguyên** của Build Tool Gradle. Sau khi học, bạn sẽ phân biệt chính xác annotation và annotation processor; hiểu JSR 269 và các processing rounds; lựa chọn `annotationProcessor`, `testAnnotationProcessor`, `compileOnly`, `implementation`, `testCompileOnly`, `testImplementation`; chạy một project **Java 17 + Gradle Kotlin DSL + MapStruct + JUnit 5**; đọc generated sources, chẩn đoán processor path, nhận biết các thay đổi từ JDK 23, và tối ưu incremental compilation.

## 1. Annotation không có nghĩa compiler tự biết phải sinh code

Một Java annotation là metadata được định nghĩa bằng `@interface`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
```

Đây là **file Java định nghĩa annotation**, chưa có processor nào được viết. Nó có thể được áp dụng lên class:

```java
package demo;

@GenerateGreeting("Hello")
public class Example {
}
```

Nhưng chỉ vì source có `@GenerateGreeting` **không có nghĩa Java compiler tự tạo `ExampleGreeting.java`**. Cần một `javax.annotation.processing.Processor` có logic đọc annotation và yêu cầu `Filer` tạo file tương ứng.

Ngoài annotation processing, còn có nhiều cơ chế dùng annotations khác:

- **Compile-time validation**: processor kiểm tra quy tắc và phát diagnostics.
- **Source generation**: tạo Java source mới (MapStruct, Dagger, AutoService…).
- **Metadata/resource generation**: sinh file service descriptors, configuration hoặc tài nguyên build.
- **AST compiler transformation**: Lombok thay đổi compiler AST theo cơ chế riêng; không nhất thiết sinh một file `Getter.java` trên disk.
- **Runtime reflection**: một số frameworks đọc annotation có retention `RUNTIME` khi ứng dụng chạy; đây không phải annotation processing chạy lúc biên dịch.

**Phân biệt retention và processor**: `RetentionPolicy.SOURCE` nghĩa annotation không được giữ trong class file, nhưng vẫn có thể được processor xử lý trong lúc compile. `RetentionPolicy.RUNTIME` cho phép đọc qua reflection khi chạy; nó **không bắt buộc** processor phải chạy và không quyết định trực tiếp Gradle configuration.

## 2. `javac` làm annotation processing theo các vòng như thế nào?

Java annotation processing API thường được gọi là **JSR 269** (Pluggable Annotation Processing API). Những thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `javax.annotation.processing.Processor` | Contract mà compiler gọi để thực thi processor |
| `AbstractProcessor` | Base class giúp triển khai Processor |
| `ProcessingEnvironment` | Truy cập compiler utilities, options, filer, messager |
| `RoundEnvironment` | Danh sách elements được xét ở một processing round |
| `Element`, `TypeElement` | Mô hình declarations/type information |
| `Filer` | Tạo Java source/class/resource outputs |
| `Messager` | Phát warning/error/note tại compile time |
| `META-INF/services/javax.annotation.processing.Processor` | Service descriptor giúp `javac` phát hiện processor trên processor path |

Chu trình khái quát:

```text
src/main/java: @Mapper, @GenerateGreeting, ...
            |
            v
javac đọc source + compile classpath
            |
            v
Đọc processor path riêng
            |
            v
Phát hiện Processor implementations
            |
            v
Round 1: processor phân tích elements -> tạo source/resources
            |
            v
Round 2: source mới có thể mang annotation khác -> xử lý tiếp
            |
            v
Round cuối: không còn source mới cần xét
            |
            v
javac biên dịch source gốc + source sinh ra thành .class
```

Processor có thể được gọi **nhiều lần trong cùng một invocation**. Vì thế khi tự viết processor, không được tạo lặp lại cùng file `Filer.createSourceFile(...)` ở mọi round; phải kiểm tra elements và xử lý lifecycle đúng. Nếu không, có thể gặp `FilerException` vì file đã được tạo.

### Processors chạy ở đâu?

Processor được **thực thi trong môi trường compiler**, không phải trong JVM application đang chạy sau khi build hoàn tất. Một processor có thể dùng file I/O và code Java của chính nó để tạo source/metadata; không phải một annotation mà application tự chạy.

Đây là lý do processor path là một phần của **trusted build-time executable code**. Chỉ dùng processor từ nguồn tin cậy và kiểm tra dependencies/versions như với Gradle plugins.

## 3. Có ít nhất ba classpaths khác nhau

| Classpath/path | Ai dùng? | Cấu hình Gradle thường liên quan |
| --- | --- | --- |
| **Main compile classpath** | Compiler phải nhận diện kiểu import trong `src/main/java` | `implementation`, `api`, `compileOnly` |
| **Main annotation processor path** | Compiler nạp và thực thi processor cho `compileJava` | `annotationProcessor` |
| **Main runtime classpath** | JVM khi ứng dụng chạy | `implementation`, `runtimeOnly` và dependencies runtime phù hợp |
| **Test compile classpath** | Compiler biên dịch `src/test/java` | `testImplementation`, `testCompileOnly` và main outputs |
| **Test annotation processor path** | Compiler nạp processor cho `compileTestJava` | `testAnnotationProcessor` |
| **Test runtime classpath** | JVM và test engine chạy test | `testImplementation`, `testRuntimeOnly` và main/test outputs |

Một annotation type như `org.mapstruct.Mapper` cần được source compiler nhìn thấy, nhưng compiler cần **processor implementation** từ `mapstruct-processor` để tạo class `PersonMapperImpl`.

**Processor path không tự trở thành compile classpath.** Khai báo:

```kotlin
dependencies {
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}
```

không thay thế được dependency chứa **annotation types** mà Java source đang import. Ngược lại:

```kotlin
dependencies {
    implementation("org.mapstruct:mapstruct:1.6.3")
}
```

cho phép import `@Mapper` nhưng **không tự đưa `mapstruct-processor` vào processor path**.

Gradle tách hai vai trò vì compiler code và generated-code API có lifecycle, classloading, rủi ro và caching khác nhau.

## 4. Chọn đúng configuration: bảng quyết định

| Scope | Mục đích | Thông thường xuất hiện ở | Ví dụ |
| --- | --- | --- | --- |
| `implementation` | API/source library cần khi compile **và runtime** | Main compile + runtime | `org.mapstruct:mapstruct` nếu dùng `Mappers.getMapper` khi chạy |
| `api` | Dependency nằm trong public ABI của `java-library` | Compile API của library và consumer | Public method trả kiểu external API |
| `compileOnly` | Kiểu/annotation cần để compile main, không được tự đưa vào runtime | Main compile | `org.projectlombok:lombok` annotations |
| `annotationProcessor` | Mã Java processor chạy trong main `compileJava` | Main processor path | `mapstruct-processor`, Lombok processor |
| `runtimeOnly` | Module chỉ cần khi ứng dụng chạy | Main runtime | Một runtime provider/driver |
| `testImplementation` | Test source cần compile và run | Test compile + test runtime | JUnit Jupiter API/engine phù hợp |
| `testCompileOnly` | Kiểu/annotation chỉ cần khi compile tests | Test compile | Lombok annotations có trong test source |
| `testAnnotationProcessor` | Processor xử lý `src/test/java` | Test processor path | Lombok/MapStruct processor cho test-specific sources |
| `testRuntimeOnly` | Thành phần chỉ cần khi chạy tests | Test runtime | JUnit Platform launcher |
| `compileOnlyApi` | Public compile-time-only contract trong Java library | Library + consumer compile API | Annotation/type public chỉ phục vụ compile |

**Quy tắc phân loại:**

- Source cần `@Annotation`? → Cấp annotation API trên **compile classpath** thích hợp.
- Compiler cần chạy processor? → Cấp implementation trên **processor path** thích hợp.
- Runtime code gọi thư viện đó? → Chọn `implementation`/`runtimeOnly` theo source usage.
- Chỉ test source dùng annotation? → Dùng **test** scopes.
- Public API của một `java-library` lộ external type? → Xem xét `api`/`compileOnlyApi` cho type đó, **không tự công bố processor**.

### Không phải cứ annotation API là `compileOnly`

Lombok annotation types thường không cần runtime. Nhưng MapStruct thường được dùng với runtime factory:

```java
PersonMapper mapper = Mappers.getMapper(PersonMapper.class);
```

Class `Mappers` nằm trong **MapStruct API artifact**. Nếu dùng cách gọi này khi chạy, `org.mapstruct:mapstruct` cần hiện diện ở runtime; vì vậy `implementation` là chọn lựa đúng trong ví dụ. Không thay `implementation` bằng `compileOnly` chỉ vì thấy `@Mapper` là annotation.

## 5. Quy ước Gradle Java plugin và JavaCompile tasks

Trong `build.gradle.kts`:

```kotlin
plugins {
    java
}
```

Gradle Java plugin tạo các nhiệm vụ liên quan:

```text
src/main/java        -> compileJava        -> build/classes/java/main
src/test/java        -> compileTestJava    -> build/classes/java/test
src/main/resources   -> processResources
src/test/resources   -> processTestResources
```

`compileJava` có một thuộc tính riêng:

```kotlin
// Mảnh cấu hình task, không phải một build.gradle.kts hoàn chỉnh:
tasks.named<JavaCompile>("compileJava") {
    // Gradle tự thiết lập processor path từ Java plugin.
    // Thuộc tính đọc/truy cập: options.annotationProcessorPath
}
```

Mục đích của `annotationProcessor` configuration là cung cấp JARs để Gradle đặt lên **`JavaCompile.options.annotationProcessorPath`** khi compile main. Với `compileTestJava`, Java plugin có configuration riêng `testAnnotationProcessor`.

Các configurations `annotationProcessor` và `testAnnotationProcessor` được Gradle tạo khi áp dụng Java plugin; **không cần cài thêm plugin apt legacy chỉ để dùng Java annotation processors** ở các bản Gradle hiện đại.

Lưu ý: thông thường bạn khai báo bằng:

```kotlin
dependencies {
    annotationProcessor("group:processor-artifact:version")
}
```

chứ không đưa thủ công `-processorpath`/JAR filenames vào `options.compilerArgs`. Việc tự ghép processor path dễ gây thiếu transitive dependencies, sai separator Windows/Linux và làm Gradle khó theo dõi task inputs.

## 6. Ví dụ MapStruct hoàn chỉnh với Java 17 và Kotlin DSL

Ví dụ này làm rõ **Java API ở compile/runtime** và **processor chỉ được thực thi khi biên dịch**. Project có class `Person`, DTO `PersonDto`, interface `PersonMapper`. MapStruct tạo `PersonMapperImpl.java`; Java main gọi mapper và in kết quả.

### 6.1. Yêu cầu và cấu trúc

Cần:

- JDK/toolchain Java 17 phù hợp Gradle Wrapper version;
- Gradle Wrapper được project tạo/commit đúng cách;
- Maven Central có thể truy cập, hoặc Gradle cache đã có các artifacts;
- Không cần plugin Lombok hay plugin annotation-processing của bên thứ ba.

```text
mapstruct-gradle-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/
    │   ├── Person.java
    │   ├── PersonDto.java
    │   ├── PersonMapper.java
    │   └── Main.java
    └── test/java/demo/
        └── PersonMapperTest.java
```

`build/` chưa xuất hiện trước lần build đầu tiên; Gradle sẽ tạo thư mục outputs. Không commit `build/generated` như source code viết tay, trừ khi kiến trúc/project policy thực sự đòi một published generated artifact riêng.

### 6.2. `settings.gradle.kts`

```kotlin
rootProject.name = "mapstruct-gradle-demo"
```

### 6.3. `build.gradle.kts` — file đầy đủ

```kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

dependencies {
    // Chứa @Mapper và Mappers.getMapper() dùng lúc runtime.
    implementation("org.mapstruct:mapstruct:1.6.3")

    // Chứa code processor tạo PersonMapperImpl.
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")

    // JUnit chỉ thuộc test source/test runtime.
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.test {
    useJUnitPlatform()
}
```

**Vì sao `application`?** Đây là core Gradle plugin, tự áp dụng Java plugin, tạo `run` task và cung cấp `application { mainClass.set(...) }`. Các configurations `implementation`, `annotationProcessor`, `testImplementation`… có sẵn nhờ Java plugin.

**Vì sao MapStruct 1.6.3?** Đây là một bản phát hành ổn định được MapStruct tài liệu hóa với hai artifacts `mapstruct` và `mapstruct-processor`. Cố định cùng version của hai artifacts trong bài học để tránh rủi ro khác biệt API/processor. Nếu dự án dùng bản mới hơn, kiểm tra release notes và compatibility trước khi nâng.

**Vì sao chưa thêm `testAnnotationProcessor`?** Test chỉ sử dụng mapper được sinh từ **main Java source**; nó không khai báo một mapper annotation mới trong `src/test/java`. Main processor đã xử lý `PersonMapper` khi `compileJava`.

### 6.4. `src/main/java/demo/Person.java`

```java
package demo;

public final class Person {
    private final String name;
    private final int age;

    public Person(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }
}
```

Class `Person` là source model. MapStruct nhận diện public getters theo quy ước JavaBeans để lấy `name` và `age`.

### 6.5. `src/main/java/demo/PersonDto.java`

```java
package demo;

public final class PersonDto {
    private String name;
    private int age;

    public PersonDto() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
```

DTO có no-argument constructor và setters. Vì không dùng Lombok, ví dụ tránh phụ thuộc vào thứ tự/khả năng phối hợp giữa hai processors khác nhau. Chỉ cần MapStruct processor là đủ sinh code mapping.

### 6.6. `src/main/java/demo/PersonMapper.java`

```java
package demo;

import org.mapstruct.Mapper;

@Mapper
public interface PersonMapper {
    PersonDto toDto(Person source);
}
```

Đây là interface viết tay. Không có source file `PersonMapperImpl.java` do lập trình viên tạo trước build. `@Mapper` yêu cầu `org.mapstruct:mapstruct` trên main compile classpath, còn `mapstruct-processor` trên main annotation processor path sẽ **sinh implementation**.

### 6.7. `src/main/java/demo/Main.java`

```java
package demo;

import org.mapstruct.factory.Mappers;

public final class Main {
    public static void main(String[] args) {
        PersonMapper mapper = Mappers.getMapper(PersonMapper.class);
        PersonDto dto = mapper.toDto(new Person("Ada", 37));

        System.out.println(dto.getName() + "; age=" + dto.getAge());
    }
}
```

`Mappers.getMapper` là một API của MapStruct được gọi **khi chương trình chạy**, nên `mapstruct` phải có trên application runtime classpath. Class `PersonMapperImpl` được tạo lúc `compileJava`, biên dịch thành `.class`, rồi factory tìm class implementation theo quy ước MapStruct.

### 6.8. `src/test/java/demo/PersonMapperTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.mapstruct.factory.Mappers;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PersonMapperTest {
    @Test
    void mapsNameAndAge() {
        PersonMapper mapper = Mappers.getMapper(PersonMapper.class);

        PersonDto dto = mapper.toDto(new Person("Grace", 42));

        assertEquals("Grace", dto.getName());
        assertEquals(42, dto.getAge());
    }
}
```

Test compile dùng `@Test` và Assertions của JUnit Jupiter qua `testImplementation`. Nó sử dụng **implementation mapper của main** đã tạo trước, nên **không cần `testAnnotationProcessor`** trong demo này.

### 6.9. Lệnh chạy và stdout

Linux/macOS:

```bash
./gradlew clean compileJava --console=plain
./gradlew run --quiet
./gradlew test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean compileJava --console=plain
.\gradlew.bat run --quiet
.\gradlew.bat test --console=plain
```

Khi Gradle resolve được đúng artifacts và build thành công, **stdout của Java `Main.main`** là:

```text
Ada; age=37
```

Đây là kết quả từ method `System.out.println` trong Java source. Gradle có thể in logs, warnings hoặc progress tùy console/version; không nên khẳng định toàn bộ terminal luôn chỉ một dòng. JUnit test PASS có thể không in stdout từ chính test.

### 6.10. Xác nhận file được sinh ra

Sau `compileJava`:

```text
build/
├── generated/
│   └── sources/
│       └── annotationProcessor/
│           └── java/
│               └── main/
│                   └── demo/
│                       └── PersonMapperImpl.java
└── classes/
    └── java/
        └── main/
            └── demo/
                ├── Person.class
                ├── PersonDto.class
                ├── PersonMapper.class
                ├── PersonMapperImpl.class
                └── Main.class
```

Đường dẫn chính xác phụ thuộc Gradle plugin/tasks được cấu hình; với Java plugin thông thường, **`build/generated/sources/annotationProcessor/java/main` là mặc định**. Đừng tự tìm generated code dưới `src/main/java` nếu bạn không chủ ý thay đổi output directory.

Hình dung source do MapStruct sinh, **trích đoạn minh họa, không phải output byte-for-byte**:

```java
package demo;

public class PersonMapperImpl implements PersonMapper {
    @Override
    public PersonDto toDto(Person source) {
        if (source == null) {
            return null;
        }

        PersonDto dto = new PersonDto();
        dto.setName(source.getName());
        dto.setAge(source.getAge());
        return dto;
    }
}
```

Generated source thật có thể có comments, `@Generated`, imports và format khác theo version/options. Điều quan trọng là class thực thi interface, copy `name`/`age` và được `javac` biên dịch thành bytecode.

## 7. Thử lỗi có chủ đích: bỏ từng dependency

Dùng bản copy của project thực hành, không thử trên production branch.

| Bỏ/thay đổi | Hệ quả |
| --- | --- |
| Bỏ `implementation("org.mapstruct:mapstruct:...")` | `PersonMapper.java` không tìm thấy `org.mapstruct.Mapper`; `Main.java` cũng không tìm được `Mappers` |
| Bỏ `annotationProcessor("org.mapstruct:mapstruct-processor:...")` | Source `@Mapper` vẫn có thể compile nhưng **`PersonMapperImpl` không được sinh**; main có thể lỗi khi runtime factory tìm implementation |
| Đưa `mapstruct-processor` vào `implementation` thay vì `annotationProcessor` | Compiler có thể không chạy processor theo cấu hình Gradle đúng chuẩn; source generator không được bảo đảm hoạt động |
| Đặt `mapstruct-processor` chỉ vào `testAnnotationProcessor` | Chỉ phục vụ test compiler, không tạo mapper cho `src/main/java` |
| Bỏ `testImplementation` của JUnit | `PersonMapperTest.java` không biên dịch được vì `org.junit.jupiter.api` không có trên test compile classpath |
| Bỏ JUnit Platform launcher | Tùy Gradle/JUnit versions, test discovery/execution có thể thiếu launcher hoặc báo cảnh báo/lỗi |
| Thêm `-proc:none` | Vô hiệu hóa annotation processing, dù processor đã được khai báo |
| Xóa generated file rồi chạy `compileJava` khi task được Gradle coi up-to-date sai do cấu hình custom | Cần kiểm tra outputs/task inputs và build lifecycle; với Java plugin chuẩn, generated outputs được Gradle theo dõi |

Một điểm tinh tế của MapStruct: `Main.java` **không gọi tên `PersonMapperImpl` trực tiếp ở compile-time**. Vì vậy khi processor thiếu, `compileJava` vẫn có thể PASS, nhưng `Mappers.getMapper(PersonMapper.class)` ném exception lúc chạy do không tìm thấy implementation. Trái lại, nếu Java source viết:

```java
// Ví dụ minh họa sự cố:
PersonMapper mapper = new PersonMapperImpl();
```

thì compiler có thể báo `cannot find symbol: PersonMapperImpl` ngay trong compile vì generated class chưa được tạo. Cả hai là biểu hiện của cùng vấn đề processor không chạy, chỉ khác **lúc phát hiện lỗi**.

## 8. Lombok: cùng artifact ở cả `compileOnly` và `annotationProcessor`

Lombok phổ biến do annotation như `@Getter`, `@Setter`, `@Builder`, `@RequiredArgsConstructor`. Đối với Java source, cấu hình không cần plugin bổ sung:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    compileOnly("org.projectlombok:lombok:1.18.48")
    annotationProcessor("org.projectlombok:lombok:1.18.48")
}
```

Ví dụ source:

```java
package demo;

import lombok.Getter;

public final class Book {
    @Getter
    private final String title;

    public Book(String title) {
        this.title = title;
    }
}
```

Trong các Java classes khác sau khi compiler chạy Lombok:

```java
Book book = new Book("Gradle");
System.out.println(book.getTitle());
```

Đây là **mảnh code dùng sau khi cấu hình Lombok đầy đủ**, không phải Java file hoàn chỉnh để chạy riêng. Nó dựa vào getter được Lombok tạo trong bytecode/AST. Lombok có cách tích hợp sâu với `javac`, vì vậy không nhất thiết tạo `BookWithGetter.java` dưới generated source directory.

### Vì sao không dùng `implementation("lombok")`?

Trong trường hợp getter/builder được Lombok sinh trong bytecode, application **không cần** Lombok runtime library chỉ để gọi getter/builder đã tồn tại. `compileOnly` tránh đưa Lombok vào runtime classpath. `annotationProcessor` vẫn cần vì compiler phải thực thi Lombok.

Nếu code trực tiếp gọi một runtime API của một thư viện khác, cần đánh giá scope riêng theo runtime usage; không áp đặt `compileOnly` cho mọi annotations.

### Lombok trong test source

Nếu `src/test/java` có test classes tự dùng `@Getter` hoặc `@Builder`, bổ sung:

```kotlin
dependencies {
    testCompileOnly("org.projectlombok:lombok:1.18.48")
    testAnnotationProcessor("org.projectlombok:lombok:1.18.48")
}
```

Nếu tests **chỉ gọi getter đã được Lombok sinh trong main classes**, không cần khai báo lại test processor chỉ cho việc đó. Main `compileJava` đã hoàn tất code generation trước khi test compile.

## 9. Test processors phải được khai báo riêng khi test source có mapper

Thử một project dùng MapStruct và JUnit, trong đó **chính test source** định nghĩa một mapper:

```java
// src/test/java/demo/TestOnlyMapper.java
package demo;

import org.mapstruct.Mapper;

@Mapper
public interface TestOnlyMapper {
    PersonDto toDto(Person source);
}
```

Đây là **mảnh file bổ sung** vào ví dụ MapStruct; để test thực sự dùng implementation, viết test gọi `Mappers.getMapper(TestOnlyMapper.class)` và assert kết quả.

Thêm:

```kotlin
dependencies {
    // Nếu main implementation đã cung cấp MapStruct API cho test compile,
    // không cần lặp testImplementation mapstruct chỉ để thấy @Mapper.
    testAnnotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}
```

Còn nếu test source trong một project khác **chưa có MapStruct API trên test compile classpath**, khai báo thêm `testImplementation("org.mapstruct:mapstruct:1.6.3")` hoặc scope test thích hợp. Điểm quyết định là **classpath thật của test compiler**, không phải mong muốn rằng main processor tự kế thừa sang test.

Khi compile tests, code generated tương ứng thường nằm ở:

```text
build/generated/sources/annotationProcessor/java/test/demo/TestOnlyMapperImpl.java
```

Còn main processor outputs vẫn ở `.../main`. Hai bộ generated sources có đường biên khác nhau.

### Đừng lặp processor bừa cho test

Cấu hình `testAnnotationProcessor` không luôn cần:

- Test chỉ dùng public method do main source đã được generate: **không cần**.
- Test khai báo annotations `@Mapper`, `@AutoValue`, `@Getter` mới trong chính test source: **cần**, nếu muốn compiler chạy processor trong `compileTestJava`.
- Test chỉ đọc reflection metadata của annotation `RUNTIME`: có thể cần annotation runtime library, nhưng **không đồng nghĩa** cần annotation processor.
- Test uses a generated implementation in an external dependency: nó đã nằm trong external JAR nếu library tác giả build đúng; consumer **không cần chạy lại processor** của library.

## 10. JDK 23+ thay đổi mặc định annotation processing của `javac`

Trước Java 23, một invocation `javac` có thể **tự dò processors** trên classpath khi không được cấu hình rõ processor path; vì thế một số tutorial cũ chỉ thêm processor vào `implementation` rồi thấy code generation tình cờ hoạt động.

**Từ JDK 23**, `javac` mặc định **không tự kích hoạt annotation processing ngầm** nếu không có ít nhất một tùy chọn kích hoạt/thiết lập rõ:

- `-processor` để chỉ định processor class;
- `--processor-path` hoặc `-processorpath` để đặt processor search path;
- `--processor-module-path` với modular processors;
- `-proc:full` (xử lý annotations và biên dịch) hoặc `-proc:only` (chỉ xử lý annotations).

`-proc:none` luôn **tắt** annotation processing.

Hệ quả quan trọng đối với Gradle: **khai báo processor bằng `annotationProcessor` trên Java plugin là hướng chuẩn và an toàn hơn**, vì Gradle cấp processor path rõ ràng thay vì dựa vào việc `javac` quét bừa compile classpath. Với Gradle/JDK versions thực tế, nên kiểm tra compiler invocation bằng `--info` khi nghi cấu hình bị plugin/custom task override.

Đừng sửa lỗi trên JDK 23 bằng cách bỏ Gradle separation và thêm mọi processor vào `implementation`. Điều đó vừa sai scope, vừa có thể không kích hoạt processor như bạn tưởng.

### Toolchain JDK khác Daemon JVM

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

chỉ định compiler/JDK dùng cho Java tasks, **không tự thay đổi JDK chạy Gradle Daemon** và cũng không tự đưa processor artifact lên path. Nếu IDE/CI dùng toolchain 23 hoặc 25 trong khi local dùng 17, hành vi annotation processing khi dựa vào mặc định cũ có thể khác đáng kể.

**Quy tắc:** đối chiếu Gradle Wrapper, JVM chạy Gradle, Java toolchain, processor version và plugin versions. Khi nâng JDK, kiểm tra processor compatibility, đặc biệt với những processor tích hợp sâu vào `javac` internals như Lombok.

## 11. Đọc generated sources và chỉnh output directory

Java plugin tạo source generated mặc định tại:

```text
build/generated/sources/annotationProcessor/java/main
build/generated/sources/annotationProcessor/java/test
```

Đây là **outputs của `JavaCompile`**, không phải một `src/main/java` mới mà bạn phải quản lý bằng tay. Gradle thường biên dịch generated source cùng invocation, và Gradle IDE integrations có thể nhận diện vị trí này khi được import đúng.

Nếu muốn thay đổi output folder cho main processor:

```kotlin
// Mảnh ghép vào build.gradle.kts đã có Java plugin.
tasks.named<JavaCompile>("compileJava") {
    options.generatedSourceOutputDirectory.set(
        layout.buildDirectory.dir("generated/custom-apt/main")
    )
}
```

Điều này thay nơi nhận **generated Java sources** do annotation processors tạo. Chỉ đổi khi có yêu cầu thật; Gradle defaults thường đã đủ tốt.

**Không nhầm `options.generatedSourceOutputDirectory` với `destinationDirectory`:**

- `generatedSourceOutputDirectory`: Java source được processor tạo.
- `destinationDirectory`: bytecode `.class` sau biên dịch.
- `options.annotationProcessorPath`: JARs của processor, không phải nơi lưu outputs.

Đừng thêm một file generated source vào Git theo cách thủ công rồi tiếp tục giữ processor cũng tạo file đó ở mỗi build. Điều đó có thể gây duplicate class hoặc code lỗi thời. Trong project thông thường, `build/` nên được `.gitignore`, và generated source là **sản phẩm có thể tái tạo của compiler task**.

### Generated resources không phải source Java

Một processor còn có thể tạo `META-INF/services/...` hoặc metadata. Tùy API/Filer và cách Gradle giao output locations, tài nguyên đó có thể nằm trong class output hoặc thư mục task output khác. Đừng giả định mọi output của annotation processor đều là `.java` dưới `build/generated/sources`.

Nếu processor tạo file nằm ngoài locations mà Gradle theo dõi, incremental/up-to-date checks có thể không chính xác. Hãy ưu tiên processor tuân theo Filer/compiler outputs, và không dùng file I/O trực tiếp ra source tree trừ khi có thiết kế/task tracking rõ ràng.

## 12. Cách Gradle quyết định việc biên dịch lại

Java compile task có nhiều inputs:

```text
Java source files
    + compileClasspath (ABI / compile inputs)
    + annotationProcessorPath
    + compiler arguments & processor options
    + Java toolchain / compiler
    + declared external resource inputs
    -> compiled classes + generated sources/resources
```

Gradle có **incremental Java compilation** và **compile avoidance**, nhưng annotation processor có thể làm thay đổi graph inputs/outputs khó hơn so với JavaCompile thông thường:

1. **Processor path là input nhạy cảm**: một thay đổi trong implementation của processor có thể làm generated code thay đổi dù public API của processor JAR không đổi.
2. **Processors có thể incremental hoặc non-incremental**: chỉ processor khai báo đúng và tuân thủ Gradle incremental processing contract mới có thể tận dụng tối ưu tương ứng.
3. **Processor dạng isolating** thường tạo output phụ thuộc vào một annotated element; **aggregating** có thể tạo output phụ thuộc nhiều elements.
4. **Nguồn/trang cấu hình ngoài Java source** mà processor đọc cần được khai báo phù hợp làm task input để Gradle biết phải recompile.
5. **Compiler args/processor options** ảnh hưởng generated code nên là inputs đáng quan tâm.
6. **Processor không deterministic** (timestamp/random/output order không ổn định) làm giảm độ tái lập và build caching.

Không tự khẳng định mọi bản Lombok/MapStruct đều incremental chỉ vì đã đặt dependency đúng scope. Điều này phụ thuộc chính processor version, Gradle version, compiler và cách processor sử dụng APIs.

### Vì sao processor path nên tách khỏi main compile classpath?

Gradle có thể phân tích public ABI của ordinary compile dependency để tránh compile lại khi chỉ thay private method body. Nhưng với **processor JAR**, thay đổi trong method body của processor có thể làm generated sources thay đổi. Vì vậy processor path được Gradle coi như runtime-sensitive input; nếu trộn processor vào compileClasspath, có thể khiến compile avoidance hoạt động kém hoặc processor bị phát hiện/hoạt động không mong muốn ở một số phiên bản cũ.

**Tối ưu đúng:** giữ processor code trên `annotationProcessor`, annotation API trên compile scope và không kéo thêm application runtime dependencies vào processor path.

## 13. Cấu hình processor options bằng `-A...`

Nhiều processors nhận options qua compiler arguments:

```text
-AoptionName=value
```

Với MapStruct:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.addAll(
        listOf(
            "-Amapstruct.unmappedTargetPolicy=ERROR",
            "-Amapstruct.suppressGeneratorTimestamp=true",
            "-Amapstruct.suppressGeneratorVersionInfoComment=true"
        )
    )
}
```

Đây là **snippet bổ sung** vào project MapStruct, không phải build file độc lập. Giải thích:

- `mapstruct.unmappedTargetPolicy=ERROR`: yêu cầu MapStruct báo lỗi đối với các target properties không được mapping trong phạm vi chính sách đó.
- `suppressGeneratorTimestamp=true`: bỏ timestamp trong generated code để tăng tính tái lập.
- `suppressGeneratorVersionInfoComment=true`: bỏ version-info comment khi thích hợp.

**Chỉ truyền các `-A...` mà processor bạn dùng hỗ trợ**, và đặt đúng task (`compileJava`, `compileTestJava` hoặc custom JavaCompile). Một option lạ có thể bị compiler báo unsupported/unrecognized, hoặc bị processor bỏ qua. Không giả định `-A...` là Gradle DSL property có tác dụng cho mọi framework.

Có thể dùng `tasks.withType<JavaCompile>().configureEach { ... }` khi chủ ý áp dụng cho cả main, test và custom source sets. Nhưng trong example này, chỉ main mapper cần MapStruct, nên giới hạn `compileJava` là rõ ràng hơn.

## 14. Chẩn đoán processor đang chạy hay không

Các lệnh hữu ích trong project MapStruct:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testAnnotationProcessor
./gradlew dependencyInsight --configuration annotationProcessor --dependency mapstruct-processor
./gradlew compileJava --info --rerun-tasks
```

Windows PowerShell:

```powershell
.\gradlew.bat dependencies --configuration annotationProcessor
.\gradlew.bat compileJava --info --rerun-tasks
```

- `compileClasspath`: kiểm tra **annotation API** (ở demo là `org.mapstruct:mapstruct`).
- `annotationProcessor`: kiểm tra processor implementation có thể resolve được không.
- `testAnnotationProcessor`: có thể rỗng dù main processor đã chạy đúng.
- `dependencyInsight`: chỉ rõ module processor được kéo vào theo đường nào và version được chọn.
- `--rerun-tasks`: buộc các task liên quan chạy lại dù trước đó UP-TO-DATE, phù hợp khi muốn quan sát compiler.
- `--info`: Gradle log chi tiết hơn; không phải lúc nào cũng in mọi compiler argument hoặc processor name.

### `-XprintRounds` và `-XprintProcessorInfo`

Khi cần xem annotation processing rounds trực tiếp từ `javac`, bổ sung tạm:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.addAll(
        listOf("-XprintRounds", "-XprintProcessorInfo")
    )
}
```

Sau đó:

```bash
./gradlew compileJava --rerun-tasks --console=plain
```

Các flags này dành cho `javac` và output thay đổi theo JDK/compiler/processor. Chúng **không phải cấu hình tối ưu performance** để bật mãi. Với môi trường compiler khác hoặc IDE build không delegate Gradle, flags có thể không được dùng như khi chạy Gradle CLI.

Đặc biệt, **lệnh `dependencies --configuration annotationProcessor` chỉ cho thấy JARs đã resolve**, không chứng minh chắc chắn `process()` thực sự đã chạy. Để xác minh, quan sát generated files/compiled classes hoặc logging về processors và chạy chương trình/test sử dụng generated output.

## 15. Kiểm tra processor path bằng API Gradle

JavaCompile có property `options.annotationProcessorPath`. Khi debugging:

```kotlin
// Đoạn minh họa cấu hình, không phải file độc lập.
tasks.named<JavaCompile>("compileJava") {
    doFirst {
        val path = options.annotationProcessorPath
        println("Processor path files:")
        path?.files?.forEach { file ->
            println(file.name)
        }
    }
}
```

Đoạn này dùng để **quan sát** trong bài thực hành. Tuy nhiên, việc đọc Project/Gradle model trong `doFirst` hoặc dùng task closures có thể không thích hợp với Configuration Cache trong các build lớn. Khi muốn triển khai diagnostics lâu dài, ưu tiên Gradle dependency reports hoặc một task type có inputs được mô hình hóa rõ, và kiểm tra yêu cầu Configuration Cache của version đang dùng.

**Không sửa**:

```kotlin
options.annotationProcessorPath = configurations.compileClasspath.get()
```

chỉ để processor hoạt động. Như vậy đánh mất sự tách biệt giữa compiler API và executable processors, kéo cả những thư viện không cần thiết vào processor path và có thể làm giảm build performance. Để sửa lỗi thiếu processor, phải đưa artifact đúng vào `annotationProcessor`.

### Không thêm source directory sinh ra vào `src/main/java`

Gradle đã biết generated-source output của JavaCompile. Nếu tự:

```kotlin
sourceSets.main {
    java.srcDir("build/generated/sources/annotationProcessor/java/main")
}
```

một cách máy móc, bạn có thể tạo dependency cycle về outputs, compiler quét source sinh ra từ lượt trước hoặc duplicate class. Chỉ thêm generated directories do **task khác** sản xuất khi đã nối task dependency/provider đúng cách, không phải với processor outputs mặc định của chính `compileJava`.

## 16. Tự viết processor: tách module API/processor/consumer

Khi muốn hiểu một annotation processor hoạt động thế nào, tưởng tượng multi-project build:

```text
:annotations
    src/main/java/demo/annotation/GenerateGreeting.java

:processor
    src/main/java/demo/processor/GreetingProcessor.java
    src/main/resources/META-INF/services/javax.annotation.processing.Processor

:app
    src/main/java/demo/app/Example.java
```

**Ba vai trò khác nhau:**

- `:annotations`: chứa Java annotation definition (code consumer import để compile).
- `:processor`: chứa `Processor` thực thi lúc compilation.
- `:app`: source sử dụng annotation, Gradle compiler chạy processor để sinh class.

Một `app/build.gradle.kts` có thể khai báo:

```kotlin
plugins {
    application
}

dependencies {
    compileOnly(project(":annotations"))
    annotationProcessor(project(":processor"))
}
```

Đây là **mảnh kiến trúc**, không phải project runnable vì chưa có full source `GreetingProcessor`, service descriptor và Java main. Mục đích minh họa module-level separation. Processor project thường phải **tự phụ thuộc vào annotation API** để compile, và processor path của app phải có các dependencies mà processor cần khi được `javac` thực thi.

### Ví dụ skeleton của Processor

```java
package demo.processor;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("demo.annotation.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Phải dùng Filer để sinh source/resource thật.
        // Skeleton này CHƯA sinh class nào.
        return false;
    }
}
```

Đây là **skeleton compiler plugin**, không phải processor hoàn chỉnh hay demo có output. Nó chỉ cho thấy type/annotations liên quan JSR 269.

Để `javac` tự phát hiện processor trên processor path, JAR cần service descriptor:

```text
META-INF/services/javax.annotation.processing.Processor
```

nội dung:

```text
demo.processor.GreetingProcessor
```

Khi viết processor thật, dùng `processingEnv.getFiler().createSourceFile(...)`, tạo source đúng package, lưu originating elements để hỗ trợ incremental processing khi áp dụng, xử lý `IOException`, không sinh trùng qua rounds và không đọc file tuỳ tiện mà Gradle không biết.

**Không ép compiler tìm processor qua `implementation(project(":processor"))`**. Processor module chỉ phục vụ build-time; app runtime không nên kéo theo processor classes trừ khi contract của app thật sự cần.

## 17. Java vs Kotlin source: Kotlin DSL không đồng nghĩa Kotlin compilation

Hai điều này hoàn toàn khác:

- **`build.gradle.kts`** là build configuration viết bằng Kotlin DSL.
- **`src/main/java`** là Java source, Gradle dùng `JavaCompile` và `annotationProcessor`.
- **`src/main/kotlin`** là Kotlin source, do Kotlin Gradle Plugin/Kotlin compiler xử lý; Java annotation processing configurations **không tự thay thế** được KAPT hoặc KSP cho những Kotlin declarations cần code generation.

Nếu project dùng Kotlin source và một thư viện yêu cầu annotation processing, hãy kiểm tra chính thức:

- `kapt` (Kotlin Annotation Processing Tool) khi processor được hỗ trợ qua KAPT;
- **KSP** nếu processor có bản KSP riêng tương thích;
- Kotlin compiler plugins, khi thư viện dùng extension kiểu đó thay vì JSR 269.

**Đừng chọn `annotationProcessor` cho `@Mapper` trên Kotlin interface rồi mặc định rằng processor JSR 269 sẽ xử lý Kotlin source giống Java.** Điều đó phụ thuộc Kotlin compilation pipeline, plugin được áp dụng và thư viện có hỗ trợ KAPT/KSP hay không.

Ở mixed Java/Kotlin project, có thể đồng thời tồn tại `JavaCompile`, Kotlin compile tasks, kapt/KSP tasks và các generated directories khác. Phân tích từng task/source set trước khi thêm dependency.

## 18. Java Module System (JPMS) và processors

Java 9+ phân biệt:

- **Compile module path** chứa named modules được source yêu cầu qua `module-info.java`.
- **Annotation processor path** cho processors kiểu classpath (ServiceLoader discovery).
- **Processor module path** (`--processor-module-path`) cho modular processors theo cơ chế `javac`.

Khi source là JPMS module, `module-info.java` có thể cần `requires static` cho một annotation module chỉ phục vụ compile hoặc `requires` bình thường cho API có runtime behavior. Điều này **không có nghĩa** processor implementation phải là runtime module của application.

Ví dụ minh họa:

```java
module demo.app {
    requires org.mapstruct;
}
```

Đây là **mảnh module-info** và tên module phải được kiểm tra trên đúng MapStruct artifact/version. Với Lombok có thể cần module metadata riêng hoặc `requires static lombok;` trong modular source; hãy xem tài liệu compatibility Lombok/JPMS của phiên bản cụ thể.

Đừng tự thêm processor JAR vào `module-info.java` của ứng dụng chỉ vì Gradle compile cần chạy nó. Processor chạy trong **môi trường compiler**, không mặc định là application runtime dependency.

Khi thấy `module not found`, cần phân biệt app module path, annotationProcessorPath, processor module path và Gradle variant selection; đây là các ngữ cảnh khác nhau.

## 19. Incremental annotation processing: isolating và aggregating

Các processor sinh code có thể được chia thành hai mô hình trong Gradle incremental API:

**Isolating:** Một output được xác định bởi một annotated source element chính, ví dụ class `UserMapperImpl` được sinh chủ yếu từ `UserMapper`. Khi thay một element không liên quan, không nhất thiết phải sinh lại toàn bộ outputs nếu processor tuân thủ incremental contract.

**Aggregating:** Một output tổng hợp thông tin từ nhiều annotated elements, ví dụ một registry/index liệt kê tất cả các classes mang `@Command`. Thêm một element có thể yêu cầu cập nhật output tổng hợp.

**Non-incremental:** Processor chưa công bố/tuân thủ contract incremental phù hợp, nên Gradle có thể buộc compile đầy đủ hơn.

Khi bạn **viết processor**, chỉ tự đăng ký tính năng incremental nếu logic output thực sự thỏa các constraints của Gradle. Trả sai metadata incremental có thể khiến Gradle tin một task không cần chạy trong khi generated files đã lỗi thời.

Khi bạn **dùng processor có sẵn**, chọn version tương thích, kiểm tra Gradle `--info` logs nếu compile task báo processor nào gây full recompile, và tránh tùy tiện thay đổi output directory hoặc processor path. Không nên cố tạo incremental behavior bằng việc đánh dấu mọi file generated là source inputs thủ công.

### Inputs ngoài source Java

Một processor đọc `config/mapper.yml`, `schema.json` hay một resource khác từ filesystem có thể thay đổi generated code khi resource đổi. Khi processor không thông báo đường dẫn đó đúng vào Gradle inputs, build cache hoặc up-to-date checks có thể trả lại output cũ.

Giải pháp:

1. Theo tài liệu processor, khai báo resource là input của JavaCompile hoặc task sinh nguồn phù hợp.
2. Với processor do chính bạn phát triển, dùng API/resource handling phù hợp để Gradle biết dependency.
3. Ưu tiên processor có hỗ trợ incremental và documentation rõ.
4. Không tắt caching toàn bộ build khi có thể mô hình hóa inputs/outputs chính xác.

## 20. Source generator và code generator không nhất thiết là annotation processor

Nhiều công cụ đều “sinh mã” nhưng có cơ chế khác nhau:

| Công cụ | Động cơ | Gradle configuration/tasks thường gặp |
| --- | --- | --- |
| MapStruct | JSR 269 processor | `annotationProcessor` trên `compileJava` |
| Lombok (Java) | Compiler-integrated annotation processing/AST transformation | `compileOnly` + `annotationProcessor` |
| Dagger compiler | JSR 269 processor | Annotation API + processor riêng |
| KAPT | Kotlin compiler + Java APT bridge | `kapt` qua Kotlin plugin |
| KSP | Kotlin Symbol Processing | `ksp` qua KSP Gradle plugin |
| OpenAPI/Protobuf generator | Thường là task sinh source từ schema | Plugin/task riêng với `SourceTask`/outputs, không tự là `annotationProcessor` |
| Java records / compiler language feature | Java compiler xử lý source language construct | Không cần annotation processor chỉ vì source dùng records |

**Quy tắc:** tìm cơ chế generator cụ thể trong tài liệu công cụ. Nếu công cụ là task chạy `protoc` hoặc OpenAPI generator từ schema, không thể sửa lỗi chỉ bằng `annotationProcessor("...")`.

## 21. Các lỗi phổ biến và hướng xử lý

| Lỗi/triệu chứng | Phạm vi cần kiểm tra | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- | --- |
| `package org.mapstruct does not exist` | Main `compileClasspath` | Thiếu `mapstruct` API | Thêm `implementation("org.mapstruct:mapstruct:...")` |
| `cannot find symbol: PersonMapperImpl` | `annotationProcessor`, generated output | Processor không được chạy hoặc mapper chưa được xử lý | Thêm `mapstruct-processor` vào `annotationProcessor`, kiểm tra compiler args |
| Runtime factory không tìm `PersonMapperImpl` | Main generated class và runtimeClasspath | Compile không sinh implementation hoặc artifact đóng gói thiếu classes | Kiểm tra `compileJava` và JAR contents |
| `package lombok does not exist` | Main `compileClasspath` | Thiếu Lombok annotation types | Thêm `compileOnly("lombok")` |
| Lombok `@Getter` có nhưng caller báo getter không tồn tại | Main processor path | Chỉ khai báo `compileOnly`, processor bị tắt hoặc JDK incompatibility | Thêm `annotationProcessor`, kiểm tra toolchain/version |
| Test compile thiếu generated class của test mapper | `testAnnotationProcessor` | Processor chỉ được khai báo cho main | Thêm `testAnnotationProcessor` khi test source tự dùng annotations |
| Thêm processor vào `implementation` nhưng JDK 23 không sinh code | `annotationProcessor`/javac options | Dựa vào implicit discovery đã bị tắt | Khai báo processor path rõ |
| `-proc:none` còn trong compiler args | JavaCompile options | Annotation processing bị cố ý vô hiệu hóa | Bỏ flag hoặc thiết kế compilation đúng |
| `Processor not found` | Processor JAR/service descriptor | Artifact sai, descriptor thiếu, classpath sai hoặc processor name sai | Kiểm tra `META-INF/services`, processor path |
| `FilerException: Attempt to recreate a file` | Processor logic/rounds | Processor sinh cùng file nhiều lần hoặc generated source bị scan như handwritten source | Sửa processor và generated directory wiring |
| Không thấy file .java generated dù Lombok hoạt động | Cơ chế của processor | Lombok sửa AST, không nhất thiết tạo file java | Xem bytecode/getters, không đòi file `Getter.java` |
| File `PersonMapperImpl.java` có nhưng runtime vẫn lỗi | Class output/JAR/runtime | Generated source chưa compile/đóng gói, classpath sai | Xem `build/classes`, `jar tf`, runtimeClasspath |
| Processor chạy trong IDE nhưng CI không chạy | Khác Gradle Wrapper/JDK/IDE compiler | IDE dùng cơ chế APT riêng, Gradle config thiếu | Delegate IDE build/test cho Gradle, sửa Gradle declarations |
| Build chậm sau khi thêm processor | Incremental processor support/inputs | Non-incremental processor, processor path quá lớn | Kiểm tra `--info`, giảm path, nâng processor |
| Compiler option `-A...` không có tác dụng | Sai option hoặc apply sai JavaCompile task | Option tên/version không khớp | Xem documentation processor/compile task |
| Generated code lệ thuộc timestamps | Nondeterministic generator | Generated output khác mỗi build dù source giữ nguyên | Dùng options suppress timestamp nếu processor hỗ trợ |
| Annotation processor lỗi khi đổi JDK | Processor/JDK compatibility | Dựa vào compiler internal API hoặc không hỗ trợ JDK mới | Nâng processor, kiểm tra release notes và Java toolchain |
| Source là `.kt` nhưng `annotationProcessor` không chạy | Kotlin compiler pipeline | Kotlin source không do `JavaCompile` xử lý trực tiếp | Dùng kapt/KSP khi processor hỗ trợ |
| Có `module-info.java` và processor/module missing | JPMS module/processor paths | Module path và processor path bị nhầm | Kiểm tra từng đường, không thêm bừa `requires` |
| Generated source không update khi file ngoài đổi | Processor đọc input chưa được Gradle biết | Caching/incrementality inputs thiếu | Khai báo external resource input hoặc sửa processor |
| `annotationProcessor` resolve nhưng không thấy generated source | Processor không khớp annotation hoặc không tạo file | Không phải mọi processor đều generate .java | Kiểm tra rounds, diagnostics và documented outputs |

**Phân loại theo thời điểm lỗi:**

- **Configuration/dependency resolution**: repository thiếu, artifact version không tồn tại, module conflict.
- **Compile time**: annotation type không tìm thấy, processor không chạy, invalid generated source.
- **Runtime**: generated class không có trong distribution, classloader/provider API bị thiếu, metadata không đúng.
- **Incremental/cache issue**: task UP-TO-DATE dù một input ngoài source đã đổi, generated files không được theo dõi chính xác.

Không trộn cả bốn trường hợp thành một câu “Gradle không nhận annotation”.

## 22. Phương pháp debug theo thứ tự đáng tin

Khi một mapper/generation không hoạt động, hãy làm tuần tự:

1. **Xác định source set**: main, test, custom integration test hay Kotlin?
2. **Xác định annotation API artifact**: source đang import annotation/kiểu từ module nào?
3. **Xác định processor implementation artifact**: processor class nằm trong JAR nào? Có service descriptor không?
4. **So dependencies đã resolve**: `compileClasspath` so với `annotationProcessor`, hoặc test equivalents.
5. **Kiểm tra compiler version/toolchain**: Java 17, JDK 23+ default processing rule, processor compatibility.
6. **Xem `-proc:none`/custom compiler args**: có vô tình tắt processor hoặc override processor path không?
7. **Buộc compile lại để quan sát**: `./gradlew compileJava --info --rerun-tasks`.
8. **Kiểm tra generated outputs**: file .java, .class và resources tùy loại processor.
9. **Kiểm tra runtime packaging**: JAR/distribution có generated implementation không?
10. **Thử test/runner thực tế**: mã ứng dụng hoặc test phải gọi kết quả do processor tạo.
11. **Sửa scope và options ở đúng task**: main vs test, Java vs Kotlin.
12. **Kiểm tra incremental/cache** sau khi build clean đã hoạt động đúng, tránh chữa bằng cách xóa `build/` liên tục.

Những commands có thể dùng để xác định thực tế:

```bash
./gradlew :app:dependencies --configuration annotationProcessor
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration testAnnotationProcessor
./gradlew :app:compileJava --info --rerun-tasks
./gradlew :app:test --console=plain
```

Đây là **mảnh lệnh cho multi-project có subproject `:app`**. Với demo một project ở phần 6, bỏ tiền tố `:app:`. Trên Windows dùng `.\gradlew.bat`.

## 23. Security, reproducibility và version management

Annotation processor là **mã thực thi trong build**, không phải dữ liệu inert. Nó có thể đọc source, file hệ thống, biến môi trường hoặc kết nối mạng tùy quyền của tiến trình Gradle/Java compiler.

Thực hành tốt:

- Dùng processor từ repositories đáng tin; hạn chế plugin/artifact từ nguồn không rõ.
- Cố định phiên bản processor; với MapStruct, giữ `mapstruct` và `mapstruct-processor` tương thích.
- Khi dùng version catalog, khai báo riêng **annotation API** và **processor artifact** để tránh lẫn.
- Sử dụng Gradle dependency locking khi team cần cùng selected versions và dependency verification khi cần kiểm tra artifact bytes.
- Tránh in secrets vào compiler args, processor options hoặc logs.
- Không để processor tùy tiện ghi vào `src/main/java` hoặc sửa tracked source khi compile.
- Giữ generated code trong Gradle-managed build outputs và chỉ commit sản phẩm khi quy trình release có thiết kế rõ.
- Cân nhắc reproducible generation: suppress timestamp/build-path metadata khi processor hỗ trợ.
- Kiểm thử khi nâng compiler/JDK hoặc đổi processor version; processor tích hợp compiler internal APIs có thể dễ bị ảnh hưởng.

### Version Catalog ví dụ

```toml
# gradle/libs.versions.toml
[versions]
mapstruct = "1.6.3"

[libraries]
mapstruct-api = { module = "org.mapstruct:mapstruct", version.ref = "mapstruct" }
mapstruct-processor = { module = "org.mapstruct:mapstruct-processor", version.ref = "mapstruct" }
```

Dùng trong `build.gradle.kts` đã có Java plugin:

```kotlin
dependencies {
    implementation(libs.mapstruct.api)
    annotationProcessor(libs.mapstruct.processor)
}
```

**Version Catalog quản lý khai báo**; nó không tự làm cho `mapstruct-processor` xuất hiện ở annotationProcessor path. **Scope vẫn phải đúng**. Hai library aliases có thể trỏ cùng version, nhưng ý nghĩa compiler/runtime khác nhau.

## 24. Nên chọn `implementation`, `compileOnly`, `annotationProcessor` thế nào?

| Câu hỏi | Lựa chọn |
| --- | --- |
| Source import annotation hoặc API type nào? | Đưa artifact chứa type đó lên compile classpath |
| API đó được code gọi ở runtime? | `implementation` hoặc `runtimeOnly` tùy source usage |
| Annotation chỉ tồn tại để compile, runtime không gọi library? | `compileOnly` thường phù hợp |
| Compiler phải chạy mã Processor? | `annotationProcessor` |
| Tests tự khai báo mapper/annotation cần code generation? | `testAnnotationProcessor` cùng test compile dependency đúng |
| Tests chỉ dùng generated main class? | Main processor là đủ; test chỉ cần thư viện test |
| Dự án là Java library, public ABI lộ kiểu của annotation library? | Cân nhắc `api`/`compileOnlyApi`, tùy runtime contract |
| Source thuộc Kotlin, không phải Java? | Kiểm tra kapt/KSP/compiler plugin đúng công cụ |
| Processor không hỗ trợ incremental? | Chấp nhận/đánh giá chi phí, nâng version hoặc thay công cụ |
| Công cụ sinh file từ schema qua task độc lập? | Tạo/áp dụng codegen task, không đặt bừa vào `annotationProcessor` |

Một quy tắc tổng quát: **chọn Gradle scope bằng câu hỏi “ai cần dependency này, vào thời điểm nào?”**. Khi compiler cần type, đó là compile scope. Khi compiler cần **chạy** processor code, đó là annotationProcessor scope. Khi JVM ứng dụng cần type khi chạy, đó là runtime scope. Chỉ test dùng thì chuyển sang test scopes.

## 25. Bài tập tự kiểm tra

**Câu 1.** Trong Gradle Java project, bạn khai báo `implementation("org.mapstruct:mapstruct:1.6.3")` nhưng không có `annotationProcessor`. Annotation `@Mapper` có được nhận diện không, và `PersonMapperImpl` có chắc được sinh không?

**Đáp:** Annotation type có trên compile classpath nên source thường biên dịch được. Nhưng không có MapStruct processor trên processor path thì **không bảo đảm implementation được sinh**; Gradle hiện đại không nên dựa vào implicit discovery.

**Câu 2.** Vì sao Lombok thường có hai declarations dùng chung một tọa độ Maven?

**Đáp:** `compileOnly` cung cấp `@Getter` cho Java compiler, còn `annotationProcessor` cung cấp mã Lombok được compiler thực thi. Hai classpaths khác vai trò.

**Câu 3.** Test `PersonMapperTest` trong demo chỉ gọi mapper sinh từ main sources. Có phải thêm `testAnnotationProcessor` không?

**Đáp:** Không. `PersonMapperImpl` đã được sinh bởi main `compileJava`. Test không khai báo mapper mới.

**Câu 4.** Một file `src/test/java/demo/TestOnlyMapper.java` có `@Mapper`. Scope nào cấp processor cho test compiler?

**Đáp:** `testAnnotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")`. Test compiler còn phải có MapStruct annotation API trên test compile classpath.

**Câu 5.** Processor không sinh file `.java` nhưng getter Lombok vẫn dùng được. Có phải processor lỗi không?

**Đáp:** Không nhất thiết. Lombok sửa compiler AST và kết quả có thể chỉ xuất hiện ở compiled class. Kiểm tra getter/class bytecode thay vì áp một mô hình generated Java file cho mọi processor.

**Câu 6.** Trên JDK 23, chỉ thêm một processor JAR vào compile classpath có còn bảo đảm annotation processing tự chạy không?

**Đáp:** Không. Chính sách mặc định `javac` đã đổi; nên khai báo processor path một cách tường minh qua Gradle `annotationProcessor`.

**Câu 7.** `./gradlew dependencies --configuration annotationProcessor` hiển thị `mapstruct-processor`. Điều đó đã chứng minh `process()` thực sự chạy chưa?

**Đáp:** Chưa. Nó chứng minh artifact được resolve cho configuration, không chứng minh processor matched annotations và tạo outputs. Kiểm tra task compile, generated files, rounds/logs và hành vi runtime.

**Câu 8.** Bạn thêm `options.compilerArgs.add("-proc:none")` rồi Maven artifacts vẫn resolve đủ. MapStruct có sinh implementation không?

**Đáp:** Không. `-proc:none` tắt annotation processing.

**Câu 9.** Processor đọc `schema.json` ngoài Java sources nhưng Gradle không biết đây là task input. Lỗi gì có thể xảy ra?

**Đáp:** Gradle có thể coi task up-to-date dù schema đổi, dẫn đến generated output cũ. Cần khai báo/mô hình hóa external input đúng, hoặc dùng processor/task tuân thủ Gradle incremental APIs.

**Câu 10.** Có nên commit `build/generated/sources/annotationProcessor/java/main` vào Git để “chắc chắn” dùng được mapper?

**Đáp:** Trong project thông thường, không. Đây là generated build output; nên tái sinh khi compile và giữ ngoài source control, trừ quy trình artifact riêng được thiết kế rõ ràng.

**Câu 11.** Source viết bằng Kotlin trong `src/main/kotlin`, nhưng build script là `build.gradle.kts`. Có thể coi đó là JavaCompile annotation processing chỉ vì DSL cũng là Kotlin không?

**Đáp:** Không. Kotlin DSL là **ngôn ngữ cấu hình build**, Kotlin source được Kotlin compiler xử lý; cần kapt/KSP/compiler plugin phù hợp nếu dùng annotations/code generation trên Kotlin source.

**Câu 12.** Vì sao không nên đặt mọi processor artifacts vào `implementation` “cho chắc”?

**Đáp:** Nó làm phình compile/runtime classpaths, có thể không kích hoạt processor đúng cách, ảnh hưởng compile avoidance và đưa code build-time không cần thiết vào artifact/runtime graph.

## 26. Checklist áp dụng trên dự án thật

- [ ] Xác định chính xác annotation API artifact và processor implementation artifact.
- [ ] Xác định main/test/custom source set và compiler xử lý source.
- [ ] Processor chính nằm trong `annotationProcessor`, không phụ thuộc vào implicit compile-classpath scanning.
- [ ] Annotation types được khai báo trên compile classpath bằng `implementation`/`compileOnly`/scope tương ứng.
- [ ] Không kéo processor code vào runtime khi ứng dụng không dùng.
- [ ] `testAnnotationProcessor` chỉ được thêm khi test sources thật sự cần processor.
- [ ] Gradle Wrapper/JDK toolchain/processor versions phù hợp; kiểm tra JDK 23+ change khi nâng compiler.
- [ ] Generated source/class/resource outputs được Gradle theo dõi và không ghi đè source viết tay.
- [ ] Kiểm tra `dependencies` cho `annotationProcessor` và `compileClasspath` riêng, không trộn chúng.
- [ ] Chạy `compileJava`, xem generated classes và test/runtime call thực tế.
- [ ] Không dùng `-proc:none` nếu cần generated code.
- [ ] Xem incremental annotation processing support và external processor inputs nếu build cache/up-to-date có vấn đề.
- [ ] Không nhầm annotation processing Java với kapt/KSP hoặc các generator tasks khác.
- [ ] Xem lại bảo mật/reproducibility, kiểm soát processor versions và artifact integrity.

## Tài liệu chính thức

- [Gradle — Java Library Plugin: Declaring an annotation processor](https://docs.gradle.org/current/userguide/java_library_plugin.html): phân biệt `compileOnly` và `annotationProcessor`; annotation API và processor implementation.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `annotationProcessor`, `testAnnotationProcessor`, JavaCompile và incremental annotation processing.
- [Gradle — JavaCompile CompileOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): `annotationProcessorPath` và `generatedSourceOutputDirectory`.
- [Gradle — Incremental Java compilation / Annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html#sec:incremental_annotation_processing): isolating/aggregating processors và giới hạn.
- [Gradle — Caching Java projects](https://docs.gradle.org/current/userguide/caching_java_projects.html): compile avoidance, processor classpath và caching.
- [MapStruct — Installation (Gradle)](https://mapstruct.org/documentation/installation/): artifact `mapstruct` và `mapstruct-processor`.
- [MapStruct — Reference Guide 1.6](https://mapstruct.org/documentation/1.6/reference/html/): `@Mapper`, generated implementation, compiler options và phối hợp với Java projects.
- [Project Lombok — Gradle Setup](https://projectlombok.org/setup/gradle): `compileOnly` + `annotationProcessor` và test equivalents.
- [OpenJDK — Annotation Processing Change from JDK 23](https://inside.java/2024/06/18/quality-heads-up/): chính sách `javac` yêu cầu explicit annotation-processing configuration.
- [Oracle — JDK 26 javac Manual](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-processorpath`, `--processor-module-path`, `-proc:none/only/full`, `-XprintRounds` và Filer outputs.
- [Oracle — javax.annotation.processing.Processor](https://docs.oracle.com/en/java/javase/23/docs/api/java.compiler/javax/annotation/processing/Processor.html): processing rounds, Processor lifecycle và discovery.
