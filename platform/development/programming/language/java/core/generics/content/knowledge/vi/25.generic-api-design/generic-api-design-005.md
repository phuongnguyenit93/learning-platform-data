# Tránh tham số kiểu chỉ xuất hiện một lần mà không tạo quan hệ cần thiết

## Mục tiêu bài học

Khi thiết kế Java Generic API, một lỗi thường gặp là khai báo `<T>` cho mọi phương thức nhìn thấy một kiểu generic, kể cả khi `T` không giúp ràng buộc bất kỳ thông tin nào. Ví dụ:

```java
static <T> void printValues(List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}
```

Method này chỉ **đọc rồi in** phần tử. Nếu không cần biết chính xác `T`, chữ ký thường rõ hơn khi viết:

```java
static void printValues(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

**Nguyên tắc:** Chỉ đặt tên cho một type variable `T` khi tên đó mang thông tin có ích: liên kết nhiều vị trí kiểu, giới hạn kiểu một cách cần thiết, diễn đạt kiểu kết quả theo đầu vào, hoặc cho phép một thao tác nội bộ an toàn mà wildcard bên ngoài không biểu diễn trực tiếp được. Nếu `T` chỉ xuất hiện một lần và không tạo ràng buộc cần thiết, một wildcard hoặc một supertype thông thường thường dễ đọc hơn.

Tuy nhiên, đây là **quy tắc thiết kế (heuristic), không phải lệnh cấm tuyệt đối**. Có ngoại lệ đáng kể: wildcard capture helper, generic factory trả collection rỗng, type inference dựa trên return target, và những type bounds quan trọng. Không nên thay cơ học mọi `<T>` xuất hiện một lần bằng `?`.

Sau bài này, bạn có thể:

- Phân biệt tham số kiểu **có ý nghĩa ràng buộc** với một tham số chỉ làm phức tạp chữ ký.
- Chọn đúng giữa `Object`, `List<?>`, `List<? extends Number>`, `List<? super T>` và `List<T>`.
- Giải thích vì sao `<T> void print(List<T>)` thường là quá mức, còn `<T> void append(List<? super T>, T)` lại có quan hệ kiểu thực sự.
- Nhận ra các trường hợp `T` có mặt ở **đầu vào và đầu ra**, trong callback, hoặc trong bounds `Comparable<? super T>`.
- Hiểu tại sao `<T> List<T> emptyTyped()` vẫn có ích dù không nhận `T` từ tham số đầu vào.
- Hiểu wildcard capture: API public `List<?>`, implementation private dùng `<T>` để đọc rồi ghi lại **cùng một kiểu phần tử chưa biết**.
- Biết những rủi ro khi đổi chữ ký public API: source compatibility, generic reflection metadata, overload/override và binary descriptors.
- Kiểm chứng ví dụ Java 17 bằng `javac`/`java`/`javap`.

Bài thuộc chủ đề **Thiết kế API** trong Java Core — Generics, dành cho Java 17+. Các chương trình đầy đủ đã được chạy thực tế với `javac -Xlint:all`; những đoạn trích khác có ghi chú về ngữ cảnh và khả năng biên dịch.

## 1. Type parameter là một biến biểu thị **quan hệ kiểu**

Trong generic method:

```java
static <T> T identity(T input) {
    return input;
}
```

cùng một `T` xuất hiện ở tham số và return type. Nếu caller truyền `String`, compiler có thể suy ra kiểu kết quả liên quan với kiểu đầu vào:

```java
String s = identity("Java");
Integer n = identity(42);
```

Ý nghĩa của `T` không chỉ là “method dùng được với nhiều kiểu”. Nó diễn đạt **giá trị đầu ra có cùng kiểu tĩnh suy luận được từ giá trị đầu vào**.

Một hàm không generic:

```java
static Object identityObject(Object input) {
    return input;
}
```

có thể trả chính object ấy, nhưng kiểu return chỉ là `Object`. Caller muốn lấy `String` thường phải cast hoặc dùng logic khác. Như vậy `identity(T)` có quan hệ cần giữ, không nên thay `T` bằng `Object`.

Đối chiếu với method:

```java
static <T> void display(T value) {
    System.out.println(value);
}
```

Ở đây nếu method chỉ đưa value vào `println(Object)`, không có thêm tham số hay kết quả cần ràng buộc, ta có thể viết đơn giản:

```java
static void display(Object value) {
    System.out.println(value);
}
```

Cả hai minh họa cùng ý định “nhận một object và in”. Sự khác biệt trong overload/type inference có thể tồn tại ở một API phức tạp; hãy đánh giá chữ ký cụ thể, nhưng **generic `T` không thêm bảo đảm thiết thực** trong implementation đơn giản này.

## 2. Đọc vai trò của kiểu trước khi đếm số lần xuất hiện

Một bảng khởi đầu:

| Chữ ký | `T` có tạo quan hệ thiết yếu không? | Thiết kế gợi ý |
| --- | --- | --- |
| `<T> void print(List<T> data)` | Không, nếu chỉ đọc dưới dạng `Object` | `void print(List<?> data)` |
| `<T> boolean containsNull(List<T> data)` | Không, nếu chỉ quan sát phần tử | `boolean containsNull(List<?> data)` |
| `<T extends Number> double sum(List<T> xs)` | Thường không, nếu chỉ cần các `Number` | `double sum(List<? extends Number> xs)` |
| `<T> T identity(T x)` | Có: input → return | Giữ `<T>` |
| `<T> void append(List<? super T> dst, T value)` | Có: dst chấp nhận value | Giữ `<T>` |
| `<T> long countIf(List<? extends T> src, Predicate<? super T> test)` | Có: predicate phải nhận phần tử nguồn | Giữ `<T>` |
| `<T> List<T> repeat(T x, int n)` | Có: kiểu phần tử kết quả theo `x` | Giữ `<T>` |
| `<T> List<T> emptyTyped()` | Có ý nghĩa với target typing dù chỉ một vị trí xuất hiện | Giữ được `<T>` |
| `private <T> void swapCaptured(List<T> xs,...)` | Có ý nghĩa ở **thân phương thức** qua wildcard capture | Không thay máy móc |

Cần nhìn **hợp đồng public + cách dùng trong body + mục tiêu suy luận kiểu**. Đếm ký tự `T` là một tín hiệu code review, không phải bằng chứng đủ để tự động refactor.

## 3. Vì sao `List<?>` thường đúng khi chỉ đọc?

Java generics **invariant**. Dù `String extends Object`:

```java
List<String> names = List.of("Lan", "Minh");
// List<Object> objects = names; // Lỗi compile time.
```

`List<String>` không phải subtype của `List<Object>`. Nếu chữ ký nhận:

```java
static void print(List<Object> values)
```

thì method **không** nhận trực tiếp biến `List<String>` hoặc `List<Integer>`.

Nếu method chỉ cần duyệt, không đòi ràng buộc giữa hai vị trí kiểu:

```java
static void print(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

thì chấp nhận an toàn `List<String>`, `List<Integer>`, `List<Dog>` và nhiều loại list khác.

Dấu `?` nghĩa là “kiểu phần tử nào đó mà caller không cần công khai tên”; compiler **không** giả định đó là `Object` để cho ghi tùy tiện. Khi đọc, giá trị có thể dùng như `Object`.

**Quan trọng:** `List<?>` không đồng nghĩa một list bất biến. Tùy implementation, các thao tác như `clear()`, `remove(int)` hay `iterator().remove()` có thể sửa cấu trúc. Điều compiler hạn chế là việc **thêm một giá trị non-null tùy ý** vì không biết element type thật.

Không nên gọi `List<?>` là “read-only list” tuyệt đối. Nó là **góc nhìn có kiểu phần tử chưa xác định**, hữu ích cho các thao tác quan sát.

## 4. `Object` hay wildcard? Đừng coi chúng là thay thế tương đương

Với một giá trị đơn lẻ, không cần quan hệ kiểu:

```java
static void log(Object event)
```

rõ ràng hơn `static <T> void log(T event)` khi body chỉ gọi `String.valueOf` hoặc `System.out.println`.

Nhưng đối với **container**, `List<Object>` khác hẳn `List<?>`:

```java
static void inspect(List<?> source) {
    for (Object x : source) System.out.println(x);
}
```

chấp nhận nhiều `List<E>`, còn:

```java
static void inspectObjects(List<Object> source) {
    for (Object x : source) System.out.println(x);
}
```

chỉ chấp nhận các tham chiếu phù hợp `List<Object>` (và subtype theo quan hệ class/type parameter tương ứng). Nó không chấp nhận `List<String>` trực tiếp vì invariance.

Một quy tắc nhanh:

- **Một object tự do:** `Object` nếu không có ràng buộc kiểu khác.
- **Một cấu trúc generic có phần tử không cần gọi tên:** `List<?>`, `Collection<?>`, `Class<?>`, v.v.
- **Nguồn chỉ được đọc dưới supertype xác định:** `List<? extends Number>`.
- **Có liên hệ giữa nhiều vị trí kiểu:** type variable `T`.

## 5. Nếu chỉ đọc `Number`, hãy để wildcard diễn đạt điều đó

Thiết kế thường thấy:

```java
static <T extends Number> double sum(List<T> source) {
    double total = 0;
    for (T n : source) total += n.doubleValue();
    return total;
}
```

Trong method này, caller không nhận lại một giá trị có kiểu `T`, cũng không có tham số thứ hai bị ràng buộc bởi `T`. Method chỉ cần `Number.doubleValue()`.

Có thể viết:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) total += n.doubleValue();
    return total;
}
```

Nó nhận `List<Integer>`, `List<Double>` hoặc danh sách subtype khác của `Number`, và công bố rõ **cần một nguồn cung cấp các Number**.

Không nên thay thành `List<Number>` nếu vẫn muốn nhận `List<Integer>`, vì Java generic invariance. Không nên dùng raw `List` rồi cast từng phần tử nếu wildcard đã biểu diễn được ý định.

Với dữ liệu không đáng tin, `List<? extends Number>` là **cam kết compile time của tham chiếu nguồn**, không phải cơ chế validate một raw collection đã bị heap pollution. Đó là một vấn đề khác cần xử lý tại ranh giới dữ liệu.

## 6. Chương trình A — API tối giản và API cần quan hệ kiểu

Tạo tệp **`ApiSignatureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

public class ApiSignatureDemo {
    static void printValues(List<?> source) {
        for (Object value : source) {
            System.out.println("item: " + value);
        }
    }

    static boolean containsNull(List<?> source) {
        for (Object value : source) {
            if (value == null) return true;
        }
        return false;
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number number : source) {
            total += number.doubleValue();
        }
        return total;
    }

    static <T> long countIf(
            List<? extends T> source,
            Predicate<? super T> predicate) {
        long count = 0;
        for (T value : source) {
            if (predicate.test(value)) count++;
        }
        return count;
    }

    static <T> void append(List<? super T> target, T value) {
        target.add(value);
    }

    static <T> List<T> repeat(T value, int times) {
        if (times < 0) {
            throw new IllegalArgumentException("times");
        }
        List<T> result = new ArrayList<>();
        for (int i = 0; i < times; i++) {
            result.add(value);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> words =
                List.of("Java", "Generic", "API");

        printValues(List.of("A", "B"));
        System.out.println("null: " + containsNull(words));
        System.out.println("sum: " + sum(List.of(2, 3.5)));

        Predicate<CharSequence> longText =
                s -> s.length() >= 4;
        System.out.println("long words: "
                + countIf(words, longText));

        List<Number> numbers = new ArrayList<>();
        append(numbers, Integer.valueOf(10));
        append(numbers, Double.valueOf(2.5));
        System.out.println("target: " + numbers);

        System.out.println("repeat: " + repeat("ok", 3));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all ApiSignatureDemo.java
java ApiSignatureDemo
```

**Stdout đã kiểm chứng trên Java 17:**

```text
item: A
item: B
null: false
sum: 5.5
long words: 2
target: [10, 2.5]
repeat: [ok, ok, ok]
```

Chương trình biên dịch không cảnh báo dưới `-Xlint:all`.

### Phân tích nhóm không cần `<T>`

`printValues(List<?>)` không mang một kiểu phần tử riêng vào tham số khác hoặc return type: đọc như `Object` là đủ.

`containsNull(List<?>)` chỉ kiểm tra từng phần tử và trả `boolean`, hoàn toàn không cần đặt tên type parameter.

**Một chi tiết Java đáng nhớ:** không nên triển khai `containsNull` bằng cách giả định `source.contains(null)` luôn trả boolean. Một số implementation list từ `List.of(...)` từ chối thao tác tìm `null` và có thể ném `NullPointerException`. Bởi vậy ví dụ **duyệt phần tử** rồi so `== null` để có kết quả rõ theo hợp đồng của method tự viết.

`sum(List<? extends Number>)` chỉ cần đọc phần tử như `Number`, nên bound có thể nằm ở wildcard mà không phải một type variable được đặt tên.

### Phân tích nhóm **thật sự cần** `<T>`

`countIf` nối hai tham số:

```java
List<? extends T> source
Predicate<? super T> predicate
```

Source cung cấp những giá trị dùng như `T`, còn predicate có thể **tiêu thụ** các `T` ấy. Ví dụ `List<String>` phối hợp an toàn với `Predicate<CharSequence>` vì predicate nhận một supertype của `String`. Nếu bỏ `T`, phương thức mất cách diễn đạt ràng buộc giữa loại phần tử và loại callback.

`append` nối loại phần tử `T` cần ghi và một target chấp nhận `T`:

```java
List<? super T> target
T value
```

Với `List<Number>`, `Integer` và `Double` đều là lựa chọn an toàn trong lời gọi phù hợp. Không được tùy tiện thay `T` ở đích thành `?`, vì qua `List<?>` compiler không cho thêm các giá trị non-null không biết kiểu.

`repeat(T,int)` nối input kiểu `T` với output `List<T>`: caller nhận danh sách chứa đúng loại đã suy luận từ `value`. Đây là một cam kết đầu vào–đầu ra có giá trị.

**Chính sách `null`:** `repeat` dùng `List.copyOf`, nên không hỗ trợ `null` làm phần tử. Đây là đặc điểm của implementation ví dụ, độc lập với việc chọn `T` hay wildcard.

## 7. Vì sao `countIf` cần `? super T` ở callback?

Đọc lời gọi trong chương trình A:

```java
Predicate<CharSequence> longText =
        value -> value.length() >= 4;

long result = countIf(words, longText);
```

`words` là `List<String>`. Mỗi `String` có thể dùng như `CharSequence`. Nếu predicate chấp nhận mọi `CharSequence`, nó chắc chắn đánh giá được mọi `String`.

Chữ ký:

```java
static <T> long countIf(
        List<? extends T> source,
        Predicate<? super T> predicate)
```

là phiên bản **PECS** có quan hệ:

- `source` **sản xuất** giá trị `T` → `? extends T`.
- `predicate` **tiêu thụ** giá trị `T` → `? super T`.

Cặp `T` không phải trang trí; nó buộc hai tham số phối hợp đúng. Đây là ví dụ tiêu biểu về một generic method có ích dù không trả `T`.

### Khi nào có thể không cần `T` cho callback?

Nếu yêu cầu đơn giản là “đọc `Object` và in”, bạn không cần callback generic phức tạp:

```java
static void dump(List<?> values) {
    for (Object value : values) System.out.println(value);
}
```

Nhưng nếu caller đưa callback typed, hãy giữ ràng buộc phù hợp thay vì hạ tất cả về `Object` rồi dùng unchecked cast.

## 8. Việc dùng một type variable có thể ở nhiều **vị trí logic**, không phải chỉ nhiều tham số

Không chỉ quan hệ giữa hai method parameters mới đáng giữ. Những nơi sau cũng là lý do hợp lệ:

**Input → return:**

```java
static <T> T identity(T value) {
    return value;
}
```

**Input → element type của collection trả về:**

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
```

**Input từ nhiều nguồn → một loại đích:**

```java
static <T> void copyInto(
        java.util.Collection<? extends T> source,
        java.util.Collection<? super T> destination) {
    for (T item : source) destination.add(item);
}
```

Đây là các đoạn method minh họa có thể đặt trong một class với imports phù hợp. Trong `copyInto`, `T` liên kết producer và consumer; đó là lý do không thể đơn giản loại bỏ type variable nếu muốn compiler giữ cùng hợp đồng linh hoạt.

**Một bound tham chiếu lại `T`** cũng có ý nghĩa, chẳng hạn:

```java
<T extends Comparable<? super T>>
```

nói rằng mỗi `T` có thể được so sánh với giá trị loại `T` theo giao diện `Comparable` phù hợp. Nó không giống một `<T>` chỉ đặt tên cho một đối số mà method không dùng quan hệ nào.

## 9. Đừng quên ngoại lệ lớn: wildcard capture helper

Quy tắc “`T` xuất hiện một lần thì dùng `?`” **không được áp dụng máy móc** vào generic helper nhằm **capture một wildcard**.

Ví dụ caller truyền `List<?>`; bạn cần hoán đổi hai phần tử. Vì không biết kiểu phần tử cụ thể, Java từ chối lời ghi tùy ý như:

```java
static void badSwap(List<?> items, int i, int j) {
    // items.set(i, items.get(j)); // Lỗi vì hai biểu thức bị capture độc lập.
}
```

Đoạn trên là minh họa đã comment thao tác nguy hiểm. Khi nhìn ở mức API public, `List<?>` vẫn là hợp đồng phù hợp: caller không cần biết kiểu phần tử. Nhưng **bên trong** cần ràng buộc giá trị đọc ra với kiểu phần tử của **cùng list**.

Giải pháp là helper có type variable riêng:

```java
static void swapAny(List<?> items, int i, int j) {
    swapCaptured(items, i, j);
}

private static <T> void swapCaptured(
        List<T> items, int i, int j) {
    T first = items.get(i);
    items.set(i, items.get(j));
    items.set(j, first);
}
```

Tại phương thức public, caller thấy `List<?>`. Khi `swapCaptured(items, ...)` được gọi, compiler dùng **wildcard capture conversion** để gán tên `T` cho đúng một kiểu phần tử chưa biết nhưng nhất quán ở **lời gọi helper ấy**.

Tại helper:

- `items.get(i)` có kiểu `T`.
- `items.set(i, ...)` nhận một giá trị kiểu `T`.
- Giá trị đã lấy từ **chính `items`** có thể được ghi trở lại an toàn.

Dù trong **chữ ký** helper `T` có thể chỉ xuất hiện ở `List<T>`, **body** dùng `T` để bảo toàn quan hệ đọc–ghi. Đây là một **ngoại lệ có ý nghĩa** đối với heuristic “xuất hiện một lần”.

## 10. Chương trình B — Wildcard capture trong implementation

Tạo tệp **`WildcardCaptureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapAny(List<?> items, int i, int j) {
        swapCaptured(items, i, j);
    }

    private static <T> void swapCaptured(
            List<T> items, int i, int j) {
        T first = items.get(i);
        items.set(i, items.get(j));
        items.set(j, first);
    }

    static void duplicateFirst(List<?> items) {
        duplicateCaptured(items);
    }

    private static <T> void duplicateCaptured(List<T> items) {
        if (!items.isEmpty()) {
            T first = items.get(0);
            items.add(first);
        }
    }

    public static void main(String[] args) {
        List<String> words =
                new ArrayList<>(List.of("left", "right"));
        swapAny(words, 0, 1);
        System.out.println("swapped: " + words);

        duplicateFirst(words);
        System.out.println("duplicated: " + words);

        List<Integer> nums =
                new ArrayList<>(List.of(1, 2));
        swapAny(nums, 0, 1);
        System.out.println("numbers: " + nums);
    }
}
```

Chạy:

```bash
javac -Xlint:all WildcardCaptureDemo.java
java WildcardCaptureDemo
```

**Stdout đã kiểm chứng:**

```text
swapped: [right, left]
duplicated: [right, left, right]
numbers: [2, 1]
```

Compiler không đưa cảnh báo khi dùng `-Xlint:all`.

### Tại sao `duplicateFirst` an toàn?

`duplicateFirst(List<?>)` không biết kiểu phần tử là `String`, `Integer` hay một class khác. Helper `duplicateCaptured(List<T>)` lấy một phần tử `T` từ **chính danh sách ấy** và thêm lại **cùng phần tử ấy**. Nó không bịa ra giá trị mới có kiểu không xác định.

Hợp đồng public vẫn không cho caller thêm một `Object` tùy tiện, nhưng implementation có thể dùng capture conversion để thực hiện **các thao tác nội bộ nhất quán**.

Bản thân generic capture không làm mutable list trở thành immutable hoặc ngược lại. Nếu `items` là list bất biến tạo bởi `List.of`, `set`/`add` có thể ném `UnsupportedOperationException`. Ví dụ dùng `new ArrayList<>(...)` để những thao tác đó hợp lệ.

Ngoài ra, `swapAny` cần index hợp lệ; index ngoài phạm vi có thể gây `IndexOutOfBoundsException`. Đây là điều kiện thông thường của list operations, không phải lỗi generics.

### Có cần tự viết swap helper trong sản phẩm?

Thư viện chuẩn đã có `Collections.swap(List<?>, int, int)`, nên ví dụ ở đây nhằm **minh họa capture**. Trong code sản phẩm, cân nhắc API chuẩn khi phù hợp; không tự duy trì utility lặp lại nếu không có yêu cầu riêng.

## 11. Ngoại lệ thứ hai: `T` chỉ xuất hiện trong return type vẫn có ích

Một generic factory có thể **không nhận bất kỳ tham số nào liên quan `T`** nhưng vẫn mang type parameter cho caller suy luận từ kiểu đích:

```java
static <T> List<T> emptyTyped() {
    return List.of();
}
```

Ví dụ:

```java
List<String> words = emptyTyped();
List<Integer> numbers = MyApi.<Integer>emptyTyped();
```

Dòng thứ hai là ví dụ minh họa cần thay `MyApi` bằng class có khai báo `emptyTyped`.

Không thể đơn giản thay return type bằng `List<?>` mà giữ nguyên công dụng:

```java
// List<String> names = someMethodReturningListWildcard();
```

`List<?>` không thể gán trực tiếp vào `List<String>` khi chưa có bằng chứng ràng buộc kiểu, trong khi `List<T>` của generic factory có thể được compiler chọn từ target type.

Ở factory **không lưu phần tử**, như `List.of()`, việc tạo một collection rỗng có thể an toàn cho mọi `T`. Đây là lý do thư viện chuẩn có các generic factories kiểu như `Collections.emptyList()`.

**Giới hạn cần hiểu:** “`T` chỉ trong return type” không cho phép một implementation tự tạo một object `T` tùy ý mà không có nguồn dữ liệu hoặc factory đáng tin. Một method:

```java
// Không được giả lập an toàn bằng unchecked cast:
// static <T> T magic() { return (T) new Object(); }
```

có thể tạo hợp đồng sai và gây `ClassCastException` ở caller. Chỉ dùng return-only generic khi implementation có căn cứ bảo toàn contract (ví dụ danh sách rỗng, dữ liệu được kiểm tra hoặc nguồn kiểu hợp lệ).

## 12. Chương trình C — Return-only generic, factory và self-bound

Tạo tệp **`ReturnOnlyTypeDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

public class ReturnOnlyTypeDemo {
    static <T> List<T> emptyTyped() {
        return List.of();
    }

    static <T> T fromFactory(Supplier<? extends T> factory) {
        return factory.get();
    }

    static <T extends Comparable<? super T>> T minimum(
            List<? extends T> source) {
        if (source.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }

        T best = source.get(0);
        for (T candidate : source) {
            if (candidate.compareTo(best) < 0) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        List<String> names = emptyTyped();
        List<Integer> ids =
                ReturnOnlyTypeDemo.<Integer>emptyTyped();

        System.out.println("empty strings: " + names);
        System.out.println("empty integers: " + ids);
        System.out.println("library empty: "
                + Collections.<String>emptyList());

        String message = fromFactory(() -> "ready");
        System.out.println("factory: " + message);
        System.out.println("minimum: "
                + minimum(List.of(5, 2, 9)));
    }
}
```

Chạy:

```bash
javac -Xlint:all ReturnOnlyTypeDemo.java
java ReturnOnlyTypeDemo
```

**Stdout đã kiểm chứng:**

```text
empty strings: []
empty integers: []
library empty: []
factory: ready
minimum: 2
```

Chương trình được biên dịch bằng `-Xlint:all` không có cảnh báo.

### Ba lý do khác nhau khiến `T` cần thiết

1. **`emptyTyped()`**: thông qua target typing, caller nhận được `List<String>`, `List<Integer>`, v.v. một cách type-safe vì list rỗng không mang phần tử sai kiểu. Type variable ở đây không liên kết với input nhưng vẫn biểu diễn output contract có ích.
2. **`fromFactory(Supplier<? extends T>)`**: ràng buộc kiểu do factory sản xuất với kiểu giá trị trả về. Tồn tại quan hệ callback output → method output.
3. **`minimum`**: dùng bound `T extends Comparable<? super T>` để bảo đảm có thể so sánh các `T`, đồng thời giữ kiểu phần tử ở kết quả. Không thể chỉ thay return type bằng `Object` mà giữ được lời hứa kiểu gốc.

**Quy tắc rút ra:** Không đếm số lần `T` trong text một cách máy móc. Hãy hỏi “type variable này đang chứng minh điều gì cho caller hoặc cho body?”

## 13. Một type parameter được dùng trong bound cũng có thể mang hợp đồng quan trọng

Ví dụ:

```java
static <T extends Comparable<? super T>> T minimum(
        List<? extends T> source)
```

`Comparable<? super T>` cho phép các giá trị `T` tự so sánh một cách hợp lệ với `T` qua một kiểu đối số thích hợp của `Comparable`.

Nếu thay return bằng `Comparable<?>` hoặc `Object`, caller mất kiểu phần tử cụ thể. Nếu xóa ràng buộc `Comparable`, compiler không còn biết `compareTo` dùng được.

Điều này minh họa một lý do khác để giữ type parameter: **giới hạn hành vi/capability của các giá trị và mối quan hệ kiểu giữa chúng**.

Tuy nhiên, cũng không nên đưa `<T extends Comparable<? super T>>` vào một method chỉ `System.out.println(value)` khi không sử dụng khả năng so sánh. Bound có ý nghĩa khi API hoặc body **thực sự cần** những thao tác mà nó hứa.

## 14. Khi nào cần `? extends`, khi nào cần `? super`?

PECS — *Producer Extends, Consumer Super* — là gợi ý xác định wildcard theo hướng dữ liệu:

| Vị trí | Mục đích | Chữ ký thường phù hợp |
| --- | --- | --- |
| Nguồn chỉ đọc các giá trị kiểu `T` | Producer | `Collection<? extends T>` |
| Đích nhận các giá trị kiểu `T` | Consumer | `Collection<? super T>` |
| Callback nhận `T` | Consumer of T | `Predicate<? super T>`, `Consumer<? super T>` |
| Callback trả các giá trị dùng như `R` | Producer of R | `Function<? super T, ? extends R>` |
| Chỉ duyệt phần tử dưới dạng Object | Không cần đặt tên element type | `Collection<?>` |
| Cần ràng buộc cùng element type ở nhiều vị trí | Quan hệ tên `T` | Generic method với `<T>` |

Đừng thay **bất cứ** `List<T>` nào bằng `List<?>` chỉ vì nó ngắn hơn. Nếu method cần **thêm một giá trị `T`**, hoặc truyền phần tử từ một nguồn sang đích có loại tương thích, tên `T` có thể rất quan trọng.

Và ngược lại: `<T>` không phải một “điểm cộng” về mức độ generic nếu nó không chứng minh quan hệ nào. Một chữ ký `List<?>` dễ đọc đôi khi **mạnh hơn về thiết kế**, vì nó không để lộ một type variable không cần thiết.

## 15. Rủi ro khi đổi sang `List<Object>` hoặc raw `List`

Hai cách viết sai mục tiêu thường thấy:

```java
static void print(List<Object> source)
```

và:

```java
static void print(List source)
```

Dạng `List<Object>` không nhận một biến `List<String>` do invariance. Dạng raw `List` bỏ type arguments, có thể kéo theo `rawtypes` warnings và mở đường cho unchecked operations trong code phức tạp.

Dạng phù hợp cho việc chỉ đọc:

```java
static void print(List<?> source)
```

vừa chấp nhận nhiều element types, vừa giữ compiler kiểm tra giới hạn được phép đối với dữ liệu.

Khi cần một loại phần tử cụ thể để đọc, ví dụ `Number`, chọn `List<? extends Number>` thay vì raw `List` cộng cast bằng tay. Khi cần các elements chính xác là `String`, chữ ký `List<String>` vẫn có thể là hợp đồng đúng: không phải API nào cũng nên dùng wildcard.

## 16. Negative tests: compiler phải từ chối những cách sử dụng sai

Tạo tệp **`InvalidApiSignatures.java`**. Tệp này **cố ý không biên dịch**:

```java
import java.util.List;

public class InvalidApiSignatures {
    static void use(List<?> items) {
        items.add("bad");
    }

    static void assign(List<String> names) {
        List<Object> objects = names;
    }

    static <T> void wronglySet(
            List<T> items, Object replacement) {
        items.set(0, replacement);
    }
}
```

Chạy:

```bash
javac InvalidApiSignatures.java
```

Với Java compiler được dùng để kiểm chứng, ba lỗi liên quan:

```text
error: incompatible types: String cannot be converted to CAP#1
error: incompatible types: List<String> cannot be converted to List<Object>
error: incompatible types: Object cannot be converted to T
3 errors
```

**Phân tích:**

1. `items.add("bad")` qua `List<?>`: compiler không biết kiểu element thực và không thể bảo đảm chuỗi này được phép thêm.
2. `List<Object> objects = names`: generic invariance ngăn phép gán; dù `String` là subtype của `Object`, hai kiểu list không có quan hệ ấy.
3. `items.set(0,replacement)`: `Object` tùy ý không bảo đảm là `T`. Một method đặt tên `T` vẫn không cho phép ghi bừa dữ liệu sai kiểu.

**Điều cần nhớ:** việc bỏ một type variable thừa không phải là nới mọi kiểm tra. Wildcard vẫn giữ các ràng buộc an toàn và compiler từ chối thao tác mà dữ liệu nguồn không chứng minh được.

## 17. Một cách nhìn khác: Type variable tạo “phương trình kiểu”

Bạn có thể mô hình hóa một số hợp đồng như các phương trình:

```text
identity:
    Input = T
    Output = T

repeat:
    Input = T
    Output elements = T

append:
    Source value = T
    Destination accepts any supertype of T

countIf:
    Source supplies T
    Predicate accepts any supertype of T

printValues:
    Source supplies some unknown element type
    Output = void
    No connection requiring a named T

sum:
    Source supplies subtypes of Number
    Output = primitive double
    No connection requiring original subtype T
```

Nếu việc **đặt tên** một loại có thể thay bằng một mô tả hướng dữ liệu đơn giản mà không mất thông tin caller cần, type parameter đó có thể không đáng có trong public signature.

Nếu việc loại bỏ tên kiểu làm mất khả năng ràng buộc hai vị trí, làm yếu kiểu trả về, hoặc phá thao tác cần cùng element type ở implementation, giữ type parameter là có cơ sở.

## 18. Vấn đề public API và implementation detail

Một method public thường nên thể hiện **ít chi tiết nội bộ nhất**, miễn vẫn đủ contract:

```java
public static void process(List<?> input)
```

đủ nếu chỉ duyệt và không cần giữ tên element type.

Ở implementation nội bộ, một helper generic riêng có thể cần cho capture:

```java
private static <T> void processCaptured(List<T> input)
```

Đây không phải mâu thuẫn: **public contract** và **implementation algorithm** có mức độ biểu đạt khác nhau.

Lợi ích của API public tối giản:

- Reader không phải đi tìm “`T` ràng buộc cái gì?” nếu thực ra nó không có nhiệm vụ ấy.
- Generic inference ít điểm cần xét hơn.
- Javadoc tập trung vào điều caller thật sự có thể bảo đảm.
- Hạn chế việc lộ một tham số kiểu vô nghĩa như một phần của API contract.

Nhưng public API không nên giản lược tới mức caller mất generic result hoặc cross-parameter relationship. Chữ ký ngắn nhất không phải lúc nào cũng là chữ ký tốt nhất.

## 19. Cẩn thận với refactor trên API đã phát hành

Khi refactor một method:

```java
public static <T> void printValues(List<T> values)
```

thành:

```java
public static void printValues(List<?> values)
```

sự thay đổi có thể giữ **erased JVM descriptor** tương đương:

```text
(Ljava/util/List;)V
```

Nhưng **không nên suy từ cùng descriptor rằng việc đổi public API luôn vô hại**. Có nhiều tầng tương thích:

- **Source compatibility:** Một số overload resolution, method references, type inference hoặc source-level declarations có thể phụ thuộc vào generic form cũ.
- **Binary compatibility:** Ở trường hợp đơn giản, cùng erased descriptor có thể giúp code đã biên dịch tiếp tục liên kết, nhưng phải xét toàn bộ signature, return type, inheritance và bridge methods.
- **Reflection metadata:** `getGenericParameterTypes()` và generic `Signature` thay đổi giữa `List<T>` và `List<?>`. Framework dùng reflection có thể quan sát khác biệt.
- **Override/overload:** Khi thay chữ ký trong hierarchy generic, cần kiểm tra override rules và name clash sau erasure.
- **Documentation/semantic contract:** Người dùng API có thể hiểu type parameter cũ như một lời hứa về quan hệ kiểu dù implementation chưa tận dụng.

Với thư viện public, hãy biên dịch **downstream callers** và chạy compatibility tests trước khi thay chữ ký. Đừng đổi chỉ vì IDE báo “type parameter used once” nếu API có nhiều người dùng.

### Hai overload không thể chỉ khác wildcard/generic parameter cùng erasure

Không thể định nghĩa cùng class hai method chỉ khác `List<T>` và `List<?>` với cùng tên/tham số còn lại, vì erasure đều tương ứng `List`. Ví dụ về thiết kế **không hợp lệ**:

```java
// Không được cùng tồn tại trong một class:
// static <T> void process(List<T> data) {}
// static void process(List<?> data) {}
```

Compiler sẽ báo name clash do cùng erasure. Wildcard không tạo một overload runtime khác.

## 20. Quan sát erased signature bằng `javap`

Sau khi biên dịch `ApiSignatureDemo.java`:

```bash
javap -p -s ApiSignatureDemo
```

Trích từ bản chạy đã kiểm chứng:

```text
static void printValues(java.util.List<?>);
  descriptor: (Ljava/util/List;)V

static boolean containsNull(java.util.List<?>);
  descriptor: (Ljava/util/List;)Z

static double sum(java.util.List<? extends java.lang.Number>);
  descriptor: (Ljava/util/List;)D

static <T> long countIf(
    java.util.List<? extends T>,
    java.util.function.Predicate<? super T>);
  descriptor: (Ljava/util/List;Ljava/util/function/Predicate;)J

static <T> void append(java.util.List<? super T>, T);
  descriptor: (Ljava/util/List;Ljava/lang/Object;)V

static <T> java.util.List<T> repeat(T, int);
  descriptor: (Ljava/lang/Object;I)Ljava/util/List;
```

Tại bytecode, các generic types và wildcards trong method descriptors dùng erased types như `List`, `Predicate`, `Object`. Metadata generic `Signature` có thể giữ `T`/`?` để compiler và reflection xem khai báo.

**Vì vậy:** cùng erased descriptor **không** có nghĩa các source-level generic contracts tương đương. Compiler vẫn áp dụng generic type checking ở source. Những ràng buộc có ích ở `countIf`, `append` và `repeat` vẫn quan trọng dù bytecode không tạo specialized method cho từng `T`.

## 21. Những câu hỏi code review nên hỏi

Khi thấy một method khai báo `<T>`, hãy kiểm tra theo thứ tự:

1. `T` xuất hiện ở **những vị trí nào trong chữ ký**? Một input, nhiều inputs, return, callback, bound?
2. Caller có nhận lại một giá trị hoặc collection mang kiểu **suy luận từ input** không?
3. `T` có ràng buộc một **producer** với một **consumer** không?
4. Body có cần **giữ cùng element type** để đọc rồi ghi lại vào cùng container không (wildcard capture)?
5. Nếu bỏ `T`, compiler còn bảo đảm được điều caller cần không?
6. Nếu chỉ đọc như `Object`, có thể dùng `List<?>` hoặc `Object` rõ ràng hơn không?
7. Nếu chỉ cần upper bound `Number`, có thể dùng `? extends Number` mà không lộ `T` không?
8. Nếu method trả generic empty/factory value, có cần `T` để target typing không?
9. Có overload/override, Java reflection hay framework nào phụ thuộc metadata cũ không?
10. Thay đổi đó sẽ ảnh hưởng code caller, binary descriptors hay generic `Signature` ở mức nào?

**Không có quy tắc “`T` xuất hiện đúng hai lần thì luôn hợp lệ”.** Một `T` xuất hiện nhiều lần nhưng không ràng buộc có ích vẫn có thể là dấu hiệu thiết kế khó hiểu. Ngược lại, helper capture có một `T` trên public-facing signature nhưng body cần nó.

## 22. Những sai lầm dễ mắc

**Sai 1 — “Hễ có `<T>` là API type-safe hơn.”** Generic type variable không tự thêm bảo đảm nếu không liên kết điều gì quan trọng. `print(List<?>)` có thể biểu đạt contract chính xác và rõ ràng hơn `<T> print(List<T>)`.

**Sai 2 — “`T` chỉ xuất hiện một lần là lỗi compile.”** Không đúng; nhiều chữ ký ấy hoàn toàn hợp lệ. Đây là vấn đề thiết kế và tính dễ đọc, không phải một quy tắc cú pháp.

**Sai 3 — “Tất cả `<T>` một lần nên thay bằng `?`.”** Không đúng vì wildcard capture helpers và generic factories trả kiểu từ target context là những trường hợp đáng giữ.

**Sai 4 — “Thay `List<T>` bằng `List<Object>` là đơn giản nhất.”** Có thể phá khả năng nhận `List<String>` vì Java generics invariant. Với input chỉ đọc, `List<?>` hoặc `List<? extends Bound>` thường phù hợp hơn.

**Sai 5 — “`List<?>` là immutable.”** Nó không cho thêm phần tử non-null không rõ kiểu qua tham chiếu ấy, nhưng một list mutable vẫn có thể bị xóa phần tử/hoán đổi thông qua capture hoặc các operation khác.

**Sai 6 — “Nếu method không trả `T`, `<T>` chắc chắn không cần.”** `countIf`/ `append` vẫn cần `T` để ràng buộc các tham số, dù return là `long` hoặc `void`.

**Sai 7 — “Một factory `<T> List<T> empty()` là thừa vì không nhận input.”** Không đúng: nó có thể cung cấp một typed empty list từ ngữ cảnh đích, giữ khả năng `List<String> x = empty()`.

**Sai 8 — “Wildcard capture helper là bất hợp lý vì T chỉ ở `List<T>`.”** Helper có thể cần `T` trong body để ghi lại giá trị đọc từ cùng danh sách mà không dùng unchecked casts.

**Sai 9 — “`? extends T` cho phép thêm T bất kỳ.”** Không. Khi một list sản xuất subtype của `T`, compiler không biết subtype thực để cho thêm một `T` tùy ý. Dùng `? super T` khi danh sách là destination nhận `T`.

**Sai 10 — “Dùng raw types để tránh vấn đề inference.”** Raw types xóa ràng buộc generic, dẫn đến cảnh báo unchecked và có thể gây `ClassCastException` muộn. Hãy sửa chữ ký đúng vai trò dữ liệu thay vì bỏ generic checks.

**Sai 11 — “Mọi refactor generic/wildcard giữ nguyên erased descriptor đều tương thích hoàn toàn.”** Không đúng ở mọi ngữ cảnh; generic reflection, source-level inference, hierarchy và contract có thể thay đổi. Cần compatibility review.

**Sai 12 — “Một biến tên T chứng minh input thuộc một runtime class T riêng.”** Type erasure khiến các kiểu generic không có specialized runtime class theo mỗi type argument. Type parameter biểu đạt ràng buộc compile-time.

## 23. Bài tập và đáp án

### Bài 1 — Chọn chữ ký khi chỉ hiển thị dữ liệu

API chỉ duyệt và in `List<E>`, không dùng quan hệ với kết quả hay tham số nào khác. Chọn:

```java
static <T> void show(List<T> xs)
static void show(List<?> xs)
static void show(List<Object> xs)
```

**Đáp án:** `show(List<?>)` thường rõ nhất. `List<Object>` quá hạn chế với `List<String>`/ `List<Integer>`; `<T>` không đóng góp quan hệ quan trọng trong tình huống này.

### Bài 2 — Khi nào cần ràng buộc input/output?

```java
static <T> T identity(T x) { return x; }
```

Có nên thay return thành `Object` không?

**Đáp án:** không nếu muốn caller giữ kiểu suy luận từ `x`. `T` liên kết tham số và kết quả; đổi thành `Object` làm yếu static contract.

### Bài 3 — Cần `T` dù return void

```java
static <T> void append(List<? super T> dst, T value)
```

`T` có thật sự cần không?

**Đáp án:** có. Nó ràng buộc loại giá trị đưa vào với khả năng chấp nhận của destination list. Không thể thay `dst` thành `List<?>` rồi thêm `value` non-null tùy ý.

### Bài 4 — Upper bound chỉ để đọc

Method cộng `doubleValue()` của các phần tử, không trả dữ liệu có kiểu `T`. So sánh:

```java
<T extends Number> double sum(List<T> values)
double sum(List<? extends Number> values)
```

**Đáp án:** phương án thứ hai thường biểu đạt đúng nhu cầu với ít type variable hơn, đồng thời chấp nhận lists của các subtype `Number`.

### Bài 5 — Ngoại lệ capture

Vì sao `private static <T> void swapCaptured(List<T> list,...)` có ích khi public method nhận `List<?>`?

**Đáp án:** helper dùng `T` để giữ nhất quán kiểu phần tử được lấy ra và được ghi lại vào **cùng list**; wildcard capture cung cấp một tên cho unknown element type ở một lời gọi.

### Bài 6 — Return-only factory

`static <T> List<T> empty()` không nhận `T` trong input. Có nên thay bằng `List<?>` không?

**Đáp án:** không nếu muốn `List<String> names = empty()` được compiler kiểm tra hợp lệ. `T` biểu diễn kiểu element do caller chọn bằng target typing; list rỗng là implementation an toàn.

### Bài 7 — Type inference của predicate

`List<String> data` và `Predicate<CharSequence> predicate`. Vì sao chữ ký `countIf(List<? extends T>,Predicate<? super T>)` chấp nhận cặp đó?

**Đáp án:** `String` có thể dùng như `CharSequence`; predicate nhận một supertype của phần tử nguồn. `T` nối hai tham số để diễn đạt điều kiện này.

### Bài 8 — Overloading sau erasure

Có thể định nghĩa đồng thời hai overload:

```java
<T> void handle(List<T> list)
void handle(List<?> list)
```

không?

**Đáp án:** không, nếu cùng method name và cùng các tham số khác; erased parameter type của cả hai là `List`, gây name clash.

### Bài 9 — Method chỉ đọc `Object`

`static <T> void audit(T event)` chỉ gọi `System.out.println(event)`. Có phương án nào đơn giản hơn?

**Đáp án:** `static void audit(Object event)` thường đủ. Không cần type variable vì không có quan hệ giữa nhiều vị trí kiểu.

### Bài 10 — Ngăn nhầm `List<?>` với `List<Object>`

Tại sao `List<String>` truyền được cho `show(List<?>)` mà không cho `show(List<Object>)`?

**Đáp án:** `?` là wildcard chấp nhận một element type chưa biết theo capture, còn `List<Object>` là tham số hóa cụ thể. Java generics invariant.

### Bài 11 — Binary và reflection

Một method public `<T> void print(List<T>)` đổi thành `void print(List<?>)`. Hai method có thể cùng descriptor erased không? Có thể thay không cần kiểm thử không?

**Đáp án:** descriptor có thể cùng `(Ljava/util/List;)V`, nhưng generic `Signature` và source-level contract khác; các overload/inheritance/framework có thể chịu ảnh hưởng. Cần kiểm tra downstream callers và compatibility.

### Bài 12 — Thiết kế một transform API

Bạn cần nhận một list chứa subtype của `T`, chuyển từng phần tử bằng một `Function` nhận `T` hoặc supertype, và trả `List<R>` mà mapper có thể tạo subtype của `R`. Chữ ký nào phù hợp?

```java
static <T, R> List<R> map(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper)
```

**Đáp án:** đây là cách biểu đạt hợp đồng linh hoạt an toàn: source là producer của `T`, mapper consumer của `T`/producer của `R`, và kết quả có element type `R`. Hai type variables cần thiết vì liên kết nhiều vị trí kiểu.

## 24. Checklist thiết kế generic API

- [ ] Tôi có thể giải thích chính xác `T` liên kết những vị trí nào không?
- [ ] Nếu method chỉ quan sát một container bất kỳ, đã cân nhắc `List<?>`?
- [ ] Nếu method chỉ quan sát một subtype của `Number`, đã cân nhắc `? extends Number`?
- [ ] Nếu method chỉ nhận một object mà không trả/so sánh theo cùng kiểu, `Object` có đủ không?
- [ ] Nếu output cần giữ kiểu từ input, tôi có giữ `<T>`?
- [ ] Nếu cần quan hệ producer/consumer, tôi có chọn đúng `? extends T`/`? super T`?
- [ ] Nếu cần ghi lại phần tử cùng list chưa biết kiểu, tôi có dùng helper capture thay unchecked cast?
- [ ] Nếu generic factory trả collection rỗng, tôi có giữ typed output có ích cho caller?
- [ ] Nếu có bound `Comparable<? super T>`, API thật sự sử dụng khả năng so sánh không?
- [ ] Có tránh được raw types và cast không thể chứng minh không?
- [ ] Tôi có kiểm chứng cả nguồn subtype và callback supertype bằng `javac`?
- [ ] Nếu là API đã phát hành, tôi đã kiểm tra generic `Signature`, callers, overloads và compatibility?
- [ ] Không xem `List<?>` là immutable hoặc `List<Object>` là cha của `List<String>`.
- [ ] Tôi chỉ làm chữ ký ngắn hơn **khi không mất quan hệ kiểu cần thiết**, không refactor máy móc.

## Kết luận

Một type parameter có tên như `T` đáng dùng khi nó **truyền đạt ràng buộc**: nối input với output, nối source với destination/callback, thể hiện self-bound hoặc cho phép wildcard capture trong implementation. Nếu method chỉ dùng một loại phần tử ở một vị trí mà không cần ràng buộc tiếp, một **wildcard `?`** hoặc supertype cụ thể như `Object`/`Number` thường làm API dễ hiểu hơn.

Vì vậy, **“tránh type parameter chỉ xuất hiện một lần” là quy tắc hướng dẫn, không phải phép thay văn bản**. Luôn xét public contract, thân method, generic return-only factories, capture helpers và compatibility trước khi sửa. Thiết kế tốt không tối đa số lượng `<T>`, cũng không tối thiểu chúng bằng mọi giá — nó biểu diễn **đúng những quan hệ kiểu mà caller cần compiler bảo vệ**.
