# So sánh với `null` và kiểu không tương thích trong thứ tự tự nhiên

Khi một lớp Java cài đặt `Comparable<T>`, phương thức `compareTo(T other)` định nghĩa **thứ tự tự nhiên (natural ordering)** giữa các đối tượng cùng miền so sánh. Kết quả không đơn giản là `true`/`false`: số âm nghĩa là đứng trước, `0` nghĩa là tương đương theo thứ tự, số dương nghĩa là đứng sau.

Hai trường hợp biên cần có chính sách rõ ràng là **đối số `null`** và **đối tượng không thuộc kiểu có thể so sánh**. Theo hợp đồng của `Comparable`, lời gọi `x.compareTo(null)` trên một `x` khác `null` phải ném `NullPointerException`; nếu đối tượng không thể so sánh với `x` theo kiểu được hỗ trợ, phép so sánh có thể ném `ClassCastException`. Đây là hành vi khác với `equals(null)`, vốn phải trả về `false`.

Mục tiêu: biết **khi nào phép so sánh nên ném ngoại lệ**, cách generic giúp phát hiện lỗi kiểu sớm, và cách dùng `Comparator` nếu **thực sự cần** sắp xếp cả giá trị `null`.

## 1. `compareTo` biểu diễn thứ tự, không phải phép kiểm tra kiểu tùy ý

Một dạng khai báo phổ biến:

```java
public final class Lesson implements Comparable<Lesson> {
    @Override
    public int compareTo(Lesson other) {
        // So sánh các thuộc tính quyết định thứ tự.
        throw new UnsupportedOperationException("Phần thân chỉ minh họa");
    }
}
```

Đây chỉ là **khung minh họa API**, không phải cài đặt hoàn chỉnh: phần thân phải được thay bằng quy tắc so sánh thật. Khi đã dùng `Comparable<Lesson>`, một biến kiểu `Lesson` chỉ được gọi `compareTo` với đối số kiểu `Lesson` (hoặc subtype phù hợp) hay `null` ở mức kiểm tra kiểu tĩnh.

Các điều kiện đáng nhớ của `compareTo`:

- `x.compareTo(y) < 0`: `x` đứng trước `y`; `== 0`: bằng nhau theo *thứ tự*; `> 0`: `x` đứng sau `y`. **Không giả định kết quả luôn là đúng `-1`, `0`, `1`**; chỉ dấu của kết quả có ý nghĩa.
- Phải giữ tính đối xứng dấu: `signum(x.compareTo(y)) == -signum(y.compareTo(x))` với các đối tượng so sánh được. Nếu một chiều ném ngoại lệ vì không so sánh được, chiều còn lại cũng không được vô cớ trở thành một phép so sánh hợp lệ.
- Thứ tự phải có tính bắc cầu và nhất quán với các trường hợp so sánh tương đương theo thứ tự. Nếu `x.compareTo(y) == 0`, kết quả so sánh `x` và `y` với một `z` khác phải có cùng dấu khi các phép so sánh đó hợp lệ.
- Nhất quán với `equals` **được khuyến nghị mạnh**: `x.compareTo(y) == 0` nên tương đương với `x.equals(y)`. Tuy nhiên, API `Comparable` không bắt buộc mọi lớp phải giữ sự tương đương này; trường hợp `BigDecimal` được trình bày ở phần sau.

Phép `compareTo` chỉ có ý nghĩa trong miền đối tượng mà lớp thực sự biết sắp thứ tự. Nó không phải bộ chuyển đổi dữ liệu, cũng không nên dựa vào việc tự trả `0` cho mọi đối tượng không hợp lệ.

## 2. Đối số `null`: `compareTo(null)` phải ném `NullPointerException`

Một lớp cài đặt `Comparable` đúng hợp đồng không xem `null` như phần tử thuộc thứ tự tự nhiên của nó:

```java
// Minh họa khi value khác null:
value.equals(null);     // false nếu equals tuân thủ hợp đồng
value.compareTo(null);  // ném NullPointerException
```

Lý do: `null` không phải instance của một lớp, nên việc một đối tượng có đứng trước hay sau `null` không được `Comparable` tự định nghĩa. Trong một `compareTo` tự viết, có thể dùng `Objects.requireNonNull(other)` ngay đầu phương thức để khẳng định điều kiện này; sau đó so sánh các trường theo chính sách của lớp.

Nếu chỉ viết `other.field`, việc truy cập đó cũng ném `NullPointerException` khi `other == null`, nhưng cách kiểm tra tường minh giúp ý định rõ hơn và tránh vô tình xử lý `null` như một đối tượng hợp lệ.

**Không sửa `compareTo` để trả `0` khi `other == null`**. Làm vậy khiến `null` bị coi là tương đương theo thứ tự với một instance có thật, trái với hợp đồng `Comparable` và gây ngữ nghĩa khó hiểu cho các cấu trúc dựa trên thứ tự.

Cũng phân biệt hai tình huống:

- **Đối số `null`:** `someValue.compareTo(null)` có receiver hợp lệ và phải ném `NullPointerException`.
- **Receiver `null`:** `someNullableVariable.compareTo(x)` cũng có thể ném `NullPointerException`, nhưng vì cố gọi instance method trên tham chiếu `null` ngay trước khi có thể chạy thân `compareTo`; đây là lỗi gọi phương thức, không phải một thứ tự được định nghĩa cho `null`.

## 3. Kiểu không tương thích và vai trò của generic

Với lớp `Lesson implements Comparable<Lesson>`, Java kiểm tra kiểu đối số ngay lúc biên dịch:

```java
// Chỉ là đoạn minh họa; giả sử first có kiểu Lesson:
first.compareTo(anotherLesson); // Hợp lệ nếu anotherLesson là Lesson
first.compareTo(null);          // Hợp lệ khi biên dịch; NPE khi chạy
// first.compareTo("java");     // Không biên dịch: String không phải Lesson
```

Dấu comment ở dòng cuối cố ý giữ ví dụ có thể đặt trong mã nguồn hợp lệ; nếu bỏ comment, compiler sẽ phát hiện sai kiểu. Nhưng với **raw type** (`Comparable` không có tham số generic), ép kiểu không an toàn, hoặc Java code cũ, lỗi có thể lọt qua compiler rồi xuất hiện tại runtime:

```java
// Minh họa code cũ/không an toàn, không nên dùng trong API bình thường:
Comparable raw = first;
raw.compareTo("java"); // Có thể biên dịch với unchecked warning; CCE khi chạy
```

Một lớp triển khai `Comparable<Lesson>` thông thường sinh ra bridge method cho cơ chế type erasure. Khi raw caller đưa vào một `String`, runtime không thể chuyển `String` thành `Lesson`, nên ném `ClassCastException` trước khi đi vào logic sắp thứ tự thông thường.

**`ClassCastException` khác `NullPointerException`:** ngoại lệ đầu tiên báo đối tượng không thể so sánh vì kiểu, ngoại lệ thứ hai báo tham chiếu không tồn tại. Không nên bắt cả hai rồi im lặng coi như `compareTo` trả `0`; như vậy che giấu vi phạm hợp đồng và có thể làm `TreeSet`, `TreeMap` mất hoặc gộp sai dữ liệu.

## 4. Chương trình Java 17+ hoàn chỉnh

Ví dụ sau xây dựng một thứ tự tự nhiên rõ ràng cho `LessonOrder`: trước tiên sắp theo `priority` tăng dần, nếu trùng thì so `title` bằng thứ tự từ điển của `String`. Constructor từ chối `title == null`, nên các trường dùng trong `compareTo` luôn hợp lệ.

Lưu vào tệp **`NaturalOrderBoundariesDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

final class LessonOrder implements Comparable<LessonOrder> {
    private final int priority;
    private final String title;

    LessonOrder(int priority, String title) {
        this.priority = priority;
        this.title = Objects.requireNonNull(title, "title");
    }

    @Override
    public int compareTo(LessonOrder other) {
        Objects.requireNonNull(other, "other");

        int byPriority = Integer.compare(priority, other.priority);
        if (byPriority != 0) {
            return byPriority;
        }
        return title.compareTo(other.title);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof LessonOrder other)) {
            return false;
        }
        return priority == other.priority
                && title.equals(other.title);
    }

    @Override
    public int hashCode() {
        return Objects.hash(priority, title);
    }
}

public class NaturalOrderBoundariesDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    private static String compareWithWrongType(LessonOrder lesson) {
        Comparable raw = lesson;
        try {
            raw.compareTo("wrong type");
            return "accepted";
        } catch (ClassCastException expected) {
            return expected.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        LessonOrder first = new LessonOrder(1, "Core");
        LessonOrder same = new LessonOrder(1, "Core");
        LessonOrder later = new LessonOrder(2, "Advanced");

        System.out.println("compare equal values: "
                + first.compareTo(same));
        System.out.println("equals equal values: " + first.equals(same));
        System.out.println("first before later: "
                + (first.compareTo(later) < 0));
        System.out.println("equals(null): " + first.equals(null));

        try {
            first.compareTo(null);
            System.out.println("compareTo(null): accepted");
        } catch (NullPointerException expected) {
            System.out.println("compareTo(null): NullPointerException");
        }

        System.out.println("wrong type via raw Comparable: "
                + compareWithWrongType(first));

        Set<LessonOrder> naturalSet = new TreeSet<>();
        naturalSet.add(first);
        naturalSet.add(same);
        naturalSet.add(later);
        System.out.println("natural TreeSet size: " + naturalSet.size());

        Comparator<LessonOrder> nullFirst =
                Comparator.nullsFirst(Comparator.naturalOrder());
        TreeSet<LessonOrder> nullableSet = new TreeSet<>(nullFirst);
        nullableSet.add(first);
        nullableSet.add(null);
        System.out.println("nullable TreeSet first is null: "
                + (nullableSet.first() == null));

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal otherOne = new BigDecimal("1.00");
        System.out.println("BigDecimal compareTo zero: "
                + (one.compareTo(otherOne) == 0));
        System.out.println("BigDecimal equals: "
                + one.equals(otherOne));
        Set<BigDecimal> decimalSet = new TreeSet<>();
        decimalSet.add(one);
        decimalSet.add(otherOne);
        System.out.println("BigDecimal TreeSet size: "
                + decimalSet.size());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac NaturalOrderBoundariesDemo.java
java NaturalOrderBoundariesDemo
```

Kết quả stdout xác định:

```text
compare equal values: 0
equals equal values: true
first before later: true
equals(null): false
compareTo(null): NullPointerException
wrong type via raw Comparable: ClassCastException
natural TreeSet size: 2
nullable TreeSet first is null: true
BigDecimal compareTo zero: true
BigDecimal equals: false
BigDecimal TreeSet size: 1
```

Giải thích:

1. Hai `LessonOrder(1, "Core")` là hai instance độc lập nhưng bằng nhau theo `equals` và tương đương theo `compareTo`, vì cả hai phương thức dùng cùng cặp trường.
2. `LessonOrder(1, "Core")` đứng trước `LessonOrder(2, "Advanced")` vì `priority` nhỏ hơn; không cần quan tâm `title` khi đã phân định được theo `priority`.
3. `first.equals(null)` trả `false`, trong khi `first.compareTo(null)` ném `NullPointerException`. Đây là hai hợp đồng khác nhau, đều đúng.
4. Hàm `compareWithWrongType` cố tình dùng raw `Comparable`. Runtime từ chối `String` bằng `ClassCastException`, thay vì đưa ra một kết quả thứ tự giả.
5. `naturalSet` dùng thứ tự tự nhiên. Vì `first.compareTo(same) == 0`, `TreeSet` coi chúng là một phần tử theo thứ tự sắp xếp.
6. `nullableSet` có **`Comparator.nullsFirst` rõ ràng**, nên có thể chứa `null` và đặt nó trước các đối tượng hợp lệ. Không cần sửa `LessonOrder.compareTo(null)`.
7. `BigDecimal("1.0")` và `BigDecimal("1.00")` bằng nhau theo giá trị số học khi gọi `compareTo`, nhưng khác `scale` nên `equals` là `false`. `TreeSet` dùng quan hệ `compareTo == 0` làm tương đương khi sắp xếp, vì vậy chỉ giữ một phần tử.

## 5. `Comparator.nullsFirst`/`nullsLast`: cách định nghĩa thứ tự có `null`

Nếu ứng dụng thật sự có danh sách chứa `null` cần sắp xếp, hãy định nghĩa chính sách **ở bên ngoài thứ tự tự nhiên**, qua `Comparator`:

```java
Comparator<LessonOrder> nullFirst =
        Comparator.nullsFirst(Comparator.naturalOrder());
Comparator<LessonOrder> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());
```

Với `nullFirst`, `null` được xếp trước đối tượng không `null`; với `nullLast`, `null` được xếp sau. Khi hai đối số đều không `null`, comparator ủy quyền cho `compareTo` tự nhiên. Khi cả hai cùng `null`, comparator coi chúng bằng nhau theo thứ tự.

| So sánh | Thứ tự tự nhiên `x.compareTo(y)` | `nullsFirst(naturalOrder())` | `nullsLast(naturalOrder())` |
| --- | --- | --- | --- |
| `x` khác `null`, `y` khác `null` | Theo `compareTo` | Theo `compareTo` | Theo `compareTo` |
| `x == null`, `y != null` | Không gọi instance method được | `null` đứng trước | `null` đứng sau |
| `x != null`, `y == null` | `compareTo(null)` ném NPE | `x` đứng sau | `x` đứng trước |
| `x == null`, `y == null` | Không có receiver hợp lệ | `0` | `0` |

Chọn một trong hai tùy nghiệp vụ (ví dụ dữ liệu thiếu cần ưu tiên đầu danh sách hay đặt cuối). `Comparator` giúp chính sách này tường minh mà vẫn giữ hợp đồng `Comparable`.

**Cảnh báo về `null` ở hai cấp:** `Comparator.nullsFirst(Comparator.comparing(Person::getName))` chỉ xử lý **đối tượng `Person` có thể `null`**, không tự xử lý **`getName()` trả về `null`**. Nếu cả phần tử lẫn khóa so sánh có thể `null`, cần chọn comparator ở mỗi cấp:

```java
// Minh họa đặt tại nơi đã định nghĩa lớp Person có getName():
Comparator<Person> byName = Comparator.nullsFirst(
        Comparator.comparing(
                Person::getName,
                Comparator.nullsLast(Comparator.naturalOrder())
        )
);
```

Đây là đoạn minh họa kiểu `Person` do ứng dụng cung cấp, **không phải ví dụ biên dịch độc lập**. `nullsFirst` ngoài cùng xử lý `Person == null`; `nullsLast` bên trong xử lý `Person.getName() == null`.

Một `TreeSet`/`TreeMap` dùng thứ tự tự nhiên thường không nhận khóa `null`, vì cần phép so sánh tự nhiên. Chúng có thể nhận `null` nếu comparator do ứng dụng cung cấp **thật sự định nghĩa được** cách so với `null`. Không suy ra rằng mọi `SortedSet` hoặc mọi comparator đều chấp nhận `null`.

## 6. Kiểu khác nhau: `equals` có thể trả `false`, còn `compareTo` có thể ném CCE

Mục đích của `equals(Object)` là kiểm tra bằng nhau với một đối số `Object` bất kỳ; nếu khác kiểu và không thuộc quan hệ bằng nhau hợp lệ, kết quả thường là `false`:

```java
// Giả sử lesson là LessonOrder:
lesson.equals("Core"); // false: String không phải LessonOrder
```

Ngược lại, `compareTo` không phải phương thức có nghĩa “khác kiểu thì trả `1`”. Việc trả một số âm hoặc dương cho mọi kiểu không có quy tắc sắp xếp chung có thể phá tính đối xứng và bắc cầu. Tránh cố tạo quan hệ thứ tự tùy tiện chỉ để không ném ngoại lệ.

Generics tạo ra một đường ranh giới rõ:

- **Đúng kiểu tại compile time:** `Comparable<LessonOrder>` chỉ cho phép đối số `LessonOrder` hoặc `null`; compiler loại bỏ nhiều lời gọi sai.
- **Raw type/unchecked cast/reflection hoặc mã cũ:** có thể đưa đối số sai kiểu tại runtime; lúc này `ClassCastException` là tín hiệu phù hợp.
- **Khi cần so các kiểu khác nhau theo quy tắc ứng dụng:** dùng **`Comparator` trên một miền chung đã xác định**, ví dụ chuyển các dạng dữ liệu sang một key chung trước khi so. Không tự động trộn `String`, số và đối tượng nghiệp vụ trong một natural ordering vô căn cứ.

Không bắt ngoại lệ để thay bằng `0`; `0` có ý nghĩa **cùng thứ hạng** và có thể khiến `TreeSet` xem hai phần tử như một.

## 7. Ảnh hưởng đối với `TreeSet`, `TreeMap`, `Collections.sort`

Các API sắp xếp/dựa trên thứ tự sử dụng `compareTo` hoặc `Comparator.compare`:

- `TreeSet` dùng dấu của phép so sánh để xác định vị trí và tương đương theo thứ tự. Nếu hai phần tử có kết quả so sánh `0`, thường không thể lưu như hai phần tử phân biệt theo semantics của set đó.
- `TreeMap` dùng thứ tự để phân biệt khóa; nếu comparator coi hai khóa là tương đương (`0`), thêm khóa thứ hai sẽ tác động vào cùng entry logic theo thứ tự của map.
- `Collections.sort(list)` hoặc `list.sort(null)` dùng thứ tự tự nhiên; nếu có `null` hoặc phần tử không thể so sánh với nhau, thao tác có thể ném NPE/CCE. Với danh sách có `null` hợp lệ, hãy truyền comparator minh thị qua `list.sort(Comparator.nullsLast(...))`.

Đặc biệt, cấu trúc `SortedSet` và `SortedMap` có hành vi đúng theo quy tắc tập hợp/map thông thường khi thứ tự của chúng **nhất quán với `equals`**. Trong ví dụ `BigDecimal`, `compareTo` có thể trả `0` trong khi `equals` trả `false`, làm `TreeSet` có hành vi khác `HashSet` trên cùng dữ liệu. Đây là điều cần biết để chọn mô hình và tránh nhầm số lượng phần tử.

Nếu một lớp custom được dùng làm khóa `TreeMap` hoặc phần tử `TreeSet`, nên đặt các trường quyết định thứ tự là **bất biến** trong thời gian lưu. Nếu thay đổi trường tham gia `compareTo` sau khi chèn, cấu trúc cây có thể không còn sắp xếp và tra cứu đúng như kỳ vọng.

## 8. Checklist khi viết hoặc sử dụng `Comparable<T>`

1. **Miền kiểu:** lớp chỉ chấp nhận những đối tượng nào? `Comparable<T>` đã biểu diễn đúng miền này chưa?
2. **Null:** `x.compareTo(null)` có ném `NullPointerException` không? Có vô tình coi `null` là bằng một giá trị thật không?
3. **Kiểu không tương thích:** lời gọi sai kiểu qua raw/unchecked path có bị từ chối bằng `ClassCastException` thay vì trả một thứ tự giả không?
4. **Thứ tự toán học:** phép so sánh có giữ đối xứng dấu, bắc cầu và ngữ nghĩa `compareTo == 0` ổn định không?
5. **Quan hệ với `equals`:** nếu `compareTo == 0` khác `equals == true`, hành vi `TreeSet`/`TreeMap` có được hiểu và chấp nhận không?
6. **Chính sách null của collection:** nếu dữ liệu hợp lệ có `null`, đã dùng `Comparator.nullsFirst` hoặc `nullsLast` ở đúng cấp phần tử hoặc khóa chưa?
7. **Trạng thái mutable:** các trường tham gia thứ tự có được giữ ổn định khi đối tượng đang nằm trong cấu trúc sắp xếp không?
8. **Giá trị trả về:** phần code sử dụng có kiểm tra `< 0`, `== 0`, `> 0` thay vì so đúng `-1` hoặc `1` không?

**Ghi nhớ:** `Comparable.compareTo` định nghĩa thứ tự **giữa các giá trị thuộc miền so sánh**. `compareTo(null)` ném **`NullPointerException`**; kiểu không tương thích bị từ chối, thường bằng **`ClassCastException`** nếu vượt qua kiểm tra generic. Khi nghiệp vụ muốn sắp xếp cả `null`, hãy viết quy tắc riêng bằng **`Comparator.nullsFirst`/`nullsLast`**, và cân nhắc sự tương thích với `equals` trong `TreeSet`/`TreeMap`.
