# Chi phí common pool và ngưỡng dữ liệu phù hợp khi xử lý mảng trong Java

## 1. Vấn đề: `parallel` không đồng nghĩa nhanh hơn

Java cung cấp các thao tác trên **mảng** có phiên bản tuần tự và song song, nổi bật từ Java 8:

- **`Arrays.sort(array)` và `Arrays.parallelSort(array)`**: sắp xếp tại chỗ. Phiên bản song song có thể chia mảng thành những đoạn nhỏ, sắp xếp các đoạn rồi hợp nhất.
- **`Arrays.setAll(array, generator)` và `Arrays.parallelSetAll(array, generator)`**: gán giá trị cho từng phần tử dựa vào chỉ số. Phiên bản song song có thể xử lý các chỉ số đồng thời.
- **`Arrays.parallelPrefix(array, operator)`**: tính phép tích lũy *prefix* trên mảng tại chỗ theo toán tử **kết hợp được**, ví dụ từ `[1,2,3,4]` thành `[1,3,6,10]` khi dùng phép cộng.

Các API này vẫn được hỗ trợ trên JDK hiện đại. Điểm chung: **song song phải trả một chi phí cố định và biến thiên trước khi đem lại lợi ích**. Với mảng nhỏ hoặc phép xử lý đơn giản, bản tuần tự có thể nhanh hơn. Với mảng lớn, nhiều lõi CPU thực sự rảnh và đủ công việc trên mỗi nhánh, xử lý song song *có cơ hội* tốt hơn.

Bài này phân tích hai câu hỏi thực tế:

1. **Chi phí ForkJoin common pool đến từ đâu, và tại sao nó có thể làm chậm thao tác mảng?**
2. **Cách xác định ngưỡng kích thước mảng phù hợp** cho `parallelSort`, `parallelSetAll` hoặc `parallelPrefix` mà không bịa ra một số cố định?

> Không có quy tắc chung kiểu “mảng từ 8.192/10.000/100.000 phần tử là nên gọi `parallelSort`”. Những số nội bộ của một phiên bản OpenJDK không phải ngưỡng tăng tốc được Java API cam kết.

### 1.1. So sánh các API đúng mục tiêu

| Mục tiêu | Cách tuần tự | Cách có cơ chế song song |
| --- | --- | --- |
| Sắp xếp `int[]` | `Arrays.sort(a)` | `Arrays.parallelSort(a)` |
| Sắp xếp `T[]` theo comparator | `Arrays.sort(a, cmp)` | `Arrays.parallelSort(a, cmp)` |
| Điền giá trị theo chỉ số | `Arrays.setAll(a, i -> ...)` | `Arrays.parallelSetAll(a, i -> ...)` |
| Tổng lũy kế từng vị trí | Vòng lặp tích lũy tuần tự | `Arrays.parallelPrefix(a, Integer::sum)` |
| Chỉ cần tổng cuối cùng | Vòng lặp hoặc `Arrays.stream(a).sum()` | Có thể thử primitive stream song song; **không cần** tạo cả mảng prefix |

`parallelSort` và `parallelSetAll` cập nhật **mảng truyền vào**, không tự tạo bản sao. Muốn giữ đầu vào, dùng `clone()` hoặc cách sao chép thích hợp. `parallelPrefix` cũng sửa mảng tại chỗ.

## 2. ForkJoin common pool là gì?

`ForkJoinPool` là cơ chế thực thi các tác vụ dạng chia nhỏ rồi hợp nhất (*fork/join*) trong `java.util.concurrent`. Nó hỗ trợ *work-stealing*: worker có thể lấy việc từ những worker khác khi còn công việc chưa xử lý.

`ForkJoinPool.commonPool()` là một pool **dùng chung trong JVM** cho nhiều hoạt động sử dụng cơ chế Fork/Join. Theo hợp đồng của `Arrays.parallelSort`, **ForkJoin common pool được dùng để thực thi các tác vụ song song của thuật toán này**. Khi mảng đủ nhỏ, implementation có thể chạy đường tuần tự của `Arrays.sort` thay vì tạo nhiều tác vụ Fork/Join.

Sơ đồ ý tưởng khi sắp xếp mảng:

```text
Mảng gốc
   |
   +-- chia đoạn trái --------> worker A: sort đoạn trái
   |
   +-- chia đoạn phải --------> worker B: sort đoạn phải
                                               |
                hợp nhất hai đoạn đã sort <----+
                           |
                      mảng đã sort
```

Hình này chỉ minh họa quy trình; số tác vụ, số nhánh, thứ tự xử lý và mức độ song song phụ thuộc JDK, kích thước và môi trường.

### 2.1. Dùng chung pool có hệ quả gì?

- **Không có một worker mới dành riêng cho mỗi phần tử.** Nhiều phần tử được xử lý trong một tác vụ; task scheduling không miễn phí.
- **Pool có thể đang bận** vì công việc Fork/Join khác. Nếu những tác vụ đó cũng cần CPU hoặc bị chặn, độ trễ xử lý mảng có thể tăng.
- **Có tranh chấp CPU, cache và băng thông bộ nhớ.** Thêm worker không bảo đảm nhiều dữ liệu được xử lý hơn mỗi giây.
- **Nhiều request cùng gọi thao tác song song** có thể khiến throughput toàn dịch vụ kém hơn dù từng request riêng lẻ chạy tốt trong bài thử cô lập.
- **Pool không phải transaction manager.** Một tác vụ lỗi không làm mọi thay đổi mảng tự động rollback.
- **Không thể truyền riêng một `Executor`/`ForkJoinPool` vào `Arrays.parallelSort(a)`** qua overload chuẩn. Nếu hệ thống cần tài nguyên/cách ly nghiêm ngặt, phải cân nhắc thiết kế xử lý song song khác thay vì giả định có tham số pool ẩn.

Một số API khác trong Java cũng có thể sử dụng common pool theo cơ chế và điều kiện riêng; không suy ra **mọi** tác vụ chạy bất đồng bộ đều mặc định dùng chung pool đó.

### 2.2. Xem thông tin pool, nhưng đừng suy diễn speedup

```java
import java.util.concurrent.ForkJoinPool;

int targetParallelism =
    ForkJoinPool.getCommonPoolParallelism();
int visibleProcessors =
    Runtime.getRuntime().availableProcessors();
```

Đây là đoạn mã minh họa đặt trong method. `getCommonPoolParallelism()` mô tả mức **parallelism mục tiêu** của common pool, không phải số worker đang chạy thao tác hiện tại. `availableProcessors()` là số bộ xử lý JVM nhìn thấy ở môi trường đó, **không phải** lượng CPU rảnh hay hệ số tăng tốc bảo đảm.

Cấu hình runtime, CPU quota/container, số request đồng thời và các tác vụ khác đều tác động đến công suất thực có. Không điều chỉnh thuộc tính toàn JVM `java.util.concurrent.ForkJoinPool.common.parallelism` một cách tùy tiện chỉ để làm nhanh một mảng: nó ảnh hưởng tài nguyên dùng chung, và việc cấu hình/quan sát pool thay đổi theo JDK.

## 3. Phân rã chi phí song song: chia việc, điều phối, gộp và bộ nhớ

Với thao tác tuần tự, chi phí chủ yếu là thuật toán xử lý mảng. Với thao tác song song, phải cộng thêm những khoản khác:

```text
T_tuan_tu ≈ T_thuat_toan_tuan_tu

T_song_song ≈ T_chia_doan
            + T_dieu_phoi_ForkJoin
            + T_thuat_toan_tren_cac_nhanh
            + T_hop_nhat
            + T_bo_nho_dong_bo_va_tranh_chap
```

Mô hình định tính khác:

```text
T_parallel ≈ Overhead + Work / P_effective + Merge + MemoryCost

P_effective <=? số lõi khả dụng, thường thấp hơn mức lý tưởng;
không có công thức đơn giản dự báo chính xác mọi loại mảng.
```

Các thành phần cụ thể:

1. **Chia mảng:** tính các đoạn con, tạo/điều phối task và xác định khi nào cần dừng chia.
2. **Fork/Join scheduling:** đẩy task vào hàng đợi, lấy việc, đồng bộ điểm hoàn thành; work-stealing có ích nhưng không miễn phí.
3. **Làm việc trên nhánh:** sắp từng phần mảng, gọi comparator hoặc tạo giá trị từ generator.
4. **Hợp nhất:** với `parallelSort`, các đoạn đã sắp cần được merge; đây là công việc thực sự và có chi phí bộ nhớ.
5. **Bộ nhớ đệm và băng thông:** nhiều worker đọc/ghi mảng lớn có thể làm tăng cache misses hoặc bão hòa memory bandwidth.
6. **Cạnh tranh với việc khác:** common pool cùng CPU có thể đang phục vụ những đoạn khác của ứng dụng; tác động tăng mạnh dưới tải đồng thời.
7. **Cấp phát và GC:** sắp xếp song song có thể dùng vùng làm việc bổ sung; với kiểu đối tượng, comparator hoặc key extractor cũng có thể tạo object tạm.

**Đánh đổi quan trọng:** sắp xếp song song không nhất thiết tiết kiệm **tổng lượng CPU**. Nó có thể rút ngắn *latency* một phép sort bằng cách dùng **nhiều CPU đồng thời hơn**, làm ảnh hưởng throughput và latency của các request khác.

### 3.1. Chi phí bộ nhớ của `Arrays.parallelSort`

Tài liệu `Arrays.parallelSort` mô tả thuật toán dạng **parallel sort-merge**, có thể cần vùng nhớ làm việc bổ sung **không vượt quá kích thước mảng hoặc vùng mảng đang sắp**, theo cách mô tả của overload tương ứng.

Do đó phải cân nhắc ngân sách RAM khi sắp nhiều mảng lớn đồng thời. Không chỉ xem số lõi CPU: giới hạn heap, GC và vùng đệm dùng để merge có thể quyết định liệu phương án song song có phù hợp.

`Arrays.sort` cũng có thể cần bộ nhớ tạm tùy kiểu mảng và triển khai; không khẳng định nó tuyệt đối không cấp phát. Chỉ có thể kết luận phương án phù hợp sau khi tính cả chi phí bộ nhớ thực tế.

## 4. “Ngưỡng dữ liệu phù hợp” là ngưỡng nào?

Có **hai khái niệm khác nhau** thường bị đánh đồng:

### 4.1. Ngưỡng phân chia bên trong implementation

Trong mô tả `Arrays.parallelSort`, khi kích thước đoạn xuống tới **minimum granularity**, thuật toán sắp đoạn đó bằng `Arrays.sort`. Nếu mảng ban đầu nhỏ hơn ngưỡng phân chia, đường xử lý có thể chính là sắp xếp tuần tự.

Đây là **chi tiết thuật toán được mô tả bởi JDK**, không phải cấu hình ứng dụng công khai hay cam kết rằng “trên ngưỡng là nhanh hơn”. Kích thước cụ thể, lượng task và heuristics có thể khác giữa phiên bản JDK, kiểu mảng hoặc môi trường. Không hard-code một số rút ra từ mã nguồn JDK để làm **ngưỡng nghiệp vụ phổ quát**.

### 4.2. Điểm hòa vốn hiệu năng của ứng dụng

Điểm hòa vốn (*break-even point*) là kích thước hoặc khối lượng công việc tại đó:

```text
Thời gian parallel (bao gồm overhead)
           <
Thời gian sequential
```

Ngưỡng thực tế phụ thuộc ít nhất:

- **Số phần tử `N`** và loại mảng: `int[]`, `long[]`, `double[]`, `String[]`, đối tượng tùy biến.
- **Chi phí so sánh:** so số nguyên rẻ; comparator tính nhiều trường hoặc trích thuộc tính phức tạp có thể nặng hơn.
- **Dạng dữ liệu:** ngẫu nhiên, đã tăng/giảm, gần như đã sắp, có rất nhiều phần tử trùng nhau.
- **Mức song song hiệu dụng:** lõi CPU, giới hạn container, tải common pool và scheduler.
- **Chi phí bộ nhớ:** kích thước mảng, vùng đệm merge, GC và memory bandwidth.
- **Mục tiêu đo:** latency một lần xử lý, throughput theo giây, p95/p99 dưới tải hay mức sử dụng CPU.

Một tập dữ liệu `N=100_000` có thể là ứng viên tốt ở máy đa lõi ít tải nhưng không hiệu quả trong container giới hạn CPU hoặc dịch vụ đang bão hòa. Vì vậy, **đo kiểm bằng nhiều kích thước dữ liệu** mới xác định được ngưỡng vận hành.

### 4.3. Không dùng một ngưỡng cho tất cả API

`parallelSort` có chi phí **sort + merge**. `parallelSetAll` không cần merge dữ liệu theo thứ tự sắp xếp, nhưng nếu generator chỉ trả `i+1`, phép toán quá nhẹ và có thể thua `setAll`. `parallelPrefix` cần phối hợp các phần kết quả lũy tích, nên điểm hòa vốn lại khác.

Cùng `N` không đồng nghĩa cùng workload. Thay vì “mảng bao nhiêu phần tử?”, hãy hỏi “mỗi phần tử tốn bao nhiêu CPU, dữ liệu dễ chia không, và cần gộp theo thuật toán nào?”.

## 5. `Arrays.sort` và `Arrays.parallelSort`: lựa chọn theo dữ liệu

### 5.1. So sánh trực tiếp trên mảng primitive

```java
int[] original = {5, 1, 4, 2, 3};
int[] sequential = original.clone();
int[] parallel = original.clone();

Arrays.sort(sequential);
Arrays.parallelSort(parallel);

boolean same = Arrays.equals(sequential, parallel); // true
```

Đây là snippet trong một method (cần `import java.util.Arrays;`). Hai kết quả đều `[1,2,3,4,5]`. `clone()` quan trọng vì cả `sort` và `parallelSort` đều biến đổi mảng truyền vào; nếu dùng cùng một mảng để chạy bản tuần tự trước rồi song song sau thì hai lần chạy **không cùng đầu vào** nữa.

Với primitive, thứ tự mặc định là thứ tự số tương ứng; một số kiểu như `float`/`double` có thêm quy tắc so sánh với `NaN` và số không có dấu, phải theo hợp đồng `Arrays.sort`, không tự thay bằng `a < b` đơn giản.

### 5.2. Sắp xếp mảng đối tượng và chi phí comparator

```java
Employee[] employees = { /* cac Employee hop le */ };

Arrays.parallelSort(employees,
    Comparator.comparingInt(Employee::score)
              .thenComparing(Employee::id));
```

Đây là **snippet minh họa**, yêu cầu lớp `Employee` có `score()` và `id()`, và các import `Arrays`, `Comparator`. Nếu comparator rất nhẹ, overhead chia/merge có thể trội với mảng nhỏ. Nếu comparator nặng, phần công việc trên mỗi nhánh nhiều hơn nhưng phải bảo đảm comparator đúng hợp đồng, **stateless**, không làm thay đổi input hoặc dữ liệu được so sánh.

`Arrays.parallelSort(T[], Comparator)` **bảo đảm stable sort**: các phần tử comparator coi là bằng nhau (`compare == 0`) giữ thứ tự tương đối ban đầu. Nhưng “ổn định” không có nghĩa comparator tự tách hai đối tượng khác ID cùng điểm; nếu nghiệp vụ cần thứ tự duy nhất, thêm tie-breaker rõ ràng.

Để tránh boxing khi so sánh trường số nguyên, `Comparator.comparingInt` thường phù hợp hơn `Comparator.comparing` với key kiểu `Integer`, tuy nhiên tác động hiệu năng vẫn cần đo.

### 5.3. Sắp xếp một đoạn: `fromIndex` bao gồm, `toIndex` loại trừ

```java
int[] a = {9, 5, 4, 1, 8};
Arrays.parallelSort(a, 1, 4);
// a = [9, 1, 4, 5, 8]
```

Chỉ phần tử tại vị trí `1,2,3` được sắp. Không có bảo đảm `parallel` tốt hơn khi khoảng ngắn; trên thực tế đoạn nhỏ thường là trường hợp nên ưu tiên đường tuần tự khi có quyền lựa chọn.

### 5.4. Dạng dữ liệu khác nhau cho kết quả tốc độ khác nhau

Mảng gần như đã sắp có thể cho `Arrays.sort` (đặc biệt với kiểu object) cơ hội tận dụng cấu trúc dữ liệu; với mảng ngẫu nhiên lớn, song song có thể có lợi hơn. Mảng có phần tử trùng nhiều, comparator phức tạp hoặc giá trị object lớn có thể thay đổi chi phí gộp và cache.

Vì vậy bài benchmark nên thử **nhiều phân phối**, không tạo một mảng random duy nhất rồi tuyên bố ngưỡng chung.

## 6. `Arrays.parallelSetAll` và `Arrays.parallelPrefix`: cùng mảng nhưng khác chi phí

### 6.1. `parallelSetAll`: generator tính từng vị trí

```java
int[] values = new int[6];
Arrays.parallelSetAll(values, index -> index * index);
// [0, 1, 4, 9, 16, 25]
```

`parallelSetAll` gọi generator theo chỉ số để gán giá trị trong mảng. Generator nên là **hàm xác định từ chỉ số/đầu vào bất biến**, không phụ thuộc thứ tự thread hoặc biến đếm chia sẻ. Nếu dùng generator quá rẻ, overhead song song có thể lớn hơn mọi công việc hữu ích.

**Không nên:**

```java
AtomicInteger counter = new AtomicInteger();
Arrays.parallelSetAll(values, i -> counter.getAndIncrement());
```

Đây là đoạn minh họa dùng `AtomicInteger`, không phải mô hình tối ưu. Kết quả ở từng vị trí phụ thuộc thứ tự thực thi các callback, nên không còn là một hàm theo chỉ số dễ kiểm tra. Atomic chỉ giải quyết tính nguyên tử của biến đếm, không giúp thứ tự được xác định; contention trên một biến chia sẻ cũng làm giảm lợi ích. Muốn `values[i] = i`, hãy dùng trực tiếp `i -> i`.

Theo tài liệu API, nếu generator ném exception, `parallelSetAll` truyền tiếp exception dạng unchecked và **mảng có thể ở trạng thái không xác định** sau khi dừng; không mong chờ rollback. Với nghiệp vụ cần all-or-nothing, tính trên mảng tạm rồi chỉ công bố kết quả sau khi thành công.

### 6.2. `parallelPrefix`: điều kiện phép toán kết hợp được

`parallelPrefix` tính tổng lũy tích (prefix scan):

```java
int[] prefix = {1, 2, 3, 4, 5};
Arrays.parallelPrefix(prefix, Integer::sum);
// [1, 3, 6, 10, 15]
```

Giá trị ở vị trí `i` là phép tích lũy từ phần tử đầu đến phần tử `i`. Để chia đoạn và gộp mà không làm đổi ngữ nghĩa, toán tử phải **associative**:

```text
op(op(a,b),c) == op(a,op(b,c))
```

Các phép cộng số nguyên trên miền dữ liệu có kiểm soát và các phép tính tổng nhóm thích hợp là những ứng viên thông dụng. **Phép trừ** không kết hợp: `(10-3)-2 = 5` trong khi `10-(3-2) = 9`, nên không dùng `(a,b)->a-b` cho prefix song song nếu cần kết quả tuần tự tương ứng. Toán tử cũng phải tránh side effect vì có thể được gọi trong những cách phân hoạch khác nhau.

**Số thực:** phép cộng `double`/`float` có làm tròn và không kết hợp một cách chính xác; tài liệu `parallelPrefix(double[])` cho phép kết quả có sai khác với cách cộng tuần tự. Khi cần kết quả thập phân chính xác, lựa chọn mô hình dữ liệu hoặc phép tổng hợp phù hợp, không dựa vào số thread.

Nếu bài toán chỉ cần **một tổng cuối cùng**, `Arrays.stream(a).asLongStream().sum()` (với `int[]`) có thể diễn đạt đúng ý nghĩa mà không cần tính toàn bộ prefix. Nếu muốn tổng số nguyên lớn, tránh tràn `int` bằng cách mở rộng kiểu hoặc kiểm soát miền giá trị.

## 7. Ví dụ Java hoàn chỉnh: kết quả đúng không chứng minh tăng tốc

Mã dưới đây chỉ sử dụng API từ Java 8, chạy được trên các JDK hiện đại. Nó kiểm tra:

1. `Arrays.sort` và `Arrays.parallelSort` cho cùng thứ tự trên **hai bản sao cùng dữ liệu**.
2. Mảng gốc vẫn giữ nguyên khi sắp xếp bản sao.
3. `parallelSort` hoạt động đúng với mảng nhỏ và vùng chỉ số `[fromIndex,toIndex)`.
4. Sắp xếp **stable** của mảng đối tượng khi nhiều phần tử có cùng điểm.
5. `parallelSetAll` và `parallelPrefix` cho kết quả dự đoán được với hàm thuần túy và phép toán kết hợp.
6. Có thể quan sát thông số parallelism mục tiêu mà **không lấy nó làm kết luận hiệu năng**.

Tạo file **ArrayCommonPoolThresholdDemo.java**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.concurrent.ForkJoinPool;

public class ArrayCommonPoolThresholdDemo {
    static final class Student {
        final String name;
        final int score;

        Student(String name, int score) {
            this.name = name;
            this.score = score;
        }

        @Override
        public String toString() {
            return name + ":" + score;
        }
    }

    static boolean nonDecreasing(int[] values) {
        for (int i = 1; i < values.length; i++) {
            if (values[i - 1] > values[i]) {
                return false;
            }
        }
        return true;
    }

    static long checksum(int[] values) {
        long total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    public static void main(String[] args) {
        int[] original = new int[20_000];

        // Khoi tao co the lap lai, khong dung random khong seed.
        Arrays.setAll(original,
            i -> ((i * 37 + 11) % 10_007) - 5_000);

        int[] sequential = original.clone();
        int[] parallel = original.clone();

        Arrays.sort(sequential);
        Arrays.parallelSort(parallel);

        System.out.println("Sort cho cung ket qua: "
            + Arrays.equals(sequential, parallel));
        System.out.println("Ket qua da tang dan: "
            + nonDecreasing(parallel));
        System.out.println("Tong gia tri duoc giu: "
            + (checksum(original) == checksum(parallel)));
        System.out.println("Mang goc khong bi sort: "
            + !Arrays.equals(original, sequential));

        int[] small = {5, -3, 1, 5, 0};
        Arrays.parallelSort(small);
        System.out.println("Mang nho: " + Arrays.toString(small));

        int[] range = {9, 4, 7, 2, 8};
        Arrays.parallelSort(range, 1, 4);
        System.out.println("Sap xep doan [1,4): "
            + Arrays.toString(range));

        Student[] students = {
            new Student("Lan", 90),
            new Student("An", 95),
            new Student("Binh", 90),
            new Student("Hoa", 88)
        };
        Arrays.parallelSort(students,
            Comparator.comparingInt(s -> s.score));
        System.out.println("Sort object stable: "
            + Arrays.toString(students));

        int[] generated = new int[6];
        Arrays.parallelSetAll(generated, i -> i * i);
        System.out.println("parallelSetAll: "
            + Arrays.toString(generated));

        int[] prefix = {1, 2, 3, 4, 5};
        Arrays.parallelPrefix(prefix, Integer::sum);
        System.out.println("parallelPrefix: "
            + Arrays.toString(prefix));

        int target = ForkJoinPool.getCommonPoolParallelism();
        System.out.println("Common parallelism >= 1: "
            + (target >= 1));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ArrayCommonPoolThresholdDemo.java
java ArrayCommonPoolThresholdDemo
```

**Stdout chính xác:**

```text
Sort cho cung ket qua: true
Ket qua da tang dan: true
Tong gia tri duoc giu: true
Mang goc khong bi sort: true
Mang nho: [-3, 0, 1, 5, 5]
Sap xep doan [1,4): [9, 2, 4, 7, 8]
Sort object stable: [Hoa:88, Lan:90, Binh:90, An:95]
parallelSetAll: [0, 1, 4, 9, 16, 25]
parallelPrefix: [1, 3, 6, 10, 15]
Common parallelism >= 1: true
```

**Vì sao kết quả đáng tin?**

- `Arrays.setAll` tạo đầu vào xác định. Hai thuật toán sort chạy trên **hai bản sao** giống nhau; `Arrays.equals` xác minh toàn bộ thứ tự kết quả, thay vì chỉ so hai số tổng.
- So sánh tổng bằng `long` kiểm tra không làm mất giá trị trong ví dụ; nó là phép kiểm tra bổ sung, không thay thế kiểm tra toàn mảng.
- `Arrays.parallelSort(range,1,4)` chỉ tác động chỉ số `1,2,3`. Kết quả vùng khác phải được giữ nguyên.
- `Comparator.comparingInt(Student::score)` chỉ so điểm. Thứ tự `Lan` trước `Binh` được giữ lại khi cùng điểm `90`, minh họa stable sort.
- `parallelSetAll` dùng generator theo **chỉ số**; kết quả không phụ thuộc lịch chạy. `parallelPrefix` dùng phép cộng kết hợp nên cho prefix dự đoán được.
- `ForkJoinPool.getCommonPoolParallelism()` chỉ xác nhận JVM báo mức parallelism mục tiêu hợp lệ; không chứng minh có nhiều thread chạy, không chứng minh nhanh hơn.

Chương trình **không in thời gian** vì không có “stdout hiệu năng chuẩn” chung cho mọi máy. Nó được thiết kế để xác minh **tính đúng đắn** trước khi đo tốc độ.

## 8. Benchmark để tìm điểm hòa vốn thực tế

Để trả lời “mảng đủ lớn là bao nhiêu?”, cần benchmark trên **dữ liệu và môi trường của chính ứng dụng**.

### 8.1. Thiết lập ma trận thí nghiệm

Thay đổi có kiểm soát các yếu tố:

| Yếu tố | Các trường hợp nên thử | Câu hỏi |
| --- | --- | --- |
| Kích thước | `256`, `2_048`, `16_384`, `131_072`, `1_048_576` hoặc kích thước thực tế | Khi nào chi phí song song được bù? |
| Kiểu mảng | `int[]`, `long[]`, `double[]`, `T[]` | Primitive và object có cùng điểm hòa vốn không? |
| Phân bố | Ngẫu nhiên có seed, đã sort, gần sort, nhiều giá trị trùng | Dạng nào ảnh hưởng sort/merge? |
| Comparator | Số nguyên nhẹ, nhiều trường, so chuỗi, chi phí CPU lớn | Cường độ công việc có thay đổi ngưỡng không? |
| CPU | Giới hạn 1–2 vCPU, nhiều CPU rảnh, CPU đang bão hòa | Có lợi khi song song hiệu dụng thấp không? |
| Tải | Chỉ một phép sort, nhiều request cùng lúc | Có tăng latency tail hoặc giảm throughput không? |
| Tài nguyên | Heap, allocation rate, GC, bandwidth | Memory overhead có làm kết quả kém đi không? |

Các kích thước ở bảng **chỉ là điểm thử nghiệm mẫu**, không phải ngưỡng Java cam kết. Mỗi phép toán (`sort`, `setAll`, `prefix`) cần được đo riêng.

### 8.2. Đo công bằng: cùng dữ liệu đầu vào, không sort một mảng hai lần

**Sai:**

```java
long start1 = System.nanoTime();
Arrays.sort(data);
long t1 = System.nanoTime() - start1;

long start2 = System.nanoTime();
Arrays.parallelSort(data); // data da duoc sort tu lan dau!
long t2 = System.nanoTime() - start2;
```

Đây là **minh họa sai**, giả sử có biến `int[] data`. Hai lần chạy xử lý hai trạng thái đầu vào khác nhau. Đừng kết luận từ `t1` và `t2`.

**Đúng về tính công bằng đầu vào:**

```java
int[] copyA = data.clone();
int[] copyB = data.clone();

long start1 = System.nanoTime();
Arrays.sort(copyA);
long t1 = System.nanoTime() - start1;

long start2 = System.nanoTime();
Arrays.parallelSort(copyB);
long t2 = System.nanoTime() - start2;

if (!Arrays.equals(copyA, copyB)) {
    throw new AssertionError("Different sort result");
}
```

Đây là snippet trong một method cần `data`, import `Arrays`. Nó tốt hơn vì hai phương án nhận **cùng dữ liệu** và việc clone diễn ra trước khi bắt đầu đo. Tuy nhiên, đây vẫn chỉ là **một phép đo thô**: JIT, warm-up, GC, CPU scaling, scheduler và nội dung cache có thể khiến số đo dao động. Với môi trường sản xuất còn phải tính cả chi phí copy nếu thiết kế ứng dụng đòi giữ bản gốc.

### 8.3. Dùng JMH cho microbenchmark đáng tin

**JMH (Java Microbenchmark Harness)** là công cụ phù hợp khi muốn đo chênh lệch của các thao tác Java rất ngắn. Một phương án benchmark hợp lệ thường:

1. Chuẩn bị dữ liệu trong `@Setup` theo size/config đã chọn, seed cố định và phân bố đại diện.
2. Với mỗi lần đo `sort`, sử dụng **một bản sao chưa sắp**; không đo liên tiếp trên cùng mảng đã sort.
3. So sánh `Arrays.sort` và `Arrays.parallelSort` trong cùng điều kiện thử. Nếu benchmark bao gồm chi phí clone ở mỗi invocation, phải **nêu rõ** kết quả là tổng chi phí clone + sort cho cả hai phương án.
4. Có warm-up, nhiều iteration đo và nhiều fork để hạn chế ảnh hưởng trạng thái JIT/JVM.
5. Tránh dead-code elimination: đưa kết quả vào cơ chế tiêu thụ kết quả của JMH hoặc trả kết quả benchmark một cách phù hợp.
6. Tách thử nghiệm **latency cô lập** và **throughput dưới tải đồng thời**. Common pool có thể trông nhanh khi chỉ có một tác vụ nhưng cạnh tranh khi có nhiều request.
7. Ghi JDK, OS, số vCPU/CPU quota, heap, GC, độ song song common pool và kích thước dữ liệu để tái lập phép thử.

Nếu chưa có JMH, `System.nanoTime()` có thể giúp khám phá sơ bộ, **không** nên dùng một phép đo duy nhất để đưa ra kết luận tuyệt đối.

### 8.4. Tính speedup và chọn ngưỡng có biên an toàn

```text
speedup = T_sequential / T_parallel

speedup > 1  -> parallel nhanh hơn trong phép đo đó
speedup = 1  -> tương đương trong phép đo đó
speedup < 1  -> parallel chậm hơn trong phép đo đó
```

Ví dụ **giả định, không phải benchmark thực tế**:

| Kích thước | Tuần tự | Song song | Speedup |
| --- | ---: | ---: | ---: |
| `1_000` | 0,1 ms | 0,6 ms | 0,17× |
| `100_000` | 8 ms | 6 ms | 1,33× |
| `1_000_000` | 100 ms | 42 ms | 2,38× |

Từ bảng minh họa này **không thể kết luận một ngưỡng chung** cho mọi loại mảng. Ngay với một ứng dụng, chọn điểm chuyển chế độ chỉ khi nhiều lần đo cho mức lợi ích **rõ hơn nhiễu**, tiêu thụ CPU/bộ nhớ chấp nhận được và tải thực tế còn phù hợp. Có thể thêm một vùng đệm an toàn (*safety margin*) để tránh chuyển trạng thái theo dao động nhỏ của số liệu.

Một ứng dụng có thể chủ động chọn `Arrays.sort` với input nhỏ, và `Arrays.parallelSort` khi input lớn **theo ngưỡng được kiểm chứng**. Đừng phụ thuộc vào một con số đo trên laptop nếu triển khai trên máy chủ hoặc container khác.

## 9. Khi common pool bị cạnh tranh: nhìn vào toàn hệ thống

Giả sử dịch vụ web đồng thời xử lý nhiều request; mỗi request có một mảng vài trăm nghìn phần tử. Trong bài benchmark đơn lẻ, `parallelSort` có thể giảm latency. Nhưng nếu nhiều request cùng làm vậy, tất cả cùng cần CPU và có thể tranh common pool, dẫn đến:

- Tăng thời gian chờ task hoặc bão hòa CPU.
- Tăng memory bandwidth/GC do nhiều vùng làm việc song song.
- Latency của request khác dao động, đặc biệt ở p95/p99.
- Throughput toàn hệ thống không tăng, thậm chí giảm, dù một phép sort chạy độc lập nhanh hơn.

Vì thế phải tách hai mục tiêu:

- **Latency một thao tác:** `parallelSort` có giảm thời gian hoàn thành một mảng khi hệ thống ít tải không?
- **Throughput một dịch vụ:** với tải đồng thời, tổng số request/giây và độ ổn định latency có tốt hơn không?

Không có một lựa chọn luôn tối ưu cả hai. Nếu cần **giới hạn đồng thời hoặc cách ly tài nguyên**, có thể giữ `Arrays.sort` theo request hoặc chuyển sang kiến trúc tác vụ có executor riêng và backpressure. Bản thân `Arrays.parallelSort` không nhận executor do ứng dụng truyền vào; không mô tả nó như có thể “đổi common pool” bằng một overload không tồn tại.

`ForkJoinPool` thích hợp với tác vụ tính toán chia nhỏ CPU; các công việc blocking I/O kéo dài trong cùng môi trường có thể làm worker khó duy trì độ song song hiệu dụng. Đừng dùng việc tăng parallelism trên toàn JVM để che giấu bottleneck I/O.

## 10. Các tình huống quyết định

| Bài toán thực tế | Nhận định ban đầu | Phương án kiểm chứng |
| --- | --- | --- |
| Sort `int[]` vài chục/vài trăm phần tử | Tác vụ rất nhỏ; chi phí song song khó bù | Bắt đầu với `Arrays.sort` |
| Sort `int[]` hàng triệu phần tử ngẫu nhiên | Có cơ hội tận dụng nhiều lõi | Benchmark `sort` vs `parallelSort` cùng input |
| Sort mảng đối tượng với comparator nhiều trường | Công việc mỗi so sánh có thể nặng; comparator phải thuần túy | Đo cả comparator cost, GC và tính stable |
| Sort mảng đã gần đúng thứ tự | Thuật toán tuần tự có thể tận dụng cấu trúc dữ liệu | Thử phân bố gần sort, không chỉ random |
| Điền mảng bằng `i -> i * 2` | Generator rất nhẹ | `Arrays.setAll` thường là baseline hợp lý |
| Điền giá trị bằng phép tính CPU độc lập nặng | Có nhiều công việc trên từng chỉ số | Thử `parallelSetAll` sau khi kiểm tra tính thuần túy |
| Tính prefix tổng trên mảng lớn | Toán tử cộng kết hợp; mục tiêu là tất cả prefix | So vòng lặp và `parallelPrefix` |
| Chỉ cần tổng cuối, không cần prefix | Tạo toàn bộ prefix là việc thừa | Dùng phép tổng trực tiếp thích hợp |
| Dịch vụ xử lý nhiều mảng cùng lúc | Cạnh tranh common pool, CPU, bộ nhớ | Đo throughput và tail latency toàn dịch vụ |
| Container bị quota CPU nhỏ | Ít song song hiệu dụng | Ưu tiên benchmark trực tiếp trên môi trường deploy |

Các nhận định ở bảng chỉ là **giả thuyết kỹ thuật**, không thay thế số liệu thực tế.

## 11. Những lỗi phổ biến cần tránh

### 11.1. Dùng “mốc nội bộ JDK” làm quy tắc nghiệp vụ

`Arrays.parallelSort` có ngưỡng chia nhỏ để tránh tạo quá nhiều tác vụ, nhưng con số đó không phải một hứa hẹn speedup. Không viết `if (n >= SOME_JDK_INTERNAL_NUMBER)` chỉ vì thấy hằng số tương ứng trong source của một bản JDK.

### 11.2. Đo trên mảng đã sắp từ phép thử trước

`sort` sửa mảng tại chỗ. Benchmark phải clone/reset input để hai phương án được đo cùng trạng thái.

### 11.3. Kết luận chỉ từ `getCommonPoolParallelism()`

Mức song song mục tiêu không cho biết CPU còn rảnh, lượng task thực tế đã chia, queue contention hay tốc độ dữ liệu. Không in một số parallelism rồi suy ra speedup xấp xỉ số đó.

### 11.4. Generator hoặc comparator có side effect

`Arrays.parallelSetAll(a, i -> sharedCounter++)` vừa không an toàn vừa phụ thuộc thứ tự. Comparator thay đổi trạng thái dữ liệu trong khi so sánh có thể vi phạm hợp đồng và làm sort sai. Dùng hàm xác định, không can thiệp vào nguồn đang được thuật toán xử lý.

### 11.5. `parallelPrefix` với phép toán không kết hợp

Phép trừ, chia hoặc phép cộng `double` cần xem xét kỹ: kết quả có thể khác phép tích lũy tuần tự do cách nhóm/độ chính xác. Chọn phép toán có ngữ nghĩa phù hợp và kiểm thử dữ liệu biên.

### 11.6. Quên chi phí bộ nhớ và tải đồng thời

Một mảng lớn có thể tận dụng nhiều lõi nhưng đòi thêm vùng làm việc. Khi xử lý nhiều mảng đồng thời, RAM, GC và common pool contention đều cần đo; thời gian một thao tác giảm không bảo đảm throughput tốt hơn.

### 11.7. Tưởng mọi lời gọi “parallel” bắt buộc dùng nhiều worker

Implementation có thể chọn đường tuần tự cho dữ liệu quá nhỏ, máy giới hạn CPU hoặc điều kiện cụ thể. API tên `parallelSort` cam kết **kết quả sắp xếp đúng**, không cam kết số thread đã thực thi hay phần trăm cải thiện hiệu năng.

### 11.8. Thử dữ liệu không đại diện

Các mảng phân bố ngẫu nhiên không giống mảng gần sắp, nhiều giá trị trùng hoặc object comparator phức tạp. Benchmark phải gần với dữ liệu sản xuất và có tái lập.

## 12. Checklist trước khi chọn `parallel`

1. **Đúng API:** cần sort, setAll hay prefix? Có cần làm thay đổi mảng gốc không?
2. **Đúng kết quả:** sort tuần tự/song song cho mảng bằng nhau? Comparator có tính nhất quán? Prefix có toán tử kết hợp và không side effect?
3. **Nguồn công việc:** bao nhiêu phần tử, loại mảng gì, comparator/generator nặng tới đâu?
4. **Dạng dữ liệu:** random, tăng, giảm, gần sort, nhiều duplicate, có null hoặc dữ liệu biên?
5. **Chi phí pool:** có chia được hiệu quả, overhead khởi tạo task và merge có lớn không?
6. **Tài nguyên:** CPU/vCPU thực sự sẵn, heap, bandwidth, common pool đang có tải?
7. **Benchmark công bằng:** hai bản sao cùng input; warm-up, nhiều iteration/fork, kiểm tra output?
8. **Mục tiêu:** ưu tiên latency thao tác riêng hay throughput/p95 của cả dịch vụ?
9. **Ngưỡng:** kết quả có đủ rõ rệt, ổn định qua nhiều tải/JDK để đặt threshold vận hành?
10. **Giám sát:** nếu dữ liệu/phần cứng/tải thay đổi, có đo lại và điều chỉnh quyết định không?

**Kết luận:** Với mảng, hãy coi `Arrays.sort` và các phép toán tuần tự như **đường baseline cần đo**, không phải phương án “lạc hậu”. `Arrays.parallelSort`, `Arrays.parallelSetAll` và `Arrays.parallelPrefix` là API hiện đại hữu ích khi workload đủ lớn, phép tính chia được và tài nguyên song song thật sự có lợi. **Ngưỡng phù hợp phải được quyết định từ benchmark và yêu cầu toàn hệ thống**, không lấy từ tên hàm hay hằng số nội bộ của một phiên bản JVM.

## 13. Tài liệu chính thức

Các API và hợp đồng trong bài có từ Java 8 và vẫn được duy trì; tài liệu JDK hiện đại mô tả chi tiết:

- [`Arrays` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): `sort`, `parallelSort`, minimum granularity, ForkJoin common pool, `setAll`, `parallelSetAll` và `parallelPrefix`.
- [`ForkJoinPool` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): common pool, work-stealing, parallelism và đặc tính tài nguyên.
- [`Comparator` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): yêu cầu tính nhất quán của comparator khi sort object.
- [`IntStream` — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html): các phép tính số không yêu cầu tạo toàn bộ mảng prefix.
- [JMH — OpenJDK Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): phương pháp đo microbenchmark với warm-up, measurement và forks.
