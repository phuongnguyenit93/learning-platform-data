# Nhiều keyspace, nhiều session và phân biệt các bean trong Spring Data Cassandra

## 1. Khi một ứng dụng cần truy cập nhiều keyspace

Giả sử một ứng dụng Spring Boot phục vụ hai nhóm chức năng:

- **Catalog:** đọc sản phẩm từ keyspace `catalog_ks`.
- **Billing:** ghi và tra cứu hóa đơn từ keyspace `billing_ks`.

Cả hai nhóm đều lưu trong Apache Cassandra. Lập trình viên muốn dùng **entity mapping**, `CassandraRepository`, `CassandraTemplate` và truy vấn CQL thông thường. Nếu tất cả repository tự động dùng cùng một session với keyspace mặc định, truy vấn có thể đi vào **sai bảng/sai keyspace**, thậm chí không khởi động được khi không tìm thấy bảng.

Đây là bài học thuộc chương **Cấu hình kết nối** của **Spring Data Cassandra**: cần hiểu chính xác mối quan hệ giữa **keyspace**, **`CqlSession`**, **`CassandraTemplate`**, **Spring bean** và phạm vi quét repository, rồi chọn chiến lược có chi phí hợp lý.

Sau bài học, bạn cần:

1. Giải thích một Cassandra cluster có thể chứa nhiều keyspace và một session có thể truy vấn bảng ở nhiều keyspace bằng CQL chỉ rõ tên đầy đủ.
2. Biết khi nào nên dùng **một session** và khi nào cần tạo **nhiều session** với cấu hình độc lập.
3. Định danh rõ các bean session/template bằng `@Bean`, `@Qualifier`, `@Primary` khi phù hợp.
4. Liên kết từng nhóm repository với **đúng `CassandraTemplate`** và xác minh bằng test tích hợp.
5. Nhận diện lỗi trùng bean, repository quét nhầm, sai keyspace, sai datacenter và những giới hạn về transaction, paging, consistency khi thao tác nhiều keyspace.

## 2. Bốn lớp cấu hình rất dễ nhầm

| Thành phần | Chịu trách nhiệm | Không nên hiểu nhầm |
| --- | --- | --- |
| **Keyspace Cassandra** | Namespace của bảng, kiểu dữ liệu và cấu hình replication; tương tự vùng tổ chức dữ liệu ở mức schema nhưng có đặc thù Cassandra | Không phải một máy chủ riêng hoặc một kết nối TCP riêng |
| **`CqlSession` (Java driver)** | Kết nối đến cluster, quản lý metadata, connection pools, execution profile; có thể có **default keyspace** | Mỗi keyspace không bắt buộc phải có một session |
| **`CassandraTemplate` / `CassandraOperations`** | API Spring Data thực thi CQL và mapping đối tượng qua session/converter | Tạo thêm template không tự sửa keyspace trong các entity hoặc repository |
| **`CassandraRepository`** | Repository domain được triển khai qua `CassandraOperations` mà Spring gắn cho nhóm repository | Interface repository tự nó không quyết định kết nối nào được dùng |

Một **Spring bean** là đối tượng được Spring quản lý. Nếu có hai bean cùng loại `CqlSession` hoặc `CassandraTemplate`, Spring không nhất thiết biết bean nào phải tiêm vào chỗ yêu cầu **một** đối tượng loại đó.

~~~mermaid
flowchart TB
    A[CatalogRepository] -->|cassandraTemplateRef| B[catalogTemplate]
    C[BillingRepository] -->|cassandraTemplateRef| D[billingTemplate]
    B --> E[catalogSession]
    D --> F[billingSession]
    E -->|default keyspace: catalog_ks| G[(Cassandra cluster)]
    F -->|default keyspace: billing_ks| G
    G --> H[(catalog_ks)]
    G --> I[(billing_ks)]
~~~

Sơ đồ minh họa **phương án hai session**. Khi cả hai keyspace cùng cluster, ta cũng có thể dùng **một session** cho các câu CQL chỉ rõ `keyspace.table`. Quyết định cuối cùng tùy cách truy cập và giới hạn vận hành.

## 3. Một keyspace khác một cluster như thế nào?

Trong một cluster Cassandra, có thể tạo nhiều keyspace:

~~~sql
-- Chỉ minh họa trên cluster thử nghiệm có DC tên dc1.
-- Với RF = 3 cần topology/replica phù hợp.
CREATE KEYSPACE catalog_ks
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE KEYSPACE billing_ks
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE catalog_ks.products_by_id (
    product_id uuid PRIMARY KEY,
    name text,
    price_cents bigint
);

CREATE TABLE billing_ks.invoices_by_id (
    invoice_id uuid PRIMARY KEY,
    amount_cents bigint,
    state text
);
~~~

**`dc1` là tên datacenter giả định**, phải khớp tên thực tế Cassandra công bố. Ví dụ RF = 3 yêu cầu cluster thử nghiệm có đủ node phù hợp; với môi trường một node, hãy tạo keyspace với replication phù hợp cho bài thực hành, không sao chép nguyên RF = 3 rồi coi đó là cấu hình sẵn sàng sản xuất.

Nhận xét:

- Hai keyspace **có thể cùng dùng một cluster và những node vật lý như nhau**.
- Mỗi keyspace có cấu hình **replication strategy/factor** riêng, và có thể có quyền truy cập riêng.
- Một bảng được định danh đầy đủ bởi **`keyspace.table`**; `catalog_ks.products_by_id` khác `billing_ks.products_by_id`.
- Mỗi bảng vẫn phải thiết kế **partition key theo mẫu truy vấn**. Tách keyspace không làm truy vấn `ALLOW FILTERING` hoặc quét toàn bộ bảng trở nên hiệu quả.
- **Keyspace khác cluster:** nếu hai nhóm dữ liệu thực sự ở **hai cluster khác nhau**, không thể dùng một session để tự động định tuyến qua cả hai cluster.

## 4. Chọn một hay nhiều session?

| Tình huống | Phương án thường phù hợp | Lý do |
| --- | --- | --- |
| Cùng cluster, cùng thông tin kết nối/xác thực, thỉnh thoảng cần đọc thêm keyspace khác bằng CQL | **Một `CqlSession`**, CQL ghi rõ `keyspace.table` | Ít pool kết nối, ít tài nguyên và đơn giản hơn |
| Cùng cluster, nhiều nhóm repository với các keyspace mặc định khác nhau | **Các template/session đặt tên rõ ràng**, hoặc một session với mapping keyspace được cấu hình và kiểm chứng theo phiên bản | Giảm nhầm lẫn phạm vi mapping và repository |
| Hai cluster độc lập | **Nhiều `CqlSession`** | Mỗi session khám phá một cluster và có vòng đời/metadata riêng |
| Khác account/TLS/authentication hoặc profile vận hành cần cô lập | Thường **nhiều session** | Không nên giả định một session có thể thay đổi danh tính kết nối an toàn cho từng request |
| Một keyspace **riêng cho mỗi tenant**, số tenant lớn và thường xuyên thay đổi | **Xem lại kiến trúc trước khi tạo một session cho mỗi tenant** | Quá nhiều session làm tăng kết nối, bộ nhớ và chi phí quản lý |

**Nguyên tắc thực hành:** `CqlSession` được thiết kế để **tái sử dụng và an toàn khi gọi đồng thời**. Một session thường có nhiều kết nối được driver quản lý. Không tạo session mới cho từng lời gọi repository, request HTTP hoặc mỗi câu CQL.

### 4.1. Một session có thể dùng nhiều keyspace

Giả sử session đã kết nối tới cluster và có quyền đọc ở cả hai keyspace:

~~~java
try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .withKeyspace(CqlIdentifier.fromCql("catalog_ks"))
        .build()) {

    // Dù default keyspace là catalog_ks,
    // vẫn có thể đọc bảng ở billing_ks khi CQL chỉ rõ tên đầy đủ.
    PreparedStatement ps = session.prepare(
        "SELECT amount_cents, state " +
        "FROM billing_ks.invoices_by_id WHERE invoice_id = ?");
    Row row = session.execute(ps.bind(invoiceId)).one();
}
~~~

Ví dụ sử dụng **Java driver 4.x**, cần import `CqlSession`, `CqlIdentifier`, `PreparedStatement`, `Row` và `InetSocketAddress`, đồng thời cung cấp biến `invoiceId`. `try-with-resources` dùng cho ví dụ **driver độc lập**; khi Spring tạo session thành bean, để Spring quản lý việc đóng session.

Đặt default keyspace thành `catalog_ks` chỉ quyết định cách hiểu những bảng **không chỉ rõ keyspace** trong CQL/mapping phù hợp. Nó **không giới hạn** session vào một namespace, nếu tài khoản có quyền và CQL chỉ rõ tên đầy đủ. Tránh thay default keyspace ở giữa các request bằng cách gửi `USE other_keyspace`: session và connection pools dùng chung khiến việc dựa vào trạng thái keyspace biến đổi gây khó dự đoán. Hãy chỉ rõ `keyspace.table` hoặc thiết kế cấu hình truy cập tách biệt.

### 4.2. Khi nào không nên cố ép một session cho mọi repository?

Repository hoạt động từ metadata mapping của entity và `CassandraOperations` được chỉ định. Nếu hai nhóm entity khai báo tên bảng **không kèm keyspace**, cả hai nhóm có thể sử dụng default keyspace giống nhau khi đặt trên cùng template/session. Đó là nguồn gây lỗi khi copy repository từ module này sang module khác.

Một số phiên bản Spring Data Cassandra hỗ trợ định danh keyspace qua metadata mapping hoặc cấu hình riêng; nếu dùng khả năng đó, **phải kiểm chứng trên chính phiên bản thư viện của dự án** bằng test tích hợp. Phần tiếp theo chọn phương án **hai session, hai template, hai phạm vi repository** để minh họa ranh giới rõ ràng.

## 5. Mặc định Spring Boot: một session và một template

Với một keyspace, các thế hệ Spring Boot sử dụng nhóm cấu hình `spring.cassandra.*` có thể cấu hình:

~~~yaml
spring:
  cassandra:
    contact-points:
      - 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: catalog_ks
~~~

Spring Boot có thể tự cấu hình hạ tầng truy cập Cassandra và repository khi dependency tương ứng tồn tại và các điều kiện auto-configuration được đáp ứng. Trong cách dùng đơn giản này, code chỉ cần inject `CassandraOperations` hoặc khai báo repository.

**Khi chuyển sang nhiều session tự quản lý**, cần xem lại những auto-configuration có đang tạo session/template/repository mặc định hay không. Không nên vừa để quét tất cả repository mặc định, vừa khai báo hai nhóm `@EnableCassandraRepositories` quét chồng lên nhau. Các lựa chọn bật/tắt auto-configuration, tiền tố property và cách xây converter thay đổi theo dòng Spring Boot/Spring Data; hãy giữ một chiến lược rõ ràng cho phiên bản đang sử dụng.

> Chú ý phiên bản: Spring Boot 3.x thường dùng `spring.cassandra.*`; nhiều ứng dụng Spring Boot 2.x dùng `spring.data.cassandra.*`. Những ví dụ Java phía dưới minh họa Spring Data Cassandra dùng Java driver 4.x và cần xác minh API với phiên bản project trước khi áp dụng nguyên mẫu.

## 6. Tạo hai session và hai CassandraTemplate bằng bean có tên

Trong cùng một cluster thử nghiệm `dc1`, ta chủ động tạo các bean:

| Tên bean | Kiểu | Keyspace mặc định | Dùng cho |
| --- | --- | --- | --- |
| `catalogSession` | `CqlSession` | `catalog_ks` | Catalog |
| `catalogTemplate` | `CassandraTemplate` | Theo `catalogSession` | Truy cập/mapping Catalog |
| `billingSession` | `CqlSession` | `billing_ks` | Billing |
| `billingTemplate` | `CassandraTemplate` | Theo `billingSession` | Truy cập/mapping Billing |

Ví dụ minh họa trong một lớp cấu hình Java:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.CassandraTemplate;

@Configuration(proxyBeanMethods = false)
public class MultiKeyspaceCassandraConfig {

    // Dùng chung contact point/DC vì ví dụ có hai keyspace trên một cluster.
    // Ứng dụng thực tế nên lấy host, port, DC và keyspace từ cấu hình triển khai.
    private CqlSession openSession(String keyspace) {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .withKeyspace(CqlIdentifier.fromCql(keyspace))
            .build();
    }

    @Bean(name = "catalogSession", destroyMethod = "close")
    public CqlSession catalogSession() {
        return openSession("catalog_ks");
    }

    @Bean(name = "billingSession", destroyMethod = "close")
    public CqlSession billingSession() {
        return openSession("billing_ks");
    }

    @Bean(name = "catalogTemplate")
    public CassandraTemplate catalogTemplate(
            @Qualifier("catalogSession") CqlSession session) {
        return new CassandraTemplate(session);
    }

    @Bean(name = "billingTemplate")
    public CassandraTemplate billingTemplate(
            @Qualifier("billingSession") CqlSession session) {
        return new CassandraTemplate(session);
    }
}
~~~

**Ý nghĩa:**

1. `@Bean(name = "...")` đặt tên ổn định cho từng đối tượng trong Spring context.
2. `@Qualifier("catalogSession")` ràng buộc template Catalog với session Catalog, tránh chọn nhầm session có cùng kiểu.
3. `destroyMethod = "close"` giúp Spring đóng session khi context kết thúc.
4. Hai session có **connection pools và metadata riêng**, dù cùng kết nối tới một cluster; đây là chi phí có thật cần cân nhắc.
5. Ví dụ dùng constructor `CassandraTemplate(CqlSession)` cho mapping cơ bản. Nếu có **custom conversions, entity callbacks, converter, mapping context hoặc cấu hình schema phức tạp**, cần gắn đầy đủ hạ tầng mapping tương ứng cho từng template và kiểm tra tương thích với phiên bản đang dùng.

Các keyspace phải **tồn tại trước khi khởi tạo session** với `withKeyspace(...)`; tài khoản Cassandra phải có quyền tương ứng. Đoạn cấu hình trên chỉ để minh họa ranh giới bean. Với môi trường thực, không hard-code endpoint/mật khẩu; sử dụng properties/secret manager và cấu hình TLS, authentication, timeout, local DC thích hợp.

### 6.1. Tại sao không dùng @Primary cho cả hai?

Nếu có hai bean `CqlSession`, một chỗ inject:

~~~java
// Không chỉ rõ bean nào:
public SomeService(CqlSession session) {
    // ...
}
~~~

có thể gặp `NoUniqueBeanDefinitionException` khi Spring không xác định được ứng viên duy nhất. Một số cách xử lý:

- **`@Qualifier("billingSession")`:** rõ ràng và phù hợp nhất khi code biết chính xác keyspace/nhóm nghiệp vụ cần dùng.
- **`@Primary` trên đúng một bean:** chỉ hợp lý khi có một kết nối mặc định được thừa nhận rộng rãi. Inject theo loại sẽ chọn bean primary; những vị trí khác vẫn nên dùng `@Qualifier`.
- **Inject `Map<String, CqlSession>`:** chỉ phù hợp với thành phần điều phối thật sự cần quản lý nhiều kết nối; phải xác thực tên/khóa lựa chọn trước khi sử dụng.

Không gắn `@Primary` cho cả hai session cùng loại, không dựa vào thứ tự bean được đăng ký và không đổi tên bean ngẫu nhiên để “xử lý” lỗi injection.

## 7. Gắn đúng repository với đúng template

Giả sử các repository được tổ chức trong **hai package riêng**:

~~~text
com.example.catalog.repository
  ProductRepository

com.example.billing.repository
  InvoiceRepository
~~~

Khai báo cấu hình quét repository cho từng nhóm. Hai lớp cấu hình dưới đây được đặt trong **hai tệp Java riêng**, mỗi lớp quản lý đúng package repository của mình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.repository.config.EnableCassandraRepositories;

@Configuration(proxyBeanMethods = false)
@EnableCassandraRepositories(
    basePackages = "com.example.catalog.repository",
    cassandraTemplateRef = "catalogTemplate"
)
public class CatalogRepositoryConfig {
}

@Configuration(proxyBeanMethods = false)
@EnableCassandraRepositories(
    basePackages = "com.example.billing.repository",
    cassandraTemplateRef = "billingTemplate"
)
public class BillingRepositoryConfig {
}
~~~

`cassandraTemplateRef` tham chiếu **tên bean của template**, không phải tên keyspace hoặc tên session. Nếu vô tình viết `cassandraTemplateRef = "billingSession"`, Spring không nhận được bean thao tác dữ liệu cần thiết cho repository.

Các interface repository có thể trông rất giống nhau:

~~~java
// Nằm trong package com.example.catalog.repository
public interface ProductRepository
        extends CassandraRepository<Product, UUID> {
}

// Nằm trong package com.example.billing.repository
public interface InvoiceRepository
        extends CassandraRepository<Invoice, UUID> {
}
~~~

Đây là ví dụ rút gọn: cần import `CassandraRepository`, `UUID` và định nghĩa các entity `Product`/`Invoice` ánh xạ bảng thích hợp. Với entity cơ bản:

~~~java
@Table("products_by_id")
public class Product {
    @PrimaryKey("product_id")
    private UUID productId;

    @Column("name")
    private String name;

    @Column("price_cents")
    private Long priceCents;

    // Constructors, getters/setters, equals/hashCode khi thích hợp.
}
~~~

Ở đây bảng được gọi tên `products_by_id` **không kèm keyspace** trong entity. Nhóm repository Catalog dùng `catalogTemplate` và session có default keyspace `catalog_ks`; tương tự nhóm Billing dùng `billing_ks`. Nếu entity ánh xạ keyspace cụ thể hoặc dùng truy vấn `@Query` có tên `keyspace.table`, phải kiểm tra chúng nhất quán với cấu hình repository.

**Quy tắc tránh quét trùng:** package của hai nhóm không chồng nhau, và cơ chế tự động tìm repository của Spring Boot không đăng ký lặp cùng interface với cấu hình quét thủ công. Khi dự án có nhiều module, nên dùng cấu trúc package hoặc `basePackageClasses` theo lớp marker phù hợp để tránh thay đổi package âm thầm làm lẫn phạm vi.

## 8. Phân biệt bean khi dùng CassandraTemplate trong service

Nếu service cần thực thi truy vấn bằng template, inject qua interface `CassandraOperations` và tên bean rõ ràng:

~~~java
import java.util.UUID;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.stereotype.Service;

@Service
public class CatalogReadService {
    private final CassandraOperations catalogOps;

    public CatalogReadService(
            @Qualifier("catalogTemplate") CassandraOperations catalogOps) {
        this.catalogOps = catalogOps;
    }

    public Product findProduct(UUID productId) {
        return catalogOps.selectOneById(productId, Product.class);
    }
}
~~~

`selectOneById(...)` minh họa thao tác ánh xạ entity theo ID; method và mapping cần phù hợp phiên bản Spring Data Cassandra. Trường hợp có bean template Catalog lẫn Billing, Spring chọn bean dựa trên **`@Qualifier`** trong constructor, không dựa vào việc tham số được đặt tên `catalogOps`.

Nếu một service thực sự cần cả hai:

~~~java
@Service
public class ConsolidatedService {
    private final CassandraOperations catalog;
    private final CassandraOperations billing;

    public ConsolidatedService(
            @Qualifier("catalogTemplate") CassandraOperations catalog,
            @Qualifier("billingTemplate") CassandraOperations billing) {
        this.catalog = catalog;
        this.billing = billing;
    }

    // Ghép kết quả theo nghiệp vụ ở Java; Cassandra không JOIN xuyên keyspace.
}
~~~

**Lưu ý thiết kế:** nếu giao dịch nghiệp vụ cần đọc Catalog rồi ghi Billing, đây là **hai thao tác có thể thất bại độc lập**. Inject cả hai template không mang lại transaction toàn cục. Cần xử lý retry, idempotency, trạng thái trung gian và đối soát dữ liệu theo yêu cầu nghiệp vụ.

## 9. Những sai lầm khi dùng nhiều keyspace

### 9.1. Dùng một session rồi giả định repository tự chọn keyspace

Nếu `ProductRepository` và `InvoiceRepository` cùng gắn vào một template mặc định mà entity chỉ khai báo `@Table("...")`, một hoặc cả hai có thể truy vấn **sai keyspace**. Đặt đúng tên package chưa đủ; phải ràng buộc repository với template đúng và kiểm tra query thực tế.

### 9.2. Tạo session mới sau mỗi request

Session không phải kết nối dùng một lần. Driver quản lý pool, khám phá topology và cache metadata. Tạo/đóng liên tục làm tăng chi phí kết nối, authentication, chuẩn bị statement và áp lực hạ tầng. Hãy tái sử dụng bean session do Spring quản lý.

### 9.3. Cho rằng hai keyspace có transaction hoặc JOIN như RDBMS

CQL không hỗ trợ JOIN SQL tùy ý giữa hai bảng, kể cả cùng keyspace; ứng dụng thường **thiết kế bảng theo truy vấn** hoặc ghép dữ liệu ở tầng service. **Logged batch** không phải giao dịch ACID có isolation xuyên nhiều partition/keyspace. **LWT** có phạm vi và chi phí riêng; không tự biến hai repository thành một transaction toàn cục. Nếu cần đồng bộ nghiệp vụ giữa Catalog và Billing, hãy xác định rõ mô hình eventual consistency, workflow/saga hoặc lựa chọn cơ sở dữ liệu khác nếu yêu cầu nguyên tử bắt buộc.

### 9.4. Nghĩ session quyết định replication/consistency

Replication strategy/factor được cấu hình ở **keyspace trên Cassandra**. Consistency level được thiết lập theo statement/execution profile hoặc chính sách driver. Session mặc định chọn keyspace nào **không tự thay đổi RF**, cũng không làm mọi truy vấn trở nên nhất quán mạnh. Khi dùng nhiều keyspace, kiểm tra consistency/timeout theo yêu cầu của từng nhóm dữ liệu.

### 9.5. Không kiểm tra paging và schema từng keyspace

Hai repository có thể có kiểu kết quả tương tự nhưng **schema khác nhau**, mapping khác nhau, TTL khác nhau. Khi đọc nhiều trang, paging state gắn với truy vấn/điều kiện cụ thể; không dùng token trang của Catalog cho truy vấn Billing. Thao tác tổng hợp hai nguồn cần quy tắc sắp xếp, trùng lặp và lỗi từng phần riêng ở tầng ứng dụng.

### 9.6. Không tính chi phí của nhiều session

Hai session tới cùng cluster có thể tạo **hai bộ pool kết nối và tài nguyên nền**. Với vài keyspace cố định, chi phí có thể chấp nhận để phân biệt bean rõ ràng; với hàng trăm hoặc hàng nghìn tenant, cách “mỗi tenant một session” dễ làm tăng tiêu thụ tài nguyên và độ phức tạp. Cần đánh giá nhu cầu cô lập thực sự, số lượng session và chính sách kết nối/quan sát.

## 10. Kiểm thử đúng bean, keyspace và quyền truy cập

Lỗi đa keyspace thường không xuất hiện khi chỉ test một repository bằng mock. Cần **kiểm thử tích hợp** với Cassandra thử nghiệm có đúng keyspace/bảng như cấu hình.

### 10.1. Kế hoạch kiểm thử

| Kiểm tra | Hành động | Dấu hiệu đạt |
| --- | --- | --- |
| Bean wiring | Khởi động Spring context với hai session và hai template | Không có `NoUniqueBeanDefinitionException`, bean có đúng tên |
| Default keyspace | Đọc `session.getKeyspace()` của từng bean | Catalog = `catalog_ks`, Billing = `billing_ks` |
| Catalog repository | Ghi/đọc `Product` theo primary key | Hàng tồn tại tại `catalog_ks.products_by_id` |
| Billing repository | Ghi/đọc `Invoice` theo primary key | Hàng tồn tại tại `billing_ks.invoices_by_id` |
| Cô lập đường truy cập | Kiểm tra bảng tương ứng bằng CQL fully qualified | Không có dữ liệu bị ghi nhầm namespace |
| Quyền truy cập | Dùng role tương ứng trên cluster thử nghiệm | Chỉ thao tác được trong phạm vi quyền cấp |
| Lỗi từng phần | Mô phỏng một nhóm thao tác Billing lỗi | Catalog tiếp tục xử lý theo chính sách, Billing ghi log và xử lý retry phù hợp |
| Đóng tài nguyên | Dừng Spring context | Session được Spring đóng, không tạo thêm session rò rỉ |

Ví dụ kiểm tra định danh session trong một test tích hợp:

~~~java
@SpringBootTest
class MultiKeyspaceWiringTest {
    @Autowired
    @Qualifier("catalogSession")
    CqlSession catalogSession;

    @Autowired
    @Qualifier("billingSession")
    CqlSession billingSession;

    @Test
    void sessionsUseExpectedKeyspaces() {
        assertEquals(
            CqlIdentifier.fromCql("catalog_ks"),
            catalogSession.getKeyspace().orElseThrow());
        assertEquals(
            CqlIdentifier.fromCql("billing_ks"),
            billingSession.getKeyspace().orElseThrow());
    }
}
~~~

Đoạn test cần import JUnit 5, Spring Test, driver và static `assertEquals`. Test này chỉ chứng minh **default keyspace của session**, chưa chứng minh repository được gắn đúng template. Phải có thêm test ghi/đọc dữ liệu rồi kiểm tra **bảng được chỉ rõ keyspace** để bắt lỗi mapping hoặc quét repository.

### 10.2. Chẩn đoán nhanh các triệu chứng

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| `NoUniqueBeanDefinitionException` cho `CqlSession` hoặc `CassandraOperations` | Có nhiều bean cùng loại, thiếu `@Qualifier`/một `@Primary` hợp lý |
| Repository không tạo bean | Package không được quét, cấu hình repository chưa kích hoạt, hoặc quét trùng/điều kiện auto-config |
| Repository tìm sai bảng | `cassandraTemplateRef` sai, entity mapping sai, default keyspace không đúng |
| `unconfigured keyspace` hoặc `unconfigured table` | Keyspace/bảng chưa tồn tại, viết sai tên hoặc câu CQL dùng keyspace mặc định không như dự kiến |
| Kết nối đầu tiên thành công, truy vấn sau đó timeout | Các node driver khám phá không thể tiếp cận, local DC sai, network hoặc cluster có vấn đề |
| Một keyspace đọc được, keyspace khác bị `Unauthorized` | Role/privilege khác nhau hoặc session kết nối bằng tài khoản không đủ quyền |
| Tạo nhiều session làm ứng dụng chậm/thiếu tài nguyên | Quá nhiều pool kết nối, driver metadata và luồng nền; xem lại mô hình tái sử dụng |

## 11. Thực hành từng bước

**Bối cảnh:** cluster Cassandra thử nghiệm có hai keyspace `catalog_ks` và `billing_ks`, các bảng `products_by_id` và `invoices_by_id` như ví dụ ở phần 3.

1. **Xác nhận hạ tầng:** chạy CQL truy vấn `system.local` để lấy tên datacenter; kiểm tra keyspace và quyền truy cập. Chỉ chọn RF phù hợp số node của môi trường thử nghiệm.
2. **Kiểm tra một session:** tạo `CqlSession` với default keyspace Catalog; thực hiện truy vấn `SELECT ... FROM billing_ks.invoices_by_id WHERE invoice_id = ?` bằng statement có bind parameter. Giải thích vì sao session vẫn đọc được bảng Billing nếu có quyền.
3. **Định nghĩa bean:** tạo `catalogSession`, `billingSession` và hai template. Khởi động Spring context, dùng `@Qualifier` để inject và kiểm tra `getKeyspace()`.
4. **Giới hạn phạm vi repository:** đưa repository vào hai package riêng, khai báo `@EnableCassandraRepositories` với `cassandraTemplateRef` tương ứng. Kiểm tra không có cơ chế auto-scan quét chồng.
5. **Kiểm thử ghi/đọc:** lưu một Product và một Invoice, xác minh trực tiếp bằng CQL với tên `keyspace.table` đầy đủ; không dựa vào tên repository để suy ra đã vào đúng bảng.
6. **Thử lỗi có chủ ý:** tạm đổi `cassandraTemplateRef` của Catalog sang `billingTemplate`. Quan sát lỗi hoặc kết quả sai, khôi phục cấu hình đúng. Không dùng dữ liệu thật khi thử.
7. **Thử injection mơ hồ:** inject `CqlSession` khi không đặt qualifier. Giải thích vì sao Spring báo nhiều candidate; sửa bằng `@Qualifier` thay vì đặt `@Primary` tùy tiện.
8. **Đánh giá chi phí:** ghi lại số session mở, các kết nối liên quan và nguyên nhân dự án cần tách session. Nếu chỉ thỉnh thoảng đọc chéo keyspace trong cùng cluster, so sánh với một session và CQL fully-qualified.

**Đạt yêu cầu khi** người học giải thích được đầy đủ đường đi:

~~~text
Repository/Service
    -> CassandraTemplate được chọn bởi bean name / @Qualifier
    -> CqlSession của template
    -> default keyspace hoặc keyspace.table trong CQL
    -> coordinator và replica Cassandra
~~~

## 12. Câu hỏi tự kiểm tra

1. Một cluster Cassandra có thể chứa bao nhiêu keyspace và có bắt buộc mở một session cho mỗi keyspace không?
2. `catalog_ks.products_by_id` khác `billing_ks.products_by_id` ở cấp độ định danh nào?
3. Nếu session có default keyspace `catalog_ks`, câu CQL nào cho phép đọc một bảng ở `billing_ks`?
4. Vì sao không nên chạy `USE billing_ks` giữa các request trên session dùng chung?
5. Sự khác nhau giữa `CqlSession`, `CassandraTemplate`, `CassandraOperations` và `CassandraRepository` là gì?
6. `@Bean(name = "billingTemplate")` và `@Qualifier("billingTemplate")` giải quyết những vấn đề nào?
7. `cassandraTemplateRef` của `@EnableCassandraRepositories` cần trỏ tới tên của bean nào?
8. Khi có hai bean `CqlSession` cùng kiểu, `@Primary` có ý nghĩa gì? Khi nào nên ưu tiên `@Qualifier`?
9. Vì sao test `session.getKeyspace()` đạt vẫn chưa đủ để khẳng định BillingRepository đọc đúng keyspace?
10. Vì sao nhiều session làm tăng chi phí dù tất cả cùng trỏ tới một cluster?
11. Nếu hai keyspace cần một thao tác nghiệp vụ chung, Spring có tự tạo transaction ACID xuyên hai keyspace không?
12. Những giới hạn của phân trang, consistency và thiết kế partition key nào vẫn tồn tại khi có nhiều keyspace?

**Kết luận của bài học:** **keyspace** tổ chức dữ liệu, **session** quản lý truy cập cluster, **template** là cổng truy cập Spring Data và **repository** được gắn vào template thông qua cấu hình. Đặt ranh giới bean rõ ràng và kiểm thử đường truy cập bằng CQL đầy đủ là cách quan trọng để tránh nhầm keyspace; lựa chọn một hay nhiều session cần dựa trên nhu cầu cô lập thực tế và chi phí kết nối.
