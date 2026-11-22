# Lập kế hoạch nâng phiên bản provider và Jakarta Persistence

Khi ứng dụng dùng Java Persistence API (JPA) hoặc Jakarta Persistence nhiều năm, thay đổi persistence provider (ví dụ một phiên bản Hibernate ORM sang phiên bản mới hơn, hoặc chuyển sang EclipseLink) có thể tác động tới toàn bộ đường đi của dữ liệu. Việc nâng từ nền tảng `javax.persistence` sang `jakarta.persistence` còn thay đổi ranh giới API, thư viện phụ thuộc và môi trường chạy.

Không nên coi nâng phiên bản là việc **đổi một dependency, sửa imports và khởi động lại ứng dụng**. Một ứng dụng có thể biên dịch thành công nhưng đọc sai enum, tạo ID bị trùng trong rolling deployment, thực hiện bulk UPDATE thiếu điều kiện tenant, hoặc sinh SQL khác khiến thời gian phản hồi tăng mạnh. Ngược lại, nhiều thay đổi SQL, proxy hoặc thứ tự flush là khác biệt triển khai hợp lệ và không nhất thiết làm sai nghiệp vụ.

Bài học thuộc chương **Vận hành và di trú** của chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào cách **lập kế hoạch nâng cấp thực tế**: xác định phạm vi, kiểm kê dependencies, chọn tổ hợp phiên bản, phân tích rủi ro dữ liệu, thử nghiệm trên schema và dữ liệu cũ, chuẩn bị triển khai từng giai đoạn, theo dõi production và quay lui an toàn.

Các nguyên tắc xuyên suốt:

1. **Lấy bất biến dữ liệu và nghiệp vụ làm tiêu chuẩn**, không lấy việc ứng dụng khởi động được làm tiêu chuẩn duy nhất.
2. **Chốt một tổ hợp stack được hỗ trợ**, gồm Jakarta Persistence API, provider, framework, JDK, JDBC driver, database, transaction manager.
3. **Tách nâng library khỏi di trú schema khi có thể**, giảm số biến thay đổi trong một lần.
4. **Không để hai bộ sinh ID không tương thích cùng ghi database** khi có rolling deployment.
5. **Migration phải xử lý dữ liệu hiện hữu**; test với schema trống là chưa đủ.
6. **Rollback phải xét cả code, schema và dữ liệu mới được ghi**, không chỉ triển khai lại binary cũ.
7. **Mỗi bước có điều kiện go/no-go**, bằng chứng test, telemetry và chủ sở hữu quyết định.

---

## 1. Phân biệt nâng provider, nâng đặc tả và nâng platform

Có ít nhất bốn loại thay đổi thường được gộp vào một yêu cầu “upgrade JPA”:

| Thay đổi | Ví dụ khái niệm | Thành phần chịu ảnh hưởng |
|---|---|---|
| Provider implementation | Hibernate bản cũ → Hibernate bản mới | SQL, dialect, generators, cache, query parser, proxies |
| Provider switch | Hibernate → EclipseLink | Extensions, enhancement/weaving, cấu hình và runtime behavior |
| API/specification | JPA `javax.persistence` → Jakarta Persistence `jakarta.persistence` | Imports, binary types, XML namespaces, metamodel, annotations |
| Platform/framework | Spring Boot/Spring Data hoặc Jakarta EE runtime đổi generation | Dependency alignment, transaction integration, class loading, JDK |

Một đợt nâng cấp có thể chứa cả bốn, nhưng kế hoạch phải ghi rõ **từng trục**, để biết lỗi phát sinh từ đâu.

### 1.1. Đổi API không nhất thiết thay business behavior

Một entity vẫn được persist, load và remove theo JPA semantics. Tuy nhiên, nếu application code dùng Jakarta APIs trong khi một third-party module vẫn dùng `javax.persistence.EntityManager`, hệ thống có thể không link hoặc khởi tạo được.

### 1.2. Đổi provider có thể giữ nguyên API

Nếu hai providers implement cùng Jakarta Persistence generation, nhiều repository/service interfaces vẫn compile. Nhưng custom annotations, query hints, custom types hoặc DDL generation có thể không portable.

### 1.3. Đổi framework có thể kéo provider mới

Một framework BOM/dependency management có thể thay provider version và transitives. Không nên nâng framework mà không kiểm kê thực tế persistence implementation sau dependency resolution.

---

## 2. Kết quả cần bàn giao của một kế hoạch nâng cấp

Một migration plan có thể review cần có các artifacts sau:

1. **Current-state inventory**: phiên bản thực đang chạy, không chỉ những gì khai báo trong build.
2. **Target-state matrix**: những tổ hợp API/provider/JDK/framework/driver/DB được hỗ trợ.
3. **Dependency and extension impact report**: những APIs, annotations và SQL riêng provider cần sửa.
4. **Data/schema impact report**: bảng, indexes, constraints, sequences, type mappings, data compatibility.
5. **Test/benchmark evidence**: baseline, compatibility suite, regression và performance budgets.
6. **Execution plan**: từng environment, bước chuyển đổi, owner, điểm kiểm tra, thời gian bảo trì nếu cần.
7. **Backward/forward compatibility strategy**: bảo đảm old/new binaries có thể cùng sống khi rolling deploy.
8. **Rollback/roll-forward strategy**: xác định khi nào có thể đảo ngược, khi nào phải phục hồi từ backup hoặc sửa dữ liệu.
9. **Production monitoring and runbook**: metrics, alerts, trigger dừng rollout, người chịu trách nhiệm.
10. **Post-migration closure**: xác minh dữ liệu, loại bỏ cấu hình cũ, cập nhật documentation và ownership.

Kế hoạch thiếu rollback khả thi hoặc không nêu phạm vi database writes trong giai đoạn chuyển phiên bản thường chưa đủ để đưa vào production.

---

## 3. Xác định phạm vi và mức độ rủi ro trước khi bắt đầu

Các câu hỏi đầu tiên:

- Có bao nhiêu services dùng chung database hoặc cùng entities?
- Có bao nhiêu applications/jobs độc lập vẫn chạy provider cũ?
- Có zero-downtime SLA hay được phép maintenance window?
- Có multi-tenant shared tables, schema per tenant hay database per tenant?
- Có dữ liệu tài chính, ledger, audit hoặc quy định retention đặc biệt?
- Có distributed transactions/JTA/XA hay chỉ local DB transaction?
- Có event/outbox và consumers phụ thuộc entity IDs/schema?
- Có nhiều database engines/dialects cần hỗ trợ?
- Có dữ liệu legacy do thủ tục SQL, batch jobs hoặc dịch vụ ngoài JPA ghi?
- Có API clients lệ thuộc ID format, enum values hoặc sort order không?

### 3.1. Phân loại service theo tác động

Một admin application ít dữ liệu với downtime cho phép có thể nâng đơn giản. Một order/payment service ghi liên tục, nhiều pods, nhiều consumers và ràng buộc tính đúng cao cần di trú theo giai đoạn, kiểm tương thích old/new và reconciliation.

### 3.2. Định nghĩa bất biến không được phá

Ví dụ:

~~~text
Invariant A: Một order_request_id chỉ tạo tối đa một Order trong tenant.
Invariant B: Tổng debit/credit trong một transfer phải cân bằng.
Invariant C: Mọi OrderLine phải tham chiếu đúng Order.
Invariant D: User không thấy row tenant khác.
Invariant E: Versioned update không ghi đè stale state.
Invariant F: Consumer không xử lý lại event như business effect mới.
~~~

Những bất biến này là tiêu chuẩn mạnh hơn “tất cả HTTP endpoints trả 200”.

---

## 4. Kiểm kê phiên bản hiện hữu

Lưu một baseline từ môi trường đang chạy:

| Thành phần | Cần ghi | Lý do |
|---|---|---|
| JDK | Version, vendor/runtime image | Bytecode, reflection, instrumentation |
| JPA/Jakarta API | Artifact và version | Package/API/feature contract |
| Provider | Exact implementation/version | SQL, generators, hints, mappings |
| Framework | Spring Boot/Data hoặc Jakarta EE version | Transaction, dependency BOM |
| JDBC driver | Artifact/version | Generated keys, batching, type conversion |
| Database | Engine, major/minor, topology | Dialect, SQL, isolation, failover |
| Migration tool | Flyway/Liquibase version | Schema state và rollout |
| Cache | L2/query cache provider/config | Eviction, serialization, tenant keys |
| Enhancement | Build-time/Load-time weaving plugin | Lazy loading, dirty tracking |
| Transaction owner | RESOURCE_LOCAL/JTA/Spring TM | Flush/commit boundaries |
| App topology | Pods/nodes, background workers | Rolling compatibility |
| Native SQL | Queries/stored procedures/views | Dialect coupling |

### 4.1. Xác minh runtime thay vì chỉ đọc build file

Khi ứng dụng có nhiều dependencies, version thực được load có thể khác version được khai báo trong module. Ghi runtime banner/class/package metadata, dependency resolution và persistence unit/provider thực.

### 4.2. Tìm transitive dependencies

Một thư viện cũ kéo `javax.persistence-api` vào app dùng `jakarta.persistence-api` có thể gây conflict/mismatch. Kiểm classpath/module path, annotation processors và dependency BOM.

### 4.3. Đặc biệt chú ý thư viện ít được nhìn thấy

Audit listeners, custom Hibernate types, metamodel generator, JSON mappings, spatial modules, validation integration, cache plugin và migration scripts có thể bị quên trong code review chính.

---

## 5. Chọn tổ hợp target, không chọn từng phiên bản độc lập

Ví dụ bảng ra quyết định:

| Trục | Baseline | Target đề xuất | Bằng chứng cần có |
|---|---|---|---|
| API | JPA/Jakarta hiện tại | Jakarta target | Provider thực sự hỗ trợ API |
| Provider | Current runtime | Target runtime | Compatibility notes + integration |
| Framework | Current | Supported release line | BOM alignment |
| JDK | Current | Supported JDK | Build và runtime compatibility |
| Driver | Current | Driver tương thích | Vendor matrix + DB test |
| Database | Current | Giữ nguyên hoặc migrate riêng | Dialect/DDL/SQL tests |
| Transaction manager | Current | Target compatible | Commit/rollback/timeout tests |
| Cache | Current cache stack | Target compatible | Provider cache integration |

### 5.1. “Mới nhất” không phải mục tiêu tự thân

Mục tiêu là phiên bản được vendor/framework hỗ trợ, còn nằm trong vòng hỗ trợ bảo mật, đáp ứng feature và vận hành. Không tự ép một Hibernate version vào framework BOM nếu dependency integration không hỗ trợ.

### 5.2. Không đoán compatibility theo major number

Một provider có thể implement một API generation nhưng vẫn yêu cầu JDK/runtime/driver cụ thể. Cần xác nhận combination trên tài liệu chính thức của từng thành phần tại thời điểm lập kế hoạch và thử nghiệm trên target thực.

### 5.3. Lập compatibility matrix được ký duyệt

Ghi rõ **supported**, **unsupported**, **needs experiment** cho từng combination. Một job fail trên tổ hợp không được hỗ trợ không chứng minh provider mới có bug.

---

## 6. Các thay đổi giữa JPA và Jakarta Persistence cần nhận diện

Từ các generations cũ dùng `javax.persistence` sang Jakarta Persistence 3.x dùng `jakarta.persistence`, thay đổi quan trọng nhất là package namespace và ecosystem alignment.

Trước:

~~~java
import javax.persistence.Entity;
import javax.persistence.EntityManager;
import javax.persistence.GeneratedValue;
~~~

Sau:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.GeneratedValue;
~~~

### 6.1. Không chỉ search-replace source imports

Phải xét:
- Entity annotations.
- Entity listeners và converters.
- Criteria API và static metamodel.
- `persistence.xml` version/namespace.
- `orm.xml` nếu dùng.
- Reflection strings/annotation scanning.
- Bytecode enhancement/weaving.
- JPA metamodel processors.
- Bean Validation, CDI, JTA, Servlet nếu cả platform chuyển generation.
- Third-party library APIs và method signatures.

### 6.2. `javax.persistence.EntityManager` và `jakarta.persistence.EntityManager` là hai types

Một module nhận `javax.persistence.EntityManager` không tự có binary compatibility với `jakarta.persistence.EntityManager`. Việc để cả hai API jars cạnh nhau không giải quyết type incompatibility.

### 6.3. Đừng nhầm mọi javax package đều đổi

Các Java SE packages như `javax.sql.DataSource` vẫn có vai trò riêng. Chỉ thay packages thuộc các Jakarta EE APIs tương ứng khi migration yêu cầu; không thực hiện global string replacement `javax` thành `jakarta`.

### 6.4. XML cần đổi có chủ đích

Namespace, schema version và entity mappings trong persistence descriptors phải tương thích API/provider target. Một file XML version cũ có thể khiến bootstrap fail dù annotation Java đã đổi.

---

## 7. Xây kế hoạch module-by-module cho namespace migration

Một ứng dụng nhiều modules:

~~~text
platform/
  domain-model/
  persistence-adapter/
  repository-api/
  business-service/
  rest-api/
  worker-jobs/
  reporting/
  integration-tests/
~~~

### 7.1. Lập thứ tự dependency

- Kiểm JDK/framework target.
- Nâng libraries dùng trực tiếp Jakarta.
- Chuyển domain entity annotations/converters/listeners.
- Chuyển repository/EntityManager/Criteria APIs.
- Nâng JPA processor/weaving/compiler plugins.
- Chuyển Spring/Jakarta EE transaction integration.
- Chuyển tests và fixture bootstrap.
- Chuyển background workers và modules đọc model.
- Kiểm packaging/runtime ở container.

### 7.2. Không duy trì một module entity hỗn hợp hai API tùy ý

Nếu cả old/new runtimes phải tồn tại tạm thời, cân nhắc tách deployables/adapters rõ ràng, build riêng theo profile, hoặc một compatibility layer được thiết kế có test. Không mặc định một JAR entity dùng annotations của cả hai generations sẽ hoạt động đúng ở mọi provider.

### 7.3. Giữ bước build reproducible

Dependency locks/BOM, container image tags và migration version phải được pin đủ để tái tạo lỗi. Tránh floating versions trong rollout.

---

## 8. Những API mới không mặc định tồn tại trong version cũ

Một số ví dụ mang tính version-sensitive:

- `GenerationType.UUID` được chuẩn hóa từ **Jakarta Persistence 3.1**.
- `Query.getSingleResultOrNull()` thuộc **Jakarta Persistence 3.2**.
- Các vendor có thể cung cấp UUID generators hoặc nullable result alternatives sớm hơn bằng extensions.

### 8.1. Định nghĩa compatibility floor

Nếu một library cần chạy trên Jakarta Persistence 3.0, source code của module portable không thể tùy ý gọi API 3.2 rồi trông mong runtime cũ đáp ứng.

### 8.2. Feature adapters

Tách những use cases cần API mới khỏi core compatibility modules. Các method khác nhau về API shape có thể được bọc bằng adapter được compile/test trên profile tương ứng.

### 8.3. Không dùng fallback reflection không kiểm soát

Reflection có thể che compile incompatibility và biến lỗi thành runtime failure. Nếu cần compatibility động, phải định nghĩa behavior/tests rõ.

---

## 9. Kiểm kê và phân loại provider-specific extensions

Những thành phần có thể phụ thuộc Hibernate hoặc EclipseLink:

| Nhóm | Ví dụ loại phụ thuộc | Hướng di trú |
|---|---|---|
| Annotations | `@Filter`, `@BatchSize`, custom fetch | JPA equivalent hoặc adapter |
| Custom types | `UserType`, JDBC type descriptor | Chuyển type system target |
| Generators | Sequence optimizers, UUID custom generator | Audit DDL và ID collisions |
| Query language | HQL extensions, vendor functions | JPQL portable/native query |
| Hints | Fetch/timeout/cache/lock hints | Map target features hoặc bỏ có kiểm |
| Cache | L2 region factory, query cache | Reconfigure và test invalidation |
| Enhancement | Hibernate enhancement/EclipseLink weaving | Cập nhật build/runtime |
| Statistics | Vendor metrics | Adapt telemetry |
| Schema | Auto-DDL, naming strategies | Migration scripts là source of truth |
| APIs | Unwrap `Session`, provider query APIs | Adapter riêng |

### 9.1. Chia thành ba danh mục

- **Có thể bỏ**: extension không còn nhu cầu.
- **Có thay thế chuẩn**: chuyển sang `EntityGraph`, Criteria, `AttributeConverter`, JPA locks...
- **Bắt buộc vendor-specific**: giữ adapter hoặc chấp nhận thay đổi kiến trúc.

### 9.2. Không ép provider mới hiểu property cũ

Một config như `hibernate.jdbc.batch_size` không phải thuộc tính chuẩn JPA; một provider khác có thể bỏ qua hoặc xử lý khác. Bỏ qua mà ứng dụng vẫn chạy chưa chắc là an toàn về throughput.

### 9.3. Ghi hiệu quả sau chuyển đổi

Nếu một Hibernate `@Filter` được thay bằng application-scoped JPQL predicate, phải chứng minh mọi path — kể cả find, native query, count, bulk DML — vẫn giữ tenant authorization.

---

## 10. Những mapping cần được review trước nâng

Danh sách ưu tiên:

1. `@Id`, `@GeneratedValue`, sequence/table/identity generators.
2. `@EmbeddedId`, `@IdClass`, `@MapsId`.
3. `@OneToOne`, `@ManyToOne`, `@OneToMany`, `@ManyToMany`.
4. Owning side, join columns/tables và cascades.
5. `orphanRemoval`, delete semantics và FK constraints.
6. `@Inheritance`, discriminators, mapped superclasses.
7. `@Access` field/property modes.
8. `@Version` optimistic locking.
9. `@Enumerated`, `@Convert`, `@Lob`, column definitions.
10. Temporal/decimal/UUID/JSON/custom types.
11. Entity listeners, validation và lifecycle callbacks.
12. Fetch graphs, lazy proxies, bytecode enhancement.
13. Named queries, native mappings, stored procedures.

### 10.1. Không sửa mapping chỉ để test green

Nếu provider cũ chấp nhận mapping không portable, provider mới báo lỗi có thể là cơ hội sửa mapping đúng chuẩn. Nhưng thay đổi phải bảo toàn data schema và business semantics, không xóa field/constraint bất ngờ để vượt bootstrap.

---

## 11. Ví dụ entity dùng để xác định phạm vi di trú

~~~java
@Entity
@Table(
    name = "purchase_order",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_tenant_request",
        columnNames = {"tenant_id", "request_id"}
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq"
    )
    @SequenceGenerator(
        name = "order_seq",
        sequenceName = "order_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "request_id", nullable = false)
    private String requestId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private long version;
}
~~~

Cùng một mapping kéo theo nhiều quyết định khi nâng:

- Provider mới có mapping `SEQUENCE` tương thích DB sequence hiện tại?
- `allocationSize` có dùng pooled optimizer cùng DDL/INCREMENT không?
- Trong rolling deployment, provider cũ và mới có thể cùng cấp ID an toàn?
- Enum strings trong DB có tương thích names sau refactor?
- Generated DDL có đổi precision/column type không?
- Unique constraint còn tồn tại, tenant/request scope được giữ?
- `@Version` có bảo vệ concurrent updates theo cùng nghiệp vụ?

### 11.1. Schema không được suy ra chỉ từ annotation

Nếu production dùng migrations, phải kiểm database DDL thực và dữ liệu đang lưu, không chỉ review Java code.

---

## 12. Rủi ro bộ sinh ID khi rolling deployment

Đây là một trong những vùng rủi ro cao nhất của provider upgrade.

Giả sử provider cũ cấp ID bằng database sequence theo một thuật toán, provider mới chuyển sang pooled allocation khác. Nếu old/new pods cùng hoạt động:

~~~text
Pod old: đọc sequence, cấp ID theo rule A
Pod new: đọc sequence, cấp block theo rule B
                      |
                      v
             Có thể overlap / duplicate IDs
~~~

### 12.1. Không đổi allocationSize độc lập với sequence DDL

Một số pooled optimizers yêu cầu database sequence `INCREMENT BY` khớp allocation size. Không có một quy tắc universal cho mọi provider; phải kiểm generator algorithm, database state và từng version.

### 12.2. Không chỉ test từng version riêng

Một test old-only và new-only pass vẫn chưa chứng minh **mixed-version coexistence** an toàn. Thử concurrent inserts old/new trên cùng DB/sequence với schema đại diện.

### 12.3. Không điều chỉnh sequence trong khi traffic đang ghi mà thiếu kế hoạch

Thay sequence start/increment/cache trên database production phải xét locks, in-flight allocations, pods giữ unused ID blocks và rollback behavior.

### 12.4. Có thể cần quiesce writes

Nếu không chứng minh được hai allocators tương thích, chọn **write freeze / single-writer cutover** thay vì rolling mixed writes. Một maintenance window có thể an toàn hơn việc cố zero downtime không có bằng chứng.

---

## 13. Phân biệt ID kỹ thuật và business identifier

Một Order có thể có:

~~~text
id = 108922                   (surrogate PK)
request_id = "req-abc-123"     (idempotency key)
order_number = "SO-2026-052"  (business reference)
~~~

### 13.1. Primary key không bắt buộc gapless

Sequence/identity caching, rollback và pooling có thể tạo khoảng trống. Upgrade không nên chạy script “điền khoảng trống ID” nếu không có business justification cụ thể.

### 13.2. Unique business key vẫn cần

Hai requests retry có thể tạo hai technical IDs khác nhau; unique `(tenant_id,request_id)` mới bảo vệ idempotency của command.

### 13.3. Đổi type PK là migration lớn

Long → UUID ảnh hưởng primary keys, foreign keys, join tables, DTOs, APIs, events, analytics và cache keys. Tách khỏi provider upgrade nếu có thể.

---

## 14. Kiểu dữ liệu: Vùng rủi ro có thể làm hỏng dữ liệu âm thầm

Mapping cũ và mới có thể khác cách lưu:

| Java type | Cần kiểm | Rủi ro |
|---|---|---|
| `String` | Length, Unicode, collation | Truncation, sort khác |
| `BigDecimal` | Precision, scale | Làm tròn tiền |
| `Instant` | Timestamp precision, timezone | Lệch thời gian |
| `LocalDateTime` | Session timezone semantics | Trôi thời gian |
| `Enum` | STRING/ORDINAL | Đọc sai status |
| `UUID` | Native UUID/BINARY/CHAR | Sai column size/order |
| `Boolean` | DB representation | Chuyển 0/1/null sai |
| `@Lob` | CLOB/BLOB strategy | Lỗi encoding/stream |
| JSON/custom | Type descriptor/JDBC mapping | Không đọc được payload |
| `@Convert` | Auto apply, null behavior | Đổi ciphertext/value |

### 14.1. Không thay EnumType.ORDINAL sang STRING mà không migrate data

Một DB lưu `1` không tự biến thành `"ACTIVE"` khi đổi annotation. Cần migration dữ liệu rõ, reversible khi có thể.

### 14.2. Thời gian phải có policy

Cùng một `Instant` đọc lại có thể mất phần sub-millisecond tùy DB. Quy tắc test cần phản ánh storage precision và timezone contract; không đơn giản disable assertions.

### 14.3. Tiền tệ cần giữ numeric integrity

Một provider mới chọn JDBC type khác có thể làm `BigDecimal` scale hoặc rounding thay đổi. Dùng representative edge cases và DB-readback tests.

---

## 15. Kế hoạch đối với JPQL, Criteria và native SQL

Có ba lớp query:

1. **JPQL** theo mô hình entity, có contract chuẩn.
2. **Criteria API** dựng query tree bằng typed/untyped APIs.
3. **Native SQL** phụ thuộc database engine/dialect.

### 15.1. Inventory queries

Gom danh mục:
- Named queries.
- Spring Data `@Query`.
- Derived repository methods.
- Criteria/Specification builders.
- QueryDSL hoặc DSL của ứng dụng.
- Native SQL trong repositories/services.
- Stored procedures/functions.
- Bulk UPDATE/DELETE.
- Locks/hints.
- Page/count/search/export.

### 15.2. HQL extension không tự là JPQL portable

Một Hibernate HQL query có thể dùng syntax/function mà EclipseLink không hỗ trợ. Đặt mục tiêu chuyển sang JPQL chuẩn hoặc giữ vendor adapter. Không xử lý lỗi parser bằng cách đổi ngẫu nhiên entity mapping.

### 15.3. Query result cardinality

Kiểm 0/1/many rows, `getSingleResult` exceptions, `getResultList`, GROUP BY và aggregate null semantics. Một query join collection có thể nhân rows; không dựa vào provider de-duplication ngầm để viết business code.

### 15.4. Pagination và stable ordering

Count query và data query phải có cùng filters; pageable query nên có deterministic ORDER BY. Khi nâng provider, collection fetch join + pagination cần được kiểm SQL plans và memory usage.

### 15.5. Security predicates không được mất

Nếu ứng dụng nhiều tenants, JPQL/native/bulk paths đều cần tenant/owner/ACL filters. Một đổi provider làm vendor filter ngừng hoạt động là **lỗi bảo mật**, không chỉ query regression.

---

## 16. Schema: Ưu tiên migration scripts, không tự động tái tạo

Trong production, schema thường được quản lý bằng Flyway, Liquibase hoặc một quy trình DDL có review.

### 16.1. Không bật create-drop khi provider mới khởi động

Một cấu hình như `create-drop` thích hợp cho một số tests disposable, **không** cho production. Auto-DDL có thể xóa bảng/dữ liệu hoặc đổi column types ngoài kế hoạch.

### 16.2. Quá trình chuẩn

~~~text
Existing schema + existing data
             |
             v
   Apply reviewed migration scripts
             |
             v
   Validate table/column/index/FK/sequence
             |
             v
   Bootstrap target provider in validate mode
             |
             v
       Execute compatibility tests
~~~

### 16.3. Diff schema phải được phân loại

Những khác biệt đáng chú ý:
- Identity/sequence naming và increments.
- Default schema/catalog.
- Quoted identifiers.
- Unicode/text column widths.
- Temporal precision.
- Decimal/numeric types.
- Join table naming.
- FK ON DELETE rules.
- Unique constraints/indexes.
- Partial indexes.
- Nullable/default values.

### 16.4. Dùng nguồn sự thật nhất quán

Nếu migration files là source of truth, provider schema validation nên so với chúng. Không thay đổi DDL production chỉ vì provider đề xuất một auto-generated schema khác.

---

## 17. Expand–migrate–contract khi cần zero downtime

Một chiến lược chuẩn cho schema không tương thích ngay là **expand–migrate–contract**.

~~~text
Phase 1: EXPAND
    Thêm column/table/index mới
    Không xóa column cũ
    Old app vẫn đọc/ghi được

Phase 2: MIGRATE
    Chạy backfill, dual-read/dual-write nếu cần
    Đối soát số lượng/checksum/business invariants

Phase 3: CUT OVER
    New app đọc path mới
    Old app dừng dùng path cũ

Phase 4: CONTRACT
    Xóa old schema sau khi hết rollback window
~~~

### 17.1. Ví dụ đổi một cột status

Ban đầu:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    status_code SMALLINT NOT NULL
);
~~~

Muốn chuyển sang string status:

~~~sql
ALTER TABLE purchase_order
ADD COLUMN status_name VARCHAR(32);
~~~

Backfill có mappings được duyệt:

~~~sql
UPDATE purchase_order
SET status_name =
    CASE status_code
        WHEN 0 THEN 'CREATED'
        WHEN 1 THEN 'PAID'
        WHEN 2 THEN 'CANCELLED'
        ELSE NULL
    END
WHERE status_name IS NULL;
~~~

### 17.2. Không bật NOT NULL ngay nếu còn backfill

Sau backfill, kiểm không còn unexpected nulls, mọi writers đã hỗ trợ column mới và constraints đã sẵn. Mới sau đó siết NOT NULL/unique hoặc drop old column.

### 17.3. Dual-write có rủi ro

Nếu old/new columns phải được ghi cùng transaction, cần logic nhất quán, idempotent, có reconciliation. Dual-write qua hai systems không atomically commit thì phải có recovery strategy.

### 17.4. Chỉ contract sau rollback window

Xóa old column sớm khiến rollback code cũ không chạy được. Mốc contract nên là một release có approval riêng, không mặc định gắn vào cùng deploy cutover.

---

## 18. Migration của dữ liệu cũ phải có kiểm chứng

Một target schema mới được tạo từ đầu có thể pass toàn bộ CRUD tests, nhưng production data chứa:

- Enum ordinals cũ.
- Nulls không còn hợp lệ.
- Trùng business keys đã bị legacy job tạo.
- Timestamps ngoài miền mong đợi.
- ID sequence lệch max PK.
- FK orphans.
- Invalid encodings.
- Unknown discriminator values.
- Serialized custom types dạng cũ.
- Data rows được ghi từ native SQL bên ngoài JPA.

### 18.1. Inventory data quality

Chạy queries đối soát (trên môi trường được phép), ví dụ:

~~~sql
SELECT status_code, COUNT(*)
FROM purchase_order
GROUP BY status_code;
~~~

và:

~~~sql
SELECT MAX(id)
FROM purchase_order;
~~~

### 18.2. Dùng sanitized production-like snapshot

Không đưa PII, tokens hoặc payment details vào CI. Snapshot phải đại diện giá trị/size/cardi­nality và constraints, có cơ chế masking/anonymization.

### 18.3. Backfill phải resumable

Một migration hàng triệu rows có thể cần chia batch, có checkpoint, idempotent retries, lock timeout và throttling. Nếu script bị gián đoạn, chạy lại không được làm sai dữ liệu.

### 18.4. Reconciliation sau backfill

So row counts, business aggregates, uniqueness, FK integrity, null rates và checksums/hashes của fields quan trọng; không chỉ dựa vào SQL affected count.

---

## 19. Transaction semantics và @Transactional

Kế hoạch nâng phải xác định **ai sở hữu transaction**.

### 19.1. RESOURCE_LOCAL

~~~java
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();
    em.persist(order);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Đây là mẫu ở JPA RESOURCE_LOCAL, không áp trực tiếp cho mọi Spring/JTA-managed EntityManager.

### 19.2. Spring @Transactional

Khi gọi qua Spring proxy, commit thường xảy ra **sau khi method body return**. Commit exception có thể được caller nhận tại proxy boundary. Migration cần test rollback rules, checked/unchecked exception policies, transaction propagation và self-invocation.

### 19.3. JTA

JTA transaction manager có recovery/status contract riêng. Không tự gọi `em.getTransaction()` trên JTA-managed EntityManager. Những applications có XA/distributed resources cần migration/recovery plan sâu hơn.

### 19.4. Flush không phải commit

`em.flush()` đồng bộ changes trong transaction, không xác nhận đã committed. Nếu provider mới flush ở thời điểm khác nhưng business state đúng sau commit, chưa chắc là regression.

### 19.5. Mất COMMIT ACK

Connection loss tại commit boundary có thể tạo outcome không rõ. Không retry tạo order bằng operation key mới; cần idempotency, durable receipt/outbox và fresh connection reconciliation khi nghiệp vụ yêu cầu.

---

## 20. Locking và concurrent updates

Hai lớp concurrency phải được kiểm:

- **Optimistic**: `@Version`, `OptimisticLockException`.
- **Pessimistic**: `LockModeType.PESSIMISTIC_WRITE` và related lock/timeouts.

### 20.1. Upgrade có thể đổi exception timing

Stale version conflict có thể xuất hiện tại `merge`, `flush` hoặc `commit`. Tests nên bao toàn transaction và kiểm root cause, không bắt exception phải phát ở đúng một Java statement nếu spec cho phép nhiều thời điểm.

### 20.2. DB locking behavior có thể khác

Một provider mới có thể đổi generated lock SQL hoặc query plans. Kiểm lock waits, deadlocks, isolation, timeout mapping và rollback behavior trên DB thật.

### 20.3. Race trong quyền truy cập

Nếu policy ACL thay đổi khi một transaction đang update row, `@Version` trên row không tự phát hiện membership revoke. Giữ security contract và DB policy khi nâng provider.

---

## 21. Caches, sessions và enhancement

Tách:

- First-level persistence context cache.
- Second-level entity cache.
- Query cache.
- Application/HTTP caches.
- Bytecode enhancement/weaving.

### 21.1. L1 là theo EntityManager

`find` cùng PK trong một context có thể trả managed instance từ cache. Một fresh-transaction readback cần hiểu L2 cache nếu mục tiêu là xác nhận DB state.

### 21.2. L2/query caches là provider-dependent

Hibernate và EclipseLink có integrations/settings khác nhau. Không coi region factory, concurrency strategy hoặc query cache TTL là portable configuration.

### 21.3. Cache invalidation correctness

Test:
- Update rồi read sau commit.
- Delete rồi không trả stale result.
- Cross-tenant IDs không collision.
- Bulk UPDATE/DELETE không để stale cached state ngoài chính sách.
- Rolling old/new instances dùng cache serializer/key version tương thích.

### 21.4. Lazy loading và enhancement

Khi provider đổi, cơ chế proxies/weaving/bytecode enhancement có thể khác. Những entity classes final, constructors, access strategy và lazy basic attributes cần được kiểm theo spec và provider target.

---

## 22. Tương thích với các services không dùng JPA

Một database thường được truy cập bởi:
- SQL ETL jobs.
- Reporting/BI.
- CDC pipelines.
- Messaging consumers.
- Legacy applications.
- Stored procedures.
- Admin scripts.
- External integrations.

### 22.1. Không chỉ migrate ORM application

Đổi column/sequence hoặc enum mapping có thể làm một SQL job khác fail dù toàn bộ JPA test pass. Inventory upstream/downstream dependencies theo bảng và field.

### 22.2. Event schemas có thể phụ thuộc ID/data types

Nếu Order ID đổi Long sang UUID, consumers cần migration riêng. Giữ event compatibility/serialization contract qua rolling deployment.

### 22.3. Database triggers và defaults

Provider mới có thể gửi explicit NULL thay vì bỏ column, làm DB default không chạy. Test với actual schema/triggers.

---

## 23. Lập ma trận kiểm thử tối thiểu

| Lớp test | Mục tiêu | Điều kiện pass |
|---|---|---|
| Compile/dependency | API/framework alignment | Không có class/type mismatch |
| Bootstrap | Persistence unit thực | Đúng provider, entity set |
| Mapping | Id/basic/relationships | DB readback và FKs đúng |
| CRUD | persist/find/merge/remove | Transaction mới thấy expected state |
| Transaction | rollback/commit/timeout | Không partial writes |
| Constraints | PK/unique/FK | Cấm duplicate/orphan |
| Versioning | Concurrent stale update | Không lost update |
| JPQL/Criteria | Search/projection/count | Đúng cardinality/filter |
| Native SQL | Dialect integration | Kết quả/schema types đúng |
| Pagination | Stable sort/count | Không missing/duplicate tùy contract |
| Fetch/cache | Lazy/graph/L2 | Không stale/unauthorized rows |
| Security | Tenant/owner/ACL | Không cross-tenant leak |
| Migration data | Legacy read/write | Không semantic corruption |
| Performance | SQL/N+1/batching/latency | Nằm trong SLO/budgets |
| Operational | Canary/rollback | Fail-fast và phục hồi được |

### 23.1. Test với DB target

H2 có thể hỗ trợ smoke tests, nhưng những vấn đề sequence, locking, native SQL, collation và generated keys cần database tương đương production.

### 23.2. Test không chỉ exception class

Spring/provider có thể dịch errors sang types khác. Trong domain-level tests, assert business meaning và DB effect; ở integration layer kiểm cause/SQLSTATE khi cần.

---

## 24. JPA contract test mẫu bằng JUnit 5

~~~java
final class JpaTestTx {

    static <T> T execute(
            EntityManagerFactory emf,
            Function<EntityManager, T> action) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            T result = action.apply(em);
            tx.commit();
            return result;
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException cleanup) {
                    failure.addSuppressed(cleanup);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
~~~

Imports gồm `jakarta.persistence.*` và `java.util.function.Function`. Helper này dành cho RESOURCE_LOCAL tests; không sử dụng trên EntityManager do JTA/Spring quản lý transaction.

Một test business contract:

~~~java
@Test
void committedOrderCanBeReadFromNewContext() {
    String requestId = UUID.randomUUID().toString();

    Long id = JpaTestTx.execute(emf, em -> {
        PurchaseOrder order =
            buildOrderForTenant(42L, requestId);

        em.persist(order);
        em.flush();

        return order.getId();
    });

    Long storedId = JpaTestTx.execute(
        emf,
        em -> em.createQuery(
            """
            SELECT o.id FROM PurchaseOrder o
            WHERE o.tenantId = :tenantId
              AND o.requestId = :requestId
            """,
            Long.class
        )
        .setParameter("tenantId", 42L)
        .setParameter("requestId", requestId)
        .getSingleResult()
    );

    assertEquals(id, storedId);
}
~~~

`buildOrderForTenant` là test fixture factory tự tạo Order fields hợp lệ, không phải JPA API. Test phải chạy trên provider target và DB schema thật.

### 24.1. Tại sao fresh transaction?

Để tránh việc `em.find()` trong cùng L1 cache che lỗi flush/commit hoặc mapping.

### 24.2. Không trộn API mới trong portable core test nếu target cũ

Nếu cần hỗ trợ Jakarta Persistence 3.0, không gọi `getSingleResultOrNull()` trong code test chung compile với API đó. Đặt feature tests theo API version.

---

## 25. Testcontainers và ma trận database

Testcontainers cho phép chạy DB engine phù hợp trong integration tests. Một Spring Boot test ví dụ:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class OrderPersistenceTest {

    @Container
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.datasource.url",
            db::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            db::getUsername
        );
        registry.add(
            "spring.datasource.password",
            db::getPassword
        );
    }
}
~~~

Phiên bản image trong ví dụ không phải khuyến nghị cố định; dùng DB engine/version tương ứng production. Cấu hình Spring dependencies/annotation imports theo phiên bản framework target.

### 25.1. @DataJpaTest thường rollback theo mặc định

`flush()` trong một `@DataJpaTest` không chứng minh durable commit. Với committed-state tests, dùng `TransactionTemplate` hoặc `TestTransaction`/test-level transaction configuration phù hợp.

### 25.2. Một container không mô phỏng mọi thứ

Primary/replica lag, failover, sharding, network partition và XA recovery cần môi trường/thử nghiệm riêng nếu ứng dụng phụ thuộc.

---

## 26. Chiến lược chạy hai providers để so sánh

Một hướng an toàn ở non-production:

~~~text
Baseline build/profile
   JPA API A + Provider A + DB schema S
             |
             v
      Shared contract suite
             |
             v
        Baseline results

Target build/profile
   API target + Provider B + cùng schema S
             |
             v
      Shared contract suite
             |
             v
        Compare results
~~~

### 26.1. Đừng nhét cả hai providers vào runtime vô tình

Nếu classpath chứa hai implementations, service discovery có thể chọn provider không mong đợi. Chọn explicit provider và assert runtime identity.

### 26.2. Chạy test fixture tương đương

Schema, data distributions, transaction boundaries, feature flags và DB version phải cùng một basis nếu muốn so sánh meaningful.

### 26.3. Phân biệt khác biệt hợp lệ

Provider A chạy 3 queries, B chạy 4 queries có thể là performance finding, chưa phải behavioral bug nếu dữ liệu đúng. Ngược lại, B bỏ tenant predicate là security regression dù queries ít hơn.

---

## 27. Performance baseline trước migration

Chọn use cases đại diện:

- Tạo 1 Order + 10 Lines + Outbox.
- Đọc Order details.
- List 50 Orders bằng DTO projection.
- Search filter nhiều điều kiện.
- Export 100.000 rows theo chunk.
- Bulk update 1.000 rows.
- Concurrent order creation.
- Optimistic lock conflict.
- Soft-delete và count.
- Cache warm/cold read.

### 27.1. Đo các thành phần

| Metric | Vì sao |
|---|---|
| Requests/s và p95/p99 latency | Trải nghiệm khách hàng |
| JDBC SQL executions/batches | N+1 và write-path regression |
| DB CPU/WAL/redo | Giá thành ghi dữ liệu |
| Lock waits/deadlocks | Transaction contention |
| Connection pool wait | Saturation |
| Heap/GC | Entity graph/cache |
| Sequence allocations | ID generator compatibility/performance |
| SQL errors/rollback rate | Persistence correctness |
| Cache hit/staleness | Read consistency |
| Outbox lag | Downstream consistency |

### 27.2. Đặt ngưỡng trước khi đo

Ví dụ minh họa:

~~~text
- Không có cross-tenant leakage hoặc duplicate Order.
- P95 order-create latency không vượt ngưỡng SLO đã ký.
- SQL count cho list endpoint không tăng quá guardrail.
- DB CPU/locks không vượt safe operating band.
- Error/retry rate không vượt canary baseline đáng kể.
~~~

Ngưỡng thực tế phải dựa vào service SLO/load tests; không lấy những con số tùy ý áp cho mọi ứng dụng.

### 27.3. Nhận diện driver/provider batching

`IDENTITY` thường hạn chế ORM INSERT batching trong một số Hibernate paths; `SEQUENCE` được cấu hình pooling có thể thuận lợi hơn. Kiểm actual batch executions, không chỉ property `batch_size`.

---

## 28. Readiness gates: Có bằng chứng mới cho đi tiếp

Một kế hoạch theo giai đoạn:

| Gate | Mục tiêu | Không được qua nếu |
|---|---|---|
| G0 – Scope | Chốt target/bất biến/rủi ro | Thiếu owner hoặc architecture inventory |
| G1 – Compile/Bootstrap | Chạy đúng stack | API/provider mismatch |
| G2 – Correctness | Portable/extension tests pass | Data/transaction/security regression |
| G3 – Migration rehearsal | Schema/data cũ chuyển được | Backfill không đối soát |
| G4 – Performance | Đạt budgets | N+1/lock/latency vượt SLO |
| G5 – Rollback | Quay lại/roll forward được | Không có recovery path |
| G6 – Canary | Production evidence ổn | Error/correctness alerts |
| G7 – Cutover | Chuyển toàn bộ traffic | Mixed-version gap/collision |
| G8 – Contract | Gỡ old schema/config | Còn old consumers/rollback window |

### 28.1. Go/no-go phải có người chịu trách nhiệm

Database migration owner, service owner, SRE và security/compliance nếu liên quan phải biết họ xác nhận điều gì. Không để “tests xanh” tự thay business approval cho thay đổi irreversible.

### 28.2. Không vượt gate vì deadline

Nếu sequence optimizer mixed writes chưa được chứng minh tương thích, không chuyển sang rolling deployment vì muốn zero downtime. Chọn maintenance cutover hoặc redesign.

---

## 29. Kế hoạch triển khai theo môi trường

Một lộ trình:

1. **Developer sandbox**: compile, bootstrap, chỉnh APIs/extensions.
2. **Ephemeral integration DB**: portable JPA contracts và constraints.
3. **Staging production-like**: migration scripts, sanitized legacy data, load tests.
4. **Pre-production rehearsal**: cutover sequence, rollback, operational runbook.
5. **Canary production**: một subset traffic nếu architecture cho phép.
6. **Progressive rollout**: tăng traffic hoặc pods, quan sát metrics.
7. **Post-cutover monitoring**: duy trì cảnh báo và reconciliation.
8. **Contract cleanup**: xóa old paths sau rollback window.

### 29.1. Không mirror production PII sang staging tùy tiện

Sử dụng synthetic/sanitized datasets và access controls. Security của dữ liệu test là một phần của migration plan.

### 29.2. Không nên coi environment tên “staging” là đủ

Cần so sánh DB version, collation, constraints, indexes, pool, load pattern và transaction manager. Một staging nhỏ có thể không phát hiện hotspot sequence/locks.

---

## 30. Canary khi nhiều app instances cùng dùng một DB

Canary không phải luôn an toàn cho persistence upgrade.

~~~text
Production:
   Pod old A ─┐
   Pod old B ─┤
   Pod new C ─┴──> Shared database
~~~

### 30.1. Rủi ro mixed writes

Pod new có thể:
- Cấp IDs theo generator khác.
- Ghi status format mới.
- Bỏ update old column.
- Publish event schema mới.
- Thay lock/version semantics.
- Thao tác cache chung không tương thích.

### 30.2. Điều kiện trước canary

- Schema backward/forward compatible.
- ID generators tương thích khi đồng thời.
- Old code đọc được rows do new code ghi.
- New code đọc được rows do old code ghi.
- Event/DTO/cache formats tương thích.
- Transaction/business invariants được kiểm bằng mixed-version tests.

### 30.3. Nếu không đủ điều kiện

Dùng write-quiesce, blue/green với controlled switchover, hoặc maintenance window có rollback. Không mặc định “canary = ít traffic nên ít rủi ro” cho lỗi dữ liệu.

---

## 31. Feature flags, dark launch và shadow reads

Một số trường hợp có thể chạy target provider để **đọc thử** cùng dữ liệu nhưng không ghi production.

### 31.1. Shadow reads

So sánh normalized DTO results giữa baseline và target, bỏ fields không ổn định như internal proxy class, SQL alias hoặc thời điểm thực thi.

### 31.2. Tránh lộ dữ liệu qua shadow pipeline

Shadow requests cần authentication/tenant scope, logging redaction và data access permissions tương đương production. Không phát bản sao raw PII sang monitoring ngoài policy.

### 31.3. Shadow writes nguy hiểm

Không “thử ghi” vào production rồi hy vọng rollback mọi thứ: triggers, sequences, external side effects hoặc locks có thể tạo ảnh hưởng. Nếu cần shadow write, dùng isolated DB, disposable tenant hoặc transaction-safe sandbox với threat assessment riêng.

### 31.4. Feature flag không thay schema migration

Tắt feature code không tự khôi phục old column khi nó đã bị drop. Phải giữ versioning/rollback plan độc lập.

---

## 32. Kịch bản zero downtime có một schema expand-only

Một phương án minh họa:

~~~text
Release N:
   Add new nullable columns/indexes
   Keep legacy behavior
   Verify old apps continue working

Release N+1:
   Deploy code that can read old+new
   Backfill gradually
   Compare old/new fields

Release N+2:
   Enable new provider/API behavior
   Dual-write fields if contract requires
   Monitor correctness and latency

Release N+3:
   Disable old readers/writers
   Verify rollback window expired

Release N+4:
   Drop legacy schema/config
~~~

Các release labels là ví dụ. Một hệ thống nhỏ có thể gộp bước khi không có concurrency risk; một hệ thống phức tạp có thể cần nhiều giai đoạn hơn.

### 32.1. Thêm index không luôn tức thời

Một số DB hỗ trợ online/concurrent index creation với điều kiện riêng. Kiểm lock behavior và resource usage; đừng giả định một `CREATE INDEX` lớn không ảnh hưởng traffic.

### 32.2. Backfill cần pacing

Backfill hàng triệu rows có thể làm replication lag, WAL, lock contention và cache pressure tăng. Giới hạn batch sizes, concurrency, checkpoint và metrics.

---

## 33. Quy trình write freeze khi không thể mixed-version

Nếu provider versions dùng ID allocator/schema không tương thích:

1. Đưa hệ thống vào chế độ không nhận **new writes** theo business contract.
2. Dừng workers, schedulers và async consumers ghi DB liên quan.
3. Đợi in-flight transactions hoàn tất hoặc xử lý timeout an toàn.
4. Ghi checkpoint: DB backup/snapshot, sequence state, migration version.
5. Apply migration cấu hình/schema cần thiết.
6. Deploy target binary đồng nhất cho writers.
7. Smoke test create/update/delete với controlled data.
8. Chạy reconciliation/uniqueness/foreign-key checks.
9. Mở lại writes từng phần và theo dõi.
10. Nếu fail, thực thi rollback/restore plan đã rehearsal.

### 33.1. Read-only HTTP không có nghĩa toàn hệ thống không ghi

Background workers, CDC repair, scheduled maintenance, retry queues và integration jobs vẫn có thể tạo writes. Inventory mọi writer.

### 33.2. Không làm mất operations ở hàng đợi

Khi stop workers, cần biết jobs đang in-flight, ack status, idempotency keys và replay behavior để resume an toàn.

---

## 34. Rollback: Ba cấp độ khác nhau

1. **Rollback binary**: redeploy app/provider version cũ.
2. **Rollback configuration**: quay lại settings, flags, datasource routing, cache region options.
3. **Rollback data/schema**: reverse migrations hoặc restore snapshot/PITR/roll forward repair.

### 34.1. Binary rollback chỉ an toàn khi old code đọc được new writes

Nếu target provider đã ghi một enum representation mới hoặc thay primary key schema, redeploy old binary có thể khởi động nhưng xử lý dữ liệu sai.

### 34.2. Data rollback có thể làm mất writes hợp lệ

Restore snapshot từ 10 phút trước có thể làm mất các Orders/Payments hợp lệ trong khoảng đó. Cần RPO/RTO, event replay, reconciliation và business decision, không coi restore là thao tác vô hại.

### 34.3. Forward-fix có thể an toàn hơn reverse DDL

Khi schema/data migration đã irreversible, giữ compatibility layer và sửa lỗi trên target có thể ít rủi ro hơn việc drop new fields/restore old types.

### 34.4. Viết điều kiện “không thể rollback tự động”

Ví dụ:
- New rows không tương thích old binary.
- Sequence allocator đã thay và old pod không được phép cấp ID nữa.
- Old column đã bị drop.
- Provider-specific serialized cache format đã chuyển.
- Data transform mất thông tin nguồn.

Các điều kiện này phải có trong rollback runbook trước production.

---

## 35. Phân tích rủi ro theo xác suất × tác động

Một risk register minh họa:

| Rủi ro | Dấu hiệu sớm | Tác động | Giảm thiểu |
|---|---|---|---|
| javax/jakarta mismatch | NoClassDefFoundError/bootstrap fail | Service unavailable | Dependency alignment + smoke |
| Provider chọn nhầm | Wrong runtime implementation | Tests báo xanh giả | Assert provider identity |
| Sequence allocator overlap | Duplicate PK/unique error | Data correctness | Mixed-version test/write freeze |
| Enum mapping đổi | Status đọc sai | Business corruption | Data migration/readback |
| N+1 sau upgrade | SQL count/p99 tăng | Performance | Fetch plans + benchmark |
| ACL filter bị bỏ | Cross-tenant result | Security incident | Negative authorization tests |
| Bulk DML semantics đổi | Missing audit/version checks | Data consistency | Explicit DML contract tests |
| Query parser chặt hơn | Startup/query exception | Endpoint errors | Named query execution suite |
| Cache key không hợp | Stale/cross-tenant cache | Data leak | Cache migration/namespace/disable |
| Rolling schema incompatibility | Old pod fail với new row | Outage | Expand-contract |
| Backfill gây locks | Waits/replica lag | Latency/outage | Throttle, monitor, pause |
| Rollback không chạy | Old code không đọc new data | Prolonged incident | Rehearsal + forward-fix plan |

### 35.1. Gán owner cho từng risk

Mỗi rủi ro quan trọng cần người chịu trách nhiệm, status và evidence giảm thiểu. Không để một dòng “team sẽ kiểm tra” không có owner/cách đo.

---

## 36. Runbook điều tra khi canary có lỗi

### Bước 1. Xác định layer

- Compile/bootstrap?
- Datasource/driver?
- Query parse?
- Schema/sequence?
- Transaction/locking?
- Cache/fetch?
- Security/tenant?
- Data representation?

### Bước 2. Khoanh vùng

So sánh baseline và target với cùng request/tenant/schema và correlation ID. Không log raw secrets hoặc PII.

### Bước 3. Xác nhận correctness

Nếu có dấu hiệu duplicate business effect, unauthorized access hoặc dữ liệu bị ghi sai, **dừng tăng traffic/writes ngay theo runbook**. Performance lỗi nhỏ có thể được điều chỉnh, nhưng data corruption/leak là no-go.

### Bước 4. Kiểm operational metrics

DB error rate, locks, sequence usage, slow queries, p99, connection pool, CPU/GC, outbox lag.

### Bước 5. Quyết định

- Giữ canary để điều tra nếu impact được giới hạn và an toàn.
- Rollback binary nếu schema/data tương thích.
- Tắt write path nếu mixed-version/collision risk.
- Thực thi forward-fix có kiểm soát nếu rollback không an toàn.
- Khôi phục dữ liệu bằng quy trình DBA/business reconciliation nếu có corruption.

### Bước 6. Ghi postmortem evidence

Version combination, migration ID, time, fault window, data impact, fix/rollback và regression test mới.

---

## 37. Điều kiện go/no-go trước khi triển khai production

Một release chỉ nên được duyệt khi:

- Runtime implementation và API versions được xác minh.
- Portable contract suite pass trên target.
- Vendor extension changes đã được review.
- Production migration scripts đã chạy rehearsal.
- Old data được đọc/ghi đúng.
- ID generators có mixed-version plan hoặc write freeze.
- Query/count/pagination/ACL tests pass.
- Optimistic locks và DB constraints pass.
- Không có known data corruption/security blocker.
- Load/performance budgets đạt mục tiêu.
- Cache/connection pool metrics phù hợp.
- Backfill có checkpoint và pause/resume path.
- Rollback hoặc roll-forward runbook được thực hành.
- Owners/SRE/DBA biết cách theo dõi và dừng rollout.

### 37.1. “Đã test manual một endpoint” không đủ

Persistence layer phục vụ nhiều paths: workers, exports, bulk jobs, scheduled tasks và events. Mọi writer/reader quan trọng phải được đưa vào kế hoạch.

---

## 38. Lộ trình minh họa theo các đợt công việc

Không bắt buộc thời lượng cụ thể, nhưng công việc có thể chia theo pha:

| Pha | Việc chính | Deliverable |
|---|---|---|
| Khởi động | Scope, owners, invariants, risk | Approved charter |
| Inventory | Dependencies, schema, extensions | Current-state report |
| Target selection | Supported compatibility combinations | Target matrix |
| Refactor chuẩn | javax→jakarta, remove extensions | Build/runtime profiles |
| Data planning | DDL, ID generators, backfill | Migration scripts |
| Compatibility testing | CRUD/queries/transactions/ACL | Test evidence |
| Performance testing | SQL/p95/p99/lock budgets | Performance report |
| Rehearsal | Cutover, rollback, data reconciliation | Runbook evidence |
| Canary/rollout | Progressive deployment/monitoring | Production telemetry |
| Closure | Contract old schema, docs | Final sign-off |

### 38.1. Không gắn chặt theo lịch nếu gate chưa pass

Khi gặp blocker dữ liệu, quay lại điều tra và test; không chuyển sang rollout chỉ vì đã đến mốc thời gian dự kiến.

---

## 39. Mẫu kế hoạch thay đổi ngắn gọn để review

~~~text
CHANGE ID:
SERVICE / DATABASE:
OWNER:
CURRENT JDK / API / PROVIDER / DRIVER / DB:
TARGET JDK / API / PROVIDER / DRIVER / DB:

BUSINESS INVARIANTS:
  - ...
  - ...

CODE CHANGES:
  - Namespace/API:
  - Provider extensions:
  - Queries:
  - Mapping/converters:

DATA/SCHEMA:
  - DDL migration:
  - Backfill:
  - Sequence/ID allocation:
  - Legacy compatibility:

TEST EVIDENCE:
  - Portable suite:
  - DB-specific suite:
  - Concurrency:
  - Tenant/ACL:
  - Performance:

DEPLOYMENT:
  - Expand schema:
  - Mixed-version compatibility:
  - Canary/write freeze:
  - Cutover:
  - Monitoring window:

GO / NO-GO:
  - Conditions:
  - Approvers:

ROLLBACK / FORWARD FIX:
  - Binary compatibility:
  - Schema/data restore:
  - RPO/RTO:
  - Reconciliation:

POST-CUTOVER:
  - Metrics:
  - Cleanup:
  - Lessons learned:
~~~

Mẫu này giúp một reviewer không phải đoán “nâng provider có đổi DB sequence không?” hoặc “ai chịu trách nhiệm kiểm tra dữ liệu cũ?”.

---

## 40. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Phương án phù hợp |
|---|---|---|
| Đổi dependency rồi deploy ngay | Không biết runtime/DDL effects | Inventory + gates |
| Chỉ sửa javax imports | Thiếu framework/metamodel/XML alignment | Migration theo modules |
| Trộn nhiều provider jars | Runtime có thể chọn nhầm | Explicit implementation |
| Tin API version là đủ | Provider/driver/DB có support matrix | Target combination |
| Upgrade DB và provider cùng lúc | Khó cô lập lỗi | Tách trục khi có thể |
| Bật create-drop để “sửa schema” | Có thể xóa production data | Reviewed migrations |
| Đổi allocationSize khi rolling | ID collision risk | Generator compatibility proof |
| Chỉ test schema sạch | Legacy data không được kiểm | Data rehearsal |
| Dùng H2 làm bằng chứng tất cả DB | Dialect/locks khác | Production-like DB |
| Chỉ test GET | Mutations/rollback có thể sai | Full CRUD/transaction |
| Không test bulk/native queries | Bypass filters/callbacks | Explicit coverage |
| Bỏ qua ACL after provider switch | Data leak | Tenant negative tests |
| Chỉ so exact SQL text | False regression | Behavioral contract |
| Không đặt performance budget | N+1 lộ khi production | SQL + latency budgets |
| Canary mixed writes không test | Key/schema compatibility gap | Mixed-version tests |
| Rollback chỉ là redeploy | Old code không hiểu new data | Data/schema rollback plan |
| Drop old column sớm | Mất rollback path | Expand–contract |
| Backfill một transaction khổng lồ | Locks/WAL/rollback cost | Chunk/checkpoint |
| Không quan sát cache | Stale/cross-tenant data | Cache migration tests |
| Bỏ qua background workers | Writers cũ vẫn ghi | Full writer inventory |
| Tắt failed test để qua gate | Che correctness regression | Root-cause + fix |

---

## 41. Bài tập thực hành

### Bài 1. Nâng provider có phải chỉ đổi Maven/Gradle dependency?

**Đáp án:** Không. Cần kiểm API/framework/driver/DB combination, mappings, SQL, transactions, schema, caches, performance và rollback.

### Bài 2. Đổi `javax.persistence.EntityManager` thành `jakarta.persistence.EntityManager`

Một thư viện cũ vẫn nhận type javax. Có thể dùng trực tiếp không?

**Đáp án:** Không có binary compatibility giữa hai types; cần version/module/adapter tương thích.

### Bài 3. Mọi package javax đều phải đổi thành jakarta?

**Đáp án:** Không. Những Java SE packages như `javax.sql.DataSource` không phải một phần namespace migration của Jakarta Persistence.

### Bài 4. Provider mới khởi động thành công

Đã đủ go/no-go?

**Đáp án:** Chưa. Cần tests CRUD/queries, schema/data, locks, security và performance evidence.

### Bài 5. Provider mới thay `GenerationType.AUTO`

**Đáp án:** Kiểm actual generator và sequence/identity DDL, IDs, batches và mixed-version behavior.

### Bài 6. `allocationSize` đổi từ 1 sang 50

Có thể rollout old/new pods đồng thời luôn không?

**Đáp án:** Không nếu chưa chứng minh allocators/DB sequence settings tương thích. Có thể cần write freeze.

### Bài 7. Enum cũ lưu ordinal

Đổi sang STRING chỉ bằng annotation được không?

**Đáp án:** Không. Cần data backfill/mapping và rollback plan.

### Bài 8. Legacy data có nulls nhưng target mapping NOT NULL

**Đáp án:** Kiểm data quality và xử lý/backfill trước siết constraint.

### Bài 9. Một Hibernate `@Filter` không có bên provider mới

**Đáp án:** Thay bằng portable query/security layer hoặc DB RLS có test mọi read/write paths.

### Bài 10. JPQL query trước đây dùng HQL extension

**Đáp án:** Đổi sang JPQL portable hoặc cô lập trong provider adapter; test parse và behavior trên target.

### Bài 11. Đổi provider thấy ít SQL hơn

Có chắc nhanh hơn không?

**Đáp án:** Không. Cần p95/p99, DB CPU, locks, network, memory và correctness.

### Bài 12. `@DataJpaTest` flush rồi clear

Đã commit test data chưa?

**Đáp án:** Thường chưa; test transaction mặc định rollback cuối test.

### Bài 13. Target provider khác thứ tự INSERT

**Đáp án:** Chỉ là regression nếu phá FK/constraints/business state hoặc budgets; không ép exact SQL order không được spec bảo đảm.

### Bài 14. Old app không đọc được status mới

**Đáp án:** Không thể binary rollback an toàn. Cần expand-contract/dual-read hoặc forward-fix plan.

### Bài 15. Data backfill đang chạy thì bị ngắt

**Đáp án:** Dùng checkpoints/chunks/idempotent retry, không chạy lại mù quáng gây duplicate/corruption.

### Bài 16. User T1 nhìn thấy row T2 sau upgrade

**Đáp án:** Security no-go; dừng rollout, kiểm vendor filter/native/cache/tenant scoping và remediation.

### Bài 17. Testcontainers với H2 thay PostgreSQL

**Đáp án:** H2 không đủ chứng minh PostgreSQL-specific SQL/locks. Dùng DB engine/version đại diện.

### Bài 18. Chuyển Long PK sang UUID cùng đợt nâng

**Đáp án:** Đây là data/API migration lớn; tách release nếu có thể, xét FK/event/cache/mixed writers.

### Bài 19. `@Version` stale update fail tại commit thay vì merge

**Đáp án:** Có thể là timing khác; test bao toàn transaction và xác nhận final DB state.

### Bài 20. Old/new providers cùng dùng shared L2 cache

**Đáp án:** Cần kiểm format/keys/invalidation; có thể tách cache namespace và warm-up lại.

### Bài 21. Canary ít traffic nhưng cùng sequence

**Đáp án:** Dù ít requests vẫn có thể collision/mixed allocator risk; cần test trước canary.

### Bài 22. Một background worker bị bỏ quên

**Đáp án:** Có thể tiếp tục ghi legacy schema/IDs; inventory mọi writer và đưa vào cutover plan.

### Bài 23. Restore database snapshot

**Đáp án:** Có thể mất writes mới hợp lệ, cần RPO/RTO, reconciliation/approval; không coi là rollback vô hại.

### Bài 24. New provider query count tăng 4 → 104

**Đáp án:** Điều tra N+1/fetch plan, so latency và SLO; không chỉ quan tâm CRUD test pass.

### Bài 25. Xóa old column ngay sau cutover

**Đáp án:** Có thể chặn rollback. Chỉ contract sau khi hết rollback window và đã dừng old readers/writers.

### Bài 26. Provider property bị bỏ qua nhưng app vẫn chạy

**Đáp án:** Kiểm behavior thật như batching/fetch/timeout; vendor-specific config không tự portable.

### Bài 27. Chỉ test một tenant

**Đáp án:** Không phát hiện cross-tenant leaks; seed T1/T2 và owner/ACL negative cases.

### Bài 28. JPA API mới nhưng metamodel compiler vẫn dùng javax

**Đáp án:** Annotation processor mismatch; nâng processor và rebuild generated sources.

### Bài 29. Kiểm toán schema bằng auto-DDL của provider mới

**Đáp án:** Không xem generated DDL là source of truth nếu migrations quản lý schema; diff và review với schema thực.

### Bài 30. Cần quyết định go/no-go

**Đáp án:** Dựa trên correctness, data reconciliation, compatibility, performance, rollout/rollback readiness và sign-off owners, không chỉ deadline.

---

## 42. Checklist trước khi phê duyệt nâng cấp

1. Đã định nghĩa đúng loại thay đổi: API/provider/platform/DB?
2. Có owner, business invariants và phạm vi services?
3. Đã kiểm kê tất cả writers/readers?
4. Có target support matrix được xác minh?
5. Có ghi exact runtime versions?
6. Có dependency BOM/lock reproducible?
7. Có xử lý javax→jakarta packages/XML/metamodel?
8. Có inventory provider extensions?
9. Có plan cho custom types/converters/listeners?
10. Có mapping review ID/composite keys/associations?
11. Có schema diff và migration scripts?
12. Có kế hoạch cho enum/timezone/decimal/UUID data?
13. Có kiểm dữ liệu legacy trên staging?
14. Có backfill checkpoint và reconciliation?
15. Có bảo đảm sequence/generator compatibility?
16. Có chứng minh mixed-version writes an toàn hoặc chọn write freeze?
17. Có portable CRUD/transaction tests?
18. Có test optimistic locking và unique/FK constraints?
19. Có JPQL/Criteria/native/bulk suites?
20. Có tenant/ACL negative tests?
21. Có test fetching, caches và lazy behavior?
22. Có test Spring/JTA transaction boundary?
23. Có database Testcontainers production-like?
24. Có baseline và target performance measurement?
25. Có ngưỡng SQL/N+1/p95/p99/lock budgets?
26. Có staging rehearsal và representative data?
27. Có canary/rollout plan với triggers dừng?
28. Có rollback binary/config/schema/data phù hợp?
29. Có RPO/RTO và ownership cho data restore?
30. Có kiểm old app đọc được new writes nếu rollback dự kiến?
31. Có kế hoạch outbox/consumer/event compatibility?
32. Có audit và security logging thích hợp?
33. Có runbook incident/reconciliation?
34. Có monitor producer/consumer/DB metrics?
35. Có go/no-go approval rõ ràng?
36. Có xác định thời điểm được drop old schema/config?
37. Có post-cutover verification và incident review?
38. Có tài liệu hóa các vendor dependencies còn lại?

---

## 43. Quy trình tổng thể

~~~text
                 Yêu cầu nâng provider / Jakarta Persistence
                                    |
                                    v
                          Inventory + business invariants
                                    |
                                    v
                          Chọn supported target stack
                                    |
                                    v
                          Compatibility impact analysis
                                    |
                 +------------------+------------------+
                 |                                     |
                 v                                     v
          Code/API namespace                      Data/DDL impact
          + vendor extensions                     + ID generators
                 |                                     |
                 +------------------+------------------+
                                    |
                                    v
                          Contract/integration tests
                                    |
                                    v
                      Legacy data + schema rehearsal
                                    |
                                    v
                        Performance + mixed-version tests
                                    |
                                    v
                        Rollback/forward-fix ready?
                               /             \
                              No             Yes
                              |               |
                              v               v
                       Rework / hold     Go/no-go approval
                                              |
                                              v
                                   Canary or write-freeze cutover
                                              |
                                              v
                                 Production verification/monitoring
                                              |
                                              v
                                Contract obsolete schema/config
~~~

### 43.1. Zero downtime không phải mục tiêu cao hơn tính đúng

Nếu hai providers không thể ghi an toàn trên cùng sequence/schema, một maintenance window có kiểm soát là lựa chọn đúng đắn hơn mixed deployment gây duplicate keys hoặc mất dữ liệu.

### 43.2. Kết thúc migration chỉ sau dữ liệu được đối soát

Một deployment xanh trong orchestration platform chưa có nghĩa migration đã hoàn thành. Chỉ đóng thay đổi khi invariants, queries, transaction behavior, security, performance và rollback/closure plan đã được xác nhận.

---

## 44. Tổng kết

**Lập kế hoạch nâng phiên bản JPA provider hoặc Jakarta Persistence là một thay đổi của hệ thống dữ liệu, không chỉ là một thay đổi build dependency.** Những việc quan trọng:

1. Tách rõ **API**, **provider**, **framework/platform**, **JDK**, **driver** và **database**; chọn tổ hợp được hỗ trợ thay vì những versions rời rạc.
2. Kiểm kê runtime/dependency thực tế, bao gồm module cũ, jobs, custom types, caches, query hints và build-time enhancement.
3. Chuyển `javax.persistence` sang `jakarta.persistence` có chủ đích; cập nhật XML/metamodel/third-party integrations chứ không chỉ source imports.
4. Review mapping, generated IDs, sequence allocation, enum/time/decimal types và native queries trên **schema production hiện hữu**.
5. Dùng **migrations được duyệt**, expand–migrate–contract nếu cần tương thích old/new binaries.
6. Kiểm tra **mixed-version writes**, đặc biệt ID generators và event/data representations, trước khi dùng canary/rolling deployment.
7. Có portable contract suite, provider/database-specific suite, Testcontainers và concurrency tests; đọc lại dữ liệu từ transaction mới khi kiểm durable state.
8. Duy trì tenant/ACL predicates, uniqueness, FK integrity, optimistic locking và idempotency như những bất biến không thể thương lượng.
9. Đo SQL counts, batching, locks, p95/p99, cache và DB resource usage để chặn regression hiệu năng.
10. Thiết kế rollback **cho binary, cấu hình, schema và dữ liệu mới ghi**, với RPO/RTO/reconciliation rõ ràng; không coi redeploy old code là đủ.
11. Gắn từng giai đoạn với điều kiện go/no-go, owners, observability, incident runbook và thời điểm contract old schema.
12. Không xóa cấu hình/column cũ cho đến khi hết rollback window và mọi consumers/writers đã chuyển.

Một upgrade thành công là upgrade mà **ứng dụng tiếp tục đọc đúng, ghi đúng, kiểm soát concurrency đúng, không lộ dữ liệu và có thể phục hồi khi gặp sự cố**. Khi kế hoạch xác định rõ cách chứng minh từng điều đó trước production, việc thay provider hay nâng Jakarta Persistence trở thành một thay đổi kỹ thuật có kiểm soát thay vì một cuộc thử nghiệm trên dữ liệu thật.
