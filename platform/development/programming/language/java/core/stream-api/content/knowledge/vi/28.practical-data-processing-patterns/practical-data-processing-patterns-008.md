# Tạo histogram và phân khoảng giá trị

Trong xử lý dữ liệu thực tế, một danh sách số đôi khi khó mang lại thông tin tổng quan. Ví dụ có hàng nghìn thời gian phản hồi API, điểm kiểm tra, kích thước đơn hàng hoặc giá trị đo cảm biến: thay vì xem từng con số, ta muốn biết **bao nhiêu phần tử rơi vào từng khoảng**. Đó là tư duy tạo **histogram** (bảng phân bố tần suất) và **phân khoảng giá trị** (*bucketing/binning*).

Bài học thuộc chương **Mẫu xử lý dữ liệu thực tế** của module `JAVA_STREAM_API`. Ta sẽ thiết kế các khoảng đúng ranh giới, chọn giữa `groupingBy`/`counting` và bộ tích lũy nguyên thủy, xử lý giá trị âm, điểm nằm ngoài miền, khoảng có độ rộng khác nhau, `double` đặc biệt, nhóm không có phần tử, và cân nhắc hiệu năng, bộ nhớ, song song, nguồn I/O. Các pipeline đều dựa trên tư duy khai báo `filter`, `map`, `collect`; khi cần tổng hợp nhiều chỉ số ta cũng sẽ đối chiếu với `reduce` và `summaryStatistics`.

> Các ví dụ Java chính dùng API có từ **Java 8**. Mỗi đoạn mã là một ví dụ độc lập hoặc sử dụng biến/hàm đã giới thiệu ở phần trước. Chọn giới hạn khoảng và chính sách với giá trị không hợp lệ là **quyết định nghiệp vụ**, không phải mặc định của Java Stream API.

## 1. Histogram khác gì danh sách hoặc grouping thông thường?

Giả sử có các điểm kiểm tra:

```text
0, 9, 10, 18, 20, 45, 57, 60, 76, 88, 99, 100, -5, 120
```

Nếu chỉ tính `average()`, ta biết một giá trị trung bình nhưng chưa biết điểm tập trung ở đâu. Nếu dùng `distinct()`, ta biết các điểm khác nhau nhưng cũng chưa biết tần suất theo mức. Histogram giải quyết câu hỏi khác:

> Trong từng mức 0–9, 10–19, ..., 90–100 có **bao nhiêu điểm hợp lệ**?

Ví dụ bảng tần suất:

| Khoảng điểm | Số lượng |
| --- | ---: |
| 0–9 | 2 |
| 10–19 | 2 |
| 20–29 | 1 |
| 30–39 | 0 |
| 40–49 | 1 |
| 50–59 | 1 |
| 60–69 | 1 |
| 70–79 | 1 |
| 80–89 | 1 |
| 90–100 | 2 |

Tổng số điểm thuộc miền `0..100` là **12**. Hai giá trị `-5` và `120` nằm ngoài miền nên cần một chính sách: loại bỏ, đếm riêng hoặc coi là lỗi dữ liệu. Không được lặng lẽ đưa chúng vào một khoảng hợp lệ nếu báo cáo cần phân biệt lỗi đo.

Một histogram có thể gồm ba thành phần:

1. **Quy tắc phân khoảng:** ánh xạ mỗi giá trị vào một khóa khoảng.
2. **Bộ đếm:** cộng 1 cho khoảng tương ứng.
3. **Biểu diễn:** nhãn khoảng, số lượng, tần suất tương đối hoặc biểu đồ.

Phân khoảng là bước tạo **khóa**; histogram là kết quả **thống kê số lượng theo khóa đó**. Nếu sau này cần tổng, trung bình hoặc min/max cho mỗi khoảng, ta có thể giữ cùng quy tắc phân khoảng và đổi downstream collector.

## 2. Xác định ranh giới trước khi viết code

Quy ước dễ sử dụng nhất là khoảng **đóng ở bên trái, mở ở bên phải**:

```text
[0, 10)    chứa 0, 1, ..., 9
[10, 20)   chứa 10, 11, ..., 19
[20, 30)   chứa 20, 21, ..., 29
...
[90, 100)  chứa 90, ..., 99
```

Với quy ước này, điểm nằm đúng ranh giới như `10` chỉ thuộc **một** khoảng, không bị đếm hai lần. Công thức cho giá trị nguyên không âm trong miền bắt đầu tại 0:

```java
int width = 10;
int bucketIndex = value / width;
```

Tuy nhiên, dữ liệu ví dụ cho phép điểm **100** và muốn đúng **10 nhóm**. Nếu dùng `100 / 10`, ta nhận chỉ số 10, vượt các nhóm có chỉ số `0..9`.

Có hai lựa chọn hợp lệ nhưng khác ngữ nghĩa:

| Chính sách | Miền hợp lệ | Cách biểu diễn điểm 100 |
| --- | --- | --- |
| **Mười khoảng đều rộng 10** | `[0,100)` | 100 thuộc nhóm ngoài miền hoặc khoảng thứ 11 |
| **Mười mức điểm, mức cuối bao gồm 100** | `[0,100]` | Nhóm cuối là `90–100`, rộng hơn các nhóm trước một giá trị nguyên |

Bài ví dụ điểm số chọn **chính sách thứ hai** và ghi rõ ngoại lệ của nhóm cuối. Không gọi tất cả nhóm là những khoảng số nguyên có kích thước hoàn toàn bằng nhau trong chính sách này.

Với dữ liệu thực, hãy ghi rõ các quyết định: cận dưới/cận trên có bao gồm không; khoảng dưới/ngoài miền được đếm ở đâu; và báo cáo có cần hiển thị nhóm đếm bằng 0 hay không.

## 3. Histogram với groupingBy và counting

Khi các giá trị đã nằm trong `int[]`, có thể dùng `Arrays.stream` để tạo `IntStream` rồi `boxed()` thành `Stream<Integer>` trước khi gọi `Collectors.groupingBy`:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

int[] scores = {
        0, 9, 10, 18, 20, 45, 57,
        60, 76, 88, 99, 100, -5, 120
};

Map<Integer, Long> countsByBucket = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.groupingBy(
                score -> Math.min(score / 10, 9),
                TreeMap::new,
                Collectors.counting()
        ));

System.out.println(countsByBucket.get(0)); // 2
System.out.println(countsByBucket.get(1)); // 2
System.out.println(countsByBucket.get(9)); // 2
System.out.println(countsByBucket.get(3)); // null
```

Phân tích pipeline:

- `filter` chỉ giữ điểm trong miền hợp lệ `0..100`.
- `boxed()` chuyển `IntStream` sang `Stream<Integer>`, vì `groupingBy` là Collector dành cho Stream của object.
- Hàm phân khoảng `Math.min(score / 10, 9)` tạo khóa từ 0 tới 9; riêng 100 được đưa vào khóa 9.
- `Collectors.counting()` đếm các phần tử trong mỗi khoảng.
- `TreeMap::new` khiến các khóa số được duyệt theo thứ tự tăng dần.

**Cảnh báo:** `groupingBy` chỉ tạo khóa đã thực sự gặp. Không có điểm nào thuộc 30–39 nên Map **không có khóa 3**; `get(3)` trả `null` chứ không trả `0L`.

Nếu muốn hiển thị đủ 10 khoảng:

```java
for (int i = 0; i < 10; i++) {
    int lower = i * 10;
    String label = (i == 9)
            ? "90-100"
            : lower + "-" + (lower + 9);

    long count = countsByBucket.getOrDefault(i, 0L);
    System.out.println(label + ": " + count);
}
```

`getOrDefault` chỉ trả giá trị dự phòng; nó **không thêm** nhóm vắng vào Map. Nếu một API báo cáo yêu cầu đầy đủ 10 khóa, hãy tạo Map báo cáo mới hoặc bổ sung các khóa tường minh.

### Vì sao không dùng toMap hai tham số?

Nếu hai điểm khác nhau rơi vào cùng một khoảng, `Collectors.toMap(keyMapper, valueMapper)` sẽ gặp **khóa trùng** và ném `IllegalStateException`. Có thể dùng overload có `Long::sum` làm merge function, nhưng `groupingBy(..., counting())` diễn đạt “đếm theo nhóm” trực tiếp hơn:

```java
Map<Integer, Long> alternative = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.toMap(
                score -> Math.min(score / 10, 9),
                score -> 1L,
                Long::sum
        ));
```

Hai cách đều cho tần suất theo chỉ số khoảng; loại Map, thứ tự và các đặc tính có thể khác nếu không chỉ rõ factory.

## 4. Histogram nguyên thủy bằng IntStream.collect ba tham số

Với số lượng khoảng **ít và cố định**, không nhất thiết phải boxing từng `int` hoặc tạo các đối tượng khóa. `IntStream` hỗ trợ `collect` nhận **supplier**, **accumulator** và **combiner**.

Để vừa đếm 10 mức điểm, vừa giữ số phần tử ngoài miền, ta dành:

- Chỉ số `0..9`: 10 khoảng điểm;
- Chỉ số `10`: điểm dưới 0;
- Chỉ số `11`: điểm trên 100.

```java
import java.util.Arrays;

int[] scores = {
        0, 9, 10, 18, 20, 45, 57,
        60, 76, 88, 99, 100, -5, 120
};

long[] histogram = Arrays.stream(scores)
        .collect(
                () -> new long[12],
                (counts, score) -> {
                    if (score < 0) {
                        counts[10]++;
                    } else if (score > 100) {
                        counts[11]++;
                    } else {
                        counts[Math.min(score / 10, 9)]++;
                    }
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(histogram));
// [2, 2, 1, 0, 1, 1, 1, 1, 1, 2, 1, 1]
```

Ở đây `long[]` là **bộ tích lũy mutable**, còn `long` giữ số lần xuất hiện. Ba tham số phải thỏa hợp đồng:

| Tham số | Trong ví dụ | Tại sao cần |
| --- | --- | --- |
| Supplier | `() -> new long[12]` | Mỗi lần gọi cấp mảng đếm **mới**, khởi tạo 0 |
| Accumulator | Phân loại một `int` rồi tăng đúng một ô | Mỗi phần tử đi vào đúng một nhóm |
| Combiner | Cộng từng ô của mảng bên phải vào bên trái | Gộp kết quả các nhánh khi chạy song song |

Không dùng một mảng `long[]` tạo bên ngoài và trả lại cùng instance từ Supplier. Khi chạy song song, từng nhánh cần trạng thái riêng theo hợp đồng của `IntStream.collect`; chia sẻ mảng thường có thể gây **data race** và làm kết quả sai.

Ví dụ dùng cùng Collector với nguồn song song:

```java
long[] parallelHistogram = Arrays.stream(scores)
        .parallel()
        .collect(
                () -> new long[12],
                (counts, score) -> {
                    int index = score < 0 ? 10
                            : score > 100 ? 11
                            : Math.min(score / 10, 9);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.equals(histogram, parallelHistogram));
// true
```

Vì mỗi ô được cộng độc lập, phép gộp không phụ thuộc cách phân nhánh (trong phạm vi không tràn `long`). Tuy nhiên, parallel **không mặc nhiên nhanh hơn**. Với 14 số và 12 ô, chi phí chia/gộp mảng có thể lớn hơn thời gian xử lý.

### Khi nào chọn mảng thay vì Map?

| Tình huống | Mảng `long[]` | `Map<K,Long>` |
| --- | --- | --- |
| Số khoảng cố định, ít | Thường hợp lý | Có thể dùng nhưng nhiều đối tượng hơn |
| Khoảng được đánh số liên tục | Truy cập trực tiếp theo chỉ số | Cần mã hóa khóa |
| Khoảng thưa, số lượng chưa biết | Dễ lãng phí bộ nhớ | Thường linh hoạt hơn |
| Nhãn là chuỗi hoặc cấu trúc phức tạp | Cần lớp ánh xạ chỉ số ↔ nhãn | Khóa có thể biểu diễn trực tiếp |
| Chạy song song | Mỗi nhánh có mảng riêng rồi gộp | Combiner có thể gộp Map |
| Muốn thống kê nhiều đại lượng mỗi nhóm | Cần thiết kế container/DTO | Downstream collector đa dạng |

Đừng chọn mảng chỉ vì muốn “tối ưu”: nếu tên khoảng hoặc ranh giới thay đổi liên tục theo cấu hình, Map/DTO có thể dễ bảo trì hơn.

## 5. Đếm đầy đủ, đếm hợp lệ và tỷ lệ phần trăm

Một histogram dùng cho báo cáo cần xác định rõ **mẫu số**. Từ mảng trên:

```java
long validCount = 0L;
for (int i = 0; i < 10; i++) {
    validCount += histogram[i];
}

long belowRange = histogram[10];
long aboveRange = histogram[11];
long totalInput = validCount + belowRange + aboveRange;

System.out.println(validCount); // 12
System.out.println(belowRange); // 1
System.out.println(aboveRange); // 1
System.out.println(totalInput); // 14
```

Nếu báo cáo tỷ trọng từng mức điểm **trên các điểm hợp lệ**, tính:

```java
for (int i = 0; i < 10; i++) {
    double percent = validCount == 0L
            ? Double.NaN
            : 100.0 * histogram[i] / validCount;
    System.out.printf("bucket %d: %.2f%%%n", i, percent);
}
```

Chọn `Double.NaN` cho trường hợp mẫu số bằng 0 ở đây là **một quyết định biểu diễn**: “không xác định vì không có điểm hợp lệ”. Nếu ứng dụng muốn hiển thị `"N/A"` hoặc trả `OptionalDouble.empty()`, có thể thiết kế kiểu kết quả phù hợp. Tránh hiển thị 0% như thể đã thống kê từ một tập có dữ liệu.

Đặc biệt, tổng tỷ trọng có thể hiển thị 99,99% hoặc 100,01% do **làm tròn từng nhóm**. Hãy giữ số lượng nguyên làm dữ liệu gốc; phần trăm chỉ là một dạng trình bày.

Có thể dùng `LongStream.of(histogram).limit(10).sum()` để cộng các ô hợp lệ, nhưng một vòng lặp rõ ràng như trên thường đơn giản trong phần trình bày báo cáo.

## 6. Giá trị âm: dùng Math.floorDiv, không chỉ phép chia /

Khi các khoảng bắt đầu từ 0 và dữ liệu có số âm, phép chia nguyên trong Java **làm tròn về 0**, không phải làm tròn xuống. Điều này khiến cách viết `value / 10` phân khoảng sai với các giá trị âm.

```java
System.out.println(-1 / 10);                 // 0  (không đúng nhóm [-10, 0))
System.out.println(Math.floorDiv(-1, 10));   // -1
System.out.println(Math.floorDiv(-10, 10));  // -1
System.out.println(Math.floorDiv(-11, 10));  // -2
```

Nếu các khoảng có độ rộng 10 và gốc 0:

```text
bucket -3 = [-30, -20)
bucket -2 = [-20, -10)
bucket -1 = [-10,   0)
bucket  0 = [  0,  10)
bucket  1 = [ 10,  20)
bucket  2 = [ 20,  30)
```

Dữ liệu kiểm tra:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

int[] changes = {
        -21, -20, -11, -10, -1, 0, 9, 10, 19, 20
};

Map<Integer, Long> frequency = Arrays.stream(changes)
        .boxed()
        .collect(Collectors.groupingBy(
                value -> Math.floorDiv(value, 10),
                TreeMap::new,
                Collectors.counting()
        ));

System.out.println(frequency);
// {-3=1, -2=2, -1=2, 0=2, 1=2, 2=1}
```

Với mỗi khóa `bucket`, nhãn khoảng có thể được tính trên `long` để tránh tràn khi nhân khóa với độ rộng:

```java
for (Map.Entry<Integer, Long> entry : frequency.entrySet()) {
    long lower = (long) entry.getKey() * 10L;
    long upper = lower + 10L;

    System.out.printf(
            "[%d, %d): %d%n",
            lower, upper, entry.getValue()
    );
}
```

**Lưu ý:** đối với dữ liệu nguyên với gốc khác 0, hãy xét độ lệch `value - origin`. Nếu hai toán hạng có thể gần hai đầu miền `int`, trừ trên `int` có thể tràn. Ta có thể nâng phép trừ lên `long` trước rồi mới chia:

```java
static long uniformBucket(int value, int origin, int width) {
    if (width <= 0) {
        throw new IllegalArgumentException("width must be positive");
    }

    long offset = (long) value - origin;
    return Math.floorDiv(offset, (long) width);
}
```

Cách này xử lý các khoảng có gốc bất kỳ, bao gồm cả khi `value` âm hoặc `origin` âm, mà không phụ thuộc vào cách làm tròn về 0 của phép chia `int`.

## 7. Khoảng có độ rộng không đều

Không phải mọi histogram đều chia thành các đoạn bằng nhau. Ví dụ phân mức thời gian phản hồi API:

```text
[0, 100)      phản hồi rất nhanh
[100, 300)    phản hồi nhanh
[300, 1000)   phản hồi chậm
[1000, 5000)  phản hồi rất chậm
ngoài miền     lỗi đo hoặc cảnh báo riêng
```

Ta có thể mô tả ranh giới bằng mảng tăng nghiêm ngặt:

```java
int[] edges = {0, 100, 300, 1000, 5000};
```

Quy tắc: phần tử có giá trị bằng ranh giới trái thì **thuộc nhóm bắt đầu tại ranh giới đó**, còn giá trị bằng ranh giới trên cuối cùng (`5000`) **nằm ngoài tất cả khoảng**.

### Tìm khoảng bằng binarySearch

Với các ranh giới tăng dần và không trùng nhau:

```java
import java.util.Arrays;

static int findBucket(int value, int[] edges) {
    // Giả định edges đã được kiểm tra: ít nhất 2 phần tử,
    // tăng nghiêm ngặt, và không bị sửa khi xử lý.
    int pos = Arrays.binarySearch(edges, value);

    if (pos >= 0) {
        // Bằng cận trái của một khoảng, trừ cận trên cuối cùng.
        return pos == edges.length - 1 ? -1 : pos;
    }

    // Mã kết quả âm của binarySearch chứa insertion point.
    int insertionPoint = -pos - 1;
    int index = insertionPoint - 1;

    return index >= 0 && index < edges.length - 1
            ? index
            : -1;
}

static void validateEdges(int[] edges) {
    if (edges == null || edges.length < 2) {
        throw new IllegalArgumentException(
                "At least two edges required"
        );
    }

    for (int i = 1; i < edges.length; i++) {
        if (edges[i] <= edges[i - 1]) {
            throw new IllegalArgumentException(
                    "Edges must be strictly increasing"
            );
        }
    }
}
```

`Arrays.binarySearch` trả vị trí của giá trị nếu khớp ranh giới, hoặc số âm mã hóa **vị trí có thể chèn** nếu không khớp. Vì có `k` khoảng với `k+1` ranh giới, mỗi lần tìm có chi phí khoảng `O(log k)`.

**Quan trọng:** hãy chạy `validateEdges(edges)` **một lần trước khi tạo pipeline**, không kiểm tra toàn bộ cấu hình cho từng phần tử. Mảng `edges` cần được giữ cố định trong suốt quá trình Stream xử lý; thay đổi nó đồng thời làm quy tắc phân khoảng không ổn định.

### Thu thập vào mảng đếm

```java
import java.util.Arrays;

int[] edges = {0, 10, 25, 50, 100};
int[] values = {0, 9, 10, 24, 25, 49, 50, 99, -1, 100};

validateEdges(edges);

long[] counts = Arrays.stream(values)
        .collect(
                () -> new long[edges.length - 1],
                (acc, value) -> {
                    int index = findBucket(value, edges);
                    if (index >= 0) {
                        acc[index]++;
                    }
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(counts));
// [2, 2, 2, 2]
```

Chính sách ví dụ là **loại các giá trị ngoài miền**. Hai phần tử `-1` và `100` không được đếm trong bốn khoảng. Nếu cần đối chiếu số lượng bản ghi, nên có hai ô riêng cho underflow/overflow như phần 4, hoặc một bộ báo cáo lưu cả số lượng hợp lệ và không hợp lệ.

### Cảnh báo khi so sánh các khoảng có độ rộng khác nhau

Một khoảng rộng có thể chứa nhiều phần tử chỉ vì **nó rộng hơn**. Nếu muốn so sánh mật độ trên trục số liên tục, cần cân nhắc dùng **mật độ tần suất** thay vì chỉ so sánh chiều cao đếm:

```text
tần suất tương đối của nhóm = count / validCount
mật độ trong một khoảng     = count / (validCount * độ rộng khoảng)
```

Bởi vậy, với các khoảng `[0,10)` và `[10,100)`, cùng có 20 phần tử không có nghĩa hai vùng có mật độ bằng nhau. Mật độ là khái niệm thống kê riêng, và cách vẽ biểu đồ cần phản ánh đúng độ rộng khoảng để người xem không bị hiểu nhầm.

## 8. Dữ liệu double: NaN, vô cực và sai số tại ranh giới

Với `DoubleStream`, phân khoảng cần kiểm tra thêm **giá trị đặc biệt**:

- `Double.NaN` không có vị trí bình thường trên trục số.
- `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` không thuộc miền hữu hạn.
- Số thực có sai số biểu diễn; phép chia cho độ rộng như `0.1` có thể tạo kết quả sát ranh giới nhưng không đúng như kỳ vọng toán học.
- `-0.0` và `0.0` cần một quy tắc hiển thị nhất quán nếu chúng có ý nghĩa khác trong miền ứng dụng.

Ví dụ nguồn:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] samples = {
        0.4, 1.0, 2.2, 2.9,
        3.1, -0.1,
        Double.NaN,
        Double.POSITIVE_INFINITY
};

long[] buckets = DoubleStream.of(samples)
        .filter(Double::isFinite)
        .filter(value -> value >= 0.0 && value < 3.0)
        .collect(
                () -> new long[3],
                (counts, value) -> {
                    int index = (int) Math.floor(value);
                    counts[index]++;
                },
                (left, right) -> {
                    for (int i = 0; i < left.length; i++) {
                        left[i] += right[i];
                    }
                }
        );

System.out.println(Arrays.toString(buckets));
// [1, 1, 2]
```

Các khoảng của ví dụ là `[0,1)`, `[1,2)` và `[2,3)`. Có bốn mẫu hợp lệ, bốn mẫu bị loại (hai ngoài miền, một NaN và một vô cực). Nếu lỗi đo là thông tin quan trọng, hãy ghi lại các nhóm bị loại thay vì chỉ lọc mất dữ liệu.

**Về `DoubleStream.collect`:** API nhận ba tham số như `IntStream.collect` nhưng accumulator có kiểu `ObjDoubleConsumer<R>`. Không thể gọi `DoubleStream.collect(Collectors.groupingBy(...))` trực tiếp; muốn dùng Collector thông thường, phải chuyển sang `Stream<Double>` hoặc `mapToObj(...)`.

### Phân khoảng thập phân chính xác

Đối với giá trị tiền tệ, `0.1` và `0.01` biểu diễn dưới dạng `double` có thể không chính xác tuyệt đối. Nếu ranh giới phải chính xác theo nghiệp vụ:

- Lưu giá trị dưới dạng `long` theo đơn vị nhỏ nhất (đồng, cent, milliunit...), rồi phân khoảng trên số nguyên; hoặc
- Dùng `BigDecimal` và phép so sánh `compareTo` theo các ranh giới đã xác định.

Không dùng ép kiểu `(int) value` như một thay thế phổ quát cho `Math.floor`, vì ép từ số thực về `int` cắt phần thập phân theo hướng 0 và có giới hạn miền giá trị.

## 9. Nhóm không có phần tử cần được hiển thị rõ

Với `groupingBy(..., counting())`, Map chỉ chứa khóa được thấy. Nếu báo cáo luôn phải hiển thị các mức tần suất, có thể dựng Map theo thứ tự từ cấu hình thay vì cố suy từ Map đã thu thập:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Long> report = new LinkedHashMap<>();

for (int i = 0; i < 10; i++) {
    int lower = i * 10;
    String label = i == 9
            ? "90-100"
            : lower + "-" + (lower + 9);

    report.put(label, countsByBucket.getOrDefault(i, 0L));
}

System.out.println(report.get("30-39")); // 0
System.out.println(report.containsKey("30-39")); // true
```

Đây là **một Map báo cáo mới** có đủ các nhãn khoảng, kể cả khoảng không có dữ liệu. `LinkedHashMap` giữ thứ tự chèn nên có thể in bảng theo 0–9, 10–19, ... 90–100, thay vì dựa vào thứ tự duyệt của `HashMap`.

Đừng nhầm `getOrDefault(i, 0L)` với việc Map gốc tự có nhóm đó; phương thức chỉ trả một giá trị dự phòng. Việc bổ sung nhóm trống là trách nhiệm của tầng báo cáo hoặc logic cấu hình.

Nếu ứng dụng cần phân biệt **“khoảng chưa được quan sát”** với **“khoảng được đo nhưng số lượng bằng 0”**, phải lưu thêm trạng thái nguồn dữ liệu hoặc kỳ đo. Chỉ một giá trị số `0` không đủ để khẳng định nguyên nhân.

## 10. Histogram so với partitioningBy và summaryStatistics

Các API tổng hợp có hình dạng kết quả khác nhau:

| Mục tiêu | Cách làm phù hợp | Đặc điểm |
| --- | --- | --- |
| Chỉ cần min, max, count, sum, average | `IntStream.summaryStatistics()` | Không tạo các bucket |
| Chỉ chia hai nhóm theo điều kiện | `Collectors.partitioningBy(predicate)` | Luôn có khóa `true` và `false` |
| Nhiều khoảng hoặc nhiều loại | `groupingBy(classifier, counting())` | Số nhóm linh hoạt |
| Nhiều khoảng cố định, đánh chỉ số liên tiếp | `IntStream.collect` với `long[]` | Tránh boxing từng phần tử |
| Cần nhiều phần tử gốc trong từng khoảng | `groupingBy(classifier)` | Giữ `List<T>` nên tốn bộ nhớ hơn |
| Cần thống kê nhiều chỉ số trong mỗi khoảng | `groupingBy(classifier, downstream)` hoặc container tùy chỉnh | Chọn downstream theo dữ liệu cần có |

Ví dụ nếu chỉ quan tâm **đạt hoặc không đạt** ngưỡng 50:

```java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

Map<Boolean, Long> passFail = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .boxed()
        .collect(Collectors.partitioningBy(
                score -> score >= 50,
                Collectors.counting()
        ));

System.out.println(passFail.get(true));  // 6
System.out.println(passFail.get(false)); // 6
```

`partitioningBy` tự cung cấp cả hai khóa Boolean ngay cả khi một nhánh không có phần tử. Nhưng khi cần 10 mức điểm, nó không thay cho một phép phân khoảng nhiều nhóm.

Để lấy thống kê miền hợp lệ mà không tạo histogram:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = Arrays.stream(scores)
        .filter(score -> score >= 0 && score <= 100)
        .summaryStatistics();

System.out.println(stats.getCount()); // 12
System.out.println(stats.getMin());   // 0
System.out.println(stats.getMax());   // 100
```

Có thể dùng cả histogram và summary statistics trong cùng báo cáo, nhưng hai phép terminal riêng biệt trên một nguồn **không thể tái sử dụng cùng instance Stream**. Với mảng, tạo hai Stream mới được; với tệp I/O hoặc nguồn một lần, cần thiết kế bộ tích lũy chung nếu muốn chỉ đọc một lượt.

## 11. Dữ liệu thiếu, ngoại lệ và chính sách nhập liệu

Nguồn `IntStream` không chứa `null`, nhưng danh sách wrapper `List<Integer>` có thể chứa null. Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;

List<Integer> rawScores = Arrays.asList(10, null, 20, 30);

IntStream validValues = rawScores.stream()
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue);
```

Biểu thức này chủ động **loại giá trị vắng mặt**. Nếu cần đếm số bản ghi bị thiếu, không nên dùng riêng pipeline như vậy rồi coi tổng sau lọc bằng tổng đầu vào.

Một mô hình báo cáo rõ nghĩa có thể có:

```text
totalRows
missingCount
invalidBelowCount
invalidAboveCount
validCount
bins[0..k-1]
```

Khi thu thập từ `List<Integer>` có null, người viết có thể dùng `Stream<Integer>.collect` với container riêng để phân loại `null` và số hợp lệ trong một lượt. Đây là dạng **mutable reduction**: Supplier phải tạo container mới, accumulator cập nhật đúng trường, combiner gộp từng trường khi chạy parallel.

Nếu đơn vị dữ liệu là số thực, còn phải tách riêng `NaN` và `Infinity`. Nếu một giá trị nằm ngoài giới hạn cấu hình, hãy quyết định **bỏ qua, báo lỗi, ghi nhóm ngoài miền hay giới hạn cứng (clamp)**. Clamp mọi giá trị ngoài miền vào nhóm đầu/cuối có thể tạo biểu đồ trông hợp lệ nhưng che giấu lỗi đo.

Đối với phép đếm tăng rất lớn, `long` có giới hạn. Đối với phép tính tổng trong mỗi bucket, `int`/`long` cũng có thể tràn. Chọn kiểu số và chính sách kiểm tra tràn theo quy mô dữ liệu.

## 12. Mẫu histogram cho luồng sự kiện thực tế

Giả sử dịch vụ giám sát cần theo dõi độ trễ (mili giây) của các yêu cầu API. Những khoảng mức độ phục vụ được quy định:

```text
[0, 100)      rất nhanh
[100, 300)    bình thường
[300, 1000)   chậm
[1000, 5000)  rất chậm
ngoài miền    đo lỗi hoặc giá trị cần điều tra
```

Để biểu diễn kết quả với các nhãn rõ ràng, tạo một bộ xử lý hoàn chỉnh:

```java
import java.util.Arrays;

final class LatencyHistogram {
    private static final int[] EDGES = {0, 100, 300, 1000, 5000};

    static long[] summarize(int[] latencyMillis) {
        int[] edges = EDGES; // cấu hình bất biến trong lúc xử lý

        long[] result = Arrays.stream(latencyMillis)
                .collect(
                        () -> new long[edges.length + 1],
                        (counts, value) -> {
                            int index = findBucket(value, edges);

                            if (index >= 0) {
                                counts[index]++;
                            } else if (value < edges[0]) {
                                counts[edges.length - 1]++;
                            } else {
                                counts[edges.length]++;
                            }
                        },
                        (left, right) -> {
                            for (int i = 0; i < left.length; i++) {
                                left[i] += right[i];
                            }
                        }
                );

        return result;
    }

    private static int findBucket(int value, int[] edges) {
        int pos = Arrays.binarySearch(edges, value);
        if (pos >= 0) {
            return pos == edges.length - 1 ? -1 : pos;
        }

        int insertionPoint = -pos - 1;
        int index = insertionPoint - 1;
        return index >= 0 && index < edges.length - 1
                ? index
                : -1;
    }
}
```

Ví dụ:

```java
int[] latencies = {20, 90, 100, 250, 299, 300, 999, 1000, 6000, -3};

long[] report = LatencyHistogram.summarize(latencies);

System.out.println(Arrays.toString(report));
// [2, 3, 2, 1, 1, 1]
```

Mảng kết quả có bốn ô cho khoảng hợp lệ, một ô dưới miền và một ô trên miền. Chỉ số ngoài miền được tính từ `edges.length - 1` và `edges.length`, không trộn với các khoảng hợp lệ.

Với bộ ranh giới `{0,100,300,1000,5000}`, có **4 khoảng**, nên độ dài mảng là `4 + 2 = 6`. Cách tính `new long[edges.length + 1]` phù hợp vì `edges.length = 5`.

Ví dụ phân loại:

- 20 và 90 → `[0,100)`: 2.
- 100, 250 và 299 → `[100,300)`: 3.
- 300 và 999 → `[300,1000)`: 2.
- 1000 → `[1000,5000)`: 1.
- 6000 → trên miền: 1.
- -3 → dưới miền: 1.

**Ghi chú triển khai:** lớp chứa phiên bản `findBucket` tương đương hàm đã học ở phần 7 để ví dụ có thể dùng độc lập. `EDGES` là mảng cấu hình biết trước, tăng nghiêm ngặt và **không được sửa** khi xử lý. Nếu cấu hình đến từ tệp, hãy sao chép nó, chạy `validateEdges` một lần và quản lý như dữ liệu bất biến trong suốt lượt thống kê.

## 13. Cân nhắc song song và hiệu năng

Với histogram, công việc mỗi phần tử thường khá nhẹ: xác định khóa và tăng bộ đếm. Có một số cách xử lý, mỗi cách có đánh đổi:

| Cách tiếp cận | Điểm mạnh | Chi phí hoặc giới hạn |
| --- | --- | --- |
| `IntStream` tuần tự + `long[]` | Ít object, dễ hiểu, ghi vào một mảng | Một luồng xử lý |
| `IntStream.parallel().collect(...)` với mảng riêng | Có thể chia việc, combiner cộng các mảng | Tạo nhiều mảng và cộng `O(k)` theo số lần gộp |
| `Stream<Integer>.collect(groupingBy(..., counting()))` | Linh hoạt với nhóm động, downstream | Boxing và Map/Long trung gian |
| `groupingByConcurrent(..., counting())` | Phù hợp khi không cần encounter order và số nhóm linh hoạt | Có thể tranh chấp khi nhiều giá trị vào cùng khóa |
| Tự ghi `sharedCounts[index]++` trong `parallel().forEach(...)` | Trông ngắn | **Không an toàn** vì tăng không nguyên tử |

Ví dụ **không được dùng** với parallel:

```java
long[] sharedCounts = new long[10];

// SAI: nhiều luồng có thể cập nhật cùng một ô mà không đồng bộ.
Arrays.stream(scores)
        .parallel()
        .filter(s -> s >= 0 && s <= 100)
        .forEach(s -> sharedCounts[Math.min(s / 10, 9)]++);
```

Mỗi biểu thức `x++` là đọc–tăng–ghi, không phải phép toán nguyên tử; số đếm có thể thấp hơn thực tế.

Thay bằng `IntStream.collect` có Supplier tạo mảng riêng và combiner gộp từng ô như phần 4. Nếu thực sự cần cấu trúc chia sẻ đồng thời, có thể dùng `AtomicLongArray` hoặc các bộ đếm đồng thời thích hợp, nhưng việc đồng bộ có overhead và không nhất thiết tốt hơn mảng cục bộ.

**Một lưu ý về thứ tự:** histogram tần suất thuần túy thường không cần encounter order vì phép đếm là giao hoán. Tuy nhiên, nếu một bucket đồng thời lưu **ba phần tử đầu tiên** hoặc một chuỗi mô tả theo thứ tự xuất hiện, kết quả không còn đơn thuần là histogram và cần quy tắc bảo toàn thứ tự.

Kích thước bộ nhớ cũng quan trọng:

- Mảng đếm `k` khoảng cần `O(k)` trạng thái cho mỗi bộ tích lũy.
- Map đếm chỉ cần lưu các khoảng đã xuất hiện, thường `O(số khóa thực tế)`.
- `groupingBy(...)` mặc định lưu danh sách phần tử trong từng nhóm, có thể cần `O(n)` bộ nhớ cho phần tử nguồn.
- Với cửa sổ thời gian lăn (rolling histogram), phải quyết định cách loại giá trị cũ, không thể chỉ cộng mãi vào cùng histogram nếu muốn đại diện cho một cửa sổ hữu hạn.

Chỉ chạy benchmark trên JDK và khối lượng dữ liệu đại diện sau khi thuật toán đã đúng với tất cả biên.

## 14. Nguồn I/O và histogram không giữ toàn bộ dữ liệu

Với một tệp chứa **mỗi dòng là số nguyên** biểu thị độ trễ, có thể xây histogram ngay khi đọc, tránh nạp toàn bộ tệp thành List:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long[] readHistogram(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .mapToInt(Integer::parseInt)
                .collect(
                        () -> new long[12],
                        (counts, value) -> {
                            int index = value < 0 ? 10
                                    : value > 100 ? 11
                                    : Math.min(value / 10, 9);
                            counts[index]++;
                        },
                        (left, right) -> {
                            for (int i = 0; i < left.length; i++) {
                                left[i] += right[i];
                            }
                        }
                );
    }
}
```

Giả định tất cả dòng không rỗng đều là số nguyên hợp lệ; nếu dòng có chữ hoặc vượt miền `int`, `Integer.parseInt` sẽ ném `NumberFormatException`. Hệ thống thật cần chính sách ghi nhận số dòng lỗi, loại bỏ hoặc dừng xử lý.

Điều quan trọng là `Files.lines` tạo một Stream **giữ tài nguyên**, nên phải đóng bằng `try-with-resources`. Terminal `collect` **không tự đóng tệp**; cả khi dữ liệu rỗng, lỗi parse hoặc downstream dừng sớm, vẫn cần giải phóng nguồn.

Một số lỗi I/O xảy ra khi duyệt lazy có thể xuất hiện dưới dạng `UncheckedIOException`. Nên phân biệt chúng với lỗi định dạng dữ liệu, không bắt mọi ngoại lệ rồi biến thành một histogram toàn số 0, vì làm như vậy có thể che giấu tệp bị hỏng.

## 15. Bài tập thực hành và tiêu chí kiểm thử

### Bài tập A: histogram điểm số có hai nhóm ngoại lệ

Viết một phương thức nhận `int[]` và trả mảng `long[12]` theo hợp đồng của phần 4. Dùng dữ liệu:

```java
int[] sample = {0, 9, 10, 99, 100, -1, 101};
```

Kết quả mong đợi:

```text
bucket 0 (0-9)      = 2
bucket 1 (10-19)    = 1
bucket 9 (90-100)   = 2
underflow           = 1
overflow            = 1
tất cả bucket khác  = 0
tổng số phần tử     = 7
```

Điều kiện đạt: số lượng ở các bucket và hai ô ngoại lệ cộng lại đúng bằng độ dài nguồn; kết quả giống nhau ở pipeline tuần tự và song song.

### Bài tập B: khoảng âm và ranh giới

Dùng `Math.floorDiv` với độ rộng 10:

```java
int[] samples = {-11, -10, -1, 0, 9, 10};
```

Kết quả:

```text
[-20,-10) -> 1
[-10,  0) -> 2
[  0, 10) -> 2
[ 10, 20) -> 1
```

Hãy giải thích vì sao `-1 / 10` không thể thay cho `Math.floorDiv(-1, 10)`.

### Bài tập C: khoảng không đều

Với `edges = {0,10,25,50,100}`, xác minh:

```text
findBucket(-1)   = -1
findBucket(0)    = 0
findBucket(9)    = 0
findBucket(10)   = 1
findBucket(24)   = 1
findBucket(25)   = 2
findBucket(49)   = 2
findBucket(50)   = 3
findBucket(99)   = 3
findBucket(100)  = -1
```

Thử truyền ranh giới trùng hoặc giảm dần và xác minh `validateEdges` từ chối cấu hình.

### Bài tập D: đếm histogram nhiều mức độ trễ

Mở rộng `LatencyHistogram` để trả một đối tượng gồm `total, accepted, underflow, overflow` và `bins`. Ghi nhãn từ `edges`, đếm số trường hợp dưới/trên miền, rồi xuất một bảng có cả nhóm số lượng bằng 0. Khi dùng báo cáo trong môi trường thật, hãy định nghĩa điều gì xảy ra nếu cấu hình ranh giới thay đổi giữa hai lượt chạy.

## 16. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `value / width` cho số âm | `-1` có thể rơi vào bucket 0 | Dùng `Math.floorDiv` |
| Không quy định điểm bằng cận trên | Đếm sai `100` hoặc tạo bucket thừa | Chọn `[min,max)` hoặc ngoại lệ nhóm cuối tường minh |
| Đưa outlier vào nhóm cuối không báo | Che giấu dữ liệu không hợp lệ | Underflow/overflow riêng hoặc báo lỗi |
| Dùng `groupingBy` và mong mọi khoảng đều có key | Bucket rỗng không xuất hiện | Bổ sung từ cấu hình hoặc dùng mảng |
| `toMap` hai tham số cho nhiều giá trị chung khoảng | `IllegalStateException` do khóa trùng | `groupingBy(counting)` hoặc merge function |
| `Map.get(missingKey)` rồi coi null là 0 | Có thể gây `NullPointerException` hoặc nhầm nghĩa | `getOrDefault` hoặc biểu diễn dữ liệu rỗng rõ ràng |
| Lấy phần trăm chia cho toàn bộ đầu vào nhưng ghi “trên điểm hợp lệ” | Tỷ trọng không khớp định nghĩa | Xác định mẫu số và ghi nhãn |
| `counts[index]++` từ `parallel().forEach` | Data race, mất lần đếm | Bộ tích lũy riêng qua `collect` |
| Supplier trả cùng mảng mutable trong các nhánh | Tranh chấp hoặc gộp chính nó | Tạo mảng mới mỗi lần |
| `Double.NaN` hoặc Infinity không được kiểm tra | Quy tắc phân khoảng không rõ | Kiểm tra `Double.isFinite` |
| Cắt `double` sang `int` để “làm tròn xuống” | Sai với số âm, có thể vượt miền | `Math.floor` và xác thực miền |
| Tạo bins từ ranh giới chưa sắp xếp | Binary search trả nhóm sai | `validateEdges` trước pipeline |
| Sửa mảng edges khi pipeline đang chạy | Các giá trị cùng miền có thể vào nhóm khác nhau | Cấu hình bất biến trong lượt xử lý |
| Dùng `groupingBy` mặc định để giữ tất cả bản ghi khi chỉ cần count | Bộ nhớ `O(n)` không cần thiết | Downstream `counting` hoặc `long[]` |
| Dùng `parallel()` chỉ vì dữ liệu là số | Overhead có thể vượt lợi ích | Đo sau khi thuật toán đúng |
| Đọc `Files.lines` mà không đóng | Giữ tài nguyên I/O | `try-with-resources` |

## 17. Câu hỏi tự kiểm tra

1. Histogram trả lời câu hỏi gì? **Số lượng hoặc tỷ lệ phần tử nằm trong từng khoảng giá trị**.
2. Quy ước `[10,20)` có nhận giá trị 20 không? **Không**, nhưng nhận 10.
3. Trong chính sách 10 mức điểm 0–100, tại sao điểm 100 cần xử lý riêng? **Vì 100/10 = 10, vượt chỉ số 0..9**.
4. Vì sao `groupingBy(counting())` có thể không có khóa của một khoảng? **Vì không phần tử nào tạo ra khóa đó**.
5. Khi nào cần `boxed()`? **Khi chuyển IntStream thành Stream<Integer> để dùng Collector object như groupingBy**.
6. Vì sao `IntStream.collect` dùng ba hàm? **Nó tạo bộ tích lũy mutable, tích lũy từng int và gộp hai bộ chứa**.
7. Mảng `long[12]` trong ví dụ dùng hai ô cuối cho gì? **Điểm dưới 0 và điểm trên 100**.
8. Vì sao `Math.floorDiv(-1,10)` đúng hơn `-1/10`? **Vì nó làm tròn xuống về -1, đúng khoảng [-10,0)**.
9. Nhãn của một nhóm số âm có chỉ số -2, gốc 0 và bước 10 là gì? **[-20,-10)**.
10. Với mảng ranh giới, giá trị đúng bằng cận trái vào nhóm nào? **Nhóm bắt đầu tại cận đó**, trừ cận trên cuối cùng nằm ngoài miền.
11. Tại sao nên kiểm tra mảng ranh giới trước pipeline? **Vì binarySearch yêu cầu tăng dần và việc kiểm tra mỗi giá trị rất lãng phí**.
12. `Double.NaN` nên đưa vào bucket 0 không? **Không**, cần chính sách missing/invalid riêng.
13. Nếu các khoảng rộng khác nhau, chỉ so sánh raw count có thể gây nhầm gì? **Khoảng rộng thường chứa nhiều điểm hơn dù mật độ thấp**.
14. `partitioningBy` có thay `groupingBy` khi cần 10 khoảng không? **Không**, nó chỉ phân thành true/false.
15. Nếu chỉ cần count theo bucket, tại sao không nên `groupingBy` mặc định ra List? **Vì nó giữ các phần tử trong bộ nhớ không cần thiết**.
16. Có thể cập nhật chung một `long[]` bằng `parallel().forEach` an toàn không? **Không**, tăng ô mảng không nguyên tử.
17. Khi nguồn là `Files.lines`, `collect` có tự đóng tệp không? **Không**, phải dùng `try-with-resources`.

**Nguyên tắc áp dụng:** Tạo histogram đúng bắt đầu từ **định nghĩa khoảng và ranh giới**, rồi mới chọn `groupingBy(..., counting())` hay `IntStream.collect` với mảng đếm. Hãy quy định rõ nhóm rỗng, điểm biên, giá trị âm, outlier, dữ liệu thiếu và mẫu số của tỷ lệ phần trăm. Khi tối ưu, bảo đảm accumulator/combiner đúng hợp đồng, cấu hình bất biến, nguồn I/O được đóng, và chỉ dùng parallel khi phép đo trên dữ liệu thực cho thấy lợi ích.
