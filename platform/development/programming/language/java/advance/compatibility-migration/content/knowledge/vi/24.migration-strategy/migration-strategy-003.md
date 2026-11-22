# Chọn bước chuyển nhỏ có thể kiểm chứng và quay lui

Nâng cấp một hệ thống Java lâu năm từ JDK 8 hoặc 11 lên JDK 17, 21 hay thế hệ mới hơn không chỉ là thay `JAVA_HOME` và sửa vài lỗi biên dịch. Một đợt **Java Advance Compatibility Migration** có thể đồng thời chạm tới dependency, Gradle/Maven, application server, module system, reflection, security provider, TLS, garbage collector, logging, Java EE/Jakarta EE, cơ chế triển khai và định dạng dữ liệu. Nếu gộp tất cả thay đổi vào một lần phát hành, khi xảy ra lỗi rất khó xác định nguyên nhân; việc quay về bản cũ cũng có thể không còn an toàn.

Một chiến lược thực tế hơn là chia migration thành **những bước nhỏ, có tiêu chí kiểm chứng rõ ràng và có đường quay lui đã chuẩn bị từ trước**. “Nhỏ” không chỉ có nghĩa ít dòng code. Một bước được coi là nhỏ khi phạm vi ảnh hưởng được giới hạn, số giả thuyết cần kiểm tra vừa đủ, các kết quả có thể quan sát, và có thể đảo hoặc vô hiệu hóa thay đổi trong một khoảng thời gian chấp nhận được.

Bài học này hướng dẫn cách xác định ranh giới của một bước chuyển, phân loại thay đổi có thể đảo ngược và không thể đảo ngược, tổ chức test/CI/CD, dùng feature flags và canary, giữ tương thích dữ liệu khi chạy song song hai phiên bản, đặt điều kiện rollback và xây dựng lộ trình nâng JDK mà không biến mỗi lần deploy thành một canh bạc.

## 1. “Bước chuyển nhỏ” nghĩa là gì?

Một bước migration tốt không chỉ thay đổi một thành phần; nó phải trả lời được năm câu hỏi:

1. **Mục tiêu:** sau bước này, hệ thống tốt hơn hoặc sẵn sàng cho JDK mục tiêu ở điểm nào?
2. **Phạm vi:** module, service, API, job, nhóm người dùng hoặc tài nguyên nào bị ảnh hưởng?
3. **Bằng chứng:** test, benchmark, log, metrics hoặc đối chiếu nào chứng minh thay đổi hoạt động?
4. **Điều kiện dừng:** khi nào không tiếp tục rollout hoặc phải dừng phát hành?
5. **Đường quay lui:** nếu lỗi, triển khai lại artifact cũ, tắt flag, chuyển traffic hay khôi phục dữ liệu bằng cách nào?

Ví dụ một bước hợp lý:

> Nâng một background worker từ JDK 11 lên JDK 17, giữ nguyên source, dependency và định dạng message; chạy contract test với message broker, triển khai canary 5% workload, quan sát error rate/lag, và có thể chuyển worker về image JDK 11 nếu message format không đổi.

Ví dụ một bước quá lớn:

> Đồng thời nâng JDK 11 lên 21, chuyển Spring Boot 2 lên 3, đổi `javax.*` sang `jakarta.*`, thay ORM, đổi database schema, bật virtual threads và nâng toàn bộ logging/tracing agents.

Nếu đợt thứ hai gây `NoSuchMethodError`, `SSLHandshakeException` hoặc tăng p99 latency, có quá nhiều biến thay đổi khiến việc khoanh vùng khó khăn.

### 1.1. Nhỏ theo số biến độc lập, không chỉ theo số file

Một pull request sửa 300 file import do đổi namespace có thể là một bước có ranh giới rõ, nếu chỉ đổi namespace, giữ logic và kiểm chứng contract. Ngược lại, một dòng đổi dependency version có thể làm thay đổi hàng chục dependency transitive và behavior của framework.

Vì vậy phải phân tích **đồ thị ảnh hưởng**, không dùng số dòng code làm chỉ số rủi ro duy nhất.

### 1.2. Có thể kiểm chứng nghĩa là có tín hiệu độc lập

Một bước “build xanh” chưa chắc kiểm chứng được hành vi runtime. Ví dụ:

- JavaCompile thành công nhưng container còn dùng JDK cũ.
- Test chạy JDK 21 trong khi production chạy JDK 17.
- HTTP 200 nhưng response schema đã thay.
- Startup thành công nhưng `ServiceLoader` không tìm được provider.
- Giao diện vẫn hiển thị nhưng transaction bị commit hai lần.
- App chạy được nhưng latency hoặc heap tăng vượt SLO.

Bằng chứng cần khớp **giả thuyết của bước chuyển**, không chỉ là một chỉ báo chung.

### 1.3. Có thể quay lui nghĩa là quay lui được trạng thái vận hành

Git revert chỉ hoàn tác source. Nó không khôi phục:

- Schema database đã drop cột.
- Dữ liệu được mã hóa lại bằng khóa mà bản cũ không đọc được.
- Message/event đã phát ra với format mới.
- Certificate cũ đã bị thu hồi.
- External API đã thay hợp đồng.
- Dữ liệu ghi theo enum hoặc serialization format mới.
- Client desktop đã tự cập nhật và không hỗ trợ downgrade.

**Rollback phải bao gồm code, runtime, cấu hình, dependency, traffic, dữ liệu và tác động bên ngoài.** Với những thay đổi không thể đảo trực tiếp, cần thay đổi thiết kế để tạo một khoảng thời gian tương thích ngược hoặc có kế hoạch phục hồi được kiểm soát.

## 2. Các chiều thay đổi trong migration Java

Một dự án có nhiều lớp compatibility, nên không nhất thiết phải chuyển đồng thời.

| Chiều thay đổi | Ví dụ | Rủi ro nếu gộp chung |
|---|---|---|
| JVM chạy build tool | Gradle daemon JDK 11 → 17 | Plugin/build script không khởi động được |
| Compiler toolchain | `javac` 11 → 17 | Annotation processor, bytecode tool lỗi |
| Source/bytecode target | `--release 11` → 17 | Runtime cũ không nạp được class |
| Runtime JDK | Container JDK 11 → 17 | Reflection/TLS/GC/charset/provider khác |
| Dependency | Framework, JDBC, ASM, Byte Buddy | Binary incompatibility và hành vi mới |
| Application server | Servlet container Javax → Jakarta | Namespace và lifecycle khác |
| JPMS | Classpath → module path | `requires`, `exports`, `opens`, split package |
| Security | Certificate, TLS policy, signer | Kết nối hoặc chữ ký bị từ chối |
| Execution model | Fixed pool → virtual threads | Concurrency và resource saturation thay đổi |
| Deployment | JAR → runtime image/native package | Launcher, config và update khác |
| Data contract | DB schema, JSON schema, event version | Bản cũ không đọc được dữ liệu mới |

Một chiến lược thường có lợi là **giữ ổn định càng nhiều chiều càng tốt trong từng bước**, sau đó đo sự khác biệt.

Ví dụ nâng JDK mà vẫn dùng classpath truyền thống trước khi chuyển JPMS; hoặc nâng thư viện ASM/Byte Buddy để đọc bytecode mới trước khi bật compiler target mới.

## 3. Phân loại bước chuyển theo tính đảo ngược

Không phải mọi thay đổi đều có cùng đường rollback.

| Loại bước | Ví dụ | Khả năng đảo | Cần chuẩn bị |
|---|---|---|---|
| Thay cấu hình có thể bật/tắt | Feature flag, executor strategy | Thường cao | Tắt nhanh, xác minh state không đổi |
| Đổi artifact/runtime không đổi dữ liệu | Image JDK 11 → 17 | Thường cao nếu contract giữ nguyên | Artifact cũ, image digest, traffic switch |
| Nâng dependency nội bộ không đổi public API | JDBC client, parser | Tùy hành vi | Regression và integration tests |
| Đổi contract có khả năng tương thích ngược | Thêm JSON field tùy chọn | Trung bình–cao nếu consumer bỏ qua field lạ | Consumer-driven contract |
| Đổi cơ sở dữ liệu additive | Thêm nullable column/index | Thường đảo được ở mức ứng dụng, không nhất thiết cần drop DB | Expand-contract, kiểm soát migration |
| Chuyển định dạng persisted data | Serialization/encryption mới | Thấp nếu bản cũ không đọc được | Dual read, versioning, backup/recovery |
| Đổi public namespace/framework | Javax → Jakarta | Thấp nếu không có tương thích trung gian | Biên giới service, artifact riêng, rollout phối hợp |
| Xóa cột/đổi ý nghĩa dữ liệu | Drop legacy column | Thấp | Delayed contract phase, backup, restore thử nghiệm |
| Cập nhật external system side effects | Gửi tiền, phát email, revoke certificate | Không đảo trực tiếp | Idempotency, compensating action, runbook |

**Tính đảo ngược phải được xác nhận bằng thử nghiệm**, không dựa trên nhãn “config-only” hoặc “minor version”.

## 4. Tạo bản đồ phụ thuộc và xác định ranh giới chuyển đổi

Trước khi chọn bước đầu tiên, cần biết những thành phần nào bị phụ thuộc và có thể tách riêng.

Ví dụ:

```text
Web client
    |
    v
API Gateway
    |
    +--> Order Service (JDK 11)
    |       |
    |       +--> PostgreSQL
    |       +--> Payment API
    |       +--> Kafka: order-events.v1
    |
    +--> Inventory Service (JDK 11)
            |
            +--> PostgreSQL
            +--> Inventory SDK
```

Nếu Order Service có hợp đồng HTTP/event ổn định và không chia sẻ Java object qua classloader với Inventory Service, có thể nâng từng service độc lập. Nhưng nếu hai service dùng chung database schema và thực hiện migration phá vỡ tương thích, việc tách rollout vẫn bị hạn chế.

### 4.1. Các ranh giới có thể chia nhỏ

- **Theo service:** một microservice độc lập.
- **Theo deployment group:** một nhóm pod/instance.
- **Theo request cohort:** nhóm người dùng hoặc tỷ lệ traffic.
- **Theo endpoint:** chỉ một luồng API.
- **Theo job:** một scheduled/batch/consumer worker.
- **Theo dependency boundary:** một client library hoặc integration adapter.
- **Theo artifact:** một plugin hoặc command-line tool riêng.
- **Theo data contract:** một schema version hoặc một loại event.

Lựa chọn ranh giới phụ thuộc khả năng triển khai, tính thống nhất dữ liệu và mức độ quan sát, không nhất thiết theo cấu trúc package Java.

### 4.2. Phân biệt dependency kỹ thuật và dependency vận hành

Một service có thể độc lập ở mức code nhưng bị ràng buộc vận hành bởi:

- Shared database và transaction.
- Cùng queue với message không có version.
- Authentication/certificate chung.
- File format dùng chung qua storage.
- Application server chứa nhiều WAR.
- Cache có serialization format không ổn định.
- Client desktop chưa được cập nhật đồng thời.

Các điểm này phải có trong impact map; nếu không, “nâng một service” có thể thực tế là thay cả hệ thống.

## 5. Ưu tiên bước chuyển bằng giá trị và rủi ro

Không nên bắt đầu từ bước lớn nhất hoặc từ phần “dễ thay import” nhất. Hãy chọn bước có thể **giảm bất định** mà không mở rộng blast radius quá mức.

Một bảng quyết định có thể dùng:

| Bước ứng viên | Giá trị nhận được | Rủi ro | Dễ kiểm chứng | Dễ rollback |
|---|---|---|---|---|
| Ghim Gradle wrapper và compiler toolchain | Build tái hiện được | Thấp–TB | Cao | Cao |
| Thêm CI job chạy test trên JDK mục tiêu | Phát hiện lỗi sớm | Thấp | Cao | Cao |
| Nâng ASM/Byte Buddy và test agents | Hỗ trợ classfile mới | TB | Cao | TB–Cao |
| Nâng runtime cho một stateless worker | Kiểm chứng JVM production | TB | Cao | Cao nếu data contract ổn định |
| Chuyển toàn bộ JPA/Hibernate + Jakarta | Chuẩn bị framework mới | Cao | TB | TB–Thấp |
| Đổi schema phá vỡ tương thích | Đơn giản hóa dữ liệu | Cao | TB | Thấp |
| Bật virtual threads toàn hệ thống | Có thể tăng I/O concurrency | Cao | Cần load test | TB nếu có cấu hình song song |

Đây là một ví dụ định tính, không phải chấm điểm mặc định cho mọi tổ chức. Một thư viện đã hết hỗ trợ bảo mật có thể cần ưu tiên dù migration phức tạp; khi đó nên **tách nó thành những bước nhỏ hơn** thay vì trì hoãn vô hạn.

### 5.1. Công thức chấm điểm minh họa

Có thể đánh giá theo thang 1–5:

```text
Priority =
    (Business value + Risk reduction + Learning value)
    / (Implementation effort + Blast radius + Rollback difficulty)
```

Không dùng công thức như một mô hình định lượng chính xác. Nó giúp buộc nhóm thảo luận về giá trị, độ rủi ro và khả năng hoàn tác của từng bước.

### 5.2. Bắt đầu với bước tạo năng lực quan sát

Trước khi nâng runtime, bổ sung test/metrics có thể là bước đầu tiên có giá trị lớn:

- Chạy bộ test trên JDK cũ và JDK mới song song.
- Chụp baseline throughput/latency/heap.
- Lưu dependency tree và version.
- Bật cảnh báo handshake/PKIX errors.
- Ghi version runtime tại startup.
- Xác định artifact/container digest và cách rollback.

Những bước này không trực tiếp nâng JDK nhưng **giảm rủi ro cho tất cả bước sau**.

## 6. Định nghĩa “bước chuyển” như một thí nghiệm

Mỗi bước nên có mô tả nhất quán.

| Trường | Cần ghi |
|---|---|
| Mục tiêu | Kết quả kỹ thuật hoặc nghiệp vụ mong muốn |
| Giả thuyết | Vì sao thay đổi này được kỳ vọng hoạt động |
| Phạm vi | Service, module, endpoint, user cohort, environment |
| Biến thay đổi | JDK, dependency hoặc cấu hình nào thay |
| Điều kiện trước | Test/backup/compatibility được chuẩn bị |
| Bằng chứng | Unit/integration/contract/load tests, metrics |
| Tiêu chí đạt | Điều kiện để tăng rollout |
| Tiêu chí dừng | Điều kiện khiến không rollout thêm |
| Rollback | Cách tắt/đảo thay đổi và giới hạn của nó |
| Owner | Người/nhóm chịu trách nhiệm |
| Thời điểm ra quyết định | Khi nào xem dữ liệu và quyết định tiếp |
| Artifact | Image digest, JAR hash, feature flag, manifest version |

Ví dụ ngắn:

```yaml
step: migrate-order-worker-runtime
change:
  from: JDK 11 runtime image
  to: JDK 17 runtime image
  code_changes: none
scope:
  deployment: order-worker
  canary_fraction: "5%"
preconditions:
  - Can read and write message schema v1
  - Old image digest retained
  - Contract tests passing
evidence:
  - Message processing success
  - Queue lag
  - p95 processing latency
  - DLQ count
rollback:
  - Stop new canary consumers
  - Switch traffic/partition assignment to previous image
  - Confirm offsets and idempotency
```

Đây là template minh họa; không phải một CI/CD schema được công cụ nào đó tự hiểu. Các ngưỡng và lệnh vận hành cần điền theo hệ thống thật.

## 7. Tách JDK build, compiler và runtime thành các bước

Một lỗi chiến lược phổ biến là đổi cả JDK chạy Gradle, compiler target và production runtime cùng lúc.

### 7.1. Bước A: làm build tái hiện được

Ghim Gradle wrapper hoặc Maven version/plugin được hỗ trợ. Ghi nhận build JVM và toolchain. Kiểm tra dependency locks/versions, không dùng dynamic versions ngoài kiểm soát.

Với Gradle Groovy DSL:

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

Đây là ví dụ **compiler JDK 17, target bytecode/API Java 11**. Nó không buộc Gradle daemon chạy JDK 17, và không tự chứng minh dependency runtime tương thích Java 11.

### 7.2. Bước B: chạy kiểm thử trên JDK mục tiêu

Có thể tạo thêm CI job dùng runtime JDK 17 trong khi production vẫn ở JDK 11. Giữ nguyên code và dependency để xác định lỗi runtime: reflection, TLS, classloader, charset, native libraries hoặc agent.

Khi test JDK mới fail, lỗi được khoanh vùng trong phạm vi runtime change, thay vì trộn với nâng framework.

### 7.3. Bước C: nâng từng dependency không tương thích

Ví dụ:

- ASM/Byte Buddy/JaCoCo phải đọc được class file target.
- JDBC driver và ORM hỗ trợ JDK mục tiêu.
- Logging/tracing agent hỗ trợ JVM version.
- Thư viện dùng JDK internal APIs phải được cập nhật.
- Provider bảo mật phải hỗ trợ TLS/certificate policy mới.

Nâng từng nhóm có quan hệ rõ, lưu dependency tree và chạy regression suite.

### 7.4. Bước D: thay production runtime của một deployment unit

Khi artifact đã chạy trên JDK mới trong test environment, chọn một worker hoặc service không chia sẻ trạng thái nội bộ để canary.

### 7.5. Bước E: nâng source/release target nếu cần

Chỉ sau khi runtime ổn định mới cân nhắc dùng language features và Java APIs mới. Nếu một thư viện vẫn phải chạy trên Java 11, tiếp tục phát hành classfile target 11 cho thư viện đó dù build process và ứng dụng khác đã lên JDK 17.

### 7.6. Bước F: chuyển kiến trúc sau khi baseline ổn định

Chuyển JPMS, `javax.*` sang `jakarta.*`, hoặc virtual threads là các thay đổi kiến trúc/contract có thể độc lập với việc nâng runtime. Nên tạo các bước riêng nếu có thể.

## 8. Maven và Gradle: xây test matrix không đổi production ngay

### 8.1. Maven Compiler Plugin và `release`

Ví dụ Maven:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Compiler phải đủ mới để hỗ trợ `--release 11` và plugin phải tương thích; thông số này chỉ ràng buộc Java platform APIs/bytecode trong compilation tương ứng, không tự giảm bytecode của dependencies.

### 8.2. Gradle test với toolchain runtime cụ thể

Ví dụ:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Có thể chạy một test job riêng với Java 17 launcher ở CI. Điều quan trọng là báo cáo **JDK thực tế của test worker**, không chỉ `java -version` trong shell.

### 8.3. Cấu hình matrix ở mức ý tưởng

```text
Job 1:
  Gradle daemon JDK: 17
  Compiler:           17
  --release:          11
  Test runtime:       11

Job 2:
  Gradle daemon JDK: 17
  Compiler:           17
  --release:          11
  Test runtime:       17
```

Nếu Job 1 pass nhưng Job 2 fail, có khả năng thay đổi hành vi/runtime compatibility. Nếu Job 1 fail do classfile version, cần kiểm tra compiler release hoặc dependency. Việc cô lập biến giúp rút ngắn điều tra.

### 8.4. Không coi test matrix là bằng chứng tuyệt đối

Một integration path không chạy trong test có thể vẫn lỗi trên JDK mới. Cần kết hợp test chức năng, staging, canary, observability và runtime compatibility của system dependencies.

## 9. Chọn điểm kiểm chứng cho mỗi bước

Không dùng cùng một bộ tiêu chí cho mọi thay đổi. Ví dụ:

| Bước chuyển | Bằng chứng có giá trị |
|---|---|
| Nâng JDK runtime | Startup, smoke, TLS/PKIX, reflection, integration, JVM metrics |
| Nâng logging agent | Agent hoạt động, traces/metrics đầy đủ, không làm tăng overhead |
| Nâng ORM | Transaction semantics, lazy loading, SQL behavior, database integration |
| Đổi Javax/Jakarta | Servlet/filter/listener lifecycle, injection, JPA, Validation, REST |
| Nâng Byte Buddy | Mock/proxy, instrumentation, classfile parser, runtime agent |
| Bật virtual threads | Load test, DB waiters, CPU, p99, pinning/cancellation |
| Đổi JSON schema | Backward/forward contract tests và consumer compatibility |
| Đổi DB schema | Both-version read/write tests, migration correctness, index performance |
| Đổi TLS/certificate | Handshake với toàn bộ client class và rollback/cert chain |
| Đổi container image | Startup, health, configuration, native libraries, data paths |

### 9.1. Test pyramid cho migration

Một hệ thống thường cần nhiều lớp:

```text
           Production canary metrics
                 /        \
           End-to-end critical flows
             /            \
      Integration & contract tests
           /               \
     Unit tests & static checks
```

Test nhanh nên chạy ở mọi commit. End-to-end và canary kiểm chứng những giả định không thể tái hiện hoàn toàn trong unit test, nhưng không thay thế cơ sở test nhanh.

### 9.2. Negative testing quan trọng không kém happy path

Sau khi nâng Validation hoặc security provider, ứng dụng vẫn trả HTTP 200 cho dữ liệu hợp lệ. Nhưng nếu dữ liệu không hợp lệ cũng được chấp nhận, migration đã gây regression nguy hiểm.

Cần kiểm tra tình huống thất bại mong đợi:

- Input thiếu field bắt buộc.
- Chứng chỉ hết hạn/không hợp lệ.
- Event schema version chưa hỗ trợ.
- API downstream timeout.
- Database connection bị từ chối.
- Retry không tạo side effect trùng.
- Consumer nhận message ngoài thứ tự.
- Authorization bị từ chối đúng.

### 9.3. Kiểm tra binary compatibility

Khi đổi library version, `NoSuchMethodError`, `NoSuchFieldError` hoặc classloader conflict có thể chỉ xuất hiện ở runtime. Có thể dùng API/binary diff tools và smoke test bằng artifact thực tế để bổ sung cho source compilation.

## 10. Đặt tiêu chí pass/fail trước khi deploy

Một canary không có ngưỡng là một đợt deploy chưa được kiểm soát. Nên xác định tiêu chí trước khi nhìn dữ liệu để tránh thay đổi định nghĩa thành công theo kết quả.

Ví dụ minh họa cho một service stateless:

| Chỉ số | Baseline | Ngưỡng minh họa để tiếp tục |
|---|---|---|
| HTTP 5xx rate | 0,2% | Không vượt baseline quá một độ lệch được thống nhất |
| p95 latency | 180 ms | Không tăng quá 15% sau khi chuẩn hóa traffic mix |
| p99 latency | 450 ms | Không tăng quá 20% trên đủ số request |
| CPU utilization | 45% | Không tăng bất thường khi cùng traffic |
| Heap/GC pause | Ổn định | Không vượt SLO bộ nhớ/GC |
| Payment failure | 0,1% | Không tăng so với nhóm control |
| Queue lag | < 30 giây | Không tăng kéo dài so với baseline |

**Các con số trên chỉ là ví dụ, không phải chuẩn ngành hay SLO có sẵn của một hệ thống.** Ngưỡng thực tế phải dựa trên mức chấp nhận rủi ro, mùa vụ, khối lượng mẫu và mục tiêu nghiệp vụ.

### 10.1. Tránh so sánh traffic không tương đương

Nếu canary nhận các request đơn giản còn bản cũ xử lý nhiều request nặng, p95 thấp hơn không chứng minh thay đổi tốt hơn.

Nên so sánh:

- Cùng loại endpoint.
- Cùng region/tenant nếu có.
- Cùng thời gian hoặc có control cohort.
- Cùng data size và retry mix.
- Cùng yêu cầu authentication/TLS.
- Số mẫu đủ để không kết luận từ vài request.

### 10.2. Chỉ dùng health check là chưa đủ

`/health` trả 200 có thể chứng minh process còn sống, nhưng không chứng minh business flow đúng. Cần cả readiness/liveness, downstream dependency health, event lag và domain-level success metrics.

### 10.3. Đặt hard stop và soft warning

Ví dụ:

- **Hard stop:** lỗi dữ liệu, tăng payment failures vượt giới hạn, mất authentication hoặc message duplication gây hậu quả nghiệp vụ.
- **Soft warning:** GC hoặc CPU cao hơn nhẹ trong thời gian quan sát ngắn, cần thêm mẫu.
- **Không đủ dữ liệu:** tiếp tục giữ ở canary level, không tăng traffic chỉ vì chưa thấy lỗi.

## 11. Canary release: tăng mức ảnh hưởng theo từng nấc

Canary cho phép triển khai một bản mới tới một phần workload trước khi mở rộng.

Ví dụ lộ trình:

```text
0% (staging)
    |
    v
1% hoặc một canary instance
    |
    v
5% traffic
    |
    v
20% traffic
    |
    v
50% traffic
    |
    v
100% traffic
```

Tỷ lệ và thời gian quan sát phải do hệ thống quyết định dựa trên request volume, rủi ro và khả năng phát hiện lỗi. Với một worker ít traffic, rollout theo số consumer hoặc queue partition có thể có ý nghĩa hơn phần trăm HTTP requests.

### 11.1. Một canary tốt có tính đại diện

Chọn nhóm đủ đại diện về:

- Endpoint và dữ liệu.
- Authentication/tenant.
- Region và dependency.
- Traffic peak và off-peak.
- Retry, failure và fallback paths.
- Batch job hoặc message flow hiếm gặp.

Nếu canary chỉ chạy trên một endpoint ít quan trọng, không thể dùng kết quả để khẳng định toàn ứng dụng tương thích.

### 11.2. Cần traffic routing có thể đảo

Nếu sử dụng reverse proxy, gateway hoặc service mesh, nên có cách chuyển traffic về release cũ. Với worker xử lý queue, cần kiểm tra offset, consumer group, partition assignment và cách xử lý in-flight tasks.

Canary rollback không chỉ là “xóa pod mới”; phải xác định request/message đang xử lý dở sẽ được hoàn tất, retry hay được route lại.

### 11.3. Blue-green deployment

Blue-green giữ hai môi trường production có thể chạy song song:

```text
           Traffic router
             /       \
      Blue (old)    Green (new)
```

Chỉ chuyển traffic sang green sau khi kiểm chứng. Nếu lỗi, có thể chuyển lại blue **khi data contract và state vẫn tương thích**.

Blue-green không phải bảo đảm rollback dữ liệu. Nếu green đã chạy migration xóa cột hoặc ghi format mà blue không đọc được, switching traffic cũng không an toàn.

## 12. Feature flags để tách deploy và kích hoạt

Một feature flag có thể giữ code mới trong cùng artifact nhưng chưa áp dụng cho tất cả request.

Ví dụ trừu tượng:

```java
public final class PricingService {
    private final FeatureFlags flags;
    private final LegacyPricing legacy;
    private final NewPricing modern;

    public PricingService(
            FeatureFlags flags,
            LegacyPricing legacy,
            NewPricing modern) {
        this.flags = flags;
        this.legacy = legacy;
        this.modern = modern;
    }

    public Price quote(Order order) {
        if (flags.enabled("pricing-v2", order.customerId())) {
            return modern.quote(order);
        }
        return legacy.quote(order);
    }
}
```

Các kiểu `FeatureFlags`, `LegacyPricing`, `NewPricing`, `Price` và `Order` là mô hình ứng dụng minh họa. Ý tưởng là **chọn behavior tại boundary** có thể điều khiển được, không phải dùng một framework flag cụ thể.

### 12.1. Flag phù hợp khi nào?

- Có thể tồn tại đồng thời hai implementation trong một phiên bản artifact.
- Cả hai implementation dùng được dữ liệu chung.
- Việc chọn luồng xử lý không phá vỡ invariant nghiệp vụ.
- Có thể đo riêng kết quả của bản mới.
- Tắt flag đủ nhanh so với thời gian phát hiện sự cố.

Ví dụ bật hai implementation của một thuật toán thuần tính toán thường đơn giản hơn bật hai schema ghi dữ liệu.

### 12.2. Những việc flag không giải quyết

Một feature flag không tự quay lui:

- Schema database đã drop.
- Library API bị xóa khỏi artifact.
- Runtime image đã thay và không còn bản cũ.
- Certificate đã revoke.
- Message đã publish dưới format không tương thích.
- Side effect đã thực hiện với hệ thống ngoài.

Một số thay đổi cần **deployment rollback**, một số cần **data recovery hoặc compensating workflow**, không thể chỉ tắt cờ.

### 12.3. Đặt hạn sử dụng của flag

Flag migration là công cụ chuyển tiếp, không nên tồn tại vô thời hạn. Sau khi phiên bản mới ổn định và đường cũ được ngừng hỗ trợ, xóa code/flag cũ bằng một bước riêng và kiểm chứng.

## 13. Shadow traffic và so sánh song song

Để kiểm chứng code mới mà không cho nó quyết định kết quả người dùng, có thể **chạy song song** logic mới như một nhánh shadow.

Ví dụ:

```text
Request
   |
   +--> Old implementation ---> Response thật
   |
   +--> New implementation ---> Kết quả shadow để so sánh
```

Cách này phù hợp cho một số thuật toán thuần tính toán, parser, định dạng response hoặc recommendation engine.

### 13.1. Không shadow bừa các side effects

Không được sao chép request đặt hàng, chuyển tiền, gửi email hoặc ghi dữ liệu sang nhánh shadow nếu nó thực hiện side effect thật. Cần dùng sandbox/test endpoint hoặc tách hoàn toàn phần tính toán.

### 13.2. So sánh theo semantics, không nhất thiết byte-for-byte

Hai JSON responses có thể khác thứ tự field hoặc timestamp nhưng giống logic. Cần canonicalize và bỏ qua các field không quan trọng trước khi kết luận mismatch.

### 13.3. Bảo vệ dữ liệu người dùng

Shadow payload có thể chứa thông tin cá nhân hoặc bí mật. Phải đáp ứng quyền riêng tư, audit, access control và retention policy. Không ghi nguyên request body lên log chỉ để so sánh migration.

## 14. Database migration: nguyên tắc expand–migrate–contract

Một trong những phần khó rollback nhất là thay đổi schema dữ liệu.

### 14.1. Mô hình nguy hiểm: đổi schema cùng lúc với code

Giả sử ứng dụng cũ đọc:

```sql
SELECT full_name FROM customer;
```

Bản mới muốn dùng `first_name` và `last_name`. Nếu deploy migration:

```sql
ALTER TABLE customer DROP COLUMN full_name;
```

trước khi mọi instance cũ ngừng dùng `full_name`, bản cũ có thể lỗi ngay. Nếu phải rollback release mới, bản cũ cũng không thể chạy như trước.

### 14.2. Expand: thêm schema tương thích

Bước đầu chỉ thêm cột mới:

```sql
ALTER TABLE customer ADD COLUMN first_name VARCHAR(100);
ALTER TABLE customer ADD COLUMN last_name VARCHAR(100);
```

Schema cũ vẫn tồn tại, nên old application có thể tiếp tục chạy. Nhưng lưu ý schema change có thể lock table hoặc ảnh hưởng performance tùy database; cần đánh giá DDL thật.

### 14.3. Migrate: hỗ trợ cả hai dạng dữ liệu

Một giai đoạn chuyển tiếp có thể:

1. Backfill dữ liệu cũ sang cột mới.
2. Cho code mới đọc từ cột mới, fallback sang cột cũ nếu chưa có.
3. Viết cả hai định dạng khi cần duy trì tương thích.
4. Đo tiến độ backfill và kiểm tra dữ liệu nhất quán.
5. Cập nhật mọi consumer/worker trước khi bỏ cột cũ.

**Dual-write không đơn giản**: nếu một transaction ghi một bên thành công và bên kia thất bại, dữ liệu có thể lệch. Cần dùng transaction phù hợp, outbox/event hoặc một chiến lược đồng bộ được thiết kế rõ, không chép “ghi hai lần” vào mọi method.

### 14.4. Contract: loại schema cũ sau khi hết cửa sổ rollback

Chỉ khi mọi phiên bản ứng dụng được hỗ trợ đã bỏ phụ thuộc `full_name`, backfill hoàn tất, và rollback plan không còn yêu cầu version cũ, mới cân nhắc drop cột:

```sql
ALTER TABLE customer DROP COLUMN full_name;
```

Đây phải là **một bước riêng có gate và backup/recovery**, không gộp với bước bật version mới.

### 14.5. Rollback code không đồng nghĩa rollback schema

Với expand-only schema, nhiều trường hợp có thể rollback ứng dụng mà **giữ lại cột mới**. Việc cố drop ngay cột vừa thêm có thể không cần thiết và còn tăng rủi ro.

Ngược lại, khi dữ liệu đã được ghi theo format mà bản cũ không đọc được, giữ cột mới có thể chưa đủ. Cần kiểm thử cả đọc và ghi ở hai chiều tương thích.

## 15. Event và message schema khi chạy hai phiên bản

Trong hệ thống có Kafka, RabbitMQ hoặc các message broker khác, canary thường khiến old/new consumers tồn tại đồng thời.

Ví dụ event version:

```json
{
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "orderId": "O-1001",
  "currency": "VND",
  "totalMinorUnits": 250000
}
```

Nếu consumer cũ chỉ hiểu version 1, việc producer mới phát v2 có thể khiến rollback consumer thất bại. Cần thiết kế một compatibility window.

### 15.1. Các hướng phù hợp

- Thêm field tùy chọn mà consumer cũ bỏ qua.
- Giữ wire schema v1 đến khi mọi consumer có khả năng đọc v2.
- Sử dụng schema registry và compatibility policy phù hợp.
- Publish song song topic/event types có version rõ nếu có kế hoạch chuyển đổi.
- Đưa adapter/gateway chuyển đổi format ở boundary.
- Kiểm tra deserialization cả hai phiên bản.

### 15.2. Thử rollback với message thật

Đừng chỉ chạy contract test bằng mock JSON. Trong môi trường kiểm thử, cho producer mới ghi message rồi dùng consumer cũ đọc lại. Nếu consumer cũ không xử lý được, plan rollback production cần giới hạn phạm vi producer hoặc thiết kế lại format.

### 15.3. Idempotency và in-flight tasks

Khi chuyển consumer giữa versions, message có thể được xử lý lại. Các bước migration phải xem:

- At-least-once delivery.
- Dedupe key hoặc idempotency token.
- Retry policy và dead-letter queue.
- Offset commit và transaction semantics.
- Side effects phía downstream.

Một rollback làm tăng duplicate processing có thể nguy hiểm hơn lỗi khiến canary bị dừng.

## 16. API backward/forward compatibility

Trong giai đoạn rollout trộn version, cần phân biệt:

- **Backward compatibility:** component mới hiểu dữ liệu/contract do component cũ tạo.
- **Forward compatibility:** component cũ vẫn xử lý được dữ liệu/contract do component mới tạo, trong phạm vi được thiết kế.

Các định nghĩa chi tiết có thể thay đổi theo hệ thống schema/tool, nên cần mô tả cụ thể **producer nào, consumer nào, version nào** khi kiểm thử.

### 16.1. Bảng tương thích hai chiều

| Producer | Consumer | Cần kiểm tra |
|---|---|---|
| Old | Old | Baseline hiện tại |
| Old | New | Bản mới đọc được dữ liệu cũ |
| New | New | Chức năng mới |
| New | Old | Có thể rollback consumer hoặc chạy rollout hỗn hợp |

Ô **New → Old** thường bị bỏ sót. Nó quyết định liệu quay về bản cũ sau khi bản mới đã ghi dữ liệu có an toàn hay không.

### 16.2. Tránh breaking change trong bước chuyển runtime

Khi mục tiêu chỉ là nâng JDK runtime, nên giữ API schema, event schema và persistence format không đổi. Nếu cần thay, tách thành bước sau với contract tests và rollout riêng.

## 17. Đổi Java EE sang Jakarta EE: trường hợp rollback khó

Chuyển từ `javax.servlet.*` sang `jakarta.servlet.*` có thể đòi hỏi đồng thời nâng framework, Servlet container và một số thư viện provider. Đây là thay đổi type contract, không chỉ đổi source target.

### 17.1. Tách các bước chuẩn bị

Một lộ trình có thể:

1. Cập nhật test và dependency inventory.
2. Nâng lên bản cuối của framework còn dùng Javax và tương thích JDK mục tiêu, nếu phù hợp.
3. Loại/thay thư viện đã không còn được bảo trì.
4. Tách logic nghiệp vụ khỏi Servlet/JPA boundary.
5. Chuẩn bị một deployment artifact Jakarta độc lập.
6. Chạy contract tests cùng wire protocol.
7. Canary qua gateway hoặc blue-green môi trường container riêng.
8. Chỉ xóa hỗ trợ container Javax sau cửa sổ rollback.

### 17.2. Đừng thử thả Javax WAR vào Jakarta container để canary

Container Jakarta không tự coi `javax.servlet.Filter` là `jakarta.servlet.Filter`. Nếu cần chạy đồng thời hai thế hệ, sử dụng môi trường/container phù hợp với từng artifact, hoặc một giải pháp migration/transformer đã được kiểm chứng.

### 17.3. Rollback có thể là chuyển traffic về môi trường cũ

Nếu đường HTTP và database schema tương thích, có thể giữ blue environment với Javax stack và green environment với Jakarta stack. Nhưng phải kiểm tra session affinity, session serialization, authentication cookies và in-flight requests.

Không mặc định HTTP contract ổn định đồng nghĩa session state được chia sẻ được.

## 18. JDK security migration và rollback

Thay JDK còn có thể thay thuật toán TLS/chứng chỉ được chấp nhận, keystore behavior, security provider và chính sách chữ ký.

### 18.1. Nâng security không nên rollback bằng cách bật lại thuật toán yếu

Nếu JDK mới từ chối TLS 1.0, RSA key quá ngắn hoặc certificate chain không đạt policy, hướng đúng là nâng server/certificate/provider.

Quay về JDK cũ chỉ để duy trì giao thức không an toàn có thể vi phạm chính sách bảo mật. Trong trường hợp cần chuyển tiếp, phải xác định ngoại lệ rủi ro được phê duyệt, phạm vi cô lập và thời hạn xử lý.

### 18.2. Certificate rotation cũng có thứ tự

Một bước thay server certificate cần cân nhắc:

- Client nào tin CA/chain mới?
- Nếu chuyển về server cũ, certificate cũ còn hiệu lực không?
- Key cũ đã bị revoke/loại khỏi HSM chưa?
- Có giai đoạn hỗ trợ song song hai chain/certificate không?
- mTLS client certificates có cần rotate theo nhóm không?

Nếu khóa cũ đã bị thu hồi, rollback không thể đơn giản “bật lại cấu hình cũ”. Phải thiết kế rollback theo trust policy mới hoặc đưa ra phương án cấp lại phù hợp.

## 19. Runtime image và artifact phải tái hiện được

Một kế hoạch rollback có thể thất bại nếu hệ thống chỉ lưu branch name chứ không lưu artifact đã chạy trước đó.

Cần ghi:

- JAR/WAR version và SHA-256 checksum.
- Container image digest, không chỉ mutable tag như `latest`.
- JDK vendor/full update/build.
- Build tool và dependency versions.
- Database migration version.
- Configuration/feature flag snapshot.
- Agent/native library versions.
- Deployment manifest hoặc artifact release đã phê duyệt.

Ví dụ ghi metadata release:

```yaml
release: order-service-2026.11.12-01
applicationArtifact: order-service.jar
applicationSha256: "<calculated-sha256>"
runtime:
  javaVendor: "Example JDK Vendor"
  javaVersion: "17.0.x"
container:
  imageDigest: "sha256:<digest>"
databaseSchemaVersion: "V042"
featureFlags:
  newOrderParser: false
```

Giá trị là placeholder. Trong hệ thống thật, cần dùng digest/version chính xác được CI ghi tự động.

### 19.1. Rollback theo immutable artifact

Khi có lỗi, deploy lại **đúng artifact/image digest** đã được kiểm chứng. Build lại từ source cũ có thể cho kết quả khác do dependency dynamic, base image tag đã thay hoặc toolchain mới.

### 19.2. Tách release artifact và activation

Có thể deploy một artifact chứa cả logic cũ/mới nhưng chỉ bật feature mới cho canary sau khi deploy ổn. Điều này giúp tách hai câu hỏi:

1. Artifact/runtime mới có chạy ổn không?
2. Logic mới có đúng và hiệu quả không?

Tuy nhiên, không phải mọi thay đổi runtime có thể được đặt sau feature flag; đổi JDK image đòi hỏi deployment strategy thực sự.

## 20. Rollback trong Kubernetes hoặc nền tảng triển khai tương tự

Ví dụ một lệnh có thể dùng khi deployment được quản lý bằng Kubernetes:

```bash
kubectl rollout status deployment/order-service -n production
```

Nếu revision trước còn được lưu và tương thích:

```bash
kubectl rollout undo deployment/order-service -n production
```

Lệnh này là **ví dụ về deployment rollback**, không bảo đảm:

- Database quay về schema cũ.
- Message đã phát được thu hồi.
- Cache/session format trở lại.
- Certificate cũ được khôi phục.
- In-flight request không tạo side effect.
- Container image cũ vẫn còn trong registry.

Không thực hiện lệnh production chỉ vì có ví dụ trong tài liệu; cần runbook của hệ thống, quyền truy cập và quyết định vận hành theo quy trình.

### 20.1. Đối với job và batch processing

Rollout của worker không giống web service:

- Job có đang xử lý batch không?
- Có checkpoint hoặc resume marker không?
- Có thể replay an toàn không?
- Có transaction/lock còn mở không?
- Message acknowledgment được ghi khi nào?
- Có thể chạy old/new consumers song song không?

Khi rollback, có thể cần dừng nhận việc mới, đợi hoặc hủy có kiểm soát tác vụ đang chạy, rồi mới chuyển image.

### 20.2. Đối với desktop Java client

Nếu nâng Java runtime đi kèm desktop installer, một số client đã được cập nhật và có thể offline. Downgrade phải xem:

- File/config format mới bản cũ còn đọc được không?
- Database local đã được migrate chưa?
- Updater có hỗ trợ cài lại phiên bản cũ?
- Server API còn phục vụ client cũ không?
- Chữ ký installer và quy trình update/rollback có hợp lệ không?

Rollback desktop thường cần **cửa sổ hỗ trợ nhiều client versions**, không chỉ đổi deployment phía server.

## 21. Roll-forward và rollback: chọn hướng theo bản chất lỗi

Không phải lúc nào rollback cũng là lựa chọn tốt nhất.

| Tình huống | Hướng thường cân nhắc |
|---|---|
| Canary JDK mới có regression rõ, data contract không đổi | Rollback về image runtime cũ |
| Config sai nhỏ, chưa có side effect | Tắt flag/rollback config hoặc fix-forward nhanh, theo rủi ro |
| DB schema mới đã ghi dữ liệu bản cũ không đọc | Tránh rollback code mù quáng; khôi phục compatibility hoặc roll-forward |
| Lỗi security do certificate yếu | Ưu tiên sửa certificate/endpoint thay vì hạ chính sách |
| Event v2 đã được phát rộng | Giữ consumer đọc được v2 hoặc dùng adapter; không quay về consumer cũ thiếu hỗ trợ |
| Tăng CPU nhẹ chưa đủ mẫu | Giữ canary, thu thập thêm dữ liệu; không vội mở rollout |
| Sai tiền/authorization | Dừng rollout ngay, cô lập ảnh hưởng và áp dụng quy trình xử lý sự cố |

Một **rollback plan** tốt phải cho phép nói “không thể rollback tự động an toàn sau điểm X”. Khi vượt điểm đó, cần kế hoạch roll-forward hoặc phục hồi chuyên biệt.

## 22. Khái niệm điểm không thể quay lui

Một số hệ thống có **point of no return**: sau khi thay đổi hoặc dữ liệu được ghi tới mức nhất định, old artifact không còn tương thích.

Ví dụ:

```text
T0: Thêm cột mới (old vẫn chạy)
T1: New code đọc cả hai format
T2: Backfill và hỗ trợ ghi tương thích
T3: Mọi client/consumer đã nâng
T4: Dừng ghi format cũ
T5: Drop cột cũ (old không thể chạy)
```

Từ T0 đến trước T5, rollback ứng dụng có thể tương đối an toàn nếu contract được giữ. Từ T5 trở đi, chỉ deploy lại old code không còn đủ.

### 22.1. Quy tắc trước khi vượt điểm này

- Có xác nhận mọi consumer cũ đã ngừng.
- Có backup và restore procedure được thử nghiệm.
- Có dữ liệu đối chiếu sau migration.
- Có quyết định phê duyệt contract phase.
- Có kế hoạch xử lý client còn offline hoặc batch chưa chạy.
- Có thông tin tương thích rõ trong release notes.

Việc chủ động ghi nhận điểm không thể quay lui giúp nhóm tránh hứa “rollback trong 5 phút” khi thực tế phải restore database nhiều giờ.

## 23. Observability: điều kiện cần để biết có nên tăng rollout

Thay JDK có thể đổi hành vi GC, logging, TLS, thread scheduling và JNI/native calls. Nếu không có metrics, một canary chỉ tạo cảm giác an toàn.

### 23.1. Metrics kỹ thuật

- Startup time, readiness failures, crashes/restarts.
- CPU, memory, heap allocation và GC pauses.
- Thread states, virtual threads nếu có sử dụng.
- Latency p50/p95/p99 theo endpoint.
- Error rate theo loại exception.
- Database pool utilization, waiters và timeouts.
- Queue lag, dead-letter messages và retries.
- Outbound HTTP/TLS failures.
- Logging/tracing agent health.
- Container throttling và OOM kills.

### 23.2. Metrics nghiệp vụ

- Tỷ lệ thanh toán thành công.
- Đơn hàng ghi nhận/hoàn tất.
- Tỷ lệ authorization thất bại.
- Số event bị xử lý trùng.
- Độ trễ đồng bộ tồn kho.
- Chênh lệch tổng tiền hoặc dữ liệu đối soát.

Một ứng dụng có CPU thấp và HTTP 200 nhiều hơn nhưng ghi sai đơn hàng vẫn phải bị rollback/khắc phục.

### 23.3. Log có khả năng phân nhóm

Log nên bao gồm release version, deployment group, correlation ID và relevant dependency/service identifier. Không log token, private key hoặc dữ liệu nhạy cảm để dễ debug.

Với canary, phân biệt rõ log/metric của old và new release để không đánh đồng tất cả dữ liệu.

### 23.4. JFR và profiling có kiểm soát

Java Flight Recorder và các profiler thích hợp có thể giúp điều tra thay đổi allocation, CPU, blocking hoặc GC. Tuy nhiên, đây là công cụ quan sát bổ sung, không thay thế SLO và functional correctness.

## 24. Kịch bản tổng hợp: nâng Order Service từ Java 11 lên Java 17

Giả sử Order Service:

```text
Java 11
Spring-based application
PostgreSQL via JDBC pool
HTTP call to Payment Gateway
Kafka order-events.v1
Container deployment
```

Mục tiêu là chạy runtime JDK 17, chưa thay framework hay message schema.

### Bước 0 — Baseline

- Ghim image Java 11 đang chạy bằng digest.
- Lưu startup/health, p95/p99 latency, error rate, DB waiters, Kafka lag.
- Chạy regression/contract tests hiện tại.
- Ghi JDK vendor/update, dependency graph, agent versions.

### Bước 1 — Chuẩn bị CI JDK 17

Giữ production Java 11. Chạy unit/integration tests với runtime JDK 17. Phát hiện các vấn đề như reflection bị chặn, certificate constraints hoặc dependency incompatible.

**Rollback:** không có thay đổi production. Nếu test fail, dừng bước này và sửa trong môi trường phát triển.

### Bước 2 — Nâng dependency không tương thích

Ví dụ nếu một bytecode agent cũ không hỗ trợ class file/JDK mới, nâng agent ở một commit/phát hành riêng. Giữ Java 11 runtime production nếu agent version mới vẫn hỗ trợ, hoặc chỉ kiểm chứng trong CI nếu không.

**Bằng chứng:** instrumentation vẫn có traces, test pass và overhead trong giới hạn.

### Bước 3 — Tạo image runtime JDK 17

Dùng cùng source và dependency đã kiểm chứng. Kiểm tra startup, keystore, truststore, resource paths, native libraries và JVM flags.

**Rollback:** giữ Java 11 image và config tương ứng.

### Bước 4 — Canary một nhóm instances

Chuyển một phần traffic sang image mới, không đổi event schema hoặc DB schema.

**Quan sát:** request success, payment errors, timeout, GC, CPU, latency, Kafka lag và business metrics.

### Bước 5 — Tăng rollout có gate

Chỉ mở 20%, 50%, 100% khi đủ dữ liệu và không vượt stop condition. Tỷ lệ là ví dụ; lịch trình thật tùy tải.

### Bước 6 — Giữ cửa sổ rollback

Giữ image cũ, manifests và khả năng chuyển traffic về trong một thời gian đã thống nhất. Theo dõi tác động chậm như batch job, certificate renewal và scheduled tasks.

### Bước 7 — Dọn cấu hình cũ

Khi ổn định, bỏ những JVM flags lỗi thời, cập nhật runbook, xóa workaround không còn cần. Sau đó mới bắt đầu bước độc lập để nâng framework hoặc chuyển Jakarta nếu thuộc roadmap.

**Điểm mạnh của lộ trình:** khi lỗi xuất hiện ở bước 4, có thể chủ yếu điều tra runtime JDK và môi trường triển khai thay vì hàng loạt thay đổi framework và dữ liệu.

## 25. Kịch bản tổng hợp: đổi từ thread pool sang virtual threads

Đổi mô hình thực thi là thay đổi hành vi concurrency, nên cần đặc biệt chú ý khả năng rollback.

Ví dụ code trước:

```java
ExecutorService executor =
        Executors.newFixedThreadPool(64);
```

Ứng viên trên JDK 21:

```java
ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor();
```

Đây không chỉ là đổi loại executor: fixed pool có thể đang ngầm giới hạn số lời gọi database hoặc HTTP. Virtual threads có thể khiến hàng nghìn task truy cập tài nguyên cùng lúc.

### 25.1. Chia bước hợp lý

1. Đo baseline số active workers, queue depth, DB pool waiters và p99 latency.
2. Bổ sung semaphore/rate limiter cho downstream khan hiếm.
3. Viết test timeout/cancellation và load/overload tests.
4. Bật virtual thread executor cho một endpoint I/O-bound qua config/flag nếu có thể.
5. Quan sát pinning/ThreadLocal/context propagation theo JDK thực tế.
6. Canary và so sánh cùng traffic mix.
7. Nếu regression, chuyển endpoint về executor cũ mà không phải đổi database schema.

### 25.2. Giới hạn rollback

Nếu trong lúc thử nghiệm có task ghi dữ liệu khác format hoặc tạo side effects trùng, tắt executor mới không đảo được những thay đổi đó. Vì vậy bước đổi executor nên **giữ nguyên data contract và idempotency logic**.

## 26. Kịch bản tổng hợp: chuyển Javax sang Jakarta theo hai môi trường

Giả sử ứng dụng cũ:

```text
Java 11 + Servlet container Javax
   |
   v
Orders API v1
   |
   v
Database schema hiện tại
```

Phiên bản mới:

```text
Java 17 + Servlet container Jakarta
   |
   v
Orders API v1 (giữ nguyên wire contract)
   |
   v
Database schema tương thích
```

### 26.1. Bước nhỏ không có nghĩa đổi được một servlet duy nhất

Trong cùng một container, `javax.servlet.Filter` không tự tương đương `jakarta.servlet.Filter`. Một số ranh giới type phải chuyển đồng bộ. Vì vậy **đơn vị nhỏ nhất khả thi** có thể là một WAR/service với Servlet contract đã đồng bộ, chứ không phải một class đơn lẻ.

### 26.2. Dùng blue-green theo container

Giữ old Javax application ở Blue và Jakarta application ở Green. Cho traffic thông qua gateway khi cả hai có cùng HTTP API.

Kiểm thử session/auth/cookie và các tích hợp khác. Nếu dùng session serialized qua Java classes khác package, có thể không chia sẻ state được; cần chiến lược session migration hoặc affinity phù hợp.

### 26.3. Hoãn thay database schema

Để rollback dễ, giữ data contract nhất quán trong bước chuyển container. Các thay đổi DB lớn được tách sang những bước expand-contract trước/sau với cửa sổ tương thích rõ.

## 27. Những sai lầm khiến bước chuyển không còn nhỏ

### 27.1. Gộp nhiều nâng cấp “tiện thể”

Một developer nâng JDK rồi nhân tiện nâng framework, database driver, JSON serializer và logging library. Mỗi thành phần đều có thay đổi hành vi riêng, làm tăng số giả thuyết cần kiểm tra.

Cách giảm rủi ro: ghi rõ phạm vi của từng pull request/release và lý do dependency nào bắt buộc phải đổi cùng nhau.

### 27.2. Chỉ đặt gate “build pass”

Compile time không chứng minh runtime compatibility, classloader, TLS, DB transaction, message schema hoặc hiệu năng. Cần test đúng mục tiêu.

### 27.3. Không giữ artifact cũ

Tag container đã bị ghi đè hoặc image cũ bị xóa khỏi registry. Kết quả là deployment rollback không thể thực hiện ngay khi cần.

Cần lưu immutable artifact/digest và xác minh quyền truy cập trước rollout.

### 27.4. Có runbook nhưng chưa thử

Một câu “chạy rollout undo” không đủ nếu data schema đã đổi. Phải diễn tập rollback trên staging hoặc environment có tính chất dữ liệu/traffic đại diện.

### 27.5. Gọi thay đổi database phá vỡ tương thích là “minor”

Thêm cột nullable có thể là additive. Drop cột, rename trực tiếp hoặc thay semantics enum có thể khiến bản cũ không chạy. Phạm vi tác động quan trọng hơn kích thước migration script.

### 27.6. Canary thiếu tính đại diện

Canary chạy toàn request nhẹ, chưa kích hoạt đường thanh toán hoặc batch. Kết quả không thể dùng để xác nhận các flow chưa được kiểm chứng.

### 27.7. Dừng monitoring quá sớm

Một số lỗi chỉ xuất hiện khi scheduled job chạy mỗi ngày/tuần, TLS certificate renew hoặc cuối kỳ kế toán. Cần cửa sổ quan sát tương ứng chu kỳ nghiệp vụ.

### 27.8. Trộn lỗi nền tảng với lỗi nghiệp vụ

Trong canary, một downstream đang outage trên cả old/new group. Nếu chỉ nhìn error rate new release, có thể rollback nhầm. Cần so sánh control cohort và xác định nguyên nhân.

### 27.9. Đặt flag nhưng không biết ai tắt

Flag không có owner, audit trail hoặc runbook có thể làm giảm giá trị rollback. Cần quyền điều khiển và điều kiện kích hoạt rõ.

### 27.10. Xóa hỗ trợ bản cũ trước khi hết rollback window

Xóa dependency, schema hoặc API cũ quá sớm có thể biến rollback từ một thao tác deploy thành một dự án khôi phục dữ liệu. Contract phase phải là bước cuối riêng biệt.

## 28. Checklist trước khi phê duyệt một bước migration

### Trước khi bắt đầu

- [ ] Có một mục tiêu chính và giả thuyết kiểm chứng được.
- [ ] Đã liệt kê chính xác những biến thay đổi.
- [ ] Đã xác định phạm vi service/module/traffic cohort.
- [ ] Đã kiểm tra các hợp đồng API, event, database và file format liên quan.
- [ ] Đã biết bước này reversible, conditionally reversible hay irreversible.
- [ ] Đã có baseline metrics và test phù hợp.
- [ ] Đã ghi JDK/toolchain/framework/container versions cụ thể.
- [ ] Đã lưu artifact/image digest và config trước thay đổi.
- [ ] Đã xác định tiêu chí pass, stop và rollback.
- [ ] Đã có owner, người phê duyệt và thời điểm quyết định.

### Trước khi tăng rollout

- [ ] Unit/integration/contract tests đã chạy đúng runtime mục tiêu.
- [ ] Happy path và negative path đã được kiểm tra.
- [ ] Data schema tương thích với old/new trong rollback window.
- [ ] Canary nhận traffic đủ đại diện.
- [ ] Đã so sánh control cohort và baseline.
- [ ] Không có lỗi bảo mật hoặc mất dữ liệu nghiêm trọng.
- [ ] Latency, throughput, GC, CPU và downstream saturation trong ngưỡng.
- [ ] Có khả năng dừng nhận việc mới và xử lý in-flight tasks.
- [ ] Rollback path đã được diễn tập hoặc có bằng chứng khả thi.

### Trước khi kết thúc cửa sổ rollback

- [ ] Đã đủ thời gian quan sát batch/cron và luồng hiếm gặp.
- [ ] Old/new producer-consumer compatibility đã được xác nhận.
- [ ] Không còn client offline/worker cũ cần đọc data mới, hoặc đã có hỗ trợ.
- [ ] Backup/recovery plan đã được kiểm chứng.
- [ ] Không còn rollback dependency vào schema/artifact bị chuẩn bị xóa.
- [ ] Đã ghi release outcome, metrics và bài học từ canary.
- [ ] Có ticket riêng cho contract phase và xóa feature flags.
- [ ] Đã cập nhật runbook, owner và monitoring tương ứng.

## 29. Mẫu báo cáo kết quả một bước

Một báo cáo gọn nên đủ để nhóm vận hành quyết định tiếp tục hay dừng:

```text
STEP:
  order-worker-runtime-jdk17

CHANGE:
  Runtime JDK 11 -> 17
  Source/dependencies/message schema: unchanged

SCOPE:
  5% worker workload, one region

EVIDENCE:
  Contract tests: passed
  Integration tests: passed
  Processing success: stable vs control
  Queue lag: within SLO
  p95 latency: within pre-agreed limit
  TLS/DB failures: no regression detected

ROLLBACK READINESS:
  Old image digest: retained
  Message format old/new compatible: checked
  In-flight processing runbook: available
  Rollback rehearsal: completed in staging

DECISION:
  Proceed to next canary level, or hold/rollback based on gates

OWNER:
  Assigned migration owner and on-call team
```

Đây là mẫu minh họa, không phải kết quả đã đo của một hệ thống cụ thể. Mọi kết luận “passed”, “stable” hoặc “completed” trong báo cáo thật phải dựa vào bằng chứng tương ứng.

## 30. Nguyên tắc để chọn bước tiếp theo

Sau mỗi bước thành công, nên hỏi:

1. Rủi ro nào vừa được loại bỏ?
2. Điều gì vẫn chưa biết?
3. Bước tiếp theo có thể giữ nguyên những gì vừa được kiểm chứng không?
4. Nếu bước tiếp theo thất bại, chúng ta có thể trở lại trạng thái hiện tại không?
5. Chúng ta đã vượt một điểm không thể quay lui chưa?
6. Có cần thêm quan sát hoặc test trước khi tăng phạm vi không?
7. Một dependency/framework bắt buộc phải đổi đồng thời hay chỉ vì tiện triển khai?
8. Thao tác rollback đã được thử bằng artifact và dữ liệu tương ứng chưa?

Thứ tự hợp lý thường ưu tiên những bước **tạo khả năng phát hiện lỗi** (test, metrics, reproducible build), tiếp theo là những bước **giảm phụ thuộc legacy** (dependency updates, adapter boundaries), rồi mới tới các bước có thay đổi runtime, framework và data contract lớn.

Không có một thứ tự bất biến cho mọi tổ chức. Yêu cầu bảo mật khẩn cấp hoặc hết hạn hỗ trợ có thể buộc ưu tiên một thay đổi rủi ro; khi đó càng cần giới hạn phạm vi và chuẩn bị điều kiện dừng rõ hơn.

## 31. Kết luận

Một đợt nâng Java thành công không nhất thiết là đợt thay đổi lớn nhất; nó là chuỗi thay đổi mà **mỗi bước giải quyết được một vấn đề, tạo ra bằng chứng mới và giữ quyền quyết định cho bước sau**. Để làm được điều đó, cần tách những chiều khác nhau của migration—JDK build/compiler/runtime, dependency, container, JPMS, Jakarta, execution model và dữ liệu—thành các đơn vị triển khai có ranh giới rõ.

Trước mỗi bước, hãy viết giả thuyết và tiêu chí kiểm chứng, lưu artifact cũ, xác định phạm vi ảnh hưởng và chuẩn bị rollback thực tế. Với DB, event và persisted data, hãy thiết kế backward/forward compatibility cùng cửa sổ expand–migrate–contract; **đừng hứa rollback code khi bản cũ không còn đọc được dữ liệu mới**. Với rollout, kết hợp automated tests, canary/blue-green, observability và stop conditions.

Nguyên tắc cốt lõi của chiến lược chuyển đổi là: **đổi ít biến nhất cần thiết, đo đúng điều quan trọng, giới hạn thiệt hại khi sai và luôn biết cách trở về một trạng thái vận hành an toàn**. Khi mỗi bước đều có thể kiểm chứng và quay lui trong phạm vi đã công bố, nâng cấp JDK trở thành một quá trình kỹ thuật có kiểm soát thay vì một lần “big bang” khó dự đoán.
