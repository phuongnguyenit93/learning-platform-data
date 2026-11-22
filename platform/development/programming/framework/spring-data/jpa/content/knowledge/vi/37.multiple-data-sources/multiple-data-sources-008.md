# Mô hình đa khách hàng theo cơ sở dữ liệu, schema hoặc tenant_id

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Nhiều nguồn dữ liệu

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích mô hình multi-tenancy và ranh giới dữ liệu giữa các tenant.
- So sánh ba cách tổ chức: database riêng, schema riêng và shared schema có tenant_id.
- Chọn mô hình phù hợp theo mức cô lập, chi phí vận hành, quy mô tenant và nhu cầu mở rộng.
- Thiết kế cách xác định tenant từ danh tính đã xác thực và truyền tenant context vào tầng persistence.
- Cấu hình định tuyến datasource hoặc schema ở đúng thời điểm của vòng đời transaction.
- Bảo đảm mọi truy vấn, quan hệ, cache và tác vụ nền đều giữ đúng phạm vi tenant.
- Lập kế hoạch migration, provisioning, backup, giám sát và kiểm thử rò rỉ dữ liệu giữa tenant.

## 2. Multi-tenancy là gì?

Multi-tenancy là kiến trúc trong đó một ứng dụng phục vụ nhiều khách hàng hoặc tổ chức (tenant) trên cùng nền tảng. Mỗi tenant có dữ liệu riêng và chỉ được phép truy cập dữ liệu thuộc phạm vi của mình.

Ví dụ một hệ thống quản lý bán hàng SaaS có nhiều công ty sử dụng cùng ứng dụng. Công ty A có người dùng, sản phẩm, đơn hàng và hóa đơn riêng; công ty B cũng có các dữ liệu tương tự nhưng không được đọc hoặc sửa dữ liệu của A.

Tenant có thể được nhận diện bằng tenant ID, tổ chức trong tài khoản, hostname hoặc thông tin định tuyến khác. Tuy nhiên, tenant được dùng để truy cập dữ liệu phải được xác định từ danh tính và quyền đã xác thực ở phía máy chủ. Không được tin một tenant_id tùy ý do client gửi lên mà không kiểm tra người dùng có quyền truy cập tenant đó.

Mục tiêu cốt lõi của multi-tenancy là:

1. **Cô lập dữ liệu:** tenant này không thể đọc, sửa hoặc xóa dữ liệu tenant khác.
2. **Vận hành hiệu quả:** dùng chung ứng dụng, hạ tầng hoặc schema ở mức phù hợp.
3. **Mở rộng:** thêm tenant mà không phải triển khai một hệ thống hoàn toàn mới trong mọi trường hợp.
4. **Quản trị:** có thể áp dụng backup, migration, quota, giám sát và chính sách riêng cho từng tenant.

Multi-tenancy là một quyết định kiến trúc và bảo mật. Chỉ thêm cột tenant_id vào một vài bảng chưa đủ để tạo ra một hệ thống đa tenant an toàn.

## 3. Ba mô hình lưu trữ phổ biến

Có ba cách tổ chức dữ liệu thường gặp:

- **Database per tenant:** mỗi tenant có một database riêng.
- **Schema per tenant:** mỗi tenant có một schema riêng trong cùng database instance.
- **Shared schema:** nhiều tenant dùng chung các bảng; mỗi hàng được gắn tenant_id.

| Tiêu chí | Database riêng | Schema riêng | Shared schema + tenant_id |
|---|---|---|---|
| Ranh giới dữ liệu | Database | Schema | Hàng dữ liệu |
| Cô lập vật lý/logic | Cao | Trung bình đến cao | Phụ thuộc truy vấn và constraint |
| Chi phí tài nguyên | Cao hơn | Trung bình | Thường thấp hơn |
| Định tuyến kết nối | Theo database | Theo schema | Không cần đổi database/schema |
| Migration | Theo từng database | Theo từng schema | Một schema dùng chung |
| Backup/restore riêng tenant | Thuận lợi | Có thể thực hiện theo schema, tùy DB | Khó hơn, cần lọc dữ liệu |
| Truy vấn tổng hợp nhiều tenant | Khó hơn | Khó hơn | Thuận tiện hơn nhưng cần phân quyền |
| Rủi ro quên tenant predicate | Thấp hơn ở cấp query | Thấp hơn nếu schema routing đúng | Rất đáng chú ý |

Không có mô hình tốt nhất cho mọi sản phẩm. Quyết định cần dựa vào yêu cầu cách ly, số tenant, kích thước tenant, chi phí vận hành, khả năng phục hồi và nhu cầu truy vấn liên tenant.

## 4. Database per tenant

Mỗi tenant có database riêng, có thể nằm trên cùng database server hoặc trên các cụm database khác nhau.

Ví dụ:

- tenant A → database tenant_a
- tenant B → database tenant_b
- tenant C → database tenant_c

Ứng dụng xác định tenant hiện tại, sau đó định tuyến kết nối đến datasource tương ứng.

### 4.1. Ưu điểm

- Ranh giới dữ liệu rõ ở cấp database.
- Có thể cấp quyền database riêng và giảm phạm vi ảnh hưởng khi một tenant gặp sự cố.
- Backup, restore, chuyển máy chủ hoặc nâng cấp riêng một tenant dễ tổ chức hơn.
- Tenant lớn có thể được chuyển sang cụm database mạnh hơn mà không cần di chuyển toàn bộ khách hàng.
- Có thể áp dụng cấu hình, quota hoặc lịch bảo trì khác nhau theo tenant.

### 4.2. Nhược điểm

- Cần quản lý nhiều database và thông tin kết nối.
- Pool connection riêng cho từng datasource có thể tiêu thụ nhiều connection và bộ nhớ.
- Migration, backup, monitoring và provisioning phải chạy trên nhiều database.
- Truy vấn tổng hợp trên tất cả tenant phức tạp hơn.
- Việc tạo tenant mới cần tự động hóa để tránh cấu hình thủ công sai lệch.

Khi số tenant tăng lên hàng nghìn, không nên mặc định tạo một pool lớn cho từng tenant. Cần cân nhắc pool dùng chung có định tuyến, pool giới hạn theo nhóm tenant, hoặc cấp phát kết nối theo nhu cầu và chính sách vận hành.

### 4.3. Định tuyến datasource trong Spring

Spring cung cấp AbstractRoutingDataSource để chọn datasource dựa trên một lookup key. Ví dụ dưới đây minh họa cơ chế định tuyến:

~~~java
public final class TenantContext {

    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();

    private TenantContext() {
    }

    public static void setTenantId(String tenantId) {
        CURRENT.set(tenantId);
    }

    public static String getTenantId() {
        return CURRENT.get();
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

Datasource định tuyến:

~~~java
public class TenantRoutingDataSource
        extends AbstractRoutingDataSource {

    @Override
    protected Object determineCurrentLookupKey() {
        String tenantId = TenantContext.getTenantId();

        if (tenantId == null) {
            throw new IllegalStateException(
                    "Tenant context chưa được thiết lập");
        }

        return tenantId;
    }
}
~~~

Khi cấu hình, ứng dụng đăng ký map tenant ID đã được xác thực với datasource tương ứng. Ví dụ:

~~~java
Map<Object, Object> targets = new HashMap<>();
targets.put("tenant-a", dataSourceA);
targets.put("tenant-b", dataSourceB);

routingDataSource.setTargetDataSources(targets);
routingDataSource.setDefaultTargetDataSource(defaultDataSource);
routingDataSource.afterPropertiesSet();
~~~

Đây là các đoạn minh họa cấu hình; trong ứng dụng thật cần tạo datasource, transaction manager và EntityManagerFactory theo cùng một cấu hình nhất quán. Không dùng tenant ID chưa kiểm tra làm tên datasource hoặc thông tin kết nối tùy ý. Nếu tenant không có trong registry, nên từ chối request thay vì rơi về database mặc định chứa dữ liệu của tenant khác.

### 4.4. Tenant context phải có trước khi lấy connection

Routing datasource chọn database tại thời điểm lấy connection. Vì vậy tenant context phải được thiết lập trước khi transaction bắt đầu và trước khi EntityManager lấy connection.

Nếu một transaction đã lấy connection của tenant A, việc đổi ThreadLocal sang tenant B ở giữa transaction không tự chuyển connection sang database B. Không được đổi tenant trong một transaction đang hoạt động.

Trong web request, tenant context thường được thiết lập ở filter/interceptor sau khi xác thực và kiểm tra membership. Sau đó Service mới chạy transaction. Cuối request phải xóa context trong finally:

~~~java
try {
    TenantContext.setTenantId(authorizedTenantId);
    filterChain.doFilter(request, response);
} finally {
    TenantContext.clear();
}
~~~

Đoạn code là phần minh họa bên trong filter; authorizedTenantId phải đến từ bước xác thực và kiểm tra quyền, không lấy trực tiếp từ một header chưa tin cậy.

Với tác vụ async, executor hoặc message consumer, ThreadLocal không tự truyền sang thread khác. Phải truyền tenant ID trong message/job context đã được xác thực, thiết lập context ở đầu tác vụ và xóa trong finally. Không để thread pool tái sử dụng thread với tenant context còn sót lại.

## 5. Schema per tenant

Mỗi tenant dùng một schema riêng trong cùng database instance. Ví dụ:

- tenant A → schema tenant_a
- tenant B → schema tenant_b

Các schema có thể chứa cùng tên bảng như customer, product, orders nhưng dữ liệu nằm trong namespace riêng.

### 5.1. Ưu điểm và nhược điểm

Ưu điểm:

- Cô lập dữ liệu rõ hơn shared schema ở cấp schema.
- Dùng chung một database instance và có thể dùng chung hạ tầng connection pool.
- Có thể backup/restore hoặc cấp quyền theo schema tùy khả năng database.
- Có thể migration từng tenant hoặc theo nhóm tenant.

Nhược điểm:

- Vẫn phải quản lý số lượng schema lớn.
- Mỗi schema cần được tạo, nâng cấp và kiểm tra đồng bộ.
- Định tuyến schema sai có thể khiến ứng dụng đọc nhầm dữ liệu.
- Một số database có giới hạn hoặc chi phí quản lý schema đáng kể.
- Việc truy vấn liên schema và backup riêng phụ thuộc database.

### 5.2. Chuyển schema theo connection

Có thể cấu hình schema trên connection khi lấy connection, ví dụ qua Connection.setSchema(schemaName) nếu driver/database hỗ trợ. Một số hệ quản trị có cơ chế riêng như search_path.

Phải bảo đảm schema name được lấy từ registry tenant đáng tin cậy và ánh xạ từ tenant ID đã xác thực. Không nối chuỗi trực tiếp một header client vào SQL như SET search_path TO <giá trị client>.

Connection pool tái sử dụng connection. Vì vậy, schema được thiết lập cho một request phải được reset về trạng thái an toàn khi connection trả về pool hoặc được thiết lập lại chắc chắn mỗi lần mượn connection. Nếu connection của tenant A được tái sử dụng cho tenant B mà schema cũ còn sót, dữ liệu có thể bị truy cập nhầm.

Cần kiểm thử cả đường lấy connection, trả connection, transaction rollback và tái sử dụng connection trong pool.

### 5.3. Hibernate multi-tenancy

Hibernate có cơ chế multi-tenancy hỗ trợ định danh tenant và cung cấp connection phù hợp. Tùy phiên bản Hibernate, các thành phần thường gặp gồm:

- CurrentTenantIdentifierResolver: xác định tenant hiện tại cho Session.
- MultiTenantConnectionProvider: cung cấp và giải phóng connection phù hợp với tenant.
- Cấu hình multi-tenancy và chiến lược tương ứng với database/schema.

Tên API và cách cấu hình có thể khác giữa các phiên bản Hibernate. Hãy dùng tài liệu đúng phiên bản đang được Spring Boot quản lý; không sao chép cấu hình Hibernate 5 sang Hibernate 6 hoặc ngược lại mà chưa kiểm tra.

Khi dùng Hibernate native multi-tenancy, tenant identifier cần được thiết lập trước khi mở Session/EntityManager. Một transaction/session thông thường chỉ làm việc với một tenant. Truy cập nhiều tenant trong cùng một nghiệp vụ cần thiết kế riêng, không đổi tenant tùy tiện giữa các repository call.

## 6. Shared schema với tenant_id

Tất cả tenant dùng chung bảng. Mỗi bản ghi thuộc tenant nào được xác định bằng cột tenant_id.

Ví dụ:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uq_customer_tenant_code
        UNIQUE (tenant_id, name)
);
~~~

Dữ liệu có thể trông như sau:

| id | tenant_id | name |
|---:|---|---|
| 1 | tenant-a | Công ty An |
| 2 | tenant-b | Công ty Bình |
| 3 | tenant-a | Chi nhánh Hà Nội |

ID có thể duy nhất toàn bảng, nhưng các quy tắc duy nhất trong nghiệp vụ thường phải bao gồm tenant_id. Ví dụ hai tenant có thể cùng dùng mã khách hàng KH001, do đó unique constraint nên là (tenant_id, customer_code) thay vì chỉ customer_code.

### 6.1. Mapping entity

~~~java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customer_tenant_code",
        columnNames = {"tenant_id", "customer_code"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "customer_code", nullable = false)
    private String customerCode;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }
}
~~~

tenantId cần được gán từ tenant context đã xác thực ở phía server. Không cho client tự quyết định tenantId khi tạo hoặc cập nhật entity. Thuộc tính updatable = false giúp Hibernate không đưa cột này vào câu UPDATE thông thường sau khi entity được tạo, nhưng đây không phải hàng rào bảo mật hoàn chỉnh. Cần kiểm soát setter, service, query và constraint ở database.

### 6.2. Repository phải giới hạn tenant

Một cách rõ ràng là đưa tenant ID vào tên phương thức hoặc điều kiện query:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByTenantIdAndId(
            String tenantId,
            Long id);

    List<Customer> findAllByTenantId(
            String tenantId);
}
~~~

Service lấy tenant từ context phía server:

~~~java
@Transactional(readOnly = true)
public Customer getCustomer(Long id) {
    String tenantId = TenantContext.getTenantId();

    return customerRepository
            .findByTenantIdAndId(tenantId, id)
            .orElseThrow(() ->
                    new EntityNotFoundException("Không tìm thấy khách hàng"));
}
~~~

Không nên viết findById(id) cho dữ liệu tenant-scoped rồi chỉ kiểm tra quyền ở giao diện. Client có thể thay ID trong URL và truy cập bản ghi tenant khác nếu Service không giới hạn truy vấn.

Mọi thao tác cần phạm vi tenant:

- findById, findAll, existsById và count.
- update/delete theo ID.
- JPQL, native SQL, specification và Querydsl.
- join tới entity tenant-scoped khác.
- bulk update/delete và batch job.
- export, báo cáo và truy vấn phân trang.

### 6.3. Khóa ngoại cũng cần bảo vệ ranh giới tenant

Chỉ lọc bảng cha theo tenant chưa đủ nếu một hàng con có thể tham chiếu đến hàng cha thuộc tenant khác.

Ví dụ OrderLine có order_id và tenant_id. Có thể thiết kế khóa duy nhất ghép trên bảng orders:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_tenant_id
UNIQUE (tenant_id, id);
~~~

Sau đó dùng khóa ngoại ghép:

~~~sql
ALTER TABLE order_line
ADD CONSTRAINT fk_order_line_tenant_order
FOREIGN KEY (tenant_id, order_id)
REFERENCES orders (tenant_id, id);
~~~

Như vậy database cũng ngăn một OrderLine của tenant A tham chiếu đến Order của tenant B, kể cả khi code ứng dụng có lỗi. Cần điều chỉnh cú pháp và kiểu cột theo database cụ thể.

### 6.4. Index nên tính đến tenant_id

Truy vấn tenant-scoped thường có dạng:

~~~sql
SELECT id, customer_code, name
FROM customer
WHERE tenant_id = ?
  AND customer_code = ?;
~~~

Index ghép (tenant_id, customer_code) thường phù hợp với mẫu truy vấn này. Với bảng lớn, thứ tự cột index phải dựa trên điều kiện lọc, selectivity, sort và workload thực tế. Không thêm tenant_id vào mọi index một cách máy móc; hãy xem execution plan và đo.

## 7. Dùng tính năng discriminator của Hibernate

Hibernate có hỗ trợ multi-tenancy theo discriminator trong một số phiên bản, trong đó entity có thể được gắn tenant identifier bằng annotation riêng của Hibernate như @TenantId.

Đây là tính năng của Hibernate, không phải annotation chuẩn Jakarta Persistence. Cách bật, lấy tenant identifier và áp dụng với query phụ thuộc phiên bản Hibernate và cấu hình SessionFactory. Nếu dùng, phải xác minh:

- Tenant identifier được resolve từ context đã xác thực.
- Mọi entity thuộc phạm vi tenant được mapping đúng.
- Native SQL, bulk query và các đường truy cập đặc biệt có giữ được isolation.
- Migration và unique/foreign key constraint vẫn bảo vệ tenant.
- Cache và truy vấn có tenant awareness.
- Các test cố tình truy cập chéo tenant đều bị chặn.

Với dự án chưa dùng Hibernate discriminator, repository method có tenant predicate tường minh là cách dễ đọc và dễ kiểm tra. Dù dùng cơ chế tự động, không được coi annotation là lý do để bỏ qua review bảo mật của native query, job nền và đường truy cập ngoài ORM.

## 8. Xác định tenant an toàn từ request

Một request có thể chứa hostname, path hoặc header biểu thị tenant. Những giá trị này chỉ là đầu mối để tìm tenant, không tự chứng minh người dùng được phép truy cập tenant đó.

Một flow an toàn thường là:

1. Xác thực người dùng hoặc service principal.
2. Xác định tenant được yêu cầu từ domain, route hoặc lựa chọn hợp lệ.
3. Kiểm tra danh tính có membership/permission trong tenant đó.
4. Gắn tenant ID chuẩn hóa vào request context.
5. Tầng Service và persistence chỉ dùng tenant ID từ context tin cậy.
6. Xóa context sau khi request kết thúc.

Nếu người dùng có quyền ở nhiều tenant, việc chọn tenant hiện hành phải được xác thực theo danh sách membership. Không để client gửi tenant_id bất kỳ rồi truy vấn trực tiếp.

Cũng cần tránh lộ sự tồn tại của dữ liệu tenant khác qua thông báo lỗi. Với tài nguyên ngoài phạm vi, nhiều API chọn trả 404 thay vì phân biệt rõ bản ghi không tồn tại và bản ghi tồn tại ở tenant khác. Chính sách phản hồi cần nhất quán.

## 9. Transaction và nhiều tenant

Một transaction JPA thông thường nên làm việc với một tenant duy nhất. Tenant context phải ổn định từ lúc transaction lấy connection cho tới khi transaction hoàn tất.

Không làm các việc sau trong cùng transaction:

- Bắt đầu transaction dưới tenant A rồi đổi context sang tenant B.
- Gọi Repository của tenant khác nhưng vẫn dùng EntityManager/connection của tenant A.
- Để một async task kế thừa nhầm tenant context của thread gọi.
- Dùng một transaction manager cục bộ rồi giả định nó commit nguyên tử trên nhiều database độc lập.

Nếu một nghiệp vụ cần tác động nhiều tenant hoặc nhiều database, phải thiết kế quy trình riêng. Các lựa chọn có thể gồm điều phối tuần tự từng transaction, outbox, saga và thao tác bù trừ. JTA/XA chỉ phù hợp khi hạ tầng và database hỗ trợ, đồng thời chấp nhận chi phí vận hành của giao dịch phân tán.

Không nên mở rộng một transaction đơn lẻ để giữ khóa trên nhiều tenant trong thời gian dài.

## 10. Cache trong hệ thống multi-tenant

Cache là một nơi dễ xảy ra rò rỉ dữ liệu nếu cache key không chứa tenant.

Ví dụ key nguy hiểm:

~~~java
@Cacheable(cacheNames = "customer", key = "#id")
public CustomerDto getCustomer(Long id) {
    // ...
}
~~~

Nếu tenant A và tenant B đều có ID 10 trong phạm vi riêng, cache key chỉ là 10 có thể trả dữ liệu của tenant này cho tenant kia.

Key phải chứa tenant identifier:

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "T(com.example.TenantContext).getTenantId() + ':' + #id"
)
public CustomerDto getCustomer(Long id) {
    // ...
}
~~~

Cú pháp biểu thức cần phù hợp package và cấu hình Spring Cache của dự án. Có thể dùng một key generator riêng để chuẩn hóa và kiểm tra tenant ID.

Cần rà soát:

- Spring Cache key có tenant ID không?
- Cache region có tách tenant hay dùng chung nhưng key được namespace đúng?
- Eviction khi cập nhật/xóa có đúng tenant và đúng key?
- Hibernate second-level/query cache có hoạt động tenant-aware theo cấu hình không?
- Dữ liệu global và dữ liệu tenant-scoped có được phân biệt rõ?
- Cache phân tán có tránh va chạm key giữa các ứng dụng hoặc môi trường không?

Không cache object chứa dữ liệu tenant nếu không thể chứng minh key và invalidation giữ đúng ranh giới.

## 11. Migration và provisioning tenant

### 11.1. Shared schema

Shared schema thường có một migration áp dụng cho toàn bộ bảng. Khi thêm tenant_id vào một bảng đã có dữ liệu, không nên lập tức thêm cột NOT NULL nếu chưa có giá trị cho các hàng cũ.

Một quy trình nhiều bước có thể là:

1. Thêm tenant_id cho phép null.
2. Backfill tenant_id cho từng hàng dựa trên nguồn dữ liệu đã xác minh.
3. Kiểm tra không còn hàng thiếu hoặc gán nhầm tenant.
4. Tạo index và unique constraint có tenant_id.
5. Chuyển ứng dụng sang truy vấn tenant-scoped.
6. Thêm NOT NULL và constraint ghép sau khi dữ liệu hợp lệ.

Nếu dữ liệu cũ không có thông tin để xác định tenant, cần giải quyết mapping nghiệp vụ trước khi backfill. Không gán tất cả dữ liệu cho một tenant mặc định chỉ để migration chạy qua.

### 11.2. Database per tenant và schema per tenant

Migration cần được áp dụng trên từng database hoặc schema. Registry tenant nên theo dõi phiên bản schema, trạng thái provisioning, database/schema đích và thời điểm migration gần nhất.

Khi tạo tenant mới, quy trình có thể:

1. Tạo database hoặc schema theo template đã kiểm soát.
2. Cấp quyền và thông tin kết nối.
3. Chạy toàn bộ migration theo thứ tự.
4. Kiểm tra schema version và health check.
5. Đăng ký tenant vào registry.
6. Cho phép tenant nhận traffic sau khi provisioning thành công.

Không đưa tenant vào trạng thái active trước khi database/schema đã sẵn sàng.

### 11.3. Triển khai rolling deployment

Khi nhiều phiên bản ứng dụng chạy đồng thời, migration nên tương thích với phiên bản cũ trong giai đoạn chuyển tiếp. Dùng chiến lược expand-contract:

- Expand: thêm cột/bảng mới theo cách phiên bản cũ vẫn hoạt động.
- Migrate data: backfill hoặc đồng bộ dữ liệu.
- Switch: triển khai code đọc/ghi cấu trúc mới.
- Contract: xóa cấu trúc cũ ở lần phát hành sau khi không còn instance phụ thuộc.

Với nhiều tenant, cần có báo cáo tenant nào đã migration thành công, tenant nào đang chờ và cách retry an toàn.

## 12. Backup, restore và vận hành

Mô hình lưu trữ ảnh hưởng trực tiếp đến phục hồi dữ liệu:

- Database per tenant: thuận lợi hơn cho backup/restore một tenant, nhưng cần quản lý nhiều bản backup.
- Schema per tenant: có thể backup/restore theo schema nếu database hỗ trợ và quy trình được kiểm thử.
- Shared schema: restore riêng một tenant phức tạp hơn vì nhiều tenant nằm trong cùng bảng; có thể cần export/import theo tenant ID hoặc phục hồi vào môi trường tạm rồi lọc dữ liệu.

Ngoài backup, cần theo dõi:

- Số tenant active và trạng thái provisioning.
- Database/schema version của từng tenant.
- Connection pool usage theo tenant hoặc nhóm tenant.
- Query chậm, lock, deadlock và lỗi connection.
- Dung lượng dữ liệu và tốc độ tăng trưởng từng tenant.
- Cache hit/miss và eviction theo namespace.
- Tỷ lệ lỗi authorization và truy cập tenant không hợp lệ.

Với database per tenant, tránh để một tenant có tải lớn chiếm toàn bộ connection pool hoặc tài nguyên database. Có thể đặt quota, giới hạn concurrency và tách tenant lớn sang hạ tầng riêng.

## 13. Kiểm thử isolation giữa tenant

Kiểm thử multi-tenancy phải chứng minh tenant A không thể truy cập dữ liệu tenant B, kể cả khi biết ID bản ghi.

Một bộ kiểm thử tích hợp nên có ít nhất hai tenant với dữ liệu có ID hoặc business key dễ trùng. Kiểm tra:

1. Tenant A đọc được bản ghi của A.
2. Tenant B đọc được bản ghi của B.
3. Tenant A không đọc được ID của B.
4. Tenant A không sửa hoặc xóa được bản ghi của B.
5. Danh sách, count và phân trang không trộn dữ liệu.
6. Join, native query và bulk update không bỏ qua tenant scope.
7. Cache không trả kết quả chéo tenant.
8. Tenant context được xóa sau request và không rò qua thread pool.
9. Transaction rollback không để lại dữ liệu ở tenant khác.
10. Migration và provisioning tạo đúng cấu trúc cho tenant mới.

Với shared schema, có thể thêm kiểm thử constraint ghép để database từ chối quan hệ chéo tenant. Nếu dùng PostgreSQL Row-Level Security (RLS), cần kiểm tra policy với đúng database role mà ứng dụng sử dụng; owner hoặc role có quyền bypass có thể không chịu cùng policy như user runtime thông thường.

Testcontainers giúp chạy loại database gần production, kiểm thử migration, foreign key, schema routing và RLS. H2 có thể hữu ích cho một số test nhanh nhưng không thay thế kiểm thử trên database thật khi dự án phụ thuộc tính năng riêng của database.

## 14. So sánh và chọn mô hình

### Chọn database per tenant khi

- Khách hàng yêu cầu cách ly mạnh hoặc có yêu cầu hợp đồng/quy định riêng.
- Tenant có quy mô lớn và cần scale, backup hoặc restore độc lập.
- Số tenant ở mức có thể vận hành database và connection hiệu quả.
- Có khả năng tự động hóa provisioning và migration.

### Chọn schema per tenant khi

- Muốn tách namespace dữ liệu nhưng vẫn dùng chung database instance.
- Database hỗ trợ schema isolation và routing ổn định.
- Số tenant không quá lớn hoặc đã có cơ chế quản lý schema hàng loạt.
- Có thể kiểm soát trạng thái schema trên connection pool.

### Chọn shared schema + tenant_id khi

- Có rất nhiều tenant và dữ liệu mỗi tenant tương đối nhỏ.
- Muốn dùng chung bảng, index và hạ tầng.
- Truy vấn, báo cáo và vận hành liên tenant cần thuận tiện.
- Có thể xây dựng tenant scope bắt buộc ở tầng ứng dụng và bảo vệ thêm bằng constraint/RLS.

Có thể dùng mô hình lai: tenant nhỏ dùng shared schema, tenant lớn hoặc có yêu cầu cách ly cao dùng database riêng. Mô hình lai tăng độ linh hoạt nhưng làm phức tạp routing, migration, observability và hỗ trợ vận hành. Chỉ chọn khi có lý do kinh doanh và năng lực vận hành tương ứng.

## 15. Những lỗi thường gặp

### 15.1. Tin tenant_id từ client

Client có thể thay header, path hoặc request body để thử truy cập tenant khác. Tenant phải được xác thực qua danh tính và membership ở server.

### 15.2. Quên tenant predicate ở một query

Một repository method, native SQL, count query hoặc job nền có thể vô tình trả dữ liệu của mọi tenant. Cần review mọi đường truy cập dữ liệu, không chỉ endpoint chính.

### 15.3. Dùng ID làm cache key mà thiếu tenant

ID có thể trùng giữa tenant hoặc cache namespace dùng chung. Luôn đưa tenant vào key hoặc tách region/cache theo tenant.

### 15.4. Đổi tenant trong transaction đang mở

Connection có thể đã được chọn cho tenant trước đó. Một transaction phải giữ tenant ổn định; không thay context để truy cập tenant khác giữa chừng.

### 15.5. Không reset schema trên pooled connection

Connection được tái sử dụng có thể giữ schema/search_path trước đó. Phải thiết lập và reset trạng thái một cách an toàn ở mỗi lần mượn/trả connection.

### 15.6. Chỉ kiểm tra ở tầng Service

Một đường truy cập native SQL, batch hoặc job có thể bỏ qua service method đã được bảo vệ. Cân nhắc constraint ghép, database permission hoặc RLS như lớp bảo vệ bổ sung.

### 15.7. Migration không đồng bộ giữa các tenant

Một số tenant đã lên schema mới trong khi tenant khác chưa được nâng cấp. Cần theo dõi version và trạng thái migration theo tenant, có retry và cảnh báo.

### 15.8. Cho rằng cascade hoặc JPA mapping tự bảo đảm isolation

JPA mapping mô tả quan hệ object-relational, không tự chứng minh quyền truy cập tenant. Tenant scope phải được kiểm tra ở query, service, database constraint và cache.

## 16. Checklist triển khai multi-tenancy

- [ ] Đã chọn mô hình database, schema hay tenant_id dựa trên yêu cầu cách ly và vận hành.
- [ ] Tenant được resolve từ danh tính đã xác thực và membership hợp lệ.
- [ ] Tenant context được thiết lập trước khi mở transaction/connection.
- [ ] Một transaction/session chỉ làm việc với tenant đã xác định.
- [ ] ThreadLocal hoặc context async được truyền và xóa đúng cách.
- [ ] Repository, native query, count, pagination và batch job đều tenant-scoped.
- [ ] Unique constraint và foreign key có tenant_id khi cần.
- [ ] Cache key, eviction và Hibernate cache giữ đúng tenant boundary.
- [ ] Migration/provisioning theo dõi phiên bản từng database hoặc schema.
- [ ] Backup/restore được kiểm thử theo mô hình dữ liệu.
- [ ] Có kiểm thử truy cập chéo tenant với ID biết trước.
- [ ] Có giám sát tải, connection, dung lượng và trạng thái migration theo tenant.

## 17. Kết luận

Database per tenant tạo ranh giới database rõ và hỗ trợ vận hành riêng từng khách hàng nhưng làm tăng chi phí quản lý. Schema per tenant chia namespace trong cùng database instance và cần định tuyến schema an toàn trên connection. Shared schema với tenant_id tiết kiệm tài nguyên và thuận tiện mở rộng số lượng tenant, nhưng yêu cầu mọi truy vấn, khóa ngoại, cache và tác vụ nền giữ đúng tenant scope. Dù chọn mô hình nào, tenant phải được xác thực từ phía server, tenant context phải ổn định trong transaction và isolation cần được kiểm chứng bằng kiểm thử tích hợp cùng các lớp bảo vệ ở database.
