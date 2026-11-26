# Phân biệt nhóm thuộc tính `spring.couchbase` và `spring.data.couchbase`

## 1. Vì sao phải phân biệt hai nhóm thuộc tính?

Khi sử dụng **Spring Data Couchbase** trong một ứng dụng Spring Boot, developer thường thấy hai nhánh cấu hình có tên gần giống nhau:

- `spring.couchbase.*`
- `spring.data.couchbase.*`

Cả hai cùng phục vụ truy cập Couchbase, nhưng chúng trả lời **hai loại câu hỏi khác nhau**. Nhầm vị trí thuộc tính có thể làm ứng dụng dùng cluster hoặc bucket không đúng, hoặc khiến giá trị cấu hình không được bind như mong đợi.

Trong module **SPRING_DATA_COUCHBASE**, tầng truy cập dữ liệu gồm Couchbase SDK, document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++. Việc chia đúng cấu hình là bước nền tảng trước khi học bucket/scope/collection, index, TTL, CAS, giao dịch hoặc API reactive.

Sau bài này, bạn có thể xác định property thuộc nhóm nào, giải thích đường đi của cấu hình tới các bean, đọc được file YAML hỗn hợp, phát hiện sai vị trí property và chẩn đoán lỗi tại đúng lớp.

> **Ý chính:** `spring.couchbase.*` mô tả **kết nối đến cluster qua Couchbase SDK**; `spring.data.couchbase.*` mô tả **cách tầng Spring Data Couchbase sử dụng kết nối đó**, nổi bật là bucket mặc định.

Các ví dụ tập trung vào Spring Boot **3.x**, với phiên bản Spring Data Couchbase/Couchbase Java SDK do Spring Boot quản lý. Những property nâng cao có thể khác giữa các dòng phiên bản; luôn đối chiếu configuration metadata của phiên bản đang dùng.

## 2. Ranh giới SDK và Spring Data

Couchbase có cấu trúc tài nguyên theo thứ bậc:

~~~text
Couchbase Cluster
├── Node / Service (Data, Query, Index, ...)
├── Bucket: inventory
│   ├── Scope: sales
│   │   └── Collection: products
│   └── Scope: _default
│       └── Collection: _default
└── Bucket: analytics
    └── ...
~~~

Một ứng dụng có hai nhiệm vụ riêng:

1. **Kết nối cluster.** SDK cần biết địa chỉ bootstrap, username/password, giao thức/TLS và các tùy chọn mạng/timeout. Đây là trách nhiệm của `spring.couchbase.*`.
2. **Thực hiện ánh xạ và truy cập document.** Spring Data cần biết bucket mặc định để xây dựng tầng truy cập dữ liệu; repository và template dùng mapping để đi tiếp tới scope/collection. Đây là trách nhiệm chủ yếu của `spring.data.couchbase.*` kết hợp với các annotation hoặc cấu hình Spring Data.

~~~mermaid
flowchart TD
    C["spring.couchbase.*"] --> SDK["Couchbase SDK<br/>Cluster / môi trường kết nối"]
    D["spring.data.couchbase.*"] --> DATA["Spring Data Couchbase<br/>Bucket mặc định / mapping"]
    SDK --> DATA
    E["@Document, @Scope, @Collection"] --> DATA
    DATA --> API["CouchbaseRepository<br/>CouchbaseTemplate"]
    API --> KEYSPACE["Bucket → Scope → Collection"]
~~~

**Chú ý:** Spring Boot cung cấp auto-configuration cho các thành phần này khi starter phù hợp xuất hiện trên classpath và không có cấu hình thủ công thay thế. Việc khai báo properties **không tạo ra** cluster, bucket, scope, collection, chỉ mục hoặc user trên Couchbase Server.

## 3. Bảng so sánh trực diện

| Tiêu chí | `spring.couchbase.*` | `spring.data.couchbase.*` |
| --- | --- | --- |
| Tầng chính | Kết nối/thiết lập Couchbase Java SDK | Hạ tầng Spring Data Couchbase |
| Câu hỏi | “Kết nối tới **cluster nào**, bằng danh tính nào?” | “Spring Data sử dụng **bucket nào** và quản lý truy cập dữ liệu ra sao?” |
| Thuộc tính tiêu biểu | `connection-string`, `username`, `password` | `bucket-name` |
| Tác động chính | Bootstrap, xác thực, TLS, timeout và môi trường client | Bucket được chọn bởi client factory/template/repository mặc định |
| Quan hệ với entity | Chưa quyết định document thuộc collection nào | Bucket mặc định kết hợp với mapping của entity |
| Loại lỗi thường gặp | DNS, kết nối, TLS, xác thực, timeout | Sai bucket, thiếu quyền bucket hoặc chọn sai keyspace |
| Khi ứng dụng chuyển cluster | Thường phải cập nhật | Chỉ cập nhật nếu tên bucket trên cluster mới thay đổi |
| Khi chỉ đổi bucket trên cùng cluster | Có thể giữ nguyên | Thay đổi `bucket-name` và kiểm tra quyền |

Không nên suy luận rằng mọi thứ có chữ “Couchbase” đều đặt dưới cùng một prefix. **Tên property đầy đủ là một phần của hợp đồng cấu hình**; ví dụ `spring.couchbase.bucket-name` và `spring.data.couchbase.connection-string` không phải hai cách viết tương đương của các thuộc tính hợp lệ.

## 4. Nhóm `spring.couchbase.*`: cấu hình SDK kết nối cluster

### 4.1. Các thuộc tính cốt lõi

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
~~~

| Thuộc tính | Ý nghĩa | Ví dụ / lưu ý |
| --- | --- | --- |
| `spring.couchbase.connection-string` | Seed address để Couchbase SDK bootstrap cluster | `couchbase://127.0.0.1`, `couchbases://cb.example.internal` |
| `spring.couchbase.username` | Username để xác thực với Couchbase | Tài khoản ứng dụng được cấp RBAC |
| `spring.couchbase.password` | Password đi kèm username | Lấy từ biến môi trường hoặc secret manager |
| `spring.couchbase.env.*` | Một số tùy chọn môi trường SDK mà Spring Boot hỗ trợ | Timeout và các điều chỉnh kết nối phụ thuộc phiên bản |

Trong ví dụ, tên `CB_CONNECTION_STRING`, `CB_USERNAME`, `CB_PASSWORD` là **biến môi trường do ứng dụng đặt ra**, được chèn bằng cú pháp placeholder của Spring. Chúng không phải tên property được định nghĩa sẵn của Spring Boot.

**Connection string không chứa tên bucket theo dạng path.** Tên bucket thuộc tầng Spring Data và phải được khai báo riêng.

### 4.2. Giao thức kết nối và TLS

~~~text
# Cluster phát triển nội bộ, không dùng TLS
couchbase://127.0.0.1

# Một số seed node trong mạng private
couchbase://cb-1.internal,cb-2.internal

# TLS
couchbases://cb.example.internal
~~~

`couchbase://` và `couchbases://` biểu diễn hai cách bootstrap có yêu cầu bảo mật khác nhau. Khi kết nối cluster có TLS, ngoài prefix đúng, phải bảo đảm hostname, chứng chỉ tin cậy và chính sách mạng cho phép kết nối. Với cluster quản lý như Couchbase Capella, sử dụng connection string và hướng dẫn về mạng, chứng chỉ được cung cấp cho cluster cụ thể.

SDK có thể lấy topology sau khi kết nối seed node; một seed reachable **chưa chắc** toàn bộ các node/dịch vụ mà SDK cần đều reachable. Những lỗi dạng bootstrap timeout, DNS hoặc TLS nên được kiểm tra ở tầng kết nối, trước khi thay đổi entity, repository hay index SQL++.

### 4.3. Thuộc tính timeout là cấu hình kết nối, không phải cấu hình mapping

Trong các phiên bản Boot 3.x hỗ trợ, có thể cấu hình timeout của client theo nhóm môi trường, ví dụ:

~~~yaml
spring:
  couchbase:
    env:
      timeouts:
        connect: 10s
        query: 20s
~~~

Cú pháp `10s` và `20s` là các giá trị thời gian được bind sang `Duration`. Đây chỉ là ví dụ để nhận diện **nhóm thuộc tính**; cần kiểm tra tên thuộc tính và giá trị mặc định theo phiên bản Boot thực tế. Không nên tăng timeout vô điều kiện để che lỗi mạng, thiếu secondary index hoặc truy vấn không tối ưu.

### 4.4. Thứ mà nhóm này không quyết định

Dù kết nối và xác thực thành công, các property trong `spring.couchbase.*` tự chúng **không xác định**:

- Bucket mặc định cho Spring Data repository.
- Scope/collection dùng cho từng entity.
- Primary/secondary index cho SQL++.
- TTL hay CAS policy của từng document.
- Quy tắc lựa chọn đồng bộ hoặc reactive ở lớp service.

Những vấn đề này được giải quyết bằng nhóm cấu hình khác, annotation, API và thiết kế dữ liệu thích hợp.

## 5. Nhóm `spring.data.couchbase.*`: cấu hình tầng dữ liệu

### 5.1. Chọn bucket mặc định

Thuộc tính thường gặp và quan trọng nhất:

~~~yaml
spring:
  data:
    couchbase:
      bucket-name: inventory
~~~

`spring.data.couchbase.bucket-name` nói với hạ tầng Spring Data rằng các thao tác mặc định sẽ sử dụng bucket `inventory` trên cluster mà SDK đã kết nối.

Nó **không tự tạo bucket**; Couchbase Server phải có sẵn bucket với tên đó và tài khoản cần quyền phù hợp. Bucket name có thể giống nhau giữa các cluster khác nhau, nhưng vẫn tham chiếu đến hai tập dữ liệu khác nhau. Vì vậy khi chuyển môi trường, phải kiểm tra cả **địa chỉ cluster** lẫn **bucket**.

### 5.2. Scope và collection không nằm trong `bucket-name`

Giả sử trong bucket `inventory` có scope `catalog` và collection `products`. Có thể ánh xạ entity:

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

    private String name;

    protected ProductDocument() {}

    public ProductDocument(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
}
~~~

Khi một `CouchbaseRepository<ProductDocument, String>` lưu đối tượng, ba lớp xác định nơi ghi là:

| Lớp | Nguồn cấu hình | Kết quả |
| --- | --- | --- |
| Cluster | `spring.couchbase.connection-string` | Cluster đang kết nối |
| Bucket | `spring.data.couchbase.bucket-name` | `inventory` |
| Scope + Collection | `@Scope` + `@Collection` | `catalog.products` |

Do đó keyspace đầy đủ là `inventory.catalog.products`. Nếu không khai báo scope/collection, cần hiểu cơ chế mặc định của Spring Data và các collection `_default` tương ứng trong Couchbase.

**Đừng tạo property giả định** như `spring.data.couchbase.collection-name` rồi kỳ vọng toàn bộ entity tự đi vào collection đó. Collection thường được chọn qua annotation mapping hoặc API/config chuyên biệt; kiểm tra property metadata chính thức trước khi thêm các tên mới vào YAML.

### 5.3. Hai nhóm property không thay thế cho logic dữ liệu

Với repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Các thao tác theo ID như `findById` thường dùng Key-Value API. Khi thêm query theo thuộc tính và sử dụng SQL++, ứng dụng cần Query service, quyền và index phù hợp trên collection. Việc đặt `bucket-name` không tạo index.

Ví dụ, nếu thiết kế truy vấn dựa trên trường `name`, index mẫu phải đặt trên **đúng keyspace**:

~~~sql
CREATE INDEX ix_products_name
ON `inventory`.`catalog`.`products`(`name`);
~~~

Các yêu cầu TTL, CAS/optimistic locking, giao dịch và scan consistency nằm ở lựa chọn API, annotation, cấu hình Spring Data/SDK hoặc cách triển khai nghiệp vụ; không thể giải quyết bằng cách đổi nhóm prefix của property kết nối.

## 6. Ghép hai nhóm vào một file cấu hình hoàn chỉnh

Một ví dụ `application.yml` cho ứng dụng quản lý sản phẩm:

~~~yaml
spring:
  application:
    name: inventory-service

  # Nhánh A: kết nối tới cluster bằng Couchbase SDK
  couchbase:
    connection-string: "${CB_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"

  # Nhánh B: bucket mặc định ở tầng Spring Data
  data:
    couchbase:
      bucket-name: "${CB_BUCKET:inventory}"
~~~

Đường đi khi khởi động và truy cập:

~~~mermaid
sequenceDiagram
    participant APP as Spring Boot
    participant SDK as Couchbase SDK
    participant DATA as Spring Data Couchbase
    participant DB as Couchbase Cluster

    APP->>SDK: Bind spring.couchbase.*
    SDK->>DB: Bootstrap / authentication
    APP->>DATA: Bind spring.data.couchbase.*
    DATA->>DATA: Cấu hình bucket và entity mapping
    APP->>DATA: Repository / CouchbaseTemplate
    DATA->>DB: KV hoặc SQL++ tới đúng keyspace
~~~

Sơ đồ là trình tự trách nhiệm logic, không hàm ý rằng ứng dụng luôn mở kết nối đầy đủ hoặc xác minh mọi bucket ngay trong giai đoạn khởi tạo bean. Một số lỗi chỉ xuất hiện lúc có thao tác I/O thực tế.

### Mẫu Gradle/Maven liên quan

Để auto-configuration có các bean cần thiết, ứng dụng Spring Boot đồng bộ thường dùng dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Mô hình reactive có thể dùng `spring-boot-starter-data-couchbase-reactive`. **Lựa chọn starter quyết định kiểu API/repository mà ứng dụng sử dụng**; nhóm property kết nối cốt lõi vẫn phân chia như trên. Tránh cấu hình thủ công các bean lõi nếu không có nhu cầu đặc biệt, vì bean tùy chỉnh có thể ảnh hưởng điều kiện auto-configuration.

## 7. Các lỗi đặt nhầm prefix và cách sửa

Những đoạn YAML dưới đây minh họa lỗi hay gặp.

### Lỗi A: đặt `bucket-name` trong nhóm kết nối cluster

~~~yaml
# SAI
spring:
  couchbase:
    connection-string: couchbase://127.0.0.1
    username: app
    password: "${CB_PASSWORD}"
    bucket-name: inventory
~~~

**Sửa:**

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://127.0.0.1
    username: app
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: inventory
~~~

Nếu cấu hình sai được binder bỏ qua, ứng dụng có thể không báo rõ “unknown property” mà thất bại về sau do không có bucket đúng. Không lấy việc YAML parse thành công làm bằng chứng property đã có hiệu lực.

### Lỗi B: đặt `connection-string` vào nhánh Spring Data

~~~yaml
# SAI
spring:
  data:
    couchbase:
      connection-string: couchbase://cb.example.internal
      bucket-name: inventory
~~~

`connection-string` cần ở `spring.couchbase.connection-string`. Khi thiếu hoặc đặt sai property cluster, ứng dụng có thể dùng một cấu hình mặc định khác hoặc thất bại khởi tạo, tùy phiên bản và các nguồn cấu hình còn lại. Vì vậy phải xác minh **giá trị hiệu lực** chứ không suy luận từ vị trí của một dòng YAML.

### Lỗi C: xem bucket là database trong URL

~~~text
# Không dùng để chọn bucket trong Spring Data Couchbase
couchbase://cb.example.internal/inventory
~~~

Sử dụng:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://cb.example.internal
  data:
    couchbase:
      bucket-name: inventory
~~~

### Lỗi D: đổi cluster nhưng quên kiểm tra bucket

Ứng dụng local trỏ `couchbase://127.0.0.1` với bucket `inventory`. Khi chuyển sang cluster production, developer chỉ thay connection string nhưng không xác minh bucket cũng tồn tại ở cluster mới. Kết quả là có thể bootstrap được cluster nhưng lệnh KV thất bại vì bucket thiếu, permission sai hoặc scope/collection chưa được provision.

Những lỗi này không được sửa bằng cách thêm `@Document`, thay index hay tăng timeout. Hãy kiểm tra từng lớp theo thứ tự.

## 8. Biến môi trường và Spring profiles: cùng một hợp đồng property

Đôi khi local, staging và production dùng cùng một codebase nhưng khác cluster/bucket. Khi đó cấu trúc hai nhóm property vẫn giữ nguyên.

`application.yml` lưu phần chung:

~~~yaml
spring:
  couchbase:
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
~~~

`application-local.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://127.0.0.1
  data:
    couchbase:
      bucket-name: inventory_local
~~~

`application-prod.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_PROD_CONNECTION_STRING}"
  data:
    couchbase:
      bucket-name: "${CB_PROD_BUCKET}"
~~~

Với profile `prod`, Spring Boot dùng nhánh cluster cho kết nối tới cluster production và nhánh data cho bucket production. Username/password đến từ secret/biến môi trường theo chính sách triển khai.

**Hai lớp cấu hình độc lập nhưng phải tương thích:** có thể dùng cùng connection string nhưng chọn hai bucket khác nhau nếu tài khoản có quyền; cũng có thể giữ cùng tên bucket nhưng chuyển sang cluster khác. Không thể suy ra đúng bucket chỉ từ địa chỉ cluster, hoặc đúng cluster chỉ từ bucket name.

### Thứ tự ưu tiên và relaxed binding

Spring Boot có nhiều property sources (file YAML, environment, command-line, v.v.) với thứ tự ưu tiên riêng. Vì thế giá trị cuối cùng có thể khác ví dụ trong file, đặc biệt khi production truyền biến môi trường override.

Khi dùng biến môi trường **thông qua placeholder** như `"${CB_BUCKET}"`, Spring sẽ lấy đúng tên biến được chỉ định. Nếu dùng **biến môi trường để bind trực tiếp property**, cần tuân theo quy tắc ánh xạ tên của Spring Boot (chuyển dấu chấm sang gạch dưới, bỏ dấu nối, viết hoa). Ví dụ dạng chuẩn hóa trực tiếp:

~~~text
SPRING_COUCHBASE_CONNECTIONSTRING=couchbases://cb.example.internal
SPRING_COUCHBASE_USERNAME=app_reader
SPRING_COUCHBASE_PASSWORD=<secret từ runtime>
SPRING_DATA_COUCHBASE_BUCKETNAME=inventory
~~~

Không tự động giả định biến `SPRING_DATA_COUCHBASE_BUCKET_NAME` sẽ tương đương `SPRING_DATA_COUCHBASE_BUCKETNAME` ở mọi cơ chế bind/version; nếu muốn dùng một tên biến tùy ý, tham chiếu minh bạch bằng placeholder. Kiểm tra cấu hình có hiệu lực mà **không in mật khẩu** vào log.

## 9. Phương pháp chẩn đoán theo tầng

Khi gặp sự cố, bắt đầu từ triệu chứng và gắn với nhóm property liên quan:

| Triệu chứng | Nhóm cần kiểm tra đầu tiên | Kiểm tra cụ thể |
| --- | --- | --- |
| Không phân giải hostname | `spring.couchbase.*` | Connection string, DNS trong runtime |
| Bootstrap/connect timeout | `spring.couchbase.*` | Seed nodes, topology, mạng, TLS, timeout |
| Authentication failed | `spring.couchbase.*` | Username/password và secret được inject |
| Kết nối cluster được nhưng mở bucket không được | `spring.data.couchbase.*` rồi RBAC | `bucket-name`, bucket tồn tại, quyền tài khoản |
| Đọc ID không lỗi nhưng dữ liệu nằm nhầm collection | Mapping entity | `@Scope`, `@Collection` và bucket đang chọn |
| `findById` được, query tìm kiếm lỗi | Query/Index và quyền | SQL++, index trên đúng collection, dịch vụ Query |
| Repository không được tạo | Starter/auto-configuration/scan | Dependency, package scan, custom bean overrides |
| Staging trỏ vào dữ liệu local | Cả hai nhóm và nguồn cấu hình | Profile active, env overrides, giá trị effective |
| Đọc sau ghi bằng SQL++ chưa thấy dữ liệu mới | Query consistency | Chọn scan consistency phù hợp, phân biệt KV và Query |

Một trình tự smoke test hiệu quả:

1. **Xác nhận property có hiệu lực:** môi trường/profile, connection string (đã ẩn thông tin nhạy cảm), username và bucket name.
2. **Kiểm tra cluster:** DNS, mạng, TLS và xác thực dùng đúng tài khoản.
3. **Kiểm tra keyspace:** bucket/scope/collection đã tồn tại; tài khoản có quyền đọc/ghi cần thiết.
4. **Thử thao tác KV theo ID:** dùng repository `findById` trên entity ánh xạ đúng collection. Nếu trả về `Optional.empty()` mà không exception, đường đọc KV đến collection đã hoạt động.
5. **Thử truy vấn SQL++:** chỉ sau bước KV, kiểm tra Query service, index và quyền truy vấn trên đúng keyspace.
6. **Kiểm tra khía cạnh vận hành:** độ trễ, timeout, chỉ số lỗi, phân quyền tối thiểu và secrets không bị lộ.

Một lớp tự động cấu hình thành công chưa bảo đảm lớp dưới đã hoạt động hoàn toàn. Tùy cách khởi tạo, một số lỗi kết nối hoặc quyền bucket chỉ xuất hiện tại I/O đầu tiên.

## 10. Bài tập vận dụng: hai dịch vụ trên cùng cluster

Một tổ chức có cluster `couchbases://cb.example.internal` chứa hai bucket:

- `inventory` dành cho quản lý sản phẩm.
- `orders` dành cho đơn hàng.

Hai ứng dụng dùng cùng địa chỉ cluster nhưng tài khoản có thể khác để giới hạn quyền.

**Inventory service:**

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${INVENTORY_USERNAME}"
    password: "${INVENTORY_PASSWORD}"
  data:
    couchbase:
      bucket-name: inventory
~~~

**Order service:**

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${ORDERS_USERNAME}"
    password: "${ORDERS_PASSWORD}"
  data:
    couchbase:
      bucket-name: orders
~~~

Hãy tự trả lời:

1. Vì sao hai ứng dụng có thể dùng cùng `spring.couchbase.connection-string` nhưng khác `spring.data.couchbase.bucket-name`?
2. Nếu chuyển bucket `orders` sang cluster khác, cần kiểm tra lại những giá trị nào?
3. Vì sao một lỗi index trong `orders.commerce.order_items` không nhất thiết là lỗi cluster connection?
4. Điều gì xảy ra nếu developer nhầm `spring.couchbase.bucket-name: orders` thành cấu hình bucket hợp lệ?

**Đáp án định hướng:** hai nhóm cấu hình thuộc hai tầng; connection string xác định cluster, bucket name xác định bucket mặc định trong cluster đó. Khi di chuyển bucket, cần xác nhận cluster mới, tên bucket, quyền, scope/collection, index và cấu hình bảo mật. Lỗi Query service/index thuộc bước truy vấn, còn property bucket đặt sai prefix có thể không được Spring Boot bind như dự kiến.

## 11. Ghi nhớ để triển khai đúng

Khi xem một YAML Spring Boot tích hợp Couchbase, hãy đọc theo thứ tự:

- **`spring.couchbase.*`:** cluster ở đâu, đăng nhập bằng ai, kết nối qua mạng/TLS thế nào?
- **`spring.data.couchbase.*`:** bucket mặc định là gì?
- **Mapping và API:** entity nằm ở scope/collection nào, repository/`CouchbaseTemplate` truy cập bằng KV hay SQL++ và cần index/consistency gì?

Phân biệt đúng hai nhóm thuộc tính giúp tầng Spring Data Couchbase vận hành rõ ràng hơn và tránh nhầm lỗi cấu hình với lỗi document mapping, TTL, CAS, giao dịch hoặc reactive API. Từ đó có thể kiểm chứng và tối ưu từng lớp mà không thay đổi nhầm thành phần.

