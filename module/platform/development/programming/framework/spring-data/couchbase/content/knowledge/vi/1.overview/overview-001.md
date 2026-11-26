# Spring Data Couchbase là gì và giải quyết bài toán truy cập dữ liệu nào?

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích Couchbase lưu dữ liệu theo document JSON như thế nào và Spring Data Couchbase đứng ở đâu trong kiến trúc ứng dụng Spring.
- Phân biệt truy cập theo document ID (Key–Value/KV), truy vấn SQL++ qua chỉ mục và vai trò của Repository, CouchbaseTemplate, Reactive API.
- Thiết kế bước đầu bucket, scope, collection, ID, cấu trúc document và chỉ mục cho một nghiệp vụ cụ thể.
- Nhận diện các quyết định ảnh hưởng đến tính nhất quán, xử lý cập nhật đồng thời, TTL, giao dịch và hiệu năng.
- Xác định khi nào Spring Data Couchbase phù hợp, khi nào cần xem xét giải pháp khác hoặc dùng trực tiếp Couchbase Java SDK.

## 2. Bài toán: ứng dụng cần đọc, ghi document linh hoạt ở quy mô lớn

Giả sử một nền tảng thương mại điện tử cần phục vụ đồng thời các thao tác:

1. Mở hồ sơ khách hàng bằng mã khách hàng.
2. Tìm khách hàng theo email hoặc trạng thái thành viên.
3. Lưu giỏ hàng với danh sách sản phẩm thay đổi thường xuyên.
4. Tự hết hạn một phiên làm việc sau khoảng thời gian nhất định.
5. Tránh trường hợp hai yêu cầu cập nhật cùng một giỏ hàng ghi đè dữ liệu của nhau.

Với cơ sở dữ liệu quan hệ, ta thường bắt đầu từ bảng, khóa ngoại và phép JOIN. Với Couchbase, một cách tiếp cận là lưu **mỗi đối tượng nghiệp vụ phù hợp thành một document JSON**, có ID riêng và các trường có thể lồng nhau:

~~~json
{
  "id": "customer::c123",
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "preferences": {
    "language": "vi",
    "notifications": true
  },
  "addresses": [
    { "type": "home", "city": "Da Nang" }
  ]
}
~~~

Ở ví dụ trên, trường `id` chỉ để minh họa cho người đọc; **khóa document thực sự** trong Couchbase là metadata ID, không bắt buộc phải được lưu lặp trong phần JSON. Khi ánh xạ bằng Spring Data, trường Java gắn `@Id` tương ứng với khóa document đó.

Khi ứng dụng cần lấy đúng document `customer::c123`, Couchbase có thể đọc theo khóa qua **Data Service/KV**. Khi cần tìm khách hàng theo email, truy vấn thường sử dụng **SQL++** (trước đây thường gọi là N1QL) và **chỉ mục**. Hai đường truy cập này khác nhau về độ trễ, tài nguyên và yêu cầu vận hành.

**Spring Data Couchbase** là mô-đun của hệ sinh thái Spring Data giúp ứng dụng Java/Spring làm việc với Couchbase theo các mô hình quen thuộc: ánh xạ object–document, repository, template và tích hợp reactive. Nó nằm **trên Couchbase Java SDK**; bản thân Spring Data không thay thế Couchbase Server, không tự thiết kế chỉ mục và không tự giải quyết mọi vấn đề nhất quán.

## 3. Spring Data Couchbase nằm ở đâu trong kiến trúc?

~~~mermaid
flowchart TD
    A["Controller / Application Service"] --> B["CouchbaseRepository"]
    A --> C["CouchbaseTemplate"]
    A --> D["Reactive Repository / ReactiveCouchbaseTemplate"]
    B --> E["Spring Data: Mapping, conversion, query"]
    C --> E
    D --> E
    E --> F["Couchbase Java SDK"]
    F --> G[("Couchbase Cluster")]
    G --> H["Data Service: KV theo ID"]
    G --> I["Query Service: SQL++"]
    I --> J["Index Service: chỉ mục"]
~~~

Có ba nhóm trách nhiệm cần phân biệt:

| Tầng | Trách nhiệm chính | Điều không nên mặc định |
| --- | --- | --- |
| Ứng dụng và Spring Data Couchbase | Mô hình Java, mapping, CRUD, truy vấn, tích hợp vòng đời bean và API đồng bộ/reactive | Repository không tự tạo thiết kế document tối ưu |
| Couchbase Java SDK | Quản lý kết nối tới cluster, giao tiếp KV và query, timeout, retry và các khả năng cấp thấp | SDK không thay thế kiểm soát nghiệp vụ của ứng dụng |
| Couchbase Server | Lưu trữ document, phân phối dữ liệu, quản lý index, thực thi SQL++, cấu hình durability và dịch vụ cluster | Có database không đồng nghĩa mọi truy vấn đều nhanh hoặc luôn đọc được kết quả ghi gần nhất qua index |

Một luồng truy cập thường bắt đầu từ service, gọi repository hoặc template, được Spring Data chuyển thành thao tác SDK, rồi đến dịch vụ tương ứng của Couchbase. Sơ đồ chỉ mang tính khái quát; tùy cấu hình cluster, các dịch vụ có thể nằm trên cùng hoặc khác node.

## 4. Các khái niệm dữ liệu cần hiểu trước khi viết repository

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Bucket** | Không gian chứa dữ liệu ở cấp cao, có cấu hình tài nguyên/chính sách liên quan | `shop` |
| **Scope** | Nhóm logic các collection trong bucket | `crm`, `sales` |
| **Collection** | Tập document cùng mục đích nghiệp vụ trong một scope | `customers`, `orders` |
| **Document** | Giá trị JSON được lưu dưới một khóa duy nhất trong collection | Hồ sơ của khách hàng C123 |
| **Document ID** | Khóa dùng để đọc/ghi trực tiếp một document | `customer::c123` |
| **Secondary index** | Cấu trúc hỗ trợ lọc/sắp xếp theo các trường của document | Index trên `email` |
| **CAS** | Giá trị phiên bản do server quản lý cho một document, dùng để phát hiện cập nhật xung đột | Chỉ ghi nếu document chưa bị thay đổi |
| **TTL/expiry** | Thời điểm document tự hết hạn | Session hết hạn sau 30 phút |

Trong những bucket có cấu hình mặc định, scope và collection `_default` có thể được dùng để bắt đầu nhanh. Khi ứng dụng có nhiều miền nghiệp vụ, nên xác định rõ cách tách collection theo quyền truy cập, loại dữ liệu, mẫu truy vấn và vận hành; không nên chọn chỉ vì tên entity Java.

**Document ID là quyết định thiết kế quan trọng.** Với ID `customer::c123`, việc đọc đúng một khách hàng có thể đi thẳng theo KV. Với yêu cầu “tìm tất cả khách hàng thuộc hạng Gold”, ID không đủ; ứng dụng cần truy vấn và index phù hợp. Tiền tố `customer::` là quy ước của ứng dụng để nhận diện loại khóa, không phải cú pháp Couchbase bắt buộc.

### Embed hay tham chiếu?

- **Embed** dữ liệu thường được đọc cùng nhau, có kích thước giới hạn, ví dụ vài tùy chọn hiển thị trong hồ sơ. Điều này có thể giảm số lần truy cập.
- **Tham chiếu bằng ID** khi dữ liệu tăng không giới hạn, có vòng đời độc lập hoặc được nhiều đối tượng cùng cập nhật, ví dụ danh sách toàn bộ đơn hàng của khách hàng.
- Tránh document phình to hoặc trở thành **điểm nóng cập nhật** khi nhiều yêu cầu đồng thời cùng sửa một document. Document JSON linh hoạt về cấu trúc nhưng vẫn cần quản lý phiên bản schema và migration khi ứng dụng thay đổi.

## 5. Repository giải quyết phần lặp lại của tầng truy cập dữ liệu

Trong một dự án Spring Boot tương thích, dependency thường được khai báo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Ví dụ cấu hình kết nối (minh họa cho Spring Boot 3.x; cần đối chiếu với phiên bản Spring Boot/Spring Data thực tế của dự án):

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: shop
~~~

Ví dụ này dùng bucket `shop` và collection mặc định của bucket; cluster, bucket và tài khoản phải tồn tại, tài khoản phải có quyền cần thiết. Không đưa mật khẩu thật vào mã nguồn. Khi dùng scope/collection riêng, phải cấu hình ánh xạ và quyền truy cập tương ứng với phiên bản Spring Data đang dùng.

### 5.1. Ánh xạ Java object thành document

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Customer {
    @Id
    private String id;

    @Field
    private String fullName;

    @Field
    private String email;

    @Version
    private Long version;

    public Customer() {}

    public Customer(String id, String fullName, String email) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

- `@Document`: đánh dấu kiểu Java được ánh xạ thành document.
- `@Id`: xác định document key trong Couchbase.
- `@Field`: trường dữ liệu được ánh xạ vào JSON; các quy tắc converter quyết định chi tiết serialization.
- `@Version`: hỗ trợ **optimistic locking** dựa trên cơ chế CAS của Couchbase; khi bản đã đọc trở nên cũ, thao tác ghi có thể bị từ chối thay vì lặng lẽ ghi đè.

Spring Data cũng có thể lưu metadata về loại entity (thường là trường phân biệt kiểu) để phục vụ mapping. Vì thế, JSON thực tế do framework ghi có thể có thêm metadata so với ví dụ JSON minh họa ở phần 2.

### 5.2. Định nghĩa repository và service

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<Customer, String> {
    List<Customer> findByEmail(String email);
}
~~~

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Customer create(String fullName, String email) {
        String id = "customer::" + UUID.randomUUID();
        return customers.save(new Customer(id, fullName, email));
    }

    public Optional<Customer> getById(String id) {
        return customers.findById(id);
    }

    public List<Customer> searchByEmail(String email) {
        return customers.findByEmail(email);
    }
}
~~~

Trong ví dụ:

1. `save(...)` giúp đưa entity vào database mà không tự viết đoạn SDK để chuyển object thành JSON và gọi thao tác ghi.
2. `findById(...)` tìm theo document key, thường là đường truy cập KV phù hợp cho lookup một document.
3. `findByEmail(...)` là **derived query**: Spring Data suy ra điều kiện truy vấn từ tên phương thức. Tìm theo một trường khác ID thường dựa vào SQL++ và cần chỉ mục thích hợp.

Tên phương thức repository không đảm bảo rằng truy vấn đã tối ưu. Cần hiểu query được sinh ra, index được chọn và lượng document được quét. Trong hệ thống thật, phải thêm kiểm tra dữ liệu đầu vào, quy tắc trùng email, xử lý lỗi, timeout và quan sát truy vấn.

### 5.3. Vì sao tìm theo email cần index?

Với dữ liệu ở scope/collection mặc định, ví dụ một truy vấn SQL++ tương đương về mặt ý tưởng:

~~~sql
SELECT META(c).id AS documentId, c.fullName, c.email
FROM `shop`.`_default`.`_default` AS c
WHERE c.email = "an@example.com";
~~~

Một index minh họa cho điều kiện này:

~~~sql
CREATE INDEX ix_customer_email
ON `shop`.`_default`.`_default`(email);
~~~

Đây là truy vấn SQL++ độc lập để minh họa lựa chọn index, **không phải nguyên văn SQL++ mà Spring Data chắc chắn sẽ sinh ra**. Truy vấn do Spring Data phát sinh có thể bổ sung điều kiện loại entity và metadata phục vụ mapping. Khi dùng collection `crm.customers`, phải đổi keyspace và thiết kế chỉ mục đúng collection đó; không nên sao chép index ở collection mặc định một cách máy móc.

Chỉ mục làm tăng chi phí lưu trữ và ghi nhưng thường giảm chi phí truy vấn có điều kiện phù hợp. Truy vấn lọc, JOIN, ORDER BY, phân trang và projection có thể cần thiết kế index khác nhau. Dùng `EXPLAIN` và theo dõi thời gian thực thi để kiểm chứng thay vì mặc định mọi truy vấn SQL++ là nhanh.

## 6. Chọn đúng API cho từng công việc

| Nhu cầu | API thường phù hợp | Điều cần để ý |
| --- | --- | --- |
| CRUD theo ID, truy vấn đơn giản | `CouchbaseRepository` | Dễ dùng, tích hợp Spring Data; derived query vẫn cần index |
| Truy vấn đặc thù, thao tác linh hoạt hơn | `CouchbaseTemplate` | Chủ động hơn với query/mapping và tùy chọn thao tác |
| Nhiều request I/O đồng thời theo luồng reactive | `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate` | Trả `Mono`/`Flux`; cần giữ toàn bộ pipeline không chặn |
| Tính năng SDK chuyên biệt hoặc tinh chỉnh rất sâu | `Couchbase Java SDK` | Thêm quyền kiểm soát nhưng tăng công sức ánh xạ và tích hợp |

**Repository** phù hợp khi đa số trường hợp là tạo/đọc/sửa/xóa entity và một số truy vấn đơn giản. **Template** phù hợp khi service cần chủ động điều kiện truy vấn, mapping hoặc thao tác dữ liệu phức tạp hơn. Cả hai nằm trên SDK. Không cần chuyển toàn bộ ứng dụng sang SDK chỉ vì một thao tác đặc thù: có thể phối hợp nhưng cần thống nhất thời gian chờ, retry và quy tắc dữ liệu.

### Ví dụ reactive tối giản

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Mono;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {
    Mono<Customer> findByEmail(String email);
}
~~~

Với yêu cầu email có thể không duy nhất, chữ ký `Mono<Customer>` ở trên chỉ phù hợp khi **nghiệp vụ và dữ liệu bảo đảm tối đa một kết quả**; nếu không, dùng `Flux<Customer>` và xử lý danh sách. Reactive giúp sử dụng tài nguyên luồng hiệu quả khi có nhiều tác vụ I/O đồng thời; nó **không tự động** làm từng query nhanh hơn hoặc sửa lỗi thiếu index. Không gọi `block()` trong chuỗi xử lý WebFlux chỉ để lấy kết quả đồng bộ.

## 7. Tính nhất quán, CAS, TTL và giao dịch: những giới hạn không thể bỏ qua

### 7.1. Đọc theo ID khác với truy vấn qua index

Đọc document vừa ghi theo **ID qua KV** và tìm document vừa ghi bằng **SQL++ qua index** không nên được giả định có cùng hành vi nhất quán. Việc cập nhật index có thể trễ hơn thao tác ghi; kết quả SQL++ với scan consistency mặc định có thể tạm thời chưa phản ánh dữ liệu mới. Khi nghiệp vụ yêu cầu read-your-writes ở truy vấn, cần tìm hiểu tùy chọn như `request_plus` hoặc nhất quán theo mutation token (`consistent_with`) và chấp nhận chi phí độ trễ tương ứng.

**Ví dụ:** Người dùng đổi email, sau đó màn hình lập tức tìm bằng email mới. Đọc theo ID có thể cho dữ liệu mới nhưng màn hình tìm qua index chưa hiện ngay. Đây là yêu cầu nhất quán cần được thiết kế rõ ở tầng service, API query và trải nghiệm người dùng.

### 7.2. CAS và optimistic locking

Giả sử hai request cùng đọc giỏ hàng phiên bản V1. Request A thêm sản phẩm X, request B đổi số lượng sản phẩm Y. Nếu cả hai ghi đè toàn bộ document mà không kiểm tra phiên bản, thay đổi của một bên có thể mất.

~~~text
Thời điểm 1: A đọc cart (CAS=V1); B đọc cart (CAS=V1)
Thời điểm 2: A ghi thành công -> CAS=V2
Thời điểm 3: B ghi theo CAS=V1 -> xung đột, phải xử lý
~~~

Couchbase cung cấp CAS cho thao tác trên document; với entity có `@Version`, Spring Data có thể áp dụng optimistic locking. Khi xảy ra xung đột, ứng dụng nên trả thông báo phù hợp hoặc **đọc lại, áp dụng lại thay đổi nghiệp vụ rồi thử lại có giới hạn**. Không nên retry vô hạn hay ghi đè bất chấp, đặc biệt với giao dịch thanh toán hoặc tồn kho.

CAS giải quyết một nhóm vấn đề cập nhật đồng thời **trên một document**. Nó không tự tạo giao dịch nguyên tử cho nhiều document.

### 7.3. TTL/expiry

TTL cho phép Couchbase tự đánh dấu document hết hạn, hữu ích cho session, mã tạm, token dùng một lần hoặc giỏ hàng không hoạt động lâu. TTL là **metadata của document**, không đơn thuần là một trường JSON do ứng dụng tự so sánh. Các cách cấu hình expiry ở entity, template hoặc SDK và hành vi khi cập nhật phụ thuộc API/phiên bản, nên cần kiểm tra lại khi triển khai.

Không nên dùng TTL như cách duy nhất để bảo đảm một tác vụ phải chạy chính xác tại thời điểm hết hạn (ví dụ hoàn tiền đúng 00:00): document expiry phục vụ vòng đời dữ liệu, không phải hệ thống lịch tác vụ có bảo đảm thời gian thực.

### 7.4. Giao dịch đa document

Khi nghiệp vụ cập nhật cùng lúc nhiều document, ví dụ trừ tồn kho và tạo đơn hàng, cần quyết định yêu cầu nguyên tử, cô lập, khả năng retry và chi phí. Couchbase có cơ chế transaction đa document và tích hợp ở các cấp API tương ứng, nhưng **không thể suy từ một lệnh `repository.save()` rằng toàn bộ luồng nghiệp vụ đã là transaction**. Hãy kiểm tra rõ hỗ trợ và cấu hình transaction của bộ phiên bản Spring Data/SDK đang sử dụng.

Giao dịch nhiều document thường có chi phí và cách xử lý lỗi phức tạp hơn cập nhật một document. Với các luồng phân tán giữa nhiều dịch vụ, đôi khi phải kết hợp idempotency, outbox hoặc saga ở kiến trúc hệ thống; chọn theo bất biến nghiệp vụ thay vì chỉ theo tiện ích API.

## 8. Ba tình huống thiết kế thực tế

### Tình huống A — Xem chi tiết sản phẩm

Request có sẵn product ID, ví dụ `product::sku-123`. Service có thể gọi `findById` để đọc một document. Nên tối ưu khóa và nội dung sản phẩm cho màn hình chi tiết; không cần SQL++ chỉ để lấy document đã biết ID.

Nếu màn hình danh mục cần “sản phẩm còn hàng, thuộc nhóm X, giá tăng dần”, lúc đó cần truy vấn SQL++, index và chiến lược phân trang. Một API đọc tốt cho chi tiết sản phẩm không đồng nghĩa API tìm kiếm tốt.

### Tình huống B — Giỏ hàng và cạnh tranh cập nhật

Một giỏ hàng có thể biểu diễn dưới dạng document:

~~~json
{
  "customerId": "c123",
  "items": [
    { "sku": "sku-123", "quantity": 2 },
    { "sku": "sku-456", "quantity": 1 }
  ],
  "currency": "VND"
}
~~~

Đặt ID metadata là `cart::c123` để đọc nhanh giỏ hàng của người dùng. Các item được embed vì thường được đọc cùng nhau và trong bài toán thông thường kích thước có giới hạn. Dùng CAS/optimistic locking để tránh lost update khi nhiều tab cùng sửa giỏ hàng. TTL có thể thích hợp cho giỏ hàng khách vãng lai; với giỏ hàng đã đăng nhập, thời hạn lưu phải theo quy tắc sản phẩm.

### Tình huống C — Tìm khách hàng theo nhiều tiêu chí

Chức năng lọc theo email, hạng thành viên và ngày đăng ký không thể chỉ dựa vào document key. Thiết kế SQL++ và index theo mẫu truy vấn thực tế, ví dụ điều kiện email chính xác khác với lọc ngày + sắp xếp. Với dữ liệu lớn, tránh đọc mọi document vào bộ nhớ Java rồi mới lọc. Cần quan sát execution plan, số lượng kết quả và giới hạn/phân trang.

## 9. Những lỗi thường gặp khi bắt đầu

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `findById` nhanh nhưng `findByEmail` chậm hoặc lỗi query | Thiếu/sai index, query qua SQL++ | Kiểm tra index đúng keyspace và `EXPLAIN` |
| Vừa ghi xong nhưng tìm kiếm chưa thấy | Query qua index với chính sách consistency chưa đáp ứng read-your-writes | Xác định mức nhất quán, chọn tùy chọn query phù hợp |
| Người dùng làm mất cập nhật của người khác | Ghi đè document không kiểm tra CAS | `@Version`, xử lý xung đột và retry có giới hạn |
| Một document ngày càng lớn | Embed danh sách không giới hạn | Tách các đối tượng có vòng đời riêng, quản lý quan hệ qua ID |
| “Bật reactive” nhưng throughput không tăng | Pipeline có đoạn block, query/index vẫn là nút thắt | Rà soát blocking, pool, query plan và tài nguyên cluster |
| Triển khai môi trường khác chạy lỗi | Sai bucket/scope/collection, quyền tài khoản hoặc không khớp phiên bản | Quản lý cấu hình, role, migration index và dependency theo môi trường |
| Lưu được entity nhưng dữ liệu không đọc đúng kiểu | Mapping field, kiểu dữ liệu hay metadata entity thay đổi | Kiểm tra converter, schema evolution và tương thích dữ liệu |

Ngoài index, cần dự trù timeout, độ bền ghi (durability), retry có kiểm soát, metric và tracing; xử lý Couchbase exception thành lỗi nghiệp vụ/API phù hợp. Không retry bừa các thao tác không idempotent. Thực hiện load test với mẫu document và phân bố traffic gần thực tế trước khi kết luận giải pháp đáp ứng tải.

## 10. Khi nào nên chọn Spring Data Couchbase?

**Phù hợp khi** ứng dụng Spring xử lý dữ liệu dạng document JSON, thường xuyên đọc bằng key, cần các truy vấn SQL++ theo thuộc tính, muốn giảm mã CRUD/mapping và có thể khai thác ưu điểm scale-out của Couchbase. Các ví dụ hay gặp là hồ sơ người dùng, danh mục sản phẩm nhiều thuộc tính, giỏ hàng, session và dữ liệu nghiệp vụ có cấu trúc thay đổi theo thời gian.

**Cần cân nhắc thêm khi** hệ thống chủ yếu dựa vào các giao dịch quan hệ chặt chẽ nhiều bảng, JOIN phức tạp, ràng buộc khóa ngoại ở mức DB hoặc yêu cầu báo cáo phân tích khác biệt rõ với workload truy cập document. Couchbase vẫn hỗ trợ SQL++ và transaction, nhưng lựa chọn dữ liệu/kiến trúc cần căn cứ vào khối lượng công việc, mô hình nhất quán, kỹ năng vận hành và chi phí thực tế. Spring Data làm code thuận tiện hơn; nó không thay thế việc thiết kế dữ liệu và kiểm thử hiệu năng.

### Checklist trước khi xây tầng repository

1. Liệt kê các đường đọc/ghi phổ biến: theo **ID**, theo **thuộc tính**, hay cập nhật hàng loạt?
2. Chọn bucket/scope/collection và quy ước ID; xác định ranh giới embed/tham chiếu.
3. Định nghĩa entity, mapping và vòng đời schema; quyết định có cần optimistic locking, TTL hay transaction không.
4. Chọn Repository, Template, Reactive API hoặc SDK theo nhu cầu thật; thống nhất cách xử lý lỗi/timeout.
5. Thiết kế index từ mẫu truy vấn; xác nhận bằng `EXPLAIN`, không tạo chỉ mục tùy tiện.
6. Viết rõ yêu cầu nhất quán và xử lý race condition, đặc biệt với truy vấn ngay sau ghi.
7. Kiểm chứng trên dữ liệu và tải đại diện, theo dõi hiệu năng KV, query, index, retry và contention.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `findById("customer::c123")` thường không cần secondary index, còn `findByEmail("an@example.com")` thì cần?

**Gợi ý:** Một thao tác biết khóa document và đi theo KV; thao tác còn lại phải tìm document dựa trên giá trị trường JSON, thường qua SQL++/index.

**Câu 2.** Nếu hai tab sửa cùng một giỏ hàng, chỉ dùng `repository.save()` đã đủ để bảo đảm không mất dữ liệu chưa?

**Gợi ý:** Chưa thể bảo đảm nếu không có cơ chế kiểm soát xung đột. Cân nhắc `@Version`/CAS và chính sách thử lại hợp lý.

**Câu 3.** Sau khi tạo khách hàng, tìm bằng email chưa xuất hiện ngay nhưng đọc bằng ID đã có. Bạn cần điều tra điều gì?

**Gợi ý:** Kiểm tra query qua index, trạng thái cập nhật index, scan consistency và yêu cầu read-your-writes.

**Câu 4.** Vì sao chuyển hết repository sang reactive không chắc cải thiện độ trễ của một truy vấn SQL++ thiếu index?

**Gợi ý:** Reactive giảm chi phí chờ I/O tại ứng dụng, nhưng không thay đổi bản chất execution plan và công việc của Query/Index Service.

## 12. Kết luận

Spring Data Couchbase là tầng tích hợp giúp ứng dụng Spring dùng Couchbase thông qua **document mapping, repository, template và reactive API**. Giá trị lớn nhất là làm rõ ranh giới giữa domain object và thao tác lưu trữ, giảm mã lặp, đồng thời vẫn tiếp cận được KV và SQL++ khi cần.

Để sử dụng đúng, luôn phân biệt **truy cập theo ID** với **truy vấn theo thuộc tính**, đặt **document/collection/index** theo mẫu sử dụng thực tế và thiết kế rõ **CAS, TTL, consistency, transaction**. Khi những quyết định này được làm đúng, tầng truy cập dữ liệu vừa dễ phát triển trong Spring vừa có cơ sở để đạt hiệu năng, độ tin cậy và khả năng vận hành trên Couchbase.
