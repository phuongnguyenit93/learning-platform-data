# Phân biệt kiểm tra kiểu tổng thể với xác minh kiểu của mọi phần tử trong Java Generics

Khi nhận một giá trị kiểu `Object` từ API, JSON, reflection, mã cũ hoặc một thư viện bên ngoài, ta thường muốn biết: “Đây có phải danh sách chứa toàn `String` hay không?”. Câu hỏi này thực chất gồm **hai yêu cầu kiểm tra khác nhau**:

1. **Kiểm tra kiểu của đối tượng bên ngoài**: giá trị có phải một đối tượng triển khai `List` không?
2. **Xác minh từng phần tử**: mỗi phần tử trong danh sách thực tế có thỏa điều kiện “là `String`” không?

Trong Java, kiểm tra thứ nhất có thể viết bằng `value instanceof List<?>`. Kiểm tra thứ hai cần **duyệt các phần tử và kiểm tra từng giá trị**, chẳng hạn dùng `instanceof String` hoặc `String.class.isInstance(element)`.

```java
// Snippet minh họa trong một phương thức; import java.util.List.
Object value = List.of("Java", 42);

boolean isList = value instanceof List<?>; // true
// Không thể suy ra tất cả phần tử đều là String.
```

Đối tượng trên là một `List` hợp lệ, nhưng chứa `Integer` ở vị trí thứ hai. Vì vậy, `isList == true` **không chứng minh** danh sách là `List<String>` theo nghĩa dữ liệu hiện có đều là `String`.

Đây là khác biệt cốt lõi giữa **kiểm tra hình dạng/kiểu bên ngoài** và **xác minh nội dung dữ liệu**.

## 1. Hai mức kiểm tra trả lời hai câu hỏi khác nhau

Giả sử:

```java
Object input = java.util.List.of("An", 123);
```

Kiểm tra tổng thể:

```java
if (input instanceof java.util.List<?> values) {
    System.out.println("Đây là danh sách với " + values.size() + " phần tử");
}
```

Compiler có thể gán `input` cho biến mẫu `values` kiểu `List<?>` khi kiểm tra thành công. Nhưng kiểu `List<?>` chỉ nói rằng có một **kiểu phần tử chưa biết**; nó không giới hạn kiểu đó thành `String`.

Kiểm tra từng phần tử:

```java
// Snippet tiếp tục trong nhánh đã biết values là List<?>.
boolean allStrings = true;

for (Object element : values) {
    if (!(element instanceof String)) {
        allStrings = false;
        break;
    }
}
```

Với `["An", 123]`, kết quả là `false`. Với `["An", "Binh"]`, kết quả là `true`. Hai đoạn đều biên dịch theo cú pháp Java 17+ khi được đặt vào phương thức hợp lệ, nhưng kiểm tra tổng thể và kiểm tra phần tử có phạm vi khác nhau.

| Giá trị thật | `instanceof List<?>` | Mọi phần tử là `String`? |
| --- | --- | --- |
| `List.of("An", "Binh")` | `true` | `true` |
| `List.of("An", 42)` | `true` | `false` |
| `List.of(1, 2)` | `true` | `false` |
| `List.of()` | `true` | `true` theo điều kiện “mọi phần tử”, vì danh sách rỗng không có phần tử phản ví dụ |
| `"An"` | `false` | Không phải danh sách, nên kiểm tra tổng hợp phải từ chối |
| `null` | `false` | Không phải danh sách, nên kiểm tra tổng hợp phải từ chối |

**Lưu ý với danh sách rỗng:** `allStrings(emptyList)` thường trả `true` theo quy tắc logic “mọi phần tử đều thỏa”; điều đó **không cung cấp bằng chứng có tồn tại phần tử String**. Nếu nghiệp vụ yêu cầu danh sách không rỗng, cần bổ sung điều kiện `!list.isEmpty()`.

## 2. Vì sao `instanceof List<String>` không thay việc kiểm tra từng phần tử?

Generics Java thông thường sử dụng **type erasure**. Kiểu tham số hóa `List<String>` được kiểm tra ở mã nguồn, nhưng runtime class của một `ArrayList<String>` vẫn là `ArrayList`, giống đối tượng `ArrayList<Integer>` tạo từ cùng class.

```java
// Snippet minh họa:
java.util.List<String> text = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

boolean sameClass = text.getClass() == numbers.getClass(); // true
```

Thông tin type argument `String` hoặc `Integer` không khiến Java sinh một class runtime riêng cho mỗi cách tham số hóa. Đối với giá trị chỉ có kiểu tĩnh `Object`, câu lệnh sau **không hợp lệ**:

```java
Object value = java.util.List.of("An");
// boolean result = value instanceof java.util.List<String>; // Lỗi biên dịch
```

Trong khi đó:

```java
Object value = java.util.List.of("An");
boolean result = value instanceof java.util.List<?>; // Hợp lệ, true
```

`List<?>` là **reifiable type**: phép kiểm tra runtime không đòi xác minh một type argument cụ thể. Nó chỉ cần kiểm tra object thực hiện `List`. Còn `List<String>` không phải một parameterized type reifiable để kiểm tra kiểu phần tử `String` trực tiếp theo cách này.

Một số trường hợp `instanceof` với biểu thức đã có kiểu tĩnh rất cụ thể được các phiên bản Java hiện đại xử lý theo quy tắc tương thích kiểu; nhưng điều đó **không** tạo ra cơ chế runtime tổng quát để xác nhận tất cả phần tử của một `Object` là `String`. Khi nhận dữ liệu chưa biết, hãy dùng `List<?>` rồi xác minh nội dung.

## 3. Dữ liệu phải đi qua hai bước kiểm tra

Một hàm xác nhận đúng mục tiêu có thể viết:

```java
// Snippet phương thức có thể đặt trong một class Java.
static boolean isListOfStrings(Object input) {
    if (!(input instanceof java.util.List<?> items)) {
        return false;
    }

    for (Object item : items) {
        if (!(item instanceof String)) {
            return false;
        }
    }

    return true;
}
```

**Bước 1:** nếu `input` không phải `List`, trả `false`. Nhờ pattern matching của `instanceof`, khi vào sau điều kiện `if`, biến `items` đã có kiểu `List<?>` hợp lệ.

**Bước 2:** vòng `for` đọc từng giá trị thành `Object` và hỏi `item instanceof String`. Bất kỳ giá trị sai kiểu nào cũng khiến kết quả là `false`.

**Bước 3:** nếu vòng lặp kết thúc không thấy phản ví dụ, trả `true`. Với danh sách rỗng, vòng lặp không chạy và hàm trả `true`, phù hợp cách hiểu “mọi phần tử thỏa điều kiện”.

Phương thức này trả về một **kết quả xác minh tại thời điểm duyệt**. Nó không thay đổi generic type được khai báo trên tham chiếu cũ và không bảo vệ một danh sách có thể bị sửa ngay sau khi kiểm tra.

### Có thể dùng Stream không?

Có:

```java
static boolean isListOfStrings(Object input) {
    return input instanceof java.util.List<?> items
            && items.stream().allMatch(String.class::isInstance);
}
```

`allMatch` trả `true` khi **mọi** phần tử thỏa predicate; với stream rỗng, kết quả cũng là `true`. Cú pháp ngắn hơn nhưng vẫn thực hiện kiểm tra trên từng phần tử cho đến khi có thể quyết định kết quả.

Về mặt hành vi, `allMatch` là **short-circuiting terminal operation**: có thể dừng ngay khi gặp phần tử không phù hợp. Không nên xem việc dùng stream như một phép kiểm tra type argument được JVM cung cấp sẵn; nó vẫn phải xét dữ liệu.

## 4. Kiểm tra mọi phần tử không có nghĩa danh sách đã trở thành `List<String>`

Xét:

```java
Object input = java.util.List.of("An", "Binh");

if (input instanceof java.util.List<?> items) {
    boolean verified = items.stream().allMatch(String.class::isInstance);

    // Dù verified là true, kiểu tĩnh của items vẫn là List<?>.
    // java.util.List<String> result = items; // Không biên dịch
}
```

Kết quả boolean là một khẳng định về **những phần tử vừa kiểm tra**, nhưng compiler Java không có cơ chế tự chuyển kiểu tĩnh `List<?>` thành `List<String>` chỉ vì một phép kiểm tra bằng vòng lặp trả `true`. Java không phải một hệ thống kiểu có khả năng suy luận tự động điều kiện “mọi phần tử trong collection đều String” thành thay đổi type argument của biến.

Có ba hướng tùy mục tiêu:

1. Chỉ cần kết luận đúng/sai: giữ kết quả boolean và tiếp tục làm việc qua `List<?>`.
2. Cần dùng một `List<String>` có dữ liệu đáng tin: **kiểm tra từng phần tử rồi sao chép sang danh sách mới với kiểu đúng**.
3. Cần tránh sao chép vì hiệu năng: chỉ dùng một cast được kiểm soát khi có hợp đồng dữ liệu đủ mạnh và kiểm soát được mọi cách danh sách có thể bị sửa; đây là tình huống có điều kiện an toàn chặt chẽ, không phải mặc định.

Đừng viết `(List<String>) items` rồi cho rằng phép cast tự quét từng phần tử. Java không có kiểm tra runtime đầy đủ cho type argument `String` của `List<String>`.

## 5. Kiểm tra rồi sao chép sang danh sách có kiểu đáng tin

Khi xử lý dữ liệu bên ngoài, phương án rõ ràng là **tạo bản sao được xác thực**. Với `Class<T>` từ caller, có thể viết một adapter generic:

```java
// Snippet phương thức; cần java.util.List và java.util.ArrayList.
static <T> java.util.List<T> validatedCopy(Object value, Class<T> expected) {
    if (!(value instanceof java.util.List<?> items)) {
        throw new IllegalArgumentException("Not a list");
    }

    java.util.List<T> result = new java.util.ArrayList<>();
    for (int i = 0; i < items.size(); i++) {
        Object item = items.get(i);
        if (!expected.isInstance(item)) {
            throw new IllegalArgumentException("Invalid element at " + i);
        }
        result.add(expected.cast(item));
    }

    return java.util.List.copyOf(result);
}
```

Lời gọi:

```java
// Snippet trong phương thức:
java.util.List<String> names =
        validatedCopy(java.util.List.of("An", "Binh"), String.class);
```

Cơ chế:

- `value instanceof List<?> items` xác nhận cấu trúc bên ngoài.
- `expected.isInstance(item)` kiểm tra class runtime của **mỗi** phần tử. Với `String.class`, chỉ các instance `String` được chấp nhận; `null` bị từ chối vì `Class.isInstance(null)` là `false`.
- `expected.cast(item)` thực hiện cast được kiểm tra; compiler biết kết quả có kiểu `T`, nhờ token `Class<T>`.
- `List.copyOf(result)` tạo kết quả không sửa được và không chứa `null`. Nó là **bản sao nông** (*shallow copy*): nếu các phần tử là đối tượng mutable thì nội trạng của chúng vẫn có thể thay đổi; riêng `String` là bất biến.

Vì danh sách kết quả mới không dùng chung bộ chứa phần tử có thể sửa với nguồn, việc sửa cấu trúc danh sách nguồn **sau khi sao chép xong** không chèn được một phần tử sai kiểu vào danh sách kết quả.

Nhưng **kiểm tra từng phần tử không tự động chống race** khi một luồng khác đang sửa danh sách *trong quá trình duyệt*. Với collection có thể thay đổi đồng thời, cần đồng bộ hóa, snapshot nhất quán theo hợp đồng nguồn, hoặc yêu cầu ownership thích hợp trước khi duyệt. Một vòng lặp đọc thông thường không hứa cung cấp snapshot nguyên tử.

## 6. Chương trình Java 17+ chạy đầy đủ

Lưu toàn bộ chương trình sau trong **`OverallVsElementsDemo.java`**:

```java
public class OverallVsElementsDemo {
    static boolean allStrings(Object value) {
        if (!(value instanceof java.util.List<?> items)) {
            return false;
        }
        for (Object item : items) {
            if (!(item instanceof String)) {
                return false;
            }
        }
        return true;
    }

    static <T> java.util.List<T> validatedCopy(
            Object value, Class<T> expected) {
        if (!(value instanceof java.util.List<?> items)) {
            throw new IllegalArgumentException("Not a list");
        }

        java.util.List<T> result = new java.util.ArrayList<>();
        for (int i = 0; i < items.size(); i++) {
            Object item = items.get(i);
            if (!expected.isInstance(item)) {
                throw new IllegalArgumentException(
                        "Invalid element at " + i);
            }
            result.add(expected.cast(item));
        }

        return java.util.List.copyOf(result);
    }

    static boolean nestedStrings(Object value) {
        if (!(value instanceof java.util.List<?> rows)) {
            return false;
        }
        for (Object row : rows) {
            if (!(row instanceof java.util.List<?> cells)) {
                return false;
            }
            for (Object cell : cells) {
                if (!(cell instanceof String)) {
                    return false;
                }
            }
        }
        return true;
    }

    public static void main(String[] args) {
        Object mixed = java.util.List.of("Java", 42);
        Object valid = java.util.List.of("An", "Binh");
        Object empty = java.util.List.of();

        System.out.println("Mixed instanceof List<?>: "
                + (mixed instanceof java.util.List<?>));
        System.out.println("Mixed all Strings: " + allStrings(mixed));
        System.out.println("Valid all Strings: " + allStrings(valid));
        System.out.println("Empty all Strings: " + allStrings(empty));

        try {
            validatedCopy(mixed, String.class);
        } catch (IllegalArgumentException exception) {
            System.out.println("Mixed copy rejected: "
                    + exception.getMessage());
        }

        java.util.List<String> copy = validatedCopy(valid, String.class);
        System.out.println("Validated copy: " + copy);
        System.out.println("Copy shares list object: " + (copy == valid));

        Object goodNested = java.util.List.of(
                java.util.List.of("A"), java.util.List.of("B"));
        Object badNested = java.util.List.of(
                java.util.List.of("A"), java.util.List.of(7));

        System.out.println("Nested valid: " + nestedStrings(goodNested));
        System.out.println("Nested invalid: " + nestedStrings(badNested));

        Object array = new String[] { "x" };
        System.out.println("String[] runtime check: "
                + (array instanceof String[]));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 OverallVsElementsDemo.java
java OverallVsElementsDemo
```

Standard output:

```text
Mixed instanceof List<?>: true
Mixed all Strings: false
Valid all Strings: true
Empty all Strings: true
Mixed copy rejected: Invalid element at 1
Validated copy: [An, Binh]
Copy shares list object: false
Nested valid: true
Nested invalid: false
String[] runtime check: true
```

Các kết quả minh họa những điều quan trọng:

- `mixed instanceof List<?>` là `true` mặc dù `mixed` chứa `Integer`.
- `allStrings(mixed)` trả `false` sau khi gặp `42`, còn `allStrings(valid)` là `true`.
- Danh sách rỗng cho kết quả `true` với điều kiện “mọi phần tử là String”. Nếu cần không rỗng, hãy kiểm tra riêng.
- `validatedCopy(mixed, String.class)` từ chối phần tử ở chỉ số 1 và báo vị trí rõ ràng.
- Bản sao xác thực không cùng đối tượng với danh sách nguồn.
- Hai lớp dữ liệu `List<List<String>>` cần hai tầng kiểm tra: danh sách ngoài chứa các danh sách con, rồi mỗi danh sách con chứa đúng `String`.
- `String[]` có kiểu thành phần nhận biết ở runtime; đó là cơ chế khác với việc kiểm tra generic element của `List<String>`.

## 7. Tình huống danh sách rỗng, phần tử null và kiểm tra định lượng

### 7.1. “Mọi phần tử thỏa” khác “có ít nhất một phần tử thỏa”

Với `List.of()`, kết quả của `allMatch(String.class::isInstance)` là `true`; đây là **chân lý rỗng** (*vacuous truth*) của mệnh đề “mọi phần tử”.

Nếu yêu cầu nghiệp vụ là **danh sách phải có ít nhất một chuỗi**, hãy viết:

```java
static boolean nonEmptyStringList(Object input) {
    return input instanceof java.util.List<?> list
            && !list.isEmpty()
            && list.stream().allMatch(String.class::isInstance);
}
```

Đừng dùng `anyMatch` thay `allMatch` nếu hợp đồng yêu cầu **mọi** phần tử đều thỏa. `anyMatch` chỉ cần **ít nhất một** phần tử là `String`.

Ví dụ với `["An", 42]`: `anyMatch(String.class::isInstance)` là `true` nhưng `allMatch(String.class::isInstance)` là `false`.

### 7.2. Null có được chấp nhận không?

Biểu thức `null instanceof String` là `false`, và `String.class.isInstance(null)` cũng là `false`. Do đó cả `allStrings` lẫn `validatedCopy` ở trên có **hợp đồng nghiêm ngặt không chấp nhận null**.

Cần nói rõ vì một biến `List<String>` ở mã nguồn Java **có thể chứa null** nếu collection cho phép: type argument `String` tự nó không có nghĩa “non-null String”. Nếu nghiệp vụ cho phép `null`, cần diễn đạt predicate rõ ràng:

```java
static boolean stringsOrNull(Object input) {
    return input instanceof java.util.List<?> list
            && list.stream().allMatch(
                    element -> element == null || element instanceof String);
}
```

Không nên dùng nguyên `List.copyOf` cho danh sách có thể chứa null: API này **không chấp nhận phần tử null**. Khi cho phép null, có thể sao chép vào `ArrayList<String>` sau khi kiểm tra, rồi áp dụng một chiến lược không sửa được phù hợp nếu cần.

### 7.3. Kiểm tra mọi phần tử chỉ là một loại validation

Một danh sách chỉ chứa `String` vẫn có thể sai nghiệp vụ: chuỗi rỗng, quá dài, không đúng định dạng hoặc chứa giá trị trùng lặp. Bài toán “type validation” chỉ xác nhận **loại phần tử**; validation nghiệp vụ có thể cần những predicate bổ sung:

```java
// Snippet minh họa:
boolean valid = input instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.stream().allMatch(
                item -> item instanceof String s
                        && !s.isBlank()
                        && s.length() <= 50);
```

Những yêu cầu này phải đến từ hợp đồng dữ liệu cụ thể, không nên tự áp chúng khi chỉ được hỏi “có phải danh sách String không?”.

## 8. Dữ liệu lồng nhau: phải kiểm tra từng tầng

Giả sử muốn xác thực dữ liệu có cấu trúc gần với `List<List<String>>`:

```java
Object rows = java.util.List.of(
        java.util.List.of("A", "B"),
        java.util.List.of("C"));
```

Kiểm tra `rows instanceof List<?>` chỉ nói rằng **bên ngoài** là danh sách. Nó không chứng minh:

1. Từng phần tử bên ngoài là một danh sách khác.
2. Từng phần tử của các danh sách con là `String`.

Vì vậy, cần kiểm tra lần lượt:

```java
static boolean nestedStrings(Object value) {
    if (!(value instanceof java.util.List<?> rows)) {
        return false;
    }
    for (Object row : rows) {
        if (!(row instanceof java.util.List<?> cells)) {
            return false;
        }
        for (Object cell : cells) {
            if (!(cell instanceof String)) {
                return false;
            }
        }
    }
    return true;
}
```

Mỗi tầng generic bị xóa kiểu đều cần được xác minh theo cấu trúc thực tế nếu đầu vào chưa đáng tin. Với dữ liệu lồng nhau nhiều tầng, có thể thiết kế validator đệ quy hoặc parser có schema; nhưng việc xác minh đúng **cấu trúc và từng lá** vẫn là trách nhiệm của cơ chế validation.

Cùng ý tưởng áp dụng cho `Map<String, Integer>`: `value instanceof Map<?, ?>` chỉ kiểm tra là một `Map`. Muốn xác nhận `String` ở khóa và `Integer` ở giá trị, cần duyệt `entrySet()` và kiểm tra **cả key lẫn value**.

## 9. Kiểm tra class với `Class<T>`: hữu ích nhưng có giới hạn

`Class<T>` cung cấp token của một class runtime cụ thể:

```java
static <T> boolean everyElementIs(
        Object input, Class<T> expected) {
    return input instanceof java.util.List<?> list
            && list.stream().allMatch(expected::isInstance);
}
```

Ví dụ `everyElementIs(List.of(1, 2), Number.class)` là `true`, vì `Integer` là subtype của `Number`. `Class.isInstance` kiểm tra **khả năng gán tương thích** theo runtime class, không đòi `element.getClass() == Number.class`.

Nếu nghiệp vụ đòi đúng class cụ thể và **không cho phép subclass**, cần quy tắc khác, ví dụ `element != null && element.getClass() == expected`. Đây là một lựa chọn thiết kế, thường không cần trong API hướng đối tượng thông thường.

Nhưng một token `Class<T>` **không mô tả đầy đủ kiểu tham số hóa lồng nhau**. Không có class literal Java dạng `List<String>.class` để xác minh tất cả phần tử. `List.class` chỉ giúp xác nhận class/interface bên ngoài; token `String.class` giúp kiểm tra một phần tử tại một thời điểm.

Muốn xác minh `List<List<String>>` thì cần thông tin cấu trúc “list của list của string” và các bước kiểm tra tương ứng, không thể chỉ truyền `List.class` một lần.

## 10. Kiểm tra tổng thể của array khác collection generic như thế nào?

Array Java mang **runtime component type**, còn collection generic thông thường không lưu type argument cụ thể như một phần runtime class của từng instance.

```java
Object value = new String[] { "A", "B" };

System.out.println(value instanceof String[]); // true
```

Với mảng `String[]`, JVM có thể xác minh object là mảng chứa phần tử kiểu `String` theo runtime component type. Nếu một tham chiếu `Object[]` trỏ tới mảng `String[]` thực tế, cố ghi `Integer` sẽ gây `ArrayStoreException`:

```java
Object[] array = new String[1];

try {
    array[0] = 42;
} catch (ArrayStoreException exception) {
    System.out.println("Rejected by runtime array type");
}
```

Mảng có kiểm tra kiểu thành phần khi ghi. Trong khi đó, nếu mã raw hoặc unchecked operation đưa `Integer` vào đối tượng `List<String>`, generic collection không có kiểm tra kiểu phần tử được duy trì bởi runtime container theo cách mảng có. Lỗi có thể xuất hiện lúc cast trên đường đọc dữ liệu thành `String`.

Cũng cần hiểu `String[]` là một array có component type reifiable, còn `List<String>` **không phải kiểu reifiable**. Java cho phép `new List<?>[3]` vì `List<?>` reifiable, nhưng không cho phép tạo trực tiếp `new List<String>[3]`.

Tuy vậy, kiểm tra `instanceof String[]` chỉ khẳng định runtime array component type. Nó không tự đánh giá những điều kiện nghiệp vụ như độ dài, phần tử rỗng, quy tắc định dạng hay chính sách cho phép `null`.

## 11. Vì sao unchecked cast không chứng minh kiểu mọi phần tử?

Xét đoạn cố ý không an toàn:

```java
// Snippet minh họa cảnh báo unchecked, không phải mẫu nên dùng.
Object value = java.util.List.of("Java", 42);

@SuppressWarnings("unchecked")
java.util.List<String> casted = (java.util.List<String>) value;

// String second = casted.get(1); // Có thể ném ClassCastException
```

Cast `(List<String>) value` không kiểm tra từng phần tử là `String`. Khi runtime chỉ có thể xác nhận phần raw `List`, việc tin tưởng type argument `String` là **unchecked**. `@SuppressWarnings("unchecked")` chỉ che cảnh báo, không làm cast trở nên có khả năng kiểm tra generic contents.

Nếu cố lấy `casted.get(1)` thành `String`, compiler có thể chèn `checkcast String`, và phần tử `42` khiến `ClassCastException` xuất hiện.

**Quy tắc:** muốn xác minh toàn bộ phần tử, phải có bằng chứng từ cấu trúc dữ liệu đáng tin hoặc tự kiểm tra; một unchecked cast không tạo ra bằng chứng đó.

Tương tự, raw type có thể gây **heap pollution**:

```java
// Snippet mô tả dữ liệu bị làm bẩn.
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(42); // Unchecked warning, nhưng có thể ghi Integer vào List<String>
```

Điều này cho thấy việc kiểm tra một `List` bên ngoài hợp lệ hoàn toàn không đủ để bảo đảm các đối tượng bên trong phù hợp với một type argument mong muốn.

## 12. Kiểm tra một lần chưa đủ nếu dữ liệu có thể thay đổi

Giả sử một thread xác nhận mọi phần tử là `String`, nhưng thread khác sau đó thay đổi danh sách qua raw reference. Kiểm tra đã đúng **tại một thời điểm**, song danh sách hiện tại có thể không còn đúng.

Ngay cả khi chỉ một luồng, một API khác giữ alias tới `ArrayList` cũng có thể thêm phần tử sau khi hàm validation trả về.

Nếu cần một kết quả ổn định:

1. **Nắm rõ quyền sở hữu dữ liệu**: ai có thể thay đổi collection?
2. **Kiểm tra trong thời điểm/điều kiện nhất quán**: không duyệt danh sách đang bị thay đổi không được kiểm soát rồi tưởng đó là một snapshot nguyên tử.
3. **Sao chép các phần tử đã qua kiểm tra** vào collection mới có kiểu tương ứng, thay vì cast tham chiếu gốc.
4. **Ngăn sửa cấu trúc bản sao** nếu kết quả phải giữ hợp đồng lâu dài: dùng `List.copyOf` khi phần tử không null, hoặc view không sửa được trên bản sao phù hợp.

`List.copyOf` là bản sao **nông** và không làm các object bên trong trở nên bất biến. Với `String`, phần tử vốn bất biến nên kết quả tương đối đơn giản; với `List<Person>`, một `Person` có thể vẫn thay đổi nội trạng. Validation kiểu class không đồng nghĩa validation toàn bộ trạng thái của object.

Một số API như `Collections.checkedList(list, String.class)` tạo wrapper kiểm tra kiểu của **các lần thêm qua wrapper đó**, nhưng không xác nhận tự động mọi dữ liệu đã có trong list và không ngăn một alias khác ghi thẳng vào list gốc. Đây là cơ chế phòng ngừa tương lai, khác với việc duyệt để xác minh mọi phần tử hiện có.

## 13. Reflection và generic metadata không xác nhận nội dung

Reflection có thể đọc thông tin một trường được **khai báo** là `List<String>`:

```java
class Sample {
    java.util.List<String> names;
}
```

`Sample.class.getDeclaredField("names").getGenericType()` có thể trả về dạng biểu diễn `List<String>` trong metadata `Signature`, còn `getType()` thường trả về raw runtime interface `List`.

Nhưng thông tin đó mô tả **kiểu khai báo của trường**, không phải bằng chứng collection gắn vào trường lúc chạy chỉ chứa `String`. Raw type, unchecked conversion, reflection hoặc nguồn dữ liệu không tin cậy vẫn có thể phá bất biến generic mà compiler đã bảo vệ trong mã nguồn bình thường.

Vì thế, reflection giúp hiểu **hợp đồng kiểu dự kiến**, nhưng khi nhận dữ liệu từ ranh giới không đáng tin, việc xác thực các phần tử vẫn phụ thuộc dữ liệu thực tế và chiến lược kiểm tra đã chọn.

## 14. Thiết kế API: cần kiểm tra kiểu ở đâu?

Nếu API nhận một `List<String>` từ **mã nguồn Java được biên dịch an toàn**, compiler đã kiểm tra phần lớn quan hệ type argument ở điểm gọi. Không cần chạy kiểm tra toàn bộ phần tử ở mọi phương thức chỉ để lặp lại công việc của compiler, trừ khi API có yêu cầu khác (như không cho null, phải đúng định dạng, chống dữ liệu bị làm bẩn).

Nếu API nhận `Object`, raw `List`, dữ liệu JSON được ánh xạ động hoặc đầu vào có thể qua unchecked operation, hãy xác định rõ:

| Trường hợp | Kiểm tra phù hợp | Ý nghĩa |
| --- | --- | --- |
| Chỉ cần biết có phải danh sách | `instanceof List<?>` | Kiểm tra interface bên ngoài |
| Cần mọi phần tử là String | Kiểm tra ngoài, rồi `allMatch(String.class::isInstance)` | Xác minh dữ liệu tại thời điểm duyệt |
| Cần ít nhất một phần tử và mọi phần tử là String | Thêm `!list.isEmpty()` | Tránh việc danh sách rỗng qua validation |
| Cho phép phần tử null | Kiểm tra `item == null` **hoặc** `item instanceof String` | Nêu rõ null policy |
| Cần trả `List<String>` ổn định | Xác minh, cast từng phần tử rồi sao chép | Có collection mới mang kiểu tĩnh đúng |
| Cần `List<List<String>>` | Kiểm tra từng tầng và các phần tử ở lá | Xác minh cấu trúc lồng nhau |
| Cần xác minh nghiệp vụ | Thêm điều kiện nội dung/format/giới hạn | Loại phần tử đúng vẫn có thể sai nghiệp vụ |

Nếu dữ liệu đã đi qua một parser/schema validator tin cậy có hợp đồng rõ ràng, việc xác minh có thể được đặt tại **ranh giới nhập dữ liệu**, rồi luồng nội bộ duy trì invariants bằng type system và ownership. Không nhất thiết phải lặp kiểm tra nặng khắp mọi tầng ứng dụng.

## 15. Những sai lầm thường gặp

**Sai lầm 1: “`instanceof List<?>` trả true nghĩa là `List<String>`.”** Không. Nó chỉ xác nhận object thực hiện `List`, không kiểm tra type argument.

**Sai lầm 2: “Chỉ cần phần tử đầu tiên là String.”** Không. Danh sách có thể bắt đầu bằng `String` rồi chứa `Integer` ở vị trí sau, nên kiểm tra phải bao phủ mọi phần tử được yêu cầu.

**Sai lầm 3: “`anyMatch` và `allMatch` giống nhau.”** Không. `anyMatch` kiểm tra tồn tại ít nhất một phần tử thỏa; `allMatch` yêu cầu tất cả thỏa.

**Sai lầm 4: “Danh sách rỗng phải bị coi là không phải `List<String>`.”** Điều đó là quyết định hợp đồng. Mệnh đề “mọi phần tử là String” đúng trên tập rỗng; nếu yêu cầu có dữ liệu, cần thêm `!isEmpty()`.

**Sai lầm 5: “Generic `List<String>` mặc định cấm null.”** Không. Java type argument `String` không tự cấm null. Phải đặt quy tắc riêng nếu không cho phép null.

**Sai lầm 6: “Cast `(List<String>)` đã kiểm tra mọi phần tử.”** Không. Do type erasure, type argument không được xác minh như một phần của cast thông thường.

**Sai lầm 7: “Reflection thấy `List<String>` nghĩa là dữ liệu chắc chắn chỉ chứa String.”** Không. Reflection có thể thấy metadata khai báo, không xác nhận nội dung runtime.

**Sai lầm 8: “Kiểm tra xong thì collection mãi mãi an toàn.”** Không nếu collection hoặc đối tượng bên trong còn mutable, có alias hoặc có thao tác không an toàn. Cần kiểm soát mutation hoặc snapshot.

**Sai lầm 9: “`Class<T>` biểu diễn được mọi generic type lồng nhau.”** Không. `Class<String>` giúp kiểm tra `String`; kiểu như `List<List<String>>` đòi mô tả cấu trúc và validation nhiều tầng.

## 16. Bài tập tự kiểm tra

**Câu 1.** `Object x = List.of("A", 7); x instanceof List<?>;` là `true` hay `false`?

`true`: lớp bao ngoài là một danh sách. Kết quả không phụ thuộc việc danh sách chứa kiểu phần tử nào.

**Câu 2.** Với `List.of("A", 7)`, `allMatch(String.class::isInstance)` cho kết quả gì?

`false`, vì `7` là `Integer`, không phải `String`.

**Câu 3.** Vì sao `List.of().stream().allMatch(String.class::isInstance)` là `true`?

Vì không có phần tử phản ví dụ; đây là định nghĩa của kiểm tra “mọi phần tử” trên tập rỗng.

**Câu 4.** `List<String>` có cho phép `null` không?

Kiểu `List<String>` tự nó không cấm `null`. Khả năng chèn null phụ thuộc implementation và hợp đồng collection; `List.of` và `List.copyOf` không cho phép phần tử null.

**Câu 5.** Nếu đã kiểm tra `List<?>` chứa toàn `String`, có thể gán trực tiếp nó cho `List<String>` không?

Không. Kiểu tĩnh vẫn là `List<?>`; cần cơ chế chuyển đổi có chứng minh an toàn như kiểm tra từng phần tử rồi sao chép.

**Câu 6.** `Object x = List.of(List.of("A"), List.of(9)); x instanceof List<?>;` có đủ để xác nhận `List<List<String>>` không?

Không. Cần kiểm tra từng phần tử ngoài là `List<?>` và tất cả phần tử của từng danh sách con là `String`.

**Câu 7.** `String[]` khác `List<String>` ở khả năng kiểm tra runtime như thế nào?

`String[]` giữ component type `String` tại runtime; `List<String>` không có runtime class riêng giữ type argument `String` cho phép `instanceof List<String>` như cách kiểm tra với `Object` chưa biết kiểu.

## 17. Quy tắc áp dụng

```text
Object đầu vào
    |
    v
instanceof List<?> ?
    | không -> từ chối đầu vào
    | có
    v
Duyệt từng phần tử
    | gặp sai kiểu -> từ chối / trả false
    | tất cả hợp lệ
    v
Nếu chỉ cần câu trả lời -> true
Nếu cần List<T> đáng tin -> cast từng phần tử và tạo bản sao phù hợp
```

**Kết luận:** `instanceof List<?>` chỉ kiểm tra **đối tượng tổng thể** có là danh sách hay không. Khi hợp đồng yêu cầu **mọi phần tử** mang một kiểu cụ thể, Java phải kiểm tra các phần tử thật hoặc dựa vào một nguồn dữ liệu đã bảo đảm hợp đồng. Type erasure khiến một type argument như `String` không được xác minh trực tiếp qua runtime class của `List`. Hãy phân biệt kiểm tra bên ngoài, kiểm tra từng phần tử và tạo bản sao đã xác thực; đồng thời nêu rõ cách xử lý danh sách rỗng, null, dữ liệu lồng nhau và mutation.