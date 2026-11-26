# Chọn scope mặc định trong cấu hình Spring Data Couchbase

Trong **Spring Data Couchbase**, ứng dụng có thể dùng scope `_default` của Couchbase hoặc chọn một scope nghiệp vụ, chẳng hạn `commerce`, làm **scope mặc định ở cấp cấu hình ứng dụng**. Quyết định này ảnh hưởng trực tiếp đến nơi repository và `CouchbaseTemplate` đọc, ghi document khi thao tác không chỉ rõ scope riêng.

Điểm cần phân biệt ngay từ đầu: **scope `_default` của Couchbase Server** là một tài nguyên có tên cụ thể trong bucket; còn **scope mặc định trong cấu hình Spring Data** là giá trị được ứng dụng lựa chọn để sử dụng khi thao tác chưa khai báo scope khác. Giá trị của ứng dụng có thể là `_default` hoặc một scope tùy chỉnh.

Bài này hướng dẫn cách thiết lập, ghi đè và kiểm tra lựa chọn đó, áp dụng trong chương *Scope và Collection* của module `SPRING_DATA_COUCHBASE`. Kiến thức cũng giúp tránh lỗi khi dùng repository, `CouchbaseTemplate`, SQL++, API reactive, chỉ mục và quyền truy cập.

## 1. Hiểu rõ hai ý nghĩa của “mặc định”

Giả sử bucket `shop` có cấu trúc:

```text
shop
├── _default                  # scope mặc định được Couchbase tạo sẵn
│   ├── _default              # collection mặc định trong scope _default
│   └── audit                 # collection tạo thêm trong scope _default
└── commerce                  # scope do ứng dụng/người quản trị tạo
    ├── orders                # collection do ứng dụng/người quản trị tạo
    └── customers             # collection do ứng dụng/người quản trị tạo
```

Một document luôn thuộc về **một bucket, một scope và một collection**. Ví dụ, `shop.commerce.orders` và `shop._default._default` là hai nơi lưu khác nhau. Key `order::1001` có thể xuất hiện ở cả hai mà không đại diện cho cùng một document.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Scope mặc định của **Couchbase Server** | Scope hệ thống có tên `_default` trong mỗi bucket. | `shop._default` |
| Scope mặc định của **ứng dụng Spring Data** | Scope được cấu hình làm lựa chọn nền khi không có chỉ định có ưu tiên cao hơn. | `commerce` |
| Collection mặc định của **Couchbase Server** | Collection `_default`, chỉ có trong scope `_default`. | `shop._default._default` |
| Collection nghiệp vụ | Collection được tạo riêng để lưu loại dữ liệu cụ thể. | `shop.commerce.orders` |

**Quy tắc rất quan trọng:** Một scope tùy chỉnh như `commerce` **không có collection `_default`**, và không thể tự tạo collection dành riêng đó trong scope tùy chỉnh. Theo mô hình được Spring Data Couchbase hỗ trợ, có ba cặp hợp lệ:

1. Scope `_default` + collection `_default`.
2. Scope `_default` + collection tự tạo, ví dụ `audit`.
3. Scope tự tạo + collection tự tạo, ví dụ `commerce.orders`.

Vì thế, khi chuyển scope mặc định của ứng dụng từ `_default` sang `commerce`, **phải xác định collection đích** cho các document cần lưu. Đặt `scope-name: commerce` nhưng không có mapping collection thích hợp có thể khiến thao tác nhắm tới một tổ hợp scope/collection không tồn tại.

## 2. Chọn scope mặc định qua application.yml của Spring Boot

Trong dự án Spring Boot sử dụng Spring Data Couchbase, cấu hình thông dụng gồm thông tin kết nối cluster, bucket và scope:

```yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}

  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce
```

Ý nghĩa từng cấu hình:

- `spring.couchbase.connection-string`: địa chỉ kết nối tới Couchbase cluster.
- `spring.couchbase.username` và `spring.couchbase.password`: thông tin xác thực; ví dụ nhận qua biến môi trường, không lưu mật khẩu thật trong mã nguồn.
- `spring.data.couchbase.bucket-name`: bucket được Spring Data sử dụng, ở đây là `shop`.
- `spring.data.couchbase.scope-name`: scope **mặc định của Spring Data**, ở đây là `commerce`.

Trong Spring Boot hỗ trợ thuộc tính này, cấu hình tương ứng ở `application.properties` là:

```properties
spring.couchbase.connection-string=couchbase://localhost
spring.couchbase.username=${COUCHBASE_USERNAME}
spring.couchbase.password=${COUCHBASE_PASSWORD}
spring.data.couchbase.bucket-name=shop
spring.data.couchbase.scope-name=commerce
```

### Khi muốn dùng scope `_default`

Thông thường, chỉ cần **không khai báo** `spring.data.couchbase.scope-name`:

```yaml
spring:
  data:
    couchbase:
      bucket-name: shop
      # scope-name được bỏ qua -> dùng scope _default
```

Không cần đặt giá trị thành chuỗi rỗng hoặc giả định tên một collection mặc định trong scope nghiệp vụ. Cấu hình mặc định của `AbstractCouchbaseConfiguration.getScopeName()` trả về `null`, biểu thị sử dụng scope mặc định.

**Lưu ý:** Ví dụ cú pháp dựa trên cơ chế cấu hình Spring Boot 3.x/Spring Data Couchbase hiện đại. Khi dùng phiên bản cụ thể, hãy đối chiếu danh sách thuộc tính của chính phiên bản đó và kiểm tra có cấu hình Java tùy chỉnh ghi đè cơ chế tự động hay không.

## 3. Chọn scope mặc định bằng cấu hình Java

Dự án không dùng Spring Boot auto-configuration, hoặc chủ động quản lý Spring Data Couchbase bằng Java, có thể mở rộng `AbstractCouchbaseConfiguration` và ghi đè `getScopeName()`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.couchbase.config.AbstractCouchbaseConfiguration;

@Configuration
public class CouchbaseDataConfig extends AbstractCouchbaseConfiguration {

    @Override
    public String getConnectionString() {
        return "couchbase://localhost";
    }

    @Override
    public String getUserName() {
        return System.getenv("COUCHBASE_USERNAME");
    }

    @Override
    public String getPassword() {
        return System.getenv("COUCHBASE_PASSWORD");
    }

    @Override
    public String getBucketName() {
        return "shop";
    }

    @Override
    protected String getScopeName() {
        return "commerce";
    }
}
```

Phương thức `getScopeName()` có thể lấy giá trị từ cấu hình môi trường thay vì cố định `commerce`. Nếu muốn dùng scope `_default`, có thể không ghi đè phương thức này hoặc để nó trả về `null` theo hợp đồng của Spring Data.

Chọn **một cách quản lý cấu hình chính** cho ứng dụng: nếu dự án tự khai báo các bean và cấu hình Couchbase qua Java, cần xác minh cơ chế đó đang là nguồn cấu hình được sử dụng. Không nên mặc định cho rằng giá trị trong `application.yml` sẽ thắng mọi bean Java do ứng dụng tự tạo.

## 4. Kết hợp scope mặc định với mapping collection

Chọn scope mặc định **không tương đương** với chọn collection mặc định. Với cấu hình `bucket-name: shop` và `scope-name: commerce`, entity cần biết collection nghiệp vụ đích.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;

    // Constructor và getter/setter được lược bỏ.
}
```

Repository:

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Trong trường hợp không có override khác:

- Bucket đến từ cấu hình: `shop`.
- Scope đến từ cấu hình: `commerce`.
- Collection đến từ `@Collection("orders")`: `orders`.
- Đường dẫn lưu dữ liệu của entity: **`shop.commerce.orders`**.

Lệnh `orderRepository.save(order)` và `orderRepository.findById(id)` sẽ thao tác trên collection đó, với điều kiện schema/entity và cấu hình repository hợp lệ.

### Khai báo cả scope và collection ngay trên entity

Nếu muốn entity tự thể hiện đầy đủ đích lưu, có thể dùng:

```java
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
    private String status;

    // Constructor và getter/setter được lược bỏ.
}
```

Lúc này, khi không có override có ưu tiên cao hơn, annotation `@Scope("commerce")` của entity được dùng thay cho scope nền trong cấu hình.

Cách khai báo tường minh thường hữu ích khi ứng dụng làm việc với nhiều scope, nhưng cũng cần cân nhắc khả năng tái sử dụng entity ở những môi trường khác nhau. Tránh cùng lúc đặt nhiều khai báo xung đột mà không có chủ đích.

### Đặt scope/collection trên repository

Spring Data Couchbase cũng hỗ trợ chỉ định scope và collection ở cấp interface repository:

```java
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

@Scope("commerce")
@Collection("orders")
public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
```

Khi các annotation repository và entity khác nhau, annotation repository có độ ưu tiên cao hơn đối với thao tác qua repository đó. Quy tắc này hỗ trợ chọn phạm vi theo cách truy cập, nhưng nên dùng nhất quán để hạn chế bất ngờ khi bảo trì.

## 5. Quy tắc ưu tiên khi có nhiều nơi khai báo scope

Một ứng dụng có thể khai báo scope trong cấu hình nền, trên entity, trên repository hoặc ngay tại một thao tác `CouchbaseTemplate`. Tài liệu Spring Data Couchbase công bố thứ tự từ **ưu tiên cao xuống thấp**:

| Thứ tự | Cơ chế chọn scope/collection | Khi nào hữu ích |
| --- | --- | --- |
| 1 | Fluent API `inScope()` / `inCollection()` của một thao tác template. | Đọc/ghi một lần vào nơi được chọn rõ ràng. |
| 2 | `withScope()` / `withCollection()` trên đối tượng hỗ trợ đổi phạm vi, ví dụ repository theo `DynamicProxyable`. | Chọn phạm vi theo ngữ cảnh xử lý. |
| 3 | Annotation tại phương thức repository. | Điều chỉnh một phương thức cụ thể. |
| 4 | Annotation tại interface repository. | Dùng cùng đích cho repository. |
| 5 | Annotation tại entity. | Tập trung ánh xạ trên kiểu document. |
| 6 | Scope lấy từ cấu hình chung. | Giá trị nền cho những thao tác chưa chỉ định scope khác. |

Ví dụ, nếu cấu hình chung đặt `commerce` nhưng entity khai báo `@Scope("_default")` và `@Collection("audit")`, các thao tác phù hợp với mapping entity đó sẽ chọn `shop._default.audit` khi không có ghi đè khác.

Với template, có thể chỉ định ngay nơi truy vấn:

```java
List<OrderDocument> orders = couchbaseTemplate
        .findByQuery(OrderDocument.class)
        .inScope("commerce")
        .inCollection("orders")
        .all();
```

Ở ví dụ trên, `inScope("commerce")` và `inCollection("orders")` là lựa chọn trực tiếp của thao tác, không phải thay đổi cấu hình mặc định cho toàn ứng dụng.

**Cách suy luận đúng:** Xác định scope và collection **cuối cùng của từng thao tác** bằng cách xem cấu hình nền rồi lần lượt kiểm tra các cơ chế có độ ưu tiên cao hơn; đừng chỉ nhìn một thuộc tính YAML rồi kết luận mọi repository đều dùng cùng scope.

## 6. Kết hợp với môi trường development, test và production

Có thể dùng cùng một bản build nhưng cấu hình scope khác nhau giữa các môi trường.

```yaml
# application-dev.yml
spring:
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce_dev
```

```yaml
# application-prod.yml
spring:
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce
```

Khi dùng cách này, các collection được ánh xạ trong entity/repository (ví dụ `orders`, `customers`) phải tồn tại ở **cả hai scope**. Đồng thời, chỉ mục và quyền cần được chuẩn bị riêng cho từng keyspace.

Bảng minh họa:

| Profile | Scope cấu hình | Annotation `@Collection("orders")` | Đích thực tế |
| --- | --- | --- | --- |
| `dev` | `commerce_dev` | `orders` | `shop.commerce_dev.orders` |
| `prod` | `commerce` | `orders` | `shop.commerce.orders` |

Nếu entity cố định `@Scope("commerce")` thì cấu hình `commerce_dev` ở profile dev có thể **không được sử dụng** cho entity đó, vì annotation ưu tiên hơn cấu hình nền. Đây là lý do cần chọn một chiến lược rõ ràng:

- **Scope theo môi trường:** đặt scope trong YAML/profile; trên entity chỉ đặt `@Collection` khi phù hợp.
- **Scope cố định theo nghiệp vụ:** khai báo `@Scope` cùng `@Collection` trên entity hoặc repository; điều chỉnh phạm vi qua cấu hình hoặc API có chủ đích khi cần.

Không đưa mật khẩu hoặc tài khoản production thật vào profile. Sử dụng biến môi trường hay kho quản lý bí mật theo quy trình triển khai của nhóm.

## 7. Scope mặc định ảnh hưởng gì tới SQL++ và SDK?

### SQL++ phải trỏ đúng keyspace

Khi truy vấn trên collection nghiệp vụ `shop.commerce.orders`, một câu SQL++ tường minh có dạng:

```sql
SELECT META(o).id AS documentId,
       o.customerId,
       o.status
FROM `shop`.`commerce`.`orders` AS o
WHERE o.status = "CONFIRMED";
```

Câu lệnh trên sử dụng đầy đủ `bucket.scope.collection`; nó dễ kiểm tra trong Query Workbench, log và quá trình xử lý sự cố.

Nếu truy vấn dựa vào chỉ mục thứ cấp, chỉ mục phải tồn tại **trên đúng collection**:

```sql
CREATE INDEX ix_orders_status
ON `shop`.`commerce`.`orders`(status);
```

Chỉ mục của `shop._default._default` không tự phục vụ truy vấn `shop.commerce.orders`.

### Không nhầm cấu hình Spring Data với query context của Java SDK

Ví dụ mã SDK gọi trực tiếp:

```java
Bucket bucket = cluster.bucket("shop");
Scope commerce = bucket.scope("commerce");
Collection orders = commerce.collection("orders");

// KV: xác định trực tiếp collection.
JsonObject document = orders.get("order::1001").contentAsObject();

// SQL++ qua Scope.query: có query context là scope commerce.
QueryResult result = commerce.query(
    "SELECT o.* FROM `orders` AS o WHERE o.status = 'CONFIRMED'"
);
```

Trong ví dụ này, `Bucket`, `Scope`, `Collection`, `JsonObject` và `QueryResult` là các kiểu của Couchbase Java SDK (cần import tương ứng). Gọi `commerce.query(...)` cho phép sử dụng keyspace tương đối `orders` theo query context của scope.

Ngược lại, câu lệnh SQL++ gọi trực tiếp qua `cluster.query(...)` thường nên nêu đủ `bucket.scope.collection` hoặc truyền query context phù hợp. **`spring.data.couchbase.scope-name` không tự thay đổi mọi lời gọi SDK tự viết bên ngoài Spring Data.**

### Repository, template và reactive

- `CouchbaseRepository` sử dụng mapping và cơ chế chọn scope/collection của Spring Data.
- `CouchbaseTemplate` có thể dùng giá trị nền hoặc ghi đè qua fluent API khi tác vụ cần chọn phạm vi cụ thể.
- `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate` sử dụng cùng khái niệm định vị dữ liệu; chọn reactive chủ yếu ảnh hưởng mô hình xử lý bất đồng bộ, không làm scope/collection tự xuất hiện.

Việc chọn scope cũng không tự thay đổi quy tắc TTL, CAS hoặc tính nguyên tử. Các đặc tính đó vẫn phụ thuộc thao tác, collection, cấu hình server và API được sử dụng; thay đổi scope có thể làm ứng dụng thao tác với document khác dù key giống nhau.

## 8. Chuẩn bị tài nguyên trước khi chạy ứng dụng

Khai báo `scope-name: commerce` hay `@Collection("orders")` **không tự tạo** tài nguyên tương ứng trong Couchbase Server. Cần chuẩn bị trước:

1. Bucket `shop` tồn tại.
2. Scope `commerce` tồn tại.
3. Collection `orders` tồn tại trong `commerce`.
4. Tài khoản ứng dụng có quyền đọc/ghi phù hợp trên collection đích; tài khoản chạy SQL++ có quyền truy vấn theo chính sách cụ thể.
5. Chỉ mục cho những câu truy vấn SQL++ cần sử dụng đã được tạo trên đúng collection.

Người có quyền quản trị có thể tạo tài nguyên bằng giao diện Couchbase hoặc câu lệnh DDL tương ứng, ví dụ:

```sql
CREATE SCOPE `shop`.`commerce`;

CREATE COLLECTION `shop`.`commerce`.`orders`;
```

Chạy các lệnh tạo tài nguyên **một lần khi cần**, sau khi kiểm tra sự tồn tại và quyền; đây không phải câu lệnh để ứng dụng tự thực thi ở mỗi lần khởi động. Khả năng hỗ trợ DDL và quyền yêu cầu phụ thuộc phiên bản Couchbase Server.

Khi dùng scope riêng cho nhiều môi trường, cần tạo tài nguyên cho từng môi trường theo quy trình triển khai và quản lý thay đổi của nhóm.

## 9. Chẩn đoán lỗi chọn nhầm scope

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `findById(id)` trả về rỗng, nhưng thấy document cùng key trong Console. | Document nằm ở scope/collection khác đích mà Spring Data đang dùng. | So sánh đầy đủ `bucket.scope.collection` của cả hai phía. |
| Đổi `scope-name` sang `commerce` rồi xuất hiện lỗi collection không tồn tại. | Entity thiếu collection nghiệp vụ, hoặc collection chưa được tạo trong scope mới. | Kiểm tra mapping `@Collection`, sự tồn tại của scope và collection. |
| Đổi profile từ `dev` sang `prod` nhưng dữ liệu vẫn đọc ở scope cũ. | `@Scope` trên entity/repository hoặc cấu hình Java có độ ưu tiên cao hơn profile. | Xem lại thứ tự ưu tiên và giá trị cấu hình đang được nạp. |
| Truy vấn template hoạt động, nhưng câu `cluster.query(...)` tự viết thất bại. | Hai API không cùng query context hoặc keyspace. | Dùng keyspace đầy đủ, hoặc đặt query context của SDK. |
| KV `get` thành công nhưng truy vấn SQL++ báo lỗi về index hoặc quyền. | Chỉ mục hoặc quyền truy vấn ở collection đích chưa đầy đủ. | Kiểm tra index và quyền trên đúng keyspace. |
| Ghi mới thành công nhưng không nhìn thấy các document cũ. | Thay đổi đích lưu mà không di chuyển dữ liệu. | Kiểm kê dữ liệu cũ và lập kế hoạch migrate/đồng bộ. |

### Kiểm tra nhanh trên một ứng dụng đang chạy

1. Xác định profile Spring Boot thực tế và giá trị `bucket-name`, `scope-name` được nạp.
2. Xác định annotation `@Scope`, `@Collection` trên entity, repository và phương thức.
3. Kiểm tra xem thao tác template hoặc repository có ghi đè scope/collection hay không.
4. Ghi lại đích dự kiến, ví dụ `shop.commerce.orders`, rồi so với vị trí document quan sát được ở Couchbase.
5. Thử một thao tác KV có key đã biết và một câu SQL++ với keyspace đầy đủ; kiểm tra index, quyền và lỗi độc lập.

Không ghi mật khẩu, token hoặc nội dung nhạy cảm vào log khi chẩn đoán. Chỉ cần ghi tên bucket, scope, collection cùng thông tin lỗi được phép hiển thị.

## 10. Ví dụ quyết định thiết kế

**Bài toán:** Dịch vụ bán hàng sử dụng một bucket `shop`. Môi trường dev dùng scope `commerce_dev`, production dùng scope `commerce`. Cả hai môi trường đều có collection `orders` và `customers`.

**Thiết kế phù hợp:**

- Đặt `spring.data.couchbase.scope-name` theo profile.
- Đặt `@Collection("orders")` trên entity đơn hàng, `@Collection("customers")` trên entity khách hàng.
- Không cố định `@Scope("commerce")` trên những entity cần tuân theo profile.
- Tạo collection, index và quyền tương ứng trong từng môi trường.

Với thiết kế đó, cùng thao tác repository trên đơn hàng sẽ nhắm tới `shop.commerce_dev.orders` ở dev và `shop.commerce.orders` ở production, **miễn là không có override khác**.

Nếu sau này cần một repository phục vụ báo cáo trên scope `reporting`, hãy khai báo scope/collection riêng cho repository hoặc dùng thao tác template có chọn phạm vi rõ ràng. Không nên đổi scope nền của toàn ứng dụng chỉ để phục vụ một truy vấn đặc biệt.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Cấu hình `spring.data.couchbase.scope-name: commerce` có biến `commerce` thành scope `_default` của Couchbase Server không?

**Đáp án:** Không. `commerce` vẫn là scope tùy chỉnh; nó chỉ trở thành giá trị nền mà Spring Data sử dụng.

**Câu 2.** Cấu hình scope `commerce`, entity chỉ có `@Document` và không có collection. Có thể giả định dữ liệu nằm trong `commerce._default` không?

**Đáp án:** Không. Scope tự tạo không có collection `_default`; cần chọn collection nghiệp vụ hợp lệ hoặc chủ động sử dụng scope `_default` với collection tương ứng.

**Câu 3.** Profile dev đặt `scope-name: commerce_dev`, entity có `@Scope("commerce")` và `@Collection("orders")`. Repository mặc định đọc ở đâu?

**Đáp án:** `shop.commerce.orders` (với bucket `shop`), vì annotation scope trên entity ưu tiên hơn cấu hình nền, nếu không có override khác.

**Câu 4.** Đổi `scope-name` có di chuyển document cũ hoặc chuyển chỉ mục sang scope mới không?

**Đáp án:** Không. Phải triển khai di chuyển dữ liệu và tạo chỉ mục riêng nếu cần, đồng thời kiểm tra đường đọc/ghi và quyền truy cập.

**Câu 5.** Cấu hình `scope-name` có tự khiến lời gọi `cluster.query(...)` của SDK dùng scope đó không?

**Đáp án:** Không. Truy vấn SDK tự viết cần xác định keyspace hoặc query context theo cơ chế của SDK.

## Ghi nhớ

**Chọn scope mặc định trong cấu hình** là chọn phạm vi nền cho các thao tác Spring Data Couchbase. Cấu hình Spring Boot thường dùng `spring.data.couchbase.scope-name`; cấu hình Java có thể ghi đè `getScopeName()`. Luôn kết hợp scope tùy chỉnh với collection hợp lệ và hiểu thứ tự ưu tiên của annotation/API. Thay đổi scope có thể khiến cùng một key được đọc ở vị trí hoàn toàn khác, do đó cần kiểm tra cả dữ liệu, chỉ mục, quyền và cấu hình môi trường.

### Tài liệu tham khảo

- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): các cơ chế chọn scope/collection, cặp hợp lệ và thứ tự ưu tiên.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): các thuộc tính cấu hình Couchbase.
- [Spring Data Couchbase — AbstractCouchbaseConfiguration API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/config/AbstractCouchbaseConfiguration.html): hợp đồng của phương thức `getScopeName()`.

