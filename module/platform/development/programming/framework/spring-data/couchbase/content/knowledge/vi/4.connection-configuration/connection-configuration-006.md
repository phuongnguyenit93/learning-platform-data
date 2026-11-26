# Vòng đời và khả năng dùng chung các đối tượng kết nối

## 1. Vì sao vòng đời kết nối ảnh hưởng đến toàn bộ tầng dữ liệu?

Trong **Spring Data Couchbase** (module **SPRING_DATA_COUCHBASE**), các thao tác `save()`, `findById()`, truy vấn SQL++ qua repository hoặc `CouchbaseTemplate` đều cần hạ tầng Couchbase phía dưới. Nếu mỗi yêu cầu HTTP tự tạo một kết nối cluster rồi đóng ngay sau truy vấn, hệ thống phải liên tục khởi tạo tài nguyên mạng, xác thực, khám phá topology và dọn dẹp. Nếu một service đóng nhầm kết nối dùng chung, những service khác có thể bắt đầu lỗi dù code của chúng không thay đổi.

Bài học thuộc chương **Cấu hình kết nối**, tập trung vào **ai sở hữu tài nguyên, đối tượng nào nên dùng chung, sử dụng chung an toàn tới mức nào và lúc nào phải đóng**. Các ví dụ giả định Spring Boot 3.x, Spring Data Couchbase tương thích và Couchbase Java SDK 3.x; API nâng cao và cấu hình cụ thể cần đối chiếu theo phiên bản dự án.

Sau bài học, bạn có thể:

- Phân biệt vòng đời của `ClusterEnvironment`, `Cluster`, `Bucket`, `Scope`, `Collection` và `CouchbaseClientFactory`.
- Quyết định nên dùng một client dùng chung cho ứng dụng hay cần nhiều cluster/factory riêng.
- Để Spring Boot quản lý khởi tạo và đóng tài nguyên đúng ranh giới.
- Nhận diện sự khác nhau giữa **an toàn chia sẻ handle** và **nhất quán khi nhiều request cùng sửa một document**.
- Thiết kế bước kiểm tra sẵn sàng, quá trình dừng ứng dụng và xử lý lỗi vận hành phù hợp cho cả API đồng bộ và reactive.

> **Nguyên tắc trung tâm:** tạo các đối tượng kết nối lâu sống ở phạm vi ứng dụng, tái sử dụng chúng cho nhiều thao tác và đóng chúng tại ranh giới sở hữu. Mỗi thao tác chỉ tạo dữ liệu yêu cầu, kết quả và ngữ cảnh riêng của nó.

## 2. Cây sở hữu và phạm vi của từng đối tượng

Couchbase Java SDK cung cấp đối tượng kết nối ở nhiều tầng; Spring Data xây dựng repository/template trên những đối tượng đó:

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["ClusterEnvironment<br/>Thiết lập + tài nguyên SDK"]
    B --> C["Cluster<br/>Topology + dịch vụ cluster"]
    C --> D["Bucket handle"]
    D --> E["Scope handle"]
    E --> F["Collection handle"]
    C --> G["CouchbaseClientFactory<br/>Spring Data"]
    D --> G
    G --> H["CouchbaseTemplate / Converter"]
    H --> I["CouchbaseRepository"]
    I --> J["Service và các request song song"]
~~~

Sơ đồ thể hiện **mối quan hệ sử dụng**, không khẳng định mọi handle đều sở hữu trực tiếp hoặc tự đóng đối tượng bên dưới. Đặc biệt, việc gọi `cluster.bucket("inventory")` hay `bucket.scope("catalog")` chủ yếu lấy handle; thao tác đó chưa đủ chứng minh tài nguyên ở server sẵn sàng cho đọc/ghi.

| Đối tượng | Tầng thư viện | Phạm vi nên dùng | Đóng khi nào? |
| --- | --- | --- | --- |
| `ClusterEnvironment` | Couchbase Java SDK | Dùng chung cho những cluster tương thích chính sách SDK | Khi tất cả cluster sử dụng nó đã dừng; nếu tự tạo thì tự shutdown |
| `Cluster` | Couchbase Java SDK | Một client sống lâu cho cluster, credentials và cấu hình tương ứng | Khi owner ngừng sử dụng; gọi `disconnect()` nếu tự tạo |
| `Bucket` | Couchbase Java SDK | Handle có thể giữ và dùng lại cho nhiều thao tác trong bucket | Không tự đóng như một kết nối độc lập |
| `Scope` | Couchbase Java SDK | Handle cho scope trong bucket | Theo vòng đời cluster/bucket phía dưới |
| `Collection` | Couchbase Java SDK | Handle cho tập document cần đọc/ghi | Theo vòng đời client phía dưới |
| `CouchbaseClientFactory` | Spring Data Couchbase | Hạ tầng chia sẻ bởi template/repository trong ngữ cảnh bucket | Theo vòng đời context/bean do Spring quản lý |
| `CouchbaseTemplate` / repository | Spring Data Couchbase | Bean dùng chung, thường inject vào các service | Không được tự đóng SDK client khi xử lý request |
| `GetResult`, `JsonObject`, entity/DTO | Dữ liệu từng thao tác | Biến cục bộ hoặc payload từng yêu cầu | Thu gom theo vòng đời thao tác; không dùng như kết nối toàn cục |

**Dùng chung** trong bảng nghĩa là các handle và client thích hợp cho nhiều thao tác, bao gồm thao tác từ nhiều luồng, theo hợp đồng của SDK. Điều đó **không bảo đảm** mọi đối tượng dữ liệu mutable đi kèm, hay mọi phép cập nhật vào cùng document, đều tự nhiên an toàn trước xung đột nghiệp vụ.

## 3. `ClusterEnvironment`: một nơi quản lý tài nguyên SDK

`com.couchbase.client.java.env.ClusterEnvironment` gom chính sách và tài nguyên nền của Java SDK, chẳng hạn các cấu hình timeout, TLS, I/O và khả năng quan sát theo phiên bản. Tạo mới environment cho mỗi lời gọi truy vấn khiến ứng dụng phát sinh thêm tài nguyên cần quản lý.

Với SDK trực tiếp, cách tạo minh họa:

~~~java
import java.time.Duration;
import com.couchbase.client.java.env.ClusterEnvironment;
import com.couchbase.client.java.env.TimeoutConfig;

ClusterEnvironment environment = ClusterEnvironment.builder()
        .timeoutConfig(
                TimeoutConfig.kvTimeout(Duration.ofSeconds(3))
        )
        .build();
~~~

Environment được cấu hình **trước** khi đưa vào client cần dùng. Tránh thay đổi một cấu hình chung trong lúc request đang chạy và kỳ vọng mọi thao tác đang thực thi đều nhận một chính sách mới.

Một environment có thể phục vụ các cluster khác nhau khi yêu cầu SDK tương thích, nhưng không phải mọi hệ thống đều nên ép mọi cluster dùng chung environment. Ví dụ, hai cluster có trust policy hoặc nhu cầu phân vùng tài nguyên khác nhau có thể cần cấu hình riêng. Quyết định dựa trên yêu cầu thực tế và cách SDK quản lý tài nguyên, không dựa trên số lượng collection.

### Ai chịu trách nhiệm gọi `shutdown()`?

- Nếu **chính ứng dụng** tạo `ClusterEnvironment` bằng builder ở bên ngoài Spring, ứng dụng phải shutdown nó sau khi dừng các cluster đang sử dụng.
- Nếu **Spring Boot hoặc cấu hình Spring** tạo và sở hữu environment bean, hãy để container thực hiện cơ chế hủy bean khi `ApplicationContext` đóng.
- Không gọi `environment.shutdown()` trong một repository/service đang còn được các request khác dùng; điều đó có thể làm hỏng những client sử dụng chung tài nguyên môi trường.

## 4. `Cluster`: một client sống lâu cho nhiều thao tác

`com.couchbase.client.java.Cluster` là client SDK cung cấp điểm truy cập tới một Couchbase cluster cùng các dịch vụ như KV và Query. Bạn thường muốn **tái sử dụng** một instance cho cùng endpoint, danh tính đăng nhập và chính sách kết nối trong suốt vòng đời ứng dụng.

Ví dụ kết hợp environment đã có:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;

Cluster cluster = Cluster.connect(
        connectionString,
        ClusterOptions.clusterOptions(username, password)
                .environment(environment)
);
~~~

`connectionString`, `username` và `password` nên đến từ cấu hình môi trường/secret. Nếu một ứng dụng có hàng trăm request đồng thời, không cần hàng trăm lời gọi `Cluster.connect()`. Các yêu cầu dùng chung client và SDK điều phối I/O theo cơ chế nội bộ.

### Sai mẫu: mở cluster trong từng request

~~~java
// VÍ DỤ CẦN TRÁNH
public String loadSku(String id) {
    Cluster temporary = Cluster.connect(
            connectionString, username, password
    );
    try {
        return temporary.bucket("inventory")
                .scope("catalog")
                .collection("products")
                .get(id)
                .contentAsObject()
                .getString("sku");
    } finally {
        temporary.disconnect();
    }
}
~~~

Dù đoạn code dọn dẹp cluster sau mỗi thao tác, chi phí khởi tạo và đóng tài nguyên sẽ lặp lại theo số request. Trong ứng dụng Spring, nên inject client/factory/template do container quản lý và chỉ thực hiện thao tác trên handle sẵn có.

### Khi nào cần nhiều `Cluster`?

Một instance `Cluster` có thể mở nhiều bucket trong **cùng cluster**:

~~~java
var inventoryBucket = cluster.bucket("inventory");
var ordersBucket = cluster.bucket("orders");
~~~

Một cluster handle không đại diện cho một bucket cụ thể. Tuy nhiên, hai endpoint thuộc **hai cluster khác nhau**, hoặc hai danh tính có quyền khác nhau, có thể yêu cầu client riêng. Nếu tạo nhiều cluster, quản lý rõ mối quan hệ mỗi cluster với environment, thông tin xác thực, quota tài nguyên và vòng đời shutdown.

Không tạo cluster mới chỉ vì một entity dùng collection khác; nhiều collection trong cùng bucket vẫn dùng chung cluster và các hạ tầng tương ứng.

## 5. `Bucket`, `Scope`, `Collection`: handle dùng chung

Một đường đi xuống dữ liệu:

~~~java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Scope;
import com.couchbase.client.java.Collection;

Bucket bucket = cluster.bucket("inventory");
Scope scope = bucket.scope("catalog");
Collection products = scope.collection("products");
~~~

Những handle này gắn với cùng client phía dưới. Chúng thích hợp để lưu ở field `final` của một service dùng chung hoặc được lấy lại khi cần. Lấy handle mới không tạo một kết nối cluster mới; song cũng không nên nhầm việc lấy handle với thao tác xác minh có tồn tại bucket/scope/collection.

Ví dụ service dùng một handle collection:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductRawReader {

    private final Collection products;

    public ProductRawReader(CouchbaseClientFactory clientFactory) {
        this.products = clientFactory.getBucket()
                .scope("catalog")
                .collection("products");
    }

    public JsonObject findRaw(String id) {
        return products.get(id).contentAsObject();
    }
}
~~~

Trong code trên:

1. Spring inject `CouchbaseClientFactory` đã được cấu hình; service không tự gọi `Cluster.connect()`.
2. Constructor lấy collection handle một lần, trong khi nhiều request có thể gọi `findRaw` trên cùng handle.
3. Kết quả `JsonObject` là dữ liệu của lời gọi, được trả về cho từng request; không lưu nó vào một field mutable toàn cục.
4. Đây là truy cập **SDK trực tiếp**. Nó không tự áp dụng các quy tắc mapping entity hoặc `@Version` của Spring Data.

Nếu chỉ cần thao tác entity, `CouchbaseRepository` hoặc `CouchbaseTemplate` thường thể hiện nghiệp vụ rõ hơn.

### Lưu handle và thay đổi cấu trúc server

Một handle `Collection` trỏ tới tên keyspace đã chọn. Nếu người vận hành xóa rồi tạo lại collection, đổi quyền, thay topology hoặc xoay secret, handle cũ **không biến thành một ánh xạ sang collection khác**. Những thao tác sau đó có thể thất bại và cần phối hợp cập nhật hạ tầng/cấu hình hoặc tái khởi động theo chính sách ứng dụng.

Đừng xây dựng cache các handle không giới hạn theo một tên collection do người dùng nhập trực tiếp. Tên bucket/scope/collection cần được kiểm soát ở ranh giới dữ liệu và quyền truy cập.

## 6. `CouchbaseClientFactory` và các bean Spring Data sống lâu

`org.springframework.data.couchbase.core.CouchbaseClientFactory` giúp Spring Data truy cập SDK theo bucket/config của ứng dụng. `CouchbaseTemplate` và các repository thường được tạo từ cùng hạ tầng mapping, converter và client factory.

Một luồng phụ thuộc điển hình:

~~~mermaid
flowchart LR
    A["Bean CouchbaseClientFactory"] --> B["Bean CouchbaseTemplate"]
    A --> C["Mapping / Converter"]
    C --> B
    B --> D["Repository proxy"]
    D --> E["ProductService singleton"]
    E --> F["Request A"]
    E --> G["Request B"]
    E --> H["Request C"]
~~~

Không tạo lại factory/template cho từng HTTP request. Dịch vụ nghiệp vụ thường nhận repository bằng **constructor injection**:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Optional<ProductDocument> find(String id) {
        return products.findById(id);
    }
}
~~~

`ProductRepository` là interface kế thừa `CouchbaseRepository<ProductDocument, String>`. Một entity có thể ánh xạ bằng `@Document`, `@Id`, `@Scope("catalog")` và `@Collection("products")`. Bucket mặc định được cung cấp qua cấu hình Spring Data.

**Quan trọng với nhiều bucket:** factory mặc định gắn với ngữ cảnh một bucket. Để sử dụng nhiều bucket, phải thiết kế rõ các factory/template và ràng buộc repository tương ứng. Đổi annotation `@Collection` chỉ thay collection trong bucket đã chọn, không đổi sang một bucket khác.

## 7. Để Spring Boot sở hữu kết nối: trường hợp nên ưu tiên

Trong ứng dụng thông thường, thêm starter Spring Data Couchbase rồi khai báo:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Spring Boot, với điều kiện classpath và auto-configuration phù hợp, thiết lập các bean SDK/Spring Data cần thiết. Luồng vòng đời nên là:

1. Khi `ApplicationContext` khởi động, container tạo và liên kết những bean cần cho việc truy cập Couchbase.
2. Service nhận repository/template/factory từ dependency injection.
3. Nhiều request sử dụng cùng hạ tầng client; mỗi request có tham số, payload và kết quả riêng.
4. Khi ứng dụng dừng, Spring đóng các bean mà nó quản lý theo cơ chế hủy bean tương ứng.

Điều này cũng áp dụng khi bạn sử dụng `AbstractCouchbaseConfiguration` để chủ động cung cấp cấu hình Spring Data: xác định chính xác bean nào do Spring quản lý và không dọn dẹp lại trong service nghiệp vụ.

### Không gọi `disconnect()` trong service

Ví dụ sai khi inject một `Cluster` bean dùng chung:

~~~java
// KHÔNG THỰC HIỆN TRONG PHƯƠNG THỨC NGHIỆP VỤ
public void afterQuery(Cluster sharedCluster) {
    sharedCluster.disconnect();
}
~~~

`disconnect()` ngắt client mà những bean hoặc request khác có thể vẫn sử dụng. Chỉ owner tạo/đăng ký tài nguyên mới phải chịu trách nhiệm dọn dẹp tại ranh giới vòng đời phù hợp.

Không cần viết `@PreDestroy` ở mọi service. Khi auto-configuration đã đăng ký bean cùng cơ chế destroy, việc tự đóng ở một service có thể dẫn tới shutdown sớm hoặc thao tác đóng trùng.

## 8. Khi phải tự tạo bean: chủ sở hữu đóng theo thứ tự phụ thuộc

Có những chương trình dùng SDK riêng hoặc cấu hình Spring đặc biệt cần kiểm soát hoàn toàn `ClusterEnvironment` và `Cluster`. Khi tự tạo, nên có một điểm sở hữu thống nhất.

**Ví dụ ứng dụng SDK độc lập**, không dùng Spring Boot:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.env.ClusterEnvironment;

public final class ClientLifecycleExample {

    public static void main(String[] args) {
        String endpoint = requireEnv("COUCHBASE_CONNECTION_STRING");
        String username = requireEnv("COUCHBASE_USERNAME");
        String password = requireEnv("COUCHBASE_PASSWORD");

        ClusterEnvironment env = ClusterEnvironment.builder().build();
        Cluster cluster = null;

        try {
            cluster = Cluster.connect(
                    endpoint,
                    ClusterOptions.clusterOptions(username, password)
                            .environment(env)
            );

            Bucket bucket = cluster.bucket("inventory");
            bucket.waitUntilReady(Duration.ofSeconds(10));

            boolean found = bucket.scope("catalog")
                    .collection("products")
                    .exists("probe::nonexistent")
                    .exists();

            System.out.println("KV probe completed; found=" + found);
        } finally {
            try {
                if (cluster != null) {
                    cluster.disconnect();
                }
            } finally {
                env.shutdown();
            }
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing: " + key);
        }
        return value;
    }
}
~~~

Ở đây ứng dụng **tự tạo cả environment lẫn cluster**. Khi rời chương trình, nó đóng cluster trước, rồi mới shutdown environment ngay cả khi việc đóng cluster phát sinh lỗi. `Bucket`/`Collection` là handle, không có bước disconnect riêng trong ví dụ này.

`exists("probe::nonexistent")` là phép kiểm tra KV không ghi dữ liệu; `found=false` vẫn là kết quả hợp lệ nếu collection truy cập được nhưng document không tồn tại. Giá trị ID chỉ là minh họa; môi trường yêu cầu phân quyền đúng collection.

### Khai báo bean thủ công trong Spring

Nếu chủ đích sở hữu **toàn bộ** client SDK bằng Spring, có thể đăng ký:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.env.ClusterEnvironment;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DirectSdkConfiguration {

    @Bean(destroyMethod = "shutdown")
    ClusterEnvironment sdkEnvironment() {
        return ClusterEnvironment.builder().build();
    }

    @Bean(destroyMethod = "disconnect")
    Cluster sdkCluster(
            ClusterEnvironment sdkEnvironment,
            @Value("${app.couchbase.connection-string}") String endpoint,
            @Value("${app.couchbase.username}") String user,
            @Value("${app.couchbase.password}") String secret) {

        return Cluster.connect(endpoint,
                ClusterOptions.clusterOptions(user, secret)
                        .environment(sdkEnvironment));
    }
}
~~~

Trong trường hợp này, bean `sdkCluster` **phụ thuộc vào** bean `sdkEnvironment`. Khi context bị đóng bình thường, Spring có thể hủy bean phụ thuộc trước rồi mới hủy bean được dùng chung. `destroyMethod` diễn đạt rõ trách nhiệm đóng từng tài nguyên.

Đoạn code minh họa **một phương án cấu hình SDK thủ công**. Không thêm nó vào ứng dụng đã có auto-configuration Spring Boot quản lý `Cluster`/`ClusterEnvironment` nếu chưa thiết kế lại hạ tầng, bởi các bean mới có thể thay đổi điều kiện auto-configuration, trùng bean hoặc làm client factory sử dụng đối tượng khác dự định.

Nếu một cấu hình thủ công tạo một `ClusterEnvironment` nhưng `Cluster` thực tế lại đến từ bean khác, hãy xác định owner và dependency thực sự trước khi quyết định ai gọi `shutdown()`.

## 9. Tính an toàn khi nhiều luồng dùng chung: hai vấn đề khác nhau

**Vấn đề 1 — client thread safety:** một `Cluster`, `Bucket` hay `Collection` handle được thiết kế để dùng cho các thao tác đồng thời theo hợp đồng SDK. Dùng chung handle giúp giảm chi phí tạo lại tài nguyên. Repository/template thông thường cũng được quản lý như bean dùng chung, miễn không bổ sung state mutable riêng theo request vào những bean đó.

**Vấn đề 2 — xung đột ghi dữ liệu:** hai request có thể đồng thời đọc cùng một document rồi cùng cập nhật. Việc dùng chung client an toàn **không** ngăn trường hợp “last write wins” hoặc lỗi cập nhật đè nhau.

Ví dụ diễn biến:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant CB as Collection
    A->>CB: Đọc product::SKU-1 (giá = 100)
    B->>CB: Đọc product::SKU-1 (giá = 100)
    A->>CB: Ghi giá = 110
    B->>CB: Ghi giá = 105
    Note over A,CB: Không có kiểm soát cạnh tranh ghi: kết quả có thể ghi đè thay đổi trước
~~~

Ở Spring Data Couchbase, `@Version` cho phép optimistic locking dựa trên CAS trong những thao tác được Spring Data hỗ trợ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class StockDocument {
    @Id
    private String id;

    private int available;

    @Version
    private Long version;

    // Constructors và accessors theo mapping của dự án.
}
~~~

Khi version/CAS không còn khớp, một thao tác cập nhật có thể bị từ chối theo cơ chế optimistic locking; tầng nghiệp vụ cần quyết định đọc lại, tính toán lại và thử lại khi phù hợp. **Không** sửa xung đột dữ liệu bằng cách tạo `Cluster` riêng cho từng request.

Tương tự, dữ liệu `JsonObject` có thể thay đổi và các entity mutable không nên được dùng như một biến toàn cục rồi sửa đồng thời. Hãy để chúng thuộc về thao tác/request, hoặc bảo vệ state theo chiến lược lập trình thích hợp.

## 10. Vòng đời trong ứng dụng reactive

Spring Data Couchbase có các API như `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`. Couchbase Java SDK cũng có API reactive. Chúng chia sẻ các khái niệm kết nối phía dưới; chuyển sang Reactor không có nghĩa phải khởi tạo một cluster mới cho mỗi `Mono`.

Ví dụ sử dụng một `Collection` handle đã giữ trong service:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import reactor.core.publisher.Mono;

public class ReactiveRawProductReader {

    private final Collection products;

    public ReactiveRawProductReader(Collection products) {
        this.products = products;
    }

    public Mono<GetResult> find(String id) {
        return products.reactive().get(id);
    }
}
~~~

`Mono` cho phép gọi được tổ chức thành pipeline reactive. Trong WebFlux, tránh `block()` trên luồng xử lý bất đồng bộ. Khi request hủy subscription, không nên hiểu việc đó như một lệnh đóng `Cluster`; client vẫn phục vụ các thao tác khác.

Với shutdown, cần ngừng tiếp nhận công việc mới và xử lý các thao tác đang chạy theo quy trình dừng ứng dụng trước khi container đóng SDK resources. Nếu có những task reactive chạy nền vượt khỏi vòng đời request, chính ứng dụng phải quản lý subscription và chính sách dừng tương ứng.

## 11. Khởi tạo và kiểm tra sẵn sàng: tránh xác nhận quá sớm

Cần phân biệt:

- **Bean tồn tại:** Spring đã tạo một `Cluster`, client factory hoặc repository.
- **Cluster có thể kết nối:** bootstrap, DNS, TLS, xác thực và topology hoạt động.
- **Bucket/collection có thể đọc:** server có keyspace và tài khoản có quyền KV.
- **Truy vấn SQL++ chạy được:** có Query service, quyền Query và chỉ mục phù hợp.
- **Nghiệp vụ đạt yêu cầu:** dữ liệu có độ nhất quán, độ trễ và quy tắc cập nhật phù hợp.

Gọi `cluster.bucket("inventory")` hoặc tạo bean repository chưa tự động chứng minh tất cả các điều kiện trên.

### Một phép thử KV đọc không ghi dữ liệu

Trong một môi trường local có thể dùng một `ApplicationRunner` để xác nhận collection truy cập được:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;

@Configuration(proxyBeanMethods = false)
@Profile("local")
class LocalCouchbaseProbeConfiguration {

    @Bean
    ApplicationRunner verifyKv(CouchbaseClientFactory clientFactory) {
        return args -> {
            boolean present = clientFactory.getBucket()
                    .scope("catalog")
                    .collection("products")
                    .exists("probe::absent")
                    .exists();
            System.out.println("Couchbase KV reachable; found=" + present);
        };
    }
}
~~~

Ví dụ giới hạn bằng `@Profile("local")` để tránh làm cho mọi bản triển khai production phụ thuộc vào một probe đồng bộ ở thời điểm khởi động. Trong production, kiểm tra readiness nên có timeout có kiểm soát, hạn chế tần suất và dựa trên các đường truy cập thật sự cần phục vụ.

**Không dùng `findAll()` làm phép kiểm tra cluster đầu tiên.** Với repository Couchbase, nó có thể liên quan SQL++/index và khiến bạn nhầm lỗi truy vấn với lỗi kết nối. Trước tiên kiểm tra KV theo key, sau đó mới thử query theo thuộc tính.

## 12. Vòng đời khi triển khai, đóng ứng dụng và xoay secret

Một quy trình vận hành đúng phải xem client dùng chung như một tài nguyên thuộc về cả tiến trình:

~~~mermaid
flowchart LR
    A["Application startup"] --> B["Tạo client/factory một lần"]
    B --> C["Readiness có kiểm soát"]
    C --> D["Phục vụ nhiều request"]
    D --> E["Bắt đầu shutdown"]
    E --> F["Ngừng nhận việc mới<br/>xử lý việc đang chạy"]
    F --> G["Spring đóng bean / SDK resources"]
~~~

Trong triển khai rolling update, instance mới có thể khởi động và đạt readiness trước khi instance cũ dừng. Instance cũ nên ngừng nhận request mới rồi cho những request đang xử lý thời gian hoàn tất phù hợp trước khi đóng client. Nếu một tác vụ dài tiếp tục dùng repository sau khi context đã đóng, lỗi kết nối có thể xuất hiện; cần ràng buộc task đó với lifecycle của ứng dụng.

### Xoay vòng credentials hoặc đổi endpoint

Thông tin xác thực và connection string thường được dùng khi tạo client. Thay một biến môi trường ở bên ngoài **không đồng nghĩa** một `Cluster` đang sống tự nhận username/password mới. Cần xác định cơ chế cập nhật kết nối của phiên bản SDK và chiến lược triển khai thực tế; thông thường có thể thay instance ứng dụng bằng cấu hình mới một cách có kiểm soát.

Nếu đổi sang cluster khác, hãy xác minh bucket/scope/collection, quyền RBAC và các index SQL++ trên cluster mới. Đừng giữ một repository gắn với factory của cluster cũ nhưng thay thông tin endpoint ở một vị trí không liên quan.

### Timeout và retry không thay thế quản lý vòng đời

Timeout quá ngắn có thể tạo lỗi giả khi tải tăng; timeout quá dài có thể giữ tác vụ chờ quá lâu. Retry bừa bãi làm tăng tải lên cluster và có thể lặp thao tác ghi không idempotent. Đánh giá theo loại thao tác KV/Query, khả năng idempotency, CAS và số liệu thực tế; một cluster dùng chung vẫn cần chính sách timeout/retry hợp lý.

## 13. Những anti-pattern và triệu chứng thường gặp

| Dấu hiệu | Nguyên nhân cần xem xét | Hướng sửa |
| --- | --- | --- |
| CPU, số connection và thời gian đáp ứng tăng theo số request | Mỗi request tạo `Cluster`/`ClusterEnvironment` | Tạo tài nguyên ở phạm vi ứng dụng, inject lại cho các thao tác |
| Các repository đồng loạt lỗi sau một lời gọi service | Có code gọi `disconnect()`/`shutdown()` trên tài nguyên chung | Đưa đóng tài nguyên về owner của ứng dụng |
| Khởi động xong nhưng thao tác KV đầu tiên timeout | Bean được tạo trước khi data path sẵn sàng | Kiểm tra DNS, TLS, RBAC, bucket, Data service và readiness |
| Đọc từ sai collection hoặc sai bucket | Factory/mapping hoặc profile chọn sai keyspace | Xác minh bucket mặc định và `@Scope`/`@Collection` |
| Nhiều factory/template gây lỗi inject | Không chỉ rõ bean cho từng bucket/cluster | Đặt tên, qualifier và gắn repository đúng factory |
| KV chạy nhưng tìm kiếm theo thuộc tính lỗi | Thiếu Query service, quyền hoặc index | Kiểm tra SQL++ và chỉ mục trên đúng collection |
| Cùng document bị ghi đè khi nhiều request | Không kiểm soát cạnh tranh ghi | Cân nhắc CAS, `@Version`, giao dịch hoặc quy tắc nghiệp vụ |
| Lỗi ở các tác vụ nền khi ứng dụng đang dừng | Task vẫn chạy sau shutdown client | Buộc task dừng trước giai đoạn đóng SDK |
| Deployment mới dùng secret cũ | Instance chưa khởi tạo lại client với cấu hình mới | Thiết kế rotation/deployment có readiness và rollback |
| Mỗi tenant tạo cluster riêng không giới hạn | Thiếu quản lý số lượng client và tài nguyên | Thiết kế vòng đời/giới hạn tài nguyên theo tenant, cluster và quyền |

Để điều tra có hệ thống, hãy đi theo thứ tự **client được tạo ở đâu → ai sở hữu → có bị đóng sớm không → keyspace có đúng không → KV hoạt động không → Query/index hoạt động không**. Cách này giúp tránh thay đổi timeout, chỉ mục hoặc cấu hình TLS khi nguyên nhân thật sự là dọn dẹp client sai thời điểm.

## 14. Bài tập tình huống: từ mã nguồn sang vận hành

Một ứng dụng bán hàng dùng bucket `commerce`, scope `catalog`, collection `products`. Nhóm có ba chức năng: đọc sản phẩm bằng ID, cập nhật tồn kho và tìm sản phẩm bằng SKU. Dịch vụ hiện tạo `Cluster.connect(...)` ở mỗi controller action, cuối action gọi `disconnect()`; hệ thống có nhiều request đồng thời.

**Yêu cầu thiết kế:**

1. Thêm starter Spring Data Couchbase, cấu hình connection string/credentials và bucket theo môi trường.
2. Inject repository/template hoặc một `CouchbaseClientFactory` dùng chung vào service, rồi truy cập `catalog.products`.
3. Bỏ lệnh tạo/đóng client trong controller. Để Spring sở hữu tài nguyên và đóng khi ứng dụng kết thúc.
4. Dùng KV theo ID để xác minh kết nối. Chỉ sau đó kiểm tra truy vấn theo SKU và index phù hợp.
5. Với cập nhật tồn kho đồng thời, bổ sung chiến lược CAS/optimistic locking và xử lý xung đột.
6. Khi triển khai rolling update, bảo đảm instance sắp dừng ngừng nhận việc trước khi hạ tầng Couchbase của nó đóng.

**Câu hỏi tự kiểm tra:**

- Vì sao một `Cluster` có thể phục vụ cả ba chức năng trên mà không cần tạo ba kết nối cluster?
- Khi nào bạn nên dùng một `CouchbaseClientFactory` mới?
- Vì sao `@Version` không liên quan đến việc một `Collection` handle có dùng chung được giữa các luồng hay không?
- Ai shutdown `ClusterEnvironment` nếu nó được tạo bằng SDK thuần? Ai quản lý khi Boot tự tạo?
- Vì sao một kết quả `findById` thành công chưa đảm bảo `findBySku` sẽ hoạt động?

**Đáp án định hướng:** hạ tầng client được xây cho việc tái sử dụng; factory mới cần khi ngữ cảnh bucket/cluster/config được phân tách có chủ đích. CAS bảo vệ tính đúng đắn của cập nhật dữ liệu, trong khi thread safety bảo vệ việc sử dụng handle. Tài nguyên tự tạo phải tự đóng; bean do Spring quản lý theo lifecycle của context. Tìm theo SKU thường cần SQL++ và index phù hợp, khác với KV theo ID.

## 15. Những nguyên tắc cần nhớ

`ClusterEnvironment` và `Cluster` là tài nguyên SDK có vòng đời dài và phải có owner rõ ràng. `Bucket`, `Scope`, `Collection` là những handle có thể dùng chung để truy cập keyspace tương ứng; `CouchbaseClientFactory`, template và repository giúp Spring Data chia sẻ hạ tầng đó cho nhiều service/request.

Thiết kế kết nối tốt phải đi cùng thiết kế dữ liệu: dùng đúng bucket/scope/collection, chỉ mục SQL++ cho truy vấn theo thuộc tính, CAS/`@Version` khi có cập nhật cạnh tranh, lựa chọn TTL/giao dịch theo nghiệp vụ và giữ pipeline reactive không blocking khi áp dụng. Khi phân biệt rõ **vòng đời client**, **an toàn đồng thời** và **tính nhất quán dữ liệu**, ứng dụng Couchbase dễ mở rộng, giám sát và dừng an toàn hơn.

