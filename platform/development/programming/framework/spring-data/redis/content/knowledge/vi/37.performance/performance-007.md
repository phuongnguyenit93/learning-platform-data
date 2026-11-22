# Đánh đổi kích thước nhóm lệnh với bộ nhớ và thời gian đáp ứng

Trong **Spring Data Redis**, tối ưu hiệu năng thường bắt đầu bằng câu hỏi: *“Có nên gom nhiều thao tác Redis vào một lượt để giảm số lần trao đổi mạng?”* Câu trả lời thường là **có, nhưng không phải càng nhiều càng tốt**.

Nếu gửi 1.000 lệnh `GET` lần lượt, client có thể phải đợi quá nhiều vòng trao đổi mạng. Nếu gom 1.000 lệnh vào một pipeline, lượng chờ theo từng lệnh có thể giảm rõ rệt. Nhưng cùng lúc, Redis và ứng dụng phải giữ nhiều command và response hơn trong bộ đệm; batch có thể chiếm kết nối lâu; lỗi khó cô lập; một request xuất hiện sớm phải chờ các request còn lại được gom; và độ trễ ở phần đuôi phân phối (*tail latency*, p95/p99) có thể xấu đi.

Điều cần tối ưu không phải **một con số batch size lớn nhất**, mà là **điểm cân bằng giữa throughput, bộ nhớ, thời gian chờ, giới hạn đồng thời và khả năng phục hồi**.

Bài học hướng dẫn cách quyết định kích thước nhóm cho pipelining, `MGET`/`MSET`, xử lý theo lô, `SCAN`, Redis Streams và Lua trong ứng dụng Spring Data Redis; đưa ra ví dụ Java, mô hình định lượng, cách benchmark và các sai lầm cần tránh.

## 1. “Nhóm lệnh” có nhiều nghĩa khác nhau

Cùng chữ *batch* có thể mô tả những cơ chế Redis có ngữ nghĩa rất khác nhau.

| Cơ chế | Nhóm gồm những gì? | Mục tiêu chính | Có nguyên tử cho cả nhóm? |
|---|---|---|---|
| Nhiều lệnh Java tuần tự | N lần gọi `GET`/`SET` | Dễ viết, dễ tách lỗi | Không |
| **Pipelining** | N command gửi không chờ từng response | Giảm round-trip | **Không** |
| **Multi-key command** | `MGET`, `MSET` và các lệnh nhận nhiều key | Giảm số command/round-trip | Tùy command và giới hạn Cluster |
| **`MULTI`/`EXEC`** | N command queue vào transaction | Không cho lệnh từ client khác xen trong khi EXEC chạy | Theo semantics của Redis transaction; không rollback runtime error |
| **Lua script** | N thao tác Redis được gọi trong một script | Kiểm tra/cập nhật nguyên tử và giảm mạng | Script thực thi nguyên tử, **không tự rollback** nếu runtime error |
| **`SCAN COUNT`** | Gợi ý số phần tử mỗi vòng duyệt | Kiểm soát lượng dữ liệu mỗi lần quét | Không; không phải snapshot |
| **Redis Streams `COUNT`** | Số message yêu cầu trong một lượt đọc | Cân bằng throughput và thời gian xử lý | Không bảo đảm cả batch xử lý thành công |
| **Batch từ ứng dụng** | N request/item được gom trước khi gửi | Giảm I/O/scheduling overhead | Phụ thuộc lệnh và giao thức sử dụng |

Ví dụ: “batchSize = 100” trong một `StreamMessageListenerContainer` không tương đương “pipeline 100 SET” và cũng không tương đương một Lua script xử lý 100 key. Mỗi trường hợp có các giới hạn riêng về bộ nhớ, độ trễ và phục hồi.

**Nguyên tắc:** trước khi điều chỉnh batch size, hãy viết rõ **đơn vị của batch là gì**, khi nào batch được flush, dữ liệu trả về lớn bao nhiêu và ngữ nghĩa khi một phần thất bại.

## 2. Ba mục tiêu cạnh tranh nhau

Một tối ưu nhóm lệnh thường đồng thời ảnh hưởng:

1. **Throughput:** số thao tác hoặc số bản ghi xử lý được mỗi giây.
2. **Latency:** thời gian từ lúc một yêu cầu đến cho tới lúc nhận kết quả; cần phân biệt trung bình với p95/p99.
3. **Memory:** bộ đệm command, response, Java object, serializer, connection buffers và dữ liệu Redis đang lưu.

Có thêm ba ràng buộc không nên bỏ qua:

- **Correctness:** kết quả cuối cùng đúng không; có mất/trùng/đảo thứ tự thao tác không?
- **Fairness:** một batch dài có chặn các yêu cầu ưu tiên thấp/khác không?
- **Recoverability:** nếu timeout hoặc client chết giữa batch, biết phần nào đã chạy để retry an toàn không?

Ví dụ:

```text
Batch nhỏ:
  + Flush nhanh, mỗi request ít chờ trong hàng gom.
  + Dễ cô lập lỗi, ít dữ liệu giữ trong bộ nhớ mỗi lượt.
  - Nhiều round-trip và nhiều lần flush.
  - Có thể kém throughput khi mạng có RTT đáng kể.

Batch lớn:
  + Amortize round-trip, giảm số lần flush, có thể tăng throughput.
  - Giữ nhiều request/replies, dễ tăng memory peak.
  - Có thể tăng thời gian chờ gom nhóm và p99.
  - Nếu downstream chậm, một nhóm lớn giữ kết nối lâu.
  - Lỗi giữa nhóm dễ gây kết quả không rõ ràng hoặc cần xử lý lại.
```

Không có batch size mặc định tối ưu cho tất cả mạng, loại command và kích thước value.

## 3. Vì sao batching có thể giảm round-trip?

Giả sử kết nối Redis có round-trip time (*RTT*) ước lượng là `R` và mỗi command cần thời gian xử lý máy chủ trung bình `C`. Nếu gọi từng command đồng bộ:

\[
T_{\text{sequential}}(N) \approx N(R+C)
\]

Nếu pipeline N command và trả replies theo một đợt, mô hình tối giản:

\[
T_{\text{pipeline}}(N) \approx R + NC + T_{\text{transfer}} + T_{\text{client}}
\]

Như vậy **chi phí RTT được chia cho số command trong mỗi flush**. Nhưng các thành phần transfer, serialization, queueing và Redis server load vẫn tồn tại.

Trong mô hình lý tưởng, chi phí trung bình mỗi operation của batch B có thể viết:

\[
t_{\text{avg}}(B) \approx \frac{R}{B} + C + D(B)
\]

Trong đó `D(B)` gom thêm chi phí chuyển dữ liệu, decode, queueing, flush và contention.

Đây là **mô hình giải thích**, không phải công thức dự báo chính xác latency ứng dụng. Nó có ích để hiểu xu hướng: khi B tăng, `R/B` giảm dần, nhưng `D(B)` có thể tăng.

### Một phép tính chỉ để minh họa

Giả sử `R = 0,8 ms` và `C = 0,06 ms` mỗi command, bỏ qua chi phí khác:

| Kích thước batch B | `R/B + C` ước lượng/command |
|---:|---:|
| 1 | 0,860 ms |
| 10 | 0,140 ms |
| 50 | 0,076 ms |
| 200 | 0,064 ms |
| 1.000 | 0,0608 ms |

Lợi ích lớn nhất có thể xuất hiện từ B = 1 lên B = 10 hoặc 50. Khi tăng từ 200 lên 1.000, phần tiết kiệm RTT/command trong mô hình đã rất nhỏ. Trong thực tế, batch cực lớn có thể khiến memory và tail latency trở nên xấu hơn mức tiết kiệm đó.

**Không dùng số liệu trong bảng như benchmark Redis thật.** Redis, serializer, mạng và command mix của từng hệ thống có kết quả khác nhau.

## 4. Thời gian chờ gom batch cũng là latency

Có hai hình thức batching:

- **Batch có sẵn:** service đã có 500 ID từ một request duy nhất rồi gom để đọc. Không cần chờ thêm request khác tới.
- **Micro-batching liên request:** một bộ gom chờ đủ 500 công việc từ nhiều request hoặc chờ tối đa một khoảng thời gian trước khi flush.

Trường hợp thứ hai có thêm **batch formation delay**.

Giả sử request đến đều đặn 1.000 operations/giây, bộ gom chỉ flush khi đủ B và không có thời hạn chờ tối đa. Với mô hình arrival gần đều, thời gian chờ trung bình để lấp một batch xấp xỉ:

\[
W_{\text{formation}} \approx \frac{B-1}{2\lambda}
\]

với `λ` là số operation đến mỗi giây.

| B | Chờ trung bình để lấp batch ở 1.000 op/s |
|---:|---:|
| 1 | 0 ms |
| 10 | 4,5 ms |
| 50 | 24,5 ms |
| 200 | 99,5 ms |
| 1.000 | 499,5 ms |

Đây là mô hình lý tưởng để làm rõ rủi ro, **không phải công thức thay thế dữ liệu đo thực tế**. Traffic có tính burst, sự thay đổi rate, nhiều workers và flush timeout sẽ làm phân phối chờ khác đi.

Một hệ thống HTTP yêu cầu p99 thấp hơn 100 ms không thể chỉ dựa vào batch “đủ 1.000 items mới gửi” khi lưu lượng không cao và ổn định. Trong nhiều trường hợp, phải thiết kế cả **giới hạn số item B, giới hạn byte S và thời gian chờ tối đa W**.

## 5. Bộ nhớ tăng theo cả kích thước lệnh lẫn kết quả

Khi pipeline đang hoạt động, dữ liệu có thể nằm đồng thời ở nhiều nơi:

```text
Ứng dụng Java:
    request objects / input collections
    serialized keys/values
    command queue / futures
    reply buffers
    deserialized List<Object> / DTOs

Mạng / Redis client:
    outbound command bytes
    inbound response bytes
    connection buffers

Redis server:
    client input/output buffers
    command/reply bookkeeping
    chính dữ liệu trong keyspace
```

Vì vậy không chỉ tính kích thước key/value trong Redis. Một `MGET` đọc 5.000 values có thể buộc JVM giữ cả danh sách kết quả và bản sao các object deserialize ngay cả khi Redis memory vẫn còn rộng.

Một ước lượng thô cho **payload đang đồng thời xử lý**:

\[
M_{\text{payload}} \approx B \times (S_{\text{request}} + S_{\text{reply}}) \times F
\]

Trong đó:

- `B`: số command/item của một batch;
- `S_request`: bytes request trung bình/item;
- `S_reply`: bytes reply trung bình/item;
- `F`: số batch cùng đang in-flight.

Ví dụ chỉ để minh họa:

```text
B = 2.000
request payload mỗi item ≈ 2 KiB
response payload mỗi item ≈ 4 KiB
F = 4 batches đang in-flight

Tổng byte payload gần:
  2.000 × (2 + 4) KiB × 4
  = 48.000 KiB
  ≈ 46,9 MiB
```

Con số 46,9 MiB **chưa tính** Java object headers, collection overhead, serializer intermediate buffers, protocol headers, socket buffers, heap fragmentation và bản sao dữ liệu. Memory peak thật có thể lớn hơn đáng kể.

Đặc biệt nếu mỗi Spring request tạo một pipeline riêng và server đồng thời xử lý hàng trăm requests, **batch size vừa phải của từng request vẫn có thể tạo aggregate memory rất lớn**.

## 6. Tổng lượng dữ liệu quan trọng hơn mỗi số lệnh

Hai batch cùng chứa 200 commands có thể khác nhau hoàn toàn:

```text
Batch A:
  200 lệnh GET, mỗi reply 16 bytes
  -> khoảng 3,2 KiB payload reply (chưa tính giao thức)

Batch B:
  200 lệnh GET, mỗi reply 2 MiB
  -> khoảng 400 MiB payload reply
```

Nếu chỉ cấu hình `maxBatchCommands = 200`, batch B có thể vượt ngân sách bộ nhớ/network.

Nên xét cùng lúc:

- **Max commands/items per batch.**
- **Max serialized bytes per batch**, tách bytes request và ước lượng reply.
- **Max wait time** để không làm latency tăng quá mức khi traffic thấp.
- **Max in-flight batches** để không tạo hàng đợi vô hạn.
- **Kích thước result buffer** hoặc cách tiêu thụ kết quả theo từng chunk.
- **Max processing time** cho một batch nếu các command tốn CPU/server time.

Với lệnh đọc giá trị kích thước rất khác nhau, có thể cần histogram value sizes và ngưỡng byte; không thể suy ra response size từ số keys một cách chính xác.

## 7. Kích thước batch và độ trễ đuôi p95/p99

Lợi ích throughput thường được báo bằng operations/second. Nhưng request người dùng chịu **latency end-to-end**:

```text
T_request
  = thời gian đợi vào batch
  + thời gian đợi slot in-flight
  + thời gian serialize
  + thời gian gửi mạng / Redis xử lý
  + thời gian nhận và deserialize replies
  + thời gian map kết quả / xử lý nghiệp vụ
```

Khi batch lớn:

1. Request đầu tiên có thể phải chờ thêm nhiều request đến.
2. Một item lớn có thể làm cả nhóm chậm.
3. Một connection đang xử lý batch dài có thể làm các nhóm khác chờ.
4. Garbage collection tăng nếu tạo nhiều `List<Object>`/DTO lớn cùng lúc.
5. Retry một batch lớn sau timeout có thể gây đột biến tải hoặc side effects lặp.
6. P99 có thể tăng ngay cả khi average throughput cải thiện.

**Chỉ số phải đo:** thời gian từ lúc user/request sinh operation đến lúc nhận kết quả, **không chỉ thời gian của `executePipelined`**. Nếu chỉ đo từ lúc batch đã được flush, bạn bỏ qua thời gian chờ gom batch — phần có thể chi phối p99.

## 8. Định nghĩa đúng batch size theo Spring Data Redis API

Trong `StringRedisTemplate` hoặc `RedisTemplate`, các kiểu gom thường gặp:

| API | Đơn vị nhóm | Đặc điểm |
|---|---|---|
| `opsForValue().multiGet(keys)` | Số keys mỗi lệnh đọc nhiều key | Một API nhiều-key, trả tập kết quả |
| `opsForValue().multiSet(values)` | Số cặp key/value | Một API nhiều-key |
| `executePipelined(callback)` | Số commands được callback gửi | Nhiều Redis commands, replies gom thành List |
| `execute(SessionCallback)` với `multi/exec` | Số commands trong transaction | Điều khiển transaction theo connection |
| `scan(ScanOptions.count(n))` | Gợi ý COUNT cho mỗi lần SCAN | Không phải số phần tử cố định |
| `opsForStream().read(options.count(n), ...)` | Số records yêu cầu/lần đọc | Không phải ngưỡng pending/ACK |
| `StreamMessageListenerContainerOptions.batchSize(n)` | Số records mỗi lần poll | Listener vẫn cần xử lý và ACK riêng |
| `execute(RedisScript<T>, keys, args...)` | Số keys và logic một script | Server-side work, không phải pipeline |
| Reactive `bufferTimeout(B,W)` | Số publisher items gom trước khi phát batch | Không tự đảm bảo atomicity Redis |

Một số API thay đổi overload hoặc chi tiết theo Spring Data Redis version. Điều quan trọng là **hiểu command thực tế mà API tạo** và không áp đặt quy tắc của pipeline cho Streams hay Lua.

## 9. Đọc nhiều key bằng MGET: thuận tiện nhưng có giới hạn

Nếu một request cần 100 product names độc lập, có thể thay 100 lần `GET` bằng một `MGET` ở Redis standalone:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductNameLookup {
    private final StringRedisTemplate redis;

    public ProductNameLookup(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> findNames(List<String> keys) {
        if (keys.isEmpty()) {
            return List.of();
        }
        return redis.opsForValue().multiGet(keys);
    }
}
```

Một số lưu ý:

- Kết quả được trả về **theo thứ tự key đầu vào** theo hợp đồng của `MGET`.
- Key không tồn tại có thể tương ứng với phần tử `null` trong kết quả; kiểm tra contract của API và xử lý miss.
- `multiGet` có thể phải materialize toàn bộ replies trong memory.
- `MGET` không biến một loạt GET thành snapshot transaction xuyên nhiều writer ngoài command semantics trên Redis server.
- Trong **Redis Cluster**, lệnh nhiều-key có giới hạn hash slot; driver/API có thể có cơ chế chia lệnh theo node/slot trong một số trường hợp, nhưng **không được giả định một lệnh MGET đa slot luôn nguyên tử hoặc luôn được hỗ trợ**. Test trên topology đang dùng.

Đọc 50.000 keys bằng một `multiGet` có thể gây memory peak và latency rất cao. Nếu đầu vào lớn, chia thành các nhóm nhỏ hơn và giải phóng results từng nhóm.

## 10. Chia MGET thành từng chunk có giới hạn

Mẫu thao tác đọc theo từng phần:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ChunkedMultiGet {

    private final StringRedisTemplate redis;

    public ChunkedMultiGet(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> getInChunks(
            List<String> keys,
            int maxKeysPerBatch) {

        if (maxKeysPerBatch <= 0) {
            throw new IllegalArgumentException(
                    "maxKeysPerBatch must be positive");
        }

        List<String> output = new ArrayList<>(keys.size());

        for (int offset = 0; offset < keys.size();
                offset += maxKeysPerBatch) {

            int end = Math.min(keys.size(),
                    offset + maxKeysPerBatch);

            List<String> chunk = keys.subList(offset, end);
            List<String> values =
                    redis.opsForValue().multiGet(chunk);

            if (values == null) {
                throw new IllegalStateException(
                        "MGET returned null batch result");
            }

            output.addAll(values);
        }

        return output;
    }
}
```

Đây là một phiên bản **chỉ giới hạn số keys mỗi Redis call**, nhưng vẫn tích lũy toàn bộ `output` trong JVM. Nếu mục tiêu là hạn chế memory peak, cách tốt hơn có thể là **tiêu thụ từng chunk và giải phóng nó ngay**, thay vì trả về một List chứa tất cả dữ liệu.

### Xử lý từng chunk mà không giữ mọi reply

```java
public void processInChunks(
        List<String> keys,
        int batchSize,
        java.util.function.BiConsumer<String, String> consumer) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize");
    }

    for (int i = 0; i < keys.size(); i += batchSize) {
        int end = Math.min(keys.size(), i + batchSize);
        List<String> slice = keys.subList(i, end);

        List<String> values = redis.opsForValue().multiGet(slice);

        if (values == null || values.size() != slice.size()) {
            throw new IllegalStateException("Unexpected MGET result");
        }

        for (int j = 0; j < slice.size(); j++) {
            consumer.accept(slice.get(j), values.get(j));
        }
    }
}
```

Cần quyết định liệu `consumer` được phép giữ các value lại ở nơi khác hay không, vì nếu nó tự lưu tất cả vào List/cache khác thì memory vẫn tăng.

Khi đầu vào rất lớn hoặc được stream từ database, nên **không materialize cả danh sách keys**; thay vào đó lấy keys theo trang, gửi và tiêu thụ một chunk rồi chuyển sang trang tiếp theo.

## 11. Pipelining trong Spring Data Redis

Spring Data Redis hỗ trợ `executePipelined`. Ví dụ cần 100 independent GET nhưng không muốn phụ thuộc vào multi-key semantics:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class PipelinedReader {

    private final StringRedisTemplate redis;

    public PipelinedReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> getAll(List<String> keys) {
        if (keys.isEmpty()) {
            return List.of();
        }

        return redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        for (String key : keys) {
                            ops.opsForValue().get(key);
                        }

                        // Callback phải trả null. Replies được lấy sau.
                        return null;
                    }
                });
    }
}
```

Trong pipeline:

- Các lời gọi `get` trong callback **không trả ngay giá trị String** như một GET đồng bộ bình thường.
- `executePipelined` thu replies vào `List<Object>` khi pipeline được thực thi/đọc xong.
- Nên kiểm tra số lượng và thứ tự replies theo command đã gửi.
- Serialization và result deserialization có thể tạo nhiều object trên heap.
- Command lỗi trong pipeline không rollback các command đã thành công trước đó.
- Redis Cluster có routing/pipelining behavior tùy driver; cần test với topology thực tế.

### Lưu ý về độ lớn của reply list

`executePipelined` trả về **toàn bộ danh sách replies cho pipeline đã gửi**. Nếu gửi 50.000 GET cho value lớn, JVM có thể giữ list kết quả cùng lúc.

Muốn khống chế memory peak, thay vì một pipeline 50.000 lệnh, hãy chia thành các pipeline vừa phải và **tiêu thụ/kết thúc từng pipeline** trước khi gửi thêm. Không dùng một callback khổng lồ rồi hy vọng driver tự chuyển replies thành một stream từng phần cho Java.

## 12. Pipeline theo chunk thay vì một batch không giới hạn

```java
import java.util.List;
import java.util.function.BiConsumer;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public void processWithPipelines(
        List<String> keys,
        int batchSize,
        BiConsumer<String, Object> consumer) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize");
    }

    for (int i = 0; i < keys.size(); i += batchSize) {
        int end = Math.min(keys.size(), i + batchSize);
        List<String> chunk = keys.subList(i, end);

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        for (String key : chunk) {
                            ops.opsForValue().get(key);
                        }
                        return null;
                    }
                });

        if (replies.size() != chunk.size()) {
            throw new IllegalStateException(
                    "Pipeline reply count mismatch");
        }

        for (int j = 0; j < chunk.size(); j++) {
            consumer.accept(chunk.get(j), replies.get(j));
        }
    }
}
```

Ví dụ giả định các replies ứng với những lệnh GET đúng thứ tự; với transaction, script hoặc lỗi có reply phức tạp, contract phải được xác định riêng.

Chia chunk giúp giới hạn số replies nằm trong memory ở mỗi lượt. Tuy nhiên:

- `List<String> keys` đầu vào vẫn nằm trong memory.
- `consumer` có thể xử lý chậm, kéo dài request end-to-end.
- Nếu chunk thứ ba lỗi, hai chunk đầu có thể đã chạy.
- Có thể cần ghi tiến độ (offset, last processed ID) để retry theo cách phù hợp.
- Không nên mở hàng trăm pipelines đồng thời chỉ vì mỗi chunk đã nhỏ.

**Giới hạn batch size và giới hạn in-flight là hai núm điều chỉnh khác nhau.** Nếu mỗi batch 200 lệnh nhưng 1.000 batch chạy đồng thời, số lệnh đang chờ phản hồi vẫn có thể rất lớn.

## 13. MGET và pipeline: nên chọn cách nào?

| Tiêu chí | `MGET` | Pipeline của nhiều `GET` |
|---|---|---|
| Lệnh Redis về mặt logic | Một multi-key read | N independent GET commands |
| Số round-trip | Thường ít, nếu command hợp lệ | Giảm chờ từng GET qua pipelining |
| Kết quả | Một cấu trúc list trả values | Một reply cho từng command, tập hợp ở client |
| Xử lý lỗi | Lỗi ở cấp command multi-key | Có thể lỗi từng GET/route |
| Redis Cluster | Multi-key slot constraints, driver behavior cần test | Từng GET có thể route tới các node phù hợp |
| Atomic snapshot | Theo single-command semantics trong phạm vi server hợp lệ | Không có snapshot/atomicity cho cả pipeline |
| Mức chiếm memory | Một danh sách values lớn | Reply list và command buffers có thể lớn |
| Thích hợp khi | Nhiều key cùng phạm vi hợp lệ, chỉ cần values | Command mix đa dạng hoặc key/route độc lập |

Không thể kết luận `MGET` luôn nhanh hơn pipeline hoặc ngược lại chỉ từ số command. Hãy đo với **Redis topology, key placement và kích thước value thực tế**.

Nếu đọc các key từ nhiều Redis Cluster slots, đôi khi việc **nhóm theo hash slot** hoặc gửi independent GET qua client cluster-aware có thể phù hợp hơn. Nhưng nhóm theo slot làm phức tạp thứ tự kết quả; cần map reply về key/ID đầu vào, không giả định danh sách trả về được ghép đúng thứ tự nếu đã sắp xếp lại.

## 14. Ghi nhiều key: batch size và rủi ro partial success

Giả sử cần cập nhật 10.000 cache entries. Nếu chia thành 100 batches, mỗi batch 100 `SET`, có thể nhận được lợi ích pipeline.

Nhưng giả sử batch thứ 60 timeout:

```text
Batches 1..59: đã nhận success replies
Batch 60: mất phản hồi/không rõ bao nhiêu command đã chạy
Batches 61..100: chưa gửi
```

Không thể giả định “mọi cache entries đều giữ trạng thái cũ” hoặc “batch 60 chắc chắn chưa có SET nào”. Retry phải xét tính chất của từng command:

- `SET key value` cùng value thường có trạng thái cuối idempotent, nhưng TTL có thể bị reset hoặc dữ liệu có thể bị writer khác thay đổi.
- `INCR`/`DECR` có side effect tích lũy; retry có thể làm tăng/giảm hai lần.
- `LPUSH`/`XADD` có thể tạo phần tử/event trùng khi retry.
- `DEL` thường idempotent về trạng thái cuối, nhưng reply số key bị xóa sẽ thay đổi.
- Lua có side effect không tự trở thành idempotent chỉ vì nó nguyên tử.

Nếu ghi cache dựa trên database source, có thể dùng **version field** hoặc invalidation/reconciliation để chống stale overwrite. Nếu đang ghi event nghiệp vụ, cần operation ID/outbox hoặc một cơ chế đảm bảo không mất/trùng phù hợp.

## 15. Pipeline không phải MULTI/EXEC

Cần phân biệt hai kiểu gom:

```text
Pipeline:
  SET A
  SET B
  SET C
  -> gửi nhiều command để tiết kiệm round-trip
  -> các command độc lập về atomicity

Transaction:
  MULTI
  SET A
  SET B
  SET C
  EXEC
  -> commands trong EXEC chạy mà không có command client khác xen giữa
```

Spring Data Redis sử dụng:

- `executePipelined(...)` khi cần pipelining.
- `SessionCallback` + `multi()`/`exec()` khi cần Redis transaction.
- `RedisScript`/`DefaultRedisScript` khi cần logic server-side.

Không dùng `executePipelined` và đặt tên method `atomicBatchUpdate` nếu không có cơ chế atomicity thực sự. Ngay cả `MULTI/EXEC` cũng **không rollback mọi lỗi runtime** như SQL.

### Batch lớn bên trong transaction có mặt trái

Một `EXEC` chứa hàng chục nghìn command có thể giữ Redis bận lâu trong một lần thực thi nhóm, làm các client khác tăng latency. Giao dịch lớn cũng có chi phí queueing và bộ nhớ trước khi thực thi.

Nếu nghiệp vụ thực sự cần atomicity cho 50.000 cập nhật, phải đánh giá lại mô hình dữ liệu và phạm vi bất biến: việc đưa toàn bộ vào một transaction/script lớn trên Redis có thể gây trở ngại cho SLA phục vụ các request khác.

## 16. Không nhầm batchSize với flush policy của Lettuce

Với Lettuce, có thể có cấu hình điều khiển **khi các commands đang pipeline được flush xuống socket**. Các client options và API chi tiết khác nhau theo version; một số phiên bản Spring Data Redis/Lettuce cung cấp cách chọn flush policy thay vì flush từng command.

Cần phân biệt:

- Số command bạn đặt trong callback `executePipelined`.
- Số command client gom trước khi flush xuống connection.
- Số byte có thể ghi vào socket mỗi lượt.
- Số replies client giữ trước khi chuyển thành Java objects.
- Số batches ứng dụng chạy đồng thời.

Ví dụ, application chia thành chunks 200 commands nhưng driver flush theo chính sách riêng; tổng network behavior không thể suy chỉ từ số 200.

Khi tinh chỉnh Lettuce options:

1. Kiểm tra driver version và API được hỗ trợ.
2. Đo thực tế số command/flush và latency thay vì đoán.
3. Theo dõi memory của outbound queue khi flush bị trì hoãn.
4. Bảo đảm error/connection shutdown không để commands bị bỏ quên.
5. Không dùng flush policy như một cách thay thế limit in-flight hoặc bảo đảm transaction.

## 17. HGETALL và các lệnh trả kết quả lớn cũng là “batch”

Một command đơn vẫn có thể trả một lượng dữ liệu khổng lồ. Ví dụ:

```text
HGETALL profile:huge
SMEMBERS wishlist:huge
ZRANGE ranking:global 0 -1
LRANGE tasks:all 0 -1
XRANGE events:all - +
```

Mỗi command có thể yêu cầu Redis dựng một response lớn và client deserialize mọi phần tử. Vì vậy “chỉ có một command, chắc chắn memory nhỏ” là một kết luận sai.

Các lựa chọn thay thế:

| Truy vấn lớn | Cách giảm peak có thể xem xét |
|---|---|
| `HGETALL` của Hash lớn | `HMGET` các field mục tiêu hoặc `HSCAN` có cursor |
| `SMEMBERS` của Set lớn | `SSCAN` để xử lý từng nhóm |
| `ZRANGE 0 -1` trên ZSet khổng lồ | Range có giới hạn, chia theo score/rank |
| `LRANGE 0 -1` trên List rất dài | Các range nhỏ hoặc thiết kế queue thích hợp |
| `XRANGE - +` toàn stream | `XRANGE ... COUNT n` với offset |
| `MGET` hàng chục nghìn values | Chia keys thành batches có giới hạn |
| Pipeline đọc toàn keyspace | Chia pipeline và tiêu thụ từng reply chunk |

**Mục tiêu là bound dữ liệu trả về**, không chỉ bound số commands.

## 18. SCAN COUNT là gợi ý, không phải page size cố định

Redis `SCAN` có cursor và tham số `COUNT`:

```bash
redis-cli SCAN 0 MATCH 'cache:product:*' COUNT 100
```

Trong Spring Data Redis:

```java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;

ScanOptions options =
        ScanOptions.scanOptions()
                .match("cache:product:*")
                .count(100)
                .build();

try (Cursor<String> cursor = redis.scan(options)) {
    while (cursor.hasNext()) {
        String key = cursor.next();
        // Xử lý từng key; đừng giữ mọi key trong List khổng lồ.
    }
}
```

**`COUNT 100` chỉ là một hint cho lượng công việc mỗi lượt scan**, Redis có thể trả ít hơn hoặc nhiều hơn con số đó. Cursor `0` là tín hiệu kết thúc toàn bộ scan, **không phải** việc một lượt trả về 0 phần tử.

Các đặc điểm cần nhớ:

- `SCAN` có thể trả key trùng khi keyspace đang thay đổi.
- Không có snapshot nhất quán trên toàn bộ Redis.
- Tăng COUNT có thể giảm số lượt scan nhưng tăng thời gian xử lý/response mỗi lượt.
- `MATCH` lọc theo pattern, không đồng nghĩa chỉ Redis duyệt đúng những key phù hợp.
- Trên Redis Cluster, `SCAN` theo một node không phải truy vấn toàn bộ cluster.
- Đóng Cursor khi xong để giải phóng tài nguyên kết nối.

Test `SCAN` nên xác định **xử lý đúng kết quả có thể lặp** và thời gian/memory phù hợp, không assert mỗi vòng luôn có đúng 100 keys.

## 19. Phân trang scan trong ứng dụng không có nghĩa phân trang ổn định

Nếu UI muốn “trang 1, trang 2, trang 3” trên tập dữ liệu thay đổi liên tục, `SCAN` không cung cấp **stable ordering và snapshot paging** như một truy vấn database có cơ chế snapshot phù hợp.

Vì thế không nên lộ raw Redis SCAN cursor như pagination nghiệp vụ mà chưa hiểu đặc tính:

- Key có thể được thêm hoặc xóa giữa các vòng.
- Một key có thể xuất hiện lặp.
- Thứ tự không mang ý nghĩa nghiệp vụ.
- Độ dài mỗi lượt trả về biến thiên.
- Cursor có vòng đời và ý nghĩa theo điểm quét, topology, client.

`SCAN` tốt cho **bảo trì/kiểm kê best-effort**, không phải mặc định tối ưu cho “trang sản phẩm được sắp xếp theo mới nhất”. Khi cần paging ổn định, hãy chọn cấu trúc/cơ sở dữ liệu được thiết kế cho truy vấn đó, chẳng hạn ZSet có score với quy tắc tie-break rõ ràng hoặc SQL.

## 20. Redis Streams COUNT và batchSize của listener

Với Redis Streams, `COUNT` giới hạn số entry yêu cầu trong một lần đọc:

```bash
redis-cli XREAD COUNT 100 STREAMS orders:events 0-0
```

Trong consumer group:

```bash
redis-cli XREADGROUP GROUP orders-workers worker-1 COUNT 100 STREAMS orders:events '>'
```

Khi dùng Spring Data Redis:

```java
import java.time.Duration;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;

var options = StreamMessageListenerContainerOptions
        .<String, org.springframework.data.redis.connection.stream.MapRecord
                <String, String, String>>builder()
        .batchSize(100)
        .pollTimeout(Duration.ofSeconds(2))
        .executor(taskExecutor)
        .build();
```

`taskExecutor` là bean executor do ứng dụng cấu hình. Ví dụ chỉ mô tả options, còn container cần được tạo, đăng ký listener và start/stop theo lifecycle phù hợp.

Cần phân biệt:

- `batchSize(100)` điều khiển số record mỗi lần **poll**.
- Nó không tự giới hạn tối đa 100 message trong **Pending Entries List (PEL)**.
- Nó không bảo đảm listener xử lý 100 message trong một transaction nghiệp vụ.
- Nó không tự thực hiện `XACK` sau xử lý đúng theo yêu cầu.
- Nếu listener chậm, batch lớn có thể khiến message được giao rồi chờ xử lý lâu.
- Nếu worker crash, các message chưa ACK vẫn có thể pending và cần reclaim.

### Bảng tác động của batchSize trong Streams

| Batch nhỏ | Batch lớn |
|---|---|
| Nhanh phản ứng với message mới khi có flush/poll phù hợp | Ít vòng đọc hơn khi backlog dày |
| Ít message được giao trong mỗi lượt | Có thể tạo nhiều message đang chờ ACK hơn |
| Thường dễ cô lập message lỗi | Cần phân biệt message nào đã xử lý thành công |
| Callback được kích hoạt theo nhịp nhỏ hơn | Một lượt đọc lớn có thể giữ handler bận lâu |
| Thích hợp khi message nặng/không đồng nhất | Có thể tốt khi message nhỏ, handler nhanh và nguồn nhiều |

Đừng tăng batchSize để xử lý lỗi PEL phình to do consumer không ACK. Đó là bài toán **recovery, idempotency và downstream throughput**, không chỉ là số message lấy mỗi vòng.

## 21. Lua script cũng có “kích thước nhóm” và rủi ro blocking

Một Lua script có thể gọi hàng trăm Redis commands ở server-side, tiết kiệm round-trip và giúp logic kiểm tra–ghi nguyên tử.

Ví dụ:

```lua
-- KEYS[1] = key counter
-- ARGV[1] = increment step

local current = redis.call('INCRBY', KEYS[1], ARGV[1])
return current
```

Với bài toán tăng counter, **`INCRBY` đơn là đủ**; dùng Lua chỉ để bọc đúng một command sẽ không đem lại lợi ích atomicity mới.

Lua có ý nghĩa hơn khi phải ghép nhiều thao tác, ví dụ kiểm tra version rồi cập nhật có điều kiện:

```lua
-- KEYS[1] = value key
-- ARGV[1] = expected string
-- ARGV[2] = new string

local current = redis.call('GET', KEYS[1])

if current == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2])
    return 1
end

return 0
```

Tuy nhiên **gom quá nhiều thao tác vào một script** làm Redis server bận thực thi script lâu; các command client khác phải chờ. Với logic kiểm tra phức tạp, hàng chục nghìn key hoặc loop dài, p99 của toàn Redis instance/primary có thể bị ảnh hưởng.

Lua script không tự hỗ trợ chia nhỏ giữa chừng như một pipeline chunk, bởi chia nhỏ có thể mất atomicity toàn cục mà business muốn. Vì vậy cần giới hạn **phạm vi bất biến** để script ngắn; nếu cần xử lý một dataset cực lớn, xem lại kiến trúc dữ liệu thay vì tạo một “siêu script” xử lý toàn bộ.

### Hai sai lầm khi test Lua batch lớn

1. Script lỗi sau một số lệnh ghi **không rollback** những tác động đã xảy ra trước runtime error.
2. Redis client timeout sau `EVAL` không chứng minh script chưa chạy; retry có thể lặp side effect.

Trong Redis Cluster, các key mà script sử dụng cần tuân thủ hash-slot restrictions. Một test standalone thành công không chứng minh script nhiều key chạy được trên cluster.

## 22. Redis Cluster làm lựa chọn batch phức tạp hơn

Redis Cluster ánh xạ mỗi key vào một trong **16.384 hash slots**. Các lệnh multi-key có ràng buộc slot; còn các lệnh độc lập trong pipeline phải được cluster-aware client định tuyến tới primary phù hợp.

```text
Ứng dụng có 300 GET:
  100 keys -> slot/node A
  100 keys -> slot/node B
  100 keys -> slot/node C
```

Nếu chỉ kết nối một node và tự gửi `MGET` cho mọi key, Redis có thể trả `CROSSSLOT`. Nếu client cluster-aware gửi các `GET` độc lập, nó có thể route theo slot, nhưng tốc độ/buffering của từng node có thể khác nhau.

Những điểm phải cân nhắc:

- **Multi-key command:** các key phải đáp ứng điều kiện hash slot và hỗ trợ từ client/server.
- **Pipeline:** routing tới các nodes có thể làm phân phối buffer/latency khác với standalone.
- **Lua/MULTI:** phạm vi atomicity không tự vượt qua nhiều Redis primaries.
- **Hot slot:** hash tag quá rộng dồn quá nhiều key vào một slot/node.
- **Failover/resharding:** `MOVED`/`ASK` và timeout có thể xuất hiện giữa một nhóm lệnh.
- **Read preference:** nếu đọc replica, dữ liệu có thể stale so với primary.
- **Node memory:** server có giới hạn memory/buffer theo node; batch cân bằng ở client không có nghĩa tải đều giữa các primary.

Nếu chọn hash tag như `cart:{user-42}:items` và `cart:{user-42}:total`, hai key thuộc cùng slot, thuận lợi khi nghiệp vụ cần multi-key operations. Nhưng không dùng cùng tag `{global}` cho mọi key, vì điều đó phá phân phối tải.

### Thời gian đáp ứng bị chi phối bởi node chậm nhất

Khi một batch hợp thành cần replies từ nhiều nodes, latency end-to-end có thể bị chi phối bởi **node trả chậm nhất**, ngay cả khi hai node còn lại rất nhanh. Vì thế cần đo latency theo node/slot và response size, không chỉ latency trung bình toàn cluster.

## 23. Giới hạn đồng thời quan trọng ngang giới hạn batch

Giả sử mỗi pipeline chứa 100 commands và trả trung bình 50 KiB replies. Nếu 10 pipeline đồng thời:

```text
100 × 10 = 1.000 commands đang liên quan
50 KiB × 10 = 500 KiB payload reply (minh họa)
```

Nếu tăng lên 1.000 pipeline in-flight:

```text
100 × 1.000 = 100.000 commands
50 KiB × 1.000 ≈ 48,8 MiB payload reply
```

Chưa tính protocol, metadata, futures, Java objects và client/server buffers. Tăng throughput bằng cách mở vô hạn pipelines có thể làm memory và latency không kiểm soát.

Một chính sách hữu ích:

```text
maxCommandsPerBatch = 100
maxEstimatedBytesPerBatch = 1 MiB
maxInFlightBatches = 8
maxWaitBeforeFlush = 5 ms
```

Các con số là **ví dụ khái niệm**, không phải defaults được Spring Data Redis cung cấp thành một config chung. Một số giới hạn phải do lớp application/queue tự thực hiện.

Nên có **backpressure**: khi đã đủ batch in-flight, yêu cầu mới chờ ở hàng đợi **có giới hạn**, bị từ chối theo hợp đồng hoặc giảm tốc upstream. Không để queue Java phát triển vô hạn trong một Redis outage.

## 24. Buffer theo số lượng và thời gian trong reactive pipeline

Project Reactor có thể gom phần tử bằng `bufferTimeout(maxSize, maxTime)`:

```java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> sourceKeys = Flux.fromIterable(keys);

Flux<List<String>> batches = sourceKeys
        .bufferTimeout(100, Duration.ofMillis(10));
```

Ở đây batch được phát khi **đủ 100 keys** hoặc khi **đủ thời gian chờ tối đa theo operator**. Nhưng chưa có Redis I/O trong ví dụ này; `bufferTimeout` chỉ gom dữ liệu ở tầng Reactor.

Nếu ứng dụng dùng `ReactiveStringRedisTemplate`:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;

Flux<List<String>> results = Flux.fromIterable(keys)
        .bufferTimeout(100, Duration.ofMillis(10))
        .flatMap(
                batch -> reactiveRedis.opsForValue().multiGet(batch),
                4);
```

`reactiveRedis` là một bean `ReactiveStringRedisTemplate` đã cấu hình. `flatMap(..., 4)` giới hạn **concurrency của các publishers con** ở mức minh họa 4; nó không tự giới hạn toàn bộ memory của `keys` đầu vào hay đảm bảo những batch đang xử lý không vượt byte budget. Nếu kết quả phải giữ đúng thứ tự batch đầu vào, cân nhắc `concatMap` hoặc cơ chế lập lại thứ tự phù hợp.

**Lưu ý thực tế:** `multiGet` có thể trả `List` chứa phần tử `null` cho key miss theo hợp đồng API; không đẩy trực tiếp các `null` vào `Flux.just/Flux.fromIterable` mà chưa xử lý. Cũng phải kiểm tra multi-key slot rules nếu Redis deployment là Cluster.

### Không gọi block() trong WebFlux chỉ để ép batching

Một service reactive không nên làm:

```java
List<String> values =
        reactiveRedis.opsForValue()
                .multiGet(batch)
                .block();
```

trên WebFlux event-loop. `block()` biến xử lý thành chờ đồng bộ và có thể gây lỗi trên các thread không cho blocking. Nên trả `Mono`/`Flux` và hợp thành pipeline để framework subscribe.

## 25. Tại sao cần byte budget cho micro-batching?

`bufferTimeout(100, 10 ms)` giới hạn số item và thời gian, **không giới hạn tổng serialized bytes**. Một item có payload 10 MiB vẫn có thể khiến batch chỉ 100 phần tử rất lớn.

Nếu payload không đồng nhất, application cần:

- Ước lượng byte trước khi enqueue.
- Không nhận item vượt một ngưỡng đơn lẻ nếu hệ thống không hỗ trợ xử lý nó.
- Flush batch khi sắp vượt byte budget.
- Giới hạn số batch in-flight.
- Thời gian chờ tối đa cho item đến sớm.
- Chính sách xử lý item quá lớn (đường riêng, phân mảnh hợp lệ hoặc từ chối).

### Pseudocode của một batch aggregator

```text
batch = []
batchBytes = 0
firstEnqueuedAt = none

for each incomingItem:
    itemBytes = estimateSerializedSize(incomingItem)

    if itemBytes > MAX_SINGLE_ITEM_BYTES:
        rejectOrRouteSeparately(incomingItem)
        continue

    if batch not empty and (
        batch.size >= MAX_ITEMS or
        batchBytes + itemBytes > MAX_BATCH_BYTES
    ):
        submitWithInFlightLimit(batch)
        batch = []
        batchBytes = 0

    add incomingItem to batch
    batchBytes += itemBytes

    if now - firstEnqueuedAt >= MAX_WAIT:
        submitWithInFlightLimit(batch)
        batch = []
        batchBytes = 0
```

Trong implementation thật, cần timer/đồng hồ monotonic, thread safety, flush khi shutdown và xử lý queue overflow; pseudocode ở đây chỉ làm rõ điều kiện **flush khi chạm bất kỳ giới hạn nào**.

Không được tính itemBytes dựa trên số ký tự Java đơn thuần nếu Redis wire format dùng UTF-8, JSON, compression hay binary protocol; kích thước bytes trên mạng có thể khác.

## 26. Batch quá lớn có thể gây head-of-line blocking

Một batch có hàng nghìn operations xử lý chậm giữ connection/server bận, khiến những request xuất hiện sau phải chờ.

```text
Connection / Redis server:
  [Batch A: 5.000 lệnh]   [GET khẩn]   [Batch B]
          lâu                chờ
```

Có thể cải thiện bằng cách:

1. Chia batch dài thành các chunk ngắn hơn.
2. Giới hạn số commands và bytes mỗi batch.
3. Tách critical traffic (interactive GET) khỏi background bulk jobs nếu hạ tầng/chính sách cho phép.
4. Điều chỉnh mức đồng thời thay vì đổ mọi command vào cùng một connection.
5. Đo p95/p99 theo workload, không chỉ throughput của bulk jobs.
6. Tránh Lua hoặc `EXEC` rất lớn nếu sẽ giữ Redis server không phục vụ các client khác đủ lâu.
7. Đặt deadline theo request để batcher không giữ công việc đã quá hạn mà không có giá trị.

Nếu Redis server đã CPU-bound hoặc memory-bound, giảm round-trip bằng pipeline có thể không còn tăng throughput; nó chỉ làm hàng đợi dài hơn.

## 27. Khi nào batch size nên nhỏ?

Ưu tiên batch nhỏ hoặc không chờ gom khi:

- Request có deadline thấp và traffic đến thưa.
- Mỗi value/reply lớn hoặc phân phối kích thước rất không đồng đều.
- Redis node đã có latency p99 cao.
- Mỗi command có side effect khó retry/idempotency.
- Có nhiều failure domains, ví dụ cluster routing qua nhiều nodes.
- Cần cô lập từng item lỗi để báo kết quả chi tiết.
- Lua script hoặc transaction chứa logic tốn CPU/server time.
- Ứng dụng có bộ nhớ JVM hạn chế hoặc container bị giới hạn memory nghiêm ngặt.
- Downstream database/consumer xử lý chậm và cần backpressure rõ ràng.

Một cách tiếp cận thường hợp lý là chọn batch nhỏ làm baseline, đo rồi tăng có kiểm soát. Không cố đạt số throughput cao nhất nếu đã vượt giới hạn tail latency hoặc memory.

## 28. Khi nào batch size lớn hơn có thể hữu ích?

Batch lớn hơn có thể có lợi khi:

- Input đã có sẵn một tập dữ liệu lớn, không tốn thời gian chờ gom.
- RTT đến Redis cao hơn đáng kể so với command time.
- Mỗi command nhỏ, đơn giản, độc lập và an toàn khi xử lý theo chunk.
- Redis/server/network còn headroom.
- Application tiêu thụ reply theo chunk và không cần giữ toàn bộ data.
- Lỗi một phần có cách retry/idempotency rõ ràng.
- Batch chỉ chạy ở background với deadline khác interactive traffic.
- Có cơ chế giám sát p99, memory peak và giới hạn số batch in-flight.

Ngay cả trong trường hợp này, nên tăng theo từng bước và dừng tại điểm mà throughput gần như không cải thiện nhưng memory hoặc p99 bắt đầu tăng đáng kể.

## 29. Benchmark phải trả lời câu hỏi nào?

Một phép benchmark hữu ích cần xác định:

- **Workload:** 100% GET, 100% SET, GET/SET hỗn hợp, command mix Hash/ZSet hay Streams.
- **Dữ liệu:** số keys, payload bytes, key hit/miss ratio, cache TTL, hot key distribution.
- **Mạng:** RTT và bandwidth thực tế tới Redis, cùng hoặc khác vùng mạng.
- **Topology:** standalone, Sentinel, Redis Cluster; có đọc replica không.
- **Client:** Spring Data Redis version, Lettuce version, serializer, connection config.
- **Kích thước nhóm:** số commands, bytes, thời gian chờ và in-flight.
- **Concurrency:** số request/threads/publishers đồng thời.
- **Thời gian:** warm-up, steady-state và thời gian sample.
- **Kết quả:** throughput, p50/p95/p99, error rate, memory peak và correctness.
- **Đơn vị đo:** request HTTP, Redis commands hay processed records.

Đừng gọi một số đo 100.000 Redis commands/s là “100.000 user requests/s” nếu mỗi user request thực hiện 20 commands.

## 30. Thiết kế một ma trận thử nghiệm có kiểm soát

Một thử nghiệm có thể khảo sát các cấu hình sau, **không phải khuyến nghị mặc định**:

| Cấu hình | Max commands | Max bytes | Max wait | Max in-flight |
|---|---:|---:|---:|---:|
| A — baseline | 1 | 64 KiB | 0 ms | 4 |
| B — nhỏ | 20 | 256 KiB | 2 ms | 4 |
| C — vừa | 100 | 1 MiB | 5 ms | 8 |
| D — lớn | 500 | 4 MiB | 10 ms | 8 |
| E — rất lớn | 2.000 | 16 MiB | 20 ms | 8 |

Với mỗi cấu hình, ghi nhận:

```text
throughput_ops_sec
throughput_http_requests_sec
latency_p50_ms
latency_p95_ms
latency_p99_ms
batch_formation_wait_p99_ms
batch_fill_ratio
batch_bytes_p95
batch_bytes_p99
inflight_batch_max
pending_queue_depth_max
jvm_heap_used_peak
jvm_gc_pause_p99
redis_command_latency_p99
redis_memory_used
redis_cpu
timeout_rate
retry_rate
error_rate
```

Nếu tăng từ C lên E làm throughput chỉ tăng 2% nhưng p99 tăng từ 40 ms lên 180 ms và heap peak gấp đôi, E khó là lựa chọn tốt cho một HTTP API có SLO p99 = 100 ms.

Cần so sánh nhiều lần để tránh ảnh hưởng của warm-up, GC và fluctuations trên CI. Khi benchmark production-like, bảo đảm tải đủ lâu để phát hiện memory buildup hoặc queue saturation, chứ không chỉ test 10 giây khi hệ thống còn trống.

## 31. Đo end-to-end latency bằng Java

Một phép đo đơn giản:

```java
long started = System.nanoTime();

try {
    List<Object> replies = redis.executePipelined(callback);
    processReplies(replies);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordLatencyNanos(elapsedNanos);
}
```

`recordLatencyNanos` là hàm đo metric do ứng dụng triển khai. `System.nanoTime()` phù hợp đo khoảng thời gian trôi qua, không phải timestamp để hiển thị theo múi giờ.

Tuy nhiên, đoạn trên chỉ đo từ lúc đã bắt đầu gọi Redis/pipeline. Nếu request nằm trong **batch queue** trước đó, phải đánh dấu thời gian **ngay khi item vào queue**:

```text
item.receivedAtNanos
    |
    +--> đợi batch formation
    |
    +--> đợi in-flight permit
    |
    +--> Redis command
    |
    +--> deserialize
    |
    +--> business result ready
    |
item.completedAtNanos

Latency E2E = completed - received
```

Cần phân biệt latency của từng item với latency toàn batch. Nếu chỉ ghi timer của một batch 100 items, bạn có thể bỏ sót request đầu tiên đợi lâu hơn request cuối cùng.

### Giám sát bằng Micrometer

Ứng dụng Spring Boot có thể dùng Micrometer/Actuator để xuất histogram timers và percentiles theo cấu hình registry. Khi gắn tags:

- Operation type: GET, SET, MGET, pipeline, Streams poll.
- Batch size bucket: nhỏ/vừa/lớn, không thêm giá trị riêng cho từng batch.
- Namespace hoặc service logical name.
- Success/error/timeout.
- Redis topology hoặc node role nếu telemetry có.
- Payload size bucket.

**Không đưa Redis key chứa user ID/token vào metric tag**, vì sẽ tạo cardinality rất lớn và có thể làm lộ dữ liệu nhạy cảm. Đo bytes và counts theo histogram thay vì một time series cho từng key.

## 32. Little's Law và lượng công việc in-flight

Một quy tắc hàng đợi hữu ích là **Little's Law** trong trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó:

- `L`: số request/operation trung bình đang nằm trong hệ thống;
- `λ`: tốc độ đến/hoàn tất trung bình;
- `W`: thời gian ở trong hệ thống trung bình.

Nếu hệ thống xử lý khoảng 20.000 operations/s và mỗi operation mất trung bình 50 ms end-to-end, số operation in-flight trung bình có thể gần:

\[
L = 20\,000 \times 0.05 = 1\,000
\]

Nó không nói Redis có 1.000 command cùng chạy song song; đây là **lượng công việc đang chờ hoặc được xử lý ở toàn hệ thống** theo phạm vi đo.

Khi batch formation delay tăng, `W` tăng, nên `L` và nhu cầu buffering cũng có thể tăng ngay cả khi throughput không thay đổi. Đây là lý do tăng batch size đôi khi làm memory tăng theo một vòng lặp xấu: batch lớn → chờ lâu → nhiều request in-flight → queue sâu hơn → latency cao hơn.

Little's Law là công cụ suy luận, không phải phép dự đoán chính xác dưới traffic burst hoặc hệ thống chưa ổn định.

## 33. Backpressure và từ chối tải an toàn

Khi hàng đợi batcher đầy, ứng dụng có ba lựa chọn chính:

1. **Backpressure:** làm upstream tạm chậm lại theo contract.
2. **Bounded queue + reject:** từ chối hoặc trả lỗi thích hợp khi đã vượt giới hạn.
3. **Load shedding/priority:** bảo vệ các request quan trọng hơn, giảm tác vụ không thiết yếu.

Điều không nên làm là giữ một `ConcurrentLinkedQueue` vô hạn rồi tiếp tục nhận request khi Redis chậm. Bộ nhớ JVM có thể hết trước Redis.

Nếu xử lý message từ Redis Streams, backpressure còn liên quan đến **độ trễ ACK/PEL**, không chỉ queue Java. Khi ngừng nhận batch mới, cần đảm bảo message đã nhận nhưng chưa ACK vẫn có đường recovery khi worker crash.

Nếu sử dụng reactive operators, `flatMap(..., concurrency)` giúp giới hạn publisher con đồng thời, nhưng không tự giải quyết byte budget, subscription upstream demand hoặc dữ liệu đã được tạo từ nguồn eager. Cần quan sát queueing toàn pipeline.

## 34. Các trường hợp không nên tăng pipeline để “chữa” lỗi

### Lỗi A: Redis server CPU đã gần bão hòa

Nếu Redis CPU đã là bottleneck, batching có thể giảm network overhead mà **không làm server xử lý command nhanh hơn nhiều**. Một batch lớn làm hàng đợi dài hơn và có thể tăng p99. Cần tối ưu command/algorithm, payload hoặc scale/shard phù hợp.

### Lỗi B: Network bandwidth bị nghẽn vì value lớn

Pipeline không làm biến mất số byte phải truyền. Nếu truyền 10 GiB values, việc gom các GET không giảm tổng payload. Cần giảm kích thước data, chọn chỉ field cần hoặc caching strategy khác.

### Lỗi C: Nhiều kết quả được giữ trên heap

Một pipeline khổng lồ trả `List<Object>` có thể khiến GC pause tăng. Chia chunk và xử lý từng phần, không gom thêm results vào list khác.

### Lỗi D: Workload chứa hot key

Một key/slot nóng trong Redis Cluster có thể tạo bottleneck. Tăng batch size từ client không làm phân phối một ZSet khổng lồ qua nhiều primary. Cần đánh giá data model/key sharding theo use case.

### Lỗi E: Mỗi lệnh cần atomic condition

Nếu cần “kiểm tra còn hàng rồi trừ tồn kho”, pipeline của `GET` và `DECR` không bảo đảm an toàn cạnh tranh. Dùng lệnh atomic hoặc Lua/transaction phù hợp trước khi benchmark.

### Lỗi F: Redis Streams pending tăng do không ACK

Tăng `batchSize` không giải quyết consumer đã nhận nhưng không ACK. Cần kiểm tra PEL, xử lý lỗi, idempotency và reclaim worker.

### Lỗi G: Connection timeout và retry không giới hạn

Batch lớn + retry vô hạn sau timeout có thể khuếch đại tải và tạo side effect lặp. Cần retry budget và phân loại command idempotency.

## 35. Case study: bulk cache warm-up

Một ứng dụng cần làm nóng 200.000 product cache entries từ database trước chiến dịch.

Yêu cầu:

- Dữ liệu gốc nằm trong database; Redis chỉ là cache.
- Mỗi product entry có TTL.
- Hoạt động warm-up chạy background, không được gây ảnh hưởng lớn đến traffic HTTP.
- Mỗi product có payload 1–10 KiB.
- Cho phép retry những entry chưa hoàn thành nếu version/TTL phù hợp.

Một phương án:

```text
Database cursor (pages 200-500 rows)
        |
        v
Serialize product DTOs
        |
        v
Bounded pipeline chunks
  max items = 100
  max estimated bytes = 512 KiB
  max in-flight = 2
        |
        v
Redis SET with TTL
        |
        v
Metrics + checkpoint progress
```

Đừng tải 200.000 rows vào một `List<Product>` rồi gửi một pipeline 200.000 SET. Dù Redis chấp nhận các commands, JVM có thể cần giữ input/replies lớn, tăng GC và làm request tương tác chịu latency.

Cần đo:

- Background throughput.
- Redis memory/cpu và eviction rate.
- P99 GET/SET của traffic người dùng trong lúc warm-up.
- Số item retry hoặc bị bỏ qua.
- Cache freshness/source version nếu dữ liệu có thể đổi trong lúc warm-up.

Nếu dữ liệu nguồn đổi trong thời gian chạy, một warm-up job đọc version cũ rồi SET sau một update mới có thể làm cache stale. Batch size không giải quyết được race này; cần TTL, version-aware write hoặc invalidation phù hợp.

## 36. Case study: tra cứu nhiều user permissions

Một service cần đọc permissions của 5 user cho mỗi HTTP request, p99 mục tiêu rất thấp.

Hai cách:

```text
A: 5 GET tuần tự
B: 1 MGET (nếu key placement/command hợp lệ)
C: pipeline 5 GET qua cluster-aware driver
```

Lượng dữ liệu nhỏ và đã có sẵn trong một request, nên batching có thể giảm RTT mà **không có batch formation wait**. Đây là tình huống phù hợp để cân nhắc `multiGet` hoặc pipeline.

Nhưng permissions có thể là dữ liệu bảo mật, stale read hoặc fallback khi Redis lỗi phải được đánh giá nghiêm ngặt. Không nên đọc replica stale chỉ để tăng throughput khi quyền vừa bị thu hồi.

Nếu request chỉ cần 5 keys, không có lý do chờ “gom đủ 100 user keys” từ các HTTP requests khác nếu điều đó đẩy p99 lên cao. Một microbatcher liên-request chỉ phù hợp khi đo thấy lợi ích lớn và ràng buộc latency cho phép.

## 37. Case study: consumer Redis Streams

Một worker xử lý event cập nhật search index:

```text
XREADGROUP COUNT B
    |
    v
Deserialize B records
    |
    v
Process each record
    |
    +--> success -> XACK
    |
    +--> failure -> leave pending/retry/DLQ
```

Nếu `B=10`, nhiều lần poll nhưng dễ giới hạn backlog local. Nếu `B=500`, ít lần poll khi stream có nhiều dữ liệu nhưng hàng trăm message có thể đã giao cho consumer, đang chờ xử lý/ACK.

Nên đo:

- Thời gian xử lý trung bình và p99 từng event.
- Poll count và time blocked.
- PEL size và oldest pending idle.
- Throughput đã **ACK**, không chỉ đã nhận từ Redis.
- Reclaim/duplicate count.
- JVM heap khi message payload lớn.
- End-to-end event lag từ `XADD` đến nghiệp vụ hoàn tất.

Không dùng `COUNT` để mặc định rằng Redis sẽ đợi đủ B message mới trả về; các lệnh stream read có semantics riêng về số records được trả và BLOCK timeout. Hiệu ứng “chờ đủ batch” thường là cơ chế gom ở ứng dụng, không phải nghĩa phổ quát của Redis Streams COUNT.

## 38. Case study: cập nhật 50.000 scores trong ZSet

Một tác vụ cập nhật điểm của nhiều users:

```text
ZINCRBY leaderboard:weekly:{game-1} delta user-id
```

Gom 50.000 `ZINCRBY` vào một pipeline duy nhất có thể giảm round-trips nhưng cũng có rủi ro:

- Một ZSet key nóng thuộc một Redis primary, không scale theo số member.
- Client giữ nhiều commands/replies.
- Nếu timeout sau khi đã xử lý một phần, retry `ZINCRBY` có thể làm điểm tăng trùng.
- Background bulk update kéo dài khiến request xem leaderboard có p99 cao hơn.
- Một phần lỗi không được rollback như một giao dịch SQL.

Nếu mỗi event có operation ID và cần chống trùng, thiết kế idempotency trước rồi chia thành chunks nhỏ có checkpoint. Nếu tất cả scores có thể **được thay thế bằng giá trị tuyệt đối có version**, một chiến lược `ZADD` có điều kiện phù hợp có thể dễ retry hơn; nhưng vẫn phải đảm bảo không ghi lùi version khi các batch đan xen.

Đừng lựa chọn kích thước pipeline chỉ dựa trên số lượng users; hãy đo command cost của ZSet, hot-key pressure và memory.

## 39. Chiến lược chọn batch size thực dụng

Một quy trình triển khai:

1. **Xác định ngữ nghĩa:** pipeline, multi-key, Streams, SCAN hay Lua? Cần atomicity không?
2. **Xác định SLO:** p95/p99 end-to-end, throughput tối thiểu, memory limit.
3. **Đo baseline B=1** với workload tương đương production.
4. **Ước lượng payload size distribution**, nhất là p95/p99 bytes/item.
5. **Chọn giới hạn ban đầu thấp** cho max items và max bytes.
6. **Đặt max wait time** nếu phải gom liên-request.
7. **Đặt max in-flight và queue capacity** để memory bị chặn ở giới hạn xác định.
8. **Benchmark nhiều mức B**, không chỉ một giá trị “tối ưu” theo kinh nghiệm.
9. **Đo p99 và memory peak** ở thời điểm tải cao, không chỉ trung bình.
10. **Kiểm tra correctness và partial failure** khi timeout, Redis restart/failover.
11. **Chọn điểm cân bằng**, không chọn batch size throughput cực đại nếu vượt SLO.
12. **Giám sát và điều chỉnh** khi command mix, payload distribution hoặc traffic thay đổi.

Nếu workload thay đổi rất lớn theo giờ, có thể cân nhắc **adaptive batching** dựa trên queue depth/latency và memory pressure. Tuy nhiên cơ chế thích ứng cần giới hạn trên/dưới và kiểm thử ổn định; một bộ điều khiển tự tăng batch khi throughput giảm có thể làm tình trạng nghẽn nặng hơn.

## 40. Checklist trước khi đưa batching vào production

- [ ] Mỗi batch được định nghĩa đúng đơn vị (commands, bytes, records, key count).
- [ ] Biết cơ chế đó có **atomic** hay không; không dùng pipeline để thay transaction.
- [ ] Có giới hạn số items, serialized bytes, max wait và max in-flight.
- [ ] Có xử lý item quá lớn và áp lực hàng đợi.
- [ ] Có budget cho heap, reply list, network buffers và Redis client buffers.
- [ ] Kết quả được map đúng về input; xử lý cache miss và error.
- [ ] Pipeline/chunk có partial-failure và retry policy rõ ràng.
- [ ] Side effects như `INCR`/`XADD`/`ZINCRBY` có idempotency khi cần.
- [ ] Trên Redis Cluster, multi-key commands và Lua tuân thủ hash-slot rules.
- [ ] Nếu dùng `SCAN`, hiểu COUNT là hint và cursor không phải snapshot.
- [ ] Nếu dùng Streams, đo ACK throughput, PEL và recovery, không chỉ poll rate.
- [ ] Có histogram p50/p95/p99 từ lúc request vào batch tới lúc hoàn tất.
- [ ] Có metrics bytes/batch, batch fill ratio, queue wait, retries và memory peak.
- [ ] Benchmark với dữ liệu, serializer, network và topology tương đương production.
- [ ] Không chạy bulk job lớn làm interactive traffic vi phạm SLO.
- [ ] Có ngưỡng rollback cấu hình nếu p99 hoặc memory vượt giới hạn.

## 41. Câu hỏi tự đánh giá

**1. Vì sao pipeline 1.000 SET có thể nhanh hơn 1.000 SET tuần tự?**  
Vì giảm thời gian chờ round-trip từng lệnh, nhưng tổng command work, network bytes và memory buffer không biến mất.

**2. Vì sao batch lớn có thể tăng p99 dù throughput tốt hơn?**  
Vì thời gian gom batch, queueing, deserialize replies, head-of-line blocking và GC có thể tăng.

**3. `executePipelined` có làm toàn nhóm SET nguyên tử không?**  
Không. Nó là tối ưu I/O, không mặc nhiên có transaction hoặc rollback.

**4. Vì sao cùng 100 GET nhưng memory có thể khác nhau rất lớn?**  
Kích thước value/reply khác nhau; số commands không đủ để dự báo bytes.

**5. Cần những giới hạn nào ngoài maxBatchSize?**  
Max bytes, max wait time, max in-flight batches và bounded queue/backpressure.

**6. `SCAN COUNT 100` có bảo đảm mỗi lần trả đúng 100 keys?**  
Không. COUNT là hint; mỗi lượt có thể trả số phần tử khác 100, kể cả 0.

**7. Stream listener batchSize=100 có giới hạn PEL tối đa 100 message không?**  
Không. PEL có thể tích lũy khi message chưa ACK.

**8. Vì sao cần đo latency từ lúc request vào batch queue?**  
Vì nếu chỉ đo Redis execution, bạn bỏ qua formation wait, có thể là phần trễ lớn nhất.

**9. `MGET` có tự tương thích với mọi key đa slot Redis Cluster không?**  
Không được giả định. Multi-key slot rules và driver behavior phải được xác định/test.

**10. Nếu một lệnh ZINCRBY đã chạy rồi client timeout, retry có chắc an toàn?**  
Không. Retry có thể cộng điểm hai lần nếu không có idempotency.

**11. Lua script rất lớn có thể ảnh hưởng request không liên quan thế nào?**  
Khi Redis đang thực thi script, các command client khác phải đợi; p99 của node có thể tăng.

**12. Tại sao MGET theo chunk có thể vẫn tốn rất nhiều memory?**  
Nếu application giữ mọi chunk result trong một List lớn, memory peak vẫn tăng theo tổng output.

**13. Một workload đã CPU-bound trên Redis có chắc hưởng lợi khi tăng batch size không?**  
Không. Giảm network overhead không loại bỏ CPU bottleneck; queueing có thể xấu hơn.

**14. Little's Law giúp hiểu gì?**  
Khi throughput giữ nguyên mà thời gian ở trong hệ thống tăng, số request/item đang chờ hoặc xử lý cũng tăng, gây thêm nhu cầu buffer.

**15. Nên chọn batch size throughput cao nhất hay đáp ứng SLO tổng thể?**  
Chọn cấu hình đạt throughput cần thiết **trong giới hạn p99, memory, error budget và correctness**.

## 42. Kết luận

**Batching không phải mục tiêu tự thân; nó là một cách đánh đổi chi phí mạng lấy buffering và thời gian chờ.** Trong Spring Data Redis, một nhóm lớn có thể tăng throughput khi RTT là bottleneck, nhưng cũng có thể đẩy bộ nhớ, GC, queue wait và p99 vượt ngân sách.

Muốn chọn đúng:

- Hiểu rõ **pipeline ≠ transaction**, `SCAN COUNT ≠ page size cố định`, `Streams COUNT ≠ ACK guarantee`.
- Xem xét **số item và tổng bytes**, không chỉ số command.
- Đo **latency end-to-end**, bao gồm thời gian request chờ được gom.
- Giới hạn **in-flight batches** và hàng đợi thay vì để workload phát triển vô hạn.
- Kiểm chứng **partial failure, idempotency và Redis Cluster constraints**.
- Tăng batch size theo dữ liệu đo thật và dừng ở điểm phù hợp với SLO, không phải giá trị tối đa mà Redis còn chấp nhận.

Câu hỏi đáng đặt khi quyết định là: **“Nếu tăng số phần tử mỗi batch thêm 5 lần, throughput tăng bao nhiêu, p99 tăng bao nhiêu, số byte đang in-flight tăng bao nhiêu và khi batch lỗi sẽ phục hồi như thế nào?”** Một quyết định hiệu năng tốt phải trả lời được cả bốn phần.

## Tài liệu tham khảo

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, callback và kết quả trả về.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations và serializer.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI`/`EXEC`, `SessionCallback` và giao dịch Redis.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `COUNT`, listener container, ACK và pending.
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): các API reactive và publisher.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): round-trip optimization và giới hạn tài nguyên.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): semantics transaction và không rollback runtime errors.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor, COUNT hint và thay đổi keyspace.
- [Redis — MGET](https://redis.io/docs/latest/commands/mget/): trả về values theo key order.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): COUNT, consumer group và pending messages.
- [Redis — Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): Lua atomicity và hạn chế script.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, multi-key constraints và failover.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): giới hạn memory, TTL và eviction.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Flux`, batching, concurrency và backpressure.
