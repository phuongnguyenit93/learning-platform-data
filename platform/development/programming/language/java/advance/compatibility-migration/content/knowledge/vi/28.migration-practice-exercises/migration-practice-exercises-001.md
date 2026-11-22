# Tạo ma trận tương thích và báo cáo hiện trạng cho một dự án Java

Khi bắt đầu **Java Advance Compatibility Migration**, câu hỏi đầu tiên không nên chỉ là “Đổi `JAVA_HOME` sang JDK 21 có chạy được không?”. Một hệ thống Java còn phụ thuộc vào build tool, compiler target, các thư viện runtime, application server, Java agents, bộ đọc bytecode, native libraries, bảo mật TLS, hệ thống dữ liệu và cách triển khai. Việc nâng JDK chỉ an toàn khi biết **thành phần nào đã được kiểm chứng ở phiên bản nào, bằng chứng nằm ở đâu, và còn khoảng trống nào**.

Bài thực hành này hướng dẫn bạn tạo hai đầu ra cụ thể:

1. **Ma trận tương thích**: bảng đối chiếu từng thành phần, môi trường và phiên bản JDK với kết quả kiểm chứng có bằng chứng.
2. **Báo cáo hiện trạng**: tài liệu tóm tắt baseline, các rủi ro/gap, mức độ sẵn sàng, ưu tiên xử lý và đề xuất các bước migration có thể đo lường.

Để thực hành, ta sử dụng dự án giả định **OrderHub**, một dịch vụ xử lý đơn hàng Java. Toàn bộ số liệu, tên hệ thống, phiên bản, kết quả kiểm thử và đường dẫn báo cáo trong ví dụ đều là **dữ liệu minh họa**, không phải kết quả đã chạy trên một repository thật. Khi áp dụng cho dự án của bạn, phải thay chúng bằng kết quả kiểm chứng thực tế.

## 1. Mục tiêu học tập và sản phẩm bàn giao

Sau bài học, bạn có thể:

- Phân biệt **JDK chạy công cụ build**, **compiler/toolchain**, **bytecode target**, **JVM chạy test** và **JVM production**.
- Lập inventory của các dependency và integration có thể cản trở migration.
- Xây matrix kết hợp JDK, build tool, library, container, test suite và môi trường triển khai.
- Thu thập bằng chứng từ Maven/Gradle, `java`, `javap`, `jdeps`, runtime logs và CI.
- Ghi trạng thái `PASS`, `FAIL`, `BLOCKED`, `NOT_RUN` hoặc `UNKNOWN` mà không biến phỏng đoán thành kết luận.
- Gắn từng gap với mức rủi ro, owner, biện pháp xử lý và điều kiện xác nhận.
- Viết báo cáo hiện trạng đủ để người duyệt quyết định: **sẵn sàng canary**, **cần xử lý blocker** hay **cần bổ sung bằng chứng**.

### 1.1. Các tệp bàn giao gợi ý

Trong một dự án thực tế, có thể dùng cấu trúc:

```text
migration-assessment/
├── 01-inventory.csv
├── 02-compatibility-matrix.csv
├── 03-risk-register.csv
├── 04-current-state-report.md
├── 05-evidence-index.md
└── evidence/
    ├── jdk-runtime.txt
    ├── maven-version.txt
    ├── dependency-tree.txt
    ├── jdeps-report.txt
    ├── unit-tests.txt
    ├── integration-tests.txt
    └── baseline-metrics.txt
```

Đây chỉ là **cấu trúc đề xuất**. Bạn có thể dùng Google Sheets, Excel, Markdown, Jira, một database hoặc hệ thống quản trị bằng chứng của tổ chức. Điều quan trọng là **tất cả kết luận trong báo cáo truy được về nguồn bằng chứng**.

### 1.2. Definition of Done

Một bài thực hành được coi là hoàn chỉnh khi:

- Có scope: ứng dụng, phiên bản hiện tại, JDK mục tiêu, hệ thống tích hợp.
- Mỗi ô kết luận quan trọng đều có trạng thái và evidence.
- Những ô chưa kiểm chứng được ghi `NOT_RUN`/`UNKNOWN`, không để người đọc hiểu nhầm là đạt.
- Có danh sách rủi ro được ưu tiên và chủ sở hữu.
- Có lộ trình xử lý blocker, kiểm thử lại và bước rollout/rollback đề xuất.
- Mỗi bằng chứng có thời điểm, môi trường và artifact/version tương ứng.

## 2. Kịch bản dự án giả định: OrderHub

OrderHub là dịch vụ quản lý đơn hàng của một tổ chức giả định, gồm REST API, xử lý nghiệp vụ, lưu PostgreSQL và gửi thông điệp tới broker.

```text
Client / Gateway
       |
       v
OrderHub REST API
       |
       +--> Database: PostgreSQL
       |
       +--> Outbound Payment HTTPS API
       |
       +--> Event broker
       |
       +--> Scheduled reconciliation job
```

Giả định ban đầu (phải xác minh nếu dùng ở dự án thật):

| Thuộc tính | Dữ liệu giả định |
|---|---|
| Tên ứng dụng | OrderHub |
| Runtime production hiện tại | JDK 11 |
| Runtime đích | JDK 17 trước, JDK 21 sau |
| Build tool | Maven Wrapper và Maven Compiler Plugin |
| Framework | Spring Boot 2.7.x |
| Servlet API | Thế hệ `javax.servlet.*` |
| Data access | JDBC/JPA |
| Database | PostgreSQL |
| Message integration | Broker và client library |
| Outbound network | HTTPS, một đối tác có mTLS |
| Deployment | Container image |
| CI | Unit test, integration test, Docker build |
| Monitoring | Java APM agent |
| Native dependency | Có thể có — chưa xác minh |

**Không suy ra mức hỗ trợ JDK từ tên Spring Boot hoặc từ phiên bản major Maven một mình.** Cần kiểm tra ma trận hỗ trợ chính thức của đúng release và chạy test thực tế. Bài này tập trung vào **cách xác minh**, không phê chuẩn một tổ hợp phiên bản chưa được kiểm chứng.

### 2.1. Mục tiêu migration đã giới hạn

Đợt đầu chỉ muốn:

> Chứng minh OrderHub có thể được build và chạy trên JDK 17 mà không thay đổi public REST/event schema, database schema hoặc phương thức xử lý nghiệp vụ.

Đợt sau mới xét JDK 21, nâng framework và chuyển Javax → Jakarta nếu cần.

Phạm vi hẹp giúp tránh trộn nhiều nguyên nhân:

```text
Bước A: kiểm kê và chuẩn hóa bằng chứng
Bước B: unit/integration tests trên JDK 17
Bước C: nâng các dependency chưa tương thích
Bước D: chạy container JDK 17 trên staging/canary
Bước E: xét JDK 21 + nâng framework theo kế hoạch riêng
```

### 2.2. Câu hỏi phải trả lời

- Source/bytecode hiện được biên dịch cho Java nào?
- Maven process đang chạy dưới JVM nào?
- Tests chạy trên JVM nào?
- Production image và application process thực sự dùng Java nào?
- Dependency nào không tương thích với runtime mới?
- Java agent hoặc plugin có đọc được class file mới không?
- Có dùng JDK internal APIs hoặc reflection bị encapsulation ảnh hưởng không?
- HTTPS/mTLS có hoạt động với truststore và security properties của JDK mục tiêu không?
- Test nào đã chạy trên artifact cuối thay vì source mới build?
- Có rollback được về runtime cũ không nếu chưa đổi data format?

## 3. Ma trận tương thích không phải một bảng “có/không”

Ma trận hữu ích cần ít nhất ba chiều:

1. **Đối tượng kiểm chứng** — component hoặc integration.
2. **Phiên bản/môi trường** — JDK hiện tại, JDK ứng viên, OS/container, build/runtime.
3. **Kết quả có bằng chứng** — PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN, test ID, logs và ngày thực hiện.

Một ô “JDK 21: Yes” không cho biết ai test, test nào, trong môi trường nào và tính đến bản nào. Khi dependency hoặc JDK update thay đổi, kết luận đó có thể không còn giá trị.

### 3.1. Các trạng thái chuẩn

| Trạng thái | Ý nghĩa | Có thể dùng làm gate? |
|---|---|---|
| `PASS` | Kiểm chứng đã thực thi và đạt tiêu chí ghi rõ | Có, nếu bằng chứng còn hiệu lực |
| `FAIL` | Kiểm chứng đã thực thi và không đạt | Block nếu nằm trong phạm vi bắt buộc |
| `BLOCKED` | Chưa thể chạy/hoàn thành do một tiền điều kiện bị chặn | Không |
| `NOT_RUN` | Chưa tiến hành kiểm chứng | Không |
| `UNKNOWN` | Chưa đủ dữ kiện để kết luận hoặc chưa xác định cách kiểm tra | Không |
| `NOT_APPLICABLE` | Không áp dụng, đã giải thích vì sao | Có thể bỏ khỏi denominator nếu hợp lý |

`PASS` phải gắn với **kết quả test và phạm vi đã kiểm chứng**. Nó không có nghĩa mọi hành vi và mọi khách hàng đã được chứng minh tương thích.

### 3.2. Không đánh đồng “vendor claims supported” với “verified”

Có thể dùng hai trường riêng:

```text
Vendor support status: SUPPORTED / UNSUPPORTED / UNKNOWN
Local test status: PASS / FAIL / BLOCKED / NOT_RUN / UNKNOWN
```

Một thư viện có thể được vendor tuyên bố hỗ trợ JDK 21 nhưng ứng dụng của bạn vẫn lỗi do truststore hoặc conflicting dependency. Ngược lại, một bản thư viện không được công bố hỗ trợ có thể tạm chạy qua smoke test, nhưng điều đó **không biến nó thành bản được hỗ trợ cho production**.

### 3.3. Tách bắt buộc và tùy chọn

Ví dụ:

- Kết nối payment HTTPS: **bắt buộc**.
- Export CSV cuối tháng: **bắt buộc**, nhưng chưa được test nếu chưa tới chu kỳ.
- Đo benchmark tối ưu cache: **bổ sung**, không nhất thiết chặn bước runtime-only.
- Chuyển sang virtual threads: **ngoài phạm vi** đợt đầu.

Sự phân loại này giúp tránh thông báo “100% pass” khi những hạng mục quan trọng chưa chạy.

## 4. Bước 1 — Thu thập inventory ban đầu

Trước khi tạo ma trận, cần một danh sách đầy đủ các thành phần có thể ảnh hưởng khả năng nâng JDK.

### 4.1. Các nhóm inventory

| Nhóm | Cần ghi |
|---|---|
| Build | Maven/Gradle version, Wrapper, plugins, daemon/build JVM |
| Compilation | Java compiler version, toolchain, `--release`/source/target |
| Runtime | JDK vendor/update, Java home, OS/architecture, container digest |
| Dependencies | group/artifact/version, direct/transitive, scope, BOM |
| Java EE/Jakarta | Servlet/JPA/JAX-RS/Validation namespace và providers |
| Bytecode tools | ASM, Byte Buddy, JaCoCo, Mockito, enhancement/agents |
| Security | TLS versions, cipher suites, certpath policy, truststore/keystore |
| JVM internals | `sun.*`, `com.sun.*`, reflection, `--add-opens` |
| Native | JNI/JNA libraries, OS ABI, CPU architecture |
| Data integration | Database driver, ORM, message broker, serialization |
| Operations | JVM flags, logging, monitoring, rollout, rollback |
| Testing | Unit, integration, contract, load, canary và tình trạng gần nhất |

### 4.2. Mẫu inventory CSV

```csv
component_id,category,name,observed_version,used_by,environment,owner,evidence_id,notes
CMP-001,runtime,JDK,11.0.x,OrderHub,production,Platform,EVD-001,Update number requires verification
CMP-002,build,Maven,3.x,OrderHub,CI,BuildTeam,EVD-002,Wrapper in repository
CMP-003,framework,Spring Boot,2.7.x,OrderHub,all,AppTeam,EVD-003,Exact patch to record
CMP-004,api,Servlet API,javax generation,OrderHub,production,AppTeam,EVD-004,Container contract
CMP-005,agent,APM Java agent,unknown,OrderHub,production,Observability,,Needs inventory
CMP-006,security,Truststore,custom PKCS12,Outbound TLS,production,Security,EVD-006,Path and CA owner
```

Trong ví dụ, ô evidence trống của APM agent là **khoảng trống**, không phải tín hiệu pass. Khi áp dụng thực tế, nên có quy tắc cấm `PASS` khi thiếu evidence ID.

### 4.3. Thêm thông tin về quyền sở hữu

Một component có thể do nhóm khác quản lý: platform team phụ trách JDK image, security team phụ trách CA truststore, app team phụ trách source, vendor phụ trách APM agent.

Nếu inventory thiếu owner, migration có thể bế tắc khi cần nâng một thành phần không thuộc nhóm dự án.

## 5. Bước 2 — Xác định build JVM, compiler và runtime JVM

Một dự án có thể chạy Maven bằng JDK 17 nhưng compile target Java 11, chạy tests trên JDK 21 và production bằng JDK 11. Không được ghi chỉ một cột “Java Version”.

### 5.1. Trên máy hoặc CI

Linux/macOS:

```bash
java -version
javac -version
echo "$JAVA_HOME"
./mvnw -version
```

Windows PowerShell:

```powershell
java -version
javac -version
$env:JAVA_HOME
.\mvnw.cmd -version
```

Nếu repository không có Maven Wrapper, sử dụng `mvn -version` từ build environment đã kiểm soát.

### 5.2. Runtime của process thật

Trên host/container, `java -version` ở shell có thể khác Java binary đang chạy service. Nếu hệ thống cho phép, quan sát command line, `java.home`, runtime version hoặc process metadata:

```java
public final class RuntimeFingerprint {
    public static void main(String[] args) {
        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.runtime.version=" +
                System.getProperty("java.runtime.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("java.home=" +
                System.getProperty("java.home"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
    }
}
```

Khi chương trình chạy bên trong chính application process, metadata có giá trị hơn việc đọc shell bên ngoài.

### 5.3. Maven Compiler Plugin và release target

Ví dụ cấu hình:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

Cấu hình `release` yêu cầu compiler hỗ trợ tùy chọn và bị ảnh hưởng bởi Maven Compiler Plugin/toolchain. Nó giới hạn source level, class file level và Java SE platform API trong compilation tương ứng.

Nó **không** đảm bảo third-party JARs được compile cho Java 11 hoặc test JVM cũng dùng JDK 11.

### 5.4. Nếu dự án dùng Gradle

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies --configuration runtimeClasspath
```

Trong `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

Ví dụ này có thể dùng javac JDK 17 để tạo class files mục tiêu Java 11. **JVM chạy Gradle daemon có thể vẫn khác compiler toolchain.**

### 5.5. Kết quả đầu ra của bước này

Ghi đầy đủ:

```text
EVD-001:
  environment: CI linux-x64
  build_tool: Maven Wrapper
  build_jvm: JDK 17
  compiler_jdk: JDK 17
  compiler_release: 11
  test_jvm: requires verification
  production_jvm: JDK 11.0.x
  captured_at: <timestamp>
```

Không tự điền `test_jvm = build_jvm` nếu chưa xem Surefire/Failsafe/toolchains và JVM thật chạy test.

## 6. Bước 3 — Chụp dependency graph

### 6.1. Maven

Chạy từ project root:

```bash
./mvnw dependency:tree
```

Có thể lưu output:

```bash
./mvnw dependency:tree -DoutputFile=dependency-tree.txt
```

Tùy plugin/version, output có thể bao gồm scope, selected versions và một số thông tin omitted dependency. Cần chạy với **đúng profiles và modules** mà CI production build dùng.

Để xem một thư viện liên quan:

```bash
./mvnw dependency:tree -Dincludes=net.bytebuddy:byte-buddy
./mvnw dependency:tree -Dincludes=org.ow2.asm:asm
```

### 6.2. Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để phân tích version:

```bash
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
```

Cần xem cả `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, build plugin classpath và artifact đóng gói khi có yêu cầu.

### 6.3. Build graph chưa chắc bằng production classpath

Ví dụ Gradle/Maven đã resolve đúng JDBC driver, nhưng Dockerfile hoặc application server copy một JAR cũ vào shared library directory. Runtime vẫn có thể nạp class sai phiên bản.

Cần quan sát:

```text
Build output
    |
    +--> compile/test classpaths
    |
    +--> packaged JAR/WAR
    |
    +--> container image filesystem
    |
    +--> classloader của process đang chạy
```

Đó là bốn vị trí có thể khác nhau.

### 6.4. Liệt kê nội dung JAR/WAR

```bash
jar tf target/orderhub.jar
```

Đối với WAR:

```bash
jar tf target/orderhub.war
```

Đối với executable JAR do framework đóng gói, dependency có thể nằm dưới các thư mục nested JAR riêng. Cần xem cấu trúc thực tế của packaging plugin.

## 7. Bước 4 — Kiểm tra bytecode và JDK APIs

### 7.1. Class file major version

Dùng:

```bash
javap -verbose \
  -classpath target/classes \
  com.example.orderhub.Main
```

Tìm dòng `major version`. Các mốc thông dụng:

| Java target | Major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

Bytecode major 61 chỉ cho biết class file thuộc target Java 17; nó không khẳng định mọi runtime dependency tương thích JDK 17 hoặc code không sử dụng dynamic reflection.

### 7.2. Quét phụ thuộc tới JDK internals

Với JDK có `jdeps`:

```bash
jdeps --jdk-internals target/orderhub.jar
```

Khi artifact có dependencies nằm ngoài JAR:

```bash
jdeps --jdk-internals \
  --class-path "lib/*" \
  target/orderhub.jar
```

Một số ứng dụng dùng fat/executable JAR có nested dependencies; `jdeps` trên file JAR ngoài không nhất thiết quét được tất cả nested JARs theo cách mong muốn. Cần giải nén/thu thập classpaths thích hợp cho phân tích.

### 7.3. Giới hạn của `jdeps`

Nó phân tích tham chiếu tĩnh, không bảo đảm tìm hết:

- `Class.forName("sun.misc...")` bằng string.
- Reflection gọi private JDK members.
- Native/JNI.
- ServiceLoader providers nạp động.
- Annotation-driven integration.
- Script/configuration sinh class names.
- Instrumentation của Java agents.

Vì vậy `jdeps` không phát hiện internal APIs **không có nghĩa chắc chắn tương thích**.

### 7.4. Ghi phát hiện dưới dạng inventory row

```text
component_id: CMP-009
category: jdk-internals
finding: Static dependency to internal JDK API
status: FAIL
evidence_id: EVD-009
severity: HIGH
owner: AppTeam
next_action: Replace with supported Java SE API
```

Chỉ dùng `FAIL` nếu một tiêu chí cụ thể đã được kiểm và không đạt; nếu chưa quét được artifact thì ghi `BLOCKED` hoặc `NOT_RUN`.

## 8. Bước 5 — Kiểm tra API Java EE/Jakarta

Đổi runtime JDK **không đồng nghĩa** đổi Java EE sang Jakarta EE.

### 8.1. Phân biệt namespace

- Java EE và Jakarta EE 8 dùng nhiều APIs trong namespace `javax.*`.
- Jakarta EE 9 trở lên chuyển các API thuộc phạm vi Jakarta EE sang `jakarta.*`.
- Các Java SE packages như `javax.net.ssl`, `javax.crypto`, `javax.sql`, `javax.xml.parsers` **không** đổi tương ứng.

Ví dụ:

```java
// Servlet thế hệ Java EE/Jakarta EE 8:
import javax.servlet.Filter;

// Jakarta Servlet thế hệ mới:
import jakarta.servlet.Filter;
```

Hai interfaces là hai binary types khác nhau.

### 8.2. Các câu hỏi dành cho matrix

| Câu hỏi | Nếu chưa rõ, ghi gì? |
|---|---|
| Container đích dùng Servlet API level nào? | `UNKNOWN` |
| Framework version hỗ trợ Jakarta EE generation nào? | `UNKNOWN` |
| Có filters/listeners compiled với Javax không? | `NOT_RUN` cho bài kiểm tra |
| Có JPA entities với `javax.persistence.*` không? | Inventory finding |
| Có REST/Validation providers thuộc API generation cũ không? | Dependency gap |
| WAR đã triển khai thành công trên container đích chưa? | `NOT_RUN` nếu chưa thử |

Đối với OrderHub giả định, migration JDK 11 →17 có thể được kiểm riêng với việc nâng Spring Boot 2.x →3.x. Nếu kế hoạch thực tế buộc nâng đồng thời, phải phân loại **hai nhóm rủi ro độc lập**.

## 9. Bước 6 — Kiểm tra JSSE/TLS và truststore

Một JDK mới có thể cập nhật disabled algorithms, certificate path constraints hoặc CA truststore. Một runtime migration chỉ được xác nhận khi các kết nối bảo mật trọng yếu đã được thử.

### 9.1. Inventory kết nối bảo mật

```csv
endpoint_id,host_role,requires_tls,mtls,trust_material_owner,status,evidence_id
TLS-001,Payment HTTPS API,yes,yes,SecurityTeam,NOT_RUN,
TLS-002,Internal inventory API,yes,no,PlatformTeam,NOT_RUN,
TLS-003,Message broker,yes,unknown,MessagingTeam,UNKNOWN,
```

Với mTLS cần xác minh cả:

- Client truststore tin server certificate chain.
- Client keystore có private key và certificate dùng xác thực client.
- Server tin client CA.
- Hostname/SNI, validity và EKU đúng.

### 9.2. Chụp policy của JDK

Ví dụ:

```java
import java.security.Security;

public final class SecurityReport {
    public static void main(String[] args) {
        for (String name : new String[] {
                "jdk.tls.disabledAlgorithms",
                "jdk.certpath.disabledAlgorithms"
        }) {
            System.out.println(name + " = " +
                    Security.getProperty(name));
        }
    }
}
```

Không in password, private key hoặc secrets. Có thể chạy từ JDK mục tiêu, so sánh policy với JDK hiện tại và test TLS endpoint.

### 9.3. JSSE debug trong môi trường kiểm soát

```bash
java -Djavax.net.debug=ssl,handshake -jar orderhub.jar
```

Đây là ví dụ câu lệnh chẩn đoán; log có thể chứa thông tin nhạy cảm và rất nhiều dữ liệu. Không bật lâu dài trên production.

### 9.4. Phân loại lỗi theo chứng cứ

| Lỗi | Giả thuyết cần kiểm |
|---|---|
| `PKIX path building failed` | Trust chain/trust anchor thiếu hoặc certpath constraints |
| `Algorithm constraints check failed` | Key/signature/disabled algorithms |
| `No appropriate protocol` | TLS version/cipher không hợp |
| `No subject alternative DNS name matching` | Hostname/SAN mismatch |
| `Received fatal alert: bad_certificate` | Peer từ chối certificate, có thể mTLS |

Không được sửa lỗi bằng cách tắt TrustManager hoặc hostname verification. **Một kết nối chỉ được chấp nhận khi vừa hoạt động vừa xác thực đúng danh tính và policy.**

## 10. Bước 7 — Kiểm tra agent, bytecode tools và native libraries

JDK mới không chỉ tác động ứng dụng; các thành phần đọc bytecode có thể lỗi dù JVM hỗ trợ classfile mới.

### 10.1. Nhóm cần kiểm kê

- Java APM/tracing/monitoring agents.
- Coverage agent như JaCoCo.
- Mocking/proxy frameworks và Byte Buddy.
- ASM readers trong build plugins.
- ORM bytecode enhancement.
- Annotation processors.
- JNI/JNA/native drivers.
- Profilers, obfuscators hoặc security agents.

Một `Unsupported class file major version 65` có thể đến từ **parser ASM cũ**, trong khi JVM JDK 21 vẫn chạy được classfile major 65.

### 10.2. Matrix phải có riêng plugin/agent

```text
Row: Monitoring Java agent
Current version: unknown
Target: JDK 17 / JDK 21
Vendor support: UNKNOWN
Local startup test: NOT_RUN
Instrumentation correctness: NOT_RUN
Owner: Observability
Decision: BLOCKED until artifact/version identified
```

**Application dependencies và Gradle/Maven plugin dependencies có classpaths khác nhau**. Nâng ASM trong runtime dependencies không chắc sửa parser đã được shade trong một plugin/agent.

### 10.3. Native integration

Đối với `.so`, `.dll`, `.dylib`, cần ghi:

- OS và architecture.
- JDK/ABI support do vendor công bố.
- Native library file version/digest.
- Native load path.
- Test bắt buộc qua code path sử dụng JNI.
- Ảnh hưởng của container base image/OS library.

Một smoke test không dùng native function không đủ chứng minh compatibility.

## 11. Bước 8 — Thiết kế tập kiểm thử theo tầng

Một ma trận tốt ghi rõ **test suite** được dùng để xác nhận từng phần.

### 11.1. Các loại kiểm thử

| Test ID | Lớp kiểm thử | Chức năng |
|---|---|---|
| TST-001 | Compile | Project và annotation processors biên dịch |
| TST-002 | Unit | Business logic và edge cases |
| TST-003 | Integration | Database, broker và HTTP partners |
| TST-004 | Contract | REST/event/serialization backward compatibility |
| TST-005 | Binary | Consumer JAR cũ chạy với provider mới |
| TST-006 | Security | TLS, mTLS, truststore, algorithm policies |
| TST-007 | Packaging | JAR/WAR/container image và launcher |
| TST-008 | Agent | Tracing, metrics, coverage/instrumentation |
| TST-009 | Native | JNI/JNA/OS integration |
| TST-010 | Load/performance | Throughput, p95/p99, heap, GC, pool waits |
| TST-011 | Rollback | Deploy artifact cũ và xác minh dữ liệu tương thích |
| TST-012 | Scheduled paths | Batch/cron, retry, recovery/timeout |

Đây là các ID minh họa để dùng thống nhất trong report.

### 11.2. Baseline phải có trước candidate

Nếu JDK 17 fail TST-003, cần biết JDK 11 baseline đã pass hay chưa. Một lỗi database credential xuất hiện ở cả hai môi trường không nên được báo cáo như một Java 17 regression.

Mô hình:

```text
Same source + same dependencies + same test fixture
          |
          +--> JDK 11 baseline
          |
          +--> JDK 17 candidate
          |
          +--> Compare failure and metrics
```

Điều kiện “same” có thể không hoàn toàn đạt nếu JDK cũ không hỗ trợ build plugin mới; khi đó ghi **đúng khác biệt** và nguy cơ gây nhiễu khi so sánh.

### 11.3. Kiểm thử bằng artifact cuối

Test unit của source là cần thiết, nhưng để xác nhận deployment phải kiểm tra:

- Exact JAR/WAR được phát hành.
- Container image có JDK update tương ứng.
- Startup flags, truststores và config mounts.
- Application server/launcher classloader.
- Native libraries và agent được nhúng hoặc mount.
- Credentials/secret handling theo môi trường.

Một artifact được kiểm trong CI có thể khác container đã deploy nếu Dockerfile copy JAR cũ hoặc base image bị đổi.

## 12. Bước 9 — Tạo ma trận tương thích ban đầu

Định dạng CSV dài (*long-form*) dễ lọc, nhập vào Sheets/Excel hoặc phân tích bằng script.

### 12.1. Schema đề xuất

| Cột | Ý nghĩa |
|---|---|
| `row_id` | ID bất biến của một phép kiểm |
| `component_id` | Liên kết inventory |
| `component` | Tên thành phần |
| `environment` | local/CI/staging/production |
| `jdk` | JDK version/vendor thực tế |
| `scenario` | Hành vi được kiểm |
| `expected` | Tiêu chí đạt |
| `status` | PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN |
| `evidence_id` | Link tới log/report/artifact |
| `tested_at` | Thời điểm kiểm |
| `owner` | Người/nhóm chịu trách nhiệm |
| `risk_id` | Liên kết risk register |
| `next_action` | Hành động tiếp theo |

Có thể bổ sung `build_id`, `git_sha`, `artifact_digest`, `os_arch`, `framework_version` và `support_claim` nếu dự án phức tạp.

### 12.2. CSV ví dụ ban đầu

```csv
row_id,component_id,component,environment,jdk,scenario,expected,status,evidence_id,tested_at,owner,risk_id,next_action
MAT-001,CMP-001,OrderHub,CI,JDK 11,unit tests,all tests pass,PASS,EVD-101,example-date,AppTeam,,retain baseline
MAT-002,CMP-001,OrderHub,CI,JDK 17,unit tests,all tests pass,PASS,EVD-102,example-date,AppTeam,,run integration
MAT-003,CMP-001,OrderHub,staging,JDK 17,production image smoke,health and core flows,NOT_RUN,, ,Platform,RISK-01,deploy candidate
MAT-004,CMP-005,APM agent,staging,JDK 17,tracing instrumentation,critical spans present,BLOCKED,, ,Observability,RISK-02,identify agent version
MAT-005,CMP-006,Payment mTLS,staging,JDK 17,mTLS handshake,server and client validated,NOT_RUN,, ,Security,RISK-03,prepare trust material
MAT-006,CMP-001,OrderHub,CI,JDK 21,compile and tests,all required tests pass,NOT_RUN,, ,AppTeam,RISK-04,plan later phase
```

**Các trạng thái `PASS` trong bảng là giả định để minh họa cách ghi**, không phải kết quả thực thi. Dòng đang `NOT_RUN` hoặc `BLOCKED` phải để trống evidence kết quả cho đến khi có chứng cứ.

Đối với file CSV thật, nên thống nhất cách biểu diễn timestamp (ISO 8601), không ghi chuỗi `" "` làm giá trị trống và dùng parser CSV chuẩn khi trường chứa dấu phẩy.

### 12.3. Pivot view để người duyệt dễ nhìn

Có thể biểu diễn dữ liệu trên thành bảng tổng hợp:

| Hạng mục | JDK 11 baseline | JDK 17 candidate | JDK 21 candidate |
|---|---|---|---|
| Compile | PASS (ví dụ) | PASS (ví dụ) | NOT_RUN |
| Unit tests | PASS (ví dụ) | PASS (ví dụ) | NOT_RUN |
| Integration DB | PASS (ví dụ) | NOT_RUN | NOT_RUN |
| Payment mTLS | PASS (ví dụ) | NOT_RUN | NOT_RUN |
| APM agent | PASS (ví dụ) | BLOCKED | UNKNOWN |
| Container smoke | PASS (ví dụ) | NOT_RUN | NOT_RUN |
| Performance | Baseline available | NOT_RUN | NOT_RUN |
| Rollback rehearsal | NOT_APPLICABLE | NOT_RUN | NOT_RUN |

Mọi `PASS` ở bảng này là **tình huống giả định**. Trong báo cáo thật, mỗi ô cần truy được về record long-form có `evidence_id`.

### 12.4. Vì sao cần cả long-form và pivot?

- Long-form: hỗ trợ audit, filter, automation và dữ liệu có nhiều môi trường.
- Pivot: giúp stakeholder nhìn nhanh gap theo JDK.
- Risk register: cho biết ai đang xử lý blocker và khi nào kiểm lại.

Không gộp tất cả vào một ô chứa paragraph dài vì khó truy vết và cập nhật.

## 13. Bước 10 — Ghi bằng chứng theo quy ước nhất quán

Một kết quả test phải đi cùng **metadata xác định nó đã kiểm cái gì**.

Ví dụ:

```yaml
evidence_id: EVD-102
scenario_id: MAT-002
environment: ci-linux-x64
application_commit: "<git-sha>"
application_artifact: "orderhub.jar"
artifact_sha256: "<digest>"
jdk_vendor: "<vendor>"
jdk_version: "17.0.x"
build_tool: "Maven Wrapper"
command: "./mvnw -B test"
started_at: "<ISO-8601>"
completed_at: "<ISO-8601>"
exit_code: 0
result: PASS
log_location: "evidence/ci-jdk17-unit-tests.log"
notes: "Example only; replace with real execution data"
```

Trường `result: PASS` là **giá trị giả định trong mẫu**, không thể được sử dụng nguyên văn nếu chưa thực thi.

### 13.1. Evidence ID có thể được dẫn trong báo cáo

Ví dụ:

```text
MAT-002 -> EVD-102
MAT-005 -> no evidence yet
RISK-03 -> MAT-005
```

Người đọc có thể từ báo cáo → matrix → evidence. Một finding không có nguồn nên mang trạng thái `UNKNOWN` hoặc ghi là **đánh giá sơ bộ**.

### 13.2. Phạm vi bằng chứng có hạn

Ví dụ `./mvnw test` exit 0 không tự chứng minh:

- Integration tests đã chạy nếu test class không được phát hiện.
- Test thực thi trên JVM mong muốn.
- Test chạy với production truststore.
- Native code hoặc mTLS đã được gọi.
- Artifact production đã được deploy.

Khi báo cáo, cần ghi **chính xác những test suites đã được khám phá và chạy** cùng runtime của test.

### 13.3. Bảo vệ dữ liệu

Không đưa private key, truststore password, API tokens, access keys, user personal data hoặc production credentials vào evidence. Logs cần redaction và quyền truy cập phù hợp.

## 14. Bước 11 — Đánh giá rủi ro và khoảng trống

Không nên xếp hạng chỉ dựa trên số ô FAIL. Một `FAIL` về critical payment path có thể quan trọng hơn hàng chục test tùy chọn `NOT_RUN`.

### 14.1. Mô hình rủi ro đơn giản

Có thể dùng hai thang 1–5:

- `Impact`: mức độ nghiêm trọng nếu lỗi xảy ra.
- `Likelihood`: xác suất hợp lý dựa trên evidence/unknowns.

```text
Risk score = Impact × Likelihood
```

Ví dụ:

| Score | Nhãn minh họa | Hành động |
|---|---|---|
| 1–4 | Low | Theo dõi, có thể đưa vào sprint tiếp |
| 5–9 | Medium | Có kế hoạch xử lý và test |
| 10–16 | High | Cần xử lý trước canary rộng |
| 17–25 | Critical | Không phát hành khi chưa có quyết định phê duyệt |

Các ngưỡng là **quy ước ví dụ**, không phải chuẩn bắt buộc. Hãy tuân thủ risk framework của tổ chức nếu có.

### 14.2. Risk register mẫu

| Risk ID | Vấn đề | Impact | Likelihood | Score | Owner | Phương án |
|---|---|---:|---:|---:|---|---|
| RISK-01 | Container JDK 17 chưa qua smoke test | 4 | 3 | 12 | Platform | Deploy staging artifact cuối |
| RISK-02 | Chưa xác định version của APM agent | 4 | 4 | 16 | Observability | Inventory agent, xác minh vendor support và instrumentation |
| RISK-03 | Payment mTLS chưa kiểm trên JDK 17 | 5 | 3 | 15 | Security | Test truststore/keystore và partner endpoint |
| RISK-04 | JDK 21 chưa nằm trong test matrix | 3 | 3 | 9 | App | Đưa vào giai đoạn sau, không công bố hỗ trợ |
| RISK-05 | Rollback container chưa diễn tập | 4 | 3 | 12 | SRE | Rehearsal trên staging và data-compat check |

Đây là bảng giả định. **Likelihood không nên được coi như số đo thống kê** nếu chưa có dữ liệu; nó là đánh giá định tính có owner và thời điểm cần xem lại.

### 14.3. Phân biệt blocker và risk chưa kiểm

- **Blocker kỹ thuật**: test đã fail hoặc tiền điều kiện bắt buộc chưa đạt.
- **Coverage gap**: test chưa chạy hoặc không có môi trường.
- **Policy blocker**: vendor/runtime không được phép theo chính sách.
- **Operational risk**: rollback, monitoring hoặc certificate ownership chưa sẵn sàng.

Những nhóm này cần cách xử lý khác nhau, không quy tất cả thành “dependency lỗi”.

## 15. Bước 12 — Tính mức độ hoàn thành không gây hiểu nhầm

Đừng báo cáo “95% compatible” chỉ vì 95% ô có màu xanh nếu còn một endpoint payment chưa được kiểm.

### 15.1. Coverage và pass rate là hai số khác nhau

Ví dụ một tập 20 checks bắt buộc:

```text
PASS:        12
FAIL:         2
BLOCKED:      3
NOT_RUN:      3
```

Coverage thực thi:

\[
\text{Executed coverage} = \frac{12+2}{20} = 70\%
\]

Pass rate trong những checks đã chạy:

\[
\text{Pass rate among executed} = \frac{12}{12+2} \approx 85.7\%
\]

Nếu chỉ báo cáo 85,7% sẽ làm người đọc tưởng hệ thống đã được kiểm gần hết, trong khi 30% checks bắt buộc vẫn chưa chạy.

### 15.2. Báo cáo tiêu chí gate riêng

Ví dụ chính sách rollout:

```text
Required:
- All critical functional and security checks PASS.
- No unresolved high-severity FAIL.
- No BLOCKED test on mandatory production path.
- Production image smoke PASS.
- Rollback rehearsal PASS.
- SLO threshold and monitoring defined.
```

Một đợt migration có thể có 90% test coverage nhưng **chưa sẵn sàng canary** vì mTLS chưa được kiểm. Đây là kết luận hợp lý nếu phạm vi còn thiếu là critical.

### 15.3. Khi nhiều test không áp dụng

`NOT_APPLICABLE` chỉ được loại khỏi denominator khi có lý do, ví dụ một CLI tool không dùng Servlet container. Không dùng `NOT_APPLICABLE` để loại những bài test khó hoặc đã fail.

## 16. Bước 13 — Viết báo cáo hiện trạng

Báo cáo nên giúp người ra quyết định hiểu **mức độ sẵn sàng, bằng chứng, gap và hành động tiếp theo** mà không cần đọc toàn bộ dependency tree.

Cấu trúc phù hợp:

1. Executive summary.
2. Scope và mục tiêu migration.
3. Baseline hiện tại.
4. Thành phần, JDK và dependency inventory.
5. Compatibility matrix summary.
6. Findings/risk register.
7. Verification evidence và limitations.
8. Đề xuất xử lý theo thứ tự.
9. Rollout/rollback readiness.
10. Decision requested và owners.

### 16.1. Mẫu báo cáo thực hành: OrderHub

> **Lưu ý:** toàn bộ nội dung dưới đây là báo cáo **minh họa**. Không xem số liệu là kết quả kiểm thử đã thực hiện.

#### A. Thông tin chung

```text
Project: OrderHub (fictional)
Assessment date: <date>
Current runtime: JDK 11
Target candidate: JDK 17
Future target: JDK 21 (out of current release scope)
Build: Maven Wrapper
Deployment: container
Owners: Application / Platform / Security / SRE
Assessment version: v0.1
```

#### B. Tóm tắt điều hành

Dự án đã có baseline Java 11 ở mức giả định và một phần kiểm thử JDK 17. Hiện **chưa đủ bằng chứng để phê duyệt canary production JDK 17**, vì còn chưa kiểm tra artifact container cuối, payment mTLS, APM agent và diễn tập rollback. JDK 21 chưa thuộc phạm vi xác nhận của giai đoạn này.

Không công bố “JDK 17 compatible” khi các kiểm tra critical chưa hoàn tất. Đề xuất hoàn thiện kiểm kê và verification trước khi chuyển traffic thực.

#### C. Hiện trạng môi trường

| Thành phần | Baseline minh họa | Candidate | Đánh giá |
|---|---|---|---|
| Production JDK | 11 | 17 | Chưa rollout |
| Compiler release | 11 | 11 | Giữ bytecode/API target |
| Unit tests | PASS giả định | PASS giả định | Chưa đủ chứng minh runtime |
| Database integration | PASS giả định | NOT_RUN | Gap |
| TLS/mTLS | PASS giả định | NOT_RUN | Gap quan trọng |
| APM instrumentation | PASS giả định | BLOCKED | Cần xác định agent |
| Container startup | PASS giả định | NOT_RUN | Gap |
| Rollback rehearsal | N/A | NOT_RUN | Gap vận hành |

#### D. Findings quan trọng

- **F-01:** Chưa có smoke test trên image JDK 17 cuối; chưa thể xác nhận startup/config/packaging.
- **F-02:** APM agent chưa được inventory về version và vendor support.
- **F-03:** Kết nối mTLS với payment gateway chưa có evidence từ JSSE JDK 17 và truststore production.
- **F-04:** Chưa có test rollback image sau khi một candidate đã xử lý message.
- **F-05:** JDK 21 chưa có bằng chứng test; không đưa vào tuyên bố hỗ trợ.

#### E. Khuyến nghị xử lý

| Ưu tiên | Hành động | Owner | Điều kiện hoàn thành |
|---|---|---|---|
| P0 | Xác định agent version và test instrumentation | Observability | Có log và trace evidence với candidate |
| P0 | Chạy payment mTLS trên staging tương đương production | Security + App | Certificate validation pass và negative test fail đúng |
| P0 | Build/deploy exact JDK 17 image để smoke/integration | Platform + App | Critical flows và health pass |
| P1 | Diễn tập rollback container + xử lý in-flight events | SRE | Runbook được test |
| P1 | Thu baseline p95/p99, GC, DB pool waiters | SRE | Có ngưỡng so sánh |
| P2 | Lập matrix JDK 21 và nâng framework theo phase | Tech Lead | Lộ trình riêng được phê duyệt |

#### F. Quyết định đề xuất

```text
Decision: HOLD production canary
Reason: Mandatory mTLS, APM and image smoke evidence missing
Next gate: Re-evaluate when P0 checks PASS and rollback path is ready
JDK 21 declaration: NOT ASSESSED
```

Đây là một kết luận **dựa trên tình huống minh họa**, không phải kết luận về một dự án thật.

## 17. Quy tắc ghi nhận hiện trạng khách quan

### 17.1. Không viết “đã tương thích” khi chưa có test

Một lời khẳng định cần trả lời:

- Ai thực hiện?
- Khi nào?
- Artifact hash nào?
- Runtime vendor/update nào?
- Lệnh/test suite nào?
- Tiêu chí đạt nào?
- Có giới hạn phạm vi không?

Nếu thiếu một số thông tin, có thể ghi nhận test là **đã chạy nhưng evidence chưa đủ chuẩn**, thay vì xóa hoặc sửa kết quả gốc.

### 17.2. Nhận định phải khác bằng chứng

Ví dụ:

```text
Evidence:
  Test suite TST-003 failed with PKIX path building failed.

Hypothesis:
  Candidate container may use a truststore missing the partner CA.

Not yet proven:
  Whether missing CA is the root cause, versus missing intermediate
  or algorithm constraints.
```

Lập luận tốt là **không nâng giả thuyết thành root cause** trước khi phân tích.

### 17.3. Ghi rõ điều chưa kiểm

Bài test chưa có môi trường payment sandbox được ghi `BLOCKED`, không phải “pass vì vendor hỗ trợ TLS 1.2”.

Một hàng khác chưa có người chạy thì dùng `NOT_RUN`. Phân biệt để quản lý kế hoạch.

## 18. Triển khai ma trận bằng Maven CI

Đối với Maven project, có thể tạo CI matrix nhiều JDK với **cùng source commit và dependency configuration**.

Ví dụ lệnh chạy trong các CI runners khác nhau:

```bash
./mvnw -B -version
./mvnw -B clean verify
```

Ở mỗi runner, lưu:

- `java -version` và `./mvnw -version`.
- Maven plugin versions.
- Compiler release và test runtime.
- Exit code và discovered tests.
- Report Surefire/Failsafe nếu có.
- Artifact digest.

Không giả định `verify` tự chạy integration tests nếu project chưa cấu hình Failsafe hoặc integration-test goals đúng.

### 18.1. Bước baseline không nên thay quá nhiều biến

Ví dụ đợt test:

```text
CI Job A:
  Runtime JVM: JDK 11
  Source/dependencies: baseline
  Suites: unit + integration

CI Job B:
  Runtime JVM: JDK 17
  Source/dependencies: same commit/config
  Suites: unit + integration
```

Nếu phải đổi compiler/plugin để build được trên JDK 17, ghi rõ đó là **biến thay đổi bổ sung**, không tuyên bố test chỉ khác runtime.

### 18.2. `mvn -version` không đủ

Maven process có thể dùng một JVM, còn compiler/test fork dùng toolchain khác. Nếu dự án cấu hình Maven Toolchains, Compiler Plugin, Surefire/Failsafe `jvm` hoặc plugin runtime, cần ghi JDK của từng vai trò.

## 19. Triển khai ma trận bằng Gradle CI

Ví dụ Groovy DSL khi cần compiler target Java 11:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

CI có thể chạy:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
```

Để test Java 11 runtime thay vì toolchain default, có thể cấu hình `Test.javaLauncher`:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Nếu muốn một matrix test JDK 11/17/21, có thể để CI truyền tham số và đặt launcher phù hợp cho mỗi job, hoặc tạo các test tasks tường minh. Quan trọng là **không cho hai jobs vô tình chạy cùng một JVM rồi ghi kết quả ở hai cột khác nhau**.

### 19.1. Dependency graph theo configuration

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Nếu lỗi phát sinh ở Gradle plugin chứ không phải code ứng dụng, các configurations này chưa phản ánh đầy đủ plugin classpath. Cần phân tích Gradle wrapper/plugin versions riêng.

## 20. Đo hiệu năng ở runtime mới

Compatibility không chỉ là hết lỗi linkage. JDK migration có thể thay GC ergonomics, CPU scheduling, TLS overhead, charset defaults, compiler/JIT behavior và native interactions.

### 20.1. Baseline metrics

Thu thập từ môi trường kiểm soát:

- Request throughput.
- p50/p95/p99 latency.
- HTTP error rate.
- CPU usage/throttling.
- Heap committed/used và allocation rate.
- GC pauses/frequency.
- Thread/pool queue depth.
- Database pool waiters/timeouts.
- Message consumer lag.
- Retry rate và downstream errors.

### 20.2. So sánh đúng điều kiện

Không so sánh test JDK 11 với 5.000 req/s và JDK 17 với 500 req/s rồi kết luận JDK 17 có latency tốt hơn. Cần kiểm soát traffic mix, instance size, DB capacity, payload, load shape và warmup.

### 20.3. Ghi khoảng trống đúng cách

Nếu chưa có load test, `Performance JDK 17: NOT_RUN`. Không suy từ unit test pass hoặc một lần chạy local rằng performance production đạt.

### 20.4. Thiết kế performance gate

Ví dụ **ngưỡng minh họa**:

```text
Required:
- No critical functional failures.
- p95 latency increase <= 10% against comparable baseline.
- No sustained increase in error rate.
- No database pool saturation.
- No unexplained GC or memory regression.
```

Các con số phải được điều chỉnh theo SLO thật; không coi 10% là chuẩn bắt buộc của Java migration.

## 21. Kiểm thử hồi quy nhị phân với consumer artifact cũ

Đối với một library được nhiều ứng dụng dùng, **recompile toàn bộ consumer source** không chứng minh library mới tương thích với những consumer JAR đã phát hành.

Mô hình:

```text
Provider v1.jar ----> Compile consumer-old.jar once
                              |
                              v
                        Freeze bytes/hash
                              |
                    +---------+---------+
                    |                   |
                    v                   v
          Run with provider v1   Run with provider v2
             (control)             (candidate)
```

Nếu provider v2 xóa method/constructor hoặc đổi descriptor, consumer binary cũ có thể lỗi `NoSuchMethodError`.

### 21.1. Thêm hàng binary compatibility

```text
MAT-020:
  component: shared-order-api
  scenario: Precompiled consumer v1 running with provider v2
  expected: No linkage errors; contract assertions pass
  status: NOT_RUN
  evidence: none
  owner: LibraryTeam
```

Test này cần có nếu hệ thống tuyên bố provider JAR mới là **drop-in replacement**.

## 22. Đánh giá rollback và tính tương thích dữ liệu

Một ma trận chỉ chứa unit tests có thể bỏ sót rủi ro quan trọng: nếu ứng dụng mới ghi dữ liệu mà bản cũ không đọc được, **rollback runtime không còn an toàn**.

### 22.1. Cần kiểm tra hai chiều

| Producer | Consumer | Điều cần chứng minh |
|---|---|---|
| Old | Old | Baseline |
| Old | New | Bản mới đọc được data cũ |
| New | New | Bản mới hoạt động |
| New | Old | Rollback còn đọc được data mới |

Với JSON/event/database schema, nếu dòng `New → Old` fail, phải có compatibility window, adapter hoặc kế hoạch roll-forward khác; không hứa rollback JAR trong vài phút.

### 22.2. Ghi một row rollback

```text
MAT-030:
  component: OrderHub deployment
  scenario: JDK17 candidate -> restore JDK11 image
  expected:
    - old image starts
    - existing messages remain processable
    - no data/schema incompatibility
  status: NOT_RUN
  owner: SRE
  risk_id: RISK-05
```

### 22.3. Immutable artifacts

Rollback phải dựa trên image digest, release artifact và configuration snapshot đã kiểm chứng. Container tag `latest` bị thay đổi không phải nguồn đáng tin để khôi phục chính xác.

## 23. Bài tập thực hành từng bước

Hãy sử dụng **một dự án Java bạn có quyền kiểm tra**. Nếu chưa có dự án, dùng kịch bản OrderHub giả định để hoàn thành bản thiết kế ma trận; khi đó phải ghi mọi kết quả chưa được chạy là `NOT_RUN`/`UNKNOWN`.

### Nhiệm vụ A — Viết phạm vi

Ghi:

```text
Project:
Application version:
Current JDK:
Target JDK:
Migration type: runtime-only / compiler / framework / full
Build tool:
Deployment type:
Critical business flows:
Excluded changes:
Owner:
```

**Kết quả:** một đoạn scope có thể được nhóm kỹ thuật và vận hành cùng xác nhận.

### Nhiệm vụ B — Thu thập environment fingerprint

Dùng các lệnh Maven hoặc Gradle tương ứng và quan sát runtime process. Lưu evidence gắn timestamp.

**Kết quả:** ít nhất một row cho build JVM, compiler JDK, test JVM và production JVM.

### Nhiệm vụ C — Thu thập dependencies

Lưu dependency tree, application server/container versions, agents, native libraries và framework integration.

**Kết quả:** inventory có component ID, version và owner. Thành phần chưa biết ghi `UNKNOWN`.

### Nhiệm vụ D — Chạy baseline

Thực thi test suites hiện có trên JDK hiện tại. Không tự tạo ra con số pass nếu không chạy được.

**Kết quả:** evidence cho baseline, hoặc nêu lý do `BLOCKED`/`NOT_RUN`.

### Nhiệm vụ E — Chạy candidate

Dùng JDK mục tiêu, giữ các biến khác cố định nếu có thể. Thu log/exit codes/test reports.

**Kết quả:** cùng tập test IDs với candidate results.

### Nhiệm vụ F — Đối chiếu artifact và security

Kiểm tra packaged JAR/WAR, bytecode major, `jdeps`, Java agents, TLS truststores và các critical integration points.

**Kết quả:** các hàng matrix và findings có evidence.

### Nhiệm vụ G — Lập risk register

Với mỗi lỗi/gap critical, ghi:

```text
Risk ID:
Finding:
Evidence or uncertainty:
Impact:
Likelihood:
Owner:
Mitigation:
Verification plan:
Due date:
```

**Kết quả:** danh sách được ưu tiên, không chỉ một tập log.

### Nhiệm vụ H — Viết báo cáo hiện trạng

Viết summary, matrix summary, blockers, unknowns, proposed next step, rollback readiness và decision requested.

**Kết quả:** báo cáo mà người không trực tiếp chạy lệnh vẫn hiểu được lý do cho phép hoặc chưa cho phép migration.

## 24. Mẫu bảng điền trực tiếp

Sao chép mẫu dưới đây vào tài liệu riêng và điền bằng kết quả của dự án thật.

| Test ID | Hạng mục | Baseline JDK | Candidate JDK | Môi trường | Trạng thái | Evidence | Owner |
|---|---|---|---|---|---|---|---|
| TST-001 | Build và compile |  |  | CI | UNKNOWN |  |  |
| TST-002 | Unit tests |  |  | CI | NOT_RUN |  |  |
| TST-003 | DB integration |  |  | staging | NOT_RUN |  |  |
| TST-004 | REST/event contract |  |  | staging | NOT_RUN |  |  |
| TST-005 | Consumer binary |  |  | test | NOT_RUN |  |  |
| TST-006 | TLS/mTLS |  |  | staging | NOT_RUN |  |  |
| TST-007 | Package/container |  |  | staging | NOT_RUN |  |  |
| TST-008 | Java agents |  |  | staging | NOT_RUN |  |  |
| TST-009 | JNI/native |  |  | test | UNKNOWN |  |  |
| TST-010 | Performance |  |  | load test | NOT_RUN |  |  |
| TST-011 | Rollback |  |  | staging | NOT_RUN |  |  |
| TST-012 | Scheduled jobs |  |  | staging | NOT_RUN |  |  |

Ở cột `Trạng thái`, nên phân biệt **baseline result** và **candidate result** bằng hai cột riêng trong bảng thật nếu mỗi bên có thể PASS/FAIL độc lập. Bảng rút gọn chỉ là điểm khởi đầu để điền.

## 25. Những lỗi thường gặp khi lập ma trận

### 25.1. Chỉ liệt kê các JDK version

Ví dụ:

```text
Java 11: OK
Java 17: OK
Java 21: OK
```

Không có môi trường, test, version dependency hoặc evidence. Không đủ làm báo cáo chấp thuận production.

### 25.2. Dùng vendor support như kết quả local test

Vendor công bố hỗ trợ Java 21 không có nghĩa custom agent config, truststore hoặc app business flow đã đạt. Tách hai cột.

### 25.3. Gộp build JVM và runtime JVM

`mvn -version` báo JDK 17 không chứng minh Docker image production dùng JDK 17; `gradlew --version` không tự chứng minh compiler toolchain version.

### 25.4. Recompile consumer khi muốn test binary compatibility

Nếu không giữ compiled consumer JAR từ provider cũ, phép thử có thể bỏ sót ABI break.

### 25.5. Không ghi `NOT_RUN` hoặc `BLOCKED`

Để ô trắng dễ khiến người duyệt hiểu nhầm “không có vấn đề”. Dùng trạng thái có nghĩa rõ và lý do thiếu evidence.

### 25.6. Không phân biệt fail do migration và fail baseline

Một downstream outage xuất hiện ở cả JDK cũ và mới không tự chứng minh JDK mới lỗi. Cần control run và cùng điều kiện test.

### 25.7. Ghi pass từ máy developer nhưng báo cáo production-ready

Máy developer có CA store, OS và proxy khác production. Với TLS/JPMS/JNI, điều này đặc biệt nguy hiểm.

### 25.8. Chỉ test startup

Ứng dụng có thể startup nhưng fail ở JPA mapping, message deserialization, mTLS request, scheduled job hoặc shutdown.

### 25.9. Tính tỷ lệ pass bỏ qua các test chưa chạy

Dễ làm báo cáo quá lạc quan. Báo coverage và pass rate riêng, nhấn mạnh critical gaps.

### 25.10. Không có artifact identity

Nếu container image tag, dependency snapshot hoặc plugin version thay đổi, không thể lặp lại test. Ghi hashes/digests và build IDs.

### 25.11. Không chỉ định owner

Findings không có owner thường tồn tại mãi. Mỗi blocker cần hành động, người chịu trách nhiệm và ngày kiểm lại.

### 25.12. Không định nghĩa rollback

Một runtime candidate có thể chạy tốt nhưng dữ liệu hoặc event format mới không được old runtime đọc. Phải thử rollback trước rollout nếu khả năng quay lui là yêu cầu.

## 26. Cách ra quyết định dựa trên ma trận

Một báo cáo tốt nên kết thúc bằng **một quyết định cụ thể**, thay vì chỉ mô tả tiến độ.

### 26.1. `GO` — Có thể tiến tới rollout đã giới hạn

Chỉ cân nhắc nếu:

- Critical compatibility checks PASS.
- Build/runtime JDKs và artifacts được xác định.
- Integration/TLS/agent tests phù hợp đã hoàn tất.
- Không còn high-severity unresolved failures.
- Có monitoring, SLO và rollback plan đã kiểm chứng.
- Có owner phê duyệt giai đoạn tiếp.

`GO` có thể chỉ có nghĩa “được canary 5%”, **không đồng nghĩa triển khai toàn bộ production**.

### 26.2. `HOLD` — Cần bổ sung bằng chứng

Áp dụng khi critical tests `NOT_RUN`, `BLOCKED`, hoặc không rõ runtime/classloader/truststore đang dùng.

Đây là tình trạng phù hợp với báo cáo OrderHub giả định vì mTLS và agent chưa được kiểm.

### 26.3. `NO-GO` — Có blocker đã được chứng minh

Ví dụ một critical payment transaction fail trên JDK candidate hoặc security policy bị vi phạm. Không mở rộng rollout khi chưa có fix và regression evidence.

### 26.4. `RE-SCOPE` — Cần chia nhỏ mục tiêu

Nếu muốn nâng JDK 11 →21 cùng lúc đổi Jakarta, DB schema và virtual threads mà rủi ro quá lớn, hãy tách thành các phase:

```text
Phase 1: inventory + CI JDK17 test
Phase 2: upgrade incompatible dependencies
Phase 3: runtime JDK17 canary
Phase 4: framework/Jakarta migration
Phase 5: JDK21 and execution-model improvements
```

Đây là lộ trình minh họa; thứ tự thật phải dựa vào dependency requirements và support policy.

## 27. Checklist cuối bài

### Phạm vi và inventory

- [ ] Đã xác định project, version, môi trường, JDK hiện tại và mục tiêu.
- [ ] Đã tách build JVM, compiler JDK, bytecode target, test JVM, production runtime.
- [ ] Đã kiểm kê framework, server, dependencies và plugins.
- [ ] Đã ghi các Java agents, bytecode tools và native libraries.
- [ ] Đã xác định những integration quan trọng: DB, HTTPS/mTLS, messaging, jobs.
- [ ] Đã có owner cho từng nhóm thành phần.

### Bằng chứng và ma trận

- [ ] Đã định nghĩa rõ PASS/FAIL/BLOCKED/NOT_RUN/UNKNOWN.
- [ ] Đã tách vendor support và local verified status.
- [ ] Đã chạy hoặc ghi rõ chưa chạy baseline và candidate.
- [ ] Mỗi PASS/FAIL quan trọng đều có evidence ID và artifact/runtime identity.
- [ ] Đã kiểm tra classfile level, JDK internal APIs và runtime packaging.
- [ ] Đã kiểm tra certificate/truststore và security policy trên JVM mục tiêu.
- [ ] Đã xem reflection, Javax/Jakarta, classloader và binary compatibility nếu liên quan.
- [ ] Đã test exact artifact deployment, không chỉ source build.
- [ ] Đã ghi những tests không áp dụng kèm lý do.
- [ ] Đã kiểm tra data/event compatibility và rollback readiness.

### Báo cáo và quyết định

- [ ] Executive summary nêu mức sẵn sàng, không phóng đại từ smoke test.
- [ ] Có matrix summary và coverage/pass rate riêng.
- [ ] Có findings được ưu tiên theo tác động và mức bất định.
- [ ] Mỗi risk có owner, action và điều kiện đóng.
- [ ] Có đề xuất giai đoạn migration tiếp theo.
- [ ] Có kết luận `GO`, `HOLD`, `NO-GO` hoặc `RE-SCOPE` với phạm vi cụ thể.
- [ ] Có kế hoạch kiểm chứng lại sau khi dependency/JDK/config thay đổi.
- [ ] Báo cáo có ngày, version và liên kết tới evidence không chứa secrets.

## 28. Kết luận

**Ma trận tương thích** là bản đồ của những kết hợp JDK, build tool, framework, dependency, runtime, integration và deployment **đã được xác minh**. **Báo cáo hiện trạng** chuyển bản đồ đó thành một quyết định kỹ thuật và vận hành: phần nào sẵn sàng, phần nào thiếu bằng chứng, rủi ro nào cần xử lý trước, và bước migration nào đủ nhỏ để thực hiện an toàn.

Khi lập ma trận cho dự án Java, đừng dừng ở “build pass” hay “ứng dụng khởi động được”. Hãy thu thập thông tin từ **đúng JVM**, kiểm tra artifact cuối, gắn từng kết quả với test/evidence, phân loại `NOT_RUN` và `BLOCKED` trung thực, rồi kiểm tra cả TLS, agents, native integrations, dữ liệu và rollback. Một báo cáo có những ô chưa hoàn tất nhưng chỉ rõ owner và điều kiện đóng **đáng tin cậy hơn** một bảng toàn màu xanh không truy được bằng chứng.

Mục tiêu của bài thực hành không phải tạo một bảng tính đẹp; đó là tạo **cơ sở kiểm chứng để quyết định nâng JDK theo từng bước, biết khi nào nên tiếp tục và khi nào phải dừng**.
