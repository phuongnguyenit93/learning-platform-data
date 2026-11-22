# Thiết kế trạng thái tích lũy an toàn cho Collector đồng thời

Trong Java Stream API, `collect()` biến các phần tử đi qua pipeline thành một kết quả tổng hợp. Khi sử dụng `parallelStream()`, nhiều luồng có thể xử lý các phần tử cùng lúc. Nếu bộ thu thập (`Collector`) cho phép những luồng đó cùng cập nhật **một vùng trạng thái tích lũy**, trạng thái phải được thiết kế để không mất dữ liệu, không hỏng cấu trúc và vẫn cho kết quả đúng dù thứ tự thực thi thay đổi.

Bài học thuộc chương **Thu thập đồng thời** của `JAVA_STREAM_API`. Trọng tâm là thiết kế accumulator dùng chung an toàn, hiểu hợp đồng của `Collector`, triển khai một collector đếm theo khóa và biết khi nào nên dùng các collector có sẵn như `groupingByConcurrent()` và `toConcurrentMap()`.

## 1. Trạng thái tích lũy nằm ở đâu trong Collector?

Về mặt kiểu dữ liệu, `Collector<T, A, R>` có ba thành phần:

- `T`: kiểu phần tử đầu vào từ stream.
- `A`: kiểu **trạng thái tích lũy trung gian** có thể thay đổi (mutable accumulation state).
- `R`: kiểu kết quả được trả về sau `collect()`.

Năm thành phần tạo nên hợp đồng của collector:

| Thành phần | Vai trò | Điều cần bảo đảm |
| --- | --- | --- |
| `supplier` | Tạo một trạng thái `A` mới | Mỗi trạng thái mới độc lập, được khởi tạo hợp lệ |
| `accumulator` | Gộp một phần tử `T` vào `A` | Cập nhật đúng; an toàn khi các luồng dùng chung `A` nếu khai báo `CONCURRENT` |
| `combiner` | Gộp hai trạng thái `A` | Không mất, nhân đôi dữ liệu; phép gộp có tính kết hợp |
| `finisher` | Chuyển `A` thành `R` | Kết quả phản ánh toàn bộ dữ liệu đã tích lũy |
| `characteristics` | Công bố khả năng của collector | Phải mô tả đúng hành vi thực tế, không khai báo chỉ để tăng tốc |

Có hai cách thực thi song song cần phân biệt:

1. **Nhiều trạng thái riêng:** các tác vụ tích lũy vào các container độc lập, sau đó gọi `combiner`. Một `HashMap` có thể dùng được trong từng tác vụ nếu không bị chia sẻ giữa các luồng.
2. **Trạng thái dùng chung:** nhiều tác vụ cùng gọi `accumulator` trên một container. Trường hợp này đòi hỏi cấu trúc dữ liệu và từng thao tác cập nhật phải an toàn đồng thời.

Khai báo `Collector.Characteristics.CONCURRENT` có nghĩa collector **cho phép** `accumulator` được gọi đồng thời trên cùng một container. Điều đó không đồng nghĩa mọi lần `collect()` đều dùng chung container: cơ chế thu thập phụ thuộc đặc tính collector, thứ tự của stream và cách triển khai.

### Ba đặc tính dễ nhầm

| Đặc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `CONCURRENT` | Accumulator hỗ trợ nhiều luồng cập nhật cùng một container | `ConcurrentHashMap` kết hợp `LongAdder` |
| `UNORDERED` | Kết quả không phụ thuộc encounter order của phần tử | Đếm số sự kiện theo loại |
| `IDENTITY_FINISH` | Kết quả `R` chính là container `A`, không cần chuyển đổi | Trả trực tiếp một map tích lũy đúng kiểu |

Với stream có encounter order, một collector `CONCURRENT` thường chỉ có thể tích lũy chung nếu collector là `UNORDERED` **hoặc** stream đã được đánh dấu không có thứ tự (ví dụ `unordered()`). Việc thêm `UNORDERED` phải xuất phát từ ngữ nghĩa bài toán: phép nối chuỗi theo thứ tự hoặc chọn “phần tử đầu tiên” không thể tùy tiện bỏ thứ tự.

## 2. Các bất biến cần có ở một trạng thái dùng chung

Một trạng thái an toàn phải thỏa **đồng thời** những yêu cầu sau:

1. **Cấu trúc container hỗ trợ đồng thời.** Dùng `ConcurrentHashMap` thay vì `HashMap` khi nhiều luồng ghi vào cùng một map.
2. **Giá trị bên trong cũng được bảo vệ.** `ConcurrentHashMap<K, V>` chỉ bảo vệ thao tác trên map; nó không biến một `ArrayList` hoặc đối tượng `V` mutable bất kỳ thành thread-safe.
3. **Cập nhật một đơn vị logic không bị tách thành kiểm tra rồi ghi.** Tránh `get()` → tính giá trị → `put()` vì các luồng có thể cùng đọc giá trị cũ rồi ghi đè nhau. Chọn `merge()`, `compute()`, `computeIfAbsent()` hoặc bộ đếm nguyên tử theo nhu cầu.
4. **Tính đúng đắn không phụ thuộc lịch chạy.** Phép gộp trong `combiner` phải có tính kết hợp; với collector `UNORDERED`, kết quả còn cần không phụ thuộc hoán vị đầu vào.
5. **Không đụng tới trạng thái bên ngoài pipeline.** Hàm phân loại nên thuần (không có side effect), dữ liệu nguồn không bị thay đổi trong khi chạy stream, và khóa dùng cho map phải có `equals()/hashCode()` ổn định.
6. **Không công bố kết quả dở dang.** Nếu cần một kết quả nhất quán, chỉ đọc snapshot cuối cùng sau khi `collect()` đã kết thúc. Đọc nhiều counter khi các luồng còn cập nhật không tạo ra snapshot nguyên tử của toàn map.

Chọn dạng trạng thái tùy phép tổng hợp:

| Bài toán | Trạng thái phù hợp | Lý do |
| --- | --- | --- |
| Đếm số phần tử theo khóa | `ConcurrentHashMap<K, LongAdder>` | `increment()` an toàn; `LongAdder` thường giảm tranh chấp khi nhiều luồng cùng tăng |
| Cộng dồn số theo khóa | `ConcurrentHashMap<K, LongAdder>` hoặc `merge()` | Không mất phép cộng dưới cạnh tranh |
| Lưu tập giá trị duy nhất theo khóa | Map đồng thời + `ConcurrentHashMap.newKeySet()` | Cả map lẫn tập giá trị có thể được cập nhật đồng thời |
| Lưu danh sách theo khóa | Collector có sẵn `groupingByConcurrent()`, hoặc đồng bộ riêng ở danh sách | `ArrayList.add()` không an toàn nếu tự gọi đồng thời |
| Chọn min/max theo khóa | `ConcurrentMap.merge()` với phép chọn min/max | Phép gộp kết hợp và không phụ thuộc thứ tự |

`LongAdder` phù hợp cho tổng hợp có tần suất ghi cao. `sum()` **không phải** snapshot nguyên tử khi vẫn có cập nhật đồng thời; trong collector bên dưới, chúng ta chỉ lấy `sum()` cho kết quả cuối cùng khi mọi cập nhật đã hoàn tất.

## 3. Tự xây dựng Collector đếm đồng thời theo loại sự kiện

Giả sử hệ thống cần thống kê số sự kiện `login`, `payment`, `logout` từ danh sách log. Mỗi sự kiện được xử lý độc lập; thứ tự xuất hiện không ảnh hưởng kết quả. Ta chọn:

- `T = Event`: một sự kiện.
- `A = ConcurrentHashMap<String, LongAdder>`: map chứa bộ đếm có thể cập nhật đồng thời.
- `R = Map<String, Long>`: bản tổng hợp chỉ đọc của kết quả.

Ví dụ hoàn chỉnh, chạy với **JDK 17+**:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCollectorExample {

    record Event(String type) {}

    static Collector<Event, ?, Map<String, Long>> countingByType() {
        return Collector
            .<Event, ConcurrentHashMap<String, LongAdder>, Map<String, Long>>of(
                ConcurrentHashMap::new,

                // accumulator: được phép gọi đồng thời trên cùng một map
                (counts, event) -> {
                    String key = Objects.requireNonNull(event.type(), "event.type");
                    counts.computeIfAbsent(key, ignored -> new LongAdder())
                          .increment();
                },

                // combiner: vẫn bắt buộc để gộp các container độc lập
                (left, right) -> {
                    right.forEach((key, counter) ->
                        left.computeIfAbsent(key, ignored -> new LongAdder())
                            .add(counter.sum())
                    );
                    return left;
                },

                // finisher: tạo snapshot kết quả sau khi thu thập hoàn tất
                counts -> {
                    Map<String, Long> snapshot = new HashMap<>();
                    counts.forEach(
                        (key, counter) -> snapshot.put(key, counter.sum())
                    );
                    return Map.copyOf(snapshot);
                },

                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
            );
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
            new Event("login"),
            new Event("payment"),
            new Event("payment"),
            new Event("logout"),
            new Event("login"),
            new Event("payment")
        );

        Map<String, Long> result =
            events.parallelStream().collect(countingByType());

        Map<String, Long> expected =
            Map.of("login", 2L, "payment", 3L, "logout", 1L);

        if (!result.equals(expected)) {
            throw new AssertionError("Wrong counts: " + result);
        }

        System.out.println(result); // Thứ tự hiển thị khóa không cố định
    }
}
```

### Tại sao từng bước an toàn?

**`supplier`:** `ConcurrentHashMap::new` tạo container ban đầu. Khi triển khai stream chọn dùng nhiều container, mỗi lần gọi supplier vẫn tạo một map độc lập.

**`accumulator`:** `computeIfAbsent()` giúp khởi tạo bộ đếm cho một khóa một cách an toàn khi nhiều luồng cùng nhìn thấy khóa mới. Sau đó, `LongAdder.increment()` thực hiện tăng đếm an toàn. Map đồng thời bảo vệ cấu trúc khóa; `LongAdder` bảo vệ giá trị mutable bên trong.

**`combiner`:** với mỗi khóa của map bên phải, ta thêm tổng đếm vào bộ đếm tương ứng bên trái. `right` không bị sửa; `left` được trả về. Đẳng thức cần bảo toàn là:

```text
count(merge(left, right), key) = count(left, key) + count(right, key)
```

Phép cộng có tính kết hợp và giao hoán, nên cách phân chia các tác vụ không làm thay đổi số đếm. Dù một luồng thu thập dùng chung map và hiếm khi cần combiner, **không được bỏ qua hoặc viết combiner giả**: hợp đồng collector vẫn yêu cầu nó hoạt động đúng.

**`finisher`:** sau khi terminal operation hoàn thành, biến các `LongAdder` thành `Long` và trả về `Map.copyOf()`. Người gọi không thể sửa kết quả qua `put()` hoặc `remove()`, và không được tiếp cận map tích lũy trung gian.

**`characteristics`:** `CONCURRENT` là đúng vì container và các phép cập nhật đều hỗ trợ đồng thời; `UNORDERED` là đúng vì số đếm không phụ thuộc thứ tự. Ta **không** khai báo `IDENTITY_FINISH` vì `A` và `R` khác kiểu, đồng thời finisher phải tạo snapshot.

> Lưu ý: `ConcurrentHashMap` không cho phép khóa hoặc giá trị `null`. Trong ví dụ, `Objects.requireNonNull()` chủ động báo lỗi nếu sự kiện không có loại. Khi dùng khóa là đối tượng mutable, tuyệt đối tránh thay đổi trường tham gia `equals()`/`hashCode()` sau khi đưa khóa vào map.

## 4. Khi nào nên dùng collector có sẵn?

Trước khi viết collector tùy chỉnh, kiểm tra xem thư viện đã cung cấp phép tổng hợp tương đương hay chưa. Với bài toán đếm theo loại, hai cách dưới đây ngắn gọn hơn:

```java
// Cách 1: Gom nhóm đồng thời rồi đếm từng nhóm
Map<String, Long> counts1 = events.parallelStream()
    .collect(java.util.stream.Collectors.groupingByConcurrent(
        Event::type,
        java.util.stream.Collectors.counting()
    ));

// Cách 2: Chuyển trực tiếp từng sự kiện thành 1 và cộng khi trùng khóa
Map<String, Long> counts2 = events.parallelStream()
    .collect(java.util.stream.Collectors.toConcurrentMap(
        Event::type,
        event -> 1L,
        Long::sum
    ));
```

Cả hai cho cùng số đếm trong ví dụ. `groupingByConcurrent()` thích hợp khi cần phân nhóm và có thể thay downstream collector, chẳng hạn `counting()`, `mapping()` hoặc `summarizingLong()`. `toConcurrentMap()` phù hợp khi mỗi phần tử tạo ra cặp khóa/giá trị và có hàm gộp rõ ràng.

Hàm gộp `Long::sum` có tính kết hợp và giao hoán. Ngược lại, phép gộp như “giữ chuỗi được gặp trước” có thể cho kết quả khác nhau khi các luồng chạy theo lịch khác nhau; không nên dùng nếu yêu cầu bảo toàn thứ tự.

**Cần phân biệt an toàn của collector với an toàn của kết quả.** `groupingByConcurrent(classifier)` mặc định có thể tạo `ConcurrentMap<K, List<T>>`. Collector quản lý an toàn quá trình gom nhóm, nhưng các `List<T>` trong map không được bảo đảm là thread-safe cho thao tác sửa đổi đồng thời **sau khi** `collect()` trả về.

### Chọn `groupingBy()` hay `groupingByConcurrent()`

`groupingBy()` có thể chạy trong parallel stream bằng cách sử dụng các map riêng rồi kết hợp chúng, và kết quả mặc định là `Map`. `groupingByConcurrent()` là collector đồng thời, không bảo đảm thứ tự phần tử của từng nhóm và cho ra `ConcurrentMap`. Vì vậy:

- Chọn `groupingBy()` nếu cần giữ encounter order khi đưa phần tử vào danh sách trong từng nhóm.
- Xem xét `groupingByConcurrent()` nếu bỏ qua thứ tự và các nhóm đủ lớn để có lợi từ tích lũy đồng thời.
- Chọn collector tùy chỉnh khi cần trạng thái, logic tích lũy hoặc kiểu kết quả mà collector có sẵn không thể biểu diễn rõ ràng.

Không thể kết luận phiên bản concurrent luôn nhanh hơn chỉ từ tên API. Số phần tử ít, số khóa quá ít gây tranh chấp cao, hoặc chi phí điều phối tác vụ có thể khiến `stream()` tuần tự chạy nhanh hơn.

## 5. Những lỗi thường gặp

### Lỗi 1: Dùng chung HashMap trong forEach song song

```java
Map<String, Long> counts = new HashMap<>();

// SAI: nhiều luồng cùng đọc/ghi HashMap không đồng bộ
events.parallelStream().forEach(event ->
    counts.merge(event.type(), 1L, Long::sum)
);
```

`HashMap.merge()` không có hợp đồng an toàn đồng thời. Kết quả có thể bị đếm thiếu hoặc cấu trúc map bị lỗi. Sửa bằng `collect(Collectors.toConcurrentMap(...))` hoặc một collector an toàn như phần 3.

### Lỗi 2: Map đồng thời nhưng giá trị không đồng thời

```java
var groups =
    new ConcurrentHashMap<String, java.util.List<Event>>();

// SAI: nhiều luồng có thể gọi ArrayList.add() trên cùng danh sách
events.parallelStream().forEach(event ->
    groups.computeIfAbsent(event.type(),
                           ignored -> new java.util.ArrayList<>())
          .add(event)
);
```

`computeIfAbsent()` chỉ đảm bảo tạo/tra cứu giá trị map an toàn. Nó không đồng bộ các lệnh `add()` tiếp theo. Có thể dùng `groupingByConcurrent(Event::type)` cho tác vụ gom nhóm thông thường, hoặc thiết kế container giá trị có cơ chế đồng bộ tương ứng.

### Lỗi 3: Đọc rồi ghi thay vì cập nhật nguyên tử

```java
// SAI nếu nhiều luồng cùng thao tác trên counts
Long oldValue = counts.get(key);
counts.put(key, oldValue == null ? 1L : oldValue + 1L);
```

Hai luồng có thể cùng thấy giá trị cũ là `5` và đều ghi `6` thay vì `7`. Với `ConcurrentMap<String, Long>`, dùng `counts.merge(key, 1L, Long::sum)`; với `ConcurrentHashMap<String, LongAdder>`, dùng `computeIfAbsent(...).increment()`.

### Lỗi 4: Khai báo CONCURRENT cho accumulator không an toàn

`Collector.Characteristics.CONCURRENT` là một lời cam kết với bộ máy Stream, không phải cơ chế khóa hay công cụ tự động biến code thành thread-safe. Nếu accumulator sửa `ArrayList`, `HashMap` hoặc trường `long` thông thường dùng chung mà thiếu bảo vệ, việc thêm đặc tính này khiến collector có thể sai dưới parallel stream.

### Lỗi 5: Nhầm snapshot cuối với truy vấn đang chạy

`LongAdder.sum()` phù hợp để lấy tổng sau khi pipeline kết thúc. Nếu một dashboard cần snapshot nhất quán tại bất kỳ thời điểm nào **trong lúc** nhiều luồng còn ghi, chỉ đọc lần lượt các `LongAdder` là chưa đủ. Bài toán đó cần giao thức snapshot hoặc đồng bộ riêng.

### Lỗi 6: Combiner làm sai phép tổng hợp

Nếu `combiner` chỉ trả về map bên trái mà không gộp map bên phải, các kết quả có thể bị mất trong cách chạy chia nhiều container. Nếu gộp cùng một bộ đếm hai lần, kết quả bị nhân đôi. Tính đúng đắn của collector phải giữ trong cả hai trường hợp: tích lũy tuần tự và tích lũy vào nhiều container rồi gộp.

## 6. Kiểm tra tính đúng đắn và đo hiệu năng

Một cách kiểm thử có ý nghĩa là so sánh với kết quả tuần tự đáng tin cậy, lặp lại nhiều lần để tăng khả năng gặp lịch chạy khác nhau và sử dụng tập dữ liệu đủ lớn:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

// Chèn vào main của ConcurrentCollectorExample để thử với tải lớn:
List<Event> many = IntStream.range(0, 100_000)
    .mapToObj(i -> new Event(i % 4 == 0 ? "payment" : "login"))
    .toList();

Map<String, Long> reference = many.stream()
    .collect(Collectors.groupingBy(Event::type, Collectors.counting()));

for (int attempt = 0; attempt < 100; attempt++) {
    Map<String, Long> actual =
        many.parallelStream().collect(countingByType());

    if (!actual.equals(reference)) {
        throw new AssertionError(
            "Mismatch at attempt " + attempt + ": " + actual
        );
    }
}
```

Kiểm tra thêm các trường hợp stream rỗng, chỉ một khóa (tranh chấp cao), rất nhiều khóa, khóa `null` và các trường hợp dữ liệu không đồng đều. Chỉ có test thành công chưa chứng minh collector an toàn; phải kết hợp với việc kiểm tra bất biến và hợp đồng ở phần 2.

Khi đo hiệu năng, so sánh `stream()` với `parallelStream()` trên **cùng lượng dữ liệu**, cùng kết quả, sau giai đoạn làm nóng JVM và chạy nhiều lượt. Với phép đo có tính quyết định, dùng JMH để kiểm soát warm-up, fork và cách tiêu thụ kết quả. Không thực hiện I/O hoặc thao tác chặn trong accumulator của một parallel stream tính toán CPU.

## 7. Bài tập áp dụng

Giả sử mỗi `Event` có thêm `userId`. Hãy thiết kế collector trả về số người dùng **khác nhau** theo `type`:

1. Chọn trạng thái `ConcurrentHashMap<String, Set<String>>`, trong đó tập cho từng khóa được tạo bằng `ConcurrentHashMap.newKeySet()`.
2. Dùng `computeIfAbsent()` để tạo tập và `add()` để tích lũy `userId` đồng thời.
3. Viết `combiner` bằng cách hợp nhất các tập theo khóa; ở `finisher`, chuyển mỗi tập thành kích thước của nó và trả về map kết quả bất biến.
4. Tự giải thích vì sao collector có thể khai báo `CONCURRENT` và `UNORDERED` nhưng không được khai báo `IDENTITY_FINISH`.

Thử nghiệm với hai luồng cùng gửi nhiều sự kiện cho một `userId`: kết quả theo loại vẫn phải tính người dùng đó đúng **một lần**, bất kể số lần xuất hiện.

## 8. Ghi nhớ

Để thiết kế một concurrent collector đúng, cần chứng minh **cả container lẫn giá trị mutable bên trong** có thể cập nhật an toàn, phép gộp tuân thủ hợp đồng collector và đặc tính công bố đúng với ngữ nghĩa của phép tổng hợp. Tính an toàn đồng thời bắt đầu từ lựa chọn trạng thái `A` và các thao tác trên nó; `CONCURRENT` chỉ cho Stream biết collector đã đáp ứng yêu cầu đó.

Với các bài toán thường gặp, hãy ưu tiên `groupingByConcurrent()` hoặc `toConcurrentMap()`. Chỉ tự triển khai khi cần kiểm soát accumulator, combiner hoặc finisher, và luôn đối chiếu kết quả tuần tự, song song trước khi đánh giá hiệu năng.
