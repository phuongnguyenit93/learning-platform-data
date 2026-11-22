# Kiểm thử tính lười và số phần tử thực sự được duyệt trong Java Stream

> **Phạm vi:** Stream API được giới thiệu từ Java 8 và vẫn được dùng trong Java hiện đại. Ví dụ chỉ dùng các API Stream phổ biến, còn hiệu lực; mã chạy với JDK 17+ (đã kiểm tra trên OpenJDK 24). Trọng tâm là **làm sao kiểm chứng thời điểm xử lý và số lần từng phép biến đổi thực sự được gọi**, thay vì suy luận từ số phần tử đầu ra.

## 1. Phân biệt bốn đại lượng dễ nhầm

Một pipeline có dạng `nguồn → thao tác trung gian → thao tác kết thúc`, ví dụ:

```java
int first = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 3 == 0)
        .map(n -> n * 10)
        .findFirst()
        .orElse(-1); // 30
```

Các con số sau **không đồng nghĩa**:

1. **Số phần tử từ nguồn cần xét:** bao nhiêu giá trị đầu vào phải được lấy để xác định kết quả.
2. **Số lần gọi predicate của `filter`:** mỗi giá trị đến `filter` được kiểm tra bao nhiêu lần.
3. **Số lần gọi mapper của `map`:** chỉ các giá trị vượt qua `filter` mới đến `map`; thao tác trung gian có thể bị tối ưu bỏ qua nếu không ảnh hưởng kết quả.
4. **Số phần tử kết quả:** với `findFirst` tối đa một, dù có thể phải kiểm tra nhiều phần tử đầu vào.

Trong ví dụ trên với **stream tuần tự có thứ tự**, giá trị 1 và 2 không đạt `filter`, giá trị 3 đạt, được biến thành 30, rồi `findFirst` dừng. Vì thế có **3 lần kiểm tra `filter`, 1 lần gọi `map`, 1 kết quả**. Không thể lấy số lượng kết quả làm số lượng phần tử đã duyệt.

## 2. Tính lười (lazy evaluation) hoạt động thế nào?

- `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit` tạo các bước *trung gian*. Việc khai báo chúng **chưa** khiến pipeline đọc dữ liệu hay gọi lambda để xử lý phần tử.
- `findFirst`, `anyMatch`, `collect`, `toArray`, `forEach`, `count` là các thao tác *kết thúc* (terminal); khi chúng được gọi, pipeline mới có thể bắt đầu xử lý để tạo kết quả.
- Với các bước không lưu trạng thái như `filter` và `map`, một stream tuần tự thường xử lý **theo từng phần tử qua các bước**: lấy một phần tử, lọc, biến đổi, chuyển đến terminal; không bắt buộc lọc toàn bộ nguồn trước rồi mới map toàn bộ.
- **Short-circuit** là khả năng dừng sau khi đã có đủ thông tin. `findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` là terminal có thể dừng sớm; `limit(n)` là bước trung gian có thể giới hạn luồng.
- Sau khi terminal tiêu thụ, **không sử dụng lại cùng một đối tượng Stream**. Nếu muốn chạy phép thử mới, tạo stream mới từ nguồn.

Lưu ý: “lazy” **không có nghĩa** mỗi pipeline luôn duyệt ít phần tử. Nếu không có cơ hội dừng sớm, nếu cần kết quả từ mọi phần tử, hoặc có bước lưu trạng thái cần nhiều dữ liệu, số phần tử phải xử lý vẫn có thể bằng toàn bộ nguồn.

## 3. Phòng thí nghiệm Java: đo ngay trước và sau terminal

Lưu nguyên khối sau vào tệp **`StreamLazinessLab.java`**:

```java
import java.util.Arrays;
import java.util.OptionalInt;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

public class StreamLazinessLab {
    public static void main(String[] args) {
        AtomicInteger inspected = new AtomicInteger();
        AtomicInteger mapped = new AtomicInteger();

        // Khai báo pipeline: lambda chưa được gọi.
        IntStream pipeline = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    inspected.incrementAndGet();
                    return n % 3 == 0;
                })
                .map(n -> {
                    mapped.incrementAndGet();
                    return n * 10;
                });

        System.out.println("Before: inspected=" + inspected.get()
                + ", mapped=" + mapped.get());

        // Terminal: dừng ở số chia hết cho 3 đầu tiên.
        OptionalInt first = pipeline.findFirst();
        System.out.println("First=" + first.orElse(-1)
                + ", inspected=" + inspected.get()
                + ", mapped=" + mapped.get());

        // filter rồi limit: cần tìm đủ HAI số chia hết cho 3.
        AtomicInteger afterFilter = new AtomicInteger();
        int[] firstTwo = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    afterFilter.incrementAndGet();
                    return n % 3 == 0;
                })
                .limit(2)
                .toArray();
        System.out.println("Filter then limit=" + Arrays.toString(firstTwo)
                + ", tested=" + afterFilter.get());

        // limit rồi filter: chỉ xét HAI phần tử nguồn đầu tiên.
        AtomicInteger afterLimit = new AtomicInteger();
        int[] none = IntStream.rangeClosed(1, 10)
                .limit(2)
                .filter(n -> {
                    afterLimit.incrementAndGet();
                    return n % 3 == 0;
                })
                .toArray();
        System.out.println("Limit then filter=" + Arrays.toString(none)
                + ", tested=" + afterLimit.get());

        // sorted cần tiếp nhận toàn bộ nguồn hữu hạn trước khi
        // biết phần tử nhỏ nhất; map sau sorted chỉ nhận phần tử cần lấy.
        AtomicInteger beforeSort = new AtomicInteger();
        AtomicInteger afterSort = new AtomicInteger();
        int smallest = IntStream.of(5, 1, 4, 2, 3)
                .map(n -> {
                    beforeSort.incrementAndGet();
                    return n;
                })
                .sorted()
                .map(n -> {
                    afterSort.incrementAndGet();
                    return n;
                })
                .findFirst()
                .orElse(-1);
        System.out.println("Sorted first=" + smallest
                + ", upstream=" + beforeSort.get()
                + ", downstream=" + afterSort.get());

        // count có thể suy ra kích thước mà không gọi peek.
        AtomicInteger peekCalls = new AtomicInteger();
        long count = Arrays.asList("a", "b", "c").stream()
                .peek(s -> peekCalls.incrementAndGet())
                .count();
        System.out.println("Count=" + count + ", peek=" + peekCalls.get());

        // Các kiểm tra có kết quả xác định cho pipeline tuần tự ở trên.
        if (first.orElse(-1) != 30
                || inspected.get() != 3 || mapped.get() != 1
                || !Arrays.equals(firstTwo, new int[] {3, 6})
                || afterFilter.get() != 6
                || none.length != 0 || afterLimit.get() != 2
                || smallest != 1
                || beforeSort.get() != 5 || afterSort.get() != 1
                || count != 3) {
            throw new AssertionError("Unexpected pipeline behavior");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac StreamLazinessLab.java
java StreamLazinessLab
```

**Stdout thực tế trên OpenJDK 24:**

```text
Before: inspected=0, mapped=0
First=30, inspected=3, mapped=1
Filter then limit=[3, 6], tested=6
Limit then filter=[], tested=2
Sorted first=1, upstream=5, downstream=1
Count=3, peek=0
Checks passed.
```

Dòng `peek=0` là ví dụ về một **tối ưu hóa hợp lệ**, không phải cam kết của mọi bản JDK; tuyệt đối không tạo unit test đòi `peek` phải chạy chính xác 0 hoặc 3 lần trong pipeline `count()` này. Những kiểm tra còn lại gắn với kết quả và chuỗi xử lý tuần tự đã định rõ trong ví dụ.

## 4. Đọc trace: chính xác những phần tử nào đi qua pipeline?

Với `rangeClosed(1, 10).filter(n -> n % 3 == 0).map(n -> n * 10).findFirst()`:

| Phần tử nguồn | `filter` gọi? | Đạt điều kiện? | `map` gọi? | Điều xảy ra |
| --- | --- | --- | --- | --- |
| 1 | Có | Không | Không | Tiếp tục |
| 2 | Có | Không | Không | Tiếp tục |
| 3 | Có | Có | Có, thành 30 | `findFirst` nhận 30, dừng |
| 4…10 | Không | — | Không | Chưa cần duyệt |

Bài học: phép đếm đặt ở **đầu pipeline** và ở **sau `filter`** đo hai việc khác nhau. Nếu đặt counter trong `filter`, biến `inspected` đo số **lần gọi predicate**, không mặc nhiên là số phần tử cuối cùng. Trong pipeline tuần tự đơn giản này, ba lần gọi predicate tương ứng với ba phần tử nguồn được xét.

### Vị trí của `limit` làm thay đổi cả kết quả lẫn khối lượng xử lý

| Pipeline tuần tự trên 1…10 | Kết quả | Số lần gọi `filter` |
| --- | --- | --- |
| `filter(n % 3 == 0).findFirst()` | 3 | 3 |
| `filter(n % 3 == 0).limit(2).toArray()` | [3, 6] | 6 |
| `limit(2).filter(n % 3 == 0).toArray()` | [] | 2 |
| `filter(n > 100).findFirst()` | rỗng | 10 |

- `filter → limit(2)` cần đi qua 1, 2, 3, 4, 5, 6 mới có hai giá trị **hợp lệ** là 3 và 6.
- `limit(2) → filter` chỉ cho 1 và 2 đi qua; cả hai bị loại, nên kết quả rỗng.
- Khi **không tồn tại kết quả phù hợp**, `findFirst` phải xét hết nguồn hữu hạn trong ví dụ để xác nhận không tìm thấy.

Không hoán đổi thứ tự các bước chỉ để tiết kiệm chi phí nếu việc hoán đổi làm đổi ý nghĩa dữ liệu.

## 5. Khi “lười” vẫn phải đọc hết: `sorted` và thao tác lưu trạng thái

`sorted()` là bước trung gian **stateful**. Để chắc chắn giá trị nhỏ nhất trong `[5, 1, 4, 2, 3]` là 1, nó phải tiếp nhận toàn bộ năm phần tử trước khi phát kết quả có thứ tự. Vì thế:

```text
IntStream.of(5,1,4,2,3)
  -> map (đếm trước sorted: 5)
  -> sorted (cần toàn bộ dữ liệu đầu vào)
  -> map (đếm sau sorted: 1)
  -> findFirst (trả 1)
```

`limit(1)` hoặc `findFirst()` **đặt sau `sorted()` không biến việc sắp xếp toàn bộ thành tìm kiếm một phần tử đầu tiên từ nguồn**. Với nguồn vô hạn, `sorted().findFirst()` có thể không bao giờ hoàn tất vì không có điểm kết thúc để biết thứ tự toàn cục.

`distinct()` cũng là stateful, nhưng mức xử lý phụ thuộc dữ liệu và phép kết thúc. Ví dụ luồng tuần tự `[1, 1, 2, 2, 3] → distinct() → limit(2)` phải xem ba giá trị nguồn đầu tiên mới xuất được hai giá trị duy nhất `[1, 2]`. Khi có dữ liệu trùng lặp, số giá trị đầu vào thường lớn hơn số kết quả.

## 6. Các terminal dừng sớm: đo điều kiện dừng, không suy từ tên hàm

Trong các minh họa sau, dùng nguồn **tuần tự có thứ tự** `IntStream.rangeClosed(1, 10)`, không thêm bước stateful:

| Terminal | Khi nào có thể dừng? | Ví dụ số phần tử cần xét |
| --- | --- | --- |
| `findFirst()` sau `filter(n -> n == 4)` | Tìm được phần tử phù hợp đầu tiên | 4 |
| `anyMatch(n -> n >= 5)` | Gặp giá trị trả `true` đầu tiên | 5 |
| `allMatch(n -> n < 5)` | Gặp giá trị trả `false` đầu tiên | 5 |
| `noneMatch(n -> n == 4)` | Gặp giá trị trả `true` đầu tiên | 4 |
| `anyMatch(n -> n > 100)` | Không có kết quả đúng: cần xét hết | 10 |
| `forEach(...)` | Không phải short-circuit terminal | Thông thường toàn bộ 10 |

Các biểu thức `anyMatch`, `allMatch`, `noneMatch` lần lượt trả `false`, `true`, `true` trên **stream rỗng** mà không gọi predicate. Không giả định terminal “ngắn” lúc nào cũng dừng sớm: nó chỉ dừng khi đủ dữ kiện xác định đáp án.

`findAny()` được phép chọn phần tử bất kỳ, đặc biệt trong parallel stream. Không dùng `findAny()` để viết test yêu cầu “phải lấy đúng phần tử đầu tiên”; dùng `findFirst()` và giữ encounter order khi điều đó là yêu cầu.

## 7. Thiết kế unit test kiểm chứng laziness và số lần gọi

Một test tốt cần làm rõ *điều đang đo*: trước terminal không gọi predicate; sau một terminal cụ thể thì gọi predicate bao nhiêu lần. Ví dụ dưới đây dùng **JUnit Jupiter (JUnit 5)**, chạy khi dự án đã có dependency/test runner JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class StreamLazinessTest {
    @Test
    void intermediateOperationsAreLazy() {
        AtomicInteger predicateCalls = new AtomicInteger();

        IntStream pipeline = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    predicateCalls.incrementAndGet();
                    return n % 3 == 0;
                });

        assertEquals(0, predicateCalls.get()); // Chỉ mới tạo pipeline
        assertEquals(3, pipeline.findFirst().orElse(-1));
        assertEquals(3, predicateCalls.get()); // Đã xét 1, 2, 3
    }

    @Test
    void limitAfterFilterNeedsTwoMatchingValues() {
        AtomicInteger predicateCalls = new AtomicInteger();

        int[] actual = IntStream.rangeClosed(1, 10)
                .filter(n -> {
                    predicateCalls.incrementAndGet();
                    return n % 3 == 0;
                })
                .limit(2)
                .toArray();

        org.junit.jupiter.api.Assertions.assertArrayEquals(
                new int[] {3, 6}, actual);
        assertEquals(6, predicateCalls.get());
    }
}
```

Ở đây counter chỉ là **thiết bị đo trong test**, không là dữ liệu nghiệp vụ. Trong ứng dụng thực tế, hãy biểu đạt phép tính bằng `filter`/`map`/`collect`/`reduce` thay vì dựa vào việc mutate biến ngoài lambda.

Quy trình thử nghiệm nên gồm:

1. **Dùng nguồn nhỏ, hữu hạn, thứ tự xác định** (`IntStream.rangeClosed`, `List.stream()`).
2. **Tạo counter riêng cho từng bước cần quan sát**; kiểm tra `0` sau bước khai báo và trước terminal.
3. **Chọn terminal minh bạch** như `findFirst`, `anyMatch`, `toArray`; xác định bằng tay khi nào có đủ kết quả.
4. **Assert cả đầu ra và số lần gọi ở bước liên quan**, phân biệt số lần gọi hàm với kích thước kết quả.
5. **Tạo stream mới cho mỗi test**. Không tái sử dụng stream sau terminal.
6. Nếu thay sang parallel, **viết lại kỳ vọng về traversal**, đừng mang nguyên số lần gọi tuần tự sang.

## 8. Những bẫy khiến phép đo sai

### 8.1. `peek` không phải máy đếm phần tử nguồn đáng tin cậy

`peek` hữu ích khi **quan sát tạm thời** một pipeline, nhưng không có hợp đồng bảo đảm callback sẽ chạy cho mọi phần tử mà ta *nghĩ* pipeline có. Stream có quyền lược bỏ các thao tác không cần để cho ra kết quả. Ví dụ:

```java
long size = Arrays.asList("a", "b", "c").stream()
        .peek(System.out::println)
        .count(); // size = 3; có thể không in dòng nào trên JDK hiện đại
```

Khi nguồn có kích thước đã biết và pipeline không làm thay đổi số phần tử, `count()` **có thể tính thẳng kích thước** mà không duyệt và không thực thi `peek` (hành vi được JavaDoc cho phép). Đây là lý do không lấy số lần callback của `peek`/`map` làm chân lý chung về số phần tử nguồn đã đọc, nhất là trong các phép đo hiệu năng.

### 8.2. Side effect và parallel stream làm kỳ vọng số lần gọi kém ổn định

- `parallel()` có thể xử lý các nhánh đồng thời và có thể làm **nhiều việc hơn mức tối thiểu lý thuyết** trước khi short-circuit dừng các nhánh khác.
- `AtomicInteger` chỉ đảm bảo phép tăng an toàn khi có nhiều luồng; nó **không đảm bảo** mỗi callback được gọi đúng số lần như luồng tuần tự, và không ép callback phải được thực thi nếu có tối ưu hóa bỏ qua.
- Không dựa vào thứ tự log của `peek` hoặc `forEach` trong parallel; nếu đầu ra bắt buộc theo encounter order, cân nhắc `forEachOrdered` nhưng vẫn kiểm tra yêu cầu hiệu năng riêng.
- Hành vi có side effect trong `filter`/`map` có thể gây lỗi về thread safety, tính lặp lại và tối ưu hóa. Tránh dùng counter ngoài lambda làm phần logic vận hành.

### 8.3. Đừng đồng nhất “tạo được kết quả” với “đã duyệt đủ dữ liệu”

`limit(5)` có thể tạo kết quả hữu hạn từ `Stream.generate(...)` nếu không có bước cản trở trước nó. Nhưng pipeline với `filter` có thể cần xét nhiều hơn năm phần tử nguồn mới có năm phần tử hợp lệ; với `sorted` trước `limit`, việc đợi toàn bộ nguồn có thể khiến stream vô hạn không kết thúc.

### 8.4. Phạm vi khẳng định khi test

- **Có thể khẳng định:** pipeline tuần tự đã cho trả đúng 30; predicate đã được gọi khi terminal cần đánh giá điều kiện; hai biến đếm trong ví dụ `findFirst` lần lượt là 3 và 1.
- **Không nên khẳng định chung:** mọi pipeline đều thực thi mọi lambda; `count()` luôn gọi `peek`; short-circuit luôn chạm đúng số phần tử tối thiểu trên parallel stream.
- **Khi phải đo chính xác số phần tử đọc ở tầng nguồn:** chọn lớp bao nguồn hoặc một `Spliterator` instrumented có theo dõi cả `tryAdvance` và `forEachRemaining` (và việc chia nhánh nếu chạy parallel), rồi kiểm chứng trên cấu hình JDK/nguồn thực tế. Counter ở `filter` chỉ đo predicate, không thay thế phép đo ở tầng nguồn trong mọi pipeline.

## 9. Câu hỏi tự kiểm tra

1. Vì sao tạo `stream.filter(...).map(...)` mà chưa gọi terminal thì hai counter vẫn bằng 0?
2. Với 1…10, tại sao `filter(n % 3 == 0).limit(2)` phải kiểm tra sáu giá trị nhưng chỉ trả hai giá trị?
3. Vì sao `sorted().findFirst()` vẫn có thể đọc toàn bộ nguồn dù chỉ cần một kết quả?
4. Nếu `list.stream().peek(...).count()` không in gì, đây có chắc là bug của Java không?
5. Vì sao không thể lấy số lần gọi `filter` trong parallel stream làm kiểm chứng cứng giống ví dụ tuần tự?

**Đáp án tóm lược:** (1) intermediate lazy; (2) phải tìm hai kết quả đạt điều kiện, ở vị trí 3 và 6; (3) cần biết thứ tự toàn cục; (4) không, `count` có thể tối ưu bỏ traversal; (5) xử lý song song, short-circuit và tối ưu hóa không cam kết cùng số lần thực thi callback.

## Tài liệu chuẩn còn hiệu lực

- [Java SE 25 — `Stream` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): lazy operations, short-circuit, `count()` và quyền tối ưu bỏ callback.
- [Java SE 25 — `java.util.stream` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): pipeline, stateless/stateful, traversal, side effects và parallel.
- [Dev.java — Terminal Operations](https://dev.java/learn/api/streams/terminal-operations/): ý nghĩa và cách dùng các thao tác kết thúc.

Các khái niệm trên là hợp đồng Stream API vẫn còn áp dụng trên Java hiện đại; khi cần kết quả đo cụ thể, cố định phiên bản JDK, loại nguồn và chế độ tuần tự/song song của chính bài test.
