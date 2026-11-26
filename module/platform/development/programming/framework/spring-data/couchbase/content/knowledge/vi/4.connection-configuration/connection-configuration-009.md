# Tùy chỉnh môi trường SDK theo nhu cầu ứng dụng

## 1. Vì sao cần tùy chỉnh môi trường Couchbase SDK?

Một ứng dụng **Spring Data Couchbase** có thể chạy tốt với cấu hình Spring Boot mặc định, nhưng môi trường thực tế không phải lúc nào cũng giống nhau. Dịch vụ chạy trong Kubernetes có thể cần cách xử lý mạng khác máy local; cluster có TLS yêu cầu chuỗi chứng chỉ đáng tin cậy; dịch vụ có SLA thấp cần giới hạn timeout chặt hơn; hệ thống giao dịch cao cần quan sát độ trễ theo từng loại thao tác.

Trong module **SPRING_DATA_COUCHBASE**, hạ tầng kết nối phục vụ document mapping, `CouchbaseRepository`, `CouchbaseTemplate` và truy vấn SQL++. Để vận hành tin cậy với bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive API, đôi khi cần điều chỉnh **môi trường SDK** thay vì chỉ đổi repository hay entity.

Đối tượng trung tâm ở đây là `com.couchbase.client.java.env.ClusterEnvironment` của Couchbase Java SDK.

**Mục tiêu học tập:**

- Phân biệt cấu hình thuộc **SDK environment** với cấu hình **cluster**, **bucket** và **mapping**.
- Chọn giữa cấu hình mặc định bằng Spring Boot properties, một bean customizer và khởi tạo SDK thủ công.
- Điều chỉnh timeout, TLS/trust, kết nối mạng, thông số I/O và quan sát hoạt động mà không tạo client trùng lặp.
- Tổ chức các profile local/staging/production để không đưa thiết lập phát triển thiếu an toàn vào production.
- Kiểm chứng cấu hình qua hoạt động KV/SQL++ và các chỉ số vận hành, thay vì chỉ kiểm tra ứng dụng khởi động.
- Hiểu tác động tới API đồng bộ, reactive, độ nhất quán và vòng đời tài nguyên.

Các ví dụ trình bày theo cách tổ chức phổ biến của **Spring Boot 3.x**, Spring Data Couchbase và Couchbase Java SDK 3.x tương thích. Tên API/property nâng cao có thể thay đổi theo phiên bản; hãy đối chiếu tài liệu, metadata cấu hình và dependency management của bản thực tế.

## 2. Đặt `ClusterEnvironment` đúng vị trí trong kiến trúc

Các tầng làm những việc khác nhau:

~~~mermaid
flowchart TD
    A["Spring Boot configuration<br/>application.yml / secret / profile"] --> B["ClusterEnvironment<br/>Timeout, TLS, I/O, logging/tracing"]
    A --> C["Cluster<br/>Connection string + credentials"]
    B --> C
    C --> D["Bucket: inventory"]
    D --> E["Scope: catalog"]
    E --> F["Collection: products"]
    C --> G["CouchbaseClientFactory<br/>Spring Data"]
    D --> G
    G --> H["Converter / Mapping"]
    H --> I["Repository / CouchbaseTemplate"]
    I --> F
~~~

| Thành phần | Quyết định chính | Ví dụ |
| --- | --- | --- |
| `ClusterEnvironment` | Chính sách/tài nguyên hoạt động của SDK | Timeout, bảo mật truyền tải, cấu hình I/O, ghi nhận request chậm |
| `Cluster` | Cluster nào và xác thực thế nào | `couchbases://cb.example.internal`, user ứng dụng |
| `Bucket` / `Scope` / `Collection` | Tài nguyên dữ liệu nào được truy cập | `inventory.catalog.products` |
| `CouchbaseClientFactory` | Cầu nối SDK với tầng Spring Data | Cấp cluster/bucket cho template và repository |
| Mapping entity | Java object ánh xạ vào document nào | `@Document`, `@Id`, `@Scope`, `@Collection` |

**Ví dụ:** lỗi Query service thiếu index không được giải quyết bằng cách thay `ClusterEnvironment`. Lỗi truy cập sai collection cũng không do environment; phải kiểm tra bucket và entity mapping. Environment chỉ phù hợp để giải quyết những nhu cầu mang tính **client policy và tài nguyên SDK**.

### 2.1. Không đồng nhất environment với một kết nối TCP

`ClusterEnvironment` không phải một socket độc lập hay một connection string. Nó mô tả cấu hình và sở hữu/tham gia quản lý tài nguyên nền mà SDK dùng. `Cluster` mới là client đại diện cluster; từ cluster ta lấy các handle bucket/scope/collection.

Vì vậy “tùy chỉnh môi trường” không có nghĩa là tạo `Cluster.connect(...)` mới ở mỗi request. Một SDK environment và cluster được dùng lâu dài phù hợp hơn với ứng dụng có nhiều thao tác song song.

## 3. Khi nào nên giữ mặc định, khi nào cần tùy chỉnh?

Không phải mọi dự án đều cần một lớp `@Configuration` mới. Bắt đầu bằng câu hỏi: **yêu cầu nào thực sự khác mặc định?**

| Nhu cầu | Cách xử lý ưu tiên | Vì sao |
| --- | --- | --- |
| Chỉ cần địa chỉ, user/password và bucket | Spring Boot properties | Đơn giản, ít bean thủ công |
| Điều chỉnh connect/KV/Query timeout được Boot hỗ trợ | `spring.couchbase.env.timeouts.*` | Dễ phân tách theo môi trường |
| Cần tùy chỉnh SDK builder vượt các property Boot hỗ trợ | `ClusterEnvironmentBuilderCustomizer` nếu phiên bản có | Giữ vòng đời bean do Spring Boot quản lý |
| Viết ứng dụng SDK thuần, không dùng Spring Data | Tạo `ClusterEnvironment` và `Cluster` trực tiếp | Tự kiểm soát SDK và shutdown |
| Hệ thống có nhiều cluster hoặc chính sách TLS khác nhau | Thiết kế nhiều client/factory có chủ đích | Tránh dùng lẫn credentials, topology và resource policy |
| Cần đổi collection của entity | Mapping/`@Collection` | Không phải nhu cầu tùy chỉnh environment |
| Query SQL++ chậm vì thiếu index | Thiết kế index và truy vấn | Tăng timeout không giải quyết gốc rễ |

**Quy tắc thực hành:** dùng cấu hình ở tầng **cao nhất vẫn đáp ứng chính xác yêu cầu**, rồi chỉ đi xuống SDK khi có lý do rõ. Điều chỉnh cùng một tham số ở nhiều lớp có thể khiến khó xác định giá trị nào có hiệu lực cuối cùng.

## 4. Điểm xuất phát: Spring Boot auto-configuration

Với ứng dụng đồng bộ, dependency thường là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Một `application.yml` nền tảng:

~~~yaml
spring:
  application:
    name: inventory-service
  couchbase:
    connection-string: "${CB_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${CB_BUCKET:inventory}"
~~~

Hai nhóm property không thay thế nhau:

- `spring.couchbase.*` cấu hình **kết nối SDK tới cluster**, bao gồm môi trường SDK.
- `spring.data.couchbase.*` cấu hình **tầng Spring Data**, nổi bật là bucket mặc định.

`spring.couchbase.connection-string` xác định seed nodes của cluster. Bucket không được lấy từ phần path trong connection string. Scope/collection của entity có thể được chỉ định bằng annotation hoặc cơ chế mapping tương ứng.

Một ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
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

    protected ProductDocument() { }

    public ProductDocument(String id, String sku, String name) {
        this.id = id;
        this.sku = sku;
        this.name = name;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
}
~~~

Environment không tự provision bucket/scope/collection trên Couchbase Server; chúng phải tồn tại, và user phải được cấp RBAC thích hợp.

## 5. Cách 1: tùy chỉnh qua property đã được Spring Boot hỗ trợ

Khi chỉ cần điều chỉnh thời gian chờ, không nhất thiết phải tự tạo `ClusterEnvironment`. Ví dụ:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
    env:
      timeouts:
        connect: 10s
        kv: 2s
        query: 8s

  data:
    couchbase:
      bucket-name: inventory
~~~

Nhóm `spring.couchbase.env.timeouts.*` được dùng để đưa các giới hạn tương ứng vào cấu hình SDK theo cơ chế Boot phiên bản đang chạy.

| Thuộc tính | Tác dụng | Không xử lý được |
| --- | --- | --- |
| `connect` | Ngân sách thiết lập kết nối/bootstrap | DNS sai, firewall chặn, chứng chỉ không tin cậy |
| `kv` | Ngân sách thao tác KV theo document ID | SQL++ thiếu chỉ mục |
| `query` | Ngân sách request Query/SQL++ | Bucket bị thiếu, quyền KV bị từ chối |

Các giá trị `10s`, `2s` và `8s` chỉ minh họa; không phải đề xuất mặc định cho production. Chọn ngưỡng dựa trên phân bố latency, SLA và retry budget thực tế.

### 5.1. Vì sao phân biệt KV và Query timeout?

Các thao tác như `repository.findById(id)` thường sử dụng Key-Value API; các phương thức tìm theo thuộc tính như `findBySku(sku)` thường dùng SQL++ và cần Query service/index.

Một ứng dụng có thể đọc bằng ID thành công nhưng tìm theo SKU thất bại vì thiếu secondary index. Nếu chỉ tăng `query`, lỗi nền vẫn tồn tại.

### 5.2. Đưa ngưỡng ra môi trường triển khai

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: "${CB_CONNECT_TIMEOUT:10s}"
        kv: "${CB_KV_TIMEOUT:2s}"
        query: "${CB_QUERY_TIMEOUT:8s}"
~~~

`CB_*` là tên biến môi trường **do ví dụ ứng dụng quy ước**, được Spring chèn bằng placeholder. Việc đặt giá trị ở profile/environment cho phép thay đổi chính sách mà không sửa Java code. Đừng dùng fallback local thiếu an toàn khi triển khai production.

Ngoài timeout, một số phiên bản Boot có thêm nhóm property SDK khác; **không suy luận tên YAML từ tên setter của Java SDK**. Kiểm tra configuration metadata của starter đúng phiên bản để biết property nào được hỗ trợ và property nào phải tùy chỉnh qua Java.

## 6. Cách 2: tùy chỉnh builder trong Spring Boot

Khi một cấu hình SDK không được Boot hỗ trợ trực tiếp bằng YAML, Spring Boot cung cấp điểm mở rộng theo builder trong các phiên bản phù hợp: `ClusterEnvironmentBuilderCustomizer`.

Ví dụ chỉ minh họa cách làm đối với timeout:

~~~java
package com.example.inventory.config;

import java.time.Duration;
import com.couchbase.client.java.env.TimeoutConfig;
import org.springframework.boot.autoconfigure.couchbase.ClusterEnvironmentBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CouchbaseSdkCustomization {

    @Bean
    ClusterEnvironmentBuilderCustomizer customSdkEnvironment() {
        return builder -> builder.timeoutConfig(
                TimeoutConfig
                        .kvTimeout(Duration.ofSeconds(2))
                        .queryTimeout(Duration.ofSeconds(8))
        );
    }
}
~~~

Lớp này **không** gọi `ClusterEnvironment.builder().build()` và **không** tạo `Cluster.connect()` thủ công. Nó cung cấp một customizer để quá trình auto-configuration áp dụng lên SDK environment builder của Spring Boot.

**Cần lưu ý:**

1. Nếu các ngưỡng đã được hỗ trợ bởi YAML, thường chỉ dùng YAML là đủ; đoạn customizer ở trên nhằm minh họa cơ chế mở rộng.
2. Nếu dùng đồng thời customizer với `spring.couchbase.env.timeouts.*`, phải kiểm chứng thứ tự áp dụng và giá trị hiệu lực trong **đúng phiên bản Boot**. Không phụ thuộc vào thứ tự bean “tình cờ”.
3. Việc đặt `timeoutConfig(...)` trên builder có thể ảnh hưởng cấu hình timeout đã thiết lập trước đó; cần kiểm tra cách builder phối hợp cấu hình.
4. Nếu bạn khai báo bean `ClusterEnvironment`/`Cluster` hoàn toàn thủ công, customizer của Boot có thể không được áp dụng như trong mô hình auto-configuration. Khi đó xác minh bean nào thật sự được Spring Data sử dụng.
5. Hãy giữ số lượng customizer nhỏ và có mục đích; một customizer cho từng thông số không nhất thiết dễ kiểm soát hơn một cấu hình thống nhất.

Những API tùy chỉnh sâu hơn — TLS/trust, I/O, telemetry — cần dùng đúng builder method của Couchbase Java SDK tương ứng. Nên kiểm tra thay đổi qua log, health, metrics và phép thử thực tế, không chỉ qua việc class biên dịch.

## 7. Cách 3: tự tạo `ClusterEnvironment` bằng Couchbase Java SDK

Với một chương trình SDK độc lập, hoặc một kiến trúc thực sự tự quản lý kết nối, có thể xây dựng environment trực tiếp:

~~~java
import java.time.Duration;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.TimeoutConfig;

ClusterEnvironment environment = ClusterEnvironment.builder()
        .timeoutConfig(
                TimeoutConfig
                        .connectTimeout(Duration.ofSeconds(10))
                        .kvTimeout(Duration.ofSeconds(2))
                        .queryTimeout(Duration.ofSeconds(8))
        )
        .build();
~~~

Sau đó sử dụng environment để tạo cluster:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

Cluster cluster = Cluster.connect(
        connectionString,
        ClusterOptions.clusterOptions(username, password)
                .environment(environment)
);
~~~

`connectionString`, `username`, `password` lấy từ cấu hình/secret ngoài source code. Environment được dùng chung cho các request; không tạo mới ở từng lời gọi truy vấn.

### 7.1. Vòng đời của tài nguyên tự quản lý

Vì ứng dụng tự tạo environment, ứng dụng phải giải phóng tài nguyên khi không dùng nữa:

~~~java
try {
    // Thao tác KV/Query qua cluster đã tạo.
} finally {
    try {
        cluster.disconnect();
    } finally {
        environment.shutdown();
    }
}
~~~

Ví dụ trên giả định cluster đã tạo thành công trước `try`. Trong chương trình production cần xử lý cả lỗi xảy ra **trong quá trình tạo cluster**, tránh làm environment bị rò rỉ khi bootstrap thất bại.

Một mô hình đầy đủ có điều kiện dọn dẹp:

~~~java
Cluster cluster = null;
try {
    cluster = Cluster.connect(
            connectionString,
            ClusterOptions.clusterOptions(username, password)
                    .environment(environment)
    );

    // Hoạt động với cluster, bucket, collection...
} finally {
    try {
        if (cluster != null) {
            cluster.disconnect();
        }
    } finally {
        environment.shutdown();
    }
}
~~~

Nếu SDK environment do **Spring** tạo và quản lý, để container thực thi cơ chế destroy tương ứng. Không gọi `disconnect()`/`shutdown()` từ một service nghiệp vụ trong khi repository khác còn sử dụng chung tài nguyên.

## 8. Kết nối bảo mật: TLS, trust và danh tính

Ứng dụng production thường yêu cầu TLS:

~~~text
# Local không TLS, khi môi trường cho phép
couchbase://127.0.0.1

# Endpoint có TLS
couchbases://cb.example.internal
~~~

Khi dùng TLS, cần quan tâm:

- **Địa chỉ và hostname:** hostname trong connection string phải phù hợp với chứng chỉ của server.
- **Chuỗi CA tin cậy:** runtime/SDK phải tin được chứng chỉ server theo cơ chế trust được hỗ trợ.
- **Network policy:** các cổng dịch vụ TLS của Couchbase có thể khác cổng môi trường không TLS.
- **Xác thực user:** TLS mã hóa và xác minh kênh; username/password hoặc cơ chế auth tương ứng vẫn cần có hiệu lực.
- **Secrets:** không commit private key, password hoặc nội dung trust material nhạy cảm vào repository.

Tùy phiên bản SDK, môi trường có thể nhận cấu hình security/trust qua builder hoặc các cơ chế chứng chỉ được runtime hỗ trợ. Chỉ dùng API trust chính thức theo **đúng phiên bản** và chính sách triển khai. Không tắt xác thực chứng chỉ trong production để vượt qua TLS handshake failure.

### 8.1. Những lỗi trông giống timeout nhưng không phải do ngưỡng

Một kết nối TLS thất bại có thể được báo là handshake/certificate error; một địa chỉ không reachable có thể thành connect timeout. Đọc **loại exception** và ngữ cảnh kèm theo trước khi tăng ngưỡng. Nếu trust chain sai, chờ thêm thời gian không làm chứng chỉ trở nên hợp lệ.

### 8.2. Phân quyền không được “sửa” bằng tùy chỉnh environment

RBAC thuộc phía Couchbase Server và danh tính ứng dụng. Một user có thể kết nối cluster nhưng không được đọc `inventory.catalog.products`. Cấu hình timeout, I/O hoặc TLS khác không cấp thêm quyền cho user.

Dùng nguyên tắc quyền tối thiểu theo bucket/scope/collection và nghiệp vụ. Với truy vấn SQL++, cần xem thêm quyền dịch vụ Query và quyền/index phù hợp.

## 9. Network topology, seed node và địa chỉ quảng bá

Một cluster có thể chạy ở mạng nội bộ, trong Kubernetes hoặc dịch vụ quản lý. Couchbase SDK dùng seed node ban đầu và thông tin topology để tìm các node và dịch vụ tiếp theo.

~~~mermaid
sequenceDiagram
    participant App as Java SDK Client
    participant Seed as Seed Node
    participant Topo as Cluster Topology
    participant Data as Data/Query Node
    App->>Seed: Bootstrap qua connection string
    Seed-->>App: Thông tin cluster và node
    App->>Topo: Cập nhật routing
    App->>Data: KV hoặc Query tới node phù hợp
    Data-->>App: Response
~~~

Một số kiểu sai:

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Đến được seed nhưng KV timeout | Node trong topology có địa chỉ không reachable | Địa chỉ được quảng bá, route, firewall |
| Local chạy, container không chạy | DNS/NAT/bridge network khác nhau | Kiểm tra từ chính runtime container |
| Có TLS nhưng Query service unreachable | Cổng dịch vụ/TLS không được mở đúng | Connectivity tới các node/dịch vụ |
| Một số request chạy, số khác lỗi | Một phần cluster/network không reachable | Node mapping và telemetry |
| Đổi endpoint nhưng vẫn dùng cluster cũ | Client còn sống với cấu hình cũ | Cách rollout/refresh bean |

Đừng giả định DNS của máy developer giống DNS trong pod hoặc container production. Khi mạng có NAT, alternate address hoặc cấu hình DNS SRV, dùng tùy chọn SDK/cluster phù hợp theo hướng dẫn mạng của môi trường đó. **Không tự bật những thiết lập networking chỉ vì chúng có trong SDK.** Mỗi tùy chọn nên có giả thuyết và cách kiểm chứng rõ ràng.

## 10. Tùy chỉnh timeout theo *workload*, không theo cảm tính

Đặt timeout là phần dễ thấy nhất của môi trường SDK, nhưng cần gắn với loại thao tác:

| Workload | Đường đi chính | Điểm cần cân nhắc |
| --- | --- | --- |
| Đọc chi tiết sản phẩm theo ID | KV Get | Data service, mạng, KV timeout |
| Ghi tồn kho có durability | KV mutation | Durability level, durable KV budget, trạng thái mutation |
| Tìm sản phẩm theo SKU | SQL++ Query | Query/index service, query plan, query timeout |
| Đọc sau ghi bằng SQL++ | Query/Index | Scan consistency và thời gian index bắt kịp |
| Nhiều query song song | SDK + server | Hàng đợi, số request đồng thời, memory và throughput |

Thời gian chờ nên được thiết kế trong **deadline tổng** của request:

~~~text
HTTP deadline: 3 s (ví dụ)
  ├── Validate: 0.2 s
  ├── KV read: 0.5 s
  ├── Query:   1.5 s
  └── Nghiệp vụ/serialize/mạng: 0.8 s
~~~

Đây là minh họa cách phân bổ ngân sách, không phải chuẩn bắt buộc. Nếu một request có retry, phải tính tổng thời gian các lần thử. Nếu nhiều thao tác chạy song song, ngân sách theo đường găng khác với tổng các thao tác nối tiếp.

### 10.1. Override một thao tác thay vì đổi cả environment

SDK Java hỗ trợ per-operation options cho một số thao tác:

~~~java
import java.time.Duration;
import com.couchbase.client.java.kv.GetOptions;

var result = products.get(
        "product::SKU-001",
        GetOptions.getOptions().timeout(Duration.ofMillis(700))
);
~~~

Với SQL++:

~~~java
import java.time.Duration;
import com.couchbase.client.java.query.QueryOptions;

var rows = cluster.query(
        "SELECT p.sku FROM `inventory`.`catalog`.`products` AS p LIMIT 10",
        QueryOptions.queryOptions().timeout(Duration.ofSeconds(3))
);
~~~

Những ví dụ này giới hạn **từng request** mà không thay cấu hình chung cho mọi repository và service. Trong Spring Data, điểm can thiệp per-operation phụ thuộc API của `CouchbaseTemplate`/repository ở phiên bản đang dùng.

### 10.2. Không tăng timeout để che lỗi thiếu index

Một query tìm theo `sku` có thể cần index:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`catalog`.`products`(`sku`);
~~~

Nếu `repository.findById(...)` chạy bình thường nhưng `findBySku(...)` chậm, kiểm tra Query service và kế hoạch truy vấn/secondary index trước khi thay environment. Index không được tạo chỉ bởi `ClusterEnvironment` hay `CouchbaseClientFactory`.

## 11. Các tùy chọn I/O và connection resource

SDK environment còn có thể điều khiển các chính sách liên quan network I/O, kết nối và tài nguyên nội bộ theo API được hỗ trợ ở phiên bản tương ứng.

**Những điều cần đánh giá trước khi chỉnh:**

1. **Thông lượng và concurrency:** số lượng thao tác đang chạy đồng thời có vượt quá năng lực cluster hoặc thread/event-loop của ứng dụng?
2. **Độ trễ:** vấn đề phát sinh ở KV, Query, TLS, mạng hay trong code xử lý business?
3. **Số kết nối và tài nguyên:** việc tăng thông số có làm tăng file descriptors, bộ nhớ hoặc tải server vượt khả năng?
4. **Hạ tầng mạng:** NAT, proxy, load balancer, keepalive và timeout của thiết bị trung gian có ảnh hưởng tới kết nối lâu sống?
5. **Phiên bản SDK:** tên tùy chọn I/O, ý nghĩa và default có thể thay đổi.

Không đặt một số thread, connection pool hoặc endpoint count tùy tiện mà thiếu số đo trước/sau. SDK đã có cơ chế quản lý I/O và routing; đôi khi nút thắt là truy vấn thiếu index hoặc server thiếu tài nguyên, không phải số kết nối phía client.

### 11.1. Mỗi request không tạo một `ClusterEnvironment`

Ví dụ anti-pattern:

~~~java
// KHÔNG KHUYẾN NGHỊ: khởi tạo SDK client trong mỗi HTTP request
public String loadProduct(String id) {
    var env = ClusterEnvironment.builder().build();
    var cluster = Cluster.connect(
            endpoint,
            ClusterOptions.clusterOptions(username, password)
                    .environment(env)
    );
    try {
        return cluster.bucket("inventory")
                .scope("catalog")
                .collection("products")
                .get(id)
                .contentAsObject()
                .getString("sku");
    } finally {
        try {
            cluster.disconnect();
        } finally {
            env.shutdown();
        }
    }
}
~~~

Dù có đóng tài nguyên đúng cuối lời gọi, cách này liên tục tốn chi phí bootstrap, tạo tài nguyên và thu hồi. Nên dùng SDK/client factory đã được Spring quản lý ở phạm vi ứng dụng, inject vào service và tái sử dụng.

## 12. Telemetry: tùy chỉnh môi trường phải có khả năng đo

Khi thay cấu hình environment, cần biết thay đổi **cải thiện** hay **làm xấu** hệ thống.

Các tín hiệu hữu ích:

- Latency P50/P95/P99 của KV read, KV mutation và SQL++ riêng biệt.
- Tỷ lệ timeout theo loại `connect`, `kv`, `query`; không gộp thành một con số duy nhất.
- Nguyên nhân retry và số lần retry SDK/ứng dụng.
- Tải, CPU, memory, queue và độ sẵn sàng của Data/Query/Index service.
- Request bị chậm, response mồ côi và thông tin request tracing/observability do SDK hỗ trợ.
- Trạng thái DNS, topology refresh và thay đổi connectivity trong thời gian triển khai.
- Độ trễ của các truy vấn được phân nhóm theo keyspace và query pattern.

Couchbase SDK có cơ chế logging/tracing/metrics được tích hợp hoặc có thể kết nối với hệ thống quan sát tùy phiên bản. Nếu điều chỉnh reporter, threshold tracer hay cấu hình log qua builder, cần kiểm tra tên API chính xác và khối lượng telemetry tạo ra. Bật ghi log chi tiết thường xuyên ở production có thể tốn I/O và lộ thông tin nhạy cảm.

### 12.1. Một quy trình điều chỉnh có thể kiểm chứng

~~~mermaid
flowchart LR
    A["Xác định SLA và lỗi hiện tại"] --> B["Đo baseline theo KV/Query"]
    B --> C["Đưa ra giả thuyết"]
    C --> D["Chỉnh một nhóm cấu hình"]
    D --> E["Kiểm thử tải + lỗi mạng"]
    E --> F{"Đạt mục tiêu?"}
    F -- "Có" --> G["Rollout có quan sát"]
    F -- "Không" --> H["Rollback / phân tích"]
    H --> C
~~~

Thay một nhóm cấu hình tại một thời điểm giúp phân biệt tác động. Đừng đồng loạt tăng thread count, timeout, retry và query limit rồi kết luận một tùy chọn cụ thể đã giải quyết vấn đề.

## 13. Reactive và non-blocking I/O

Spring Data Couchbase hỗ trợ `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`; Couchbase Java SDK cũng hỗ trợ API reactive. Chúng dùng cùng các khái niệm environment, cluster, bucket, scope và collection.

Ví dụ lấy dữ liệu bằng SDK reactive:

~~~java
import com.couchbase.client.java.kv.GetResult;
import reactor.core.publisher.Mono;

Mono<GetResult> result =
        products.reactive().get("product::SKU-001");
~~~

Điểm cần nhớ:

- Reactive **không** yêu cầu tạo một `ClusterEnvironment` cho từng `Mono` hay subscriber.
- Ngân sách timeout SDK vẫn áp dụng cho thao tác liên quan; một operator Reactor `timeout` giới hạn thêm pipeline ở tầng ứng dụng, không thay thế cấu hình SDK.
- Tránh `block()` trong event-loop của WebFlux; việc blocking có thể làm giảm throughput dù SDK cấu hình I/O tốt.
- Retry hoặc resubscribe một `Mono` chứa mutation phải xét idempotency, vì có trường hợp kết quả ghi bị mơ hồ.
- Reactive không tự tạo chỉ mục SQL++, cũng không tự bảo đảm scan consistency mong muốn.

Mở rộng khả năng đồng thời ở client không làm cluster có thêm CPU hoặc Query service. Khi tăng tải, theo dõi backpressure, pending requests và tài nguyên của cả ứng dụng lẫn Couchbase.

## 14. Nhiều cluster, nhiều môi trường: khi nào tách biệt?

Một cluster có thể chứa nhiều bucket; cùng một environment/cluster SDK có thể phục vụ nhiều bucket khi chính sách phù hợp. Nhưng với hai cluster khác mạng, khác TLS trust hoặc khác quyền, cần xem xét mô hình nhiều client.

| Tình huống | Thiết kế thường hợp lý |
| --- | --- |
| Một cluster, một bucket, nhiều collection | Một client/factory mặc định, mapping theo `@Scope`/`@Collection` |
| Một cluster, nhiều bucket | Chung `Cluster` nếu phù hợp; cấu hình rõ factory/template theo bucket |
| Hai cluster khác credentials/topology | Client `Cluster` riêng, phân định bean và lifecycle |
| Hai nhóm cluster khác TLS/trust policies | Có thể cần `ClusterEnvironment` riêng theo chính sách |
| Nhiều tenants | Giới hạn số client, quản lý bí mật và cô lập quyền có chủ đích |

Nếu tự tạo hai environment, phải biết environment nào được dùng bởi cluster nào và ai sẽ shutdown. Không tự thêm `ClusterEnvironment` bean thứ hai với hy vọng Spring Boot tự chọn đúng dựa trên tên bucket.

Tương tự, tên collection không phải tên cluster; `@Collection("orders")` không chuyển một repository sang bucket `orders` hoặc cluster khác.

## 15. Kiểm chứng cấu hình sau khi tùy chỉnh

Một `ClusterEnvironment` được xây thành công chưa bảo đảm dữ liệu truy cập đúng. Cần kiểm chứng theo từng lớp.

### 15.1. Đường kiểm tra đề xuất

1. **Property và bean:** xác nhận active profile, giá trị cấu hình có hiệu lực, một nguồn sự thật cho environment và client factory.
2. **Connectivity:** kiểm tra DNS, TLS, các node/port liên quan trong runtime thật.
3. **Authentication/RBAC:** xác thực bằng đúng tài khoản ứng dụng, không sử dụng admin account chỉ để vượt lỗi.
4. **Keyspace:** bucket, scope, collection đã tồn tại và user có quyền.
5. **KV:** thử một lệnh đọc ID không tồn tại hoặc `exists` trên đúng collection, không ghi dữ liệu.
6. **SQL++:** kiểm tra Query service, index trên đúng keyspace và kế hoạch truy vấn.
7. **Latency:** đo riêng connect/KV/Query và quan sát tỷ lệ lỗi dưới tải mục tiêu.
8. **Shutdown/rollout:** xác nhận tài nguyên do Spring quản lý không bị đóng sớm và secret rotation có hiệu lực theo deployment.

### 15.2. Smoke test KV an toàn dành cho local

Giả sử ứng dụng đã sử dụng Spring Data Couchbase và có một `CouchbaseClientFactory` mặc định:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

@Configuration(proxyBeanMethods = false)
@Profile("local")
public class LocalCouchbaseSmokeTestConfig {

    @Bean
    ApplicationRunner checkKv(CouchbaseClientFactory factory) {
        return args -> {
            boolean found = factory.getBucket()
                    .scope("catalog")
                    .collection("products")
                    .exists("smoke::missing")
                    .exists();

            System.out.println("KV reachable; document exists: " + found);
        };
    }
}
~~~

`false` vẫn là kết quả hợp lệ nếu document không tồn tại nhưng thao tác được thực hiện thành công. Smoke test chỉ xác nhận đường KV tới keyspace đã chọn; không chứng minh index SQL++ đã được tạo hay transaction hoạt động.

Dùng `@Profile("local")` để tránh buộc mọi bản production khởi động phải gọi probe đồng bộ. Trong môi trường thật, readiness nên có timeout/rate limit và chính sách kiểm tra phù hợp.

## 16. Khắc phục sự cố sau khi tùy chỉnh

| Dấu hiệu | Kiểm tra trước | Điều chỉnh đúng tầng |
| --- | --- | --- |
| Local chạy nhưng production không kết nối | Endpoint, TLS trust, DNS, node address, network policy | Kết nối/bảo mật SDK |
| Spring tạo bean nhưng `findById` timeout | Data service, bucket/collection, node routing, KV budget | Connectivity/KV; không chỉ nhìn bean |
| `findById` ổn, `findBySku` chậm | Query service, index, execution plan, consistency | Query/index trước khi tăng query timeout |
| Đổi YAML timeout nhưng độ trễ không đổi | Có customizer/bean tự tạo ghi đè hay không? | Nguồn cấu hình có hiệu lực |
| Cấu hình customizer không tác động | Auto-configuration có tạo environment không, custom bean nào thay thế? | Lifecycle và wiring |
| Timeout nhiều hơn sau khi tăng concurrency | SDK queue, server load, pool resources | Đo bottleneck trước khi mở rộng |
| Một request đóng cluster khiến request khác lỗi | Service tự gọi `disconnect()` trên tài nguyên chung | Để owner/container quản lý shutdown |
| TLS handshake lỗi | CA, hostname, endpoint, trust chain | Security/trust; không tắt verification |
| Query có kết quả trễ sau ghi | Scan consistency và tiến độ index | Query consistency, không phải connect timeout |
| Durable write timeout rồi dữ liệu vẫn có | Kết quả mutation có thể mơ hồ | Idempotency, CAS/`@Version`, đối soát |

### 16.1. Timeout ghi không đồng nghĩa server chắc chắn chưa ghi

Đặc biệt với mutation, nếu SDK trả `AmbiguousTimeoutException`, ứng dụng không thể kết luận chắc chắn thao tác được áp dụng hay chưa. Không retry mù một nghiệp vụ không idempotent như tăng số lượng, trừ tiền hoặc tạo đơn hàng mới mỗi lần.

Có thể sử dụng document ID ổn định, idempotency key, kiểm tra lại trạng thái, CAS hoặc `@Version` theo nghiệp vụ. Đây là quyết định về **tính đúng đắn dữ liệu**, không phải chỉ là một property trong `ClusterEnvironment`.

## 17. Bài tập tình huống: cấu hình cho hai môi trường

Một dịch vụ bán hàng sử dụng:

~~~text
Bucket: inventory
Scope: catalog
Collection: products
~~~

Môi trường local kết nối `couchbase://127.0.0.1`; production dùng cluster có TLS. Local thường chỉ có một node, trong khi production có nhiều node và dịch vụ Query riêng. Nhóm vận hành phát hiện:

- Production thỉnh thoảng lỗi TLS handshake sau thay đổi endpoint.
- `findById` ổn định nhưng `findBySku` chậm vào giờ cao điểm.
- Nhóm đề xuất tạo `Cluster.connect()` mới mỗi request và tăng tất cả timeout lên 60 giây.
- Có hai nơi khai báo cùng một timeout: YAML và Java customizer.

**Yêu cầu:**

1. Xác định những việc phải kiểm tra trước khi sửa SDK environment: TLS/trust, DNS/topology, dịch vụ Query và secondary index.
2. Chọn **một nguồn cấu hình có thể kiểm chứng** cho từng timeout; giải thích vì sao YAML đủ nếu Boot đã hỗ trợ property.
3. Giải thích vì sao tạo client mỗi request là anti-pattern và nên tái sử dụng `Cluster`/factory.
4. Thiết lập ngân sách cho API tổng thể thay vì tăng ngưỡng đồng loạt mà không đo.
5. Đề xuất smoke test KV và kiểm tra SQL++ độc lập.
6. Chỉ ra điều gì cần làm nếu mutation timeout tạo ra kết quả ghi mơ hồ.

Index minh họa cho `findBySku`:

~~~sql
CREATE INDEX ix_products_sku
ON `inventory`.`catalog`.`products`(`sku`);
~~~

**Hướng giải:** lỗi TLS cần kiểm tra chứng chỉ/hostname/trust; query chậm cần kiểm tra Query service/index/plan; client phải có vòng đời dài; timeout phải phù hợp SLA và nguồn cấu hình rõ ràng. Với mutation mơ hồ cần đối soát và idempotency/CAS. Một thay đổi SDK environment chỉ được xem là thành công khi có bằng chứng từ KV, Query và metrics dưới tải.

## 18. Tổng kết

`ClusterEnvironment` là nơi điều chỉnh **chính sách và tài nguyên Couchbase Java SDK**, không phải nơi khai báo entity, repository hay chọn collection nghiệp vụ. Với Spring Boot, ưu tiên các property được hỗ trợ; khi thật sự cần tùy biến sâu, sử dụng điểm mở rộng `ClusterEnvironmentBuilderCustomizer` của phiên bản tương thích hoặc một cấu hình SDK thủ công có owner rõ ràng.

Tùy chỉnh hiệu quả phải đi cùng bảo mật TLS, quản lý secret, hiểu biết về topology, timeout theo workload, đo telemetry, lifecycle client dùng chung và kiểm thử đường KV/SQL++ thực tế. Từ nền tảng đó, Spring Data Couchbase có thể tiếp tục triển khai document mapping, repository, `CouchbaseTemplate`, index, TTL, CAS, giao dịch và API reactive mà vẫn bảo đảm yêu cầu hiệu năng và tính nhất quán.

