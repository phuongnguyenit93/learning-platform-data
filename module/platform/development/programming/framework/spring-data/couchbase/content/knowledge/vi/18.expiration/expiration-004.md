# TTL tương đối và mốc thời gian tuyệt đối

## 1. Cùng là “hết hạn”, nhưng có hai ý định khác nhau

Trong **Spring Data Couchbase**, document có thể mang metadata về thời điểm hết hạn (expiry). Khi hết thời hạn, Couchbase coi document là không còn hiệu lực để đọc như dữ liệu đang tồn tại. Tuy nhiên, câu “giữ document trong 30 phút” và câu “giữ document đến 17:00 ngày 1 tháng 1” không diễn đạt cùng một chính sách.

- **TTL tương đối (relative TTL)**: sống thêm một khoảng thời gian sau khi một thao tác gán expiry diễn ra.
- **Mốc thời gian tuyệt đối (absolute expiry)**: hết hiệu lực tại một thời điểm cố định trên trục thời gian.

Phân biệt này quan trọng khi ứng dụng có retry, nhiều lần lưu lại entity, tác vụ nền, lịch khuyến mãi, mã OTP hoặc giỏ hàng cần gia hạn. Nếu một thao tác lặp lại relative TTL, nó có thể **đẩy hạn sử dụng ra xa**; nếu thao tác lặp lại cùng một absolute deadline, hạn cuối vẫn cố định.

Bài học thuộc chương **Thời gian hết hạn** của module **SPRING_DATA_COUCHBASE**. Module hướng đến xây dựng tầng truy cập bằng document mapping, `CouchbaseRepository`, `CouchbaseTemplate` và SQL++; học cách bố trí bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, nhất quán, vận hành.

Sau bài này, bạn có thể:

1. Giải thích bằng timeline sự khác nhau giữa relative TTL và absolute expiry.
2. Sử dụng `java.time.Duration` và `java.time.Instant` đúng ngữ nghĩa trong Couchbase Java SDK.
3. Chuyển deadline theo múi giờ nghiệp vụ thành mốc UTC rõ ràng.
4. Tránh lỗi đơn vị số giây, quy tắc 30 ngày ở API thấp và timestamp Unix.
5. Quyết định lúc nào **gia hạn**, **bảo toàn** hoặc **không đặt TTL** khi cập nhật.
6. Thiết kế expiry an toàn khi retry, CAS, giao dịch, repository và reactive.
7. Kiểm chứng expiry hiệu lực khi có `maxTTL`, thay đổi đồng hồ hoặc race condition.

Các ví dụ viết theo phong cách **Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x**. Cách diễn giải raw numeric expiry, API mapping và chính sách maxTTL thay đổi theo version; nên xác nhận bằng đúng artifact/server đang triển khai.

## 2. Mô hình thời gian của một document

Ví dụ một keyspace:

~~~text
Bucket: commerce
├── Scope: catalog
│   └── Collection: campaigns
└── Scope: checkout
    ├── Collection: carts
    ├── Collection: otp_codes
    └── Collection: reservations
~~~

Một document gồm key, content và metadata, trong đó có expiry:

~~~text
Document key: cart::u-42
Content:
  { "userId": "u-42", "itemCount": 2 }

Metadata:
  CAS: ...
  expiry: một mốc thời gian hoặc không có expiry
~~~

**Điểm mấu chốt:** Couchbase lưu và thực thi **trạng thái hết hạn hiệu lực của document**; relative TTL là cách caller **yêu cầu tạo ra** một thời điểm hết hạn khi thao tác được thực hiện. Khi đã áp dụng, “thêm 30 phút” dẫn tới một deadline cụ thể.

~~~mermaid
flowchart LR
    A["Yêu cầu mutation"] --> B{"Kiểu expiry?"}
    B -- "Duration 30 phút" --> C["Tính hạn từ thời điểm áp dụng"]
    B -- "Instant cố định" --> D["Giữ mốc tuyệt đối"]
    C --> E["Server xác định expiry hiệu lực"]
    D --> E
    F["Bucket/collection maxTTL"] --> E
    E --> G["Document hết hạn theo metadata"]
~~~

Không nhầm expiry với `kvTimeout`, `queryTimeout` hay transaction timeout: ba giới hạn kia điều khiển **thời gian chờ công việc**, không trực tiếp quy định document sống bao lâu.

## 3. TTL tương đối là gì?

TTL tương đối có dạng “tính từ lúc gán expiry, sống thêm N đơn vị thời gian”. Java biểu diễn nó bằng `Duration`.

Ví dụ: lúc 10:00 ứng dụng tạo giỏ hàng với TTL 30 phút.

~~~text
10:00   Ghi cart::u-42 với TTL 30 phút
10:15   Cart chưa hết hạn
10:29   Cart chưa hết hạn
10:30   Mốc expiry dự kiến
10:31   Cart được coi là hết hiệu lực
~~~

Nếu lúc 10:20 ứng dụng **chủ động đặt lại TTL 30 phút** khi người dùng cập nhật giỏ, hạn có thể dịch đến 10:50:

~~~text
10:00 ─────── 10:20 ───────────────────── 10:50
  │             │                           │
  │             └─ Áp lại TTL 30 phút ─────┘
  └─ Hạn cũ ban đầu: 10:30
~~~

Vậy relative TTL thường phù hợp với:

- Giỏ hàng tạm còn hoạt động.
- Bộ nhớ đệm có thời hạn sau lần ghi.
- Phiên làm việc có **idle timeout** nếu chính sách cho gia hạn.
- Dữ liệu trung gian chỉ cần một khoảng thời gian tồn tại kể từ lần tạo/sửa.

### 3.1. Khi nào nên dùng relative TTL?

Chọn relative TTL khi nghiệp vụ thật sự được định nghĩa theo **khoảng cách so với sự kiện**: “30 phút sau lần cập nhật giỏ gần nhất” hoặc “2 giờ sau khi cache entry được tạo”.

Đừng tự động gia hạn sau **mọi** lần đọc. “30 phút sau lần sửa gần nhất” khác “30 phút sau lần xem gần nhất”. Lời gọi `get(id)` bình thường không phải `touch`; nếu service tự động gọi `touch` sau đọc, bạn đã thay đổi chính sách nghiệp vụ.

## 4. Mốc thời gian tuyệt đối là gì?

Absolute expiry diễn đạt “document hết hạn **vào đúng một thời điểm xác định**”, bất kể lúc ứng dụng tạo hoặc sửa content.

Ví dụ chiến dịch phải kết thúc vào `2027-01-01T00:00:00Z`:

~~~text
2026-12-20   Tạo campaign
2026-12-29   Sửa mô tả
2026-12-31   Sửa tên chiến dịch
2027-01-01
00:00 UTC     Deadline không đổi
~~~

Cách biểu diễn phù hợp trong Java là `Instant`. Mỗi lần cập nhật cần truyền **cùng deadline** hoặc bảo toàn expiry metadata đã đặt.

Absolute expiry thích hợp với:

- Mã OTP hết hạn đúng 5 phút sau khi phát hành, không được gia hạn khi kiểm tra sai.
- Giấy giữ chỗ hết hiệu lực tại giờ đã xác nhận với người dùng.
- Chiến dịch có ngày giờ kết thúc công bố trước.
- Session có **absolute maximum lifetime**.
- Một tài liệu có thời điểm kết thúc theo hợp đồng hoặc lịch.

### 4.1. Bảng so sánh

| Câu hỏi | TTL tương đối | Absolute expiry |
| --- | --- | --- |
| Kiểu Java rõ nghĩa | `Duration` | `Instant` |
| Dữ liệu đầu vào | 30 phút | `2027-01-01T00:00:00Z` |
| Mốc tham chiếu | Thời điểm áp TTL | Deadline đã xác định |
| Khi retry vào thời điểm sau | Có thể đẩy deadline ra xa | Giữ nguyên deadline nếu dùng lại cùng `Instant` |
| Khi sửa nội dung | Quyết định có làm mới TTL hay không | Thường giữ cùng deadline |
| Nhu cầu timezone | Không cần cho một khoảng thời gian thuần | Cần nếu deadline xuất phát từ lịch địa phương |
| Rủi ro | Sliding TTL ngoài ý muốn | Clock/timezone sai, deadline quá khứ |

**Không có lựa chọn tốt hơn tuyệt đối cho mọi loại document.** Lựa chọn phải đi từ quy tắc nghiệp vụ, không phải API nào viết ít code hơn.

## 5. Dùng `Duration` trong Couchbase Java SDK

Ví dụ tạo cart ở `commerce.checkout.carts`:

~~~java
import java.time.Duration;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

// carts là Collection handle đã trỏ đúng commerce.checkout.carts.
JsonObject content = JsonObject.create()
        .put("userId", "u-42")
        .put("itemCount", 2);

carts.upsert(
        "cart::u-42",
        content,
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofMinutes(30))
);
~~~

Khi thao tác thành công, yêu cầu expiry tương đối đã được gửi tới server. Thời hạn thực tế có thể chịu giới hạn `maxTTL` ở bucket/collection. Ví dụ không tự tạo tài nguyên Couchbase; keyspace và quyền truy cập phải có từ trước.

### 5.1. API khác có thể đặt relative TTL

Ví dụ tạo mã xác minh chỉ khi key chưa tồn tại:

~~~java
import java.time.Duration;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.InsertOptions;

verificationCodes.insert(
        "otp::u-42",
        JsonObject.create().put("hash", "hash-placeholder"),
        InsertOptions.insertOptions()
                .expiry(Duration.ofMinutes(5))
);
~~~

`insert` và `upsert` có semantics khác nhau: `insert` từ chối key đã tồn tại, còn `upsert` có thể thay content. Với mã dùng một lần, chọn key/chiến lược tạo mới theo yêu cầu idempotency và chống cấp mã trùng; **TTL không thay thế rate limit, kiểm tra mã đã dùng hoặc bảo vệ secret**.

### 5.2. `Duration.ofDays(1)` không đồng nghĩa “hết cuối ngày”

`Duration.ofDays(1)` là 24 giờ. Nếu người dùng tạo order lúc 18:00 hôm nay, áp TTL 24 giờ sẽ hết lúc 18:00 ngày mai, **không phải** 00:00 ngày mai.

Đối với “hết ngày” hay “đầu kỳ mới”, phải tính bằng ngày lịch và múi giờ, rồi chuyển sang `Instant`.

## 6. Dùng `Instant` cho deadline cố định

Ví dụ campaign sẽ hết hạn lúc 00:00 UTC ngày 1 tháng 1 năm 2027:

~~~java
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Instant campaignDeadline =
        Instant.parse("2027-01-01T00:00:00Z");

campaigns.upsert(
        "campaign::NEW_YEAR",
        JsonObject.create().put("name", "New Year"),
        UpsertOptions.upsertOptions()
                .expiry(campaignDeadline)
);
~~~

Ưu điểm: nếu ứng dụng cần cập nhật nội dung ngày 29/12, deadline đã lưu vẫn có thể được truyền lại **y nguyên**. Không cần “tính số phút còn lại” rồi cộng vào mỗi lần retry, vốn dễ bị dịch hạn theo thời gian chờ.

### 6.1. Tính deadline từ thời điểm phát hành

Ví dụ OTP hết hạn đúng 5 phút kể từ khi **phát hành**, không phải từ lần ghi lại sau cùng:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

Clock clock = Clock.systemUTC();

Instant issuedAt = Instant.now(clock);
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(5));
~~~

Lưu `expiresAt` như dữ liệu nghiệp vụ nếu cần đối soát, đồng thời dùng **chính `expiresAt` đó** khi đặt metadata expiry.

Nếu retry hoặc cập nhật số lần thử thất bại, dùng lại biến/mốc deadline đã lưu; **không gọi `Instant.now().plus(5m)` lần nữa** để tính hạn mới.

### 6.2. Điều kiện trước khi ghi

Một `Instant` thuộc quá khứ hoặc quá gần hiện tại có thể khiến document hết hiệu lực ngay hoặc chỉ tồn tại rất ngắn. Khi cấp mã/phiên, service nên xác nhận:

- Deadline chưa qua.
- Khoảng thời gian hợp lệ theo chính sách sản phẩm.
- Đồng hồ ứng dụng được đồng bộ đáng tin cậy.
- Mốc deadline không bị dịch chuyển bởi retry.
- Server `maxTTL` không rút ngắn thời hạn ngoài mong đợi.

## 7. Múi giờ địa phương và thời điểm UTC

Ví dụ sản phẩm áp dụng tại Việt Nam có khuyến mãi kết thúc lúc **đầu ngày 1/1/2027 theo giờ Việt Nam**. Phải chuyển ngày lịch với `ZoneId`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant endExclusive = LocalDate.of(2027, 1, 1)
        .atStartOfDay(zone)
        .toInstant();
~~~

Mốc tính được là **2026-12-31T17:00:00Z**, khác `2027-01-01T00:00:00Z`.

| Yêu cầu | Mốc UTC tương ứng |
| --- | --- |
| 00:00 ngày 1/1/2027 ở Việt Nam (UTC+7) | 17:00 ngày 31/12/2026 UTC |
| 00:00 ngày 1/1/2027 UTC | 07:00 ngày 1/1/2027 ở Việt Nam |
| Sống thêm 24 giờ từ lúc ghi | Phụ thuộc thời điểm ghi; không gắn ngày lịch |

Với vùng có DST, việc “đầu ngày mai” càng không nên suy bằng cách thêm đúng 24 giờ. Dùng `LocalDate`, `ZoneId` và `Instant` là cách biểu diễn rõ hợp đồng.

### 7.1. Lưu deadline trong JSON và metadata

Một document có thể lưu:

~~~json
{
  "campaignId": "NEW_YEAR",
  "endsAt": "2026-12-31T17:00:00Z",
  "status": "ACTIVE"
}
~~~

Nhưng field JSON `endsAt` **không tự trở thành** metadata expiration. Phải có code đặt `UpsertOptions.expiry(instant)`, mapping hỗ trợ hoặc thao tác server tương ứng.

Nếu giữ cả field JSON và expiry metadata, hãy thống nhất nguồn sự thật, cách cập nhật và các điều kiện retry. Field JSON hữu ích cho truy vấn/hiển thị, nhưng metadata server quyết định việc document hết hạn.

## 8. Vì sao một số API nhắc đến ngưỡng 30 ngày?

Khi dùng **giá trị expiry số nguyên thô** trong một số giao thức/API Couchbase, quy tắc lịch sử thường được mô tả như sau:

- Giá trị dương ngắn (tới khoảng 30 ngày tính bằng giây) có thể được diễn giải là số giây **tương đối**.
- Giá trị dương lớn hơn ngưỡng có thể được diễn giải là **Unix timestamp tuyệt đối**.
- Giá trị 0 thường mang nghĩa **không đặt expiry ở cấp document**, nhưng phải xét `maxTTL`.

Ngưỡng thường được nhắc tới là **30 × 24 × 60 × 60 = 2.592.000 giây**. Đây là **cảnh báo về biểu diễn số thấp tầng/legacy**, không phải lời khuyên tự viết logic phân nhánh ở ứng dụng Java hiện đại.

### 8.1. Sai lầm khi chuyển thủ công số giây

~~~java
// Tránh tự truyền một số giây mơ hồ cho API raw.
long fortyFiveDaysInSeconds = Duration.ofDays(45).getSeconds();
~~~

Một API thô có thể diễn giải con số lớn như timestamp gần epoch 1970 thay vì “45 ngày tính từ bây giờ”. Hậu quả có thể là document hết hạn ngay hoặc sai lệch nghiêm trọng.

**Cách phòng tránh:** dùng overload biểu đạt ngữ nghĩa như `expiry(Duration.ofDays(45))` hoặc `expiry(Instant)` do Couchbase Java SDK phiên bản đang dùng hỗ trợ. Khi giao tiếp qua REST/SQL++ hoặc API khác, xác nhận hợp đồng expiry và các thay đổi ở **server/SDK version thực tế**.

### 8.2. Không dùng timestamp theo mili giây thay cho giây

Unix timestamp có thể ở hai độ phân giải phổ biến:

- `Instant.getEpochSecond()`: giây từ Unix epoch.
- `Instant.toEpochMilli()`: mili giây từ Unix epoch.

Chúng không thể thay thế nhau bằng cùng một numeric parameter. Nếu API thô yêu cầu giây mà bạn truyền mili giây, thời điểm sẽ sai rất xa. Ưu tiên `Instant` để không phải tự quyết định đơn vị.

## 9. Khi nào document không có expiry?

Một document sản phẩm có thể được thiết kế **không tự hết hạn**. Ở mức Couchbase, expiry bằng 0 thường được dùng để biểu đạt không có thời hạn ở cấp document.

Tuy nhiên, **không TTL** không đồng nghĩa **bất tử**:

1. Document có thể bị xóa bằng `remove` hoặc nghiệp vụ.
2. Bucket, scope hoặc collection có thể bị xóa.
3. Server có thể có chính sách maximum TTL ở cấp bucket/collection.
4. Dữ liệu có thể bị ảnh hưởng bởi các quy trình backup/restore và vận hành khác.
5. Expiry không tự bảo đảm xóa vật lý khỏi mọi bản sao ở một thời điểm.

Nếu `products` cần lưu dài hạn nhưng collection bị ép `maxTTL` một ngày, việc bỏ thuộc tính `expiry` trong Java **không đủ** để đảm bảo retention.

### 9.1. “Không chỉ định expiry” khác “preserve expiry”

Một mutation không truyền expiry **không được mặc nhiên hiểu là giữ hạn cũ**. Một số thao tác thay thế/upsert có thể reset metadata expiry hoặc chịu maxTTL server, trong khi option **preserve expiry** yêu cầu giữ đúng hạn đang có.

Bảng phân biệt:

| Ý định | Diễn đạt |
| --- | --- |
| Không có hạn ở cấp document | Expiry bằng 0 khi policy/server cho phép |
| Sống thêm N phút | `Duration` tương đối |
| Hết tại giờ cố định | `Instant` tuyệt đối |
| Giữ hạn cũ khi cập nhật content | `preserveExpiry(true)` khi API hỗ trợ |
| Làm mới hạn vì có hoạt động hợp lệ | `touch` hoặc mutation đặt expiry mới |

Không gom cả năm ý định thành “đặt TTL”.

## 10. Chính sách `maxTTL` có thể thay đổi hạn thực tế

Couchbase Server có thể cấu hình maximum TTL trên bucket hoặc collection tùy phiên bản. Khi ghi document, expiry hiệu lực chịu tác động của **request + policy server**.

~~~mermaid
flowchart TD
    A["Ứng dụng yêu cầu expiry"] --> C["Couchbase Server"]
    B["Bucket/Collection maxTTL"] --> C
    C --> D["Expiry metadata hiệu lực"]
    D --> E["Thao tác KV / SQL++ nhìn nhận document"]
~~~

Ví dụ:

| Expiry ứng dụng muốn | maxTTL server | Cần kiểm tra |
| --- | --- | --- |
| Cart 30 phút | Không có giới hạn ngắn hơn | Khoảng 30 phút nếu request áp đúng |
| Cart 30 phút | Collection maxTTL 10 phút | Có thể hết sau 10 phút |
| Campaign hết cuối tháng | Collection maxTTL 1 tuần | Có thể hết trước deadline sự kiện |
| Product không TTL | Bucket ép maxTTL 1 ngày | Không bảo đảm sống dài hạn |
| OTP 5 phút | maxTTL 1 giờ | TTL 5 phút vẫn có thể hợp lệ |

Quy tắc chi tiết về áp dụng, kế thừa hoặc ưu tiên giữa maxTTL bucket/collection cần được xác nhận theo **server version và cấu hình keyspace thực**. `@Document` không thể vượt qua một ràng buộc server.

### 10.1. Đặt tài liệu vào collection hợp lý

Thiết kế thường tốt hơn khi tách collection theo chính sách expiry:

~~~text
commerce.catalog.products        → không ép TTL ngắn
commerce.checkout.carts          → cho phép TTL theo hoạt động
commerce.checkout.otp_codes      → TTL rất ngắn
commerce.catalog.campaigns       → deadline tuyệt đối
~~~

Không đặt sản phẩm lâu dài và OTP trong cùng collection có maxTTL 5 phút chỉ vì chúng cùng một service.

## 11. Update có thể làm deadline dịch chuyển

Giả sử OTP được tạo lúc 10:00, deadline 10:05. Lúc 10:03 người dùng nhập sai và ứng dụng cần ghi lại số lần thử.

~~~mermaid
sequenceDiagram
    participant App as Checkout Service
    participant CB as Couchbase
    App->>CB: 10:00 tạo OTP, hạn 10:05
    Note over CB: Deadline cố định
    alt Áp lại TTL tương đối 5 phút
      App->>CB: 10:03 cập nhật, TTL 5 phút
      Note over CB: Có thể trôi hạn thành 10:08
    else Giữ expiry hoặc dùng lại Instant gốc
      App->>CB: 10:03 cập nhật, preserve/deadline 10:05
      Note over CB: Vẫn hết hạn 10:05
    end
~~~

Với OTP, “ghi tăng bộ đếm sai” **không phải sự kiện được phép gia hạn**. Giữ deadline là yêu cầu an toàn nghiệp vụ, không chỉ lựa chọn tối ưu hiệu năng.

### 11.1. Bảo toàn expiry bằng SDK khi cập nhật

Ví dụ `ReplaceOptions`:

~~~java
import com.couchbase.client.java.kv.ReplaceOptions;

verificationCodes.replace(
        otpId,
        completeUpdatedJson,
        ReplaceOptions.replaceOptions().preserveExpiry(true)
);
~~~

`preserveExpiry(true)` yêu cầu giữ expiration cũ nếu API/server hỗ trợ. `completeUpdatedJson` phải chứa nội dung đầy đủ vì `replace` thay toàn bộ document content; không nhầm đây là thao tác sửa một field riêng lẻ.

**CAS là vấn đề khác:** nếu hai request cùng cập nhật số lần OTP nhập sai, cần dùng CAS hoặc optimistic locking để tránh lost update. Preserve expiry không tự ngăn xung đột.

### 11.2. Sliding TTL qua `touch`

Ví dụ người dùng đã sửa giỏ và nghiệp vụ cho gia hạn 30 phút:

~~~java
import java.time.Duration;

carts.touch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

`touch` thay metadata expiry, không yêu cầu ghi lại JSON content. Chỉ gọi từ nơi nghiệp vụ cho phép. Nếu gọi mỗi lần người dùng *xem* giỏ thay vì *sửa*, policy đã chuyển từ “30 phút sau lần sửa” sang “30 phút sau mọi tương tác”.

## 12. Relative TTL khi có retry và kết quả mutation mơ hồ

Một thao tác ghi có thể bị timeout dù server đã thực hiện mutation. Với `AmbiguousTimeoutException`, ứng dụng **không biết chắc** ghi đã thành công hay chưa.

Vấn đề của relative TTL:

~~~text
10:00:00   Gửi mutation OTP TTL 5 phút
10:00:01   Client không nhận response → ambiguous timeout
10:00:04   Retry với TTL 5 phút
10:05:04   Hạn mới có thể muộn hơn hạn phát hành dự kiến
~~~

Trong khi đó, nếu mọi lần thử dùng cùng `Instant deadline = issuedAt + 5m`, retry không tự dịch thời hạn.

### 12.1. Mẫu đặt deadline một lần

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

Clock clock = Clock.systemUTC();
Instant issuedAt = Instant.now(clock);
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(5));

// expiresAt được tính MỘT LẦN cho nghiệp vụ phát hành này.
verificationCodes.upsert(
        otpKey,
        JsonObject.create()
                .put("hash", otpHash)
                .put("issuedAt", issuedAt.toString())
                .put("expiresAt", expiresAt.toString()),
        UpsertOptions.upsertOptions().expiry(expiresAt)
);
~~~

Nếu cần retry, **tái sử dụng `expiresAt` và identity nghiệp vụ**, không tạo deadline khác. Mẫu trên không tự giải quyết việc two writers cùng cấp mã; cần thêm semantics insert/upsert, idempotency key và CAS/transaction tùy bài toán.

### 12.2. Phân biệt retry đọc và retry ghi

Đọc theo ID thường có thể thử lại khi lỗi tạm thời với deadline tổng hợp lý. Ghi làm phát sinh side effect cần kiểm tra:

- Mutation có idempotent theo **nghiệp vụ** không?
- Key document đã cố định hay thay đổi mỗi lần retry?
- Kết quả của lần trước có thể đã được áp dụng?
- Deadline phải cố định hay được phép kéo dài?
- Phải đọc lại trạng thái/CAS trước khi thử tiếp không?

Đừng chồng retry ở SDK, service và HTTP gateway mà không có giới hạn tổng.

## 13. Một session có cả idle TTL và hard deadline

Một phiên đăng nhập thường cần **hai giới hạn**:

- Idle TTL: ví dụ 20 phút kể từ tương tác hợp lệ gần nhất.
- Absolute lifetime: tối đa 8 giờ từ lúc phát hành, bất kể người dùng còn hoạt động.

Nếu chỉ gọi `touch(Duration.ofMinutes(20))` mãi, phiên có thể được gia hạn vô hạn. Chính sách đúng lấy **deadline sớm hơn**.

~~~text
issuedAt:           09:00
hardDeadline:       17:00
lastActivity:       16:50
idleDeadline:       17:10
effectiveDeadline:  17:00
~~~

Một hàm Java dùng `Clock` để dễ test:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

static Instant nextSessionExpiry(
        Instant issuedAt,
        Duration idleTtl,
        Duration absoluteLifetime,
        Clock clock) {

    Instant now = Instant.now(clock);
    Instant idleUntil = now.plus(idleTtl);
    Instant absoluteUntil = issuedAt.plus(absoluteLifetime);

    return idleUntil.isBefore(absoluteUntil)
            ? idleUntil
            : absoluteUntil;
}
~~~

Hàm chỉ tính deadline. Service phải kiểm tra session đã hết hạn hay chưa trước khi gia hạn, và ghi `Instant` hiệu lực bằng thao tác phù hợp. **Không reset `issuedAt` mỗi lần refresh** nếu field này phục vụ hard deadline.

### 13.1. Tại sao `Clock` có ích?

Gọi `Instant.now()` trực tiếp trong mọi method khiến test phụ thuộc đồng hồ hệ thống. Với `Clock.fixed(...)`, bạn có thể chứng minh một session lúc 16:50 không được gia hạn quá 17:00:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock testClock = Clock.fixed(
        Instant.parse("2027-01-01T16:50:00Z"),
        ZoneOffset.UTC
);
~~~

Tất cả thời gian đầu vào của test phải dùng cùng time basis. Phần test này xác minh phép tính nghiệp vụ, **không thay thế integration test expiry ở Couchbase Server**.

## 14. Spring Data `@Document(expiry)` và ranh giới phiên bản

Khi expiry đơn giản và giống nhau cho toàn bộ entity class, Spring Data Couchbase có thể dùng TTL tĩnh:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 900) // Thông thường: 900 giây
public class ShortLivedSessionDocument {

    @Id
    private String id;
    private String userId;

    protected ShortLivedSessionDocument() {
    }

    public ShortLivedSessionDocument(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
}
~~~

Ở những release hỗ trợ, `expiry` trong annotation là một số **giây** tĩnh được mapper Spring Data sử dụng theo contract của version đó.

Nhưng annotation này **không trực tiếp biểu diễn một `Instant` khác nhau cho từng document**. Nếu chính sách là “mỗi OTP hết hạn đúng 5 phút sau lúc phát hành, không gia hạn khi cập nhật”, cần xác minh mapping create/update và khả năng expiry động.

Một số phiên bản Spring Data Couchbase có các cơ chế liên quan đến **expiry expression** hoặc annotation `@Expiry`. Tên property, cú pháp SpEL, kiểu kết quả và độ ưu tiên so với `expiry` tĩnh cần được xác nhận trong Javadoc/artifact của bản đang dùng. Không suy luận rằng các khả năng đó tồn tại ở mọi bản Spring Data Couchbase.

### 14.1. Bảng lựa chọn API

| Nhu cầu | API thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| Mọi session cùng TTL 15 phút | `@Document(expiry = 900)` | Kiểm tra mapper update có gia hạn không |
| TTL theo config/instance | Cơ chế expiry động của Spring Data nếu version hỗ trợ | Xác minh type/đơn vị và precedence |
| Tạo cart với relative TTL | SDK `UpsertOptions.expiry(Duration)` | Không tự áp mapping entity |
| Campaign deadline cố định | SDK `UpsertOptions.expiry(Instant)` | Kiểm tra timezone và deadline quá khứ |
| Giữ hạn khi sửa | SDK `preserveExpiry(true)` nếu operation hỗ trợ | Không thay CAS |
| Gia hạn sau hoạt động | SDK `touch(Duration)` hoặc cách API tương ứng | Có thể gây sliding TTL |
| Document lâu dài | Không đặt expiry ở cấp document | Vẫn kiểm tra maxTTL server |

`CouchbaseRepository`/`CouchbaseTemplate` có thể sử dụng entity mapping; SDK operations trên `Collection` không tự đọc annotation. Nếu hệ thống kết hợp nhiều đường ghi, hãy xây dựng một chính sách expiry thống nhất ở tầng nghiệp vụ.

## 15. Khi thay đổi code từ repository sang SDK

Giả sử code trước dùng:

~~~java
sessionRepository.save(session);
~~~

Sau refactor, developer sử dụng:

~~~java
sessions.upsert(
        session.getId(),
        JsonObject.create().put("userId", session.getUserId())
);
~~~

Nếu entity có `@Document(expiry = 900)`, **thao tác SDK thuần không biết annotation đó**. Thời hạn thực tế có thể khác sau refactor, đặc biệt nếu SDK upsert không chỉ định expiry trên document đang tồn tại.

Khi đổi đường truy cập, cần đánh giá lại:

1. Cách encode JSON và metadata mapping.
2. `@Version`/CAS để chống lost update.
3. Relative hay absolute expiry được sử dụng.
4. Preserve/reset khi upsert/replace.
5. `maxTTL` của keyspace.
6. Các thao tác reactive hoặc transaction có đi theo đường mới không.

Đừng coi refactor từ repository sang SDK chỉ là thay đổi hiệu năng; nó có thể làm đổi **ngữ nghĩa vòng đời dữ liệu**.

## 16. Đọc metadata expiry: kiểm chứng thay vì đoán

Sau một mutation, SDK Java có thể yêu cầu trả về expiry metadata khi đọc:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = carts.get(
        "cart::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Expiry: " + deadline)
);
~~~

`withExpiry(true)` yêu cầu metadata theo API SDK hỗ trợ; `expiryTime()` trả giá trị tùy chọn trong những SDK 3.x cung cấp API này. Nếu không có giá trị, phải đọc hợp đồng API phiên bản cụ thể và điều kiện document, không suy ra deadline.

**Kiểm chứng hữu ích:**

- Với relative TTL: so expiry metadata với khoảng `thời điểm ghi + Duration`, có độ dung sai.
- Với absolute expiry: so với **mốc `Instant` đã chọn**.
- Khi update preserve: xác minh deadline trước/sau là như nhau (trong độ chính xác API).
- Khi touch: xác minh mốc đã chuyển theo chính sách.
- Khi server có maxTTL: xác minh giới hạn được áp ra sao.

Không cần bật đọc expiry metadata ở mọi request production chỉ để ghi log; dùng khi test, chẩn đoán hoặc nghiệp vụ thực sự cần.

## 17. Kiểm thử với đồng hồ giả lập và Couchbase thật

Nên tách **unit test logic thời gian** và **integration test metadata server**.

### 17.1. Unit test không cần server

Ví dụ xác nhận deadline OTP cố định:

~~~java
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ExpiryPolicyTest {

    @Test
    void absoluteDeadlineDoesNotMoveWithRetry() {
        Instant issuedAt = Instant.parse("2027-01-01T10:00:00Z");
        Instant expiresAt = issuedAt.plus(Duration.ofMinutes(5));

        Instant retryAt = Instant.parse("2027-01-01T10:01:00Z");

        assertThat(expiresAt)
                .isEqualTo(Instant.parse("2027-01-01T10:05:00Z"));

        // retryAt không được dùng để phát hành deadline mới.
        assertThat(retryAt.plus(Duration.ofMinutes(5)))
                .isNotEqualTo(expiresAt);
    }
}
~~~

Test trên chỉ chứng minh cách tính và chính sách. Nó không chứng minh SDK/server đã thực thi expiration.

### 17.2. Integration test với collection riêng

Một kịch bản:

1. Tạo unique key, ví dụ `expiry-it::UUID`.
2. Upsert với `Duration.ofSeconds(5)`.
3. Đọc `expiryTime()` để xác minh mốc gần `now + 5s`.
4. Thử replace với `preserveExpiry(true)` và xác minh hạn cũ giữ nguyên.
5. Với key khác, upsert bằng `Instant` cố định đủ xa trong tương lai.
6. Đọc metadata sau mutation, so với `Instant` trong dung sai thích hợp.
7. Sau deadline có khoảng dự phòng, polling hữu hạn cho đến khi KV không tìm thấy document.
8. Đảm bảo cleanup test data còn sót nếu test thất bại.

Ví dụ mutation test:

~~~java
import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String id = "expiry-it::" + UUID.randomUUID();

testCollection.upsert(
        id,
        JsonObject.create().put("kind", "relative-test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(5))
);
~~~

**Đừng assert đúng từng mili giây.** TTL có độ phân giải/thao tác xử lý riêng; lập lịch test và đồng hồ client/server cũng có sai số. Ưu tiên kiểm tra khoảng dung sai và polling với deadline để giảm flaky tests.

### 17.3. Test maxTTL có chủ đích

Nếu muốn chứng minh behavior của maxTTL, cần biết chính xác cấu hình bucket/collection test. Không thể kết luận từ một entity Java đơn lẻ. Không thay đổi maxTTL của keyspace production chỉ để chạy test.

## 18. SQL++, chỉ mục và document đã hết hạn

Spring Data Couchbase hỗ trợ derived queries và `CouchbaseTemplate` gọi SQL++. Khi một document đã hết hạn logic, ứng dụng không nên coi nó là một document còn hiệu lực chỉ vì backend storage chưa thu hồi hết dữ liệu vật lý.

Tuy nhiên, một query không trả về document **không phải bằng chứng duy nhất rằng TTL đã hết**. Nó có thể thất bại do Query service, index hoặc scan consistency.

Ví dụ truy vấn campaign:

~~~sql
SELECT c.name
FROM `commerce`.`catalog`.`campaigns` AS c
WHERE META(c).id = "campaign::NEW_YEAR";
~~~

Nếu nghiệp vụ cần kiểm tra sự tồn tại/expiry của **một key đã biết**, KV `get(id)` là đường kiểm tra trực tiếp hơn SQL++ và không yêu cầu secondary index.

### 18.1. Field deadline có thể phục vụ tìm kiếm

Nếu bạn lưu `expiresAt` như JSON field, có thể dùng SQL++ để truy vấn các campaign gần kết thúc, sau khi tạo index phù hợp. Nhưng field JSON chỉ hỗ trợ truy vấn nghiệp vụ; **không thay thế metadata expiry** trừ khi code ghi đúng cả hai.

## 19. CAS, transaction và reactive khi gần deadline

### 19.1. CAS và `@Version`

Hai client có thể cập nhật cùng cart hoặc OTP đồng thời. CAS (Compare-And-Swap) hoặc Spring Data `@Version` giúp tránh lost update khi đi qua API hỗ trợ. Expiry và CAS có vai trò riêng:

- **CAS** xác định document có bị người khác thay đổi kể từ lúc đọc hay không.
- **Expiry** xác định document còn tồn tại hợp lệ đến khi nào.
- **Timeout** cho biết request chưa hoàn tất đúng ngân sách, không chứng minh document hết hạn.

Một document có thể hết hạn giữa lúc đọc và replace, dẫn tới not-found. Đừng biến trường hợp đó thành một mutation tạo mới vô điều kiện nếu nghiệp vụ muốn từ chối phiên hoặc giữ chỗ đã hết hạn.

### 19.2. Transaction và deadline

Thời hạn của document **không phải** transaction timeout. Không dùng TTL như một cơ chế tự động commit/rollback transaction chính xác vào một mốc thời gian.

Nếu nghiệp vụ cần giữ hàng đến deadline rồi xác nhận đơn, phải kiểm tra trạng thái và deadline khi thực hiện mutation hoặc transaction, kết hợp CAS/fencing khi cần. TTL hỗ trợ dọn dữ liệu, không thay mọi kiểm tra tính hợp lệ ở logic nghiệp vụ.

### 19.3. Reactive cũng có relative và absolute expiry

SDK reactive sử dụng cùng operation options:

~~~java
import java.time.Instant;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;
import reactor.core.publisher.Mono;

Instant fixedDeadline = issuedAt.plusSeconds(300);

Mono<?> write = verificationCodes.reactive().upsert(
        otpKey,
        JsonObject.create().put("hash", otpHash),
        UpsertOptions.upsertOptions().expiry(fixedDeadline)
);
~~~

Tạo `Mono` chưa có nghĩa write đã được thực thi; phải có subscription. `Mono.timeout(...)` giới hạn thời gian pipeline, **không** đặt document TTL. Retry/resubscribe có thể lặp mutation, vì vậy việc tính một `Instant` bên ngoài pipeline hữu ích khi deadline phải cố định.

Cancellation cũng không bảo đảm mutation đã gửi tới server bị rollback. Với kết quả ambiguous, cần idempotency và đối soát.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xét | Cách tiếp cận |
| --- | --- | --- |
| OTP được gia hạn sau lần nhập sai | Update áp lại relative TTL | Dùng fixed `Instant` hoặc preserve expiry |
| Campaign hết lệch 7 giờ | Nhầm UTC với giờ Việt Nam | Dùng `ZoneId` và chuyển `Instant` |
| Document 45 ngày biến mất sớm | Raw numeric expiry bị diễn giải như epoch | Dùng `Duration`/`Instant` API cấp cao |
| Document không có TTL vẫn hết hạn | Server maxTTL | Kiểm tra policy bucket/collection |
| Update làm mất hạn cũ | Mutation không preserve | Dùng preserve hoặc mốc absolute phù hợp |
| Document sống lâu hơn dự kiến | Retry/touch/save gia hạn | Kiểm tra timeline và operation path |
| Metadata khác giá trị annotation | Mapper/version hoặc maxTTL | Đọc expiry thực tế, rà soát pipeline |
| Chỉ SDK path có TTL sai | SDK không đọc `@Document` | Truyền expiry option rõ ràng |
| SQL++ không thấy nhưng KV còn | Index/query consistency hoặc keyspace | Chẩn đoán SQL++ riêng |
| Giao dịch thất bại gần deadline | Deadline transaction khác document TTL | Xử lý hợp đồng transaction riêng |
| Test hết hạn chập chờn | Kiểm tra sát ranh giới từng ms | Dùng Clock và polling có dung sai |
| Retry viết nhiều bản dữ liệu | Không có idempotency/CAS | Chọn key ổn định và đối soát |

## 21. Bài tập tình huống

Một ứng dụng đặt hàng có:

~~~text
commerce.checkout.carts
commerce.checkout.otp_codes
commerce.checkout.reservations
commerce.catalog.campaigns
~~~

Các yêu cầu:

1. Cart hết hạn 30 phút sau lần sửa giỏ hợp lệ gần nhất.
2. OTP hết hạn 5 phút sau lúc phát hành và không gia hạn khi nhập sai.
3. Reservation chỉ hợp lệ đến **17:00 ngày 1/1/2027 theo giờ Việt Nam**.
4. Campaign hết hạn **00:00 UTC ngày 1/1/2027**.
5. Collection cart có maxTTL 10 phút; các collection khác có chính sách phù hợp.
6. Hệ thống có retry khi mutation timeout và đôi khi chuyển từ repository sang SDK.

**Câu hỏi:**

- Dữ liệu nào phù hợp `Duration`? Dữ liệu nào phải dùng `Instant`?
- Mốc UTC của reservation là bao nhiêu? Có bằng mốc campaign không?
- Vì sao cart không nhất thiết sống được 30 phút dù code truyền `Duration.ofMinutes(30)`?
- Nếu retry một OTP sau 60 giây, dùng relative TTL mới có vấn đề gì?
- Khi cập nhật số lần thử OTP, chọn `preserveExpiry(true)` hay reset TTL? Vì sao?
- Nếu áp `@Document(expiry = 300)` trong repository nhưng chuyển ghi sang SDK, cần xem lại điều gì?
- Cách kiểm chứng expiry hiệu lực bằng SDK nào sẽ tách được vấn đề TTL khỏi vấn đề SQL++ index?
- CAS có giải quyết lỗi deadline bị gia hạn không? Nếu không, nó giải quyết điều gì?

**Đáp án định hướng:** cart dùng relative TTL nhưng maxTTL 10 phút có thể giới hạn hạn thực; OTP dùng deadline cố định; reservation 17:00 ngày 1/1/2027 Việt Nam tương ứng **2027-01-01T10:00:00Z**; campaign là **2027-01-01T00:00:00Z**, lệch 10 giờ. CAS bảo vệ cập nhật cạnh tranh chứ không tự giữ deadline. Muốn kiểm chứng, đọc expiry metadata trên đúng collection và test update/retry.

## 22. Checklist trước khi triển khai

- [ ] Mỗi entity được mô tả rõ theo relative TTL, absolute deadline hoặc không TTL.
- [ ] Relative TTL chỉ được gia hạn bởi sự kiện nghiệp vụ cho phép.
- [ ] Absolute expiry được tính một lần cho nghiệp vụ và tái sử dụng khi retry.
- [ ] Các giá trị thời gian có đơn vị rõ ràng, không truyền raw epoch theo cảm tính.
- [ ] Deadline địa phương được chuyển thành `Instant` với đúng `ZoneId`.
- [ ] Không dùng `Duration.ofDays(1)` thay cho “hết ngày lịch” nếu policy không yêu cầu 24 giờ.
- [ ] Đã kiểm tra `maxTTL` bucket/collection ở môi trường đích.
- [ ] `@Document(expiry)` được hiểu đúng đơn vị/version và không bị bỏ qua bởi SDK trực tiếp.
- [ ] Đường update xác định rõ reset, preserve hay touch.
- [ ] Retry mutation tính đến `AmbiguousTimeoutException` và idempotency.
- [ ] Sliding session có hard deadline nếu nghiệp vụ yêu cầu.
- [ ] CAS/`@Version` dùng cho cạnh tranh cập nhật, không thay thế TTL.
- [ ] Transaction deadline và KV/Query timeout được tách khỏi document expiry.
- [ ] Có unit test với `Clock.fixed` và integration test đọc `expiryTime()`.
- [ ] Không coi expiry logic là bằng chứng xóa vật lý tức thì khỏi mọi bản sao/backup.

## 23. Tổng kết

**TTL tương đối** dùng `Duration` để nói document sống thêm bao lâu kể từ một thao tác gán expiry; **mốc tuyệt đối** dùng `Instant` để nói document hết hạn vào lúc nào trên trục thời gian. Cùng một yêu cầu lưu trữ nhưng lựa chọn sai kiểu thời gian có thể khiến document bị gia hạn ngoài ý muốn, đặc biệt khi update hoặc retry.

Couchbase Java SDK cho phép biểu đạt hai ý định bằng các API expiry tương ứng; Spring Data Couchbase có mapping TTL tĩnh như `@Document(expiry = ...)` và các cơ chế nâng cao phụ thuộc phiên bản. Hạn thực còn chịu chính sách `maxTTL` ở server và hành vi của mutation.

Khi chọn chính sách theo nghiệp vụ, dùng mốc thời gian rõ ràng, kiểm tra metadata và kết hợp đúng CAS, transaction, SQL++ index cũng như reactive API, hệ thống có thể quản lý vòng đời dữ liệu nhất quán mà không nhầm document expiration với timeout của request.

