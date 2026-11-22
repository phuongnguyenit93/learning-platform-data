# Kiểm kê dependency và phát hiện xung đột phiên bản

Jackson thường xuất hiện trong ứng dụng Java dưới dạng nhiều artifact: core parser/generator, databind, annotations, module cho Java Time hoặc Kotlin, và module định dạng như YAML hay XML. Các dependency này có thể được khai báo trực tiếp trong project hoặc được kéo vào gián tiếp bởi Spring Boot, framework, thư viện message broker, SDK và các thư viện bên thứ ba. Vì vậy, chỉ nhìn vào một dòng jackson-databind trong file build là chưa đủ để biết runtime đang dùng phiên bản nào.

Kiểm kê dependency là quá trình xác định **những artifact Jackson thực sự có mặt trên từng classpath, phiên bản nào được chọn, dependency nào đưa chúng vào và bộ phiên bản đó có tương thích với nhau hay không**. Phát hiện xung đột cần nhìn cả compile, runtime và test classpath; cả dependency trực tiếp lẫn transitive; cả graph do build tool giải quyết lẫn JAR thực sự được đóng gói và nạp lúc chạy.

Cách quản lý ổn định là dùng một bộ quản lý phiên bản thống nhất, thường là Jackson BOM hoặc dependency management của Spring Boot, tránh pin riêng lẻ từng artifact, kiểm tra dependency graph bằng công cụ của Maven/Gradle và xác nhận runtime thực tế. Sau đó mới nâng cấp theo một thay đổi có kiểm soát, chạy test tích hợp và quét bảo mật trên artifact đã resolve.

## 1. Vì sao Jackson có nhiều dependency?

Jackson được chia thành nhiều phần để ứng dụng chỉ cần dùng đúng khả năng cần thiết:

| Artifact hoặc nhóm | Vai trò |
|---|---|
| jackson-core | Streaming API: JsonFactory, JsonParser, JsonGenerator và token |
| jackson-annotations | Annotation như JsonProperty, JsonCreator, JsonTypeInfo, JsonInclude |
| jackson-databind | Data Binding và Tree Model: ObjectMapper, JsonNode, serializer/deserializer |
| jackson-datatype-jsr310 | Hỗ trợ kiểu java.time như Instant, LocalDate, OffsetDateTime |
| jackson-datatype-jdk8 | Hỗ trợ kiểu JDK 8 như Optional |
| jackson-module-parameter-names | Sử dụng tên tham số constructor khi phù hợp |
| jackson-module-kotlin | Hỗ trợ Kotlin data class và semantics liên quan |
| jackson-dataformat-yaml | Đọc/ghi YAML qua YAML factory/parser |
| jackson-dataformat-xml | Đọc/ghi XML |
| Các module khác | Hỗ trợ định dạng hoặc kiểu dữ liệu chuyên biệt |

Một ứng dụng Spring Boot có thể chỉ khai báo starter web, nhưng dependency graph vẫn chứa Jackson vì starter hoặc framework kéo vào. Một ứng dụng khác có thể khai báo jackson-databind trực tiếp và thêm YAML module. Cả hai đều cần kiểm kê graph cuối cùng.

Không phải mọi artifact có chữ Jackson đều có cùng chu kỳ phát hành hoặc được quản lý bởi cùng BOM. Jackson BOM quản lý các artifact thuộc hệ sinh thái được liệt kê trong BOM của release đó; module của bên thứ ba có thể có versioning riêng. Khi kiểm kê, ghi rõ artifact, groupId, version, scope/configuration và nguồn dependency thay vì chỉ gom theo tên thư viện.

## 2. Phân biệt dependency trực tiếp và transitive

Dependency trực tiếp được project khai báo trong file build. Dependency transitive được kéo vào bởi một dependency khác.

Ví dụ Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

jackson-dataformat-yaml có thể kéo theo các dependency Jackson cần thiết và parser YAML. Spring Boot starter hoặc thư viện khác cũng có thể đưa jackson-databind vào graph mà project không khai báo trực tiếp.

Một graph minh họa:

~~~text
application
├── spring-boot-starter-web
│   └── spring-boot-starter-json
│       └── jackson-databind
│           ├── jackson-core
│           └── jackson-annotations
├── jackson-dataformat-yaml
│   ├── jackson-core
│   └── YAML parser dependency
└── partner-sdk
    └── jackson-databind (transitive request version khác)
~~~

Sơ đồ này chỉ minh họa quan hệ có thể gặp; graph thật phải được lấy từ project. Hai nhánh có thể yêu cầu các version khác nhau, nhưng build tool sẽ áp dụng quy tắc mediation/resolution để chọn version cho từng module. Việc build thành công không chứng minh mọi artifact đã được chọn đúng release train.

### 2.1. Vì sao khai báo trực tiếp không cho biết toàn bộ runtime?

Một dòng khai báo jackson-databind không cho biết:

- jackson-core và jackson-annotations nào được resolve.
- Module Java Time hoặc YAML đến từ dependency nào.
- Một SDK có yêu cầu phiên bản khác hay không.
- Test runtime có thêm module hoặc version khác không.
- Plugin đóng gói có shade hoặc copy JAR khác vào output không.
- Container/server có cung cấp thư viện bên ngoài ứng dụng hay không.

Vì vậy, luôn kiểm tra dependency tree đã resolve và classpath runtime.

## 3. Jackson BOM giải quyết vấn đề gì?

Jackson BOM (Bill of Materials) là POM quản lý phiên bản cho các artifact Jackson. Khi import BOM, project có thể khai báo dependency mà không lặp version cho từng artifact. BOM cung cấp một bộ version đã được phát hành cùng nhau theo release train tương ứng.

Maven example:

~~~xml
<properties>
    <jackson.version>JACKSON_BOM_VERSION</jackson.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>JACKSON_BOM_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.dataformat</groupId>
        <artifactId>jackson-dataformat-yaml</artifactId>
    </dependency>
</dependencies>
~~~

JACKSON_BOM_VERSION là placeholder; thay bằng version đã được chọn và xác nhận tương thích với framework của project. Không copy nguyên placeholder vào POM. Trong dự án thật, có thể dùng property trong dependencyManagement để tránh lặp version ở nhiều nơi.

Với BOM được import, dependency Jackson được quản lý có thể bỏ version tại từng khai báo. Khi nâng cấp release train, thay đổi một điểm quản lý version thay vì chỉnh tay nhiều artifact.

### 3.1. BOM không tự thêm dependency

BOM quản lý version, không có nghĩa mọi module được liệt kê trong BOM đều tự xuất hiện trên classpath. Project vẫn khai báo các artifact cần sử dụng hoặc nhận chúng qua dependency khác.

Ví dụ import BOM không tự thêm YAML module. Muốn đọc YAML, project vẫn cần dependency jackson-dataformat-yaml (trực tiếp hoặc qua một dependency phù hợp).

### 3.2. Không trộn version riêng lẻ ngoài BOM nếu không có lý do

Mẫu dễ tạo xung đột:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>VERSION_A</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-core</artifactId>
    <version>VERSION_B</version>
</dependency>
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-annotations</artifactId>
    <version>VERSION_C</version>
</dependency>
~~~

Các artifact cốt lõi cần một bộ version tương thích. Một số tổ hợp có thể vẫn chạy trong vài luồng nhưng lỗi ở một code path khác, ví dụ NoSuchMethodError, NoSuchFieldError hoặc lỗi linkage khi serializer/deserializer gọi API không tồn tại ở artifact còn lại.

Ưu tiên BOM. Chỉ override riêng một artifact khi có lý do kỹ thuật được ghi nhận, hiểu rõ compatibility matrix và có test runtime bao phủ.

## 4. Khi dùng Spring Boot, ai quản lý version Jackson?

Spring Boot có dependency management riêng và thường quản lý phiên bản Jackson tương thích với release line của Boot. Nếu project đã dùng Spring Boot parent POM hoặc dependency management/BOM của Boot, các version Jackson thường đã được quản lý.

Trong tình huống đó, không nên thêm một version ngẫu nhiên cho riêng jackson-databind chỉ vì muốn nâng một CVE. Thay đổi một artifact có thể khiến jackson-databind, jackson-core, jackson-annotations và module khác lệch nhau hoặc rời khỏi bộ version Boot đã kiểm thử.

Các hướng xử lý thường gặp:

1. Nâng Spring Boot patch/minor lên bản hỗ trợ bộ Jackson đã vá, nếu có.
2. Dùng cơ chế override dependency version được Spring Boot release đó hỗ trợ, áp dụng nhất quán và kiểm thử.
3. Nếu cần quản lý Jackson BOM trực tiếp, xác định rõ quan hệ ưu tiên giữa Boot BOM và Jackson BOM, sau đó kiểm tra effective POM hoặc dependency graph cuối cùng.

Không giả định thứ tự import BOM giống nhau ở mọi cấu hình Maven/Gradle. Hãy kiểm tra version thực tế được chọn thay vì chỉ đọc file khai báo.

### 4.1. Tránh tự tạo ObjectMapper mới để giải quyết dependency issue

Nếu một lỗi xuất phát từ version dependency, tạo thêm new ObjectMapper() không sửa được classpath. Tất cả mapper trong cùng classloader vẫn dùng các class Jackson đã được nạp. Hãy sửa dependency graph và runtime packaging trước.

## 5. Kiểm kê bằng Maven

Maven có goal dependency:tree để hiển thị dependency graph. Có thể lọc theo group/artifact để tập trung vào Jackson.

~~~bash
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:*
~~~

Có thể kiểm tra thêm các nhóm module:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:*,com.fasterxml.jackson.datatype:*,com.fasterxml.jackson.dataformat:*
~~~

Dấu -Dverbose giúp hiển thị các node bị conflict/omitted trong một số trường hợp, qua đó nhìn được đường dependency yêu cầu version khác với version được chọn.

Để tìm riêng một artifact:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Để xem POM sau khi parent, profile và dependency management được áp dụng:

~~~bash
mvn help:effective-pom
~~~

Effective POM giúp xác định version/property/BOM nào đang thực sự tham gia quản lý. Khi project multi-module, chạy lệnh ở đúng module hoặc root phù hợp và xem cả graph của module tạo artifact deploy.

### 5.1. Đọc output dependency tree

Ví dụ output minh họa:

~~~text
com.example:orders-service
+- org.springframework.boot:spring-boot-starter-json
|  \- com.fasterxml.jackson.core:jackson-databind:jar:2.x.y:compile
|     +- com.fasterxml.jackson.core:jackson-annotations:jar:2.x.y:compile
|     \- com.fasterxml.jackson.core:jackson-core:jar:2.x.y:compile
\- com.vendor:partner-sdk
   \- (com.fasterxml.jackson.core:jackson-databind:jar:2.a.b:compile - omitted for conflict)
~~~

Trong ví dụ, partner SDK yêu cầu một version khác, nhưng Maven chọn version theo mediation và dependency management. Cần kiểm tra version được chọn có tương thích với SDK và các Jackson module khác hay không. Đừng chỉ nhìn dòng omitted for conflict rồi kết luận lỗi đã được xử lý an toàn.

### 5.2. Kiểm tra scope

Maven có các scope như compile, provided, runtime và test. Cần kiểm tra đúng scope vì:

- Dependency chỉ có ở test có thể làm test pass nhưng production thiếu module.
- Dependency provided có thể do container cung cấp, và runtime server có thể dùng version khác.
- Dependency runtime có thể không hiện trong compile classpath nhưng vẫn cần lúc chạy.
- Một module có thể có profile build khác nhau giữa CI và máy local.

Hãy kiểm tra cả module deploy, profile thực tế và dependency graph của test/runtime.

## 6. Kiểm kê bằng Gradle

Gradle cung cấp task dependencies để xem graph theo configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể lọc output bằng cách tìm tên Jackson trong kết quả hoặc dùng dependencyInsight để xem vì sao một version được chọn.

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Kiểm tra artifact khác:

~~~bash
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-annotations --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-dataformat-yaml --configuration runtimeClasspath
~~~

Gradle configuration có thể gồm compileClasspath, runtimeClasspath, testCompileClasspath và testRuntimeClasspath. Cần chọn đúng configuration cho câu hỏi đang kiểm tra. Một version có mặt trong test runtime chưa chắc có mặt trong production runtime.

### 6.1. Đọc dependencyInsight

dependencyInsight giải thích dependency được yêu cầu bởi những đường nào và lý do Gradle chọn version cuối cùng, chẳng hạn conflict resolution, constraint hoặc platform. Đây là công cụ quan trọng để truy ngược một version không mong đợi về thư viện kéo nó vào.

Không nên chỉ kiểm tra dependencies ở root project nếu ứng dụng multi-project. Mỗi module có thể có configuration và dependency graph khác nhau. Kiểm tra module tạo executable/fat JAR hoặc module thực sự được deploy.

## 7. Quản lý Jackson BOM trong Gradle

Nếu không có dependency management từ Spring Boot hoặc một platform khác, Gradle có thể import Jackson BOM bằng platform:

~~~kotlin
val jacksonVersion = "JACKSON_BOM_VERSION"

dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:$jacksonVersion"))

    implementation("com.fasterxml.jackson.core:jackson-databind")
    implementation("com.fasterxml.jackson.datatype:jackson-datatype-jsr310")
    implementation("com.fasterxml.jackson.dataformat:jackson-dataformat-yaml")
}
~~~

JACKSON_BOM_VERSION là placeholder, cần thay bằng version thực tế đã được phê duyệt. Không pin từng artifact nếu BOM đã quản lý chúng.

Nếu dùng Spring Boot Gradle plugin hoặc dependency management plugin, Boot có thể đã cung cấp platform/dependency constraints. Tránh thêm một platform thứ hai mà không kiểm tra thứ tự và mức ưu tiên. Dùng dependencyInsight để xác nhận kết quả.

### 7.1. platform và enforcedPlatform

platform(...) đưa dependency constraints từ BOM vào resolution. enforcedPlatform(...) áp dụng ràng buộc mạnh hơn và có thể buộc consumer sử dụng version được chỉ định, kể cả khi dependency khác yêu cầu version khác.

Không dùng enforcedPlatform như một cách sửa nhanh mà không hiểu ảnh hưởng tới các module phụ thuộc hoặc project tiêu thụ thư viện. Với ứng dụng có thể triển khai độc lập, platform thông thường thường đủ; nếu cần enforcement, hãy ghi rõ lý do và kiểm tra toàn bộ graph.

### 7.2. Version catalog không thay thế resolution inspection

Gradle version catalog (libs.versions.toml) giúp tập trung alias và version khai báo. Nhưng một dependency transitive vẫn có thể yêu cầu version khác; platform/constraint và conflict resolution vẫn quyết định version cuối. Version catalog không thay cho dependencyInsight.

## 8. Cách Maven và Gradle giải quyết xung đột khác nhau

Không nên giả định hai build tool sẽ chọn cùng version chỉ vì POM/Gradle file có vẻ giống nhau.

| Đặc điểm | Maven | Gradle |
|---|---|---|
| Xem graph | dependency:tree | dependencies |
| Truy nguồn version | Tree với các đường dependency và node omitted | dependencyInsight |
| Quản lý bộ version | dependencyManagement và imported BOM | platform, constraints hoặc dependency management |
| Quy tắc mediation mặc định | Thường chọn dependency gần nhất theo đường graph, trừ khi bị dependency management điều khiển | Thường chọn version cao nhất trong các version được yêu cầu, có xét constraints/platform/rules |
| Kiểm soát hội tụ | Maven Enforcer dependencyConvergence | Constraints, platforms, resolution rules và dependency locking |
| Classpath cần kiểm tra | Scope/profile/module | Configuration/module |

Vì quy tắc resolution khác nhau, việc cùng source code nhưng build bằng hai tool có thể tạo runtime graph khác. Nếu repository hỗ trợ cả Maven và Gradle, kiểm tra cả hai đường build theo cách project thực sự phát hành.

## 9. Dấu hiệu của xung đột phiên bản Jackson

Một số lỗi runtime có thể gợi ý classpath không nhất quán:

| Lỗi | Ý nghĩa có thể gặp |
|---|---|
| NoSuchMethodError | Code gọi method không có trong class đã nạp; thường liên quan API mismatch |
| NoSuchFieldError | Field được compile-time mong đợi không có ở runtime |
| AbstractMethodError | Implementation runtime không khớp API/abstract method kỳ vọng |
| NoClassDefFoundError | Class cần thiết không có hoặc không thể khởi tạo/nạp ở runtime |
| ClassNotFoundException | Classloader không tìm được class được yêu cầu |
| LinkageError | Xung đột hoặc không tương thích ở cấp liên kết class |
| InvalidDefinitionException | Có thể do model/configuration sai; không mặc định là version conflict |
| JsonMappingException | Lỗi mapping dữ liệu; thường cần kiểm tra input/model trước khi quy cho dependency |

Các lỗi linkage thường xuất hiện khi code được compile với một API nhưng runtime nạp artifact khác. Tuy nhiên, không phải mọi exception Jackson đều là xung đột version. InvalidDefinitionException hoặc MismatchedInputException thường có thể do DTO, annotation, input hoặc cấu hình. Hãy dùng stack trace và dependency graph để xác định nguyên nhân.

### 9.1. Vì sao build có thể thành công nhưng ứng dụng lỗi lúc chạy?

Compile classpath và runtime classpath không nhất thiết giống nhau. Một dependency có thể ở scope provided, bị loại khỏi packaging hoặc bị container thay thế. Fat JAR có thể chứa version khác với version mà IDE dùng. Một app server có thể có classloader riêng hoặc thư viện Jackson dùng chung.

Vì vậy, build thành công chỉ xác nhận bước build với classpath build đã giải quyết; nó chưa chứng minh artifact triển khai sẽ nạp đúng class.

## 10. Kiểm tra class thực sự được nạp lúc runtime

Khi nghi ngờ version mismatch, có thể in nguồn JAR của class:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

public final class JacksonRuntimeInfo {
    private JacksonRuntimeInfo() {
    }

    public static void print() {
        var codeSource = ObjectMapper.class
                .getProtectionDomain()
                .getCodeSource();

        System.out.println("ObjectMapper loaded from: "
                + (codeSource == null ? "unknown" : codeSource.getLocation()));

        Package jacksonPackage = ObjectMapper.class.getPackage();
        System.out.println("Implementation version: "
                + jacksonPackage.getImplementationVersion());
    }
}
~~~

getImplementationVersion() có thể trả null nếu manifest không cung cấp metadata. CodeSource cũng có thể không khả dụng trong một số classloader/module environment. Đây là tín hiệu hỗ trợ điều tra, không thay thế dependency report.

Có thể dùng class-loading log của JVM khi cần:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Với Java runtime cũ hơn, tùy chọn -verbose:class có thể hữu ích. Log có thể rất dài, nên lọc các dòng chứa com.fasterxml.jackson khi phân tích.

Nếu ObjectMapper đến từ một JAR khác với graph dự kiến, kiểm tra packaging, container shared library, shading/relocation, plugin runtime và thứ tự classloader.

## 11. Kiểm tra artifact được đóng gói

Dependency graph của build tool chưa phải toàn bộ câu chuyện nếu quá trình đóng gói có bước copy/shade/overlay.

Các vị trí cần kiểm tra:

- BOOT-INF/lib trong Spring Boot executable JAR.
- WEB-INF/lib trong WAR.
- Thư mục lib của application server.
- JAR do Docker image hoặc startup script bổ sung.
- Thư viện được shade/relocate vào một JAR khác.
- Thư viện được cung cấp bởi container hoặc platform runtime.

Với executable JAR, có thể liệt kê nội dung archive để xem artifact Jackson nào thực sự được đóng gói. Với WAR hoặc container image, kiểm tra output cuối cùng và base image. Không kết luận runtime chỉ từ IDE classpath.

Nếu có nhiều bản JAR cùng chứa com/fasterxml/jackson/databind/ObjectMapper.class, cần xác định classloader nào nạp bản nào. Một JAR shaded có thể không mang tên jackson-databind, vì vậy tìm theo filename là chưa đủ; khi cần, kiểm tra nội dung JAR.

## 12. Phân biệt xung đột version với duplicate class

Hai tình huống có liên quan nhưng không giống nhau:

- **Version conflict trong dependency graph:** nhiều dependency yêu cầu các version khác nhau của cùng module; build tool chọn một version.
- **Duplicate class ở runtime:** hai JAR khác nhau cùng chứa một class có cùng fully qualified name, có thể do packaging, shading sai hoặc classloader riêng.

Dependency resolution có thể hội tụ một module Maven coordinate về một version, nhưng không đảm bảo không có class trùng từ artifact khác hoặc JAR được chép thủ công.

Khi có lỗi khó tái hiện, hãy kiểm tra cả graph lẫn nội dung package. Nếu app chạy trong container, xem cả thư viện của ứng dụng và thư viện được server cung cấp.

## 13. Kiểm tra compatibility giữa các nhóm Jackson

Khi kiểm kê, không chỉ so version của jackson-databind. Hãy xem cả các thành phần liên quan:

- jackson-core và jackson-annotations cần tương thích với jackson-databind.
- jackson-dataformat-* thường có quan hệ chặt với core/databind tương ứng của release train.
- jackson-datatype-* và jackson-module-* cần version phù hợp với dòng Jackson mà chúng hỗ trợ.
- Module của bên thứ ba có thể hỗ trợ một dải Jackson version cụ thể.
- YAML module còn phụ thuộc parser YAML và API/behavior của parser đó.
- Spring Boot/Spring Framework có thể có compatibility assumptions với Jackson major version.

Jackson BOM giúp align các artifact được BOM quản lý. Nhưng BOM không tự đảm bảo module bên thứ ba, framework, plugin hoặc parser transitive đều tương thích. Đọc metadata/POM của module và tài liệu hỗ trợ version nếu có.

### 13.1. Không chỉ so sánh chuỗi version

Các version có thể có suffix, qualifier, patch hoặc major khác nhau. Đừng tự suy ra compatibility chỉ từ việc hai chuỗi version gần nhau. Xem release train, BOM, dependency metadata và migration guide của đúng module.

### 13.2. Không trộn Jackson 2.x và 3.x trong cùng một đường binding

Một nâng cấp major có thể thay đổi package, artifact coordinates, API, yêu cầu Java và tích hợp framework. Không chỉ thay version số trong một dependency rồi để phần còn lại ở major khác. Chọn một migration path thống nhất, đọc migration guide chính thức và nâng cấp module/framework tương ứng theo compatibility matrix.

Nếu project có thư viện chưa hỗ trợ major mới, cần đánh giá nâng cấp thư viện đó, giữ một boundary adapter hoặc trì hoãn migration. Không ép dependency bằng một constraint chỉ để build xanh nếu runtime/API contract không tương thích.

## 14. Tìm nguồn dependency kéo version không mong muốn

Khi dependencyInsight hoặc dependency:tree cho thấy version không mong muốn, truy ngược theo từng đường:

1. Xác định artifact và version thực tế.
2. Xem dependency nào yêu cầu version đó.
3. Kiểm tra dependency trực tiếp của project và dependency transitive.
4. Xem parent POM, imported BOM, Gradle platform và constraints.
5. Xem plugin hoặc convention plugin có thêm dependency không.
6. Kiểm tra profile, variant và configuration đang được resolve.
7. Xem exclusion hoặc resolution rule có làm thay đổi graph không.

Ví dụ, một SDK có thể kéo jackson-databind cũ. Nếu project đã có BOM, graph có thể chọn version theo BOM. Điều đó chưa đủ để chứng minh SDK tương thích; kiểm tra tài liệu SDK hoặc test integration với version được chọn.

Không nên sửa bằng cách thêm dependency trực tiếp một cách mù quáng. Làm vậy có thể thay version được chọn nhưng che mất nguồn xung đột và tạo gánh nặng nâng cấp sau này.

## 15. Dùng Maven Enforcer để phát hiện graph không hội tụ

Maven Enforcer Plugin có rule dependencyConvergence để phát hiện nhiều version của cùng dependency trong graph. Ví dụ cấu hình:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>ENFORCER_PLUGIN_VERSION</version>
            <executions>
                <execution>
                    <id>enforce-dependency-convergence</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <dependencyConvergence/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Version plugin nên được quản lý trong parent/build plugin management của dự án; placeholder ở ví dụ cần được thay bằng version đã chọn.

Rule này có thể phát hiện xung đột rộng trong toàn project, không chỉ Jackson. Trước khi bật ở chế độ fail build, hãy xem các khác biệt có chủ đích và giải quyết chúng bằng BOM/constraint/exclusion phù hợp. Không thêm suppression rộng để bỏ qua mọi dependency mismatch.

Một rule khác như requireUpperBoundDeps có thể giúp phát hiện tình huống version thấp hơn một version được yêu cầu trong graph, nhưng không thay thế việc kiểm tra compatibility. Version cao nhất không đồng nghĩa version tương thích nhất.

## 16. Dùng Gradle constraints và dependency locking

Gradle hỗ trợ platform/BOM, dependency constraints và resolution strategy. Với project cần bảo đảm một release train Jackson, ưu tiên khai báo platform thống nhất thay vì ép từng module bằng rule rời rạc.

~~~kotlin
dependencies {
    implementation(platform("com.fasterxml.jackson:jackson-bom:$jacksonVersion"))
}
~~~

Nếu cần constraint riêng, ghi rõ lý do và phạm vi:

~~~kotlin
dependencies {
    constraints {
        implementation("com.fasterxml.jackson.core:jackson-databind") {
            version {
                strictly(jacksonVersion)
            }
            because("Keep databind aligned with the approved Jackson BOM")
        }
    }
}
~~~

Ví dụ constraint chỉ minh họa kỹ thuật; nếu BOM đã quản lý artifact, không cần lặp constraint cho từng module. Strict constraint có thể làm resolution thất bại khi dependency khác đòi version không tương thích, điều này thường tốt hơn âm thầm chọn version nhưng cần xử lý có chủ đích.

Dependency locking giúp cố định version đã resolve để các lần build tiếp theo có kết quả lặp lại. Locking không thay thế việc chọn version an toàn: nếu lockfile giữ version cũ, cần chủ động cập nhật lock khi nâng cấp đã được phê duyệt.

## 17. Exclusion: chỉ dùng khi hiểu dependency path

Maven và Gradle cho phép loại một transitive dependency khỏi một đường dependency. Điều này có thể hữu ích nếu thư viện kéo một module không cần thiết hoặc version conflict được giải quyết bằng BOM chung.

Ví dụ Maven exclusion:

~~~xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>partner-sdk</artifactId>
    <exclusions>
        <exclusion>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Sau exclusion, project phải cung cấp dependency tương thích nếu SDK thật sự cần nó. Exclusion có thể làm thiếu class lúc runtime nếu hiểu sai dependency path.

Không dùng exclusion toàn cục để che mọi Jackson dependency. Xác định artifact, đường kéo vào và version policy trước; sau khi sửa, chạy dependency tree lại để xác nhận graph.

## 18. Kiểm kê module theo nhu cầu sử dụng

Không nên thêm mọi Jackson module cho chắc. Mỗi module làm tăng dependency graph, bề mặt bảo trì và khả năng phát sinh xung đột.

Một bảng kiểm kê hữu ích:

| Module | Có cần không? | Ai sử dụng? | Nguồn dependency | Version được resolve |
|---|---|---|---|---|
| jackson-databind | Có/không | DTO binding, Tree Model | Trực tiếp/starter | Lấy từ graph |
| jackson-core | Có/không | Parser/generator | Thường transitive | Lấy từ graph |
| jackson-annotations | Có/không | Annotation | Thường transitive | Lấy từ graph |
| jackson-datatype-jsr310 | Có/không | java.time | Trực tiếp/module bean | Lấy từ graph |
| jackson-module-kotlin | Có/không | Kotlin model | Trực tiếp/starter | Lấy từ graph |
| jackson-dataformat-yaml | Có/không | YAML import/export | Trực tiếp | Lấy từ graph |
| jackson-dataformat-xml | Có/không | XML integration | Trực tiếp | Lấy từ graph |
| Module bên thứ ba | Có/không | Kiểu/domain cụ thể | SDK/framework | Theo metadata module |

Hãy xác định module có thật sự được dùng ở production, test hoặc tool build. Nếu module chỉ phục vụ test, có thể scope test phù hợp; nếu code production gọi class của module, nó phải có mặt ở runtime.

## 19. Kiểm tra security advisory và dependency vulnerability

Jackson, parser YAML và các dependency transitive có thể nhận bản vá bảo mật. Kiểm kê version không chỉ là tìm lỗi linkage; còn cần xác định version nào đã hết hỗ trợ hoặc có advisory áp dụng.

Quy trình nên bao gồm:

- Quét dependency đã resolve, không chỉ dependency khai báo trực tiếp.
- Kiểm tra advisory theo groupId, artifactId và version bị ảnh hưởng.
- Phân biệt dependency runtime với test-only nếu công cụ báo phạm vi.
- Đọc điều kiện khai thác: code path, cấu hình polymorphic typing, input trust boundary và classpath có thể ảnh hưởng mức độ rủi ro.
- Ưu tiên bản vá trong release line được hỗ trợ hoặc nâng framework/BOM nếu cần.
- Quét lại artifact cuối cùng sau khi thay version.

Không kết luận không bị ảnh hưởng chỉ vì ứng dụng không gọi trực tiếp một method; một transitive library có thể sử dụng Jackson thay mặt ứng dụng. Ngược lại, không kết luận một CVE chắc chắn khai thác được nếu chưa xét điều kiện ảnh hưởng. Dùng advisory chính thức và công cụ scan làm đầu vào cho đánh giá.

### 19.1. SBOM giúp biết những gì đã phát hành

Software Bill of Materials (SBOM) liệt kê component trong artifact. Có thể tạo SBOM theo CycloneDX hoặc SPDX qua plugin/tool phù hợp với build pipeline.

SBOM nên được tạo từ artifact phát hành hoặc dependency graph đã resolve, không chỉ từ file khai báo. Điều này giúp đội vận hành biết chính xác phiên bản Jackson và parser YAML đang được deploy, đồng thời hỗ trợ rà soát khi có advisory mới.

## 20. Kiểm tra runtime classpath và packaging trong CI

Một pipeline hữu ích có thể thực hiện các bước:

~~~text
Resolve dependencies
       |
       v
Inspect Jackson dependency graph
       |
       v
Enforce convergence / approved platform
       |
       v
Compile and run unit tests
       |
       v
Run Spring integration tests
       |
       v
Build executable artifact
       |
       v
Inspect packaged libraries / generate SBOM
       |
       v
Scan vulnerabilities
       |
       v
Publish artifact with dependency metadata
~~~

Không phải project nào cũng cần mọi bước trong cùng một job. Nhưng dependency graph, integration test và vulnerability scan nên chạy trên đúng profile/variant được phát hành.

Với multi-module build, kiểm tra module thực sự deploy và các module dùng chung. Với Docker, scan image hoặc SBOM của image vì base image và runtime libraries cũng có thể bổ sung component ngoài graph Maven/Gradle.

## 21. Nâng cấp Jackson theo từng bước

Một thay đổi version nên có kế hoạch rõ ràng:

1. **Ghi nhận trạng thái hiện tại:** export dependency tree/insight cho runtime và test.
2. **Xác định owner của version:** Spring Boot BOM, Jackson BOM, parent POM, Gradle platform hay version catalog.
3. **Xác định mục tiêu nâng cấp:** bản vá bảo mật, bug fix, tương thích Java/framework hay major migration.
4. **Đọc release notes/migration guide:** xem API thay đổi, behavior thay đổi và yêu cầu Java.
5. **Align bộ artifact:** core, annotations, databind và các module liên quan.
6. **Kiểm tra dependency transitive:** SDK, framework và module bên thứ ba có hỗ trợ version mục tiêu không.
7. **Cập nhật dependency management:** thay một điểm quản lý version, tránh pin lẻ tẻ.
8. **Resolve lại graph:** xác nhận không có version bất ngờ hoặc module major bị trộn.
9. **Chạy test:** unit, serialization contract, Spring MVC, YAML/XML nếu dùng, security và integration.
10. **Build artifact cuối:** kiểm tra JAR/WAR/container thực tế.
11. **Scan vulnerability/SBOM:** xác nhận bản phát hành chứa đúng version.
12. **Triển khai có theo dõi:** xem log linkage, mapping error, latency và lỗi parsing sau nâng cấp.

Nâng patch/minor trong cùng release line thường ít thay đổi contract hơn major migration, nhưng vẫn cần test. Major migration cần một nhánh công việc riêng vì có thể đổi package/API, Java baseline hoặc cách tích hợp framework.

## 22. Những test nên chạy sau khi align version

Tùy tính năng project sử dụng, bộ test có thể bao gồm:

- Đọc/ghi DTO có constructor, record, builder và generic type.
- java.time, Optional, Kotlin hoặc module tùy biến.
- Naming strategy, inclusion, mix-in và custom serializer/deserializer.
- Polymorphic deserialization với allowlist và type ID lạ.
- Null, missing field, coercion và unknown property.
- YAML/XML nếu module định dạng được dùng.
- Duplicate-key detection và parser constraints nếu được bật.
- Spring MVC MockMvc để xác nhận message converter.
- RestTemplate/WebClient/message converter hoặc codec được cấu hình riêng.
- Runtime smoke test trên executable JAR/container.
- Concurrency test nếu có custom serializer/deserializer giữ state.

Một test chỉ kiểm tra new ObjectMapper().writeValueAsString() không đại diện cho mapper production do Spring quản lý. Dùng cấu hình và integration point thực tế.

## 23. Các anti-pattern khi xử lý dependency conflict

### 23.1. Pin riêng jackson-databind rồi bỏ qua core

Có thể tạo mismatch giữa databind và core/annotations. Dùng BOM hoặc platform thống nhất.

### 23.2. Thêm Jackson BOM mà không xem Boot BOM

Có thể ghi đè version management của framework ngoài ý muốn. Kiểm tra effective POM/Gradle graph sau khi thêm.

### 23.3. Chỉ xem compile classpath

Runtime hoặc test runtime có thể khác. Kiểm tra configuration thực sự được deploy.

### 23.4. Tin rằng build xanh nghĩa là runtime tương thích

Packaging, classloader, container và shaded JAR có thể thay đổi class được nạp. Kiểm tra artifact và smoke test.

### 23.5. Exclude transitive dependency hàng loạt

Có thể làm thiếu class hoặc phá tương thích SDK. Exclude theo dependency path có lý do và resolve lại graph.

### 23.6. Dùng version mới nhất mà không đọc compatibility

Version mới nhất của một module có thể yêu cầu major Jackson/framework mới. Chọn version theo BOM, release notes và compatibility matrix.

### 23.7. Suppress toàn bộ dependency convergence warning

Điều đó che giấu xung đột thật. Chỉ suppress ngoại lệ đã được hiểu và ghi nhận.

### 23.8. Chỉ quét dependency trực tiếp

Advisory có thể đến từ transitive artifact. Scan resolved graph hoặc SBOM của artifact phát hành.

### 23.9. Nâng dependency mà không kiểm tra integration

Mapper trong service có thể khác mapper trong HTTP converter hoặc message codec. Test từng boundary có sử dụng Jackson.

### 23.10. Trộn Jackson major versions

Có thể gây package/API mismatch và linkage errors. Chọn migration path thống nhất, không trộn 2.x và 3.x trong cùng đường binding.

## 24. Mẫu báo cáo kiểm kê dependency

Một báo cáo ngắn nhưng hữu ích nên có các cột:

| Trường | Nội dung |
|---|---|
| Module ứng dụng | Module tạo JAR/WAR/image được deploy |
| Build tool | Maven hoặc Gradle và version |
| Framework | Spring Boot/Spring Framework version nếu có |
| Jackson BOM owner | Boot BOM, Jackson BOM hoặc platform khác |
| Artifact | GroupId và artifactId |
| Requested versions | Những version được các dependency yêu cầu |
| Selected version | Version cuối cùng trên configuration |
| Dependency path | Dependency trực tiếp/transitive đưa artifact vào |
| Scope/configuration | compile/runtime/test/provided hoặc configuration Gradle |
| Runtime location | JAR trong artifact/container hoặc code source |
| Advisory status | Kết quả scan và mức ảnh hưởng đã đánh giá |
| Action | Giữ, align, exclude có chủ đích hoặc nâng cấp |

Ví dụ bảng minh họa:

| Artifact | Selected version | Được kéo bởi | Ghi chú |
|---|---|---|---|
| jackson-databind | RESOLVED_VERSION | Spring starter, SDK | Kiểm tra BOM owner |
| jackson-core | RESOLVED_VERSION | databind/dataformat | Phải tương thích với databind |
| jackson-annotations | RESOLVED_VERSION | databind/module | Kiểm tra version alignment |
| jackson-datatype-jsr310 | RESOLVED_VERSION | Application | Kiểm tra date/time tests |
| jackson-dataformat-yaml | RESOLVED_VERSION | Config import | Kiểm tra parser YAML transitive |

Các giá trị RESOLVED_VERSION là placeholder cho kết quả thực tế; không điền version bằng suy đoán.

## 25. Checklist kiểm kê và phát hiện xung đột

Trước khi kết luận dependency Jackson ổn định, hãy trả lời:

- Đã liệt kê jackson-core, jackson-annotations, jackson-databind và các module đang dùng chưa?
- Đã xác định dependency trực tiếp và mọi đường transitive chưa?
- Đã xem version được resolve trên runtime classpath chưa?
- Đã kiểm tra test classpath và profile/variant phát hành chưa?
- Có Jackson BOM hoặc platform làm nguồn quản lý version rõ ràng không?
- Nếu dùng Spring Boot, đã xác định Boot BOM đang quản lý Jackson chưa?
- Có version pin riêng lẻ làm lệch BOM không?
- Các module định dạng/kiểu dữ liệu có tương thích với release train không?
- Module bên thứ ba có hỗ trợ version Jackson đã chọn không?
- Có duplicate class, shaded JAR hoặc server-provided library không?
- Runtime thực sự nạp ObjectMapper từ JAR nào?
- Có rule convergence/constraint/locking phù hợp trong CI không?
- Đã quét advisory trên dependency graph hoặc SBOM phát hành chưa?
- Sau nâng cấp đã chạy serialization, deserialization và integration test chưa?

## 26. Kết luận

Kiểm kê Jackson phải dựa trên dependency graph đã resolve và artifact thực sự chạy, không chỉ dựa vào các dòng khai báo trong build file. Jackson gồm nhiều artifact liên quan như core, annotations, databind, datatype, module và dataformat; chúng có thể được kéo vào bởi Spring Boot, SDK hoặc thư viện transitive. Dùng Jackson BOM hoặc dependency management của Spring Boot để giữ một release train nhất quán, sau đó dùng Maven dependency:tree/effective POM hoặc Gradle dependencies/dependencyInsight để truy nguồn version được chọn.

Khi phát hiện mismatch, hãy xác định dependency path, scope/configuration, BOM owner, runtime classloader và nội dung JAR được đóng gói trước khi sửa. Tránh pin lẻ tẻ, exclusion rộng hoặc nâng một artifact riêng mà không kiểm tra các module còn lại. Thêm dependency convergence, locking và vulnerability/SBOM scan vào quy trình phù hợp; khi nâng cấp, align toàn bộ bộ artifact, đọc migration guide, chạy test ở đúng Spring/HTTP/message boundary và xác nhận artifact cuối cùng. Quy trình này giúp phát hiện sớm xung đột version, tránh lỗi linkage chỉ xuất hiện khi deploy và giữ dependency Jackson có thể kiểm soát qua các lần vận hành, vá bảo mật và nâng cấp tiếp theo.
