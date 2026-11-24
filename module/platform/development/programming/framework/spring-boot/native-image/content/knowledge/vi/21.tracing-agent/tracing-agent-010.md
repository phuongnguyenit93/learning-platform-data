# Build lại và kiểm thử native sau khi kết hợp hints với kết quả agent

## 1. Mục tiêu của bước kết hợp và kiểm thử

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để kiểm tra tính tương thích, thời gian khởi động, bộ nhớ và khả năng vận hành trong container. Khi ứng dụng có reflection, resource lookup, dynamic proxy, serialization hoặc JNI, nhóm phát triển có thể dùng **Native Image Tracing Agent** để quan sát các đường truy cập động trên JVM và sinh reachability metadata.

Kết quả agent chỉ là một nguồn thông tin. Một ứng dụng Spring Boot còn có thể có:

- Spring Runtime Hints được khai báo bằng RuntimeHintsRegistrar, @ImportRuntimeHints hoặc annotation binding.
- Metadata Native Image do dependency JAR cung cấp.
- Metadata lấy từ GraalVM Reachability Metadata Repository.
- Metadata do tracing agent ghi nhận từ các test hoặc luồng ứng dụng đã chạy.
- Cấu hình bổ sung được nhóm phát triển review và duy trì trong source.

Mục tiêu của bài này là kết hợp các nguồn đó thành đầu vào native build có thể tái lập, sau đó build lại và chạy cùng một bộ kiểm thử trên native executable. Không nên xem việc agent sinh được JSON hoặc native compiler trả exit code 0 là bằng chứng cuối cùng. Kết quả cần chứng minh ứng dụng đã giữ đúng hành vi sau khi hợp nhất metadata.

Sau bài học, người học có thể:

1. Phân biệt Spring Runtime Hints, metadata của dependency và metadata tracing agent.
2. Thu thập metadata từ nhiều scenario JVM vào cùng một thư mục an toàn.
3. Review, lọc và hợp nhất kết quả agent với metadata hiện có.
4. Đặt metadata đã duyệt vào classpath native build đúng vị trí.
5. Cấu hình metadata copy cho Maven/Gradle Native Build Tools.
6. Build lại executable bằng đúng GraalVM/toolchain và kiểm tra output.
7. Chạy native unit/integration/smoke tests với cùng dữ liệu đã dùng trên JVM.
8. Phát hiện metadata thiếu, metadata thừa, sai version hoặc lỗi do environment/platform.
9. Ghi lại bằng chứng, coverage và quyết định phát hành.

> **Nguyên tắc:** agent ghi nhận những truy cập đã xảy ra trong các process được instrument. Spring hints mô tả nhu cầu đã được khai báo trong code. Dependency metadata mô tả nhu cầu của thư viện. Hãy giữ nguồn gốc của từng cấu hình rõ ràng, review kết quả rồi mới dùng để build native.

## 2. Ba nguồn metadata phối hợp như thế nào?

### 2.1. Spring Runtime Hints

Spring Runtime Hints được khai báo trong source code thông qua API Spring Framework. Ví dụ, một registrar đăng ký constructor của plugin và resource template:

~~~java
public final class OrderRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            OrderPlugin.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("templates/order-*.txt");
    }
}
~~~

Registrar được kết nối với application context bằng annotation @ImportRuntimeHints. Spring AOT xử lý những hints này trong quá trình chuẩn bị ứng dụng. Hãy giữ chúng trong source code để reviewer thấy được lý do và test có thể xác minh bằng RuntimeHintsPredicates.

### 2.2. Metadata của thư viện

Dependency có thể đóng gói reachability metadata trong thư mục META-INF/native-image/ của chính JAR, hoặc metadata có thể được Native Build Tools lấy từ GraalVM Reachability Metadata Repository. Các cấu hình này mô tả nhu cầu của dependency theo artifact/version tương ứng.

Không chép metadata từ một version dependency khác rồi giả định nó phù hợp. Khi nâng version thư viện hoặc GraalVM, phải kiểm tra lại schema, điều kiện version và feature liên quan.

### 2.3. Kết quả tracing agent

Tracing agent gắn vào **JVM process** và quan sát những truy cập động xảy ra trong lúc chương trình chạy. Nó có thể ghi metadata cho reflection, resource, dynamic proxy, JNI và các cơ chế được Native Image hỗ trợ.

Agent không tự biết một luồng nghiệp vụ chưa chạy sẽ cần gì. Nếu test chỉ đi qua luồng tạo đơn hàng thành công, metadata cho retry, lỗi validation, plugin khác hoặc profile khác có thể không xuất hiện.

### 2.4. Sơ đồ luồng tổng thể

~~~mermaid
flowchart TD
    A[Spring RuntimeHints trong source] --> D[Spring AOT processing]
    B[Dependency JAR và metadata repository] --> E[Native classpath]
    C[JVM scenarios chạy với tracing agent] --> F[Agent metadata output]
    F --> G[Review, lọc và hợp nhất]
    G --> H[META-INF/native-image trong application resources]
    D --> I[Native Build Tools]
    E --> I
    H --> I
    I --> J[GraalVM Native Image build]
    J --> K[Native executable]
    K --> L[Native unit/integration/smoke tests]
    L --> M[Compatibility và release evidence]
~~~

Đây là sơ đồ khái niệm. Task graph, generated output và cách metadata được copy phụ thuộc version Spring Boot và Native Build Tools đang dùng.

## 3. Chuẩn bị trước khi chạy agent

Trước khi thu thập metadata, chốt cùng một cấu hình cho JVM run và native build:

- Commit/source revision đang kiểm tra.
- Spring Boot và Spring Framework version.
- JDK/GraalVM distribution và version.
- Maven/Gradle Native Build Tools version.
- Dependency graph và profile được bật.
- OS/architecture của build host và target runtime.
- Test fixtures, environment variables và external services cần dùng.
- Các Runtime Hints đã được khai báo trong source.
- Metadata hiện có trong dependency JAR và application resources.

Ghi version của GraalVM JDK:

~~~bash
java -version
native-image --version
~~~

Nếu Gradle dùng Java toolchain hoặc Maven plugin chọn một GraalVM khác với terminal, kiểm tra log native build để xác nhận executable và toolchain thực sự được sử dụng. Tracing agent nên đến từ GraalVM JDK tương ứng với toolchain build; không trộn output từ nhiều phiên bản agent/schema mà không kiểm tra tương thích.

### 3.1. Tạo thư mục làm việc riêng cho agent

Trong ví dụ, dùng:

~~~text
target/
└── tracing-agent/
~~~

Đây là thư mục tạm để thu thập và review. Không ghi trực tiếp output đầu tiên vào thư mục metadata đã được duyệt trong source nếu chưa biết agent sẽ tạo những file nào. Giữ một bản output thô giúp có thể so sánh và loại bỏ entries không cần thiết.

Đối với Gradle, thư mục output mặc định của plugin thường nằm dưới build/native/agent-output/<taskName>. Với Maven, Native Build Tools có thể dùng target/native/agent-output. Xem đúng log/plugin version trước khi sao chép.

### 3.2. Xác định scenario cần chạy

Tạo danh sách các đường đi có truy cập động. Với một dịch vụ Spring Boot, có thể gồm:

| Nhóm | Scenario cần chạy |
| --- | --- |
| Reflection | Tạo từng implementation plugin được cấu hình, gọi constructor/method cần thiết. |
| Binding/JSON | DTO thường, record, generic collection, nested DTO, polymorphic subtype. |
| Resource | Đọc template, schema, certificate, resource bundle và file cấu hình trên classpath. |
| Proxy | Tạo các JDK dynamic proxy hoặc proxy integration mà ứng dụng dùng. |
| Serialization | Serialize/deserialize các kiểu thực tế, bao gồm error payload nếu có. |
| JNI/native library | Load và gọi các đường native integration nếu ứng dụng có dùng. |
| Error paths | Validation error, retry, fallback, exception mapping và dữ liệu không hợp lệ. |
| Profile/configuration | Các profile hoặc feature flag làm thay đổi class/resource được chọn. |

Chỉ đưa vào danh sách những feature thực sự thuộc ứng dụng. Scenario cần có dữ liệu đại diện và kết quả mong đợi để sau này chạy lại trên native executable.

## 4. Thu thập metadata từ JVM bằng tracing agent

### 4.1. Chạy ứng dụng Spring Boot dạng executable JAR

Sau khi tạo JAR JVM, chạy với agent:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar
~~~

Thay orders-service.jar bằng artifact thực tế. Agent option phải xuất hiện trước -jar và các application arguments. Nếu dùng profile hoặc tham số ứng dụng, đặt chúng sau tên JAR:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check
~~~

Sau khi ứng dụng khởi động, gọi các API hoặc chạy kịch bản đã lập. Khi hoàn tất, dừng ứng dụng một cách graceful để JVM thoát và agent ghi metadata cuối cùng. Với ứng dụng server chạy lâu, có thể dùng tùy chọn ghi định kỳ như config-write-period-secs nếu phù hợp với GraalVM version; vẫn cần kiểm tra output sau khi process kết thúc.

**Agent phải chạy trên JVM.** Không gắn native-image-agent vào native executable đã build. Native executable không phải JVM process để agent này instrument.

### 4.2. Thu thập nhiều scenario vào cùng thư mục

Lần chạy đầu dùng config-output-dir để tạo tập metadata:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=orders
~~~

Các lần chạy tiếp theo dùng config-merge-dir để bổ sung vào cấu hình đã có:

~~~bash
java \
  -agentlib:native-image-agent=config-merge-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=payments
~~~

Tiếp tục với scenario resource, error handling hoặc plugin khác:

~~~bash
java \
  -agentlib:native-image-agent=config-merge-dir=target/tracing-agent \
  -jar target/orders-service.jar \
  --spring.profiles.active=native-check \
  --app.test-scenario=error-paths
~~~

config-merge-dir yêu cầu agent mở rộng tập cấu hình hiện có thay vì ghi đè kết quả của lần chạy trước. Nếu nhiều process chạy đồng thời, không cho chúng cùng ghi vào một thư mục. Hãy dùng output directory riêng theo process/scenario rồi hợp nhất bằng công cụ hỗ trợ của GraalVM hoặc chạy tuần tự với config-merge-dir.

Nếu một ứng dụng chỉ thoát khi nhận tín hiệu dừng, bảo đảm shutdown hook chạy và agent có cơ hội ghi file. Không đọc thư mục output khi process vẫn đang ghi mà kết luận file đã hoàn chỉnh.

### 4.3. Chạy agent thông qua JAVA_TOOL_OPTIONS

Khi không thể sửa lệnh khởi chạy, có thể inject agent qua JAVA_TOOL_OPTIONS:

~~~bash
export JAVA_TOOL_OPTIONS="-agentlib:native-image-agent=config-output-dir=target/tracing-agent"
./mvnw spring-boot:run
~~~

Cách này phụ thuộc shell, launcher và cách process con kế thừa environment. Nếu có nhiều JVM process cùng nhận biến này, mỗi process phải có output directory riêng để tránh ghi đè hoặc xung đột.

Sau khi thu thập xong, bỏ JAVA_TOOL_OPTIONS trước khi chạy test JVM thông thường hoặc native build. Không vô tình tiếp tục thu thập metadata ở những lần build không chủ đích.

## 5. Dùng Maven Native Build Tools để thu thập và copy metadata

Maven plugin có thể tự gắn agent vào test process và copy metadata về project. Cấu hình cụ thể phụ thuộc version plugin; ví dụ cấu trúc trong native-maven-plugin:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <agent>
            <enabled>true</enabled>
            <metadataCopy>
                <merge>true</merge>
                <outputDirectory>
                    src/main/resources/META-INF/native-image/com.example/orders-service
                </outputDirectory>
            </metadataCopy>
        </agent>
    </configuration>
</plugin>
~~~

Đây là đoạn cấu hình minh họa để ghép vào plugin/profile đã có. Giữ nguyên version, executions, mainClass, build arguments và các cấu hình Spring Boot hiện tại.

Có thể bật agent cho một lần chạy cụ thể bằng property:

~~~bash
./mvnw -Pnative -Dagent=true test
~~~

Nếu đã cấu hình metadataCopy, chạy goal copy theo plugin version:

~~~bash
./mvnw -Pnative -Dagent=true test native:metadata-copy
~~~

Nếu cấu hình POM đặt enabled là true cố định, agent sẽ tiếp tục được gắn vào các lần chạy Maven tiếp theo. Sau khi thu thập/copy xong, tắt agent trong cấu hình hoặc chuyển việc bật agent sang profile/property chỉ dùng cho bước thu thập. Sau đó chạy lại test/build **không bật agent** để xác nhận metadata đã được copy và native build dùng kết quả đã duyệt. Nếu dùng một profile Maven khác với native, điều chỉnh lệnh theo profile thật của project.

metadataCopy có thể merge output với metadata đã tồn tại trong output directory khi cấu hình merge bật. Điều này hữu ích để tránh ghi đè metadata thủ công đã có. Vẫn cần review nội dung sau khi copy; merge kỹ thuật không thay thế việc đánh giá từng entry.

## 6. Dùng Gradle Native Build Tools để thu thập và copy metadata

Trong build.gradle.kts, có thể cấu hình agent và metadata copy theo DSL của plugin:

~~~kotlin
graalvmNative {
    agent {
        enabled.set(true)

        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add(
                "src/main/resources/META-INF/native-image/com.example/orders-service"
            )
            mergeWithExisting.set(true)
        }
    }
}
~~~

Với Groovy DSL, cú pháp property setter có thể dùng dạng assignment theo version plugin:

~~~groovy
graalvmNative {
    agent {
        enabled = true

        metadataCopy {
            inputTaskNames.add("test")
            outputDirectories.add(
                "src/main/resources/META-INF/native-image/com.example/orders-service"
            )
            mergeWithExisting = true
        }
    }
}
~~~

Chạy test JVM với agent:

~~~bash
./gradlew -Pagent test
~~~

Sau khi test đã chạy và agent sinh metadata, copy về resources:

~~~bash
./gradlew metadataCopy
~~~

Sau đó tắt agent, chạy test/build native bình thường:

~~~bash
./gradlew clean test
./gradlew nativeTest
./gradlew nativeCompile
~~~

Nếu plugin version yêu cầu chỉ rõ mode, dùng mode đã cấu hình, ví dụ -Pagent=standard. Với Gradle java-library, plugin có thể chọn conditional mode làm mặc định; mode đó cần user-code filter. Đọc log để xác định mode và task nào đã được instrument.

inputTaskNames phải trùng tên task đã chạy với agent, chẳng hạn test, run hoặc task integration test riêng. outputDirectories là vị trí nhận metadata; mergeWithExisting quyết định có merge với metadata đã tồn tại ở đích hay không.

## 7. Review và hợp nhất kết quả agent với hints hiện có

Đây là bước quan trọng nhất trước khi build lại. Metadata agent là dữ liệu quan sát; nó có thể chứa entries thừa, thiếu hoặc phụ thuộc test framework.

### 7.1. Kiểm tra danh sách file và format

Liệt kê output directory:

~~~text
target/tracing-agent/
├── reachability-metadata.json
└── ...
~~~

Tùy GraalVM release, agent có thể tạo một file reachability-metadata.json hoặc các file cấu hình riêng như reflect-config.json, resource-config.json, proxy-config.json, serialization-config.json và jni-config.json. Dùng format mà GraalVM version đang build hỗ trợ. Không tự đổi schema bằng cách đổi tên file.

Kiểm tra JSON hợp lệ và đọc các nhóm metadata. Chú ý:
- Reflection entries: type, constructor, method, field và access category.
- Resource entries: glob/pattern và điều kiện.
- Proxy entries: interface set.
- Serialization entries: kiểu được serialize/deserialize.
- JNI entries: class/member được truy cập từ native code.
- Conditional metadata: điều kiện typeReached hoặc điều kiện khác nếu schema/version hỗ trợ.

### 7.2. Phân biệt ba thao tác merge

| Thao tác | Mục đích | Nơi áp dụng |
| --- | --- | --- |
| Agent config-merge-dir | Bổ sung kết quả từ lần chạy JVM tiếp theo vào metadata agent đã có. | Thư mục output của tracing agent. |
| Native Build Tools metadataCopy với merge bật | Copy và hợp nhất agent output với metadata đã có tại thư mục đích. | Application resources hoặc metadata output directory. |
| Spring AOT xử lý Runtime Hints | Chuyển hints khai báo trong source thành đầu vào AOT/native. | Application context và generated AOT outputs. |

config-merge-dir không tự đọc mọi RuntimeHintsRegistrar trong source. metadataCopy cũng không thay thế Spring AOT. Hãy giữ registrar trong source và để Spring AOT xử lý nó theo build pipeline.

### 7.3. Không ghi đè metadata thủ công

Giả sử source đã có:

~~~text
src/main/resources/
└── META-INF/native-image/
    └── com.example/orders-service/
        └── reachability-metadata.json
~~~

Nếu agent được copy vào đúng thư mục này, bật merge theo khả năng của plugin. Nếu không bật merge, metadata cũ có thể bị ghi đè. Trước khi chạy copy, commit hoặc sao lưu file đã có để có thể review diff.

Nếu metadata đang được duy trì dưới nhiều thư mục con, có thể để từng nguồn ở classpath entry riêng và cho Native Image đọc chúng. Không cần gom tất cả thành một file chỉ vì muốn có một nơi quản lý; điều quan trọng là classpath build chứa đúng metadata và mỗi entry có nguồn gốc rõ ràng.

### 7.4. Phân biệt metadata agent với Spring-generated output

Spring AOT có thể sinh mã và metadata trong build output. Không chỉnh trực tiếp file generated để thêm entries agent, vì build sau có thể ghi đè. Hãy:

- Giữ RuntimeHintsRegistrar và annotation trong source.
- Giữ metadata agent đã review trong application resources hoặc nơi plugin hỗ trợ.
- Giữ metadata thư viện trong dependency artifact.
- Kiểm tra native build classpath để xác nhận tất cả nguồn được sử dụng.

Nếu một truy cập đã được Spring hints mô tả và agent cũng ghi nhận, hãy kiểm tra hai entry có cùng mục tiêu hay khác phạm vi. Trùng lặp không phải lúc nào cũng gây lỗi, nhưng cần tránh duy trì hai cấu hình rộng và không rõ nguồn.

## 8. Lọc metadata thừa và loại bỏ dấu vết test framework

Khi agent chạy trên JUnit hoặc integration test, nó có thể quan sát các truy cập từ JUnit, Gradle/Maven test launcher, logging và thư viện test. Những entries đó có thể không cần trong executable production.

### 8.1. Giữ built-in filters

Tracing agent có built-in caller filters và heuristic filters để loại bớt truy cập mà Native Image đã hỗ trợ hoặc không cần khai báo. Không tắt chúng chỉ để tạo file metadata lớn hơn. Việc tắt filter thường tạo ra cấu hình kém hữu ích và nhiều noise.

### 8.2. Caller filter và access filter khác nhau

- **Caller filter** lọc dựa trên class/method thực hiện truy cập động.
- **Access filter** lọc class/member/resource là đích của truy cập.

Chỉ thêm filter tùy chỉnh khi đã hiểu entry nào không cần. Ví dụ, có thể loại caller thuộc test harness nếu chắc chắn chúng không phải đường chạy production. Không loại toàn bộ package của một thư viện chỉ vì test output có nhiều entries; ứng dụng có thể cần một phần của thư viện đó.

Cấu trúc filter và tên option phụ thuộc GraalVM version. Đối chiếu tài liệu agent trước khi áp dụng caller-filter-file hoặc access-filter-file.

### 8.3. Review theo tính năng

Với từng entry agent sinh ra, hỏi:

1. Entry thuộc code ứng dụng, thư viện production hay test harness?
2. Scenario nào đã tạo entry đó?
3. Feature nào của ứng dụng cần entry?
4. Entry có được Spring Runtime Hints hoặc dependency metadata mô tả rồi không?
5. Có thể thu hẹp từ toàn bộ member sang constructor/method/field cụ thể không?
6. Nếu xóa entry, test native nào sẽ chứng minh nó không cần?

Không xóa hàng loạt metadata chỉ để giảm file. Hãy dùng diff và native regression tests để xác nhận mỗi lần thu hẹp.

## 9. Đưa metadata đã duyệt vào native classpath

Vị trí thường dùng trong application resources:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── orders-service/
                └── reachability-metadata.json
~~~

Sau khi resource processing:
- Maven thường copy vào target/classes/META-INF/native-image/...
- Gradle thường copy vào build/resources/main/META-INF/native-image/...

Kiểm tra output:

~~~bash
find target/classes/META-INF/native-image -type f
~~~

hoặc:

~~~bash
find build/resources/main/META-INF/native-image -type f
~~~

Nếu dùng PowerShell, có thể dùng Get-ChildItem -Recurse với đường dẫn tương ứng.

Đóng gói JAR và kiểm tra:

~~~bash
jar tf target/orders-service.jar
~~~

Spring Boot executable JAR thường đặt application resources dưới BOOT-INF/classes/; dependency JAR nằm dưới BOOT-INF/lib/. Native Build Tools tích hợp Spring Boot cần chuẩn bị classpath native phù hợp. Đừng chỉ thấy metadata trong archive rồi kết luận nó đã được native task sử dụng. Hãy xác nhận native build log và output classpath.

Nếu dùng directory metadata bên ngoài classpath, GraalVM có tùy chọn cấu hình directory theo phiên bản, ví dụ -H:ConfigurationFileDirectories. Ưu tiên cơ chế Native Build Tools/Spring Boot đang hỗ trợ và ghi lại cách metadata được truyền vào build để tái lập.

## 10. Build lại native từ đầu

Sau khi metadata đã được review và copy vào source resources, thực hiện build mới. Clean build giúp loại output cũ khỏi lần xác minh; nó không xóa metadata trong src/main/resources.

### 10.1. Maven

Với profile native và plugin đã cấu hình:

~~~bash
./mvnw clean
./mvnw -Pnative test
./mvnw -Pnative package
~~~

Nếu project đã cấu hình native test execution, test có thể chạy cả JVM tests và native tests theo thứ tự do plugin quy định. Kiểm tra log/test report để xác định test nào đã chạy. Nếu chỉ muốn compile executable và tự chạy smoke tests:

~~~bash
./mvnw -Pnative -DskipTests package
~~~

Chỉ dùng -DskipTests khi đã chạy test ở bước riêng và có chủ đích bỏ qua test trong package phase. Không dùng cờ này rồi báo native test pass.

### 10.2. Gradle

Với Gradle Native Build Tools:

~~~bash
./gradlew clean
./gradlew test
./gradlew nativeTest
./gradlew nativeCompile
~~~

nativeTest chạy test trên native test executable nếu plugin/test engine đã được cấu hình. nativeCompile tạo executable chính. Nếu test suite dùng task riêng, cấu hình native test binary tương ứng hoặc chạy smoke/integration tests từ executable được build.

### 10.3. Kiểm tra log build

Xác nhận:

- Đúng JDK/GraalVM distribution và version.
- Đúng Native Build Tools plugin version.
- Spring AOT đã chạy và nhận diện configuration có @ImportRuntimeHints.
- Dependency graph đúng như compatibility matrix.
- Metadata application resources được copy vào output.
- Dependency metadata/repository được đưa vào native analysis.
- Không có warning JSON schema, missing registration hoặc conflicting initialization.
- Executable mới được tạo ở output path dự kiến.

Không lấy executable cũ để test sau khi metadata vừa thay đổi. Ghi timestamp/hash hoặc đường dẫn build output để bảo đảm đang chạy đúng binary mới.

## 11. Kiểm thử native sau khi kết hợp metadata

Bộ kiểm thử cần bao phủ đúng các scenario đã dùng để tạo metadata và các scenario quan trọng chưa từng chạy trong agent. Điều này giúp phát hiện metadata bị thiếu do coverage chưa đủ.

### 11.1. Chạy native executable

Ví dụ Maven:

~~~bash
./target/orders-service
~~~

Ví dụ Gradle:

~~~bash
./build/native/nativeCompile/orders-service
~~~

Tên executable và output path phụ thuộc cấu hình plugin. Dùng đúng path trong log build.

Kiểm tra health endpoint, startup, shutdown, environment variables, logging và resource files. Nếu chạy trong container, dùng đúng runtime image/OS/architecture dự kiến triển khai.

### 11.2. Chạy lại cùng fixture trên JVM và native

Dùng cùng một tập request/input cho hai chế độ:

| Scenario | JVM baseline | Native executable |
| --- | --- | --- |
| Tạo order với DTO thông thường | Kết quả và response mong đợi | So sánh cùng kết quả |
| Deserialize generic list/map | Đúng element type | Không trả về raw map hoặc lỗi reflection |
| Chọn plugin bằng tên cấu hình | Đúng implementation | Class được reach và constructor hoạt động |
| Đọc template/resource | Nội dung đúng | Resource có trong executable |
| Dynamic proxy | Gọi đúng interface | Proxy được tạo và hoạt động |
| Serialization/deserialization | Dữ liệu round-trip đúng | Kết quả tương đương |
| Error path/retry | Mã lỗi và side effect đúng | Hành vi tương đương |
| Profile/configuration khác | Đúng feature theo profile | Metadata đủ cho profile đã hỗ trợ |

Không chỉ so sánh HTTP status. Kiểm tra response body, kiểu dữ liệu, side effects, log quan trọng, database state và tài nguyên đã giải phóng.

### 11.3. Native test và smoke test có vai trò khác nhau

- **Native unit tests:** xác nhận logic và reflection path nhỏ chạy trong native test image.
- **Native integration tests:** xác nhận nhiều component/dependency phối hợp.
- **Smoke tests:** xác nhận executable khởi động, health endpoint và các luồng chính.
- **Container tests:** xác nhận OS libraries, certificates, environment, filesystem và network ở runtime image.

Một unit test pass không chứng minh database driver hoặc HTTP transport chạy đúng trong container. Một smoke test pass cũng không chứng minh các error path và feature optional đã được kiểm tra.

### 11.4. Test cả những đường agent chưa quan sát

Sau khi native build pass, chủ động chạy các scenario chưa được tracing agent kích hoạt:
- Một subtype/plugin ít dùng.
- Một locale/resource bundle khác.
- Một nhánh retry hoặc fallback.
- Một validation/error path.
- Một profile/configuration khác.
- Một module optional được bật trong deployment.

Nếu test mới phát hiện thiếu metadata, quay lại JVM với agent, chạy scenario tái hiện, merge output, review diff, build lại và chạy lại regression suite.

## 12. Chẩn đoán missing metadata và regression

### 12.1. Native báo thiếu class/member/resource

Xác định loại lỗi trước khi thêm metadata:

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| ClassNotFoundException | Class name, dependency có trên classpath, reflection reachability. |
| NoSuchMethodException hoặc lỗi constructor | Constructor signature và invocation metadata. |
| Reflection access/missing registration | Member category, condition và đúng GraalVM schema. |
| Resource không tìm thấy | Resource path, glob/pattern, resource có trong JAR/output không. |
| Proxy creation lỗi | Đúng tổ hợp interface và proxy metadata. |
| Serialization lỗi | Kiểu thực tế, serializer, subtype và serialization metadata. |
| JNI load/link lỗi | JNI metadata, native library, OS/architecture và shared dependencies. |

Đừng thêm allDeclaredMethods hoặc toàn bộ reflection cho một package trước khi biết member nào bị thiếu. Hãy tái hiện bằng test nhỏ và bổ sung cấu hình tối thiểu.

### 12.2. Dùng missing-registration diagnostics khi version hỗ trợ

Một số GraalVM release hỗ trợ chế độ báo cáo missing reachability metadata chi tiết hơn, ví dụ --exact-reachability-metadata ở các version tương ứng hoặc runtime reporting mode. Tên flag và thời điểm hỗ trợ phụ thuộc GraalVM release. Kiểm tra tài liệu của toolchain đang dùng trước khi thêm vào build arguments.

Các diagnostics này có thể giúp chỉ ra class/member chưa được đăng ký, nhưng vẫn cần chạy đúng feature để trigger lỗi. Không thay thế test coverage bằng một lần build có bật diagnostic.

### 12.3. Nếu native build pass nhưng runtime fail

Điều tra theo thứ tự:

1. Xác nhận executable là binary mới được build.
2. Xác nhận metadata đã nằm trong classpath native build.
3. Kiểm tra scenario đã chạy với agent chưa.
4. Kiểm tra Spring AOT registrar có được import không.
5. Kiểm tra dependency version và metadata condition.
6. Kiểm tra profile/environment/OS khác với JVM test.
7. Kiểm tra JNI/shared library, certificates và resource hệ thống.
8. Tạo regression test native cho thao tác gây lỗi.

### 12.4. Nếu metadata tăng bất thường

Nguyên nhân thường là test framework hoặc scenario rộng đã kích hoạt nhiều class. So sánh diff, phân loại entries theo package/caller/feature và dùng filter có kiểm soát. Không xóa entries chỉ vì chúng thuộc dependency; một số truy cập có thể là đường chạy production thật.

## 13. Quy trình lặp lại khi phát hiện metadata còn thiếu

Có thể lặp quy trình sau cho đến khi các test mục tiêu ổn định:

~~~mermaid
flowchart TD
    A[Native test phát hiện missing metadata] --> B[Tạo JVM scenario tái hiện]
    B --> C[Chạy tracing agent vào output hiện có]
    C --> D[Review diff và nguồn gốc entry]
    D --> E{Entry cần cho production?}
    E -->|Không| F[Loại entry hoặc điều chỉnh scenario/filter]
    E -->|Có| G[Giữ entry và cập nhật metadata]
    F --> H[Build native sạch]
    G --> H
    H --> I[Chạy regression suite trên native]
    I --> J{Tất cả scenario mục tiêu pass?}
    J -->|Chưa| B
    J -->|Rồi| K[Ghi compatibility evidence]
~~~

Mỗi vòng lặp phải có một scenario tái hiện rõ, một diff metadata có thể review và một regression test xác nhận lỗi đã được sửa. Không chạy agent nhiều lần mà không lưu scenario/đầu ra tương ứng; khi đó khó biết entry nào đến từ luồng nào.

## 14. Tiêu chí chấp nhận trước khi phát hành

Chỉ xem bước kết hợp và kiểm thử là hoàn tất khi có đủ bằng chứng:

- Metadata agent được thu thập từ các scenario có danh sách và có thể tái lập.
- Kết quả agent được review; entries test-only và entries thừa đã được xử lý có lý do.
- Spring Runtime Hints vẫn được duy trì trong source và được Spring AOT xử lý.
- Metadata thư viện đúng artifact/version và không bị ghi đè.
- Metadata đã duyệt nằm trên native classpath.
- Native build dùng đúng JDK/GraalVM/Native Build Tools.
- Native executable được build mới sau thay đổi metadata.
- Native unit/integration/smoke tests chạy thành công theo phạm vi đã xác định.
- JVM và native cho kết quả tương đương với cùng fixtures.
- Container/platform tests bao phủ môi trường đích.
- Known limitations và scenario chưa được kiểm thử được ghi rõ.

## 15. Bài thực hành: hợp nhất hints và agent metadata cho dịch vụ đơn hàng

**Bối cảnh:** dịch vụ Spring Boot có OrderPlugin được chọn từ cấu hình, Order DTO dùng Jackson, template email đọc từ classpath và một client tạo JDK dynamic proxy. Ứng dụng đã có OrderRuntimeHints, nhưng native test phát hiện thiếu một plugin và resource template trong một profile phụ.

### Nhiệm vụ

1. Ghi lại GraalVM/JDK/Spring Boot/Native Build Tools version và dependency graph.
2. Đọc OrderRuntimeHints và xác nhận registrar được import vào application context.
3. Tạo danh sách scenario cho plugin mặc định, plugin phụ, JSON binding, template và proxy.
4. Chạy ứng dụng/test trên JVM với config-output-dir cho scenario đầu.
5. Chạy các scenario còn lại bằng config-merge-dir hoặc metadataCopy của Maven/Gradle.
6. Review metadata: loại entries trùng với hints, entries test-only, resource pattern rộng và plugin không thuộc allowlist.
7. Hợp nhất metadata đã duyệt vào application resources bằng cơ chế merge được plugin hỗ trợ.
8. Kiểm tra resource output và JAR; xác nhận native classpath sử dụng metadata.
9. Build native sạch bằng Maven hoặc Gradle.
10. Chạy native unit/integration tests và smoke test cho từng profile.
11. Chạy thêm một scenario chưa dùng khi tracing để kiểm tra coverage.
12. Ghi lại diff metadata, test report, build log, executable path và kết luận.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Toolchain | JDK, GraalVM, Spring Boot, Native Build Tools và platform. |
| Scenario inventory | Scenario, input, profile, kết quả mong đợi. |
| Agent output | Thư mục, thời điểm chạy, command và file metadata. |
| Merge/review | Diff trước/sau, entries thêm/xóa, lý do và reviewer. |
| Spring hints | Registrar/annotation, nơi import và predicate tests. |
| Dependency metadata | Artifact/version và metadata đã dùng. |
| Native build | Lệnh, log, executable path và build timestamp/hash. |
| Native tests | Test report, fixtures, profile và kết quả. |
| Container tests | Image/architecture, runtime config và smoke result. |
| Known limitations | Feature chưa chạy, metadata chưa xác nhận và next action. |

### Tiêu chí hoàn thành

- [ ] Thu thập được metadata từ ít nhất hai scenario JVM khác nhau.
- [ ] Biết dùng config-output-dir và config-merge-dir đúng mục đích.
- [ ] Phân biệt merge giữa các lần agent, metadataCopy và Spring AOT hints.
- [ ] Review và loại được entries không cần với bằng chứng.
- [ ] Metadata đã duyệt được đưa vào native classpath.
- [ ] Maven/Gradle build lại executable từ output sạch.
- [ ] Native tests xác nhận plugin, JSON, resource và proxy hoạt động.
- [ ] Chạy thêm scenario chưa có trong agent coverage.
- [ ] Ghi được build/toolchain/test evidence để tái lập.

## 16. Câu hỏi tự đánh giá

1. Vì sao tracing agent phải chạy trên JVM thay vì native executable?
2. Khi nào dùng config-output-dir, khi nào dùng config-merge-dir?
3. Agent có thể bỏ sót metadata nào nếu scenario không đi qua error path hoặc plugin phụ?
4. Vì sao không nên ghi output agent trực tiếp đè lên metadata đã review?
5. metadataCopy của Native Build Tools khác config-merge-dir ở đâu?
6. Spring Runtime Hints được xử lý ở giai đoạn nào và vì sao vẫn cần giữ registrar trong source?
7. Làm thế nào phân biệt entries production với entries chỉ do JUnit/test framework tạo?
8. Vì sao native build thành công chưa chứng minh native runtime đúng?
9. Khi nào cần chạy lại tracing agent sau một lần nâng dependency hoặc thay đổi profile?
10. Những bằng chứng nào cần có trước khi kết luận metadata đã được hợp nhất đúng?

## 17. Tài liệu chính thức

Cú pháp agent, metadata schema và plugin DSL thay đổi theo GraalVM/Native Build Tools release. Luôn dùng tài liệu khớp toolchain thực tế:

- [GraalVM Native Image — Configure with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/guides/configure-with-tracing-agent/): cách chạy agent, config-output-dir, config-merge-dir, build lại và kiểm thử.
- [GraalVM Native Image — Collect Metadata with the Tracing Agent](https://www.graalvm.org/reference-manual/native-image/Agent/): periodic writes, caller/access filters và cách cung cấp metadata cho Native Image.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): agent integration, metadataCopy, nativeTest và nativeCompile.
- [GraalVM Native Build Tools — Maven End-to-End Guide](https://graalvm.github.io/native-build-tools/latest/end-to-end-maven-guide.html): agent activation, metadata copy, native test và troubleshooting missing configuration.
- [Spring Framework — Ahead-of-Time Processing](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints và quá trình Spring AOT.
- [Spring Boot — GraalVM Native Image](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): build và vận hành ứng dụng Spring Boot native.

**Điểm cần nhớ:** metadata agent chỉ phản ánh các đường chạy đã quan sát; Spring Runtime Hints và metadata thư viện vẫn có vai trò riêng. Hãy review nguồn, merge đúng cơ chế, đưa metadata đã duyệt vào classpath, build lại executable sạch và chạy regression tests trên native trước khi phát hành.

