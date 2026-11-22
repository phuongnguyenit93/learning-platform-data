# Comparator.comparing(), thenComparing() và đảo thứ tự trong Java

Khi sắp xếp danh sách đối tượng, ta thường cần nhiều tiêu chí: **phòng ban tăng dần, điểm giảm dần, rồi tên tăng dần**. Java cung cấp `Comparator<T>` như một *hành vi so sánh* có thể truyền vào `List.sort(...)`, `Stream.sorted(...)` hoặc các API khác. Các phương thức `Comparator.comparing(...)`, `thenComparing(...)` và `reversed()` cho phép mô tả thứ tự đó theo cách khai báo, tận dụng lambda và method reference.

Bài này tập trung vào cách tạo và phối hợp các `Comparator`, đặc biệt là **phân biệt đảo chiều một tiêu chí với đảo chiều toàn bộ chuỗi tiêu chí**.

## 1. Nền tảng: một Comparator quyết định thứ tự như thế nào?

`Comparator<T>` là một functional interface, có phương thức trừu tượng:

~~~java
int compare(T left, T right);
~~~

Giá trị trả về chỉ cần bảo đảm dấu:

- **Âm** nếu `left` đứng trước `right`.
- **Bằng 0** nếu hai đối tượng ngang nhau theo tiêu chí so sánh đang dùng.
- **Dương** nếu `left` đứng sau `right`.

Không cần trả về đúng `-1`, `0`, `1`. Ví dụ `String.compareTo` có thể trả về các số âm/dương khác.

`compare(left, right) == 0` có nghĩa là hai phần tử có **khóa sắp xếp ngang nhau**, không nhất thiết `left.equals(right)`. Các comparator chuẩn cần tuân thủ tính phản đối xứng về dấu, tính bắc cầu và tính nhất quán khi so sánh các bộ ba phần tử. Trong suốt một lần sort, dữ liệu khóa nên ổn định để tránh vi phạm hợp đồng so sánh.

Cách truyền hành vi so sánh vào API:

~~~java
List<String> cities = new ArrayList<>(List.of("Hue", "Ha Noi", "Da Nang"));
cities.sort(Comparator.comparingInt(String::length));
~~~

Đoạn mã trên cần import `java.util.List`, `java.util.ArrayList` và `java.util.Comparator`, đồng thời đặt trong một phương thức. `List.sort(...)` **thay đổi thứ tự danh sách hiện có**, còn `Stream.sorted(...)` tạo một stream mới với thứ tự sắp xếp (không tự sắp xếp lại nguồn).

## 2. Comparator.comparing(): tạo Comparator từ khóa trích xuất

Dạng thường dùng:

~~~java
Comparator.comparing(keyExtractor)
~~~

`keyExtractor` là một `Function<T, U>` lấy **khóa sắp xếp** từ phần tử `T`. Kiểu khóa `U` phải có thứ tự tự nhiên thông qua `Comparable` phù hợp, chẳng hạn `String`, `Integer` hoặc `LocalDate`.

Ví dụ khi có `record Member(String team, String name, int points, int age) {}`:

~~~java
Comparator<Member> byName = Comparator.comparing(Member::name);
Comparator<Member> byTeam = Comparator.comparing(m -> m.team());
~~~

`Member::name` tương đương lambda `m -> m.name()`. Với `byName.compare(a, b)`, comparator lấy `a.name()` và `b.name()` rồi so sánh hai khóa theo thứ tự tự nhiên của `String`. Mặc định là **tăng dần**.

Khi khóa không có thứ tự tự nhiên phù hợp hoặc cần quy tắc khác, dùng overload thứ hai:

~~~java
Comparator.comparing(keyExtractor, keyComparator)
~~~

Ví dụ sắp xếp theo tên không phân biệt chữ hoa/thường:

~~~java
Comparator<Member> byNameIgnoreCase =
        Comparator.comparing(Member::name, String.CASE_INSENSITIVE_ORDER);
~~~

Ở đây `String.CASE_INSENSITIVE_ORDER` so sánh khóa `String`, **không** phải toàn bộ đối tượng `Member`. Với các từ tiếng Việt, quy tắc phân loại theo ngôn ngữ có thể cần `Collator` phù hợp; thứ tự tự nhiên của `String` là thứ tự Unicode, không bảo đảm thứ tự từ điển tiếng Việt mong muốn.

### Dùng biến thể dành cho kiểu nguyên thủy

Nếu khóa là `int`, `long` hoặc `double`, ưu tiên:

~~~java
Comparator<Member> byPoints = Comparator.comparingInt(Member::points);
Comparator<Member> byAge = Comparator.comparingInt(Member::age);
~~~

Các phương thức liên quan là `comparingInt(ToIntFunction)`, `comparingLong(ToLongFunction)` và `comparingDouble(ToDoubleFunction)`. Chúng giúp tránh boxing/unboxing khóa nguyên thủy thường gặp khi dùng `comparing(Function)`.

Ví dụ `Comparator.comparing(Member::points)` cũng có thể dùng nhờ autoboxing từ `int` sang `Integer`, nhưng `comparingInt(Member::points)` nêu rõ ý định và tránh việc tạo khóa boxed cho phần so sánh đó.

## 3. thenComparing(): thêm tiêu chí phụ theo thứ tự ưu tiên

Sắp xếp nhiều khóa thực hiện theo nguyên tắc *so sánh từ trái sang phải* (lexicographic ordering):

1. So sánh tiêu chí chính.
2. **Chỉ khi tiêu chí chính bằng 0**, xét tiêu chí phụ đầu tiên.
3. **Chỉ khi các tiêu chí trước đều bằng 0**, xét tiêu chí tiếp theo.
4. Nếu tất cả tiêu chí bằng 0, `compare(...)` trả về 0.

Ví dụ:

~~~java
Comparator<Member> order = Comparator.comparing(Member::team)
        .thenComparing(Member::name)
        .thenComparingInt(Member::age);
~~~

Ý nghĩa là **team tăng dần → name tăng dần → age tăng dần**. `thenComparing` không sắp xếp riêng rẽ một lần nữa; nó tạo **một comparator tổng hợp**, mỗi phép so sánh có thể rẽ sang tiêu chí tiếp theo nếu cần.

Những overload phổ biến:

| Cách viết | Cách áp dụng |
| --- | --- |
| `thenComparing(otherComparator)` | Dùng một comparator khác cho cùng kiểu phần tử `T` khi các tiêu chí trước hòa |
| `thenComparing(keyExtractor)` | So sánh khóa phụ theo thứ tự tự nhiên |
| `thenComparing(keyExtractor, keyComparator)` | So sánh khóa phụ bằng comparator riêng cho kiểu khóa |
| `thenComparingInt(keyExtractor)` | Khóa phụ `int`, không boxing |
| `thenComparingLong(keyExtractor)` | Khóa phụ `long` |
| `thenComparingDouble(keyExtractor)` | Khóa phụ `double` |

Vì `thenComparing` trả về `Comparator<T>`, ta có thể nối nhiều lời gọi thành một pipeline. Thứ tự các lời gọi quyết định **mức ưu tiên**: đặt khóa quan trọng nhất trước.

Một comparator thể hiện thứ tự rõ ràng thường dễ bảo trì hơn việc viết `compare` dài với nhiều nhánh `if`. Tuy nhiên, phương thức `compare` tường minh vẫn phù hợp khi logic so sánh phức tạp và cần xử lý trạng thái đặc biệt.

## 4. Ba cách đảo thứ tự và sự khác biệt

### 4.1. reversed(): đảo **toàn bộ** comparator hiện tại

~~~java
Comparator<Member> byTeamThenAge =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::age);
Comparator<Member> completelyReversed = byTeamThenAge.reversed();
~~~

`completelyReversed` đảo kết quả của **tất cả tiêu chí trong comparator đã ghép**: team giảm dần và (khi cùng team) age giảm dần.

Cách đọc đối chiếu:

~~~java
Comparator<Member> allDescending =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::age)
                  .reversed(); // Đảo cả team VÀ age
~~~

`reversed()` là phương thức instance của `Comparator<T>`; nó tạo comparator theo chiều ngược với comparator được gọi.

### 4.2. Chỉ đảo một khóa khi xây dựng chuỗi

Giả sử yêu cầu là **team tăng dần, points giảm dần, name tăng dần**. Nếu viết:

~~~java
Comparator<Member> incorrectForRequirement =
        Comparator.comparing(Member::team)
                  .thenComparingInt(Member::points)
                  .thenComparing(Member::name)
                  .reversed();
~~~

thì cả team, points và name đều bị đảo, **không đúng yêu cầu**. Để chỉ đảo điểm, tạo comparator riêng cho khóa điểm rồi gắn nó làm tiêu chí phụ:

~~~java
Comparator<Member> correctOrder =
        Comparator.comparing(Member::team)
                  .thenComparing(Comparator.comparingInt(Member::points).reversed())
                  .thenComparing(Member::name);
~~~

Chú ý cặp dấu ngoặc: `reversed()` nằm **bên trong** đối số của `thenComparing(...)`, vì ta chỉ muốn đảo comparator điểm. Cách tương đương cho khóa đối tượng là:

~~~java
Comparator<Member> orderByTeamAndNameDescending =
        Comparator.comparing(Member::team)
                  .thenComparing(Member::name, Comparator.reverseOrder());
~~~

Trong trường hợp này, `Comparator.reverseOrder()` là comparator cho **khóa `String`** của `name`, khiến tên giảm dần trong từng team. Team vẫn tăng dần.

### 4.3. Comparator.reverseOrder() khác reversed()

- `Comparator.reverseOrder()` là phương thức **static**, trả về comparator dùng **thứ tự tự nhiên đảo ngược** cho các giá trị `Comparable` (ví dụ `String`, `Integer`). Nó không cần có comparator gốc.
- `someComparator.reversed()` là phương thức **instance**, đảo kết quả của `someComparator`, kể cả khi comparator gốc so sánh nhiều khóa hoặc có quy tắc tùy chỉnh.
- `Comparator.naturalOrder()` là comparator theo thứ tự tự nhiên, giúp làm rõ cách viết khi cần so sánh trực tiếp các đối tượng `Comparable`.

Ví dụ:

~~~java
List<String> tags = new ArrayList<>(List.of("b", "a", "c"));
tags.sort(Comparator.reverseOrder());
// tags == [c, b, a]
~~~

Đoạn này cần import `List`, `ArrayList`, `Comparator` và đặt trong một phương thức.

## 5. Chương trình minh họa hoàn chỉnh, Java 17+

Đặt toàn bộ đoạn sau vào tệp **`ComparatorChainDemo.java`**. Dữ liệu có nhiều phần tử trùng team và points để thấy `thenComparing` hoạt động.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorChainDemo {
    record Member(String team, String name, int points, int age) {}

    public static void main(String[] args) {
        List<Member> members = new ArrayList<>(List.of(
                new Member("Backend", "An", 90, 24),
                new Member("Frontend", "Binh", 75, 22),
                new Member("Backend", "Binh", 90, 30),
                new Member("Backend", "Chi", 70, 28),
                new Member("Frontend", "An", 75, 26),
                new Member("Backend", "An", 90, 21)
        ));

        Comparator<Member> byPriority =
                Comparator.comparing(Member::team)
                        .thenComparing(Comparator.comparingInt(Member::points).reversed())
                        .thenComparing(Member::name)
                        .thenComparingInt(Member::age);

        System.out.println("TEAM ASC, POINTS DESC, NAME ASC, AGE ASC:");
        members.sort(byPriority);
        members.forEach(ComparatorChainDemo::print);

        System.out.println("REVERSE ENTIRE ORDER:");
        members.sort(byPriority.reversed());
        members.forEach(ComparatorChainDemo::print);

        System.out.println("REVERSED NATURAL STRINGS:");
        List<String> tags = new ArrayList<>(List.of("b", "a", "c"));
        tags.sort(Comparator.reverseOrder());
        System.out.println(tags);
    }

    static void print(Member member) {
        System.out.printf("%s | %s | %d | %d%n",
                member.team(), member.name(), member.points(), member.age());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac ComparatorChainDemo.java
java ComparatorChainDemo
~~~

**Đầu ra chính xác:**

~~~text
TEAM ASC, POINTS DESC, NAME ASC, AGE ASC:
Backend | An | 90 | 21
Backend | An | 90 | 24
Backend | Binh | 90 | 30
Backend | Chi | 70 | 28
Frontend | An | 75 | 26
Frontend | Binh | 75 | 22
REVERSE ENTIRE ORDER:
Frontend | Binh | 75 | 22
Frontend | An | 75 | 26
Backend | Chi | 70 | 28
Backend | Binh | 90 | 30
Backend | An | 90 | 24
Backend | An | 90 | 21
REVERSED NATURAL STRINGS:
[c, b, a]
~~~

Phân tích:

- Tất cả `Backend` đứng trước `Frontend` vì khóa `team` so sánh tăng dần.
- Trong `Backend`, nhóm `points=90` đứng trước `points=70` vì chỉ **khóa points** được đảo chiều.
- Hai phần tử `Backend / An / 90` được phân biệt bằng `age` cuối cùng: `21` rồi `24`.
- Khi gọi `byPriority.reversed()`, các quan hệ sắp xếp **đảo toàn bộ**, nên `Frontend` đứng đầu; trong mỗi nhóm, thứ tự các khóa còn lại cũng đảo.
- `Comparator.reverseOrder()` sắp xếp ba chuỗi `a, b, c` theo thứ tự tự nhiên giảm dần.

Mã sử dụng `record`, có sẵn từ Java 16, vì thế chạy hợp lệ trên Java 17+. `List.of(...)` trả về danh sách không thể thay đổi cấu trúc; cần `new ArrayList<>(...)` để dùng `List.sort(...)` trực tiếp.

## 6. Sử dụng comparator trong API nhận hành vi

`Comparator` là dữ liệu biểu diễn **hành vi so sánh**, nên có thể truyền qua tham số API. Ví dụ một phương thức nhận comparator do người gọi lựa chọn:

~~~java
static <T> List<T> sortedCopy(List<T> source, Comparator<? super T> comparator) {
    return source.stream().sorted(comparator).toList();
}
~~~

Đây là **đoạn phương thức** cần đặt trong một lớp và import `List`, `Comparator`. Kết quả `Stream.toList()` là danh sách không hỗ trợ các thao tác thay đổi cấu trúc; không nên gọi `sort` trên kết quả đó.

Người gọi có thể tái sử dụng một quy tắc sắp xếp duy nhất ở nhiều nơi:

~~~java
Comparator<Member> byNameThenAge =
        Comparator.comparing(Member::name)
                  .thenComparingInt(Member::age);

members.sort(byNameThenAge);            // Thay đổi list hiện có
List<Member> copy = members.stream()
        .sorted(byNameThenAge)
        .toList();                      // Tạo kết quả mới
~~~

`copy` là danh sách kết quả; việc sắp xếp stream không yêu cầu sửa thứ tự `members`. Đây là lợi ích quan trọng khi API nhận hành vi: phần xử lý có thể độc lập với tiêu chí do bên gọi cung cấp.

`Collections.sort(list, comparator)` cũng chấp nhận `Comparator`; với API hiện đại, `list.sort(comparator)` thường ngắn gọn hơn.

## 7. Khóa null và đối tượng null: xử lý rõ ràng

**`Comparator.comparing(Member::name)` mặc định không xử lý khóa `null`.** Khi gặp tên `null`, phép so sánh tự nhiên có thể ném `NullPointerException`. Nếu ứng dụng cho phép tên vắng mặt, hãy chỉ định rõ vị trí của khóa thiếu:

~~~java
Comparator<Member> byNullableName =
        Comparator.comparing(
                Member::name,
                Comparator.nullsLast(Comparator.naturalOrder())
        );
~~~

Với comparator trên, Member có `name == null` đứng **sau** các Member có tên không null. `Comparator.nullsFirst(...)` làm ngược lại; hai phương thức này là comparator bao ngoài để xử lý null một cách có chủ đích.

**Phân biệt khóa null và chính phần tử null.** `nullsLast` ở trong `comparing` chỉ xử lý giá trị khóa `name`, nhưng không bảo vệ phép gọi `Member::name` khi chính phần tử `Member` là null. Muốn xử lý phần tử null:

~~~java
Comparator<Member> nullableMembers =
        Comparator.nullsLast(Comparator.comparing(Member::name));
~~~

Ở đây các **phần tử null** đứng cuối. Nếu cả phần tử lẫn khóa có thể null, ghép cả hai tầng:

~~~java
Comparator<Member> bothNullCases =
        Comparator.nullsLast(
                Comparator.comparing(
                        Member::name,
                        Comparator.nullsLast(Comparator.naturalOrder())
                )
        );
~~~

Khi cần sắp xếp giảm dần có null, hãy chú ý thứ tự áp dụng `reversed()`: đảo comparator sau khi bọc `nullsLast` có thể khiến null chuyển lên đầu. Muốn quy tắc **không null giảm dần, null vẫn cuối**, đặt `reverseOrder()` bên trong:

~~~java
Comparator<Member> nameDescNullLast =
        Comparator.comparing(
                Member::name,
                Comparator.nullsLast(Comparator.reverseOrder())
        );
~~~

Các ví dụ trong mục này là các đoạn mã minh họa đặt trong lớp có `Member` và import phù hợp.

## 8. Lỗi phổ biến, hợp đồng so sánh và thực hành tốt

### Đảo sai phạm vi

`comparing(A).thenComparing(B).reversed()` đảo **cả A và B**; `comparing(A).thenComparing(comparing(B).reversed())` chỉ đảo **B**. Hãy đặt `reversed()` đúng chỗ trong biểu thức.

### Trả về phép trừ hai số làm kết quả compare

Không nên viết:

~~~java
Comparator<Member> unsafe = (a, b) -> a.points() - b.points();
~~~

Phép trừ `int` có thể tràn số, phá vỡ dấu so sánh. Dùng `Integer.compare(a.points(), b.points())` hoặc `Comparator.comparingInt(Member::points)` để an toàn. Với nhu cầu đảo chiều, dùng `reversed()`, không cần tự đổi dấu bằng phép trừ.

### Nhầm so sánh bằng 0 với hai đối tượng bằng nhau

Nếu chỉ so theo `name`, hai Member khác `age` vẫn có thể được `compare` trả 0. `List.sort` và `Stream.sorted` là các phép sort ổn định trên các nguồn có thứ tự: những phần tử ngang nhau theo comparator giữ thứ tự tương đối ban đầu. Tuy nhiên, `TreeSet` và `TreeMap` dùng comparator để xác định khóa trùng; `compare(a, b) == 0` khiến chúng xem hai khóa là tương đương dù `equals` có thể khác. Nếu cần phân biệt thực thể, thêm tiêu chí phá hòa thích hợp, chẳng hạn ID duy nhất.

### Phân biệt thứ tự tự nhiên và so sánh tùy chỉnh

`Comparator.comparing(Member::name)` dùng thứ tự tự nhiên của `String`, phân biệt hoa/thường; `comparing(Member::name, String.CASE_INSENSITIVE_ORDER)` thay quy tắc so khóa. Đừng áp dụng thứ tự so sánh theo chữ cái tiếng Anh cho yêu cầu phân loại ngôn ngữ tự nhiên mà không xét locale.

### Khóa thay đổi trong khi sort

Comparator nên ổn định và không gây side effect. Không nên làm key extractor cập nhật dữ liệu, gọi API mạng, phát sinh số ngẫu nhiên hoặc thay đổi các trường dùng để so sánh. Nếu khóa đắt đỏ để tính, hãy cân nhắc tính trước/cache ngoài comparator và kiểm soát tính nhất quán.

### Cho rằng mọi List đều có thể sort tại chỗ

`List.of(...)` và danh sách từ `Stream.toList()` không hỗ trợ thay đổi thứ tự qua `sort`. Tạo `new ArrayList<>(source)` trước khi sort tại chỗ; hoặc dùng `source.stream().sorted(comparator).toList()` khi muốn kết quả mới.

### Tiêu chí phụ không nhất quán hoặc bị bỏ sót

Ví dụ chỉ so theo `team` rồi `points` có thể để nhiều Member có cùng khóa. Nếu ứng dụng cần thứ tự kết quả xác định ngay cả khi đầu vào có thứ tự khác nhau, hãy thêm khóa phá hòa như `thenComparing(Member::name).thenComparingInt(Member::age)` hoặc một ID duy nhất. Không thêm khóa phá hòa chỉ để thay đổi ngữ nghĩa nếu yêu cầu muốn các phần tử ngang nhau.

### Null và đảo thứ tự

`Comparator.reverseOrder()` không tự động xử lý `null`. Dùng `nullsFirst` hoặc `nullsLast` đúng cấp, và kiểm tra lại chính sách null sau khi gọi `reversed()`. Ngoài ra, `Comparator.comparing(...)` sẽ không thể trích xuất khóa từ đối tượng null nếu chưa có comparator bao ngoài.

## 9. Ghi nhớ cách lựa chọn

| Nhu cầu | Mẫu Comparator |
| --- | --- |
| Một khóa tăng dần | `Comparator.comparing(Member::name)` |
| Khóa `int` tăng dần | `Comparator.comparingInt(Member::age)` |
| Một khóa theo comparator riêng | `Comparator.comparing(Member::name, String.CASE_INSENSITIVE_ORDER)` |
| Nhiều khóa tăng dần | `Comparator.comparing(Member::team).thenComparing(Member::name)` |
| Khóa chính tăng, khóa phụ giảm | `Comparator.comparing(Member::team).thenComparing(Comparator.comparingInt(Member::points).reversed())` |
| Đảo toàn bộ bộ so sánh | `existingComparator.reversed()` |
| Đảo thứ tự tự nhiên của phần tử `Comparable` | `Comparator.reverseOrder()` |
| Khóa có thể null, null cuối | `Comparator.comparing(Member::name, Comparator.nullsLast(Comparator.naturalOrder()))` |

Điểm quyết định là **vị trí trong chuỗi**: `comparing` xác định khóa đầu, `thenComparing` bổ sung các khóa theo mức ưu tiên, còn `reversed` đảo comparator mà nó được gọi trên. Viết comparator đúng cấu trúc sẽ giúp hành vi sắp xếp rõ ràng, tái sử dụng được và dễ kiểm chứng.