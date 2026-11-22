# Comparator.comparingInt() và xử lý giá trị null trong Java

Khi sắp xếp đối tượng bằng Java, `Comparator.comparingInt()` là lựa chọn gọn và rõ nghĩa nếu khóa sắp xếp là một giá trị `int`. Nhưng một phần tử trong danh sách có thể là `null`, hoặc trường dùng làm khóa có kiểu `Integer` và đang chứa `null`. Hai tình huống này **khác nhau**, vì `comparingInt()` dùng hàm trích xuất trả về `int` nguyên thủy, không mang được trạng thái “thiếu giá trị”.

Bài này giải thích chữ ký và cơ chế hoạt động, cách đặt `Comparator.nullsFirst()` / `nullsLast()` đúng vị trí, cách sắp xếp khóa `Integer` có thể null, và các bẫy khi kết hợp `thenComparing()` hoặc `reversed()`. Ví dụ dùng cú pháp Java 17+.

## 1. `comparingInt()` nhận hành vi gì?

Chữ ký khái quát của API là:

~~~java
public static <T> Comparator<T> comparingInt(
        java.util.function.ToIntFunction<? super T> keyExtractor);
~~~

Đây là **chữ ký minh họa**, không phải tệp Java biên dịch độc lập. `ToIntFunction<T>` là functional interface có phương thức:

~~~java
int applyAsInt(T value);
~~~

Vì thế `Comparator.comparingInt(Person::age)` tạo ra bộ so sánh nhận hai `Person`, gọi hàm lấy tuổi của mỗi đối tượng và so sánh hai giá trị `int` bằng ngữ nghĩa của `Integer.compare` (không trừ hai số để lấy chênh lệch). Giá trị số nhỏ hơn sẽ đứng trước theo thứ tự tăng dần.

- `comparingInt()` **tạo ra comparator**; nó chưa tự sắp xếp tập dữ liệu.
- `Person::age` hoặc `p -> p.age()` là hành vi trích xuất khóa, được comparator gọi khi cần so sánh.
- Khóa là `int`, nên không cần tạo `Integer` chỉ để biểu diễn kết quả hàm trích xuất.
- Hàm trích xuất có thể được gọi **nhiều lần** trong một lần sắp xếp. Nên giữ nó thuần, nhanh và không có side effect.
- Nếu extractor phải dereference một phần tử `null`, hoặc phải unbox một `Integer null`, `NullPointerException` có thể phát sinh.

### Ví dụ cơ bản: trường nguyên thủy không null

Tạo file `PrimitiveComparatorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class PrimitiveComparatorDemo {
    record Candidate(String name, int score) {}

    public static void main(String[] args) {
        List<Candidate> candidates = new ArrayList<>(List.of(
                new Candidate("An", 9),
                new Candidate("Chi", 5),
                new Candidate("Bình", 5)
        ));

        candidates.sort(
                Comparator.comparingInt(Candidate::score)
                        .thenComparing(Candidate::name)
        );

        System.out.println(candidates.stream()
                .map(Candidate::name)
                .toList());
    }
}
~~~

~~~bash
javac --release 17 PrimitiveComparatorDemo.java
java PrimitiveComparatorDemo
~~~

Kết quả:

~~~text
[Bình, Chi, An]
~~~

Khóa chính là `score` tăng dần; khi hai điểm đều bằng 5, `thenComparing(Candidate::name)` so sánh tên theo thứ tự tự nhiên của `String`. Trong ví dụ này mọi đối tượng và tên đều không null.

## 2. Phải xác định chính xác đối tượng nào có thể null

Có hai mức null thường gặp:

| Tình huống | Ví dụ | Hậu quả nếu dùng `comparingInt()` trực tiếp | Cách xử lý |
| --- | --- | --- | --- |
| **Phần tử đang so sánh là null** | Danh sách chứa `null` thay cho một `Candidate` | `Candidate::score` không có receiver để gọi | Bọc *toàn bộ comparator của đối tượng* bằng `Comparator.nullsFirst(...)` hoặc `Comparator.nullsLast(...)`. |
| **Phần tử có thật nhưng khóa null** | `candidate.score()` trả về `Integer null` | Java phải unbox `Integer` thành `int` và có thể ném `NullPointerException` | Dùng `Comparator.comparing(..., Comparator.nullsFirst/Last(...))`, hoặc đưa ra quy tắc giá trị mặc định tường minh. |

**Bọc comparator ngoài cùng chỉ xử lý null ở cấp đối tượng được so sánh.** Nó không bảo vệ một khóa null bên trong đối tượng còn tồn tại. Ngược lại, bọc comparator của khóa chưa xử lý đối tượng null nếu code vẫn gọi getter trên đối tượng null.

Đừng dựa vào việc dữ liệu “hiện chưa có null”: từ database, JSON, map, nguồn nhập người dùng, dữ liệu legacy hoặc khi biến đổi qua nhiều pipeline, chính sách null phải được thống nhất ở ranh giới API.

## 3. Trường hợp A: phần tử null, khóa kiểu `int` luôn hợp lệ

Nếu danh sách có thể chứa một đối tượng `null`, nhưng mỗi đối tượng không null có khóa kiểu `int`, hãy đặt `nullsFirst` hoặc `nullsLast` **bao quanh comparator của đối tượng**.

~~~java
Comparator<Candidate> byScoreWithNullLast =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score));
~~~

Đoạn trên nằm trong ngữ cảnh đã có `Candidate` và `import java.util.Comparator`.

Cách hoạt động khi comparator nhận hai đầu vào:

1. Cả hai đều null: trả về 0, tức được xem là bằng nhau theo khóa sắp xếp này.
2. Chỉ một bên null: đưa bên đó lên đầu với `nullsFirst` hoặc xuống cuối với `nullsLast`.
3. Cả hai không null: ủy quyền cho comparator bên trong, lúc này extractor được gọi an toàn đối với null ở cấp đối tượng.

Ví dụ độc lập, file `NullElementSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullElementSortDemo {
    record Candidate(String name, int score) {}

    public static void main(String[] args) {
        List<Candidate> items = new ArrayList<>(Arrays.asList(
                new Candidate("An", 9),
                null,
                new Candidate("Chi", 4)
        ));

        Comparator<Candidate> order = Comparator.nullsFirst(
                Comparator.comparingInt(Candidate::score)
        );
        items.sort(order);

        for (Candidate candidate : items) {
            System.out.println(candidate == null
                    ? "<null>"
                    : candidate.name() + "=" + candidate.score());
        }
    }
}
~~~

~~~bash
javac --release 17 NullElementSortDemo.java
java NullElementSortDemo
~~~

Kết quả:

~~~text
<null>
Chi=4
An=9
~~~

`Comparator.nullsFirst` nhận một comparator có thể dùng cho các phần tử không null. Bản thân phép bọc không sửa dữ liệu và không thay thế `null` bằng một đối tượng giả.

Lưu ý: `List.of(...)` **không cho phép** phần tử null, và danh sách trả về cũng không hỗ trợ sắp xếp tại chỗ. Vì vậy ví dụ dùng `new ArrayList<>(Arrays.asList(...))` để tạo một danh sách có thể chứa null và cho phép gọi `sort`.

## 4. Trường hợp B: khóa là `Integer` và có thể null

Nếu một trường `score` khai báo `Integer` (kiểu wrapper) thay vì `int`, lời gọi sau có thể **biên dịch được** nhưng thất bại khi so sánh đối tượng có điểm null:

~~~java
// Đoạn cố ý thể hiện lỗi, không phải chương trình độc lập:
record Candidate(String name, Integer score) {}
Comparator<Candidate> unsafe =
        Comparator.comparingInt(candidate -> candidate.score());
// candidate.score() là Integer; phải auto-unbox thành int.
// Nếu score() trả null, thao tác unbox sẽ ném NullPointerException.
~~~

Ngay cả khi bọc thêm `Comparator.nullsLast(unsafe)`, null của *Candidate* được xử lý nhưng `Candidate.score() == null` vẫn có thể ném lỗi.

Để giữ null như một khóa có ý nghĩa riêng, dùng `Comparator.comparing()` với comparator cho **kiểu khóa tham chiếu**:

~~~java
Comparator<Candidate> byNullableScore =
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.naturalOrder()));
~~~

Khác nhau ở chỗ:

- `comparingInt()` nhận `ToIntFunction<T>`, buộc khóa thành `int`.
- `comparing()` nhận hàm trả về một kiểu khóa tham chiếu, như `Integer`, và có thể nhận comparator riêng của khóa.
- `Comparator.nullsLast(Comparator.naturalOrder())` ở đây sắp **các giá trị `Integer`**, đưa `Integer null` xuống sau mọi số không null.
- Nếu bản thân `Candidate` cũng có thể null, vẫn cần **thêm một lớp nullsLast/nullsFirst bên ngoài**.

### Ví dụ hoàn chỉnh: cả đối tượng và khóa đều có thể null

Tạo file `NullableScoreSortDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullableScoreSortDemo {
    record Candidate(String name, Integer score) {}

    public static void main(String[] args) {
        List<Candidate> candidates = new ArrayList<>(Arrays.asList(
                new Candidate("An", 8),
                new Candidate("Bình", null),
                null,
                new Candidate("Chi", 3),
                new Candidate("Dũng", 8)
        ));

        Comparator<Candidate> order = Comparator.nullsLast(
                Comparator.comparing(
                        Candidate::score,
                        Comparator.nullsLast(Comparator.naturalOrder()))
                    .thenComparing(Candidate::name)
        );
        candidates.sort(order);

        for (Candidate candidate : candidates) {
            System.out.println(candidate == null
                    ? "<null>"
                    : candidate.name() + "=" + candidate.score());
        }
    }
}
~~~

~~~bash
javac --release 17 NullableScoreSortDemo.java
java NullableScoreSortDemo
~~~

Kết quả:

~~~text
Chi=3
An=8
Dũng=8
Bình=null
<null>
~~~

Bộ so sánh có **hai lớp chính sách null**. Lớp bên trong bảo vệ khóa `Integer score`; lớp ngoài cùng bảo vệ chính đối tượng `Candidate`. Trong phần tử không null, điểm được so tăng dần, hai người cùng điểm 8 được phân xử bởi tên.

Nếu tên cũng có thể null thì `.thenComparing(Candidate::name)` không an toàn khi hai điểm bằng nhau. Chọn chính sách cho cả tên:

~~~java
// Đoạn minh họa đặt trong ngữ cảnh đã có Candidate:
Comparator<Candidate> safeAllFields = Comparator.nullsLast(
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.naturalOrder()))
            .thenComparing(
                Candidate::name,
                Comparator.nullsLast(Comparator.naturalOrder()))
);
~~~

Điều này cho thấy cần kiểm tra **từng khóa** và **đối tượng gốc** trong hợp đồng sắp xếp, không chỉ thêm một `nullsLast` ở bất kỳ vị trí nào.

## 5. Nếu buộc phải dùng `comparingInt()` với khóa nullable

Có thể tự định nghĩa quy tắc thay thế một giá trị `Integer null` bằng số `int` nào đó, rồi cho extractor luôn trả về primitive:

~~~java
// Minh họa: chỉ dùng khi score() có thể null nhưng Candidate không null.
Comparator<Candidate> byScoreWithFallback =
        Comparator.comparingInt(candidate ->
                candidate.score() == null ? -1 : candidate.score());
~~~

Nếu điểm hợp lệ là các số không âm, `-1` có thể diễn đạt “chưa có điểm, xếp trước”. Nhưng **đây là quyết định nghiệp vụ**, không phải hành vi tự động của `comparingInt`. Nếu `-1` cũng là điểm hợp lệ, các phần tử có điểm thật `-1` và các phần tử có điểm null sẽ có cùng khóa; không phân biệt được bằng comparator chính.

Tương tự, dùng `Integer.MAX_VALUE` để đẩy null xuống cuối không luôn an toàn nếu giá trị hợp lệ có thể bằng `Integer.MAX_VALUE`. Nếu thật sự cần giữ null khác mọi số, ưu tiên `Comparator.comparing(..., Comparator.nullsLast(...))`.

Một lựa chọn khác là **lọc bỏ bản ghi thiếu điểm** nếu yêu cầu nghiệp vụ cho phép:

~~~java
// Minh họa trong ngữ cảnh stream Candidate:
List<Candidate> ranked = candidates.stream()
        .filter(java.util.Objects::nonNull)
        .filter(candidate -> candidate.score() != null)
        .sorted(Comparator.comparingInt(candidate -> candidate.score()))
        .toList();
~~~

Kết quả không còn các phần tử null hoặc thiếu score. Đây là thay đổi tập dữ liệu chứ không phải cách đưa null lên đầu/cuối. Phải thể hiện rõ yêu cầu lọc bỏ trước khi áp dụng.

## 6. Bẫy kết hợp `thenComparing()` với `nullsFirst/nullsLast`

Cấu trúc comparator nhiều khóa quan trọng hơn một lời gọi `nullsFirst` đơn lẻ.

**Không an toàn nếu phần tử có thể null:**

~~~java
// Đoạn minh họa sai nếu cả hai đầu vào đều null:
Comparator<Candidate> unsafeOrder =
        Comparator.nullsLast(Comparator.comparingInt(Candidate::score))
                  .thenComparing(Candidate::name);
~~~

Vì sao? Khi hai đối tượng đều null, lớp `nullsLast` có thể trả về 0. Sau đó `thenComparing` tiếp tục so sánh khóa phụ, gọi `Candidate::name` trên null và gây `NullPointerException`. Ngay cả khi chỉ một phần tử null, comparator ban đầu khác 0 nên tránh được khóa phụ; nhưng trường hợp **hai null** vẫn đủ khiến cấu trúc trên sai.

**An toàn hơn khi đặt lớp bảo vệ null ngoài cùng:**

~~~java
// Đoạn minh họa đúng với Candidate không null có name hợp lệ:
Comparator<Candidate> safeOrder =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score)
                          .thenComparing(Candidate::name));
~~~

Trong cấu trúc này, mọi so sánh liên quan tới `Candidate null` được lớp ngoài cùng giải quyết, và chỉ khi cả hai đối tượng đều không null mới gọi comparator gồm khóa chính và phụ. Nếu khóa phụ tự nó nullable, phải cung cấp comparator null-safe tại chính khóa phụ như ở mục 4.

Đối với một chuỗi nhiều khóa, hãy xây dựng đầy đủ comparator cho đối tượng **không null**, rồi bọc `nullsFirst` hoặc `nullsLast` ở lớp ngoài cùng.

## 7. Bẫy `reversed()`: đảo cả thứ tự null nếu đặt sai chỗ

`Comparator.reversed()` đảo thứ tự của **toàn bộ comparator** mà nó áp dụng, bao gồm cả vị trí của null nếu vị trí đó đã được xác định trong comparator.

~~~java
// Candidate có score kiểu int, các đoạn chỉ để minh họa:
Comparator<Candidate> nullsLastAndScoreDesc =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score).reversed());

Comparator<Candidate> nullsFirstAfterReverse =
        Comparator.nullsLast(
                Comparator.comparingInt(Candidate::score)).reversed();
~~~

Với biểu thức đầu, `reversed()` chỉ đảo điểm của phần tử không null, **null vẫn ở cuối**. Với biểu thức thứ hai, toàn bộ comparator “điểm tăng dần, null cuối” bị đảo, vì vậy **null lên đầu** và điểm giảm dần.

Tương tự với khóa `Integer` nullable:

~~~java
// Giữ score == null cuối khi xếp điểm giảm dần:
Comparator<Candidate> scoreDescNullLast =
        Comparator.comparing(
                Candidate::score,
                Comparator.nullsLast(Comparator.reverseOrder()));
~~~

Nếu cả đối tượng cũng có thể null, có thể bọc kết quả này bằng `Comparator.nullsLast(...)`. Hãy quyết định riêng chính sách tăng/giảm của **khóa**, chính sách cho **khóa null**, và chính sách cho **đối tượng null**, rồi ghép chúng theo đúng tầng.

## 8. Sắp xếp tại chỗ, stream và tính ổn định

Các cách dùng sau đều áp dụng bộ so sánh đã tạo:

~~~java
// Minh họa trong phương thức đã có List<Candidate> candidates và Comparator<Candidate> order:
candidates.sort(order);                // Thay đổi thứ tự List có thể sửa.
List<Candidate> copy = candidates.stream()
        .sorted(order)
        .toList();                     // Danh sách kết quả mới, không sửa nguồn.
~~~

Một số lưu ý:

- `List.sort` yêu cầu list hỗ trợ thay đổi phần tử; `List.of(...)` là immutable collection, gọi `sort` trên đó sẽ ném `UnsupportedOperationException`.
- Với danh sách nguồn có thứ tự, `Stream.sorted` ổn định theo thứ tự gặp; `List.sort` cũng là phép sắp xếp ổn định. Hai phần tử có comparator trả 0 giữ thứ tự tương đối ban đầu trong các điều kiện đó.
- Với stream *unordered*, `Stream.sorted` không đưa ra bảo đảm ổn định tương tự.
- Comparator có thể được gọi nhiều lần và không phải theo thứ tự cố định. Tránh lambda đọc trạng thái thường xuyên thay đổi hoặc gây side effect; nên tính giá trị khóa ổn định trước khi sắp xếp nếu cần.
- Không dùng `a.score() - b.score()` làm comparator số nguyên vì có thể tràn số và vi phạm thứ tự; `comparingInt` dùng phép so sánh nguyên an toàn hơn.
- Không nên bắt `NullPointerException` từ comparator để rồi mặc định coi như bằng nhau: cách đó giấu lỗi hợp đồng so sánh và dễ tạo thứ tự thiếu nhất quán.

## 9. Kiểm tra chính sách null bằng dữ liệu biên

Khi xây dựng comparator cho production, hãy thử tối thiểu các trường hợp:

| Bộ dữ liệu | Kỳ vọng cần xác nhận |
| --- | --- |
| Hai đối tượng có điểm khác nhau | Tăng/giảm đúng theo điểm. |
| Hai đối tượng cùng điểm | Khóa phụ (nếu có) hoạt động đúng. |
| Một đối tượng null và một đối tượng hợp lệ | `nullsFirst`/`nullsLast` đặt đúng vị trí. |
| Hai đối tượng đều null | Không có `thenComparing` dereference đối tượng null. |
| Một hoặc hai khóa `Integer` null | Thứ tự các khóa null đúng, không auto-unbox lỗi. |
| Khóa phụ như tên null | Đã có comparator null-safe cho khóa phụ. |
| Có số âm, 0, `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | Không dựa vào phép trừ hoặc sentinel có thể trùng dữ liệu hợp lệ. |
| Đảo thứ tự bằng `reversed()` | Chính sách null vẫn đúng yêu cầu. |

Nếu comparator được dùng lâu dài trong `TreeSet`, `TreeMap` hoặc cấu trúc cây có thứ tự, hãy đảm bảo quan hệ so sánh có tính nhất quán, phản đối xứng và bắc cầu. Trường hợp so sánh trả về 0 cho hai đối tượng khác nhau có thể khiến cấu trúc dựa trên comparator xem chúng như cùng một khóa; có thể cần khóa phụ duy nhất. Comparator không bắt buộc phải nhất quán với `equals`, nhưng nếu không thì cần hiểu hệ quả đối với các tập/map có sắp thứ tự.

## 10. Quy tắc lựa chọn nhanh

| Dữ liệu thực tế | Biểu thức đề xuất |
| --- | --- |
| Đối tượng không null, khóa `int` | `Comparator.comparingInt(Person::age)` |
| Đối tượng có thể null, khóa `int` | `Comparator.nullsLast(Comparator.comparingInt(Person::age))` |
| Đối tượng không null, khóa `Integer` có thể null | `Comparator.comparing(Person::age, Comparator.nullsLast(Comparator.naturalOrder()))` |
| Cả đối tượng và khóa `Integer` đều có thể null | `Comparator.nullsLast(Comparator.comparing(Person::age, Comparator.nullsLast(Comparator.naturalOrder())))` |
| Có khóa phụ và đối tượng null | Bọc `Comparator.nullsLast(...)` **sau khi** đã ghép đủ `thenComparing(...)` |
| Điểm giảm dần nhưng null phải cuối | Đảo comparator của khóa bên trong, rồi bọc `nullsLast` theo tầng. |

**Ghi nhớ:** `Comparator.comparingInt()` lý tưởng cho **khóa `int` không null**. `Comparator.nullsFirst()/nullsLast()` phải đặt đúng cấp: bao quanh comparator của **đối tượng** để bảo vệ phần tử null, và bao quanh comparator của **khóa** khi dùng `comparing()` với khóa `Integer` nullable. Cần phân định rõ chính sách null trước khi thêm khóa phụ và đảo thứ tự.
