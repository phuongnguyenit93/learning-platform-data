# Đọc giá trị từ wildcard không giới hạn (`?`) trong Java Generics

Trong Java Generics, khai báo `List<?>` có nghĩa là **một danh sách có kiểu phần tử cụ thể nhưng chưa được biết tại vị trí sử dụng**. Danh sách ấy có thể thực sự là `List<String>`, `List<Integer>`, `List<Customer>` hoặc một kiểu tham số hóa khác. Java cho phép đọc phần tử từ `List<?>`, nhưng kiểu tĩnh an toàn chung nhất mà chương trình nhận được khi đọc là **`Object`**.

Quy tắc nền tảng:

> Từ `List<?>`, có thể đọc phần tử dưới dạng `Object`; không được tự giả định phần tử là `String`, `Integer` hay bất kỳ kiểu cụ thể nào. Muốn dùng API riêng của kiểu phần tử, cần kiểm tra kiểu lúc chạy hoặc dùng chữ ký generic mang thông tin kiểu tốt hơn.

Bài này tập trung vào thao tác **đọc** từ wildcard không giới hạn, cách hiểu kiểu kết quả, vòng lặp, thao tác lấy dữ liệu an toàn, những giới hạn thường gặp và cách thiết kế phương thức nhận `?`.

## 1. Ý nghĩa chính xác của `List<?>`

Xét hai danh sách:

```java
List<String> names = List.of("An", "Binh");
List<Integer> ages = List.of(20, 21);
```

Cả hai đều có thể được tham chiếu qua `List<?>`:

```java
List<?> first = names; // Hợp lệ.
List<?> second = ages; // Hợp lệ.
```

Dấu `?` là **wildcard không giới hạn** (*unbounded wildcard*). Nó biểu diễn một đối số kiểu chưa xác định. `List<?>` không phải một danh sách “không có kiểu” và cũng không phải một danh sách có kiểu phần tử là `Object`; mỗi đối tượng danh sách vẫn tuân theo kiểu phần tử trong khai báo của nó.

So sánh:

| Khai báo | Có nhận trực tiếp `List<String>`? | Kiểu đọc từ `get` | Ý nghĩa |
| --- | --- | --- | --- |
| `List<String>` | Có | `String` | Biết rõ phần tử là `String` |
| `List<Object>` | Không | `Object` | Danh sách được khai báo chứa `Object`, có thể thêm các kiểu tham chiếu vào |
| `List<?>` | Có | `Object` | Có một kiểu phần tử chưa biết; an toàn nhất là đọc dưới `Object` |
| Raw `List` | Có thể dùng nhưng mất kiểm tra generic | `Object` | Bỏ qua thông tin kiểm tra kiểu; dễ sinh cảnh báo `unchecked` |

Điểm dễ nhầm: mặc dù `List<Object>` và `List<?>` đều cho phép lấy giá trị vào biến `Object`, chúng **khác nhau khi nhận tham số và ghi phần tử**. `List<String>` không thể gán cho `List<Object>` vì generic Java bất biến theo đối số kiểu; nhưng có thể gán cho `List<?>`.

## 2. Đọc bằng `get(index)`: kết quả an toàn là `Object`

Với một biến `List<?> items`, biểu thức `items.get(index)` có kiểu được compiler xem là một kiểu **capture** chưa biết, thường được mô tả trong thông báo lỗi bằng ký hiệu như `CAP#1`. Vì kiểu này chưa biết nhưng là kiểu tham chiếu và có cận trên mặc định `Object`, kết quả có thể được gán vào biến `Object`:

```java
List<?> items = List.of("Java", "Generics");

Object value = items.get(0); // Hợp lệ.
System.out.println(value);   // Java

// String text = items.get(0); // Không biên dịch:
// compiler không thể chứng minh kiểu phần tử là String.
```

Về mặt suy luận kiểu, có thể hình dung:

```text
List<?> items
    |
    | get(0)
    v
phần tử kiểu CAP#1 (kiểu thực tế chưa biết)
    |
    | chuyển kiểu tham chiếu lên Object an toàn
    v
Object value
```

Điều này đúng ngay cả khi người viết biết đối tượng thực tế được tạo từ `List.of("Java", "Generics")`. Một biến đã khai báo là `List<?>` không còn cung cấp bảo đảm kiểu `String` ở điểm gọi `get`. Compiler dựa vào **kiểu tĩnh của biểu thức**, không tự suy ngược đối số kiểu từ một giá trị từng gán vào biến.

Một số giới hạn khác vẫn tồn tại dù phép đọc hợp lệ:

- `get(0)` trên danh sách rỗng ném `IndexOutOfBoundsException`.
- Nếu một triển khai danh sách cho phép phần tử `null`, `get` có thể trả về `null`; kiểm tra trước khi gọi phương thức trên giá trị.
- Đọc qua `List<?>` không thay đổi, chuyển đổi hay sao chép đối tượng phần tử; kết quả `Object` vẫn tham chiếu tới cùng đối tượng.
- Không thể giả định kiểu tham chiếu tĩnh `Object` chứa mọi phương thức riêng của kiểu phần tử.

## 3. Ví dụ Java 17 hoàn chỉnh: đọc nhiều kiểu danh sách

Lưu chương trình sau thành `UnboundedReadDemo.java`:

```java
import java.util.List;

public class UnboundedReadDemo {
    static void printElements(List<?> items) {
        System.out.println("size=" + items.size());

        for (int i = 0; i < items.size(); i++) {
            Object element = items.get(i);
            String type = element == null
                    ? "null"
                    : element.getClass().getSimpleName();

            System.out.println(i + ": " + element + " (" + type + ")");
        }
    }

    public static void main(String[] args) {
        List<String> words = List.of("Java", "API");
        List<Integer> numbers = List.of(10, 20);

        printElements(words);
        printElements(numbers);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac UnboundedReadDemo.java
java UnboundedReadDemo
```

Kết quả:

```text
size=2
0: Java (String)
1: API (String)
size=2
0: 10 (Integer)
1: 20 (Integer)
```

Phương thức `printElements(List<?> items)` không cần biết danh sách chứa kiểu gì để đếm phần tử, truy cập theo chỉ số và in ra biểu diễn của từng đối tượng. Phương thức `getClass()` trong ví dụ chỉ dùng để **quan sát kiểu runtime** của một phần tử không phải `null`. Thông tin đó không làm thay đổi kiểu tĩnh của `items` từ `List<?>` thành `List<String>` hay `List<Integer>`.

Đây là tình huống điển hình nên dùng wildcard không giới hạn: thuật toán làm việc đồng đều với mọi đối tượng và không cần gọi một phương thức chuyên biệt của kiểu phần tử.

## 4. Đọc bằng enhanced `for`, iterator, stream và mảng

Không nhất thiết phải dùng chỉ số. `List<?>` triển khai `Iterable<?>` nên có thể duyệt như sau:

```java
static void printEach(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Với iterator, kiểu kết quả cũng chưa biết:

```java
Iterator<?> it = items.iterator();
while (it.hasNext()) {
    Object item = it.next();
    System.out.println(item);
}
```

Hai đoạn trên minh họa **thân phương thức**, không phải chương trình độc lập. Đoạn dùng `Iterator<?>` cần `import java.util.Iterator;` và `items` phải là `List<?>` đã khai báo.

Tương tự:

```java
Stream<?> stream = items.stream();
Object[] array = items.toArray();
```

Đoạn này cần `import java.util.stream.Stream;`. `Stream<?>` có thể được duyệt dưới kiểu `Object`; `toArray()` không tham số trả về `Object[]`. Nếu muốn có phần tử kiểu `String` hoặc `Number`, phải có cơ sở về kiểu rồi mới chuyển đổi hoặc áp dụng chữ ký có cận kiểu.

**Điểm kỹ thuật:** `Iterable<?>`, `Iterator<?>`, `Stream<?>` và `List<?>` là những kiểu generic riêng biệt; compiler kiểm tra mỗi biểu thức qua chữ ký phương thức tương ứng. Chúng cùng thể hiện nguyên tắc: đọc giá trị thuộc một đối số kiểu không xác định vẫn an toàn khi xem giá trị là `Object`.

## 5. Muốn sử dụng phương thức riêng của kiểu phần tử thì làm gì?

Vì `Object` không có phương thức như `String.toUpperCase()` hay `Number.doubleValue()`, đoạn sau không biên dịch:

```java
List<?> items = List.of("java");

// items.get(0).toUpperCase(); // Không biên dịch.
// String text = items.get(0);  // Không biên dịch.
```

Có hai hướng giải quyết, tùy ý nghĩa nghiệp vụ.

### 5.1. Kiểm tra kiểu runtime bằng `instanceof`

Nếu dữ liệu thật sự có thể khác kiểu và cần xử lý theo từng kiểu, dùng kiểm tra kiểu trước khi gọi phương thức. Java 17 hỗ trợ pattern matching cho `instanceof`:

Lưu thành `SafeWildcardRead.java`:

```java
import java.util.List;

public class SafeWildcardRead {
    static void describeFirst(List<?> items) {
        if (items.isEmpty()) {
            System.out.println("empty");
            return;
        }

        Object first = items.get(0);

        if (first instanceof String text) {
            System.out.println("text: " + text.toUpperCase());
        } else if (first instanceof Number number) {
            System.out.println("number: " + number.doubleValue());
        } else if (first == null) {
            System.out.println("null");
        } else {
            System.out.println("other: " + first.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        describeFirst(List.of("java"));
        describeFirst(List.of(7));
        describeFirst(List.of());
    }
}
```

```bash
javac SafeWildcardRead.java
java SafeWildcardRead
```

Kết quả:

```text
text: JAVA
number: 7.0
empty
```

Nhánh `instanceof String text` đảm bảo bên trong nhánh ấy, **biến `text`** có kiểu `String`. Điều đó không làm cho toàn bộ danh sách `items` được suy ra là `List<String>`: có thể có những phần tử kiểu khác ở chỉ số khác, nhất là khi nguồn được truyền vào qua các kiểu khác nhau.

Nếu bắt buộc phải ép kiểu tường minh, chẳng hạn `String text = (String) items.get(0);`, hãy nhớ ép kiểu chỉ được xác minh tại runtime và có thể ném `ClassCastException`. Không dùng ép kiểu chỉ để che đi việc thiếu thông tin kiểu.

### 5.2. Dùng wildcard có cận nếu nghiệp vụ cần một nhóm kiểu cụ thể

Nếu phương thức cần đọc số để tính toán, chữ ký thích hợp hơn là `List<? extends Number>`:

```java
static double sum(List<? extends Number> numbers) {
    double total = 0;
    for (Number number : numbers) {
        total += number.doubleValue();
    }
    return total;
}
```

Bây giờ compiler bảo đảm mọi phần tử đọc ra có thể xem là `Number`. Phương thức nhận được `List<Integer>`, `List<Double>` và `List<Number>` mà không cần kiểm tra `instanceof Number` cho từng phần tử. Ngược lại, `List<?>` dành cho trường hợp thuật toán **không cần** biết đặc tính cụ thể nào ngoài những gì `Object` cung cấp.

Có thể ghi nhớ sự khác nhau:

| Kiểu tham số | Compiler biết gì khi đọc? | Có thể gọi trực tiếp |
| --- | --- | --- |
| `List<?>` | Phần tử là một kiểu tham chiếu chưa biết | Phương thức `Object` |
| `List<? extends Number>` | Phần tử là `Number` hoặc kiểu con | `doubleValue()`, `intValue()`, v.v. |
| `List<? super Integer>` | Phần tử thuộc một kiểu cha chưa biết của `Integer` | Khi đọc chỉ chắc chắn có `Object` |
| `List<String>` | Phần tử là `String` | `length()`, `toUpperCase()`, v.v. |

`? super Integer` cho phép **ghi** `Integer` nhưng không giúp đọc ra giá trị có kiểu `Integer`. Cận dưới chỉ bảo đảm đích nhận được `Integer`; danh sách thực tế cũng có thể là `List<Object>`.

## 6. Ví dụ với `Map<?, ?>`: đọc khóa và giá trị đều là `Object`

Với `Map<K, V>`, hai đối số kiểu độc lập nhau. `Map<?, ?>` cho biết cả kiểu khóa lẫn kiểu giá trị đều chưa biết. Ta có thể đọc từ bản đồ nhưng không tự kết luận khóa là `Integer` hoặc giá trị là `String`.

Lưu thành `UnknownMapRead.java`:

```java
import java.util.Map;

public class UnknownMapRead {
    static void printEntries(Map<?, ?> map) {
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            Object key = entry.getKey();
            Object value = entry.getValue();
            System.out.println(key + " -> " + value);
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> labels = Map.of(7, "seven");
        printEntries(labels);

        Map<?, ?> unknown = labels;
        Object value = unknown.get(7);
        System.out.println("lookup: " + value);
    }
}
```

```bash
javac UnknownMapRead.java
java UnknownMapRead
```

Kết quả:

```text
7 -> seven
lookup: seven
```

Trong `Map<?, ?>`, `get(Object key)` **nhận tham số kiểu `Object`** theo hợp đồng của `Map`, nên được phép gọi với đối tượng khóa dù kiểu khóa generic chưa biết. Tuy nhiên, kết quả đọc ra vẫn chỉ bảo đảm gán được cho `Object`. `Map.Entry<?, ?>.getKey()` và `getValue()` cũng tuân theo quy tắc tương tự.

Nếu muốn giữ kiểu tĩnh của khóa và giá trị để thao tác chuyên biệt, nên dùng `Map<K,V>` hoặc cận wildcard đúng nhu cầu, thay vì ép kiểu tùy ý.

## 7. `?` khác `Object` ở đâu khi đọc?

Xét:

```java
List<String> names = List.of("Lan", "Mai");
List<?> unknown = names;
Object first = unknown.get(0); // Hợp lệ.

// List<Object> objects = names; // Không biên dịch.
```

Kết quả từ `unknown.get(0)` có thể lưu trong `Object`, nhưng **không có phép chuyển đổi ngầm từ `List<?>` sang `List<Object>`**.

Lý do là một biến `List<Object>` cho phép thêm một `Object` bất kỳ (nếu danh sách có hỗ trợ sửa đổi); nếu nó trỏ tới `List<String>`, việc thêm `Integer` sẽ phá hợp đồng phần tử. Ngược lại, `List<?>` duy trì giới hạn thao tác khiến ta không thể thêm một phần tử bất kỳ chỉ dựa trên việc đọc được kiểu `Object`.

Thử so sánh các lời gọi sau trong một ngữ cảnh có danh sách thay đổi được:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;
Object value = "hello";

unknown.size();       // Hợp lệ.
unknown.contains(value); // Hợp lệ: contains nhận Object.
unknown.getClass();   // Hợp lệ: phương thức của Object.

// unknown.add(value); // Không biên dịch.
// unknown.add("hi");  // Không biên dịch.
```

Đoạn minh họa trên cần `import java.util.ArrayList;` và `import java.util.List;`.

**Đọc được một phần tử không đồng nghĩa có quyền ghi chính phần tử ấy trở lại bằng kiểu `Object`**. Việc đọc và việc ghi cần những bảo đảm kiểu khác nhau.

## 8. Có thể đọc phần tử rồi đặt lại vào cùng danh sách không?

Đây là trường hợp dễ gây nhầm lẫn với *wildcard capture*:

```java
static void replaceFirstWithSecond(List<?> items) {
    // items.set(0, items.get(1)); // Không biên dịch.
}
```

Mặc dù `items.get(1)` đọc từ chính danh sách đó, kiểu tĩnh mà compiler xử lý tại lời gọi `set` vẫn cần một đối số tương thích với kiểu phần tử chưa biết được capture. Không thể đơn giản coi kết quả của lời gọi `get` là một `Object` rồi đưa vào `set`.

Khi cần sử dụng **cùng một kiểu phần tử `T`** xuyên suốt thao tác, dùng một phương thức generic để compiler đặt tên cho kiểu được capture:

Lưu thành `WildcardCaptureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> items) {
        if (items.size() < 2) {
            return;
        }
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("before", "after"));
        swapFirstTwo(words);
        System.out.println(words);

        List<Integer> numbers = new ArrayList<>(List.of(1, 2));
        swapFirstTwo(numbers);
        System.out.println(numbers);
    }
}
```

```bash
javac WildcardCaptureDemo.java
java WildcardCaptureDemo
```

Kết quả:

```text
[after, before]
[2, 1]
```

Phương thức ngoài nhận mọi `List<?>`. Phương thức `swapCaptured` ràng buộc mọi lần đọc và ghi trong thân của nó vào cùng tham số kiểu `T`, nên truyền phần tử từ vị trí này sang vị trí khác an toàn về kiểu. Trong thư viện chuẩn, `Collections.swap(List<?>, int, int)` cũng cung cấp chức năng hoán đổi tương ứng; ví dụ trên giúp hiểu vì sao phương thức generic hỗ trợ những trường hợp kiểu capture mà code trực tiếp bị từ chối.

Lưu ý `set` có thể ném `UnsupportedOperationException` nếu danh sách không hỗ trợ sửa đổi; trong ví dụ dùng `ArrayList` để bảo đảm danh sách có thể cập nhật.

## 9. Kiểm tra và duyệt nội dung mà không biết đối số kiểu

Một số thao tác không yêu cầu kiểu phần tử cụ thể, nên có thể triển khai chung qua `List<?>`:

```java
static boolean hasAnyItem(List<?> items) {
    return !items.isEmpty();
}

static Object firstOrNull(List<?> items) {
    return items.isEmpty() ? null : items.get(0);
}

static void logObjects(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Đây là các phương thức minh họa; để biên dịch cùng nhau, đặt chúng trong một class có `import java.util.List;`. Ở đây:

- `isEmpty()` và `size()` không phụ thuộc đối số kiểu.
- `get(0)` và vòng lặp đọc ra được `Object`.
- `contains(Object)`, `indexOf(Object)` và `lastIndexOf(Object)` nhận đối số là `Object` nên có thể gọi mà không phải biết kiểu generic.

`List<?>` thường thích hợp cho API kiểm tra, hiển thị, thống kê số lượng phần tử, logging hoặc xem xét cấu trúc dữ liệu khi không yêu cầu phương thức riêng trên từng phần tử.

Với kiểu hoàn toàn không biết, xử lý theo `Object` là an toàn về **hệ kiểu**, nhưng không tự bảo đảm mọi thao tác nghiệp vụ đều thành công: phương thức của phần tử có thể ném exception; `toString()` có thể chứa thông tin nhạy cảm, hoặc danh sách có thể bị thay đổi trong khi duyệt. Chỉ sử dụng những dữ liệu thật sự cần xử lý.

## 10. Đọc qua wildcard không đảm bảo danh sách bất biến

Một phương thức **chỉ đọc** nên chọn `List<?>` khi không cần type argument cụ thể, nhưng chữ ký ấy không ngăn người khác sửa backing list; bản thân `clear()` hoặc `remove(Object)` cũng có thể gọi qua wildcard.

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<?> view = source;
Object first = view.get(0);
view.clear();
System.out.println(first + " / " + source); // A / []
```

Ví dụ dùng `ArrayList` có thể sửa. Với `List.of(...)`, thao tác `clear()` sẽ không được hỗ trợ. Nếu cần một snapshot không cho chỉnh sửa cấu trúc, cân nhắc `List.copyOf(source)` (không chấp nhận phần tử null); không nhầm bảo đảm bất biến với kiểu wildcard hay khả năng an toàn đa luồng.

## 11. Wildcard không giới hạn và generic method: chọn theo nhu cầu đọc

Một phương thức chỉ cần đọc dưới kiểu `Object` có thể nhận `List<?>` trực tiếp:

```java
static void display(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Không cần tạo một tham số kiểu `<T>` chỉ để viết lại:

```java
static <T> void displayGeneric(List<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
```

Cả hai ví dụ đều xử lý được `List<String>` và `List<Integer>`. Khi `T` chỉ xuất hiện một lần trong chữ ký và không có quan hệ giữa các tham số, `List<?>` thường thể hiện ý định đơn giản hơn.

Tuy nhiên, `<T>` hữu ích khi kiểu cần được **duy trì và kết nối** qua giá trị trả về hoặc nhiều tham số:

```java
static <T> T first(List<T> items) {
    return items.get(0);
}
```

Với:

```java
List<String> words = List.of("hello");
String word = first(words); // Compiler suy ra T là String.
```

Nếu thay bằng phương thức trả `Object`:

```java
static Object firstUnknown(List<?> items) {
    return items.get(0);
}
```

thì:

```java
Object value = firstUnknown(words); // Hợp lệ.
// String word = firstUnknown(words); // Không biên dịch.
```

Không có gì “sai” trong phương thức `firstUnknown`: nó chỉ cung cấp một hợp đồng yếu hơn. Chọn `List<?>` khi chỉ cần đối tượng tổng quát; chọn `<T>` khi caller cần giữ chính xác kiểu phần tử đọc ra.

## 12. Vấn đề `null`, danh sách rỗng và tính an toàn khi đọc

Đọc dữ liệu từ `List<?>` vẫn cần kiểm tra các điều kiện runtime thông thường.

**Danh sách rỗng:** `items.get(0)` ném `IndexOutOfBoundsException` nếu `items.isEmpty()` là `true`. Wildcard không bảo đảm số phần tử.

**Phần tử `null`:** một danh sách mutable có thể chứa `null`. Khi đọc vào `Object`, vẫn phải kiểm tra `null` trước khi gọi `getClass()`, `toString()` hoặc các phương thức khác. `List.of(...)` từ Java 9 không nhận `null`, nhưng điều này chỉ đúng với cách tạo danh sách đó.

**Danh sách không thể sửa:** `List.of(...)` tạo danh sách không sửa đổi; điều này độc lập với kiểu wildcard. Việc đọc có thể thành công, trong khi `clear` hoặc `set` sẽ ném `UnsupportedOperationException`.

**Đa luồng:** kiểu `List<?>` không tự đảm bảo an toàn luồng. Nếu danh sách bị sửa đồng thời, kết quả đọc hoặc duyệt phụ thuộc hợp đồng của triển khai và cách đồng bộ. Đừng suy diễn rằng “chỉ đọc qua wildcard” là một cơ chế đồng bộ.

**Sai kiểu ở runtime:** việc đọc thành `Object` không gây ép kiểu xuống lớp cụ thể. `ClassCastException` thường phát sinh khi mã sau đó ép kiểu không hợp lệ, hoặc khi chương trình trước đó phá bảo đảm generic bằng raw type/unchecked conversion.

## 13. Câu hỏi kiểm tra nhanh

**Câu 1.** Với `List<?> items`, câu nào chắc chắn hợp lệ về kiểu?

```java
Object a = items.get(0);
// String b = items.get(0);
// Integer c = items.get(0);
```

**Đáp án:** chỉ dòng đầu. Hai dòng sau yêu cầu compiler biết kiểu phần tử cụ thể, nhưng `?` không cung cấp thông tin ấy. Dòng đầu vẫn có thể thất bại lúc chạy nếu danh sách rỗng.

**Câu 2.** Vì sao có thể viết `for (Object value : items)`?

**Đáp án:** mọi phần tử của một `List<?>` là đối tượng thuộc một kiểu tham chiếu chưa biết, nên việc xem từng phần tử như `Object` là an toàn.

**Câu 3.** `List<?>` và `List<Object>` có đồng nhất không?

**Đáp án:** không. Cả hai đọc ra được `Object`, nhưng `List<?>` nhận trực tiếp danh sách tham số hóa với kiểu bất kỳ, còn `List<Object>` chỉ nhận danh sách có đối số kiểu phù hợp với `Object` theo các quy tắc kế thừa generic.

**Câu 4.** Nếu cần gọi `Number.doubleValue()` trên mọi phần tử thì nên nhận `List<?>` hay `List<? extends Number>`?

**Đáp án:** `List<? extends Number>`. Compiler khi đó biết mỗi phần tử đọc ra có thể xem là `Number`, nên gọi `doubleValue()` an toàn mà không phải ép kiểu.

**Câu 5.** Nếu cần trả về đúng kiểu phần tử đầu tiên cho caller, chữ ký nào phù hợp hơn?

```java
static <T> T first(List<T> source)
```

**Đáp án:** phương thức generic này giữ quan hệ giữa kiểu phần tử của `source` và kiểu trả về `T`, trong khi `Object first(List<?> source)` chỉ cung cấp kiểu tổng quát.

## 14. Tổng kết để áp dụng

- `?` biểu diễn một đối số kiểu chưa biết; **đọc từ `List<?>` bảo đảm gán được vào `Object`**.
- `get`, vòng lặp `for` và `Iterator<?>` đều cho phép lấy giá trị dưới kiểu `Object`; cần kiểm tra rỗng và `null` như bình thường.
- Không được tự động nhận kết quả đọc là `String`, `Integer` hay lớp cụ thể khác. Sử dụng `instanceof` nếu dữ liệu thực sự hỗn hợp và cần phân nhánh tại runtime.
- Khi thuật toán cần một họ kiểu cụ thể, ví dụ `Number`, dùng `? extends Number` để tăng thông tin kiểu cho kết quả đọc.
- Khi cần giữ nguyên kiểu phần tử từ đầu vào đến đầu ra, dùng tham số kiểu `<T>`; khi cần xử lý bất kỳ phần tử nào như `Object`, `List<?>` thường đủ.
- Wildcard không giới hạn **không biến collection thành immutable**, không bảo đảm thread-safety và không cho phép thêm tùy ý phần tử chỉ vì đọc được một `Object`.

Đặt câu hỏi “**Sau khi đọc ra, thuật toán cần biết điều gì về phần tử?**” sẽ giúp chọn giữa `List<?>`, wildcard có cận và generic method một cách chính xác.