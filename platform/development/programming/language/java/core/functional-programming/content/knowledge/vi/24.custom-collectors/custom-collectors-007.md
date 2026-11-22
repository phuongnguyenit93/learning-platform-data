# `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT` trong Java Collector tùy chỉnh

Trong Java Stream API, `Collector<T, A, R>` mô tả cách **thu thập các phần tử kiểu `T`** vào **container trung gian kiểu `A`**, rồi tạo ra **kết quả kiểu `R`**. Khi xây dựng collector tùy chỉnh, ngoài các hàm `supplier`, `accumulator`, `combiner` và `finisher`, Java còn cho phép khai báo các **đặc tính** (*characteristics*) của collector:

- `Collector.Characteristics.IDENTITY_FINISH`
- `Collector.Characteristics.UNORDERED`
- `Collector.Characteristics.CONCURRENT`

Đây là các **cam kết về hành vi**, không phải nhãn trang trí hay nút bật hiệu năng. Stream framework có thể dựa vào chúng để quyết định cách thu thập dữ liệu, đặc biệt khi `parallelStream()` được sử dụng. Khai báo sai có thể làm kết quả sai thứ tự, mất phần tử, có race condition hoặc trả đối tượng không đúng kiểu.

Ví dụ kết quả mong muốn:

~~~java
List<String> words = List.of("beta", "alpha", "beta", "gamma");
List<String> keptOrder = words.parallelStream()
        .collect(Collectors.toList()); // [beta, alpha, beta, gamma]
~~~

Ở đây `toList()` có thể gom dữ liệu từ nhiều nhánh song song mà vẫn tạo kết quả theo encounter order của nguồn `List`. Điều đó **không** đồng nghĩa một `ArrayList` dùng chung đã được nhiều thread ghi an toàn. Khi không tuyên bố `CONCURRENT`, framework có thể tạo những container trung gian riêng, rồi dùng `combiner` để hợp nhất.

## 1. Kiến trúc collector: năm yếu tố liên quan

Xét khai báo tổng quát:

~~~java
Collector<T, A, R> collector = ...;
R result = stream.collect(collector);
~~~

Các thành phần chính:

| Thành phần | Kiểu khái niệm | Nhiệm vụ |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Cấp phát một container `A` mới |
| `accumulator()` | `BiConsumer<A, T>` | Đưa một phần tử `T` vào container `A` |
| `combiner()` | `BinaryOperator<A>` | Ghép hai container `A` thành một container `A` |
| `finisher()` | `Function<A, R>` | Chuyển container trung gian `A` thành kết quả `R` |
| `characteristics()` | `Set<Characteristics>` | Công bố các đặc tính mà collector thật sự bảo đảm |

Trong một pipeline tuần tự, có thể chỉ thấy một container và việc gọi accumulator tuần tự. Với pipeline song song, framework có thể tạo nhiều container, tích lũy độc lập rồi ghép bằng combiner, hoặc có thể dùng chiến lược concurrent reduction khi điều kiện cho phép.

Mô hình minh họa:

~~~text
Stream<T>
   |
   +--> supplier() --> A1 --accumulate(T)--> A1'
   |
   +--> supplier() --> A2 --accumulate(T)--> A2'
                                 |
                                 v
                          combiner(A1', A2')
                                 |
                                 v
                           A (container)
                                 |
                          finisher(A)
                                 |
                                 v
                            R (result)
~~~

Đồ thị này **không** là trình tự bắt buộc của mọi lần chạy: collector concurrent có thể nhận phần tử từ nhiều thread trên cùng container; thứ tự và số lần gọi supplier/combiner cũng không được suy diễn chỉ từ số phần tử đầu vào. Cần hiểu **hợp đồng**, không phụ thuộc vào một cách thực thi cụ thể.

Ba characteristic chính xác là các enum constant nằm trong `java.util.stream.Collector.Characteristics`. Không có characteristic `ORDERED`: nếu collector không khai báo `UNORDERED`, điều đó cho phép framework bảo toàn những yêu cầu encounter order phù hợp với collector.

## 2. `IDENTITY_FINISH`: kết quả chính là container tích lũy

`IDENTITY_FINISH` biểu thị **bước hoàn tất có thể bị bỏ qua**: có thể xem container trung gian `A` cũng chính là kết quả `R`. Về hợp đồng, điều đó đòi hỏi phép chuyển container thành kết quả là phép đồng nhất (*identity*) và kiểu container phải tương thích trực tiếp với kiểu kết quả.

Ví dụ gom vào `ArrayList`:

~~~java
Collector<String, ?, List<String>> listCollector = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

Đoạn minh họa cần import `Collector`, `ArrayList`, `List`. `supplier` tạo một list, `accumulator` thêm từng phần tử, `combiner` nối hai list và trả list bên trái. Không có phép biến đổi kết quả sau cùng: `A` là list tích lũy và `R` cũng là list.

**Quan trọng:** overload `Collector.of(supplier, accumulator, combiner)` **ngầm khai báo `IDENTITY_FINISH`**. Khi dùng overload ba tham số, `finisher` về bản chất là hàm đồng nhất, vì vậy không cần chỉ định cờ này thêm.

Ngược lại, với collector có container `StringJoiner` nhưng muốn kết quả là `String`:

~~~java
Collector<String, StringJoiner, String> joining = Collector.of(
        () -> new StringJoiner("|"),
        StringJoiner::add,
        StringJoiner::merge,
        StringJoiner::toString
);
~~~

`A` là `StringJoiner`, `R` là `String`. `finisher` bắt buộc chuyển `StringJoiner` sang `String`; **không được** gắn `IDENTITY_FINISH`. Nếu khai báo sai, framework được phép bỏ finisher và dùng container trung gian làm kết quả; có thể dẫn đến kiểu kết quả sai hay `ClassCastException` ở nơi tiêu thụ.

### Hợp đồng không chỉ là cùng generic type

Ngay cả khi `A` và `R` có cùng kiểu khai báo, nếu finisher thực sự **biến đổi** container (ví dụ tạo bản sao không cho sửa, chuẩn hóa nội dung hoặc mã hóa kết quả), nó cũng **không phải identity finisher**.

~~~java
Collector<String, List<String>, List<String>> snapshot = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        List::copyOf
);
~~~

Đây là đoạn minh họa, cần `Collector`, `ArrayList`, `List`. `List.copyOf` tạo kết quả không sửa được và từ chối phần tử `null`; nó không phải hàm đồng nhất trên một `ArrayList` có thể thay đổi. Vì vậy không khai báo `IDENTITY_FINISH`. Đừng dựa vào kiểu kết quả `List<String>` để kết luận finisher đồng nhất.

## 3. `UNORDERED`: kết quả không phụ thuộc encounter order

`UNORDERED` có nghĩa collector **không cam kết giữ encounter order** của phần tử đầu vào. Khi collector có đặc tính này, framework có thể tận dụng việc không phải bảo toàn thứ tự nguồn để tổ chức thực thi.

Các trường hợp điển hình:

- Gom vào `Set` khi chỉ quan tâm **tập giá trị phân biệt**, không quan tâm thứ tự xuất hiện.
- Tính thống kê có tính kết hợp/giao hoán thích hợp và không có logic chọn phần tử dựa trên "đến trước".
- Thu thập vào một map keyed theo giá trị, nếu ý nghĩa kết quả không phụ thuộc thứ tự phần tử được chèn.

`UNORDERED` **không bắt buộc nguồn phải là unordered**. Một nguồn `List` có encounter order rõ ràng vẫn có thể được xử lý bởi unordered collector; lúc đó collector tuyên bố không có yêu cầu duy trì order ấy trong kết quả của mình.

~~~java
Set<String> unique = List.of("B", "A", "B")
        .parallelStream()
        .collect(Collectors.toSet());
~~~

`Collectors.toSet()` có đặc tính unordered: tập kết quả chứa `A` và `B`, nhưng **thứ tự duyệt/in Set không được bảo đảm**. `UNORDERED` không đồng nghĩa "kết quả tự động sort"; thậm chí một container có cấu trúc riêng như Set cũng cần xem hợp đồng của từng collector và collection.

### Khi không nên khai báo `UNORDERED`

Nếu kết quả là một `List` mà nghiệp vụ cần giữ thứ tự xuất hiện:

~~~java
List<String> ordered = List.of("B", "A", "B").parallelStream()
        .collect(Collectors.toList());
// [B, A, B]
~~~

Đừng tùy tiện thêm `UNORDERED` vào một collector tương tự nếu kết quả phải giữ đúng thứ tự gốc. Khi collector yêu cầu "phần tử đầu tiên", "thứ tự chèn" hoặc format văn bản theo thứ tự nguồn, thứ tự là **một phần của ngữ nghĩa**.

Đặc biệt, phép nối chuỗi có dấu phân cách (như `beta|alpha|beta|gamma`) thường phụ thuộc thứ tự; nếu gắn `UNORDERED` thì kết quả có thể khác yêu cầu.

### "Không cam kết thứ tự" khác "thứ tự ngẫu nhiên"

`UNORDERED` không bắt framework cố ý đảo phần tử, và một lần chạy có thể tình cờ cho kết quả giống đầu vào. Sai lầm là **viết bài test dựa vào sự trùng hợp này**. Nếu cần trình bày ổn định một `Set`, hãy sắp xếp lúc xuất:

~~~java
List<String> display = unique.stream().sorted().toList();
~~~

Đây là List đã sort mới, không phải bằng chứng rằng unordered collector giữ thứ tự.

## 4. `CONCURRENT`: accumulator có thể chạy đồng thời trên cùng container

`CONCURRENT` tuyên bố collector được thiết kế để `accumulator` có thể được nhiều thread gọi **đồng thời trên cùng một container kết quả**. Cờ này nói về **khả năng tích lũy an toàn đồng thời**, không phải chỉ việc Stream chạy song song.

Ví dụ collector dùng Set tạo từ `ConcurrentHashMap.newKeySet()`:

~~~java
Collector<String, ?, Set<String>> concurrentUnique = Collector.of(
        () -> ConcurrentHashMap.<String>newKeySet(),
        Set::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        },
        Collector.Characteristics.UNORDERED,
        Collector.Characteristics.CONCURRENT
);
~~~

Đoạn minh họa cần `java.util.Set`, `java.util.concurrent.ConcurrentHashMap` và `java.util.stream.Collector`. `newKeySet()` là một Set hỗ trợ cập nhật đồng thời; `add` có thể được gọi từ nhiều thread cho cùng container. `combiner` vẫn phải có hợp đồng hợp nhất đúng và không được bỏ qua khi triển khai Stream chọn cách thu thập bằng các container riêng.

**Điểm dễ bỏ sót:** overload `Collector.of(supplier, accumulator, combiner, characteristics...)` vẫn là overload không có finisher riêng, nên **`IDENTITY_FINISH` được thêm ngầm**. Với collector này, tập characteristic thực tế có cả `IDENTITY_FINISH`, `UNORDERED` và `CONCURRENT`.

### Điều kiện concurrent reduction thực tế

Ngay cả khi Stream song song và collector có `CONCURRENT`, framework chỉ **được phép** dùng một container chung để tích lũy đồng thời khi **Stream là unordered hoặc collector có `UNORDERED`**. Có thể đọc logic khái quát:

~~~text
parallel
  AND collector.CONCURRENT
  AND (stream.unordered OR collector.UNORDERED)
  -> Có thể chọn concurrent reduction trên cùng container
~~~

Không được diễn giải điều kiện này như cam kết framework **bắt buộc** dùng nhiều thread hay chắc chắn tăng tốc. Nó là điều kiện cho phép một chiến lược thực thi. Nếu collector có `CONCURRENT` nhưng không `UNORDERED` và nguồn vẫn ordered, framework không được mặc nhiên phá encounter order; có thể sử dụng các accumulator riêng rồi kết hợp để bảo toàn yêu cầu.

Ngược lại, một **collector không có `CONCURRENT` vẫn có thể dùng trong `parallelStream()`**: framework tích lũy ở nhiều container riêng, sau đó sử dụng combiner. Không gắn `CONCURRENT` chỉ vì người gọi có thể dùng stream song song.

### Cờ không thay thế cấu trúc dữ liệu thread-safe

Đây là ví dụ **sai**:

~~~java
// Không thực thi ví dụ này; ArrayList::add không an toàn
// khi nhiều thread cập nhật cùng một ArrayList.
// Collector<String, ?, List<String>> wrong = Collector.of(
//         ArrayList::new,
//         List::add,
//         (a, b) -> { a.addAll(b); return a; },
//         Collector.Characteristics.CONCURRENT,
//         Collector.Characteristics.UNORDERED
// );
~~~

Tuyên bố `CONCURRENT` có thể khiến framework gọi `ArrayList.add` đồng thời trên cùng list, gây race, mất phần tử hoặc làm hỏng cấu trúc. `UNORDERED` cũng không sửa được lỗi an toàn luồng. Nếu dùng một `ArrayList` thường, **không** khai báo `CONCURRENT`; framework có thể tự chia container cho các nhánh song song.

Một collector concurrent hợp lệ cũng phải đảm bảo **mọi trạng thái mutable mà accumulator chạm tới** được bảo vệ phù hợp, kể cả bộ đếm, map phụ hoặc object chứa bên trong. Chỉ dùng `ConcurrentHashMap` bên ngoài không tự làm mọi đối tượng giá trị trong map trở nên thread-safe.

## 5. Mối quan hệ giữa ba characteristic

Các đặc tính **độc lập về mặt khái niệm**, nhưng sự phối hợp của chúng ảnh hưởng chiến lược thu thập:

| `IDENTITY_FINISH` | `UNORDERED` | `CONCURRENT` | Ý nghĩa thiết kế |
| --- | --- | --- | --- |
| Có | Không | Không | Container chính là kết quả; có thể cần giữ encounter order |
| Không | Không | Không | Finisher tạo kiểu/giá trị khác; có thể cần giữ encounter order |
| Có | Có | Không | Container là kết quả; không cam kết thứ tự; dùng combiner khi song song |
| Có | Có | Có | Container là kết quả; không cam kết thứ tự; có thể tích lũy đồng thời trên cùng container |
| Không | Có | Có | Có finisher thực sự và accumulator an toàn đồng thời; finisher thực hiện sau giai đoạn tích lũy |
| Có | Không | Có | Accumulator thread-safe nhưng collector vẫn cam kết ngữ nghĩa có thứ tự khi nguồn ordered |

Bảng này **không nói mọi tổ hợp tự động đúng**: cần xem dữ liệu, quy tắc tích lũy, luật kết hợp và bảo đảm thứ tự. Ngoài ra, `IDENTITY_FINISH` hoàn toàn không quyết định collector có thể dùng trong parallel stream hay không; nó chỉ quyết định khả năng bỏ qua finisher.

Quan trọng: `CONCURRENT` và `UNORDERED` **không phải từ đồng nghĩa**. Một collector có thể unordered mà không hỗ trợ cập nhật đồng thời; một collector concurrent có thể vẫn có các ràng buộc về thứ tự cần được xử lý.

### Bảng phản ví dụ ngắn

| Suy luận sai | Thực tế |
| --- | --- |
| "Có `IDENTITY_FINISH` thì result là immutable" | Không: container trả về có thể là list mutable |
| "Có `UNORDERED` thì kết quả được sắp xếp" | Không: thứ tự không được bảo đảm |
| "Có `CONCURRENT` thì mọi method của kết quả thread-safe" | Chỉ cam kết accumulator được dùng đồng thời đúng; không tự bảo vệ mọi thao tác hậu xử lý |
| "Parallel stream cần `CONCURRENT`" | Không: có thể tích lũy vào các container độc lập và combiner |
| "`CONCURRENT` làm nhanh hơn" | Không có cam kết tốc độ; phải đo |
| "Cờ chỉ giúp tối ưu, khai báo sai không sao" | Sai: framework có thể tin vào cờ và trả kết quả hỏng/sai kiểu |

## 6. Ví dụ Java 17+ đầy đủ với ba collector tùy chỉnh

Lưu file **`CollectorCharacteristicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.StringJoiner;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collector;

public class CollectorCharacteristicsDemo {
    public static void main(String[] args) {
        List<String> words = List.of("beta", "alpha", "beta", "gamma");

        Collector<String, ?, List<String>> orderedList = Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );

        Collector<String, StringJoiner, String> joined = Collector.of(
                () -> new StringJoiner("|"),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString
        );

        Collector<String, ?, Set<String>> concurrentUnique = Collector.of(
                () -> ConcurrentHashMap.<String>newKeySet(),
                Set::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.UNORDERED,
                Collector.Characteristics.CONCURRENT
        );

        System.out.println("ordered=" + words.parallelStream().collect(orderedList));
        System.out.println("joined=" + words.parallelStream().collect(joined));
        System.out.println("uniqueSorted=" + words.parallelStream()
                .collect(concurrentUnique).stream().sorted().toList());

        printFlags("orderedList", orderedList);
        printFlags("joined", joined);
        printFlags("concurrentUnique", concurrentUnique);
    }

    private static void printFlags(String name, Collector<?, ?, ?> collector) {
        Set<Collector.Characteristics> flags = collector.characteristics();
        System.out.println(name + ": identity="
                + flags.contains(Collector.Characteristics.IDENTITY_FINISH)
                + ", unordered=" + flags.contains(Collector.Characteristics.UNORDERED)
                + ", concurrent=" + flags.contains(Collector.Characteristics.CONCURRENT));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17** trở lên:

~~~bash
javac CollectorCharacteristicsDemo.java
java CollectorCharacteristicsDemo
~~~

**Stdout chính xác:**

~~~text
ordered=[beta, alpha, beta, gamma]
joined=beta|alpha|beta|gamma
uniqueSorted=[alpha, beta, gamma]
orderedList: identity=true, unordered=false, concurrent=false
joined: identity=false, unordered=false, concurrent=false
concurrentUnique: identity=true, unordered=true, concurrent=true
~~~

Giải thích:

1. `orderedList` dùng container `ArrayList`, tích lũy với `List::add` và combiner nối list. Overload ba tham số ngầm mang `IDENTITY_FINISH` nhưng không khai báo `UNORDERED` hoặc `CONCURRENT`. Parallel Stream vẫn có thể thu thập bằng các container độc lập rồi ghép, trả list theo encounter order.
2. `joined` tích lũy vào `StringJoiner` và kết thúc bằng `StringJoiner::toString`. Vì `A` và `R` khác nhau nên **không có `IDENTITY_FINISH`**. Khi nguồn ordered, kết quả nối chuỗi đúng thứ tự.
3. `concurrentUnique` dùng một container Set an toàn cho cập nhật đồng thời, bỏ trùng và không yêu cầu encounter order. `Collector.of` tự bổ sung `IDENTITY_FINISH`, đồng thời ta khai báo `UNORDERED` và `CONCURRENT`.
4. `uniqueSorted` in ra một **List đã được sorted riêng**, không dựa vào thứ tự lặp không được bảo đảm của concurrent Set.
5. Phương thức `printFlags` kiểm tra từng characteristic bằng `contains` thay vì in trực tiếp `Set<Characteristics>`, nên thứ tự hiển thị và tính chính xác của chuỗi stdout không phụ thuộc vào cách Set sắp enum.

Ví dụ này dùng `parallelStream()` để minh họa rằng **collector không concurrent vẫn dùng được trong parallel pipeline**; output vẫn đúng khi các hàm tuân thủ hợp đồng. Đoạn mã đã biên dịch bằng `javac --release 17` và stdout được kiểm chứng bằng chạy thực tế.

## 7. Đặc tính từ các collector có sẵn

Không phải mọi collector từ `Collectors` có cùng tập characteristic. Trước khi viết collector tùy chỉnh, có thể tham khảo hợp đồng các collector tương ứng:

- `Collectors.toList()` thông thường có `IDENTITY_FINISH` vì container kết quả là List tích lũy, nhưng **không** công bố kết quả loại List nào hoặc chắc chắn mutable theo hợp đồng public API. Không nên dùng `toList()` để cam kết `ArrayList`.
- `Collectors.toSet()` không yêu cầu giữ thứ tự và có thể dùng tính chất unordered. Bản thân `toSet()` không vì thế mà là collector concurrent.
- `Collectors.toUnmodifiableList()` có bước biến đổi để tạo collection không sửa được, vì vậy không được hiểu là một identity finisher.
- `Collectors.joining(delimiter)` cần tạo chuỗi kết quả từ accumulator, nên không phải bài toán identity finish giống việc trả ngay container StringJoiner.
- `Collectors.toConcurrentMap(...)` hoặc `Collectors.groupingByConcurrent(...)` cung cấp các collector concurrent/unordered khi phù hợp với trường hợp sử dụng; không được tự coi mọi collector có chữ "Map" là concurrent.

Tập characteristic cụ thể có thể được quan sát qua `collector.characteristics()`; **đừng suy ra mọi cờ chỉ từ tên collector**. Quan trọng hơn, khi tự khai báo cờ, phải hiểu và đáp ứng điều kiện mà cờ đó đại diện.

## 8. Tính kết hợp, identity và luật cho combiner

Đặc tính của Collector không thay thế các quy tắc của một phép thu thập đúng. Collector phải có:

- **Identity constraint:** ghép container đã tích lũy với một container rỗng mới phải cho kết quả tương đương container ban đầu.
- **Associativity constraint:** chia phần tử ra nhiều đoạn, tích lũy độc lập rồi kết hợp theo cấu trúc khác nhau phải cho kết quả tương đương về mặt kết quả collector hứa.
- **Tương thích supplier/accumulator/combiner/finisher:** các container được tạo, cập nhật, gộp, hoàn tất theo cùng ý nghĩa; không để sót, đếm đôi hay đổi kiểu sai.

Ví dụ accumulator cộng số `int`:

~~~java
Collector<Integer, long[], Long> sum = Collector.of(
        () -> new long[1],
        (a, n) -> a[0] += n,
        (left, right) -> {
            left[0] += right[0];
            return left;
        },
        a -> a[0]
);
~~~

Đây là đoạn minh họa, cần import `Collector`. Container `A` là `long[]`, kết quả `R` là `Long`; finisher `a -> a[0]` không phải identity. **Không** gắn `IDENTITY_FINISH`. **Không** gắn `CONCURRENT` vì cập nhật `a[0] += n` không an toàn khi nhiều thread đồng thời cập nhật cùng một mảng. Nhưng collector vẫn có thể dùng trong parallel stream khi framework tạo container riêng và dùng combiner để hợp nhất.

Chú ý kết quả `long` vẫn có thể tràn nếu tổng vượt `Long.MAX_VALUE`; với nguồn `Integer`, việc unbox `n` từ `Integer` có thể ném `NullPointerException` nếu phần tử null. Các vấn đề này thuộc thiết kế phép tính, không được giải quyết bằng characteristic.

### Combiner không được ngẫu nhiên loại bỏ một vế

Đoạn mã sai:

~~~java
// Sai: bỏ toàn bộ kết quả của nhánh bên phải.
// (left, right) -> left
~~~

Có thể tình cờ cho kết quả trong pipeline tuần tự không gọi combiner, nhưng khi parallel dữ liệu của nhánh phải bị mất. Cần hợp nhất sao cho kết quả tương đương với việc xử lý mọi phần tử đầu vào.

Với phép nối chuỗi, thứ tự ghép cũng quan trọng. Nếu kết quả phải giữ encounter order, combiner cần ghép trái trước phải, không đảo tùy tiện.

## 9. Collector concurrent và giới hạn an toàn luồng

Một container **concurrent** không tự động làm toàn bộ collector đúng:

1. `supplier` phải tạo container phù hợp; nếu tái sử dụng một container global giữa nhiều lần gọi `collect`, có thể làm trộn dữ liệu.
2. `accumulator` phải an toàn khi được gọi đồng thời trên **cùng một `A`**; bất kỳ state phụ nào cũng cần được bảo vệ.
3. `combiner` vẫn phải đúng khi framework chọn nhiều container; đừng giả định nó sẽ không bao giờ được gọi chỉ vì có `CONCURRENT`.
4. `finisher` không nên giả định chạy trước khi tích lũy hoàn tất, và cần tạo đúng kiểu `R`. Nếu trả về mutable container và người gọi tiếp tục dùng nhiều thread, hợp đồng thread-safety của **collection kết quả** cần xét riêng.
5. `UNORDERED` chỉ nên khai báo khi kết quả không phụ thuộc vào thứ tự; một cấu trúc thread-safe có thể vẫn yêu cầu order cho nghiệp vụ.

Ví dụ accumulator `ConcurrentHashMap.computeIfAbsent` rồi sửa một `ArrayList` ở value không tự an toàn nếu các thread cùng thêm vào list đó. Cần dùng container thành phần có cơ chế đồng bộ, hoặc thiết kế accumulator dựa trên các toán tử nguyên tử/phù hợp.

Không có bảo đảm việc gắn `CONCURRENT` sẽ làm phép toán **nhanh hơn**. Chi phí contention, bộ nhớ, số lượng nhóm và overhead song song có thể làm pipeline chậm hơn tuần tự.

## 10. Những lỗi tinh vi khi khai báo characteristic

### Sai: gắn `IDENTITY_FINISH` cho finisher biến đổi kết quả

~~~java
// Sai về hợp đồng nếu thêm IDENTITY_FINISH:
// Collector<String, StringJoiner, String> c = Collector.of(
//         () -> new StringJoiner(","),
//         StringJoiner::add,
//         StringJoiner::merge,
//         StringJoiner::toString,
//         Collector.Characteristics.IDENTITY_FINISH
// );
~~~

Nếu framework bỏ qua finisher và sử dụng `StringJoiner` ở vị trí `String`, kết quả không phải kiểu người gọi mong đợi. Đừng gắn cờ này để "giảm một lời gọi finisher".

### Sai: gắn `CONCURRENT` cho accumulator dùng `ArrayList`

~~~java
// Sai về thread safety nếu còn dùng List::add:
// Collector<String, ?, List<String>> c = Collector.of(
//         ArrayList::new,
//         List::add,
//         (a, b) -> { a.addAll(b); return a; },
//         Collector.Characteristics.CONCURRENT,
//         Collector.Characteristics.UNORDERED
// );
~~~

Collector có thể bị sử dụng trên một container chung trong parallel stream, gây race. Không khai báo `CONCURRENT` nếu chỉ đúng khi mỗi thread có container riêng.

### Sai: gắn `UNORDERED` khi cần phần tử đầu tiên hoặc thứ tự xuất

Nếu collector đang tạo `List` theo thứ tự đầu vào hoặc `String` nối các phần tử theo thứ tự, gắn `UNORDERED` khiến framework được phép không bảo toàn một yêu cầu nghiệp vụ quan trọng.

### Sai: cho rằng có `CONCURRENT` thì lúc nào accumulator cũng chạy cùng lúc

Cờ này không bảo đảm thread count, parallelism, tốc độ hay lựa chọn một container chung trong từng lần chạy. Nó cho phép dùng concurrent reduction **khi điều kiện còn lại phù hợp**.

### Sai: nghĩ `IDENTITY_FINISH` nghĩa là kết quả immutable

Collector trả về chính `ArrayList` có thể sửa được mà vẫn là identity finish. `toUnmodifiableList()` ngược lại có bước hoàn tất riêng để tạo kết quả không cho sửa. *Identity* nói về bước chuyển kết quả, không nói về tính bất biến.

### Sai: đo hiệu năng bằng side effect trong accumulator

Tăng một biến global không đồng bộ để "đếm số lần gọi" vừa phá tính đúng của collector concurrent, vừa có thể làm benchmark sai lệch. Dùng bài đo có dữ liệu đại diện, quan sát kết quả chuẩn và dùng JMH/Java Flight Recorder khi cần đánh giá hiệu năng thực.

## 11. Quy trình kiểm chứng collector tự viết

Khi tạo custom collector, nên kiểm tra theo các bước:

1. **Xác định kiểu `T, A, R`:** phần tử vào, container tích lũy, kết quả phải trả là gì?
2. **Chứng minh identity:** `combiner(a, supplier.get())` phải tương đương với `a` đã tích lũy, theo nghĩa kết quả.
3. **Chứng minh associativity:** phân chia nguồn thành các đoạn, thu độc lập và ghép theo nhiều cách phải cho kết quả tương đương; chú ý thứ tự với collection/list hoặc nối chuỗi.
4. **Xét finisher:** kết quả có thật là chính container không? Nếu có thể bỏ finisher mà vẫn trả đúng kiểu và ý nghĩa, mới khai báo `IDENTITY_FINISH`.
5. **Xét encounter order:** có cần "lần đầu", "đúng thứ tự", hay nối chuỗi theo thứ tự không? Nếu có, đừng gắn `UNORDERED` tùy tiện.
6. **Xét cập nhật đồng thời trên cùng `A`:** accumulator có an toàn khi hai thread cùng gọi không? Nếu không, **không** gắn `CONCURRENT`.
7. **Thử cả `stream()` và `parallelStream()`:** đối chiếu giá trị, không so thứ tự của một kết quả unordered; thử đầu vào rỗng, một phần tử, nhiều phần tử trùng, dữ liệu lớn.
8. **Đo nếu thật sự cần:** benchmark có warm-up và dữ liệu hợp lý, vì overhead song song và contention có thể át lợi ích collector concurrent.

Một cách thực hành quan trọng: khi chưa chứng minh được một characteristic, **đừng khai báo nó**. Collector an toàn và đúng hợp đồng đáng giá hơn những cờ tối ưu không có cơ sở.

## 12. Bảng quyết định nhanh

| Tình huống | `IDENTITY_FINISH` | `UNORDERED` | `CONCURRENT` |
| --- | --- | --- | --- |
| Thu List với `ArrayList`, trả chính list, giữ thứ tự | Có | Không | Không |
| Tích lũy `StringJoiner`, trả `String` theo thứ tự | Không | Không | Không |
| Thu Set phân biệt, không quan tâm thứ tự, container không thread-safe | Có nếu trả chính Set | Có | Không |
| Thu Set bằng `ConcurrentHashMap.newKeySet()`, trả chính Set, không quan tâm thứ tự | Có | Có | Có |
| Đếm bằng `long[]` rồi finisher trả `Long` | Không | Có thể, nếu ngữ nghĩa không phụ thuộc thứ tự | Không |
| Thu List rồi finisher tạo `List.copyOf(...)` | Không | Không nếu cần thứ tự | Không nếu accumulator là ArrayList |
| Thu Map theo khóa có thể cập nhật đồng thời | Tùy finisher | Tùy ngữ nghĩa | Chỉ khi accumulator và trạng thái bên trong thực sự an toàn đồng thời |

**Tóm lại:** `IDENTITY_FINISH` cho phép xem container tích lũy chính là kết quả; `UNORDERED` cho phép bỏ ràng buộc encounter order; `CONCURRENT` cho phép accumulator nhận cập nhật đồng thời trên cùng container khi framework chọn chiến lược concurrent reduction. Ba cờ là **tuyên bố hợp đồng** phải được thực thi đúng bởi supplier, accumulator, combiner và finisher. Chọn ít cờ hơn nhưng đúng luôn tốt hơn khai báo quá mức rồi trông chờ framework tình cờ chạy an toàn.