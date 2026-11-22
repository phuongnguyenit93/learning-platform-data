# Tương thích JDK của dependency trực tiếp và bắc cầu

## 1. Vì sao dependency là điểm rủi ro của Java migration?

Trong **Java Advance Compatibility Migration**, việc thay JDK không chỉ tác động đến mã nguồn do nhóm phát triển tự viết. Một ứng dụng thường phụ thuộc vào hàng chục hoặc hàng trăm thư viện: framework, JSON/XML serialization, HTTP client, database driver, logging, security, cache, testing, bytecode manipulation, build plugin và các thành phần tích hợp.

Một dependency có thể chạy tốt trên JDK hiện tại nhưng gặp lỗi khi chuyển JDK vì:

- Thư viện được biên dịch cho Java mới hơn runtime được triển khai.
- Thư viện dùng API JDK bị loại bỏ hoặc thay đổi hành vi.
- Framework cũ truy cập API nội bộ JDK hoặc thực hiện reflection vào package không còn mở.
- Dependency bắc cầu kéo vào một phiên bản class không tương thích với thư viện gọi nó.
- Build tool chọn khác version dependency giữa compile, test và runtime.
- Một JAR chứa native library hoặc javaagent không hỗ trợ CPU/JDK đích.
- Các module chạy qua module path khác với classpath truyền thống.
- Một thư viện dùng namespace javax.*, thư viện khác kỳ vọng jakarta.*.
- Thư viện mới yêu cầu Java version cao hơn mức Java tối thiểu mà sản phẩm đã cam kết.

Một bản build thành công không tự chứng minh ứng dụng tương thích JDK. Compiler có thể không nhìn thấy toàn bộ dependency runtime; class chỉ được nạp ở một đường xử lý hiếm gặp; hoặc container triển khai thực tế mang bộ dependency khác với test environment.

Vì vậy, quản lý dependency trong migration cần kiểm tra **toàn bộ đồ thị phụ thuộc thực sự được phân giải**, không chỉ danh sách thư viện khai báo trực tiếp.

## 2. Direct dependency và transitive dependency

### 2.1. Dependency trực tiếp

**Direct dependency** là thư viện ứng dụng khai báo rõ trong file build, ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:api-client:3.2.0")
    implementation("com.example:json-adapter:2.1.0")
}
~~~

Đây là các tọa độ minh họa, không phải thư viện thực tế để tải. Người phát triển có chủ đích chọn api-client và json-adapter.

### 2.2. Dependency bắc cầu

**Transitive dependency** là thư viện được một dependency khác yêu cầu, ngay cả khi dự án không khai báo trực tiếp.

~~~text
application
  ├─ api-client:3.2.0             (direct)
  │   ├─ http-core:5.0.0         (transitive)
  │   │   └─ tls-helper:2.0.0    (transitive)
  │   └─ json-core:4.1.0         (transitive)
  └─ json-adapter:2.1.0           (direct)
      └─ json-core:3.8.0         (transitive, xung đột version)
~~~

Ở đồ thị trên, json-core xuất hiện ở hai đường với hai version. Build tool sẽ áp dụng quy tắc giải quyết conflict để chọn phiên bản thực tế, hoặc báo lỗi nếu cấu hình/metadata không cho phép chọn một bản nhất quán.

Thư viện ở một cấp sâu như tls-helper vẫn có thể làm ứng dụng không chạy trên JDK mục tiêu. Việc không khai báo trực tiếp không làm rủi ro của nó biến mất.

### 2.3. Đồ thị được khai báo khác với đồ thị được sử dụng

Phải phân biệt:

1. **Declared dependencies:** các dependency xuất hiện trong build script/POM.
2. **Resolved dependencies:** phiên bản cuối cùng được công cụ build chọn sau conflict resolution, dependency management, constraints và exclusions.
3. **Packaged dependencies:** các JAR/class thực sự được đặt trong executable JAR, container, deployment directory hoặc application server.
4. **Loaded dependencies:** những class được runtime/classloader thực sự nạp trong luồng chạy.

Một dependency có thể được khai báo nhưng bị loại bởi profile; có thể được chọn ở runtime khác version compile; hoặc không đóng gói vì scope provided. Khi có lỗi JDK, cần truy tới artifact thực tế, không chỉ nhìn file build ban đầu.

## 3. Những chiều tương thích phải xác định

Tương thích JDK của một thư viện không phải thuộc tính nhị phân “có/không” theo một con số duy nhất. Hãy xem từng chiều:

| Chiều tương thích | Câu hỏi | Bằng chứng cần có |
|---|---|---|
| Bytecode | Class file của dependency có được JVM mục tiêu đọc không? | Class-file major version; kiểm tra toàn bộ artifact. |
| Java API | Thư viện có gọi API chỉ có ở release mới hơn hoặc bị loại khỏi JDK? | Biên dịch/test trên runtime tối thiểu, phân tích bằng công cụ. |
| JVM internals | Thư viện có dùng sun.*, jdk.internal.* hoặc reflection vào JDK? | jdeps, log IllegalAccess/InaccessibleObjectException, release notes. |
| Binary linkage | Method/class/field mà thư viện tham chiếu có đúng version runtime không? | Dependency graph và integration test; linkage errors. |
| Module system | Module name, requires, exports, opens, split packages có hợp lệ? | module-info, jdeps, chạy trên module path thực tế. |
| Framework integration | Thư viện có tương thích framework/container phiên bản mục tiêu? | Support matrix, BOM và integration tests. |
| Native code / agent | JNI, JNA, JVMTI, agent có hỗ trợ JDK/OS/CPU? | Vendor docs, thực thi trên runtime/architecture mục tiêu. |
| Behavioral | API dùng được nhưng hành vi có còn phù hợp? | Regression tests về TLS, serialization, concurrency, locale và nghiệp vụ. |
| Security/support | Version còn được vá và hỗ trợ trên JDK mục tiêu? | Release notes, advisory và chính sách bảo trì từ nhà cung cấp. |

Thư viện có class file tương thích Java 17 vẫn có thể gặp lỗi khi chạy trên Java 17 nếu tham chiếu method chỉ có ở Java 21, hoặc dependency runtime thực tế mang bytecode Java 21.

**Mức Java tối thiểu của ứng dụng không được thấp hơn mức cao nhất bắt buộc trong các dependency cần thiết ở runtime**, trừ khi có cơ chế đóng gói/biến thể khác được thiết kế và kiểm chứng riêng.

## 4. Class-file version: dấu hiệu đầu tiên

JVM chỉ nạp được class file có định dạng mà phiên bản đó hỗ trợ. Một class được biên dịch cho runtime mới có thể thất bại trên Java cũ với UnsupportedClassVersionError.

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Đọc metadata của class:

~~~bash
javap -verbose -classpath dependency.jar com.example.library.EntryPoint
~~~

Tìm trường major version trong output.

### 4.1. Cần xem toàn bộ JAR, không chỉ một class

Một JAR có thể chứa nhiều package, class sinh tự động, dependency đã được shade hoặc các class trong META-INF/versions của multi-release JAR. Kiểm tra một entry point không bảo đảm mọi class khác trong artifact đều có cùng target.

Có thể liệt kê nội dung:

~~~bash
jar tf dependency.jar
~~~

Khi có multi-release JAR, phần base và các biến thể dành riêng cho các Java release có thể dùng class-file version khác nhau. Cần xác nhận cách JVM chọn class theo runtime mục tiêu, đặc biệt với dependency packaging hoặc công cụ phân tích không xử lý đúng multi-release layout.

### 4.2. Mức release của build không phải mức Java runtime

Ví dụ Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Cấu hình này yêu cầu compiler toolchain Java 21 nhưng tạo code application theo Java 17 ở các task JavaCompile liên quan. Nó **không** buộc dependency runtime cũng tương thích Java 17. Nếu runtimeClasspath kéo một JAR chỉ dành cho Java 21, ứng dụng có thể vẫn lỗi trên Java 17.

Tương tự, Maven property maven.compiler.release chỉ điều khiển việc compile của dự án trong cấu hình phù hợp, không sửa bytecode bên trong JAR đã tải từ repository.

## 5. Java API và các thay đổi khác ngoài bytecode

Ngay cả khi major version phù hợp, dependency vẫn có thể gặp rủi ro vì thay đổi nền tảng.

### 5.1. API bị loại bỏ khỏi JDK

Một ví dụ điển hình là các module Java EE và CORBA từng đi kèm một số JDK cũ nhưng đã bị loại bỏ từ JDK 11. Thư viện legacy có thể tham chiếu javax.xml.bind, javax.xml.ws hoặc org.omg.CORBA mà trước đây không cần dependency bên ngoài.

Trong trường hợp này:

- Kiểm tra source/bytecode và các thư viện tích hợp đang sử dụng API gì.
- Xác định API JAR và runtime implementation thay thế.
- Chọn thế hệ javax hay jakarta phù hợp với framework.
- Kiểm chứng cả build-time code generation và runtime provider.

Không nên chỉ thêm một JAR API rồi kết luận chức năng XML/SOAP hoạt động. Đối với một số công nghệ, runtime implementation hoặc provider độc lập mới là thành phần thực thi thực tế.

### 5.2. Encapsulation và API nội bộ

Một số dependency cũ truy cập API nội bộ JDK, ví dụ sun.misc hoặc jdk.internal, hoặc dùng reflection để mở private field của lớp Java nền tảng.

Khi JDK áp dụng module encapsulation chặt hơn, ứng dụng có thể gặp:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
~~~

Để phát hiện phụ thuộc JDK internal API:

~~~bash
jdeps --jdk-internals dependency.jar
~~~

Tuy nhiên, phân tích tĩnh không bảo đảm phát hiện những lookup bằng reflection với tên class được tạo động. Phải kết hợp integration tests.

Các flag như --add-opens hoặc --add-exports đôi khi được dùng như biện pháp chuyển tiếp có kiểm soát, nhưng không phải bằng chứng thư viện đã tương thích lâu dài. Nếu nhà cung cấp đã phát hành bản thay API nội bộ bằng API được hỗ trợ, thường nên ưu tiên bản phù hợp đó.

### 5.3. Thay đổi hành vi runtime

Một dependency xử lý TLS, timezone, locale, charset, serialization hoặc concurrency có thể thay đổi behavior khi đổi JDK dù không lỗi linkage:

- TLS handshake hoặc certificate validation thất bại vì security policy khác.
- Charset hoặc locale mặc định thay đổi cách encode/decode dữ liệu.
- Reflective access không còn như trước.
- Serialization framework cần module opens hay cấu hình mới.
- Date/time và timezone database ảnh hưởng kết quả định dạng.
- Thuật toán hoặc native provider có khác biệt về tính toán số.

Cần xác định hợp đồng nghiệp vụ quan trọng và thử trên JDK thật, không chỉ dựa vào compatibility claim của thư viện.

## 6. Dependency graph trong Gradle

Gradle giải quyết dependency theo configuration và có thể sử dụng module metadata, variants, constraints, platforms và rules. Vì vậy phải kiểm tra từng classpath cần thiết, không chỉ một danh sách toàn dự án.

### 6.1. Xem dependency của compile và runtime

Ví dụ ở project dùng Java/Java Library plugin:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Nếu multi-module:

~~~bash
./gradlew :service-a:dependencies --configuration runtimeClasspath
~~~

Lưu ý tên configuration có thể khác theo plugin hoặc module; những lệnh trên minh họa cho một số Java source set thông thường.

### 6.2. Tìm nguồn một dependency bắc cầu

~~~bash
./gradlew :service-a:dependencyInsight \
    --dependency library-name \
    --configuration runtimeClasspath
~~~

dependencyInsight giúp quan sát đường phụ thuộc và lý do một version được chọn, ví dụ constraint, rule hoặc xung đột version. Với Gradle, một thư viện yêu cầu version cao hơn có thể khiến Gradle chọn một phiên bản khác với bản developer mong đợi trong trường hợp không có ràng buộc cứng.

Khi thấy một thư viện không tương thích Java 17 nhưng xuất hiện trong runtimeClasspath, cần tìm **thư viện cha kéo nó vào**, không chỉ xóa JAR ở folder build.

### 6.3. Phân biệt các configuration

| Configuration | Phạm vi thường gặp | Ý nghĩa cho migration |
|---|---|---|
| implementation | Dependency dùng trong triển khai, không nhất thiết lộ vào compile API của consumer. | Thường ảnh hưởng compile/runtime của module và runtime downstream theo metadata. |
| api | Dependency lộ trong public API của module dùng java-library plugin. | Consumer có thể cần type của nó khi compile; nâng version có thể ảnh hưởng source/binary API. |
| compileOnly | Có khi compile, không tự được đưa vào runtime. | Dễ thiếu class ở runtime nếu container không cung cấp. |
| runtimeOnly | Cần khi chạy nhưng không cần compile source chính. | Có thể tạo lỗi chỉ lộ ở runtime. |
| testImplementation | Dùng cho test compile/runtime. | Test framework hoặc helper cũng có mức JDK tối thiểu riêng. |
| testRuntimeOnly | Chỉ cần khi chạy test. | Test có thể lỗi JDK dù ứng dụng production không dùng dependency đó. |

Một project có thể có các configuration đặc thù của framework/plugin. Phải xem resolved graph thật của artifact/launcher được triển khai.

### 6.4. Gradle variant và Java compatibility metadata

Khi được công bố trong metadata, Gradle có thể sử dụng thuộc tính Java compatibility của variant, chẳng hạn org.gradle.jvm.version, trong quá trình lựa chọn artifact phù hợp. Cơ chế này giúp phát hiện một số trường hợp dependency yêu cầu Java mới hơn consumer.

Tuy nhiên:

- Không phải mọi artifact từ Maven repository có metadata mô tả đầy đủ mức Java tối thiểu.
- Metadata sai hoặc thiếu có thể dẫn đến chọn artifact không phù hợp.
- Kiểm tra variant không thay thế kiểm tra class file và runtime tests.
- Java toolchain của task compile, target của module và Java phiên bản chạy Gradle là các khái niệm khác nhau.

Vì vậy, khi Gradle báo không tìm được matching variant cho Java version, nên kiểm tra metadata và mức Java mà consumer thực sự khai báo. Không tự nâng target chỉ để resolver hết lỗi nếu sản phẩm vẫn có nghĩa vụ hỗ trợ JDK cũ.

## 7. Dependency graph trong Maven

Maven giải quyết dependency bằng POM, scope, dependencyManagement và các quy tắc mediation. Với bản phát hành thông thường, cần kiểm tra resolved tree thay vì chỉ các dependency ghi trong pom.xml.

### 7.1. Xem cây phụ thuộc

~~~bash
./mvnw dependency:tree
~~~

Nếu cần tập trung runtime:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Có thể lọc theo nhóm artifact khi công cụ và phiên bản plugin hỗ trợ:

~~~bash
./mvnw dependency:tree -Dincludes=org.example:example-core
~~~

Trong các lệnh này, org.example:example-core là tọa độ minh họa. Nếu plugin cần được cài/cấu hình, phải dùng phiên bản đã quản lý trong build.

### 7.2. Dependency mediation: nearest definition và quản lý version

Trong Maven, việc giải quyết version conflict có quy tắc mediation dựa trên khoảng cách dependency trong cây; khi có những đường cùng độ sâu, thứ tự khai báo có thể ảnh hưởng lựa chọn. dependencyManagement có thể quản lý version dùng trong các dependency tương ứng, nhưng bản thân việc khai báo trong dependencyManagement **không** tự thêm dependency vào project.

Ví dụ:

~~~text
application
  ├─ A:1.0
  │   └─ common:1.1
  └─ B:2.0
      └─ common:2.5
~~~

Nếu thư viện A được build với common:1.1 nhưng runtime giải quyết về common:2.5, cần kiểm tra mức binary/behavioral compatibility giữa hai bản. Không phải version mới hơn luôn tương thích hoặc luôn phù hợp Java tối thiểu.

### 7.3. BOM và dependencyManagement

Một BOM (Bill of Materials) giúp đồng bộ phiên bản của một nhóm thư viện, đặc biệt framework có nhiều module phụ thuộc lẫn nhau.

Ví dụ cấu trúc Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>3.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Tọa độ trên là minh họa. BOM giúp quản lý tổ hợp version nhưng vẫn cần xác minh framework/BOM version đó hỗ trợ JDK mục tiêu và Java tối thiểu nào.

### 7.4. Maven scope và tác động runtime

| Scope | Điểm cần chú ý |
|---|---|
| compile (mặc định) | Có trong compile và nhiều classpath downstream; thường có mặt ở runtime. |
| runtime | Không cần cho compile source chính nhưng cần chạy ứng dụng. |
| provided | Được kỳ vọng do môi trường/container/JDK cung cấp ở runtime; cần kiểm chứng giả định. |
| test | Chỉ phục vụ test, có thể yêu cầu Java version riêng. |
| optional | Ảnh hưởng truyền dependency sang consumer, có thể cần khai báo trực tiếp khi sử dụng. |

Một API từng nằm trong JDK 8 nhưng đã bị loại bỏ trong JDK 11+ không nên tiếp tục được coi là provided bởi JDK mới. Cần phân biệt môi trường application server thực sự cung cấp API/implementation với JDK tiêu chuẩn không còn chứa module cũ.

## 8. Khi direct và transitive dependencies xung đột

### 8.1. Một version được chọn, nhiều thư viện cùng sử dụng

Ví dụ:

~~~text
Payment Service
  ├─ payment-client 4.x ──> jackson-core A
  ├─ audit-library 2.x ──> jackson-core B
  └─ framework BOM     ──> jackson-core C
~~~

Các phiên bản A/B/C có thể không tương đương. Build tool chọn một bản theo quy tắc resolution, nhưng một thư viện đã biên dịch với API của B có thể tham chiếu method không có trong C.

Các lỗi có thể xuất hiện:

- NoSuchMethodError khi method expected không tồn tại trong bản runtime.
- NoSuchFieldError khi field đã đổi/biến mất.
- IncompatibleClassChangeError nếu static/instance hoặc class/interface contract thay đổi.
- AbstractMethodError do interface/implementation không đồng bộ.
- ClassCastException khi có các kiểu không tương thích hoặc duplicate class qua classloader.
- NoClassDefFoundError nếu class bị thiếu hoặc không tải được.

Không phải lỗi nào cũng do JDK. Đổi JDK thường đi kèm nâng framework, dẫn đến resolved dependency khác trước; phải kiểm tra cả hai.

### 8.2. Không phải cứ ép version mới nhất là đúng

Version mới hơn có thể:

- Yêu cầu Java mới hơn mức ứng dụng hỗ trợ.
- Đổi namespace javax sang jakarta.
- Bỏ method cũ hoặc thay đổi API.
- Thay hành vi mặc định về serialization, HTTP hoặc TLS.
- Không còn hỗ trợ một framework/application server cũ.
- Chứa thay đổi về license hoặc security policy cần xem xét.

Do đó, “force latest” không phải giải pháp chung cho dependency conflict. Hãy chọn **tổ hợp được hỗ trợ**, dựa trên matrix của framework, tài liệu phát hành và test thực tế.

### 8.3. Exclusion và override có mục đích

Khi một dependency bắc cầu kéo version không phù hợp, một hướng có thể là:

1. Tìm đường kéo vào bằng dependencyInsight hoặc dependency:tree.
2. Kiểm tra version yêu cầu của dependency cha.
3. Xem framework BOM hoặc constraints chính thức.
4. Nếu có bản compatible, điều chỉnh trực tiếp dependency version hoặc alignment policy.
5. Nếu phải exclude, khai báo dependency thay thế rõ ràng và kiểm thử runtime.
6. Ghi lý do, rủi ro và điều kiện gỡ override.

Exclusion chỉ thay đồ thị phụ thuộc; nó không tự tạo tính tương thích giữa phiên bản thư viện cha và bản được chọn thay thế. Nếu thư viện cha gọi một method đã bị xóa, loại JAR và kéo bản khác vẫn có thể gây linkage error.

## 9. Đặc biệt chú ý đến framework, BOM và Jakarta migration

Framework lớn thường có compatibility matrix gắn với JDK và nhiều thành phần:

- Spring/Spring Boot và các starter.
- Jakarta EE application server.
- Hibernate/JPA.
- Netty, HTTP stack, Servlet container.
- gRPC và protobuf.
- Logging framework, bytecode instrumentation.
- Database drivers, message brokers, cloud SDK.

Không nên nâng một module trong họ framework quá xa khỏi BOM rồi mong mọi thứ vẫn chạy. Ví dụ một JPA provider mới có thể yêu cầu Jakarta Persistence, trong khi ứng dụng cũ vẫn dùng javax.persistence. Một JSON binding library mới có thể đổi cách xử lý reflection hoặc cần Java release cao hơn.

### 9.1. Tách JDK migration và framework migration khi có thể

Một kế hoạch nhiều bước:

~~~text
Ứng dụng trên JDK cũ
        │
        ▼
Nâng dependency trong dòng còn tương thích với JDK cũ
        │
        ▼
Xác nhận runtime trên JDK mục tiêu (giữ API/framework nếu khả thi)
        │
        ▼
Nâng framework + BOM + code generation cùng thế hệ
        │
        ▼
Chuyển đổi javax/jakarta hoặc API breaking changes nếu cần
        │
        ▼
Kiểm thử và triển khai artifact mới
~~~

Không phải mọi tổ hợp đều khả thi; framework mục tiêu có thể yêu cầu JDK mới, buộc thực hiện một số bước đồng thời. Khi đó, phải ghi các ràng buộc để tránh nhầm nguyên nhân khi lỗi phát sinh.

### 9.2. Không tự động thay mọi javax bằng jakarta

Jakarta EE namespace migration áp dụng cho nhiều API Java EE, nhưng một số javax.* vẫn thuộc Java SE. Ngoài source import, các annotation, code generated, provider, serializers và runtime framework cũng phải thuộc cùng thế hệ.

Một dependency trực tiếp có thể chuyển sang jakarta, trong khi dependency bắc cầu vẫn được compile với javax. Khi đó, cùng một ý tưởng API nhưng binary name khác nhau; không thể xem chúng là một class.

Hãy tìm chính xác package được từng artifact cung cấp và sử dụng thay vì chỉ nhìn groupId hoặc tên thư viện.

## 10. Build plugin, annotation processor và code generation cũng có mức JDK

Đồ thị dependency không chỉ gồm runtime libraries. Pipeline build có nhiều plugin/tool:

- Compiler plugin và annotation processor (ví dụ code generator).
- Build plugins, static analysis, code coverage.
- Test runner, mocking framework, testcontainers.
- Bytecode instrumentation, agent.
- JAXB/JAX-WS/Protobuf/OpenAPI codegen.
- Packaging, shading và native-image tooling khi được sử dụng.

Chúng có thể chạy ở JDK khác với target bytecode của ứng dụng. Một build plugin yêu cầu Java 21 không bắt buộc thư viện xuất bản phải chỉ chạy trên Java 21, miễn là compiler release, packaging và runtime dependency thực tế vẫn đáp ứng Java tối thiểu. Ngược lại, plugin tạo class cho Java mới hơn có thể làm artifact cuối không còn chạy trên Java cũ.

### 10.1. Các câu hỏi cần kiểm tra

1. JDK nào đang chạy Gradle/Maven daemon/process?
2. Compiler toolchain nào thực hiện JavaCompile?
3. Annotation processor có tương thích compiler/JDK mục tiêu không?
4. Generated source có sử dụng API mới hơn release mục tiêu không?
5. Test launcher và test dependencies có tương thích JDK được test không?
6. Jacoco/coverage agent, Mockito/Byte Buddy hoặc các agent khác có nhận dạng class-file version mục tiêu không?
7. Plugin có tương thích Gradle/Maven version và JDK chạy build tool không?

Build lỗi do plugin không nhận Java class-file version khác bản thân ứng dụng lỗi runtime. Cần tách các đường xử lý, tránh nâng toàn bộ production runtime chỉ để chữa một công cụ build cũ.

## 11. Multi-release JAR, shading và service discovery

### 11.1. Multi-release JAR

Một multi-release JAR có thể chứa code base tương thích Java cũ và các class specialized cho runtime mới dưới META-INF/versions.

Ví dụ:

~~~text
library.jar
  com/example/Feature.class
  META-INF/versions/17/com/example/Feature.class
  META-INF/versions/21/com/example/Feature.class
~~~

Trên Java 17, JVM chọn phiên bản phù hợp theo cơ chế multi-release nếu manifest/đóng gói tuân thủ yêu cầu. Trên runtime cũ hơn, base class phải tương thích để JAR dùng được.

Cần xem:

- Manifest có khai báo Multi-Release theo quy tắc áp dụng không?
- Class-file version trong từng thư mục versioned có phù hợp Java tương ứng không?
- Tool phân tích JAR đang xét base hay một release cụ thể?
- Có class bị thiếu ở base version khiến runtime tối thiểu không chạy được không?

Không thể kết luận cả JAR yêu cầu Java 21 chỉ vì nó chứa một class trong META-INF/versions/21. Ngược lại, không thể kết luận JAR hỗ trợ Java 8 chỉ vì một class base có major version 52.

### 11.2. Shaded/Fat JAR

Trong executable/fat JAR, dependency có thể được đóng gói hoặc relocate vào cùng artifact. Điều này tạo khác biệt:

- Metadata Maven/Gradle không còn chỉ rõ phiên bản của mọi class đã gộp.
- Class version trong shaded dependency có thể cao hơn phần code ứng dụng.
- Relocation có thể làm thay đổi reflection, serialization và service-provider discovery.
- Tệp META-INF/services có thể cần merge đúng để ServiceLoader tìm provider.
- Duplicate resources hoặc class có thể bị một bản ghi đè âm thầm.

Vì vậy, kiểm tra tính tương thích phải áp dụng trên artifact cuối cùng, không chỉ các JAR trước khi đóng gói.

### 11.3. JPMS, classpath và module path

Trên module path, JDK áp dụng ranh giới module và resolution khác classpath. Một dependency có thể:

- Có module-info.java với requires không được đáp ứng.
- Có automatic module name không như nhóm dự kiến.
- Gây split package khi nhiều module cung cấp cùng package.
- Cần opens cho framework reflection.
- Không khai báo uses/provides cần thiết cho ServiceLoader trong module scenario.

Nếu sản phẩm thực sự chạy trên classpath, không cần tự chuyển toàn bộ lên JPMS khi nâng JDK, nhưng cũng không nên dùng kết quả test classpath để tuyên bố module-path deployment tương thích.

## 12. Native libraries, JNI và javaagent

Một số dependency gắn với thư viện native hoặc runtime agent. Ví dụ:

- JDBC driver kèm native authentication.
- Cryptographic provider, HSM hoặc PKCS#11.
- Compression/media processing library.
- JNA/JNI bridge.
- Monitoring/tracing/profiling agent.
- Bytecode weaving/instrumentation.

Các thành phần này có thêm ràng buộc về:

| Ràng buộc | Tình huống cần kiểm tra |
|---|---|
| OS | Linux/Windows/macOS có cùng binary native không? |
| CPU architecture | x86_64, aarch64 hoặc nền tảng khác có package được hỗ trợ không? |
| libc/platform | Container Alpine/musl và glibc có khác nhau không? |
| JVM/JVMTI | Agent có hỗ trợ Java release, class-file version và runtime startup options không? |
| Security provider | Native crypto provider có hoạt động trên JDK mới không? |
| Container | Native files có được đóng gói và có quyền load không? |

Một JAR có thể được compile cho Java 8 nhưng native library bên trong không chạy trên architecture đích. Do đó, binary compatibility Java không chứng minh tương thích toàn bộ môi trường.

Nếu lỗi chỉ xảy ra ở production container hoặc agent-enabled test, nên ghi OS, architecture, base image digest, JDK distribution và danh sách agent options để tái hiện.

## 13. Công cụ hỗ trợ phân tích dependency compatibility

### 13.1. jdeps

jdeps có thể phân tích dependency giữa các class/JAR:

~~~bash
jdeps --jdk-internals dependency.jar
~~~

Với app artifact và classpath cần thiết:

~~~bash
jdeps --missing-deps --class-path "libs/*" app.jar
~~~

Với multi-release JAR có thể chọn Java release phù hợp khi phiên bản công cụ hỗ trợ:

~~~bash
jdeps --multi-release 17 --class-path "libs/*" app.jar
~~~

Đây là phân tích tĩnh. Reflection, class loading từ tên chuỗi, service provider và plugin động có thể không được quan sát đầy đủ. Cần kết hợp test runtime.

### 13.2. jdeprscan

jdeprscan giúp phát hiện bytecode tham chiếu API JDK deprecated hoặc forRemoval theo release được chọn:

~~~bash
jdeprscan --release 17 dependency.jar
jdeprscan --release 17 --for-removal dependency.jar
~~~

Quét API deprecated không có nghĩa là quét toàn bộ compatibility; một thư viện có thể không dùng API deprecated nhưng vẫn yêu cầu JDK cao hơn hoặc gặp lỗi runtime khác.

Nếu dùng JDK khác, phải xác nhận release được jdeprscan đó hỗ trợ. Khi scan một JAR ứng dụng, dependency dùng để phân giải class không nhất thiết tự động là mọi artifact được quét; nếu cần đánh giá dependency riêng, hãy quét trực tiếp artifact đó.

### 13.3. javap và jar

~~~bash
javap -verbose -classpath dependency.jar com.example.EntryPoint
jar tf dependency.jar
~~~

javap giúp xem major version, signature và một số metadata. jar tf giúp kiểm tra layout và class/resources. Với hàng trăm dependency, nên kết hợp công cụ build/CI tự động để tạo báo cáo; không dựa vào kiểm tra thủ công một class đại diện.

### 13.4. Công cụ kiểm tra binary API

Với thư viện phát hành public API, các công cụ so sánh API như japicmp hoặc Revapi có thể phát hiện những thay đổi class, method, modifier và hierarchy giữa hai phiên bản.

Những công cụ này trả lời câu hỏi “API giữa hai artifact thay đổi thế nào”, không trực tiếp trả lời “toàn bộ ứng dụng chạy được trên JDK X hay không”. Vẫn phải thực thi client binary cũ với thư viện mới và kiểm tra runtime compatibility.

### 13.5. Security/SBOM scanning

Dependency management còn cần rà soát CVE, license và vòng đời hỗ trợ. SBOM giúp xác định thành phần và version của sản phẩm, trong khi vulnerability scanner phát hiện những cảnh báo cần đánh giá.

Không nên coi việc cập nhật bản vá bảo mật như một phép nâng version vô hại; bản vá/major upgrade cũng có thể thay mức Java tối thiểu hoặc API. Cần kết hợp chính sách security với compatibility matrix.

## 14. Ma trận tương thích dependency

Mỗi dependency quan trọng nên có một bản ghi:

| Trường | Dữ liệu cần ghi |
|---|---|
| Artifact | groupId:artifactId:version hoặc identifier tương đương. |
| Nguồn | Direct hay transitive; chuỗi path nào đã kéo vào. |
| Scope/configuration | Compile, runtime, test, plugin, annotation processor. |
| Resolved version | Version thực sự được build tool chọn. |
| Minimum Java | Yêu cầu Java tối thiểu theo nguồn tin đáng tin cậy và kiểm chứng. |
| Target bytecode | Class-file major version hoặc thông tin multi-release. |
| JDK target | Các JDK mà sản phẩm đang migration/định hỗ trợ. |
| Framework constraints | BOM/framework/container yêu cầu version nào. |
| Risk | API removed, internal JDK, reflection, native, namespace, security. |
| Evidence | Release notes, dependency report, test run, artifact checksum. |
| Decision | Giữ, nâng, thay, exclude có kiểm soát, cô lập hoặc loại bỏ. |
| Owner/status | Người phụ trách và tình trạng xử lý. |

Ví dụ dữ liệu minh họa, **không phải compatibility claim thực tế của các thư viện cụ thể**:

| Component | Quan hệ | Resolved | JDK yêu cầu (giả định) | Quyết định |
|---|---|---|---|---|
| web-framework | Direct | 3.x | Java 17+ | Giữ nếu Java target là 17/21 và matrix được xác minh. |
| serialization-core | Transitive qua web-framework | 2.x | Java 8+ | Kiểm thử serializer và reflection trên JDK 17/21. |
| telemetry-agent | Runtime/agent | 1.x | Java 11–17 (giả định) | Cần nâng agent nếu production dùng Java 21. |
| legacy-xml-api | Transitive qua plugin | 2.x | Legacy javax API | Xác định scope/build-time hay runtime; chọn thế hệ phù hợp. |

Không dùng các giá trị giả định trên để quyết định version thật. Chính sách thực tế phải dựa trên artifact và tài liệu phát hành cụ thể.

### 14.1. Xác định mức Java tối thiểu của cả sản phẩm

Giả sử ứng dụng đặt --release 17, nhưng runtimeClasspath chứa một JAR yêu cầu Java 21. Khi deploy trên Java 17, khả năng chạy không còn được bảo đảm.

Cần quyết định một trong những hướng:

1. Chọn version dependency còn hỗ trợ Java 17 và có maintenance phù hợp.
2. Thay dependency bằng implementation khác tương thích Java 17.
3. Cô lập chức năng yêu cầu Java 21 sang một service/artifact riêng nếu kiến trúc cho phép.
4. Nâng Java tối thiểu của sản phẩm lên 21 kèm chính sách versioning và thông báo breaking change.

Không nên chỉ đổi compiler release 17 sang 21 để “phù hợp” rồi âm thầm phá vỡ hợp đồng với consumer vẫn đang dùng Java 17.

## 15. Kiểm thử trên JDK mục tiêu

### 15.1. Tạo baseline có thể tái lập

Trước khi thay dependency:

- Ghi commit, build tool wrapper và JDK đầy đủ.
- Lưu resolved dependency graph của compile/runtime/test.
- Ghi platform/BOM, constraints, exclusions và custom rules.
- Ghi artifact checksum, container image digest và cấu hình runtime.
- Xác định các integration quan trọng được framework/plugin cung cấp.

Nếu việc nâng JDK đồng thời đổi cả framework và hàng loạt dependency, hãy ghi rõ các biến đã đổi để phân tích regression.

### 15.2. Ma trận build/test đề xuất

| Hạng mục | JDK hiện tại | JDK mục tiêu | Ý nghĩa |
|---|---|---|---|
| Build source và generated code | Baseline | Bắt buộc nếu được hỗ trợ | Phát hiện lỗi compiler/plugin. |
| Unit tests | Baseline | Bắt buộc | Kiểm tra logic và phụ thuộc test. |
| Integration tests | Baseline | Bắt buộc | Kiểm tra framework, DB, HTTP, messaging, serialization. |
| Runtime startup | Baseline | Bắt buộc | Phát hiện class loading/provider/module errors. |
| Deployment container | Baseline nếu có | Bắt buộc | Kiểm tra OS, native agent, image và runtime packaging. |
| Minimum-supported Java | Nếu khác baseline | Bắt buộc nếu sản phẩm còn cam kết | Xác nhận mức tối thiểu thật. |
| Binary consumer fixture | Khi có API công bố | Khi có API công bố | Chạy client cũ với library mới, không biên dịch lại. |

Nếu library công bố hỗ trợ Java 17 dù build bằng JDK 21, cần có test chạy artifact và runtime dependencies thật trên Java 17. Chạy mọi test trên JDK 21 chỉ chứng minh một phần tương thích với JDK 21.

### 15.3. Các luồng tích hợp quan trọng

Với dependency cấp framework và hạ tầng, ưu tiên test:

- JSON/XML serialization: field, annotation, timezone, null handling.
- HTTP/TLS: certificate chain, hostname, HTTP protocol, proxy và connection pooling.
- JDBC/ORM: connection authentication, query, transaction, metadata, schema.
- Message broker: producer/consumer, serializer, retry và ACL/TLS.
- Security: token signature, authorization rules, OAuth/OIDC callbacks.
- Logging/tracing/metrics: agent load, context propagation và startup.
- Caching: serialization compatibility và invalidation.
- Scheduler/batch: classloader, cron, timezone và long-lived resource.
- Native/agent path: đúng OS/CPU architecture và JDK target.

Thành công của một test đơn lẻ không chứng minh toàn bộ dependency tương thích; phạm vi test nên phản ánh các đường chức năng quan trọng của sản phẩm.

## 16. Ví dụ sự cố: transitive JAR yêu cầu JDK cao hơn

Giả sử ứng dụng công bố minimum Java 17 và vẫn compile với --release 17. Sau khi nâng một HTTP client trực tiếp, runtimeClasspath kéo vào một dependency bắc cầu mới được compile cho Java 21.

Trên môi trường CI chạy Java 21, build và test đều thành công. Nhưng khi triển khai trên Java 17:

~~~text
UnsupportedClassVersionError: ... class file version 65.0;
this runtime only recognizes up to version 61.0
~~~

Quy trình điều tra:

1. Xác định chính xác class báo lỗi.
2. Tìm JAR chứa class đó trong runtime deployment.
3. Kiểm tra major version bằng javap.
4. Dùng dependencyInsight hoặc dependency:tree để truy ra dependency cha.
5. Kiểm tra release notes của cả direct dependency và transitive artifact.
6. Chọn phiên bản/tổ hợp tương thích Java 17 hoặc ra quyết định nâng minimum Java.
7. Chạy lại test bằng Java 17 trên artifact đã giải quyết.

Sự cố này cho thấy **build JDK không phải minimum runtime JDK**. Nếu CI chỉ có môi trường Java 21, pipeline dễ bỏ sót lỗi.

## 17. Ví dụ sự cố: NoSuchMethodError sau khi nâng framework

Giả sử một module A được biên dịch với common-library bản 4.x, còn module B kéo common-library bản 3.x qua dependency bắc cầu. Sau conflict resolution, runtime dùng bản 3.x không có method mà A gọi.

Khi thực thi đường code liên quan:

~~~text
java.lang.NoSuchMethodError: 'Result CommonApi.execute(Request)'
~~~

Điều tra:

1. Xác nhận class CommonApi runtime được nạp từ JAR nào, không chỉ version trong build file.
2. So sánh method descriptor trong JAR runtime với method mà binary caller tham chiếu.
3. Xem resolved runtimeClasspath và đường phụ thuộc gây chọn bản đó.
4. Đối chiếu version alignment/BOM tương thích với A và B.
5. Chỉnh version hoặc nâng A/B thành tổ hợp tương thích.
6. Chạy integration test trên deployment artifact thật, đặc biệt các luồng liên quan method.

Không nên chỉ xóa cache hoặc ép version mới nhất mà chưa biết compatibility matrix. Nếu classloader của app server/plugin nạp một bản common-library khác, phải xử lý ở deployment/classloader boundary.

## 18. Ví dụ sự cố: JDK encapsulation và reflection

Một framework cũ dùng reflection để truy cập private member của JDK. Sau khi chuyển JDK, ứng dụng gặp:

~~~text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible
~~~

Các bước:

1. Đọc stack trace và xác định dependency sở hữu lời gọi reflection.
2. Kiểm tra version framework/bytecode utility có hỗ trợ JDK mục tiêu hay không.
3. Dùng jdeps và ghi nhận những internal APIs trực tiếp nếu có.
4. Ưu tiên nâng sang version framework không cần truy cập bị hạn chế.
5. Nếu có workaround --add-opens tạm thời, giới hạn phạm vi và ghi thời hạn loại bỏ.
6. Test khởi động, serialization, proxy, ORM và code generation trên JDK mục tiêu.

Không coi mọi InaccessibleObjectException là lỗi bytecode target. Chúng thuộc nhóm giới hạn truy cập/module behavior; đổi --release của compiler không tự giải quyết.

## 19. Kiểm soát dependency drift trong CI và môi trường triển khai

### 19.1. Vì sao graph có thể tự thay đổi?

Graph được phân giải có thể biến động do:

- Dùng dynamic version như 1.+ hoặc version range rộng.
- Snapshot/changing modules cập nhật theo thời gian.
- Thay BOM/parent POM hoặc plugin.
- Repository mirror phản hồi metadata khác.
- Cache hoặc dependency lock không đồng bộ.
- Module/profile/feature flag thay đổi scope dependency.
- Container đóng gói từ artifact khác với bản đã test.

Đối với migration, ưu tiên pin/lock version theo cơ chế phù hợp với build tool. Lưu resolved graph, checksum và build identifier để có thể truy lại một kết quả.

### 19.2. Dependency locking và verification

Gradle hỗ trợ cơ chế dependency locking và dependency verification tùy cấu hình. Maven thường dựa trên version cố định, dependency management, repository chính sách và công cụ bổ sung để tạo inventory/xác nhận checksum.

Mục đích:

- Tránh một bản dependency bắc cầu thay đổi âm thầm giữa các lần build.
- Giảm rủi ro supply-chain hoặc artifact metadata không khớp.
- Giữ CI và local resolve cùng bộ version.
- Có bằng chứng về dependency graph đi kèm release.

Không nên dùng checksum hay lockfile như phép thay thế test JDK; artifact được khóa phiên bản vẫn có thể không tương thích runtime mục tiêu.

### 19.3. SBOM và provenance

Đối với sản phẩm phân phối, SBOM có thể chứa danh sách thành phần và version để nhóm bảo mật/khách hàng kiểm tra. Cần bảo đảm SBOM đại diện cho **artifact thực sự phát hành**, không chỉ toàn bộ dependency trong repository, đồng thời lưu build provenance phù hợp.

Khi sử dụng fat JAR, shading hoặc application server cung cấp dependency, cần ghi nhận rõ các thành phần do ai cung cấp và phạm vi có trong SBOM.

## 20. Chiến lược thay hoặc nâng dependency an toàn

### 20.1. Ưu tiên nâng theo cụm tương thích

Các component liên kết chặt như framework modules, ORM, HTTP stack hoặc logging nên được nâng theo BOM/cặp version được hỗ trợ. Nâng một module đơn lẻ có thể tạo tổ hợp chưa được kiểm thử.

Ví dụ quy trình:

~~~text
Chốt baseline dependency graph
           │
           ▼
Xác định JDK target và minimum Java contract
           │
           ▼
Phân nhóm dependency theo framework/BOM và owner
           │
           ▼
Chọn phiên bản được hỗ trợ + security-patched
           │
           ▼
Build + static analysis + runtime matrix tests
           │
           ▼
Kiểm tra artifact, lock versions, release notes
           │
           ▼
Deploy từng giai đoạn và theo dõi regression
~~~

### 20.2. Khi cần loại bỏ dependency

Một dependency có thể không còn được duy trì và chặn nâng JDK. Lựa chọn:

- Thay bằng API JDK hiện đại nếu phù hợp nghiệp vụ và contract.
- Dùng thư viện khác còn được hỗ trợ.
- Viết adapter để cô lập API cũ trong thời gian consumer di chuyển.
- Tách thành service độc lập nếu khác biệt runtime không thể giải quyết trong một JVM.
- Giữ nhánh legacy có thời hạn khi yêu cầu hỗ trợ chưa thể chấm dứt.

Tránh tự fork dependency lâu dài mà không có kế hoạch patch bảo mật, license, test và owner. Fork có thể giải quyết một lỗi trước mắt nhưng chuyển toàn bộ trách nhiệm bảo trì sang nhóm của bạn.

### 20.3. Mức độ ưu tiên xử lý

| Mức | Tình huống | Hành động |
|---|---|---|
| Blocker | Runtime bắt buộc class-file version cao hơn mức Java cam kết. | Chặn release hoặc đổi dependency/minimum Java theo chính sách. |
| Blocker | Lỗi link/runtime tại luồng nghiệp vụ chính, hoặc security provider không khởi động. | Điều tra và sửa trước deploy. |
| High | Dependency không hỗ trợ JDK mục tiêu, dựa vào API nội bộ và chỉ chạy với workaround rộng. | Nâng/thay và giảm workaround. |
| High | CVE nghiêm trọng trong dependency runtime với đường tấn công liên quan. | Phối hợp security response và chọn bản vá tương thích. |
| Medium | Cảnh báo deprecated JDK API không forRemoval, có giải pháp thay thế. | Theo dõi và lên kế hoạch. |
| Investigate | Metadata thiếu hoặc chưa có test cho một dependency ít dùng. | Xác minh phạm vi, tạo test hoặc ghi ngoại lệ có owner. |

Đây là cách phân nhóm minh họa; mức nghiêm trọng cụ thể phải dựa trên tác động nghiệp vụ, phạm vi khai thác, mức hỗ trợ và chính sách tổ chức.

## 21. Mẫu báo cáo kiểm kê dependency cho migration

Một báo cáo ngắn có thể gồm:

~~~text
Module/artifact:
Commit/build:
Target JDK:
Minimum supported Java runtime:
Build JDK/compiler toolchain:
Dependency graph identifier:
Artifact checksum:

Direct dependencies:
  - name/version/scope

Transitive dependencies:
  - resolved name/version
  - introduced by ...

Compatibility findings:
  - class-file version mismatch
  - removed/deprecated Java APIs
  - JDK internal/reflection/module issues
  - framework/BOM mismatch
  - native or agent risk
  - security/support risk

Decisions:
  - keep / upgrade / align / exclude / replace / isolate
  - owner / due date / evidence

Validation:
  - build JDK
  - minimum runtime JDK tests
  - target runtime JDK tests
  - integration and binary consumer tests
  - deployment artifact verification

Open blockers and accepted exceptions:
Release readiness:
~~~

Không điền “compatible” chỉ vì không thấy compile error. Nếu chưa kiểm tra một dependency, ghi “chưa xác minh” hoặc nêu rõ phạm vi test còn thiếu.

## 22. Những nhận định sai thường gặp

| Nhận định | Vì sao không đúng | Cách tiếp cận |
|---|---|---|
| “Chỉ cần các direct dependencies tương thích.” | Transitive JAR cũng được nạp ở runtime và có thể yêu cầu Java mới hơn. | Kiểm tra resolved runtime graph toàn bộ. |
| “Build bằng JDK 21 là app yêu cầu Java 21.” | Compiler có thể tạo artifact --release 17. | Phân biệt build JDK, target và runtime. |
| “Compile --release 17 thì mọi dependency đều chạy Java 17.” | --release không hạ bytecode hay API của JAR bên ngoài. | Kiểm tra dependency và test runtime Java 17. |
| “Version mới nhất luôn tốt nhất.” | Có thể tăng minimum Java hoặc đổi API/framework. | Chọn bộ phiên bản được hỗ trợ và test. |
| “Thêm API JAR là runtime chạy.” | Một số công nghệ cần implementation/provider riêng. | Xác nhận runtime provider và packaging. |
| “dependencyManagement/BOM tự thêm mọi dependency.” | Chúng chủ yếu quản lý phiên bản, không tự thêm module cho mọi trường hợp. | Xem resolved graph và khai báo dependency cần thiết. |
| “Exclusion chữa được mọi conflict.” | Loại JAR có thể làm thiếu class hoặc phá binary API. | Dùng exclusion có bằng chứng và test integration. |
| “Cùng package nghĩa là cùng thế hệ thư viện.” | javax/jakarta và artifact version có thể khác binary name/semantics. | Kiểm tra class thực tế và framework matrix. |
| “Một class trong JAR có bytecode 52 thì JAR hỗ trợ Java 8.” | Các class khác hoặc variant có thể yêu cầu mức cao hơn. | Kiểm tra toàn artifact và runtime. |
| “jdeps không báo lỗi tức là app tương thích.” | Reflection, native, plugin động và behavioral changes có thể lọt. | Kết hợp static analysis và runtime tests. |
| “Test JDK mới nhất là đủ.” | Product có thể còn cam kết chạy trên JDK tối thiểu cũ. | CI matrix bao gồm minimum-supported Java. |
| “Không thấy lỗi local thì production cũng ổn.” | Runtime image, classloader, TLS/native khác. | Test artifact và topology triển khai thật. |
| “Phiên bản JAR trong POM luôn là bản nạp.” | Mediation, shading, profile, classloader có thể đổi bản runtime. | Đối chiếu resolved graph và class source. |
| “Có CVE thì cứ force dependency lên major mới ngay.” | Có thể gây breaking JDK/API changes. | Đánh giá bản vá khả thi, exposure và compatibility. |

## 23. Quy trình xử lý từng dependency rủi ro

Khi có một thư viện không rõ tương thích JDK:

1. **Xác định artifact thật.** Ghi groupId, artifactId, version, checksum và nguồn.
2. **Xác định đường đi.** Dùng dependencyInsight hoặc dependency:tree để biết direct/transitive và vì sao version được chọn.
3. **Xác định phạm vi.** Runtime, compile, test, plugin, optional, provided hay native/agent?
4. **Thu thập yêu cầu Java.** Xem release notes, metadata, class-file versions và thông tin framework/BOM.
5. **Phân tích API.** Kiểm tra JDK internals, removed/deprecated API, javax/jakarta, JPMS và reflection.
6. **Đánh giá phương án.** Giữ, nâng, thay, override có kiểm soát, tách module hoặc nâng minimum Java.
7. **Thực hiện thay đổi trong graph.** Giữ version nhất quán và không mở rộng override ngoài nhu cầu.
8. **Build lại artifact.** Dùng wrapper/toolchain được xác định, kiểm tra packaging thật.
9. **Chạy matrix.** JDK tối thiểu, JDK mục tiêu và các integration quan trọng.
10. **Ghi kết luận.** Lưu bằng chứng test, decision, owner, security status và các giới hạn còn lại.

Nếu dependency chỉ phục vụ test hoặc build-time và không nằm trong artifact triển khai, mức Java của nó có thể khác mức runtime tối thiểu sản phẩm công bố. Tuy nhiên, nó vẫn phải tương thích với JDK dùng để chạy test/build để pipeline hoạt động tin cậy.

## 24. Kết luận

Tương thích JDK của dependency cần được đánh giá trên **đồ thị phụ thuộc đã giải quyết và artifact thực tế**, gồm cả thư viện trực tiếp lẫn bắc cầu. Một version dependency có thể làm tăng minimum Java, thay binary API, kéo provider không tương thích, sử dụng JDK internal API hoặc gây xung đột trong module/classloader dù mã ứng dụng vẫn biên dịch được.

Để chuyển đổi Java an toàn, cần kiểm kê compile/runtime/test/build dependency, phân biệt build JDK với runtime Java tối thiểu, kiểm tra class-file version và API, đối chiếu framework/BOM, tìm đúng nguồn transitive conflicts, và kiểm thử trên JDK mục tiêu lẫn JDK tối thiểu đã cam kết. Lock resolved versions, lưu compatibility evidence và triển khai từng giai đoạn giúp giảm dependency drift và tránh những lỗi chỉ xuất hiện ở production.

**Đích đến không chỉ là làm cho dependency tree hết cảnh báo, mà là có một bộ dependency được hỗ trợ, kiểm chứng được và tái lập được trên những phiên bản Java mà sản phẩm thực sự cam kết sử dụng.**
