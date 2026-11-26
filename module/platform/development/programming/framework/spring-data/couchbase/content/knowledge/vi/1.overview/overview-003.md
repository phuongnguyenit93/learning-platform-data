# Mô hình tài liệu JSON và truy cập theo khóa trong Spring Data Couchbase

## 1. Mục tiêu học tập

Bài học thuộc chương **Tổng quan** của **Spring Data Couchbase**. Trọng tâm là cách Couchbase tổ chức document JSON, cách ứng dụng tìm đúng document bằng **document key** và cách Spring Data chuyển thao tác trên Java object thành thao tác truy cập dữ liệu.

Sau bài học, bạn có thể:

- Giải thích mối quan hệ giữa bucket, scope, collection, document ID, JSON body và metadata của document.
- Chọn cách tổ chức trường JSON, dữ liệu lồng nhau và tham chiếu document phù hợp với mẫu đọc/ghi nghiệp vụ.
- Thiết kế document ID ổn định, phân biệt truy cập key–value (KV) với truy vấn SQL++ qua chỉ mục.
- Thực hiện CRUD theo ID bằng Spring Data Couchbase Repository và nhận diện khi cần `CouchbaseTemplate` hoặc SDK.
- Nhận biết ảnh hưởng của CAS, TTL, tính nguyên tử trên một document và lựa chọn reactive API khi ứng dụng có nhiều thao tác I/O đồng thời.

## 2. Couchbase lưu cái gì? Document JSON và khóa truy cập

Trong mô hình document, đối tượng nghiệp vụ thường được lưu thành một JSON document có cấu trúc lồng nhau. Ví dụ hồ sơ người dùng:

~~~json
{
  "name": "Nguyen An",
  "email": "an@example.com",
  "settings": {
    "locale": "vi-VN",
    "receiveEmail": true
  },
  "addresses": [
    {
      "label": "home",
      "city": "Da Nang"
    }
  ]
}
~~~

Couchbase lưu document trên với một **document ID**, ví dụ `profile::u-1001`. ID đó thuộc **metadata của document**; trong JSON phía trên không cần lặp thêm trường `id`. Spring Data ánh xạ trường Java có `@Id` thành document ID, trong khi các trường nghiệp vụ thông thường được chuyển thành JSON body.

Hình dung một document theo hai phần:

~~~text
Địa chỉ logic: bucket = app, scope = identity, collection = profiles
Khóa (metadata ID): profile::u-1001

Giá trị (JSON body):
{
  "name": "Nguyen An",
  "email": "an@example.com",
  "settings": { "locale": "vi-VN", "receiveEmail": true },
  "addresses": [{ "label": "home", "city": "Da Nang" }]
}

Metadata do Couchbase quản lý:
  CAS: thay đổi sau mỗi lần document được sửa
  Expiry/TTL: có thể được thiết lập để document hết hạn
~~~

**Phân biệt quan trọng:** `id` đặt bên trong JSON chỉ là một thuộc tính JSON nếu ứng dụng chủ động lưu nó. Nó không tự động trở thành khóa truy cập. Ngược lại, `@Id` trên Java entity biểu thị khóa metadata của document được Spring Data quản lý.

Couchbase có thể chứa các kiểu giá trị khác ở tầng KV; trong ứng dụng **Spring Data Couchbase với document mapping**, ta tập trung vào JSON document để ánh xạ qua các lớp Java.

## 3. Địa chỉ của một document: bucket → scope → collection → key

~~~mermaid
flowchart TB
    B["Bucket: app"]
    B --> S1["Scope: identity"]
    B --> S2["Scope: commerce"]
    S1 --> C1["Collection: profiles"]
    S1 --> C2["Collection: sessions"]
    S2 --> C3["Collection: carts"]
    C1 --> D1["ID: profile::u-1001"]
    C1 --> D2["ID: profile::u-1002"]
    C3 --> D3["ID: cart::u-1001"]
~~~

| Cấp | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Bucket** | Không gian lưu trữ ở cấp cao; liên quan chính sách và tài nguyên của dữ liệu | Ứng dụng dùng bucket nào? |
| **Scope** | Nhóm collection theo một miền logic | Đây là dữ liệu nhận dạng hay bán hàng? |
| **Collection** | Tập document có mục đích và mô hình truy cập gần nhau | Lưu hồ sơ, session hay giỏ hàng? |
| **Document ID** | Khóa duy nhất **trong một collection** dùng để định vị một document | ID nào giúp lấy đúng đối tượng? |
| **JSON body** | Giá trị chứa các trường nghiệp vụ | Dữ liệu nào cần đọc và thay đổi cùng nhau? |

Một cặp `(collection, document ID)` xác định document trong ngữ cảnh bucket/scope đã chọn. Hai collection khác nhau có thể cùng một chuỗi ID mà không phải cùng một document. Vì vậy, không được bỏ qua collection khi lý giải tính duy nhất của khóa.

Couchbase có scope/collection mặc định tên `_default`. Trong môi trường sản xuất, phân chia collection thường cần xét mô hình truy cập, phân quyền, vòng đời dữ liệu và nhu cầu index. **Một lớp Java không bắt buộc tương ứng với một collection riêng**, và cũng không nên dồn mọi loại document vào một collection chỉ vì ứng dụng có một bucket.

## 4. Tại sao JSON lồng nhau hữu ích?

Một đơn hàng có thể chứa thông tin tóm tắt và các dòng hàng:

~~~json
{
  "customerId": "u-1001",
  "placedAt": "2026-11-25T02:00:00Z",
  "status": "CREATED",
  "currency": "VND",
  "items": [
    { "sku": "SKU-A1", "quantity": 2, "unitPrice": 120000 },
    { "sku": "SKU-B7", "quantity": 1, "unitPrice": 95000 }
  ],
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  }
}
~~~

Nếu màn hình chi tiết đơn hàng luôn cần dòng hàng và địa chỉ giao hàng, lưu các phần đó **lồng vào cùng document** cho phép lấy chúng bằng một lần đọc theo ID. Mô hình này hỗ trợ thao tác nguyên tử trên **một document** (tùy loại thao tác), nhưng cũng đòi hỏi giới hạn kích thước và cách cập nhật phù hợp.

### 4.1. Chọn embed hay tham chiếu ID?

| Tình huống | Gợi ý mô hình | Lý do |
| --- | --- | --- |
| Danh sách dòng hàng trong đơn mua đã chốt | Embed trong document đơn hàng | Thường đọc cùng đơn hàng; số lượng tương đối giới hạn |
| Địa chỉ giao hàng tại thời điểm đặt mua | Embed bản chụp thông tin | Đơn hàng không bị thay đổi lịch sử khi người dùng sửa địa chỉ cá nhân |
| Toàn bộ đơn hàng của khách hàng nhiều năm | Mỗi đơn hàng là document riêng, chứa `customerId` | Danh sách tăng liên tục, vòng đời độc lập, cần truy vấn/phân trang |
| Giỏ hàng hiện tại của một người dùng | Một document với mảng items có giới hạn | Đọc và cập nhật theo người dùng |
| Mọi đánh giá của một sản phẩm phổ biến | Các document đánh giá riêng | Dữ liệu có thể rất lớn và có nhiều cập nhật đồng thời |

**Nguyên tắc:** Embed các thành phần có vòng đời và đường đọc gần nhau; tham chiếu khi dữ liệu có thể tăng không giới hạn, được chia sẻ hoặc cần thay đổi độc lập. Tránh làm một document thành điểm nóng khi hàng nghìn yêu cầu cập nhật chung một khóa.

### 4.2. JSON linh hoạt không có nghĩa là thiếu hợp đồng dữ liệu

Hai document trong một collection có thể có tập trường khác nhau:

~~~json
{ "name": "Mai", "phone": null }
~~~

~~~json
{ "name": "Nam", "preferences": { "language": "vi" } }
~~~

Trường `phone` bằng `null` khác với việc trường đó **không tồn tại**; hành vi truy vấn và mapping có thể khác nhau tùy điều kiện và converter. Khi đổi schema, cần có quy ước dữ liệu bắt buộc/tùy chọn, giá trị mặc định và tương thích với document cũ. JSON không tự bảo đảm khóa ngoại, uniqueness của email hay các quy tắc nghiệp vụ; ứng dụng và thiết kế lưu trữ phải xử lý những bất biến đó.

## 5. Thiết kế document ID cho truy cập theo khóa

Document ID là yếu tố quyết định xem ứng dụng có thể truy cập trực tiếp bằng KV hay phải tìm kiếm trước.

Ví dụ ID đề xuất:

| Loại dữ liệu | ID minh họa | Cách xác định |
| --- | --- | --- |
| Hồ sơ người dùng | `profile::u-1001` | Từ ID người dùng bất biến |
| Giỏ hàng đang hoạt động | `cart::u-1001` | Từ ID người dùng nếu mỗi người chỉ có một giỏ |
| Đơn hàng | `order::ord-09f4` | ID đơn hàng duy nhất được cấp khi tạo |
| Phiên truy cập | `session::7f28c...` | Token/ID ngẫu nhiên không đoán được, với chính sách bảo mật phù hợp |

Dấu `::` chỉ là **quy ước đặt tên** giúp con người hiểu khóa; Couchbase không yêu cầu tiền tố đó và không tự phân loại document theo dấu này. Không nên nhét email, số điện thoại, mật khẩu, token gốc hoặc dữ liệu riêng tư vào ID; khóa thường có mặt trong log, trace và thông báo lỗi. Nếu yêu cầu một người dùng chỉ có một giỏ hàng, ID xác định như `cart::u-1001` hỗ trợ tìm ngay giỏ mà không cần truy vấn theo `customerId`.

**Quy tắc chọn ID:**

1. Dùng giá trị ổn định qua vòng đời document. Không chọn email làm ID hồ sơ khi email có thể đổi.
2. Biết rõ phạm vi định danh: bucket/scope/collection và tenant liên quan.
3. Không để hai luồng tạo đối tượng khác nhau nhưng vô tình cấp cùng ID.
4. Dùng định danh ngẫu nhiên phù hợp cho đối tượng không có khóa nghiệp vụ ổn định.
5. Chỉ đưa tenant vào ID khi đó là chiến lược định danh đã thống nhất; vẫn phải kiểm soát quyền truy cập theo tenant ở tầng dịch vụ/database.
6. Đừng mặc định tìm theo tiền tố ID là truy cập KV. KV yêu cầu **biết chính xác toàn bộ khóa**; tìm các khóa cùng tiền tố là bài toán truy vấn hoặc cơ chế liệt kê khác.

### Từ khóa nghiệp vụ đến ID

~~~mermaid
flowchart LR
    R["GET /customers/u-1001"] --> ID["Tạo ID: profile::u-1001"]
    ID --> KV["KV get: collection + ID"]
    KV --> D{"Có document?"}
    D -->|Có| OK["Ánh xạ JSON → Java"]
    D -->|Không| NF["Trả 404 theo quy ước API"]
~~~

Nếu ứng dụng nhận email thay cho ID, không thể suy ra chắc chắn khóa `profile::u-1001` nếu thiếu bảng ánh xạ/thiết kế riêng. Lúc này có thể tìm qua SQL++ với index hoặc thiết kế document ánh xạ phụ, nhưng phải cân nhắc độ nhất quán và cập nhật đồng bộ.

## 6. Đọc ghi theo KV khác gì SQL++?

Couchbase hỗ trợ hai nhóm đường truy cập thường gặp:

| Tiêu chí | KV theo document ID | SQL++ theo trường JSON |
| --- | --- | --- |
| Đầu vào | Collection và **chính xác ID** | Điều kiện lọc, sắp xếp, join, projection… |
| Ví dụ | Đọc `cart::u-1001` | Tìm các giỏ cập nhật sau một thời điểm |
| Cơ chế | Data/KV Service định vị document | Query Service thực thi SQL++, thường dựa vào index |
| Secondary index | Không cần để lấy chính xác ID | Thường cần index phù hợp với truy vấn |
| Kết quả | Một document hoặc không tồn tại | Không, một hoặc nhiều dòng |
| Tính nhất quán ngay sau ghi | Thường dùng KV để lấy trạng thái document mới nhất theo key và semantics được cấu hình | Cần xét độ trễ cập nhật index và scan consistency |
| Phù hợp | Tra cứu chi tiết, session, giỏ hàng, cập nhật theo ID | Màn hình tìm kiếm, lọc danh sách, báo cáo theo tiêu chí |

**KV không thể tự thực hiện** yêu cầu “cho tôi 20 người có email thuộc domain X”. Việc biết giá trị trường JSON không đồng nghĩa biết document ID.

Ví dụ truy vấn SQL++ tìm theo email ở keyspace `app.identity.profiles`:

~~~sql
SELECT META(p).id AS documentId, p.name, p.email
FROM `app`.`identity`.`profiles` AS p
WHERE p.email = "an@example.com";
~~~

Một index minh họa:

~~~sql
CREATE INDEX ix_profiles_email
ON `app`.`identity`.`profiles`(email);
~~~

Hai câu SQL++ này dùng để làm rõ mô hình truy cập, **không phải** SQL++ chính xác mà mọi phương thức Spring Data Repository sẽ sinh ra. Derived queries của Spring Data có thể kèm điều kiện phân biệt kiểu entity; hãy xem query thực và `EXPLAIN` khi thiết kế index. Ghi thêm index có chi phí lưu trữ và cập nhật; đừng tạo index chỉ để cải thiện thao tác `findById`.

### 6.1. Các thao tác KV và ngữ nghĩa thường gặp

| Thao tác | Ý nghĩa | Khi sử dụng |
| --- | --- | --- |
| `get` | Đọc document theo ID | Xem hồ sơ, lấy giỏ hàng |
| `insert` | Chỉ tạo nếu ID chưa có; trùng ID thì báo lỗi | Tạo đối tượng cần ngăn ghi đè |
| `upsert` | Tạo mới hoặc thay thế giá trị theo ID | Trường hợp thực sự cho phép ghi đè |
| `replace` | Thay document đã tồn tại; có thể kèm CAS | Cập nhật có kiểm soát |
| `remove` | Xóa theo ID | Xóa đối tượng theo yêu cầu |
| `exists` | Kiểm tra ID tồn tại | Kiểm tra tồn tại (vẫn phải xử lý race condition) |

Bảng trên mô tả ngữ nghĩa **ở mức KV/SDK**. Phương thức `save` trong Spring Data là API mức entity và hành vi cụ thể còn chịu ảnh hưởng của metadata/versioning; không đồng nhất máy móc `save` với mọi thao tác trong bảng.

Lỗi race condition điển hình: gọi `exists` trước rồi `insert` **không** bảo đảm không xảy ra cạnh tranh. Hai request đều có thể đọc “chưa tồn tại” trước khi một request ghi. Cần để thao tác tạo có điều kiện (như insert) hoặc cơ chế ràng buộc nghiệp vụ quyết định kết quả cuối cùng.

## 7. Truy cập JSON bằng Spring Data Couchbase

Mục tiêu của Spring Data Couchbase là ánh xạ giữa Java object và JSON document, hỗ trợ Repository, `CouchbaseTemplate` và Reactive API mà không yêu cầu service tự chuyển đổi JSON trong các trường hợp thông thường.

### 7.1. Entity và mapping

Ví dụ sau minh họa kiểu Java cho document hồ sơ. Giả sử ứng dụng đã cấu hình Couchbase connection, bucket và mapping tới collection phù hợp với phiên bản Spring Boot/Spring Data đang sử dụng.

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class CustomerProfile {

    @Id
    private String id;

    @Field
    private String name;

    @Field
    private String email;

    @Field
    private Preferences preferences;

    @Version
    private Long version;

    public CustomerProfile() {}

    public CustomerProfile(String id, String name,
                           String email, Preferences preferences) {
        this.id = id;
        this.name = name;
        this.email = email;
        this.preferences = preferences;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Preferences getPreferences() { return preferences; }
    public void setPreferences(Preferences preferences) {
        this.preferences = preferences;
    }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public static class Preferences {
        private String locale;
        private boolean receiveEmail;

        public Preferences() {}

        public Preferences(String locale, boolean receiveEmail) {
            this.locale = locale;
            this.receiveEmail = receiveEmail;
        }

        public String getLocale() { return locale; }
        public void setLocale(String locale) { this.locale = locale; }

        public boolean isReceiveEmail() { return receiveEmail; }
        public void setReceiveEmail(boolean receiveEmail) {
            this.receiveEmail = receiveEmail;
        }
    }
}
~~~

Trong ví dụ này:

- `@Document`: đánh dấu entity được Couchbase mapping.
- `@Id`: định danh document ở Couchbase, **không yêu cầu lưu vào JSON body**.
- `@Field`: đưa thuộc tính vào JSON, bao gồm object lồng nhau như `preferences`.
- `@Version`: Spring Data dùng thông tin phiên bản/CAS để hỗ trợ optimistic locking. CAS là metadata do server quản lý, không phải số tăng tuần tự do ứng dụng tự ghi trong JSON.
- Dữ liệu thực tế có thể có trường metadata phân biệt loại entity do Spring Data thêm, ví dụ `_class`, tùy cấu hình mapper. Cần xác nhận JSON và query generated trong môi trường thật.

Ví dụ nhằm làm rõ cách ánh xạ; kiểu Java và chú thích collection, độ tương thích Java/Boot phải được thống nhất với dependency cụ thể của dự án.

### 7.2. Repository và truy cập theo key

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerProfileRepository
        extends CouchbaseRepository<CustomerProfile, String> {
}
~~~

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {
    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public Optional<CustomerProfile> findByCustomerId(String customerId) {
        String documentId = "profile::" + customerId;
        return repository.findById(documentId);
    }

    public CustomerProfile create(String customerId, String name,
                                  String email) {
        String documentId = "profile::" + customerId;
        CustomerProfile.Preferences preferences =
                new CustomerProfile.Preferences("vi-VN", true);
        CustomerProfile profile =
                new CustomerProfile(documentId, name, email, preferences);
        return repository.save(profile);
    }

    public void deleteByCustomerId(String customerId) {
        repository.deleteById("profile::" + customerId);
    }
}
~~~

Tuyến chính của `findById(documentId)` là lookup theo khóa, không phải quét tập document tìm trường `id` trong JSON. `save(profile)` làm việc trên entity; khi dùng `@Version`, phiên bản của entity ảnh hưởng đến cách Spring Data kiểm soát insert/update và xung đột ghi. API xóa cần được service bảo vệ bởi phân quyền và quy tắc nghiệp vụ; không nên nhận trực tiếp khóa tùy ý từ client rồi tin tưởng tuyệt đối.

Để tìm theo `email`, có thể thêm phương thức dẫn xuất `findByEmail`; lúc đó API không còn là lookup thuần theo key, cần xem truy vấn SQL++/index. Đây là hai cách truy cập cần được đo và thiết kế riêng.

### 7.3. Khi nào chọn Template hoặc SDK?

- **Repository:** CRUD entity theo ID, phương thức tìm kiếm phổ biến, phù hợp phần lớn thao tác tầng ứng dụng.
- **`CouchbaseTemplate`:** cần kiểm soát trực tiếp hơn cấu hình query/mapping/thao tác trên entity trong hệ sinh thái Spring Data.
- **Couchbase Java SDK:** thao tác chuyên sâu, điều chỉnh KV đặc thù, sub-document operations hoặc lựa chọn tính năng mà abstraction hiện dùng chưa phơi bày thuận tiện.
- **Reactive Repository/Template:** với ứng dụng đã dùng Reactor/WebFlux và muốn chuỗi I/O không chặn; API reactive không làm một query thiếu index trở nên nhanh.

Không có một API tối ưu cho mọi workload. Chọn theo đường truy cập, yêu cầu concurrency và khả năng quan sát vận hành.

## 8. Cập nhật document và xử lý ghi đồng thời

Hình dung hai request cùng đọc một hồ sơ:

~~~text
T0: Request A đọc profile::u-1001, CAS = C1
T1: Request B đọc profile::u-1001, CAS = C1
T2: A đổi locale và ghi -> thành công, CAS = C2
T3: B đổi receiveEmail trên bản cũ, ghi với CAS = C1
T4: Nếu dùng optimistic locking -> xung đột thay vì ghi đè thay đổi của A
~~~

Dùng `@Version` cho entity thường giúp phát hiện xung đột khi lưu. Khi bắt được xung đột, service có thể yêu cầu người dùng làm mới dữ liệu hoặc **đọc lại bản mới, áp dụng lại thay đổi nghiệp vụ rồi retry có giới hạn**. Retry phải có quy tắc để tránh gửi lại tác dụng phụ như gọi thanh toán hay gửi email.

### 8.1. Ghi nguyên document hay cập nhật một phần?

Có hai cách tư duy:

- **Đọc–sửa–ghi entity**: lấy document thành Java object, thay đổi thuộc tính, lưu trở lại. Cách này rõ ràng trong domain code; với concurrency phải nghĩ tới CAS.
- **Sub-document KV operation**: SDK có thao tác cập nhật một đường dẫn JSON hoặc một phần của document mà không cần truyền toàn bộ body giữa client và server. Đây là lựa chọn để tối ưu một số phép thay đổi nhưng vẫn cần kiểm soát đường dẫn, kiểu dữ liệu, điều kiện cập nhật và xung đột.

Một thay đổi trong một document có thể được xử lý nguyên tử ở cấp document, nhưng không vì thế tự suy ra hai document khác nhau được cập nhật nguyên tử cùng nhau. Nếu chuyển hàng từ kho A sang kho B, hoặc tạo đơn và trừ tồn kho ở các document riêng, phải thiết kế giao dịch đa document hoặc workflow bù trừ theo yêu cầu nhất quán.

### 8.2. CAS khác TTL và durability

| Cơ chế | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **CAS** | Có ai thay document kể từ khi tôi đọc? | Không làm mất thay đổi giữa hai tab |
| **TTL/expiry** | Document nên tự hết hạn khi nào? | Phiên tạm hết hạn theo thời gian |
| **Durability** | Ghi đã đạt mức xác nhận/lưu bền yêu cầu chưa? | Chọn mức bảo đảm khi ghi dữ liệu quan trọng |
| **Transaction** | Nhiều thao tác liên quan có cần cùng thành công/thất bại? | Tạo đơn và cập nhật dữ liệu đi kèm |

Bốn vấn đề này độc lập về mục đích. TTL nằm trong metadata, không phải một trường `expiresAt` thông thường mà Couchbase tự hiểu. Cách thiết lập/thay đổi expiry qua entity, template và SDK cần đối chiếu tài liệu theo phiên bản; không giả định mọi thao tác `save` sẽ giữ nguyên expiry trong mọi cấu hình.

## 9. Truy vấn ngay sau khi ghi: vấn đề nhìn thấy dữ liệu

Giả sử ứng dụng tạo hồ sơ và thực hiện liên tiếp:

1. `repository.save(profile)` ghi document.
2. `repository.findById("profile::u-1001")` truy cập theo key.
3. `repository.findByEmail("an@example.com")` truy vấn theo thuộc tính và index.

Bước 2 và bước 3 có đường thực thi khác nhau. Với query dùng secondary index, việc cập nhật index có thể chưa bắt kịp thao tác ghi; kết quả query mặc định có thể **tạm thời chưa phản ánh** document vừa ghi. Khi hệ thống cần khả năng read-your-writes ở query, phải xác định scan consistency phù hợp, chẳng hạn `request_plus` hoặc chính sách consistency theo mutation token khi API cung cấp, đồng thời đo độ trễ tăng thêm.

Đọc KV trực tiếp theo ID giúp tránh sự phụ thuộc vào secondary index cho tình huống biết khóa. Tuy nhiên, không nên gom mọi khái niệm nhất quán, khả dụng và độ bền ghi thành một bảo đảm đơn giản: timeout, failover, durability và tính nhất quán truy vấn vẫn cần xem xét theo cluster và API đang dùng.

## 10. Hiệu năng: khi nào document key mang lại lợi ích rõ nhất?

### Trường hợp A — Xem giỏ hàng của người dùng

API nhận `userId = u-1001`. Nếu ID giỏ được quy ước là `cart::u-1001` trong collection `carts`, service biết luôn collection và key. Một lần `findById` có thể lấy cả danh sách items và tổng tiền tạm tính, không cần tìm theo trường `userId`.

Rủi ro: nếu hai request thay đổi giỏ đồng thời, phải dùng optimistic locking/CAS hoặc thao tác có điều kiện; một document quá lớn hay bị cập nhật quá dày sẽ gây contention.

### Trường hợp B — Xem đơn hàng từ URL

`GET /orders/ord-09f4` ánh xạ tới `order::ord-09f4`. Đọc theo key phù hợp cho màn hình chi tiết. Ngược lại, “liệt kê đơn hàng của người dùng trong tháng này” cần truy vấn theo `customerId` và `placedAt` (hoặc cơ chế index/tổng hợp riêng); không thể dùng một KV get duy nhất.

### Trường hợp C — Session hết hạn

Ứng dụng lưu document session theo khóa phiên ngẫu nhiên, với expiry thích hợp. Truy cập session bằng đúng khóa phù hợp KV; TTL giúp quản lý vòng đời. Cần lưu ý xóa do hết hạn có cơ chế xử lý theo hệ thống, không phải bộ hẹn giờ chính xác đến từng mili giây để kích hoạt một nghiệp vụ khác.

### Trường hợp D — Tìm hồ sơ bằng email

Nếu API chỉ nhận email, `findById` không giải quyết được vì không biết ID người dùng. Dùng truy vấn SQL++ với index email hoặc cơ chế ánh xạ email–ID được thiết kế riêng. Nếu email phải duy nhất, đừng suy rằng tạo secondary index thông thường tự bảo đảm tính duy nhất của email; phải thiết kế ràng buộc và thao tác tạo/cập nhật phù hợp.

## 11. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân | Cách cải thiện |
| --- | --- | --- |
| Truy vấn theo ID lại chậm vì phải lọc toàn bộ document | Lưu khóa chỉ trong JSON, không biết metadata key | Thiết kế quy ước ID ổn định và truy cập `findById` |
| Document hồ sơ đổi email khiến phải đổi ID | Dùng email làm khóa chính | Dùng ID bất biến; email là thuộc tính thay đổi |
| Giỏ hàng mất dữ liệu của một tab | Ghi đè document không kiểm tra bản cũ | `@Version`/CAS, giải quyết xung đột |
| Danh sách đánh giá được embed mãi trong sản phẩm | Mảng không giới hạn, cập nhật tập trung | Tách đánh giá thành document riêng |
| Tìm theo email vừa lưu lại không thấy | Query qua index, consistency chưa đáp ứng | Kiểm tra index và scan consistency |
| `findById` hoạt động nhưng `findByEmail` lỗi | Thiếu index hoặc sai collection/điều kiện query | Tạo index phù hợp, xem SQL++ sinh ra và `EXPLAIN` |
| Dữ liệu trong JSON đọc sang Java sai | Khác tên trường, kiểu dữ liệu hoặc schema qua các phiên bản | Chuẩn hóa mapper, default, migration và kiểm thử tương thích |
| Hai collection có cùng ID bị xem là cùng document | Hiểu sai phạm vi duy nhất của key | Luôn định danh cùng bucket/scope/collection |

Để vận hành ổn định, cần thêm timeout, retry có giới hạn, xác thực/phân quyền, theo dõi độ trễ KV và SQL++, số lỗi CAS, dung lượng document, tác động của index và load test với phân bố key thực tế. Với workload reactive, giữ pipeline không chặn và quan sát cả mức dùng connection/tài nguyên server.

## 12. Thực hành tư duy thiết kế

**Bài tập:** Một nền tảng học trực tuyến quản lý hồ sơ học viên, khóa học, tiến độ từng học viên và lịch sử xem bài. API phổ biến:

- Xem hồ sơ từ ID học viên.
- Xem tiến độ của một học viên trong một khóa học.
- Liệt kê toàn bộ khóa học mà học viên đang học.
- Ghi sự kiện mỗi lần người dùng xem bài.
- Hết hạn mã truy cập tạm sau 15 phút.

**Phương án gợi ý:**

| Dữ liệu | Khóa gợi ý | Chiến lược truy cập |
| --- | --- | --- |
| Hồ sơ học viên | `student::s-123` | KV get theo ID |
| Tiến độ học viên–khóa học | `progress::s-123::course-456` | KV get khi biết cặp ID; CAS khi cập nhật đồng thời |
| Danh sách khóa đã đăng ký | Document enrollment riêng hoặc mô hình tổng hợp có giới hạn | Query/index theo học viên hoặc cache/tổng hợp được cập nhật có kiểm soát |
| Lịch sử xem bài | ID sự kiện duy nhất cho mỗi lần xem | Ghi độc lập, query theo học viên/thời gian khi cần |
| Mã truy cập tạm | ID ngẫu nhiên có entropy phù hợp | KV get và expiry được cấu hình |

Không nhất thiết phải lấy toàn bộ lịch sử xem bài bằng một document học viên; lịch sử tăng liên tục. Với tiến độ, cặp ID định danh giúp truy cập trực tiếp, nhưng vẫn phải quyết định cách xử lý nhiều thiết bị đồng thời và quy tắc chỉ tiến lên của phần trăm hoàn thành.

**Tự kiểm tra:**

1. Nếu hai collection đều có khóa `student::s-123`, có phải cùng một document không? **Không** — key chỉ có ý nghĩa trong collection tương ứng.
2. Khi đã biết ID chính xác, cần tạo secondary index để `findById` hoạt động không? **Không**.
3. Lưu `"id": "student::s-123"` vào JSON có tự động biến nó thành document key không? **Không** — phải dùng metadata key thông qua API/mapping phù hợp.
4. `@Version` giải quyết trường hợp gì? **Phát hiện xung đột cập nhật**, không thay thế giao dịch nhiều document.
5. Vì sao truy vấn theo email có thể chưa thấy document vừa tạo? **Index/query consistency** có thể khác đường đọc KV.

## 13. Kết luận

Mô hình JSON document của Couchbase cho phép lưu một đơn vị nghiệp vụ dưới dạng cấu trúc có thể lồng nhau; **document ID là địa chỉ truy cập trực tiếp** tới đơn vị đó trong collection. Thiết kế key bền vững, chọn ranh giới embed/tham chiếu và hiểu rõ KV là nền tảng để tầng truy cập Spring Data Couchbase đạt hiệu năng tốt.

`CouchbaseRepository` giúp ánh xạ Java object và thực hiện CRUD theo key; `CouchbaseTemplate` và SDK mở thêm lựa chọn cho thao tác đặc thù, còn reactive API thích hợp với luồng xử lý I/O không chặn. Để dữ liệu đúng và có thể vận hành, cần kết hợp thiết kế document với **index SQL++, CAS, TTL, durability và transaction** theo nhu cầu thực tế.
