# Giới hạn khi khai báo collector đồng thời trong Java Stream

Một custom `Collector` có thể làm việc với `parallelStream()` mà **không cần** khai báo `Collector.Characteristics.CONCURRENT`. Điểm khác biệt của `CONCURRENT` là: Stream framework **được phép gọi hàm `accumulator` đồng thời trên cùng một đối tượng tích lũy** nếu các điều kiện về parallel và ordering phù hợp. Vì thế, việc thêm cờ `CONCURRENT` là **một lời cam kết về tính an toàn luồng và ngữ nghĩa kết quả**, không phải mẹo để biến collector bình thường thành nhanh hơn.

Bài học này tập trung vào các giới hạn khi tự khai báo collector đồng thời thuộc chủ đề **Collector tùy biến**. Các API `java.util.stream.Collector`, `Collector.of`, `Collector.Characteristics`, `LongAdder` và `ConcurrentHashMap` ở đây vẫn phù hợp với Java hiện đại, ví dụ sử dụng API từ Java 8 và chạy được trên JDK 17+.

## 1. Phân biệt *parallel collection* và *concurrent reduction*

**Parallel collection**: Stream có thể chia dữ liệu thành nhiều nhánh. Với collector không có `CONCURRENT`, mỗi nhánh có thể tích lũy vào một container riêng, rồi `combiner` ghép các kết quả. Ví dụ `Collectors.toList()` thường được dùng an toàn với `parallelStream()` dù `ArrayList` bên trong không tự thread-safe: framework thực thi theo hợp đồng collector và quản lý các container độc lập.

**Concurrent reduction**: Nhiều task có thể tích lũy **cùng một container** nếu collector khai báo `CONCURRENT` và điều kiện ordering cho phép. Lúc đó mã `accumulator` phải xử lý được các lời gọi đồng thời.

~~~text
Không CONCURRENT, parallel:
    task 1 → container A ─┐
                          ├── combiner → result
    task 2 → container B ─┘

CONCURRENT, parallel và không ràng buộc encounter order:
    task 1 ───┐
              ├── accumulator → shared container → finisher → result
    task 2 ───┘
~~~

Hai hình trên là mô hình tư duy, **không ràng buộc chi tiết phân nhánh hoặc số thread** của JVM. `CONCURRENT` không khiến `stream()` tự chạy song song; phải có stream parallel. Với lượng dữ liệu nhỏ, triển khai có thể có ít hoặc không có hoạt động song song thực tế.

Điều kiện để Stream API thực hiện concurrent reduction là **đủ cả ba**:

1. Stream đang ở chế độ parallel.
2. Collector có `Collector.Characteristics.CONCURRENT`.
3. **Stream là unordered hoặc collector có `Collector.Characteristics.UNORDERED`.**

Với nguồn `List` có encounter order, collector chỉ gắn `CONCURRENT` mà không gắn `UNORDERED` **không được framework dùng theo lối concurrent reduction trên một nguồn ordered**. Có thể gọi `stream.unordered()` khi yêu cầu thực sự không cần thứ tự; không làm thế chỉ để ép tốc độ.

## 2. Ba Characteristics: lời cam kết và giới hạn

| Cờ | Điều bạn cam kết | Điều không được suy diễn |
| --- | --- | --- |
| `CONCURRENT` | Hàm `accumulator` có thể được gọi từ nhiều thread **trên cùng container A** mà vẫn cho kết quả đúng. | Không có nghĩa mọi collector parallel đều cần cờ này; cũng không có nghĩa luồng xử lý tự song song. |
| `UNORDERED` | Kết quả không phải giữ nguyên **encounter order** của phần tử đầu vào. | Không có nghĩa container không thể duyệt theo một thứ tự riêng; cũng không có nghĩa kết quả có thể bỏ hoặc đếm trùng phần tử. |
| `IDENTITY_FINISH` | Hàm `finisher` thực sự là identity; kiểu tích lũy `A` có thể được ép kiểu an toàn thành kiểu kết quả `R`. | Không được khai báo nếu `finisher` chuyển `LongAdder → Long`, `StringBuilder → String` hoặc biến đổi kiểu/giá trị kết quả. |

Ví dụ: collector tính **tổng** có thể là `CONCURRENT + UNORDERED` vì tổng không phụ thuộc thứ tự phần tử theo đại số số nguyên. Collector tạo **danh sách giữ encounter order** không thể khai báo `UNORDERED` đúng nghĩa. Collector tính tổng bằng `LongAdder` rồi trả `Long` có **finisher không phải identity**, nên không thể gắn `IDENTITY_FINISH`.

Một collector có `CONCURRENT` **không bắt buộc đồng thời có `UNORDERED`**. Trường hợp có `CONCURRENT` mà thiếu `UNORDERED` chỉ được phép concurrent reduction khi **nguồn unordered**. Ngược lại, nếu collector tự khai báo `UNORDERED`, người sử dụng phải chấp nhận kết quả không theo encounter order, kể cả nguồn ban đầu là `List`.

## 3. Bốn thành phần của custom `Collector<T, A, R>`

~~~java
Collector<T, A, R> collector = Collector.of(
    supplier,
    accumulator,
    combiner,
    finisher,
    Collector.Characteristics.CONCURRENT,
    Collector.Characteristics.UNORDERED
);
~~~

- **`T`**: kiểu phần tử của stream.
- **`A`**: kiểu container tích lũy trung gian, có thể thay đổi.
- **`R`**: kiểu kết quả cuối.
- **`supplier()`**: tạo container mới và rỗng cho mỗi lần framework yêu cầu. **Không trả về một singleton/static mutable object dùng chung giữa các lần collect**.
- **`accumulator(A,T)`**: thêm/ghi nhận một phần tử. Khi có `CONCURRENT`, phải an toàn khi nhiều thread gọi trên cùng `A`.
- **`combiner(A,A)`**: kết hợp hai kết quả tích lũy; phải đúng ngay cả khi triển khai có lúc không dùng shared accumulation hoặc khi tái cấu trúc pipeline. **Không trả về một kết quả bỏ mất một nhánh**.
- **`finisher(A) -> R`**: chuyển kết quả cuối. Với kiểu `A` khác `R`, không khai báo `IDENTITY_FINISH`.

Điểm quan trọng: **`CONCURRENT` chỉ nói về khả năng tích lũy trên cùng `A`**, chứ không thay thế hợp đồng identity/associativity/compatibility của `combiner`. Một collector phải có kết quả tương đương khi Stream chia dữ liệu, kết hợp theo các cách hợp lệ và khi chạy tuần tự.

### Identity của combiner

Giả sử `a` là kết quả tích lũy từ một số phần tử, `empty = supplier.get()`. Kết hợp thêm container rỗng phải không thay đổi kết quả ngữ nghĩa:

~~~text
combiner(a, empty) ≃ a
~~~

Ký hiệu `≃` nghĩa là **tương đương về kết quả được cam kết**, không yêu cầu hai đối tượng mutable có cùng reference. Với bộ đếm, container rỗng mang giá trị 0. Với set, container rỗng là tập rỗng.

### Associativity và compatibility

Kết hợp các nhóm theo nhiều cách vẫn phải cho kết quả tương đương:

~~~text
combine(combine(a, b), c) ≃ combine(a, combine(b, c))
~~~

Đồng thời, tách phần tử vào các container rồi gộp phải có cùng ý nghĩa với tích lũy trực tiếp. Nếu container dùng dữ liệu phụ trợ, `combiner` phải gộp **đầy đủ cả trạng thái liên quan**, không chỉ một trường mà quên những trường khác.

Không nên dùng comparator hoặc phép merge phụ thuộc thời gian/thread để quyết định kết quả trong collector unordered. Với tổng số thực, phép cộng `double` có thể thay đổi ở bit cuối vì phép cộng dấu phẩy động không hoàn toàn kết hợp theo tính toán máy; yêu cầu độ chính xác/tính tái lập cao cần cách tổng hợp phù hợp.

## 4. Collector đồng thời đúng: tích lũy bằng `LongAdder`

`LongAdder` (có từ Java 8) hỗ trợ nhiều thread cộng vào một bộ đếm/tổng. Nó phù hợp để minh họa collector có **shared mutable accumulation**:

~~~java
Collector<Integer, LongAdder, Long> sumCollector = Collector.of(
    LongAdder::new,
    (sum, value) -> sum.add(value),
    (left, right) -> {
        left.add(right.sum());
        return left;
    },
    LongAdder::sum,
    Collector.Characteristics.CONCURRENT,
    Collector.Characteristics.UNORDERED
);
~~~

Vì sao hợp lệ?

1. Mỗi lần `supplier` tạo một `LongAdder` mới, ban đầu bằng `0`.
2. `LongAdder.add(value)` an toàn cho nhiều thread cập nhật cùng accumulator.
3. `combiner` cộng giá trị của hai bộ tích lũy; cộng các số nguyên có identity 0 và có tính kết hợp theo số học `long` của Java.
4. `finisher` chỉ lấy tổng `Long` sau khi `collect` hoàn tất. Khi đang có update đồng thời, `LongAdder.sum()` không phải snapshot nguyên tử; **không đọc giữa lúc đang tích lũy để coi là kết quả cuối**.
5. Tổng không phụ thuộc encounter order, nên `UNORDERED` là chính xác.
6. `A = LongAdder` khác `R = Long`, nên **không gắn `IDENTITY_FINISH`**.

Nếu tổng thực tế vượt giới hạn `long`, phép cộng có thể tràn. `LongAdder` giải quyết concurrency của phép cộng, **không bảo đảm số học vô hạn chính xác**. Khi cần tổng số học chính xác vượt miền long, dùng kiểu/thuật toán thích hợp.

**Khi nào không nên tự viết?** Nếu chỉ cần tổng số nguyên, `IntStream.sum()`, `LongStream.sum()` hoặc `reduce(0, Integer::sum)` thường ngắn, rõ và đã hỗ trợ parallel reduction đúng hợp đồng. Custom concurrent collector chỉ đáng dùng khi bạn thật sự có bài toán tích lũy riêng và đã kiểm tra hiệu năng.

## 5. Collector đồng thời đúng: đếm theo khóa bằng `ConcurrentHashMap`

Với bài toán “đếm số lần xuất hiện từng nhãn”, có thể dùng container:

~~~text
ConcurrentHashMap<String, LongAdder>
     key: nhãn → bộ đếm độc lập và an toàn luồng
~~~

`ConcurrentHashMap` cho phép cập nhật/tra cứu các khóa với bảo đảm đồng thời, còn `LongAdder` bảo vệ phép tăng đếm cho từng khóa.

Mẫu accumulator:

~~~java
(map, label) -> map.computeIfAbsent(
    label, key -> new LongAdder()
).increment()
~~~

Nếu hai thread nhìn thấy cùng một khóa, `computeIfAbsent` đảm bảo việc thiết lập ánh xạ theo hợp đồng `ConcurrentHashMap`; các thread nhận `LongAdder` của khóa rồi có thể gọi `increment` an toàn. Không dùng cách tách rời `if (!map.containsKey(key)) map.put(...)` trong mã concurrent vì có race giữa kiểm tra và cập nhật.

Mẫu combiner khi có hai map trung gian:

~~~java
(left, right) -> {
    right.forEach((key, count) -> left.computeIfAbsent(
        key, ignored -> new LongAdder()
    ).add(count.sum()));
    return left;
}
~~~

Kết quả nhận tổng đếm của cả hai nhánh. `finisher` có thể chuyển map mutable thành `TreeMap<String,Long>` để **in khóa theo thứ tự xác định**, nhưng vì biến đổi kiểu/đối tượng nên không khai báo `IDENTITY_FINISH`.

**Giới hạn quan trọng:** `ConcurrentHashMap` cấm khóa `null` và giá trị `null`. Dữ liệu đầu vào phải có nhãn hợp lệ; với tên/ngày/ID có thể null, hãy xử lý thiếu dữ liệu trước. Trong ví dụ đếm, chỉ có kết quả cuối cần ổn định; không cần giữ thứ tự gặp nhãn.

## 6. Ví dụ Java hoàn chỉnh, kết quả ổn định khi parallel

Lưu mã sau trong **`ConcurrentCollectorRulesDemo.java`**. Mã tương thích các API Java 8 và chạy được trên JDK 17+.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ConcurrentCollectorRulesDemo {

    private static Collector<Integer, LongAdder, Long> sumCollector() {
        return Collector.of(
                LongAdder::new,
                (sum, value) -> sum.add(value),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
    }

    private static Collector<String,
                             ConcurrentHashMap<String, LongAdder>,
                             Map<String, Long>> countingCollector() {
        return Collector.of(
                ConcurrentHashMap::new,
                (map, label) -> map.computeIfAbsent(
                        label, key -> new LongAdder()
                ).increment(),
                (left, right) -> {
                    right.forEach((key, count) ->
                            left.computeIfAbsent(
                                    key, ignored -> new LongAdder()
                            ).add(count.sum()));
                    return left;
                },
                map -> {
                    Map<String, Long> result = new TreeMap<>();
                    map.forEach((key, count) ->
                            result.put(key, count.sum()));
                    return result;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
    }

    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(2, 3, 5, 7, 11, 13);
        Collector<Integer, LongAdder, Long> sum = sumCollector();

        long sequential = numbers.stream().collect(sum);
        long parallel = numbers.parallelStream().collect(sum);
        long empty = new ArrayList<Integer>().parallelStream()
                .collect(sum);

        System.out.println("sequential = " + sequential);
        System.out.println("parallel = " + parallel);
        System.out.println("empty = " + empty);
        System.out.println("CONCURRENT = " +
                sum.characteristics().contains(
                        Collector.Characteristics.CONCURRENT));
        System.out.println("UNORDERED = " +
                sum.characteristics().contains(
                        Collector.Characteristics.UNORDERED));
        System.out.println("IDENTITY_FINISH = " +
                sum.characteristics().contains(
                        Collector.Characteristics.IDENTITY_FINISH));

        List<String> labels = Arrays.asList(
                "java", "sql", "java", "junit", "sql", "java");
        Map<String, Long> counts = labels.parallelStream()
                .collect(countingCollector());
        System.out.println("counts = " + counts);

        List<Integer> ordered = numbers.parallelStream()
                .collect(Collectors.toList());
        System.out.println("ordered = " + ordered);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConcurrentCollectorRulesDemo.java
java ConcurrentCollectorRulesDemo
~~~

Đầu ra **không phụ thuộc lịch chạy các thread**:

~~~text
sequential = 41
parallel = 41
empty = 0
CONCURRENT = true
UNORDERED = true
IDENTITY_FINISH = false
counts = {java=3, junit=1, sql=2}
ordered = [2, 3, 5, 7, 11, 13]
~~~

Giải thích đầu ra:

- `2+3+5+7+11+13 = 41`, không phụ thuộc thứ tự cộng với kiểu `long` ở miền này.
- Stream rỗng trả `0` vì `supplier` tạo `LongAdder` ban đầu rỗng.
- `CONCURRENT` và `UNORDERED` được khai báo chính xác; `IDENTITY_FINISH` không có vì `finisher` chuyển `LongAdder` thành `Long`.
- Các nhãn có `java` ba lần, `sql` hai lần, `junit` một lần. `TreeMap` trong finisher làm thứ tự **khóa in ra** ổn định.
- `Collectors.toList()` không cần là concurrent collector để chạy được với parallel stream. Với nguồn `List` ordered, kết quả giữ thứ tự encounter order, cho ra danh sách ban đầu.

**Lưu ý QA:** Đây là ví dụ thu thập dữ liệu song song **và chỉ đọc kết quả sau khi terminal `collect` kết thúc**. Không gọi `LongAdder.sum()` trong task cập nhật đồng thời rồi coi đó là tổng cuối.

## 7. Phản ví dụ: khai báo `CONCURRENT` sai làm hỏng dữ liệu

### 7.1. `ArrayList` dùng chung không an toàn

~~~java
// PHẢN VÍ DỤ: không chạy trong production.
Collector<Integer, List<Integer>, List<Integer>> broken =
    Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.CONCURRENT,
        Collector.Characteristics.UNORDERED
    );
~~~

Đoạn trên là **mã minh họa không độc lập**; cần import `java.util.ArrayList`, `List` và `Collector`. `ArrayList.add` không an toàn cho nhiều thread gọi đồng thời trên một `ArrayList`, nên không được khai báo `CONCURRENT`. Khi stream parallel đưa nhiều phần tử vào cùng container, có thể mất phần tử, làm hỏng cấu trúc mảng hoặc xuất hiện kết quả không xác định. Việc chạy một vài lần “có vẻ đúng” không chứng minh collector an toàn.

Cách sửa nếu thực sự cần một danh sách **giữ encounter order** là bỏ các cờ concurrent/unordered và dùng:

~~~java
List<Integer> safe = numbers.parallelStream()
    .collect(Collectors.toList());
~~~

Hoặc tự viết collector có supplier/accumulator/combiner đúng hợp đồng **không gắn `CONCURRENT`** để framework quản lý container độc lập và hợp nhất an toàn. Một `Collections.synchronizedList(...)` có thể bảo vệ từng lời gọi đơn lẻ vào list, nhưng không biến thứ tự cập nhật đồng thời thành encounter order; không được đánh dấu `UNORDERED` nếu yêu cầu chính là giữ thứ tự.

### 7.2. `IDENTITY_FINISH` sai kiểu dữ liệu

~~~java
// PHẢN VÍ DỤ: A là StringBuilder, R dự kiến là String.
Collector<String, StringBuilder, String> invalid =
    Collector.of(
        StringBuilder::new,
        StringBuilder::append,
        (left, right) -> left.append(right),
        StringBuilder::toString,
        Collector.Characteristics.IDENTITY_FINISH
    );
~~~

Đoạn này có thể biên dịch nhờ generic types, nhưng **khai báo sai hợp đồng**. Framework có quyền bỏ qua finisher và trả container trung gian `StringBuilder` như thể đó là `String`, gây lỗi kiểu hoặc kết quả sai. Phải bỏ `IDENTITY_FINISH`; overload `Collector.of` có finisher `StringBuilder::toString` chính là chỗ cần chuyển `A -> R`.

Đừng khai báo `IDENTITY_FINISH` để giảm một bước xử lý nếu `finisher` không thực sự là identity. Cờ này là sự thật về kiểu và ngữ nghĩa, không phải tùy chọn tối ưu tùy ý.

### 7.3. Supplier trả về một biến mutable dùng chung

~~~java
// PHẢN VÍ DỤ: singleton được tái sử dụng giữa nhiều lần collect.
static final LongAdder SHARED = new LongAdder();
// Supplier sai: () -> SHARED
~~~

Đây là đoạn **minh họa riêng lẻ**, không phải một lớp Java đầy đủ. Với supplier như trên, hai lần thu thập có thể cộng dồn kết quả cũ, và các phép thu thập độc lập có thể gây nhiễu lẫn nhau. Dùng `LongAdder::new` để mỗi lần tạo container rỗng mới; chỉ để Stream quản lý vòng đời các container của một lần collect.

### 7.4. Bộ đếm thường và race condition

~~~java
// PHẢN VÍ DỤ: không bảo vệ counter++.
int[] counter = {0};
Collector<Integer, int[], Integer> brokenCount = Collector.of(
    () -> new int[1],
    (array, item) -> array[0]++,
    (left, right) -> {
        left[0] += right[0];
        return left;
    },
    array -> array[0],
    Collector.Characteristics.CONCURRENT,
    Collector.Characteristics.UNORDERED
);
~~~

Đây là **đoạn minh họa**; biến `counter` không được sử dụng trong collector và chỉ gợi nhớ vấn đề đếm bằng `int[]`. `array[0]++` là một chuỗi đọc–tăng–ghi **không nguyên tử**; nếu hai thread cùng gọi, có thể mất lượt cập nhật. Dùng `LongAdder`, `AtomicInteger` hoặc đồng bộ phù hợp, rồi kiểm tra tính tương thích combiner/finisher.

## 8. Những giới hạn tinh tế: ordering, combiner, downstream

### 8.1. `CONCURRENT` không tự động hợp với yêu cầu giữ thứ tự

Nếu bạn cần kết quả `[A, B, C]` theo thứ tự xuất hiện từ `List`, không thể lấy một `ConcurrentLinkedQueue` hay synchronized list rồi tự ý gắn `UNORDERED` mà vẫn hứa giữ encounter order. Concurrent insertion xảy ra theo lịch thread, không nhất thiết trùng với thứ tự nguồn.

Muốn **đếm, tập hợp không thứ tự, tổng** thì `UNORDERED` thường hợp lý. Muốn **nối chuỗi có thứ tự, chạy phép toán phụ thuộc vị trí, lấy phần tử đầu tiên**, phải giữ thứ tự trong hợp đồng hoặc thiết kế thêm metadata vị trí rồi sort kết quả. Không nên dựa vào thread hoàn thành trước.

### 8.2. Có container thread-safe chưa đủ

`ConcurrentHashMap<K, V>` bảo vệ các thao tác map, nhưng nếu `V` là `ArrayList`, gọi `map.computeIfAbsent(key, ...).add(item)` từ nhiều thread vẫn có thể làm hỏng danh sách. Muốn đếm dùng `LongAdder`; muốn tập hợp đồng thời phải dùng vùng chứa con hỗ trợ concurrent hoặc đồng bộ đúng cách, rồi xác nhận rằng tổng thể collector vẫn đúng và không yêu cầu thứ tự.

Collector built-in như `Collectors.groupingByConcurrent(classifier, downstream)` đã có cơ chế xử lý concurrent phù hợp với downstream mà nó nhận. **Không suy diễn rằng mọi downstream như `toList()` đều tự có `CONCURRENT`.** Khi tự viết custom collector, chính người viết phải đảm bảo hợp đồng đó.

### 8.3. Combiner vẫn phải hợp lệ

Ngay cả khi concurrent reduction thường tích lũy vào một container, `combiner` vẫn là một phần hợp đồng. Hàm chỉ `return left;` và bỏ `right` là sai nếu `right` mang dữ liệu. Cần đảm bảo combiner không làm mất/đếm lặp phần tử và hợp lệ trên các container trung gian khác nhau.

Với hai container mutable độc lập, combiner có thể chọn ghi các giá trị bên phải vào bên trái rồi trả bên trái, như mẫu `LongAdder` hoặc `ConcurrentHashMap` ở trên. Nếu tự chia sẻ đối tượng giữa nhiều container, việc gộp có thể đếm hai lần hoặc gây race không mong muốn.

### 8.4. Không ép thêm `CONCURRENT` vào collector built-in

`Collectors.toList()`, `Collectors.toMap(...)`, `Collectors.groupingBy(...)` được thiết kế theo hợp đồng của riêng chúng. Không có API chuẩn cho việc “sửa bộ Characteristics” của một collector theo ý muốn mà không kiểm tra supplier/accumulator/combiner/finisher. Muốn có map concurrent, cân nhắc `Collectors.toConcurrentMap(...)` hoặc `groupingByConcurrent(...)`, nhưng vẫn phải chấp nhận quy tắc unordered và merge.

`Collector.of(supplier, accumulator, combiner)` dùng overload **không có finisher tách biệt** và khai báo `IDENTITY_FINISH` theo thiết kế vì kết quả `R = A`. Nếu cần biến container sang kiểu khác, dùng overload có finisher rồi đặt các flags đúng sự thật. Không đánh đồng `CONCURRENT` với `IDENTITY_FINISH`.

## 9. Giới hạn về tốc độ và khả năng mở rộng

**Concurrent không đồng nghĩa nhanh hơn.** Cân nhắc các yếu tố sau:

- **Tranh chấp (contention):** nhiều thread cùng cập nhật một khóa/hot counter có thể làm chậm. `LongAdder` thường phù hợp với phép cộng nhiều lượt vì giảm tranh chấp so với khóa toàn cục, nhưng thêm bộ nhớ và chi phí hơn phép cộng tuần tự.
- **Chi phí khởi tạo và điều phối:** dữ liệu nhỏ có thể chạy parallel chậm hơn sequential do split, task scheduling và tổng hợp kết quả.
- **Chi phí hash và phân bố khóa:** `ConcurrentHashMap` hoạt động tốt khi có nhiều khóa phân bố tương đối đều; nếu mọi phần tử cùng một khóa, bottleneck tích lũy vẫn tồn tại.
- **Finisher:** nếu phải sắp xếp tất cả khóa trong `TreeMap` hoặc tạo bản sao kết quả, sẽ có chi phí sau khi collect; cờ concurrent không làm chi phí này biến mất.
- **Nguồn dữ liệu/I/O:** stream parallel phù hợp tác vụ CPU và dữ liệu có thể chia; dùng mapper/accumulator có I/O hoặc phụ thuộc mutable state bên ngoài có thể tạo bottleneck hoặc hành vi khó kiểm soát.
- **Độ chính xác và số học:** tích lũy `double` trên các luồng theo thứ tự khác nhau có thể làm thay đổi bit kết quả; tổng `long` có thể tràn khi vượt miền. Các ràng buộc dữ liệu phải được đánh giá trước.
- **Khả năng quan sát:** không chứng minh tính thread-safe bằng cách nhìn một lần chạy thành công. Đo bằng workload thực tế, so sánh sequential/parallel qua kết quả và benchmark bằng JMH khi hiệu năng quan trọng.

**Dấu hiệu collector đồng thời không có lợi:** pipeline chỉ có vài trăm phần tử, phép accumulator rất rẻ, số khóa rất ít, có nhiều bước stateful/ordered hoặc phải khóa toàn cục để giữ thứ tự. Trong những trường hợp đó, collector không concurrent với combiner đúng có thể dễ hiểu và đủ nhanh hơn.

## 10. Kiểm thử bắt buộc theo hợp đồng trước khi khai báo `CONCURRENT`

Thử ít nhất những tình huống có khả năng bộc lộ lỗi:

1. **Stream rỗng:** `supplier` tạo identity đúng, `finisher` không NPE.
2. **Một phần tử:** accumulator cập nhật đúng.
3. **Nhiều phần tử:** kết quả của `stream()` và `parallelStream()` tương đương về ngữ nghĩa.
4. **Chạy lặp nhiều lần:** không rò trạng thái giữa các lần collect, không dùng supplier singleton.
5. **Khóa lặp dày:** thử 1 khóa nóng và nhiều khóa khác nhau để tìm contention, lost updates và merge sai.
6. **Nguồn ordered/unordered:** biết collector có cam kết encounter order hay không; có thể dùng `unordered()` chỉ khi nghiệp vụ cho phép.
7. **Vùng chứa mutable:** thử đồng thời khi có `CONCURRENT`, đảm bảo mọi cập nhật vào shared `A` đều thread-safe, kể cả bên trong map.
8. **Combiner:** ghép hai container chứa dữ liệu khác nhau, kiểm tra không mất/đếm lặp.
9. **Finisher/flags:** nếu `A` và `R` khác nhau, `IDENTITY_FINISH` phải vắng mặt; nếu kết quả phụ thuộc thứ tự, không khai báo `UNORDERED`.
10. **Dữ liệu biên:** `null`, tràn số, duplicate keys, kết quả cuối bị thay đổi từ bên ngoài sau collect.

Để kiểm tra tự động, so sánh **giá trị logic** như tổng, số lần xuất hiện hoặc nội dung tập hợp. Tránh so sánh iteration order của `ConcurrentHashMap` vì API không bảo đảm thứ tự đó. Nếu cần test ứng suất, kiểm thử nhiều lần với phân bố khóa khác nhau; một lần chạy đúng là chưa đủ bằng chứng.

## 11. Checklist khi quyết định gắn cờ

Trước khi viết `Collector.Characteristics.CONCURRENT`, tự hỏi:

- `accumulator` có thực sự an toàn nếu **nhiều thread cùng nhận một `A`** không?
- `supplier` có luôn tạo container mới, rỗng và không dùng chung giữa các lần collect không?
- `combiner` có giữ đủ dữ liệu, có identity và tính kết hợp theo hợp đồng không?
- Kết quả có thực sự **không cần encounter order** để được gắn `UNORDERED` không?
- `finisher` có làm biến đổi kiểu/giá trị không? Nếu có thì **không gắn `IDENTITY_FINISH`**.
- Có giá trị mutable lồng trong concurrent container khiến thao tác chưa an toàn không?
- Kết quả sequential, parallel và trường hợp stream rỗng có tương đương không?
- Dữ liệu đủ lớn và mức tranh chấp phù hợp để concurrent reduction có lợi không?

**Điều cần nhớ:** `CONCURRENT` là cam kết cho phép framework **chia sẻ accumulator A giữa nhiều thread**, còn `UNORDERED` là cam kết **không phụ thuộc encounter order**, và `IDENTITY_FINISH` là cam kết **finisher thật sự identity**. Chỉ khai báo các cờ mà collector của bạn đáp ứng đúng. Khi không chắc về tính an toàn, hãy giữ collector không concurrent và để Stream framework quản lý container trung gian.

## Tài liệu chính thức

- [Oracle Java SE 26 — `Collector`, các ràng buộc identity/associativity và `Collector.of`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html)
- [Oracle Java SE 26 — `Collector.Characteristics`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html)
- [Oracle Java SE 26 — `java.util.stream`: Concurrent reduction và ordering](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — `LongAdder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Oracle Java SE 26 — `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
