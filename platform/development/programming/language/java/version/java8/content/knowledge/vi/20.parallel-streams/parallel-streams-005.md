# Chi phí sorted, distinct, skip và limit trong Stream song song (Java 8)

Bốn thao tác **`sorted`**, **`distinct`**, **`skip`** và **`limit`** có vẻ đơn giản: sắp xếp, loại phần tử trùng, bỏ qua một đoạn đầu, lấy tối đa một số phần tử. Tuy nhiên, khi dùng **parallel Stream**, chúng có thể gây chi phí lớn vì phải **ghi nhớ trạng thái giữa các phần tử**, duy trì **thứ tự gặp (encounter order)** hoặc phối hợp nhiều tác vụ để biết chính xác phần tử nào thuộc kết quả.

Bài này giải thích **hành vi đúng theo hợp đồng Java Stream**, chi phí thường gặp, cách thay đổi thứ tự thao tác mà không vô tình đổi ý nghĩa dữ liệu, và cách đo hiệu năng. Các API đều có từ Java 8 và **vẫn được áp dụng trong Java hiện hành**. Không dùng API đã lỗi thời hay một đặc tính triển khai cụ thể làm bảo đảm chung cho mọi JDK.

## 1. Kiến thức nền: Stream song song không có nghĩa mọi bước đều song song rẻ

Một pipeline có dạng:

```text
source
  │
  ├─ filter / map        (thao tác trung gian không trạng thái)
  ├─ sorted              (có trạng thái)
  ├─ distinct            (có trạng thái)
  ├─ skip / limit        (có trạng thái; limit có thể dừng sớm)
  │
  └─ collect / count / forEach / ...   (terminal operation)
```

- **Intermediate operation** như `map`/`filter` trả về Stream mới; đa số được đánh giá *lazy*, tức chưa duyệt phần tử ngay lúc khai báo pipeline.
- **Terminal operation** như `collect` kích hoạt quá trình xử lý và trả về kết quả.
- **Stateless operation** (thường là `map`/`filter`) xử lý phần tử mà không phải nhớ những phần tử đã qua để biết kết quả hiện tại.
- **Stateful operation** cần thông tin ngoài phần tử hiện tại: `sorted` cần biết thứ tự toàn cục, `distinct` cần biết phần tử nào đã gặp, `skip`/`limit` cần quản lý vị trí hoặc số phần tử đã chọn.
- **Parallel Stream** cho phép framework phân chia dữ liệu để xử lý đồng thời; không cam kết luôn tạo nhiều luồng, luôn nhanh hơn hoặc mỗi thao tác đều tránh được chi phí đồng bộ/gộp kết quả.

Điểm quyết định thường là **encounter order**. Một nguồn như `List` có thứ tự gặp; các thao tác trên ordered stream phải giữ những bảo đảm liên quan đến thứ tự đó. Ví dụ:

```java
// Trong một phương thức có sẵn List<Integer> numbers.
List<Integer> page = numbers.parallelStream()
    .skip(100)
    .limit(20)
    .collect(Collectors.toList());
```

Nếu đầu vào là List có thứ tự, kết quả phải là **20 phần tử tiếp theo sau 100 phần tử đầu** (nếu nguồn còn đủ). Framework không được chọn tùy ý 20 phần tử chỉ vì chạy song song. Điều này có thể cần phối hợp đáng kể giữa các nhánh xử lý.

## 2. So sánh nhanh bốn thao tác

| Thao tác | Bản chất | Ý nghĩa trên ordered stream | Chi phí thường gặp |
| --- | --- | --- | --- |
| `sorted()` / `sorted(comparator)` | **Stateful** | Trả các phần tử theo thứ tự sắp xếp; `sorted` ổn định đối với ordered streams | Thường cần xử lý/sắp xếp toàn bộ phần tử đầu vào; bộ nhớ đệm và CPU lớn |
| `distinct()` | **Stateful** | Giữ phần tử xuất hiện **đầu tiên** trong mỗi nhóm bằng nhau theo `equals` | Cần theo dõi phần tử đã gặp; ordered parallel có thể phải đợi/gom dữ liệu để giữ tính ổn định |
| `skip(n)` | **Stateful** | Bỏ **đúng n phần tử đầu** theo encounter order hoặc toàn bộ nếu ít hơn n | Ordered parallel có thể đắt vì phải xác định tiền tố chính xác |
| `limit(n)` | **Short-circuiting stateful** | Chỉ lấy **n phần tử đầu**, hoặc ít hơn nếu stream kết thúc trước | Có thể dừng sớm nhưng ordered parallel vẫn phải xác định tiền tố; thao tác có trạng thái phía trước có thể cản dừng sớm |

**Lưu ý:** Bảng nói về xu hướng và các ràng buộc ngữ nghĩa, **không phải bảng độ phức tạp cứng do API bảo đảm**. Hiệu năng thực tế còn tùy nguồn `Spliterator`, mức độ có thứ tự, lượng dữ liệu, triển khai JDK, terminal operation và phần cứng.

Có thể hình dung:

```text
Các phần tử được chia vào nhiều nhánh:
       A        B        C        D
       │        │        │        │
      map      map      map      map    ← dễ phân công độc lập
       │        │        │        │
       └────────┼────────┼────────┘
                │
          sorted / distinct             ← có thể cần barrier/gộp
                │
            skip / limit                ← có thể cần biết vị trí toàn cục
                │
            kết quả cuối
```

Không phải mọi pipeline đều tạo một barrier ở đúng chỗ như hình minh họa; đây là **mô hình tư duy**, không phải sơ đồ bắt buộc về cách JDK thực thi.

## 3. sorted(): có thể phải chờ toàn bộ tập dữ liệu để biết thứ tự toàn cục

### 3.1. Ý nghĩa

`sorted()` dùng thứ tự tự nhiên; `sorted(comparator)` dùng `Comparator` được truyền vào. Với ordered streams, phép sắp xếp có tính **ổn định**: các phần tử được comparator đánh giá bằng nhau giữ thứ tự tương đối theo encounter order. Với unordered streams, tính ổn định không được bảo đảm.

Ví dụ:

```java
// Minh họa trong ngữ cảnh numbers là List<Integer>.
List<Integer> sorted = numbers.parallelStream()
    .sorted()
    .collect(Collectors.toList());
```

Kết quả bắt buộc là các số tăng dần theo thứ tự tự nhiên, dù pipeline chạy song song. Bộ so sánh phải nhất quán với điều kiện nghiệp vụ, không phụ thuộc vào state thay đổi trong quá trình sắp xếp.

### 3.2. Chi phí

- Để biết giá trị nào phải đứng trước, việc sắp xếp một tập dữ liệu hữu hạn thông thường cần xem xét **toàn bộ phần tử được đưa tới `sorted`**. Với thuật toán sắp xếp so sánh tổng quát, chi phí CPU thường ở bậc `O(n log n)`; không coi con số đó là cam kết chính xác của Java API.
- Việc sắp xếp thường cần **buffer đáng kể** (thường tỷ lệ theo số phần tử), gây áp lực bộ nhớ và GC. Parallel sort còn có chi phí chia việc, đồng bộ và gộp các phần đã sắp.
- `sorted().limit(k)` **không bảo đảm** chỉ cần nhìn k phần tử đầu nguồn. Muốn biết k phần tử nhỏ nhất của **toàn bộ dữ liệu**, thường vẫn phải xét các phần tử ở phía sau.
- Với stream không kết thúc, một phép sắp xếp toàn cục trước khi giới hạn có thể không bao giờ tạo được kết quả; không dùng `sorted().limit(k)` với nguồn vô hạn mà không có giới hạn hữu hạn thích hợp **trước** `sorted`.
- Nếu phần tử không có thứ tự tự nhiên hợp lệ, `sorted()` có thể ném `ClassCastException`; comparator hoặc dữ liệu null không được xử lý phù hợp cũng có thể gây lỗi. Hãy xác định thứ tự và quy tắc null rõ ràng.

### 3.3. Chọn đúng nhu cầu

Nếu yêu cầu là "**k phần tử nhỏ nhất/lớn nhất toàn bộ nguồn**", `sorted().limit(k)` diễn tả đúng ngữ nghĩa nhưng có thể tốn bộ nhớ. Với bộ dữ liệu rất lớn và k nhỏ, có thể cân nhắc thuật toán **top-k dùng heap kích thước k** hoặc công cụ chuyên dụng, sau đó sắp chính k kết quả để hiển thị. Đây là một **thuật toán khác phải kiểm thử**, không phải bảo đảm rằng Stream tự động dùng heap top-k.

Nếu yêu cầu chỉ là "**sắp xếp k phần tử đầu nguồn**", đặt `limit(k).sorted()`. Nhưng **kết quả này khác** top-k toàn cục, vì các phần tử sau k vị trí đã bị loại trước khi sắp.

Nếu dữ liệu ban đầu đã có thứ tự phù hợp và hợp đồng cho phép, tránh sắp xếp lặp lại không cần thiết. Với số nguyên, cân nhắc primitive streams (`IntStream`, `LongStream`, `DoubleStream`) khi phù hợp, nhằm giảm boxing; vẫn phải đo hiệu năng thực tế.

## 4. distinct(): loại trùng nhưng có thể trả giá cho thứ tự

### 4.1. distinct khác với sorted

`distinct()` giữ mỗi giá trị **duy nhất theo `Object.equals`** đúng một lần, không bắt buộc sắp xếp. Trên ordered stream, `distinct` là phép loại trùng **ổn định**: giữ phần tử gặp đầu tiên của mỗi nhóm bằng nhau.

Ví dụ:

```text
Nguồn:                  [9, 3, 9, 1, 5, 3, 7]
distinct (ordered):      [9, 3, 1, 5, 7]
sorted:                  [1, 3, 3, 5, 7, 9, 9]
sorted + distinct:       [1, 3, 5, 7, 9]
```

Chú ý `distinct` **không** sử dụng comparator của `sorted` để quyết định giá trị trùng. Hai đối tượng chỉ được loại trùng khi chúng bằng nhau theo `equals`. Nếu bạn muốn "trùng theo một khóa nghiệp vụ" (ví dụ email không phân biệt hoa/thường), cần định nghĩa phép biến đổi hoặc quy tắc giữ bản ghi phù hợp; không coi `distinct` như `distinctByKey` có sẵn trong Java 8.

### 4.2. Chi phí của ordered parallel distinct

Để vừa loại trùng vừa giữ **phần tử đầu tiên theo encounter order**, kết quả của nhánh xử lý trước có thể quyết định liệu một phần tử ở nhánh sau phải được giữ hay bỏ. Vì vậy `distinct()` trên ordered parallel pipeline có thể yêu cầu **phối hợp nhiều nhánh, barrier và bộ đệm đáng kể**, như tài liệu Java Stream mô tả.

- Với dữ liệu có `n` phần tử và `u` giá trị khác nhau, cách loại trùng thường cần theo dõi tới `u` khóa/giá trị đã gặp; bộ nhớ có thể tăng mạnh khi gần như mọi phần tử đều duy nhất.
- Chất lượng `equals`/`hashCode` quan trọng; hai phương thức phải tuân thủ hợp đồng và đối tượng không được bị mutate khiến quan hệ bằng nhau/hash thay đổi giữa quá trình thu.
- Nếu không cần thứ tự phần tử được giữ, có thể dùng `unordered()` **khi đúng hợp đồng nghiệp vụ**; nhờ bỏ yêu cầu ổn định theo encounter order, framework có thêm không gian tối ưu hóa.
- Không mặc định `unordered().distinct()` nhanh hơn trong mọi dữ liệu; điều này cần đo.

### 4.3. Có thể dùng unordered() an toàn khi nào?

Nếu kết quả yêu cầu **tập hợp giá trị duy nhất**, không quan tâm thứ tự gặp hay "bản ghi đầu tiên" trong các bản ghi tương đương, một pipeline như sau có thể phù hợp:

```java
// Minh họa: words là List<String> đã được kiểm tra.
Set<String> unique = words.parallelStream()
    .unordered()
    .distinct()
    .collect(Collectors.toSet());
```

Nhưng nếu downstream còn `limit(5)` và người dùng muốn **năm giá trị duy nhất đầu tiên**, bỏ thứ tự có thể làm **thay đổi chính những phần tử được chọn**. Đừng tối ưu bằng `unordered()` khi điều kiện chọn phụ thuộc vào vị trí.

## 5. skip(n) và limit(n): chi phí nằm ở việc xác định lát cắt

### 5.1. skip(n)

Với ordered stream, `skip(n)` phải bỏ **đúng n phần tử đầu**, nếu có đủ; nếu nguồn ít hơn n phần tử thì kết quả rỗng. Trên parallel stream có thứ tự, việc xác định phần tử nào nằm trong **n vị trí đầu tiên** có thể tốn nhiều công sức phối hợp.

Ví dụ:

```text
Nguồn:                [A, B, C, D, E, F]
skip(2):              [C, D, E, F]
skip(2).limit(3):     [C, D, E]
```

**Không khẳng định `skip(n)` luôn phải đọc hoặc giữ toàn bộ n phần tử** trong mọi trường hợp. Với nguồn có kích thước và khả năng chia theo vị trí (ví dụ một số `Spliterator` báo `SIZED`/`SUBSIZED`), implementation có thể tối ưu đáng kể. Nhưng trên nguồn có thứ tự và khó phân chia theo vị trí, đặc biệt sau `filter`, `skip(n)` có thể đắt.

`skip(0)` không bỏ phần tử nào. `skip(-1)` ném `IllegalArgumentException`. Với dữ liệu phân trang sâu, việc bỏ qua rất nhiều phần tử mỗi lần truy vấn có thể kém hiệu quả; cân nhắc thiết kế nguồn có thể truy cập theo chỉ mục hoặc sử dụng cursor/keyset pagination ở tầng lưu trữ phù hợp, thay vì giả định Stream có thể nhảy tới vị trí tùy ý.

### 5.2. limit(n)

`limit(n)` là **short-circuiting stateful intermediate operation**: khi chỉ cần n kết quả, pipeline có thể ngừng duyệt sớm hơn so với việc xử lý toàn bộ nguồn.

Ví dụ:

```java
// Minh họa: orders là List<Order>, predicate đã có.
List<Order> firstPage = orders.stream()
    .filter(predicate)
    .limit(20)
    .collect(Collectors.toList());
```

Trên ordered stream, đó là **20 phần tử đầu tiên sau khi lọc**. Khi chạy song song, phải bảo toàn ý nghĩa "đầu tiên" này, nên có thể phát sinh chi phí phối hợp. Nếu phía trước có `sorted()`, chi phí sắp xếp toàn cục có thể ngăn tận dụng được phần lớn lợi thế dừng sớm. Với `distinct()` trên ordered parallel stream, vẫn phải giữ ràng buộc chọn phần tử đầu tiên khác nhau.

`limit(0)` cho stream rỗng. `limit(-1)` ném `IllegalArgumentException`. Nếu nguồn không có thứ tự và ứng dụng chấp nhận **bất kỳ n phần tử**, `unordered().limit(n)` có thể cho phép cách thực thi ít bị ràng buộc hơn, nhưng không được hứa tập phần tử nào sẽ được chọn.

### 5.3. Kết hợp skip và limit: thứ tự quan trọng

```java
// Minh họa: source là List<T> có thứ tự.
List<T> page = source.parallelStream()
    .skip(offset)
    .limit(pageSize)
    .collect(Collectors.toList());
```

Đây là **phân trang theo encounter order**. Với một nguồn đã lọc hoặc sắp, "trang" được tính **sau những phép đó**. Nếu bạn đổi vị trí `skip`/`limit` sang trước `filter` hoặc `sorted`, bạn có thể đang mô tả một câu hỏi hoàn toàn khác.

Công thức kết quả với nguồn hữu hạn có `m` phần tử, `skip(n)` và `limit(k)`, với `n,k ≥ 0`: tối đa `min(k, max(m - n, 0))` phần tử được trả về. Công thức chỉ mô tả **số lượng**; trên ordered stream, phần tử phải nằm đúng vị trí.

## 6. Ví dụ chạy được: thứ tự thao tác thay đổi cả kết quả

Ví dụ dưới đây dùng cùng một danh sách nguồn và **parallel Stream** để thấy rõ chi phí không thể tối ưu bằng cách hoán đổi thao tác tùy ý.

Tệp **`StreamCostsDemo.java`** (Java 8 trở lên):

```java
import java.util.*;
import java.util.stream.*;

public class StreamCostsDemo {
    public static void main(String[] args) {
        List<Integer> values =
            Arrays.asList(9, 3, 9, 1, 5, 3, 7, 2, 7, 4);

        List<Integer> unique = values.parallelStream()
            .distinct().collect(Collectors.toList());

        List<Integer> ascending = values.parallelStream()
            .sorted().collect(Collectors.toList());

        List<Integer> page = values.parallelStream()
            .sorted().distinct().skip(2).limit(3)
            .collect(Collectors.toList());

        List<Integer> limitThenSort = values.parallelStream()
            .limit(4).sorted().collect(Collectors.toList());

        List<Integer> sortThenLimit = values.parallelStream()
            .sorted().limit(4).collect(Collectors.toList());

        List<Integer> distinctThenLimit = values.parallelStream()
            .distinct().limit(4).collect(Collectors.toList());

        List<Integer> limitThenDistinct = values.parallelStream()
            .limit(4).distinct().collect(Collectors.toList());

        List<Integer> top3 = values.parallelStream()
            .sorted(Comparator.reverseOrder()).limit(3)
            .collect(Collectors.toList());

        List<Integer> top3Unique = values.parallelStream()
            .distinct().sorted(Comparator.reverseOrder()).limit(3)
            .collect(Collectors.toList());

        System.out.println("unique=" + unique);
        System.out.println("ascending=" + ascending);
        System.out.println("page=" + page);
        System.out.println("limitThenSort=" + limitThenSort);
        System.out.println("sortThenLimit=" + sortThenLimit);
        System.out.println("distinctThenLimit=" + distinctThenLimit);
        System.out.println("limitThenDistinct=" + limitThenDistinct);
        System.out.println("top3=" + top3);
        System.out.println("top3Unique=" + top3Unique);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 StreamCostsDemo.java
java StreamCostsDemo
```

Kết quả chính xác:

```text
unique=[9, 3, 1, 5, 7, 2, 4]
ascending=[1, 2, 3, 3, 4, 5, 7, 7, 9, 9]
page=[3, 4, 5]
limitThenSort=[1, 3, 9, 9]
sortThenLimit=[1, 2, 3, 3]
distinctThenLimit=[9, 3, 1, 5]
limitThenDistinct=[9, 3, 1]
top3=[9, 9, 7]
top3Unique=[9, 7, 5]
```

**Phân tích:**

1. `distinct()` bảo toàn giá trị gặp đầu tiên của mỗi nhóm bằng nhau trong nguồn `List` có thứ tự: `[9,3,1,5,7,2,4]`, không phải danh sách tăng dần.
2. `sorted()` sắp mọi phần tử, vẫn giữ bản ghi trùng.
3. `sorted().distinct().skip(2).limit(3)` tạo tập giá trị tăng dần `[1,2,3,4,5,7,9]`, bỏ hai phần tử đầu rồi lấy `[3,4,5]`.
4. `limit(4).sorted()` chỉ sắp **bốn phần tử đầu nguồn** `[9,3,9,1]`, trả `[1,3,9,9]`; `sorted().limit(4)` lấy **bốn phần tử nhỏ nhất trong toàn bộ nguồn**, trả `[1,2,3,3]`.
5. `distinct().limit(4)` lấy **bốn giá trị khác nhau đầu tiên**; `limit(4).distinct()` chỉ loại trùng **trong bốn phần tử đầu** và có thể trả ít hơn bốn phần tử.
6. `sorted(reverseOrder()).limit(3)` giữ phần tử trùng vì đây là **top 3 bản ghi**; `distinct().sorted(reverseOrder()).limit(3)` là **top 3 giá trị khác nhau**.

Tất cả các stream của chương trình đều được **tạo mới** bằng `values.parallelStream()`. Không tái sử dụng cùng một đối tượng `Stream` sau terminal operation vì Stream đã tiêu thụ không được dùng lại.

## 7. unordered(): giảm ràng buộc khi kết quả cho phép, không phải công tắc tăng tốc

`BaseStream.unordered()` yêu cầu pipeline bỏ yêu cầu về thứ tự gặp nếu đang có. Nó **không phải** lệnh "trộn ngẫu nhiên" và không bảo đảm kết quả thực sự bị đổi thứ tự. Mục đích là cho phép framework không cần duy trì một yêu cầu thứ tự vốn không quan trọng với ứng dụng.

Bỏ thứ tự có thể giúp các stateful operation đặc biệt như `distinct`, `skip`, `limit` trên parallel Stream, **nhưng chỉ khi việc thay đổi phần tử được chọn hoặc thứ tự hiển thị không làm sai nghiệp vụ**.

Tệp **`UnorderedSafetyDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class UnorderedSafetyDemo {
    public static void main(String[] args) {
        List<String> words =
            Arrays.asList("b", "a", "b", "c", "a", "d", "e", "c");

        List<String> orderedDistinct = words.parallelStream()
            .distinct().collect(Collectors.toList());

        Set<String> left = words.parallelStream()
            .distinct().collect(Collectors.toSet());

        Set<String> right = words.parallelStream()
            .unordered().distinct().collect(Collectors.toSet());

        long limitedCount = IntStream.range(0, 1000)
            .parallel().unordered().limit(10).count();

        long skippedCount = IntStream.range(0, 1000)
            .parallel().unordered().skip(10).count();

        System.out.println("orderedDistinct=" + orderedDistinct);
        System.out.println("sameUniqueSet=" + left.equals(right));
        System.out.println("unorderedLimitedCount=" + limitedCount);
        System.out.println("unorderedSkippedCount=" + skippedCount);
    }
}
```

```bash
javac -encoding UTF-8 UnorderedSafetyDemo.java
java UnorderedSafetyDemo
```

```text
orderedDistinct=[b, a, c, d, e]
sameUniqueSet=true
unorderedLimitedCount=10
unorderedSkippedCount=990
```

Vì sao chỉ in số lượng ở hai phép cuối? Với unordered stream, `limit(10)` có thể chọn **bất kỳ mười phần tử nào**, và `skip(10)` có thể bỏ **bất kỳ mười phần tử nào**. Với `IntStream.range(0,1000)` có 1.000 phần tử phân biệt, số lượng còn lại tương ứng là 10 và 990; **không có cam kết cụ thể về danh tính** mười phần tử được chọn/bỏ. Một test giả định kết quả `[0,1,...,9]` sau `unordered().limit(10)` là sai về hợp đồng.

Trái lại, kết quả `orderedDistinct` bảo toàn phần tử xuất hiện đầu tiên theo thứ tự `List`, nên có kết quả xác định. So sánh hai tập `left` và `right` bằng `Set.equals` là phù hợp khi yêu cầu chỉ là **tập các chuỗi duy nhất**, không phải thứ tự.

**Không sử dụng `unordered()`** cho việc chọn trang dựa trên vị trí, top-k theo thứ tự nghiệp vụ, hoặc lấy "n bản ghi đầu". Kể cả khi lần chạy thử vẫn trả đúng thứ tự, không được biến một hiện tượng triển khai thành cam kết API.

## 8. Test giữ nguyên lát cắt khi chạy song song có thứ tự

Với nguồn `List` có encounter order, `parallelStream().skip(n).limit(k)` phải giữ **cùng lát cắt** với `stream().skip(n).limit(k)` khi nguồn và pipeline tương đương, không có side effect.

Tệp độc lập **`OrderedSliceDemo.java`**:

```java
import java.util.*;
import java.util.stream.*;

public class OrderedSliceDemo {
    public static void main(String[] args) {
        List<Integer> values = IntStream.rangeClosed(1, 10)
            .boxed().collect(Collectors.toList());

        List<Integer> sequential = values.stream()
            .skip(3).limit(4).collect(Collectors.toList());

        List<Integer> parallel = values.parallelStream()
            .skip(3).limit(4).collect(Collectors.toList());

        if (!sequential.equals(parallel)) {
            throw new AssertionError("ordered parallel slice differs");
        }

        System.out.println("sequentialSlice=" + sequential);
        System.out.println("parallelSlice=" + parallel);
        System.out.println("same=" + sequential.equals(parallel));
    }
}
```

```bash
javac -encoding UTF-8 OrderedSliceDemo.java
java OrderedSliceDemo
```

```text
sequentialSlice=[4, 5, 6, 7]
parallelSlice=[4, 5, 6, 7]
same=true
```

Điều này kiểm tra **tính đúng**, không cho biết pipeline song song rẻ hay đắt. Với chỉ mười phần tử, parallel thường không có lợi; không nên đưa `parallelStream()` vào code chỉ vì nó tồn tại.

## 9. Đặt thao tác ở đâu để giảm chi phí mà không đổi nghĩa?

Chi phí của stateful operations phụ thuộc lớn vào **lượng dữ liệu phải đi qua chúng**. Tuy nhiên, không phải mọi phép đổi chỗ đều bảo toàn kết quả.

### 9.1. filter sớm nếu điều kiện độc lập và đúng nghiệp vụ

```java
// Minh họa, không phải chương trình độc lập; values/predicate đã tồn tại.
List<Integer> filteredSorted = values.stream()
    .filter(predicate)
    .sorted()
    .collect(Collectors.toList());
```

Nếu chỉ cần sắp các giá trị thỏa predicate, lọc trước có thể giảm kích thước tập phải sắp. Nhưng:

```java
// KHÁC Ý NGHĨA nếu filter có thể loại phần tử trong top-k:
values.stream().sorted().limit(10).filter(predicate);
values.stream().filter(predicate).sorted().limit(10);
```

Dòng đầu là "lọc trong mười phần tử nhỏ nhất của toàn nguồn"; dòng sau là "mười phần tử nhỏ nhất **đạt điều kiện**". Đừng đổi chỉ vì mong nhanh hơn.

### 9.2. distinct trước sorted khi đúng phép toán giá trị

Với dữ liệu như các `Integer` trong ví dụ, nếu chỉ cần **các giá trị khác nhau sắp tăng**, có thể dùng:

```java
// Giữ các giá trị duy nhất trước khi sắp.
values.stream().distinct().sorted().collect(Collectors.toList());
```

Nếu số phần tử trùng nhiều, lượng phần tử đưa tới `sorted` có thể giảm. Tuy nhiên `distinct` vẫn cần bộ nhớ để xác định phần tử trùng, còn `sorted` vẫn có chi phí trên phần tử còn lại; cần đo trong dữ liệu thực.

Với đối tượng phức tạp, `distinct` dựa trên `equals` còn `sorted(comparator)` dựa trên Comparator. Khi comparator không nhất quán với `equals` hoặc logic giữ phần tử đại diện phụ thuộc thứ tự, không đánh đồng hai thao tác hoặc tùy ý hoán đổi mà không kiểm thử kết quả.

### 9.3. Không hoán đổi limit và sorted nếu cần top-k toàn cục

| Câu hỏi nghiệp vụ | Pipeline đúng ý nghĩa |
| --- | --- |
| "Cho tôi 10 số nhỏ nhất **trong toàn bộ dữ liệu**." | `sorted().limit(10)` |
| "Lấy 10 số đầu nguồn, rồi sắp xếp chúng." | `limit(10).sorted()` |
| "Lấy 10 **giá trị phân biệt** lớn nhất." | `distinct().sorted(reverseOrder()).limit(10)` |
| "Lấy 10 bản ghi có giá trị cao nhất, **cho phép trùng**." | `sorted(reverseOrder()).limit(10)` |
| "Lấy trang thứ p sau khi sort toàn nguồn." | `sorted().skip(offset).limit(pageSize)` |
| "Lấy p phần tử sau offset theo thứ tự đầu vào." | `skip(offset).limit(p)` trên ordered stream |

Một tối ưu đáng tin phải **giữ nguyên lời mô tả nghiệp vụ ở cột bên trái**. Chỉ so sánh số lượng kết quả không đủ: hai pipeline đều cho 10 phần tử nhưng là **10 phần tử khác nhau**.

### 9.4. Có thể bỏ sorted không?

Chỉ khi upstream **đã đáp ứng đúng** thứ tự cần thiết và điều kiện đó được bảo đảm qua biến đổi. Ví dụ nguồn danh sách đã tăng dần, sau `filter` thuần không thay đổi thứ tự và `limit` lấy tiền tố thì không cần `sorted` thêm. Nhưng sau một phép `map` làm thay đổi giá trị sắp xếp, không thể mặc định kết quả vẫn có thứ tự theo tiêu chí mới.

Không dùng `unordered()` sau `sorted()` nếu bước tiếp theo cần giữ "phần tử đầu tiên theo thứ tự đã sort"; như vậy tự bỏ cam kết mà bạn vừa tốn chi phí tạo ra.

## 10. Chi phí tương đối theo hình dạng dữ liệu

Gọi:

- `n` = số phần tử tới một stateful operation.
- `u` = số giá trị khác nhau sau khi xét `equals`.
- `k` = số phần tử mong muốn từ `limit(k)`.
- `s` = số phần tử cần bỏ qua từ `skip(s)`.

| Tình huống | Điểm có thể trở thành nút thắt | Lựa chọn cần đánh giá |
| --- | --- | --- |
| `n` lớn, mọi giá trị gần như khác nhau | `distinct` phải theo dõi nhiều giá trị | Có thật sự cần loại trùng? Đảm bảo dữ liệu đầu vào duy nhất ở nguồn nếu phù hợp |
| `n` lớn, chỉ `u` giá trị khác nhau | `distinct` tốn trạng thái nhưng có thể giảm kích thước đầu vào cho sort | Cân nhắc `distinct` trước `sorted` khi không đổi nghĩa |
| `sorted().limit(k)` với `k << n` | Sắp xếp toàn nguồn cho một kết quả nhỏ | Thuật toán top-k riêng hoặc tối ưu ở cơ sở dữ liệu |
| `skip(s)` rất lớn | Bỏ nhiều phần tử, nhất là ordered parallel | Nguồn có chỉ mục, seek/cursor, hoặc phân trang từ tầng dữ liệu |
| `limit(k)` nhỏ, upstream không có barrier | Có khả năng short-circuit sớm | Đặt `limit` ở vị trí hợp lệ mà không đổi ngữ nghĩa |
| Ordered parallel `distinct` | Phối hợp để giữ phần tử xuất hiện đầu tiên | Chỉ dùng `unordered` nếu hợp đồng không cần thứ tự/đại diện đầu |
| Ordered parallel `skip/limit` | Phối hợp để xác định đúng tiền tố | So sánh với stream tuần tự, giữ ý nghĩa trước khi tối ưu |
| Dữ liệu rất nhỏ hoặc mapper nhẹ | Scheduling/merging có thể lớn hơn phần tính toán | Bắt đầu với tuần tự, đo trước khi dùng parallel |
| Nguồn không phân chia tốt | Các nhánh không cân bằng hoặc quá nhiều phối hợp | Xem `Spliterator` và đặc tính nguồn |

**Quan trọng:** `O(n log n)`, `O(u)` hoặc "barrier" là mô hình để suy nghĩ về chi phí điển hình, không thay thế profiling. Ví dụ `skip` trên nguồn có khả năng tách theo chỉ số có thể được tối ưu tốt hơn nhiều so với bỏ lần lượt từng phần tử; trái lại `filter` phía trước có thể khiến vị trí kết quả không còn tính nhanh từ chỉ số nguồn. Chi tiết này thay đổi hiệu năng mà **không thay đổi ngữ nghĩa**.

## 11. Khi nào nên dùng parallelStream()?

Một quyết định hợp lý cần xét đồng thời:

1. **Khối lượng và chi phí xử lý từng phần tử:** mapper/filter tốn CPU thuần và dữ liệu đủ lớn thường là ứng viên tốt hơn mapper cực rẻ.
2. **Cấu trúc nguồn:** mảng, `ArrayList` và `IntStream.range` thường dễ phân chia hơn các nguồn có cấu trúc khó chia; đặc tính `Spliterator` ảnh hưởng cách framework vận hành.
3. **Tỷ lệ thao tác stateful:** nhiều `sorted`/`distinct`/`skip`/`limit` có thể làm phần gộp hoặc đồng bộ lấn át lợi ích xử lý song song.
4. **Bảo toàn encounter order:** nếu cần "đầu tiên", phân trang, thứ tự hiển thị chính xác, ràng buộc này có thể quan trọng hơn độ nhanh.
5. **Tính thuần của hàm:** predicate/mapper/comparator nên **không gây side effect** làm phụ thuộc thứ tự hoặc chia sẻ state không đồng bộ.
6. **Tài nguyên hệ thống:** parallel Stream có thể dùng tài nguyên xử lý chung với tác vụ khác; tăng tải CPU/băng thông bộ nhớ hoặc GC có thể làm hệ thống phục vụ yêu cầu chậm hơn.
7. **Kết quả đo với dữ liệu đại diện:** đo throughput/latency và allocation ở trường hợp thực sự được triển khai, không đánh giá từ ví dụ mười phần tử.

Parallel phù hợp với một số workload, **không phải lựa chọn mặc định**. Đôi khi `stream().filter(...).limit(...)` tuần tự rõ ràng và nhanh hơn một pipeline song song có nhiều stateful stages.

## 12. Đo hiệu năng đúng: đo chi phí, không đo cảm giác

Để trả lời "`distinct` trên ordered parallel pipeline có đắt không?" hoặc "đổi sang `unordered()` có lợi gì?", hãy làm thí nghiệm kiểm soát:

- **Cùng nguồn và cùng đầu ra hợp lệ:** so sánh `stream()` và `parallelStream()` trên tập dữ liệu tương đương; so sánh cả tập kết quả, không chỉ thời gian.
- **Thay kích thước:** thử n nhỏ, trung bình và lớn; tách trường hợp k rất nhỏ so với n và k gần n.
- **Thay phân phối:** dữ liệu duy nhất gần như hoàn toàn so với dữ liệu lặp nhiều; dữ liệu đã sắp so với đảo thứ tự; thay offset của `skip`.
- **Thay thứ tự và loại nguồn:** `ArrayList`, mảng, primitive range và nguồn có khả năng phân chia khác nhau có thể cho hiệu năng khác.
- **Quan sát thời gian, memory và GC:** `sorted`/`distinct` có thể tăng allocation hoặc peak memory; chỉ đo tổng milliseconds có thể che rủi ro bộ nhớ.
- **Warm-up, nhiều fork và cấu hình ổn định:** JIT, GC, CPU contention ảnh hưởng phép đo. Dùng framework benchmark Java như **JMH** cho microbenchmark nghiêm túc; tránh quyết định tối ưu dựa trên một lần `System.nanoTime()`.
- **Tránh đo pipeline bị tối ưu bỏ:** nếu chỉ gọi `count()` trên nguồn có kích thước biết trước, JDK có thể suy ra kết quả mà không cần chạy một số thao tác trung gian. Không dùng `peek` có side effect để kết luận mọi phần tử đã được xử lý. Hãy tiêu thụ kết quả theo cách giữ phép tính cần đánh giá và bảo đảm benchmark không bị dead-code elimination.
- **Đo trên môi trường thật:** số lõi, mức đồng thời và workload chung quyết định lợi ích. Không diễn giải máy phát triển rảnh rỗi thành kết quả chắc chắn trên service chịu tải.

**Không đưa con số "nhanh hơn x lần" khi chưa có phép đo.** Bài này cung cấp các yếu tố chi phí và code xác minh ngữ nghĩa; nó không tuyên bố kết quả benchmark chung cho mọi JDK hoặc nguồn dữ liệu.

## 13. Các lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao nguy hiểm? | Cách làm đúng |
| --- | --- | --- |
| Thêm `parallelStream()` để "luôn nhanh hơn" | Phí chia/gộp, barrier, phối hợp thứ tự | Đo tuần tự và song song trên dữ liệu thật |
| Dùng `sorted().limit(k)` rồi nghĩ chỉ sắp k phần tử | Sort toàn cục có thể cần toàn bộ đầu vào | Nếu chỉ sort tiền tố, dùng `limit(k).sorted()`; nếu cần top-k, giữ semantics hoặc thuật toán riêng |
| Đổi `sorted().limit(k)` thành `limit(k).sorted()` không kiểm tra | Thay top-k toàn cục bằng sắp tiền tố | Viết lại yêu cầu nghiệp vụ trước khi thay |
| Dùng `distinct()` để sắp xếp | `distinct` chỉ loại trùng | Thêm `sorted` khi cần thứ tự |
| Dùng `distinct()` với đối tượng có `equals/hashCode` sai | Bỏ hoặc giữ phần tử không đúng | Định nghĩa hợp đồng equality ổn định |
| Cho rằng `distinct` dựa trên comparator | Comparator không quyết định trùng lặp | Dùng `equals` hoặc thiết kế distinct theo khóa rõ ràng |
| Thêm `unordered()` trước `limit` khi cần "n đầu tiên" | Có thể chọn tập phần tử khác | Giữ ordered pipeline |
| Dùng `unordered()` sau `sorted()` rồi lấy trang | Mất bảo đảm tiền tố theo thứ tự sort | Không bỏ thứ tự nếu trang phụ thuộc vị trí |
| Bỏ `filter` ra sau `limit` để hy vọng giảm việc | Có thể không lấy đủ k phần tử hợp lệ | `filter(...).limit(k)` nếu cần k bản ghi đạt |
| Dùng `skip` offset rất lớn lặp lại nhiều lần | Tốn công truy cập lại tiền tố | Phân trang theo chỉ mục/cursor ở nguồn khi phù hợp |
| Giả định thứ tự duyệt của `Collectors.toSet()` | Set không cam kết thứ tự hiển thị | Dùng collection có thứ tự theo hợp đồng, hoặc sort trước khi xuất |
| Đo bằng `count()` cộng `peek` có side effect | Runtime có thể bỏ các bước không cần để tính count | Test kết quả thực và dùng benchmark hợp lệ |
| Sửa list/map bên ngoài qua `parallelStream().forEach` | Race, thứ tự không xác định | Tích lũy bằng collector phù hợp hoặc cấu trúc đồng thời đúng yêu cầu |

## 14. Bài tập thực hành

**Bài 1 — Hai câu hỏi khác nhau.** Với nguồn `[8, 1, 7, 2, 6, 3]`, hãy xác định kết quả:

```java
// Đoạn minh họa: numbers chứa danh sách ở trên.
numbers.stream().sorted().limit(3).collect(Collectors.toList());
numbers.stream().limit(3).sorted().collect(Collectors.toList());
```

**Đáp án:** Dòng đầu `[1,2,3]` (ba giá trị nhỏ nhất toàn bộ dữ liệu); dòng sau `[1,7,8]` (sắp ba phần tử đầu). Một phép đổi chỗ làm đổi nghiệp vụ.

**Bài 2 — Giữ n giá trị khác nhau đầu tiên.** Có danh sách `[A,A,B,C,B,D,E]`. So sánh `distinct().limit(3)` với `limit(3).distinct()`.

**Đáp án:** `distinct().limit(3)` → `[A,B,C]`; `limit(3).distinct()` → `[A,B]`. Dòng sau có thể trả ít hơn ba giá trị.

**Bài 3 — Khi nào bỏ thứ tự?** Báo cáo chỉ cần **số lượng mã duy nhất** trong tập dữ liệu, không cần đại diện đầu tiên hoặc thứ tự.

**Gợi ý:** `parallelStream().unordered().distinct().count()` có thể là phương án hợp lệ về mặt nội dung, nhưng phải so sánh hiệu năng với bản tuần tự, không tự kết luận nhanh hơn.

**Bài 4 — Phân trang một tập đã sắp.** Muốn trang chứa các bản ghi ở vị trí 41–60 (đếm từ 1) sau khi sắp theo điểm tăng dần.

**Gợi ý:** `sorted(comparator).skip(40).limit(20)`. Nếu muốn chỉ lấy 20 bản ghi bất kỳ, đây là bài toán khác và có thể không cần sort.

**Bài 5 — Cần số liệu benchmark gì?** So sánh `ordered parallel distinct` và `unordered parallel distinct` khi nguồn có một triệu phần tử, 100 giá trị khác nhau.

**Đáp án định hướng:** kiểm tra hai kết quả bằng tập giá trị, đo nhiều lần và nhiều kích thước nguồn, phân phối trùng lặp, allocation, peak memory, GC, số lõi, throughput; không chỉ so một lần wall clock. Nếu downstream còn `limit`/`skip` và cần chọn đúng phần tử đầu tiên, **không được bỏ order** để benchmark như hai thuật toán tương đương.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao `sorted()` có thể làm `limit(k)` phía sau không dừng sớm như kỳ vọng?**  
Vì `sorted` cần xác lập thứ tự toàn cục từ các phần tử upstream. Kết quả top-k không thể suy ra chỉ bằng việc nhìn k phần tử đầu bất kỳ.

**2. `distinct()` trên ordered parallel Stream giữ phần tử nào trong các giá trị bằng nhau?**  
Phần tử gặp đầu tiên theo encounter order. Bảo đảm ổn định này góp phần gây chi phí phối hợp và bộ đệm.

**3. `unordered()` có đảo ngẫu nhiên Stream không?**  
Không. Nó **bỏ ràng buộc thứ tự**, không cam kết xáo trộn. Kết quả có thể vô tình giống bản ordered ở một lần chạy.

**4. `skip(100).limit(20)` có nghĩa gì trên List?**  
Bỏ 100 phần tử đầu theo thứ tự gặp, sau đó lấy tối đa 20 phần tử tiếp theo. Trên ordered parallel Stream, ý nghĩa vị trí vẫn phải được bảo toàn.

**5. Vì sao `limit(10).sorted()` thường không phải top-10 nhỏ nhất toàn bộ nguồn?**  
Vì chỉ mười phần tử **đầu nguồn** được đưa tới sorted; các phần tử nhỏ hơn ở phía sau không được xét.

**6. `distinct().sorted()` có luôn giống `sorted().distinct()` không?**  
Không nên khẳng định vô điều kiện với mọi kiểu đối tượng/comparator và yêu cầu giữ đại diện. Với tập `Integer` và thứ tự tự nhiên trong bài, chúng có thể cho cùng dãy số duy nhất đã sắp; nhưng khi `equals` và Comparator có ý nghĩa khác nhau, cần đánh giá hợp đồng nghiệp vụ.

**7. Có được dùng `unordered().limit(10)` rồi báo đó là "10 bản ghi đầu tiên" không?**  
Không. Với unordered stream, danh tính phần tử được chọn không có cam kết như tiền tố của nguồn có thứ tự.

**8. Tại sao chạy parallel Stream nhanh với `map` không chứng minh `sorted().distinct().skip().limit()` cũng nhanh?**  
Vì `map` thường xử lý độc lập từng phần tử; bốn thao tác còn lại có trạng thái, có thể cần nhìn nhiều phần tử hoặc phối hợp về thứ tự trước khi xuất kết quả.

## Tài liệu tham khảo chính thức

- [Java SE 8 — Stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html): `sorted`, `distinct`, `skip`, `limit`; ghi chú đặc biệt về **ordered parallel pipelines**, trạng thái, bộ đệm và việc dùng `unordered()`.
- [Java SE 8 — java.util.stream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html): laziness, stateless/stateful operations, encounter order, parallelism và giảm mutable state.
- [Java SE 8 — BaseStream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/BaseStream.html): `parallel`, `sequential`, `unordered` và cách xem tính song song của pipeline.
- [Java SE 8 — Spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html): `ORDERED`, `SIZED`, `SUBSIZED` và các đặc tính của nguồn giúp thực hiện chia dữ liệu.
- [Java SE 8 — Collectors](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collectors.html): thu kết quả sau pipeline và hợp đồng của các collection.

**Ghi nhớ:** `sorted` và `distinct` cần trạng thái toàn cục hoặc phối hợp; `skip`/`limit` trên ordered parallel Stream phải tôn trọng tiền tố chính xác. Hãy **giữ đúng ngữ nghĩa trước, tối ưu sau**: lọc sớm khi phù hợp, chỉ bỏ thứ tự khi được phép, đo trên dữ liệu đại diện và dùng cấu trúc/thuật toán khác nếu thực sự cần phân trang sâu hoặc top-k lớn.