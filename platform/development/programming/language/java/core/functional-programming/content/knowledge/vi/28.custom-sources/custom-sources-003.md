# Spliterator.estimateSize() và kích thước chính xác khi được biết trong Java

## 1. Vì sao kích thước của nguồn Stream lại quan trọng?

Khi tự viết **nguồn dữ liệu cho Java Stream**, việc cung cấp từng phần tử chưa đủ. Stream framework còn cần biết **có thể còn bao nhiêu phần tử** để quyết định cách chia công việc, dành chỗ lưu kết quả và, trong một số pipeline, tính kết quả mà không cần duyệt từng phần tử.

Interface `java.util.Spliterator<T>` — viết tắt của *splitable iterator* — có hai phương thức liên quan trực tiếp:

~~~java
long estimateSize();
long getExactSizeIfKnown();
~~~

Đó là **chữ ký API để đối chiếu**, không phải hai phương thức cần tự khai báo ở cấp file. `estimateSize()` là phương thức mà một Spliterator phải cung cấp; `getExactSizeIfKnown()` có triển khai mặc định trong interface.

Chúng trả lời hai câu hỏi **khác nhau**:

- **`estimateSize()`:** “Tôi ước lượng còn bao nhiêu phần tử có thể gặp nếu tiếp tục duyệt Spliterator này?”
- **`getExactSizeIfKnown()`:** “Theo hợp đồng đặc tính của Spliterator, tôi có được phép khẳng định chính xác số phần tử còn lại không?”

Ví dụ với một `List` bất biến chứa bốn phần tử:

~~~java
Spliterator<Integer> sp = List.of(10, 20, 30, 40).spliterator();

System.out.println(sp.estimateSize());          // 4
System.out.println(sp.getExactSizeIfKnown());   // 4
~~~

Đoạn này cần import `java.util.List` và `java.util.Spliterator`, đặt trong một phương thức. Với Spliterator của List này, đặc tính `SIZED` được công bố và kích thước 4 được biết chính xác.

Ngược lại, một nguồn đọc dần từ iterator, file, socket hoặc generator có thể không biết còn bao nhiêu phần tử, ngay cả khi thực tế sẽ kết thúc. Khi đó `estimateSize()` **không phải lời bảo đảm chính xác**, và `getExactSizeIfKnown()` thường trả `-1`.

**Mục tiêu bài học:** hiểu chính xác hợp đồng của `estimateSize()`, đặc tính `SIZED`/`SUBSIZED`, những thay đổi sau `tryAdvance()` và `trySplit()`, cách tạo Stream từ Spliterator tự viết và hậu quả khi khai báo kích thước sai.

## 2. Vai trò của Spliterator trong nguồn tùy chỉnh

Một `Spliterator<T>` kết hợp hai năng lực:

1. **Traversal**: lần lượt cung cấp phần tử cho action bằng `tryAdvance(Consumer)` hoặc `forEachRemaining(Consumer)`.
2. **Partitioning**: tùy khả năng, tách một phần nguồn thành Spliterator khác bằng `trySplit()` để xử lý có thể song song.

Thêm vào đó, Spliterator công bố:
- `estimateSize()`: ước lượng số phần tử còn lại.
- `characteristics()`: các bit mô tả nguồn và tính chất phần tử, ví dụ `ORDERED`, `SIZED`, `SUBSIZED`.
- `getExactSizeIfKnown()`: giá trị chính xác nếu `SIZED` được khai báo; nếu không, mặc định `-1`.
- `hasCharacteristics(flags)`: kiểm tra các bit đặc tính yêu cầu.

Có thể hình dung:

~~~text
Nguồn tùy chỉnh: dãy số 0,1,2,3,4,5,6,7
                     |
            IntRangeSpliterator
       current=0, fence=8, size=8
                /         \
       trySplit()         phần còn lại
          |                    |
      [0,1,2,3]           [4,5,6,7]
      size=4                size=4
          \                    /
           Stream có thể chia việc
                      |
                terminal op
~~~

Đây là mô hình chia nguồn thành hai nửa, **không phải lịch chạy thread được bảo đảm**. Phần quan trọng là số phần tử của hai Spliterator sau chia phải **phù hợp với số phần tử trước chia** khi tuyên bố `SUBSIZED`.

### 2.1. Spliterator khác Iterator ở điều gì?

`Iterator<T>` chủ yếu cung cấp `hasNext()` và `next()` để duyệt tuần tự. Nó không có hợp đồng tổng quát yêu cầu biết kích thước còn lại và không cung cấp phương thức chia nguồn tương đương `trySplit()`.

`Spliterator<T>` có thể:
- Duyệt tuần tự bằng `tryAdvance`.
- Chia nguồn thành những Spliterator độc lập thích hợp để parallel processing.
- Công bố metadata về thứ tự, tính duy nhất, kích thước, tính bất biến...
- Giúp framework tối ưu các phép toán chỉ cần số lượng hoặc phân hoạch nguồn.

Không phải Spliterator nào cũng chia được: `trySplit()` được phép trả `null` khi không còn phần hợp lý để tách hoặc do đặc tính nguồn.

## 3. estimateSize() thực sự cam kết điều gì?

Chữ ký:

~~~java
long estimateSize();
~~~

Theo API Java SE 17, phương thức trả về **ước lượng số phần tử** sẽ gặp khi duyệt hết những phần tử còn lại, hoặc trả `Long.MAX_VALUE` khi nguồn vô hạn, không biết kích thước hoặc việc xác định quá tốn kém.

Ba tình huống:

| Nguồn/Spliterator | estimateSize() có thể là | Có nhất thiết chính xác? |
| --- | --- | --- |
| List ổn định được khai báo SIZED | 4 nếu còn 4 phần tử | Có, theo điều kiện hợp đồng SIZED |
| Dãy int hữu hạn tự viết với current/fence rõ ràng | `fence - current` | Có, nếu cài đặt và đặc tính đúng |
| Iterator không có kích thước công bố | `Long.MAX_VALUE` | Không; đây là sentinel cho “không biết” |
| Nguồn có thể thay đổi nhưng không có bảo đảm kích thước | Một con số ước lượng | Không nên coi là count chính xác |
| Nguồn thực sự vô hạn | `Long.MAX_VALUE` | Không phải số lượng hữu hạn chính xác |

Lưu ý: **ước lượng có ích dù không chính xác**. Một framework song song có thể sử dụng ước lượng để cân nhắc chia nhỏ công việc. Nhưng ước lượng không phải bằng chứng có đúng từng đó phần tử và không tự biến thành lời hứa về tốc độ.

### 3.1. “Còn lại” chứ không phải tổng ban đầu

Nếu Spliterator có tám phần tử và ta đã lấy một phần tử thành công bằng `tryAdvance()`, thì về mặt logic chỉ còn bảy phần tử. Với một custom Spliterator được khai báo `SIZED/SUBSIZED` và tự cập nhật cursor chính xác, `estimateSize()` phải phản ánh lượng phần tử còn lại, không giữ nguyên tám mãi.

Ví dụ thiết kế:

~~~java
// Ví dụ logic trong custom Spliterator:
public long estimateSize() {
    return (long) fence - current;
}
~~~

Đây là **phần phương thức đặt bên trong class**, không phải chương trình độc lập. `fence` là chỉ số kết thúc **exclusive**, `current` là chỉ số phần tử kế tiếp sẽ được cung cấp.

Nếu `current=5` và `fence=8`, kích thước còn lại là 3, dù nguồn gốc có thể từng có 8 phần tử.

### 3.2. Long.MAX_VALUE không phải số lượng thật

Khi kích thước không biết, API cho phép:

~~~java
return Long.MAX_VALUE;
~~~

Đây là **ví dụ biểu thức return bên trong phương thức estimateSize()**. Giá trị `9_223_372_036_854_775_807` được dùng như một tín hiệu **unknown/infinite/too expensive**, không có nghĩa Stream thực sự sẽ tạo hơn chín tỷ tỷ phần tử.

Tuyệt đối tránh:

~~~java
// PHẢN VÍ DỤ: không xem estimateSize như kích thước mảng đã được chứng minh.
// int capacity = (int) spliterator.estimateSize();
// Object[] output = new Object[capacity];
~~~

Nó có thể làm tràn khi ép `long` sang `int`, cấp phát vô nghĩa hoặc dùng ước lượng không đúng. Nếu cần kích thước chính xác, kiểm tra `getExactSizeIfKnown()` và xử lý trường hợp `-1`; kể cả khi biết số phần tử, vẫn cần kiểm tra giới hạn bộ nhớ/cấp phát.

## 4. SIZED — khi nào được gọi là kích thước chính xác?

`Spliterator.SIZED` là một **characteristic flag**. Nó mô tả rằng số phần tử được báo bởi Spliterator là **chính xác trong những điều kiện hợp đồng áp dụng**, điển hình là khi chưa duyệt/chia và nguồn không bị can thiệp trái phép.

Các hằng số đặc tính được kết hợp bằng phép OR bit:

~~~java
int flags = Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED
        | Spliterator.IMMUTABLE
        | Spliterator.NONNULL;
~~~

Đoạn minh họa cần import `java.util.Spliterator`.

Không nên đánh dấu `SIZED` chỉ vì **ước đoán gần đúng** hoặc vì biết kích thước của một mảng khác với nguồn đang thực sự cung cấp. Muốn khai báo `SIZED`, implementation phải bảo đảm giá trị phù hợp với các phần tử sẽ được duyệt theo hợp đồng.

### 4.1. getExactSizeIfKnown() dựa trên SIZED, không dựa vào may mắn

Triển khai mặc định trong interface về mặt ý nghĩa tương đương:

~~~java
default long getExactSizeIfKnown() {
    return (characteristics() & SIZED) == 0 ? -1L : estimateSize();
}
~~~

Đây là **đoạn diễn giải của method mặc định trong Spliterator**; từ `SIZED` là hằng số của chính interface.

Hệ quả:

- Nếu **có** `SIZED`, `getExactSizeIfKnown()` gọi `estimateSize()` và trả giá trị ấy.
- Nếu **không có** `SIZED`, mặc định trả `-1` **ngay cả khi** `estimateSize()` tình cờ bằng số phần tử thật.
- Việc `getExactSizeIfKnown()` trả số dương là **sự tin tưởng vào đặc tính của Spliterator**, không phải phép kiểm tra độc lập bằng cách duyệt tất cả phần tử.

Đây là lý do viết `estimateSize()` và `characteristics()` phải **nhất quán**. Một lời khai `SIZED` sai có thể làm Stream framework cho ra kết quả sai vì nó được phép tin metadata đó.

### 4.2. Không có SIZED không đồng nghĩa estimateSize vô ích

Một Spliterator **không có SIZED** vẫn có thể trả một ước lượng hữu hạn để phục vụ quyết định chia nguồn. Tuy nhiên, downstream client không thể suy rằng con số ấy là exact chỉ bằng việc nó trông hợp lý.

Nếu nguồn là iterator không có khả năng tính số lượng rẻ hoặc đang đọc dữ liệu đến khi hết, trả `Long.MAX_VALUE` là lựa chọn hợp lệ thay vì cố duyệt hết chỉ để tính kích thước. Việc tự duyệt nguồn để đếm có thể **tiêu thụ dữ liệu**, làm mất phần tử cho những bước sau hoặc tăng I/O không cần thiết.

## 5. SUBSIZED — kích thước chính xác ngay cả sau khi chia

`SUBSIZED` là đặc tính **mạnh hơn SIZED**. Nó có nghĩa Spliterator này và **tất cả Spliterator được tạo từ nó bằng `trySplit()`** đều đáp ứng `SIZED` và `SUBSIZED`.

Với dãy tám phần tử:

~~~text
Trước chia: [0,1,2,3,4,5,6,7]  estimateSize=8

Sau trySplit():
  prefix:     [0,1,2,3]       estimateSize=4
  remainder:  [4,5,6,7]       estimateSize=4

Tổng kích thước sau chia: 4 + 4 = 8
~~~

Với custom Spliterator khai báo `SUBSIZED` và kiểm soát phạm vi rõ ràng, ta phải bảo đảm quan hệ này. Duyệt thêm một phần tử của prefix sẽ khiến kích thước prefix giảm từ 4 xuống 3.

### 5.1. SIZED không tự động đồng nghĩa SUBSIZED

**SIZED** nói đến độ chính xác kích thước theo điều kiện của Spliterator; nó không tự nói tất cả phần chia con cũng có thông tin exact. **SUBSIZED** bổ sung bảo đảm cho các Spliterator con và việc chia tiếp.

Do đó không được bật `SUBSIZED` theo thói quen. Chỉ dùng nếu:
- Mỗi phần dữ liệu được tách là rời nhau, không bỏ/lặp phần tử.
- Mỗi phần chia mới có khả năng báo chính xác số lượng phần tử còn lại.
- Việc chia tiếp không làm mất cam kết trên.
- Các bit đặc tính và số lượng vẫn nhất quán sau các thao tác được phép.

Một số nguồn khó chia đều hoặc chỉ biết số lượng trước lần chia có thể khai báo `SIZED` mà không thể hứa `SUBSIZED` một cách đúng đắn.

### 5.2. Spliterator có thể không chia được

`trySplit()` được phép trả `null`. Điều đó có thể xảy ra vì Spliterator đã rỗng, chỉ còn một phần tử, thuật toán không có điểm chia hợp lý hoặc chi phí chia quá cao.

Không được diễn giải `trySplit()==null` là “nguồn có kích thước bằng 0” hay “nguồn đã hỏng”; nó chỉ cho biết không có phần nguồn nào được tách ra trong lời gọi ấy.

### 5.3. Với ORDERED, phần tách ra phải đúng ý nghĩa prefix

Khi nguồn có encounter order và khai báo `ORDERED`, `trySplit()` trên Spliterator phù hợp thường trả một **prefix** của các phần tử còn lại, còn instance gốc tiếp tục giữ phần **suffix**.

Trong ví dụ dãy số 0 đến 7:
- Spliterator trả về sau `trySplit()` giữ 0 đến 3.
- Instance gốc sau split giữ 4 đến 7.

Nếu không duy trì đúng thứ tự phân đoạn, một stream có thứ tự có thể cho kết quả sai với thao tác như `findFirst()`, `limit()` hoặc `toList()`.

## 6. Thiết kế custom Spliterator.OfInt có kích thước xác định

Ta triển khai một nguồn dãy nguyên **[start, end)** với end exclusive. Để tránh boxing và tận dụng API chuyên dụng, dùng `Spliterator.OfInt` và `IntConsumer`:

~~~java
static final class IntRangeSpliterator implements Spliterator.OfInt {
    private int current;
    private final int fence;
    private final AtomicInteger advances;

    IntRangeSpliterator(int start, int end, AtomicInteger advances) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.current = start;
        this.fence = end;
        this.advances = Objects.requireNonNull(advances);
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action);
        if (current >= fence) return false;
        int value = current++;
        advances.incrementAndGet();
        action.accept(value);
        return true;
    }

    @Override
    public OfInt trySplit() {
        int lo = current;
        int mid = lo + ((fence - lo) >>> 1);
        if (mid == lo) return null;
        current = mid;
        return new IntRangeSpliterator(lo, mid, advances);
    }

    @Override
    public long estimateSize() {
        return (long) fence - current;
    }

    @Override
    public int characteristics() {
        return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                | NONNULL | IMMUTABLE;
    }

    @Override
    public java.util.Comparator<? super Integer> getComparator() {
        return null;
    }
}
~~~

Đây là **toàn bộ khai báo class lồng cần đặt bên trong một class bao ngoài**. Import cần thiết: `java.util.Spliterator`, `java.util.Objects`, `java.util.concurrent.atomic.AtomicInteger` và `java.util.function.IntConsumer`. Chương trình Java 17 độc lập, có wrapper class và `main`, ở phần 10.

### 6.1. Vai trò của từng thành phần

**`current`** là phần tử tiếp theo có thể được cấp; **`fence`** là cận kết thúc exclusive. Mỗi lần thành công, `tryAdvance` tăng `current` nên kích thước còn lại giảm đúng một đơn vị.

**`trySplit()`** tính điểm giữa phạm vi còn lại. Nếu đã đến mức không tách được, trả `null`. Nếu tách được, nó cập nhật instance hiện tại thành nửa sau và trả một instance mới đại diện cho nửa đầu.

**`estimateSize()`** trả `fence-current` chính xác vì nguồn này là khoảng số hữu hạn, không bị chỉnh sửa bởi ai khác. Trong ví dụ, constructor giới hạn `start >= 0` và `end >= start` nên phép tính chia nửa dựa trên hiệu hai chỉ số không có tràn số do khoảng có thứ tự và nằm trong miền int không âm.

**`advances`** chỉ là bộ đếm instrumentation để kiểm tra thử nghiệm; nó không quyết định giá trị phần tử và không được dùng thay thế kích thước thực sự của nguồn. Nó là AtomicInteger vì thử nghiệm song song có thể gọi các Spliterator khác nhau từ nhiều thread.

### 6.2. Vì sao khai báo các characteristic đó?

| Bit | Có hợp lý với dãy số ví dụ? | Giải thích |
| --- | --- | --- |
| `ORDERED` | Có | Dãy tăng từ start tới end-1; phân đoạn trả về là prefix |
| `DISTINCT` | Có | Mỗi giá trị trong khoảng xuất hiện đúng một lần |
| `SORTED` | Có | Các số tăng dần theo natural ordering |
| `SIZED` | Có | Số phần tử còn lại đúng bằng fence-current |
| `SUBSIZED` | Có | Cả hai nửa và mọi lần chia tiếp đều có kích thước exact |
| `NONNULL` | Có | Nguồn nguyên thủy không sinh tham chiếu null |
| `IMMUTABLE` | Có | Nội dung miền số được sinh từ khoảng cố định, không có cấu trúc nguồn mutable bên ngoài |
| `CONCURRENT` | Không khai báo | Không thiết kế để nhiều thread cùng duyệt/chia một instance |
 
`SORTED` có một yêu cầu bổ sung: `getComparator()` cần phù hợp với thứ tự; với natural order, trả `null`. Nếu bạn khai báo `SORTED` nhưng kế thừa implementation `getComparator()` ném exception mặc định không phù hợp, client có thể gặp lỗi. Trong ví dụ, phương thức được override rõ ràng.

**Chỉ khai báo những thuộc tính có thể chứng minh.** Không thêm `DISTINCT` nếu nguồn có duplicate, `SORTED` nếu dữ liệu không sắp, hoặc `IMMUTABLE` nếu nội dung nguồn có thể bị sửa theo cách trái hợp đồng.

### 6.3. Một chú ý về đơn vị đo

`estimateSize()` đo **số phần tử sẽ được duyệt**, không đo số byte, không đo số object Java được cấp phát, không đo độ dài của chuỗi ký tự, và không đo số bước CPU.

Ví dụ một phần tử String có một triệu ký tự vẫn **tính là một phần tử**. Nếu một `flatMap` tạo nhiều phần tử từ một String, kích thước sau `flatMap` có thể hoàn toàn khác với số phần tử String nguồn.

## 7. Nguồn không biết kích thước: spliteratorUnknownSize()

Java cung cấp helper:

~~~java
Spliterator<Integer> unknown =
        Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED);
~~~

Đây là mã minh họa trong phương thức có biến `iterator` và import `java.util.Spliterator`/`Spliterators`. Helper nhận `Iterator<? extends T>` và bit characteristics. Nó **không** giả định biết kích thước của iterator.

Ví dụ có một Iterator trên List bốn phần tử:

~~~java
Iterator<Integer> it = List.of(10, 20, 30, 40).iterator();
Spliterator<Integer> sp =
        Spliterators.spliteratorUnknownSize(it, Spliterator.ORDERED);

System.out.println(sp.estimateSize());         // Long.MAX_VALUE
System.out.println(sp.getExactSizeIfKnown());  // -1
~~~

Đây là đoạn minh họa cần import `java.util.Iterator`, `List`, `Spliterator`, `Spliterators`. Mặc dù lập trình viên **biết List gốc** có bốn phần tử, adapter chỉ được cung cấp một Iterator và một bộ đặc tính không khai báo SIZED. Theo kết quả kiểm thử Java 17:
- `estimateSize()` trả `Long.MAX_VALUE`.
- `getExactSizeIfKnown()` trả `-1`.
- `SIZED` không được khai báo.
- Duyệt Stream từ Spliterator này để `count()` phải xác định số lượng thực tế; trong ví dụ, đã gọi `next()` bốn lần.

### 7.1. Vì sao hai nguồn có cùng dữ liệu nhưng metadata khác?

`List.spliterator()` có thể báo kích thước vì List có API `size()`. Ngược lại, chỉ riêng interface `Iterator` không có `size()`; helper unknown-size không được phép đoán size bằng cách âm thầm tiêu thụ Iterator.

Điều đó cho thấy metadata thuộc về **hợp đồng nguồn/Spliterator** chứ không chỉ thuộc về “số phần tử có mặt trong thế giới thực”.

### 7.2. Khi cần biết kích thước, có nên đếm bằng cách duyệt trước?

Không phải lúc nào cũng hợp lý. Với iterator đọc một lần từ file hoặc network, việc duyệt để đếm có thể **tiêu thụ nguồn**. Muốn xử lý lại cần rewind/mở lại kết nối hoặc lưu dữ liệu vào bộ nhớ, gây thêm tài nguyên.

Trong nhiều hệ thống, cứ khai báo không biết kích thước, để Stream duyệt khi cần là đúng. Chỉ công bố `SIZED` nếu thực sự có khả năng tính chính xác mà không làm hỏng semantics traversal.

## 8. getExactSizeIfKnown() khác gì với count()?

Hai lời gọi này ở **hai tầng abstraction khác nhau**:

~~~java
long known = spliterator.getExactSizeIfKnown();

long result = StreamSupport.stream(spliterator, false)
        .count();
~~~

Đoạn minh họa trên cần import `java.util.stream.StreamSupport` và biến `spliterator`. **Không nên chạy đúng hai dòng này trên cùng instance đã tiêu thụ ở nơi khác**; trong ví dụ đầu, lời gọi truy vấn size không tiêu thụ phần tử, còn terminal operation `count` sẽ hoàn tất vòng đời Stream.

| Thuộc tính | `getExactSizeIfKnown()` | `Stream.count()` |
| --- | --- | --- |
| Đối tượng | Spliterator | Stream pipeline |
| Giá trị trả | Size còn lại khi SIZED, hoặc `-1` | Số phần tử **kết quả pipeline**, kiểu long |
| Có nhất thiết duyệt phần tử? | Không trong default method; dựa trên characteristics/estimate | Không nhất thiết; có thể duyệt hoặc suy ra |
| Có tính `filter`/`flatMap` không? | Không, chỉ metadata nguồn Spliterator | Có, theo ngữ nghĩa pipeline |
| Có thể dùng với nguồn unknown-size? | Trả `-1` nếu không SIZED | Có, thường duyệt để đếm |
| Đối với nguồn Stream vô hạn | Có thể unknown | Nếu không hạn chế, có thể không kết thúc |

**Ví dụ:** custom source có năm số [0,1,2,3,4]. `getExactSizeIfKnown()` trả 5. Nhưng pipeline `filter(v -> v % 2 == 0).count()` trả 3 vì sau filter chỉ còn [0,2,4].

Đừng dùng kích thước **nguồn** để thay thế số lượng **sau các phép biến đổi có thể thay đổi cardinality**.

### 8.1. count() có thể tận dụng SIZED để tối ưu

Nếu Stream framework tin metadata SIZED và các thao tác trung gian giữ nguyên số lượng, nó có thể trả count mà **không gọi tryAdvance trên từng phần tử**.

Ví dụ:

~~~java
AtomicInteger visits = new AtomicInteger();

long count = StreamSupport.intStream(
        new IntRangeSpliterator(0, 5, visits), false)
        .map(v -> v * 2)
        .count();
~~~

Đây là **mã minh họa trong phương thức**, cần class `IntRangeSpliterator` ở phần 6, import `AtomicInteger` và `StreamSupport`.

Trong thí nghiệm JDK 17:
- `count = 5`.
- `visits.get() = 0`.

Đó là một tối ưu hợp lệ: `map` là thao tác một phần tử vào/một phần tử ra, nên số phần tử cuối vẫn là 5. **Không được đặt tác dụng phụ bắt buộc trong `tryAdvance` hoặc `map` rồi dựa vào count để kích hoạt chúng.**

Đây không phải hợp đồng rằng mọi JDK luôn tối ưu theo một cách; chỉ có kết quả cuối của pipeline, trong điều kiện các đặc tính được khai báo **đúng**, mới là điều phải đúng theo API.

### 8.2. Filter có thể khiến framework phải duyệt

~~~java
AtomicInteger visits = new AtomicInteger();

long evenCount = StreamSupport.intStream(
        new IntRangeSpliterator(0, 5, visits), false)
        .filter(v -> v % 2 == 0)
        .count();
~~~

Trong cùng thí nghiệm:
- `evenCount = 3` vì [0,2,4].
- `visits.get() = 5` vì cần xét tất cả giá trị trong nguồn ví dụ để quyết định ba giá trị hợp lệ.

Dù source Spliterator là SIZED, thao tác `filter` **có thể làm số phần tử đầu ra thay đổi**; do đó không thể dùng con số 5 từ source như kết quả cuối của pipeline đã lọc.

**Điểm học quan trọng:** `SIZED` có nghĩa chính xác **ở tầng nguồn đang được mô tả**, không có nghĩa “mọi phép biến đổi trong Stream đều biết sẵn số lượng kết quả”.

## 9. Những sai lầm nghiêm trọng khi tự viết estimateSize()

### 9.1. Báo SIZED nhưng trả size lớn hơn thực tế

Giả sử nguồn chỉ phát được 3 phần tử nhưng `estimateSize()` luôn trả 100 và `characteristics()` khai báo `SIZED`. Đây là sự **vi phạm hợp đồng**. Framework có thể tin metadata để dành chỗ, sắp xếp, hoặc tối ưu count, dẫn đến số lượng báo cáo sai hay lỗi khác.

Điểm nguy hiểm nằm ở chỗ test “duyệt forEach được ba phần tử” có thể vẫn qua, trong khi test `count()` có thể cho kết quả khác. Không nên coi kết quả đúng của một terminal operation là bằng chứng mọi characteristic đã khai báo đều chính xác.

### 9.2. Không giảm estimate sau tryAdvance

Nếu đã cấp phát một phần tử nhưng `estimateSize()` giữ nguyên, số liệu “remaining” sai. Với custom Spliterator khai báo SIZED/SUBSIZED, đó là vi phạm quan trọng, nhất là nếu framework hỏi kích thước sau khi duyệt một phần.

Mô hình đúng với khoảng số:

~~~java
// Bên trong custom Spliterator:
if (current < fence) {
    int element = current++;
    action.accept(element);
    return true;
}
return false;
~~~

Và phương thức kích thước phải dựa trên cursor đã tiến lên:

~~~java
public long estimateSize() {
    return (long) fence - current;
}
~~~

Hai đoạn là **minh họa phần phương thức**, không phải file độc lập.

### 9.3. Chia trùng hoặc bỏ phần tử nhưng vẫn khai SUBSIZED

Nếu `trySplit()` trả prefix 0–4 nhưng remainder vẫn bắt đầu từ 4 (và cả hai đều chứa 4), dữ liệu có thể bị trùng. Nếu remainder bắt đầu từ 6 sau prefix 0–4, dữ liệu 5 sẽ bị mất.

Ngay cả khi tổng hai `estimateSize()` trông bằng kích thước ban đầu, các phần có thể **không thực sự rời nhau và bao phủ hết nguồn**. Do đó test cần kiểm tra cả **các giá trị được phát ra**, không chỉ số lượng.

### 9.4. Khai SORTED mà không có comparator phù hợp

`SORTED` là một lời khai về thứ tự tự nhiên hoặc comparator. Nếu đặc tính này được công bố, cần bảo đảm `getComparator()` phù hợp. Với dãy int tăng dần, trả `null` là chỉ dấu natural ordering. Với thứ tự tùy chỉnh, comparator phải nhất quán với traversal.

Khai `SORTED` cho dãy ngẫu nhiên chỉ để Stream chạy nhanh hơn là không hợp lệ.

### 9.5. Thay đổi nguồn sau khi đã công bố size

Với nguồn mutable hoặc được ghi đồng thời, “size đúng vào lúc tạo Spliterator” chưa đủ nếu source thay đổi trái hợp đồng trước/trong traversal. Nếu không thể đảm bảo nguồn ổn định, cần cài đặt chính sách **late-binding**, fail-fast, snapshot hoặc concurrent characteristics phù hợp.

`StreamSupport.stream(spliterator, false)` được thiết kế để Stream chỉ duyệt/chia/truy vấn kích thước sau khi terminal operation bắt đầu; tuy vậy, điều này **không tự thay thế** hợp đồng đồng bộ và binding của custom source.

### 9.6. Tự mở một cuộc duyệt để đo estimateSize

Sai về mặt thiết kế nếu `estimateSize()` gọi `tryAdvance()` liên tục để đếm: nó sẽ tiêu thụ phần tử, làm thay đổi trạng thái nguồn, phá vỡ kỳ vọng chỉ truy vấn metadata. Với nguồn không có exact size, hãy trả ước lượng hoặc `Long.MAX_VALUE`, thay vì làm hỏng traversal.

### 9.7. Nhầm “có SUBSIZED” với “tự động chạy nhiều thread”

`SUBSIZED` giúp framework chia và biết kích thước; nó không buộc `parallelStream` phải tạo một thread trên mỗi phần, không đảm bảo tăng tốc và không biến Spliterator thành đối tượng thread-safe.

Mỗi instance Spliterator thường cần được **giới hạn quyền sở hữu theo thread**; trong parallel splitting, một instance con có thể được bàn giao cho thread khác, nhưng không nên để nhiều thread cùng gọi `tryAdvance`/`trySplit` trên cùng instance khi implementation không hỗ trợ.

## 10. Chương trình Java 17 hoàn chỉnh, đã biên dịch và chạy

Tạo tệp **SpliteratorSizeDemo.java**. Chương trình có hai loại nguồn:

- `IntRangeSpliterator` tự viết, khai báo SIZED + SUBSIZED và có thể chia đôi.
- `spliteratorUnknownSize` tạo Spliterator từ Iterator nhưng không công bố kích thước exact.

Các bộ đếm `AtomicInteger` chỉ đo hành vi traversal trong **lần chạy thử**, không tạo ra lời hứa về số lần `tryAdvance` bắt buộc trong mọi pipeline.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class SpliteratorSizeDemo {
    static final class IntRangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;
        private final AtomicInteger advances;

        IntRangeSpliterator(int start, int end, AtomicInteger advances) {
            if (start < 0 || end < start) {
                throw new IllegalArgumentException("Invalid range");
            }
            this.current = start;
            this.fence = end;
            this.advances = Objects.requireNonNull(advances);
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (current >= fence) return false;
            int value = current++;
            advances.incrementAndGet();
            action.accept(value);
            return true;
        }

        @Override
        public OfInt trySplit() {
            int lo = current;
            int mid = lo + ((fence - lo) >>> 1);
            if (mid == lo) return null;
            current = mid;
            return new IntRangeSpliterator(lo, mid, advances);
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED | SUBSIZED
                    | NONNULL | IMMUTABLE;
        }

        @Override
        public java.util.Comparator<? super Integer> getComparator() {
            return null;
        }
    }

    static final class CountingIterator implements Iterator<Integer> {
        private final Iterator<Integer> delegate;
        int nextCalls;

        CountingIterator(List<Integer> source) {
            this.delegate = source.iterator();
        }
        @Override
        public boolean hasNext() {
            return delegate.hasNext();
        }
        @Override
        public Integer next() {
            nextCalls++;
            return delegate.next();
        }
    }

    public static void main(String[] args) {
        Spliterator<Integer> list = List.of(10, 20, 30, 40).spliterator();
        System.out.println("list estimate=" + list.estimateSize()
                + ", exact=" + list.getExactSizeIfKnown()
                + ", sized=" + list.hasCharacteristics(Spliterator.SIZED));

        AtomicInteger splitAdvances = new AtomicInteger();
        IntRangeSpliterator range = new IntRangeSpliterator(0, 8, splitAdvances);
        System.out.println("range initial=" + range.estimateSize());
        Spliterator.OfInt prefix = range.trySplit();
        System.out.println("split prefix=" + prefix.estimateSize()
                + ", remainder=" + range.estimateSize());
        prefix.tryAdvance((int v) ->
                System.out.println("first from prefix=" + v));
        System.out.println("prefix after advance=" + prefix.estimateSize()
                + ", exact=" + prefix.getExactSizeIfKnown());

        CountingIterator iterator = new CountingIterator(
                List.of(10, 20, 30, 40));
        Spliterator<Integer> unknown = Spliterators.spliteratorUnknownSize(
                iterator, Spliterator.ORDERED);
        System.out.println("unknown estimate=" + unknown.estimateSize()
                + ", exact=" + unknown.getExactSizeIfKnown()
                + ", sized=" + unknown.hasCharacteristics(Spliterator.SIZED));
        long unknownCount = StreamSupport.stream(unknown, false).count();
        System.out.println("unknown count=" + unknownCount
                + ", next calls=" + iterator.nextCalls);

        AtomicInteger sizedAdvances = new AtomicInteger();
        long size = StreamSupport.intStream(
                new IntRangeSpliterator(0, 5, sizedAdvances), false)
                .map(v -> v * 2)
                .count();
        System.out.println("sized count=" + size
                + ", advances=" + sizedAdvances.get());

        AtomicInteger filteredAdvances = new AtomicInteger();
        long even = StreamSupport.intStream(
                new IntRangeSpliterator(0, 5, filteredAdvances), false)
                .filter(v -> v % 2 == 0)
                .count();
        System.out.println("filtered count=" + even
                + ", advances=" + filteredAdvances.get());
    }
}
~~~

Biên dịch bằng JDK 17:

~~~bash
javac --release 17 SpliteratorSizeDemo.java
java SpliteratorSizeDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
list estimate=4, exact=4, sized=true
range initial=8
split prefix=4, remainder=4
first from prefix=0
prefix after advance=3, exact=3
unknown estimate=9223372036854775807, exact=-1, sized=false
unknown count=4, next calls=4
sized count=5, advances=0
filtered count=3, advances=5
~~~

### 10.1. Giải thích từng kết quả

1. **`list estimate=4, exact=4, sized=true`:** List cung cấp một Spliterator có kích thước chính xác được công bố.
2. **`range initial=8`:** dãy 0..7 có tám phần tử.
3. **`split prefix=4, remainder=4`:** `trySplit()` trả nửa đầu, instance gốc giữ nửa sau. Tổng kích thước sau split bằng 8.
4. **`first from prefix=0`:** nửa đầu bắt đầu ở giá trị 0, đúng encounter order.
5. **`prefix after advance=3, exact=3`:** sau khi cung cấp giá trị 0, prefix chỉ còn ba phần tử. Vì custom Spliterator có SIZED/SUBSIZED và cập nhật cursor đúng, cả hai phương thức trả 3.
6. **`unknown estimate=Long.MAX_VALUE, exact=-1, sized=false`:** wrapper iterator không cung cấp exact-size metadata mặc dù iterator cụ thể sẽ kết thúc sau bốn phần tử.
7. **`unknown count=4, next calls=4`:** trong thử nghiệm tuần tự này, `count()` duyệt qua cả bốn phần tử của nguồn unknown-size.
8. **`sized count=5, advances=0`:** JDK 17 tận dụng size metadata và phép `map` giữ cardinality, không cần duyệt phần tử để đếm.
9. **`filtered count=3, advances=5`:** sau `filter(v -> v%2==0)`, kết quả còn [0,2,4]; JDK 17 đã duyệt toàn bộ năm phần tử trong lần chạy này.

Không suy số lần callback chính xác theo hợp đồng từ dữ liệu instrumentation; chỉ **giá trị count và đặc tính được khai báo đúng** là nền tảng cần dựa vào.

## 11. Kiểm tra độc lập với xử lý song song

Một custom Spliterator có `SUBSIZED` không chỉ cần báo size đúng; nó phải **chia nguồn không mất/lặp phần tử**. Một test bổ sung có thể lấy tổng từ 0 đến 99 bằng Stream song song:

~~~java
AtomicInteger visits = new AtomicInteger();

long total = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100, visits), true)
        .asLongStream()
        .sum();

System.out.println("parallel sum=" + total
        + ", advances=" + visits.get());
~~~

Đoạn minh họa này nằm trong phương thức cùng class `IntRangeSpliterator` và import `AtomicInteger`/`StreamSupport`.

Đã kiểm chứng với `javac --release 17`, stdout:

~~~text
parallel sum=4950, advances=100
~~~

Vì tổng từ 0 đến 99 là `99*100/2 = 4950`, ví dụ giúp kiểm tra thiết kế chia nguồn trong một phép tổng hợp thực tế. Bộ đếm cho thấy 100 lần cung cấp phần tử ở lần thử này. Khi kiểm thử thực tế, nên kiểm tra thêm việc **tập phần tử kết quả đúng chính xác** thay vì chỉ sum/count, bởi nguồn có phần tử mất và trùng có thể tình cờ cho cùng tổng trong một số tập dữ liệu.

### 11.1. Kiểm thử trySplit có hệ thống

Một bộ test tốt cho custom Spliterator nên bao gồm:

- **Nguồn rỗng**: `start=end`, `estimateSize()==0`, `tryAdvance()==false`, `trySplit()==null`.
- **Một phần tử**: có thể `trySplit()==null`; một lần advance thành công, size còn 0.
- **Hai phần tử**: thử chia một và một; xác minh không overlap.
- **Số lẻ**: từ 0 đến 4 có 5 phần tử, chia có thể 2 và 3; không nhất thiết nửa nào có cùng size.
- **Đã advance rồi split**: các phần mới phải chỉ chứa những phần tử **còn lại**, không phát lại phần tử đã lấy.
- **Split nhiều tầng**: nếu khai SUBSIZED, các nhánh tiếp tục biết size exact.
- **Duyệt tuần tự/parallel**: cả hai tạo cùng tập kết quả (và cùng encounter order nếu terminal operation yêu cầu).
- **Count vs filter count**: số sau filter có thể khác kích thước nguồn.
- **Biên số học**: xác minh không tràn số khi tính `mid` và `estimateSize()`; đoạn mẫu giới hạn khoảng không âm để đơn giản.

### 11.2. Đo hiệu năng không phải mục đích của bài thử

Một Stream song song với 100 phần tử có thể không nhanh hơn tuần tự; việc đo ở đây phục vụ **tính đúng** của custom Spliterator và phân đoạn. Nếu benchmark hiệu năng, cần dữ liệu đại diện, JMH hoặc phương pháp thích hợp, chú ý warm-up, thread contention và chi phí thử nghiệm.

## 12. Liên hệ với nguồn mutable, late-binding và non-interference

Tài liệu `StreamSupport` khuyến nghị Spliterator của nguồn tùy chỉnh nên có `IMMUTABLE` hoặc `CONCURRENT`, hoặc là **late-binding**. Nếu không, overload nhận `Supplier<? extends Spliterator<T>>` có thể giúp giảm khoảng thời gian nguồn có thể bị thay đổi trước khi terminal operation bắt đầu.

Những hướng thiết kế:

| Loại nguồn | Thiết kế có thể phù hợp |
| --- | --- |
| Dãy toán học cố định | Immutable, SIZED/SUBSIZED nếu chia chính xác |
| Mảng hoặc List bất biến | Báo SIZED theo nguồn và bảo toàn traversal |
| Collection mutable được duyệt theo snapshot | Snapshot + SIZED nếu kích thước snapshot exact |
| Collection mutable late-binding | Xác định nguồn tại thời điểm bind theo contract |
| Queue concurrent | Dùng nguồn concurrent với đặc tính/thứ tự/số lượng phù hợp, không tự gắn SIZED nếu không bảo đảm |
| Iterator chỉ đọc dần | Có thể dùng unknown-size adapter; không bịa SIZED |
| Generator không giới hạn | Không gắn exact finite size; cần terminal giới hạn nếu muốn hoàn tất |

Nếu dùng overload `StreamSupport.stream(supplier, characteristics, parallel)`, **các characteristic được cung cấp riêng phải khớp** với Spliterator mà supplier tạo ra; nếu không, hành vi có thể không xác định theo hợp đồng. Không truyền `SIZED` cho supplier tạo nguồn unknown-size để “thúc” framework tối ưu.

**Non-interference:** các callback `map`/`filter` không nên sửa nguồn đang được Spliterator duyệt, trừ khi nguồn có contract concurrent phù hợp. Và custom Spliterator nói chung **không tự thread-safe** chỉ vì dùng trong parallel Stream; hệ thống phân chia công việc thường giao từng Spliterator cho một worker tại một thời điểm.

## 13. Checklist trước khi công bố kích thước trong custom Spliterator

Khi tự triển khai `estimateSize()`, hãy tự hỏi:

1. **Tôi đang đo số phần tử còn lại hay tổng ban đầu?** Phải là còn lại theo traversal hiện tại.
2. **Có biết chính xác kích thước không?** Nếu không, không khai `SIZED`.
3. **Nếu không biết, ước lượng có hợp lý không?** Có thể dùng `Long.MAX_VALUE` thay vì cố duyệt để đếm.
4. **`getExactSizeIfKnown()` có trả đúng trên dữ liệu rỗng và sau một lần advance không?** Với custom SIZED, kiểm tra kỹ.
5. **`trySplit()` có chia không trùng, không bỏ sót không?** Kiểm tra dữ liệu, không chỉ tổng size.
6. **Có hứa SUBSIZED không?** Nếu có, mọi nhánh sau chia phải giữ đặc tính và size exact.
7. **Có hứa ORDERED không?** Nếu có, phần trả về từ trySplit cần là prefix theo encounter order.
8. **Có hứa SORTED/DISTINCT/NONNULL không?** Chỉ khi nội dung thực sự thỏa; SORTED cần getComparator thích hợp.
9. **Nguồn có bị sửa đồng thời không?** Xác định binding, snapshot, fail-fast hoặc concurrent policy.
10. **Có vượt miền int/long hoặc ép kiểu nguy hiểm không?** Chọn cách tính size an toàn, không chuyển `Long.MAX_VALUE` sang số phần tử mảng.
11. **Pipeline có thay đổi cardinality không?** Không dùng size nguồn làm kết quả của filter/flatMap.
12. **Có phụ thuộc side effect trong tryAdvance/map khi gọi count không?** Size metadata có thể khiến count không duyệt.
13. **Đã test với parallel và các lần split nhiều tầng chưa?** Tăng độ tin cậy nếu công bố SUBSIZED.
14. **Đã phân biệt kết quả được đảm bảo với callback count thực nghiệm chưa?** Không suy quá mức từ JVM đang dùng.
15. **Nếu nguồn chỉ đọc một lần, có đang tiêu thụ nó trong estimateSize không?** Phải tránh.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `estimateSize()` luôn trả kích thước chính xác phải không?

**Đáp án:** Không. Nó trả ước lượng; khi unknown/infinite/too expensive có thể là `Long.MAX_VALUE`. Chỉ khi đặc tính và điều kiện hợp đồng phù hợp, ví dụ SIZED đúng, mới có thể xem là exact.

**Câu 2.** `getExactSizeIfKnown()` trả gì nếu `estimateSize()==4` nhưng Spliterator không khai `SIZED`?

**Đáp án:** Triển khai mặc định trả `-1`. Con số estimate bằng 4 không tự chứng minh tính chính xác.

**Câu 3.** Khác nhau giữa `SIZED` và `SUBSIZED`?

**Đáp án:** SIZED công bố khả năng báo size exact theo điều kiện của Spliterator. SUBSIZED còn đảm bảo tất cả các Spliterator được tạo bởi các lần `trySplit` cũng có SIZED/SUBSIZED.

**Câu 4.** Với custom range [0,8), `trySplit()` tạo prefix [0,4) và suffix [4,8). Số lượng từng phần là bao nhiêu?

**Đáp án:** Mỗi phần còn bốn phần tử. Tổng sau split 4+4 bằng tám phần tử ban đầu.

**Câu 5.** Sau khi lấy phần tử 0 từ prefix [0,4), size của prefix phải là bao nhiêu?

**Đáp án:** 3, vì chỉ còn 1,2,3.

**Câu 6.** Tại sao `spliteratorUnknownSize(iterator, ORDERED)` không trả size exact dù iterator đang đọc từ List có bốn phần tử?

**Đáp án:** Adapter chỉ biết hợp đồng Iterator và không nhận metadata List.size(). Nó không được tự suy size bằng cách làm hỏng dữ liệu; mặc định không khai SIZED.

**Câu 7.** Vì sao `StreamSupport.intStream(range, false).map(f).count()` có thể không gọi `tryAdvance`?

**Đáp án:** range khai SIZED đúng và map giữ cardinality, nên count có thể lấy số lượng trực tiếp từ metadata thay vì duyệt các giá trị.

**Câu 8.** Nếu thêm `filter(x -> x%2==0)`, vẫn có thể lấy size của range làm kết quả count không?

**Đáp án:** Không. Filter có thể loại phần tử; với range 0..4, kết quả chỉ có 3 số chẵn.

**Câu 9.** Một Spliterator báo SIZED nhưng estimate=100 dù chỉ có ba phần tử, có chấp nhận được không?

**Đáp án:** Không. Đây là hợp đồng sai và framework có quyền tin metadata, nên các terminal operation có thể cho kết quả sai hoặc lỗi.

**Câu 10.** `Long.MAX_VALUE` từ `estimateSize()` có thể dùng để cấp mảng chứa số phần tử thật không?

**Đáp án:** Không. Nó có thể là sentinel unknown/infinite; cần một chiến lược lưu trữ/streaming phù hợp và kiểm tra giới hạn bộ nhớ.

**Câu 11.** Nếu custom Spliterator luôn tạo prefix đúng nhưng remainder vô tình chứa lại phần tử cuối của prefix, chỉ so sánh sum size có phát hiện không?

**Đáp án:** Không nhất thiết. Phải kiểm tra giá trị phát ra, độ duy nhất và sự bao phủ của nguồn cùng đặc tính được công bố.

**Câu 12.** Cần đặt `SORTED` cho một nguồn tăng dần không? Và getComparator trả gì?

**Đáp án:** Có thể đặt nếu thực sự bảo đảm sorted. Với natural ordering, getComparator trả `null` theo hợp đồng SORTED; khi dùng thứ tự khác cần comparator phù hợp.

**Câu 13.** Khi nguồn mutable, có cần bảo đảm gì thêm?

**Đáp án:** Có. Phải thiết kế thời điểm bind, snapshot, fail-fast/concurrent semantics và tính nhất quán giữa traversal, characteristics, estimate. Không chỉ đọc size tại thời điểm tạo rồi giả định nguồn sẽ không đổi.

## 15. Tài liệu chính thức Java 17

- [Spliterator<T> — overview, estimateSize(), getExactSizeIfKnown(), characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Spliterator.SIZED và SUBSIZED](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#SIZED).
- [Spliterator.OfInt — traversal cho số nguyên thủy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.OfInt.html).
- [Spliterators.spliteratorUnknownSize()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterators.html).
- [StreamSupport.intStream() và stream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html).
- [Stream.count() và API Note về bỏ qua traversal khi biết size](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).

**Ghi nhớ:** `estimateSize()` là **ước lượng số phần tử còn lại**, có thể trả `Long.MAX_VALUE` khi unknown; `getExactSizeIfKnown()` chỉ công bố số chính xác khi Spliterator có `SIZED` theo hợp đồng. `SUBSIZED` mở rộng bảo đảm ấy tới mọi phần được tạo bằng `trySplit()`. Với nguồn tùy chỉnh, việc khai báo kích thước phải **trung thực, cập nhật đúng sau traversal và split, không bỏ/lặp phần tử**. Metadata đúng giúp Stream tối ưu; metadata sai có thể làm sai kết quả, đặc biệt khi `count()` tin SIZED và không cần gọi `tryAdvance()`.
