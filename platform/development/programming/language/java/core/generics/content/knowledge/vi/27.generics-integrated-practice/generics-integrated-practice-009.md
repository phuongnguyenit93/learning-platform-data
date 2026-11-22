# Lập bảng lựa chọn `T`, `?`, `? extends`, `? super` và tự đánh giá tình huống

## 1. Mục tiêu: chọn cú pháp Generics từ yêu cầu dữ liệu

Khi viết một API Java, câu hỏi quan trọng không phải “nên dùng wildcard ở đâu cho nhiều?”, mà là **mối quan hệ kiểu nào cần được hợp đồng phương thức thể hiện**. Bốn lựa chọn thường gặp là:

- **`T`**: một *type variable có tên*, được khai báo ở class hoặc method và có thể xuất hiện tại nhiều vị trí để **liên kết các kiểu**.
- **`?`**: một *wildcard chưa xác định*, thường phù hợp khi code chỉ cần thao tác không phụ thuộc element type.
- **`? extends T`**: một kiểu chưa biết nhưng là subtype phù hợp của `T`, thường dùng khi **đọc dữ liệu như `T`**.
- **`? super T`**: một kiểu chưa biết nhưng là `T` hoặc supertype phù hợp, thường dùng khi **đưa giá trị kiểu `T` vào**.

Ví dụ ngắn:

```java
static void inspect(List<?> items) { ... }

static double total(List<? extends Number> items) { ... }

static void append(List<? super Integer> items) { ... }

static <T> T first(List<T> items) { ... }
```

Đây là **mẫu chữ ký minh họa**, không phải một file Java hoàn chỉnh. Cần import `java.util.List`, định nghĩa thân method và đặt trong một class.

Đối với bài thực hành tổng hợp này, hãy tập trung trả lời ba câu hỏi trước khi chọn cú pháp:

1. **Phương thức có cần ghi phần tử vào cấu trúc hay chỉ đọc?**
2. **Kiểu ở tham số này có phải liên hệ với tham số khác hoặc kiểu trả về không?**
3. **Caller cần đưa được những concrete parameterizations nào vào API?**

Chọn sai thường không gây lỗi lúc chạy ngay: nhiều trường hợp compiler từ chối lời gọi hữu ích, hoặc API trở nên quá rộng và phải cast không an toàn. Chọn đúng giúp giữ **type safety** mà caller vẫn linh hoạt.

## 2. Bảng quyết định nhanh

| Nhu cầu ở biên API | Lựa chọn thường hợp lý | Điều đảm bảo |
|---|---|---|
| Chỉ cần đọc, đếm, in hoặc xóa toàn bộ, không quan tâm element type | `List<?>` | Chấp nhận `List<String>`, `List<Integer>`, ... |
| Đọc số và gọi `doubleValue()` | `List<? extends Number>` | Mỗi phần tử đọc ra dùng được như `Number` |
| Thêm các `Integer` vào list do caller cung cấp | `List<? super Integer>` | Chấp nhận `List<Integer>`, `List<Number>`, `List<Object>` |
| Input và output cần liên kết cùng một type parameter | `<T> T first(List<T>)` | Trả type `T` được suy ra từ input |
| Chuyển phần tử từ nguồn sang đích | `<T> void copy(List<? extends T>, List<? super T>)` | Nguồn cấp T, đích nhận T |
| Trả một `List` có element type tường minh cho caller | `List<T>` hoặc `List<String>` | Caller biết kiểu chính xác theo contract |
| So sánh các object kiểu `T` bằng comparator của T hoặc supertype | `Comparator<? super T>` | Comparator tiêu thụ T |
| Chuyển các T thành các R bằng một hàm | `Function<? super T, ? extends R>` | Hàm nhận T, tạo R |
| Giới hạn type variable khai báo phải thuộc họ số | `<T extends Number>` | Bound trên type parameter |
| Chỉ đọc nested lists số | `List<? extends List<? extends Number>>` | Mỗi cấp có hướng đọc và giới hạn riêng |

**Từ khóa nhớ:** *Producer Extends, Consumer Super* — thường viết là **PECS**. Đây là mẹo chọn **wildcard tại vị trí dùng generic type**, không thay thế việc phân tích data flow.

Khi một tham số vừa phải nhận lẫn trả một `T` cụ thể, một type variable `<T>` hoặc invariant `List<T>` có thể cần thiết. Không cố đặt wildcard vào mọi chỗ.

## 3. Bảng đọc/ghi chính xác với `List`

Giả sử các list **mutable** và không có ràng buộc nghiệp vụ khác:

| Kiểu tham chiếu | Đọc phần tử an toàn như | Được `add` giá trị kiểu nào? | Có thể trỏ tới |
|---|---|---|---|
| `List<String>` | `String` | `String` | Một list có static element type `String` |
| `List<Number>` | `Number` | `Number` và subtypes phù hợp | `List<Number>` |
| `List<Object>` | `Object` | Mọi reference value | `List<Object>` |
| `List<?>` | `Object` | Chỉ `null` tùy mutability; không add giá trị non-null tùy ý | `List<String>`, `List<Integer>`, ... |
| `List<? extends Number>` | `Number` | Chỉ `null` tùy mutability; không add một `Number` tùy ý | `List<Integer>`, `List<Double>`, `List<Number>`, ... |
| `List<? super Integer>` | `Object` | `Integer` và các subtype hợp lệ của `Integer` (vì `Integer` final, chính `Integer`) | `List<Integer>`, `List<Number>`, `List<Object>` |
| `List<? super Number>` | `Object` | `Number` và các subtype của `Number`, như `Integer`, `Double` | `List<Number>`, `List<Object>` |

Cần phân biệt **“compiler cho phép lời gọi `add`”** với **“đối tượng list thực có thể chỉnh sửa”**. `List.of(...)` là unmodifiable: ngay cả `List<String>` cũng không thêm phần tử được lúc chạy. Các bảng ở trên nói về **kiểm tra kiểu tĩnh**, không hứa mọi list mutable.

`List<?>` và `List<? extends Number>` vẫn cho phép nhiều thao tác không yêu cầu cung cấp một giá trị mới của element type: `size`, `get`, `clear`, `remove` theo index hoặc `add(null)` nếu implementation cho phép. Vì vậy gọi chúng là “read-only list” là cách nói tắt không hoàn toàn chính xác; chúng chủ yếu **không cho phép thêm phần tử non-null có kiểu tùy chọn**.

## 4. Vì sao `List<Integer>` không phải `List<Number>`?

Trong Java, generic types như `List<T>` mặc định **invariant**:

```java
List<Integer> integers = new ArrayList<>();
// CỐ Ý KHÔNG BIÊN DỊCH:
// List<Number> numbers = integers;
```

Nếu phép gán bị cấm ở trên được cho phép, ta có thể gọi `numbers.add(3.14)` rồi làm ô nhiễm một list vốn cần chỉ `Integer`.

Kế thừa của phần tử **không tự lan sang** quan hệ kế thừa của hai generic instantiations:

```text
Integer <: Number <: Object

List<Integer> KHÔNG phải subtype của List<Number>
List<Integer> là subtype phù hợp của List<? extends Number>
List<Number> là subtype phù hợp của List<? super Integer>
```

Từ khóa `extends` và `super` ở **wildcard** tạo một tập những parameterized types mà method có thể chấp nhận. Nó không đổi class hierarchy thực sự.

Dùng `List<? extends Number>` khi cần **đọc như Number** từ nhiều loại list. Dùng `List<? super Integer>` khi cần **ghi Integer** vào nhiều loại list.

## 5. Ví dụ chạy được: `?`, `extends`, `super` trong cùng chương trình

Tạo tệp **`WildcardChoiceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardChoiceDemo {

    static int count(List<?> values) {
        return values.size();
    }

    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number number : values) {
            result += number.doubleValue();
        }
        return result;
    }

    static void appendIntegers(List<? super Integer> target) {
        target.add(10);
        target.add(20);
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Double> decimals = List.of(1.5, 2.5);
        List<Number> target = new ArrayList<>();

        appendIntegers(target);

        System.out.println(count(integers));
        System.out.println(sum(integers));
        System.out.println(sum(decimals));
        System.out.println(target);
        System.out.println(target.get(0) instanceof Number);
    }
}
```

Lệnh JDK 17+:

```bash
javac WildcardChoiceDemo.java
java WildcardChoiceDemo
```

Stdout:

```text
3
6.0
4.0
[10, 20]
true
```

Giải thích:

- `count(List<?>)` không cần biết element type, chỉ gọi `size`.
- `sum(List<? extends Number>)` đọc được mọi phần tử như `Number`, áp dụng được cho cả `List<Integer>` và `List<Double>`.
- `appendIntegers(List<? super Integer>)` được phép thêm `Integer` vào `List<Number>`.
- Phương thức không cần trả một element type cụ thể từ `target`; kết quả `get` khi nhìn qua `List<? super Integer>` chỉ bảo đảm kiểu `Object`.

Nếu `target` là `List.of(...)` unmodifiable, `appendIntegers` có thể ném `UnsupportedOperationException` dù kiểu tĩnh khớp. Trong ví dụ, `target` dùng `ArrayList`.

## 6. Khi nào cần type variable `<T>` thay vì `?`

Type variable có tên giúp **liên kết hai hoặc nhiều vị trí kiểu**.

Ví dụ:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
```

Caller:

```java
List<String> words = List.of("A", "B");
String firstWord = first(words);
```

Ở đây compiler suy luận `T = String` từ `List<String>` và cho return type `String`. Nếu thay bằng:

```java
static Object first(List<?> values) {
    return values.get(0);
}
```

method vẫn đọc đúng object nhưng caller chỉ biết return type là `Object`. Quan hệ đầu vào/đầu ra đã không còn trong signature.

**Quy tắc thực dụng:** Nếu một kiểu xuất hiện tại **chỉ một vị trí và không cần đặt tên để liên kết**, wildcard thường làm API ngắn hơn. Nếu kiểu xuất hiện ở nhiều vị trí ràng buộc lẫn nhau, `<T>` thường có giá trị.

Lưu ý tinh tế: `<T>` có thể được suy luận thành một **common supertype** của các actual arguments trong một lời gọi. Nó không đảm bảo hai runtime objects có cùng concrete class. `<T>` là một ràng buộc kiểu tĩnh, không phải phép kiểm tra runtime class equality.

## 7. Ví dụ: `<T>` giữ return type và copy dữ liệu

Tệp **`TypeVariableDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class TypeVariableDemo {

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    static <T> List<T> duplicate(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> words = List.of("An", "Binh");
        List<Integer> numbers = List.of(4, 5);

        String word = first(words);
        Integer number = first(numbers);
        List<String> copy = duplicate(words);

        System.out.println(word);
        System.out.println(number);
        System.out.println(copy);
    }
}
```

Chạy:

```bash
javac TypeVariableDemo.java
java TypeVariableDemo
```

Stdout:

```text
An
4
[An, Binh]
```

Phân tích:

- Method `first` dùng `T` trong **tham số list** và **return type**.
- Method `duplicate` dùng `T` để mô tả **return list**, còn input `? extends T` cho phép một producer thuộc subtype phù hợp.
- `new ArrayList<>(source)` tạo list mới có thể thay đổi; đây là **shallow copy**, không clone phần tử.
- Nếu chỉ cần in tất cả phần tử dưới dạng `Object`, không có lý do bắt buộc khai báo `<T>`: `List<?>` đơn giản hơn.

## 8. `<T extends Bound>` không phải `? extends Bound`

Đây là nhầm lẫn quan trọng nhất:

```java
static <T extends Number> T identity(T value) {
    return value;
}
```

`<T extends Number>` **khai báo type variable T** và hạn chế T phải là `Number` hoặc subtype hợp lệ.

Ngược lại:

```java
static double total(List<? extends Number> values) {
    // ...
    return 0;
}
```

`? extends Number` **không khai báo type variable**. Nó là wildcard type argument ở chỗ dùng `List`.

So sánh:

| Cú pháp | Nằm ở đâu? | Ý nghĩa |
|---|---|---|
| `<T>` | Khai báo type parameters | Đặt tên một biến kiểu |
| `<T extends Number>` | Khai báo generic class/method | Bound trên type variable |
| `List<T>` | Chỗ dùng kiểu, T đã khai báo | Gắn element type với T |
| `List<? extends Number>` | Chỗ dùng kiểu | Một unknown element type dưới Number |
| `List<? super Integer>` | Chỗ dùng kiểu | Một unknown element type là Integer hoặc supertype |
| `<T super Number>` | Không hợp lệ trong Java | Không có lower bound syntax cho type parameter |
| `List<? extends T>` | Chỗ dùng kiểu, T đã có | Producer của T hoặc subtype |
| `List<? super T>` | Chỗ dùng kiểu, T đã có | Consumer của T hoặc supertype |

Java không cho khai báo `<T super Number>`. `super` nằm ở **wildcard type argument**, không phải cách khai báo lower bound cho type parameter.

Một type variable còn có thể có nhiều upper bounds:

```java
<T extends Number & Comparable<T>>
```

nhưng wildcard `? extends Number & Comparable<...>` không phải cách tương đương để đặt intersection bounds trong type argument Java thông thường.

## 9. Kết hợp `T`, `extends` và `super`: chuyển nguồn sang đích

Bài toán điển hình của PECS là copy các phần tử từ một collection sang collection khác. API cần đủ linh hoạt:

- `List<Integer>` → `List<Number>`: hợp lệ.
- `List<Integer>` → `List<Object>`: hợp lệ.
- `List<Double>` → `List<Number>`: hợp lệ.
- `List<Number>` → `List<Integer>`: **không** an toàn: nguồn có thể chứa Double.

Chữ ký:

```java
static <T> void transfer(
        List<? extends T> source,
        List<? super T> target) {
    for (T value : source) {
        target.add(value);
    }
}
```

Đây là một method minh họa; đặt trong class và import `List`.

Ý nghĩa:

- `T` liên kết nguồn và đích.
- Nguồn **producer**, nên `? extends T`.
- Đích **consumer**, nên `? super T`.

Compiler có thể tìm một `T` phù hợp từ các constraints của lời gọi. Cấu trúc này không yêu cầu nguồn và đích có element types giống hệt nhau.

## 10. Bài kiểm tra thực hành: di chuyển một phần tử theo PECS

Khác với append toàn bộ nguồn, phương thức sau **lấy phần tử đầu khỏi nguồn** và đưa sang đích. Đây là một bài kiểm tra tốt vì generic type đúng vẫn chưa đủ: nguồn phải thực sự hỗ trợ `remove`, đích phải hỗ trợ `add`.

Tệp **`PecsMoveDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PecsMoveDemo {
    static <T> void moveFirst(
            List<? extends T> source,
            List<? super T> destination) {
        if (!source.isEmpty()) {
            T element = source.remove(0);
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<Number> numbers = new ArrayList<>(List.of(0.5));
        moveFirst(integers, numbers);

        System.out.println(integers);
        System.out.println(numbers);
    }
}
```

Chạy:

```bash
javac --release 17 PecsMoveDemo.java
java PecsMoveDemo
```

Stdout:

```text
[2, 3]
[0.5, 1]
```

**Tại sao biên dịch được?** `source` cho đọc phần tử có kiểu tương thích `T`; `destination` có thể nhận `T`. Hai collection không cần cùng type argument: `Integer` được đọc để thêm vào `List<Number>`.

**Tại sao chưa đủ bảo đảm runtime?** Nếu thay `integers` bằng `List.of(1, 2, 3)`, `remove(0)` có thể ném `UnsupportedOperationException`; generic signature không cam kết mutability. Nếu `destination.add` thất bại sau khi đã xóa nguồn, thao tác không tự rollback: đây là **partial failure** mà một API chuyển dữ liệu production phải xử lý.

Thử sửa code bằng cách truyền `List<Number>` làm nguồn và `List<Integer>` làm đích. Compiler cần từ chối quan hệ ngược này; không dùng raw cast để ép thông qua.

## 11. Bảng kiểm từng tình huống producer/consumer

| Nguồn hoặc đích thực tế | API `List<? extends Number>` | API `List<? super Integer>` | Giải thích |
|---|---|---|---|
| `List<Integer>` | Chấp nhận | Chấp nhận | Integer là subtype Number và chính Integer |
| `List<Double>` | Chấp nhận | Không | Double không phải supertype của Integer |
| `List<Number>` | Chấp nhận | Chấp nhận | Number vừa bound trên, vừa supertype của Integer |
| `List<Object>` | Không | Chấp nhận | Object không phải subtype Number nhưng là supertype Integer |
| `List<String>` | Không | Không | String không thuộc quan hệ bounds này |

Đây là bảng về **type compatibility của đối số list**, không khẳng định một method dùng wildcard tương ứng có thể thực hiện tùy ý mọi thao tác trên list.

Ví dụ, API `List<? extends Number>` cho phép nhận `List<Integer>` nhưng **không được** tùy tiện gọi `add(3.14)`; vì object list có thể chỉ chấp nhận Integer.

Đối với `List<? super Integer>`, khi đọc `get` compiler chỉ bảo đảm `Object`: list thực có thể là `List<Object>`, nên không được giả định phần tử nào cũng là Integer.

## 12. `? extends` không nghĩa là “list chỉ có thể đọc”

Nói “producer extends” giúp chọn type argument nhưng không phải định nghĩa khả năng mutability toàn bộ list.

Ví dụ:

```java
static void removeEverything(List<? extends Number> values) {
    values.clear();
}
```

Đây là một method hợp lệ trong class (giả định import `List`). `clear()` không yêu cầu truyền một phần tử kiểu chưa biết, nên compiler cho phép. Tại runtime, nếu implementation là mutable `ArrayList`, method có thể xóa hết; nếu là `List.of`, có thể ném `UnsupportedOperationException`.

Các thao tác như `size`, `isEmpty`, `contains`, `get`, `clear` không cần cung cấp một giá trị mới loại unknown element. Ngược lại:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
void bad(List<? extends Number> values) {
    values.add(42);
}
```

Một `Number` bất kỳ không chắc phù hợp với concrete captured element type, chẳng hạn khi `values` thật sự tham chiếu `List<Double>`.

`null` là trường hợp đặc biệt có thể đi qua generic compile-time check của `add`, nhưng implementation có thể không hỗ trợ thêm hoặc cấm null. Không nên xây một API producer dựa trên thao tác `add(null)` trừ khi hợp đồng nghiệp vụ đòi hỏi.

## 13. `? super` không nghĩa là “mọi thứ đều có thể thêm”

Xét:

```java
List<? super Integer> target = new ArrayList<Number>();
```

Các thao tác:

```java
target.add(1);                // Hợp lệ: Integer
target.add(Integer.valueOf(2)); // Hợp lệ
Object item = target.get(0); // Hợp lệ
```

Nhưng:

```java
// CỐ Ý KHÔNG BIÊN DỊCH:
target.add(3.5);              // Double không phải Integer
Integer x = target.get(0);   // get chỉ bảo đảm Object
```

Vì sao compiler không cho đọc thành Integer? `target` có thể trỏ tới `List<Object>` với một object khác kiểu Integer đã có sẵn. Mặc dù **những giá trị chính phương thức vừa thêm** đều là Integer, các phần tử khác của list không bị hợp đồng wildcard ràng buộc là Integer.

Nếu thực sự cần đọc lại các giá trị chính mình vừa thêm như Integer, có thể giữ reference tới các object đó, hoặc thiết kế API khác; không ép toàn bộ `List<? super Integer>` sang `List<Integer>`.

## 14. Ví dụ: tác vụ vừa đọc vừa thêm và ảnh hưởng của wildcard

Tệp **`ConsumerReadBackDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ConsumerReadBackDemo {

    static void append(List<? super Integer> target) {
        target.add(7);
        target.add(8);
    }

    public static void main(String[] args) {
        List<Object> objects = new ArrayList<>();
        objects.add("old");

        append(objects);

        Object first = objects.get(0);

        System.out.println(first);
        System.out.println(objects);
        System.out.println(objects.get(1) instanceof Integer);
    }
}
```

Biên dịch/chạy:

```bash
javac ConsumerReadBackDemo.java
java ConsumerReadBackDemo
```

Stdout:

```text
old
[old, 7, 8]
true
```

List thực là `List<Object>`, và đã chứa String trước khi thêm Integer. Vì thế method consumer chỉ nên coi `get` là `Object`.

Nếu implementation cần xử lý dữ liệu hỗn hợp, có thể dùng `instanceof` hoặc một logic validation riêng — không giả định `? super Integer` biến toàn bộ existing elements thành Integer.

## 15. Khi chỉ cần in/đếm: `?` tốt hơn type variable không cần thiết

So sánh:

```java
static <T> void printAll(List<T> values) {
    values.forEach(System.out::println);
}
```

với:

```java
static void printAll(List<?> values) {
    values.forEach(System.out::println);
}
```

Cả hai là method minh họa, cần import `List`.

Nếu `T` không xuất hiện ở kiểu trả về, không liên hệ với tham số khác và không dùng trong phần logic cần quan hệ cụ thể, **wildcard ngắn và diễn đạt đúng ý định hơn**.

Dùng `?` giúp người gọi đưa `List<String>`, `List<Integer>`, `List<LocalDate>` mà không cần method khai báo một `<T>` chỉ để trông có vẻ generic.

Nhưng đừng máy móc thay `List<T>` bằng `List<?>` nếu helper bên trong cần truyền một phần tử kiểu T sang API khác ràng buộc T. Khi có **mối quan hệ kiểu cần giữ**, type variable có tên vẫn có vai trò.

## 16. Wildcard capture: kiểm tra khả năng giữ cùng kiểu qua hai lần truy cập

Một `List<?>` có **một element type chưa biết**, không phải mặc nhiên là `List<Object>`. Nếu lấy một phần tử rồi ghi lại vào **chính list ấy**, có thể nhờ generic helper giữ mối quan hệ kiểu mà không cast.

Thay vì lặp thuật toán hoán đổi, thử yêu cầu mới: **thay phần tử cuối bằng chính phần tử đầu**, giữ nguyên kích thước list.

Tệp **`CaptureLastDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CaptureLastDemo {
    static void copyFirstToLast(List<?> values) {
        copyCaptured(values);
    }

    private static <T> void copyCaptured(List<T> values) {
        if (values.size() >= 2) {
            T first = values.get(0);
            values.set(values.size() - 1, first);
        }
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

        copyFirstToLast(words);
        copyFirstToLast(numbers);

        System.out.println(words);
        System.out.println(numbers);
    }
}
```

Chạy:

```bash
javac --release 17 CaptureLastDemo.java
java CaptureLastDemo
```

Stdout:

```text
[A, B, A]
[1, 2, 1]
```

Ở ranh giới công khai, `List<?>` cho phép caller dùng list của bất kỳ element type. Trong helper, compiler **capture đúng dấu wildcard của một object list cho mỗi lời gọi**, suy luận `T` rồi cho dùng `get` và `set` dưới cùng type. Không được biến `T` thành một `String` do người viết tự đoán; `List<Integer>` cũng phải chạy an toàn.

Bài tập tự kiểm tra: (1) tại sao `Object first = values.get(0); values.set(0, first);` trực tiếp trong method nhận `List<?>` không hợp lệ? (2) nếu muốn ghi phần tử từ một list khác, điều kiện nào cần thêm? **Đáp án:** (1) `Object` không bảo đảm đúng captured element type; (2) cần type variable/wildcard ràng buộc nguồn–đích như PECS, không ghép hai `?` độc lập tùy ý.

`List.of(...)` là unmodifiable; phương thức cần `set` nên ví dụ dùng `ArrayList`. Generic capture bảo vệ **quan hệ kiểu**, không tự bảo đảm mutability hoặc chỉ số hợp lệ.

## 17. Chọn `Collections.copy` hay `addAll`: hai hợp đồng khác nhau

Cả hai có thể chuyển `Integer` vào `List<Number>` một cách type-safe, nhưng **hành vi thay đổi list** không giống nhau:

| Ý định | Lựa chọn | Điều kiện/ảnh hưởng |
|---|---|---|
| **Nối thêm** các phần tử từ nguồn | `destination.addAll(source)` | Đích phải hỗ trợ thêm; size thường tăng |
| **Ghi đè** các slot đã tồn tại | `Collections.copy(destination, source)` | Đích phải có **size ≥ source.size()** và hỗ trợ `set` |
| Chỉ dành capacity mà chưa có element | `new ArrayList<>(capacity)` | `size() == 0`; không đáp ứng `Collections.copy` với nguồn không rỗng |

Ví dụ Java 17 trong method có import `java.util.*`:

```java
List<Integer> source = List.of(7, 8);
List<Number> overwrite = new ArrayList<>(List.of(0, 0, 99));
List<Number> append = new ArrayList<>(List.of(99));

Collections.copy(overwrite, source);
append.addAll(source);

System.out.println(overwrite); // [7, 8, 99]
System.out.println(append);    // [99, 7, 8]
```

Nếu viết `List<Number> empty = new ArrayList<>(source.size());`, rồi gọi `Collections.copy(empty, source)`, generic types vẫn tương thích nhưng runtime có thể ném `IndexOutOfBoundsException` vì **capacity không phải size**. Đây là lỗi về **hợp đồng API**, không phải PECS.

Để ghi nhớ đúng thứ tự tham số, `Collections.copy(destination, source)` nhận **đích trước, nguồn sau**. Quyết định đúng cần cả hai lớp: *kiểu dữ liệu có thể chuyển an toàn không?* và *thao tác runtime cần append hay overwrite, có đủ phần tử/khả năng sửa không?*

## 18. Method `sort`: vì sao comparator dùng `? super T`?

Chữ ký của `List.sort`:

```java
void sort(Comparator<? super E> c)
```

với `E` là element type của List.

Comparator là một đối tượng **tiêu thụ hai E** để so sánh, nên comparator dành cho một supertype phù hợp vẫn có thể so các E.

Tệp **`ComparatorWildcardDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorWildcardDemo {
    record Person(String name, int age) {
    }

    static <T> void sortWith(
            List<T> values, Comparator<? super T> comparator) {
        values.sort(comparator);
    }

    public static void main(String[] args) {
        List<Person> people = new ArrayList<>(List.of(
                new Person("Binh", 21),
                new Person("An", 20)
        ));

        Comparator<Person> byName =
                Comparator.comparing(Person::name);

        sortWith(people, byName);

        System.out.println(
                people.stream().map(Person::name).toList());
    }
}
```

Chạy:

```bash
javac ComparatorWildcardDemo.java
java ComparatorWildcardDemo
```

Stdout:

```text
[An, Binh]
```

Một `Comparator<Object>` có thể có type phù hợp cho `Comparator<? super Person>`, nhưng **hợp lệ về generic type không chứng minh comparator ấy có thứ tự nghiệp vụ đúng**.

Không thay thành `Comparator<? extends T>`: comparator cần **nhận** T để `compare`, chứ không phải sản sinh ra T.

## 19. `Function<? super T, ? extends R>`: hai hướng trong một chữ ký

`Function<T, R>` **nhận T** và **trả R**. Một helper linh hoạt có thể nhận:

```java
Function<? super T, ? extends R>
```

Vì:

- Đầu vào của function là consumer của T → `? super T`.
- Đầu ra của function là producer của R → `? extends R`.

Tệp **`FunctionVarianceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class FunctionVarianceDemo {

    static <T, R> List<R> transform(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {

        List<R> result = new ArrayList<>();

        for (T element : source) {
            result.add(mapper.apply(element));
        }

        return result;
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 3);

        Function<Number, String> description =
                n -> "value=" + n.intValue();

        List<String> output = transform(source, description);

        System.out.println(output);
    }
}
```

Biên dịch/chạy:

```bash
javac FunctionVarianceDemo.java
java FunctionVarianceDemo
```

Stdout:

```text
[value=2, value=3]
```

`List<Integer>` sản sinh những phần tử tương thích với `T = Number`; `Function<Number,String>` tiêu thụ chúng; list kết quả có `R = String`.

Hợp đồng này minh họa rằng **PECS cũng áp dụng cho generic functional interfaces** — không chỉ collections.

## 20. Nested Generics: phải xét từng cấp

Có hai lớp generic:

```java
List<List<Integer>>
```

Không thể tự coi đây là `List<List<Number>>`, vì generic invariance áp dụng ở **mỗi cấp**.

Nhưng nếu API chỉ cần đọc các nhóm số, có thể dùng:

```java
List<? extends List<? extends Number>>
```

Cấp ngoài `? extends` nói “các phần tử là một dạng List phù hợp”; cấp trong `? extends Number` nói “các phần tử của từng list có thể được đọc như Number”.

Tệp **`NestedWildcardDemo.java`**:

```java
import java.util.List;

public class NestedWildcardDemo {

    static double sumAll(
            List<? extends List<? extends Number>> groups) {

        double sum = 0;

        for (List<? extends Number> group : groups) {
            for (Number value : group) {
                sum += value.doubleValue();
            }
        }

        return sum;
    }

    public static void main(String[] args) {
        List<List<Integer>> batches =
                List.of(List.of(1, 2), List.of(3));

        System.out.println(sumAll(batches));
    }
}
```

Chạy:

```bash
javac NestedWildcardDemo.java
java NestedWildcardDemo
```

Stdout:

```text
6.0
```

`List<List<Integer>>` không phải subtype của `List<List<Number>>`, nhưng phù hợp với cấu trúc wildcard nhiều cấp cho bài toán **chỉ đọc**.

Cần cẩn thận nếu muốn thêm một list mới vào outer collection: outer wildcard cũng có captured element type chưa biết, nên compiler không cho chèn tùy ý một `List<Number>`.

## 21. Return type: vì sao tránh `List<?>` khi caller cần dữ liệu typed?

Một API có thể trả:

```java
List<?> load();
```

Nếu thực sự không có schema element type, đây là cách trả trung thực: caller chỉ biết có một list phần tử chưa xác định.

Nhưng nếu producer biết danh sách là String, chữ ký:

```java
List<String> loadNames();
```

truyền nhiều thông tin hơn; caller có thể đọc phần tử như `String` mà không cast.

Với generic factory:

```java
static <T> List<T> empty() {
    return new ArrayList<>();
}
```

caller có thể viết:

```java
List<String> names = empty();
```

Compiler dựa trên target type để suy luận T.

Một `List<? extends Number>` return type có thể phù hợp nếu API chủ đích giấu subtype nhưng cho phép đọc như Number. Tuy nhiên nó gây khó khăn cho caller khi muốn thêm giá trị Number. Đừng dùng wildcard return type chỉ để chứng tỏ mã “generic hơn” nếu một result type cụ thể hoặc named type variable phù hợp hơn.

## 22. Khi nào phải dùng `T` ở nhiều input?

Xét hai biến cùng element type:

```java
static <T> void moveOne(List<T> source, List<T> target) {
    target.add(source.remove(0));
}
```

Method có thể dùng trong một class với import `List`. Nó yêu cầu hai list được xem dưới cùng một `T` cho thao tác đọc–ghi; tuy nhiên cách viết này có thể **quá chặt** nếu nguồn là `List<Integer>` và đích là `List<Number>`.

Linh hoạt hơn:

```java
static <T> void moveOne(
        List<? extends T> source,
        List<? super T> target) {
    target.add(source.remove(0));
}
```

Sự thay đổi cho phép quan hệ subtype hợp lệ mà không mất safety. Nếu mục đích là “sao chép rồi xóa một phần tử”, source phải mutable; generic type checking không bảo đảm remove thành công trên `List.of`.

**Bài học:** Dùng T để **liên kết**, nhưng xem xét wildcard quanh T để mô tả variance theo data flow.

## 23. `?` và `Object` không tương đương

Ví dụ:

```java
List<String> strings = List.of("a", "b");

List<?> unknown = strings; // Hợp lệ.

// CỐ Ý KHÔNG BIÊN DỊCH:
// List<Object> objects = strings;
```

`List<?>` chấp nhận list của một type argument bất kỳ. `List<Object>` lại là list có chính element type `Object`; nó không nhận trực tiếp `List<String>`.

Một method nhận `List<Object>` có thể thêm một `Integer`; nếu compiler cho truyền `List<String>` vào thì contract của `List<String>` sẽ hỏng. Vì vậy Java không cho phép phép chuyển ấy.

Nếu chỉ duyệt rồi in, `List<?>` là lựa chọn đúng hơn `List<Object>`. Nếu muốn một kho hỗn hợp thực sự mà code có quyền thêm `String`, `Integer`, v.v., `List<Object>` mới thể hiện đúng hợp đồng.

## 24. Không dùng raw type để “linh hoạt hơn”

Raw type:

```java
List raw = new ArrayList();
```

bỏ type arguments thay vì mô tả quan hệ kiểu linh hoạt. Nó có thể sinh warnings `rawtypes` và khiến một số method invocations trở thành unchecked.

Một thiết kế:

```java
static void show(List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

giữ compiler checking mà vẫn nhận các list element types khác nhau.

Không thay `List<? extends Number>` bằng raw `List` rồi cast từng element sang Number để tránh viết wildcard. Khi cần đọc số, bounded wildcard đã mô tả được ràng buộc tại compile time, với diagnostic tốt hơn.

Bật:

```bash
javac -Xlint:rawtypes,unchecked YourClass.java
```

để tìm các ranh giới raw/unchecked trong code thực tế. `@SuppressWarnings` không phải cách sửa quan hệ kiểu sai.

## 25. `extends`/`super` không quyết định `null` và mutability

Một `List<? super Integer>` có thể là `ArrayList<Object>` mutable hoặc một collection có thao tác thêm bị cấm. Một `List<? extends Number>` có thể có phần tử null nếu implementation cho phép.

Kiểu generic chỉ ràng buộc **element type**, không xác định đầy đủ:

- Có cho phép `null` không?
- Có cho phép thêm/xóa/set không?
- Có đồng thời nhiều threads thay đổi không?
- Có được phép sửa dữ liệu từ reference khác không?
- Có bị ràng buộc thứ tự hoặc uniqueness không?

Ví dụ `List.of(1,2)` không cho `add` vì unmodifiable, không liên quan việc nó có type `List<Integer>` hay `List<? extends Number>` khi nhìn qua một tham chiếu.

Khi viết API production, hãy ghi các điều kiện mutability/ownership/nullability **riêng** ngoài generic signature, và kiểm thử các đường thao tác tương ứng.

## 26. Bảng lựa chọn theo API Java thường gặp

| API hoặc tình huống | Chữ ký/mẫu quan trọng | Vì sao |
|---|---|---|
| `Collections.copy` | `<T> copy(List<? super T> dest, List<? extends T> src)` | Source producer, destination consumer |
| `List.sort` | `sort(Comparator<? super E>)` | Comparator nhận E để so |
| `Collection.addAll` | `addAll(Collection<? extends E>)` | Collection nguồn tạo các E |
| `Stream.map` | `Function<? super T, ? extends R>` | Hàm tiêu thụ T, sản sinh R |
| `Collections.max` (với comparator) | `<T> T max(Collection<? extends T>, Comparator<? super T>)` | Source đọc T, comparator nhận T, return T |
| Duyệt không cần quan hệ kiểu | `void inspect(Collection<?>)` | Không cần đặt tên T |
| Lấy một phần tử đúng element type | `<T> T first(List<T>)` | Input liên kết với return |
| Chuyển `List<Integer>` sang `List<Number>` | `<T> transfer(List<? extends T>, List<? super T>)` | Phù hợp quan hệ con–cha |
| Nhận một list chứa Object thật sự và thêm nhiều loại | `List<Object>` | Element type cụ thể Object |

Các chữ ký trong bảng là **mẫu rút gọn để học**. Khi thực hiện API cụ thể, nên đọc javadoc của overload đúng; ngoài Generics còn có preconditions như capacity/size, mutability, `null`, comparator contract.

## 27. Chọn cú pháp bằng 5 câu hỏi

Khi thiết kế một method, có thể tự thực hiện trình tự sau:

**Câu 1: Có cần gọi operation dựa vào element type cụ thể không?**

- Nếu chỉ `size`, `isEmpty`, logging chung: cân nhắc `<?>`.
- Nếu đọc như `Number` để gọi `doubleValue`: cân nhắc `<? extends Number>`.

**Câu 2: Có cần đưa object kiểu X vào collection do caller cung cấp không?**

- Nếu cần thêm `Integer`: `<? super Integer>` phù hợp hơn `<? extends Integer>`.
- Nếu chỉ thêm cùng element type được khai báo cụ thể: có thể dùng `List<T>`.

**Câu 3: Kiểu ở hai vị trí phải liên hệ với nhau không?**

- Input và return cùng type: khai báo `<T>`.
- Source và sink liên hệ: `<T>` kết hợp `? extends T`/`? super T`.

**Câu 4: Caller cần đưa subtype/supertype vào không?**

- Chữ ký quá chặt `List<T>` ở mọi nơi có thể loại bỏ các cuộc gọi an toàn như `List<Integer>` → `List<Number>`.
- Dùng variance thích hợp khi data flow cho phép.

**Câu 5: Điều gì nằm ngoài generic type checking?**

- Null, mutability, index, concurrency, type erasure, nested content.
- Bổ sung contract và test phù hợp.

Nên chọn chữ ký **đơn giản nhất diễn đạt đúng các quan hệ cần thiết**, không chọn dạng có nhiều wildcard nhất.

## 28. Tự đánh giá — phần A: chọn một trong bốn hướng

Với mỗi yêu cầu, hãy thử chọn từ **`T` / `?` / `? extends` / `? super`** trước khi xem đáp án.

| Mã | Tình huống | Gợi ý API cần điền |
|---|---|---|
| A1 | Nhận mọi danh sách để in số phần tử | `void count(List<...> list)` |
| A2 | Tính tổng mọi `Number` từ các list chuyên biệt | `sum(List<...> list)` |
| A3 | Cho phép caller đưa `List<Object>` để thêm `Integer` | `append(List<...> dest)` |
| A4 | Trả đúng element type của list truyền vào | `static <...> ... first(List<...>)` |
| A5 | Đưa `List<Double>` sang `List<Number>` | `transfer(List<...> src, List<...> dst)` |
| A6 | Đọc mọi list chỉ như `Object` | `inspect(List<...>)` |
| A7 | Sort `List<Person>` bằng `Comparator<Object>` phù hợp | `sort(List<T>, Comparator<...>)` |
| A8 | Hàm nhận T và tạo R, cho phép input supertype/output subtype | `Function<..., ...>` |
| A9 | Type variable chỉ chấp nhận `Number` và subtype | `static <...> ...` |
| A10 | Chuyển vị trí hai phần tử trong một `List<?>` | Helper dùng một type variable captured |

### Đáp án phần A

| Mã | Lựa chọn | Lý do ngắn |
|---|---|---|
| A1 | `List<?>` | Không liên hệ tới element type |
| A2 | `List<? extends Number>` | Đọc các phần tử như Number |
| A3 | `List<? super Integer>` | Đích nhận Integer |
| A4 | `<T> T first(List<T>)` | T liên kết input và output |
| A5 | `<T> transfer(List<? extends T>, List<? super T>)` | PECS hai phía |
| A6 | `List<?>` | Element type chưa biết, chỉ đọc Object |
| A7 | `Comparator<? super T>` | Comparator tiêu thụ T |
| A8 | `Function<? super T, ? extends R>` | Function nhận T, trả R |
| A9 | `<T extends Number>` | Upper bound ở khai báo type variable |
| A10 | `<T>` trong helper nhận `List<T>` | Capture wildcard để `set` lại cùng element type |

Tự chấm: mỗi lựa chọn đúng và có giải thích theo luồng dữ liệu được **2 điểm**, đúng nhưng chưa giải thích được **1 điểm**, sai **0 điểm**. Tối đa **20 điểm** cho phần A.

Đây là thang tự kiểm tra kiến thức, không phải kết quả từ một công cụ chấm tự động.

## 29. Tự đánh giá — phần B: có biên dịch không?

Xét các mảnh code với imports thích hợp, chạy trong một method, và giả định các biến được khai báo ngay trước khi dùng. Đánh dấu **hợp lệ** hay **không hợp lệ**, sau đó nêu lý do.

**B1**

```java
List<Integer> xs = new ArrayList<>();
List<? extends Number> ys = xs;
```

**B2**

```java
List<Integer> xs = new ArrayList<>();
List<Number> ys = xs;
```

**B3**

```java
List<Object> objects = new ArrayList<>();
List<? super Integer> sink = objects;
sink.add(10);
```

**B4**

```java
List<? super Integer> sink = new ArrayList<Number>();
Integer n = sink.get(0);
```

**B5**

```java
List<? extends Number> source = List.of(1, 2);
Number n = source.get(0);
```

**B6**

```java
List<? extends Number> source = new ArrayList<Integer>();
source.add(10);
```

**B7**

```java
List<?> any = new ArrayList<String>();
any.add(null);
```

**B8**

```java
List<?> any = new ArrayList<String>();
any.add("new");
```

**B9**

```java
List<? super Number> sink = new ArrayList<Object>();
sink.add(1.5);
```

**B10**

```java
List<? super Number> sink = new ArrayList<Integer>();
```

**B11**

```java
List<List<Integer>> batches = List.of(List.of(1));
List<? extends List<? extends Number>> readOnly = batches;
```

**B12**

```java
List<String> names = new ArrayList<>();
names.sort(Comparator.naturalOrder());
```

### Đáp án phần B và lý do

| Mã | Kết quả | Lý do |
|---|---|---|
| B1 | Hợp lệ | `Integer` nằm dưới `Number`; wildcard upper bound chấp nhận |
| B2 | Không hợp lệ | Generic invariance |
| B3 | Hợp lệ | `Object` là supertype của `Integer`; thêm Integer an toàn |
| B4 | Không hợp lệ về kiểu | `get` chỉ bảo đảm `Object`; không gán thẳng vào `Integer`. Nếu sửa thành `Object`, `get(0)` còn có thể ném `IndexOutOfBoundsException` vì list mới rỗng |
| B5 | Hợp lệ | Đọc Number từ upper-bounded wildcard |
| B6 | Không hợp lệ | Không thêm Integer tùy ý vào `? extends Number` |
| B7 | Hợp lệ về kiểu | `null` có thể được truyền cho `add` của wildcard unknown; backing `ArrayList` ở đây mutable |
| B8 | Không hợp lệ | Không thêm String non-null khi captured element type chưa biết |
| B9 | Hợp lệ | `Number` là lower bound; có thể thêm `Double` là subtype của Number |
| B10 | Không hợp lệ | `Integer` không phải supertype của `Number` |
| B11 | Hợp lệ | Upper-bounded wildcard ở cả hai cấp cho phép đọc nested lists |
| B12 | Hợp lệ | `String` có natural order, comparator có kiểu phù hợp với sort |

Câu B4 đặc biệt hữu ích: phải phân biệt **lỗi compile-time** do gán `Object` vào Integer với **lỗi runtime** do đọc index 0 của list rỗng nếu đổi kiểu biến.

Tự chấm mỗi câu đúng **1 điểm**, tổng tối đa **12 điểm**.

## 30. Tự đánh giá — phần C: sửa API sai hoặc quá chặt

### C1. Chỉ đọc nhưng chữ ký quá cụ thể

Ban đầu:

```java
static void printAll(List<Object> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Vấn đề: caller không thể đưa trực tiếp `List<String>` dù method chỉ đọc.

**Đáp án:** Đổi thành `List<?>`.

### C2. Tính tổng nhưng dùng raw List

Ban đầu:

```java
static double sum(List numbers) {
    double result = 0;
    for (Object n : numbers) {
        result += ((Number) n).doubleValue();
    }
    return result;
}
```

**Đáp án ưu tiên:** `static double sum(List<? extends Number> numbers)`. Khi đó duyệt bằng `for (Number n : numbers)` để compiler bảo vệ contract.

### C3. Chỉ thêm Integer nhưng tham số đích quá hẹp

Ban đầu:

```java
static void addDefaults(List<Integer> dest) {
    dest.add(1);
}
```

Nếu muốn nhận cả `List<Number>` và `List<Object>`:

**Đáp án:** Đổi thành `List<? super Integer>`.

### C4. Cần trả lại đúng element type

Ban đầu:

```java
static Object first(List<?> items) {
    return items.get(0);
}
```

Nếu caller mong `String` khi truyền `List<String>`:

**Đáp án:** `static <T> T first(List<T> items)`.

### C5. Copy nguồn Integer vào đích Number

Ban đầu:

```java
static <T> void copy(List<T> src, List<T> dst) {
    dst.addAll(src);
}
```

Nếu muốn hỗ trợ quan hệ subtype an toàn:

**Đáp án:** `static <T> void copy(List<? extends T> src, List<? super T> dst)`.

### C6. Comparator bị đặt `extends`

Ban đầu:

```java
static <T> void sort(
        List<T> values, Comparator<? extends T> cmp) {
    // Không dùng trực tiếp được cho values.sort(cmp).
}
```

**Đáp án:** Comparator nhận T, nên dùng `Comparator<? super T>`.

### C7. Mapper bị đảo variance

Ban đầu:

```java
Function<? extends T, ? super R> mapper
```

Đây thường không phù hợp khi method muốn **đưa T vào function và đọc R ra**.

**Đáp án:** `Function<? super T, ? extends R>`.

### C8. Nested list chỉ để đọc

Ban đầu:

```java
static double sumGroups(List<List<Number>> groups) {
    // ...
    return 0;
}
```

Nếu muốn nhận `List<List<Integer>>`:

**Đáp án:** Dùng `List<? extends List<? extends Number>>` nếu chỉ cần đọc cả hai cấp.

Phần C không cần viết lại cả class; mục tiêu là lý giải **chữ ký public API**. Tự chấm 0–2 điểm cho mỗi tình huống (lựa chọn + giải thích), tối đa **16 điểm**.

## 31. Ba thử thách bổ sung không nên giải bằng cast

### Thử thách 1 — Sao chép rồi sắp xếp

Cần nhận `Collection<? extends T>`, tạo một `List<T>` và sort với `Comparator<? super T>`.

Gợi ý:

```java
static <T> List<T> sortedCopy(
        Collection<? extends T> source,
        Comparator<? super T> order) {
    List<T> result = new ArrayList<>(source);
    result.sort(order);
    return result;
}
```

Đặt method trong class và import `java.util.Collection`, `List`, `ArrayList`, `Comparator`.

Không ép `Collection<? extends T>` thành `Collection<T>`: constructor nhận producer phù hợp mà không cần cast.

### Thử thách 2 — Đổi chỗ trong `List<?>`

Yêu cầu public method nhận `List<?>` nhưng không dùng raw type/unchecked cast.

**Đáp án:** Gọi một helper `<T> void swapCaptured(List<T>, int, int)` từ wrapper `swapAny(List<?>, int, int)` như chương trình ở phần 16. Đây là wildcard capture.

### Thử thách 3 — Cần lưu các giá trị khác nhau vào một cấu trúc

Không dùng `List<? super Integer>` nếu mục tiêu là vừa lưu String vừa Integer mà element type mong muốn thật sự là Object.

**Đáp án:** `List<Object>` là chính xác nếu code có quyền thêm nhiều reference types và đọc như Object. PECS không phải giải pháp cho mọi bài toán collection.

## 32. Thang tự đánh giá tổng hợp

Ba phần trắc nghiệm và sửa API có tối đa:

| Phần | Số mục | Điểm tối đa |
|---|---:|---:|
| A. Chọn hướng cú pháp | 10 | 20 |
| B. Có biên dịch không? | 12 | 12 |
| C. Sửa chữ ký API | 8 | 16 |
| **Tổng** | **30** | **48** |

Gợi ý tự diễn giải (chỉ là rubric học tập):

- **0–20 điểm:** cần ôn lại invariance và khác biệt giữa đọc/ghi.
- **21–32 điểm:** nắm cú pháp cơ bản, cần luyện type inference và nhiều tham số.
- **33–41 điểm:** chọn đúng phần lớn tình huống; chú ý nested generics, capture, mutability.
- **42–48 điểm:** có nền tảng tốt; thử tự thiết kế API từ yêu cầu thực và review edge cases.

Điểm số không có ý nghĩa chứng chỉ; quan trọng hơn là **mỗi lựa chọn phải có lời giải thích theo data flow** và không dựa vào unchecked casts.

Để kiểm chứng, hãy đặt các ví dụ được đánh dấu **không hợp lệ** vào file thử riêng, chạy `javac` và tự đọc diagnostic. Không đưa các dòng cố ý sai vào file chương trình đã gắn stdout chạy được.

## 33. Những lỗi tư duy phổ biến

**Lỗi 1 — “Có extends thì list read-only”.** Không chính xác; các operation không nhận giá trị element type như `clear()` vẫn có thể biên dịch, tùy mutability runtime.

**Lỗi 2 — “Có super thì đọc được T”.** Không; đọc từ `List<? super T>` chỉ có kiểu an toàn chung là `Object`.

**Lỗi 3 — “`List<Integer>` là `List<Number>`”.** Sai vì invariance. Dùng `List<? extends Number>` nếu chỉ cần producer.

**Lỗi 4 — “`List<?>` chính là `List<Object>`”.** Không; wildcard chưa biết khác element type Object cụ thể.

**Lỗi 5 — “`?` làm API luôn tốt hơn `<T>`”.** Không; type variable liên kết input/output và nhiều tham số.

**Lỗi 6 — “`<T extends Number>` và `? extends Number` giống nhau”.** Không; một cái khai báo type variable, cái kia là type argument ở vị trí dùng.

**Lỗi 7 — “Có thể khai báo `<T super Integer>`”.** Không hợp lệ trong Java.

**Lỗi 8 — “`List<? super Number>` chấp nhận `List<Integer>`”.** Không; Integer không phải supertype của Number.

**Lỗi 9 — “Method thêm Integer vào `List<? super Integer>` bảo đảm mọi element đều Integer”.** Không; list có thể chứa object khác từ trước.

**Lỗi 10 — “Dùng `Comparator<? extends T>` vì comparator liên quan T”.** Sai hướng: comparator **tiêu thụ** T, nên cần `? super T`.

**Lỗi 11 — “Function đầu vào nên extends, đầu ra nên super”.** Sai theo hướng flow thông thường; dạng linh hoạt là `Function<? super T, ? extends R>`.

**Lỗi 12 — “Wildcard lồng một cấp đủ cho mọi nested generics”.** Không; phải xét variance từng lớp của `List<List<T>>`.

**Lỗi 13 — “Có thể dùng raw List rồi cast để hết lỗi compile”.** Có thể mất safety và tạo unchecked warnings/heap pollution.

**Lỗi 14 — “`List<T>` bắt buộc cùng runtime concrete class ở mọi chỗ”.** Không. Compiler có thể suy luận T là common supertype; Java generic type variables không phải runtime equality assertions.

**Lỗi 15 — “Generic signature cho biết list mutable”.** Không; `List.of` vẫn unmodifiable.

**Lỗi 16 — “`Collections.copy` tự kéo dài destination”.** Không; destination phải có đủ phần tử để thay.

**Lỗi 17 — “Wildcard capture cần unchecked cast”.** Không; generic helper có thể capture wildcard an toàn.

**Lỗi 18 — “Return type dùng wildcard là luôn linh hoạt nhất”.** Không; caller có thể cần type argument rõ để thao tác typed mà không cast.

**Lỗi 19 — “`? extends T` cho phép thêm bất kỳ subtype của T”.** Không; captured subtype thực có thể hẹp hơn giá trị được thêm.

**Lỗi 20 — “PECS bảo đảm thread safety hoặc null safety”.** Không; chúng là hợp đồng kiểu, không phải chính sách đồng thời/dữ liệu.

## 34. Checklist trước khi chốt generic API

1. Nêu rõ method **đọc**, **ghi** hay **vừa đọc vừa ghi** qua mỗi tham số.
2. Hỏi element type có cần xuất hiện ở return type hoặc tham số khác không.
3. Nếu không cần quan hệ type, cân nhắc wildcard `?`.
4. Nếu đọc dưới một upper bound, cân nhắc `? extends Bound`.
5. Nếu ghi các giá trị kiểu T vào một consumer, cân nhắc `? super T`.
6. Nếu cần liên kết input/output, khai báo `<T>` hoặc `<T, R>` rõ ràng.
7. Khi kết hợp source và sink, thử chữ ký PECS với các subtype/supertype thực tế.
8. Thử compile cả `List<Integer>`, `List<Number>`, `List<Object>` để phát hiện bounds bị đảo.
9. Không dùng `List<Object>` thay `List<?>` khi API chỉ đọc list bất kỳ.
10. Không dùng raw types để bỏ qua lỗi suy luận generic.
11. Với nested types, phân tích từng mức wildcard riêng.
12. Nếu gặp capture error, cân nhắc helper `<T>` thay vì unchecked cast.
13. Nếu dùng comparator, xác nhận chiều **consumer** của `Comparator<? super T>`.
14. Nếu dùng function, xác nhận input `super`, output `extends`.
15. Kiểm tra null, mutability, ownership và index preconditions ngoài chữ ký type.
16. Chọn return type giúp caller có đủ thông tin, tránh wildcard nếu không cần.
17. Viết bài test cho cả accepted và rejected calls ở compile-time.
18. Đọc API Java chuẩn có cùng patterns để đối chiếu.
19. Bật `javac -Xlint:unchecked,rawtypes` khi làm việc với legacy code.
20. Ghi rõ vì sao mỗi wildcard được chọn, thay vì chỉ ghi “dùng PECS”.

## 35. Tóm tắt và nguồn chuẩn

Một cách ghi nhớ nhanh là:

```text
Không quan tâm kiểu phần tử           → ?
Đọc các giá trị theo kiểu Bound       → ? extends Bound
Thêm các giá trị kiểu T vào đích      → ? super T
Liên kết input/output hoặc nhiều vị trí → <T>
```

Đừng chọn theo hình thức. Hãy **vẽ hướng dữ liệu**: đâu là nơi sản sinh giá trị, đâu là nơi nhận giá trị, và đâu là mối quan hệ kiểu phải được giữ giữa các tham số và kết quả.

Trong Java, **`T` là type variable được đặt tên; `?` là wildcard chưa xác định; `? extends` tạo góc nhìn producer, `? super` tạo góc nhìn consumer**. Generic invariance giải thích vì sao cần wildcard để cho phép subtype/supertype ở những nơi an toàn.

Bài thực hành tổng hợp nên kết thúc khi bạn có thể tự viết và giải thích các chữ ký:

```java
static void inspect(List<?> values)

static double sum(List<? extends Number> values)

static void append(List<? super Integer> destination)

static <T> T first(List<T> values)

static <T> void copy(
        List<? extends T> source,
        List<? super T> destination)

static <T, R> List<R> map(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper)
```

Đây là **mẫu chữ ký minh họa**; không copy thành những declarations thiếu method bodies rồi mong biên dịch. Hãy dựa vào các chương trình hoàn chỉnh ở phần trước để thực hành.

Tài liệu Java 17 để đối chiếu:

- [JLS §4.5 — Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): type arguments và wildcard.
- [JLS §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): T và upper bounds.
- [JLS §4.10 — Subtyping](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10): quan hệ generic subtype.
- [JLS §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): wildcard capture.
- [JLS §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): inference cho generic methods.
- [Java SE 17 `java.util.Collections`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html): `copy`, `max`, `sort`.
- [Java SE 17 `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `addAll`, `sort`, `get`, `set`.
- [Java SE 17 `java.util.function.Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): functional interface nhận T và trả R.
- [Java SE 17 `java.util.Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparator generic và `? super T`.