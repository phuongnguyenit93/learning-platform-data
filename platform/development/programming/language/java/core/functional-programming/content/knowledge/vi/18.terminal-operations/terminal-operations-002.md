# Stream.count() và những trường hợp không cần duyệt từng phần tử trong Java

## 1. count() trả kết quả gì?

Trong Java Stream API, `count()` là một **thao tác kết thúc** (*terminal operation*) trả về số phần tử của Stream dưới dạng `long`:

~~~java
long count = List.of("An", "Binh", "Chi").stream().count();
System.out.println(count); // 3
~~~

Đoạn minh họa đặt trong một phương thức, cần import `java.util.List`. Tại thời điểm gọi `count()`, pipeline được yêu cầu cung cấp một kết quả kiểu số: **có bao nhiêu phần tử thuộc Stream kết quả**, sau khi tính tới các thao tác đứng trước nó.

Ví dụ:

~~~java
long result = List.of(1, 2, 3, 4, 5).stream()
        .filter(n -> n % 2 == 0)
        .count();
// 2
~~~

Ở đây, `count()` đếm phần tử **sau khi lọc**: chỉ có 2 và 4. Không phải cứ nguồn có năm phần tử thì mọi pipeline đều trả 5.

Điều bất ngờ là: **để biết có bao nhiêu phần tử, Java không nhất thiết phải gọi hàm xử lý cho từng phần tử**. Nếu implementation đã biết chính xác số lượng từ nguồn và biết các bước trung gian không đổi số lượng, nó **có thể** tính ra `count()` mà **không duyệt** từng phần tử và **không gọi** những lambda trong `map` hoặc `peek`.

Đây là hành vi được ghi rõ trong *API Note* của Java SE 17 về `Stream.count()`, không phải lỗi của Stream hay lỗi của `peek`.

## 2. Phải phân biệt ba loại số lượng và ba câu hỏi

Các phép đếm trông giống nhau nhưng trả lời những câu hỏi khác nhau:

| Biểu thức | Câu hỏi được trả lời | Kết quả với [1,2,3,4,5] |
| --- | --- | --- |
| `list.size()` | Collection nguồn đang có bao nhiêu phần tử? | 5 |
| `list.stream().count()` | Stream nguồn có bao nhiêu phần tử? | 5 |
| `list.stream().filter(n -> n > 3).count()` | Có bao nhiêu phần tử thỏa điều kiện? | 2 |
| `list.stream().limit(3).count()` | Tiền tố giới hạn 3 phần tử có bao nhiêu phần tử? | 3 |
| `list.stream().skip(2).count()` | Còn bao nhiêu phần tử sau khi bỏ hai phần tử đầu? | 3 |

`Collection.size()` trả `int`. `Stream.count()` trả `long`. Với một collection thông thường không bị sửa trong quá trình xử lý và **pipeline không đổi số lượng phần tử**, giá trị hai phép đếm có thể bằng nhau; song chúng là hai API có **hợp đồng và phạm vi áp dụng khác nhau**.

Nếu chỉ cần số phần tử của một `Collection` đang có, không có bước xử lý dữ liệu nào, gọi `collection.size()` thường diễn đạt ý định trực tiếp hơn và tránh tạo Stream không cần thiết. Nếu cần đếm **kết quả sau lọc hoặc những bước biến đổi**, dùng `stream().filter(...).count()` hay pipeline tương ứng.

**Không nhầm `count()` với việc “chạy mọi callback rồi mới tăng bộ đếm”.** Đặc tả cho phép tránh những công việc không cần thiết để trả về số lượng chính xác.

## 3. Cơ chế tối ưu: nguồn có kích thước chính xác đã biết

### 3.1. Spliterator và đặc tính SIZED

Stream đọc phần tử từ một nguồn, thường thông qua một `Spliterator`. Một số nguồn và spliterator biết chính xác số phần tử có thể duyệt **mà không cần lặp qua chúng**.

Đặc tính `Spliterator.SIZED` có ý nghĩa: ở thời điểm thích hợp, `estimateSize()` của spliterator cho biết kích thước chính xác của các phần tử còn lại theo hợp đồng. Khi có đặc tính này, `getExactSizeIfKnown()` có thể trả kích thước chính xác; nếu không có `SIZED`, phương thức đó trả `-1`.

Nguồn `List` chuẩn, một số Stream từ mảng, và `IntStream.range(...)` thường cung cấp đủ thông tin về số phần tử. Ngược lại, một nguồn được tạo bởi thao tác phát sinh không giới hạn có thể **không có** kích thước chính xác biết trước.

Ví dụ minh họa:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
long count = names.stream().count(); // 3

long numbers = java.util.stream.IntStream.range(0, 1_000_000)
        .count(); // 1_000_000
~~~

Không cần suy ra rằng Java đã gọi một triệu lần một callback để tạo ra kết quả thứ hai. Nguồn dạng khoảng số có kích thước được biết theo cấu trúc khoảng.

**Giới hạn cần nắm:** `SIZED` của một nguồn chưa đủ để kết luận mọi pipeline đều không cần duyệt. Các phép xử lý đứng sau có thể thay đổi số lượng phần tử và làm kích thước kết quả không thể tính đơn giản từ kích thước nguồn.

### 3.2. Các thao tác giữ nguyên số lượng

Về **ngữ nghĩa**, các thao tác như `map` hoặc `peek` không thêm/bớt phần tử của Stream:

~~~java
long value = List.of("a", "bb", "ccc").stream()
        .map(String::toUpperCase)
        .count(); // 3
~~~

Dù mỗi phần tử sẽ được chuyển thành chuỗi khác **nếu phần tử được ánh xạ**, số lượng trước và sau `map` vẫn bằng nhau. Với nguồn có kích thước biết trước, implementation có thể biết kết quả `count()` bằng kích thước nguồn mà không cần tạo các chuỗi chữ hoa.

Tương tự, `peek` quan sát các phần tử **khi phần tử thực sự đi qua bước này**, nhưng không bổ sung hay loại phần tử khỏi Stream. Vì vậy `peek` không phải “hàng rào” bắt buộc mọi phần tử phải được duyệt trước khi `count()` hoàn tất.

Một số phép như `sorted()`, `unordered()` và các chuyển đổi kiểu phần tử giữ nguyên cardinality về mặt ý nghĩa, nhưng điều đó **không phải cam kết** rằng implementation luôn bỏ qua mọi thao tác ấy. Quy tắc an toàn là: **viết chương trình chỉ phụ thuộc vào giá trị kết quả và những tác dụng phụ được hợp đồng API bảo đảm, không phụ thuộc vào việc một callback trung gian nhất định đã chạy**.

### 3.3. Các thao tác có thể thay đổi số lượng

| Thao tác | Có thể thay đổi số phần tử? | Ý nghĩa với khả năng suy ra count |
| --- | --- | --- |
| `map(f)` | Không: một vào, một ra | Có thể suy từ nguồn |
| `peek(action)` | Không | Có thể bị bỏ qua khi tính count |
| `mapToInt(f)`, `mapToLong(f)` | Không | Kết quả nguyên thủy, số phần tử không đổi |
| `sorted()` | Không | Có thể không cần thực hiện sắp xếp chỉ để đếm |
| `filter(p)` | Có: phần tử có thể bị loại | Thường cần xác định phần tử nào thỏa |
| `flatMap(f)` | Có: một phần tử có thể sinh 0, 1 hoặc nhiều phần tử | Thường không biết số kết quả từ kích thước nguồn |
| `mapMulti(...)` | Có: một vào có thể tạo nhiều/không tạo phần tử | Cần thêm thông tin để biết số lượng |
| `distinct()` | Có: bỏ phần tử trùng | Thường phải xét dữ liệu, trừ khi thuộc tính nguồn/pipeline đã đủ để biết |
| `takeWhile(p)`, `dropWhile(p)` | Có | Phụ thuộc predicate và thứ tự/đặc tính nguồn |
| `skip(n)` và `limit(n)` | Có nhưng theo số lượng giới hạn rõ | Có thể tính trực tiếp nếu đã biết kích thước đầu vào |

Nói “thường cần” không đồng nghĩa luôn buộc chạy đúng một callback trên mọi phần tử. Terminal operation, nguồn, chế độ tuần tự/song song và tối ưu cho phép thay đổi số lần thực thi callback. Nếu phép đếm không thể được suy từ metadata, implementation phải xác định cardinality kết quả bằng một cách phù hợp với hợp đồng.

## 4. Thí nghiệm quan trọng: map().count() có thể không gọi map

Hãy xét:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");
AtomicInteger mapped = new AtomicInteger();

long n = words.stream()
        .map(word -> {
            mapped.incrementAndGet();
            return word.toUpperCase();
        })
        .count();

System.out.println(n);
System.out.println(mapped.get());
~~~

Đây là đoạn minh họa trong một phương thức, cần import `java.util.List` và `java.util.concurrent.atomic.AtomicInteger`.

Trong môi trường Java 17 được kiểm thử cho bài này, kết quả là:

~~~text
4
0
~~~

**Tại sao `mapped.get()` bằng 0?** Bốn phần tử nguồn đã có số lượng chính xác; `map` giữ nguyên số lượng. Khi chỉ cần `count()`, việc tính giá trị chữ hoa của từng phần tử không ảnh hưởng kết quả nên implementation có thể bỏ qua bước ánh xạ.

Không được kết luận:

- “`map` luôn bị bỏ qua nếu phía sau là `count`.”
- “Nếu có `map` thì mọi exception hoặc log trong lambda chắc chắn xảy ra.”
- “Trình biên dịch đã hiểu nội dung lambda có hoặc không có side effect.”

Điều được phép là **bỏ qua việc đánh giá bước trung gian nếu điều đó không ảnh hưởng kết quả theo hợp đồng Stream**. Tác dụng phụ phụ thuộc vào việc gọi lambda không phải thứ được đảm bảo trong tình huống này.

Đặt công việc bắt buộc trong `map` rồi mong `count()` “kích hoạt công việc” là một lỗi thiết kế.

## 5. peek().count(): ví dụ chính thức dễ gây bất ngờ

`peek(action)` thường được giới thiệu như cách quan sát dữ liệu đi qua pipeline:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");

long count = words.stream()
        .peek(System.out::println)
        .count();
~~~

Trong Java 17, với nguồn `List` như trên, implementation có thể in **không dòng nào** từ `peek` mà vẫn trả `count == 4`. Đây cũng là tình huống được Javadoc `Stream.count()` dùng để giải thích quyền tối ưu bỏ qua quá trình duyệt. Nó không mâu thuẫn với ý nghĩa của `peek`: action chỉ diễn ra khi các phần tử được xử lý qua bước đó.

Nếu muốn kiểm chứng bằng bộ đếm:

~~~java
AtomicInteger peeked = new AtomicInteger();

long count = words.stream()
        .peek(word -> peeked.incrementAndGet())
        .count();

System.out.println("count=" + count);
System.out.println("peek calls=" + peeked.get());
~~~

Khi chạy ví dụ Java 17 đã kiểm chứng, `count=4` và `peek calls=0`. Hãy nhớ đó là **hành vi thực nghiệm của implementation trong ví dụ**, không phải lời hứa mọi phiên bản Java phải thực hiện chính xác zero callback.

### 5.1. peek dành chủ yếu cho quan sát khi xử lý, không phải công việc bắt buộc

Sử dụng `peek` để:
- Gỡ lỗi tạm thời khi một pipeline thực sự cần xử lý phần tử.
- Quan sát giá trị trung gian trong ngữ cảnh đã hiểu rõ tính lazy/short-circuit và khả năng tối ưu.

Không sử dụng `peek` để:
- Lưu bản ghi bắt buộc vào database.
- Gửi email/HTTP request bắt buộc một lần cho từng phần tử.
- Thay đổi trạng thái nghiệp vụ phải xảy ra.
- Làm bằng chứng rằng mọi phần tử đã được xử lý.

Nếu mục tiêu là thực hiện hành động cho từng phần tử, hãy chọn API có **hợp đồng hành động** phù hợp, chẳng hạn `forEach(Consumer)`, hoặc một vòng lặp. Tuy nhiên `forEach` trên parallel stream không đảm bảo thứ tự; và mọi tác dụng phụ vẫn cần cân nhắc thread safety, exception và idempotency.

**Nếu chỉ cần đếm**, đừng đưa logging hay nghiệp vụ vào pipeline rồi dùng `count()` làm cách kích hoạt chúng.

## 6. Tại sao filter().count() thường phải xét dữ liệu?

Xét:

~~~java
long count = List.of("a", "bb", "ccc", "dddd").stream()
        .filter(word -> word.length() > 2)
        .count(); // 2
~~~

Từ số lượng nguồn 4 **chưa thể suy ra** có bao nhiêu chuỗi dài hơn hai ký tự. Cần biết nội dung các chuỗi hoặc thông tin tương đương về predicate. Trong một pipeline tuần tự thông thường, `filter` quyết định phần tử nào được giữ trước khi biết `count`.

Để quan sát:

~~~java
AtomicInteger tested = new AtomicInteger();

long count = words.stream()
        .filter(word -> {
            tested.incrementAndGet();
            return word.length() > 2;
        })
        .count();

System.out.println("filtered=" + count);
System.out.println("predicate calls=" + tested.get());
~~~

Trong kiểm thử Java 17 của bài, `filtered=2` và `predicate calls=4`. Đây là ví dụ cụ thể cho lý do `filter` thường làm mất khả năng suy ra cardinality từ kích thước nguồn.

**Không tuyệt đối hóa:** các tối ưu khác, nguồn đã mang thuộc tính đặc biệt, hoặc cách kết hợp terminal operation có thể thay đổi công việc thực tế. `filter` chỉ bảo đảm kết quả chứa phần tử thỏa predicate, không buộc người lập trình có thể dùng số lần callback như một chỉ số nghiệp vụ độc lập.

### 6.1. filter và map đứng ở đâu?

Hai pipeline:

~~~java
long a = words.stream()
        .map(String::toUpperCase)
        .filter(word -> word.length() >= 3)
        .count();

long b = words.stream()
        .filter(word -> word.length() >= 3)
        .map(String::toUpperCase)
        .count();
~~~

Ở đây kết quả cùng là 2 với dữ liệu ví dụ, vì chuyển sang chữ hoa không làm thay đổi độ dài chuỗi trong ngữ cảnh ví dụ cụ thể. Nhưng thứ tự các thao tác **có thể** thay đổi ngữ nghĩa, chi phí, số callback nếu logic thực tế khác (ví dụ một phép `map` chuẩn hóa/sửa dữ liệu trước khi kiểm tra).

Chỉ hoán đổi hai bước khi chứng minh chúng không làm thay đổi điều kiện nghiệp vụ và hợp đồng kết quả. Không tự đảo bước để “tăng hiệu năng” nếu làm thay đổi ý nghĩa dữ liệu được đếm.

## 7. skip(), limit() và khả năng tính số lượng không duyệt

Giả sử nguồn đã biết có `N` phần tử, chẳng hạn `List` ổn định có kích thước 4:

~~~java
List<String> words = List.of("a", "bb", "ccc", "dddd");
long count = words.stream()
        .skip(1)
        .limit(2)
        .count();
// 2
~~~

Với pipeline đơn giản này, số lượng có thể tính toán từ N và các giới hạn:
- Sau `skip(k)`: còn `max(0, N - k)` phần tử.
- Sau `limit(m)`: còn `min(m, N còn lại)` phần tử.

Nếu `N=4`, `k=1`, `m=2`, số lượng là 2. Với `List` có kích thước xác định và không có bước phụ thuộc nội dung xen giữa, việc tính kích thước có thể **không cần** lấy từng phần tử.

| Pipeline trên List 4 phần tử | Kết quả count |
| --- | ---: |
| `stream().count()` | 4 |
| `stream().limit(2).count()` | 2 |
| `stream().limit(20).count()` | 4 |
| `stream().skip(1).count()` | 3 |
| `stream().skip(20).count()` | 0 |
| `stream().skip(1).limit(2).count()` | 2 |
| `stream().limit(2).skip(1).count()` | 1 |
| `stream().filter(x -> x.length() > 2).count()` | 2, cần biết các giá trị |

**Giới hạn:** các công thức trên dựa vào nguồn có kích thước đã biết và pipeline với những thao tác đúng như ví dụ. Khi có `filter`, `flatMap` hoặc các thao tác khác làm số lượng phụ thuộc dữ liệu, không thể lấy kích thước nguồn rồi áp dụng các phép cộng trừ đơn giản để suy ra kết quả.

### 7.1. count() sau limit không giống “đã xem đúng limit phần tử”

Giá trị `count()` bằng 2 không chứng minh hai phần tử đã thật sự được duyệt hay các callback trước đó đã chạy đúng hai lần.

Nếu nguồn là một `List` và mọi thao tác trước limit giữ nguyên số lượng, Java có thể suy ra kết quả. Nếu nguồn là một bộ tạo không có kích thước sẵn, để có n phần tử có thể cần phát sinh/evaluate phần tử.

Vì vậy **cardinality** (số lượng trong kết quả) và **work performed** (số phần tử được xử lý/callback được gọi) không đồng nghĩa.

## 8. Nguồn không biết sẵn kích thước: generate và flatMap

Một trường hợp ngược lại:

~~~java
AtomicInteger generated = new AtomicInteger();

long count = Stream.generate(() -> {
        generated.incrementAndGet();
        return "x";
    })
    .limit(3)
    .count();
~~~

Đoạn minh họa cần import `java.util.stream.Stream` và `AtomicInteger`. `Stream.generate` tạo nguồn về mặt hợp đồng không bị giới hạn, không có số lượng hữu hạn được công bố như `List.size()`. `limit(3)` làm kết quả hữu hạn.

Trong chương trình Java 17 được kiểm thử:
- `count` bằng 3.
- `generated.get()` bằng 3.

Không nên biến số lần supplier được gọi ở một implementation thành luật tổng quát cho mọi API/lịch chạy. Quan trọng hơn: nếu loại bỏ `limit(3)` và gọi `Stream.generate(...).count()` trên nguồn không giới hạn mà không có điều kiện chấm dứt khác, phép tính không có kết quả hữu hạn để hoàn tất bình thường.

Với `flatMap`:

~~~java
long letters = List.of("ab", "cde").stream()
        .flatMap(word -> word.chars()
                .mapToObj(codePoint -> (char) codePoint))
        .count();
// 5
~~~

Đây là đoạn minh họa trong một phương thức, cần import `java.util.List`. `flatMap` tạo 2 phần tử từ chuỗi đầu và 3 phần tử từ chuỗi sau, nên số kết quả là 5. Không thể tính kết quả này chỉ từ `List.size()==2`. Mã `String.chars()` trả các đơn vị UTF-16 dưới dạng int; với văn bản Unicode có ký tự bổ sung, “chữ cái” trong nghĩa người dùng có thể khác số đơn vị UTF-16. Ví dụ ở đây dùng ký tự ASCII để không lẫn khái niệm.

## 9. Ví dụ chạy độc lập bằng Java 17

Tạo file **StreamCountOptimizationDemo.java**. Ví dụ sử dụng bộ đếm AtomicInteger **chỉ để quan sát** số lần callback được gọi trong lần chạy thực nghiệm; trong ứng dụng production không dùng counter như cách kích hoạt công việc.

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamCountOptimizationDemo {
    public static void main(String[] args) {
        List<String> words = List.of("a", "bb", "ccc", "dddd");

        AtomicInteger mapped = new AtomicInteger();
        long mappedCount = words.stream()
                .map(word -> {
                    mapped.incrementAndGet();
                    return word.toUpperCase();
                })
                .count();
        System.out.println("map count=" + mappedCount
                + ", map calls=" + mapped.get());

        AtomicInteger peeked = new AtomicInteger();
        long peekCount = words.stream()
                .peek(word -> peeked.incrementAndGet())
                .count();
        System.out.println("peek count=" + peekCount
                + ", peek calls=" + peeked.get());

        AtomicInteger tested = new AtomicInteger();
        long longWords = words.stream()
                .filter(word -> {
                    tested.incrementAndGet();
                    return word.length() > 2;
                })
                .count();
        System.out.println("filtered count=" + longWords
                + ", predicate calls=" + tested.get());

        long sliced = words.stream().skip(1).limit(2).count();
        System.out.println("slice count=" + sliced);

        AtomicInteger generated = new AtomicInteger();
        long generatedCount = Stream.generate(() -> {
                    generated.incrementAndGet();
                    return "x";
                })
                .limit(3)
                .count();
        System.out.println("generated count=" + generatedCount
                + ", supplier calls=" + generated.get());

        long rangeCount = IntStream.range(0, 1_000_000).count();
        System.out.println("range count=" + rangeCount);

        long emptyCount = Stream.<String>empty().count();
        System.out.println("empty count=" + emptyCount);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc JDK mới hơn có hỗ trợ đích Java 17:

~~~bash
javac --release 17 StreamCountOptimizationDemo.java
java StreamCountOptimizationDemo
~~~

**Stdout đã được kiểm chứng với Java 17 trong môi trường thử nghiệm:**

~~~text
map count=4, map calls=0
peek count=4, peek calls=0
filtered count=2, predicate calls=4
slice count=2
generated count=3, supplier calls=3
range count=1000000
empty count=0
~~~

### 9.1. Vì sao các con số đúng?

1. **`map count=4, map calls=0`:** nguồn `List` dài 4, `map` giữ cardinality và giá trị mới không cần thiết để tính số lượng.
2. **`peek count=4, peek calls=0`:** `peek` không làm đổi cardinality. Implementation được phép không duyệt nguồn khi biết số lượng.
3. **`filtered count=2, predicate calls=4`:** predicate chọn `"ccc"` và `"dddd"`. Trong lần chạy này cả bốn phần tử được kiểm tra để biết hai phần tử hợp lệ.
4. **`slice count=2`:** nguồn 4 phần tử, bỏ một, giới hạn hai, nên cardinality kết quả là 2.
5. **`generated count=3, supplier calls=3`:** `Stream.generate` không phải nguồn hữu hạn có kích thước biết sẵn; trong implementation được thử nghiệm đã phát sinh ba phần tử để đáp ứng `limit(3)`.
6. **`range count=1000000`:** `IntStream.range(0,1_000_000)` mô tả đúng một triệu số nguyên từ 0 tới 999.999, đủ thông tin kích thước nguồn.
7. **`empty count=0`:** Stream rỗng có không phần tử.

**Cảnh báo quan trọng về output:** kết quả `count` là hợp đồng; các chỉ số callback là **dữ liệu chẩn đoán của lần chạy này**, không phải cam kết mọi phiên bản JVM phải có số lần gọi giống hệt. Nên kiểm tra hành vi thực tế trên JDK sử dụng nếu đang điều tra tối ưu hóa, nhưng thiết kế nghiệp vụ không được dựa vào những con số chẩn đoán đó.

## 10. count() có bảo đảm exception trong map được ném ra không?

**Không.** Nếu tính được số lượng mà không cần đánh giá `map`, exception do chính `map` sẽ ném **khi lambda thực sự chạy** cũng có thể không xuất hiện.

Phản ví dụ minh họa:

~~~java
// Không được dùng như một bước xác thực dữ liệu:
// long count = items.stream()
//         .map(item -> {
//             if (!isValid(item)) throw new IllegalArgumentException();
//             return transform(item);
//         })
//         .count();
~~~

Ở đây `items`, `isValid` và `transform` là các tên giả định; code được comment để nhấn mạnh **đây không phải một quy trình validation đáng tin**. Nếu nguồn có kích thước biết trước và `map` chỉ thay đổi giá trị chứ không thay đổi số lượng, `count` có thể trả kết quả mà không gọi `isValid`.

Muốn kiểm tra dữ liệu rồi báo lỗi hoặc thống kê số phần tử hợp lệ, hãy sử dụng một operation mà **kết quả phụ thuộc vào điều kiện**:

~~~java
long validCount = items.stream()
        .filter(item -> isValid(item))
        .count();
~~~

Đây là ví dụ với tên `items` và `isValid` giả định. Với pipeline thông thường, số phần tử thỏa điều kiện phụ thuộc vào việc kiểm tra dữ liệu. Tuy nhiên, nếu yêu cầu là **xác nhận mọi phần tử đều hợp lệ và báo lỗi đầy đủ**, hãy thiết kế một quy trình validation rõ ràng hoặc danh sách kết quả Success/Failure; không coi `filter(...).count()` là giải pháp chung cho mọi chính sách kiểm tra lỗi.

Đặc biệt, **không dùng side effect hoặc exception trong `map` làm cơ chế kiểm tra bắt buộc trước `count`**. Đây là bài học thực tế quan trọng nhất của tối ưu hóa `count()`.

## 11. count() trong parallel stream

Một pipeline như:

~~~java
long count = List.of(10, 20, 30, 40)
        .parallelStream()
        .map(n -> n * n)
        .count();
// 4
~~~

vẫn có nguồn `List` với cardinality đã biết, và `map` vẫn giữ một-đổi-một. Việc bật parallel không làm mất quyền suy ra số lượng. Có thể implementation không cần khởi chạy các callback song song để hoàn tất `count()`.

Với pipeline có `filter` và nguồn lớn, việc đánh giá predicate có thể được phân phối trên nhiều thread. Khi đó:
- Thứ tự thời gian đánh giá predicate không được bảo đảm giống thứ tự phần tử nguồn.
- Không ghi vào `ArrayList` hay bộ đếm mutable không thread-safe từ callback để dự đoán chính xác kết quả.
- Nếu cần đếm điều kiện, để Stream tự tổng hợp thông qua `filter(...).count()`.
- Các tác dụng phụ có thể bị bỏ qua hoặc thực thi khác cách nếu implementation tối ưu pipeline.
- Không suy ra “parallel nhanh hơn” chỉ từ tên phương thức. Với `count` có thể lấy kích thước trực tiếp, việc thử bật parallel để tăng tốc là không có lợi ích rõ ràng.

**Không dùng `count()` để điều phối công việc.** Nếu yêu cầu là chạy action cho từng phần tử, cần thiết kế hành động và phối hợp đa luồng phù hợp, độc lập với việc lấy cardinality.

## 12. Tối ưu và tính đúng: khi nào kết quả count có thể suy ra?

Một checklist kỹ thuật:

1. **Nguồn có kích thước chính xác không?** `List`, mảng, một khoảng số có giới hạn thường dễ suy ra; nguồn generated không giới hạn hoặc một pipeline sinh nhiều phần tử có thể không.
2. **Các bước trung gian có đổi số lượng không?** `map` thường giữ nguyên, `filter` và `flatMap` thường làm thay đổi; `skip`/`limit` có thể tính từ một kích thước đã biết.
3. **Stream có được dùng đúng hợp đồng không?** Không sửa nguồn trong lúc duyệt, không đặt callback can thiệp vào nguồn, không dựa vào side effect tùy ý.
4. **Có cần giá trị phần tử hay chỉ cần số lượng?** Nếu chỉ đếm, framework có thể không cần tạo giá trị biến đổi trung gian.
5. **Có bước trung gian như `sorted` không?** Nếu số phần tử không đổi và mục tiêu chỉ là đếm, sắp xếp có thể là công việc không cần thực hiện.
6. **Bạn đang dựa vào logger/counter trong `peek` hoặc `map` không?** Nếu có, đó là hợp đồng không an toàn.
7. **Có nguồn vô hạn không?** Cần `limit` hoặc điều kiện kết thúc khác nếu muốn phép đếm hoàn tất.
8. **Có concurrency hoặc nguồn bị thay đổi không?** Phải tuân thủ contract của Collection/Spliterator để kết quả được xác định.

Cũng không nên suy từ việc một Stream có `SIZED` rằng bất kỳ operation nào tự động là `O(1)`. Kích thước có thể mất tính xác định sau các bước xử lý, hoặc implementation có thể chọn cách thực thi khác. **Tối ưu hóa được phép**, chứ không phải một cam kết hiệu năng tuyệt đối trong mọi hệ thống.

## 13. Những lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu/sửa |
| --- | --- | --- |
| `count()` luôn lặp qua từng phần tử | Có thể lấy cardinality từ metadata của nguồn | Xem `SIZED` và các bước thay đổi cardinality |
| `peek(...).count()` luôn in mọi phần tử | `peek` có thể không được đánh giá | Chỉ dùng `peek` để quan sát, không thực thi nghiệp vụ |
| `map(...).count()` buộc chạy logic `map` | `map` giữ nguyên số lượng nên có thể bỏ qua | Không để validation/side effect bắt buộc trong `map` trước `count` |
| `filter(...).count()` bằng `Collection.size()` | Filter có thể loại phần tử | Đếm kết quả sau filter |
| `count()` luôn nhanh hơn `size()` | Khác mục đích và cấu trúc API | Chỉ đếm Collection thì cân nhắc `size()` |
| `limit(5).count()` chứng minh đã xử lý năm phần tử | Cardinality và số callback khác nhau | Không dùng count để kiểm soát số callback |
| `count()` trả `int` | API trả `long` | Khai báo `long count` |
| Có `parallelStream` thì callback chắc chắn chạy đa luồng | Pipeline có thể tối ưu bỏ qua xử lý | Không suy luận thread từ kết quả count |
| Dùng Stream đã tiêu thụ lần hai | Terminal operation kết thúc vòng đời Stream | Tạo Stream mới từ nguồn |
| Nguồn thay đổi đồng thời nhưng vẫn mong số lượng ổn định | Vi phạm hoặc nằm ngoài contract một số nguồn | Ổn định nguồn hoặc dùng cấu trúc/concurrency phù hợp |

### 13.1. Một Stream chỉ dùng cho một terminal operation

~~~java
Stream<String> stream = List.of("A", "B").stream();
long count = stream.count(); // 2

// Không hợp lệ khi chạy vì Stream đã tiêu thụ:
// List<String> again = stream.toList();
~~~

Đoạn này là minh họa trong một phương thức, cần import `java.util.stream.Stream` và `java.util.List`. Nếu cần cả số lượng và danh sách giá trị, hãy cân nhắc lấy danh sách rồi đếm `list.size()`, hoặc tạo Stream mới từ nguồn cho tác vụ riêng.

## 14. Bài tập tự kiểm tra

**Bài 1.** Cho `List.of(1,2,3,4)`, kết quả của `stream().map(x -> x*10).count()` là gì? `map` bắt buộc chạy bốn lần không?

**Đáp án:** 4. Không có bảo đảm callback chạy bốn lần; Java có thể biết cardinality của nguồn và `map` không đổi số lượng.

**Bài 2.** Vì sao `List.of("a","bb","ccc").stream().filter(s -> s.length() > 1).count()` không thể lấy ngay số lượng 3 từ List?

**Đáp án:** vì `filter` có thể loại phần tử theo nội dung. Kết quả chính xác là 2, không phải 3.

**Bài 3.** `List.of(1,2,3,4,5).stream().skip(2).limit(2).count()` trả gì?

**Đáp án:** 2. Bỏ hai phần tử đầu còn ba, sau đó giới hạn hai. Có thể tính cardinality từ kích thước biết trước.

**Bài 4.** Nếu `peek(System.out::println).count()` trên một List không in gì, đó có phải lỗi Java không?

**Đáp án:** Không. API cho phép bỏ qua việc duyệt phần tử nếu đếm trực tiếp được; do đó `peek` không phải công cụ đảm bảo in từng phần tử trong trường hợp này.

**Bài 5.** Vì sao không nên viết `stream.map(this::sendEmail).count()` để gửi email cho toàn bộ phần tử?

**Đáp án:** `count` có thể không gọi `map`, vì `map` không thay đổi số lượng. Gửi email là side effect bắt buộc và phải được thiết kế bằng API/hợp đồng thực thi phù hợp.

**Bài 6.** `IntStream.range(0, 100).count()` cần trả bao nhiêu?

**Đáp án:** 100. Nguồn khoảng số có kích thước chính xác theo hai đầu mút.

**Bài 7.** Một Stream vô hạn từ `Stream.generate(...)` gọi `count()` mà không có giới hạn sẽ thế nào?

**Đáp án:** không có số lượng hữu hạn để hoàn tất bình thường. Cần giới hạn hoặc một cơ chế chấm dứt phù hợp nếu muốn nhận kết quả.

**Bài 8.** Một dòng báo `mapped=0` trong thí nghiệm có đủ để kết luận mọi JDK luôn bỏ qua `map` khi đếm không?

**Đáp án:** Không. Đó là hành vi thực nghiệm của implementation và pipeline cụ thể. Hợp đồng chỉ cho phép tối ưu bỏ qua những công việc không ảnh hưởng kết quả count.

## 15. Tài liệu tham khảo

- [Java SE 17 API — Stream.count() và API Note về bỏ qua thực thi pipeline](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).
- [Java SE 17 API — Spliterator.SIZED và getExactSizeIfKnown()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Java SE 17 API — IntStream.count()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#count()).
- [Java SE 17 API — Stream.peek()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#peek(java.util.function.Consumer)).
- [Java SE 17 API — Stream pipeline và side effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

**Ghi nhớ:** `count()` đếm phần tử **của kết quả Stream**, không chứng minh callback đã thực thi bao nhiêu lần. Nguồn biết chính xác kích thước cộng với các bước giữ nguyên số phần tử như `map`/`peek` có thể cho phép Java trả kết quả mà không duyệt. Ngược lại, các bước như `filter` và `flatMap` thường làm số lượng phụ thuộc vào dữ liệu. Hãy chọn `count()` để **đếm**, không dùng nó như cách bắt buộc chạy validation, logging hoặc side effect.
