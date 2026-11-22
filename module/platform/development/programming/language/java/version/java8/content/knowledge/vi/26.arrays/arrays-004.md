# Arrays.parallelSetAll và giới hạn tác dụng phụ (Java 8)

`Arrays.parallelSetAll` là một phương thức của `java.util.Arrays`, có từ Java 8 và **vẫn được hỗ trợ trong Java hiện đại**. Nó gán giá trị cho **từng vị trí trong một mảng có sẵn**, dùng hàm `generator(index)` để tính phần tử tương ứng. Khác với vòng `for` thông thường hay `Arrays.setAll` chạy tuần tự, `Arrays.parallelSetAll` **cho phép nhiều chỉ số được xử lý song song**.

Cách dùng an toàn nhất là để generator trở thành một hàm **xác định, không có tác dụng phụ không được kiểm soát**, chỉ phụ thuộc vào chỉ số và dữ liệu đọc **ổn định**. Một generator đọc những vị trí đang bị cập nhật, tăng một bộ đếm dùng để định giá trị, thêm vào `ArrayList` chung hoặc ghi database theo thứ tự sẽ khiến kết quả phụ thuộc lịch thực thi, tạo data race, mất dữ liệu hoặc làm hiệu năng kém đi.

Bài học tập trung vào **cơ chế hoạt động**, **những side effect được phép và không được phép dựa vào**, **cách viết generator an toàn**, **xử lý exception**, **lựa chọn giữa tuần tự và song song**, và **kiểm thử kết quả độc lập với thứ tự chạy**. Các ví dụ độc lập sử dụng API Java 8, đã kiểm tra biên dịch/chạy ở mức `--release 8`.

## 1. Mô hình tư duy: mỗi index quyết định một phần tử

Giả sử có mảng độ dài 8 và muốn tạo các giá trị bình phương chỉ số:

```java
int[] squares = new int[8];
Arrays.parallelSetAll(squares, index -> index * index);
```

Khi thành công, mảng có giá trị:

```text
index:     0  1  2  3   4   5   6   7
generator: 0  1  4  9  16  25  36  49
result:    0  1  4  9  16  25  36  49
```

**Điều được bảo đảm về kết quả** là mỗi vị trí tương ứng với giá trị generator dành cho chỉ số đó, giả sử generator tính đúng, không gây xung đột hoặc exception. **Điều không được bảo đảm** là generator cho index 0 chạy trước index 1, hoặc callback chạy trên một thread cố định. Hai tác vụ có thể hoàn thành theo thứ tự khác, trong khi mảng cuối vẫn đúng.

Sơ đồ khái niệm:

```text
Mảng target:     [ ?, ?, ?, ?, ?, ?, ?, ? ]
                     │
        chia các chỉ số 0..length-1
                     │
          ┌──────────┼──────────┐
        nhóm A      nhóm B      nhóm C
          │           │           │
      generator    generator    generator
      (index)      (index)      (index)
          └──────────┼──────────┘
                     │
       ghi giá trị tại chính array[index]
                     │
                target hoàn tất
```

Sơ đồ **không phải lịch thực thi bắt buộc** của một JDK. Số worker, cách chia index và thứ tự callback là chi tiết triển khai; không viết logic dựa trên các giả định đó.

## 2. Bốn overload được hỗ trợ và kiểu generator

Trong Java 8, `Arrays.parallelSetAll` có bốn overload chính:

| Mảng đích | Kiểu hàm generator | Giá trị trả từ lambda |
| --- | --- | --- |
| `T[]` | `IntFunction<? extends T>` | Đối tượng kiểu T hoặc subtype |
| `int[]` | `IntUnaryOperator` | `int` |
| `long[]` | `IntToLongFunction` | `long` |
| `double[]` | `IntToDoubleFunction` | `double` |

Chữ ký API:

```java
// Chữ ký API rút gọn, không phải class Java độc lập.
static <T> void parallelSetAll(
    T[] array, IntFunction<? extends T> generator);

static void parallelSetAll(
    int[] array, IntUnaryOperator generator);

static void parallelSetAll(
    long[] array, IntToLongFunction generator);

static void parallelSetAll(
    double[] array, IntToDoubleFunction generator);
```

**Chi tiết dễ nhầm:**

- Đối số của **tất cả generator đều là chỉ số kiểu `int`**, không phải giá trị hiện tại của mảng.
- Phương thức thay đổi **chính mảng truyền vào**, không tạo mảng mới và trả về `void`.
- Chỉ số hợp lệ chạy từ `0` đến `array.length - 1`. Không có chỉ số cần xử lý nếu độ dài bằng 0.
- Với `T[]`, generator có thể trả `null` nếu kiểu mảng và nghiệp vụ cho phép. Với `int[]`, `long[]`, `double[]`, phần tử là kiểu nguyên thủy nên không có `null`.
- Không có overload tương ứng trực tiếp cho `byte[]`, `short[]`, `char[]`, `boolean[]` hoặc `float[]` trong API này. Khi cần xử lý các loại đó, chọn vòng lặp hoặc cách tiếp cận khác phù hợp.
- Mảng hoặc generator không hợp lệ có thể làm phương thức ném exception; tài liệu `Arrays` quy định `NullPointerException` cho array null (trừ ngoại lệ được nêu) và nêu riêng generator null.
- Phương thức không tự định nghĩa các phép xử lý như sắp xếp hoặc cộng dồn. Nó chỉ hỏi "giá trị tại index này là gì?".

### Phân biệt chỉ số và phần tử

```java
int[] numbers = {100, 200, 300};
Arrays.parallelSetAll(numbers, i -> i + 10);
// Kết quả: [10, 11, 12], KHÔNG phải [110, 210, 310].
```

Trong lời gọi trên, `i` là **0, 1, 2**, không phải **100, 200, 300**. Nếu muốn biến đổi dựa trên giá trị cũ, cần chủ động bảo toàn nguồn trước khi ghi, như ví dụ ở phần sau.

## 3. So sánh Arrays.setAll với Arrays.parallelSetAll

Java 8 cung cấp cặp API tương đương về ý nghĩa **tính giá trị theo chỉ số**:

```java
// Hai mảng khác nhau, cùng generator thuần.
int[] a = new int[8];
int[] b = new int[8];

Arrays.setAll(a, i -> i * i);
Arrays.parallelSetAll(b, i -> i * i);
```

Khi thành công và generator xác định, cả `a` và `b` có cùng nội dung. Khác biệt chính là cách thực thi.

| Khía cạnh | `Arrays.setAll` | `Arrays.parallelSetAll` |
| --- | --- | --- |
| Cách xử lý | Tuần tự theo chỉ số | Có thể thực hiện nhiều index song song |
| Thứ tự gọi generator | Đọc theo tiến trình tuần tự | Không được dựa vào thứ tự cụ thể |
| Generator có side effect phụ thuộc thứ tự | Dù có thể quan sát được, vẫn khó bảo trì | **Không an toàn** nếu dựa vào thứ tự |
| Dữ liệu nhỏ/tính toán nhẹ | Thường đơn giản, ít overhead | Có thể chậm hơn vì chi phí phối hợp |
| Tính toán nặng, độc lập theo index | Không khai thác parallel ở bước này | Có thể có lợi, phải benchmark |
| Đầu ra | Ghi vào mảng đã truyền | Ghi vào mảng đã truyền |
| Khi generator lỗi | Mảng có thể cập nhật một phần | Mảng ở trạng thái không xác định theo hợp đồng |

**Không nên chỉ đổi `setAll` thành `parallelSetAll` mà giữ nguyên một generator có mutable state.** Một hàm hoạt động đúng khi chạy tuần tự có thể không còn đúng khi nhiều callback chạy đồng thời.

## 4. Ví dụ chạy được: int, long, double và Object[]

Tệp **`ParallelSetAllBasicsDemo.java`** tạo các giá trị chỉ từ chỉ số. Nó đối chiếu setAll/parallelSetAll bằng `Arrays.equals`, kiểm tra bốn kiểu mảng và cả mảng độ dài 0.

```java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ParallelSetAllBasicsDemo {
    static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        int[] sequential = new int[8];
        int[] parallel = new int[8];

        Arrays.setAll(sequential, index -> index * index);
        Arrays.parallelSetAll(parallel, index -> index * index);
        require(Arrays.equals(sequential, parallel),
            "same indexed result");

        long[] largeValues = new long[4];
        Arrays.parallelSetAll(
            largeValues, index -> 1_000_000_000L * (index + 1));

        double[] fractions = new double[4];
        Arrays.parallelSetAll(fractions, index -> index * 0.25);

        String[] labels = new String[4];
        Arrays.parallelSetAll(labels,
            index -> (index % 2 == 0)
                ? "item-" + index : null);

        int[] empty = new int[0];
        AtomicInteger emptyCalls = new AtomicInteger();
        Arrays.parallelSetAll(empty, index -> {
            emptyCalls.incrementAndGet();
            return index;
        });
        require(emptyCalls.get() == 0, "empty array");

        System.out.println(
            "sequential=" + Arrays.toString(sequential));
        System.out.println(
            "parallel=" + Arrays.toString(parallel));
        System.out.println(
            "longs=" + Arrays.toString(largeValues));
        System.out.println(
            "doubles=" + Arrays.toString(fractions));
        System.out.println(
            "objects=" + Arrays.toString(labels));
        System.out.println(
            "emptyCalls=" + emptyCalls.get());
        System.out.println("PASS");
    }
}
```

Chạy với JDK 8 trở lên:

```bash
javac -encoding UTF-8 ParallelSetAllBasicsDemo.java
java ParallelSetAllBasicsDemo
```

Hoặc khi dùng JDK mới nhưng muốn kiểm tra chỉ dùng API của Java 8:

```bash
javac --release 8 -encoding UTF-8 ParallelSetAllBasicsDemo.java
java ParallelSetAllBasicsDemo
```

**Stdout đã xác minh:**

```text
sequential=[0, 1, 4, 9, 16, 25, 36, 49]
parallel=[0, 1, 4, 9, 16, 25, 36, 49]
longs=[1000000000, 2000000000, 3000000000, 4000000000]
doubles=[0.0, 0.25, 0.5, 0.75]
objects=[item-0, null, item-2, null]
emptyCalls=0
PASS
```

### Đọc kết quả

1. Bình phương index cho hai mảng `int[]` bằng nhau. Không có lý do kết quả phụ thuộc vào cách chia tác vụ vì biểu thức `index * index` chỉ dùng index.
2. Với mảng `long[]`, số `1_000_000_000L` là long literal; tích được tính trong miền `long`. Không dùng phép nhân `int` rồi mới ép sang long khi giá trị có thể tràn.
3. Với `double[]`, các giá trị 0.0, 0.25, 0.5, 0.75 có biểu diễn nhị phân chính xác ở ví dụ, nên in ổn định.
4. Với `String[]`, việc trả null ở index lẻ là **kết quả được cho phép**, nhưng ứng dụng thực tế cần xác định có muốn cho null đi vào downstream hay không.
5. Với mảng độ dài 0, không có index để xử lý; generator không được gọi. Bộ đếm trong ví dụ chỉ phục vụ **kiểm thử**, không phải đề nghị dùng shared counter để tính kết quả mảng.

## 5. "Giới hạn tác dụng phụ" nghĩa là gì?

Phương thức `Arrays.parallelSetAll` tự nó **phải ghi mảng đích** — đó là side effect chủ đích. Cảnh báo về side effect tập trung vào **hàm generator**.

Một generator lý tưởng:

- Nhận chỉ số `index` và tính giá trị cần đặt ở vị trí đó.
- Chỉ đọc những dữ liệu **không thay đổi trong suốt lời gọi**.
- Không ghi sang index khác, không thay đổi mảng nguồn đang được các callback khác đọc.
- Không cập nhật collection mutable chia sẻ hoặc biến đếm để quyết định giá trị.
- Không phụ thuộc vào thứ tự callback, thread chạy hoặc thời điểm các callback hoàn thành.
- Không làm I/O hoặc side effect bên ngoài không được thiết kế cho việc gọi song song.
- Dễ kiểm tra bằng một hàm tham chiếu: `expected[i] = f(i)`.

Ta có thể gọi đây là tính **stateless/pure tương đối của generator**. Nó vẫn có thể đọc một bảng cấu hình bất biến, một mảng nguồn chỉ-đọc hoặc các hằng số; không nhất thiết chỉ có phép toán số học. Mục tiêu là việc gọi generator ở index nào trước cũng không làm thay đổi giá trị đúng của các index còn lại.

### Mẫu an toàn

```java
// Trong ngữ cảnh có int[] result và final int multiplier.
Arrays.parallelSetAll(result, index -> index * multiplier);
```

Ở đây, mỗi index độc lập. Nếu `multiplier` không đổi, kết quả ổn định. Nếu phép nhân có thể tràn int thì cần xác định chính sách số học, ví dụ dùng `Math.multiplyExact` hoặc đổi mảng đích sang `long[]`.

### Mẫu không an toàn: kết quả phụ thuộc vào counter chung

```java
// PHẢN VÍ DỤ: không dùng làm logic sinh ID theo vị trí.
AtomicInteger next = new AtomicInteger();
int[] ids = new int[1000];

Arrays.parallelSetAll(
    ids, index -> next.incrementAndGet());
```

`AtomicInteger` làm mỗi phép tăng **atomic**, nhưng **không bảo đảm ID 1 được gán index 0, ID 2 vào index 1**. Index nào gọi `incrementAndGet` trước tùy lịch thực thi. Kết quả có thể là một hoán vị của các số được cấp, chứ không có ánh xạ vị trí như mong muốn.

Nếu muốn `ids[i] = i + 1`, hãy viết trực tiếp:

```java
Arrays.parallelSetAll(ids, index -> index + 1);
```

**Thread-safe không đồng nghĩa deterministic theo index.** Sử dụng công cụ đồng bộ chỉ giải quyết tính an toàn của một phép cập nhật; nó không cho thứ tự callback cố định.

## 6. Không ghi vào ArrayList/HashMap chung trong generator

Một lỗi rất phổ biến là dùng generator để vừa sinh mảng vừa thu thập "log" hoặc "kết quả phụ" vào một collection:

```java
// PHẢN VÍ DỤ: side effect lên ArrayList chung.
List<Integer> visited = new ArrayList<>();
int[] output = new int[10000];

Arrays.parallelSetAll(output, index -> {
    visited.add(index); // Không thread-safe.
    return index * 2;
});
```

`ArrayList.add` không an toàn khi nhiều thread cùng gọi trên một instance không được đồng bộ. Hậu quả có thể là thiếu dữ liệu, trạng thái collection không nhất quán hoặc exception; **không có bảo đảm** chỉ vì mọi callback đều ghi phần tử khác nhau trong mảng đích.

Nếu thay bằng `Collections.synchronizedList(...)` hoặc concurrent collection, có thể tránh một số data race nhưng vẫn phát sinh hai vấn đề:

1. **Thứ tự insert không phải thứ tự index.** Không được dùng danh sách log để suy ra `0, 1, 2, ...` theo thứ tự.
2. **Tranh chấp/overhead.** Các callback phải chia sẻ một tài nguyên, giảm lợi ích chia việc.

Nếu thật sự cần dữ liệu phụ có quan hệ một-một với index, hãy dùng **mảng phụ** và chỉ ghi `aux[index]` theo quy tắc độc lập, hoặc thiết kế một giai đoạn thu thập riêng sau khi tính toán. Việc thêm side effect vào generator chỉ để tiết kiệm một lượt duyệt có thể làm ứng dụng khó kiểm soát hơn rất nhiều.

### Việc ghi vào những index khác cũng sai về quyền sở hữu

`Arrays.parallelSetAll` đã có trách nhiệm gán `array[index]`. Nếu generator tự viết:

```java
// PHẢN VÍ DỤ: không được ghi bừa sang ô của callback khác.
Arrays.parallelSetAll(array, i -> {
    if (i + 1 < array.length) {
        array[i + 1] = 0;  // Callback khác có thể ghi cùng ô.
    }
    return i * 10;
});
```

thì giá trị ở index `i+1` có thể bị hai callback tranh nhau ghi. Mảng cuối **không còn bảo đảm phản ánh generator chỉ số** mà bạn mong muốn.

**Hạn chế side effect an toàn:** để API ghi đúng vị trí được giao; generator không chủ động cập nhật target hoặc dữ liệu mutable dùng chung khác.

## 7. Đọc giá trị cũ trong chính mảng đang được ghi là rủi ro lớn

Mục tiêu: từ mảng đầu vào `[2, 4, 6, 8, 10]`, muốn tạo mảng mới bằng cách nhân ba giá trị cũ và cộng chỉ số.

Cách **không nên** làm:

```java
// PHẢN VÍ DỤ: đọc từ cùng mảng đang bị parallelSetAll thay đổi.
int[] data = {2, 4, 6, 8, 10};
Arrays.parallelSetAll(
    data, i -> data[i] * 3 + i);
```

Với câu lệnh này, lambda đọc `data[i]` trong khi chính lời gọi `parallelSetAll` đang cập nhật mảng đó. Với từng index độc lập, có thể tình cờ ra kết quả mong muốn trong một số triển khai, nhưng thiết kế không đưa ra một **snapshot dữ liệu đầu vào bất biến** và trở nên rất nguy hiểm khi mở rộng công thức sang giá trị ở những index khác hoặc thêm writer khác.

Lỗi rõ ràng hơn khi tính tổng phần tử lân cận:

```java
// PHẢN VÍ DỤ: không dùng để tính dựa trên giá trị cũ của hàng xóm.
int[] data = {1, 2, 3, 4};

Arrays.parallelSetAll(data, i ->
    i == 0 ? data[i] : data[i - 1] + data[i]);
```

Nếu callback index 1 đã thay đổi `data[1]` trước khi callback index 2 đọc `data[1]`, index 2 có thể dùng **giá trị mới**; nếu chưa, nó có thể dùng **giá trị cũ**. Các lần chạy có thể tạo kết quả khác nhau. Việc đó khác với phép biến đổi "dựa trên snapshot ban đầu", vốn phải tạo `[1, 3, 5, 7]` cho ví dụ.

### Cách đúng: cố định đầu vào, ghi sang đầu ra riêng

```java
// Mã minh họa: biến source không được thay đổi khi chạy.
int[] source = {2, 4, 6, 8, 10};
int[] snapshot = Arrays.copyOf(source, source.length);
int[] result = new int[source.length];

Arrays.parallelSetAll(
    result, i -> snapshot[i] * 3 + i);
```

Lợi ích:

- `snapshot` **không bị thay đổi** trong suốt phép tính.
- Mỗi callback chỉ đọc `snapshot[i]` và trả giá trị của `result[i]`.
- Các callback không chia sẻ trạng thái ghi ngoài các vị trí đích riêng.
- `source` được giữ nguyên. Nếu generator thất bại, source không bị biến thành mảng nửa cũ nửa mới.
- Có thể kiểm tra `result` độc lập với `source` và với phép xử lý tuần tự.

Nếu nguồn vốn đã bất biến và không có nơi nào khác sửa nó, không cần tạo bản copy chỉ để chứng minh tính bất biến. Trong ví dụ, copy làm điều kiện ownership rõ ràng. Nếu các đối tượng trong mảng nguồn cũng là mutable, copy mảng tham chiếu là **shallow copy**, không tự khiến các object bên trong bất biến.

## 8. Ví dụ hoàn chỉnh: generator độc lập và kiểm thử mảng lớn

Tệp **`IndependentGeneratorDemo.java`** kết hợp mô hình snapshot với kiểm tra 10.000 index. Nó sử dụng một bộ đếm AtomicInteger **chỉ để xác minh số lần callback trong test**, không dùng bộ đếm đó để tính giá trị mảng.

```java
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class IndependentGeneratorDemo {
    static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    static int deterministic(int index) {
        return (index * 31 + 7) ^ 0x5A5A;
    }

    public static void main(String[] args) {
        int[] source = {2, 4, 6, 8, 10};
        int[] sourceSnapshot =
            Arrays.copyOf(source, source.length);
        int[] result = new int[source.length];

        Arrays.parallelSetAll(result,
            index -> sourceSnapshot[index] * 3 + index);

        require(Arrays.equals(
            result, new int[]{6, 13, 20, 27, 34}),
            "expected transform");
        require(Arrays.equals(source, sourceSnapshot),
            "source must not be modified");

        int[] parallel = new int[10_000];
        int[] sequential = new int[10_000];
        AtomicInteger calls = new AtomicInteger();

        Arrays.parallelSetAll(parallel, index -> {
            calls.incrementAndGet(); // test instrumentation only
            return deterministic(index);
        });

        Arrays.setAll(sequential,
            index -> deterministic(index));

        require(Arrays.equals(parallel, sequential),
            "parallel must equal sequential for pure generator");
        require(calls.get() == 10_000,
            "one callback per index");

        System.out.println(
            "source=" + Arrays.toString(source));
        System.out.println(
            "result=" + Arrays.toString(result));
        System.out.println(
            "largeEqual=" + Arrays.equals(parallel, sequential));
        System.out.println(
            "generatorCalls=" + calls.get());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 IndependentGeneratorDemo.java
java IndependentGeneratorDemo
```

Stdout đã xác minh:

```text
source=[2, 4, 6, 8, 10]
result=[6, 13, 20, 27, 34]
largeEqual=true
generatorCalls=10000
PASS
```

Các assertion có ý nghĩa:

1. **Đúng giá trị từng index.** `sourceSnapshot[index] * 3 + index` tạo `[6, 13, 20, 27, 34]`, có kết quả xác định.
2. **Nguồn không bị thay đổi.** `source` vẫn bằng snapshot, nên việc tạo kết quả mới không phá dữ liệu đầu vào.
3. **Song song tương đương tuần tự.** Hai mảng 10.000 phần tử, một mảng dùng `Arrays.parallelSetAll` và một dùng `Arrays.setAll`, có kết quả bằng nhau với cùng phép tính theo index.
4. **Số lần gọi có thể xác minh được trong ca thành công.** Bộ đếm dùng AtomicInteger vì các callback có thể chạy đồng thời; không sử dụng một `int calls++` đơn thuần trong callback song song, vì cập nhật không atomic.
5. **Không kiểm tra thứ tự callback.** Kết quả của array được xác định theo index, không theo index nào được xử lý trước.

Test này tăng độ tin cậy về **tính đúng đắn**, chứ không chứng minh parallel nhanh hơn. Muốn đo hiệu năng cần thí nghiệm riêng với workload và cỡ mảng đại diện.

## 9. Khi generator ném exception, mảng không có tính giao dịch

Một quy tắc trực tiếp từ tài liệu Java SE 8 `Arrays.parallelSetAll`: nếu generator ném exception, phương thức ném ra một **unchecked exception** và mảng được để lại ở **trạng thái không xác định theo hợp đồng**.

Điều đó có nghĩa:

- Không có rollback tự động về toàn bộ giá trị trước khi gọi.
- Không có cam kết toàn bộ mảng đã được cập nhật hay chưa.
- Không nên khẳng định "chỉ các phần tử trước index lỗi được cập nhật": callback không chạy theo thứ tự index cố định.
- Không có bảo đảm rằng mọi callback khác dừng ngay ở một thời điểm xác định khi một callback thất bại.
- Không sử dụng mảng đang có thể bị cập nhật một phần như một kết quả thành công.
- Nếu callback đã ghi dữ liệu ngoài Map/file/database, những side effect đó cũng không tự rollback.

Bởi vậy, quy tắc an toàn khi generator có thể thất bại là **không xuất bản mảng mới cho người dùng trước khi phép tính hoàn tất thành công**. Nếu cần giữ nguyên mảng cũ, tạo mảng đích khác, chạy parallelSetAll trên mảng mới, rồi chỉ thay tham chiếu sau khi không còn exception.

### Không viết test dựa trên "chắc đã cập nhật x phần tử"

Giả sử bạn cố ý ném exception ở index 3. Mã test có thể **xác minh rằng có exception**, nhưng không được dựa vào nội dung cụ thể của mảng sau lỗi để suy ra tiến độ chung. Đừng in mảng sau exception và coi stdout là contract giữa các JVM.

## 10. Ví dụ hoàn chỉnh: exception và generator null

Tệp **`ParallelSetAllFailureDemo.java`** minh họa cách kiểm thử exception **mà không suy đoán trạng thái mảng khi thất bại**.

```java
import java.util.*;
import java.util.function.IntUnaryOperator;

public class ParallelSetAllFailureDemo {
    public static void main(String[] args) {
        int[] values = new int[8];
        Arrays.fill(values, -1);

        boolean errorCaught = false;

        try {
            Arrays.parallelSetAll(values, index -> {
                if (index == 3) {
                    throw new IllegalStateException("index 3 failed");
                }
                return index + 100;
            });
        } catch (RuntimeException ex) {
            errorCaught = true;
        }

        if (!errorCaught) {
            throw new AssertionError("generator must fail");
        }

        // Không kiểm tra các phần tử values sau lỗi:
        // Nội dung mảng không có bảo đảm theo hợp đồng.

        boolean nullGeneratorCaught = false;
        try {
            Arrays.parallelSetAll(
                new int[2], (IntUnaryOperator) null);
        } catch (NullPointerException ex) {
            nullGeneratorCaught = true;
        }

        if (!nullGeneratorCaught) {
            throw new AssertionError("null generator");
        }

        System.out.println("errorCaught=" + errorCaught);
        System.out.println("contentsNotAssumed=true");
        System.out.println(
            "nullGeneratorCaught=" + nullGeneratorCaught);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 ParallelSetAllFailureDemo.java
java ParallelSetAllFailureDemo
```

Stdout đã xác minh:

```text
errorCaught=true
contentsNotAssumed=true
nullGeneratorCaught=true
PASS
```

**Phân tích:**

- Với generator ném `IllegalStateException` ở index 3, test chỉ kiểm **phương thức không hoàn tất bình thường**. Việc catch `RuntimeException` phù hợp với điều kiện API có thể truyền một unchecked exception; không áp đặt giả định không cần thiết rằng wrapper/thông điệp exception phải giống nhau ở mọi cách thực thi.
- Test **không** kiểm `values[0]`, `values[3]` hay những index khác sau lỗi, vì hợp đồng không cho phép tin rằng mảng có một trạng thái hoàn chỉnh nhất định.
- Truyền generator null được kiểm bằng cách ép kiểu rõ sang `IntUnaryOperator`, tránh hiểu nhầm overload. Java SE 8 quy định generator null dẫn tới `NullPointerException`.
- Hai ca exception độc lập nhau; chúng không có tác động giao dịch nào lên hệ thống bên ngoài.

Nếu ứng dụng cần bảo đảm **"thất bại thì mảng cũ giữ nguyên"**, giải pháp là giữ mảng cũ riêng, không sửa trực tiếp nó trong lời gọi có thể thất bại:

```java
// Mã minh họa: oldData là int[] do ứng dụng đang dùng.
int[] candidate = new int[oldData.length];
Arrays.parallelSetAll(candidate, i -> safeCompute(i));
// Chỉ publish candidate nếu phương thức hoàn tất thành công.
// oldData được giữ nguyên.
```

Phương thức `safeCompute` vẫn phải tuân thủ điều kiện về shared state và side effect. Nếu nó ghi database rồi exception, thay mảng đích cũng **không thể rollback database**.

## 11. Side effect kiểu logging, I/O và gọi dịch vụ

Giả sử mỗi generator cần gọi một HTTP API, ghi một hàng database hoặc in một dòng log:

```java
// PHẢN VÍ DỤ: hành động bên ngoài phụ thuộc lịch chạy.
// Chỉ minh họa rủi ro, không phải chương trình độc lập.
Arrays.parallelSetAll(data, i -> {
    remoteService.update(i);    // side effect bên ngoài
    return calculate(i);
});
```

Các vấn đề có thể xảy ra:

- Lời gọi bên ngoài diễn ra **đồng thời và không theo thứ tự index**.
- Service có thể bị giới hạn tốc độ, connection pool cạn, timeout hoặc rate-limit.
- Nếu một callback thất bại, những side effect khác có thể đã hoàn thành; API không bảo đảm rollback.
- Ghi log có thể xuất hiện ngoài thứ tự, khiến người đọc tưởng thứ tự xử lý dữ liệu bị hỏng.
- Việc khóa tuần tự trong generator để "ép đúng thứ tự" thường phá hủy lợi ích parallel và có thể gây deadlock nếu có nhiều khóa.

Nếu công việc là **I/O hoặc nghiệp vụ có side effect**, dùng một phương án được thiết kế riêng: giới hạn concurrency, quản lý timeout/retry, idempotency, thứ tự và bù trừ. `parallelSetAll` thích hợp nhất cho **phép tính mỗi index độc lập**, không phải bộ điều phối hàng nghìn hoạt động bên ngoài.

### Có được ghi log trong lúc debug không?

Có thể in log **để quan sát**, nhưng không được viết test mong thấy các dòng log theo thứ tự `0,1,2,...`. Nên đính kèm index trong thông điệp để truy dấu. Nếu log ảnh hưởng lớn đến chi phí, tách nó khỏi phần benchmark vì overhead I/O có thể lấn át lợi ích parallel.

### Có được dùng AtomicInteger trong generator không?

Có thể dùng một bộ đếm atomic cho **instrumentation** giống ví dụ mục 8, nhưng không lấy giá trị trả về của counter làm kết quả đòi hỏi thứ tự vị trí. Atomicity không cấp guarantee về lịch chạy. Ngoài ra, contention trên một counter chung cũng có thể khiến throughput kém đi.

## 12. Chọn kiểu số và xử lý tràn

Dù chỉ số luôn là `int`, kiểu kết quả tùy overload. Hãy lưu ý:

```java
// Với int[]: phép nhân được tính trong miền int, có thể tràn.
Arrays.parallelSetAll(intValues, i -> i * i);

// Với long[]: ép/chọn kiểu long trước khi nhân.
Arrays.parallelSetAll(longValues, i -> (long) i * i);
```

Nếu `i` đủ lớn, `i*i` trên `int` có thể tràn trước khi gán; việc chỉ dùng `long[]` làm đích nhưng vẫn viết biểu thức `i * i` có thể khiến phép toán tràn ở int trước khi chuyển sang long. Chọn kiểu hoặc dùng `Math.multiplyExact` phù hợp, và xác định hành vi exception theo nghiệp vụ.

Với `double[]`, mỗi index có thể được tính độc lập nhưng kết quả vẫn tuân theo quy tắc dấu phẩy động IEEE 754, gồm làm tròn và các giá trị đặc biệt như NaN/Infinity. Nếu cần tính chính xác tiền tệ, mảng `double[]` không tự bảo đảm độ chính xác nghiệp vụ; cân nhắc `BigDecimal` trong một mảng object hoặc biểu diễn đơn vị nhỏ nhất bằng số nguyên phù hợp.

Một ví dụ có generator trả null cho `String[]` là hợp lệ về kiểu, nhưng cần kiểm tra downstream có chấp nhận null hay không. Với các mảng object, việc tạo object mới cho từng index có thể phát sinh nhiều allocation và áp lực garbage collector.

## 13. Khi nào parallelSetAll có thể nhanh hơn setAll?

**Không có bảo đảm `parallelSetAll` luôn nhanh hơn.** Song song có chi phí chia việc, lập lịch và phối hợp. Lợi ích phụ thuộc vào lượng công việc **trong mỗi index**.

Các câu hỏi thực dụng:

1. **Mảng có đủ lớn không?** Với vài phần tử hoặc generator chỉ trả `i`, vòng `for` hoặc `Arrays.setAll` thường dễ hiểu hơn và có thể nhanh hơn.
2. **Phép tính mỗi index có đủ tốn CPU không?** Ví dụ một phép mô phỏng toán học thuần, độc lập theo index có thể khai thác nhiều lõi tốt hơn phép `i * 2` rất rẻ.
3. **Có phụ thuộc giữa các index không?** Nếu index i cần kết quả đã ghi ở i-1, bạn đang gặp một bài toán có phụ thuộc và không thể tự động song song bằng generator độc lập.
4. **Có ghi/chia sẻ trạng thái ở bên ngoài không?** Lock, counter tranh chấp và I/O có thể xóa hết lợi ích parallel.
5. **Có dùng nhiều bộ nhớ không?** Object allocations, cache locality, memory bandwidth và garbage collection có thể trở thành nút thắt.
6. **Ứng dụng đã có nhiều công việc concurrent khác chưa?** Thêm phép parallel có thể cạnh tranh CPU hoặc bộ nhớ với các tác vụ khác.
7. **Có thể đo đầu ra đúng và thời gian ổn định không?** Benchmark phải xác minh kết quả trước rồi mới so thời gian.

Không khẳng định số thread, ngưỡng kích thước hay chiến lược chia index là cố định giữa các JDK. Nếu cần mô hình tính toán với executor riêng, chính sách thread pool riêng hoặc giới hạn số tác vụ chính xác, hãy thiết kế với các công cụ concurrency phù hợp thay vì giả định `parallelSetAll` cung cấp toàn bộ cấu hình đó.

## 14. Thiết kế benchmark có ý nghĩa

Một microbenchmark có ích nên:

- Chạy cả `Arrays.setAll` và `Arrays.parallelSetAll` với **cùng generator** xác định và cùng dữ liệu.
- Có nhiều kích thước, từ nhỏ đến lớn; phép đo trên 8 phần tử không đại diện cho 10 triệu phần tử.
- Có nhiều độ nặng CPU của generator: cực nhẹ, trung bình, tốn CPU nhưng không có I/O.
- Tạo/chuẩn bị mảng mục tiêu tương đương cho hai phương án; quyết định có tính chi phí cấp phát mảng vào phép đo hay không.
- Kiểm tra kết quả bằng `Arrays.equals` hoặc oracle theo index. Một phép chạy nhanh nhưng cho mảng sai không phải tối ưu.
- Warm up JVM, chạy nhiều lượt/fork, quan sát GC và contention. Với microbenchmark Java nghiêm túc, có thể dùng **JMH** thay vì một lần `System.nanoTime()`.
- Không ghi `System.out.println` ở mỗi callback khi đo; I/O làm thay đổi workload và lịch chạy.
- Xem xét tác động lên latency/throughput của ứng dụng toàn cục, không chỉ một phép cập nhật mảng.

Kết quả benchmark **phụ thuộc môi trường**: JDK, phần cứng, số lõi, dữ liệu, bộ nhớ, các ứng dụng cùng chạy. Bài này không tuyên bố `parallelSetAll` nhanh hơn một con số cố định.

## 15. Phân biệt parallelSetAll với parallelSort và parallelPrefix

Các phương thức của `Arrays` có chữ `parallel` không phục vụ cùng mục đích:

| API | Tác dụng | Hàm đầu vào |
| --- | --- | --- |
| `Arrays.parallelSetAll(array, generator)` | **Gán từng vị trí theo chỉ số**, có thể song song | Hàm `index → value` |
| `Arrays.setAll(array, generator)` | Cũng gán từng vị trí theo chỉ số nhưng **tuần tự** | Hàm `index → value` |
| `Arrays.parallelSort(array)` | **Sắp xếp** các phần tử đã có trong mảng | Comparator hoặc thứ tự tự nhiên tùy overload |
| `Arrays.parallelPrefix(array, op)` | Tính **prefix tích lũy** theo một phép toán kết hợp | Hàm hai đối số cho việc kết hợp các giá trị |
| `IntStream.range(0,n).parallel()` | Tạo một luồng index, có thể phối hợp nhiều thao tác khác | Lambda theo Stream operation |

**Không dùng `parallelSetAll` để làm phép prefix có phụ thuộc giữa các index.** Nếu bài toán cần tổng tích lũy theo tiền tố, `Arrays.parallelPrefix` có semantics và yêu cầu phép toán riêng; không thay bằng lambda đọc `array[i-1]` đang bị update.

**Không dùng `parallelSetAll` để sắp xếp.** Giá trị generator chỉ theo index, không có tác dụng tự thu thập và so sánh dữ liệu toàn mảng. Dùng `Arrays.sort` hoặc `Arrays.parallelSort` khi mục tiêu thật là sort.

Nếu chỉ cần thiết lập một **đoạn con** của mảng, phương thức `parallelSetAll` không có overload nhận `fromIndex/toIndex`. Một cách minh họa tương đương theo chỉ số là:

```java
// Mã minh họa; start/end được kiểm tra hợp lệ.
IntStream.range(start, end)
    .parallel()
    .forEach(i -> array[i] = generator.applyAsInt(i));
```

Điều này **không cấp quyền** để thêm side effect tùy ý: mỗi index vẫn cần được ghi độc lập, dữ liệu đọc ổn định và exception vẫn cần được xử lý. Với các nguồn hoặc ranh giới đặc thù, có thể chọn cách chia công việc khác.

## 16. Kiểm thử cho mảng khởi tạo song song

Một bộ test tốt không chỉ xem `array.length`. Nó phải đối chiếu giá trị tại từng index, nguồn bất biến và hành vi lỗi.

| Tình huống | Input | Expected |
| --- | --- | --- |
| Mảng rỗng | `new int[0]` | Không có callback, kết quả độ dài 0 |
| Một phần tử | `new int[1]` | index 0 được sinh đúng |
| Mảng nhỏ | `new int[8]` | Mỗi `a[i] = f(i)` |
| Mảng lớn | `new int[10000]` | Bằng kết quả tuần tự/oracle |
| Chỉ số biên | 0 và `length-1` | Không off-by-one |
| Kiểu primitive int | `int[]` | Biểu thức trả int hợp lệ, không tràn ngoài ý muốn |
| Kiểu long | `long[]` | Phép nhân long đúng |
| Kiểu double | `double[]` | Quy tắc số thực và tolerance thích hợp |
| Kiểu object | `String[]` | Giá trị/nullable policy đúng |
| Generator độc lập | Chỉ phụ thuộc index và snapshot | Bằng nhau qua nhiều lần chạy |
| Nguồn snapshot | Source và target riêng | Source không đổi |
| Generator ném lỗi | Một index gây exception | Có unchecked exception; **không assert nội dung mảng** |
| Generator null | Null callback | `NullPointerException` |
| Mutable shared state | Code anti-pattern | Tránh thiết kế; nếu có, test race/contract riêng |
| Số lượng callback thành công | Test-only AtomicInteger | Một lần cho mỗi index được xử lý trong ca hoàn tất |
| Nhiều luồng ghi cùng target từ bên ngoài | Trạng thái chia sẻ ngoài API | Không dùng nếu không có phối hợp riêng |

### Oracle độc lập với thứ tự lịch chạy

Đối với hàm xác định `f(i)`, hãy tạo mảng expected bằng cách chạy tuần tự hoặc tính công thức riêng:

```java
// Mã minh họa, không phải tệp độc lập.
int[] expected = new int[10000];
int[] actual = new int[10000];

Arrays.setAll(expected, i -> pureFormula(i));
Arrays.parallelSetAll(actual, i -> pureFormula(i));

if (!Arrays.equals(expected, actual)) {
    throw new AssertionError("parallel result differs");
}
```

Nếu cả oracle và code đang thử dùng **cùng một hàm sai** (ví dụ tràn số), hai mảng vẫn có thể bằng nhau. Vì thế nên thêm một số **golden cases tính tay** ở input nhỏ cùng test biên. Trong ví dụ mục 8, array `[6,13,20,27,34]` là expected độc lập được viết rõ.

### Đừng kiểm tra thứ tự callback

Một test như "callback ở index i phải được gọi sau callback ở index i-1" là kiểm tra sai hợp đồng. Dùng `AtomicInteger` để đếm số lần callback có thể là công cụ chẩn đoán, nhưng không được so sequence giá trị counter với index rồi kết luận JDK lỗi.

### Đừng dùng mảng có lỗi như kết quả thành công

Nếu generator ném exception, trạng thái mảng không xác định. Test nên kiểm exception và xử lý lỗi, còn mảng bị ảnh hưởng phải được **loại bỏ, reset hoặc thay thế**, không so các phần tử với một prefix dự kiến.

## 17. Những lỗi phổ biến và cách xử lý

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ lambda nhận giá trị hiện tại | Công thức sai vì nó thực nhận index | Gọi tham số là `index`, test kết quả tay |
| Nghĩ parallelSetAll trả mảng mới | Code không biên dịch vì phương thức trả void | Cấp phát mảng, gọi để cập nhật in-place |
| Đọc phần tử lân cận đang thay đổi | Phụ thuộc lịch thực thi, data race | Đọc snapshot bất biến, ghi target riêng |
| Viết sang `array[i+1]` từ generator của i | Hai callback tranh nhau cùng index | Chỉ trả giá trị cho index đang xử lý |
| Gọi `sharedList.add(i)` trong generator | Collection mutable không thread-safe | Thu dữ liệu riêng sau phép tính hoặc dùng cấu trúc an toàn theo hợp đồng |
| Dùng AtomicInteger để sinh số thứ tự theo index | Atomic nhưng thứ tự gán bất định | Trả `i+1` hoặc một hàm thuần của i |
| Ghi log rồi assert log có thứ tự tăng dần | Callback không có encounter order được bảo đảm | Gắn index vào log, không test thứ tự |
| Gọi HTTP/database từ mọi callback | Rate-limit, blocking, side effect không rollback | Dùng pipeline I/O/concurrency được thiết kế riêng |
| Generator ném lỗi nhưng vẫn dùng mảng đích | Mảng có trạng thái không xác định | Chỉ publish kết quả khi hoàn tất, bỏ/reset mảng lỗi |
| Dùng `int` để nhân các giá trị lớn rồi gán sang long | Tràn int trước khi gán | Ép/toán hạng long ngay từ đầu |
| Dùng `parallelSetAll` cho mảng vài phần tử | Overhead có thể lớn hơn việc tính | Ưu tiên `setAll` hoặc vòng `for`, benchmark |
| Tưởng parallelSetAll giúp sắp xếp | Sai mục đích | Dùng `sort/parallelSort` |
| Tưởng parallelSetAll dùng để làm prefix sum | Sai ràng buộc phụ thuộc | Dùng `parallelPrefix` với toán tử đúng |
| Trả null trong Object[] mà downstream không chấp nhận | NPE sau đó | Xác định hợp đồng nullable, kiểm thử |
| Test chỉ kiểm không ném exception | Giá trị có thể sai nhưng test vẫn qua | So với oracle/golden từng index |
| Tin vào số thread hoặc thứ tự hiện tại của một JDK | Code phụ thuộc implementation | Không dựa vào lịch chạy; đo hiệu năng riêng |

## 18. Bài tập thực hành

### Bài 1 — Dựng một bảng bình phương

**Đề bài:** dùng `parallelSetAll` tạo mảng 10 phần tử với `a[i] = i*i`. Kiểm tra mảng expected.

**Đáp án định hướng:**

```java
int[] a = new int[10];
Arrays.parallelSetAll(a, i -> i * i);
// Expected: [0,1,4,9,16,25,36,49,64,81].
```

Sự đúng đắn dựa trên việc mỗi index độc lập. Không cần counter hoặc collection ngoài.

### Bài 2 — Nâng số lượng dữ liệu mà không tràn int

**Đề bài:** muốn lưu bình phương index tới giá trị lớn, kết quả có thể vượt miền int. Chọn mảng và biểu thức nào?

**Đáp án:**

```java
long[] squares = new long[n];
Arrays.parallelSetAll(squares, i -> (long) i * i);
```

Không chỉ tạo `long[]` nhưng vẫn viết `i*i` mà không ép kiểu trước phép nhân.

### Bài 3 — Biến đổi dựa trên dữ liệu cũ

**Đề bài:** với `[1,2,3,4]`, muốn tạo `b[0]=a[0]` và `b[i]=a[i-1]+a[i]` ở các index tiếp theo. Có được dùng `parallelSetAll(a, i -> a[i-1]+a[i])` không?

**Đáp án:** không, vì callback đọc những phần tử trong mảng đang bị cập nhật. Tạo mảng kết quả riêng:

```java
int[] source = {1, 2, 3, 4};
int[] result = new int[source.length];
Arrays.parallelSetAll(result, i ->
    i == 0 ? source[0] : source[i - 1] + source[i]);
// Expected: [1, 3, 5, 7].
```

Giữ `source` không thay đổi trong suốt phép tính.

### Bài 4 — Vì sao AtomicInteger chưa đủ?

**Đề bài:** `AtomicInteger counter` được dùng để trả số chạy cho index. Mọi increment là atomic. Có được khẳng định phần tử i sẽ bằng i+1?

**Đáp án:** không. Các callback có thể chạy không theo thứ tự index. Atomic chỉ ngăn mất cập nhật trên counter, không quyết định index nào nhận số nào. Muốn giá trị theo index, dùng `i+1`.

### Bài 5 — Cần rollback khi thất bại

**Đề bài:** cập nhật mảng đang được người dùng tham chiếu, nhưng generator có thể ném exception. Làm sao tránh để người dùng thấy mảng bị ghi dở?

**Đáp án định hướng:** dựng mảng `candidate` riêng, chạy `parallelSetAll(candidate, generator)`, kiểm tra thành công rồi mới công bố tham chiếu candidate. Cần bảo đảm quy tắc xuất bản và sở hữu dữ liệu đúng theo ngữ cảnh đa luồng, và không coi side effect ngoài mảng là đã rollback.

### Bài 6 — Đánh giá lợi ích parallel

**Đề bài:** mảng có 100 phần tử, mỗi generator chỉ làm `i+1`. Có nên mặc định dùng `parallelSetAll` vì "parallel"?

**Đáp án:** không. Chi phí chia và phối hợp có thể vượt phần tính toán rất nhỏ. Ưu tiên code dễ hiểu, so sánh với `Arrays.setAll` và chỉ dùng parallel khi benchmark đại diện cho thấy lợi ích.

## 19. Câu hỏi tự kiểm tra

**1. Generator của `Arrays.parallelSetAll` nhận index hay giá trị hiện tại?**  
Nhận **index kiểu int**. Nó phải trả giá trị để gán vào đúng vị trí tương ứng.

**2. `Arrays.parallelSetAll` có trả về mảng mới không?**  
Không. Nó trả `void` và ghi trực tiếp lên mảng được truyền vào.

**3. Kết quả của generator thuần có phụ thuộc thứ tự callback không?**  
Không, nếu mỗi kết quả chỉ phụ thuộc index và dữ liệu đọc ổn định. Giá trị cuối vẫn đúng theo index dù callback được thực hiện theo thứ tự khác.

**4. Có được cập nhật một `ArrayList` chia sẻ trong generator không?**  
Không an toàn nếu các callback cùng ghi không đồng bộ. Cần tách trách nhiệm thu thập dữ liệu hoặc dùng cấu trúc/chiến lược đồng bộ phù hợp, không phụ thuộc thứ tự chạy.

**5. Dùng AtomicInteger trong generator có làm thứ tự kết quả đúng theo index không?**  
Không. Atomicity của counter không quyết định callback nào được chạy trước.

**6. Khi generator ném exception, nội dung mảng có bảo đảm chỉ cập nhật một prefix không?**  
Không. Mảng ở trạng thái **không xác định theo hợp đồng**; không được suy ra prefix hoặc rollback.

**7. Làm sao tính dựa trên giá trị cũ của các phần tử lân cận?**  
Tách nguồn không đổi (snapshot hoặc mảng nguồn read-only) khỏi mảng đích; generator đọc nguồn và trả giá trị cho index được giao.

**8. `parallelSetAll` hỗ trợ trực tiếp những loại mảng nào trong Java 8?**  
`T[]`, `int[]`, `long[]` và `double[]`.

**9. Khi nào cần cân nhắc `Arrays.parallelPrefix` thay vì parallelSetAll?**  
Khi bài toán thực sự là tính prefix tích lũy theo phép toán kết hợp, có phụ thuộc trên dãy các phần tử.

**10. Có nên khẳng định parallelSetAll luôn nhanh hơn setAll?**  
Không. Cần đo với cỡ mảng và chi phí mỗi index đại diện, đồng thời kiểm tra kết quả chính xác.

## Tài liệu Java chính thức

- [Java SE 8 — Arrays](https://docs.oracle.com/javase/8/docs/api/java/util/Arrays.html): `parallelSetAll`/`setAll`, bốn overload và hợp đồng exception khi generator thất bại.
- [Java SE 8 — IntUnaryOperator](https://docs.oracle.com/javase/8/docs/api/java/util/function/IntUnaryOperator.html): hàm `int → int` dùng cho `int[]`.
- [Java SE 8 — IntToLongFunction](https://docs.oracle.com/javase/8/docs/api/java/util/function/IntToLongFunction.html): hàm `int → long` dùng cho `long[]`.
- [Java SE 8 — IntToDoubleFunction](https://docs.oracle.com/javase/8/docs/api/java/util/function/IntToDoubleFunction.html): hàm `int → double` dùng cho `double[]`.
- [Java SE 8 — IntFunction](https://docs.oracle.com/javase/8/docs/api/java/util/function/IntFunction.html): hàm `int → T` dùng cho mảng object.
- [Java SE 8 — java.util.stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): nguyên tắc non-interference, stateless behavior và bất định thứ tự side effect trong xử lý song song.
- [Java SE 26 — Arrays (xác nhận API vẫn tồn tại)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): các overload `parallelSetAll` vẫn được hỗ trợ trên Java hiện đại.

**Ghi nhớ:** `Arrays.parallelSetAll` hiệu quả nhất khi mỗi giá trị là **một hàm độc lập của index và dữ liệu bất biến**, còn việc ghi phần tử do API đảm nhiệm. Không dựa vào thứ tự callback, không mutate collection dùng chung, không đọc những giá trị đang bị ghi trong cùng mảng, và không giả định thao tác atomic khi generator thất bại. Hãy giữ nguồn ổn định, tạo mảng đích riêng nếu cần bảo toàn dữ liệu cũ, kiểm thử kết quả theo từng index và chỉ chọn xử lý song song khi đo lường thực tế cho thấy lợi ích.