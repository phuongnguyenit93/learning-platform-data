# Nhiều tham số kiểu và quan hệ giữa các tham số

## 1. Khái niệm: một kiểu generic có thể mô tả nhiều vai trò

Một đối tượng có thể chứa nhiều thành phần giữ những vai trò khác nhau: khóa và giá trị, yêu cầu và phản hồi, phần tử thứ nhất và phần tử thứ hai. Nếu tất cả đều dùng một tham số kiểu `T`, ta có thể vô tình ép các vai trò ấy về cùng một kiểu khai báo. Nếu dùng `Object`, chương trình lại mất thông tin kiểu cần thiết khi đọc dữ liệu.

Nhiều tham số kiểu cho phép mô tả từng vai trò riêng và chỉ bổ sung quan hệ khi bài toán thực sự cần:

```java
// Khai báo minh họa; chưa phải chương trình chạy độc lập.
final class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() {
        return first;
    }

    B second() {
        return second;
    }
}
```

Trong `Pair<String, Integer>`:

- `A`, `B` là **tham số kiểu** trong khai báo.
- `String`, `Integer` là **đối số kiểu** được truyền vào.
- `first()` trả về `String`, `second()` trả về `Integer` theo góc nhìn của trình biên dịch.
- Vị trí có ý nghĩa: `Pair<String, Integer>` khác `Pair<Integer, String>`.

Các tên `A`, `B`, `K`, `V` là quy ước đặt tên, không phải từ khóa. Tên `K` thường gợi ý khóa, `V` gợi ý giá trị; Java không tự suy ra quan hệ chỉ từ các chữ cái ấy.

Generics xuất hiện từ Java 5 và các nguyên tắc trong bài vẫn dùng được trên Java hiện đại. Chương trình thực hành được viết để biên dịch bằng Java 17 trở lên, không cần thư viện ngoài.

## 2. Vì sao phải khai báo quan hệ rõ ràng?

Xét hợp đồng quen thuộc `Map<K, V>`: `K` mô tả kiểu khóa, `V` mô tả kiểu giá trị. `Map<String, Integer>` có thể ánh xạ tên mặt hàng sang số lượng. Hai vai trò dùng hai kiểu khác nhau; không có yêu cầu `Integer` phải kế thừa `String`.

Hai tham số giúp trình biên dịch kiểm tra việc dùng từng vai trò nhất quán. Tuy nhiên, chúng không tự chứng minh quan hệ nghiệp vụ như “giá trị này thuộc đúng khách hàng có mã khóa này”.

Ví dụ, nếu hai mã khách hàng đều có kiểu `String`, việc truyền nhầm mã vẫn hợp lệ về kiểu Java. Quan hệ về quyền sở hữu, số tiền dương hoặc khóa trùng phải được xử lý bằng mô hình miền và kiểm tra dữ liệu phù hợp.

Trước khi viết API, hãy xác định cần hợp đồng nào:

| Nhu cầu | Cách biểu diễn | Điều được kiểm tra |
| --- | --- | --- |
| Hai vai trò độc lập | `Pair<A, B>` | Mỗi vị trí giữ kiểu đã chọn |
| Hai vị trí dùng cùng kiểu khai báo | `Pair<T, T>` | Cả hai được nhìn qua cùng `T` |
| Kiểu thứ hai có giới hạn là kiểu thứ nhất | `<T, U extends T>` | Đối số của `U` phải thỏa giới hạn `T` |
| Giá trị cung cấp khóa có kiểu tương ứng | `<K, V extends Keyed<K>>` | `V` phải thực hiện hợp đồng `Keyed<K>` |

Các quan hệ này là phần khác nhau của thiết kế, không phải những cách viết thay thế tùy ý.

## 3. Hai tham số độc lập không có nghĩa là hai kiểu bắt buộc khác nhau

Khai báo `Pair<A, B>` không nêu giới hạn tường minh cho `A` và `B`; giới hạn trên mặc định của từng tham số là `Object`. Không có quan hệ kế thừa nào được khai báo giữa chúng.

Các cách dùng sau đều hợp lệ với lớp `Pair` ở trên:

```java
// Các câu lệnh minh họa đặt bên trong một phương thức.
Pair<String, Integer> stock = new Pair<>("Book", 7);
Pair<String, String> names = new Pair<>("Lan", "Mai");
Pair<Number, Integer> amounts = new Pair<>(2.5, 8);
```

`A` và `B` có thể nhận cùng một đối số kiểu hoặc các đối số khác nhau. Với `amounts`, việc `Integer` là kiểu con của `Number` chỉ là một lựa chọn hợp lệ của người dùng; lớp `Pair<A, B>` không yêu cầu điều đó.

Trong phần thân lớp, trình biên dịch không cho phép tùy tiện chuyển `B` thành `A`:

```java
// Minh họa lỗi; đoạn này cố ý không biên dịch.
static <A, B> A wrong(B value) {
    return value;
}
```

Nếu phương thức này hợp lệ, người gọi có thể chọn `A = String`, `B = Integer` và nhận một số nguyên qua kiểu trả về `String`. Vì không có hợp đồng bảo đảm chuyển đổi đó, lỗi được phát hiện khi biên dịch.

Cũng không thể gọi một phương thức đặc thù như `length()` trên `A` chỉ vì một lần sử dụng đã chọn `A = String`. Thân generic phải hợp lệ với mọi đối số kiểu được khai báo cho phép, không chỉ một trường hợp cụ thể.

## 4. Dùng lại cùng một tham số: cùng kiểu nhìn thấy, chưa chắc cùng lớp thực tế

Khi một API thực sự cần cùng kiểu ở nhiều vị trí, dùng lại một tham số kiểu:

```java
// Phương thức minh họa, đặt bên trong một lớp có định nghĩa Pair.
static <T> Pair<T, T> sameType(T first, T second) {
    return new Pair<>(first, second);
}
```

Phương thức có **một** tham số kiểu `T`, dù `T` xuất hiện nhiều lần. Các vị trí đầu vào và đầu ra liên hệ qua cùng tham số đó.

Tuy nhiên, “cùng `T`” không có nghĩa là hai đối tượng phải có cùng kết quả `getClass()`:

```java
// Ví dụ minh họa bên trong một phương thức.
Pair<Number, Number> numbers =
        new Pair<Number, Number>(Integer.valueOf(1), Double.valueOf(2.5));
```

Cả `Integer` lẫn `Double` đều dùng được ở vị trí `Number`. Hai thành phần cùng được nhìn qua kiểu `Number`, nhưng lớp thực tế khác nhau.

Tương tự, suy luận kiểu khi gọi phương thức generic có thể tìm một kiểu chung phù hợp cho các đối số, tùy ngữ cảnh. Đừng dùng chữ ký `sameType(T, T)` để khẳng định rằng người gọi chỉ có thể đưa vào hai đối tượng cùng lớp thực tế.

Nếu cần kiểm tra lớp thực tế hoặc điều kiện nghiệp vụ khác, hãy đặt tên và triển khai điều kiện ấy rõ ràng. Đó là yêu cầu bổ sung, không phải bảo đảm sẵn có của việc lặp lại `T`.

## 5. Quan hệ trực tiếp: tham số sau được giới hạn bởi tham số trước

Khai báo sau biểu diễn một giới hạn giữa hai tham số:

```java
// Phương thức minh họa, đặt bên trong một lớp có định nghĩa Pair.
static <T, U extends T> T secondAsBase(Pair<T, U> pair) {
    return pair.second();
}
```

Đọc từ trái sang phải:

1. Chọn `T`.
2. Chọn `U` sao cho `U` thỏa giới hạn trên `T`.
3. Thành phần thứ hai có kiểu `U`, nên có thể trả về qua kiểu `T`.

Ví dụ, `T = Number`, `U = Integer` là một lựa chọn hợp lệ. `T = Number`, `U = Number` cũng hợp lệ: `extends` ở đây không bắt buộc là kiểu con nghiêm ngặt.

`extends` trong khai báo tham số kiểu biểu diễn giới hạn trên, dùng được cả khi giới hạn là một interface. Không thay bằng `implements`.

Chiều ngược lại không được bảo đảm:

```java
// Minh họa lỗi; đoạn này cố ý không biên dịch.
static <T, U extends T> U wrongDirection(T value) {
    return value;
}
```

Nếu `T` là `Number`, `U` là `Integer`, một `T` vẫn có thể đang trỏ tới `Double`. Có giới hạn `U extends T` chỉ bảo đảm chuyển từ `U` sang `T`; nó không biến mọi `T` thành `U`.

Không dùng phép ép kiểu để che đi thiếu sót trong hợp đồng. Hãy đổi kiểu trả về, thêm bước chuyển đổi có ý nghĩa, hoặc thiết kế lại yêu cầu.

## 6. Quan hệ phụ thuộc: kiểu giá trị gắn với kiểu khóa

Một quan hệ hữu ích hơn trong thiết kế API là: mỗi giá trị biết khóa của chính nó, và khóa ấy phải có kiểu `K`.

```java
// Các khai báo minh họa; chương trình đầy đủ nằm ở phần thực hành.
interface Keyed<K> {
    K key();
}

final class Index<K, V extends Keyed<K>> {
    // Có thể gọi key() trên V và nhận kết quả kiểu K.
}
```

Ở đây:

- `K` là kiểu khóa.
- `V` là kiểu giá trị.
- `V extends Keyed<K>` nối hai vai trò: mọi `V` được chấp nhận phải cung cấp một khóa có kiểu `K`.

Nếu `Product implements Keyed<String>`, thì `Index<String, Product>` hợp lệ. `Index<Integer, Product>` không hợp lệ vì `Product` không thực hiện `Keyed<Integer>`.

Mối liên hệ này cho phép thiết kế `put(V value)` tự lấy khóa từ `value.key()`. Người gọi không cần truyền thêm một khóa rời có thể không khớp với chính đối tượng.

Dù vậy, giới hạn kiểu vẫn không chứng minh rằng khóa duy nhất, ổn định hoặc khác `null`. Chương trình bên dưới kiểm tra `null`; đối tượng `Product` giữ khóa trong trường `final`. Với dữ liệu do hệ thống khác cung cấp, vẫn cần chính sách phù hợp về khóa trùng và tính bất biến.

## 7. Phương thức dùng nhiều tham số có thể biến đổi quan hệ đầu vào–đầu ra

Không phải cứ có nhiều tham số kiểu là cần giới hạn `extends`. Đôi khi quan hệ nằm ở cách dùng lại và đổi vị trí các tham số:

```java
// Phương thức minh họa, đặt bên trong một lớp có định nghĩa Pair.
static <A, B> Pair<B, A> swap(Pair<A, B> source) {
    return new Pair<>(source.second(), source.first());
}
```

Với đầu vào `Pair<String, Integer>`, kết quả có kiểu `Pair<Integer, String>`. `A` và `B` vẫn độc lập, nhưng chữ ký giữ được mối liên hệ chính xác giữa đầu vào và đầu ra.

Một API trả về `Pair<Object, Object>` sẽ làm mất mối liên hệ này. Người gọi phải tự khôi phục thông tin kiểu hoặc ép kiểu, dù phương thức đã biết chính xác thành phần nào được chuyển sang đâu.

Tham số kiểu của phương thức được khai báo trước kiểu trả về: `static <A, B> Pair<B, A> ...`. Phương thức `static` tự khai báo các tham số cần dùng; nó không thể trực tiếp dùng tham số kiểu của một đối tượng thuộc lớp bao ngoài.

Tránh đặt tham số kiểu của phương thức trùng tên tham số của lớp khi chúng không cùng vai trò. Hai chữ `T` ở hai phạm vi có thể là hai biến kiểu khác nhau; tên giống nhau không tạo quan hệ giữa chúng.

## 8. Thực hành: chương trình đầy đủ và kết quả

Lưu nguyên chương trình sau vào `MultipleTypeParametersDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MultipleTypeParametersDemo {
    static final class Pair<A, B> {
        private final A first;
        private final B second;

        Pair(A first, B second) {
            this.first = first;
            this.second = second;
        }

        A first() {
            return first;
        }

        B second() {
            return second;
        }
    }

    interface Keyed<K> {
        K key();
    }

    static final class Product implements Keyed<String> {
        private final String id;
        private final String name;

        Product(String id, String name) {
            this.id = Objects.requireNonNull(id);
            this.name = Objects.requireNonNull(name);
        }

        @Override
        public String key() {
            return id;
        }

        String name() {
            return name;
        }
    }

    static final class Index<K, V extends Keyed<K>> {
        private final Map<K, V> values = new HashMap<>();

        void put(V value) {
            V checked = Objects.requireNonNull(value);
            K key = Objects.requireNonNull(checked.key());
            values.put(key, checked);
        }

        V get(K key) {
            return values.get(key);
        }
    }

    static <A, B> Pair<B, A> swap(Pair<A, B> source) {
        return new Pair<>(source.second(), source.first());
    }

    static <T, U extends T> T secondAsBase(Pair<T, U> pair) {
        return pair.second();
    }

    public static void main(String[] args) {
        Pair<String, Integer> item = new Pair<>("Book", 7);
        System.out.println(item.first() + ":" + item.second());

        Pair<Number, Integer> related = new Pair<>(2.5, 8);
        Number widened = secondAsBase(related);
        System.out.println(widened);

        Index<String, Product> catalog = new Index<>();
        catalog.put(new Product("p-1", "Pencil"));
        Product found = catalog.get("p-1");
        System.out.println(found.name());

        Pair<Integer, String> reversed = swap(item);
        System.out.println(reversed.first() + ":" + reversed.second());

        Pair<Number, Number> common =
                new Pair<Number, Number>(Integer.valueOf(1), Double.valueOf(2.5));
        System.out.println(common.first().getClass().getSimpleName()
                + "/" + common.second().getClass().getSimpleName());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 MultipleTypeParametersDemo.java
java MultipleTypeParametersDemo
```

Stdout chính xác:

```text
Book:7
8
Pencil
7:Book
Integer/Double
```

Giải thích từng kết quả:

1. `item` giữ hai vai trò độc lập: tên kiểu `String` và số lượng kiểu `Integer`.
2. Thành phần thứ hai của `related` là `Integer`; giới hạn `U extends T` cho phép trả về qua `Number`. Giá trị vẫn là số `8`.
3. `catalog.put` lấy khóa `String` trực tiếp từ `Product`; truy vấn khóa đã thêm trả về `Product` mà không cần ép kiểu.
4. `swap` đổi cả thứ tự giá trị lẫn vị trí các đối số kiểu trong kết quả.
5. Hai vị trí cùng khai báo qua `Number` nhưng đang giữ các đối tượng thuộc hai lớp thực tế khác nhau.

`Index` là ví dụ hợp đồng kiểu, chưa phải kho lưu trữ hoàn chỉnh. Việc thêm một giá trị có khóa đã tồn tại thay thế giá trị cũ theo `Map.put`. `get` trả về `null` khi không có khóa; ví dụ biết chắc khóa đã được thêm trước khi gọi `name()`. Khi dùng trong ứng dụng, cần xử lý trường hợp không tìm thấy.

## 9. Những cách dùng cố ý gây lỗi biên dịch

Các đoạn dưới đây dùng các kiểu đã định nghĩa trong chương trình đầy đủ. Chúng là ví dụ lỗi, không chèn đồng thời vào chương trình đang chạy.

### Sai vị trí đối số kiểu

```java
Pair<Integer, String> wrong =
        new Pair<Integer, String>("Book", 7);
```

Constructor cần `Integer` rồi `String`, nhưng nhận `String` rồi `Integer`. Dấu phẩy trong `<A, B>` không làm mất thứ tự.

### Sai quan hệ giữa khóa và giá trị

```java
Index<Integer, Product> wrong = new Index<>();
```

`Product` thực hiện `Keyed<String>`, không thỏa giới hạn `Keyed<Integer>`.

### Không có tính hiệp biến tự động

```java
Pair<String, Integer> narrow = new Pair<>("Book", 7);
Pair<Object, Number> broad = narrow;
```

Dù `String` là kiểu con của `Object` và `Integer` là kiểu con của `Number`, `Pair<String, Integer>` không tự trở thành kiểu con của `Pair<Object, Number>`. Các đối số kiểu của lớp generic trong ví dụ là bất biến (invariant).

Muốn mở rộng cách nhìn để đọc dữ liệu, có thể biểu diễn giới hạn bằng wildcard:

```java
// Minh họa hợp lệ trong một phương thức có biến narrow như trên.
Pair<? extends Object, ? extends Number> view = narrow;
Object first = view.first();
Number second = view.second();
```

Hai wildcard ở hai vị trí không tự nối với nhau bằng một tên chung. Nếu cần diễn đạt quan hệ giữa nhiều vị trí đầu vào–đầu ra, tham số kiểu có tên như trong `swap` thường thể hiện hợp đồng rõ hơn. Việc thiết kế đầy đủ wildcard là một chủ đề riêng.

### Dùng kiểu nguyên thủy làm đối số kiểu

```java
Pair<String, int> wrong;
```

Đối số kiểu phải là kiểu tham chiếu; dùng `Integer` thay cho `int`. Trong ví dụ chạy được, hằng số `7` được boxing thành `Integer` ở vị trí tương ứng.

## 10. Cách lựa chọn hợp đồng và tự kiểm tra

Khi thiết kế một kiểu hoặc phương thức generic:

1. Xác định các vai trò dữ liệu. Nếu chúng thay đổi độc lập, khai báo các tham số độc lập.
2. Chỉ dùng lại cùng một tham số khi cần giữ một kiểu khai báo chung giữa các vị trí.
3. Chỉ thêm giới hạn phụ thuộc khi thuật toán thực sự cần dùng bảo đảm đó, chẳng hạn chuyển `U` sang `T` hoặc gọi `V.key()` để nhận `K`.
4. Theo dõi tham số xuất hiện ở đầu vào và đầu ra. Chữ ký nên giữ được thông tin mà người gọi cần, như `Pair<A, B>` thành `Pair<B, A>`.
5. Tách quan hệ kiểu khỏi quy tắc về giá trị. Hai đối tượng cùng kiểu khóa vẫn có thể chứa khóa sai nghiệp vụ.
6. Giữ tên và số tham số đủ rõ. Nếu API có nhiều chữ cái khó liên hệ với bài toán, cân nhắc dùng tên theo vai trò hoặc một kiểu miền có tên rõ nghĩa.

Bài tập:

- Thay `Product` bằng một kiểu `Invoice implements Keyed<Long>`. Khai báo `Index` tương ứng và giải thích vì sao kiểu khóa phải là `Long`.
- Viết `keepFirst(Pair<T, U>)` với `U extends T`, trả về `T`. Sau đó thử đổi kiểu trả về thành `U` và giải thích lỗi mà không dùng phép ép kiểu.
- Dự đoán kiểu của `swap(swap(item))`. Kiểm tra bằng phép gán vào `Pair<String, Integer>`.
- Tạo `Pair<Number, Number>` giữ `Integer` và `Double`. Giải thích sự khác nhau giữa đối số kiểu được khai báo và lớp thực tế của từng đối tượng.

## Tài liệu đối chiếu

- [Java Language Specification — Type Variables (§4.4)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4): đối chiếu cú pháp khai báo biến kiểu và giới hạn.
- [Java Language Specification — Parameterized Types (§4.5)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5): đối chiếu việc truyền đối số kiểu vào kiểu generic.
- [Java API — Map<K,V>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): ví dụ thư viện chuẩn về hai vai trò khóa–giá trị và hành vi lưu trữ ánh xạ.
