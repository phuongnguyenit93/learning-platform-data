# Thời hạn mặc định của bucket hoặc collection và ảnh hưởng lên tài liệu

## 1. Tại sao đặt TTL trong ứng dụng chưa đủ?

Một service Spring Data Couchbase lưu document giỏ hàng với thời hạn 30 phút. Đoạn Java dùng `Duration.ofMinutes(30)` là đúng, nhưng document lại biến mất sau 10 phút. Một service khác dùng `@Document` không đặt TTL và mong dữ liệu sản phẩm tồn tại lâu dài, nhưng sau khi chuyển collection, sản phẩm lại hết hạn sau một ngày.

Cả hai tình huống có thể bắt nguồn từ **chính sách expiration phía Couchbase Server**, đặc biệt **maximum TTL** (`maxTTL`) ở bucket hoặc collection. Chính sách này có thể đặt thời hạn mặc định cho những thao tác không yêu cầu expiry riêng và giới hạn thời hạn mà client được yêu cầu.

Đây là bài **“Thời hạn mặc định của bucket hoặc collection và ảnh hưởng lên tài liệu”**, thuộc chương **Thời gian hết hạn**, module **SPRING_DATA_COUCHBASE**. Phạm vi module là xây dựng tầng truy cập Couchbase thông qua document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive để đáp ứng yêu cầu hiệu năng, nhất quán, vận hành.

Sau bài học, bạn có thể:

1. Giải thích khác biệt giữa expiry metadata trên document và chính sách `maxTTL` ở server.
2. Phân tích tác động của cấu hình bucket hoặc collection lên thao tác ghi có TTL, không TTL hoặc TTL vượt giới hạn.
3. Xác định điểm cần kiểm tra khi collection có chính sách riêng hoặc kế thừa từ bucket.
4. Hiểu vì sao `@Document(expiry = ...)`, `repository.save` và SDK options không thể bỏ qua chính sách server.
5. Kiểm thử expiry thực tế qua Couchbase Java SDK `withExpiry(true)`, phân biệt KV với SQL++/index.
6. Thiết kế phân tách collection theo retention, thay đổi chính sách an toàn và chẩn đoán lỗi dữ liệu hết hạn ngoài dự kiến.

Ví dụ hướng tới Spring Boot 3.x, Spring Data Couchbase 5.x và Couchbase Java SDK 3.x tương thích. **Chi tiết kế thừa, quy tắc riêng của maxTTL và khả năng cấu hình cấp collection phụ thuộc Couchbase Server version/edition**. Trong production luôn đối chiếu tài liệu và cấu hình của server hiện đang chạy trước khi dựa vào một quy tắc cụ thể.

## 2. Ba tầng tham gia quyết định thời hạn sống

Xét một document giỏ hàng:

~~~text
Cluster: commerce-cluster
Bucket: commerce
Scope: checkout
Collection: carts

Document key: cart::u-42

JSON:
  { "userId": "u-42", "itemCount": 2 }

Metadata:
  CAS: ...
  expiry: thời điểm hết hiệu lực
~~~

Có ba nơi có thể ảnh hưởng tới expiry:

1. **Ứng dụng:** annotation `@Document(expiry)` hoặc một operation SDK với `expiry(Duration)`/`expiry(Instant)`.
2. **Bucket:** cấu hình `maxTTL` hoặc chính sách expiration tương ứng trên server.
3. **Collection:** có thể có cấu hình expiry riêng và cơ chế kế thừa/ghi đè chính sách bucket theo server version.

~~~mermaid
flowchart TD
    A["Spring Data entity / Repository"] --> D["Yêu cầu mutation"]
    B["Couchbase Java SDK options"] --> D
    D --> E["Couchbase Server"]
    F["Bucket maxTTL policy"] --> E
    G["Collection maxTTL / inheritance"] --> E
    E --> H["Expiry metadata hiệu lực trên document"]
    H --> I["KV get / Query / lifecycle"]
~~~

**Không phải mọi thành phần đều có quyền quyết định cuối cùng.** Annotation là ý định từ Java. Metadata expiry thực tế do server áp dụng theo request và chính sách có hiệu lực của keyspace.

### 2.1. Phân biệt thuật ngữ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **TTL của document** | Thời lượng hoặc mốc hết hạn dành cho một document cụ thể |
| **Expiry metadata** | Thời điểm hết hiệu lực đã được server gắn cho document |
| **Maximum TTL (`maxTTL`)** | Chính sách ở keyspace có thể áp thời hạn mặc định và giới hạn độ dài TTL hiệu lực |
| **TTL tương đối** | Ví dụ 30 phút tính từ thời điểm áp expiry |
| **Expiry tuyệt đối** | Ví dụ hết hạn tại 00:00 UTC ngày 1/12 |
| **Không expiry ở cấp document** | Thông thường expiry 0, nhưng vẫn phải xét chính sách server |
| **Retention** | Yêu cầu nghiệp vụ hoặc pháp lý về thời gian lưu dữ liệu, thường rộng hơn TTL |

Từ “default TTL” đôi khi được dùng để mô tả tác động mặc định của `maxTTL`. **Không nên xem “default” và “maximum” là hai property độc lập chỉ vì tên gọi khác**. Cần tìm đúng cấu hình được server cung cấp cho phiên bản đang chạy.

## 3. `maxTTL` hoạt động như một chính sách phía server

Có thể hình dung:

- Khi document **mới** được ghi mà ứng dụng không chỉ định expiry, server có thể áp một thời hạn dựa trên `maxTTL` có hiệu lực.
- Khi ứng dụng yêu cầu TTL **ngắn hơn** giới hạn, expiry ngắn có thể được chấp nhận.
- Khi ứng dụng yêu cầu TTL **dài hơn** giới hạn, server có thể áp một thời hạn ngắn hơn theo policy.
- Khi ứng dụng yêu cầu expiry bằng **0**, không được suy ra nó chắc chắn tồn tại vĩnh viễn nếu keyspace đang có `maxTTL`.
- Với **document đã tồn tại** và các thao tác preserve/replace/touch, hiệu lực thực tế cần xét semantics của mutation và server version.

Bảng sau là **mô hình chẩn đoán**, không thay thế việc đọc contract của từng release:

| Yêu cầu client | Server policy | Kết quả kỳ vọng cần kiểm chứng |
| --- | --- | --- |
| Tạo cart, không truyền TTL | Collection có `maxTTL = 30 phút` | Server có thể gắn hạn khoảng 30 phút |
| Tạo cart, TTL 10 phút | `maxTTL = 30 phút` | TTL 10 phút thường phù hợp |
| Tạo cart, TTL 60 phút | `maxTTL = 30 phút` | Hạn có thể bị giới hạn khoảng 30 phút |
| Tạo product, không TTL | `maxTTL = 1 ngày` | Product có thể tự hết hạn sau khoảng 1 ngày |
| Tạo product, không TTL | Không có chính sách buộc expiry | Product thường không tự hết hạn |
| Cập nhật với `preserveExpiry` | Collection có `maxTTL` | Phải xác minh hạn cũ được bảo toàn thế nào |
| TOUCH 2 giờ | `maxTTL = 30 phút` | Hạn có thể bị giới hạn |
| Cập nhật với `expiry(Instant)` xa tương lai | Keyspace có `maxTTL` ngắn | Mốc tuyệt đối có thể không được giữ tới thời điểm yêu cầu |

Không dựa vào bảng để khẳng định **tất cả thao tác** luôn có cùng luật `min(requestTTL, maxTTL)`. Các trường hợp preservation, absolute expiry, collection override và bản server khác có thể cần diễn giải riêng.

### 3.1. `maxTTL = 0` không phải thuộc tính của entity

Ở mức policy bucket, giá trị `0` thường biểu thị không áp giới hạn maximum TTL mặc định. Nhưng nếu một collection có thiết lập riêng, hoặc server có quy tắc kế thừa, **chỉ xem số 0 ở bucket hoặc collection riêng lẻ chưa đủ** để suy ra effective policy.

Ngược lại, khi bucket/collection không buộc TTL, document vẫn có thể được cấp một expiry riêng bằng SDK. `maxTTL = 0` không phải lệnh vô hiệu hóa mọi TTL của ứng dụng.

## 4. Chính sách bucket và collection: phải xác định phạm vi hiệu lực

Một bucket chứa nhiều scope và collection:

~~~text
Bucket: commerce
├── Scope: catalog
│   ├── Collection: products
│   └── Collection: campaigns
└── Scope: checkout
    ├── Collection: carts
    ├── Collection: sessions
    └── Collection: otp_codes
~~~

Nếu bucket có một giới hạn thời gian ngắn, những document cần lưu dài hạn có thể bị tác động — trừ khi server version và cấu hình collection cho phép thiết lập policy hiệu lực khác.

**Câu hỏi phải trả lời trước khi triển khai:**

1. Bucket `commerce` có `maxTTL` hay không?
2. Collection `products` có giá trị riêng, giá trị kế thừa hay trạng thái “không buộc expiry”?
3. Với một collection **không chỉ định** policy, server hiểu nó là **kế thừa** hay **không áp hạn**?
4. Nếu bucket và collection đều có giá trị, policy nào có hiệu lực?
5. Các thao tác tạo và cập nhật document có áp cùng một policy không?
6. Đổi policy có tác động đến document đã tồn tại hay chỉ những mutation tiếp theo?

Không tự trả lời các câu hỏi này bằng cách nhìn một file Spring Boot; đây là **cấu hình của server và namespace**.

### 4.1. Ví dụ thiết kế phân tách collection

| Collection | Dữ liệu | Nhu cầu retention | Gợi ý policy |
| --- | --- | --- | --- |
| `commerce.catalog.products` | Sản phẩm | Lâu dài, xóa có chủ đích | Không buộc TTL ngắn |
| `commerce.catalog.campaigns` | Chương trình khuyến mãi | Mốc kết thúc riêng từng campaign | Cho phép expiry tuyệt đối phù hợp |
| `commerce.checkout.carts` | Giỏ hàng | TTL tương đối theo hoạt động | `maxTTL` phù hợp giới hạn cho cart |
| `commerce.checkout.sessions` | Phiên đăng nhập | Idle TTL và hard deadline | Policy tương thích cả hai giới hạn |
| `commerce.checkout.otp_codes` | Mã xác minh | Vài phút từ lúc phát hành | Giới hạn ngắn, không gia hạn khi đọc |

Đây là **gợi ý thiết kế**, không khẳng định mọi collection trên mọi cluster đều cho phép set policy độc lập. Đặc biệt, tránh đặt **product và OTP** chung collection có maxTTL 5 phút khi sản phẩm cần tồn tại lâu dài.

## 5. Cách quản trị và kiểm tra `maxTTL`

Chính sách server nên được quản trị tập trung qua công cụ Couchbase Server phù hợp với quyền truy cập của đội vận hành. Tùy version/edition, có thể xem hoặc đặt TTL ở:

- Giao diện quản trị bucket.
- Giao diện quản lý scope/collection.
- CLI/REST Management API được server hỗ trợ.
- Cơ sở hạ tầng định nghĩa bằng mã (*Infrastructure as Code*) của tổ chức.

**Không có một property Spring Boot chung tự biến `spring.data.couchbase.bucket-name` thành thao tác tạo bucket hoặc cấu hình maxTTL.**

### 5.1. Checklist kiểm kê trước khi sửa

~~~text
Environment:   staging / production
Cluster:       tên cluster thực tế
Server version: [x.y.z]
Bucket:        commerce
Scope:         checkout
Collection:    carts

Bucket maxTTL:          giá trị thực đang đọc từ server
Collection maxTTL:      giá trị hoặc trạng thái kế thừa thực tế
Effective policy:       kết luận theo hợp đồng của server version
Expected document TTL:  30 phút
Observed document TTL:  đo từ expiry metadata
~~~

Nên lưu những thông tin trên trong runbook và cấu hình quản trị; không sao chép giá trị vào nhiều file ứng dụng khác nhau rồi kỳ vọng luôn đồng bộ.

### 5.2. Thay cấu hình có rủi ro dữ liệu

Tăng hoặc giảm maxTTL trên keyspace đang có traffic có thể ảnh hưởng lớn đến hành vi ghi tiếp theo. Với yêu cầu lưu trữ quan trọng:

1. Xem danh sách entity của keyspace và retention policy tương ứng.
2. Kiểm tra hiện trạng trước khi đổi.
3. Thử thay đổi trên môi trường staging có server version giống production.
4. Kiểm chứng insert, replace, preserve expiry, touch và query.
5. Lập kế hoạch rollback và theo dõi document-not-found.
6. Xác định tác động tới **document cũ**; không tự suy là mọi metadata đã được ghi lại.

Không thay maxTTL production chỉ để chạy thử TTL với một document.

## 6. Ví dụ Spring Boot: property kết nối không phải policy server

Một ứng dụng Spring Data Couchbase thường dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

Ví dụ cấu hình `application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: "couchbases://cb.example.internal"
    username: "application-user"
    password: "inject-from-secret-in-real-deployments"
  data:
    couchbase:
      bucket-name: commerce
~~~

Cấu hình trên minh họa **kết nối và chọn bucket mặc định**. Nó **không mô tả maxTTL của server**. Khi triển khai thật, thay chuỗi bí mật minh họa bằng secret injection, thiết lập TLS/trust theo cluster và cấp RBAC tối thiểu.

Nếu ứng dụng tự định nghĩa property:

~~~yaml
app:
  expiration:
    cart: 30m
    otp: 5m
~~~

thì hai khóa `app.expiration.*` chỉ có tác dụng khi code đọc và dùng chúng trong mutation. Không có cơ chế mặc định tự động truyền `cart = 30m` sang maxTTL server.

## 7. `@Document(expiry)` trong entity Spring Data

Ví dụ một session sống 15 phút theo mapping tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(expiry = 900)  // 900 giây trong các release hỗ trợ.
@Scope("checkout")
@Collection("sessions")
public class SessionDocument {

    @Id
    private String id;

    private String userId;

    protected SessionDocument() {
    }

    public SessionDocument(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface SessionRepository
        extends CouchbaseRepository<SessionDocument, String> {
}
~~~

Khi `repository.save(session)` sử dụng Spring Data mapper và annotation expiry theo version, thao tác ghi có thể áp TTL 900 giây. **Nếu server maxTTL thấp hơn**, document có thể hết hạn sớm hơn dự kiến. Ngoài ra, mỗi lần save/update có thể thay expiry theo semantics của mapper — cần kiểm chứng trước/sau bằng SDK.

### 7.1. Annotation không sửa policy bucket

`@Document(expiry = 900)` được áp cho **entity** qua mapping, không tạo collection, không set maxTTL bucket và không đảm bảo retention vượt chính sách server. Nếu `@Scope`/`@Collection` trỏ sang keyspace khác, document sẽ chịu **effective policy của keyspace mới**.

### 7.2. Dữ liệu không có TTL tĩnh

Một entity sản phẩm:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class ProductDocument {

    @Id
    private String id;

    private String sku;

    private String name;

    protected ProductDocument() {
    }

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

Việc không đặt expiry trên annotation là một ý định **không gán TTL tĩnh ở cấp mapper**. Nó không ngăn `maxTTL` phía server và không có nghĩa document không bao giờ bị xóa.

## 8. SDK `insert`: document mới không chỉ chịu expiry từ Java

Couchbase Java SDK 3.x có thể đặt TTL tương đối khi tạo document:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

otpCodes.insert(
        "otp::u-42",
        JsonObject.create().put("hash", "hash-placeholder"),
        InsertOptions.insertOptions()
                .expiry(Duration.ofMinutes(5))
);
~~~

Yêu cầu là “TTL 5 phút kể từ khi insert”. Nhưng nếu collection `otp_codes` bị giới hạn tối đa 2 phút, **expiry hiệu lực có thể là 2 phút**. Lệnh insert thành công không đồng nghĩa deadline nghiệp vụ được giữ đủ 5 phút.

### 8.1. Insert không có expiry explicit

~~~java
import com.couchbase.client.java.json.JsonObject;

products.insert(
        "product::SKU-001",
        JsonObject.create()
                .put("sku", "SKU-001")
                .put("name", "Keyboard")
);
~~~

Nếu keyspace `products` có maxTTL buộc 24 giờ, server có thể áp expiry mặc dù operation không chỉ định TTL. Đây là lý do cần kiểm tra policy khi một loại document được thiết kế lưu lâu dài.

**Không tự chữa bằng việc gửi `expiry(Duration.ZERO)` rồi coi document bất tử**: behavior giá trị 0 phải được xem cùng maxTTL và SDK/server version.

## 9. SDK `upsert`: cập nhật có thể làm thay đổi expiry

Ví dụ lưu giỏ hàng:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

carts.upsert(
        "cart::u-42",
        JsonObject.create()
                .put("userId", "u-42")
                .put("itemCount", 3),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Khi upsert lại lúc 10:20 với relative TTL 30 phút, deadline có thể được tính lại từ mutation sau. Nhưng nếu collection có maxTTL 10 phút, deadline hiệu lực có thể ngắn hơn. Nếu chính sách nghiệp vụ là “30 phút từ lần sửa giỏ”, cấu hình server 10 phút sẽ gây mâu thuẫn.

**Phân biệt:** `upsert` có thể tạo mới nếu key chưa có. Với session/OTP không được phép hồi sinh khi hết hạn, dùng thao tác có điều kiện và chính sách tạo mới riêng.

### 9.1. Upsert không gửi expiry

~~~java
carts.upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 4)
);
~~~

Không thể kết luận lần ghi này chắc chắn **bảo toàn hạn cũ**. Với một số mutation, không truyền expiry có thể reset về giá trị mặc định hoặc bị policy server can thiệp. Đừng trộn upsert với/không có options trong cùng service mà không có test.

Nếu cần giữ hạn khi sửa content, dùng một API preserve expiry được hỗ trợ thay vì dựa vào giá trị mặc định tình cờ.

## 10. Replace với `preserveExpiry(true)`

Một document OTP được tạo lúc 10:00, deadline 10:05. Lúc 10:03, ứng dụng muốn tăng bộ đếm thất bại mà không làm mã sống thêm.

~~~java
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.kv.ReplaceOptions;

GetResult current = otpCodes.get("otp::u-42");
var updated = current.contentAsObject();

Integer attempts = updated.getInt("failedAttempts");
updated.put(
        "failedAttempts",
        (attempts == null ? 0 : attempts) + 1
);

otpCodes.replace(
        "otp::u-42",
        updated,
        ReplaceOptions.replaceOptions()
                .cas(current.cas())
                .preserveExpiry(true)
);
~~~

`preserveExpiry(true)` thể hiện ý định giữ deadline cũ, còn `cas(...)` kiểm tra phiên bản để tránh mất cập nhật. Hai thứ này **giải quyết hai bài toán riêng**.

**Cần kiểm chứng trên server có maxTTL:** preservation có thể có quy tắc riêng, không nhất thiết giống tạo mới với TTL yêu cầu. Nếu policy server thay đổi trong lúc document còn sống, đừng tự suy mốc cũ sẽ được kéo dài hay bị cắt trong mọi API/version.

### 10.1. Tại sao không thay bằng touch?

`touch(id, Duration.ofMinutes(5))` tại 10:03 sẽ chủ động đặt hạn tương đối mới khoảng 10:08 nếu policy cho phép. Nó **không** giữ deadline 10:05. Đối với OTP, đó là một lỗi nghiệp vụ.

### 10.2. CAS không giữ document sống lâu hơn

CAS giúp phát hiện concurrent writer. Nếu document hết hạn giữa `get` và `replace`, thao tác có thể báo không tìm thấy. Không tự dùng `upsert` để tái tạo cùng OTP sau khi đã hết hạn.

## 11. Touch và get-and-touch khi có maxTTL

Couchbase SDK hỗ trợ làm mới expiry mà không thay content:

~~~java
import java.time.Duration;

carts.touch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

Hoặc đọc kết hợp gia hạn:

~~~java
var result = carts.getAndTouch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

Một lời gọi TOUCH là **mutation của expiry metadata**. Nó có thể khiến mốc hết hạn mới được tính theo thời gian hiện tại, rồi chịu chính sách server. Nếu maxTTL collection ngắn hơn TTL yêu cầu, hạn thực có thể ngắn hơn 30 phút.

`getAndTouch` **không phải GET thuần**. Nếu một endpoint chỉ xem giỏ hàng mà gọi get-and-touch, nó có thể vô tình gia hạn. Với session có hard deadline, cứ làm mới TTL không điều kiện có thể vi phạm giới hạn bảo mật.

### 11.1. MaxTTL không phải hard deadline tính từ lúc document được phát hành

Nếu session phải có absolute lifetime 8 giờ kể từ `issuedAt`, đừng tự xem maxTTL 8 giờ là tương đương. Trong các mô hình áp expiry ở mỗi mutation, hạn server có thể được tính lại; hãy lưu/kiểm tra **deadline nghiệp vụ cố định** độc lập với TTL sliding.

## 12. Expiry tuyệt đối cũng phải chịu policy server

Một chiến dịch phải hết hạn lúc 00:00 UTC ngày 1 tháng 12 năm 2026:

~~~java
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Instant fixedDeadline =
        Instant.parse("2026-12-01T00:00:00Z");

campaigns.upsert(
        "campaign::WINTER",
        JsonObject.create().put("name", "Winter"),
        UpsertOptions.upsertOptions()
                .expiry(fixedDeadline)
);
~~~

Dùng `Instant` giúp giữ cùng deadline khi retry hoặc khi cập nhật có chủ đích. Nhưng nếu collection `campaigns` chỉ cho maxTTL một ngày và deadline còn một tuần, **server policy có thể khiến document hết hạn trước sự kiện**.

Vì vậy đặt `Instant` cố định là điều kiện cần để tránh drift do retry, nhưng **không vượt qua maxTTL**.

### 12.1. Múi giờ địa phương

Một chiến dịch kết thúc lúc 00:00 ngày 1/12 tại Việt Nam khác 00:00 UTC:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Instant endExclusive = LocalDate.of(2026, 12, 1)
        .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

Kết quả là `2026-11-30T17:00:00Z`. Nếu cần expiry theo lịch địa phương, hãy chuyển bằng `ZoneId` trước khi gửi SDK. TTL của server không tự hiểu lịch khuyến mãi của ứng dụng.

## 13. Quy tắc 30 ngày khi dùng expiry số nguyên thô

Một số đường API Couchbase cấp thấp/legacy diễn giải expiration dạng **số nguyên giây** với ranh giới thường nhắc tới là 30 ngày:

- Khoảng thời gian nhỏ được xem như TTL tương đối.
- Giá trị số lớn có thể được xem như Unix timestamp tuyệt đối.
- Giá trị 0 có ngữ nghĩa riêng và có thể chịu maxTTL.

Nếu tự chuyển `45 ngày` thành giây rồi truyền vào API raw không đúng contract, server có thể hiểu nó như timestamp ở quá khứ.

**Cách an toàn hơn:** với Couchbase Java SDK 3.x, dùng overload phân biệt `Duration` và `Instant` ở operation hỗ trợ, thay vì tự nhét một số nguyên có ý nghĩa mơ hồ.

Cảnh báo 30 ngày là vấn đề **ngữ nghĩa expiry request**, khác với giới hạn `maxTTL` của server. Cả hai có thể cùng ảnh hưởng kết quả, nhưng không phải cùng một quy tắc.

## 14. Spring Data repository, CouchbaseTemplate và SDK không tự đồng bộ policy

Một service có thể:

1. Tạo document bằng `CouchbaseRepository.save(entity)`.
2. Sửa nhanh một field bằng SDK `Collection.replace(...)`.
3. Truy vấn bằng `CouchbaseTemplate` hoặc SQL++.

Ba đường truy cập không tự bảo đảm cùng semantics expiry.

| Đường thao tác | Nguồn expiry cần kiểm tra |
| --- | --- |
| Repository save | Mapping `@Document(expiry)`/expiry động, behavior update, server maxTTL |
| `CouchbaseTemplate` entity operation | Mapping, options cụ thể, server maxTTL |
| SDK `insert/upsert` | Operation expiry options, server maxTTL |
| SDK `replace` | Set expiry hoặc preserve expiry, CAS, server maxTTL |
| SDK `touch/getAndTouch` | TTL mới từ thao tác, server maxTTL |
| SQL++ UPDATE/UPSERT | Semantics statement/version, không tự đọc annotation Java |
| SDK GET | Không đặt expiry mới theo mặc định |

**Tình huống:** repository tạo session với TTL 15 phút nhưng một lệnh SDK upsert không truyền expiry sửa JSON rồi khiến hạn thay đổi. Dù annotation vẫn tồn tại, đường SDK **không tự đọc annotation**. Cần thống nhất policy trong service và regression test khi refactor.

### 14.1. Mapper không provisioning bucket/collection

`@Scope` và `@Collection` trỏ tới keyspace đã có. Chúng không tự thay maxTTL của collection.

Nếu đổi entity từ `checkout.sessions` sang `checkout.records`, một annotation expiry không thay đổi nhưng **retention thực tế có thể đổi** vì server policy ở collection mới khác.

## 15. SQL++ index và dữ liệu đã hết hạn

Một query SQL++ có thể dùng index trên field JSON:

~~~sql
SELECT p.sku, p.name
FROM `commerce`.`catalog`.`products` AS p
WHERE p.sku = "SKU-001";
~~~

Việc document không được trả về qua Query service có thể do:

- Document đã hết hạn logic.
- Truy vấn trỏ nhầm bucket/scope/collection.
- Query service hoặc secondary index có vấn đề.
- Scan consistency khiến kết quả chưa phản ánh một mutation rất gần.

**Không lấy một kết quả SQL++ rỗng làm bằng chứng duy nhất rằng TTL đã hết**. Với document key đã biết, hãy kiểm tra bằng KV GET trước, rồi tiếp tục chẩn đoán index/query riêng.

Index không đặt TTL. Tương tự, một field JSON tên `expiresAt` có thể được index để tìm dữ liệu gần deadline nhưng **không tự trở thành metadata expiry**.

## 16. CAS và `@Version`: không thay thế giới hạn server

CAS là token phiên bản để phát hiện việc document bị thay đổi bởi một writer khác. Spring Data `@Version` hỗ trợ optimistic locking ở đường mapper phù hợp.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant CB as Couchbase
    A->>CB: GET cart => CAS c1
    B->>CB: GET cart => CAS c1
    B->>CB: REPLACE CAS c1 + expiry 30m
    CB-->>B: Success; CAS c2
    A->>CB: REPLACE CAS c1 + preserve expiry
    CB-->>A: CAS mismatch
~~~

- CAS kiểm soát **concurrent update**.
- Expiry kiểm soát **document lifetime**.
- maxTTL là **ràng buộc server** đối với expiration theo policy.
- Timeout là **giới hạn thời gian chờ thao tác**, không phải TTL.

Khi document hết hạn giữa GET và REPLACE, phải xử lý document-not-found; không tự fallback sang UPSERT để hồi sinh một session/OTP đã hết hạn.

## 17. Giao dịch và timeout là những cơ chế khác

Một transaction có thời hạn thực thi, cơ chế commit/rollback và điều kiện nhìn thấy dữ liệu riêng. `maxTTL` hay document expiry không phải transaction scheduler.

Ví dụ hệ thống đặt hàng giữ một reservation đến deadline:

1. Document reservation có expiry phù hợp.
2. Business logic kiểm tra `expiresAt`/trạng thái khi xử lý xác nhận.
3. CAS/transaction được dùng để bảo vệ tính nhất quán khi có cạnh tranh.
4. Server maxTTL phải cho phép thời gian reservation dự kiến.
5. Deadline giao dịch và timeout KV/Query phải được cấu hình độc lập.

Không coi “document sẽ tự hết hạn” là bằng chứng có một lock phân tán an toàn với fencing. Các nghiệp vụ giá trị cao cần kiểm tra trạng thái trước khi xác nhận, không chỉ dựa vào việc key còn đọc được.

## 18. Reactive API vẫn chịu cùng chính sách server

Couchbase Java SDK reactive truyền operation options tương tự:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import reactor.core.publisher.Mono;

Mono<?> operation = carts.reactive().upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 2),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Cần nhớ:

- Chỉ tạo `Mono` chưa có nghĩa mutation đã chạy; cần subscription.
- Server maxTTL không thay đổi chỉ vì ứng dụng dùng reactive thay blocking.
- Retry/resubscription có thể áp một TTL tương đối mới, làm deadline trôi.
- `Mono.timeout(Duration.ofSeconds(2))` là timeout của pipeline, **không phải TTL document**.
- Cancellation không bảo đảm mutation đã gửi bị rollback.

Với mã OTP có deadline cố định, tính `Instant` một lần cho nghiệp vụ và tái sử dụng nếu retry hợp lệ; không phát hành TTL mới từ mỗi lần retry.

## 19. Quan sát expiry metadata thực tế

Đây là cách quan trọng nhất để chứng minh server đã áp policy nào.

Với Java SDK 3.x hỗ trợ trả expiry trên GET:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = carts.get(
        "cart::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(expiry ->
        System.out.println("Effective expiry: " + expiry)
);
~~~

`withExpiry(true)` yêu cầu metadata; `expiryTime()` là giá trị tùy chọn theo API SDK đang dùng. Khi không có giá trị, phải đọc Javadoc/semantics version đó thay vì tự gán deadline.

### 19.1. Kiểm chứng bằng hai mốc thời gian

Giả sử:

~~~text
Trước mutation:     10:00:00 UTC
Client expiry:      Duration 30m
Server maxTTL:      10m
Metadata sau ghi:   khoảng 10:10 UTC
~~~

Kết quả này sẽ cho thấy TTL hiệu lực khác yêu cầu. Tuy nhiên để kết luận **vì maxTTL**, cần kiểm tra policy server trên **đúng collection**, vì một sai khác cũng có thể do API, keyspace hoặc mutation update.

### 19.2. Cảnh báo về thời gian và độ phân giải

Không so sánh expiry với một timestamp client ở chính xác từng mili giây. Cần tính tới:

- Thời gian round trip và thời điểm server xử lý mutation.
- Độ phân giải expiry metadata/API.
- Đồng bộ đồng hồ giữa client/server.
- Thao tác khác có thể đổi expiry giữa hai lần đo.

Integration test nên dùng khoảng dung sai và key riêng. Đừng lấy “disk usage chưa giảm” làm bằng chứng maxTTL không hoạt động; expiry logic và thu hồi vật lý không phải một sự kiện duy nhất.

## 20. Unit test cho chính sách thời hạn nghiệp vụ

Một phần logic về TTL có thể kiểm tra **không cần Couchbase Server**. Ví dụ tính deadline cố định cho session với idle TTL và absolute lifetime:

~~~java
import java.time.Duration;
import java.time.Instant;

public final class SessionDeadlinePolicy {

    public static Instant effectiveDeadline(
            Instant issuedAt,
            Instant now,
            Duration idle,
            Duration absoluteLifetime) {

        Instant idleUntil = now.plus(idle);
        Instant hardUntil = issuedAt.plus(absoluteLifetime);

        return idleUntil.isBefore(hardUntil)
                ? idleUntil
                : hardUntil;
    }
}
~~~

Unit test:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class SessionDeadlinePolicyTest {

    @Test
    void doesNotExtendPastHardDeadline() {
        Instant issuedAt = Instant.parse("2026-12-01T09:00:00Z");
        Instant now = Instant.parse("2026-12-01T16:50:00Z");

        Instant deadline = SessionDeadlinePolicy.effectiveDeadline(
                issuedAt,
                now,
                Duration.ofMinutes(20),
                Duration.ofHours(8)
        );

        assertThat(deadline)
                .isEqualTo(Instant.parse("2026-12-01T17:00:00Z"));
    }
}
~~~

Test này chứng minh **phép tính nghiệp vụ**, không chứng minh server maxTTL. Một session có hard deadline đúng trên code vẫn có thể hết sớm do maxTTL. Vì vậy cần integration test đọc metadata.

## 21. Integration test: lập ma trận request và policy server

Trước khi test, cần một cluster/collection **dành riêng cho kiểm thử** với maxTTL đã biết. Không thay đổi bucket production.

Bộ kịch bản:

| Test | Document/mutation | Policy server | Assertion cần có |
| --- | --- | --- | --- |
| A | INSERT không expiry explicit | Không giới hạn bắt buộc | Document không có expiry mặc định nếu hợp đồng server như vậy |
| B | INSERT không expiry explicit | maxTTL 10s | Expiry gần 10s từ lúc ghi |
| C | INSERT TTL 5s | maxTTL 10s | Expiry theo khoảng 5s |
| D | INSERT TTL 30s | maxTTL 10s | Expiry không vượt policy |
| E | UPSERT lại với TTL 30s | maxTTL 10s | Kiểm tra hạn sau mutation mới |
| F | REPLACE preserve expiry | maxTTL 10s | Kiểm chứng hạn giữ/đổi theo server contract |
| G | TOUCH TTL 30s | maxTTL 10s | Kiểm tra hạn sau touch |
| H | `@Document(expiry = 30)` qua repository | maxTTL 10s | Metadata server phản ánh hiệu lực |
| I | No-TTL entity trên collection khác | Không ép TTL | Document còn hợp lệ sau thời lượng test |
| J | `expiry(Instant)` ở tương lai | maxTTL 10s | Kiểm tra ràng buộc server |

### 21.1. Ghi dữ liệu bằng SDK

~~~java
import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String key = "max-ttl-it::" + UUID.randomUUID();

testCollection.upsert(
        key,
        JsonObject.create().put("kind", "ttl-test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(30))
);
~~~

Sau đó đọc metadata bằng `GetOptions.getOptions().withExpiry(true)` và so sánh với time window được chấp nhận. Một test tốt phải dùng unique key, cleanup nếu lỗi và không dựa trên dữ liệu người dùng thật.

### 21.2. Kiểm tra khi document đã hết hạn

Có thể poll KV GET với deadline hữu hạn cho tới khi document không còn hợp lệ, thay vì `Thread.sleep(10000)` rồi assert chính xác ở một mili giây. Kiểm tra theo deadline logic, không đo dung lượng đĩa làm tiêu chí chính.

### 21.3. Test thay đổi policy

Nếu mục tiêu là xác minh tác động của **đổi maxTTL**, tạo document trước, thay policy ở môi trường test, rồi quan sát lại:

- Document trước thay đổi có giữ expiry metadata cũ?
- Mutation sau thay đổi áp policy mới ra sao?
- Preserve expiry tương tác thế nào?
- Query/index có đồng nhất với KV không?
- Có race với worker đang ghi dữ liệu không?

Test này có thể cần quyền quản trị cluster; không nên chạy tự động trên một môi trường dùng chung không kiểm soát.

## 22. Thay đổi maxTTL có tự rút hạn document cũ không?

Không nên suy luận rằng đổi một thông số quản trị sẽ **ngay lập tức tính lại expiry metadata cho toàn bộ document đã có**. Một document có expiry được ghi trước đó là trạng thái đã lưu; việc server áp policy mới cho document cũ hay cho mutation kế tiếp phụ thuộc version/operation.

Muốn chuyển từ retention 30 ngày xuống 7 ngày một cách chắc chắn, cần kế hoạch dữ liệu:

1. Xác định collection nào chịu policy mới.
2. Quy định document cũ phải giữ hạn cũ hay rút ngắn.
3. Chọn migration/batch hoặc cơ chế quản trị được server hỗ trợ.
4. Tránh cập nhật hàng loạt làm sai JSON content/CAS.
5. Ghi nhận tiến độ, retry/idempotency và tiêu chí dừng.
6. Quan sát document-not-found và expiry metrics sau triển khai.

**Không xem “thay maxTTL” tương đương một lệnh mass delete đã hoàn tất.**

### 22.1. Thay đổi khi đang có traffic

Nếu hàng nghìn service instances đang ghi trên keyspace, một số mutation có thể áp policy cũ và một số mutation áp policy mới theo thời điểm rollout. Cần có giai đoạn kiểm thử và giám sát thay vì kỳ vọng mọi document đồng loạt có cùng deadline.

## 23. TTL và yêu cầu xóa dữ liệu vật lý

Expired document được coi là không còn hợp lệ cho truy cập thông thường, nhưng không nhất thiết được xóa vật lý khỏi mọi replica, backup, snapshot hoặc log đúng tại thời điểm đó.

Nếu tổ chức có yêu cầu “xóa dữ liệu cá nhân sau 30 ngày”:

- Xác định định nghĩa “xóa” của chính sách.
- Đánh giá expiry, dọn dẹp server, bản sao lưu và retention của backup.
- Phân biệt cache hết hạn với bản ghi nghiệp vụ cần lưu lâu.
- Kiểm tra dữ liệu liên quan trong các hệ thống downstream khác.
- Thiết kế audit/giám sát phù hợp mà không lưu thêm nội dung nhạy cảm.

**maxTTL là một công cụ của quản lý vòng đời dữ liệu, không phải bằng chứng hoàn chỉnh về xóa vật lý hoặc tuân thủ pháp lý.**

## 24. Hiệu năng và vận hành khi đặt maxTTL

Thời hạn mặc định có thể giảm số document sống lâu không cần thiết, nhưng nếu thiết lập sai cũng gây:

- Tăng tỷ lệ cache miss hoặc document-not-found.
- Lặp tạo lại cart/session gây tải ghi.
- Dữ liệu nghiệp vụ biến mất trước khi được xử lý.
- Nhiều request retry do không tìm thấy key.
- Sai lệch giữa UI và backend khi một document hết hạn sớm.
- Khó chẩn đoán khi repository và SDK gửi các expiry khác nhau.

Nên theo dõi:

| Tín hiệu | Mục tiêu |
| --- | --- |
| Document-not-found theo collection | Phát hiện dữ liệu hết hạn bất thường |
| KV read/write latency p95/p99 | Theo dõi tác động tới Data service |
| Mutation timeout/ambiguous timeout | Không nhầm timeout với expiry |
| Query latency, index health | Phân biệt lỗi query khỏi TTL |
| Tần suất TOUCH/GET-AND-TOUCH | Tránh gia hạn vô ý |
| Số lượng document và expiry/purge metrics phù hợp | Kiểm tra vòng đời và tài nguyên |
| CAS conflict | Phát hiện cập nhật cạnh tranh |
| So sánh expiry metadata với policy kỳ vọng | Xác minh ràng buộc server và code |

Không log mật khẩu, access token, OTP thô hoặc JSON chứa dữ liệu nhạy cảm khi chẩn đoán TTL.

## 25. Bảng chẩn đoán lỗi thường gặp

| Triệu chứng | Nguồn cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Product hết hạn dù `@Document` không đặt TTL | Collection/bucket maxTTL | Xem effective policy, tách collection nếu cần |
| Cart TTL 30m nhưng mất sau 10m | maxTTL server ngắn hơn | Điều chỉnh chính sách có kiểm soát |
| OTP 5m bị hết sau 2m | Policy maxTTL 2m | Cân đối security/functional requirements |
| `expiry = 0` nhưng document vẫn mất | Có maxTTL hoặc thao tác xóa khác | Kiểm tra server policy và audit |
| Sau đổi collection, TTL thay đổi | Collection mới có effective maxTTL khác | Kiểm tra mapping/keyspace |
| Repository đúng, SDK sai | SDK không đọc `@Document` | Đặt expiry options rõ ràng |
| UPSERT làm mất TTL cũ | Không preserve hoặc reset mặc định | Test behavior và dùng preserve thích hợp |
| TOUCH làm TTL khác dự kiến | maxTTL hoặc relative renewal | Xem metadata sau touch |
| Document đã expired nhưng disk usage chưa giảm | Thu hồi vật lý theo chu trình riêng | Dùng metrics và kiểm tra KV |
| SQL++ không thấy document | Query/index/keyspace/expiry | Kiểm tra KV theo key trước |
| Thay maxTTL nhưng dữ liệu cũ còn | Không có migration hoặc behavior áp policy khác | Xác minh version và thiết kế migration |
| Retry sau timeout làm gia hạn | Đặt lại relative TTL | Dùng fixed deadline khi cần |
| CAS mismatch | Writer khác cập nhật | Đọc lại, retry hữu hạn |
| Reactive save không có tác dụng | Publisher chưa subscribe hoặc signal lỗi | Kiểm tra subscription |

### 25.1. Cây quyết định

~~~mermaid
flowchart TD
    A["Document hết hạn ngoài dự kiến"] --> B{"Đúng bucket/scope/collection?"}
    B -- "Không" --> C["Sửa keyspace / mapping"]
    B -- "Có" --> D["Đọc effective maxTTL policy"]
    D --> E{"Mutation thực tế có expiry?"}
    E -- "Có" --> F["Kiểm tra Duration / Instant / preserve"]
    E -- "Không" --> G["Kiểm tra default và update semantics"]
    F --> H["Đọc expiry metadata"]
    G --> H
    H --> I{"KV theo key có tồn tại?"}
    I -- "Không" --> J["Kiểm tra deadline / delete / race"]
    I -- "Có" --> K["Nếu SQL++ khác, kiểm tra Query/index"]
~~~

## 26. Tình huống thực hành: thiết kế policy cho cửa hàng

Bạn xây dựng `commerce-service` có:

~~~text
Bucket: commerce
Scope catalog:
  Collection products
  Collection campaigns
Scope checkout:
  Collection carts
  Collection otp_codes
  Collection orders
~~~

Yêu cầu nghiệp vụ:

- Product phải tồn tại cho đến khi bị xóa có chủ đích.
- Cart sống 30 phút từ lần sửa cuối.
- OTP sống đúng 5 phút từ lúc phát hành và không gia hạn khi đọc.
- Campaign hết hạn vào ngày giờ được công bố.
- Order phải lưu theo chính sách retention riêng, không áp TTL của session.
- Hiện tại bucket có maxTTL 24 giờ, còn collection carts có một maxTTL khác.
- Một số thao tác dùng `CouchbaseRepository`, số khác dùng SDK hoặc reactive.

**Câu hỏi:**

1. Vì sao maxTTL 24 giờ ở bucket có thể là vấn đề với product/order?
2. Cần kiểm tra thông tin gì để biết `products` và `orders` thực sự có kế thừa policy bucket không?
3. Nếu cart SDK yêu cầu TTL 30m nhưng expiry metadata gần 10m, phải kiểm tra gì trước?
4. `@Document(expiry = 300)` có tự tạo maxTTL 5 phút phía server không?
5. Khi OTP được cập nhật số lần thử, vì sao không dùng TOUCH 5 phút?
6. Vì sao GET không trả document không chứng minh dữ liệu đã bị xóa vật lý?
7. Tại sao chuyển repository sang SDK có thể làm expiry thay đổi dù entity annotation giữ nguyên?
8. Một lần `maxTTL` đổi từ 24 giờ xuống 12 giờ có bảo đảm mọi document cũ lập tức đổi hạn không?
9. CAS có thể giúp bảo vệ vấn đề gì, và không giải quyết gì về maxTTL?
10. Thiết kế ít nhất 4 integration tests để chứng minh policy ở collection mới.

**Hướng giải:**

- Phân tách collection theo nhu cầu retention.
- Đọc policy bucket/collection và luật kế thừa của server version thực.
- So sánh TTL yêu cầu với metadata expiry quan sát được.
- Giữ deadline cố định cho OTP/campaign, không gia hạn do retry.
- Kiểm thử create/update/preserve/touch theo đúng đường API.
- Có kế hoạch migration và giám sát document cũ nếu thay maxTTL.

## 27. Checklist production

- [ ] Đã kiểm kê chính sách expiration của mọi bucket/collection liên quan.
- [ ] Biết server version và quy tắc kế thừa/ưu tiên maxTTL.
- [ ] Phân biệt maxTTL server với TTL trên `@Document`/SDK options.
- [ ] Document lâu dài không vô tình nằm trong keyspace có giới hạn ngắn.
- [ ] Từng entity có retention policy được ghi rõ.
- [ ] Đã kiểm tra create và update trong cả repository, template, SDK.
- [ ] Không xem `expiry = 0` là cam kết tồn tại vĩnh viễn.
- [ ] Có chính sách dùng `preserveExpiry` và TOUCH hợp lý.
- [ ] Fixed deadline không bị kéo dài bởi retry/refresh.
- [ ] Có kiểm thử cả `Duration` và `Instant`, đúng đơn vị.
- [ ] Đã đối chiếu expiry metadata thực sau mutation.
- [ ] Khi có chuyển collection, đã kiểm tra policy keyspace mới.
- [ ] Có test maxTTL trong môi trường độc lập, không đổi production để thử.
- [ ] Có kế hoạch khi thay maxTTL và xem xét document cũ.
- [ ] Không nhầm KV/Query timeout, CAS và transaction deadline với document TTL.
- [ ] Theo dõi document-not-found và các chỉ số server phù hợp.
- [ ] Không dùng TTL làm bằng chứng đã xóa vật lý mọi bản sao/backup.

## 28. Tổng kết

**Thời hạn mặc định của bucket hoặc collection không phải giá trị do Spring Boot tự quyết định.** Trong Couchbase, chính sách `maxTTL` phía server có thể áp expiry cho document không yêu cầu TTL riêng và giới hạn thời hạn mà SDK/Spring Data yêu cầu. Đồng thời, hiệu lực của bucket/collection policy, thao tác preserve và thay đổi cấu hình cần đối chiếu với **server version thực tế**.

`@Document(expiry = ...)` mô tả TTL ở metadata entity; SDK `expiry(Duration/Instant)` đặt yêu cầu từ mutation; `touch` đổi expiry; `preserveExpiry` yêu cầu giữ hạn. Không cơ chế nào tự thay thế việc kiểm tra policy của keyspace và đọc **expiry metadata cuối cùng** trên server.

Thiết kế bucket/scope/collection theo retention rõ ràng, kiểm thử chính xác cả create/update và quản trị thay đổi `maxTTL` có kiểm soát sẽ giúp tầng Spring Data Couchbase vận hành ổn định cùng repository, `CouchbaseTemplate`, SQL++, CAS, giao dịch và reactive API mà không làm dữ liệu hết hạn ngoài ý muốn.

