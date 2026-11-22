# Thiết kế nguồn hữu hạn, nguồn trì hoãn và trách nhiệm đóng tài nguyên trong Java Stream

## 1. Mục tiêu bài học

Khi làm việc với Java Stream, chúng ta không chỉ xử lý dữ liệu từ `List` hoặc mảng. Đôi khi nguồn đến từ một dải số tự tạo, một bộ phát dữ liệu, một cursor, một tệp đang đọc dở, hoặc một API cung cấp phần tử theo yêu cầu. Lúc này, thiết kế **nguồn Stream** đúng quan trọng không kém các phép `map`, `filter`, `reduce`.

Ba câu hỏi cần giải quyết độc lập:

1. **Nguồn hữu hạn hay vô hạn?** Có bao nhiêu phần tử có thể được cung cấp, và liệu terminal operation có thể kết thúc?
2. **Nguồn được đánh giá trì hoãn ra sao?** Việc gọi API tạo Stream có đọc toàn bộ dữ liệu, mở tài nguyên hoặc thực thi hàm sinh phần tử ngay không?
3. **Ai đóng tài nguyên?** Khi nguồn giữ file handle, reader, connection hoặc cursor, việc hoàn tất một terminal operation **không tự có nghĩa** tài nguyên đã được đóng.

Sau bài học, bạn có thể:

- Chọn giữa `Stream.of`, `Stream.iterate`, `Stream.generate`, `StreamSupport.stream` và các nguồn I/O.
- Tạo **Spliterator hữu hạn** có `tryAdvance`, `trySplit`, `estimateSize` và `characteristics` hợp lệ.
- Dùng overload `StreamSupport.stream(Supplier, characteristics, parallel)` khi muốn **late-binding** nguồn.
- Giải thích lazy evaluation và short-circuit trong `limit`, `findFirst`, `anyMatch`.
- Quản lý vòng đời bằng `try-with-resources`, `BaseStream.close()` và `onClose(...)`.
- Phân biệt tài nguyên được mở khi tạo stream, khi gọi terminal và khi thực sự lấy phần tử.
- Nhận diện các lỗi về tập vô hạn, tài nguyên rò rỉ, `Spliterator` báo sai đặc tính, mutable state và xử lý song song.

## 2. Stream pipeline không phải collection

Một Stream mô tả **quá trình duyệt và biến đổi dữ liệu**, thay vì là một cấu trúc lưu trữ kết quả như List.

~~~java
Stream<Integer> pipeline = List.of(1, 2, 3, 4)
        .stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);
~~~

Ở thời điểm tạo `pipeline`, các lambda trong `filter` và `map` thường **chưa được chạy**. Chúng là **intermediate operations** được đánh giá trì hoãn. Một terminal operation mới yêu cầu tạo kết quả:

~~~java
List<Integer> result = pipeline.toList();
System.out.println(result); // [20, 40]
~~~

Stream có thể được chia thành ba tầng:

~~~text
Nguồn dữ liệu
   |
   v
Spliterator / một factory method tạo Stream
   |
   v
Intermediate operations (filter, map, limit, sorted, ...)
   |
   v
Terminal operation (toList, count, findFirst, reduce, ...)
   |
   v
Kết quả hoặc side effect theo hợp đồng terminal
~~~

**Tính trì hoãn của pipeline không tự bảo đảm mọi tài nguyên được mở trì hoãn.** Một factory có thể mở file ngay khi tạo stream nhưng vẫn chưa đọc hết dòng nào. Đây là sự khác biệt quan trọng khi thiết kế nguồn có tài nguyên.

## 3. Nguồn hữu hạn và nguồn vô hạn

**Nguồn hữu hạn (finite source)** có số phần tử hữu hạn trong một lượt duyệt, như List, mảng hoặc một dải số `[start, end)`.

~~~java
Stream<Integer> finite = Stream.of(3, 1, 4);
IntStream range = IntStream.range(0, 5);
~~~

`IntStream.range(0, 5)` có năm giá trị: **0, 1, 2, 3, 4**; cận cuối là **exclusive**.

**Nguồn có khả năng vô hạn (potentially unbounded source)** có thể tạo thêm phần tử nếu terminal tiếp tục yêu cầu:

~~~java
Stream<Long> powers = Stream.iterate(1L, n -> n * 2);
Stream<Double> randoms = Stream.generate(Math::random);
~~~

Các đoạn minh họa cần import `Stream` và `IntStream`. `iterate(seed, next)` và `generate(supplier)` có thể tiếp tục cấp phần tử cho tới khi bị giới hạn hoặc terminal short-circuit. Với ví dụ nhân đôi, kiểu long cuối cùng có thể overflow; điều đó không khiến `iterate` tự dừng.

**Vấn đề:** một terminal như `count()` hoặc `toList()` thường không thể hoàn tất trên một nguồn thật sự vô hạn nếu không có bước giới hạn thích hợp.

~~~java
// Không nên gọi trực tiếp trên nguồn vô hạn:
// Stream.generate(Math::random).toList();
~~~

### 3.1. Giới hạn bằng limit

~~~java
List<Integer> firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` là **short-circuiting intermediate operation**. Trong pipeline đơn giản này, terminal chỉ cần năm phần tử để kết thúc.

Nhưng **không phải cứ có limit ở cuối là an toàn**:

~~~java
// Tránh: sorted có thể phải chờ toàn bộ nguồn vô hạn.
// Stream.iterate(0, n -> n + 1).sorted().limit(5).toList();
~~~

Nếu muốn lấy năm phần tử trước rồi sắp, viết **limit(5).sorted()**; tuy nhiên điều đó mang **ý nghĩa khác** với việc tìm năm phần tử nhỏ nhất trong toàn bộ nguồn. Hãy thiết kế theo bài toán thực sự, không tùy tiện hoán đổi các bước.

### 3.2. iterate với điều kiện dừng (Java 9+)

~~~java
List<Integer> finiteRange = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
).toList();

System.out.println(finiteRange); // [1, 2, 3, 4, 5]
~~~

Overload ba đối số `iterate(seed, hasNext, next)` tạo nguồn hữu hạn nếu điều kiện eventually false. Nếu điều kiện mãi true, nguồn vẫn có thể không kết thúc.

Cần để ý **thứ tự kiểm tra**: `hasNext` được xét để xác định phần tử hiện tại có được đưa ra không; nếu false, phần tử ấy không nằm trong Stream.

### 3.3. generate khác iterate

`Stream.generate(Supplier<T>)` lấy mỗi giá trị từ một Supplier, thường dùng để tạo dữ liệu mô phỏng hoặc những phần tử độc lập.

~~~java
List<String> tickets = Stream.generate(() -> "NEW")
        .limit(3)
        .toList();

System.out.println(tickets); // [NEW, NEW, NEW]
~~~

Nếu Supplier dựa vào bộ đếm mutable hoặc tài nguyên có trạng thái, tính an toàn khi chuyển sang parallel cần được kiểm tra. Với `generate`, Stream không tự cam kết các phần tử theo một trình tự đánh số nghiệp vụ. Nên dùng `IntStream.range` hoặc `iterate` nếu yêu cầu một chuỗi có thứ tự rõ ràng.

## 4. Nguồn hữu hạn nên mô tả kích thước và ranh giới rõ

Một nguồn tự định nghĩa cần trả lời:

- Giá trị **đầu tiên** có thể phát ra là gì?
- **Điều kiện kết thúc** chính xác là gì?
- Có bao gồm cận cuối không?
- Nếu terminal yêu cầu thêm phần tử sau khi hết, nguồn trả gì?
- Có thể gọi một lượt duyệt nhiều lần hay không?
- Có thể chia thành các đoạn rời nhau cho parallel không?

Một thiết kế đơn giản là dải số nguyên từ **startInclusive** đến **endExclusive**:

~~~text
startInclusive = 1
endExclusive   = 6

Phần tử: 1, 2, 3, 4, 5
Số lượng: endExclusive - startInclusive = 5
~~~

Với cận cuối exclusive, điều kiện hết nguồn là `current >= endExclusive`. Việc cận cuối exclusive nhất quán với `IntStream.range(start, end)`, giúp tránh lỗi cộng/trừ 1.

**Nếu endExclusive nhỏ hơn startInclusive**, phải quyết định rõ: từ chối tham số, hoặc biểu diễn nguồn rỗng. Đừng vừa công bố kích thước âm vừa báo đặc tính `SIZED`.

Trong nguồn tổng quát, nếu số lượng lớn hơn phạm vi int, hãy dùng số đếm kiểu long và tính khoảng cách cẩn thận để tránh overflow.

## 5. Spliterator: ranh giới giữa nguồn và Stream

Java dùng **`java.util.Spliterator<T>`** để duyệt và, nếu phù hợp, chia nguồn thành các phần có thể xử lý.

Các phương thức/thuộc tính quan trọng:

| Thành phần | Ý nghĩa |
| --- | --- |
| **tryAdvance(action)** | Thử chuyển tiếp đúng một phần tử tới Consumer, trả true nếu có phần tử |
| **forEachRemaining(action)** | Chuyển tiếp các phần tử còn lại; có default implementation |
| **trySplit()** | Thử tách một phần nguồn chưa xử lý để có thể duyệt độc lập |
| **estimateSize()** | Ước lượng số phần tử chưa duyệt |
| **characteristics()** | Cờ mô tả các đặc tính được bảo đảm của nguồn |
| **getExactSizeIfKnown()** | Trả kích thước chính xác nếu có `SIZED`, ngược lại -1 |
| **getComparator()** | Có ý nghĩa khi Spliterator báo `SORTED` |

**tryAdvance** là trung tâm: với nguồn hữu hạn, sau phần tử cuối, những lần gọi tiếp theo cần trả **false**, không gọi action nữa.

Ví dụ dạng mô tả:

~~~java
@Override
public boolean tryAdvance(Consumer<? super Integer> action) {
    if (current >= endExclusive) {
        return false;
    }
    action.accept(current++);
    return true;
}
~~~

Đoạn này giả định đang trong lớp có field `current` và `endExclusive`; cần import `Consumer`. Chương trình hoàn chỉnh ở phần 13 cung cấp định nghĩa đầy đủ và kiểm thử.

### 5.1. Một Spliterator là trạng thái duyệt, không phải danh sách

Mỗi Spliterator thường có **vị trí hiện tại**. Khi gọi `tryAdvance`, vị trí ấy thay đổi. Việc này không có nghĩa dữ liệu nguồn bên ngoài bị sửa: trạng thái vị trí của bộ duyệt có thể mutable dù nguồn toán học là bất biến.

Không được dùng một Spliterator đang bị nhiều thread tự ý gọi `tryAdvance` đồng thời mà không có thiết kế tương ứng. Trong một parallel stream được xây dựng đúng, framework tổ chức quá trình **split**, và mỗi nhánh sẽ sở hữu các phần công việc theo hợp đồng phân chia.

## 6. trySplit: chia nguồn để hỗ trợ parallel

`trySplit()` cố tách phần chưa duyệt thành các phần rời nhau. Nó trả:

- Một Spliterator mới đại diện cho một phần được tách, hoặc
- `null` khi không tách được hoặc không nên tách.

Giả sử còn đoạn `[1, 9)`:

~~~text
Trước split:
[1, 2, 3, 4, 5, 6, 7, 8]

trySplit():
  nhánh trả về [1, 2, 3, 4]
  nhánh gốc   [5, 6, 7, 8]
~~~

Hai nhánh **không được chồng phần tử hoặc bỏ sót phần tử**. Chúng phải cùng mô tả đúng tập dữ liệu chưa duyệt, nhất quán với `estimateSize`.

Một cách chia dải đơn giản là:

~~~java
int low = current;
int mid = low + (endExclusive - low) / 2;

if (mid <= low) {
    return null;
}

current = mid; // Nhánh gốc giữ nửa sau.
return new RangeSpliterator(low, mid);
~~~

Đây là thuật toán minh họa, cần lớp RangeSpliterator có constructor tương ứng. Nếu phạm vi chỉ số có thể khiến **endExclusive - low** overflow int, hãy chuyển phép tính độ dài sang long trước khi chia.

### 6.1. trySplit có bắt buộc không?

Không. Một Spliterator có thể luôn trả `null`, và nguồn vẫn sử dụng được cho sequential Stream. Tuy nhiên, parallel Stream thường sẽ khó thu được lợi ích nếu nguồn không chia được, hoặc việc chia tốn kém hơn phần tính toán.

**Không báo sai `SUBSIZED`** nếu kích thước các nhánh sau split không chính xác. Đối với một dải số bất biến được chia theo khoảng không giao nhau, `SIZED | SUBSIZED` có thể được công bố hợp lệ.

## 7. Các characteristics quan trọng

Một Spliterator có thể công bố những cờ trong `Spliterator`:

| Cờ | Điều được bảo đảm | Chú ý |
| --- | --- | --- |
| **ORDERED** | Có encounter order xác định | Không đồng nghĩa Stream sequential |
| **DISTINCT** | Không có hai phần tử trùng theo equals | Chỉ báo khi thật sự đúng |
| **SORTED** | Phần tử theo một thứ tự so sánh | Có hợp đồng `getComparator()` tương ứng |
| **SIZED** | `estimateSize()` là số phần tử chính xác còn lại trước khi chia/duyệt | Không báo nếu nguồn thực tế thay đổi kích thước không kiểm soát |
| **SUBSIZED** | Các Spliterator sau split cũng SIZED và SUBSIZED | Rất hữu ích cho chia nguồn hiệu quả |
| **NONNULL** | Không phát ra phần tử null | Không tương đương các field bên trong object khác null |
| **IMMUTABLE** | Nguồn không bị can thiệp cấu trúc trong lúc duyệt | Trạng thái con trỏ nội bộ vẫn có thể thay đổi |
| **CONCURRENT** | Nguồn được thiết kế để sửa đồng thời theo hợp đồng | Không tự suy diễn từ một biến AtomicInteger |

**Các cờ là lời cam kết**, không phải “gợi ý tăng tốc” tùy ý. Nếu báo **SIZED** nhưng `estimateSize` sai, Stream có thể tối ưu dựa trên thông tin sai và tạo kết quả bất ngờ.

Ví dụ với một dải số không thay đổi:

~~~java
int characteristics = Spliterator.ORDERED
        | Spliterator.SIZED
        | Spliterator.SUBSIZED
        | Spliterator.NONNULL
        | Spliterator.IMMUTABLE;
~~~

Nên chỉ công bố những gì triển khai bảo đảm. Nếu nguồn là dữ liệu từ tệp/cursor mà số bản ghi chưa biết, **không tự gắn SIZED**. Nếu nguồn có thể phát null, **không gắn NONNULL**.

### 7.1. SORTED cần thêm hợp đồng

Khi công bố `SORTED`, Spliterator phải hỗ trợ `getComparator()` theo ngữ nghĩa: trả null khi đã sắp theo natural order, hoặc trả Comparator phù hợp với thứ tự khác. Không gắn SORTED chỉ vì “thường thì dữ liệu có vẻ tăng dần”.

Báo cờ sai có thể dẫn đến việc pipeline bỏ qua bước sort cần thiết hoặc giả định sai về nguồn.

### 7.2. SIZED không tự đồng nghĩa hữu hạn trong mọi bài toán

Một nguồn hữu hạn có thể **không biết trước kích thước**, ví dụ đọc dòng từ một reader mà chưa quét hết. Nguồn đó vẫn hữu hạn nhưng không nên báo SIZED.

Ngược lại, một nguồn tạo phần tử không giới hạn có thể trả `Long.MAX_VALUE` như ước lượng chưa biết, không phải tuyên bố rằng nguồn chính xác có Long.MAX_VALUE phần tử.

## 8. Tạo Stream từ Spliterator bằng StreamSupport

Cách phổ biến khi có một Spliterator:

~~~java
Stream<Integer> stream = StreamSupport.stream(
        spliterator,
        false // sequential
);
~~~

Đây là mảnh ghép với biến `spliterator` kiểu Spliterator<Integer> và import Stream/StreamSupport. Nếu truyền **true**, Stream có parallel mode ban đầu:

~~~java
Stream<Integer> parallel = StreamSupport.stream(
        spliterator,
        true
);
~~~

`parallel` không bảo đảm chia việc hiệu quả nếu trySplit không hỗ trợ hoặc nguồn nhỏ. Tương tự, `stream.parallel()` có thể thay đổi mode của pipeline sau đó.

**Lưu ý ownership:** nếu Spliterator đã được tạo từ một resource mở, resource ấy vẫn cần được đóng theo cơ chế rõ ràng; chỉ gọi StreamSupport.stream không làm Java tự suy luận phải đóng cái gì.

## 9. Late-binding bằng Supplier<Spliterator<T>>

Java còn cung cấp overload:

~~~java
Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel)
~~~

Điểm khác là caller truyền **một Supplier tạo Spliterator**, thay vì đưa Spliterator đã có sẵn.

Với overload này, **Supplier được gọi không sớm hơn khi terminal operation bắt đầu** (hoặc trong quá trình đánh giá pipeline tương ứng), giúp trì hoãn việc lấy bộ duyệt cho tới lúc thật sự cần.

Ví dụ:

~~~java
AtomicInteger creations = new AtomicInteger();

Supplier<Spliterator<Integer>> factory = () -> {
    creations.incrementAndGet();
    return List.of(1, 2, 3).spliterator();
};

Stream<Integer> stream = StreamSupport.stream(
        factory,
        Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED,
        false);

System.out.println(creations.get()); // 0
System.out.println(stream.toList()); // [1, 2, 3]
System.out.println(creations.get()); // 1
~~~

Đây là đoạn minh họa trong phương thức có import `List`, `Stream`, `Spliterator`, `Supplier`, `AtomicInteger` và `StreamSupport`.

**Không suy ra** rằng Supplier luôn được gọi đúng một lần trong mọi cách khai thác Stream hoặc khi có lỗi. Hợp đồng chính là Supplier cung cấp một Spliterator phù hợp khi Stream cần đánh giá; mỗi Stream vẫn dành cho một lần tiêu thụ.

### 9.1. Characteristics phải khớp

Ở overload Supplier, đối số **characteristics** phải khớp với characteristics của Spliterator mà Supplier thực sự trả về. Đặc tả yêu cầu chúng **bằng nhau**, nếu không hành vi không xác định theo hợp đồng API.

Vì vậy, với một Spliterator tùy chỉnh, hãy dùng **cùng tập cờ** ở lớp nguồn và lời gọi `StreamSupport.stream(supplier, flags, parallel)`.

### 9.2. Supplier không tự xử lý việc đóng tài nguyên

Trì hoãn tạo Spliterator có thể giúp trì hoãn mở nguồn, nhưng **không làm Stream tự đóng file/cursor sau terminal**. Nếu Supplier mở tài nguyên, cần thiết kế nơi giữ tham chiếu tài nguyên, hành động `onClose` và chính sách xử lý lỗi một cách rõ ràng.

Nếu caller không gọi terminal mà đóng Stream, `onClose` vẫn cần an toàn với trường hợp **chưa mở tài nguyên**. Nếu mở thất bại giữa chừng, phải bảo đảm không rò rỉ những tài nguyên đã tạo thành công.

## 10. Tính lazy có nhiều lớp khác nhau

Hãy phân biệt:

1. **Lười tạo bộ duyệt:** Supplier<Spliterator> chưa được gọi.
2. **Lười lấy phần tử:** Spliterator đã tồn tại nhưng `tryAdvance` chưa được yêu cầu.
3. **Lười biến đổi:** `map/filter` chưa được chạy.
4. **Lười làm I/O:** mỗi dòng/chunk chỉ được đọc khi cần, nếu nguồn hỗ trợ.
5. **Lười mở tài nguyên:** file/connection chưa được mở; điều này **không tự động đúng** với mọi Stream I/O.

Một Stream có thể lazy ở các mục 2–4 nhưng **đã mở tài nguyên** ngay khi gọi factory.

Ví dụ, API `Files.lines(path)` mở file để tạo Stream đọc dòng; việc xử lý nội dung có tính lazy, nhưng file là tài nguyên phải đóng. Không được coi “chưa terminal” đồng nghĩa “chưa có resource được giữ”.

### 10.1. map/filter và terminal short-circuit

~~~java
List<Integer> firstTwoEven = Stream.iterate(1, n -> n + 1)
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

System.out.println(firstTwoEven); // [2, 4]
~~~

Trong một sequential pipeline đơn giản, chỉ cần thử các số 1,2,3,4 để tìm hai số chẵn. Không phải toàn bộ chuỗi vô hạn đã được sinh ra.

Tuy nhiên, **không dùng side effect trong Supplier/Predicate làm cam kết “chính xác bốn lời gọi” cho mọi parallel pipeline**. Short-circuiting và việc chia việc có thể làm số callback thay đổi.

## 11. Một Stream thường chỉ tiêu thụ một lần

~~~java
Stream<String> stream = Stream.of("A", "B");
long size = stream.count();

// Không sử dụng lại cùng Stream:
// stream.toList(); // Có thể ném IllegalStateException.
~~~

Stream chỉ dành cho một pipeline được tiêu thụ một lần. Nếu cần dùng lại dữ liệu, tạo Stream mới từ **nguồn có thể phát lại** (List, array, factory trả một nguồn mới) hoặc materialize kết quả hợp lệ khi cần.

**Nguồn phát lại** khác **Spliterator phát lại**. Một đối tượng Spliterator đã đi tới cuối không tự quay lại đầu. Muốn tái duyệt, tạo **Spliterator mới** qua factory thích hợp.

Nếu nguồn là một tệp hoặc cursor chỉ dùng một lần, hãy quyết định rõ liệu API có cho phép đọc lại, và liệu việc tạo Stream mới cần mở một resource mới.

## 12. Tài nguyên: terminal không tự đóng Stream

Các Stream chỉ làm việc với collection trong bộ nhớ thường không cần đóng một tài nguyên bên ngoài. Nhưng Stream từ file, reader hoặc tài nguyên I/O có thể giữ file descriptor, buffer hoặc reader.

**Điểm trọng tâm:**

- `Stream<T>` thực hiện `AutoCloseable` thông qua `BaseStream`.
- `close()` là hành động đóng Stream và chạy các close handler đã đăng ký.
- **Terminal operation không mặc nhiên gọi close()**.
- `onClose(Runnable)` đăng ký một hành động để chạy khi Stream được đóng.
- `try-with-resources` bảo đảm Stream.close được gọi cả khi terminal ném exception, theo cấu trúc ngôn ngữ Java.
- **Ai tạo hoặc nhận quyền sở hữu Stream chứa resource nên xác định rõ trách nhiệm đóng**.

Ví dụ chuẩn với file:

~~~java
Path path = Path.of("data.txt");

try (Stream<String> lines = Files.lines(path)) {
    List<String> preview = lines
            .limit(5)
            .toList();

    System.out.println(preview);
}
~~~

Đây là đoạn minh họa cần file data.txt tồn tại và import `Path`, `Files`, `Stream`, `List`. Không thể khẳng định stdout nếu chưa biết nội dung file.

**Files.lines(path)** cung cấp Stream các dòng có resource mở, và tài liệu API yêu cầu đóng Stream kịp thời. `try-with-resources` là cách dễ đọc và an toàn nhất.

### 12.1. Không đóng Stream rồi mới trả về

Phản ví dụ:

~~~java
Stream<String> loadLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines; // SAI: đã đóng trước khi caller duyệt.
    }
}
~~~

Đoạn này là method minh họa không phải file độc lập. Khi thoát khối try, Stream đã bị đóng. Việc trả về một Stream đã đóng khiến caller không thể dùng nó hợp lệ như một pipeline mới.

Hai hướng thiết kế tốt:

- **Xử lý trong phạm vi sở hữu resource:** phương thức mở Stream, duyệt và trả **kết quả đã materialize**, sau đó đóng.
- **Chuyển quyền sở hữu rõ ràng:** phương thức trả Stream vẫn còn mở; tài liệu API nói caller **phải đóng** trong try-with-resources.

Nếu trả Stream cho caller, phải xác định exception từ I/O khi terminal chạy sẽ xuất hiện ở đâu, không chỉ lỗi mở file ban đầu.

### 12.2. onClose không chạy chỉ vì toList hoàn tất

~~~java
AtomicBoolean closed = new AtomicBoolean(false);

Stream<String> lines = Stream.of("A", "B")
        .onClose(() -> closed.set(true));

List<String> data = lines.toList();
System.out.println(closed.get()); // false

lines.close();
System.out.println(closed.get()); // true
~~~

Đây là đoạn minh họa với import Stream, List, AtomicBoolean. Nó chứng minh `toList()` không tự gọi close handler; `close()` là thao tác riêng.

**Không dùng việc một terminal trả về thành công như tín hiệu resource đã được đóng.**

## 13. Chương trình Java 17 hoàn chỉnh

Ví dụ này kiểm chứng ba ý chính:

1. Một **Spliterator hữu hạn** phát các số theo khoảng `[startInclusive, endExclusive)`, trả false khi hết.
2. Nguồn được tạo bằng **Supplier<Spliterator>**, nên lần tạo Spliterator được trì hoãn đến terminal. Pipeline `filter(...).limit(2)` chỉ lấy số phần tử cần thiết.
3. **BufferedReader.lines()** lấy dòng theo nhu cầu; một `onClose` gắn nhiệm vụ đóng reader vào vòng đời Stream. `toList()` không tự gọi close handler; `try-with-resources` gọi close khi thoát khối.

Dùng `StringReader` thay tệp thật để ví dụ chạy độc lập, không phụ thuộc đường dẫn máy tính. Một nguồn file thực tế có cùng nguyên tắc ownership.

Tạo file **CustomStreamSourceDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class CustomStreamSourceDemo {
    private static final int FLAGS =
            Spliterator.ORDERED
            | Spliterator.SIZED
            | Spliterator.SUBSIZED
            | Spliterator.NONNULL
            | Spliterator.IMMUTABLE;

    static final class RangeSpliterator
            implements Spliterator<Integer> {
        private int current;
        private final int endExclusive;
        private final AtomicInteger emitted;

        RangeSpliterator(int startInclusive,
                         int endExclusive,
                         AtomicInteger emitted) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException(
                        "start must not exceed end");
            }
            this.current = startInclusive;
            this.endExclusive = endExclusive;
            this.emitted = Objects.requireNonNull(emitted);
        }

        @Override
        public boolean tryAdvance(
                Consumer<? super Integer> action) {
            Objects.requireNonNull(action);

            if (current >= endExclusive) {
                return false;
            }

            int value = current++;
            emitted.incrementAndGet();
            action.accept(value);
            return true;
        }

        @Override
        public Spliterator<Integer> trySplit() {
            int low = current;
            int mid = low + (endExclusive - low) / 2;

            if (mid <= low) {
                return null;
            }

            current = mid;
            return new RangeSpliterator(low, mid, emitted);
        }

        @Override
        public long estimateSize() {
            return (long) endExclusive - current;
        }

        @Override
        public int characteristics() {
            return FLAGS;
        }
    }

    static Stream<Integer> delayedRange(
            int start,
            int end,
            AtomicInteger creations,
            AtomicInteger emitted) {
        Supplier<Spliterator<Integer>> supplier = () -> {
            creations.incrementAndGet();
            return new RangeSpliterator(start, end, emitted);
        };

        return StreamSupport.stream(supplier, FLAGS, false);
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        AtomicInteger emitted = new AtomicInteger();

        try (Stream<Integer> range = delayedRange(
                1, 8, creations, emitted)) {
            System.out.println(
                    "created before: " + creations.get());
            System.out.println(
                    "emitted before: " + emitted.get());

            List<Integer> twoEven = range
                    .filter(n -> n % 2 == 0)
                    .limit(2)
                    .toList();

            System.out.println("two even: " + twoEven);
            System.out.println(
                    "created after: " + creations.get());
            System.out.println(
                    "emitted after: " + emitted.get());
        }

        AtomicInteger parallelEmitted = new AtomicInteger();
        List<Integer> parallel = StreamSupport.stream(
                new RangeSpliterator(
                        1, 6, parallelEmitted), true)
                .map(n -> n * 10)
                .toList();

        System.out.println("parallel values: " + parallel);

        AtomicBoolean closed = new AtomicBoolean(false);
        BufferedReader reader = new BufferedReader(
                new StringReader("alpha\nbeta\ngamma"));

        Stream<String> lines = reader.lines()
                .onClose(() -> {
                    try {
                        reader.close();
                        closed.set(true);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });

        try (lines) {
            System.out.println("line preview: "
                    + lines.limit(2).toList());
            System.out.println(
                    "closed inside: " + closed.get());
        }

        System.out.println(
                "closed after: " + closed.get());

        System.out.println("finite prefix: "
                + Stream.iterate(0, n -> n + 1)
                        .limit(4)
                        .toList());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac CustomStreamSourceDemo.java
java CustomStreamSourceDemo
~~~

**Đầu ra dự kiến:**

~~~text
created before: 0
emitted before: 0
two even: [2, 4]
created after: 1
emitted after: 4
parallel values: [10, 20, 30, 40, 50]
line preview: [alpha, beta]
closed inside: false
closed after: true
finite prefix: [0, 1, 2, 3]
~~~

### 13.1. Vì sao created before là 0?

`delayedRange(...)` gọi overload **StreamSupport.stream(supplier, FLAGS, false)**. Tại lúc tạo Stream, Supplier chưa cần được gọi; `creations` vẫn bằng 0. Sau khi terminal `toList()` khởi động đánh giá, Supplier được dùng để tạo RangeSpliterator.

Đây là **late-binding** của Spliterator, khác với overload nhận **một Spliterator đã tồn tại**.

### 13.2. Vì sao emitted after là 4?

Nguồn phát 1,2,3,4,...; `filter(n % 2 == 0)` giữ số chẵn; `limit(2)` cần **hai giá trị chẵn đầu tiên** là 2 và 4. Trong pipeline tuần tự này, RangeSpliterator phát ra đúng bốn số đầu để tạo kết quả.

AtomicInteger ở đây chỉ dùng để **quan sát** thử nghiệm, không phải business logic. Nếu thay pipeline thành parallel hoặc có một stateful stage, số lần callback/thứ tự lấy phần tử có thể khác. Không thiết kế hệ thống kiểm toán dựa vào bộ đếm này.

### 13.3. trySplit và parallel

RangeSpliterator được chia thành các khoảng không giao nhau; `trySplit()` thay đổi chỉ số của nhánh gốc và trả một nhánh mới chứa nửa trước. `StreamSupport.stream(..., true)` yêu cầu parallel mode, và `toList()` tạo kết quả **theo encounter order** vì Spliterator báo ORDERED.

**parallel values** vẫn là [10,20,30,40,50]. Parallel không có nghĩa kết quả sẽ bị đảo thứ tự. Tuy nhiên, chương trình không dựa vào số thread hay số lần chia thực tế.

### 13.4. Vì sao closed inside là false?

Đối với `BufferedReader.lines()` với `onClose` riêng ở ví dụ, terminal `toList()` không tự đóng Stream. Trong khối try, close handler chưa được gọi nên `closed` vẫn false. Khi thoát khối **try-with-resources**, Stream.close() chạy `onClose`, đóng BufferedReader và đặt `closed` thành true.

Đó là trách nhiệm vòng đời khác với việc tạo kết quả.

**Chú ý:** ví dụ dùng `StringReader` (không giữ file descriptor thật), nhưng nguyên tắc đóng vẫn đúng với BufferedReader đọc file. Khi dùng API tạo Stream từ resource đã mở, phải quyết định rõ ai đóng Reader và đảm bảo xử lý cả tình huống terminal ném lỗi.

## 14. Đóng tài nguyên từ Stream hoặc từ chủ sở hữu

Có hai cách ownership thường gặp.

### 14.1. Stream sở hữu vòng đời resource

Một factory mở resource rồi trả Stream có gắn close handler. Caller nhận Stream và phải đóng nó:

~~~java
static Stream<String> openLines(Path path)
        throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);

    return reader.lines().onClose(() -> {
        try {
            reader.close();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    });
}
~~~

Đây là một phương thức minh họa, cần import Path, Files, BufferedReader, IOException, UncheckedIOException, Stream và đặt trong lớp.

Caller:

~~~java
try (Stream<String> lines = openLines(path)) {
    lines.filter(s -> !s.isBlank())
            .limit(10)
            .forEach(System.out::println);
}
~~~

Phương thức `openLines` có thể ném IOException lúc mở file. Trong quá trình duyệt, lỗi đọc có thể được bọc thành **UncheckedIOException**. Khi đóng, nếu close ném IOException, close handler ở trên chuyển nó thành UncheckedIOException.

**Một giới hạn của ví dụ:** nếu giữa thao tác mở reader và việc tạo/đăng ký Stream xuất hiện exception, factory production cần dọn resource đã mở. Trong đoạn đơn giản này, các thao tác trung gian không có nguyên nhân thường gặp để ném checked exception, nhưng nguyên tắc cleanup khi xây dựng thất bại vẫn quan trọng.

### 14.2. Đối tượng khác sở hữu resource

Có thể một service sở hữu Reader và dùng Stream chỉ để duyệt trong phạm vi phương thức. Khi đó service phải đóng Reader trong một `try-with-resources` bao ngoài, thay vì luôn chuyển quyền sở hữu sang Stream.

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    List<String> values = reader.lines()
            .limit(5)
            .toList();
}
~~~

Đây là mảnh ghép yêu cầu biến path và import tương ứng. Reader là resource được try-with-resources quản lý trực tiếp. Terminal hoàn tất hay ném exception thì khi thoát try, Reader vẫn được đóng.

**Quy tắc:** chỉ nên có **một hợp đồng ownership rõ ràng**. Một Stream có thể gắn close handler đóng Reader, hoặc Reader được quản lý bên ngoài. Đừng vừa đóng quá sớm vừa chuyển đối tượng cho caller dùng tiếp.

## 15. Files.lines, Files.list và Files.walk

JDK cung cấp các API tạo Stream gắn với tài nguyên hệ thống:

- **Files.lines(path)**: duyệt các dòng trong tệp văn bản.
- **Files.list(dir)**: Stream các entry trực tiếp trong thư mục.
- **Files.walk(start)**: Stream các đường dẫn khi duyệt cây thư mục.

Các Stream này cần được **đóng kịp thời** theo tài liệu API, vì có thể giữ tài nguyên liên quan đến tệp/thư mục. Dùng try-with-resources.

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    long files = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(files);
}
~~~

Đây là đoạn minh họa, cần import Path, Files, Stream, có biến directory và xử lý IOException. Kết quả phụ thuộc thư mục thật nên không nêu stdout cố định.

### 15.1. Đóng ngay cả khi short-circuit

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Optional<String> firstError = lines
            .filter(line -> line.startsWith("ERROR"))
            .findFirst();
}
~~~

Dù `findFirst()` có thể dừng sớm, tài nguyên file vẫn phải được đóng. `try-with-resources` làm điều đó khi rời khối.

**Không đóng file vì đã đọc tới EOF** theo suy đoán của ứng dụng: terminal đã đủ kết quả hay đã đọc hết đều không thay thế trách nhiệm close.

### 15.2. Exceptions có thể xuất hiện lúc tạo hoặc lúc duyệt

- **Mở file** có thể ném IOException.
- **Đọc dòng trong terminal** có thể gặp I/O error, thường biểu hiện qua UncheckedIOException từ API Stream liên quan.
- **Đóng resource** cũng có thể gặp exception.

Thiết kế API cần phân biệt ba giai đoạn, xác định ai bắt/ghi log/chuyển lỗi và không đánh đồng “Stream rỗng” với “đọc lỗi”.

## 16. onClose và các close handler

`BaseStream.onClose(Runnable)` đăng ký handler chạy khi Stream được đóng; handler được thực thi **một lần theo hợp đồng close của pipeline**, theo thứ tự đăng ký nếu có nhiều handler.

~~~java
Stream<String> stream = Stream.of("A", "B")
        .onClose(() -> System.out.println("first close"))
        .onClose(() -> System.out.println("second close"));

try (stream) {
    System.out.println(stream.toList());
}
~~~

Kết quả:

~~~text
[A, B]
first close
second close
~~~

Lưu ý: nếu nhiều close handler ném exception, Java vẫn cố chạy các handler còn lại; exception có thể được gắn suppressed theo hợp đồng đóng. **Không coi close handler là nơi phù hợp để thực hiện tác vụ nghiệp vụ chủ chốt có phụ thuộc thứ tự ngoài việc dọn tài nguyên.**

Nếu không có tài nguyên đặc biệt, gọi close trên Stream từ List thường không cần thiết, nhưng việc dùng try-with-resources cũng không có hại khi API tổng quát cần đóng bất kỳ Stream được truyền vào.

### 16.1. Không dùng onClose để sửa một lỗi thiết kế vòng đời

Nếu một file đã được đóng trước khi Stream bắt đầu duyệt, đăng ký onClose không thể “mở lại” file. Đảm bảo resource **còn sống trong toàn thời gian terminal cần đọc**.

Nếu một Stream được trả ra bên ngoài phạm vi sở hữu, caller phải được thông báo nghĩa vụ close; cách diễn đạt rõ bằng tên API như `openLines` và tài liệu mô tả có thể hữu ích.

## 17. Tài nguyên mở trì hoãn: mẫu factory cẩn trọng

Khi thật sự muốn **trì hoãn việc mở resource đến lúc terminal**:

1. Có thể dùng Supplier của `StreamSupport.stream`.
2. Supplier mở resource và tạo Spliterator phù hợp.
3. Đăng ký onClose biết resource nào đã được mở (nếu có).
4. Xử lý lỗi mở và lỗi đọc, đồng thời bảo đảm resource được dọn trong mọi đường đi.
5. Không báo `SIZED` khi số phần tử chưa biết, và không chia sẻ một reader không thread-safe qua các nhánh parallel một cách tùy ý.

Sơ đồ:

~~~text
Tạo Stream
   |
   +-- chưa mở resource nếu factory thiết kế late-open
   |
   v
Terminal bắt đầu
   |
   v
Supplier mở resource, tạo Spliterator
   |
   v
tryAdvance đọc từng phần tử
   |
   +-- terminal có thể kết thúc sớm (limit/findFirst)
   |
   v
Stream.close() từ try-with-resources
   |
   v
onClose đóng resource nếu đã mở
~~~

**Đây là mẫu thiết kế, không phải lời hứa mọi Files.lines() đang thực hiện late-open như trên.** Các factory có thể chọn mở tài nguyên ở thời điểm tạo Stream.

Với resource dùng một lần, tránh giả định có thể xử lý lại cùng Stream hoặc Spliterator sau một terminal. Nếu muốn lặp lại quá trình đọc, thiết kế factory tạo **một Stream mới, một resource mới** cho mỗi lượt và yêu cầu caller đóng đúng lượt đó.

### 17.1. Khi nào không cần tự viết Spliterator cho I/O?

Đừng tự viết Spliterator chỉ để bọc API đã cung cấp nguồn phù hợp và tự quản lý close. Nếu cần đọc tệp dòng, **Files.lines** đã có semantics và ownership rõ. Nếu cần duyệt một List, dùng **list.stream()**. Nếu cần dải số, dùng **IntStream.range**.

Chỉ xây Spliterator tùy chỉnh khi bạn cần nguồn đặc biệt, khả năng chia, thứ tự, late-binding hoặc điều kiện kết thúc không được biểu đạt tốt bằng API sẵn có.

## 18. Sai sót thường gặp trong thiết kế nguồn

| Sai sót | Hậu quả | Cách thiết kế đúng |
| --- | --- | --- |
| Nguồn hữu hạn không trả false khi hết | Terminal có thể không kết thúc hoặc lặp giá trị | Xác định điều kiện kết thúc trong tryAdvance |
| Báo SIZED nhưng estimateSize sai | Stream tối ưu dựa trên thông tin không đúng | Chỉ báo SIZED khi số lượng chính xác |
| Báo SUBSIZED cho những nhánh không đủ kích thước | Sai hợp đồng phân chia | Đảm bảo mỗi nhánh SIZED/SUBSIZED hoặc bỏ cờ |
| trySplit trả nhánh chồng lấp | Mất/nhân đôi dữ liệu khi parallel | Chia các khoảng rời nhau |
| Supplier StreamSupport báo characteristics khác Spliterator | Hành vi ngoài hợp đồng API | Sử dụng cùng bộ cờ |
| Nghĩ `limit` luôn cứu được `sorted` trên nguồn vô hạn | Sorted có thể cần mọi phần tử | Đặt giới hạn hợp lý trước sort hoặc dùng thuật toán khác |
| Nghĩ terminal tự đóng file | Rò tài nguyên | try-with-resources hoặc ownership rõ |
| Trả Stream từ trong try-with-resources đã đóng | Caller không thể tiêu thụ hợp lệ | Trả kết quả materialize hoặc chuyển ownership |
| Nghĩ lazy pipeline luôn lazy-open | Resource có thể đã mở ở factory | Phân biệt lazy traversal với late resource acquisition |
| Dùng Stream một lần rồi duyệt lại | IllegalStateException / nguồn đã tiêu thụ | Tạo Stream mới từ nguồn phát lại |
| Dùng shared Reader cho parallel trySplit tùy tiện | Race hoặc kết quả sai | Chọn sequential hoặc thiết kế nguồn an toàn chia độc lập |
| Dùng onClose như một terminal tự chạy | onClose chỉ chạy khi close | Đảm bảo gọi close rõ ràng |
| Đóng resource trước khi terminal kết thúc | Lỗi đọc / resource đã đóng | Quản lý vòng đời bao trọn quá trình đánh giá |
| Dựa vào số lần peek/filter để audit | Callback có thể bị bỏ qua hoặc short-circuit | Audit qua quy trình có hợp đồng riêng |
| Tự viết nguồn dù API chuẩn đủ dùng | Tăng độ phức tạp không cần thiết | Ưu tiên Files.lines, stream, range, iterate có điều kiện |

## 19. Bài tập tự luyện

### Bài 1 — Đoán lúc Supplier được gọi

Giả sử Stream được tạo bằng overload **StreamSupport.stream(supplier, flags, false)**, supplier tăng một bộ đếm khi tạo Spliterator. Sau khi tạo Stream nhưng trước terminal, bộ đếm có bắt buộc tăng không?

**Đáp án:** không. Overload supplier được thiết kế để trì hoãn lấy Spliterator cho tới khi cần đánh giá pipeline. Trong ví dụ của bài, bộ đếm bằng 0 trước terminal và bằng 1 sau terminal.

### Bài 2 — Thiết kế nguồn hữu hạn

Hãy mô tả điều kiện kết thúc cho nguồn `[startInclusive, endExclusive)`.

**Gợi ý:** nếu `current >= endExclusive`, `tryAdvance` trả false và không gọi Consumer. Nếu còn phần tử, gọi Consumer với current rồi tăng current. `estimateSize()` trả số phần tử chưa duyệt, không trả số phần tử ban đầu.

### Bài 3 — trySplit đúng

Nguồn còn các số từ 1 đến 8. Hãy tách thành hai khoảng độc lập và tính estimateSize tương ứng.

**Đáp án gợi ý:** Spliterator trả về chứa [1,5) = 1,2,3,4, có size 4; Spliterator gốc giữ [5,9) = 5,6,7,8, size 4. Không phần tử nào xuất hiện ở hai nhánh.

### Bài 4 — Đóng tài nguyên sau findFirst

Một hàm mở file rồi tìm dòng đầu tiên bắt đầu bằng "ERROR". Nếu tìm thấy và findFirst trả Optional, file có tự đóng không?

**Đáp án:** không được dựa vào terminal để đóng. Đặt Stream file trong try-with-resources; đóng khi ra khỏi phạm vi, kể cả trường hợp tìm thấy sớm hoặc ném exception.

### Bài 5 — Nhận diện báo cờ sai

Một nguồn đọc file từng dòng từ BufferedReader, chưa biết số dòng nhưng trả `Spliterator.SIZED` và `estimateSize() == 1000` chỉ vì file có khoảng 1000 dòng. Đúng không?

**Đáp án:** không. SIZED là cam kết kích thước chính xác, không phải ước lượng đại khái. Nguồn phải bỏ SIZED nếu không thể xác định chính xác số phần tử còn lại.

### Bài 6 — Phân biệt lười mở và lười xử lý

Một API gọi `Files.lines(path)` rồi mới thêm `filter(...)` nhưng không gọi terminal. Các lambda filter đã chạy chưa? File đã có khả năng được mở chưa?

**Đáp án:** các lambda filter chưa cần chạy. Nhưng Files.lines là API tạo Stream gắn resource đã mở; phải đóng Stream kịp thời ngay cả khi không thực thi terminal.

### Bài 7 — Nguồn vô hạn và sort

Đoạn `Stream.iterate(0, n -> n + 1).sorted().limit(3).toList()` có nên dùng không?

**Đáp án:** không. Sorted tổng quát cần xét toàn nguồn để xác định thứ tự, không thể chờ hết một nguồn vô hạn. Nếu ý định là sắp ba số đầu, đặt `limit(3)` trước sorted, nhưng phải hiểu rằng yêu cầu nghiệp vụ đã khác.

### Bài 8 — Trách nhiệm close của một factory

Bạn viết `Stream<String> openRecords(Path path)` trả Stream đọc file. Ai phải đóng?

**Gợi ý:** nếu factory chuyển ownership cho caller, tài liệu API phải nói rõ caller dùng `try (Stream<String> records = openRecords(path)) { ... }`. Factory cần đăng ký close handler hoặc dùng API resource Stream có sẵn. Nếu factory tự sở hữu resource, đừng trả Stream sống lâu hơn resource; hãy trả kết quả đã đọc hoặc thực thi callback trong phạm vi.

## 20. Ghi nhớ

**Nguồn Stream tốt phải rõ tính hữu hạn, thời điểm tạo/đọc phần tử và quyền sở hữu tài nguyên.** Ba vấn đề này khác nhau, nhưng ảnh hưởng trực tiếp đến correctness và hiệu năng.

- **Finite source:** xác định cận, điều kiện kết thúc, và kích thước khi có thể bảo đảm.
- **Potentially unbounded source:** dùng `limit` hoặc điều kiện dừng hợp lệ; chú ý stateful operations như sorted.
- **Custom Spliterator:** triển khai `tryAdvance` chính xác, `trySplit` không chồng lấp, `estimateSize` và characteristics đúng hợp đồng.
- **Late-binding:** overload `StreamSupport.stream(Supplier, characteristics, parallel)` có thể trì hoãn việc tạo Spliterator; bộ cờ phải khớp với Spliterator thực.
- **Lazy traversal không nhất thiết lazy-open:** một Stream đọc file có thể giữ resource trước khi terminal chạy.
- **Terminal không tự đóng Stream:** quản lý file, reader, cursor bằng `try-with-resources` và `onClose` khi phù hợp.
- **Ownership rõ:** ai mở/nhận resource chịu trách nhiệm đóng đúng thời điểm, kể cả khi terminal thất bại hoặc short-circuit.
- **Parallel phải được thiết kế riêng:** phân chia an toàn, không dùng mutable state chung hoặc công bố đặc tính sai.

Trước khi đưa một nguồn tùy chỉnh vào ứng dụng, hãy tự hỏi: **“Khi nào nguồn kết thúc? Ai sinh phần tử? Có thể dừng sớm và chia nguồn đúng không? Resource mở lúc nào và sẽ được đóng ở đâu nếu không có terminal, terminal thành công hoặc terminal ném lỗi?”** Nếu trả lời được các câu hỏi đó bằng một hợp đồng rõ ràng, Stream mới thực sự dễ sử dụng và an toàn.
