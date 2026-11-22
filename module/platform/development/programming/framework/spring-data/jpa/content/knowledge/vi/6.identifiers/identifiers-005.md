# Sinh khóa UUID và yêu cầu tương thích phiên bản JPA, Hibernate

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích UUID là gì và vì sao nhiều hệ thống dùng UUID làm khóa chính.
- Phân biệt UUID được sinh bởi JPA provider, bởi ứng dụng và bởi database.
- Dùng `GenerationType.UUID` khi runtime hỗ trợ Jakarta Persistence 3.1.
- Chọn cách triển khai phù hợp cho hệ thống cũ dùng JPA 2.2 hoặc Hibernate phiên bản chưa hỗ trợ chuẩn UUID generation.
- Hiểu ảnh hưởng của kiểu UUID, cách lưu trữ, index, thứ tự sinh khóa và tính tương thích.
- Cấu hình UUID trong Spring Data JPA, kiểm tra schema và kiểm thử vòng đời entity.

## 1. UUID là gì?

UUID (Universally Unique Identifier) là mã định danh có độ dài 128 bit, được thiết kế để tạo ra giá trị có xác suất trùng lặp rất thấp trong một không gian hệ thống rộng. Một UUID thường được biểu diễn dưới dạng chuỗi 36 ký tự gồm 32 chữ số hex và 4 dấu gạch nối.

Ví dụ:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Trong Java, kiểu chuẩn là `java.util.UUID`. Không cần tự xử lý UUID như một chuỗi nếu ứng dụng có thể giữ kiểu UUID từ entity, repository đến tầng service.

UUID thường được dùng làm surrogate key vì:

- Có thể tạo ID ở nhiều ứng dụng hoặc node mà không cần hỏi một sequence trung tâm.
- Có thể cấp ID trước khi insert vào database.
- Khó đoán hơn số tăng tuần tự, dù UUID không phải cơ chế bảo mật.
- Thuận tiện khi đồng bộ dữ liệu hoặc tạo bản ghi offline rồi gửi lên server.
- Có không gian định danh lớn, giảm nguy cơ xung đột giữa các hệ thống.

UUID cũng có chi phí: kích thước lớn hơn BIGINT, index có thể lớn hơn và UUID ngẫu nhiên có thể làm giảm tính locality khi insert vào B-tree index. Vì vậy, không nên chọn UUID chỉ vì đây là một xu hướng; cần xét quy mô, database, cách phân phối dữ liệu và yêu cầu tích hợp.

## 2. Các cách sinh UUID

Có ba nơi phổ biến để tạo UUID:

1. JPA provider sinh theo chiến lược chuẩn hoặc extension của provider.
2. Ứng dụng tự tạo UUID trước khi persist.
3. Database tạo UUID bằng hàm hoặc default expression của database.

Mỗi cách có thời điểm tạo, tính di động và ảnh hưởng đến Spring Data khác nhau.

| Cách sinh | Ví dụ | Điểm mạnh | Cần lưu ý |
|---|---|---|---|
| JPA chuẩn | `GenerationType.UUID` | Di động giữa các provider hỗ trợ Jakarta Persistence 3.1 | Cần đúng JPA API và provider runtime |
| Hibernate extension | `@UuidGenerator` | Có tùy chọn đặc thù Hibernate | Không portable; phụ thuộc phiên bản Hibernate |
| Ứng dụng | `UUID.randomUUID()` | Có ID trước khi persist, dùng được cả với JPA cũ | Phải quản lý newness detection của Spring Data khi ID đã có |
| Database | Hàm UUID hoặc default của DB | Database là nơi chịu trách nhiệm sinh ID | Phụ thuộc database và mapping insert/default |

### UUID ngẫu nhiên và UUID có thứ tự

Java `UUID.randomUUID()` tạo UUID version 4 dựa trên số ngẫu nhiên mạnh. Cách này đơn giản và phù hợp với nhiều hệ thống.

Một số hệ thống cần UUID có thứ tự gần theo thời gian để cải thiện locality của index. UUID version 7 được thiết kế có thành phần thời gian ở đầu mã, theo RFC 9562. Java 17 không cung cấp API chuẩn dựng sẵn để sinh UUID v7; cần thư viện hoặc cơ chế đã được lựa chọn và kiểm thử. UUID có thứ tự cũng có thể để lộ thông tin thời gian tạo gần đúng, nên cần cân nhắc khi đưa ra ngoài hệ thống.

Không giả định rằng `GenerationType.UUID` luôn tạo cùng một UUID version trên mọi provider. Đặc tả chuẩn hóa kiểu định danh và chiến lược, nhưng thuật toán/chi tiết provider có thể khác. Nếu hệ thống phụ thuộc vào UUID version cụ thể, hãy chọn generator rõ ràng và kiểm thử giá trị thực tế.

## 3. Sinh UUID bằng Jakarta Persistence 3.1

Jakarta Persistence 3.1 bổ sung `GenerationType.UUID`. Khi cả API biên dịch và JPA provider lúc chạy đều hỗ trợ Jakarta Persistence 3.1, có thể dùng annotation chuẩn:

~~~java
package com.example.catalog;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    protected Product() {
        // Required by JPA
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public UUID getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Repository khai báo kiểu ID là UUID:

~~~java
package com.example.catalog;

import java.util.Optional;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, UUID> {

    Optional<Product> findBySku(String sku);
}
~~~

Spring Data JPA sử dụng kiểu ID generic của repository. Nếu entity khai báo `UUID` nhưng repository lại khai báo `Long`, các method như `findById`, `deleteById` và các thao tác ID khác sẽ không khớp kiểu.

### Điều kiện tương thích

Để compile và chạy được `GenerationType.UUID`, cần đồng bộ cả ba lớp:

- Jakarta Persistence API phải có enum `GenerationType.UUID`, tức đặc tả 3.1 trở lên.
- JPA provider runtime phải thực hiện chiến lược UUID của đặc tả đó.
- Spring Data JPA và Spring Framework phải thuộc bộ phiên bản tương thích với provider và namespace đang dùng.

Chỉ thêm dependency API mới để làm code biên dịch không đủ nếu runtime vẫn dùng provider cũ. Khi chạy có thể gặp lỗi liên quan enum/strategy hoặc provider không xử lý annotation như mong đợi.

Với Spring Boot, nên để Spring Boot BOM quản lý phiên bản Spring Data, Hibernate và Jakarta Persistence. Không tự nâng riêng `jakarta.persistence-api` hoặc Hibernate lên một phiên bản khác với BOM nếu chưa kiểm tra ma trận tương thích.

## 4. Tương thích với Hibernate và các thế hệ JPA

Một khác biệt quan trọng là namespace và phiên bản đặc tả:

| Hệ sinh thái | Namespace thường gặp | UUID strategy chuẩn |
|---|---|---|
| JPA 2.2 và các stack cũ | `javax.persistence.*` | Không có `GenerationType.UUID` |
| Jakarta Persistence 3.0 | `jakarta.persistence.*` | Chưa có `GenerationType.UUID` |
| Jakarta Persistence 3.1 trở lên | `jakarta.persistence.*` | Có `GenerationType.UUID` |

Spring Boot 2 thường thuộc hệ sinh thái `javax.persistence`; Spring Boot 3 chuyển sang `jakarta.persistence`. Tuy nhiên, chỉ nhìn major version Spring Boot chưa đủ để kết luận mọi tính năng của JPA API đều có mặt. Hãy kiểm tra phiên bản Jakarta Persistence và Hibernate thực tế được BOM quản lý.

### Hibernate hiện đại

Các phiên bản Hibernate có hỗ trợ Jakarta Persistence 3.1 có thể dùng `GenerationType.UUID`. Hibernate cũng có extension riêng như `@UuidGenerator` trong những phiên bản cung cấp annotation này.

Ví dụ extension Hibernate:

~~~java
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import org.hibernate.annotations.UuidGenerator;

@Entity
public class ExternalRecord {

    @Id
    @GeneratedValue
    @UuidGenerator
    private UUID id;

    protected ExternalRecord() {
    }
}
~~~

Đây là cách phụ thuộc Hibernate. Nếu ứng dụng có mục tiêu đổi provider hoặc muốn mapping portable, ưu tiên `GenerationType.UUID` khi provider hỗ trợ JPA 3.1. Nếu cần tính năng riêng của Hibernate, kiểm tra Javadoc và user guide của đúng phiên bản đang chạy trước khi dùng annotation.

### Hibernate cũ và JPA 2.2

JPA 2.2 không có `GenerationType.UUID`. Với hệ thống cũ, cách portable đơn giản là ứng dụng tự gán UUID:

~~~java
import java.util.UUID;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "legacy_records")
public class LegacyRecord {

    @Id
    @Column(name = "id", nullable = false, updatable = false, length = 36)
    private UUID id;

    @Column(name = "description", nullable = false)
    private String description;

    protected LegacyRecord() {
    }

    public LegacyRecord(String description) {
        this.id = UUID.randomUUID();
        this.description = description;
    }

    public UUID getId() {
        return id;
    }
}
~~~

Đoạn code dùng `javax.persistence`, phù hợp với stack JPA 2.x. Nếu dự án dùng Jakarta Persistence thì đổi import sang `jakarta.persistence`; không trộn hai namespace.

Với Hibernate cũ, có thể dùng generator riêng của Hibernate, chẳng hạn generator `uuid2` trong một số phiên bản 5.x:

~~~java
@Id
@GeneratedValue(generator = "uuid2")
@org.hibernate.annotations.GenericGenerator(
    name = "uuid2",
    strategy = "uuid2"
)
private UUID id;
~~~

Đây là extension theo Hibernate và API generator có thể thay đổi/deprecate giữa các major version. Không sao chép cấu hình này sang Hibernate 6+ mà không kiểm tra tài liệu phiên bản. Khi có thể, application-assigned UUID là lựa chọn dễ di chuyển hơn cho hệ thống JPA cũ.

## 5. Sinh UUID ngay trong ứng dụng

Ứng dụng có thể gán ID ngay khi tạo đối tượng:

~~~java
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "outbox_events")
public class OutboxEvent {

    @Id
    @Column(nullable = false, updatable = false)
    private UUID id;

    @Column(nullable = false, length = 100)
    private String eventType;

    protected OutboxEvent() {
    }

    public OutboxEvent(String eventType) {
        this.id = UUID.randomUUID();
        this.eventType = eventType;
    }

    public UUID getId() {
        return id;
    }
}
~~~

Lợi ích là ID đã tồn tại trước khi gọi repository save. Điều này hữu ích khi cần tạo event, liên kết object graph hoặc lưu dữ liệu offline trước khi gửi lên server.

Nhưng với Spring Data JPA có một điểm cần chú ý: mặc định, Spring Data thường xác định entity mới bằng nullable `@Version` trước, sau đó dựa vào ID null. Nếu entity có ID được gán sẵn và không có version property phù hợp, Spring Data có thể xem entity là đã tồn tại và gọi `merge()` thay vì `persist()`.

Có hai cách thường dùng để xử lý:

1. Khai báo thuộc tính `@Version` nullable để Spring Data nhận diện entity mới khi version còn null.
2. Implement `Persistable<UUID>` và tự cung cấp `isNew()`, cập nhật cờ sau khi persist/load.

Ví dụ với `Persistable`:

~~~java
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

@Entity
public class AssignedIdRecord implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity = true;

    protected AssignedIdRecord() {
    }

    public AssignedIdRecord() {
        this.id = UUID.randomUUID();
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    @Transient
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Trong ví dụ trên, constructor không tham số có thể xung đột với constructor không tham số JPA; trong code thực tế hãy giữ đúng một constructor protected cho JPA và một constructor public có tham số nghiệp vụ. Bản rút gọn hợp lệ:

~~~java
protected AssignedIdRecord() {
}

public AssignedIdRecord(String ignoredBusinessValue) {
    this.id = UUID.randomUUID();
}
~~~

Cờ `newEntity` chỉ là ví dụ về state detection. Nếu entity có thể được deserialize, clone hoặc tái sử dụng giữa các persistence context, cần kiểm thử callback và quy trình khởi tạo. Đừng triển khai `Persistable` theo mẫu máy móc khi nullable version property đã giải quyết được vấn đề.

## 6. Lưu trữ UUID trong database

UUID có 128 bit, nhưng cách biểu diễn trong database phụ thuộc hệ quản trị và dialect:

- PostgreSQL có kiểu native `uuid`.
- SQL Server có kiểu `uniqueidentifier`.
- MySQL thường được thiết kế với `BINARY(16)` hoặc `CHAR(36)`; lựa chọn ảnh hưởng dung lượng và cách chuyển đổi.
- Một số database khác lưu UUID dưới dạng binary hoặc chuỗi.

Không nên ép `columnDefinition = "uuid"` cho mọi database vì kiểu `uuid` không phải kiểu SQL phổ quát. Hãy để dialect chọn kiểu phù hợp hoặc dùng migration riêng cho database mục tiêu.

### Binary và chuỗi

| Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|
| Native UUID | Database hiểu UUID như một kiểu dữ liệu riêng | Phụ thuộc database |
| BINARY(16) | Nhỏ hơn chuỗi 36 ký tự, index gọn hơn | Khó đọc trực tiếp; cần quy tắc byte order thống nhất |
| CHAR(36) | Dễ đọc, dễ debug và truyền qua công cụ | Tốn dung lượng hơn, collation/string comparison cần được tính đến |

Hibernate có thể chọn kiểu JDBC/SQL theo dialect và cấu hình của phiên bản. Không giả định mọi database đều nhận cùng một kiểu vật lý. Khi cần ép kiểu lưu trữ, hãy tra cứu thuộc tính Hibernate của đúng phiên bản và kiểm thử migration.

Nếu ứng dụng lưu UUID ở dạng binary, mọi dịch vụ khác đọc/ghi cột đó phải thống nhất cách chuyển 16 byte thành UUID. Sai thứ tự byte có thể tạo ra UUID khác dù dữ liệu có vẻ hợp lệ.

## 7. UUID và hiệu năng index

UUID ngẫu nhiên version 4 phân bố đều trong không gian khóa. Khi insert liên tục, các giá trị có thể rơi vào nhiều vị trí của B-tree index, làm tăng page split và giảm locality so với ID tăng tuần tự. Mức ảnh hưởng phụ thuộc database, kích thước bảng, workload, fill factor và cấu trúc index.

Một số hướng cân nhắc:

- Dùng UUID native hoặc binary 16 byte nếu database và stack hỗ trợ tốt.
- Dùng UUID có thứ tự thời gian như version 7 nếu workload cần cải thiện locality và có generator phù hợp.
- Không thêm index dư thừa lên cùng một cột đã là primary key.
- Đo bằng benchmark gần với workload thật trước khi đổi generator.
- Cân nhắc index trên natural key riêng nếu ứng dụng thường xuyên tra cứu theo mã nghiệp vụ.

UUID v7 cải thiện thứ tự gần theo thời gian nhưng không phải phép thay thế tự động cho UUID v4. Nó có thể tiết lộ thời gian tạo gần đúng và cần đảm bảo mọi producer sinh theo cùng định dạng. Hãy kiểm tra hỗ trợ của thư viện, database và hệ thống tích hợp trước khi chọn.

## 8. UUID trong API và hệ thống phân tán

UUID thường được serialize thành chuỗi chuẩn để truyền qua JSON:

~~~json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "PRODUCT_CREATED"
}
~~~

Ở tầng Java, giữ kiểu `UUID` thay vì chuyển sang `String` ở mọi lớp. Chuyển đổi sang chuỗi tại ranh giới API hoặc message giúp validation và mapping rõ ràng.

Trong hệ thống nhiều dịch vụ:

- Định nghĩa service nào sở hữu ID và ai được phép tạo ID.
- Xác định UUID được dùng xuyên service hay mỗi service có ID nội bộ riêng.
- Dùng unique constraint ở nơi lưu trữ cuối cùng.
- Định nghĩa quy tắc idempotency cho request/message để tránh xử lý trùng.
- Không xem UUID khó đoán là quyền truy cập. Mọi endpoint vẫn phải kiểm tra quyền trên tài nguyên.
- Không thay UUID bằng ID tuần tự trong URL chỉ để ẩn thông tin nếu authorization chưa được thực hiện.

UUID giúp giảm nhu cầu đồng bộ cấp ID, nhưng không tự giải quyết xung đột dữ liệu, phân quyền, idempotency hay consistency giữa các dịch vụ.

## 9. Migration từ khóa số sang UUID

Chuyển một bảng đang dùng BIGINT primary key sang UUID là thay đổi schema và API có thể ảnh hưởng đến toàn hệ thống.

Một quy trình expand-and-contract thường an toàn hơn:

1. Thêm cột UUID mới, cho phép null tạm thời.
2. Sinh và backfill UUID cho các bản ghi hiện tại.
3. Tạo unique constraint/index trên cột UUID và xác minh không có null/trùng.
4. Thêm cột UUID tương ứng ở các bảng con; backfill bằng cách join theo khóa cũ.
5. Tạo foreign key mới và xác minh toàn bộ quan hệ.
6. Triển khai ứng dụng có thể đọc/ghi theo chiến lược chuyển tiếp; nếu cần, dual-write có kiểm soát.
7. Chuyển truy vấn, API và consumer sang UUID.
8. Theo dõi consumer cũ, job, báo cáo và dữ liệu tích hợp.
9. Chỉ bỏ khóa cũ sau khi không còn tham chiếu và đã có kế hoạch rollback.

Không xóa BIGINT primary key trước khi mọi foreign key, consumer và dữ liệu lịch sử đã được xử lý. Với hệ thống đang hoạt động, cần migration theo từng bước, backup, kiểm tra số lượng bản ghi và khả năng rollback.

## 10. Kiểm thử UUID trong Spring Data JPA

Một integration test nên kiểm tra:

- Entity mới được persist và ID không null sau khi lưu.
- Hai entity mới có UUID khác nhau.
- Repository có kiểu ID là UUID và `findById` trả đúng entity.
- UUID được serialize/deserialize qua API theo định dạng đã thống nhất.
- Unique constraint và foreign key vẫn hoạt động.
- Application-assigned ID được Spring Data nhận diện đúng là entity mới.
- `equals()` và `hashCode()` không đổi bất ngờ khi entity chuyển trạng thái.
- Cấu hình runtime provider thực sự hỗ trợ chiến lược đang dùng.

Ví dụ kiểm tra đơn giản với JUnit và repository:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository repository;

    @Test
    void generatedUuidCanBePersistedAndLoaded() {
        Product product = new Product("BK-UUID-01", "UUID Guide");

        Product saved = repository.saveAndFlush(product);

        assertNotNull(saved.getId());
        assertEquals(product.getSku(),
                repository.findById(saved.getId()).orElseThrow().getSku());
    }
}
~~~

Test này giả định entity Product dùng `GenerationType.UUID` và runtime hỗ trợ Jakarta Persistence 3.1. Với application-assigned ID, bổ sung kiểm thử Spring Data newness detection để xác nhận `persist`/`merge` được chọn đúng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không compile được GenerationType.UUID | API Jakarta Persistence đang dùng thấp hơn 3.1 hoặc import sai namespace | Kiểm tra dependency API, BOM và import |
| Compile được nhưng runtime không hỗ trợ UUID strategy | API compile mới hơn provider runtime | Đồng bộ JPA API và provider theo BOM tương thích |
| Không tìm thấy annotation UuidGenerator | Hibernate version không có extension này hoặc dependency không đúng | Dùng JPA chuẩn nếu hỗ trợ; kiểm tra tài liệu Hibernate đúng phiên bản |
| Hai namespace javax và jakarta cùng xuất hiện | Trộn thư viện JPA 2.x và Jakarta Persistence | Chọn một stack tương thích, không trộn API |
| Spring Data gọi merge cho entity mới có UUID sẵn | ID khác null khiến cơ chế mặc định nghĩ entity đã tồn tại | Dùng nullable @Version hoặc Persistable.isNew() |
| UUID lưu sai định dạng hoặc không đọc được | Mapping JDBC/SQL hoặc byte order không thống nhất | Kiểm tra dialect, kiểu cột và chuyển đổi ở mọi producer |
| Index chậm khi insert nhiều | UUID ngẫu nhiên làm giảm locality hoặc index quá lớn | Đo workload, xem xét UUID v7 hoặc kiểu lưu trữ phù hợp |
| Cho rằng UUID bảo vệ endpoint | ID khó đoán bị nhầm với authorization | Kiểm tra quyền truy cập ở service/API |

## Checklist trước khi merge

- [ ] Kiểu Java của ID là UUID và repository dùng đúng generic ID type.
- [ ] Jakarta Persistence API và runtime provider hỗ trợ chiến lược UUID được chọn.
- [ ] Spring Boot BOM quản lý JPA API, Spring Data và Hibernate đồng bộ.
- [ ] Nếu dùng JPA 2.2, không dùng GenerationType.UUID; chọn generator tương thích hoặc tự gán UUID.
- [ ] Không trộn javax.persistence và jakarta.persistence.
- [ ] Database column type và JDBC mapping đã được kiểm tra trên database mục tiêu.
- [ ] Unique/primary key constraint và foreign key được tạo bằng migration.
- [ ] Spring Data nhận diện đúng entity mới khi UUID được gán trước.
- [ ] API, message và các service thống nhất định dạng UUID.
- [ ] Integration test xác nhận sinh ID, lưu, đọc, quan hệ và serialization.

## Kết luận

UUID là một surrogate key hữu ích khi cần tạo định danh phân tán hoặc cấp ID trước khi lưu. `GenerationType.UUID` là cách chuẩn từ Jakarta Persistence 3.1, nhưng chỉ hoạt động khi cả API biên dịch và provider runtime hỗ trợ. Với JPA 2.2, có thể tự gán UUID hoặc dùng extension đúng phiên bản Hibernate. Hãy thống nhất kiểu cột và cách chuyển đổi ở database, kiểm tra newness detection của Spring Data khi ID được gán sẵn, và đánh giá kích thước index cùng thứ tự UUID theo workload thực tế.
