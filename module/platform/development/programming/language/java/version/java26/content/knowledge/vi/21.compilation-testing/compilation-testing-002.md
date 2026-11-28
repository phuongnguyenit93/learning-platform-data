# Cấu hình annotation processor tường minh

Annotation processor là chương trình chạy trong lúc biên dịch Java để đọc annotation và mô hình chương trình, kiểm tra quy tắc hoặc sinh thêm source/resource cho compiler. Các thư viện như MapStruct, Hibernate Processor, Dagger và Lombok có thể dùng annotation processing để tạo mã hoặc kiểm tra cấu trúc source. Từ JDK 23, `javac` không còn tự động dò và chạy processor trên classpath theo mặc định. Dự án phải chủ động yêu cầu annotation processing; cách an toàn hơn là khai báo rõ processor nào được chạy và đường dẫn chứa chúng.

Thay đổi này vẫn áp dụng trên JDK 26. Nó là thay đổi mặc định của công cụ biên dịch vì lý do bảo mật, không phải một tính năng preview của ngôn ngữ Java. Khi nâng JDK, nếu dự án trước đây dựa vào processor được phát hiện ngầm, mã nguồn sinh tự động có thể biến mất và build báo thiếu class/method. Cần cấu hình processor ở build tool và kiểm tra cả main source lẫn test source.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò và vòng đời của annotation processor trong `javac`.
- Hiểu thay đổi từ JDK 23 khiến annotation processing không còn tự động chạy khi không có cấu hình tường minh.
- Phân biệt compile classpath, processor classpath và processor module path.
- Chọn `-processor`, `--processor-path`, `--processor-module-path`, `-proc:full`, `-proc:only` và `-proc:none` đúng mục đích.
- Cấu hình processor trong Maven 3, Maven 4 và Gradle.
- Tách annotation API dùng để biên dịch source khỏi implementation của processor.
- Giới hạn processor được phép chạy để giảm rủi ro supply-chain.
- Kiểm tra source được sinh, thứ tự processing rounds và tính tương thích với JDK/compiler.
- Tránh cấu hình cũ khiến mọi processor có trên classpath được thực thi ngoài ý muốn.

## 1. Annotation processing làm gì?

Annotation processor là một implementation của `javax.annotation.processing.Processor`. Compiler gọi processor trong các vòng xử lý annotation (rounds) khi biên dịch source. Processor có thể đọc:

- Annotation được gắn lên class, method, field, parameter, package hoặc các element khác.
- Kiểu dữ liệu, modifier, method signature, generic type và quan hệ giữa các element qua `javax.lang.model`.
- Annotation của các source/class trong compilation environment.

Processor có thể kiểm tra quy tắc và phát diagnostic, hoặc sinh thêm source/resource qua `Filer`. Source được sinh sẽ được đưa vào các vòng tiếp theo và cuối cùng được `javac` biên dịch cùng source ban đầu, trừ khi dùng chế độ chỉ xử lý annotation.

Ví dụ thư viện MapStruct đọc interface có `@Mapper` rồi sinh implementation class. Hibernate Processor có thể sinh JPA metamodel từ entity. Một processor kiểm tra cấu trúc API có thể không sinh file nào mà chỉ báo lỗi nếu annotation được dùng sai.

Annotation processing là công việc ở compile time. Processor implementation không phải dependency cần có khi chạy ứng dụng, trừ khi chính thư viện runtime cũng được ứng dụng sử dụng. Vì vậy, cần phân biệt artifact chứa annotation/API với artifact chứa processor.

### Processor không sửa trực tiếp source hiện có

Annotation processing API chủ yếu cho phép đọc mô hình chương trình và tạo file mới bằng `Filer`; nó không phải macro system có quyền biến đổi tùy ý AST của source hiện có. Processor có thể sinh class mới, resource hoặc file hỗ trợ, sau đó code gốc tham chiếu tới chúng. Nếu cần thay đổi source trước compile theo cách khác, đó là một loại build plugin/compiler plugin hoặc source generation task riêng.

### Vòng đời processing rounds

Quy trình rút gọn:

```text
Source files + annotations
          │
          ▼
      javac tìm Processor
          │
          ▼
   Gọi process() cho round hiện tại
          │
          ├── Diagnostic: warning / error
          │
          └── Filer tạo source/resource mới
                         │
                         ▼
                Round tiếp theo
                         │
             Không còn source mới
                         │
                         ▼
          Round cuối cho processor hoàn tất
                         │
                         ▼
             javac biên dịch source gốc
               và source được sinh
```

Một processor có thể được gọi nhiều lần. Nó cần xử lý trạng thái theo round và tránh sinh lại cùng một file gây `FilerException`. Processor phải khai báo annotation types mà nó quan tâm, thường qua `@SupportedAnnotationTypes` hoặc `getSupportedAnnotationTypes()`.

## 2. Thay đổi mặc định từ JDK 23

Trước JDK 23, `javac` mặc định dò service provider trên classpath và chạy các annotation processor tìm thấy, ngay cả khi người dùng không truyền tùy chọn annotation processing. Điều này có nghĩa một dependency bất kỳ được thêm vào classpath có thể mang theo processor và khiến code của nó được thực thi trong lúc build.

Từ JDK 23, annotation processing chỉ chạy khi được yêu cầu bằng cấu hình tường minh, chẳng hạn:

- Chỉ định class processor bằng `-processor`.
- Chỉ định nơi tìm processor bằng `--processor-path` hoặc `--processor-module-path`.
- Bật rõ chế độ bằng `-proc:full` hoặc `-proc:only`.

Nếu không có cấu hình này, `javac` biên dịch source mà không chạy processor. Đây là default của JDK 23, 24, 25 và 26; không phải thay đổi chỉ có ở JDK 26.

**Tác động khi nâng JDK:** một dự án có thể vẫn tìm thấy annotation library trên compile classpath nhưng không còn sinh implementation class. Lỗi thường xuất hiện dưới dạng `cannot find symbol`, thiếu generated implementation/metamodel, hoặc một số kiểm tra compile-time không còn chạy. Nếu processor chỉ kiểm tra mà không sinh code, build thậm chí có thể thành công nhưng bỏ sót validation.

Mục tiêu bảo mật là tránh thực thi processor ẩn hoặc ngoài ý muốn chỉ vì một dependency xuất hiện trên classpath. Nên khai báo cả nơi chứa processor và danh sách processor được phép chạy, sau đó khóa phiên bản dependency.

## 3. Phân biệt các đường dẫn classpath

Có ba nhóm đường dẫn cần phân biệt:

| Đường dẫn | Chứa gì? | Dùng cho |
|---|---|---|
| Compile classpath (`-classpath`/`--class-path`) | Annotation/API và thư viện mà source tham chiếu | Để `javac` kiểm tra kiểu của source |
| Processor classpath (`--processor-path`) | JAR processor cùng dependency của processor | Nạp và chạy processor trong compiler runtime |
| Processor module path (`--processor-module-path`) | Module chứa processor và module dependency | Nạp processor được đóng gói theo JPMS |

`javac` chạy processor trong runtime environment của compiler. Các type mà processor phân tích thuộc compilation environment của source. Hai môi trường này liên quan nhưng không giống nhau. Dependency cần cho processor chạy phải có trên processor path; annotation API mà source tham chiếu phải có trên compile classpath hoặc module path.

Ví dụ với MapStruct:

- `org.mapstruct:mapstruct` chứa annotation/API mà source import `@Mapper`.
- `org.mapstruct:mapstruct-processor` chứa processor sinh implementation.

Trong Maven/Gradle, annotation API thường được khai báo ở `provided`/`compileOnly`, còn processor nằm ở `annotationProcessorPaths`/`annotationProcessor`. Không đưa processor vào runtime classpath của ứng dụng nếu ứng dụng không có nhu cầu runtime riêng với artifact đó.

### Processor classpath và module path

Với processor đóng gói dạng JAR classpath, dùng `--processor-path`. `javac` tìm processor thông qua file service provider:

```text
META-INF/services/javax.annotation.processing.Processor
```

File này chứa tên đầy đủ của các lớp processor, mỗi dòng một tên.

Với processor được đóng gói thành named module, dùng `--processor-module-path`. Module processor cần khai báo service provider bằng `provides javax.annotation.processing.Processor with ...` và thường cần `requires java.compiler;` để truy cập API xử lý annotation. Không nhầm `--module-path` của ứng dụng với `--processor-module-path` của compiler.

## 4. Các tùy chọn `javac` cần biết

| Tùy chọn | Tác dụng | Lưu ý |
|---|---|---|
| `-processor A,B` | Chỉ định tên các processor cần chạy | Bỏ qua bước discovery mặc định; phù hợp để allowlist |
| `--processor-path path` | Nơi tìm processor dạng classpath | Nếu không chỉ định `-processor`, các processor được discover trên path này có thể được chạy |
| `--processor-module-path path` | Nơi tìm processor dạng module | Dùng cho processor được đóng gói theo JPMS |
| `-proc:full` | Chạy annotation processing rồi compile source | Không phải allowlist; có thể discovery các processor trên path mặc định |
| `-proc:only` | Chỉ chạy annotation processing, không compile source sau processing | Hữu ích cho pipeline tách riêng bước generate |
| `-proc:none` | Tắt annotation processing | Dùng khi build không cần processor hoặc muốn kiểm tra source thuần |
| `-s directory` | Nơi ghi source được sinh | Giúp quan sát và quản lý generated source |
| `-Akey=value` | Truyền option riêng cho processor | Processor phải hỗ trợ key tương ứng |
| `-XprintProcessorInfo` | In thông tin processor được gọi và annotation được xử lý | Hữu ích khi chẩn đoán |
| `-XprintRounds` | In từng processing round | Hữu ích khi processor sinh source theo nhiều vòng |
| `-Xlint:processing` | Bật cảnh báo liên quan annotation processing | Giúp phát hiện annotation không được processor claim |

`-processor` và `--processor-path` giải quyết hai vấn đề khác nhau. Path xác định code nào có thể được nạp; danh sách `-processor` xác định processor class nào được phép gọi. Nếu chỉ khai báo path mà không khai báo class, javac vẫn có thể discovery tất cả processor được đăng ký trên path đó.

### Ví dụ chạy trực tiếp bằng javac

```bash
javac \
  --release 26 \
  -classpath lib/mapstruct.jar \
  --processor-path processors/mapstruct-processor.jar:processors/dependency.jar \
  -processor org.mapstruct.ap.MappingProcessor \
  -s build/generated/sources/annotations \
  -d build/classes \
  src/main/java/example/CarMapper.java
```

Đây là cú pháp shell POSIX minh họa; dấu phân tách các entry của path là `:` trên Linux/macOS và `;` trên Windows. Processor path phải bao gồm dependency cần thiết của processor. Nếu processor được cung cấp qua module path, thay `--processor-path` bằng `--processor-module-path`.

`--release 26` kiểm soát ngôn ngữ/API và bytecode đích của source; nó không tự bật hoặc tắt annotation processing. Processor implementation vẫn chạy trong compiler runtime của JDK được dùng để chạy `javac`.

### Vì sao không chỉ thêm `-proc:full`?

`-proc:full` bật processing và compilation, nhưng tự nó không giới hạn processor nào được chạy. Nếu không có processor list và path riêng, compiler có thể dò processor trên classpath. Cách này giữ lại hành vi cũ nhưng làm mất mục tiêu kiểm soát execution.

Chỉ dùng `-proc:full` khi đã kiểm soát processor path và chấp nhận discovery trên path đó. Với build có yêu cầu bảo mật, ưu tiên khai báo processor cụ thể bằng `-processor` và path tách biệt.

## 5. Cấu hình với Maven 3 và Maven Compiler Plugin 3.x

Với Maven 3 và Compiler Plugin 3.x, dùng `annotationProcessorPaths` để tách processor khỏi compile classpath, và `annotationProcessors` để khai báo class processor cần chạy. Ví dụ dưới đây minh họa MapStruct; hãy thay version property bằng phiên bản đã được dự án kiểm duyệt và khóa.

```xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <mapstruct.version>1.6.3</mapstruct.version>
    <maven-compiler-plugin.version>3.14.1</maven-compiler-plugin.version>
</properties>

<dependencies>
    <!-- Annotation API mà source sử dụng -->
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>${mapstruct.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>${maven-compiler-plugin.version}</version>
            <configuration>
                <release>26</release>
                <annotationProcessors>
                    <annotationProcessor>
                        org.mapstruct.ap.MappingProcessor
                    </annotationProcessor>
                </annotationProcessors>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>${mapstruct.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Các điểm cần hiểu:

- `mapstruct` là annotation/API ở compile classpath.
- `mapstruct-processor` là code được nạp và thực thi trong compile phase.
- `annotationProcessorPaths` giới hạn nơi compiler tìm processor.
- `annotationProcessors` allowlist class `org.mapstruct.ap.MappingProcessor`.
- Phiên bản annotation API và processor cần tương thích; thường nên dùng cùng version.

Không sao chép version ví dụ mà không kiểm tra compatibility với JDK/compiler và dependency policy của dự án. Maven Compiler Plugin 3.x có thể cần cập nhật để hỗ trợ option hoặc JDK mới; kiểm tra tài liệu đúng version plugin mà build đang dùng.

### Khi nào cần processor cho test source?

Maven Compiler Plugin có execution riêng cho `compile` và `testCompile`. Nếu test source dùng annotation processor riêng hoặc cần processor để sinh test helper, cấu hình processor phù hợp cho execution `default-testCompile` hoặc phần cấu hình áp dụng cho test compilation. Không giả định cấu hình test tự động giống main source trong mọi custom lifecycle.

## 6. Cấu hình với Maven 4 và Compiler Plugin 4.x

Maven Compiler Plugin 4.x chuyển sang khai báo processor như dependency có type riêng. Cách này thể hiện rõ processor là thành phần build-time và cho phép chọn nơi đặt nó:

- `processor`: plugin cố gắng suy luận classpath hay module path.
- `classpath-processor`: yêu cầu processor nằm trên processor classpath.
- `modular-processor`: yêu cầu processor nằm trên processor module path.

Ví dụ:

```xml
<properties>
    <maven.compiler.release>26</maven.compiler.release>
    <mapstruct.version>1.6.3</mapstruct.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>${mapstruct.version}</version>
        <scope>provided</scope>
    </dependency>

    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct-processor</artifactId>
        <version>${mapstruct.version}</version>
        <type>classpath-processor</type>
    </dependency>
</dependencies>
```

`classpath-processor` phù hợp với processor được đóng gói kiểu classpath. Nếu processor là named module và được thiết kế để chạy trên module path, dùng `modular-processor`. Tránh để plugin tự đoán nếu đã biết chính xác dạng đóng gói.

Trong Compiler Plugin 4.x, cách khai báo `annotationProcessorPaths` kiểu cũ được đánh dấu deprecated và dự kiến bị loại bỏ trong version tương lai. Với Maven 4 và Compiler Plugin 4.x, ưu tiên dependency type mới theo tài liệu của plugin. Không trộn cú pháp Maven 3/plugin 3.x và Maven 4/plugin 4.x mà không kiểm tra phiên bản.

Nếu cần giới hạn một processor class cụ thể khi một artifact cung cấp nhiều processor, kiểm tra khả năng cấu hình processor list của plugin version đang dùng; chỉ khai báo dependency path chưa chắc đã chọn một class duy nhất nếu artifact đăng ký nhiều service provider.

## 7. Cấu hình với Gradle

Gradle Java plugin cung cấp các configuration riêng:

- `annotationProcessor`: processor cho main source.
- `testAnnotationProcessor`: processor cho test source.
- `<sourceSet>AnnotationProcessor`: processor cho custom source set.

Không khai báo processor trong `implementation` chỉ để mong compiler tự chạy nó. Tách annotation API khỏi processor implementation.

Ví dụ Kotlin DSL với MapStruct:

```kotlin
val mapstructVersion = "1.6.3"

dependencies {
    compileOnly("org.mapstruct:mapstruct:$mapstructVersion")
    annotationProcessor("org.mapstruct:mapstruct-processor:$mapstructVersion")

    testCompileOnly("org.mapstruct:mapstruct:$mapstructVersion")
    testAnnotationProcessor("org.mapstruct:mapstruct-processor:$mapstructVersion")
}
```

Gradle đặt dependency trong `annotationProcessor` trên processor path của task compile tương ứng. Đây là cấu hình tường minh giúp JDK 23+ kích hoạt processing mà không cần dựa vào việc dò processor trong application compile classpath.

Nếu processor path có nhiều processor nhưng chỉ muốn chạy một class cụ thể, có thể truyền `-processor` cho JavaCompile task:

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.named<JavaCompile>("compileJava") {
    options.compilerArgs.addAll(
        listOf("-processor", "org.mapstruct.ap.MappingProcessor")
    )
}
```

Nếu test source cũng cần giới hạn processor, cấu hình `compileTestJava` riêng với processor class phù hợp. Không áp dụng cùng một `-processor` toàn cục nếu main và test source sử dụng các processor khác nhau.

Ví dụ Groovy DSL:

```groovy
dependencies {
    compileOnly 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'

    testCompileOnly 'org.mapstruct:mapstruct:1.6.3'
    testAnnotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}

tasks.named('compileJava', JavaCompile) {
    options.compilerArgs.addAll([
        '-processor',
        'org.mapstruct.ap.MappingProcessor'
    ])
}
```

Với custom source set, khai báo processor trong configuration tương ứng, ví dụ `integrationTestAnnotationProcessor`. Gradle dùng processor path riêng cho từng source set; không đưa processor test vào main runtime classpath.

## 8. Quản lý dependency và rủi ro bảo mật

Annotation processor là code thực thi trong quá trình build. Nó thường chạy với quyền của tài khoản CI/developer đang biên dịch. Không có sandbox mặc định bảo đảm processor chỉ đọc source: một processor độc hại hoặc bị chiếm quyền có thể truy cập file mà user có quyền đọc, đọc environment variables, mở network connection hoặc chạy process khác.

Vì vậy, processor phải được xem như build tool có quyền thực thi, không chỉ là một thư viện annotation vô hại.

Thực hành nên áp dụng:

1. **Allowlist processor:** khai báo chính xác processor cần chạy, không bật toàn bộ discovery trên classpath lớn.
2. **Tách processor path:** chỉ đưa processor và dependency build-time cần thiết vào processor configuration.
3. **Pin version:** không dùng version động hoặc `latest.release`; khóa version của processor và dependency transitive.
4. **Kiểm tra nguồn:** dùng repository tin cậy, kiểm tra maintainer, release notes và checksum/signature theo chính sách tổ chức.
5. **Kiểm soát dependency transitive:** processor có thể kéo theo nhiều thư viện; kiểm tra dependency tree, exclusion và version conflict.
6. **Giới hạn quyền CI:** build job chỉ nhận secret tối thiểu cần thiết; tránh cấp credential production cho bước compile nếu không cần.
7. **Tách build untrusted:** pull request từ fork hoặc source chưa tin cậy không nên được cấp secret có quyền cao.
8. **Theo dõi generated output:** xem source/resource được sinh có chứa code lạ, đường dẫn tuyệt đối, credential hoặc nội dung ngoài dự kiến không.

Không nên nghĩ rằng `--processor-path` là sandbox. Nó chỉ xác định nơi compiler tìm processor; processor vẫn chạy trong JVM compiler với quyền của build process.

### Dependency tree và version verification

Maven có thể xem cây dependency để biết processor cùng dependency được kéo vào:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Gradle có thể xem cấu hình processor riêng:

```bash
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencies --configuration testAnnotationProcessor
```

Trong CI, dùng dependency locking/verification của build tool nếu tổ chức đã áp dụng. Khi cập nhật processor, xem diff của dependency graph và generated source, không chỉ xem build có pass hay không.

## 9. Cấu hình processor trong project modular

Khi source ứng dụng dùng JPMS, processor cũng có thể được đóng gói thành module riêng. Cần phân biệt:

- Module path của ứng dụng: chứa các module mà source đang compile phụ thuộc.
- Processor module path: chứa module cung cấp implementation `Processor` và dependency của nó.

Một module processor có thể khai báo:

```java
module com.example.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
            with com.example.processor.ModelProcessor;
}
```

Sau đó `javac` dùng:

```bash
javac \
  --release 26 \
  --module-path libs/application-modules \
  --processor-module-path libs/processor-modules \
  -processor com.example.processor.ModelProcessor \
  -d build/modules \
  --module-source-path src/main/java \
  -m com.example.application
```

Ví dụ minh họa cho project nhiều module; cần điều chỉnh `--module-source-path`, module name và module dependency theo cấu trúc thực tế. Nếu processor không phải named module, dùng processor classpath thay vì cố đưa một JAR classpath lên module path.

## 10. Generated source và thư mục đầu ra

Processor nên tạo file bằng `Filer` thay vì tự ghi vào thư mục build bằng `FileOutputStream` hoặc API file system tùy ý. `Filer` giúp compiler và build tool biết file nào được sinh trong compilation, tránh ghi đè source gốc và hỗ trợ incremental compilation.

Khi cần xem code được sinh:

- `javac`: dùng `-s generated-sources`.
- Maven Compiler Plugin: cấu hình generated sources directory theo API của plugin nếu cần thay đổi mặc định.
- Gradle: dùng `options.generatedSourceOutputDirectory` của `JavaCompile` nếu cần custom output; mặc định Gradle quản lý output riêng cho task.

Không commit generated source nếu dự án quy định sinh ở build time, trừ khi repository có chủ đích lưu code sinh để phục vụ artifact hoặc quy trình review. Không để output generator vào `src/main/java` nếu build tool không quản lý việc xóa và tái tạo; stale generated source có thể che giấu processor không còn chạy.

Nếu processor cần đọc resource như file schema/config, khai báo resource đó là input của compile task trong Gradle. Nếu không, incremental build hoặc build cache có thể không nhận ra resource đã thay đổi và dùng output cũ.

## 11. Incremental annotation processing trong Gradle

Gradle phân loại processor incremental thành các nhóm chính:

- **Isolating:** mỗi file sinh ra phụ thuộc vào một annotated element và các thông tin có thể truy xuất từ element đó. Processor cần khai báo đúng originating element cho file được sinh.
- **Aggregating:** output tổng hợp thông tin từ nhiều annotated elements không độc lập, ví dụ registry chứa toàn bộ service được annotate.
- **Dynamic:** processor khai báo metadata dynamic và tự xác định category qua supported options khi chạy.

Processor muốn được Gradle xử lý incremental cần khai báo metadata trong:

```text
META-INF/gradle/incremental.annotation.processors
```

Ví dụ nội dung:

```text
com.example.processor.EntityProcessor,isolating
com.example.processor.RegistryProcessor,aggregating
```

Không khai báo `isolating` nếu processor thực tế phụ thuộc vào tập element toàn cục. Khai báo sai có thể khiến Gradle chỉ chạy lại một phần source không đủ và tạo output sai hoặc stale. Nếu processor không hỗ trợ incremental, Gradle có thể phải biên dịch lại rộng hơn.

Các giới hạn quan trọng gồm:

- Processor cần tạo file qua `Filer`.
- Processor không nên ghi file tùy ý ra ngoài output do compiler quản lý.
- Isolating processor phải xác định chính xác originating element của từng file sinh ra.
- Processor dùng compiler-specific API như `com.sun.source.util.Trees` có thể không đáp ứng incremental processing theo cơ chế Gradle nếu không có fallback phù hợp.

Kiểm tra log `--info` của Gradle để biết processor nào làm incremental compilation bị vô hiệu hóa hoặc khiến toàn bộ source phải compile lại.

## 12. Kiểm tra và chẩn đoán annotation processing

Khi code generated biến mất hoặc build behavior thay đổi sau khi nâng JDK, kiểm tra theo thứ tự:

1. Xác nhận JDK thực sự chạy compiler bằng `javac -version` hoặc toolchain của Maven/Gradle.
2. Kiểm tra compiler có yêu cầu annotation processing hay chưa.
3. Kiểm tra processor classpath/module path có chứa đúng artifact và transitive dependencies.
4. Kiểm tra processor class name có được allowlist và service descriptor có đúng không.
5. Bật `-XprintProcessorInfo` và `-XprintRounds` để xem processor nào được gọi và số round.
6. Bật `-Xlint:processing` để tìm annotation chưa được processor claim.
7. Kiểm tra generated source directory có file mới hay file cũ từ lần build trước.
8. Kiểm tra processor có tương thích với JDK/compiler đang dùng không.

Ví dụ chẩn đoán bằng javac:

```bash
javac \
  --release 26 \
  --processor-path processors/my-processor.jar \
  -processor com.example.MyProcessor \
  -XprintProcessorInfo \
  -XprintRounds \
  -Xlint:processing \
  -s build/generated \
  -d build/classes \
  src/main/java/example/Example.java
```

Trong Maven, chạy `mvn -X compile` để xem compiler arguments được plugin truyền xuống. Trong Gradle, dùng `./gradlew compileJava --info` để xem task và processor behavior. Không đưa toàn bộ debug output chứa đường dẫn nội bộ hoặc environment nhạy cảm vào issue công khai.

### Triệu chứng thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Thiếu generated class sau khi nâng JDK 23+ | Processor không còn tự chạy mặc định | Khai báo processor path và processor class tường minh |
| Annotation vẫn compile nhưng không có validation | Processor chỉ kiểm tra, không sinh code; processing đã tắt | Xác nhận processor được gọi bằng `-XprintProcessorInfo` |
| `NoSuchMethodError` trong processor | Processor hoặc dependency không tương thích compiler/JDK | Cập nhật processor và đồng bộ dependency |
| `ClassNotFoundException` khi load processor | Processor dependency thiếu trên processor path | Bổ sung dependency vào processor configuration |
| `FilerException: Attempt to recreate a file` | Processor sinh trùng tên file trong cùng compile/round | Sửa logic round và kiểm tra file đã được tạo chưa |
| Annotation không được claim | Processor không hỗ trợ annotation đó hoặc tên package sai | Kiểm tra `@SupportedAnnotationTypes`, bật `-Xlint:processing` |
| Gradle build sinh output stale | Processor không khai báo input hoặc incremental category sai | Khai báo input và metadata incremental đúng; clean output khi cần |
| Processor lạ chạy trong CI | Discovery trên classpath rộng hoặc `-proc:full` không giới hạn | Dùng processor path riêng và allowlist class processor |
| Maven/Gradle chạy khác nhau | Processor path, JDK toolchain hoặc plugin version khác | So sánh effective POM, compiler args và dependency configuration |

## 13. Annotation processor khác compiler plugin và runtime annotation

| Cơ chế | Thời điểm | Vai trò |
|---|---|---|
| Annotation processor | Compile time | Đọc annotation/model, kiểm tra và sinh source/resource |
| Compiler plugin (`javac -Xplugin`) | Trong compiler | Mở rộng hành vi compiler bằng API plugin riêng; không đồng nghĩa với annotation processor |
| Runtime reflection | Khi ứng dụng chạy | Đọc annotation/runtime metadata và thực hiện logic trong ứng dụng |
| Build plugin (Maven/Gradle) | Trong build lifecycle | Thực hiện task như generate source, copy resource, đóng gói hoặc kiểm tra |

Một annotation có thể được dùng bởi processor ở compile time, reflection ở runtime hoặc cả hai, tùy `RetentionPolicy`. Processor không bắt buộc annotation phải có `RUNTIME`; annotation `SOURCE` hoặc `CLASS` cũng có thể được processor đọc trong compilation environment.

Nếu một thư viện dùng annotation cho code generation, annotation API có thể cần ở compile classpath nhưng processor không cần trong runtime. Nếu ứng dụng dùng reflection để đọc annotation lúc chạy, annotation cần retention phù hợp và artifact chứa annotation phải có trong runtime classpath.

## 14. Bài tập thực hành

Một dự án dùng MapStruct để sinh implementation cho mapper. Dự án chạy được trên JDK 21 nhưng sau khi chuyển compiler sang JDK 26, build báo thiếu implementation class.

**Yêu cầu:**

1. Tách annotation API và processor artifact thành hai dependency riêng.
2. Chạy `javac` trực tiếp với `--processor-path` và `-processor` để sinh implementation.
3. Cấu hình Maven 3 Compiler Plugin 3.x bằng `annotationProcessorPaths` và `annotationProcessors`.
4. Cấu hình Maven 4 Compiler Plugin 4.x bằng dependency type `classpath-processor`.
5. Cấu hình Gradle bằng `annotationProcessor` và `testAnnotationProcessor`.
6. Bật `-XprintProcessorInfo`, `-XprintRounds` và `-Xlint:processing` để xác nhận processor chạy.
7. Thử bỏ processor declaration và quan sát khác biệt trên JDK 26.
8. Thử `-proc:none` để xác nhận processing bị tắt.
9. Kiểm tra generated source được đặt trong thư mục build, không bị trộn với source viết tay.
10. Kiểm tra dependency tree của processor và đánh giá rủi ro khi một dependency transitive đăng ký processor khác.

**Kết quả mong đợi:**

- Người học giải thích được thay đổi mặc định từ JDK 23 và lý do bảo mật.
- Processor được khai báo rõ ràng, không phụ thuộc discovery trên compile classpath.
- Annotation API không bị nhầm với processor implementation.
- Maven và Gradle đặt processor vào đúng path.
- Build có thể tái lập nhờ pin version và kiểm soát dependency transitive.
- Generated source được quản lý bởi build tool và có thể kiểm tra khi cần.
- Không cần `--enable-preview` cho annotation processing; đây là cơ chế compiler đã ổn định từ lâu.

## Tài liệu tham khảo

- [The `javac` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): tùy chọn `-processor`, `--processor-path`, `--processor-module-path`, `-proc` và vòng đời processing rounds.
- [JDK 23 Release Notes — Annotation processing in javac disabled by default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): lý do và thay đổi mặc định từ JDK 23.
- [Apache Maven Compiler Plugin — Annotation processors](https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html): cấu hình Maven 3, Maven 4 và lý do không nên chỉ bật `proc`.
- [Apache Maven Compiler Plugin — compile goal](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/compile-mojo.html): `annotationProcessors`, processor paths, `proc` và các tùy chọn compiler.
- [Gradle Java Plugin — Dependency management](https://docs.gradle.org/current/userguide/java_plugin.html): `annotationProcessor`, `testAnnotationProcessor` và source-set processor configurations.
- [Gradle CompileOptions API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): `annotationProcessorPath`, compiler args và generated source output.
- [Gradle Java Library Plugin — Declaring an annotation processor](https://docs.gradle.org/current/userguide/java_library_plugin.html): tách annotation API khỏi processor dependency.
- [Java SE 26 `javax.annotation.processing` package](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/package-summary.html): API chuẩn để viết annotation processor.
