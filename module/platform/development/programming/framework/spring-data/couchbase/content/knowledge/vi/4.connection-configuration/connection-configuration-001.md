# Cấu hình tự động với các starter Couchbase của Spring Boot

## 1. Bối cảnh và mục tiêu

Trong **Spring Data Couchbase**, ứng dụng Java cần kết nối tới Couchbase Cluster, chọn bucket chứa dữ liệu, ánh xạ document thành đối tượng và cung cấp API truy cập qua repository hoặc `CouchbaseTemplate`. Spring Boot tự động cấu hình phần lớn hạ tầng này khi phát hiện đúng starter và các thuộc tính kết nối.

Sau bài học, bạn có thể:

- Chọn starter Couchbase cho ứng dụng đồng bộ hoặc reactive.
- Cấu hình cluster, tài khoản và bucket bằng `application.yml` và biến môi trường.
- Hiểu những thành phần Spring Boot tạo tự động, điều kiện để tự động cấu hình hoạt động.
- Truy cập scope/collection qua entity và repository, biết khi nào cần chỉ mục SQL++.
- Phân biệt lỗi bootstrap, phân quyền, định tuyến dữ liệu và truy vấn để xử lý sự cố triển khai.

**Phạm vi:** bài này tập trung vào cơ chế cấu hình kết nối và kiểm chứng một ứng dụng đã truy cập được Couchbase. Thiết kế chỉ mục nâng cao, TTL, CAS, giao dịch và tối ưu reactive là những chủ đề tiếp nối. Các ví dụ dùng cách cấu hình phổ biến của **Spring Boot 3.x** và phiên bản Spring Data Couchbase do Spring Boot quản lý; khi sử dụng phiên bản khác, kiểm tra lại tên thuộc tính trong tài liệu của đúng phiên bản.

## 2. Starter và các thành phần được tạo tự động

| Nhu cầu | Starter | API ứng dụng thường sử dụng |
| --- | --- | --- |
| Xử lý đồng bộ, Spring MVC hoặc tác vụ nền | `spring-boot-starter-data-couchbase` | `CouchbaseRepository`, `CouchbaseTemplate` |
| Luồng dữ liệu bất đồng bộ với Reactor/WebFlux | `spring-boot-starter-data-couchbase-reactive` | `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate` |
| Quan sát trạng thái ứng dụng (tùy chọn) | `spring-boot-starter-actuator` | Health indicator và endpoint `/actuator/health` |

Một starter kéo theo Spring Data Couchbase và Couchbase Java SDK tương thích trong hệ sinh thái dependency của Spring Boot. Nên dùng BOM/dependency management của Spring Boot thay vì tự gán phiên bản SDK và Spring Data khác nhau nếu không có lý do rõ ràng.

Sơ đồ khởi tạo tổng quát:

~~~mermaid
flowchart TD
    A["Thêm Couchbase starter"] --> B["Spring Boot phát hiện các class trên classpath"]
    C["spring.couchbase.* và spring.data.couchbase.*"] --> D["Auto-configuration"]
    B --> D
    D --> E["Couchbase SDK: Cluster và môi trường kết nối"]
    D --> F["Couchbase client factory / converter / mapping"]
    F --> G["CouchbaseTemplate và repository"]
    E --> F
    G --> H["Service của ứng dụng"]
    H --> I["Bucket → Scope → Collection"]
~~~

Spring Boot dựa vào **classpath**, **thuộc tính cấu hình**, **component/repository scanning** và các bean mà ứng dụng đã tự định nghĩa. Khi có cấu hình phù hợp, Boot tạo các bean phục vụ kết nối, mapping, template và repository; bạn thường **không phải tự viết `@Configuration` để tạo `Cluster` hay `CouchbaseTemplate`**.

Tự động cấu hình **không** có nghĩa là Boot tạo cluster, bucket, scope, collection, user hay index bên phía máy chủ. Các tài nguyên đó phải có sẵn và tài khoản kết nối phải được cấp quyền cần thiết.

## 3. Chuẩn bị Couchbase trước khi chạy ứng dụng

Giả sử một hệ thống bán hàng có:

| Thành phần | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| Cluster | `couchbase://127.0.0.1` | Địa chỉ bootstrap đến máy chủ Couchbase nội bộ |
| Bucket | `catalog` | Vùng chứa dữ liệu ứng dụng |
| Scope | `commerce` | Nhóm nghiệp vụ trong bucket |
| Collection | `products` | Tập document sản phẩm |
| User | `app_catalog` | Tài khoản ứng dụng với quyền phù hợp |

Trước tiên, cần khởi tạo cluster, bucket, scope và collection trong Couchbase Server/Capella. Cấp quyền đọc/ghi trên đúng dữ liệu và quyền truy vấn nếu ứng dụng chạy SQL++. Với cluster ở mạng khác, kiểm tra DNS, mạng, TLS và các dịch vụ/port Couchbase mà SDK cần; truy cập được giao diện quản trị qua HTTP **không đảm bảo** SDK đã kết nối được các dịch vụ dữ liệu.

**Phân biệt hai nhóm cấu hình:**

- `spring.couchbase.*`: cách client kết nối tới **cluster** (connection string, xác thực và các tùy chọn môi trường).
- `spring.data.couchbase.*`: lựa chọn và cấu hình tầng **Spring Data**, trước hết là bucket mặc định.

Bucket được chọn ở cấp Spring Data; scope và collection có thể khai báo theo từng entity. Một kết nối cluster có thể phục vụ nhiều collection; không cần tạo một kết nối mạng riêng cho mỗi collection.

## 4. Thêm dependency

### Maven — truy cập đồng bộ

Thêm vào `pom.xml` của dự án Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

### Gradle Kotlin DSL — truy cập đồng bộ

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Với ứng dụng reactive, chọn starter tương ứng:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase-reactive")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
~~~

`spring-boot-starter-webflux` chỉ cần khi bạn xây dựng tầng HTTP reactive bằng WebFlux; bản thân mục tiêu truy cập Couchbase reactive là do starter Couchbase reactive đáp ứng. Hạn chế thêm cả hai loại starter nếu ứng dụng không thực sự cần cả hai mô hình.

## 5. Cấu hình kết nối bằng `application.yml`

Ví dụ cho môi trường local, sử dụng biến môi trường để giữ thông tin đăng nhập ngoài mã nguồn:

~~~yaml
spring:
  application:
    name: catalog-service
  couchbase:
    connection-string: ${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: ${COUCHBASE_BUCKET:catalog}
~~~

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| `spring.couchbase.connection-string` | Danh sách seed node hoặc địa chỉ bootstrap; dùng `couchbase://` trong mạng nội bộ, `couchbases://` khi kết nối TLS | Sai hostname, DNS, giao thức hoặc chính sách mạng |
| `spring.couchbase.username` | Username xác thực với cluster | User không tồn tại hoặc không được phép truy cập |
| `spring.couchbase.password` | Mật khẩu tài khoản cluster | Sai mật khẩu hoặc biến môi trường chưa được truyền |
| `spring.data.couchbase.bucket-name` | Bucket mặc định cho Spring Data mapping/repository | Tên bucket sai hoặc tài khoản thiếu quyền |

Không hardcode mật khẩu thật trong `application.yml`, ví dụ minh họa hay lịch sử Git. Trong môi trường triển khai, truyền giá trị từ cơ chế quản lý secret của nền tảng hoặc hệ thống cấu hình bảo mật.

Một file cấu hình tối giản thường đủ để Boot kết nối. **Không cần** viết `@EnableCouchbaseRepositories` khi repository nằm trong phạm vi package được `@SpringBootApplication` quét mặc định. Nếu repository đặt ngoài phạm vi đó, điều chỉnh cấu trúc package hoặc khai báo phạm vi quét một cách có chủ đích.

### Cấu hình riêng theo môi trường

Có thể đặt địa chỉ và bucket khác nhau trong `application-local.yml`, `application-prod.yml`, rồi chọn profile khi chạy. Mật khẩu vẫn nên lấy từ secret/biến môi trường. Với môi trường dùng TLS, connection string sẽ có dạng như:

~~~yaml
spring:
  couchbase:
    connection-string: ${COUCHBASE_CONNECTION_STRING:couchbases://cb.example.internal}
~~~

Hostname chỉ là ví dụ. Với cluster quản lý/Capella, cấu hình DNS, danh sách IP được phép và chuỗi chứng chỉ tin cậy theo hướng dẫn của môi trường đó; không tắt kiểm tra chứng chỉ để xử lý lỗi TLS.

### Điều chỉnh timeout có mục đích

Khi có số liệu cho thấy một môi trường cần ngưỡng khác mặc định, có thể cấu hình một số timeout ở cấp Couchbase SDK:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: 10s
        query: 20s
~~~

Giá trị trên chỉ minh họa cách khai báo `Duration`, không phải ngưỡng tối ưu cho mọi hệ thống. Phân biệt timeout lúc kết nối với timeout của lệnh KV hoặc SQL++; tăng timeout không khắc phục được thiếu index, DNS lỗi hoặc pool kết nối bị nghẽn. Tên nhóm timeout có thể thay đổi giữa các thế hệ Spring Boot, nên đối chiếu metadata cấu hình của đúng bản đang dùng.

## 6. Kết nối từ entity đến scope/collection

Spring Data ánh xạ document JSON vào một Java class. Với bucket `catalog`, scope `commerce` và collection `products`, ta có thể khai báo:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("commerce")
@Collection("products")
public class Product {
    @Id
    private String id;

    private String sku;
    private String name;

    @Version
    private Long version;

    protected Product() {}

    public Product(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    // Bổ sung getters/setters hoặc quy ước mapping phù hợp của dự án.
}
~~~

Trong ví dụ:

- `@Document` đánh dấu kiểu được Spring Data Couchbase ánh xạ sang document.
- `@Id` là **document key**, dùng cho các thao tác KV theo ID.
- `@Scope` và `@Collection` đặt nơi lưu entity bên trong bucket đã cấu hình.
- `@Version` hỗ trợ optimistic locking bằng CAS, hữu ích khi nhiều yêu cầu cùng sửa một document.

Nếu không chỉ định scope/collection riêng, Couchbase có vùng mặc định `_default`. Tránh vô tình ghi document vào `_default._default` khi dữ liệu nghiệp vụ đã được thiết kế cho collection cụ thể.

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    List<Product> findBySku(String sku);
}
~~~

Spring Boot tạo bean repository để inject vào service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Product create(String sku, String name) {
        Product item = new Product("product::" + sku, sku, name);
        return products.save(item);
    }

    public Product load(String id) {
        return products.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));
    }
}
~~~

Các đoạn Java minh họa trọng tâm cấu hình và API; lớp entity cần thêm accessor phù hợp nếu sử dụng trực tiếp. Key như `product::SKU-001` là một quy ước ứng dụng, không phải định dạng bắt buộc của Couchbase.

### Vì sao `findById` hoạt động nhưng `findBySku` có thể lỗi?

`findById` sử dụng thao tác **key-value** theo document ID; `findBySku` là truy vấn theo thuộc tính, thường được Spring Data chuyển thành **SQL++**, nên cần dịch vụ Query và index phù hợp. Ví dụ index trên collection đã tạo:

~~~sql
CREATE INDEX ix_products_sku
ON `catalog`.`commerce`.`products`(`sku`);
~~~

Chỉ mục phải được tạo và ở trạng thái phục vụ truy vấn trước khi gọi `findBySku`. Index trên collection khác hoặc bucket mặc định không thay thế được index trên `catalog.commerce.products`. Trong môi trường production nên thiết kế index theo truy vấn thực tế, predicate, sort và chính sách vận hành; primary index chỉ nên dùng cho thử nghiệm có kiểm soát.

Truy vấn SQL++ dựa trên index có thể quan sát cập nhật trễ hơn thao tác KV; các yêu cầu nhất quán ngay sau ghi cần chọn cách đọc và mức scan consistency phù hợp, thay vì mặc định coi mọi truy vấn đều đọc được dữ liệu mới tức thì.

## 7. Khi nào dùng `CouchbaseTemplate`?

Repository phù hợp với CRUD, tìm kiếm theo phương thức và một số truy vấn khai báo. Khi cần thao tác mapping linh hoạt hoặc truy vấn phức tạp hơn, inject `CouchbaseTemplate` do Spring Boot cấu hình tự động. Không cần xây dựng template bằng tay cho nhu cầu thông thường.

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductDocumentService {
    private final CouchbaseTemplate template;

    public ProductDocumentService(CouchbaseTemplate template) {
        this.template = template;
    }

    public Product getById(String id) {
        return template.findById(Product.class).one(id);
    }
}
~~~

Template vẫn dùng cấu hình cluster, bucket và mapping đã thiết lập. Nếu ứng dụng cần nhiều bucket hoặc tùy chỉnh kết nối khác nhau, hãy thiết kế bean/config riêng có kiểm soát; việc tự khai báo một bean lõi có thể làm thay đổi điều kiện auto-configuration và hành vi của bean mặc định.

## 8. Biến thể reactive

Ứng dụng dùng Reactor chọn `spring-boot-starter-data-couchbase-reactive`, giữ nguyên các thuộc tính kết nối cơ bản, và khai báo repository phản ứng:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveCouchbaseRepository<Product, String> {

    Mono<Product> findBySku(String sku);
}
~~~

Trong tầng service:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductService {
    private final ReactiveProductRepository products;

    public ReactiveProductService(ReactiveProductRepository products) {
        this.products = products;
    }

    public Mono<Product> load(String id) {
        return products.findById(id);
    }
}
~~~

Thay vì nhận ngay đối tượng `Product`, lời gọi trả về `Mono<Product>` để được subscribe trong chuỗi reactive. Tránh gọi `block()` trên luồng xử lý HTTP của WebFlux. Starter reactive thay đổi cách ứng dụng **tiêu thụ API**, nhưng không thay thế yêu cầu cấp quyền bucket, chuẩn bị collection hay tạo index cho truy vấn SQL++.

## 9. Kiểm chứng cấu hình chạy được

Thực hiện lần lượt từ hạ tầng đến tầng ứng dụng:

1. **Cluster:** địa chỉ bootstrap phân giải được; dịch vụ cần thiết của Couchbase sẵn sàng; cấu hình TLS/mạng hợp lệ.
2. **Credentials:** username/password thực sự được truyền vào tiến trình; tài khoản có quyền trên `catalog` và collection liên quan.
3. **Metadata:** bucket `catalog`, scope `commerce` và collection `products` tồn tại trước khi ứng dụng truy cập.
4. **Application startup:** log không có lỗi auto-configuration, xác thực hoặc khởi tạo SDK. Nếu bean repository không xuất hiện, kiểm tra starter và package scan.
5. **KV smoke test:** `save` và `findById` với một document thử nghiệm có ID riêng, sau đó xóa dữ liệu thử nếu môi trường yêu cầu.
6. **Query smoke test:** chạy `findBySku` sau khi tạo index trên đúng collection; kiểm tra quyền Query và tình trạng index.

Nếu có Actuator, thêm dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Kiểm tra `/actuator/health` để có tín hiệu về khả năng hoạt động. Mức chi tiết health phụ thuộc cấu hình Actuator và quyền truy cập; trạng thái “UP” **không thay thế** một smoke test trên collection và câu truy vấn thực tế.

## 10. Sự cố thường gặp và cách khoanh vùng

| Biểu hiện | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không khởi động được kết nối hoặc bootstrap timeout | Sai connection string, DNS, routing, TLS hoặc port bị chặn | Kiểm tra địa chỉ bootstrap, khả năng truy cập dịch vụ và chứng chỉ |
| Lỗi authentication | Biến môi trường trống, sai username/password | Kiểm tra cách cấp secret và user trên cluster |
| Thấy cluster nhưng không truy cập được bucket | Bucket sai tên hoặc quyền thiếu | So khớp `bucket-name` và quyền cấp trên bucket/scope/collection |
| `save/findById` chạy, `findBySku` lỗi | Thiếu Query service hoặc secondary index trên keyspace | Kiểm tra Query service, index tương ứng với field và collection |
| Không tìm thấy bean repository | Thiếu starter, cấu hình loại repository không phù hợp hoặc package không được scan | Kiểm tra dependency, package của `@SpringBootApplication` và interface repository |
| Document vào nhầm collection | Thiếu hoặc sai `@Scope` / `@Collection` | Kiểm tra annotation và tên keyspace thực tế |
| Lỗi cập nhật đồng thời | CAS thay đổi khi dùng `@Version` | Xử lý optimistic locking, đọc lại bản mới trước khi quyết định retry |
| Timeout khi tải tăng cao | Độ trễ truy vấn, index chưa tối ưu hoặc giới hạn tài nguyên | Quan sát latency theo dịch vụ, query plan và capacity trước khi tăng timeout |

**Phân biệt lỗi kết nối với lỗi truy vấn:** cluster connect thành công mới chỉ chứng minh client có thể bootstrap; các lệnh KV/Query còn phụ thuộc quyền, dịch vụ tương ứng, keyspace và index. Chẩn đoán theo thao tác đang thất bại sẽ chính xác hơn việc thay đổi hàng loạt tham số kết nối.

## 11. Thực hành ngắn: thêm Couchbase cho catalog service

Giả sử một nhóm chuyển chức năng quản lý sản phẩm sang document store:

1. Tạo bucket `catalog`, scope `commerce`, collection `products` và user ứng dụng với quyền tối thiểu.
2. Thêm `spring-boot-starter-data-couchbase` vào dự án Boot, khai báo connection string, thông tin đăng nhập và bucket bằng `application.yml`.
3. Ánh xạ `Product` vào `commerce.products` với `@Document`, `@Scope`, `@Collection`.
4. Tạo `ProductRepository`, thử `save` và `findById` với key `product::SKU-001`.
5. Tạo index `ix_products_sku`, rồi thử `findBySku("SKU-001")`.
6. Xác nhận cấu hình tương ứng trên môi trường triển khai: credentials bằng secret, connection string/TLS đúng và quyền chỉ trên tài nguyên cần dùng.

**Tiêu chí hoàn thành:** ứng dụng khởi động mà không tự tạo bean kết nối thủ công; đọc/ghi bằng ID đúng bucket/scope/collection; truy vấn theo SKU hoạt động sau khi index sẵn sàng; secret không nằm trong repository Git.

## 12. Ghi nhớ

Spring Boot tự cấu hình SDK, Spring Data mapping, template và repository dựa trên starter cùng properties. Hai nhóm thông tin thường được thiết lập riêng là **cluster** (`spring.couchbase.*`) và **bucket mặc định** (`spring.data.couchbase.bucket-name`); **scope/collection** được chọn qua mapping entity hoặc cấu hình truy cập chuyên biệt.

Sau khi kết nối thành công, hiệu năng và tính đúng đắn còn phụ thuộc ID, index SQL++, nhất quán truy vấn, TTL, CAS, giao dịch và lựa chọn đồng bộ/reactive. Vì vậy, kiểm chứng đủ cả thao tác KV và truy vấn thực tế là bước cần thiết trước khi coi cấu hình đã sẵn sàng vận hành.

