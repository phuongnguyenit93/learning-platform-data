# Replica set, read preference và write concern

## 1. Vì sao ứng dụng tích hợp cần hiểu ba khái niệm này?

Một dịch vụ Spring Boot nhận yêu cầu từ HTTP, ghi trạng thái xử lý vào MongoDB, rồi gửi sự kiện tới broker hoặc gọi API đối tác. Nếu MongoDB primary ngừng hoạt động hoặc secondary chưa sao chép kịp, một cấu hình thiếu chủ đích có thể khiến dịch vụ:

- Ghi thành công nhưng sau failover không còn thấy bản ghi mà hệ thống vừa xác nhận.
- Đọc từ secondary và thấy trạng thái cũ, rồi gửi lại sự kiện hoặc trả sai kết quả cho API.
- Chờ acknowledgment quá lâu, timeout rồi không biết phía MongoDB đã áp dụng thao tác hay chưa.
- Tưởng rằng có replica set là đã bảo đảm **exactly-once**, **read-your-writes** và **zero downtime**.

**Replica set** giải quyết khả năng sao chép, bầu chọn primary và khôi phục tính sẵn sàng. **Read preference** quyết định client chọn node nào để đọc. **Write concern** quyết định MongoDB phải nhận được bao nhiêu xác nhận trước khi báo thao tác ghi thành công. Ngoài ra, **read concern** quyết định mức bảo đảm về dữ liệu được trả về; muốn thiết kế một luồng tích hợp đúng, cần xem cả bốn yếu tố.

| Khái niệm | Câu hỏi nó trả lời | Không tự bảo đảm |
| --- | --- | --- |
| Replica set | Dữ liệu được sao chép và bầu primary ra sao? | Không có thời gian gián đoạn khi bầu lại primary |
| Read preference | Đọc từ primary, secondary hay node gần nhất? | Không xác định bản ghi đã được commit bền vững hay chưa |
| Write concern | Khi nào lệnh ghi được xác nhận đủ mức đã chọn? | Không tự chống duplicate khi client gửi lại yêu cầu |
| Read concern | Trạng thái dữ liệu nào được phép trả cho một lệnh đọc? | Không bắt buộc đọc từ primary hoặc tạo ra read-your-writes trên mọi session |

### Bài toán xuyên suốt

Giả sử service tích hợp lưu một `IntegrationRequest` theo `requestId`. API `POST /imports` ghi tài liệu với trạng thái `RECEIVED`; worker khác đọc và gọi API bên ngoài; sau đó worker cập nhật `COMPLETED`. Yêu cầu của hệ thống:

1. Yêu cầu đã được thông báo nhận thành công phải đủ bền vững để tiếp tục xử lý khi primary đổi.
2. Worker không dựa vào trạng thái cũ khi quyết định có phát yêu cầu lần nữa hay không.
3. Retry từ HTTP client hoặc broker không được tạo tác dụng phụ trùng.
4. Việc đọc báo cáo có thể chấp nhận trễ ngắn, nhưng việc kiểm tra trạng thái giao dịch cần phù hợp với độ nhất quán đã cam kết.

Chúng ta sẽ dùng tình huống này để lựa chọn cấu hình thay vì chỉ ghi nhớ tên tham số.

## 2. Replica set: primary, secondary, election và oplog

Replica set là một nhóm tiến trình `mongod` duy trì cùng bộ dữ liệu logic. Trong cấu hình điển hình có **một primary** nhận các thao tác ghi thông thường, và **nhiều secondary** sao chép hoạt động từ primary. Secondary áp dụng thay đổi thông qua **oplog** (operation log) và vì sao chép bất đồng bộ nên có thể đi sau primary một khoảng thời gian.

~~~mermaid
flowchart LR
    A[Spring Boot MongoDB Driver] -->|Ghi và đọc primary| P[(Primary A)]
    P -->|Oplog replication| S1[(Secondary B)]
    P -->|Oplog replication| S2[(Secondary C)]
    A -.->|Đọc nếu read preference cho phép| S1
    A -.->|Đọc nếu read preference cho phép| S2
~~~

### Một lần failover xảy ra như thế nào?

1. Driver theo dõi topology và chọn primary hiện tại cho các lệnh cần ghi.
2. Nếu primary bị lỗi hoặc mất kết nối, các thành viên có quyền biểu quyết tiến hành election theo điều kiện của replica set.
3. Một secondary phù hợp được bầu thành primary mới khi có đủ số phiếu.
4. Trong thời gian phát hiện lỗi và bầu cử, thao tác ghi hoặc đọc yêu cầu primary có thể thất bại, chờ hoặc được driver retry nếu đủ điều kiện.
5. Driver cập nhật topology rồi hướng các thao tác tiếp theo tới primary mới; ứng dụng phải xử lý timeout, transient error và kết quả ghi không chắc chắn.

Không phải mọi node có thể đồng thời nhận ghi. Trong replica set truyền thống, thông thường chỉ primary nhận các write thông thường. **Arbiter** có phiếu bầu nhưng **không lưu dữ liệu**, không phục vụ đọc hoặc góp xác nhận dữ liệu bền vững. Một topology ba node **Primary–Secondary–Secondary (P-S-S)** thường phù hợp hơn **Primary–Secondary–Arbiter (P-S-A)** nếu cần chịu lỗi một data-bearing node trong khi tiếp tục dùng `w: "majority"`.

**Quorum và durability là hai điều khác nhau:** đủ phiếu để bầu primary không có nghĩa là có đủ bản sao **mang dữ liệu** để xác nhận ghi với `majority`. Trong P-S-A, nếu secondary duy nhất ngừng hoạt động, có thể vẫn có primary và arbiter bỏ phiếu nhưng ghi `w: "majority"` không đủ số bản sao dữ liệu để xác nhận.

### Oplog và replication lag

- Primary ghi thao tác vào oplog; secondary đọc và áp dụng tuần tự các thay đổi cần sao chép.
- **Replication lag** là độ trễ giữa trạng thái secondary và primary; nó chịu ảnh hưởng của network, tốc độ đĩa, tải đọc/ghi và trạng thái node.
- Một secondary lag có thể trả `RECEIVED` dù primary đã cập nhật `COMPLETED`.
- Khi election/failover, những thao tác ghi chưa được majority-committed có nguy cơ rollback tùy topology và mức write concern.

Replica set làm tăng **khả năng sẵn sàng và độ bền** nhưng vẫn cần ứng dụng tự kiểm soát idempotency, transaction, retry và quan sát.

### Kiểm tra nhanh topology với mongosh

~~~javascript
rs.status();           // Vai trò và trạng thái các thành viên
rs.conf();             // Cấu hình replica set, số phiếu và priority
db.hello();            // Thông tin node hiện tại và trạng thái writable primary
db.adminCommand({ getDefaultRWConcern: 1 }); // Default read/write concern
~~~

Các lệnh cần quyền truy cập phù hợp và chạy trong môi trường được phép. `rs.status()` phản ánh trạng thái tại thời điểm đọc, chưa thay thế metric lag, health check và cảnh báo election. Không tự chạy `rs.initiate()` hoặc `rs.reconfig()` lên cụm production để thử bài này.

## 3. Read preference: chọn thành viên phục vụ thao tác đọc

Read preference là một **chính sách chọn server** của MongoDB driver, có thể đặt trên client, database, collection hoặc từng lệnh đọc tùy API. Mặc định driver đọc từ `primary`.

| Chế độ | Cách chọn node | Khi nào cân nhắc | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| `primary` | Chỉ primary | Kiểm tra trạng thái nghiệp vụ mới cập nhật, đọc trong transaction | Không đọc được nếu chưa có primary sẵn sàng |
| `primaryPreferred` | Ưu tiên primary; dùng secondary đủ điều kiện nếu không có primary | Truy vấn muốn primary nhưng chấp nhận fallback dữ liệu trễ | Trong failover, dữ liệu có thể đột ngột cũ hơn |
| `secondary` | Chỉ secondary đủ điều kiện | Báo cáo, phân tích và truy vấn có khả năng chịu stale read | Không có secondary hợp lệ thì đọc thất bại |
| `secondaryPreferred` | Ưu tiên secondary; fallback primary nếu không có secondary hợp lệ | Tách tải đọc báo cáo khỏi primary | Kết quả có thể khác nhau về độ mới giữa các lần |
| `nearest` | Chọn node đủ điều kiện có độ trễ mạng trong latency window, không phân biệt vai trò | Truy vấn đặt nặng latency mạng, chấp nhận độ mới biến thiên | Không có nghĩa là node có dữ liệu mới nhất |

**Read preference không phải read concern.** Ví dụ `secondaryPreferred` với read concern `majority` có thể chỉ đọc dữ liệu đã majority-committed nhưng **vẫn chưa phải giá trị mới nhất** nếu secondary chưa bắt kịp primary. `primary` với read concern `local` có thể nhìn thấy ghi chưa majority-committed và do đó có thể bị rollback trong failover.

### Tags, latency window và max staleness

Driver có thể lọc secondary theo tag của thành viên (ví dụ `region`, `rack`), đặt giới hạn độ cũ ước lượng với `maxStalenessSeconds` rồi chọn trong nhóm có round-trip time thuộc **latency window**. Các giá trị quan trọng:

~~~text
readPreference=secondaryPreferred
maxStalenessSeconds=120
readPreferenceTags=region:ap-southeast-1
localThresholdMS=15
~~~

- `maxStalenessSeconds` cần **ít nhất 90 giây** nếu đặt giá trị không âm. Đó là **độ cũ ước lượng để chọn server**, không phải SLA “dữ liệu luôn trễ tối đa đúng 120 giây”.
- `readPreferenceTags` giới hạn node có tag phù hợp; khi kết hợp danh sách tag-set cần hiểu thứ tự fallback. Không gán tags cho `primary`.
- `localThresholdMS` là khoảng chênh latency được phép so với node nhanh nhất; `nearest` đánh giá mạng, không đánh giá độ tươi dữ liệu.
- `primary` không chấp nhận `maxStalenessSeconds` hoặc tag-set.

Nếu nghiệp vụ yêu cầu **ngay sau khi ghi phải đọc thấy bản ghi của chính mình**, ưu tiên đọc từ primary hoặc sử dụng session có bảo đảm nhân quả (causal consistency) được cấu hình đúng. Chỉ chuyển read preference thành `nearest` để “tối ưu latency” có thể làm hỏng logic chống trùng.

### Ví dụ dòng thời gian và stale read

~~~text
T0   Primary A nhận update: requestId=R9, state=COMPLETED
T1   A xác nhận ghi với w:majority; B đã nhận đủ dữ liệu
T2   Secondary C vẫn chưa áp dụng update do replication lag
T3   Worker đọc secondaryPreferred; driver chọn C
T4   Worker thấy state=RECEIVED (cũ), dù update đã majority-committed
~~~

Tại `T3`, cả việc ghi thành công với `w:majority` lẫn việc dùng read concern `majority` **không tự ép** mọi secondary hiện ra giá trị mới nhất ngay lập tức. Thiết kế worker phải dùng idempotency key/unique index và, khi cần, đọc tuyến phù hợp hoặc session causal.

### Transactions và read preference

**Transaction chứa thao tác đọc phải dùng read preference `primary`.** Đừng đặt `readPreference=secondaryPreferred` toàn ứng dụng rồi mặc định mọi giao dịch Spring Data MongoDB sẽ chạy đúng. Một cách đơn giản là để URI mặc định `primary`, và chỉ dùng secondary cho truy vấn báo cáo có chủ đích. Trong các transaction, các thao tác thuộc cùng giao dịch phải được định tuyến tới cùng thành viên.

## 4. Write concern: khi nào MongoDB được trả lời “đã ghi”?

Write concern là mức **acknowledgment** mà ứng dụng yêu cầu cho lệnh ghi. Thành phần thường thấy gồm `w`, `j` và `wtimeout` (được biểu diễn dưới dạng `wTimeoutMS` trong URI).

| Thiết lập | Điều kiện xác nhận | Đánh đổi và trường hợp dùng |
| --- | --- | --- |
| `w: 0` | Không yêu cầu ack xác nhận ghi | Không phù hợp với lưu trạng thái quan trọng của luồng tích hợp |
| `w: 1` | Primary xác nhận thao tác | Latency thấp hơn, nhưng ghi có thể rollback khi failover trước khi được sao chép đủ |
| `w: 2` hoặc `w: 3` | Số member mang dữ liệu đã xác nhận theo giá trị | Gắn chặt với kích thước và trạng thái topology; không giống majority |
| `w: "majority"` | Đủ số member mang dữ liệu theo majority được tính cho replica set | Phù hợp với dữ liệu cần bền vững qua failover thông thường, đổi lại latency và availability khi thiếu quorum |
| `j: true` | Yêu cầu journaling theo cơ chế write concern | Tăng yêu cầu độ bền trước khi ack; cần hiểu cấu hình journaling của cụm |
| `wtimeout` | Giới hạn thời gian đợi write concern | Timeout **không tự rollback** lệnh ghi đã áp dụng |

**Quan trọng:** `w: 1` không có nghĩa là đã bền vững trên đa số node; `w: "majority"` không có nghĩa “có đủ phiếu bầu, kể cả arbiter, là xong”. MongoDB tính majority cho write concern dựa trên các thành viên có dữ liệu đủ điều kiện. Theo cấu hình phổ biến, majority acknowledgment đi cùng journaling; hành vi cụ thể còn phụ thuộc `writeConcernMajorityJournalDefault` và `j`.

### Default có thể thay đổi theo topology

Không nên nói một cách tuyệt đối rằng MongoDB **luôn mặc định** `w: "majority"`. Với nhiều replica set hiện đại, implicit default là majority, nhưng topology có arbiter có ngoại lệ: chẳng hạn P-S-A có thể có implicit default `w: 1`. Hãy kiểm tra `getDefaultRWConcern` hoặc cấu hình explicit cho luồng quan trọng. Nếu yêu cầu bền vững là một phần của hợp đồng dữ liệu, khai báo rõ `w=majority` trong connection string hoặc trên thao tác phù hợp.

### Write concern timeout không chứng minh thao tác thất bại

Giả sử primary đã ghi yêu cầu R9 nhưng secondary quá chậm để xác nhận đa số trong khoảng cho phép. Ứng dụng có thể nhận `write concern timeout`. Từ đây có ba khả năng:

1. Ghi đã được áp dụng trên primary và vẫn có thể tiếp tục sao chép.
2. Ghi chưa đạt durability như yêu cầu tại thời điểm timeout.
3. Sau lỗi mạng hoặc election, ứng dụng chưa biết kết quả cuối của thao tác.

Vì vậy **không được biến timeout thành “chắc chắn chưa ghi”** rồi phát một giao dịch mới với request ID mới. Dùng khóa idempotency, kiểm tra lại trạng thái và retry có giới hạn. `retryWrites=true` của driver hỗ trợ một số thao tác ghi đủ điều kiện, nhưng không thay thế thiết kế idempotency của toàn luồng HTTP → MongoDB → broker.

### Mongo shell: thiết lập tường minh trên một thao tác

~~~javascript
db.integrationRequests.insertOne(
  {
    _id: "partnerA:req-1001",
    state: "RECEIVED",
    createdAt: new Date()
  },
  { writeConcern: { w: "majority", j: true, wtimeout: 10000 } }
);
~~~

Ví dụ yêu cầu majority acknowledgment cùng journaling và đặt giới hạn đợi 10 giây. Với workload có độ nhạy latency cao, thử nghiệm bằng tải thật và theo dõi `writeConcernErrors` trước khi áp dụng hàng loạt.

Một chi tiết theo phiên bản: từ MongoDB **8.0**, acknowledgment `w:majority` dựa trên việc đa số thành viên mang dữ liệu ghi bền vững **oplog entry**; các secondary có thể áp dụng thay đổi vào collection **sau** khi acknowledgment đã trả về. Vì vậy việc đọc ngay trên secondary vẫn có thể chưa thấy tài liệu vừa ghi, càng củng cố nhu cầu lựa chọn read preference hoặc causal session theo nghiệp vụ. Các phiên bản trước có thời điểm acknowledgment theo cơ chế áp dụng thay đổi khác; cần kiểm tra tài liệu cho server đang triển khai.

## 5. Read concern và causal consistency: mảnh ghép còn thiếu

Read concern thường được nhắc cùng read/write preference bởi chúng liên quan nhưng **không thay thế nhau**.

| Read concern | Ý nghĩa chính | Lưu ý trong luồng tích hợp |
| --- | --- | --- |
| `local` | Đọc dữ liệu khả dụng cục bộ trên node, có thể chưa majority-committed | Có thể thấy dữ liệu sau này rollback |
| `available` | Ưu tiên khả dụng/độ trễ thấp trong trường hợp phù hợp | Không bảo đảm majority; trong sharded cluster có thể thấy orphaned data |
| `majority` | Trả dữ liệu tại snapshot đã majority-committed trên node đang đọc | Bền vững hơn nhưng **không** đồng nghĩa newest trên toàn cụm |
| `linearizable` | Cho một số thao tác đọc trên primary, phản ánh các majority write đã hoàn tất trước lúc đọc bắt đầu | Yêu cầu mạnh, có thể chờ lâu; đặt `maxTimeMS` hợp lý và hiểu điều kiện áp dụng |
| `snapshot` | Đọc dữ liệu tại snapshot nhất quán cho thao tác/giao dịch được hỗ trợ | Có điều kiện sử dụng; trong multi-document transaction, cần commit `w:majority` để có bảo đảm tương ứng |

### Causal consistency

MongoDB cung cấp client session có tính **causal consistency**. Với thao tác **đọc `readConcern=majority`** và **ghi `writeConcern=majority`** trong session được dùng đúng cách, ứng dụng có các bảo đảm như **read your writes**, **monotonic reads**, **monotonic writes** và **writes follow reads**; kể cả khi một số lần đọc được route tới secondary. Điều này khác hoàn toàn việc đặt `readPreference=secondaryPreferred` đơn thuần.

Ví dụ Java Sync Driver, minh họa một session đọc lại sau khi ghi cùng document:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.springframework.stereotype.Service;
import static com.mongodb.client.model.Filters.eq;

@Service
public class CausalReadExample {
    private final MongoClient mongoClient;

    public CausalReadExample(MongoClient mongoClient) {
        this.mongoClient = mongoClient;
    }

    public Document writeThenRead(String id) {
        try (ClientSession session = mongoClient.startSession(
                ClientSessionOptions.builder().causallyConsistent(true).build())) {

            MongoCollection<Document> requests =
                    mongoClient.getDatabase("integration")
                            .getCollection("integrationRequests")
                            .withReadConcern(ReadConcern.MAJORITY)
                            .withWriteConcern(WriteConcern.MAJORITY);

            requests.insertOne(session, new Document("_id", id)
                    .append("state", "RECEIVED"));

            return requests
                    .withReadPreference(ReadPreference.secondaryPreferred())
                    .find(session, eq("_id", id))
                    .first();
        }
    }
}
~~~

Đây là ví dụ **cùng session**, không phải một guarantee tự động giữa hai HTTP request hoặc giữa hai consumer độc lập. `id` phải là khóa mới cho lần chạy thử này; `insertOne` sẽ báo trùng khóa nếu cố chèn lại cùng `_id`. Session không nên dùng chung đồng thời giữa các thread. Khi kết nối theo Spring Data và quản lý transaction/session của Spring, cần dùng API session/transaction tương ứng, không tự mở transaction mới trong đoạn đọc mà không biết context đang tồn tại.

Đối với worker quyết định phát sự kiện ra broker, causal consistency không loại bỏ điều kiện kiểm tra idempotency và trạng thái xử lý được khóa/ghi nguyên tử. Causal session làm rõ thứ tự quan sát; không biến một thao tác HTTP ngoài MongoDB thành cùng một transaction.

## 6. Cấu hình MongoDB replica set trong Spring Boot

### 6.1. Dependency và connection string

Với dự án Spring MVC hoặc REST đồng bộ sử dụng Spring Data MongoDB:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Với WebFlux và reactive pipeline, dùng `spring-boot-starter-data-mongodb-reactive` tương ứng. Hai mô hình có API khác nhau; không gọi `block()` tùy tiện trong event-loop để chờ MongoDB.

Connection string ví dụ cho cụm ba node:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/integration?replicaSet=rs0&readPreference=primary&w=majority&journal=true&wTimeoutMS=10000&retryWrites=true&serverSelectionTimeoutMS=5000&readConcernLevel=majority
~~~

Giải thích các tham số:

| URI option | Giá trị ví dụ | Vai trò |
| --- | --- | --- |
| `mongo1,mongo2,mongo3` | Ba hostname/port | Seed list để driver khám phá replica set và theo dõi thay đổi primary |
| `replicaSet` | `rs0` | Xác thực topology thuộc đúng replica set dự kiến |
| `readPreference` | `primary` | Tất cả truy vấn mặc định đọc từ primary |
| `w` | `majority` | Yêu cầu majority write acknowledgment |
| `journal` | `true` | Yêu cầu độ bền thông qua journal theo write concern |
| `wTimeoutMS` | `10000` | Chờ write concern tối đa 10 giây; timeout không xóa ghi đã áp dụng |
| `retryWrites` | `true` | Driver có thể retry **một số** lệnh ghi đủ điều kiện khi gặp lỗi có nhãn retryable |
| `serverSelectionTimeoutMS` | `5000` | Giới hạn thời gian tìm server phù hợp; có thể timeout trong election |
| `readConcernLevel` | `majority` | Đọc snapshot majority-committed theo mặc định |

URI này minh họa chính sách cho dữ liệu quan trọng. Trong production, bật TLS, xác thực, cấu hình secret qua kho bí mật/biến môi trường và đặt hostname mà mọi pod truy cập được. Không commit mật khẩu hoặc URI có credential vào repository; cũng không log toàn bộ connection string chứa secret.

**Lưu ý phiên bản mới:** tài liệu MongoDB hiện đánh dấu URI option `wtimeoutMS` là **deprecated** và khuyên dùng `timeoutMS` khi driver hỗ trợ. Hai option có phạm vi khác nhau: `wtimeoutMS` giới hạn thời gian chờ **write concern**, còn `timeoutMS` là timeout của **toàn bộ thao tác** (bao gồm server selection, checkout kết nối và thực thi). Nếu thay bằng `timeoutMS`, hãy đánh giá lại các timeout liên quan thay vì xem chúng tương đương. Ví dụ trên giữ `wTimeoutMS` để minh họa cụ thể write concern trên hệ thống còn hỗ trợ nó.

Với **Spring Boot 3.x**, có thể đặt:

~~~yaml
# application.yml (Spring Boot 3.x)
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Với **Spring Boot 4.x**, đường dẫn cấu hình connection URI được chuyển về nhóm `spring.mongodb.*`:

~~~yaml
# application.yml (Spring Boot 4.x)
spring:
  mongodb:
    uri: ${MONGODB_URI}
~~~

Những phiên bản Spring Boot/driver có thể thay đổi tên property và kiểu tự cấu hình theo major release. Đối chiếu metadata và migration guide của **phiên bản dự án thực tế** trước khi sao chép ví dụ. Nếu khai báo bean `MongoClient` thủ công, phải kiểm soát toàn bộ `MongoClientSettings` và không mặc định rằng các property Boot vẫn được áp dụng như đường auto-configuration.

**Vì sao chỉ nhập một hostname chưa đủ?** Driver kết nối tới replica set bằng seed list và khám phá các thành viên trong topology. Nếu các hostname mà MongoDB tự quảng bá không phân giải được trong container/Kubernetes, ứng dụng vẫn có thể lỗi server selection dù seed host ban đầu truy cập được. Kiểm tra DNS, network policy, TLS certificate name và advertised host của cả cụm.

### 6.2. Đọc báo cáo từ secondary theo từng truy vấn

Thay vì đặt `secondaryPreferred` ở mọi nơi, hãy giữ mặc định `primary` cho xử lý trạng thái và gắn read preference riêng cho endpoint/report chịu được độ trễ. Spring Data MongoDB (các phiên bản hỗ trợ `Query.withReadPreference`) cho phép:

~~~java
import java.util.List;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
class IntegrationReportService {

    private final MongoTemplate template;

    IntegrationReportService(MongoTemplate template) {
        this.template = template;
    }

    List<IntegrationRequest> recentlyCompleted() {
        Query query = Query.query(Criteria.where("state").is("COMPLETED"))
                .withReadPreference(ReadPreference.secondaryPreferred())
                .withReadConcern(ReadConcern.MAJORITY)
                .limit(100);
        return template.find(query, IntegrationRequest.class);
    }
}
~~~

Giả sử `IntegrationRequest` là entity Spring Data đã được ánh xạ bằng `@Document` và có index phù hợp trên `state`/thời gian; tránh quét toàn collection khi lịch đồng bộ chạy thường xuyên. `Query.withReadPreference(...)` chỉ áp dụng cho **query này**; không ảnh hưởng thao tác kiểm tra trạng thái ở service khác. Nếu đang dùng Spring Data MongoDB cũ chưa có API này, xem annotation `@ReadPreference` trong repository hoặc thiết lập trên collection/template phù hợp với phiên bản.

Đối với kiểm tra duplicate, phân bổ công việc hay phản hồi API ngay sau khi ghi, dùng đọc trên primary và điều kiện cập nhật nguyên tử. Bất kỳ read preference nào cũng không thay thế index, unique key hoặc transaction trong xử lý cạnh tranh.

## 7. Ví dụ thực hành: lưu trạng thái yêu cầu tích hợp an toàn hơn

Giả sử ứng dụng nhận message có `sourceSystem`, `requestId` và nội dung đơn hàng từ một HTTP API hoặc broker. Nhiều lần giao lại cùng message phải dẫn tới **một** bản ghi trạng thái và **không** thực thi side effect nghiệp vụ lần hai.

### 7.1. Model và unique key

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "integrationRequests")
public record IntegrationRequest(
        @Id String id,
        String sourceSystem,
        String requestId,
        String payloadHash,
        String state,
        Instant createdAt,
        String workerId,
        Instant claimedAt) {
}
~~~

Trong bài này, `id = sourceSystem + ":" + requestId` và được lưu dưới khóa `_id` duy nhất của MongoDB. Nếu `sourceSystem`/`requestId` có thể chứa ký tự phân cách, dùng định dạng có length-prefix hoặc hash có quy tắc chuẩn hóa để không sinh collision. Trong môi trường nhiều nguồn gửi yêu cầu, không được giả định `requestId` duy nhất trên toàn hệ thống.

**Quan trọng:** Idempotency không chỉ là “nếu trùng ID thì bỏ qua”. Nếu cùng khóa nhưng nội dung khác, hệ thống nên trả lỗi hợp đồng hoặc đưa vào quarantine; cần so sánh `payloadHash` (được tính trên dữ liệu đã chuẩn hóa) với bản ghi tồn tại.

### 7.2. Upsert chỉ ghi khi bản ghi chưa tồn tại

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class IntegrationRequestStore {

    private final MongoTemplate template;

    public IntegrationRequestStore(MongoTemplate template) {
        this.template = template;
    }

    public IntegrationRequest receive(
            String sourceSystem, String requestId, String payloadHash) {

        String id = sourceSystem + ":" + requestId;
        Query key = Query.query(Criteria.where("_id").is(id));
        Update onCreate = new Update()
                .setOnInsert("sourceSystem", sourceSystem)
                .setOnInsert("requestId", requestId)
                .setOnInsert("payloadHash", payloadHash)
                .setOnInsert("state", "RECEIVED")
                .setOnInsert("createdAt", Instant.now());

        // URI đang yêu cầu writeConcern majority.
        template.upsert(key, onCreate, IntegrationRequest.class);

        // Kiểm tra bằng tuyến primary theo mặc định.
        IntegrationRequest stored =
                template.findById(id, IntegrationRequest.class);

        if (stored == null ||
                !payloadHash.equals(stored.payloadHash())) {
            throw new IllegalStateException(
                    "requestId đã tồn tại với payload khác hoặc chưa thấy ghi");
        }
        return stored;
    }
}
~~~

`$setOnInsert` chỉ đặt giá trị khi thao tác upsert thực sự tạo tài liệu mới; một lần retry với cùng khóa sẽ không tùy tiện chuyển `COMPLETED` trở lại `RECEIVED`. Tuy nhiên, tùy trường hợp cạnh tranh của `upsert` và tình trạng index, một lời gọi vẫn có thể ném duplicate-key/transient exception; tầng gọi phải phân loại lỗi và tra cứu bằng khóa trước khi retry đúng chính sách.

**Giới hạn của đoạn minh họa:** `receive` tạo hoặc đọc trạng thái, chưa đánh dấu một worker đã “claim” quyền xử lý. Với nhiều worker, cần `findAndModify` có điều kiện như `state=RECEIVED` để đổi nguyên tử sang `PROCESSING`, có worker token/lease hết hạn và điều kiện recovery. Việc đọc trạng thái rồi gọi API đối tác ngay mà không claim vẫn có race giữa các consumer.

### 7.3. Chuyển trạng thái bằng điều kiện nguyên tử

Ví dụ claim chỉ thành công nếu trạng thái vẫn là `RECEIVED`:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public IntegrationRequest tryClaim(String id, String workerId) {
    Query claimable = Query.query(
            Criteria.where("_id").is(id).and("state").is("RECEIVED"));

    Update update = new Update()
            .set("state", "PROCESSING")
            .set("workerId", workerId)
            .currentDate("claimedAt");

    return template.findAndModify(
            claimable,
            update,
            FindAndModifyOptions.options().returnNew(true),
            IntegrationRequest.class);
}
~~~

Đây là phương thức bổ sung bên trong `IntegrationRequestStore`, dùng cùng trường `template`. Nếu không có bản ghi ở trạng thái `RECEIVED` thì trả về `null`: chỉ consumer nhận được document mới là consumer claim thành công. `workerId` và `claimedAt` đã được ánh xạ trong record; khi áp dụng ngoài bài học, còn cần thiết kế lease hết hạn, timeout và quy tắc hoàn tất theo token để worker cũ không được ghi đè kết quả worker mới.

Đường xử lý thực tế:

~~~mermaid
flowchart TD
    A[HTTP request hoặc broker message] --> B[receive theo idempotency key]
    B --> C{Payload hash hợp lệ?}
    C -- Không --> X[Conflict hoặc quarantine]
    C -- Có --> D[Atomic claim RECEIVED → PROCESSING]
    D --> E{Claim thành công?}
    E -- Không --> F[Đọc trạng thái và trả kết quả thích hợp]
    E -- Có --> G[Gọi downstream với cùng idempotency key]
    G --> H{Downstream xác nhận?}
    H -- Có --> I[Ghi COMPLETED + event/outbox]
    H -- Timeout/không rõ --> J[Tra cứu kết quả + retry có giới hạn]
    J --> G
~~~

Trong hệ thống thực sự phát sự kiện sang Kafka/RabbitMQ sau khi MongoDB commit, cần **transactional outbox** hoặc thiết kế cơ chế phát lại bền vững. MongoDB transaction không thể tự bao trùm lệnh HTTP bên ngoài hay producer gửi vào một broker độc lập. Read preference/write concern đúng giúp bền và nhìn thấy trạng thái, nhưng không giải quyết atomicity xuyên hệ thống.

### 7.4. Có nên dùng transaction đa document?

MongoDB hỗ trợ transaction đa document trên cấu hình triển khai phù hợp, và Spring Data MongoDB có `MongoTransactionManager` để tích hợp với `@Transactional`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {

    @Bean
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Chỉ mở transaction khi có yêu cầu thay đổi nhiều tài liệu/collection cần commit hoặc rollback chung. Các thao tác đọc trong transaction phải dùng `primary`; write concern cho **transaction commit** cần được xác định rõ (ví dụ majority) để đạt mức durability mong muốn, và read concern `majority`/`snapshot` trong transaction có giới hạn bảo đảm theo mức write concern lúc commit. Đừng gắn transaction bao quanh một lời gọi HTTP chậm và mong rollback được tác dụng phụ phía đối tác.

## 8. Chọn chính sách theo từng luồng tích hợp

| Nhu cầu | Read preference | Write concern | Read concern / cách bảo đảm |
| --- | --- | --- | --- |
| HTTP ghi `RECEIVED` trước khi trả `202 Accepted` | `primary` cho truy vấn điều kiện | `majority`, cân nhắc journaling | Kiểm tra trạng thái với `majority` và idempotency key |
| Worker claim một yêu cầu để gọi đối tác | `primary` | `majority` khi đổi claim có ý nghĩa khôi phục | `findAndModify` nguyên tử, token/lease và retry |
| API vừa ghi rồi kiểm tra trạng thái | `primary` | `majority` | `majority` hoặc causal session nếu có nhiều bước/nút |
| Báo cáo dashboard chịu stale read | `secondaryPreferred` | Theo luồng ghi gốc | `majority` tùy yêu cầu; đo lag và chấp nhận dữ liệu cũ |
| Phân tích offline chỉ đọc | `secondary` hoặc `nearest` | Không áp dụng | Đặt giới hạn stale/khả năng chịu thiếu secondary |
| Multi-document MongoDB transaction | `primary` | Chọn ở transaction commit, thường `majority` | `snapshot`/`majority` theo hợp đồng transaction |
| Gửi event tới broker sau khi ghi DB | Kiểm tra trạng thái trên `primary` | `majority` | Outbox/inbox, key chống trùng, không phụ thuộc vào read preference |

Không có một URI tốt nhất cho mọi truy vấn. Cấu hình **mặc định an toàn cho nghiệp vụ** và gắn chính sách riêng cho read-only report thường dễ kiểm soát hơn đặt `secondaryPreferred` ở cấp client rồi phải ngoại lệ cho từng tác vụ quan trọng.

### Một số trade-off thường bị bỏ qua

**Độ bền so với tính sẵn sàng:** Nếu không còn đa số data-bearing member đủ điều kiện, ghi `w:majority` có thể không hoàn thành trong timeout. Hệ thống cần trả lỗi có ngữ nghĩa rõ, xếp hàng để thử sau hoặc giảm tải. Tự động hạ xuống `w:1` mà không có quyết định nghiệp vụ sẽ thay đổi hợp đồng durability.

**Độ trễ so với tính mới:** Đưa báo cáo sang secondary giảm tải primary khi đọc nhiều, nhưng độ trễ sao chép có thể khiến dashboard hiển thị trạng thái cũ. Giám sát lag, đặt ngưỡng stale và cảnh báo cho người dùng nếu cần.

**Retry so với duplicate:** Sau lỗi election hoặc write concern timeout, cùng request có thể đã được ghi một phần/toàn phần. Retry an toàn phải dùng cùng khóa nghiệp vụ và phép cập nhật có điều kiện; không tạo UUID mới trong mỗi lần retry của cùng thông điệp.

**Replica set so với multi-region:** Replication chưa đồng nghĩa là mọi region có cùng latency hay dữ liệu mới nhất. Khi dùng tags/nearest, cần đo network latency và lag theo region, đồng thời kiểm soát thứ tự xử lý các message cùng business key.

## 9. Kiểm thử failover, stale read và write concern

Để hiểu ảnh hưởng đến luồng Spring Boot Integration, nên chạy bài tập trong **replica set thử nghiệm có ít nhất ba data-bearing node**, có dữ liệu test, tuyệt đối không dùng lệnh cố ý step down trên cụm đang phục vụ production.

### 9.1. Kiểm tra đường đi trước khi thử lỗi

1. Khởi động replica set và chờ đủ thành viên ở trạng thái khỏe.
2. Kết nối Spring Boot bằng URI chứa nhiều seed host cùng `replicaSet` đúng.
3. Ghi một `IntegrationRequest` với `w:majority`, lưu ID ổn định.
4. Đọc lại bằng `primary` và kiểm tra trạng thái khớp; tiếp theo đọc bằng `secondaryPreferred` hoặc `secondary` để quan sát khác biệt khi có replication lag.
5. Kiểm tra metrics/log phía server và driver để xác nhận node được chọn, thời gian phản hồi và kết quả write concern.

Trong `mongosh` có thể dùng:

~~~javascript
// Chỉ trên môi trường kiểm thử được kiểm soát:
rs.status();
db.adminCommand({ getDefaultRWConcern: 1 });
db.integrationRequests
  .find({ _id: "sourceA:req-101" })
  .readPref("secondaryPreferred");
~~~

Đọc một document từ secondary ngay sau write có thể thấy dữ liệu đã cập nhật, dữ liệu cũ hoặc chưa thấy bản ghi tùy replication. **Không nên viết test kỳ vọng lúc nào cũng quan sát được stale read**; đó là hành vi phụ thuộc timing. Có thể tạo tải kiểm thử/độ trễ mạng trong môi trường cô lập để tăng khả năng quan sát, nhưng vẫn khẳng định chính sách bằng thiết lập read preference và kết quả hợp lệ theo hợp đồng.

### 9.2. Thử bầu lại primary có kiểm soát

Một quy trình:

1. Liệt kê primary ban đầu qua `rs.status()` hoặc `hello`.
2. Ghi yêu cầu R1 với `w:majority`; nhận acknowledgment thành công.
3. Trên primary **của cụm thử nghiệm**, có thể chủ động `rs.stepDown(60)` để kích hoạt election theo điều kiện thực tế.
4. Trong lúc bầu cử, phát một thao tác ghi có ID ổn định; ghi nhận lỗi server selection, retryable error, timeout và thời gian phục hồi.
5. Sau khi có primary mới, kiểm tra R1 và kết quả cuối của thao tác phát trong lúc failover; không suy đoán kết quả chỉ từ exception phía client.
6. Phát lại yêu cầu bằng **cùng request ID** và xác nhận không tạo bản ghi hoặc tác dụng phụ thứ hai.

Nếu write concern timeout xuất hiện, không khẳng định dữ liệu đã bị rollback; đọc lại từ primary mới hoặc truy vấn trạng thái theo khóa idempotency, rồi quyết định retry. Với ứng dụng Java, lỗi `MongoTimeoutException`, `MongoSocketException` hoặc `MongoWriteConcernException` thường mang thông tin khác nhau; ghi lại error label và context khi phân loại. Trên tầng Spring Data, ngoại lệ có thể đã được dịch sang phân cấp `DataAccessException`, nên test không gắn cứng vào một exception class duy nhất.

### 9.3. Bảng kiểm thử theo mục tiêu

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| Normal majority write | Ghi với đủ P-S-S khỏe | Sau ack, đọc dữ liệu theo chính sách đã chọn và ghi nhận latency |
| Một secondary mất kết nối | Dừng một secondary trên P-S-S | Nếu primary và một secondary vẫn tạo majority, ghi `w:majority` có thể tiếp tục |
| Mất đủ member để không đạt majority | Cô lập số node cần thiết trong môi trường test | Ghi majority không thể được xác nhận; báo timeout/lỗi phù hợp, không tự hạ durability |
| Election | Step down primary khi đang có tải | Driver phát hiện primary mới; application retry có giới hạn và idempotent |
| Đọc secondary | Đặt `secondaryPreferred` | Quan sát khả năng lag; không dùng kết quả cho quyết định cần dữ liệu tức thời |
| Secondary không có sẵn | Đặt `secondary` | Lệnh đọc có thể fail/chờ server selection; không tự fallback primary |
| Secondary không có sẵn | Đặt `secondaryPreferred` | Driver có thể fallback sang primary |
| Sai ngưỡng stale | `maxStalenessSeconds=30` | Cấu hình không hợp lệ vì ngưỡng tối thiểu là 90 giây |
| Write concern timeout | Thiết lập timeout ngắn trong điều kiện thiếu ack | Báo trạng thái không chắc chắn, tra cứu lại bằng cùng ID trước khi retry |
| Retry cùng request | Gửi hai lần cùng `(sourceSystem, requestId)` | Không tạo side effect trùng, payload khác cùng key bị từ chối |
| Transaction có đọc | Thử read preference `secondary` cho transaction | Bị từ chối/không hỗ trợ; chuyển sang `primary` |

Test tốt cần xác minh **tác dụng phụ cuối cùng** (document, số lần gọi downstream, message outbox) và giới hạn thời gian, không chỉ xác minh rằng driver có ném exception. Khi kiểm thử tích hợp với Spring Data, dùng database/collection riêng, seed dữ liệu độc lập và dọn kết quả theo khóa test; tránh tái sử dụng tên collection nghiệp vụ của production.

## 10. Quan sát và xử lý sự cố khi vận hành

Các nhóm tín hiệu nên có trên dashboard:

- **Replica set:** vai trò PRIMARY/SECONDARY, số node khỏe, lịch sử election/stepdown, trạng thái quorum.
- **Replication:** oplog window, replication lag theo secondary, node không đồng bộ hoặc chậm áp dụng thay đổi.
- **Write:** latency theo `w`, số lần write concern timeout, retryable write, duplicate-key conflict và kết quả không chắc chắn.
- **Read:** tỷ lệ chọn primary/secondary theo loại truy vấn, server selection latency, timeout, stale-result và độ trễ báo cáo chấp nhận được.
- **Ứng dụng tích hợp:** backlog message/outbox, trạng thái `RECEIVED/PROCESSING/COMPLETED`, yêu cầu retry, lỗi HTTP/broker, thời gian xử lý và số yêu cầu bị phát trùng đã được chặn.

Tên metric phụ thuộc phiên bản MongoDB Exporter, driver Micrometer integration và hệ thống monitoring đang triển khai. Nên đặt nhãn theo `service`, `operation`, `result` và `cluster`; không dùng `requestId` làm label cardinality cao. Correlation ID vẫn cần xuất hiện trong log/tracing để đối chiếu một yêu cầu từ HTTP qua MongoDB đến broker.

### Triệu chứng và cách khoanh vùng

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| Ứng dụng thỉnh thoảng không tìm thấy primary | Election đang diễn ra? Hostname replica set có phân giải được từ pod? TLS/cert? Server selection timeout quá ngắn? |
| Ghi lâu hoặc `wtimeout` | Replication lag, trạng thái đủ data-bearing member, journal, tài nguyên đĩa/network, giới hạn timeout |
| Đọc được `RECEIVED` dù worker đã ghi `COMPLETED` | Query có route tới secondary? Lag bao nhiêu? Read concern/session có phù hợp không? |
| Sau restart xuất hiện record bị phát lại | Write trước đó dùng `w:1`? Có rollback hoặc message redelivery? Idempotency key/index đã đúng chưa? |
| Transaction lỗi vì read preference | Query trong transaction có dùng `primary` không? Có override ở client/repository/query? |
| Driver chỉ kết nối được seed host, không tìm thấy member khác | Advertised host trong `rs.conf()`, DNS, firewall, NetworkPolicy, port mapping và TLS |
| Tăng throughput bằng `nearest` nhưng kết quả thiếu mới | `nearest` tối ưu latency mạng, không bảo đảm fresh read; kiểm tra lag và chọn tuyến đọc phù hợp |

**Không cấu hình tùy tiện:** nếu một luồng HTTP đã xác nhận thành công cho người dùng, việc đổi `w=majority` thành `w=1` chỉ để “hết timeout” có thể làm thay đổi khả năng mất dữ liệu của hợp đồng. Nếu đổi `readPreference=primary` thành `secondaryPreferred` để giảm CPU primary, cần kiểm tra tất cả nhánh từng dựa vào dữ liệu mới nhất.

## 11. Tổng kết và câu hỏi tự kiểm tra

Ba câu phân biệt cần nhớ:

1. **Replica set** giúp dữ liệu được sao chép và có thể bầu primary mới, nhưng failover có khoảng gián đoạn và không ngăn ứng dụng phát lại message.
2. **Read preference** xác định node được chọn để đọc; secondary thường có thể trễ. **Read concern** xác định mức dữ liệu mà câu lệnh được phép nhìn thấy; `majority` không có nghĩa luôn mới nhất.
3. **Write concern** xác định mức acknowledgment; `w:majority` thường phù hợp với bản ghi nghiệp vụ quan trọng, nhưng phải có đủ node mang dữ liệu và timeout vẫn có thể để lại kết quả không chắc chắn.

Tự trả lời các tình huống:

- Vì sao một thao tác ghi đã `w:majority` nhưng ngay sau đó query trên secondary lại đọc thấy trạng thái cũ?
- Vì sao P-S-A không giống P-S-S đối với khả năng xác nhận ghi majority khi secondary mất kết nối?
- Nếu HTTP client timeout ngay lúc election, service nên làm gì trước khi gửi lại yêu cầu?
- Khi nào dùng `secondaryPreferred`, và khi nào bắt buộc đọc `primary`?
- Muốn đọc lại ghi của chính mình từ secondary qua nhiều bước, cần thiết kế session/read/write concern thế nào?
- Vì sao một MongoDB transaction không thể bảo đảm atomicity cho cả thao tác DB và HTTP request ra đối tác?

Trong Spring Boot Integration, một thiết kế đáng tin cậy kết hợp **cấu hình MongoDB có chủ đích**, **khóa idempotency**, **cập nhật có điều kiện**, **transaction đúng phạm vi**, **retry theo loại lỗi** và **metric/log/tracing** có thể đối chiếu được toàn bộ luồng.

## Tài liệu tham khảo

- [MongoDB Manual — Replica Set](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/)
- [MongoDB Manual — Read Preference Staleness](https://www.mongodb.com/docs/manual/core/read-preference-staleness/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Default Read and Write Concerns](https://www.mongodb.com/docs/manual/reference/mongodb-defaults/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [Spring Boot Reference — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Data MongoDB — Querying Documents and Read Preference](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)



