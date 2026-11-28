# mapMultiToLong và LongConsumer cho kết quả số nguyên dài

`Stream.mapMultiToLong` là biến thể chuyên biệt của `mapMulti` khi các giá trị đầu ra có kiểu nguyên thủy `long`. Mapper nhận phần tử nguồn cùng một `LongConsumer`; mỗi lần gọi `accept(long)` sẽ phát một giá trị `long` vào `LongStream` kết quả. Một phần tử nguồn có thể phát không, một hoặc nhiều giá trị.

Phương thức này phù hợp khi cần trích xuất nhiều số nguyên dài từ một đối tượng, duyệt các giá trị con hoặc phát các đại lượng như kích thước byte, số lượng bản ghi, mã định danh số lớn và thời điểm epoch. Vì kết quả là `LongStream`, pipeline có thể dùng các phép toán số học chuyên biệt mà không cần đóng gói từng giá trị thành `Long`.

## 1. mapMultiToLong là gì?

`mapMultiToLong` là phương thức trên `Stream<T>`, được bổ sung trong Java 16. Phương thức nhận mapper kiểu `BiConsumer` và trả về `LongStream`.

Chữ ký tổng quát:

```java
LongStream mapMultiToLong(
    BiConsumer<? super T, ? super LongConsumer> mapper
)
```

Các thành phần có ý nghĩa như sau:

- `T` là kiểu phần tử của Stream nguồn.
- Mapper nhận phần tử nguồn kiểu `T` ở tham số thứ nhất.
- Tham số thứ hai là `LongConsumer`, dùng để phát các giá trị `long`.
- Mỗi lần gọi `accept(long)` tạo một phần tử trong `LongStream` kết quả.
- Mapper không trả về `long` trực tiếp; nó gửi từng giá trị qua Consumer.

Ví dụ khung:

```java
import java.util.stream.LongStream;
import java.util.stream.Stream;

Stream<String> source = Stream.of("batch-A", "batch-B");

LongStream result = source.mapMultiToLong((batch, emit) -> {
    emit.accept(1_000_000_000L);
    emit.accept(2_000_000_000L);
});
```

Mỗi phần tử nguồn phát hai giá trị `long`. Nếu mapper không gọi `emit.accept`, phần tử nguồn hiện tại không đóng góp giá trị nào vào kết quả.

## 2. LongConsumer và phương thức accept(long)

`LongConsumer` là functional interface trong `java.util.function`, đại diện cho một hành động nhận một giá trị nguyên thủy kiểu `long`.

```java
@FunctionalInterface
public interface LongConsumer {
    void accept(long value);
}
```

Trong mapper của `mapMultiToLong`, tham số thứ hai có kiểu `LongConsumer`. Tên tham số có thể là `emit`, `output` hoặc `consumer`:

```java
import java.util.List;

List<String> files = List.of("report.csv", "archive.zip");

long[] sizes = files.stream()
    .mapMultiToLong((file, emit) -> {
        emit.accept(file.length());
    })
    .toArray();
```

Trong ví dụ này, `String.length()` trả về `int`; Java mở rộng giá trị đó thành `long` khi truyền vào `LongConsumer.accept`. Với dữ liệu thực tế vốn đã là `long`, giá trị được truyền trực tiếp mà không cần chuyển qua wrapper `Long`.

Có thể gọi `accept` nhiều lần trong cùng một lần mapper chạy:

```java
import java.util.List;

List<String> files = List.of("report.csv", "archive.zip");

long[] metrics = files.stream()
    .mapMultiToLong((file, emit) -> {
        emit.accept(file.length());
        emit.accept(file.length() * 1_000L);
    })
    .toArray();
```

Mỗi tên tệp phát hai số. Kết quả vẫn là `long[]`, vì thao tác trung gian trả về `LongStream`.

## 3. Phát không, một hoặc nhiều giá trị long

Số lần gọi `accept` quyết định số phần tử đầu ra mà mỗi phần tử nguồn đóng góp:

| Cách mapper xử lý | Số phần tử đầu ra |
|---|---:|
| Không gọi `emit.accept` | 0 |
| Gọi `emit.accept` một lần | 1 |
| Gọi `emit.accept` nhiều lần | Nhiều |

Ví dụ, mỗi gói dữ liệu chứa một số lượng byte đã truyền và byte nhận. Ta chỉ phát các giá trị dương:

```java
import java.util.List;

record NetworkSample(String host, long bytesSent, long bytesReceived) {}

List<NetworkSample> samples = List.of(
    new NetworkSample("api-1", 5_000_000_000L, 8_000_000_000L),
    new NetworkSample("api-2", 0L, 2_500_000_000L),
    new NetworkSample("api-3", 1_200_000_000L, 0L)
);

long[] byteCounts = samples.stream()
    .mapMultiToLong((sample, emit) -> {
        if (sample.bytesSent() > 0) {
            emit.accept(sample.bytesSent());
        }

        if (sample.bytesReceived() > 0) {
            emit.accept(sample.bytesReceived());
        }
    })
    .toArray();
```

Kết quả:

```text
[5000000000, 8000000000, 2500000000, 1200000000]
```

Mỗi mẫu có thể phát không, một hoặc hai giá trị. Những trường bằng không không gọi Consumer nên không xuất hiện trong mảng kết quả. Các giá trị lớn hơn giới hạn của `int` vẫn được giữ nguyên vì mapper phát kiểu `long`.

Nếu chỉ cần giữ hoặc loại một giá trị đã có sẵn, `filter` thường thể hiện ý định rõ hơn. `mapMultiToLong` phù hợp khi một phần tử nguồn có thể tạo nhiều giá trị hoặc cần duyệt các trường/dữ liệu con để phát số nguyên dài.

## 4. Ví dụ: làm phẳng danh sách số nguyên dài

Một bản ghi có thể chứa danh sách các kích thước hoặc số đếm kiểu `long`. Ta có thể nối các danh sách con thành một `LongStream`:

```java
import java.util.List;

record StorageNode(String name, List<Long> objectSizes) {}

List<StorageNode> nodes = List.of(
    new StorageNode("node-A", List.of(4_000_000_000L, 2_500_000_000L)),
    new StorageNode("node-B", List.of(8_000_000_000L)),
    new StorageNode("node-C", List.of())
);

long[] allSizes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .toArray();
```

Kết quả:

```text
[4000000000, 2500000000, 8000000000]
```

Mapper duyệt danh sách kích thước của từng node và phát từng giá trị qua `LongConsumer`. Node có danh sách rỗng không phát phần tử nào. Thứ tự đầu ra tuân theo thứ tự các node trong Stream nguồn và thứ tự phần tử trong từng danh sách.

Vì `objectSizes()` trả về `List<Long>`, vòng lặp for-each đọc từng `Long` rồi unbox thành `long` khi gọi `emit.accept`. Nếu dữ liệu có thể chứa null, cần kiểm tra null trước khi unbox.

## 5. Ví dụ: phát các mốc thời gian epoch

Thời điểm epoch milliseconds thường được biểu diễn bằng `long`. Một sự kiện có thể có thời điểm bắt đầu và một số mốc liên quan. Ta có thể phát các mốc hợp lệ:

```java
import java.util.List;

record JobTimeline(
    String jobId,
    long startedAt,
    long completedAt,
    long lastHeartbeat
) {}

List<JobTimeline> jobs = List.of(
    new JobTimeline("J-01", 1_800_000_000_000L, 1_800_000_003_000L, 1_800_000_002_000L),
    new JobTimeline("J-02", 1_800_000_010_000L, 0L, 1_800_000_012_000L)
);

long[] timestamps = jobs.stream()
    .mapMultiToLong((job, emit) -> {
        emit.accept(job.startedAt());

        if (job.completedAt() > 0) {
            emit.accept(job.completedAt());
        }

        if (job.lastHeartbeat() > 0) {
            emit.accept(job.lastHeartbeat());
        }
    })
    .toArray();
```

Mỗi job luôn phát thời điểm bắt đầu; thời điểm hoàn tất và heartbeat chỉ được phát nếu có giá trị hợp lệ theo quy ước của ứng dụng. Kết quả vẫn là các số nguyên dài, phù hợp để tiếp tục tính khoảng cách hoặc sắp xếp theo thời gian.

Lưu ý: giá trị `0` ở đây là quy ước dữ liệu của ví dụ để biểu thị mốc chưa có. Với hệ thống thực tế, nên mô hình hóa rõ trạng thái chưa có thời điểm, chẳng hạn bằng `OptionalLong` hoặc trường trạng thái riêng, thay vì mặc định mọi ứng dụng đều dùng epoch zero theo cách này.

## 6. Tiếp tục xử lý bằng các phép toán của LongStream

`mapMultiToLong` trả về `LongStream`, vì vậy có thể dùng trực tiếp các thao tác chuyên biệt cho `long`:

| Thao tác | Công dụng |
|---|---|
| `sum()` | Tính tổng và trả về `long` |
| `average()` | Tính trung bình và trả về `OptionalDouble` |
| `min()` / `max()` | Tìm giá trị nhỏ nhất/lớn nhất và trả về `OptionalLong` |
| `count()` | Đếm số phần tử |
| `summaryStatistics()` | Thu thập count, sum, min, max và average |
| `toArray()` | Thu kết quả vào `long[]` |
| `boxed()` | Chuyển thành `Stream<Long>` khi API phía sau cần object |

Ví dụ tính tổng byte đã truyền và nhận:

```java
long totalBytes = samples.stream()
    .mapMultiToLong((sample, emit) -> {
        if (sample.bytesSent() > 0) {
            emit.accept(sample.bytesSent());
        }

        if (sample.bytesReceived() > 0) {
            emit.accept(sample.bytesReceived());
        }
    })
    .sum();
```

Với dữ liệu ở mục 3, tổng là `16_700_000_000L`. Không cần tạo `Long[]` hoặc `List<Long>` chỉ để cộng các giá trị.

Để lấy nhiều chỉ số thống kê cùng lúc:

```java
import java.util.LongSummaryStatistics;

LongSummaryStatistics statistics = samples.stream()
    .mapMultiToLong((sample, emit) -> {
        if (sample.bytesSent() > 0) {
            emit.accept(sample.bytesSent());
        }

        if (sample.bytesReceived() > 0) {
            emit.accept(sample.bytesReceived());
        }
    })
    .summaryStatistics();
```

Với cùng dữ liệu, thống kê có bốn phần tử, tổng `16_700_000_000`, nhỏ nhất `1_200_000_000` và lớn nhất `8_000_000_000`. Nếu Stream rỗng, `sum()` trả về `0`, còn `average()`, `min()` và `max()` trả về các Optional rỗng tương ứng.

## 7. Chú ý tràn số khi tính tổng long

Kiểu `long` có phạm vi lớn hơn `int`, nhưng vẫn có giới hạn. `LongStream.sum()` thực hiện phép cộng trên `long`; nếu tổng vượt `Long.MAX_VALUE` hoặc nhỏ hơn `Long.MIN_VALUE`, kết quả có thể tràn và quay vòng theo biểu diễn số nguyên có dấu. Phương thức không tự báo lỗi tràn.

Nếu tổng có thể vượt phạm vi `long`, cần chọn cách biểu diễn phù hợp với yêu cầu, chẳng hạn cộng bằng `BigInteger`:

```java
import java.math.BigInteger;
import java.util.List;

List<Long> values = List.of(
    Long.MAX_VALUE,
    1L
);

BigInteger exactTotal = values.stream()
    .map(BigInteger::valueOf)
    .reduce(BigInteger.ZERO, BigInteger::add);
```

Trong ví dụ này, `BigInteger` giữ chính xác tổng lớn hơn `Long.MAX_VALUE`. Nếu từng giá trị nguồn vốn đã vượt phạm vi `long`, phải dùng kiểu dữ liệu phù hợp ngay từ đầu; `mapMultiToLong` không thể khôi phục độ chính xác đã mất khi ép kiểu.

## 8. So sánh mapMultiToLong, mapMulti và mapToLong

Các phương thức này có hình dạng đầu ra khác nhau:

| Phương thức | Mapper phát/trả về | Kiểu Stream kết quả |
|---|---|---|
| `mapMulti` | `Consumer<R>` nhận object kiểu `R` | `Stream<R>` |
| `mapMultiToLong` | `LongConsumer` nhận `long` | `LongStream` |
| `mapToLong` | Mapper trả về đúng một `long` | `LongStream` |

Dùng `mapToLong` khi mỗi phần tử nguồn luôn tạo đúng một số nguyên dài:

```java
long[] sizes = nodes.stream()
    .mapToLong(node -> node.objectSizes().stream()
        .mapToLong(Long::longValue)
        .sum())
    .toArray();
```

Dùng `mapMultiToLong` khi một phần tử nguồn có thể phát không hoặc nhiều giá trị:

```java
long[] allSizes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .toArray();
```

Nếu dùng `mapMulti` để phát các đối tượng `Long`, kiểu đầu ra là `Stream<Long>`:

```java
List<Long> allSizes = nodes.stream()
    .<Long>mapMulti((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .toList();
```

Khi các bước tiếp theo là tính tổng, min, max hoặc thống kê số học, `mapMultiToLong` thường phù hợp hơn vì giữ kết quả trong `LongStream`. Nếu API đích cần object `Long`, có thể dùng `mapMulti` hoặc chuyển từ `LongStream` bằng `boxed()`.

## 9. So sánh với flatMapToLong

`flatMapToLong` phù hợp khi mapper tự nhiên trả về một `LongStream` cho mỗi phần tử nguồn. Với danh sách kích thước của các node, có thể viết:

```java
import java.util.List;

List<Long> allSizes = nodes.stream()
    .flatMapToLong(node ->
        node.objectSizes().stream().mapToLong(Long::longValue)
    )
    .boxed()
    .toList();
```

Nếu kết quả cần là mảng `long[]`, bỏ bước `boxed()` và gọi `toArray()` trực tiếp:

```java
long[] allSizes = nodes.stream()
    .flatMapToLong(node ->
        node.objectSizes().stream().mapToLong(Long::longValue)
    )
    .toArray();
```

Cùng dữ liệu có thể được làm phẳng bằng `mapMultiToLong`:

```java
long[] allSizes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .toArray();
```

Chọn `flatMapToLong` khi phép biến đổi tự nhiên tạo ra một `LongStream` và muốn kết hợp các thao tác trên Stream con. Chọn `mapMultiToLong` khi việc duyệt collection con bằng vòng lặp hoặc các nhánh điều kiện thể hiện logic rõ ràng hơn.

`mapMultiToLong` thường phù hợp với số lượng đầu ra nhỏ cho mỗi phần tử nguồn. Nếu một phần tử có thể phát một lượng rất lớn hoặc không giới hạn giá trị, hãy cân nhắc `flatMapToLong` với một Stream con. Không mặc định rằng một phương thức luôn nhanh hơn phương thức còn lại; hiệu năng phụ thuộc dữ liệu, mapper, JDK và các thao tác tiếp theo.

## 10. Vì sao dùng LongConsumer thay vì Consumer<Long>?

`Consumer<Long>` nhận object wrapper `Long`, trong khi `LongConsumer` nhận trực tiếp giá trị nguyên thủy `long`.

| Đặc điểm | `Consumer<Long>` | `LongConsumer` |
|---|---|---|
| Kiểu nhận | `Long` | `long` |
| Kiểu Stream tương ứng | `Stream<Long>` | `LongStream` |
| Boxing ở đầu ra | Có thể phát sinh khi chuyển `long` thành `Long` | Không cần boxing để gọi `accept(long)` |
| Phép toán số học chuyên biệt | Cần chuyển đổi hoặc unbox | Có sẵn trên `LongStream` |

Ví dụ dùng `Consumer<Long>`:

```java
import java.util.List;

List<String> ids = List.of("customer-100", "customer-200");

List<Long> lengths = ids.stream()
    .<Long>mapMulti((id, emit) -> {
        emit.accept((long) id.length());
    })
    .toList();
```

Ví dụ dùng `LongConsumer`:

```java
import java.util.List;
import java.util.stream.LongStream;

List<String> ids = List.of("customer-100", "customer-200");

LongStream lengths = ids.stream()
    .mapMultiToLong((id, emit) -> {
        emit.accept(id.length());
    });
```

Primitive specialization có thể giảm boxing và unboxing trong pipeline. Tuy nhiên, nếu nguồn dữ liệu là collection `Long`, việc đọc phần tử có thể vẫn cần unbox; nếu terminal operation yêu cầu `List<Long>`, bước `boxed()` sẽ tạo lại wrapper. Hãy xét toàn bộ pipeline thay vì chỉ một thao tác riêng lẻ.

## 11. Chuyển từ LongStream sang object khi cần

Nếu các phép toán số học đã hoàn tất và bước tiếp theo cần object, có thể dùng `mapToObj` hoặc `boxed()`.

Ví dụ tạo nhãn cho từng kích thước:

```java
import java.util.List;

List<String> labels = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .mapToObj(size -> "bytes=" + size)
    .toList();
```

Nếu chỉ cần danh sách `Long`, dùng `boxed()`:

```java
List<Long> boxedSizes = nodes.stream()
    .mapMultiToLong((node, emit) -> {
        for (long size : node.objectSizes()) {
            emit.accept(size);
        }
    })
    .boxed()
    .toList();
```

Chỉ chuyển sang object khi kiểu tham chiếu cần thiết cho API hoặc mô hình dữ liệu tiếp theo. Nếu pipeline chỉ tính toán số học, giữ `LongStream` sẽ tránh boxing không cần thiết.

## 12. Các biến thể primitive liên quan

Stream API có ba phương thức chuyên biệt cùng mô hình:

- `mapMultiToInt` dùng `IntConsumer` và trả về `IntStream`.
- `mapMultiToLong` dùng `LongConsumer` và trả về `LongStream`.
- `mapMultiToDouble` dùng `DoubleConsumer` và trả về `DoubleStream`.

Hãy chọn kiểu theo miền giá trị của dữ liệu:

- Dùng `int` khi giá trị nằm trong phạm vi số nguyên 32-bit.
- Dùng `long` cho số đếm, kích thước hoặc thời điểm có thể vượt giới hạn `int`.
- Dùng `double` cho đại lượng cần biểu diễn số thực dấu phẩy động.

Không ép một giá trị sang `long` chỉ để sử dụng `mapMultiToLong` nếu kiểu gốc hoặc độ chính xác cần thiết là kiểu khác. Primitive specialization giúp tránh wrapper, nhưng không thay đổi giới hạn biểu diễn của kiểu số.

## 13. Đặc tính lazy và lưu ý khi sử dụng

`mapMultiToLong` là thao tác trung gian. Mapper chỉ được thực thi khi terminal operation tiêu thụ pipeline, chẳng hạn `sum()`, `toArray()`, `count()` hoặc `summaryStatistics()`.

Nếu terminal operation có khả năng dừng sớm, pipeline có thể không xử lý toàn bộ phần tử nguồn. Không dựa vào mapper để thực hiện tác dụng phụ bắt buộc phải xảy ra đúng một lần cho mọi phần tử.

Với parallel Stream, mapper của các phần tử nguồn khác nhau có thể chạy đồng thời. Hãy phát kết quả độc lập theo từng phần tử, không cập nhật một mảng hoặc collection mutable dùng chung từ mapper. Gọi `emit.accept` ngay trong callback; không lưu `LongConsumer` để gọi sau khi mapper kết thúc hoặc từ tác vụ bất đồng bộ.

## 14. Lỗi thường gặp

**Dùng Consumer<Long> khi cần LongConsumer.** `mapMultiToLong` yêu cầu `LongConsumer`. Gọi `emit.accept(longValue)` với giá trị nguyên thủy.

**Nghĩ rằng mapper phải trả về long.** Mapper là `BiConsumer`, không trả về kết quả. Mỗi giá trị phải được phát qua `emit.accept`.

**Chỉ gọi accept một lần dù cần phát nhiều giá trị.** Một phần tử nguồn có thể gọi `accept` nhiều lần. Đặt lời gọi trong vòng lặp hoặc các nhánh tương ứng.

**Dùng mapMultiToLong cho phép biến đổi một-một đơn giản.** Nếu mỗi phần tử luôn tạo đúng một giá trị `long`, `mapToLong` thường ngắn gọn hơn.

**Dùng mapMultiToLong khi mapper tự nhiên tạo LongStream.** Nếu đã có một Stream con phù hợp, `flatMapToLong` có thể thể hiện ý định rõ hơn.

**Giả định tổng long không thể tràn.** `LongStream.sum()` không tự kiểm tra overflow. Nếu tổng có thể vượt phạm vi `long`, hãy dùng cách tính chính xác phù hợp như `BigInteger`.

**Boxing sớm rồi unbox lại.** Tránh chuyển sang `Stream<Long>` nếu các bước tiếp theo chỉ cần phép toán trên `LongStream`.

**Giả định mapMultiToLong luôn nhanh hơn flatMapToLong.** Hãy đo trên dữ liệu và môi trường thực tế khi cần tối ưu.

## 15. Ghi nhớ

- `mapMultiToLong` nhận mapper có kiểu `BiConsumer<? super T, ? super LongConsumer>`.
- `LongConsumer.accept(long)` phát một giá trị nguyên thủy `long` vào `LongStream`.
- Không gọi `accept` để phần tử nguồn không tạo kết quả; gọi nhiều lần để phát nhiều giá trị.
- Dùng `mapMultiToLong` khi logic phát số bằng vòng lặp hoặc nhiều nhánh là tự nhiên và số kết quả trên mỗi phần tử ở mức nhỏ.
- Dùng `mapToLong` cho phép biến đổi một-một; dùng `flatMapToLong` khi mapper tự nhiên tạo một `LongStream`.
- `LongStream` hỗ trợ `sum`, `average`, `min`, `max`, `count` và `summaryStatistics`.
- `LongConsumer` giúp phát `long` mà không cần đóng gói mỗi giá trị thành `Long` ở đầu ra.
- Tổng kiểu `long` vẫn có thể tràn; dùng `BigInteger` nếu cần tổng chính xác vượt phạm vi `long`.
- Dùng `boxed()` hoặc `mapToObj` khi bước tiếp theo cần object.

Khi dữ liệu đầu ra là số nguyên dài và mỗi phần tử nguồn có thể phát không, một hoặc nhiều giá trị, `mapMultiToLong` kết hợp với `LongConsumer` tạo nên pipeline rõ ràng, tận dụng các phép toán của `LongStream` và hạn chế boxing không cần thiết.

