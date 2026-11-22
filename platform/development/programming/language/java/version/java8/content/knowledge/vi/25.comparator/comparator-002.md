# comparingInt, comparingLong, comparingDouble trong Java Comparator

`Comparator.comparingInt`, `Comparator.comparingLong` và `Comparator.comparingDouble` là ba phương thức factory tạo `Comparator<T>` theo **khóa số kiểu primitive** được trích từ mỗi đối tượng. Chúng có từ **Java 8**, vẫn có mặt trong Java hiện hành và rất hữu ích khi sắp xếp danh sách đối tượng theo tuổi, số lượng, số lượt xem, mốc thời gian, điểm số hoặc các tiêu chí số khác.

Một lỗi quen thuộc là tự viết phép so sánh bằng phép trừ:

```java
(a, b) -> a.age() - b.age() // Có thể overflow!
```

Thay vào đó:

```java
Comparator<Person> byAge = Comparator.comparingInt(Person::age);
```

`comparingInt` dùng quy tắc so sánh `int` đúng, không tự gây lỗi tràn số do lấy hiệu hai giá trị. Hai phương thức còn lại có mục đích tương ứng với `long` và `double`. Tuy nhiên, **kiểu khóa quyết định ngữ nghĩa so sánh**: `long` giữ độ chính xác nguyên 64 bit, còn `double` có các quy tắc đặc biệt cho `NaN`, vô cực và `-0.0`.

Bài học tập trung vào cách chọn đúng phương thức, nối nhiều tiêu chí và tránh lỗi với giá trị biên, null, số thực và cấu trúc dữ liệu có thứ tự. Ví dụ hoàn chỉnh dùng **JDK 17+** để tiện viết `record` và `Stream.toList()`; ba factory Comparator và các phương thức `thenComparingInt/Long/Double` đã dùng được từ **Java 8**.

## 1. Khái niệm: so sánh đối tượng dựa trên khóa số

`Comparator<T>` định nghĩa cách so sánh hai đối tượng kiểu `T`. Một phép so sánh trả số:
- **Âm**: đối tượng bên trái đứng trước đối tượng bên phải.
- **0**: hai đối tượng được xem là tương đương **theo tiêu chí của comparator**.
- **Dương**: đối tượng bên trái đứng sau đối tượng bên phải.

Không cần trả đúng `-1`, `0`, `1`; dấu của giá trị mới quyết định thứ tự. Comparator phải tuân thủ các yêu cầu về dấu ngược, tính bắc cầu và hành vi nhất quán trên các phần tử.

Ví dụ một `Product` có các thuộc tính `stock`, `views` và `rating`. Ta có thể tạo ba thứ tự khác nhau:

```java
Comparator<Product> byStock =
        Comparator.comparingInt(Product::stock);

Comparator<Product> byViews =
        Comparator.comparingLong(Product::views);

Comparator<Product> byRating =
        Comparator.comparingDouble(Product::rating);
```

Đây là **đoạn mã minh họa trong phạm vi đã định nghĩa `Product`**; ví dụ đầy đủ nằm ở mục 3.

Mặc định, cả ba factory tạo thứ tự **tăng dần** theo khóa trích xuất. Một comparator không tự thay đổi collection; nó được đưa vào `List.sort`, `Stream.sorted`, `TreeSet`, `TreeMap` hoặc API khác cần quan hệ thứ tự.

## 2. Chữ ký API và cách chọn kiểu extractor

Các chữ ký rút gọn từ `java.util.Comparator`:

```java
static <T> Comparator<T> comparingInt(
        ToIntFunction<? super T> keyExtractor);

static <T> Comparator<T> comparingLong(
        ToLongFunction<? super T> keyExtractor);

static <T> Comparator<T> comparingDouble(
        ToDoubleFunction<? super T> keyExtractor);
```

`ToIntFunction<T>` trả `int`, `ToLongFunction<T>` trả `long`, `ToDoubleFunction<T>` trả `double`. Đây là các functional interface cho khóa **primitive**, không phải `Function<T, Integer>`, `Function<T, Long>` hay `Function<T, Double>`.

| Tiêu chí dữ liệu | Factory | Kiểu khóa | Cơ chế so sánh ý nghĩa |
| --- | --- | --- | --- |
| Tuổi, số lượng, điểm nguyên trong miền `int` | `comparingInt` | `int` | Thứ tự số nguyên `int`, như `Integer.compare` |
| Số lượt xem lớn, mili-giây, định danh số nguyên `long` | `comparingLong` | `long` | Thứ tự số nguyên `long`, như `Long.compare` |
| Điểm thập phân, số đo khoa học | `comparingDouble` | `double` | Thứ tự theo `Double.compare`, có quy tắc cho `NaN`/signed zero |
| Khóa `String`, `BigDecimal`, `LocalDate` hoặc `enum` | `comparing` generic | Khóa đối tượng | So sánh theo `Comparable` hoặc comparator truyền vào |
| Khóa `Integer` có thể `null` | `comparing(..., nullsFirst/Last(...))` | Khóa đối tượng nullable | Quyết định vị trí của null rõ ràng |

### Vì sao dùng primitive specialization?

`Comparator.comparing(Product::stock)` cũng có thể hợp lệ khi `stock()` trả `int`: Java boxing khóa thành `Integer` để đáp ứng `Function<Product, Integer>`. Nhưng `comparingInt(Product::stock)` biểu đạt rõ extractor trả **primitive `int`**, tránh yêu cầu boxing khóa cho phép so sánh trong factory.

Tương tự, `comparingLong` và `comparingDouble` giúp chọn ngữ nghĩa theo đúng kiểu số. Không nên hứa chúng **luôn nhanh hơn một mức cố định**; hiệu năng còn phụ thuộc JIT, dữ liệu, số lần so sánh, cache, allocation và phần việc của extractor. Lợi ích chắc chắn nhất là **đúng kiểu dữ liệu và diễn đạt ý định rõ**.

### Chọn kiểu trước khi chuyển đổi

Nếu khóa vốn là `long`, đừng tùy tiện viết:

```java
Comparator<Event> risky =
        Comparator.comparingDouble(e -> e.id());
```

Nếu `Event.id()` trả `long` lớn, chuyển `long → double` có thể mất các đơn vị nguyên. Nếu thứ tự cần chính xác, viết `Comparator.comparingLong(Event::id)`. Một comparator rất nhanh nhưng **xếp nhầm hai ID gần nhau** vẫn là lỗi nghiệp vụ.

## 3. Ví dụ đầy đủ: sắp xếp theo int, long, double

Tạo tệp `PrimitiveComparatorDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class PrimitiveComparatorDemo {
    record Product(String sku, int stock, long views, double rating) {}

    static List<String> keys(List<Product> products) {
        return products.stream().map(Product::sku).toList();
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("A", 12, 9_000_000_000L, 4.5),
                new Product("B", -2, 20L, 3.7),
                new Product("C", 12, 15L, 5.0),
                new Product("D", 0, 20L, Double.NaN),
                new Product("E", Integer.MIN_VALUE,
                        Long.MAX_VALUE, -0.0),
                new Product("F", Integer.MAX_VALUE,
                        Long.MIN_VALUE, +0.0));

        System.out.println("stock = " + keys(
                products.stream()
                        .sorted(Comparator.comparingInt(Product::stock))
                        .toList()));

        System.out.println("views = " + keys(
                products.stream()
                        .sorted(Comparator.comparingLong(Product::views))
                        .toList()));

        System.out.println("rating = " + keys(
                products.stream()
                        .sorted(Comparator.comparingDouble(Product::rating))
                        .toList()));

        System.out.println("rating reversed = " + keys(
                products.stream()
                        .sorted(Comparator.comparingDouble(Product::rating)
                                .reversed())
                        .toList()));

        System.out.println("stock original unchanged = "
                + keys(products));
    }
}
```

```bash
javac -encoding UTF-8 PrimitiveComparatorDemo.java
java PrimitiveComparatorDemo
```

Đầu ra:

```text
stock = [E, B, D, A, C, F]
views = [F, C, B, D, A, E]
rating = [E, F, B, A, C, D]
rating reversed = [D, C, A, B, F, E]
stock original unchanged = [A, B, C, D, E, F]
```

**Giải thích kết quả:**

- `stock` tăng từ `Integer.MIN_VALUE` (E), qua `-2` (B), `0` (D), hai giá trị `12` (A/C), rồi `Integer.MAX_VALUE` (F).
- `views` tăng từ `Long.MIN_VALUE` (F) tới `Long.MAX_VALUE` (E). Hai phần tử B và D cùng có `views = 20`, nên thứ tự tương đối giữ như nguồn khi sort ổn định.
- `rating`: `-0.0` (E) đứng **trước** `+0.0` (F), rồi `3.7`, `4.5`, `5.0`, cuối cùng `NaN` (D), đúng theo `Double.compare`.
- `reversed()` đảo toàn bộ thứ tự đánh giá của comparator: ở đây NaN đứng đầu.
- `stream().sorted(...)` tạo pipeline/result mới, **không sửa `products`**. Bản thân `List.of` cũng trả danh sách unmodifiable, nên không gọi `products.sort(...)` trên nó.

`Stream.sorted` là sort ổn định đối với **ordered stream**; `List.sort` cũng ổn định. Tuy nhiên, nguồn `unordered` không có bảo đảm giữ thứ tự tương đối của các phần tử có khóa bằng nhau. Để thứ tự của kết quả đồng hạng không phụ thuộc đầu vào, hãy thêm tie-breaker như `thenComparing(Product::sku)`.

## 4. Vì sao không viết comparator bằng phép trừ?

Phản ví dụ:

```java
Comparator<Item> bad = (a, b) ->
        a.count() - b.count();
```

Khi `count` là `int`, hiệu của hai số trong miền `int` **có thể vượt miền `int`**, tạo overflow. Kết quả có thể mang dấu **ngược với quan hệ lớn/nhỏ thực tế**, khiến sắp xếp sai và vi phạm hợp đồng comparator.

Giả sử:
- `a.count() = Integer.MIN_VALUE`.
- `b.count() = Integer.MAX_VALUE`.

Trong số học nguyên có giới hạn của Java, `MIN_VALUE - MAX_VALUE` trả `1` do overflow. Comparator sai kết luận `a > b` dù về toán học `a < b`.

Đúng hơn:

```java
Comparator<Item> safe =
        Comparator.comparingInt(Item::count);

// Nếu chỉ so sánh hai int rời:
int result = Integer.compare(aCount, bCount);
```

Đối với `long` cũng không dùng `(int) (a.longValue() - b.longValue())` hoặc phép trừ `long` để quyết định dấu. Hãy dùng `Comparator.comparingLong`/`Long.compare`. Hai hàm này so sánh đúng cả các giá trị biên `Long.MIN_VALUE` và `Long.MAX_VALUE`.

Nếu chỉ cần đảo thứ tự, `Comparator.comparingInt(Item::count).reversed()` rõ và an toàn hơn `(a, b) -> b.count() - a.count()`.

## 5. Phép chuyển long sang double có thể phá thứ tự cần chính xác

Kiểu `double` có khoảng **53 bit độ chính xác phần trị**, trong khi `long` là số nguyên có dấu 64 bit. Mọi số nguyên `long` **không nhất thiết** biểu diễn chính xác bằng `double`.

Hai giá trị:

```text
2^53     = 9007199254740992
2^53 + 1 = 9007199254740993
```

là hai số `long` khác nhau, nhưng khi chuyển thành `double`, `2^53 + 1` được làm tròn thành giá trị `2^53`. Nếu dùng `comparingDouble(x -> x.longId())`, hai khóa có thể được comparator xem là **tương đương**, dù về `long` chúng khác nhau.

Hậu quả:
- Sắp xếp ID/timestamp/counter `long` có thể không đúng thứ tự chi tiết.
- `TreeSet` với comparator sai kiểu có thể xem hai phần tử khác nhau thành “trùng” khóa.
- `Stream.sorted` ổn định có thể giữ thứ tự đầu vào của hai phần tử bị làm tròn bằng nhau, tạo cảm giác sắp xếp không tác dụng.
- Phép so sánh chính xác số nguyên phải giữ kiểu `long` với `comparingLong`, không dùng kiểu `double` chỉ vì nó có miền số thực lớn.

**Widening primitive conversion `long → double` là hợp lệ nhưng có thể mất chính xác.** Widening về miền biểu diễn không đồng nghĩa bảo toàn mọi chữ số nguyên. Với tiền cần chính xác, cân nhắc `long` theo đơn vị nhỏ nhất (khi miền đủ) hoặc `BigDecimal` cùng comparator generic.

## 6. Trường hợp double: NaN, ±Infinity và signed zero

`Comparator.comparingDouble` sử dụng thứ tự như `Double.compare`, **khác việc dùng toán tử `<`/`>` hoặc lấy hiệu**. Điều này đặc biệt quan trọng với:

| Giá trị double | Vị trí theo thứ tự tăng dần |
| --- | --- |
| `Double.NEGATIVE_INFINITY` | Nhỏ nhất |
| Số hữu hạn âm | Sau âm vô cực |
| `-0.0` | Sau các số âm, **trước `+0.0`** |
| `+0.0` | Trước các số dương |
| Số hữu hạn dương | Sau `+0.0` |
| `Double.POSITIVE_INFINITY` | Sau mọi số hữu hạn |
| `Double.NaN` | **Lớn hơn mọi giá trị double khác, kể cả +Infinity** theo `Double.compare` |

Theo toán tử primitive, `-0.0 == +0.0` là `true`. Nhưng `Double.compare(-0.0, +0.0) < 0`; comparator **phân biệt hai dạng zero**. Các giá trị NaN được `Double.compare` sắp xếp ở phía sau, các NaN được coi tương đương với nhau trong thứ tự so sánh này.

### Lưu ý nghiệp vụ

NaN không phải “điểm số cao nhất” theo ý nghĩa thực tế. `Double.compare` chọn một **total ordering** phù hợp cho sắp xếp, chứ không quyết định quy tắc xếp hạng điểm hay số liệu kinh doanh. Nếu dữ liệu không cho phép NaN/Infinity, nên **kiểm tra bằng `Double.isFinite` hoặc chính sách rõ ràng** trước khi xếp hạng. Nếu domain xem `-0.0` và `+0.0` là tương đương, cân nhắc chuẩn hóa khóa trước khi so sánh.

Đừng dùng:

```java
(a, b) -> (int) (a.score() - b.score())
```

Hiệu nhỏ hơn 1 có thể ép về 0, vô cực hoặc NaN cũng dẫn đến hành vi không đúng. Hãy dùng `comparingDouble` hoặc `Double.compare` theo ngữ nghĩa mong muốn.

## 7. Ví dụ đầy đủ: so sánh các giá trị double đặc biệt và phần tử null

Tạo tệp `FloatingComparatorDemo.java`:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class FloatingComparatorDemo {
    record Measure(String id, double value) {}

    public static void main(String[] args) {
        List<Measure> values = List.of(
                new Measure("NAN", Double.NaN),
                new Measure("PLUS_ZERO", +0.0),
                new Measure("MINUS_INF", Double.NEGATIVE_INFINITY),
                new Measure("PLUS_INF", Double.POSITIVE_INFINITY),
                new Measure("NEG_ZERO", -0.0),
                new Measure("NEG_ONE", -1.5));

        System.out.println("double order = " +
                values.stream()
                        .sorted(Comparator.comparingDouble(Measure::value))
                        .map(Measure::id)
                        .toList());

        System.out.println("compare zeros = " +
                Integer.signum(Double.compare(-0.0, +0.0)));
        System.out.println("zero == zero = " + (-0.0 == +0.0));
        System.out.println("NaN after infinity = " +
                (Double.compare(
                        Double.NaN, Double.POSITIVE_INFINITY) > 0));

        List<Measure> nullable = Arrays.asList(
                null,
                new Measure("TWO", 2.0),
                new Measure("ONE", 1.0));

        System.out.println("null elements last = " +
                nullable.stream()
                        .sorted(Comparator.nullsLast(
                                Comparator.comparingDouble(Measure::value)))
                        .map(x -> x == null ? "NULL" : x.id())
                        .toList());
    }
}
```

```bash
javac -encoding UTF-8 FloatingComparatorDemo.java
java FloatingComparatorDemo
```

```text
double order = [MINUS_INF, NEG_ONE, NEG_ZERO, PLUS_ZERO, PLUS_INF, NAN]
compare zeros = -1
zero == zero = true
NaN after infinity = true
null elements last = [ONE, TWO, NULL]
```

`Comparator.nullsLast(Comparator.comparingDouble(...))` xử lý trường hợp **đối tượng `Measure` là null**: đặt nó sau đối tượng không null và không gọi extractor trên null. Điều này **khác** trường hợp đối tượng không null nhưng trường số của nó là wrapper `Double` có giá trị null; xem mục 10.

## 8. Nối nhiều tiêu chí bằng `thenComparingInt`, `thenComparingLong`, `thenComparingDouble`

Một khóa duy nhất có thể trùng nhau. Thay vì viết nhiều `if/else` trong comparator, dùng các phương thức chain:

```java
Comparator<Player> byCriteria =
        Comparator.comparingInt(Player::wins)
                .thenComparingLong(Player::points)
                .thenComparingDouble(Player::accuracy);
```

Đây là thứ tự **từ điển (lexicographic)**:
1. So `wins` bằng `int`. Nếu khác, dừng và dùng kết quả đó.
2. Nếu `wins` bằng nhau, so `points` bằng `long`.
3. Nếu cả hai bằng nhau, so `accuracy` bằng `double`.
4. Nếu tất cả tiêu chí bằng nhau, comparator trả 0. Muốn thứ tự tổng quát có điểm phân biệt, nối thêm `thenComparing(Player::id)` khi ID có thể so sánh và duy nhất.

Extractor ở các tiêu chí sau **chỉ cần được gọi để phân xử hòa** ở các tiêu chí trước; không nên dựa vào số lần hoặc thứ tự callback làm side effect. Comparator được phép gọi extractor nhiều lần trong quá trình sắp xếp.

Ví dụ chiều:
- **Thứ tự tăng dần toàn bộ:** `comparingInt(...).thenComparingLong(...).thenComparingDouble(...)`.
- **Thắng nhiều đứng trước, điểm nhiều đứng trước, độ chính xác cao đứng trước:** mỗi tiêu chí cần được đảo **riêng** nếu thứ tự giảm dần.
- **Thắng nhiều đứng trước nhưng điểm ít đứng trước:** đảo `wins` rồi dùng `thenComparingLong` tăng dần cho `points`.

## 9. Bẫy quan trọng: `reversed()` đảo đúng phần nào?

Xét hai comparator:

```java
Comparator<Player> mixed =
        Comparator.comparingInt(Player::wins).reversed()
                .thenComparingLong(Player::points);

Comparator<Player> bothDescending =
        Comparator.comparingInt(Player::wins)
                .thenComparingLong(Player::points)
                .reversed();
```

`mixed` sắp `wins` **giảm dần**, khi hòa dùng `points` **tăng dần**. `bothDescending` đảo **toàn bộ comparator đã tạo trước đó**, nên `wins` và `points` đều **giảm dần**. Việc đặt `reversed()` sau `thenComparingLong` không chỉ đảo tiêu chí cuối.

Nếu muốn chiều giảm dần theo từng khóa và nối tiếp, truyền comparator đã đảo vào `thenComparing(Comparator)`:

```java
Comparator<Player> ranking =
        Comparator.comparingInt(Player::wins).reversed()
                .thenComparing(
                        Comparator.comparingLong(Player::points).reversed())
                .thenComparing(
                        Comparator.comparingDouble(Player::accuracy).reversed())
                .thenComparing(Player::id);
```

Cách này diễn đạt rõ: nhiều trận thắng hơn đứng trước; nếu bằng nhau, nhiều điểm hơn đứng trước; tiếp tục dùng độ chính xác cao hơn; cuối cùng ID tăng dần để giải quyết đồng hạng.

## 10. Ví dụ đầy đủ: chain, thứ tự tăng/giảm và tie-breaker

Tạo tệp `ComparatorChainDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorChainDemo {
    record Player(String id, int wins, long points, double accuracy) {}

    static List<String> ids(List<Player> players) {
        return players.stream().map(Player::id).toList();
    }

    public static void main(String[] args) {
        List<Player> players = List.of(
                new Player("A", 10, 100, 0.80),
                new Player("B", 10, 150, 0.75),
                new Player("C", 8, 200, 0.85),
                new Player("D", 10, 150, 0.95));

        Comparator<Player> ranking =
                Comparator.comparingInt(Player::wins).reversed()
                        .thenComparing(
                                Comparator.comparingLong(Player::points)
                                        .reversed())
                        .thenComparing(
                                Comparator.comparingDouble(Player::accuracy)
                                        .reversed())
                        .thenComparing(Player::id);

        System.out.println("ranking = " + ids(
                players.stream().sorted(ranking).toList()));

        Comparator<Player> mixed =
                Comparator.comparingInt(Player::wins).reversed()
                        .thenComparingLong(Player::points)
                        .thenComparing(Player::id);

        System.out.println("wins desc points asc = " + ids(
                players.stream().sorted(mixed).toList()));

        Comparator<Player> allReversed =
                Comparator.comparingInt(Player::wins)
                        .thenComparingLong(Player::points)
                        .reversed();

        System.out.println("reversed whole chain = " + ids(
                players.stream().sorted(allReversed).toList()));
    }
}
```

```bash
javac -encoding UTF-8 ComparatorChainDemo.java
java ComparatorChainDemo
```

```text
ranking = [D, B, A, C]
wins desc points asc = [A, B, D, C]
reversed whole chain = [B, D, A, C]
```

`ranking` xếp D trước B vì cùng `wins=10` và `points=150` nhưng `accuracy` của D là `0.95`, cao hơn `0.75` của B. C xếp cuối vì chỉ có `wins=8`. `mixed` xếp A trước vì `points=100` thấp nhất trong nhóm có 10 trận thắng; `allReversed` xếp B/D trước A vì `points=150` lớn hơn 100 trong cùng nhóm, và giữ thứ tự gặp B rồi D khi tất cả tiêu chí xếp hạng đã xét bằng nhau.

`reversed()` không tự bỏ tie. Khi comparator trả 0, ordered Stream sort giữ encounter order của các phần tử đó. Nếu muốn đầu ra ổn định **bất kể thứ tự nhập**, thêm tie-breaker ở cuối.

## 11. Kiểu số nguyên cực trị: `comparingInt` và `comparingLong` không overflow vì lấy hiệu

Khi sắp xếp khóa nguyên, so sánh tốt phải hoạt động đúng tại `MIN_VALUE`/`MAX_VALUE`. `Comparator.comparingInt` sử dụng cách so sánh số nguyên, không viết `a-b`; `comparingLong` tương tự cho `long`.

Ta cũng cần phân biệt:
- **Tràn phép tính trước khi extract:** nếu `keyExtractor` chứa `x -> x.a() * x.b()` trên `int` và nhân bị overflow, comparator không thể khôi phục khóa đúng. Phải tính biểu thức ở miền đủ rộng, ví dụ `comparingLong(x -> (long) x.a() * x.b())` nếu tích nằm trong `long`.
- **Mất chính xác do ép kiểu extractor:** nếu `long` bị ép sang `int` hoặc `double` trước khi so, thứ tự có thể không còn chính xác.
- **Comparator trả 0 cho khóa bằng nhau:** mặc định chỉ so khóa đó, không so các trường khác trừ khi có `thenComparing`.

Đoạn phản ví dụ sau minh họa tràn do lấy hiệu:

```java
Comparator<Item> bad =
        (a, b) -> a.count() - b.count();

Comparator<Item> good =
        Comparator.comparingInt(Item::count);
```

Với hai Item có `count` lần lượt là `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, `bad.compare(min, max)` cho dấu dương **sai**, còn `good.compare(min, max)` cho dấu âm đúng.

## 12. Null: phân biệt đối tượng null và khóa số wrapper null

Ba factory primitive có extractor trả `int`, `long`, `double`, vì vậy chúng **không mang theo trạng thái null ở kiểu kết quả**. Nhưng vẫn có hai nơi phát sinh null:

**Trường hợp A — phần tử toàn bộ là null.** Ví dụ danh sách `[null, product1, product2]`. Nếu dùng `Comparator.comparingInt(Product::stock)` đơn lẻ, việc truy cập `stock()` trên null sẽ ném `NullPointerException`. Nếu domain cho phép đối tượng null:

```java
Comparator<Product> byStockNullLast =
        Comparator.nullsLast(
                Comparator.comparingInt(Product::stock));
```

`nullsLast` đặt **đối tượng null** sau đối tượng không null; `nullsFirst` là chiều ngược lại. Nếu không cho phép null, tốt hơn là validate dữ liệu thay vì “xếp chỗ” cho các phần tử sai.

**Trường hợp B — đối tượng tồn tại nhưng trường số là `Integer`/`Long`/`Double` nullable.** Ví dụ `Item.nullableCount()` trả `Integer` và có thể null:

```java
Comparator<Item> unsafe =
        Comparator.comparingInt(item -> item.nullableCount());
// Tự unbox Integer null thành int -> NullPointerException.
```

`Comparator.nullsLast(unsafe)` **không giải quyết trường hợp B**, vì phần tử Item không null, chỉ khóa bên trong null. Để quyết định vị trí của khóa nullable, dùng generic `Comparator.comparing`:

```java
Comparator<Item> byNullableCount =
        Comparator.comparing(
                Item::nullableCount,
                Comparator.nullsFirst(Integer::compare));
```

Hoặc `Comparator.nullsLast(Comparator.naturalOrder())` để đặt khóa null ở cuối. Lúc này comparator so sánh giá trị wrapper có thể null theo policy rõ ràng. Nếu null có nghĩa dữ liệu không hợp lệ, có thể validate và báo lỗi sớm thay vì sắp xếp nó.

## 13. Ví dụ đầy đủ: overflow và hai loại null

Tạo tệp `ComparatorPitfallDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorPitfallDemo {
    record Item(String id, int count, long eventId,
                Integer nullableCount) {}

    public static void main(String[] args) {
        Item low = new Item(
                "MIN", Integer.MIN_VALUE, Long.MIN_VALUE, null);
        Item high = new Item(
                "MAX", Integer.MAX_VALUE, Long.MAX_VALUE, 1);

        Comparator<Item> bad =
                (a, b) -> a.count() - b.count();
        Comparator<Item> good =
                Comparator.comparingInt(Item::count);

        System.out.println("bad MIN vs MAX sign = "
                + Integer.signum(bad.compare(low, high)));
        System.out.println("good MIN vs MAX sign = "
                + Integer.signum(good.compare(low, high)));

        System.out.println("long MIN vs MAX sign = "
                + Integer.signum(
                        Comparator.comparingLong(Item::eventId)
                                .compare(low, high)));

        Comparator<Item> nullable =
                Comparator.comparing(
                        Item::nullableCount,
                        Comparator.nullsFirst(Integer::compare));

        System.out.println("nullable first = "
                + List.of(high, low).stream()
                        .sorted(nullable)
                        .map(Item::id)
                        .toList());

        try {
            Comparator<Item> unbox =
                    Comparator.comparingInt(x -> x.nullableCount());
            unbox.compare(low, high);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing = NullPointerException");
        }
    }
}
```

```bash
javac -encoding UTF-8 ComparatorPitfallDemo.java
java ComparatorPitfallDemo
```

```text
bad MIN vs MAX sign = 1
good MIN vs MAX sign = -1
long MIN vs MAX sign = -1
nullable first = [MIN, MAX]
null unboxing = NullPointerException
```

`Integer.signum` ở đây được dùng để **in dấu của kết quả** cho dễ đọc, không phải để thay Comparator. `bad` đã cho dấu sai. `comparingInt`/`comparingLong` đúng tại các giá trị biên. `nullable first` xếp Item có `nullableCount=null` trước nhờ `Comparator.nullsFirst` dùng trên **khóa**, còn `comparingInt` sẽ ném NPE khi Java tự unbox null wrapper.

## 14. Comparator cho TreeSet/TreeMap: vì sao tie-breaker có thể là yêu cầu dữ liệu?

Comparator không chỉ dùng để in danh sách đã sắp xếp. `TreeSet` và `TreeMap` dựa vào quan hệ `compare(a,b) == 0` để quyết định **hai khóa/phần tử tương đương theo thứ tự**, kể cả khi `equals` của đối tượng nói chúng khác nhau. Vì vậy, nếu chỉ so `age`, hai `Person` khác tên cùng tuổi có thể bị xem là một phần tử trong `TreeSet`.

```java
record Person(String name, int age) {}

Set<Person> byAge = new TreeSet<>(
        Comparator.comparingInt(Person::age));
byAge.add(new Person("An", 30));
byAge.add(new Person("Binh", 30));
// byAge.size() == 1, không phải 2.
```

Ví dụ minh họa trong phương thức đã import `Set`/`TreeSet`/`Comparator`. Nếu domain muốn phân biệt hai người, thêm tie-breaker mang tính định danh:

```java
Set<Person> byAgeThenName = new TreeSet<>(
        Comparator.comparingInt(Person::age)
                  .thenComparing(Person::name));
```

Điều này không có nghĩa phải luôn thêm `id`; comparator phải phản ánh **ngữ nghĩa equality của bộ sưu tập có thứ tự**. Nếu hai người có thể trùng tuổi và tên, cần khóa định danh khác. Với `List.sort`, comparator trả 0 thường chỉ nghĩa là hai phần tử có cùng vị trí xếp hạng theo khóa, **không làm List tự mất phần tử**.

Các collection có thứ tự theo comparator có thể hoạt động khác với quy tắc `equals` nếu comparator không nhất quán với equals. Hãy cân nhắc hợp đồng của `SortedSet`/`SortedMap` khi dùng các factory Comparator làm tiêu chí khóa.

### Khóa mutable cũng là rủi ro

Không nên thay đổi `age`/`views` hay trường dùng cho comparator **sau khi đã thêm đối tượng vào `TreeSet`/`TreeMap`**, vì vị trí sắp xếp đã được xác lập theo giá trị cũ và thao tác tìm kiếm có thể sai. Ưu tiên khóa bất biến, hoặc xóa rồi thêm lại với khóa mới theo cơ chế phù hợp.

## 15. Ví dụ đầy đủ: long chính xác, double làm tròn và TreeSet

Tạo tệp `ComparatorMoreCases.java`:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorMoreCases {
    record Point(String id, long n) {}
    record Player(String id, int wins, long points, double accuracy) {}
    record Person(String name, int age) {}

    public static void main(String[] args) {
        List<Point> points = List.of(
                new Point("BIG", 9_007_199_254_740_993L),
                new Point("SMALL", 9_007_199_254_740_992L));

        System.out.println("precise long order = " +
                points.stream()
                        .sorted(Comparator.comparingLong(Point::n))
                        .map(Point::id)
                        .toList());

        System.out.println("double rounded order = " +
                points.stream()
                        .sorted(Comparator.comparingDouble(p -> p.n()))
                        .map(Point::id)
                        .toList());

        Comparator<Point> idTie =
                Comparator.comparingDouble((Point p) -> p.n())
                        .thenComparing(Point::id);

        System.out.println("double then id order = " +
                points.stream()
                        .sorted(idTie)
                        .map(Point::id)
                        .toList());

        List<Player> players = List.of(
                new Player("A", 10, 100, 0.80),
                new Player("B", 10, 150, 0.75),
                new Player("C", 8, 200, 0.85),
                new Player("D", 10, 150, 0.95));

        Comparator<Player> allAscending =
                Comparator.comparingInt(Player::wins)
                        .thenComparingLong(Player::points)
                        .thenComparingDouble(Player::accuracy);

        System.out.println("all ascending = " +
                players.stream()
                        .sorted(allAscending)
                        .map(Player::id)
                        .toList());

        Set<Person> badSet =
                new TreeSet<>(Comparator.comparingInt(Person::age));
        badSet.add(new Person("An", 30));
        badSet.add(new Person("Binh", 30));

        System.out.println("age only set size = " + badSet.size());

        Set<Person> goodSet =
                new TreeSet<>(Comparator.comparingInt(Person::age)
                        .thenComparing(Person::name));
        goodSet.add(new Person("An", 30));
        goodSet.add(new Person("Binh", 30));

        System.out.println("age plus name set size = " + goodSet.size());
    }
}
```

```bash
javac -encoding UTF-8 ComparatorMoreCases.java
java ComparatorMoreCases
```

```text
precise long order = [SMALL, BIG]
double rounded order = [BIG, SMALL]
double then id order = [BIG, SMALL]
all ascending = [C, A, B, D]
age only set size = 1
age plus name set size = 2
```

**Tại sao `double rounded order` vẫn in BIG trước SMALL?** Dữ liệu đầu vào có BIG trước SMALL. Khi `long` được chuyển thành `double`, hai giá trị khác nhau đều tròn về `2^53`, nên comparator thấy **hai khóa bằng nhau**; `Stream.sorted` giữ thứ tự nguồn vì Stream ordered. Đó **không** phải thứ tự số nguyên đúng. `thenComparing(Point::id)` có thể tạo thứ tự ổn định theo ID, nhưng **không sửa được sự mất chính xác của khóa long đầu tiên**. Nếu ý định là sắp tăng theo `n`, hãy dùng `comparingLong(Point::n)`.

`all ascending` minh họa trực tiếp các phương thức `thenComparingLong` và `thenComparingDouble`. Ví dụ TreeSet cho thấy comparator chỉ theo tuổi xem hai Person bằng tuổi là tương đương, còn thêm tên phân biệt được hai phần tử.

## 16. Sắp xếp List, Stream và các collection có thứ tự

### `List.sort`: sửa danh sách có thể sửa

```java
List<Product> copy = new ArrayList<>(products);

copy.sort(Comparator.comparingInt(Product::stock)
        .thenComparing(Product::sku));
```

Đoạn minh họa giả định `Product` và `products` từ mục 3, đã import `ArrayList`/`List`/`Comparator`. `List.sort` sắp ngay trên `copy`, không trả một List mới. `List.of(...)` là unmodifiable nên phải tạo bản sao trước khi sort.

### `Stream.sorted`: trả Stream đã được sắp xếp

```java
List<Product> sorted = products.stream()
        .sorted(Comparator.comparingLong(Product::views)
                .thenComparing(Product::sku))
        .toList();
```

`Stream.sorted` là intermediate operation, chỉ chạy khi có terminal như `toList`. Danh sách nguồn `products` không bị thay đổi. `Stream.toList` có từ Java 16; nếu dùng Java 8, có thể thay bằng `collect(Collectors.toList())` (với hợp đồng loại danh sách khác).

### `TreeSet`/`TreeMap`: comparator quyết định logic khóa

```java
Set<Person> people = new TreeSet<>(
        Comparator.comparingInt(Person::age)
                .thenComparing(Person::name));
```

Comparator còn quyết định việc một phần tử được xem là trùng trong SortedSet. `TreeMap` tương tự ở **khóa**. Nếu comparator quá ít tiêu chí, nhiều đối tượng khác nhau có thể được đối xử như một khóa.

### Sắp xếp ổn định và dữ liệu song song

`Stream.sorted` ổn định cho ordered streams; không có cam kết ổn định với unordered streams. Một parallel ordered stream vẫn có thể tạo kết quả đúng thứ tự so sánh, nhưng hiệu quả của sort song song phụ thuộc dữ liệu và runtime. Đừng tạo side effect trong extractor để “ghi nhận thứ tự so sánh”: sorter được quyền gọi comparator theo lịch khác nhau, nhiều lần trên mỗi phần tử.

## 17. Nguyên tắc viết extractor và comparator đúng

1. **Pure/stateless:** extractor nên chỉ đọc khóa cần so, không thay dữ liệu hay ghi log/đếm làm nhiệm vụ nghiệp vụ. Sort có thể gọi comparator nhiều lần và không cố định thứ tự gọi.
2. **Consistent:** với cùng object không đổi, extractor trả cùng khóa. Trường dùng để so nên ổn định trong suốt thời gian sort hoặc tồn tại trong cấu trúc cây.
3. **Không làm tính toán tràn số trước khi so:** `comparingInt(x -> x.amount() * x.quantity())` vẫn có thể sai nếu tích overflow; `comparingLong(x -> (long) x.amount() * x.quantity())` tránh overflow `int` khi tích còn nằm trong `long`.
4. **Không ép kiểu nguy hiểm:** đổi `long` sang `double` có thể mất chính xác; đổi `long` sang `int` cắt miền giá trị.
5. **Xử lý null rõ:** `nullsFirst/nullsLast` bên ngoài chỉ xử lý **phần tử null**; nullable field cần comparator cho **khóa nullable**, không gọi primitive extractor rồi chờ nó tự xử lý.
6. **Chọn chiều theo từng tiêu chí:** `reversed` ở cuối đảo cả chain; nếu chỉ đảo khóa đầu, gọi `reversed` trước `thenComparing`; để đảo khóa sau, truyền comparator con đã đảo.
7. **Thêm tie-breaker khi cần:** khóa numeric trùng nhau có thể phù hợp cho ranking; nhưng SortedSet/SortedMap hoặc kết quả ổn định giữa các nguồn có thể đòi khóa phân biệt như `id`.
8. **Tránh so số tiền bằng double khi cần chính xác:** so `long` đơn vị nhỏ nhất hoặc dùng `Comparator.comparing(Invoice::amount)` nếu `amount` là `BigDecimal`.
9. **Không đặt truy vấn database trong extractor:** comparator có thể gọi extractor lặp lại; nên nạp/chuẩn hóa khóa trước, không đưa I/O hay việc nặng vào mỗi lần so.
10. **Kiểm thử dữ liệu biên:** MIN/MAX, số âm, 0, duplicate keys, missing/null fields, NaN, ±Infinity, -0.0, long quanh `2^53`.

## 18. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `(a,b) -> a.age() - b.age()` | Overflow làm sai dấu | `comparingInt` hoặc `Integer.compare` |
| `(a,b) -> (int)(a.id()-b.id())` với khóa long | Mất phần high bits/overflow | `comparingLong` hoặc `Long.compare` |
| `comparingDouble(x -> x.longId())` | Hai ID lớn có thể bị làm tròn thành cùng khóa | `comparingLong` |
| `(int)(a.score()-b.score())` | Hai score khác nhau có thể bị xem bằng nhau, NaN/∞ không đúng | `comparingDouble`/`Double.compare` |
| `comparingInt(x -> x.nullableAge())` | Unboxing nullable Integer gây NPE | `comparing` generic + null policy |
| `nullsLast(comparingInt(...))` khi khóa nullable | Chỉ xử lý object null, không xử lý field null | `comparing(extractor, nullsLast(...))` |
| `thenComparing(...).reversed()` khi chỉ muốn đảo khóa phụ | Đảo cả comparator đã nối | Đảo comparator con trước khi nối |
| Comparator chỉ so tuổi trong `TreeSet` | Hai người cùng tuổi bị coi trùng | Thêm khóa định danh khi cần |
| Extractor thay đổi state khi sort | Kết quả không nhất quán, khó debug | Extractor thuần, dữ liệu ổn định |
| `List.of(...).sort(...)` | `UnsupportedOperationException` | Copy sang mutable List hoặc dùng Stream.sorted |
| Dùng `NaN` như “điểm cao nhất” mặc định | Xếp hạng sai nghiệp vụ | Validate/chuẩn hóa/sắp theo policy domain |
| Mong `sorted` gọi extractor đúng một lần mỗi item | Side effect hoặc I/O bị gọi nhiều lần | Cache khóa khi cần, tránh side effect |

Không có một comparator “đúng” cho mọi hệ thống; nó phải nhất quán với **kiểu dữ liệu và ý nghĩa nghiệp vụ của thứ tự**.

## 19. Bài tập tự kiểm tra

**Câu 1.** `age()` trả `int`, nên dùng factory nào?  
**Đáp án:** `Comparator.comparingInt(Person::age)`. Nó đọc khóa int và so sánh theo thứ tự nguyên đúng.

**Câu 2.** `eventId()` trả `long` và có thể vượt `2^53`. Dùng `comparingDouble` được không?  
**Đáp án:** Không nếu cần thứ tự nguyên chính xác. `long → double` có thể làm tròn; dùng `comparingLong(Event::eventId)`.

**Câu 3.** `rating()` trả `double`. `NaN` đứng ở đâu khi dùng `comparingDouble` tăng dần?  
**Đáp án:** Sau mọi giá trị double khác, kể cả `+Infinity`, theo `Double.compare`. Nên có chính sách xử lý NaN nếu domain không coi nó là điểm hợp lệ.

**Câu 4.** `-0.0` và `+0.0` có đồng hạng trong `comparingDouble` không?  
**Đáp án:** Không; `Double.compare(-0.0, +0.0) < 0` dù toán tử `-0.0 == +0.0` trả true.

**Câu 5.** Muốn `wins` giảm dần nhưng `points` tăng dần thì viết thế nào?  
**Đáp án:** `Comparator.comparingInt(Player::wins).reversed().thenComparingLong(Player::points)`.

**Câu 6.** Nếu gọi `comparingInt(...).thenComparingLong(...).reversed()` thì điều gì bị đảo?  
**Đáp án:** Cả chuỗi so sánh đã nối, không chỉ khóa `long`.

**Câu 7.** `Integer age` có thể null; dùng `comparingInt(Person::age)` được không?  
**Đáp án:** Có thể biên dịch nhờ unboxing nhưng sẽ ném NPE khi so một phần tử có age null. Dùng `Comparator.comparing(Person::age, Comparator.nullsLast(Integer::compare))` hoặc validate dữ liệu.

**Câu 8.** Vì sao `TreeSet<>(comparingInt(Person::age))` có thể giữ một người dù thêm hai người khác nhau cùng tuổi?  
**Đáp án:** Vì TreeSet coi `compare(a,b)==0` là tương đương theo thứ tự. Thêm tie-breaker định danh để phân biệt nếu cần.

**Câu 9.** `stream.sorted(comparator)` có sửa List gốc không?  
**Đáp án:** Không. Đây là pipeline tạo kết quả sắp xếp; `List.sort(comparator)` mới sắp trên danh sách được gọi, nếu danh sách sửa được.

**Câu 10.** Comparator có nên gọi HTTP hoặc thay dữ liệu mỗi lần extract khóa?  
**Đáp án:** Không nên. Sort có thể gọi extractor nhiều lần theo lịch không dự đoán trước; nên dùng khóa ổn định, thuần và không gây side effect.

## 20. Ghi nhớ

- **`comparingInt` / `comparingLong` / `comparingDouble`** tạo comparator theo khóa primitive `int` / `long` / `double`, mặc định tăng dần.
- Chúng **tránh lỗi comparator dùng phép trừ** khi so số nguyên cực trị; nhưng phép tính **bên trong extractor** vẫn phải đúng miền giá trị.
- `comparingLong` giữ thứ tự nguyên chính xác. `comparingDouble` có semantics của `Double.compare`, bao gồm NaN, vô cực, signed zero.
- `thenComparingInt`, `thenComparingLong`, `thenComparingDouble` nối các tiêu chí để phân xử hòa. **Vị trí `reversed()` quyết định phần nào của chain bị đảo**.
- `nullsFirst/nullsLast` phải được đặt đúng lớp: bọc comparator cho **object null**; dùng comparator generic cho **key wrapper null**.
- Comparator trả 0 có ý nghĩa đặc biệt trong `TreeSet`/`TreeMap`: có thể coi hai đối tượng khác nhau là cùng một key.
- Chọn API theo **kiểu số, ngữ nghĩa thứ tự, dữ liệu biên và hợp đồng của collection**, không chọn chỉ vì mã ngắn.

### Tài liệu Java API chính thức còn áp dụng

- [`Comparator` — `comparingInt`, `comparingLong`, `comparingDouble`, `thenComparingInt/Long/Double`, `reversed`, `nullsFirst/Last`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html)
- [`ToIntFunction`, `ToLongFunction` và `ToDoubleFunction`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html) — primitive key extractor interfaces.
- [`Double` — `compare`, NaN và signed zero](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html)
- [`Stream` — `sorted(Comparator)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html) và [`List` — `sort(Comparator)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html)
- [`TreeSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html) và [`TreeMap`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html) — ngữ nghĩa tương đương khóa theo comparator.
