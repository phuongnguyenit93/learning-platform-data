# Dùng phép trừ trong Comparator có thể tràn số trong Java

## 1. Lỗi thường gặp: dùng hiệu số làm kết quả so sánh

Một Comparator số nguyên thường được viết rất ngắn:

```java
Comparator<Integer> bad = (a, b) -> a - b;
```

Cách viết này có vẻ hợp lý: nếu a nhỏ hơn b, hiệu âm; nếu bằng nhau, hiệu bằng 0; nếu lớn hơn, hiệu dương. Nhưng phép trừ trên kiểu `int` và `long` có thể **overflow**. Khi hiệu toán học không biểu diễn được trong kiểu dữ liệu, dấu của kết quả Java có thể sai, khiến Comparator mô tả một quan hệ thứ tự mâu thuẫn.

Ví dụ:

```java
int min = Integer.MIN_VALUE; // -2147483648
int zero = 0;

System.out.println(min - zero); // -2147483648
System.out.println(zero - min); // -2147483648, đã overflow
```

Theo toán học, `0 - (-2147483648) = 2147483648` là số dương. Nhưng `Integer.MAX_VALUE` chỉ bằng `2147483647`. Trong phép trừ `int`, giá trị này trở thành `-2147483648`. Comparator sai sẽ cho rằng `min < zero` **và đồng thời** `zero < min`.

Giải pháp đúng:

```java
Comparator<Integer> good = Integer::compare;
```

Hoặc:

```java
Comparator<Integer> good = (a, b) -> Integer.compare(a, b);
```

`Integer.compare` so sánh số nguyên có dấu mà không tính hiệu có thể tràn. Với `long`, dùng `Long.compare`. Với thuộc tính của một đối tượng, ưu tiên `Comparator.comparingInt` hoặc `Comparator.comparingLong`.

**Ghi nhớ:** `Comparator.compare` chỉ yêu cầu số **âm, 0 hoặc dương** để biểu diễn thứ tự, không yêu cầu một giá trị đúng bằng khoảng cách giữa hai số.

## 2. Hợp đồng Comparator cần tuân thủ

`java.util.Comparator<T>` là functional interface có phương thức:

```java
int compare(T left, T right);
```

| Kết quả | Ý nghĩa |
| --- | --- |
| `< 0` | `left` đứng trước `right` |
| `== 0` | Hai đối tượng ngang nhau **theo quan hệ thứ tự của Comparator** |
| `> 0` | `left` đứng sau `right` |

Kết quả không nhất thiết là -1, 0 hoặc 1: bất kỳ số âm hay dương đều có thể hợp lệ nếu tuân thủ quy tắc. Vì thế phép trừ số học vốn không cần thiết.

Ba tính chất nền tảng:

1. **Phản đối xứng theo dấu:** `sgn(compare(a,b)) == -sgn(compare(b,a))`. Nếu a đứng trước b thì b phải đứng sau a.
2. **Bắc cầu:** nếu `compare(a,b) > 0` và `compare(b,c) > 0`, thì `compare(a,c) > 0`; tương tự với chiều âm.
3. **Tính nhất quán của phần tử ngang thứ tự:** khi `compare(a,b) == 0`, dấu của `compare(a,z)` và `compare(b,z)` phải trùng nhau với mọi z.

Comparator sai bởi overflow có thể vi phạm ngay tính chất thứ nhất: cả hai chiều so sánh đều âm. Những lần sort chạy thành công trên số nhỏ **không chứng minh** Comparator đúng cho mọi giá trị.

Một khái niệm liên quan nhưng khác là **nhất quán với equals**. Comparator hợp lệ vẫn có thể cho `compare(a,b) == 0` khi `!a.equals(b)`; đây là vấn đề thiết kế danh tính trong sorted collection. Nếu muốn `TreeSet` và `TreeMap` tuân thủ hoàn toàn ý nghĩa chung của `Set`/`Map` dựa trên `equals`, thứ tự cần nhất quán với `equals`.

## 3. Vì sao phép trừ bị tràn trước khi trả về?

Java `int` có miền từ `-2147483648` đến `2147483647`. Phép trừ `int` thông thường không tự ném lỗi khi vượt miền; giá trị wraparound theo số học 32-bit. Ví dụ:

```text
min = -2147483648
zero = 0

min - zero:
  -2147483648 → hợp lệ trong int → dấu âm

zero - min:
  +2147483648 → vượt Integer.MAX_VALUE
  kết quả trong int = -2147483648 → dấu âm SAI
```

Với các số nhỏ như 3 và 5, `a-b` dường như luôn đúng vì hiệu chưa vượt miền. Lỗi thường chỉ lộ khi so sánh số âm với số dương lớn, hoặc giá trị gần `Integer.MIN_VALUE`/`Integer.MAX_VALUE`.

`long` cũng có giới hạn: miền từ `Long.MIN_VALUE` đến `Long.MAX_VALUE`. Hiệu của hai giá trị `long` có thể cần nhiều hơn 64 bit có dấu, nên `(a,b) -> a-b` **vẫn nguy hiểm với long**.

Có một hiểu nhầm đáng tránh:

```java
long result = intA - intB; // phép trừ int có thể đã tràn
```

Dù biến nhận là `long`, phép trừ vẫn diễn ra bằng `int` khi hai toán hạng là `int`. Việc gán sang `long` không phục hồi giá trị đã mất. Trong trường hợp chỉ cần tính **hiệu chính xác của hai int**, `(long) intA - intB` có thể an toàn; nhưng một Comparator không cần hiệu, nên dùng `Integer.compare`.

## 4. Ví dụ hoàn chỉnh Java 17+: lỗi phản đối xứng, sort và TreeSet

Lưu `ComparatorOverflowDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class ComparatorOverflowDemo {
    public static void main(String[] args) {
        int min = Integer.MIN_VALUE;
        int zero = 0;

        Comparator<Integer> bad = (a, b) -> a - b;
        Comparator<Integer> good = Integer::compare;

        System.out.println("bad(min, zero): " + bad.compare(min, zero));
        System.out.println("bad(zero, min): " + bad.compare(zero, min));
        System.out.println("good(min, zero): " + good.compare(min, zero));
        System.out.println("good(zero, min): " + good.compare(zero, min));

        List<Integer> badSorted = new ArrayList<>(List.of(min, zero));
        badSorted.sort(bad);
        System.out.println("bad sorted: " + badSorted);

        List<Integer> goodSorted = new ArrayList<>(List.of(min, zero));
        goodSorted.sort(good);
        System.out.println("good sorted: " + goodSorted);

        TreeSet<Integer> badSet = new TreeSet<>(bad);
        badSet.add(min);
        badSet.add(zero);
        System.out.println("bad TreeSet first: " + badSet.first());

        TreeSet<Integer> goodSet = new TreeSet<>(good);
        goodSet.add(min);
        goodSet.add(zero);
        System.out.println("good TreeSet first: " + goodSet.first());
    }
}
```

Biên dịch và chạy:

```bash
javac ComparatorOverflowDemo.java
java ComparatorOverflowDemo
```

Stdout đã đối chiếu với Java 17+:

```text
bad(min, zero): -2147483648
bad(zero, min): -2147483648
good(min, zero): -1
good(zero, min): 1
bad sorted: [0, -2147483648]
good sorted: [-2147483648, 0]
bad TreeSet first: 0
good TreeSet first: -2147483648
```

Kết quả chứng minh:

- Comparator lỗi trả dấu âm ở **cả hai chiều** giữa `Integer.MIN_VALUE` và 0.
- `List.sort` với hai phần tử có thể trả thứ tự sai mà không ném ngoại lệ.
- `TreeSet` dùng Comparator sai cho `first() == 0`, trái với thứ tự số nguyên mong đợi.
- Comparator dùng `Integer.compare` cho kết quả đúng.

Trong những trường hợp khác, thuật toán sort có thể ném `IllegalArgumentException` kèm thông điệp như `Comparison method violates its general contract!`. Nhưng ngoại lệ đó **không phải bảo đảm sẽ xuất hiện cho mọi Comparator sai**. Thứ tự kết quả sai một cách im lặng còn nguy hiểm hơn.

## 5. Cách viết an toàn theo kiểu dữ liệu

### int/Integer

```java
Comparator<Integer> natural = Integer::compare;
Comparator<Integer> alsoNatural = Comparator.naturalOrder();
```

Với thuộc tính `int age()` của object:

```java
Comparator<Employee> byAge = Comparator.comparingInt(Employee::age);
```

`Employee` là kiểu minh họa do chương trình tự định nghĩa, chẳng hạn `record Employee(String name, int age) {}`; đoạn này chưa phải chương trình độc lập.

### long/Long

```java
Comparator<Long> byLong = Long::compare;
Comparator<Order> byAmount = Comparator.comparingLong(Order::amountCents);
```

`Order` là kiểu minh họa có phương thức `long amountCents()`. Cả hai cách dùng tránh phép trừ `long` có thể overflow.

**Không dùng** `(int)(aLong-bLong)`: có thể overflow ở phép trừ, rồi tiếp tục mất bit khi ép hiệu `long` về `int`. Hai số khác nhau có thể bị xem ngang thứ tự do hiệu sau cast thành 0.

### double/Double

```java
Comparator<Double> byDouble = Double::compare;
Comparator<Measurement> byMeasure =
        Comparator.comparingDouble(Measurement::value);
```

`Measurement` là kiểu minh họa có phương thức `double value()`. Không dùng `(int)(a-b)` với số thực: hiệu nhỏ hơn 1 về trị tuyệt đối sẽ thành 0 khi cast `int`, dù hai số khác nhau. Ngoài ra còn có NaN, vô cực và signed zero.

`Double.compare` có quy tắc cho các giá trị đó, chẳng hạn `Double.compare(-0.0,+0.0)<0` và NaN được xếp theo thứ tự wrapper. Hãy dùng API chuẩn thay vì tự xét dấu hiệu trừ.

### BigInteger/BigDecimal

```java
Comparator<java.math.BigInteger> integerOrder =
        java.math.BigInteger::compareTo;
Comparator<java.math.BigDecimal> decimalOrder =
        java.math.BigDecimal::compareTo;
```

Không tính `a.subtract(b).intValue()` cho `BigDecimal`: phép đổi sang `int` có thể cắt giá trị hoặc bỏ phần thập phân. `BigDecimal.compareTo` so theo giá trị số; lưu ý `2.0` và `2.00` ngang thứ tự dù `equals` có xét scale.

### Số unsigned

Nếu `int`/`long` đang lưu bit pattern của số không dấu, dùng `Integer.compareUnsigned` hoặc `Long.compareUnsigned`. Đó là thứ tự **khác** signed: `-1` trong unsigned 32-bit tương ứng giá trị lớn nhất. Chỉ dùng khi domain yêu cầu, không dùng unsigned như mẹo “chống overflow”.

## 6. Sắp xếp theo nhiều trường bằng thenComparing

Khi sort các đối tượng có nhiều tiêu chí, tránh viết biểu thức thủ công kiểu:

```java
// Sai: có thể overflow ngay tại phép trừ đầu.
return a.score() - b.score();
```

Nếu khóa chính bằng nhau, có thể so thêm khóa phụ; không nên cộng các hiệu hay cố gộp thành một giá trị `int`. Sử dụng:

- `Comparator.comparingInt` / `comparingLong` / `comparingDouble` để lấy khóa primitive.
- `thenComparingInt` / `thenComparingLong` / `thenComparingDouble` cho khóa phụ.
- `thenComparing` để so thêm String, Comparable hoặc một comparator khác.

Ví dụ đầy đủ lưu `ComparatorFieldsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorFieldsDemo {
    record Item(String id, long cents, int priority) {}

    public static void main(String[] args) {
        List<Item> items = new ArrayList<>(List.of(
                new Item("C", 250L, 2),
                new Item("B", -10L, 4),
                new Item("A", 250L, 1),
                new Item("D", 250L, 1)));

        Comparator<Item> order = Comparator
                .comparingLong(Item::cents)
                .thenComparingInt(Item::priority)
                .thenComparing(Item::id);
        items.sort(order);
        System.out.println("ordered ids: "
                + items.stream().map(Item::id).toList());

        long min = Long.MIN_VALUE;
        System.out.println("bad long (min - 0): " + (min - 0L));
        System.out.println("bad long (0 - min): " + (0L - min));
        System.out.println("safe long order: " + Long.compare(min, 0L));
        System.out.println("reverse cents first: "
                + items.stream().sorted(order.reversed())
                        .map(Item::id).findFirst().orElseThrow());

        int bits = -1;
        System.out.println("signed -1 vs 1: " + Integer.compare(bits, 1));
        System.out.println("unsigned -1 vs 1: " + Integer.compareUnsigned(bits, 1));
    }
}
```

Chạy:

```bash
javac ComparatorFieldsDemo.java
java ComparatorFieldsDemo
```

Stdout đã kiểm chứng:

```text
ordered ids: [B, A, D, C]
bad long (min - 0): -9223372036854775808
bad long (0 - min): -9223372036854775808
safe long order: -1
reverse cents first: C
signed -1 vs 1: -1
unsigned -1 vs 1: 1
```

Các khóa được áp dụng lần lượt: `cents` tăng dần, rồi `priority` tăng dần, rồi `id` theo thứ tự String. `Long.MIN_VALUE` và 0 tạo lỗi overflow tương tự trường hợp `int`. Hai dòng signed/unsigned cho thấy việc chọn thứ tự phải dựa vào ý nghĩa miền dữ liệu.

## 7. Đảo chiều sắp xếp đúng cách

Đổi `a-b` thành `b-a` chỉ đảo một phép trừ có thể tràn thành phép trừ có thể tràn khác. Dùng:

```java
Comparator<Integer> descending =
        (a, b) -> Integer.compare(b, a);
```

Hoặc:

```java
Comparator<Integer> descending = Comparator.reverseOrder();
```

Với Comparator đã có, sử dụng `reversed()`:

```java
Comparator<Item> allKeysReversed = order.reversed();
```

Đoạn này giả sử `Item` và `order` đã được khai báo trong chương trình phần trước. `order.reversed()` đảo **toàn bộ thứ tự**, bao gồm các khóa phụ. Nếu muốn khóa chính giảm nhưng khóa phụ vẫn tăng, xây dựng lại cụ thể:

```java
Comparator<Item> centsDescendingPriorityAscending =
        Comparator.<Item>comparingLong(Item::cents)
                .reversed()
                .thenComparingInt(Item::priority);
```

**Đừng mặc định đảo Comparator tổng quát bằng `-compare(a,b)`.** Một Comparator hợp lệ được phép trả bất kỳ số âm, bao gồm `Integer.MIN_VALUE`. Phủ định `Integer.MIN_VALUE` ở kiểu `int` vẫn trả giá trị âm đó vì overflow; `Comparator.reversed()` an toàn hơn và thể hiện đúng ý định.

## 8. Những mẹo cast thường không khắc phục được vấn đề

### 8.1. Tính hiệu bằng long rồi ép về int

```java
Comparator<Integer> bad = (a, b) -> (int) ((long) a - b);
```

Phép trừ của hai số `int` được mở rộng sang `long` nên hiệu không tràn `long`; nhưng cast cuối về `int` có thể làm sai dấu. Ví dụ hiệu `0 - Integer.MIN_VALUE` là `2147483648L`, cast về `int` thành số âm.

Với hai giá trị `long`, ngay cả `long diff = a-b` cũng có thể overflow, nên không có một kiểu nguyên primitive có dấu rộng hơn `long` để luôn chứa mọi hiệu. Dùng `Long.compare`.

### 8.2. Dùng Math.subtractExact trong Comparator

`Math.subtractExact(a,b)` ném `ArithmeticException` khi hiệu tràn. Nó hữu ích nếu thật sự cần hiệu nguyên chính xác. Nhưng **so sánh không cần hiệu**: việc ném lỗi khi hai khóa hợp lệ có thể so thứ tự bằng `Integer.compare` làm tăng rủi ro mà không mang lại lợi ích.

### 8.3. Lấy Math.signum của hiệu đã tràn

`Math.signum` áp dụng cho `float`/`double`; `Integer.signum` và `Long.signum` áp dụng cho nguyên. Nếu hiệu nguyên **đã tràn**, lấy dấu của hiệu vẫn sai. Có thể lấy `Integer.signum(Integer.compare(a,b))`, nhưng lúc đó hàm `signum` là thừa vì `Integer.compare` đã trả dấu đúng.

### 8.4. So sánh bằng phép trừ số thực

`Double.compare(a-b,0.0)` cũng không phải thay thế tổng quát cho `Double.compare(a,b)`: hiệu có thể tràn thành vô cực, bị mất precision, trở thành signed zero hoặc NaN. So sánh trực tiếp cho biết thứ tự theo quy tắc API; tính hiệu là một bài toán khác.

## 9. Hệ quả thực tế trong collection và thuật toán

Comparator không chỉ quyết định thứ tự của một danh sách:

| API | Rủi ro khi Comparator sai |
| --- | --- |
| `List.sort` / `Collections.sort` | Có thể cho danh sách sai thứ tự hoặc ném lỗi do vi phạm hợp đồng |
| `Arrays.sort` với Comparator | Sort có thể sai hoặc không ổn định trước các quan hệ mâu thuẫn |
| `Stream.sorted` | Dữ liệu đi tiếp theo thứ tự không phù hợp |
| `TreeSet` | `first`, `last`, `add`, `contains` và tính duy nhất bị ảnh hưởng |
| `TreeMap` | Tra cứu key, các phép điều hướng/range và cập nhật có thể sai |
| `PriorityQueue` | Phần tử được lấy ra không phải độ ưu tiên đúng theo nghiệp vụ |

Đối với `TreeSet` và `TreeMap`, `compare(a,b)==0` quyết định hai phần tử hoặc hai key tương đương về thứ tự. Một comparator kiểu `(int)(aLong-bLong)` có thể biến hai số khác nhau thành kết quả 0 nếu hiệu bị cắt bit, dẫn tới dữ liệu bị xem trùng trong `TreeSet` hoặc `put` ghi đè entry trong `TreeMap`. Điều này nguy hiểm hơn một kết quả sort sai hiển nhiên.

Ví dụ với Comparator sai (đặt trong một phương thức):

```java
TreeSet<Integer> values = new TreeSet<>((a, b) -> a - b);
values.add(Integer.MIN_VALUE);
values.add(0);

System.out.println(values.first()); // 0, thứ tự sai
```

Trong bài này, ví dụ đầy đủ ở mục 4 kiểm chứng hành vi đó. Sau khi sửa comparator, nếu collection đã được xây dựng với quan hệ thứ tự sai, có thể cần **xây dựng lại collection/index**; đừng giả định mọi cấu trúc đã bị sắp sai sẽ tự phục hồi.

## 10. Kiểm tra hợp đồng bằng các giá trị biên

Bộ test chỉ có 1, 2, 3 thường không phát hiện tràn số. Với `int`, nên kiểm tra các giá trị:

```text
Integer.MIN_VALUE
Integer.MIN_VALUE + 1
-1
0
1
Integer.MAX_VALUE - 1
Integer.MAX_VALUE
```

Với mỗi cặp a,b, kiểm tra tính phản đối xứng theo dấu:

```java
int ab = Integer.signum(comparator.compare(a, b));
int ba = Integer.signum(comparator.compare(b, a));
if (ab != -ba) {
    throw new AssertionError("Comparator violates antisymmetry");
}
```

Đây là đoạn minh họa trong phương thức với biến `comparator`, a và b đã định nghĩa. **Lấy dấu trước khi phủ định** sẽ tránh overflow của `-Integer.MIN_VALUE` nếu một Comparator trả về giá trị đó.

Có thể kiểm tra tính bắc cầu cho các bộ ba giá trị, kiểm tra quy tắc tie-breaker với các khóa bằng nhau, và so sánh với `Integer.compare(a,b)` nếu ý định là thứ tự số nguyên tăng dần.

Chương trình độc lập `ComparatorContractCheck.java`:

```java
import java.util.Comparator;

public class ComparatorContractCheck {
    static boolean antisymmetric(Comparator<Integer> comparator,
                                 int[] values) {
        for (int a : values) {
            for (int b : values) {
                int ab = Integer.signum(comparator.compare(a, b));
                int ba = Integer.signum(comparator.compare(b, a));
                if (ab != -ba) {
                    return false;
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        int[] extremes = {
                Integer.MIN_VALUE, -1, 0, 1, Integer.MAX_VALUE
        };
        Comparator<Integer> bad = (a, b) -> a - b;
        Comparator<Integer> good = Integer::compare;

        System.out.println("Bad comparator valid: "
                + antisymmetric(bad, extremes));
        System.out.println("Good comparator valid: "
                + antisymmetric(good, extremes));
    }
}
```

Chạy:

```bash
javac ComparatorContractCheck.java
java ComparatorContractCheck
```

Stdout đã xác minh:

```text
Bad comparator valid: false
Good comparator valid: true
```

Test chỉ chứng minh tính chất trên tập đầu vào cụ thể, **không phải chứng minh mọi hợp đồng của mọi comparator**. Nên kết hợp test giá trị biên, test bộ ba cho tính bắc cầu và lập luận rõ ràng rằng API `Integer.compare`/`Long.compare` có thứ tự chính xác.

## 11. Liên hệ với equals, BigDecimal và null

Không phải mọi comparator cho kết quả 0 khi `!a.equals(b)` đều bị overflow. Ví dụ:

```java
new java.math.BigDecimal("2.0")
        .compareTo(new java.math.BigDecimal("2.00")) == 0; // true
```

Hai `BigDecimal` cùng giá trị toán học nhưng khác scale. `BigDecimal.equals` vẫn trả false. Comparator dựa trên `compareTo` là thứ tự có định nghĩa, nhưng sorted collection sử dụng `compareTo` để quyết định key tương đương, nên ứng dụng phải thống nhất danh tính của key.

Tương tự, khi so một object nhiều trường mà chỉ so age:

```java
Comparator<Person> byAge = Comparator.comparingInt(Person::age);
```

Hai người khác nhau nhưng cùng age được xem ngang thứ tự theo comparator. Nếu cần phân biệt, thêm khóa phụ như ID:

```java
Comparator<Person> byAgeThenId =
        Comparator.comparingInt(Person::age)
                  .thenComparing(Person::id);
```

`Person` là một kiểu minh họa có `int age()` và `String id()`. Nếu hai object vẫn có age và id bằng nhau, Comparator trả 0; điều đó phải là quy tắc được chấp nhận của domain.

Với `null`, quyết định chính sách trước khi sort. Ví dụ:

```java
Comparator<Integer> nullable =
        Comparator.nullsLast(Integer::compare);
```

Comparator này cho số null nằm cuối, số nguyên còn lại tăng dần. Nếu null là dữ liệu lỗi, nên reject ở ranh giới thay vì tự gán thứ tự.

## 12. Quy trình sửa Comparator trong code thực tế

1. **Tìm những lambda trả hiệu:** `(a,b)->a-b`, `return x.id-y.id`, `(int)(a.longValue-b.longValue)`, và mọi phép phủ định kết quả của Comparator khác.
2. **Xem kiểu thật của toán hạng:** `int`, `long`, `double`, `BigDecimal`, unsigned hoặc object có null. Đừng bị đánh lừa bởi kiểu biến nhận kết quả.
3. **Đọc yêu cầu nghiệp vụ về thứ tự:** signed hay unsigned? Tăng hay giảm? Khóa chính và phụ nào? NaN/null có hợp lệ?
4. **Thay bằng API so sánh trực tiếp:** `Integer.compare`, `Long.compare`, `Double.compare`, `Comparable.compareTo`, `Comparator.comparing*`.
5. **Dùng `thenComparing` khi cần khóa phụ** và `reversed()` khi muốn đảo thứ tự. Tránh trừ hoặc cộng các hiệu trường.
6. **Test MIN/MAX, số âm, zero, giá trị trùng**, đồng thời kiểm tra cả hai chiều so sánh và các bộ ba bắc cầu.
7. **Kiểm tra các collection thực sự dùng comparator:** sort, `TreeSet`, `TreeMap`, `PriorityQueue`, đặc biệt việc chứa và tra cứu key.
8. **Xem xét dữ liệu đã lưu/index đang hoạt động:** nếu cấu trúc được dựng bằng comparator sai, có thể cần tái tạo theo comparator đúng.

Một Comparator nên làm một việc: **định nghĩa thứ tự**. Nếu logic nghiệp vụ cần **khoảng cách số học**, hãy viết phép tính hiệu ở hàm riêng, dùng kiểu đủ rộng hoặc checked arithmetic phù hợp. Không tái sử dụng giá trị chênh lệch làm kết quả so sánh.

## 13. Lỗi phổ biến và cách thay thế

| Cách viết hoặc quan niệm | Rủi ro | Cách sửa |
| --- | --- | --- |
| `(a,b)->a-b` với `int` | Tràn số, sai dấu | `Integer.compare(a,b)` |
| `(a,b)->b-a` để giảm dần | Vẫn tràn | `Integer.compare(b,a)` hoặc `reversed()` |
| `(a,b)->(int)(a-b)` với `long` | Tràn rồi cast mất bit | `Long.compare(a,b)` |
| `(int)((long)a-b)` với `int` | Cast trở lại `int` mất bit | `Integer.compare(a,b)` |
| `-comparator.compare(a,b)` | Có thể overflow nếu comparator trả `Integer.MIN_VALUE` | `comparator.reversed()` |
| `Math.subtractExact(a,b)` làm Comparator | Ném exception khi hiệu vượt miền dù thứ tự xác định | `Integer.compare`/`Long.compare` |
| `(int)(aDouble-bDouble)` | Chênh lệch nhỏ thành 0; NaN khó xử lý | `Double.compare` |
| Thử vài số dương nhỏ rồi kết luận an toàn | Không thử biên MIN/MAX | Test phản đối xứng, bắc cầu và giá trị cực trị |
| Cho rằng sort không ném lỗi thì comparator đúng | Sai thứ tự có thể xảy ra im lặng | Dựa trên hợp đồng và test biên |
| Dùng comparator sai trong `TreeSet`/`TreeMap` | Key ngang thứ tự hoặc vị trí cây có thể sai | Sửa comparator và cân nhắc dựng lại collection |

## 14. Câu hỏi tự kiểm tra

1. **Vì sao `return a-b` không an toàn trong Comparator<Integer>?** Hiệu `int` có thể overflow, làm dấu không còn phản ánh thứ tự.
2. **Cặp nào phá phản đối xứng?** `Integer.MIN_VALUE` và 0: phép trừ hai chiều đều cho dấu âm.
3. **Kiểu trả về của `compare` là int; có cần trả khoảng cách toán học giữa hai số không?** Không. Chỉ dấu âm, zero hoặc dương mới quan trọng.
4. **Đảo từ `a-b` sang `b-a` có sửa được lỗi không?** Không; cả hai vẫn có thể overflow.
5. **Sắp xếp theo trường `long cents` nên dùng gì?** `Comparator.comparingLong(Item::cents)` hoặc `Long.compare`.
6. **Sắp xếp nhiều trường số nên làm gì?** Dùng `thenComparingInt`, `thenComparingLong`, `thenComparing`.
7. **Có nên phủ định trực tiếp kết quả của Comparator tùy ý?** Không; `-Integer.MIN_VALUE` trong int vẫn âm. Dùng `reversed()`.
8. **Tại sao `TreeSet` và `TreeMap` dễ bị ảnh hưởng nghiêm trọng?** Comparator quyết định thứ tự và tính tương đương của key, có thể ảnh hưởng việc thêm, tìm, xóa, duyệt.
9. **`Math.subtractExact` có cần thiết để xây Comparator không?** Không, vì so sánh không cần tính hiệu.
10. **`Double.compare` có giống phép trừ double rồi xét dấu không?** Không; nó có quy tắc cho NaN/signed zero và tránh sự cố cast/precision.
11. **Nếu hai object khác nhau có cùng khóa sắp xếp thì sao?** Comparator có thể trả 0; cần xác định đó là cùng key hay phải bổ sung tie-breaker.
12. **Một sort chạy thành công có chứng minh comparator đúng không?** Không; test biên và lập luận hợp đồng vẫn cần thiết.

## 15. Kết luận

**Đừng dùng phép trừ để cài đặt Comparator số chỉ vì nó ngắn.** Phép trừ `int`/`long` có thể overflow ở giới hạn miền số, vi phạm phản đối xứng hoặc bắc cầu, khiến `sort` cho thứ tự sai và `TreeSet`/`TreeMap` vận hành ngoài mong đợi.

Dùng `Integer.compare`, `Long.compare`, `Double.compare` hoặc `Comparable.compareTo` theo đúng loại khóa. Với object có nhiều trường, dùng `Comparator.comparingInt`, `comparingLong` và `thenComparing*`; khi cần giảm dần dùng `reversed()`. Luôn kiểm thử các cặp MIN/MAX và hai chiều so sánh — vì lỗi nguy hiểm nhất là Comparator **có vẻ đúng trên dữ liệu nhỏ nhưng sai ở biên**.
