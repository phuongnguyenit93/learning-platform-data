# Các bước có thể được phối hợp trong một lần duyệt trong Java Stream

## 1. Điều đang xảy ra phía sau một pipeline Stream

Với Java Stream API, ta có thể viết liên tiếp nhiều thao tác trung gian (*intermediate operations*) như `filter()`, `map()`, `peek()` và một thao tác kết thúc (*terminal operation*) như `toList()`, `findFirst()` hoặc `sum()`:

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

Đoạn trên là minh họa trong phương thức có `numbers` là một `List<Integer>` và import `java.util.List`. Đọc theo nghĩa nghiệp vụ: giữ số chẵn, nhân lên 10, thu kết quả.

Điều dễ nhầm là tưởng Java **luôn** làm lần lượt:

1. Duyệt hết `numbers` và tạo một danh sách chứa mọi số chẵn.
2. Duyệt hết danh sách đó và tạo một danh sách chứa mọi số đã nhân 10.
3. Duyệt danh sách thứ hai để đưa vào kết quả.

Với những thao tác trung gian **không lưu trạng thái** (*stateless*) như `filter` và `map`, mô hình xử lý tuần tự thường là **theo từng phần tử xuyên qua nhiều bước** (*vertical processing*, còn gọi là pipeline fusion):

~~~text
Nguồn          filter(chẵn)           map(*10)           terminal toList
  1 ─────────► loại
  2 ─────────► giữ ────────────────► 20 ────────────────► ghi 20
  3 ─────────► loại
  4 ─────────► giữ ────────────────► 40 ────────────────► ghi 40
  5 ─────────► loại
~~~

Ở cách hình dung này, từng phần tử đi qua chuỗi xử lý trước khi phần tử tiếp theo được yêu cầu, thay vì nhất thiết tạo collection trung gian sau **mỗi** phương thức trong pipeline.

**Ý nghĩa của bài:** Các thao tác trung gian có thể được **phối hợp trong một lần traversal nguồn**. Nhưng không nên hiểu thành một bảo đảm máy móc rằng *mọi* pipeline luôn là một vòng lặp đơn giản, không dùng bộ đệm, không phải duyệt lại dữ liệu ở bất cứ đâu, hoặc phải gọi mọi callback đúng một lần.

## 2. Ba thành phần: nguồn, thao tác trung gian và thao tác kết thúc

Pipeline Stream thường gồm:

| Phần | Ví dụ | Vai trò |
|---|---|---|
| **Nguồn** (*source*) | `list.stream()`, `Arrays.stream(...)`, `IntStream.range(...)` | Cung cấp dãy phần tử để duyệt |
| **Intermediate operation** | `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit` | Thiết lập bước xử lý mới, thường chưa duyệt nguồn ngay |
| **Terminal operation** | `toList`, `collect`, `sum`, `anyMatch`, `findFirst`, `forEach` | Kích hoạt tiêu thụ pipeline và tạo kết quả/side effect |

Ví dụ:

~~~java
Stream<String> pipeline = names.stream()    // Nguồn.
        .filter(s -> !s.isBlank())           // Trung gian.
        .map(String::strip);                // Trung gian.

List<String> cleaned = pipeline.toList();    // Kết thúc.
~~~

Đây là đoạn minh họa với `names` và các import `List`/`Stream`. Lời gọi `filter` và `map` dựng các bước xử lý; pipeline chỉ bắt đầu thực thi khi `toList()` tiêu thụ nó.

**Laziness** ở đây có nghĩa việc đánh giá các thao tác trung gian được trì hoãn tới lúc cần. Nó giúp:

- Tránh tạo các kết quả trung gian không cần dùng.
- Có thể dừng sớm khi thao tác kết thúc đã đủ dữ liệu.
- Phối hợp các bước xử lý mà không phải tự viết nhiều vòng lặp riêng.
- Cho phép thư viện thực hiện một số tối ưu hóa khi tính đúng đắn của kết quả được bảo toàn.

Tuy nhiên, Stream không tự cache kết quả sau terminal operation, và một đối tượng stream đã tiêu thụ **không được tái sử dụng**.

## 3. Chương trình Java 17: quan sát từng phần tử đi xuyên qua pipeline

Lưu thành file **`PipelineFusionDemo.java`**:

~~~java
import java.util.List;

public class PipelineFusionDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);

        System.out.println("pipeline constructed");

        List<Integer> result = numbers.stream()
                .filter(n -> {
                    System.out.println("filter:" + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    System.out.println("map:" + n);
                    return n * 10;
                })
                .limit(2)
                .toList();

        System.out.println("result=" + result);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac PipelineFusionDemo.java
java PipelineFusionDemo
~~~

Kết quả stdout trong pipeline tuần tự dùng nguồn `List.of(1,2,3,4,5)`:

~~~text
pipeline constructed
filter:1
filter:2
map:2
filter:3
filter:4
map:4
result=[20, 40]
~~~

**Giải thích đúng thứ tự:**

1. Dòng `pipeline constructed` chạy trước khi Stream pipeline bên dưới bắt đầu. Các lời gọi trung gian như `filter`, `map`, `limit` không buộc phải duyệt toàn bộ nguồn ngay.
2. Phần tử `1` vào `filter`; bị loại, nên **không đi tới `map`**.
3. Phần tử `2` qua `filter` rồi ngay sau đó được `map` biến thành `20`.
4. Phần tử `3` bị loại.
5. Phần tử `4` đi qua `filter` và `map`, tạo `40`.
6. Khi `limit(2)` đã nhận hai kết quả, terminal operation không cần đòi thêm phần tử `5`. Pipeline kết thúc với `[20,40]`.

Đặc biệt, thứ tự in là `filter:2` rồi `map:2`, **không phải** `filter:1`, `filter:2`, ..., `filter:5` rồi mới in tất cả dòng `map`. Đó là một minh họa rõ cho việc **phối hợp xử lý theo phần tử** trong một pipeline tuần tự thông thường.

Trong ví dụ này, `println` được cài vào callback nhằm dạy cơ chế. **Không nên biến những dòng log/biến đếm trong intermediate operations thành yêu cầu nghiệp vụ**, vì Stream API có những tối ưu hóa và chế độ thực thi khác nhau được phép bỏ qua một số lời gọi callback.

## 4. “Một lần duyệt” chính xác nghĩa là gì?

Có ba mức độ cần phân biệt:

**(a) Duyệt nguồn một lần theo một pipeline tiêu thụ.** Với một pipeline tuần tự cơ bản, terminal operation yêu cầu các phần tử từ nguồn và đẩy chúng qua các bước trung gian. Không cần tạo một list sau `filter` rồi lại duyệt list ấy sau `map`.

**(b) Một phần tử có thể đi qua nhiều phép biến đổi.** Chẳng hạn `filter` có thể từ chối phần tử, khiến `map` không chạy với phần tử đó. Nếu nó được giữ, `map` có thể lập tức tạo giá trị đưa xuống downstream.

**(c) Không phải mọi bước đều chỉ cần O(1) bộ nhớ hay cho phép phát kết quả ngay.** Những thao tác stateful như `sorted()` có thể phải giữ dữ liệu để tạo thứ tự đúng. `distinct()` có thể cần lưu thông tin các giá trị đã gặp. `flatMap()` có thể mở từng stream con và duyệt các phần tử bên trong nó.

Do đó, **phối hợp trong một pipeline** không đồng nghĩa:

- Mọi phần tử nguồn bắt buộc phải được kiểm tra.
- Mọi callback người dùng đều được gọi.
- Mỗi callback chỉ chạy đúng một lần trong mọi tình huống.
- Không có buffer hoặc cấu trúc dữ liệu phụ.
- Không có việc xử lý nhiều chunk khác nhau khi chạy song song.
- Luôn nhanh hơn mọi vòng lặp thủ công.

Đặc tả Stream tập trung vào **kết quả và hợp đồng hành vi**, không cam kết một hình dạng vòng lặp/đồ thị object cố định cho mọi JDK.

## 5. Stateless operations: thuận lợi cho xử lý “xuyên dọc”

Một số intermediate operations phổ biến:

| Thao tác | Bản chất | Có thể chuyển từng phần tử xuống bước sau? |
|---|---|---|
| `map(Function)` | Một phần tử thành một giá trị | Thường có |
| `mapToInt(ToIntFunction)` | Một object thành một `int` | Thường có |
| `filter(Predicate)` | Giữ hoặc loại phần tử | Thường có; có thể không phát ra giá trị |
| `peek(Consumer)` | Thực hiện action lên phần tử khi nó được tiêu thụ | Có thể; chủ yếu để debug, không bảo đảm mọi action chạy |
| `flatMap(Function<T,Stream<R>>)` | Một phần tử tạo stream con | Có thể phát nhiều phần tử con; cần duyệt stream con |
| `limit(n)` | Chặn số phần tử đi xuống | Có thể dừng sớm, phụ thuộc dữ liệu và thứ tự |
| `skip(n)` | Bỏ qua các phần tử đầu | Có thể đi qua/bỏ phần tử trước khi phát tiếp |

`map` và `filter` là ví dụ tiêu biểu của **stateless operations**: callback của chúng không cần nhớ mọi phần tử đã gặp để áp dụng phép toán cho phần tử hiện tại. `flatMap` có thể phát số lượng phần tử thay đổi cho từng phần tử nguồn, nên số kết quả đầu ra khác số đầu vào; điều đó không khiến nó mặc định phải materialize toàn bộ output.

### 5.1. Phân biệt stateless operation và lambda có state

`map` được phân loại là stateless intermediate operation, **nhưng lambda do lập trình viên truyền vào vẫn có thể stateful**:

~~~java
// KHÔNG KHUYẾN NGHỊ nếu dùng state biến đổi bên ngoài:
AtomicInteger counter = new AtomicInteger();

List<Integer> values = numbers.stream()
        .map(n -> n + counter.incrementAndGet())
        .toList();
~~~

Đây là đoạn minh họa có `numbers` và import `AtomicInteger`. Dù `map` là stateless operation, callback đang truy cập trạng thái ngoài thay đổi theo số lần gọi. Điều này làm kết quả khó suy luận khi đổi sang parallel stream, thay terminal operation hoặc áp dụng tối ưu hóa.

Nên viết mapper **thuần khiết, không gây ảnh hưởng nguồn (*non-interfering*) và không phụ thuộc trạng thái thay đổi** khi có thể, nhất là trong các pipeline song song.

### 5.2. `flatMap` không phải một vòng lặp chỉ có một tầng

~~~java
List<String> words = groups.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();
~~~

`groups` trong đoạn minh họa là `List<List<String>>`. `flatMap` mở từng danh sách con và phát các `String` xuống `map`. Java có thể kết hợp các bước này, nhưng bản chất là duyệt cả nguồn ngoài và những phần tử của nguồn con, **không phải** phép xử lý “một lần gọi get cho mỗi phần tử outer” với đầu ra cố định một-một.

## 6. Stateful operations: khi phải có bộ nhớ hoặc ranh giới xử lý

Một intermediate operation **stateful** cần thông tin từ các phần tử khác để xác định kết quả.

### 6.1. `sorted()`

Để phát đầu ra đúng thứ tự, `sorted()` thường cần **nhận các phần tử và sắp xếp** trước khi downstream có thể xử lý chúng theo thứ tự cuối.

~~~java
List<String> ordered = Stream.of("pear", "fig", "apple")
        .sorted()
        .map(String::toUpperCase)
        .toList();
// [APPLE, FIG, PEAR]
~~~

Dòng trên là minh họa trong một phương thức, cần import `Stream`/`List`. Không nên kỳ vọng `sorted` luôn có thể đưa phần tử đầu tiên ra ngay khi nhận nó, vì vẫn có thể xuất hiện một phần tử nhỏ hơn ở phía sau nguồn.

### 6.2. `distinct()`

`distinct()` cần biết giá trị nào đã xuất hiện để loại phần tử lặp. Trên stream có thứ tự, việc duy trì lựa chọn phần tử đầu tiên và đặc biệt khi xử lý parallel có thể tốn thêm bộ nhớ hoặc synchronization.

~~~java
List<String> unique = Stream.of("a", "b", "a", "c")
        .distinct()
        .toList();
// [a, b, c]
~~~

Với `Stream<T>`, `distinct` dựa trên `Object.equals()`; các object có trạng thái mutable làm thay đổi kết quả của `equals/hashCode` trong khi đang xử lý là nguồn lỗi khó đoán.

### 6.3. `sorted`, `distinct` và `limit`

Các thao tác này có đặc điểm xử lý khác nhau:

- `sorted()` là thao tác stateful; với nguồn hữu hạn, việc sắp xếp có thể cần buffer rất nhiều phần tử. Với nguồn vô hạn, `sorted()` thường không thể cho ra phần tử đầu tiên hoặc hoàn tất.
- `distinct()` có thể cần tập giá trị đã thấy; với nguồn vô hạn có nhiều giá trị duy nhất, bộ nhớ lưu state có thể tăng.
- `limit(n)` là **short-circuiting stateful intermediate operation**; nó theo dõi số lượng phần tử được phép phát và có thể chặn nguồn sớm trong những tình huống phù hợp.

Phân loại `limit` là stateful vì cần nhớ đã phát bao nhiêu phần tử. Tuy nhiên, mức state này khác hẳn với `sorted` cần xử lý/giữ nhiều phần tử để sắp xếp.

**Hãy phân biệt việc “pipeline vẫn lazy” với việc “mọi bước có thể phát output ngay”**. Một pipeline có `sorted` vẫn có thể lazy ở mức **chưa chạy khi chưa có terminal operation**, song khi chạy nó có thể tạo ranh giới phải buffer.

## 7. Chương trình Java 17: ranh giới buffer tại sorted()

Lưu file **`SortedPipelineDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class SortedPipelineDemo {
    public static void main(String[] args) {
        List<String> names = List.of("kiwi", "pear", "fig");

        List<String> sorted = names.stream()
                .filter(s -> {
                    System.out.println("source:" + s);
                    return true;
                })
                .sorted(Comparator.comparingInt(String::length)
                        .thenComparing(Comparator.naturalOrder()))
                .map(s -> {
                    System.out.println("map:" + s);
                    return s.toUpperCase(Locale.ROOT);
                })
                .toList();

        System.out.println("result=" + sorted);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SortedPipelineDemo.java
java SortedPipelineDemo
~~~

Stdout của pipeline tuần tự trên danh sách này:

~~~text
source:kiwi
source:pear
source:fig
map:fig
map:kiwi
map:pear
result=[FIG, KIWI, PEAR]
~~~

**Phân tích:**

1. `filter(s -> true)` có thêm dòng in để quan sát thời điểm các phần tử **đi vào** `sorted`. Trong chương trình minh họa này, nó chấp nhận cả ba phần tử.
2. `sorted(Comparator.comparingInt(String::length).thenComparing(...))` sắp theo **độ dài tăng dần**, rồi theo **thứ tự tự nhiên** nếu cùng độ dài. `fig` có 3 ký tự, `kiwi` và `pear` có 4 ký tự, và `kiwi` đứng trước `pear`.
3. Trong cách thực thi tuần tự minh họa, ba dòng `source` được in trước khi các dòng `map` xuất hiện. `sorted` phải biết dữ liệu cần sắp trước khi phát kết quả theo thứ tự đúng.
4. `map` nhận từng phần tử **sau khi đã sắp xếp**, chuyển thành chữ in hoa bằng `Locale.ROOT`.
5. Pipeline vẫn dùng một chuỗi thao tác Stream; **không cần** lập trình viên tự tạo các list trung gian và viết nhiều vòng lặp. Nhưng không thể suy ra bộ nhớ phụ là O(1): `sorted` có thể cần buffer.

Lưu ý rằng những dòng `println` trong intermediate operations được dùng **có chủ đích để minh họa**, không phải API bảo đảm side effect cho mọi phép tối ưu, terminal operation hoặc kiểu nguồn khác.

## 8. Short-circuiting: phối hợp các bước và dừng khi đủ

`findFirst()`, `findAny()`, `anyMatch()`, `allMatch()` và `noneMatch()` là những terminal operations có thể **dừng sớm** khi đã đủ thông tin. `limit(n)` cũng tạo khả năng cắt phần còn lại của nguồn.

Ví dụ:

~~~java
Optional<String> first = names.stream()
        .filter(s -> s.startsWith("A"))
        .map(String::toUpperCase)
        .findFirst();
~~~

Đoạn minh họa có `names` kiểu `List<String>`, import `Optional`, và stream có encounter order từ `List`. Nếu phần tử khớp đầu tiên xuất hiện sớm, pipeline không cần xử lý tất cả phần tử còn lại.

### 8.1. Chương trình Java 17: findFirst dừng sau một kết quả

Lưu **`ShortCircuitPipelineDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class ShortCircuitPipelineDemo {
    public static void main(String[] args) {
        List<String> words = List.of("alpha", "beta", "gamma");

        Optional<String> first = words.stream()
                .filter(s -> {
                    System.out.println("check:" + s);
                    return s.length() > 4;
                })
                .map(s -> {
                    System.out.println("map:" + s);
                    return s.toUpperCase(Locale.ROOT);
                })
                .findFirst();

        System.out.println("first=" + first.orElse("none"));
    }
}
~~~

Lệnh chạy:

~~~bash
javac ShortCircuitPipelineDemo.java
java ShortCircuitPipelineDemo
~~~

Stdout:

~~~text
check:alpha
map:alpha
first=ALPHA
~~~

`alpha` là phần tử đầu tiên và có độ dài 5, vì vậy thỏa `s.length() > 4`. `findFirst()` đã có kết quả đúng theo encounter order và có thể dừng pipeline, nên không cần kiểm tra `beta` hay `gamma`.

**Nếu đổi sang `parallel()`**, Java có thể kiểm tra nhiều phần tử ở nhiều worker trước khi tìm thấy kết quả, nên không được dựa vào **số lần callback** hoặc thứ tự log như chương trình tuần tự ở trên. Kết quả giá trị `findFirst()` trên stream ordered vẫn tuân theo encounter order, nhưng lộ trình thực thi có thể khác.

### 8.2. Vị trí của limit và filter

~~~java
// Giới hạn số phần tử nguồn được cho qua trước khi lọc.
stream.limit(5).filter(predicate)

// Chọn tối đa năm phần tử thỏa điều kiện sau khi lọc.
stream.filter(predicate).limit(5)
~~~

Hai pipeline có thể trả kết quả khác nhau. Với nguồn vô hạn và predicate không bao giờ đúng, `filter(predicate).limit(5).toList()` có thể **không kết thúc**, dù có `limit(5)` ở phía sau, vì không nhận đủ năm phần tử qua lọc. Nếu cần giới hạn số lượt thử, đặt `limit` trước `filter`.

## 9. Tối ưu hóa: có thể bỏ qua một bước trung gian khi không ảnh hưởng kết quả

Một sự thật tinh tế: **Stream API không hứa gọi mọi behavioral parameter** nếu implementation chứng minh có thể tính terminal result mà không cần chạy phần đó.

Ví dụ:

~~~java
long count = List.of("a", "bb", "ccc").stream()
        .map(s -> {
            System.out.println("mapping:" + s);
            return s.toUpperCase();
        })
        .count();
~~~

Đây là đoạn minh họa; **đừng dùng số dòng `mapping` làm output được đảm bảo**. Một implementation biết chính xác số phần tử của nguồn, lại biết `map` không đổi số phần tử, có thể tính `count() == 3` **mà không duyệt mapper**. Đây là tối ưu hóa được nêu trực tiếp trong tài liệu `Stream.count()`.

Vì thế, phát biểu “stream phối hợp các bước trong một lần duyệt” **không có nghĩa** “mỗi thao tác trung gian chắc chắn sẽ được thực thi”. Đôi khi terminal operation được tối ưu để **không cần duyệt** phần nguồn mà kết quả vẫn đúng theo hợp đồng của Stream.

### 9.1. Tác dụng phụ không phải cơ chế bảo đảm

~~~java
// Không dùng kiểu này để bắt buộc ghi audit cho mọi phần tử.
long count = records.stream()
        .peek(this::audit)
        .count();
~~~

Nếu implementation có thể tính `count` từ kích thước nguồn, phần `peek` có thể **không chạy**. Thậm chí khi terminal operation cần traversal, short-circuiting có thể dừng sớm. Vì thế `peek` phù hợp hơn với debug/quan sát trong điều kiện có kiểm soát, **không nên dùng để thực hiện nghiệp vụ bắt buộc**.

Nếu mục đích là ghi audit cho mọi record, hãy tổ chức riêng một thao tác có hợp đồng rõ về xử lý toàn bộ phần tử, kiểm soát lỗi, giao dịch và thứ tự thực thi; không phụ thuộc các side effect của intermediate pipeline.

### 9.2. Đừng đo hiệu năng bằng số callback trong một ví dụ đơn lẻ

Lợi ích của pipeline fusion thường đến từ việc giảm collection trung gian và xử lý theo phần tử, nhưng hiệu năng còn phụ thuộc:

- Chi phí thực tế của mapper/predicate.
- Cách tổ chức nguồn, bộ nhớ/cache CPU và kiểu primitive hay boxed.
- Mức độ buffering của stateful operations.
- Tối ưu hóa JIT và phiên bản JDK.
- Chi phí phân mảnh/phối hợp khi dùng `parallel()`.
- Chi phí cấp phát/copy cuối cùng tại `collect()`/`toList()`.

Khi hiệu năng quan trọng, dùng benchmark phù hợp (ví dụ JMH) và dữ liệu đại diện, không kết luận “stream luôn nhanh hơn vòng lặp” chỉ dựa trên ví dụ nhỏ.

## 10. So sánh với vòng lặp và nhiều collection trung gian

Giả sử cần lấy số chẵn và nhân 10. Một cách thủ công:

~~~java
List<Integer> evens = new ArrayList<>();
for (Integer n : numbers) {
    if (n % 2 == 0) {
        evens.add(n);
    }
}

List<Integer> result = new ArrayList<>();
for (Integer n : evens) {
    result.add(n * 10);
}
~~~

Đây là đoạn minh họa với `numbers` kiểu `List<Integer>` và imports `ArrayList`/`List`. Cách này tạo một **`evens` trung gian** và duyệt nó thêm lần nữa.

Pipeline Stream:

~~~java
List<Integer> result = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .toList();
~~~

Biểu đạt cùng phép biến đổi với số bước khai báo ít hơn. Với `filter` và `map` stateless, Stream có thể nối các bước mà không tạo một `List` trung gian cho `evens`. `toList` vẫn phải tạo/giữ **kết quả cuối** theo yêu cầu của API.

Một **vòng lặp duy nhất** cũng làm được điều tương tự mà không cần list trung gian:

~~~java
List<Integer> result = new ArrayList<>();
for (Integer n : numbers) {
    if (n % 2 == 0) {
        result.add(n * 10);
    }
}
~~~

Do đó, lợi thế của Stream **không phải Java tạo ra khả năng “một vòng lặp” mà loop không có**, mà là cách **khai báo chuỗi biến đổi rõ ràng để thư viện tự điều phối**. Nếu nghiệp vụ yêu cầu nhiều `break`/`continue`, cập nhật trạng thái theo thứ tự, hoặc xử lý ngoại lệ phức tạp, vòng lặp tường minh có thể dễ đọc và kiểm soát hơn.

## 11. Một pipeline không đồng nghĩa một lần quét ở mọi bài toán

Một số tình huống yêu cầu **nhiều bước xử lý dữ liệu về mặt thuật toán**:

### 11.1. Sắp xếp cần thu thập rồi sắp xếp

`sorted()` có thể phải tích lũy nhiều hoặc tất cả phần tử để sắp xếp. Sau đó các phần tử mới được đưa xuống downstream theo thứ tự. Ngay cả khi code là một pipeline, nó không đơn giản tương đương một lần quét O(n) với bộ nhớ O(1).

### 11.2. `distinct()` cần ghi nhớ phần tử đã gặp

Để loại trùng, implementation có thể duy trì một tập hoặc cấu trúc tương đương. Khi dữ liệu lớn, lượng state cũng có thể lớn. Với stream ordered và parallelism, việc giữ đúng encounter order có thêm chi phí.

### 11.3. Một terminal operation có thể thu thập toàn bộ dữ liệu

`toList()` và `collect(toList())` cần lưu kết quả cuối. `groupingBy()` còn tạo cấu trúc map và các nhóm. Phối hợp thao tác không xóa nhu cầu lưu dữ liệu phục vụ **kết quả được yêu cầu**.

### 11.4. Sự khác biệt của nhiều terminal operations

~~~java
long size = numbers.stream().count();
int max = numbers.stream().mapToInt(Integer::intValue).max().orElse(0);
~~~

Ở đây có **hai pipeline khác nhau** và có thể là **hai traversal khác nhau** (hoặc được tối ưu). Không có chuyện biến `Stream` dùng một lần thành đối tượng có thể chạy nhiều terminal operations chỉ nhờ tính lazy.

Nếu cần nhiều số liệu tổng hợp từ một nguồn đắt đỏ, cân nhắc dùng một collector tổng hợp hoặc record accumulator đúng hợp đồng, thay vì chạy lại nguồn nhiều lần. Nhưng cần thiết kế combiner tương thích nếu chạy song song.

## 12. Sequential và parallel: vẫn phối hợp các bước nhưng cách chạy khác

### 12.1. Stream tuần tự

Trong `list.stream().filter(...).map(...).toList()`, cách suy nghĩ “từng phần tử đi qua các bước” thường hữu ích. Nguồn là `List` có encounter order; khi dùng các thao tác giữ thứ tự và terminal phù hợp, thứ tự kết quả được bảo toàn.

### 12.2. Parallel stream

Với `list.parallelStream()`, nguồn có thể được **chia thành nhiều phần** để xử lý song song. Mỗi worker áp dụng các bước của pipeline cho phần dữ liệu của mình, sau đó kết quả có thể được gộp.

~~~java
List<Integer> squares = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * n)
        .boxed()
        .toList();
~~~

Với stream có encounter order và phép biến đổi giữ thứ tự, kết quả logic vẫn là `[1, 4, 9, 16, 25]`. Tuy nhiên, các worker **không nhất thiết xử lý các giá trị theo thứ tự 1 → 5**, và callback có side effect không được dựa vào thứ tự thực thi.

**Phân biệt:**
- *Encounter order* là thứ tự phần tử theo semantics của nguồn/pipeline.
- *Execution order* là thứ tự thực tế các callback và task chạy.
- *Output order* phụ thuộc hợp đồng của terminal operation. Chẳng hạn `forEach` trên parallel stream không hứa duy trì encounter order, còn `forEachOrdered` áp dụng ràng buộc thứ tự phù hợp.

Dùng `parallel()` không tự đảm bảo nhanh hơn: `sorted`, `distinct`, `limit` trên nguồn ordered có thể cần điều phối/buffer và gây chi phí lớn.

## 13. Các nguồn primitive và phép xử lý không boxing không cần thiết

Một pipeline như:

~~~java
int total = IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .sum();
~~~

có `IntStream` xuyên suốt; các bước thao tác trên primitive `int`, không bắt buộc tạo `Integer` cho từng phần tử. Kết quả là `2 * (2+4+6+8+10) = 60`.

Trong khi đó:

~~~java
int total = boxedNumbers.stream()
        .filter(n -> n % 2 == 0)
        .mapToInt(Integer::intValue)
        .sum();
~~~

`boxedNumbers` là `List<Integer>`; `mapToInt` chuyển sang primitive stream. Nếu dữ liệu gốc là primitive hoặc số lượng rất lớn, chọn đúng `IntStream`/`LongStream`/`DoubleStream` có thể giảm boxing/unboxing và giúp mô tả phép tổng hợp chính xác hơn.

Dù thao tác có thể được phối hợp, **kiểu phần tử** và **chi phí mỗi bước** vẫn ảnh hưởng đến hiệu năng.

## 14. Các lỗi phổ biến khi hiểu “một lần duyệt”

| Quan niệm sai | Vì sao sai | Hiểu đúng |
|---|---|---|
| “Mỗi `filter()`/`map()` sẽ tạo list mới” | Intermediate operation thường chỉ dựng pipeline | Kết quả trung gian không nhất thiết được materialize |
| “`filter` luôn duyệt hết rồi `map` mới chạy” | Stateless operations có thể xử lý theo từng phần tử | `filter` và `map` thường xen kẽ trong traversal tuần tự |
| “Một pipeline = O(1) bộ nhớ” | `sorted`, `distinct`, collector có thể giữ state | Phân biệt fusion với bộ nhớ phụ |
| “Mỗi lambda luôn chạy đúng một lần với mỗi phần tử” | `filter` chặn downstream, short-circuit và tối ưu hóa bỏ bước | Không dùng callback trung gian làm cam kết side effect |
| “`Stream.count()` luôn chạy `map`” | API có thể suy ra size mà bỏ mapper | Chỉ dựa vào kết quả `count`, không dựa vào side effect mapper |
| “Có `limit(5)` là pipeline vô hạn chắc chắn dừng” | `filter` trước `limit` có thể không cho phần tử nào qua | Xét vị trí limit và điều kiện đạt |
| “Có `sorted()` thì không còn lazy” | Pipeline vẫn có thể trì hoãn đến terminal operation | Khi chạy, sorted có thể tạo ranh giới buffer |
| “`parallel()` giữ thứ tự in callback” | Worker thực thi không theo thứ tự xác định | Phân biệt thứ tự kết quả và thứ tự callback |
| “Có thể gọi nhiều terminal operations trên cùng stream” | Stream là luồng sử dụng một lần | Tạo pipeline mới hoặc tổng hợp nhiều kết quả trong một lần |
| “Chỉ Stream mới làm được một vòng lặp” | Vòng lặp thủ công cũng có thể fusion | Chọn theo độ rõ ràng, yêu cầu và đo lường |
| “`peek()` phù hợp với audit bắt buộc” | Có thể bị bỏ qua hoặc dừng sớm | Tách side effect bắt buộc khỏi intermediate operations |
| “`flatMap` luôn là một-một” | Một phần tử có thể phát 0..n kết quả | Đếm theo các phần tử nguồn con thực tế |

## 15. Checklist để đọc và tối ưu một Stream pipeline

1. **Nguồn là gì?** Collection, mảng, file, nguồn vô hạn hay primitive range?
2. **Đâu là terminal operation?** Chưa có terminal thì phần lớn intermediate pipeline chưa được tiêu thụ.
3. **Bước nào stateless?** `map` và `filter` thường thuận lợi cho xử lý theo phần tử.
4. **Bước nào stateful?** `sorted`, `distinct`, `limit` có nhu cầu state khác nhau.
5. **Bước nào có thể dừng sớm?** `findFirst`, `anyMatch`, `limit` có thể giảm số phần tử cần xử lý.
6. **Thứ tự thao tác có thay đổi kết quả không?** `limit` trước/sau `filter`, `sorted` trước/sau `limit` thường không hoán đổi tùy ý.
7. **Callback có side effect, đọc state thay đổi hoặc sửa source không?** Cố gắng dùng hàm stateless, non-interfering.
8. **Có cần encounter order không?** Kiểm tra nguồn và terminal khi dùng parallelism.
9. **Có cấu trúc trung gian/bộ nhớ lớn không?** `sorted`/`distinct`/`groupingBy`/`toList` có thể giữ nhiều dữ liệu.
10. **Có đang dùng lại stream đã tiêu thụ không?** Một terminal operation kết thúc vòng đời sử dụng stream đó.
11. **Có thể dùng primitive stream để tránh boxing không?** Cân nhắc `mapToInt`, `IntStream` khi phù hợp.
12. **Có tài nguyên cần đóng không?** Stream từ `Files.lines` cần try-with-resources; việc lazy không tự đóng file giúp bạn.

Khi đánh giá hiệu năng, hãy đo một pipeline **với cùng kết quả**, tránh so sánh với một vòng lặp có hành vi, null policy hoặc ranh giới dừng khác nhau.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Với `filter` rồi `map` trên một Stream tuần tự, Java có buộc phải tạo List trung gian giữa hai bước không?

**Câu 2.** Trong `PipelineFusionDemo`, vì sao không thấy `filter:5`?

**Câu 3.** Vì sao `sorted` có thể khiến tất cả các dòng log upstream xuất hiện trước dòng log downstream?

**Câu 4.** `Stream.toList()` có nghĩa không cấp phát một collection nào không?

**Câu 5.** `Stream.of("a","b").map(x -> sideEffect(x)).count()` có chắc gọi `sideEffect` hai lần không?

**Câu 6.** Chạy song song có thay đổi nghĩa logic của `map`/`filter` thuần khiết trên nguồn ordered không? Thứ tự callback có cố định không?

**Câu 7.** Vì sao `Stream.generate(() -> 1).filter(n -> n > 1).limit(3).toList()` không hoàn tất?

**Câu 8.** Dùng `peek` để ghi audit bắt buộc có an toàn không?

**Câu 9.** Muốn cả tổng và số lượng từ cùng một nguồn đắt, có nên chạy hai pipeline độc lập hay cân nhắc collector tổng hợp?

**Câu 10.** `flatMap` có luôn tạo một phần tử mới cho mỗi phần tử nguồn không?

**Đáp án ngắn:**

1. Không. Những bước stateless có thể được phối hợp, xử lý lần lượt theo từng phần tử.
2. `limit(2)` có đủ hai kết quả sau khi xử lý `2` và `4`, nên pipeline dừng trước `5`.
3. `sorted` cần biết các phần tử sẽ sắp trước khi phát kết quả đúng thứ tự, nên thường có buffering.
4. Không, `toList` vẫn phải tạo/giữ kết quả cuối thích hợp.
5. Không; `count` có thể dựa vào size của nguồn mà bỏ mapper.
6. Với callback thuần khiết, semantics kết quả vẫn theo hợp đồng; thứ tự thực thi callback không cố định.
7. `filter` không bao giờ cho phần tử qua, `limit` phía sau không đạt ba phần tử.
8. Không; intermediate callback có thể bị bỏ qua hoặc dừng sớm.
9. Có thể cân nhắc một collector/accumulator tổng hợp đúng hợp đồng để tránh tiêu thụ lại nguồn.
10. Không. `flatMap` có thể tạo 0, 1 hoặc nhiều phần tử kết quả từ mỗi phần tử nguồn.

## 17. Nguồn đối chiếu chính thức

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): intermediate/terminal operations, laziness, short-circuiting, stateless/stateful behaviors và tối ưu hóa.
- [Java SE 17 API — Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()): giải thích khả năng suy ra số phần tử mà không thực hiện một số intermediate operations.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): pipeline execution, behavioral parameters, non-interference, statelessness và parallelism.
- [Java SE 17 API — Stream.sorted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#sorted()): stateful intermediate operation có ràng buộc thứ tự.
- [Java SE 17 API — Stream.limit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#limit(long)): short-circuiting stateful intermediate operation và lưu ý trên stream parallel có thứ tự.

**Ghi nhớ:** Trong Java Stream, các bước như `filter` và `map` **có thể được phối hợp** để phần tử đi qua nhiều bước **trong cùng một traversal**, không cần tạo list trung gian sau mỗi bước. Nhưng `sorted`/`distinct` có thể giữ state, short-circuit có thể dừng sớm, và những tối ưu hóa như `count` có thể bỏ hoàn toàn một vài callback. Hãy tin **hợp đồng kết quả** của Stream API, không dựa vào thứ tự hoặc số lần gọi side effect ở các intermediate operations.