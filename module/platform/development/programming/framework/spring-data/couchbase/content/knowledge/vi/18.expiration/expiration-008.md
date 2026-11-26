# Dữ liệu đã hết hạn và thời điểm kết quả đọc phản ánh trạng thái mới

## 1. Vấn đề: document hết hạn rồi, tại sao các cách đọc chưa luôn giống nhau?

Một giỏ hàng được đặt TTL 30 phút, một mã xác minh có hạn 5 phút và một phiên đăng nhập bị thu hồi khi người dùng đăng xuất. Chúng đều có thể dẫn đến trạng thái “không còn được sử dụng”, nhưng các tầng quan sát không nhất thiết nhìn thấy thay đổi vào đúng cùng một mili giây:

- Một phép **Key-Value GET** trên document đã hết hạn thường trả kết quả **không tìm thấy** khi Data service kiểm tra expiry.
- **SQL++** sử dụng Query service và thường dựa trên chỉ mục được cập nhật bất đồng bộ. Việc một index entry biến mất có thể xảy ra sau mốc document hết hạn.
- Một **cache của ứng dụng**, HTTP cache hoặc bản sao dữ liệu ở hệ thống khác có thể vẫn giữ kết quả đã đọc trước khi document hết hạn.
- Một request GET bắt đầu trước hạn nhưng hoàn tất sau hạn có thể trả nội dung đã hợp lệ ở thời điểm xử lý; thời gian người dùng nhận response không phải bằng chứng dữ liệu còn hiệu lực khi họ sử dụng.

Chủ đề của bài là **“Dữ liệu đã hết hạn và thời điểm kết quả đọc phản ánh trạng thái mới”**, thuộc chương **Thời gian hết hạn**, module **SPRING_DATA_COUCHBASE**. Module xây dựng tầng truy cập Couchbase bằng document mapping, repository, `CouchbaseTemplate` và truy vấn SQL++; đồng thời thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và lựa chọn API reactive cho hiệu năng, nhất quán và vận hành.

**Sau bài này, bạn có thể:**

1. Phân biệt thời điểm **hết hạn logic**, thời điểm **không đọc được qua KV** và thời điểm **dọn dẹp vật lý/index**.
2. Giải thích ảnh hưởng của expiry pager, truy cập trực tiếp, compaction và cơ chế cập nhật index theo server version.
3. Hiểu vì sao phép KV read và SQL++ query có thể có độ trễ quan sát khác nhau.
4. Sử dụng các tùy chọn query scan consistency mà không nhầm chúng với bảo đảm “TTL đã được quét sạch ngay”.
5. Xử lý kết quả `DocumentNotFoundException`, timeout và race condition một cách đúng nghiệp vụ.
6. Thiết kế deadline nghiệp vụ cho OTP/session/reservation, không chỉ dựa vào TTL như một bộ hẹn giờ chính xác tuyệt đối.
7. Kiểm thử expiry, cập nhật và truy vấn với polling có giới hạn, quan sát metadata và instrumentation phù hợp.

Ví dụ dựa trên **Spring Boot 3.x**, **Spring Data Couchbase 5.x**, **Couchbase Java SDK 3.x** và một Couchbase Server hỗ trợ collection. Chi tiết về lịch chạy expiry pager, thời điểm index cleanup và các tùy chọn query phải được đối chiếu với **phiên bản và cấu hình thực tế**. Bài không giả định một khoảng trễ cố định cho mọi cluster.

## 2. Vòng đời của document có expiry

Xét một mã xác minh:

~~~text
Bucket: commerce
Scope: checkout
Collection: otp_codes
Key: otp::u-42

Nội dung JSON:
{
  "userId": "u-42",
  "failedAttempts": 0,
  "issuedAt": "2026-11-25T10:00:00Z",
  "expiresAt": "2026-11-25T10:05:00Z"
}

Metadata trên Couchbase:
  CAS: ...
  expiry: 2026-11-25T10:05:00Z
~~~

Trường `expiresAt` trong JSON chỉ là dữ liệu nghiệp vụ. **Metadata expiry** mới là dữ liệu được Couchbase sử dụng cho cơ chế hết hạn document. Hai giá trị có thể được đặt nhất quán bằng code, nhưng field JSON **không tự động đặt TTL**.

Một cách nhìn đơn giản:

~~~mermaid
flowchart TD
    A["Document được ghi + expiry metadata"] --> B["Trước deadline: còn hợp lệ"]
    B --> C["Thời gian đạt expiry deadline"]
    C --> D["Hết hạn logic"]
    D --> E["KV truy cập: không coi là document còn hợp lệ"]
    D --> F["Expiry cleanup: xử lý nền / theo truy cập"]
    F --> G["Thông báo thay đổi tới index/replica theo cơ chế server"]
    G --> H["Index, thống kê, lưu trữ dần phản ánh thay đổi"]
~~~

Điểm quan trọng: **hết hạn logic không buộc mọi dữ liệu vật lý, mọi chỉ mục hoặc mọi cache ứng dụng được dọn ở cùng một thời điểm**. Đây là vấn đề về thứ tự quan sát giữa các tầng, không phải một lỗi lập trình Java đơn lẻ.

## 3. Ba “đồng hồ” thường bị nhầm

| Mốc | Ý nghĩa | Điều không được suy ra |
| --- | --- | --- |
| **Expiry deadline** | Thời điểm document được coi là hết hiệu lực theo metadata/server | Dữ liệu đã bị xóa vật lý khỏi mọi nơi ngay lập tức |
| **KV observation time** | Khi một KV operation kiểm tra trạng thái và trả kết quả | Mọi query/index/cache đồng thời thấy cùng trạng thái |
| **Index/cleanup visibility time** | Khi index và các hệ thống phụ trợ phản ánh thay đổi qua cơ chế cập nhật | Đúng bằng deadline đến từng mili giây |

Một timeline minh họa:

~~~text
T0 = 10:00:00  Tạo document, expiry = 10:05:00
T1 = 10:04:59  KV GET được server xử lý trước hạn → có thể thành công
T2 = 10:05:00  Đạt expiry deadline
T3 = 10:05:01  KV GET sau hạn → thường không tìm thấy
T4 > T2        Dọn vật lý / cập nhật index theo cơ chế bất đồng bộ
T5 >= T4       Các thống kê, query plan hoặc cache liên quan đã đồng bộ
~~~

T4 và T5 **không có độ trễ cố định** trong ví dụ; chúng phụ thuộc tải, phiên bản, đường truy cập, index type và cấu hình. T1 minh họa thời điểm server xử lý request, không phải bắt buộc thời điểm client nhận response.

### 3.1. Lỗi suy luận từ thời điểm nhận response

Một request có thể được xử lý lúc 10:04:59.9 và trả về client lúc 10:05:00.1. Lúc người dùng nhận response, hạn đã qua, dù **kết quả đọc đã được xác định trước khi hết hạn**.

Nếu chính sách bảo mật là “không cho sử dụng mã sau 10:05:00”, phải kiểm tra deadline tại **điểm quyết định chấp nhận mã**, không chỉ dựa vào việc một request đọc trước đó đã trả document.

## 4. Hết hạn logic khác với xóa vật lý

Couchbase dùng cơ chế kiểm tra thời gian hết hạn khi truy cập và các tiến trình bảo trì nền để xử lý document hết hạn. Tùy server version, các cơ chế có thể liên quan đến **expiry pager**, việc đọc document và hoạt động dọn dẹp/compaction.

Cần tách hai câu:

- **“Document đã hết hạn, có nên được trả lại như dữ liệu hợp lệ không?”** Đây là vấn đề **logic expiry** và hợp đồng truy cập.
- **“Byte cũ đã được thu hồi hoàn toàn khỏi storage, replica, index, backup chưa?”** Đây là vấn đề **thu gom và quản trị vòng đời vật lý**.

Một `get` trả `DocumentNotFoundException` sau expiry không chứng minh file lưu trữ đã giảm dung lượng hoặc mọi bản backup không còn dữ liệu. Ngược lại, dung lượng ổ đĩa chưa giảm không chứng minh KV expiry không hoạt động.

### 4.1. Vai trò của expiry pager

Expiry pager là cơ chế nền giúp xử lý các item đã hết hạn mà không cần ứng dụng truy cập từng key. Chu kỳ và hành vi cụ thể có thể thay đổi theo phiên bản hoặc cài đặt cluster.

Không nên mã hóa kỳ vọng “pager chắc chắn chạy đúng phút thứ N” trong logic nghiệp vụ. TTL không phải cron job thực thi callback chính xác tại deadline; nó chủ yếu quản lý **khả năng tồn tại hợp lệ và vòng đời** của document.

### 4.2. Vì sao cleanup có thể trễ?

Có nhiều lý do kỹ thuật:

1. Một expired document chưa bị truy cập lại bằng KV.
2. Worker nền hoạt động theo chu kỳ và chịu tải server.
3. Index cần nhận/thực hiện thông báo thay đổi từ Data service.
4. Compaction và giải phóng dung lượng diễn ra trong tiến trình khác.
5. Backup, snapshot, replica hoặc downstream cache có vòng đời dữ liệu riêng.

Mỗi nguyên nhân thuộc một tầng khác nhau. Không dùng một kết quả thống kê storage để thay cho phép kiểm tra document có thể đọc được hay không.

## 5. KV GET: phép kiểm tra trực tiếp cho một key

Nếu đã biết document key, Couchbase Java SDK có thao tác đọc KV:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;

// otpCodes trỏ tới commerce.checkout.otp_codes.
GetResult result = otpCodes.get("otp::u-42");

String userId = result.contentAsObject()
        .getString("userId");
~~~

Khi document đã hết hạn logic tại thời điểm Data service kiểm tra, operation thường xử lý như một document **không tồn tại hợp lệ**. Java SDK có thể phát sinh `DocumentNotFoundException`.

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;

try {
    GetResult result = otpCodes.get("otp::u-42");
    process(result.contentAsObject());
} catch (DocumentNotFoundException ex) {
    handleMissingOrExpiredOtp();
}
~~~

**Không mặc định lỗi not-found có nghĩa “đã hết hạn”.** Cùng lỗi này có thể do key chưa từng được tạo, đã bị xóa có chủ đích hoặc client trỏ sai collection. Nếu cần biết *lý do* biến mất, phải có audit hoặc trạng thái nghiệp vụ bổ sung.

### 5.1. KV GET không cần secondary index

Một lookup theo key qua `Collection.get(id)` sử dụng Data/Key-Value service, không phụ thuộc secondary index SQL++. Vì vậy khi chẩn đoán TTL của **một document có key biết trước**, KV GET là điểm bắt đầu tự nhiên.

Nếu SQL++ không trả document, nhưng KV GET vẫn thành công, cần điều tra query statement, index, scan consistency, bucket/scope/collection và các mutation gần đó, không nên lập tức kết luận “TTL sai”.

### 5.2. Kiểm tra tồn tại với `exists`

SDK có thao tác KV kiểm tra sự tồn tại:

~~~java
var exists = otpCodes.exists("otp::u-42");

if (!exists.exists()) {
    // Có thể chưa từng tồn tại, đã xóa hoặc đã hết hạn.
}
~~~

`exists` không trả nội dung JSON và không phải một phép xác minh toàn bộ trạng thái nghiệp vụ. Đặc biệt, `exists` thành công ngay trước một thao tác khác **không bảo đảm** document còn tồn tại ở thời điểm mutation tiếp theo.

## 6. Đọc metadata expiry trước khi document biến mất

Java SDK 3.x có tùy chọn yêu cầu metadata expiry khi GET:

~~~java
import com.couchbase.client.java.kv.GetOptions;

var result = otpCodes.get(
        "otp::u-42",
        GetOptions.getOptions().withExpiry(true)
);

result.expiryTime().ifPresent(deadline ->
        System.out.println("Expiry deadline: " + deadline)
);
~~~

Mục đích: kiểm tra **mốc expiry hiệu lực đã được server gắn lên document**. `expiryTime()` trong các phiên bản SDK hỗ trợ trả giá trị tùy chọn; cần kiểm tra Javadoc chính xác để hiểu khi không có expiry hoặc metadata không được trả về.

**Giới hạn:** sau khi document đã hết hạn và KV GET trả not-found, bạn thường **không thể đọc metadata của chính document đó bằng GET bình thường**. Vì vậy, với integration test cần khẳng định deadline, hãy đọc metadata ngay **sau mutation** và **trước khi hạn hết**.

### 6.1. Metadata expiry có thể bị thay đổi bởi mutation khác

Đọc expiry lúc 10:02 không bảo đảm giá trị đó vẫn đúng lúc 10:04 nếu một request khác thực hiện:

- `touch(id, Duration.ofMinutes(30))`.
- `getAndTouch(id, ...)`.
- `replace` với expiry mới.
- `upsert` đặt lại TTL.
- Một đường `repository.save` áp metadata mapper theo semantics version.

Muốn có một deadline không được gia hạn cho OTP, code phải kiểm soát **mọi đường ghi**, không chỉ một lần đọc metadata.

## 7. SQL++ và KV không cùng đường quan sát

SQL++ đi qua **Query service**, thường sử dụng **Global Secondary Index (GSI)** hoặc các loại chỉ mục phù hợp để xác định document cần đọc. Index có thể được cập nhật bất đồng bộ khi Data service thay đổi trạng thái document.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Client"] --> B{"Loại đọc?"}
    B -- "KV get(id)" --> C["Data Service / KV lookup"]
    B -- "SQL++ SELECT" --> D["Query Service"]
    D --> E["Index Service / index entries"]
    E --> F["Có thể fetch content từ Data Service"]
    C --> G["Kết quả KV theo thời điểm đọc"]
    F --> H["Kết quả query theo scan + fetch + consistency"]
~~~

Với một số query plan, index có thể đã phản ánh mọi thay đổi; với kế hoạch khác, có thể còn entry chưa được dọn hoặc cần fetch document để xác nhận. **Không khẳng định rằng mọi query đều trả row đã expired hoặc mọi query đều loại row ngay một cách đồng nhất**: kết quả thực phụ thuộc query plan, trạng thái index, cách thực thi và phiên bản server.

Điều chắc chắn cho thiết kế là **SQL++ index không phải chiếc đồng hồ TTL chính xác từng mili giây**. Nếu nghiệp vụ phải kiểm tra quyền sử dụng một key ở thời điểm quyết định, ưu tiên kiểm tra trạng thái/deadline theo một đường được định nghĩa rõ, không lấy một query result rời rạc làm chứng cứ tuyệt đối.

### 7.1. Ví dụ truy vấn SQL++

~~~sql
SELECT META(s).id AS documentId, s.userId
FROM `commerce`.`checkout`.`sessions` AS s
WHERE s.userId = "u-42";
~~~

Statement này yêu cầu một index phù hợp để thực thi hiệu quả. Index không đồng nghĩa một listener tự kích hoạt chính xác khi TTL đến hạn.

Một câu SQL++ SELECT không tự làm mới expiry như `getAndTouch`. Nếu ứng dụng thấy session “mất” khi query nhưng “còn” khi đọc qua một cache khác, phải xét đường truy cập và thời điểm quan sát.

## 8. Scan consistency: giải quyết độ trễ index do mutation, không phải đồng hồ TTL

Couchbase Java SDK cho phép điều khiển **scan consistency** của SQL++ query. Các lựa chọn thường gặp gồm:

- **`NOT_BOUNDED`:** ưu tiên độ trễ/throughput; không đợi index đuổi kịp một tập mutation cụ thể.
- **`REQUEST_PLUS`:** yêu cầu index scan đạt mức nhất quán theo trạng thái mutation được xác định tại lúc query bắt đầu, theo contract của Query service.
- **`AT_PLUS` hoặc nhất quán theo mutation token:** yêu cầu index nhìn thấy ít nhất một số mutation xác định, qua các API tương ứng.

**Điểm rất quan trọng:** một deadline TTL đi qua chỉ vì đồng hồ dịch chuyển **không giống** client vừa phát sinh một mutation token. `REQUEST_PLUS` giúp xử lý độ trễ index đối với mutation đã có, nhưng **không hứa chạy expiry pager ngay hoặc buộc mọi con đường cleanup hoàn tất đúng deadline**.

### 8.1. Ví dụ query `REQUEST_PLUS`

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryScanConsistency;

var result = cluster.query(
        "SELECT META(s).id AS id, s.userId " +
        "FROM `commerce`.`checkout`.`sessions` AS s " +
        "WHERE s.userId = $userId",
        QueryOptions.queryOptions()
                .parameters(JsonObject.create().put("userId", "u-42"))
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

Khi dùng `REQUEST_PLUS`, query có thể cần chờ index, làm tăng latency. Nó có thể hữu ích cho *read-after-write* trong các luồng phù hợp, nhưng không phải phương án “bắt Query Service tự tạo expiry event tại một thời điểm”.

### 8.2. Bảng chọn consistency

| Vấn đề thực tế | Lựa chọn cần đánh giá |
| --- | --- |
| Vừa ghi document, query cần thấy mutation mới | `REQUEST_PLUS` hoặc token-based consistency |
| Cần đọc một key ngay sau ghi | KV GET theo key, không cần GSI |
| Document vừa chạm deadline TTL | KV/metadata và kiểm tra deadline nghiệp vụ; không kỳ vọng consistency tự dọn expiry |
| Query dùng index đang rebuild | Kiểm tra index state, query plan và deadline/timeout |
| Cần báo cáo có thể chấp nhận độ trễ | Có thể dùng `NOT_BOUNDED` theo SLA |
| Cần bảo đảm quyết định nghiệp vụ ngay tại lúc commit | CAS/transaction và kiểm tra deadline; query consistency đơn lẻ không đủ |

Trong những ứng dụng có yêu cầu nhất quán đặc biệt, lựa chọn cần dựa trên query plan thật, kiểm thử trên server version và dữ liệu mô phỏng, không chỉ tên enum.

## 9. Index có thể trễ, nhưng điều đó có nghĩa gì cho người dùng?

Một chỉ mục có thể tạm thời chứa thông tin về key vừa hết hạn. Điều này không tự chứng minh một query đã phát ra row expired: Query service có thể thực hiện thêm bước fetch/validation, tùy plan.

Vì thế cần tách ít nhất ba quan sát:

1. **Index membership:** key còn trong cấu trúc index hay đã bị loại.
2. **Query output:** câu SQL++ có trả row cho client không.
3. **KV output:** một `get(id)` hiện tại có trả document không.

Đây là ba phép đo khác nhau. Một query được che phủ hoàn toàn bởi index (*covered query*) có đường thực thi khác một query cần fetch content; khi cần giải thích chênh lệch, xem `EXPLAIN` và thông tin vận hành phù hợp của server version.

### 9.1. Không lấy `COUNT(*)` làm bộ đếm expired chính xác theo thời gian thực

~~~sql
SELECT COUNT(*) AS sessionCount
FROM `commerce`.`checkout`.`sessions`;
~~~

Giá trị COUNT từ query dựa trên trạng thái và consistency của query/index; nó không phải một phép đếm tức thời độc lập với cleanup, index lag và query execution.

Nếu cần dùng số liệu này cho dashboard, nên định nghĩa độ trễ chấp nhận được và tần suất cập nhật. Không dùng nó như điều kiện bảo mật “chỉ còn đúng N phiên hợp lệ” mà không có bước xác minh chi tiết.

## 10. Kết quả đọc trước hạn có thể trở nên lỗi thời sau một khoảnh khắc

Giả sử:

~~~text
10:04:59.500  GET session thành công
10:05:00.000  Session hết hạn
10:05:00.300  Request bắt đầu thao tác nhạy cảm bằng dữ liệu vừa đọc
~~~

Nếu nghiệp vụ yêu cầu “phải còn hạn tại thời điểm xác nhận”, kết quả GET thành công trước đó **không bảo đảm** phiên còn hạn ở 10:05:00.300.

Điều này là một dạng **time-of-check/time-of-use (TOCTOU)**. Không thể giải quyết chỉ bằng retry GET hoặc tăng `kvTimeout`.

### 10.1. Kiểm tra deadline nghiệp vụ

Có thể lưu `issuedAt` và `expiresAt` trong nội dung nghiệp vụ, đồng thời đặt metadata expiry để dọn dữ liệu:

~~~json
{
  "sessionId": "session::u-42",
  "issuedAt": "2026-11-25T09:00:00Z",
  "expiresAt": "2026-11-25T17:00:00Z",
  "revoked": false
}
~~~

Tại **điểm sử dụng**, service kiểm tra `expiresAt` và trạng thái `revoked` theo thời gian đáng tin cậy. Couchbase expiry giúp document không còn hợp lệ theo policy server, nhưng deadline nghiệp vụ là điều kiện bổ sung cho những thao tác nhạy cảm.

Khi cần tính nhất quán dưới concurrent updates, kết hợp CAS/transaction hoặc cơ chế nghiệp vụ thích hợp để tránh việc một request dùng dữ liệu đã bị thay đổi.

## 11. Spring Data repository: API đọc nào thực sự được gọi?

Một entity ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document(expiry = 300) // 300 giây theo mapping phiên bản hỗ trợ
public class OtpDocument {

    @Id
    private String id;

    private String userId;
    private int failedAttempts;

    protected OtpDocument() {
    }

    public OtpDocument(String id, String userId, int failedAttempts) {
        this.id = id;
        this.userId = userId;
        this.failedAttempts = failedAttempts;
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public int getFailedAttempts() { return failedAttempts; }
}
~~~

Repository:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OtpRepository
        extends CouchbaseRepository<OtpDocument, String> {
}
~~~

Khi gọi `repository.findById(id)`, Spring Data Couchbase thường có thể sử dụng đường **Key-Value** để đọc bằng document key. Với derived query như `findByUserId(...)`, Spring Data có thể dùng **SQL++** và index phù hợp.

Do đó, hai method trong cùng repository có thể không đi qua **cùng một cơ chế đọc**, nhất là khi so sánh exact-key lookup với một query predicate.

**Không được coi `@Document(expiry = 300)` là bằng chứng rằng mọi query luôn thấy đúng kết quả vào đúng giây 300.** Annotation mô tả thời hạn khi mapper ghi; kết quả đọc còn phụ thuộc thời điểm thực thi và các tầng phục vụ đọc.

### 11.1. `findById` và derived query

Ví dụ:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;

public interface OtpSearchRepository
        extends CouchbaseRepository<OtpDocument, String> {

    List<OtpDocument> findByUserId(String userId);
}
~~~

Cách thực thi derived method và tên trường phụ thuộc mapping/repository version. Trong các đường SQL++, cần có index thích hợp; nếu query không thấy document, bắt đầu kiểm tra keyspace, index, consistency rồi mới quy về TTL.

### 11.2. `CouchbaseTemplate`

`CouchbaseTemplate` có các API thao tác entity và truy vấn tùy version. Một lời gọi template đọc entity theo ID và một lời gọi template chạy SQL++ không nên được giả định có chi phí, consistency hoặc lịch quan sát giống nhau.

Khi service yêu cầu **một identity document đã biết**, ưu tiên đường KV khi thích hợp. Nếu cần tìm nhiều document theo predicate, SQL++ đúng công cụ nhưng phải hiểu yêu cầu index và độ trễ.

## 12. Document hết hạn có thể bị ghi mới lại: hiện tượng “hồi sinh”

Một sai lầm logic sau khi GET trả not-found:

~~~java
// Ví dụ không phù hợp cho OTP đã hết hạn:
try {
    otpCodes.get(otpId);
} catch (DocumentNotFoundException ex) {
    otpCodes.upsert(otpId, oldOtpContent);
}
~~~

`upsert` có thể tạo một document mới khi key không còn tồn tại hợp lệ. Nếu đây là OTP đã hết hạn, hành vi đó **phát hành lại mã cũ ngoài luồng xác thực**.

Với session/OTP/reservation:

1. Khi read không tìm thấy, phân loại “không tồn tại/hết hạn” theo chính sách.
2. Không tự tạo lại cùng dữ liệu chỉ để xử lý lỗi.
3. Nếu cần cấp mới, dùng luồng phát hành mới có authorization và identity/idempotency.
4. Nếu đang có concurrent writers, dùng CAS hoặc transaction theo yêu cầu nhất quán.
5. Với thao tác mutation timeout, không suy rằng server chưa ghi.

### 12.1. Replace khác upsert

`replace(id, json, ...)` yêu cầu document đang tồn tại; nếu đã hết hạn, nó thường không tạo mới. `upsert(id, json, ...)` có thể tạo mới.

Lựa chọn thao tác là một phần của semantics: “sửa mã còn sống” khác “tạo mã mới”. Expiry chỉ giúp dữ liệu hết hiệu lực; nó không tự bảo vệ ứng dụng khỏi một luồng upsert viết sai.

## 13. GET-AND-TOUCH có thể làm chính đồng hồ hạn thay đổi

`getAndTouch` là một lệnh đọc **có tác dụng đổi expiry**:

~~~java
import java.time.Duration;

var result = carts.getAndTouch(
        "cart::u-42",
        Duration.ofMinutes(30)
);
~~~

Khi operation thành công, document được đọc và expiry metadata được đặt lại. Vì vậy nếu sau đó query vẫn thấy cart “sống lâu hơn”, cần kiểm tra có một đường code đang gia hạn không.

So sánh:

| Phép đọc | Có thể đổi expiry? |
| --- | --- |
| SDK `get(id)` | Không theo mặc định |
| SDK `exists(id)` | Không phải API gia hạn |
| `getAndTouch(id, Duration)` | **Có** |
| SQL++ SELECT thông thường | Không tự gia hạn |
| Repository finder thông thường | Không mặc định gọi TOUCH |
| Cache getter tùy biến | Có thể gia hạn cache TTL riêng, không đồng nghĩa Couchbase document TTL |

Tránh dùng `getAndTouch` cho OTP hoặc token có thời hạn cố định. Nếu session có hard deadline, phải kiểm tra nó trước khi làm mới hạn theo chính sách, không chỉ truyền một relative Duration.

## 14. Dữ liệu đọc từ cache ứng dụng không phải một lần đọc Couchbase

Ngoài Couchbase, hệ thống có thể có:

- Spring `@Cacheable` với Caffeine hoặc Redis.
- Cache trong gateway/API.
- HTTP caching bằng Cache-Control/ETag.
- Cache ở frontend hoặc CDN.
- Bản sao dữ liệu trong search service hay analytics pipeline.

Một cache hit có thể trả dữ liệu đã từng được đọc **trước** expiry, mà không liên hệ Couchbase ở lần request hiện tại.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Application cache hit?"}
    B -- "Có" --> C["Trả cached value"]
    B -- "Không" --> D["Spring Data / SDK"]
    D --> E["Couchbase KV / Query"]
    E --> F["Kết quả theo server observation"]
    F --> G["Có thể lưu vào cache với TTL riêng"]
~~~

**Không đồng nhất TTL của cache với expiry metadata của Couchbase.** Nếu Couchbase TTL = 5 phút mà cache TTL = 30 phút, một client có thể thấy document qua cache dù key trên Couchbase đã hết hạn. Đây là lỗi chính sách cache, không phải bằng chứng Data service bỏ qua expiry.

### 14.1. Cache phải có deadline riêng phù hợp

Với dữ liệu nhạy cảm hoặc có expiry cố định:

1. Lưu deadline khi cache giá trị.
2. Không trả cache hit nếu deadline đã qua.
3. Đặt TTL cache **không vượt** thời gian còn hiệu lực theo policy.
4. Invalidate khi logout/revoke hoặc mutation liên quan.
5. Với quyết định quan trọng, kiểm tra trạng thái tại điểm commit, không chỉ dựa vào một cache hit cũ.

Khi nhiều cache cùng tham gia, cần một sơ đồ ownership và chính sách invalidation thống nhất.

## 15. Replica reads và quá trình lan truyền thay đổi

Trong cluster Couchbase, dữ liệu có thể được replicate giữa các node. Tùy đường API và cấu hình read preference, một số đường đọc có thể liên quan tới replica. Thời điểm replica nhận mutation và thời điểm server xử lý expiry có thể không trùng ngay.

Không nên hứa rằng **một lần đọc từ node bất kỳ ở mọi cơ chế** sẽ có cùng quan sát tại một mili giây sát deadline. Đặc biệt khi ứng dụng dùng API đọc replica hoặc có cơ chế failover, cần xem contract của đường đọc đang dùng và kiểm thử.

### 15.1. Khi nào nên đọc replica?

Việc dùng API đọc replica là một lựa chọn về availability/latency và semantics consistency. Với một session/OTP cần kiểm tra hiệu lực mạnh, đừng tự chuyển sang một đường replica read chỉ vì nhanh hoặc giảm tải mà chưa đánh giá khả năng quan sát trạng thái mới.

Kết quả từ replica, cache hoặc index có thể cần **validation thêm** trước hành động nhạy cảm.

## 16. Đọc thất bại vì timeout khác với document hết hạn

Một phép GET có thể thất bại vì nhiều lý do:

| Tín hiệu | Kết luận an toàn |
| --- | --- |
| `DocumentNotFoundException` | Key không tồn tại hợp lệ ở thời điểm thao tác; có thể expired, removed hoặc chưa từng tồn tại |
| `TimeoutException` | Không có response đúng deadline thao tác; chưa kết luận key còn hay hết |
| `AmbiguousTimeoutException` trên mutation | Mutation có thể đã được server áp dụng hoặc chưa |
| Authentication/authorization error | Không có quyền hoặc thông tin xác thực không hợp lệ; không phải TTL |
| SQL++ index error | Có vấn đề Query/Index; không chứng minh document expired |
| CAS mismatch trên replace | Document bị thay đổi so với phiên bản đọc; không phải một lỗi expiry đơn thuần |
| Scope/collection không tồn tại | Sai keyspace hoặc provisioning; không phải TTL |

Đừng bắt mọi exception rồi trả “session expired”. Điều đó che giấu outage và làm sai các chỉ số nghiệp vụ.

Ví dụ xử lý:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.core.error.TimeoutException;

try {
    var document = sessions.get(sessionKey);
    return validateBusinessDeadline(document.contentAsObject());
} catch (DocumentNotFoundException ex) {
    return SessionStatus.NOT_FOUND_OR_EXPIRED;
} catch (TimeoutException ex) {
    // Đánh dấu lỗi hạ tầng / retry có giới hạn tùy use case.
    throw ex;
}
~~~

Đây là đoạn minh họa cần các type `SessionStatus` và method `validateBusinessDeadline` do ứng dụng định nghĩa; **không phải** mã Java độc lập chạy được ngay.

## 17. CAS và race giữa thời điểm đọc và thời điểm ghi

Couchbase CAS (Compare-And-Swap) cho phép kiểm soát optimistic concurrency. Một request có thể đọc document hợp lệ, sau đó document bị sửa hoặc hết hạn trước khi request cập nhật.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant CB as Couchbase KV
    A->>CB: 10:04:59 GET OTP + CAS c1
    CB-->>A: JSON + CAS c1
    B->>CB: 10:04:59 UPDATE/TOUCH
    CB-->>B: CAS mới
    A->>CB: 10:05:01 REPLACE với CAS c1
    alt Document đã hết hạn
      CB-->>A: Not found
    else Document còn nhưng CAS đổi
      CB-->>A: CAS mismatch
    end
~~~

- **Not-found**: document không còn tồn tại hợp lệ hoặc đã bị xóa.
- **CAS mismatch**: version document khác bản A đã đọc.
- **Expiry**: deadline sống của document, độc lập với CAS.
- **Transaction timeout**: giới hạn thực thi transaction, không phải document expiry.

Không xử lý mọi lỗi bằng `upsert` mới nếu nghiệp vụ không cho phép hồi sinh dữ liệu.

### 17.1. Dùng `@Version` trong Spring Data

Spring Data Couchbase có thể dùng `@Version` để hỗ trợ optimistic locking trên entity. Điều đó giúp tránh lost update khi repository/template đi qua pipeline phù hợp. Nó **không tự bảo đảm document còn hiệu lực tới bước tiếp theo**, và không thay kiểm tra deadline nghiệp vụ.

## 18. Transaction, TTL và thời điểm ra quyết định

Một transaction có thể đọc document khi còn hiệu lực nhưng dành thời gian tính toán trước khi commit. Nếu nghiệp vụ yêu cầu “reservation chưa hết hạn tại lúc xác nhận”, phải kiểm tra deadline **tại điểm ra quyết định** và bảo vệ thao tác bằng cơ chế nhất quán phù hợp.

TTL không phải cơ chế hẹn giờ tự động abort giao dịch đúng khi clock tới hạn. Các trường hợp document hết hạn/không còn tồn tại có thể dẫn tới conflict hoặc transaction failure theo API và thời điểm thực thi; cần xử lý rõ ràng.

### 18.1. Mẫu xác nhận reservation

Logic nghiệp vụ nên biểu đạt:

1. Đọc reservation từ keyspace đúng.
2. Kiểm tra `expiresAt`, `status` và quyền sở hữu.
3. Kiểm tra deadline theo đồng hồ được sử dụng nhất quán.
4. Cập nhật trạng thái bằng CAS/transaction theo thiết kế.
5. Nếu deadline đã qua hoặc key không còn hợp lệ, trả “expired” thay vì tạo reservation mới.
6. Đối soát kết quả khi timeout/ambiguous mutation.

Cơ chế cụ thể phụ thuộc mức nhất quán yêu cầu và transaction support của server/SDK. Không tự coi một query SQL++ trả row là khóa reservation đã tồn tại an toàn.

## 19. Reactive publisher và thời điểm subscription

Spring Data Couchbase có `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate`; SDK Java có API reactive. Dù API reactive, quy tắc expiry vẫn được server thực hiện.

Ví dụ KV reactive:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Mono;

Mono<JsonObject> document =
        otpCodes.reactive()
                .get("otp::u-42")
                .map(result -> result.contentAsObject())
                .onErrorResume(
                        DocumentNotFoundException.class,
                        ignored -> Mono.empty()
                );
~~~

Điểm đáng chú ý:

- Publisher thường chỉ thực thi khi có subscription; thời điểm **tạo Mono** không nhất thiết là thời điểm đọc.
- Một lần subscribe thứ hai có thể truy cập document sau TTL và nhận kết quả khác lần đầu.
- `Mono.cache(...)` có thể giữ tín hiệu/value ở tầng Reactor; sau đó subscriber không nhất thiết tạo một KV GET mới.
- `Mono.timeout(Duration.ofSeconds(2))` là timeout của pipeline, **không phải TTL document**.
- Cancellation không đảm bảo server chưa thực hiện thao tác đã gửi.

Đừng nuốt mọi lỗi thành `Mono.empty()`. Chỉ chuyển **not-found** sang trạng thái “không có dữ liệu” nếu đó là contract nghiệp vụ; timeout, RBAC và outage phải được phân loại khác.

### 19.1. Hai lần subscribe có thể khác kết quả

~~~text
10:04:59  Subscriber A GET → document hợp lệ
10:05:01  Subscriber B GET → key đã hết hạn, empty/not-found
~~~

Không có mâu thuẫn nếu hai subscriptions thật sự tạo hai lần đọc ở hai thời điểm khác nhau. Nếu dùng operator cache, phải hiểu lần B có thể lấy lại kết quả cũ từ publisher cache thay vì truy cập server.

## 20. Thời gian đọc và vấn đề đồng hồ

Expiry được Couchbase xử lý bằng metadata thời gian; client thường gửi `Duration` hoặc `Instant` qua SDK. Phép tính của ứng dụng có thể dùng `Clock`.

### 20.1. Không so thời gian chính xác từng nano giây

TTL có thể được thể hiện theo đơn vị giây trong protocol/metadata; cộng thêm network round trip và scheduling, một test so deadline bằng từng nano giây thường sẽ flaky.

Nên kiểm thử với:

- TTL đủ dài để có cửa sổ đọc trước hạn.
- Độ dung sai phù hợp cho timestamp metadata.
- Polling có deadline sau mốc expiry.
- Key duy nhất, collection test được kiểm soát.
- Đồng hồ client/server đồng bộ.

### 20.2. Đồng hồ lệch và deadline nghiệp vụ

Với một OTP có deadline tuyệt đối, service có thể tính `issuedAt.plus(Duration.ofMinutes(5))`. Nếu đồng hồ ứng dụng sai, deadline được gửi có thể ở quá khứ hoặc tương lai ngoài mong muốn.

Dùng đồng bộ thời gian ở cluster/app và một `Clock` được inject trong Java để unit test được logic. Không để mỗi service dùng timezone local một cách tùy ý rồi so với một mốc UTC.

## 21. Test TTL: ba phép kiểm tra thay vì một lần ngủ

Một integration test tốt cần chứng minh ba điều riêng:

1. Mutation đặt **expiry metadata dự kiến**.
2. KV read **trước hạn** thấy document hợp lệ.
3. KV read **sau hạn** cuối cùng trả không tồn tại trong một khoảng chờ hợp lý.

Khi cần kiểm tra SQL++ index, đó là một bộ test **riêng**, không làm lẫn kết quả với KV TTL.

### 21.1. Tạo document test có TTL ngắn

~~~java
import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

String key = "expiry-read-it::" + UUID.randomUUID();

testCollection.upsert(
        key,
        JsonObject.create().put("type", "ttl-test"),
        UpsertOptions.upsertOptions()
                .expiry(Duration.ofSeconds(5))
);
~~~

Ngay sau mutation, đọc `withExpiry(true)` để ghi nhận deadline thực, rồi đọc content. Sử dụng collection test có `maxTTL` đã biết; nếu maxTTL 2 giây, một test kỳ vọng TTL 5 giây sẽ sai.

### 21.2. Polling có giới hạn

Ví dụ với Awaitility và JUnit (phụ thuộc test thêm trong dự án):

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

await()
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() -> {
            var exists = testCollection.exists(key);
            assertThat(exists.exists()).isFalse();
        });
~~~

Phép kiểm tra dựa trên **kết quả KV** sau TTL, không dựa vào dung lượng disk. Thời gian 15 giây là ví dụ, cần điều chỉnh theo môi trường test. Nếu test quá tải hoặc có chênh lệch clock, phải chẩn đoán, không chỉ tăng thời gian ngủ vô hạn.

### 21.3. Phải kiểm tra điều kiện trước hạn

Nếu test chỉ assert not-found sau 5 giây, có thể document chưa từng được ghi thành công hoặc keyspace đã sai. Vì vậy cần kiểm tra:

~~~java
var initial = testCollection.get(key);
assertThat(initial.contentAsObject().getString("type"))
        .isEqualTo("ttl-test");
~~~

Kết hợp expiry metadata readback giúp phân biệt “đã ghi và sau đó hết hạn” với “lỗi write/keyspace”.

## 22. Test Query consistency riêng với expiry

Khi muốn hiểu khoảng trễ giữa KV và SQL++:

1. Ghi một document có TTL phù hợp, lấy key duy nhất.
2. Đảm bảo index cần thiết đã tồn tại và query plan được biết.
3. Query `NOT_BOUNDED` hoặc cấu hình mặc định, ghi nhận kết quả.
4. Query `REQUEST_PLUS` theo đúng API, ghi nhận kết quả và latency.
5. Khi expiry đi qua, đọc KV để xác nhận trạng thái logic.
6. Lặp lại query có giới hạn thời gian và quan sát khi kết quả thay đổi.
7. Ghi rõ query có index coverage hay cần fetch; không gộp tất cả query plan.
8. Không dùng test này làm bảo đảm rằng `REQUEST_PLUS` tự kích hoạt expiration cleanup.

**Điểm cần chứng minh không phải “SQL++ luôn trễ X giây”**. Nó là **thời điểm quan sát giữa Data/Index/Query phụ thuộc cơ chế và tải**, và ứng dụng cần chọn contract phù hợp.

### 22.1. Bảng quan sát mẫu

| Thời điểm | KV GET | SQL++ SELECT | Điều cần điều tra |
| --- | --- | --- | --- |
| Ngay sau insert | Có | Có hoặc chưa tùy index consistency | Read-after-write/index lag |
| Trước expiry | Có | Thường kỳ vọng có nếu query/index đã cập nhật | Keyspace/query plan |
| Ngay sau expiry | Not-found thường là kỳ vọng | Không nên giả định một hành vi tức thời duy nhất | Expiry handling, index/fetch path |
| Sau khi cleanup/index đã theo kịp | Not-found | Không còn row hợp lệ theo contract | Kiểm tra index và server state |
| Cache ứng dụng vẫn trả document | Không trực tiếp từ KV | Không trực tiếp từ SQL++ | TTL/invalidation cache riêng |

Bảng là **kịch bản kiểm thử**, không phải kết quả đo trên cluster cụ thể.

## 23. Đừng suy từ `DELETE` hay `REMOVE` sang TTL mà không kiểm tra

Một API `remove(key)` tạo một mutation xóa được yêu cầu trực tiếp; thời điểm nó được ghi, replicate và index hóa có semantics riêng. Một document đến expiry vì thời gian trôi qua có thể được xử lý qua cơ chế hết hạn nền hoặc khi truy cập.

Vì vậy:

- Không dùng thời gian index cập nhật sau `remove` làm số đo chính xác cho thời gian dọn TTL.
- Không dùng thành công của `remove` làm bằng chứng expired data đã được xóa khỏi backup.
- Không coi giá trị `expiry = 0` là lệnh delete.
- Không cho rằng `@Document(expiry)` sẽ tự chạy một callback Java khi hết hạn.

Nếu cần một job chính xác tại deadline (gửi thông báo, giải phóng nguồn lực, hủy đơn), hãy thiết kế **scheduler/event processing riêng**, dùng TTL như một lớp bảo vệ/dọn dẹp bổ sung.

## 24. Đọc và transaction trong môi trường phân tán

Nếu hai service cùng quan sát document:

~~~text
Service A: đọc lúc T-50ms  → vẫn còn
Service B: đọc lúc T+50ms  → không còn
~~~

Hai response khác nhau có thể đúng theo **thời điểm xử lý**. Không nên cố biến TTL thành một kiểu “đồng hồ toàn cục” bảo đảm mọi client nhìn giống hệt nhau ở sát ranh giới thời gian.

Nếu nghiệp vụ cần một điểm quyết định duy nhất:

- Chuyển việc kiểm tra deadline và thay đổi trạng thái vào cùng luồng xử lý.
- Dùng CAS/transaction/locking phù hợp với semantics Couchbase và mức nhất quán cần.
- Bảo vệ khỏi upsert vô điều kiện tái tạo dữ liệu đã hết hạn.
- Dùng idempotency key và lưu kết quả khi có retry.
- Xem xét log/audit nếu cần phân biệt hết hạn với xóa có chủ đích.

Không sử dụng Query service và KV xen kẽ như thể chúng luôn tạo một snapshot nhất quán tuyệt đối cho toàn bộ request.

## 25. Xử lý `maxTTL` của bucket/collection

Ngay cả khi client truyền `Duration.ofMinutes(30)`, server có thể có `maxTTL` 10 phút cho collection, khiến document hết hạn sớm hơn ý định ứng dụng.

~~~mermaid
flowchart LR
    A["Client expiry = 30m"] --> B["Couchbase Server"]
    C["Collection/bucket maxTTL"] --> B
    B --> D["Metadata expiry thực tế"]
    D --> E["KV đọc trước/sau deadline"]
~~~

Vì vậy, khi document biến mất **sớm hơn** dự kiến, kiểm tra:

1. Bucket, scope và collection thực.
2. `maxTTL` ở bucket/collection và luật kế thừa theo server version.
3. Thao tác mutation gần nhất có `expiry(Duration)`, `expiry(Instant)` hay `preserveExpiry` không.
4. Có lời gọi `touch`/`getAndTouch` làm mới hoặc rút ngắn hạn không.
5. Metadata expiry thực tế đã đọc trước khi document hết hạn.
6. Có thao tác `remove`/job cleanup khác hay không.

Đừng tăng KV timeout để sửa một vấn đề expiry. Timeout chỉ điều chỉnh thời gian chờ operation, không kéo dài vòng đời document.

## 26. Observability: đo đúng tầng

Các tín hiệu vận hành nên chia theo tầng:

| Tầng | Nên theo dõi | Không thể suy chỉ từ số liệu này |
| --- | --- | --- |
| Data/KV | Not-found, latency, timeout, mutation errors | Lý do mọi key biến mất |
| Expiration | Expired item counters/metrics server tương ứng | Thời điểm xóa vật lý khỏi tất cả backups |
| Index/Query | Index state, scan latency, query errors | KV document luôn còn/đã hết hạn ở từng mili giây |
| Cache ứng dụng | Hit/miss, TTL, invalidation | Metadata expiry thật của Couchbase |
| Business | OTP used/expired, session revoked, reservation deadline | Chỉ số storage vật lý |
| Concurrency | CAS conflicts, transaction retry | Quyền được gia hạn TTL |

Đặt dashboard/alert cho **tỷ lệ document-not-found bất thường**, đặc biệt sau khi đổi maxTTL, triển khai release mới hoặc refactor từ repository sang SDK.

### 26.1. Không log dữ liệu nhạy cảm

Không log raw OTP, token, credential, session secret hoặc JSON chứa thông tin cá nhân chỉ để tìm lỗi TTL. Log thông tin keyspace, loại thao tác, deadline đã được làm tròn/an toàn, trạng thái lỗi và correlation ID phù hợp với policy bảo mật.

## 27. Bảng chẩn đoán sự khác biệt quan sát

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| GET trả not-found đúng hạn nhưng disk chưa giảm | Expiry logic khác cleanup vật lý | Kiểm tra server metrics/pager/compaction |
| Query chưa phản ánh thay đổi vừa ghi | Index lag/scan consistency | Kiểm tra `REQUEST_PLUS` hoặc mutation-token consistency |
| Query kết quả khác KV ở sát expiry | Đường index/fetch và thời điểm quan sát khác | Kiểm tra plan, server version, metadata và timeline |
| Spring `findById` khác derived query | KV theo ID vs SQL++ qua index | Kiểm tra đường thực thi |
| Cache vẫn trả session đã hết hạn | Cache TTL/invalidation riêng | Giới hạn TTL cache và xác thực deadline |
| OTP được chấp nhận sau deadline | Check-then-use hoặc gia hạn do mutation | Kiểm tra deadline tại điểm quyết định, preserve expiry |
| GET trước hạn thành công, REPLACE sau hạn thất bại | Race với expiry | Xử lý not-found; không tự upsert |
| Chỉ replica path trả thông tin cũ | Cơ chế replica/consistency khác | Xem contract read preference |
| GET timeout bị báo nhầm expired | Phân loại lỗi sai | Phân biệt timeout với not-found |
| Document mất sớm hơn TTL ứng dụng | `maxTTL` ngắn hơn hoặc expiry bị rút | Đọc policy và metadata |
| Document sống lâu hơn expected | TOUCH/GET-AND-TOUCH hoặc update reset TTL | Kiểm tra mutation paths |
| `expiryTime()` không đọc được sau hạn | Document không còn đọc KV | Đọc metadata ngay sau ghi trước expiry |
| SQL++ COUNT thay đổi không đúng lúc mong đợi | Index/cleanup bất đồng bộ | Định nghĩa SLA độ trễ, tránh dùng như clock |
| Test TTL chập chờn | Assert sát mốc, clock/rounding, keyspace | Poll có deadline, dung sai và key riêng |

### 27.1. Cây quyết định

~~~mermaid
flowchart TD
    A["Kết quả đọc không như dự kiến"] --> B{"Nguồn đọc là gì?"}
    B -- "Ứng dụng cache" --> C["Kiểm tra cache TTL/invalidation"]
    B -- "KV GET" --> D["Kiểm tra keyspace, metadata, deadline"]
    B -- "SQL++" --> E["Kiểm tra index, plan, scan consistency"]
    C --> F{"Document có hard deadline nghiệp vụ?"}
    D --> F
    E --> F
    F -- "Có" --> G["Xác thực deadline tại điểm quyết định"]
    F -- "Không" --> H["So timeline mutations với expiry"]
    G --> I["Tách not-found, timeout, CAS conflict"]
    H --> I
    I --> J["Test và quan sát lại từng tầng"]
~~~

## 28. Bài tập tình huống: OTP, session và dashboard

Một ứng dụng `checkout-service` sử dụng:

~~~text
commerce.checkout.otp_codes
commerce.checkout.sessions
commerce.checkout.carts
~~~

Các yêu cầu:

- OTP sống 5 phút từ lúc phát hành, không gia hạn khi nhập sai.
- Session idle TTL 20 phút, hard lifetime 8 giờ.
- Cart có TTL 30 phút từ lần sửa cuối.
- Dashboard vận hành dùng SQL++ đếm số session.
- Một lớp Caffeine cache lưu session 30 phút.
- Server collection `sessions` có `maxTTL` 10 phút.
- Một số màn hình truy cập bằng repository finder, số khác dùng SDK `getAndTouch`.

**Câu hỏi:**

1. Vì sao OTP GET trước hạn một chút và GET sau hạn có thể trả kết quả khác nhau?
2. KV GET not-found có chứng minh OTP đã bị xóa vật lý khỏi backup không?
3. Vì sao dashboard SQL++ có thể phản ánh khác KV tại một số thời điểm?
4. `REQUEST_PLUS` có buộc expiry pager quét ngay không?
5. Caffeine cache 30 phút có thể khiến client thấy session sau khi KV đã hết hạn như thế nào?
6. Nếu hard lifetime là 8 giờ, tại sao `getAndTouch(id, 20m)` mỗi request chưa đủ để tuân thủ?
7. Nếu collection maxTTL chỉ 10 phút, kỳ vọng session 20 phút cần điều chỉnh ở đâu?
8. Một `findById` và một derived query có chắc đi qua cùng đường đọc không?
9. Vì sao một mutation sau GET thành công có thể trả not-found khi document đã hết hạn?
10. Thiết kế integration test riêng cho KV expiry và Query index visibility, không trộn hai phép đo.

**Đáp án định hướng:**

- KV read được đánh giá tại thời điểm server xử lý; kết quả đọc trước hạn có thể khác sau hạn.
- Expiry logic không chứng minh purge vật lý tức thời.
- Query/index có độ trễ cập nhật và kế hoạch thực thi riêng; `REQUEST_PLUS` chủ yếu liên quan độ trễ index theo mutation, không phải trigger expiry pager.
- Cache TTL phải phù hợp deadline thật và cần invalidation.
- Sliding session vẫn phải kiểm tra hard deadline.
- maxTTL server có thể rút ngắn TTL client.
- Integration test nên đọc metadata sau ghi, kiểm tra KV trước/sau deadline, rồi test query với scan consistency và query plan tách biệt.

## 29. Checklist trước production

- [ ] Phân biệt deadline expiry logic, quan sát KV và cleanup/index visibility.
- [ ] Không coi not-found là bằng chứng duy nhất rằng document đã “expired” thay vì deleted/never existed.
- [ ] Không suy từ dung lượng disk rằng TTL không hoạt động.
- [ ] Không dựa vào SQL++ COUNT hoặc index entry làm đồng hồ hết hạn chính xác từng giây.
- [ ] Biết `findById` đi qua KV và derived query có thể dùng SQL++/index.
- [ ] Dùng `REQUEST_PLUS` cho read-after-write phù hợp, không coi nó là trigger TTL cleanup.
- [ ] Đã xét query plan có fetch content hay covered index.
- [ ] Cache ứng dụng/HTTP có TTL và invalidation độc lập, không vượt deadline nghiệp vụ.
- [ ] Đã phân biệt read từ primary KV, replica và cache.
- [ ] Với OTP/session/reservation, kiểm tra deadline tại điểm quyết định quan trọng.
- [ ] Không upsert vô điều kiện để hồi sinh document đã hết hạn.
- [ ] CAS, `@Version` và transaction được dùng để quản lý cạnh tranh, không thay TTL.
- [ ] Không nhầm KV/Query timeout với document expiry.
- [ ] Đã xác minh `maxTTL` ở đúng bucket/collection.
- [ ] Đọc expiry metadata ngay sau mutation khi cần chứng minh hạn đã áp.
- [ ] Test dùng key riêng, polling có deadline và dung sai clock phù hợp.
- [ ] Test KV và Query/index riêng, không ép một SLA không được server cam kết.
- [ ] Theo dõi not-found, index lag, mutation timeout và cache stale reads theo tầng.
- [ ] Không xem TTL là cam kết dữ liệu đã bị xóa vật lý khỏi mọi replica/backup.
- [ ] Tài liệu vận hành ghi rõ thời điểm quan sát và policy retention.

## 30. Tổng kết

**Document hết hạn logic** không có nghĩa mọi index, cache, thống kê và byte lưu trữ đều được cập nhật vào đúng cùng một mili giây. Với key đã biết, **KV GET** là cách kiểm tra trực tiếp document còn hợp lệ ở thời điểm đọc; SQL++ dùng Query/Index service và có yêu cầu về scan consistency khác, còn cache của ứng dụng có vòng đời riêng.

`REQUEST_PLUS` và các mức consistency giúp quản lý việc index theo kịp mutation, **không biến đồng hồ TTL thành một sự kiện xóa tức thời ở mọi tầng**. Kết quả đọc còn phụ thuộc thời điểm server xử lý, race với mutation, replica read và trạng thái cache.

Trong Spring Data Couchbase, kết hợp đúng repository, `CouchbaseTemplate`, SDK, SQL++, CAS, giao dịch và reactive API đòi hỏi tách **cơ chế expiry của Couchbase** khỏi **deadline nghiệp vụ cần kiểm tra tại điểm sử dụng**. Khi có test metadata, KV trước/sau hạn, query plan riêng và quan sát từng tầng, ứng dụng sẽ tránh được cả quyết định sai do dữ liệu lỗi thời lẫn kết luận sai về việc dọn dẹp document đã hết hạn.

