# Tránh chạy lại thay đổi lược đồ và khởi tạo dữ liệu ngoài ý muốn

Khi dùng CRaC (Coordinated Restore at Checkpoint), một ứng dụng Java có thể được khôi phục từ ảnh checkpoint mà không phải khởi động JVM và application context từ đầu. Các object trong heap được phục hồi, luồng thực thi tiếp tục từ trạng thái đã lưu và các callback afterRestore được gọi để tái tạo tài nguyên cần thiết.

Cơ sở dữ liệu có vòng đời riêng. Database server và dữ liệu của nó thường nằm ngoài tiến trình Java, nên checkpoint image không phải bản sao của database. Trong khoảng thời gian ứng dụng ở trạng thái checkpoint, database vẫn có thể tiếp tục hoạt động, schema có thể được migration và dữ liệu có thể thay đổi.

Vì vậy, cần phân biệt rõ các công việc khởi tạo database với công việc phục hồi kết nối sau restore. Migration schema và seed dữ liệu nên có cơ chế kiểm soát riêng, có thể chạy lặp an toàn khi cần, và không bị gọi lại ngoài ý muốn trong callback phục hồi.

## 1. Vì sao CRaC cần chú ý tới migration và initialization?

Một ứng dụng Java thường có các bước database khi khởi động:

- Tạo hoặc kiểm tra schema.
- Chạy migration để nâng phiên bản database.
- Tạo bảng, index, constraint, sequence hoặc view.
- Nạp dữ liệu tham chiếu như danh mục, loại trạng thái hoặc cấu hình mặc định.
- Tạo tài khoản quản trị ban đầu.
- Kiểm tra quyền và kết nối database.
- Khởi tạo connection pool và các repository.

Trong một lần khởi động thông thường, các bước này có thể được thực hiện bởi Spring Boot, Flyway, Liquibase, Hibernate hoặc mã bootstrap riêng.

Với CRaC, nếu checkpoint được tạo sau khi ứng dụng hoàn tất startup, ảnh có thể đã chứa trạng thái Java của các thành phần đó. Khi restore, tiến trình tiếp tục từ ảnh. **CRaC restore không tự khởi chạy lại main(), không tự tạo lại application context và không tự chạy lại toàn bộ startup hook như một lần khởi động JVM mới.**

Tuy nhiên, ứng dụng vẫn có thể vô tình chạy lại initialization nếu:

- Mã sau lời gọi Core.checkpointRestore() gọi lại hàm bootstrap.
- afterRestore callback gọi một phương thức khởi tạo tổng thể có cả migration và seed.
- Framework hoặc thư viện được cấu hình chạy initialization khi connection pool được tạo lại.
- Một tác vụ nền được khởi động lại và tự chạy script khởi tạo.
- Controller restore nhiều bản sao từ cùng image, và mỗi bản sao đều thực thi logic migration sau restore.
- Quy trình deployment tạo process mới thay vì restore image nhưng dùng chung startup script.

Cần xác định rõ đoạn code nào thực sự chạy khi restore và đoạn code nào chỉ chạy trong một startup mới. Điều này giúp tránh chạy DDL, seed hoặc các side effect nhiều lần.

## 2. Phân biệt migration, validation, seed và reconnect

Bốn công việc này có mục đích và vòng đời khác nhau.

| Công việc | Mục đích | Thời điểm thường phù hợp |
|---|---|---|
| Schema migration | Thay đổi cấu trúc database theo phiên bản | Startup có kiểm soát hoặc migration job riêng trước khi ứng dụng nhận traffic |
| Schema validation | Xác nhận schema hiện tại tương thích với ứng dụng | Startup hoặc bước kiểm tra sau khi kết nối lại |
| Data initialization / seed | Nạp dữ liệu ban đầu hoặc dữ liệu tham chiếu | Migration hoặc bootstrap có kiểm soát, dùng thao tác idempotent |
| Connection recovery | Tạo connection/session mới tới database | afterRestore hoặc lifecycle hook chuyên dụng của connection pool |

Không nên gộp cả bốn việc vào một hàm có tên chung như initializeDatabase() rồi gọi hàm đó từ afterRestore. Một hàm như vậy có thể vừa mở kết nối, vừa chạy migration, vừa chèn dữ liệu mặc định và vừa tạo tài khoản.

Hãy tách chúng thành các thành phần có trách nhiệm rõ ràng:

- Migration runner quản lý phiên bản schema.
- Seed runner quản lý dữ liệu tham chiếu và dữ liệu bootstrap.
- Schema validator kiểm tra tính tương thích.
- Connection manager quản lý pool và session.
- CRaC Resource quản lý việc dừng và phục hồi các tài nguyên thuộc tiến trình.

Một callback afterRestore thông thường chỉ cần tái tạo connection pool, xác minh kết nối và cập nhật readiness. Nó không nên chạy lại toàn bộ migration hoặc seed.

## 3. Restore tiếp tục từ checkpoint, không phải một lần startup mới

Đây là khác biệt quan trọng nhất khi thiết kế logic khởi tạo database.

Giả sử startup của ứng dụng có trình tự:

~~~text
JVM start
  -> Load configuration
  -> Create application context
  -> Run database migrations
  -> Seed reference data
  -> Create connection pool
  -> Warm-up services
  -> Application ready
  -> Create CRaC checkpoint
~~~

Khi restore image:

~~~text
Restore JVM process
  -> Restore heap and execution state
  -> Run afterRestore callbacks
  -> Reconnect database resources
  -> Resume execution after checkpoint
~~~

Các bước migration và seed nằm trước checkpoint đã hoàn tất trong trạng thái được lưu. Chúng không tự chạy lại chỉ vì tiến trình được restore.

Có thể hình dung bằng sơ đồ:

~~~mermaid
flowchart TD
    A["Fresh JVM startup"] --> B["Create application context"]
    B --> C["Run schema migration"]
    C --> D["Initialize seed data"]
    D --> E["Create database pool"]
    E --> F["Warm-up and validate"]
    F --> G["Checkpoint"]
    G --> H["Restore image"]
    H --> I["afterRestore: reconnect pool"]
    I --> J["Resume application"]
    J --> K["Serve requests"]
    style C fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    style D fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    style I fill:#dcfce7,stroke:#16a34a,color:#14532d
~~~

Sơ đồ này thể hiện trường hợp lý tưởng: migration và seed hoàn tất trước checkpoint; callback restore chỉ phục hồi tài nguyên kết nối.

Nếu code sau checkpoint gọi lại migration runner, hoặc callback afterRestore gọi lại bootstrap, các thao tác đó sẽ chạy vì ứng dụng yêu cầu chúng, không phải vì CRaC tự khởi động lại ứng dụng.

### 3.1 Trường hợp gọi Core.checkpointRestore()

Khi ứng dụng gọi Core.checkpointRestore(), luồng thực thi tiếp tục sau lời gọi trong tiến trình đã restore nếu checkpoint và restore thành công. Ví dụ:

~~~java
runDatabaseMigrations();
initializeReferenceData();

Core.checkpointRestore();

// Dòng này tiếp tục chạy trong tiến trình đã restore.
startServing();
~~~

Đoạn runDatabaseMigrations() và initializeReferenceData() nằm trước checkpoint nên không tự được thực hiện lần thứ hai khi lời gọi trả về sau restore.

Tuy nhiên, nếu viết:

~~~java
Core.checkpointRestore();

runDatabaseMigrations();
initializeReferenceData();
startServing();
~~~

thì migration và seed sẽ chạy sau restore vì chúng nằm sau lời gọi. Nếu nhiều instance cùng restore image này, nhiều tiến trình có thể cùng chạy logic đó. Vì vậy, vị trí của checkpoint trong startup flow rất quan trọng.

Khi checkpoint được kích hoạt từ bên ngoài, ứng dụng cũng tiếp tục từ trạng thái thread đã lưu. Không có một lần gọi main() mới chỉ vì một controller gửi yêu cầu restore.

## 4. Quản lý schema migration bằng versioned migration

Thay đổi schema nên được quản lý bằng migration có phiên bản. Mỗi migration mô tả một thay đổi cụ thể và được ghi nhận sau khi thực hiện thành công.

Ví dụ:

~~~text
db/migration/
  V001__create_customer_table.sql
  V002__add_customer_status.sql
  V003__create_order_index.sql
  V004__add_reference_country.sql
~~~

Một migration tool lưu lại các migration đã áp dụng trong database. Khi chạy lại, tool so sánh trạng thái hiện tại với danh sách migration và chỉ thực thi những thay đổi chưa được áp dụng, theo quy tắc của tool.

Điều này giúp phân biệt:

- Migration chưa chạy.
- Migration đã chạy thành công.
- Migration có checksum hoặc nội dung thay đổi.
- Migration thất bại hoặc database đang ở trạng thái cần can thiệp.

Không nên tự suy luận trạng thái schema chỉ từ việc một bảng đã tồn tại. Bảng có thể tồn tại nhưng thiếu cột, index, constraint hoặc có cấu trúc khác với phiên bản mong đợi.

### 4.1 Flyway

Flyway quản lý lịch sử migration trong bảng schema history, thường là **flyway_schema_history**. Bảng này lưu phiên bản, mô tả, script, checksum và trạng thái migration.

Ví dụ sử dụng:

~~~java
Flyway flyway = Flyway.configure()
        .dataSource(dataSource)
        .locations("classpath:db/migration")
        .load();

flyway.migrate();
~~~

Lệnh migrate áp dụng các migration còn thiếu theo cấu hình và lịch sử của Flyway. Việc gọi migrate nhiều lần không có nghĩa toàn bộ script cũ được chạy lại; tool dựa vào schema history để xác định phần việc còn lại.

Dù vậy, hãy tránh gọi migrate không cần thiết trong afterRestore. Khi nhiều instance cùng restore, chúng có thể cùng cố gắng kiểm tra hoặc áp dụng migration, gây thêm contention và làm thời gian phục hồi khó dự đoán.

Các thao tác hữu ích:

- migrate(): áp dụng migration chưa chạy.
- validate(): xác thực lịch sử và checksum migration theo cấu hình.
- info(): xem trạng thái migration.
- repair(): sửa metadata lịch sử trong tình huống được xác định; không phải công cụ sửa schema tùy ý.

Nếu script migration đã được áp dụng nhưng file script sau đó bị sửa, validation có thể phát hiện checksum không khớp. Không sửa migration cũ đã phát hành để làm thay đổi schema ở môi trường hiện hữu; hãy tạo migration mới.

### 4.2 Liquibase

Liquibase ghi nhận các changeSet đã chạy trong bảng **DATABASECHANGELOG**. Nó dùng bảng **DATABASECHANGELOGLOCK** để điều phối việc một tiến trình thực hiện changelog tại một thời điểm.

Một changeSet được nhận diện bằng id, author và file path. Khi chạy update, Liquibase so sánh changelog với lịch sử database để quyết định changeSet nào cần thực thi.

Cần chú ý các thuộc tính có thể làm changeSet chạy lại:

- runAlways khiến changeSet được thực hiện mỗi lần update.
- runOnChange cho phép thực hiện lại khi checksum của changeSet thay đổi.
- preConditions xác định điều kiện trước khi chạy.
- onFail và onError quyết định cách xử lý khi điều kiện hoặc thao tác gặp lỗi.

Các thuộc tính này có ích trong một số tình huống, nhưng nếu dùng không chủ ý có thể khiến script được chạy lại mỗi lần startup hoặc mỗi lần một instance restore rồi gọi update.

Hãy chỉ dùng runAlways hoặc runOnChange khi logic thật sự được thiết kế cho việc thực thi lặp và side effect của nó đã được kiểm soát.

### 4.3 Không tự quản lý migration chỉ bằng câu lệnh CREATE TABLE IF NOT EXISTS

Một câu lệnh như:

~~~sql
CREATE TABLE IF NOT EXISTS customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
~~~

có thể tránh lỗi khi bảng đã tồn tại, nhưng không chứng minh bảng hiện tại đúng cấu trúc yêu cầu. Nếu bảng đã có nhưng thiếu cột, sai kiểu dữ liệu hoặc thiếu constraint, câu lệnh trên vẫn có thể kết thúc bình thường.

Tương tự, kiểm tra một bảng có tồn tại rồi bỏ qua toàn bộ migration sẽ khiến schema drift khó phát hiện.

Dùng migration history để quản lý thay đổi theo phiên bản; dùng schema validation để kiểm tra cấu trúc thực tế.

## 5. Đảm bảo migration chỉ chạy ở một nơi

Trong hệ thống có nhiều replica, nếu mỗi instance tự chạy migration khi startup, có thể xảy ra nhiều tiến trình cùng kiểm tra hoặc thay đổi schema.

Migration tool thường có cơ chế locking hoặc kiểm tra lịch sử, nhưng vẫn cần một chính sách triển khai rõ ràng. Có hai cách thường dùng.

### 5.1 Migration job riêng

Một job hoặc deployment step chạy migration trước khi rollout phiên bản ứng dụng mới:

~~~text
Build artifact
  -> Start migration job
  -> Acquire database migration lock
  -> Apply pending migrations
  -> Validate schema
  -> Mark migration job successful
  -> Roll out application instances
  -> Create checkpoint after warm-up
~~~

Ưu điểm:

- Chỉ một thành phần chịu trách nhiệm thay đổi schema.
- Application instances không phải cùng thực hiện DDL.
- Có thể phân quyền database riêng cho migration job.
- Dễ kiểm soát thời gian, log và rollback/forward-fix.
- Restore nhiều bản sao từ một checkpoint image không kích hoạt migration job mới.

Application runtime có thể chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ, trong khi migration job có quyền DDL.

### 5.2 Migration khi startup có khóa

Một số hệ thống nhỏ chọn để ứng dụng chạy migration khi startup. Nếu dùng cách này:

- Migration tool phải có cơ chế locking phù hợp với database.
- Mỗi instance phải chờ migration hoàn tất trước khi readiness bật.
- Các migration phải có tính tương thích với phiên bản ứng dụng đang chạy.
- Cần kiểm soát số instance cùng startup.
- Không gọi lại migration runner trong afterRestore.
- Không cho phép nhiều phiên bản ứng dụng cạnh tranh thay đổi schema ngoài kế hoạch.

Cơ chế lock của migration tool không thay thế việc lập kế hoạch rollout. Một migration có thể được tuần tự hóa nhưng vẫn làm hỏng ứng dụng phiên bản cũ nếu nó xóa cột hoặc đổi semantics quá sớm.

### 5.3 Không dùng synchronized trong JVM làm khóa migration

Một static synchronized method chỉ đồng bộ thread trong cùng một classloader/process. Nó không bảo vệ database khi có nhiều JVM, pod hoặc host cùng chạy migration.

Dùng database lock, migration tool lock hoặc distributed coordination phù hợp. Khóa phải được quản lý ở phạm vi tất cả instance có thể truy cập database.

## 6. Khởi tạo dữ liệu: seed phải an toàn khi chạy lặp

Seed data là dữ liệu được tạo ban đầu để ứng dụng hoạt động, ví dụ:

- Danh sách quốc gia, tiền tệ hoặc múi giờ.
- Loại trạng thái đơn hàng.
- Quyền mặc định và role hệ thống.
- Cấu hình mặc định.
- Tài khoản quản trị ban đầu.

Không phải mọi dữ liệu ban đầu đều có cùng semantics. Dữ liệu tham chiếu ít thay đổi có thể được quản lý như một phần của migration. Dữ liệu người dùng, đơn hàng hoặc trạng thái nghiệp vụ không nên bị reset bởi startup script.

### 6.1 INSERT không có kiểm soát có thể tạo dữ liệu trùng

Ví dụ:

~~~sql
INSERT INTO order_status(code, label)
VALUES ('PENDING', 'Pending');
~~~

Nếu câu lệnh được chạy mỗi lần bootstrap, nó có thể:

- Báo lỗi duplicate key.
- Tạo bản ghi trùng nếu không có unique constraint.
- Làm migration thất bại.
- Khiến startup hoặc restore không hoàn tất.

Cần xác định một khóa duy nhất có ý nghĩa nghiệp vụ, chẳng hạn code, và đặt unique constraint ở database. Không chỉ kiểm tra trước bằng SELECT trong Java vì hai instance có thể cùng đọc thấy chưa tồn tại rồi cùng INSERT.

### 6.2 Seed idempotent với unique key

Với PostgreSQL, có thể dùng INSERT ... ON CONFLICT:

~~~sql
INSERT INTO order_status(code, label)
VALUES
    ('PENDING', 'Pending'),
    ('PAID', 'Paid'),
    ('CANCELLED', 'Cancelled')
ON CONFLICT (code) DO NOTHING;
~~~

Unique constraint trên code khiến các lần chạy lặp không tạo bản ghi trùng. Nếu dữ liệu đã tồn tại, câu lệnh bỏ qua bản ghi đó.

Nếu seed cần cập nhật các cột do hệ thống sở hữu, có thể dùng DO UPDATE:

~~~sql
INSERT INTO order_status(code, label)
VALUES ('PENDING', 'Pending')
ON CONFLICT (code)
DO UPDATE SET label = EXCLUDED.label;
~~~

Chỉ cập nhật các cột mà seed có quyền quản lý. Nếu người vận hành hoặc người dùng được phép sửa label, một upsert ghi đè mọi lần khởi động có thể làm mất thay đổi hợp lệ.

Cú pháp upsert khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Hãy dùng cú pháp và semantics của database thực tế.

### 6.3 Phân biệt reference data và mutable data

| Loại dữ liệu | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Reference data do ứng dụng sở hữu | Mã trạng thái, loại tiền tệ | Migration có phiên bản hoặc seed idempotent |
| Default configuration | Ngưỡng mặc định, feature mặc định | Insert nếu chưa có; tránh ghi đè giá trị đã được vận hành tùy chỉnh |
| Bootstrap identity | Tài khoản quản trị đầu tiên | Tạo một lần có kiểm soát, dùng unique identity và quy trình bảo mật |
| User data | Hồ sơ người dùng | Không seed lại hoặc reset trong restore |
| Business data | Đơn hàng, giao dịch, lịch sử | Được quản lý bởi nghiệp vụ và transaction |
| Runtime cache | Cache có thể rebuild | Tái tạo theo lifecycle, không coi là seed database |

Một seed script nên biết rõ nó sở hữu dữ liệu nào. Không nên dùng một lệnh UPDATE rộng để đưa toàn bộ bảng về giá trị mặc định mỗi lần khởi động.

## 7. Không chạy lại DDL hoặc seed trong afterRestore

afterRestore được dùng để phục hồi resource của tiến trình. Đối với database, công việc thường là:

1. Tạo lại DataSource hoặc connection pool nếu pool cũ đã được đóng trước checkpoint.
2. Kiểm tra khả năng kết nối.
3. Xác minh database user và quyền cần thiết.
4. Kiểm tra schema version có tương thích với ứng dụng.
5. Khôi phục consumer, scheduler hoặc các hoạt động phụ thuộc database.
6. Bật readiness sau khi các dependency thiết yếu đã sẵn sàng.

Ví dụ Resource chỉ quản lý pool:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabasePoolResource implements Resource {

    private final DatabasePoolFactory poolFactory;
    private DatabasePool pool;

    public DatabasePoolResource(DatabasePoolFactory poolFactory) {
        this.poolFactory = poolFactory;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (pool != null) {
            pool.close();
            pool = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        DatabasePool reopened = poolFactory.create();
        reopened.validateConnection();
        pool = reopened;
    }
}
~~~

DatabasePool và DatabasePoolFactory trong ví dụ là abstraction của ứng dụng. Có thể thay bằng HikariDataSource hoặc pool mà framework đang sử dụng.

Callback không gọi flyway.migrate(), liquibase.update() hoặc hàm seed. Nó chỉ tạo lại resource kết nối. Nếu schema validation là một phần bắt buộc của readiness, có thể gọi một thao tác kiểm tra chỉ đọc, với timeout và quyền phù hợp.

Nếu tạo pool thất bại, callback phải truyền exception để CRaC biết restore chưa hoàn tất. Không gán readiness true trước khi kết nối và xác minh thành công.

### 7.1 Tránh gọi lại toàn bộ application bootstrap

Không nên viết:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context) {
    applicationBootstrap.initializeEverything();
}
~~~

Tên initializeEverything() không cho biết nó làm gì. Nếu bên trong có migration, seed, tạo tài khoản, ghi cấu hình mặc định hoặc đăng ký side effect, những thao tác đó có thể chạy lại.

Thay vào đó, tách các phương thức cụ thể:

~~~java
@Override
public void afterRestore(Context<? extends Resource> context)
        throws Exception {
    databaseConnections.reopen();
    databaseConnections.validate();
    messageClients.reconnect();
    readiness.markReady();
}
~~~

Việc tách tên và trách nhiệm giúp review code dễ dàng hơn và giảm nguy cơ callback vô tình thực hiện thay đổi database.

## 8. Spring Boot: kiểm soát SQL initialization và Hibernate DDL

Spring Boot có thể chạy một số thao tác database trong quá trình khởi tạo ApplicationContext. Cần hiểu các cấu hình này để không nhầm startup mới với restore.

### 8.1 Hibernate schema generation

Thuộc tính **spring.jpa.hibernate.ddl-auto** điều khiển cách Hibernate xử lý schema trong quá trình tạo SessionFactory/EntityManagerFactory.

Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| none | Không tự động quản lý schema |
| validate | Kiểm tra schema tương thích với mapping |
| update | Cố gắng điều chỉnh schema theo entity |
| create | Tạo schema khi khởi tạo |
| create-drop | Tạo schema khi khởi tạo và xóa khi đóng SessionFactory |

Trong production, nên quản lý schema bằng Flyway hoặc Liquibase và dùng validate hoặc none tùy chính sách. Tránh create hoặc create-drop trên database chứa dữ liệu cần giữ. update cũng không thay thế một migration có phiên bản và có thể tạo thay đổi khó kiểm soát.

Nếu application context không bị tạo lại trong restore, Hibernate startup action không tự chạy lại. Nhưng nếu ứng dụng chủ động đóng rồi tạo lại context hoặc EntityManagerFactory trong callback, các cấu hình này sẽ được áp dụng lại.

### 8.2 Spring SQL initialization

Spring Boot có thể thực thi schema.sql và data.sql khi application context khởi động, tùy cấu hình và loại database.

Các thuộc tính liên quan gồm:

- spring.sql.init.mode
- spring.sql.init.schema-locations
- spring.sql.init.data-locations
- spring.sql.init.continue-on-error

Nếu dùng các script này cho dữ liệu khởi tạo, hãy xác định chính xác khi nào chúng chạy. Trong một quy trình restore CRaC bình thường, application context đã nằm trong ảnh và không tự được khởi động lại. Nhưng nếu context hoặc datasource initializer được tạo lại bởi code ứng dụng, script có thể chạy lại.

Không bật continue-on-error để che giấu lỗi duplicate key hoặc lỗi schema. Điều đó có thể khiến ứng dụng chuyển sang trạng thái sẵn sàng dù initialization chỉ hoàn tất một phần.

### 8.3 Flyway hoặc Liquibase cùng Hibernate

Một cấu hình thường gặp là để migration tool sở hữu schema và Hibernate chỉ validate:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Cấu hình cụ thể phụ thuộc phiên bản Spring Boot, database và cách deployment. Có thể tắt Flyway trong application runtime nếu migration được chạy bởi job riêng:

~~~properties
spring.flyway.enabled=false
spring.jpa.hibernate.ddl-auto=validate
~~~

Nếu dùng migration job, application cần xác minh schema version phù hợp trước khi nhận traffic. Đừng tắt validation mà không có một bước kiểm tra thay thế.

### 8.4 ApplicationReadyEvent không phải afterRestore

ApplicationReadyEvent thuộc lifecycle startup của Spring Boot. Nó được phát khi application context hoàn tất startup. CRaC restore không tự khởi chạy lại toàn bộ Spring startup lifecycle như một process mới.

Nếu cần xử lý sau restore, hãy dùng Resource callback hoặc integration CRaC của framework. Không đặt migration hoặc seed trong một callback được gọi lại sau restore chỉ vì muốn “chạy lại startup”.

## 9. Liquibase và Flyway: các cấu hình dễ khiến script chạy lại

Migration tool có cơ chế lịch sử, nhưng chính changelog hoặc script vẫn có thể được thiết kế để chạy lại.

### 9.1 Liquibase runAlways

Một changeSet có runAlways=true sẽ được chạy mỗi lần Liquibase update được gọi, kể cả khi changeSet đã được ghi nhận trước đó.

Không dùng runAlways cho các thao tác không idempotent như:

- INSERT một tài khoản mới mà không có unique key.
- Reset số dư hoặc trạng thái nghiệp vụ.
- DELETE toàn bộ bảng rồi INSERT lại.
- Tạo dữ liệu test hoặc dữ liệu mẫu trên production.
- Tăng counter mỗi lần startup.

Nếu một thao tác thật sự cần chạy mỗi lần, hãy bảo đảm nó an toàn khi lặp và có phạm vi dữ liệu rõ ràng.

### 9.2 Liquibase runOnChange

runOnChange=true cho phép changeSet chạy lại khi checksum thay đổi. Nó phù hợp với một số object có thể được thay thế như view hoặc stored procedure, tùy thiết kế.

Không dùng nó cho migration thay đổi dữ liệu một lần nếu việc chạy lại có thể ghi đè dữ liệu người dùng. Với thay đổi schema hoặc data migration có lịch sử, thường nên tạo changeSet mới.

### 9.3 Flyway repeatable migration

Flyway hỗ trợ repeatable migration, thường dùng tiền tố R__, và thực hiện lại khi checksum thay đổi. Đây là cơ chế hữu ích cho view, procedure hoặc object có thể cập nhật theo định nghĩa mới.

Nếu repeatable migration chứa dữ liệu hoặc side effect, hãy kiểm soát tính lặp. Việc sửa file repeatable migration có thể khiến nó được thực thi lại ở lần migrate tiếp theo.

### 9.4 Migration đã phát hành cần bất biến

Không chỉnh sửa migration versioned đã chạy trên môi trường dùng chung để “sửa nhanh” lịch sử. Checksum validation có thể báo lỗi và database khác nhau có thể đã chạy các nội dung khác nhau.

Tạo migration mới để sửa schema hoặc dữ liệu. Điều này giữ lịch sử có thể kiểm toán và giúp các môi trường tiến tới cùng một trạng thái.

## 10. Database vẫn thay đổi trong khi image đang được giữ

Checkpoint image lưu trạng thái tiến trình Java. Nó không đóng băng database server và không lưu snapshot nhất quán của toàn bộ dữ liệu database.

Giả sử:

1. Phiên bản ứng dụng A kết nối database schema version 10.
2. A được warm-up và checkpoint.
3. Database được migration lên version 11.
4. Nhiều instance được restore từ image A.
5. Các instance A tiếp tục chạy với code được build cho schema version 10.

Nếu migration version 11 xóa cột mà code A vẫn cần, các instance restore sẽ lỗi dù checkpoint thành công.

Đây là vấn đề tương thích phiên bản giữa application image và schema database. Cần quản lý theo chiến lược expand/contract.

### 10.1 Expand/contract migration

Một trình tự an toàn thường là:

**Expand**

- Thêm cột hoặc bảng mới.
- Giữ các cột cũ để code cũ tiếp tục hoạt động.
- Nếu cần, dual-write hoặc backfill dữ liệu.
- Triển khai code mới có thể đọc schema cũ và mới.

**Migrate application and data**

- Chuyển traffic sang code mới.
- Backfill hoặc chuyển dữ liệu theo batch.
- Xác minh không còn instance dùng cấu trúc cũ.

**Contract**

- Chỉ sau khi mọi instance và checkpoint image cũ không còn được dùng, mới xóa cột, bảng hoặc index cũ.
- Tạo migration riêng cho bước loại bỏ.
- Hủy hoặc đánh dấu image cũ hết hạn để không restore nhầm.

~~~mermaid
flowchart TD
    A["Schema v10 + App A"] --> B["Expand: thêm cấu trúc tương thích"]
    B --> C["Schema v10/v11 tương thích"]
    C --> D["Deploy App B và backfill"]
    D --> E["Xác minh không còn App A/image cũ"]
    E --> F["Contract: xóa cấu trúc cũ"]
    F --> G["Schema v11"]
~~~

Checkpoint image có thể tồn tại lâu hơn một lần rollout. Vì vậy, cần quản lý tuổi thọ image và schema compatibility cùng nhau. Không chỉ kiểm tra các pod đang chạy; phải biết còn image nào có thể được restore từ cache hoặc kho lưu trữ.

### 10.2 Lưu schema version trong image metadata

Có thể ghi nhận application version và schema compatibility range cùng checkpoint image:

~~~json
{
  "applicationVersion": "2.4.0",
  "checkpointId": "image-2026-11-13-001",
  "schemaMinVersion": 10,
  "schemaMaxVersion": 11
}
~~~

Đây là metadata do hệ thống deployment định nghĩa, không phải định dạng bắt buộc của CRaC. Controller có thể dùng nó để từ chối restore nếu schema hiện tại nằm ngoài phạm vi mà ứng dụng hỗ trợ.

Không nên chỉ lưu schema version trong một static field rồi tin rằng nó luôn chính xác. Cần đối chiếu với trạng thái database thực tế hoặc migration history sau khi reconnect.

## 11. Transaction và dữ liệu đang thay đổi

Không nên checkpoint khi ứng dụng còn transaction database chưa được xử lý. Connection và transaction state thuộc database server, không được đảm bảo khôi phục chỉ vì object JDBC còn trong heap.

Trước checkpoint:

- Ngừng nhận công việc mới.
- Chờ request và transaction đang chạy hoàn tất.
- Commit hoặc rollback theo logic nghiệp vụ.
- Trả connection về pool hoặc đóng pool theo lifecycle.
- Lưu offset/message acknowledgment nếu ứng dụng xử lý message.
- Không giữ một transaction mở qua khoảng thời gian checkpoint.

Sau restore, tạo connection mới và bắt đầu transaction mới. Nếu một nghiệp vụ được thực hiện dở trước checkpoint, hãy dùng cơ chế idempotency hoặc trạng thái workflow để tiếp tục an toàn.

Ví dụ, nếu một đơn hàng được tạo ở database nhưng message xác nhận chưa được gửi, callback reconnect không thể biết chắc message đã được broker nhận hay chưa. Outbox pattern, idempotent consumer hoặc transaction boundary rõ ràng sẽ giúp xử lý tình huống này.

## 12. Xử lý seed và bootstrap có side effect

Một số khởi tạo không chỉ ghi vào database mà còn gọi dịch vụ khác:

- Tạo user mặc định.
- Cấp API key.
- Đăng ký webhook.
- Tạo bucket hoặc queue.
- Gửi email welcome.
- Tạo subscription hoặc lịch chạy định kỳ.

Nếu bootstrap được gọi lại sau restore, side effect có thể lặp ngay cả khi database insert đã được bảo vệ bằng unique key.

### 12.1 Dùng khóa nghiệp vụ và trạng thái hoàn tất

Với một bước bootstrap chỉ được thực hiện một lần, có thể lưu marker có khóa duy nhất:

~~~sql
CREATE TABLE bootstrap_step (
    step_key VARCHAR(100) PRIMARY KEY,
    completed_at TIMESTAMP NOT NULL
);
~~~

Trước khi thực hiện side effect, hệ thống cần phối hợp marker với thao tác nghiệp vụ một cách an toàn. Một SELECT kiểm tra marker rồi gọi API bên ngoài vẫn có race condition nếu hai instance cùng chạy.

Có thể dùng transaction và lock ở database để dành quyền thực hiện, nhưng không thể tạo một transaction ACID chung với mọi HTTP API bên ngoài. Với side effect từ xa, nên dùng idempotency key mà dịch vụ đích hỗ trợ hoặc outbox/retry protocol.

### 12.2 Seed tài khoản quản trị

Không nên tạo lại tài khoản admin với mật khẩu mặc định mỗi lần restore. Nếu bootstrap account là bắt buộc:

- Chỉ tạo khi chưa tồn tại.
- Dùng unique username hoặc identity.
- Lưu password hash theo chính sách bảo mật.
- Không reset mật khẩu của tài khoản đã được quản trị viên thay đổi.
- Ghi nhận bootstrap đã hoàn tất.
- Không in secret vào log hoặc checkpoint metadata.

Nếu cần khôi phục quyền truy cập, hãy dùng quy trình quản trị riêng thay vì tái chạy seed.

### 12.3 Không reset dữ liệu nghiệp vụ

Các câu lệnh như:

~~~sql
TRUNCATE TABLE customer;
DELETE FROM orders;
UPDATE account SET balance = 0;
~~~

không phải thao tác initialization an toàn nếu bảng chứa dữ liệu thực. Không đưa chúng vào callback afterRestore hoặc startup hook chạy trên database production.

Nếu cần tạo lại dữ liệu cache, hãy dùng bảng hoặc namespace riêng có thể rebuild mà không ảnh hưởng dữ liệu nghiệp vụ.

## 13. Kiểm tra database sau restore

Sau khi connection pool được tạo lại, ứng dụng có thể chạy các phép kiểm tra chỉ đọc:

- Kết nối thành công.
- Database user có quyền cần thiết.
- Schema history tồn tại và ở phiên bản được hỗ trợ.
- Các bảng hoặc cột thiết yếu có mặt.
- Một truy vấn health check đơn giản thực hiện thành công.
- Các transaction trước checkpoint đã kết thúc.
- Consumer hoặc scheduler chỉ được khởi động sau khi dependency sẵn sàng.

Không cần chạy migration để thực hiện các kiểm tra này. Có thể dùng một validator đọc metadata schema hoặc truy vấn migration history.

Nếu schema version không tương thích, hãy giữ readiness false và báo lỗi rõ ràng. Không tự động chạy một migration phá vỡ tương thích chỉ để làm cho instance restore được.

## 14. Kiểm thử để phát hiện initialization bị chạy lại

Nên kiểm thử cả lần khởi động mới, checkpoint thành công, restore thành công và checkpoint thất bại.

| Tình huống | Điều cần xác nhận |
|---|---|
| Fresh startup | Migration và seed chạy theo đúng chính sách |
| Chạy migration runner lần hai | Migration cũ không chạy lại; checksum/version được xác thực |
| Checkpoint sau startup | Không có transaction hoặc migration đang dở |
| Restore thành công | Chỉ connection/resource recovery chạy; không có DDL hoặc seed ngoài ý muốn |
| Restore nhiều replica | Không có nhiều tiến trình cùng chạy bootstrap side effect |
| Checkpoint thất bại | Resource được mở lại; database không bị reset hoặc migration chạy lại |
| Database đổi schema trong lúc image tồn tại | Image cũ bị từ chối hoặc vẫn tương thích theo chính sách |
| Seed chạy lặp | Không tạo duplicate và không ghi đè dữ liệu người dùng |
| Connection pool reconnect lỗi | Readiness giữ false; không chạy migration như một cách chữa kết nối |
| Restore từ image cũ | Schema compatibility được xác minh trước khi phục vụ |

Có thể ghi migration version và số lần seed vào log hoặc metric để so sánh trước checkpoint và sau restore. Đối với test, dùng database riêng và dữ liệu có thể xóa. Không kiểm thử các script destructive trên database dùng chung.

## 15. Quy trình triển khai đề xuất

Khi tích hợp CRaC với ứng dụng sử dụng database, có thể áp dụng quy trình sau:

**Bước 1 — Kiểm kê mọi initialization.** Tìm Flyway, Liquibase, Hibernate DDL, schema.sql, data.sql, import.sql, initializer tự viết và script do container chạy.

**Bước 2 — Phân loại thao tác.** Tách migration schema, seed reference data, bootstrap identity, validation và connection recovery thành các thành phần riêng.

**Bước 3 — Quản lý migration có phiên bản.** Dùng schema history và checksum. Không sửa migration đã phát hành; tạo migration mới cho thay đổi tiếp theo.

**Bước 4 — Chọn nơi chạy migration.** Ưu tiên migration job riêng hoặc một startup path có khóa database rõ ràng. Không đặt migration runner trong afterRestore.

**Bước 5 — Làm seed idempotent.** Dùng unique constraint, upsert phù hợp và chỉ cập nhật các cột do hệ thống sở hữu. Tách dữ liệu tham chiếu khỏi dữ liệu người dùng.

**Bước 6 — Tách CRaC Resource.** beforeCheckpoint dừng công việc và đóng pool; afterRestore tạo pool mới, xác minh kết nối và khôi phục client. Không gọi bootstrap tổng thể.

**Bước 7 — Bảo đảm tương thích schema.** Dùng expand/contract và theo dõi các checkpoint image còn có thể restore. Không xóa cấu trúc mà code trong image cũ còn cần.

**Bước 8 — Xử lý transaction và side effect.** Drain request, kết thúc transaction và dùng idempotency/outbox cho các thao tác có thể lặp.

**Bước 9 — Kiểm thử restore nhiều lần.** Xác nhận không có DDL hoặc seed bất ngờ, pool kết nối lại đúng và readiness chỉ bật khi schema tương thích.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và sự phối hợp lifecycle với ứng dụng.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): đăng ký Resource và triển khai beforeCheckpoint/afterRestore.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): SQL initialization, Hibernate và migration tool.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): lifecycle và application events.
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations): versioned và repeatable migrations.
- [Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate): kiểm tra migration history và checksum.
- [Liquibase — Changeset attributes](https://docs.liquibase.com/concepts/changelogs/attributes/home.html): runAlways, runOnChange và các thuộc tính changeSet.
- [Liquibase — Database changelog lock](https://docs.liquibase.com/concepts/basic/databasechangeloglock-table.html): cách Liquibase điều phối thay đổi changelog.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): ON CONFLICT và thao tác insert/upsert.

