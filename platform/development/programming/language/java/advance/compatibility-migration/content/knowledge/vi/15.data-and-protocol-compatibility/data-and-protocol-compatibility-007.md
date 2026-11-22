# Cache, phiên đăng nhập và thông điệp tồn tại qua lần triển khai

Khi nâng cấp JDK, framework hoặc phiên bản ứng dụng Java, chúng ta thường kiểm tra mã nguồn có biên dịch được và service có khởi động được hay không. Tuy nhiên, một hệ thống đang hoạt động còn chứa **trạng thái được tạo bởi phiên bản trước**: giá trị trong cache, phiên đăng nhập của người dùng, các sự kiện chờ tiêu thụ trong message broker, tác vụ retry, bản ghi dead-letter và dữ liệu do một service khác phát hành. Những dữ liệu này không tự biến mất khi thay container, đổi JDK hoặc đưa một phiên bản mới vào production.

Ví dụ, service cũ chạy Java 8 đã ghi một object đã Java-serialize vào Redis. Service mới chạy Java 21 có cùng cache key nhưng một lớp đã đổi package, thêm field hoặc đổi `serialVersionUID`. Việc triển khai có thể thành công, nhưng request đọc cache tạo `InvalidClassException` hoặc `ClassNotFoundException`. Một tình huống khác: consumer cũ vẫn đang chạy trong rolling deployment, trong khi producer mới bắt đầu phát sự kiện với enum hoặc kiểu dữ liệu mà consumer cũ không biết. Mọi test chỉ dùng dữ liệu mới trên phiên bản mới đều có thể xanh, còn production lỗi sau nhiều phút hoặc nhiều ngày.

Bài học này hướng dẫn cách xác định các loại trạng thái vượt qua ranh giới triển khai, đánh giá khả năng đọc/ghi giữa phiên bản cũ và mới, lập chiến lược **expand–migrate–contract** và kiểm thử trên đúng vòng đời của cache, session và thông điệp.

## 1. Trạng thái “sống lâu hơn phiên bản ứng dụng” là gì?

Một process Java có thể kết thúc, nhưng dữ liệu mà nó tạo ra vẫn được giữ ở nơi khác:

- **Distributed cache:** Redis, Memcached, Hazelcast, Infinispan hoặc kho dữ liệu cache của ứng dụng.
- **Persistent local cache:** file cache, disk store hoặc embedded data store nằm trên volume không bị thay khi deploy.
- **HTTP session:** session ở database/Redis, session replication trong application server, hoặc token chứa claim do server trước phát hành.
- **Message broker:** Kafka topic, RabbitMQ queue, JMS provider, hệ thống event streaming và các bản ghi retry/dead-letter.
- **Scheduled/durable jobs:** payload đã lưu trong job scheduler hoặc database để xử lý sau.
- **Outbox/inbox:** sự kiện và bản ghi deduplication được lưu để chuyển tiếp giao dịch và xử lý lặp lại.
- **Object storage/file:** snapshot hoặc payload xuất ra cho các batch/consumer đọc trong tương lai.

Đây là những dạng **hợp đồng dữ liệu theo thời gian**. Bên ghi dữ liệu tại thời điểm T có thể không phải cùng phiên bản với bên đọc ở thời điểm T+1.

Một triển khai tiêu biểu:

~~~text
                  Trước khi deploy                 Sau khi deploy
              +---------------------+        +---------------------+
              | App v1 / JDK cũ     |        | App v2 / JDK mới     |
              | Cache writer v1     |        | Cache reader v2     |
              | Session writer v1   |        | Session reader v2   |
              | Event producer v1   |        | Event consumer v2   |
              +----------+----------+        +----------+----------+
                         |                              |
                         +--------------+---------------+
                                        |
                        +---------------+---------------+
                        | Redis / DB / broker / storage  |
                        | Dữ liệu chưa hết hạn hoặc chưa |
                        | được tiêu thụ vẫn còn nguyên  |
                        +-------------------------------+
~~~

Trong rolling deployment, **v1 và v2 còn có thể chạy đồng thời**. Do đó phải tính cả trường hợp v1 đọc dữ liệu v2 vừa ghi, chứ không chỉ v2 đọc dữ liệu cũ.

## 2. Năm chiều tương thích cần đánh giá

Tương thích dữ liệu qua deployment không chỉ là “JSON còn parse được”. Có ít nhất năm chiều:

1. **Format compatibility:** payload được biểu diễn bằng JSON, Java Serialization, Avro, Protobuf, CBOR hay binary format nào? Reader có nhận ra format không?
2. **Schema compatibility:** tên field, kiểu, required/optional, default, enum và cấu trúc nested có còn phù hợp?
3. **Semantic compatibility:** cùng một field nhưng ý nghĩa có thay đổi không? Ví dụ `expiresAt` trước là giây, sau là mili giây.
4. **Security compatibility:** dữ liệu có bị mã hóa/ký, thay key, đổi algorithm, thêm policy hoặc thay trust boundary không?
5. **Operational compatibility:** dữ liệu tồn tại bao lâu, có được ghi đồng thời bởi hai phiên bản, có thể rollback và có đủ metrics để biết lỗi không?

Mỗi chiều có thể tạo lỗi theo cách khác nhau:

| Thay đổi | Lỗi có thể gặp | Biện pháp kiểm chứng |
|---|---|---|
| Đổi serializer từ JDK binary sang JSON | Reader đọc sai magic bytes/format | Thử payload thật của v1 bằng reader v2 |
| Đổi package/class name | Java deserializer không tìm thấy class | Dùng fixture binary cũ; tránh Java object serialization cho hợp đồng dài hạn |
| Thêm required field không có default | Payload cũ thiếu dữ liệu bắt buộc | Test schema v1→reader v2 |
| Thêm enum value | Consumer cũ không xử lý giá trị mới | Kiểm tra fallback/unknown enum |
| Đổi đơn vị timestamp | Không lỗi parse nhưng thời gian sai | Contract test hành vi và boundary cases |
| Đổi khóa mã hóa/signing | Session hoặc payload cũ không giải mã/xác minh | Test rotation và rollback có kiểm soát |
| Đổi TTL | Session mất sớm hoặc dữ liệu cũ sống lâu bất thường | Test expiration và monitoring |
| Deploy đồng thời producer/consumer | v1 nhận event chỉ v2 hiểu | Ma trận v1↔v2 và kế hoạch rollout |

**Đọc thành công chưa đồng nghĩa hành vi đúng.** Một value parse ra đầy đủ field nhưng đơn vị tiền hoặc timezone sai có thể nguy hiểm hơn lỗi rõ ràng.

## 3. Ma trận đọc và ghi giữa phiên bản

Dùng ký hiệu:

- `W1`: phiên bản cũ ghi.
- `R1`: phiên bản cũ đọc.
- `W2`: phiên bản mới ghi.
- `R2`: phiên bản mới đọc.

Bốn tổ hợp quan trọng:

| Payload | Reader | Mục tiêu |
|---|---|---|
| W1 | R1 | Baseline cũ hoạt động |
| W1 | R2 | **Backward-read:** phiên bản mới đọc được dữ liệu cũ |
| W2 | R2 | Phiên bản mới tự hoạt động |
| W2 | R1 | **Forward-read:** phiên bản cũ đọc được dữ liệu mới, cần cho rolling deploy hoặc rollback |

Trong hệ thống chỉ nâng đồng loạt và không rollback, W2→R1 có thể không xuất hiện. Nhưng nếu nhiều pod chạy đồng thời, một load balancer còn đưa request sang bản cũ, hoặc consumer cũ vẫn có thể nhận thông điệp mới, thì W2→R1 là tình huống thực tế.

Cần kiểm tra **mỗi producer/consumer độc lập**, không chỉ từng service. Một payload ghi bởi cache-writer v2 có thể được đọc bởi batch-job v1; một cookie phiên được cấp bởi frontend v2 có thể được xử lý bởi backend v1.

## 4. Kiểm kê các điểm lưu trạng thái

Trước khi sửa serializer hay schema, lập inventory:

| Thành phần | Nơi lưu | Writer | Reader | Định dạng | Thời gian sống | Rollback cần đọc? |
|---|---|---|---|---|---|---|
| Giá sản phẩm | Redis | Catalog v1/v2 | Catalog API | JSON schema v1 | 30 phút | Có |
| Hồ sơ người dùng | Redis | Account v1/v2 | Account API | JDK binary cũ | 6 giờ | Có |
| HTTP session | Redis/DB | Web nodes | Web nodes | Serializer framework | 12 giờ | Có |
| Refresh token | DB/identity service | Auth service | Auth service | Token/hash metadata | Nhiều ngày | Có |
| Sự kiện đơn hàng | Kafka topic | Order producer | Billing/Shipping | Avro v1 | 7 ngày | Có |
| Retry job | Durable queue | Batch worker | Batch worker | JSON job v2 | Tới khi hoàn tất | Có |
| Dead-letter event | DLQ | Broker/consumer | Replay tool | Nhiều schema | Có thể nhiều tháng | Phải xét riêng |

Thông tin quan trọng hơn tên kho là:

- Có những phiên bản nào **được phép đồng thời đọc/ghi**?
- Dữ liệu thuộc business source-of-truth hay chỉ là bản sao có thể tái tạo?
- TTL/retention có được thực thi thật không, hay một vài entry không bao giờ hết hạn?
- Có writer nào ngoài ứng dụng chính như cronjob, admin script, ETL hoặc service của đối tác?
- Data có chứa PII, session token, khóa bí mật hoặc thông tin nhạy cảm không?
- Dữ liệu có thể xóa an toàn không, hay việc xóa gây logout, mất job hoặc phá idempotency?

Không nên gộp “cache” và “queue” thành cùng một chính sách. Cache có thể được xóa rồi tái dựng trong một số trường hợp; thông điệp nghiệp vụ chưa xử lý có thể là nghĩa vụ cần hoàn tất và không được xóa.

## 5. Cache khi đổi JDK và phiên bản ứng dụng

Cache thường được coi là tối ưu hiệu năng, nhưng ảnh hưởng tương thích đôi khi rất lớn. Một cache miss có thể làm tăng tải database; một cache hit với payload cũ không tương thích có thể gây lỗi 500; một cache hit chứa dữ liệu semantic sai có thể dẫn tới quyết định nghiệp vụ không chính xác.

### 5.1. Phân loại cache theo rủi ro

- **Local in-memory cache:** bị mất khi process dừng, nhưng có thể tồn tại đồng thời trong các node v1/v2 và gây khác biệt behavior.
- **Distributed cache:** tồn tại độc lập với process, có thể được đọc bởi nhiều phiên bản.
- **Persistent cache:** file disk/snapshot còn qua restart/deploy, cần kiểm tra format/version và khả năng phục hồi.
- **Shared cross-service cache:** producer và consumer là các service khác nhau; sự thay đổi không còn là refactor nội bộ.
- **Derived cache:** có thể tái tạo từ database/source-of-truth.
- **Authority-like cache:** chứa token/session/rate-limit/idempotency state; xóa cache có thể làm mất kiểm soát hoặc thay đổi bảo mật.

Với derived cache đơn thuần, đổi key namespace hoặc invalidation là lựa chọn khả thi. Với session hoặc idempotency state, không được giả định xóa cache luôn an toàn.

### 5.2. Cache key cũng là schema

Một cache entry có hợp đồng gồm **key + value + TTL + semantic**:

~~~text
catalog:price:v1:sku-104
catalog:price:v2:sku-104
~~~

Hai key tương tự nhưng payload khác:

~~~json
{
  "schemaVersion": 1,
  "amount": 125000,
  "currency": "VND"
}
~~~

~~~json
{
  "schemaVersion": 2,
  "money": {
    "decimal": "125000",
    "currency": "VND"
  },
  "calculatedAt": "2026-11-12T08:00:00Z"
}
~~~

Nếu đổi cấu trúc value nhưng giữ key `catalog:price:sku-104`, reader cũ và reader mới có thể đọc nhầm format của nhau. Một cách giảm rủi ro là **version cache key** để hai định dạng không tranh chấp cùng vị trí.

Tuy vậy, đổi key làm cả hai bản cache cùng tồn tại và có thể tăng tải vào source-of-truth khi v2 lần đầu đọc. Cần tính cache warm-up, TTL, memory quota và khả năng giới hạn request.

### 5.3. Các chiến lược chuyển cache

**Chiến lược A — Reader mới hỗ trợ hai schema.** Giữ key hiện tại, R2 đọc được v1 và v2. Thích hợp khi khác biệt nhỏ, dữ liệu cũ vẫn đáng dùng và writer v2 không làm R1 hỏng trong thời gian chạy song song.

**Chiến lược B — Namespace/version mới.** V2 ghi `prefix:v2:...`, v1 dùng `prefix:v1:...`. Hai phiên bản tách biệt; v2 có thể fallback đọc v1 rồi chuyển đổi nếu dữ liệu nguồn và policy cho phép.

**Chiến lược C — Invalidate có kiểm soát.** Xóa dần các key thuộc phạm vi xác định và để chúng được tái tạo. Chỉ phù hợp khi dữ liệu là derived cache, có nguồn chuẩn và có khả năng chịu cache miss.

**Chiến lược D — Background migration.** Đọc entry v1, kiểm tra hợp lệ, chuyển sang schema v2 và ghi key mới. Cần tránh thay đổi semantic, xử lý write races và ghi lại progress.

**Chiến lược E — Bỏ qua dữ liệu cũ khi đọc.** Nếu reader nhận ra schema v1 không được hỗ trợ, coi entry như cache miss và fetch lại. Chỉ thực hiện cho những loại entry được phép tái tạo; không áp dụng cho session hoặc message cần xử lý.

### 5.4. Cách chọn theo dữ liệu

| Trạng thái | Có thể xóa để tái tạo? | Lựa chọn thường phù hợp |
|---|---|---|
| Cache HTTP response tạm | Thường có, nhưng cần tính tải | Key version, invalidate, TTL |
| Bảng tra cứu derived từ DB | Có nếu DB chịu được tải | Schema-aware read hoặc rebuild |
| Giá trong quy trình thanh toán | Cần xét consistency và thời điểm chốt giá | Hợp đồng rõ, không silent fallback |
| Session lưu trong Redis | Không nên xóa đại trà | Reader tương thích + session migration |
| Distributed lock | Xóa nguy hiểm | Giữ key/TTL semantics, kiểm thử concurrency |
| Idempotency key | Xóa có thể tạo duplicate | Giữ thời hạn và semantics cho replay |
| Event trong queue | Không phải cache | Versioned message + consumer compatibility |

## 6. Java Serialization và rủi ro cache nhị phân

Một số ứng dụng cũ lưu Java object trực tiếp bằng `ObjectOutputStream`, Java serialization serializer của framework hoặc hệ thống session replication. Cách này làm dữ liệu phụ thuộc chặt vào **binary class name, serialVersionUID, cấu trúc field và classpath của reader**.

Ví dụ lớp cũ:

~~~java
package com.acme.session;

import java.io.Serializable;

public final class CartSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String cartId;
    private int quantity;
}
~~~

Nếu phiên bản mới đổi package thành `com.acme.checkout.CartSnapshot`, thì serialized payload cũ vẫn tham chiếu tới tên lớp cũ. Dù field mới giống hệt, deserializer có thể không tìm thấy class và báo `ClassNotFoundException`.

Nếu lớp vẫn cùng tên nhưng `serialVersionUID` được thay không tương thích, có thể nhận:

~~~text
java.io.InvalidClassException
~~~

Nếu đổi kiểu field, hierarchy hoặc cấu trúc serialization theo cách không tương thích, có thể phát sinh lỗi khác hoặc kết quả không như mong đợi. Không nên dùng một `serialVersionUID` cố định như “bảo đảm mọi thay đổi đều tương thích”. Nó chỉ là một phần của cơ chế kiểm tra version khi Java deserialization.

### 6.1. Thay đổi field không chỉ là chuyện thêm/bớt

Với Java object serialization mặc định, một số trường hợp thêm field mới có thể được deserializer cũ/bản mới xử lý theo quy tắc compatibility. Nhưng:

- Field mới có thể nhận giá trị mặc định `null`, `0` hoặc `false` khi đọc stream cũ.
- Business invariant mới có thể không còn được bảo đảm.
- Class đã đổi tên/package không tự ánh xạ sang tên mới.
- Externalizable/custom `readObject`/`writeObject` có logic và contract riêng.
- Field `transient` không được serialize theo cách mặc định.
- Hệ sinh thái proxy, ORM enhancement và class loader có thể làm compatibility phức tạp hơn.

Ví dụ thêm `currency` vào `CartSnapshot`: payload v1 không có `currency`; reader v2 phải quyết định có thể dùng giá trị mặc định hay phải truy xuất thông tin từ source-of-truth. Gán bừa `"USD"` khi dữ liệu cũ thực tế là VND là lỗi semantic dù không có exception.

### 6.2. Không deserialise Java object từ dữ liệu không tin cậy

Java native deserialization có rủi ro bảo mật khi xử lý stream do bên không tin cậy kiểm soát. Dữ liệu cache/message có thể thuộc hệ thống tin cậy nhưng vẫn cần đánh giá khả năng bị sửa, quyền ghi kho dữ liệu và type allowlist.

Với các trường hợp buộc phải đọc binary cũ:

- Giới hạn nguồn và quyền ghi của dữ liệu.
- Áp dụng serialization filtering theo API và cấu hình JDK hỗ trợ, ví dụ `ObjectInputFilter`, với allowlist/giới hạn phù hợp.
- Tránh nạp các class không cần thiết.
- Không tự động chấp nhận mọi type chỉ để migration thành công.
- Lên kế hoạch chuyển sang format có schema rõ, ví dụ JSON, Avro hoặc Protobuf, nếu đó là hợp đồng lưu dài hạn.

Nếu mục tiêu là “đọc dữ liệu tồn tại sau deploy”, format độc lập với implementation class thường dễ quản trị hơn Java serialized object.

## 7. Thiết kế payload cache có schemaVersion

Một cách giảm coupling là dùng **data transfer object và định dạng được quản lý**. Ví dụ payload JSON:

~~~json
{
  "schemaVersion": 2,
  "cacheKey": "customer:981",
  "cachedAt": "2026-11-12T08:20:00Z",
  "expiresAt": "2026-11-12T08:50:00Z",
  "value": {
    "customerId": "981",
    "status": "ACTIVE"
  }
}
~~~

Reader cần biết:

- Thiếu `schemaVersion` có được coi là v1 không, hay là payload lỗi?
- Version nào đang được hỗ trợ?
- Field có thể vắng mặt không?
- Unknown field/enum được xử lý thế nào?
- Timestamp dùng UTC ISO-8601 hay epoch unit nào?
- TTL ở storage có khớp `expiresAt` trong payload không?

Mã minh họa hướng xử lý (pseudocode, không ràng buộc thư viện JSON cụ thể):

~~~java
CacheValue readCache(byte[] bytes) {
    JsonObject json = jsonCodec.decode(bytes);
    int version = json.getInt("schemaVersion", 1);

    switch (version) {
        case 1:
            return migrateV1ToCurrent(json);
        case 2:
            return parseCurrent(json);
        default:
            throw new UnsupportedSchemaVersionException(version);
    }
}
~~~

Trong cache derived, `UnsupportedSchemaVersionException` có thể được chuyển thành cache miss và truy xuất source-of-truth. Trong session hoặc dữ liệu nghiệp vụ mang nghĩa bắt buộc, không được tự nuốt lỗi và tạo state rỗng.

### 7.1. Đọc cũ, ghi mới

Cách thường dùng trong giai đoạn chuyển là:

~~~text
                 Reader v2
                    |
          +---------+---------+
          |                   |
       Payload v1          Payload v2
          |                   |
      Parse v1            Parse v2
          |                   |
      Normalize --------------+
                    |
             Internal model v2
                    |
              Writer v2
~~~

Reader v2 tiếp tục hỗ trợ v1 trong khoảng thời gian đã được đo/định nghĩa. Writer v2 có thể bắt đầu ghi format mới **chỉ sau khi** mọi consumer vẫn có thể nhận dữ liệu này đã được nâng hoặc có compatibility bridge.

### 7.2. Đừng chuyển lỗi schema thành cache stampede

Nếu nhiều request cùng gặp hàng nghìn cache entry cũ không đọc được và đồng loạt fetch DB, hệ thống có thể bị overload. Cần:

- Coalesce/single-flight các request cho cùng key.
- Giới hạn concurrency và rate truy cập source-of-truth.
- Dùng TTL jitter để tránh hàng loạt key hết hạn cùng thời điểm.
- Warm-up các cache nóng trước rollout.
- Đo cache hit/miss, deserialize error và latency.
- Có phương án ngăn ghi schema mới bằng feature flag khi cần rollback.

## 8. TTL, expiration và khái niệm “đã hết dữ liệu cũ”

Không thể kết luận “deploy xong một giờ thì mọi cache cũ đã biến mất” nếu không biết TTL thực tế.

Các trạng thái có thể tồn tại lâu hơn dự kiến:

- Key không có TTL do bug hoặc được ghi bằng lệnh không đặt expiration.
- TTL được gia hạn khi truy cập (sliding expiration).
- Một job hoặc node v1 vẫn tiếp tục ghi định dạng cũ.
- Backup/restore đưa dữ liệu cũ trở lại.
- Client cache local giữ bản sao lâu hơn distributed cache.
- Dead-letter queue hoặc retry job chứa payload không có thời hạn tối đa rõ ràng.

Với Redis, các thao tác quan sát key và TTL nên dùng trên key cụ thể được cho phép:

~~~text
TTL catalog:price:v1:sku-104
PTTL catalog:price:v1:sku-104
TYPE catalog:price:v1:sku-104
~~~

Không khuyến khích quét hoặc xóa đại trà key production chỉ để tìm dữ liệu cũ. Các thao tác như `KEYS *` trên một Redis lớn có thể gây tác động vận hành; việc xóa cần có phạm vi, backup và kế hoạch được phê duyệt.

Mốc “ngừng hỗ trợ schema v1” phải dựa trên **thời gian sống tối đa thực tế + thời gian còn writer cũ + chính sách replay/restore**, không chỉ dựa vào mặc định TTL trong source code.

## 9. Phiên đăng nhập HTTP tồn tại qua rolling deployment

Với ứng dụng web, người dùng có thể đăng nhập trước khi deploy rồi tiếp tục gửi request sau khi service mới được bật. Nếu trạng thái phiên được lưu ở server hoặc kho dùng chung, phiên đó có thể do **v1 tạo nhưng v2 đọc**.

Những dạng session phổ biến:

- **In-memory `HttpSession` tại một node:** có thể mất khi node dừng, hoặc được replicate tùy application server.
- **Distributed session** trong Redis/DB: được nhiều node truy cập và tồn tại qua restart.
- **Sticky session:** load balancer ưu tiên cùng node, nhưng failover/rolling deploy vẫn làm thay đổi node xử lý.
- **Opaque session token:** cookie chỉ chứa session identifier, state được giữ ở server.
- **Signed/encrypted cookie hoặc JWT:** một phần hoặc toàn bộ claim nằm phía client, tiếp tục được gửi sau khi phiên bản phát hành đã thay đổi.
- **Refresh token/SSO session:** có thời gian sống dài và phụ thuộc identity provider/authorization server.

Không nên đánh đồng **HTTP session**, **access token**, **refresh token** và **business workflow state**. Chúng có vòng đời, quyền truy cập và yêu cầu migration khác nhau.

### 9.1. Session chứa đối tượng Java cũ

Ví dụ code cũ:

~~~java
HttpSession session = request.getSession();
session.setAttribute("currentUser", userEntity);
~~~

Nếu `userEntity` là entity Hibernate hoặc object Java phụ thuộc vào implementation class, serialized session có thể gắn với class name, `serialVersionUID`, lazy proxies và framework version. Khi deploy v2, session store vẫn chứa object v1.

Lỗi có thể phát sinh khi:

- Session được deserialize trên node mới.
- Framework đổi serializer mặc định.
- Class bị đổi tên hoặc property không còn tương thích.
- Class loader của application server không tìm thấy class cũ.
- Session contains non-serializable object khi replication được kích hoạt.
- Session chứa dữ liệu nhạy cảm không nên lưu hoặc cần revalidation.

### 9.2. Lưu session DTO ổn định thay vì object nghiệp vụ

Một thiết kế dễ migration hơn là giữ session attributes nhỏ, dựa trên primitive/string và định dạng có schema:

~~~java
public final class SessionProfile implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String userId;
    private String localeTag;
    private int schemaVersion;

    public SessionProfile(String userId, String localeTag) {
        this.userId = userId;
        this.localeTag = localeTag;
        this.schemaVersion = 1;
    }

    // Getters và validation theo hợp đồng của ứng dụng.
}
~~~

Ví dụ trên vẫn dùng Java serialization để minh họa DTO, không phải khuyến nghị tuyệt đối sử dụng serialization cho distributed session. Với Redis hoặc database-backed session, JSON/format có schema riêng thường làm ranh giới dữ liệu rõ ràng hơn nếu hệ thống hỗ trợ.

Tránh lưu raw password, private key, credential dài hạn hoặc toàn bộ entity graph vào session. Ưu tiên ID và dữ liệu tối thiểu; lấy dữ liệu nghiệp vụ mới từ source-of-truth khi cần.

### 9.3. Session expiry, cookie và bảo mật

Ngoài serializer, migration có thể thay đổi:

- Session timeout và sliding expiration.
- Cookie name, domain, path, `SameSite`, `Secure`, `HttpOnly`.
- Key ký/mã hóa cookie và lộ trình key rotation.
- Session ID regeneration sau login hoặc đổi quyền.
- Cơ chế logout/invalidation trên nhiều node.
- CSRF token lưu trong session.
- Principal/authority claims khi nâng security framework.
- Session fixation protection và cách khôi phục session sau restart.

Một v2 không đọc được session v1 có thể tạo logout hàng loạt. Điều này đôi khi là quyết định chấp nhận được, nhưng **phải là quyết định sản phẩm/bảo mật được công bố**, không phải hậu quả ngẫu nhiên của migration.

Nếu cả v1/v2 đang chạy, thay đổi cookie name hoặc secret có thể làm người dùng bị chuyển qua lại giữa hai trạng thái xác thực. Cần thiết kế giai đoạn đọc hai key/format có giới hạn, hoặc rollout theo user cohort nếu khả thi.

## 10. Token được phát hành trước deploy

JWT và token tự chứa không được deserialize giống Java object trong Redis, nhưng vẫn là **thông điệp tồn tại qua lần triển khai**. Một access token được cấp lúc 09:00 có thể được API v2 kiểm tra lúc 09:15.

Cần kiểm tra:

- `iss`, `aud`, `sub`, `exp`, `nbf` và clock skew.
- Algorithm được phép và key ID như `kid`.
- Key rotation có overlap đủ để xác minh token cũ đến khi hết hạn không.
- Claim mới có làm consumer cũ hiểu sai vai trò/quyền không.
- Consumer cũ có bỏ qua claim mới hay cần một schema version tường minh?
- Refresh tokens/SSO sessions có thể tồn tại dài hơn access tokens.
- Revocation/logout policy có còn nhất quán không?

Không hạ kiểm tra chữ ký, bỏ qua `aud` hoặc chấp nhận algorithm yếu chỉ để “giữ đăng nhập” khi nâng JDK. Nếu buộc phải hết phiên vì thay security contract, phải có kế hoạch UX, số lượng người dùng ảnh hưởng và thông báo rõ ràng.

## 11. Message queue và các thông điệp chưa được xử lý

Khác với cache, thông điệp trong broker thường biểu thị một sự kiện hoặc yêu cầu cần xử lý. Nó có thể được phát bởi producer v1 nhưng chỉ được consumer v2 đọc do backlog kéo dài qua thời điểm deploy.

Ví dụ:

~~~text
Producer v1 -- order.created(v1) --> Topic/Queue --> Consumer v2
Producer v2 -- order.created(v2) --> Topic/Queue --> Consumer v1
                            |
                      Retry / DLQ
                            |
                   Replay sau nhiều ngày
~~~

Tập dữ liệu cần xét gồm:

- Messages chưa được consume.
- Messages đang xử lý khi process bị thay.
- Messages đã được ack nhưng còn outbox/dedup state.
- Retry messages có delay.
- Dead-letter messages chờ điều tra và replay.
- Events được lưu trong Kafka log để consumer mới đọc từ offset cũ.
- Snapshots/checkpoints của stream processor hoặc materialized view.
- Batch jobs được lên lịch trước khi triển khai.

Một message schema chỉ tương thích trong phiên bản mới không bảo đảm hệ thống an toàn nếu còn **consumer cũ** hoặc công cụ replay chưa nâng.

## 12. Version hóa message envelope và payload

Một contract message nên tách metadata định tuyến khỏi payload nghiệp vụ:

~~~json
{
  "messageId": "8d30cc13-a53c-4d9a-9c14-f2a61b20bda1",
  "eventType": "order.created",
  "schemaVersion": 2,
  "occurredAt": "2026-11-12T08:10:00Z",
  "producer": "order-service",
  "payload": {
    "orderId": "O-18025",
    "total": {
      "amount": "125000.00",
      "currency": "VND"
    },
    "items": [
      {"sku": "P-104", "quantity": 2}
    ]
  }
}
~~~

Những trường thường hữu ích:

| Trường | Mục đích |
|---|---|
| `messageId` | Nhận diện message, phục vụ dedup/idempotency |
| `eventType` | Chỉ định loại sự kiện, tránh đoán qua field |
| `schemaVersion` | Chọn parser/adapter cho payload |
| `occurredAt` | Thời điểm sự kiện xảy ra theo chuẩn đã định |
| `producer` | Truy vết nguồn phát, không phải cơ chế trust duy nhất |
| `correlationId` | Theo dõi workflow/request nhiều service |
| `payload` | Dữ liệu nghiệp vụ theo schema cụ thể |
| `trace metadata` | Liên kết logging/tracing khi phù hợp |

Không phải mọi hệ thống cần mọi field ở dạng này; Kafka headers, schema registry hoặc framework messaging có thể lưu metadata riêng. Nhưng phải có **một hợp đồng version và identity rõ ràng**, không chỉ suy đoán phiên bản từ việc field có tồn tại hay không.

### 12.1. Phân biệt version của event và version ứng dụng

`schemaVersion=2` không có nghĩa message chỉ hợp lệ trên “app version 2” hoặc “Java 21”. Một schema version có thể được nhiều phiên bản producer/consumer hỗ trợ. Version là thuộc tính của **hợp đồng dữ liệu**, không nên đồng nhất với JDK runtime.

Khi nâng JDK mà message schema không đổi, vẫn cần kiểm tra serializer library và classpath/provider. Khi đổi schema nhưng giữ JDK, vẫn cần test compatibility tương tự.

### 12.2. Thay đổi thường tương thích và thường phá vỡ

| Thay đổi schema | Rủi ro | Cách giảm rủi ro |
|---|---|---|
| Thêm optional field có default | Thường dễ hỗ trợ | Consumer cũ bỏ qua unknown field theo hợp đồng |
| Thêm required field không default | Reader mới không đọc payload cũ | Chuyển field thành optional, đặt default hoặc adapter v1 |
| Đổi kiểu `number` sang `string` | Parser/consumer không còn đúng | Chuyển theo version, có giai đoạn chuyển đổi |
| Đổi tên field | Consumer cũ không tìm thấy | Alias đọc trong giai đoạn chuyển |
| Đổi semantic cùng kiểu | Dễ gây sai nghiệp vụ âm thầm | Version schema, contract test và migration |
| Thêm enum value | Consumer cũ có thể crash hoặc default sai | Unknown-value strategy |
| Xóa field | Consumer cũ cần field sẽ thất bại | Deprecate trước, đo usage, chỉ xóa khi hết consumer cũ |
| Đổi timestamp unit | Parse được nhưng sai thời gian | Contract unit cụ thể, test boundary |
| Đổi key/order cho Kafka | Có thể thay đổi partition/ordering | Đánh giá luồng xử lý theo entity |

Không kết luận máy móc rằng “JSON thêm field luôn backward compatible”. Điều đó chỉ đúng nếu reader và schema thực tế cho phép unknown field, và field mới không phá semantic.

## 13. JSON, Avro, Protobuf và Java binary messages

### 13.1. JSON

JSON có khả năng đọc/ghi giữa nhiều ngôn ngữ, nhưng không tự đảm bảo schema compatibility. Các Jackson/Gson settings như fail on unknown properties, null handling, polymorphic type metadata, date/time serialization hoặc case sensitivity có thể thay đổi giữa framework versions.

Một message có:

~~~json
{"status":"PENDING"}
~~~

không tự bảo đảm parser mới sẽ biết cách xử lý:

~~~json
{"status":"AWAITING_REVIEW"}
~~~

Nếu code dùng:

~~~java
Status.valueOf(statusFromMessage)
~~~

thì enum value mới sẽ gây `IllegalArgumentException` khi reader cũ chưa khai báo. Có thể dùng parser có nhánh unknown rõ ràng, đưa message không hỗ trợ vào một luồng xử lý an toàn hoặc chặn producer phát enum mới cho tới khi consumer được nâng.

### 13.2. Avro

Avro hỗ trợ schema evolution theo các quy tắc có cấu trúc, ví dụ reader schema/writer schema, field default, union và compatibility mode. Nhưng compatibility phụ thuộc schema registry/configuration cùng encoding thực tế, không phải chỉ vì payload dùng Avro.

Nếu topic dùng schema registry, cần xác minh:

- Subject naming strategy.
- Compatibility mode được cấu hình, ví dụ backward/forward/full khi phù hợp.
- Reader/writer schema versions được hỗ trợ.
- Consumer còn chạy và các event có thể được replay.
- Có schema migration tool hoặc state-store format phụ thuộc version không.

### 13.3. Protocol Buffers

Protobuf có thể duy trì tương thích tốt khi tuân thủ quy tắc field numbers và wire types. Tuy nhiên, đổi field number, tái sử dụng số field đã xóa hoặc thay semantic không kiểm soát có thể phá contract.

Các nguyên tắc quan trọng:

- Không tái sử dụng field number đã được công bố.
- Dùng `reserved` cho những field number/name đã bị loại nếu phù hợp schema.
- Kiểm tra enum unknown values và default semantics.
- Kiểm tra version `protoc`, generated classes và runtime library.
- Đảm bảo consumer cũ có thể bỏ qua field mới theo contract.
- Kiểm tra thay đổi ảnh hưởng binary/source API của generated Java code.

### 13.4. Java native serialization cho messages

Nếu message payload là `Serializable` object hoặc một framework binary serializer gắn với FQCN, lỗi có thể xuất hiện khi nâng JDK, đổi class hierarchy hoặc đổi dependency version. Đây là vấn đề tương tự cache/session nhưng thường nguy hiểm hơn vì dữ liệu message có thể không được phép bỏ qua.

Với contract sống lâu hoặc có nhiều producer/consumer, ưu tiên schema và encoding được quản lý độc lập với implementation class. Nếu phải giữ binary cũ, dựng compatibility reader có giới hạn và kế hoạch chuyển đổi riêng, tránh yêu cầu producer mới phát payload mà consumer cũ không thể hiểu.

## 14. Thứ tự rollout: nâng reader trước writer

Với message schema hoặc shared state schema, một nguyên tắc hữu ích là **reader hỗ trợ mới trước khi writer phát mới**.

~~~text
T0:  Producer v1 -> schema v1 -> Consumer v1

T1:  Producer v1 -> schema v1 -> Consumer v2
     (Consumer v2 đọc được cả v1 và v2)

T2:  Producer v2 -> schema v2 -> Consumer v2
     (Chỉ bật schema v2 khi không còn consumer v1 không tương thích)

T3:  Chờ hết retention/retry/replay cần hỗ trợ schema v1

T4:  Loại parser v1 nếu không còn nguồn dữ liệu cũ
~~~

Đây là mẫu **expand–migrate–contract**:

1. **Expand:** mở rộng reader và schema để hỗ trợ phiên bản cũ lẫn mới.
2. **Migrate:** chuyển writer, dữ liệu tồn đọng và các consumer sang định dạng mới.
3. **Contract:** ngừng ghi v1, chờ dữ liệu v1 hết vòng đời, rồi mới xóa compatibility code.

Với **rollback**, thứ tự có thể phức tạp hơn. Nếu producer v2 đã phát schema v2 mà consumer v1 không hiểu, rollback chỉ riêng consumer về v1 có thể tạo lỗi. Phải chọn một trong các giải pháp: giữ consumer v2 đọc được schema v2, dùng message contract v1 trong cửa sổ rollback, hoặc bảo đảm bridge/adapter.

## 15. Dual-read, dual-write và biến thể migration

### 15.1. Dual-read

Reader mới thử đọc schema mới; nếu gặp payload v1 được nhận diện rõ, dùng adapter chuyển vào domain model hiện tại.

~~~text
Reader v2
  -> detect schemaVersion
  -> parse v1 / parse v2
  -> normalize to internal model
  -> validate business invariants
  -> execute operation
~~~

Cần phân biệt **payload hợp lệ của v1** với **payload bị hỏng**. Không nên coi mọi parse failure là v1 rồi fallback vô điều kiện, vì điều đó có thể che dữ liệu đã bị corrupt hoặc bị sửa trái phép.

### 15.2. Dual-write

Trong một số chuyển đổi cache hoặc state store, phiên bản mới ghi cả format v1 và v2. Cách này giúp reader cũ không bị bỏ lại phía sau, nhưng có rủi ro:

- Hai bản ghi không được cập nhật nguyên tử.
- Ghi v1 thành công, v2 thất bại hoặc ngược lại.
- Không rõ bản nào là nguồn chuẩn.
- TTL không đồng bộ.
- Khối lượng ghi và chi phí lưu trữ tăng.
- Dữ liệu nhạy cảm bị nhân bản, tạo thêm rủi ro bảo mật.

Chỉ dùng dual-write khi có chính sách consistency và retry cụ thể. Với event nghiệp vụ, phát song song hai message cho cùng hành động có thể khiến consumer thực hiện hai lần. Khi cần chuyển event format, dùng adapter hoặc định tuyến version được thiết kế rõ, có idempotency/dedup.

### 15.3. Shadow-read và canary

Một kỹ thuật giảm rủi ro là để phiên bản mới đọc dữ liệu v1 trong **shadow mode** nhưng chưa dùng kết quả để quyết định nghiệp vụ. So sánh parse result, schema validation và latency với reader cũ. Không ghi log payload chứa PII hoặc token để đối chiếu.

Canary rollout cho phép một nhóm nhỏ traffic/session được xử lý bởi v2 trước khi mở rộng. Tuy nhiên, với shared cache hoặc queue, canary writer có thể phát dữ liệu v2 tới tất cả consumer, bao gồm v1. Vì vậy **canary application không tự cô lập data contract**: cần versioned namespace, riêng topic/queue hoặc feature flag cho writer.

## 16. Retry, redelivery, idempotency và thông điệp đến trễ

Broker và consumer thường có cơ chế at-least-once delivery. Một message có thể được gửi lại sau timeout, crash hoặc retry. Tăng phiên bản ứng dụng không làm mất khả năng redelivery.

Cần thiết kế consumer sao cho một sự kiện được xử lý lặp lại không tạo thêm tác dụng phụ ngoài ý muốn.

Ví dụ message:

~~~json
{
  "messageId": "41e64ab9-3313-4311-8d2d-99162808b9bd",
  "schemaVersion": 1,
  "eventType": "payment.authorized",
  "payload": {
    "paymentId": "PM-309",
    "orderId": "O-18025"
  }
}
~~~

Consumer có thể lưu `messageId` trong inbox/dedup table và thực hiện nghiệp vụ theo một giao dịch phù hợp. Khi deploy v2, **không được xóa dedup state** chỉ vì thay service version; nếu không, message v1 được retry có thể được xử lý lần hai.

### 16.1. “Exactly once” cần giới hạn theo phạm vi

Một nền tảng streaming có thể cung cấp cơ chế exactly-once cho một số thao tác nội bộ nhưng không mặc nhiên bảo đảm tác dụng phụ ở database, cổng thanh toán hoặc API bên ngoài chỉ xảy ra đúng một lần. Cần xét idempotent key, transaction boundaries và replay semantics.

### 16.2. Ordering và message key

Một message mới có thể đổi cách tính partition key hoặc grouping. Dù schema đọc được, thứ tự xử lý của các sự kiện cùng entity có thể thay đổi. Ví dụ `order.created` và `order.cancelled` có thể tới consumer khác nhau hoặc bị đảo nếu thay partition strategy.

Khi migration, giữ ổn định business key nếu hợp đồng ordering dựa vào key đó, hoặc thiết kế lại theo một rollout riêng có kiểm thử concurrency.

### 16.3. Dead-letter queue là kho dữ liệu lịch sử

DLQ đôi khi lưu payload nhiều tuần hoặc nhiều tháng. Khi replay, tool hiện tại phải đọc được các schema cũ hoặc có migration job.

Không xóa parser v1 chỉ vì topic chính hết v1. Cần kiểm kê cả DLQ, retries, backups, reprocessing jobs và event archives. Với poison message, cần tách lỗi schema khỏi lỗi nghiệp vụ để không tạo vòng retry vô hạn.

## 17. Transactional outbox và dữ liệu chờ phát

Một pattern phổ biến là ghi business change và outbox event vào cùng database transaction, sau đó relay gửi event tới broker.

~~~text
Business transaction
  -> update order table
  -> insert outbox row (schema v1)
  -> commit
           |
           v
     Outbox relay v2
           |
           v
       Event broker
           |
           v
      Consumer v2
~~~

Nếu relay nâng lên v2, nó có thể gặp outbox rows v1 chưa phát. Khi đó relay phải biết cách đọc và phát đúng hợp đồng của các hàng cũ. Nếu relay tự động serialize lại mọi row thành schema v2, cần kiểm tra rằng consumer cũ/đối tác có thể chấp nhận.

Các thuộc tính outbox cần theo dõi:

- Payload schema version.
- Message ID/idempotency key.
- Trạng thái phát, retry count, next attempt time.
- Thứ tự theo aggregate/business key nếu cần.
- Transaction boundary và nguyên tắc không mất/không nhân đôi event.
- Thời gian giữ outbox rows và khả năng replay.

Cũng cần kiểm tra inbox/dedup table qua migration; xóa hoặc đổi key format có thể làm xử lý lặp lại message cũ.

## 18. Cache/session/message có các cửa sổ thời gian khác nhau

Một sai lầm vận hành là chọn cùng một mốc “đợi 24 giờ rồi xóa compatibility layer” cho mọi loại state.

| Loại dữ liệu | Yếu tố chi phối thời gian sống | Cách xác minh dữ liệu cũ không còn |
|---|---|---|
| Derived cache | TTL, refresh, old writers, restore | Quan sát versioned key, TTL, traffic, nguồn ghi |
| Session | Idle timeout, max lifetime, refresh, user activity | Số phiên theo schema version, logout/reissue policy |
| Access token | `exp`, key overlap, clock skew | Metrics xác minh theo `kid`/token version |
| Refresh token | Chính sách rotation/revocation | Inventory token metadata và thời hạn tối đa |
| Broker event | Retention, consumer lag, replay | Offset, schema distribution, backlog, DLQ |
| Delayed/retry message | Delay tối đa, retry backoff, manual replay | Retry queue/DLQ metrics và policy |
| Outbox | Relay lag, retry và manual recovery | Hàng pending theo schema version |
| Backup/snapshot | Retention và restore policy | Test restore bằng reader hiện tại |

Mốc gỡ reader v1 phải là quyết định dựa trên **các nguồn dữ liệu thực sự có thể tái xuất hiện**, không chỉ thời điểm deployment v2 hoàn tất.

## 19. Kiểm thử bằng fixture dữ liệu thật nhưng an toàn

Để chứng minh compatibility, cần một bộ **golden fixtures** đại diện cho dữ liệu đã phát hành trước đó. Mỗi fixture nên lưu:

- Producer version/JDK/vendor hoặc build ID nếu có.
- Serializer và schema version.
- Payload đã loại bỏ hoặc giả lập PII/secrets an toàn.
- Kỳ vọng sau parse: domain values, default, validation result.
- Hành vi khi gặp unknown field/enum, missing field hoặc corrupted data.
- Mốc thời gian/TTL/expiration phù hợp.
- Trường hợp có khả năng rollback hoặc replay.

Ví dụ cấu trúc fixture của một bài test:

~~~text
fixtures/
  cache/
    price-v1.json
    price-v2.json
    cart-java8.ser
  sessions/
    anonymous-v1.json
    authenticated-v1.json
    expired-session-v1.json
  messages/
    order-created-v1.json
    order-created-v2.json
    order-cancelled-legacy.json
    unknown-enum-v2.json
~~~

Đây là ví dụ tổ chức test artifacts, không phải yêu cầu đưa raw session token hoặc binary chứa private data vào repository. Nếu fixture là Java serialized binary, nên tự tạo dữ liệu giả trong môi trường cô lập và không deserialize nội dung lấy từ nguồn không tin cậy.

### 19.1. Ma trận test tối thiểu

| Test | Input | Reader/runtime | Kỳ vọng |
|---|---|---|---|
| Cache v1 đọc bằng v2 | Fixture cache cũ | App v2/JDK mới | Đọc đúng hoặc cache miss có kiểm soát |
| Cache v2 đọc bằng v1 | Fixture cache mới | App v1/JDK cũ | Pass nếu rolling/rollback yêu cầu |
| Session cũ trên node mới | Session do v1 tạo | App v2 | Vẫn xác thực, expiry đúng |
| Session sau key rotation | Token/key cũ | Auth v2 | Xác minh trong overlap window |
| Event cũ chờ tiêu thụ | Event v1 | Consumer v2 | Xử lý đúng, không lặp tác dụng phụ |
| Event mới gặp consumer cũ | Event v2 | Consumer v1 | Chỉ cho phép nếu contract tương thích |
| Replay từ DLQ | Message v1 | Replay tool mới | Đọc/định tuyến/ack đúng |
| Outbox pending | Row v1 | Relay v2 | Phát đúng một message logic theo policy |
| Corrupted/unknown schema | Payload lỗi | Reader v2 | Có lỗi có kiểm soát, không silent corruption |
| Mixed deployment | W1/W2 và R1/R2 | Cluster hỗn hợp | Không mất phiên, không ghi sai format |

Test phải phân biệt **mong đợi pass** và **mong đợi fail an toàn**. Ví dụ unknown schema có thể phải bị reject hoặc chuyển vào DLQ, không phải luôn được parse tiếp.

### 19.2. Kiểm thử cấp hệ thống

Một bài integration test có giá trị:

1. Khởi chạy v1 với Redis/broker/test database dùng thật.
2. Cho v1 ghi cache, tạo session, phát event v1 và để một số message chưa consume.
3. Dừng một phần v1 hoặc đưa v2 vào trong khi dữ liệu vẫn còn.
4. Cho v2 đọc những key/session/message cũ.
5. Tiếp tục chạy v1 và v2 đồng thời nếu rollout thật có giai đoạn mixed version.
6. Cho v2 ghi dữ liệu mới, kiểm tra v1 có đọc được khi yêu cầu.
7. Dừng v1, để backlog/retry/DLQ còn tồn tại, chạy replay v2.
8. Thử rollback theo artifact và schema contract đã công bố.
9. So sánh kết quả nghiệp vụ và số lượng message trước/sau.
10. Lưu logs/metrics đã ẩn dữ liệu nhạy cảm.

Nếu chỉ chạy unit tests với object mới được tạo bởi code v2, sẽ bỏ qua phần lớn vấn đề “trạng thái còn tồn tại qua deployment”.

## 20. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân cần khảo sát | Bằng chứng hữu ích |
|---|---|---|
| `InvalidClassException` khi đọc cache/session | Java serialization class evolution hoặc UID không phù hợp | Binary fixture, class name, `serialVersionUID` |
| `ClassNotFoundException` khi deserialize | Class đổi package, dependency thiếu, loader khác | Tên trong stream, classpath, defining loader |
| JSON mapping exception | Field/type/enum thay đổi, mapper config khác | Payload schema version và mapper settings |
| Cache miss tăng đột ngột | Key namespace đổi, TTL/invalidation, decode fail | Hit/miss metric theo schema, source load |
| User logout sau deploy | Session serializer, cookie/key rotation hoặc store config | Session read failures, cookie attrs, key IDs |
| Lỗi chỉ xảy ra khi pod v1 và v2 cùng chạy | Two-way compatibility chưa có | W1/R2, W2/R1 test |
| Kafka consumer lag tăng | Parser/schema error hoặc xử lý chậm | Error rate, partition offsets, retries |
| DLQ tăng sau release | Unknown event version/field hoặc business validation | DLQ reason/category và schema distribution |
| Event bị xử lý hai lần | Retry, dedup state bị xóa hoặc key đổi | Message IDs, inbox record, side-effect log |
| Outbox phát sai format | Relay v2 đọc hàng v1 theo logic v2 | Outbox schema metadata và payload |
| Số tiền/thời điểm sai mà không exception | Semantic contract đổi đơn vị/default | Golden fixture semantic assertions |
| Rollback thất bại | v1 không đọc được dữ liệu v2 | Forward-read compatibility results |

Nên phân loại lỗi theo **trạng thái nguồn gốc và contract**. Không “fix” mọi lỗi bằng cách xóa Redis, bỏ qua unknown fields hoặc tăng retry vô hạn. Những workaround đó có thể che mất dữ liệu nghiệp vụ hoặc tạo tải đột biến.

## 21. Quan sát trong production sau deploy

Các metrics hữu ích:

**Cache**
- Hits, misses, deserialize errors, stale reads theo cache schema version.
- Số key từng namespace, TTL distribution (theo khả năng thu thập an toàn).
- Redis memory, eviction, latency, source-of-truth fallback load.
- Tỷ lệ writer v1 còn xuất hiện trong cửa sổ mixed deployment.

**Session và authentication**
- Số phiên được tạo/đọc theo schema version.
- Session deserialize failure.
- Tỷ lệ login, logout ngoài ý muốn, 401/403 theo deployment version.
- Session expiry, refresh và key rotation usage.
- Sự cố lựa chọn node sticky/replication/failover.

**Message**
- Consumer lag, backlog và processing latency theo topic/partition.
- Schema-version distribution của message được tiêu thụ.
- Retry/negative-ack/DLQ counts theo loại nguyên nhân.
- Dedup hit rate, duplicate business operations và outbox pending count.
- Replay attempts, poison messages và thời gian xử lý tối đa.

**Bảo mật và dữ liệu**
- Số token/signature cũ vẫn được xác minh trong overlap window.
- Lỗi decrypt/verify, policy violations và thay đổi trust keys.
- Không đưa payload chứa PII, token hoặc secret vào logs chỉ để tăng quan sát.

Một dashboard chỉ xem HTTP 5xx là chưa đủ: consumer lỗi ở background có thể không tạo HTTP response nào, nhưng backlog và DLQ tăng liên tục.

## 22. Cách quyết định “giữ tương thích hay xóa dữ liệu cũ”

Không có câu trả lời duy nhất. Cần cân nhắc giá trị dữ liệu, khả năng tái tạo, tính bảo mật, downtime cho phép và cam kết với người dùng.

### Có thể invalidate/rebuild khi

- Dữ liệu thuần cache, không phải nguồn chân lý.
- Source-of-truth còn đầy đủ và có thể chịu tải tái dựng.
- Cửa sổ stale data và performance degradation được chấp nhận.
- Việc xóa không làm mất session, lock, idempotency hay job.
- Có kế hoạch thực thi theo key prefix/partition được kiểm soát.

### Cần reader tương thích khi

- Session của người dùng phải còn hiệu lực qua deploy.
- Message cũ bắt buộc phải được xử lý.
- Có backlog, retry, DLQ hoặc restore từ snapshot.
- Rolling deployment có cả v1/v2.
- Quy trình rollback yêu cầu phiên bản cũ tiếp tục đọc dữ liệu mới.
- Dữ liệu là hồ sơ nghiệp vụ hoặc kiểm toán chứ không phải derived cache.

### Có thể chủ động cắt phiên/đổi contract khi

- Hệ thống có lý do bảo mật hoặc thay đổi chính sách rõ ràng.
- Người dùng/đối tác được thông báo và có đường đăng nhập/kết nối lại.
- Các message/job tồn tại được chuyển đổi hoặc xử lý riêng.
- Điều kiện downtime/maintenance được phê duyệt.
- Có bằng chứng không làm mất những nghĩa vụ nghiệp vụ chưa hoàn tất.

Thay đổi làm logout hàng loạt mà không được quản lý có thể gây sự cố vận hành; tuy nhiên cố giữ mọi phiên bằng cách hạ security checks cũng không phải mục tiêu hợp lệ.

## 23. Một lộ trình triển khai an toàn

### Giai đoạn 1 — Baseline và inventory

- Xác định JDK/framework/serializer v1.
- Liệt kê các cache key prefix, session stores, brokers, topics, DLQ, retry jobs và outbox.
- Ghi schema, TTL, retention, writers, readers, secret/key dependencies và owner.
- Lưu golden fixtures an toàn cho v1, kể cả những payload ít gặp.
- Đo lỗi và độ trễ hiện tại để có mốc so sánh.

### Giai đoạn 2 — Mở rộng khả năng đọc

- Triển khai reader v2 hiểu format v1 và format v2 cần thiết.
- Thêm version detection và semantic validation.
- Giữ writer phát schema v1 trong cửa sổ còn consumer cũ.
- Thêm telemetry theo schema và cơ chế fail an toàn cho corrupted payload.
- Kiểm tra cache stampede, session expiration và message retries.

### Giai đoạn 3 — Mixed deployment

- Đưa một số instance v2 vào hệ thống.
- Giữ reader v1 chỉ nhận dữ liệu mà nó đã được chứng minh đọc được.
- Nếu v2 cần ghi schema v2, cô lập bằng key namespace, topic/version hoặc feature flag để không đưa dữ liệu mới tới v1 ngoài ý muốn.
- Test user session chuyển node, request đồng thời và broker consumer-group rebalance.
- Đo cả lỗi nền và DLQ, không chỉ health check.

### Giai đoạn 4 — Chuyển writer và state

- Chỉ bật producer/writer v2 khi các consumer liên quan đã sẵn sàng.
- Chuyển cache key, session DTO hoặc payload bằng adapter/background migration khi cần.
- Đảm bảo outbox/retry/DLQ xử lý dữ liệu lịch sử.
- Ghi lại mốc ngừng ghi v1 và theo dõi tồn dư schema v1.
- Chuẩn bị rollback phù hợp với dữ liệu v2 đã xuất hiện.

### Giai đoạn 5 — Chờ hết vòng đời dữ liệu và dọn hợp đồng cũ

- Chờ TTL/session max lifetime/message retention/retry/replay/backup policy.
- Xác minh không còn writer v1 hoạt động.
- Kiểm tra DLQ/outbox/snapshot có thể phục hồi dữ liệu v1 không.
- Chỉ loại reader v1 khi có bằng chứng các nguồn lịch sử đã hết hoặc được chuyển đổi.
- Gỡ feature flag và compatibility adapter theo thay đổi phát hành riêng, có test hồi quy.

### Giai đoạn 6 — Đánh giá rollback thật

Một rollback không chỉ thay image từ v2 về v1. Sau khi writer v2 đã ghi:

- Cache có thể mang key/schema mới.
- Sessions có thể chứa format hoặc security claims mới.
- Queue có thể chứa event schema mới.
- Database/outbox có thể có hàng v2.
- Token có thể được ký bằng khóa mới.

Do đó cần xác định **phiên bản v1 rollback có thể đọc gì** và liệu có phải giữ một compatibility release thay vì quay về build gốc. Không ghi “rollback ready” chỉ vì container cũ vẫn khởi động được.

## 24. Ví dụ tổng hợp: nâng JDK và framework với Redis + session + Kafka

Giả sử nền tảng bán hàng đang chạy ứng dụng Java 11, Redis cache/session và Kafka. Đội phát triển muốn chuyển sang Java 21 và nâng framework; trong quá trình đó:

- Redis lưu `ProductView` dưới dạng Java serialization.
- Session chứa principal object được framework serialize.
- Kafka lưu `order.created` JSON schema v1 trong topic 7 ngày.
- Một số event thất bại nằm trong DLQ có thể được replay sau một tháng.
- Hệ thống deploy rolling, v1 và v2 chạy đồng thời một khoảng thời gian.

### Phương án có rủi ro

1. Đổi package `ProductView` và cấu trúc principal.
2. Chuyển Redis serializer sang JSON với cùng cache keys/session prefix.
3. Cho producer phát `order.created` schema v2 ngay khi pod đầu tiên chạy.
4. Xóa toàn bộ Redis khi có lỗi.
5. Rollback v1 khi DLQ tăng.

Hậu quả có thể là v1/v2 không đọc được session của nhau, logout hàng loạt, cache miss gây quá tải DB, consumer v1 không hiểu event v2, và rollback vẫn không xử lý được thông điệp đã phát.

### Phương án có kiểm soát

**Bước 1:** Tách cache derived khỏi Redis session và idempotency keys; không xóa chung cả database/prefix.

**Bước 2:** Tạo golden fixtures từ format v1 cho cache/session/event, dùng dữ liệu kiểm thử giả lập không chứa secret.

**Bước 3:** Đối với cache derived, dùng namespace `product:v2` với serializer JSON mới, cho phép cache miss/rebuild được giới hạn. Không để v1 đọc nhầm key v2.

**Bước 4:** Giữ session serializer tương thích hoặc tạo adapter session v1→v2 trong cửa sổ chuyển đổi. Nếu không thể, thiết kế migration có thời điểm cắt phiên rõ ràng thay vì sự cố ngẫu nhiên.

**Bước 5:** Consumer Kafka v2 chấp nhận cả schema v1 và v2. Khi vẫn có consumer v1, producer tiếp tục gửi schema v1 hoặc chỉ sử dụng field mới theo policy tương thích với v1.

**Bước 6:** Sau khi không còn consumer v1 trong nhóm có thể đọc event, bật producer v2 phát schema v2. Theo dõi schema distribution, lag và DLQ.

**Bước 7:** Giữ parser v1 đủ lâu cho retention Kafka, DLQ, delayed retries và replay policy; không xóa chỉ dựa vào TTL của cache.

**Bước 8:** Kiểm tra rollback. Nếu v1 không đọc được schema v2 đã phát, rollback cần một phiên bản tương thích hoặc cách chặn/quarantine payload mới được phê duyệt, không đơn giản redeploy v1.

Kết quả báo cáo:

| Hạng mục | Bằng chứng cần có |
|---|---|
| Cache v1/v2 | Read fixture, hit/miss, source load, TTL, key namespace |
| Session | Old session trên node mới, new session trên node cũ nếu cần, auth/expiry |
| Kafka | W1/R2 và W2/R1 theo thời điểm rollout, lag, DLQ, replay |
| Outbox/retry | Pending schema cũ vẫn được xử lý, idempotency không mất |
| JDK/framework | Serializer/provider settings và classloading đúng |
| Rollback | Artifact, feature flags, data contract và test thực tế |

## 25. Những nhận định dễ sai

**“Cache bị xóa khi deploy nên không cần migration.”** Không đúng với distributed/persistent cache và cache được chia sẻ nhiều service.

**“Thêm `serialVersionUID` là đủ để Java Serialization tương thích.”** Không đúng. Class/package name, cấu trúc trường, custom serialization và semantic invariants vẫn quan trọng.

**“Chỉ cần producer mới và consumer mới hiểu nhau.”** Chưa đủ khi còn consumer cũ, retry, DLQ hoặc replay event cũ.

**“JSON có thể bỏ qua unknown fields nên thay schema nào cũng được.”** Không đúng. Required field, enum, kiểu dữ liệu và ý nghĩa field có thể phá hợp đồng.

**“Xóa Redis sửa được lỗi session.”** Có thể làm logout và mất idempotency/lock nếu cùng kho chứa các loại state khác.

**“Broker đã ack nghĩa là event không bao giờ xuất hiện lại.”** Không nên giả định trong mọi hệ thống; cần xét redelivery, retry, replay và side effects.

**“Rolling deployment là an toàn vì mỗi pod đều healthy.”** Không đủ. Reader/writer khác version có thể tương tác qua cùng storage hoặc queue dù HTTP health checks đều xanh.

**“Đợi hết TTL cache rồi xóa parser cũ cho mọi dữ liệu.”** Không đủ với session sliding expiry, message retention, DLQ, outbox và backup restore.

**“Rollback chỉ là chạy lại image v1.”** Không đúng nếu data format đã được writer v2 ghi theo một chiều không thể đọc ngược.

**“Lỗi parse có thể được bỏ qua để service tiếp tục chạy.”** Với cache derived, có thể fallback có kiểm soát; với payment event, session security state hoặc job nghiệp vụ, bỏ qua có thể tạo mất dữ liệu và sai lệch nghiêm trọng.

## 26. Checklist trước khi nâng JDK hoặc thay contract dữ liệu

- [ ] Đã liệt kê mọi loại state còn tồn tại sau restart/deploy.
- [ ] Đã phân biệt cache derived, session, idempotency state, lock và durable message.
- [ ] Đã xác định producer/writer và reader/consumer của từng payload.
- [ ] Đã ghi serializer, schema version, key namespace, TTL và retention.
- [ ] Đã xác minh JDK/framework mới đọc được fixture dữ liệu v1.
- [ ] Đã xác minh v1 đọc được dữ liệu v2 nếu rolling/rollback yêu cầu.
- [ ] Đã kiểm tra Java Serialization class names, UID, custom serializer và classloader.
- [ ] Đã xác định unknown field/enum, null/default và semantic compatibility.
- [ ] Đã tính TTL, session sliding expiry, token max life, broker retention, retry và DLQ.
- [ ] Đã kiểm tra session cookie, security key rotation, expiry và user experience.
- [ ] Đã bảo đảm consumer sẵn sàng trước khi producer phát schema mới.
- [ ] Đã xác minh idempotency, dedup và message ordering khi retry/replay.
- [ ] Đã kiểm tra outbox/inbox và các job chưa xử lý.
- [ ] Đã tránh xóa key hoặc message nghiệp vụ bằng một lệnh invalidate đại trà.
- [ ] Đã chạy integration test với dữ liệu v1 tồn tại khi khởi chạy v2.
- [ ] Đã chạy mixed-version và rollback tests theo kiến trúc thực tế.
- [ ] Đã có metrics parse errors, cache misses, session failures, lag và DLQ.
- [ ] Đã có giai đoạn giữ reader v1 đủ theo vòng đời của dữ liệu lịch sử.
- [ ] Đã xác định owner và bằng chứng trước khi dọn compatibility code.
- [ ] Đã bảo vệ PII, tokens, passwords và tránh deserialize nguồn không tin cậy.

## 27. Kết luận

Trong Java Advance Compatibility Migration, **cache, phiên đăng nhập và thông điệp là những hợp đồng còn hiệu lực sau khi phiên bản mã tạo ra chúng đã bị thay thế**. Một deploy có thể hoàn thành về mặt hạ tầng nhưng thất bại về mặt dữ liệu nếu phiên bản mới không đọc được payload cũ, phiên bản cũ không hiểu payload mới, hoặc dữ liệu lịch sử bị xử lý sai do thay đổi ý nghĩa field.

Phương pháp đáng tin cậy là lập inventory theo nơi lưu và vòng đời, tạo fixture v1, kiểm tra ma trận W1/R1–W1/R2–W2/R2–W2/R1, dùng schema version và triển khai **reader trước writer**. Với cache có thể tái tạo, có thể chuyển namespace hoặc invalidate có kiểm soát; với session và durable messages, phải bảo tồn quyền truy cập và xử lý đúng nghĩa vụ nghiệp vụ. Chỉ xóa reader cũ sau khi đã xác minh TTL, session lifetime, broker retention, retry, DLQ, outbox và restore policy.

Tương thích qua lần triển khai không chỉ là khả năng nạp một file hay parse một JSON. Đó là cam kết rằng **dữ liệu được tạo hôm qua vẫn có ý nghĩa và được xử lý đúng vào ngày mai**, kể cả khi JDK, framework, class loader và ứng dụng đã thay đổi.
