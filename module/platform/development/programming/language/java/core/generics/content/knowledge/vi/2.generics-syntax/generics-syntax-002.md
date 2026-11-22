# Quy ước tên T, E, K, V và cách đặt tên có nghĩa trong Java Generics

Trong Java Generics, `T`, `E`, `K`, `V` là **tên tham số kiểu (type parameters)**, không phải từ khóa của Java và không phải tên những kiểu có sẵn. Chúng là các tên thay thế cho kiểu mà người viết định nghĩa generic class, interface hoặc method chưa biết trước. Đặt tên rõ ràng giúp người đọc nhận ra **vai trò của từng kiểu** ngay tại chữ ký API.

Bài học này tập trung vào cách đọc, khai báo và chọn tên tham số kiểu. Cách đặt tên không đổi cơ chế hoạt động của generics, nhưng ảnh hưởng mạnh đến khả năng hiểu và sử dụng API.

## 1. Phân biệt tên tham số kiểu với đối số kiểu

Xét lớp và cách dùng sau:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

// Khi dùng trong ngữ cảnh có thể khai báo biến:
Box<String> textBox = new Box<>("Hello");
```

- `T` trong `class Box<T>` là **tham số kiểu**: tên được khai báo bởi tác giả lớp, có phạm vi sử dụng trong các phần hợp lệ của định nghĩa lớp.
- `String` trong `Box<String>` là **đối số kiểu (type argument)**: kiểu cụ thể do người dùng lớp cung cấp tại điểm sử dụng.
- Hai chỗ `T` tại trường `value` và phương thức `get()` cùng chỉ một kiểu được chọn cho mỗi cách sử dụng `Box<T>`. Vì thế `Box<String>.get()` có kiểu kết quả `String` tại thời điểm biên dịch.
- Dấu `<>` trong `new Box<>("Hello")` là **diamond operator**: trình biên dịch suy luận đối số kiểu phù hợp từ ngữ cảnh. Nó không phải tên tham số kiểu.

`T` có thể đổi thành `ELEMENT` hoặc một định danh hợp lệ khác mà không thay đổi thuật toán:

```java
class Box<VALUE> {
    private final VALUE value;

    Box(VALUE value) {
        this.value = value;
    }

    VALUE get() {
        return value;
    }
}
```

Hai phiên bản `Box` trên là **hai cách viết thay thế**, không đặt cả hai cùng tên trong cùng một tệp/package để biên dịch. Sự khác biệt nằm ở tên dùng cho người đọc; Java vẫn kiểm tra quan hệ kiểu theo cùng nguyên tắc.

## 2. Ý nghĩa quy ước của T, E, K, V

| Tên | Gợi nghĩa thường gặp | Ngữ cảnh phù hợp | Cách đọc |
|---|---|---|---|
| `T` | **Type** – một kiểu bất kỳ | `Box<T>`, `Optional<T>`, `Comparable<T>` | “kiểu T” |
| `E` | **Element** – kiểu phần tử | `List<E>`, `Set<E>`, `Queue<E>` | “phần tử E” |
| `K` | **Key** – kiểu khóa | `Map<K, V>`, cấu trúc tìm kiếm theo khóa | “khóa K” |
| `V` | **Value** – kiểu giá trị | `Map<K, V>`, giá trị ghép với khóa | “giá trị V” |

Đây là **quy ước đọc hiểu**, không phải luật ngữ pháp hoặc ràng buộc của trình biên dịch. Java không yêu cầu tên `E` chỉ xuất hiện trong collection, `K` chỉ có trong map, hay `V` chỉ chứa giá trị được ghi. Ví dụ `class Container<E>` và `class Container<T>` đều hợp lệ nếu dùng nhất quán. Tuy nhiên, đổi `K` thành `T` và `V` thành `U` ở một map sẽ khiến vai trò khóa/giá trị khó nhìn ra.

Các dạng quen thuộc trong thư viện Java:

```java
List<String> names;          // List<E>: E = String
Set<Integer> uniqueNumbers;  // Set<E>: E = Integer
Map<String, Integer> ages;   // Map<K, V>: K = String, V = Integer
Optional<Double> price;      // Optional<T>: T = Double
```

Đây là những **khai báo biến minh họa**; để chạy riêng cần đặt trong lớp/phương thức và import các kiểu tương ứng. Tên `names`, `ages` là tên biến chứa đối tượng; `E`, `K`, `V` là tên kiểu trong **định nghĩa** của collection.

Một hiểu nhầm phổ biến là `E` viết tắt của *Exception*. Với các collection như `List<E>`, `E` có nghĩa là *Element*. Nếu API đang biểu đạt kiểu ngoại lệ, hãy cân nhắc tên giúp tránh nhầm lẫn với phần tử.

## 3. Những ký hiệu khác và cách mở rộng nhất quán

Bên cạnh bộ bốn cơ bản, một số tên thường thấy:

| Tên | Gợi nghĩa theo ngữ cảnh | Ví dụ |
|---|---|---|
| `S`, `U` | Kiểu thứ hai/thứ ba khi `T` đã được dùng | `<T, U>` cho phép hai kiểu độc lập |
| `R` | **Result/Return** – kiểu kết quả | `Function<T, R>` nhận `T`, trả `R` |
| `L`, `R` | **Left/Right** – thành phần trái/phải | `Pair<L, R>` |
| `N` | **Number** – kiểu số, khi thích hợp | `<N extends Number>` |
| `X` | Một kiểu đặc biệt như kiểu lỗi, tùy API | `<X extends Exception>` trong một số thiết kế |

`R` có thể là *Result* trong `Function<T, R>` nhưng là *Right* trong `Pair<L, R>`. **Ý nghĩa của ký hiệu đến từ hợp đồng API**, không từ một “từ điển bắt buộc” của Java.

Ví dụ đọc `Function<T, R>`: một hàm nhận đầu vào thuộc kiểu `T` và trả đầu ra thuộc kiểu `R`. Với `Function<String, Integer>`, `T = String`, `R = Integer`. `BiFunction<T, U, R>` dùng hai kiểu đầu vào `T` và `U`, kết quả `R`. Còn `Map<K, V>` diễn đạt cặp vai trò *khóa → giá trị*, nên ký hiệu `K` và `V` dễ hiểu hơn `T`, `U`.

Nếu nhiều tham số có **cùng vai trò**, có thể dùng `T`, `U`, `S` một cách nhất quán; nếu chúng có **vai trò khác nhau rõ rệt**, tên theo vai trò sẽ giúp người gọi hiểu nhanh hơn. Không có yêu cầu phải dùng một thứ tự mở rộng duy nhất cho tất cả thư viện.

## 4. Ví dụ Java 17 chạy độc lập: tên thể hiện vai trò

Lưu toàn bộ chương trình sau thành `GenericNamingDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public class GenericNamingDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class Pair<L, R> {
        private final L left;
        private final R right;

        Pair(L left, R right) {
            this.left = left;
            this.right = right;
        }

        L left() {
            return left;
        }

        R right() {
            return right;
        }
    }

    @FunctionalInterface
    interface Converter<INPUT, OUTPUT> {
        OUTPUT convert(INPUT input);
    }

    static <E> E first(List<E> elements) {
        return elements.get(0);
    }

    static <T, R> List<R> transform(List<T> inputs, Function<T, R> mapper) {
        return inputs.stream().map(mapper).toList();
    }

    static <K, V> Map<K, V> oneEntry(K key, V value) {
        Map<K, V> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");
        System.out.println("box: " + box.get());

        System.out.println("first: " + first(List.of(7, 8, 9)));

        List<Integer> lengths = transform(
            List.of("a", "java"),
            String::length
        );
        System.out.println("lengths: " + lengths);

        Map<String, Integer> ages = oneEntry("Ada", 36);
        System.out.println("map: " + ages);

        Pair<String, Integer> pair = new Pair<>("year", 2026);
        System.out.println("pair: " + pair.left() + "=" + pair.right());

        Converter<String, Integer> converter = String::length;
        System.out.println("converter: " + converter.convert("Generics"));
    }
}
```

Chạy:

```bash
javac GenericNamingDemo.java
java GenericNamingDemo
```

Kết quả chuẩn:

```text
box: Java
first: 7
lengths: [1, 4]
map: {Ada=36}
pair: year=2026
converter: 8
```

Phân tích ý nghĩa tên trong từng chữ ký:

1. `Box<T>`: lớp là hộp cho **một kiểu bất kỳ**. Tên `T` ngắn, đủ thông tin vì chỉ có một tham số kiểu và không có vai trò cạnh tranh.
2. `<E> E first(List<E> elements)`: `E` là **kiểu phần tử**. Truyền `List<Integer>` thì kết quả được suy luận là `Integer`. Phương thức giả định danh sách không rỗng; nếu rỗng, `get(0)` ném `IndexOutOfBoundsException`.
3. `<T, R> List<R> transform(List<T> inputs, Function<T, R> mapper)`: `T` là **kiểu đầu vào**, `R` là **kiểu kết quả**. Chuỗi `"java"` được chuyển thành số độ dài `4`; `T` và `R` có thể là hai kiểu khác nhau.
4. `<K, V> Map<K, V> oneEntry(K key, V value)`: `K` luôn nhất quán ở khóa và `V` ở giá trị. Hàm có thể được gọi với `K = String`, `V = Integer`. `LinkedHashMap` bảo toàn thứ tự chèn; kết quả chỉ có một mục nên hiển thị `{Ada=36}`.
5. `Pair<L, R>`: hai thành phần có vai trò **trái** và **phải**, dù không có ý nghĩa khóa–giá trị; ở đây `L, R` rõ hơn `K, V`.
6. `Converter<INPUT, OUTPUT>`: minh họa cách dùng **tên có nghĩa dài hơn** khi hai vai trò đầu vào và đầu ra cần đặc biệt dễ đọc. Cú pháp này hợp lệ; chữ `INPUT` và `OUTPUT` không có nghĩa đặc biệt với trình biên dịch. Trong API nhỏ, `Converter<T, R>` cũng hoàn toàn hợp lý.

Ví dụ trên dùng một `@FunctionalInterface` để minh họa kiểu đầu vào/đầu ra. `String::length` là method reference hợp lệ vì `convert(String)` trả `Integer` nhờ autoboxing từ `int`.

## 5. Khi nào chọn tên một chữ cái, khi nào tên đầy đủ?

**Ưu tiên một chữ cái viết hoa** khi vai trò phổ biến và nhìn là hiểu ngay. Các API kiểu `List<E>`, `Map<K, V>`, `Box<T>`, `Function<T, R>` thường dễ đọc hơn một danh sách tên dài mà không có ích thêm. Đây là phong cách rất phổ biến trong Java Standard Library, đặc biệt ở generic class và method nhỏ.

**Cân nhắc tên mô tả** khi một chữ cái khiến hợp đồng trở nên mơ hồ, nhất là API công khai có nhiều loại dữ liệu mang vai trò khác nhau. Ví dụ một repository có thể được diễn đạt như sau:

```java
interface Repository<ENTITY, ID> {
    ENTITY findById(ID id);
    void save(ENTITY entity);
}
```

Ở đây hai tham số có hai vai trò khác nhau: `ENTITY` là kiểu thực thể mà repository thao tác; `ID` là kiểu định danh để tra cứu. Tên `Repository<T, U>` hợp lệ nhưng chữ ký `U findById(T id)` sẽ khó hiểu và dễ viết nhầm vai trò hơn. Nếu nhóm ưu tiên kiểu tên `EntityT` và `IdT` thì cũng hợp lệ; chọn một quy ước nhất quán và tài liệu hóa API rõ ràng.

**Lưu ý về phong cách:** Java không bắt buộc type parameter phải viết hoa một chữ cái. Những tên như `INPUT`, `OUTPUT`, `ENTITY` là ví dụ hợp lệ để đặt tên có nghĩa; không phải quy ước chuẩn bắt buộc ở mọi codebase. Đừng kéo dài tên chỉ để “mô tả cho đủ”: `<VeryGenericElementType>` hiếm khi rõ hơn `<E>` ở `List`.

Cách chọn thực dụng:

- Nếu chỉ một kiểu bất kỳ: bắt đầu bằng `T`.
- Nếu đang mô tả phần tử một tập hợp: dùng `E`.
- Nếu là khóa và giá trị có vai trò bất đối xứng: dùng `K, V`.
- Nếu đầu vào và đầu ra cần giữ quan hệ nhưng khác vai trò: cân nhắc `T, R` hoặc tên diễn đạt rõ như `INPUT, OUTPUT`.
- Nếu hai mặt trái/phải của cặp không nhất thiết là key/value: dùng `L, R` hoặc tên theo domain.
- Nếu ký hiệu không đủ truyền tải quan hệ ở một API phức tạp: dùng tên dài hơn với quy ước nhất quán của dự án.

## 6. Tên phải nhất quán trong phạm vi khai báo

Một tham số kiểu **được khai báo** trong phần `<...>` và chỉ được dùng ở những vị trí thuộc phạm vi khai báo đó. Ví dụ:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T read() {
        return value;
    }

    static <U> U echo(U input) {
        return input;
    }
}
```

Trong `Holder<T>`, các vị trí `T` ở trường, constructor và `read()` cùng nói về **một tham số kiểu của lớp**. Trong `static <U> U echo(U input)`, `U` là **tham số kiểu riêng của phương thức static**: tên `U` được khai báo ngay trước kiểu trả về và không phụ thuộc vào `T` của một instance `Holder<T>`.

Đoạn sau **không biên dịch** nếu đặt trong một generic class:

```java
static T invalid(T input) {
    return input;
}
```

Lý do: phương thức `static` không được sử dụng trực tiếp tham số kiểu của lớp, vì tham số đó gắn với các cách dùng instance của kiểu generic. Có thể sửa thành `static <T> T valid(T input)`, khai báo một tham số kiểu thuộc chính phương thức. Dù tên trùng `T`, đó là **tham số khác**, nên trong tài liệu giảng dạy nên cân nhắc tên `U` để tránh hiểu nhầm.

Với chữ ký `static <K, V> Map<K, V> oneEntry(K key, V value)`, cả hai tên được khai báo trước kiểu trả về, sau đó dùng nhất quán ở `Map<K, V>` và các tham số. Đổi `V` thành `R` ở một vị trí nhưng không cập nhật chỗ khai báo sẽ gây lỗi biên dịch (không tìm thấy ký hiệu kiểu).

Tên biến thông thường khác tên tham số kiểu. Ví dụ `<K, V> Map<K, V> oneEntry(K key, V value)` dùng `K` và `V` cho **kiểu**, còn `key` và `value` cho **biến dữ liệu**. Tên biến viết camelCase và tên tham số kiểu thường viết chữ hoa để dễ phân biệt.

## 7. Bound không đổi ý nghĩa đặt tên

Generic bound giúp giới hạn kiểu được chấp nhận. Tên thể hiện vai trò, còn `extends` quy định giới hạn:

```java
static <N extends Number> double doubled(N value) {
    return value.doubleValue() * 2;
}

static <T extends Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Đây là hai **đoạn phương thức minh họa**, cần đặt vào trong một class trước khi biên dịch độc lập.

- `N` gợi **number**; bound `extends Number` mới là cơ chế thực sự cho phép `doubleValue()`. Đổi tên thành `T` mà giữ nguyên bound không làm phương thức mất tính an toàn kiểu.
- `T` trong `larger` biểu diễn một kiểu có khả năng so sánh với chính kiểu đó; cùng `T` xuất hiện tại bound, tham số và kết quả để giữ quan hệ.
- `extends` trong generic bound không có nghĩa `N` là một lớp con mới được tạo. Nó chấp nhận đối số kiểu thỏa ràng buộc. `Number` có các subtype như `Integer`, `Double`, không chấp nhận kiểu không phải subtype phù hợp.

Một số API dùng ràng buộc linh hoạt hơn như `<T extends Comparable<? super T>>` khi cần hỗ trợ kiểu so sánh được với một supertype. Cú pháp có thể phức tạp, nhưng tên `T` vẫn giữ vai trò: **kiểu của giá trị cần so sánh**. Không đổi tên sang `K` hoặc `E` nếu chúng không thật sự diễn đạt vai trò.

## 8. Các lỗi đặt tên phổ biến

**Lỗi 1: Lạm dụng `T, U, V` dù có quan hệ khóa–giá trị.** Ví dụ `interface Storage<T, U> { U get(T key); }` hợp lệ, nhưng `Storage<K, V>` rõ hơn cho cấu trúc tra cứu theo khóa. Có thể giữ tên ngắn mà vẫn có ý nghĩa.

**Lỗi 2: Dùng `E` cho cả phần tử lẫn ngoại lệ mà không phân biệt.** `E` trong `List<E>` là element; nếu API có cả kiểu kết quả và kiểu exception, hãy chọn tên không xung đột và giải thích rõ trong Javadoc. Đừng giả định tất cả ký hiệu đều có ý nghĩa cố định ở mọi ngữ cảnh.

**Lỗi 3: Nhầm ký hiệu kiểu với một lớp Java tên `T`.** `T` trong `class Box<T>` là tên được khai báo tại lớp generic, không phải class đã có trong package. Trong một vùng code, đặt tham số kiểu trùng tên với lớp domain có thể gây che khuất tên và làm người đọc khó hiểu; nên tránh.

**Lỗi 4: Viết thường `<t>` theo thói quen đặt tên biến.** Java có thể chấp nhận định danh kiểu như `t`, nhưng quy ước dùng chữ cái in hoa (`T`, `E`...) giúp phân biệt tham số kiểu với biến thường. Tên kiểu và tên biến tuân theo các quy ước đọc khác nhau.

**Lỗi 5: Cùng một ký hiệu nhưng dùng cho hai vai trò lẫn lộn.** Ví dụ `<T> Map<T, T> convert(T key, T value)` ép cả khóa lẫn giá trị thuộc cùng một kiểu dù thiết kế muốn hai kiểu độc lập. Nên dùng `<K, V> Map<K, V> convert(K key, V value)` khi cần cho phép khác kiểu. Đây là **lỗi thiết kế quan hệ kiểu**, không chỉ lỗi thẩm mỹ.

**Lỗi 6: Dùng tên dài làm mờ cấu trúc.** `<ElementTypeOfTheInputList>` có thể khiến method một dòng khó đọc. Với một generic method nhỏ, `<E> E first(List<E> elements)` rõ ràng hơn. Tên dài chỉ có ích khi diễn đạt một ý nghĩa mà tên ngắn không thể hiện được.

**Lỗi 7: Tưởng tên `K`, `V` tự giới hạn kiểu.** `<K, V>` không ngăn truyền `String`, `Integer`, hoặc cùng một kiểu cho cả hai. Chỉ type bounds (nếu có) và các chữ ký API mới giới hạn quan hệ kiểu. `K` không mặc nhiên phải hashable hay `V` phải mutable.

**Lỗi 8: Tưởng đổi tên `T` thành `R` sẽ thay đổi giá trị trả về.** Tên ký hiệu không tạo chuyển đổi kiểu. Một method `<T, R> R convert(T x)` chỉ biên dịch khi thân phương thức thật sự tạo/nhận được `R` phù hợp; không thể đơn giản `return x;` vì không có bảo đảm `T` là `R`.

**Lỗi 9: Quên viết Javadoc cho API generic công khai.** Nếu vai trò khó hiểu, chú thích `@param <T>` là nơi giải thích tham số kiểu. Ví dụ:

```java
/**
 * Lấy phần tử đầu tiên của danh sách không rỗng.
 *
 * @param <E> kiểu phần tử trong danh sách
 * @param items danh sách đầu vào
 * @return phần tử tại vị trí 0
 * @throws IndexOutOfBoundsException nếu danh sách rỗng
 */
static <E> E first(List<E> items) {
    return items.get(0);
}
```

Đoạn Javadoc minh họa cho phương thức có thể đặt trong class và cần import `java.util.List`. Khác với `@param items` mô tả biến phương thức, cú pháp **`@param <E>`** mô tả *tham số kiểu*.

## 9. Câu hỏi tự kiểm tra

1. Trong `Map<String, Long>`, `K` và `V` ở định nghĩa `Map<K, V>` ứng với gì? **Đáp án:** `K = String` cho khóa và `V = Long` cho giá trị.
2. `List<E>` có bắt buộc dùng chữ `E` không? **Không.** Đó là quy ước của Java Collections; tên khác vẫn hợp lệ nếu khai báo và dùng nhất quán.
3. Trong `<T, R> R transform(T input, Function<T, R> f)`, vì sao có hai tham số kiểu? **Đáp án:** `T` mô tả kiểu đầu vào, `R` mô tả kiểu đầu ra; chúng có thể khác nhau.
4. Trong `Pair<L, R>`, có nên mặc định giải thích `R` là Result không? **Không.** Với cặp trái–phải, `R` thường là Right; cần đọc hợp đồng API.
5. Tên `<INPUT, OUTPUT>` có hợp lệ không? **Có.** Compiler không yêu cầu đúng một chữ cái, nhưng nhóm dự án nên thống nhất phong cách và chỉ dùng tên dài khi cần rõ nghĩa.
6. Đổi `static <E> E first(List<E> xs)` thành `static <T> T first(List<T> xs)` có đổi hành vi không? **Không**, nếu chỉ thay tên tham số kiểu nhất quán; cả hai mô tả cùng quan hệ kiểu.
7. `<K, V>` có tự buộc `K` và `V` khác nhau không? **Không.** `Map<String, String>` vẫn hợp lệ.
8. `class Box<T>` có thể viết `static T current;` không? **Không.** Thành viên static không được tham chiếu trực tiếp tham số kiểu của lớp; khai báo static generic method với tham số kiểu riêng nếu cần.

Khi đọc hoặc viết generic API, luôn hỏi ba điều: **Ký hiệu này đại diện cho đối tượng nào hoặc vai trò nào? Nó được khai báo ở phạm vi nào? Các vị trí lặp lại của ký hiệu có đang mô tả đúng cùng một kiểu không?** Nếu trả lời rõ cả ba, cách đặt tên thường đủ tốt; nếu còn mơ hồ, hãy chọn ký hiệu phù hợp hơn hoặc diễn giải rõ bằng tên và Javadoc.
