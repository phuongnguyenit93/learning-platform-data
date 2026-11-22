# Tác vụ cần thực hiện trước và ràng buộc thứ tự thực hiện

Một build Java thường gồm nhiều công việc: tải hoặc kiểm tra dependency, sinh mã nguồn, biên dịch, xử lý resource, chạy test, đóng gói JAR và tạo báo cáo. Các công việc này có quan hệ với nhau. Ví dụ, compiler phải có mã nguồn trước khi biên dịch; kiểm thử cần có class đã biên dịch; tác vụ đóng gói cần có class và resource đầu ra.

Build tool cần biết **tác vụ nào phụ thuộc vào tác vụ nào** và **thứ tự nào phải được giữ**. Nếu khai báo thiếu, build có thể chạy sai thứ tự hoặc chỉ thất bại trên một máy. Nếu khai báo quá nhiều quan hệ, build bị tuần tự hóa không cần thiết, giảm khả năng chạy song song và khó bảo trì.

Với Gradle, các quan hệ này được biểu diễn trong **task graph** — đồ thị các task cần thực thi cho một lần build. Một task có thể phụ thuộc vào task khác, yêu cầu thứ tự tương đối với task khác, hoặc khai báo một task cần chạy sau khi nó kết thúc. Những quan hệ đó có ý nghĩa khác nhau và cần chọn đúng loại.

## 1. Task và task graph

### 1.1. Task là gì?

Trong Gradle, task biểu diễn một đơn vị công việc của build. Ví dụ:

| Task | Công việc thường thực hiện |
|---|---|
| `compileJava` | Biên dịch mã nguồn Java chính |
| `processResources` | Xử lý và sao chép resource chính |
| `classes` | Gom các đầu ra cần thiết của source set chính |
| `test` | Chạy bộ kiểm thử |
| `jar` | Đóng gói class và resource thành JAR |
| `build` | Chạy các công việc build và kiểm tra theo cấu hình plugin |

Task có thể do Gradle core, plugin hoặc dự án tự định nghĩa tạo ra. Một task có thể có input, output, dependency và một hoặc nhiều task action.

Ví dụ khai báo task đơn giản bằng Groovy DSL:

```groovy
tasks.register('sayHello') {
    doLast {
        println 'Hello from Gradle'
    }
}
```

`tasks.register(...)` đăng ký task theo cơ chế lazy. Task được biểu diễn bằng `TaskProvider`, cho phép Gradle trì hoãn việc tạo và cấu hình đối tượng task cho đến khi cần. `doLast` thêm một action được thực hiện khi task chạy.

### 1.2. Task graph là gì?

Khi người dùng yêu cầu một task, Gradle xác định task đó và những task cần thiết để hoàn thành nó. Tập hợp các task được chọn cùng các quan hệ giữa chúng tạo thành task graph cho lần build đó.

Ví dụ, khi yêu cầu `jar`, một phần đồ thị có thể có dạng:

```text
compileJava ---------+
                     +----> classes ----+
processResources ----+                  |
                                        v
                                       jar
```

Sơ đồ thể hiện `jar` cần đầu ra từ `classes`; `classes` cần các đầu ra Java đã biên dịch và resource đã xử lý. Các plugin có thể bổ sung nhiều task hoặc quan hệ khác, nên task graph thực tế của dự án có thể lớn hơn.

Đồ thị có hướng: một cạnh dependency từ task `A` tới task `B` có nghĩa là `A` cần `B` hoàn thành trước khi `A` có thể thực hiện. Có thể đọc theo cách diễn đạt: **A depends on B**, tức `A` phụ thuộc vào `B`.

### 1.3. Gradle chọn task nào?

Task graph được hình thành từ những task người dùng yêu cầu trên command line hoặc qua API, rồi mở rộng theo các dependency của chúng. Ví dụ:

```bash
./gradlew jar
```

Gradle không chỉ chạy riêng task `jar`; nó đưa vào graph những task cần thiết để tạo artifact đó.

Nếu chạy:

```bash
./gradlew compileJava test
```

cả hai task được yêu cầu làm entry point. Graph sẽ bao gồm dependency của `compileJava` và `test`. Task dùng chung chỉ cần thực hiện một lần trong cùng build invocation.

Thứ tự viết tên task trên command line không phải cách đáng tin cậy để khai báo quan hệ phụ thuộc. Nếu `test` bắt buộc cần output do `generateSources` tạo, hãy mô tả quan hệ trong build script. Đừng dựa vào việc người dùng luôn nhớ chạy `generateSources` trước `test`.

## 2. Ba giai đoạn lớn của Gradle

Để hiểu task được chọn và chạy khi nào, cần phân biệt ba giai đoạn:

1. **Initialization:** xác định build, settings và các project tham gia.
2. **Configuration:** đánh giá build script, tạo/cấu hình mô hình project và task, rồi xác định task graph cần thực thi.
3. **Execution:** thực hiện các task action theo graph và các ràng buộc thứ tự.

Ví dụ:

```text
./gradlew build
       |
       v
Initialization
       |
       v
Configuration
  - đọc build scripts
  - đăng ký/cấu hình task
  - xác định task graph
       |
       v
Execution
  - thực hiện task dependencies
  - xử lý output/input
  - chạy task actions
```

Task action như `doLast` chạy trong execution phase. Đăng ký task bằng `tasks.register` và khai báo dependency là công việc cấu hình mô hình build. Không nên ghi tệp hoặc thực hiện công việc nặng ngay khi build script được đánh giá, vì điều đó có thể xảy ra ngay cả khi task tương ứng không nằm trong graph.

## 3. `dependsOn` — khai báo tác vụ tiên quyết

`dependsOn` biểu diễn quan hệ phụ thuộc: task được yêu cầu chỉ có thể chạy sau khi các task phụ thuộc hoàn tất.

Ví dụ, một task đóng gói báo cáo cần task tạo dữ liệu báo cáo chạy trước:

```groovy
tasks.register('generateReportData') {
    doLast {
        println 'Generating report data'
    }
}

tasks.register('packageReport') {
    dependsOn(tasks.named('generateReportData'))

    doLast {
        println 'Packaging report'
    }
}
```

Khi chạy:

```bash
./gradlew packageReport
```

Gradle đưa cả hai task vào graph và thực hiện `generateReportData` trước `packageReport`.

```text
generateReportData
        |
        | dependsOn relationship
        v
   packageReport
```

Mũi tên trong sơ đồ biểu diễn thứ tự thực hiện: task ở phía trên là dependency, task phía dưới là task phụ thuộc.

### 3.1. Một task có nhiều dependency

Một task có thể phụ thuộc vào nhiều task:

```groovy
tasks.register('publishArtifacts') {
    dependsOn(
        tasks.named('jar'),
        tasks.named('generateChecksums'),
        tasks.named('validateMetadata')
    )

    doLast {
        println 'Publishing artifacts'
    }
}
```

Gradle phải hoàn thành các dependency trước khi chạy `publishArtifacts`. Tuy nhiên, ba dependency không mặc nhiên phải chạy tuần tự với nhau. Nếu chúng độc lập và build cho phép chạy song song, Gradle có thể thực hiện chúng đồng thời.

```text
jar -------------------+
generateChecksums -----+----> publishArtifacts
validateMetadata ------+
```

Đây là điểm quan trọng: `dependsOn` thiết lập quan hệ giữa dependency và task phụ thuộc; nó không tự tạo quan hệ thứ tự giữa các dependency ngang hàng.

### 3.2. Dependency được kéo vào graph

Nếu task `A` phụ thuộc `B`, khi người dùng yêu cầu `A`, Gradle tự đưa `B` vào graph. Người dùng không phải gọi riêng `B`.

Ngược lại, nếu chỉ khai báo `A.mustRunAfter(B)`, task `B` không tự động được đưa vào graph. Khác biệt này sẽ được giải thích ở phần ràng buộc thứ tự.

### 3.3. Dùng `TaskProvider` để giữ cấu hình lazy

Với task do dự án hoặc plugin đăng ký, nên tham chiếu qua provider:

```groovy
def generateTask = tasks.register('generateSources') {
    doLast {
        println 'Generate source files'
    }
}

tasks.register('compileGeneratedSources') {
    dependsOn(generateTask)

    doLast {
        println 'Compile generated sources'
    }
}
```

`generateTask` là `TaskProvider`, không phải đối tượng task đã được tạo ngay tại thời điểm khai báo. Gradle có thể tận dụng provider để trì hoãn cấu hình task và tối ưu configuration phase.

Với task đã được đăng ký ở nơi khác, có thể lấy provider bằng:

```groovy
tasks.named('compileJava') {
    dependsOn(tasks.named('generateSources'))
}
```

Nếu task không tồn tại hoặc tên task sai, Gradle sẽ báo lỗi khi phân giải task tương ứng. Cần kiểm tra tên task được plugin thực sự đăng ký.

## 4. `mustRunAfter` — bắt buộc thứ tự khi cả hai task đã được chọn

`mustRunAfter` đặt ràng buộc thứ tự giữa hai task: nếu cả hai cùng có mặt trong task graph, task được chỉ định phải chạy sau task làm mốc.

Ví dụ:

```groovy
tasks.named('integrationTest') {
    mustRunAfter(tasks.named('test'))
}
```

Nếu cả `test` và `integrationTest` được chọn, Gradle phải chạy `test` trước `integrationTest`.

Tuy nhiên, chạy riêng:

```bash
./gradlew integrationTest
```

không có nghĩa Gradle sẽ tự chạy `test`. `mustRunAfter` chỉ điều chỉnh thứ tự giữa các task đã có trong graph; nó không tạo dependency và không kéo task đứng trước vào graph.

Muốn `integrationTest` luôn yêu cầu `test` hoàn thành, cần dùng `dependsOn`:

```groovy
tasks.named('integrationTest') {
    dependsOn(tasks.named('test'))
}
```

Chỉ thêm `mustRunAfter` nếu mục tiêu là điều khiển thứ tự trong trường hợp cả hai task đã được chọn bởi một task cấp cao hoặc bởi command line.

### 4.1. Khi nào dùng `mustRunAfter`?

Ví dụ, dự án có hai task kiểm tra độc lập `checkFormatting` và `checkLicense`. Task `verifyRepository` phụ thuộc cả hai:

```groovy
tasks.register('verifyRepository') {
    dependsOn('checkFormatting', 'checkLicense')
}
```

Nếu có yêu cầu báo cáo định dạng luôn xuất hiện trước báo cáo license khi chạy chung, có thể thêm:

```groovy
tasks.named('checkLicense') {
    mustRunAfter(tasks.named('checkFormatting'))
}
```

Dependency graph bảo đảm cả hai được chọn khi chạy `verifyRepository`; `mustRunAfter` thêm thứ tự giữa chúng.

Không nên dùng `mustRunAfter` để biểu diễn việc một task cần output của task kia. Nếu task thứ hai cần file do task thứ nhất tạo, quan hệ đúng là dependency hoặc kết nối input/output có dependency được suy ra.

## 5. `shouldRunAfter` — thứ tự ưu tiên nhưng có thể linh hoạt

`shouldRunAfter` cũng biểu diễn mong muốn chạy task này sau task khác nếu cả hai được chọn, nhưng đây là ràng buộc mềm. Gradle có thể bỏ qua nó trong một số trường hợp, chẳng hạn khi áp dụng nó làm phát sinh vòng lặp trong thứ tự hoặc khi giữ thứ tự đó sẽ cản trở việc thực thi song song.

Ví dụ:

```groovy
tasks.named('slowQualityReport') {
    shouldRunAfter(tasks.named('test'))
}
```

Ý nghĩa: nếu `test` và `slowQualityReport` cùng được chọn, Gradle nên chạy `slowQualityReport` sau `test` khi có thể. Nhưng đây không phải bảo đảm cứng như `mustRunAfter`.

Có thể dùng `shouldRunAfter` cho các task độc lập khi muốn thứ tự đầu ra log hoặc báo cáo dễ đọc hơn, nhưng vẫn muốn Gradle có quyền sắp xếp linh hoạt để tăng khả năng chạy song song.

Không dùng `shouldRunAfter` khi task thực sự cần kết quả từ task khác. Nếu có quan hệ dữ liệu hoặc điều kiện tiên quyết, hãy dùng `dependsOn` hoặc khai báo input/output đúng cách.

## 6. `finalizedBy` — tác vụ chạy sau để hoàn tất hoặc dọn dẹp

`finalizedBy` khai báo một task finalizer cần chạy sau task được hoàn tất. Đây thường là cơ chế cho báo cáo, thu thập log, dọn dẹp tài nguyên hoặc đóng một dịch vụ tạm.

Ví dụ:

```groovy
tasks.register('stopTestEnvironment') {
    doLast {
        println 'Stopping test environment'
    }
}

tasks.register('startTestEnvironment') {
    doLast {
        println 'Starting test environment'
    }

    finalizedBy(tasks.named('stopTestEnvironment'))
}
```

Khi `startTestEnvironment` được đưa vào graph, task finalizer `stopTestEnvironment` cũng được đưa vào graph và được lên lịch sau task được finalize.

Trong thực tế, tên task ví dụ trên chỉ minh họa quan hệ. Một task có tên `start...` thường cần một task kiểm thử hoặc tác vụ sử dụng môi trường được chạy ở giữa; không nên suy luận rằng `finalizedBy` sẽ tự chèn một task bất kỳ vào giữa hai task.

Ví dụ thực tế hơn: task chạy kiểm thử cần luôn tạo báo cáo sau khi kết thúc:

```groovy
tasks.register('writeTestSummary') {
    doLast {
        println 'Writing test summary'
    }
}

tasks.named('test') {
    finalizedBy(tasks.named('writeTestSummary'))
}
```

Finalizer được lên lịch khi task được finalize được chọn. Cơ chế này được thiết kế để finalizer vẫn có cơ hội chạy sau task được finalize kể cả khi task đó thất bại. Tuy nhiên, nếu toàn bộ build bị dừng đột ngột bởi tiến trình bên ngoài, máy bị tắt hoặc JVM bị kết thúc, không có bảo đảm rằng finalizer sẽ thực thi xong.

### 6.1. Phân biệt `finalizedBy` với `dependsOn`

| Câu hỏi | `dependsOn` | `finalizedBy` |
|---|---|---|
| Task được thêm vào graph vì quan hệ này? | Có, dependency được kéo vào graph | Có, finalizer được kéo vào graph khi task được finalize được chọn |
| Thứ tự | Dependency chạy trước task phụ thuộc | Finalizer chạy sau task được finalize |
| Mục đích thường gặp | Chuẩn bị input, sinh mã, biên dịch, kiểm tra | Dọn dẹp, tạo báo cáo, thu thập kết quả |
| Nếu task chính thất bại | Dependency đã chạy trước đó; task phụ thuộc không chạy nếu dependency thất bại theo luồng thông thường | Finalizer được thiết kế để vẫn chạy sau task được finalize khi build còn tiếp tục điều phối |

Không dùng `finalizedBy` để mô tả một prerequisite. Nếu task `compileJava` cần source từ `generateSources`, generator phải chạy trước compile, vì vậy quan hệ đúng là `compileJava.dependsOn(generateSources)` hoặc cơ chế nối output/input tương ứng.

## 7. So sánh các quan hệ task

| Quan hệ | Đảm bảo điều gì? | Có kéo task khác vào graph? | Dùng khi nào? |
|---|---|---|---|
| `dependsOn` | Dependency phải hoàn tất trước task phụ thuộc | Có | Task cần kết quả hoặc điều kiện tiên quyết từ task khác |
| `mustRunAfter` | Nếu cả hai được chọn, task này phải chạy sau task kia | Không | Ép thứ tự giữa các task đã được chọn |
| `shouldRunAfter` | Nếu có thể, task này nên chạy sau task kia | Không | Thứ tự ưu tiên mềm, có thể bỏ qua |
| `finalizedBy` | Finalizer được lên lịch sau task được finalize | Có | Dọn dẹp, báo cáo, thu thập kết quả sau task |

Có thể ghi nhớ bằng bốn câu hỏi:

- **Cần task kia để hoàn thành công việc?** Dùng `dependsOn` hoặc khai báo input/output để Gradle suy ra dependency.
- **Cả hai đã được chọn, chỉ cần điều chỉnh thứ tự?** Dùng `mustRunAfter`.
- **Chỉ muốn ưu tiên thứ tự nhưng cho phép Gradle linh hoạt?** Dùng `shouldRunAfter`.
- **Cần một việc chạy sau khi task kết thúc?** Dùng `finalizedBy`.

## 8. Khai báo quan hệ qua input và output

Một cách thiết kế tốt là mô tả dữ liệu mà task tạo ra và dữ liệu task khác tiêu thụ. Khi provider của output task được nối trực tiếp với input của task tiêu thụ, Gradle có thể suy ra dependency giữa hai task.

Ví dụ dưới đây minh họa một task tạo tệp dữ liệu và một task đọc tệp đó. Các kiểu property giúp Gradle biết output và input:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateMessage extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = 'Message generated by Gradle'
    }
}

abstract class ConsumeMessage extends DefaultTask {
    @InputFile
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void consume() {
        println inputFile.get().asFile.text
    }
}

def generateMessage = tasks.register('generateMessage', GenerateMessage) {
    outputFile.set(layout.buildDirectory.file('generated/message.txt'))
}

tasks.register('consumeMessage', ConsumeMessage) {
    inputFile.set(generateMessage.flatMap { it.outputFile })
}
```

Trong ví dụ, `consumeMessage` nhận provider trỏ tới output file của `generateMessage`. Khi Gradle nhận ra input của task tiêu thụ được cung cấp bởi output của task khác, nó có thể thiết lập quan hệ task dependency tương ứng. Khi chạy:

```bash
./gradlew consumeMessage
```

Gradle sẽ chạy `generateMessage` trước nếu cần để tạo input, sau đó mới chạy `consumeMessage`.

Khai báo input/output có thêm lợi ích: Gradle có thể kiểm tra task có `UP-TO-DATE` hay không, hỗ trợ incremental build và build cache nếu task được thiết kế phù hợp. Nếu chỉ viết `dependsOn` nhưng không khai báo dữ liệu đầu vào/đầu ra, Gradle biết thứ tự nhưng khó xác định chính xác khi nào output còn hợp lệ.

Khi một task tiêu thụ nhiều tệp, hãy dùng property phù hợp như `ConfigurableFileCollection`, `DirectoryProperty` hoặc `RegularFileProperty` và annotation `@InputFiles`, `@InputDirectory`, `@InputFile`, `@OutputDirectory` hoặc `@OutputFile` theo đúng bản chất dữ liệu.

## 9. Ví dụ tổng hợp: generate, compile, test và report

Giả sử dự án có quy trình:

1. Sinh mã nguồn từ schema.
2. Biên dịch mã nguồn.
3. Chạy test.
4. Tạo báo cáo kết quả sau test.

Có thể mô hình hóa dependency và finalizer như sau:

```groovy
tasks.register('generateSources') {
    doLast {
        println '1. Generate sources'
    }
}

tasks.named('compileJava') {
    dependsOn(tasks.named('generateSources'))
}

tasks.register('writeTestReport') {
    doLast {
        println '4. Write test report'
    }
}

tasks.named('test') {
    dependsOn(tasks.named('compileJava'))
    finalizedBy(tasks.named('writeTestReport'))
}
```

Sơ đồ quan hệ:

```text
generateSources
       |
       v
  compileJava
       |
       v
      test
       |
       v
writeTestReport (finalizer)
```

Đây là mô hình minh họa. Java plugin đã định nghĩa các quan hệ mặc định giữa `test`, `testClasses`, `classes`, `compileJava` và các task liên quan. Trong dự án thật, cần tránh khai báo lại dependency đã có sẵn nếu không cần thiết. Ví dụ này cho thấy nơi có thể bổ sung generator và finalizer vào quy trình.

Nếu `test` được yêu cầu, dependency chain sẽ kéo `compileJava` và `generateSources` vào graph. Finalizer `writeTestReport` được đưa vào graph để chạy sau `test`.

Nếu chỉ chạy `compileJava`, `test` và `writeTestReport` không tự động chạy vì chúng không phải dependency của `compileJava` và finalizer chỉ được kích hoạt khi task được finalize được chọn.

## 10. Thứ tự task không đồng nghĩa với thứ tự task action

Một task có thể có nhiều action. `doFirst` và `doLast` điều khiển thứ tự action **bên trong cùng một task**:

```groovy
tasks.register('sampleTask') {
    doFirst {
        println 'First action'
    }

    doLast {
        println 'Last action'
    }
}
```

`doFirst` thêm action ở đầu danh sách action, còn `doLast` thêm action ở cuối. Các action này không tạo task mới và không thay thế quan hệ dependency giữa những task khác nhau.

Phân biệt:

- `dependsOn`, `mustRunAfter`, `shouldRunAfter`, `finalizedBy`: quan hệ giữa các task trong task graph.
- `doFirst`, `doLast`: thứ tự action bên trong một task.
- Thứ tự dòng lệnh trên terminal: danh sách task người dùng yêu cầu, không phải cơ chế thay thế khai báo dependency trong build script.

## 11. Chạy song song và các task độc lập

Gradle có thể thực hiện các task độc lập theo cách song song nếu cấu hình build và điều kiện thực thi cho phép. Ví dụ:

```text
                 +--> compileJava --+
                 |                  |
generateSources -+                  +--> packageApp
                 |                  |
                 +--> generateDocs -+
```

Nếu cả `compileJava` và `generateDocs` cùng phụ thuộc `generateSources`, chúng phải chờ generator hoàn tất. Sau đó, hai nhánh có thể chạy song song nếu không có ràng buộc hoặc tài nguyên chung ngăn cản.

Nếu thêm:

```groovy
tasks.named('generateDocs') {
    mustRunAfter(tasks.named('compileJava'))
}
```

thì hai task sẽ bị ràng buộc thứ tự khi cùng nằm trong graph. Điều này có thể giảm khả năng chạy song song. Chỉ thêm ràng buộc khi có lý do thực tế, chẳng hạn hai task cùng ghi vào một thư mục hoặc cần đọc kết quả của nhau.

Không nên dùng `mustRunAfter` để che giấu việc hai task cùng ghi một output. Cách đúng thường là tách output directory, khai báo input/output rõ ràng hoặc hợp nhất trách nhiệm vào một task phù hợp.

## 12. Chu trình dependency và thứ tự không hợp lệ

Task graph cần có thứ tự thực thi hợp lệ. Một chu trình dependency khiến Gradle không thể tìm được task nào phải chạy trước.

Ví dụ sai:

```groovy
tasks.register('taskA') {
    dependsOn('taskB')
}

tasks.register('taskB') {
    dependsOn('taskA')
}
```

Sơ đồ:

```text
taskA ---> taskB
  ^          |
  |__________|
```

`taskA` yêu cầu `taskB`, trong khi `taskB` lại yêu cầu `taskA`. Không task nào có thể bắt đầu trước khi dependency của nó hoàn thành. Gradle sẽ báo lỗi circular dependency hoặc lỗi chu trình tương ứng.

Chu trình có thể xuất hiện gián tiếp qua nhiều task hoặc plugin:

```text
taskA -> taskB -> taskC -> taskD -> taskA
```

Khi gặp lỗi, cần lần theo toàn bộ đường dependency chứ không chỉ hai task được nêu đầu tiên trong thông báo.

Các ràng buộc thứ tự mềm như `shouldRunAfter` có thể bị bỏ qua khi chúng gây xung đột hoặc chu trình. Với `mustRunAfter`, hãy thiết kế quan hệ sao cho không tạo ra thứ tự mâu thuẫn. Không nên dựa vào việc Gradle tự đoán cách giải quyết một đồ thị được khai báo không nhất quán.

## 13. Phân biệt task dependency với dependency của thư viện

Trong Gradle, từ “dependency” có thể nói về hai khái niệm khác nhau:

| Loại dependency | Ví dụ | Ý nghĩa |
|---|---|---|
| Task dependency | `compileJava.dependsOn(generateSources)` | Task nào phải hoàn tất trước task khác |
| Library dependency | `implementation 'org.example:library:1.0'` | Thư viện nào cần có trên compile/runtime classpath |

Khai báo thư viện trong `dependencies {}` không đồng nghĩa với việc tạo một task dependency trực tiếp mà người viết build script phải tự điều khiển. Plugin Java và dependency resolution quản lý việc giải quyết thư viện, tạo classpath và kết nối các tác vụ biên dịch theo mô hình build.

Ví dụ:

```groovy
dependencies {
    implementation 'org.example:library:1.0'
}
```

Khai báo trên nói rằng ứng dụng cần thư viện `org.example:library:1.0` trong cấu hình `implementation`. Nó không có nghĩa task `compileJava` phải chạy sau một task do lập trình viên tự đặt tên là `downloadLibrary`. Gradle xử lý việc phân giải dependency theo các configuration và task liên quan.

## 14. Quan hệ task trong build nhiều project

Gradle có thể chứa nhiều project con. Task ở project này có thể phụ thuộc vào task ở project khác nếu build có cấu hình tương ứng.

Ví dụ notation của task ở project con:

```groovy
tasks.register('assembleDistribution') {
    dependsOn(':service:jar', ':web:jar')
}
```

Khi yêu cầu `assembleDistribution`, Gradle đưa task `jar` của hai project `service` và `web` vào graph cùng các dependency của chúng.

Task path bắt đầu bằng `:` để chỉ project path trong build. Cần bảo đảm project và task được tham chiếu tồn tại. Với build phức tạp, nên dùng API provider hoặc cơ chế variant/artifact của Gradle thay vì liên kết task thủ công nếu mục tiêu thực sự là truyền artifact giữa các project.

## 15. Maven và thứ tự thực hiện

Maven có cách tổ chức khác Gradle. Maven sử dụng các lifecycle và phase theo thứ tự định nghĩa. Plugin gắn goal vào một phase; khi yêu cầu một phase, Maven chạy các phase trước đó trong lifecycle tương ứng.

Ví dụ các phase của default lifecycle:

```text
validate
   |
   v
compile
   |
   v
test
   |
   v
package
   |
   v
verify
   |
   v
install
   |
   v
deploy
```

Đây là một phần chuỗi phase được rút gọn để minh họa; lifecycle thực tế có thêm nhiều phase ở giữa. Nếu một plugin gắn goal sinh source vào `generate-sources`, goal đó sẽ chạy trước phase `compile` khi người dùng gọi `mvn compile` hoặc một phase phía sau.

Maven không dùng mô hình task graph có thể tự do biểu diễn `dependsOn`, `mustRunAfter` và `finalizedBy` theo cùng API của Gradle. Khi làm việc với Maven, cần hiểu lifecycle, phase, plugin execution và thứ tự khai báo execution trong cấu hình plugin.

Không nên áp dụng cú pháp Gradle vào Maven hoặc cho rằng thứ tự phase Maven và task graph Gradle hoàn toàn tương đương. Cả hai đều điều phối công việc build, nhưng mô hình cấu hình và quy tắc thực thi khác nhau.

## 16. Quan sát task graph và thứ tự thực thi

### 16.1. Dùng `--dry-run`

Gradle hỗ trợ `--dry-run` để hiển thị task dự kiến thực hiện mà không chạy task action:

```bash
./gradlew build --dry-run
```

Có thể dùng lệnh này để kiểm tra:

- Task dependency có được kéo vào graph không.
- Generator có đứng trước compiler không.
- Finalizer có được đưa vào graph không.
- Có task nào bị chọn ngoài dự kiến không.

`--dry-run` cho biết kế hoạch task ở mức task graph; nó không chứng minh task action chạy thành công hoặc output thực tế đã được tạo.

### 16.2. Xem log task

```bash
./gradlew build --info
```

Log `--info` cung cấp thêm thông tin về task được thực hiện, bỏ qua hoặc đánh dấu `UP-TO-DATE`. Nếu cần điều tra sâu hơn, có thể tăng mức log, nhưng log chi tiết có thể rất dài.

### 16.3. Liệt kê task

```bash
./gradlew tasks --all
```

Lệnh này giúp tìm tên task do plugin đăng ký. Khi một dependency tham chiếu sai tên, kiểm tra danh sách task thực tế thay vì đoán từ tên plugin.

### 16.4. Đọc quan hệ từ build script

Khi một task chạy trước hoặc sau một task khác, tìm các cấu hình:

```groovy
dependsOn(...)
mustRunAfter(...)
shouldRunAfter(...)
finalizedBy(...)
```

Ngoài ra, kiểm tra input/output provider có tạo ra dependency được suy ra hay không, và plugin có tự đăng ký task relationship không. Không phải mọi cạnh trong task graph đều xuất hiện dưới dạng một dòng `dependsOn` do người dùng viết.

## 17. Những lỗi thường gặp khi khai báo thứ tự task

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Chạy task compile nhưng generated source chưa tồn tại | Chưa khai báo dependency hoặc output/input connection | Nối generator vào compile bằng dependency hoặc provider input/output |
| Chạy task B nhưng task A không tự chạy dù có `mustRunAfter` | `mustRunAfter` chỉ sắp thứ tự, không kéo A vào graph | Dùng `dependsOn` nếu B cần A |
| Hai task chạy theo thứ tự không mong muốn | Chưa khai báo quan hệ hoặc chỉ có ràng buộc mềm | Xác định quan hệ dữ liệu và dùng đúng loại constraint |
| Build chậm sau khi thêm nhiều `mustRunAfter` | Các task độc lập bị tuần tự hóa | Loại bỏ constraint không cần thiết, để Gradle chạy song song |
| Finalizer không chạy trong một tình huống | Task được finalize không được chọn, hoặc build/process bị kết thúc đột ngột | Kiểm tra graph và phân biệt lỗi task với việc dừng toàn bộ tiến trình |
| Lỗi circular dependency | Quan hệ dependency hoặc ordering tạo chu trình | Lần theo toàn bộ đường cạnh và loại bỏ quan hệ mâu thuẫn |
| Task chạy lại quá nhiều | Input/output chưa khai báo hoặc output không ổn định | Khai báo input/output đúng và làm task có kết quả xác định |
| Task không chạy dù được khai báo trong script | Task chưa được yêu cầu và không phải dependency/finalizer | Kiểm tra task graph và entry point của build |
| Task dependency chạy nhưng task chính vẫn không tìm thấy file | Đường dẫn output và input không khớp, hoặc generator ghi ở nơi khác | Kết nối output provider với input và kiểm tra đường dẫn thực tế |

## 18. Quy trình thiết kế một quan hệ task

Khi cần nối hai tác vụ, hãy trả lời lần lượt:

1. **Task sau có cần dữ liệu do task trước tạo ra không?** Nếu có, mô tả dữ liệu bằng input/output và thiết lập dependency.
2. **Task sau chỉ cần task trước hoàn thành vì một quy tắc vận hành?** Nếu có, cân nhắc `dependsOn` nếu đó là prerequisite thật, hoặc `mustRunAfter` nếu cả hai đã được chọn độc lập.
3. **Thứ tự chỉ là mong muốn để log/report dễ đọc?** Dùng `shouldRunAfter` nếu có thể chấp nhận Gradle bỏ qua ràng buộc.
4. **Cần thu thập kết quả hoặc dọn dẹp sau task?** Dùng `finalizedBy` cho finalizer.
5. **Các task có thể chạy song song không?** Tránh thêm thứ tự cứng nếu không có phụ thuộc dữ liệu hoặc yêu cầu vận hành.
6. **Có nguy cơ tạo chu trình không?** Lần theo graph cả chiều dependency lẫn các ràng buộc thứ tự.
7. **Task có khai báo input/output chính xác không?** Đây là cơ sở để Gradle thực hiện up-to-date check, incremental build và cache đáng tin cậy.

## 19. Kết luận

Task graph giúp Gradle xác định những công việc cần thực hiện và thứ tự hợp lệ giữa chúng. `dependsOn` thể hiện prerequisite và kéo dependency vào graph; `mustRunAfter` áp đặt thứ tự khi cả hai task đã được chọn; `shouldRunAfter` chỉ là ưu tiên mềm; `finalizedBy` đưa một task hoàn tất hoặc dọn dẹp vào sau task được finalize.

Khi task tạo dữ liệu cho task khác, nên khai báo input/output để Gradle hiểu cả quan hệ dữ liệu lẫn thứ tự. Khi task độc lập, hãy giữ chúng độc lập để Gradle có thể chạy song song. Một task graph rõ ràng giúp build đúng, dễ quan sát, có khả năng tái sử dụng kết quả và ít phụ thuộc vào cách người dùng gọi lệnh trên terminal.
