# ClusterEnvironment, Cluster, Bucket và CouchbaseClientFactory

## 1. Bốn lớp đối tượng trong một kết nối Spring Data Couchbase

Khi xây dựng tầng truy cập Couchbase bằng **Spring Data Couchbase** (module **SPRING_DATA_COUCHBASE**), chúng ta không chỉ cần một URL và mật khẩu. Ở dưới repository, `CouchbaseTemplate` và document mapping là những đối tượng hạ tầng có phạm vi trách nhiệm khác nhau:

- **`ClusterEnvironment`** — các thiết lập và tài nguyên dùng chung cho Couchbase Java SDK.
- **`Cluster`** — điểm truy cập tới một Couchbase cluster và các dịch vụ của nó.
- **`Bucket`** — handle truy cập một bucket trong cluster; từ đây tới scope và collection.
- **`CouchbaseClientFactory`** — lớp trừu tượng của **Spring Data Couchbase** để lấy client/handle phù hợp với cấu hình và cung cấp nền cho template, repository.

Điểm cần nắm vững: `ClusterEnvironment`, `Cluster`, `Bucket` thuộc **Couchbase Java SDK**; `CouchbaseClientFactory` thuộc **Spring Data Couchbase**. Các đối tượng SDK không thay thế vai trò mapping entity, repository hoặc transaction support của Spring Data.

Bài học này giúp bạn trả lời: tạo mỗi loại đối tượng ở đâu, đối tượng nào nên được tái sử dụng, ai quản lý vòng đời, cách kết nối đúng bucket/scope/collection và khi nào nên dùng SDK trực tiếp thay vì repository/template.

Các ví dụ áp dụng cho kiến trúc phổ biến của **Spring Boot 3.x**, Spring Data Couchbase tương thích và **Couchbase Java SDK 3.x**. API cấu hình chi tiết có thể thay đổi giữa phiên bản; nếu mở rộng framework, hãy kiểm tra lại API của phiên bản thực tế.

## 2. Bức tranh kiến trúc

~~~mermaid
flowchart TD
    P["application.yml / secrets"] --> E["ClusterEnvironment<br/>Timeout, TLS, I/O, telemetry"]
    P --> C["Cluster<br/>Bootstrap, authentication, topology"]
    E --> C
    C --> B["Bucket: inventory"]
    B --> S["Scope: catalog"]
    S --> K["Collection: products"]
    C --> F["CouchbaseClientFactory<br/>Spring Data"]
    B --> F
    F --> M["Mapping & Converter"]
    M --> T["CouchbaseTemplate"]
    M --> R["CouchbaseRepository"]
    T --> K
    R --> K
~~~

Sơ đồ thể hiện **quan hệ trách nhiệm**, không phải sơ đồ khởi tạo theo thời gian. SDK có thể thiết lập một số kết nối khi thực sự cần; lấy handle `Bucket` không chứng minh bucket hay collection có thể truy cập được.

Hãy phân biệt hai hướng sử dụng cùng một SDK:

| Hướng | Đường đi | Dùng khi |
| --- | --- | --- |
| SDK trực tiếp | `Cluster → Bucket → Scope → Collection` | Thao tác KV/Query cấp thấp, chức năng SDK chuyên biệt |
| Spring Data | `CouchbaseClientFactory → Template/Repository → Mapping → Collection` | CRUD entity, mapping document, repository, truy vấn Spring Data |

SDK trực tiếp trao quyền điều khiển thấp hơn. Spring Data bổ sung chuyển đổi object–document, mapping, optimistic locking qua `@Version` và tích hợp với ứng dụng Spring.

## 3. `ClusterEnvironment`: chính sách và tài nguyên dùng chung

`com.couchbase.client.java.env.ClusterEnvironment` đại diện cho môi trường hoạt động của Couchbase Java SDK. Bạn có thể cấu hình những mối quan tâm như timeout, TLS, đặc tính kết nối/I/O và quan sát hệ thống theo API của bản SDK đang dùng.

Một số điểm cần hiểu:

1. **Môi trường không đại diện cho bucket.** Không đặt tên bucket hoặc collection ở `ClusterEnvironment`.
2. **Môi trường không phải tài khoản đăng nhập.** Credentials thường được truyền khi tạo `Cluster`; chính sách bảo mật ở môi trường có thể bao gồm TLS/trust.
3. **Môi trường dùng chung có chi phí tài nguyên.** Nó quản lý hoặc tham gia quản lý các tài nguyên nền của SDK. Tránh tạo một môi trường mới cho mỗi request HTTP.
4. **Vòng đời phải rõ ràng.** Nếu **ứng dụng tự tạo** environment, ứng dụng phải dọn dẹp sau khi ngừng sử dụng cluster. Nếu Spring Boot quản lý bean này, để Spring quản lý quá trình đóng.

Ví dụ cấu hình một timeout KV bằng SDK:

~~~java
import java.time.Duration;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.TimeoutConfig;

ClusterEnvironment environment = ClusterEnvironment.builder()
        .timeoutConfig(TimeoutConfig.kvTimeout(Duration.ofSeconds(3)))
        .build();
~~~

`kvTimeout` chỉ đặt giới hạn cho một loại thao tác KV; các dịch vụ như Query có timeout riêng. Ngưỡng 3 giây chỉ để minh họa cú pháp. Khi vận hành, hãy đặt timeout dựa trên độ trễ mục tiêu, tải và dữ liệu quan sát, thay vì tăng ngưỡng để che lỗi mạng hoặc index.

**Với Spring Boot**, không nhất thiết phải tự xây dựng `ClusterEnvironment` trong một bean mới. Khi starter và auto-configuration đáp ứng nhu cầu, nên dùng các thuộc tính Boot được hỗ trợ trong đúng phiên bản, ví dụ:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: 10s
        kv: 3s
        query: 20s
~~~

Tên property nâng cao là hợp đồng của phiên bản Spring Boot; hãy kiểm tra metadata cấu hình nếu ứng dụng dùng dòng khác. Tránh tạo đồng thời một SDK environment riêng và một môi trường do Boot quản lý mà không xác định bean nào thật sự đang được Spring Data sử dụng.

## 4. `Cluster`: cửa ngõ tới các dịch vụ Couchbase

`com.couchbase.client.java.Cluster` là đối tượng SDK đại diện cho một Couchbase cluster. Nó dùng connection string và credentials để bootstrap, xác thực và điều phối thao tác đến những dịch vụ thích hợp.

Một ví dụ tạo cluster trực tiếp bằng SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

Cluster cluster = Cluster.connect(
        "couchbase://127.0.0.1",
        ClusterOptions.clusterOptions("inventory_app", password)
                .environment(environment)
);
~~~

Trong đoạn code trên:

- `couchbase://127.0.0.1` là địa chỉ bootstrap của cluster nội bộ; với môi trường yêu cầu TLS dùng connection string `couchbases://...` phù hợp.
- `inventory_app` là user trên Couchbase, còn `password` lấy từ nguồn secret ở runtime.
- `environment` là instance đã tạo ở bước trước.

Không hardcode password thật trong code, testcase hoặc tài liệu cấu hình được commit. Chuỗi kết nối nên được cấp theo môi trường. Đối với Couchbase Capella, cần dùng endpoint, cấu hình mạng và chứng chỉ tin cậy của cluster được cấp.

**Cluster là đối tượng dùng chung.** Tạo một `Cluster.connect(...)` ở mỗi lần truy vấn làm phát sinh kết nối và tài nguyên không cần thiết. Với Spring Boot, ưu tiên dùng `Cluster`/client factory được container quản lý, rồi inject vào các service phụ thuộc.

### Bootstrap và readiness không hoàn toàn giống nhau

Có những thao tác được khởi tạo theo nhu cầu. Việc đã có biến `cluster` không tự động chứng minh mọi dịch vụ hoặc bucket đều sẵn sàng. Khi viết ứng dụng SDK độc lập hoặc một probe có chủ đích, có thể chờ bucket sẵn sàng trước khi thực hiện KV:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Bucket;

Bucket bucket = cluster.bucket("inventory");
bucket.waitUntilReady(Duration.ofSeconds(10));
~~~

`waitUntilReady` giúp kiểm tra khả năng sẵn sàng trong thời hạn đã cho, nhưng không thay thế xác minh quyền trên scope/collection hay index của truy vấn SQL++.

## 5. `Bucket`: handle tới một bucket, không phải document

`com.couchbase.client.java.Bucket` là handle được lấy từ cluster:

~~~java
Bucket bucket = cluster.bucket("inventory");
~~~

Từ handle này, SDK cho phép truy cập scope và collection:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.Scope;

Scope scope = bucket.scope("catalog");
Collection products = scope.collection("products");
~~~

Cấu trúc tương ứng trên Couchbase:

~~~text
Cluster
└── Bucket: inventory
    └── Scope: catalog
        └── Collection: products
            ├── product::SKU-001
            └── product::SKU-002
~~~

**Bucket, scope và collection là ba cấp khác nhau.** Nếu ứng dụng chỉ mở `bucket("inventory")`, SDK chưa chọn collection nghiệp vụ cụ thể cho từng thao tác. Với một số API, collection mặc định có thể được dùng khi gọi `bucket.defaultCollection()`; điều đó khác với `catalog.products`.

Vì vậy, khi review một lỗi “không tìm thấy document”, cần kiểm tra **keyspace** (cluster, bucket, scope, collection) trước khi kết luận ID sai. Hai collection có thể chứa hai document cùng ID nhưng khác nội dung.

### KV hoạt động như thế nào?

Ví dụ dùng SDK trực tiếp trên collection `catalog.products`:

~~~java
import com.couchbase.client.java.json.JsonObject;

products.upsert(
        "product::SKU-001",
        JsonObject.create()
                .put("sku", "SKU-001")
                .put("name", "Mechanical keyboard")
);

JsonObject saved = products.get("product::SKU-001")
                           .contentAsObject();
System.out.println(saved.getString("name"));
~~~

`upsert` ghi theo document key, `get` đọc bằng key. Chúng là các thao tác **Key-Value** và thông thường không đòi hỏi secondary index SQL++.

Đây là code SDK thuần, do đó đối tượng JSON không tự đi qua `MappingCouchbaseConverter` của Spring Data. Nếu hệ thống cần mapping entity, annotation, quản lý version bằng `@Version` hoặc repository abstraction, nên dùng template/repository cho phần logic đó.

## 6. Ví dụ SDK đầy đủ và vòng đời tài nguyên

Dưới đây là chương trình Java SDK độc lập minh họa rõ ai tạo và ai đóng môi trường, cluster:

~~~java
import java.time.Duration;

import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.TimeoutConfig;
import com.couchbase.client.java.json.JsonObject;

public final class CouchbaseSdkExample {

    public static void main(String[] args) {
        String connectionString = requireEnv("COUCHBASE_CONNECTION_STRING");
        String username = requireEnv("COUCHBASE_USERNAME");
        String password = requireEnv("COUCHBASE_PASSWORD");

        ClusterEnvironment environment = ClusterEnvironment.builder()
                .timeoutConfig(TimeoutConfig.kvTimeout(Duration.ofSeconds(3)))
                .build();

        Cluster cluster = null;
        try {
            cluster = Cluster.connect(
                    connectionString,
                    ClusterOptions.clusterOptions(username, password)
                            .environment(environment)
            );

            Bucket bucket = cluster.bucket("inventory");
            bucket.waitUntilReady(Duration.ofSeconds(10));

            Collection products = bucket.scope("catalog")
                                        .collection("products");

            products.upsert(
                    "product::SKU-001",
                    JsonObject.create().put("sku", "SKU-001")
                                       .put("name", "Mechanical keyboard")
            );

            JsonObject result = products.get("product::SKU-001")
                                        .contentAsObject();

            System.out.println(result.getString("sku"));
        } finally {
            if (cluster != null) {
                cluster.disconnect();
            }
            environment.shutdown();
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

Ví dụ giả định bucket/scope/collection tồn tại và user có quyền. Nó cũng **ghi đè** document có key `product::SKU-001` nếu đã tồn tại: chỉ chạy trên môi trường thực hành hoặc dùng key thử nghiệm riêng. Chương trình SDK độc lập không tạo Spring context hay Spring Data repository.

Vòng đời quan trọng:

| Đối tượng | Ai tạo? | Khi nào kết thúc? |
| --- | --- | --- |
| `ClusterEnvironment` | Chương trình tự tạo qua builder | Sau khi các cluster dùng environment đã dừng |
| `Cluster` | Chương trình tự gọi `Cluster.connect(...)` | Khi không còn thao tác, gọi `disconnect()` |
| `Bucket` | Lấy từ cluster | Handle thuộc tài nguyên cluster; không tạo cluster mới cho từng bucket |
| `Collection` | Lấy từ bucket/scope | Handle truy cập keyspace; không tạo SDK environment mới |

Nếu ứng dụng dùng **Spring Boot + Spring Data**, không sao chép nguyên đoạn khởi tạo và shutdown này vào mỗi service. Thay vào đó để container quản lý các bean; gọi `disconnect()` giữa vòng đời ứng dụng sẽ làm các repository khác mất kết nối.

## 7. `CouchbaseClientFactory`: cầu nối giữa SDK và Spring Data

`org.springframework.data.couchbase.core.CouchbaseClientFactory` là giao diện Spring Data cung cấp khả năng truy cập các đối tượng SDK mà tầng data cần, trong ngữ cảnh cấu hình của ứng dụng.

Hãy hiểu sự khác biệt:

- `Cluster` được SDK tạo dựa trên connection string/credentials và quản lý liên lạc với cluster.
- `Bucket` là handle SDK tới một bucket.
- `CouchbaseClientFactory` đặt **Cluster/Bucket trong ngữ cảnh Spring Data**, để converter, template và repository sử dụng cùng hạ tầng.

Một ứng dụng Spring Boot đã thêm starter Couchbase và có properties phù hợp thường được cung cấp client factory qua auto-configuration. Một cấu hình Java kế thừa `AbstractCouchbaseConfiguration` cũng có thể cung cấp hạ tầng Spring Data tương ứng. Bạn không cần tự `new` factory khi dùng thiết lập thông thường.

### Các property đi vào factory như thế nào?

Ví dụ `application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Bảng ranh giới:

| Cấu hình | Đích logic | Ví dụ |
| --- | --- | --- |
| `spring.couchbase.connection-string` | SDK/Cluster | `couchbase://127.0.0.1` |
| `spring.couchbase.username` / `password` | Xác thực SDK/Cluster | User ứng dụng và secret |
| `spring.couchbase.env.*` | Môi trường SDK nếu Boot hỗ trợ property tương ứng | Timeout |
| `spring.data.couchbase.bucket-name` | Bucket mặc định của hạ tầng Spring Data | `inventory` |
| `@Scope`, `@Collection` | Mapping entity đến keyspace cụ thể | `catalog.products` |

Như vậy, không đưa bucket vào path của connection string và không dùng `spring.couchbase.bucket-name` để thay thế `spring.data.couchbase.bucket-name`.

### Inject client factory để dùng SDK có kiểm soát

Trong một service cần SDK thấp hơn cấp repository, có thể nhận factory đã do Spring quản lý:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductSdkReader {

    private final CouchbaseClientFactory clientFactory;

    public ProductSdkReader(CouchbaseClientFactory clientFactory) {
        this.clientFactory = clientFactory;
    }

    public JsonObject getProduct(String id) {
        Collection products = clientFactory.getBucket()
                .scope("catalog")
                .collection("products");

        return products.get(id).contentAsObject();
    }
}
~~~

Điểm đáng chú ý: service **không gọi `Cluster.connect()`**, không tạo môi trường mới và không đóng cluster. Nó dùng bucket của Spring Data hiện tại. Phần đọc `JsonObject` bằng SDK trực tiếp không đi qua mapping entity của repository.

Ví dụ này giả định chỉ có một `CouchbaseClientFactory` bean mặc định. Nếu ứng dụng có nhiều factory cho nhiều bucket, phải chỉ rõ đúng bean/qualifier; không chọn ngẫu nhiên một factory theo thứ tự khởi tạo.

## 8. Repository và `CouchbaseTemplate` nằm ở đâu?

CouchbaseClientFactory là hạ tầng dưới các API Spring Data. Giả sử entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class ProductDocument {
    @Id
    private String id;

    private String sku;
    private String name;

    @Version
    private Long version;

    protected ProductDocument() {}

    public ProductDocument(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    // Khai báo accessors phù hợp nếu dùng class này trực tiếp.
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Service bằng template:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductTemplateReader {

    private final CouchbaseTemplate template;

    public ProductTemplateReader(CouchbaseTemplate template) {
        this.template = template;
    }

    public ProductDocument get(String id) {
        return template.findById(ProductDocument.class).one(id);
    }
}
~~~

Hai API này sử dụng mapping, converter và client factory đã cấu hình. Mức trừu tượng cao hơn giúp:

1. Ánh xạ document JSON với class Java.
2. Xác định scope/collection từ annotation.
3. Dùng `@Version` cho optimistic locking dựa trên CAS ở những thao tác tương ứng.
4. Giữ nhất quán cách truy cập dữ liệu qua nhiều service.

Nếu trực tiếp dùng `clientFactory.getBucket().scope(...).collection(...)` rồi thay dữ liệu không qua Spring Data, các annotation mapping và cơ chế versioning của entity **không tự áp dụng**. Khi phối hợp SDK trực tiếp với repository trên cùng document, hãy cân nhắc CAS, TTL, schema và converter để tránh thay đổi ngoài ý muốn.

## 9. Một cluster, nhiều bucket: đừng nhầm phạm vi sử dụng lại

Một `Cluster` có thể mở nhiều `Bucket`:

~~~java
Bucket inventory = cluster.bucket("inventory");
Bucket orders = cluster.bucket("orders");
~~~

Điều này **không đồng nghĩa** mọi repository Spring Data tự chọn được bucket dựa trên tên entity. `CouchbaseClientFactory` mặc định thường gắn với cấu hình bucket tương ứng; khi có nhiều bucket, cần thiết kế rõ cách tạo factory/template và phân vùng repository, đúng với API của phiên bản Spring Data.

| Nhu cầu | Thiết kế thường phù hợp |
| --- | --- |
| Một ứng dụng, một bucket, nhiều collections | Một factory mặc định; phân biệt `@Scope` và `@Collection` |
| Một cluster, nhiều buckets | Tách rõ factory/template theo bucket, lựa chọn đúng bean |
| Nhiều clusters | Tách cấu hình cluster/environment và các factory, quản lý vòng đời riêng |
| Nhiều repository dùng chung bucket | Dùng chung hạ tầng do Spring quản lý |

**Sai lầm phổ biến:** đổi `@Collection("orders")` thành `@Collection("inventory")` với hy vọng chuyển từ bucket `orders` sang bucket `inventory`. Annotation collection chỉ đổi **collection** trong bucket đã chọn; bucket là cấp phía trên.

Với nhiều client factories, các bean có thể thiếu hoặc nhập nhằng nếu không đặt tên/qualifier và cấu hình repository rõ ràng. Đừng đăng ký lại `CouchbaseClientFactory` mặc định khi chỉ cần thêm một repository cùng bucket.

## 10. Reactive có thay đổi bốn khái niệm này không?

**Không đổi về bản chất.** Couchbase SDK hỗ trợ nhiều phong cách API; Spring Data cung cấp `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate` để làm việc với Reactor. Vẫn cần một môi trường SDK, cluster và bucket phù hợp cùng factory của Spring Data.

Ví dụ SDK reactive trực tiếp:

~~~java
import reactor.core.publisher.Mono;
import com.couchbase.client.java.kv.GetResult;

Mono<GetResult> resultMono =
        products.reactive().get("product::SKU-001");
~~~

Việc khai báo `Mono` chỉ tạo pipeline phản ứng; thao tác được thực hiện khi có subscriber. Trong ứng dụng WebFlux, tránh gọi `block()` trên event-loop. Nếu hệ thống đã xây dựng với repository reactive, nên giữ chuỗi reactive xuyên suốt service và controller.

Lưu ý: “reactive” không thay đổi bucket/collection, không bỏ qua RBAC, cũng không tự giải quyết vấn đề index SQL++. Cấu hình SDK timeout, áp lực tải và độ nhất quán vẫn cần đánh giá theo thao tác thực tế.

## 11. Truy vấn SQL++, TTL, CAS và giao dịch liên quan gì?

Bài học này nói về nền kết nối, nhưng thiết kế hạ tầng sẽ tác động tới các tính năng nâng cao:

| Tính năng | Liên hệ với bốn đối tượng |
| --- | --- |
| SQL++ | `Cluster` cung cấp API Query; truy vấn theo thuộc tính cần Query service, quyền và index trên đúng keyspace |
| Chỉ mục | Tạo trong Couchbase, không được sinh tự động chỉ bằng cách mở `Bucket` hoặc tạo factory |
| TTL | Là thuộc tính hết hạn của document/operation hoặc quy tắc cấu hình thích hợp; không phải lifetime của `Bucket` handle |
| CAS | SDK cung cấp CAS cho thao tác KV; Spring Data có thể tích hợp optimistic locking qua `@Version` |
| Giao dịch | Có phạm vi thao tác/điều kiện riêng; không đồng nghĩa mọi `Cluster` hoặc `CouchbaseClientFactory` tự tạo transaction |
| Scan consistency | Liên quan truy vấn SQL++ và khả năng nhìn thấy index update, khác đọc trực tiếp theo ID |
| Bucket/scope/collection | Ảnh hưởng tới chính xác keyspace, quyền và index mà API thao tác |

Ví dụ, `repository.findById("product::SKU-001")` thường đọc KV; một phương thức `findBySku("SKU-001")` thường được thực hiện dưới dạng SQL++ và cần index phù hợp:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`catalog`.`products`(`sku`);
~~~

Index phải nằm trên collection đúng và sẵn sàng trước khi chạy truy vấn. Lỗi thiếu index không được sửa bằng cách tạo một `ClusterEnvironment` mới, tăng connection timeout hoặc đổi tài khoản nếu nguyên nhân thực tế là index chưa có.

## 12. Chẩn đoán lỗi theo từng tầng

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động / thao tác I/O"] --> B{"Cấu hình & cluster bootstrap?"}
    B -- "Không" --> C["Connection string, DNS, TLS,<br/>ClusterEnvironment, topology"]
    B -- "Có" --> D{"Xác thực thành công?"}
    D -- "Không" --> E["Credentials và RBAC"]
    D -- "Có" --> F{"Mở bucket và đọc KV?"}
    F -- "Không" --> G["Tên bucket, Data service,<br/>scope/collection, quyền"]
    F -- "Có" --> H{"Mapping/repository đúng?"}
    H -- "Không" --> I["Factory đang dùng, converter,<br/>annotations, package scanning"]
    H -- "Có" --> J{"SQL++ query chạy được?"}
    J -- "Không" --> K["Query service, secondary index,<br/>quyền và consistency"]
    J -- "Có" --> L["Kiểm chứng hoàn tất"]
~~~

| Triệu chứng | Tầng cần kiểm tra | Câu hỏi đầu tiên |
| --- | --- | --- |
| Bootstrap timeout | `ClusterEnvironment` / `Cluster` | Hostname, topology, các node/dịch vụ có reachable? |
| TLS/certificate error | Môi trường SDK | Giao thức, chứng chỉ, hostname và trust chain có đúng? |
| Authentication failure | `Cluster` / credentials | User/password được inject đúng, còn hiệu lực? |
| Bucket not found | `Bucket` / factory | Bucket có tồn tại trên cluster đang kết nối? |
| Access denied khi đọc document | Bucket/scope/collection và RBAC | User có quyền KV trên collection đích? |
| Repository đọc sai collection | Mapping | `@Scope`, `@Collection` và factory đang chọn gì? |
| Nhiều bean factory/template bị nhập nhằng | Spring Data context | Có hơn một factory/bean mà không có qualifier? |
| `findById` chạy, `findBySku` lỗi | SQL++/Index | Query service và index đúng keyspace có sẵn? |
| Lỗi sau khi đóng cluster | Vòng đời SDK | Có service tự gọi `disconnect()` trong khi bean vẫn được dùng? |
| Độ trễ tăng khi tải lớn | SDK/Query và vận hành | Có tạo cluster mỗi request, query thiếu index hoặc timeout không phù hợp? |

**Tách readiness và data-path:** ứng dụng khởi động không lỗi bean chưa chắc đã đọc/ghi được. Hãy chạy một KV smoke test bằng `findById` trên entity đã mapping, rồi mới kiểm thử query theo thuộc tính; nhờ vậy dễ phân biệt lỗi kết nối với lỗi Query service và index.

## 13. Quy tắc thiết kế vòng đời trong ứng dụng Spring Boot

Một mô hình vận hành đơn giản nên tuân theo:

1. **Một nguồn cấu hình kết nối rõ ràng** cho connection string, credentials, TLS và timeout; secret nằm ngoài source code.
2. **Dùng bean SDK/factory do Spring quản lý** khi đã chọn Spring Boot auto-configuration hoặc `AbstractCouchbaseConfiguration`. Không tự tạo thêm client chỉ để thực hiện một query.
3. **Tái sử dụng cluster và environment** thay vì khởi tạo theo request hoặc theo từng repository.
4. **Truy cập đúng keyspace** bằng bucket, scope, collection; mapping entity phải tương thích với thiết kế dữ liệu.
5. **Đóng tài nguyên ở ranh giới vòng đời phù hợp**: chương trình SDK tự quản lý phải đóng cluster/environment; ứng dụng Spring-managed để container điều phối shutdown.
6. **Quan sát thao tác thật**: kiểm tra KV, SQL++, độ trễ, timeout và lỗi permission theo dịch vụ; không coi tạo bean thành công là kiểm chứng đầy đủ.

Tránh dùng endpoint health tổng quát làm chứng cứ duy nhất. Health indicator có thể kiểm tra một mức khả dụng khác với luồng truy cập collection, index hoặc transaction của nghiệp vụ.

## 14. Bài tập thực hành: truy vết một thao tác ghi sản phẩm

Một nhóm xây dựng `inventory-service` bằng Spring Boot. Cấu hình:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: inventory
~~~

Entity có `@Scope("catalog")` và `@Collection("products")`. Repository nhận `ProductDocument` với ID `product::SKU-123`.

**Các câu hỏi tự kiểm tra:**

1. Cấu hình cluster được dùng để tạo và quản lý đối tượng SDK nào?
2. Thành phần nào đóng vai trò cầu nối để Spring Data repository sử dụng cluster/bucket?
3. Vì sao đổi `@Collection("products")` thành `@Collection("orders")` không thể chuyển document sang bucket khác?
4. Nếu `repository.save(...)` hoạt động nhưng `findBySku(...)` báo thiếu index, nên xử lý ở tầng nào?
5. Nếu service tự gọi `Cluster.connect(...)` mỗi request, rủi ro vận hành là gì?
6. Ai phải đóng `ClusterEnvironment` nếu bạn tự xây dựng SDK client bên ngoài Spring?

**Hướng trả lời:** `ClusterEnvironment` mô tả môi trường client; `Cluster` đại diện cluster; `Bucket` là handle đến bucket; `CouchbaseClientFactory` đưa các handle vào Spring Data. Collection nằm trong bucket, Query cần index riêng, cluster/environment nên được tái sử dụng và tài nguyên SDK do người tạo quản lý vòng đời.

**Tiêu chí hoàn thành:** giải thích đúng quan hệ bốn đối tượng, chỉ ra được keyspace `inventory.catalog.products`, viết được một phép đọc KV bằng repository hoặc SDK, xác định đúng nguyên nhân khi KV chạy nhưng truy vấn SQL++ thất bại.

## 15. Tổng kết

`ClusterEnvironment` quản lý thiết lập/tài nguyên nền của SDK; `Cluster` cung cấp kết nối và API tới cluster; `Bucket` xác định một vùng dữ liệu trong cluster; còn `CouchbaseClientFactory` là cầu nối do Spring Data Couchbase dùng để cấp các handle SDK cho mapping, template và repository.

Thiết kế đúng bốn lớp này giúp tránh tạo client trùng lặp, nhầm bucket với collection và đóng tài nguyên sai vòng đời. Từ nền đó, bạn có thể sử dụng `CouchbaseTemplate` hoặc repository để ánh xạ document, lập kế hoạch index SQL++, xử lý TTL/CAS, xây dựng giao dịch và lựa chọn API reactive theo yêu cầu về hiệu năng, nhất quán và vận hành.

