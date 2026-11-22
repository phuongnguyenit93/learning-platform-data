# Xác định điều kiện hoàn tất và loại bỏ cấu hình chuyển tiếp

Trong một dự án **Java Advance Compatibility Migration**, việc ứng dụng khởi động trên JDK mới hoặc có một lần chạy unit test thành công chưa đủ để tuyên bố chuyển đổi hoàn tất. Hệ thống có thể vẫn cần `--add-opens` cho thư viện reflection cũ, còn nhánh đọc JSON V1, còn ứng dụng phụ chạy Java 8, chưa thử job cuối tháng, hoặc có một cờ vô hiệu hóa kiểm tra bảo mật nhằm giữ client legacy. Những thành phần này là **nợ chuyển tiếp** và có thể trở thành sự cố sau khi nhóm dự án kết thúc.

Để kết thúc một cuộc migration có kiểm soát, nhóm cần làm hai việc: **định nghĩa các điều kiện hoàn tất có bằng chứng** (*exit criteria*, *Definition of Done*) và **loại bỏ các cấu hình chuyển tiếp theo thứ tự an toàn**. Hai công việc liên quan nhưng không trùng nhau. Có thể đạt mục tiêu triển khai JDK mới trước, rồi phải tiếp tục duy trì cửa sổ tương thích để phục vụ dữ liệu/consumer cũ. Chỉ khi những phụ thuộc này đã hết hoặc được chuyển thành ngoại lệ chính thức thì mới có cơ sở đóng chương trình.

Bài học hướng dẫn xây dựng bộ tiêu chí nghiệm thu, xác định tuổi thọ và chủ sở hữu của compatibility flags, xử lý dual-read/dual-write, adapters, legacy JDK/Jakarta settings, tổ chức canary và rollback, cùng các bằng chứng vận hành cần lưu trước khi đánh dấu migration hoàn tất.

## 1. Phân biệt “chạy được” với “đã chuyển đổi xong”

Giả sử service đã đổi từ JDK 8 sang JDK 17. CI build xanh, API trả HTTP 200, container khởi động ổn. Nhưng:
- Startup vẫn truyền `--add-opens=java.base/java.lang=ALL-UNNAMED`.
- `order-worker` chạy một lần mỗi tháng vẫn dùng Java 8.
- Bản ghi JSON cũ vẫn chỉ đọc được bằng deserializer legacy.
- Một plugin build dùng dependency override không còn được nhà cung cấp hỗ trợ.
- Production và DR dùng hai JDK khác nhau.
- Rollback của phiên bản mới chưa được thử với dữ liệu mà nó vừa ghi.
- TLS được cho phép hạ chuẩn để một đối tác cũ tiếp tục kết nối.

Không thể tuyên bố “migration completed” chỉ từ việc main service đã khởi động. Có bốn mốc cần báo cáo riêng:

| Mốc | Ý nghĩa | Bằng chứng minh họa |
|---|---|---|
| **Build migrated** | Mã và dependency biên dịch với toolchain/target đã chọn. | Artifact provenance, compile/test build logs. |
| **Runtime migrated** | Workload thực sự chạy trên runtime đích. | Java version telemetry của API, batch, consumer, DR. |
| **Compatibility proven** | Hợp đồng API/dữ liệu/hành vi được kiểm chứng trong cửa sổ hỗn hợp. | Golden fixtures, contract/integration tests, canary results. |
| **Migration closed** | Nợ chuyển tiếp đã được gỡ hoặc có ngoại lệ chính thức, vận hành và handoff xong. | Cleanup PR, metrics, ADR, owner sign-off. |

Một đơn vị có thể ở mốc 2 trong khi cả hệ thống chưa đạt mốc 4.

## 2. Exit criteria là một hợp đồng kiểm chứng

Một tiêu chí hoàn tất tốt phải trả lời:
1. **Đối tượng:** component, service, client, database, CI job hay toàn chương trình?
2. **Phạm vi:** môi trường, release, runtime, tenant, region, traffic và dữ liệu nào?
3. **Điều kiện:** trạng thái hoặc ngưỡng nào được chấp nhận?
4. **Phương pháp:** test, metrics, query, artifact audit hay xác nhận thủ công?
5. **Bằng chứng:** link build/deployment, test report, dashboard, diff, issue, chữ ký duyệt?
6. **Owner:** ai kiểm tra và ai xử lý khi không đạt?
7. **Thời gian:** cần quan sát bao lâu để bao phủ tác vụ hiếm và dữ liệu tồn tại lâu?
8. **Ngoại lệ:** điều gì chưa đạt nhưng được chấp thuận có hạn, kèm expiry?

Một câu “không còn lỗi đáng kể” không đo được. Tốt hơn:

> Trong cửa sổ quan sát được SRE và chủ sở hữu nghiệp vụ phê duyệt, toàn bộ instance thuộc scope chạy JDK đích; tỷ lệ lỗi và độ trễ của các giao dịch chính đáp ứng ngưỡng đã định nghĩa; không có lỗi compatibility mới chưa được phân loại; mọi trường hợp phụ thuộc runtime cũ đều có ticket ngoại lệ và chủ sở hữu.

Cụ thể con số, thời gian quan sát, phạm vi traffic phải được dự án quyết định. Không có tiêu chí phần trăm hay số ngày chung phù hợp cho mọi hệ thống.

## 3. Xác định phạm vi hoàn tất trước khi bắt đầu dọn

Một chương trình nâng JDK/framework có thể bao gồm:

```text
Migration Program
    |
    +-- Source + build + dependency
    |
    +-- Runtime + packaging + CI
    |
    +-- Business behavior + security
    |
    +-- API + data + protocol
    |
    +-- Operations + performance + DR
    |
    +-- Transitional configuration cleanup
    |
    +-- Evidence + ownership + closure
```

Inventory cần liệt kê cả:
- API services, CLI, scheduler, batch, message consumers và offline workers.
- Toolchains, compiler runtime, test JVM và container runtime.
- Regions, environments, failover/DR và các image đang chạy.
- Framework/BOM, plugin và dependency versions **đã resolve thực tế**.
- HTTP, database, queue, cache, file và backup contracts.
- Các thiết lập tạm đưa vào để chạy song song legacy/new.
- Owner, deadline, ngày review và rollback dependencies.

Một workload chỉ chạy khi sự cố DR xảy ra vẫn có thể quyết định liệu chương trình đã đủ điều kiện đóng hay chưa.

## 4. Ma trận tiêu chí nghiệm thu

| Nhóm | Điều kiện nên chứng minh | Bằng chứng phù hợp |
|---|---|---|
| Source/build | Toàn bộ module trong scope build đúng baseline. | CI report, compiler/toolchain configuration. |
| Dependency | Không còn tổ hợp không hỗ trợ hoặc override vô chủ. | Resolved dependency tree, BOM audit. |
| Runtime | Workload thực chạy JDK đã cam kết. | Process/deployment inventory, JVM runtime metrics. |
| Binary/linkage | Không còn lỗi thiếu class/method/module trên đường chạy thực. | Integration test, log/alert theo release. |
| Behavior | Hợp đồng nghiệp vụ và error handling còn đúng. | Regression, E2E, business comparison. |
| Data | V1/V2 records và schema đáp ứng hợp đồng. | Golden fixtures, reconciliation, restore drill. |
| Security | Không còn security exception ngoài whitelist được phê duyệt. | Security tests, flags/advisory review. |
| Performance | Throughput, latency, memory, GC đạt ngân sách. | Load tests và production dashboard. |
| Operations | Alert, runbook, backup, rollback hoặc forward-fix đã thực hành. | Incident rehearsal, SRE sign-off. |
| Cleanup | Flags/adapters/legacy writers không còn phụ thuộc. | Metrics, code/config diff, deployment audit. |
| Governance | Rủi ro tồn dư có owner, quyết định và expiry. | ADR, change record, sign-off. |

Nên tách thành **cổng triển khai** (đủ an toàn để lên production), **cổng kết thúc cửa sổ tương thích** và **cổng đóng chương trình**. Không bắt nhóm phải gỡ decoder V1 ngay trong ngày deploy V2 nếu dữ liệu cũ vẫn còn.

## 5. Cấu hình chuyển tiếp là gì?

*Cấu hình chuyển tiếp* là cơ chế được thêm hoặc giữ lại **tạm thời** để nối hai thế hệ runtime, code, dữ liệu hoặc triển khai.

Ví dụ:
- JVM `--add-opens`, `--add-exports` cho thư viện chưa tương thích JPMS.
- Workaround cho JAXB/Java EE modules đã bị loại khỏi JDK.
- Parser/serializer đọc cả JSON/XML cũ và mới.
- Alias field cũ, dual-read/dual-write database hoặc queue.
- Feature flag chọn producer format V1/V2.
- Adapter giữa `javax.servlet.*` và `jakarta.servlet.*`.
- Compatibility HTTP routes hoặc endpoints cũ.
- Maven/Gradle dependency pin, profile/override tạm.
- Dockerfile có nhánh fallback Java 8/JRE layout cũ.
- TLS security exception cho đối tác chưa nâng.
- Traffic mirroring/canary routing dùng để đối chiếu.

**Không phải mọi cấu hình có tên `legacy` đều phải bị xóa.** Có thể đó là một chức năng có hợp đồng hỗ trợ lâu dài. Cần biết lý do, đối tượng sử dụng và chính sách sản phẩm trước khi coi nó là nợ tạm.

## 6. Phân nhóm cấu hình theo điều kiện rút bỏ

| Kiểu | Ví dụ | Điều kiện gỡ |
|---|---|---|
| **Temporary workaround** | `--add-opens` cho plugin reflection. | Plugin sửa/nâng, tests và canary không còn cần flag. |
| **Compatibility reader** | Đọc schema V1/V2. | Không còn dữ liệu V1 cần đọc, kể cả archive/restore. |
| **Rollout switch** | `newSerializerEnabled`. | Toàn bộ producer ổn định trên V2, rollback không cần bật lại branch. |
| **Operational bridge** | Proxy dịch endpoint V1 sang V2. | Client hợp lệ đã chuyển, hợp đồng V1 đã hết hỗ trợ. |
| **Dependency override** | Pin old transitive library. | Tổ hợp framework/library mới được kiểm thử hỗ trợ. |
| **Security exception** | Chấp nhận cipher/TLS version yếu. | Client đã chuyển, security owner duyệt bỏ ngoại lệ. |
| **Dual-write scaffold** | Ghi cả DB column cũ và mới. | Dữ liệu đối soát, không còn old reader/rollback dependency. |

Một tiêu chí “traffic V1 bằng 0 trong 24 giờ” có thể không phù hợp nếu có batch chạy một lần mỗi quý. Cần hiểu **nhịp sử dụng thực tế** và thời gian giữ dữ liệu.

## 7. Lập hồ sơ cho từng flag hoặc adapter

Một bản ghi nên có mã ID, vị trí, giá trị mặc định, lý do ra đời, owner, rủi ro nếu giữ/gỡ, điều kiện gỡ, tín hiệu quan sát, đường phục hồi, ngày review.

Ví dụ:

```yaml
id: MIG-TEMP-014
component: order-api
kind: jvm-flag
setting: "--add-opens=java.base/java.lang=ALL-UNNAMED"
reason: "Mapper legacy still uses deep reflection"
introducedIn: "jdk17-migration"
owner: "order-platform"
securityOwner: "security-team"
riskIfKept: "Unnecessary reflective access"
riskIfRemovedEarly: "Mapper startup/runtime failure"
removalGate:
  - "Upgrade mapper to a supported version"
  - "Run integration suite without flag"
  - "Canary under representative workload"
telemetry:
  - "Reflection errors by release"
rollback:
  - "Redeploy previously approved JVM configuration"
reviewBy: "Next migration checkpoint"
status: "temporary"
```

Đây là mẫu theo dõi nội bộ, không phải chuẩn metadata có sẵn của Java/Maven/Gradle. Mỗi setting nên có **người chịu trách nhiệm xóa**; nếu không có owner, cấu hình tạm rất dễ trở thành phụ thuộc vĩnh viễn.

## 8. Tiêu chí source code và dependency

Kiểm tra:
1. Mọi module trong scope biên dịch bằng toolchain hợp lệ.
2. Compiler target như `--release 17` tương ứng minimum runtime cam kết.
3. Không còn import JDK internals hoặc API bị loại ngoài danh sách ngoại lệ.
4. BOM/dependency graph không có tổ hợp unsupported.
5. Annotation processors, plugins và bytecode libraries hỗ trợ runtime đích.
6. Generated code không tự sinh lại các API cũ sau mỗi build.
7. Tất cả build artifact có version, commit và provenance.

Ví dụ Maven:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Gradle Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

`--release` không chọn JVM thực thi unit tests và không bảo đảm dependency JARs cũng tương thích với runtime 17. Cần kiểm thử trên runtime mục tiêu riêng.

## 9. Tiêu chí runtime và deployment

Dự án có thể có API, background jobs, scheduler, event consumers, CLI và DR image. Cần đo JDK của **tiến trình đang chạy**, không chỉ JDK trên CI agent.

Ví dụ:

```java
public final class RuntimeInfo {
    public static void main(String[] args) {
        System.out.println("Java version: "
            + System.getProperty("java.version"));
        System.out.println("Java home: "
            + System.getProperty("java.home"));
        System.out.println("Java vendor: "
            + System.getProperty("java.vendor"));
    }
}
```

Nếu dùng Maven Toolchains hoặc Gradle Test `javaLauncher`, test JVM có thể khác JVM chạy build tool. Nếu production có rolling deployment và vùng dự phòng, cần kiểm tra **toàn bộ workload thuộc scope**, không chỉ phần lớn instances.

Tiêu chí “không còn JDK 8” phải nêu phạm vi rõ; nếu còn batch cũ ngoài scope, phải ghi nó thành dependency/exclusion có hạn hoặc chuyển vào kế hoạch riêng.

## 10. Tiêu chí hành vi và giao thức

Một ứng dụng có thể biên dịch nhưng thay đổi ở:
- Encoding, locale, timezone và date formatting.
- TLS/truststore/security providers.
- Reflection, JPMS, module loading.
- JSON/XML serialization, null inclusion, numeric precision.
- Database schema, JDBC driver, transaction semantics.
- Retry, timeout, HTTP headers và error handling.
- Logging, GC, thread scheduling, performance.

Cần có contract tests đối chiếu với **điều được cam kết**, không chỉ output ngẫu nhiên của thư viện cũ. Ví dụ hai JSON numbers có cùng giá trị ngữ nghĩa nhưng khác raw bytes có thể vẫn khác nếu payload được ký.

Kiểm tra chiều tương thích:
- Consumer V2 đọc dữ liệu producer V1.
- Consumer V1 đọc V2 nếu rolling deployment/rollback vẫn cần.
- Dữ liệu lưu từ lâu còn được decode/restore theo yêu cầu.
- Các client offline hoặc scheduled jobs chưa chạy trong cửa sổ quan sát có được tính tới.

## 11. Tiêu chí bảo mật

Một migration không được hoàn tất chỉ bằng cách tắt validation hoặc làm mọi request thành `permitAll`. Cần kiểm tra:
- Các JVM flags mở module có còn cần thiết không.
- TLS protocol/cipher/hostname verification có bị hạ chuẩn không.
- Parser/deserializer có chấp nhận input không an toàn không.
- Authentication, authorization, CSRF, CORS và session policy còn đúng không.
- Dependency security advisories đã được phân loại/khắc phục chưa.
- Security exception còn lại có owner, expiry và biện pháp giảm thiểu không.

Nếu một workaround buộc phải tiếp tục, **đừng gọi nó là đã được dọn sạch**. Có thể đóng một scope với ngoại lệ chính thức nếu tổ chức cho phép, nhưng báo cáo phải ghi rõ nợ tồn dư, rủi ro và kế hoạch theo dõi. Không âm thầm biến ngoại lệ thành default.

## 12. Tiêu chí hiệu năng và độ ổn định

Nâng JDK có thể ảnh hưởng GC, JIT, memory layout, TLS handshake, concurrency và container ergonomics.

Thống nhất trước:
- Throughput của các luồng nghiệp vụ.
- P50/P95/P99 latency.
- Error rate và retry rate.
- CPU, heap/RSS, GC pause, thread count.
- Connection pool, queue lag, restart/OOM.
- SLO, ngân sách chi phí hạ tầng.
- Tải thử tương ứng và cửa sổ sản xuất cần quan sát.

Ví dụ **chỉ mang tính minh họa**:

| Chỉ số | Baseline | Ngưỡng nghiệm thu ví dụ |
|---|---:|---:|
| P99 latency | 400 ms | Không vượt 450 ms dưới tải so sánh được. |
| Error rate | 0,2% | Không tăng quá 0,1 điểm phần trăm. |
| Queue lag | 30 s | Không vượt ngưỡng SLO đã duyệt. |
| Container memory | 1,2 GiB | Có headroom và không OOM. |

Không lấy những ngưỡng ví dụ làm policy của mọi ứng dụng. SRE, team nghiệp vụ và release owner phải chốt theo độ quan trọng và đặc tính tải.
## 13. Dữ liệu lưu lâu dài phải có exit criteria riêng

Một số dữ liệu V1 vẫn tồn tại rất lâu sau khi producer đã ngừng ghi V1:
- Database record, serialized columns và audit events.
- Object storage hoặc archive.
- Queue, delayed messages và dead-letter queue.
- Cache TTL dài hoặc snapshot.
- Backup cần restore sau nhiều năm.
- Client offline đồng bộ lại theo định kỳ.
- Report/batch job chỉ chạy mỗi tháng/quý.

Khi nào có thể xóa V1 decoder? Không chỉ khi production traffic V1 bằng 0, mà khi **mọi đường đọc dữ liệu V1 còn được hỗ trợ** đã được xử lý:
1. Đã chuyển đổi dữ liệu còn tồn tại, hoặc có công cụ restore/migration độc lập.
2. Đã qua thời gian retention cần thiết hoặc có quyết định kết thúc hỗ trợ được thông báo.
3. Queues/dead-letter queues đã drain/convert theo chính sách.
4. Các client hợp lệ không còn tạo payload V1, kể cả offline consumers.
5. Các vùng dự phòng và backup restore paths đã được kiểm chứng.
6. Có bằng chứng đối soát record count, values, error cases và data integrity.

Nếu một bản backup năm trước chỉ đọc được bởi V1 decoder, việc loại decoder khỏi runtime chính có thể vẫn hợp lý **nếu** có một restore tool được quản lý và kiểm thử riêng. Exit criterion phải mô tả rõ cách phục hồi, không mơ hồ “dữ liệu cũ không còn cần”.

## 14. Backward compatibility và forward compatibility

Giả sử producer/consumer phiên bản V1 và V2:

```text
                     Consumer V1      Consumer V2
Producer V1          Baseline         Backward read
Producer V2          Forward read*    Target operation

* Cần thiết khi còn consumer V1 hoặc rollback đòi hỏi.
```

**Backward compatibility**: consumer mới đọc được dữ liệu cũ. **Forward compatibility**: consumer cũ đọc được dữ liệu mới trong phạm vi contract đã quy định. Tính hai chiều quan trọng trong rolling deployment, asynchronous messaging và rollback.

Một mục tiêu hoàn tất cần nêu:
- Những phiên bản client nào hiện được hỗ trợ?
- Khi nào support V1 kết thúc?
- Producer mới có được phát trường/enum mà consumer cũ không hiểu?
- Sau rollback, code cũ có thể đọc record V2 đã được ghi không?
- Dữ liệu V1 nào phải tiếp tục đọc sau ngày gỡ legacy API?

Nếu câu trả lời là “không cần forward compatibility”, phải đảm bảo triển khai không còn đường đi nào buộc consumer cũ đọc dữ liệu mới.

## 15. Cửa sổ tương thích có điểm bắt đầu và kết thúc

Một lộ trình thường có:

```text
V1 baseline
     |
     v
Expand: deploy reader hỗ trợ V1 + V2
     |
     v
Migrate: chuyển producer V1 -> V2 từng phần
     |
     v
Observe: đo traffic/data V1 còn lại
     |
     v
Contract: gỡ writer V1, adapter/reader V1 theo từng gate
     |
     v
Close: dọn flags, docs và handoff
```

**Compatibility window** là thời gian hai thế hệ cùng tồn tại. Nó phụ thuộc:
- Rolling rollout/canary duration.
- Client update cadence, mobile/offline clients.
- Queue retention, retry/poison messages.
- Database/archive/backup retention.
- DR environment và failover readiness.
- Sự kiện hiếm như báo cáo cuối năm.
- Khoảng thời gian mà tổ chức còn cam kết rollback code về V1.

Ví dụ, nếu thiết bị offline có quyền gửi dữ liệu sau 90 ngày, bảy ngày không còn traffic V1 có thể chưa đủ để tuyên bố bỏ được reader. Nếu consumer chỉ chạy đầu mỗi quý, cửa sổ quan sát phải bao phủ trường hợp đó hoặc có kiểm thử kích hoạt chủ động.

## 16. Rollout flag khác compatibility flag

Hai loại cờ phổ biến:

- **Rollout flag:** chọn phần trăm traffic/tenant được trải nghiệm xử lý mới, ví dụ `useNewSerializerWriter`.
- **Compatibility flag:** cho phép xử lý input/behavior cũ trong thời gian chuyển, ví dụ `acceptV1Payload`.

Ví dụ:

```yaml
migration:
  useNewSerializerWriter: false
  acceptV1Payload: true
  routeLegacyApi: true
```

Một lộ trình đúng:
1. Deploy consumer đọc cả V1/V2 trước.
2. Bật writer V2 dần dần.
3. Theo dõi parse errors và metrics cho cả hai schema.
4. Khi toàn bộ producer ổn định trên V2, gỡ writer V1.
5. Chỉ gỡ reader V1 sau khi dữ liệu/consumer V1 đã hết trong phạm vi đã phê duyệt.
6. Cuối cùng bỏ flags và code branches không còn cần.

Không chuyển ba flags thành `false` cùng lúc chỉ vì chúng cùng có tiền tố `migration`. Mỗi cái có cổng nghiệm thu và deadline khác nhau.

## 17. Dual-write cần đối soát trước khi gỡ

Dual-write là ghi vào cả schema/store cũ và mới:

```text
                   Application
                    /       \
                   v         v
               V1 store    V2 store
```

Những nguy cơ:
- Ghi V1 thành công nhưng V2 lỗi, hoặc ngược lại.
- Retry tạo trùng bản ghi.
- Ordering của events khác nhau.
- Hai nơi lệch dữ liệu sau một thời gian.
- Backfill và write thời gian thực chồng chéo.
- Transaction không atomic khi đi qua hai storage systems.

Muốn dừng dual-write cần có:
- Reconciliation theo primary keys, checksum/semantic values hoặc các chỉ số phù hợp.
- Quy tắc giải quyết conflict và xử lý record lỗi.
- Monitoring cho partial writes và retry.
- Reader/consumer chính đã chuyển sang V2.
- Không còn consumer hợp lệ đòi writer V1.
- Rollback plan không phụ thuộc việc tiếp tục ghi V1.

Nếu ghi hai storage qua network mà không có distributed transaction, phải xác định eventual consistency/outbox/idempotency contract; chỉ so số lượng record bằng nhau không đủ chứng minh không mất dữ liệu.

## 18. Dual-read và tín hiệu fallback

Dual-read có thể dùng các cơ chế khác nhau:
- Thử V2, fallback V1 khi thiếu.
- Đọc V1 và V2 rồi so sánh kết quả trong shadow mode.
- Cho phép deserialize cả schema V1/V2 theo version marker.

Nếu chỉ đo HTTP 200, không biết bao nhiêu request còn đi qua V1 path. Nên quan sát:
- `legacy_reader_invocations`.
- `legacy_reader_success`.
- `legacy_reader_fallback`.
- `new_reader_success`.
- `unknown_format_rejections`.
- `schema_version_by_source`.

Tên metric chỉ là ví dụ. Không đặt user IDs, token hoặc payload raw trong metric labels. Cần đo theo service/tenant class/client version ở mức cardinality kiểm soát được, không lộ dữ liệu nhạy cảm.

Chỉ gỡ V1 reader khi đã xử lý các ca hiếm như archive restore, delayed messages, offline clients và rollback. Nếu có một công cụ restore riêng giữ V1 support, cần giao trách nhiệm duy trì nó lâu dài.

## 19. Tắt JVM flags tạm thời có kiểm soát

Trong Java 8 → Java 17+, một số thư viện cũ cần flags như:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
--add-exports=java.base/jdk.internal.misc=ALL-UNNAMED
```

Hai loại này phục vụ mục đích khác nhau: `--add-opens` cho deep reflection; `--add-exports` cho quyền truy cập package được module export tới target. Chúng không tự thay thế nhau và có thể phục vụ nhiều thư viện khác nhau.

Quy trình gỡ:
1. Xác định thư viện hoặc call stack thực sự cần flag.
2. Nâng/refactor library để dùng API được hỗ trợ.
3. Xóa đúng một flag trong test/staging configuration.
4. Chạy integration tests có đường reflection thực, không chỉ startup.
5. Canary với config không có flag.
6. Theo dõi `InaccessibleObjectException`, `IllegalAccessError`, serialization/binding failures.
7. Loại flag ở tất cả nơi khai báo: `JAVA_TOOL_OPTIONS`, CLI, Dockerfile, Helm/config maps, IDE runs, Maven Surefire, Gradle test JVM args.
8. Ghi bằng chứng về phiên bản thư viện và cấu hình đã đổi.

**Cảnh báo:** các tùy chọn `--illegal-access` thời JDK 9–16 đã có vòng đời thay đổi; không dùng chúng như giải pháp lâu dài cho JDK 17+. Còn `--add-opens` không phải lỗi tự thân trong mọi trường hợp: có thể có nhu cầu hợp lệ của một thư viện/công cụ đã được đánh giá. Hãy phân biệt setting tạm với exception được quản lý chính thức.

## 20. Gỡ các cấu hình build/JDK 8 không còn cần

Sau khi đã phê duyệt thay minimum supported JDK:
- Xóa build profiles chỉ phục vụ Java 8 khi không còn consumer.
- Bỏ `-source 8 -target 8` / `--release 8` nếu target thực sự được nâng.
- Xóa Maven `systemPath` trỏ `tools.jar`, `rt.jar`.
- Thay script copy `jdk/jre/` bằng runtime image phù hợp.
- Xóa `lib/ext`/endorsed mechanisms không còn được hỗ trợ.
- Nâng Maven/Gradle plugins và annotation processors.
- Loại dependency override dùng để né bug cũ sau khi có bản fix.
- Cập nhật IDE, CI matrix, Docker base image và release documentation.

Ví dụ Maven:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Ví dụ Gradle Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

Không thay `--release 8` bằng 17 nếu sản phẩm vẫn cam kết hỗ trợ Java 8. Việc xóa JDK cũ phải dựa trên quyết định support policy, không phải mong muốn làm cho build script ngắn hơn.

## 21. Gỡ tương thích Java EE / Jakarta theo nhóm

Khi chuyển từ Java EE namespace `javax.*` sang Jakarta EE `jakarta.*`, một số adapter có thể được giữ để hỗ trợ hai thế hệ:

```text
Old javax web adapter --> Domain contract <-- New jakarta web adapter
```

Trước khi xóa adapter cũ:
1. Không còn runtime/container hợp lệ phải nạp các interface `javax.servlet.*` tương ứng.
2. Framework, ORM, validation, CDI/JMS providers thuộc thế hệ target.
3. Các plugin/extension bên thứ ba đã nâng hoặc thay thế.
4. Không còn source/generated code tái sinh import cũ.
5. Public API contract không lộ kiểu cũ ở boundary.
6. Integration tests chạy trên container thực và không có `ClassNotFoundException`/`NoClassDefFoundError`.
7. Nếu còn service legacy riêng, boundary HTTP/queue vẫn hỗ trợ hợp đồng của nó hoặc đã có kế hoạch độc lập.

**Không thay tất cả `javax.*` bằng `jakarta.*`.** Các package như `javax.sql`, `javax.naming`, `javax.crypto` và `javax.tools` vẫn thuộc Java SE trong bối cảnh tương ứng. Cleanup phải phân loại đúng API owner.

## 22. Gỡ dependency pin và plugin compatibility override

Một dependency override tạm có thể được thêm khi nâng framework, ví dụ ép transitive library về bản cũ để giữ plugin cũ. Về lâu dài, nó có thể gây:
- Mismatch với BOM/framework.
- `NoSuchMethodError` hoặc lỗi linkage khi framework gọi API mới.
- Security advisory chưa được vá.
- Phức tạp hóa dependency graph khiến lần nâng tiếp khó hơn.

Một kế hoạch gỡ pin:
1. Kiểm tra version thực tế được resolve, không chỉ version khai báo.
2. Đọc support matrix của framework/plugin với dependency mới.
3. Bỏ pin ở nhánh thử nghiệm.
4. So sánh dependency tree trước/sau.
5. Chạy compile, integration, binary linkage và runtime tests.
6. Canary nếu phụ thuộc chạm đường quan trọng.
7. Xóa pin cùng ghi chú/documentation lỗi thời.

Nếu pin vẫn cần thiết, ghi version mục tiêu, chủ sở hữu và lý do cụ thể; không để giá trị vô danh trong `pom.xml` hoặc `build.gradle`.

## 23. Gỡ endpoint legacy cần đánh giá cả consumer lẫn dữ liệu

Một endpoint cũ có thể tiếp tục được dùng bởi:
- Mobile app chưa cập nhật.
- Partner integration với chu kỳ phát hành dài.
- Scheduled task hoặc webhook ít khi chạy.
- Hệ thống DR chỉ kích hoạt khi failover.
- Client offline gửi lại request cũ.
- Monitoring hoặc synthetic probes chạy ở môi trường riêng.

Để retire endpoint:
- Xác định API contract, thời gian thông báo và thời điểm hết hỗ trợ.
- Thu thập traffic metrics theo client/version với chính sách privacy phù hợp.
- Xác minh các consumer đã migrate hoặc bị ngừng hỗ trợ chính thức.
- Chạy test cho routing, authentication, authorization và error behavior.
- Đảm bảo gateway/cache/ingress không còn route ẩn tới phiên bản cũ.
- Dọn tài liệu, API specs, SDKs và monitoring sau khi xóa.

“Endpoint không có traffic hôm nay” không đủ nếu hợp đồng cho phép gọi theo mùa. Một số hệ thống cần thời gian deprecation dài và thông báo đối tác trước khi tắt.

## 24. Gỡ compatibility mode liên quan encoding, locale và timestamp

Nâng JDK có thể làm lộ phụ thuộc vào charset/timezone/locale defaults, ví dụ từ JDK 18 theo JEP 400, default charset được chuẩn hóa thành UTF-8 trong phạm vi được mô tả.

Đôi khi ứng dụng thêm:
- `-Dfile.encoding=...` để mô phỏng môi trường cũ.
- Formatter legacy cho date/time.
- Fallback parser chấp nhận timestamp theo local timezone.
- Custom decimal/coercion mode.
- Một lớp chuyển đổi dữ liệu từ encoding cũ.

Gỡ những lớp này chỉ khi:
1. Input/output contract có charset/timezone/format tường minh.
2. Dữ liệu lịch sử đã được chuyển hoặc vẫn có decoder có trách nhiệm riêng.
3. Client phụ thuộc format cũ đã chuyển.
4. Test có các trường hợp đa timezone, DST, locale, large numbers.
5. Không đổi dữ liệu nghiệp vụ do implicit default.

Không nên coi việc xóa flag `file.encoding` là tiến bộ nếu code vẫn đang dựa vào `Charset.defaultCharset()` cho một giao thức cần ổn định. Hướng bền vững là dùng charset tường minh ở ranh giới dữ liệu.

## 25. Khi nào một workaround được giữ lại thành cấu hình chính thức?

Không phải lúc nào có thể xóa hết nợ tạm trong cùng một release. Ví dụ một thư viện bên thứ ba chưa cung cấp bản hỗ trợ Jakarta mới hoặc một đối tác vẫn gửi định dạng đã được cam kết.

Có thể chấp thuận **ngoại lệ có quản trị** nếu:
- Có lý do nghiệp vụ hoặc hợp đồng cụ thể.
- Rủi ro được đánh giá và chấp thuận bởi người có thẩm quyền.
- Phạm vi ảnh hưởng được giới hạn.
- Có monitoring và biện pháp giảm thiểu.
- Có owner chịu trách nhiệm.
- Có ngày review và expiry/trigger cụ thể.
- Không ghi nhầm thành “đã gỡ hoàn toàn”.

Một trạng thái báo cáo hữu ích:

```text
Cleanup:
  removed: 18
  approved_exceptions: 2
  unresolved_blockers: 0
  unowned_items: 0
```

Các số là minh họa. Ngoại lệ được chấp thuận có thể cho phép kết thúc **một giai đoạn** của chương trình, nhưng vẫn phải công khai và được theo dõi; không được coi là bằng chứng không còn rủi ro.

## 26. Không xóa đường rollback trước khi hết rollback window

Một trap phổ biến:
- Deployment V2 hoạt động.
- Nhóm xóa V1 reader và old schema sau một ngày.
- Hôm sau phát hiện regression nghiêm trọng ở V2.
- Rollback V1 thất bại vì V2 đã ghi dữ liệu không tương thích.

Cần phân biệt:
- **Rollback code:** triển khai lại artifact/config cũ.
- **Rollback runtime:** quay lại JDK/container image cũ.
- **Rollback dữ liệu:** khôi phục/chuyển đổi dữ liệu đã thay schema.
- **Forward-fix:** giữ runtime hiện tại, triển khai bản sửa mà không lùi dữ liệu.

Đôi khi rollback dữ liệu là quá rủi ro, nên chọn forward-fix và kế hoạch khôi phục phù hợp. Dù chọn cách nào, exit criterion phải nêu **đường phục hồi được phê duyệt**, không chỉ nói “có backup”.

Một trình tự thường an toàn hơn:
1. Đã ổn định producer V2.
2. Hết cửa sổ rollback V1 theo quyết định được ghi nhận.
3. Không còn consumer V1.
4. Dữ liệu/schema cũ được xử lý.
5. Xóa compatibility code và đối chiếu khả năng restore.
6. Gỡ old schema/infra sau một quyết định riêng nếu là thay đổi khó đảo ngược.

## 27. Canary khi tắt flag và adapter

Không nên xóa nhiều workaround độc lập cùng một đợt nếu không thể xác định nguyên nhân khi regression xuất hiện.

Một quy trình:
1. **Prepare:** có test/metric cho chức năng mà flag đang ảnh hưởng.
2. **Disable in nonproduction:** bỏ flag ở test/staging và chạy suite tương ứng.
3. **Canary:** áp dụng trên một tập traffic/instance kiểm soát.
4. **Observe:** so sánh với baseline và các luồng hiếm liên quan.
5. **Expand:** tăng tỷ lệ instance/tenant.
6. **Remove:** xóa flag, code branch và tài liệu cấu hình cũ.
7. **Close:** xác nhận release mới không còn flag trong deployment thực.

Ví dụ:

```text
100% legacy flag enabled
           |
           v
     Canary: flag off
           |
     Metrics/contracts OK?
           |
     +-----+-----+
     |           |
    No          Yes
     |           |
Restore        Expand rollout
configuration     |
                   v
             Remove flag/code
```

**Tắt cờ runtime** và **xóa code hỗ trợ cờ** là hai thời điểm khác nhau. Nếu cần rollback bằng cách bật lại cờ, chưa nên xóa branch tương ứng. Nhưng không nên giữ code dead branch vô hạn sau khi cửa sổ rollback kết thúc.

## 28. Cổng kiểm tra trước khi xóa cấu hình

Một cổng tối thiểu cho từng item:
- [ ] Có owner và mục đích của cấu hình.
- [ ] Bằng chứng không còn consumer/đường chạy cần cấu hình.
- [ ] Dữ liệu lịch sử và retention đã được xử lý.
- [ ] Đã xác định đường rollback/forward-fix.
- [ ] Positive và negative tests quan trọng đều đi qua đường mới.
- [ ] Có metrics, alerts và cửa sổ quan sát phù hợp.
- [ ] Đã gỡ thử trong staging/canary.
- [ ] Dependencies/runtime phù hợp khi không có cờ.
- [ ] Security reviewer đã xem nếu setting liên quan quyền truy cập.
- [ ] PR thay đổi có reference tới ticket/decision.

Một item chưa đạt không nên bị xóa chỉ vì cả chương trình đang chịu áp lực đóng milestone. Nếu không thể gỡ, ghi blocker và người xử lý thay vì bỏ trống.
## 29. “Không còn dùng” phải được chứng minh bằng nhiều nguồn

Tuyên bố “flag không được dùng nữa” dễ sai nếu chỉ dựa vào một loại dữ liệu:
- Code search chỉ thấy source, không thấy environment variables trong deployment.
- Runtime telemetry chỉ thấy môi trường đã bật logging.
- Traffic metrics không thấy client offline chưa gửi request.
- Dependency report không thấy code được load qua reflection.
- Test coverage không có scheduled job chạy hàng quý.
- “0 errors” chưa chứng minh code legacy path không được thực thi.

Tốt hơn là tam giác chứng cứ:

```text
       Static evidence
       (source/config)
             /   \
            /     \
           v       v
 Runtime telemetry ---- Contract/integration testing
     (production)           (behavior)
```

Đối với data migration, bổ sung **storage inventory và reconciliation**. Đối với API retirement, bổ sung **client contract/support policy**. Đối với JDK runtime retirement, bổ sung **process/deployment inventory** ở mọi môi trường trong scope.

Không có bằng chứng tuyệt đối về mọi request có thể xảy ra trong tương lai. Exit criteria là một quyết định kỹ thuật dựa trên phạm vi hỗ trợ, dữ liệu có thể quan sát và rủi ro được người có trách nhiệm chấp nhận.

## 30. Không gỡ logging và metrics quá sớm

Một số telemetry được bổ sung tạm cho migration:
- Phiên bản Java đang chạy theo instance.
- Số lượt fallback vào parser V1.
- Số lần dùng API cũ.
- Cảnh báo unknown enum/schema.
- Authentication failures sau đổi security framework.
- Queue lag, dual-write divergence và cleanup errors.
- Lỗi JPMS/reflection.
- Latency P99 của JDK mới so với baseline.

Sau khi gỡ compatibility code, vẫn nên giữ một khoảng quan sát phù hợp đối với các metric quan trọng. Nếu xóa logging/alert cùng lúc với flag, nhóm có thể mất khả năng phát hiện regression.

Có thể tách:
- **Telemetry tạm:** metric chỉ đo một branch sắp bị xóa; sau khi đã chứng minh branch không còn và qua rollback window có thể xóa.
- **Telemetry vận hành lâu dài:** lỗi API, security, data integrity và latency; cần tiếp tục duy trì.

Metrics cũng có lifecycle: cần xóa dashboard, alert hoặc SLO reference không còn đúng sau khi đã cập nhật monitoring chính thức. Nhưng không dọn trước khi có khả năng quan sát bản mới.

## 31. Một bảng quyết định theo từng giai đoạn

| Giai đoạn | Điều kiện bắt buộc | Quyết định |
|---|---|---|
| **Go-live target** | Build/runtime/critical tests đạt, rollback plan có thể thực thi. | Cho phép rollout JDK/framework mới. |
| **Promote canary** | Không có regression về API/security, metrics trong ngân sách. | Mở rộng traffic/instances. |
| **End compatibility window** | Producer/consumer đã chuyển, dữ liệu và retention được xử lý. | Cho phép gỡ writer/adapter/reader cũ theo thứ tự. |
| **Remove transitional flags** | Các dependency mới chạy ổn không cần flags, có rollback đã định nghĩa. | Gỡ code/config nhánh tạm. |
| **Close program** | Mọi item được gỡ hoặc là ngoại lệ có owner/expiry, docs và handoff hoàn tất. | Đánh dấu hoàn thành chương trình. |

Không nên nhập tất cả thành một trạng thái “Done” vì sẽ khó phân biệt nguyên nhân chưa thể đóng. Ví dụ, code đã migrated nhưng client partner chưa nâng có thể là vấn đề phụ thuộc bên ngoài, không phải lỗi implementer.

## 32. Mẫu Definition of Done cho một service

Dưới đây là mẫu có thể điều chỉnh:

```yaml
migrationId: JAVA-COMPAT-2026-ORDER
component: order-api
source:
  jdk: "8"
  framework: "legacy-baseline"
target:
  jdk: "17"
  framework: "approved-supported-release"
scope:
  environments: [ci, staging, production, disaster-recovery]
  workloads: [api, consumer, nightly-batch]
build:
  compilerRelease: 17
  dependencyGraphReviewed: true
runtime:
  allInstancesTargetJdk: true
  scheduledJobsVerified: true
contracts:
  http: "passed"
  messaging: "passed"
  storedData: "reconciled"
security:
  negativeTests: "passed"
  exceptions: []
operations:
  rollbackDrill: "passed"
  dashboardsUpdated: true
cleanup:
  jvmReflectionFlagsRemoved: true
  legacyCodecWriterRemoved: true
  legacyCodecReaderRemoved: false
  oldReaderException:
    reason: "Archived data still within retention"
    owner: "data-platform"
    reviewTrigger: "Archive conversion complete"
evidence:
  ciBuild: "link-to-verified-ci-run"
  deployment: "link-to-production-release"
  compatibility: "link-to-contract-test-report"
  rollback: "link-to-drill-record"
decision:
  releaseGate: "passed"
  programClosure: "pending-exception-approval"
```

Đây là **hồ sơ quản trị minh họa**, không phải cấu hình được JVM đọc. Trong dự án thật, cần điền version, ID evidence và trạng thái đã kiểm chứng thay vì đánh dấu các trường `true` bằng tay khi chưa có dữ liệu.

Điểm đáng chú ý: một migration có thể qua release gate nhưng vẫn ở trạng thái program closure pending vì compatibility reader cần tồn tại thêm. Báo cáo minh bạch như vậy tốt hơn đóng giả tạo.

## 33. Sử dụng tiêu chí định lượng mà không biến thành chỉ tiêu sai

Một số chỉ số hữu ích:
- Tỷ lệ workload trong scope chạy JDK đích.
- Số deployment còn image JDK cũ.
- Số compatibility flags còn active.
- Số code path legacy còn được thực thi.
- Số records/messages V1 chưa chuyển.
- Tỷ lệ deserialize failures, dual-write mismatch.
- Số security exceptions đang mở.
- Test coverage của các integration critical paths.
- Số blockers vô chủ hoặc quá hạn.
- Số lần rollback drill thành công/thất bại.

Nhưng không nên lấy “0 flag” làm chỉ tiêu duy nhất nếu việc xóa flag khiến hệ thống mất backward compatibility đang được cam kết. Và cũng không nên chỉ nhắm “100% workload chạy JDK 17” mà bỏ qua việc chuyển đổi cả DR image, process khởi động thủ công hoặc data migration tooling.

Một thước đo tốt đi cùng **định nghĩa phạm vi** và **số tuyệt đối**. Ví dụ “100% (35/35 workload đã kiểm kê)” có ý nghĩa hơn “100%” không rõ mẫu số.

## 34. Điều kiện hoàn tất về tài liệu và ownership

Sau khi code/config đã ổn định, cần cập nhật:
- README/build instructions cho JDK và toolchain đích.
- Hướng dẫn local development.
- Base image và container build documentation.
- API/schema version và danh sách client được hỗ trợ.
- Runbook startup/shutdown/rollback.
- Debug guide cho lỗi JPMS, classpath, serializer và TLS.
- Dashboard/alerts và alert ownership.
- Sơ đồ architecture/dependency mới.
- On-call handoff và lịch patching JDK.
- Danh sách ngoại lệ còn hiệu lực và thời điểm xem lại.

Xóa workaround trong source nhưng không cập nhật runbook có thể khiến một người trực hệ thống bật lại cờ cũ khi có sự cố. “Completed” phải bao gồm cả **tri thức vận hành**.

Ngoài ra, khi migration project kết thúc, cần chuyển trách nhiệm các ngoại lệ còn mở về backlog/team vận hành chính thức, không để chúng thuộc một nhóm dự án đã giải tán.

## 35. RACI và người phê duyệt cổng đóng

Một phân chia mẫu:

| Vai trò | Trách nhiệm trọng tâm |
|---|---|
| Service owner | Đảm bảo hành vi nghiệp vụ và tính tương thích. |
| Platform/JDK owner | JDK distribution, modules, container/build toolchains. |
| Data owner | Reconciliation, retention, schema/backup/restore. |
| Security owner | Xem security flags, TLS, authentication và exception. |
| QA/test owner | Bằng chứng regression/contract coverage. |
| SRE/operations | Canary, metrics, alert, disaster recovery, rollback drill. |
| Release manager | Điều phối cổng go-live, compatibility window và closeout. |
| External client/partner owner | Lịch nâng cấp và thông báo deprecation. |

Không nhất thiết tổ chức nào cũng có nhiều vai trò như vậy; một người có thể đảm nhiệm nhiều vai trò. Quan trọng là mỗi cổng nghiệm thu có **người được giao trách nhiệm**, và quyết định chấp thuận rủi ro không bị đưa ra ngầm.

## 36. Ví dụ hoàn chỉnh: nâng Java 8 lên 17 và gỡ workaround

Giả sử một ứng dụng order gồm API, Kafka consumer, batch cuối tháng và DB có JSON columns.

### 36.1. Trạng thái ban đầu

```text
API: JDK 8
Consumer: JDK 8
Monthly Batch: JDK 8
JSON V1: all producers and readers
JVM flags: old JDK profile
Database: old schema
CI: Java 8
```

### 36.2. Sau khi triển khai bản V2 đầu tiên

```text
API: JDK 17
Consumer: JDK 17
Monthly Batch: still JDK 8
JSON writer: V2 behind feature flag
JSON reader: V1 + V2
Database: expanded schema
CI: build 17, tests 17
--add-opens: enabled for old mapper
```

Tại đây đã có tiến bộ rõ nhưng **chưa đủ điều kiện đóng**.

### 36.3. Đường hoàn tất

1. Nâng mapper lên phiên bản được JDK 17 hỗ trợ.
2. Gỡ `--add-opens` ở staging rồi canary.
3. Chạy batch cuối tháng bằng JDK 17 trên dữ liệu/fixture đại diện.
4. Chuyển producer JSON sang V2 toàn bộ.
5. Đo và xử lý mọi V1 payload trong queue, DB, archive.
6. Chờ hết cửa sổ rollback V1 theo kế hoạch; chạy restore drill.
7. Xóa V1 writer trước, V1 reader sau khi đủ điều kiện.
8. Loại Java 8 image và CI profile khỏi mọi workload trong scope.
9. Cập nhật docs/runbooks, dashboards, security exception inventory.
10. Người phụ trách business/data/security/SRE xác nhận các cổng riêng.

### 36.4. Dạng báo cáo trung gian

| Đối tượng | Trạng thái | Còn thiếu |
|---|---|---|
| API | Runtime migrated | Chưa gỡ flag reflective access. |
| Consumer | Runtime migrated | Cần đo V1 fallback. |
| Monthly batch | Pending | Chưa chạy trên JDK 17. |
| JSON writer | Partially migrated | Còn feature flag V1. |
| JSON reader | Dual support | Phụ thuộc archive retention. |
| DB schema | Expanded | Còn đối soát và rollback window. |

Điều kiện đóng chỉ được đánh dấu khi các hạng mục đã hoàn tất hoặc có ngoại lệ chính thức. Việc ghi trạng thái trung gian rõ ràng giúp Prime/release owner không đánh đồng tiến độ coding với trạng thái production.

## 37. Các sai lầm thường gặp

**“Build xanh nghĩa là hoàn tất.”** Không xác nhận runtime, dữ liệu, bảo mật, hiệu năng và rollout.

**“Đã chạy một ngày không lỗi nên bỏ backward compatibility.”** Có thể chưa bao phủ batch job, offline client, delayed queue và backup restore.

**“Gỡ flag không thấy lỗi startup tức là flag vô dụng.”** Lỗi reflection có thể chỉ xuất hiện ở đường code hiếm.

**“Gỡ writer và reader V1 cùng lúc.”** Dữ liệu V1 lưu lâu hoặc rollback code có thể vẫn cần reader.

**“Tắt dual-write khi số record bằng nhau.”** Không chứng minh values, ordering, idempotency và partial failure đúng.

**“Nới TLS/authorization tạm không cần ghi lại.”** Security exception phải có owner, scope, expiry và quyết định được duyệt.

**“Xóa mọi cờ có tên legacy.”** Một số cờ có thể phục vụ hợp đồng hỗ trợ chính thức, cần phân loại trước.

**“Gỡ cơ chế rollback càng sớm càng sạch.”** Cleanup quá sớm có thể làm hệ thống không thể phục hồi sau regression.

**“Không còn request trên dashboard nghĩa là mọi client đã nâng.”** Có thể thiếu telemetry hoặc client chỉ kết nối theo chu kỳ dài.

**“Xóa luôn metrics sau khi xóa flag.”** Mất khả năng giám sát regression trong cửa sổ tiếp theo.

**“Không còn Java 8 trong production chính.”** DR, command-line jobs hoặc plugin runtime vẫn có thể dùng Java 8.

**“Đưa mọi phần chưa xong vào ngoại lệ vô hạn.”** Ngoại lệ không có expiry/owner là nợ kỹ thuật thiếu quản trị, không phải closure đáng tin cậy.

## 38. Checklist đóng chương trình migration

- [ ] Có inventory đầy đủ các workload, environments và runtime trong phạm vi.
- [ ] Có Definition of Done với phạm vi, ngưỡng, evidence, owner và thời gian quan sát.
- [ ] Build/compile đã sử dụng toolchain và target được hỗ trợ.
- [ ] Runtime version được xác minh trên mọi deployment và job liên quan.
- [ ] Dependency graph/BOM/plugin và generated code được kiểm kê.
- [ ] API/data/protocol contract tests chạy trên runtime đích.
- [ ] Các trường hợp negative/security và failed inputs được kiểm thử.
- [ ] Performance/SLO đạt tiêu chí đã thống nhất dưới tải phù hợp.
- [ ] Backup/restore và rollback/forward-fix được xem xét, thực hành.
- [ ] Đã có dữ liệu về V1 clients, payloads, queue và archive retention.
- [ ] Không xóa reader/adapter cũ trước khi hết support/rollback window.
- [ ] Dual-write đã đối soát và có giải pháp cho partial failures.
- [ ] Mọi `--add-opens`/`--add-exports` tạm đều được gỡ hoặc quản lý ngoại lệ.
- [ ] Không còn script `rt.jar`/`tools.jar` hay Java 8 image ngoài scope được chấp thuận.
- [ ] Dependency pins/profiles/feature flags tạm đã được gỡ hoặc có owner.
- [ ] Không có security exception vô chủ hoặc quá hạn.
- [ ] Canary/rollout quan sát được và không tạo regression mới.
- [ ] Không còn code branch chết, dashboard/alert sai hoặc docs không cập nhật.
- [ ] Tất cả blocker có owner; các ngoại lệ tồn dư được phê duyệt và có review date.
- [ ] Có sign-off của những bên chịu trách nhiệm theo chính sách tổ chức.

## 39. Tài liệu tham khảo

- [JEP 261 — Module System](https://openjdk.org/jeps/261): JPMS, module path và bối cảnh tương thích khi nâng Java 9+.
- [JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396): bối cảnh quyền truy cập các API nội bộ.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): chính sách strong encapsulation trong những JDK hiện đại.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset ở JDK 18 và ảnh hưởng dữ liệu legacy.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): ví dụ cần loại bỏ dependency giả định module được JDK cung cấp.
- [Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/): các thay đổi giữa các thế hệ JDK và gợi ý migration.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xác định dependency graph đã resolve.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): kiểm tra dependencies và version resolution.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): ví dụ về framework security policy cần được kiểm thử trong migration.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): tham khảo khi retire adapters chuyển từ Java EE sang Jakarta.
- [Semantic Versioning](https://semver.org/): đánh giá phạm vi version upgrade; không thay release notes/compatibility matrix.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): nguyên tắc kiểm soát quyền và negative tests.
- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): xác định signals/monitoring phục vụ vận hành và release.
- [The Site Reliability Workbook](https://sre.google/workbook/): thực hành SLO, rollout, monitoring và vận hành.

## Kết luận

Một chương trình Java migration chỉ thực sự **hoàn tất** khi phạm vi đã được xác định, runtime và hành vi được kiểm chứng, dữ liệu/consumer cũ có lộ trình xử lý, rủi ro bảo mật được kiểm soát, vận hành có bằng chứng và mọi cấu hình chuyển tiếp được gỡ hoặc đưa vào danh sách ngoại lệ có trách nhiệm. Việc xóa cờ không phải mục tiêu tự thân: gỡ quá sớm có thể làm hỏng rollback và dữ liệu lịch sử, giữ quá lâu có thể khiến hệ thống phức tạp và thiếu an toàn. Cách kết thúc bền vững là đặt cổng nghiệm thu đo được, chia pha expand–migrate–contract, kiểm tra tác động từng flag, canary và quan sát trước khi xóa hẳn code/config, rồi ghi lại bằng chứng và ownership. Như vậy trạng thái “DONE” phản ánh một hệ thống thực sự có thể duy trì và nâng cấp tiếp, thay vì một lần build thành công.





