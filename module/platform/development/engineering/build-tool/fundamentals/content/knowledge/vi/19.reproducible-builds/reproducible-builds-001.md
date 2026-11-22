# Build lặp lại được và artifact tái lập từng byte

Một build đáng tin cậy có thể được chạy lại với cùng bộ đầu vào được quản lý và tạo ra cùng kết quả. Với phần mềm phát hành, mục tiêu mạnh hơn là **artifact có thể tái lập từng byte**: hai lần build độc lập từ cùng source, dependency, cấu hình và toolchain tạo ra file đầu ra giống hệt nhau ở cấp byte.

Điều này quan trọng vì artifact là thứ được kiểm thử, lưu trong repository và triển khai lên môi trường thật. Nếu hai lần build cùng một commit tạo ra hai JAR khác checksum mà không có lý do được giải thích, nhóm khó xác nhận binary nào đã được kiểm thử, khó điều tra sự cố và khó chứng minh nguồn gốc sản phẩm.

Tái lập build không chỉ là chạy lại lệnh build. Nó đòi hỏi kiểm soát các yếu tố có thể ảnh hưởng đầu ra: source, dependency, plugin, JDK, hệ điều hành, biến môi trường, thời gian, thứ tự file, encoding, đường dẫn, quyền file và cách đóng gói archive. Mỗi yếu tố không được quản lý đều có thể khiến artifact thay đổi.

## 1. Các khái niệm cần phân biệt

### 1.1. Build lặp lại được

Một build lặp lại được là build có thể chạy lại với cùng đầu vào đã xác định và tạo ra kết quả tương đương theo hợp đồng của dự án. Trong thực tế, cụm từ này đôi khi được dùng rộng để nói rằng quy trình có thể thực hiện nhiều lần một cách ổn định.

Ví dụ, chạy build hai lần đều tạo ra ứng dụng có cùng hành vi, cùng class và cùng resource cần thiết. Tuy nhiên, file JAR vẫn có thể khác checksum vì timestamp bên trong archive hoặc metadata được sinh theo thời điểm chạy.

### 1.2. Reproducible build

Một reproducible build theo nghĩa nghiêm ngặt có thể được tái tạo độc lập: cùng source và các đầu vào được xác định sẽ tạo ra artifact giống hệt từng byte. Người khác có thể build lại trong môi trường được mô tả và so sánh checksum để kiểm chứng.

Ví dụ:

~~~text
Build A: inventory-service-1.4.0.jar
SHA-256: 4f...a9

Build B: inventory-service-1.4.0.jar
SHA-256: 4f...a9

Kết quả: hai file có nội dung byte-for-byte giống nhau.
~~~

Checksum trùng nhau là bằng chứng mạnh rằng hai file có cùng nội dung, với giả định thuật toán hash không bị phá vỡ. Nó không tự chứng minh source hoặc quy trình phát hành đáng tin cậy; nguồn gốc và chữ ký cần được quản lý riêng.

### 1.3. Deterministic build

Build deterministic là build mà cùng một tập đầu vào tạo ra cùng một đầu ra. Tính xác định là điều kiện cốt lõi để có thể tái lập từng byte.

Một task có thể không deterministic nếu nó:

- chèn thời gian hiện tại vào file sinh ra;
- dùng số ngẫu nhiên không có seed cố định;
- duyệt danh sách file theo thứ tự không ổn định;
- phụ thuộc vào biến môi trường hoặc đường dẫn máy mà không khai báo;
- tải dữ liệu thay đổi từ Internet trong lúc build;
- đọc trạng thái bên ngoài mà không được cố định.

### 1.4. Reproducible build khác build cache

Build cache lưu kết quả của công việc để lần sau có thể dùng lại khi input phù hợp. Reproducible build yêu cầu các lần thực thi độc lập tạo cùng output từ cùng input.

| Khái niệm | Câu hỏi được trả lời |
|---|---|
| Incremental build | Có thể bỏ qua công việc không cần chạy lại không? |
| Build cache | Có thể tái sử dụng kết quả đã tạo trước đó không? |
| Deterministic task | Cùng input có luôn tạo cùng output không? |
| Reproducible build | Build độc lập có tạo artifact giống hệt từng byte không? |
| Provenance | Ai hoặc hệ thống nào đã build artifact, từ source và quy trình nào? |

Một build dùng cache nhanh không nhất thiết tái lập được. Nếu task phụ thuộc thời gian nhưng khai báo input thiếu, cache có thể trả về kết quả cũ trong một lần chạy và thực thi lại trong lần khác, tạo ra hành vi khó đoán. Ngược lại, một build không bật cache vẫn có thể reproducible nếu mọi đầu vào được kiểm soát và mọi task deterministic.

## 2. Vì sao hai lần build cùng source có thể tạo file khác nhau?

Source code chỉ là một phần của đầu vào. Artifact cuối còn chịu ảnh hưởng từ compiler, plugin, dependency, tài nguyên, metadata và môi trường thực thi.

Những nguồn khác biệt thường gặp:

| Nguồn biến thiên | Ví dụ | Hệ quả |
|---|---|---|
| Timestamp | ZIP entry ghi thời gian tạo file | JAR/ZIP khác checksum |
| Thứ tự file | Duyệt thư mục theo thứ tự filesystem | Entry trong archive có thứ tự khác |
| Version dependency động | 1.+ hoặc latest.release | Hai lần build chọn phiên bản khác |
| Snapshot mutable | Cùng tọa độ snapshot được publish lại | Nội dung dependency thay đổi |
| JDK/compiler | Khác phiên bản javac hoặc toolchain | Bytecode hoặc metadata khác |
| Plugin/build tool | Khác phiên bản Maven/Gradle/plugin | Cách biên dịch và đóng gói khác |
| Biến môi trường | BUILD_NUMBER, USER, HOME, locale | File sinh ra hoặc manifest khác |
| Thời gian/múi giờ | Local date/time trong resource | Nội dung khác theo máy và thời điểm |
| Encoding/line endings | UTF-8 so với encoding khác, LF so với CRLF | Byte trong resource khác |
| Đường dẫn tuyệt đối | Ghi workspace path vào generated file | Máy khác tạo output khác |
| Quyền và thuộc tính file | Unix mode hoặc symlink | Archive khác metadata |
| Mạng | Tải schema hoặc dữ liệu mới nhất | Input không cố định |
| Randomness | UUID hoặc random seed khi generate | Nội dung khác mỗi lần |
| Race condition | Hai task cùng ghi một output | Kết quả phụ thuộc thứ tự chạy |

Để tìm nguyên nhân, cần xem artifact khác nhau ở đâu: bytecode, resource, manifest, archive metadata hay dependency. Chỉ nhìn checksum cho biết file khác, chưa chỉ ra lý do.

## 3. Kiểm soát đầu vào của build

Muốn tái lập output, trước hết phải xác định đầy đủ input.

### 3.1. Source và generated source

Source phải được xác định bằng commit hoặc source archive cụ thể. Generated source cũng phải có quy tắc rõ ràng:

- generator và phiên bản generator được khóa;
- schema/template đầu vào được quản lý trong repository hoặc artifact có version;
- thứ tự đầu vào ổn định;
- không đưa timestamp hoặc đường dẫn máy vào source được sinh nếu không cần;
- output cũ không được dùng thay cho source mới.

Nếu generated source được tạo bởi một công cụ ngoài build mà không lưu lại lệnh và version, người khác có thể không tạo được cùng output.

### 3.2. Khóa dependency version

Tránh dùng version động trong release build, ví dụ:

~~~kotlin
dependencies {
    // Không phù hợp cho build phát hành cần tái lập.
    implementation("com.example:catalog-core:1.+")
}
~~~

Ưu tiên version cụ thể:

~~~kotlin
dependencies {
    implementation("com.example:catalog-core:1.4.0")
}
~~~

Với Maven, khai báo version cụ thể hoặc quản lý qua BOM/dependencyManagement. Với Gradle, dùng version catalog, constraints hoặc dependency locking để kiểm soát phiên bản được chọn.

Một tọa độ release version nên bất biến. Nếu repository cho phép ghi đè JAR dưới cùng version, cùng một POM có thể resolve thành binary khác theo thời điểm. Snapshot và changing module cần được giới hạn trong môi trường phát triển có chính sách rõ ràng.

### 3.3. Khóa plugin và build tool

Plugin cũng là dependency của quy trình build. Nếu không khóa version, hai máy có thể chạy cùng source nhưng dùng plugin khác nhau.

Maven nên khai báo version plugin trong POM hoặc parent POM, thường qua pluginManagement. Gradle nên chỉ định version plugin rõ ràng trong plugins block hoặc quản lý tập trung bằng convention plugin/version catalog phù hợp.

Dùng Maven Wrapper hoặc Gradle Wrapper để cố định phiên bản build tool mà dự án yêu cầu. Wrapper không tự cố định JDK; toolchain cần được quản lý riêng.

### 3.4. Khóa JDK và compiler toolchain

Compiler có thể tạo bytecode và metadata khác nhau giữa các phiên bản JDK. Hãy khai báo Java toolchain hoặc compiler release để project nêu rõ môi trường cần dùng.

Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Maven Compiler Plugin:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Thuộc tính release xác định mức API Java và bytecode mục tiêu. Nó không tự bảo đảm mọi máy dùng cùng bản phân phối JDK hoặc cùng bản vá compiler. Nếu yêu cầu tái lập nghiêm ngặt, cần cố định cả JDK distribution/version trong CI hoặc build image.

### 3.5. Quản lý repository và dependency metadata

Một build có thể khác nếu repository thay đổi metadata, snapshot hoặc artifact dưới cùng tọa độ. Nên:

- dùng repository được quản lý và có chính sách version bất biến;
- ưu tiên HTTPS và nguồn dependency được cho phép;
- tránh tải file tùy tiện từ URL không có checksum/version;
- dùng dependency verification khi phù hợp;
- lưu lockfile hoặc dependency resolution result khi công cụ hỗ trợ;
- không phụ thuộc artifact chỉ tồn tại trong local repository của một developer.

### 3.6. Đưa mọi đầu vào quan trọng vào hợp đồng task

Với custom task, khai báo input/output đầy đủ. Nếu task đọc file cấu hình, biến môi trường, version generator hoặc schema thì các giá trị ảnh hưởng kết quả phải được thể hiện trong input model hoặc được cố định trong môi trường build.

Một task khai báo thiếu input có thể được đánh dấu up-to-date hoặc cache hit dù dữ liệu thực tế đã thay đổi. Điều đó làm kết quả không đáng tin cậy.

## 4. Loại bỏ thời gian khỏi artifact

Timestamp là một nguồn khác biệt phổ biến vì archive format có thể lưu thời gian của từng entry. Hai lần đóng gói cùng một file ở hai thời điểm có thể tạo JAR khác checksum.

### 4.1. Chuẩn hóa timestamp trong Maven

Maven hỗ trợ property chuẩn project.build.outputTimestamp để cung cấp thời điểm ổn định cho các plugin archive hỗ trợ nó. Có thể khai báo một giá trị cố định hoặc giá trị được quản lý trong quy trình release:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Với Maven JAR Plugin, có thể cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-jar-plugin</artifactId>
    <version>3.4.2</version>
    <configuration>
        <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
    </configuration>
</plugin>
~~~

Plugin archive cần hỗ trợ thuộc tính outputTimestamp thì cấu hình mới có tác dụng. Nếu project tạo WAR, ZIP hoặc assembly bằng plugin khác, hãy kiểm tra tham số timestamp tương ứng của chính plugin đó. Không nên giả định property này tự động chuẩn hóa mọi file mà build tạo ra.

Một số quy trình dùng SOURCE_DATE_EPOCH làm nguồn timestamp chuẩn. Nếu dùng biến môi trường này, hãy chuyển nó thành property mà plugin hỗ trợ và bảo đảm giá trị giống nhau giữa các build độc lập.

### 4.2. Chuẩn hóa timestamp trong Gradle

Gradle archive tasks cung cấp thuộc tính để không giữ timestamp gốc của file và sắp xếp entry theo thứ tự có thể tái lập:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Thiết lập này áp dụng cho các task archive kế thừa AbstractArchiveTask trong build. Cần kiểm tra các plugin archive khác hoặc task tùy chỉnh nếu chúng không dùng loại task này.

isPreserveFileTimestamps = false yêu cầu archive không giữ timestamp gốc của từng file theo cách mặc định. isReproducibleFileOrder = true giúp thứ tự entry trong archive ổn định.

### 4.3. Timestamp trong nội dung file

Chuẩn hóa timestamp của archive chưa đủ nếu chính file resource hoặc generated source chứa thời gian hiện tại.

Ví dụ không deterministic:

~~~java
String buildInfo = "Built at: " + java.time.Instant.now();
~~~

Mỗi lần chạy sẽ tạo nội dung khác. Nếu cần ghi thời điểm build để phục vụ truy vết, hãy phân biệt:

- metadata provenance bên ngoài artifact hoặc gắn với build run;
- timestamp chuẩn được cố định cho các lần tái lập;
- timestamp thực tế của lần build, vốn làm artifact khác nhau.

Không nên đưa thời gian hiện tại vào artifact nếu nó không cần thiết cho ứng dụng.

## 5. Ổn định thứ tự file và dữ liệu sinh ra

Một thư mục có thể trả file theo thứ tự khác nhau giữa hệ điều hành, filesystem hoặc lần chạy. Nếu task đưa kết quả duyệt file trực tiếp vào archive hoặc file index, output có thể thay đổi.

### 5.1. Sắp xếp file trước khi xử lý

Ví dụ Kotlin:

~~~kotlin
val orderedFiles = sourceFiles.sortedBy {
    it.relativeTo(sourceRoot).invariantSeparatorsPath
}
~~~

Sử dụng đường dẫn tương đối chuẩn hóa thay vì đường dẫn tuyệt đối của máy. Điều này giúp thứ tự ổn định và tránh workspace path xuất hiện trong output.

### 5.2. Không phụ thuộc thứ tự collection không được bảo đảm

Nếu output được tạo từ Map/Set hoặc dữ liệu truy vấn, hãy sắp xếp theo khóa rõ ràng trước khi serialize. Không nên dựa vào thứ tự tình cờ của cấu trúc dữ liệu.

Ví dụ Java:

~~~java
entries.stream()
    .sorted(Comparator.comparing(Entry::getName))
    .forEach(this::writeEntry);
~~~

Nếu thứ tự có ý nghĩa nghiệp vụ, hãy định nghĩa thứ tự đó trong hợp đồng thay vì sắp xếp tùy tiện.

### 5.3. Chuẩn hóa JSON/YAML/XML

Hai file có thể biểu diễn cùng dữ liệu nhưng khác byte do thứ tự key, khoảng trắng, newline hoặc cách serialize số/ngày tháng. Nếu cần artifact tái lập, serializer cần có cấu hình canonical hoặc quy tắc định dạng ổn định.

Các điểm cần kiểm soát:

- thứ tự key/property;
- encoding UTF-8;
- line ending LF hoặc quy ước thống nhất;
- format số và decimal separator;
- timezone và định dạng ngày;
- khoảng trắng, indent và newline cuối file.

### 5.4. Randomness trong code generator

Generator có thể tạo tên định danh, thứ tự file hoặc giá trị ngẫu nhiên. Nếu randomness là cần thiết, dùng seed được khai báo như input. Nếu không cần randomness, loại bỏ nó.

Không dùng UUID ngẫu nhiên hoặc timestamp để đặt tên file output khi tên đó có thể được xác định từ input ổn định.

## 6. Kiểm soát môi trường build

Build có thể đọc nhiều thuộc tính môi trường mà người viết không để ý.

### 6.1. Locale và timezone

Locale có thể ảnh hưởng định dạng số, ngày, tên tháng hoặc thứ tự sắp xếp chuỗi. Timezone có thể làm thay đổi timestamp hoặc ngày được sinh ra.

CI nên quy định locale/timezone thống nhất, ví dụ UTC và locale phù hợp với công cụ. Tốt hơn nữa, code build nên dùng định dạng bất biến và truyền timezone rõ ràng thay vì dựa vào cấu hình máy.

### 6.2. Encoding và line endings

Hãy thống nhất UTF-8 cho resource và file sinh ra. Có thể dùng .editorconfig và .gitattributes để quy định encoding/line endings trong repository.

Ví dụ .gitattributes:

~~~text
*.java text eol=lf
*.kt text eol=lf
*.properties text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
~~~

Quy tắc cụ thể phụ thuộc project và nền tảng chạy script. Mục tiêu là không để Git checkout cùng file thành byte khác nhau chỉ vì cấu hình line ending trên máy.

### 6.3. Đường dẫn và tên người dùng

Không ghi đường dẫn tuyệt đối như C:\Users\Alice\workspace\project hoặc /home/bob/project vào artifact. Đường dẫn này thay đổi theo máy và có thể tiết lộ thông tin không cần thiết.

Nếu compiler hoặc generator ghi source path vào metadata, hãy xem tùy chọn path mapping/debug info mà công cụ hỗ trợ. Dùng đường dẫn tương đối hoặc prefix mapping khi có thể.

### 6.4. Biến môi trường

Các biến như USER, HOME, BUILD_NUMBER, CI, JAVA_HOME hoặc biến do pipeline tự đặt có thể ảnh hưởng output. Hãy liệt kê biến nào thực sự cần thiết và truyền chúng rõ ràng.

Không đọc mọi biến môi trường rồi đưa vào generated file. Nếu một biến làm thay đổi output, nó phải được xem là input có chủ đích và được ghi nhận trong build provenance.

### 6.5. Hệ điều hành và filesystem

Khác biệt giữa Windows, Linux và macOS có thể ảnh hưởng:

- separator của đường dẫn;
- phân biệt chữ hoa/chữ thường;
- permission và executable bit;
- symlink;
- line endings;
- công cụ native được gọi từ build;
- thứ tự file và quy tắc nén.

Nếu artifact cần reproducible giữa các OS, build phải tránh phụ thuộc các khác biệt này hoặc chuẩn hóa chúng. Nếu artifact có thành phần native theo OS/architecture, mục tiêu tái lập phải xác định rõ nền tảng tương ứng.

## 7. Kiểm soát compiler, toolchain và plugin

### 7.1. Maven Wrapper và Gradle Wrapper

~~~bash
./mvnw -version
./gradlew --version
~~~

Wrapper giúp project yêu cầu phiên bản build tool cụ thể. Hãy commit wrapper scripts và wrapper configuration theo quy ước của repository. Không nên để mỗi developer tự chọn Maven/Gradle version toàn cục.

### 7.2. Java toolchain

Gradle có thể chọn JDK theo toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Maven có thể cấu hình toolchains plugin hoặc quản lý JDK trong CI image. Chỉ đặt maven.compiler.release không có nghĩa Maven tự tải và dùng cùng một JDK distribution ở mọi máy.

### 7.3. Pin plugin version

Maven:

~~~xml
<build>
    <pluginManagement>
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
    </pluginManagement>
</build>
~~~

Gradle:

~~~kotlin
plugins {
    java
    id("com.example.some-plugin") version "1.2.3"
}
~~~

Version minh họa cần được thay bằng version tương thích với dự án. Điều quan trọng là version plugin không thay đổi âm thầm giữa hai lần build.

### 7.4. Annotation processor và generator

Annotation processor có thể sinh mã dựa trên metadata, thứ tự symbol hoặc version compiler. Hãy pin version processor và cấu hình processor path riêng. Không để processor tải schema hoặc đọc file ngoài hợp đồng trong lúc compile.

Nếu processor sinh timestamp hoặc đường dẫn tuyệt đối, hãy xem nó có tùy chọn deterministic output hay không. Nếu không, cần thay thế hoặc bọc generator bằng bước chuẩn hóa được kiểm soát.

## 8. Maven: cấu hình archive có thể tái lập

Một ví dụ POM rút gọn:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>inventory-service</artifactId>
    <version>1.4.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <outputTimestamp>${project.build.outputTimestamp}</outputTimestamp>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Ví dụ này khóa compiler plugin, JAR plugin, encoding, release target và timestamp của archive. Nó là một phần của cấu hình reproducible build, không phải bảo đảm toàn bộ build đã deterministic.

Các plugin khác tạo ZIP, WAR, assembly, generated source hoặc metadata cần được cấu hình tương ứng. Dependency version, Maven Wrapper, JDK distribution, property môi trường và task tùy chỉnh cũng phải được kiểm soát.

## 9. Gradle: cấu hình archive có thể tái lập

Với Gradle, có thể chuẩn hóa thứ tự và timestamp cho archive tasks:

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Kết hợp với version plugin cố định, toolchain rõ ràng và dependency locking/verification:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}

dependencyLocking {
    lockAllConfigurations()
}
~~~

Để tạo lock state, chạy task phù hợp với cấu hình dependency của project:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle dependency verification có thể dùng file verification metadata được tạo và kiểm tra theo quy trình của project. Không nên tự tin chỉ vì có lockfile; cần xác nhận dependency được khóa đúng và checksum/signature metadata được quản lý đáng tin cậy.

Gradle có thể tạo archive reproducible theo cấu hình trên, nhưng task tùy chỉnh vẫn phải deterministic. Nếu một task ghi timestamp vào file, archive timestamp đã chuẩn hóa cũng không làm nội dung file giống nhau.

## 10. Dependency locking và verification

### 10.1. Dependency locking

Dependency locking ghi nhận phiên bản dependency được resolve để các lần build sau chọn cùng phiên bản trong phạm vi cấu hình đã khóa.

Gradle có thể bật locking:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó tạo hoặc cập nhật lock state bằng task phù hợp, ví dụ:

~~~bash
./gradlew dependencies --write-locks
~~~

Khi dependency graph thay đổi có chủ đích, cần cập nhật lockfile và review thay đổi như một phần của source change.

### 10.2. Maven dependency management

Maven có thể quản lý version bằng dependencyManagement, parent POM hoặc BOM. Maven không dùng cơ chế lockfile tiêu chuẩn giống Gradle trong mọi dự án. Nếu cần tái lập nghiêm ngặt, phải bảo đảm tất cả dependency version và repository metadata được quản lý, kể cả dependency bắc cầu.

Không dùng version range hoặc version động trong release build nếu không có chính sách khóa và xác minh kết quả resolve.

### 10.3. Gradle dependency verification

Gradle dependency verification cho phép lưu checksum hoặc chữ ký mong đợi của dependency trong metadata verification. Khi resolve, Gradle kiểm tra artifact tải về theo metadata này.

Điều này giúp phát hiện artifact bị thay đổi hoặc nguồn cung cấp không khớp giá trị tin cậy. Nó bổ sung cho dependency locking:

- locking kiểm soát phiên bản được chọn;
- verification kiểm tra nội dung artifact được tải.

Hai cơ chế giải quyết hai vấn đề khác nhau và nên được cập nhật có kiểm soát.

## 11. Tính xác định của custom task

Một custom task có thể phá vỡ reproducibility dù các plugin tiêu chuẩn đã được cấu hình tốt.

### 11.1. Khai báo input/output đầy đủ

Gradle task nên khai báo input files, input properties và output files/directories. Task action chỉ nên dựa trên những input đã được mô tả.

Ví dụ không tốt:

~~~kotlin
tasks.register("generateBuildInfo") {
    doLast {
        val now = java.time.Instant.now()
        file("build/generated/build-info.txt").writeText("Built at $now")
    }
}
~~~

Task này đọc thời gian hiện tại nhưng không khai báo nó như input. Output thay đổi mỗi lần chạy và không thể tái lập.

Nếu timestamp thực sự là yêu cầu, cần xác định timestamp chuẩn từ một input cố định, ví dụ SOURCE_DATE_EPOCH hoặc build parameter được quản lý. Nếu không cần timestamp, bỏ nó khỏi nội dung.

### 11.2. Tránh đọc trạng thái ngầm

Task không nên âm thầm đọc:

- file ngoài project không được khai báo;
- biến môi trường tùy ý;
- dữ liệu mạng thay đổi;
- đồng hồ hệ thống;
- thư mục home của developer;
- trạng thái service bên ngoài.

Nếu cần các giá trị đó, đưa chúng vào cấu hình rõ ràng và ghi nhận như input. Nếu giá trị không thể cố định, task có thể không phù hợp với cache/reproducibility.

### 11.3. Không ghi output chung từ nhiều task

Hai task cùng ghi một file có thể tạo race condition. Kết quả cuối phụ thuộc task nào ghi sau hoặc cách filesystem xử lý.

Mỗi output nên có một task sở hữu. Nếu cần nhiều bước, hãy tạo output trung gian riêng rồi nối task dependency theo thứ tự.

### 11.4. Sắp xếp và chuẩn hóa output

Generator cần sắp xếp input, chuẩn hóa newline/encoding và tránh thông tin máy cục bộ. Nếu serialize Map/Set, hãy định nghĩa thứ tự. Nếu tạo archive, bật reproducible file order.

### 11.5. Tách side effect khỏi artifact generation

Task tạo JAR có thể deterministic và cacheable. Task publish lên repository hoặc gửi thông báo là side effect bên ngoài, không nên coi nó là cùng một công việc có thể bỏ qua bằng cache.

Tách:

- tạo artifact từ input xác định;
- xác minh artifact;
- publish/promote artifact theo quyền và quy trình riêng.

## 12. Tái lập artifact không đồng nghĩa build không phụ thuộc môi trường

Một số sản phẩm phụ thuộc nền tảng một cách hợp lệ. Ví dụ native executable hoặc image cho ARM64 khác sản phẩm cho x86_64. Khi đó, mục tiêu không phải tạo cùng một binary cho mọi kiến trúc, mà là tái lập trong từng target platform đã xác định.

Hãy ghi rõ build target:

- OS và architecture;
- JDK/toolchain;
- native compiler và linker;
- container base image;
- libc hoặc runtime phụ thuộc;
- biến cấu hình build được phép.

Một artifact native Linux x86_64 có thể tái lập trong môi trường Linux x86_64 được khóa, nhưng không thể mong nó byte-for-byte giống artifact macOS ARM64.

## 13. Container image và reproducibility

Nếu ứng dụng được phân phối bằng container image, việc tái lập cần kiểm soát nhiều lớp hơn JAR:

- base image phải được khóa bằng digest thay vì chỉ tag có thể thay đổi;
- package manager và OS packages cần version cụ thể;
- build context phải được xác định;
- file copy và timestamp cần được chuẩn hóa khi có thể;
- build argument và environment phải được ghi nhận;
- image layer và metadata cần được kiểm soát.

Ví dụ Dockerfile có base image dùng digest:

~~~dockerfile
FROM eclipse-temurin:21-jre@sha256:<approved-digest>
WORKDIR /app
COPY build/libs/inventory-service.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Digest ở đây là placeholder minh họa; cần dùng digest thật được tổ chức phê duyệt. Chỉ khóa base image chưa đủ nếu build còn cài package không khóa version hoặc tải file thay đổi từ mạng.

Container image có metadata và layer digest. Hai image có thể khác do timestamp hoặc config metadata dù ứng dụng JAR bên trong giống nhau. Nếu yêu cầu reproducibility ở mức image, cần kiểm soát cả quy trình image build.

## 14. Cách kiểm chứng artifact tái lập từng byte

Một kiểm chứng thực tế cần hai build độc lập, lý tưởng trong hai workspace sạch và môi trường được mô tả giống nhau.

### 14.1. Build từ hai workspace sạch

Quy trình khái niệm:

1. Checkout cùng commit vào workspace A.
2. Checkout cùng commit vào workspace B.
3. Dùng cùng wrapper, JDK/toolchain, dependency lock và cấu hình.
4. Build artifact trong cả hai workspace.
5. Tính SHA-256 cho từng artifact.
6. So sánh checksum.
7. Nếu khác, so sánh cấu trúc archive và nội dung bên trong.

Ví dụ:

~~~bash
./mvnw clean verify
sha256sum target/inventory-service-1.4.0.jar
~~~

Hoặc Gradle:

~~~bash
./gradlew clean build
sha256sum build/libs/inventory-service-1.4.0.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash target/inventory-service-1.4.0.jar -Algorithm SHA256
~~~

Chạy lệnh phù hợp với artifact và workspace đang kiểm tra.

### 14.2. So sánh checksum

Linux/macOS:

~~~bash
sha256sum build-a/app.jar
sha256sum build-b/app.jar
~~~

Windows:

~~~powershell
Get-FileHash build-a/app.jar -Algorithm SHA256
Get-FileHash build-b/app.jar -Algorithm SHA256
~~~

Nếu hash giống nhau, hai file có cùng nội dung theo SHA-256. Nếu hash khác nhau, cần điều tra thay vì kết luận ngay rằng bytecode khác.

### 14.3. So sánh nội dung archive

JAR là ZIP archive. Có thể liệt kê entry:

~~~bash
jar --list --file app.jar
~~~

Giải nén hai file vào hai thư mục riêng rồi so sánh:

~~~bash
mkdir extracted-a extracted-b
unzip -q build-a/app.jar -d extracted-a
unzip -q build-b/app.jar -d extracted-b
diff -ru extracted-a extracted-b
~~~

Nếu file đã giải nén giống nhau nhưng JAR checksum khác, khác biệt có thể nằm ở archive metadata, timestamp, compression hoặc thứ tự entry. Nếu file bên trong khác, tiếp tục xác định class/resource/manifest nào khác.

### 14.4. Công cụ phân tích khác biệt

Các công cụ như diffoscope có thể phân tích hai archive và chỉ ra khác biệt ở metadata, file nội bộ hoặc nội dung nhị phân. Công cụ này hữu ích khi archive phức tạp và so sánh thủ công mất thời gian.

Kết quả so sánh nên được lưu cùng build record nếu reproducibility là yêu cầu phát hành. Không cần chạy phân tích sâu cho mọi build hằng ngày; có thể chạy ở pipeline xác minh định kỳ hoặc release.

## 15. Phân loại khác biệt khi hash không giống nhau

Khi hai artifact khác checksum, hãy phân loại:

| Khác biệt quan sát được | Nguyên nhân cần kiểm tra |
|---|---|
| Chỉ timestamp ZIP/JAR khác | Archive timestamp chưa chuẩn hóa |
| Thứ tự entry khác | File collection hoặc archive task chưa có thứ tự ổn định |
| Manifest khác | Version, build number, timestamp hoặc property môi trường |
| Resource khác | Filtering, encoding, line endings hoặc biến môi trường |
| Class file khác | JDK/compiler, annotation processor, debug info hoặc input source |
| Dependency JAR khác | Version động, snapshot mutable hoặc repository thay đổi |
| File generated khác | Generator version, thời gian, random seed hoặc thứ tự input |
| Permission khác | OS/filesystem hoặc cách đóng gói file mode |
| Chỉ container image khác | Base image, layer metadata, timestamp hoặc image config |

Nếu khác biệt là có chủ đích, hãy ghi nhận lý do và đầu vào làm thay đổi artifact. Nếu không có chủ đích, loại bỏ nguồn biến thiên và chạy lại kiểm chứng.

## 16. Build một lần và promote cùng artifact

Một cách giảm rủi ro giữa test và production là build artifact một lần, kiểm thử nó, publish nó với version bất biến rồi promote chính file đó qua các môi trường.

~~~text
Commit
  |
  v
Build artifact
  |
  v
Test exact artifact
  |
  v
Publish immutable version
  |
  +----> Deploy staging
  |          |
  |          v
  |       Acceptance test
  |
  +----> Promote same artifact to production
~~~

Nếu mỗi môi trường chạy build lại, artifact có thể khác do property, dependency, timestamp hoặc môi trường. Khi đó, việc staging thành công không chứng minh binary production giống binary đã được test.

Ưu tiên externalize cấu hình môi trường để cùng một artifact chạy ở nhiều môi trường. Nếu phải tạo artifact riêng theo môi trường, hãy dùng version/metadata khác nhau và ghi lại cấu hình build.

## 17. Provenance, checksum, chữ ký và SBOM

Reproducibility là một phần của chuỗi cung ứng phần mềm, nhưng không thay thế các bằng chứng khác.

### 17.1. Checksum

Checksum xác nhận nội dung file có khớp với giá trị hash được ghi nhận hay không. Nó hữu ích khi truyền artifact giữa CI, repository và môi trường triển khai.

Nếu kẻ tấn công có thể thay cả artifact lẫn file checksum trên cùng kênh không tin cậy, checksum đơn lẻ không xác minh được nguồn phát hành.

### 17.2. Chữ ký số

Chữ ký số giúp xác minh artifact được ký bởi khóa tương ứng và nội dung chưa bị thay đổi kể từ khi ký. Người tiêu thụ cần biết public key nào đáng tin cậy và cách kiểm tra chữ ký.

Chữ ký không tự bảo đảm source code an toàn; nó chứng minh mối liên hệ với khóa ký và tính toàn vẹn của nội dung.

### 17.3. Build provenance

Provenance ghi lại artifact được tạo bởi hệ thống nào, từ source revision nào, dùng builder/toolchain nào và với tham số nào. Thông tin này giúp truy vết và điều tra.

Một provenance record tốt có thể chứa:

- repository và commit;
- build run ID;
- builder identity;
- JDK/build tool/plugin version;
- dependency lock/verification state;
- tham số build quan trọng;
- digest của artifact đầu ra.

Provenance không đồng nghĩa artifact reproducible. Nó mô tả nguồn gốc một lần build; reproducibility cho phép bên khác tái tạo và đối chiếu kết quả.

### 17.4. SBOM

Software Bill of Materials liệt kê thành phần phần mềm được đưa vào sản phẩm, thường gồm dependency, version và metadata liên quan. SBOM giúp kiểm kê, phân tích lỗ hổng và đáp ứng yêu cầu quản trị.

SBOM cần gắn với đúng artifact/version/digest. Nếu build lại tạo artifact khác, cần biết SBOM thuộc binary nào.

## 18. Quy trình thực hiện reproducible build trong nhóm

Một lộ trình thực tế:

1. **Chọn artifact cần tái lập:** ví dụ JAR release, WAR hoặc container image.
2. **Xác định target environment:** OS, architecture, JDK và runtime.
3. **Khóa source revision:** dùng commit/tag cụ thể.
4. **Khóa dependency:** version cụ thể, lockfile/BOM và dependency verification.
5. **Khóa toolchain:** Maven/Gradle Wrapper, JDK, compiler và plugin version.
6. **Chuẩn hóa môi trường:** locale, timezone, encoding, line endings và biến môi trường.
7. **Chuẩn hóa archive:** timestamp, thứ tự entry, permissions và metadata.
8. **Làm deterministic task:** loại thời gian/randomness ngầm, sắp xếp input và khai báo input/output.
9. **Build trong CI sạch:** tránh artifact cục bộ hoặc trạng thái không được quản lý.
10. **Build lại độc lập:** dùng workspace hoặc runner khác nhưng cùng bộ input đã khóa.
11. **So sánh digest:** xác nhận byte-for-byte.
12. **Điều tra khác biệt:** dùng archive listing, extraction hoặc diffoscope.
13. **Lưu provenance:** gắn digest với source, toolchain và build record.
14. **Promote đúng artifact:** triển khai file đã được kiểm thử và xác minh.

Không nhất thiết phải đạt reproducibility byte-for-byte ngay trong một bước. Có thể bắt đầu bằng việc khóa dependency/toolchain, chuẩn hóa archive và loại timestamp; sau đó xử lý các task tùy chỉnh và thành phần khó kiểm soát.

## 19. Những hiểu lầm thường gặp

### 19.1. Cùng commit nghĩa là cùng artifact

Không đúng nếu dependency, plugin, JDK, timestamp, môi trường hoặc repository metadata thay đổi. Commit chỉ khóa source revision, không tự khóa toàn bộ build input.

### 19.2. Build thành công hai lần là reproducible

Hai lần build cùng thành công chỉ chứng minh cả hai lần hoàn thành. Muốn kiểm tra byte-for-byte, cần so sánh artifact hoặc checksum.

### 19.3. Checksum giống nhau chứng minh source an toàn

Checksum giống nhau chứng minh hai file có cùng nội dung theo hash đã chọn. Nó không chứng minh source không có mã độc, builder đáng tin cậy hoặc dependency được chọn an toàn.

### 19.4. Bật build cache là đủ

Cache chỉ tái sử dụng kết quả dựa trên input/output và cache key. Task không deterministic hoặc khai báo input thiếu vẫn có thể làm cache trả kết quả sai hoặc tạo artifact khác khi thực thi thật.

### 19.5. Chỉ cần chuẩn hóa timestamp của JAR

Archive timestamp chỉ là một nguồn biến thiên. Nội dung file, manifest, generated code, dependency, compression, permission và môi trường vẫn có thể làm artifact khác.

### 19.6. Dùng cùng version dependency là đủ

Version có thể bị ghi đè trong repository, snapshot có thể thay đổi, hoặc metadata bắc cầu có thể khác. Cần repository policy, lock/verification và artifact integrity.

### 19.7. Reproducible build có nghĩa build trên mọi OS ra cùng một file

Không nhất thiết. Native artifact phụ thuộc OS/architecture. Mục tiêu cần xác định platform; reproducibility được đánh giá giữa các build có cùng target và input.

## 20. Bài tập thực hành

### Bài 1 — So sánh hai JAR được build liên tiếp

Tạo một project Java nhỏ, build JAR hai lần ở hai thời điểm khác nhau rồi tính SHA-256. Nếu hash khác, liệt kê nội dung archive và tìm entry có timestamp hoặc metadata khác.

### Bài 2 — Chuẩn hóa Gradle archive

Thêm cấu hình:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Build lại hai lần và so sánh checksum. Nếu vẫn khác, giải nén archive và so sánh nội dung file.

### Bài 3 — Chuẩn hóa Maven JAR

Khai báo project.build.outputTimestamp và cấu hình Maven JAR Plugin dùng giá trị đó. Chạy clean package ở hai workspace và so sánh SHA-256.

### Bài 4 — Phát hiện version động

Thử khai báo dependency version động trong project thử nghiệm. Xem dependency report ở hai thời điểm hoặc sau khi repository có version mới. Chuyển sang version cụ thể/locking và so sánh kết quả.

### Bài 5 — Loại bỏ thời gian trong generated file

Tạo task sinh build info có timestamp hiện tại. Build hai lần và so sánh output. Sau đó bỏ timestamp hoặc truyền một timestamp cố định làm input. Kiểm tra task có tạo cùng output hay không.

### Bài 6 — Build độc lập ở hai workspace

Checkout cùng commit vào hai thư mục khác nhau. Dùng wrapper và toolchain đã khóa, build artifact ở cả hai nơi, sau đó so sánh checksum. Nếu khác, kiểm tra đường dẫn tuyệt đối, môi trường, file order và archive metadata.

### Bài 7 — Kiểm tra đúng artifact được triển khai

Tạo pipeline khái niệm build, test, publish và deploy. Tính checksum sau test và trước deploy. Xác nhận stage deploy dùng cùng file đã kiểm thử, không chạy lại build để tạo một artifact mới.

## 21. Câu hỏi tự kiểm tra

1. Build lặp lại được khác reproducible build từng byte ở điểm nào?
2. Deterministic task cần đáp ứng điều gì?
3. Build cache có bảo đảm artifact tái lập từng byte không?
4. Vì sao cùng commit vẫn có thể tạo hai JAR khác checksum?
5. Timestamp của ZIP/JAR ảnh hưởng checksum như thế nào?
6. Maven project.build.outputTimestamp dùng để làm gì?
7. Gradle preserveFileTimestamps và reproducibleFileOrder điều khiển điều gì?
8. Vì sao phải khóa JDK, build tool, plugin và dependency?
9. Dependency locking khác dependency verification như thế nào?
10. Những biến môi trường nào có thể làm output thay đổi?
11. Vì sao custom task cần khai báo đầy đủ input và output?
12. Làm thế nào loại bỏ khác biệt do thứ tự file hoặc Map/Set?
13. Vì sao build một lần rồi promote cùng artifact giúp tăng độ tin cậy?
14. Checksum, chữ ký số, provenance và SBOM chứng minh những điều gì?
15. Làm thế nào kiểm tra hai artifact khác nhau ở archive metadata hay nội dung bên trong?

Khi hiểu các nguồn biến thiên và biết cách khóa đầu vào, chuẩn hóa archive, thiết kế task deterministic và so sánh checksum, bạn có thể tiến tới quy trình build mà người khác có thể tái tạo độc lập. Artifact tái lập từng byte giúp nhóm xác nhận binary phát hành đúng là binary đã được kiểm thử, tăng khả năng truy vết và củng cố niềm tin vào chuỗi cung ứng phần mềm.
