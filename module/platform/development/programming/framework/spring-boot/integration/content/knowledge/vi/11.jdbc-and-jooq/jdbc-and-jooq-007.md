# Thiết lập jOOQ và DSLContext do Boot cấu hình

## 1. Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, một hướng tích hợp cơ sở dữ liệu quan trọng là dùng **JDBC và jOOQ** để thực thi SQL có kiểm soát. Module còn xem xét HTTP client, cache, message broker và các adapter của Spring Integration; vì vậy kết nối cơ sở dữ liệu phải phù hợp với cấu hình môi trường, giao dịch, hợp đồng dữ liệu, lỗi, xử lý trùng lặp, kiểm thử và quan sát luồng tích hợp thực tế.

**jOOQ** (Java Object Oriented Querying) cung cấp DSL để xây dựng câu SQL bằng Java. Khi có mã Java được sinh từ schema database, compiler có thể kiểm tra tên bảng, cột và nhiều kiểu dữ liệu ngay khi biên dịch. **DSLContext** là điểm bắt đầu cho các truy vấn của jOOQ, chẳng hạn **select**, **insertInto**, **update** và **deleteFrom**.

**Spring Boot có thể tự tạo bean DSLContext** gắn với **DataSource** do ứng dụng cấu hình. Trong trường hợp chuẩn với một cơ sở dữ liệu, ứng dụng thường chỉ cần khai báo dependency, cấu hình JDBC và inject DSLContext để sử dụng. Bạn không cần tự tạo kết nối JDBC hoặc tự khởi tạo DSLContext trong từng repository.

Sau bài này, người học có thể:

1. Thiết lập dependency jOOQ, driver JDBC và datasource trong Spring Boot.
2. Giải thích những bean Boot có thể tự cấu hình và điều kiện để auto-configuration hoạt động.
3. Phân biệt thiết lập **DSLContext lúc runtime** và **code generation lúc build**.
4. Dùng DSLContext do Spring quản lý trong một repository có truy vấn type-safe.
5. Kết hợp truy vấn jOOQ với transaction, xử lý lỗi, kiểm thử và giới hạn connection pool.
6. Biết khi nào nên dùng **DefaultConfigurationCustomizer** hoặc tự cấu hình DSLContext.

## 2. Vai trò của từng thành phần

Mô hình cho một ứng dụng quản lý tồn kho:

~~~mermaid
flowchart TD
    A["application.yml / biến môi trường"] --> B["Spring Boot DataSource auto-configuration"]
    C["JDBC driver + connection pool"] --> B
    B --> D["DataSource"]
    D --> E["jOOQ auto-configuration"]
    F["spring.jooq.sql-dialect"] --> E
    G["TransactionManager nếu có"] --> E
    H["DefaultConfigurationCustomizer nếu có"] --> E
    E --> I["org.jooq.Configuration"]
    I --> J["DSLContext bean"]
    J --> K["InventoryRepository"]
    K --> L["Application service"]
    M["Schema database + jOOQ code generator"] --> N["Java table / field classes"]
    N --> K
~~~

| Thành phần | Trách nhiệm | Được tạo khi nào? |
| --- | --- | --- |
| **DataSource** | Cung cấp JDBC Connection, thường qua pool như HikariCP | Runtime, bởi Boot hoặc cấu hình của ứng dụng |
| **SQLDialect** | Cho jOOQ biết biến thể cú pháp SQL cần render | Runtime, Boot suy ra từ datasource hoặc cấu hình tường minh |
| **org.jooq.Configuration** | Gom ConnectionProvider, dialect, Settings, listener và các provider khác | Runtime, Boot có thể tạo |
| **DSLContext** | API thực thi DSL query dựa trên Configuration | Runtime, Boot có thể tạo thành Spring bean |
| **Generated tables/records** | Kiểu Java biểu diễn schema, cột và record | Build time, do jOOQ code generator sinh ra |
| **Repository/application service** | Áp dụng truy vấn và nghiệp vụ trên DSLContext | Runtime, do ứng dụng viết |

Ba điểm cần phân biệt:

- **Spring Boot không tự chạy jOOQ code generation chỉ vì có starter**. Generator là một bước build riêng, cần truy cập schema đầu vào.
- **DSLContext không phải là một connection cố định**; nó giữ cấu hình và qua ConnectionProvider lấy kết nối phục vụ truy vấn. Có thể inject DSLContext vào repository dùng chung thay vì tự tạo mỗi lần gọi.
- **jOOQ sử dụng JDBC là xử lý blocking**. Dùng nó trên luồng I/O reactive cần bố trí thread phù hợp; một DSLContext JDBC không biến thành R2DBC client.

## 3. Chuẩn bị dependency

### 3.1. Ví dụ Maven

Với dự án có **spring-boot-starter-parent** hoặc Spring Boot BOM quản lý dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jooq</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**spring-boot-starter-jooq** cung cấp các dependency cần cho tích hợp jOOQ với JDBC của Spring Boot. Driver PostgreSQL phải có trên runtime classpath để **DataSource** kết nối tới PostgreSQL. Nếu dùng MySQL, MariaDB hoặc H2 thì thay bằng driver tương ứng.

Đối với dự án Gradle có Spring Boot dependency management, khai báo tương đương:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các mẫu trên giả định dự án đã có plugin Spring Boot và quản lý phiên bản. Không nên tùy ý ghép starter của một phiên bản Boot với jOOQ runtime hoặc codegen ở phiên bản không tương thích. **Hãy kiểm tra ma trận phiên bản Java, Spring Boot và jOOQ của chính dự án**; package import của một số lớp auto-configuration cũng thay đổi giữa các thế hệ Spring Boot.

### 3.2. Một schema minh họa

Giả sử database PostgreSQL có bảng tồn kho:

~~~sql
CREATE TABLE inventory (
    sku           varchar(64) PRIMARY KEY,
    available_qty integer NOT NULL CHECK (available_qty >= 0),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
~~~

Đây chỉ là DDL minh họa. Trong dự án thực tế, quản lý DDL bằng migration như Flyway hoặc Liquibase, có thứ tự áp dụng rõ ràng theo môi trường. jOOQ được dùng để **truy vấn**; bản thân việc thêm starter không thay thế migration.

## 4. Cấu hình DataSource và dialect

Ví dụ **application.yml** cho môi trường local:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 2000
  jooq:
    sql-dialect: POSTGRES
~~~

Ý nghĩa:

- **spring.datasource.url / username / password**: kết nối JDBC. Mật khẩu được lấy từ biến môi trường **DB_PASSWORD**; không đưa mật khẩu thật vào source control.
- **spring.datasource.hikari.maximum-pool-size**: số connection tối đa trong pool HikariCP ở ví dụ này; đây là giá trị minh họa, không phải khuyến nghị chung cho mọi dịch vụ.
- **spring.datasource.hikari.connection-timeout**: thời gian chờ mượn connection từ pool, tính bằng mili giây; không đồng nghĩa với thời gian timeout của một câu SQL đang chạy.
- **spring.jooq.sql-dialect**: yêu cầu jOOQ render cú pháp theo PostgreSQL.

Trong trường hợp datasource được nhận diện, Spring Boot có thể **tự suy ra SQL dialect**; khi không nhận diện được, Boot dùng **DEFAULT**. Nếu hệ thống cần một dialect xác định, cấu hình tường minh và kiểm tra trong test sẽ dễ kiểm soát hơn. Lưu ý Boot chỉ có thể tự cấu hình những dialect tương thích với phiên bản jOOQ đang sử dụng, bao gồm giới hạn theo edition.

Với deployment, nên tách cấu hình từng môi trường và cung cấp credential qua secret manager, biến môi trường hoặc cơ chế cấu hình bảo mật. Không mở rộng quyền database account của ứng dụng sang quyền DDL nếu runtime không cần.

## 5. DSLContext do Spring Boot tạo như thế nào?

Khi dependency cần thiết hiện diện, **DataSource** khả dụng và ứng dụng chưa cung cấp bean thay thế tương ứng, jOOQ auto-configuration của Spring Boot thường cung cấp:

1. **ConnectionProvider** làm việc với DataSource do Spring quản lý.
2. **TransactionProvider** tích hợp Spring transaction nếu có **PlatformTransactionManager** thích hợp.
3. Cấu hình liên quan đến chuyển đổi lỗi SQL sang hệ exception truy cập dữ liệu của Spring.
4. **org.jooq.Configuration**, kết hợp dialect, connection, listener và các tùy chỉnh.
5. Bean **DSLContext** dùng Configuration trên.

Việc tạo các bean có điều kiện **@ConditionalOnMissingBean**: nếu ứng dụng tự cung cấp bean cùng vai trò, Boot có thể bỏ qua phần auto-configuration tương ứng. Vì vậy, không nên thêm bean **new DefaultDSLContext(...)** hoặc **DSL.using(...)** chỉ để “kích hoạt jOOQ”; làm vậy có thể bỏ qua wiring kết nối, transaction hoặc exception translation mà Boot đã thiết lập.

Một cách sử dụng cơ bản:

~~~java
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {

    private final DSLContext dsl;

    public InventoryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    // Các phương thức truy vấn sử dụng dsl ở phần sau.
}
~~~

Spring inject bean DSLContext đã được cấu hình sẵn. Repository không cần giữ **Connection** hoặc gọi **close()** trên connection mà nó không tự sở hữu. Khi thực thi query, jOOQ và infrastructure bên dưới chịu trách nhiệm cấp phát và trả kết nối theo cấu hình.

### Kiểm tra hệ thống thực sự nhận bean của Boot

Trong ứng dụng test, có thể xác nhận DSLContext và dialect:

~~~java
@SpringBootTest
class JooqWiringTest {

    @Autowired
    private DSLContext dsl;

    @Test
    void bootConfiguresDslContext() {
        assertNotNull(dsl);
        assertEquals(
                SQLDialect.POSTGRES,
                dsl.configuration().dialect()
        );
    }
}
~~~

Các import JUnit và Spring Test được lược bỏ. Test cần database test đúng cấu hình; chỉ kiểm tra bean hiện diện chưa chứng minh truy vấn có thể kết nối và thực thi. Khi khởi động thất bại, kiểm tra **Condition Evaluation Report** của Spring Boot cùng lỗi tạo DataSource và nguồn credential, thay vì khởi tạo DSLContext thủ công như một đường vòng.

## 6. Code generation: phần cần cấu hình riêng

jOOQ có thể tạo SQL động bằng **DSL.table(...)**, **DSL.field(...)**, nhưng lợi thế nổi bật của jOOQ là dùng **lớp Java được sinh từ schema**. Các lớp generated thường chứa trường bảng, cột và kiểu dữ liệu; compiler có thể phát hiện nhiều lỗi khi tên cột bị đổi.

Quy trình phù hợp:

~~~mermaid
flowchart LR
    A["Migration SQL"] --> B["Schema database cho build/test"]
    B --> C["jOOQ code generator"]
    C --> D["Generated Java sources"]
    D --> E["Compile ứng dụng"]
    E --> F["Runtime: Boot inject DSLContext"]
~~~

Với Maven, có thể dùng plugin **org.jooq:jooq-codegen-maven** trong pha **generate-sources**:

~~~xml
<plugin>
    <groupId>org.jooq</groupId>
    <artifactId>jooq-codegen-maven</artifactId>
    <executions>
        <execution>
            <phase>generate-sources</phase>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
    <dependencies>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>${postgresql.version}</version>
        </dependency>
    </dependencies>
    <configuration>
        <jdbc>
            <driver>org.postgresql.Driver</driver>
            <url>${env.JOOQ_CODEGEN_URL}</url>
            <user>${env.JOOQ_CODEGEN_USER}</user>
            <password>${env.JOOQ_CODEGEN_PASSWORD}</password>
        </jdbc>
        <generator>
            <database>
                <name>org.jooq.meta.postgres.PostgresDatabase</name>
                <inputSchema>public</inputSchema>
            </database>
            <target>
                <packageName>com.example.shop.jooq</packageName>
                <directory>target/generated-sources/jooq</directory>
            </target>
        </generator>
    </configuration>
</plugin>
~~~

**Điều kiện của ví dụ:** POM dùng **spring-boot-starter-parent** quản lý phiên bản plugin và dependency, bao gồm thuộc tính **postgresql.version**; nếu dự án chỉ nhập BOM hoặc dùng cấu trúc build khác, cần cấu hình version/plugin management cho phù hợp. Biến **JOOQ_CODEGEN_*** phải có trong môi trường chạy Maven, trỏ đến database đã áp dụng migrations. Code generator chạy trong quá trình build, dùng credential chỉ đọc metadata nếu có thể; không nên trỏ thẳng đến production.

Một số điều cần quyết định rõ:

- Tạo generated sources trong CI từ **schema đã migrate**, tránh chạy generator trên schema cũ hoặc lệch phiên bản.
- Đồng bộ **jOOQ codegen** và **jOOQ runtime**, đặc biệt khi thay đổi phiên bản major/minor.
- Chọn package và cách publish generated classes; có dự án commit code sinh ra, có dự án sinh ở mỗi build. Cần bảo đảm build tái lập được.
- Đặt tên và datatype của cột trong migration làm nguồn sự thật. Thay đổi schema cần có quá trình cập nhật codegen và test trước khi phát hành.
- Với Gradle, dùng jOOQ codegen plugin phù hợp phiên bản jOOQ; chi tiết cấu hình plugin là trách nhiệm của pipeline build, không phải bean DSLContext lúc runtime.

**Lưu ý:** các tên lớp minh họa bên dưới giả định jOOQ đã sinh **com.example.shop.jooq.tables.references.INVENTORY** hoặc đường import tương ứng với phiên bản/cấu hình generator. Hãy dùng đúng tên package và cấu trúc classes mà build của bạn sinh ra; nhiều cấu hình jOOQ xuất bảng qua lớp **Tables**.

## 7. Viết repository type-safe bằng DSLContext được inject

Giả sử codegen sinh trường **INVENTORY.SKU**, **INVENTORY.AVAILABLE_QTY** và **INVENTORY.UPDATED_AT**. Repository dùng chúng trực tiếp:

~~~java
import java.util.Optional;
import org.jooq.DSLContext;
import org.springframework.stereotype.Repository;
import static com.example.shop.jooq.Tables.INVENTORY;

@Repository
public class InventoryRepository {

    private final DSLContext dsl;

    public InventoryRepository(DSLContext dsl) {
        this.dsl = dsl;
    }

    public Optional<Integer> availableQuantity(String sku) {
        Integer value = dsl
                .select(INVENTORY.AVAILABLE_QTY)
                .from(INVENTORY)
                .where(INVENTORY.SKU.eq(sku))
                .fetchOne(INVENTORY.AVAILABLE_QTY);

        return Optional.ofNullable(value);
    }

    public int decreaseIfEnough(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        return dsl.update(INVENTORY)
                .set(INVENTORY.AVAILABLE_QTY,
                        INVENTORY.AVAILABLE_QTY.minus(quantity))
                .set(INVENTORY.UPDATED_AT, DSL.currentOffsetDateTime())
                .where(INVENTORY.SKU.eq(sku))
                .and(INVENTORY.AVAILABLE_QTY.ge(quantity))
                .execute();
    }
}
~~~

Trong ví dụ trên, cần import **org.jooq.impl.DSL** cho biểu thức thời gian; **currentOffsetDateTime()** phải phù hợp với kiểu cột, dialect và cách generator mapping. Có thể để database tự cập nhật mốc thời gian thông qua thiết kế schema hoặc SQL được quản lý tập trung nếu muốn tránh phụ thuộc vào cách mapping timestamp.

Các chi tiết cần hiểu:

- **fetchOne(field)** trả giá trị hoặc **null** nếu không có dòng nào; ví dụ chuyển sang **Optional** để phân biệt bản ghi không tồn tại.
- Điều kiện **available_qty >= quantity** được thực hiện **trong cùng câu UPDATE**, giúp ngăn giảm tồn kho xuống âm dưới cạnh tranh ghi. Đếm số dòng được cập nhật để biết thao tác có thành công.
- jOOQ bind giá trị qua cơ chế truy vấn có tham số; tránh ghép chuỗi SQL trực tiếp từ SKU do người dùng cung cấp.
- **execute()** trả số dòng chịu ảnh hưởng. Giá trị 0 có thể là không có SKU hoặc tồn kho không đủ; nếu nghiệp vụ cần phân biệt, phải thực hiện thêm truy vấn/thiết kế trạng thái phù hợp và cân nhắc race condition.

Với hệ thống tích hợp, repository nên trả về dữ liệu hoặc mã trạng thái rõ ràng để application service có thể quyết định ghi giao dịch tiếp, trả lỗi nghiệp vụ hay phát event.

## 8. Giao dịch Spring và jOOQ dùng chung DataSource

Khi **DSLContext** và **PlatformTransactionManager** được cấu hình phù hợp trên cùng datasource, các truy vấn jOOQ có thể tham gia vào transaction do Spring quản lý. Một service thực hiện giảm tồn kho và ghi bản ghi giữ hàng:

~~~java
@Service
public class ReservationService {

    private final DSLContext dsl;

    public ReservationService(DSLContext dsl) {
        this.dsl = dsl;
    }

    @Transactional
    public void reserve(UUID reservationId, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int changed = dsl.update(INVENTORY)
                .set(INVENTORY.AVAILABLE_QTY,
                        INVENTORY.AVAILABLE_QTY.minus(quantity))
                .where(INVENTORY.SKU.eq(sku))
                .and(INVENTORY.AVAILABLE_QTY.ge(quantity))
                .execute();

        if (changed != 1) {
            throw new IllegalStateException(
                    "SKU not found or insufficient stock");
        }

        dsl.insertInto(RESERVATION,
                        RESERVATION.ID,
                        RESERVATION.SKU,
                        RESERVATION.QUANTITY)
                .values(reservationId, sku, quantity)
                .execute();
    }
}
~~~

Ở đây giả định codegen đã sinh bảng **RESERVATION** (các import được lược bỏ). Nếu insert thất bại và exception runtime thoát khỏi service, transaction **thông thường** được Spring rollback, kể cả UPDATE đã chạy trước đó. Với checked exception, cần hiểu quy tắc rollback mặc định hoặc cấu hình **rollbackFor** khi phù hợp.

Điều kiện quan trọng:

1. Phương thức **@Transactional** phải được gọi qua cơ chế proxy/interceptor transaction của Spring; tự gọi một phương thức cùng lớp có thể khiến transaction advice không chạy như mong đợi.
2. **DSLContext** và transaction manager phải sử dụng cùng datasource hoặc hạ tầng transaction tương thích; một DSLContext tự tạo với connection riêng có thể không tham gia transaction.
3. Transaction JDBC **không bao phủ** lời gọi HTTP tới hệ thống khác hoặc publish message lên broker. Muốn đảm bảo dữ liệu và event không lệch nhau, cân nhắc **transactional outbox**, cơ chế chống trùng và consumer idempotent.
4. Khóa unique trên **reservation_id** có thể giúp chống tạo bản ghi trùng khi caller retry; cần quyết định việc trả kết quả cũ hoặc báo xung đột trong application service.
5. Giữ transaction ngắn; tránh vừa giữ database connection vừa gọi HTTP downstream chậm.

Spring Boot cung cấp **SpringTransactionProvider** cho jOOQ khi có **PlatformTransactionManager** phù hợp. Nếu thay ConnectionProvider hoặc transaction provider bằng bean tùy biến, phải kiểm tra lại khả năng tham gia transaction và rollback thực tế.

## 9. Tùy biến DSLContext mà vẫn giữ auto-configuration

Đối với ứng dụng chỉ cần thay đổi **Settings**, nên giữ DSLContext của Boot và dùng **DefaultConfigurationCustomizer**:

~~~java
@Configuration
public class JooqSettingsConfiguration {

    @Bean
    DefaultConfigurationCustomizer jooqCustomizer() {
        return configuration -> {
            configuration.settings().setRenderSchema(false);
            configuration.settings().setExecuteLogging(false);
        };
    }
}
~~~

Ví dụ có ý nghĩa:

- **renderSchema(false)**: bỏ schema qualifier khỏi SQL được render; chỉ nên dùng khi search path/default schema của connection đã được kiểm soát. Nếu có nhiều schema hoặc tenant, bỏ qualifier có thể khiến truy vấn hướng tới bảng sai.
- **executeLogging(false)**: tắt logging truy vấn mặc định của jOOQ qua cơ chế tương ứng; không tắt mọi log SQL của driver, monitoring hay proxy. Nếu cần log SQL để chẩn đoán, cân nhắc lượng dữ liệu nhạy cảm và môi trường.

Lưu ý về import: ở Spring Boot 3.x, customizer thuộc **org.springframework.boot.autoconfigure.jooq.DefaultConfigurationCustomizer**; ở Spring Boot 4.x, package auto-configuration jOOQ được tổ chức lại, ví dụ **org.springframework.boot.jooq.autoconfigure.DefaultConfigurationCustomizer**. Chọn theo version thực tế, tránh copy import giữa các phiên bản mà không kiểm tra.

Ngoài Settings, cấu hình nâng cao có thể liên quan **ExecuteListenerProvider**, connection provider, transaction provider hoặc custom binding. Khi thay đổi các thành phần này, cần kiểm tra thứ tự listener, exception translation và các bean đang được Boot tự cấu hình.

### Khi nào mới tự tạo Configuration hoặc DSLContext?

Thông thường, không cần tạo riêng nếu ứng dụng chỉ có **một datasource** và một cấu hình jOOQ. Tự tạo khi có yêu cầu thực sự, ví dụ:

- Nhiều datasource với dialect, schema và transaction manager khác nhau.
- Chọn connection hoặc tenant theo quy tắc riêng không thể biểu diễn an toàn bằng cấu hình mặc định.
- Cấu hình listener/transaction provider đặc thù phải thay thế phần wiring chuẩn.

Khi có nhiều datasource, cần định nghĩa rõ mỗi DSLContext thuộc datasource nào, dùng **@Qualifier**, **@Primary** và transaction manager tương ứng nếu cần. Không giả định Boot tự sinh một DSLContext hoàn chỉnh **cho mỗi datasource**. Một DSLContext gắn nhầm datasource có thể đọc hoặc ghi nhầm database mà câu SQL vẫn hợp lệ.

## 10. Lỗi truy cập dữ liệu và giới hạn tài nguyên

Hành vi vận hành vẫn bị chi phối bởi **JDBC driver, DataSource/pool và database** dù truy vấn được viết bằng jOOQ:

| Vấn đề | Biểu hiện | Cách tiếp cận |
| --- | --- | --- |
| Không kết nối được database | Lỗi driver, DNS, authentication, TLS | Xác minh URL, credential, network và cấu hình bảo mật |
| Pool hết connection | Request chờ lâu rồi lỗi mượn connection | Đo số connection active, thời gian checkout, truy vấn chậm và transaction kéo dài |
| Query timeout / lock timeout | Truy vấn chờ khóa hoặc chạy quá lâu | Đặt timeout phù hợp ở JDBC/database; phân tích execution plan và lock |
| Sai schema hoặc codegen cũ | “Table/column not found”, lỗi kiểu dữ liệu | Đồng bộ migration, code generation và môi trường |
| Unique constraint violation | Ghi trùng reservation hoặc request key | Trả lỗi nghiệp vụ phù hợp, dùng unique key và idempotency |
| SQL dialect không đúng | SQL render không hợp lệ trên DB | Kiểm tra **spring.jooq.sql-dialect** và dialect thực tế |
| Thiếu transaction | Một phần các lệnh ghi thành công trước khi lỗi | Xác minh annotation, transaction manager, connection provider và đường gọi |

Spring Boot có tích hợp cơ chế chuyển đổi một số lỗi thực thi SQL của jOOQ sang **DataAccessException** của Spring. Không nên phụ thuộc vào đúng một class exception cho mọi lỗi của mọi driver; hãy kiểm thử điều kiện thực tế, đồng thời phân biệt lỗi nghiệp vụ (ví dụ không đủ tồn kho) với lỗi hạ tầng.

**Connection timeout của HikariCP không phải statement timeout.** Tham số **spring.datasource.hikari.connection-timeout** giới hạn thời gian chờ *mượn connection*. Để giới hạn truy vấn chậm, cần cấu hình timeout JDBC/database tương ứng và kiểm tra ứng dụng có xử lý timeout, rollback, retry đúng cách không.

**Không retry mọi thao tác ghi một cách mù quáng.** Với request giảm tồn kho, timeout có thể xảy ra sau khi DB commit nhưng trước khi caller nhận được phản hồi. Nếu gửi lại cùng request, phải có cơ chế chống trùng ở database hoặc tầng nghiệp vụ.

## 11. Kiểm thử tích hợp và quan sát

### Kiểm thử đúng hệ quản trị cơ sở dữ liệu

**@JooqTest** là test slice của Spring Boot dành cho jOOQ; nó cấu hình DSLContext và hạ tầng truy cập dữ liệu cần thiết. Tuy nhiên, bean application service/repository tùy chỉnh có thể cần **@Import** hoặc test rộng hơn. Package của annotation cũng có thể khác giữa các phiên bản Boot. Với **Spring Boot 4.x**, cần đưa module test jOOQ phù hợp vào test classpath, chẳng hạn starter **org.springframework.boot:spring-boot-starter-jooq-test**; chỉ thêm starter test chung có thể chưa cung cấp slice này. Với Spring Boot 3.x, kiểm tra test auto-configuration được quản lý trong phiên bản đang sử dụng.

Với truy vấn đặc thù PostgreSQL như **ON CONFLICT**, JSONB hoặc locking, ưu tiên test trên PostgreSQL thật dùng Testcontainers hoặc database test độc lập. H2 không luôn mô phỏng đúng cú pháp, transaction isolation hoặc giới hạn của PostgreSQL.

Ví dụ test repository ở mức logic:

~~~java
@JooqTest
@Import(InventoryRepository.class)
class InventoryRepositoryTest {

    @Autowired
    InventoryRepository inventoryRepository;

    @Test
    void unknownSkuReturnsEmpty() {
        assertTrue(
                inventoryRepository.availableQuantity(
                        "SKU-DOES-NOT-EXIST").isEmpty()
        );
    }
}
~~~

Để test chạy được, phải chuẩn bị schema và dữ liệu test phù hợp với datasource trong test context. Test trên giả lập có thể kiểm tra DSL logic, nhưng test dùng datasource thật mới xác nhận connection, dialect, migration và transaction.

Một bộ tình huống nên bao gồm:

1. Application context tạo được DSLContext và nhận đúng dialect.
2. Truy vấn SELECT với SKU tồn tại, không tồn tại và giá trị biên.
3. Hai request đồng thời giảm tồn kho: không được âm kho hoặc tạo kết quả vượt số lượng thực có.
4. INSERT thất bại giữa transaction: UPDATE trước đó rollback đúng.
5. Ghi lặp cùng **reservationId**: unique constraint hoặc idempotency xử lý như thiết kế.
6. Migration đổi cột: build codegen và compile báo sai biệt trước khi deploy.
7. Database không sẵn sàng, pool timeout, lock wait: lỗi không bị biến thành “không có dữ liệu”.

### Observability cần đo

- **Thời gian thực thi SQL** theo operation/query class; theo dõi p95/p99 và các truy vấn chậm.
- **HikariCP active, idle, pending connection** và số lần chờ pool timeout.
- **Transaction duration**, rollback và deadlock/lock timeout.
- **Tỷ lệ lỗi** theo loại DataAccessException hoặc SQLState phù hợp; tránh đưa SKU hoặc dữ liệu có cardinality cao vào nhãn metrics.
- **Correlation ID/trace** của request nghiệp vụ tới truy vấn database, sự kiện outbox và downstream.

Tuyệt đối cân nhắc dữ liệu nhạy cảm khi bật **jOOQ execute logging**, logging bind values hay SQL audit. Không in mật khẩu, token, thông tin cá nhân và payload nghiệp vụ vào log. Đối với truy vấn chậm, kết hợp thống kê database, query plan và kích thước pool để tìm đúng nút thắt.

## 12. Những nhầm lẫn thường gặp

**“Có spring-boot-starter-jooq là tự sinh Tables Java.”** Sai. Boot tạo hạ tầng runtime; code generation được cấu hình riêng trong build và phải đọc schema thật.

**“Phải tự gọi DSL.using(dataSource) trong mọi repository.”** Thường không cần. Điều đó làm trùng cấu hình, có thể bỏ qua transaction và listener do Boot thiết lập.

**“DSLContext là connection; nên tạo và đóng mỗi request.”** Không đúng. DSLContext là điểm truy cập DSL trên cấu hình; connection được lấy qua ConnectionProvider theo vòng đời thích hợp.

**“SQLDialect auto-detect luôn chính xác với mọi database.”** Không đảm bảo. Boot có thể rơi về DEFAULT hoặc bị giới hạn bởi edition; kiểm tra runtime với DB thật.

**“Bật @Transactional là đủ, kể cả khi viết cùng lúc vào DB và message broker.”** Transaction JDBC chỉ bảo vệ các thao tác thuộc transaction manager tương ứng; cần outbox hoặc cơ chế tích hợp khác để đảm bảo tính nhất quán liên hệ thống.

**“Dùng jOOQ là non-blocking.”** jOOQ qua JDBC vẫn blocking. Chọn thread model, giới hạn concurrency và connection pool cho đúng.

**“Hikari connection-timeout giới hạn thời gian query.”** Nó chủ yếu giới hạn việc chờ mượn connection; timeout của statement/database là vấn đề khác.

## 13. Checklist triển khai

Trước khi dùng jOOQ trong một luồng tích hợp, xác minh:

1. Starter, JDBC driver và phiên bản jOOQ/codegen tương thích với Spring Boot/Java đang dùng.
2. DataSource lấy URL, user và credential từ nguồn cấu hình đúng môi trường.
3. DSLContext được inject từ Spring; SQLDialect phù hợp với DB thật.
4. Migration và generated sources dùng cùng schema được kiểm soát phiên bản.
5. Repository dùng DSL field/record có type, bind tham số và xử lý kết quả rỗng có chủ đích.
6. Các thao tác ghi nhiều bước có transaction đúng datasource và rollback được kiểm thử.
7. Có unique key/idempotency khi caller hoặc consumer có thể gửi lại yêu cầu.
8. Pool, statement timeout, lock wait, retry và năng lực database được đo, không chỉ suy đoán.
9. Tests chạy với dialect thật cho truy vấn đặc thù; metric và log đủ chẩn đoán mà không lộ dữ liệu.

Với cách thiết lập này, **DSLContext do Spring Boot cấu hình** trở thành thành phần truy cập SQL thống nhất cho ứng dụng. Giá trị chính của jOOQ nằm ở SQL type-safe và khả năng diễn đạt truy vấn rõ ràng; tính tin cậy của tích hợp tiếp tục phụ thuộc vào quản lý schema, transaction, connection pool, kiểm thử và vận hành.

## Tài liệu tham khảo

- [Spring Boot Reference — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/reference/data/sql.html): datasource, DSLContext auto-configuration, dialect và customizer.
- [Spring Boot 3.5 Reference — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): hướng dẫn cho nhánh Spring Boot 3.x.
- [Spring Boot API — JooqAutoConfiguration (3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jooq/JooqAutoConfiguration.html): các bean ConnectionProvider, TransactionProvider và DSLContext.
- [jOOQ Manual — Code Generation Configuration](https://www.jooq.org/doc/latest/manual/code-generation/codegen-configuration/): cấu hình generator và nguồn schema.
- [jOOQ Manual — Transaction Management](https://www.jooq.org/doc/current/manual/sql-execution/transaction-management/): transaction provider và tương tác giao dịch.
