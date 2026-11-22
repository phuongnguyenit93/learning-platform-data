# Accumulator: thêm phần tử vào vùng tích lũy trong Collector tùy chỉnh

## 1. Tại sao cần hiểu accumulator?

Một pipeline Java Stream thường kết thúc bằng phương thức §collect(...)§. Khi yêu cầu thu thập đặc biệt hơn §toList()§, §joining()§ hoặc §groupingBy()§, ta có thể tự tạo **Collector**. Bộ thu thập phải biết cách tạo vùng lưu trạng thái, thêm từng phần tử vào vùng đó, kết hợp các vùng khi thực thi phân đoạn và chuyển trạng thái thành kết quả.

Trong bốn thành phần ấy, **accumulator** là hàm làm nhiệm vụ trực tiếp: **nhận vùng tích lũy hiện tại và một phần tử Stream, cập nhật vùng tích lũy để ghi nhận phần tử đó**.

Ví dụ với danh sách tên:

§§§text
Stream<String>           "Lan"   "An"   "Minh"
                            \      |     /
                             \     |    /
Accumulator: add vào   ArrayList<String>
                                  |
                                  v
Kết quả:                  [Lan, An, Minh]
§§§

Khi tự tạo collector, không nên tưởng §accumulator§ trả về một danh sách mới ở mỗi phần tử. Theo hợp đồng §Collector§, nó là một **BiConsumer** và trả về §void§. Nó thường **mutate vùng tích lũy tạm thời** §A§ được cấp bởi §supplier§. Vùng tạm này khác với nguồn Stream và khác với đối tượng kết quả §R§ sau khi §finisher§ chuyển đổi.

## 2. Bốn vai trò của Collector<T, A, R>

Interface §java.util.stream.Collector<T,A,R>§ biểu diễn cách thu thập các phần tử §T§ thành kết quả §R§, qua vùng tích lũy §A§.

| Thành phần | Kiểu khái niệm | Vai trò |
| --- | --- | --- |
| §supplier§ | §Supplier<A>§ | Tạo vùng tích lũy mới, độc lập |
| **§accumulator§** | **§BiConsumer<A,T>§** | **Thêm một phần tử §T§ vào vùng §A§** |
| §combiner§ | §BinaryOperator<A>§ | Hợp nhất hai vùng tích lũy cùng kiểu §A§ |
| §finisher§ | §Function<A,R>§ | Đổi vùng tích lũy thành kết quả §R§ |
| §characteristics§ | §Set<Collector.Characteristics>§ | Khai báo đặc tính khi thích hợp, chẳng hạn §IDENTITY_FINISH§, §UNORDERED§, §CONCURRENT§ |

Ví dụ các kiểu cụ thể:

§§§text
Collector<String, ArrayList<String>, List<String>>
          T           A                  R

supplier:    () -> new ArrayList<String>()
accumulator: (list, word) -> list.add(word)
combiner:    (left, right) -> { left.addAll(right); return left; }
finisher:    list -> List.copyOf(list)
§§§

Chú ý: §T§ và §A§ không buộc phải cùng kiểu; §A§ và §R§ cũng không bắt buộc giống nhau. Chẳng hạn ta có thể thu một Stream số thành đối tượng thống kê chứa số lượng, tổng và trung bình.

**Accumulator không chọn nhóm** và không tự sắp xếp. Nó làm một nhiệm vụ cục bộ theo hợp đồng: tiếp nhận đúng một phần tử và tích lũy thông tin vào vùng được cung cấp.

## 3. Chữ ký accumulator và cách hoạt động

Phương thức trừu tượng của §BiConsumer<T,U>§ có chữ ký:

§§§java
void accept(T first, U second);
§§§

Đối với Collector, các kiểu được gán như sau:

§§§java
BiConsumer<A, T> accumulator
§§§

Nó nhận:

1. **Tham số thứ nhất §A§:** vùng tích lũy hiện tại do §supplier§ tạo, ví dụ §ArrayList<String>§ hoặc §MutableStats§.
2. **Tham số thứ hai §T§:** phần tử đang được Stream chuyển tới collector, ví dụ §String`, §Employee§ hoặc §Integer§.
3. **Kết quả trả về:** §void§; tác động được ghi vào đối tượng vùng tích lũy.

Ví dụ:

§§§java
(list, item) -> list.add(item)
§§§

§ArrayList.add(item)§ trả boolean, nhưng lambda ở đây được dùng trong ngữ cảnh target type trả §void§: Java cho phép bỏ qua giá trị trả về của một statement expression tương thích. Viết dạng block sẽ làm ý nghĩa cập nhật dễ đọc hơn:

§§§java
(list, item) -> {
    list.add(item);
}
§§§

Cả hai là **đoạn minh họa**, chỉ đầy đủ về nghĩa khi compiler biết kiểu §list§, §item§ thông qua collector. Về mặt thiết kế, accumulator thường nên **cập nhật đúng container được truyền vào**, tránh trả một vùng mới rồi không ghi nhận nó.

Nếu một mapper chỉ tạo giá trị mới và không chỉnh sửa vùng tích lũy, đó chưa phải một accumulator thích hợp. Với collector, vùng §A§ được dùng làm chỗ lưu trung gian để combiner và finisher có thể quan sát đúng dữ liệu.

## 4. Ví dụ Java 17+ hoàn chỉnh: thu tên vào vùng List

Ta muốn chuẩn hóa từng tên bằng §trim§ và §toUpperCase(Locale.ROOT)§, sau đó đưa vào list theo thứ tự nguồn. Thay vì dùng §map(...).toList()§, ví dụ dưới tạo collector riêng **để học về accumulator**.

Lưu tệp §ListAccumulatorDemo.java§:

§§§java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collector;

public class ListAccumulatorDemo {
    public static void main(String[] args) {
        List<String> names = List.of("  lan  ", "minh", " an ");

        Collector<String, ArrayList<String>, List<String>> collector =
                Collector.of(
                        ArrayList::new,
                        (bucket, raw) -> {
                            String cleaned = raw.trim()
                                    .toUpperCase(Locale.ROOT);
                            bucket.add(cleaned);
                        },
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf
                );

        List<String> result = names.stream().collect(collector);

        System.out.println("result=" + result);
        System.out.println("count=" + result.size());
        System.out.println("source unchanged=" +
                names.get(0).equals("  lan  "));
    }
}
§§§

Biên dịch/chạy:

§§§bash
javac ListAccumulatorDemo.java
java ListAccumulatorDemo
§§§

Output chính xác:

§§§text
result=[LAN, MINH, AN]
count=3
source unchanged=true
§§§

**Theo dõi toàn bộ chu kỳ:**

1. §ArrayList::new§ tạo một §ArrayList<String>§ rỗng làm vùng tạm §A§.
2. Với từng chuỗi đầu vào, **accumulator** nhận §(bucket, raw)§, chuẩn hóa tên và gọi §bucket.add(cleaned)§. Trạng thái mong đợi sau các phần tử là §[LAN]§, rồi §[LAN, MINH]§, cuối cùng §[LAN, MINH, AN]§ nếu framework thực thi tuần tự theo thứ tự nguồn.
3. §combiner§ được cung cấp để hai vùng tạm có thể được hợp nhất khi framework cần; một pipeline tuần tự không bắt buộc phải gọi nó.
4. §List::copyOf§ hoàn tất, tạo §List<String>§ không sửa được cấu trúc như kết quả. Collector không trả trực tiếp §ArrayList§ mutable từ accumulator.
5. Nguồn §names§ vẫn giữ nguyên chuỗi có khoảng trắng. Accumulator cập nhật container mới, **không sửa source List**.

Giải thích về performance: trong ứng dụng chỉ cần chuẩn hóa rồi lấy list, cách viết sẵn có §names.stream().map(...).toList()§ ngắn và dễ hiểu hơn. Collector tùy chỉnh ở đây có giá trị vì **làm rõ vòng đời vùng tích lũy**.

## 5. Vì sao accumulator mutate A nhưng không nên mutate nguồn?

Đây là điểm phân biệt quan trọng trong lập trình hàm với Java Stream:

- **Mutation bên trong container §A§ do collector sở hữu** là cách làm tiêu chuẩn của mutable reduction.
- **Mutation vào danh sách nguồn đang được stream duyệt** có thể vi phạm yêu cầu non-interference, gây kết quả không đáng tin hoặc exception.
- **Mutation vào biến chia sẻ bên ngoài collector** có thể gây race khi chuyển sang parallel stream, đồng thời làm pipeline khó kiểm thử.

Ví dụ cần tránh:

§§§java
List<String> external = new ArrayList<>();
source.parallelStream().forEach(external::add);
§§§

Đây là **đoạn code minh họa không an toàn** nếu §source§ là collection, cần import §List§, §ArrayList§. Nhiều thread có thể gọi §ArrayList.add§ trên cùng đối tượng; §ArrayList§ không thread-safe. Hơn nữa thứ tự thêm vào external không nhất thiết phản ánh encounter order.

Thay bằng phép thu thập:

§§§java
List<String> collected = source.parallelStream()
        .collect(java.util.stream.Collectors.toList());
§§§

Với nguồn ordered và downstream phù hợp, kết quả tuân theo hợp đồng Collector/Stream mà không cần tự chia sẻ một ArrayList mutable. Collector có thể tạo nhiều vùng tích lũy riêng và dùng combiner để gộp khi xử lý song song.

**Điểm tinh tế:** accumulator có mutation không có nghĩa collector tự động mang đặc tính §CONCURRENT§. Mutate container riêng của một partition **khác** với hỗ trợ nhiều thread gọi accumulator **đồng thời trên cùng container**.

## 6. Cách hoạt động khi Stream xử lý song song

Trong trường hợp đơn giản, có thể tưởng tượng:

§§§text
                 Stream<T>
                 /       \
                /         \
          Partition 1   Partition 2
             |             |
          supplier()     supplier()
             |             |
          A(left)        A(right)
             |             |
        accumulator   accumulator
             \             /
              \           /
            combiner(left, right)
                     |
                     v
                A(merged)
                     |
                  finisher
                     |
                     v
                  Result R
§§§

Sơ đồ là **mô hình khái niệm**, không phải một cam kết về số lần supplier/combiner được gọi, số thread, hay cấu trúc phân mảnh cụ thể. Các chi tiết này do implementation và kế hoạch thực thi quyết định.

Hợp đồng quan trọng:

1. Supplier phải tạo container mới, độc lập, không vô tình trả lại một object singleton đã được dùng chung.
2. Accumulator ghi nhận chính xác phần tử vào container nhận được.
3. Combiner phải gộp đầy đủ nội dung của hai container để kết quả tương đương với cách xử lý toàn bộ dữ liệu.
4. Finisher biến vùng đã gộp thành đầu ra cuối cùng, nếu collector không có §IDENTITY_FINISH§.
5. Các hàm supplier/accumulator/combiner cần tuân thủ tính tương thích và các ràng buộc về associativity/identity mà Collector yêu cầu.

Không suy rằng §parallelStream()§ luôn nhanh hơn. Với tập dữ liệu nhỏ, chi phí tạo container, chia việc và gộp container có thể vượt lợi ích của song song.

## 7. Accumulator, combiner và finisher không thể thay vai trò cho nhau

### Accumulator: nhận từng phần tử

§§§java
(bucket, value) -> bucket.add(value)
§§§

Mỗi lời gọi chỉ xử lý **một phần tử T** và ghi nhận vào **một container A**.

### Combiner: gộp hai vùng A

§§§java
(left, right) -> {
    left.addAll(right);
    return left;
}
§§§

Nó không nhận một phần tử T riêng lẻ mà nhận **hai trạng thái tích lũy A**. Nếu combiner vô tình chỉ trả §left§ mà không đưa phần tử trong §right§ sang, quá trình thu song song có thể làm mất dữ liệu.

### Finisher: đổi A sang R

§§§java
bucket -> List.copyOf(bucket)
§§§

Nó hoạt động trên container đã tích lũy, biến thành kết quả có hợp đồng khác. Ví dụ một collector đếm và cộng sẽ có vùng mutable giữ §count§, §sum§ nhưng kết quả có thể là record immutable.

Phân biệt bằng bảng:

| Hàm | Nhận | Có nhiệm vụ |
| --- | --- | --- |
| §accumulator.accept(a, t)§ | container §a§ và phần tử §t§ | Cập nhật container với một phần tử |
| §combiner.apply(a1, a2)§ | hai container | Hợp nhất trạng thái |
| §finisher.apply(a)§ | container đã hoàn tất | Tạo đối tượng kết quả |

Ba vai trò tách biệt giúp cho một custom collector có thể thay thế chính xác quá trình thu dữ liệu theo vòng lặp mà vẫn hợp đồng được với Stream API.

## 8. Ví dụ Java 17+: accumulator thu thống kê count/sum

Một ví dụ cần collector riêng hơn là thu **số lượng, tổng và trung bình** trong một lần duyệt, bằng vùng tích lũy mutable và kết quả immutable.

Lưu §StatisticsAccumulatorDemo.java§:

§§§java
import java.util.List;
import java.util.stream.Collector;

public class StatisticsAccumulatorDemo {
    static final class MutableStats {
        long count;
        long sum;

        void accept(Integer value) {
            count++;
            sum += value;
        }

        MutableStats merge(MutableStats other) {
            count += other.count;
            sum += other.sum;
            return this;
        }

        Summary finish() {
            double average = count == 0
                    ? 0.0
                    : (double) sum / count;
            return new Summary(count, sum, average);
        }
    }

    record Summary(long count, long sum, double average) {}

    public static void main(String[] args) {
        Collector<Integer, MutableStats, Summary> statsCollector =
                Collector.of(
                        MutableStats::new,
                        MutableStats::accept,
                        MutableStats::merge,
                        MutableStats::finish
                );

        List<Integer> numbers = List.of(4, 6, 8);

        Summary sequential = numbers.stream()
                .collect(statsCollector);
        Summary parallel = numbers.parallelStream()
                .collect(statsCollector);
        Summary empty = List.<Integer>of().stream()
                .collect(statsCollector);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
§§§

Biên dịch/chạy Java 17:

§§§bash
javac StatisticsAccumulatorDemo.java
java StatisticsAccumulatorDemo
§§§

Output:

§§§text
sequential=Summary[count=3, sum=18, average=6.0]
parallel=Summary[count=3, sum=18, average=6.0]
empty=Summary[count=0, sum=0, average=0.0]
§§§

Giải thích cụ thể:

- Supplier tạo một §MutableStats(count=0, sum=0)§ cho vùng tạm.
- Accumulator §accept(Integer value)§ được gọi khi một phần tử đi vào vùng đó: tăng §count§ và cộng §value§ vào §sum§.
- Combiner §merge§ cộng count và sum của hai vùng tạm; nó trả lại vùng bên trái đã cập nhật.
- Finisher tạo record immutable §Summary(count, sum, average)§, tách biệt trạng thái mutable của collector.
- Với stream rỗng, supplier tạo trạng thái rỗng; finisher trả §Summary(0,0,0.0)§ theo chính sách minh họa của chương trình.

**Vấn đề số học:** phép cộng kiểu §long§ có thể tràn nếu dữ liệu vượt phạm vi; chương trình dùng tập số nhỏ để minh họa. Nếu ứng dụng cần tổng chính xác với số lượng cực lớn, cân nhắc §BigInteger`/§BigDecimal` và chính sách đầu vào. Trung bình bằng §double§ là quyết định về kiểu kết quả; nó không tự cho độ chính xác thập phân tuyệt đối. Các yếu tố này độc lập với cơ chế accumulator.

### Vì sao phép gộp thống kê đúng?

Hai vùng có trạng thái:

```text
left  = (count=c1, sum=s1)
right = (count=c2, sum=s2)
merged = (count=c1+c2, sum=s1+s2)
```

Với số học không tràn, các phép cộng bảo đảm kết quả gộp nhất quán bất kể chia thành các partition thế nào. Average chỉ tính **sau khi hợp nhất**, tránh việc lấy “trung bình của các trung bình” mà không xét số lượng phần tử mỗi nhóm.

Không dùng cách cộng average có sẵn của mỗi vùng rồi chia đôi nếu kích thước hai nhóm khác nhau: ví dụ nhóm 1 có một điểm 10, nhóm 2 có ba điểm 0; average thực là 2.5 chứ không phải 5.0.

## 9. Thực hiện cùng logic qua vòng lặp để hiểu accumulator

Phần cốt lõi của accumulator trong ví dụ thống kê tương đương việc cập nhật một vùng trong vòng lặp:

```java
MutableStats state = new MutableStats();
for (Integer n : numbers) {
    state.accept(n);
}
Summary result = state.finish();
```

Đây là đoạn code đặt trong class §StatisticsAccumulatorDemo` cùng các định nghĩa §MutableStats`, §Summary` ở trên.

Với cách viết imperative, ta tự điều khiển vòng lặp và lựa chọn vùng. Với §collect(statsCollector)§, Stream framework điều khiển quá trình gọi supplier/accumulator/combiner/finisher theo hợp đồng. Vì vậy accumulator nên chỉ mô tả **một bước cập nhật**, không phụ thuộc vào số lần duyệt, index vòng lặp hay số lượng thread.

**Đừng khai báo một accumulator có trạng thái toàn cục** như:

```java
// Phản ví dụ: không phù hợp để tái sử dụng song song
static long sharedTotal;
(bucket, n) -> sharedTotal += n;
```

Phần trên chỉ là pseudocode minh họa trong ngữ cảnh có biến static và một lambda cần target type, **không phải một class Java độc lập**. Nó bỏ qua container §bucket§ và cập nhật biến toàn cục; kết quả của collector không còn được xác định từ vùng tích lũy mà nó sở hữu, dễ gây race và sai kết quả khi gọi nhiều lần.

## 10. Collector.of() và lựa chọn IDENTITY_FINISH

Java có hai dạng factory đặc biệt hữu ích:

```java
Collector.of(supplier, accumulator, combiner)
Collector.of(supplier, accumulator, combiner, finisher)
```

Các biểu thức trên là **mô tả overload rút gọn**, không phải khai báo method đầy đủ.

- Dạng **ba thành phần** áp dụng khi kết quả đầu ra chính là vùng tích lũy §A§, đồng thời collector nhận đặc tính §IDENTITY_FINISH§ theo factory này.
- Dạng **bốn thành phần** dùng khi cần chuyển container §A§ thành kiểu hoặc dạng kết quả khác bằng finisher, ví dụ §MutableStats → Summary§, hay §ArrayList<String> → List<String>§ đã được sao chép.
- Cả hai có overload nhận thêm §Collector.Characteristics...§, nhưng **không khai báo đặc tính nếu collector không thật sự đáp ứng**.

Ví dụ collector ba thành phần:

```java
Collector<String, ?, List<String>> collector = Collector.of(
        java.util.ArrayList::new,
        (list, item) -> list.add(item),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

Đây là đoạn khai báo minh họa trong phương thức, cần import §Collector` và §List`; khi viết mã thật có thể làm rõ type arguments hoặc dùng lambda có kiểu tường minh nếu compiler không suy luận được như mong muốn.

Ở dạng này, kết quả là vùng tích lũy của collector, thường là một list mutable. Dùng dạng có finisher như §List::copyOf` nếu muốn kết quả unmodifiable nhưng đảm bảo **mọi phần tử khác null** (vì §List.copyOf` từ chối null). Không gắn §IDENTITY_FINISH§ cho collector dùng finisher tạo object khác hoặc tạo bản sao: framework được phép bỏ qua finisher khi đặc tính đó được khai báo, dẫn tới sai kiểu/hợp đồng.

## 11. Collector.Characteristics và an toàn luồng

Ba đặc tính thường thấy:

| Đặc tính | Ý nghĩa | Khi nào thận trọng |
| --- | --- | --- |
| §IDENTITY_FINISH§ | Có thể xem trạng thái tích lũy trực tiếp là kết quả mà không cần chuyển đổi | Không dùng nếu finisher tạo bản sao hoặc DTO |
| §UNORDERED§ | Collector không cam kết giữ encounter order trong kết quả | Không dùng nếu yêu cầu thứ tự list/chuỗi |
| §CONCURRENT§ | Accumulator có thể được gọi đồng thời từ nhiều thread trên **cùng container** | Không dùng với §ArrayList`, §StringBuilder` hoặc trạng thái mutable chưa đồng bộ |

Với các ví dụ trong bài:

- Collector dùng §ArrayList::new` và §List::copyOf` **không** có §IDENTITY_FINISH`.
- Collector tích lũy tên theo thứ tự nguồn không nên khai báo §UNORDERED§ nếu thứ tự tên là yêu cầu của API.
- Các accumulator thay đổi §ArrayList` hoặc §MutableStats` **không được gắn §CONCURRENT`** vì không được thiết kế để nhiều thread chỉnh sửa cùng đối tượng đồng thời.

Điểm rất quan trọng: **không khai báo §CONCURRENT` vẫn có thể dùng collector với parallel stream**. Framework quản lý container tách biệt cho các partition rồi hợp nhất qua combiner theo hợp đồng. Không cần thêm synchronized cho mỗi thao tác chỉ vì Stream có thể chạy parallel, nếu collector dùng kiểu non-concurrent đúng chuẩn và không chia sẻ container sai cách.

Đừng tự ép performance bằng cách bật §CONCURRENT`. Đặc tính phải phản ánh **hành vi được bảo đảm**, không phải “mẹo để chạy nhanh”.

## 12. Những lỗi phổ biến về accumulator

### 12.1. Không cập nhật container được truyền vào

Sai hướng:

```java
(list, value) -> {
    new ArrayList<String>().add(value);
}
```

Đây là đoạn minh họa trong ngữ cảnh cần §BiConsumer<ArrayList<String>,String>`. Nó thêm phần tử vào một list mới rồi bỏ list đó, **không thay đổi §list§**, nên kết quả thu thập mất dữ liệu.

Đúng:

```java
(list, value) -> list.add(value)
```

### 12.2. Cộng dồn vào biến ngoài thay vì container

Thao tác như §total[0] += n` với mảng chia sẻ bên ngoài accumulator khiến nhiều lần thu thập có thể ảnh hưởng nhau, đặc biệt khi xử lý parallel. Nên đưa trạng thái tổng vào vùng §A` và gộp các vùng bằng combiner.

### 12.3. Dùng combiner chỉ trả left mà bỏ right

Sai:

```java
(left, right) -> left
```

Nếu framework chia dữ liệu thành nhiều vùng, vùng bên phải bị bỏ qua. Điều này có thể “qua” thử nghiệm sequential nhưng sai ở parallel.

Đúng với list:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

### 12.4. Khai báo shared mutable supplier

Sai:

```java
ArrayList<String> shared = new ArrayList<>();
Supplier<ArrayList<String>> supplier = () -> shared;
```

Đây là đoạn mã trong một phương thức với import §ArrayList` và §Supplier`. Mỗi lần gọi supplier đều trả lại **cùng một** list, khiến trạng thái bị dùng chung giữa các collection hoặc partition. Đúng hơn là §ArrayList::new` để mỗi lần tạo một container mới.

### 12.5. Gắn CONCURRENT khi container không thread-safe

Nếu nhiều thread gọi §bucket.add(...)§ đồng thời vào cùng §ArrayList`, có thể mất phần tử, sai trạng thái hoặc lỗi. Đừng đánh dấu §CONCURRENT` cho accumulator dựa trên ArrayList/MutableStats như các ví dụ.

### 12.6. Dùng finisher không tương thích đặc tính

Ví dụ collector có §finisher = List::copyOf` không được khai báo §IDENTITY_FINISH`. Kết quả đầu ra là một list khác, không phải container bên trong. Sai đặc tính có thể khiến framework không gọi finisher như bạn tưởng.

### 12.7. Rely on execution details

Không ghi nghiệp vụ trong accumulator dưới giả định “mỗi phần tử chắc chắn đến đúng một thread”, “supplier luôn gọi một lần”, hay “combiner chắc chắn chạy trong sequential”. API đưa ra **hợp đồng kết quả**, không cam kết chi tiết kế hoạch chạy cụ thể.

## 13. Bài tập: tự viết accumulator thu danh sách email

Giả sử mỗi nhân viên có tên và email, cần một collector thu email chuẩn hóa (trim + lowercase), bỏ email blank và tạo một danh sách unmodifiable theo thứ tự nguồn.

Định nghĩa:

```java
record User(String name, String email) {}
```

Hãy tự trả lời trước khi xem lời giải:

1. Kiểu phần tử §T§ là gì?
2. Container §A§ hợp lý là gì?
3. Accumulator cần làm những bước nào khi nhận một §User§?
4. Combiner nối hai container thế nào?
5. Finisher nên trả gì và có được khai báo §IDENTITY_FINISH§ không?

### Lời giải tham khảo Java 17+ hoàn chỉnh

Tạo §EmailAccumulatorDemo.java§:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collector;

public class EmailAccumulatorDemo {
    record User(String name, String email) {}

    public static void main(String[] args) {
        List<User> users = List.of(
                new User("Lan", " Lan@Example.COM "),
                new User("An", " "),
                new User("Minh", "MINH@example.com")
        );

        Collector<User, ArrayList<String>, List<String>> emails =
                Collector.of(
                        ArrayList::new,
                        (acc, user) -> {
                            String email = user.email().trim()
                                    .toLowerCase(Locale.ROOT);
                            if (!email.isBlank()) {
                                acc.add(email);
                            }
                        },
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf
                );

        List<String> result = users.stream().collect(emails);

        System.out.println(result);
        System.out.println("count=" + result.size());
        System.out.println("users=" + users.size());
    }
}
```

Chạy:

```bash
javac EmailAccumulatorDemo.java
java EmailAccumulatorDemo
```

Output:

```text
[lan@example.com, minh@example.com]
count=2
users=3
```

Giải thích:

- §T = User§, §A = ArrayList<String>§ và §R = List<String>§.
- Accumulator nhận một §User§ và chuyển email thành chuỗi chuẩn hóa. Nếu chuỗi blank, không thêm phần tử nào vào list. Đây là một chính sách nghiệp vụ minh họa, không phải hành vi tự động của Collector.
- Combiner nối các danh sách email giữa các container mà không bỏ dữ liệu.
- Finisher tạo list không sửa được bằng §List.copyOf`, vì vậy **không dùng §IDENTITY_FINISH`**.
- Nguồn §users§ vẫn có ba bản ghi; collector chỉ thu hai email không blank.

Nếu đầu vào có §email == null`, dòng §user.email().trim()` sẽ ném §NullPointerException`. Trong ứng dụng thật cần nêu rõ chính sách: reject null, coi null như blank hay gắn nhãn. Không mặc định email null có nghĩa là chuỗi rỗng.

Đồng thời, chuẩn hóa địa chỉ email ngoài đời còn tùy quy tắc của domain và hệ thống; ví dụ chỉ nhằm minh họa accumulator, **không** phải một bộ chuẩn hóa email hoàn chỉnh.

## 14. Khi nào không cần Collector tùy chỉnh?

Nếu chỉ cần thu một list đã được biến đổi, nên ưu tiên các API sẵn có:

```java
List<String> result = names.stream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();
```

Đây là đoạn code trong phương thức có danh sách §names§; `String::toUpperCase` sử dụng locale mặc định khi không nhận tham số; với dữ liệu cần quy tắc locale xác định, dùng §name -> name.toUpperCase(Locale.ROOT)` thay vì method reference này.

Các collector có sẵn bao gồm:

- §Collectors.toList()§, §toSet()§, §toCollection(...)§.
- §Collectors.mapping(...)§, §filtering(...)§, §flatMapping(...)§ để biến đổi/filter trong nhóm hoặc collector con.
- §Collectors.groupingBy(...)§, §partitioningBy(...)§ để chia theo khóa/điều kiện.
- §Collectors.joining(...)§ để ghép CharSequence.
- §Collectors.summingInt(...)§, §summarizingInt(...)§, §counting()§, §reducing(...)§ cho nhiều phép tổng hợp.

Custom collector đáng cân nhắc khi cần một trạng thái tích lũy đặc thù, một lượt duyệt tổng hợp nhiều chỉ số, hoặc muốn đưa quy tắc tạo/gộp/hoàn tất dữ liệu vào một abstraction có thể kiểm thử riêng. **Đừng viết custom accumulator chỉ để thay thế một lời gọi thư viện đơn giản**.

Ngoài ra, nếu bài toán là cộng tổng một số, §reduce(identity, accumulator)§ có ngữ nghĩa khác với mutable reduction bằng §collect(...)§: ở dạng reduction bất biến, accumulator của reduce **trả về giá trị kết hợp mới**; còn BiConsumer của Collector **mutate vùng A và trả void**. Đừng lấy thói quen viết lambda của reduce áp nguyên vào Collector.

## 15. Quy tắc đọc và viết một accumulator đúng

Có thể dùng checklist sau mỗi khi thiết kế collector:

1. **T là gì?** Xác định phần tử Stream thực sự cung cấp cho accumulator, có thể sau §map/filter§.
2. **A chứa thông tin gì?** Chọn cấu trúc mutable tối thiểu đủ để xây kết quả cuối cùng.
3. **Supplier có tạo A mới mỗi lần không?** Không dùng singleton mutable chia sẻ.
4. **Accumulator có thực sự ghi nhận phần tử vào A không?** Không tạo object mới rồi vứt đi, không ghi sai biến ngoài.
5. **Combiner có gộp đủ hai vùng A không?** Kiểm tra đặc biệt với parallel stream.
6. **Phép gộp có kết hợp theo hợp đồng không?** Thử nhóm dữ liệu thành các partition khác nhau rồi so kết quả.
7. **Finisher có biến A thành R đúng không?** Nếu tạo bản sao/DTO, không gắn IDENTITY_FINISH.
8. **Có cần thứ tự encounter không?** Không khai báo UNORDERED nếu thứ tự list/chuỗi mang ý nghĩa.
9. **Có an toàn nếu gọi accumulator đồng thời trên cùng A không?** Nếu không, không gắn CONCURRENT.
10. **Có side effect ngoài collector không?** Ưu tiên để toàn bộ trạng thái do container A quản lý.
11. **Đầu vào rỗng và null được xử lý thế nào?** Supplier/finisher phải tạo được kết quả hợp đồng; null cần quy tắc cụ thể.
12. **Đã thử sequential và parallel chưa?** Chỉ dùng parallel nếu collector đáp ứng hợp đồng và hiệu năng đáng giá.

**Kết luận:** accumulator trong Collector là **BiConsumer<A,T> cập nhật vùng tích lũy A bằng từng phần tử T**. Nó không phải combiner, không phải finisher và không tự thay đổi nguồn dữ liệu. Khi hiểu rõ supplier tạo vùng mới, accumulator ghi dữ liệu, combiner hợp nhất vùng và finisher tạo kết quả, bạn sẽ thiết kế được Collector tùy chỉnh đúng đắn, dễ kiểm thử và có thể hoạt động với Stream tuần tự hoặc song song theo hợp đồng.

**Tham khảo:** Java SE 17 API §java.util.stream.Collector§, §Collector.of§, §java.util.stream.Stream.collect§, §java.util.function.BiConsumer§, §java.util.stream.Collectors§; phần đặc tả Collector về identity/associativity, Characteristics và phép thu thập mutable.