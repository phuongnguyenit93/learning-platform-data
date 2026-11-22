# Dọn dependency, cờ mở quyền và mã trung gian sau giai đoạn chuyển tiếp

Nâng ứng dụng Java từ JDK cũ lên JDK mới thường cần những giải pháp tạm thời: thêm API JAR để thay thành phần từng đi kèm JDK, giữ thư viện đời cũ, mở package bằng --add-opens, bổ sung --add-exports, viết adapter cho hai schema hoặc dùng feature flag để chạy song song implementation. Các biện pháp đó giúp chuyển đổi theo giai đoạn, nhưng có thể trở thành **nợ tương thích** nếu để lại sau khi đã không còn cần thiết.

Một dịch vụ chạy ổn định trên Java 21 vẫn có thể mang theo Java 8 backport, thư viện không được hỗ trợ, một loạt cờ mở module quá rộng và hai đường xử lý không còn được kiểm thử như nhau. Điều này làm tăng rủi ro bảo mật, xung đột dependency, khó tái lập lỗi và gây trở ngại cho đợt nâng JDK tiếp theo.

Bài học thuộc **Java Advance Compatibility Migration**, chương **Phát hành và vận hành**, tập trung vào **dọn dependency, cờ mở quyền và mã trung gian sau giai đoạn chuyển tiếp**. Mục tiêu là loại bỏ thành phần không cần thiết **dựa trên bằng chứng**, nhưng vẫn bảo vệ API/SPI, dữ liệu lịch sử, consumer contract và khả năng rollback trong thời hạn cam kết.

## 1. Cleanup khác với việc chỉ chạy thành công trên JDK mới

Một dự án có thể đạt trạng thái:

~~~text
Build JDK: Java 21
Production JVM: Java 21
Unit tests: PASS
Integration tests: PASS

Nhưng vẫn còn:
  old JAXB provider
  old bytecode manipulation tool
  --add-opens=java.base/java.lang=ALL-UNNAMED
  --add-exports=java.base/sun.nio.ch=ALL-UNNAMED
  LegacySerializer.java
  ReflectionFallback.java
  USE_NEW_SERIALIZER feature flag
  outdated GC logging script
~~~

Chạy được trên JDK mới chỉ xác nhận một phần compatibility. Cleanup sau migration cần trả lời thêm:

- Thành phần nào còn thực sự được gọi?
- Thành phần nào chỉ tồn tại cho lần chuyển đổi?
- Có runtime path nào dùng reflection hoặc ServiceLoader?
- Cờ mở quyền đang phục vụ thư viện nào?
- Mã legacy có còn cần đọc dữ liệu cũ không?
- Public consumer có còn phụ thuộc vào binary interface cũ không?
- Thời hạn rollback đã đóng chưa?
- CI, container và runbook còn cấu hình cũ không?

**Không nên xóa mọi thứ có tên Legacy mà chưa biết hợp đồng, cũng không nên giữ mọi thứ chỉ vì sợ phá production.**

### 1.1. Lợi ích của cleanup có thể quan sát

| Khía cạnh | Trước cleanup | Sau cleanup mong muốn |
|---|---|---|
| Dependency graph | Thư viện đời cũ và mới chồng chéo | Chỉ artifact cần thiết và được hỗ trợ |
| Module access | Cờ mở package rộng | Quyền tối thiểu có lý do |
| Source code | Hai hoặc nhiều đường xử lý | Implementation chủ đạo rõ ràng |
| Build | Cấu hình tạm và override version | Cấu hình xác định và có thể tái lập |
| Security | Thư viện có CVE/permission dư | Giảm bề mặt rủi ro |
| Release | Rollback không rõ điều kiện | Versioned artifact và cửa sổ rollback |
| Operations | Flags rải rác | Effective runtime config được quản lý |
| Observability | Parsers và alerts cũ | Giám sát tương thích với JDK mới |

Cleanup không có nghĩa tối thiểu hóa số dòng code bằng mọi giá. Một compatibility reader vẫn cần nếu dữ liệu lịch sử phải được hỗ trợ nhiều năm.

## 2. Phân loại trước khi xóa

Mỗi thành phần nên được đánh dấu:

1. **Temporary workaround:** thêm để vượt blocker có điều kiện gỡ cụ thể.
2. **Required runtime dependency:** dùng qua import, reflection, provider hoặc native loading.
3. **Public compatibility contract:** phục vụ consumers/plugins vẫn được hỗ trợ.
4. **Historical-data compatibility:** dùng để đọc schema và file cũ.
5. **Permanent architectural adapter:** ranh giới có chủ đích, không phải code thừa.
6. **Dead code/dependency:** đã xác định không còn sử dụng hoặc cam kết.
7. **Security exception:** quyền JVM hoặc policy nới lỏng được phê duyệt tạm.

### 2.1. Ví dụ giữ adapter hợp lý

Một Java library cam kết chạy trên Java 17 và 21. Adapter chỉ chọn public API khả dụng theo runtime có thể vẫn cần, dù ứng dụng nội bộ đã chạy Java 21.

### 2.2. Ví dụ workaround có thể gỡ

Một mock library cũ cần --add-opens tới java.lang. Sau khi nâng library lên version hỗ trợ JDK đích, không còn lý do mở package nếu các đường test/runtime đều chạy ổn mà không có cờ.

## 3. Vòng đời của một workaround có trách nhiệm

~~~text
Migration blocker
        |
        v
Introduce temporary workaround
        |
        v
Record reason, scope, owner, removal condition
        |
        v
Upgrade framework/dependency or migrate consumer
        |
        v
Evidence workaround is no longer used
        |
        v
Remove in controlled branch
        |
        v
Build + contract + integration + runtime tests
        |
        +-- failure --> investigate, retain with owner
        |
        v
Canary and operational verification
        |
        v
Close migration debt record
~~~

Nên có một registry hoặc issue riêng cho mỗi workaround.

| ID | Loại | Phạm vi | Lý do | Điều kiện gỡ |
|---|---|---|---|---|
| MIG-101 | --add-opens | Test JVM | Mock framework đời cũ | Nâng tool và test không cần cờ |
| MIG-102 | Legacy JAXB | Batch | Đọc tài liệu XML cũ | Đã chuyển reader hoặc hết retention |
| MIG-103 | Serializer switch | API service | Rollout V1/V2 | Consumer chuyển và rollback window đóng |
| MIG-104 | Reflection fallback | App runtime | Dùng JDK internal API | Có public replacement |
| MIG-105 | Native agent | Production JVM | Agent chưa hỗ trợ JDK mới | Nâng bản vendor-supported |

Nếu chưa có ngày gỡ, vẫn phải có owner và review date.

## 4. Dependency có thể ẩn ở nhiều vị trí

Một dependency không chỉ là dòng import Java. Nó có thể nằm ở:

- Maven POM, parent POM, BOM, profiles.
- Gradle configurations, version catalogs, platforms.
- Transitive dependency graph.
- Maven/Gradle plugins.
- Annotation processors.
- Test-only hoặc runtime-only classpath.
- ServiceLoader và META-INF/services.
- Framework auto-configuration.
- Reflection strings, plugin registration.
- Java agents hoặc JVMTI agents.
- JNI/JNA native binaries.
- Container OS packages.
- JAR được COPY thủ công vào image.
- Shaded/fat JAR hoặc WAR libraries.
- Generated sources và toolchain.

Do đó, câu hỏi “IDE có import class của JAR này không?” chỉ là bước khởi đầu.

### 4.1. Phân loại theo vai trò

| Nhóm | Ví dụ | Rủi ro khi xóa |
|---|---|---|
| Legacy API | javax EE, JAXB/JAX-WS | Code/plugin cũ mất type |
| New API | Jakarta API | Thiếu implementation/provider |
| Backport | API cho JDK cũ | Consumer baseline thấp còn cần |
| Bytecode library | ASM/Byte Buddy | Agent/mock/proxy không tạo được class |
| Logging bridge | SLF4J/JUL/Log4j bridge | Mất log hoặc vòng bridge |
| Native library | JNI/JNA codec | UnsatisfiedLinkError |
| Test dependency | Mocking/coverage | Test không chạy, agent thiếu |
| JDBC driver | Service provider | Runtime không kết nối database |
| Annotation processor | Code generation | Generated source biến mất |

## 5. Điều tra dependency với Maven

~~~bash
./mvnw dependency:tree
~~~

Khi project là multi-module:

~~~bash
./mvnw -pl service-app dependency:tree
~~~

Một ví dụ lọc artifact:

~~~bash
./mvnw dependency:tree -Dincludes=org.example:legacy-adapter
~~~

Tên module và artifact chỉ để minh họa, điều chỉnh theo project.

### 5.1. Direct và transitive

~~~text
service-app
   |
   +-- framework-starter
   |      |
   |      +-- legacy-provider
   |
   +-- legacy-provider (direct)
~~~

Xóa dependency trực tiếp chưa chắc loại thư viện khỏi runtime vì starter vẫn kéo nó đến.

### 5.2. Exclusion có thể cần nhưng phải kiểm thử

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>framework-starter</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-provider</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Nếu framework cần legacy-provider qua reflection, exclusion có thể làm build xanh nhưng runtime lỗi. Phải biết dependency path và provider role.

### 5.3. Effective configuration

~~~bash
./mvnw help:effective-pom
./mvnw help:active-profiles
~~~

Parent POM, dependencyManagement, pluginManagement và profiles có thể giữ version hoặc option đã tưởng được xóa ở module.

## 6. Điều tra dependency với Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
  --dependency legacy-adapter \
  --configuration runtimeClasspath
~~~

Một số configuration:

| Configuration | Ý nghĩa |
|---|---|
| api | Dependency công bố qua API |
| implementation | Implementation dependency |
| compileOnly | Chỉ dùng cho compile |
| runtimeOnly | Cần ở runtime, thường không import trực tiếp |
| testImplementation | Compile/run test |
| testRuntimeOnly | Provider chỉ có ở test runtime |
| annotationProcessor | Bộ tạo source |

Không xóa runtimeOnly vì source không import trực tiếp. Một JDBC driver hoặc provider có thể được ServiceLoader tìm thấy lúc chạy.

### 6.1. Version catalog không thuộc một module duy nhất

Xóa module usage chưa chắc version catalog entry đã dư, vì các module khác có thể vẫn dùng. Kiểm tra toàn repository trong phạm vi được giao cho quy trình cleanup.

### 6.2. Buildscript và plugin classpath

Một library có thể chỉ phục vụ build plugin hoặc annotation processing, không xuất hiện trong runtimeClasspath. Nếu đang làm cleanup build tooling, cần nhìn đúng configuration.

## 7. Phân tích dependency bằng mã nguồn và công cụ JDK

Một số lệnh tham khảo:

~~~bash
jdeps --jdk-internals target/app.jar
jdeprscan --release 17 target/app.jar
~~~

jdeps giúp phát hiện một số tham chiếu tới JDK internal APIs; jdeprscan giúp nhận diện API deprecated trong phạm vi công cụ hỗ trợ.

Những công cụ này không chứng minh mọi runtime dependency đã được tìm thấy vì chúng không nhất thiết phát hiện:

- Reflection strings.
- ServiceLoader providers.
- Generated class names.
- Code tải plugin từ cấu hình.
- Native libraries.
- Resource-driven class loading.
- Code chỉ có trong một deployment cụ thể.

Khi cần, phân tích cả các JAR ngoài app.jar và cung cấp classpath thích hợp.

### 7.1. Deprecated khác removed

Deprecated là cảnh báo thiết kế; deprecated for removal là dấu hiệu API có thể bị loại; removed là API không còn tồn tại ở phiên bản đó. Public API deprecated vẫn có thể được support policy bảo vệ, không tự động được phép xóa.

## 8. ServiceLoader và runtime-only code

Ví dụ:

~~~java
import java.util.ServiceLoader;

public final class DriverInventory {
    public static void main(String[] args) {
        for (java.sql.Driver driver
                : ServiceLoader.load(java.sql.Driver.class)) {
            System.out.println(driver.getClass().getName());
        }
    }
}
~~~

Code không cần import tên implementation của từng driver. Nếu xóa JAR chỉ vì thiếu import, hệ thống có thể mất JDBC provider ở runtime.

Các trường hợp tương tự:

- Logging provider/binding.
- JSON/XML serialization modules.
- ServletContainerInitializer.
- CDI/JPA provider.
- JDBC driver.
- Native codec loader.
- Third-party plugin.

**Dependency removal phải được kiểm tra ở artifact/runtime, không chỉ compile.**

## 9. Những xung đột dependency thường gặp sau migration

- Hai versions của một API/provider.
- Legacy javax EE và Jakarta EE provider cùng nằm trên runtime path.
- Hai logging bindings hoặc bridge vòng lặp.
- Jackson modules không đồng bộ versions.
- ASM/Byte Buddy đời cũ không hiểu class-file version mới.
- JNI/JNA libraries khác architecture hoặc ABI.
- Cùng một class trong shaded JAR và dependency thường.
- Split packages trên Java module path.
- Thư viện compile cho Java release cao hơn JRE production.

### 9.1. Legacy javax và Jakarta

javax.servlet.Filter và jakarta.servlet.Filter là hai type khác nhau. Việc giữ cả hai API JAR không làm plugin servlet cũ tương thích với Jakarta Servlet runtime.

Không được xóa mọi javax.*: javax.sql, javax.net.ssl, javax.crypto và javax.xml.parsers vẫn là API Java SE.

### 9.2. Logging bridge

Nếu adapter A chuyển log sang B và bridge B chuyển ngược về A, có thể tạo vòng lặp hoặc duplication. Cần chọn logging architecture cuối, một provider/binding tương ứng và dọn những bridge dư.

### 9.3. Bytecode tool version

Một thư viện instrumentation cũ có thể không hỗ trợ Java class-file mới. Dọn bằng cách nâng phiên bản được vendor hỗ trợ, không giữ --add-opens rộng mãi mãi để che nhiều loại lỗi khác nhau.

## 10. Hiểu cờ --add-opens trong JPMS

Java Platform Module System giới hạn quyền truy cập package giữa modules. Một framework cũ có thể gọi reflection vào private field của JDK class, rồi gặp InaccessibleObjectException.

Cờ ví dụ:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

Nó mở java.lang của java.base cho unnamed modules theo quy tắc runtime. Đây là **quyền bổ sung**, không phải cấu hình phải có cho mọi chương trình Java.

### 10.1. Tại sao phải xem lại cờ?

Nếu framework đã được nâng để dùng public API và không còn cần deep reflection, cờ tạo quyền rộng không cần thiết và làm khó nhận diện dependency còn dùng internal behavior.

### 10.2. Scope của ALL-UNNAMED

ALL-UNNAMED cho phép những unnamed modules (thường code trên classpath) hưởng phạm vi mở tương ứng, không chỉ thư viện gây ra lỗi ban đầu. Khi có thể, nên loại bỏ thay vì nới quyền.

### 10.3. Đừng phụ thuộc cờ như một hợp đồng ổn định

Một JDK internal implementation có thể đổi hoặc bị loại. Mở package không khiến private API có cùng cam kết với public Java SE API.

## 11. Phân biệt --add-opens và --add-exports

| Cơ chế | Tác dụng chính |
|---|---|
| exports | Cho phép dùng các public types của package theo module accessibility |
| opens | Cho phép deep reflection theo module access rules |
| --add-exports | Bổ sung export của một package |
| --add-opens | Bổ sung openness ở runtime |

Ví dụ workaround:

~~~text
--add-exports=java.base/sun.nio.ch=ALL-UNNAMED
~~~

Đây là ví dụ để nhận diện **rủi ro sử dụng API nội bộ**, không phải cờ nên thêm vào mọi service.

Nếu một thư viện cần truy cập non-exported public type, --add-exports có vai trò khác với --add-opens dùng cho private reflection. Không thay chúng tùy ý.

### 11.1. Compiler và runtime có cấu hình riêng

Một source dùng non-exported API có thể cần compiler option phù hợp, nhưng runtime cũng phải có quyền nếu code thực sự liên kết tới API đó. Không giả định Maven compiler args tự truyền tới Surefire hoặc production Java command.

### 11.2. Public replacement tốt hơn

Tùy use case có thể chuyển sang public NIO APIs, VarHandle, MethodHandles trong giới hạn access hợp lệ, hoặc nâng framework. Không phải internal API nào cũng có bản thay thế trực tiếp; phải test behavior và performance.

## 12. Những flags khác cần kiểm kê

| Option | Ý nghĩa | Câu hỏi cleanup |
|---|---|---|
| --add-opens | Mở package cho reflection | Ai còn cần? |
| --add-exports | Bổ sung export | Có còn dùng JDK internals? |
| --add-reads | Bổ sung readability | Module graph đã sửa đúng chưa? |
| --patch-module | Patch module | Còn hợp đồng cần patch? |
| --add-modules | Thêm modules | Module nào thực sự cần? |
| --limit-modules | Giới hạn observable modules | Có thiếu provider không? |
| --enable-preview | Bật preview features | Code còn dùng preview không? |
| --enable-native-access | Cho phép native access theo JDK | Component nào cần và phạm vi nào? |

Không có quy tắc “xóa toàn bộ flags”. Mục tiêu là loại những cờ tạm, lỗi thời, dư hoặc quá rộng.

### 12.1. --illegal-access là cờ chuyển tiếp lịch sử

Một số JDK sau Java 8 từng hỗ trợ --illegal-access như biện pháp chuyển tiếp. Từ Java 17, option này không còn là cách hữu hiệu để nới lỏng strong encapsulation như giai đoạn trước.

Không nên giữ cờ cũ trên JVM mới và coi warning/ignored flag là giải pháp. Phải xem tài liệu của đúng JDK target.

### 12.2. Native access

Các JDK mới có cơ chế cảnh báo/kiểm soát JNI hoặc Foreign Function & Memory khác nhau theo release. Không cấp --enable-native-access=ALL-UNNAMED mặc định cho toàn bộ ứng dụng; xác định module/library thực sự cần và chính sách cụ thể.

## 13. JVM flags được cấu hình ở những đâu?

Một dự án có nhiều JVM processes:

~~~text
Maven/Gradle JVM
      |
Test JVMs
      |
Integration test process
      |
Production application JVM
      |
Batch/scheduler JVM
      |
Agent or maintenance process
~~~

Cờ có thể xuất hiện trong:

- JAVA_TOOL_OPTIONS/JDK_JAVA_OPTIONS.
- Shell script, systemd, Windows service.
- Docker ENTRYPOINT/CMD.
- Helm/Kubernetes args/env.
- Maven Surefire/Failsafe argLine.
- Gradle Test/JavaExec jvmArgs.
- Application server settings.
- CI workflows và secrets.
- IDE run config.
- Runbook.

Xóa ở một nơi không có nghĩa đã xóa khỏi production.

### 13.1. Maven Surefire

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <argLine>
            --add-opens=java.base/java.lang=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
~~~

Ví dụ này chỉ minh họa nơi cờ tồn tại. Với JaCoCo và agents khác có thể cùng thay argLine; đừng ghi đè toàn bộ options mà không kiểm tra.

### 13.2. Gradle Test

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED")
}
~~~

Cờ này áp dụng với JVM của Test task, không tự áp vào JVM chạy production JAR.

### 13.3. Kiểm tra effective JVM configuration

Phải xác minh command line/runtime args thực tế trong môi trường mục tiêu. Có thể có sự khác biệt giữa file configuration trong Git và options được platform injected.

## 14. Cách gỡ --add-opens có kiểm soát

Giả sử một thư viện mock cũ cần mở java.lang, nhưng version mới đã hỗ trợ JDK đích.

1. Ghi lại stack trace/lý do thêm cờ.
2. Xác nhận phiên bản thư viện được vendor hỗ trợ.
3. Gỡ cờ trong một môi trường kiểm thử.
4. Chạy clean unit, contract và integration tests.
5. Kiểm tra reflection/proxy/DI/ORM/serializer paths.
6. Khởi động final production image.
7. Kiểm tra dynamic plugins, agents và scheduled jobs.
8. Xác nhận cờ không bị inject lại qua environment.
9. Canary và theo dõi lỗi.
10. Gỡ khỏi mọi script/template/runbook.

### 14.1. Vì sao java -version không đủ?

Lệnh này không kích hoạt reflection hoặc plugin loading. Lỗi có thể chỉ xảy ra khi request đầu tiên chạm vào một class hoặc khi scheduler chạy cuối tháng.

### 14.2. Gỡ từng nhóm

Nếu có nhiều --add-opens/--add-exports, ưu tiên nhóm theo dependency/owner thay vì xóa tất cả cùng lúc rồi không biết flag nào gây lỗi.

### 14.3. Khi chưa gỡ được

Ghi rõ component cần quyền, package, phạm vi JVM, support risk, owner và mốc review. Không nên để quyền rộng mà không ai chịu trách nhiệm.

## 15. Thay reflection fallback bằng public API

Mã chuyển tiếp:

~~~java
import java.lang.reflect.Field;

public final class LegacyReflection {
    public static Object read(
            Object instance, String fieldName) throws Exception {
        Field field = instance.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(instance);
    }
}
~~~

Có thể bị chặn bởi module encapsulation. Nếu ứng dụng sở hữu class, thiết kế accessor công khai:

~~~java
public final class Order {
    private final String status;

    public Order(String status) {
        this.status = status;
    }

    public String status() {
        return status;
    }
}
~~~

Khi consumer đã dùng API chính thức và test xác minh đúng, có thể bỏ fallback và quyền mở liên quan.

Với framework bên thứ ba, ưu tiên nâng bản được hỗ trợ hoặc sử dụng extension point hợp lệ. MethodHandles cũng tuân theo access control; không phải cách bypass JPMS vô điều kiện.

## 16. Dọn các JVM flags khác sau nâng JDK

Bên cạnh module access, thường còn:

- Cờ GC logging Java 8 đã chuyển sang Unified Logging.
- GC tuning flags không còn áp dụng.
- Preview flags không còn dùng.
- Diagnostic/trace flags chỉ phục vụ incident.
- Java agent options thuộc version cũ.
- Cấu hình TLS/security compatibility tạm.
- Locale/charset overrides không còn lý do.
- Native access flags quá rộng.

### 16.1. Ví dụ GC logs

Trước:

~~~text
-XX:+PrintGCDetails
-Xloggc:/logs/gc.log
~~~

Sau với JVM hỗ trợ Unified Logging:

~~~text
-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Cần kiểm thử cả log parser/rotation/retention, không chỉ JVM startup.

### 16.2. Không xóa tuning hợp lệ

-Xmx hoặc lựa chọn collector có thể là cấu hình hiệu năng được đo đạc. Không đặt mục tiêu startup line càng ngắn càng tốt; chỉ dọn flags không cần hoặc không có căn cứ.

## 17. Mã trung gian trong migration

Một số kiểu code:

- OldSerializer/NewSerializer.
- LegacyDateBridge giữa java.util.Date và java.time.
- ReflectionFallback.
- JavaVersionStrategy.
- API aliases và compatibility shim.
- javax/Jakarta adapter.
- Database dual-read/dual-write.
- Event schema V1/V2 converter.
- Feature flag switch.
- CompatibilityFacade.
- Multi-release JAR classes.
- Native client/agent wrapper.

Không phải tất cả đều dư. Một adapter domain có thể là ranh giới kiến trúc lâu dài; một shim cho consumer cũ có thể còn được cam kết. Cleanup cần phân biệt rõ.

## 18. Ví dụ dual serializer và thời điểm dọn

~~~java
public final class EventWriter {
    private final Serializer oldSerializer;
    private final Serializer newSerializer;
    private final boolean useNew;

    public EventWriter(
            Serializer oldSerializer,
            Serializer newSerializer,
            boolean useNew) {
        this.oldSerializer = oldSerializer;
        this.newSerializer = newSerializer;
        this.useNew = useNew;
    }

    public byte[] encode(Event event) {
        return useNew
            ? newSerializer.encode(event)
            : oldSerializer.encode(event);
    }
}
~~~

Sau khi mọi writer chuyển sang implementation mới, consumer compatibility được xác nhận và rollback window đóng:

~~~java
public final class EventWriter {
    private final Serializer serializer;

    public EventWriter(Serializer serializer) {
        this.serializer = serializer;
    }

    public byte[] encode(Event event) {
        return serializer.encode(event);
    }
}
~~~

### 18.1. Old writer khác old reader

Ngừng ghi event V1 không có nghĩa dữ liệu V1 đã biến mất. Có thể xóa old writer trước nhưng giữ old reader cho đến khi dữ liệu lịch sử được chuyển hoặc hết retention.

### 18.2. Feature flag không phải rollback bảo đảm

Nếu new writer tạo dữ liệu mà old reader không hiểu, toggle flag về OFF không bảo đảm rollback. Phải xét data schema, event format và database compatibility.

### 18.3. Dọn cả control plane

Sau khi loại cờ trong Java source, cũng phải xóa/đóng flag trong feature flag service, Helm values, config, CI, dashboard và tài liệu để người vận hành không tưởng còn đường fallback.

## 19. Feature flag lifecycle

~~~text
OFF by default
      |
Canary for internal users
      |
Rollout by tenant/percentage
      |
ON for all traffic
      |
Observe rollback window
      |
Remove OFF path and flag
~~~

Trước khi xóa cần hỏi:

- Có tenant nào vẫn dùng OFF path?
- Có batch jobs hiếm hoặc consumers legacy không?
- Dữ liệu mới có backward-compatible?
- Rollback được cam kết tới thời điểm nào?
- Monitoring có chứng minh traffic đã chuyển?
- Có test dữ liệu lịch sử chưa?
- Có ai sở hữu quyết định đóng flag chưa?

Giữ một fallback không được chạy nhiều tháng có thể tạo cảm giác an toàn giả, vì đường cũ không còn được kiểm thử.

## 20. Adapter, facade và shim: giữ hay xóa?

| Thành phần | Khi giữ | Khi dọn |
|---|---|---|
| Domain facade | Ổn định ranh giới kiến trúc | Chỉ phục vụ library cũ |
| API compatibility shim | Consumer cũ còn được support | Support window đóng |
| Schema converter | Có dữ liệu lịch sử | Dữ liệu đã migrate/hết retention |
| Reflection fallback | Runtime cũ còn hỗ trợ | JDK/library đã thay và không cần |
| Dual client | Hai backend cùng tồn tại | Backend cũ đã tắt an toàn |
| Multi-release JAR | Thư viện hỗ trợ nhiều JDK | Minimum JDK tăng và variant cũ dư |
| Native wrapper | ABI legacy được cam kết | Native client/vendor mới đồng bộ |

Không quyết định chỉ dựa trên tên Legacy hoặc số call sites. Public library có thể không có internal call sites nhưng vẫn có consumers bên ngoài.

## 21. Public API, SPI và plugin compatibility

Ví dụ interface cũ:

~~~java
public interface LegacyPlugin {
    void execute(LegacyContext context);
}
~~~

Interface mới:

~~~java
public interface Plugin {
    void execute(PluginContext context);
}
~~~

Nếu xóa LegacyPlugin, plugin binary đã build trước đó có thể bị linkage errors.

### 21.1. Trước khi xóa

- Có support policy và consumer inventory.
- Đã công bố deprecation/migration guide.
- Có decision về breaking version.
- Đã xác nhận consumers/plugins chuyển.
- Có binary compatibility tests khi cần.
- Đã thử plugin loading trên JDK/container đích.
- Rollback không còn phụ thuộc old interface.

### 21.2. Deprecated không đồng nghĩa hết hỗ trợ

Một public method đã deprecated vẫn có thể cần trong support window. Removal phải đi qua versioning và consumer migration process.

### 21.3. ServiceLoader metadata

Nếu plugin được tải qua META-INF/services hoặc config string, xóa implementation phải cập nhật metadata và kiểm thử discovery. Compile success chưa đủ.

## 22. Cleanup javax sang Jakarta đúng phạm vi

Một ứng dụng sau chuyển Jakarta EE có thể còn:

~~~text
Legacy javax.servlet / javax.persistence APIs
New jakarta.servlet / jakarta.persistence APIs
Old web filters and providers
New Jakarta-compatible filters
Binary transformation utility
~~~

Các enterprise APIs chuyển namespace là những type khác nhau. Chỉ thêm cả hai JAR không khiến javax.servlet.Filter trực tiếp tương thích jakarta.servlet.Filter.

### 22.1. Không xóa javax thuộc Java SE

javax.sql, javax.net.ssl, javax.crypto và javax.xml.parsers vẫn là Java SE APIs. Không áp một rule cấm toàn bộ javax imports.

### 22.2. Jakarta EE 8 có nuance

Một số Jakarta EE 8-era artifacts mang tên Jakarta nhưng class packages vẫn là javax. Phải xem đúng API release và nội dung JAR, không suy luận từ Maven groupId.

### 22.3. Dọn binary transformer

Khi đã có bản Jakarta-native từ vendor, có thể thay transformed legacy binary, kiểm tra service metadata, framework behavior và gỡ transformation step sau khi test thành công.

## 23. Dependency cho API từng có trong JDK

Một ví dụ điển hình là JAXB/JAX-WS. Khi nâng Java 8 lên các JDK mới, project có thể phải thêm dependency vì một số module Java EE trước đây từng đi kèm JDK đã không còn ở JDK 11.

Một lộ trình:

~~~text
Java 8
  Legacy javax.xml.bind code

Java 11 transition
  Explicit compatible JAXB API + runtime

Jakarta stack migration
  Switch source/generated code to jakarta.xml.bind
  Upgrade API and implementation

Post-transition cleanup
  Remove unused legacy JAXB stack
  Remove bridge/transformer
  Verify historic XML is still readable
~~~

API JAR không thay thế runtime implementation. Nếu xóa provider không cần import trực tiếp, JAXB operation có thể lỗi khi chạy.

### 23.1. Generated sources

Nếu generator vẫn phát sinh javax.xml.bind imports, cần nâng generator/template; không sửa output generated bằng tay.

### 23.2. Data history

Nếu old XML/data còn được đọc theo contract, giữ reader phù hợp hoặc migrate dữ liệu có đối soát trước khi xóa.

## 24. Dữ liệu lịch sử và schema version

Hệ thống có thể ngừng ghi V1 nhưng vẫn giữ hàng triệu records V1.

~~~text
Old data: V1
New data: V2

New writer: writes V2
Current reader: reads V1 + V2
~~~

Việc xóa V1 reader chỉ an toàn khi:

1. Tất cả dữ liệu V1 đã chuyển sang V2 với validation/rollback.
2. Dữ liệu V1 đã hết retention và được xóa theo policy.
3. Contract hỗ trợ V1 được chấm dứt và consumer impact được xử lý.

Không được coi new writer rollout 100% là bằng chứng old reader đã vô dụng.

### 24.1. Expand-contract

~~~text
Expand schema
      |
Support old/new readers and writers
      |
Migrate data and consumers
      |
Close rollback window
      |
Contract old columns/adapters
~~~

Xóa old column hoặc mapper trước khi rollback window đóng có thể làm bản ứng dụng cũ không hoạt động.

### 24.2. Dual write

Ghi đồng thời V1/V2 cần idempotency và transaction safeguards; nếu không có thể tạo duplicate events/payments. Khi cleanup, cần xác nhận chỉ một logical side effect được tạo.

## 25. Rollback cũng có contract

Một kế hoạch rollback phải xét nhiều tầng:

~~~text
Application release
   |
   +--> Java runtime and JVM flags
   +--> Container image digest
   +--> Database schema
   +--> Event/serialization format
   +--> Native libraries and agents
   +--> Feature flag configuration
~~~

Nếu V2 ghi dữ liệu mà V1 không đọc được, chỉ đổi image về V1 có thể làm ứng dụng lỗi hoặc mất dữ liệu.

### 25.1. Quyết định đóng rollback window

Cần có:

- Thời hạn rollback được hỗ trợ.
- Consumer inventory đã nâng.
- Data format compatibility đã kiểm chứng.
- Backup/restore/replay strategy.
- Người phê duyệt mốc không quay về V1.
- Lịch dọn adapters, flags, old configs.

### 25.2. Runtime flags theo release

Một image Java 8 và một image Java 21 có thể dùng GC logging/module flags khác nhau. Rollback config phải gắn với artifact, không sử dụng chung một command line chứa flags không hợp lệ.

## 26. Build configuration cleanup

Các dấu vết thường gặp:

- maven.compiler.source/target chồng với maven.compiler.release.
- Temporary Maven profiles.
- Compiler executable path pin tạm.
- Plugin version override cũ.
- Annotation processor không hỗ trợ JDK mới.
- Shading/exclusion rules không còn cần.
- Gradle JVM args cho tests nhưng production không cần.
- Copy task chứa native binary cũ.
- Legacy BOM hoặc version catalog entries.

Ví dụ Maven với Java 17 baseline:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Nếu artifact phải hỗ trợ Java 17, đừng đổi release lên 21 chỉ vì Maven chạy trên JDK 21.

### 26.1. Mâu thuẫn source/target/release

~~~xml
<maven.compiler.source>8</maven.compiler.source>
<maven.compiler.target>8</maven.compiler.target>
<maven.compiler.release>17</maven.compiler.release>
~~~

Nếu chọn release làm chuẩn, nên dọn các thiết lập mâu thuẫn rồi kiểm tra effective POM.

### 26.2. Gradle toolchain khác release

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Compiler JDK 21 có thể tạo artifact target Java 17. Hai version này phục vụ mục đích khác nhau.

## 27. Cleanup từ source đến production

Một thay đổi có thể cần cập nhật:

~~~text
Source and tests
    |
    +--> pom.xml / build.gradle
    +--> generated-code templates
    +--> Dockerfile / container image
    +--> Kubernetes / Helm / systemd
    +--> CI workflows
    +--> feature flag control plane
    +--> agent settings
    +--> logs / dashboards / alerts
    +--> rollback scripts and runbooks
~~~

Xóa dependency khỏi source nhưng vẫn copy JAR vào container thì runtime vẫn chứa thư viện đó.

### 27.1. Kiểm tra final artifact

Đối chiếu resolved dependency graph với executable JAR, WAR và container image. Nếu dùng shading, có thể còn duplicated classes hoặc old providers.

### 27.2. Kiểm tra effective JVM args

Một cờ đã bị xóa khỏi POM nhưng còn trong JAVA_TOOL_OPTIONS được injected ở cluster sẽ vẫn có hiệu lực. Phải nhìn runtime configuration thực tế.

### 27.3. Cập nhật runbook

Sau cleanup, runbook không nên khuyên thêm --add-opens rộng như cách xử lý reflection errors mặc định. Hãy hướng dẫn xác định dependency/version/module boundary.

## 28. Cách kiểm thử việc gỡ dependency

Quy trình thực tế:

1. Xác định artifact, version, dependency path và scope.
2. Tìm code/reference và config.
3. Kiểm tra ServiceLoader, reflection, plugins, native components.
4. Xác định public API/SPI và consumers.
5. Xóa dependency ở branch có kiểm soát.
6. Chạy clean compile, unit/contract/integration tests.
7. Kiểm tra dependency graph đã resolve.
8. Inspect final packaged JAR/WAR/image.
9. Chạy các paths sử dụng provider runtime.
10. Smoke test trên JDK/container đích.
11. Canary và đo business/error metrics.
12. Dọn exclusions, overrides và docs liên quan.

Không dùng compile success như bằng chứng duy nhất: runtime-only provider có thể bị thiếu mà javac không báo lỗi.

## 29. Kiểm thử việc gỡ mã trung gian

Cần tối thiểu:

- Contract tests cho API và event formats.
- Fixtures dữ liệu lịch sử.
- Database migration/rollback tests.
- Serializer round-trip.
- Idempotency và duplicate side-effect tests.
- Authorization và validation negative tests.
- Dynamic plugin/agent loading.
- Concurrency/retry behavior.
- Performance regression.
- Startup/graceful shutdown.

Một adapter có thể chứa caching, batching, error mapping hoặc retry logic. Xóa nó không chỉ là xóa class; phải kiểm tra behavior mới không thay đổi ngoài hợp đồng.

## 30. Canary sau khi gỡ JVM access flags

~~~text
Remove flag in test configuration
              |
       Build and tests
              |
       Staging with final image
              |
       Canary selected instances
              |
       Monitor access/linkage errors
              |
       Expand rollout or rollback
              |
       Close flag cleanup record
~~~

Theo dõi:

- InaccessibleObjectException.
- IllegalAccessError.
- NoClassDefFoundError.
- NoSuchMethodError.
- ServiceConfigurationError.
- Startup failures.
- Serialization/ORM/proxy errors.
- Agent/JNI problems.
- Business error rates và latency.

### 30.1. Paths hiếm

Canary vài giờ không bảo đảm monthly batch hoặc plugin code path đã chạy. Phải tạo synthetic/replay tests hoặc kéo dài observation window phù hợp.

### 30.2. Chứng minh quyền đã giảm

Sau canary, kiểm tra effective JVM arguments để bảo đảm --add-opens không bị inject từ nguồn khác.

## 31. SBOM và bảo mật dependency

Sau migration, SBOM có thể vẫn ghi nhận thư viện cũ do:

- Shaded/relocated classes.
- Manually copied JAR.
- OS package trong base image.
- Duplicate provider.
- Native library bị bỏ quên.

Nên đối chiếu artifact thực tế, license, support status, CVEs và provenance.

### 31.1. Không xóa dependency chỉ để giảm CVE count

Một library vẫn cần có thể phải nâng version hoặc thay implementation. Xóa nó có thể phá runtime functionality.

### 31.2. Immutable image

Khi thay dependency hoặc base image, ghi lại image digest và chạy security/functional tests. Mutable tag không đủ để tái hiện production artifact.

## 32. Dọn operational debt

Ngoài code/dependency, cần xem:

- Legacy GC parser không hiểu Unified Logging.
- Alert dùng exception text cũ.
- Debug JVM flags đang bật quá lâu.
- Native agent version cũ.
- Dashboard tìm package javax.* đã được chuyển.
- Scripts tải heap dump/JFR không phù hợp image mới.
- CI còn test theo profile không được hỗ trợ.
- Runbook có command line của JDK cũ.

### 32.1. Không xóa metric mà mất cảnh báo

Nếu old metric không còn được phát, cần tạo metric/alert thay thế trước khi xóa. Khả năng phát hiện OOME, GC pauses, TLS failures, queue lag và security issues phải được giữ.

### 32.2. Debug flags có chi phí

Trace-level logs có thể tăng CPU/I/O và lộ runtime metadata. Khi migration ổn định, đưa logging về baseline được thiết kế.

## 33. Guardrails để nợ tương thích không quay lại

Các biện pháp:

- Maven Enforcer/Gradle constraints cho version alignment.
- jdeps/internal API scans.
- Rules kiểm tra dependency bị cấm hoặc unsupported.
- CI phát hiện --add-opens/--add-exports mới cần review.
- Contract tests cho API/SPI.
- Test matrix cho minimum supported JDK.
- Runtime smoke test trên final container image.
- SBOM diff và security review.
- PR template buộc khai báo owner và removal condition.

### 33.1. Đừng cấm bằng pattern quá rộng

Một rule cấm mọi javax imports sẽ báo sai với javax.sql và javax.net.ssl thuộc Java SE. Một rule cấm mọi --add-opens có thể chặn exception đã được phê duyệt. Nên có policy cụ thể và danh sách ngoại lệ có owner.

### 33.2. Mẫu lý do khi thêm workaround mới

~~~text
Workaround ID:
Why needed:
Affected dependency:
Affected JVM process:
Minimal scope:
Security impact:
JDK versions:
Owner:
Removal condition:
Review date:
Integration tests:
~~~

Nhờ đó cleanup của đợt migration tiếp theo sẽ dễ hơn.

## 34. Tình huống tổng hợp: Java 11 sang Java 21

Một order service đã chạy Java 21 nhưng còn:

~~~text
Dependencies:
  legacy XML binding library
  Jakarta XML Binding runtime
  older bytecode tool
  temporary JSON adapter

JVM:
  --add-opens=java.base/java.lang=ALL-UNNAMED
  --add-exports=java.base/sun.nio.ch=ALL-UNNAMED

Code:
  OldJsonWriter
  NewJsonWriter
  ReflectionFallback
  USE_NEW_JSON
~~~

### Bước 1 — Kiểm kê graph và usage

Xem Maven/Gradle, generated code, providers và container image. Không kết luận từ import count.

### Bước 2 — Đánh giá dữ liệu/consumer

Có historical XML hoặc JSON V1 không? Consumer còn dùng schema/old API không? Rollback còn cam kết không?

### Bước 3 — Nâng dependency

Thay bytecode framework bằng bản hỗ trợ JDK 21. Đồng bộ Jakarta API và runtime, tránh duplicate providers.

### Bước 4 — Dọn reflection fallback

Chuyển sang public API/library chính thức, chạy regression tests. Khi không còn reference, gỡ code tạm.

### Bước 5 — Thu hồi quyền JVM

Gỡ --add-exports/--add-opens theo component, test reflection/proxy/ORM/agents. Canary bằng final production image.

### Bước 6 — Đóng serializer rollout

Xác nhận mọi writes mới dùng V2, consumers đã chuyển và dữ liệu lịch sử vẫn đọc được. Xóa old writer/feature flag đúng thời điểm; giữ V1 reader nếu còn data.

### Bước 7 — Dọn artifact và runbook

Loại legacy JARs, stale flags, CI variables, old scripts; cập nhật SBOM/digest và ghi quyết định cleanup.

## 35. Những sai lầm phổ biến

### “Không import trực tiếp thì dependency vô dụng”

Sai. ServiceLoader, reflection, generated code, native loading và framework provider discovery có thể dùng nó.

### “Đã lên JDK mới thì gỡ mọi cờ --add-opens ngay”

Chưa đủ. Cần kiểm tra code paths hiếm, plugins và agents; gỡ theo bằng chứng và phạm vi.

### “--add-opens và --add-exports giống nhau”

Sai. Chúng giải quyết các loại access khác nhau, và cả hai cần được kiểm soát.

### “Cấp export cho internal API nghĩa là API đó được hỗ trợ lâu dài”

Sai. JDK internal APIs vẫn có thể thay đổi hoặc biến mất.

### “Một flag không làm JVM crash nên cứ để lại”

Không nên. Nó có thể obsolete, bị ignored hoặc mở quyền không cần thiết.

### “Đường code cũ không có traffic nên xóa được”

Chưa chắc. Có thể còn historical data, consumer legacy, batch job hoặc rollback.

### “Feature flag luôn giúp rollback”

Không đúng nếu dữ liệu do code mới ghi không tương thích code cũ.

### “Xóa dependency trong POM là container đã sạch”

Không chắc. Shading, manual COPY hoặc stale runtime assets có thể còn.

### “Unit tests xanh chứng minh cleanup thành công”

Chưa đủ nếu provider/agent chỉ được load ở runtime hoặc scheduled job hiếm.

### “Deprecated API có thể xóa tùy lúc”

Không đúng với public compatibility contract; cần versioning/deprecation policy.

### “Known defect có thể ghi thành allowed difference”

Không nên. Defect cần tracking và risk acceptance riêng, không hợp thức hóa thành behavior đúng.

### “Càng ít JAR càng tốt”

Không nếu làm mất provider cần thiết. Correctness và support contract quan trọng hơn số thư viện.

## 36. Checklist cleanup sau migration

- [ ] Đã xác định JDK target và minimum runtime được hỗ trợ.
- [ ] Đã liệt kê dependencies, JVM flags và transitional code.
- [ ] Mỗi workaround có owner, scope và removal condition.
- [ ] Đã xem Maven/Gradle resolved graphs.
- [ ] Đã phân biệt compile/runtime/test/annotation processor.
- [ ] Đã kiểm tra reflection, ServiceLoader, config strings và native loading.
- [ ] Đã đánh giá public API/SPI và plugin consumers.
- [ ] Đã kiểm tra generated code.
- [ ] Đã phân biệt --add-opens với --add-exports.
- [ ] Đã tìm internal API replacement hoặc vendor-supported library.
- [ ] Không còn quyền module quá rộng khi không cần.
- [ ] Không giữ obsolete flags như biện pháp che lỗi.
- [ ] Đã kiểm tra build/test/production JVMs riêng.
- [ ] Đã phân loại đúng javax Java SE và Jakarta EE.
- [ ] Đã xác minh dữ liệu lịch sử/event compatibility.
- [ ] Đã đóng rollback window hoặc thiết kế data migration.
- [ ] Đã dọn feature flags và fallback không còn cần.
- [ ] Đã giữ legacy readers khi còn hợp đồng.
- [ ] Đã chạy clean build, contract và integration tests.
- [ ] Đã kiểm tra final JAR/WAR/container image.
- [ ] Đã test plugins, agents, reflection và scheduled paths.
- [ ] Đã canary và quan sát runtime.
- [ ] Đã cập nhật SBOM và security review.
- [ ] Đã dọn Docker/Helm/CI/scripts/runbook.
- [ ] Có guardrails cho workaround mới.

## 37. Mẫu hồ sơ một cleanup item

~~~text
IDENTITY
  ID:
  Owner:
  Type: dependency / JVM option / adapter / feature flag
  Introduced in release:
  Original blocker:
  Reason:
  Security and maintenance impact:

SCOPE
  Service/module:
  JDK vendor/version:
  Dependency/framework version:
  Build/test/runtime processes:
  Consumers/plugins:
  Historical data:

REMOVAL
  Artifact/flag/class:
  Proposed replacement:
  Vendor support evidence:
  Removal condition:
  Rollback window:
  Data migration/retention:

VALIDATION
  Source references:
  Dependency graph:
  ServiceLoader/reflection:
  Final image:
  Unit/contract tests:
  Integration tests:
  Agent/plugin tests:
  Runtime smoke:
  Canary:
  Security/performance:

DECISION
  Remove / retain / defer:
  Reviewer:
  Release:
  Remaining exceptions:
  Review date:
  Rollback artifact/config:
~~~

Hồ sơ cần được cập nhật cùng release để người vận hành và người nâng JDK sau này biết thành phần nào được giữ và vì sao.

## 38. Tổng kết

Dọn dependency, cờ mở quyền và mã trung gian là bước hoàn tất có trách nhiệm của Java compatibility migration. Một ứng dụng có thể đã chạy tốt trên JDK mới nhưng vẫn mang rủi ro của nền tảng cũ nếu giữ quá nhiều thư viện, quyền reflection mở rộng và nhánh fallback không còn được bảo trì.

Những nguyên tắc quan trọng:

1. **Dọn theo bằng chứng, không theo tên.** Runtime discovery có thể dùng dependency mà không có import Java.
2. **Quản lý quyền module theo phạm vi.** --add-opens và --add-exports có semantics khác nhau; quyền mở không làm internal API ổn định.
3. **Ưu tiên public APIs và libraries được hỗ trợ.** Không thay workaround cũ bằng workaround không có cam kết khác.
4. **Giữ đúng public contract và dữ liệu lịch sử.** Consumer, plugin và rollback có thể yêu cầu giữ adapter trong thời hạn.
5. **Không duy trì dual-path code vô thời hạn.** Sau rollout, dọn feature flags và đường code cũ theo kế hoạch.
6. **Dọn cả source, build lẫn runtime.** JAR, container, CI, startup arguments và runbook phải thống nhất.
7. **Kiểm thử code path hiếm.** Reflection, ServiceLoader, batch, agent và data history có thể chỉ lỗi sau nhiều ngày.
8. **Triển khai có canary và rollback.** Thu hồi một workaround là một thay đổi production, không chỉ refactor source.
9. **Duy trì guardrails.** Workaround mới cần owner, minimal scope và removal condition rõ ràng.

Migration chỉ thật sự hoàn thiện khi hệ thống không những chạy đúng trên JDK đích mà còn có dependency được hỗ trợ, quyền JVM có thể giải thích, mã trung gian dư thừa đã được loại bỏ và quy trình vận hành đáng tin cậy cho những lần nâng cấp tiếp theo.

