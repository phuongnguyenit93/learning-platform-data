# Bộ đếm nguyên tử theo khóa và phạm vi sử dụng

Trong **Spring Data Couchbase**, nhiều nghiệp vụ cần tăng hoặc giảm một giá trị dùng chung: lượt truy cập, số yêu cầu đã xử lý, bộ cấp số tham chiếu hoặc thống kê theo từng tenant/ngày. Cách đọc giá trị bằng Repository rồi cộng một trong Java và `save(...)` lại có thể gây **lost update** khi hai request thực hiện đồng thời.

Couchbase Java SDK cung cấp **KV atomic counter** qua `collection.binary().increment(...)` và `decrement(...)`. Server xử lý mỗi thao tác tăng/giảm nguyên tử trên **một counter document được xác định bằng key trong một collection**. Đây là công cụ đơn giản và hữu ích, nhưng có phạm vi bảo đảm cụ thể.

**Một phép tăng nguyên tử không mặc nhiên bảo đảm một business event được tính đúng một lần, không tạo ra dãy ID không có lỗ hổng, không bảo đảm quota hay số dư, không giao dịch đồng thời với document khác và không cung cấp bộ đếm nguyên tử toàn cầu giữa các datacenter XDCR hai chiều.**

Bài thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase bằng document mapping, Repository, `CouchbaseTemplate`, SQL++, thiết kế bucket/scope/collection, TTL, CAS, giao dịch và reactive API để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích atomicity ở cấp document key và những giới hạn vượt ngoài một key.
2. Sử dụng `BinaryCollection.increment` và `decrement`, đọc `CounterResult.content()`.
3. Phân biệt `initial` với `delta`, kể cả khi nhiều writer cùng tạo key.
4. Xử lý unsigned 64-bit, giới hạn Java `long`, việc giảm về 0 và wrap-around.
5. Phân biệt **counter document non-JSON** và **counter field trong JSON** bằng `mutateIn`.
6. Chọn đúng cơ chế cho metrics, sequence, quota, inventory, thống kê materialized và dữ liệu cần transaction.
7. Thiết kế key theo tenant, khoảng thời gian, shard và phạm vi cluster.
8. Hiểu expiry chỉ áp dụng khi tạo counter qua counter operation, cùng tác động của durability và timeout.
9. Đối phó retry ambiguous, duplicate event, idempotency và lệch dữ liệu nguồn.
10. Viết SDK adapter được Spring quản lý, phiên bản reactive và integration test đồng thời.

## 2. Race condition của vòng đọc–cộng–ghi

Giả sử document JSON có:

~~~json
{
  "tenantId": "tenant-01",
  "views": 10
}
~~~

Hai request cùng muốn tăng lượt xem:

~~~text
Thời điểm      Request A               Request B
----------     --------------------    ---------------------
T0             đọc views = 10
T1                                     đọc views = 10
T2             tính 10 + 1 = 11
T3                                     tính 10 + 1 = 11
T4             ghi views = 11
T5                                     ghi views = 11

Kỳ vọng: 12
Kết quả khi ghi đè vô điều kiện: 11
~~~

Đổi `repository.findById(...)` và `save(...)` sang SDK `get(...)` rồi `upsert(...)` **không tự làm thao tác nguyên tử**. Vấn đề không nằm ở kiểu API, mà là việc kiểm tra và cập nhật bị tách thành nhiều bước không có điều kiện cạnh tranh.

Các cơ chế thay thế:

| Cơ chế | Đơn vị thao tác | Khi nào phù hợp |
| --- | --- | --- |
| KV `binary().increment` | Toàn bộ **counter document** | Giá trị số độc lập, tăng/giảm theo key |
| `mutateIn` increment | Field số trong **một JSON document** | Cần giữ thêm metadata ở cùng document |
| Replace kèm CAS | Một document | Có điều kiện “chỉ ghi nếu phiên bản chưa đổi” |
| Transaction | Nhiều thao tác/document trong phạm vi hỗ trợ | Bất biến cần nguyên tử qua nhiều đối tượng |
| SQL++ `COUNT` | Tập row đang khớp query | Muốn đếm hiện trạng dữ liệu theo bộ lọc |

## 3. “Nguyên tử theo khóa” nghĩa là gì?

Một counter có địa chỉ:

~~~text
Cluster/deployment
 └── Bucket: shop
      └── Scope: metrics
           └── Collection: counters
                └── Key: visits::tenant-01::2026-11-25
                     └── Value: 142
~~~

Các thao tác đồng thời vào **cùng document key, trong cùng collection và cùng miền writer của cluster** được server thực hiện nguyên tử theo semantics KV counter.

Những điều **không** suy ra từ đó:

- Increment trên hai key khác nhau không tự thành một transaction chung.
- Increment counter rồi insert Order là hai thay đổi độc lập nếu không có transaction/phối hợp.
- Timeout không cho biết chắc server đã tăng hay chưa.
- Retry cùng event có thể tạo thêm một lần tăng.
- Hai collection cùng chuỗi key có hai counter độc lập.
- Key hết hạn TTL rồi tạo lại không giữ lịch sử cũ.
- Hai clusters ghi cùng key rồi đồng bộ XDCR không tạo phép cộng toàn cục nguyên tử.

Phân biệt **atomicity của một mutation**, **durability của mutation**, **idempotency của một command** và **snapshot của một tập dữ liệu**. Chúng giải quyết những câu hỏi khác nhau.

## 4. KV counter document không phải JSON entity

Một KV counter lưu giá trị số theo định dạng đặc biệt (ASCII numeric):

~~~text
142
~~~

Nó **không phải** JSON object như:

~~~json
{
  "tenantId": "tenant-01",
  "count": 142
}
~~~

Điều đó có nghĩa:

- Không coi counter là entity Spring Data Couchbase có `@Document`/`@Id`/`@Version` như bình thường.
- Không ghi `repository.save(new CounterEntity(...))` vào cùng key rồi mong `binary().increment` tiếp tục hoạt động.
- Không kỳ vọng SQL++ có thể index/query counter non-JSON theo các field như document JSON.
- Nếu cần thêm tenant, tên metric, timestamp và nhiều số đếm **trong body**, cân nhắc JSON document với sub-document counter.
- Nên có collection `shop.metrics.counters` riêng, tránh trùng đường ghi với `Customer`, `Order` và converter.

Repository/`CouchbaseTemplate` vẫn là lựa chọn phù hợp cho entity JSON. Java SDK direct counter là trường hợp mở rộng thấp tầng khi cần một thao tác KV chuyên biệt.

## 5. Sử dụng `Cluster` do Spring quản lý

Ví dụ Spring Boot/Spring Data đã tạo bean `Cluster` dùng chung. SDK adapter lấy đúng collection:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

@Component
public final class CounterSdkAdapter {

    private final Collection counters;

    public CounterSdkAdapter(Cluster cluster) {
        this.counters = cluster.bucket("shop")
                .scope("metrics")
                .collection("counters");
    }

    // Các method dùng counters.binary().
}
~~~

Trong production, tên bucket/scope/collection nên được lấy từ **trusted application configuration**, không hard-code rải rác hoặc để client chọn tùy ý.

Không gọi `Cluster.connect(...)` trong mỗi request, không đóng `Cluster.disconnect()` trong một method nghiệp vụ và không tạo client thứ hai khi Repository/Template đã có hạ tầng được Spring quản lý. Với multi-cluster có chủ đích, cần bean `@Qualifier` và ownership/lifecycle tường minh.

## 6. Tăng một counter đã tồn tại

SDK có `BinaryCollection` thông qua `Collection.binary()`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.CounterResult;

public long incrementExisting(
        Collection counters,
        String key) {

    CounterResult result = counters.binary().increment(key);
    return result.content();
}
~~~

Giả sử giá trị cũ là 41. Nếu mutation thành công, `result.content()` trả **42**, tức giá trị **sau** phép tăng.

Nếu document key chưa tồn tại và không có `initial`, thao tác có thể trả `DocumentNotFoundException`. Nó không tự tạo counter 1 trong mọi trường hợp.

Muốn cộng một lượng cụ thể:

~~~java
import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

public long addExisting(
        Collection counters,
        String key,
        long amount) {

    if (amount < 1 || amount > 1000) {
        throw new IllegalArgumentException("Invalid amount");
    }

    return counters.binary().increment(
            key,
            incrementOptions().delta(amount))
        .content();
}
~~~

Giới hạn `amount <= 1000` chỉ là **ví dụ chính sách ứng dụng**, không phải giới hạn SDK. Nếu key cũ là 100 và `delta(5)`, giá trị mới là 105.

## 7. `initial` không phải `delta` của lần gọi đầu

Để tạo counter khi key thiếu:

~~~java
long result = counters.binary().increment(
        "visits::tenant-01::2026-11-25",
        incrementOptions()
                .initial(1)
                .delta(1))
        .content();
~~~

Semantics quan trọng:

- **Key chưa tồn tại:** counter được tạo bằng **giá trị `initial`**; `delta` không cộng thêm vào `initial` ngay trong lần tạo.
- **Key đã tồn tại:** `initial` bị bỏ qua; `delta` được cộng vào giá trị hiện tại.
- Việc tạo và tăng của các writer cùng key do server xử lý với semantics counter nguyên tử.

| Trước khi gọi | `initial` | `delta` | Kết quả |
| --- | ---: | ---: | --- |
| Key chưa có | 1 | 1 | **1** |
| Đang có 1 | 1 | 1 | **2** |
| Đang có 2 | 1 | 1 | **3** |
| Key chưa có | 100 | 5 | **100** |
| Đang có 100 | 100 | 5 | **105** |
| Key chưa có | 0 | 1 | **0**, không phải 1 |
| Key chưa có, không truyền initial | — | 1 | Lỗi không tìm thấy document |

Nếu mỗi request đại diện một sự kiện mới và counter chưa có, `initial(1)` là cách đơn giản để sự kiện đầu tiên được tính. Nếu muốn một mốc ban đầu cố định 100, hãy chủ động chọn `initial(100)` theo nghiệp vụ.

**Đừng dùng “check exists → insert → increment”** như giải pháp tạo counter mặc định: nó gây race không cần thiết. Khi cần kiểm soát điều kiện khởi tạo đặc biệt, thiết kế rõ các trường hợp key tồn tại, tạo đồng thời và yêu cầu nhất quán.

## 8. Giảm bằng `decrement`

Ví dụ:

~~~java
import static com.couchbase.client.java.kv.DecrementOptions.decrementOptions;

long after = counters.binary().decrement(
        "active-sessions::tenant-01",
        decrementOptions().delta(3))
    .content();
~~~

Nếu giá trị cũ là 10, giá trị mới là 7.

**KV full-document counter là unsigned**, không âm. Nếu giảm dưới 0, kết quả **được chặn tại 0**. Ví dụ giảm 5 từ 2 không trả -3, cũng không tự báo “không đủ 5 suất” theo nghĩa nghiệp vụ.

Vì vậy `decrement(delta=5)` không thể dùng trực tiếp như một thao tác “trừ năm sản phẩm nếu còn đủ”. Muốn giữ bất biến tồn kho, quota hoặc số dư, cần **conditional mutation** được thực thi nguyên tử với điều kiện.

`DecrementOptions` có thể dùng `initial(...)` để khởi tạo khi key thiếu. Như với increment, initial áp dụng ở lúc tạo; delta áp dụng khi key đã có. Hãy xác định rõ thiếu counter là lỗi, 0, hay một mốc khởi tạo hợp lệ.

## 9. Unsigned 64-bit và Java `long`

Giá trị KV counter Couchbase có miền:

~~~text
0 ... 18446744073709551615
    = 0 ... (2^64 - 1)
~~~

Java `long` lại là **signed 64-bit**:

~~~text
-9223372036854775808 ... 9223372036854775807
~~~

`CounterResult.content()` trả `long`. Nếu giá trị unsigned vượt `Long.MAX_VALUE`, biểu diễn signed trong Java có thể trông như giá trị âm. Có thể định dạng bằng:

~~~java
long rawBits = result.content();
String asUnsigned = Long.toUnsignedString(rawBits);
~~~

Nhưng không nên để hệ thống định danh nghiệp vụ phụ thuộc khả năng giải mã unsigned đó mà không thiết kế toàn bộ JSON/API/database path tương ứng.

Một khác biệt quan trọng khác:

- KV full-document `decrement` **không âm**, chặn tại 0.
- KV full-document `increment` có thể **wrap-around** khi vượt giá trị tối đa unsigned 64-bit.
- Số sau wrap có thể quay về thấp, gây trùng ID nếu key dùng cấp định danh.

Nếu sản phẩm cần sequence lâu dài, chủ động giới hạn miền an toàn (thường không vượt `Long.MAX_VALUE` ở Java), giám sát ngưỡng và thiết kế phương án thay thế trước khi xảy ra wrap. Không “xử lý” overflow bằng cách reset counter đang được dùng để cấp ID.

## 10. CAS và atomic increment giải quyết hai việc khác nhau

Đối với yêu cầu “tăng thêm một đơn vị”, counter không cần vòng get–replace có CAS:

~~~java
long next = counters.binary().increment(key).content();
~~~

Ngược lại, yêu cầu “tăng **chỉ nếu** vẫn còn dưới quota” không được bảo vệ chỉ bởi atomic increment.

`CounterResult` kế thừa thông tin mutation như CAS, nhưng **không vì thế mà `binary().increment(...)` là một thao tác có điều kiện CAS của nghiệp vụ**. CAS dùng để kiểm tra rằng phiên bản document chưa đổi trước khi replace/mutate.

Với JSON document, Spring Data `@Version` hoặc SDK `replaceOptions().cas(expected)` có thể giúp tránh lost update ở mức document. Chúng không tự giữ atomicity khi nghiệp vụ cần cập nhật **nhiều document**.

## 11. Counter ở field JSON bằng sub-document mutation

Nếu số đếm cần nằm chung với metadata:

~~~json
{
  "tenantId": "tenant-01",
  "dayUtc": "2026-11-25",
  "views": 42,
  "likes": 8
}
~~~

Dùng `mutateIn` với `MutateInSpec.increment`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.MutateInResult;
import com.couchbase.client.java.kv.MutateInSpec;
import java.util.List;

public long incrementViews(
        Collection metrics,
        String documentId) {

    MutateInResult result = metrics.mutateIn(
            documentId,
            List.of(MutateInSpec.increment("views", 1)));

    return result.contentAs(0, Long.class);
}
~~~

Lệnh này tăng field `views` trên server mà không thực hiện một full-document read–modify–replace trong Java.

Các điểm cần biết:

1. Document này là **JSON**, không phải full-document binary counter.
2. `"views"` là JSON field name/path thực tế, không nhất thiết giống tên property Java nếu có `@Field`.
3. Nhiều sub-document mutation specs trong **một** `mutateIn` có semantics nguyên tử **một document**.
4. Nếu field chưa có, việc tạo field/parent path có quy tắc cụ thể của sub-document API; cần kiểm thử schema.
5. Không dùng `mutateIn` trên một counter document non-JSON như thể nó có field JSON.
6. SDK raw mutation không tự chạy auditing/lifecycle converter của Spring Data.
7. Nếu Repository còn full-replace cùng document, dùng CAS/`@Version` phù hợp để tránh ghi đè thay đổi của SDK.

## 12. KV counter và sub-document counter có miền số khác nhau

| Khía cạnh | KV counter | Sub-document JSON counter |
| --- | --- | --- |
| Lệnh | `binary().increment/decrement` | `mutateIn(...increment/decrement...)` |
| Body | Scalar non-JSON | JSON object |
| Miền | Unsigned 64-bit | Signed 64-bit theo semantics sub-document |
| Giảm dưới 0 | Chặn về 0 | Có thể âm trong miền hợp lệ |
| Overflow | Có thể wrap | Lỗi khi vượt miền cho phép |
| Field metadata cùng body | Không | Có |
| Mapping entity | Không nên coi là entity JSON | Có thể map JSON, nhưng raw SDK không tự dùng converter |
| Kết quả | `CounterResult.content()` | `MutateInResult.contentAs(index, ...)` |
| Nhiều thay đổi trong một document | Không theo cấu trúc field | Có thể kết hợp sub-doc specs |

Sub-document counter có các quy tắc giới hạn signed và lỗi overflow/underflow cần đọc theo phiên bản SDK. Không tự thay một loại counter bằng loại khác rồi kỳ vọng kết quả âm/overflow giữ nguyên.

## 13. KV counter không phải SQL++ `COUNT(1)`

Muốn đếm số Order đang ở trạng thái PAID:

~~~sql
SELECT COUNT(1) AS totalPaidOrders
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = "PAID";
~~~

Câu `COUNT` tính trên **dữ liệu nguồn đang khớp predicate** theo khả năng index và scan consistency của query. Nó không đọc một counter materialized mà ứng dụng duy trì.

Một counter được cập nhật bằng event:

~~~text
paid-count::tenant-01 = 178392
~~~

có thể khác `COUNT(1)` nếu:

- Event bị mất hoặc đến trễ.
- Event bị xử lý hai lần.
- Order chuyển khỏi PAID nhưng không decrement.
- Có order bị xóa/TTL mà counter không điều chỉnh.
- Counter bị xóa/reset hoặc thay đổi writer.
- Data query và counter được đọc ở hai thời điểm khác nhau.

Không nói KV counter “đếm đúng hơn” chỉ vì mutation nguyên tử. Nó cho biết **giá trị hiện tại của chính counter key**. Sự phù hợp với dataset là trách nhiệm của kiến trúc duy trì counter.

## 14. Dùng counter làm sequence ID: chỉ khi chấp nhận được khoảng trống

Ví dụ cấp số tham chiếu Order:

~~~java
import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

public String allocateOrderRef(
        Collection counters,
        String tenantId) {

    String key = "order-seq::" + tenantId;

    long next = counters.binary().increment(
            key,
            incrementOptions().initial(1).delta(1))
        .content();

    if (next <= 0) {
        throw new IllegalStateException(
                "Counter out of application range");
    }
    return "ORD-" + tenantId + "-" + next;
}
~~~

`tenantId` cần validation và xuất phát từ authenticated context. Trong ví dụ này, quy tắc ID đơn giản chỉ để minh họa; production phải kiểm soát encoding, separator và chính sách sequence.

Điều cần chấp nhận:

- Request cấp được số nhưng tạo Order thất bại → **mất một số**.
- Client timeout sau increment và xin số lại → có thể cấp thêm một số.
- Một số đã cấp không đồng nghĩa một entity đã tồn tại.
- Không dùng TTL cho sequence phải tồn tại lâu dài.
- Không reset, restore hoặc wrap counter khi hệ thống còn cấp ID trên cùng miền.
- Dùng `insert` khi tạo Order theo ID mới để phát hiện trùng, thay vì `upsert` ghi đè document cũ.

Nếu chỉ cần ID duy nhất mà không cần thứ tự liên tiếp, UUID/ULID có thể phù hợp hơn vì không tạo hot counter key tập trung.

### Dãy số không hở là yêu cầu khác

~~~text
increment(order-seq) -> 105
insert(order::105)   -> lỗi
increment(order-seq) -> 106
~~~

Số 105 bị hở là **hành vi có thể xảy ra**, không phải bug atomic counter. Để đáp ứng quy định số chứng từ đặc biệt, cần đặc tả nghiệp vụ và cơ chế phát số/ghi nhận có thể kiểm chứng; một KV counter đơn lẻ không tự cung cấp điều đó.

## 15. Quota/tồn kho: không dùng increment rồi kiểm tra

Giả sử quota là 100 và counter `used=99`:

~~~java
long after = counters.binary().increment(key).content();

if (after > 100) {
    // Đã tăng quá giới hạn rồi.
}
~~~

Nếu hai request đồng thời, chỉ kiểm tra sau increment không ngăn counter vượt quota. Decrement “bù” sau khi phát hiện vượt có thể thất bại, bị retry hoặc đan xen với request khác.

Tương tự, `decrement` từ 2 xuống 0 khi yêu cầu trừ 5 không chứng minh hệ thống còn đủ năm sản phẩm.

Yêu cầu **“chỉ cập nhật nếu điều kiện vẫn đúng”** cần conditional mutation được thực hiện atomically trong cùng document hoặc transaction/phương án khác nếu liên quan nhiều document.

## 16. Mẫu CAS cho quota trong một JSON document

Thay counter non-JSON bằng document JSON:

~~~json
{
  "tenantId": "tenant-01",
  "used": 99,
  "capacity": 100
}
~~~

Ví dụ CAS loop có giới hạn thử:

~~~java
import com.couchbase.client.core.error.CasMismatchException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;

import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

public boolean reserveOne(
        Collection quotas,
        String quotaKey) {

    for (int attempt = 0; attempt < 5; attempt++) {
        GetResult current = quotas.get(quotaKey);
        JsonObject body = current.contentAsObject();

        long used = body.getLong("used");
        long capacity = body.getLong("capacity");

        if (used < 0 || capacity < 0 || used > capacity) {
            throw new IllegalStateException("Bad quota state");
        }
        if (used == capacity) {
            return false;
        }

        body.put("used", used + 1);
        try {
            quotas.replace(
                    quotaKey,
                    body,
                    replaceOptions().cas(current.cas()));
            return true;
        } catch (CasMismatchException conflict) {
            // Writer khác thắng; thử đọc lại trạng thái mới.
        }
    }
    throw new IllegalStateException("Quota too contended");
}
~~~

Đối với **một JSON document**, replace chỉ thành công nếu CAS vẫn khớp phiên bản đã đọc. Nếu writer khác cập nhật trước, code đọc lại và kiểm tra quota trên dữ liệu mới.

Nhưng nếu cần vừa giữ quota **vừa tạo Invitation document**, đó là bất biến **hai document**. CAS loop này vẫn không tạo transaction cho Invitation; cần idempotency/transaction hoặc thiết kế khác.

Khi replace full document, chú ý TTL, schema, auditing, quyền tenant và mọi writer Spring Data khác. Không lặp vô hạn khi CAS mismatch và không nuốt lỗi timeout/quyền như một CAS conflict bình thường.

## 17. TTL: thời hạn counter áp dụng lúc tạo

Ví dụ một key đếm lượt truy cập theo ngày:

~~~text
visits::tenant-01::2026-11-25
visits::tenant-01::2026-11-26
~~~

SDK có thể đặt expiry:

~~~java
import java.time.Duration;
import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

long dayCount = counters.binary().increment(
        "visits::tenant-01::2026-11-25",
        incrementOptions()
                .initial(1)
                .delta(1)
                .expiry(Duration.ofDays(8)))
    .content();
~~~

**Quan trọng:** Theo SDK `IncrementOptions`, `expiry(...)` được áp dụng khi counter **mới được tạo**. Nếu key **đã tồn tại**, option expiry bị bỏ qua và thời hạn hiện có được giữ. Increment không tự biến TTL thành “8 ngày kể từ lần tăng gần nhất”.

Hệ quả:

1. TTL có thể tính từ thời điểm key được tạo, không phải từ đầu ngày báo cáo.
2. Nếu cần hết hạn tại một mốc cố định, cân nhắc `expiry(Instant)` theo phiên bản hỗ trợ.
3. Late event sau khi key đã hết hạn có thể **tạo lại** counter từ initial, mất giá trị cũ.
4. Bucket/collection `maxTTL` và các operation khác có thể ảnh hưởng expiry.
5. Nếu cần đổi TTL của counter đã tồn tại, xem API `touch` phù hợp; không trông chờ increment làm mới.
6. Không dùng TTL trên counter cấp số lâu dài nếu reset làm mất tính duy nhất.

Với `DecrementOptions.expiry(...)` cũng cần hiểu caveat tương tự khi counter đã tồn tại.

## 18. Time bucket phải có định nghĩa nghiệp vụ

Key `2026-11-25` có thể chỉ ngày UTC hoặc ngày theo timezone cửa hàng. Hai nghĩa khác nhau khi sự kiện xảy ra sát nửa đêm.

Nên quy định:

- Dùng timestamp event hay timestamp xử lý?
- Chọn timezone nào, ví dụ `UTC` hay `Asia/Ho_Chi_Minh`?
- Chấp nhận sự kiện đến trễ trong bao lâu?
- Event sau thời hạn đóng sổ có được làm thay đổi counter cũ không?
- Khi đổi chính sách timezone, có thêm version của key schema không?
- Có bao nhiêu ngày dữ liệu phải được giữ trước khi TTL dọn?

Ví dụ key format:

~~~text
metric :: tenant-id :: yyyy-MM-dd :: timezone/version

visits::tenant-01::2026-11-25::UTC
~~~

Không dùng timezone mặc định của server bất kỳ để phân loại ngày trong hệ thống nhiều instance có timezone khác nhau. Cần phân biệt **TTL dọn dữ liệu** với **quy tắc event-time của phép đếm**.

## 19. Durability làm mạnh hơn xác nhận ghi, không thêm transaction

KV counter hỗ trợ durability option:

~~~java
import com.couchbase.client.java.durability.DurabilityLevel;
import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

long next = counters.binary().increment(
        key,
        incrementOptions()
                .initial(1)
                .delta(1)
                .durability(DurabilityLevel.MAJORITY))
    .content();
~~~

`DurabilityLevel.MAJORITY` là yêu cầu xác nhận sao chép theo semantics durable writes, có thể tăng latency/chi phí.

Không đồng nhất:

| Thuộc tính | Atomic counter tự bảo đảm? |
| --- | --- |
| Hai increments cùng key không bị lost update như get–upsert | Có trong phạm vi single-cluster KV operation |
| Đạt mức durability yêu cầu | Theo option và kết quả mutation |
| Counter và Order cùng commit | Không |
| Business request retry không bị tính hai lần | Không |
| Không có gap trong số sequence | Không |
| Không mất dữ liệu trong mọi thảm họa/restore | Không |
| Giữa hai datacenter XDCR luôn cùng tổng | Không |

Khi chọn durability, đo p95/p99 latency và xử lý lỗi/timeout ambiguous. Nếu một counter mang giá trị kế toán hoặc ID quan trọng, còn cần phương án backup/restore, audit và đối soát, không chỉ tăng durability.

## 20. Timeout và retry: mutation nguyên tử vẫn có thể bị nhân đôi

Kịch bản:

~~~text
Client gửi increment(+1).
Server tăng 40 -> 41 thành công.
Phản hồi bị mất / client timeout.
Client không biết thao tác đã thực hiện hay chưa.
Client retry increment(+1).
Server có thể tăng 41 -> 42.
~~~

Mỗi phép tăng độc lập **đều nguyên tử**, nhưng **một logical event đã bị tính hai lần**.

Phải tách:

- **Success:** nhận `CounterResult` và giá trị mới.
- **Failure rõ ràng trước mutation:** đánh giá retry theo nguyên nhân.
- **Ambiguous timeout:** không thể suy ra chưa tăng; retry mù nguy hiểm.
- **Durability ambiguity:** trạng thái mutation chưa chắc đạt yêu cầu; cần chính sách đối soát.

Đừng dùng `onErrorResume(... -> Mono.just(0L))` hay `catch (Exception) { return 0; }` để giấu sự bất định: trả 0 có thể khiến downstream tin nhầm đây là số thật.

### Khi cần exactly-once theo business event

Cần idempotency key/event ID và trạng thái đã xử lý được lưu bền vững. Nếu phải cập nhật event marker **và** counter ở hai document, chuỗi “kiểm tra marker rồi increment” **không nguyên tử**; có race/partial failure.

Cân nhắc transaction/thiết kế event log và materialized view có deduplication, hoặc xử lý lại từ nguồn có khả năng đối soát. Exactly-once ở cấp nghiệp vụ phức tạp hơn atomicity của một phép tăng.

## 21. Một counter được duy trì từ dữ liệu nguồn có thể bị lệch

Giả sử `paid-count::tenant-01` tăng khi Order chuyển sang PAID. Có hai thao tác:

~~~text
Order.status -> PAID
             \
              +--> Increment paid-count
~~~

Nếu không có cơ chế phối hợp:

- Lưu Order thành công nhưng increment thất bại → thiếu.
- Increment thành công nhưng lưu Order thất bại → thừa.
- Duplicate event → thừa.
- Chuyển PAID sang CANCELLED không decrement → thừa.
- TTL/xóa Order không phản ánh vào counter → lệch.
- Late event làm counter trễ so với trạng thái hiện tại.

Một dashboard chấp nhận eventual consistency có thể dùng materialized counter và định kỳ **reconciliation** bằng SQL++ `COUNT(1)`/aggregation trên dữ liệu nguồn.

Nếu số liệu phục vụ thanh toán/kiểm kê yêu cầu mạnh, phải thiết kế source-of-truth, outbox/transaction/idempotency và lịch sử thay đổi phù hợp. Counter per key không tự trở thành sổ cái.

## 22. XDCR: đừng ghi cùng counter tại hai datacenter

Couchbase XDCR có thể đồng bộ document giữa các clusters. Nhưng **hai clusters ghi cùng một counter key đồng thời không biến hai increments thành phép cộng toàn cục**.

Ví dụ:

~~~text
Cluster A có x = 10
Cluster B có x = 10

A increment x -> 11
B increment x -> 11

XDCR đồng bộ: không bảo đảm x cuối = 12.
~~~

Mô hình an toàn hơn:

1. Chọn **single-writer** cho mỗi miền counter quan trọng.
2. Hoặc tách key theo datacenter, ví dụ `visits::dc-a` và `visits::dc-b`, rồi tổng hợp kết quả theo chính sách.
3. Thiết kế failover để tránh hai writers cùng cấp số trong thời gian chuyển vùng.
4. Không dùng sequence per-key active-active cho ID phải duy nhất toàn cục nếu chưa có điều phối bổ sung.

**Atomic per-key trong một cluster không suy ra atomic global counter xuyên XDCR.**

## 23. Hot key: một khóa không scale vô hạn

Nếu mọi request đều gọi:

~~~text
increment("visits::global")
~~~

thì toàn bộ lưu lượng mutation tập trung lên **một key**. Có thể xuất hiện queueing, latency tail cao, timeout hoặc áp lực lên node/vBucket phục vụ key đó.

Không có một ngưỡng increments/giây chung cho mọi deployment. Phải đo thực tế theo topology, replication, durability, network và tải khác.

### Sharded counters

Phân phối event lên nhiều key:

~~~text
visits::global::shard-00
visits::global::shard-01
...
visits::global::shard-31
~~~

Mỗi event tăng một shard, khi đọc tổng thì cộng các shard.

**Đổi lại:**

- Có thể tăng throughput ghi do giảm hot key.
- Đọc tổng phải thực hiện nhiều KV gets hoặc đường aggregate được thiết kế.
- Không có snapshot nguyên tử của mọi shard chỉ bằng việc đọc tuần tự.
- Chuyển số shard cần version/migration policy.
- Timeout, duplicate event, XDCR và độ đúng vẫn phải xử lý.

Chỉ sharding khi có benchmark chứng minh hot key là nút thắt, thay vì mặc định thêm phức tạp.

## 24. Key design và multi-tenancy

Một cấu trúc thường dùng:

~~~text
type :: tenant :: time-window :: optional-shard

visits::tenant-01::2026-11-25::s03
paid-count::tenant-01
order-seq::tenant-01
likes::post-abc123
~~~

Quy tắc:

- Tenant lấy từ **authenticated context**, không tin nguyên chuỗi client gửi.
- Chuẩn hóa các key components, delimiter, Unicode và độ dài UTF-8.
- Không cho phép client chọn tùy ý bucket/scope/collection.
- Không đưa PII/secret vào key và logs nếu không cần.
- Định nghĩa rõ ngày theo timezone nào.
- Chọn collection riêng để phân quyền và lifecycle counters khi hợp lý.
- Bổ sung validation/rate limit cho endpoint tăng số, đặc biệt nếu số dùng cho billing/quota.
- Phân biệt cùng chuỗi ID trong hai collections là hai document khác nhau.

Biết counter key **không đồng nghĩa** có quyền increment/decrement key đó. SDK credential của service có thể có RBAC rộng; application phải áp dụng authorization theo tenant và nghiệp vụ.

## 25. SDK adapter sau domain port

Không phát tán `BinaryCollection` và tên collection vào controller. Tạo port thể hiện ý định:

~~~java
public interface VisitCounterPort {
    long recordVisit(String tenantId, String dayUtc);
}
~~~

SDK adapter:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

@Component
public final class CouchbaseVisitCounterAdapter
        implements VisitCounterPort {

    private final Collection counters;

    public CouchbaseVisitCounterAdapter(Cluster cluster) {
        this.counters = cluster.bucket("shop")
                .scope("metrics")
                .collection("counters");
    }

    @Override
    public long recordVisit(String tenantId, String dayUtc) {
        // Minh họa: tenantId và dayUtc đã được xác thực,
        // chuẩn hóa tại application boundary.
        String key = "visits::" + tenantId + "::" + dayUtc;

        return counters.binary().increment(
                key,
                incrementOptions().initial(1).delta(1))
            .content();
    }
}
~~~

Đây là ví dụ cấu trúc, chưa phải endpoint production đầy đủ: cần auth, key-validation, expiry, durability, timeout, monitoring và chính sách retry.

Lợi ích: mọi nơi dùng cùng initial/key format, đổi thiết kế sharding dễ hơn, unit test có thể mock port và integration test tập trung vào Couchbase thật.

## 26. Reactive atomic counter

Java SDK có API reactive trên collection:

~~~java
import com.couchbase.client.java.Collection;
import reactor.core.publisher.Mono;

import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

public Mono<Long> recordVisitReactive(
        Collection counters,
        String key) {

    return counters.reactive()
            .binary()
            .increment(
                    key,
                    incrementOptions().initial(1).delta(1))
            .map(result -> result.content());
}
~~~

`Mono<Long>` phát giá trị counter sau mutation nếu thành công. Reactive không thay đổi tính nguyên tử của server và **không bổ sung idempotency**.

### Tránh blocking trong WebFlux

~~~java
// SAI: Mono.just thực thi biểu thức blocking ngay lúc tạo Mono.
Mono<Long> bad = Mono.just(
        counters.binary().increment(key).content());
~~~

~~~java
// SAI trong event-loop: block một thao tác reactive.
Long bad = counters.reactive().binary()
        .increment(key)
        .map(result -> result.content())
        .block();
~~~

Nếu cần nhiều mutations:

~~~java
Flux.fromIterable(counterKeys)
        .flatMap(key ->
                counters.reactive().binary().increment(key),
                16);
~~~

`flatMap(..., 16)` giới hạn số publisher con đang thực thi đồng thời, **không** biến nhiều increments thành một transaction, không tự giữ thứ tự kết quả và không giải quyết duplicate event. Cần quản lý subscription/lifecycle, kết quả và lỗi trong pipeline của ứng dụng.

## 27. Lỗi cần phân biệt trong SDK counter

| Tình huống | Phản ứng nên thiết kế |
| --- | --- |
| Key thiếu, không truyền initial | Not found; xác định khởi tạo hay lỗi dữ liệu |
| Key chứa JSON/sai định dạng counter | Báo lỗi schema, không tự overwrite |
| `delta`/`initial` sai policy | Validate trước khi gửi mutation |
| Timeout/ambiguous | Không retry mù, dùng idempotency/đối soát |
| Durability không đạt | Phân loại theo operation và policy |
| Không đủ quyền | Trả lỗi/audit, không fallback sang quyền rộng |
| Counter bị TTL reset | Xác minh time-window lifecycle |
| Giá trị gần overflow | Chặn/đổi chiến lược |
| Hot key | Benchmark rồi cân nhắc shard |
| Writer đa datacenter | Single-writer hoặc key riêng |
| Counter lệch COUNT nguồn | Reconciliation/materialized projection repair |

Không đổi mọi lỗi thành “0 lượt” hoặc “không có dữ liệu”, vì điều đó che một mutation ambiguous có thể đã thành công.

## 28. Integration test atomicity với nhiều writer

Seed một key test mới, gửi `N=100` increments đồng thời và đợi **tất cả** hoàn tất thành công:

~~~text
Given:
  test key chưa tồn tại
  N=100 calls với initial=1, delta=1

When:
  chạy đồng thời N calls và đợi mọi call thành công

Then:
  kết quả cuối của counter là N
  N kết quả trả về phân biệt nhau
~~~

Không assert task A “phải nhận 1” hay task B “phải nhận 2”: thứ tự **completion** khác thứ tự server thực hiện.

Điều kiện kiểm thử:

1. Key riêng mỗi lần chạy, không bị writer ngoài test sử dụng.
2. Không có timeout được bỏ qua.
3. Chạy trên Couchbase thật/Testcontainers/cụm thử nghiệm đúng phiên bản.
4. Không đọc số cuối khi publisher/future còn đang chạy.
5. Cleanup key test an toàn, không xóa dữ liệu production.

Test thêm: hai request cùng tạo key, delta lớn hơn 1, counter missing, key ở hai collections, counter sai định dạng, underflow về 0, ttl expire/tái tạo và policy durability.

## 29. Test những bất biến mà counter không bảo đảm

### Test A — Quota

~~~text
Given used=99, capacity=100
When  hai request cùng reserve một slot
Then  chỉ một request thành công
And   used không vượt 100
~~~

Dùng CAS conditional mutation/transaction phù hợp, **không** raw increment rồi chỉ trả lỗi khi vượt 100.

### Test B — Sequence gap

~~~text
When  increment order-seq -> 105
And   tạo Order thất bại
Then  số 105 có thể bị hở
~~~

Nếu yêu cầu không cho phép gap, kỹ thuật này **chưa đáp ứng**.

### Test C — Retry cùng event

~~~text
Given eventId="evt-42"
When  gửi cùng event hai lần
Then  chỉ tính một lần nếu hợp đồng yêu cầu
~~~

Atomic increment riêng lẻ **không tạo được Then**; kiểm thử idempotency/transaction của tầng nghiệp vụ.

### Test D — XDCR

Hai clusters ghi cùng key trong XDCR hai chiều. Không giả định hai increments được hợp nhất thành tổng cộng hai đơn vị.

### Test E — Đồng bộ với nguồn

Seed Order PAID, so `COUNT(1)` với materialized counter; tạo duplicate event, order cancel, TTL/delete và kiểm tra cơ chế reconciliation.

## 30. Benchmark và quan sát vận hành

Nên theo dõi:

| Chỉ số | Mục đích |
| --- | --- |
| Increments/s trên key nóng | Nhận ra nút thắt per-key |
| p50/p95/p99 mutation latency | Tail latency theo tải |
| Timeout/ambiguity rate | Rủi ro retry không chắc chắn |
| Durability overhead | Chi phí của `MAJORITY` |
| CPU/heap/network | Tài nguyên client và server |
| Shard skew | Tải shard có đều không? |
| TTL resets | Key hết hạn/tái tạo trái chính sách |
| Chênh với SQL++ COUNT nguồn | Phát hiện materialized counter lệch |
| Duplicate event rate | Kiểm tra idempotency |
| Giá trị gần ngưỡng số | Ngăn overflow/wrap |

Không so throughput một phép tăng đơn với transaction nhiều document rồi kết luận kỹ thuật có atomic counter “tốt hơn”: chúng đáp ứng yêu cầu độ đúng khác nhau.

## 31. Ma trận lựa chọn

| Yêu cầu | Lựa chọn khởi đầu | Giới hạn |
| --- | --- | --- |
| Metrics lượt xem gần realtime | KV counter | Cần duplicate policy/đối soát |
| Lượt truy cập theo ngày | KV counter có time-bucket + TTL | Expiry chỉ lúc tạo, late event có thể reset |
| Field views trong JSON entity | Sub-document increment | Không phải KV full-document counter |
| Dãy số nội bộ chấp nhận gap | KV counter không TTL | Quản lý overflow, restore, timeout |
| Mã chứng từ bắt buộc không gap | Thiết kế nghiệp vụ riêng | Counter đơn lẻ không đủ |
| Quota không vượt N | CAS/transaction | Raw increment không check-and-set |
| Trừ tồn kho khi đủ hàng | CAS/transaction/inventory model | Decrement về 0 không chứng minh đủ lượng |
| Count document hiện tại theo filter | SQL++ COUNT | Chi phí index/query; semantics hiện trạng |
| Số liệu dashboard nhanh | Materialized counter/projection | Phải duy trì và reconcile |
| Counter global trên XDCR active-active | Single-writer/key per DC | Không có global atomic increment mặc định |
| Write throughput per-key cực cao | Benchmark/sharded counters | Tổng đọc không snapshot nguyên tử |
| Logical event đúng một lần qua retry | Idempotency + transaction/log | Atomic mutation chỉ một phần |

## 32. Checklist code review

### API, dữ liệu và miền số

- [ ] Counter key/collection tách biệt với JSON entity cần Repository mapping.
- [ ] `initial` và `delta` có semantics được ghi rõ.
- [ ] Giá trị `CounterResult.content()` được giới hạn theo miền nghiệp vụ.
- [ ] Có chính sách tránh unsigned wrap nếu dùng để cấp ID.
- [ ] Không dùng decrement floor-zero làm phép “trừ khi đủ”.
- [ ] Không dùng get–upsert không CAS để mô phỏng tăng nguyên tử.
- [ ] Khi muốn JSON field, chọn `mutateIn` và hiểu signed/overflow.

### Phạm vi và lifecycle

- [ ] Sử dụng Spring-managed `Cluster`/`Collection`.
- [ ] Key có tenant/time-window/shard khi cần; tenant được xác thực.
- [ ] Không cho client chọn keyspace hoặc amount vô giới hạn.
- [ ] Không dùng TTL cho sequence phải tồn tại lâu dài.
- [ ] Biết expiry counter operation chỉ áp dụng khi tạo.
- [ ] Có chiến lược XDCR single-writer/failover.
- [ ] Hot key có benchmark và monitoring.

### Tính đúng và vận hành

- [ ] Durability option phù hợp.
- [ ] Timeout/ambiguous không retry mù.
- [ ] Business events quan trọng có idempotency.
- [ ] Materialized counter có đối soát/rebuild.
- [ ] Quota/inventory không chỉ dùng increment/decrement thô.
- [ ] Có concurrency tests, lỗi, TTL và security tests.
- [ ] Reactive không `block()` trong event-loop.

## 33. Bài tập thực hành

**A. Đếm lượt xem theo ngày**

1. Tạo collection `shop.metrics.counters`.
2. Định nghĩa key `visits::{tenant}::{dayUtc}`.
3. Inject Spring-managed `Cluster`.
4. Tăng bằng `incrementOptions().initial(1).delta(1)`.
5. Đặt TTL tám ngày, kiểm tra increment sau đó không refresh expiry.
6. Gửi 100 increments đồng thời, kiểm tra tổng khi tất cả thành công.
7. Viết variant reactive với `counters.reactive().binary().increment`.
8. Giả lập timeout rồi retry, mô tả vì sao có thể đếm hai lần.

**B. Cấp số tham chiếu đơn hàng**

1. Dùng key `order-seq::tenant-01` không TTL.
2. Tăng và tạo Order với `insert` theo ID mới.
3. Giả lập lỗi insert sau increment: ghi nhận gap.
4. Thiết kế idempotency cho create command.
5. Mô tả cách nhận biết counter bị reset sau restore/failover.
6. So sánh với UUID/ULID nếu chỉ cần ID duy nhất.

**C. Quota và điều kiện**

1. Tạo JSON document có `used`, `capacity`.
2. Viết CAS loop hữu hạn để reserve một suất.
3. Gửi hai request đồng thời lúc `used=capacity-1`.
4. Chỉ một request được chấp nhận.
5. Thêm yêu cầu tạo Invitation document, chỉ rõ cần cơ chế gì để quota và Invitation nhất quán.
6. Giải thích vì sao raw decrement không thay thế check-and-set.

### Câu hỏi tự kiểm tra

1. “Atomic theo khóa” có tự đảm bảo hai document commit cùng nhau không?
2. KV counter khác JSON sub-document counter thế nào?
3. Khi key thiếu, `initial(100).delta(5)` trả bao nhiêu?
4. Khi key đã có 100, lời gọi đó trả bao nhiêu?
5. Decrement 5 từ giá trị 2 có trả -3 không?
6. Vì sao Java `long` có thể hiển thị giá trị unsigned lớn như số âm?
7. CAS có cần cho increment đơn giản không?
8. Vì sao increment rồi kiểm tra quota có thể sai?
9. TTL trong `IncrementOptions` có refresh ở mọi increment không?
10. Vì sao timeout rồi retry có thể đếm hai lần?
11. Counter sequence vì sao có gap?
12. `COUNT(1)` SQL++ và KV counter khác nhau ở nguồn sự thật nào?
13. Việc chia shards cải thiện write throughput bằng cách nào, đổi lại điều gì?
14. Vì sao XDCR hai chiều không có global atomic counter tự động?
15. Những kiểm thử nào chứng minh atomicity mà không đánh đồng exactly-once?

## 34. Tài liệu chính thức và đối chiếu phiên bản

- [Couchbase Java SDK — KV Data Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): atomic counters, expiry, durability và XDCR.
- [Couchbase Java SDK — Documents/Counters](https://docs.couchbase.com/java-sdk/current/concept-docs/documents.html): định dạng counter, unsigned range và semantics increment/decrement.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): field counter, atomicity trong document và signed range.
- [Java SDK API — BinaryCollection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/BinaryCollection.html): `increment/decrement`.
- [Java SDK API — IncrementOptions](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/IncrementOptions.html): `initial`, `delta`, `expiry` và durability.
- [Java SDK API — DecrementOptions](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/DecrementOptions.html): `delta`, `initial` và expiry.
- [Java SDK API — CounterResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/CounterResult.html): `content()` trả giá trị sau mutation.
- [Java SDK API — ReactiveBinaryCollection](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/ReactiveBinaryCollection.html): `Mono<CounterResult>` cho reactive counter.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): mapping/entity operations và khả năng mở rộng SDK.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD entity và optimistic locking.
- [Couchbase Server — SQL++ Aggregate Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/aggregatefun.html): `COUNT`/aggregation trên dữ liệu nguồn.

Các ví dụ dùng API phổ biến của **Couchbase Java SDK 3.x**. Khi triển khai, kiểm chứng chữ ký API, converter, option durability/expiry và kết quả tích hợp trên phiên bản Couchbase Server, Java SDK và Spring Data Couchbase đã khóa. Vòng QA học thuật/biên dịch tích hợp đầy đủ thuộc giai đoạn kiểm thử sau bước viết nội dung.

> **Ghi nhớ:** **KV atomic counter bảo vệ phép tăng/giảm trên một key khỏi lost update, không bảo vệ toàn bộ quy trình nghiệp vụ.** Chọn KV counter cho số đơn giản theo key, sub-document counter cho field JSON, CAS khi cần điều kiện, transaction/idempotency khi phải giữ bất biến nhiều thao tác. Luôn hiểu `initial`, `delta`, unsigned range, TTL chỉ lúc tạo, rủi ro XDCR và retry ambiguous trước khi sử dụng counter cho quota, tồn kho hoặc định danh quan trọng.
