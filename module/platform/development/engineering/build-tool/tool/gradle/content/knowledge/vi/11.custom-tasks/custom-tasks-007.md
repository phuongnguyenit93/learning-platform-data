# Tiêm dịch vụ và sử dụng ExecOperations, FileSystemOperations trong custom task Gradle

## 1. Mục tiêu

Một task Gradle tùy chỉnh đôi khi cần chạy chương trình ngoài, gọi Java main class, sao chép tệp, đồng bộ thư mục hoặc dọn tệp tạm. Gradle cung cấp hai **public service** được thiết kế cho công việc đó:

- `ExecOperations` (`org.gradle.process.ExecOperations`): chạy external process bằng `exec { ... }` hoặc Java process bằng `javaexec { ... }`.
- `FileSystemOperations` (`org.gradle.api.file.FileSystemOperations`): thao tác tệp bằng `copy { ... }`, `sync { ... }`, `delete { ... }` và các `CopySpec`.

Với **service injection**, Gradle cung cấp các service cần thiết qua `@Inject`. Task nhận **dữ liệu** qua `Property<T>`, `DirectoryProperty`, `RegularFileProperty`, `ConfigurableFileCollection` và sử dụng service trong `@TaskAction`. Cách tổ chức này giúp task có ranh giới rõ giữa configuration và execution, giảm truy cập `Project` trong task action và thuận lợi hơn cho Configuration Cache.

Bài học thuộc nhóm **Task tùy chỉnh** của **Build Tool Gradle**, sử dụng **Groovy DSL** (`build.gradle`) và ví dụ Java 17. Hãy dùng Gradle Wrapper của project: `./gradlew` trên Linux/macOS hoặc `.\gradlew.bat` trong Windows PowerShell. Java/JDK chạy Gradle và toolchain Java 17 phải tương thích phiên bản Gradle dự án đang dùng.

Sau bài, bạn có thể:

1. Giải thích vì sao service khác task input/output.
2. Tạo task abstract có constructor/getter injection.
3. Gọi `ExecOperations.exec` hoặc `javaexec` với executable, args, classpath, stdout/stderr và exit code phù hợp.
4. Dùng `FileSystemOperations.copy`, `sync` và `delete` an toàn, đặc biệt tránh xóa nhầm file trong destination.
5. Mô hình hóa input/output để Gradle có thể xét `UP-TO-DATE` và hỗ trợ Configuration Cache.
6. Tự chạy ví dụ, đọc output, sửa lỗi và chọn giữa built-in task với custom task.

## 2. Service injection là gì?

Trong Gradle, một task có hai nhóm phụ thuộc khác nhau.

| Nhóm | Ví dụ | Cần khai báo ra sao |
| --- | --- | --- |
| **Dữ liệu đầu vào/đầu ra** | file nguồn, directory đích, String option, Java classpath | Managed properties và annotations `@Input`, `@InputDirectory`, `@OutputDirectory`, `@Classpath`... |
| **Khả năng thực hiện công việc** | `ExecOperations`, `FileSystemOperations`, `ProviderFactory` | Inject bằng `@Inject` ở constructor hoặc getter |

Service **không phải dữ liệu để fingerprint**. Không đặt `@Input` lên getter `ExecOperations` và không tự serialize service vào cache. Dữ liệu cần được Gradle biết để quyết định **khi nào** task phải chạy; service cung cấp API để làm việc **khi task chạy**.

Luồng điển hình:

~~~text
tasks.register('myTask', MyTaskType)
                |
                v
        TaskProvider<MyTaskType>
                |
      task được Gradle realize khi cần
                |
                +--> inject service @Inject
                +--> cấu hình task Property
                |
                v
   Gradle xác định input/output/task graph
                |
                v
              EXECUTION
                |
                v
            @TaskAction
                |
                +--> ExecOperations.exec/javaexec
                +--> FileSystemOperations.copy/sync/delete
                |
                v
        Kết quả, log và trạng thái task
~~~

**`tasks.register(...)` trả về `TaskProvider<T>`**, tức là tham chiếu tới task có thể được tạo/cấu hình khi cần. Đừng gọi `tasks.register(...).get()` tại top level chỉ để nhận Task instance nếu có thể dùng Provider trực tiếp. Với task dependency, `dependsOn(taskProvider)` là đủ; Gradle sẽ xử lý quan hệ mà không cần ép task được realize sớm. Đây là **task configuration avoidance**, độc lập với service injection.

**Một service được inject không tự làm task cacheable.** Cần thêm input/output đầy đủ và hành vi xác định để Gradle xét up-to-date hoặc Build Cache. Nếu task chỉ in stdout, nó có thể chạy mỗi khi được yêu cầu dù đã khai báo input String.

## 3. Vì sao không gọi `project.exec` hoặc `project.copy` trong task action?

Mã cũ có thể viết:

~~~groovy
tasks.register('copyOldWay') {
    doLast {
        // Phản ví dụ: phụ thuộc Project khi task chạy.
        project.copy {
            from 'assets'
            into "$buildDir/copied"
        }
    }
}
~~~

Có nhiều vấn đề:

- Action truy cập `Project` trong **execution phase**, không phù hợp yêu cầu Configuration Cache.
- Input và output của task không được mô tả rõ bằng annotation/property.
- Biến đường dẫn động và nguồn data có thể phụ thuộc trạng thái của build script.
- Người gọi `help` không nên tạo output; nếu thao tác copy bị chuyển ra ngoài `doLast`, nó còn có thể chạy ngay trong configuration.

Giải pháp cho custom task là **khai báo dữ liệu lúc configuration, thực thi bằng service inject ở `@TaskAction`**. Nếu chỉ cần copy hoặc chạy một lệnh đơn giản, `Copy`, `Sync`, `Exec`, `JavaExec`, `Delete` tích hợp có thể ngắn và rõ hơn custom task.

## 4. Hai kiểu `@Inject`: constructor và abstract getter

Service được Gradle cấp **khi Gradle khởi tạo task** qua `tasks.register`/plugin. Không tạo task bằng `new TaskType()`.

### 4.1. Constructor injection

~~~groovy
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations

abstract class ShowJavaVersion extends DefaultTask {
    private final ExecOperations execOps

    @Inject
    ShowJavaVersion(ExecOperations execOps) {
        this.execOps = execOps
    }

    @TaskAction
    void showVersion() {
        execOps.exec { spec ->
            spec.commandLine('java', '-version')
        }
    }
}

tasks.register('showJavaVersion', ShowJavaVersion)
~~~

Đây là một **đoạn build script đủ để minh họa task**, cần executable `java` trên `PATH`. Lệnh `./gradlew showJavaVersion` chạy `java -version` **khi task thực thi**; version phụ thuộc JDK trên máy, output của Java thường nằm ở stderr, vì vậy không có stdout cố định để chép nguyên văn. Nếu `java` không ở `PATH` dù `JAVA_HOME` đã được đặt, ví dụ có thể thất bại; khi cần độ ổn định, hãy dùng Java toolchain và đường dẫn `JavaLauncher.executablePath`.

### 4.2. Abstract getter injection

~~~groovy
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.FileSystemOperations
import org.gradle.api.tasks.TaskAction

abstract class CopySample extends DefaultTask {
    @Inject
    abstract FileSystemOperations getFileSystemOperations()

    @TaskAction
    void copyFiles() {
        fileSystemOperations.copy { spec ->
            spec.from('assets')
            spec.into('build/sample-copy')
        }
    }
}

tasks.register('copySample', CopySample)
~~~

Gradle tạo implementation của abstract getter và trả service. Đoạn này giả sử có thư mục `assets`; nó chỉ minh họa injection, **chưa khai báo @InputDirectory/@OutputDirectory**, nên không phải mẫu cuối cùng cho task production.

Một task có thể inject **cả hai service**:

~~~groovy
// Trích đoạn trong một abstract custom task:
@Inject
abstract ExecOperations getExecOperations()

@Inject
abstract FileSystemOperations getFileSystemOperations()
~~~

Đây là **hai getter** trong một class được Gradle quản lý. Getter được inject là API/khả năng, không phải đầu vào hoặc output của task.

## 5. ExecOperations.exec: chạy lệnh ngoài

Phương thức `ExecOperations.exec(Action<ExecSpec>)` chạy một executable với các đối số. `ExecSpec` có các lựa chọn quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `commandLine('git', '--version')` | Chọn chương trình và đối số |
| `executable = 'git'`, `args('status')` | Khai báo executable và arguments riêng |
| `workingDir = directory` | Thư mục làm việc của process con |
| `environment('KEY', 'value')` | Đặt/ghi đè biến môi trường của process |
| `standardOutput = outputStream` | Đích nhận stdout |
| `errorOutput = errorStream` | Đích nhận stderr |
| `standardInput = inputStream` | Luồng cấp dữ liệu vào process |
| `ignoreExitValue = true` | Không tự fail vì exit code khác 0; phải tự kiểm tra kết quả |

Phương thức trả `ExecResult` để xem exit value và kiểm tra thành công. Theo mặc định, Gradle xử lý non-zero exit code như lỗi. Nếu bỏ qua bằng `ignoreExitValue`, task phải có logic rõ ràng về exit code.

Ví dụ tùy chọn cần Git:

~~~groovy
import java.io.ByteArrayOutputStream
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations

abstract class CheckGitVersion extends DefaultTask {
    @Inject
    abstract ExecOperations getExecOperations()

    @TaskAction
    void check() {
        def out = new ByteArrayOutputStream()

        def result = execOperations.exec { spec ->
            spec.commandLine('git', '--version')
            spec.standardOutput = out
            spec.ignoreExitValue = true
        }

        if (result.exitValue != 0) {
            throw new GradleException(
                'git failed: exit=' + result.exitValue)
        }
        logger.lifecycle('tool=' + out.toString('UTF-8').trim())
    }
}

tasks.register('checkGitVersion', CheckGitVersion)
~~~

Nếu Git có trên `PATH`, log chứa dòng dạng `tool=git version ...`. Phiên bản khác nhau tùy môi trường; không tuyên bố stdout có số cụ thể. Nếu hệ điều hành **không khởi động được executable**, nó có thể ném lỗi trước khi bạn nhận được `ExecResult`.

**Không giả định Gradle tự gọi shell.** `commandLine('echo hello && date')` không diễn giải `&&` như shell script. Truyền executable/arguments thành các phần riêng. Chỉ dùng `sh -c` hoặc `cmd /c` khi có nhu cầu shell thật và đã giải quyết quoting, portability và đầu vào không tin cậy. Đặc biệt không ghép nội dung người dùng thành shell command.

## 6. ExecOperations.javaexec: chạy Java process

`ExecOperations.javaexec(Action<JavaExecSpec>)` được dùng khi process cần chạy main class bằng Java. Các nhóm tham số:

- `classpath`: đường dẫn classes/JAR cần để load main class và dependency.
- `mainClass`: tên class đầy đủ có package.
- `args`: tham số của `public static void main(String[] args)`.
- `jvmArgs`: JVM flags như `-Xmx256m`, `--add-opens`.
- `systemProperty`: Java `-Dkey=value` trong JVM con.
- `environment`: biến môi trường của process con.
- `executable`: đường dẫn chương trình Java dùng để chạy.
- `standardOutput`/`errorOutput`: luồng kết quả và lỗi.

Không nhầm `args('hello')` (tham số ứng dụng) với `jvmArgs('-Xmx256m')` (tùy chọn JVM). Cũng không nhầm `-Pperson=Lan` (Gradle project property) với system property Java; chỉ khi task **chủ động truyền** thì chương trình con nhận nó.

`ExecOperations.javaexec` hữu ích cho một custom task phải **điều phối Java process trong workflow riêng**. Nếu chỉ cần chạy một main class, task `JavaExec` tích hợp thường đơn giản hơn và có sẵn API để cấu hình các option này.

### Java toolchain và JVM của build

Project có thể khai báo Java 17 toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Nhưng một process do custom task gọi bằng `ExecOperations` không tự chọn Java toolchain chỉ vì project đã khai báo Java plugin. Nếu yêu cầu JDK chính xác, hãy **wire JavaLauncher vào property của task** và dùng executable path tương ứng. Gradle Daemon JVM, Java launcher dùng để chạy process và JDK để biên dịch là các lựa chọn liên quan nhưng có thể khác nhau.

## 7. Demo hoàn chỉnh: ExecOperations.javaexec + Java 17

Ví dụ độc lập dùng **Groovy DSL**, Java plugin tích hợp, không cần thư viện ngoài. Project phải có Gradle Wrapper hợp lệ và JDK 17 được Gradle phát hiện hoặc cung cấp qua toolchain resolver phù hợp.

### 7.1. Cấu trúc project

~~~text
exec-service-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    └── main/
        └── java/
            └── demo/
                └── Greeter.java
~~~

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'exec-service-demo'
~~~

### 7.3. `src/main/java/demo/Greeter.java`

~~~java
package demo;

public final class Greeter {
    private Greeter() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "stranger" : args[0];
        System.out.println("child.hello=" + name);
    }
}
~~~

Đây là Java program chạy độc lập, biên dịch được trên Java 17. Có thể tự thử bằng JDK 17:

~~~bash
javac -d out src/main/java/demo/Greeter.java
java -cp out demo.Greeter Minh
~~~

Stdout nguyên văn:

~~~text
child.hello=Minh
~~~

File `Greeter.java` phải khớp public class `Greeter` và nằm trong thư mục package `demo`.

### 7.4. `build.gradle` hoàn chỉnh

~~~groovy
import javax.inject.Inject

import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Classpath
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.Nested
import org.gradle.api.tasks.TaskAction
import org.gradle.jvm.toolchain.JavaLanguageVersion
import org.gradle.jvm.toolchain.JavaLauncher
import org.gradle.process.ExecOperations

plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

abstract class RunGreeter extends DefaultTask {
    @Input
    abstract Property<String> getPerson()

    @Classpath
    abstract ConfigurableFileCollection getProgramClasspath()

    @Nested
    abstract Property<JavaLauncher> getLauncher()

    @Inject
    abstract ExecOperations getExecOperations()

    @TaskAction
    void runChild() {
        String name = person.get()
        String javaExe = launcher.get().executablePath.asFile.absolutePath

        execOperations.javaexec { spec ->
            spec.executable = javaExe
            spec.classpath = programClasspath
            spec.mainClass.set('demo.Greeter')
            spec.args(name)
        }
    }
}

tasks.register('runGreeter', RunGreeter) {
    group = 'verification'
    description = 'Runs demo.Greeter through ExecOperations.'

    person.convention(
        providers.gradleProperty('person').orElse('Gradle')
    )

    programClasspath.from(sourceSets.main.runtimeClasspath)

    launcher.set(javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    })
}
~~~

**Giải thích:**

1. `tasks.register('runGreeter', RunGreeter)` trả `TaskProvider<RunGreeter>`; Gradle có thể trì hoãn việc realize task.
2. `@Inject abstract ExecOperations` nhận service qua getter, không khai báo đây là input task.
3. `@Input Property<String> person` nhận giá trị mặc định hoặc `-Pperson=...` qua Provider, không ép đọc sớm trong configuration.
4. `@Classpath ConfigurableFileCollection` được nối với runtime classpath của `sourceSets.main`; Java plugin cung cấp output biên dịch cần thiết.
5. `@Nested Property<JavaLauncher>` trỏ tới toolchain Java 17 và cho Gradle biết thông tin launcher liên quan task.
6. `@TaskAction` chỉ đọc property **của chính task**, lấy executable từ launcher và dùng service `javaexec`. Nó không cần gọi `project` trong execution.
7. `spec.mainClass.set('demo.Greeter')` chọn main class, `spec.args(name)` đưa `name` vào `args[0]` trong Java.

### 7.5. Lệnh chạy và stdout

Linux/macOS:

~~~bash
./gradlew -q runGreeter
./gradlew -q runGreeter -Pperson=Lan
~~~

Stdout do class `Greeter` in cho lệnh thứ nhất:

~~~text
child.hello=Gradle
~~~

Cho lệnh thứ hai:

~~~text
child.hello=Lan
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q runGreeter
.\gradlew.bat -q runGreeter -Pperson=Lan
~~~

Các dòng trên là **output chương trình Java**, không bao gồm thông báo của Gradle, JDK hoặc plugin nếu môi trường tạo thêm. Task chỉ in console, **không khai báo output file**, nên không phải một task có artifact để lưu vào Build Cache.

Kiểm tra quá trình task được tạo/cấu hình và Configuration Cache:

~~~bash
./gradlew runGreeter --info
./gradlew runGreeter --configuration-cache
./gradlew runGreeter --configuration-cache
~~~

Không cần kỳ vọng mọi invocation có log giống nhau. Cache hit của configuration model khác với trạng thái task `UP-TO-DATE`; một lần chạy thành công chưa chứng minh tất cả plugin/task trong build đều tương thích.

## 8. FileSystemOperations: copy, sync, delete

Cùng mô hình injection, `FileSystemOperations` cung cấp các operation trên file và directory.

| Method | Hành vi chính | Lưu ý |
| --- | --- | --- |
| `copy { from(...); into(...) }` | Chép file nguồn tới đích | Không tự xóa file thừa chỉ vì chúng không có trong nguồn |
| `sync { from(...); into(...) }` | Đồng bộ thư mục đích với tập file nguồn | Có thể **xóa file thừa ở đích**; chỉ dùng destination task sở hữu |
| `delete { delete(...) }` | Xóa file/directory được chỉ rõ | Có thể xóa dữ liệu thật nếu chọn sai path |
| `copySpec { ... }` | Tạo cấu hình copy có thể dùng tiếp | Tạo CopySpec không đồng nghĩa copy đã thực thi |

Các operation này **thực hiện công việc khi được gọi**, nên đối với custom task thông thường hãy gọi chúng trong `@TaskAction` hoặc worker action, không đặt trực tiếp ở top level `build.gradle`. `@Inject` chỉ quyết định cách nhận service, không biến mọi lời gọi thành lazy.

### copy và sync khác nhau khi có file dư

Giả sử nguồn `assets` có `note.txt`; đích `build/mirror` chứa cả `note.txt` và `orphan.txt`.

~~~groovy
// Trích đoạn trong @TaskAction của task đã inject FileSystemOperations:
fileSystemOperations.copy { spec ->
    spec.from(sourceDirectory.get().asFile)
    spec.into(destinationDirectory.get().asFile)
}
~~~

`copy` cập nhật/chuyển file từ source sang destination; nó không đặt mục tiêu loại bỏ `orphan.txt`. Nhưng:

~~~groovy
// Trích đoạn trong @TaskAction của task đã inject FileSystemOperations:
fileSystemOperations.sync { spec ->
    spec.from(sourceDirectory.get().asFile)
    spec.into(destinationDirectory.get().asFile)
}
~~~

`sync` thiết kế để destination phản ánh nguồn nên `orphan.txt` có thể bị xóa. Điều này đúng về mặt API, không phải bug. Vì vậy destination nên là thư mục riêng dưới `layout.buildDirectory`, không phải repository root hay thư mục home.

Với xóa file, ví dụ đoạn bên trong task action có property `temporaryDirectory`:

~~~groovy
fileSystemOperations.delete { spec ->
    spec.delete(temporaryDirectory.get().asFile)
}
~~~

Nếu chỉ cần xóa một thư mục đơn giản, task `Delete` tích hợp thường đủ:

~~~groovy
tasks.register('deleteMirroredAssets', Delete) {
    delete(layout.buildDirectory.dir('mirrored-assets'))
}
~~~

Đây là task xóa **output demo dưới build directory**, chỉ hoạt động khi được chạy. Không chuyển logic xóa file vào phần configuration.

## 9. Demo hoàn chỉnh: FileSystemOperations.sync có input/output

Ví dụ này **độc lập với demo Java ở mục 7**. Nó đồng bộ `assets` sang `build/mirrored-assets` và dùng input/output annotations để Gradle kiểm tra thay đổi.

### 9.1. Cấu trúc

~~~text
files-service-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── assets/
    └── note.txt
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'files-service-demo'
~~~

`assets/note.txt`, có thể lưu một dòng với newline cuối:

~~~text
Xin chào từ assets
~~~

### 9.2. `build.gradle`

~~~groovy
import javax.inject.Inject

import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileSystemOperations
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class MirrorAssets extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getSourceDirectory()

    @OutputDirectory
    abstract DirectoryProperty getDestinationDirectory()

    @Inject
    abstract FileSystemOperations getFileSystemOperations()

    @TaskAction
    void mirror() {
        fileSystemOperations.sync { spec ->
            spec.from(sourceDirectory.get().asFile)
            spec.into(destinationDirectory.get().asFile)
        }
    }
}

tasks.register('mirrorAssets', MirrorAssets) {
    group = 'verification'
    description = 'Sync task-owned asset directory.'

    sourceDirectory.set(layout.projectDirectory.dir('assets'))
    destinationDirectory.set(
        layout.buildDirectory.dir('mirrored-assets')
    )
}
~~~

**Vì sao input/output được khai báo như vậy?**

- `@InputDirectory` cho biết task đọc nguồn tệp nào; `@PathSensitive(PathSensitivity.RELATIVE)` mô tả cách xét đường dẫn của các file input.
- `@OutputDirectory` cho Gradle biết task sở hữu **cả directory đích**, nơi file được thêm/xóa trong quá trình sync.
- `DirectoryProperty` cho phép nối location từ `ProjectLayout` tại configuration, còn task action chỉ mở property khi cần.
- `@Inject FileSystemOperations` cấp khả năng sync, không buộc task action tham chiếu `Project`.
- `tasks.register` giúp task chỉ cần realize khi được yêu cầu hoặc liên quan task graph.
- Trong `@TaskAction`, service thực thi sync. Nếu task bị skip vì `UP-TO-DATE`, action không được chạy.

Thư mục `assets` phải tồn tại vì `@InputDirectory` là đầu vào bắt buộc. Nếu không có, Gradle có thể báo lỗi validation thay vì âm thầm lấy một source giả.

### 9.3. Chạy và kiểm chứng

Linux/macOS:

~~~bash
./gradlew mirrorAssets
cat build/mirrored-assets/note.txt
./gradlew mirrorAssets
~~~

Nội dung file đầu ra:

~~~text
Xin chào từ assets
~~~

Nếu input/output không thay đổi, lần gọi thứ hai thường báo task `UP-TO-DATE`. Điều đó đến từ input/output tracking; nó khác cơ chế Configuration Cache và Build Cache.

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat mirrorAssets
Get-Content build\mirrored-assets\note.txt
~~~

Để thấy `sync` loại file thừa, **chỉ trong thư mục đích demo** tạo `build/mirrored-assets/orphan.txt` rồi chạy lại. Task có thể chạy vì output directory bị thay đổi; `sync` loại `orphan.txt` vì nguồn không có file này. Không thử trên destination có dữ liệu quan trọng.

Chạy với Configuration Cache:

~~~bash
./gradlew mirrorAssets --configuration-cache
./gradlew mirrorAssets --configuration-cache
~~~

Gradle có thể tạo rồi reuse cấu hình khi input cấu hình không đổi và không có problem. Xem thông báo Gradle để xác nhận. `@Inject` giúp một task dùng service đúng cách, nhưng không bảo đảm mọi plugin khác đều tương thích Configuration Cache.

## 10. Quan hệ task, input/output và cache

### TaskProvider và dependency

Nếu task `prepareAssets` chỉ muốn gọi `mirrorAssets` trước:

~~~groovy
tasks.register('prepareAssets') {
    dependsOn(tasks.named('mirrorAssets'))
}
~~~

`tasks.named('mirrorAssets')` trả `TaskProvider`, Gradle có thể thiết lập dependency mà không phải gọi `get()` để ép realize sớm. `prepareAssets` là lifecycle task không có action. Với consumer thật sự đọc output của `mirrorAssets`, nên nối **output Provider** vào input của consumer để Gradle suy ra dependency theo dữ liệu.

### Input/output không phải trang trí

Khi dùng external tool hoặc FileSystemOperations:

- `@Input` cho options như target environment, argument ảnh hưởng kết quả.
- `@InputFile`, `@InputDirectory`, `@InputFiles` cho file đọc.
- `@Classpath` cho runtime/compiler classpath nếu Java process phụ thuộc nó.
- `@OutputFile` hoặc `@OutputDirectory` cho dữ liệu tạo.
- `@Nested` cho model con như JavaLauncher, nếu cần.
- `@PathSensitive` cho cách fingerprint file paths.

Mục tiêu là Gradle biết **đầu vào làm thay đổi output như thế nào**. Service injection không khai báo điều này thay cho bạn.

Nếu tool bên ngoài tạo output, cần cân nhắc version/path của tool là input vì thay tool có thể đổi kết quả dù file nguồn giống nhau. Tác dụng phụ không nằm trong output declared khiến up-to-date/cache trở nên sai. Đừng đánh dấu `@CacheableTask` nếu không chắc task deterministic, output được khai báo đầy đủ và có khả năng tái sử dụng.

### Ba cơ chế khác nhau

| Cơ chế | Nó tối ưu điều gì? |
| --- | --- |
| **Task configuration avoidance** | Không realize/configure task không cần |
| **Configuration Cache** | Lưu/khôi phục trạng thái configuration để bỏ qua việc cấu hình lại |
| **Up-to-date checking / Build Cache** | Xác định task có cần chạy, hoặc dùng lại kết quả đã lưu dựa trên input/output |

Một lần Configuration Cache hit **không** có nghĩa task `runGreeter` bị skip; task in stdout không có output file đã khai báo. Ngược lại, `mirrorAssets` có thể `UP-TO-DATE` mà vẫn trải qua configuration nếu Configuration Cache chưa dùng.

## 11. Thực thi ở thời điểm đúng

Các lời gọi `execOperations.exec`, `execOperations.javaexec`, `fileSystemOperations.copy`, `sync` và `delete` **thực hiện công việc khi được gọi**. Nếu gọi chúng từ top level build script, action cấu hình task, hoặc plugin `apply`, chúng chạy tại **configuration time**, ngay cả khi user chỉ chạy `./gradlew help`.

Đặc biệt, Gradle hiện đại cảnh báo/không hỗ trợ trực tiếp việc chạy external process trong configuration bằng `ProcessBuilder`, `Runtime.exec`, Groovy `execute()` hay `ExecOperations.exec` khi dùng Configuration Cache. Nếu thật sự cần **đọc output process làm configuration input**, cân nhắc `providers.exec { ... }.standardOutput.asText` hoặc `ValueSource` thích hợp; đó là bài toán khác với **chạy một task có tác dụng phụ**.

Không chuyển việc deploy, xóa file, xuất artifact hoặc gọi API ghi dữ liệu vào Provider transformer. Chúng phải gắn với task/operation tường minh, có quyền thực thi, input/output và failure behavior rõ.

## 12. Bảo mật và portability

`ExecOperations` chạy executable bằng quyền của Gradle process:

1. Không ghép input không tin cậy vào shell command; dùng argument list.
2. Không in secret/token/password vào log hoặc đưa chúng vào command-line args dễ bị lộ trong process listing nếu có cách an toàn hơn.
3. Không giả định `git`, `bash` hay `cmd.exe` có sẵn ở mọi runner; chọn executable theo OS hoặc định nghĩa toolchain hợp lệ.
4. Nếu process cần environment, khai báo rõ biến cần thiết; không tự ghi đè toàn bộ môi trường bằng cấu hình thiếu dữ liệu.
5. Xử lý timeout và exit code của tool phù hợp. `ignoreExitValue=true` không giúp khởi động executable bị thiếu.
6. Khi output phải tái lập, pin version tool và quản lý phần phụ thuộc vào environment/time/network.

`FileSystemOperations.sync/delete` có thể xóa dữ liệu:

1. Dùng destination riêng thuộc task, ưu tiên dưới `layout.buildDirectory`.
2. Không sync sang repository root, home directory, thư mục dùng chung hoặc folder do task khác sở hữu.
3. Với source trống, kiểm tra rõ hành vi sync của Gradle version/operation đang dùng; không để việc xóa phụ thuộc vào giả định mơ hồ.
4. Với đường dẫn do người dùng nhập, validate ranh giới thư mục và quyền truy cập trước khi thực hiện thao tác nguy hiểm.
5. Nếu có file cần giữ ở destination, dùng cơ chế preserve của `SyncSpec` khi phù hợp hoặc thiết kế lại cấu trúc output.

## 13. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Could not start process ...` | Không có executable, sai `PATH`, permission hoặc working dir | Kiểm OS/JDK/tool path và quyền chạy |
| Process exit code khác 0 | Tool báo lỗi; Gradle fail theo mặc định | Đọc stderr/command args; chỉ ignore exit khi có xử lý riêng |
| `&&` hoặc pipe không chạy | `exec` không tự qua shell | Gọi executable và args riêng; dùng shell có kiểm soát nếu bắt buộc |
| JVM con dùng Java sai version | Không wire JavaLauncher cho custom javaexec | Dùng toolchain và `launcher.executablePath` |
| `ClassNotFoundException` | Sai `mainClass` hoặc runtime classpath thiếu output | Kiểm package/classpath và compile dependency |
| `-Pperson` không đến chương trình Java | Gradle project property không tự thành Java args | Wire Provider vào `@Input Property` rồi truyền `spec.args` |
| `project.copy` gây Configuration Cache problem | Truy cập Project ở task execution | Inject FileSystemOperations và dùng task properties |
| `project.exec` gây Configuration Cache problem | Truy cập Project ở task execution | Inject ExecOperations; chuyển process vào `@TaskAction` |
| File thừa ở destination không mất | `copy` không đồng bộ xóa file dư | Chỉ dùng `sync` khi destination task sở hữu |
| File quan trọng bị xóa | Dùng `sync` hoặc `delete` với path sai | Giới hạn output, kiểm path/permission trước khi chạy |
| Task chạy dù input không đổi | Chưa khai báo output hoặc output bị thay đổi | Thêm `@OutputFile`/`@OutputDirectory` đúng |
| Build ghi file dù chỉ chạy `help` | Side effect nằm ở configuration | Chuyển sang task action |
| Task không thấy file nguồn | `@InputDirectory` trỏ sai hoặc file chưa được task trước tạo | Kiểm source, dependency và provider wiring |
| Log không có stdout như mong đợi | Tool ghi stderr hoặc stream đã redirect | Kiểm `standardOutput`, `errorOutput`, encoding |
| Output khác trên CI | Version tool, OS, JVM, environment khác | Pin phiên bản, truyền flags/paths rõ, kiểm inputs |

Khi chẩn đoán, xác định **task đã chạy chưa**, rồi lần lượt kiểm tra executable/JDK, classpath, args, workingDir, environment, stdout/stderr, exit code, và input/output. Lỗi của process ngoài không có nghĩa injection đã thất bại.

## 14. Bài tập thực hành

### Bài A: so sánh hai kiểu injection

Thay abstract getter `@Inject ExecOperations` trong `RunGreeter` bằng constructor injection:

~~~groovy
private final ExecOperations execOps

@Inject
RunGreeter(ExecOperations execOps) {
    this.execOps = execOps
}
~~~

Sau đó dùng `execOps.javaexec { ... }` trong task action. Đây là **trích đoạn để thay thế getter**, không dán cùng lúc cả hai nếu chưa đổi call site. Hai cách đều nhận service do Gradle cấp.

### Bài B: phân biệt copy và sync

Trong project file demo, tạo file dư dưới `build/mirrored-assets` rồi chạy `mirrorAssets`. Quan sát `sync` loại file không còn ở source. Sau đó, trong **bản sao demo**, thay `sync` bằng `copy` và dùng một destination thử nghiệm riêng để thấy file thừa không tự bị xóa.

### Bài C: truyền cấu hình từ Gradle vào Java process

Chạy:

~~~bash
./gradlew -q runGreeter -Pperson=Hoa
~~~

Stdout của `Greeter`:

~~~text
child.hello=Hoa
~~~

Giải thích đường đi: Gradle property `-Pperson` → Provider → `@Input Property<String>` của task → `spec.args(name)` → `args[0]` của Java main.

### Bài D: xác định JVM args khác app args

Trong đoạn `execOperations.javaexec`, thêm:

~~~groovy
spec.jvmArgs('-Xmx128m')
spec.systemProperty('demo.mode', 'training')
~~~

Đây là **trích đoạn bổ sung** bên trong closure `javaexec`. `-Xmx128m` giới hạn heap child JVM, còn `-Ddemo.mode=training` được đọc qua `System.getProperty("demo.mode")`. Không gửi `-Xmx128m` bằng `spec.args` rồi kỳ vọng heap JVM đổi.

### Bài E: Configuration Cache, task graph và output

Lần lượt ở đúng root project của từng demo:

~~~bash
./gradlew runGreeter --configuration-cache
./gradlew runGreeter --configuration-cache
~~~

Và ở project file demo:

~~~bash
./gradlew mirrorAssets --configuration-cache
./gradlew mirrorAssets --configuration-cache
~~~

Quan sát log tạo/reuse Configuration Cache, output của Java app, trạng thái `UP-TO-DATE` của file task. Nhớ rằng đây là **hai project độc lập**, không phải bốn lệnh có thể chạy trong một project chưa tạo đầy đủ task.

### Bài F: chọn built-in task hay custom task

Với yêu cầu chỉ “copy asset từ A sang B”, hãy thử `Copy` hoặc `Sync` tích hợp. Với yêu cầu “đọc metadata, chạy Java tool, kiểm exit code, biến đổi output và xử lý file ở nhiều bước”, custom task có service injection và typed inputs có thể phù hợp hơn. Chọn kiến trúc dựa trên hành vi cần kiểm thử, không dựa vào số lượng API có thể sử dụng.

## 15. Checklist khi review custom task

1. Task được Gradle tạo qua `tasks.register`/plugin, trả `TaskProvider` và không bị `get()` ép realize sớm?
2. `@Inject` dùng ở constructor hoặc abstract getter cho service công khai đúng scope?
3. Giá trị task dùng có `@Input`, `@InputDirectory`, `@Classpath`, `@Nested` đúng và output có `@OutputFile`/`@OutputDirectory` không?
4. Có truy cập `Project`/`Gradle`/`Settings` từ `@TaskAction` không? Nếu có, nên wire qua properties.
5. External process, copy, sync, delete có chạy trong execution thay vì configuration?
6. Tool command, JVM version, args, workingDir, environment, stdout/stderr và exit behavior có xác định?
7. Destination của sync/delete có thuộc task và an toàn để thay đổi hoặc xóa?
8. Có khai báo version tool và các input thực sự ảnh hưởng output để build tái lập không?
9. Có cần output Build Cache không; nếu cần đã thiết kế output và determinism chưa?
10. Đã chạy `--configuration-cache` ít nhất hai lần và đọc báo cáo khi có vấn đề chưa?

## 16. Ghi nhớ

- `@Inject` cho phép Gradle cấp service vào task; getter/constructor được inject **khác với task input**.
- `ExecOperations.exec` chạy external command; `ExecOperations.javaexec` chạy Java process, không tự áp Java toolchain trừ khi bạn truyền launcher/executable phù hợp.
- `FileSystemOperations.copy` chép, `sync` đồng bộ có thể xóa file dư, `delete` xóa đúng mục tiêu. Chỉ thao tác trong vùng đích có quyền sửa.
- `@TaskAction` là nơi thực hiện công việc; configuration dùng để wire `Property`/file locations/task dependencies.
- `tasks.register` trả `TaskProvider` và hỗ trợ configuration avoidance; không ép `get()` khi chỉ cần task reference.
- Inject service không tự làm task up-to-date, cacheable hoặc hoàn toàn tương thích Configuration Cache; metadata input/output và hành vi đúng mới quyết định.
- Dùng `Copy`/`Sync`/`Exec`/`JavaExec`/`Delete` tích hợp khi đủ đáp ứng; viết custom task khi có quy trình hoặc validation riêng.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Services and Service Injection](https://docs.gradle.org/current/userguide/service_injection.html): cơ chế `@Inject`, các service công khai và ví dụ Groovy.
- [Gradle API — ExecOperations](https://docs.gradle.org/current/javadoc/org/gradle/process/ExecOperations.html): `exec`, `javaexec` và kết quả process.
- [Gradle API — FileSystemOperations](https://docs.gradle.org/current/javadoc/org/gradle/api/file/FileSystemOperations.html): `copy`, `sync`, `delete`.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): truy cập Project trong execution, process trong configuration và service injection.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `DefaultTask`, task actions, input/output annotations.
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): `TaskProvider`, `tasks.register` và thực thi khi cần.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): `Copy`/`Sync` và đường dẫn tệp.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): JavaLauncher và chọn JDK.
