# Mảng trong Java: Đối chiếu kết quả tuần tự, song song và tràn số

**Chủ đề cha:** Mảng (Arrays). **Trọng tâm:** Khi xử lý `int[]`, `long[]`, `double[]` hoặc mảng đối tượng, chương trình có thể dùng thuật toán **tuần tự** hay **song song**. Muốn kiểm tra tính đúng đắn, cần tách ba câu hỏi: (1) hai cách chạy có bảo đảm tạo **cùng kết quả theo hợp đồng** không; (2) kết quả đó có **đúng ý nghĩa toán học/nghiệp vụ** không; (3) có sự cố **tràn số, sai số thực hoặc side effect dùng chung** không.

Các API `Arrays.sort`, `Arrays.parallelSort`, `Arrays.setAll`, `Arrays.parallelSetAll` và `Arrays.parallelPrefix` vẫn là API được hỗ trợ trên JDK hiện đại. `Arrays.stream(array).parallel()` cho phép áp dụng Stream song song lên mảng. Các chương trình độc lập trong bài biên dịch với **Java 17+**, dùng cú pháp có kiểm tra kết quả và không phụ thuộc thứ tự thread chạy.

> **Ghi nhớ ngay:** “Tuần tự và song song trả ra cùng số” **không chứng minh số đó không bị tràn**. Ví dụ tổng `int` có thể tràn giống nhau ở cả hai chế độ. Ngược lại, với `double`, hai cách gộp các số hữu hạn theo thứ tự khác nhau có thể tạo kết quả khác nhau **mà không có data race**.

## 1. Hiểu đúng “tuần tự” và “song song” trên mảng

**Tuần tự** (sequential) thường là một vòng lặp xử lý phần tử theo thứ tự xác định, hoặc một API như `Arrays.sort(array)`, `Arrays.setAll(array, ...)`, `Arrays.stream(array).sum()` (stream mặc định tuần tự). **Song song** (parallel) cho phép chia dữ liệu thành các phần và thực thi công việc trên nhiều tác vụ, ví dụ `Arrays.parallelSort`, `Arrays.parallelSetAll`, `Arrays.parallelPrefix` và `Arrays.stream(array).parallel()`.

Không nhầm các dạng xử lý sau:

| Nhu cầu | Cách tuần tự | Cách song song / lưu ý |
| --- | --- | --- |
| Sắp xếp mảng | `Arrays.sort(copy)` | `Arrays.parallelSort(copy)` |
| Tạo giá trị theo **chỉ số** | `Arrays.setAll(array, i -> ...)` | `Arrays.parallelSetAll(array, i -> ...)` |
| Tính tiền tố tích lũy (*prefix scan*) | Vòng lặp cộng dồn từ trái sang phải | `Arrays.parallelPrefix(array, op)` |
| Tính tổng từ `int[]` | `Arrays.stream(a).sum()` | `Arrays.stream(a).parallel().sum()` |
| Biến đổi thành mảng mới | `Arrays.stream(a).map(...).toArray()` | `Arrays.stream(a).parallel().map(...).toArray()` |
| Thực hiện action cho từng phần tử | `forEach(...)` | `parallel().forEach(...)`, **thứ tự action không cam kết** |

Chữ **parallel** không có nghĩa kết quả ngẫu nhiên hoặc phải khác tuần tự. Với một phép tính không có trạng thái chia sẻ, có hợp đồng đủ chặt và dữ liệu phù hợp, kết quả thường phải tương đương; **thứ tự callback, thời gian chạy và số thread** thì không nên được dùng làm điều kiện đúng/sai.

`Arrays.parallelSort`/`parallelSetAll`/`parallelPrefix` có thể làm việc song song nhưng **không cam kết luôn nhanh hơn**. Kích thước mảng, số lõi, tác vụ đang chạy, bộ nhớ, chi phí chia/gộp và thuật toán đều ảnh hưởng. Đừng viết unit test dựa vào kỳ vọng “cứ gọi parallel là chạy trên nhiều thread” hoặc “phải nhanh hơn 2 lần”.

## 2. Cách đối chiếu công bằng: cùng dữ liệu đầu vào, hai bản sao riêng

Các thao tác `sort` và `parallelSort` **sửa trực tiếp mảng đầu vào**. `parallelPrefix` cũng sửa mảng trực tiếp. Nếu chạy thuật toán tuần tự trên chính mảng rồi mới chạy thuật toán song song trên **mảng đã bị biến đổi**, bạn không còn kiểm tra cùng một đầu vào.

**Mẫu đối chiếu đúng**:

```java
int[] input = {5, 1, 3, 1, -2, 5};
int[] sequential = input.clone();
int[] parallel = input.clone();

Arrays.sort(sequential);
Arrays.parallelSort(parallel);

boolean same = Arrays.equals(sequential, parallel);
```

Đây là **đoạn trong một phương thức** với import `java.util.Arrays`. `clone()` tạo **một mảng mới** chứa bản sao các phần tử. Với mảng nguyên thủy, các giá trị được sao chép độc lập; với mảng đối tượng, `clone()` chỉ tạo **bản sao nông** của mảng (cùng các tham chiếu phần tử), không sao chép sâu trạng thái các object.

Để so sánh hai mảng một chiều, dùng:

- `Arrays.equals(int[], int[])`, `Arrays.equals(long[], long[])` và các overload nguyên thủy phù hợp.
- `Arrays.equals(T[], T[])` khi muốn so sánh phần tử theo `Objects.equals`.
- `Arrays.deepEquals(Object[], Object[])` khi cần so sánh cấu trúc lồng nhau gồm các array phù hợp.
- `Arrays.mismatch(a, b)` (Java 9+) để xác định chỉ số đầu tiên khác nhau; trả `-1` nếu không khác.

**Không dùng `a == b` để so nội dung mảng**: `==` chỉ so **tham chiếu mảng**. `Arrays.toString(a)` giúp in log/debug, nhưng cách kiểm thử nên dựa vào assertion/`Arrays.equals` và quy tắc dữ liệu cụ thể.

## 3. `Arrays.sort` so với `Arrays.parallelSort`: Kết quả và thứ tự

Với `int[]` và comparator/ngữ nghĩa tự nhiên hợp lệ, cả hai phải sắp xếp thành thứ tự được đặc tả. Không có lợi ích gì khi cho rằng parallel sort được quyền trả một mảng chưa sắp xếp chỉ vì lịch thread khác nhau.

### 3.1. Ví dụ chạy được: mảng nguyên thủy và object có khóa trùng

Tạo file **`ArraySortComparisonDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;

public class ArraySortComparisonDemo {
    public static void main(String[] args) {
        int[] original = {5, 1, 3, 1, -2, 5};

        int[] sequential = original.clone();
        int[] parallel = original.clone();

        Arrays.sort(sequential);
        Arrays.parallelSort(parallel);

        System.out.println("sort sequential: "
                + Arrays.toString(sequential));
        System.out.println("sort parallel:   "
                + Arrays.toString(parallel));
        System.out.println("same: "
                + Arrays.equals(sequential, parallel));

        String[] words = {"bb", "a", "cc", "d", "eee"};
        Arrays.parallelSort(
                words, Comparator.comparingInt(String::length));

        System.out.println("stable words: "
                + Arrays.toString(words));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ArraySortComparisonDemo.java
java ArraySortComparisonDemo
```

**Stdout chính xác:**

```text
sort sequential: [-2, 1, 1, 3, 5, 5]
sort parallel:   [-2, 1, 1, 3, 5, 5]
same: true
stable words: [a, d, bb, cc, eee]
```

Giải thích:

1. `Arrays.sort` và `Arrays.parallelSort` đều làm thay đổi bản sao của mảng, không làm thay đổi `original`.
2. `Arrays.equals` trả true vì hai mảng `int[]` có cùng kích thước và cùng giá trị tương ứng tại từng vị trí.
3. `Arrays.parallelSort(String[], comparator)` **bảo đảm stable** cho mảng đối tượng: `"bb"` và `"cc"` cùng độ dài 2 nên vẫn giữ thứ tự tương đối ban đầu; tương tự `"a"` và `"d"` có độ dài 1. `Arrays.sort(Object[], comparator)` cũng có bảo đảm stable.
4. Lời gọi comparator trong quá trình parallel sort có thể diễn ra trên nhiều tác vụ; comparator phải nhất quán, không phụ thuộc thứ tự được gọi và không sửa trạng thái dùng chung thiếu đồng bộ.

**Lưu ý quan trọng:** Tính stable dành cho **mảng object** khi comparator coi hai phần tử là bằng nhau. Mảng nguyên thủy không có thông tin riêng về “bản sắc phần tử” khi hai giá trị số bằng nhau; đừng suy luận từ output của `int[]` để kiểm chứng stable ordering của object.

### 3.2. Đối chiếu trên một đoạn mảng

Các overload `sort(a, fromIndex, toIndex)` và `parallelSort(a, fromIndex, toIndex)` sắp xếp phần `[fromIndex, toIndex)`: **cận trái được lấy, cận phải không được lấy**. Ngoài đoạn này, các giá trị phải giữ nguyên.

```java
int[] values = {9, 5, 3, 4, 1, 8};
Arrays.parallelSort(values, 1, 5);
System.out.println(Arrays.toString(values));
```

Đây là **đoạn mã trong phương thức** với import `java.util.Arrays`, in:

```text
[9, 1, 3, 4, 5, 8]
```

Vì chỉ các vị trí 1, 2, 3, 4 được sắp xếp; chỉ số 0 và 5 vẫn là 9 và 8. Đối chiếu cả **mảng kết quả** chứ không chỉ một đoạn con. Test biên cần bao gồm `fromIndex == toIndex` (đoạn rỗng), đoạn dài 1, `fromIndex == 0`, `toIndex == array.length` và trường hợp chỉ số không hợp lệ. Với `fromIndex > toIndex` hoặc vượt phạm vi, API ném exception theo hợp đồng.

### 3.3. Mảng `double[]` khi có giá trị đặc biệt

`Arrays.sort(double[])` và `Arrays.parallelSort(double[])` áp dụng thứ tự toàn phần tương thích với `Double.compare`: `-0.0` đứng trước `+0.0` và `NaN` được xem lớn hơn các giá trị số khác. Đừng kiểm thử bằng comparator tự viết chỉ dùng `<` và `>`, vì `NaN` sẽ phá tính nhất quán.

Thí dụ đầu vào gồm `NaN`, vô cùng và signed zero có kết quả:

```text
[-Infinity, -0.0, 0.0, Infinity, NaN]
```

Hãy xem chương trình `ArrayFloatingComparisonDemo` bên dưới để kiểm chứng độc lập.

## 4. `setAll` với `parallelSetAll`: Bản chất là sinh theo chỉ số

`Arrays.setAll(array, generator)` và `Arrays.parallelSetAll(array, generator)` gán giá trị ở từng chỉ số `i` theo một generator:

```java
int[] values = new int[6];
Arrays.parallelSetAll(values, i -> i * i - 2 * i);
```

Đây là **đoạn trong phương thức** cần import `java.util.Arrays`, kết quả là `[0, -1, 0, 3, 8, 15]`. Mỗi đầu ra chỉ phụ thuộc **chỉ số i**, nên không cần đọc giá trị do một thread khác vừa ghi.

**Điều kiện để đối chiếu có ý nghĩa:** generator phải **độc lập giữa các index**, không dùng một counter mutable chung, không đọc/ghi cùng mảng đang cập nhật theo cách phụ thuộc vào các index khác, và không dựa vào thời gian thực/thứ tự callback.

**Sai về mặt thiết kế song song**:

```java
// Phản ví dụ, không chạy để dự đoán stdout:
int[] result = new int[1000];
int[] counter = {0};
Arrays.parallelSetAll(result, i -> counter[0]++);
```

Đây là **đoạn mã không an toàn** vì các lần tăng `counter[0]++` tranh chấp nhau. Chạy tuần tự có thể cho dãy 0,1,2,..., còn song song có thể mất cập nhật và không bảo đảm kết quả theo index.

Nếu mục tiêu là điền số `0,1,2,...`, chỉ cần:

```java
Arrays.parallelSetAll(result, i -> i);
```

Đây là **đoạn trong phương thức**, sử dụng cùng `result` đã tạo; phép tạo giá trị là hàm của index, không có trạng thái chia sẻ.

### 4.1. Nếu generator ném exception?

Theo tài liệu `Arrays.setAll`/`parallelSetAll`, nếu generator ném exception, thao tác thất bại và mảng có thể ở **trạng thái chỉ được ghi một phần, không thể giả định giá trị từng vị trí**. Cụ thể với `parallelSetAll`, một unchecked exception được ném ra và mảng ở trạng thái không xác định theo hợp đồng API.

**Không** dựa vào việc “hoặc tất cả index được gán, hoặc không index nào được gán”. Nếu muốn atomic publish, sinh kết quả vào một **mảng tạm riêng**, chỉ đưa mảng đó ra hệ thống sau khi toàn bộ việc tính toán thành công và validate xong. Với object mutable, cần tính tới bản sao nông của mảng và quyền sở hữu tham chiếu.

## 5. Ví dụ đầy đủ: điền mảng và tính prefix tuần tự/song song

Prefix sum (tổng tiền tố) là dãy trong đó phần tử `i` chứa tổng của mọi phần tử từ đầu đến `i`. Với `[2, 1, 0, 3]`, prefix cộng là `[2, 3, 3, 6]`.

Mẫu tuần tự:

```java
for (int i = 1; i < values.length; i++) {
    values[i] += values[i - 1];
}
```

Đây là **đoạn mã bên trong phương thức** với `values` là một mảng có thể sửa. Cách song song là `Arrays.parallelPrefix(values, Integer::sum)`; phép cộng các số nguyên theo ngữ nghĩa Java thỏa tính kết hợp modulo độ rộng bit, nhưng **vẫn có thể bị tràn đối với tổng toán học**.

Tạo file **`ArrayFillAndPrefixDemo.java`**:

```java
import java.util.Arrays;

public class ArrayFillAndPrefixDemo {
    public static void main(String[] args) {
        int[] sequentialFill = new int[6];
        int[] parallelFill = new int[6];

        Arrays.setAll(sequentialFill, i -> i * i - 2 * i);
        Arrays.parallelSetAll(parallelFill, i -> i * i - 2 * i);

        System.out.println("setAll: "
                + Arrays.toString(sequentialFill));
        System.out.println("parallelSetAll equal: "
                + Arrays.equals(sequentialFill, parallelFill));

        int[] original = {2, 1, 0, 3};
        int[] sequentialPrefix = original.clone();
        int[] parallelPrefix = original.clone();

        for (int i = 1; i < sequentialPrefix.length; i++) {
            sequentialPrefix[i] += sequentialPrefix[i - 1];
        }
        Arrays.parallelPrefix(parallelPrefix, Integer::sum);

        System.out.println("prefix: "
                + Arrays.toString(parallelPrefix));
        System.out.println("prefix equals: "
                + Arrays.equals(sequentialPrefix, parallelPrefix));

        int[] range = {100, 1, 2, 3, 200};
        Arrays.parallelPrefix(range, 1, 4, Integer::sum);
        System.out.println("partial prefix: "
                + Arrays.toString(range));
    }
}
```

Chạy:

```bash
javac --release 17 ArrayFillAndPrefixDemo.java
java ArrayFillAndPrefixDemo
```

**Stdout chính xác:**

```text
setAll: [0, -1, 0, 3, 8, 15]
parallelSetAll equal: true
prefix: [2, 3, 3, 6]
prefix equals: true
partial prefix: [100, 1, 3, 6, 200]
```

**Giải thích:**

- `setAll` và `parallelSetAll` có cùng biểu thức tính theo chỉ số, không có side effect và luôn được kiểm tra bằng `Arrays.equals`.
- `parallelPrefix` là thao tác **in-place**. Vì cần đối chiếu, mảng ban đầu được clone hai lần trước khi xử lý.
- `parallelPrefix(range, 1, 4, Integer::sum)` chỉ cộng dồn **bên trong đoạn chỉ số 1..3**. Phần tử 0 (100) và 4 (200) không tham gia prefix và không đổi.
- Nếu dùng phép trừ `(a,b) -> a-b` thay vì phép cộng cho prefix, toán tử **không kết hợp**; khi nhóm dữ liệu khác nhau, phép tính song song không nhất thiết khớp vòng lặp tuần tự. Không dùng phép toán không thỏa hợp đồng để đòi kết quả song song ổn định.

## 6. Tính kết hợp: Điều kiện toán học phía sau parallel reduction/prefix

Một phép toán `op` là **kết hợp** (*associative*) nếu:

```text
(a op b) op c == a op (b op c)
```

Với phép kết hợp, thuật toán có thể chia dãy ra rồi gộp từng nhóm mà vẫn giữ kết quả theo phép toán đã định nghĩa. Chẳng hạn cộng số nguyên **trong ngữ nghĩa tràn số của `int`** là phép cộng modulo `2^32`: các cách nhóm cho cùng bit kết quả. Nhưng đó **không có nghĩa** tổng tính ra bằng tổng số học không giới hạn.

**Các phép có thể phù hợp** khi áp dụng đúng:

- Cộng `int`/`long` theo ngữ nghĩa Java, nếu bài toán chấp nhận modulo wraparound.
- `Integer::max` / `Long::min` cho miền dữ liệu phù hợp.
- Phép gộp bất biến, kết hợp trên kiểu dữ liệu riêng khi đã chứng minh được tính kết hợp.
- `BigInteger::add` nếu cần tổng nguyên chính xác vượt phạm vi của `long`.

**Các phép không mặc nhiên phù hợp:**

- Trừ liên tiếp: `(a - b) - c` khác `a - (b - c)`.
- Chia số thực: `(a / b) / c` thường khác `a / (b / c)`.
- Nối string mà thay đổi thứ tự phần tử hoặc cố dùng một `StringBuilder` mutable chung trong callback.
- “Cộng có giới hạn/trả giá trị đặc biệt khi overflow”, nếu logic làm mất tính kết hợp do quy tắc cắt/xử lý lỗi.
- Phép cộng `double` thông thường không có tính kết hợp chặt do làm tròn số thực.

**Quy tắc an toàn:** Với `parallelPrefix`, toán tử nên là **side-effect-free** và có tính kết hợp trên miền dữ liệu được phép. Với `Stream.reduce` song song, toán tử cũng phải thỏa identity/associativity và statelessness theo hợp đồng Stream. Không dùng counter ngoài lambda để mô phỏng reduction.

## 7. Tràn số nguyên: Kết quả giống nhau nhưng đều sai về toán học

Java dùng `int` có dấu 32 bit và `long` có dấu 64 bit. Phép cộng thông thường **không tự ném exception khi tràn**: kết quả wrap theo độ rộng bit.

### 7.1. Tràn `int` ở cả stream tuần tự và song song

Giả sử:

```java
int[] amounts = {Integer.MAX_VALUE, 1, 1};
```

Đây là một mảng trong phương thức. Tổng toán học chính xác là **2.147.483.649**. Nhưng `int` có giá trị lớn nhất **2.147.483.647**, nên:

```java
int sequentialSum = Arrays.stream(amounts).sum();
int parallelSum = Arrays.stream(amounts).parallel().sum();
```

Hai biến đều có thể nhận cùng kết quả `-2147483647` theo ngữ nghĩa phép cộng `int`, vì kết quả đã wrap. **Đối chiếu chỉ bằng `sequentialSum == parallelSum` sẽ báo PASS mặc dù tổng tiền/số lượng thực bị sai.**

### 7.2. Mở rộng kiểu **trước** khi cộng

Với `int[]`, dùng:

```java
long correct = Arrays.stream(amounts)
        .asLongStream()
        .sum();
```

hoặc:

```java
long correct = Arrays.stream(amounts)
        .mapToLong(x -> x)
        .sum();
```

Hai cách mở rộng **từng phần tử `int` thành `long` trước khi cộng**, cho `2147483649L`. Đừng viết `(long) Arrays.stream(amounts).sum()`: phép ép kiểu xảy ra **sau khi tổng `int` đã tràn**, không thể khôi phục dữ liệu.

Tuy nhiên, `long` cũng có giới hạn. `asLongStream().sum()` chỉ đúng về tổng toán học **nếu tổng thực tế nằm trong miền `long` và các thao tác trung gian được thiết kế phù hợp**. Khi tổng có thể vượt quá `Long.MAX_VALUE`, cân nhắc `BigInteger`.

### 7.3. Prefix cũng tràn

`Arrays.parallelPrefix(intArray, Integer::sum)` giữ mỗi phần tử prefix trong `int`. Với đầu vào `{Integer.MAX_VALUE, 1, 1}`:

```text
[2147483647, -2147483648, -2147483647]
```

Nếu mong prefix toán học là `[2147483647, 2147483648, 2147483649]`, phải dùng **`long[]` từ đầu**:

```java
long[] wide = Arrays.stream(amounts)
        .asLongStream()
        .toArray();
Arrays.parallelPrefix(wide, Long::sum);
```

Đây là các dòng trong một phương thức; kết quả `wide` là `[2147483647, 2147483648, 2147483649]`.

## 8. Ví dụ đầy đủ: so sánh int, long, BigInteger và kiểm tra overflow

Tạo file **`ArrayOverflowComparisonDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;

public class ArrayOverflowComparisonDemo {
    public static void main(String[] args) {
        int[] amounts = {Integer.MAX_VALUE, 1, 1};

        int sequential = Arrays.stream(amounts).sum();
        int parallel = Arrays.stream(amounts).parallel().sum();
        long wide = Arrays.stream(amounts)
                .asLongStream()
                .sum();
        long wideParallel = Arrays.stream(amounts)
                .parallel()
                .asLongStream()
                .sum();

        System.out.println("int sequential: " + sequential);
        System.out.println("int parallel: " + parallel);
        System.out.println("long sequential: " + wide);
        System.out.println("long parallel: " + wideParallel);

        int[] intPrefix = amounts.clone();
        Arrays.parallelPrefix(intPrefix, Integer::sum);
        System.out.println("int prefix: "
                + Arrays.toString(intPrefix));

        long[] longPrefix = Arrays.stream(amounts)
                .asLongStream().toArray();
        Arrays.parallelPrefix(longPrefix, Long::sum);
        System.out.println("long prefix: "
                + Arrays.toString(longPrefix));

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
            System.out.println("addExact overflow: false");
        } catch (ArithmeticException ex) {
            System.out.println("addExact overflow: true");
        }

        long[] beyondLong = {Long.MAX_VALUE, 1L};
        long wrapped = Arrays.stream(beyondLong).sum();
        BigInteger exact = Arrays.stream(beyondLong)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);

        System.out.println("long sum: " + wrapped);
        System.out.println("big sum: " + exact);
    }
}
```

Chạy:

```bash
javac --release 17 ArrayOverflowComparisonDemo.java
java ArrayOverflowComparisonDemo
```

**Stdout chính xác:**

```text
int sequential: -2147483647
int parallel: -2147483647
long sequential: 2147483649
long parallel: 2147483649
int prefix: [2147483647, -2147483648, -2147483647]
long prefix: [2147483647, 2147483648, 2147483649]
addExact overflow: true
long sum: -9223372036854775808
big sum: 9223372036854775808
```

**Bài học:**

- `int` và `long` wrap khi cộng vượt phạm vi; cả hai có thể “đồng nhất giữa tuần tự và song song” nhưng sai so với toán học.
- `Math.addExact` báo `ArithmeticException` khi hai toán hạng không thể cộng chính xác trong kiểu đã chọn. Nó giúp **phát hiện** tràn chứ không tạo kiểu kết quả rộng hơn.
- Nếu dùng `addExact` như toán tử reduction song song, phải đặc biệt thận trọng: **nhóm các tổng trung gian khác nhau có thể làm phát sinh ngoại lệ ở một nhánh dù tổng cuối theo số học vẫn nằm trong miền kiểu**. Đó không phải một toán tử kết hợp toàn phần trên các giá trị có thể gây overflow. Để tính tổng lớn chính xác, mở rộng miền số trước.
- Với `BigInteger`, phép cộng số nguyên có độ chính xác tùy ý theo khả năng tài nguyên. Cả `BigInteger.ZERO` và `BigInteger::add` hợp với phép reduction theo cộng. Chỉ dùng khi dữ liệu/kiểu đầu ra thật sự cần, vì cấp phát và hiệu năng khác số nguyên thủy.

### 8.1. Nếu không được phép tràn, chọn cách nào?

| Yêu cầu | Hướng xử lý |
| --- | --- |
| Dữ liệu `int[]`, tổng chắc chắn nằm trong `long` | `Arrays.stream(a).asLongStream().sum()` |
| Dữ liệu `long[]`, tổng có thể vượt `long` | Chuyển từng giá trị sang `BigInteger` rồi reduce |
| Cần báo lỗi ngay khi một phép cộng tràn | `Math.addExact` trong thuật toán có thứ tự kiểm soát được; lưu ý cả overflow ở intermediate |
| Cần tính tất cả prefix chính xác trên miền số rộng | `long[]` nếu đủ; `BigInteger[]` khi cần số nguyên lớn |
| Giá trị số dùng cho tiền/đơn vị | Quy định rõ đơn vị, miền giá trị, làm tròn; dùng cents nguyên có kiểm tra hoặc `BigDecimal` khi thích hợp |

Đừng cố sửa bằng việc “thêm `parallel()`” hay “ép kiểu sau phép tính”. Hai thao tác này **không thay đổi miền chứa tổng đã được tính**.

## 9. Số thực: Cùng input vẫn có thể khác kết quả hợp lệ

Không nên kết luận song song có race chỉ vì tổng `double` chênh lệch vài bit. Số dấu phẩy động `double` được làm tròn sau mỗi phép toán, và phép cộng **không kết hợp chặt**.

Ví dụ ba giá trị:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;
```

Về toán học, tổng là 1. Nhưng các cách nhóm khác nhau trong `double` cho:

```java
double left = (a + b) + c;   // 1.0
double right = a + (b + c);  // 0.0
```

Ở biểu thức thứ hai, `b + c` bị làm tròn khiến `1.0` không còn đóng góp ở độ lớn `1e16`. Sau đó cộng với `a` cho 0. Không có thread nào sửa dữ liệu ngoài; sai khác do **thứ tự làm tròn**.

### 9.1. `DoubleStream.sum` và `Arrays.parallelPrefix(double[], ...)`

- `Arrays.stream(doubleArray).sum()` và `Arrays.stream(doubleArray).parallel().sum()` là các phép reduction có thể dùng chiến lược chia/gộp khác. Javadoc `DoubleStream.sum` có lưu ý về độ chính xác số học và không nên kiểm thử dựa trên giả định kết quả phải có bit pattern giống nhau ở mọi lịch gộp.
- `Arrays.parallelPrefix(doubleArray, Double::sum)` cũng có thể khác vòng lặp cộng dồn tuần tự: tài liệu `Arrays.parallelPrefix(double[])` **nêu rõ** kết quả có thể không trùng với cách tính tuần tự do phép toán floating-point không kết hợp chặt.
- `NaN` và `Infinity` làm phức tạp việc cộng và so sánh; cần xác định chúng có được phép trong domain không.
- Nếu bài toán cần tính tiền hoặc số thập phân với quy tắc chính xác, không dùng phép so sánh `double == expected` như thể mọi phép toán là số thực toán học. Cân nhắc `BigDecimal`, fixed-point hoặc chiến lược xử lý được domain quy định.

**Đừng viết một unit test bắt buộc `parallelSum != sequentialSum`**: một lần chạy vẫn có thể cho cùng kết quả, vì thuật toán có thể chọn cùng hoặc tương đương cách gộp. Ví dụ phân nhóm ở trên chứng minh **có khả năng khác nhau**, không cam kết Java luôn chọn hai nhánh khác nhau.

### 9.2. Kiểm thử `double[]` và signed zero

`Arrays.equals(double[], double[])` dùng ngữ nghĩa so sánh tương thích với `Double.doubleToLongBits`: các biểu diễn `NaN` được xem bằng nhau theo quy tắc đó, còn `-0.0` và `+0.0` **không giống nhau** cho mục đích equals của mảng.

Nếu nghiệp vụ coi hai số gần nhau là tương đương, hãy viết **hàm so sánh xấp xỉ** theo tolerance cụ thể và xử lý `NaN`/Infinity/từng vị trí. Không tùy tiện áp dụng một epsilon tuyệt đối nhỏ cho mọi độ lớn: có thể cần kết hợp sai số tuyệt đối và tương đối, tùy miền dữ liệu.

### 9.3. Ví dụ đầy đủ: Floating-point và thứ tự sort

Tạo file **`ArrayFloatingComparisonDemo.java`**:

```java
import java.util.Arrays;

public class ArrayFloatingComparisonDemo {
    public static void main(String[] args) {
        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        System.out.println("double left: " + ((a + b) + c));
        System.out.println("double right: " + (a + (b + c)));

        double[] special = {
                Double.NaN,
                Double.POSITIVE_INFINITY,
                +0.0,
                -0.0,
                Double.NEGATIVE_INFINITY
        };
        Arrays.parallelSort(special);

        System.out.println("floating sort: "
                + Arrays.toString(special));

        System.out.println("NaN arrays equal: "
                + Arrays.equals(
                        new double[]{Double.NaN},
                        new double[]{Double.NaN}
                ));

        System.out.println("signed-zero arrays equal: "
                + Arrays.equals(
                        new double[]{-0.0},
                        new double[]{+0.0}
                ));
    }
}
```

Chạy:

```bash
javac --release 17 ArrayFloatingComparisonDemo.java
java ArrayFloatingComparisonDemo
```

**Stdout:**

```text
double left: 1.0
double right: 0.0
floating sort: [-Infinity, -0.0, 0.0, Infinity, NaN]
NaN arrays equal: true
signed-zero arrays equal: false
```

Điểm cần kiểm thử riêng:

1. **Giá trị rất lớn và rất nhỏ** trong cùng một phép cộng.
2. **Số dương và âm triệt tiêu nhau**, dẫn đến sai số làm tròn.
3. **NaN, ±Infinity, +0.0 và -0.0** trong dữ liệu.
4. **Giá trị âm nhỏ**, số dưới chuẩn (subnormal) nếu có trong domain.
5. Kết quả **được phép xấp xỉ** hay bắt buộc đúng bit pattern theo yêu cầu thuật toán.

Tốt hơn hãy so sánh **độ đúng với một reference chính xác thích hợp** thay vì chỉ đối chiếu tuần tự và song song mà không biết cả hai có chính xác không.

## 10. Thứ tự dữ liệu đầu ra không giống thứ tự chạy lambda

Với stream tạo từ mảng, có **encounter order**. Một pipeline stateless dùng `map` rồi `toArray` có thể chạy các phép biến đổi trên nhiều tác vụ nhưng vẫn lắp kết quả **theo thứ tự nguồn**.

Ví dụ:

```java
int[] transformed = Arrays.stream(new int[]{10, 20, 30, 40})
        .parallel()
        .map(x -> x + 1)
        .toArray();

System.out.println(Arrays.toString(transformed));
```

Đây là đoạn trong một phương thức với import `java.util.Arrays`. Kết quả:

```text
[11, 21, 31, 41]
```

Nhưng với:

```java
Arrays.stream(new int[]{10, 20, 30, 40})
        .parallel()
        .forEach(System.out::println);
```

Đây là **đoạn minh họa**, không có stdout theo thứ tự cố định. `forEach` có thể gọi action ở thứ tự bất kỳ khi chạy song song. Nếu muốn action theo encounter order, `forEachOrdered` làm rõ hợp đồng nhưng có thể giảm lợi ích song song. Khi muốn **thu mảng kết quả**, `toArray` thường phù hợp hơn việc tự ghi vào `ArrayList` dùng chung.

### 10.1. Vì sao dùng biến/cấu trúc ngoài là nguy hiểm?

Phản ví dụ:

```java
// Không an toàn và không có stdout được cam kết:
int[] counter = {0};

Arrays.stream(new int[10_000])
        .parallel()
        .forEach(x -> counter[0]++);
```

Nhiều thread cùng cập nhật một ô mảng bằng `++` không nguyên tử, có thể mất lần tăng. Thay bằng `count()` nếu muốn đếm phần tử, `sum()` hoặc `reduce` với phép kết hợp đúng nếu muốn tổng. Nếu bài toán thực sự đòi hỏi side effect, phải có thiết kế đồng bộ rõ ràng và không làm hỏng source trong lúc stream đang duyệt.

Đồng thời **không** sửa chính mảng nguồn trong các lambda của `Arrays.stream(array).parallel()` rồi giả định Spliterator/Stream tự bảo vệ kết quả; dữ liệu nguồn cần ổn định trong khi pipeline tiêu thụ, trừ khi một API chuyên biệt cho phép đồng thời và có hợp đồng rõ.

## 11. Kiểm thử tự động: So với reference và so với hai chế độ

Chỉ kiểm tra `Arrays.equals(sequential, parallel)` là chưa đủ. Cần thêm **reference expected** ở những ca quan trọng. Một unit test tốt:

- So sánh hai cách chạy **trên hai bản sao** cùng input.
- Xác nhận kết quả với expected đã được xác lập độc lập.
- Xác minh không thay đổi input gốc nếu API/thuật toán không được phép.
- Có **dữ liệu biên gây tràn** và kiểm tra bằng `long`/`BigInteger`.
- Không gắn assertion với thứ tự callback/thời gian hoàn tất thread.
- Dùng so sánh xấp xỉ cho `double` nếu yêu cầu chỉ quy định sai số cho phép.
- Kiểm tra các API in-place đúng phạm vi, không làm đổi phần tử ngoài đoạn.

### 11.1. Chương trình Java 17+ dùng assertions chủ động

Tạo file **`ArrayComparisonChecks.java`**:

```java
import java.util.Arrays;

public class ArrayComparisonChecks {
    static void check(boolean valid, String message) {
        if (!valid) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        int[] original = {4, -2, 9, 4, 0, 1};
        int[] sequential = original.clone();
        int[] parallel = original.clone();

        Arrays.sort(sequential);
        Arrays.parallelSort(parallel);

        check(Arrays.equals(sequential, parallel), "sort mismatch");
        check(Arrays.equals(
                sequential,
                new int[]{-2, 0, 1, 4, 4, 9}),
                "wrong sorted values");
        check(Arrays.equals(
                original,
                new int[]{4, -2, 9, 4, 0, 1}),
                "original was modified");
        System.out.println("Sort: PASS");

        int[] source = {2, 1, 0, 3};
        int[] seqPrefix = source.clone();
        int[] parPrefix = source.clone();

        for (int i = 1; i < seqPrefix.length; i++) {
            seqPrefix[i] += seqPrefix[i - 1];
        }
        Arrays.parallelPrefix(parPrefix, Integer::sum);
        check(Arrays.equals(seqPrefix, parPrefix), "prefix mismatch");
        check(Arrays.equals(parPrefix, new int[]{2, 3, 3, 6}),
                "wrong prefix");
        System.out.println("Prefix: PASS");

        int[] edge = {Integer.MAX_VALUE, 1, 1};
        check(Arrays.stream(edge).sum()
                == Arrays.stream(edge).parallel().sum(),
                "unexpected int reduction");
        check(Arrays.stream(edge).asLongStream().sum()
                == 2147483649L,
                "wide sum incorrect");
        check(Arrays.stream(edge).sum() != 2147483649L,
                "overflow was not detected");
        System.out.println("Overflow detected: PASS");

        int[] empty = {};
        int[] one = {42};
        Arrays.parallelSort(empty);
        Arrays.parallelSort(one);
        check(empty.length == 0 && one[0] == 42,
                "boundary sort incorrect");
        System.out.println("Empty and singleton: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 ArrayComparisonChecks.java
java ArrayComparisonChecks
```

**Stdout:**

```text
Sort: PASS
Prefix: PASS
Overflow detected: PASS
Empty and singleton: PASS
```

Mẫu `check(...)` chủ động ném `AssertionError` khi có sai, nên hoạt động ngay cả khi không bật cờ JVM `-ea`. Nếu dùng Java `assert ...;` thông thường, cần bật `java -ea` trong kiểm thử; mặc định nhiều môi trường không bật Java assertion.

**Ranh giới của test:** Chương trình kiểm tra bộ dữ liệu cụ thể, không chứng minh mọi thuật toán tương đương trên mọi input. Bổ sung các mảng với kích thước khác nhau, dữ liệu trùng nhiều, số âm, số cực trị và trường hợp nhiều phần tử khiến thuật toán thật sự chia tác vụ song song.

## 12. Tập ca biên nên có khi thử thuật toán mảng

| Nhóm test | Input tiêu biểu | Điều cần khẳng định |
| --- | --- | --- |
| Mảng rỗng | `new int[0]` | Kết quả/exception đúng contract; sort không làm hỏng dữ liệu |
| Một phần tử | `{42}` | Không dựa vào giả định có nhiều tác vụ |
| Hai phần tử đảo | `{2, 1}` | Sort và prefix đúng |
| Nhiều phần tử trùng | `{5, 5, 5, 1, 1}` | Sort không mất giá trị, object sort giữ stable order khi cần |
| Đã sắp xếp | `{1, 2, 3, 4}` | Không thay đổi sai |
| Đảo ngược | `{4, 3, 2, 1}` | Đúng mọi vị trí |
| Số âm và số 0 | `{-3, 0, 2}` | Tổng/prefix đúng dấu |
| `int` cực trị | `{MIN_VALUE, MAX_VALUE, 1}` | Không suy luận sai do phép cộng overflow |
| `long` cực trị | `{Long.MAX_VALUE, 1}` | Chọn BigInteger nếu cần chính xác |
| Range đầu/cuối | `from=0, to=length` | Đoạn sort/prefix được chọn đúng |
| Range rỗng | `from=to` | Không sửa phần tử ngoài đoạn |
| Index sai | `from=-1`, `to>length` | Exception đúng hợp đồng |
| Object keys bằng nhau | Comparator trả 0 trên hai object khác | Stable order với object sort |
| Generator có side effect | Counter mutable dùng chung | Phát hiện mẫu sai, thay bằng generator thuần |
| Số thực rất lớn + rất nhỏ | `1e16, -1e16, 1.0` | Nhận biết phép cộng không kết hợp |
| Số thực đặc biệt | `NaN`, `±Infinity`, `±0.0` | So sánh phù hợp contract |
| Chạy nhiều lần | Dữ liệu tự sinh với seed ổn định | Không phụ thuộc ngẫu nhiên không kiểm soát |

Chỉ chạy nhiều lần không **chứng minh vắng mặt race**. Khi test đồng thời, cần xem hợp đồng thread safety và, nếu cần, stress-test/property-test có dữ liệu được thiết kế để kích hoạt lỗi.

## 13. Kiến trúc kiểm thử tốt hơn cho dữ liệu lớn

Khi bài toán xử lý hàng triệu bản ghi:

1. **Định nghĩa expected behavior trước:** sort tăng, prefix đúng toán học, tổng không được tràn hay được wrap theo protocol? Không có câu trả lời chung cho mọi nghiệp vụ.
2. **Chọn reference đơn giản:** thuật toán tuần tự rõ ràng, có kiểu rộng/độ chính xác thích hợp. Với dữ liệu giá trị lớn, reference `BigInteger` có thể dễ kiểm chứng hơn.
3. **Đối chiếu độc lập:** chạy tuần tự và song song trên **bản sao đầu vào**. Đừng dùng cùng một mảng mutable cho hai phép tính.
4. **Kiểm tra toàn bộ hoặc đặc trưng cần thiết:** `Arrays.equals`, `Arrays.mismatch`, kiểm tra permutation/đếm giá trị nếu cần. Nếu output là float, định nghĩa tolerance.
5. **Kiểm tra bất biến dữ liệu:** kết quả không mất phần tử, số lượng không đổi khi sort, phần tử ngoài range giữ nguyên.
6. **Kiểm thử mọi miền dữ liệu được phép:** âm, 0, min/max, duplicates, rỗng, giá trị cực lớn, null object khi có Comparator xử lý.
7. **Tách test đúng/sai và đo hiệu năng:** benchmark không được đánh đồng với tính đúng đắn; pass unit test không chứng minh parallel nhanh hơn.
8. **Chỉ tối ưu khi cần:** nếu kích thước mảng nhỏ hoặc chi phí tác vụ thấp, chi phí chia/gộp có thể làm parallel chậm hơn tuần tự.

Nếu muốn benchmark nghiêm túc trong Java, nên dùng **JMH** để xử lý warm-up/JIT, tránh dead-code elimination, lặp đo và cấu hình môi trường. Không nên kết luận thuật toán nào nhanh chỉ từ một lần `System.nanoTime()` trong một chương trình không có warm-up; có thể chạy ngoài lúc CPU tải cao, bộ nhớ/GC khác nhau và trạng thái cache khác nhau.

## 14. Một ví dụ nghiệp vụ: Tổng số lượng và tổng tiền

Giả sử một `int[] quantities` chứa số lượng bán theo đơn và mỗi lượng có thể rất lớn. Khi chỉ tính số đơn:

```java
long numberOfOrders = quantities.length;
```

Nếu tính tổng sản phẩm, **đừng** dùng `Arrays.stream(quantities).sum()` khi tổng có thể vượt `int`. Với miền dữ liệu số lượng thỏa tổng nằm trong `long`:

```java
long totalQuantity = Arrays.stream(quantities)
        .parallel()
        .asLongStream()
        .sum();
```

Đây là các đoạn mã **trong phương thức**, giả sử `quantities` là `int[]` đã khởi tạo. Một biến `long` để chứa kết quả **không đủ** nếu phép cộng được tính trước bằng `int`; cần mở rộng từng phần tử trước reduction.

Nếu các lượng là số tiền tính theo **đơn vị nhỏ nhất** (ví dụ cents) và đầu vào là `long[]`, hãy xác định miền tổng tối đa. Nếu có khả năng tràn `long`, cân nhắc `BigInteger`; nếu cần giá thập phân, cân nhắc `BigDecimal` theo chính sách làm tròn của hệ thống. Việc dùng mảng song song không tự khắc phục được vấn đề overflow hoặc đồng bộ dữ liệu với database bên ngoài JVM.

Nếu cần **tổng tích lũy theo thời gian** từ các đơn được đặt đúng thứ tự, `parallelPrefix` trên mảng kiểu rộng là một lựa chọn, với điều kiện phép gộp có tính kết hợp theo ngữ nghĩa mong muốn. Tránh dùng `parallelPrefix` với logic có tác dụng phụ lên hệ thống ngoài hoặc phụ thuộc thời điểm thread thực thi.

## 15. Những lỗi thường gặp

1. **Đối chiếu trên cùng mảng đã bị `sort` sửa trước đó:** phải clone đầu vào cho từng thuật toán.
2. **Dùng `arrayA == arrayB` để so kết quả:** đó là tham chiếu, không phải nội dung; dùng `Arrays.equals`.
3. **Nghĩ song song luôn nhanh hơn:** song song có overhead và phụ thuộc dữ liệu/hệ thống.
4. **Nghĩ song song luôn phải cho thứ tự callback giống tuần tự:** `parallel().forEach` không cam kết thứ tự.
5. **Nghĩ song song cho phép sort sai thứ tự:** `parallelSort` vẫn phải tuân theo hợp đồng sắp xếp.
6. **Quên stable sorting của mảng object:** `Arrays.parallelSort(T[], Comparator)` giữ thứ tự tương đối của phần tử comparator coi bằng nhau.
7. **Dùng comparator có state mutable:** có thể gây data race hoặc thứ tự không nhất quán trong sort.
8. **Đếm `sum()` int tuần tự bằng `sum()` int song song rồi kết luận không tràn:** hai bên có thể cùng wrap.
9. **Ép `long` sau khi đã tính `int` sum:** giá trị int tràn không được phục hồi.
10. **Nghĩ `long` không bao giờ tràn:** `long[]` cộng cũng có giới hạn 64 bit.
11. **Dùng `Math.addExact` rồi tưởng kết quả sẽ có độ rộng vô hạn:** addExact chỉ phát hiện overflow bằng exception.
12. **Cho rằng `Math.addExact` là reduction parallel an toàn cho mọi dãy nếu tổng cuối vừa kiểu:** overflow trung gian phụ thuộc cách gộp có thể dẫn tới lỗi.
13. **Dùng phép trừ làm operator cho `parallelPrefix`:** phép trừ không kết hợp.
14. **Nghĩ `parallelPrefix` trả mảng mới:** nó sửa trực tiếp mảng được truyền vào.
15. **Lấy prefix của đoạn [from,to) nhưng cộng thêm phần tử ngoài range:** prefix cho range bắt đầu từ chính phần tử ở `fromIndex`.
16. **Dùng generator có counter ngoài ở `parallelSetAll`:** phụ thuộc shared state và thứ tự chạy.
17. **Bỏ qua khả năng generator ném lỗi:** mảng có thể bị sửa một phần; không tự động rollback.
18. **Ghi vào `ArrayList` từ `parallel().forEach`:** `ArrayList` không thread-safe; dùng `toArray`/collector phù hợp.
19. **Dùng `DoubleStream.sum` rồi assert tuyệt đối giống bitwise trong mọi parallel execution:** thứ tự gộp và làm tròn số thực cần được xem xét.
20. **Coi `NaN` hoặc `-0.0` như số thường trong mọi phép so sánh:** phải hiểu `Double.compare` và `Arrays.equals(double[])`.
21. **Dùng `Arrays.equals` như deep compare cho mọi mảng lồng nhau:** với object arrays chứa arrays, cân nhắc `Arrays.deepEquals`.
22. **Đổi input trong khi song song đang duyệt:** gây vi phạm quy tắc về nguồn ổn định, kết quả khó xác định.
23. **Không thử mảng rỗng, 1 phần tử, range lỗi:** test không bao phủ giới hạn API.
24. **Đo thời gian một lần, không warm-up, rồi tuyên bố parallel tốt hơn:** phải benchmark phù hợp và đo dữ liệu thực.

## 16. Câu hỏi tự kiểm tra

1. Vì sao phải `clone()` mảng trước khi chạy `Arrays.sort` và `Arrays.parallelSort` để đối chiếu?
2. Với `int[]{Integer.MAX_VALUE, 1, 1}`, tại sao hai lệnh `Arrays.stream(a).sum()` và `Arrays.stream(a).parallel().sum()` có thể trả giống nhau nhưng không bằng tổng toán học?
3. `(long) Arrays.stream(a).sum()` khác `Arrays.stream(a).asLongStream().sum()` ở điểm nào?
4. `Arrays.parallelPrefix(a, Integer::sum)` sửa mảng gốc hay tạo mảng mới?
5. Vì sao phép trừ không phù hợp làm operator của `parallelPrefix` khi muốn tương đương cộng dồn tuần tự?
6. `Arrays.parallelSetAll(a, i -> counter++)` có thể gây lỗi gì khi counter dùng chung giữa các thread? Nên thay bằng cách nào nếu muốn `a[i] = i`?
7. `Arrays.parallelSort(T[], Comparator)` có được phép đảo hai object có `compare == 0` không?
8. Vì sao `(1e16 + (-1e16)) + 1.0` khác `1e16 + ((-1e16) + 1.0)` trong double?
9. Vì sao `Arrays.equals(new double[]{-0.0}, new double[]{+0.0})` trả false dù `-0.0 == +0.0` trả true?
10. Trong `Arrays.parallelSort(a, 1, 5)`, các chỉ số nào bị sắp xếp? Chỉ số 5 có được lấy không?
11. Nếu cần cộng `Long.MAX_VALUE + 1` chính xác, nên mở rộng sang kiểu nào?
12. Khi `Arrays.parallelSetAll` có generator ném exception, có được coi toàn mảng chưa bị thay đổi không?

**Đáp án gợi ý:** (1) Các API sort sửa mảng trực tiếp; cần hai đầu vào độc lập. (2) Cùng overflow trong `int`; modulo wrap không phải tổng toán học. (3) Cách đầu ép kiểu sau overflow, cách sau mở rộng phần tử trước khi cộng. (4) Sửa in-place. (5) Không associative, nhóm khác có thể khác kết quả. (6) Data race/mất cập nhật; dùng `i -> i`. (7) Không, object parallel sort được bảo đảm stable. (8) Làm tròn floating point và phép cộng không kết hợp chặt. (9) Arrays.equals dùng quy tắc so sánh khác toán tử `==` đối với signed zero. (10) 1,2,3,4; không gồm 5. (11) `BigInteger`. (12) Không; mảng có thể ở trạng thái được điền một phần.

**Kết luận:** Kết quả **tuần tự và song song** cần được đối chiếu bằng đúng hợp đồng từng API và **trên cùng input được sao chép độc lập**. Với mảng nguyên, phép cộng có thể wrap khiến hai cách chạy **bằng nhau nhưng sai số học**; với `double`, cách nhóm có thể khác nhau dù code không có data race. Hãy chọn kiểu số phù hợp, toán tử kết hợp/không side effect, các phép so sánh mảng đúng kiểu, bộ ca biên đầy đủ và kiểm thử expected độc lập trước khi dùng parallel để tối ưu tốc độ.

## Tài liệu Java chính thức — API còn áp dụng

- `Arrays` — `sort`, `parallelSort`, `setAll`, `parallelSetAll`, `parallelPrefix`, `equals` và `mismatch`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html
- `IntStream` — `sum`, `asLongStream`, `parallel`, `toArray`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html
- `LongStream` — `sum`, `mapToObj`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html
- `DoubleStream` — `sum` và lưu ý số thực: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/DoubleStream.html
- Stream package — associative reduction, statelessness, non-interference và parallel execution: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html
- `Math.addExact` — phát hiện overflow bằng exception: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html
- `BigInteger` — số nguyên chính xác có miền giá trị lớn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html
