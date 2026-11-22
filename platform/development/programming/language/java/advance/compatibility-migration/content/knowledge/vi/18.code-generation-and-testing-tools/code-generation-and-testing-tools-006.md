# JaCoCo, công cụ phân tích tĩnh và phiên bản class file được hỗ trợ

Trong **Java Advance Compatibility Migration**, việc nâng JDK thường khiến nhóm phát triển tập trung vào lỗi biên dịch và lỗi chạy ứng dụng. Tuy nhiên, một lớp tương thích khác rất quan trọng nằm ở **các công cụ đọc, phân tích hoặc biến đổi class file**. Ứng dụng có thể được biên dịch thành công bằng JDK mới, nhưng JaCoCo không instrument được bytecode, một công cụ phân tích tĩnh không đọc được class file, plugin báo lỗi không rõ nguyên nhân hoặc báo cáo chất lượng mất dữ liệu. Khi đó, chất lượng kiểm thử không còn được đo một cách đáng tin cậy.

**JaCoCo** là công cụ đo code coverage cho JVM. Nó có thể instrument bytecode khi class được nạp hoặc xử lý file class theo chế độ offline, rồi tạo báo cáo line/branch/instruction coverage. Một số công cụ phân tích tĩnh như SpotBugs đọc bytecode; công cụ khác như PMD, Checkstyle hoặc Error Prone phân tích source code, AST hay mô hình compiler. Do chúng hoạt động ở **những tầng khác nhau của Java toolchain**, một công cụ có thể tương thích JDK đích trong khi công cụ khác không tương thích.

Bài này giải thích cách đọc phiên bản class file, mối quan hệ giữa JDK, JVM và thư viện ASM, cách JaCoCo instrument và lập báo cáo, cách phân loại các static analyzers, kiểm tra cấu hình Gradle/Maven, nhận diện lỗi thường gặp và thiết kế ma trận xác minh khi nâng cấp Java. Mục tiêu không phải chỉ làm CI xanh mà là **giữ được bằng chứng kiểm thử và phân tích chất lượng có ý nghĩa** trên runtime mới.

## 1. Class file là ranh giới tương thích quan trọng

Một file `.java` được compiler xử lý thành bytecode lưu trong file `.class`. Mỗi class file có header và các cấu trúc mô tả constant pool, methods, attributes, annotations và thông tin cần thiết cho JVM.

Sơ đồ:

~~~text
Java source (.java)
       |
       | javac / compiler
       v
Class file (.class)
       |
       +----> Java Virtual Machine đọc và thực thi
       |
       +----> JaCoCo / bytecode agent đọc hoặc biến đổi
       |
       +----> SpotBugs / bytecode analyzer đọc
       |
       +----> Shading / obfuscation / weaving tools
       |
       +----> Framework proxy / instrumentation
~~~

Những thành phần này không nhất thiết hỗ trợ cùng một phiên bản định dạng class file. Ví dụ, JVM Java 21 có thể chạy class file Java 21, nhưng một bản bytecode analyzer cũ có thể chưa hiểu cấu trúc tương ứng.

Cũng cần phân biệt:

- **Java source level:** tập cú pháp compiler chấp nhận.
- **Class-file version:** major/minor version ghi trong `.class`.
- **Platform API target:** tập Java SE API được phép sử dụng khi biên dịch.
- **Runtime JVM version:** khả năng JVM nạp và thực thi bytecode.
- **Tool parser version:** khả năng công cụ bên ngoài đọc và biến đổi file class.

Một tool thông báo “supports Java 21” cần được đọc trong đúng ngữ cảnh: hỗ trợ **chạy chính tool trên JDK 21**, **phân tích class files do JDK 21 tạo**, hay **phân tích source dùng cú pháp Java 21**? Ba cam kết đó khác nhau.

## 2. Major/minor version của class file

Header class file bắt đầu bằng magic number `CAFEBABE`, sau đó là minor và major version. Major version thường giúp xác định Java release tương ứng với định dạng bytecode.

| Java release | Class-file major version |
|---|---:|
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
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |

Ví dụ, class file có major version **65** tương ứng định dạng class file Java 21. Một JVM Java 17 thông thường không thể nạp class file có major 65; kết quả có thể là `UnsupportedClassVersionError`. Tuy nhiên, một công cụ phân tích tĩnh vẫn có thể ném lỗi tương tự dưới dạng `IllegalArgumentException: Unsupported class file major version 65`, dù JVM chạy tool là Java 21. Trường hợp đó thể hiện **parser bytecode của tool chưa hỗ trợ**, không nhất thiết JVM không chạy được ứng dụng.

### 2.1. Minor version và preview features

Đối với class files được tạo khi sử dụng preview language features trên các Java release áp dụng cơ chế preview class-file version, minor version có thể là `65535`. Việc nạp/chạy những class files này chịu các điều kiện gắn với release và `--enable-preview`.

Ví dụ:

~~~bash
javac --enable-preview --release 21 Example.java
java --enable-preview Example
~~~

Cú pháp trên là minh họa cho việc chạy một project **có dùng preview features hợp lệ của Java 21**. Không phải class nào được compiler tạo từ source code trong một compilation preview cũng nhất thiết mang dấu preview; cần quan sát file cụ thể.

Công cụ phân tích cần hỗ trợ cả **class-file major version** và những **construct/attributes** xuất hiện trong code, đặc biệt khi dùng preview hoặc tính năng JVM mới. Chỉ nhìn major version chưa đủ để chứng minh tool hiểu hết semantics.

### 2.2. Kiểm tra class file với javap

~~~bash
javap -verbose -classpath build/classes/java/main \
  com.example.orders.OrderService
~~~

Tìm trong output:

~~~text
minor version: 0
major version: 65
~~~

Ở đây major 65 nghĩa định dạng class file tương ứng Java 21. Hãy kiểm tra **đúng class file mà tool đang đọc**. Trong multi-module repository, một module có thể được biên dịch theo `--release 17` còn module khác theo Java 21.

### 2.3. Không dùng tuổi đời JAR để suy ra bytecode version

Một JAR có thể chứa nhiều classes được biên dịch ở các release khác nhau, đặc biệt khi dùng **multi-release JAR** với `META-INF/versions/...`. Vì vậy không nên chỉ nhìn version của JAR hoặc một class đại diện rồi kết luận mọi class file đều cùng major.

Nhiều công cụ bytecode có khả năng xử lý multi-release JAR, nhưng cách chọn variant có thể phụ thuộc tool version và cấu hình. Khi report chỉ lỗi với một JDK, cần xác định variant thực tế được runtime hoặc analyzer sử dụng.

## 3. Ba kiểu lỗi “không hỗ trợ version” dễ bị nhầm

Cùng từ khóa “unsupported version”, nguyên nhân có thể hoàn toàn khác nhau.

| Lỗi | Thành phần thường phát sinh | Ý nghĩa |
|---|---|---|
| `UnsupportedClassVersionError` khi start ứng dụng | JVM | JVM đang chạy không nạp được class-file version |
| `Unsupported class file major version N` trong JaCoCo/ASM/SpotBugs | Parser/transformer của công cụ | Tool hoặc thư viện bytecode chưa hiểu định dạng bytecode |
| `release version N not supported` khi compile | javac | Compiler quá cũ hoặc cấu hình `--release` không phù hợp |
| `Invalid source release: N` | Compiler hoặc build plugin | Toolchain/source level mismatch |
| `Preview features are not enabled` | Compiler/JVM hoặc tool | Preview setting chưa phù hợp với source/class |
| Report coverage rỗng dù tests pass | Plugin/agent/report pipeline | Chưa instrument, exec data thiếu, class mapping sai hoặc task không chạy |

**Quy tắc chẩn đoán:** tìm *process* và *class* đang phát sinh exception. Một `java.lang.IllegalArgumentException` từ thư viện ASM không được xử lý như lỗi JVM major version, dù thông báo rất giống.

## 4. JaCoCo đo code coverage bằng cách nào?

JaCoCo (Java Code Coverage) thu thập dữ liệu thực thi của bytecode trong quá trình chạy tests hoặc ứng dụng, rồi lập báo cáo từ dữ liệu đó và các class/source files tương ứng.

Luồng phổ biến:

~~~text
Source code                         Test source
    |                                   |
    | compile                           | compile
    v                                   v
.class files                      Test .class files
    |                                   |
    | JVM nạp class khi tests chạy      |
    v                                   |
JaCoCo Java agent <----------------------+
    |
    | Instrument bytecode (probes)
    | Ghi dữ liệu execution
    v
jacoco.exec hoặc dữ liệu execution tương đương
    |
    | + Original class files
    | + Source files
    v
JaCoCo report task
    |
    +--> HTML report
    +--> XML report (CI/Sonar integration)
    +--> CSV report (khi cần)
~~~

JaCoCo không đo coverage chỉ bằng việc đọc source; nó cần dữ liệu cho biết những probe nào được chạy. Việc hiển thị line/branch coverage còn phụ thuộc thông tin line number, bytecode structures và khả năng ánh xạ về source.

### 4.1. Coverage không phải “số dòng source đã chạy” theo nghĩa đơn giản

JaCoCo sử dụng các probe trong bytecode để suy ra các đơn vị coverage như:

- **Instructions:** các instruction bytecode được thực thi hoặc không.
- **Branches:** các nhánh điều kiện có thể nhận biết theo mô hình bytecode mà công cụ phân tích.
- **Lines:** ánh xạ bytecode tới các dòng source khi debug information phù hợp có sẵn.
- **Methods/classes:** sự hiện diện và mức độ thực thi của các thành phần.

Một dòng source có thể ánh xạ sang nhiều bytecode instructions; một biểu thức phức tạp có thể có nhiều nhánh. Vì vậy, “80% line coverage” không có nghĩa 80% nghiệp vụ đã được kiểm thử đầy đủ.

### 4.2. JaCoCo cần hiểu bytecode

Để thêm probe và phân tích class file, JaCoCo sử dụng công nghệ đọc/biến đổi bytecode, trong đó có thư viện **ASM**. Nếu phiên bản JaCoCo hoặc ASM mà tool sử dụng chưa hỗ trợ class-file major mới, instrumentation hoặc report generation có thể thất bại.

Khi nâng JDK, hãy xác định **JaCoCo version thực tế** mà plugin/test runner đang dùng và so với compatibility notes của release phù hợp. Không giả định một plugin Gradle/Maven mới tự động đồng nghĩa JaCoCo agent mới; phiên bản plugin, agent runtime và report tooling có thể là các thành phần riêng.

## 5. Online instrumentation và offline instrumentation

### 5.1. Online instrumentation

Chế độ thông dụng là chạy JaCoCo như **Java agent** qua `-javaagent`. Agent can thiệp vào quá trình class loading, instrument bytecode trước khi class được định nghĩa trong JVM.

Ví dụ minh họa hình thức JVM argument:

~~~bash
java -javaagent:/opt/tools/jacocoagent.jar=destfile=build/jacoco/test.exec \
     -cp "build/classes:lib/*" \
     com.example.orders.Main
~~~

Đây là ví dụ cơ chế agent, không phải khuyến nghị chạy ứng dụng production với agent coverage. Cách truyền tham số, lựa chọn port và nơi lưu execution data phải theo JaCoCo release thực tế.

### 5.2. Offline instrumentation

Trong offline mode, class files được instrument **trước** khi JVM chạy. Chế độ này đôi khi dùng khi class loading đặc biệt hoặc không thể gắn agent theo cách thông thường.

Rủi ro cần lưu ý:

- Instrumented classes khác original classes.
- Một số cấu hình cần runtime support phù hợp để chạy probes.
- Report cần class files phù hợp với cơ chế instrumentation đang dùng; tùy quy trình, dùng original classes là yêu cầu quan trọng.
- Không được vô tình instrument cùng một class **hai lần**.
- Build cache/shading có thể gây nhầm lẫn artifact gốc và artifact đã instrument.

Khi dự án chưa có lý do riêng dùng offline instrumentation, nên giữ một cách đo coverage nhất quán và tránh đồng thời bật online/offline cho cùng classes.

### 5.3. Khác biệt với static analysis

JaCoCo cần code được thực thi mới có dữ liệu execution; một công cụ như SpotBugs có thể phân tích bytecode mà không chạy phương thức nghiệp vụ. Do đó:

- **Coverage** trả lời mức độ code đã được chạy bởi tests.
- **Static analysis** tìm pattern hoặc vấn đề tiềm tàng trong code mà không cần chạy toàn bộ chương trình.
- **Tests** kiểm chứng assertions và hành vi.
- **Runtime instrumentation** có thể thay đổi timing/performance và chịu tác động từ class loaders, agent order.

Không nên xem điểm coverage cao như bằng chứng không có bug hoặc thay static analysis cho tests.

## 6. Vì sao JaCoCo cũ thất bại sau khi nâng JDK?

Các tình huống tiêu biểu:

1. JaCoCo agent không biết class-file major mới.
2. ASM version bên trong JaCoCo hoặc một thành phần khác trong pipeline quá cũ.
3. Test launcher chạy trên JVM khác với JVM được dùng để compile classes.
4. Framework/test library tạo bytecode động ở version mới mà agent không xử lý.
5. Dự án bật preview features nhưng agent/report tool chưa hỗ trợ construct đó.
6. Class được transform bởi nhiều Java agents theo thứ tự gây xung đột.
7. Report task đọc classes không khớp với execution data.
8. Test task bị skip, JVM fork không chạy hoặc JaCoCo agent argument không được truyền.
9. Một số classes được nạp bằng custom class loader hoặc cơ chế không tương thích với cấu hình instrumentation.
10. Agent report destination không có quyền ghi, bị xóa trước bước merge hoặc viết vào path khác.

Một ví dụ log có thể trông như:

~~~text
java.lang.instrument.IllegalClassFormatException:
Error while instrumenting com/example/OrderService
Caused by: java.lang.IllegalArgumentException:
Unsupported class file major version 65
~~~

Với major 65 (Java 21), cần kiểm tra **version của JaCoCo/ASM thực tế** trước khi thêm JVM flags. Mở package JPMS bằng `--add-opens` không làm parser bytecode cũ hiểu định dạng mới.

### 6.1. Lỗi chỉ xảy ra lúc tạo report

Có trường hợp test JVM chạy và ghi được execution data, nhưng report task thất bại khi đọc các class files mới. Điều này có thể xảy ra nếu agent và report generator khác version, hoặc report task chỉ đọc một class-file variant mà parser không hỗ trợ.

Cần tách:

- Lỗi chạy test/agent.
- Lỗi instrument classes.
- Lỗi tạo execution data.
- Lỗi phân tích class files trong report.
- Lỗi upload/import XML vào hệ phân tích.

Không coi mọi lỗi “jacocoTestReport FAILED” là lỗi test behavior.

## 7. Cập nhật JaCoCo theo JDK mục tiêu

Khi nâng JDK, cần kiểm tra release notes và compatibility matrix **của chính phiên bản JaCoCo được dự án sử dụng**. Không nên ghi cứng quy tắc “JaCoCo từ bản X hỗ trợ mọi Java sau đó”; định dạng class file có thể được cập nhật ở các release tương lai.

Quy trình kỹ thuật:

1. Ghi JDK dùng để chạy tests và compiler bytecode target.
2. Ghi class-file major của source/test/generated classes.
3. Ghi JaCoCo plugin version, agent version và report generator version.
4. Đọc tài liệu JaCoCo về hỗ trợ Java/Class file releases tương ứng.
5. Cập nhật JaCoCo lên bản phù hợp.
6. Nếu cần, cập nhật Gradle/Maven plugin để cấu hình và report tasks tương thích.
7. Dọn output cũ và chạy pipeline instrumentation/report mới.
8. Xác minh coverage report và các quality gates bằng dữ liệu thực tế.

Không tự kết luận từ **version number của Gradle** rằng JaCoCo agent đã đủ mới. Gradle cung cấp cách cấu hình plugin, còn JaCoCo toolVersion quyết định công nghệ JaCoCo được dùng ở pipeline Gradle khi cấu hình tương ứng.

## 8. Ví dụ cấu hình JaCoCo bằng Gradle

Với Gradle Java plugin:

~~~groovy
plugins {
    id 'java'
    id 'jacoco'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}

jacoco {
    // Chọn một bản JaCoCo mà release notes xác nhận hỗ trợ JDK mục tiêu.
    toolVersion = 'REPLACE_WITH_VERIFIED_JACOCO_VERSION'
}

tasks.named('test') {
    useJUnitPlatform()
    finalizedBy(tasks.named('jacocoTestReport'))
}

tasks.named('jacocoTestReport') {
    dependsOn(tasks.named('test'))

    reports {
        html.required = true
        xml.required = true
        csv.required = false
    }
}
~~~

Chuỗi `REPLACE_WITH_VERIFIED_JACOCO_VERSION` là **placeholder**, không phải một version có thể dùng nguyên vẹn. Chọn version thực tế từ release notes, kho artifact và chính sách quản lý dependency. Ví dụ cũng giả định bộ test sử dụng JUnit Platform; nếu không dùng JUnit 5, cần điều chỉnh `useJUnitPlatform()`.

Một số phiên bản Gradle cũ có cú pháp cấu hình báo cáo khác. Không copy cấu hình từ một release Gradle bất kỳ mà chưa kiểm tra wrapper trong dự án.

### 8.1. Vai trò của toolchain và options.release

- `java.toolchain` chỉ định JDK compiler/test tools theo cơ chế Gradle hỗ trợ.
- `options.release` kiểm soát source syntax, class-file target và tập API nền tảng đích khi compiler hỗ trợ.
- Test JVM có thể được Gradle cấu hình khác compiler JVM; cần kiểm tra execution environment thực tế.
- JaCoCo agent chạy cùng process test JVM, vì vậy **agent phải tương thích với runtime và bytecode thực tế được nạp**.

Nếu compiler JDK 21 tạo class file theo `--release 17`, nhiều classes của ứng dụng có major 61, nhưng các thư viện/test tools khác hoặc generated code vẫn có thể chứa class files với major cao hơn. Không nên chỉ kiểm tra một class rồi kết luận toàn bộ process cần hỗ trợ mỗi major 61.

### 8.2. Chạy các task tương ứng

Ví dụ lệnh để team dùng trong quy trình build:

~~~bash
./gradlew clean test jacocoTestReport
~~~

Lệnh minh họa quy trình, không hàm ý tests của một dự án cụ thể đã chạy hoặc đã pass. Khi nâng Java, cần kiểm tra task `test` có thực sự chạy bao nhiêu tests, report XML/HTML được tạo và đường dẫn report có đúng với cấu hình CI không.

### 8.3. Coverage verification gates

JaCoCo Gradle plugin có task `jacocoTestCoverageVerification` với các rules có thể cấu hình. Ví dụ:

~~~groovy
tasks.named('jacocoTestCoverageVerification') {
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.80
            }
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('jacocoTestCoverageVerification'))
}
~~~

Ngưỡng 0.80 là **ví dụ chính sách của dự án**, không phải khuyến nghị áp dụng cho mọi hệ thống. Cần xác minh các task nhận execution data đúng và không biến thao tác đổi JDK thành việc thay đổi coverage threshold mà không có quyết định riêng.

Một build có thể pass coverage gate vì test task bị skip hoặc report rỗng nếu rule không thực thi như mong đợi; cần quan sát cả tasks executed và dữ liệu coverage thực tế.

## 9. Ví dụ cấu hình JaCoCo trong Maven

Trong Maven, JaCoCo Maven Plugin thường cung cấp goals để:

- `prepare-agent`: chuẩn bị các thuộc tính JVM agent cho test runner.
- `report`: tạo coverage report sau khi test chạy.
- `check`: áp dụng coverage rules.
- `report-aggregate`: hỗ trợ báo cáo tổng hợp trong một số dự án multi-module.

Ví dụ đoạn cấu hình, không phải POM hoàn chỉnh:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jacoco</groupId>
      <artifactId>jacoco-maven-plugin</artifactId>
      <version>REPLACE_WITH_VERIFIED_JACOCO_VERSION</version>
      <executions>
        <execution>
          <id>prepare-coverage-agent</id>
          <goals>
            <goal>prepare-agent</goal>
          </goals>
        </execution>
        <execution>
          <id>generate-coverage-report</id>
          <phase>verify</phase>
          <goals>
            <goal>report</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Version vẫn là placeholder phải thay bằng bản được xác nhận hỗ trợ runtime/bytecode target. Để kết quả coverage đáng tin, cần phối hợp với cấu hình Maven Surefire/Failsafe và JVM forking của tests.

### 9.1. Vấn đề argLine

Khi JaCoCo chuẩn bị Java agent cho Maven tests, cấu hình test plugin phải **giữ lại JVM arguments mà JaCoCo thêm vào**. Nếu build tự ghi đè `argLine` trong Surefire/Failsafe mà không kết hợp đúng, tests vẫn có thể pass nhưng agent không chạy.

Một cấu hình minh họa nguyên tắc late property evaluation:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>@{argLine} -Xmx1g</argLine>
  </configuration>
</plugin>
~~~

Cú pháp và cơ chế `@{argLine}` cần được dùng phù hợp với version Surefire/Failsafe và JaCoCo trong dự án. Nếu property chưa được định nghĩa trong một số nhánh build, cần xử lý theo hướng dẫn plugin. Không sửa mù quáng vào mọi POM mà chưa hiểu cấu hình test JVM hiện có.

### 9.2. Không tắt JVM fork tùy tiện

Nếu test runner chạy tests trong cùng JVM với Maven process hoặc JVM agent không được gắn đúng, JaCoCo có thể không thu thập dữ liệu. Đảm bảo test process khởi tạo bằng cách tương thích với JaCoCo. Việc tests thành công không bảo đảm agent đã được khởi chạy.

### 9.3. Chạy các pha build mẫu

~~~bash
mvn clean verify
~~~

Nếu có unit/integration test tách pha, cần xét goals được gắn đúng pha và file execution data được nối vào report phù hợp. Không mặc định mục tiêu `verify` sẽ tự đo tất cả luồng integration, nhất là khi integration tests được chạy bởi plugin khác hoặc JVM/process riêng.

## 10. Coverage report trong multi-module projects

Một Java monorepo thường có nhiều subprojects:

~~~text
project/
├── api/
├── domain/
├── persistence/
├── web/
└── integration-tests/
~~~

Nếu integration tests nằm trong module riêng nhưng thực thi code của `domain` và `persistence`, báo cáo coverage theo từng module có thể thiếu dữ liệu hoặc bị tính khác mong đợi.

Các vấn đề thường gặp:

- File execution data nằm trong `integration-tests` nhưng report task của `domain` không biết đến.
- Reports trỏ tới compiled classes khác với classes test JVM đã chạy.
- Một module có code generated và source mappings riêng.
- Nhiều JVM forks ghi đè cùng file `jacoco.exec`.
- Tests chạy song song và dữ liệu được ghi ở nhiều destination khác nhau.
- Một module dùng Java release khác, khiến report parser không hỗ trợ mọi class.
- Aggregate report gom cùng class name từ nhiều variants/versions.
- CI chỉ import XML của một submodule.

Trước khi làm báo cáo tổng hợp, xác định **phạm vi coverage muốn đo**: line coverage của source production, toàn bộ module hay chỉ changed code. Sau đó thiết kế cách tập hợp execution data và class/source files.

### 10.1. Dữ liệu execution cần khớp class files

JaCoCo định danh class để liên kết probes với class files. Nếu report đọc bytecode khác với bytecode thực tế được instrument trong lúc test, coverage có thể mất hoặc báo lỗi class mismatch.

Một nguyên nhân phổ biến là vừa chạy test xong thì compilation/shading/generation viết lại class files trước khi report task đọc chúng. Vì thế, pipeline cần thống nhất thời điểm tạo class, instrument, chạy tests và report.

### 10.2. Không merge dữ liệu tùy tiện giữa các version

Dữ liệu `.exec` là dạng riêng của JaCoCo; khi kết hợp report từ nhiều processes hoặc phiên bản JaCoCo, cần dùng công cụ và phiên bản tương thích. Không đơn giản nối nhị phân các file hoặc coi XML report là execution data có thể merge tương đương.

Nếu CI nâng JaCoCo trong giai đoạn migration, cần kiểm tra bước upload/merge/report tổng hợp có dùng cùng protocol/format mong đợi.

## 11. Coverage khi Java bổ sung cấu trúc ngôn ngữ mới

Java hiện đại có records, sealed classes, switch expressions, pattern matching, lambda, text blocks và những tính năng khác. Compiler có thể sinh bytecode khác mã nguồn mà lập trình viên nhìn thấy.

Ví dụ record:

~~~java
public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Order id must not be blank");
        }
    }
}
~~~

Compiler có thể phát sinh methods và bytecode cần thiết cho record theo đặc tả. Một công cụ coverage đủ mới có thể có logic **filter** bỏ một số bytecode được compiler sinh mà người viết source không trực tiếp kiểm soát. Logic filter và report có thể thay đổi giữa các phiên bản JaCoCo.

### 11.1. Coverage percentage có thể đổi dù tests không đổi

Khi nâng compiler hoặc JaCoCo, cùng source và tests có thể dẫn tới tỷ lệ coverage khác do:

- Compiler phát bytecode khác.
- Công cụ hỗ trợ thêm filter cho synthetic/generated constructs.
- Branch counting thay theo bytecode structure.
- Debug information hoặc source line mapping khác.
- Java language feature mới thay dạng nhánh.
- Exclusions/report scope được cấu hình khác.

Điều đó không nhất thiết có nghĩa chất lượng test đã tốt hơn hoặc kém hơn. Cần đối chiếu số lượng tests, dữ liệu đầu vào, generated bytecode và report scope.

### 11.2. Text blocks và constant folding

Một text block hoặc biểu thức compile-time constant có thể tạo ít bytecode hơn người đọc source tưởng tượng. Coverage của một dòng source không phải phép đếm số token hoặc số statement hiển thị trên dòng đó.

### 11.3. Branch coverage của switch và pattern

Một switch expression có thể dẫn tới bytecode phức tạp hơn switch statement cũ. JaCoCo sử dụng bytecode để suy ra nhánh theo mô hình của nó, không nhất thiết đếm mọi `case` trong source như một đơn vị tương đương. Khi phát hiện branch coverage khác baseline, cần đọc report và biết công cụ đang đo gì.

## 12. Generated code, Lombok và coverage filters

Trong một project dùng annotation processors hoặc generator:

~~~text
src/main/java/            source viết tay
build/generated/sources/  source được sinh
build/classes/            compiled output
~~~

Một số generated classes có thể làm coverage denominator tăng lớn. Nếu báo cáo được dùng để đo hiệu quả tests của business code, nhóm cần quyết định có tính generated source không.

Một số công cụ có thể nhận diện/filter mã được sinh dựa vào bytecode patterns hoặc annotations tương ứng, nhưng hành vi thay đổi theo phiên bản công cụ. Không mặc định mọi annotation có tên `Generated` đều khiến tất cả tools bỏ qua code giống nhau.

### 12.1. Exclusion có phạm vi rõ ràng

Các lựa chọn có thể gồm:

- Chỉ đo packages đại diện cho production business code.
- Loại generated classes khỏi report theo patterns có giải thích.
- Duy trì report riêng cho generated code quan trọng nếu cần.
- Dùng test coverage trên code mà organization thực sự chịu trách nhiệm.

Nếu generated client hoặc mapper là phần quyết định chất lượng sản phẩm, loại bỏ hoàn toàn khỏi test strategy có thể không phù hợp. **Coverage exclusion chỉ thay report, không xác minh correctness**.

### 12.2. Lombok và AST transformations

Một công cụ như Lombok có thể ảnh hưởng code mà compiler tạo ra. Khi nâng JDK, cần kiểm tra cả Lombok/processor version và JaCoCo version. Một lỗi ở compiler plugin/AST transformation có thể xuất hiện trước khi coverage instrumentation bắt đầu.

Không quy mọi line coverage bất thường của Lombok-generated methods cho JaCoCo; có thể là thay đổi trong generated bytecode do compiler hoặc processor.

## 13. Công cụ phân tích tĩnh: không phải tất cả đều đọc class file

**Static analysis** là kiểm tra chương trình mà không cần thực thi toàn bộ code path nghiệp vụ. Nhưng cách công cụ thực hiện rất đa dạng.

| Công cụ/nhóm | Đầu vào chính | Kiểu phân tích | Rủi ro nâng Java |
|---|---|---|---|
| JaCoCo | Bytecode + execution data | Runtime coverage instrumentation/report | Không hỗ trợ class-file version, report mapping |
| SpotBugs | Compiled Java bytecode | Bytecode static analysis | Parser không hiểu class file, detector version lỗi |
| PMD Java | Java source/AST | Source rules và cú pháp | Parser chưa hỗ trợ language level mới |
| Checkstyle | Java source/AST grammar | Style và structural checks | Grammar/token mới chưa được nhận diện |
| Error Prone | javac compilation/type model | Compiler-integrated bug checking | Version plugin không hợp JDK/javac APIs |
| SonarJava / quality analyzer | Source, semantic model và tùy pipeline bytecode | Rules/semantic analysis | Analyzer version và JDK support mismatch |
| Semgrep và các source-based analyzers | Source/AST/patterns tùy ngôn ngữ | Pattern/semantic checks | Grammar, rule engine, language version |
| Custom Java agent/ASM tool | Loaded class files/bytecode | Instrumentation hoặc transformation | Bytecode parser không hỗ trợ major mới |

Bảng là mô hình khái quát; một sản phẩm có thể kết hợp source và bytecode hoặc thay kiến trúc giữa các release. Khi đánh giá tool, đọc tài liệu của **version cụ thể** chứ không suy diễn mọi version vận hành giống nhau.

### 13.1. Source parser failure

Nếu PMD hoặc Checkstyle chưa hiểu cú pháp switch pattern/record, tool có thể lỗi parse ngay cả khi javac mới biên dịch source thành công. Trong trường hợp đó, thay ASM chưa chắc liên quan; cần nâng **language parser** của analyzer.

### 13.2. Bytecode parser failure

Nếu SpotBugs hoặc JaCoCo gặp `Unsupported class file major version N`, cần kiểm tra thư viện đọc bytecode và version analyzer. Nâng source grammar tool khác không giải quyết lỗi này.

### 13.3. Compiler-integrated failure

Error Prone hoặc một plugin javac có thể phụ thuộc vào compiler internals/lifecycle. JDK mới có thể làm plugin không load hoặc báo `IllegalAccessError`, `NoSuchMethodError`, `NoSuchFieldError`. Vấn đề không nhất thiết là parser source hoặc ASM mà là **tương thích giữa plugin và phiên bản javac**.

## 14. SpotBugs: kiểm tra bytecode với parser tương thích

SpotBugs hoạt động chủ yếu trên class files và cần hiểu cấu trúc bytecode của những module được quét.

Một workflow thường là:

~~~text
Compile source
    |
    v
Compiled .class / JAR
    |
    v
SpotBugs analyzer + detectors
    |
    v
Bug reports XML/HTML/other
    |
    v
CI quality gate / triage
~~~

Các tình huống cần điều tra:

- Công cụ cũ không hiểu major version mới.
- Thiếu dependency classpath khiến type resolution thiếu.
- Analyzer hoặc plugin Gradle/Maven wrapper không tương thích với JDK mới.
- Custom detector plugin được biên dịch cho API version khác.
- New compiler output thay đổi pattern phát hiện, tăng/giảm findings.
- Generated classes, test classes hoặc exclusions bị đưa vào scope khác trước.

Ví dụ lệnh Gradle tham khảo khi dự án đã cài plugin tương ứng:

~~~bash
./gradlew spotbugsMain
~~~

`spotbugsMain` không phải task mặc định của mọi Gradle Java project; nó chỉ xuất hiện khi plugin SpotBugs tương ứng được áp dụng và cấu hình phù hợp. Không nên viết tài liệu CI yêu cầu task mà dự án chưa có.

### 14.1. Không xem zero findings là bằng chứng đủ

Nếu analyzer bỏ qua module vì classpath sai, quét một source set rỗng hoặc báo lỗi bị chuyển thành warning, report có thể ít findings hơn mà chất lượng code không thay đổi. Khi nâng JDK, cần xác nhận số classes được phân tích, rules/plugins bật và exit status.

## 15. Checkstyle, PMD và parser cú pháp Java

Các công cụ source-based không nhất thiết cần đọc class-file version, nhưng vẫn phải hiểu **cú pháp Java mà source code sử dụng**.

Ví dụ:

~~~java
public record Account(String id) {
}

public sealed interface PaymentState
        permits Pending, Completed {
}

public record Pending(String key) implements PaymentState {
}

public record Completed(long transactionId)
        implements PaymentState {
}
~~~

Nếu parser cũ chỉ hỗ trợ Java 11, nó có thể không nhận `record` hoặc `sealed interface`. Khi đó việc ứng dụng compile trên Java 21 không tự làm Checkstyle/PMD version cũ phân tích được.

Các dấu hiệu:

- ParseException/unexpected token.
- AST node kind không được rule/plugin hỗ trợ.
- Rule viết riêng cast node sai khi xuất hiện construct mới.
- Cấu hình language level mặc định khác source target.
- Analyzer upgrade thay rule defaults hoặc mức độ severity.

### 15.1. Nâng analyzer có thể làm số findings đổi

Một bản PMD/Checkstyle mới có thể:

- Thêm rules mới hoặc đổi rule identifiers.
- Hỗ trợ node mới.
- Thay behavior của một số AST visitors.
- Đổi mặc định severity hoặc phạm vi files.
- Xóa rules đã deprecated.

Vì vậy, baseline findings cần được đối chiếu với **rule set, analyzer version, source scope** và Java language level, không chỉ tổng số lỗi.

### 15.2. Quy tắc riêng của dự án

Custom checks/PMD rules cũng là một dependency. Nếu chúng dùng AST internals hoặc API plugin cũ, một analyzer mới có thể làm rule lỗi dù core engine đã hỗ trợ Java mới. Cần kiểm tra plugin/rules compatibility riêng.

## 16. Error Prone và javac plugins

Các công cụ chạy trong quá trình javac có đặc tính khác source scanner độc lập. Chúng có thể dùng compiler trees, type models hoặc APIs gắn với một phiên bản javac.

Khi nâng JDK:

- Plugin cần tương thích javac API/lifecycle của JDK đó.
- Build plugin dùng để kết nối với javac cũng phải tương thích.
- Các rule providers có thể cần biên dịch lại theo API/plugin version.
- JVM module boundaries có thể ảnh hưởng khả năng truy cập compiler internals.
- Toolchain Gradle/Maven có thể dùng JDK khác với daemon/build process.

Không nên dùng `--add-exports` hàng loạt để che lỗi `NoSuchFieldError` của compiler plugin. Nếu internal field đã đổi, mở quyền truy cập không làm nó xuất hiện trở lại. Tìm bản Error Prone/plugin đã được phát hành cho JDK mục tiêu hoặc thay cách tích hợp.

## 17. Sonar và pipeline import coverage

Một pipeline phân tích chất lượng thường có hai bước riêng:

~~~text
Run tests + JaCoCo agent
       |
       v
Generate JaCoCo XML report
       |
       v
Quality analyzer / Sonar scanner
       |
       v
Dashboard và quality gate
~~~

Khi nâng JDK, nhiều điểm có thể lỗi độc lập:

- JaCoCo agent không instrument được Java bytecode mới.
- JaCoCo report task không đọc được class files.
- XML report không được tạo vì tests bị skip.
- Scanner không tìm được XML report ở đường dẫn mới.
- Analyzer server hoặc plugin không hỗ trợ source language level mới.
- Scanner JVM cần version khác với build/test JVM.
- Source paths trong XML không khớp structure/module của scanner.
- Quality gate import thiếu module hoặc trùng dữ liệu.

**Một scanner “SUCCESS” không bảo đảm coverage đã được import.** Cần nhìn thông báo report paths và dashboard thực tế. Nếu coverage trở về 0 hoặc “not available” sau migration, phải xác định đó là lỗi instrument, report hay import.

### 17.1. JaCoCo XML và execution data khác nhau

`jacoco.exec` thường là execution data ở định dạng nội bộ của JaCoCo; XML report được tạo từ execution data + classes + sources. Các hệ thống báo cáo chất lượng thường nhập XML report, không thể dùng file exec như XML chỉ vì cả hai là coverage artifacts.

Khi chuyển pipeline, cần kiểm tra loại file, schema/version phù hợp và đường dẫn được cấu hình rõ ràng.

## 18. Tương thích ASM và những bytecode tools khác

JaCoCo không phải thành phần duy nhất sử dụng ASM hoặc công nghệ đọc bytecode. Nhiều thư viện có thể chứa ASM riêng hoặc phiên bản đã được shade.

Ví dụ hệ sinh thái:

- Byte Buddy.
- ASM trực tiếp hoặc thông qua plugin.
- Mocking frameworks và inline mock maker.
- AOP/weaving tools.
- Spring proxy/instrumentation components.
- Coverage agents và Java profilers.
- Bytecode optimizers, obfuscators và shad ers.
- Testing utilities tạo class động.

Một tool có thể báo lỗi khi đọc classes do compiler mới tạo, hoặc khi đọc dynamically generated classes chứa construct không được hỗ trợ. Nâng duy nhất JaCoCo có thể chưa đủ nếu một mocking/agent library khác vẫn chứa parser cũ.

### 18.1. Các agents chạy cùng nhau

JVM có thể nhận nhiều `-javaagent`. Thứ tự agent, cơ chế retransformation và tương tác giữa các transformers có thể ảnh hưởng bytecode cuối cùng.

Ví dụ:

~~~text
JVM startup
   |
   +-- JaCoCo agent
   +-- APM / tracing agent
   +-- Mocking or test instrumentation
   |
   v
Class loading and transformation chain
   |
   v
Application / tests
~~~

Nếu lỗi chỉ xảy ra khi bật coverage, cần thử tách các agents trong môi trường test để xác định thành phần xung đột. Không làm trên production một cách tùy tiện vì có thể tác động giám sát và bảo mật.

### 18.2. Không tự ép ASM version bằng dependency override

Một thư viện có thể shade ASM nội bộ; thêm `org.ow2.asm:asm` bản mới vào application classpath chưa chắc thay ASM đang được sử dụng trong agent. Việc ép một transitive version cũng có thể phá ABI của thư viện cha.

Cách tốt hơn là nâng **component sở hữu parser** theo bản tương thích được phát hành và xác minh dependency graph thực tế.

## 19. Gradle daemon, compiler toolchain và test JVM

Trong một Java migration, có thể có các JVM khác nhau:

~~~text
Gradle daemon JVM
       |
       +--> JavaCompile toolchain (javac)
       |
       +--> Test JVM (JaCoCo agent)
       |
       +--> Static analyzer worker JVM
       |
       +--> Packaging / codegen plugin
~~~

Một bản Gradle có thể cần JDK tối thiểu nhất định để chạy daemon, trong khi compiler toolchain có thể được chọn riêng. Test tasks cũng có thể cấu hình Java launcher hoặc forked JVM khác.

Ví dụ:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cấu hình minh họa ý định chạy tests với Java 21. API/cú pháp cần phù hợp Gradle wrapper và plugin đã cài. Thực tế, một số cấu hình toolchain có thể tự áp cho tests, nhưng khi chẩn đoán nên **xác minh JVM mà tests thực sự dùng** chứ không chỉ suy ra từ compile task.

### 19.1. Vì sao tests chạy Java cũ nhưng bytecode Java mới?

Nếu compile target cao hơn test JVM, test startup có thể ném `UnsupportedClassVersionError` trước khi JaCoCo instrument. Đây là mismatch của runtime, không phải thiếu khả năng đọc class file của JaCoCo.

Nếu test JVM mới nhưng JaCoCo agent cũ, lỗi có thể đến từ agent. Hai trường hợp phải được phân biệt bằng stack trace và log JVM.

## 20. Maven compiler, Surefire/Failsafe và Java agent

Trong Maven, thường có ba điểm cần kiểm tra:

1. Maven JVM chạy plugins.
2. Maven Compiler Plugin sử dụng compiler/release mục tiêu.
3. Surefire/Failsafe tạo hoặc sử dụng test JVM và nhận JaCoCo agent arguments.

Ví dụ một cấu hình compiler release:

~~~xml
<properties>
  <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Đây là fragment thuộc POM, không phải file Maven đầy đủ. Nếu đang chạy Maven bằng JDK cũ, compiler release mới không được hỗ trợ chỉ vì property đã khai báo. Cần compiler JDK phù hợp.

Nếu tests chạy nhưng coverage không xuất hiện, tìm trong logs JVM arguments do `jacoco:prepare-agent` thêm, các cấu hình `argLine`, fork settings và report phase. Không nên giảm coverage gate để che việc agent không chạy.

## 21. Preview features và toolchain support

Một số nhóm thử nghiệm Java preview features. Khi đó cần quan sát hai vấn đề riêng:

- Compiler/runtime phải được bật preview theo release phù hợp.
- Parser/transformer/analyzer cần hỗ trợ bytecode và source constructs xuất hiện.

Ví dụ ý niệm về Java 21:

~~~bash
javac --enable-preview --release 21 Example.java
java --enable-preview Example
~~~

Nếu ứng dụng dùng preview trong bản release nhất định, một công cụ static analysis có thể chưa nhận AST node mới dù JDK biên dịch được. JaCoCo/ASM cũng phải hỗ trợ class-file version và cấu trúc liên quan.

Không kết luận “tool hỗ trợ Java 21” là chắc chắn hỗ trợ mọi preview feature của Java 21. Đọc release notes và thử trên các class cụ thể đang dùng preview.

### 21.1. Preview và phát hành production

Preview features có vòng đời và điều kiện tương thích riêng. Việc phát hành sản phẩm phụ thuộc preview làm tăng chi phí nâng JDK tiếp theo; cần ghi rõ lựa chọn đó và bảo đảm tests/agents/analyzers tương thích.

## 22. Multi-release JAR và class-file variant

Một multi-release JAR có thể chứa:

~~~text
META-INF/MANIFEST.MF
com/example/Util.class
META-INF/versions/11/com/example/Util.class
META-INF/versions/17/com/example/Util.class
META-INF/versions/21/com/example/Util.class
~~~

JVM có thể chọn variant phù hợp runtime theo cơ chế multi-release JAR. Static analyzer hoặc report generator có thể có cách chọn variant riêng; nếu không hỗ trợ đầy đủ, kết quả coverage hoặc findings có thể khác chạy runtime.

Các câu hỏi cần trả lời:

- Tool đang đọc base class hay version-specific class?
- Variant được biên dịch theo major nào?
- JVM test thực sự nạp variant nào?
- Source mapping cho variant đó nằm ở đâu?
- Report có đang gom nhiều variants thành một logical class không?

Khi nâng từ JDK 17 lên JDK 21, một JAR có thể bắt đầu nạp variant Java 21, khiến agent gặp class-file major mới dù source ứng dụng không đổi.

## 23. Kiểm tra đường dẫn source và debug information

Line coverage cần ánh xạ bytecode về source. Nếu compile thiếu hoặc khác debug information, report có thể hiển thị class/method coverage nhưng thiếu line mapping hoặc hiện “no source”.

Các nguyên nhân khác:

- Source files không có tại nơi report task tìm.
- Class name/package khác source layout.
- Generated source directory không được khai báo.
- Compiler/code generator thay đổi line number tables.
- Report đọc original classes khác với classes đã chạy.
- Build artifact bị obfuscate/shade sau khi tests thu thập data.

Việc cấu hình source directories phải phù hợp build project. Đừng tăng số dòng coverage bằng cách map source sai hoặc bỏ qua các class không mong muốn mà không có quyết định về report scope.

## 24. Phân biệt lỗi instrument và lỗi test behavior

Khi `test` failed, một build log có thể chứa cả thông báo từ JaCoCo và assertion failure. Cần xác định root cause.

| Biểu hiện | Giai đoạn khả dĩ | Cách xử lý |
|---|---|---|
| `Error while instrumenting ...` | Java agent/class transform | Kiểm tra JaCoCo/ASM version, class major và agents |
| `Unsupported class file major version N` trong analyzer | Bytecode parser | Nâng công cụ sở hữu parser, kiểm tra bytecode |
| `UnsupportedClassVersionError` | Test JVM không nạp được class | Đồng bộ runtime/target |
| `ClassFormatError` | Bytecode invalid hoặc transform lỗi | Kiểm tra agent ordering, compiler/transformers |
| Test assertion failed | Nghiệp vụ hoặc test logic | Điều tra behavior change; không quy cho coverage trước |
| Report file không tồn tại | Task/report pipeline | Test execution, destination, report task, paths |
| Coverage = 0 | Không có/không khớp data hoặc import | Agent args, exec files, class mapping, scanner |
| Static analyzer parse error | Source grammar/tool | Nâng parser và rule plugins |
| Compiler plugin `IllegalAccessError` | Javac internals/module boundary | Nâng plugin tương thích JDK |
| Findings tăng mạnh | Analyzer/rules/scope thay | So baseline, rule set, parser version |

Một cách chẩn đoán có giá trị là chạy tests với và không có coverage trong một môi trường **kiểm thử** để phân biệt lỗi của instrumentation với lỗi ứng dụng; nhưng cần giữ test inputs, runtime, dependency graph và environment không đổi để so sánh có ý nghĩa.

## 25. Không đánh đồng coverage với mức độ kiểm thử chất lượng

Coverage là một chỉ số của việc các đoạn bytecode được kích hoạt, không phải bảo đảm chương trình đúng. Ví dụ:

~~~java
public int divide(int total, int count) {
    return total / count;
}
~~~

Một test chạy `divide(10, 2)` có thể tạo line coverage cao nhưng chưa kiểm tra `count == 0`, overflow, dấu số hoặc kỳ vọng nghiệp vụ.

Với migration, một nguy cơ là team tập trung làm coverage percentage “trở lại như cũ” mà không xác nhận các assertions còn hiệu lực. Nếu JDK hoặc library đổi semantics, tests cần kiểm tra behavior đúng, không chỉ execution count.

### 25.1. Kết hợp các lớp chất lượng

- Unit tests kiểm chứng logic.
- Integration tests kiểm chứng dependency/framework/runtime.
- JaCoCo đo execution coverage trong những tests được chạy.
- Static analysis phát hiện một số patterns lỗi, style hoặc code smells.
- Dependency/security analysis tìm rủi ro thư viện.
- Performance tests tìm regression.
- Runtime smoke tests kiểm tra deployment thực tế.

Không lớp nào thay thế hoàn toàn lớp còn lại. Java upgrade an toàn cần tổng hợp bằng chứng.

## 26. Cách xác định công cụ có hỗ trợ class-file major mới

Đối với JaCoCo hoặc bytecode analyzer, dùng quy trình:

1. Xác định JDK mục tiêu và bytecode compiler thực sự tạo.
2. Đọc class-file major từ một tập classes đại diện.
3. Xác định version tool và dependencies có liên quan.
4. Đọc release notes/compatibility matrix của tool, bao gồm preview khi áp dụng.
5. Xác nhận tool có hỗ trợ đọc **định dạng class file**, không chỉ chạy JVM.
6. Thử phân tích/instrument chính classes từ dự án.
7. Kiểm tra output artifact/report, không chỉ exit code.
8. Ghi version pin và bằng chứng trong migration report.

Không tự đoán “ASM bản N chắc chắn hỗ trợ Java M” dựa vào version số học. Khả năng hỗ trợ được bổ sung qua từng release và có thể khác nhau giữa experimental và official support.

Nếu tool shade một bản ASM riêng, nâng `org.ow2.asm` trên application classpath chưa chắc thay implementation mà tool đang dùng.

## 27. Bảng kiểm kê phiên bản tooling

Một migration report có thể dùng bảng:

| Thành phần | Version hiện tại | JDK chạy tool | Input bytecode/source | Trạng thái |
|---|---|---|---|---|
| Gradle/Maven wrapper | Ghi version | Build JVM | Project configuration | Cần xác minh |
| javac / compiler plugin | Ghi version | Compiler JDK | Source level/`--release` | Cần xác minh |
| JaCoCo agent | Ghi version | Test JVM | Class-file major | Cần xác minh |
| JaCoCo report plugin | Ghi version | Build JVM | Exec data + class/source files | Cần xác minh |
| SpotBugs | Ghi version | Analyzer JVM | Compiled classes | Cần xác minh |
| PMD | Ghi version | Analyzer JVM | Java source syntax | Cần xác minh |
| Checkstyle | Ghi version | Analyzer JVM | Java grammar/tokens | Cần xác minh |
| Error Prone | Ghi version | Javac JVM | Compiler internals/type model | Cần xác minh |
| Sonar scanner/analyzer | Ghi version | Scanner JVM | Source/bytecode/coverage XML | Cần xác minh |
| Mocking/bytecode agent | Ghi version | Test JVM | Dynamically loaded/created classes | Cần xác minh |

Không có cột nào nên được tự đánh PASS chỉ vì dự án build trước migration. Cần ghi **kịch bản đã chạy và bằng chứng** cho runtime JDK mục tiêu.

## 28. Ma trận test/tooling trong Java migration

Ví dụ hai JDK cần hỗ trợ:

| Bước | Java 17 | Java 21 | Bằng chứng |
|---|---|---|---|
| Compile source với release mục tiêu | PASS/FAIL | PASS/FAIL | Compiler logs |
| Chạy unit tests không coverage | PASS/FAIL | PASS/FAIL | Test reports |
| Chạy tests có JaCoCo agent | PASS/FAIL | PASS/FAIL | Agent logs |
| Tạo JaCoCo XML/HTML report | PASS/FAIL | PASS/FAIL | Report artifacts |
| Coverage gate | PASS/FAIL | PASS/FAIL | Rule evaluation |
| SpotBugs trên compiled classes | PASS/FAIL | PASS/FAIL | Analyzer logs/findings |
| PMD/Checkstyle với source syntax | PASS/FAIL | PASS/FAIL | Static reports |
| Error Prone/compiler plugin | PASS/FAIL | PASS/FAIL | Compilation results |
| Sonar/quality analyzer import | PASS/FAIL | PASS/FAIL | Scanner logs/dashboard |
| Multi-module aggregate coverage | PASS/FAIL | PASS/FAIL | Combined report |
| Preview/MR-JAR variant nếu có | PASS/FAIL | PASS/FAIL | Variant-specific tests |
| Packaging và runtime smoke tests | PASS/FAIL | PASS/FAIL | Image/JVM logs |

Các giá trị PASS/FAIL là placeholder. Với hệ thống chỉ cam kết một JDK, ma trận có thể nhỏ hơn. Nếu vừa thay JDK vừa thay JaCoCo, nên lưu một baseline có version của từng tool để giải thích coverage deltas.

## 29. Ví dụ lỗi thực tế dạng giả định

Giả sử hệ thống trước đây dùng Java 17 và JaCoCo phiên bản cũ. Sau khi build bằng Java 21, pipeline báo:

~~~text
> Task :orders-service:test FAILED
java.lang.instrument.IllegalClassFormatException:
Error while instrumenting com/example/orders/OrderService
Caused by: java.lang.IllegalArgumentException:
Unsupported class file major version 65
~~~

Một cách điều tra:

1. Xác nhận `OrderService.class` có major 65 bằng `javap -verbose`.
2. Xem JaCoCo agent version đang được gắn vào Test JVM.
3. Xác nhận test JVM đang chạy Java 21 hoặc runtime phù hợp.
4. Đọc release notes của JaCoCo để chọn bản hỗ trợ major 65.
5. Cập nhật JaCoCo và plugin cần thiết, pin version.
6. Chạy lại tests có instrumentation.
7. Tạo report XML/HTML và kiểm tra line/branch coverage.
8. Xác nhận quality analyzer import đủ dữ liệu.

Không nên đổi `--add-opens java.base/...` để xử lý lỗi major 65. Lỗi liên quan định dạng class file, không phải reflective access vào package bị đóng.

### 29.1. Tình huống lỗi kế tiếp: Coverage về 0

Sau khi JaCoCo agent được nâng, tests pass nhưng dashboard coverage về 0.

Khả năng:

- Test runner không nhận `-javaagent`.
- JaCoCo exec data file không được ghi.
- Report task không chạy hoặc đọc sai path.
- XML report không được import vào scanner.
- Class files report không khớp những classes đã chạy.
- Exclusions quá rộng.
- Multi-module aggregation thiếu module.

Đây là một **lỗi pipeline khác**; không nên tiếp tục nâng JaCoCo version một cách ngẫu nhiên nếu instrumentation đã thành công.

## 30. Quản lý quality gate khi compiler làm đổi coverage

Khi nâng JDK, JaCoCo và analyzer, percentage hoặc số findings có thể đổi dù tests giống nhau.

Để phân biệt nguyên nhân:

- Lưu report baseline của JDK và JaCoCo cũ.
- Ghi compiler target, tool versions, excludes, rules và source scope.
- So sánh số tests được thực thi.
- So sánh classes/instructions/branches được đưa vào mẫu số.
- Kiểm tra synthetic/generated code filters.
- Kiểm tra source mapping và original class files.
- Đánh giá riêng các thay đổi về rules hoặc severity của static analyzers.
- Nếu cần chỉnh threshold, phải có quyết định chất lượng rõ chứ không lặng lẽ nới gate.

Một chênh lệch coverage nhỏ sau khi compiler đổi bytecode không tự chứng minh test regression; nhưng **không được giả định** mọi chênh lệch là do tool. Có thể thực sự đã mất tests hoặc thay code paths.

## 31. Generated classes, instrumented artifacts và reproducibility

Trong Java migration, code generation cũng thay đổi output. Một annotation processor cập nhật có thể sinh methods, getters, builders hoặc model khác trước.

Do đó, một coverage report đáng tin cần có:

1. Build inputs và code generator versions.
2. JDK compiler và `--release`.
3. Class files thực sự nạp trong tests.
4. JaCoCo agent/report versions.
5. Execution data với các JVM forks tương ứng.
6. Source mapping và classes gốc phù hợp.
7. Exclusions được review.
8. Version của quality analyzer import.

Không nên tạo report bằng class files của build khác hoặc artifact bị transform sau khi execution data được thu thập. Nếu có shading hoặc obfuscation, xác định lúc nào instrumentation xảy ra và báo cáo đang ánh xạ tới class nào.

## 32. Tối ưu quy trình sửa lỗi theo giai đoạn

Khi pipeline nâng Java thất bại, nên tránh sửa nhiều công cụ cùng một lúc. Một cách phân tầng:

### Giai đoạn A: Chạy Java không instrumentation

Xác nhận compiler, runtime và tests cơ bản tương thích. Nếu test JVM không nạp được class, hãy giải quyết runtime/bytecode mismatch trước khi điều tra JaCoCo.

### Giai đoạn B: Bật JaCoCo agent

Xác nhận test JVM nạp agent, classes được instrument và tests vẫn chạy. Đọc lỗi chính xác ở class nào, major bao nhiêu và transformer nào thất bại.

### Giai đoạn C: Tạo JaCoCo reports

Xác nhận execution data được ghi và XML/HTML báo cáo đúng module. So sánh dữ liệu với baseline.

### Giai đoạn D: Chạy các static analyzers

Tách bytecode analyzers như SpotBugs khỏi source parsers như PMD/Checkstyle và compiler-integrated tools. Mỗi loại cần version tương thích riêng.

### Giai đoạn E: Tích hợp quality dashboard

Xác nhận scanner import đúng XML, các rules/scopes không thay ngoài ý muốn và quality gate phản ánh dữ liệu mới.

### Giai đoạn F: Test cross-JDK và deployment

Nếu hỗ trợ nhiều JDK, chạy lại ma trận. Kiểm tra agent, native libraries và instrumentation trong environment gần production, không chỉ trên laptop.

Tách các giai đoạn giúp xác định chính xác dependency/tool nào cần nâng, tránh biến migration thành nhiều lần override phiên bản không có bằng chứng.

## 33. Checklist điều tra khi gặp lỗi coverage/static analysis

- [ ] Đã xác định JDK thực sự chạy build, javac, test và analyzer.
- [ ] Đã đọc class-file major/minor của classes gây lỗi.
- [ ] Đã xác minh `--release`, source level và preview flags.
- [ ] Đã biết JaCoCo agent version và report plugin version.
- [ ] Đã xác minh hỗ trợ class file qua release notes của công cụ.
- [ ] Đã kiểm tra ASM/bytecode tool khác, kể cả bản shaded.
- [ ] Đã phân biệt lỗi JVM với lỗi parser của analyzer.
- [ ] Đã kiểm tra test JVM có gắn JaCoCo agent thật không.
- [ ] Đã xác minh execution data tồn tại và report task sử dụng đúng.
- [ ] Đã xác nhận XML/HTML được tạo và dashboard import thành công.
- [ ] Đã rà multi-module aggregate và report class/source mapping.
- [ ] Đã xem source parser hỗ trợ cú pháp Java mới.
- [ ] Đã kiểm tra custom analyzer rules và compiler plugin compatibility.
- [ ] Đã kiểm tra preview/MR-JAR/generated classes nếu có.
- [ ] Đã so sánh test count, coverage scope và rule set với baseline.
- [ ] Đã có kết quả tests không có coverage để tách lỗi behavior và instrumentation.
- [ ] Đã lưu version pin, artifacts, logs và owner của các fixes.

Danh sách là hướng dẫn cho bài học, không phải xác nhận các bước đã chạy trên một repository cụ thể.

## 34. Những sai lầm cần tránh

### 34.1. Nhầm “JVM hỗ trợ Java 21” thành “JaCoCo hỗ trợ bytecode Java 21”

JVM có khả năng nạp class major 65 không chứng minh JaCoCo/ASM version cũ có thể parse/instrument định dạng đó. Cần support matrix riêng.

### 34.2. Chỉ nâng JaCoCo mà bỏ qua mocking/agent tools

Một Java agent khác cũng có thể chứa ASM hoặc bytecode parser cũ. Lỗi chỉ xảy ra khi coverage bật có thể do tương tác transformers, không chỉ do agent coverage.

### 34.3. Thêm --add-opens cho lỗi unsupported class-file major

Module exports/opens liên quan access, không sửa parser thiếu hỗ trợ class-file version.

### 34.4. Thấy tests pass thì cho rằng JaCoCo chạy

Tests có thể không gắn agent; coverage data rỗng. Phải xem JVM args, exec data và report outputs.

### 34.5. Thấy XML report có file thì tin mọi số liệu

Report có thể từ build trước, scope thiếu module hoặc không khớp classes. Cần dọn output khi điều tra và xác minh timestamp/source mapping/artifact.

### 34.6. Dùng coverage cao thay cho assertions

Code đã được chạy không đồng nghĩa code đúng. Vẫn cần unit, integration và behavior tests.

### 34.7. Tắt toàn bộ static analysis để CI xanh

Điều đó che lỗi source/bytecode compatibility và làm mất kiểm soát chất lượng. Nên nâng tool và ghi ngoại lệ có owner nếu cần trì hoãn ngắn hạn.

### 34.8. Giảm coverage gate ngay khi nâng JDK

Coverage percentage thay có thể do compiler filters, nhưng cũng có thể do tests bị skip. Điều tra nguyên nhân trước khi quyết định thay threshold.

### 34.9. Ép một bản ASM bên ngoài vào mọi dependency

Nhiều tool shade parser hoặc yêu cầu API tương ứng; override không có compatibility evidence có thể gây lỗi mới.

### 34.10. Chỉ test một class file

Một dự án có generated classes, multi-release JAR hoặc dependency ở major khác. Cần quét tập class files thực tế mà các analyzers đọc.

## 35. Mẫu báo cáo trạng thái tương thích tooling

~~~yaml
javaMigrationTooling:
  project: "orders-service"
  targetJdk: "21"
  compilerRelease: "21"
  observedClassFileMajor: 65
  build:
    tool: "Gradle"
    version: "record-real-version"
  jacoco:
    agentVersion: "record-real-version"
    reportVersion: "record-real-version"
    classFileSupportVerified: false
    executionDataVerified: false
    xmlReportVerified: false
  staticAnalysis:
    spotbugs:
      version: "record-real-version"
      bytecodeParseVerified: false
    pmd:
      version: "record-real-version"
      syntaxSupportVerified: false
    checkstyle:
      version: "record-real-version"
      syntaxSupportVerified: false
  scanner:
    xmlImportVerified: false
  tests:
    plainUnitTestsPassed: false
    instrumentedTestsPassed: false
    integrationTestsPassed: false
  owner: "platform-team"
  status: "under-investigation"
~~~

Giá trị trên chỉ minh họa biểu mẫu. Các mục `false` hoặc `under-investigation` không mang ý nghĩa một môi trường thật đã thất bại; cần điền theo kết quả và evidence của project cụ thể.

Một báo cáo hoàn chỉnh nên có link build logs, JaCoCo HTML/XML, số tests, tool versions, class-file versions, screenshot/đường dẫn dashboard khi cần, cũng như quyết định xử lý và kế hoạch rollout.

## 36. Nguyên tắc tổng kết

- **Class-file version là điều kiện tương thích giữa compiler, JVM và bytecode tools.** Không chỉ JDK runtime mới phải đọc được bytecode; JaCoCo và analyzers cũng phải hiểu định dạng đó.
- **Tool chạy được trên JDK mới không đồng nghĩa tool phân tích được class files do JDK mới tạo.** Phân biệt runtime compatibility và input-format compatibility.
- **JaCoCo instrument bytecode và thu execution data**, sau đó kết hợp classes/sources để tạo báo cáo. Tests chạy thành công chưa chắc có dữ liệu coverage.
- **JaCoCo/ASM phải hỗ trợ bytecode target thực tế.** Cần tra release notes/version matrix và thử trên classes của project, không suy đoán.
- **Source analyzers, bytecode analyzers và javac-integrated tools có rủi ro khác nhau.** PMD/Checkstyle cần grammar; SpotBugs cần bytecode parser; Error Prone cần compiler integration phù hợp.
- **Coverage tỷ lệ có thể đổi khi compiler/tool filters đổi.** Cần đối chiếu scope, tests, class files và report rules trước khi hạ gate.
- **Generated code, records, patterns, preview và multi-release JARs** có thể ảnh hưởng bytecode, instrumentation và source mapping.
- **Gradle/Maven plugin, JaCoCo agent, test JVM và report generator là các thành phần cần xác minh riêng**. Đừng suy rằng nâng wrapper đã nâng toàn bộ analyzer.
- **Agent conflicts và shaded ASM versions** cần được điều tra đúng component sở hữu thay vì ép dependency override chung.
- **XML coverage import là bước độc lập** với tạo exec data và report. Dashboard thành công chưa chắc đã nhập đủ dữ liệu.
- **Static analysis không thay kiểm thử hành vi; coverage không thay assertions**. Migration cần phối hợp các lớp chất lượng.
- **Kết luận tương thích phải dựa trên evidence**: tool version, JDK runtime, class-file major, tests executed, report artifacts và CI quality gates.

Một kế hoạch Java Advance Compatibility Migration đáng tin không chỉ làm source biên dịch và service khởi động. Nó còn phải bảo đảm **JaCoCo đo được code thật sự chạy, công cụ phân tích tĩnh hiểu được cú pháp và bytecode của Java mới, và pipeline chất lượng tiếp tục tạo báo cáo có ý nghĩa**. Khi giữ được khả năng quan sát và kiểm chứng này, nhóm có thể đánh giá thay đổi JDK dựa trên bằng chứng, thay vì chấp nhận một bản nâng cấp “xanh CI” nhưng đã vô tình mất năng lực phát hiện lỗi.
