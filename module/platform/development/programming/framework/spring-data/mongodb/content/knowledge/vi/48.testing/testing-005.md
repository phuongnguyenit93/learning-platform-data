# Replica set trong test transaction và change stream

## 1. Vì sao kiểm thử MongoDB đôi khi bắt buộc cần replica set?

Khi dùng **Spring Data MongoDB** để ánh xạ document và thao tác qua **MongoRepository**, **MongoTemplate**, **ReactiveMongoRepository** hay **ReactiveMongoTemplate**, các phép thử CRUD đơn giản có thể chạy với một MongoDB standalone. Tuy nhiên, hai nhóm tính năng quan trọng phụ thuộc vào hạ tầng replica set:

- **Multi-document transaction**: một nhóm thao tác có thể được commit hoặc rollback như một đơn vị logic. Giao dịch MongoDB yêu cầu môi trường hỗ trợ transaction, chẳng hạn **replica set** hoặc **sharded cluster** tương thích.
- **Change stream**: ứng dụng lắng nghe các thay đổi đã được ghi nhận trên collection, database hoặc deployment. Change stream sử dụng cơ chế theo dõi thay đổi dựa trên **oplog** của replica set, hoặc hạ tầng tương ứng khi kết nối qua **mongos** trong sharded cluster.

Vì vậy, một bài test repository lưu được một document trên MongoDB standalone **không chứng minh** rằng nghiệp vụ dùng transaction hoặc change stream hoạt động. Nếu chạy hai tính năng trên standalone, ứng dụng thường nhận lỗi từ server. Bật **@Transactional**, thêm dependency Reactor hoặc sửa cấu hình retry của driver không thể tự biến standalone thành replica set.

Trong chương **Kiểm thử** của module **SPRING_DATA_MONGODB**, chúng ta cần biết cách dựng replica set cho môi trường kiểm thử, điều khiển transaction từ Spring, chủ động tạo change event và kiểm chứng kết quả thực tế.

### Kết quả mong đợi sau bài học

1. Giải thích vì sao transaction và change stream cần topology phù hợp.
2. Phân biệt **single-node replica set cho integration test** với **replica set nhiều node để kiểm thử chịu lỗi**.
3. Tạo replica set tự động bằng Testcontainers, cung cấp URI cho Spring Data MongoDB.
4. Viết test chứng minh **commit** và **rollback** của transaction.
5. Viết test lắng nghe sự kiện **insert** qua change stream mà không làm rơi sự kiện do đăng ký quá muộn.
6. Nhận biết các lỗi cấu hình, timeout, race condition và giới hạn của môi trường thử nghiệm.

## 2. Topology, oplog và cơ chế hoạt động

MongoDB thường xuất hiện trong các mô hình sau:

| Môi trường | Transaction nhiều document | Change stream | Dùng để kiểm thử gì? |
| --- | --- | --- | --- |
| **Standalone mongod** | Không hỗ trợ transaction theo mô hình này | Không hỗ trợ | CRUD đơn giản, một số thao tác mapping |
| **Single-node replica set** | Có, khi MongoDB/driver hỗ trợ | Có | Test transaction và change stream chức năng cơ bản |
| **Replica set nhiều thành viên** | Có | Có | Thử chuyển primary, majority write, replica lag, lỗi mạng |
| **Sharded cluster** | Có, theo tính năng và phiên bản được hỗ trợ | Có, thường qua mongos | Transaction nhiều shard, change stream toàn cụm, định tuyến |

Một **replica set một thành viên** vẫn có cơ chế primary và oplog. Nó đủ cho nhiều test chức năng vì MongoDB xem node này là thành viên của một replica set. Nhưng nó không kiểm tra được tự động bầu primary mới, mất một node mà hệ thống vẫn còn quorum, hay độ trễ đồng bộ giữa các thành viên.

### Oplog quan trọng như thế nào?

**Oplog** là nhật ký thao tác có thứ tự mà các thành viên replica set sử dụng để sao chép thay đổi. Change stream đọc các thay đổi từ cơ chế này và trả về những event có cấu trúc, chẳng hạn **insert**, **update**, **replace** hoặc **delete**. Những sự kiện phù hợp chỉ được phát hành khi thay đổi đạt điều kiện xác nhận theo cơ chế của MongoDB.

**Transaction** có semantics khác: nhiều lệnh được thực hiện trong cùng một session/transaction, và việc commit mới làm toàn bộ hiệu ứng của transaction được công khai theo quy tắc nhất quán. Các thay đổi trong transaction đã **abort** không phải các sự kiện dữ liệu được commit để change stream phát ra như một kết quả thành công.

~~~mermaid
flowchart TB
    Test["JUnit integration test"]
    Spring["Spring Data MongoDB<br/>MongoTemplate / Repository"]
    Driver["MongoDB Java Driver"]
    Primary[("mongod<br/>Single-node replica set<br/>PRIMARY + oplog")]
    Tx["MongoTransactionManager<br/>session + commit / abort"]
    Stream["Change stream cursor<br/>watch collection"]
    Test --> Spring
    Spring --> Driver
    Spring --> Tx
    Tx --> Driver
    Driver --> Primary
    Test --> Stream
    Stream --> Driver
    Primary -.->|"Thay đổi đã ghi nhận"| Stream
~~~

Sơ đồ trên mô tả môi trường test đơn giản: client thao tác với một thành viên primary. Khi triển khai production, có thể có nhiều node và nhiều router **mongos**, nhưng nguyên tắc kiểm tra transaction và change stream vẫn dựa trên hành vi server thực.

## 3. Dựng replica set cho test bằng cách nào?

### 3.1. Khởi tạo thủ công

Khi có một MongoDB test riêng, có thể khởi chạy mongod với tùy chọn replica set, ví dụ:

~~~bash
# Đường dẫn thư mục dữ liệu và cách chạy thay đổi theo hệ điều hành.
mongod --dbpath /data/mongo-test --replSet rsTest --bind_ip localhost --port 27017
~~~

Sau khi process chạy, kết nối mongosh và khởi tạo:

~~~javascript
rs.initiate({
  _id: "rsTest",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});

rs.status();
db.hello();
~~~

Đợi đến khi node thực sự trở thành **PRIMARY** trước khi chạy test. URI minh họa khi client và mongod ở cùng máy:

~~~text
mongodb://localhost:27017/spring_mongo_test?replicaSet=rsTest
~~~

**Lưu ý:** tên host mà replica set tự quảng bá phải kết nối được từ nơi chạy test. Nếu container quảng bá tên hostname nội bộ mà JVM trên host không truy cập được, driver có thể kết nối ban đầu rồi báo lỗi **server selection**. Đây là một lý do nên dùng thư viện có sẵn để khởi tạo và ánh xạ URI của replica set khi chạy Docker.

### 3.2. Testcontainers với replica set một node

**Testcontainers** có module MongoDB hỗ trợ khởi tạo MongoDB phục vụ test và cung cấp **replica set URL**. Khi đó bộ kiểm thử có lifecycle rõ ràng, có thể chạy cục bộ hoặc trong CI có Docker tương thích.

Ví dụ dependency Gradle cho dự án Spring Boot 3.x và Testcontainers 1.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong Testcontainers 1.x, class thường dùng là **org.testcontainers.containers.MongoDBContainer**. Với các thế hệ Testcontainers mới hơn, tên artifact/package có thể đã được tổ chức lại; cần chỉnh theo phiên bản của dự án. Mẫu bên dưới minh họa API của Testcontainers 1.x với MongoDB 7.0, không hàm ý toàn bộ ứng dụng đều phải cố định các phiên bản này.

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ReplicaSetSmokeTest {

    @Container
    static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @Test
    void containerExposesReplicaSetUri() {
        String uri = MONGO.getReplicaSetUrl();
        org.junit.jupiter.api.Assertions.assertTrue(uri.startsWith("mongodb://"));
    }
}
~~~

Smoke test chỉ xác nhận container đã khởi chạy và API trả URI; **bài test transaction/change stream ở phần sau mới xác nhận các tính năng hoạt động**. Không nên chỉ assert URI để kết luận replica set đã đáp ứng đúng toàn bộ yêu cầu nghiệp vụ.

## 4. Cấu hình Spring Data MongoDB dùng đúng URI của container

Spring Boot thường cung cấp cấu hình tự động cho MongoClient và MongoTemplate. Với các ví dụ **Spring Boot 3.x**, thuộc tính URI là **spring.data.mongodb.uri**. Ở các dòng Spring Boot mới hơn, tên property/auto-configuration có thể thay đổi; cần dùng thuộc tính đúng với phiên bản đang triển khai.

Trong integration test, **@DynamicPropertySource** đưa URI được Testcontainers tạo lúc chạy vào Spring context:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void mongoProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
}
~~~

Điểm quan trọng:

- **MONGO** là container static được Testcontainers khởi động cho class test.
- **getReplicaSetUrl()** cung cấp thông tin kết nối thích hợp cho replica set test, kể cả host/port được ánh xạ động.
- Không nên tự đoán port **27017** trên máy host; Testcontainers thường ánh xạ ra một port khác.
- Nếu ứng dụng có nhiều **MongoClient**, cần bảo đảm client dùng trong test transaction và client dùng cho change stream kết nối tới cùng deployment test theo đúng cấu hình.

Test phải chờ container và replica set khởi động xong, đồng thời tránh chia sẻ MongoDB test với ứng dụng thật. Testcontainers hỗ trợ vòng đời container; các thử nghiệm độ sẵn sàng còn cần đặt timeout hợp lý và xác minh hành vi cụ thể.

## 5. Test transaction thực với MongoTransactionManager

### 5.1. Vì sao chỉ dùng @Transactional chưa đủ?

Trong Spring Data MongoDB, **@Transactional** có ý nghĩa khi có transaction manager phù hợp và code thực thi qua proxy/quản lý transaction của Spring. Với cách truy cập đồng bộ, **MongoTransactionManager** liên kết session với các thao tác MongoDB được thực hiện trong phạm vi transaction.

Điều kiện cần:

1. MongoDB server là replica set/sharded cluster tương thích với transaction.
2. Spring Data sử dụng **MongoDatabaseFactory** và MongoClient phù hợp.
3. Có bean **MongoTransactionManager** và transaction management được kích hoạt.
4. Lời gọi business method đi qua Spring bean/proxy, thay vì tự tạo đối tượng bằng **new**.
5. Thao tác ghi thực sự đi qua thành phần dữ liệu có tham gia session của transaction.

**Self-invocation** là lỗi dễ gặp: một phương thức trong cùng class gọi thẳng phương thức khác có **@Transactional** có thể đi vòng qua proxy và không mở transaction như mong đợi.

### 5.2. Domain và repository minh họa

Giả sử nghiệp vụ cần ghi **hai dòng ledger** cùng một batch. Nếu lỗi xảy ra sau khi ghi dòng đầu, transaction phải rollback cả hai dòng.

~~~java
// LedgerEntry.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "ledger_entries")
public record LedgerEntry(
    @Id String id,
    String batchId,
    long amount
) {}
~~~

~~~java
// LedgerEntryRepository.java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface LedgerEntryRepository
        extends MongoRepository<LedgerEntry, String> {

    long countByBatchId(String batchId);
}
~~~

~~~java
// LedgerService.java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    private final LedgerEntryRepository repository;

    public LedgerService(LedgerEntryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void writePair(String batchId) {
        repository.save(new LedgerEntry(batchId + "-in", batchId, 100));
        repository.save(new LedgerEntry(batchId + "-out", batchId, -100));
    }

    @Transactional
    public void writePairThenFail(String batchId) {
        repository.save(new LedgerEntry(batchId + "-in", batchId, 100));
        repository.save(new LedgerEntry(batchId + "-out", batchId, -100));
        throw new IllegalStateException("Forced business failure");
    }
}
~~~

Hai thao tác **save** trên cùng document collection cho phép ta quan sát rõ tính nguyên tử của transaction. Trường hợp lỗi được tạo có chủ đích bằng runtime exception để kích hoạt rollback theo quy tắc mặc định của Spring. Với checked exception, cần xem xét cấu hình **rollbackFor** hoặc chính sách rollback phù hợp.

### 5.3. Cấu hình transaction manager riêng cho test

~~~java
// MongoTxTestConfiguration.java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@TestConfiguration(proxyBeanMethods = false)
@EnableTransactionManagement
public class MongoTxTestConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory mongoDatabaseFactory
    ) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

Bean này dành cho test để làm rõ dependency. Trong ứng dụng thực, transaction manager có thể đã được khai báo trong cấu hình chung, khi đó cần tránh đăng ký trùng tên hoặc đăng ký nhiều manager khiến Spring chọn nhầm.

### 5.4. Test commit và rollback trên replica set thật

~~~java
// MongoReplicaSetIntegrationTest.java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@DataMongoTest
@Import({LedgerService.class, MongoTxTestConfiguration.class})
class MongoReplicaSetIntegrationTest {

    @Container
    static final MongoDBContainer MONGO =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", MONGO::getReplicaSetUrl);
    }

    @Autowired LedgerEntryRepository repository;
    @Autowired LedgerService service;
    @Autowired MongoTemplate template;

    @BeforeEach
    void ensureCollectionExists() {
        // Tạo collection trước khi bắt đầu transaction để không phụ
        // thuộc vào hành vi tạo collection ngầm bên trong transaction.
        if (!template.collectionExists(LedgerEntry.class)) {
            template.createCollection(LedgerEntry.class);
        }
    }

    @Test
    void successfulTransactionCommitsBothDocuments() {
        String batchId = UUID.randomUUID().toString();

        service.writePair(batchId);

        assertEquals(2, repository.countByBatchId(batchId));
    }

    @Test
    void runtimeFailureRollsBackBothDocuments() {
        String batchId = UUID.randomUUID().toString();

        assertThrows(
            IllegalStateException.class,
            () -> service.writePairThenFail(batchId)
        );

        assertEquals(0, repository.countByBatchId(batchId));
    }
}
~~~

Hai test chứng minh điều khác nhau:

- **Commit:** khi lời gọi Spring service kết thúc bình thường, hai document phải tồn tại sau khi transaction commit.
- **Rollback:** khi service ném lỗi trong transaction, không document nào của batch được lưu lại.

Các test dùng **UUID** cho batch để tránh ảnh hưởng bởi dữ liệu còn sót lại trong cùng container. Nếu cần đối chiếu rõ hơn, có thể truy vấn từng ID trước và sau operation.

**Không đặt @Transactional trên chính test method** trong ví dụ này. Transaction do test framework mở quanh test có thể làm sai ý nghĩa của phép đo commit: sau khi service trả về, các ghi có thể vẫn chưa được commit, hoặc toàn bộ test tự rollback khi kết thúc. Mục tiêu ở đây là kiểm tra transaction được quản lý bởi **LedgerService**.

Một điểm nữa: cần so sánh hành vi khi có và không có transaction manager đúng cách. Nếu manager thiếu, ứng dụng có thể không tạo transaction hoặc báo lỗi tùy cấu hình. **Bằng chứng đáng tin là trạng thái dữ liệu sau khi gọi service**, kết hợp kiểm tra topology và transaction manager, chứ không chỉ nhìn thấy annotation.

## 6. Test change stream bằng cursor đồng bộ

### 6.1. Bẫy quan trọng: chỉ nhận thay đổi xảy ra sau khi mở stream

Change stream thường theo dõi những thay đổi **sau thời điểm bắt đầu quan sát** (trừ khi dùng cơ chế tiếp tục từ token/thời điểm hợp lệ). Nếu insert document trước rồi mới gọi **watch()**, test có thể chờ mãi mà không nhận event.

Một test ổn định cần:

1. Tạo collection trước khi mở stream.
2. Mở stream và **khởi tạo cursor** trước khi ghi document.
3. Ghi document với ID riêng, phân biệt được với event từ test khác.
4. Poll tới khi thấy đúng event trong một deadline hữu hạn.
5. Đóng cursor bằng **try-with-resources**.

Ví dụ sử dụng **MongoTemplate** để lấy collection của Java Driver, từ đó gọi **watch()**:

~~~java
// Đặt phương thức này trong class test sử dụng @DataMongoTest và
// Testcontainers ở mục 5.4, với MongoTemplate đã được @Autowired.
import static org.junit.jupiter.api.Assertions.*;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.bson.Document;
import org.junit.jupiter.api.Test;

@Test
void insertAppearsOnChangeStream() {
    String collectionName = "stream_events";
    if (!template.collectionExists(collectionName)) {
        template.createCollection(collectionName);
    }

    MongoCollection<Document> collection =
        template.getCollection(collectionName);
    String eventId = UUID.randomUUID().toString();

    // iterator() thực hiện việc mở cursor phía server trước thao tác ghi.
    try (MongoCursor<ChangeStreamDocument<Document>> cursor =
             collection.watch()
                 .maxAwaitTime(200, TimeUnit.MILLISECONDS)
                 .iterator()) {

        collection.insertOne(new Document("_id", eventId)
            .append("eventType", "ORDER_CREATED"));

        ChangeStreamDocument<Document> matched = null;
        long deadline =
            System.nanoTime() + TimeUnit.SECONDS.toNanos(15);

        while (System.nanoTime() < deadline) {
            ChangeStreamDocument<Document> candidate = cursor.tryNext();
            if (candidate == null) {
                continue;
            }
            if (candidate.getOperationType() == OperationType.INSERT
                && candidate.getDocumentKey() != null
                && eventId.equals(
                    candidate.getDocumentKey()
                        .getString("_id")
                        .getValue()
                )) {
                matched = candidate;
                break;
            }
        }

        assertNotNull(matched, "Expected insert change event");
        assertEquals(
            "ORDER_CREATED",
            matched.getFullDocument().getString("eventType")
        );
        assertNotNull(matched.getResumeToken());
    }
}
~~~

Đoạn test này **dùng chung class test, trường template và container** ở mục 5.4; khi đưa vào dự án, đặt import ở đầu file và phương thức **insertAppearsOnChangeStream()** trong class đó. Kết quả mong đợi là một event:

~~~javascript
{
  operationType: "insert",
  documentKey: { _id: "ID-cua-test" },
  fullDocument: {
    _id: "ID-cua-test",
    eventType: "ORDER_CREATED"
  },
  _id: { /* resume token */ }
}
~~~

Đây là minh họa cấu trúc trường; **_id** của change event là một **resume token dạng BSON**, không giống **_id** document được thay đổi. Không nên hardcode giá trị token hoặc so sánh thứ tự byte của token giữa những phiên bản MongoDB.

### 6.2. Vì sao dùng tryNext và deadline?

- **tryNext()** cho phép kiểm tra xem có event mới trong đợt đợi/getMore hay chưa; có thể trả **null** khi tạm thời chưa có event.
- **maxAwaitTime** kiểm soát thời gian đợi các lệnh lấy thêm event trên cursor.
- Deadline hữu hạn tránh test treo vô thời hạn khi event không xuất hiện.
- Lọc theo **documentKey._id** tránh nhận nhầm event do một test khác tạo ra.

Vì đây là test tích hợp thực, CI có thể chịu độ trễ tài nguyên lớn hơn môi trường local. Timeout nên được đặt theo thực tế CI, tránh quá ngắn khiến test thất bại ngẫu nhiên. Không dùng **Thread.sleep()** tùy ý để “hy vọng stream đã sẵn sàng”, vì sleep không chứng minh rằng server đã mở change stream.

### 6.3. Thử nghiệm update, delete và resume

Khi mở rộng bài test:

- Với **UPDATE**, event thường có **updateDescription**, nhưng **fullDocument** có thể không có nội dung đầy đủ nếu không yêu cầu **fullDocument: updateLookup** hoặc cấu hình tương thích.
- Với **DELETE**, document đã bị xóa nên không thể giả định **fullDocument** luôn chứa dữ liệu cũ.
- Khi cần tiếp tục stream, lưu **resume token** từ event đã xử lý và dùng tính năng **resumeAfter/startAfter** phù hợp. Token phụ thuộc oplog và thời hạn giữ dữ liệu; token quá cũ có thể không resume được.
- Test thay đổi DDL hoặc invalidate stream cần thiết kế riêng; việc xóa/drop collection có thể làm stream kết thúc hoặc thay đổi trạng thái.

Một bài test insert đơn giản đủ để xác minh môi trường đã bật change streams. Nó chưa chứng minh đúng mọi event type, tính liên tục khi primary thay đổi, hoặc cơ chế retry của một change-stream consumer thực.

## 7. Change stream với ReactiveMongoTemplate

Nếu ứng dụng dùng **reactive access**, Spring Data MongoDB có thể cung cấp **Flux** các **ChangeStreamEvent** thay cho cursor đồng bộ. API được dùng theo dạng:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import reactor.core.publisher.Flux;

Flux<ChangeStreamEvent<OrderDocument>> updates =
    reactiveMongoTemplate.changeStream(
        "orders",
        ChangeStreamOptions.empty(),
        OrderDocument.class
    );
~~~

Ví dụ ở trên giả định có **reactiveMongoTemplate** và entity **OrderDocument** do ứng dụng khai báo. Phiên bản Spring Data có thể cung cấp thêm API builder cho **ChangeStreamOptions**, ví dụ lựa chọn điều kiện filter hoặc resume token.

Điểm khác biệt khi test reactive là **Flux thường chỉ bắt đầu theo dõi khi có subscriber**. Chỉ khai báo biến **updates** rồi thực hiện save chưa đủ. Nếu viết:

~~~java
reactiveMongoTemplate.save(order).block();
StepVerifier.create(updates.take(1)).expectNextCount(1).verifyComplete();
~~~

thì subscriber bắt đầu **sau** khi thay đổi đã diễn ra; event có thể không được quan sát.

Để test ổn định, cần cơ chế phối hợp đảm bảo stream đã được thiết lập trước thao tác ghi (hoặc dùng resume token/thời điểm bắt đầu thích hợp). Có thể:

- Dùng cursor đồng bộ như mục 6 cho kiểm thử topology và semantics cơ bản.
- Trong test reactive chuyên sâu, dùng một tín hiệu xác nhận subscription **và** thời điểm stream đã được mở phía server, hoặc cấu hình resume/start-at phù hợp với yêu cầu test.
- Dùng **StepVerifier** để kiểm tra dữ liệu, error/completion và giới hạn thời gian sau khi điều phối chắc chắn. Tránh **thenAwait** với thời gian cố định như một cách chứng minh stream đã sẵn sàng.

Với **reactive transaction**, cần **ReactiveMongoTransactionManager** và các thao tác MongoDB reactive phải tham gia cùng reactive transaction context. Không giả định **MongoTransactionManager** của luồng đồng bộ có thể quản lý transaction của ReactiveMongoTemplate. Khi test commit/rollback reactive, phải subscribe pipeline và xác nhận trạng thái dữ liệu sau kết quả.

## 8. Kết hợp transaction và change stream trong một test

Một trường hợp thực tế là consumer chỉ được xử lý **event từ transaction đã commit**. Ví dụ hệ thống ghi cùng lúc ledger và outbox event trong một transaction:

~~~mermaid
sequenceDiagram
    participant Test as JUnit Test
    participant Watch as Change stream
    participant S as Spring service
    participant Mongo as MongoDB replica set
    Test->>Watch: Mở stream trên outbox
    Test->>S: Gọi nghiệp vụ transactional
    S->>Mongo: Ghi ledger + outbox trong transaction
    alt Commit thành công
        S->>Mongo: commit
        Mongo-->>Watch: Phát sự kiện outbox
        Watch-->>Test: Nhận event, xác minh payload
    else Rollback
        S->>Mongo: abort
        Note over Watch,Mongo: Không có outbox event được commit
    end
~~~

Với trường hợp commit, test nên kiểm tra hai mặt: **document nghiệp vụ được ghi** và **event tương ứng xuất hiện trong change stream**. Với rollback, xác nhận các document không tồn tại, đồng thời không có event tương ứng được commit. Tránh dùng một thời gian đợi ngắn để kết luận chắc chắn **không bao giờ** có event; test phủ định cần deadline hữu hạn, lọc đúng ID và tiêu chí rõ ràng.

**Outbox pattern** thường cần consumer xử lý idempotent vì việc phân phối event/khởi động lại consumer có thể khiến một event được nhận nhiều lần ở tầng ứng dụng. Test tích hợp transaction và change stream không thay thế kiểm thử idempotency, checkpoint và resume token.

## 9. Những lỗi thường gặp trong môi trường test

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/cách xử lý |
| --- | --- | --- |
| Transaction báo **Transaction numbers are only allowed on a replica set member or mongos** | Đang kết nối standalone hoặc sai endpoint | Kiểm tra **rs.status()**, URI và container đang chạy |
| **$changeStream is only supported on replica sets** | Server không chạy như replica set | Dùng replica set hoặc sharded cluster tương thích |
| **Server selection timeout**, không thấy PRIMARY | Replica set chưa khởi tạo, đang bầu primary, hostname quảng bá không truy cập được | Kiểm tra **db.hello()**, **rs.status()**, hostname và replica set URI |
| **@Transactional** chạy nhưng dữ liệu không rollback | Thiếu manager, proxy không được áp dụng, tự gọi method trong cùng class, hoặc ghi ngoài session | Kiểm tra cấu hình transaction, cách inject service và các bean sử dụng MongoClient |
| Transaction báo lỗi tạo collection/index | Collection/index được tạo ngầm trong transaction hoặc topology/quyền không phù hợp | Tạo collection và index trước transaction trong setup |
| Test change stream không bao giờ nhận event | Stream được mở sau insert, thiếu subscription, sai namespace hoặc filter | Mở cursor trước ghi; xác minh collection/ID và timeout |
| Test nhận nhầm event | Test song song chia sẻ collection, không lọc theo document ID | Dùng collection/ID duy nhất; filter event chính xác |
| Event UPDATE thiếu fullDocument | Chưa yêu cầu lookup hoặc semantics event khác insert | Sử dụng **fullDocument: updateLookup** nếu phù hợp |
| Resume thất bại sau thời gian dài | Oplog đã loại bỏ phần lịch sử cần thiết, token không còn hợp lệ | Tăng khả năng giữ lịch sử phù hợp hoặc thiết kế tái đồng bộ |
| Test chạy cục bộ nhưng lỗi trong CI | Docker không khả dụng, thiếu tài nguyên, timeout quá ngắn, quyền container khác nhau | Kiểm tra Docker service, tài nguyên, log MongoDB và thời điểm primary sẵn sàng |

### Lệnh kiểm tra topology hữu ích

Khi có quyền truy cập vào mongosh của môi trường test:

~~~javascript
// Trạng thái thành viên replica set:
rs.status();

// Thông tin topology và vai trò của server:
db.hello();

// Cấu hình replica set hiện hành:
rs.conf();
~~~

Trong một replica set một node, hãy xác minh node đã là **PRIMARY**. Đừng giả định chỉ cần cổng TCP mở thì MongoDB đã sẵn sàng cho transaction hoặc change stream.

## 10. Cách tổ chức test để kết quả đáng tin

### 10.1. Phân biệt unit test và integration test

Không phải bài test nào của service dùng Spring Data MongoDB cũng cần container. Quy tắc tính phí, validation, chuyển trạng thái có thể kiểm tra bằng JUnit/Mockito không cần database. Nhưng **transaction và change stream là hành vi của MongoDB server**, nên cần integration test thực để chứng minh.

### 10.2. Tránh gây nhiễu dữ liệu

Sử dụng ID riêng cho từng test, collection riêng khi cần, hoặc dọn dữ liệu trước/sau mỗi test. Với test change stream, dọn dữ liệu cũng có thể sinh event **delete**; cần lọc theo ID và điều khiển thứ tự test. Không dùng chung collection giữa các test chạy song song nếu chúng giả định không có thao tác cạnh tranh.

### 10.3. Không nhầm rollback của test framework với rollback nghiệp vụ

Các thư viện test của Spring có thể tự tạo transaction quanh test khi có annotation/cấu hình tương ứng. Điều đó làm việc quan sát trạng thái sau **service commit** phức tạp hơn. Khi muốn chứng minh @Transactional của service hoạt động, để service quản lý transaction và đọc kết quả sau khi lời gọi đã hoàn tất.

### 10.4. Test chức năng và test khả năng chịu lỗi có mục tiêu khác nhau

Single-node replica set phù hợp cho kiểm thử hành vi transaction và lắng nghe change stream cơ bản. Muốn test **failover** hoặc **resume sau bầu primary mới**, phải dùng replica set nhiều node, topology mạng thực tế và các tình huống thay đổi primary có kiểm soát. Không suy ra tính sẵn sàng cao chỉ từ việc single-node test đã xanh.

### 10.5. Không giữ cursor vô hạn

Change stream được thiết kế để lắng nghe dài hạn; test thì phải kết thúc. Dùng **try-with-resources** cho cursor đồng bộ hoặc quản lý **Disposable/subscription** cho reactive. Đặt deadline rõ ràng và thông báo lỗi hữu ích khi quá thời gian để pipeline CI không bị treo.

### 10.6. Đo đúng mục tiêu

| Mục tiêu | Assert nên có | Assert chưa đủ |
| --- | --- | --- |
| Transaction commit | Cả hai document nhìn thấy sau service trả về | Chỉ kiểm tra service không ném exception |
| Transaction rollback | Không còn document nào của batch thất bại | Chỉ kiểm tra exception đã xảy ra |
| Change stream insert | Nhận event INSERT đúng documentKey và payload | Chỉ kiểm tra cursor tạo được |
| Resume stream | Consumer khởi động lại, đọc tiếp từ token hợp lệ, không mất event cần xử lý | Chỉ kiểm tra token không null |
| Failover | Client hoạt động/khôi phục theo yêu cầu sau thay đổi primary | Chỉ kiểm tra có replica set |

## 11. Checklist triển khai kiểm thử

1. **Phân loại bài test:** đơn thuần nghiệp vụ, repository CRUD, transaction, change stream hay failover.
2. **Chọn topology tương ứng:** standalone cho những trường hợp thực sự đủ, single-node replica set cho transaction/change stream, nhiều node khi cần đo failover.
3. **Ghim phiên bản hợp lý:** MongoDB server, Spring Boot/Spring Data, MongoDB Java Driver và Testcontainers phải tương thích.
4. **Khởi tạo MongoDB tự động:** dùng Testcontainers hoặc cơ chế triển khai test có tái lập, kiểm tra node ở trạng thái PRIMARY.
5. **Cung cấp URI chính xác:** đưa replica set URI vào đúng MongoClient của ứng dụng, không hardcode cổng host.
6. **Chuẩn bị collection/index:** thực hiện thao tác DDL cần thiết trước khi transaction bắt đầu.
7. **Kiểm tra transaction từ bên ngoài proxy:** gọi service đã được Spring quản lý, đo commit và rollback bằng document thật.
8. **Mở change stream trước khi ghi:** lọc theo ID, dùng deadline và đóng cursor/subscription khi kết thúc.
9. **Chạy trên CI:** xác nhận Docker/network, tài nguyên và timeout; giữ log có ích khi thất bại.
10. **Mở rộng theo rủi ro:** thêm test cho concurrent update, resume token, restart consumer, reactive transaction hoặc nhiều node nếu hệ thống yêu cầu.

### Câu hỏi tự kiểm tra

**1. Replica set một node có kiểm thử được transaction không?** Có, khi phiên bản server/driver hỗ trợ và node đã trở thành PRIMARY. Nó không chứng minh failover hay chịu lỗi nhiều node.

**2. Có thể dùng MongoDB standalone để kiểm thử change stream không?** Không với cơ chế change stream MongoDB tiêu chuẩn; cần replica set hoặc sharded cluster phù hợp.

**3. Vì sao test rollback phải đọc dữ liệu sau khi service ném lỗi?** Exception có thể xảy ra mà transaction chưa được mở đúng. Kiểm tra database mới chứng minh những ghi trước lỗi đã rollback.

**4. Vì sao gọi watch sau insert thường không nhận event vừa ghi?** Change stream theo dõi từ thời điểm bắt đầu quan sát. Nếu cần đọc từ trước, phải sử dụng resume token hoặc thời điểm bắt đầu hợp lệ theo cơ chế được hỗ trợ.

**5. Có cần MongoTransactionManager khi dùng Spring @Transactional với MongoDB đồng bộ không?** Có transaction manager phù hợp là điều kiện để Spring quản lý MongoDB transaction; annotation một mình không tự thực thi transaction.

**6. Consumer reactive đã tạo Flux nhưng chưa subscribe có nhận change event không?** Thông thường chưa. Phải bắt đầu subscription và bảo đảm stream hoạt động trước khi thực hiện ghi cần quan sát.

**7. Testcontainers tạo replica set một node đã đủ kiểm thử majority và primary failover chưa?** Chưa. Muốn đánh giá thay đổi primary, quorum và replica lag phải kiểm thử thêm topology nhiều thành viên.

## Kết luận

Trong **Spring Data MongoDB**, kiểm thử **transaction** và **change stream** cần một MongoDB deployment có topology phù hợp. **Single-node replica set với Testcontainers** là điểm bắt đầu hiệu quả để chạy integration test có thể tái lập: Spring lấy URI chính xác, transaction manager quản lý session, test kiểm tra **commit/rollback** từ trạng thái document và change stream kiểm tra **event sau khi stream được mở**. Khi yêu cầu bao gồm failover, đa shard, resume lâu dài hoặc xử lý reactive phức tạp, cần mở rộng mô hình và phép thử theo hành vi vận hành cần chứng minh.
