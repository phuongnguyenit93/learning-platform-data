# Phân biệt đồ thị được khai báo với các tệp thực tế được nạp

Khi khai báo dependency trong Gradle, ta thường viết tọa độ thư viện như `org.example:service-client:2.0`. Nhưng một tọa độ không phải là một file JAR, và danh sách dependency trong build script cũng chưa phải là danh sách file mà một task hoặc JVM thực sự sử dụng.

Để hiểu chính xác dependency của một project, cần phân biệt nhiều lớp: **khai báo dependency**, **đồ thị dependency sau khi Gradle phân giải**, **artifact/file được resolve**, **classpath được cung cấp cho task**, và **class mà JVM thực sự nạp khi chương trình chạy**. Các lớp này có liên quan nhưng không tương đương. Nhầm chúng với nhau dễ dẫn đến kết luận sai khi debug lỗi thiếu class, xung đột phiên bản, dung lượng artifact hoặc hành vi runtime.

## 1. Năm lớp cần phân biệt

Có thể theo dõi dependency qua luồng tổng quát:

~~~text
dependencies { ... }
Khai báo trực tiếp và quy tắc dependency
              |
              v
Dependency resolution
Chọn component, phiên bản và variant
              |
              v
Resolved dependency graph
Các node và cạnh sau khi giải quyết
              |
              v
Resolved artifacts / files
JAR, ZIP, directory hoặc file đã transform
              |
              v
Task classpath / packaged artifact
Tập file task sử dụng hoặc đóng gói
              |
              v
Runtime classloader
Nạp class/resource khi chương trình cần
~~~

| Lớp | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Khai báo | Project yêu cầu dependency nào? | `implementation 'org.example:client:2.0'` |
| Resolved graph | Gradle đã chọn component và phiên bản nào, theo quan hệ nào? | `client:2.0` kéo theo `http-core:5.1` |
| Artifact/file | Những artifact cụ thể nào được resolve? | `client-2.0.jar`, `http-core-5.1.jar` |
| Classpath/đóng gói | Task hoặc ứng dụng được cung cấp những file nào? | `runtimeClasspath` hoặc nội dung `bootJar` |
| Class loading | JVM thực sự nạp class/resource nào trong lần chạy? | `Client.class` được nạp khi code gọi đến |

Điểm quan trọng là một dependency được khai báo không nhất thiết tương ứng với đúng một file; một component trong graph có thể không cung cấp file runtime; một artifact có thể chứa rất nhiều class; và JVM thường chỉ nạp một phần các class có sẵn trên classpath.

## 2. Khai báo dependency chưa phải dependency graph đã resolve

Khối `dependencies` mô tả yêu cầu của project. Ví dụ:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:service-client:2.0'
    runtimeOnly 'org.example:database-driver:4.1'
    testImplementation 'org.example:test-fixtures:1.3'
}
~~~

Đây là những dependency trực tiếp được khai báo. Khi đọc đoạn này, ta biết project yêu cầu:

- Service client dùng trong compile và runtime theo configuration `implementation`.
- Database driver chỉ tham gia runtime classpath theo `runtimeOnly`.
- Test fixtures phục vụ test theo `testImplementation`.

Tuy nhiên, đoạn khai báo chưa cho biết toàn bộ dependency bắc cầu mà Gradle sẽ chọn. `service-client` có thể phụ thuộc vào HTTP client, logging API hoặc thư viện serialization. Những dependency đó có thể xuất hiện trong graph dù không được viết trực tiếp trong khối `dependencies`.

Khai báo cũng có thể đi kèm constraints, platforms, exclusions, substitutions, dependency locking và attributes. Những quy tắc này ảnh hưởng kết quả phân giải.

### Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp** là dependency được project khai báo rõ ràng. **Dependency bắc cầu** là dependency được yêu cầu bởi một dependency khác thông qua metadata của module hoặc quan hệ project.

Ví dụ:

~~~text
Ứng dụng
  |
  +--> service-client:2.0
          |
          +--> http-core:5.1
          |
          +--> logging-api:2.0
~~~

Project chỉ khai báo `service-client:2.0`, nhưng graph có thể có thêm `http-core` và `logging-api`. Đây là lý do danh sách tọa độ trong build script thường ngắn hơn dependency graph đã resolve.

Dependency bắc cầu được xác định dựa trên metadata được cung cấp bởi module, chẳng hạn Gradle Module Metadata hoặc Maven POM. Nếu metadata không khai báo đúng, graph được xây dựng có thể không phản ánh đầy đủ những thư viện mà code thực sự cần.

### Một khai báo có thể bị thay đổi trong quá trình resolution

Yêu cầu phiên bản trong build script không luôn là phiên bản cuối cùng được chọn. Ví dụ, nhiều nhánh có thể yêu cầu các phiên bản khác nhau của cùng module:

~~~text
Ứng dụng
  |
  +--> feature-a
  |      |
  |      +--> shared-core:1.8
  |
  +--> feature-b
         |
         +--> shared-core:2.1
~~~

Gradle áp dụng quy tắc version selection, constraints và metadata để chọn phiên bản phù hợp. Với quy tắc mặc định thông thường cho cùng module, phiên bản cao hơn có thể được chọn; nhưng rich version constraints, platforms, strict constraints, capabilities hoặc resolution rules có thể làm kết quả khác đi.

Do đó, cần phân biệt **requested version** và **selected version**. Đọc tọa độ trong build script chỉ cho biết yêu cầu; dependency report mới cho biết kết quả phân giải.

## 3. Resolved dependency graph biểu diễn component và quan hệ

Sau khi một configuration được resolve, Gradle có dependency graph thể hiện những component được chọn và các quan hệ giữa chúng.

Một node trong graph có thể đại diện cho:

- External module dependency được lấy từ repository.
- Project dependency đến một project khác trong build.
- File dependency được khai báo trực tiếp.
- Platform hoặc component tham gia quản lý version/variant.
- Component được chọn sau substitution hoặc resolution rule.

Một cạnh biểu diễn quan hệ dependency giữa component yêu cầu và component được chọn. Graph cũng có thể phản ánh dependency bị loại bỏ, constraint, version conflict hoặc lựa chọn variant thông qua metadata và báo cáo resolution.

### Graph không phải danh sách đường dẫn file

Ví dụ graph:

~~~text
:app
  |
  +--> org.example:service-client:2.0
  |       |
  |       +--> org.example:http-core:5.1
  |       |
  |       +--> org.example:logging-api:2.0
  |
  +--> org.example:json-api:1.4
~~~

Graph cho biết component nào liên kết với component nào. Nó không trực tiếp cho biết file nằm ở đường dẫn cache nào, file đó được transform ra sao hoặc JVM đã nạp class nào.

Cùng một component có thể có nhiều artifact. Ngược lại, một artifact có thể chứa nhiều package/class. Một platform/BOM có thể tham gia graph để cung cấp constraints nhưng không nhất thiết tạo ra một JAR runtime tương ứng.

### Variant selection là một phần của resolution

Một module có thể cung cấp nhiều variant, chẳng hạn variant dành cho compile và runtime hoặc cho những phiên bản JVM khác nhau. Gradle dùng attributes của consumer configuration và producer variant để chọn thành phần phù hợp.

Ví dụ, `compileClasspath` thường yêu cầu usage dành cho compile, còn `runtimeClasspath` yêu cầu usage dành cho runtime. Cùng một module có thể được chọn qua variant tương ứng. Artifact cuối cùng có thể khác nhau theo variant.

Vì vậy, hai configuration có thể resolve graph tương tự nhưng lấy artifact khác nhau. Để hiểu kết quả, cần xem cả dependency graph và variant/artifact selection.

## 4. Artifact là file được component cung cấp

**Artifact** là nội dung file hoặc output mà component cung cấp cho consumer. Trong Java build, artifact thường là JAR, nhưng không phải lúc nào cũng chỉ có một JAR.

Một component có thể cung cấp:

- Một JAR chính.
- Nhiều artifact, ví dụ JAR chính và artifact bổ sung.
- Artifact có classifier như sources hoặc javadoc.
- Một directory hoặc file đã được biến đổi theo artifact type/attributes.
- Metadata/variant không cung cấp artifact runtime như một thư viện Java thông thường.

Artifact selection phụ thuộc configuration, variant, attributes, artifact type và yêu cầu của consumer.

### Một component không luôn tương ứng một file

Ví dụ một module có thể có nhiều artifact:

~~~text
org.example:compiler-tools:3.0
    |
    +--> compiler-tools-3.0.jar
    |
    +--> compiler-tools-3.0-model.jar
    |
    +--> compiler-tools-3.0-sources.jar
~~~

Tùy configuration và yêu cầu, Gradle có thể resolve artifact phù hợp. Không nên đếm số node trong graph rồi kết luận đó là số file JAR cuối cùng.

Một platform/BOM có thể xuất hiện trong graph nhưng vai trò của nó là cung cấp version constraints. Nó không nhất thiết xuất hiện như một JAR trên runtime classpath. Một dependency có thể được chọn nhưng không có artifact phù hợp cho mục đích runtime nếu metadata/variant không cung cấp file cần thiết.

### Artifact transform có thể tạo file khác với file tải về

Gradle hỗ trợ artifact transforms để chuyển đổi artifact từ dạng này sang dạng khác theo yêu cầu của consumer. Ví dụ, plugin hoặc build có thể yêu cầu dạng artifact đã giải nén hoặc đã được biến đổi.

Khi đó cần phân biệt:

- File gốc được tải từ repository và lưu trong dependency cache.
- Output được tạo bởi artifact transform.
- File mà task cuối cùng nhận được trên classpath hoặc file collection.

File task sử dụng có thể là output transform trong Gradle cache, không nhất thiết trùng với đường dẫn file archive gốc đã tải.

## 5. Dependency cache, artifact file và output của project

Có ba vùng file thường bị nhầm lẫn:

| Vùng | Chứa gì? | Ví dụ |
|---|---|---|
| Gradle dependency cache | Metadata và artifact được tải từ repository; có thể có dữ liệu transform | Gradle User Home |
| Project build directory | Output do task của project tạo ra | `build/classes`, `build/libs` |
| Runtime/package directory | File hoặc archive được triển khai/chạy | `app.jar`, thư mục distribution |

Một dependency được tải về không có nghĩa nó đã được đóng gói vào artifact của ứng dụng. Nó có thể chỉ được dùng trong compile classpath, test classpath hoặc một task build riêng.

Tương tự, một JAR trong `build/libs` có thể là artifact do project tạo ra, không phải dependency bên ngoài được tải về.

### File trong cache không đồng nghĩa file đang được sử dụng

Gradle có thể giữ nhiều phiên bản của cùng một module trong cache vì các build khác nhau cần những phiên bản khác nhau. Một file JAR nằm trong Gradle User Home không có nghĩa configuration hiện tại đã resolve nó hoặc task đang sử dụng nó.

Muốn biết file nào thuộc một configuration cụ thể, hãy xem file collection hoặc artifact result của chính configuration đó. Không nên dùng việc tìm file trong cache làm bằng chứng duy nhất về classpath.

## 6. Classpath là tập file có thể cung cấp class/resource

**Classpath** là danh sách các vị trí mà compiler hoặc JVM có thể tìm class và resource. Trong Java build, Gradle thường xây dựng compile classpath và runtime classpath cho từng source set.

- Compile classpath cung cấp class cần thiết cho compiler.
- Runtime classpath cung cấp class/resource cho ứng dụng hoặc test khi chạy.
- Annotation processor path cung cấp processor cho compiler; đây là một môi trường riêng, không nên đánh đồng với runtime classpath của ứng dụng.
- Plugin/build logic có classpath riêng phục vụ Gradle.

Ví dụ, `runtimeClasspath` có thể chứa:

~~~text
build/classes/java/main/
build/resources/main/
~/.gradle/caches/.../service-client-2.0.jar
~/.gradle/caches/.../http-core-5.1.jar
~/.gradle/caches/.../logging-api-2.0.jar
~/.gradle/caches/.../database-driver-4.1.jar
~~~

Đây là ví dụ minh họa. Đường dẫn thực tế phụ thuộc hệ điều hành, Gradle User Home, version, artifact transform và cấu hình project.

Classpath có thể chứa directory output của project, không chỉ JAR. Vì vậy, nếu chỉ lọc file có phần mở rộng `.jar`, có thể bỏ sót class được cung cấp từ thư mục output hoặc directory dependency.

### Compile classpath và runtime classpath khác nhau

Ví dụ:

~~~groovy
dependencies {
    implementation 'org.example:core-api:1.0'
    compileOnly 'org.example:container-api:1.0'
    runtimeOnly 'org.example:database-driver:1.0'
}
~~~

Compile classpath có thể nhìn thấy `core-api` và `container-api`. Runtime classpath thông thường có `core-api` và `database-driver`; `container-api` được kỳ vọng do môi trường runtime cung cấp nếu ứng dụng cần nó.

Do đó, file xuất hiện trong compile classpath không nhất thiết xuất hiện trong runtime classpath. File xuất hiện trong runtime classpath cũng không nhất thiết được compiler nhìn thấy.

## 7. Classpath không đồng nghĩa với class thực sự được JVM nạp

Đây là một ranh giới rất quan trọng.

Nếu một JAR nằm trên runtime classpath, JVM có thể tìm class trong JAR đó. Điều này không có nghĩa mọi class bên trong JAR đều được đọc hoặc nạp ngay khi chương trình bắt đầu.

JVM và classloader thường nạp class khi code cần đến class đó. Các class không được sử dụng có thể không bao giờ được nạp trong lần chạy đó. Resource cũng chỉ được đọc khi ứng dụng hoặc framework yêu cầu.

~~~text
runtimeClasspath
  |
  +--> library-a.jar
  |       +--> A.class
  |       +--> B.class
  |       +--> C.class
  |
  +--> library-b.jar
          +--> D.class
          +--> E.class

Ứng dụng thực thi:
  - A.class được tham chiếu -> có thể được load
  - B.class không được dùng -> có thể chưa từng được load
  - C.class chỉ dùng ở nhánh hiếm -> chỉ load nếu nhánh đó chạy
  - D.class được framework phát hiện -> có thể được load
  - E.class không được tham chiếu -> có thể chưa được load
~~~

Vì thế, cần dùng từ chính xác:

- **Resolved/downloaded**: Gradle đã phân giải hoặc lấy artifact.
- **On classpath**: file/directory có sẵn cho compiler hoặc classloader.
- **Packaged**: nội dung đã được đưa vào artifact phân phối.
- **Loaded**: JVM đã nạp class vào một classloader.
- **Initialized**: class đã trải qua quá trình khởi tạo theo quy tắc JVM.
- **Executed**: method hoặc code cụ thể đã được thực thi.

Những trạng thái này không thể thay thế cho nhau.

### Classloader ảnh hưởng class nào được nạp

Ứng dụng Java có thể dùng nhiều classloader, chẳng hạn classloader của ứng dụng, plugin framework, application server hoặc module system. Hai class cùng tên đầy đủ nhưng được nạp bởi hai classloader khác nhau có thể được JVM xem là hai kiểu khác nhau.

Do đó, chỉ biết một JAR có trên classpath chưa chắc giải thích đầy đủ class nào được nạp nếu ứng dụng có classloader tùy chỉnh, module layer hoặc container.

Nếu điều tra lỗi `ClassNotFoundException`, `NoClassDefFoundError` hoặc `ClassCastException`, cần xem classpath, classloader và thời điểm code truy cập class, không chỉ nhìn dependency graph.

## 8. Ví dụ: graph có nhiều dependency hơn phần khai báo

Giả sử ứng dụng khai báo:

~~~groovy
dependencies {
    implementation 'org.example:order-client:3.0'
}
~~~

Metadata của module cho biết:

~~~text
order-client:3.0
  +--> json-core:2.2
  +--> http-transport:4.0
          +--> logging-api:2.1
~~~

Graph sau resolution có thể là:

~~~text
:app
  |
  +--> order-client:3.0
          |
          +--> json-core:2.2
          |
          +--> http-transport:4.0
                  |
                  +--> logging-api:2.1
~~~

Runtime artifacts tương ứng có thể gồm:

~~~text
order-client-3.0.jar
json-core-2.2.jar
http-transport-4.0.jar
logging-api-2.1.jar
~~~

Build script chỉ khai báo một dependency trực tiếp, nhưng runtime classpath có nhiều file do dependency bắc cầu.

Nếu `http-transport` đồng thời kéo theo một phiên bản `logging-api` khác, Gradle sẽ giải quyết xung đột theo quy tắc và constraints. File cuối cùng trên runtime classpath là artifact của phiên bản được chọn, không phải mọi phiên bản được yêu cầu ban đầu.

## 9. Ví dụ: graph có component không trở thành runtime JAR

Một project có thể khai báo platform:

~~~groovy
dependencies {
    implementation platform('org.example:service-bom:5.0')
    implementation 'org.example:service-api'
    implementation 'org.example:service-json'
}
~~~

BOM cung cấp constraints để quản lý version cho các module liên quan. Nó tham gia quá trình resolution và có thể xuất hiện trong báo cáo graph, nhưng không nhất thiết trở thành một JAR mà ứng dụng cần nạp lúc chạy.

Các module `service-api` và `service-json` mới là những dependency cung cấp artifact tương ứng cho compile/runtime theo variant của chúng.

Điều này cho thấy số component trong graph và số file trên classpath không nhất thiết bằng nhau.

## 10. Exclusion, constraint và substitution làm graph khác khai báo ban đầu

Khai báo dependency không phải lúc nào cũng được giữ nguyên y như yêu cầu ban đầu. Một số cơ chế có thể thay đổi graph.

### Exclusion

Có thể loại một dependency bắc cầu khỏi một nhánh:

~~~groovy
dependencies {
    implementation('org.example:legacy-client:1.0') {
        exclude group: 'org.example', module: 'old-logging'
    }
}
~~~

Exclusion tác động đến graph được xây dựng từ dependency đó. Tuy nhiên, nếu một nhánh khác vẫn yêu cầu cùng module, module có thể tiếp tục xuất hiện trong graph qua nhánh kia.

Không nên dùng exclusion chỉ để che một lỗi version conflict mà chưa hiểu component nào đang cần module bị loại.

### Dependency constraint

Constraint có thể ảnh hưởng version được chọn mà không nhất thiết thêm một dependency mới như một yêu cầu trực tiếp:

~~~groovy
dependencies {
    constraints {
        implementation('org.example:shared-core:2.4') {
            because 'Use the version validated by the application'
        }
    }
}
~~~

Constraint tham gia version resolution. Nó có thể nâng, giới hạn hoặc yêu cầu version tùy loại constraint và cách khai báo.

### Dependency substitution

Resolution rule hoặc composite build có thể thay một module dependency bằng project dependency hoặc một component khác. Khi đó tọa độ được khai báo ban đầu không còn chỉ ra trực tiếp artifact cuối cùng.

Ví dụ, trong quá trình phát triển, một module bên ngoài có thể được thay bằng project local. Dependency graph sẽ phản ánh component được chọn sau substitution.

### Version conflict và dynamic version

Nếu khai báo dynamic version như `2.+` hoặc sử dụng version thay đổi, kết quả resolution có thể thay đổi theo metadata/repository ở các lần chạy khác nhau. Dependency locking và version catalog có thể giúp quản lý version rõ ràng hơn, nhưng version catalog tự nó không khóa toàn bộ graph.

Khi cần tái lập build, hãy xem selected versions và cân nhắc dependency locking/verification phù hợp.

## 11. Xem dependency graph bằng Gradle

Gradle có task báo cáo dependency graph.

### Xem graph của runtime classpath

~~~shell
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Report hiển thị các dependency trực tiếp và bắc cầu được resolve cho runtime classpath của project `app`. Ký hiệu trong report có thể cho biết dependency bị conflict, bị thay thế hoặc có trạng thái đặc biệt.

### Xem graph của compile classpath

~~~shell
./gradlew :app:dependencies --configuration compileClasspath
~~~

So sánh compile với runtime giúp xác định dependency nào chỉ cần khi biên dịch và dependency nào có mặt khi chạy.

### Xem vì sao một version được chọn

~~~shell
./gradlew :app:dependencyInsight --dependency logging-api --configuration runtimeClasspath
~~~

`dependencyInsight` tập trung vào một module, hiển thị các đường đi yêu cầu nó và lý do Gradle chọn version/variant tương ứng. Đây là công cụ hữu ích khi nghi ngờ version conflict hoặc dependency bắc cầu không mong muốn.

### Xem các configuration

~~~shell
./gradlew :app:dependencies
~~~

Lệnh này báo cáo các configuration dependency của project. Với project lớn, nên chỉ định configuration cần điều tra để output ngắn gọn và dễ đọc.

## 12. Xem các artifact/file thực tế đã resolve

Graph cho biết component và quan hệ; khi cần biết file thực tế, hãy inspect artifact hoặc file collection của configuration.

Ví dụ đơn giản trong Groovy build script:

~~~groovy
tasks.register('printRuntimeFiles') {
    doLast {
        configurations.runtimeClasspath.files
            .sort { it.absolutePath }
            .each { file ->
                println file.absolutePath
            }
    }
}
~~~

Khi chạy task này, Gradle resolve `runtimeClasspath` và in các file trong file collection. Kết quả có thể bao gồm JAR, file hoặc directory tùy dependency và variant.

Đây là ví dụ phục vụ quan sát. Trong task type dùng thật, nên khai báo classpath bằng property phù hợp như `@Classpath` hoặc `ConfigurableFileCollection` để Gradle quản lý input và dependency đúng cách; tránh resolve configuration quá sớm trong configuration phase.

### Inspect artifact result và component identity

Gradle API còn cho phép xem artifact result của một configuration:

~~~groovy
tasks.register('printResolvedArtifacts') {
    doLast {
        configurations.runtimeClasspath.incoming.artifacts.artifacts.each { artifact ->
            println artifact.id.componentIdentifier.displayName +
                ' -> ' + artifact.file.absolutePath
        }
    }
}
~~~

Cách này giúp nối thông tin component với file artifact mà Gradle cung cấp. Khi cần điều tra sâu hơn, có thể xem thêm variant và artifact identifier từ API tương ứng.

### Xem graph bằng ResolutionResult

Có thể đọc các component và quan hệ dependency từ `ResolutionResult`:

~~~groovy
import org.gradle.api.artifacts.result.ResolvedDependencyResult

tasks.register('printResolvedGraph') {
    doLast {
        def result = configurations.runtimeClasspath.incoming.resolutionResult

        result.allComponents.each { component ->
            println component.id.displayName

            component.dependencies.each { dependency ->
                if (dependency instanceof ResolvedDependencyResult) {
                    println '  -> ' + dependency.selected.id.displayName
                }
            }
        }
    }
}
~~~

Đây là ví dụ quan sát graph ở mức component. Nó không in đường dẫn file; muốn xem file, cần inspect artifact results hoặc file collection như phần trước.

Trong build logic thực tế, cần lưu ý rằng việc truy cập `resolutionResult` hoặc file collection sẽ kích hoạt resolution của configuration. Hãy chỉ resolve configuration có chủ đích, thường trong task execution hoặc nơi API cho phép, và không truy cập cấu hình không dành cho resolution.

## 13. So sánh graph, artifact và runtime class loading khi debug

Mỗi loại lỗi cần kiểm tra đúng lớp.

| Triệu chứng | Lớp cần kiểm tra đầu tiên | Công cụ/hướng kiểm tra |
|---|---|---|
| Không tìm thấy dependency trong repository | Repository và resolution | Log `--info`, repository/credential |
| Chọn sai phiên bản | Resolved graph | `dependencies`, `dependencyInsight` |
| Graph có module nhưng không thấy file mong muốn | Variant và artifact selection | Dependency report, artifact results, attributes |
| Compiler không tìm thấy class | Compile classpath | `compileClasspath`, task compile log |
| Ứng dụng thiếu class lúc chạy | Runtime classpath/packaged artifact | `runtimeClasspath`, nội dung artifact, classloader |
| Test chạy thiếu class | Test runtime classpath | `testRuntimeClasspath`, test worker log |
| File có trong classpath nhưng class vẫn không load | Class name, classloader, module access, runtime path | JVM diagnostics, classloader logging |
| Có nhiều JAR cùng chứa một class | Classpath order, shading, duplicate classes | Phân tích nội dung JAR và classloader |
| Artifact triển khai thiếu dependency | Packaging/distribution | Kiểm tra JAR/WAR/distribution thực tế |

### Trường hợp compile thành công nhưng runtime lỗi

Ví dụ, project khai báo dependency bằng `compileOnly`. Compiler tìm thấy class nên compile thành công. Nhưng runtime environment không cung cấp class đó. Khi code cần class, JVM có thể ném `ClassNotFoundException` hoặc `NoClassDefFoundError`.

Graph compile có thể có dependency đó, trong khi runtime classpath không có. Kiểm tra mỗi compile graph sẽ không phát hiện được vấn đề triển khai.

### Trường hợp dependency có trên runtime classpath nhưng không nằm trong JAR ứng dụng

Nếu tạo JAR thông thường bằng Java plugin, task `jar` thường đóng gói class/resource của project, không tự động gom tất cả dependency vào một JAR duy nhất. Dependency vẫn có thể nằm riêng trên runtime classpath và cần được cung cấp khi chạy.

Với executable/fat JAR hoặc distribution plugin, cách đóng gói có thể khác. Ví dụ Spring Boot plugin có task `bootJar` để đóng gói ứng dụng cùng dependency theo cấu trúc executable archive. Cần kiểm tra artifact được tạo thực tế thay vì suy luận từ runtime graph.

### Trường hợp file có trên classpath nhưng JVM không nạp class

Một JAR có thể chứa hàng nghìn class, trong khi lần chạy hiện tại chỉ dùng một phần nhỏ. Nếu một class không được tham chiếu, framework không quét đến hoặc nhánh code không chạy, JVM có thể không nạp class đó.

Vì vậy, danh sách file runtime classpath không phải bằng chứng về danh sách class đã được load. Muốn biết class nào thực sự được nạp, cần dùng thông tin runtime của JVM hoặc công cụ quan sát class loading.

## 14. Kiểm tra file trong artifact đã đóng gói

Nếu vấn đề xuất hiện sau deploy, cần kiểm tra artifact đầu ra chứ không chỉ dependency report.

Với JAR thông thường, có thể liệt kê nội dung:

~~~shell
jar tf build/libs/app.jar
~~~

Với ZIP:

~~~shell
unzip -l build/distributions/app.zip
~~~

Lệnh cụ thể phụ thuộc công cụ có sẵn trên hệ điều hành. Với Windows, có thể dùng công cụ JDK hoặc tiện ích archive tương ứng.

Kiểm tra artifact giúp xác nhận:

- Class của project đã được đóng gói chưa.
- Resource có xuất hiện không.
- Dependency có được đóng gói cùng không, nếu loại archive được cấu hình như vậy.
- Metadata như manifest có đúng không.
- Có nhầm artifact cũ hoặc file từ lần build trước không.

Một JAR thông thường có thể không chứa dependency bên ngoài. Nếu ứng dụng được triển khai bằng một thư mục lib riêng hoặc classpath do container cung cấp, phải kiểm tra cả cấu trúc distribution và lệnh khởi chạy.

## 15. Vì sao số dependency và số file không bằng nhau?

Có nhiều lý do:

1. Một dependency khai báo trực tiếp có thể kéo theo nhiều dependency bắc cầu.
2. Nhiều nhánh có thể yêu cầu cùng một module; graph có thể có nhiều cạnh nhưng chỉ chọn một component/version phù hợp.
3. Một component có thể cung cấp nhiều artifact hoặc artifact classifier.
4. Một platform/BOM có thể tham gia graph mà không tạo JAR runtime.
5. Artifact transform có thể tạo file mới từ artifact gốc.
6. Một project dependency có thể cung cấp output directory hoặc nhiều artifact.
7. File collection có thể chứa directory, không chỉ archive.
8. Một số file trên classpath không được JVM nạp trong lần chạy.
9. Một file JAR có thể chứa nhiều class và resource.
10. Một archive ứng dụng có thể gói nhiều dependency vào một file phân phối.

Vì vậy, không nên dùng số dòng trong dependency tree, số file trong Gradle cache, số JAR trên classpath hoặc số class đã load như những con số có thể thay thế nhau.

## 16. Một quy trình điều tra từ khai báo đến file thực tế

Khi cần xác định một thư viện có thực sự được dùng hay không, hãy đi từng lớp:

**Bước 1 — Tìm khai báo trực tiếp**

Xem khối `dependencies`, version catalog, platform và các cấu hình được áp dụng. Xác định dependency được khai báo trực tiếp ở project/source set nào.

**Bước 2 — Xem graph đã resolve**

Chạy `dependencies` cho đúng configuration. Xác định module bắc cầu, version được chọn, nhánh dependency và các dấu hiệu conflict/substitution.

**Bước 3 — Xem lý do chọn module**

Dùng `dependencyInsight` để hiểu vì sao một version được chọn, dependency đến từ đâu và constraint nào có ảnh hưởng.

**Bước 4 — Xem artifact/file**

Inspect `configuration.incoming.artifacts` hoặc file collection tương ứng. Xác định file nào được resolve, file có được transform hay không và có phải directory dependency không.

**Bước 5 — Xem classpath của task**

Kiểm tra task compile, test hoặc run đang dùng configuration nào. Không giả định task nào cũng dùng `runtimeClasspath`; từng task có thể có classpath riêng.

**Bước 6 — Xem artifact được đóng gói**

Liệt kê nội dung JAR/WAR/ZIP hoặc distribution. Xác định dependency được đóng gói, đặt ở thư mục riêng hay do runtime environment cung cấp.

**Bước 7 — Xem class loading khi runtime**

Nếu file đã có trên classpath nhưng lỗi vẫn xảy ra, điều tra classloader, module access, tên class, classpath order và thời điểm nạp class. Khi cần, bật logging/diagnostics của JVM phù hợp với môi trường.

## 17. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Một dòng dependency tương ứng một file JAR | Dependency có thể kéo theo nhiều component bắc cầu hoặc không cung cấp JAR runtime |
| Dependency tree là danh sách file trên disk | Tree biểu diễn component và quan hệ sau resolution |
| Version ghi trong build script luôn là version được dùng | Gradle có thể chọn version khác theo conflict, constraint và resolution rules |
| Component xuất hiện trong graph chắc chắn có file trên runtime classpath | Platform/constraint hoặc variant có thể không cung cấp runtime JAR |
| File trong Gradle cache chắc chắn đang được dùng | Cache có thể giữ nhiều version/artifact của những build khác |
| File trên classpath nghĩa là JVM đã load mọi class trong file | JVM thường nạp class theo nhu cầu |
| Runtime classpath giống nội dung của JAR ứng dụng | Archive plugin quyết định cách đóng gói; JAR thường không tự chứa mọi dependency |
| Compile classpath và runtime classpath giống nhau | `compileOnly`, `runtimeOnly`, variant và plugin tạo ra khác biệt |
| Một module chỉ có một artifact | Component có thể cung cấp nhiều artifact hoặc variant |
| File tải về luôn là file task sử dụng | Artifact transform có thể tạo output khác cho consumer |

## 18. Bảng tra cứu nhanh

| Muốn biết... | Xem ở đâu |
|---|---|
| Project khai báo dependency nào? | `dependencies { }` và version catalog |
| Dependency bắc cầu nào được chọn? | `dependencies --configuration ...` |
| Vì sao một version được chọn? | `dependencyInsight` |
| Component nào thuộc resolved graph? | `ResolutionResult` |
| File artifact nào được resolve? | `incoming.artifacts` |
| File/directory nào nằm trên classpath? | File collection của configuration/task |
| Artifact ứng dụng chứa những gì? | Liệt kê nội dung JAR/WAR/ZIP/distribution |
| Class nào JVM thực sự nạp? | JVM class-loading diagnostics hoặc công cụ runtime |

Khi điều tra dependency, hãy luôn nói rõ mình đang đề cập đến khai báo, graph đã resolve, artifact/file, classpath hay class đã được JVM nạp. Cách gọi tên chính xác này giúp xác định đúng công cụ cần dùng và tránh nhầm một component trong dependency tree với một file thực tế hoặc một class đã chạy trong ứng dụng.
