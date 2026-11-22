# Combiner gộp các vùng tích lũy độc lập trong Collector tùy chỉnh (Java)

## 1. Bối cảnh: vì sao Collector cần combiner?

Trong Java Stream API, `collect` là thao tác kết thúc dùng để **tích lũy** các phần tử thành kết quả: danh sách, tập hợp, Map, chuỗi, thống kê hoặc cấu trúc nghiệp vụ do ứng dụng tự định nghĩa.

Với **Collector tùy chỉnh**, ta có thể chỉ định cách:

1. Tạo **container tích lũy** mới.
2. Đưa từng phần tử nguồn vào container ấy.
3. Gộp hai container đã được tích lũy **độc lập**.
4. Chuyển container cuối thành kết quả mong muốn.

Bước (3) chính là nhiệm vụ của **combiner**. Nó đặc biệt có ý nghĩa với parallel stream, vì luồng có thể chia thành các phân vùng dữ liệu, mỗi phân vùng tạo và tích lũy vào một container riêng, rồi các container được ghép lại.

Ví dụ một luồng tên:

~~~text
Dữ liệu: [An, Binh, Chi, Dung]

Phân vùng trái:  [An, Binh] -> container L = [An, Binh]
Phân vùng phải: [Chi, Dung] -> container R = [Chi, Dung]

combiner(L, R) -> [An, Binh, Chi, Dung]
~~~

Ở đây `combiner` **không** nhận trực tiếp một phần tử `String` từ nguồn. Nó nhận **hai kết quả tích lũy trung gian** cùng kiểu, gộp nội dung rồi trả một container đại diện cho kết quả kết hợp.

**Tư duy quan trọng:** `accumulator` làm việc với **(container, phần tử nguồn)**; `combiner` làm việc với **(container, container)**. Hai tham số của combiner không phải là hai phần tử gốc của Stream, trừ khi chính kiểu accumulator trùng kiểu phần tử nguồn trong một thiết kế đặc biệt.

## 2. Cấu trúc Collector và chữ ký Java

Interface `java.util.stream.Collector<T,A,R>` dùng ba kiểu:

| Ký hiệu | Vai trò | Ví dụ |
| --- | --- | --- |
| `T` | Kiểu phần tử nguồn từ Stream | `String` |
| `A` | Kiểu container tích lũy trung gian (*mutable accumulation type*) | `ArrayList<String>` |
| `R` | Kiểu kết quả cuối cùng | `List<String>` |

Những phương thức quan trọng của một Collector:

~~~java
Supplier<A> supplier();
BiConsumer<A, T> accumulator();
BinaryOperator<A> combiner();
Function<A, R> finisher();
Set<Collector.Characteristics> characteristics();
~~~

Đọc theo luồng:

~~~text
supplier() -> A rỗng

accumulator().accept(A, T)
    -> thay đổi A theo phần tử T

combiner().apply(A_left, A_right)
    -> trả A đã gộp hai vùng

finisher().apply(A)
    -> R
~~~

Phương thức factory để tạo Collector tùy chỉnh với finisher:

~~~java
Collector.of(
        Supplier<A> supplier,
        BiConsumer<A,T> accumulator,
        BinaryOperator<A> combiner,
        Function<A,R> finisher,
        Collector.Characteristics... characteristics)
~~~

Đây là chữ ký **mô tả các vai trò kiểu**, không phải cú pháp khai báo tham số có thể đặt nguyên văn vào mã Java. Cú pháp thực tế là một trong các overload static generic của `Collector.of`. Với `A` và `R` trùng nhau, có overload không cần finisher tường minh:

~~~java
Collector.of(supplier, accumulator, combiner, characteristics...)
~~~

Overload này tạo Collector có `IDENTITY_FINISH` vì kết quả `R` chính là container `A`.

**Chú ý tên API:** `Collector.of(...)` thuộc interface số ít `Collector`. Ngược lại `Collectors.toList()`, `Collectors.groupingBy()` là các factory có sẵn trong lớp tiện ích `Collectors` số nhiều.

## 3. Supplier: mỗi vùng tích lũy cần container riêng

`supplier()` có nhiệm vụ tạo container **mới, ban đầu rỗng về mặt tích lũy**. Ví dụ:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
List<String> left = supplier.get();
List<String> right = supplier.get();
~~~

Hai lời gọi phải cho hai container có thể tích lũy độc lập. Đặc biệt, không dùng một danh sách tĩnh chung:

~~~java
// SAI: Trả cùng một đối tượng shared cho mọi phân vùng.
List<String> shared = new ArrayList<>();
Supplier<List<String>> badSupplier = () -> shared;
~~~

Một Collector có supplier trả cùng đối tượng mutable gây ra hai rủi ro: các vùng tích lũy không còn độc lập và nhiều thread có thể sửa chung trạng thái mà không đồng bộ. Khi combiner cố gộp `left` và `right` nhưng thực chất hai biến trỏ cùng một list, thao tác `addAll` có thể nhân đôi dữ liệu hoặc dẫn tới kết quả sai.

Cách đúng:

~~~java
Supplier<List<String>> goodSupplier = ArrayList::new;
~~~

Mỗi lần gọi `get()` tạo một `ArrayList` mới. Trong parallel reduction **không dùng characteristic `CONCURRENT`**, Stream framework thường có thể tổ chức các container riêng và chỉ ghép chúng khi phù hợp. Đừng lấy số lượng container được tạo làm một hằng số: việc chia nguồn và số lần gọi supplier là chi tiết phụ thuộc cách thực thi.

## 4. Accumulator: container + phần tử nguồn

Accumulator là `BiConsumer<A,T>`, nên thường **sửa container** chứ không cần trả container.

~~~java
BiConsumer<List<String>, String> accumulator =
        (list, name) -> list.add(name);
~~~

Ý nghĩa:

~~~text
A_left = []
accumulator(A_left, "An")   -> A_left = ["An"]
accumulator(A_left, "Binh") -> A_left = ["An", "Binh"]
~~~

Khi tạo Collector bằng `Collector.of`:

~~~java
Collector<String, List<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

Đây là ví dụ sử dụng **overload không finisher**. `List::add` là method reference có thể dùng làm `BiConsumer` vì giá trị `boolean` trả về không được sử dụng trong ngữ cảnh hàm có kết quả `void`.

Điểm phân biệt:

- `accumulator` trả về `void` theo contract của `BiConsumer`; nó cập nhật `A`.
- `combiner` trả về **`A`** theo contract của `BinaryOperator<A>`; nó phải nói cho framework biết container nào biểu diễn kết quả sau gộp.

## 5. Combiner: gộp hai container và trả container kết quả

Với một collector tích lũy danh sách:

~~~java
BinaryOperator<List<String>> combiner =
        (left, right) -> {
            left.addAll(right);
            return left;
        };
~~~

Nó thực hiện hai việc:

1. Thêm toàn bộ phần tử của `right` vào `left`.
2. **Trả `left`** để framework sử dụng như accumulator đã kết hợp.

Trả về `left` ở đây là một lựa chọn thiết kế hợp lệ; không bắt buộc mọi combiner phải dùng chính container bên trái, miễn là kết quả đúng theo contract. Trong các mutable collectors, cách gộp vào `left` rồi trả `left` thường tránh phải tạo thêm container kết quả.

**Không quên câu `return left;`**. Lambda chỉ gọi `left.addAll(right)` không phù hợp kiểu `BinaryOperator<A>` vì `addAll` trả `boolean` (không phải `List<String>`); còn một lambda dạng block chỉ có mutation mà không có `return` sẽ không thỏa chữ ký trả `A`.

Một cách viết đầy đủ:

~~~java
Collector<String, List<String>, List<String>> c =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(c);

System.out.println(names); // [An, Binh, Chi]
~~~

### 5.1. Combiner không nhất thiết được gọi trên sequential stream

Nếu chỉ chạy:

~~~java
Stream.of("An", "Binh", "Chi").collect(c);
~~~

một triển khai tuần tự điển hình có thể sử dụng một container và liên tiếp gọi accumulator mà **không cần** combiner. Nhưng một Collector hợp lệ vẫn phải cung cấp combiner đúng vì API yêu cầu và vì việc chuyển sang `parallel()` có thể khiến nó cần được dùng.

Không nên viết code mà tính đúng đắn phụ thuộc vào việc combiner “sẽ luôn được gọi đúng một lần” hoặc “sẽ không bao giờ được gọi”. Đó không phải hợp đồng ổn định của Stream.

### 5.2. Combiner cũng có thể tạo container mới

Về mặt ngữ nghĩa, combiner được phép trả một accumulator kết hợp **mới**:

~~~java
BinaryOperator<List<String>> newListCombiner =
        (left, right) -> {
            List<String> merged = new ArrayList<>(left);
            merged.addAll(right);
            return merged;
        };
~~~

Điều này tránh sửa `left`, nhưng tạo bản sao container và thường có chi phí cao hơn. Với Collector tùy chỉnh và các yêu cầu quan sát về aliasing, phải thống nhất cách quản lý object trung gian. Không được để bên ngoài giữ tham chiếu và mong chúng vẫn nguyên trạng nếu combiner được thiết kế để mutate.

## 6. Ba luật quan trọng để combiner đúng

### 6.1. Identity — vùng rỗng không được làm đổi kết quả

Container `supplier.get()` đóng vai trò **phần tử đơn vị** của phép gộp về mặt kết quả. Nếu `e` là accumulator rỗng và `a` là accumulator đã tích lũy, yêu cầu về kết quả là:

\[
\operatorname{combine}(a,e)\equiv a,\qquad
\operatorname{combine}(e,a)\equiv a.
\]

Ký hiệu `≡` nghĩa là **tương đương về kết quả quan sát qua finisher**, không nhất thiết `==` cùng tham chiếu hoặc cùng object identity.

Ví dụ gộp danh sách:

~~~text
combine([An, Binh], []) => [An, Binh]
combine([], [An, Binh]) => [An, Binh]
~~~

Một combiner **không đúng** nếu luôn thêm một phần tử đánh dấu vào kết quả:

~~~java
// Sai: ghép vùng rỗng cũng làm dữ liệu thay đổi.
(left, right) -> {
    left.add("MERGED");
    left.addAll(right);
    return left;
}
~~~

Kết quả có thể chứa thêm `"MERGED"` tùy số lần chia/gộp. Không thể dùng “số lần gọi combiner” để quyết định số lần xuất hiện marker trong kết quả nghiệp vụ.

### 6.2. Associativity — cách chia/gộp không làm đổi kết quả

Với ba vùng `A`, `B`, `C`, phép gộp phải có tính **kết hợp** về mặt kết quả:

\[
\operatorname{combine}(\operatorname{combine}(A,B),C)
\equiv
\operatorname{combine}(A,\operatorname{combine}(B,C)).
\]

Ví dụ ghép danh sách theo đúng thứ tự vùng:

~~~text
A = [An]
B = [Binh]
C = [Chi]

(A + B) + C = [An, Binh, Chi]
A + (B + C) = [An, Binh, Chi]
~~~

Lưu ý: ở đây phép gộp **có thể không giao hoán**. `A + B` cho `[An, Binh]`, còn `B + A` cho `[Binh, An]`. Với ordered stream, giữ đúng thứ tự encounter order là một phần ngữ nghĩa của Collector có thứ tự. Combiner danh sách có thể có tính kết hợp mà không cần giao hoán.

Không dùng phép trừ với các vùng như một combiner chung: `(10-3)-2` khác `10-(3-2)`. Nếu dùng toán học dấu phẩy động, lưu ý phép cộng `double` không kết hợp tuyệt đối về mặt bit do làm tròn; chọn thuật toán và yêu cầu độ chính xác phù hợp.

### 6.3. Accumulator/combiner compatibility — kết quả gộp vùng tương đương tích lũy trực tiếp

Nếu một vùng có các phần tử `["An","Binh"]` và vùng kia có `["Chi"]`, gộp hai vùng phải cho cùng kết quả logic như tích lũy ba phần tử trong một vùng.

~~~text
Một vùng:
supplier -> []
accumulate An -> [An]
accumulate Binh -> [An, Binh]
accumulate Chi -> [An, Binh, Chi]

Hai vùng:
supplier -> []
accumulate An, Binh -> [An, Binh]
supplier -> []
accumulate Chi -> [Chi]
combine(left, right) -> [An, Binh, Chi]
~~~

Bất kể framework tổ chức bao nhiêu phân vùng (khi vẫn tôn trọng encounter order cần thiết), kết quả nghiệp vụ phải tương đương. Để đạt được điều đó, **supplier, accumulator và combiner phải là một bộ quy tắc thống nhất**.

## 7. Sơ đồ parallel collection

Giả sử:

~~~java
List<String> values = List.of("a", "b", "c", "d");
~~~

Một kế hoạch song song **có thể** diễn ra:

~~~text
                  Stream: [a, b, c, d]
                         /         \
                  [a, b]           [c, d]
                     |                |
                supplier()        supplier()
                     |                |
                  A = []             B = []
                     |                |
                accumulate        accumulate
                a -> [a]          c -> [c]
                b -> [a,b]        d -> [c,d]
                     \                /
                      \              /
                    combiner(A,B)
                          |
                    [a,b,c,d]
                          |
                       finisher
                          |
                     kết quả R
~~~

Đây là **mô hình khái niệm**, không phải lời hứa JVM luôn tạo hai vùng hoặc gọi từng callback với lịch cố định. Nguồn và collector có thể thay đổi cách chia/gộp và mức độ song song. Với pipeline tuần tự, có thể chỉ cần một accumulator và không có bước gộp thực tế.

### 7.1. “Độc lập” nghĩa là không dùng chung container mutable

Với collector không `CONCURRENT` điển hình, mỗi phân vùng được tích lũy vào container riêng từ supplier, không chia sẻ một `ArrayList` đồng thời. Combiner xuất hiện khi cần gộp các kết quả cục bộ.

Điều này cho phép sử dụng `ArrayList` — một lớp **không thread-safe** — bên trong một collector parallel hợp lệ, miễn mỗi container chỉ được framework sử dụng phù hợp với contract, supplier tạo instance riêng, combiner đúng và không khai báo `CONCURRENT` sai.

Không suy ra rằng một `ArrayList` bất kỳ từ ngoài được chia sẻ vào các thread là an toàn chỉ vì collector có thể được dùng trong parallel stream.

## 8. Finisher: chuyển A thành R sau khi gộp

Nếu `A` và `R` khác kiểu, dùng `Collector.of(..., finisher)`. Ví dụ, tích lũy vào `ArrayList<String>` nhưng trả một `List<String>` **không thể sửa đổi**:

~~~java
Collector<String, ArrayList<String>, List<String>> copyCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);

List<String> copy = Stream.of("An", "Binh", "Chi")
        .parallel()
        .collect(copyCollector);
~~~

Ở đây:

- `T = String`.
- `A = ArrayList<String>`.
- `R = List<String>`.
- Combiner **gộp các `ArrayList<String>`**, không gộp `List<String>` kết quả cuối.
- Finisher `List::copyOf` chỉ chạy để tạo kết quả cuối sau khi các tích lũy được tổng hợp, không phải một lần cho mỗi phần tử nguồn.

`List.copyOf` không chấp nhận phần tử null. Với dữ liệu chứa null, finisher có thể ném `NullPointerException`; điều đó là chính sách của phép tạo List cuối, không phải lỗi của chữ ký combiner.

Khi có finisher thực sự chuyển `A` sang `R`, **không** được khai báo characteristic `IDENTITY_FINISH`. Đây là một ví dụ `A` và `R` khác nhau, nên finisher không phải phép identity.

### 8.1. Ví dụ StringJoiner cho phép gộp có ngữ nghĩa

`StringJoiner` được thiết kế có thể gộp hai vùng:

~~~java
Collector<String, StringJoiner, String> joinerCollector =
        Collector.of(
                () -> new StringJoiner(","),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);

String csv = Stream.of("An", "Binh", "Chi")
        .parallel()
        .collect(joinerCollector);

System.out.println(csv); // An,Binh,Chi
~~~

`StringJoiner::merge` là combiner có sẵn và trả `StringJoiner`. Nó xử lý việc phân cách khi gộp các vùng; tránh sai lầm thường gặp của một combiner StringBuilder tự thêm dấu phẩy cho cả vùng rỗng hoặc thêm dấu ở cuối.

Với dữ liệu tùy ý có ký tự dấu phẩy, ví dụ chỉ minh họa phép nối bằng delimiter, **không tự xem là một bộ ghi CSV có đầy đủ quy tắc escape/quote**.

## 9. Ví dụ Collector tùy chỉnh có hai số liệu và một kết quả bất biến

Một Collector có thể tích lũy nhiều số liệu cùng lúc. Ví dụ, mỗi từ đi vào một container chứa số từ và tổng số ký tự.

~~~java
record WordStats(long count, long characters) {}

final class StatsBox {
    long count;
    long characters;

    void accept(String word) {
        count++;
        characters += word.length();
    }

    StatsBox combine(StatsBox other) {
        count += other.count;
        characters += other.characters;
        return this;
    }

    WordStats finish() {
        return new WordStats(count, characters);
    }
}
~~~

Collector:

~~~java
Collector<String, StatsBox, WordStats> statsCollector =
        Collector.of(
                StatsBox::new,
                StatsBox::accept,
                StatsBox::combine,
                StatsBox::finish);
~~~

Đọc kỹ combiner:

- Nó nhận **`StatsBox other`**, không phải một `String word`.
- Nó cộng hai bộ số liệu đã tổng hợp, **không gọi lại accumulator cho từng từ**.
- Nó sửa `this` rồi trả `this` làm kết quả gộp.
- Với identity `new StatsBox()`, hai trường số nguyên bắt đầu bằng 0, nên gộp vùng rỗng không làm đổi số liệu.

Tổng số từ và tổng ký tự là phép cộng các giá trị `long`, kết hợp theo arithmetic số nguyên Java (có thể overflow với số liệu cực lớn), và không phụ thuộc thứ tự dữ liệu.

Có thể dùng `parallelStream` mà không cần `synchronized` trong `StatsBox` khi dùng collector **không CONCURRENT**, vì mỗi vùng tích lũy độc lập. Không tự đặt characteristic `CONCURRENT` cho class mutable không thread-safe này.

## 10. Chương trình Java 17+ hoàn chỉnh và stdout xác định

Lưu thành **`CombinerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CombinerDemo {
    record WordStats(long count, long characters) {}

    static final class StatsBox {
        long count;
        long characters;

        void add(String word) {
            count++;
            characters += word.length();
        }

        StatsBox merge(StatsBox other) {
            count += other.count;
            characters += other.characters;
            return this;
        }

        WordStats finish() {
            return new WordStats(count, characters);
        }
    }

    public static void main(String[] args) {
        Collector<String, ArrayList<String>, List<String>> listCollector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf);

        List<String> names = Stream.of("An", "Binh", "Chi", "Dung")
                .parallel()
                .collect(listCollector);
        System.out.println("names=" + names);

        try {
            names.add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("namesUnmodifiable=true");
        }

        Collector<String, StringJoiner, String> joinerCollector =
                Collector.of(
                        () -> new StringJoiner(","),
                        StringJoiner::add,
                        StringJoiner::merge,
                        StringJoiner::toString);

        String joined = Stream.of("An", "Binh", "Chi")
                .parallel()
                .collect(joinerCollector);
        System.out.println("joined=" + joined);

        Collector<String, StatsBox, WordStats> statsCollector =
                Collector.of(
                        StatsBox::new,
                        StatsBox::add,
                        StatsBox::merge,
                        StatsBox::finish);

        WordStats stats = Stream.of("Java", "API", "Stream")
                .parallel()
                .collect(statsCollector);
        System.out.println("stats=" + stats);

        WordStats empty = Stream.<String>empty()
                .collect(statsCollector);
        System.out.println("empty=" + empty);

        StatsBox left = new StatsBox();
        left.add("Java");
        StatsBox right = new StatsBox();
        right.add("API");
        left.merge(right);
        System.out.println("manualMerge=" + left.finish());

        Collector<String, ArrayList<String>, ArrayList<String>> sameType =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (a, b) -> {
                            a.addAll(b);
                            return a;
                        });

        List<String> sequential = Stream.of("a", "b", "c")
                .collect(sameType);
        System.out.println("sequential=" + sequential);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac CombinerDemo.java
java CombinerDemo
~~~

Stdout dự kiến:

~~~text
names=[An, Binh, Chi, Dung]
namesUnmodifiable=true
joined=An,Binh,Chi
stats=WordStats[count=3, characters=13]
empty=WordStats[count=0, characters=0]
manualMerge=WordStats[count=2, characters=7]
sequential=[a, b, c]
~~~

Giải thích:

1. `names` có đúng encounter order vì nguồn có thứ tự và collector không khai báo `UNORDERED`. Cách chia/gộp nội bộ không được in ra hay giả định.
2. `namesUnmodifiable=true` chứng minh finisher tạo `List` không thể sửa qua kết quả.
3. `joined` dùng `StringJoiner::merge`, gộp vùng tích lũy mà không đặt delimiter thừa.
4. `stats` đếm ba chuỗi `Java`, `API`, `Stream`; tổng chiều dài là `4+3+6=13`.
5. `empty` cho thấy supplier tạo vùng rỗng hợp lệ và finisher trả thống kê 0/0.
6. `manualMerge` gộp hai vùng độc lập chứa `Java` và `API`; kết quả có 2 từ, 7 ký tự.
7. `sameType` minh họa overload `Collector.of` không finisher tường minh khi kiểu accumulator và kiểu kết quả trùng nhau.

Ví dụ không cố đoán số lần combiner chạy trong pipeline song song. Kết quả chỉ dựa vào **hợp đồng Collector**, nên stdout có thể kiểm chứng mà không phụ thuộc lịch thực thi của ForkJoinPool.

## 11. Những lỗi combiner thường gặp

### 11.1. Không gộp dữ liệu của container bên phải

~~~java
// SAI: Bỏ mất toàn bộ phân vùng right.
(left, right) -> left
~~~

Nếu chạy sequential, lỗi có thể ẩn vì combiner có thể không được gọi. Khi chạy parallel, một số phần tử có thể biến mất khỏi kết quả.

Cách đúng với List:

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

### 11.2. Gộp sai kiểu hoặc trả sai giá trị

~~~java
// SAI đối với BinaryOperator<List<String>>:
// (left, right) -> left.addAll(right)
// addAll trả boolean, không phải List<String>.
~~~

Combiner phải trả một container kiểu `A`. Cũng không trả `null` làm kết quả gộp: framework cần tiếp tục dùng accumulator đã được kết hợp.

### 11.3. Supplier trả một đối tượng dùng chung

~~~java
List<String> shared = new ArrayList<>();

// SAI:
Collector<String, List<String>, List<String>> unsafe =
        Collector.of(
                () -> shared,
                List::add,
                (a, b) -> {
                    a.addAll(b);
                    return a;
                });
~~~

Supplier không tạo các vùng tích lũy độc lập. Đây là lỗi căn bản, không thể “chữa” chỉ bằng cách thêm `synchronized` tùy tiện cho combiner.

### 11.4. Combiner làm đổi dữ liệu theo số lần gộp

~~~java
// SAI: thêm separator ngay cả khi right là vùng rỗng.
(left, right) -> {
    left.append(",");
    left.append(right);
    return left;
}
~~~

Nếu dùng `StringBuilder` để ghép, combiner phải xử lý đúng vùng rỗng và giữ ngữ nghĩa dấu phân cách; collector có sẵn `Collectors.joining(",")` hoặc `StringJoiner` thường ít sai hơn.

### 11.5. Sửa hai container theo cách gây nhân đôi

~~~java
// SAI: dùng cả hai chiều gộp và có thể nhân đôi/đổi dữ liệu.
(left, right) -> {
    left.addAll(right);
    right.addAll(left);
    return left;
}
~~~

Chỉ cần một accumulator kết quả đại diện cho toàn bộ dữ liệu. Không sửa `right` sau khi đã thêm nội dung của nó vào `left` nếu mutation ấy không được yêu cầu.

### 11.6. Khai báo `CONCURRENT` cho container không thread-safe

~~~java
// SAI khi A là ArrayList và accumulator dùng list.add:
// Collector.Characteristics.CONCURRENT
~~~

`CONCURRENT` cho phép accumulator được gọi đồng thời trên **cùng một container kết quả** trong những điều kiện mà Stream có thể sử dụng điều đó. Không nên khai báo nếu accumulator/container không thread-safe. Một collector dùng parallel stream **không bắt buộc** phải có `CONCURRENT`.

### 11.7. Khai báo `UNORDERED` dù thứ tự là yêu cầu

Nếu kết quả là danh sách và nghiệp vụ yêu cầu giữ thứ tự gặp phần tử, đừng thêm `Collector.Characteristics.UNORDERED`. Characteristic này tuyên bố kết quả không nhạy với encounter order; framework có thể tận dụng tuyên bố ấy để thực thi khác đi. Nó không chỉ là một nút “tăng tốc độ”.

### 11.8. Khai báo `IDENTITY_FINISH` với finisher không phải identity

Nếu dùng `List::copyOf` hoặc `StatsBox::finish` để chuyển `A` sang `R`, không được khai báo `IDENTITY_FINISH`. Characteristic này cho framework biết có thể bỏ qua bước finisher do phép chuyển là identity về kiểu và giá trị; khai báo sai có thể làm sai kết quả hoặc gây lỗi kiểu khi sử dụng.

## 12. Kiểm tra một combiner độc lập bằng các trường hợp có ích

Không chỉ chạy parallel rồi nhìn kết quả một lần. Nên xác định các tính chất mong muốn của Collector bằng những phép thử đơn giản:

### 12.1. Hai vùng có dữ liệu

~~~java
List<String> left = new ArrayList<>(List.of("A", "B"));
List<String> right = new ArrayList<>(List.of("C"));

left.addAll(right);
System.out.println(left); // [A, B, C]
~~~

### 12.2. Một vùng rỗng

~~~java
List<String> empty = new ArrayList<>();
List<String> nonEmpty = new ArrayList<>(List.of("A"));

empty.addAll(nonEmpty);
System.out.println(empty); // [A]
~~~

Với combiner thực tế, kiểm tra cả khi vùng bên trái rỗng và bên phải rỗng. Nếu container được mutate, nên tạo bản sao mới cho từng ca kiểm thử để không làm dữ liệu của ca trước ảnh hưởng ca sau.

### 12.3. Ba vùng và nhiều cách đặt ngoặc

~~~text
A = [A], B = [B], C = [C]

combine(combine(A,B),C) -> [A, B, C]
combine(A,combine(B,C)) -> [A, B, C]
~~~

Để kiểm thử trong Java, tạo các container **độc lập** cho hai cách đặt ngoặc; không tái sử dụng các container đã bị mutation. So sánh **kết quả quan sát được**, không so `==` tham chiếu.

### 12.4. Đối chiếu sequential và parallel

Nếu collector hợp lệ, cùng một nguồn và điều kiện nghiệp vụ hợp lệ phải cho kết quả tương đương:

~~~java
List<String> source = List.of("A", "B", "C", "D");

List<String> seq = source.stream().collect(listCollector);
List<String> par = source.parallelStream().collect(listCollector);

System.out.println(seq.equals(par)); // true
~~~

Trong đoạn minh họa này, `listCollector` là collector của phần 10 được khai báo trước đó. Dạng kiểm thử nên dùng nguồn có thứ tự và collector không `UNORDERED` để so sánh hai danh sách theo đúng thứ tự. Đối với các collector có kết quả không nhạy thứ tự như Set, phải chọn tiêu chí so sánh phù hợp.

Không dùng kiểm thử “combiner gọi đúng N lần” vì số vùng, lịch gộp và việc có gọi combiner hay không là đặc điểm thực thi, không phải hợp đồng cần khẳng định.

## 13. So với `reduce` và collector có sẵn

`Stream.reduce` và `Stream.collect` đều là phép tổng hợp, nhưng có cách dùng khác:

| Khía cạnh | `reduce(identity, accumulator, combiner)` | `collect(Collector)` |
| --- | --- | --- |
| Tích lũy | Từ giá trị tổng hợp và phần tử, trả giá trị tổng hợp mới | `BiConsumer<A,T>` có thể sửa container A |
| Combiner | Gộp hai **giá trị kết quả trung gian** | Gộp hai **container tích lũy A** |
| Mutable state | Không nên mutate identity chia sẻ | Mô hình collector hỗ trợ mutable accumulation có kiểm soát |
| Finisher | Không có bước finisher riêng trong overload | Có thể chuyển A thành R |
| Đặc tính | Phụ thuộc luật reduce | Có `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` khi đúng |

Ví dụ số học:

~~~java
int sum = Stream.of(1, 2, 3)
        .reduce(0, Integer::sum);
~~~

Với tác vụ thu thập danh sách, không nên gò mutable `ArrayList` vào `reduce` bằng cách sửa một identity chung. `collect(Collectors.toList())` hoặc một Collector tùy chỉnh với supplier riêng và combiner đúng là hướng phù hợp.

**Ưu tiên collector có sẵn nếu đủ nhu cầu:** `toList`, `toSet`, `toMap`, `groupingBy`, `partitioningBy`, `joining`, `summarizingInt`, `mapping`, `filtering`, `collectingAndThen` đã có các contract cần thiết. Viết custom collector khi có nhu cầu cụ thể mà collector có sẵn không diễn đạt rõ hoặc không tạo kết quả mong muốn.

## 14. Phân biệt `CONCURRENT` và “chạy song song”

Một Stream `parallel()` có thể chạy collector không CONCURRENT bằng cách sử dụng **nhiều container độc lập** và gộp chúng qua combiner. Trong khi đó, một Collector khai báo `CONCURRENT` nói rằng accumulator của nó có thể nhận nhiều lời gọi đồng thời trên một accumulator result trong điều kiện cho phép.

Điều đó dẫn tới hai mô hình tư duy:

~~~text
Không CONCURRENT, parallel:
  supplier -> A1 --- accumulate -> A1
  supplier -> A2 --- accumulate -> A2
                                combine(A1,A2)

CONCURRENT trong hoàn cảnh phù hợp:
  một accumulator chia sẻ A có thể nhận
  nhiều lời gọi accumulator đồng thời
~~~

Không thể kết luận `parallel()` luôn có đúng hai accumulator hoặc collector `CONCURRENT` luôn có một accumulator chung. Đặc biệt, đối với nguồn ordered và collector không `UNORDERED`, runtime có thể chọn cách tổ chức khác để giữ đúng ngữ nghĩa thứ tự.

**Nguyên tắc an toàn:** Không khai báo characteristic khi chưa bảo đảm hành vi thực tế đáp ứng đúng contract. Tối ưu hóa parallel chỉ nên làm sau khi logic collection được kiểm chứng với dữ liệu đa dạng.

## 15. Một số tình huống nâng cao cần phân biệt

### 15.1. Combiner của Map cần giải quyết khóa trùng

Nếu `A` là `Map<K,V>`, combiner phải đưa toàn bộ các cặp từ Map vùng phải vào Map kết quả, đồng thời xử lý đúng **khóa xuất hiện ở cả hai vùng**.

~~~java
(left, right) -> {
    right.forEach((key, value) ->
            left.merge(key, value, Integer::sum));
    return left;
}
~~~

Đoạn trên chỉ đúng khi `left`/`right` là `Map<K,Integer>` với key/value đáp ứng hợp đồng `Map.merge` và chiến lược cộng phù hợp nghiệp vụ. Nếu muốn giữ bản ghi đầu hoặc cuối, phải định nghĩa merger rõ ràng; **không ghi đè ngầm** bằng `putAll` trừ khi đó chính là quy tắc.

Với nhu cầu thông thường, `Collectors.toMap(keyMapper, valueMapper, mergeFunction)` đã xử lý bài toán Map, thường tốt hơn tự viết combiner từ đầu.

### 15.2. Combiner của Set khác combiner của List ở thứ tự

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

Đoạn trên có thể áp dụng cho `Set<T>` nếu đúng kiểu, nhưng Set loại trùng và không nhất thiết có thứ tự. Cùng hình thức gộp `addAll`, **ngữ nghĩa kết quả** của Set và List rất khác: List giữ số lần xuất hiện, Set giữ các phần tử duy nhất theo equality.

### 15.3. Combiner của kết quả thống kê

Với `StatsBox` ở phần 9, combiner cộng các trường số liệu. Nếu bổ sung `min`, `max` hoặc các chỉ số thống kê phức tạp, phải xác định **giá trị rỗng** cho từng trường và bảo đảm việc gộp hai vùng là đúng. Với trung bình cộng, thông thường cần gộp **sum và count**, sau đó mới tính `sum/count` trong finisher; không nên lấy trung bình của hai vùng rồi chia 2 nếu hai vùng có số phần tử khác nhau.

### 15.4. Không dựa vào log của combiner để kiểm thử hiệu năng

Ghi log trong combiner có thể có ích khi học và debug, nhưng số lần nó được gọi thay đổi theo kích thước dữ liệu, parallelism và cách chia nguồn. Log cũng có thể làm sai lệch đo hiệu năng. Khi benchmark, đo đầu ra và thời gian bằng công cụ phù hợp, đồng thời tránh side effect trong những hàm cần được tối ưu.

## 16. Bài tập tự kiểm tra

**Bài 1.** Trong Collector `Collector<String,List<String>,List<String>>`, combiner nhận loại dữ liệu gì?

Đáp án: hai `List<String>` là các **container tích lũy trung gian**. Nó không nhận một `String` từ nguồn trực tiếp.

**Bài 2.** Combiner sau có lỗi gì?

~~~java
(left, right) -> left
~~~

Đáp án: nó bỏ toàn bộ dữ liệu của vùng `right`. Lỗi có thể không lộ khi pipeline tuần tự không cần gộp, nhưng làm mất dữ liệu khi gộp nhiều vùng.

**Bài 3.** Supplier `() -> sharedList` có phù hợp cho mutable collector được chạy song song không?

Đáp án: không. Các vùng không độc lập, có thể sửa cùng một object và tạo race/nhân đôi dữ liệu. Cần supplier tạo container mới, như `ArrayList::new`.

**Bài 4.** Vì sao `combiner` của một collector danh sách phải giữ thứ tự trái/phải dù phép gộp không giao hoán?

Đáp án: Với ordered stream và collector không khai báo `UNORDERED`, kết quả có thể cần bảo toàn encounter order. Gộp đúng `left` rồi `right` có tính kết hợp nhưng không phải phép giao hoán.

**Bài 5.** Tại sao không khai báo `IDENTITY_FINISH` cho collector dùng `List::copyOf`?

Đáp án: `List::copyOf` tạo kết quả từ container tích lũy, không phải phép identity trên cùng object; khai báo characteristic này có thể khiến framework bỏ qua finisher, làm sai kiểu hoặc tính không thể sửa đổi.

**Bài 6.** Trong ví dụ `StatsBox`, một nhánh đếm 2 từ, tổng 7 ký tự; nhánh khác đếm 1 từ, tổng 6 ký tự. Combiner phải tạo kết quả gì?

Đáp án: tổng cộng 3 từ và 13 ký tự, bất kể nhánh nào được gộp trước trong một phép cộng số liệu kết hợp.

**Bài 7.** Nếu mục tiêu chỉ là ghép chuỗi bằng dấu phẩy, có nên tự xây combiner phức tạp cho StringBuilder không?

Đáp án: thường không. `Collectors.joining(",")` hoặc `StringJoiner` có sẵn và diễn đạt đúng quy tắc separator.

**Bài 8.** Combiner có bắt buộc chạy trên sequential stream không?

Đáp án: không. Không được viết chương trình mà kết quả phụ thuộc vào số lần gọi combiner. Quan trọng là phép gộp phải đúng **nếu được gọi**.

**Bài 9.** Sự khác biệt giữa `Accumulator` và `Combiner` là gì?

Đáp án: accumulator có dạng `(A,T) -> void`, dùng để đưa từng phần tử nguồn vào container; combiner có dạng `(A,A) -> A`, dùng để ghép kết quả của hai container đã tích lũy độc lập.

## 17. Ghi nhớ

**Combiner là hàm gộp hai vùng tích lũy độc lập trong Collector tùy chỉnh.** Nó nhận hai accumulator cùng kiểu `A` và **phải trả một accumulator `A` chứa kết quả hợp nhất**, không được bỏ dữ liệu từ bên nào.

Một collector đáng tin cậy có bốn vai trò rõ ràng:

- `supplier` tạo **container mới, rỗng** cho mỗi lần framework cần vùng tích lũy.
- `accumulator` nhận `(A,T)`, đưa từng phần tử nguồn `T` vào container `A`.
- `combiner` nhận `(A,A)`, gộp hai container với quy tắc có **identity**, **associativity** và tương thích accumulator.
- `finisher` chuyển `A` thành kết quả `R` nếu cần.

Không dùng một mutable container chia sẻ cho nhiều vùng, không khai báo `CONCURRENT`/`UNORDERED`/`IDENTITY_FINISH` sai hợp đồng, và không phụ thuộc số lần combiner được gọi. Khi thiết kế đúng, custom Collector có thể làm việc với **sequential và parallel streams** mà vẫn cho kết quả tương đương, rõ ràng và kiểm chứng được.
