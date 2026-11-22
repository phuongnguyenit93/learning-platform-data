# Chỉ định đối số kiểu tường minh khi gọi phương thức

## 1. Khái niệm: cung cấp kiểu cho một lời gọi generic

Một phương thức generic tự khai báo tham số kiểu:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <T> T identity(T value) {
    return value;
}
```

Ở khai báo này, `T` là một tên đại diện. Khi gọi phương thức, trình biên dịch thường suy luận đối số kiểu từ đối số giá trị và ngữ cảnh sử dụng.

Nếu phương thức nằm trong lớp `Tools`, ta có thể gọi:

```java
// Các câu lệnh minh họa.
String inferred = Tools.identity("Java");
String explicit = Tools.<String>identity("Java");
```

Lời gọi thứ hai **chỉ định đối số kiểu tường minh**: người viết cung cấp `String` thay vì để trình biên dịch tự chọn cho tham số `T`. Cách viết này cũng thường được gọi là **type witness**.

`<String>` ở đây thuộc **phương thức `identity`**, không phải thuộc lớp `Tools` và không phải một phép ép kiểu.

Các nguyên tắc trong bài áp dụng cho Java hiện đại. Chương trình thực hành dùng Java 17 trở lên; không dựa vào những hạn chế suy luận kiểu của các phiên bản Java cũ.

## 2. Vì sao có lúc muốn chỉ định kiểu?

Suy luận kiểu giúp mã ngắn gọn và thường là lựa chọn phù hợp. Chỉ định tường minh hữu ích khi muốn:

- Làm rõ một quyết định kiểu có ý nghĩa với người đọc.
- Chọn một kiểu bao quát hơn kiểu cụ thể của giá trị đầu vào.
- Kiểm soát kiểu của một biểu thức khi ngữ cảnh không cung cấp kiểu đích mong muốn.
- Kiểm tra xem một lời gọi có thực sự thỏa hợp đồng với một đối số kiểu cụ thể hay không.

Không cần thêm đối số kiểu vào mọi lời gọi generic. Nếu suy luận đã đúng và mã rõ ràng, việc lặp lại thông tin kiểu có thể chỉ làm câu lệnh dài hơn.

Cũng không nên dùng type witness như cách che lỗi thiết kế. Nó vẫn phải được trình biên dịch kiểm tra với đầy đủ tham số giá trị, giới hạn kiểu và quy tắc chọn phương thức.

## 3. Vị trí cú pháp: ngay trước tên phương thức

### 3.1. Phương thức static

```java
// Mẫu lời gọi minh họa.
Tools.<String>identity("Java");
```

Đọc thành:

1. Tìm thành viên trên `Tools`.
2. Cung cấp đối số kiểu `String`.
3. Gọi phương thức `identity` với đối số giá trị `"Java"`.

Đối số kiểu nằm sau dấu chấm và trước tên phương thức. Các kiểu được truyền bằng tên kiểu; các giá trị vẫn nằm trong dấu ngoặc tròn.

### 3.2. Phương thức đối tượng

```java
// Khai báo minh họa.
class Echo {
    <U> U echo(U value) {
        return value;
    }
}
```

Cách gọi:

```java
// Các câu lệnh minh họa.
Echo receiver = new Echo();
String word = receiver.<String>echo("Java");
Integer number = receiver.<Integer>echo(7);
```

Một đối tượng nhận lời gọi không làm phương thức mất khả năng generic. Hai lần gọi có thể cung cấp hai đối số kiểu khác nhau cho `U`.

Bên trong một phương thức đối tượng, cũng có thể viết `this.<String>echo("Java")` để gọi phương thức generic của chính đối tượng.

### 3.3. Phân biệt đối số kiểu của lớp và của phương thức

```java
// Minh họa các vị trí cú pháp khác nhau.
Box<String> box = new Box<>();
String result = box.<String>convert("Java");
```

Đoạn này chỉ minh họa vị trí cú pháp; nó cần một lớp `Box` có constructor và phương thức `convert` tương ứng để biên dịch.

`Box<String>` truyền kiểu cho lớp. `box.<String>convert(...)` truyền kiểu cho phương thức. Việc hai vị trí cùng dùng `String` trong ví dụ không khiến hai danh sách tham số trở thành một.

Không viết `Tools<String>.identity(...)` để truyền đối số kiểu cho một phương thức tĩnh. Đó không phải vị trí của đối số kiểu phương thức.

## 4. Nhiều tham số kiểu: đúng số lượng và đúng thứ tự

Xét một phương thức có hai tham số kiểu:

```java
// Phương thức minh họa; cần import java.util.Map.
static <K, V> Map<K, V> entry(K key, V value) {
    return Map.of(key, value);
}
```

Nếu phương thức nằm trong `Tools`:

```java
// Các câu lệnh minh họa.
Map<Number, CharSequence> item =
        Tools.<Number, CharSequence>entry(1, "one");
```

Danh sách tường minh được ghép theo thứ tự khai báo:

- `K = Number`.
- `V = CharSequence`.

Giá trị khóa `1` và giá trị `"one"` phải tương thích với hai kiểu đã chọn. `Map.of` trong ví dụ cần khóa và giá trị khác `null`; type witness không thay đổi hợp đồng đó.

Với chính phương thức `entry` này và không có overload khác, chỉ truyền một kiểu như `Tools.<Number>entry(...)` là không đủ. Java không có cú pháp truyền một nửa danh sách rồi để trống phần còn lại bằng dấu phẩy.

Nếu bỏ toàn bộ danh sách tường minh, trình biên dịch có thể suy luận các tham số:

```java
// Câu lệnh minh họa.
Map<Integer, String> item = Tools.entry(1, "one");
```

Chọn suy luận toàn bộ hoặc cung cấp danh sách hợp lệ cho phương thức đang được áp dụng; không dùng `<>` rỗng trước tên phương thức như diamond của constructor.

## 5. Kiểu đích và var: tránh áp dụng lời khuyên từ Java cũ

Một ví dụ thư viện chuẩn:

```java
// Minh họa; cần import Collections và List.
List<String> inferred = Collections.emptyList();
List<String> explicit = Collections.<String>emptyList();
```

Trên Java hiện đại, cả hai đều hợp lệ. Kiểu đích `List<String>` giúp lời gọi đầu tiên suy luận đúng. Không cần khẳng định rằng “phương thức không có đối số thì luôn phải chỉ định kiểu”.

Tuy nhiên, khi dùng `var`, biến không cung cấp trước một kiểu đích như `List<Number>`. Xét phương thức tạo danh sách thay đổi được:

```java
// Phương thức minh họa, đặt trong Tools.
// Cần import java.util.ArrayList và java.util.List.
static <T> List<T> one(T value) {
    List<T> result = new ArrayList<>();
    result.add(value);
    return result;
}
```

Các câu lệnh:

```java
// Minh họa trên Java 17+.
var specific = Tools.one(1);
var flexible = Tools.<Number>one(1);
flexible.add(2.5);
```

Trong ví dụ:

- `specific` được suy luận là `List<Integer>`; literal `1` được boxing khi đi qua phương thức generic.
- `flexible` có kiểu `List<Number>` vì lời gọi đã cung cấp `T = Number`.
- Có thể thêm một `Double` vào `flexible`, vì nó được chấp nhận qua kiểu `Number`.
- `specific.add(2.5)` không hợp lệ: đối số kiểu của danh sách đó là `Integer`.

Một cách viết rõ khác cũng hợp lệ:

```java
// Minh họa.
List<Number> flexible = Tools.one(1);
```

Ở đây kiểu đích cung cấp thông tin cần thiết. Chọn cách nào phụ thuộc khả năng đọc mã; không mặc định type witness tốt hơn khai báo biến tường minh.

## 6. Type witness không phải phép ép kiểu hoặc biến đổi giá trị

Với `identity` ở đầu bài:

```java
// Minh họa.
Object value = Tools.<Object>identity("Java");
```

Tham số `T` của lời gọi được chọn là `Object`, nên kết quả có kiểu khai báo phù hợp với `Object`. Đối tượng nhận vào vẫn là chuỗi `"Java"`. Không có thao tác biến chuỗi thành một đối tượng thuộc lớp thực tế khác.

Tương tự:

```java
// Minh họa lỗi; với Tools.identity duy nhất đã khai báo.
Integer value = Tools.<Integer>identity("Java");
```

Sau khi chọn `T = Integer`, tham số giá trị cần một đối số tương thích với `Integer`. Một `String` không đáp ứng điều đó, nên mã không biên dịch.

Type witness cũng không đổi tính bất biến của kiểu generic:

```java
// Phương thức minh họa trong Tools; cần import java.util.List.
static <T> List<T> same(List<T> values) {
    return values;
}
```

Lời gọi sau không hợp lệ:

```java
// Minh họa lỗi; cần import java.util.List.
List<Integer> integers = List.of(1, 2);
List<Number> numbers = Tools.<Number>same(integers);
```

Chọn `T = Number` làm đầu vào cần `List<Number>`. Nó không biến `List<Integer>` thành `List<Number>`. Nếu API cần đọc nhiều dạng danh sách số, phải thiết kế tham số với hợp đồng phù hợp thay vì ép kiểu để bỏ qua lỗi.

## 7. Giới hạn kiểu và các đối số không hợp lệ

### 7.1. Vẫn phải thỏa extends

```java
// Phương thức minh họa trong Tools.
static <N extends Number> double twice(N value) {
    return value.doubleValue() * 2;
}
```

`Tools.<Integer>twice(4)` hợp lệ. `Tools.<String>twice("4")` không hợp lệ vì `String` không thỏa giới hạn `Number`.

Chỉ định kiểu là đưa ra lựa chọn cho trình biên dịch kiểm tra; không phải mệnh lệnh yêu cầu bỏ qua giới hạn.

### 7.2. Không dùng kiểu nguyên thủy

`Tools.<int>identity(7)` không hợp lệ. Đối số kiểu phải là kiểu tham chiếu thích hợp; dùng `Integer` nếu muốn chọn lớp bao của `int`.

Boxing của đối số giá trị không làm `int` trở thành đối số kiểu hợp lệ.

### 7.3. Không dùng wildcard làm đối số kiểu tường minh của lời gọi

Không viết `Tools.<?>identity(...)` để yêu cầu suy luận. Với lời gọi phương thức, danh sách đối số kiểu tường minh không dùng wildcard như vị trí `List<?>`.

Nếu muốn suy luận, bỏ danh sách đó. Nếu muốn chỉ định một kiểu tham chiếu cụ thể, cung cấp kiểu phù hợp.

## 8. Overload vẫn cần được giải quyết

Type witness tham gia kiểm tra lời gọi, nhưng không thay thế toàn bộ quy tắc chọn overload.

Một điểm ít gặp nhưng cần tránh hiểu sai: Java có thể chấp nhận một lời gọi có danh sách đối số kiểu mà cuối cùng chọn một phương thức **không generic**. Trong trường hợp đó, danh sách kiểu bị bỏ qua theo quy tắc của ngôn ngữ.

Vì vậy:

- Không dùng riêng sự xuất hiện của `.<String>` ở nơi gọi để kết luận phương thức được chọn chắc chắn là generic.
- Không khẳng định thêm `<Object>` luôn ép trình biên dịch chọn một overload generic cụ thể.
- Khi có overload, đọc đầy đủ các chữ ký và kiểu đối số; nếu ý định vẫn khó thấy, cân nhắc tên phương thức rõ hơn hoặc kiểm tra overload được chọn trong IDE.

Các ví dụ lỗi về số lượng và giới hạn ở trên xét đúng phương thức generic đã khai báo, không có overload khác che đi tình huống. Nhận diện một phương thức generic trước hết dựa vào **khai báo tham số kiểu của phương thức**, không chỉ cú pháp lời gọi.

## 9. Chương trình đầy đủ

Lưu vào `ExplicitTypeArgumentsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class ExplicitTypeArgumentsDemo {
    static <T> T identity(T value) {
        return value;
    }

    static <T> List<T> one(T value) {
        List<T> result = new ArrayList<>();
        result.add(value);
        return result;
    }

    static <K, V> Map<K, V> entry(K key, V value) {
        return Map.of(key, value);
    }

    static <N extends Number> double twice(N value) {
        return value.doubleValue() * 2;
    }

    static final class Echo {
        <U> U echo(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> inferred = Collections.emptyList();
        List<String> explicit = Collections.<String>emptyList();
        System.out.println("empty=" + inferred.size() + "/" + explicit.size());

        var flexible = ExplicitTypeArgumentsDemo.<Number>one(1);
        flexible.add(2.5);
        System.out.println(flexible);

        var specific = ExplicitTypeArgumentsDemo.one(1);
        Integer first = specific.get(0);
        System.out.println(first.getClass().getSimpleName());

        Echo receiver = new Echo();
        String word = receiver.<String>echo("Java");
        System.out.println(word);

        Map<Number, CharSequence> item =
                ExplicitTypeArgumentsDemo.<Number, CharSequence>entry(1, "one");
        System.out.println(item.get(1));

        double doubled = ExplicitTypeArgumentsDemo.<Integer>twice(4);
        System.out.println(doubled);

        Object widened = ExplicitTypeArgumentsDemo.<Object>identity("text");
        System.out.println(widened.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

Stdout chính xác:

```text
empty=0/0
[1, 2.5]
Integer
Java
one
8.0
String
```

Cách đọc kết quả:

1. Hai cách gọi `emptyList` đều tạo danh sách rỗng có kiểu phù hợp; suy luận hiện đại đã đủ cho phép gán đầu tiên.
2. `<Number>` quyết định kiểu phần tử của danh sách được tạo, nên danh sách chứa được cả `Integer` và `Double`.
3. Lời gọi `one(1)` không có kiểu đích bao quát hơn trong khai báo `var`, nên kết quả ở ví dụ này là `List<Integer>`.
4. Đối số kiểu cũng được chỉ định qua một đối tượng nhận lời gọi.
5. `<Number, CharSequence>` cung cấp đủ hai đối số theo đúng thứ tự `K, V`.
6. `Integer` thỏa giới hạn `Number` của `twice`.
7. Chọn `T = Object` không đổi lớp thực tế của chuỗi đầu vào.

Các ví dụ không dựa vào thông báo lỗi cụ thể của `javac`; câu chữ chẩn đoán có thể khác giữa các phiên bản. Điều cần kiểm tra là hợp đồng kiểu được chấp nhận hay bị từ chối.

## 10. Quy trình dùng trong mã thực tế

1. Đọc khai báo phương thức và đếm các tham số kiểu của chính nó.
2. Xác định có giới hạn `extends` hoặc quan hệ giữa các tham số hay không.
3. Thử đọc lời gọi với suy luận thông thường trước.
4. Nếu cần làm rõ hoặc chọn kiểu cụ thể, đặt danh sách sau dấu chấm và trước tên phương thức.
5. Kiểm tra lại kiểu của từng đối số giá trị và kiểu kết quả.
6. Khi có overload, kiểm tra phương thức thực sự được chọn.
7. Không dùng phép ép kiểu không an toàn để bù cho một lựa chọn type witness sai.

Ví dụ, đối với `static <T> List<T> one(T value)`, lựa chọn `<Number>` có ý nghĩa rõ: “hãy tạo một danh sách của `Number` từ giá trị này”. Nó không có nghĩa “hãy coi mọi danh sách số sẵn có là `List<Number>`”.

## 11. Tự kiểm tra

- Viết cùng một lời gọi `identity` theo hai cách: suy luận và chỉ định `String` tường minh.
- Với `var values = Tools.<Number>one(1)`, thử thêm `2.5`. Sau đó bỏ `<Number>` và giải thích khác biệt khi biên dịch.
- Viết lời gọi `entry` với `K = String`, `V = Number`, rồi chủ động đảo thứ tự hai đối số kiểu để quan sát lỗi tương thích.
- Giải thích vì sao `Tools.<Integer>identity("7")` không chuyển chuỗi thành số nguyên.
- Vì sao `Collections.emptyList()` có thể gán trực tiếp cho `List<String>` trên Java hiện đại?
- Phân biệt `List<?>` với `Tools.<?>identity(...)`: wildcard có hợp lệ ở cả hai vị trí không?

## Tài liệu đối chiếu

- [Java Language Specification — Method Invocation Expressions (§15.12)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): cú pháp và kiểm tra lời gọi phương thức.
- [Java Language Specification — Potentially Applicable Methods (§15.12.2.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2.1): đối số kiểu tường minh và quan hệ với overload.
- [Java Language Specification — Type Inference (Chapter 18)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html): cơ chế suy luận kiểu.
- [Java API — Collections.emptyList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#emptyList()): phương thức generic không có đối số giá trị trong ví dụ.
