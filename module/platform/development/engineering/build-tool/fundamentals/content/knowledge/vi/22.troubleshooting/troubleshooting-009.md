# Tái hiện lỗi với phạm vi tối thiểu và lưu bằng chứng chẩn đoán

Khi build Java thất bại, cách xử lý hiệu quả nhất thường bắt đầu bằng việc tái hiện lỗi một cách có kiểm soát. Một thông báo lỗi xuất hiện trong CI có thể liên quan đến source code, dependency, JDK, build plugin, cache, cấu hình môi trường, thứ tự task hoặc dịch vụ bên ngoài. Nếu thay đổi nhiều thứ cùng lúc, xóa cache ngay hoặc chạy lại bằng một lệnh khác, dấu vết ban đầu có thể biến mất và nguyên nhân trở nên khó xác định hơn.

**Tái hiện lỗi với phạm vi tối thiểu** là thu hẹp tình huống gây lỗi tới phần nhỏ nhất vẫn còn biểu hiện vấn đề. **Lưu bằng chứng chẩn đoán** là ghi lại đầy đủ thông tin cần thiết để người khác hiểu, kiểm tra và lặp lại lỗi đó.

Hai việc này bổ trợ cho nhau:

- Tái hiện ổn định giúp phân biệt lỗi thật với sự cố ngẫu nhiên.
- Thu hẹp phạm vi giúp giảm số yếu tố cần điều tra.
- Bằng chứng đầy đủ giúp người khác xác nhận kết quả mà không phải đoán môi trường hoặc lệnh đã chạy.
- Một reproducer nhỏ giúp kiểm tra giải pháp và tránh sửa nhầm phần không liên quan.

Mục tiêu không phải tạo một dự án nhỏ bằng mọi giá. Mục tiêu là giữ lại **đúng điều kiện cần để lỗi tiếp tục xảy ra**, đồng thời loại bỏ những phần không ảnh hưởng đến lỗi.

## 1. Vì sao cần tái hiện trước khi sửa?

Một lỗi build thường được phát hiện qua một trong các dấu hiệu:

- Task compile hoặc test thất bại.
- Build chạy lâu bất thường hoặc bị treo.
- Máy lập trình viên build được nhưng CI thất bại.
- Chỉ một module trong multi-project build gặp lỗi.
- Build chỉ thất bại khi bật parallel execution hoặc build cache.
- Dependency resolution chọn version khác dự kiến.
- Artifact được tạo nhưng chạy không đúng.
- Test lúc pass, lúc fail dù source không thay đổi.

Nếu chưa xác định điều kiện tái hiện, một thay đổi code có thể vô tình làm lỗi biến mất trong lần chạy hiện tại mà không giải quyết nguyên nhân. Ví dụ, chạy `clean` có thể làm một lỗi do output cũ biến mất; tăng timeout có thể che race condition; tắt một task có thể làm build xanh nhưng bỏ qua kiểm tra bắt buộc.

Tái hiện trước khi sửa đem lại một điểm so sánh rõ ràng:

```text
Trước khi sửa: lệnh X + môi trường Y -> lỗi E
Sau khi sửa:   lệnh X + môi trường Y -> thành công
```

Nếu lệnh, môi trường hoặc đầu vào thay đổi giữa hai lần, kết luận về hiệu quả của bản sửa sẽ yếu hơn.

## 2. Phân biệt triệu chứng, nguyên nhân và điều kiện kích hoạt

Một stack trace hoặc dòng `BUILD FAILED` là triệu chứng. Nó chưa chắc chỉ ra nguyên nhân gốc.

Ví dụ:

```text
Execution failed for task ':service:compileJava'.
> Could not resolve all files for configuration ':service:compileClasspath'.
```

Triệu chứng là task compile thất bại. Nguyên nhân có thể là repository không truy cập được, credential thiếu, version dependency không tồn tại hoặc metadata không hợp lệ. Sửa source Java trong trường hợp này sẽ không giải quyết được lỗi.

Nên ghi nhận ba lớp thông tin:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Triệu chứng | Điều gì xảy ra? | `compileJava` thất bại với `Could not resolve` |
| Điều kiện kích hoạt | Khi nào lỗi xuất hiện? | Chỉ trên CI, chỉ khi chạy offline, hoặc chỉ với JDK 21 |
| Nguyên nhân gốc | Điều gì làm hệ thống đi vào trạng thái lỗi? | Token repository hết hạn hoặc dependency bị publish thiếu |

Không nên kết luận nguyên nhân chỉ từ task đầu tiên báo lỗi. Hãy tìm thông báo gốc ở phần cuối stack trace, log của plugin hoặc dịch vụ mà task đang gọi.

## 3. Bảo toàn bằng chứng trước khi thử sửa

Khi lỗi vừa xảy ra, hãy lưu trạng thái và log ban đầu trước khi thực hiện các thao tác có thể làm thay đổi môi trường.

Nên giữ lại:

- Lệnh build chính xác và thư mục chạy lệnh.
- Exit code của tiến trình.
- Toàn bộ stdout/stderr hoặc file log được tạo.
- Thời điểm xảy ra lỗi và commit/revision đang build.
- Trạng thái working tree, các thay đổi chưa commit và file sinh tự động liên quan.
- Phiên bản JDK, Gradle/Maven Wrapper và hệ điều hành.
- Các tham số, profile, biến môi trường có ảnh hưởng (chỉ ghi tên và giá trị không nhạy cảm).
- Test report, daemon log, build scan hoặc log của dịch vụ phụ thuộc nếu có.
- Tần suất lỗi: luôn xảy ra, chỉ thỉnh thoảng, hay chỉ ở một môi trường.

Tránh xóa `build/`, `.gradle/`, `~/.gradle/caches`, `~/.m2/repository`, container hoặc database test trước khi ghi nhận bằng chứng cần thiết. Các vùng đó có thể chứa output cũ, cache hoặc trạng thái giúp tái hiện lỗi. Nếu cần thử với môi trường sạch, hãy tạo bản sao/workspace mới hoặc lưu lại bằng chứng rồi mới thay đổi trạng thái.

### 3.1. Ghi lệnh và log vào file

Linux/macOS:

```bash
./gradlew :service:test --stacktrace --info --console=plain \
  > diagnostics-gradle.log 2>&1
status=$?
printf 'exit_code=%s\n' "$status" >> diagnostics-gradle.log
```

Windows PowerShell:

```powershell
& .\gradlew.bat :service:test --stacktrace --info --console=plain *> diagnostics-gradle.log
$buildExitCode = $LASTEXITCODE
Add-Content diagnostics-gradle.log "exit_code=$buildExitCode"
```

Với Maven:

```bash
mvn -pl service -am test -e \
  > diagnostics-maven.log 2>&1
status=$?
printf 'exit_code=%s\n' "$status" >> diagnostics-maven.log
```

Các ví dụ trên lưu cả output và lỗi vào một file. Trong PowerShell, `$LASTEXITCODE` giữ exit code của chương trình native gần nhất; cần lấy giá trị ngay sau lệnh Maven/Gradle.

Không chỉ copy vài dòng cuối của log. Những dòng trước đó có thể cho biết task nào tạo ra trạng thái sai hoặc dependency nào được phân giải trước khi lỗi xảy ra.

### 3.2. Giữ nguyên thông tin thời điểm và revision

Ghi lại commit:

```bash
git rev-parse HEAD
git status --short
```

Hai lệnh giúp xác định revision và các thay đổi chưa commit. Nếu lỗi chỉ xảy ra với thay đổi local, cần giữ lại diff liên quan để người khác tái hiện.

Không đưa file chứa secret hoặc dữ liệu cá nhân vào gói chẩn đoán. Có thể lưu bản log gốc ở nơi nội bộ được kiểm soát và tạo bản đã che thông tin nhạy cảm để chia sẻ.

## 4. Ghi nhận môi trường build

Một lỗi có thể phụ thuộc phiên bản công cụ hoặc hệ điều hành. Cần ghi lại môi trường đủ chi tiết để người khác không phải suy đoán.

### 4.1. Java và JDK

```bash
java -version
javac -version
```

Nếu build dùng Java toolchain, JDK đang chạy Gradle/Maven có thể khác JDK dùng để compile. Ghi nhận cả hai nếu khác biệt này có ý nghĩa.

Với Gradle:

```bash
./gradlew --version
```

Output thể hiện Gradle version, JVM và thông tin môi trường liên quan. Có thể xem toolchain được cấu hình trong build script hoặc log task để xác định compiler thực tế.

Với Maven:

```bash
mvn -version
```

Lệnh này hiển thị Maven version, Java version, Java home và OS. Nếu Maven chạy trong CI container, cần ghi cả image/version hoặc digest khi có thể.

### 4.2. Hệ điều hành và kiến trúc

Linux:

```bash
uname -a
```

PowerShell:

```powershell
Get-CimInstance Win32_OperatingSystem |
    Select-Object Caption, Version, OSArchitecture
```

Với lỗi native library hoặc cross-compilation, ghi thêm CPU architecture, compiler và target platform. Một JAR Java thuần có thể dùng trên nhiều OS, nhưng plugin/native task có thể tạo output phụ thuộc nền tảng.

### 4.3. Build tool và cấu hình dự án

Ghi lại:

- Gradle Wrapper hoặc Maven Wrapper version.
- Plugin version liên quan đến task thất bại.
- `gradle.properties`, `settings.gradle`, `pom.xml` và profile đang dùng (chỉ phần không nhạy cảm).
- Dependency lock/verification metadata nếu có.
- Repository và mirror được cấu hình.
- Có dùng daemon, parallelism, configuration cache hoặc build cache không.

Không cần gửi toàn bộ file cấu hình nếu chúng quá lớn hoặc chứa thông tin nội bộ không liên quan. Hãy lưu đúng phần cần để tái hiện và giữ nguyên các giá trị ảnh hưởng lỗi.

## 5. Tái hiện theo đúng lệnh đã thất bại

Bước đầu tiên là chạy lại cùng lệnh, cùng commit và cùng môi trường nếu có thể. Không đổi task, profile, JDK hoặc cache policy trước khi xác nhận lỗi ban đầu.

Ví dụ Gradle:

```bash
./gradlew clean build
```

Nếu lỗi xuất hiện ở lệnh này, lần tái hiện đầu tiên cũng nên dùng cùng lệnh. Sau khi đã xác nhận, có thể chạy thêm biến thể có log chi tiết:

```bash
./gradlew clean build --stacktrace --info --console=plain
```

Ví dụ Maven:

```bash
mvn clean verify
```

Sau đó:

```bash
mvn clean verify -e
```

`-e` hiển thị exception chi tiết hơn. `-X` bật debug logging rất chi tiết, có thể hữu ích khi `-e` chưa đủ nhưng cũng có thể in URL, header, đường dẫn hoặc thông tin nhạy cảm. Chỉ dùng khi cần và kiểm tra log trước khi chia sẻ.

### 5.1. Lặp lại có kiểm soát

Nếu lỗi luôn xuất hiện, một lần tái hiện có thể đủ để bắt đầu thu hẹp. Nếu lỗi ngẫu nhiên, hãy chạy lặp lại và ghi số lần pass/fail.

Ví dụ ghi nhận:

| Lần chạy | Commit | Lệnh | Kết quả | Ghi chú |
|---|---|---|---|---|
| 1 | `abc123` | `./gradlew test` | Fail | `OrderServiceTest` timeout |
| 2 | `abc123` | `./gradlew test` | Pass | Không thay đổi input |
| 3 | `abc123` | `./gradlew test` | Fail | Cùng test, khác thời gian hoàn tất |

Mẫu này gợi ý flaky test hoặc phụ thuộc môi trường. Không nên chỉ giữ lần pass cuối cùng.

## 6. Thu hẹp phạm vi theo tầng

Sau khi bảo toàn lỗi ban đầu, giảm phạm vi từng bước. Một trình tự hữu ích:

1. **Từ toàn bộ pipeline tới stage:** xác định job hoặc phase thất bại.
2. **Từ stage tới task:** xác định task đầu tiên không hoàn thành.
3. **Từ task tới source set/module:** chạy riêng module hoặc source set liên quan.
4. **Từ source set tới test/class:** chỉ chạy test hoặc class có liên quan.
5. **Từ class tới method/input:** giữ lại dữ liệu tối thiểu vẫn làm lỗi xuất hiện.
6. **Từ project tới reproducer:** loại plugin, dependency hoặc file không ảnh hưởng.

Sau mỗi bước, ghi lại lệnh và kết quả. Nếu lỗi biến mất, phần vừa loại bỏ có thể chứa điều kiện cần thiết; khôi phục nó và thử một hướng thu hẹp khác.

### 6.1. Thu hẹp task Gradle

Xem task graph:

```bash
./gradlew build --dry-run
```

`--dry-run` hiển thị các task sẽ được lên lịch mà không chạy task action. Sau đó gọi task cụ thể:

```bash
./gradlew :service:compileJava --stacktrace --info
```

Hoặc chỉ chạy test của module:

```bash
./gradlew :service:test --stacktrace --info
```

Chạy một test cụ thể với JUnit/Gradle Test:

```bash
./gradlew :service:test --tests 'com.example.OrderServiceTest.rejectsEmptyOrder'
```

Nếu lỗi chỉ xảy ra khi chạy `build` toàn dự án, không nên giả định task riêng lẻ sẽ tái hiện. Lỗi có thể phụ thuộc thứ tự task, output của project khác, cấu hình root hoặc task chạy song song.

### 6.2. Thu hẹp module Maven

Trong multi-module Maven build, có thể chọn một project bằng `-pl` và kéo các module phụ thuộc cần thiết bằng `-am`:

```bash
mvn -pl service -am test -e
```

Để chạy một test cụ thể với Surefire:

```bash
mvn -pl service -am -Dtest=OrderServiceTest#rejectsEmptyOrder test
```

Nếu lỗi xảy ra ở integration test dùng Failsafe, lựa chọn test thường được điều khiển qua `-Dit.test=...` và build cần đi tới `verify` theo cấu hình plugin:

```bash
mvn -pl service -am -Dit.test=OrderApiIT verify
```

Tên module, test class và phase phải khớp với cấu hình dự án. Nếu task phụ thuộc plugin execution hoặc lifecycle phase sau `package`, chạy riêng `test` có thể không tái hiện được.

## 7. Tạo reproducer tối thiểu mà không làm mất điều kiện lỗi

Một reproducer tốt giữ lại những gì cần để lỗi xuất hiện và loại bỏ phần không liên quan. Không phải lúc nào cũng cần tạo project mới. Có thể bắt đầu bằng cách chạy một task nhỏ trong project hiện tại.

Các cấp độ reproducer:

| Cấp độ | Nội dung giữ lại | Khi phù hợp |
|---|---|---|
| Lệnh tối thiểu | Cùng project, chỉ chạy task/test gây lỗi | Lỗi gắn với một task hoặc test cụ thể |
| Module tối thiểu | Một module và dependency bắt buộc | Lỗi xuất hiện trong multi-project build |
| Source tối thiểu | Một class/test/input nhỏ nhất | Lỗi nằm trong logic hoặc compiler behavior |
| Build mẫu độc lập | Wrapper/POM/build script tối giản và source tái hiện | Cần báo lỗi cho plugin, Gradle/Maven hoặc thư viện ngoài |
| Container/fixture tối thiểu | JDK, OS image và dịch vụ phụ thuộc được cố định | Lỗi phụ thuộc môi trường hoặc tích hợp |

### 7.1. Giữ lại file build quan trọng

Khi tạo project mẫu, đừng xóa ngay:

- Gradle/Maven Wrapper và version tương ứng.
- Repository declaration hoặc mirror cần thiết.
- Plugin version đang liên quan.
- Java toolchain/compiler release.
- Dependency lock hoặc version constraint.
- Profile, source set hoặc task custom gây lỗi.
- Annotation processor hoặc code generator liên quan.

Nếu lỗi liên quan tới plugin, reproducer không có plugin đó sẽ không còn tái hiện. Nếu lỗi liên quan dependency resolution, bỏ repository hoặc lockfile có thể làm thay đổi version được chọn.

### 7.2. Loại bỏ từng yếu tố một

Một cách giảm phạm vi có kiểm soát:

1. Tạo bản sao reproducer hoặc branch riêng.
2. Chạy lại và xác nhận lỗi vẫn xuất hiện.
3. Loại một plugin/dependency/source/resource không nghi ngờ.
4. Chạy lại đúng lệnh.
5. Nếu lỗi còn, giữ việc loại bỏ; nếu lỗi biến mất, khôi phục yếu tố vừa loại.
6. Tiếp tục cho đến khi không thể loại thêm mà lỗi vẫn còn.

Đây là phương pháp delta debugging ở dạng thực hành. Thay đổi một nhóm nhỏ mỗi lần giúp biết phần nào làm lỗi biến mất.

### 7.3. Ví dụ reproducer Gradle tối thiểu

Giả sử lỗi chỉ xảy ra khi task custom đọc resource và tạo file index. Có thể giảm dự án thành:

```text
reproducer/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── settings.gradle
├── build.gradle
└── src/main/resources/
    └── sample.yml
```

`settings.gradle`:

```groovy
rootProject.name = 'resource-index-reproducer'
```

`build.gradle`:

```groovy
tasks.register('generateIndex') {
    def sourceDirectory = layout.projectDirectory.dir('src/main/resources')
    def outputFile = layout.buildDirectory.file('generated/index.txt')

    inputs.dir(sourceDirectory)
    outputs.file(outputFile)

    doLast {
        def files = fileTree(sourceDirectory).files
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = files.collect { it.name }.join('\n')
    }
}
```

Chạy:

```bash
./gradlew generateIndex --stacktrace --info
```

Ví dụ này chỉ là khung reproducer. Để tái hiện một lỗi thật, cần giữ nguyên phần implementation/task property/Gradle version gây lỗi. Không thay implementation bằng một task “gần giống” rồi kết luận đã tái hiện cùng vấn đề.

### 7.4. Ví dụ reproducer Maven tối thiểu

Nếu lỗi nằm trong Maven plugin, project mẫu nên giữ đúng plugin version và execution:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example.repro</groupId>
  <artifactId>plugin-reproducer</artifactId>
  <version>1.0-SNAPSHOT</version>

  <build>
    <plugins>
      <plugin>
        <groupId>org.example</groupId>
        <artifactId>example-plugin</artifactId>
        <version>1.2.3</version>
        <executions>
          <execution>
            <goals>
              <goal>run</goal>
            </goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

`org.example:example-plugin:1.2.3` là placeholder minh họa. Reproducer thật phải dùng tọa độ/version và cấu hình plugin thực tế gây lỗi, cùng source/resource tối thiểu cần thiết.

## 8. Tách lỗi source, build logic, dependency và môi trường

Không phải lỗi nào cũng cần cùng cách tái hiện. Hãy phân loại trước khi thu hẹp.

| Nhóm lỗi | Dấu hiệu | Hướng tái hiện |
|---|---|---|
| Source/compile | Compiler báo lỗi cú pháp, type hoặc annotation processing | Chạy compile task/module; giữ source và compiler options |
| Test | Assertion, exception hoặc timeout trong test | Chạy riêng test/class; giữ test data và runtime classpath |
| Dependency resolution | Không tải được module hoặc version | Giữ repository, mirror, credential context không nhạy cảm và dependency declaration |
| Plugin/task | Task custom hoặc plugin execution thất bại | Giữ plugin version, task graph, inputs/outputs và build tool version |
| Cache/incremental | Chỉ sai sau khi thay đổi input hoặc khôi phục cache | So sánh clean, incremental, cache off/on và input fingerprint |
| Parallelism | Chỉ lỗi khi task/test chạy đồng thời | Lặp lại với cùng parallel setting; thử tuần tự để khoanh vùng |
| Runtime/package | Build pass nhưng JAR/WAR không chạy | Giữ artifact, manifest, runtime classpath và lệnh launch |
| Môi trường/OS | Chỉ lỗi trên một runner hoặc hệ điều hành | Giữ JDK, OS, architecture, environment và filesystem đặc trưng |
| Network/service | Timeout, 401/403, API/database unavailable | Lưu request metadata an toàn, status, latency và service health |

Phân loại không thay thế điều tra; nó giúp chọn phép thử nhỏ nhất có ích.

## 9. Dùng clean build và incremental build đúng mục đích

`clean` là một phép thử hữu ích nhưng không nên là bước đầu tiên trong mọi sự cố.

### 9.1. Lỗi chỉ xuất hiện ở incremental build

Nếu clean build pass nhưng incremental build tạo output sai, có thể task khai báo input/output chưa đầy đủ hoặc logic xử lý thay đổi chưa đúng.

Thử nghiệm:

1. Build một lần để tạo output.
2. Thay đổi đúng một input.
3. Chạy lại task mà không clean.
4. Kiểm tra task có chạy lại không.
5. So sánh output với kết quả từ clean build.

Nếu output incremental khác output clean, đây là bằng chứng quan trọng về lỗi incremental/task state.

### 9.2. Lỗi chỉ biến mất sau clean

Điều đó có thể chỉ ra output cũ, stale generated source, task output không được dọn đúng hoặc cache state. Không nên chỉ ghi nhận “clean là hết”. Hãy xác định file/trạng thái nào đã bị clean xóa và vì sao nó làm build sai.

### 9.3. Phân biệt project clean với build cache clean

Trong Gradle:

```bash
./gradlew clean build --no-build-cache --rerun-tasks
```

Lệnh này xóa output project, tắt sử dụng build cache cho lần chạy và yêu cầu chạy lại task. Nó có thể hữu ích khi muốn kiểm tra build thực thi từ đầu, nhưng vẫn có thể dùng dependency cache và configuration cache tùy lệnh/cấu hình.

Không cần xóa toàn bộ `~/.gradle` hoặc `~/.m2` để thực hiện một phép thử clean project. Nếu cần kiểm tra dependency cache, hãy tạo Gradle User Home hoặc Maven local repository riêng cho reproducer thay vì xóa dữ liệu dùng chung.

## 10. Điều tra dependency resolution

Khi lỗi liên quan dependency, hãy tìm xem module/version nào được yêu cầu và vì sao build chọn nguồn/version đó.

### 10.1. Gradle

Xem dependency graph:

```bash
./gradlew :service:dependencies --configuration runtimeClasspath
```

Xem lý do một dependency được chọn:

```bash
./gradlew :service:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Nếu lỗi compile, thay `runtimeClasspath` bằng `compileClasspath` phù hợp. Nếu dependency nằm trong test, xem `testRuntimeClasspath` hoặc `testCompileClasspath`.

Ghi lại repository declaration và version selector. Dynamic version, SNAPSHOT, changing module hoặc metadata cache có thể làm kết quả khác nhau giữa các lần chạy.

### 10.2. Maven

Xem dependency tree:

```bash
mvn -pl service dependency:tree
```

Xem effective POM khi nghi ngờ parent POM/profile/plugin management làm thay đổi cấu hình:

```bash
mvn -pl service help:effective-pom
```

Effective POM có thể rất dài và chứa URL hoặc giá trị nội bộ; chỉ chia sẻ phần liên quan sau khi kiểm tra thông tin nhạy cảm.

Nếu lỗi chỉ xảy ra khi tải dependency, ghi lại repository/mirror, status HTTP, version và thời điểm. Không đưa token hoặc password vào log chia sẻ.

## 11. Điều tra lỗi cache và incremental execution

Cache có thể làm lỗi khó tái hiện nếu task output phụ thuộc input chưa được khai báo hoặc trạng thái cũ còn tồn tại.

Với Gradle, so sánh các trường hợp:

```bash
# Build với cấu hình cache hiện tại
./gradlew :service:compileJava --info

# Không dùng build cache
./gradlew :service:compileJava --no-build-cache --rerun-tasks --info

# Làm mới dependency resolution khi nghi ngờ metadata/artifact đã cache
./gradlew :service:dependencies --refresh-dependencies
```

Các lệnh trả lời câu hỏi khác nhau:

- `--no-build-cache` tránh khôi phục task output từ build cache.
- `--rerun-tasks` yêu cầu thực thi lại task phù hợp.
- `--refresh-dependencies` yêu cầu làm mới trạng thái phân giải dependency.

Không bật tất cả tùy chọn cùng lúc nếu mục tiêu là xác định nguyên nhân. Thay từng yếu tố để biết lỗi gắn với build cache, incremental state hay dependency cache.

Với Maven, có thể dùng `-U` để yêu cầu kiểm tra cập nhật snapshot/một số artifact thiếu theo quy tắc Maven:

```bash
mvn -U -pl service verify
```

Đây không phải lệnh xóa toàn bộ local repository. Nếu cần tái hiện trên repository sạch, cấu hình một local repository riêng bằng `-Dmaven.repo.local=...` và chuẩn bị dependency cần thiết cho môi trường đó.

## 12. Điều tra lỗi song song và race condition

Nếu lỗi chỉ xuất hiện khi bật parallel execution, hãy giữ lại cấu hình ban đầu và chạy lặp lại trước khi đổi sang tuần tự.

Sau đó so sánh:

```bash
# Cấu hình parallel hiện tại
./gradlew build --parallel --stacktrace --info

# Thử tuần tự để khoanh vùng
./gradlew build --no-parallel --stacktrace --info
```

Tùy phiên bản Gradle và cấu hình, parallel behavior có thể đến từ project parallelism, worker API hoặc test forks; `--no-parallel` không nhất thiết tắt mọi hình thức concurrency bên trong plugin/task.

Với test, kiểm tra:

- File/database/port có được chia sẻ không?
- Test có phụ thuộc thứ tự hoặc static state không?
- Task có ghi chung output file không?
- Có task nào thiếu dependency edge nên chạy trước khi input sẵn sàng không?
- Worker/process có dùng chung thư mục tạm không?

Nếu lỗi biến mất khi chạy tuần tự, đó là manh mối về concurrency, không phải bằng chứng rằng tắt parallel là bản sửa cuối cùng.

## 13. Điều tra test flaky

Khi cùng một test lúc pass lúc fail, hãy ghi nhận:

- Tên test và test suite.
- Số lần chạy, số pass/fail và tỷ lệ thất bại.
- Seed nếu test dùng random data.
- Thời gian bắt đầu/kết thúc và timeout.
- Worker/fork/thread count.
- Port, database schema hoặc tài nguyên dùng chung.
- Network/service dependency và status.
- Stack trace, stdout/stderr và test report của từng lần fail.

Chạy test riêng nhiều lần có thể giúp xác định phạm vi:

```bash
./gradlew :service:test --tests 'com.example.OrderServiceTest' --rerun-tasks
```

Với Maven Surefire:

```bash
mvn -pl service -Dtest=OrderServiceTest test
```

Nếu test chỉ thất bại khi chạy cùng suite, nguyên nhân có thể là shared state hoặc thứ tự. Nếu chỉ thất bại dưới tải, có thể liên quan race, timeout hoặc tài nguyên. Không nên chỉ tăng retry để làm tỷ lệ pass trông tốt hơn.

## 14. Điều tra build treo hoặc task chạy quá lâu

Build treo khác với build thất bại nhanh. Khi tiến trình chưa thoát, hãy thu thập bằng chứng trong lúc nó còn ở trạng thái treo.

Nên ghi:

- Task đang chạy và thời gian đã trôi qua.
- CPU/memory của tiến trình Gradle/Maven/JVM.
- Thread dump của JVM nếu nghi deadlock hoặc chờ lock.
- Log cuối cùng trước khi không còn tiến triển.
- Trạng thái network, database hoặc process con mà task đang chờ.

Tìm PID JVM:

```bash
jcmd -l
```

Lấy thread dump:

```bash
jcmd <pid> Thread.print > thread-dump.txt
```

Hoặc:

```bash
jstack <pid> > thread-dump.txt
```

Thay `<pid>` bằng process ID thực tế. Nếu build chạy nhiều JVM/worker, cần xác định đúng tiến trình đang bị treo.

Với Gradle daemon, có thể xem log trong Gradle User Home dưới `daemon/<gradle-version>/`. Đường dẫn và tên file phụ thuộc phiên bản/cấu hình. Lưu log trước khi dừng daemon hoặc xóa cache.

Không nên gửi thread dump công khai mà chưa xem nội dung: nó có thể chứa tên class nội bộ, đường dẫn, URL hoặc dữ liệu từ stack frame.

## 15. Dùng binary search để tìm commit gây lỗi

Nếu biết một commit cũ build thành công và commit mới build thất bại, có thể dùng `git bisect` để tìm commit đầu tiên làm lỗi xuất hiện.

Quy trình:

1. Chọn revision tốt đã xác nhận build pass.
2. Chọn revision xấu đã xác nhận build fail.
3. Chạy `git bisect start`, đánh dấu good/bad.
4. Ở mỗi commit trung gian, chạy cùng một lệnh kiểm tra.
5. Đánh dấu `good` hoặc `bad` dựa trên kết quả tái hiện.
6. Kết thúc bằng `git bisect reset` để quay lại revision ban đầu.

Ví dụ:

```bash
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>
```

Sau đó tại mỗi revision:

```bash
./gradlew :service:test --no-build-cache
```

Đánh dấu:

```bash
git bisect good
# hoặc
git bisect bad
```

Khi hoàn tất:

```bash
git bisect reset
```

Chỉ dùng `git bisect run` khi đã có một script kiểm tra đáng tin cậy, trả exit code ổn định và không làm thay đổi trạng thái repository theo cách ảnh hưởng lần chạy tiếp theo. Nếu lỗi flaky, binary search tự động có thể phân loại sai commit.

## 16. Giữ bằng chứng có thể chia sẻ và tái sử dụng

Một gói chẩn đoán nên có cấu trúc rõ ràng để reviewer không phải tìm từng file rời.

Ví dụ:

```text
diagnostics/
├── README.md
├── command.txt
├── environment.txt
├── git-revision.txt
├── build.log
├── test-reports/
│   ├── index.html
│   └── TEST-*.xml
├── daemon-or-plugin-logs/
├── thread-dump.txt              # Chỉ khi build bị treo
├── dependency-tree.txt          # Khi lỗi liên quan dependency
└── reproducer/
    ├── gradlew
    ├── gradle/wrapper/
    ├── settings.gradle
    ├── build.gradle
    └── src/
```

Không phải lỗi nào cũng cần mọi file. Chỉ lưu bằng chứng liên quan để gói chẩn đoán gọn và dễ đọc.

### 16.1. Nội dung README chẩn đoán

README nên trả lời:

- Lỗi là gì và mức độ ảnh hưởng ra sao?
- Lệnh chính xác để tái hiện?
- Cần chạy từ thư mục nào?
- Revision nào đã được kiểm tra?
- JDK/build tool/OS nào được sử dụng?
- Lỗi xảy ra mỗi lần hay chỉ thỉnh thoảng?
- Kết quả mong đợi và thực tế là gì?
- File log/report nào chứa bằng chứng?
- Có bước nào cần service, credential hoặc biến môi trường không?
- Những thử nghiệm nào đã làm và kết quả từng thử nghiệm?

### 16.2. Không gửi secret trong bằng chứng

Debug log có thể chứa:

- Authorization header hoặc access token.
- Password trong URL connection string.
- Repository URL nội bộ.
- Username, home directory hoặc hostname.
- Dữ liệu test lấy từ hệ thống thật.
- Nội dung file cấu hình có thông tin nhạy cảm.

Trước khi chia sẻ, hãy kiểm tra và che giá trị nhạy cảm. Giữ lại cấu trúc và tên biến nếu cần chẩn đoán, nhưng thay secret bằng placeholder như `<REDACTED>`. Không xóa dòng lỗi quan trọng khi redaction; chỉ thay giá trị bí mật.

## 17. Chọn mức log phù hợp

Log càng chi tiết càng có nhiều manh mối nhưng cũng càng lớn và có thể chứa dữ liệu nhạy cảm. Nên tăng mức log theo từng bước.

| Mức | Gradle | Maven | Khi dùng |
|---|---|---|---|
| Mặc định | Không thêm flag | Không thêm flag | Ghi nhận triệu chứng ban đầu |
| Stack trace/exception | `--stacktrace` | `-e` | Xem chuỗi exception và vị trí lỗi |
| Thông tin chi tiết | `--info` | Tùy plugin; thường dùng output mặc định cộng `-e` | Xem task/configuration và hoạt động liên quan |
| Debug sâu | `--debug` | `-X` | Điều tra plugin, resolution hoặc hành vi nội bộ khi log thường chưa đủ |

Không nên bắt đầu mọi lần điều tra bằng debug sâu. Log có thể rất lớn, khó đọc và tiết lộ thông tin môi trường. Lưu log gốc ở nơi kiểm soát và chỉ chia sẻ bản đã kiểm tra.

## 18. Dùng Build Scan và báo cáo công cụ

Gradle Build Scan có thể cung cấp task timeline, dependency resolution, cache behavior, môi trường và thông tin build khác:

```bash
./gradlew build --scan
```

Build Scan hữu ích khi lỗi phụ thuộc task ordering, cache hoặc CI environment. Nhưng scan có thể upload dữ liệu build tới dịch vụ được cấu hình; cần tuân thủ chính sách của tổ chức trước khi chia sẻ link.

Gradle profile:

```bash
./gradlew build --profile
```

Maven có thể tạo dependency tree hoặc effective POM:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Các báo cáo này không thay thế log gốc. Chúng bổ sung thông tin về cấu hình và dependency graph.

## 19. Một quy trình tái hiện lỗi có kiểm soát

Có thể dùng quy trình sau cho phần lớn sự cố build Java:

1. **Dừng thay đổi môi trường:** chưa xóa cache, output hoặc container khi chưa lưu bằng chứng.
2. **Ghi nhận triệu chứng:** task, thông báo lỗi, thời điểm, tần suất và ảnh hưởng.
3. **Ghi nhận revision:** commit, working tree và các file local liên quan.
4. **Ghi nhận môi trường:** OS/architecture, JDK, build tool, plugin và cache state.
5. **Lưu lệnh và log:** giữ nguyên command, cwd, stdout/stderr và exit code.
6. **Tái hiện nguyên trạng:** chạy lại đúng lệnh trong cùng điều kiện.
7. **Phân loại lỗi:** source, test, dependency, plugin, cache, parallelism, runtime hay environment.
8. **Thu hẹp từng tầng:** pipeline → task → module → test/source/input.
9. **Tạo reproducer:** loại từng yếu tố không liên quan và xác nhận lỗi vẫn còn.
10. **Thử một biến mỗi lần:** thay cache, parallelism, JDK hoặc dependency riêng biệt.
11. **Lưu kết quả từng thử nghiệm:** command, điều kiện, kết quả và bằng chứng.
12. **Kiểm tra bản sửa:** chạy lại reproducer và bộ test/hợp đồng rộng hơn.
13. **Đóng gói chẩn đoán:** README, log, report và reproducer đã che secret.

## 20. Ví dụ: lỗi chỉ xảy ra trên CI

Giả sử developer chạy:

```bash
./gradlew clean check
```

và build thành công, nhưng CI báo `Could not resolve com.example:internal-api:2.1.0`.

Không nên lập tức thêm dependency khác hoặc sửa source. Hãy so sánh:

| Thông tin | Developer | CI |
|---|---|---|
| Commit | `abc123` | `abc123` |
| Gradle version | Wrapper version | Wrapper version |
| JDK | Ghi nhận `java -version` | Ghi nhận `java -version` |
| Repository | Có thể có local Maven/Gradle cache | Remote repository trong job |
| Credential | Có thể lấy từ user settings | CI secret variable |
| Cache | Dependency đã tải từ trước | Cache restore hoặc cache sạch |

Tiếp theo:

1. Lưu log CI đầy đủ và task thất bại.
2. Kiểm tra repository URL/mirror và credential name, không in secret.
3. Chạy `dependencyInsight` để xác định module/version cần phân giải.
4. Thử build trong workspace mới với Gradle User Home riêng để loại trạng thái local.
5. Nếu lỗi chỉ do CI thiếu credential, tái hiện bằng môi trường test có quyền đọc tương đương.

Kết quả mong muốn là reproducer cho thấy dependency resolution thất bại khi thiếu quyền/nguồn cụ thể. Khi đó, bản sửa có thể tập trung vào CI credential/repository configuration thay vì thay đổi code ứng dụng.

## 21. Ví dụ: lỗi chỉ xảy ra sau incremental build

Giả sử task `generateConfig` tạo `build/generated/app.properties` từ `src/main/config/app.yml`. Clean build tạo output đúng, nhưng sau khi sửa YAML rồi chạy build lần nữa, output vẫn cũ.

Quy trình:

1. Build lần đầu và lưu output.
2. Thay đổi một giá trị trong YAML.
3. Chạy lại task không clean.
4. Kiểm tra task có bị `UP-TO-DATE` hoặc `FROM-CACHE` không.
5. Chạy lại với `--no-build-cache --rerun-tasks`.
6. So sánh output giữa incremental và forced execution.

Nếu forced execution tạo output mới nhưng incremental không chạy task, có thể input YAML chưa được khai báo. Nếu cache restore output cũ, kiểm tra input fingerprint và cache key.

Reproducer tối thiểu chỉ cần build logic của `generateConfig`, file YAML ban đầu và thay đổi nhỏ làm lỗi xuất hiện. Không cần giữ toàn bộ ứng dụng nếu các module khác không ảnh hưởng task.

## 22. Ví dụ: test chỉ fail khi chạy song song

Một test ghi vào file cố định `build/test-data/result.json`. Hai test worker cùng ghi file này có thể ghi đè hoặc đọc dữ liệu của nhau.

Để tái hiện:

1. Ghi lại số worker/fork và test class.
2. Chạy suite với parallel setting ban đầu nhiều lần.
3. Lưu report và log của lần fail.
4. Chạy riêng test gây lỗi.
5. Chạy cùng test với parallelism thấp để so sánh.
6. Kiểm tra file, port, database và static state được chia sẻ.

Bản sửa thường là tạo thư mục tạm riêng cho mỗi test/worker, cấp port động hoặc tạo dữ liệu riêng. Sau sửa, chạy lại ở parallel setting ban đầu để chứng minh lỗi đã được giải quyết trong điều kiện kích hoạt thật.

## 23. Những lỗi thường gặp khi tái hiện và lưu bằng chứng

| Sai lầm | Hậu quả | Cách làm tốt hơn |
|---|---|---|
| Xóa cache ngay khi build lỗi | Mất trạng thái có thể cần để tái hiện | Lưu log và tạo bản sao/workspace riêng trước |
| Chỉ gửi ảnh chụp vài dòng cuối | Thiếu task, dependency và exception gốc | Lưu toàn bộ log cùng exit code |
| Đổi nhiều cấu hình cùng lúc | Không biết thay đổi nào làm lỗi biến mất | Thay một biến mỗi lần |
| Tạo reproducer quá sớm rồi bỏ plugin/version gây lỗi | Reproducer không còn cùng điều kiện | Giữ toolchain, plugin, dependency và cấu hình liên quan |
| Chạy `clean` khi lỗi chỉ xảy ra incremental | Xóa trạng thái lỗi trước khi quan sát | Tái hiện incremental trước, sau đó mới so sánh clean |
| Chỉ chạy test một lần khi lỗi flaky | Có thể bỏ sót điều kiện ngẫu nhiên | Chạy lặp và ghi tần suất/seed/tài nguyên |
| Dùng `--debug` rồi chia sẻ log nguyên bản | Có thể lộ credential/URL/dữ liệu nội bộ | Chỉ tăng log khi cần và redaction trước khi chia sẻ |
| Chỉ kiểm tra exit code | Bỏ qua test report hoặc output sai nhưng process vẫn thành công | Kiểm tra log, report, artifact và hành vi |
| Dùng `--offline` để che lỗi repository | Không xác định được nguồn lỗi mạng/credential | So sánh online/offline như hai thí nghiệm riêng |
| Tắt task/test để build xanh | Thay đổi hợp đồng build, che lỗi | Giữ verification bắt buộc và thu hẹp đúng phạm vi |
| Không ghi commit/JDK/tool version | Người khác không thể tái hiện cùng môi trường | Ghi revision và toolchain vào README chẩn đoán |

## 24. Mẫu báo cáo lỗi có thể tái hiện

Có thể dùng mẫu sau khi gửi lỗi cho đồng đội hoặc maintainer của plugin/build tool:

```text
Title:
[Mô tả ngắn triệu chứng]

Impact:
[Task/module/pipeline nào bị ảnh hưởng? Có chặn release không?]

Environment:
- OS / architecture:
- JDK (runtime):
- Java toolchain/compiler (nếu khác):
- Gradle/Maven Wrapper:
- Relevant plugin versions:
- CI runner/container (nếu có):

Revision:
- Commit:
- Working tree changes:

Command:
[Lệnh đầy đủ, gồm arguments và working directory]

Expected:
[Kết quả mong đợi]

Actual:
[Kết quả thực tế và exit code]

Reproduction rate:
[Luôn xảy ra / N trên M lần / chỉ ở môi trường cụ thể]

Minimal reproduction:
[Các file cần thiết và các bước chạy]

Evidence:
- Build log:
- Test report:
- Dependency tree / task graph:
- Thread dump / scan / other diagnostics:

Experiments:
- [Thay đổi một yếu tố và kết quả]
- [Thay đổi một yếu tố khác và kết quả]

Sensitive data:
[Đã che credential/token và dữ liệu không được phép chia sẻ]
```

Mẫu này giúp người nhận phân biệt triệu chứng với giả thuyết nguyên nhân, đồng thời có đủ thông tin để tái hiện.

## 25. Nguyên tắc cần ghi nhớ

- Tái hiện lỗi bằng đúng lệnh, revision và điều kiện ban đầu trước khi thay đổi môi trường.
- Lưu log, exit code, test report, task/dependency evidence và thông tin toolchain trước khi clean hoặc xóa cache.
- Thu hẹp từ pipeline tới task, module, test và input; mỗi lần chỉ loại một yếu tố.
- Reproducer tối thiểu phải giữ đúng plugin, version, repository, toolchain và cấu hình cần để lỗi xuất hiện.
- Phân biệt clean build, incremental build, build cache và dependency cache; chúng có thể làm lỗi biểu hiện khác nhau.
- Với lỗi flaky hoặc parallel, ghi tần suất, worker, seed và tài nguyên dùng chung.
- Với lỗi treo, thu thread dump và log trước khi dừng tiến trình.
- Dùng `dependencyInsight`, `dependency:tree`, task graph và report phù hợp để kiểm tra giả thuyết.
- Không chia sẻ debug log, Build Scan hoặc cấu hình chứa secret trước khi kiểm tra và redaction.
- Một bản sửa chỉ được xác nhận khi lệnh tái hiện ban đầu không còn lỗi và các kiểm tra rộng hơn vẫn đạt.

Tái hiện lỗi với phạm vi tối thiểu giúp biến một sự cố khó hiểu thành một tình huống có thể kiểm tra. Khi giữ nguyên điều kiện gây lỗi, thu hẹp từng bước và lưu bằng chứng đầy đủ, nhóm có thể xác định nguyên nhân chính xác hơn, đánh giá bản sửa đáng tin cậy hơn và tránh lặp lại cùng một cuộc điều tra ở những lần build sau.
