# Dùng chung Cluster, Bucket và Collection do Spring quản lý

Trong một ứng dụng **Spring Data Couchbase**, tầng Repository và `CouchbaseTemplate` thường đã sử dụng một kết nối tới Couchbase Server do Spring cấu hình. Khi cần gọi **Couchbase Java SDK trực tiếp**—ví dụ `lookupIn`, `mutateIn`, một tùy chọn KV đặc biệt hoặc truy vấn SQL++ với result shape riêng—ta nên **tái sử dụng hạ tầng kết nối đã được quản lý**, thay vì tạo một `Cluster.connect(...)` mới cho từng thao tác.

Điểm mấu chốt không chỉ là tiết kiệm connection. Dùng chung đúng cách giúp ứng dụng có một nguồn cấu hình nhất quán về **cluster endpoint, xác thực, TLS, timeout, môi trường SDK, observability và vòng đời tài nguyên**. Tuy nhiên, dùng cùng `Cluster` **không tự bảo đảm** hai đường Repository và SDK sẽ truy cập cùng bucket/scope/collection, áp dụng cùng entity mapping, TTL, CAS, scan consistency hay cùng một transaction.

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive cho hiệu năng, tính nhất quán, khả năng vận hành.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân biệt vai trò và vòng đời của `Cluster`, `Bucket`, `Scope`, `Collection` trong Couchbase Java SDK.
2. Lấy `Cluster` đã được Spring Boot/Spring Data quản lý thông qua dependency injection (DI), không tự kết nối lại.
3. Lấy đúng `Bucket`, `Scope`, `Collection` SDK và tái sử dụng các handle trong adapter.
4. Hiểu đường đi giữa entity `@Scope`/`@Collection` của Spring Data và SDK `bucket.scope(...).collection(...)`.
5. Đăng ký một SDK `Collection` bean có tên/`@Qualifier` tường minh để tránh nhầm với annotation `@Collection`.
6. Dùng cùng hạ tầng kết nối để viết SDK KV, sub-document và SQL++ mà không đánh mất tenant, schema, TTL, CAS.
7. Sử dụng API reactive từ `Cluster` đã quản lý mà không tạo thêm `Cluster` hoặc chặn event-loop.
8. Nhận diện trường hợp ứng dụng thực sự có nhiều cluster hoặc nhiều bucket và buộc phải định tuyến có chủ đích.
9. Viết integration test kiểm chứng các đường Repository, Template và SDK cùng thao tác trên đúng dữ liệu.
10. Cấu hình lifecycle, health/readiness, quyền, lỗi, timeout và monitoring rõ ràng.

> **Quy tắc thực dụng:** Hãy inject **một `Cluster` do ứng dụng quản lý**; từ đó lấy `Bucket`/`Scope`/`Collection` theo keyspace đã cấu hình; giữ các handle ở tầng adapter. **Không gọi `Cluster.connect(...)` ở mỗi request** và **không gọi `disconnect()` trong business method**.

## 2. Bốn lớp đối tượng của Couchbase SDK

Giả sử dữ liệu nằm tại keyspace:

~~~text
Cluster:   couchbase.example.internal
Bucket:    shop
Scope:     crm
Collection:customers
Document:  customer::42
~~~

Sơ đồ:

~~~text
Spring ApplicationContext
      |
      | quản lý vòng đời
      v
Couchbase Java SDK Cluster
      |
      +---- bucket("shop") ------> Bucket
                 |
                 +---- scope("crm") --------> Scope
                             |
                             +---- collection("customers") -> Collection
                                             |
                                             +---- get("customer::42")
                                             +---- lookupIn(...)
                                             +---- mutateIn(...)
~~~

| Đối tượng | Nó biểu diễn gì? | Nên sử dụng thế nào? |
| --- | --- | --- |
| `Cluster` | Điểm truy cập SDK vào một Couchbase deployment/cluster theo cấu hình | Một đối tượng lâu dài, được Spring quản lý trong trường hợp một deployment |
| `Bucket` | Bucket logic và handle thao tác với bucket | Lấy từ `cluster.bucket(name)`, có thể giữ để tái sử dụng |
| `Scope` | Namespace bên trong bucket | Lấy từ `bucket.scope(name)` |
| `Collection` | Namespace document bên trong scope; thực hiện các KV operations | Lấy từ `scope.collection(name)`, có thể inject hoặc giữ trong adapter |

Những handle này là đối tượng API để **định vị và truy cập tài nguyên**, không phải “một kết nối TCP mới cho từng Collection”. Couchbase SDK tự quản lý kết nối mạng và tài nguyên bên dưới theo cấu hình môi trường SDK.

**Không gọi `close()`/`disconnect()` tùy tiện trên handle mỗi request.** Trong kiến trúc này, Spring chịu trách nhiệm đóng `Cluster` vào lúc ứng dụng shutdown. Chi tiết lifecycle/cleanup phụ thuộc cách bean được tạo và cấu hình SDK tương ứng.

### `Collection` SDK khác annotation `@Collection`

Hai tên rất dễ nhầm:

~~~java
// Annotation Spring Data Couchbase, dùng trên entity:
org.springframework.data.couchbase.core.mapping.Collection

// Handle KV của Couchbase Java SDK:
com.couchbase.client.java.Collection
~~~

Nếu dùng cả hai trong một file Java, hãy import một tên và **viết tên đầy đủ** cho tên còn lại; Java không hỗ trợ alias import. `java.util.Collection` lại là một interface cấu trúc dữ liệu Java, không có liên hệ với Couchbase keyspace.

## 3. Đường đi của Repository, Template và SDK

Một ứng dụng phổ biến có ba nhánh truy cập:

~~~text
                 HTTP / Service / Job
                          |
                  Application service
                          |
        +-----------------+-----------------+
        |                 |                 |
   Repository        CouchbaseTemplate    SDK adapter
        |                 |                 |
        +----- Spring Data mapping ---------+
        |                                   |
        +---------- SDK infrastructure -----+
                                            |
                                   Spring-managed Cluster
                                            |
                                   Bucket/Scope/Collection
                                            |
                                       Couchbase Server
~~~

Repository và `CouchbaseTemplate` sử dụng Spring Data mapping và hạ tầng client theo cấu hình. SDK adapter gọi những operation thấp tầng mà abstraction chưa thể diễn đạt đủ tốt.

**Không hiểu sơ đồ theo nghĩa mọi method có đúng cùng xử lý nội bộ.** Repository có thể dùng KV hoặc SQL++ tùy loại thao tác; Template cũng có nhiều đường truy cập. Cấu hình Spring Data sử dụng client factory, converter, mapping context và các thành phần khác theo phiên bản.

Điểm cần bảo đảm là **không vô tình dựng một deployment client thứ hai** khi ứng dụng vốn đã có một `Cluster` do Spring quản lý.

## 4. Vì sao một `Cluster` dùng lâu dài tốt hơn mở mới?

Một anti-pattern:

~~~java
public String findName(String id) {
    Cluster temporary = Cluster.connect(
            "couchbase://server",
            "user",
            "password");
    try {
        return temporary
                .bucket("shop")
                .scope("crm")
                .collection("customers")
                .get(id)
                .contentAsObject()
                .getString("display_name");
    } finally {
        temporary.disconnect();
    }
}
~~~

Đoạn mã chỉ để minh họa **cách làm không nên sử dụng**. Mỗi request mở một client environment/kết nối mới rồi đóng lại có thể gây:

- Chi phí kết nối/khởi tạo và discovery lặp lại.
- Tăng tài nguyên thread/socket/heap và áp lực lên cluster.
- Khó đồng bộ TLS, credentials, timeout, tracing và retry.
- Khó kiểm soát readiness/health và lỗi khi kết nối.
- Rủi ro đóng tài nguyên khi thao tác bất đồng bộ chưa hoàn tất nếu lifecycle sai.
- Không tận dụng được hạ tầng mà Spring Data Repository/Template đã dùng.

Kể cả khi một SDK method chỉ thực hiện `get(id)`, nó **không phải lý do** để tạo `Cluster` mới. Mục tiêu là tái sử dụng cluster **của ứng dụng**, không phải tạo kết nối ngắn hạn rồi hy vọng SDK tối ưu lại.

## 5. Spring Boot cấu hình một nguồn kết nối

Với các phiên bản Spring Boot sử dụng Couchbase auto-configuration, một cấu hình phổ biến có dạng:

~~~yaml
spring:
  couchbase:
    connection-string: ${COUCHBASE_CONNECTION_STRING}
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: ${COUCHBASE_BUCKET_NAME}

app:
  couchbase:
    crm-scope: crm
    customers-collection: customers
~~~

Ví dụ các biến môi trường:

~~~text
COUCHBASE_CONNECTION_STRING=couchbases://couchbase.example.internal
COUCHBASE_USERNAME=app-customer-service
COUCHBASE_PASSWORD=<secret loaded by deployment>
COUCHBASE_BUCKET_NAME=shop
~~~

`couchbases://` là dạng kết nối TLS thường dùng với cluster cấu hình TLS phù hợp. Trong môi trường phát triển cục bộ, endpoint có thể khác; không hard-code mật khẩu thật vào source control.

Ở đây:

- `spring.couchbase.*` là **cấu hình kết nối**.
- `spring.data.couchbase.bucket-name` chọn bucket Spring Data sử dụng theo cấu hình Boot thông dụng.
- `app.couchbase.crm-scope` và `customers-collection` là **cấu hình nghiệp vụ do ứng dụng định nghĩa** để adapter không lặp string rải rác.

**Lưu ý theo phiên bản:** tên property, cách kết hợp auto-configuration với `AbstractCouchbaseConfiguration`, thứ tự khởi tạo bean và cơ chế customize `ClusterEnvironment` cần kiểm tra theo phiên bản **Spring Boot/Spring Data Couchbase** được khóa trong dự án. Cấu hình ở trên là một cách điển hình, không có nghĩa mọi project đều dùng cùng auto-configuration.

### Khi nào không có auto-configuration?

Một ứng dụng có thể tự cấu hình Spring Data Couchbase bằng `AbstractCouchbaseConfiguration` hoặc configuration tùy chỉnh. Nếu như vậy, hãy **tái sử dụng Cluster bean mà cấu hình đó sở hữu** hoặc expose rõ bean phù hợp. Không vô tình vừa để Boot tạo Cluster, vừa tự gọi `Cluster.connect(...)` lần nữa trong một `@Configuration` khác.

## 6. Cách đơn giản nhất: constructor-inject `Cluster`

SDK adapter có thể nhận `Cluster` sẵn có:

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.stereotype.Component;

@Component
public final class CustomerSdkGateway {

    private final com.couchbase.client.java.Collection customers;

    public CustomerSdkGateway(Cluster cluster) {
        this.customers = cluster
                .bucket("shop")
                .scope("crm")
                .collection("customers");
    }

    public String readDisplayName(String id) {
        return customers.get(id)
                .contentAsObject()
                .getString("display_name");
    }
}
~~~

Những điều có chủ đích trong ví dụ:

1. Constructor nhận `Cluster` từ Spring DI; **không** dùng `Cluster.connect(...)`.
2. Handle `Collection` được lấy **một lần** khi adapter được tạo và giữ trong field `final`.
3. Trong mỗi method chỉ thực thi thao tác KV, không giải quyết lifecycle của toàn cluster.
4. SDK đọc field `"display_name"` theo **tên JSON đã lưu**, không tự dùng converter `@Field`.
5. Dữ liệu đọc theo key cần có kiểm tra tenant/authorization ở đường gọi; ví dụ này chỉ minh họa wiring.
6. Không gọi `cluster.disconnect()` trong adapter, vì Cluster có thể đang được Repository/Template dùng chung.

**Điều kiện tiên quyết:** ApplicationContext phải có bean `Cluster` tương thích. Nếu chưa có, cần sửa **cấu hình ứng dụng một cách tập trung** thay vì tự kết nối trong constructor của mọi adapter.

## 7. Đừng hard-code keyspace trong nhiều lớp

Ví dụ trước viết trực tiếp `"shop"`, `"crm"`, `"customers"` để dễ đọc. Trong dự án thực tế, hãy giữ tên keyspace ở cấu hình.

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class CustomerSdkGateway {

    private final com.couchbase.client.java.Collection customers;

    public CustomerSdkGateway(
            Cluster cluster,
            @Value("${spring.data.couchbase.bucket-name}")
            String bucketName,
            @Value("${app.couchbase.crm-scope}")
            String scopeName,
            @Value("${app.couchbase.customers-collection}")
            String collectionName) {

        this.customers = cluster.bucket(bucketName)
                .scope(scopeName)
                .collection(collectionName);
    }
}
~~~

Các tên lấy từ **trusted application configuration**, không phải query parameter do người dùng gửi. Một property trong ứng dụng cũng có thể khác với tên property Spring Boot nếu project dùng cấu hình thủ công; khi đó dùng một bean config chuyên biệt làm nguồn chung.

### Khi ứng dụng có nhiều collection

Tránh copy/paste literal trong mười adapter:

~~~text
CUSTOMERS: shop.crm.customers
ORDERS:    shop.sales.orders
SESSIONS:  shop.auth.sessions
~~~

Nên tách một component/router có **các keyspace đã đăng ký tường minh** và các method kiểu `customers()`, `orders()`, thay vì `collection(request.getParameter("collection"))`.

## 8. Đăng ký SDK `Collection` thành Spring bean

Nếu nhiều service cùng cần một collection, có thể khai báo bean một lần:

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CouchbaseSdkHandlesConfiguration {

    @Bean("customersSdkCollection")
    public com.couchbase.client.java.Collection customersSdkCollection(
            Cluster cluster,
            @Value("${spring.data.couchbase.bucket-name}")
            String bucketName,
            @Value("${app.couchbase.crm-scope}")
            String scopeName,
            @Value("${app.couchbase.customers-collection}")
            String collectionName) {

        return cluster.bucket(bucketName)
                .scope(scopeName)
                .collection(collectionName);
    }
}
~~~

Inject theo tên để tránh mơ hồ:

~~~java
import com.couchbase.client.java.Collection;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public final class CustomerProfileSdkAdapter {

    private final Collection customers;

    public CustomerProfileSdkAdapter(
            @Qualifier("customersSdkCollection")
            Collection customers) {
        this.customers = customers;
    }

    // Dùng customers.get(...), customers.lookupIn(...), ...
}
~~~

### Có nên đăng ký bean cho mọi handle?

**Không bắt buộc.** Giữ `Collection` trong constructor của **một adapter** cũng hợp lý. Bean riêng hữu ích khi nhiều component cần cùng handle hoặc khi bạn muốn đặt tên rõ ràng và test DI dễ hơn.

Điều cốt lõi là:

- `Cluster` được quản lý thống nhất.
- Keyspace được cấu hình rõ ràng.
- Handle được dùng lại an toàn.
- Không để controller/business code tự chọn tên collection tùy ý.
- Không vô tình gọi `disconnect()` từ các bean dùng chung.

Nếu có nhiều bean kiểu `Collection`, dùng `@Qualifier` hoặc một interface chuyên biệt thay vì phụ thuộc hành vi inject theo type không rõ ràng.

## 9. Entity `@Scope`/`@Collection` phải khớp SDK path

Spring Data Couchbase có thể định nghĩa entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("display_name")
    private String displayName;

    private String tenantId;

    // Constructor và accessor phù hợp.
}
~~~

Tương ứng ở SDK:

~~~java
com.couchbase.client.java.Collection sdkCollection =
        cluster.bucket("shop")
                .scope("crm")
                .collection("customers");
~~~

Các annotation `@Scope("crm")`/`@Collection("customers")` **không làm SDK tự chọn đường dẫn**. SDK nhận string explicit từ lời gọi.

Nếu SDK adapter vô tình dùng:

~~~java
cluster.bucket("shop").defaultCollection();
~~~

nó đang truy cập **default collection**, không phải `shop.crm.customers`. Ngay cả khi hai collection cùng có document key `customer::42`, đó là **hai document khác nhau ở hai keyspace khác nhau**.

### Kiểm tra bằng ba chiều

| Thành phần | Spring Data | Java SDK |
| --- | --- | --- |
| Bucket | Cấu hình `spring.data.couchbase.bucket-name` hoặc cấu hình riêng | `cluster.bucket("shop")` |
| Scope | `@Scope("crm")` hoặc default theo mapping | `bucket.scope("crm")` |
| Collection | `@Collection("customers")` hoặc default theo mapping | `scope.collection("customers")` |

Không chỉ kiểm tra tên bucket. Phải kiểm tra đủ cả **bucket + scope + collection**.

## 10. Khi entity dùng default scope/collection

Couchbase có khái niệm default scope và default collection. Có thể lấy:

~~~java
com.couchbase.client.java.Collection defaults =
        cluster.bucket("shop").defaultCollection();
~~~

Trong khi entity có annotation chỉ rõ `@Scope`/`@Collection` thì đường truy cập phải khớp annotation.

Một số cạm bẫy:

- Entity thiếu `@Scope` nhưng SDK adapter lại chọn `scope("crm")`.
- Entity có `@Collection("customers")` nhưng adapter chỉ dùng `defaultCollection()`.
- Hai môi trường dev/staging có cấu trúc namespace khác nhau, khiến bug chỉ lộ khi deploy.
- Test chỉ xác nhận `findById` thành công trên Repository nhưng không xác nhận SDK đọc đúng cùng document.

Hãy đưa **keyspace contract** vào configuration và integration test, không suy đoán từ tên Java class.

## 11. Cùng Cluster không đồng nghĩa cùng mapping entity

Spring Data có thể áp dụng:

- `@Id`: nhận diện document key.
- `@Field("...")`: đổi tên field Java ↔ JSON.
- `@Version`: ánh xạ optimistic locking tới cơ chế CAS.
- Type discriminator và metadata của converter.
- Custom conversions cho `Instant`, enum hoặc kiểu domain khác.
- Auditing/lifecycle callbacks theo cấu hình.
- Expiry/TTL tùy entity và operation.

SDK `Collection.get(...)` có thể trả raw JSON body:

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

GetResult result = customers.get("customer::42");
JsonObject body = result.contentAsObject();

String displayName = body.getString("display_name");
long cas = result.cas();
~~~

`body.getString("display_name")` đọc field **đã lưu**. Nó không tự biết property Java tên `displayName` hay quy tắc converter.

Sai:

~~~java
// Sai nếu JSON đã lưu dùng "display_name", không phải "displayName".
String name = body.getString("displayName");
~~~

Đáng chú ý hơn: SDK JSON `upsert` không tự gọi toàn bộ conversion/auditing/type-mapping của Spring Data. Nếu một adapter SDK ghi document vào cùng collection với Repository, phải bảo toàn **document contract** mà các reader/writer khác đang sử dụng.

## 12. Không dùng kết quả KV thô như entity đã được converter tạo

Giả sử SDK đọc:

~~~json
{
  "tenantId": "tenant-01",
  "display_name": "Minh",
  "_class": "com.example.Customer"
}
~~~

Dữ liệu trên chỉ minh họa type metadata; tên, giá trị và quy tắc discriminator phụ thuộc converter và cấu hình thực tế. Không hard-code `_class` nếu dự án dùng quy ước khác hoặc không lưu field này.

Nếu bạn tạo:

~~~java
Customer customer = new Customer();
// Tự gán một vài field từ JsonObject.
~~~

rồi gọi `repository.save(customer)`, object thiếu các field cần thiết và thiếu version/CAS đúng. Hậu quả có thể là ghi đè dữ liệu, lost update hoặc document không còn phù hợp mapping.

Các lựa chọn tốt hơn:

1. Nếu thao tác là CRUD entity, dùng Repository/Template để có converter.
2. Nếu chỉ cần read model nhỏ, tạo DTO rõ ràng và không gọi `save` trên DTO.
3. Nếu cần SDK mutation một path, dùng `mutateIn` với path JSON đúng và CAS khi nghiệp vụ yêu cầu.
4. Nếu cần ghi raw document bằng SDK, có **schema contract** và integration test qua cả hai đường.
5. Nếu thật sự cần converter cho một luồng SDK đặc thù, dùng API conversion của Spring Data đã xác minh theo phiên bản; không tái triển khai conversion tùy ý.

**Cùng kết nối không có nghĩa cùng mapping.** Đây là sự phân biệt quan trọng nhất khi mở rộng bằng SDK.

## 13. SDK KV example: cùng document đã lưu bởi Repository

Giả sử Repository vừa lưu Customer với key `customer::42` vào `shop.crm.customers`.

SDK adapter đọc:

~~~java
public record DisplayNameSnapshot(
        String displayName,
        long cas) {}

public DisplayNameSnapshot readById(String documentId) {
    GetResult result = customers.get(documentId);
    return new DisplayNameSnapshot(
            result.contentAsObject().getString("display_name"),
            result.cas());
}
~~~

`GetResult.cas()` là CAS của document tại lần KV đọc. Nó không phải field JSON và không phải timestamp có ý nghĩa sắp xếp toàn collection.

Nếu business method dùng `@Version` ở Spring Data để lưu entity, một SDK mutation làm CAS thay đổi có thể làm lần `save` với version cũ bị từ chối; đó là hành vi mong muốn khi optimistic locking được cấu hình đúng.

### Chú ý: KV authorization vẫn cần thiết

Đoạn đọc chỉ để giải thích API. Biết `documentId` **không đồng nghĩa** user có quyền xem document. Service phải lấy tenant/người dùng từ context xác thực và kiểm tra quyền trước khi trả dữ liệu. Nếu app multi-tenant dùng chung collection, kiểm tra `tenantId` trong body hoặc cơ chế phân quyền tương đương và không tin prefix ID do client gửi.

## 14. Dùng chung Collection cho sub-document operation

Nếu yêu cầu chỉ đổi tên hiển thị, SDK có thể sửa đúng một path:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;
import static com.couchbase.client.java.kv.MutateInOptions.mutateInOptions;

public void changeDisplayName(
        Collection customers,
        String id,
        String newName,
        long expectedCas) {

    customers.mutateIn(
            id,
            List.of(MutateInSpec.replace(
                    "display_name", newName)),
            mutateInOptions().cas(expectedCas));
}
~~~

Ở đây:

- `"display_name"` là field JSON thật do Spring Data mapping tạo.
- `replace` đòi path tồn tại. Nếu nghiệp vụ cho phép field mới, phải chọn `upsert` đúng chủ ý.
- `expectedCas` phải lấy từ **lần đọc thật** của cùng document, không tự tạo ở client.
- CAS mismatch được map thành lỗi conflict/merge theo nghiệp vụ, không phải retry mù để ghi đè.
- `mutateIn` cập nhật một document theo semantics nguyên tử của sub-document mutation, không phải transaction nhiều document.
- Operation SDK không tự chạy auditing callback của Spring Data; nếu doanh nghiệp yêu cầu cập nhật `updatedAt`, cần đưa nó vào mutation hoặc thiết kế luồng cập nhật có chủ đích.

### Cùng Cluster không tạo cùng transaction

Một lệnh SDK `mutateIn` được gọi ngoài transaction context không tự nhập vào một Spring transaction chỉ vì cùng `Cluster`. Nếu cần giao dịch đa document, xem transaction integration của phiên bản Spring Data và SDK transaction API, bảo đảm **mọi thao tác thuộc transaction đều đi qua context thích hợp**. Không trộn operation bên ngoài context vào rồi kỳ vọng atomic rollback chung.

## 15. TTL/expiry: cùng handle vẫn có thể ghi khác chính sách

TTL là chính sách vòng đời của document, không chỉ là field JSON.

Ví dụ:

~~~java
import com.couchbase.client.java.json.JsonObject;
import java.time.Duration;
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;

customers.insert(
        "customer-session::123",
        JsonObject.create().put("kind", "session"),
        insertOptions().expiry(Duration.ofMinutes(15)));
~~~

Đây là thao tác SDK đặt expiry theo request. Nó **không tự sử dụng** annotation expiry của một entity Spring Data khác, dù cùng `Collection` SDK.

Khi dùng Repository/Template và SDK song song phải biết:

- Thời hạn do entity, operation hay bucket/collection `maxTTL` quyết định?
- Với replace/upsert, expiry được đặt lại hay bảo tồn theo semantics cụ thể của SDK và option?
- Có dùng tùy chọn bảo tồn expiry khi cần không?
- Document hết hạn có được phép biến mất giữa hai request đọc/phân trang không?
- Cả hai đường writer có cùng nghĩa “hết hạn sau 15 phút kể từ khi nào” không?

**Không áp đặt quy tắc TTL bằng suy đoán.** Thực hiện integration test với đúng version SDK/Server và đúng phương thức mutation được dùng trong dự án.

## 16. Durability, consistency và request options vẫn có thể khác nhau

Một `Cluster` dùng chung có thể phục vụ các request với tùy chọn khác nhau:

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import com.couchbase.client.java.json.JsonObject;

import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

customers.upsert(
        "audit::event-123",
        JsonObject.create().put("action", "CREATED"),
        upsertOptions().durability(DurabilityLevel.MAJORITY));
~~~

Dù Repository dùng cùng Cluster, một SDK mutation có `MAJORITY` **không làm** các mutation Repository khác tự yêu cầu durability đó.

Tương tự, với SQL++:

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

cluster.query(
        statement,
        queryOptions()
            .parameters(parameters)
            .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
~~~

`REQUEST_PLUS` liên quan mức mới của index cho **query này**, không tự áp dụng cho mọi Repository query hoặc SDK query khác.

| Thành phần | Dùng chung Cluster giúp gì? | Vẫn phải cấu hình hoặc kiểm tra gì? |
| --- | --- | --- |
| Endpoint/TLS/credentials | Có cùng client config do Spring tạo | Phạm vi RBAC và policy bảo mật |
| Network/runtime SDK | Tái sử dụng SDK environment/connections | Timeout/request concurrency |
| KV mutation | Đúng handle/keyspace và SDK instance | CAS, expiry, durability, idempotency |
| SQL++ | Cùng client/query service endpoint | Predicate, index, query options, scan consistency |
| Repository mapping | Repository/Template vẫn giữ converter | SDK thô không tự chạy converter |
| Transactions | Có chung client dùng để tạo operation | Transaction context/semantics riêng |
| Reactive | Có đường SDK reactive từ cùng Cluster | Không block, giới hạn dữ liệu và backpressure |

## 17. SQL++ dùng chung Cluster nhưng vẫn phải chọn keyspace

Ví dụ custom SQL++ trả DTO:

~~~java
public record CustomerCard(String id, String displayName) {}
~~~

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import java.util.List;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public List<CustomerCard> findActiveCustomerCards(
        Cluster cluster,
        String tenantId,
        int limit) {

    if (tenantId == null || tenantId.isBlank()) {
        throw new IllegalArgumentException("Tenant is required");
    }
    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid limit");
    }

    String sql = """
        SELECT META(c).id AS id,
               c.display_name AS displayName
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.tenantId = $tenantId
          AND c.active = TRUE
        ORDER BY c.display_name ASC, META(c).id ASC
        LIMIT $limit
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", limit);

    QueryResult result = cluster.query(
            sql,
            queryOptions().parameters(parameters));

    return result.rowsAsObject().stream()
            .map(row -> new CustomerCard(
                    row.getString("id"),
                    row.getString("displayName")))
            .toList();
}
~~~

Ở đây:

- `Cluster.query(...)` là truy vấn SQL++ qua Query Service, không phải KV get.
- Tên keyspace được viết **đầy đủ**: bucket.scope.collection. Nếu dùng query context hoặc `scope.query(...)` ở đường SDK phù hợp, phải kiểm chứng context thực tế.
- `META(c).id` lấy document key; khác `c.id` nếu body không có field `id`.
- Tên JSON `display_name` là field đã lưu theo Spring Data mapping.
- `$tenantId` và `$limit` là named parameters cho **giá trị**, không dùng cho cú pháp keyspace.
- DTO là read model; đừng gọi `repository.save(...)` với một object thiếu field/CAS.
- Cùng Cluster **không bỏ được yêu cầu index** của SQL++; phải dùng `EXPLAIN`/profiling để xác nhận plan.

### Cạm bẫy: chỉ sử dụng collection handle không giải quyết query context

Một `com.couchbase.client.java.Collection` SDK phục vụ KV operations. Nó không đồng nghĩa mọi câu `Cluster.query("SELECT ...")` tự biết phải query từ collection handle đó. SQL++ phải có `FROM` đầy đủ hoặc query context phù hợp với API được chọn.

## 18. Cùng hạ tầng, hai loại consistency khác nhau

Giả sử Repository lưu một Customer mới. Ngay sau đó:

~~~java
Customer saved = repository.save(customer);

// SDK KV get theo key:
GetResult direct = customersSdkCollection.get(saved.getId());

// SDK SQL++ query theo filter:
QueryResult result = cluster.query(sql, queryOptions());
~~~

Đây là luồng minh họa; class cần accessor/bean được cấu hình tương ứng.

- KV get dùng document key, không tìm kiếm bằng secondary index.
- SQL++ query theo `WHERE` thường sử dụng index; index có thể cập nhật với độ trễ nếu query không yêu cầu chờ.
- SDK có thể dùng `QueryScanConsistency.REQUEST_PLUS` cho query cần phản ánh các mutation đã hoàn tất theo semantics Couchbase.
- Spring Data Repository/Template có thể có cấu hình consistency riêng cho query tương ứng.

**Cùng Cluster không đồng nghĩa cùng một snapshot.** Hai request độc lập có thể thấy dữ liệu khác nhau vì time/mutation/index consistency. `REQUEST_PLUS` không tạo snapshot xuyên nhiều request và CAS không phải mốc phiên bản toàn cluster.

## 19. Reactive: lấy từ `Cluster` đã được Spring inject

Nếu service dùng WebFlux, có thể chuyển sang đường SDK reactive từ chính `Cluster` đã quản lý:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ReactiveCluster;
import org.springframework.stereotype.Component;

@Component
public final class ReactiveCustomerSdkGateway {

    private final ReactiveCluster reactiveCluster;

    public ReactiveCustomerSdkGateway(Cluster cluster) {
        this.reactiveCluster = cluster.reactive();
    }

    public reactor.core.publisher.Mono<String> findDisplayName(
            String id) {

        return reactiveCluster
                .bucket("shop")
                .scope("crm")
                .collection("customers")
                .get(id)
                .map(result ->
                        result.contentAsObject()
                                .getString("display_name"));
    }
}
~~~

`cluster.reactive()` cho một API view reactive của cùng hạ tầng SDK trong phiên bản SDK hỗ trợ. Đây **không phải** yêu cầu tạo thêm một Cluster/kết nối mới.

Có thể tối ưu code bằng cách giữ một `ReactiveCollection` handle trong constructor nếu API SDK được sử dụng cung cấp handle thích hợp. Ví dụ trên ưu tiên minh họa quan hệ với Spring-managed `Cluster`.

### Không làm blocking trong request reactive

Sai:

~~~java
// Không gọi blocking get trong WebFlux event-loop.
return Mono.just(customersSdkCollection.get(id)
        .contentAsObject()
        .getString("display_name"));
~~~

`Mono.just(...)` đánh giá đối số **ngay tại thời điểm tạo publisher**, vì vậy lời gọi `get` ở đây vẫn là blocking. `Mono.fromCallable(...)` cũng không tự biến SDK blocking operation thành non-blocking; nếu cần tạm bridge mã đồng bộ, phải thiết kế scheduler rõ và cân nhắc thay bằng SDK reactive.

Đúng hướng là gọi API reactive của SDK/`ReactiveCouchbaseTemplate`, trả publisher tới WebFlux mà không `block()` trong event-loop.

### Backpressure không thay SQL++ LIMIT

Một `Flux` không tự bảo đảm Couchbase chỉ quét vài document. `Flux.take(20)` hoặc `limitRate(20)` không tương đương một câu SQL++ có `LIMIT 20` ở server. Nếu truy vấn cần giới hạn, đẩy `WHERE/ORDER BY/LIMIT` vào SQL++ và kiểm tra `EXPLAIN`.

## 20. Nhiều Cluster: phải explicit thay vì âm thầm nhân đôi

Có những hệ thống thực sự kết nối nhiều Couchbase deployments: ví dụ cluster vận hành, cluster phân tích hoặc quá trình migration.

Lúc đó **không nên** áp một quy tắc “chỉ một Cluster cho mọi mục đích”. Điều đúng là:

1. Mỗi Cluster có **mục đích, lifecycle và owner** rõ ràng.
2. Bean được đặt tên và inject bằng `@Qualifier`.
3. Repository/Template được cấu hình đúng cluster theo dự định.
4. SDK adapter dùng đúng bean tương ứng.
5. Không tạo Cluster mới động trong request để thay định tuyến.
6. Không trộn dữ liệu/transaction của hai clusters khi hợp đồng không hỗ trợ.
7. Quan sát độc lập timeout, quyền và shutdown của từng connection manager.

Ví dụ mang tính cấu trúc:

~~~java
@Component
public final class CustomerSdkGateway {

    private final Cluster customerCluster;

    public CustomerSdkGateway(
            @Qualifier("customerCluster")
            Cluster customerCluster) {
        this.customerCluster = customerCluster;
    }
}
~~~

Ví dụ trên **giả định** ứng dụng đã đăng ký bean tên `customerCluster`. Đừng sao chép và mong Boot tự tạo một bean có tên như vậy. Cấu hình đa Cluster cần được thiết kế đồng bộ cho cả Spring Data và SDK, không chỉ cho constructor này.

## 21. Nhiều Bucket trong cùng Cluster không cần nhiều Cluster

Một Couchbase deployment có thể chứa `shop` và `analytics`:

~~~java
var customers = cluster.bucket("shop")
        .scope("crm")
        .collection("customers");

var aggregates = cluster.bucket("analytics")
        .scope("reports")
        .collection("daily_totals");
~~~

Đây là hai collection handles trên cùng Cluster; không cần gọi `Cluster.connect(...)` hai lần. Tuy nhiên:

- Credentials của Cluster phải có RBAC phù hợp với cả hai keyspaces.
- Cần xác định liệu một service **nên** có quyền tới cả hai bucket hay không; tối thiểu hóa quyền vẫn ưu tiên.
- Spring Data Repository của một entity có thể đang mặc định ở một bucket; không suy rằng thay `@Scope`/`@Collection` cho phép chuyển bucket tùy ý.
- SDK adapter phải dùng đúng collection handle và contract dữ liệu.
- Cross-bucket SQL++ và transaction có giới hạn/semantics riêng tùy phiên bản, không tự suy ra từ việc dùng cùng Cluster.

Chia bucket/scope/collection theo domain là quyết định dữ liệu/permission, không phải lý do để phát sinh một network client cho mỗi collection.

## 22. Multi-tenancy: tránh keyspace injection

Có hai mô hình phổ biến:

1. Nhiều tenant cùng collection và phân biệt bằng `tenantId` trong document/query.
2. Tách tenant theo collection/scope/bucket theo cấu trúc hệ thống đã kiểm soát.

Trong cả hai, không nên nhận trực tiếp:

~~~http
GET /customers?bucket=anyBucket&scope=anyScope&collection=anyCollection
~~~

rồi gọi:

~~~java
cluster.bucket(requestBucket)
       .scope(requestScope)
       .collection(requestCollection);
~~~

Nếu client điều khiển tên keyspace mà không có kiểm tra quyền và allowlist, có thể vượt ranh giới tài nguyên dự kiến hoặc làm hệ thống truy cập sai dataset.

Thiết kế tốt hơn:

- Lấy tenant từ principal/authorization context đáng tin cậy.
- Ánh xạ tenant → keyspace đã cấu hình/allowlist.
- Kiểm tra RBAC và quyền ở tầng application, không chỉ dựa vào tên document key.
- Định nghĩa riêng collection dành cho từng tenant nếu kiến trúc yêu cầu.
- Không nối tên keyspace/field SQL++ tùy ý từ input vào statement.
- Áp dụng cùng tenant/filter ở query data, count, aggregation, cursor và các thao tác KV.

**Dùng chung Cluster không cấp quyền nghiệp vụ.** SDK chỉ biết credentials của service; nếu service có quyền đọc nhiều tenant, chính ứng dụng vẫn phải kiểm tra phân quyền mỗi request.

## 23. Vòng đời: ai được đóng `Cluster`?

Nếu Cluster được Spring Boot auto-configure, application context sở hữu nó. Khi ứng dụng shutdown, Spring và auto-configuration thực hiện cleanup theo bean lifecycle của phiên bản tương ứng.

**Không** thực hiện:

~~~java
public CustomerCard readThenClose(String id) {
    try {
        return readCustomer(id);
    } finally {
        cluster.disconnect(); // SAI: đóng Cluster dùng chung.
    }
}
~~~

Hậu quả có thể là Repository, Template và các SDK adapters khác không còn sử dụng được hạ tầng đã đóng.

### Nếu cấu hình Cluster thủ công

Chỉ khi **chủ đích không dùng** auto-configured Cluster và đang tự sở hữu lifecycle, có thể định nghĩa một bean duy nhất với phương thức hủy:

~~~java
import com.couchbase.client.java.Cluster;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ManualCouchbaseSdkConfiguration {

    @Bean(destroyMethod = "disconnect")
    Cluster cluster(CouchbaseConnectionSettings settings) {
        return Cluster.connect(
                settings.connectionString(),
                settings.username(),
                settings.password());
    }
}
~~~

`CouchbaseConnectionSettings` là **kiểu cấu hình ứng dụng minh họa**, phải được định nghĩa/bind secrets phù hợp nếu dùng mẫu này. Đoạn mã **không nên thêm** vào dự án đã được Spring Boot/Spring Data tạo `Cluster`, vì có thể gây bean ambiguity hoặc hai connections độc lập.

Với auto-configuration, ưu tiên inject bean hiện có; trường hợp manual bean cần được tích hợp với Spring Data client factory và mapping cấu hình, không chỉ tạo cluster xong là Repository tự dùng đúng bean.

## 24. Khởi tạo, readiness và health check

Couchbase Java SDK có những bước discovery/connection có thể diễn ra bất đồng bộ theo môi trường. Việc `cluster.bucket("shop")` trả một handle **không chứng minh** cluster và mọi service/index đã sẵn sàng.

Các lựa chọn vận hành:

- Kiểm tra readiness ở startup khi yêu cầu, ví dụ SDK có các API `waitUntilReady(...)` ở đối tượng phù hợp.
- Dùng health indicator/Actuator khi ứng dụng đã cấu hình.
- Phân biệt readiness với liveness: mất kết nối tạm thời không nhất thiết phải giết process liên tục.
- Nếu SQL++ là một phụ thuộc quan trọng, kiểm tra cả Query Service/index và quyền thay vì chỉ ping KV.
- Không chạy health query nặng trên mọi HTTP request.
- Không giả định một collection handle tạo thành công đồng nghĩa collection tồn tại và user có quyền.

Ví dụ ý tưởng startup check:

~~~java
// Minh họa tùy chọn readiness; gọi tại startup khi thực sự cần,
// không gọi cho từng document GET.
cluster.bucket("shop")
       .waitUntilReady(Duration.ofSeconds(10));
~~~

`Duration` ở đây là `java.time.Duration`. Việc chọn timeout, service readiness, retry và hành vi khi cluster khởi động chậm thuộc chính sách triển khai; phải xác minh API/semantics trên phiên bản Java SDK thực tế.

## 25. Một ứng dụng, nhiều writers: nhất quán schema và trách nhiệm

Một hệ thống có thể ghi cùng một document qua:

- Spring Data Repository `save(...)`.
- `CouchbaseTemplate.upsertById(...)`.
- SDK `collection.upsert(...)`.
- SDK `collection.mutateIn(...)`.
- Một job hoặc service khác bên ngoài ứng dụng.

Dù cùng cluster và cùng collection, chúng có thể khác nhau về:

| Khía cạnh | Vấn đề khi dùng nhiều đường |
| --- | --- |
| JSON field naming | `display_name` từ `@Field` nhưng SDK raw ghi `displayName` |
| Type metadata | SDK raw không tự thêm discriminator Spring Data |
| CAS | Repository có `@Version` nhưng SDK replace bỏ điều kiện |
| TTL | Đường ghi mới reset/giữ expiry khác nhau |
| Auditing | Spring callbacks chỉ chạy ở một số đường |
| Durability | Một đường có `MAJORITY`, đường khác dùng default |
| Consistency | Query của mỗi đường dùng scan consistency khác |
| Authorization | SDK KV theo ID chưa kiểm tra tenant |
| Error mapping | CAS conflict, timeout, path not found bị xử lý không đồng nhất |

Giải pháp là xác định **document contract** và **write invariants** rõ ràng. Khi có thể, để các mutation entity phổ biến đi qua Repository/Template; dùng SDK cho thao tác thật sự cần nhưng phải viết integration test chéo.

## 26. Integration test 1: Repository ghi, SDK đọc

Bài test đúng trọng tâm phải xác minh **cùng keyspace và mapping**:

~~~java
@SpringBootTest
class SharedCouchbaseWiringIT {

    @Autowired
    CustomerRepository repository;

    @Autowired
    @Qualifier("customersSdkCollection")
    com.couchbase.client.java.Collection sdkCollection;

    @Test
    void repositoryWriteIsVisibleThroughSdk() {
        Customer customer = new Customer(/* dữ liệu test hợp lệ */);
        customer.setId("test::customer::42");
        customer.setDisplayName("Minh");
        customer.setTenantId("tenant-test");

        repository.save(customer);

        GetResult result = sdkCollection.get("test::customer::42");

        assertThat(result.contentAsObject()
                .getString("display_name"))
                .isEqualTo("Minh");
    }
}
~~~

Đây là **khung test minh họa**: constructor/accessors, imports, phương thức cleanup và cách khởi tạo test data phải phù hợp với entity thực của dự án. Không nên copy toàn khối rồi xem là test compile sẵn.

Test phải chạy với Couchbase/test container/cụm thử nghiệm phù hợp, không chỉ mock Repository và SDK; nếu mock thì rất khó phát hiện hai đường đang trỏ vào **hai collection khác nhau**.

### Cleanup test

Khi sử dụng key test thật, cần xóa dữ liệu sau test và tránh đụng tên key của môi trường dùng chung. Không chạy integration test ghi/xóa lên production bucket. Dữ liệu multi-tenant test phải có isolation để không làm sai các bài test khác.

## 27. Integration test 2: SDK mutate, Repository đọc lại

Luồng kiểm thử:

~~~text
Given Repository lưu Customer:
      id=test::customer::42
      displayName=Minh
      tenantId=tenant-test

When SDK mutateIn:
      path="display_name"
      value="Minh mới"
      with matching CAS

Then Repository.findById:
      displayName="Minh mới"
      và entity mapping không bị hỏng
~~~

Cần kiểm tra:

1. SDK dùng đúng `shop.crm.customers`.
2. JSON path là `display_name` chứ không phải `displayName`.
3. CAS được lấy từ lần đọc hợp lệ, mutation có kiểm tra phiên bản nếu hợp đồng yêu cầu.
4. Entity sau mutation vẫn đọc được bằng Spring converter.
5. Những field không được sửa vẫn giữ nguyên.
6. Auditing fields/TTL bảo toàn theo chính sách.
7. Nếu mutation làm document chứa dữ liệu thiếu type discriminator hoặc giá trị sai kiểu, test phải phát hiện.
8. Repository ghi tiếp với version cũ thì xử lý conflict đúng thay vì âm thầm đè.

Mục tiêu là chứng minh **cùng document contract**, không chỉ “SDK trả status thành công”.

## 28. Integration test 3: hai Cluster không mong muốn

Một rủi ro ít lộ trong unit test là ứng dụng tạo hai `Cluster` beans hoặc hai kết nối thủ công với cấu hình khác nhau.

Các hướng kiểm tra:

- Kiểm tra số bean `Cluster` trong ApplicationContext khi kiến trúc thiết kế chỉ có một.
- Dùng `@Qualifier` cho adapter nếu ứng dụng nhiều cluster có chủ đích.
- So effective connection string/bucket/scope/collection của môi trường, không log credentials.
- Xác nhận test Repository ghi document và SDK adapter đọc **chính document đó**.
- Sau khi adapter chạy, các Repository/Template methods khác vẫn hoạt động; adapter không được đóng Cluster dùng chung.
- Mô phỏng application shutdown để kiểm tra tài nguyên được giải phóng đúng owner.
- Xác minh không có lời gọi `Cluster.connect(...)` trong request-scoped/business code bằng code review/static check.

Nếu dự án thật sự dùng multi-cluster, test phải kiểm tra **đúng định tuyến**, không áp đặt “mọi lúc phải có một bean duy nhất”.

## 29. Lỗi thường gặp

| Triệu chứng hoặc anti-pattern | Vì sao có vấn đề | Cách sửa |
| --- | --- | --- |
| Gọi `Cluster.connect(...)` trong mỗi request | Tạo client mới, mất tái sử dụng, khó quản lý tài nguyên | Inject Spring-managed `Cluster` |
| Gọi `cluster.disconnect()` sau `get` | Đóng tài nguyên Repository/Template cũng đang dùng | Chỉ owner/lifecycle Spring đóng |
| Mở Cluster thứ hai trong `@Bean` cạnh auto-config | Bean ambiguity/hai hạ tầng cấu hình khác | Dùng Cluster hiện có hoặc chủ đích custom hóa một nơi |
| SDK dùng `defaultCollection()` còn entity ở `crm.customers` | Đọc khác keyspace | Kiểm tra bucket/scope/collection |
| Cùng Cluster nhưng SQL++ query không đúng `FROM` | Query sai keyspace/context | Chọn fully qualified keyspace/query context |
| SDK gọi field `displayName` thay vì `display_name` | Converter mapping khác nhau | Theo JSON field thực và integration test |
| Raw SDK upsert thiếu discriminator | Repository có thể không nhận/mapping đúng | Giữ document contract hoặc dùng converter |
| SDK replace bỏ CAS | Lost update | CAS conditional mutation theo nghiệp vụ |
| SDK mutation reset/bỏ TTL | Document hết hạn sai | Quy định expiry/expiry preservation |
| `@Qualifier` bị bỏ khi có hai Collection bean | Inject mơ hồ | Bean name hoặc typed gateway |
| User input thành collection name | Quyền/keyspace injection | Allowlist, trusted tenant routing |
| SDK get theo ID không kiểm tra tenant | Lộ dữ liệu dù biết key | Authorization ở application |
| Reactive code bọc blocking `get` trong `Mono.just` | Vẫn block ngay khi tạo publisher | SDK reactive API |
| Repository thấy dữ liệu vừa ghi nhưng SQL++ không thấy | Index chưa bắt kịp tùy consistency | Xem `REQUEST_PLUS`/mutation consistency |
| Gọi `waitUntilReady` trên mỗi request | Tăng latency không cần | Health/readiness ở lifecycle thích hợp |
| Nghĩ một Cluster đồng nghĩa một transaction | Không có transaction context chung tự động | Thiết kế transaction rõ ràng |
| Dùng SDK raw DTO rồi `save` như entity | Thiếu ID/version/field | Tách read model và entity mutation |

## 30. Checklist review trước khi merge

### Cấu hình và ownership

- [ ] Spring Boot/Spring Data hoặc custom configuration sở hữu `Cluster` rõ ràng.
- [ ] Không tạo `Cluster.connect(...)` trong adapter/method request.
- [ ] Không gọi `disconnect()` bên ngoài owner shutdown.
- [ ] Không tạo hai Cluster beans ngoài ý muốn.
- [ ] Tên bucket/scope/collection đến từ trusted configuration.
- [ ] Có `@Qualifier` khi nhiều collection/cluster beans cùng type.
- [ ] Có readiness/health và timeout phù hợp với deployment.

### Dữ liệu và semantics

- [ ] SDK path trùng entity `@Scope`/`@Collection` và cấu hình bucket.
- [ ] JSON field names khớp `@Field` và custom converters.
- [ ] Type discriminator được bảo toàn khi SDK raw ghi.
- [ ] `@Id` và `@Version` không bị hiểu thành JSON field tùy ý.
- [ ] CAS conflict được xử lý đúng, không ghi đè vô điều kiện.
- [ ] TTL/expiry và durability phù hợp chính sách.
- [ ] Query SQL++ tự thêm tenant/discriminator/filter cần thiết.
- [ ] Query SQL++ có index và scan consistency đã được kiểm chứng.
- [ ] Không làm lộ dữ liệu ngoài tenant hoặc collection dự kiến.

### Ứng dụng và vận hành

- [ ] SDK adapter expose domain methods, không phát tán SDK handles ra controller.
- [ ] DTO đọc riêng, không lưu partial entity bằng Repository.
- [ ] Blocking/reactive paths không trộn bừa; WebFlux không gọi `block()`.
- [ ] Có error mapping, timeout, retry và idempotency phù hợp operation.
- [ ] Có metrics/tracing mà không log credentials hoặc PII.
- [ ] Có integration tests hai chiều Repository ↔ SDK.
- [ ] Test trên môi trường cô lập và Couchbase/Spring Data versions đang sử dụng.
- [ ] Có tài liệu decision/owner nếu mở rộng sang nhiều bucket/cluster.

## 31. Bài tập thực hành

Xây dựng một service quản lý Customer với dữ liệu ở `shop.crm.customers`.

**Phần A — Wiring**

1. Cấu hình `spring.couchbase.*` và `spring.data.couchbase.bucket-name` bằng biến môi trường.
2. Entity `Customer` dùng `@Scope("crm")`, `@Collection("customers")`, `@Field("display_name")`.
3. Repository CRUD thông thường qua Spring Data.
4. Tạo bean `customersSdkCollection` từ `Cluster` đã được Spring inject.
5. Tạo `CustomerProfileSdkAdapter` inject bean đó bằng `@Qualifier`.
6. Kiểm tra không có `Cluster.connect(...)` bên trong adapter hoặc request method.

**Phần B — SDK mở rộng**

1. Viết `readDisplayName` từ KV get hoặc `lookupIn`.
2. Viết `changeDisplayName` với `mutateIn` và optional expected CAS theo nghiệp vụ.
3. Bổ sung validation, tenant authorization và xử lý not found/CAS mismatch.
4. Đọc lại document bằng Repository; chứng minh converter hiểu field mới.
5. Thử document có TTL, xác nhận mutation không phá chính sách expiry.

**Phần C — Reactive và SQL++**

1. Tạo một method dùng `cluster.reactive()` đọc theo key bằng API reactive.
2. Tạo một SQL++ projection từ keyspace `shop.crm.customers`, viết tên keyspace đầy đủ trong SQL++, dùng named parameters và `META(c).id`. So sánh với KV get theo key.
3. So sánh query KV theo key và SQL++ tìm theo filter; ghi nhận index và consistency khác nhau.
4. Không dùng `Mono.just(blockingGet())` hoặc `Flux.take(20)` để thay `LIMIT 20` ở SQL++.
5. Bật `EXPLAIN` cho query thực tế và ghi nhận query plan.

**Phần D — Test lỗi cấu hình**

1. Đổi sai scope sang `_default` trong SDK adapter; xác minh test chéo phát hiện document không có ở đúng keyspace.
2. Đổi sai field JSON từ `display_name` thành `displayName`; xác minh test mapping thất bại.
3. Gọi Repository save rồi SDK mutate; kiểm tra CAS conflict khi writer khác sửa.
4. Tạo hai Collection beans cùng type mà không `@Qualifier`; xác minh wiring trở nên mơ hồ và sửa lại.
5. Đảm bảo controller tenant A không thể dùng document key tenant B để đọc dữ liệu.

### Câu hỏi tự kiểm tra

1. `Cluster` SDK được Spring quản lý đem lại những lợi ích lifecycle và cấu hình nào?
2. `Bucket`/`Scope`/`Collection` handles có đồng nghĩa mỗi handle mở một network connection mới không?
3. Vì sao không nên gọi `Cluster.connect(...)` trong mỗi repository method?
4. Một entity `@Scope("crm") @Collection("customers")` có tự khiến SDK `defaultCollection()` trỏ đúng document không?
5. `@Collection` của Spring Data khác `com.couchbase.client.java.Collection` như thế nào?
6. Cùng `Cluster` có tự dùng converter `@Field("display_name")` khi SDK raw get/upsert không?
7. `META(c).id` khác body field `c.id` ở điểm nào?
8. Tại sao KV get theo key và SQL++ `WHERE` có thể thấy dữ liệu mới ở thời điểm khác nhau?
9. `REQUEST_PLUS` có tạo snapshot cho nhiều request không?
10. Vì sao không được gọi `disconnect()` trong adapter dùng chung?
11. Khi nào cần `@Qualifier` cho `Collection` hoặc `Cluster`?
12. Nếu app dùng hai clusters có chủ đích, chính sách lifecycle phải thay đổi thế nào?
13. CAS và TTL được bảo toàn tự động giữa Repository và raw SDK không? Cần làm gì?
14. Vì sao `Mono.just(customers.get(id))` chưa phải non-blocking?
15. Test tích hợp nào chứng minh chắc nhất Repository và SDK dùng đúng **cùng keyspace và document contract**?

## 32. Tài liệu chính thức và chú ý theo phiên bản

- [Spring Data Couchbase — Configuring Couchbase](https://docs.spring.io/spring-data/couchbase/reference/couchbase/configuration.html): cấu hình hạ tầng Couchbase và quan hệ Spring Data/SDK.
- [Spring Data Couchbase — CouchbaseTemplate](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): Template, operations, khả năng truy cập cấu hình bên dưới.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository mapping và query methods.
- [Spring Data Couchbase — Object Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Field`, metadata và converter.
- [Couchbase Java SDK — Managing Connections](https://docs.couchbase.com/java-sdk/current/howtos/managing-connections.html): Cluster, Bucket, Scope và Collection handles; lifecycle.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `get`, `upsert`, CAS, expiry, durability.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `lookupIn`, `mutateIn` và CAS.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): SQL++, named parameters, scan consistency và result shape.
- [Couchbase Java SDK — Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): reactive SDK và threading.
- [Spring Boot — Couchbase](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.couchbase): auto-configuration và connection properties của Spring Boot.

**Kiểm chứng phiên bản:** tên cấu hình Boot, bean exposure, `AbstractCouchbaseConfiguration`, handle APIs, mapping metadata, dependency versions và SDK lifecycle có thể khác theo Spring Boot, Spring Data Couchbase, Couchbase Java SDK và Server. Khi triển khai, xem cấu hình thực tế được khóa và chạy integration test để xác nhận Spring Data/SDK **cùng Cluster, cùng bucket/scope/collection và đúng semantics nghiệp vụ**.

> **Ghi nhớ:** **Dùng chung `Cluster` do Spring quản lý** là nguyên tắc tổ chức hạ tầng; các handle `Bucket`/`Scope`/`Collection` là cách chọn keyspace để KV hoặc SQL++ thao tác. Dùng chung hạ tầng không làm SDK raw tự có converter, CAS, TTL, quyền tenant hay transaction của Repository. Hãy inject và tái sử dụng đúng handle, để Spring sở hữu lifecycle, và kiểm chứng giao tiếp chéo Repository ↔ SDK bằng integration test.
