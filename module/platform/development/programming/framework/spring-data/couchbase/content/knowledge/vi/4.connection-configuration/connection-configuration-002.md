# Khai báo chuỗi kết nối, thông tin xác thực và bucket

## 1. Mục tiêu và bối cảnh

Trong **Spring Data Couchbase**, cấu hình truy cập dữ liệu bắt đầu từ ba câu hỏi: ứng dụng sẽ kết nối tới **cluster nào**, dùng **danh tính nào**, và đọc/ghi dữ liệu trong **bucket nào**. Ba câu hỏi tương ứng với connection string, thông tin xác thực và bucket mặc định. Nếu chỉ một giá trị sai, tầng document mapping, `CouchbaseRepository` hoặc `CouchbaseTemplate` có thể khởi tạo không thành công hoặc thất bại khi thực hiện thao tác đầu tiên.

Bài học thuộc chương **Cấu hình kết nối** của module `SPRING_DATA_COUCHBASE`. Sau khi học, bạn có thể:

- Cấu hình `spring.couchbase.connection-string`, `spring.couchbase.username`, `spring.couchbase.password` và `spring.data.couchbase.bucket-name`.
- Phân biệt cluster, bucket, scope, collection; hiểu Couchbase SDK sử dụng connection string như thế nào.
- Chọn giao thức cho môi trường nội bộ hoặc kết nối TLS; tránh nhúng mật khẩu vào mã nguồn.
- Tách cấu hình local/production bằng biến môi trường hoặc Spring profiles.
- Kiểm tra quyền truy cập và khoanh vùng lỗi DNS, xác thực, bucket, collection, chỉ mục SQL++.

Các ví dụ sử dụng **Spring Boot 3.x** với starter Spring Data Couchbase và phiên bản Couchbase Java SDK do Spring Boot quản lý. Với hệ sinh thái khác phiên bản, xác nhận lại tên thuộc tính trong configuration metadata của phiên bản đang triển khai.

## 2. Hiểu đúng ba lớp cấu hình

Giả sử một ứng dụng quản lý đơn hàng có cấu trúc dữ liệu:

~~~text
Couchbase Cluster (các node và dịch vụ)
└── Bucket: sales
    ├── Scope: commerce
    │   ├── Collection: orders
    │   └── Collection: order_items
    └── Scope: _default
        └── Collection: _default
~~~

Ba tham số kết nối cơ bản không cùng vai trò:

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| Connection string | `couchbase://127.0.0.1` | Điểm bắt đầu để SDK tìm và kết nối các node/dịch vụ thuộc cluster |
| Username và password | `sales_app` / secret runtime | Xác thực danh tính và quyết định những thao tác được phép qua RBAC |
| Bucket | `sales` | Không gian dữ liệu mặc định mà Spring Data Couchbase truy cập |

**Bucket khác scope và collection.** Bucket được chọn qua property của Spring Data. Scope và collection có thể được định danh bởi mapping entity, chẳng hạn `@Scope("commerce")` và `@Collection("orders")`. Nếu entity không chỉ định hai giá trị này, cần hiểu rõ quy tắc mặc định trước khi thao tác để tránh ghi vào `_default._default`.

~~~mermaid
flowchart LR
    A["Ứng dụng Spring Boot"] --> B["Connection string<br/>Cluster bootstrap"]
    A --> C["Username / password<br/>Authentication"]
    A --> D["Bucket: sales<br/>Spring Data"]
    B --> E["Couchbase Cluster"]
    C --> E
    D --> F["Scope: commerce"]
    F --> G["Collection: orders"]
    E --> F
~~~

**Không đặt tên bucket vào phần path của connection string** theo thói quen từ một số cơ sở dữ liệu quan hệ. Với Spring Data Couchbase, connection string chỉ phục vụ bootstrap cluster; bucket mặc định có thuộc tính riêng.

## 3. Các thuộc tính chuẩn của Spring Boot

Để Spring Boot tự cấu hình `Cluster`, mapping, template và repository, cần starter Couchbase có trên classpath:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

Với mô hình truy cập reactive, có thể dùng `spring-boot-starter-data-couchbase-reactive`. Cả hai mô hình dùng cùng các nhóm thuộc tính kết nối cốt lõi.

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: sales-service
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:sales}"
~~~

| Property | Có bắt buộc trong ví dụ? | Công dụng |
| --- | --- | --- |
| `spring.couchbase.connection-string` | Có, có thể dùng giá trị mặc định local | Địa chỉ bootstrap cluster Couchbase |
| `spring.couchbase.username` | Có | Username của user Couchbase |
| `spring.couchbase.password` | Có | Mật khẩu, lấy từ nguồn secret |
| `spring.data.couchbase.bucket-name` | Có, có thể dùng giá trị mặc định local | Bucket mà Spring Data sử dụng mặc định |

**Cách đọc placeholder:** biểu thức `${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}` lấy biến môi trường `COUCHBASE_CONNECTION_STRING`; nếu không có, dùng giá trị local sau dấu `:`. Biểu thức `${COUCHBASE_USERNAME}` không có fallback: thiếu biến này là lỗi cấu hình cần xử lý, thay vì dùng tài khoản mặc định thiếu an toàn.

Ở ví dụ trên, bốn tên `COUCHBASE_*` là **quy ước biến môi trường do ứng dụng chọn**, không phải tên property cố định của Spring Boot. Spring Boot thay placeholder tại runtime.

Có một cách tương đương nếu muốn cấu hình hoàn toàn bằng biến môi trường chuẩn của Spring Boot mà không dùng placeholder trong YAML:

~~~text
SPRING_COUCHBASE_CONNECTION_STRING=couchbase://127.0.0.1
SPRING_COUCHBASE_USERNAME=<tên tài khoản>
SPRING_COUCHBASE_PASSWORD=<lấy từ secret manager>
SPRING_DATA_COUCHBASE_BUCKET_NAME=sales
~~~

Cơ chế *relaxed binding* ánh xạ các tên viết hoa bằng dấu gạch dưới thành các property tương ứng. Với cách này, không bắt buộc khai báo lại cả bốn giá trị trong `application.yml`. Chọn một quy ước nhất quán trong dự án để giảm nhầm lẫn giữa các nguồn cấu hình.

## 4. Khai báo connection string

### 4.1. Connection string là địa chỉ bootstrap

Couchbase Java SDK dùng connection string để liên hệ một hoặc nhiều seed node, lấy thông tin topology rồi mở kết nối tới các dịch vụ cần thiết như Key-Value hoặc Query. Nó **không phải** URL của giao diện quản trị Couchbase và cũng không bảo đảm toàn bộ đường đi mạng đã sẵn sàng chỉ vì một hostname phản hồi.

Một số dạng minh họa:

~~~text
# Couchbase Server chạy ở máy local (không TLS)
couchbase://127.0.0.1

# Nhiều seed node trong mạng nội bộ
couchbase://cb-node-1.internal,cb-node-2.internal

# Cluster yêu cầu TLS
couchbases://cb.example.internal
~~~

| Prefix | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `couchbase://` | Bootstrap theo giao thức Couchbase không bật TLS ở URL | Môi trường local hoặc mạng tự quản lý phù hợp chính sách bảo mật |
| `couchbases://` | Bootstrap qua TLS | Môi trường cloud/managed cluster hoặc kết nối yêu cầu mã hóa |

Tên miền trong ví dụ là giả định. Đối với Couchbase Capella hoặc một cluster quản lý, lấy chính xác chuỗi kết nối được nhà cung cấp cấp phát; đồng thời cấu hình các điều kiện mạng và tin cậy chứng chỉ tương ứng.

**Vì sao có thể kết nối một seed node nhưng vẫn timeout?** SDK có thể nhận topology chứa địa chỉ các node khác. Khi cluster nằm sau NAT, Docker, proxy hoặc mạng private/public tách biệt, các địa chỉ được quảng bá có thể không truy cập được từ nơi chạy ứng dụng. Cần kiểm tra cấu hình alternate addresses, DNS và đường mạng của cả các dịch vụ mà ứng dụng thực sự dùng, thay vì chỉ thử giao diện web.

### 4.2. TLS, hostname và chứng chỉ

Với `couchbases://`, kết nối cần xác thực chứng chỉ máy chủ theo cấu hình trust của JVM/SDK và môi trường triển khai. Một kết nối được bảo vệ đúng cần đồng thời thỏa mãn:

1. Endpoint mà ứng dụng dùng phân giải được và được phép kết nối qua mạng.
2. Chứng chỉ máy chủ hợp lệ đối với hostname được sử dụng.
3. Chuỗi CA/certificates được client tin cậy.
4. Tài khoản Couchbase có quyền truy cập các tài nguyên dự định dùng.

Không chuyển sang `couchbase://` hoặc tắt xác minh chứng chỉ chỉ để vượt qua lỗi TLS trong production. Cách khai báo chứng chỉ/trust store có thể khác nhau theo bản Spring Boot và SDK; áp dụng đúng hướng dẫn của phiên bản đang chạy.

## 5. Username, password và phân quyền

Couchbase thường dùng xác thực theo danh tính user và phân quyền dựa trên vai trò (RBAC). Trong Spring Boot, username/password được khai báo **tách** khỏi connection string:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET}"
~~~

**Không** ghép username và password vào connection string rồi kỳ vọng Spring Boot tự tách; cách đó cũng làm lộ secret khi URL xuất hiện trong log, trace hoặc bản chụp cấu hình.

Thiết kế quyền theo nhu cầu thực tế:

| Chức năng ứng dụng | Quyền cần xem xét |
| --- | --- |
| `findById` theo document ID | Quyền đọc KV trên collection đích |
| `save`, `deleteById` | Quyền ghi/xóa KV phù hợp |
| Repository query theo thuộc tính, SQL++ | Quyền chạy truy vấn trên keyspace được truy cập và index thích hợp |
| Tạo index, thay đổi scope/collection | Quyền quản trị riêng; thường dành cho tài khoản migration/DBA |

Quyền đọc/ghi document không đồng nghĩa với quyền tạo index hoặc quản trị bucket. Nên tạo **tài khoản ứng dụng với quyền tối thiểu** trên những bucket/scope/collection cần thiết, đồng thời dùng tài khoản quản trị khác cho bước provision hạ tầng.

### 5.1. Quản lý secret

- Ở local, truyền biến môi trường qua cấu hình chạy của IDE, terminal hoặc công cụ phát triển; không commit password thật.
- Ở production, ưu tiên secret manager hoặc cơ chế inject secrets của môi trường chạy (ví dụ Kubernetes Secret tích hợp hệ thống quản lý bí mật).
- Không in `spring.couchbase.password` ra log, endpoint chẩn đoán, báo cáo lỗi hoặc output build.
- Khi xoay vòng password, triển khai lại hoặc làm mới cấu hình của instance theo cơ chế vận hành; kiểm tra các kết nối hiện có và quyền của tài khoản mới.

Một file `application.yml` được commit với placeholder không chứa secret. Tuy nhiên, bản thân biến môi trường và secret mount cũng cần được kiểm soát quyền truy cập; không đưa chúng vào báo cáo hỗ trợ kỹ thuật hoặc ảnh chụp màn hình.

## 6. Chọn bucket mặc định

### 6.1. Bucket phải tồn tại trước

Thuộc tính:

~~~yaml
spring:
  data:
    couchbase:
      bucket-name: sales
~~~

chỉ **chọn** bucket có tên `sales`. Nó không yêu cầu Couchbase Server tự tạo bucket. Trước khi chạy ứng dụng cần bảo đảm:

- Bucket `sales` đã được tạo trên đúng cluster.
- Tài khoản sử dụng có quyền truy cập bucket và những collection cần dùng.
- Dung lượng, persistence và các chính sách vận hành của bucket đã được thiết lập bởi người quản trị.
- Scope/collection mà entity trỏ tới cũng đã tồn tại nếu không dùng vùng mặc định.

**Bucket sai tên** có thể biểu hiện khác nhau tùy thời điểm SDK thực hiện I/O. Startup không báo lỗi không đồng nghĩa ứng dụng đã đọc/ghi thành công; cần có kiểm thử thực tế.

### 6.2. Bucket, scope và collection trong entity

Ví dụ bucket `sales` chứa scope `commerce` và collection `orders`. Cấu hình `bucket-name: sales` đi cùng entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    private String customerId;

    protected OrderDocument() {}

    public OrderDocument(String id, String customerId) {
        this.id = id;
        this.customerId = customerId;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }
}
~~~

Repository truy cập entity:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

Khi gọi `repository.save(new OrderDocument("order::1001", "customer::42"))`, mapping dự định ghi vào keyspace:

~~~text
bucket = sales
scope = commerce
collection = orders
document key = order::1001
~~~

`@Id` biểu diễn document key, **không** phải một cột khóa chính quan hệ. Ghi/đọc theo ID thông qua KV thường không đòi hỏi secondary index. Ngược lại, các query theo thuộc tính (ví dụ tìm theo `customerId`) thường sử dụng SQL++ và cần Query service, quyền tương ứng và index trên collection chính xác.

Nếu một ứng dụng cần truy cập nhiều bucket, property `spring.data.couchbase.bucket-name` vẫn chỉ là **bucket mặc định**. Các tình huống nhiều bucket yêu cầu cấu hình client factory/template hoặc chiến lược truy cập thích hợp theo thiết kế dự án; không thể thay bucket bằng cách đổi `@Collection`.

## 7. Tách cấu hình local và production

Một cách dễ kiểm soát là giữ phần cấu hình chung trong `application.yml`, sau đó đặt khác biệt không nhạy cảm vào profile.

`application.yml`:

~~~yaml
spring:
  application:
    name: sales-service
  couchbase:
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
~~~

`application-local.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://127.0.0.1
  data:
    couchbase:
      bucket-name: sales_local
~~~

`application-prod.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_PROD_CONNECTION_STRING}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_PROD_BUCKET}"
~~~

Ứng dụng chọn profile bằng `spring.profiles.active` hoặc biến `SPRING_PROFILES_ACTIVE` do môi trường cung cấp. Cấu hình trên chỉ là ví dụ: cả local và production vẫn phải cung cấp `COUCHBASE_USERNAME` và `COUCHBASE_PASSWORD`; production cần thêm connection string và bucket tương ứng.

**Lưu ý về thứ tự ưu tiên:** các nguồn cấu hình Spring Boot có thứ tự ưu tiên khác nhau; biến môi trường có thể ghi đè giá trị được định nghĩa trong file YAML. Khi kiểm tra một cấu hình có vẻ “không ăn”, xác định profile đang active và nguồn cuối cùng của property, thay vì sửa nhiều file theo phỏng đoán. Không dump toàn bộ environment trong log vì có thể làm lộ password.

## 8. Kết nối cluster chưa đồng nghĩa truy cập bucket thành công

Cấu hình có thể được parse và bean được tạo, nhưng I/O đầu tiên vẫn thất bại nếu network, credentials, bucket hay quyền bị sai. Việc xác minh nên tách thành các lớp:

~~~mermaid
flowchart TD
    A["Đọc cấu hình & khởi tạo bean"] --> B{"Bootstrap cluster?"}
    B -- "Không" --> C["Kiểm tra DNS, seed node, TLS, network"]
    B -- "Có" --> D{"Xác thực?"}
    D -- "Không" --> E["Kiểm tra username, password, secret"]
    D -- "Có" --> F{"Mở bucket & thực hiện KV?"}
    F -- "Không" --> G["Kiểm tra bucket, RBAC, scope, collection"]
    F -- "Có" --> H{"Chạy truy vấn SQL++?"}
    H -- "Không" --> I["Kiểm tra Query service, index, quyền"]
    H -- "Có" --> J["Cấu hình truy cập đã được kiểm chứng"]
~~~

### 8.1. Kiểm thử KV tối thiểu

Trong dự án nhỏ, có thể kiểm tra repository trên môi trường local bằng một lệnh đọc ID không tồn tại. Nếu trả về `Optional.empty()` mà không ném lỗi, ứng dụng đã thực thi được thao tác đọc KV trên collection mà entity ánh xạ.

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
class LocalCouchbaseProbe {

    @Bean
    ApplicationRunner checkCouchbase(OrderRepository orders) {
        return args -> {
            // ID cố ý không tồn tại: mong đợi Optional.empty().
            orders.findById("probe::missing");
            System.out.println("Couchbase KV read completed");
        };
    }
}
~~~

Đoạn này chỉ là smoke test **dành cho local**, không phải endpoint health production. Lệnh đọc theo ID không cần tự tạo dữ liệu thử và không yêu cầu secondary index. Nếu lệnh ném lỗi, hãy kiểm tra đúng bucket, scope, collection, quyền KV và kết nối tới Data service.

Không dùng `findAll()` làm kiểm thử bootstrap đầu tiên: thao tác đó thường liên quan Query service và index, khiến khó phân biệt lỗi kết nối với lỗi truy vấn.

### 8.2. Kiểm thử truy vấn sau KV

Khi KV đã hoạt động, mới tiếp tục xác nhận truy vấn SQL++ và index bằng truy vấn nghiệp vụ thực tế. Ví dụ tìm đơn hàng theo `customerId` cần index trên đúng collection:

~~~sql
CREATE INDEX ix_orders_customer_id
ON `sales`.`commerce`.`orders`(`customerId`);
~~~

Việc tạo index nên nằm trong quy trình migration/hạ tầng có quyền phù hợp, không tự động chạy bằng tài khoản ứng dụng ở mỗi lần startup. Khi cần nhất quán ngay sau ghi đối với kết quả SQL++, đánh giá scan consistency thích hợp; thao tác KV theo ID và truy vấn SQL++ có đặc tính quan sát dữ liệu khác nhau.

## 9. Bảng chẩn đoán nhanh

| Triệu chứng | Cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| Không phân giải được hostname | `spring.couchbase.connection-string`, DNS | Xác minh domain, endpoint và mạng mà tiến trình sử dụng |
| Bootstrap timeout | Seed node, topology, địa chỉ các node được quảng bá, port dịch vụ | Đảm bảo SDK tới được tất cả dịch vụ cần dùng |
| TLS handshake/certificate error | Prefix `couchbases://`, hostname, trust chain | Sửa trust/certificate hoặc endpoint hợp lệ |
| Authentication failed | `username`, `password`, nguồn secret | Kiểm tra thông tin đăng nhập và thời điểm rotation |
| Access denied | Quyền RBAC trên bucket/scope/collection | Cấp đúng quyền dữ liệu cho tài khoản ứng dụng |
| Bucket not found | `spring.data.couchbase.bucket-name` và cluster | Xác minh bucket tồn tại trên cluster đang kết nối |
| `findById` được nhưng truy vấn repository lỗi | Query service, index, quyền SQL++ | Kiểm tra keyspace, index và quyền truy vấn |
| Ghi sai collection | `@Scope`, `@Collection`, bucket mặc định | Đối chiếu mapping với thiết kế dữ liệu |
| Hoạt động local, thất bại trên môi trường khác | Profile active, env override, mạng/TLS | Xác nhận giá trị effective config nhưng che secrets |

**Nguyên tắc chẩn đoán:** lần lượt xác định **đang chạy với cấu hình nào → kết nối được cluster chưa → xác thực được chưa → thao tác KV trên đúng collection được chưa → truy vấn SQL++ được chưa**. Các lớp này có ranh giới lỗi khác nhau; tránh tăng timeout hoặc thay đổi index khi vấn đề thực tế nằm ở DNS hay password.

## 10. Tình huống thực hành: thay đổi môi trường triển khai

Nhóm phát triển đã chạy thành công ứng dụng trên laptop với:

~~~text
connection string = couchbase://127.0.0.1
bucket = sales_local
~~~

Khi triển khai lên cluster có TLS, nhóm phải khai báo kết nối và quyền của môi trường mới; nếu vẫn dùng giá trị fallback local, tiến trình sẽ cố kết nối về chính máy/container đang chạy.

Quy trình thực hành:

1. Chuẩn bị một bucket `sales_prod`, scope `commerce`, collection `orders` trên cluster mục tiêu; cấp quyền cần thiết cho `sales_app_prod`.
2. Cấp `COUCHBASE_PROD_CONNECTION_STRING` với endpoint `couchbases://...` và `COUCHBASE_PROD_BUCKET=sales_prod`; cung cấp username/password qua secret manager.
3. Chọn profile `prod` và xác nhận runtime dùng đúng property sources.
4. Kiểm tra DNS, TLS và đường mạng từ máy/container chạy ứng dụng tới cluster mục tiêu.
5. Thực hiện phép đọc KV theo một ID thử nghiệm trên collection đích, rồi kiểm chứng truy vấn theo `customerId` sau khi index đã sẵn sàng.
6. Xác nhận application logs không chứa password và tài khoản ứng dụng không cần quyền tạo bucket hay index.

**Tiêu chí hoàn thành:** kết nối đúng cluster, xác thực bằng user ứng dụng, đọc/ghi đúng bucket/scope/collection, truy vấn hoạt động với index phù hợp và toàn bộ credentials được truyền an toàn theo từng môi trường.

## 11. Tổng kết kiến thức

Trong Spring Data Couchbase, `spring.couchbase.connection-string` mô tả **cluster cần kết nối**, `spring.couchbase.username/password` cung cấp **danh tính để xác thực**, còn `spring.data.couchbase.bucket-name` quyết định **bucket mặc định**. Scope và collection thuộc tầng mapping hoặc cấu hình truy cập cụ thể. Spring Boot starter giúp tự tạo những bean cần thiết, nhưng không tạo bucket hay cấp quyền phía Couchbase.

Thiết kế cấu hình tốt cần đi cùng thực hành vận hành: secret tách khỏi mã nguồn, TLS và kết nối mạng đúng môi trường, RBAC ở phạm vi tối thiểu, profile rõ ràng và smoke test KV trước khi kiểm tra các truy vấn SQL++. Đây là nền tảng để đi tiếp tới document mapping, repository, `CouchbaseTemplate`, index, TTL, CAS, giao dịch và lựa chọn API reactive mà không nhầm lỗi cấu hình với lỗi logic dữ liệu.

