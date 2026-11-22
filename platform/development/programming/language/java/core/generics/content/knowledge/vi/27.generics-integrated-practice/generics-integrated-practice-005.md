# So sánh suy luận với diamond, `var` và đối số kiểu tường minh trong Java Generics

## 1. Cùng viết ngắn, nhưng ba cơ chế giải quyết ba câu hỏi khác nhau

Java có nhiều cú pháp giúp bớt lặp lại tên kiểu. Ba dạng thường xuất hiện cạnh nhau:

```java
List<String> names = new ArrayList<>();           // Diamond <>
var scores = new ArrayList<Integer>();            // var
var values = new ArrayList<>();                    // Kết hợp var và diamond
List<String> empty = List.<String>of();            // Đối số kiểu tường minh của method
```

Đây là đoạn minh họa, cần import `java.util.List` và `java.util.ArrayList`, đặt bên trong method nếu biên dịch.

Nhìn qua, chúng đều có vẻ “để Java tự đoán kiểu”. Nhưng vai trò khác nhau:

- **Diamond `<>`** nằm ở lời gọi constructor của một class generic. Compiler suy luận **đối số kiểu của class được khởi tạo**, dựa vào constructor arguments và ngữ cảnh đích nếu có.
- **`var`** nằm ở phần **khai báo biến cục bộ**. Compiler suy luận **kiểu tĩnh của biến** từ biểu thức khởi tạo, sau đó biến vẫn được kiểm tra kiểu tĩnh như bình thường.
- **Đối số kiểu tường minh** như `new ArrayList<String>()` hoặc `Collections.<String>emptyList()` chỉ ra cụ thể tham số kiểu muốn sử dụng ở vị trí class constructor hoặc generic method. Nó có thể giúp làm rõ ý đồ hoặc hướng dẫn suy luận trong các tình huống không có ngữ cảnh đủ mạnh.

Điểm cần ghi nhớ:

> `<>` và `var` không đồng nghĩa. Khi dùng `List<String> list = new ArrayList<>()`, vế trái truyền ngữ cảnh để suy ra `String`. Khi dùng `var list = new ArrayList<>()`, không có vế trái mang `String`; với constructor không đối số này, Java suy luận phần tử là `Object`.

Vì vậy, viết gọn **không phải lúc nào cũng giữ nguyên loại thông tin kiểu** được compiler sử dụng. Muốn đánh giá tính an toàn và khả năng đọc hiểu, hãy xem **nguồn thông tin mà compiler dùng để suy luận**.

## 2. Nền tảng: generic type parameter, type argument và kiểu tĩnh

Khai báo `ArrayList<E>` có một tham số kiểu `E`. Khi sử dụng:

```java
new ArrayList<String>()
```

`String` là **đối số kiểu** được ghi tường minh cho `E`. Với:

```java
new ArrayList<>()
```

compiler tự suy luận đối số thích hợp cho `E`.

Sau đó biểu thức khởi tạo có một kiểu tĩnh. Kiểu tĩnh này có thể được dùng để suy luận tiếp kiểu của biến cục bộ khai báo bằng `var`, nhưng `var` bản thân nó **không phải một type argument** của `ArrayList`.

Có thể mô tả đơn giản:

```text
Khai báo class:     ArrayList<E>
                           |
Constructor:        new ArrayList<>()  -- suy luận E
                           |
Biểu thức:          ArrayList<String>   -- nếu ngữ cảnh xác định String
                           |
Khai báo biến:      var list = ...      -- suy luận kiểu của list từ biểu thức
```

Sơ đồ chỉ cho thấy các quan hệ suy luận; compiler Java có các quy tắc chặt chẽ hơn về *target typing*, applicability và type inference trong Java Language Specification.

Cần phân biệt thêm:

- **Kiểu tĩnh** quyết định những lời gọi/gán nào compiler chấp nhận.
- **Class runtime** do đối tượng thực được khởi tạo quyết định. `ArrayList<String>` và `ArrayList<Integer>` thường cùng runtime class `ArrayList`.
- Java Generics dùng **type erasure**, nhưng điều đó không làm mất ý nghĩa kiểm tra kiểu của `var` và diamond tại compile time.

## 3. Diamond `<>`: suy luận đối số kiểu của constructor

### 3.1. Dạng có target type

Ví dụ điển hình:

```java
List<String> names = new ArrayList<>();
```

Vế trái mang kiểu `List<String>`. Constructor `ArrayList<>()` có thể được suy luận thành một biểu thức phù hợp với việc gán cho `List<String>`; trong trường hợp đơn giản này, tham số phần tử của `ArrayList` là `String`.

Viết đầy đủ hơn:

```java
List<String> names = new ArrayList<String>();
```

Hai cách trên có cùng ý định kiểu tại mã nguồn: `names` là `List<String>`. Diamond giảm lặp lại `<String>` ở vế phải.

Tương tự:

```java
Map<String, Integer> counts = new HashMap<>();
Set<Long> ids = new HashSet<>();
```

Cần import các class từ `java.util`. Với các khai báo trên, target type ở vế trái cung cấp thông tin cho constructor.

### 3.2. Constructor arguments cũng có thể cung cấp thông tin

Nếu constructor nhận dữ liệu có kiểu rõ ràng:

```java
var copied = new ArrayList<>(List.of("An", "Binh"));
```

`List.of("An", "Binh")` có phần tử kiểu `String` theo suy luận generic method. Constructor `ArrayList(Collection<? extends E>)` nhận collection ấy, từ đó compiler có thông tin để suy ra `E` tương ứng.

Điểm khác biệt với `new ArrayList<>()` không đối số: ở ví dụ copy, **constructor argument** cung cấp ràng buộc hữu ích ngay cả khi không có kiểu đích ở vế trái.

### 3.3. Diamond không phải dấu hiệu raw type

```java
List<String> a = new ArrayList<>(); // Generic được kiểm tra.
List b = new ArrayList();           // Raw type.
```

Hai dòng có ý nghĩa khác:

- Dòng đầu dùng generic và diamond; `a` có kiểu `List<String>`.
- Dòng sau dùng raw `List` và raw `ArrayList`, làm mất kiểm tra đối số kiểu ở điểm sử dụng và có thể gây cảnh báo `rawtypes`/`unchecked`.

Đừng bỏ dấu `<...>` ở cả hai vế rồi cho rằng vẫn có cùng mức độ an toàn kiểu.

## 4. `var`: compiler suy luận kiểu biến cục bộ từ initializer

`var` được hỗ trợ cho **local variable type inference** từ Java 10. Ví dụ:

```java
var name = "Mai";
var count = 3;
var list = new ArrayList<String>();
```

Trong ba dòng này, compiler suy ra các kiểu tĩnh tương ứng là `String`, `int` và `ArrayList<String>`. Sau khi khai báo, chúng không biến thành những biến “động” có thể đổi kiểu tùy ý.

```java
var value = "hello";
// value = 10; // Lỗi biên dịch: value có kiểu String.
```

Câu lệnh thứ hai được cố ý đặt thành comment để minh họa lỗi.

### `var` không có nghĩa “không có generic”

Một biến:

```java
var strings = new ArrayList<String>();
```

có kiểu tĩnh `ArrayList<String>`. Do đó:

```java
strings.add("valid");
// strings.add(123); // Lỗi biên dịch.
```

Dùng `var` **không tự làm mất** `<String>` đã xuất hiện trong biểu thức khởi tạo.

### `var` không dùng được ở mọi chỗ khai báo

`var` dành cho những vị trí được Java quy định, đặc biệt là local variables có initializer; nó không được dùng như tên kiểu thay thế cho mọi field, method parameter hoặc return type.

Ví dụ không hợp lệ:

```java
// Các dòng này chỉ là ví dụ lỗi:
// var field;                  // Field không dùng var kiểu này.
// var local;                  // Local variable thiếu initializer.
// var nothing = null;         // Không suy luận kiểu từ null đơn độc.
// var array = {1, 2, 3};      // Array initializer dạng rút gọn thiếu kiểu đích.
```

Một local array hợp lệ có thể viết `var array = new int[] {1, 2, 3};`.

Từ Java 11, `var` cũng được phép trong tham số lambda khi tuân thủ quy tắc liên quan, nhưng đó là một ngữ cảnh khác với phần đang so sánh.

## 5. Bẫy quan trọng nhất: `var` kết hợp `new ArrayList<>()`

Đây là phép thử cần thực hành thật:

Tạo tệp **`VarDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class VarDiamondDemo {
    public static void main(String[] args) {
        List<String> targeted = new ArrayList<>();
        targeted.add("Java");

        var inferredFromExplicit = new ArrayList<String>();
        inferredFromExplicit.add("Generics");

        var withoutTarget = new ArrayList<>();
        withoutTarget.add("text");
        withoutTarget.add(123);

        System.out.println(targeted.get(0));
        System.out.println(inferredFromExplicit.get(0));
        System.out.println(withoutTarget.get(0));
        System.out.println(withoutTarget.get(1));

        Object value = withoutTarget.get(0);
        System.out.println(value.getClass().getSimpleName());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac VarDiamondDemo.java
java VarDiamondDemo
```

Stdout:

```text
Java
Generics
text
123
String
```

### Vì sao `withoutTarget` nhận được cả `String` và `Integer`?

Với:

```java
var withoutTarget = new ArrayList<>();
```

compiler không nhận được ngữ cảnh kiểu `List<String>` ở vế trái, vì vế trái là `var`. Constructor `ArrayList()` không đối số cũng không đưa ra dữ liệu để suy ra một phần tử chuyên biệt. Trong tình huống này, type parameter `E` được suy luận thành `Object`, khiến biến có kiểu tĩnh `ArrayList<Object>`.

Vì vậy:

```java
withoutTarget.add("text");  // String là Object.
withoutTarget.add(123);     // Integer cũng là Object.
```

Cả hai lời gọi hợp lệ. Đây không phải “`var` thay đổi kiểu của danh sách sau lần add đầu tiên”. Kiểu đã được quyết định **ngay tại dòng khai báo**.

Cũng vì vậy:

```java
// Cố ý không hợp lệ:
String text = withoutTarget.get(0);
```

là lỗi biên dịch: `get(0)` trên `ArrayList<Object>` có kiểu tĩnh `Object`, không thể tự động gán vào `String`.

**Lưu ý:** `var` không hạ mọi generic thành `Object`. Nó chỉ phản ánh kiểu của **initializer**. Nếu initializer đã có đủ thông tin, ví dụ `new ArrayList<String>()` hoặc `new ArrayList<>(List.of("a"))`, thông tin kiểu tương ứng được giữ.

## 6. So sánh cùng một ý định bằng bốn khai báo

Giả sử mục tiêu là một danh sách chuỗi có thể thêm `"A"` và `"B"` nhưng compiler phải chặn `123`.

| Khai báo | Kiểu tĩnh của biến | Có đáp ứng ý định không? |
|---|---|---|
| `List<String> x = new ArrayList<>();` | `List<String>` | Có |
| `List<String> x = new ArrayList<String>();` | `List<String>` | Có, nhưng lặp `<String>` |
| `var x = new ArrayList<String>();` | `ArrayList<String>` | Có; phụ thuộc kiểu triển khai cụ thể |
| `var x = new ArrayList<>();` | `ArrayList<Object>` | Không, nếu muốn giới hạn phần tử là `String` |

Hai điểm khác biệt cần nhấn mạnh:

1. **Mức độ cụ thể của kiểu biến.** `List<String>` dùng interface `List`; `var x = new ArrayList<String>()` suy ra class cụ thể `ArrayList<String>`. Cả hai là generic an toàn nhưng cách biểu diễn phụ thuộc implementation khác nhau.
2. **Thông tin đưa vào suy luận.** Một lần viết `<String>` ở **vế trái** có thể đủ để diamond suy ra, nhưng với `var` thì thông tin đó phải đến từ **initializer** hoặc constructor arguments.

Khi bạn muốn API dễ thay implementation `ArrayList` bằng `LinkedList`, kiểu biến khai báo `List<String>` thường biểu diễn ý định tốt hơn. Khi phần khởi tạo phức tạp nhưng kiểu hiển nhiên từ initializer, `var` có thể giảm nhiễu.

## 7. `var` + diamond vẫn suy luận đúng khi constructor có dữ liệu

Tạo tệp **`DiamondFromArgumentsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondFromArgumentsDemo {
    public static void main(String[] args) {
        var first = new ArrayList<>(List.of("A", "B"));
        var second = new ArrayList<>(List.of(10, 20));

        String name = first.get(0);
        Integer number = second.get(0);

        first.add("C");
        second.add(30);

        System.out.println(name);
        System.out.println(number);
        System.out.println(first);
        System.out.println(second);
    }
}
```

Chạy:

```bash
javac DiamondFromArgumentsDemo.java
java DiamondFromArgumentsDemo
```

Stdout:

```text
A
10
[A, B, C]
[10, 20, 30]
```

Trong ví dụ:

- `List.of("A", "B")` được suy luận thành danh sách chuỗi.
- `new ArrayList<>(...)` nhận `Collection<? extends E>` để quyết định `E`.
- Biến `first` được suy luận thành `ArrayList<String>`.
- Biến `second` được suy luận thành `ArrayList<Integer>`.

Compiler vì thế có thể kiểm tra `String name = first.get(0)` và `Integer number = second.get(0)`.

Đừng học mẹo “có diamond thì phần tử luôn là Object”. Kết quả phụ thuộc **ràng buộc suy luận từ target type, constructor arguments và các quy tắc inference**.

## 8. Đối số kiểu tường minh của constructor so với diamond

Trong Java:

```java
new ArrayList<String>()
new ArrayList<>()
```

`<String>` ở ví dụ đầu là **đối số kiểu tường minh cho class generic**. `<>` ở ví dụ sau yêu cầu compiler suy luận chúng.

Với ngữ cảnh:

```java
List<String> names = new ArrayList<>();
```

diamond thường ngắn và rõ. Nhưng ở:

```java
var names = new ArrayList<String>();
```

việc chỉ rõ `String` ở constructor có ý nghĩa thực sự, vì `var` không cung cấp target type ở vế trái.

Có thể viết:

```java
ArrayList<String> names = new ArrayList<String>();
```

mà không sai. Tuy vậy cách viết này lặp `String`; thường chỉ nên dùng khi cần thể hiện kiểu đầy đủ để hướng dẫn người đọc hoặc khi phải tương thích môi trường Java rất cũ.

**Không nhầm** khai báo đối số kiểu của class với cú pháp đối số kiểu của method. `new ArrayList<String>()` khác về vị trí ngữ pháp với `Collections.<String>emptyList()`.

## 9. Đối số kiểu tường minh của generic method

Không chỉ constructor mới có type inference. Một **generic method** có thể khai báo tham số kiểu riêng:

```java
static <T> T identity(T input) {
    return input;
}
```

Khi gọi `identity("Java")`, compiler suy luận `T = String` từ tham số. Có thể chỉ rõ đối số kiểu bằng cú pháp:

```java
GenericMethodWitnessDemo.<String>identity("Java")
```

Ví dụ độc lập, tệp **`GenericMethodWitnessDemo.java`**:

```java
import java.util.Collections;
import java.util.List;

public class GenericMethodWitnessDemo {

    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        String inferred = identity("Java");
        String explicit =
                GenericMethodWitnessDemo.<String>identity("Generics");

        List<String> contextual = Collections.emptyList();
        var withoutContext = Collections.emptyList();
        var withWitness = Collections.<String>emptyList();

        System.out.println(inferred);
        System.out.println(explicit);
        System.out.println(contextual.size());
        System.out.println(withoutContext.size());
        System.out.println(withWitness.size());
    }
}
```

Chạy:

```bash
javac GenericMethodWitnessDemo.java
java GenericMethodWitnessDemo
```

Stdout:

```text
Java
Generics
0
0
0
```

Ba lời gọi `Collections.emptyList()` có kiểu **ở mã nguồn** khác nhau:

- `List<String> contextual = Collections.emptyList();` có target type `List<String>`, nên compiler suy luận `T` phù hợp với `String`.
- `var withoutContext = Collections.emptyList();` không có target type từ khai báo biến, và method không có tham số để cung cấp thêm ràng buộc. Trong ví dụ này `T` được suy luận là `Object`, nên biến có kiểu `List<Object>`.
- `var withWitness = Collections.<String>emptyList();` có **type witness** `<String>` ở lời gọi method, nên biến có kiểu `List<String>`.

Cả ba danh sách do `Collections.emptyList()` cung cấp đều rỗng; kết quả stdout không tự chứng minh generic types. Muốn thấy sự khác nhau, hãy thử gán kết quả vào các biến có yêu cầu kiểu trái nhau và xem compiler phản hồi.

### Suy luận không thay đổi generic declaration

Generic method vẫn chỉ có **một khai báo** `<T> List<T> emptyList()`. Việc compiler suy luận `String`, `Integer` hoặc `Object` ở từng lời gọi không tạo thêm các overload hay runtime class riêng cho từng `T`.

## 10. Lời gọi `List.of()` rỗng: nơi `var` dễ làm mất ý định

`List.of()` tạo danh sách không thể chỉnh sửa qua các thao tác cấu trúc thông thường. Phiên bản **không đối số** không có phần tử nào để giúp suy luận kiểu.

So sánh:

```java
List<String> a = List.of();
var b = List.of();
var c = List.<String>of();
```

Dự đoán:

- `a` có kiểu tĩnh `List<String>` nhờ ngữ cảnh ở vế trái.
- `b` có kiểu tĩnh `List<Object>` vì không có ngữ cảnh hoặc đối số phần tử mang `String`.
- `c` có kiểu tĩnh `List<String>` nhờ type witness `<String>`.

Khác với `new ArrayList<>()`, các danh sách từ `List.of()` không cho phép `add(...)`, vì vậy việc kiểm tra kiểu dễ thực hiện bằng phương thức nhận `List<String>` hoặc bằng cách gán sang biến cùng kiểu.

Ví dụ độc lập **`EmptyListInferenceDemo.java`**:

```java
import java.util.List;

public class EmptyListInferenceDemo {

    static void showStrings(List<String> values) {
        System.out.println("strings=" + values.size());
    }

    public static void main(String[] args) {
        List<String> a = List.of();
        var b = List.of();
        var c = List.<String>of();

        showStrings(a);
        showStrings(c);
        System.out.println(b.size());

        // showStrings(b); // Lỗi: b có kiểu List<Object>.
    }
}
```

Chạy:

```bash
javac EmptyListInferenceDemo.java
java EmptyListInferenceDemo
```

Stdout:

```text
strings=0
strings=0
0
```

Bài học: Với một **generic factory method không có đầu vào mang kiểu**, target type hoặc đối số kiểu tường minh thường là cách nói rõ loại kết quả mong đợi.

## 11. Hai dấu `<...>` nằm ở hai nơi khác nhau

Hãy nhìn hai cách viết:

```java
List<String> first = new ArrayList<>();
List<String> second = Collections.<String>emptyList();
```

Dấu ngoặc nhọn ở hai ví dụ có vai trò khác nhau:

- `new ArrayList<>()`: diamond tại **class instance creation expression**; compiler suy luận tham số kiểu của class `ArrayList<E>`.
- `Collections.<String>emptyList()`: `<String>` là **explicit type argument cho generic method** `emptyList<T>()`.

Một lớp generic có thể đồng thời có generic constructor hoặc generic instance method riêng, nên không thể suy luận chỉ từ số lượng dấu ngoặc rằng chúng luôn điều khiển cùng một tham số kiểu.

Ví dụ dạng đơn giản:

```java
class Pair<L, R> {
    Pair(L left, R right) {
    }

    <U> U echo(U value) {
        return value;
    }
}
```

Ở đây `L` và `R` thuộc **class**, còn `U` thuộc **method**. `new Pair<>("x", 1)` suy luận `L`, `R`; `pair.<Boolean>echo(true)` đặt `U = Boolean`. Hai cơ chế có quan hệ nhưng hoạt động tại hai vị trí khai báo riêng.

## 12. Ví dụ tổng hợp: generic class và generic method độc lập

Tạo tệp **`CombinedInferenceDemo.java`**:

```java
public class CombinedInferenceDemo {

    static class Pair<L, R> {
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

        <U> U echo(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> first = new Pair<>("age", 21);

        var second = new Pair<>("score", 99);

        String label = first.left();
        Integer score = second.right();

        String message = second.echo("ok");
        Boolean flag = second.<Boolean>echo(true);

        System.out.println(label);
        System.out.println(score);
        System.out.println(message);
        System.out.println(flag);
    }
}
```

Biên dịch và chạy:

```bash
javac CombinedInferenceDemo.java
java CombinedInferenceDemo
```

Stdout:

```text
age
99
ok
true
```

Phân tích:

1. `first` có target type `Pair<String,Integer>`, nên diamond ở constructor được suy luận phù hợp với target.
2. `second` không có target type từ `var`, nhưng constructor nhận `"score"` và `99`, đủ để suy ra `L = String`, `R = Integer`.
3. `second.right()` vì vậy có kiểu tĩnh `Integer`.
4. `second.echo("ok")` suy luận **`U` của method** từ đối số là `String`.
5. `second.<Boolean>echo(true)` là lời gọi cùng method nhưng chỉ định tường minh `U = Boolean`. Nó không thay đổi `L`, `R` của `Pair`.

Nếu thử `Pair<String,Integer> wrong = new Pair<>("age","twenty");`, compiler phải từ chối vì đối số thứ hai không phù hợp kiểu đích `Integer`. Đây là lợi ích cụ thể của target typing và kiểm tra kiểu.

## 13. Khi nào `var` làm lộ class cụ thể thay vì interface?

Nhìn vào hai khai báo:

```java
List<String> list = new ArrayList<>();
var list2 = new ArrayList<String>();
```

- `list` có kiểu tĩnh là **interface** `List<String>`.
- `list2` có kiểu tĩnh là **class triển khai** `ArrayList<String>`.

Điều này không tự động làm `list2` thiếu an toàn kiểu; cả hai đều chặn phần tử khác `String`. Khác biệt ở khả năng truy cập các thành viên chỉ thuộc class triển khai, ở tính đọc hiểu và mức độ phụ thuộc vào implementation.

Ví dụ:

```java
var concrete = new java.util.ArrayList<String>();
java.util.List<String> abstraction = new java.util.ArrayList<>();
```

Hai biến cùng trỏ tới object `ArrayList` khi chạy, nhưng khai báo thứ hai chủ động biểu đạt “tôi chỉ cần hợp đồng `List`”.

Với API dùng lâu dài hoặc được nhiều nơi sử dụng, khai báo interface ở vế trái thường tạo ranh giới phụ thuộc rõ ràng. Với biến cục bộ ngắn, `var` có thể hợp lý nếu kiểu được thể hiện trực tiếp, không làm người đọc phải đoán.

**Không suy ra rằng** `var` giống `Object`. `var concrete = new ArrayList<String>()` có type đầy đủ `ArrayList<String>`, không phải `Object`, raw `ArrayList`, hay `ArrayList<Object>`.

## 14. Bối cảnh target typing: assignment, return và lời gọi method

Compiler có thể dùng **target type** từ ngữ cảnh bao quanh một biểu thức generic:

```java
List<String> list = new ArrayList<>();
```

Ở đây assignment cung cấp kiểu đích.

Một phương thức có return type rõ ràng cũng tạo ngữ cảnh:

```java
static List<String> createNames() {
    return new ArrayList<>();
}
```

Trong lời gọi method, tham số của method có thể tạo target type:

```java
static void consume(List<String> names) {
    System.out.println(names.size());
}

static void demo() {
    consume(new ArrayList<>());
}
```

Hai đoạn trên là khai báo method để minh họa, không có class chứa và `main`; đặt chúng trong một class để biên dịch.

Bởi vậy, quy tắc “diamond chỉ nhìn vế trái” là thiếu. Diamond có thể dùng nhiều ngữ cảnh phù hợp được hệ thống type inference của Java quy định, cùng thông tin đến từ constructor arguments.

**`var` là ngữ cảnh đặc biệt:** Khi viết `var x = expression;`, compiler phải xác định kiểu của chính `expression` để tạo kiểu của `x`. Không có một khai báo `List<String>` ở vế trái để truyền thông tin `String` vào việc suy luận đối số kiểu của initializer.

## 15. Suy luận từ biểu thức generic method và type witness

Xét method:

```java
static <T> T choose(T first, T second) {
    return first;
}
```

Compiler có thể dùng hai đối số để suy luận `T`, và trong ngữ cảnh phù hợp còn xét ràng buộc từ kết quả.

Ví dụ chương trình độc lập **`ChooseInferenceDemo.java`**:

```java
public class ChooseInferenceDemo {

    static <T> T choose(T first, T second) {
        return first;
    }

    public static void main(String[] args) {
        String selected = choose("red", "blue");

        var inferred = choose(10, 20);

        Number asNumber =
                ChooseInferenceDemo.<Number>choose(10, 2.5);

        System.out.println(selected);
        System.out.println(inferred);
        System.out.println(asNumber);
    }
}
```

Chạy:

```bash
javac ChooseInferenceDemo.java
java ChooseInferenceDemo
```

Stdout:

```text
red
10
10
```

`<Number>` là explicit type argument cho method `choose`, nên cả `Integer` (từ `10`) và `Double` (từ `2.5`) đều có thể được dùng qua kiểu `Number`. Kết quả được biểu diễn ở kiểu tĩnh `Number`, dù object được chọn ở runtime là `Integer`.

Nếu khai báo type witness không phù hợp, compiler sẽ từ chối. Ví dụ:

```java
// Cố ý không hợp lệ:
String s = ChooseInferenceDemo.<String>choose("a", 42);
```

`42` không phù hợp với `String`, nên không thể ép compiler “suy luận” sai chỉ bằng `<String>`. Type witness là **ràng buộc kiểm tra kiểu**, không phải cast hoặc lệnh bỏ qua hệ thống kiểu.

### Khi nào nên chỉ định đối số kiểu?

Thông thường compiler đã suy luận được từ đối số:

```java
String selected = choose("red", "blue");
```

Viết `<String>` tường minh thường không cần thiết. Nhưng với generic factory không có tham số hoặc khi muốn làm rõ một kiểu kết quả/kiểu chung, type witness có thể giúp diễn đạt ý định và loại bỏ chỗ mơ hồ.

## 16. `var` và wildcard: đừng nhầm kiểu không biết với `Object`

Một nhu cầu phổ biến là chỉ **đọc** từ danh sách mà không cần biết chính xác kiểu phần tử. Khi đó dùng `List<?>`:

```java
static void printAll(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Đây là phương thức minh họa cần đặt trong class.

`List<?>` khác raw `List`:

- `List<?>` vẫn là kiểu generic với một đối số **chưa biết**, nên compiler giữ các ràng buộc an toàn. Chẳng hạn, không thể thêm tùy tiện `"a"` vào `List<?>`.
- Raw `List` bỏ kiểm tra generic ở nơi dùng và có thể tạo cảnh báo unchecked.
- `List<Object>` có phần tử chính xác là `Object` về mặt type argument; không thể nhận trực tiếp `List<String>` do invariance.
- `var x = new ArrayList<>()` trong trường hợp không có dữ liệu/ngữ cảnh thường cho `ArrayList<Object>`, **không** phải `ArrayList<?>`.

Ví dụ sai dễ gặp:

```java
List<String> strings = new ArrayList<>();
// List<Object> objects = strings; // Không hợp lệ.
List<?> unknown = strings;         // Hợp lệ.
```

Suy luận bằng `var` không thay đổi các quy tắc variance hay wildcard của Java.

## 17. Những trường hợp compiler không thể suy luận từ `var`

Một số cách dùng `var` bị từ chối hoặc dẫn đến kiểu ngoài ý muốn:

### Chỉ có `null`

```java
// var value = null; // Lỗi: không có kiểu thích hợp để suy luận.
String value = null; // Hợp lệ: đã có kiểu đích String.
```

### Không có initializer

```java
// var items; // Không hợp lệ.
java.util.List<String> items;
items = new java.util.ArrayList<>();
```

Một local variable khai báo bằng tên kiểu tường minh có thể gán sau, nhưng phải tuân thủ definite assignment trước khi đọc.

### Lambda/method reference đứng độc lập không có kiểu đích

```java
// var predicate = x -> x.length() > 0; // Không hợp lệ.
java.util.function.Predicate<String> predicate =
        x -> x.length() > 0;
```

Lambda cần một **functional interface target type**. Dù `var` có thể xuất hiện trong phần parameter declaration của lambda theo quy tắc Java 11+, không có nghĩa một lambda expression tự cung cấp được functional interface type cho initializer của `var`.

### Diamond rỗng

```java
var items = new java.util.ArrayList<>();
```

Dòng này hợp lệ, nhưng `items` là `ArrayList<Object>`, không phải `ArrayList<String>` chỉ vì bạn dự định thêm String sau đó.

### Anonymous class hay biểu thức có kiểu suy luận phức tạp

`var` có thể suy luận một kiểu quá cụ thể hoặc khó diễn đạt bằng tên đơn giản. Với anonymous class, local variable inference có thể giữ thông tin về anonymous type đủ để gọi thành viên trực tiếp trong phạm vi cho phép, điều khác với khai báo qua interface ở vế trái.

Khi kiểu trở nên khó hiểu hoặc API cần hợp đồng trừu tượng, viết rõ kiểu ở bên trái thường làm code dễ bảo trì hơn.

## 18. Diamond và anonymous class: lưu ý theo phiên bản Java

Từ Java 9, diamond có thể xuất hiện cùng anonymous class trong những trường hợp được ngôn ngữ cho phép. Tuy vậy, compiler đặt điều kiện đối với các kiểu được suy luận cho anonymous class (trong đó yêu cầu về kiểu có thể biểu diễn được bằng ngôn ngữ nguồn).

Không nên lấy một ví dụ `new SomeGeneric<>() { ... }` bất kỳ và kết luận nó luôn hợp lệ; cần xét constructor, inference và hạn chế liên quan.

Với Java 17+, nếu mục tiêu là minh họa diamond thông thường và `var`, ví dụ `new ArrayList<>()` hoặc `new Pair<>("x", 1)` rõ ràng hơn. Anonymous subclass còn liên quan tới việc giữ generic superclass metadata, một chủ đề riêng với mục tiêu suy luận kiểu của bài này.

## 19. Những lỗi và hiểu sai thường gặp

**Lỗi 1 — “`var` luôn suy luận thành `Object`.”** Sai. `var text = "a"` suy ra `String`; `var list = new ArrayList<String>()` suy ra `ArrayList<String>`.

**Lỗi 2 — “`new ArrayList<>()` luôn tạo `ArrayList<Object>`.”** Sai. Với target type `List<String>` hoặc constructor arguments phù hợp, diamond có thể suy luận `String`. Nó suy ra `Object` trong trường hợp không có ràng buộc đủ cụ thể, ví dụ `var x = new ArrayList<>()`.

**Lỗi 3 — “Compiler xem các lệnh `add(...)` sau đó để xác định `E`.”** Sai. Kiểu của biến được xác định ở dòng khai báo, không thay đổi theo những lời gọi tiếp theo.

**Lỗi 4 — “`var` là kiểu động giống JavaScript.”** Sai. Java vẫn kiểm tra kiểu tĩnh; `var x = "a"; x = 1;` là lỗi.

**Lỗi 5 — “Diamond chính là raw type.”** Sai. Diamond yêu cầu suy luận generic argument; raw type bỏ thông tin generic ở nơi sử dụng.

**Lỗi 6 — “`List<?>` giống `List<Object>`.”** Sai. Wildcard biểu diễn đối số kiểu chưa biết; `List<Object>` có đối số kiểu cụ thể là `Object`. Java Generics mặc định invariant.

**Lỗi 7 — “Đối số kiểu `<String>` ở `Collections.<String>emptyList()` là cast.”** Sai. Nó đặt type argument cho generic method, chịu kiểm tra kiểu bình thường.

**Lỗi 8 — “`new ArrayList<String>()` và `Collections.<String>emptyList()` cùng một loại cú pháp generic.”** Không hoàn toàn. Cái đầu áp dụng đối số kiểu cho class instance creation; cái sau cho lời gọi generic method.

**Lỗi 9 — “Nếu code compile với `var` thì đọc code sẽ luôn rõ kiểu.”** Không hẳn. `var` có thể che đi việc initializer suy luận `Object` hoặc một class cụ thể ngoài ý định thiết kế. Cần chọn cách viết dễ hiểu với người bảo trì.

**Lỗi 10 — “Đối số kiểu tường minh sinh class runtime riêng cho mỗi kiểu.”** Sai. Generics Java thông thường áp dụng erasure. Tường minh hay suy luận đều chủ yếu phục vụ compile-time type checking.

**Lỗi 11 — “Có thể sửa mismatch bằng type witness bất kỳ.”** Sai. `ChooseInferenceDemo.<String>choose("a", 42)` vẫn sai vì đối số thứ hai không đáp ứng `String`.

**Lỗi 12 — “Tất cả generic method đều phụ thuộc target type.”** Sai. Nhiều method đã đủ thông tin từ tham số đầu vào; target type chỉ là một nguồn ràng buộc có thể tham gia suy luận theo quy tắc cụ thể.

## 20. Bảng quyết định khi viết code thực tế

| Mục tiêu | Cách viết gợi ý | Vì sao |
|---|---|---|
| Muốn biến có hợp đồng `List<String>` | `List<String> x = new ArrayList<>();` | Interface rõ ràng; diamond tận dụng target type |
| Muốn `var` nhưng phải giữ `String` | `var x = new ArrayList<String>();` | Initializer mang generic argument |
| Copy một collection có kiểu rõ | `var x = new ArrayList<>(List.of("a"));` | Constructor argument giúp suy luận `String` |
| Muốn list rỗng không sửa được | `List<String> x = List.of();` | Target type gợi `String` |
| Muốn dùng `var` với generic factory rỗng | `var x = List.<String>of();` | Type witness nêu rõ type argument |
| Muốn utility generic cho nhiều loại dữ liệu | `<T> ...` và để compiler suy luận từ input | Một thuật toán, vẫn kiểm tra kiểu |
| Muốn diễn đạt rõ một type argument của method | `Utils.<Number>choose(1, 2.5)` | Hướng dẫn suy luận method, không cast |
| Không biết kiểu phần tử, chủ yếu đọc | `List<?> items` | Giữ an toàn wildcard |
| Muốn công khai API phụ thuộc interface | Khai báo `List<T>`, `Map<K,V>` ở boundary | Giảm phụ thuộc vào implementation |
| Muốn giữ code ngắn khi kiểu đã rõ | `var` cho biến cục bộ phù hợp | Ít lặp, vẫn type-safe nếu initializer đúng |

Đây không phải bảng yêu cầu phải dùng một phong cách duy nhất. Khi quyết định giữa `var` và kiểu tường minh, tiêu chí quan trọng là **người đọc có nhận diện đúng loại dữ liệu và hợp đồng kiểu từ vị trí khai báo hay không**.

## 21. Bài thực hành tổng hợp có kết quả cụ thể

Tạo tệp **`InferencePracticeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class InferencePracticeDemo {

    static <T> List<T> copy(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> one = new ArrayList<>();
        var two = new ArrayList<String>();
        var three = new ArrayList<>();
        var four = new ArrayList<>(List.of("A", "B"));

        one.add("one");
        two.add("two");
        three.add("three");
        three.add(3);
        four.add("C");

        List<String> copied = copy(four);
        var emptyTyped = List.<String>of();

        System.out.println(one);
        System.out.println(two);
        System.out.println(three);
        System.out.println(four);
        System.out.println(copied);
        System.out.println(emptyTyped.size());
    }
}
```

Biên dịch/chạy:

```bash
javac InferencePracticeDemo.java
java InferencePracticeDemo
```

Stdout:

```text
[one]
[two]
[three, 3]
[A, B, C]
[A, B, C]
0
```

Trước khi chạy, hãy dự đoán:

1. `one` có kiểu tĩnh gì? **Đáp án:** `List<String>`.
2. `two` có kiểu gì? **Đáp án:** `ArrayList<String>`.
3. `three` có kiểu gì? **Đáp án:** `ArrayList<Object>`.
4. `four` có kiểu gì? **Đáp án:** `ArrayList<String>`.
5. Tại sao `copy(four)` có thể trả `List<String>`? **Đáp án:** `List<? extends T>` nhận danh sách phần tử phù hợp và compiler suy luận `T` theo lời gọi cùng kiểu đích.
6. Vì sao `List.<String>of()` vẫn rỗng? **Đáp án:** `<String>` chỉ cung cấp type argument, không tạo phần tử.
7. `three.add(3)` có làm kiểu của `three` chuyển thành `ArrayList<Integer>`? **Đáp án:** Không; nó vốn là `ArrayList<Object>` từ initializer.

Một thử nghiệm nhỏ khác là thay dòng:

```java
var three = new ArrayList<>();
```

bằng:

```java
var three = new ArrayList<String>();
```

Khi đó compiler sẽ từ chối `three.add(3)` vì kiểu phần tử đã là `String`. Đây là cách quan sát trực tiếp tác động của việc thêm đối số kiểu tường minh.

## 22. Phân biệt các lỗi tại compile time

Khi gặp thông báo lỗi, hãy xét nó nằm ở giai đoạn nào:

| Mã gây lỗi | Vấn đề | Sửa theo ý định |
|---|---|---|
| `var x = null;` | Không có kiểu initializer để suy luận | Ghi loại biến: `String x = null;` |
| `var f = s -> s.length();` | Lambda thiếu functional interface target type | Khai báo `Function<String,Integer>` |
| `var x = new ArrayList<>(); String s = x.get(0);` | `E` đã suy ra là `Object` | Thêm target `List<String>` hoặc constructor `<String>` |
| `List<Object> x = new ArrayList<String>();` | Generic invariance | Chọn `List<String>` hoặc wildcard phù hợp |
| `var x = new ArrayList<String>(); x.add(1);` | `Integer` không phù hợp `String` | Chỉ thêm chuỗi hoặc sửa kiểu phần tử có chủ đích |
| `List<String> x = List.of(); x.add("a");` | Factory trả danh sách không thể chỉnh sửa | Chọn `new ArrayList<>(List.of())` nếu cần thay đổi |
| `ChooseInferenceDemo.<String>choose("a", 42)` | Type witness mâu thuẫn với đối số | Dùng các đối số `String` hoặc chọn một kiểu chung phù hợp |

Lỗi compile time do type inference có thể trông dài vì compiler phải giải nhiều ràng buộc. Thay vì sửa bằng cast hoặc raw type, hãy hỏi: **kiểu mong đợi là gì, và ngữ cảnh nào đang cung cấp thông tin đó?**

## 23. Ghi nhớ

Ba cơ chế bổ sung nhau:

- **Diamond `<>`** suy luận đối số kiểu khi gọi constructor của class generic.
- **`var`** suy luận kiểu của **biến cục bộ** từ initializer; kiểu sau suy luận vẫn cố định và được compiler kiểm tra.
- **Đối số kiểu tường minh** như `new ArrayList<String>()`, `List.<String>of()` hoặc `Utility.<Number>method(...)` phát biểu rõ loại cần dùng và có thể hướng dẫn generic type inference.

`List<String> x = new ArrayList<>()` và `var x = new ArrayList<>()` rất dễ bị nhầm, nhưng trường hợp đầu có target type `String`, trường hợp sau thường suy ra `ArrayList<Object>` nếu constructor không cung cấp ràng buộc khác. Ngược lại, `var x = new ArrayList<String>()` và `var x = new ArrayList<>(List.of("a"))` vẫn giữ thông tin `String`.

**Hãy chọn cú pháp dựa trên nguồn thông tin kiểu thực sự có mặt tại nơi khởi tạo.** Compiler suy luận từ khai báo, đối số và ngữ cảnh; nó không “học thêm” loại phần tử từ các thao tác `add(...)` về sau.

Tài liệu chuẩn để đối chiếu:

- [Java Language Specification §14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): `var` và quy tắc suy luận kiểu biến cục bộ.
- [Java Language Specification §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): diamond và tạo đối tượng.
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): hệ thống ràng buộc để suy luận kiểu.
- [Java Language Specification §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): generic method invocation và explicit type arguments.
- [Java Language Specification §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): generic type arguments và quan hệ kiểu.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): vì sao compile-time generic không sinh class runtime riêng.