# Timestamp, thứ tự tệp và đường dẫn máy ảnh hưởng đến artifact

Một dự án Java có thể build thành công nhiều lần nhưng mỗi lần tạo ra một file JAR có checksum khác nhau. Mã nguồn không đổi, dependency không đổi, lệnh build giống nhau, nhưng archive vẫn khác vì timestamp của entry, thứ tự file, thông tin môi trường hoặc đường dẫn trên máy đã lọt vào sản phẩm.

Đây là vấn đề của **tính tái lập (reproducibility)**. Một build có tính tái lập cần tạo ra cùng kết quả khi các đầu vào được kiểm soát giống nhau. Với reproducible build ở mức byte-for-byte, hai lần build phải tạo ra artifact có nội dung byte giống hệt nhau, thường được xác nhận bằng checksum.

Timestamp, thứ tự file và đường dẫn máy là ba nguồn sai khác dễ bị bỏ qua:

- Archive có thể lưu thời gian sửa đổi của từng entry. Hai lần đóng gói ở hai thời điểm khác nhau sẽ có byte khác nhau dù nội dung file không đổi.
- Các file có thể được thêm vào archive theo thứ tự duyệt thư mục hoặc thứ tự collection không ổn định.
- Đường dẫn tuyệt đối, username, hostname hoặc thư mục workspace có thể được ghi vào manifest, resource sinh tự động, debug metadata hoặc file cấu hình.

Những sai khác này làm khó so sánh artifact, cache, xác minh chữ ký, điều tra sự cố và chứng minh artifact được tạo từ source đã review. Bài học này tập trung vào cách nhận diện và kiểm soát chúng trong quy trình build Java.

## 1. Reproducible build là gì?

Reproducible build là quá trình tạo artifact có thể tái tạo được từ cùng một tập đầu vào đã xác định. Tập đầu vào thường gồm:

- Source code và resource trong revision cụ thể.
- Build script, plugin và build tool version.
- JDK/compiler/toolchain version.
- Dependency và metadata được phân giải.
- Cấu hình build được truyền vào.
- Các công cụ ngoài, generator và môi trường thực thi có ảnh hưởng đến output.

Nếu tất cả đầu vào có thể kiểm soát và các bước build không phụ thuộc trạng thái ngẫu nhiên của máy, artifact có thể được tạo lặp lại.

### 1.1. Reproducible khác với build thành công hai lần

Hai lần build cùng exit code `0` chỉ cho biết cả hai lần đều hoàn tất. Chúng chưa chứng minh tạo cùng artifact.

Ví dụ:

```text
Build lần 1: application.jar  SHA-256 = a1b2...
Build lần 2: application.jar  SHA-256 = c3d4...
```

Nếu checksum khác, cần xác định phần nào trong archive thay đổi. Có thể chỉ là timestamp hoặc thứ tự ZIP entry, nhưng cũng có thể là class/resource thật sự khác nội dung.

### 1.2. Hai mức kiểm tra

| Mức | Điều cần xác nhận | Ví dụ |
|---|---|---|
| Functional repeatability | Artifact từ các lần build có hành vi tương đương theo test | Cùng endpoint trả cùng kết quả với cùng cấu hình/test data |
| Byte-for-byte reproducibility | Artifact có byte giống hệt nhau | SHA-256 của hai JAR bằng nhau |

Một dự án có thể cần cả hai. Functional test không phát hiện mọi sai khác nhị phân; checksum giống nhau cũng không chứng minh ứng dụng có hành vi đúng. Hai loại bằng chứng bổ sung cho nhau.

## 2. Timestamp bên trong archive

JAR và WAR dựa trên định dạng ZIP. Mỗi entry trong archive có metadata, trong đó có thể bao gồm thời gian sửa đổi. Nếu công cụ đóng gói ghi timestamp thực tế của file nguồn vào archive, cùng một file được đóng gói vào hai thời điểm khác nhau có thể tạo ra hai archive khác nhau.

Ví dụ:

```text
Lần build A:
  com/example/Application.class  2026-11-13 08:00:00

Lần build B:
  com/example/Application.class  2026-11-13 08:15:00
```

Bytecode có thể giống nhau, nhưng timestamp entry khác nhau. Vì metadata nằm trong file ZIP, toàn bộ JAR có thể có checksum khác.

### 2.1. Timestamp của file khác timestamp của archive

Cần phân biệt:

- **Entry timestamp:** thời gian được lưu cho từng file bên trong JAR/ZIP.
- **Filesystem timestamp:** thời gian sửa đổi của file trên ổ đĩa trước khi đóng gói.
- **Build timestamp:** thời điểm tiến trình build bắt đầu hoặc hoàn tất.
- **Timestamp được nhúng vào nội dung:** chuỗi thời gian được ghi vào properties, manifest, generated source hoặc resource.

Chỉ chuẩn hóa timestamp của archive chưa đủ nếu build còn ghi thời gian hiện tại vào nội dung file.

### 2.2. Độ phân giải và timezone

Định dạng ZIP truyền thống có giới hạn biểu diễn thời gian, thường dùng timestamp DOS với độ phân giải hai giây và không lưu timezone như một instant UTC đầy đủ. Công cụ đóng gói có thể chuẩn hóa, chuyển đổi hoặc lưu thêm metadata tùy định dạng/implementation.

Do đó, cùng một instant có thể được biểu diễn khác nhau nếu công cụ xử lý timezone khác nhau. Cần dùng cùng toolchain và cấu hình archive ổn định; không nên dựa vào timezone mặc định của máy.

### 2.3. Chuẩn hóa timestamp

Một cách phổ biến là đặt timestamp của các entry về một giá trị cố định hoặc giá trị xác định từ source revision. Khi đầu vào không đổi, metadata archive cũng không đổi.

Không nên dùng thời điểm build hiện tại làm timestamp của mọi entry nếu mục tiêu là byte-for-byte reproducibility giữa các lần build. Nếu cần biết thời điểm pipeline chạy, hãy ghi nhận trong CI metadata/log hoặc provenance bên ngoài artifact thay vì nhúng một giá trị luôn thay đổi vào JAR.

## 3. Thứ tự file trong archive

Một JAR là archive chứa nhiều entry. Hai archive có cùng tập file và cùng nội dung từng file vẫn có thể khác byte nếu thứ tự entry khác nhau.

Ví dụ:

```text
Archive A:
  META-INF/MANIFEST.MF
  com/example/Application.class
  com/example/OrderService.class
  application.properties

Archive B:
  META-INF/MANIFEST.MF
  application.properties
  com/example/OrderService.class
  com/example/Application.class
```

Nếu công cụ đóng gói duyệt file theo thứ tự filesystem hoặc collection không được sắp xếp, thứ tự có thể thay đổi giữa máy hoặc giữa lần build. ZIP central directory và dữ liệu entry được ghi theo thứ tự đó, nên checksum archive khác nhau.

### 3.1. Vì sao thứ tự duyệt thư mục có thể không ổn định?

Thứ tự trả về từ filesystem, API duyệt thư mục hoặc collection có thể phụ thuộc hệ điều hành, filesystem, cách tạo file và implementation của công cụ. Không nên giả định `listFiles()` hoặc một file tree luôn trả kết quả theo thứ tự alphabet.

Một task custom có thể vô tình tạo archive bằng cách duyệt danh sách file không sắp xếp:

```groovy
def files = fileTree('src/main/resources').files

tasks.register('writeResourceIndex') {
    doLast {
        // Nếu thứ tự files không ổn định, nội dung index có thể khác.
        file('build/resource-index.txt').text = files.collect { it.name }.join('\n')
    }
}
```

Nếu thứ tự có ý nghĩa đối với output, hãy sắp xếp tường minh:

```groovy
def orderedFiles = fileTree('src/main/resources').files.sort {
    it.relativePath
}
```

Với archive task của Gradle, có property riêng để yêu cầu thứ tự entry có thể tái lập. Với custom task, phải tự xác định thứ tự và cách chuẩn hóa nội dung.

### 3.2. Thứ tự file có thể ảnh hưởng nội dung được sinh

Không chỉ archive bị khác. Nếu một generator duyệt danh sách file rồi ghi danh sách vào resource, thứ tự không ổn định sẽ làm chính nội dung resource thay đổi.

Ví dụ generator tạo registry từ nhiều file cấu hình:

```groovy
def configFiles = fileTree('config/modules').matching {
    include '*.yml'
}.files.sort { it.name }

tasks.register('generateModuleRegistry') {
    inputs.files(configFiles)
    outputs.file(layout.buildDirectory.file('generated/module-registry.txt'))

    doLast {
        def output = layout.buildDirectory
            .file('generated/module-registry.txt').get().asFile
        output.parentFile.mkdirs()
        output.text = configFiles.collect { it.name }.join('\n') + '\n'
    }
}
```

Việc sắp xếp giúp generator tạo cùng nội dung khi tập file không đổi. Cần dùng đường dẫn tương đối ổn định thay vì đường dẫn tuyệt đối của máy.

## 4. Đường dẫn tuyệt đối và thông tin máy có thể lọt vào artifact

Đường dẫn workspace trên mỗi máy thường khác nhau:

```text
Máy A: C:\work\orders\project
Máy B: D:\agents\job-42\project
Linux CI: /home/runner/work/project
```

Nếu build ghi một trong các đường dẫn này vào artifact, hai lần build từ cùng source có thể tạo nội dung khác nhau. Artifact còn có thể tiết lộ username, cấu trúc thư mục nội bộ hoặc tên máy.

Các vị trí dễ bị ảnh hưởng:

- Generated `build-info.properties` hoặc resource tương tự.
- Manifest entry do plugin tự thêm.
- File JSON/YAML chứa build metadata.
- Generated source có ghi tên thư mục đầu vào.
- Script khởi chạy hoặc cấu hình đóng gói.
- Native library/debug symbols được tạo bởi công cụ ngoài.
- Report hoặc file index vô tình được đưa vào archive.

### 4.1. Không nhúng `user.dir` hoặc `user.home` vào sản phẩm

Ví dụ không nên làm:

```groovy
tasks.register('generateBuildInfo') {
    outputs.file(layout.buildDirectory.file('generated/build-info.properties'))

    doLast {
        def output = layout.buildDirectory
            .file('generated/build-info.properties').get().asFile
        output.parentFile.mkdirs()
        output.text = "workspace=${project.projectDir.absolutePath}\n"
    }
}
```

Giá trị `project.projectDir.absolutePath` phụ thuộc nơi checkout. Hai máy build khác nhau sẽ ghi hai chuỗi khác nhau vào resource.

Nếu chỉ cần định danh module, hãy ghi một giá trị logic ổn định:

```groovy
tasks.register('generateBuildInfo') {
    outputs.file(layout.buildDirectory.file('generated/build-info.properties'))

    doLast {
        def output = layout.buildDirectory
            .file('generated/build-info.properties').get().asFile
        output.parentFile.mkdirs()
        output.text = "module=${project.name}\nversion=${project.version}\n"
    }
}
```

Tên module và version có thể ổn định nếu chúng là đầu vào được quản lý của dự án. Không ghi đường dẫn checkout, home directory hoặc username trừ khi sản phẩm có yêu cầu rõ ràng và chấp nhận việc artifact không còn byte-for-byte reproducible.

### 4.2. Đường dẫn nguồn trong debug metadata

Java class file có thể chứa thông tin debug như tên source file, line number và local variable table. Những thuộc tính này hữu ích cho debugger và stack trace.

Thông thường, thuộc tính `SourceFile` trong class file lưu tên file nguồn, không nhất thiết lưu đường dẫn tuyệt đối đầy đủ. Tuy nhiên, compiler khác, ngôn ngữ JVM khác, annotation processor hoặc generator có thể ghi thêm thông tin đường dẫn vào metadata riêng. Native code và debug symbol của công cụ ngoài có thể lưu đường dẫn build đầy đủ.

Vì vậy, không nên mặc định mọi class file Java đều chứa absolute source path, nhưng cũng không nên giả định toàn bộ artifact không thể tiết lộ đường dẫn. Khi có yêu cầu bảo mật hoặc reproducibility nghiêm ngặt, hãy kiểm tra nội dung class/resource/debug metadata thực tế.

Có thể xem thuộc tính class bằng:

```bash
javap -v -classpath build/classes/java/main com.example.Application
```

Tìm `SourceFile`, `LineNumberTable`, `LocalVariableTable` và các thuộc tính mở rộng. Với artifact chứa native binary, dùng công cụ tương ứng của nền tảng để kiểm tra debug path.

## 5. Những nguồn nondeterminism khác thường đi cùng timestamp và path

Timestamp, thứ tự file và đường dẫn máy thường chỉ là một phần của vấn đề. Các nguồn sau cũng có thể làm artifact thay đổi:

| Nguồn | Ví dụ | Cách kiểm soát |
|---|---|---|
| Build timestamp | Ghi `2026-11-13T08:00:00Z` vào resource | Loại khỏi artifact hoặc dùng giá trị cố định/đến từ revision |
| Hostname/username | Ghi `builder-17`, `alice` vào manifest | Không nhúng thông tin máy vào artifact |
| Random value | UUID tạo mới mỗi lần build | Dùng seed xác định nếu thực sự cần dữ liệu giả lập |
| Locale/timezone | Format ngày hoặc số theo máy | Đặt locale/timezone tường minh |
| Encoding/line ending | Resource sinh trên Windows khác Linux | Dùng UTF-8 và LF theo quy ước repository |
| Dependency động | `1.+`, SNAPSHOT hoặc changing module | Dùng version cố định, locking và verification |
| Toolchain khác nhau | JDK/plugin version khác | Pin wrapper, plugin và JDK toolchain |
| Compression khác nhau | Khác compressor/version/level | Dùng cấu hình công cụ ổn định |
| Permission/mode | Entry ZIP mang mode khác | Chuẩn hóa file mode và quy trình đóng gói |
| Generator không ổn định | Sinh file theo thứ tự map không xác định | Sắp xếp input và chuẩn hóa output |
| Git state | Ghi branch, dirty flag hoặc commit thay đổi | Kiểm soát revision và cách lấy metadata |

Một build chỉ có thể tái lập nếu các yếu tố ảnh hưởng đến output đều được xác định hoặc loại bỏ.

## 6. Chuẩn hóa archive trong Gradle

Gradle archive tasks như `Jar`, `War`, `Zip` và `Tar` kế thừa các property từ `AbstractArchiveTask`.

Hai property quan trọng cho reproducibility:

- `preserveFileTimestamps`: có giữ timestamp filesystem của từng file trong archive hay không.
- `reproducibleFileOrder`: có sắp xếp thứ tự file trong archive theo cách tái lập hay không.

Có thể cấu hình chung:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Hoặc cấu hình một task cụ thể:

```groovy
tasks.named('jar') {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Ý nghĩa:

- `preserveFileTimestamps = false` yêu cầu Gradle không giữ timestamp gốc của từng file như metadata archive.
- `reproducibleFileOrder = true` yêu cầu thứ tự entry ổn định thay vì phụ thuộc thứ tự duyệt nguồn.

Đây là các thiết lập quan trọng cho JAR/ZIP reproducible. Tùy phiên bản Gradle, một số mặc định có thể đã được thiết lập theo hướng tái lập; khai báo tường minh trong build logic dùng chung giúp thể hiện ý định và tránh phụ thuộc vào mặc định khác nhau giữa các toolchain.

### 6.1. Kotlin DSL

Với `build.gradle.kts`:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Kotlin DSL dùng cú pháp property setter theo kiểu Kotlin cho các thuộc tính boolean của Gradle.

### 6.2. Tên archive ổn định

Ngoài timestamp và thứ tự entry, cần bảo đảm tên artifact ổn định:

```groovy
tasks.named('jar') {
    archiveBaseName.set('order-service')
    archiveVersion.set(project.version.toString())
    archiveClassifier.set('')
    archiveExtension.set('jar')
}
```

Không dùng thời điểm hiện tại hoặc đường dẫn workspace để tạo `archiveFileName`. Nếu build number cần thiết cho mục đích truy vết, hãy xác định nó là input có chủ đích và hiểu rằng artifact từ hai build number khác nhau sẽ khác nhau.

### 6.3. Custom task phải tự ổn định output

Các property archive chỉ kiểm soát archive task của Gradle. Chúng không tự chuẩn hóa nội dung do custom task tạo ra.

Ví dụ custom task ghi danh sách file phải:

- Sắp xếp input trước khi ghi.
- Dùng relative path chuẩn hóa.
- Chọn encoding cố định.
- Dùng line ending cố định.
- Không ghi timestamp hoặc hostname nếu không cần.
- Khai báo input/output để Gradle theo dõi chính xác.

Nếu custom task tạo ZIP riêng bằng thư viện Java hoặc công cụ ngoài, chính task đó phải đặt timestamp entry, thứ tự entry và metadata theo quy tắc ổn định.

## 7. Chuẩn hóa archive trong Maven

Maven Archiver và các plugin đóng gói hỗ trợ thuộc tính `project.build.outputTimestamp` để tạo archive với timestamp đầu ra cố định. Thuộc tính này được nhiều plugin Maven hiện đại sử dụng.

Ví dụ trong `pom.xml`:

```xml
<properties>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Giá trị ở ví dụ là một timestamp cố định để minh họa. Dự án có thể chọn một giá trị xác định theo chính sách reproducible build, chẳng hạn timestamp của source revision nếu pipeline cung cấp nó một cách ổn định. Không dùng thời điểm hiện tại nếu muốn hai lần build cùng revision tạo cùng archive.

Với Maven JAR Plugin:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
    </plugin>
  </plugins>
</build>
```

Plugin sử dụng Maven Archiver để tạo JAR và đọc `project.build.outputTimestamp` khi phiên bản plugin/archiver hỗ trợ. Các plugin tạo WAR, source archive hoặc distribution cũng cần được kiểm tra riêng; không nên cho rằng một property chắc chắn điều khiển mọi plugin bên thứ ba.

### 7.1. Chọn timestamp từ source revision

Một số quy trình lấy timestamp commit của revision đang build để dùng làm `outputTimestamp`. Nếu cùng commit được build lại, giá trị vẫn giống nhau.

Điều kiện cần bảo đảm:

- CI lấy timestamp từ commit cụ thể, không lấy thời gian job.
- Không thay đổi timestamp khi checkout cùng commit.
- Cùng timezone/định dạng khi truyền cho Maven.
- Build không nhúng một timestamp khác từ plugin hoặc generated resource.

Nếu repository cho phép commit amend/rebase, commit timestamp có thể thay đổi cùng revision mới. Điều đó phù hợp vì source revision cũng đã thay đổi.

### 7.2. Pin plugin version

Plugin đóng gói có thể thay đổi cách ghi metadata, thứ tự entry hoặc compression giữa các phiên bản. Vì vậy, Maven build nên khai báo version plugin rõ ràng thay vì phụ thuộc version ngầm từ môi trường hoặc super POM.

Ví dụ trên đã pin `maven-jar-plugin` version. Các plugin khác như WAR, Assembly, Shade hoặc plugin tạo tài liệu cũng cần version được quản lý trong `pluginManagement` hoặc cấu hình tương ứng.

## 8. Đường dẫn máy trong generated resource và build metadata

Một số plugin sinh file thông tin build như version, commit, thời gian, branch hoặc trạng thái repository. Những dữ liệu này hữu ích cho chẩn đoán, nhưng nếu chứa giá trị thay đổi theo máy thì artifact không còn reproducible.

Ví dụ resource không ổn định:

```properties
build.version=2.4.0
build.time=2026-11-13T08:45:00Z
build.user=alice
build.host=ci-agent-12
build.directory=/home/runner/work/order-service
```

Trong khi đó, metadata ổn định hơn có thể là:

```properties
build.version=2.4.0
build.commit=7f1a2b3c...
```

Commit hash có thể xác định source revision; version và commit là dữ liệu đầu vào có chủ đích. Nếu yêu cầu provenance cần thời gian build, có thể lưu thời gian trong attestation hoặc metadata CI bên ngoài artifact, hoặc chấp nhận rõ ràng rằng artifact không byte-for-byte reproducible vì thời gian là một phần output.

### 8.1. Không dùng đường dẫn tuyệt đối trong manifest Class-Path

Manifest `Class-Path` của JAR có thể tham chiếu dependency tương đối với vị trí JAR. Không nên ghi đường dẫn tuyệt đối của máy build:

```text
Class-Path: /home/runner/work/app/lib/dependency.jar
```

Đường dẫn này không hoạt động trên máy khác và làm artifact phụ thuộc workspace. Dùng URL/đường dẫn tương đối theo cấu trúc distribution, ví dụ:

```text
Class-Path: lib/dependency.jar
```

Đồng thời bảo đảm dependency được phân phối đúng vị trí.

### 8.2. Không ghi đường dẫn build vào generated source

Code generator có thể tạo source chứa đường dẫn template hoặc workspace để phục vụ debug. Nếu đường dẫn thay đổi theo máy, bytecode sau compile cũng thay đổi.

Hãy truyền một root logic hoặc relative path cho generator. Nếu cần thông tin nguồn, ghi relative path từ project root hoặc source revision, không ghi đường dẫn tuyệt đối của checkout.

## 9. Locale, timezone, encoding và line ending

Hai máy có thể tạo output khác nhau dù source và dependency giống nhau nếu chương trình build sử dụng locale hoặc timezone mặc định.

Ví dụ format ngày:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd MMMM yyyy");
String text = formatter.format(LocalDate.of(2026, 11, 13));
```

Kết quả có thể khác theo locale mặc định của JVM. Nếu output phải ổn định, chỉ định locale:

```java
DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("uuuu-MM-dd", Locale.ROOT);
```

Với thời điểm tuyệt đối, dùng timezone tường minh như UTC thay vì timezone mặc định của máy.

### 9.1. Encoding

Khi ghi text output, chỉ định UTF-8 thay vì dựa vào charset mặc định của hệ điều hành/JVM:

```java
Files.writeString(
    outputPath,
    content,
    StandardCharsets.UTF_8
);
```

Nếu generator dùng `File.text` hoặc API phụ thuộc charset mặc định, cần kiểm tra cấu hình và phiên bản runtime. Với build reproducible, encoding phải là một phần của hợp đồng input.

### 9.2. Line ending

Windows thường dùng CRLF, Linux/macOS thường dùng LF. Nếu resource được tạo bằng `System.lineSeparator()` hoặc công cụ dùng line ending của host, cùng nội dung logic có thể có byte khác nhau.

Nếu output cần chuẩn hóa, dùng LF tường minh và cấu hình `.gitattributes` cho file text trong repository. Không nên chuyển mọi file binary hoặc file có định dạng riêng bằng quy tắc line ending.

## 10. Thứ tự collection, map và dữ liệu generator

Build logic có thể lặp qua `Map`, `Set`, filesystem listing hoặc kết quả API. Nếu thứ tự iteration không được đảm bảo, output sinh ra có thể thay đổi.

Ví dụ không nên phụ thuộc thứ tự map:

```groovy
def settings = [
    database: 'enabled',
    cache: 'enabled',
    metrics: 'disabled'
]

def generated = settings.collect { key, value ->
    "${key}=${value}"
}.join('\n')
```

Nếu thứ tự là một phần của output contract, sắp xếp key:

```groovy
def generated = settings.keySet().sort().collect { key ->
    "${key}=${settings[key]}"
}.join('\n') + '\n'
```

Tương tự, khi lấy kết quả từ API hoặc database, cần sắp xếp theo khóa ổn định trước khi ghi vào artifact. Không dựa vào thứ tự tình cờ của response.

## 11. Nondeterminism từ generated metadata và annotation processor

Annotation processor, code generator và plugin có thể ghi thông tin build vào source hoặc resource. Những nguồn cần kiểm tra:

- Build time hoặc thời gian sinh file.
- Hostname và username.
- Absolute source path.
- Thứ tự phần tử từ filesystem hoặc collection.
- Random ID hoặc UUID.
- Locale/timezone mặc định.
- Version dependency được chọn động.
- Thứ tự đăng ký processor/plugin.

Một generator tốt nên nhận input rõ ràng, tạo output xác định và khai báo input/output với build tool. Nếu generator cần thời gian, seed hoặc environment variable, hãy khai báo đó là input có chủ đích và quyết định xem giá trị có nên ảnh hưởng đến artifact hay không.

Nếu output chỉ cần thông tin revision, hãy truyền commit hash hoặc version đã xác định từ CI. Tránh để generator tự chạy `date`, đọc `hostname` hoặc lấy `user.dir` mà không có yêu cầu rõ ràng.

## 12. Kiểm soát build environment

Ngay cả khi archive task đã chuẩn hóa timestamp và file order, toolchain khác nhau vẫn có thể tạo byte khác nhau.

Nên kiểm soát:

- Gradle Wrapper/Maven Wrapper version.
- JDK vendor và version khi có yêu cầu reproducibility nghiêm ngặt.
- Compiler options và encoding.
- Plugin version.
- Dependency version và repository source.
- Locale, timezone và environment variable ảnh hưởng output.
- Công cụ ngoài như protoc, Node, native compiler hoặc asset bundler.
- Container image/build environment khi cần cùng môi trường giữa các lần build.

Với Gradle Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Toolchain cố định language version, nhưng nếu yêu cầu byte-for-byte ở nhiều môi trường, cần kiểm soát thêm vendor/implementation và cách JDK được phân phối theo chính sách dự án.

Với Maven Compiler Plugin, khai báo `release` phù hợp và pin plugin version. Chỉ đặt `source`/`target` không nhất thiết cố định toàn bộ hành vi compiler hoặc JDK đang chạy.

## 13. So sánh artifact bằng checksum

Sau khi tạo hai artifact, dùng SHA-256 để so sánh.

Linux:

```bash
sha256sum build-a/libs/application.jar build-b/libs/application.jar
```

macOS:

```bash
shasum -a 256 build-a/libs/application.jar build-b/libs/application.jar
```

Windows PowerShell:

```powershell
Get-FileHash .\build-a\libs\application.jar -Algorithm SHA256
Get-FileHash .\build-b\libs\application.jar -Algorithm SHA256
```

Nếu hai hash giống nhau, hai file có cùng nội dung byte theo xác suất va chạm cực nhỏ của SHA-256. Nếu khác, tiếp tục phân tích thay vì kết luận ngay rằng source đã thay đổi.

### 13.1. So sánh danh sách entry

Liệt kê archive:

```bash
jar tf build-a/libs/application.jar > entries-a.txt
jar tf build-b/libs/application.jar > entries-b.txt
diff -u entries-a.txt entries-b.txt
```

Nếu danh sách entry khác thứ tự, có thể vấn đề nằm ở archive ordering. Nếu thiếu/thừa entry, cần tìm task hoặc input tạo ra khác biệt.

### 13.2. So sánh metadata ZIP

Có thể dùng `zipinfo -v` hoặc công cụ ZIP tương ứng để xem timestamp, compression method và metadata entry. Khi nghi ngờ timestamp, kiểm tra thời gian của cùng entry ở hai archive.

Ví dụ:

```bash
zipinfo -v build-a/libs/application.jar
zipinfo -v build-b/libs/application.jar
```

### 13.3. So sánh nội dung đã giải nén

Giải nén hai archive vào hai thư mục riêng, rồi so sánh file theo relative path:

```bash
mkdir extracted-a extracted-b
unzip -q build-a/libs/application.jar -d extracted-a
unzip -q build-b/libs/application.jar -d extracted-b
diff -ru extracted-a extracted-b
```

Nếu nội dung giải nén giống nhau nhưng checksum JAR khác, nguyên nhân có thể nằm ở metadata archive, thứ tự entry, compression hoặc metadata ZIP khác. Nếu nội dung khác, tiếp tục xác định file nào thay đổi.

## 14. Quy trình kiểm tra reproducibility trong hai workspace sạch

Để kiểm tra đường dẫn máy có ảnh hưởng không, nên build cùng commit trong hai thư mục checkout khác nhau.

Ví dụ:

```text
Workspace A: /tmp/build-a/project
Workspace B: /tmp/build-b/project
```

Quy trình:

1. Checkout cùng commit vào hai workspace.
2. Dùng cùng Gradle/Maven Wrapper và cùng JDK/toolchain.
3. Dùng cùng dependency lock/verification metadata.
4. Xóa output cũ hoặc dùng workspace mới.
5. Tắt cache nếu mục tiêu là kiểm tra quá trình tạo output độc lập.
6. Build cùng task và cùng tham số.
7. So sánh checksum artifact.
8. Nếu khác, so sánh entry list, metadata và nội dung giải nén.
9. Kiểm tra generated resource, manifest và debug metadata để tìm đường dẫn/time.

Không nên dùng hai workspace có source hoặc dependency state khác nhau rồi kết luận rằng build không reproducible. Trước hết cần xác nhận đầu vào tương đương.

### 14.1. Chạy lại task thay vì tái sử dụng output

Với Gradle, có thể dùng:

```bash
./gradlew clean build --no-build-cache --rerun-tasks
```

`clean` loại output project cũ, `--no-build-cache` không lấy output từ build cache, và `--rerun-tasks` yêu cầu thực thi lại task. Các tùy chọn này hữu ích khi muốn kiểm tra khả năng tạo lại artifact, nhưng có thể làm build lâu hơn.

Với Maven:

```bash
mvn clean verify
```

Maven không có build cache task tương đương mặc định của Gradle theo cùng mô hình. Vẫn cần kiểm soát dependency cache, plugin version và đầu vào ngoài.

### 14.2. Kiểm tra trên máy khác hoặc container

Build trong container được pin bằng image digest có thể giúp kiểm soát JDK, OS packages và công cụ ngoài. Tuy nhiên, container không tự bảo đảm reproducibility nếu build vẫn nhúng timestamp, đường dẫn mount, random value hoặc dependency động.

Để kiểm tra ảnh hưởng của host path, mount cùng source vào các vị trí khác nhau hoặc build trong hai checkout path khác nhau. Nếu artifact thay đổi, tìm các thành phần đã ghi absolute path hoặc thông tin môi trường.

## 15. Đọc và loại bỏ nguồn sai khác trong JAR

Khi checksum khác, hãy phân tích theo thứ tự:

1. **Entry list:** có cùng tên và số lượng file không?
2. **Entry order:** cùng file nhưng khác thứ tự không?
3. **Timestamp:** timestamp của các entry có khác không?
4. **Compression:** cùng nội dung nhưng compression method/level khác không?
5. **Manifest:** có build time, Created-By hoặc metadata thay đổi không?
6. **Resource:** có generated properties/JSON/YAML chứa host/path/time không?
7. **Class file:** bytecode, debug metadata hoặc compiler output có khác không?
8. **Dependency:** có version hoặc artifact khác được phân giải không?
9. **Toolchain:** JDK, plugin, generator hoặc OS tool khác không?
10. **Archive metadata:** file permission, extra field hoặc central directory có khác không?

Không nên chỉ so sánh file JAR bằng cách đổi tên hoặc sửa timestamp bên ngoài. Cần sửa nguyên nhân trong build để mọi lần tạo artifact đều có kết quả ổn định.

## 16. Timestamp trong artifact và provenance

Một số tổ chức muốn artifact ghi rõ thời điểm build để điều tra sự cố. Điều đó có thể xung đột với byte-for-byte reproducibility nếu timestamp thay đổi theo từng lần chạy.

Có thể tách hai nhu cầu:

- **Artifact reproducible:** nội dung được tạo từ source revision và input đã kiểm soát; không nhúng thời điểm chạy job thay đổi.
- **Build provenance:** thông tin ai/build system nào tạo artifact, thời điểm, source revision, workflow và môi trường được lưu trong attestation hoặc metadata CI có thể xác minh.

Nếu dự án bắt buộc nhúng timestamp vào artifact, hãy xác định nguồn timestamp ổn định, chẳng hạn timestamp của source revision, và ghi rõ rằng mục tiêu reproducibility được tính theo cùng revision. Không nên vừa yêu cầu artifact chứa thời điểm hiện tại, vừa kỳ vọng hai lần build khác thời điểm có byte giống hệt nhau.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Cùng source nhưng JAR checksum khác | Entry timestamp hoặc archive metadata thay đổi | Chuẩn hóa timestamp và kiểm tra metadata ZIP |
| Danh sách file giống nhau nhưng JAR khác | Thứ tự entry hoặc compression khác | Bật reproducible file order, kiểm soát công cụ nén |
| Build trên Windows và Linux cho resource khác nhau | Line ending, encoding, locale hoặc thứ tự filesystem | Chuẩn hóa UTF-8/LF, locale và sắp xếp input |
| Artifact chứa đường dẫn `/home/runner/...` | Generated metadata hoặc debug/tool output ghi workspace path | Dùng relative path hoặc loại thông tin máy khỏi artifact |
| Artifact chứa username/hostname | Task/plugin ghi thông tin người chạy hoặc máy build | Loại khỏi output hoặc chuyển vào provenance bên ngoài |
| `build-info.properties` khác giữa hai lần build | Timestamp, branch, dirty flag hoặc commit metadata thay đổi | Chọn metadata ổn định và khai báo input rõ ràng |
| JAR giống nội dung nhưng khác hash | ZIP timestamp, entry order, extra fields hoặc compression khác | So sánh metadata archive và chuẩn hóa archive task |
| Build khác nhau dù đã chuẩn hóa archive | Bytecode/resource/dependency thực sự khác | So sánh file đã giải nén, toolchain và dependency graph |
| Gradle task dùng cache cho kết quả cũ | Task input khai báo thiếu hoặc build cache được tái sử dụng | Khai báo input đầy đủ; thử `--no-build-cache --rerun-tasks` khi điều tra |
| Maven output khác giữa máy | Plugin/JDK version, outputTimestamp hoặc môi trường khác | Pin toolchain/plugin và đặt `project.build.outputTimestamp` |

## 18. Quy trình áp dụng cho dự án Java

Khi muốn làm artifact tái lập hơn, có thể triển khai theo trình tự:

1. **Xác định artifact cần reproducible:** JAR chính, sources/Javadoc, WAR, ZIP distribution hay tất cả.
2. **Pin toolchain:** Wrapper, JDK, compiler, plugin và công cụ ngoài.
3. **Kiểm soát dependency:** version cố định, lock state và verification metadata khi phù hợp.
4. **Chuẩn hóa archive:** timestamp entry và thứ tự file.
5. **Ổn định generator:** sắp xếp input, chuẩn hóa path, encoding, line ending, locale và timezone.
6. **Loại thông tin máy:** không nhúng workspace, username, hostname hoặc thời gian job nếu không cần.
7. **Khai báo task input/output:** bảo đảm Gradle/Maven plugin nhận biết mọi đầu vào ảnh hưởng output.
8. **Build từ workspace sạch:** tránh output cũ hoặc trạng thái cá nhân.
9. **So sánh checksum:** build cùng commit ở hai vị trí hoặc môi trường độc lập.
10. **Phân tích sai khác:** so entry, timestamp, manifest và nội dung giải nén.
11. **Lưu provenance riêng:** ghi source revision, toolchain, pipeline và thời điểm theo cơ chế có thể xác minh.
12. **Đưa kiểm tra vào CI:** xác nhận artifact reproducible trước khi publish nếu đây là yêu cầu của dự án.

## 19. Ví dụ cấu hình tổng hợp

### 19.1. Gradle Groovy DSL

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '2.4.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}

tasks.named('jar') {
    archiveBaseName.set('order-service')
    archiveVersion.set(project.version.toString())
}
```

Cấu hình này chuẩn hóa timestamp và thứ tự entry cho archive task, đồng thời cố định Java language version và tên JAR. Dự án vẫn cần pin Gradle Wrapper/plugin, dependency và các generator khác để kiểm soát toàn bộ build.

### 19.2. Maven

```xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
  <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
    </plugin>
  </plugins>
</build>
```

Timestamp ở ví dụ là giá trị cố định minh họa. Trong pipeline thực tế, có thể dùng một giá trị được tính từ source revision nếu cần. Các plugin khác tạo archive cũng cần hỗ trợ và sử dụng `project.build.outputTimestamp` hoặc có cấu hình reproducibility riêng.

## 20. Nguyên tắc cần ghi nhớ

- Timestamp của entry trong JAR/ZIP có thể làm checksum thay đổi dù nội dung file không đổi.
- Thứ tự entry cũng ảnh hưởng byte của archive; không dựa vào thứ tự filesystem hoặc collection tình cờ.
- Đường dẫn tuyệt đối, username, hostname và build time có thể lọt vào generated resource, manifest hoặc metadata.
- Gradle archive tasks có `preserveFileTimestamps` và `reproducibleFileOrder` để chuẩn hóa archive.
- Maven Archiver và các plugin hỗ trợ có thể dùng `project.build.outputTimestamp`.
- Custom generator phải tự ổn định thứ tự input, path, encoding, line ending, locale, timezone và dữ liệu sinh ra.
- Pin JDK, build tool, plugin và dependency; archive reproducibility không thể bù cho dependency/toolchain thay đổi.
- So sánh checksum để phát hiện sai khác, rồi so entry list, metadata và nội dung giải nén để tìm nguyên nhân.
- Kiểm tra hai workspace sạch khác đường dẫn để phát hiện path leakage.
- Lưu thời điểm build và thông tin provenance bên ngoài artifact khi cần giữ byte-for-byte reproducibility.

Timestamp, thứ tự file và đường dẫn máy là những chi tiết nhỏ nhưng có thể làm artifact khác nhau giữa hai lần build. Khi chuẩn hóa archive, kiểm soát generator và loại bỏ thông tin phụ thuộc máy, dự án có thể tạo sản phẩm ổn định hơn, dễ xác minh hơn và thuận lợi cho cache, ký số cũng như điều tra nguồn gốc artifact.
