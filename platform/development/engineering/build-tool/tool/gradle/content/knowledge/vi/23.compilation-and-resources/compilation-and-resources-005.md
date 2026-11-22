# Thiết lập quan hệ task cho mã hoặc tài nguyên sinh tự động trong Gradle

## 1. Vấn đề: nguồn Java hoặc resource chưa tồn tại trước khi build

Trong một dự án Java, mã nguồn thông thường nằm ở `src/main/java` và tài nguyên ở `src/main/resources`. Nhưng không phải mọi file đều do developer viết tay. Một số file chỉ được tạo khi build:

- Java source được sinh từ schema, IDL, template, OpenAPI hoặc metadata.
- Class chứa build version, protocol constant hoặc thông tin biên dịch.
- File `.properties`/JSON/XML được render từ cấu hình *không nhạy cảm*.
- Descriptor đăng ký service, generated lookup table, resource bundle.
- Source test fixtures hoặc tài nguyên test tạo bởi một task riêng.

Vấn đề thứ nhất là **Gradle phải chạy task tạo file trước khi task tiêu thụ file**. Vấn đề thứ hai là **task consumer phải biết đúng đường dẫn source/resource và biết ai đã tạo nó**. Vấn đề thứ ba là **Gradle phải theo dõi input/output để tránh stale files, race conditions và lỗi cache**.

Một cấu hình đúng tạo quan hệ như sau:

~~~text
schema/config (declared input)
          |
          v
generateBuildInfo (producer task)
          |
          | OutputDirectory: build/generated/sources/buildInfo/main
          v
sourceSets.main.java.srcDir(generateBuildInfo)
          |
          v
compileJava (consumer, tự có dependency tới producer)
          |
          v
classes -> jar / run / test
~~~

Với resources:

~~~text
application message (declared input)
          |
          v
generateBanner (producer task)
          |
          | OutputDirectory: build/generated/resources/banner/main
          v
sourceSets.main.resources.srcDir(generateBanner)
          |
          v
processResources (consumer, tự có dependency tới producer)
          |
          v
classes / jar / runtimeClasspath
~~~

**Điểm chính:** không chỉ cần “chạy task A trước B”, mà cần **nối output của A thành input hợp lệ của B**. Tốt nhất là Gradle tự suy ra quan hệ từ `TaskProvider`/output properties, thay vì developer hardcode thứ tự.

Sau bài này, bạn sẽ viết được custom generator task, nối generated Java/resources vào `sourceSets`, phân biệt implicit và explicit `dependsOn`, hiểu `mustRunAfter`/`finalizedBy`, kiểm tra build graph, giải quyết xung đột output và thiết kế task hoạt động đúng với incremental build, Build Cache và Configuration Cache.

## 2. Một số khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Producer task** | Task tạo ra file/thư mục | `generateBuildInfo` |
| **Consumer task** | Task cần file/thư mục đó | `compileJava`, `processResources` |
| **Declared input** | Giá trị/file ảnh hưởng output task | `@Input`, `@InputFile` |
| **Declared output** | File/dir do task sở hữu | `@OutputFile`, `@OutputDirectory` |
| **TaskProvider** | Tham chiếu lazy đến task được đăng ký | `tasks.register<GenerateBuildInfo>(...)` |
| **Provider/Property** | Tham chiếu lazy đến giá trị | `Property<Int>`, `DirectoryProperty` |
| **SourceSet** | Tập Java source/resources, classpaths, outputs | `sourceSets.main` |
| **Implicit task dependency** | Gradle biết dependency nhờ consumer nhận output của producer với provenance | `java.srcDir(generatorTask)` |
| **Explicit task dependency** | Developer khai báo trực tiếp quan hệ bắt buộc | `dependsOn(generatorTask)` |
| **Ordering-only relationship** | Đặt thứ tự khi hai task đã có trong graph | `mustRunAfter` |
| **Built-by metadata** | FileCollection mang thông tin task tạo files | `files(...).builtBy(taskProvider)` |

Hai tính chất cần đồng thời đạt:

1. **Đúng nội dung:** task consumer nhìn thấy files được sinh.
2. **Đúng thứ tự/lifecycle:** Gradle biết phải chạy generator trước consumer và có thể skip/cache phù hợp.

Nếu chỉ có (1), build có thể chạy được khi files cũ còn trên disk nhưng fail sau `clean`. Nếu chỉ có (2), task generator có thể chạy trước, nhưng JavaCompile vẫn không nhìn thấy source vì chưa nối source directory.

## 3. Task dependencies: implicit, explicit và ordering khác nhau

Gradle xây **task graph** từ những tasks được yêu cầu và quan hệ phụ thuộc. Nếu task B thực sự tiêu thụ output của task A, B phải phụ thuộc A.

### 3.1. Quan hệ ngầm từ output provider

Với `SourceDirectorySet` và task output được khai báo:

~~~kotlin
val generator = tasks.register<GenerateBuildInfo>("generateBuildInfo") {
    outputDirectory.set(
        layout.buildDirectory.dir("generated/sources/buildInfo/main")
    )
}

sourceSets {
    named("main") {
        java.srcDir(generator)
    }
}
~~~

Đây là **snippet minh họa**, chưa độc lập vì cần định nghĩa `GenerateBuildInfo`. `srcDir(generator)` nhận `TaskProvider`; Gradle dùng các outputs của generator làm source root và mang theo task dependency.

Khi gọi:

~~~bash
./gradlew compileJava
~~~

Gradle có đủ thông tin để đưa `generateBuildInfo` vào task graph nếu output của task được dùng bởi JavaCompile.

**Đặc biệt:** việc nối source root với TaskProvider có thể giúp IDE/plugin khác nhận được thông tin generator. Đây là mô hình nên ưu tiên khi plugin/sources API chấp nhận TaskProvider.

### 3.2. Quan hệ tường minh qua dependsOn

Một cách khác:

~~~kotlin
tasks.named("compileJava") {
    dependsOn(generator)
}
~~~

Nó bảo đảm generator được yêu cầu trước compileJava, nhưng **không tự thêm file nguồn** vào JavaCompile. Nếu bạn cần biên dịch source sinh ra thì vẫn phải nối source root, ví dụ `sourceSets.main.java.srcDir(...)` hoặc `JavaCompile.source(...)` phù hợp.

Dùng `dependsOn` khi Gradle không thể suy ra quan hệ từ inputs/outputs, hoặc một task có prerequisite không được biểu diễn bằng provider. Đừng thêm vô tội vạ: dependency thừa có thể làm generator chạy ngay cả khi output của nó không cần.

### 3.3. mustRunAfter và shouldRunAfter KHÔNG tự kéo task vào graph

~~~kotlin
tasks.named("compileJava") {
    mustRunAfter(generator)
}
~~~

Nếu chỉ gọi `compileJava` mà generator không được yêu cầu bởi đường dependency nào khác, `mustRunAfter` **không bắt Gradle chạy generator**. Nó chỉ yêu cầu thứ tự **khi cả hai task có mặt trong graph**.

- `dependsOn(A)`: B yêu cầu A trước khi B chạy; đưa A vào task graph.
- `mustRunAfter(A)`: khi A và B đều được scheduled, B phải chạy sau A; **không tự schedule A**.
- `shouldRunAfter(A)`: gợi ý thứ tự mềm khi cả hai có mặt; Gradle có thể bỏ qua trong một số trường hợp.
- `finalizedBy(A)`: gắn task A làm finalizer, không phải nguồn inputs của task B.
- `onlyIf { ... }`: điều kiện chạy/skip, không thay thế dependency giữa producer/consumer.

Đừng dùng ordering rules để “chữa” lỗi generated file chưa kịp có mặt. Hãy biểu diễn **quan hệ dữ liệu**.

## 4. SourceSet và nhiệm vụ của compileJava / processResources

Java plugin tạo các source sets thông dụng:

- `main`: mã và resources production.
- `test`: mã/resources test.
- Mỗi source set có `java` (source directory set), `resources` và output/classpath tương ứng.

Thông thường:

~~~text
src/main/java              -> compileJava
src/main/resources         -> processResources
src/test/java              -> compileTestJava
src/test/resources         -> processTestResources
~~~

Generated files có thể nằm ở thư mục khác, nhưng cần nối vào **đúng source set**:

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir(generatorOfJava)
        resources.srcDir(generatorOfResources)
    }
}
~~~

Đây là snippet cấu trúc; `generatorOfJava` và `generatorOfResources` phải là tasks/provenance phù hợp.

**Đừng nhầm:**

- `java.srcDir(...)` thêm Java source root; file `.java` bên dưới sẽ được JavaCompile xem xét.
- `resources.srcDir(...)` thêm resource root; ProcessResources copy/transform resource files vào output.
- `sourceSets.main.output` gồm compiled classes **và** processed resources, được các task như `jar`/`run` sử dụng.
- Java source được sinh ra **không phải** resource chỉ vì nó cũng là một file text.
- Resource được sinh ra **không phải** Java class; chỉ cần `processResources`, không cần `compileJava` biên dịch nội dung của nó.

### 4.1. srcDir bổ sung, setSrcDirs thay thế

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir("src/extra/java")
    }
}
~~~

thêm một source root. Ngược lại:

~~~kotlin
sourceSets {
    named("main") {
        java.setSrcDirs(listOf("src/extra/java"))
    }
}
~~~

**thay thế danh sách hiện tại**, có nguy cơ bỏ `src/main/java` và source roots đã được plugin khác đăng ký. Đối với generated sources, thường cần `srcDir(...)` để **append**, không thay toàn bộ sources.

### 4.2. Source root là thư mục CHA của package

Nếu file generated Java là:

~~~text
build/generated/sources/buildInfo/main/generated/example/BuildInfo.java
~~~

thì source root đúng là:

~~~text
build/generated/sources/buildInfo/main
~~~

không phải thư mục con `generated/example`. Java compiler cần map `package generated.example;` với đường dẫn relative `generated/example/BuildInfo.java`.

Tương tự, nếu runtime cần `Main.class.getResourceAsStream("/banner.txt")` và file được tạo ở `build/generated/resources/banner/main/banner.txt`, source root của resources là `build/generated/resources/banner/main`.

## 5. Thiết kế producer task: Inputs/Outputs là hợp đồng

Gradle theo dõi input/output để quyết định một task có cần chạy, có `UP-TO-DATE` hay có thể lấy từ Build Cache hay không.

Một custom generator nên:

1. Có type rõ ràng, thường kế thừa `DefaultTask`.
2. Khai báo các giá trị ảnh hưởng output bằng `@Input` và `Property<T>`.
3. Khai báo file input bằng `@InputFile`/`@InputFiles` và normalization phù hợp.
4. Khai báo đúng đường dẫn output bằng `@OutputFile` hoặc `@OutputDirectory`.
5. Ghi **chỉ** vào output đã đăng ký.
6. Đọc input và ghi output trong `@TaskAction`, không tạo file ngay trong configuration block.
7. Không đọc `project` hoặc Gradle model động trong task action; truyền data cần thiết vào task properties lúc cấu hình.
8. Không dùng clock, random, network, user home hoặc secrets chưa khai báo làm input ẩn.
9. Không để hai tasks khác nhau sở hữu cùng một output directory.

Ví dụ task type:

~~~kotlin
@CacheableTask
abstract class GenerateBuildInfo : DefaultTask() {

    @get:Input
    abstract val code: Property<Int>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val outputFile = outputDirectory
            .file("generated/example/BuildInfo.java")
            .get().asFile

        outputFile.parentFile.mkdirs()

        val javaCode = """
            package generated.example;

            public final class BuildInfo {
                private BuildInfo() {}

                public static int code() {
                    return ${code.get()};
                }
            }
        """.trimIndent() + "\n"

        outputFile.writeText(javaCode, Charsets.UTF_8)
    }
}
~~~

Đây là **phần class** của một `build.gradle.kts`; cần imports đúng như demo hoàn chỉnh phía sau.

Giải thích:

- `@CacheableTask` chỉ nên đặt khi output là hàm deterministic của inputs/implementation; ví dụ này không đọc state ẩn.
- `@get:Input` trên Kotlin getter của `Property<Int>` giúp Gradle biết đổi `code` phải chạy lại generator.
- `@get:OutputDirectory` chỉ rõ Gradle theo dõi toàn bộ directory do task tạo ra.
- `outputDirectory.file(...).get().asFile` dùng đường dẫn từ property, không hardcode `project.buildDir` bên trong task action.
- `@TaskAction` là điểm thực thi; source được viết **khi task chạy**, không phải khi Gradle chỉ cấu hình project.
- Output file chứa Java hợp lệ, có class name phù hợp file path và package name.

**Không dùng generator để tự sửa `src/main/java`.** `src/main/java` dành cho source do developer quản lý; output build nên ở dưới `layout.buildDirectory` để `clean` và cache/incremental logic quản lý đúng.

## 6. Demo chạy được: sinh Java class + resource rồi chạy ứng dụng

Demo dưới đây có **hai producers**:

- `generateBuildInfo` viết file `BuildInfo.java` với một mã số từ `@Input`.
- `generateBanner` viết resource `banner.txt` với nội dung từ `@Input`.

Một Java Main bình thường sử dụng **cả class được sinh và resource được sinh**. Không task nào được gọi bằng tay trước `run`: quan hệ được nối bằng `sourceSets.main.java.srcDir(TaskProvider)` và `resources.srcDir(TaskProvider)`.

### 6.1. Cấu trúc ban đầu

~~~text
generated-input-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/Main.java
~~~

Các thư mục `build/generated/...` chưa tồn tại trước lần build đầu. Đây là điều **cố ý**: một clean build phải tự tạo được chúng.

Yêu cầu: Java 17+ (JDK tương thích), Gradle Wrapper đủ mới tương thích Java 17 và có thể tải/provision toolchain nếu cần. Dùng Wrapper hợp lệ của project, không phải file script giả. Không cần external library dependency.

**File `settings.gradle.kts`:**

~~~kotlin
rootProject.name = "generated-input-demo"
~~~

### 6.2. Toàn bộ file build.gradle.kts

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

@CacheableTask
abstract class GenerateBuildInfo : DefaultTask() {
    @get:Input
    abstract val code: Property<Int>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val output = outputDirectory
            .file("generated/example/BuildInfo.java")
            .get().asFile
        output.parentFile.mkdirs()

        output.writeText(
            """
            package generated.example;

            public final class BuildInfo {
                private BuildInfo() {}

                public static int code() {
                    return ${code.get()};
                }
            }
            """.trimIndent() + "\n",
            Charsets.UTF_8
        )
    }
}

@CacheableTask
abstract class GenerateBanner : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val output = outputDirectory
            .file("banner.txt")
            .get().asFile
        output.parentFile.mkdirs()
        output.writeText(message.get() + "\n", Charsets.UTF_8)
    }
}

val generateBuildInfo = tasks.register<GenerateBuildInfo>("generateBuildInfo") {
    group = "build setup"
    description = "Generate a Java source used by main"
    code.set(42)
    outputDirectory.set(
        layout.buildDirectory.dir("generated/sources/buildInfo/main")
    )
}

val generateBanner = tasks.register<GenerateBanner>("generateBanner") {
    group = "build setup"
    description = "Generate a resource used by main"
    message.set("Hello from generated resources")
    outputDirectory.set(
        layout.buildDirectory.dir("generated/resources/banner/main")
    )
}

sourceSets {
    named("main") {
        java.srcDir(generateBuildInfo)
        resources.srcDir(generateBanner)
    }
}

application {
    mainClass.set("demo.Main")
}
~~~

Từng task sử dụng **output directory riêng**, có input property cụ thể và action deterministic. Không có `dependsOn` thủ công ở `compileJava`/`processResources` vì `srcDir(TaskProvider)` chuyển **cả output lẫn thông tin task dependency** tới source set.

### 6.3. File src/main/java/demo/Main.java

~~~java
package demo;

import generated.example.BuildInfo;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        System.out.println("Code: " + BuildInfo.code());

        try (InputStream input =
                     Main.class.getResourceAsStream("/banner.txt")) {
            if (input == null) {
                throw new IllegalStateException("banner.txt is missing");
            }

            String banner = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8
            ).strip();

            System.out.println("Banner: " + banner);
        }
    }
}
~~~

Java source `Main` phụ thuộc vào class `generated.example.BuildInfo` mà developer **không viết tay**. File `banner.txt` cũng không tồn tại trong `src/main/resources`: nó được producer tạo rồi `processResources` đưa vào main runtime resources.

### 6.4. Chạy từ một workspace sạch

Linux/macOS:

~~~bash
./gradlew clean -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean -q run
~~~

**Đúng hai dòng do Java Main in ra:**

~~~text
Code: 42
Banner: Hello from generated resources
~~~

Lệnh `-q` giảm log Gradle, không bảo đảm mọi warning/JDK startup message đều biến mất. Hai dòng ở trên là output của ứng dụng khi build thành công.

Tự động sẽ có quan hệ công việc về cơ bản:

~~~text
:generateBuildInfo --> :compileJava --+
                                      +--> :classes --> :run
:generateBanner ----> :processResources
~~~

Gradle có thể chạy một số tasks song song khi không xung đột. Điều quan trọng là **mỗi consumer phải đợi producer của chính nó**, không phải thứ tự tuyệt đối giữa hai generators.

### 6.5. Các file được sinh và output sau build

Sau lần chạy thành công, bạn sẽ thấy đường dẫn dự kiến:

~~~text
build/
├── generated/
│   ├── sources/
│   │   └── buildInfo/main/
│   │       └── generated/example/BuildInfo.java
│   └── resources/
│       └── banner/main/banner.txt
├── classes/
│   └── java/main/
│       ├── demo/Main.class
│       └── generated/example/BuildInfo.class
└── resources/
    └── main/banner.txt
~~~

`compileJava` đọc cả file `src/main/java/demo/Main.java` và `build/generated/sources/buildInfo/main/generated/example/BuildInfo.java`. `processResources` copy `banner.txt` sang output resources. `run` sử dụng cả compiled classes và processed resources qua main runtime classpath.

Lưu ý: layout chính xác có thể khác nếu dự án đổi `layout.buildDirectory` hoặc dùng plugin Java khác. Trong demo nguyên bản, output directory được cấu hình như trên.

### 6.6. Tại sao không cần dependsOn?

- `generateBuildInfo` có output được khai báo qua `@OutputDirectory`.
- `sourceSets.main.java.srcDir(generateBuildInfo)` nói với Gradle rằng source root chính là outputs của task.
- Gradle giữ **task provenance** và đưa generator vào task graph khi JavaCompile cần source files.
- `generateBanner` và `resources.srcDir(generateBanner)` làm điều tương tự cho ProcessResources.
- `run` phụ thuộc kết quả `classes`/runtime classpath, nên toàn bộ chuỗi được thực hiện đúng.

Đây là phương pháp đáng tin cậy hơn việc chỉ ghi một chuỗi path dưới `build/generated` rồi hy vọng generator tình cờ đã chạy.

## 7. Kiểm tra task graph bằng --dry-run

Để quan sát task dependencies mà không thực thi actions:

~~~bash
./gradlew compileJava --dry-run
./gradlew processResources --dry-run
./gradlew run --dry-run
~~~

Với demo, bạn kỳ vọng:

- `compileJava` yêu cầu `generateBuildInfo`.
- `processResources` yêu cầu `generateBanner`.
- `run` yêu cầu các outputs của source set main (qua `classes` và các dependencies liên quan).

`--dry-run` sẽ báo tasks được lên lịch theo cách Gradle thể hiện, thường với trạng thái `SKIPPED`. **Không coi nó đã biên dịch hay đã tạo file**: để xác minh output phải chạy task thật. Thứ tự giữa tasks độc lập không phải API contract cố định.

Có thể xem chi tiết công việc thực tế:

~~~bash
./gradlew clean run --info --console=plain
~~~

Không dự đoán một chuỗi log cố định. Tập trung vào producer tasks, compile/process tasks, lý do UP-TO-DATE và các file output.

## 8. Kiểm tra incremental build, UP-TO-DATE và Build Cache

Một producer được thiết kế đúng nên phản ứng phù hợp khi inputs thay đổi.

**Lượt 1:**

~~~bash
./gradlew clean run --no-build-cache
~~~

Gradle cần tạo Java/resource outputs và chạy ứng dụng (nếu không có lỗi cấu hình).

**Lượt 2:**

~~~bash
./gradlew run --no-build-cache --info
~~~

Với input không đổi, `generateBuildInfo` và `generateBanner` có thể `UP-TO-DATE`; `compileJava` và `processResources` cũng có thể skip khi mọi inputs/outputs còn đúng. Task `run` vẫn thực thi Java app theo mô hình JavaExec.

**Thay input:**

~~~kotlin
val generateBuildInfo = tasks.register<GenerateBuildInfo>("generateBuildInfo") {
    code.set(99)
    outputDirectory.set(
        layout.buildDirectory.dir("generated/sources/buildInfo/main")
    )
}
~~~

Đây là **snippet sửa giá trị trong demo**, không phải task registration thứ hai. Sau khi thay `code=42` thành `99`:

- Gradle nhận biết input `code` đã đổi.
- Producer phải cập nhật `BuildInfo.java` từ 42 sang 99.
- JavaCompile nhận file source thay đổi và cập nhật class cần thiết.
- Kết quả ứng dụng đổi thành dòng `Code: 99`, banner vẫn là `Hello from generated resources`.

Nếu thay `message.set("Hello from generated resources")`, `generateBanner`/`processResources` cần phản ánh thay đổi ở resource.

### 8.1. CacheableTask chỉ đúng khi task thật sự deterministic

Trong ví dụ, `@CacheableTask` hợp lý vì output phụ thuộc input `Property` và implementation, không đọc clock, random, network, Git branch, system locale hoặc file không khai báo. Nếu generator thực tế cần schema file, phải khai báo `@InputFile`/`@InputFiles` và normalization hợp lý.

**Không gắn `@CacheableTask` cho task ghi timestamp hiện tại hoặc token ngẫu nhiên** rồi bỏ qua input ẩn. Build Cache có thể trả stale source/resource khiến lỗi rất khó phát hiện.

### 8.2. --rerun-tasks và --no-build-cache không phải một

- `--rerun-tasks` yêu cầu Gradle chạy lại tasks được chọn bất kể up-to-date checks thông thường; không có nghĩa xóa toàn bộ disk caches.
- `--no-build-cache` tránh restore task outputs từ Build Cache trong lượt đó; nó không tắt dependency cache.
- `clean` dọn outputs theo build model, nhưng không xóa Gradle User Home.
- `--no-configuration-cache` khi cần giảm state cấu hình đã được reuse; Configuration Cache và Build Cache là hai hệ khác nhau.

Để tái hiện lỗi “máy tôi chạy được nhưng CI sạch fail”, dùng workspace sạch với Gradle User Home phù hợp và chạy `./gradlew clean run --no-build-cache`. Đừng xóa `~/.gradle` của người khác hoặc các directory không nằm trong phạm vi dự án.

## 9. Mối quan hệ có thể suy ra khi truyền provider

Không phải mọi cách đưa file path cho Gradle đều bảo toàn quan hệ producer–consumer.

### 9.1. Cách nên dùng: truyền TaskProvider trực tiếp

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir(generateBuildInfo)
    }
}
~~~

Gradle dùng outputs của task và xây task dependency.

### 9.2. Cách nên dùng: flatMap ra output property

Khi API consumer cần `Provider<Directory>`:

~~~kotlin
val generatedJavaDir =
    generateBuildInfo.flatMap { it.outputDirectory }

tasks.register<Copy>("stageGeneratedJava") {
    from(generatedJavaDir)
    into(layout.buildDirectory.dir("snapshots/generatedJava"))
}
~~~

Đây là **snippet thêm vào demo**. `flatMap` lấy provider-typed `DirectoryProperty` mà không eager-realize task. Provider giữ liên hệ producer; task `stageGeneratedJava` nhận một input file collection từ output của generator và Gradle có thể suy ra dependency.

Chỉ dùng task `Copy` khi thực sự cần staging riêng; trong demo Java compilation, `java.srcDir(generateBuildInfo)` đã đủ.

### 9.3. Cách làm mất dependency: chỉ truyền đường dẫn

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir(
            layout.buildDirectory.dir("generated/sources/buildInfo/main")
        )
    }
}
~~~

Đây là **anti-pattern** khi đứng một mình: nó chỉ nêu source path, **không nhất thiết truyền thông tin task nào tạo nó**. Sau `clean`, compiler có thể không thấy file nếu generator chưa được scheduled.

Nếu bắt buộc dùng một đường dẫn tĩnh, bạn phải thiết lập **đầy đủ** cả input directory và task dependency tường minh, nhưng cách dùng TaskProvider vẫn rõ ràng và an toàn hơn. Không “chữa” bằng cách chạy generator bằng tay trước mỗi build.

### 9.4. map và flatMap không thể thay cho nhau tùy tiện

Khi task expose property provider-typed như `DirectoryProperty`:

~~~kotlin
val output = generateBuildInfo.flatMap { it.outputDirectory }
~~~

`flatMap` giúp lấy một provider lồng bên trong task provider. Với legacy task expose giá trị `File` thường, dùng `map { it.someFile }` sẽ phù hợp hơn. Không bọc arbitrary path vào `provider { ... }` rồi giả định task dependency được giữ: provenance phải đi theo **output property được Gradle quản lý**, không chỉ cùng chuỗi đường dẫn.

## 10. Groovy DSL: cùng nguyên tắc

Trong `build.gradle` (Groovy DSL), giả sử bạn có một task type `GenerateBuildInfo` đúng hợp đồng `@OutputDirectory`, cú pháp nối source root có thể là:

~~~groovy
def generateBuildInfo = tasks.register(
    'generateBuildInfo', GenerateBuildInfo
) {
    code.set(42)
    outputDirectory.set(
        layout.buildDirectory.dir('generated/sources/buildInfo/main')
    )
}

sourceSets {
    main {
        java {
            srcDir(generateBuildInfo)
        }
    }
}
~~~

Đây là **snippet mô tả wiring**, không phải toàn bộ Groovy build script vì bạn cần định nghĩa `GenerateBuildInfo` hoặc cung cấp task type từ plugin riêng. Trong Kotlin DSL, version tương đương là `tasks.register<GenerateBuildInfo>` và `sourceSets { named("main") { java.srcDir(taskProvider) } }`.

Nếu bạn viết generator trong một plugin Groovy/Java/Kotlin riêng, nên tách logic task type khỏi build script và dùng output properties để consumer liên kết theo cách tương tự.

**Không trộn cú pháp** `id 'java'` hoặc Groovy closures vào `build.gradle.kts`; và không tin rằng `sourceSets.main.java.srcDir("path")` mang dependency giống `srcDir(TaskProvider)`.

## 11. Mã sinh tự động và tài nguyên sinh tự động khác nhau ở điểm nào?

### 11.1. Java sources

- Task tạo `.java` dưới một thư mục `build/generated/sources/...`.
- Source root được thêm vào `sourceSets.main.java`.
- `compileJava` cần producer hoàn tất trước khi compile.
- Output `.class` nằm dưới JavaCompile destination, không dưới generated source directory.
- `jar` gói compiled classes và resources theo source set output.

### 11.2. Resources

- Task tạo file như `.properties`, JSON, XML hoặc text dưới `build/generated/resources/...`.
- Resource root được thêm vào `sourceSets.main.resources`.
- `processResources` cần producer trước khi copy/transform.
- Resource được đưa vào output như `build/resources/main` và có thể được truy cập từ classpath khi chạy/đóng JAR.
- Một resource file chứa mã Java dạng text vẫn không tự được compiler biên dịch nếu nằm trong resources.

### 11.3. Một task có nên tạo cả Java và resources?

Có thể, nếu nghiệp vụ thật sự tạo một bộ outputs gắn kết và task khai báo **hai output directories riêng**. Nhưng thường đơn giản hơn khi dùng hai tasks với trách nhiệm rõ, ví dụ demo. Hai đầu ra khác nhau có thể được gắn vào Java và resources source directories qua output providers tương ứng.

Không nên khai báo một `@OutputDirectory` chung, rồi để task khác cùng ghi vào directory đó. **Overlapping outputs** gây race, up-to-date sai, cache khó tái sử dụng và Gradle có thể chặn optimizations.

### 11.4. Quy tắc tránh trùng resource name

Nếu `src/main/resources/banner.txt` cũng tồn tại trong khi task generator tạo `banner.txt`, ProcessResources có thể gặp duplicate path hoặc phải áp dụng duplicates strategy. Đây là **xung đột về input file layout**, không phải bằng chứng Gradle đã chạy task sai thứ tự.

Giải pháp tốt: thiết kế resource namespaces rõ (ví dụ `generated/config/build-banner.txt`) và tránh hai producer cùng xuất cùng relative path. Chỉ dùng `duplicatesStrategy` khi đã quyết định rõ ưu tiên, không ép `INCLUDE` để che lỗi vô tình.

## 12. Hai antipattern phổ biến: ghi file ở configuration phase và sửa source tree

### 12.1. Viết file ngay trong build script

~~~kotlin
// KHONG NEN:
val out = layout.buildDirectory
    .file("generated/sources/buildInfo/main/generated/example/BuildInfo.java")
    .get().asFile

out.parentFile.mkdirs()
out.writeText("...generated Java...")
~~~

Đoạn này chạy trong **configuration phase**. Khi người dùng chỉ chạy `help` hoặc IDE sync, nó đã ghi file. Gradle không có task input/output contract cho thao tác này, dễ hỏng Configuration Cache, incremental behavior và tính lặp lại.

Đúng hơn: để logic ghi file trong `@TaskAction`, tham số/đường dẫn được khai báo là task properties.

### 12.2. Ghi generated file vào src/main/java

~~~text
src/main/java/generated/example/BuildInfo.java
~~~

Nếu task ghi đè vào thư mục developer quản lý, file có thể bị commit nhầm, stale khi input đổi, hoặc xóa/sửa nội dung do developer viết. Một developer mới có thể build được từ generated file đã commit dù generator hỏng; CI sạch có thể lỗi.

Ưu tiên:

~~~text
build/generated/sources/<generator>/main/...
build/generated/resources/<generator>/main/...
~~~

và nối vào sourceSets. Những output paths này nằm trong vùng build; `clean` có thể dọn, generator tạo lại đúng dữ liệu.

### 12.3. Đừng dùng task `doLast` để tùy tiện viết source trong `compileJava`

Thêm `doFirst` vào `compileJava` để sinh Java source ngay trước compilation khiến generator không có task identity/output contract riêng, khó reuse, cache và debug. Nếu logic tạo file phức tạp, tách thành custom producer task, để Gradle xây graph chính xác.

## 13. Tại sao dependsOn mà vẫn báo “cannot find symbol”?

Giả sử developer viết:

~~~kotlin
tasks.named("compileJava") {
    dependsOn(generateBuildInfo)
}
~~~

nhưng **không** thêm `sourceSets.main.java.srcDir(...)`. Khi Gradle chạy `compileJava`:

1. `generateBuildInfo` thực sự tạo `BuildInfo.java`.
2. Nhưng JavaCompile vẫn chỉ quét những source roots đã khai báo.
3. Java compiler không nhìn thấy file mới dưới `build/generated/...`.
4. File `Main.java` có `import generated.example.BuildInfo;` sẽ báo package/class không tồn tại.

Vì vậy, thứ tự đúng chưa đủ: **file phải là input của JavaCompile**.

Chiều ngược lại cũng sai: nếu chỉ thêm `java.srcDir("build/generated/...")` nhưng không đảm bảo task producer, `compileJava` có thể chạy trước generator hoặc chỉ thành công nhờ stale generated file của lượt trước.

Hãy dùng một biểu thức liên kết cả hai:

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir(generateBuildInfo)
    }
}
~~~

Và với resource:

~~~kotlin
sourceSets {
    named("main") {
        resources.srcDir(generateBanner)
    }
}
~~~

Hai snippets này cần tasks/providers đã đăng ký như demo; chúng không thêm nội dung nếu chỉ paste riêng vào một project chưa có generator.

## 14. Khi nào thực sự cần explicit dependsOn?

Mô hình ưu tiên là **implicit dependency từ data flow**. Tuy nhiên, explicit `dependsOn` vẫn cần nếu consumer không thể nhận producer output qua API có provenance, hoặc task cần một prerequisite không phải input file.

Ví dụ:

- Một task đóng gói gọi một command không được Gradle model hóa, nhưng phải bảo đảm một check task chạy trước.
- Một plugin legacy chỉ nhận đường dẫn string và bạn chưa thể đổi API sang Provider/FileCollection.
- Một task thực hiện công việc phụ trợ bắt buộc trước task khác (dù không có file input).
- Một integration task phải chờ service setup theo lifecycle cụ thể (khi đó còn cần service/cleanup semantics, không chỉ `dependsOn`).

Ví dụ explicit dependency trên task báo cáo độc lập:

~~~kotlin
tasks.register("checkPreparedInputs") {
    dependsOn(generateBuildInfo, generateBanner)
    doLast {
        println("Both generators completed")
    }
}
~~~

**Snippet này chỉ chứng minh cách lập task graph**, không tự đọc generated outputs và không thay thế `sourceSets`. Khi gọi `checkPreparedInputs`, hai generators được scheduled trước; in câu cuối chỉ khi task action chạy thành công.

### 14.1. Task ordering không bảo đảm files đã được tạo

Sai:

~~~kotlin
tasks.named("compileJava") {
    mustRunAfter(generateBuildInfo)
}
~~~

Bởi `mustRunAfter` **không schedule** `generateBuildInfo` nếu nó chưa có trong graph. Đây là lý do xem một task graph “có thứ tự đúng” vẫn chưa đủ để xác minh data flow: kiểm tra cả task dependency lẫn input provenance.

### 14.2. Đừng tạo vòng phụ thuộc

Nếu generator sử dụng JavaCompile output (ví dụ cần classes để chạy) **và** JavaCompile lại phụ thuộc vào generator, bạn tạo cycle:

~~~text
generateBuildInfo -> compileJava -> generateBuildInfo
~~~

Gradle sẽ báo circular dependency hoặc không thể lập graph.

Cách thiết kế lại:

- Đưa generator logic vào một plugin hoặc task sử dụng các input độc lập với classes đang cần generate.
- Tách source set **bootstrap/generator** riêng để compile công cụ sinh mã trước, rồi dùng công cụ đó sinh source cho `main`.
- Dùng artifact plugin/codegen tool đã hỗ trợ đúng lifecycle, thay vì viết Java generator trong cùng source set `main` rồi yêu cầu nó chạy trước `compileJava` của chính `main`.

## 15. Khi generator cần schema/template file làm input

Demo dùng `@Input` đơn giản vì source chỉ phụ thuộc số `42`. Trong dự án thực, generator thường đọc file:

~~~text
src/main/schema/model.json
src/main/schema/api.yaml
src/main/templates/BuildInfo.java.tpl
~~~

Nếu generator đọc một file mà không khai báo input, Gradle có thể coi task vẫn `UP-TO-DATE` khi schema đổi. Đúng hơn, task type nên có:

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val schemaFile: RegularFileProperty
~~~

và đăng ký:

~~~kotlin
tasks.register<GenerateFromSchema>("generateFromSchema") {
    schemaFile.set(layout.projectDirectory.file("src/main/schema/model.json"))
    outputDirectory.set(
        layout.buildDirectory.dir("generated/sources/schema/main")
    )
}
~~~

Đây là **snippet mô tả contract**, không phải toàn bộ code runnable vì `GenerateFromSchema` phải thực sự tồn tại và đọc `schemaFile` trong action. Với nhiều file input, dùng `@InputFiles`/`ConfigurableFileCollection` và normalization thích hợp. Với `@InputDirectory`, `@PathSensitive` cũng quan trọng để tránh cache phụ thuộc absolute paths.

Nếu output Java phụ thuộc version của công cụ sinh mã, hãy mô hình hóa tool classpath và parameters, không chỉ schema file. Khi generator gọi executable bên ngoài hoặc plugin, compiler/generator version là một yếu tố ảnh hưởng kết quả.

### 15.1. Vì sao PathSensitivity quan trọng?

- `RELATIVE` theo dõi paths tương đối so với root input, hữu ích với schema tree.
- `NAME_ONLY` chỉ xét tên file khi thuật toán thật sự không phụ thuộc hierarchy.
- `NONE` bỏ ảnh hưởng paths khi kết quả chỉ phụ thuộc contents.
- `ABSOLUTE` nhạy với đường dẫn máy, thường giảm relocatability.

Không chọn normalization chỉ để tăng cache hit mà bỏ qua thông tin đầu vào. Nếu generator tạo class name dựa theo relative path, `RELATIVE` thường phù hợp hơn `NONE`.

### 15.2. Đừng đọc secrets để sinh resource công khai

Một generator có thể tạo file `application.properties`, nhưng nếu nó nhúng API password/token vào resource, thông tin đó sẽ nằm trong `build/resources/main` và có thể bị đóng gói vào JAR/ZIP.

Chỉ sinh **config mẫu hoặc metadata không nhạy cảm** trong build artifacts. Cấp credentials khi deploy/runtime qua secret store hoặc môi trường phù hợp. Không log secrets trong generator hoặc Build Cache.

## 16. Annotation processors: trường hợp không cần task generator riêng

Khi dùng Java annotation processing (ví dụ một thư viện tạo source trong quá trình `javac`), việc sinh mã có thể diễn ra **bên trong `compileJava`**, không phải từ task độc lập.

Ví dụ khai báo annotation processor dependency:

~~~kotlin
dependencies {
    annotationProcessor("group:processor:version")
    compileOnly("group:annotations:version")
}
~~~

Đây là **snippet minh họa tọa độ**, không khẳng định các modules `group:...` có thật. Khi dùng processor thật, Gradle/JavaCompile cấu hình annotation processor path, compiler quản lý generated-source output directory.

Lưu ý:

- `options.generatedSourceOutputDirectory` (trên JavaCompile) kiểm soát nơi javac/processor viết generated Java files theo API phù hợp.
- Không cần thiết đăng ký thêm một task sinh lại **cùng** files nếu processor đã được compiler gọi.
- Không thêm output generated by JavaCompile làm input source root của cùng JavaCompile theo cách tạo chu trình/duplicate compile.
- Nếu processor có side effects không được khai báo, cần xem Gradle incremental annotation processing và processor compatibility.
- KAPT/KSP/Protobuf/OpenAPI/JOOQ plugins có mô hình tasks khác; ưu tiên integration API của plugin thay vì hardcode `compileJava.dependsOn(...)` cho mọi project.

**Ranh giới:** task generator độc lập cần wiring rõ; source sinh **trong compiler invocation** được compiler/plugin quản lý theo cơ chế khác.

## 17. Nhiều source sets, tests và build đa module

### 17.1. Chỉ sinh source cho tests

Nếu file sinh ra chỉ dùng trong test, nên nối vào `test` thay vì `main`:

~~~kotlin
sourceSets {
    named("test") {
        java.srcDir(generateTestSource)
        resources.srcDir(generateTestResource)
    }
}
~~~

`generateTestSource` và `generateTestResource` là **TaskProviders giả định** được khai báo theo cách tương tự demo. Khi đó `compileTestJava`/`processTestResources` mới là consumers liên quan.

Không đưa test fixture source vào `main` chỉ để test compile pass: điều đó làm artifact production có thêm classes/resources không mong muốn.

### 17.2. Nhiều generator, nhiều output roots

Ví dụ một project sinh Java client từ API schema và sinh Java model từ database metadata. Mỗi generator nên có output directory riêng:

~~~text
build/generated/sources/api/main/
build/generated/sources/db/main/
~~~

Sau đó `java.srcDir(apiGenerator)` và `java.srcDir(dbGenerator)`. Không để cả hai tasks ghi file vào cùng một shared directory; nếu chúng sinh cùng fully qualified class, compiler sẽ báo duplicate class hoặc kết quả không xác định.

### 17.3. Multi-project build

Nếu `:schema` là module cung cấp schema, `:app` là module tiêu thụ generated sources, đừng tự hardcode:

~~~text
../schema/build/generated/...
~~~

và mong Gradle tự hiểu producer task. Phương án tốt thường là:

- Generate code ngay trong consumer project từ schema đã được khai báo là **project dependency/artifact** phù hợp.
- Hoặc để project producer công bố generated artifact qua một outgoing configuration/variant, consumer dùng **project dependency** với metadata và built-by task.
- Hoặc dùng Gradle plugin/convention quản lý generator ở từng project.

Nếu chỉ thêm `dependsOn(":schema:generate")` rồi đọc file qua relative path, build có thể phụ thuộc vào filesystem layout và khó tái sử dụng. Trong composite/multi-project phức tạp, mô hình hóa dữ liệu bằng configurations, variants hoặc artifact providers cho đúng boundary.

## 18. Configuration Cache và task configuration avoidance

Task generator nên dùng `tasks.register` thay vì `tasks.create` khi có thể, để giữ task registration **lazy**. Cấu hình bằng `tasks.named`/TaskProvider, tránh eager `tasks.getByName` hoặc `TaskProvider.get()` khi không cần.

Trong demo:

~~~kotlin
val generateBuildInfo = tasks.register<GenerateBuildInfo>("generateBuildInfo") {
    code.set(42)
    outputDirectory.set(
        layout.buildDirectory.dir("generated/sources/buildInfo/main")
    )
}
~~~

Task action chỉ đọc `code` và `outputDirectory` của chính task. Nó **không truy cập `project`** khi chạy, giúp mô hình phù hợp hơn với Configuration Cache.

Đừng làm:

~~~kotlin
// KHONG NEN:
tasks.register("generate") {
    doLast {
        val dir = project.layout.buildDirectory.dir("generated").get().asFile
        dir.mkdirs()
        dir.resolve("value.txt").writeText(project.version.toString())
    }
}
~~~

Đoạn anti-pattern đọc Gradle `project` trong task action và không khai báo chính xác version input/output. Điều này có thể gây Configuration Cache incompatibility và up-to-date sai khi version đổi.

Cách tốt là `@Input val version: Property<String>`, gán giá trị tại configuration, và dùng `@OutputDirectory`/`@OutputFile` trong `@TaskAction`.

### 18.1. Vì sao eager resolution nguy hiểm?

Nếu trong configuration phase bạn gọi `generator.get().outputDirectory.get().asFile` và duyệt/đọc ngay files chưa được tạo, bạn có thể làm IDE sync hoặc `gradlew help` thất bại. Cấu hình source directory bằng task provider **không cần file tồn tại sớm**; Gradle sẽ tạo nó khi task được scheduled.

### 18.2. `@CacheableTask` không tự bảo đảm caching

Gradle chỉ có thể cache khi task không dùng state ẩn, input/output annotations chính xác, filesystem normalization phù hợp và Build Cache được bật/cho phép. Một task có `@CacheableTask` nhưng đọc timestamp/network ngoài hợp đồng vẫn không deterministic, có thể tạo cache output sai.

## 19. Debug lỗi: generated file chưa kịp có mặt

| Lỗi quan sát | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol: BuildInfo` | Generator không chạy hoặc source root chưa được thêm | Xem graph và `java.srcDir(generatorTask)` |
| Build pass sau lần chạy thứ hai nhưng fail sau clean | Consumer đang ăn stale generated file | Bỏ path-only wiring; dùng TaskProvider/output property |
| `processResources` không copy banner | Resource root chưa nối hoặc path relative sai | `resources.srcDir(generatorTask)` đúng root |
| `main.getResourceAsStream` trả null | Resource không được process hoặc đường dẫn lookup sai | Inspect `build/resources/main` và resource name |
| `mustRunAfter` đã đặt nhưng generator vẫn vắng | Ordering không schedule producer | Dùng dependency qua data flow/`dependsOn` |
| `dependsOn` chạy generator nhưng compile không thấy Java | Task dependency có nhưng source root chưa nối | Thêm source directory vào SourceSet |
| Gradle báo implicit dependency validation problem | Consumer đọc producer output nhưng không có dependency metadata | Truyền TaskProvider/Output property hoặc dependsOn đầy đủ |
| Circular dependency | Generator cần classes từ consumer mà consumer cần generator | Tách bootstrap generator/source set khác |
| Duplicate class | Hai source roots hoặc generators cùng tạo một class | Một producer sở hữu mỗi file; bỏ trùng path |
| Duplicate resource | Static và generated resources cùng relative path | Đổi resource namespace hoặc policy duplicate rõ |
| Task chạy lại mọi lần | Input/output thiếu, file thay đổi không ổn định | Khai báo `@Input`/`@OutputDirectory` và deterministic outputs |
| Task `UP-TO-DATE` nhưng output stale | Input quan trọng không được khai báo | Bổ sung schema/toolchain/version inputs |
| Build Cache phục hồi file sai | Outputs chồng lấn hoặc hidden input | Tách output dirs, sửa cache contract |
| Task action gây Configuration Cache error | Dùng project/model trong execution phase | Dùng managed properties, capture inputs lúc configuration |
| `src/main/java` bị sửa sau build | Generator ghi vào source tree | Chuyển output sang `build/generated` |
| Plugin code generator không wired | Plugin integration/configuration thiếu | Xem API plugin, task names public và source set wiring |
| `clean` không xóa file generated | Generated output nằm ngoài build directory | Chuyển vào `layout.buildDirectory`, xem ownership |
| CI fail nhưng local pass | Local có generated files cũ, JDK/schema khác | Clean checkout và so task graph/inputs |

### 19.1. Cách điều tra theo thứ tự

1. Xác định file thiếu là **Java source**, **resource** hay **compiled class**.
2. Xác định producer task duy nhất, các inputs/outputs đã khai báo.
3. Kiểm tra `--dry-run` của consumer có producer hay không.
4. Nếu có producer, kiểm tra nó có tạo đúng file relative path dưới output root không.
5. Xem `sourceSets.main.java`/`resources` đã nhận đúng task output chưa.
6. Nếu compile vẫn báo thiếu, kiểm tra package name, filename/class, generated syntax và Java version.
7. Nếu resource không có, kiểm tra `build/resources/main`, resource root và `getResourceAsStream` path.
8. Tắt Build Cache tạm thời và chạy trên clean checkout để loại stale state.
9. Nếu task up-to-date sai, kiểm tra các input properties/schema files/tool versions.
10. Sửa một quan hệ/lớp mỗi lần rồi chạy lại task thực tế.

## 20. Phân biệt các cách tạo file: custom task, Copy, Sync, Exec và generator plugin

| Cách làm | Khi nào phù hợp | Lưu ý |
| --- | --- | --- |
| Custom `DefaultTask` + `@TaskAction` | Sinh nội dung mới từ input data/schema | Khai báo tất cả inputs/outputs |
| `Copy` task | Copy/transform resource templates hoặc file đã có | `from(taskProvider)`/provider giữ task dependency |
| `Sync` task | Đồng bộ output directory với tập input files | Có thể xóa files dư; mỗi task sở hữu output riêng |
| `Exec`/`JavaExec` task | Chạy generator/tool bên ngoài | Khai báo I/O, tool version/classpath và environment cần thiết |
| Annotation processor | Java source sinh trong compilation | Dùng `annotationProcessor`/compiler API, không tạo task trùng |
| Protobuf/OpenAPI/JOOQ/KSP/KAPT plugin | Generator theo ecosystem | Ưu tiên integration do plugin cung cấp |
| Ad-hoc code trong `doLast` | Prototype nhỏ có đầy đủ inputs/outputs | Không nên cho generator phức tạp/production |
| Code chạy trong configuration phase | Hầu như không phù hợp | Dễ phá lazy/task graph/cache correctness |

Với `Copy`, một ví dụ an toàn để staging output khác:

~~~kotlin
tasks.register<Copy>("stageGeneratedJava") {
    from(generateBuildInfo)
    into(layout.buildDirectory.dir("staged/generatedJava"))
}
~~~

Đoạn snippet dùng `Copy.from(TaskProvider)` để mang outputs/provenance của producer. Nhưng đây **không phải** phần thiết yếu khi chỉ muốn JavaCompile đọc Java sources: source set wiring đã đảm nhiệm.

### 20.1. Với template resource, tránh overwrite input

Nếu bạn copy template từ `src/main/templates` và expand variables, output nên ghi dưới `build/generated/resources/template/...`, rồi nối resource source set tới **task `Copy`** thông qua provider. Không copy đè template source hoặc `src/main/resources` nếu có thể tránh.

Khi dùng `Copy.expand`, các giá trị thay thế có thể chứa dữ liệu nhạy cảm, nên **không** expand secrets vào artifact public. Với output của `Copy`, metadata task/dynamic content cần được khai báo/kiểm soát đầy đủ để cache an toàn.

## 21. Bài tập thực hành và đáp án

**Bài 1.** `compileJava` cần một class do task `generateClient` tạo. Chỉ thêm `compileJava.mustRunAfter(generateClient)` có đủ không?  
**Đáp án:** không. Nó chỉ sắp xếp khi cả hai tasks được scheduled, không tự schedule generator. Hãy truyền output task vào source root hoặc dùng dependency đúng.

**Bài 2.** Chỉ ghi `java.srcDir("build/generated/sources/client")` và build pass trên laptop nhưng fail sau `clean`. Vì sao?  
**Đáp án:** Gradle có source path nhưng không nhất thiết biết task producer. Đường dẫn có thể còn file cũ. Dùng `java.srcDir(generateClientTaskProvider)`.

**Bài 3.** `compileJava.dependsOn(generateClient)` đã có nhưng Java báo `cannot find symbol`. Vì sao?  
**Đáp án:** chưa đăng ký generated source root vào JavaCompile/SourceSet hoặc package/file sai. Task order không thay thế input wiring.

**Bài 4.** File `generated/example/BuildInfo.java` cần source root nào?  
**Đáp án:** thư mục **cha của `generated`**, ví dụ `build/generated/sources/buildInfo/main`.

**Bài 5.** Resource `banner.txt` sinh ra cần được `processResources` xử lý. Cấu hình ở đâu?  
**Đáp án:** `sourceSets.main.resources.srcDir(generateBannerTaskProvider)`.

**Bài 6.** Demo ban đầu in những gì sau `./gradlew clean -q run`?  
**Đáp án:** dòng 1 `Code: 42`; dòng 2 `Banner: Hello from generated resources`.

**Bài 7.** Đổi `code.set(42)` sang `code.set(99)` có cần sửa Java Main không?  
**Đáp án:** không. Gradle thấy `@Input` thay đổi, generator tạo Java mới, compile cập nhật; Main sẽ in `Code: 99`.

**Bài 8.** `generateBuildInfo` và `generateBanner` cùng ghi vào `build/generated` làm output dir của cả hai. Có tốt không?  
**Đáp án:** không; output overlap làm tracking/caching/race khó đúng. Mỗi task nên sở hữu directory riêng.

**Bài 9.** Ghi Java source mới trực tiếp trong cấu hình `build.gradle.kts` có vấn đề gì?  
**Đáp án:** code có side effect ở configuration phase, không có task contract và dễ lỗi Configuration Cache/IDE sync.

**Bài 10.** `java.setSrcDirs(listOf("build/generated/..."))` có khác `java.srcDir(...)` không?  
**Đáp án:** có. `setSrcDirs` thay thế danh sách source roots, có thể làm mất `src/main/java`; `srcDir` thêm root.

**Bài 11.** `@OutputDirectory` có nghĩa mọi file trong directory thuộc task nào?  
**Đáp án:** thuộc producer task khai báo directory đó. Tránh task khác ghi chồng.

**Bài 12.** Nếu generator đọc `model.json`, muốn Gradle biết khi file thay đổi thì dùng input annotation gì?  
**Đáp án:** `@InputFile` với `RegularFileProperty` và normalization phù hợp; `@InputFiles` nếu có nhiều files.

**Bài 13.** `@CacheableTask` có đủ nếu generator đọc thời gian hiện tại ngoài input không?  
**Đáp án:** không. Output không deterministic và phụ thuộc hidden state.

**Bài 14.** Annotation processor sinh source trong `compileJava`; có cần đăng ký task `generateSameSource` viết cùng file không?  
**Đáp án:** không; nên để processor/compiler quản lý, tránh duplicate/cycle.

**Bài 15.** Có task `generateServiceDescriptors` viết resource, nhưng Java chạy không đọc được. Kiểm tra gì?  
**Đáp án:** `resources.srcDir`, relative path của file dưới root, `processResources`, resource lookup và output `build/resources/main`.

**Bài 16.** Dùng `generateBuildInfo.flatMap { it.outputDirectory }` khác gì hardcode path string?  
**Đáp án:** provider map từ task output giữ task provenance/lazy evaluation, Gradle có thể suy ra dependency.

**Bài 17.** Task consumer phải chạy sau producer ngay cả khi không nhận file output; dùng quan hệ nào?  
**Đáp án:** `dependsOn` khi thực sự là prerequisite; `mustRunAfter` chỉ order, không tự schedule.

**Bài 18.** Muốn sinh Java test fixtures nhưng không đưa vào production JAR, nên nối source set nào?  
**Đáp án:** source set `test` hoặc custom test fixture source set phù hợp, không phải `main`.

**Bài 19.** Nếu generator cần chính classes do `compileJava` tạo trong khi compileJava cần generated source, điều gì xảy ra?  
**Đáp án:** circular dependency; tách bootstrap source set/generator hoặc dùng plugin tool khác.

**Bài 20.** Lệnh nào xem graph mà không tạo output?  
**Đáp án:** `./gradlew compileJava --dry-run` hoặc `./gradlew run --dry-run`; phải chạy task thật để kiểm chứng file.

## 22. Checklist trước khi đưa generated sources/resources vào dự án

- [ ] Đã xác định đúng **producer** và **consumer** cho từng generated file?
- [ ] Generator có inputs hợp lệ (value/file/tool versions) và outputs khai báo?
- [ ] Generator chỉ ghi dưới `layout.buildDirectory`, không sửa source tree?
- [ ] Mỗi generator sở hữu output dir riêng, không overlap?
- [ ] Output path relative phù hợp với Java package hoặc resource lookup?
- [ ] `sourceSets.main.java.srcDir(TaskProvider)` được dùng cho generated Java?
- [ ] `sourceSets.main.resources.srcDir(TaskProvider)` được dùng cho generated resources?
- [ ] Không dựa vào `mustRunAfter` để schedule producer?
- [ ] Không dùng `dependsOn` chỉ để che việc thiếu source root?
- [ ] Không `setSrcDirs` làm mất source roots mặc định/plugin-provided?
- [ ] Task `compileJava` và `processResources` có producer trong `--dry-run`?
- [ ] Clean build từ checkout mới thực sự tạo lại đầy đủ inputs?
- [ ] Có chạy Java Main/test để chứng minh generated source/resource được tiêu thụ?
- [ ] Những input thay đổi có làm generator/compiler chạy lại đúng?
- [ ] Không đọc Project/model hoặc viết file trong configuration phase?
- [ ] Không có circular dependencies giữa generator và compile?
- [ ] Không có duplicate class/resource ở các source roots?
- [ ] Generated outputs không chứa secrets hoặc dữ liệu nhạy cảm?
- [ ] Annotation processors và plugin-specific generators không bị đăng ký trùng?
- [ ] Nếu nhiều projects, dùng output artifact/project dependency thay hardcode thư mục khác?
- [ ] Đã kiểm tra Build Cache/Configuration Cache nếu pipeline yêu cầu?
- [ ] Source và schema được quản lý, reproducibility và codegen tool version xác định?

## 23. Tài liệu tham khảo chính thức

- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy` và implicit task dependencies.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): task input/output contracts, `map`/`flatMap` và tránh overlap outputs.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `DefaultTask`, `@Input`, `@OutputDirectory`, `@TaskAction` và cacheability.
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): source sets, generated sources, `compileJava` và `processResources`.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): `FileCollection`, `Copy.from`, outputs và file provenance.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `TaskProvider`, `tasks.named`, lazy wiring.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): input/output tracking và `UP-TO-DATE` checks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable work và determinism.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tránh truy cập Project trong task execution.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Java source sets, compile/resource task model.
- [Gradle — SourceDirectorySet API](https://docs.gradle.org/current/javadoc/org/gradle/api/file/SourceDirectorySet.html): `srcDir`, inputs và task output source roots.
- [Kotlin Documentation — Register generated sources](https://kotlinlang.org/docs/gradle-configure-project.html): ví dụ task provider + generated source directory (với Kotlin plugin).

**Tóm tắt:** muốn source hoặc resource được sinh ra đúng lúc, **không chỉ gọi task generator trước compiler**. Hãy biến generator thành task có input/output contract rõ, đặt outputs dưới `build/generated`, rồi **truyền chính TaskProvider/output provider vào `sourceSets`**. Nhờ đó Gradle nắm cả **nội dung đầu vào** lẫn **quan hệ task**, tự đưa generator vào graph trước `compileJava` hoặc `processResources`. `dependsOn` chỉ dùng khi cần prerequisite tường minh; `mustRunAfter` không thay thế dependency và hardcode một đường dẫn file không thay thế task provenance.