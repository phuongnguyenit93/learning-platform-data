# Chia nhóm lệnh để kiểm soát bộ nhớ và độ trễ

Trong Spring Data Redis, **pipelining** cho phép client gửi nhiều lệnh Redis liên tiếp mà không phải chờ phản hồi của từng lệnh rồi mới gửi lệnh kế tiếp. Thay vì thực hiện tuần tự `SET key1 ...`, nhận phản hồi, tiếp tục `SET key2 ...`, client có thể gửi cả một nhóm lệnh và đọc các phản hồi sau đó. Lợi ích chính là giảm chi phí **network round-trip** khi phải thao tác với nhiều key độc lập.

Tuy nhiên, gửi càng nhiều lệnh trong một pipeline không đồng nghĩa với hiệu năng càng tốt. Client cần giữ dữ liệu đầu vào và kết quả, Redis phải nhận/xử lý các lệnh và có thể giữ phản hồi chưa gửi hoặc chưa được client tiêu thụ trong bộ đệm. Pipeline khổng lồ có thể làm tăng mức dùng bộ nhớ, kéo dài thời gian một nhóm hoàn thành, gây timeout và khiến các request khác chịu độ trễ cao.

Giải pháp thực tế là **chia danh sách thao tác thành nhiều batch hữu hạn**. Mỗi batch có giới hạn về số lệnh, lượng byte dữ liệu và mức đồng thời; hoàn thành và tiêu thụ kết quả batch trước khi tiếp tục nhóm kế tiếp. Bài học tập trung vào cách triển khai chiến lược này với `RedisTemplate.executePipelined(...)` trong Spring Data Redis.

## 1. Pipeline giảm round-trip như thế nào?

Giả sử ứng dụng phải ghi 2.000 key vào Redis. Với cách gọi đồng bộ từng lệnh:

~~~text
Ứng dụng                        Redis
    | ---- SET k1 -------------> |
    | <--- phản hồi k1 ---------- |
    | ---- SET k2 -------------> |
    | <--- phản hồi k2 ---------- |
    |                ...         |
    | ---- SET k2000 ----------> |
    | <--- phản hồi k2000 ------- |
~~~

Mỗi lệnh phải chịu một vòng gửi yêu cầu và nhận phản hồi trước khi lệnh tiếp theo bắt đầu. Nếu thời gian round-trip của kết nối là 2 ms, riêng các lượt chờ mạng nối tiếp có thể đóng góp đáng kể vào thời gian tổng; còn có chi phí thực thi lệnh, serialization và lập lịch.

Khi dùng pipeline với mỗi nhóm 200 lệnh:

~~~text
Ứng dụng                        Redis
    | ---- SET k1 -------------> |
    | ---- SET k2 -------------> |
    | ---- SET k3 -------------> |
    |           ...              |
    | ---- SET k200 -----------> |
    | <--- các phản hồi -------- |
    |                            |
    | ---- SET k201 -----------> |
    |           ...              |
    | <--- các phản hồi -------- |
~~~

Trong thực tế driver có thể gom dữ liệu vào nhiều lần ghi socket, nhưng ứng dụng **không chờ phản hồi riêng biệt giữa từng lệnh của một pipeline**. Vì vậy, tổng chi phí round-trip theo nhóm thường thấp hơn gọi từng lệnh một.

Mô hình chi phí gần đúng:

~~~text
Gọi tuần tự:
    T ≈ N × (RTT + thời gian xử lý từng lệnh)

Pipeline chia batch:
    T ≈ số_batch × chi phí round-trip theo batch
        + tổng thời gian Redis xử lý lệnh
        + chi phí encode/decode + truyền dữ liệu + xử lý kết quả

số_batch = ceil(N / kích_thước_batch)
~~~

Đây là công thức trực giác, không phải cam kết tốc độ. Redis vẫn phải xử lý từng lệnh; payload lớn, mạng chậm, CPU Redis quá tải hoặc lượng phản hồi khổng lồ có thể khiến pipeline không còn lợi thế mong đợi.

## 2. Vì sao một pipeline quá lớn lại nguy hiểm?

Pipeline có ít nhất ba nơi tiêu thụ bộ nhớ:

| Nơi tiêu thụ | Tài nguyên được giữ | Rủi ro khi nhóm quá lớn |
| --- | --- | --- |
| **Client Java** | Đối tượng đầu vào, byte đã serialize, kết quả `List<Object>` trả về | Heap tăng, GC dày, `OutOfMemoryError` |
| **Redis server** | Bộ đệm nhận lệnh, bộ đệm phản hồi của kết nối, dữ liệu đang thực thi | Áp lực bộ nhớ, tăng độ trễ, có thể bị đóng kết nối theo giới hạn buffer |
| **Mạng/driver** | Byte chưa truyền hết và các phản hồi đang chờ đọc | Gửi/đọc chậm, timeout, kết nối bị chiếm lâu |

Ví dụ hai pipeline đều có 1.000 lệnh nhưng rất khác nhau:

- 1.000 lệnh `SET` ghi mỗi value khoảng vài chục byte.
- 1.000 lệnh `GET`, mỗi phản hồi chứa một value khoảng 1 MiB.

Trường hợp thứ hai có thể tạo ra lượng phản hồi xấp xỉ **1 GiB** chỉ tính payload, chưa kể object, metadata và bản sao tạm trong bộ nhớ Java. Vì thế chỉ giới hạn **số lệnh** là chưa đủ; phải quan tâm tới **kích thước dữ liệu** và hướng truyền.

Trong Spring Data Redis, `executePipelined(...)` trả về danh sách kết quả sau khi pipeline hoàn tất. Ứng dụng có thể vô tình giữ toàn bộ danh sách này trong bộ nhớ nếu gửi một nhóm lớn. Với truy vấn đọc nhiều value, đây thường là điểm nghẽn cần xem xét trước.

### Pipeline không phải transaction

Pipelining là tối ưu hóa cách truyền và thu hồi kết quả lệnh. Nó **không** tự bảo đảm tất cả lệnh thành công hoặc không lệnh nào chạy. Ví dụ nếu một batch có 100 lệnh `SET`, một lỗi mạng hoặc lỗi lệnh không có nghĩa 100 lệnh đã được rollback.

`MULTI/EXEC` là cơ chế giao dịch Redis khác; dùng nó cũng cần hiểu rõ xử lý lỗi và không có rollback tổng quát cho lỗi phát sinh trong lúc thực thi. Không thêm `MULTI` chỉ để làm pipeline “an toàn” khi nghiệp vụ không thật sự cần giao dịch.

## 3. Chọn hai giới hạn: số lệnh và dung lượng byte

Để bảo vệ cả client và Redis, nên kiểm tra hai ngân sách khi tạo batch:

1. **`maxCommands`**: số lệnh tối đa được đưa vào một lần `executePipelined`.
2. **`maxPayloadBytes`**: tổng kích thước key/value ước lượng tối đa của các lệnh trong nhóm.

Chẳng hạn, với workload ghi chuỗi nhỏ, có thể thử nghiệm ban đầu:

~~~text
maxCommands     = 250
maxPayloadBytes = 512 KiB
~~~

Các con số trên chỉ là **tham số khởi đầu để đo**, không phải mức tối ưu chung. Nếu mỗi value dài vài MiB, một lệnh đã vượt ngưỡng byte; nếu toàn bộ value rất nhỏ, giới hạn số lệnh thường đạt trước.

Cách quyết định khi thêm một lệnh mới:

~~~text
                       Lệnh tiếp theo
                              |
                              v
                     Ước lượng số byte
                              |
                              v
               Nhóm hiện tại có dữ liệu chưa?
                         /          \
                       Không         Có
                        |            |
                        |            v
                        |   Thêm lệnh sẽ vượt ngân sách?
                        |        /          \
                        |       Có          Không
                        |        |             |
                        |        v             |
                        |   Gửi nhóm hiện tại  |
                        |   và giải phóng bộ nhớ
                        |        |             |
                        +--------+-------------+
                                 |
                                 v
                         Thêm lệnh vào nhóm
                                 |
                                 v
                     Nhóm chạm ngưỡng giới hạn?
                            /        \
                           Có        Chưa
                            |          |
                            v          v
                         Gửi nhóm   Đọc lệnh tiếp
~~~

Giới hạn byte thường là **ước lượng payload** của key và value trước khi encode theo Redis protocol. Nó chưa tính overhead của RESP, command name, đầu vào của serializer, các object Java hay response. Với thao tác `GET`, kích thước value trả về không nhất thiết biết trước; phải sử dụng thống kê kích thước dữ liệu thực tế để định ngân sách cho pipeline đọc.

Nếu một lệnh đơn lẻ vượt `maxPayloadBytes`, có thể gửi riêng lệnh đó trong một batch một phần tử hoặc báo lỗi nếu hệ thống không cho phép value lớn. Không thể chia một lệnh `SET` thành các lệnh tùy ý mà vẫn giữ nguyên ngữ nghĩa.

## 4. Cách dùng `executePipelined` trong Spring Data Redis

Spring Data Redis cung cấp hai cách phổ biến:

- `RedisCallback`: sử dụng trực tiếp `RedisConnection` và các lệnh Redis ở mức thấp.
- `SessionCallback`: thao tác qua API `RedisOperations` với serializer của template và một ngữ cảnh connection được giữ trong callback.

Điều kiện quan trọng là các lệnh của **một batch** phải được gửi trong phạm vi callback mà `executePipelined` quản lý. Không tự mở pipeline bằng một lệnh ở ngoài rồi tiếp tục ở một connection khác.

Ví dụ ngắn với `StringRedisTemplate`:

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SimplePipelineExample {

    private final StringRedisTemplate redis;

    public SimplePipelineExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeOneBatch() {
        return redis.executePipelined((SessionCallback<Object>) operations -> {
            operations.opsForValue().set("demo:a", "one");
            operations.opsForValue().set("demo:b", "two");
            operations.opsForValue().set("demo:c", "three");
            return null;
        });
    }
}
~~~

Phương thức `executePipelined` trả về `List<Object>` theo thứ tự các lệnh đã gửi trong pipeline. Giá trị trả về **trực tiếp từ callback phải là `null`**; kết quả lệnh được lấy từ danh sách mà Spring Data Redis trả về sau khi đóng pipeline.

Trong callback, không được dựa vào kết quả trả về của `operations.opsForValue().get(...)` để rẽ nhánh nghiệp vụ như thể đó là giá trị Redis thật. Khi đang pipeline, kết quả lệnh thường chưa sẵn sàng; nó được thu hồi ở cuối pipeline. Nếu cần kiểm tra giá trị trước khi quyết định lệnh tiếp theo, hãy chia thành **hai pha**: đọc kết quả batch đầu, xử lý ở Java, rồi mới phát batch tiếp.

Trong một ứng dụng có `RedisSerializer` tùy biến, `SessionCallback` giúp tránh việc tự chuyển key/value thành bytes sai định dạng. Ngược lại, `RedisCallback` có ích khi cần trực tiếp kiểm soát byte và lệnh mức thấp.

## 5. Ví dụ hoàn chỉnh: bộ ghi pipeline chia batch theo số lệnh và byte

Giả sử ứng dụng nhận một luồng `Entry(key, value)` cần ghi vào Redis. Mục tiêu là xử lý được một nguồn dữ liệu rất lớn mà **không phải chuyển tất cả bản ghi thành một `List` duy nhất**.

Đoạn mã dưới dùng Java 21 và Spring Data Redis. `StringRedisTemplate` mặc định mã hóa key/value bằng UTF-8; ví dụ sử dụng chính quy ước đó để ước lượng số byte và ghi raw bytes qua connection.

~~~java
package com.example.redis.pipeline;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class BatchingRedisWriter {

    private static final int MAX_COMMANDS = 250;
    private static final long MAX_PAYLOAD_BYTES = 512L * 1024;

    private final StringRedisTemplate redis;

    public BatchingRedisWriter(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public record Entry(String key, String value) {
    }

    public record WriteStats(int commands, int batches) {
    }

    private record EncodedEntry(byte[] key, byte[] value) {
        long payloadBytes() {
            return (long) key.length + value.length;
        }
    }

    public WriteStats write(Iterator<Entry> source) {
        Objects.requireNonNull(source);

        List<EncodedEntry> batch = new ArrayList<>(MAX_COMMANDS);
        long pendingBytes = 0;
        int commands = 0;
        int batches = 0;

        while (source.hasNext()) {
            Entry entry = Objects.requireNonNull(source.next());
            byte[] key = Objects.requireNonNull(entry.key())
                .getBytes(StandardCharsets.UTF_8);
            byte[] value = Objects.requireNonNull(entry.value())
                .getBytes(StandardCharsets.UTF_8);
            EncodedEntry next = new EncodedEntry(key, value);
            long nextBytes = next.payloadBytes();

            // Gửi nhóm cũ trước khi thêm phần tử làm vượt giới hạn.
            if (!batch.isEmpty()
                    && (batch.size() >= MAX_COMMANDS
                    || pendingBytes + nextBytes > MAX_PAYLOAD_BYTES)) {
                flush(batch);
                batches++;
                batch.clear();
                pendingBytes = 0;
            }

            batch.add(next);
            pendingBytes += nextBytes;
            commands++;

            // Trường hợp nhóm đạt đúng ngưỡng hoặc một lệnh rất lớn.
            if (batch.size() >= MAX_COMMANDS
                    || pendingBytes >= MAX_PAYLOAD_BYTES) {
                flush(batch);
                batches++;
                batch.clear();
                pendingBytes = 0;
            }
        }

        // Gửi các phần tử còn lại khi nguồn đã hết.
        if (!batch.isEmpty()) {
            flush(batch);
            batches++;
        }

        return new WriteStats(commands, batches);
    }

    private void flush(List<EncodedEntry> batch) {
        List<Object> replies =
            redis.executePipelined((RedisCallback<Object>) connection -> {
                for (EncodedEntry entry : batch) {
                    connection.stringCommands().set(
                        entry.key(), entry.value()
                    );
                }
                return null;
            });

        if (replies.size() != batch.size()) {
            throw new IllegalStateException(
                "Unexpected pipeline reply count: " + replies.size()
                + " for " + batch.size() + " commands"
            );
        }

        // Trong ứng dụng thật, còn phải kiểm tra lỗi/giá trị phản hồi
        // theo từng loại lệnh; đúng số lượng phản hồi không bảo đảm
        // mọi thao tác đã thành công.
    }
}
~~~

Cách sử dụng:

~~~java
List<BatchingRedisWriter.Entry> smallInput = List.of(
    new BatchingRedisWriter.Entry("demo:batch:1", "A"),
    new BatchingRedisWriter.Entry("demo:batch:2", "B"),
    new BatchingRedisWriter.Entry("demo:batch:3", "C")
);

BatchingRedisWriter writer = new BatchingRedisWriter(redisTemplate);
BatchingRedisWriter.WriteStats stats =
    writer.write(smallInput.iterator());

System.out.println(stats.commands()); // 3
System.out.println(stats.batches());  // 1
~~~

`redisTemplate` trong ví dụ là một `StringRedisTemplate` được Spring quản lý. Với dữ liệu thực tế, có thể truyền iterator đọc từ file, API hoặc cursor của một nguồn khác thay vì tạo toàn bộ `List` trước.

### Luồng xử lý và giới hạn bộ nhớ

~~~text
      Iterator<Entry> từ nguồn đầu vào
                     |
                     v
            Encode key/value UTF-8
                     |
                     v
       List<EncodedEntry> có giới hạn
          250 lệnh hoặc 512 KiB
                     |
                     v
         executePipelined(batch)
                     |
                     v
          Nhận và xử lý phản hồi
                     |
                     v
           clear() vùng đệm
                     |
                     v
              Nhóm kế tiếp
~~~

Đoạn mã cố tình **gửi các batch lần lượt**. Khi `executePipelined` chưa trả về, vòng lặp không bắt đầu gửi batch mới. Điều này tạo một hình thức **backpressure tự nhiên**: nguồn dữ liệu không được tiêu thụ nhanh hơn mức pipeline hiện tại có thể hoàn tất. Chỉ một nhóm dữ liệu và danh sách kết quả của nhóm đó cần hiện diện tại một thời điểm trong phương thức.

Lưu ý các ranh giới của ví dụ:

- `MAX_COMMANDS` và `MAX_PAYLOAD_BYTES` là giá trị để bắt đầu đo hiệu năng, không phải tối ưu mặc định.
- `pendingBytes` chỉ đếm key và value đã encode; không đếm overhead của Redis protocol, Java heap hay buffer của driver.
- Một phần tử quá lớn có thể được gửi riêng trong một batch một lệnh; nếu cần giới hạn cứng cho từng request, bổ sung validation đầu vào.
- Hàm `write` trả về **số lệnh đã gửi theo đường bình thường** và số batch đã thực hiện, không phải bằng chứng của một commit nguyên tử. Nếu một pipeline báo lỗi sau khi một số lệnh đã tới Redis, cần đối soát trạng thái thực tế.
- Với `StringRedisTemplate` được cấu hình serializer khác UTF-8 mặc định, phải đồng bộ cách encode trong `RedisCallback` với serializer thực tế hoặc chuyển sang `SessionCallback`.
- Với lệnh đọc, cần giới hạn cả **kích thước phản hồi ước tính**, vì byte dữ liệu trả về có thể lớn hơn nhiều kích thước key gửi đi.

## 6. Phân nhóm thao tác GET: bộ nhớ phản hồi quan trọng hơn payload yêu cầu

Đối với `SET` giá trị nhỏ, phản hồi của mỗi lệnh thường nhỏ. Đối với `GET`, một phản hồi có thể chứa toàn bộ value lớn.

Ví dụ đọc 10.000 key bằng một pipeline:

~~~java
List<Object> results =
    redis.executePipelined((SessionCallback<Object>) operations -> {
        for (String key : keys) {
            operations.opsForValue().get(key);
        }
        return null;
    });
~~~

Nếu `keys` chứa 10.000 key và mỗi value dài 100 KiB, riêng payload kết quả có thể gần một GiB. Mỗi giá trị có thể còn được giữ dưới dạng byte array, `String` và các object trung gian trong quá trình decode; lượng heap thực tế có thể lớn hơn đáng kể.

Để giảm đỉnh bộ nhớ, chia danh sách key thành các nhóm nhỏ, xử lý kết quả từng nhóm, rồi bỏ tham chiếu tới kết quả trước khi chuyển nhóm:

~~~java
public void readInChunks(
        List<String> keys,
        StringRedisTemplate redis,
        java.util.function.BiConsumer<String, String> consumer) {

    final int chunkSize = 40; // Điều chỉnh theo kích thước value thực tế.

    for (int start = 0; start < keys.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, keys.size());
        List<String> chunk = keys.subList(start, end);

        List<Object> values =
            redis.executePipelined((SessionCallback<Object>) operations -> {
                for (String key : chunk) {
                    operations.opsForValue().get(key);
                }
                return null;
            });

        // Kết quả pipeline theo thứ tự lệnh đã gửi.
        for (int i = 0; i < chunk.size(); i++) {
            String value = (String) values.get(i);
            consumer.accept(chunk.get(i), value);
        }

        // Không giữ 'values' trong một bộ sưu tập kết quả khổng lồ.
    }
}
~~~

Ví dụ trên phù hợp khi `StringRedisTemplate` xử lý giá trị chuỗi và mỗi lệnh `GET` trả về `String` hoặc `null` khi key không tồn tại. Với serializer, kiểu dữ liệu và command khác, kiểu phần tử trong `List<Object>` có thể khác; ứng dụng phải diễn giải phản hồi theo lệnh đã phát.

`chunkSize = 40` chỉ là một ví dụ. Nếu mỗi value nhỏ 1 KiB, có thể thử nhóm lớn hơn; nếu mỗi value vài MiB, thậm chí nhóm 40 phần tử cũng có thể quá lớn. Với response có kích thước khó đoán, đặt giới hạn dữ liệu ở tầng mô hình và chọn độ lớn batch thận trọng.

### Vì sao phải xử lý ngay sau mỗi batch?

Giả sử mã đọc nhiều nhóm nhưng lại thêm toàn bộ phản hồi vào một `List<Object> allResults`, bộ nhớ Java sẽ vẫn tăng tới quy mô **toàn bộ dữ liệu**, dù pipeline đã chia nhỏ. Chia batch chỉ thực sự giảm đỉnh bộ nhớ khi vòng đời kết quả được giữ ngắn: xử lý, ghi sang đích hoặc tổng hợp một chỉ số nhỏ, rồi giải phóng tham chiếu.

Nếu `consumer` tự tích trữ mọi value ở nơi khác, bộ nhớ cuối cùng vẫn tăng. Vì thế không chỉ pipeline mà cả **đích tiêu thụ dữ liệu** phải có chiến lược streaming/bounded buffering.

## 7. Batch size ảnh hưởng độ trễ ra sao?

Kích thước nhóm là một sự đánh đổi:

| Batch | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| Quá nhỏ, ví dụ 1–5 lệnh | Mỗi batch ít chiếm bộ nhớ | Gần giống gọi từng lệnh; lợi ích giảm round-trip thấp |
| Vừa phải, theo phép đo workload | Giảm lượt mạng nhưng vẫn kiểm soát response và thời gian xử lý | Phải theo dõi và điều chỉnh theo tải |
| Rất lớn, hàng chục nghìn lệnh hoặc hơn | Ít lần gọi pipeline ở phía ứng dụng | Đỉnh bộ nhớ, response buffer, timeout, fairness và độ trễ batch có thể xấu |

**Thông lượng** và **độ trễ** không phải một đại lượng:

- *Throughput*: số lệnh/bản ghi hoàn thành mỗi giây.
- *Batch latency*: thời gian từ lúc bắt đầu gửi một batch đến lúc đã nhận xong kết quả.
- *Per-item waiting time*: một item có thể phải đợi những item khác cùng batch hoàn thành trước khi được xử lý ở ứng dụng.
- *Tail latency*: các percentile cao, chẳng hạn p95/p99, cho thấy các batch chậm bất thường.

Một batch lớn đôi khi làm tăng throughput nhưng cũng làm một request tương tác phải chờ lâu hơn. Nếu Redis vừa phục vụ background import vừa phục vụ API online, không nên để importer liên tục gửi các pipeline quá lớn rồi chiếm tài nguyên của Redis.

### Không có một con số tối ưu cho mọi hệ thống

Batch size phụ thuộc:

- Độ trễ mạng và khoảng cách từ ứng dụng đến Redis.
- Kích thước key/value, tỷ lệ `GET` so với `SET`, và lượng phản hồi.
- Chi phí serialize/deserialize dữ liệu trên JVM.
- CPU, RAM, buffer và cấu hình của Redis server.
- Driver Redis (Lettuce/Jedis), pool, số lượng connection và mức đồng thời.
- Redis standalone, Sentinel hay Cluster; routing qua các node có thể thay đổi chi phí.
- Số lượng request online đồng thời và mức độ ưu tiên của tác vụ nền.

Nên chạy benchmark với chính kiểu dữ liệu, mạng và cấu hình triển khai dự kiến thay vì lấy một giá trị “mặc định tốt nhất” từ ví dụ của người khác.

## 8. Kiểm soát số pipeline đồng thời

Giới hạn số lệnh/batch vẫn chưa đủ nếu ứng dụng cho phép 100 request cùng tạo 100 pipeline lớn. Khi đó nhiều batch đang tồn tại ở các connection, buffer và vùng heap khác nhau.

Có hai lớp giới hạn cần kết hợp:

1. **Độ lớn mỗi batch**, ví dụ `maxCommands` và `maxPayloadBytes`.
2. **Số batch đang chạy đồng thời**, ví dụ số worker hoặc semaphore cho tác vụ import.

Nếu dùng hàng đợi nền có 4 worker, mỗi worker gửi tuần tự từng batch, số pipeline đang chạy có thể được giới hạn bởi số worker đó. Với HTTP endpoint có thể nhận hàng trăm yêu cầu, cần giới hạn concurrency rõ ràng khi một yêu cầu đòi gửi khối lượng lớn.

Minh họa bằng `Semaphore`:

~~~java
import java.util.concurrent.Semaphore;

public final class LimitedImportService {
    private final BatchingRedisWriter writer;
    private final Semaphore permits = new Semaphore(4);

    public LimitedImportService(BatchingRedisWriter writer) {
        this.writer = writer;
    }

    public BatchingRedisWriter.WriteStats importEntries(
            java.util.Iterator<BatchingRedisWriter.Entry> entries)
            throws InterruptedException {

        permits.acquire();
        try {
            return writer.write(entries);
        } finally {
            permits.release();
        }
    }
}
~~~

Ví dụ này cho phép tối đa bốn lượt `importEntries(...)` chạy cùng lúc **trong một instance JVM**. Nếu dịch vụ có nhiều pod hoặc instance, mỗi instance giữ một `Semaphore` riêng: muốn giới hạn toàn hệ thống phải dùng cơ chế điều tiết ở lớp phù hợp. Việc chờ permit cũng cần timeout hoặc ngữ nghĩa huỷ request nếu đường gọi có SLA nghiêm ngặt.

Semaphore giới hạn **số luồng import**, không trực tiếp chứng minh số connection hay byte đang truyền; số thực tế còn phụ thuộc driver/pool và các thao tác Redis khác trong ứng dụng.

## 9. Flush, network buffering và xử lý phản hồi

Ở mức thấp, quá trình pipeline gồm: mở chế độ pipeline trên connection, gửi một chuỗi command, flush byte ra network theo cơ chế driver, đọc kết quả và đóng pipeline. `executePipelined` của Spring Data Redis quản lý vòng đời đó cho mỗi callback.

Trong một số cấu hình Lettuce, có thể điều chỉnh chính sách flush trong pipeline để giảm số lần ghi socket. Tuy nhiên, việc flush phụ thuộc phiên bản Spring Data Redis, Lettuce và loại kết nối. Đừng giả định một tùy chọn flush cụ thể luôn có mặt hoặc có cùng tác động trong mọi driver.

**Flush policy và batch size giải quyết hai vấn đề khác nhau:**

- **Flush policy** quyết định lúc nào driver đẩy byte xuống network khi pipeline đang mở.
- **Batch size** quyết định tổng số lệnh/byte được giữ trong một đơn vị công việc của ứng dụng.

Ngay cả khi driver đã tối ưu flush, một pipeline có quá nhiều lệnh `GET` vẫn cần nhận lượng phản hồi tương ứng; byte và bộ nhớ không biến mất chỉ nhờ ít lần flush.

Đối với phản hồi lỗi, `executePipelined` có thể ném exception từ driver/template hoặc trả những kết quả lệnh cần được diễn giải theo command và cấu hình. Một pipeline trả đủ số lượng phần tử **không phải bằng chứng** tất cả lệnh đều đã thành công. Nếu nghiệp vụ đòi xác nhận từng thao tác, hãy kiểm tra kết quả tương ứng và có chiến lược xử lý lỗi riêng.

## 10. Xử lý lỗi và retry theo từng batch

Chia batch tạo một ranh giới thuận tiện để ghi log, ghi checkpoint và retry. Nhưng pipeline không phải transaction, nên một batch thất bại có thể đã có **một phần lệnh được Redis xử lý**.

Ví dụ:

~~~text
Batch 1 (250 SET) → trả kết quả đầy đủ
Batch 2 (250 SET) → timeout phía client sau khi gửi lệnh
Batch 3            → chưa gửi
~~~

Với Batch 2, ứng dụng **không thể tự kết luận** rằng Redis chưa ghi key nào. Server có thể đã xử lý một số hoặc tất cả lệnh trước khi phản hồi bị mất. Nếu thử lại toàn batch, tính an toàn phụ thuộc loại thao tác:

| Thao tác | Retry sau kết quả không chắc chắn | Giải thích |
| --- | --- | --- |
| `SET key value` với cùng value | Thường có thể retry nếu không phá trạng thái mới hơn | Ghi lại cùng giá trị có tính idempotent về value, nhưng có thể ảnh hưởng TTL hoặc ghi đè dữ liệu đồng thời |
| `DEL key` | Thường an toàn khi mục tiêu chỉ là key không còn tồn tại | Kết quả đếm số key đã xóa có thể khác giữa các lần |
| `INCR` / `DECR` | Không an toàn nếu retry mù | Có thể tăng/giảm hai lần |
| `LPUSH` / `RPUSH` | Không an toàn nếu không có deduplication | Có thể thêm trùng phần tử |
| `SADD key member` | Idempotent theo membership của Set | Nhưng kết quả “mới thêm hay đã có” có thể khác |
| `SET` kèm TTL | Cần cân nhắc lại mốc hết hạn khi retry | Ghi lại có thể làm TTL bắt đầu tính lại |

Nếu cần đồng bộ một tập dữ liệu lớn, nên thiết kế:

- **ID ổn định** cho từng bản ghi, tránh sinh ID mới ở mỗi lần thử.
- **Checkpoint theo batch** chỉ sau khi có bằng chứng phù hợp về hoàn tất.
- **Retry có giới hạn**, exponential backoff và ghi nhận lỗi có thể điều tra.
- **Đối soát trạng thái** với thao tác có kết quả không chắc chắn, nhất là cập nhật số đếm.
- **Tính idempotent** ở cấp nghiệp vụ, có thể dùng transaction/script hoặc cơ chế nhận diện yêu cầu lặp lại khi cần.

Không nên xem `List<Object>` nhận được từ pipeline là biên bản commit nhiều lệnh nguyên tử. Hãy mô tả chính xác loại bảo đảm mà từng thao tác cung cấp.

## 11. Pipeline và thời gian sống (TTL)

Nếu giá trị được lưu với TTL, cần đảm bảo mỗi lệnh có ngữ nghĩa hết hạn đúng. Hai lệnh:

~~~redis
SET session:42 payload
EXPIRE session:42 60
~~~

được đặt liên tiếp trong cùng pipeline **không tạo thành một thao tác nguyên tử**. Nếu ứng dụng gặp lỗi hoặc kết nối gián đoạn sau khi `SET` tới Redis nhưng trước khi `EXPIRE` được thực thi, key có thể tồn tại mà không có TTL mong muốn.

Với nghiệp vụ cần dữ liệu và TTL được thiết lập cùng lúc, ưu tiên một lệnh Redis hỗ trợ expiration:

~~~redis
SET session:42 payload EX 60
~~~

Trong API Spring Data Redis cấp cao, có thể dùng:

~~~java
redis.opsForValue().set(
    "session:42",
    "payload",
    java.time.Duration.ofSeconds(60)
);
~~~

Khi thực hiện bằng `SessionCallback` trong pipeline, có thể xếp các thao tác `opsForValue().set(key, value, duration)` để mỗi key được ghi cùng thời hạn:

~~~java
redis.executePipelined((SessionCallback<Object>) operations -> {
    operations.opsForValue().set(
        "session:43", "payload-43",
        java.time.Duration.ofSeconds(60)
    );
    operations.opsForValue().set(
        "session:44", "payload-44",
        java.time.Duration.ofSeconds(60)
    );
    return null;
});
~~~

Mỗi lệnh `SET` có TTL của riêng nó, còn cả batch vẫn không phải một giao dịch. Khi retry, thời điểm hết hạn có thể thay đổi vì lệnh ghi lại sẽ thiết lập TTL mới; điều này phải phù hợp với yêu cầu nghiệp vụ.

## 12. Thực hành đo đạc trước khi chọn batch size

Thay vì tăng kích thước batch đến khi thấy throughput cao, hãy so sánh nhiều cấu hình theo **cùng một workload** và quan sát cả client lẫn Redis.

Ví dụ kế hoạch thí nghiệm:

| Lượt | Giới hạn lệnh | Giới hạn payload | Số batch đồng thời |
| --- | ---: | ---: | ---: |
| A | 25 | 128 KiB | 1 |
| B | 100 | 256 KiB | 1 |
| C | 250 | 512 KiB | 1 |
| D | 500 | 1 MiB | 1 |
| E | 250 | 512 KiB | 4 |

Các số này dùng làm **kịch bản benchmark**, không phải khuyến nghị cố định. Mỗi lượt nên dùng cùng kiểu command, phân bố kích thước key/value, mức đồng thời API và thời gian đo đủ ổn định.

Các chỉ số đáng theo dõi:

| Chỉ số | Vì sao cần |
| --- | --- |
| Commands/second và records/second | Đo throughput thực |
| Batch latency p50/p95/p99 | Phát hiện nhóm chậm bất thường |
| JVM heap dùng trước/sau batch và GC pause | Quan sát bộ nhớ và chi phí object |
| Kích thước payload gửi/nhận mỗi batch | Đối chiếu với budget byte |
| Redis CPU và memory | Kiểm tra tải server |
| Redis client input/output buffers | Phát hiện accumulation khi client không đọc kịp |
| Timeout, connection reset, retry count | Phát hiện cấu hình nhóm vượt khả năng hệ thống |
| Độ trễ của API online cùng Redis | Kiểm tra tác động của background pipeline lên workload khác |

Trên Redis, `INFO` và `CLIENT LIST` cung cấp dữ liệu chẩn đoán hữu ích. Các trường trong `CLIENT LIST` có thể bao gồm `qbuf` (query buffer) và `omem` (bộ nhớ output buffer) tùy phiên bản. Chỉ số heap của ứng dụng nên lấy từ Micrometer/JVM metrics hoặc profiler thích hợp, thay vì chỉ suy ra từ kích thước batch.

Ví dụ một phép đo thời gian ở tầng Java:

~~~java
long start = System.nanoTime();
List<Object> replies = redis.executePipelined(
    (SessionCallback<Object>) operations -> {
        for (String key : keysInOneBatch) {
            operations.opsForValue().get(key);
        }
        return null;
    }
);
long elapsedNanos = System.nanoTime() - start;

System.out.printf(
    "commands=%d, replies=%d, batchMs=%.2f%n",
    keysInOneBatch.size(),
    replies.size(),
    elapsedNanos / 1_000_000.0
);
~~~

Đây là thời gian **phía ứng dụng quan sát**, bao gồm callback, gửi lệnh, nhận và chuyển đổi phản hồi; nó không phải số đo riêng của Redis server. Để có p95/p99, ghi nhiều lần đo vào metrics/histogram thay vì kết luận từ một lượt chạy.

Nếu batch lớn làm tăng throughput nhưng p99 latency của API online hoặc mức dùng bộ nhớ vượt ngân sách, nên giảm batch size, giảm số luồng pipeline hoặc tách tài nguyên phục vụ tác vụ nền.

## 13. Kiểm thử tích hợp với Redis thật

Mock `RedisTemplate` chỉ chứng minh callback được gọi. Để xem batch thực sự ghi đủ dữ liệu và kết nối hoàn tất sau `executePipelined`, cần một Redis test thật. Ví dụ dùng JUnit 5, Spring Boot, AssertJ và Testcontainers.

Dependency minh họa (Gradle Groovy khi phiên bản được quản lý bằng Spring Boot BOM/plugin):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Kiểm thử dưới tạo 620 key, đủ để đi qua nhiều nhóm theo giới hạn 250 lệnh:

~~~java
package com.example.redis.pipeline;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = BatchingRedisWriterTest.TestApp.class)
class BatchingRedisWriterTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port", () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void splitsWritesIntoBoundedPipelines() {
        String prefix = "it:pipeline:" + UUID.randomUUID() + ":";
        List<BatchingRedisWriter.Entry> entries = new ArrayList<>();

        for (int i = 0; i < 620; i++) {
            entries.add(new BatchingRedisWriter.Entry(
                prefix + i, "value-" + i
            ));
        }

        BatchingRedisWriter writer = new BatchingRedisWriter(redis);

        try {
            BatchingRedisWriter.WriteStats stats =
                writer.write(entries.iterator());

            assertThat(stats.commands()).isEqualTo(620);
            assertThat(stats.batches()).isEqualTo(3);

            for (int i = 0; i < 620; i++) {
                assertThat(redis.opsForValue().get(prefix + i))
                    .isEqualTo("value-" + i);
            }
        } finally {
            // Dọn đúng key do test tạo; tránh FLUSHALL/FLUSHDB.
            for (int i = 0; i < 620; i++) {
                redis.delete(prefix + i);
            }
        }
    }
}
~~~

Trong dữ liệu thử nghiệm mỗi key/value chỉ có vài chục byte, nên ngưỡng 250 lệnh đạt trước ngưỡng 512 KiB: 620 lệnh được gửi qua ba nhóm có kích thước 250, 250 và 120.

Kiểm thử cần Docker hoặc môi trường container tương thích. Với dự án đã có Redis dành riêng cho integration test, có thể dùng hạ tầng đó. Trường hợp cần kiểm thử giới hạn byte, tạo value có kích thước phù hợp để ép batch đóng vì `MAX_PAYLOAD_BYTES` trước khi chạm `MAX_COMMANDS`.

Kiểm thử xác nhận dữ liệu cuối cùng đọc được từ Redis và số batch thống kê theo thuật toán chia nhóm. Nó không thay thế benchmark về throughput, memory, tail latency hoặc tác động tới workload khác.

## 14. Những lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JVM tăng heap đột biến khi pipeline `GET` | Tạo quá nhiều phản hồi lớn trong một `List<Object>` | Giảm batch; xử lý và giải phóng phản hồi theo nhóm |
| Đã chia batch nhưng heap vẫn tăng | Đầu vào hoặc `allResults` được giữ toàn bộ trong bộ nhớ | Dùng iterator/stream và consumer không tích lũy không giới hạn |
| Pipeline nhanh hơn nhưng p99 API xấu | Background pipeline quá lớn hoặc quá nhiều pipeline đồng thời | Giảm batch/concurrency; đo latency workload chung |
| Pipeline nhỏ không hiệu quả hơn gọi lẻ | Quá nhiều lần round-trip giữa các batch | Tăng nhóm dần theo phép đo |
| Có 200 lệnh nhưng payload vẫn quá lớn | Chỉ giới hạn command count | Thêm giới hạn byte và xét độ lớn response |
| Timeout sau khi gửi batch rồi retry gây đếm hai lần | Lệnh không idempotent đã có thể thực thi | Đối soát, deduplicate hoặc thiết kế retry có bảo đảm |
| `SET` thành công nhưng key không có TTL | Chia `SET` và `EXPIRE` thành hai lệnh không nguyên tử | Dùng `SET` kèm expiration trong một lệnh |
| Kết quả `GET` trong callback là `null` | Lệnh vẫn đang pipeline | Đọc kết quả sau `executePipelined` |
| Kết quả lệnh bị gán sai key | Không giữ thứ tự ánh xạ giữa command và response | Duy trì danh sách input của mỗi batch để đối chiếu theo index |
| Một batch chỉ có 1 lệnh cực lớn làm vượt byte budget | Dữ liệu đơn lẻ quá lớn | Đặt max-value riêng hoặc gửi đơn lẻ theo chính sách |
| Connection bị reset khi tải cao | Output buffer/memory/timeout hoặc lỗi mạng, tùy nguyên nhân | Kiểm tra Redis/client metrics; giảm pressure; xử lý retry |
| Pipeline không hoạt động như mong đợi trên Cluster | Routing/connection tới các node khác nhau | Kiểm tra driver, topology, hash slot và mô hình gửi lệnh |

## 15. Lưu ý với Redis Cluster và nhiều loại lệnh

Redis Cluster phân phối key qua nhiều hash slot và node. Với các lệnh một key như `GET` và `SET`, driver hỗ trợ cluster có thể phải route lệnh tới những node phù hợp. Một pipeline gửi tới các key nằm ở nhiều node không nhất thiết có cùng mô hình truyền và nhận kết quả như pipeline trên một Redis server đơn lẻ.

Không nên giả định thứ tự lệnh giữa **các node khác nhau** tạo ra một transaction liên node. Những lệnh đa key như `MGET`, `MSET` hoặc các thao tác tập hợp có thể chịu giới hạn các key phải nằm cùng hash slot, tùy lệnh/topology. Với các workload cluster lớn, cần kiểm chứng cụ thể khả năng pipelining của Redis driver và cách dữ liệu được phân phối.

Một batch gồm hỗn hợp `GET`, `SET`, `INCR` và `DEL` cũng trả về các kiểu kết quả khác nhau. `List<Object>` phải được giải mã theo **đúng thứ tự command**, không được cast toàn bộ phần tử sang `String` chỉ vì template được định kiểu `StringRedisTemplate`.

Nếu dữ liệu cần xử lý bằng các lệnh có ngữ nghĩa nguyên tử riêng, hãy dùng lệnh thích hợp. Ví dụ tăng số đếm cần `INCR` thay vì đọc `GET` rồi ghi `SET` trong cùng pipeline: pipeline không bảo vệ phép read-modify-write khỏi thay đổi của client khác.

## 16. Cách đưa batching vào dịch vụ thực tế

Một quy trình import hoặc đồng bộ dữ liệu lớn thường có ba phần:

~~~text
       Nguồn dữ liệu
       File / DB / API
             |
             v
       Iterator/stream
             |
             v
       Validate + serialize
             |
             v
       Bộ gom batch hữu hạn
       count + payload bytes
             |
             v
       executePipelined
             |
             v
       Đọc kết quả + metrics
             |
             +------> Lỗi: log/checkpoint/retry có kiểm soát
             |
             v
       Giải phóng bộ nhớ nhóm
             |
             v
       Lặp tới hết nguồn
~~~

Nên xác định rõ:

- **Mục tiêu độ trễ:** batch import chạy nền hay lệnh trực tiếp phục vụ HTTP request?
- **Ngân sách bộ nhớ:** Java heap tối đa, kích thước response lớn nhất và buffer Redis chịu được.
- **Ngân sách đồng thời:** bao nhiêu pipeline được phép tồn tại trong một JVM và toàn hệ thống?
- **Ranh giới lỗi:** retry cả batch hay từng bản ghi? Lệnh nào idempotent?
- **Định dạng dữ liệu:** serializer, TTL, encoding và định danh key dùng thống nhất?
- **Đo đạc:** throughput, p95/p99 latency, heap/GC, Redis CPU/buffer, lỗi và retry.

Nếu yêu cầu ingest chỉ vài chục lệnh không thường xuyên, dùng `RedisTemplate` bình thường có thể đủ đơn giản. Pipelining phù hợp nhất khi số lượng lệnh độc lập đủ lớn và network round-trip là chi phí đáng kể; kết quả benchmark mới quyết định một batch nên lớn đến đâu.

## 17. Tổng kết

Pipelining trong Spring Data Redis giúp giảm thời gian chờ phản hồi cho từng lệnh, nhưng một pipeline vô hạn sẽ chuyển áp lực sang **bộ nhớ client, output buffer của Redis, mạng và thời gian xử lý toàn batch**.

Chiến lược bền vững là chia công việc thành những batch có giới hạn theo **số lệnh, số byte và concurrency**, tiêu thụ phản hồi ngay khi từng batch hoàn tất và không tích lũy toàn bộ kết quả trong Java. Với dữ liệu đọc lớn, ngân sách phản hồi quan trọng hơn số key đầu vào. Với dữ liệu ghi, cần xét retry, tính idempotent và những lệnh phải có TTL nguyên tử.

`RedisTemplate.executePipelined(...)` là công cụ truyền lệnh theo nhóm; nó không cung cấp rollback cho cả batch hay một cơ chế tối ưu batch size tự động cho mọi workload. Hãy đo throughput cùng tail latency, heap và Redis buffer, sau đó điều chỉnh nhóm theo yêu cầu vận hành thực tế.
