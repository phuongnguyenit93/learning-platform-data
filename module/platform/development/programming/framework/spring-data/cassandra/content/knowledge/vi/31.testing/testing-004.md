# CassandraContainer với Testcontainers trong kiểm thử Spring Data Cassandra

**CassandraContainer** của Testcontainers giúp chạy một phiên bản Apache Cassandra thật trong container Docker để kiểm thử tích hợp các thành phần của **Spring Data Cassandra**: entity mapping, `CassandraRepository`, `CassandraTemplate`, câu lệnh CQL và cách driver kết nối tới keyspace. Bài học thuộc chương **Kiểm thử** của module `SPRING_DATA_CASSANDRA`, tập trung vào cách viết bài test có thể lặp lại và phát hiện lỗi mà mock repository thường bỏ sót.

Một test dùng Cassandra thật có thể kiểm chứng cấu trúc bảng dựa trên nhu cầu truy vấn, partition key, cột clustering, kiểu dữ liệu, câu CQL và một số thiết lập đọc/ghi. Tuy nhiên, một container Cassandra đơn lẻ không mô phỏng đầy đủ cluster phân tán nhiều node: nó không thay thế các phép thử về replication, mất node, consistency level giữa các replica, paging ở quy mô lớn hay hiệu năng thực tế.

## 1. Khi nào dùng CassandraContainer?

Giả sử ứng dụng quản lý tài khoản khách hàng có bảng Cassandra `accounts_by_id`. Unit test mock `AccountRepository` có thể xác nhận service gọi `save()`, nhưng không phát hiện một entity mapping sai tên cột, một bảng chưa tồn tại hoặc cấu hình driver chọn nhầm datacenter. Testcontainers cho phép test chạy qua chuỗi thực tế:

~~~mermaid
flowchart LR
    J["JUnit 5 / Spring Boot Test"] --> S["Service / Repository / CassandraTemplate"]
    S --> D["Spring Data Cassandra"]
    D --> C["Cassandra Java Driver"]
    C --> T["CassandraContainer (Docker)"]
    T --> K["Keyspace + bảng CQL"]
~~~

| Kiểu kiểm thử | Mục đích | Có dùng Cassandra thật? |
| --- | --- | --- |
| Unit test với mock | Kiểm tra rẽ nhánh, xử lý lỗi, tương tác giữa các lớp | Không |
| Integration test với `CassandraContainer` | Kiểm tra kết nối, mapping, schema, CQL và lưu/đọc dữ liệu | Có, thường một node |
| Test trên cluster gần production | Kiểm tra replication, failover, topology, consistency và tải thực tế | Có, nhiều node |

Ví dụ những lỗi mà integration test có thể bắt: annotation `@PrimaryKey` dùng sai tên cột; repository query không khớp partition key; dữ liệu Java không chuyển đổi đúng sang CQL type; `INSERT` hợp lệ nhưng `SELECT` thất bại do bảng hoặc điều kiện `WHERE` sai.

## 2. Điều kiện và quản lý phiên bản

Cần có:

- JDK và Spring Boot phù hợp với dự án.
- JUnit Jupiter (JUnit 5), `spring-boot-starter-test` và `spring-boot-starter-data-cassandra`.
- Testcontainers cùng module Cassandra và module JUnit Jupiter.
- Docker Engine hoặc một môi trường container được Testcontainers hỗ trợ, **truy cập được từ tiến trình chạy test**.
- Đủ RAM/CPU cho Cassandra; quá trình khởi động một database nặng hơn các container dịch vụ nhỏ.

**Chú ý khác biệt giữa các nhánh Testcontainers:**

| Nhánh | Module Gradle/Maven | Java import CassandraContainer |
| --- | --- | --- |
| Testcontainers 1.x | `org.testcontainers:cassandra` | `org.testcontainers.containers.CassandraContainer` |
| Testcontainers 2.x | `org.testcontainers:testcontainers-cassandra` | `org.testcontainers.cassandra.CassandraContainer` |

Các đoạn Java đầy đủ dưới đây minh họa **API Testcontainers 1.x**, phù hợp với nhiều dự án Spring Boot 3.x đang sử dụng nhánh này. Nếu dự án đã lên Testcontainers 2.x, đổi dependency/import và kiểm tra chữ ký constructor/API theo phiên bản đã khóa. Không trộn module 1.x với 2.x. Nên sử dụng BOM hoặc dependency management thống nhất, không viết hai phiên bản Testcontainers khác nhau cho module Cassandra và module JUnit.

Ví dụ Gradle Groovy DSL với Spring Boot đang quản lý version dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:cassandra'
}
~~~

Với dự án không dùng BOM quản lý các dependency này, phải khai báo version tương thích cho cả bộ Testcontainers. Nếu sử dụng `@ServiceConnection` ở phần mở rộng bên dưới, thêm `org.springframework.boot:spring-boot-testcontainers`.

Để kết quả ổn định theo thời gian, khóa **phiên bản Cassandra image** đã được xác minh với ứng dụng, ví dụ `cassandra:4.1` cho ví dụ này; trong CI dài hạn, cân nhắc ghim tag bản vá cụ thể hoặc digest đã phê duyệt. Tag chỉ có major/minor có thể đổi nội dung khi nhà phát hành cập nhật image. Hãy dùng phiên bản phù hợp với Cassandra trong production, vì thay đổi CQL, schema và driver có thể khiến test trả kết quả khác nhau giữa các phiên bản.

## 3. Thiết kế schema thử nghiệm dựa trên truy vấn

Giả sử yêu cầu là: lấy số dư của một tài khoản bằng `account_id`. Bảng tương ứng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_test
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS shop_test.accounts_by_id (
    account_id uuid PRIMARY KEY,
    balance_cents bigint
);
~~~

Ở đây `account_id` là **partition key**. Truy vấn sau phù hợp với cấu trúc bảng:

~~~sql
SELECT account_id, balance_cents
FROM shop_test.accounts_by_id
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Đây là schema tối thiểu để minh họa phép thử, không phải một thiết kế thanh toán thực tế. Mỗi account có một partition theo ID. Chúng ta không cần `ALLOW FILTERING` để đọc theo key; `SimpleStrategy` với replication factor 1 chỉ phù hợp cho môi trường một node trong ví dụ. Môi trường production nhiều datacenter thường cần chiến lược replication phù hợp như `NetworkTopologyStrategy`.

Lưu script trên tại **`src/test/resources/cassandra/schema.cql`** trong dự án thật. Testcontainers sẽ đọc resource từ classpath để khởi tạo schema. Giữ script test có kiểm soát và nhất quán với migration/schema của ứng dụng; nếu production schema thay đổi, test phải được cập nhật hoặc áp dụng cùng cơ chế migration để tránh lệch hợp đồng dữ liệu.

## 4. Entity và repository mẫu

Một entity Spring Data Cassandra ánh xạ bảng trên:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("accounts_by_id")
public class Account {

    @PrimaryKey("account_id")
    private UUID accountId;

    @Column("balance_cents")
    private Long balanceCents;

    public Account() {
    }

    public Account(UUID accountId, Long balanceCents) {
        this.accountId = accountId;
        this.balanceCents = balanceCents;
    }

    public UUID getAccountId() {
        return accountId;
    }

    public void setAccountId(UUID accountId) {
        this.accountId = accountId;
    }

    public Long getBalanceCents() {
        return balanceCents;
    }

    public void setBalanceCents(Long balanceCents) {
        this.balanceCents = balanceCents;
    }
}
~~~

Repository tương ứng:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface AccountRepository
        extends CassandraRepository<Account, UUID> {
}
~~~

Sử dụng `Long` thay vì `double` cho số tiền quy về đơn vị nhỏ nhất giúp tránh lỗi biểu diễn số thực. Trong ứng dụng thật còn cần quy tắc cập nhật số dư nhất quán; test dưới đây chỉ kiểm tra khả năng ánh xạ và đọc/ghi cơ bản.

## 5. Integration test đầy đủ với JUnit 5 và @DynamicPropertySource

Ý tưởng quan trọng nhất là **để Testcontainers cấp host và mapped port lúc runtime**, rồi truyền các giá trị đó vào Spring Boot. Không giả định mọi máy và mọi CI runner đều có Cassandra ở `localhost:9042`.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = {
    "spring.cassandra.schema-action=NONE"
})
class AccountRepositoryIT {

    @Container
    static final CassandraContainer<?> CASSANDRA =
        new CassandraContainer<>(
            DockerImageName.parse("cassandra:4.1")
        ).withInitScript("cassandra/schema.cql");

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points", CASSANDRA::getHost);
        registry.add("spring.cassandra.port",
            () -> CASSANDRA.getMappedPort(9042));
        registry.add("spring.cassandra.local-datacenter",
            CASSANDRA::getLocalDatacenter);
        registry.add("spring.cassandra.keyspace-name",
            () -> "shop_test");
    }

    @Autowired
    AccountRepository repository;

    @Autowired
    CassandraTemplate template;

    @Test
    void saveAndReadAccountThroughRepositoryAndTemplate() {
        UUID id = UUID.randomUUID();

        try {
            repository.save(new Account(id, 12_500L));

            Account fromRepository =
                repository.findById(id).orElseThrow();

            assertThat(fromRepository.getBalanceCents())
                .isEqualTo(12_500L);

            Account fromTemplate =
                template.selectOneById(id, Account.class);

            assertThat(fromTemplate).isNotNull();
            assertThat(fromTemplate.getBalanceCents())
                .isEqualTo(12_500L);
        } finally {
            repository.deleteById(id);
        }

        assertThat(repository.existsById(id)).isFalse();
    }
}
~~~

Lớp `AccountRepositoryIT` và entity/repository phải nằm trong phạm vi Spring Boot có thể tìm thấy, hoặc phải cấu hình scanning/test context phù hợp. Ví dụ dùng `@SpringBootTest` nên tải phần lớn application context; với project lớn có thể dùng test slice hoặc cấu hình context tối thiểu nếu framework/version đang dùng hỗ trợ.

### Vì sao cấu hình như vậy?

- `@Testcontainers`: bật JUnit Jupiter extension của Testcontainers để quản lý lifecycle.
- `@Container static ...`: một container được tạo một lần cho cả test class, thay vì khởi động Cassandra trước mỗi test method. JUnit extension dừng nó sau khi test class kết thúc.
- `withInitScript(...)`: chạy schema từ resource khi container được khởi tạo. Nếu tạo keyspace/bảng thất bại, test sẽ không đạt yêu cầu trước khi thao tác repository.
- `getHost()` và `getMappedPort(9042)`: lấy endpoint truy cập từ JVM của test. Cổng bên ngoài thường là cổng động; `9042` là cổng CQL **bên trong** container.
- `getLocalDatacenter()`: cung cấp tên datacenter mà driver nên dùng cho chính Cassandra container.
- `spring.cassandra.keyspace-name`: chỉ định keyspace có trong script.
- `spring.cassandra.schema-action=NONE`: tránh để Spring tự đổi schema trong test này; schema được tạo chủ động qua CQL script.
- `UUID.randomUUID()`: mỗi test có primary key riêng để hạn chế va chạm dữ liệu. Khối `finally` xóa bản ghi ngay cả khi assertion thất bại, phù hợp khi container được tái sử dụng trong phạm vi test class.

Với Spring Boot 3.x, các cấu hình được dùng ở đây có prefix `spring.cassandra.*`. Nếu dự án dùng nhánh Boot cũ, phải kiểm tra prefix tương ứng trong phiên bản đó. Điều này khác với cấu hình driver thuần và không nên trộn tên property của các thế hệ Spring Boot.

### Về việc kiểm chứng test

Phép thử xác nhận được đường đi entity → repository → CQL → Cassandra và CassandraTemplate → entity. Nếu mapping `account_id` thành tên cột sai, thao tác lưu/đọc sẽ cho thấy lỗi thật thay vì chỉ xác minh mock được gọi. Tuy nhiên, nó **chưa** chứng minh logic nghiệp vụ cập nhật số dư là an toàn dưới concurrent writes.

Đừng viết test chỉ assert `applicationContext` tải thành công rồi xem đó là bằng chứng mapping đúng. Hãy thực hiện một câu đọc/ghi đại diện và assert dữ liệu trả về.

## 6. Biến thể @ServiceConnection với Spring Boot 3.1+

Khi sử dụng Spring Boot hỗ trợ **Testcontainers service connections**, ta có thể dùng `@ServiceConnection` để Spring Boot tự tạo các connection details cần thiết từ CassandraContainer. Điều này làm gọn phần khai báo host, port và cấu hình driver.

Ví dụ biến thể của phần khởi tạo container trong cùng test class:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = {
    "spring.cassandra.keyspace-name=shop_test",
    "spring.cassandra.schema-action=NONE"
})
class AccountRepositoryServiceConnectionIT {

    @Container
    @ServiceConnection
    static final CassandraContainer<?> CASSANDRA =
        new CassandraContainer<>(
            DockerImageName.parse("cassandra:4.1")
        ).withInitScript("cassandra/schema.cql");

    // Tiêm repository và đặt các @Test tương tự ví dụ trước.
}
~~~

Cần có dependency test `spring-boot-testcontainers` và phiên bản Spring Boot hỗ trợ Cassandra connection details. Nếu dùng biến thể này, thông thường **không cần** khai báo lại `@DynamicPropertySource` chỉ để truyền host/port/datacenter. Tuy nhiên, `@ServiceConnection` không tự động tạo schema nghiệp vụ hoặc chọn keyspace thay cho ứng dụng, nên vẫn cần script khởi tạo và `spring.cassandra.keyspace-name` như ví dụ.

Chọn **một** cách cấp connection details nhất quán trong một test class để tránh khó truy nguồn cấu hình. Trong ứng dụng có cấu hình `CqlSession` tùy biến, cần bảo đảm cấu hình đó sử dụng chính endpoint của container.

## 7. Test truy vấn theo partition key và composite primary key

Cassandra khuyến khích **thiết kế bảng theo truy vấn**. Nếu nghiệp vụ cần truy xuất toàn bộ đơn hàng của khách hàng, bảng có thể dùng partition key `customer_id` và clustering column `order_id`:

~~~sql
CREATE TABLE shop_test.orders_by_customer (
    customer_id uuid,
    order_id timeuuid,
    total_cents bigint,
    PRIMARY KEY ((customer_id), order_id)
) WITH CLUSTERING ORDER BY (order_id DESC);
~~~

Với schema này:

~~~sql
SELECT order_id, total_cents
FROM shop_test.orders_by_customer
WHERE customer_id = ?;
~~~

Truy vấn theo `customer_id` được hỗ trợ tự nhiên. Truy vấn toàn bộ đơn hàng chỉ theo `order_id` thì **không** đúng mô hình truy vấn này nếu không có bảng bổ sung hoặc cơ chế index thích hợp. Tách test riêng để kiểm chứng repository/template tạo đúng CQL theo key.

Một test tốt cho composite key nên xác nhận:

1. Entity dùng `@PrimaryKeyClass`, `@PrimaryKeyColumn` và thứ tự `ordinal` đúng như primary key trong schema.
2. Hai order thuộc cùng customer được đọc đúng khi truy vấn theo partition key.
3. Kết quả có thứ tự clustering như yêu cầu khi dùng đúng query.
4. Query không dựa vào `ALLOW FILTERING` để che một thiết kế partition key sai.
5. Khi thêm cột cần đọc, phép chuyển đổi kiểu dữ liệu trong entity vẫn khớp schema.

Lưu ý: `order_id timeuuid` phù hợp nếu cần định danh mang thông tin thời gian và muốn sắp xếp theo thời gian. Một `UUID.randomUUID()` thông thường sinh UUID version 4, **không thể dùng thay thế một giá trị timeuuid version 1**. Trong test, hãy tạo giá trị `timeuuid` bằng API phù hợp hoặc chọn loại `uuid` trong schema nếu nhu cầu không đòi hỏi timeuuid.

## 8. Dữ liệu test, isolation và thứ tự thực thi

Nếu các test dùng chung container và keyspace, tránh dựa vào thứ tự chạy giữa các phương thức. Các kỹ thuật phổ biến:

| Chiến lược | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- |
| UUID mới cho mỗi case | Đơn giản, ít xung đột giữa test chạy song song | Phải dọn dữ liệu hoặc dùng container ngắn hạn |
| Dọn các row theo primary key trong `finally` / `@AfterEach` | Không ảnh hưởng dữ liệu của test khác | Phải lưu lại key đã tạo |
| `TRUNCATE` bảng trước/sau test | Đảm bảo bảng sạch ở bài test tuần tự | Dễ phá dữ liệu của test chạy song song; chi phí cao |
| Container/keyspace riêng theo nhóm test | Cách ly mạnh | Tốn thời gian và tài nguyên |
| Reuse container giữa nhiều test class | Giảm khởi động lặp lại | Dữ liệu có thể sót giữa các lớp; phải quản lý isolation |

Trong ví dụ chính, mỗi test dùng UUID riêng và xóa row trong `finally`. Với tập test chạy song song và nhiều nhóm bảng, một keyspace riêng theo suite hoặc container riêng theo nhóm có thể đáng tin cậy hơn `TRUNCATE` toàn bộ.

**Cassandra không hỗ trợ transaction rollback theo cách mà các test Spring trên RDBMS thường dựa vào.** Vì vậy, thêm `@Transactional` không có nghĩa mọi ghi CQL được tự động rollback khi test kết thúc. Phải chủ động thiết kế dữ liệu test độc lập và có chiến lược cleanup.

Cũng cần nhớ rằng `@Container static` được JUnit quản lý **trên phạm vi một test class**, còn Spring có cơ chế cache application context giữa các test class. Nếu context được tái sử dụng sau khi container cũ đã dừng nhưng connection details vẫn trỏ tới mapped port cũ, test có thể thất bại khó hiểu. Giữ lifecycle của container và lifecycle của context tương thích; khi cần dùng chung container cho nhiều class, quản lý container ở một phạm vi ổn định hoặc điều chỉnh context caching có chủ đích.

## 9. Kiểm thử paging, consistency và giới hạn của container một node

### Paging

Cassandra phân trang dựa trên paging state của driver, không hoạt động giống phân trang SQL dựa vào `OFFSET`. Khi kiểm thử, nên tạo đủ dữ liệu trong một partition phù hợp, cấu hình page size nhỏ và duyệt qua nhiều trang, sau đó kiểm chứng **tập ID đã đọc, thứ tự và không bị lặp/mất row**.

Ví dụ kế hoạch test:

- Tạo 23 row vào cùng một partition, với clustering key xác định.
- Đọc theo thứ tự clustering với page size 10.
- Duyệt tiếp bằng cơ chế paging phù hợp của Spring Data Cassandra/Java Driver đang dùng.
- Assert nhận đủ 23 row, không trùng lặp, đúng thứ tự.

Tránh giả định mọi repository đều trả kiểu `Page` với tổng số dòng và offset như Spring Data JPA. Tùy API Spring Data Cassandra, ta có thể nhận `Slice` hoặc sử dụng paging state của driver. Nếu test đồng thời có ghi/xóa dữ liệu, kết quả các trang có thể thay đổi theo thời gian; để test có tính quyết định, nên cố định dữ liệu trong suốt quá trình duyệt.

### Consistency

Trong script một node dùng replication factor 1, các mức như `ONE` và `LOCAL_QUORUM` không chứng minh hành vi của cluster nhiều replica. Integration test một node giúp xác nhận driver phát được câu lệnh với một consistency level hợp lệ, nhưng không kiểm chứng được:

- Read/write consistency khi một replica bị chậm hoặc mất mạng.
- Chuyển coordinator, failover hoặc quyết định routing giữa nhiều node.
- Phân phối partition, tác động của replication factor lớn hơn 1.
- Độ trễ, throughput hoặc cân bằng tải của cluster production.

Muốn đánh giá các đặc điểm đó, cần môi trường test nhiều node được cấu hình topology, keyspace replication và mạng phù hợp; mô hình cluster đó nằm ngoài phạm vi một `CassandraContainer` đơn lẻ.

### Hiệu năng

Không dùng thời gian của một test Testcontainers để kết luận latency production vì startup Docker, máy CI, số node và storage khác môi trường thật. Nên tách **thời gian khởi động container** khỏi thời gian query khi đo; nếu muốn đánh giá paging hoặc hot partition, cần benchmark có warmup, lượng dữ liệu và topology đại diện.

## 10. Những lỗi thường gặp

| Lỗi / triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Testcontainers báo không tìm được Docker environment | Docker chưa chạy, runner không cấp runtime, permission/socket không khả dụng | Xác nhận Docker từ chính tiến trình chạy test và cấu hình CI |
| Cassandra startup timeout | Image cần thêm thời gian, host thiếu RAM/CPU, init CQL lỗi | Xem container logs, tài nguyên và script; điều chỉnh thời hạn khởi động nếu thực sự cần |
| `AllNodesFailedException` / connection refused | Hard-code `localhost:9042`, sai mapped port, container đã dừng | Dùng `getHost()`/`getMappedPort(9042)`, kiểm tra lifecycle |
| `NoNodeAvailableException` hoặc lỗi chọn node | Contact point, DNS, local datacenter không khớp | Lấy datacenter từ container và kiểm tra driver |
| Keyspace/table không tồn tại | Chưa chạy init script hoặc file không nằm trên test classpath | Kiểm tra đường dẫn `src/test/resources`, nội dung và log khởi tạo |
| Mapping exception khi đọc dữ liệu | Tên cột, type, primary key annotation sai | Đối chiếu entity với CQL schema thật |
| Test chạy riêng đạt nhưng chạy cùng suite thất bại | Dữ liệu dùng chung, `TRUNCATE` cạnh tranh, container/context cache khác lifecycle | Dùng key riêng, cleanup theo key, thống nhất cách chia sẻ container |
| Test rất chậm | Mỗi test method/class mở container mới không cần thiết | Dùng `static @Container` theo class, tổ chức suite hợp lý |

Nếu test thất bại khi dùng `withInitScript()`, hãy đọc **nguyên nhân lỗi khởi tạo CQL** thay vì chỉ đọc stack trace repository. Một dấu chấm phẩy bị thiếu, sai tên keyspace hoặc kiểu dữ liệu không hợp lệ trong script có thể khiến toàn bộ integration test chưa sẵn sàng.

Khi chẩn đoán kết nối, nên xác định ranh giới lỗi: Docker startup → container ready → kết nối TCP/CQL → chọn datacenter → khởi tạo keyspace/schema → repository query. Thứ tự này giúp phân biệt lỗi test environment với lỗi mapping hay truy vấn nghiệp vụ.

## 11. Tích hợp CI và tối ưu thời gian chạy

Một pipeline CI có kiểm thử Cassandra thực thường cần:

1. Docker hoặc runtime container mà Testcontainers hỗ trợ.
2. Khả năng kéo image Cassandra từ registry cho phép.
3. CPU, RAM và timeout đủ cho quá trình Cassandra bootstrap.
4. Test task chạy integration tests sau khi mã và dependencies được build.
5. Báo cáo JUnit và container logs khi test lỗi.

Có thể tách test nhanh và test tích hợp theo convention của dự án, ví dụ tên lớp kết thúc bằng `IT`. **Tên `IT` tự nó không đảm bảo Gradle/Maven sẽ chạy hay bỏ qua class đó**; cần cấu hình test task hoặc plugin phù hợp. Trong Maven có thể dùng cơ chế Surefire/Failsafe tùy quy ước; trong Gradle có thể tạo test suite/task integration test.

Không bật `withReuse(true)` một cách tùy tiện trong CI: container tái sử dụng giữa các lần chạy có thể giữ lại dữ liệu và làm test phụ thuộc trạng thái trước đó. Việc reuse có thể hữu ích cho máy phát triển khi được cấu hình có chủ đích, nhưng CI nên ưu tiên môi trường lặp lại được và dễ truy vết.

Nếu muốn giảm thời gian, tối ưu bằng cách nhóm các case liên quan vào một test class với container static, tái sử dụng cấu hình Spring hợp lý, và giữ test data nhỏ. Không cần khởi động Cassandra để kiểm tra một phép biến đổi Java thuần túy có thể test bằng unit test.

## 12. Bài tập áp dụng

### Bài tập 1 — Xác định lỗi môi trường

Một test sử dụng `new CassandraContainer<>("cassandra:4.1")` chạy trên laptop nhưng CI báo connection refused ở `localhost:9042`. CI đã khởi động container thành công.

**Gợi ý đáp án:** Test đang dùng cổng mặc định của host thay vì mapped port do Testcontainers cấp. Lấy host từ `getHost()`, cổng từ `getMappedPort(9042)` và truyền vào Spring Boot bằng `@DynamicPropertySource` hoặc dùng `@ServiceConnection` nếu phiên bản hỗ trợ.

### Bài tập 2 — Kiểm tra thiết kế theo truy vấn

Bảng `orders_by_customer` có primary key `((customer_id), order_id)`. Repository chỉ truyền `order_id` vào điều kiện `WHERE`, rồi yêu cầu `ALLOW FILTERING` để query chạy.

**Gợi ý đáp án:** Kiểm tra lại yêu cầu truy vấn và thiết kế bảng. Query theo `customer_id` phù hợp với partition key hiện có; nếu nghiệp vụ thực sự cần tra cứu theo `order_id`, có thể cần một bảng denormalized khác được tổ chức theo `order_id`, được cập nhật theo chiến lược nhất quán của ứng dụng. Testcontainers sẽ giúp phát hiện câu CQL không phù hợp nhưng không thay người thiết kế quyết định mô hình bảng.

### Bài tập 3 — Dữ liệu test bị rò rỉ

Hai test cùng `TRUNCATE shop_test.accounts_by_id` trong `@BeforeEach` và chạy song song. Một test đôi khi không tìm thấy row vừa ghi.

**Gợi ý đáp án:** Test này có thể xóa dữ liệu của test kia. Dùng ID độc lập, cleanup theo primary key hoặc tách keyspace/container theo nhóm. Không giả định `@Transactional` sẽ rollback mọi thao tác CQL.

### Bài tập 4 — Kết quả consistency

Integration test một container với RF=1 đạt khi đọc bằng consistency `LOCAL_QUORUM`. Nhóm phát triển muốn từ đó kết luận hệ thống vẫn đọc chính xác khi một node trong cụm 3 replica bị hỏng.

**Gợi ý đáp án:** Kết luận không hợp lệ. RF=1 trong một node không tạo kịch bản quorum của ba replica. Cần thử trên cluster nhiều node, với replication strategy, consistency level và fault injection phản ánh mục tiêu kiểm thử.

## 13. Checklist trước khi coi integration test đủ tin cậy

- [ ] Phiên bản Testcontainers, Cassandra image, Spring Boot và Java Driver tương thích; dependency/import thống nhất.
- [ ] Docker và tài nguyên đủ để Cassandra khởi động trong môi trường local và CI.
- [ ] Chỉ dùng host/port do container cung cấp, không hard-code cổng publish.
- [ ] Cấu hình local datacenter, keyspace và schema khớp Cassandra đang chạy.
- [ ] Schema CQL được khởi tạo có kiểm soát và đại diện cho schema ứng dụng.
- [ ] Test thực sự lưu, đọc và assert dữ liệu bằng repository hoặc `CassandraTemplate`.
- [ ] Test có dữ liệu độc lập, cleanup rõ ràng, không phụ thuộc thứ tự.
- [ ] Test query đúng partition key; paging và consistency được hiểu trong giới hạn một node.
- [ ] Lifecycle Spring context và CassandraContainer không gây stale connection giữa test class.
- [ ] CI thu thập đủ log khi container hoặc CQL init thất bại.

**Ghi nhớ:** Giá trị của `CassandraContainer` là đưa Cassandra thật vào vòng kiểm thử Spring Data Cassandra một cách có thể lặp lại. Hãy bắt đầu từ một schema được thiết kế theo truy vấn, để Testcontainers cung cấp endpoint lúc runtime, thực hiện thao tác repository/template có assertion và làm sạch dữ liệu test. Khi cần chứng minh khả năng chịu lỗi hay tính nhất quán của hệ phân tán, phải chuyển sang môi trường kiểm thử nhiều node phù hợp.

