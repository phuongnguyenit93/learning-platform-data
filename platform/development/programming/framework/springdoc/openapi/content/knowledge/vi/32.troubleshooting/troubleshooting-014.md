# NoSuchMethodError, ClassNotFoundException và xung đột phiên bản

Các lỗi như NoSuchMethodError, ClassNotFoundException và NoClassDefFoundError thường xuất hiện khi ứng dụng Spring Boot được biên dịch với một tập thư viện nhưng lúc chạy lại nạp một tập class khác. Nguyên nhân có thể là dependency bắc cầu chọn sai version, thư viện bị thiếu khỏi runtime classpath, hai JAR chứa cùng một class, ứng dụng đóng gói khác với cấu hình chạy trong IDE hoặc các thành phần Spring/springdoc không thuộc cùng ma trận tương thích.

Không nên xử lý những lỗi này bằng cách thêm ngẫu nhiên một dependency hoặc ép mọi thư viện lên version mới nhất. Cần xác định class hoặc method nào JVM đang tìm, JAR nào thực sự được nạp, dependency nào đưa JAR đó vào runtime và phiên bản nào phù hợp với Spring Boot đang dùng.

Bài này giúp phân biệt các lỗi class loading và binary linkage, lần theo dependency graph bằng Maven/Gradle, căn chỉnh Spring Boot với springdoc-openapi và Swagger libraries, rồi xác minh đúng artifact được triển khai.

## 1. Phân biệt ba lỗi thường gặp

Tên lỗi khá giống nhau nhưng thời điểm phát sinh và cách điều tra khác nhau.

| Lỗi | Loại | Ý nghĩa chính | Dấu hiệu thường gặp |
| --- | --- | --- | --- |
| ClassNotFoundException | Checked exception | Code yêu cầu ClassLoader tải class theo tên nhưng không tìm thấy định nghĩa | Class.forName hoặc lỗi cấu hình provider/plugin có cause là class không tìm thấy |
| NoClassDefFoundError | LinkageError | JVM cần định nghĩa một class trong lúc liên kết hoặc thực thi nhưng class không có trong runtime | Ứng dụng đã compile nhưng lúc khởi động hoặc gọi một nhánh code lại thiếu class |
| NoSuchMethodError | LinkageError | Bytecode gọi một method nhưng class được nạp lúc runtime không có method với descriptor tương ứng | Compile thành công, runtime báo method cụ thể không tồn tại |

Hai lỗi LinkageError thường chỉ ra khác biệt giữa API mà bytecode được biên dịch dựa vào và class definition mà JVM thực sự nạp. ClassNotFoundException thường chỉ ra một yêu cầu tải class theo tên thất bại; nó không tự chứng minh rằng dependency graph có hai version.

## 2. ClassNotFoundException: class được tải theo tên nhưng không tìm thấy

ClassNotFoundException được ném khi ứng dụng gọi cơ chế tải class theo tên như:

- Class.forName("com.example.SomeType").
- ClassLoader.loadClass("com.example.SomeType").
- ClassLoader.findSystemClass("com.example.SomeType") khi được gọi từ subclass phù hợp.

Ví dụ:

~~~java
public class DriverLoader {

    public Object load(String driverClassName)
            throws ReflectiveOperationException {
        Class<?> driverClass = Class.forName(driverClassName);
        return driverClass.getDeclaredConstructor().newInstance();
    }
}
~~~

Nếu class name bị viết sai, JAR chứa class chưa được khai báo, dependency nằm trong test scope hoặc classloader không nhìn thấy JAR, lời gọi trên có thể ném ClassNotFoundException.

Với Spring Boot và springdoc, lỗi này có thể xuất hiện khi:

- Cấu hình plugin, serializer hoặc converter bằng tên class trong property.
- Một thư viện tích hợp cố tải class tùy chọn nhưng dependency tương ứng không có trong runtime.
- Dependency được khai báo với scope test hoặc provided nên không được đóng gói như mong đợi.
- Ứng dụng chạy trong application server có classloader khác với IDE.
- Module hoặc plugin tự tạo ClassLoader và không nhìn thấy dependency của ứng dụng.

Hãy lấy chính xác class name từ exception, tìm JAR nào phải cung cấp class đó, sau đó kiểm tra JAR có trong runtime artifact và classloader có nhìn thấy nó không.

## 3. NoClassDefFoundError: JVM cần class nhưng không thể liên kết

NoClassDefFoundError là LinkageError. JVM hoặc ClassLoader cần định nghĩa một class trong quá trình gọi method, tạo object hoặc liên kết bytecode nhưng không tìm thấy định nghĩa cần thiết. Một trường hợp điển hình là class có mặt lúc compile nhưng không có trong runtime.

Ví dụ:

~~~java
public class ApiFacade {

    public ApiResult execute(ApiClient client) {
        return client.call();
    }
}
~~~

Nếu ApiFacade được biên dịch khi ApiClient tồn tại nhưng JAR triển khai không chứa ApiClient, JVM có thể ném NoClassDefFoundError khi cần resolve class đó.

Một dạng khác cần chú ý là thông báo:

~~~text
java.lang.NoClassDefFoundError: Could not initialize class com.example.SomeConfiguration
~~~

Trường hợp này có thể bắt nguồn từ lỗi xảy ra trong static initializer hoặc quá trình khởi tạo class ở lần đầu. Hãy tìm exception đầu tiên, thường là ExceptionInInitializerError hoặc cause bên dưới, thay vì chỉ sửa dependency dựa trên thông báo NoClassDefFoundError xuất hiện sau đó.

## 4. NoSuchMethodError: class có mặt nhưng thiếu method mà bytecode cần

NoSuchMethodError xảy ra khi code được biên dịch với một method tồn tại trong API tại thời điểm compile, nhưng runtime lại nạp class không có method tương ứng.

Ví dụ minh họa:

~~~java
// Thư viện API version 2 có method mới.
public class DocumentFactory {
    public Document create(String name, boolean includeExamples) {
        return new Document(name, includeExamples);
    }
}
~~~

Một module khác được compile với API version 2 và gọi:

~~~java
Document document =
    factory.create("Orders", true);
~~~

Nếu runtime nạp DocumentFactory từ API version 1 chỉ có create(String), bytecode vẫn yêu cầu descriptor của create(String, boolean) và JVM ném NoSuchMethodError.

Ví dụ trên mô tả cơ chế binary linkage. Trong dự án thật, hãy đọc đầy đủ tên method, kiểu tham số và kiểu trả về trong thông báo lỗi. Sau đó xác định JAR nào cung cấp class chứa method đó.

Không phải mọi thay đổi source đều tạo NoSuchMethodError. JVM liên kết theo tên và descriptor của method. Thay đổi overload, kiểu tham số, kiểu trả về hoặc static/instance có thể tạo lỗi tương thích nhị phân khác nhau như NoSuchMethodError, IncompatibleClassChangeError hoặc AbstractMethodError.

## 5. Các lỗi linkage liên quan cần nhận diện

Khi xử lý NoSuchMethodError, hãy để ý các lỗi cùng họ:

| Lỗi | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| NoSuchFieldError | Field được bytecode tham chiếu không còn trong class runtime | So sánh version JAR và field descriptor |
| AbstractMethodError | Class runtime không cung cấp implementation phù hợp cho method abstract mà caller cần | Kiểm tra version interface, implementation và dependency |
| IncompatibleClassChangeError | Kiểu thay đổi class/interface hoặc static/instance không tương thích | Kiểm tra API binary giữa compile và runtime |
| IllegalAccessError | Code truy cập class/member không còn được phép | Kiểm tra visibility, module và version thư viện |
| NoClassDefFoundError | Class definition cần thiết không có hoặc không khởi tạo được | Kiểm tra runtime classpath và lỗi khởi tạo ban đầu |

Những lỗi này không nên bị gom chung thành “thiếu dependency”. Có trường hợp class vẫn có mặt nhưng cấu trúc binary đã thay đổi.

## 6. Dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là thư viện được khai báo trong build file của ứng dụng. Dependency bắc cầu được kéo vào bởi một dependency khác.

Ví dụ:

~~~text
application
├── springdoc-openapi-starter-webmvc-ui
│   ├── springdoc-openapi-starter-webmvc-api
│   ├── swagger-core
│   └── swagger-ui
└── legacy-reporting-library
    └── swagger-annotations
~~~

Nếu legacy-reporting-library yêu cầu một version Swagger annotation khác với version mà springdoc sử dụng, build tool phải giải quyết xung đột. Dependency graph cuối cùng có thể chỉ chọn một version; nếu version được chọn không tương thích với bytecode của thư viện còn lại, lỗi runtime có thể xảy ra.

Vì vậy, chỉ nhìn dependencies khai báo trực tiếp trong pom.xml hoặc build.gradle là chưa đủ. Cần xem graph đã resolve cho đúng configuration chạy ứng dụng.

## 7. Hiểu compile classpath và runtime classpath

Compile classpath và runtime classpath có thể khác nhau:

- compileClasspath chứa thư viện cần để biên dịch source.
- runtimeClasspath chứa thư viện cần khi chạy ứng dụng.
- testCompileClasspath và testRuntimeClasspath phục vụ test, có thể chứa thư viện mà production không có.
- buildscript/plugin classpath là môi trường chạy plugin build, không phải runtime classpath của ứng dụng.

Một dependency chỉ được thêm vào testImplementation hoặc Maven test scope có thể làm test chạy thành công nhưng không xuất hiện trong executable production.

Khi lỗi chỉ xuất hiện sau khi đóng gói, hãy kiểm tra runtime classpath và nội dung JAR/container image. Đừng chỉ xem compile classpath.

## 8. Căn chỉnh Spring Boot và springdoc-openapi trước tiên

springdoc có các major version gắn với major version Spring Boot. Ma trận tương thích hiện hành của dự án nêu:

| Spring Boot | Dòng springdoc-openapi |
| --- | --- |
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |
| 2.x và 1.x | 1.8.0 là dòng open-source cuối |

Đây là ma trận các dòng đã được springdoc build/test, không phải cam kết mọi patch version trong một major đều thay thế nhau không cần kiểm tra. Khi nâng Spring Boot, hãy chọn springdoc theo đúng dòng Boot và xem release notes của phiên bản cụ thể.

Ví dụ, ứng dụng Spring Boot 3.x không nên dùng springdoc 3.x chỉ vì số version lớn hơn. Dòng springdoc 3.x dành cho Spring Boot 4; dòng springdoc 2.x dành cho Spring Boot 3.

## 9. Đừng tự nâng riêng Spring Framework bên dưới Spring Boot

Spring Boot cung cấp dependency management được kiểm thử theo một tập version. BOM spring-boot-dependencies quản lý Spring Framework và nhiều thư viện tích hợp để các thành phần có thể phối hợp với nhau.

Nếu ứng dụng dùng Spring Boot 3.5.x nhưng tự ép spring-core hoặc spring-web lên version của một dòng Boot khác, classpath có thể chứa API không đồng nhất. Một thư viện compile với method của Spring Framework mới hơn nhưng runtime lại nạp module cũ có thể gây NoSuchMethodError.

Nguyên tắc:

- Chọn Spring Boot version làm điểm neo cho hệ sinh thái Spring.
- Dùng BOM của đúng Spring Boot release để quản lý các dependency mà BOM sở hữu.
- Chỉ override version khi có lý do và đã kiểm tra tương thích.
- Không khai báo version riêng cho từng module Spring Framework nếu không cần.
- Nếu cần nâng một thư viện bên thứ ba ngoài BOM, kiểm tra version của nó với Spring Boot và springdoc.

## 10. Maven: dùng Spring Boot parent hoặc import BOM

Với Maven, cách đơn giản là kế thừa Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
~~~

Sau đó khai báo starter mà không đặt version nếu version được parent quản lý:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jackson</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

Ví dụ dùng Spring Boot 4.1.2 và springdoc 3.2.0 theo ma trận hiện hành. Với Boot 3, thay springdoc bằng dòng 2.x tương ứng; không sao chép version này vào dự án Boot 3.

Nếu dự án không thể kế thừa parent, có thể import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Import BOM vẫn cho phép quản lý version theo Spring Boot nhưng không tự cấu hình mọi plugin như starter parent. Kiểm tra compiler, Surefire và Spring Boot Maven Plugin riêng nếu dự án tự quản lý build.

## 11. Gradle: dùng Spring Boot dependency management hoặc platform

Gradle có thể dùng Spring Boot plugin cùng dependency management plugin, hoặc native BOM support.

Ví dụ Kotlin DSL với platform:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
}

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:4.1.2"
    ))

    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-jackson")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0")
}
~~~

Spring Boot BOM quản lý các dependency thuộc danh mục của Boot. springdoc là dependency bên ngoài BOM trong ví dụ này nên version được khai báo theo compatibility matrix.

Nếu dùng plugin io.spring.dependency-management, Spring Boot plugin có thể tự import BOM tương ứng. Không cần vừa khai báo platform, vừa import cùng BOM qua plugin nếu dự án đã chọn một cơ chế quản lý version rõ ràng.

## 12. Tránh ép version swagger-core và swagger-annotations tùy tiện

springdoc phụ thuộc vào các thư viện OpenAPI/Swagger như swagger-core, swagger-annotations và các module liên quan. Các version này cần tương thích với dòng springdoc đang dùng.

Một lỗi thường gặp là ứng dụng thêm trực tiếp:

~~~xml
<dependency>
    <groupId>io.swagger.core.v3</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

trong khi springdoc starter đang kéo một version khác. Nếu version trực tiếp thắng quá trình mediation, runtime có thể dùng annotation/model API không phù hợp với bytecode của springdoc hoặc module Swagger còn lại.

Hãy làm theo thứ tự:

1. Xem version swagger-core và swagger-annotations mà springdoc starter yêu cầu.
2. Xác định dependency trực tiếp hoặc thư viện khác đang override version.
3. Gỡ version override nếu không còn lý do.
4. Nếu cần version khác, kiểm tra compatibility của toàn bộ swagger-core modules, không chỉ một artifact.
5. Chạy lại dependency tree và test endpoint OpenAPI.

Không nên thêm riêng swagger-annotations chỉ vì IDE báo thiếu import nếu starter springdoc đã cung cấp transitively. Nếu dự án muốn khai báo dependency trực tiếp vì quy ước build, hãy để dependency management chọn version phù hợp.

## 13. Maven: xem dependency tree đã resolve

Lệnh cơ bản:

~~~bash
./mvnw dependency:tree
~~~

Chỉ xem runtime scope:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Lọc các thư viện liên quan Spring, springdoc và Swagger:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:*,org.springdoc:*,io.swagger.core.v3:*
~~~

Dependency Plugin hỗ trợ xuất graph sang file:

~~~bash
./mvnw dependency:tree -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

JSON output cần phiên bản Maven Dependency Plugin có hỗ trợ định dạng đó. Nếu Maven báo không nhận outputType=json, kiểm tra plugin version; có thể dùng output text mặc định.

Trong output, chú ý:

- Version được chọn cho từng artifact.
- Các nhánh đưa một artifact vào graph.
- Node bị omitted hoặc version conflict.
- Scope compile, runtime, provided và test.
- Artifact xuất hiện qua nhiều dependency path.

Khi cần biết effective configuration sau khi áp parent và profile, dùng:

~~~bash
./mvnw help:effective-pom
~~~

Effective POM giúp xác định dependencyManagement, property và profile nào đang điều khiển version cuối.

## 14. Gradle: xem dependencies và lý do chọn version

Liệt kê runtime graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra riêng Spring Framework:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Kiểm tra riêng springdoc:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Kiểm tra Swagger:

~~~bash
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

Dependency insight cho biết version được chọn, dependency nào yêu cầu version khác và lý do Gradle chọn version cuối, chẳng hạn conflict resolution, constraint, platform hoặc forced rule.

Đừng chỉ kiểm tra compileClasspath. Lỗi phát sinh khi chạy executable cần đối chiếu runtimeClasspath. Nếu plugin build lỗi, kiểm tra buildEnvironment vì plugin classpath tách khỏi runtime classpath của ứng dụng.

## 15. Maven Enforcer và dependency convergence

Maven Enforcer có rule dependencyConvergence để phát hiện một artifact được yêu cầu với nhiều version trên các nhánh khác nhau của dependency tree.

Ví dụ cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.7.0</version>
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
~~~

Rule này hữu ích để phát hiện graph yêu cầu nhiều version của cùng artifact. Tuy nhiên, dependency convergence không chứng minh mọi dependency đều tương thích nhị phân. Một graph có duy nhất một version vẫn có thể chọn nhầm version không phù hợp với caller.

Nếu có ngoại lệ hợp lệ, cấu hình includes/excludes hoặc scope rõ ràng và ghi lại lý do. Không tắt toàn bộ rule chỉ vì một dependency có xung đột.

## 16. Gradle constraints và tránh force version toàn cục

Gradle hỗ trợ dependency constraints để điều khiển version của dependency trực tiếp hoặc bắc cầu:

~~~kotlin
dependencies {
    constraints {
        implementation("com.example:compatibility-module") {
            version {
                strictly("2.4.1")
            }
            because("Phiên bản đã được xác minh với runtime của ứng dụng")
        }
    }
}
~~~

Đây chỉ là ví dụ cú pháp constraint. Trong ứng dụng Spring Boot, ưu tiên BOM/platform và chỉ dùng strictly khi đã xác minh version cụ thể cần thiết.

Tránh dùng resolutionStrategy.force cho hàng loạt module Spring hoặc Swagger. Force có thể làm graph nhìn đồng nhất nhưng ép thư viện vào version mà nó chưa được build/test cùng. Hãy sửa dependency gây xung đột hoặc thêm constraint có phạm vi hẹp và lý do rõ ràng.

## 17. Exclusion chỉ dùng khi đã xác định nhánh gây lỗi

Nếu một thư viện cũ kéo một dependency bắc cầu không phù hợp, có thể exclude dependency đó tại đúng nhánh và khai báo version thay thế đã xác minh.

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-integration</artifactId>
    <version>5.1.0</version>
    <exclusions>
        <exclusion>
            <groupId>io.swagger.core.v3</groupId>
            <artifactId>swagger-annotations</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Chỉ dùng ví dụ này nếu đã chứng minh legacy-integration kéo version xung đột và có một version tương thích khác được quản lý ở nơi phù hợp. Exclusion không tự thêm dependency thay thế. Nếu bỏ một module mà code vẫn cần class của nó, ứng dụng sẽ chuyển từ lỗi version sang lỗi thiếu class.

Sau exclusion, chạy lại dependency tree và test runtime. Kiểm tra các dependency khác có thực sự cung cấp class mà thư viện đang cần không.

## 18. Kiểm tra class nào thực sự được JVM nạp

Dependency graph cho biết những JAR nào được resolve, nhưng khi có nhiều classloader hoặc môi trường đóng gói khác nhau, cần xác nhận class runtime đến từ đâu.

Có thể in CodeSource của một class đã nạp:

~~~java
import java.security.CodeSource;

public final class ClassOrigin {

    public static void print(Class<?> type) {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        System.out.println(
            type.getName() + " -> "
                + (source == null ? "unknown" : source.getLocation())
        );
    }
}
~~~

Gọi với các class đại diện như SpringApplication, Spring MVC class, class của springdoc hoặc swagger-core mà stack trace nhắc tới. CodeSource có thể null trong một số classloader hoặc module, vì vậy đây là bằng chứng hữu ích nhưng không phải lúc nào cũng có kết quả.

Với JDK 9 trở lên, có thể bật log class loading:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Với JDK 8, tùy chọn thường dùng là:

~~~bash
java -verbose:class -jar app.jar
~~~

Tìm class liên quan trong log để biết classloader nạp nó từ vị trí nào. Dùng log có chọn lọc vì output có thể rất lớn.

## 19. Kiểm tra nội dung executable JAR

Ứng dụng chạy trong IDE có thể dùng classpath khác với executable JAR. Với Spring Boot executable JAR, dependency thường được đóng gói dưới BOOT-INF/lib.

Liệt kê nội dung:

~~~bash
jar tf target/application.jar
~~~

Lọc thư viện liên quan trên Windows:

~~~powershell
jar tf target/application.jar | Select-String 'BOOT-INF/lib/(spring|springdoc|swagger|jackson)'
~~~

Trên Linux/macOS:

~~~bash
jar tf target/application.jar | grep -E 'BOOT-INF/lib/(spring|springdoc|swagger|jackson)'
~~~

Kiểm tra:

- spring-core, spring-web, spring-context có cùng dòng Spring Boot quản lý.
- Chỉ có một version của mỗi module quan trọng trong executable.
- springdoc starter và module đi kèm cùng một dòng version.
- swagger-core, swagger-models và swagger-annotations không bị override ngoài ý muốn.
- Jackson modules phù hợp với Jackson core/databind mà ứng dụng nạp.

Nếu JAR đúng nhưng container vẫn lỗi, kiểm tra Docker image có copy đúng artifact mới không. Một image cũ hoặc layer cache có thể giữ executable khác với file vừa kiểm tra.

## 20. Kiểm tra compile-time API bằng javap

Khi NoSuchMethodError nêu rõ class và method, có thể dùng javap để xem method có tồn tại trong JAR đang kiểm tra không.

Ví dụ:

~~~bash
javap -classpath path/to/library.jar com.example.DocumentFactory
~~~

Nếu method cần không có trong output, JAR đó không cung cấp API mà bytecode đang gọi. Hãy so sánh:

1. JAR dùng trong compile classpath.
2. JAR được chọn trong runtimeClasspath.
3. JAR thực sự nằm trong executable hoặc container.

Có thể dùng javap -c -verbose trên class caller để xem bytecode và method descriptor được tham chiếu. Cần hiểu descriptor JVM chứ không chỉ so tên method vì overload có thể cùng tên nhưng khác chữ ký.

## 21. Kiểm tra javax và jakarta khi nâng Spring Boot

Spring Boot 3 chuyển hệ sinh thái Spring sang Jakarta EE APIs. Các package như:

- javax.servlet chuyển sang jakarta.servlet.
- javax.validation chuyển sang jakarta.validation.
- javax.persistence chuyển sang jakarta.persistence.

Class có cùng tên đơn giản nhưng package khác là hai class khác nhau đối với JVM. Một thư viện compile với javax API không tự tương thích với jakarta API chỉ vì chức năng tương tự.

Các lỗi thường thấy:

- ClassNotFoundException hoặc NoClassDefFoundError cho javax.servlet.* khi runtime chỉ có Jakarta Servlet.
- Method parameter hoặc return type không tương thích vì descriptor chứa javax thay vì jakarta.
- Framework cũ không nhận annotation Jakarta.
- Hai dependency cũ/mới kéo hai hệ namespace vào cùng ứng dụng và tạo hành vi khó đoán.

Khi nâng Boot 2 lên Boot 3, nâng đồng bộ thư viện tích hợp, validation provider, persistence provider, servlet container và các module dùng javax. Không thêm lại javax API chỉ để làm mất thông báo lỗi nếu ứng dụng đã chuyển sang Jakarta.

Khi nâng tiếp lên Spring Boot 4, kiểm tra thêm modularization và Jackson 3:

- Starter MVC hiện hành là spring-boot-starter-webmvc; spring-boot-starter-web được giữ ở dạng deprecated để hỗ trợ chuyển tiếp.
- Starter JSON mặc định là spring-boot-starter-jackson.
- Jackson 3 dùng group/package tools.jackson; Jackson 2 dùng com.fasterxml.jackson. Ngoại lệ là jackson-annotations vẫn tiếp tục dùng group com.fasterxml.jackson.core và package com.fasterxml.jackson.annotation.
- Thư viện chỉ hỗ trợ Jackson 2 có thể cần ObjectMapper riêng hoặc module tương thích Jackson 2 của Spring Boot 4. Không ép Jackson 2 và Jackson 3 thành một version vì chúng là các dòng API khác nhau.

Khi thấy NoClassDefFoundError hoặc NoSuchMethodError quanh ObjectMapper, JsonMapper, serializer hoặc customizer, hãy xác định ứng dụng đang dùng mapper nào và dependency nào kéo từng major Jackson vào runtime. Đối chiếu migration guide của Boot 4 trước khi thêm module tương thích.

## 22. Phân biệt lỗi ứng dụng với lỗi build plugin

Một dự án có nhiều classpath:

| Classpath | Dùng cho |
| --- | --- |
| Application compile classpath | Biên dịch source của ứng dụng |
| Application runtime classpath | Chạy ứng dụng |
| Test runtime classpath | Chạy test |
| Maven plugin classpath | Chạy Maven plugin |
| Gradle buildscript/plugin classpath | Chạy Gradle plugin |

Nếu lỗi xuất hiện khi chạy plugin generate OpenAPI, lỗi có thể nằm ở plugin classpath thay vì runtime ứng dụng. Ngược lại, plugin build thành công không chứng minh ứng dụng runtime không xung đột.

Với Gradle, dùng:

~~~bash
./gradlew buildEnvironment
~~~

để xem buildscript dependencies. Với Maven, xem plugin và plugin dependencies trong effective POM hoặc dependency:resolve-plugins khi cần.

Ghi lại chính xác lỗi xảy ra ở giai đoạn nào: compile, test, package, plugin execution, startup hay khi gọi endpoint. Giai đoạn phát sinh giúp thu hẹp classpath cần điều tra.

## 23. Phân biệt lỗi do classloader và lỗi do version

Không phải mọi lỗi ClassNotFoundException đều được giải quyết bằng cách nâng version.

Một số môi trường có nhiều classloader:

- Spring Boot DevTools có restart classloader.
- Application server có classloader riêng cho server và từng deployment.
- Plugin architecture có classloader riêng cho mỗi plugin.
- OSGi hoặc Java module layer có ranh giới visibility.
- Thread context classloader có thể khác classloader của class đang chạy.

Nếu JAR có trong file nhưng ClassLoader không nhìn thấy class, hãy điều tra:

1. ClassLoader nào thực hiện việc tải class?
2. Thread context classloader đang là gì?
3. Class có nằm trong module/classloader được phép truy cập không?
4. Dependency có bị đóng gói ở classloader khác không?
5. IDE/devtools có tạo classloader khác với executable không?

Không thay Thread.currentThread().setContextClassLoader() trên toàn ứng dụng nếu chưa xác định thư viện nào cần context loader. Thay đổi global có thể ảnh hưởng ServiceLoader, logging, JDBC driver hoặc plugin khác.

## 24. Kiểm tra HttpMessageConverter khi Swagger UI không render được

Một lỗi không nhất thiết là NoSuchMethodError có thể khiến người dùng tưởng springdoc bị xung đột version: Swagger UI báo không render được definition sau khi ứng dụng override HttpMessageConverter.

FAQ springdoc lưu ý khi thay danh sách HttpMessageConverter mặc định của Spring Boot, cần giữ ByteArrayHttpMessageConverter và thứ tự converter phù hợp. Nếu converter xử lý response OpenAPI bị thay đổi, endpoint /v3/api-docs có thể trả nội dung hoặc media type không đúng.

Kiểm tra trực tiếp:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Xác minh:

- Status code là 200.
- Content-Type phù hợp với JSON.
- Body là JSON hợp lệ, không phải trang HTML lỗi/login.
- Response không bị converter tùy chỉnh biến đổi.

Đây là lỗi HTTP serialization/negotiation, không nên vội sửa bằng cách ép version swagger-core.

## 25. Một số parameter biến mất sau khi nâng Spring Boot

Nếu OpenAPI document không sinh ra tên parameter như mong đợi sau khi nâng Spring Boot 3.2, hãy kiểm tra Java parameter name discovery và cấu hình compiler.

Springdoc FAQ ghi nhận cần biên dịch với tùy chọn -parameters để giữ tên tham số trong bytecode khi ứng dụng dựa vào parameter name discovery.

Ví dụ Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Ví dụ Gradle:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đây là vấn đề metadata lúc compile, không nhất thiết là dependency conflict. Hãy kiểm tra class file và OpenAPI document trước khi thay version thư viện.

## 26. Quy trình chẩn đoán có thứ tự

Khi gặp NoSuchMethodError, ClassNotFoundException hoặc NoClassDefFoundError, làm theo thứ tự:

1. Lưu toàn bộ stack trace, bao gồm cause đầu tiên và class/method đầy đủ.
2. Xác định lỗi xuất hiện ở compile, test, package, startup hay request runtime.
3. Xác định class hoặc method mà JVM không tìm thấy.
4. Xác định artifact/JAR phải cung cấp class hoặc method đó.
5. Xem compileClasspath và runtimeClasspath.
6. Tìm dependency path đưa version đang được chọn vào graph.
7. So sánh Spring Boot, springdoc, Spring Framework, Swagger và Jackson version.
8. Kiểm tra executable JAR/container thực tế.
9. Kiểm tra class origin hoặc classloader nếu graph đúng mà lỗi vẫn còn.
10. Sửa dependency declaration, BOM, constraint hoặc exclusion tại đúng nguồn gây xung đột.
11. Xóa output build cũ và build lại artifact từ source hiện tại.
12. Chạy chính artifact đã đóng gói, không chỉ chạy trong IDE.
13. Kiểm tra OpenAPI JSON, Swagger UI và endpoint nghiệp vụ liên quan.

Không thay nhiều version cùng lúc. Thay một nguyên nhân, tạo artifact mới, rồi kiểm tra xem lỗi đã biến mất và không xuất hiện lỗi linkage khác chưa.

## 27. Ví dụ điều tra một NoSuchMethodError trong springdoc

Giả sử ứng dụng báo:

~~~text
java.lang.NoSuchMethodError:
  'some.Type some.library.Api.method(java.lang.String)'
~~~

Không nên đoán rằng springdoc có bug. Hãy thực hiện:

**Bước 1 — Xác định class chứa method**

Đọc stack trace để tìm class caller và class sở hữu method. Ghi lại package, method name và parameter type.

**Bước 2 — Tìm artifact sở hữu class**

Xem dependency tree để biết artifact nào cung cấp package đó. Kiểm tra có nhiều version hoặc thư viện legacy kéo version cũ không.

**Bước 3 — Xác minh version runtime**

Dùng dependencyInsight hoặc dependency:tree scope runtime để biết version được chọn. Kiểm tra JAR đóng gói để chắc chắn executable chứa đúng version đó.

**Bước 4 — So sánh API binary**

Dùng javap trên JAR runtime và JAR compile nếu còn. Xác định method descriptor có tồn tại ở runtime hay không.

**Bước 5 — Sửa nguồn quản lý version**

Nếu Spring Boot BOM quản lý module bị override, bỏ override không cần thiết. Nếu springdoc major không phù hợp với Boot, chọn đúng major. Nếu dependency legacy kéo version cũ, cập nhật thư viện hoặc exclude có kiểm soát.

**Bước 6 — Xác minh**

Chạy ứng dụng từ executable JAR/container mới, gọi /v3/api-docs và /swagger-ui.html, sau đó chạy các test endpoint quan trọng.

## 28. Bảng chẩn đoán nhanh

| Thông báo | Kiểm tra đầu tiên | Kiểm tra tiếp theo |
| --- | --- | --- |
| ClassNotFoundException: com.example.X | Tên class và nơi gọi Class.forName/loadClass | Runtime scope, classloader và JAR chứa X |
| NoClassDefFoundError: com/example/X | Class X có trong executable không | Optional/provided dependency, packaging và lỗi khởi tạo trước đó |
| NoClassDefFoundError: Could not initialize class | Exception đầu tiên trong static initializer | Config, static initialization và root cause |
| NoSuchMethodError: Y.foo(...) | JAR runtime của class Y | Compile/runtime version và method descriptor |
| NoSuchFieldError | JAR runtime và field descriptor | Version caller/callee |
| AbstractMethodError | Interface và implementation | Dependency version và binary compatibility |
| ClassCastException cùng tên class | Hai classloader có nạp hai bản class không | Class origin, DevTools và application server |
| Swagger UI unable to render definition | Response /v3/api-docs | JSON body, content type, converter, security và CORS |
| Parameter không có tên trong document | Compiler có giữ parameter names không | Tùy chọn -parameters và annotation @Parameter |

## 29. Checklist phòng ngừa xung đột version

- [ ] Spring Boot version được chọn rõ và dùng làm điểm neo dependency management.
- [ ] springdoc major khớp Spring Boot major.
- [ ] Không override riêng Spring Framework module nếu không có lý do đã xác minh.
- [ ] swagger-core và swagger-annotations không bị ép version ngoài ý muốn.
- [ ] Jackson modules được quản lý nhất quán.
- [ ] Không để dependency production chỉ nằm trong test scope.
- [ ] Đã kiểm tra runtimeClasspath chứ không chỉ compileClasspath.
- [ ] Đã xem dependency tree hoặc dependencyInsight khi nâng version.
- [ ] Maven Enforcer hoặc Gradle constraints được dùng có chủ đích.
- [ ] Exclusion có lý do và dependency thay thế đã được xác nhận.
- [ ] Không còn hai JAR khác version cùng cung cấp class quan trọng.
- [ ] Executable JAR/container chứa đúng dependency đã resolve.
- [ ] Đã test bằng artifact đóng gói, không chỉ chạy trong IDE.
- [ ] Classloader và class origin được kiểm tra khi graph không giải thích được lỗi.
- [ ] OpenAPI JSON, Swagger UI và API runtime đã được smoke test sau nâng cấp.

## Tài liệu tham khảo

- [Java API – NoSuchMethodError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoSuchMethodError.html)
- [Java API – ClassNotFoundException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassNotFoundException.html)
- [Java API – NoClassDefFoundError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NoClassDefFoundError.html)
- [springdoc-openapi – Compatibility Matrix and FAQ](https://springdoc.org/faq.html)
- [springdoc-openapi v2 – Compatibility Matrix and FAQ](https://springdoc.org/v2/faq.html)
- [Spring Boot – Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot 4.0 – Migration Guide, modular starters and Jackson 3](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot – Gradle Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Enforcer – Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html)
