# Gắn tác vụ tùy chỉnh vào đúng giai đoạn

Một dự án Java thường cần nhiều công việc ngoài những tác vụ mặc định của build tool. Ví dụ, dự án có thể cần sinh mã từ schema, kiểm tra quy tắc nội bộ, xác thực cấu hình, tạo tài liệu, chuẩn bị artifact hoặc thu thập báo cáo sau khi kiểm thử.

Khi thêm một tác vụ tùy chỉnh, điều quan trọng là xác định **khi nào tác vụ đó cần chạy và tác vụ nào cần sử dụng kết quả của nó**. Nếu sinh mã, tác vụ phải hoàn thành trước khi compiler đọc mã được sinh. Nếu kiểm tra chất lượng, tác vụ nên tham gia luồng `check`. Nếu tạo thêm artifact để phân phối, nó thường thuộc luồng `assemble`. Nếu tạo báo cáo sau kiểm thử, có thể gắn nó với task kiểm thử bằng cơ chế finalizer.

Trong Gradle, không có một tập hợp phase cố định tương đương hoàn toàn với Maven. Gradle tổ chức build bằng các giai đoạn xử lý build và một task graph. Vì vậy, gắn tác vụ tùy chỉnh đúng chỗ chủ yếu là khai báo quan hệ giữa task và chọn đúng task lifecycle làm điểm tích hợp.

## 1. Phân biệt giai đoạn của Gradle với task lifecycle

Gradle có ba giai đoạn lớn trong vòng đời của một build invocation:

1. **Initialization:** xác định build, đọc settings và xác định các project tham gia.
2. **Configuration:** đánh giá build script, đăng ký/cấu hình task, tạo mô hình project và xác định task graph cần thực thi.
3. **Execution:** thực thi các task action theo task graph đã được xác định.

Luồng khái quát:

```text
./gradlew build
       |
       v
Initialization
  - đọc settings.gradle
  - xác định các project
       |
       v
Configuration
  - đọc build.gradle
  - đăng ký và cấu hình task
  - tạo task graph
       |
       v
Execution
  - chạy task dependency
  - thực thi task action
  - tạo output
```

Ba giai đoạn này mô tả cách Gradle xử lý một lần build. Chúng không phải là những phase mà người viết build script có thể tùy ý gắn task vào bằng cách đặt tên như `compile-phase` hoặc `package-phase`.

Ngoài ra, Java plugin cung cấp các task lifecycle như `classes`, `test`, `check`, `assemble` và `build`. Đây là các task có ý nghĩa tổng hợp trong task graph. Chúng là điểm tích hợp thuận tiện để nối tác vụ tùy chỉnh vào quy trình phát triển.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Build lifecycle phase | Giai đoạn Gradle xử lý build invocation | Initialization, Configuration, Execution |
| Task | Một đơn vị công việc | `compileJava`, `generateSources`, `check` |
| Lifecycle task | Task tổng hợp đại diện cho một nhóm công việc | `check`, `assemble`, `build` |
| Task action | Phần logic thực thi của task | `@TaskAction`, `doLast` |
| Task dependency | Quan hệ để một task được thực hiện trước task khác | `compileJava.dependsOn(generateSources)` |

Không nên nhầm `group` của task như `verification` hoặc `build` với một giai đoạn thực thi. `group` và `description` chủ yếu giúp phân loại và hiển thị task trong danh sách task; chúng không tự tạo thứ tự hoặc dependency.

## 2. Xác định điểm tích hợp theo mục đích công việc

Trước khi đăng ký task, hãy xác định tác vụ tùy chỉnh thuộc loại công việc nào.

| Mục đích | Điểm tích hợp thường phù hợp | Lý do |
|---|---|---|
| Sinh Java source cần dùng khi biên dịch | `compileJava` hoặc source set/task compile tương ứng | Compiler phải nhìn thấy source đã được sinh |
| Sinh resource cho ứng dụng | `processResources` hoặc input của task xử lý resource | Resource phải được xử lý trước khi đóng gói |
| Kiểm tra source, cấu hình hoặc quy tắc dự án | `check` | Đây là luồng verification tổng hợp của Java plugin |
| Tạo artifact bổ sung để phân phối | `assemble` | Đây là luồng tổng hợp các artifact của dự án |
| Chạy kiểm thử đặc biệt | `check` hoặc task kiểm thử phù hợp | Đưa kiểm thử vào luồng xác minh tiêu chuẩn |
| Tạo báo cáo sau một task cụ thể | `finalizedBy` task tương ứng | Báo cáo được lên lịch sau task được finalize |
| Phát hành hoặc triển khai ra hệ thống ngoài | Task phát hành riêng, thường được gọi rõ ràng | Tránh tạo tác dụng phụ ngoài ý muốn trong build thông thường |

Đây là hướng dẫn chọn điểm tích hợp, không phải quy tắc cứng cho mọi plugin. Cần dựa trên dữ liệu đầu vào/đầu ra và hợp đồng của tác vụ thực tế.

## 3. Dùng `tasks.register` để đăng ký task tùy chỉnh

Gradle khuyến nghị đăng ký task theo cơ chế lazy bằng `tasks.register(...)`. Cách này trả về `TaskProvider`, giúp Gradle trì hoãn việc tạo và cấu hình task cho đến khi task thực sự cần thiết.

Ví dụ task kiểm tra một quy tắc nội bộ:

```groovy
tasks.register('verifyModuleMetadata') {
    group = 'verification'
    description = 'Validates module metadata before verification completes.'

    doLast {
        println 'Validating module metadata'
        // Thực hiện kiểm tra thực tế ở đây.
    }
}
```

Trong ví dụ:

- `verifyModuleMetadata` là tên task mà người dùng có thể gọi.
- `group` giúp task xuất hiện trong nhóm phù hợp khi liệt kê task.
- `description` mô tả mục đích của task.
- `doLast` thêm task action chạy trong execution phase.

Task được đăng ký chưa có nghĩa là nó sẽ tự chạy trong mọi build. Nó chỉ chạy khi được yêu cầu trực tiếp hoặc được kéo vào task graph qua dependency/finalizer hay quan hệ phù hợp khác.

Có thể gọi trực tiếp:

```bash
./gradlew verifyModuleMetadata
```

Hoặc nối task này vào một task lifecycle để người dùng không phải nhớ gọi riêng.

## 4. Gắn tác vụ kiểm tra vào `check`

Java plugin cung cấp task `check` làm điểm tổng hợp cho các tác vụ xác minh như kiểm thử và các kiểm tra chất lượng khác. Nếu task tùy chỉnh xác minh source, metadata, cấu hình hoặc quy tắc của dự án, thường nên gắn nó vào `check`.

```groovy
plugins {
    id 'java'
}

def verifyModuleMetadata = tasks.register('verifyModuleMetadata') {
    group = 'verification'
    description = 'Validates module metadata.'

    doLast {
        println 'Module metadata is valid'
    }
}

tasks.named('check') {
    dependsOn(verifyModuleMetadata)
}
```

Khi chạy:

```bash
./gradlew check
```

Gradle sẽ đưa `verifyModuleMetadata` vào task graph và chạy nó như một phần của luồng verification. Nếu task kiểm tra thất bại, `check` cũng không thể hoàn thành thành công.

Điểm tích hợp này phù hợp khi kết quả kiểm tra có ý nghĩa như một điều kiện chất lượng của dự án. Không nên đưa tác vụ có tác dụng phụ lớn hoặc cần thông tin bí mật vào `check` nếu mọi build/CI thông thường đều không nên thực hiện tác vụ đó.

## 5. Gắn tác vụ tạo artifact vào `assemble`

Task `assemble` là điểm tổng hợp các tác vụ tạo artifact của dự án. Nếu plugin hoặc dự án tạo thêm một gói phân phối, archive hoặc artifact cần được tạo cùng các sản phẩm build thông thường, có thể gắn task vào `assemble`.

```groovy
def packageAdditionalDocs = tasks.register('packageAdditionalDocs') {
    group = 'build'
    description = 'Packages additional project documentation.'

    doLast {
        println 'Packaging additional documentation'
    }
}

tasks.named('assemble') {
    dependsOn(packageAdditionalDocs)
}
```

Khi chạy:

```bash
./gradlew assemble
```

task bổ sung được kéo vào graph. Nếu tác vụ tạo artifact thật, nên khai báo rõ output file hoặc output directory để Gradle quản lý tính up-to-date và build cache.

`assemble` không phải là nơi thích hợp cho mọi thao tác sau biên dịch. Nếu một task cần class file cụ thể, hãy nối nó với task tạo class file tương ứng hoặc truyền output provider. Chỉ gắn vào `assemble` nếu mục tiêu của nó thực sự là tạo một artifact thuộc luồng assembly.

## 6. Gắn tác vụ vào `build`

Trong Java plugin, `build` là task tổng hợp cấp cao, thường bao gồm luồng verification (`check`) và tạo artifact (`assemble`). Nếu một tác vụ chỉ có ý nghĩa khi toàn bộ quy trình build hoàn tất, có thể gắn vào `build`, nhưng cần cân nhắc mục đích của task.

Ví dụ:

```groovy
def validateDistribution = tasks.register('validateDistribution') {
    group = 'verification'
    description = 'Validates the assembled distribution.'

    doLast {
        println 'Distribution validation completed'
    }
}

tasks.named('build') {
    dependsOn(validateDistribution)
}
```

Nếu `validateDistribution` cần artifact do `assemble` tạo, nên khai báo rõ dependency hoặc input/output tương ứng:

```groovy
tasks.named('validateDistribution') {
    dependsOn(tasks.named('assemble'))
}
```

Trong thực tế, task có thể được nối qua provider của artifact thay vì chỉ `dependsOn`. Cách nối dữ liệu giúp Gradle biết chính xác file nào được tạo và file nào được tiêu thụ.

Không nên gắn mọi task tùy chỉnh vào `build` chỉ vì muốn chúng tự chạy. `build` là entry point phổ biến trong CI và có thể được gọi thường xuyên bởi lập trình viên. Một tác vụ tải dữ liệu, publish artifact, deploy hoặc gửi thông báo ra ngoài thường nên là task riêng để được gọi chủ động.

## 7. Gắn tác vụ sinh mã trước khi biên dịch

Nếu task tạo Java source mà `compileJava` cần đọc, task generate phải chạy trước compile. Có thể khai báo dependency trực tiếp:

```groovy
plugins {
    id 'java'
}

def generatedSourcesDir = layout.buildDirectory.dir(
    'generated/sources/custom/main'
)

def generateCustomSources = tasks.register('generateCustomSources') {
    group = 'build'
    description = 'Generates Java sources required by compilation.'
    outputs.dir(generatedSourcesDir)

    doLast {
        def outputFile = generatedSourcesDir.get()
            .file('com/example/generated/BuildInfo.java')
            .asFile

        outputFile.parentFile.mkdirs()
        outputFile.text = '''package com.example.generated;

public final class BuildInfo {
    public static final String VALUE = "generated";

    private BuildInfo() {
    }
}
'''
    }
}

sourceSets {
    main {
        java.srcDir(generatedSourcesDir)
    }
}

tasks.named('compileJava') {
    dependsOn(generateCustomSources)
}
```

Luồng thực hiện:

```text
generateCustomSources
          |
          v
      compileJava
          |
          v
        classes
          |
          v
          jar
```

Các điểm quan trọng:

- Output được đặt bên dưới `build/`, nơi có thể tái tạo.
- `outputs.dir(...)` khai báo output của generator.
- Generated source directory được thêm vào Java source set.
- `compileJava` phụ thuộc vào generator, nên compiler không chạy trước khi source được tạo.

Trong task thực tế, cần khai báo đầy đủ input của generator như schema, template hoặc cấu hình. Nếu task dùng custom task type, nên khai báo các property bằng `@Input`, `@InputFile`, `@InputDirectory`, `@OutputDirectory` và các kiểu phù hợp.

Với nhiều source set, ví dụ `main` và `test`, cần nối generator vào đúng compile task tương ứng. Không nên chỉ nối `generateTestSources` vào `compileJava` nếu output của nó dành cho `compileTestJava`.

## 8. Gắn tác vụ xử lý resource vào đúng chỗ

Nếu task tạo resource mà ứng dụng cần đóng gói, cần bảo đảm resource được tạo trước khi `processResources` đọc chúng.

Ví dụ cấu hình minh họa:

```groovy
def generatedResourcesDir = layout.buildDirectory.dir(
    'generated/resources/main'
)

def generateBuildProperties = tasks.register('generateBuildProperties') {
    outputs.dir(generatedResourcesDir)

    doLast {
        def propertiesFile = generatedResourcesDir.get()
            .file('build-info.properties')
            .asFile

        propertiesFile.parentFile.mkdirs()
        propertiesFile.text = 'build.source=generated\n'
    }
}

sourceSets {
    main {
        resources.srcDir(generatedResourcesDir)
    }
}

tasks.named('processResources') {
    dependsOn(generateBuildProperties)
}
```

Luồng xử lý:

```text
generateBuildProperties
           |
           v
     processResources
           |
           v
   build/resources/main
           |
           v
          jar
```

Nếu output của task được truyền trực tiếp cho input của một task khác bằng provider, Gradle có thể suy ra dependency từ quan hệ dữ liệu. Dù dùng cách nào, phải bảo đảm generated resource được đăng ký vào source set hoặc input của task xử lý.

## 9. Gắn tác vụ báo cáo sau kiểm thử

Một số công việc cần chạy sau một task cụ thể, chẳng hạn tạo báo cáo bổ sung sau test hoặc thu thập thông tin kết quả. Khi đó có thể dùng `finalizedBy`.

```groovy
def writeAdditionalTestReport = tasks.register('writeAdditionalTestReport') {
    group = 'verification'
    description = 'Writes an additional test report.'

    doLast {
        println 'Writing additional test report'
    }
}

tasks.named('test') {
    finalizedBy(writeAdditionalTestReport)
}
```

Khi task `test` được chọn, finalizer được đưa vào graph và lên lịch sau `test`. Đây là cách phù hợp cho báo cáo hoặc dọn dẹp liên quan trực tiếp tới task kiểm thử.

Nếu báo cáo là một điều kiện bắt buộc để `check` thành công, hãy cân nhắc mô hình task verification riêng và gắn vào `check`. `finalizedBy` có mục đích finalization; nó không thay thế một prerequisite cần hoàn thành trước task chính.

## 10. Dùng plugin callback khi task phụ thuộc vào plugin khác

Một plugin tùy chỉnh có thể được áp dụng trong project trước hoặc sau plugin Java. Nếu plugin cần cấu hình task `check`, `compileJava` hoặc `jar`, không nên giả định task đó đã tồn tại tại thời điểm build script được đọc.

Có thể chờ plugin tương ứng được áp dụng bằng `pluginManager.withPlugin(...)`:

```groovy
pluginManager.withPlugin('java') {
    def verifyMetadata = tasks.register('verifyMetadata') {
        group = 'verification'
        doLast {
            println 'Metadata verified'
        }
    }

    tasks.named('check') {
        dependsOn(verifyMetadata)
    }
}
```

Callback chạy khi plugin `java` được áp dụng. Bên trong callback, có thể đăng ký task và cấu hình task lifecycle do Java plugin cung cấp.

Nếu đang viết build script với:

```groovy
plugins {
    id 'java'
}
```

thì plugin Java được áp dụng trong build script đó. Nhưng với convention plugin hoặc plugin dùng lại trong nhiều project, callback `withPlugin` giúp thể hiện rõ sự phụ thuộc vào plugin và tránh giả định thứ tự áp dụng.

### 10.1. Cấu hình task theo kiểu bằng `withType` và `configureEach`

Khi cần cấu hình nhiều task cùng loại, có thể dùng `withType(...).configureEach(...)`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Đoạn này cấu hình các task biên dịch Java, kể cả task được plugin đăng ký sau đó. `configureEach` hỗ trợ cấu hình lazy, tránh buộc Gradle tạo ngay mọi task chỉ để áp dụng cấu hình.

Không nên dùng `withType` để gắn một generator dành riêng cho `main` vào mọi task compile nếu điều đó làm task test hoặc source set khác chạy generator không cần thiết. Hãy xác định phạm vi source set và task cụ thể.

## 11. Không dùng `afterEvaluate` để thay thế task dependency

Một cách cũ thường gặp là chờ đến cuối configuration phase rồi tìm task và thêm dependency:

```groovy
afterEvaluate {
    tasks.compileJava.dependsOn('generateSources')
}
```

Cách này thường không cần thiết. Nó phụ thuộc vào thời điểm đánh giá project, có thể làm build khó dự đoán và gây vấn đề với cấu hình lazy hoặc configuration cache.

Ưu tiên cấu hình trực tiếp bằng provider:

```groovy
def generateSources = tasks.register('generateSources') {
    doLast {
        println 'Generating sources'
    }
}

tasks.named('compileJava') {
    dependsOn(generateSources)
}
```

Nếu task thuộc plugin được áp dụng có điều kiện, dùng `pluginManager.withPlugin(...)`. Nếu task có thể được đăng ký muộn bởi plugin khác, dùng API provider và callback phù hợp thay vì buộc toàn bộ project phải được evaluate trước.

## 12. Tránh gắn công việc vào sai thời điểm thực thi

Một số API có thể tạo cảm giác thuận tiện nhưng không phù hợp để khai báo dependency:

```groovy
gradle.taskGraph.whenReady {
    // Không nên thêm task dependency ở đây.
}
```

`taskGraph.whenReady` được gọi khi task graph đã được xác định. Đây không phải nơi thích hợp để bổ sung task mới hoặc thay đổi dependency, vì graph cần được hoàn tất trước execution phase.

Tương tự, không nên thực hiện công việc tạo file ngay trong thân build script:

```groovy
// Không nên tạo output trực tiếp trong configuration phase.
file('build/generated/value.txt').text = 'generated'
```

Thay vào đó, đặt hành động tạo file trong task action và khai báo output:

```groovy
tasks.register('generateValue') {
    def outputFile = layout.buildDirectory.file('generated/value.txt')
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.text = 'generated'
    }
}
```

Nhờ đó, file chỉ được tạo khi task được thực thi. Gradle cũng có thể quản lý output theo input/output đã khai báo.

## 13. Chọn lifecycle task hay nối trực tiếp với task cụ thể?

Hai cách tích hợp phục vụ hai mục đích khác nhau.

**Nối với task cụ thể** khi tác vụ cần một đầu vào được tạo ở bước đó. Ví dụ:

```groovy
tasks.named('compileJava') {
    dependsOn(tasks.named('generateSources'))
}
```

Đây là cách thể hiện rằng compiler cần source được sinh.

**Nối với lifecycle task** khi tác vụ là một phần của mục tiêu tổng hợp. Ví dụ:

```groovy
tasks.named('check') {
    dependsOn(tasks.named('verifyModuleMetadata'))
}
```

Đây là cách thể hiện rằng kiểm tra metadata thuộc luồng verification.

Không nên nối mọi task vào `build` để giải quyết các dependency cụ thể. Nếu compiler cần generated source, nối trực tiếp với compile task hoặc input/output của compiler. Nếu một kiểm tra cần chạy khi gọi `check`, nối vào `check`. Cấu trúc này giúp task graph phản ánh đúng quan hệ công việc.

## 14. Maven: gắn goal vào lifecycle phase

Maven dùng mô hình lifecycle và phase rõ ràng hơn. Plugin cung cấp các goal; goal có thể được gắn vào một phase trong `pom.xml`.

Một số phase phổ biến của default lifecycle:

| Phase | Mục đích khái quát |
|---|---|
| `validate` | Kiểm tra dự án và thông tin cần thiết |
| `generate-sources` | Sinh mã nguồn chính |
| `process-sources` | Xử lý mã nguồn trước compile |
| `generate-resources` | Sinh resource |
| `process-resources` | Xử lý và sao chép resource |
| `compile` | Biên dịch mã nguồn chính |
| `test` | Chạy kiểm thử |
| `package` | Đóng gói artifact |
| `verify` | Kiểm tra artifact và các điều kiện xác minh |
| `install` | Cài artifact vào local repository |
| `deploy` | Đưa artifact lên repository đích |

Ví dụ cấu hình một plugin goal chạy ở phase `generate-sources`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.example</groupId>
      <artifactId>example-codegen-maven-plugin</artifactId>
      <version>1.0.0</version>
      <executions>
        <execution>
          <id>generate-api-sources</id>
          <phase>generate-sources</phase>
          <goals>
            <goal>generate</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Tên group, artifact, version và goal trên chỉ minh họa cấu trúc cấu hình; phải thay bằng plugin thực tế có goal tương ứng. Khi chạy:

```bash
mvn compile
```

Maven đi qua các phase trước `compile`, vì vậy goal được gắn ở `generate-sources` sẽ chạy trước compile.

Trong Gradle, không nên tìm một tên phase tương ứng rồi gắn task vào đó. Hãy mô hình hóa cùng yêu cầu bằng task graph, ví dụ `compileJava.dependsOn(generateSources)` và đăng ký output vào source set.

## 15. So sánh cách tích hợp task trong Gradle và Maven

| Nhu cầu | Gradle | Maven |
|---|---|---|
| Sinh mã trước compile | Dependency của `compileJava` hoặc task compile tương ứng | Gắn goal vào `generate-sources` |
| Sinh resource trước khi đóng gói | Nối generator với `processResources` và source set | Gắn goal vào `generate-resources` hoặc `process-resources` theo mục đích |
| Kiểm tra chất lượng | Gắn task vào `check` | Gắn goal vào phase phù hợp như `verify` |
| Tạo artifact bổ sung | Gắn task vào `assemble` hoặc mô hình artifact phù hợp | Gắn goal vào `package` hoặc phase phù hợp |
| Tạo báo cáo sau task | Có thể dùng `finalizedBy` hoặc task verification riêng | Plugin thường gắn goal vào phase sau task cần báo cáo |
| Chọn thứ tự giữa các công việc | Dependency và ordering trong task graph | Thứ tự phase và thứ tự plugin execution |

Hai build tool có cùng mục tiêu điều phối công việc, nhưng mô hình cấu hình khác nhau. Không nên chuyển nguyên cách nghĩ về Maven phase sang Gradle mà không xác định lại dependency và output.

## 16. Quan sát tác vụ được gắn vào đâu

### 16.1. Liệt kê task

```bash
./gradlew tasks --all
```

Lệnh này giúp xác định task có được đăng ký hay không và xem nhóm task. `group` chỉ ảnh hưởng cách hiển thị; để biết task có chạy cùng `build`, `check` hay `assemble`, cần xem dependency hoặc task graph.

### 16.2. Xem task graph bằng `--dry-run`

```bash
./gradlew check --dry-run
./gradlew assemble --dry-run
./gradlew build --dry-run
```

Có thể so sánh ba graph để xem task tùy chỉnh xuất hiện ở luồng nào. `--dry-run` hiển thị task dự kiến mà không chạy task action.

### 16.3. Xem log thực thi

```bash
./gradlew build --info
```

Log giúp nhận biết task được thực thi, bỏ qua hoặc đánh dấu `UP-TO-DATE`. Nếu task xuất hiện trong graph nhưng không thực hiện action vì output còn hợp lệ, đó có thể là hành vi bình thường của incremental build.

### 16.4. Tìm nơi khai báo dependency

Khi task không chạy như mong đợi, tìm các cấu hình:

```groovy
dependsOn(...)
mustRunAfter(...)
shouldRunAfter(...)
finalizedBy(...)
```

Đồng thời kiểm tra các kết nối input/output provider, plugin callback và task registration. Một plugin có thể tự nối task mà không có dòng `dependsOn` trong build script của project.

## 17. Những lỗi thường gặp khi tích hợp task

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Task tùy chỉnh không chạy khi gọi `build` | Task chỉ được đăng ký nhưng chưa nối vào graph | Nối vào `check`, `assemble`, `build` hoặc task cụ thể phù hợp |
| Generator chạy sau compiler | Thiếu dependency hoặc output/input connection | Nối generator vào compile task hoặc truyền output provider |
| Task chạy trong mọi build dù không cần | Đã gắn vào lifecycle task quá rộng hoặc thực hiện việc ngay trong configuration phase | Chọn điểm tích hợp hẹp hơn và chuyển logic vào task action |
| Task không tìm thấy `check` hoặc `compileJava` | Plugin Java chưa được áp dụng hoặc task path sai | Dùng `pluginManager.withPlugin('java')` và `tasks.named(...)` |
| Task tạo output nhưng Gradle không nhận ra thay đổi | Thiếu khai báo input/output | Dùng property và annotation phù hợp |
| Dùng `afterEvaluate` để thêm dependency gây khó đoán | Cấu hình quá muộn và phụ thuộc thứ tự evaluate | Dùng provider, `tasks.named`, `configureEach` hoặc plugin callback |
| `taskGraph.whenReady` không phù hợp để nối task | Graph đã được xác định | Khai báo dependency trong configuration phase |
| Publish/deploy chạy khi chỉ muốn build | Task side effect bị nối vào `build` | Để task phát hành riêng, yêu cầu gọi rõ ràng |
| Task chạy hai lần hoặc tạo output trùng | Nhiều task cùng chịu trách nhiệm một output hoặc dependency không được mô hình hóa đúng | Tách output và xác định một chủ sở hữu cho mỗi công việc |

## 18. Quy trình chọn đúng giai đoạn tích hợp

Khi viết một task tùy chỉnh, có thể lần theo các câu hỏi sau:

1. **Task tạo ra gì hoặc tiêu thụ gì?** Xác định file, directory, artifact, dữ liệu hoặc điều kiện mà task sử dụng.
2. **Task cần chạy trước công việc nào?** Nếu compiler cần source, nối với compile task; nếu resource processor cần file, nối với `processResources`.
3. **Task thuộc luồng tổng hợp nào?** Kiểm tra, tạo artifact hay build tổng thể tương ứng với `check`, `assemble` hoặc `build`.
4. **Task cần chạy sau một task cụ thể?** Nếu là báo cáo hoặc cleanup, cân nhắc `finalizedBy`; nếu chỉ cần thứ tự khi cả hai đã được chọn, dùng ordering constraint.
5. **Plugin cung cấp task lifecycle đã được áp dụng chưa?** Dùng `pluginManager.withPlugin` nếu plugin có thể được áp dụng có điều kiện hoặc thứ tự không cố định.
6. **Input/output đã khai báo chưa?** Đây là cơ sở cho thứ tự suy ra, up-to-date check và cache.
7. **Task có side effect bên ngoài không?** Publish, deploy hoặc gửi thông báo nên được gọi có chủ đích, không nên tự động chạy trong mọi `build`.
8. **Task graph có đúng không?** Dùng `--dry-run` và log để xác nhận task xuất hiện tại điểm mong muốn.

## 19. Kết luận

Trong Gradle, gắn task tùy chỉnh đúng giai đoạn nghĩa là đặt nó vào đúng phần của task graph. Hãy nối tác vụ sinh mã với compile task cần mã đó, tác vụ xử lý resource với `processResources`, tác vụ kiểm tra với `check`, và tác vụ tạo artifact với `assemble` khi phù hợp. Dùng `finalizedBy` cho công việc cần chạy sau một task cụ thể và giữ các thao tác phát hành/triển khai thành task được gọi chủ động.

Gradle có các giai đoạn Initialization, Configuration và Execution, nhưng không dùng phase binding theo cách Maven làm. Hãy đăng ký task lazy, khai báo input/output và dependency rõ ràng, dùng plugin callback khi cần, rồi kiểm tra task graph. Một điểm tích hợp đúng giúp build thực hiện công việc đúng lúc, tránh chạy thừa và giữ khả năng incremental, cache cũng như chạy song song.
