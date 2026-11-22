# `Collection.toArray(IntFunction)` với constructor reference — Java 11+

## 1. Mục tiêu: chuyển Collection thành mảng có kiểu xác định

Khi sử dụng `List`, `Set` hoặc một `Collection` khác, đôi khi ta cần chuyển các phần tử sang mảng để truyền cho API nhận `String[]`, `Integer[]`, `Person[]`, v.v.

Từ **Java 11**, interface `java.util.Collection` có thêm overload:

```java
<T> T[] toArray(java.util.function.IntFunction<T[]> generator)
```

Cách dùng tiêu biểu:

```java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");
String[] namesArray = names.toArray(String[]::new);
```

Ở đây, `String[]::new` là **array constructor reference** (tham chiếu đến bộ tạo mảng), dùng để cung cấp hàm tạo mảng `String[]` với độ dài do API yêu cầu. Kết quả là mảng `String[]` thực sự ở runtime, chứa các phần tử của `names`.

Phương thức này **vẫn được hỗ trợ trong Java hiện đại**, không phải API đã bị loại bỏ. Đây là một cách viết ngắn và rõ ý cho việc chuyển `Collection` thành mảng có kiểu cụ thể.

## 2. Hiểu đúng `IntFunction<T[]>` và `String[]::new`

### 2.1. `IntFunction<R>` là gì?

`IntFunction<R>` là functional interface trong `java.util.function`. Phương thức trừu tượng của nó nhận một giá trị `int` và trả về giá trị kiểu `R`:

```java
R apply(int value);
```

Trong `Collection.toArray`, kiểu `R` là **mảng `T[]`**. Vì vậy generator có vai trò cung cấp mảng đúng kiểu thành phần (component type).

Ba cách biểu diễn sau cùng thể hiện ý tưởng “nhận độ dài rồi tạo mảng `String[]`”:

```java
import java.util.function.IntFunction;

IntFunction<String[]> byLambda = size -> new String[size];
IntFunction<String[]> byReference = String[]::new;
IntFunction<String[]> byMethod = StringArrayFactory::create;

// Đoạn này minh họa cú pháp và dùng cùng class sau.
class StringArrayFactory {
    static String[] create(int size) {
        return new String[size];
    }
}
```

Hai cách đầu thường đủ dùng. `String[]::new` ngắn hơn và thể hiện rõ kiểu mảng cần tạo; nó **không phải** `String::new` (tham chiếu constructor tạo đối tượng `String` riêng lẻ).

### 2.2. Dùng trực tiếp với `Collection`

Hai dòng sau tương đương về ý định và kiểu kết quả:

```java
String[] a = names.toArray(String[]::new);
String[] b = names.toArray(length -> new String[length]);
```

Compiler dựa vào overload `toArray(IntFunction<T[]>)` để nhận biết `String[]::new` cần cung cấp một `IntFunction<String[]>`.

- **`T[]` trong kết quả:** kiểu mảng được tạo, chẳng hạn `String[]`.
- **`generator`:** hàm nhận `int` và tạo mảng đúng kiểu đó.
- **`T`:** tham số kiểu của *phương thức* `toArray`; không bắt buộc trùng hoàn toàn với `E` trong `Collection<E>`. Chính vì vậy cần hiểu rủi ro `ArrayStoreException` ở mục 7.

### 2.3. Không suy đoán độ dài truyền vào generator

Một điểm quan trọng trong **hợp đồng API**: triển khai mặc định của `Collection.toArray(IntFunction)` gọi generator bằng **`0`**, sau đó chuyển mảng nhận được cho overload `toArray(T[])`. Đối với một collection có nhiều phần tử, generator **không nhất thiết** được gọi với `collection.size()`.

Ví dụ tư duy:

```java
Collection<String> words = List.of("A", "B", "C");
String[] array = words.toArray(String[]::new);
```

Mảng kết quả chứa **3 phần tử**, mặc dù triển khai mặc định có thể dùng `String[]::new` để tạo mảng ban đầu độ dài **0** rồi nhờ `toArray(T[])` cấp phát mảng cuối phù hợp. Một triển khai cụ thể có thể override phương thức này. Vì vậy, **đừng gắn side effect hoặc logic kiểm đếm vào generator**, cũng đừng khẳng định generator luôn được gọi một lần với kích thước collection.

Đây là khác biệt cần nhớ so với `Stream.toArray(IntFunction)`: Stream có cơ chế thu thập và phân vùng phần tử riêng; generator có thể được gọi với các độ dài khác, nhất là khi xử lý song song. Cả hai đều nhận array constructor reference, nhưng không nên suy luận từ cơ chế của Stream sang Collection.

## 3. Ví dụ Java 11 hoàn chỉnh, chạy được

Tạo tệp **`CollectionToArrayDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CollectionToArrayDemo {
    public static void main(String[] args) {
        Collection<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));
        String[] nameArray = names.toArray(String[]::new);
        String[] byLambda = names.toArray(length -> new String[length]);
        String[] classic = names.toArray(new String[0]);

        System.out.println("names = " + Arrays.toString(nameArray));
        System.out.println("component = "
                + nameArray.getClass().getComponentType().getSimpleName());
        System.out.println("same as lambda = " + Arrays.equals(nameArray, byLambda));
        System.out.println("same as classic = " + Arrays.equals(nameArray, classic));
        System.out.println("raw type = "
                + names.toArray().getClass().getComponentType().getSimpleName());

        String[] empty = List.<String>of().toArray(String[]::new);
        System.out.println("empty length = " + empty.length);

        Set<Integer> ids = new LinkedHashSet<>(List.of(30, 10, 20, 10));
        System.out.println("ids = " + Arrays.toString(ids.toArray(Integer[]::new)));

        nameArray[0] = "Changed";
        System.out.println("collection first = " + names.iterator().next());

        Collection<Number> mixed = List.of(1, 2.5);
        try {
            Integer[] wrong = mixed.toArray(Integer[]::new);
            System.out.println("wrong length = " + wrong.length);
        } catch (ArrayStoreException exception) {
            System.out.println("wrong array type = ArrayStoreException");
        }

        List<String> allowsNull = new ArrayList<>();
        allowsNull.add(null);
        allowsNull.add("ok");
        System.out.println("nullable = "
                + Arrays.toString(allowsNull.toArray(String[]::new)));
    }
}
```

Biên dịch bằng JDK 11 trở lên (với JDK mới, `--release 11` bảo đảm chỉ dùng API/ngôn ngữ Java 11):

```bash
javac --release 11 -encoding UTF-8 CollectionToArrayDemo.java
java CollectionToArrayDemo
```

**Đầu ra chính xác:**

```text
names = [An, Binh, Chi]
component = String
same as lambda = true
same as classic = true
raw type = Object
empty length = 0
ids = [30, 10, 20]
collection first = An
wrong array type = ArrayStoreException
nullable = [null, ok]
```

Giải thích từng nhóm:

1. `names.toArray(String[]::new)` trả về `String[]`, vì vậy `getComponentType().getSimpleName()` là `String`.
2. Lambda tạo mảng và constructor reference trả về **cùng nội dung**, dù đây là các lần chuyển đổi độc lập. `toArray(new String[0])` là overload khác nhưng cũng cho mảng `String[]` chứa cùng phần tử.
3. `names.toArray()` không có đối số tạo mảng `Object[]`. Chỉ việc `Collection<String>` có generic `String` **không** biến kết quả của overload không đối số thành `String[]`.
4. Collection rỗng cho mảng đúng kiểu với độ dài `0`.
5. `LinkedHashSet` loại phần tử `10` trùng và giữ **thứ tự chèn**, nên mảng là `[30, 10, 20]`. Không áp dụng khẳng định thứ tự này cho mọi `Set`.
6. Việc sửa `nameArray[0]` không làm đổi phần tử trong `names`; chuyển đổi này tạo mảng chứa các **tham chiếu tới phần tử**, không phải deep copy các đối tượng bên trong.
7. `Collection<Number>` chứa `Double 2.5` không thể lưu hết vào `Integer[]` nên gây `ArrayStoreException` khi chạy.
8. Nếu loại Collection cho phép phần tử `null` (như `ArrayList`), mảng kết quả vẫn có thể chứa `null`. Lưu ý `List.of(...)` không cho phép tạo list chứa `null`.

## 4. Phân biệt ba overload `toArray`

| Cách gọi | Kiểu kết quả / ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `collection.toArray()` | `Object[]` | Không ép trực tiếp thành `String[]` được chỉ vì collection chứa `String` |
| `collection.toArray(new String[0])` | `String[]` | Cách dùng `toArray(T[])`; **vẫn hợp lệ và được hỗ trợ hiện nay** |
| `collection.toArray(String[]::new)` | `String[]` | Cách dùng `toArray(IntFunction<T[]>)`, có từ Java 11; gọn khi muốn nêu kiểu mảng |
| `collection.toArray(String[]::new)` với Collection rỗng | `String[]` dài 0 | Vẫn có kiểu mảng runtime chính xác |

Ví dụ rút gọn:

```java
List<String> items = List.of("a", "b");
Object[] objects = items.toArray();
String[] oldStyle = items.toArray(new String[0]);
String[] java11Style = items.toArray(String[]::new);
```

Hai overload nhận mảng/nhận generator đều hiện hành. **Không khẳng định `String[]::new` luôn nhanh hơn `new String[0]`**: thời gian và số lượng cấp phát tùy JDK, kiểu collection, tối ưu JVM và bối cảnh sử dụng; nếu hiệu năng là mục tiêu, đo trên workload cụ thể.

### Khi nào chọn cách nào?

- Khi cần **mảng có kiểu phần tử rõ ràng** trong Java 11+, cách `toArray(String[]::new)` ngắn và dễ đọc.
- Khi đã có mảng đích để có thể dùng lại (`T[] a`), overload `toArray(T[])` là lựa chọn có ý nghĩa: nó có thể điền vào mảng truyền vào nếu đủ chỗ; nếu mảng quá nhỏ, phương thức tạo mảng khác có cùng kiểu phần tử.
- Khi API yêu cầu `Object[]` và không quan tâm kiểu runtime cụ thể hơn, `toArray()` có thể đủ.
- Khi cần chuyển các phần tử thành kiểu khác trước khi tạo mảng (ví dụ từ `Person` sang `String` tên), hãy **map giá trị** bằng Stream hoặc vòng lặp trước. `toArray(generator)` **không biến đổi kiểu từng phần tử**.

## 5. Các Collection và quy tắc thứ tự

`Collection.toArray(IntFunction)` áp dụng được cho các triển khai `Collection` như `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet` và nhiều loại Collection khác. **Kiểu mảng** được xác định bởi generator; **thứ tự phần tử** do Collection cung cấp.

```java
List<String> list = List.of("B", "A", "B");
String[] listArray = list.toArray(String[]::new);
// listArray: ["B", "A", "B"]

Set<String> ordered = new LinkedHashSet<>(list);
String[] setArray = ordered.toArray(String[]::new);
// setArray: ["B", "A"]
```

- `List` giữ thứ tự phần tử của list, có thể có phần tử trùng.
- `LinkedHashSet` giữ thứ tự chèn và loại phần tử trùng.
- `HashSet` không cam kết thứ tự iteration cố định; đừng viết kiểm thử dựa vào một thứ tự vô tình quan sát được.

Ngoài ra, mảng có thể chứa cùng các **đối tượng** mà Collection chứa. Nếu phần tử là mutable object, sửa trạng thái của đối tượng qua tham chiếu trong mảng cũng thấy thay đổi qua tham chiếu trong Collection; chỉ việc gán lại phần tử mảng (ví dụ `array[0] = otherObject`) không tự thay thế phần tử tương ứng của Collection.

## 6. Sử dụng constructor reference với các kiểu mảng khác

### 6.1. Mảng Integer, đối tượng tự định nghĩa

```java
Collection<Integer> counts = List.of(2, 4, 6);
Integer[] countArray = counts.toArray(Integer[]::new);

// Nếu có class Person do dự án định nghĩa:
Collection<Person> people = /* Collection<Person> có dữ liệu */;
Person[] peopleArray = people.toArray(Person[]::new);
```

Dòng `Person` là **mã minh họa không độc lập**: cần class `Person` và biến `people` thực tế trong dự án mới biên dịch.

### 6.2. Mảng kiểu cha hoặc interface

```java
Collection<Integer> numbers = List.of(10, 20);
Number[] boxedNumbers = numbers.toArray(Number[]::new);
Object[] objects = numbers.toArray(Object[]::new);
```

Với các phần tử `Integer`, việc lưu vào mảng `Number[]` hoặc `Object[]` hợp lệ do quan hệ kế thừa. Ngược lại, không được suy rằng mọi `Collection<Number>` đều có thể lưu an toàn vào `Integer[]`.

### 6.3. Mảng primitive không phải `T[]`

Không dùng `int[]::new` để thay thế `Integer[]::new` trong lời gọi `Collection<Integer>.toArray(IntFunction<T[]>)`. `T` là kiểu tham chiếu generic và chữ ký yêu cầu mảng `T[]`, còn `int[]` là mảng primitive.

Nếu mục tiêu thực sự là `int[]` (không boxing), dùng primitive stream:

```java
List<Integer> values = List.of(1, 2, 3);
int[] primitive = values.stream()
        .mapToInt(Integer::intValue)
        .toArray();
```

Đoạn mã này giả định các phần tử không `null`; gọi `intValue()` trên `null` gây `NullPointerException`.

## 7. Các lỗi thường gặp và ngoại lệ

### 7.1. Ép kiểu từ `Object[]` sang `String[]`

```java
Collection<String> names = List.of("A", "B");

// SAI khi chạy: Object[] thực tế không thể ép thành String[].
// String[] wrong = (String[]) names.toArray();

// ĐÚNG:
String[] result = names.toArray(String[]::new);
```

Dù phần tử bên trong là `String`, đối tượng mảng do `toArray()` không đối số trả về có runtime type là `Object[]`. Phép cast trực tiếp sẽ ném `ClassCastException`.

### 7.2. Mảng được tạo không chứa được phần tử thực tế

```java
Collection<Number> values = List.of(1, 2.5);

// Biên dịch được nhưng khi chạy ném ArrayStoreException:
// Integer[] wrong = values.toArray(Integer[]::new);

// ĐÚNG với dữ liệu hiện có:
Number[] correct = values.toArray(Number[]::new);
```

Generic type `<T>` của phương thức không phải giấy phép chuyển đổi từng giá trị. Mảng Java kiểm tra kiểu thành phần thực tế khi lưu phần tử. `toArray` **sao chép phần tử**, không ép `Double` thành `Integer`.

### 7.3. Dùng sai constructor reference

```java
List<String> values = List.of("a", "b");

// SAI: String::new tạo String, không tạo String[].
// String[] invalid = values.toArray(String::new);

// ĐÚNG:
String[] valid = values.toArray(String[]::new);
```

`String[]::new` có cặp ngoặc vuông `[]` để thể hiện rõ constructor của **mảng**.

### 7.4. Generator `null` và overload mơ hồ

Nếu truyền generator `null` một cách có kiểu rõ ràng, API ném `NullPointerException`. Điểm đặc biệt từ Java 11: vì `toArray` có **hai overload nhận tham số kiểu tham chiếu** (`T[]` và `IntFunction<T[]>`), lời gọi trực tiếp sau là **lỗi biên dịch do mơ hồ**:

```java
Collection<String> words = List.of("a");

// SAI: trình biên dịch không biết muốn gọi toArray(T[])
// hay toArray(IntFunction<T[]>).
// words.toArray(null);

// ĐÚNG: chọn overload cụ thể bằng giá trị hợp lệ.
String[] result = words.toArray(String[]::new);
```

Đừng dùng `toArray(null)` để thử null handling. Nếu muốn tạo mảng, cung cấp generator hợp lệ hoặc mảng đích phù hợp.

### 7.5. Nhầm kích thước đầu vào của generator

**Sai giả định:** "Collection có 100 phần tử thì `String[]::new` nhất định được gọi với `100`." Triển khai mặc định theo đặc tả `Collection` gọi generator với `0`. Độ dài cuối cùng vẫn được tạo đúng theo số phần tử. Đừng dựa vào số lần/kích thước gọi generator để thiết kế side effect.

### 7.6. Nhầm với `Stream.toArray(IntFunction)`

```java
List<String> names = List.of("An", "Binh");
String[] fromCollection = names.toArray(String[]::new);
String[] fromStream = names.stream().toArray(String[]::new);
```

Hai kết quả đều có thể bằng `["An", "Binh"]` nhưng đường xử lý khác nhau. Nếu chỉ cần chuyển Collection thành mảng, gọi trực tiếp `names.toArray(String[]::new)`; không cần tạo Stream chỉ để làm cùng việc. Chỉ dùng Stream khi thực sự cần các thao tác `map`, `filter` hoặc xử lý pipeline khác.

## 8. Tình huống áp dụng trong dự án

### 8.1. Gọi API yêu cầu mảng

Một API có chữ ký `void sendBatch(String[] keys)` có thể nhận dữ liệu từ list:

```java
List<String> keys = List.of("java", "spring", "sql");
String[] batch = keys.toArray(String[]::new);
// sendBatch(batch); // Minh họa: phải có phương thức sendBatch trong ứng dụng.
```

Mảng `batch` có runtime type `String[]`; không cần cast và không phải chỉ là `Object[]`.

### 8.2. Dữ liệu không được phép sửa cấu trúc Collection

Chuyển từ `List.of(...)` (list không cho phép thêm/xóa/thay phần tử) sang mảng tạo một cấu trúc chứa mới có thể chỉnh sửa các ô mảng:

```java
List<String> original = List.of("A", "B");
String[] copy = original.toArray(String[]::new);
copy[0] = "C";
// original vẫn là ["A", "B"]; copy là ["C", "B"].
```

Đây là **sao chép nông** (shallow copy): các phần tử là tham chiếu của cùng đối tượng nếu chúng là đối tượng mutable; đừng xem việc đổi sang mảng như cơ chế clone sâu hay tăng tính bất biến.

### 8.3. Thao tác với tập hợp có sắp xếp

```java
Set<String> sorted = new java.util.TreeSet<>(List.of("B", "A", "C"));
String[] orderedArray = sorted.toArray(String[]::new);
// ["A", "B", "C"] theo thứ tự tự nhiên của String.
```

Đây là tính chất của `TreeSet`, không phải do `toArray` tự sort dữ liệu.

## 9. Kiểm tra nhanh

1. **`String[]::new` thực hiện gì?** Nhận một `int` và tạo mảng `String[]` có độ dài đó.
2. **Vì sao `Collection<String>.toArray()` không trả về `String[]`?** Overload không đối số trả về `Object[]`; generic type của phần tử không thay đổi runtime type của mảng.
3. **`toArray(String[]::new)` và `toArray(new String[0])` có còn được dùng hiện nay không?** Có. Chúng là hai overload khác nhau đều hợp lệ.
4. **Collection rỗng cho kết quả gì?** Mảng đúng runtime component type và độ dài 0.
5. **Dùng `Collection<Number>` với `Integer[]::new` có chắc an toàn không?** Không. Phần tử không phải `Integer` có thể gây `ArrayStoreException`.
6. **Vì sao `Collection.toArray(IntFunction)` không được coi là cách tự chuyển `Integer` sang `int[]`?** Chữ ký yêu cầu generic reference array `T[]`; với primitive array hãy dùng primitive stream hoặc chuyển đổi rõ ràng.
7. **Nếu cần thứ tự ổn định, nên kiểm tra gì?** Hợp đồng thứ tự iteration của Collection nguồn; ví dụ `List` hoặc `LinkedHashSet` phù hợp hơn `HashSet` khi cần thứ tự xác định.

## 10. Ghi nhớ

- `Collection.toArray(IntFunction<T[]>)` được bổ sung từ **Java 11** và vẫn là API có ích trong Java hiện đại.
- `collection.toArray(String[]::new)` chuyển phần tử sang **mảng `String[]` có kiểu runtime đúng** nhờ **array constructor reference**.
- `String[]::new` tương đương generator dạng `length -> new String[length]`. Với **triển khai mặc định** của Collection, generator nhận `0` rồi kết quả được đưa cho `toArray(T[])`.
- Đừng nhầm với `toArray()` không đối số (`Object[]`), `toArray(new String[0])` hoặc `Stream.toArray(IntFunction)`.
- Giữ nguyên hiểu biết về **kiểu runtime của mảng**, **thứ tự iteration**, **sao chép nông** và các lỗi `ArrayStoreException` / `ClassCastException` khi áp dụng vào dự án.

**Tài liệu chính thức:** [Oracle Java 11 — Collection.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)), [Oracle Java 26 — Collection API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html), [Oracle Java 11 — IntFunction](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/function/IntFunction.html), [JDK 11 Release Notes — New Collection.toArray(IntFunction)](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html).