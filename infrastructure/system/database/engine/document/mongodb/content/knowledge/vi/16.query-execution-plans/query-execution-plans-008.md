# Phân biệt thời gian thực thi trong explain với độ trễ ứng dụng

## 1. Một truy vấn có thể “nhanh trong explain” nhưng API vẫn chậm

Khi tối ưu truy vấn MongoDB, ta thường thấy hai số đo không giống nhau:

- Trong `explain("executionStats")`, trường `executionStats.executionTimeMillis` báo **8 ms**.
- Trong log Java hoặc dashboard API, request sử dụng truy vấn đó mất **250 ms**.

Hai con số này **không nhất thiết mâu thuẫn**. Chúng được đo tại **hai ranh giới khác nhau** và có thể đang quan sát **hai lần thực thi khác nhau**.

`explain()` giúp hiểu cách MongoDB **lập kế hoạch và thực thi truy vấn ở phía database**. Thời gian phản hồi ứng dụng lại gồm nhiều bước hơn: chờ connection, truyền lệnh qua mạng, chạy trên server, truyền kết quả, đọc các batch của cursor, giải mã BSON, chuyển đổi dữ liệu, xử lý nghiệp vụ và trả HTTP response.

> **Nguyên tắc:** `executionTimeMillis` trong `explain` là tín hiệu về công việc truy vấn của MongoDB, **không phải** phép đo end-to-end latency mà người dùng ứng dụng trải nghiệm.

Mục tiêu của bài là biết **mỗi chỉ số đo điều gì, không đo điều gì, cách đo nhất quán và cách điều tra khi chúng chênh lệch**. Đây là kỹ năng cốt lõi trong chương *Kế hoạch thực thi*, vì đọc đúng execution plan chỉ hữu ích khi liên hệ được nó với triệu chứng ở ứng dụng.

### 1.1. Bốn câu hỏi khác nhau

| Câu hỏi | Công cụ/góc quan sát phù hợp |
| --- | --- |
| MongoDB chọn `COLLSCAN`, `IXSCAN`, `FETCH` hay `SORT`? | `explain("queryPlanner")` hoặc `explain("executionStats")`. |
| Một lần thực thi được server ghi nhận đã quét bao nhiêu key/document và tốn bao lâu? | `explain("executionStats")`, profiler/log/metrics server tùy trường hợp. |
| Một lệnh `find` hoặc `getMore` mất bao lâu từ phía driver? | Command monitoring, driver metrics, tracing. |
| API mất bao lâu từ nhận request đến gửi response? | Timer ở service, distributed tracing, HTTP server/gateway metrics. |

Không nên thay thế công cụ ở một hàng bằng công cụ ở hàng khác rồi coi số liệu có cùng ý nghĩa.

---

## 2. Ba lớp thời gian cần tách biệt

### 2.1. Lớp A — thời gian trong `explain`

Trường thường gặp:

```javascript
db.orders.find({
  customerId: "C01"
}).explain("executionStats");
```

Trong kết quả, một phần có thể giống:

```javascript
{
  executionStats: {
    executionSuccess: true,
    nReturned: 20,
    executionTimeMillis: 7,
    totalKeysExamined: 20,
    totalDocsExamined: 20
  }
}
```

Đây là **ví dụ giả định về một phần output**, không phải output đảm bảo từ mọi phiên bản. Số `7` là thời gian mà MongoDB báo cho việc lựa chọn/thực thi kế hoạch trong thao tác `explain` theo cách server đo lường. Nó **không** bao gồm toàn bộ vòng đời HTTP request của ứng dụng.

### 2.2. Lớp B — thời gian thực hiện lệnh qua driver

Ở ứng dụng Java, một command như `find` cần đi qua driver, kết nối mạng, server rồi nhận response. Command monitoring có thể ghi thời lượng một lệnh từ góc nhìn driver, phản ánh thời gian round trip và server processing cho lệnh đó.

Nếu truy vấn trả nhiều batch, sẽ có thể có:

```text
find
getMore
getMore
...
```

Vì vậy, **một lệnh `find` không nhất thiết đại diện cho toàn bộ thời gian tải kết quả**. Muốn đo toàn bộ quá trình đọc cursor, phải cộng/quan sát các batch và công việc ở ứng dụng, không chỉ nhìn thời gian command đầu.

### 2.3. Lớp C — thời gian end-to-end của ứng dụng

Một endpoint có thể trải qua:

```text
HTTP request tới service
    |
    +--> Xác thực, kiểm tra tham số, routing
    |
    +--> Chọn server / chờ connection pool
    |
    +--> MongoDB find, xử lý server, network round trip
    |
    +--> getMore nếu cursor còn dữ liệu
    |
    +--> BSON decoding và chuyển sang DTO
    |
    +--> Business logic / gọi service khác
    |
    +--> JSON serialization, nén, HTTP response
    v
Client nhận phản hồi
```

Nếu đo từ **HTTP ingress tới khi service hoàn tất trả response**, các bước trong endpoint đều có thể đóng góp. Nếu đo từ **trình duyệt** thì còn có mạng phía người dùng, gateway, TLS, tải tài nguyên giao diện và thời điểm render. Vì thế, ngay cả khái niệm “độ trễ ứng dụng” cũng phải được định nghĩa rõ.

### 2.4. Sơ đồ ba đồng hồ

```text
                          Dòng thời gian (minh họa)
HTTP ingress ------------------------------------------------ HTTP response
       |                                                        |
       |  app logic | pool | find | decode | getMore | JSON ...  |
       |            |      |      |        |         |          |
       +------------+------+------+--------+---------+----------+
       <---------------- API latency -------------------------->

                           <find round trip>
                                   <server work>

                        explain("executionStats")
                              <explain server work>
```

Phần `explain` thường là **một thao tác riêng**, không phải đoạn thời gian được ghi bên trong cùng request HTTP. Không thể đơn giản lấy `API latency - explain.executionTimeMillis` để khẳng định phần chênh lệch chính xác bằng network.

---

## 3. `explain()` thực hiện công việc gì?

MongoDB cho phép chạy explain với các mức độ chi tiết khác nhau:

| Verbosity | Điều muốn biết | Có thống kê thực thi? |
| --- | --- | --- |
| `queryPlanner` | Những thông tin lập kế hoạch, winning plan và các phương án liên quan. | Không cung cấp đầy đủ số liệu thực thi như `executionStats`. |
| `executionStats` | Thực thi kế hoạch được chọn để ghi nhận kết quả/chi phí. | Có số liệu như `nReturned`, `executionTimeMillis`, `totalKeysExamined`, `totalDocsExamined`. |
| `allPlansExecution` | Thêm thông tin các kế hoạch ứng viên trong quá trình chọn plan. | Có thông tin thực thi và một phần thống kê của các phương án trong giai đoạn chọn kế hoạch. |

Ví dụ:

```javascript
// Xem kế hoạch, không tập trung vào runtime.
db.orders.find({ customerId: "C01" })
  .explain("queryPlanner");

// Xem kế hoạch được chạy và các chỉ số chi phí thực thi.
db.orders.find({ customerId: "C01" })
  .explain("executionStats");

// Nghiên cứu thêm quá trình cạnh tranh giữa các plan.
db.orders.find({ customerId: "C01" })
  .explain("allPlansExecution");
```

Không nên dùng `allPlansExecution` cho mọi lần quan sát nếu chỉ cần các thông số cơ bản: output lớn và phức tạp hơn, không tự làm chẩn đoán chính xác hơn.

### 3.1. `executionStats.executionTimeMillis` là gì?

Đây là số mili giây MongoDB ghi nhận cho **lựa chọn và thực thi query plan trong thao tác explain**. Cách tính và nội dung chi tiết có thể phụ thuộc engine, phiên bản và loại thao tác.

Điều nó **không phải**:

- Không phải độ trễ HTTP của endpoint.
- Không phải toàn bộ thời gian ứng dụng tải và xử lý mọi document qua cursor.
- Không phải thời gian mạng giữa service và MongoDB.
- Không phải tổng thời gian chờ ở connection pool của driver.
- Không phải số đo luôn giống với một `find()` thông thường, vì `explain` có ngữ nghĩa lập kế hoạch riêng.
- Không phải lời bảo đảm cho p95/p99 latency ở production.

### 3.2. `executionTimeMillisEstimate` trong từng stage

Một số cây `executionStages` chứa giá trị như:

```javascript
{
  stage: "FETCH",
  nReturned: 20,
  executionTimeMillisEstimate: 4,
  inputStage: {
    stage: "IXSCAN",
    nReturned: 20,
    executionTimeMillisEstimate: 2
  }
}
```

Đây là output rút gọn để minh họa. `executionTimeMillisEstimate` ở **stage** là ước lượng có ngữ nghĩa riêng, **không phải bộ đồng hồ độc lập có thể cộng đơn giản**. Một stage cha bao gồm hoạt động của stage con; việc cộng 4 + 2 rồi coi bằng tổng truy vấn có thể **đếm hai lần** công việc.

Với các engine mới, cây stage và trường thống kê có thể khác cấu trúc cổ điển. Phải đọc execution plan theo phiên bản đang dùng.

### 3.3. `totalKeysExamined`, `totalDocsExamined`, `nReturned`

Ba số này thường quan trọng hơn chênh lệch vài mili giây trong một lần chạy:

- `totalKeysExamined`: số index entries được xem xét.
- `totalDocsExamined`: số document được xem xét.
- `nReturned`: số document được trả bởi phần thực thi query trong explain.

Ví dụ giả định:

| Query | Keys examined | Docs examined | Returned | Tín hiệu |
| --- | ---: | ---: | ---: | --- |
| Equality trên unique key | 1 | 1 | 1 | Đường tìm kiếm chọn lọc. |
| Compound index phù hợp | 25 | 25 | 20 | Tương đối ít công việc. |
| Index kém chọn lọc | 250.000 | 120.000 | 20 | Quét nhiều và lọc nhiều. |
| Covered query | 20 | 0 | 20 | Có thể tránh FETCH document. |
| Collection scan | 0 | 1.000.000 | 20 | Quét rộng. |

Các con số chỉ là **tình huống minh họa**, không phải benchmark MongoDB.

Nếu explain báo `executionTimeMillis: 0` trên dataset nhỏ, điều đó thường liên quan độ phân giải báo cáo thời gian hoặc thao tác rất nhanh; **không có nghĩa database không sử dụng CPU hay I/O**.

---

## 4. Điều đặc biệt quan trọng: explain không hoạt động y hệt truy vấn bình thường

MongoDB xử lý explain như **một truy vấn riêng** và không dùng/cập nhật plan cache theo cách của một lệnh truy vấn thông thường. Do đó, winning plan hoặc chi phí lập kế hoạch trong explain có thể khác con đường một request thật đang đi qua.

Ví dụ:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Không nên kết luận:

> “API chắc chắn dùng đúng winning plan của lệnh explain này.”

Một lệnh thật có thể chịu ảnh hưởng của plan cache, lịch sử hoạt động, index đã thay đổi, metadata và trạng thái workload. Explain rất hữu ích để **điều tra lựa chọn kế hoạch**, nhưng muốn biết **thực thi thật** của ứng dụng, nên kết hợp command monitoring, profiler/log và tracing.

### 4.1. Explain cũng cần tài nguyên

`explain("executionStats")` thực thi công việc để thu thập số liệu. Với query lớn, việc này có thể gây tải đáng kể; không chạy lặp lại các phép đo đắt tiền vào production chỉ để lấy một con số.

### 4.2. Chi phí thu thập thống kê có thể làm số đo khác đi

Thao tác đo có overhead riêng. Một lệnh explain vừa chạy sau khi cache được làm nóng có thể nhanh hơn lần đầu, trong khi explain chạy lúc server đang chịu tải có thể chậm hơn. Thông tin thống kê hữu ích nhưng không phải phép đo benchmark hoàn hảo của mọi request.

### 4.3. Đừng lấy hai request khác nhau làm phép trừ chính xác

Giả sử:

```text
10:00:00 explain.executionTimeMillis = 7 ms
10:05:00 API request duration       = 180 ms
```

Trong năm phút có thể xảy ra:

- Cache page khác nhau.
- Concurrency khác nhau.
- Replica khác nhau nhận truy vấn.
- Query parameter hoặc kết quả có độ chọn lọc khác.
- Plan cache/plan selection khác.
- Lượng dữ liệu trả và số batch khác.
- Network khác.
- Ứng dụng xử lý thêm công việc sau query.

Vì thế phép tính `180 - 7 = 173 ms network` là **không có cơ sở**.

---

## 5. Một endpoint thật gồm những giai đoạn nào?

Để phân tích chênh lệch, chia request thành các đoạn quan sát được:

| Giai đoạn | Ví dụ công việc | Có nằm trong explain không? |
| --- | --- | --- |
| Ingress/gateway | HTTP routing, TLS, reverse proxy. | Không. |
| App trước MongoDB | Authentication, validation, build filter. | Không. |
| Server selection | Chọn node theo read preference và topology. | Không. |
| Pool wait | Chờ được mượn connection. | Không. |
| Driver command | Encode lệnh, gửi qua mạng, nhận response. | Không đầy đủ; explain chỉ phản ánh công việc server của thao tác explain riêng. |
| Query server-side | Chọn và thực thi plan, đọc index/document, xử lý sort. | Là trọng tâm của explain. |
| Cursor/getMore | Nhận các batch còn lại. | Explain không đại diện trực tiếp cho chuỗi command getMore của client. |
| BSON -> object | Decode dữ liệu, mapping DTO/POJO. | Không. |
| Business logic | Join dữ liệu ứng dụng, gọi service khác. | Không. |
| HTTP response | Serialize JSON, nén, truyền qua mạng. | Không. |

Đây là bảng phân ranh giới, không phải bảng cộng thời gian chính xác: một số công việc có thể chồng lấp, và **các công cụ đo ở các tầng khác nhau có ranh giới thời gian khác nhau**.

### 5.1. Pool wait và server selection

Giả sử connection pool đã hết connection rảnh, request phải chờ 120 ms mới lấy được connection. Ngay sau đó MongoDB xử lý command trong 6 ms. `explain` có thể báo 6 ms hoặc một con số tương tự, nhưng ứng dụng đã mất hơn 120 ms trước khi query bắt đầu.

Tình huống này cần quan sát **connection pool metrics và server selection metrics**, không thể giải quyết chỉ bằng thêm index.

### 5.2. Network và payload

Một query server-side có thể rất nhanh, nhưng trả hàng chục nghìn document lớn khiến:

- Response phải truyền nhiều dữ liệu qua mạng.
- Client giải mã nhiều BSON object.
- Ứng dụng tạo DTO/JSON lớn.
- Gateway/client phải nhận một payload nặng.

Cách khắc phục thường là `limit`, projection, pagination hoặc thay đổi hợp đồng API; index chỉ xử lý một phần đường truy cập.

### 5.3. Thời gian sau query

Một service có thể tải 20 đơn trong 8 ms nhưng gọi tiếp ba dịch vụ bên ngoài, mỗi dịch vụ mất vài chục mili giây, rồi tạo JSON response. API latency tổng thể khi ấy không phải một phép đo chậm của MongoDB.

Không nên “tối ưu index cho đến khi explain về 0 ms” nếu phần thời gian lớn nhất lại ở logic ứng dụng.

---

## 6. Chuẩn bị ví dụ MongoDB

Giả sử collection thử nghiệm `orders` có schema:

```javascript
{
  _id: "O1001",
  customerId: "C01",
  status: "PAID",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  totalMinor: NumberLong("520000"),
  items: [
    { sku: "P10", quantity: 2 },
    { sku: "P11", quantity: 1 }
  ]
}
```

Một endpoint được yêu cầu:

> “Lấy 20 đơn PAID mới nhất của khách C01, chỉ trả mã đơn, ngày và tổng tiền.”

Query:

```javascript
db.orders.find(
  {
    customerId: "C01",
    status: "PAID"
  },
  {
    _id: 1,
    createdAt: 1,
    totalMinor: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Để phục vụ lọc và thứ tự ổn định, có thể thử index:

```javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_customer_status_recent"
  }
);
```

Đây là **ứng viên** dựa trên filter/sort, chưa chắc tối ưu mọi workload. Vì projection cần `totalMinor` không có trong index, query có thể vẫn cần `FETCH`.

### 6.1. Lấy explain

```javascript
db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 1, createdAt: 1, totalMinor: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20)
 .explain("executionStats");
```

Nếu query planner chọn index, kết quả có thể cho thấy `IXSCAN`, `FETCH`, số key/document examined thấp và không có bước `SORT` riêng. Thời gian trong explain là **chỉ số ở server cho lần explain**.

### 6.2. Đo lệnh đọc thật trong `mongosh`

```javascript
const start = Date.now();

const results = db.orders.find(
  { customerId: "C01", status: "PAID" },
  { _id: 1, createdAt: 1, totalMinor: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20)
 .toArray();

const elapsedMs = Date.now() - start;

printjson({
  returned: results.length,
  clientElapsedMs: elapsedMs
});
```

Ở đây `clientElapsedMs` đo **thời gian `mongosh` cần để chạy thao tác và lấy toàn bộ kết quả trả về** vào array trong tiến trình shell, bao gồm các công việc của shell/driver và network. Nó **không phải** thời gian của HTTP service Java, và độ phân giải `Date.now()` theo ms có giới hạn khi đo thao tác rất ngắn.

Đặc biệt, cách đo này vẫn không đại diện cho JSON serialization và gửi HTTP response của ứng dụng thực tế.

### 6.3. Đừng đo hai query không giống nhau

Hai lệnh sau có thể có thời gian rất khác:

```javascript
// Query A: 20 đơn gần nhất.
db.orders.find({ customerId: "C01" })
  .sort({ createdAt: -1 })
  .limit(20);

// Query B: toàn bộ lịch sử.
db.orders.find({ customerId: "C01" })
  .sort({ createdAt: -1 });
```

Nếu API đang tải mọi document trong query B, nhưng explain chỉ chạy query A, chênh lệch thời gian **không có ý nghĩa chẩn đoán**.

---

## 7. Cursor và lazy execution: lý do đo thời gian Java rất dễ sai

MongoDB Java Sync Driver thường sử dụng các API trả về `FindIterable` hoặc cursor. **Việc dựng một `FindIterable` không đồng nghĩa toàn bộ query đã được thực thi và kết quả được tải hết**.

Sai lầm phổ biến:

```java
long start = System.nanoTime();

FindIterable<Document> iterable = collection.find(
    Filters.eq("customerId", "C01")
);

long elapsedMs =
    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);

System.out.println("MongoDB query took " + elapsedMs + " ms");
```

Số đo này chủ yếu phản ánh việc **tạo đối tượng mô tả truy vấn**, không chắc đã gửi lệnh `find` đến server. Kết luận “MongoDB chỉ mất 0 ms” từ đoạn code này có thể sai hoàn toàn.

### 7.1. Đo đến khi thực sự đọc hết kết quả

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class MongoReadTimer {

    public static long readTwentyOrders(
            MongoCollection<Document> orders,
            String customerId
    ) {
        long started = System.nanoTime();
        long count = 0;

        try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("customerId", customerId),
                        Filters.eq("status", "PAID")
                    )
                )
                .projection(
                    Projections.include(
                        "_id", "createdAt", "totalMinor"
                    )
                )
                .sort(
                    Sorts.orderBy(
                        Sorts.descending("createdAt"),
                        Sorts.descending("_id")
                    )
                )
                .limit(20)
                .iterator()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                count++;

                // Chỉ minh họa tiêu thụ document.
                // Đo mapping DTO riêng nếu cần.
            }
        }

        long elapsedNanos = System.nanoTime() - started;
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

        System.out.printf(
            "loaded=%d; cursorElapsedMs=%d%n",
            count,
            elapsedMs
        );
        return elapsedMs;
    }
}
```

Timer bắt đầu trước lúc mở cursor và kết thúc sau khi cursor đã được tiêu thụ/đóng. Nó gần hơn với thời gian **toàn bộ quá trình đọc từ driver**, bao gồm chờ connection, network, server, decode và iteration tại client. Tuy nhiên:

- Đây vẫn chưa phải toàn bộ HTTP request.
- Nếu trong vòng lặp còn có xử lý nghiệp vụ nặng, timer cũng bao gồm công việc đó.
- Không nên `println` từng document nếu muốn đo riêng đọc MongoDB: ghi console làm sai lệch latency.
- `System.nanoTime()` phù hợp để đo khoảng thời gian trong cùng tiến trình, không phải timestamp có thể đối chiếu trực tiếp giữa nhiều máy.
- Đếm document không đo chi phí chuyển đổi sang object nghiệp vụ hoặc JSON response; các bước ấy cần span riêng.

### 7.2. Đo “first result” khác đo “all results”

Nếu chỉ gọi:

```java
Document first = collection.find(
    Filters.eq("customerId", "C01")
).first();
```

ta đang đo yêu cầu lấy document đầu tiên, **không phải** quá trình tải tất cả kết quả của query không giới hạn.

Nếu API thực tế làm:

```java
List<Document> all = collection.find(
    Filters.eq("customerId", "C01")
).into(new ArrayList<>());
```

nó có thể tải rất nhiều batch, tiêu thụ nhiều RAM và mất nhiều thời gian. Không so sánh trực tiếp một `first()` với một endpoint materialize 100.000 document.

### 7.3. `batchSize` và `getMore`

MongoDB truyền cursor result theo nhiều batch. Driver có thể gửi lệnh `find` nhận batch đầu, rồi gọi `getMore` khi cần.

```text
Service gọi query
      |
      v
   find command --------> batch 1
      |
      v
   getMore -------------> batch 2
      |
      v
   getMore -------------> batch 3
      |
      v
   Cursor hoàn tất
```

`batchSize` ảnh hưởng số batch, chi phí round trip và lượng bộ nhớ cho mỗi batch, nhưng không đơn giản là “batch càng lớn càng tốt”. Batch quá nhỏ làm tăng số lần network; batch quá lớn có thể tăng memory footprint và thời gian đến response đầu. MongoDB còn có giới hạn kích thước message và batch ở mức protocol.

Một truy vấn `limit(20)` có thể chỉ cần một batch trong tình huống thông thường; truy vấn trả hàng trăm nghìn document thường có nhiều `getMore`.

### 7.4. Time to first result và time to drain cursor

Hai metric cần tách:

- **Time to first result:** từ lúc yêu cầu đến khi có document đầu.
- **Time to drain cursor:** từ lúc yêu cầu đến khi đọc xong mọi document cần thiết.

Một API streaming có thể bắt đầu gửi response sớm nhưng còn truyền dữ liệu hàng giây. Một API materialize mọi document trước khi trả JSON có thể có time to first byte cao. Chỉ nhìn một trường `executionTimeMillis` trong explain không thể phân biệt các dạng latency này.

---

## 8. Command monitoring đo gì?

Java Driver hỗ trợ command monitoring thông qua `CommandListener`. Ta có thể ghi thời gian của các lệnh như `find`, `getMore`, `aggregate` (và các lệnh khác) **từ góc nhìn driver**, để xem truy vấn nào và batch nào mất thời gian.

Ví dụ rút gọn:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;

import java.util.concurrent.TimeUnit;

public final class MongoCommandTiming implements CommandListener {

    @Override
    public void commandStarted(CommandStartedEvent event) {
        String name = event.getCommandName();
        if ("find".equals(name) || "getMore".equals(name)) {
            System.out.printf(
                "Mongo command started: %s requestId=%d%n",
                name,
                event.getRequestId()
            );
        }
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        String name = event.getCommandName();
        if ("find".equals(name) || "getMore".equals(name)) {
            System.out.printf(
                "Mongo command succeeded: %s elapsedMs=%d%n",
                name,
                event.getElapsedTime(TimeUnit.MILLISECONDS)
            );
        }
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.err.printf(
            "Mongo command failed: %s%n",
            event.getCommandName()
        );
    }

    public static MongoClientSettings.Builder configure(
            MongoClientSettings.Builder builder
    ) {
        return builder.addCommandListener(
            new MongoCommandTiming()
        );
    }
}
```

Đây là mã minh họa cho MongoDB Java Sync Driver có các event API tương ứng. Listener được đăng ký **trước khi tạo MongoClient**; không tự hoạt động chỉ vì lớp được định nghĩa.

**Command duration không phải HTTP latency và cũng không phải thuần CPU time của server.** Nó quan sát lệnh ở driver, gồm tương tác với server và mạng trong phạm vi event được driver đo; các bước trước khi lấy connection, logic ứng dụng sau khi nhận response và serialization HTTP không tự nằm trong một duration command.

### 8.1. Những điều cần tránh khi log command

- Không log nguyên payload hoặc thông tin đăng nhập/PII khi không cần thiết.
- Không in ra stdout đồng bộ hàng nghìn dòng mỗi giây trên hệ thống tải cao; logging cũng có overhead.
- Không chỉ log `find` rồi bỏ qua `getMore`, khiến thời gian tải nhiều batch bị ẩn.
- Không mặc định một command tương đương một request HTTP; một endpoint có thể gọi nhiều query, còn một query có thể phát sinh nhiều command.
- Không coi requestId của MongoDB command là ID xuyên suốt HTTP trace nếu chưa tự liên kết.

### 8.2. Distributed tracing và tương quan request

Một hệ thống có OpenTelemetry/tracing có thể chia trace thành:

```text
HTTP GET /customers/C01/orders                    220 ms
    ├─ auth + validate                             15 ms
    ├─ Mongo pool/server-selection                  55 ms
    ├─ Mongo find command                           12 ms
    ├─ Mongo getMore commands                       20 ms
    ├─ DTO mapping                                  35 ms
    ├─ Call external pricing service                60 ms
    └─ JSON serialization/other                     23 ms
```

Các số trên là **ví dụ giả định** với các span không chồng lấp để minh họa. Trên trace thực, nhiều span có thể lồng nhau hoặc chạy song song, nên **không luôn được cộng duration của mọi span để ra total**. Khi phân tích, quan sát critical path, thời gian chờ và vùng chưa được instrument.

---

## 9. `explain` và profiler/log trên server khác nhau thế nào?

`explain` là một **thao tác chủ động**, chạy query được yêu cầu để mô tả plan và thống kê.

Profiler hoặc slow-query log ghi lại **những thao tác thật xảy ra trên server**, tùy cấu hình thu thập. Những nguồn này có thể cho biết duration của command, số key/doc examined, index được dùng và một số thông tin liên quan tới cursor.

Sự khác biệt:

| Nguồn | Ưu điểm | Giới hạn |
| --- | --- | --- |
| `explain("queryPlanner")` | Xem plan và cấu trúc index mà không cần thu thập thống kê thực thi đầy đủ. | Không phải số đo runtime. |
| `explain("executionStats")` | Có counters và thời gian của một phép explain. | Có hành vi riêng với plan cache, không đại diện mọi request. |
| Profiler/slow log | Ghi nhận thao tác server thực tế, có ngữ cảnh runtime. | Chỉ bao quát điều server thấy; thu thập có overhead và có thể chỉ lấy mẫu. |
| Driver command monitoring | Biết lệnh thực, round trip và `getMore`. | Chưa bao gồm toàn bộ thời gian HTTP/business logic. |
| End-to-end tracing | Thấy đường đi của request qua nhiều thành phần. | Chỉ chi tiết nếu span/instrumentation được gắn đúng. |

Một số metric của `getMore` có thể được ghi riêng khỏi `find`. Nếu muốn hiểu thời gian tải toàn bộ cursor ở ứng dụng, cần nhìn **chuỗi command**, không chỉ entry đầu.

### 9.1. Đọc server log có đúng bằng `executionTimeMillis` không?

Không nhất thiết. Chúng có ranh giới, điều kiện thu thập, workload và ngữ cảnh khác nhau. Cả hai cũng khác với thời gian người dùng nhìn thấy.

Nếu thấy một slow-query log báo 120 ms còn explain tương tự báo 15 ms, cần kiểm tra:

- Có cùng filter, sort, limit, projection và index không?
- Có cùng node, plan và thời điểm tải không?
- Thao tác thật có chờ gì ở server mà explain không tái hiện được không?
- Cache đã nóng khi chạy explain chưa?
- Query thật trả nhiều dữ liệu hơn hoặc cursor được xử lý theo nhiều batch không?

Không lấy chênh lệch làm “lỗi của profiler”.

---

## 10. Plan cache khiến hai lần chạy có thể khác nhau

MongoDB query planner có thể xem xét nhiều kế hoạch để chọn đường tốt cho hình dạng truy vấn. Với các truy vấn thông thường, plan cache có thể giúp tái sử dụng kế hoạch đã được chọn theo điều kiện áp dụng.

`explain()` **không dùng plan cache giống truy vấn thông thường và không tạo entry cache từ lần explain**. Vì vậy, thời gian lập kế hoạch và winning plan của explain có thể không phản ánh trực tiếp request của ứng dụng đã dùng cached plan.

Ví dụ:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Nếu query thực tế có lúc dùng plan khác, không nên sửa bằng cách ép `hint()` ngay. Cần xác định:

1. Có nhiều index ứng viên không?
2. Phân phối khách hàng có bị lệch (một khách có hàng triệu đơn, nhiều khách chỉ vài đơn) không?
3. Query shape/parameter có giống nhau không?
4. Server/phiên bản, collation, read preference có khác không?
5. Thống kê kế hoạch thực của operation chậm nói gì?

Dùng `hint()` có thể giúp so sánh các index ứng viên trong môi trường thử nghiệm:

```javascript
db.orders.find({
  customerId: "C01",
  status: "PAID"
}).sort({ createdAt: -1 })
  .hint({
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  })
  .explain("executionStats");
```

Ví dụ giả định index tương ứng đã tồn tại. **Ép plan không phải mặc định tối ưu**: index tốt cho một tập tham số có thể kém với tập tham số khác.

---

## 11. Độ nóng của cache và tải đồng thời

Hai lần chạy cùng query vẫn có thể cho độ trễ khác nhau dù execution plan không đổi.

### 11.1. Cache lạnh và cache nóng

Lần đầu MongoDB cần đọc một số trang index/document từ storage, lần sau các trang đó có thể đã nằm trong WiredTiger cache hoặc filesystem cache.

```text
Lần đầu:
    index page -> storage
    data page  -> storage
    query work -> kết quả

Lần sau:
    index page -> cache
    data page  -> cache
    query work -> kết quả
```

Sự khác biệt có thể đáng kể khi working set lớn. Không có nghĩa một hệ thống sản xuất luôn giữ cache nóng như benchmark lặp cùng truy vấn. Hệ thống thường phải phục vụ nhiều khóa và nhiều kiểu query.

### 11.2. Contention, CPU và I/O

Cùng một query có thể chậm hơn khi:

- Server có quá nhiều request đồng thời.
- CPU đang bị chiếm bởi những aggregation khác.
- Storage IOPS hoặc latency đang cao.
- Cache bị cạnh tranh bởi dữ liệu/index khác.
- Hoạt động ghi tạo áp lực lên cache và cơ chế duy trì.
- Replication/topology dẫn tới node được truy vấn khác nhau.

Một lần explain chạy khi máy rảnh không cho biết p99 của query trong giờ cao điểm.

### 11.3. Cùng plan không đồng nghĩa cùng thời gian

Plan `IXSCAN -> FETCH` có thể quét đúng 20 key trong cả hai lần, nhưng thời gian khác do trang dữ liệu nằm ở RAM hay storage, hoặc do tải đồng thời. **Execution counters giải thích khối lượng công việc logic; latency phản ánh cả tài nguyên và hoàn cảnh thực thi.**

---

## 12. `limit`, projection, `skip`, sort và kích thước kết quả

Để so sánh explain với request thật, mọi thuộc tính của query phải tương đương:

| Thuộc tính | Vì sao quan trọng? |
| --- | --- |
| Filter | Quyết định độ chọn lọc và candidate plan. |
| Sort | Có thể yêu cầu index đúng thứ tự hoặc bước `SORT`. |
| Projection | Quyết định có thể cover query và kích thước payload. |
| Limit | Giới hạn số kết quả, có thể giúp dừng sớm nếu đường đọc phù hợp. |
| Skip | Offset sâu có thể khiến engine duyệt nhiều khóa. |
| Collation | Ảnh hưởng so sánh chuỗi và việc dùng index. |
| Batch size | Ảnh hưởng số response/`getMore` ở client thật. |
| Read preference | Có thể gửi command đến node khác. |
| Read concern | Có thể làm thay đổi ngữ nghĩa và chi phí đọc. |
| Hint | Ép một index, có thể khác planner mặc định. |
| Aggregation stages | Có thể thay đổi khả năng dùng index và số document được xử lý. |

### 12.1. Bẫy của `skip`

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 })
  .skip(200000)
  .limit(20);
```

Dù có index, engine có thể phải duyệt nhiều key để bỏ qua 200.000 kết quả đầu. Một explain cho trang đầu `limit(20)` không phản ánh trang sâu dùng `skip`.

**Keyset pagination** thường hiệu quả hơn khi có thứ tự ổn định:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});

const lastCreatedAt = ISODate("2026-11-02T09:30:00Z");
const lastId = "O1002";

db.orders.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Ví dụ giả định `_id` là chuỗi và cần so sánh theo thứ tự như đã lưu; phải giữ kiểu và collation nhất quán.

### 12.2. Projection và payload

```javascript
// Trả cả document lớn:
db.orders.find({ customerId: "C01" });

// Trả các field cần thiết:
db.orders.find(
  { customerId: "C01" },
  { _id: 1, createdAt: 1, status: 1 }
);
```

Projection có thể giảm lượng dữ liệu gửi và decode, nhưng không tự bảo đảm query đã được cover. Dù MongoDB vẫn FETCH document, response nhỏ hơn có thể giúp latency ứng dụng. Ngược lại, một query đã cover nhưng trả hàng trăm nghìn key vẫn có thể tạo payload lớn.

---

## 13. Query aggregation: số liệu ở các stage không phải thời gian API

Ví dụ dashboard cần tổng doanh thu theo khách:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalRevenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { totalRevenueMinor: -1 } },
  { $limit: 10 }
]);
```

Explain:

```javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      totalRevenueMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { totalRevenueMinor: -1 } },
  { $limit: 10 }
]);
```

Một aggregation có thể phải đọc hàng triệu đơn để tạo mười dòng tổng hợp. `nReturned` cuối bằng 10 không có nghĩa chỉ có mười document nguồn được xử lý. Cần xem input/output từng stage và số document/index được kiểm tra.

### 13.1. Stage blocking và latency đến kết quả đầu tiên

`$sort` và `$group` có thể cần tích lũy nhiều dữ liệu trước khi trả một kết quả. Vì vậy, thời gian có document đầu tiên khác nhiều so với một query dùng index và `limit(10)` trả trực tiếp.

### 13.2. Không cộng các stage estimate

Nếu explain hiển thị thời gian ước lượng ở nhiều stage, không cộng chúng để khẳng định tổng latency. Stage con và cha có thể bao hàm công việc của nhau; một số stage dùng sampling/estimation riêng, và output khác nhau giữa các engine.

### 13.3. Khi index không đủ

Index có thể giúp `$match` và đôi khi `$sort`, nhưng không tự giải quyết chi phí tổng hợp lượng dữ liệu lớn. Nếu dashboard tính lại cùng số liệu liên tục, có thể cân nhắc **computed summaries** hoặc pre-aggregation với chính sách cập nhật/đối soát rõ ràng.

---

## 14. Sharded cluster và read preference

Trong hệ sharded, một truy vấn có thể đi qua `mongos` rồi được chuyển đến một hoặc nhiều shard. Explain có thể chứa các phần kế hoạch và thống kê riêng cho shard.

```text
Java application
       |
       v
     mongos
     /   \
    v     v
 Shard A Shard B
```

Độ trễ end-to-end có thể chịu ảnh hưởng của:

- Số shard được truy cập.
- Thời gian phối hợp và ghép kết quả tại router.
- Tốc độ của shard chậm nhất.
- Network giữa router và shard.
- Đường trả dữ liệu từ mongos về ứng dụng.

**Không cộng thời gian `executionTimeMillis` của từng shard rồi coi đó là HTTP latency.** Các shard có thể chạy song song; số liệu ở từng tầng có phạm vi và cách đo khác nhau. Cần đọc plan sharded và tracing của request thật.

Read preference cũng quan trọng: API có thể đọc từ secondary còn explain được chạy trên primary trong một shell khác. Nếu node khác về tải, cache hoặc độ trễ mạng, số đo không thể so sánh trực tiếp.

---

## 15. Bốn ca điều tra chênh lệch điển hình

### Ca A — Explain nhanh, API chậm vì connection pool

**Tình huống minh họa:**

```text
explain.executionTimeMillis:    6 ms
Mongo find command round trip:  9 ms
Connection pool wait:         140 ms
API request latency:          185 ms
```

Khả năng cao phần lớn thời gian nằm ở việc chờ connection hoặc công việc khác trước/sau query. Hành động:

1. Xem pool size, checked-out connections, pending checkout và thời gian chờ.
2. Xem số request đồng thời và thời gian giữ cursor/connection.
3. Xem có query/cursor lâu làm pool bận hay không.
4. Điều chỉnh concurrency, timeout/pool theo workload **sau khi đo**, không chỉ tăng pool size vô hạn.

Chỉ thêm index không trực tiếp loại bỏ thời gian chờ pool trong mọi trường hợp, dù query nhanh hơn có thể gián tiếp giải phóng connection sớm hơn.

### Ca B — Explain nhanh, API chậm vì nhiều `getMore`

```text
explain:                       12 ms
find command:                   9 ms
getMore commands:           8 × 20 ms
DTO mapping + JSON:            80 ms
HTTP total:                   290 ms
```

Các số chỉ là ví dụ. Query có thể cần trả hàng chục nghìn document và nhiều batch. Hành động:

- Thống kê số document thực tế trả.
- Đếm `getMore` và tổng byte.
- Xem API có thật sự cần toàn bộ dữ liệu không.
- Thêm projection, limit, keyset pagination hoặc streaming hợp lý.
- Đo thời gian cursor drain riêng với JSON serialization.

Nếu chỉ so explain rồi kết luận “MongoDB không chậm nên không cần làm gì”, sẽ bỏ sót chi phí của việc tải nhiều dữ liệu từ MongoDB.

### Ca C — Explain chậm vì quét nhiều, API cũng chậm

```text
explain:
  executionTimeMillis:       480
  totalKeysExamined:      450000
  totalDocsExamined:      280000
  nReturned:                  20

API p95 latency:             650 ms
```

Đây là tín hiệu cần xem **query plan và index**. Kiểm tra filter, sort và compound index, nhất là khi index đã có nhưng vẫn quét rất nhiều key. Thử phương án index dựa trên access pattern, đo trước/sau, đồng thời theo dõi chi phí ghi của index mới.

### Ca D — Explain nhanh sau khi cache nóng, production p99 vẫn cao

Một người chạy lặp explain trên đúng khách C01 trong khi production truy vấn ngẫu nhiên hàng triệu khách. Cache của những trang dành cho C01 có thể nóng, làm số đo thấp. Trong khi đó p99 bao gồm những request đụng các trang lạnh hoặc lúc I/O quá tải.

Hành động:

- Thử với phân phối tham số đại diện thay vì một khách cố định.
- Đo cả warm/cold workload khi phù hợp.
- Phân tích storage latency, cache hit/miss và working set.
- Quan sát p95/p99 dưới concurrency thực tế.

### Ca E — Explain và API thực chất không cùng câu truy vấn

Ví dụ explain chỉ dùng:

```javascript
db.orders.find({
  customerId: "C01"
}).limit(20).explain("executionStats");
```

Trong khi API thật dùng:

```javascript
db.orders.find({
  customerId: "C01"
}).sort({ createdAt: -1 })
  .skip(50000)
  .limit(100);
```

Phần sort, skip và limit khác nhau khiến cả chi phí truy vấn và lượng dữ liệu tải khác. Trước khi phân tích network, cần **tái tạo đúng query shape**, projection, sort, skip, collation và điều kiện đang dùng trong API.

### Ca F — Command MongoDB nhanh nhưng HTTP chậm do service khác

```text
MongoDB command total:      15 ms
Call pricing API:          110 ms
Business rules:             25 ms
JSON serialization:         20 ms
HTTP total:                190 ms
```

Tối ưu MongoDB lúc này có trần lợi ích rất thấp. Cần xử lý critical path ở ứng dụng hoặc service dependency thay vì tạo thêm index.

---

## 16. Một cách đo tổng thể bằng Java

Đo thời gian ở endpoint, đồng thời tách riêng đoạn đọc MongoDB và mapping:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderService {

    private final MongoCollection<Document> orders;

    public OrderService(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public List<Document> listRecentPaid(String customerId) {
        long requestStart = System.nanoTime();

        List<Document> loaded = new ArrayList<>();
        long mongoStart = System.nanoTime();

        try (MongoCursor<Document> cursor = orders.find(
                    Filters.and(
                        Filters.eq("customerId", customerId),
                        Filters.eq("status", "PAID")
                    )
                )
                .projection(Projections.fields(
                    Projections.include("createdAt", "totalMinor")
                ))
                .sort(Sorts.orderBy(
                    Sorts.descending("createdAt"),
                    Sorts.descending("_id")
                ))
                .limit(20)
                .iterator()) {

            while (cursor.hasNext()) {
                loaded.add(cursor.next());
            }
        }

        long mongoEnd = System.nanoTime();

        // Trong ứng dụng thật, có thể có logic mapping DTO ở đây.
        List<Document> response = loaded;

        long methodEnd = System.nanoTime();

        System.out.printf(
            "dbCursorMs=%d serviceMethodMs=%d count=%d%n",
            TimeUnit.NANOSECONDS.toMillis(
                mongoEnd - mongoStart
            ),
            TimeUnit.NANOSECONDS.toMillis(
                methodEnd - requestStart
            ),
            response.size()
        );

        return response;
    }
}
```

Đoạn này là **ví dụ minh họa instrumentation của service method**, không phải HTTP end-to-end. Nó bắt đầu sau khi các bước authentication/routing đã xảy ra và kết thúc trước khi framework serialize/send response. Nếu muốn biết toàn bộ request, cần timer ở HTTP middleware hoặc distributed trace bao cả handler và response.

Để tách thêm pool wait, command round trip và deserialize, dùng driver monitoring và các span phù hợp thay vì suy ra tất cả từ một timer bao quanh cursor.

### 16.1. Các metric khác nhau có thể lồng nhau

Ví dụ:

```text
serviceMethodMs = 85
dbCursorMs      = 62
findCommandMs   = 20
getMoreMs       = 10
```

Không cộng `85 + 62 + 20 + 10`. `dbCursorMs` nằm trong `serviceMethodMs`, còn `find`/`getMore` nằm trong đoạn cursor. Cộng các span lồng nhau sẽ **đếm trùng thời gian**.

---

## 17. Những metric nên lưu cho dashboard

Một bộ quan sát có ích theo endpoint và query shape:

| Nhóm | Chỉ số | Mục đích |
| --- | --- | --- |
| API | Request count, p50/p95/p99 latency, error rate | Biết người dùng chịu độ trễ nào. |
| Driver | Command duration theo `find`/`getMore`/`aggregate` | Biết lệnh MongoDB tốn bao lâu tại driver. |
| Cursor | Documents returned, batches, cursor consumption time | Phát hiện tải quá nhiều dữ liệu. |
| Pool | Checked-out, pending checkout, wait time, timeouts | Phát hiện nghẽn connection. |
| Server query | Keys/docs examined, plan, sort stage, duration | Phát hiện quét rộng, plan thiếu index. |
| Server resources | CPU, memory/cache, disk latency/IOPS | Phân biệt query logic và hạ tầng. |
| Database topology | Node, read preference, replication/lag liên quan | Phát hiện chênh giữa node hoặc chọn server. |
| Payload | BSON/HTTP bytes, JSON serialization duration | Phát hiện chi phí truyền/encode. |

Không cần log document đầu vào để có các metric này. Khi ghi query shape hoặc filter, nên **ẩn hoặc loại thông tin nhạy cảm**.

### 17.1. Dùng percentiles thay vì một mẫu

Nếu một endpoint có:

```text
p50 = 35 ms
p95 = 140 ms
p99 = 850 ms
```

một lần explain 10 ms có thể đại diện cho đường truy vấn nhẹ, nhưng không nói gì đủ chắc về các request đuôi dài. Cần xem sample chậm cùng ngữ cảnh: pool wait, concurrency, kết quả nhiều bất thường, I/O và node được truy vấn.

Không đánh đồng average latency với p95/p99. Có thể average thấp nhưng một nhóm người dùng vẫn trải nghiệm những request rất chậm.

### 17.2. Đo theo từng query shape và tham số

Một endpoint có thể phục vụ khách nhỏ (10 đơn) và khách lớn (hàng triệu đơn). Cùng query shape nhưng số tài liệu phù hợp khác nhau rất nhiều. Nên lấy mẫu cả hai nhóm và đo theo phân phối thật.

---

## 18. Một quy trình điều tra chênh lệch thực tế

### Bước 1 — Xác định chính xác câu hỏi đo

Ghi rõ:

- “Độ trễ ứng dụng” là server-side handler, gateway hay browser?
- Số đo là average, p95, p99 hay một request?
- Explain chạy trên node nào và lúc nào?
- Truy vấn ứng dụng có trả toàn bộ cursor không?

Không trả lời những câu này thì việc so hai số ms thường dẫn đến kết luận sai.

### Bước 2 — Lấy một request chậm có trace

Một trace tốt thể hiện từng đoạn:

```text
HTTP request
  -> auth/validation
  -> pool checkout
  -> MongoDB command(s)
  -> cursor consumption
  -> mapping
  -> external calls
  -> serialization
  -> response
```

Nếu thiếu span, bổ sung instrumentation trước khi thay đổi index. Không nên tự gán thời gian chưa đo được cho network hay database.

### Bước 3 — Truy nguyên query thật

Thu thập **query shape không chứa PII** và những tham số cần thiết:

```text
collection = orders
filter     = customerId + status
sort       = createdAt DESC, _id DESC
limit      = 20
projection = _id, createdAt, totalMinor
readPreference = primary
```

Tách biệt với những query chỉ tương tự về tên endpoint nhưng khác `skip`, range, batch size hoặc collation.

### Bước 4 — Đọc execution plan

Chạy explain một cách có kiểm soát và xem:

- `COLLSCAN` hay `IXSCAN`?
- Có `FETCH` hay có thể cover?
- Có `SORT` tốn công việc?
- Keys/docs examined so với số trả?
- Index nào được chọn? Có index phù hợp filter + sort không?
- Có nhiều phương án plan cạnh tranh không?
- Với sharded cluster, công việc phân bố giữa shard ra sao?

### Bước 5 — Đối chiếu với lệnh thật

Xem command monitoring/profiler của request thực:

- `find`/`aggregate` mất bao lâu?
- Có `getMore` không, bao nhiêu lần?
- Có pool wait hoặc server selection đáng kể không?
- Có timeout/retry không?
- Số bytes và document trả về là bao nhiêu?

Lúc này mới phân biệt được **server query bottleneck**, **driver/network bottleneck** và **application bottleneck**.

### Bước 6 — Đề xuất thay đổi theo nguyên nhân

| Nguyên nhân quan sát được | Hướng xử lý |
| --- | --- |
| COLLSCAN hoặc keys/docs examined rất lớn | Xem filter, compound index, selectivity, query rewrite. |
| Sort tốn công việc | Index đáp ứng filter + sort, giới hạn kết quả. |
| Trả quá nhiều document | Projection, limit, pagination, streaming hợp lý. |
| Nhiều getMore/network | Kiểm tra batch size, payload và nhu cầu trả dữ liệu. |
| Pool checkout chờ lâu | Phân tích concurrency, pool config, cursor giữ connection lâu. |
| Cache/I/O nóng | Xem working set, index/data size, workload đồng thời. |
| DTO/JSON nặng | Tối ưu mapping, response contract, serialization. |
| External service chậm | Tối ưu dependency và critical path bên ngoài MongoDB. |

### Bước 7 — Đo lại end-to-end

Sau thay đổi, đừng chỉ báo “explain giảm từ 400 xuống 10 ms”. Cần xác nhận:

- API p95/p99 giảm hay không.
- Throughput có cải thiện không.
- Tỷ lệ lỗi/timeouts có thay đổi không.
- MongoDB CPU, I/O, cache có ổn định không.
- Index mới làm insert/update/delete chậm hơn bao nhiêu.
- Truy vấn khác có bị ảnh hưởng không.

**Tối ưu hoàn tất khi hành vi người dùng cải thiện**, không phải khi chỉ một con số trong explain đẹp hơn.

---

## 19. Benchmark đúng cách, tránh tạo kết quả giả

### 19.1. Giữ cùng hình dạng query

Không so `findOne` với `find` rồi `toArray`, không so `limit(20)` với không giới hạn và không bỏ qua `sort` trong explain nếu API thật có sort. Giữ projection, collation, read concern và node đọc tương đương khi có thể.

### 19.2. Chạy nhiều lần, nhiều tham số

Một lần query có thể được hưởng cache nóng hoặc gặp tải ngẫu nhiên. Sử dụng phân phối input đại diện và báo p50/p95/p99, không chỉ một số nhỏ nhất.

### 19.3. Phân biệt tải tuần tự và tải đồng thời

Một query chạy tuần tự trên server rảnh khác với 500 request đồng thời tranh CPU, cache và connection. Muốn dự báo latency production phải kiểm tra ở concurrency tương ứng.

### 19.4. Đừng benchmark bằng cách logging quá nhiều

In JSON của từng document hoặc ghi log đồng bộ trong vòng lặp có thể làm client chậm hơn rất nhiều. Đo riêng các bước cần thiết, dùng instrumentation nhẹ và sampling phù hợp.

### 19.5. Không dùng clock giữa các máy như một phép trừ đơn giản

`System.nanoTime()` đo **khoảng thời gian trong một process**. Timestamp của app và database có thể có độ lệch đồng hồ. Distributed tracing cần correlation và cơ chế time handling phù hợp; không lấy timestamp trên hai máy rồi trừ trực tiếp để đo network latency nếu chưa kiểm soát clock skew.

### 19.6. Đánh giá chi phí index mới

Một compound index làm truy vấn đọc nhanh hơn có thể gây thêm write amplification. Cần đo cả dữ liệu ghi, index build, disk size và workload update, không chỉ `executionTimeMillis` của một endpoint.

---

## 20. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`executionTimeMillis` chính là thời gian HTTP request.” | Nó là thời gian được server báo cho thao tác explain, không bao phủ toàn bộ ứng dụng. |
| “Explain 5 ms, API 200 ms nghĩa là network 195 ms.” | Chưa có cơ sở; có thể do pool, getMore, serialization, business logic, khác tải hoặc khác query. |
| “Explain luôn chạy đúng cached plan của ứng dụng.” | Explain có hành vi riêng với plan cache và có thể chọn plan khác. |
| “Gọi `find()` trong Java xong là toàn bộ kết quả đã tải.” | `FindIterable` thường lazy; phải đọc cursor để đo quá trình thật. |
| “`first()` đo giống `toArray()`.” | Một document khác với tải cả tập kết quả. |
| “Một `find` command bằng toàn bộ cursor.” | Có thể phát sinh nhiều `getMore`. |
| “`limit(20)` chắc chắn chỉ đọc 20 document.” | Filter/sort/skip có thể buộc xét nhiều hơn. |
| “`nReturned = 20` nghĩa là chỉ xử lý 20 document nguồn.” | Aggregation/sort/filter có thể xử lý nhiều document để trả 20 kết quả. |
| “`executionTimeMillisEstimate` ở stage có thể cộng lại.” | Stage lồng nhau, ước lượng không phải các thời gian độc lập. |
| “`executionTimeMillis: 0` nghĩa là query không tốn gì.” | Độ phân giải báo cáo và thao tác nhanh có thể dẫn tới 0 ms. |
| “Query có IXSCAN thì chắc chắn nhanh.” | Có thể quét hàng triệu key và FETCH nhiều document. |
| “Một lần explain nhanh chứng minh p99 sẽ nhanh.” | p99 chịu ảnh hưởng cache, concurrency, dữ liệu lệch và nhiều yếu tố khác. |
| “Số liệu profiler là HTTP latency.” | Profiler quan sát thao tác server, không bao phủ app/network tới client cuối. |
| “Command duration là thuần CPU của MongoDB.” | Nó là thời gian lệnh được driver quan sát, gồm tương tác qua network trong phạm vi đo. |
| “Thời gian mọi span có thể cộng lại.” | Span có thể lồng nhau hoặc chạy song song; cộng sẽ đếm trùng. |
| “Index mới luôn cải thiện API latency.” | Nó có thể không được dùng hoặc bottleneck chính nằm ngoài query. |
| “Thêm index không có chi phí ghi.” | Insert/update/delete phải duy trì index; cần đo tác động. |

---

## 21. Bài tập tình huống

### Bài 1 — Đo sai trong Java

Đoạn code:

```java
long start = System.nanoTime();
FindIterable<Document> result =
    collection.find(Filters.eq("status", "PAID"));
long duration = System.nanoTime() - start;
```

**Câu hỏi:** Vì sao số đo rất nhỏ không chứng minh MongoDB trả hàng triệu document trong vài nano giây?

**Gợi ý:** `FindIterable` chủ yếu mô tả query; phép đo chưa tiêu thụ cursor. Hãy mở cursor và đọc kết quả đến điểm mà endpoint thật cần.

### Bài 2 — Explain nhanh, service chậm

```text
explain.executionTimeMillis = 8 ms
findCommandDuration        = 11 ms
poolCheckoutWait           = 130 ms
HTTP p95                   = 190 ms
```

**Câu hỏi:** Nên tạo compound index mới ngay hay điều tra gì?

**Gợi ý:** Thời gian chờ pool lớn. Xem connection pool, concurrency, cursor và thời gian giữ connection trước khi cho rằng index là nguyên nhân chính.

### Bài 3 — Có nhiều batch

API tải 50.000 document, driver thấy một `find` và 30 `getMore`. Explain chỉ báo 15 ms.

**Câu hỏi:** Vì sao API có thể mất hơn một giây?

**Gợi ý:** Nhiều round trip, payload và BSON/JSON mapping không tự được đại diện bởi thời gian explain; cần đo cursor drain và số bytes.

### Bài 4 — Đọc query plan trước khi giải thích latency

Một explain giả định:

```text
nReturned             = 15
totalKeysExamined     = 400000
totalDocsExamined     = 220000
executionTimeMillis   = 650
```

**Câu hỏi:** Vấn đề nào đáng điều tra trước?

**Gợi ý:** Filter/index kém chọn lọc hoặc không phù hợp; xem `IXSCAN`, `FETCH`, sort, compound index và query shape.

### Bài 5 — Cache nóng

Explain trên đúng mã khách C01 chạy 20 lần liên tục cho kết quả nhanh, trong khi p99 production cao với các khách khác nhau.

**Câu hỏi:** Tại sao không thể lấy con số nhanh nhất làm SLA?

**Gợi ý:** Tham số cố định làm nóng working set; cần thử phân phối đầu vào và concurrency gần thật.

### Bài 6 — Khác nhau về giới hạn kết quả

Explain dùng `limit(20)`, nhưng API thật dùng `skip(100000).limit(20)`.

**Câu hỏi:** Hai con số thời gian có thể so trực tiếp không?

**Gợi ý:** Không; engine có thể phải duyệt nhiều key để bỏ qua offset sâu. Xem keyset pagination và index phục vụ sort ổn định.

### Bài 7 — Tổng thời gian lồng nhau

Trace cho thấy:

```text
HTTP handler   250 ms
Mongo cursor    70 ms
find command    25 ms
getMore         20 ms
```

**Câu hỏi:** Có thể tính tổng 365 ms không?

**Gợi ý:** Không; Mongo cursor nằm trong HTTP handler, còn command nằm trong Mongo cursor. Phải xem quan hệ cha–con và critical path.

### Bài 8 — Tối ưu đọc nhưng hại ghi

Thêm compound index giúp explain từ 350 ms xuống 30 ms, nhưng throughput insert giảm 25%.

**Câu hỏi:** Index có chắc nên giữ không?

**Gợi ý:** Phải xem tần suất query, SLA, giá trị giảm độ trễ và tác động lên workload ghi. Có thể cân nhắc partial index, thay đổi query hoặc pre-aggregation.

---

## 22. Checklist tư duy khi đối chiếu số liệu

Trước khi nói “explain và ứng dụng không khớp”, hãy tự xác nhận:

1. **Cùng query không?** Filter, sort, projection, skip, limit, collation, batch size.
2. **Cùng node/điều kiện không?** Read preference, sharding, workload, cache, version.
3. **Đang so hai lần thực thi khác nhau không?** Explain không cùng đường thực thi cached query.
4. **Đã đọc hết cursor chưa?** `find`, `getMore`, thời gian iteration, số document.
5. **Ứng dụng chờ gì trước MongoDB?** Pool checkout, server selection, auth.
6. **Ứng dụng làm gì sau MongoDB?** DTO, business logic, HTTP serialization, external calls.
7. **Plan có vấn đề logic không?** Docs/keys examined lớn, `SORT`, `COLLSCAN`, index không phù hợp.
8. **Đó là một lần đo hay percentile?** p50/p95/p99 dưới tải.
9. **Có đếm trùng thời gian của span không?** Parent/child và async overlap.
10. **Đề xuất tối ưu có thực sự giúp SLA không?** Đo lại toàn bộ pipeline, cả tác động lên ghi.

## 23. Tài liệu MongoDB chính thức để tham khảo

- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): các trường trong explain, runtime stats và biểu diễn plan.
- [Explain Command](https://www.mongodb.com/docs/manual/reference/command/explain/): verbosity và hành vi explain.
- [Query Plans](https://www.mongodb.com/docs/manual/core/query-plans/): planner, lựa chọn kế hoạch và plan cache.
- [Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): index, sort, covered query.
- [Cursors](https://www.mongodb.com/docs/manual/core/cursors/): cursor và cách trả kết quả.
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): `find`, filter, sort, projection, cursor.
- [MongoDB Java Sync Driver — Monitor Application Events](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/): command monitoring và quan sát driver.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): thu thập thông tin thực thi thao tác trên server.

Khi dùng tài liệu, đối chiếu đúng phiên bản MongoDB server và driver vì output explain, execution engine, tính năng monitoring và chi tiết plan cache có thể thay đổi.

## 24. Kết luận

**`explain("executionStats")` trả lời “MongoDB đã chọn và chạy kế hoạch gì, tiêu tốn bao nhiêu công việc theo lần explain?”.** Nó không trả lời đầy đủ “người dùng phải chờ API bao lâu?”.

**Độ trễ ứng dụng** bao gồm nhiều phần: chọn/chờ connection, truyền command, thực thi server, tải nhiều batch, decode BSON, mapping, gọi service khác, serialize và gửi response. Một command MongoDB từ driver cũng chỉ là một đoạn trong đường đi này.

Cách điều tra hiệu quả là **kết hợp** execution plan và counters từ explain với command monitoring, cursor metrics, profiler/server logs và distributed tracing. Không lấy một số mili giây từ một tầng để suy đoán toàn bộ tầng còn lại; đo chính xác ranh giới, đối chiếu đúng workload và chọn tối ưu theo bottleneck thực tế.
