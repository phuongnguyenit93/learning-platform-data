# Vì sao không thể match trực tiếp mọi parameterized type trong Java?

## 1. Vấn đề xuất phát từ đâu?

Xét danh sách generic:

```java
import java.util.List;

Object value = List.of("Java", "Pattern");
```

Khi đọc `value`, ta có thể muốn kiểm tra “đây có phải danh sách các chuỗi hay không?” bằng:

```java
// Không biên dịch được khi value có kiểu tĩnh Object:
// if (value instanceof List<String> names) {
//     System.out.println(names.get(0).toUpperCase());
// }
```

Java không thể thực hiện phép kiểm tra đó một cách an toàn chỉ dựa trên đối tượng ở runtime. Nguyên nhân chính là **type erasure** và yêu cầu một phép `instanceof` phải kiểm tra được kiểu mục tiêu theo quy tắc ngôn ngữ.

Tuy nhiên, kết luận chính xác là: **không thể match tùy ý mọi parameterized type từ một biểu thức kiểu rộng như `Object`**. Không phải mọi cách viết có đối số generic trong `instanceof` đều bị cấm tuyệt đối. Java cũng dựa vào **kiểu tĩnh của biểu thức trước `instanceof`** để chấp nhận một số phép kiểm tra an toàn. Phần dưới trình bày cả hai trường hợp.

Bài viết dùng type pattern của `instanceof`, ổn định từ Java 16 và hoạt động trên Java 17+.

## 2. Parameterized type là gì?

Trong Java, `List<E>`, `Map<K, V>`, `Box<T>` là các khai báo generic. Khi gắn đối số kiểu vào tham số, ta có các **parameterized type**:

- `List<String>`: danh sách được khai báo chứa `String`.
- `List<Integer>`: danh sách được khai báo chứa `Integer`.
- `Map<String, Integer>`: ánh xạ từ `String` sang `Integer`.
- `List<?>`: danh sách với đối số kiểu chưa biết.
- `List<? extends Number>`: danh sách với đối số kiểu chưa biết nhưng bị chặn bởi `Number`.

Đối số kiểu giúp compiler kiểm tra các lệnh như `list.add(...)`, kết quả trả về của `get(...)` và ràng buộc generic lúc **biên dịch**. Nó không đồng nghĩa JVM tạo ra các lớp riêng biệt `ArrayList<String>` và `ArrayList<Integer>`.

Ví dụ:

```java
List<String> words = List.of("a", "b");
List<Integer> numbers = List.of(1, 2);

System.out.println(words.getClass() == numbers.getClass()); // true
```

Trong ví dụ với `List.of(...)`, các đối tượng thuộc cùng lớp triển khai runtime của JDK. Điều này minh họa lý do **chỉ nhìn lớp của đối tượng không đủ suy ra `String` hay `Integer`**. Mặt khác, không nên dựa vào lớp triển khai cụ thể mà `List.of` chọn, vì đó là chi tiết triển khai.

## 3. Type erasure làm mất thông tin gì?

Java generic chủ yếu được hiện thực bằng **type erasure**: sau khi compiler kiểm tra ràng buộc kiểu, bytecode sử dụng các kiểu đã xóa tham số generic ở nhiều vị trí. Cả `List<String>` lẫn `List<Integer>` thường được xử lý ở mức runtime như giao diện `List`.

Có hai thông tin khác nhau cần phân biệt:

| Thông tin | Compiler có thể biết | JVM thường kiểm tra trực tiếp bằng `instanceof` |
| --- | --- | --- |
| Đối tượng là một `List`? | Có | Có |
| Đối tượng là một `ArrayList`? | Có | Có |
| Tất cả phần tử thuộc `String`? | Có thể biết từ khai báo hoặc phân tích mã | Không thể suy ra chỉ từ lớp runtime của `List` |
| Đối số generic cụ thể là `String` hay `Integer`? | Có thể dựa trên kiểu tĩnh | Thường không được giữ ở mỗi đối tượng để kiểm tra bằng `instanceof` |
| Một phần tử đang là `String`? | Có thể | Có, nếu kiểm tra chính phần tử |

Một số chữ ký generic có thể được lưu trong **metadata của khai báo** để phục vụ reflection, nhưng metadata đó không phải bằng chứng về đối số generic của *mọi đối tượng cụ thể* đang chạy. Đừng nhầm thông tin reflection trên field/class với khả năng hỏi một instance `List<?>` “bên trong có tham số `String` hay không”.

Ví dụ, kể cả khi một danh sách hiện tại chỉ chứa chuỗi, `List<Integer>` và `List<String>` không được phân biệt bằng một kiểm tra runtime thuần túy trên class của danh sách.

## 4. Reifiable type: kiểu có đủ thông tin để kiểm tra ở runtime

Trong Java, **reifiable type** là kiểu mà thông tin cần thiết cho kiểm tra kiểu vẫn sẵn có tại runtime theo quy tắc của ngôn ngữ (JLS §4.7).

Các trường hợp thường dùng:

- Kiểu không generic như `String`, `Integer`, `Runnable`, `Number`.
- Kiểu raw như `List`, `Map`; tuy nhiên sử dụng raw type thường làm mất an toàn generic.
- Parameterized type có **tất cả** đối số là wildcard không giới hạn `?`, ví dụ `List<?>` và `Map<?, ?>`.
- Mảng có kiểu thành phần reifiable, chẳng hạn `String[]` hoặc `List<?>[]`.

Ngược lại, các kiểu sau nhìn chung **không reifiable**: `List<String>`, `List<Integer>`, `Map<String, Integer>`, `List<? extends Number>` và `List<List<?>>`. Kiểu biến type parameter `T` cũng không phải loại có thể match tùy ý qua `instanceof T`.

**Tại sao `List<?>` là reifiable mà `List<String>` không?**

`List<?>` chỉ yêu cầu xác định đối tượng có thực thi `List` hay không. Nó không hứa phần tử là một kiểu cụ thể, nên JVM có đủ thông tin để kiểm tra phần “là một `List`”.

`List<String>` bổ sung một lời khẳng định về đối số kiểu `String`. Thông tin này thường đã bị xóa ở runtime, nên từ một biểu thức `Object`, JVM không thể kiểm chứng lời khẳng định đó chỉ bằng `instanceof`.

```java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}

// Không hợp lệ từ Object:
// if (value instanceof java.util.List<String> names) { ... }
```

Biến pattern `items` có kiểu **`List<?>`**, không phải `List<String>`. Phần tử đọc bằng `items.get(0)` vì thế chỉ có kiểu tĩnh đủ rộng để gán vào `Object`, trừ khi ta kiểm tra tiếp.

## 5. Lý do compiler từ chối một số pattern có đối số generic

Với biểu thức có kiểu tĩnh `Object`:

```java
Object data = java.util.List.of("A", "B");

// Sai: Object không thể được kiểm tra an toàn thành List<String>
// bằng instanceof với type pattern này.
// if (data instanceof java.util.List<String> strings) { ... }
```

Nếu compiler cho phép, ta có thể nhầm rằng bất kỳ đối tượng `List` nào được match đều chứa `String`. Nhưng một `List<Integer>` ở runtime cũng thực thi cùng giao diện `List`. Việc coi nó là `List<String>` có thể dẫn đến `ClassCastException` khi đọc phần tử dưới giả định sai.

Compiler cũng từ chối một phép kiểm tra kiểu generic bất khả thi như:

```java
// Với data có kiểu Object, các type pattern này không an toàn:
// if (data instanceof java.util.List<Integer> nums) { ... }
// if (data instanceof java.util.Map<String, Integer> dict) { ... }
// if (data instanceof java.util.List<? extends Number> nums) { ... }
```

**Không thể thay bằng type variable**:

```java
// Đoạn minh họa không thể biên dịch với instanceof T:
static <T> boolean invalid(Object data) {
    // return data instanceof T;
    return false;
}
```

Dòng `data instanceof T` không hợp lệ vì `T` là type variable, không cung cấp kiểu runtime được kiểm tra trực tiếp theo cách đó. Có thể truyền `Class<?>` làm type token để kiểm tra **lớp raw/reifiable phù hợp**, nhưng nó không tự xác nhận được kiểu phần tử của `List<String>`.

## 6. Ngoại lệ cần nắm: kiểu tĩnh có thể khiến một parameterized type pattern hợp lệ

Đây là chỗ dễ học sai nếu chỉ nhớ câu “`instanceof` không hỗ trợ generic”.

Java xét **khả năng chuyển kiểu an toàn từ kiểu tĩnh của biểu thức sang kiểu trong pattern**. Nếu compiler đã biết tham số generic từ kiểu tĩnh, một pattern có đối số cụ thể có thể hợp lệ, ngay cả khi type pattern đó không reifiable theo nghĩa độc lập.

Ví dụ hợp lệ trên Java 17:

```java
import java.util.ArrayList;
import java.util.List;

static void narrow(List<String> words) {
    if (words instanceof ArrayList<String> array) {
        System.out.println(array.size());
    }
}
```

Lý do hợp lệ:

1. `words` đã có kiểu tĩnh **`List<String>`**. Compiler biết ràng buộc đối số `String` từ khai báo, không cần truy vấn phần tử ở runtime.
2. Mục tiêu là một lớp triển khai cụ thể **`ArrayList<String>`**. Quan hệ chuyển kiểu từ `List<String>` sang `ArrayList<String>` ở đây có thể kiểm tra an toàn với thông tin tĩnh đã có.
3. Runtime chỉ còn phải kiểm tra đối tượng có thực sự là `ArrayList` không; ràng buộc `String` được bảo đảm bởi hệ thống kiểu tĩnh, với giả định không có raw/unchecked operation phá hỏng dữ liệu trước đó.

So sánh ba trường hợp:

| Kiểu tĩnh của biểu thức | Pattern | Kết quả điển hình trên Java 17 |
| --- | --- | --- |
| `Object data` | `List<String> names` | Lỗi biên dịch: không kiểm tra an toàn được đối số `String` |
| `Object data` | `List<?> names` | Hợp lệ: đối số unbounded wildcard, reifiable |
| `List<String> words` | `ArrayList<String> array` | Hợp lệ: kiểu tĩnh đã cho biết đối số `String` |
| `List<?> unknown` | `ArrayList<String> array` | Lỗi biên dịch: không chứng minh được `String` |
| `List<?> unknown` | `ArrayList<?> array` | Hợp lệ: kiểm tra class triển khai, không hứa đối số cụ thể |

Vì vậy đừng hiểu rằng JVM có thể đọc tham số `String` từ một `ArrayList` tại runtime chỉ vì ví dụ `List<String> -> ArrayList<String>` biên dịch. **Compiler dựa trên ràng buộc generic có sẵn từ kiểu tĩnh**. Nếu đầu vào là `Object` hoặc `List<?>`, bằng chứng đó không còn.

Cần tách biệt chuyện **hợp lệ về kiểu** với chuyện đối tượng có thực sự là `ArrayList`: phương thức nhận `List<String>` có thể được truyền một implementation khác của `List`; khi đó pattern `ArrayList<String>` đơn giản là không khớp.

## 7. Chương trình Java 17 hoàn chỉnh: minh họa ba kiểu kiểm tra

Lưu tệp sau thành **ReifiableDemo.java**. Chương trình không dùng preview:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ReifiableDemo {
    static boolean allStrings(Object value) {
        if (!(value instanceof List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }

    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            System.out.println("List size=" + items.size());
            System.out.println("All strings=" + allStrings(value));
            if (!items.isEmpty()
                    && items.get(0) instanceof String first) {
                System.out.println("First upper="
                        + first.toUpperCase());
            }
        } else {
            System.out.println("Not a List");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("A", "B"));
        inspect(List.of("A", 7));
        inspect(null);

        List<String> typed =
                new ArrayList<>(List.of("x", "y"));
        if (typed instanceof ArrayList<String> arrayList) {
            System.out.println("ArrayList size="
                    + arrayList.size());
        }

        Object map = Map.of("k", 1);
        if (map instanceof Map<?, ?> entries) {
            System.out.println("Map size=" + entries.size());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ReifiableDemo.java
java ReifiableDemo
```

Đầu ra chính xác:

```text
List size=2
All strings=true
First upper=A
List size=2
All strings=false
First upper=A
Not a List
ArrayList size=2
Map size=1
```

Phân tích:

- Cả `List.of("A", "B")` và `List.of("A", 7)` đều khớp `List<?>`. Pattern này kiểm tra **loại container**, không chứng minh kiểu từng phần tử.
- `allStrings` kiểm tra **từng phần tử**, nên danh sách thứ nhất trả `true`, danh sách thứ hai trả `false`.
- Phần tử đầu tiên của cả hai danh sách là `String` nên cùng in `First upper=A`. Kiểm tra một phần tử **không** suy ra toàn bộ danh sách là chuỗi.
- `null instanceof List<?>` trả `false`. Điều kiện `instanceof` không tự gây `NullPointerException` khi giá trị là `null`.
- `List<String> typed` được phép kiểm tra `ArrayList<String>` vì thông tin đối số đã nằm ở kiểu tĩnh; runtime chỉ cần xác định implementation.
- `Map<?, ?>` cũng là parameterized type reifiable vì cả hai đối số là `?` không giới hạn.

Nếu truyền danh sách trống, `allStrings` trả `true` theo quy tắc logic “mọi phần tử đều là String” trên tập rỗng. Nếu nghiệp vụ còn yêu cầu danh sách **không rỗng**, cần thêm kiểm tra `!items.isEmpty()`.

## 8. Muốn lấy `List<String>` an toàn từ `Object` phải làm gì?

Đầu tiên dùng pattern `List<?>` để kiểm tra container, sau đó kiểm tra và đưa các phần tử đã xác minh vào danh sách mới có kiểu tĩnh `List<String>`.

Ví dụ phương thức (cần `import java.util.ArrayList;`, `import java.util.List;` và `import java.util.Optional;`):

```java
static Optional<List<String>> validatedStrings(Object input) {
    if (!(input instanceof List<?> items)) {
        return Optional.empty();
    }

    List<String> result = new ArrayList<>(items.size());
    for (Object element : items) {
        if (!(element instanceof String text)) {
            return Optional.empty();
        }
        result.add(text);
    }
    return Optional.of(List.copyOf(result));
}
```

Với các biểu thức độc lập sau:

```java
System.out.println(
        validatedStrings(List.of("A", "B")).orElseThrow());
System.out.println(
        validatedStrings(List.of("A", 7)).isEmpty());
System.out.println(
        validatedStrings(List.of()).orElseThrow());
```

Kết quả:

```text
[A, B]
true
[]
```

Cách làm này có các đặc điểm:

- Không cần unchecked cast từ `List<?>` sang `List<String>`; từng phần tử được chứng minh là `String` trước khi đưa vào danh sách kết quả.
- `List.copyOf(result)` trả về danh sách không sửa đổi được, giúp người nhận tránh phụ thuộc vào việc danh sách nguồn có thể tiếp tục biến đổi sau khi kiểm tra.
- Một phần tử `null` sẽ **không** khớp `instanceof String`, nên phương thức trả `Optional.empty()`. Nếu nghiệp vụ cho phép null, cần thiết kế cách xử lý riêng, đồng thời nhớ rằng `List.copyOf` không chấp nhận phần tử null.
- Đây là kiểm tra ở mức **nội dung**, có độ phức tạp theo số phần tử. `instanceof List<?>` ban đầu chỉ kiểm tra loại container và không duyệt phần tử.

Với dữ liệu đầu vào từ JSON, API hoặc hệ thống ngoài có cấu trúc phức tạp, thường nên dùng bộ giải mã/schema validation có khai báo kiểu đích và kiểm chứng từng trường, thay vì trông đợi một `instanceof List<String>` là đủ.

## 9. Raw type và unchecked cast không giải quyết vấn đề

Có thể viết:

```java
Object input = java.util.List.of("A", 7);

if (input instanceof java.util.List rawList) {
    System.out.println(rawList.size()); // 2
}
```

Kiểm tra raw type `List` chỉ chứng minh đây là một `List`. Nó **không** chứng minh loại phần tử. Cách dùng raw type rộng rãi còn làm mất kiểm tra generic ở thời điểm biên dịch.

Tương tự, đoạn ép kiểu:

```java
@SuppressWarnings("unchecked")
static java.util.List<String> unsafe(Object input) {
    return (java.util.List<String>) input;
}
```

không tiến hành kiểm chứng từng phần tử. Với danh sách chứa `Integer`, lời hứa `List<String>` là sai dù cast có thể đi qua kiểm tra raw container. Lỗi `ClassCastException` có thể xuất hiện **muộn hơn**, khi chương trình đọc một phần tử và sử dụng nó như `String`.

Dùng `@SuppressWarnings("unchecked")` chỉ ẩn cảnh báo; nó không khiến lời khẳng định generic trở nên đúng. Nếu thực sự phải nhận dữ liệu kiểu rộng, hãy kiểm tra phần tử và copy như mục 8, hoặc bảo toàn thông tin kiểu qua API ngay từ đầu.

## 10. Mảng và generic: một so sánh hữu ích

Mảng Java biết kiểu phần tử ở runtime, còn đối số kiểu generic thường bị erasure:

```java
Object value = new String[] {"A", "B"};

if (value instanceof String[] strings) {
    System.out.println(strings.length); // 2
}
```

`String[]` là reifiable nên phép kiểm tra trên hợp lệ. Với mảng của parameterized type có wildcard không giới hạn, `List<?>[]` cũng là một trường hợp reifiable được ngôn ngữ hỗ trợ.

Trái lại, không thể dùng một phép kiểm tra runtime từ `Object` để xác nhận trực tiếp “mảng `List<String>`” dưới dạng `List<String>[]`. Đối số generic `String` trong mỗi danh sách vẫn không thể kiểm tra theo cách đó.

Khác biệt này còn giải thích vì sao Java cấm tạo mảng generic như `new List<String>[10]`: mảng kiểm tra kiểu phần tử ở runtime, nhưng generic element type cụ thể không còn đầy đủ thông tin. Khi cần tập hợp generic động, ưu tiên dùng `List<List<String>>` được kiểm soát bằng hệ thống kiểu thay vì mảng generic.

## 11. Những lỗi và ngộ nhận phổ biến

| Nhận định sai | Sửa lại cho đúng |
| --- | --- |
| “`List<String>` và `List<Integer>` là hai lớp runtime khác nhau.” | Tham số generic chủ yếu bị erasure; lớp runtime không đủ nói lên kiểu phần tử. |
| “`Object instanceof List<String>` nên hoạt động khi danh sách hiện tại chỉ chứa String.” | Compiler không dựa vào việc quan sát tất cả phần tử để hợp thức hóa type pattern không an toàn đó. |
| “Không bao giờ được có đối số generic trong `instanceof`.” | `List<?>`, `Map<?, ?>` là reifiable; một số narrowing pattern như `List<String>` sang `ArrayList<String>` hợp lệ khi kiểu tĩnh đã đủ thông tin. |
| “Match `List<?>` nghĩa là các phần tử đều cùng một kiểu.” | `?` chỉ có nghĩa đối số kiểu chưa biết; cần kiểm tra phần tử nếu muốn bảo đảm kiểu cụ thể. |
| “`List<? extends Number>` sẽ được kiểm tra giống `List<?>` từ Object.” | Wildcard có bound khác wildcard `?` không giới hạn; không reifiable theo cùng quy tắc. |
| “Match `List<?>` thì gọi `get(0)` an toàn.” | Cần kiểm tra danh sách không rỗng; `get(0)` còn trả về `Object` về mặt kiểu tĩnh. |
| “Kiểm tra phần tử đầu tiên là String đủ chứng minh cả List.” | Chỉ chứng minh phần tử vừa kiểm tra; phải duyệt hết hoặc tin vào hợp đồng typed API. |
| “Ép `(List<String>) input` sẽ xác minh nội dung.” | Đây là unchecked cast; kiểu phần tử không được bảo đảm. |
| “Dùng `Class.isInstance` là kiểm tra được `List<String>`.” | `Class` kiểm tra lớp raw/reifiable, không tự xác nhận tham số `String` của container. |
| “Generics luôn không còn dấu vết gì ở runtime.” | Một số generic declaration signature có metadata; điều đó không làm mọi đối số generic của mỗi instance trở nên kiểm chứng được. |

Một lỗi diễn đạt thường gặp: khẳng định mọi parameterized type **luôn** không thể xuất hiện bên phải `instanceof`. Hãy nói cụ thể hơn về **reifiability**, **kiểu tĩnh của biểu thức**, và **khả năng chuyển kiểu an toàn**. Đây là ba yếu tố giúp giải thích đúng từng trường hợp.

## 12. Bài tập tự kiểm tra

### Bài 1 — Trường hợp nào hợp lệ?

Cho:

```java
Object x = java.util.List.of("a");
```

Phân loại các pattern sau:

1. `x instanceof java.util.List<?> list`: **hợp lệ**, vì `List<?>` reifiable.
2. `x instanceof java.util.List<String> list`: **lỗi biên dịch** từ `Object`, không kiểm tra an toàn được đối số `String`.
3. `x instanceof java.util.Map<?, ?> map`: **hợp lệ về cú pháp/kiểu** nhưng tại runtime trả `false` vì đối tượng là `List`.
4. `x instanceof java.util.List<? extends Number> nums`: **lỗi biên dịch** từ `Object` do kiểu đích không reifiable và không có bằng chứng đủ mạnh từ kiểu tĩnh.

### Bài 2 — Tại sao đoạn này hợp lệ?

```java
static void check(java.util.List<String> values) {
    if (values instanceof java.util.ArrayList<String> arr) {
        System.out.println(arr.size());
    }
}
```

**Đáp án:** tham số `values` đã có kiểu tĩnh `List<String>`; compiler biết generic argument `String`. Kiểm tra runtime chỉ cần phân biệt đối tượng là `ArrayList` hay một implementation khác. Đoạn code không chứng minh rằng Java có một cơ chế đọc đối số generic `String` từ runtime instance.

### Bài 3 — Kiểm tra nội dung thực sự

Cho `Object data = java.util.List.of("Java", 21);`. Vì sao phép `data instanceof List<?>` đúng nhưng `allStrings(data)` ở mục 7 trả `false`?

**Đáp án:** `List<?>` chỉ kiểm tra dữ liệu là container `List`. `allStrings` duyệt lần lượt và gặp phần tử `Integer 21`, nên kết luận danh sách không chỉ gồm chuỗi.

### Bài 4 — Viết API an toàn

Viết hàm nhận `Object` và trả về `Optional<List<String>>` nếu tất cả phần tử là `String`, ngược lại `Optional.empty()`, không dùng unchecked cast.

**Gợi ý và lời giải:** xem `validatedStrings` ở mục 8. Kiểm tra `List<?>` trước, rồi match từng phần tử `String text`, thêm vào `List<String>` mới và trả danh sách kết quả. Cần quyết định rõ có cho phép danh sách rỗng hoặc phần tử null hay không theo yêu cầu nghiệp vụ.

## 13. Ghi nhớ

**`instanceof` kiểm tra được quan hệ kiểu thực thi của đối tượng, nhưng không thể tùy ý xác minh tham số generic đã bị erasure.** Với đầu vào kiểu `Object`, dùng `List<?>` hoặc `Map<?, ?>` để xác nhận container; nếu cần khẳng định kiểu phần tử, hãy xác minh từng phần tử.

Đừng rút ra quy tắc quá rộng rằng mọi parameterized type đều bị cấm trong `instanceof`. Khi kiểu tĩnh của biểu thức đã bảo đảm đối số generic, một narrowing type pattern như `List<String> -> ArrayList<String>` có thể hợp lệ trên Java 17. Sự hợp lệ đó đến từ **thông tin kiểu lúc biên dịch**, không phải từ khả năng JVM đọc lại tham số `String` trên đối tượng.

Tài liệu chính thức:
- [Java Language Specification, Java SE 17 — Reifiable Types (§4.7)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7)
- [Java Language Specification, Java SE 17 — The instanceof Operator (§15.20.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
