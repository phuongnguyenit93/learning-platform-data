# TTL, thời điểm hết hạn và tài liệu không có thời hạn

## 1. Vì sao phải hiểu chính xác thời hạn sống của document?

Trong **Spring Data Couchbase** (module **SPRING_DATA_COUCHBASE**), một document có thể đại diện cho sản phẩm, giỏ hàng tạm, phiên đăng nhập, mã xác minh hoặc một bản ghi nghiệp vụ. Không phải dữ liệu nào cũng nên tồn tại mãi; nhưng nếu đặt thời gian hết hạn sai, ứng dụng có thể mất dữ liệu trước hạn hoặc giữ lại dữ liệu nhạy cảm quá lâu.

Bài học thuộc chương **Thời gian hết hạn**. Trọng tâm là phân biệt ba khái niệm:

1. **TTL (Time To Live):** khoảng thời gian document còn hiệu lực tính từ một mốc áp dụng expiry.
2. **Thời điểm hết hạn tuyệt đối:** một thời điểm cụ thể trên dòng thời gian, chẳng hạn 00:00 UTC ngày kế tiếp.
3. **Document không có thời hạn:** không được gán expiry ở cấp document, nhưng vẫn chịu các chính sách của bucket/collection và những sự kiện xóa khác.

Module học cách xây dựng tầng dữ liệu bằng document mapping, repository, `CouchbaseTemplate` và SQL++; sử dụng bucket/scope/collection, chỉ mục, CAS, giao dịch và reactive API để bảo đảm hiệu năng, nhất quán và khả năng vận hành. Expiry là một phần của những quyết định đó, **không phải chỉ là chức năng dọn dẹp dung lượng**.

Sau bài học, bạn có thể:

- Giải thích đúng tương quan giữa TTL tương đối và thời điểm hết hạn tuyệt đối.
- Nêu khi nào expiry bằng 0 có nghĩa không tự hết hạn, và giới hạn của kết luận này.
- Phân biệt chính sách expiry ở **document**, **collection** và **bucket**.
- Sử dụng API Couchbase Java SDK để đặt, đọc, gia hạn, bảo toàn hoặc xóa thời hạn sống.
- Hiểu cách `@Document(expiry = ...)` của Spring Data tác động đến entity.
- Thiết kế các trường hợp session, cart, mã xác minh và dữ liệu lâu dài.
- Tránh nhầm TTL với CAS, timeout kết nối, durable write, giao dịch và bảo đảm xóa dữ liệu vật lý.

Các ví dụ dựa trên Couchbase Server hiện đại, Couchbase Java SDK 3.x và Spring Data Couchbase/Spring Boot 3.x tương thích. Một số quy tắc expiration, đặc biệt cơ chế `maxTTL`, giới hạn giá trị và dạng dữ liệu được mapper hỗ trợ, cần được xác minh theo phiên bản server/SDK đang triển khai.

## 2. Expiry nằm ở đâu trong hệ thống Couchbase?

Một keyspace ví dụ:

~~~text
Cluster: commerce-cluster
└── Bucket: commerce
    ├── Scope: catalog
    │   └── Collection: products
    └── Scope: checkout
        ├── Collection: carts
        └── Collection: verification_codes
~~~

Các document có chính sách khác nhau:

| Document | Vai trò | Chính sách ví dụ |
| --- | --- | --- |
| `product::SKU-001` | Thông tin sản phẩm | Không expiry tự động |
| `cart::u-42` | Giỏ hàng tạm | TTL 30 phút từ lần ghi gần nhất theo nghiệp vụ |
| `code::u-42` | Mã xác minh một lần | TTL 5 phút, không gia hạn khi đọc |
| `campaign::BLACKFRIDAY` | Chiến dịch có giờ kết thúc | Expiry tại thời điểm tuyệt đối đã định |
| `order::A100` | Đơn hàng | Chính sách lưu trữ riêng; không tự áp TTL phiên đăng nhập |

Một document Couchbase được xác định bởi **bucket, scope, collection và document key**; metadata expiry của nó là thuộc tính riêng với các field JSON.

~~~mermaid
flowchart TD
    A["Document key + JSON content"] --> B["Metadata của document"]
    B --> C["Expiry / thời điểm hết hạn"]
    C --> D{"Đến thời hạn?"}
    D -- "Chưa" --> E["Document hợp lệ để truy cập"]
    D -- "Đã đến" --> F["Document được xem là hết hạn"]
    F --> G["Không thể đọc như document còn hiệu lực"]
    F --> H["Dọn dẹp vật lý theo cơ chế server"]
~~~

**Quan trọng:** hết hạn *logic* và việc server thu hồi tài nguyên lưu trữ *vật lý* không nhất thiết diễn ra chính xác cùng thời điểm. Đừng sử dụng TTL như cơ chế cam kết dữ liệu đã được ghi đè/xóa vật lý ngay một mili giây cụ thể.

## 3. TTL tương đối và thời điểm hết hạn tuyệt đối

### 3.1. TTL tương đối

TTL tương đối diễn đạt: “document có hiệu lực thêm **N giây/phút/giờ kể từ thời điểm expiry được áp dụng**.”

Ví dụ, ghi giỏ hàng lúc 10:00 với TTL 30 phút:

~~~text
10:00  Upsert cart::u-42 với TTL 30 phút
10:15  Giỏ hàng vẫn còn hiệu lực
10:30  Đến thời hạn hết hiệu lực
10:31  KV get không nên xem đây là giỏ hàng đang tồn tại
~~~

Đây là cách tự nhiên cho session, cache và giỏ hàng nếu chính sách nghiệp vụ cho phép gia hạn theo sự kiện.

### 3.2. Thời điểm tuyệt đối

Thời điểm tuyệt đối diễn đạt: “document hết hạn **tại một mốc thời gian nhất định**,” không phụ thuộc thời điểm người dùng gọi API.

Ví dụ chiến dịch phải hết hạn lúc 00:00 UTC ngày 1 tháng 12:

~~~text
Tạo lúc 25/11  → hết hạn 01/12 00:00 UTC
Cập nhật 29/11 → vẫn hết hạn 01/12 00:00 UTC
~~~

Muốn bảo vệ ý nghĩa này khi ghi lại, phải sử dụng lại mốc tuyệt đối hoặc bảo toàn metadata expiry phù hợp, không tự áp dụng lại một TTL tương đối dài tương đương từ thời điểm cập nhật.

### 3.3. So sánh

| Tiêu chí | TTL tương đối | Expiry tuyệt đối |
| --- | --- | --- |
| Cách biểu diễn trong Java SDK | `Duration` | `Instant` |
| Ý nghĩa | Sống thêm một khoảng thời gian | Hết hạn tại một thời điểm cố định |
| Thích hợp | Session, cache, cart tạm | Campaign, token có giờ kết thúc cố định |
| Khi cập nhật | Có thể khởi động lại đồng hồ nếu đặt expiry mới | Có thể giữ mốc cố định khi sử dụng đúng expiry |
| Lỗi phổ biến | Gia hạn ngoài ý muốn khi `save` lại | Lệch múi giờ hoặc dùng nhầm timestamp |

**Dùng `java.time.Duration` và `java.time.Instant` thay vì tự mã hóa số giây nguyên thủy** khi API hỗ trợ. Một số giao thức/phiên bản Couchbase có quy tắc diễn giải số expiry theo mốc 30 ngày; SDK bậc cao giúp tránh chuyển đổi thủ công dễ sai. Khi gửi raw numeric expiry qua API khác, phải hiểu chính xác quy tắc server của phiên bản đó.

## 4. Phân biệt expiry với các khái niệm thời gian khác

| Khái niệm | Đối tượng bị giới hạn | Có xóa document không? |
| --- | --- | --- |
| Document TTL / expiry | Thời gian hợp lệ của document | Có cơ chế làm document hết hiệu lực |
| Connect timeout | Thời gian thiết lập kết nối SDK | Không |
| KV timeout | Thời gian chờ đọc/ghi theo key | Không tự xóa document |
| Query timeout | Thời gian chờ SQL++ query | Không |
| HTTP request deadline | Ngân sách xử lý một API call | Không |
| Transaction timeout | Ngân sách thực hiện transaction theo cơ chế giao dịch | Không phải TTL |
| CAS / `@Version` | Phiên bản đồng thời của document | Không đặt thời hạn sống |

Ví dụ, một lần `get()` bị `TimeoutException` **không đồng nghĩa** document đã hết TTL. Ngược lại, một document hết hạn có thể được SDK báo là không tìm thấy theo hợp đồng KV, không nhất thiết báo một exception riêng “expired”.

## 5. Document không có thời hạn: expiry bằng 0 nghĩa là gì?

Ở mức ngữ nghĩa expiration của Couchbase, **giá trị expiry bằng 0 thường biểu thị không đặt thời hạn hết hiệu lực ở cấp document**. Với bucket/collection không áp chính sách maximum TTL bắt buộc, một document như vậy không tự biến mất vì đồng hồ expiry.

Nhưng cần phân biệt **không TTL** với **bảo đảm tồn tại vĩnh viễn**:

- Document vẫn có thể bị xóa bởi `remove()`, transaction, nghiệp vụ, tác vụ dọn dữ liệu hoặc quản trị viên.
- Bucket/collection có thể bị xóa, dữ liệu có thể không được giữ lại do các sự cố hoặc chính sách vận hành khác.
- Nếu bucket hoặc collection đặt **maximum TTL (maxTTL)**, server có thể áp thời hạn dù caller gửi 0 hoặc không truyền expiry.
- Việc sao lưu, restore, replication và chính sách retention là những vấn đề riêng; không thể suy ra từ một giá trị 0.

**Ví dụ nghiệp vụ:** sản phẩm trong catalog nên tồn tại cho đến khi được sửa/xóa theo quy trình kinh doanh. Nếu collection được cấu hình áp maxTTL 24 giờ, chỉ bỏ qua expiry ở SDK **không đủ** để giữ sản phẩm lâu dài. Phải kiểm tra chính sách server.

### 5.1. Không đặt expiry và đặt expiry bằng 0 có luôn giống nhau?

Không nên mặc định chúng luôn cho kết quả giống nhau trên **mọi** thao tác:

- **Insert mới:** nếu không đặt expiry, server áp chính sách mặc định/`maxTTL` có hiệu lực.
- **Mutation trên document đang có TTL:** một số mutation có thể reset expiry về “không expiry ở cấp document” (rồi vẫn chịu maxTTL), trừ khi bật chức năng **preserve expiry**.
- **Touch hoặc get-and-touch:** chủ đích của API là đổi expiry; không truyền expiry không phải một lựa chọn tương đương.
- **Các API mapping/transaction khác nhau:** có thể có cách quản lý metadata khác; phải kiểm chứng từng đường ghi.

Khi thiết kế một tài liệu cần thực sự tồn tại lâu, **định nghĩa chính sách ở server và code** trước khi chỉ dựa vào mặc định.

## 6. Chính sách expiry ở cấp bucket và collection

Couchbase có thể cung cấp **maxTTL** ở cấp bucket và/hoặc collection tùy phiên bản và cách cấu hình. Đây là chính sách phía server có thể áp thời hạn cao nhất cho dữ liệu trong phạm vi đó.

~~~mermaid
flowchart TD
    A["Ứng dụng ghi document"] --> B["Expiry yêu cầu trong SDK / Spring Data"]
    C["Bucket / Collection maxTTL policy"] --> D["Server xác định expiry có hiệu lực"]
    B --> D
    D --> E["Metadata expiry thực tế của document"]
    E --> F["KV / Query nhìn nhận hiệu lực"]
~~~

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Không có `maxTTL`, document expiry = 0 | Thường không tự hết hạn |
| Có `maxTTL`, client không chỉ định expiry | Server có thể áp thời hạn theo chính sách |
| Client yêu cầu TTL dài hơn `maxTTL` | Giới hạn server có thể rút ngắn TTL hiệu lực |
| Client yêu cầu TTL ngắn hơn `maxTTL` | Có thể dùng TTL ngắn hơn nếu chính sách cho phép |
| Bucket và collection có cấu hình khác nhau | Thứ tự ưu tiên/kế thừa phải xác minh theo phiên bản server |

**Ví dụ về thiết kế:** đừng đặt mã xác minh 5 phút và sản phẩm không TTL trong cùng một collection có maxTTL 5 phút. Nếu chính sách server ép mọi document của collection hết hạn sớm, entity sản phẩm có thể bị mất ngoài ý muốn.

Thông thường, nên tách các collection có nhu cầu retention/expiry rất khác nhau hoặc thống nhất chính sách maxTTL phù hợp. Việc chọn bucket/scope/collection không chỉ ảnh hưởng mapping và index mà còn ảnh hưởng vận hành dữ liệu.

### 6.1. Kiểm tra cấu hình thực tế ở đâu?

Thông số `maxTTL` là **cấu hình server**, không nằm trong `spring.data.couchbase.bucket-name` và không tự phát sinh từ `@Document`. Kiểm tra bằng giao diện quản trị, công cụ quản lý cluster hoặc API được quản trị viên cho phép trên **đúng bucket và collection**.

Không tự viết một tên property `spring.data.couchbase.max-ttl` và cho rằng Spring Boot sẽ tạo chính sách expiry server. Các thuộc tính kết nối/mapper không phải công cụ provisioning tài nguyên server.

## 7. Đặt TTL tương đối với Couchbase Java SDK

Couchbase Java SDK 3.x cung cấp các operation options, ví dụ `UpsertOptions` với `expiry(Duration)`.

~~~java
import java.time.Duration;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

// carts là Collection handle đã trỏ tới commerce.checkout.carts.
JsonObject cart = JsonObject.create()
        .put("userId", "u-42")
        .put("itemCount", 2);

carts.upsert(
        "cart::u-42",
        cart,
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Thao tác này yêu cầu document có TTL 30 phút theo ngữ nghĩa SDK và chính sách server. Nếu collection có `maxTTL` ngắn hơn, cần quan sát expiry hiệu lực thực tế.

Đọc theo key:

~~~java
var result = carts.get("cart::u-42");
System.out.println(result.contentAsObject().getInt("itemCount"));
~~~

Nếu TTL đã qua và document không còn hợp lệ, `get` sẽ không trả về nội dung như một document tồn tại; ứng dụng phải xử lý trường hợp `DocumentNotFoundException` theo nghiệp vụ.

### 7.1. `insert` và `upsert` có cùng TTL API không?

Các phương thức mutation như `insert`, `upsert`, `replace` có option riêng. Khi nghiệp vụ cần expiry, hãy chọn option của **đúng thao tác** thay vì giả định toàn bộ SDK dùng chung một đối tượng `MutationOptions`.

Ví dụ tạo mã dùng một lần:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

// verificationCodes là Collection handle.
verificationCodes.insert(
        "code::u-42",
        JsonObject.create().put("hash", "stored-hash-value"),
        InsertOptions.insertOptions().expiry(Duration.ofMinutes(5))
);
~~~

Đây là ví dụ về lưu **hash** cho mã xác minh thay vì lưu mã xác minh thô. Expiry 5 phút giảm thời gian dữ liệu còn hiệu lực, nhưng không thay thế kiểm soát số lần thử, rate limit và quy trình xóa/từ chối mã đã sử dụng.

## 8. Đặt thời điểm hết hạn tuyệt đối bằng `Instant`

Giả sử một chương trình khuyến mãi kết thúc đúng 00:00 UTC ngày 1 tháng 12 năm 2026. Dù document được ghi ở thời điểm nào, expiry vẫn phải là một mốc cố định.

~~~java
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Instant campaignEndsAt =
        Instant.parse("2026-12-01T00:00:00Z");

campaigns.upsert(
        "campaign::WINTER",
        JsonObject.create().put("name", "Winter"),
        UpsertOptions.upsertOptions().expiry(campaignEndsAt)
);
~~~

`Instant` biểu diễn một thời điểm theo UTC, độc lập timezone hiển thị của người sử dụng. Đừng truyền chuỗi thời gian local không có offset rồi cho rằng server hiểu đúng UTC.

### 8.1. Chuyển thời gian nghiệp vụ sang `Instant`

Nếu nghiệp vụ yêu cầu kết thúc lúc 23:59:59 ở múi giờ Việt Nam, trước tiên phải diễn đạt múi giờ đó bằng API ngày-giờ Java:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant endExclusive = LocalDate.of(2026, 12, 1)
        .atStartOfDay(businessZone)
        .toInstant();
~~~

Biến `endExclusive` ở đây có nghĩa: **mốc đầu ngày 1/12 ở Việt Nam**, nên dữ liệu chỉ còn hiệu lực trước mốc đó nếu chính sách nghiệp vụ dùng khoảng nửa mở. Cách biểu diễn bằng mốc kết thúc loại trừ thường dễ tránh sai một giây ở ranh giới.

### 8.2. Cẩn thận với đồng hồ và độ chính xác

Document expiry thường được xử lý với độ phân giải/thể hiện theo giây trong protocol và metadata; không dựa vào độ chính xác nano giây của `Instant` để thiết kế bảo mật. Đồng bộ thời gian (NTP), timezone và thời điểm server áp dụng expiry cần nằm trong quy trình vận hành.

Nếu client tạo một `Instant` đã thuộc quá khứ, document có thể hết hạn ngay hoặc rất sớm. Với thời hạn có thể đã qua, hãy kiểm tra đầu vào nghiệp vụ trước khi ghi.

## 9. Quy tắc 30 ngày trong một số đường biểu diễn expiry

Khi làm việc ở **mức wire protocol hoặc API chấp nhận giá trị số thô**, Couchbase lịch sử sử dụng quy tắc diễn giải expiration theo độ lớn, thường nhắc tới ngưỡng **30 ngày**: giá trị thời lượng ngắn được hiểu theo số giây tương đối, trong khi giá trị lớn có thể được hiểu như Unix timestamp tuyệt đối.

Vì cơ chế này có thể khác theo phiên bản Server, API và SDK:

- Tránh tự chuyển “45 ngày” thành một số giây rồi đưa vào API raw mà không kiểm tra ngữ nghĩa.
- Với Java SDK, dùng `Duration.ofDays(45)` nếu muốn “45 ngày kể từ khi ghi”, hoặc `Instant` nếu muốn một lịch tuyệt đối.
- Khi sử dụng SQL++, REST hoặc một thư viện cấp thấp, xác minh cách API đó diễn giải expiry thay vì suy từ ví dụ của SDK.
- Không giả định mọi bản Couchbase hiện đại vẫn xử lý giá trị theo cùng một quy tắc legacy.

**Bài học thực tế:** biểu đạt ý định bằng kiểu thời gian có ngữ nghĩa rõ hơn là bằng một integer không chú thích.

## 10. Cập nhật document: reset TTL, giữ TTL và gia hạn TTL

Đây là phần gây lỗi phổ biến nhất. Một document ban đầu được ghi với TTL 30 phút. Sau 20 phút, service cập nhật một field. Expiry sau khi cập nhật sẽ thế nào?

Câu trả lời phụ thuộc **thao tác mutation**, **options** và **chính sách server**:

1. **Reset / đặt expiry mới:** nếu mutation áp TTL 30 phút mới, document có thể sống thêm 30 phút từ lần update.
2. **Preserve expiry:** metadata expiration cũ được giữ lại; document vẫn hết hạn theo mốc ban đầu.
3. **Không gửi expiry trên thao tác thay thế:** tùy API, TTL có thể bị reset về 0 ở cấp document rồi chịu `maxTTL` của server.
4. **Touch:** chủ động đổi expiry mà không cần thay JSON content.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant C as Couchbase Collection
    S->>C: 10:00 upsert TTL = 30 phút
    Note over C: Hạn ban đầu 10:30
    S->>C: 10:20 replace, preserveExpiry = true
    Note over C: Giữ hạn 10:30
    S->>C: Nếu đặt TTL mới 30 phút ở 10:20
    Note over C: Hạn mới có thể là 10:50
~~~

Cách thiết kế hợp lý tùy nghiệp vụ:

- **Mã xác minh:** tuyệt đối không để một cập nhật metadata tùy ý gia hạn mã thêm 5 phút.
- **Giỏ hàng còn hoạt động:** có thể gia hạn 30 phút sau sự kiện tương tác có giá trị.
- **Chiến dịch:** phải giữ mốc hết hạn tuyệt đối, dù sửa nội dung.
- **Tài liệu không TTL:** phải biết `maxTTL` và behavior của save/replace để tránh áp hạn ngoài ý muốn.

### 10.1. Bảo toàn expiry khi `replace`

Một số mutation options của SDK cho phép `preserveExpiry(true)`:

~~~java
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.ReplaceOptions;

// products là Collection handle đã được cấu hình.
products.replace(
        "product::SKU-001",
        JsonObject.create().put("name", "Updated product"),
        ReplaceOptions.replaceOptions().preserveExpiry(true)
);
~~~

Ví dụ nhằm minh họa `preserveExpiry`: document vẫn phải tồn tại và JSON sau replace là toàn bộ content mới. Trong code nghiệp vụ, không nên thay một document nhiều field bằng JSON chỉ chứa `name` nếu muốn giữ các field khác; hãy đọc và tạo nội dung đầy đủ hoặc dùng API subdocument thích hợp.

**CAS:** để tránh ghi đè thay đổi của request khác, thao tác replace có thể cần CAS từ lần đọc trước. Preserve expiry chỉ giữ metadata hết hạn, **không xử lý xung đột ghi**.

### 10.2. Gia hạn một TTL bằng `touch`

SDK hỗ trợ thay đổi thời điểm hết hạn của document đã tồn tại:

~~~java
import java.time.Duration;

carts.touch("cart::u-42", Duration.ofMinutes(30));
~~~

Thao tác này thường không thay đổi JSON content, nhưng **thay đổi metadata hết hạn**. Nó phù hợp cho sliding session hoặc giỏ hàng nếu nghiệp vụ yêu cầu gia hạn khi có tương tác.

Cũng có thể dùng `getAndTouch` để kết hợp đọc và gia hạn:

~~~java
var cartResult = carts.getAndTouch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

**Không nên gọi `touch` cho mỗi request vô điều kiện.** Với session, cần cân nhắc tải, bảo mật, hoạt động thật của người dùng, yêu cầu idle timeout và giới hạn tuyệt đối tối đa.

### 10.3. Sliding TTL và absolute maximum lifetime

Một phiên đăng nhập có thể có hai quy tắc:

- Idle timeout: 20 phút không hoạt động thì hết hiệu lực.
- Absolute lifetime: tối đa 8 giờ kể từ lúc phát hành, bất kể hoạt động.

Nếu chỉ gọi `touch(..., Duration.ofMinutes(20))` liên tục, phiên có thể sống vô hạn trong khi người dùng vẫn hoạt động. Muốn áp cả hai, ứng dụng cần lưu `issuedAt`/`absoluteDeadline` trong dữ liệu nghiệp vụ hoặc cơ chế quản lý phiên phù hợp, và chỉ gia hạn tới **mốc sớm hơn** giữa hai hạn.

~~~text
issuedAt:            09:00
absoluteDeadline:    17:00
lastActivity:        16:50
idleDeadline:        17:10
effectiveExpiry:     17:00
~~~

Đây là quyết định về bảo mật/retention, không chỉ về cú pháp SDK.

## 11. Đọc metadata expiry để xác minh thực tế

Không nên chỉ nhìn vào tham số đã truyền khi ghi rồi đoán document có expiry gì. Cần xác minh **expiry hiệu lực** sau khi chính sách `maxTTL` và mutation được áp dụng.

Couchbase Java SDK hỗ trợ yêu cầu lấy metadata expiry khi thực hiện `get`, thông qua option tương ứng ở các phiên bản hỗ trợ:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = carts.get(
        "cart::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(expiry ->
        System.out.println("Expiry (UTC): " + expiry)
);
~~~

Ở ví dụ này, `expiryTime()` trả về một giá trị tùy chọn theo API SDK; nếu không có metadata expiry được trả về hoặc document không có expiry, không được tự đoán thời điểm. Phải hiểu ý nghĩa `Optional.empty()` theo phiên bản SDK và điều kiện operation.

Lưu ý đọc metadata expiry có thể liên quan thêm chi phí hoặc yêu cầu API cụ thể. Tránh bật chế độ này trên mọi KV read production chỉ để log thời hạn.

### 11.1. Kiểm tra theo ranh giới thời gian

Khi test TTL, phân biệt:

- **T0:** ghi document và nhận mutation thành công.
- **T1:** đọc trước thời điểm expiry dự kiến.
- **T2:** quan sát khi server đã coi document hết hạn.
- **T3:** kiểm tra việc server thu hồi tài nguyên vật lý (nếu thật sự là mục tiêu vận hành).

Một test chỉ kiểm tra “ngủ đủ 5 giây rồi nhìn disk usage” không chứng minh TTL được áp dụng đúng; cơ chế purge và thống kê tài nguyên có nhịp riêng.

## 12. Expiry trong Spring Data Couchbase entity mapping

Nếu TTL là chính sách **cố định cho một loại entity**, Spring Data Couchbase có thể diễn đạt trực tiếp trên annotation `@Document`.

Ví dụ document session hết hạn theo cấu hình tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(expiry = 900) // 900 giây = 15 phút trong mapping hỗ trợ.
@Scope("checkout")
@Collection("sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    private String userId;

    private String deviceId;

    protected LoginSessionDocument() {
    }

    public LoginSessionDocument(
            String id, String userId, String deviceId) {
        this.id = id;
        this.userId = userId;
        this.deviceId = deviceId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public String getDeviceId() { return deviceId; }
}
~~~

Các annotation đóng vai trò khác nhau:

- `@Document(expiry = 900)`: khai báo chính sách expiry tĩnh trong mapping Spring Data, đơn vị giây theo hợp đồng annotation ở phiên bản tương ứng.
- `@Id`: document key.
- `@Scope` và `@Collection`: chọn phạm vi bên trong bucket được cấu hình cho Spring Data.
- Bucket mặc định được xác định bởi cấu hình `spring.data.couchbase.bucket-name`, không bởi `@Document(expiry)`.

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface LoginSessionRepository
        extends CouchbaseRepository<LoginSessionDocument, String> {
}
~~~

Với một cấu hình phù hợp, `repository.save(session)` sẽ sử dụng metadata mapping của entity để thực hiện mutation. **Không suy ra** rằng mỗi thao tác trong SDK thuần hoặc mỗi update SQL++ cũng tự đọc annotation `@Document`: annotation này thuộc pipeline mapping Spring Data.

### 12.1. TTL động theo từng document và `@Expiry`

Có nghiệp vụ không thể dùng một giá trị TTL cố định cho mọi session. Spring Data Couchbase có cơ chế khai báo expiry động bằng property được đánh dấu `@Expiry` trong những phiên bản hỗ trợ.

Nguyên tắc:

- Xác minh package import, kiểu dữ liệu property, đơn vị và quy tắc ưu tiên so với `@Document(expiry = ...)` theo phiên bản Spring Data đang dùng.
- Không trộn một số integer biểu thị “số giây còn lại” với “Unix epoch seconds” nếu mapper đang mong chờ một biểu diễn khác.
- Quy định liệu `save` có nghĩa là *gia hạn*, *giữ hạn cũ* hay *đặt hạn cố định* theo chính sách nghiệp vụ.
- Nếu mapper không cung cấp chính xác mức kiểm soát cần thiết, dùng API SDK hoặc `CouchbaseTemplate` thích hợp, đồng thời giữ trách nhiệm mapping rõ ràng.

**Không mặc định mọi field có tên `expiresAt` đều trở thành metadata expiry.** Một thuộc tính JSON chứa thời gian chỉ là dữ liệu nghiệp vụ, trừ khi code/mapper chủ động biến nó thành expiry của document.

### 12.2. Tài liệu cần tồn tại lâu dài

Ví dụ `ProductDocument` không thiết lập expiry:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class ProductDocument {

    @Id
    private String id;

    private String sku;

    private String name;

    // Constructors và accessors theo mapping thực tế.
}
~~~

Điều này biểu thị không có TTL tĩnh được đặt tại annotation. Nó **không vượt qua** policy `maxTTL` phía bucket/collection. Hãy kiểm tra server nếu thực sự cần không tự hết hạn.

## 13. Truy cập qua `CouchbaseTemplate` và repository: chú ý đường ghi

Spring Data cung cấp abstraction ở tầng entity, nhưng Couchbase Java SDK vẫn quyết định hành vi expiry ở server. Khi chọn API, cần hỏi rõ **ai đặt TTL của mutation**.

| API | Chính sách expiry đến từ đâu? |
| --- | --- |
| `repository.save(entity)` | Metadata mapping của entity, cấu hình Spring Data và chính sách server |
| `CouchbaseTemplate` thao tác entity | Mapping, options được API hỗ trợ và chính sách server |
| SDK `collection.upsert(..., UpsertOptions)` | `expiry(Duration/Instant)` và maxTTL server |
| SDK `collection.replace(..., ReplaceOptions)` | Expiry chỉ định hoặc preserve behavior và maxTTL |
| SDK `touch` / `getAndTouch` | Expiry mới do thao tác touch chỉ định |
| SQL++ `UPDATE` | Cú pháp và hành vi expiration của SQL++/Server; không tự đọc annotation Java |

Một ứng dụng có thể dùng repository để tạo session rồi SDK để cập nhật session. Nếu SDK update không bảo toàn expiry, document có thể sống lâu hơn hoặc ngắn hơn dự kiến.

**Khuyến nghị thiết kế:** chọn một đường ghi chính cho mỗi loại entity hoặc chuẩn hóa chính sách expiry ở service/repository abstraction. Khi cần trộn API, có integration test chứng minh thời gian hết hạn giữ nguyên ý định.

### 13.1. SQL++ và document expiry

Một query tìm kiếm dữ liệu thông qua Query service và index; nó không phải một cách định nghĩa TTL mặc định cho entity. Những document đã hết hạn không nên được coi là còn hiệu lực cho nghiệp vụ chỉ vì backend storage chưa dọn hết dấu vết vật lý.

Ví dụ truy vấn sản phẩm:

~~~sql
SELECT p.sku, p.name
FROM `commerce`.`catalog`.`products` AS p
WHERE p.sku = "SKU-001";
~~~

Query trên collection cần secondary index phù hợp với predicate/plan. Một `get(id)` bằng KV không cần secondary index tương tự. Khi kiểm thử expiry, nên bắt đầu bằng KV theo ID để tách lỗi TTL khỏi lỗi Query service hoặc index.

### 13.2. Index không đặt thời gian hết hạn cho document

Tạo index trên `sku`, `userId` hoặc các trường khác không quyết định TTL. Expiry là metadata/lifecycle của document. Nếu cần tìm các bản ghi **sắp hết hạn** bằng SQL++, có thể lưu một field nghiệp vụ `expiresAt` phù hợp để truy vấn, nhưng điều đó **không tự thay thế metadata expiry**. Phải đồng bộ hai nguồn thông tin nếu cùng sử dụng.

## 14. Tính nhất quán, CAS và giao dịch khi tài liệu sắp hết hạn

Expiry tương tác với cạnh tranh ghi theo nhiều cách.

### 14.1. TTL và CAS là hai điều kiện độc lập

CAS (*Compare-And-Swap*) kiểm tra phiên bản document khi cập nhật. TTL kiểm soát thời gian document còn tồn tại. Có thể dùng cả hai:

1. Request A đọc cart và nhận CAS.
2. Request B cập nhật cart và thay đổi CAS.
3. Request A cố replace với CAS cũ nên có thể bị từ chối.
4. Trong lúc chờ, cart cũng có thể hết hạn, khiến thao tác tiếp theo gặp document-not-found.

Lỗi CAS mismatch **khác** document expired. Hệ thống phải quyết định đọc lại, tạo cart mới, trả conflict hoặc dừng theo ngữ nghĩa nghiệp vụ.

Spring Data `@Version` giúp optimistic locking cho những thao tác mapping hỗ trợ; nó không đặt TTL và không ngăn document hết hạn.

### 14.2. Mutation mơ hồ và hết hạn

Nếu thao tác `upsert` đặt TTL bị `AmbiguousTimeoutException`, client có thể không biết mutation đã thành công hay chưa. Đừng lập tức thử lại với TTL 30 phút mới nếu nghiệp vụ yêu cầu deadline cố định: retry có thể **gia hạn ngoài ý muốn**.

Với deadline tuyệt đối, sử dụng lại cùng một `Instant` khi retry sẽ giữ đúng ý nghĩa thời hạn. Với session/cart, xác định rõ khi nào được phép làm mới TTL; không để chính sách retry tự quyết định thời hạn.

### 14.3. TTL không phải transaction scheduler

Một transaction đang chạy không nên dựa vào việc document sẽ tự hết hạn chính xác trong lúc commit như một cơ chế điều phối công việc. Thời gian hết hạn, timeout của transaction và chính sách commit/rollback là những hợp đồng khác nhau.

Nếu nghiệp vụ cần “chỉ được xác nhận đơn trước hạn giữ hàng”, hãy kiểm tra deadline trong logic nghiệp vụ, dùng transaction/CAS hoặc cơ chế giữ hàng phù hợp; đừng chỉ xem TTL là khóa đồng bộ tuyệt đối giữa nhiều request.

## 15. TTL và ứng dụng reactive

Spring Data Couchbase có `ReactiveCouchbaseRepository` và `ReactiveCouchbaseTemplate`; SDK Java có API reactive. Chúng vẫn làm việc với metadata expiry của cùng Couchbase Server.

Ví dụ SDK reactive tạo giỏ hàng TTL 30 phút:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> mutation = carts.reactive().upsert(
        "cart::u-42",
        JsonObject.create().put("itemCount", 2),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Lưu ý:

- Chỉ tạo `Mono` không có nghĩa mutation đã được thực thi; cần có subscriber theo quy tắc Reactor.
- Subscription mới/retry có thể tạo một mutation mới và vì thế có thể **đặt lại TTL tương đối** nếu code khởi tạo request lại.
- Hủy subscription không chứng minh server chưa ghi hoặc document không được gia hạn.
- `Mono.timeout(...)` giới hạn pipeline reactive, **không phải** document TTL.
- Với reactive WebFlux, tránh `block()` trên event-loop để chờ document tự hết hạn.

Reactive API không làm thay đổi ngữ nghĩa 0-expiry, `maxTTL` hay absolute deadline; nó chỉ thay đổi cách ứng dụng biểu diễn và điều phối thao tác.

## 16. Thiết kế nghiệp vụ: lựa chọn expiry nào?

| Loại dữ liệu | Mẫu chính sách | Cạm bẫy cần tránh |
| --- | --- | --- |
| Mã OTP / reset token | TTL ngắn, không sliding khi đọc | Mỗi lần kiểm tra lại gia hạn mã |
| Session người dùng | Idle TTL và có thể absolute lifetime | Sliding vô hạn ngoài giới hạn bảo mật |
| Giỏ hàng | TTL theo hoạt động có ý nghĩa | Retry hoặc background save vô tình làm mới thời hạn |
| Lock tạm / lease | TTL ngắn kết hợp token sở hữu và fencing nếu cần | Tin TTL là cơ chế khóa phân tán an toàn tuyệt đối |
| Cache document | TTL theo chính sách cache | Nhầm mất cache với mất nguồn dữ liệu gốc |
| Campaign | Thời điểm kết thúc tuyệt đối | Cập nhật nội dung làm đổi deadline |
| Sản phẩm | Không TTL, xóa có chủ đích | Đặt ở collection có maxTTL ngắn |
| Đơn hàng/audit | Retention theo quy định cụ thể | Dùng TTL ngắn mà không có sao lưu/archival |

Một số nghiệp vụ cần **xóa dữ liệu sau N ngày** để đáp ứng quy trình lưu giữ. TTL có thể là một lớp thực thi, nhưng nếu mục tiêu là cam kết xóa vật lý theo yêu cầu pháp lý, cần đánh giá thêm purge, backup, replicas, snapshots, log và các quy trình quản trị dữ liệu. **Không tuyên bố TTL đơn lẻ đã đáp ứng mọi yêu cầu xóa dữ liệu.**

## 17. Kiểm chứng TTL bằng test và quan sát

Một bài test TTL tốt phải đủ chặt nhưng không mong đợi dọn vật lý tức thời.

### 17.1. Kịch bản test tối thiểu

Tạo một document dành riêng cho test trong collection có `maxTTL` đã biết, với TTL ngắn như 3 giây:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String id = "ttl-test::unique-id";

testCollection.upsert(
        id,
        JsonObject.create().put("purpose", "expiry-test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(3))
);
~~~

Kiểm tra:

1. Đọc ngay sau ghi: document tồn tại.
2. Đọc metadata expiry nếu SDK hỗ trợ và cần biết deadline.
3. Sau khi đã vượt hạn với một khoảng dự phòng hợp lý, **poll có giới hạn** cho đến khi `get` báo không tồn tại.
4. Không chỉ dùng một phép `Thread.sleep(3000)` rồi khẳng định chắc chắn server phải dọn disk đúng thời điểm.
5. Xóa dữ liệu test còn lại nếu kịch bản thất bại và dữ liệu vẫn tồn tại.

Nếu test yêu cầu chạy ổn định trên CI, dùng deadline/polling có giới hạn, key duy nhất và cách ly dữ liệu test. Tránh sử dụng document thật hoặc ngủ lâu không kiểm soát.

### 17.2. Test sự khác biệt reset/preserve TTL

Kịch bản:

~~~text
T0:  Upsert với TTL 10 giây
T+3: Replace preserveExpiry=true
T+7: Đọc; vẫn tồn tại
T+12: Đọc; đã hết hạn (có dự phòng)
~~~

Sau đó đối chiếu với trường hợp `replace` chủ động đặt TTL 10 giây mới ở T+3, kỳ vọng thời hạn logic thay đổi. Đặt assertion theo hành vi SDK/server phiên bản thực tế thay vì mặc định tất cả cách update đều preserve.

### 17.3. Test tài liệu không có thời hạn

Tạo document **không expiry** ở collection đã xác nhận không ép maxTTL. Đọc sau một khoảng thời gian hơn TTL của các document test khác và xác minh document còn. Đừng chạy test này trong collection có maxTTL rồi kết luận SDK không thể tạo tài liệu lâu dài.

### 17.4. Quan sát khi triển khai

Nên ghi số lượng document hết hạn theo monitoring/server metrics phù hợp, tỷ lệ document-not-found theo keyspace, lỗi mutation, độ trễ KV, và cảnh báo nghiệp vụ liên quan session/cart. Không log mã OTP, token, dữ liệu nhạy cảm hoặc secret khi debug.

## 18. Những lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân cần xem | Hành động phù hợp |
| --- | --- | --- |
| Document biến mất sớm hơn TTL đã đặt | Bucket/collection `maxTTL` ngắn hơn | Kiểm tra policy server và expiry metadata |
| Document sống lâu hơn mong đợi | Save/update reset hoặc gia hạn TTL | Kiểm tra mutation options và mapper `@Document`/`@Expiry` |
| Document không còn đọc được nhưng disk usage chưa giảm | Expiry logic khác với dọn vật lý | Kiểm tra cơ chế purge/compaction và metrics server |
| `get` báo không tồn tại ngay sau ghi | TTL quá ngắn, deadline quá khứ hoặc keyspace sai | Kiểm tra `Instant`, đồng hồ, bucket/scope/collection |
| Expiry bằng 0 nhưng document vẫn hết hạn | Chính sách maxTTL server | Kiểm tra bucket/collection và ưu tiên cấu hình |
| `touch` kéo dài session vô hạn | Thiếu absolute lifetime | Giới hạn bằng deadline nghiệp vụ |
| Query SQL++ không thấy document | Document đã hết hạn hoặc query/index có vấn đề | Kiểm tra KV theo ID trước, sau đó Query/index |
| Retry sau timeout làm TTL thay đổi | Dùng relative TTL lặp lại | Dùng absolute deadline hoặc idempotent policy phù hợp |
| Document bị ghi đè khi sửa expiry | Không dùng CAS/optimistic locking | Kết hợp CAS/`@Version` khi có cạnh tranh |
| Test TTL thi thoảng flaky | Test theo thời điểm sát ngưỡng, không dự phòng | Polling có deadline, đồng bộ đồng hồ và dùng key riêng |
| Ứng dụng dùng SDK và repository cho cùng entity | Đường ghi có expiry semantics khác | Chuẩn hóa chính sách và viết integration test |

### 18.1. Một luồng chẩn đoán

~~~mermaid
flowchart TD
    A["Document biến mất hoặc tồn tại ngoài mong đợi"] --> B{"Đúng bucket/scope/collection?"}
    B -- "Không" --> C["Sửa mapping hoặc SDK handle"]
    B -- "Có" --> D{"maxTTL ở server là bao nhiêu?"}
    D --> E{"Mutation gần nhất làm gì?"}
    E --> F["Đặt Duration / Instant"]
    E --> G["Preserve expiry"]
    E --> H["Reset / touch / save"]
    F --> I["Đọc expiry metadata + kiểm tra đồng hồ"]
    G --> I
    H --> I
    I --> J{"KV theo key còn hợp lệ?"}
    J -- "Không" --> K["Kiểm tra deadline đã qua"]
    J -- "Có" --> L["Nếu SQL++ khác kết quả, kiểm tra Query/index"]
~~~

Trình tự này tách **lỗi chính sách expiry** khỏi **lỗi mapping/keyspace** và **lỗi truy vấn SQL++**.

## 19. Bài tập tình huống: cart, OTP và sản phẩm

Một ứng dụng bán hàng có:

~~~text
Bucket: commerce
Scope: catalog
  Collection: products
Scope: checkout
  Collection: carts
  Collection: verification_codes
~~~

Yêu cầu:

- Mã OTP hết hạn sau 5 phút kể từ khi phát hành, không gia hạn khi người dùng nhập sai.
- Giỏ hàng hết hạn 30 phút sau hoạt động sửa giỏ gần nhất.
- Sản phẩm tồn tại cho đến khi nghiệp vụ chủ động xóa.
- Một campaign kết thúc đúng 00:00 UTC ngày 1/12/2026.
- Đội vận hành vô tình đặt maxTTL 10 phút trên collection `products`.

**Câu hỏi:**

1. Dùng `Duration` hay `Instant` cho mỗi trường hợp? Giải thích.
2. Nếu cập nhật ghi chú trong OTP sau 3 phút, có được phép reset TTL 5 phút không?
3. Khi người dùng mở giỏ nhưng không chỉnh sửa, bạn có gia hạn TTL không? Quyết định dựa trên chính sách nào?
4. Vì sao không thể bảo đảm sản phẩm tồn tại lâu chỉ bằng cách bỏ `@Document(expiry)`?
5. Nếu campaign update vào ngày 29/11, làm sao giữ nguyên deadline đã định?
6. Cần kết hợp CAS/`@Version` thế nào khi hai thiết bị cập nhật giỏ hàng đồng thời?
7. Vì sao mutation bị ambiguous timeout không được tự động retry với TTL tương đối mới?
8. Hãy thiết kế một test tách KV expiry khỏi độ trễ SQL++ index.

**Đáp án định hướng:**

- OTP: `Duration.ofMinutes(5)` chỉ ở lần phát hành; các cập nhật sau phải giữ hạn cũ, hoặc dùng absolute expiry được lưu giữ.
- Cart: `Duration.ofMinutes(30)` khi có sự kiện gia hạn đã được quy định; nếu có absolute lifetime thì lấy mốc sớm hơn giữa hai giới hạn.
- Product: không đặt TTL ở mapper **và** loại bỏ/điều chỉnh maxTTL không phù hợp ở server.
- Campaign: `Instant.parse("2026-12-01T00:00:00Z")` và giữ mốc khi cập nhật.
- CAS: giúp tránh ghi đè khi nhiều thiết bị sửa cùng document; TTL vẫn phải được xử lý độc lập.
- Retry: phải giữ ý định deadline/idempotency và kiểm tra kết quả mutation khi chưa rõ.
- Test: ghi key riêng, đọc KV trước và sau deadline có dự phòng, rồi kiểm tra SQL++ riêng nếu cần.

## 20. Checklist thiết kế và vận hành

- [ ] Mỗi loại entity có chính sách TTL hoặc “không TTL” được định nghĩa bằng ngôn ngữ nghiệp vụ.
- [ ] Phân biệt rõ `Duration` tương đối và `Instant` tuyệt đối; không dùng numeric epoch tùy tiện.
- [ ] Đã kiểm tra `maxTTL` của bucket và collection trên đúng môi trường.
- [ ] Biết behavior của `save`, `upsert`, `replace`, `touch` và `preserveExpiry` trong phiên bản đang dùng.
- [ ] Các mutation cập nhật không vô tình làm mới TTL của OTP hoặc campaign.
- [ ] Các session sliding TTL có absolute lifetime khi chính sách yêu cầu.
- [ ] Đã kiểm tra metadata expiry hiệu lực, không chỉ tin vào tham số gửi đi.
- [ ] Tài liệu lâu dài không nằm trong collection bị ép maxTTL ngắn.
- [ ] CAS/`@Version` được đánh giá riêng với expiry khi có cập nhật cạnh tranh.
- [ ] Retry mutation có xử lý ambiguous timeout và idempotency.
- [ ] Test TTL có key riêng, thời gian dự phòng và polling có deadline.
- [ ] Không dùng TTL làm bảo đảm duy nhất cho xóa vật lý, backup retention hoặc tuân thủ dữ liệu.
- [ ] KV, SQL++/index và reactive API được kiểm chứng riêng khi nghiệp vụ sử dụng kết hợp.

## 21. Tổng kết

**TTL tương đối** mô tả một khoảng thời gian còn sống; **expiry tuyệt đối** mô tả một mốc thời gian cố định; **expiry bằng 0** thường có nghĩa không đặt hạn ở cấp document, nhưng vẫn chịu chính sách `maxTTL` và các thao tác xóa khác. Hết hạn logic cũng không đồng nghĩa dữ liệu lập tức được loại bỏ vật lý khỏi mọi nơi lưu trữ.

Trong Spring Data Couchbase, có thể đặt TTL tĩnh qua `@Document(expiry = ...)` và dùng các cơ chế mapping/SDK phù hợp cho expiry động. Couchbase Java SDK diễn đạt rõ ý định bằng `Duration` và `Instant`, đồng thời cho phép cập nhật với `touch` hoặc giữ hạn cũ bằng `preserveExpiry` ở những mutation hỗ trợ.

Điều quan trọng nhất là **định nghĩa trước ý nghĩa nghiệp vụ của việc cập nhật document**: gia hạn, giữ nguyên hay đặt lại thời hạn. Khi kết hợp đúng bucket/scope/collection, repository/`CouchbaseTemplate`, SQL++ index, CAS, giao dịch và reactive API, TTL trở thành công cụ quản lý vòng đời dữ liệu tin cậy, thay vì nguồn lỗi hết hạn khó chẩn đoán.

