# Đo hiệu quả pipeline bằng khối lượng dữ liệu thực tế

## 1. Tại sao benchmark pipeline phải dùng dữ liệu giống thực tế?

Trong một ứng dụng Spring Boot dùng Redis để lưu cache, giả sử tác vụ nền phải đọc 10.000 khóa. Cách đọc tuần tự thường là:

```java
for (String key : keys) {
    String value = redisTemplate.opsForValue().get(key);
    process(value);
}
```

Mỗi lần gọi `GET`, ứng dụng chờ Redis trả kết quả rồi mới gửi lệnh tiếp theo. **Redis pipelining** cho phép gửi nhiều lệnh mà không phải chờ phản hồi của từng lệnh:

```text
Không pipeline                         Có pipeline

App                    Redis           App                    Redis
 | ---- GET k1 --------> |              | ---- GET k1 --------> |
 | <--- value1 --------- |              | ---- GET k2 --------> |
 | ---- GET k2 --------> |              | ---- GET k3 --------> |
 | <--- value2 --------- |              | <--- value1 --------- |
 | ---- GET k3 --------> |              | <--- value2 --------- |
 | <--- value3 --------- |              | <--- value3 --------- |
```

Nếu đo trên 10 khóa, mỗi giá trị chỉ 5 byte, pipeline có thể cho mức tăng tốc rất cao vì phần lớn thời gian tuần tự là chờ mạng. Nhưng điều đó **không chứng minh** pipeline vẫn tăng tốc tương tự khi ứng dụng phải nhận 20.000 giá trị JSON, mỗi giá trị 64 KiB, đồng thời Redis phục vụ những request khác.

Khi lượng dữ liệu tăng, chi phí chuyển từ các lượt chờ mạng sang những yếu tố khác: băng thông, CPU Redis, bộ nhớ nhận phản hồi, giải mã JSON, cấp phát đối tượng Java, GC và tranh chấp kết nối.

Vì vậy, để **đo hiệu quả pipeline bằng khối lượng dữ liệu thực tế**, phải mô tả đúng công việc, đo đủ kết quả và chọn kích thước lô từ các số đo, thay vì mặc định “pipeline càng lớn càng nhanh”.

## 2. Pipeline giảm được chi phí nào?

### 2.1. Chi phí của từng lượt gửi lệnh

Một lệnh Redis có nhiều thành phần thời gian:

- Chuyển lệnh từ Java thành byte theo serializer.
- Gửi lệnh qua TCP/TLS đến Redis.
- Redis phân tích cú pháp và thực thi lệnh.
- Truyền phản hồi qua mạng.
- Redis client đọc phản hồi, giải mã và tạo đối tượng Java.
- Ứng dụng xử lý hoặc lưu giữ kết quả.

Với nhiều lệnh nhỏ gọi **tuần tự**, thời gian chờ một lượt trao đổi mạng (*round-trip time*, RTT) có thể chiếm phần lớn tổng thời gian. Pipeline gửi nhiều lệnh liên tiếp, giúp giảm số lần chờ trước khi tiếp tục gửi.

Một cách nhìn gần đúng:

```text
Không pipeline:
  T ≈ N × RTT + thời_gian_xử_lý + thời_gian_truyền + thời_gian_giải_mã

Pipeline theo lô B lệnh:
  T ≈ ceil(N / B) × RTT
      + thời_gian_xử_lý
      + thời_gian_truyền
      + thời_gian_giải_mã
      + chi_phí_bộ_đệm
```

Đây chỉ là **mô hình định hướng**, không phải công thức dự báo chính xác. Mạng, Redis và ứng dụng có thể chồng lấp một phần việc.

### 2.2. Những gì pipeline không làm

| Quan niệm dễ nhầm | Cách hiểu đúng |
|---|---|
| Pipeline biến 100 lệnh thành một thao tác Redis | Redis vẫn phải thực thi những lệnh đó |
| Pipeline đồng nghĩa với xử lý song song nhiều lõi | Việc xếp lệnh liên tiếp không tự tạo song song ở Redis |
| Pipeline là giao dịch | Pipeline không tự làm nhóm lệnh thành một giao dịch nguyên tử |
| Pipeline giảm số byte phải truyền | Payload kết quả vẫn phải chuyển về ứng dụng |
| Pipeline bảo đảm từng lệnh nhanh hơn | Lợi ích chính nằm ở việc giảm chờ mạng |
| Batch càng lớn càng tốt | Batch lớn có thể làm tăng bộ nhớ, GC và độ trễ |
| Có thể bỏ qua kết quả để benchmark | Nếu ứng dụng thật phải đọc kết quả thì benchmark cũng phải đọc |

Nếu lệnh sau phụ thuộc kết quả của lệnh trước, chẳng hạn `GET balance` rồi quyết định `DECRBY`, pipeline thuần túy không đủ để bảo vệ điều kiện nghiệp vụ. Khi đó cần cân nhắc lệnh Redis nguyên tử, Lua hoặc `WATCH/MULTI/EXEC`.

## 3. Mô tả đúng khối lượng dữ liệu

Một benchmark không nên chỉ có hai tham số “số lệnh” và “batch size”. Những thuộc tính sau thường quyết định hiệu quả thực tế:

| Thuộc tính | Cần ghi nhận | Kịch bản minh họa |
|---|---|---|
| Số lệnh | Tổng số `GET`/`SET`/`HGET` | 1.000, 5.000, 20.000 |
| Số khóa khác nhau | Đọc nhiều khóa hay lặp khóa nóng | 5.000 khóa duy nhất |
| Kích thước giá trị | Byte sau khi tuần tự hóa | 128 B, 2 KiB, 8 KiB |
| Phân bố kích thước | p50/p95/p99 của kích thước giá trị | Đa số nhỏ, vài giá trị lớn |
| Loại thao tác | Đọc, ghi hay hỗn hợp | 80% `GET`, 20% `SET` |
| Serializer | Chuỗi, JSON, JDK hay tùy chỉnh | `StringRedisSerializer` |
| Số client | Số tác vụ/request hoạt động đồng thời | 1, 8, 32 |
| Mạng | Vị trí Redis và RTT | Local, cùng vùng, khác vùng |
| Kiến trúc Redis | Standalone, Sentinel, Cluster | Standalone |
| Bộ nhớ | Heap JVM và `maxmemory` Redis | Ngân sách được cấp |
| TTL | Khóa có hết hạn khi thử nghiệm không | 30 phút |
| Batch size | Lệnh trong mỗi pipeline | 20, 100, 500, 1.000 |

### 3.1. Kích thước byte, không phải độ dài Java String

`String.length()` không cho biết chính xác số byte truyền qua Redis. Ví dụ:

```java
import java.nio.charset.StandardCharsets;

String text = "Dữ liệu tiếng Việt";

int characters = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
```

Các ký tự Unicode có thể chiếm nhiều byte UTF-8. Với JSON, kích thước còn phụ thuộc tên thuộc tính, giá trị lồng nhau, thông tin kiểu và serializer.

Nếu ứng dụng dùng `Jackson2JsonRedisSerializer` hoặc `GenericJackson2JsonRedisSerializer`, hãy đo kích thước **đầu ra của serializer tương ứng**:

```java
byte[] payload = serializer.serialize(customer);
int bytes = payload.length;
```

Đối với thao tác `GET`, cần tính byte của **giá trị được trả về**. Đối với `SET`, cần tính byte của **giá trị được gửi đi**. Trường hợp cả đọc và ghi, có thể báo riêng từng chiều.

### 3.2. Cùng số lệnh chưa chắc cùng lượng công việc

So sánh hai tác vụ đều đọc 10.000 khóa:

```text
Kịch bản A:
  10.000 × 200 byte ≈ 1,91 MiB payload

Kịch bản B:
  10.000 × 64 KiB = 625 MiB payload
```

Số lệnh bằng nhau nhưng lượng dữ liệu chênh lệch hơn 300 lần. Với A, tiết kiệm RTT có thể chiếm phần lớn lợi ích. Với B, băng thông, bộ đệm và giải mã dữ liệu có thể chi phối kết quả.

Phân bố kích thước cũng quan trọng. Nếu phần lớn giá trị 1 KiB nhưng có 1% giá trị 500 KiB, một batch chứa nhiều giá trị lớn có thể chậm hoặc tốn bộ nhớ hơn đáng kể so với batch khác cùng số lệnh.

## 4. Những chỉ số cần đo

### 4.1. Thời gian hoàn thành công việc

Đo từ lúc bắt đầu gửi lệnh đến khi **đã nhận và xử lý đủ các kết quả**:

```java
long started = System.nanoTime();

runWorkload();

long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` phù hợp để tính khoảng thời gian trong cùng JVM. Không lấy chênh lệch từ đồng hồ hệ thống để đo các thao tác ngắn.

Cần phân biệt thời gian của **một pipeline batch**, thời gian của **toàn bộ công việc** và độ trễ **request nghiệp vụ**.

### 4.2. Thông lượng theo lệnh

```text
ops/s = số lệnh hoàn thành thành công / số giây thực hiện
```

Ví dụ hoàn thành 20.000 lệnh trong 2 giây tương ứng 10.000 lệnh/giây. Nếu có lỗi hoặc timeout, phải tách riêng số lệnh thất bại; không coi mọi lệnh đã gửi là đã hoàn thành.

### 4.3. Thông lượng theo byte

```text
MiB/s payload =
    tổng số byte payload đã xử lý
    / (1.048.576 × số giây thực hiện)
```

Chỉ số này giúp nhận ra khi băng thông trở thành giới hạn. Nó không bằng lưu lượng thực trên card mạng vì còn có giao thức Redis RESP, tên khóa, TCP, TLS và overhead khác.

### 4.4. Percentile độ trễ

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa mẫu có thời gian không vượt quá mức này |
| p95 | 95% mẫu có thời gian không vượt quá mức này |
| p99 | 99% mẫu có thời gian không vượt quá mức này |

Phải nêu rõ percentile được tính trên **lượt công việc**, **batch** hay **HTTP request**. Nếu một batch gồm 500 lệnh hoàn thành trong 50 ms, chia 50/500 = 0,1 ms **không phải** p99 của từng lệnh Redis.

### 4.5. Bộ nhớ, CPU và tác động lên hệ thống

Đo đồng thời:

- Peak heap và số object được cấp phát ở JVM.
- GC pause và số lần GC.
- CPU Redis và CPU ứng dụng.
- Băng thông mạng, số kết nối và buffer ở driver.
- p95/p99 của những request nghiệp vụ dùng Redis cùng lúc.
- Số lỗi và timeout trong benchmark.

Một cấu hình làm tác vụ nền nhanh hơn 15% nhưng làm p99 API chính tăng gấp đôi chưa chắc là tối ưu cho ứng dụng.

## 5. Thiết kế thí nghiệm có thể so sánh

Có thể thử ba phương án:

1. **Sequential:** gọi từng `GET` và chờ trả kết quả.
2. **Pipeline theo lô:** gửi các `GET` của cùng tập khóa thành từng batch.
3. **MGET:** khi bài toán là đọc nhiều Redis String và topology cho phép, dùng `MGET` như một điểm so sánh.

Các phương án phải thực hiện **cùng công việc**: cùng khóa, cùng dữ liệu, cùng serializer và cùng mức kiểm tra/tiêu thụ kết quả. Không so một phương án phải giải mã JSON với một phương án chỉ gửi lệnh rồi bỏ qua phản hồi.

Một ma trận thử nghiệm:

| Nhóm tải | Payload/khóa | Số khóa/lượt | Batch size nên thử |
|---|---:|---:|---|
| Nhỏ | 128 B | 5.000 | 20, 100, 500, 1.000 |
| Trung bình | 2 KiB | 5.000 | 20, 100, 500, 1.000 |
| Lớn | 8 KiB | 5.000 | 20, 100, 500, 1.000 |
| Hỗn hợp | 128 B đến 64 KiB | Theo phân bố thật | 20, 100, 500 |

Đây là **các giá trị đề xuất cho việc đo**, không phải cấu hình đã được chứng minh nhanh nhất.

Quy trình:

```text
Tạo dataset và nạp vào Redis
             |
             v
Warm-up kết nối, JVM và serializer
             |
             v
Chạy sequential/pipeline trên cùng tập khóa
             |
             v
Lặp nhiều lượt, đổi thứ tự thử
             |
             v
Đo elapsed, ops/s, MiB/s, p95, heap, CPU
             |
             v
So sánh theo payload, batch, concurrency, mạng
```

Khi chỉ đo **tốc độ đọc**, không cộng thời gian chuẩn bị dữ liệu vào phép đo. Benchmark **ghi** cần một kịch bản riêng để tránh trộn các chi phí khác bản chất.

## 6. Spring Data Redis hỗ trợ pipeline thế nào?

`RedisTemplate` và `StringRedisTemplate` cung cấp phương thức `executePipelined`. Ví dụ:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> getBatch(
        StringRedisTemplate redis,
        List<String> keys) {

    return redis.executePipelined(
            (RedisCallback<Object>) connection -> {

                for (String key : keys) {
                    byte[] rawKey =
                            key.getBytes(StandardCharsets.UTF_8);

                    connection.stringCommands().get(rawKey);
                }

                // Kết quả các lệnh được executePipelined thu thập.
                return null;
            }
    );
}
```

Trong ví dụ:

- Lời gọi `connection.stringCommands().get(...)` đưa lệnh `GET` vào pipeline.
- Callback trả về `null`; không trả kết quả truy vấn trực tiếp từ callback.
- `executePipelined` trả `List<Object>` chứa kết quả các lệnh, theo thứ tự lệnh trong pipeline.
- Với `StringRedisTemplate` mặc định, các giá trị String được giải mã theo serializer tương ứng.
- Danh sách kết quả có thể **tồn tại đồng thời trong bộ nhớ JVM** trước khi ứng dụng xử lý.

Ví dụ giả định khóa mã hóa UTF-8 như cấu hình mặc định của `StringRedisTemplate`. Nếu ứng dụng thay đổi key serializer, phải dùng đúng serializer khi chuyển khóa thành `byte[]`.

### 6.1. Tại sao cần chia lô?

Giả sử phải đọc 5.000 khóa, mỗi giá trị 32 KiB:

```text
5.000 × 32 KiB = 160.000 KiB ≈ 156,25 MiB payload
```

Nếu gửi toàn bộ trong một `executePipelined`, client có thể phải giữ dữ liệu kết quả rất lớn, cộng thêm đối tượng Java và buffer của driver.

Nếu chia batch size 100, mỗi lô tương đương khoảng 3,125 MiB payload, chưa tính overhead; chương trình có thể xử lý rồi giải phóng kết quả lô đó trước khi nhận lô tiếp theo.

Tuy nhiên, **batch size là số lệnh, không phải số byte**. Batch 100 lệnh có thể nhẹ khi giá trị 128 B, nhưng rất nặng khi giá trị 1 MiB.

## 7. Ví dụ benchmark Java trong Spring Boot

Đoạn mã sau dùng Java 21 và `StringRedisTemplate`. Nó chuẩn bị một bộ khóa với payload có độ dài xác định, sau đó đo việc đọc tuần tự và đọc theo pipeline. Phương thức `runExample()` chỉ thực hiện khi được gọi; không nên tự chạy khi ứng dụng production khởi động.

### 7.1. Tạo dữ liệu và hai phương án đọc

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.function.LongSupplier;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisPipelineBenchmark {

    private final StringRedisTemplate redis;

    public RedisPipelineBenchmark(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private List<String> seed(
            String runId,
            int count,
            int valueBytes) {

        Random random = new Random(42);
        String alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
        List<String> keys = new ArrayList<>(count);

        for (int i = 0; i < count; i++) {
            char[] chars = new char[valueBytes];

            for (int j = 0; j < valueBytes; j++) {
                chars[j] = alphabet.charAt(
                        random.nextInt(alphabet.length())
                );
            }

            String key = "bench:pipeline:" + runId + ":" + i;

            redis.opsForValue().set(
                    key,
                    new String(chars),
                    Duration.ofMinutes(30)
            );
            keys.add(key);
        }

        return keys;
    }

    public long sequentialRead(List<String> keys) {
        long payloadBytes = 0;

        for (String key : keys) {
            String value = redis.opsForValue().get(key);

            if (value == null) {
                throw new IllegalStateException("Không thấy khóa " + key);
            }

            payloadBytes += value
                    .getBytes(StandardCharsets.UTF_8).length;
        }

        return payloadBytes;
    }

    public long pipelineRead(
            List<String> keys,
            int batchSize) {

        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize phải lớn hơn 0"
            );
        }

        long payloadBytes = 0;

        for (int offset = 0; offset < keys.size();
                offset += batchSize) {

            // from/to không thay đổi trong lambda bên dưới.
            final int from = offset;
            final int to = Math.min(
                    offset + batchSize,
                    keys.size()
            );

            List<Object> results = redis.executePipelined(
                    (RedisCallback<Object>) connection -> {

                        for (int i = from; i < to; i++) {
                            byte[] rawKey = keys.get(i)
                                    .getBytes(StandardCharsets.UTF_8);

                            connection.stringCommands().get(rawKey);
                        }

                        return null;
                    }
            );

            if (results.size() != to - from) {
                throw new IllegalStateException(
                        "Số kết quả không khớp số lệnh"
                );
            }

            for (Object item : results) {
                if (!(item instanceof String value)) {
                    throw new IllegalStateException(
                            "Thiếu giá trị hoặc serializer khác"
                    );
                }

                payloadBytes += value
                        .getBytes(StandardCharsets.UTF_8).length;
            }
        }

        return payloadBytes;
    }

    public record Measurement(
            String method,
            int commands,
            long payloadBytes,
            double milliseconds,
            double opsPerSecond,
            double mebibytesPerSecond
    ) {
    }

    private static Measurement measure(
            String method,
            int commands,
            LongSupplier operation) {

        long started = System.nanoTime();
        long payloadBytes = operation.getAsLong();
        long elapsedNanos = System.nanoTime() - started;

        double seconds = elapsedNanos / 1_000_000_000.0;

        return new Measurement(
                method,
                commands,
                payloadBytes,
                elapsedNanos / 1_000_000.0,
                commands / seconds,
                payloadBytes / (1024.0 * 1024.0 * seconds)
        );
    }

    public List<Measurement> runExample() {
        int count = 5_000;
        int valueBytes = 2_048;

        List<String> keys = seed(
                UUID.randomUUID().toString(),
                count,
                valueBytes
        );

        // Warm-up trước khi ghi số đo chính thức.
        sequentialRead(keys);
        pipelineRead(keys, 100);

        return List.of(
                measure("sequential", count,
                        () -> sequentialRead(keys)),
                measure("pipeline-100", count,
                        () -> pipelineRead(keys, 100)),
                measure("pipeline-500", count,
                        () -> pipelineRead(keys, 500))
        );
    }
}
```

Đây là **bộ đo nhỏ để minh họa**, gồm một lượt đọc cho mỗi phương án:

1. `seed` tạo 5.000 khóa, mỗi giá trị chứa 2.048 ký tự ASCII = 2.048 byte UTF-8.
2. Dữ liệu được ghi **trước** phép đo và có TTL 30 phút.
3. `sequentialRead` chờ từng kết quả, xác nhận giá trị tồn tại và cộng số byte.
4. `pipelineRead` dùng `executePipelined` theo batch, nhận và kiểm tra các kết quả ngay trong từng lô.
5. `measure` tính thời gian, số lệnh/giây và MiB payload/giây.
6. Các kết quả `Measurement` có thể được ghi vào log hoặc xuất CSV để so sánh.

Điều kiện quan trọng: các khóa phải tồn tại trong toàn bộ lượt đo, Redis không được tự loại bỏ chúng do áp lực bộ nhớ và kết quả phải có cùng số byte ở hai phương án. Nếu dùng serializer tùy chỉnh, phải điều chỉnh việc mã hóa/giải mã tương ứng.

Khi muốn so sánh với dữ liệu JSON thật, thay `String` và serializer của ví dụ bằng kiểu dữ liệu và serializer của ứng dụng, nhưng bảo đảm hai phương án vẫn thực hiện công việc tương đương.

### 7.2. Vì sao ví dụ chưa đủ cho kết luận production?

Đoạn mã trên chỉ có một lượt chính thức cho mỗi phương án. Benchmark nghiêm túc cần:

- Làm nóng mỗi phương án đủ để loại bỏ chi phí khởi tạo kết nối và JIT.
- Chạy nhiều lượt sau warm-up.
- Đảo thứ tự: sequential → pipeline 100 → pipeline 500, rồi pipeline 500 → sequential → pipeline 100.
- Đo nhiều kích thước payload, số khóa và số client.
- Báo percentile của **thời gian công việc**, không chỉ lần chạy nhanh nhất.
- Kiểm tra JVM heap, GC và ảnh hưởng lên request nền.

Không nên coi số đo trên máy local là dự báo chắc chắn cho môi trường Redis Cluster hoặc mạng có TLS.

## 8. Cách lập bảng kết quả

Có thể tạo bảng ghi dữ liệu sau mỗi nhóm thử nghiệm:

| Payload | Phương án | Batch | Elapsed ms | Ops/s | MiB/s | Peak heap |
|---|---|---:|---|---|---|---|
| 128 B | Sequential | 1 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 128 B | Pipeline | 100 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 2 KiB | Sequential | 1 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 2 KiB | Pipeline | 100 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 2 KiB | Pipeline | 500 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 8 KiB | Pipeline | 100 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |
| 8 KiB | Pipeline | 500 | Đo thực tế | Đo thực tế | Đo thực tế | Đo thực tế |

**Không điền các số liệu giả thành kết quả benchmark.** Tất cả các giá trị trên phải được đo ở môi trường và phiên bản thư viện được mô tả rõ ràng.

Speedup có thể được tính từ thời gian của cùng một công việc:

```text
Speedup = elapsed_sequential / elapsed_pipeline
```

Ví dụ **giả định** một tác vụ tuần tự mất 4 giây, pipeline mất 0,8 giây thì tốc độ hoàn thành tăng 5 lần. Không được công bố “pipeline nhanh gấp 5 lần” mà không kèm dữ liệu, phương pháp và môi trường đo.

## 9. Chọn batch size bằng ngân sách byte và độ trễ

### 9.1. Batch nhỏ: còn nhiều lần chờ mạng

Với 5.000 khóa và batch size 10, ứng dụng cần khoảng 500 lượt pipeline. Trên mạng có RTT cao, số lượt chờ vẫn có thể chiếm nhiều thời gian.

### 9.2. Batch lớn: tăng áp lực bộ đệm

Với 5.000 khóa và batch size 5.000, một lần `executePipelined` có thể phải tập hợp mọi kết quả trong bộ nhớ. Nếu mỗi giá trị 32 KiB, riêng payload đã khoảng 156,25 MiB.

Bộ nhớ thực còn bao gồm:

- Buffer dữ liệu nhận trong driver.
- Đối tượng `String`, JSON object hoặc `byte[]`.
- Danh sách `List<Object>` giữ tham chiếu.
- Các bản sao do mã nghiệp vụ tạo ra.
- Những pipeline khác chạy đồng thời.

Một lô lớn có thể làm peak heap, GC pause và p99 của request khác tăng mạnh.

### 9.3. Dùng ngân sách byte để xác định điểm thử

Giả sử một lô được phép chứa khoảng 4 MiB payload và giá trị trung bình 8 KiB:

```text
4 MiB = 4096 KiB
4096 / 8 = 512 giá trị
```

Batch khoảng 500 có thể là một **điểm bắt đầu**. Nhưng nếu có giá trị lớn bất thường, một lô 500 lệnh vẫn có thể vượt xa 4 MiB.

Công thức định hướng:

```text
batch_size_ước_tính ≈ ngân_sách_payload / kích_thước_giá_trị_ước_tính
```

Công thức **không bảo đảm giới hạn byte tuyệt đối**, vì client thường không biết chắc kích thước phản hồi `GET` trước khi nhận.

### 9.4. Đồng thời cũng tiêu thụ bộ nhớ

Nếu mỗi batch trả khoảng 4 MiB payload, 20 batch xử lý đồng thời tương đương khoảng 80 MiB **chỉ riêng payload**. Trên thực tế còn nhiều chi phí khác.

Vì vậy, phải điều chỉnh cả **batch size** lẫn **số tác vụ đồng thời**. Một cấu hình hợp lý với một worker có thể quá nặng khi 50 worker cùng chạy.

## 10. Quan sát tài nguyên Redis và JVM

### 10.1. Phía Redis

Các lệnh sau giúp quan sát trạng thái trong môi trường thử nghiệm:

```redis
INFO stats
INFO commandstats
INFO cpu
INFO memory
INFO clients
SLOWLOG GET 10
```

`INFO commandstats` cung cấp thống kê xử lý lệnh. `INFO memory` giúp quan sát bộ nhớ Redis. `SLOWLOG` phản ánh thời gian Redis thực thi lệnh chậm, **không bao gồm toàn bộ thời gian truyền mạng hoặc xử lý tại ứng dụng**.

Một pipeline có thể giảm thời gian đầu cuối Java mà thời gian thực thi từng lệnh ở Redis gần như không đổi. Vì vậy phải đo cả hai phía.

### 10.2. Phía ứng dụng

Có thể dùng Micrometer, Java Flight Recorder và JVM metrics để theo dõi:

- Thời gian thực hiện pipeline batch và toàn công việc.
- Heap đang sử dụng, peak heap, số object được cấp phát.
- GC pause và thời gian CPU JVM.
- Số kết nối, queue, thread chờ và timeout.
- p95/p99 của những API nghiệp vụ cùng dùng Redis.

Với JSON, thời gian giải mã có thể đáng kể. Pipeline chỉ giảm chờ mạng nhưng không làm miễn phí việc tạo đối tượng Java.

### 10.3. Tác vụ nền và API trực tuyến cùng chạy

Benchmark một tác vụ đơn lẻ chưa nói lên tác động khi hệ thống có tải.

Một kịch bản thực tế:

```text
Tải nền:  GET/SET liên tục từ API
Tác vụ:   đọc 5.000 khóa bằng pipeline
Theo dõi: tốc độ tác vụ + p95/p99 API nền + CPU/heap Redis
```

Nếu batch 2.000 làm tác vụ nhanh thêm 5% nhưng p99 của API nền tăng mạnh, batch 100 có thể phù hợp hơn. Mục tiêu là hiệu quả **toàn hệ thống**, không chỉ con số lệnh/giây của một vòng lặp.

Không nên chạy thí nghiệm tải nặng trên Redis production khi chưa có giới hạn an toàn và kế hoạch dừng/dọn dữ liệu.

## 11. Mạng, driver và topology ảnh hưởng kết quả

### 11.1. RTT và TLS

Pipeline thường phát huy lợi ích rõ khi nhiều lệnh nhỏ đi qua mạng có RTT đáng kể. Trên localhost, mỗi lượt trao đổi đã rất ngắn nên lợi ích có thể khác.

Trong báo cáo nên ghi:

```text
Redis version:
Spring Data Redis version:
Client: Lettuce/Jedis và phiên bản:
Standalone / Sentinel / Cluster:
TLS:
Mạng và RTT:
Connection pool:
Serializer:
Kích thước batch:
Số client đồng thời:
Heap JVM:
Payload:
```

### 11.2. Lettuce và flush

Spring Data Redis thường sử dụng Lettuce. Lettuce có cơ chế quản lý kết nối và gửi lệnh bất đồng bộ; một số phiên bản/cấu hình hỗ trợ điều chỉnh cách **flush** lệnh trong pipeline.

Tên API và hỗ trợ cụ thể có thể thay đổi theo phiên bản. Không lấy một cấu hình flush từ dự án khác rồi mặc định nó luôn tối ưu. Khi so sánh, giữ ổn định các tham số còn lại và ghi rõ cách cấu hình kết nối.

### 11.3. Redis Cluster

Trong Cluster, khóa phân bố trên nhiều hash slot và nhiều nút. Khả năng định tuyến lệnh, số kết nối và phân bố dữ liệu ảnh hưởng tới hiệu quả pipeline.

`MGET` là lệnh đa khóa và có giới hạn về slot trong Redis Cluster. Pipeline nhiều `GET` không tự biến các khóa ở những shard khác nhau thành một lệnh đa khóa hoặc giao dịch hợp lệ.

Nếu hệ thống thật chạy Cluster, phải đo với topology và phân bố khóa gần thực tế.

## 12. Khi nào pipeline không phải lựa chọn tốt nhất?

### 12.1. Có lệnh đa khóa phù hợp

Khi đọc nhiều Redis String:

```redis
MGET cache:1 cache:2 cache:3
```

Đối với nhiều field của **cùng một Redis Hash**:

```redis
HMGET customer:42 name email city
```

`MGET` hoặc `HMGET` có thể giảm số lệnh và đôi khi giảm dữ liệu truyền về. Nên so sánh với pipeline nếu chúng đáp ứng đúng yêu cầu dữ liệu.

### 12.2. Lệnh sau phụ thuộc kết quả lệnh trước

```text
GET stock
  |
  v
Kiểm tra stock > 0
  |
  v
DECR stock
```

Pipeline không tự biến chuỗi này thành thao tác kiểm tra và cập nhật nguyên tử. Khi cần bảo vệ điều kiện, xem xét lệnh Redis nguyên tử, Lua script hoặc `WATCH/MULTI/EXEC`.

### 12.3. Giá trị quá lớn

Nếu một `GET` trả về JSON 50 MiB, việc gom thêm 100 lệnh `GET` vào pipeline không khiến JSON nhỏ đi. Cần xem lại mô hình dữ liệu, cách chia object hoặc chỉ đọc những phần cần thiết.

### 12.4. Redis đã bão hòa CPU hoặc mạng

Nếu CPU Redis hoặc băng thông đã tới giới hạn, gửi lệnh nhanh hơn có thể chỉ tạo thêm hàng đợi và bộ đệm. Điều này có thể cải thiện rất ít throughput mà tăng độ trễ những yêu cầu khác.

### 12.5. Công việc chỉ có vài lệnh nhỏ

Với một hoặc hai lệnh, chi phí tổ chức pipeline có thể không đáng tối ưu. Ưu tiên sự đơn giản khi chưa đo được vấn đề thực tế.

## 13. Các lỗi thường gặp khi đo pipeline

1. **Chỉ đo vài lệnh trên localhost.** Kết quả chủ yếu phản ánh chi phí cố định, không đại diện dữ liệu lớn hoặc mạng production.
2. **Chỉ so ops/s.** Cần bổ sung MiB/s vì một lệnh có thể trả vài byte hoặc vài MiB.
3. **Đếm ký tự thay byte.** Dùng byte sau serializer, nhất là với JSON và Unicode.
4. **Sequential giải mã kết quả nhưng pipeline không đọc kết quả.** Hai phương án phải xử lý cùng lượng dữ liệu.
5. **Đo cả thời gian seed khi chỉ muốn đo GET.** Tách chuẩn bị, warm-up và đo chính thức.
6. **Chỉ chạy một lượt.** Warm-up đầy đủ, lặp lại và đổi thứ tự các phương án.
7. **Một pipeline quá lớn.** `executePipelined` có thể giữ lượng lớn kết quả trong bộ nhớ; đo peak heap và giới hạn lô.
8. **Hiểu sai p99.** Percentile của batch khác percentile của request hoặc lệnh riêng lẻ.
9. **Bỏ qua timeout và kết quả thiếu.** Kiểm tra số kết quả và byte đã xử lý; thống kê lỗi riêng.
10. **Không đo tải nền.** Có thể tăng throughput benchmark nhưng làm API nghiệp vụ chậm đi.
11. **Không ghi phiên bản client/serializer.** Kết quả giữa hai cấu hình driver khác nhau khó so sánh trực tiếp.
12. **Coi batch size là giới hạn byte.** Batch 200 chỉ là 200 lệnh; tổng dữ liệu vẫn tùy giá trị.

## 14. Bài tập thực hành

### Bài tập A: Giữ số lệnh, đổi kích thước giá trị

Tạo 5.000 khóa và đo ba bộ dữ liệu:

```text
5.000 × 128 B
5.000 × 2 KiB
5.000 × 8 KiB
```

Giữ cùng batch size 100. Với mỗi bộ, so sequential và pipeline. Ghi elapsed, ops/s, MiB/s, peak heap. Xác định khi nào hiệu quả giảm RTT bắt đầu bị chi phí truyền/giải mã chi phối.

### Bài tập B: Giữ payload, đổi batch size

Với 5.000 khóa, mỗi giá trị 2 KiB, thử:

```text
Sequential
Pipeline batch 20
Pipeline batch 100
Pipeline batch 500
Pipeline batch 1000
```

Lặp nhiều lượt, đảo thứ tự phương án và tính p50/p95 của **thời gian công việc**. So sánh cùng số byte xử lý và tìm điểm tăng tốc chững lại.

### Bài tập C: Dữ liệu hỗn hợp

Tạo bộ dữ liệu có đa số giá trị 1 KiB, một số 16 KiB và vài giá trị 64 KiB. Thử batch 100 và 500. Xem những batch chứa giá trị lớn có biến động thời gian và heap nhiều hơn không.

### Bài tập D: Đo traffic nền

Duy trì một lượng request GET/SET ổn định trong khi chạy benchmark. Đo p95/p99 request nền trước, trong và sau tác vụ. Chọn cấu hình giữ request trong ngân sách độ trễ.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao pipeline tăng tốc rõ khi lệnh nhỏ và RTT cao?**

Vì client tránh phải chờ một lượt mạng sau từng lệnh. Khi xử lý Redis và payload còn nhỏ, lợi ích từ giảm RTT có tỷ trọng lớn.

**2. Hai tác vụ đều 10.000 GET có chắc đạt cùng speedup?**

Không. Kích thước payload, serializer, băng thông, CPU, số client và tải nền có thể khác nhau.

**3. Batch 1.000 luôn tốt hơn batch 100?**

Không. Batch lớn giảm số lần chờ nhưng có thể tăng buffer, heap, GC và độ trễ request khác.

**4. Có thể chia thời gian một batch cho số lệnh rồi gọi đó là p99 của từng lệnh không?**

Không. Đó chỉ là phép chia trung bình quy đổi, không phải phân bố độ trễ từng lệnh.

**5. Vì sao phải đo cả MiB/s?**

Vì ops/s không cho biết bao nhiêu dữ liệu đã được truyền và giải mã. Các workload cùng số lệnh có thể chênh lệch hàng trăm lần về byte.

**6. Benchmark local có đủ quyết định batch size trên Cluster không?**

Không. Phải xét lại RTT, TLS, shard, kết nối, serializer và mức đồng thời theo topology thật.

**7. Tại sao cần đo p99 API nền khi tối ưu một tác vụ pipeline?**

Vì một pipeline lớn có thể làm tác vụ nền nhanh hơn nhưng ảnh hưởng đến độ trễ người dùng. Cấu hình phải phù hợp toàn bộ hệ thống.

**8. Khi nào nên thử MGET?**

Khi cần đọc nhiều Redis String và ràng buộc đa khóa của topology cho phép. Đó là một phương án cần benchmark cùng công việc.

## 16. Ghi nhớ

- **Pipeline giảm lượt chờ mạng**, nhưng không làm các lệnh Redis hay dữ liệu trả về biến mất.
- **Khối lượng dữ liệu thật** gồm số lệnh, byte sau serializer, phân bố kích thước, loại truy cập, mạng và mức đồng thời.
- Spring Data Redis `executePipelined` có thể gom nhiều kết quả trong bộ nhớ; hãy **chia lô và xử lý từng lô**.
- Đánh giá cùng lúc **elapsed, ops/s, MiB/s, percentile đúng đối tượng, heap/GC và ảnh hưởng tới request nền**.
- Batch size phù hợp phải đến từ **kết quả đo với giới hạn tài nguyên thực tế**, không phải một con số tối ưu chung.

### Tài liệu tham khảo

- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/).
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
