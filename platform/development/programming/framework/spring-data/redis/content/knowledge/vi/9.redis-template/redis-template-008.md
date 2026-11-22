# Hiểu giá trị null và kết quả trả về trong giao dịch hoặc pipeline

Khi dùng **Spring Data Redis**, một dòng code như `redisTemplate.opsForValue().get(key)` thường khá trực quan: Redis có khóa thì nhận giá trị, không có thì nhận `null`. Nhưng trong **transaction** hoặc **pipeline**, cùng phương thức đó có thể trả `null` ngay tại chỗ gọi dù lệnh hoàn toàn hợp lệ và khóa thực sự tồn tại. Kết quả thật chỉ được thu thập **sau** khi nhóm lệnh hoàn tất.

Đây là nguồn gốc của nhiều lỗi khó hiểu: `NullPointerException` khi unbox `Boolean` hoặc `Long`, logic nhánh rẽ dựa trên một kết quả chưa có, hoặc ứng dụng kết luận “cache miss” sai khi nhìn thấy `null` trong callback.

Bài này trình bày cách đọc kết quả của **`RedisTemplate` / `StringRedisTemplate`** trong ba chế độ, phân biệt `null` tạm thời với kết quả Redis thực, hiểu danh sách trả về từ `exec()` và `executePipelined()`, cùng các cách viết code rõ ràng và có thể kiểm soát.

> **Ngữ cảnh:** Ví dụ dành cho Spring Data Redis 3.x, Spring Boot 3.x và Redis thông dụng; các API chính cũng xuất hiện ở nhiều phiên bản khác. Kết quả cụ thể có thể thay đổi theo command, serializer, driver và cách Spring Data Redis chuyển đổi response. Vì vậy cần dựa vào **hợp đồng API và ngữ cảnh thực thi**, không suy luận chỉ từ một giá trị `null`.

## 1. Ba chế độ gọi lệnh: cùng API, khác thời điểm nhận kết quả

Giả sử đang thao tác với Redis server có hai khóa:

~~~redis
SET demo:profile:name "Lan"
SET demo:visits 10
~~~

Một lệnh Java thông thường:

~~~java
String name = redis.opsForValue().get("demo:profile:name");
~~~

Nếu Redis trả lời bình thường và serializer tương thích, `name` là `"Lan"`.

Nhưng khi lệnh được đưa vào transaction hoặc pipeline, câu chuyện khác đi:

| Chế độ | Điều xảy ra khi gọi method RedisTemplate | Giá trị trả ngay từ method | Nơi lấy kết quả thực |
|---|---|---|---|
| **Lệnh đơn thông thường** | Gửi lệnh, chờ response theo API đồng bộ | Kết quả, `null` hợp lệ, hoặc exception | Ngay tại lời gọi |
| **Transaction Redis `MULTI/EXEC`** | Sau `MULTI`, các lệnh tương ứng được xếp hàng để thực thi tại `EXEC` | Nhiều method trả `null` vì chưa có kết quả thực | Danh sách `exec()` khi transaction được thực thi |
| **Pipeline** | Gửi nhiều lệnh mà không chờ từng response trong callback | Nhiều method trả `null` vì response chưa được thu thập | Danh sách `executePipelined(...)` sau khi pipeline được flush/đọc kết quả |

Trong các API Spring Data Redis, nhiều method có kiểu trả về nullable ngay từ hợp đồng. Ví dụ, `ValueOperations.get(...)` có thể trả `null` khi key không tồn tại **hoặc** khi được sử dụng trong pipeline/transaction. Tương tự, các method trả `Boolean`, `Long`, tập hợp hoặc danh sách cũng có thể có `null` ở ngữ cảnh xếp hàng.

**Quy tắc đầu tiên:** Chưa biết lệnh đang ở chế độ nào thì chưa thể kết luận `null` có nghĩa “không tìm thấy dữ liệu”.

## 2. `null` trong thao tác Redis bình thường

### 2.1. `GET` với key không tồn tại

Trong Redis:

~~~redis
GET demo:missing
~~~

Kết quả ở giao thức Redis là một phản hồi **nil/null** (cách hiển thị tùy phiên bản CLI và giao thức). Với `StringRedisTemplate`:

~~~java
String value = redis.opsForValue().get("demo:missing");

if (value == null) {
    // Không có giá trị ở key được truy vấn tại thời điểm đọc.
}
~~~

Đây là cách diễn giải hợp lý **khi lệnh được chạy trực tiếp ngoài transaction/pipeline** và không có exception.

Ngay cả lúc này cũng không nên diễn giải `null` một cách quá rộng:

- Khóa có thể chưa bao giờ được ghi.
- Khóa có thể đã hết TTL hoặc bị Redis eviction.
- Ứng dụng có thể đang trỏ sai Redis instance hoặc logical database.
- Cách tạo key hoặc serializer có thể khác phía ghi.
- Một request khác có thể xóa key giữa các bước trong luồng ứng dụng.

`GET` ra `null` không nói được *vì sao* khóa không có giá trị.

### 2.2. `Boolean`, `Long` và collection cũng có trường hợp riêng

Một vài ví dụ ngoài transaction/pipeline:

~~~java
Boolean exists = redis.hasKey("demo:missing");
Boolean firstWriter = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");
Long count = redis.opsForValue().increment("demo:visits");
String missing = redis.opsForValue().get("demo:missing");
~~~

Trong điều kiện lệnh trực tiếp thành công:

- `hasKey` cho biết key có tồn tại tại thời điểm kiểm tra hay không.
- `setIfAbsent` phản ánh việc thao tác đặt giá trị có thành công theo điều kiện `NX` hay không.
- `increment` trả số đếm sau khi cập nhật.
- `get` có thể trả `null` nếu key không tồn tại.

Không nên viết:

~~~java
boolean acquired = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");
~~~

mà mặc định giá trị không bao giờ nullable. Trong một pipeline hoặc Redis transaction, `setIfAbsent` có thể trả `null`; Java sẽ cố **unbox** `Boolean` thành `boolean` và phát sinh `NullPointerException`.

Khi code được dùng cho nhiều ngữ cảnh, có thể giữ kiểu wrapper và kiểm tra tường minh:

~~~java
Boolean acquired = redis.opsForValue()
        .setIfAbsent("demo:lock", "owner-1");

if (Boolean.TRUE.equals(acquired)) {
    // Có phản hồi xác nhận thành công ở ngữ cảnh này.
}
~~~

Tuy nhiên, kiểm tra `Boolean.TRUE.equals(null)` chỉ tránh `NullPointerException`; nó **không** biến kết quả chưa có trong pipeline/transaction thành kết quả `false` thật. Logic nghiệp vụ vẫn phải lấy kết quả sau khi nhóm lệnh hoàn tất.

### 2.3. Phân biệt `null` với collection rỗng và phản hồi số

Đừng đánh đồng tất cả trạng thái “không có dữ liệu”:

| Thao tác | Tình huống | Phân biệt cần giữ |
|---|---|---|
| `GET key` | Key không tồn tại | Thường nhận `null` |
| `SMEMBERS key` | Set trống/không có phần tử | Có thể nhận collection rỗng khi thực thi bình thường |
| `EXISTS key` | Không có key | Phản hồi false/0 theo lớp API |
| `TTL key` | Không có key | Redis trả `-2` |
| `TTL key` | Key có tồn tại nhưng không TTL | Redis trả `-1` |
| Command đang xếp hàng | Chưa thu response | Một số API Spring Data Redis trả `null` tạm thời |

Cách phân biệt đúng phụ thuộc lệnh và abstraction cụ thể, không phải một luật “Redis không có gì thì tất cả đều trả `null`”.

## 3. Redis transaction: `MULTI` đưa lệnh vào hàng đợi, `EXEC` mới thực thi

### 3.1. `MULTI/EXEC` thay đổi ý nghĩa phản hồi ngay lúc gọi

Redis transaction sử dụng các lệnh `MULTI`, `EXEC`, `DISCARD` và có thể kết hợp `WATCH`. Sau `MULTI`, lệnh Redis được xếp hàng. Ở Redis CLI, người dùng thường thấy phản hồi kiểu `QUEUED` trước khi `EXEC` trả kết quả cho từng lệnh.

~~~text
Client                         Redis
  │                               │
  ├──────── MULTI ────────────────►│
  │◄──────── OK ──────────────────┤
  ├──────── GET key ──────────────►│
  │◄──────── QUEUED ──────────────┤
  ├──────── INCR count ───────────►│
  │◄──────── QUEUED ──────────────┤
  ├──────── EXEC ────────────────►│
  │◄─────── [value, newCount] ────┤
~~~

Ở Spring Data Redis, phương thức `get()` nằm sau `multi()` có thể trả `null` để phản ánh rằng chưa có giá trị dùng tại thời điểm này. Những kết quả tương ứng chỉ xuất hiện trong danh sách nhận từ `exec()`.

### 3.2. Ví dụ transaction với `SessionCallback`

`SessionCallback` giúp các thao tác trong callback sử dụng cùng một **Redis session/connection** theo cách Spring Data Redis quản lý. Đây là điều quan trọng khi gọi `MULTI`, rồi xếp hàng lệnh, cuối cùng `EXEC`.

~~~java
import java.util.List;

import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

// redis là StringRedisTemplate đã được inject từ Spring.
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();

            Object queuedGet = operations.opsForValue()
                    .get("demo:profile:name");

            Object queuedIncrement = operations.opsForValue()
                    .increment("demo:visits");

            // Trong transaction Redis, các lệnh này chưa trả dữ liệu thực.
            // queuedGet và queuedIncrement có thể là null.
            // Không lấy chúng để quyết định nhánh nghiệp vụ.

            return operations.exec();
        }
);
~~~

Sau khi callback đã kết thúc:

~~~java
if (replies == null) {
    // Cần xem lý do transaction không trả danh sách kết quả,
    // đặc biệt khi có WATCH/transaction bị hủy.
} else {
    Object readResult = replies.get(0);  // Kết quả GET
    Object countResult = replies.get(1); // Kết quả INCR
}
~~~

Ở ví dụ này có **hai lệnh cần nhận kết quả** được xếp hàng theo thứ tự `GET`, `INCR`. Vì vậy khi transaction thành công và kết quả được chuyển đổi như dự kiến, danh sách có các phần tử tương ứng theo thứ tự đó. Dạng Java cụ thể của từng phần tử chịu ảnh hưởng bởi command và cấu hình serializer/conversion.

Điểm mấu chốt:

1. `operations.multi()` bắt đầu giai đoạn xếp hàng.
2. `operations.opsForValue().get()` trong transaction có thể trả `null` **trước** `EXEC`.
3. `operations.exec()` mới gửi yêu cầu thực thi các lệnh đã xếp hàng và trả **kết quả của transaction**.
4. Kết quả được đọc từ `replies`, không phải từ biến `queuedGet` đã nhận trong callback.

### 3.3. `null` tại callback và `null` trong kết quả `EXEC` là hai thứ khác nhau

Ví dụ xếp hàng hai lệnh:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();
            operations.opsForValue().get("demo:missing");
            operations.opsForValue().increment("demo:visits");
            return operations.exec();
        }
);
~~~

Nếu `EXEC` thực thi thành công và `demo:missing` không có, **phần tử kết quả `GET` có thể là `null` thật**. Trong khi đó phần tử kết quả `INCR` là số đếm mới (khi thực thi thành công và được chuyển đổi phù hợp).

Cần phân biệt:

~~~text
Trước EXEC:
  method get(...) trả null      → response chưa sẵn sàng

Sau EXEC:
  replies[0] == null             → response thực của GET có thể là nil
  replies[1] là một số           → response thực của INCR
~~~

Chính vì một `null` có thể xuất hiện ở **hai thời điểm khác nhau**, hãy luôn nêu rõ biến nào là *giá trị trả ngay khi xếp hàng* và biến nào là *giá trị lấy từ danh sách kết quả sau thực thi*.

### 3.4. Thứ tự lệnh trong transaction

Các lệnh được thực thi theo thứ tự chúng được xếp hàng trong một transaction Redis thành công. Nếu thực hiện:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.multi();
            operations.opsForValue().set("demo:tx:flag", "on");
            operations.opsForValue().get("demo:tx:flag");
            return operations.exec();
        }
);
~~~

Kết quả `GET` sau `EXEC` có thể phản ánh giá trị vừa được `SET` trong transaction. Nhưng **ngay trong callback**, phương thức `get()` trước `exec()` không cung cấp `"on"` để nhánh Java dựa vào.

Lưu ý một method Java trả `void` như `ValueOperations.set(key, value)` vẫn tương ứng với một lệnh Redis được xếp hàng. Trong nhiều pipeline/transaction, response của lệnh đó có thể chiếm vị trí trong danh sách kết quả. Vì thế cần đếm theo **các lệnh gửi đi**, không theo số method Java có kiểu trả khác `void`.

### 3.5. `WATCH` và trường hợp transaction không được thực thi

`WATCH` cung cấp cơ chế optimistic locking: Redis theo dõi một hay nhiều khóa, rồi hủy `EXEC` nếu khóa được theo dõi bị thay đổi trước khi thực thi.

Ví dụ minh họa:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.watch("demo:stock:42");

            // Đọc trạng thái trước MULTI để tính quyết định.
            Object raw = operations.opsForValue()
                    .get("demo:stock:42");

            // Ở đây cần validate raw theo mô hình dữ liệu,
            // kiểm tra đủ stock, và quyết định có cập nhật hay không.
            // Ví dụ đơn giản chỉ minh họa vị trí của WATCH.

            operations.multi();
            operations.opsForValue().set("demo:stock:42", "9");
            return operations.exec();
        }
);
~~~

Ví dụ không phải một nghiệp vụ trừ tồn kho hoàn chỉnh. Khi triển khai thật phải kiểm tra `raw`, xử lý trường hợp stock thiếu/không hợp lệ, và retry khi có xung đột. Không hard-code `9` rồi coi đây là một thuật toán quản lý stock.

Nếu `WATCH` phát hiện xung đột, `EXEC` bị hủy và **không thực thi các lệnh đã xếp hàng**. Trường hợp này cần được phân biệt với một transaction thực thi thành công mà kết quả `GET` của một key riêng lẻ là `null`. Phản hồi abort ở mức Redis là nil; ở lớp Spring Data Redis cần kiểm tra hợp đồng phiên bản đang dùng đối với `null` hoặc hình thức danh sách kết quả rỗng, rồi xử lý như một lần **cạnh tranh cần retry hoặc báo xung đột**, không phải “không tìm thấy key”.

**Cảnh báo:** `MULTI/EXEC` không cung cấp rollback cho tất cả lỗi tại lúc thực thi theo kiểu transaction SQL. Một lệnh bị lỗi lúc `EXEC` có thể không khiến những lệnh khác tự động bị hoàn tác. Transaction Redis cũng không bao trùm một database quan hệ bên ngoài.

## 4. Pipeline: giảm round trip, thu kết quả sau khi flush

### 4.1. Pipeline không phải transaction

Pipeline cho phép gửi nhiều command Redis mà **không chờ phản hồi từng command trước khi gửi command tiếp theo**. Client có thể giảm số vòng trao đổi mạng, đặc biệt khi có nhiều lệnh nhỏ.

~~~mermaid
sequenceDiagram
    participant A as Java callback
    participant T as RedisTemplate
    participant R as Redis
    A->>T: GET key1
    T-->>A: null (chưa có response để trả)
    A->>T: INCR counter
    T-->>A: null (chưa có response để trả)
    A->>T: GET key2
    T-->>A: null (chưa có response để trả)
    T->>R: Gửi/hoàn tất pipeline
    R-->>T: Response GET, INCR, GET
    T-->>A: Danh sách kết quả sau callback
~~~

Pipeline **không mặc nhiên làm các lệnh nguyên tử**. Client khác có thể thao tác dữ liệu giữa các lệnh của pipeline tùy lịch thực thi ở server. Cũng không có transaction rollback tự động cho cả pipeline.

Hai mục tiêu khác nhau:

- **Pipeline:** tối ưu giao tiếp mạng và nhận nhiều response theo thứ tự.
- **Transaction `MULTI/EXEC`:** xếp hàng lệnh và thực thi thành một khối theo quy tắc Redis transaction, có thể kết hợp `WATCH`.

Dù cả hai đều có các method trả `null` khi đang xếp hàng, không nên xem chúng là cùng cơ chế.

### 4.2. Ví dụ `executePipelined()`

Trước hết chuẩn bị dữ liệu **ngoài pipeline** để ví dụ có trạng thái đầu vào rõ:

~~~java
redis.opsForValue().set("demo:pipeline:name", "Lan");
redis.opsForValue().set("demo:pipeline:visits", "10");
redis.delete("demo:pipeline:absent");
~~~

Sau đó:

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;

List<Object> replies = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object queuedName = operations.opsForValue()
                    .get("demo:pipeline:name");

            Object queuedCount = operations.opsForValue()
                    .increment("demo:pipeline:visits");

            Object queuedMissing = operations.opsForValue()
                    .get("demo:pipeline:absent");

            // Trong callback, các phương thức có thể trả null
            // vì response chưa được thu lại.
            // Không dùng queuedName/queuedCount/queuedMissing
            // như những kết quả hoàn chỉnh.

            return null;
        }
);
~~~

Khi `executePipelined` hoàn tất, `replies` chứa kết quả của **ba lệnh** theo thứ tự `GET`, `INCR`, `GET`.

Trong điều kiện bình thường với dữ liệu ở trên:

| Vị trí | Lệnh | Ý nghĩa kết quả thực |
|---|---|---|
| `replies.get(0)` | `GET demo:pipeline:name` | Giá trị `"Lan"` nếu serializer tương thích |
| `replies.get(1)` | `INCR demo:pipeline:visits` | Giá trị số mới, ví dụ `11` |
| `replies.get(2)` | `GET demo:pipeline:absent` | `null` thực vì key không tồn tại |

Ở đây có **ba biến `queued...` trong callback có thể cùng là `null`**, nhưng sau pipeline ta thấy hai response có nội dung và một response `nil` thật. Đó là lý do không dùng kết quả tức thời trong callback để xây dựng business logic.

### 4.3. Vì sao callback phải `return null`?

Các overload phổ biến của `RedisTemplate.executePipelined(...)` yêu cầu callback không trả một giá trị kết quả tự tạo: **kết quả được cung cấp bởi danh sách pipeline**, được Spring Data Redis thu thập sau khi callback hoàn tất.

Ví dụ cách viết **không phù hợp**:

~~~java
// Minh họa lỗi ý tưởng: không sử dụng cách này.
redis.executePipelined(
        (SessionCallback<Object>) operations ->
                operations.opsForValue().get("demo:pipeline:name")
);
~~~

Ở đây callback trả giá trị từ lời gọi `get()`, trong khi contract của `executePipelined` yêu cầu callback trả `null`. Một số trường hợp lời gọi `get()` tình cờ trả `null` khi đang xếp hàng nên nhìn như “chạy được”, nhưng không có nghĩa callback đang trả dữ liệu người dùng cần.

Viết đúng ý đồ:

~~~java
List<Object> responses = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            operations.opsForValue().get("demo:pipeline:name");
            return null;
        }
);
~~~

**Kết quả thực nằm ở `responses`**, không ở giá trị trả từ lambda. Trả một object không-null từ callback không tuân theo hợp đồng và có thể làm thao tác báo lỗi.

### 4.4. Pipeline có kết quả cho lệnh trả `void` không?

Có thể có. Ví dụ `ValueOperations.set(key, value)` là `void` ở API Java, nhưng lệnh `SET` vẫn tạo Redis response. Khi pipeline thu kết quả ở mức command, response đó có thể xuất hiện trong danh sách sau khi chuyển đổi theo driver/template.

~~~java
List<Object> responses = redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            operations.opsForValue().set("demo:mode", "ready");
            operations.opsForValue().get("demo:mode");
            return null;
        }
);
~~~

Đừng giả định `responses.get(0)` là kết quả `GET` chỉ vì `set(...)` trả `void`. Với ví dụ này, vị trí đầu phản ánh response của `SET` (hình thức Java có thể là `Boolean` hoặc dạng được chuyển đổi theo API/driver); vị trí sau phản ánh `GET`. Trước khi cast hãy xem contract command và cách lớp chuyển đổi phản hồi hoạt động.

## 5. Cùng `null`, năm nguyên nhân khác nhau

Đặt cạnh nhau các trường hợp thường gặp:

| Nơi nhìn thấy `null` | Tình huống | Diễn giải phù hợp |
|---|---|---|
| `redis.opsForValue().get(k)` ngoài pipeline/transaction | Redis trả nil | Key không có giá trị tại lần đọc đó |
| `operations.opsForValue().get(k)` sau `multi()`, trước `exec()` | Lệnh đã được xếp hàng | Chưa có response, chưa kết luận key có/không |
| `operations.opsForValue().get(k)` trong `executePipelined` | Response đang được gom | Chưa có response ngay trong callback |
| `replies.get(i)` sau `exec()` hoặc pipeline | Lệnh tương ứng đã chạy, Redis trả nil | `null` thực của response lệnh tương ứng |
| Toàn bộ kết quả `exec()` không chứa danh sách hợp lệ | Transaction bị abort, ví dụ `WATCH` xung đột | Xử lý theo trạng thái transaction, không coi là cache miss |
| Một lời gọi Java không tham gia Redis như mong đợi | Custom serializer/config/flow sai | Đọc stack trace và xác định chế độ thực thi trước khi suy luận |

**Không dùng một câu `if (result == null)` cho mọi nhánh ở bảng trên.** Phải biết null đang nằm ở tầng nào: method xếp hàng, một response cụ thể, hay outcome của toàn bộ transaction.

## 6. Phản hồi của Redis và kiểu Java trong danh sách kết quả

### 6.1. `List<Object>` cần đọc theo từng command

Cả `exec()` và `executePipelined()` đều có thể trả về danh sách mà từng phần tử không cùng kiểu. Ví dụ:

~~~text
Command sequence                    Possible Java result
----------------------------------------------------------------
GET "demo:name"                     String
INCR "demo:visits"                  Long / Number
EXISTS "demo:name"                  Boolean / numeric converted
SMEMBERS "demo:tags"                Set/List tùy API và conversion
GET "demo:missing"                  null
~~~

Đây là mô tả ý nghĩa, không phải cam kết mọi overload, phiên bản và driver luôn trả đúng một class Java. Với low-level `RedisCallback`, bạn còn có thể nhận các phản hồi thô kiểu `byte[]`; ở high-level template, serializer thường được áp dụng để biến bytes thành object phù hợp.

Khi xử lý danh sách, hãy giữ **một sơ đồ vị trí lệnh** thống nhất:

~~~java
// Ví dụ responses của pipeline gồm GET, INCR, GET.
if (replies.size() != 3) {
    throw new IllegalStateException(
            "Unexpected pipeline response count: " + replies.size()
    );
}

Object nameReply = replies.get(0);
Object countReply = replies.get(1);
Object missingReply = replies.get(2);

if (nameReply != null && !(nameReply instanceof String)) {
    throw new IllegalStateException("Unexpected GET response type");
}

if (!(countReply instanceof Number number)) {
    throw new IllegalStateException("Unexpected INCR response type");
}

String name = (String) nameReply;
long count = number.longValue();

boolean missing = missingReply == null;
~~~

Đoạn trên minh họa cách **đọc và kiểm tra kết quả sau pipeline**. Trong code thật, nên đặt kết quả vào một DTO hoặc record có tên field rõ ràng, tránh truyền `List<Object>` sâu vào nghiệp vụ.

### 6.2. Không cast cứng khi chưa rõ serializer

Với `RedisTemplate<String, SomeDto>` dùng JSON serializer, `GET` trong transaction/pipeline có thể được deserialize thành DTO khi template đã cấu hình đúng. Với `StringRedisTemplate`, key/value theo serializer chuỗi thường trả `String` cho các kết quả giá trị dạng text.

Vì vậy dạng bytes trong Redis và kiểu Java nhận được có thể phụ thuộc:

- `keySerializer`, `valueSerializer`.
- `hashKeySerializer`, `hashValueSerializer` đối với HASH.
- Có dùng `RedisCallback` cấp thấp và overload cung cấp `RedisSerializer` riêng hay không.
- Cấu hình chuyển đổi kết quả transaction/pipeline của `RedisConnectionFactory` và driver.
- Command cụ thể có trả integer, status, bulk string, collection hoặc nil không.

**Một pipeline chạy thành công nhưng cast sai có thể gây `ClassCastException`**. Lỗi này khác hoàn toàn việc Redis không thực thi command.

### 6.3. Chuyển đổi pipeline và transaction response

Spring Data Redis có cơ chế deserialize/chuyển đổi kết quả của pipeline và transaction trước khi trả về. Các phiên bản/driver có thể chuẩn hóa một số response, ví dụ status phản ánh dạng boolean và số nguyên phản ánh dạng `Long` trong API cấp cao.

Ví dụ, một `SET` ở Redis command level trả status `OK`; nhưng phía Java có thể nhìn thấy hình thức đã chuyển đổi chứ không nhất thiết là chuỗi `"OK"`. Không nên viết code production đòi `responses.get(0).equals("OK")` khi chưa kiểm chứng đúng contract trên version cụ thể.

Khi cần byte-level output, Spring Data Redis có overload `executePipelined` nhận serializer kết quả, nhưng việc chỉ định serializer không làm mọi command phản hồi cùng một loại dữ liệu. Integer, status và nested collection vẫn cần được đọc theo command tương ứng.

## 7. Lỗi nguy hiểm: rẽ nhánh theo kết quả chưa sẵn sàng

### 7.1. Kiểm tra rồi ghi trong pipeline

Đoạn mã sau có logic sai:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object available = operations.opsForValue()
                    .get("stock:42");

            if (available == null) {
                // SAI: null ở đây có thể chỉ vì GET đã xếp hàng.
                operations.opsForValue().set("stock:42", "100");
            }

            return null;
        }
);
~~~

Vì `available` có thể là `null` dù `stock:42` đang tồn tại, nhánh Java có nguy cơ ghi đè tồn kho thực tế. Ngay cả khi pipeline trả đủ kết quả ở cuối, nhánh `if` đã thực thi trước đó nên không thể quay ngược logic sai.

Nếu mục tiêu là “chỉ tạo key khi chưa tồn tại”, dùng **một lệnh nguyên tử**:

~~~java
Boolean created = redis.opsForValue().setIfAbsent(
        "stock:42",
        "100"
);
~~~

Lệnh `SET ... NX` thực hiện điều kiện kiểm tra và ghi ngay tại Redis server. Nếu cần TTL ngay từ khi tạo, dùng overload có `Duration`:

~~~java
import java.time.Duration;

Boolean created = redis.opsForValue().setIfAbsent(
        "stock:42",
        "100",
        Duration.ofMinutes(5)
);
~~~

Lưu ý `created` cần được đọc **ngoài ngữ cảnh pipeline/transaction đang xếp hàng** nếu ứng dụng muốn quyết định nhánh ngay. Trong pipeline, bản thân `setIfAbsent` vẫn có thể trả `null` tạm thời, còn phản hồi thành công/thất bại xuất hiện trong danh sách pipeline sau cùng.

### 7.2. Đọc rồi tăng bộ đếm

Đây cũng là sai lầm:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            Object current = operations.opsForValue()
                    .get("counter:42");

            // SAI: không thể dùng current để tính current + 1 tại đây.
            return null;
        }
);
~~~

Nếu chỉ cần tăng số, dùng một lệnh `INCR` nguyên tử:

~~~java
Long value = redis.opsForValue().increment("counter:42");
~~~

Trong chế độ trực tiếp, giá trị trả là số sau khi tăng; trong pipeline hoặc transaction đang xếp hàng, kết quả có thể chỉ sẵn sàng sau khi nhóm lệnh hoàn thành.

Nếu cần tính toán phức tạp dựa trên giá trị hiện tại và cập nhật **nguyên tử**, cân nhắc Lua script hoặc `WATCH` + `MULTI/EXEC` với xử lý retry. Không cố biến pipeline thành read-modify-write transaction chỉ bằng việc gọi các method kế tiếp nhau.

### 7.3. `Boolean` thành `boolean`, `Long` thành `long`

Ví dụ rủi ro unboxing:

~~~java
redis.executePipelined(
        (SessionCallback<Object>) operations -> {
            // Không an toàn: trả null tạm thời rồi bị unbox.
            // boolean exists = operations.hasKey("demo:key");
            // long total = operations.opsForValue()
            //         .increment("demo:counter");

            // Giữ kết quả ở dạng object chỉ để xếp lệnh;
            // response thật sẽ có trong danh sách trả về.
            operations.hasKey("demo:key");
            operations.opsForValue().increment("demo:counter");
            return null;
        }
);
~~~

Với high-level API, dùng kiểu wrapper và hiểu annotation nullable. Nếu cần nhánh logic ngay, thực thi lệnh ở chế độ trực tiếp hoặc chọn Redis command/script có khả năng quyết định trên server.

## 8. Khi kết quả transaction bị hủy hoặc lỗi giữa chừng

### 8.1. `WATCH` abort khác với một key bị thiếu

Giả sử transaction đã `WATCH order:42`, nhưng một client khác sửa khóa trước `EXEC`. Redis có thể hủy transaction. Trong tình huống đó, **không có danh sách kết quả lệnh được thực thi như bình thường**.

Ứng dụng cần xử lý outcome ở mức transaction:

~~~java
List<Object> replies = redis.execute(
        (SessionCallback<List<Object>>) operations -> {
            operations.watch("order:42");

            // Đọc giá trị trước MULTI, kiểm tra điều kiện nghiệp vụ.

            operations.multi();
            operations.opsForValue().set("order:42", "UPDATED");
            return operations.exec();
        }
);

if (replies == null || replies.isEmpty()) {
    // Phải phân biệt transaction abort/không có kết quả
    // với tình huống expected empty, dựa trên contract thực tế.
    // Không kết luận order:42 không tồn tại từ đây.
}
~~~

Khi triển khai logic optimistic locking, phải quy định cách xác nhận transaction đã được thực thi, cách giới hạn số lần retry và cách tránh ghi sai khi một request khác đã thay đổi dữ liệu.

### 8.2. Một phần tử là lỗi không đồng nghĩa cả transaction rollback

Redis transaction có thể thực thi một số lệnh thành công trong khi một lệnh khác báo lỗi lúc thực thi, chẳng hạn thao tác không phù hợp với kiểu dữ liệu của key. Redis không cung cấp rollback kiểu SQL cho tất cả lỗi đó.

Do vậy:

- **Lệnh được queue** không đồng nghĩa đã thực thi thành công.
- **`EXEC` có kết quả** không đồng nghĩa mọi command đều không có lỗi.
- Cần kiểm tra response/exception theo contract của lệnh quan trọng.
- Nếu cần tính nguyên tử nghiệp vụ nhiều thao tác phức tạp, phải thiết kế rõ command/script, kiểm tra điều kiện và phục hồi phù hợp.

Với pipeline, các lệnh cũng không tự rollback khi một command lỗi. Một command thất bại không làm mọi lệnh trước/sau tự động bị hoàn tác.

### 8.3. Exception là tín hiệu khác với `null`

Các lỗi như mất kết nối, timeout, authentication, lỗi serializer hay command không hợp lệ có thể được ném ra dưới dạng exception Spring Data Redis/driver. Không nên gom mọi exception thành `null`:

~~~java
try {
    String value = redis.opsForValue().get("demo:key");
    // value có thể null do key vắng mặt.
} catch (RuntimeException ex) {
    // Đây là lỗi truy cập/giải mã/thực thi khác với cache miss.
    // Xử lý theo chiến lược của ứng dụng.
    throw ex;
}
~~~

Chỉ chuyển exception thành cache miss khi kiến trúc của ứng dụng đã quyết định rõ Redis là cache tùy chọn, nguồn dữ liệu chuẩn có thể thay thế và việc fallback không gây quá tải hoặc vi phạm nghiệp vụ.

## 9. `@Transactional` của Spring và Redis transaction không mặc nhiên giống nhau

Đây là một lớp bối cảnh khác thường gây nhầm khi thấy kết quả `null`.

Một method Java gắn `@Transactional`:

~~~java
@Transactional
public void updateSomething() {
    // JDBC/JPA operations...
    // RedisTemplate operations...
}
~~~

không tự bảo đảm tất cả thao tác Redis cùng tham gia một `MULTI/EXEC`. Theo mặc định, `RedisTemplate` **không tham gia Spring-managed transaction** nếu chưa bật hỗ trợ thích hợp.

Trong Spring Data Redis có thể bật hỗ trợ transaction:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisTxConfig {

    @Bean
    StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory factory
    ) {
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
~~~

Đây là ví dụ **tùy chọn có chủ đích**, không phải cấu hình bắt buộc cho mọi hệ thống. Khi Spring có transaction active và template bật transaction support, Spring Data Redis có thể gắn Redis connection với transaction và dùng Redis `MULTI/EXEC` theo lifecycle.

Nhưng cần hiểu **hai tình huống khác nhau**:

| Tình huống | Hành vi đọc cần lưu ý |
|---|---|
| Gọi `multi()` tường minh trong `SessionCallback` | Các lệnh đã queue, kể cả `GET`, có thể trả `null` tức thời; đọc kết quả qua `exec()` |
| Spring-managed transaction với `setEnableTransactionSupport(true)` | Write command được queue để commit; Spring Data Redis có thể thực hiện **read-only commands** qua một connection không bị thread-bound vào transaction, nên không nhất thiết trả `null` như `GET` đã queue |

Ví dụ ở trường hợp thứ hai, nếu trong cùng transaction Spring vừa queue một lệnh ghi Redis rồi đọc lại key bằng read-only command trên connection khác, lần đọc đó có thể thấy **giá trị cũ**, vì ghi chưa được `EXEC` khi commit. Vì vậy cũng không được giả định mọi lệnh trong `@Transactional` có ngữ nghĩa “read-your-writes” như transaction SQL.

Ngoài ra:

- Spring-managed Redis transaction support yêu cầu transaction synchronization và transaction manager phù hợp trong ứng dụng.
- Giao dịch Redis và giao dịch JDBC/JPA **không tự tạo distributed transaction hai pha** có rollback chung.
- Nếu một hệ thống cần cập nhật database và invalidation cache, nên thiết kế thứ tự commit/evict, retry và xử lý lỗi rõ ràng.
- Việc bật transaction support chỉ để “mọi thứ an toàn hơn” có thể thay đổi kết quả return/read mà ứng dụng không mong muốn.

Trong bài học này, hai ví dụ chính `SessionCallback` và `executePipelined` giúp quan sát cách queue response rõ nhất; không nên suy diễn rằng tất cả thao tác bên trong mọi `@Transactional` đều trả `null`.

## 10. Có được lồng pipeline với transaction không?

Redis client có thể có các kịch bản pipeline chứa `MULTI/EXEC`. Tuy nhiên **kết quả trả về có cấu trúc và thời điểm chuyển đổi khác với pipeline chỉ chứa command thông thường**.

Trong Spring Data Redis:

- `executePipelined(...)` trả danh sách các phản hồi sau khi kết thúc pipeline.
- `exec()` nếu được xếp trong pipeline không nhất thiết trả kết quả ngay tại method call.
- Một response của `EXEC` có thể chứa **danh sách kết quả của các lệnh thuộc transaction**, tạo cấu trúc lồng nhau.
- Cách flatten/nested list và chuyển đổi cụ thể còn phụ thuộc API, driver, cấu hình của Spring Data Redis và phiên bản.

Vì dễ nhầm cấp danh sách, khi mới học hãy **thử pipeline độc lập và transaction độc lập trước**. Chỉ kết hợp nếu có nhu cầu đo được và đã xác định đúng hình dạng response theo phiên bản triển khai.

Đặc biệt, một pipeline không thay thế cơ chế locking, còn transaction không nhất thiết đem lại lợi ích về số round trip giống pipeline. Chọn công cụ theo mục tiêu.

## 11. Thiết kế một abstraction nhỏ để không rò rỉ `List<Object>`

Đối với code dùng nhiều lần, thay vì cho business service tự cast `responses.get(0)`, `responses.get(1)`, có thể xây dựng phương thức trả object có tên ý nghĩa rõ.

Ví dụ đọc profile và tăng bộ đếm trong cùng một pipeline (không yêu cầu atomic business):

~~~java
public record PipelineView(
        String displayName,
        long visitCount,
        boolean missingOptionalKey
) {
}
~~~

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfilePipelineService {

    private final StringRedisTemplate redis;

    public ProfilePipelineService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public PipelineView loadAndCount() {
        List<Object> replies = redis.executePipelined(
                (SessionCallback<Object>) operations -> {
                    operations.opsForValue().get("demo:profile:name");
                    operations.opsForValue().increment("demo:visits");
                    operations.opsForValue().get("demo:optional");
                    return null;
                }
        );

        if (replies.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis response count: " + replies.size()
            );
        }

        Object nameReply = replies.get(0);
        Object visitsReply = replies.get(1);
        Object optionalReply = replies.get(2);

        if (nameReply != null && !(nameReply instanceof String)) {
            throw new IllegalStateException("Invalid profile result");
        }
        if (!(visitsReply instanceof Number count)) {
            throw new IllegalStateException("Invalid visits result");
        }

        return new PipelineView(
                (String) nameReply,
                count.longValue(),
                optionalReply == null
        );
    }
}
~~~

Lớp service này đặt **mapping từ vị trí response sang ý nghĩa nghiệp vụ ở một chỗ**. Phía caller chỉ nhìn thấy `PipelineView` có field rõ ràng. Nếu pipeline được chỉnh thêm lệnh hoặc thay thứ tự, phải cập nhật mapping tương ứng.

Đoạn code giả định Redis có key counter hợp lệ hoặc chưa có counter (lúc đó `INCR` tạo số mới). Nếu key counter chứa giá trị không phải số nguyên hợp lệ, Redis sẽ báo lỗi, và ứng dụng cần xử lý thay vì giả định `visitsReply` luôn là số.

### 11.1. Khi nào dùng nhiều lệnh đơn thay vì pipeline?

Pipeline không phải lựa chọn mặc định trong mọi service:

- Nếu chỉ có một hoặc hai lệnh và latency mạng nhỏ, lợi ích có thể không đáng kể.
- Nếu lệnh thứ hai phụ thuộc kết quả của lệnh đầu, pipeline không cho Java lấy kết quả đủ sớm để rẽ nhánh.
- Nếu các lệnh cần bảo đảm nguyên tử, cần cân nhắc command đơn, Lua hoặc Redis transaction.
- Nếu lỗi của một lệnh cần dừng hoặc thay đổi lệnh sau, pipeline có thể làm control flow phức tạp hơn.
- Nếu batch quá lớn, client/server phải giữ nhiều request/response hơn; nên giới hạn batch và đo áp lực bộ nhớ, độ trễ.

Lựa chọn phải dựa vào hành vi request, nhu cầu nhất quán và kết quả đo được, thay vì chỉ số lượng câu lệnh Redis trong code.

## 12. Những tình huống dễ đọc sai kết quả

### Tình huống A: `get()` trả `null` trong callback dù key tồn tại

**Nguyên nhân có thể:** Lệnh đang được queue trong pipeline/transaction.  
**Cách giải quyết:** Lấy giá trị từ `executePipelined()` hoặc `exec()` sau khi kết thúc. Không coi biến trả ngay từ `get()` là cache miss.

### Tình huống B: `setIfAbsent()` khiến `NullPointerException`

**Nguyên nhân có thể:** Kiểu trả `Boolean` nullable đang bị unbox thành `boolean` trong pipeline/transaction.  
**Cách giải quyết:** Không dùng response tức thời để rẽ nhánh; kiểm tra response thật sau nhóm lệnh hoặc dùng command ở chế độ trực tiếp.

### Tình huống C: Kết quả pipeline bị “lệch một phần tử”

**Nguyên nhân có thể:** Có command như `SET` mà method Java trả `void`, nhưng Redis vẫn tạo response được pipeline thu thập.  
**Cách giải quyết:** Ánh xạ vị trí theo **danh sách command thực tế** và contract API. Khi cần, đặt số lượng response mong đợi và kiểm tra chặt chẽ.

### Tình huống D: `replies.get(0)` là `null` sau pipeline

**Nguyên nhân có thể:** Nếu vị trí 0 thực sự ứng với `GET` của key vắng mặt, đây là `nil` thật.  
**Cách giải quyết:** Trước tiên xác định command ứng với index 0. Sau đó mới xử lý `null` theo ngữ nghĩa command đó.

### Tình huống E: `exec()` không trả kết quả mong đợi

**Nguyên nhân có thể:** `WATCH` abort, lỗi ở command/transaction, connection/session không được quản lý đúng.  
**Cách giải quyết:** Phân biệt abort với lỗi, xem exception và transaction contract, thiết kế retry thích hợp. Không tự động xem outcome là “không có dữ liệu”.

### Tình huống F: Transaction Spring đọc thấy giá trị cũ sau khi queue write

**Nguyên nhân có thể:** RedisTemplate bật Spring transaction support: write được queue, nhưng read-only command được thực thi trên connection ngoài transaction.  
**Cách giải quyết:** Hiểu vòng đời commit và thiết kế luồng đọc/ghi tương thích. Nếu cần điều kiện cập nhật atomic trên server, dùng cơ chế Redis thích hợp thay vì giả định hành vi giống JDBC.

### Tình huống G: `ClassCastException` khi đọc `List<Object>`

**Nguyên nhân có thể:** Kết quả đã được serializer/converter đổi kiểu, hoặc code đoán sai command tại vị trí đó.  
**Cách giải quyết:** Kiểm tra contract method, serializer, thứ tự command và object runtime; đưa mapping vào adapter có kiểm tra kiểu.

## 13. Một quy trình suy luận khi gặp `null`

Khi log cho thấy một lời gọi Redis trả `null`, hãy trả lời theo thứ tự:

1. **Có đang ở trong `executePipelined`, `multi/exec` hay Spring-managed transaction không?** Nếu có, xác định lời gọi chỉ đang queue hay đã có response.
2. **`null` thuộc biến nào?** Giá trị trả ngay từ method, phần tử `List<Object>`, hay toàn bộ kết quả transaction.
3. **Command nào thực sự tạo response đó?** `GET`, `SET NX`, `INCR`, `HGET`, `EXISTS` hay `EXEC` có ngữ nghĩa khác nhau.
4. **Đã thu kết quả tại đúng thời điểm chưa?** Với pipeline là sau `executePipelined`, với transaction `MULTI/EXEC` là sau `exec()`.
5. **Đã kiểm tra outcome ở mức transaction chưa?** `WATCH` abort khác với một phần tử `nil` hợp lệ.
6. **Có thể có lỗi serializer, sai DB hoặc connection không?** Nếu lệnh đã được thực thi bình thường nhưng dữ liệu không như kỳ vọng, điều tra tiếp cấu hình và key.
7. **Business code có phụ thuộc response để quyết định lệnh tiếp theo không?** Nếu có, xem lại lựa chọn pipeline/transaction và cân nhắc một command nguyên tử, Lua, hoặc `WATCH` + retry.

Một sơ đồ nhắc nhanh:

~~~mermaid
flowchart TD
    A["Method RedisTemplate trả null"] --> B{"Đang trong callback pipeline/MULTI?"}
    B -->|Có| C["Chưa kết luận cache miss"]
    C --> D["Nhận kết quả từ executePipelined/exec"]
    D --> E{"Toàn bộ transaction abort/lỗi?"}
    E -->|Có| F["Xử lý abort/error/retry phù hợp"]
    E -->|Không| G["Ánh xạ command → vị trí response"]
    G --> H{"Response tại vị trí đó là null?"}
    H -->|Có| I["Diễn giải nil theo command cụ thể"]
    H -->|Không| J["Kiểm tra type/serializer rồi xử lý"]
    B -->|Không| K["Xác định hợp đồng API và chế độ Spring transaction"]
    K --> L["Phân biệt key miss, response hợp lệ hoặc exception"]
~~~

## 14. Ghi nhớ khi thiết kế code với RedisTemplate

- **`null` là một giá trị có ngữ cảnh.** Với `GET` trực tiếp, thường thể hiện key vắng mặt; trong callback pipeline/transaction, có thể chỉ là placeholder vì response chưa sẵn.
- **Giữ `SessionCallback` cho luồng `MULTI/EXEC`.** Những lệnh liên quan phải dùng cùng Redis session/connection do Spring Data Redis quản lý.
- **Đọc `exec()` như outcome của transaction.** Kiểm tra abort/exception, số lượng phản hồi và ngữ nghĩa từng lệnh.
- **Đọc `executePipelined()` như danh sách command response.** Callback trả `null` theo contract; kết quả thực có sau khi pipeline hoàn thành.
- **Không rẽ nhánh dựa vào response tạm thời.** Nếu lệnh sau phụ thuộc giá trị lệnh trước, chọn một phương án phù hợp với control flow, thường là command nguyên tử, Lua hoặc optimistic locking.
- **Tránh auto-unboxing kiểu nullable.** `Boolean` và `Long` trong các API Redis có thể trả `null` ở chế độ queue.
- **Đừng bỏ qua conversion và serializer.** Danh sách kết quả có thể chứa nhiều loại object; kiểm tra type và đóng gói về DTO có ý nghĩa.
- **Phân biệt Redis transaction với `@Transactional` của Spring.** RedisTemplate không tự tham gia transaction Spring, và khi bật transaction support, hành vi read-only command cũng cần được hiểu riêng.

Khi hiểu chính xác **lệnh được gửi lúc nào, phản hồi được thu lúc nào và `null` đang ở cấp độ nào**, bạn có thể viết `RedisTemplate` code rõ ràng, tránh lỗi cache miss giả, mất nhánh logic và nhầm kết quả transaction/pipeline.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis API — RedisOperations](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisOperations.html)
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/)
