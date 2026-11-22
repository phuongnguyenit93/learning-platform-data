# Worker API, chế độ cô lập và công việc có thể chạy song song trong Gradle

## 1. Tại sao một custom task cần Worker API?

Một Gradle task có thể có khối lượng lớn gồm nhiều phần độc lập: chuyển đổi hàng trăm file văn bản, tối ưu hoá ảnh, kiểm tra metadata, phân tích từng file mã nguồn, tạo báo cáo cho các module hoặc xử lý từng artifact. Nếu viết vòng lặp xử lý tất cả file ngay trong một `@TaskAction`, chúng thường chạy **tuần tự trong một task action**. Gradle Worker API cho phép tách công việc thành các **work item** để lên lịch thực thi bất đồng bộ và có thể chạy **đồng thời**.

Phân biệt ba tầng:

- **Task**: nút trong task graph, có inputs/outputs, dependencies và kết quả như `UP-TO-DATE`, `FROM-CACHE` hoặc `EXECUTED`.
- **Work item**: một đơn vị công việc nhỏ hơn do task submit; không phải một task độc lập và không tự xuất hiện như một node của task graph.
- **Worker**: môi trường thực thi work item do Gradle quản lý — có thể là thread chia sẻ classloader, thread với classloader cô lập, hoặc worker daemon trong JVM riêng.

**Mục tiêu bài học:** triển khai `WorkAction` và `WorkParameters`; inject `WorkerExecutor`; submit nhiều item vào `WorkQueue`; so sánh `noIsolation()`, `classLoaderIsolation()`, `processIsolation()`; kiểm soát số worker và lỗi đồng thời; tích hợp đúng với task inputs, outputs, up-to-date checking và configuration cache.

> **Phạm vi:** dùng Gradle Groovy DSL (`build.gradle`) để đăng ký task, và Java 17+ để viết các lớp custom task/worker trong `buildSrc`. Gradle phải chạy trên JDK tương thích với phiên bản đã chọn. Các phiên bản Gradle mới có thể cải thiện scheduler; số worker thực chạy và thời gian luôn phụ thuộc tài nguyên máy.

## 2. Tư duy song song: chia việc thành những phần độc lập

Giả sử task `uppercaseFiles` đọc các file:

```text
samples/
  a.txt     -> "hello"
  b.txt     -> "gradle workers"
  c.txt     -> "parallel build"
```

Mỗi file tạo một output riêng:

```text
build/uppercased/
  a.txt     -> "HELLO"
  b.txt     -> "GRADLE WORKERS"
  c.txt     -> "PARALLEL BUILD"
```

Sơ đồ tác vụ:

```text
                  Gradle task: uppercaseFiles
                             |
                         WorkQueue
                     /       |       \
                    /        |        \
             WorkAction A   WorkAction B   WorkAction C
               a.txt         b.txt         c.txt
                  \           |           /
                    Kết quả trong build/uppercased/
```

Các work item có thể chạy đồng thời vì **không ghi đè file của nhau**, không cần đọc trạng thái item khác, không chia sẻ bộ đếm mutable và đầu ra là hàm của đầu vào. Không có cam kết rằng A bắt đầu hay kết thúc trước B. Với một task xử lý file theo thứ tự bắt buộc, không nên ép song song chỉ vì API hỗ trợ.

**Worker API không tự khiến cả build nhanh hơn.** Với file rất nhỏ, chi phí submit, khởi tạo classloader/JVM và quản lý thread có thể lớn hơn thời gian xử lý. Cần đo thực tế và chọn độ hạt work item hợp lý: không quá nhỏ khiến overhead lấn át, cũng không quá lớn khiến chỉ còn một item chiếm CPU.

## 3. Những thành phần chính của Worker API

| Thành phần | Vai trò | Lưu ý |
| --- | --- | --- |
| `WorkerExecutor` | Dịch vụ Gradle được inject vào custom task; tạo queue theo isolation mode. | Không tự `new WorkerExecutor()`. |
| `WorkQueue` | Hàng đợi với một cấu hình cô lập; nhận nhiều `submit(...)`. | Queue không thread-safe: submit từ luồng điều phối task một cách có kiểm soát. |
| `WorkParameters` | Interface khai báo dữ liệu cho **mỗi** work item. | Ưu tiên Gradle managed properties, không đưa `Project`/`Task` vào. |
| `WorkAction<P>` | Lớp code xử lý một item, với phương thức `execute()`. | Gradle cung cấp triển khai `getParameters()`; không tự viết getter. |
| `submit(ActionClass, action)` | Gửi một item và cấu hình tham số của item đó. | Submit có thể trả control trước khi item hoàn tất. |
| `await()` | Chờ work trong queue hoàn tất và nhận lỗi nếu có. | Có thể gọi trên `WorkQueue`, không nên dùng sau từng lần submit. |

Phân biệt **`WorkAction`** với **`@TaskAction`**: `@TaskAction` là phương thức task trong Gradle graph; `WorkAction.execute()` là phần công việc worker thực hiện sau khi được submit. Ví dụ một task có một phương thức `@TaskAction` nhưng gửi hàng chục `WorkAction`.

### 3.1. Luồng thực hiện điển hình

1. Gradle cấu hình task: khai báo `@InputFiles` và `@OutputDirectory`, cung cấp nguồn dữ liệu và đích.
2. Khi task cần thực thi, Gradle gọi phương thức `@TaskAction`.
3. Task dùng `getWorkerExecutor().noIsolation()` (hoặc mode khác) để lấy queue.
4. Task lặp qua input và gọi `queue.submit(UppercaseWorkAction.class, params -> { ... })`.
5. Gradle tạo snapshot/copy cô lập của tham số và lên lịch xử lý; item có thể chạy đồng thời trong giới hạn tài nguyên.
6. `queue.await()` (nếu gọi) chờ toàn bộ item của queue; khi task action kết thúc, Gradle cũng đảm bảo xử lý các work item thuộc build operation đó trước khi coi task hoàn tất.
7. Nếu worker ném lỗi, Gradle làm task thất bại và truyền thông tin lỗi về ngữ cảnh gọi worker.

**Không submit rồi cho rằng file đầu ra đã tồn tại ngay ở dòng kế tiếp.** Nếu cần đọc kết quả của tất cả item trước khi action task tiếp tục, gọi `await()` đúng lúc; nếu không cần xử lý kết quả trong cùng action, có thể để Gradle quản lý việc chờ ở cuối task. Không gọi `await()` ngay sau **mỗi** submit, vì như vậy vô tình biến lô item thành tuần tự.

## 4. Ba chế độ cô lập

WorkerExecutor có ba API:

```java
getWorkerExecutor().noIsolation();
getWorkerExecutor().classLoaderIsolation();
getWorkerExecutor().processIsolation();
```

| Chế độ | Chạy ở đâu? | Mức cô lập | Chi phí | Khi nên dùng |
| --- | --- | --- | --- | --- |
| `noIsolation()` | Thread trong Gradle JVM, chia sẻ classloader liên quan task. | Thấp; có nguy cơ tác động qua static state và thư viện chung. | Thấp nhất. | Code thuần, thread-safe, không xung đột thư viện/JVM global state. |
| `classLoaderIsolation()` | Thread trong cùng JVM, classloader cô lập theo yêu cầu worker. | Cô lập lớp/thư viện; **không** cô lập toàn bộ trạng thái JVM/process. | Trung bình. | Tool/plugin cần classpath riêng hoặc tránh xung đột version thư viện. |
| `processIsolation()` | Worker daemon trong **JVM riêng** với Gradle JVM. | Mạnh hơn về heap, system properties, classloader và môi trường tiến trình. | Cao hơn do khởi tạo/quản lý JVM. | Tool dùng global state, thư viện native, JDK/JVM options riêng, tác vụ cần cách ly mạnh. |

### 4.1. noIsolation: nhanh nhưng cần thread-safe

```java
WorkQueue queue = getWorkerExecutor().noIsolation();
```

Đây là mode có overhead thấp nhất. Work item vẫn bị Gradle kiểm soát và không được tùy tiện sửa mô hình `Project` khi task đang chạy. Tuy nhiên các item có thể chạy trong những thread khác nhau và chia sẻ state ở classloader, ví dụ:

```java
// PHẢN VÍ DỤ: nhiều worker cùng tăng biến static không đồng bộ.
static int completedCount = 0;
completedCount++; // race condition, kết quả có thể thiếu.
```

Đừng dựa vào static singleton, static mutable cache hoặc biến chung chưa được đồng bộ. Tốt nhất mỗi item nhận input riêng và tạo output riêng; nếu phải chia sẻ tài nguyên có giới hạn, thiết kế riêng cơ chế đồng bộ hoặc Gradle shared Build Service, cân nhắc `maxParallelUsages`.

### 4.2. classLoaderIsolation: cô lập thư viện, không phải process

```java
WorkQueue queue = getWorkerExecutor().classLoaderIsolation();
```

Gradle dùng classloader riêng cho code worker và có thể thêm classpath do bạn cấu hình bằng `ClassLoaderWorkerSpec.getClasspath().from(...)`. Phù hợp khi worker sử dụng công cụ phiên bản khác với các thư viện trên buildscript classpath.

Nếu bạn cần thêm dependency runtime riêng, phần sau là **đoạn minh hoạ trong custom task đã khai báo `@Classpath ConfigurableFileCollection getToolClasspath()`**:

```java
WorkQueue queue = getWorkerExecutor().classLoaderIsolation(spec -> {
    spec.getClasspath().from(getToolClasspath());
});
```

**Không** xem classloader isolation là sandbox bảo mật. Các item vẫn dùng chung JVM và một số tài nguyên như system properties/working directory/native state. Những item có cùng yêu cầu classloader cũng không nên dựa vào static mutable state để đồng bộ.

### 4.3. processIsolation: worker daemon riêng

```java
WorkQueue queue = getWorkerExecutor().processIsolation(spec -> {
    spec.forkOptions(options -> options.setMaxHeapSize("256m"));
});
```

Work item chạy trong **worker daemon process**, tách khỏi Gradle JVM. Worker daemon có thể **được tái sử dụng** cho các item phù hợp về classpath, JVM args, heap, system properties và các yêu cầu khác; không suy luận “mỗi submit tạo một JVM mới”. Để chạy một tool cần JVM options riêng, cấu hình `ProcessWorkerSpec.forkOptions(...)`; nếu tool có runtime dependencies riêng, cấu hình classpath theo API của spec.

Process isolation hữu ích cho thư viện có global state khó kiểm soát, nhưng có chi phí khởi tạo JVM, nhiều bộ nhớ hơn và yêu cầu tham số có thể cô lập/serialize. **Nó không sửa được race condition khi hai work item cùng ghi một đường dẫn đầu ra**, và không biến mã xử lý mất an toàn thành hoàn toàn an toàn. Hãy thiết kế work item độc lập trước khi chọn mode.

## 5. Ví dụ hoàn chỉnh: xử lý song song nhiều file bằng Java 17+ và Gradle

Ví dụ này dùng `noIsolation()` trước, sau đó có thể đổi sang hai mode còn lại để thực nghiệm. Để các lớp worker nằm trên classpath ổn định và dễ dùng với classloader/process isolation, đặt chúng trong `buildSrc/src/main/java` thay vì chỉ định nghĩa trong một đoạn script. **Không cần thư viện ngoài**, chỉ dùng Java chuẩn và Gradle API.

### 5.1. Cấu trúc project

```text
worker-api-demo/
├── settings.gradle
├── build.gradle
├── gradlew                     (Wrapper của dự án)
├── gradlew.bat
├── gradle/wrapper/...
├── buildSrc/
│   ├── build.gradle
│   └── src/main/java/org/example/workers/
│       ├── UppercaseParameters.java
│       ├── UppercaseWorkAction.java
│       └── UppercaseFilesTask.java
└── samples/
    ├── a.txt
    ├── b.txt
    └── c.txt
```

`buildSrc` là build phụ mà Gradle tự build trước để đưa các lớp build logic lên classpath của script chính. Bạn có thể chuyển lớp tương tự sang một standalone/convention plugin khi hệ thống lớn hơn.

**File 1 — `settings.gradle`:**

```groovy
rootProject.name = 'worker-api-demo'
```

**File 2 — `buildSrc/build.gradle`:**

```groovy
plugins {
    id 'java'
}

dependencies {
    implementation gradleApi()
}
```

`gradleApi()` cung cấp các interface `DefaultTask`, `WorkerExecutor`, `WorkAction`, managed file properties... cho lớp Java trong `buildSrc`. Không cần khai báo repository tải thư viện ngoài cho ví dụ.

### 5.2. File 3 — WorkParameters định nghĩa hợp đồng dữ liệu

**`buildSrc/src/main/java/org/example/workers/UppercaseParameters.java`:**

```java
package org.example.workers;

import org.gradle.api.file.RegularFileProperty;
import org.gradle.workers.WorkParameters;

public interface UppercaseParameters extends WorkParameters {
    RegularFileProperty getInputFile();
    RegularFileProperty getOutputFile();
}
```

Chỉ khai báo interface và getters, **không viết implementation**. Gradle tự cung cấp đối tượng parameters có managed properties. `RegularFileProperty` thích hợp cho file đầu vào và đầu ra. Nếu một work item còn cần mode, timeout hoặc cờ tùy chọn, có thể thêm `Property<String>`, `Property<Integer>`; với danh sách dùng `ListProperty<T>` hoặc `ConfigurableFileCollection`.

### 5.3. File 4 — WorkAction xử lý đúng một file

**`buildSrc/src/main/java/org/example/workers/UppercaseWorkAction.java`:**

```java
package org.example.workers;

import org.gradle.workers.WorkAction;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public abstract class UppercaseWorkAction
        implements WorkAction<UppercaseParameters> {

    @Override
    public void execute() {
        Path input = getParameters().getInputFile()
                .get().getAsFile().toPath();
        Path output = getParameters().getOutputFile()
                .get().getAsFile().toPath();

        try {
            Files.createDirectories(output.getParent());
            String text = Files.readString(input, StandardCharsets.UTF_8);
            String upper = text.toUpperCase(Locale.ROOT);
            Files.writeString(output, upper, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Cannot process " + input.getFileName(), e);
        }
    }
}
```

Giải thích:

1. `WorkAction<UppercaseParameters>` gắn lớp xử lý với kiểu tham số.
2. Không cài đặt `getParameters()`: Gradle inject giá trị từ lần `submit` tương ứng.
3. `execute()` chỉ đọc một file và ghi một file; không tham chiếu `Project`, `Task`, `Logger` của task hoặc trạng thái shared mutable.
4. `Files.readString` và `writeString` dùng charset UTF-8 tường minh, phù hợp Java 17+.
5. `Locale.ROOT` giúp cách viết hoa không phụ thuộc locale hệ điều hành. Đây là phép biến đổi demo; với mã hoá/chữ cái đặc thù hoặc xử lý dữ liệu thực, chọn quy tắc nghiệp vụ tương ứng.
6. Nếu lỗi I/O, `UncheckedIOException` được ném lên Worker API, khiến Gradle báo task thất bại; không âm thầm bỏ file lỗi.

**Output mỗi item phải khác nhau.** Ở ví dụ này tất cả source ở cùng thư mục và có tên file duy nhất. Với input từ nhiều subdirectory có thể cùng tên `config.txt`, cần ánh xạ theo relative path hoặc gán tên output duy nhất để không ghi đè.

### 5.4. File 5 — Custom task tạo queue và submit các item

**`buildSrc/src/main/java/org/example/workers/UppercaseFilesTask.java`:**

```java
package org.example.workers;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.ConfigurableFileCollection;
import org.gradle.api.file.DirectoryProperty;
import org.gradle.api.file.RegularFile;
import org.gradle.api.provider.Provider;
import org.gradle.api.tasks.InputFiles;
import org.gradle.api.tasks.OutputDirectory;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;
import org.gradle.workers.WorkQueue;
import org.gradle.workers.WorkerExecutor;

import javax.inject.Inject;
import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public abstract class UppercaseFilesTask extends DefaultTask {

    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract ConfigurableFileCollection getSourceFiles();

    @OutputDirectory
    public abstract DirectoryProperty getDestinationDir();

    @Inject
    public abstract WorkerExecutor getWorkerExecutor();

    @TaskAction
    public void uppercaseAll() {
        WorkQueue queue = getWorkerExecutor().noIsolation();

        List<File> sources = new ArrayList<>(getSourceFiles().getFiles());
        sources.sort(Comparator.comparing(File::getName));

        for (File input : sources) {
            Provider<RegularFile> output =
                    getDestinationDir().file(input.getName());

            queue.submit(UppercaseWorkAction.class, params -> {
                params.getInputFile().set(input);
                params.getOutputFile().set(output);
            });
        }

        queue.await();
    }
}
```

Điểm quan trọng trong mã:

- `@InputFiles` + `@PathSensitive(RELATIVE)` khai báo các file input; `@OutputDirectory` khai báo thư mục kết quả. Gradle dùng metadata này cho up-to-date checking và tính đúng đắn của task.
- `@Inject` trên abstract getter đưa `WorkerExecutor` vào task. Bạn không được instantiate nó bằng `new`.
- `noIsolation()` tạo WorkQueue. Muốn thử hai mode còn lại, **chỉ đổi dòng tạo queue** theo mục 8; logic work item vẫn giữ.
- Vòng lặp `submit` đưa **tất cả item** vào queue trước khi chờ; việc `sources.sort(...)` chỉ làm thứ tự submit dễ dự đoán, **không quyết định thứ tự thực thi hay hoàn tất**.
- Mỗi item nhận **hai managed file properties**. File output dựa trên `getDestinationDir().file(input.getName())`; mỗi input ở ví dụ là một tên riêng.
- `queue.await()` chờ mọi item hoàn tất và báo lỗi nếu một item thất bại. Nó ngăn action của task tiếp tục khi còn item đang chạy; có thể hạn chế một số hình thức song song giữa các task cùng project nếu dùng không cần thiết. **Không** gọi await trong vòng lặp.
- `queue` được dùng ở một thread điều phối; không chia sẻ WorkQueue cho nhiều thread cùng submit vì interface này không thread-safe.

### 5.5. File 6 — Đăng ký task bằng Gradle Groovy DSL

**`build.gradle` ở project root:**

```groovy
import org.example.workers.UppercaseFilesTask

tasks.register('uppercaseFiles', UppercaseFilesTask) {
    sourceFiles.from(fileTree('samples') {
        include '*.txt'
    })
    destinationDir.set(layout.buildDirectory.dir('uppercased'))
}
```

- `tasks.register` tạo task theo kiểu `UppercaseFilesTask` và dùng Gradle lazy configuration.
- `fileTree('samples') { include '*.txt' }` chỉ chọn `*.txt` ngay trong `samples/`, phù hợp với ví dụ file name duy nhất.
- `layout.buildDirectory.dir('uppercased')` tạo Provider cho đích trong `build/`, không hardcode đường dẫn tuyệt đối.

### 5.6. File 7 — Dữ liệu input và lệnh chạy

Tạo thư mục `samples` và ba file UTF-8.

Trên Linux/macOS (Bash):

```bash
mkdir -p samples
printf 'hello\n' > samples/a.txt
printf 'gradle workers\n' > samples/b.txt
printf 'parallel build\n' > samples/c.txt

./gradlew uppercaseFiles --max-workers=4 --console=plain
```

Trên Windows PowerShell 7:

```powershell
New-Item -ItemType Directory -Force samples | Out-Null
$utf8 = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText('samples\a.txt', "hello`n", $utf8)
[System.IO.File]::WriteAllText('samples\b.txt', "gradle workers`n", $utf8)
[System.IO.File]::WriteAllText('samples\c.txt', "parallel build`n", $utf8)

.\gradlew.bat uppercaseFiles --max-workers=4 --console=plain
```

Chú ý trong PowerShell, `$n` trong chuỗi dấu nháy kép là ký hiệu xuống dòng. Ở ví dụ trên, dùng UTF-8 không BOM để so sánh byte/nội dung nhất quán với Bash.

Sau khi chạy thành công, mở ba file:

```text
build/uppercased/a.txt  -> HELLO
build/uppercased/b.txt  -> GRADLE WORKERS
build/uppercased/c.txt  -> PARALLEL BUILD
```

Mỗi file chứa **một dấu xuống dòng cuối** vì source dùng newline; đây là **mô tả nội dung file**, không phải stdout của Gradle. Task không gọi `println` hoặc logger trong WorkAction; console có thể in task outcome như `> Task :uppercaseFiles` và `BUILD SUCCESSFUL`, nhưng nội dung/độ dài log phụ thuộc môi trường.

**Để xác nhận bằng shell:**

```bash
cat build/uppercased/a.txt
cat build/uppercased/b.txt
cat build/uppercased/c.txt
```

**PowerShell:**

```powershell
Get-Content build\uppercased\a.txt
Get-Content build\uppercased\b.txt
Get-Content build\uppercased\c.txt
```

Kết quả ba lệnh đọc file (khi gọi tuần tự) là:

```text
HELLO
GRADLE WORKERS
PARALLEL BUILD
```

Không gán thời gian chạy cố định: ba file text nhỏ như vậy có thể được xử lý xong quá nhanh nên việc bật bốn workers không tạo chênh lệch tốc độ đo được.

## 6. Worker API khác gì --parallel và phụ thuộc task?

| Công cụ | Đối tượng chạy song song | Trọng tâm |
| --- | --- | --- |
| `Worker API` | Nhiều **work item bên trong một custom task**. | Chia công việc lớn thành các item độc lập, có thể xử lý đồng thời. |
| `--parallel` / `org.gradle.parallel=true` | Nhiều task đủ điều kiện từ các project độc lập trong multi-project build. | Mở song song ở mức task/project khi task graph cho phép. |
| `--max-workers=N` / `org.gradle.workers.max=N` | Giới hạn số worker có thể sử dụng cho các dạng công việc song song do Gradle quản lý. | Tránh vượt quá CPU/bộ nhớ. |
| `dependsOn(...)` / implicit task dependency | Quy định task nào phải được xử lý trước task khác. | Đảm bảo thứ tự dữ liệu, **không** tự tạo nhiều work item song song. |
| `mustRunAfter(...)` | Thứ tự nếu cả hai task thuộc graph. | Không tự thêm dependency và không làm task song song. |

Một task có thể dùng Worker API ngay cả khi bạn **không bật `--parallel`**. Bởi `--parallel` chủ yếu thay đổi cách Gradle chạy các task đủ điều kiện ở cấp nhiều project; Worker API tự chia công việc bên trong task. Dù vậy cả hai chịu giới hạn tài nguyên và scheduling của Gradle nên không phải mọi item đều chạy cùng lúc.

`--max-workers=1` là thí nghiệm hữu ích để so sánh với `--max-workers=4`:

```bash
./gradlew uppercaseFiles --rerun-tasks --max-workers=1 --console=plain
./gradlew uppercaseFiles --rerun-tasks --max-workers=4 --console=plain
```

`--rerun-tasks` yêu cầu task action chạy lại (không bị `UP-TO-DATE` che khuất); đừng dùng nó như một tùy chọn tối ưu hiệu năng trong CI thông thường. Đo lặp lại trên nhiều file đủ lớn, giữ nguyên máy/JDK/Gradle, và đo cả memory/CPU. Một phép biến đổi I/O nhỏ có thể bị giới hạn bởi đĩa thay vì CPU; song song nhiều hơn đôi khi **chậm hơn** do contention.

Cấu hình mặc định toàn build có thể đưa vào `gradle.properties`:

```properties
org.gradle.workers.max=4
# Bật song song ở mức task/project khi phù hợp:
org.gradle.parallel=true
```

Trong nghiên cứu Worker API, đừng bật `org.gradle.parallel=true` rồi suy ra một task đơn đã chạy nhiều work item. Hai cấp song song khác nhau phải được quan sát riêng.

## 7. Cách quan sát task graph, work item và up-to-date

### 7.1. --dry-run không cho biết những item sẽ hoàn tất thế nào

```bash
./gradlew uppercaseFiles --dry-run --console=plain
```

`--dry-run` cho biết task `uppercaseFiles` nằm trong graph nhưng **không chạy `@TaskAction`**, nên không tạo WorkQueue và không ghi file. Bạn thường chỉ thấy node `:uppercaseFiles SKIPPED`, **không có ba task mới cho a/b/c**. Worker items không phải task graph nodes.

### 7.2. Chạy lại và cơ chế up-to-date

```bash
./gradlew uppercaseFiles --console=plain
./gradlew uppercaseFiles --console=plain
```

Vì task có `@InputFiles` và `@OutputDirectory`, nếu không có thay đổi đầu vào, cấu hình hoặc output và trạng thái trước đó hợp lệ, Gradle **có thể** đánh dấu `:uppercaseFiles UP-TO-DATE`. Khi đó `@TaskAction` không chạy, tức không có item nào được submit. Điều này **không phải** dấu hiệu Worker API bị hỏng; đó là incremental build.

Để thử input đổi:

```bash
printf 'worker api updated\n' > samples/b.txt
./gradlew uppercaseFiles --console=plain
cat build/uppercased/b.txt
```

Nội dung file mới phải là:

```text
WORKER API UPDATED
```

Ví dụ hiện tại xử lý lại **tất cả** source files khi task thực sự chạy, vì chưa triển khai incremental work API theo thay đổi từng file. Muốn xử lý riêng file thay đổi, hãy tìm hiểu `InputChanges` và `@Incremental`, kết hợp submit chỉ những phần công việc cần thiết. Worker API **không tự biến logic của task thành incremental per-file**.

### 7.3. Build cache và Worker API khác nhau

Khai báo inputs/outputs giúp Gradle kiểm tra up-to-date. Để custom task có thể được build cache tái sử dụng, còn cần thỏa điều kiện và chính sách cache cho task (ví dụ dùng `@CacheableTask` phù hợp với phép biến đổi deterministic). Worker API **không tự làm mọi task cacheable**.

Với output cần reproducible, không đưa timestamp, số thứ tự completion hay thread ID vào nội dung output trừ khi thật sự là dữ liệu được mô hình hóa trong inputs. Kết quả phải độc lập thứ tự scheduling.

## 8. Thực nghiệm đổi isolation mode

Vì ví dụ đặt `UppercaseFilesTask`, `UppercaseWorkAction` và `UppercaseParameters` thành các lớp Java trong `buildSrc`, bạn có thể thử đổi dòng tạo queue ở phương thức `uppercaseAll()`.

**A. Mặc định bài thực hành (no isolation):**

```java
WorkQueue queue = getWorkerExecutor().noIsolation();
```

**B. Classloader isolation (thay đúng một dòng):**

```java
WorkQueue queue = getWorkerExecutor().classLoaderIsolation();
```

**C. Process isolation (thay đúng một dòng):**

```java
WorkQueue queue = getWorkerExecutor().processIsolation();
```

Nếu muốn cấu hình heap của worker JVM, **thay dòng C** bằng:

```java
WorkQueue queue = getWorkerExecutor().processIsolation(spec -> {
    spec.forkOptions(options -> options.setMaxHeapSize("256m"));
});
```

Chỉ dùng **một** trong ba đoạn trên mỗi lần chạy, không tạo cả ba queue rồi submit cùng những file để so sánh vì sẽ khiến các item cùng ghi output. Với mã dùng Java chuẩn và không có external runtime dependency, nội dung các file output **phải giống nhau ở cả ba mode**; cách ly chỉ thay cách thực thi, classloader/process và overhead.

Nếu dùng thư viện ngoài để thực hiện work, classloader/process isolation còn cần worker classpath chứa đúng thư viện. Đặt `compileOnly` cho thư viện dùng chỉ khi compile có thể giúp tránh đưa nó vào classpath chung; cung cấp runtime dependency qua `spec.getClasspath().from(toolClasspath)` theo hướng dẫn Gradle. Nếu thiếu JAR hoặc có xung đột version, worker có thể báo `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Không giả định `processIsolation()` cho phép truy cập `Project` hoặc task mutable state từ process bên ngoài. Worker được thiết kế nhận dữ liệu qua `WorkParameters`; môi trường riêng khiến việc đóng gói input và serializability càng quan trọng.

## 9. Thiết kế WorkParameters an toàn cho song song và cô lập

### 9.1. Ưu tiên Gradle managed property types

| Dữ liệu | Kiểu trong WorkParameters |
| --- | --- |
| Chuỗi, boolean, số | `Property<String>`, `Property<Boolean>`, `Property<Integer>` |
| Một file input/output | `RegularFileProperty` |
| Một directory | `DirectoryProperty` |
| Tập file | `ConfigurableFileCollection` |
| List/Set/Map dữ liệu thuần | `ListProperty<T>`, `SetProperty<T>`, `MapProperty<K,V>` |

Giá trị scalar Java như String, boolean hoặc File có thể cô lập trong nhiều tình huống, nhưng managed properties tạo đường nối rõ giữa task configuration và worker parameters, thuận lợi cho lazy resolution. Một `WorkParameters` interface được Gradle triển khai động; Gradle cô lập/snapshot dữ liệu lúc submit. **Thay parameters ở ngoài sau `submit` không phải cơ chế cập nhật work item đã gửi.**

### 9.2. Tránh truyền đối tượng của Gradle model

Không truyền `Project`, `Task`, `NamedDomainObjectContainer`, service chưa được hỗ trợ, object không thể serialize, classloader-specific object hoặc closure capture toàn bộ project vào tham số worker. Worker API làm việc với **giá trị** cần thiết, không phải toàn bộ model Gradle. Trong process isolation, Gradle còn phải chuyển/serialize các tham số sang worker JVM.

**Phản ví dụ:**

```java
// SAI VỀ THIẾT KẾ: WorkAction không nên đọc Project/Task mutable state.
// project.getProperties().get("token"); // Không có context Project an toàn.
```

**Thay thế:** task cấu hình `Property<String>` hoặc `RegularFileProperty`; khi submit, truyền giá trị/Provider vào WorkParameters; worker chỉ đọc `getParameters()`.

Với build cache và configuration cache, hãy gắn các dữ liệu tác động kết quả vào task inputs được khai báo; WorkParameters **không thay thế** metadata đầu vào của task. Bản thân WorkAction cũng không nên log secret, sử dụng mạng tùy tiện hoặc ghi file ngoài output được khai báo.

### 9.3. Tránh race condition và ghi đè output

Mỗi item nên sở hữu một output path duy nhất. Các nguy cơ:

- Hai file ở hai thư mục khác nhau đều tên `config.txt` nếu bạn ánh xạ chỉ theo basename.
- Hai item cùng ghi `build/result.txt`.
- Nhiều item dùng một `static HashMap` mutable hoặc singleton không thread-safe.
- Một item đọc file mà item khác đang ghi nhưng không có quan hệ dataflow/barrier.
- Dựa vào thứ tự `submit` để đánh số kết quả mà không khóa đồng bộ.

Cách sửa thường là tổ chức output theo relative path, hash/tên duy nhất, tách pha xử lý, hoặc `await()` tại điểm cần barrier. Nếu công việc phải ghi một file tổng hợp, thường tốt hơn để mỗi worker ghi file riêng rồi **một bước tổng hợp cuối** chạy sau khi tất cả hoàn tất.

### 9.4. Không cần process isolation cho mọi task

Thêm JVM riêng có thể tốn bộ nhớ và làm startup chậm. Chọn mode dựa trên lỗi cần giải quyết:

- Có code thuần, thread-safe, chạy CPU/I/O độc lập: bắt đầu bằng `noIsolation()`.
- Có runtime library version khác nhau hoặc nguy cơ trùng class: thử `classLoaderIsolation()`.
- Có thư viện sử dụng system properties/JVM global state, JDK khác, hoặc cần môi trường JVM riêng: chọn `processIsolation()`.

Thử với bộ file đại diện và đo nhiều lần. Không đánh đồng classloader/process isolation với quyền chạy code không tin cậy trong sandbox bảo mật.

## 10. Lỗi worker, cancellation, timeout và debug

### 10.1. Trường hợp worker thất bại

Nếu một input file không đọc được, code trong `UppercaseWorkAction.execute()` ném `UncheckedIOException`. Khi `queue.await()` chạy, Gradle truyền lỗi từ worker về task và build thất bại. Điều cần làm là **sửa nguyên nhân**, không catch và bỏ qua toàn bộ lỗi worker để báo thành công giả.

Một số lỗi được bọc trong `WorkerExecutionException`; dùng `--stacktrace` và `--info` để tìm nguyên nhân sâu bên trong:

```bash
./gradlew uppercaseFiles --stacktrace --info --console=plain
```

Khi lỗi classpath/process isolation, kiểm tra JAR runtime, version Java, heap và messages `ClassNotFoundException`, `NoClassDefFoundError`, `OutOfMemoryError`.

### 10.2. Hủy và timeout

Worker có thể nhận tín hiệu ngắt khi người dùng dừng build hoặc task timeout. Với công việc chạy lâu, nên kiểm tra interruption ở những vòng lặp lớn, đóng stream bằng try-with-resources và giải phóng tài nguyên. Nếu tự viết đoạn `Thread.sleep(...)` để benchmark, đừng nuốt `InterruptedException` rồi tiếp tục xử lý như bình thường.

### 10.3. Đừng coi WorkQueue là thread-safe

`WorkQueue.submit()` nên được gọi từ task action tạo queue. Tự tạo thêm `Thread` rồi cho nhiều thread gọi submit trên **cùng** WorkQueue không phải thiết kế được đảm bảo; Gradle API nêu rõ WorkQueue **không thread-safe**. Worker API đã lo phần scheduler, nên đừng thêm thread pool thủ công trừ khi có yêu cầu riêng đã phân tích.

### 10.4. Một số checklist khi chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra/sửa |
| --- | --- | --- |
| Output chỉ có một file | Các item cùng ghi basename, input fileTree không khớp hoặc task không nhận đủ file. | Kiểm tra `sourceFiles`, đường dẫn output và mapping từng item. |
| File output bị lỗi ngẫu nhiên | Ghi chung file/static mutable state, data race. | Tách output, bỏ shared state, đặt barrier khi cần. |
| `--max-workers=4` không nhanh hơn `=1` | Work item quá nhỏ, I/O bottleneck hoặc overhead lớn. | Tăng workload hợp lý và benchmark nhiều lần. |
| `--dry-run` không tạo file | Dry-run không chạy task action. | Chạy thật, không dùng dry-run để kiểm tra nội dung. |
| `--parallel` không tạo 3 task con | Worker items không phải task nodes. | Dùng `WorkQueue.submit` để chia work trong task. |
| Lần thứ hai không thấy worker chạy | Task `UP-TO-DATE` hoặc `FROM-CACHE`. | Kiểm tra task outcome; thử thay input hoặc `--rerun-tasks`. |
| Worker process khởi tạo chậm | Cần start JVM mới, yêu cầu heap/classpath phức tạp. | Dùng mode ít cô lập hơn nếu an toàn; đo trước khi tối ưu. |
| `ClassNotFoundException` | Worker classpath thiếu thư viện. | Cấu hình `spec.getClasspath().from(...)` đúng mode. |
| Lỗi isolating/serializing parameters | Truyền `Project`, model container hoặc object không tương thích. | Chỉ dùng managed types và dữ liệu serializable đơn giản. |
| Build “thành công” dù worker lỗi | Đã tự swallow exception trong `execute()`. | Cho exception truyền về Gradle, chỉ catch để bổ sung ngữ cảnh. |
| Task bị invalid configuration cache | Action truy cập model Gradle trong worker, dữ liệu không được mô hình hóa. | Đưa giá trị vào managed WorkParameters/typed task inputs. |

## 11. Bài tập thực hành

**Bài 1 — Chuyển từ tuần tự sang song song.** Trong lớp `UppercaseFilesTask`, mô tả khác nhau giữa (a) gọi `Files.readString` trong vòng lặp `for` và (b) gọi `queue.submit` cho từng file, rồi `await()`. Vì sao thứ tự hoàn tất không được đảm bảo?

**Bài 2 — Thử giới hạn worker.** Dùng nhiều file đủ lớn, chạy lại với `--max-workers=1` và `--max-workers=4`, có `--rerun-tasks`. Ghi thời gian, CPU, memory. Không kết luận “4 nhanh gấp 4” nếu dữ liệu đo không chứng minh.

**Bài 3 — Đổi isolation.** Lần lượt thay `noIsolation()` bằng `classLoaderIsolation()` và `processIsolation()`. So sánh nội dung output, thời gian lần đầu, tài nguyên sử dụng. Giải thích khi nào cần classpath riêng và khi nào cần JVM riêng.

**Bài 4 — Tìm lỗi race.** Nếu `samples/one/config.txt` và `samples/two/config.txt` cùng ghi `build/uppercased/config.txt`, dự đoán output có ổn định không. Đề xuất đặt output theo đường dẫn tương đối để tránh collision.

**Bài 5 — Thay đổi input.** Chạy hai lần liên tiếp, sau đó sửa nội dung `samples/b.txt`. Phân biệt `UP-TO-DATE` với việc WorkAction tự động xử lý incremental per-file.

**Bài 6 — Cấu hình thất bại.** Tạo một input không thể đọc bằng permissions phù hợp trong môi trường thực hành; quan sát lỗi `UncheckedIOException` và Gradle stacktrace. Đừng dùng secret hoặc file hệ thống quan trọng để thử.

**Bài 7 — API.** Phác thảo một `WorkParameters` để xử lý ảnh với `RegularFileProperty inputImage`, `RegularFileProperty outputImage`, `Property<Integer> quality`. Chọn isolation mode khi dùng thư viện native không thread-safe và giải thích vì sao.

### Câu hỏi nhanh và đáp án

1. **Một WorkAction có phải task Gradle không?** Không; WorkAction là item bên trong một task.
2. **`--parallel` có bắt buộc để nhiều item của cùng task chạy đồng thời không?** Không; Worker API thực hiện scheduling riêng.
3. **WorkerExecutor có được khởi tạo bằng `new` không?** Không; sử dụng dependency injection `@Inject`.
4. **Tại sao phải dùng WorkParameters?** Để truyền dữ liệu rõ ràng, cô lập và tương thích với các mode thực thi.
5. **`classLoaderIsolation` có tạo process riêng không?** Không.
6. **`processIsolation` có tạo một JVM mới cho từng item không?** Không nhất thiết; Gradle có thể reuse compatible worker daemon.
7. **Có được submit mọi item rồi gọi `await()` một lần không?** Có, đó là mẫu sử dụng đúng trong ví dụ.
8. **WorkQueue có thread-safe không?** Không; submit từ luồng điều phối thay vì share cho nhiều luồng.
9. **Tại sao 10 work item vẫn có thể chạy từng đợt?** Scheduler bị giới hạn bởi `--max-workers`, yêu cầu cô lập và tài nguyên máy.
10. **Task khai báo output có đương nhiên cacheable không?** Không; up-to-date checking và build cache có các điều kiện riêng.

## 12. Tài liệu chính thức

- **Gradle — Developing Parallel Tasks (Worker API)**: https://docs.gradle.org/current/userguide/worker_api.html
- **Gradle — WorkerExecutor Javadoc** (injection, isolation, await): https://docs.gradle.org/current/javadoc/org/gradle/workers/WorkerExecutor.html
- **Gradle — WorkQueue Javadoc** (submit, await, thread-safety): https://docs.gradle.org/current/javadoc/org/gradle/workers/WorkQueue.html
- **Gradle — WorkAction Javadoc**: https://docs.gradle.org/current/javadoc/org/gradle/workers/WorkAction.html
- **Gradle — WorkParameters Javadoc**: https://docs.gradle.org/current/javadoc/org/gradle/workers/WorkParameters.html
- **Gradle — Implementing Custom Tasks** (typed inputs/outputs): https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- **Gradle — Configuring Builds for Performance** (worker concurrency and parallel execution): https://docs.gradle.org/current/userguide/performance.html
- **Gradle — Configuration Cache Requirements**: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html

**Ghi nhớ:** Worker API giúp chia một custom task thành nhiều work item độc lập; `WorkerExecutor` tạo môi trường, `WorkQueue` nhận các lần `submit`, `WorkParameters` đóng gói dữ liệu và `WorkAction.execute()` thực thi. Chọn mức cô lập đủ an toàn, tránh shared mutable state và output collision, đồng thời đo thực tế trước khi tăng số workers.