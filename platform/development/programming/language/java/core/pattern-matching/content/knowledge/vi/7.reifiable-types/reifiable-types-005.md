# Pattern với wildcard trong Java 21

## 1. Mục tiêu và ngữ cảnh

Khi học pattern matching cùng Java generics, bạn sẽ gặp mã như sau:

```java
Object candidate = java.util.List.of("A", "B");

if (candidate instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
```

`List<?> elements` là **type pattern**: chương trình kiểm tra `candidate` có phải một `List` hay không và, nếu khớp, tạo **pattern variable** `elements` có kiểu `List<?>`. Dấu `?` ở đây là **wildcard type argument của generics**, diễn đạt “kiểu phần tử chưa biết”. Nó **không** tự kiểm tra từng phần tử và cũng **không phải** một loại pattern độc lập.

Bài này giải thích cách đọc và viết pattern có wildcard trong Java 21, vì sao `List<?>` được phép kiểm tra bằng `instanceof` hoặc `switch`, giới hạn của **type erasure**, cách kiểm tra phần tử an toàn, tương tác với **record pattern** và các lỗi thường gặp.

Sau bài học, bạn cần phân biệt được:

1. `List<?> list`: type pattern có **unbounded wildcard** ở kiểu generic.
2. `List<String> list`: kiểu tham số hóa cụ thể, thường **không thể kiểm tra an toàn từ `Object`**.
3. `List<? extends Number>` và `List<? super Integer>`: bounded wildcards hữu ích trong khai báo API nhưng không có cùng khả năng runtime-check như `List<?>`.
4. `Box<?> box`: type pattern cho generic record; có thể kiểm tra các component sau khi khớp.
5. Dấu `?` của generics khác dấu `_` của **unnamed pattern** (preview trong Java 21).

## 2. Wildcard `?` thực chất biểu thị điều gì?

Generics cho phép định nghĩa kiểu chứa kiểu khác:

```java
java.util.List<String> words = java.util.List.of("Java", "Pattern");
java.util.List<Integer> numbers = java.util.List.of(10, 20);
```

`List<String>` và `List<Integer>` có cùng kiểu raw `List`, nhưng trình biên dịch theo dõi kiểu phần tử riêng để hỗ trợ type safety.

Khi chỉ cần biết “đây là một danh sách, chưa quan tâm kiểu phần tử”, dùng **unbounded wildcard**:

```java
java.util.List<?> unknownElements = words;
unknownElements = numbers;
```

`List<?>` có nghĩa: *danh sách này có một kiểu phần tử nào đó, nhưng ở vị trí đang đọc ta chưa biết đó là kiểu nào*. Nó **không** có nghĩa là “danh sách bảo đảm chứa mọi kiểu”, càng không có nghĩa là “các phần tử đã được xác minh là `Object` theo ý nghĩa có thể thêm bất kỳ đối tượng nào”.

Đọc ra giá trị từ `List<?>` một cách an toàn:

```java
Object first = unknownElements.get(0);
```

Nhưng không thể thêm một `String` hoặc `Integer` bất kỳ:

```java
// LỖI BIÊN DỊCH: không biết kiểu phần tử thật sự
unknownElements.add("new item");
```

Có thể truyền `null` theo giới hạn kiểu của `List<?>` trong nhiều trường hợp, nhưng **khả năng biên dịch không bảo đảm danh sách có thể sửa đổi**: `List.of(...)` là immutable/unmodifiable và sẽ từ chối thao tác cập nhật. Không dùng `add(null)` làm cách giải quyết bài toán kiểu phần tử.

## 3. Vì sao `List<?>` dùng được trong pattern?

### 3.1. Type erasure và reifiable types

Java generics dùng **type erasure**: tại runtime, đối tượng `ArrayList<String>` và `ArrayList<Integer>` đều được nhận diện bằng lớp `ArrayList`; JVM không giữ một “nhãn runtime `String`” cho toàn bộ đối tượng danh sách để `instanceof` xác minh.

Java Language Specification §4.7 gọi kiểu có đủ thông tin để thực hiện kiểm tra runtime là **reifiable type**. Với generic, một kiểu tham số hóa được coi là reifiable khi **tất cả đối số kiểu của nó đều là unbounded wildcard**.

| Kiểu | Reifiable trong Java 21? | Ghi chú |
| --- | --- | --- |
| `String` | **Có** | Kiểu class không generic |
| `List<?>` | **Có** | Một đối số kiểu là `?` không giới hạn |
| `Map<?, ?>` | **Có** | Cả hai đối số đều là `?` |
| `Box<?>` | **Có** | Nếu `Box<T>` là generic class hoặc record |
| `List` (raw) | **Có** | Dùng raw type được, nhưng mất an toàn generic khi thao tác |
| `List<String>` | **Không** | Thông tin `String` không kiểm tra được từ đối tượng tùy ý |
| `List<? extends Number>` | **Không** | Wildcard có bound, không phải unbounded `?` |
| `List<? super Integer>` | **Không** | Wildcard có bound |
| `Map<String, ?>` | **Không** | Có đối số `String` cụ thể |
| `List<List<?>>` | **Không** | Đối số của `List` ngoài là `List<?>`, không phải `?` trực tiếp |

Vì vậy, kiểm tra từ một giá trị có kiểu tĩnh `Object`:

```java
Object candidate = java.util.List.of("one", "two");

if (candidate instanceof java.util.List<?> elements) {
    System.out.println(elements.size()); // Hợp lệ
}
```

Pattern chỉ xác nhận **kiểu thùng chứa là `List`**. Dù ví dụ dùng `List.of("one", "two")`, chính pattern `List<?> elements` không biết gì về `String` trong các phần tử.

### 3.2. Mẫu không hợp lệ khi nguồn là `Object`

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
Object candidate = java.util.List.of("one", "two");

if (candidate instanceof java.util.List<String> strings) {
    System.out.println(strings.get(0));
}
```

Đây là phép kiểm tra từ `Object` sang `List<String>` không thể được JVM xác minh một cách đầy đủ; compiler từ chối. Không có cách biến `instanceof` thành phép kiểm tra tự động mọi phần tử bằng cách viết đối số generic cụ thể.

Tương tự, từ `Object`:

```java
// Đều không hợp lệ từ nguồn Object:
candidate instanceof java.util.List<? extends Number> nums
candidate instanceof java.util.Map<String, ?> records
```

**Nuance quan trọng:** đừng biến các ví dụ trên thành quy tắc “mọi `instanceof` có kiểu generic cụ thể đều bị cấm”. Từ Java 16, compiler cho phép một số trường hợp khi **kiểu tĩnh của toán hạng trái** đã cung cấp đủ thông tin và phép chuyển kiểu là *checked cast conversion*. Ví dụ:

```java
java.util.List<String> words = new java.util.ArrayList<>();

if (words instanceof java.util.ArrayList<String> arrayList) {
    System.out.println(arrayList.size());
}
```

Trường hợp này hợp lệ vì `words` đã có kiểu `List<String>` ở thời điểm biên dịch; phép kiểm tra bổ sung ở runtime chủ yếu xác minh lớp cụ thể `ArrayList`. Nó **không phải** kiểm tra type argument của danh sách bất kỳ lấy từ `Object`.

Cách đánh giá đúng là xem compiler có thể thực hiện **checked cast** từ *kiểu tĩnh bên trái* sang kiểu pattern hay không (JLS §14.30.3 và §5.5).

## 4. Type pattern với `List<?>` trong `instanceof`

Mẫu thông dụng:

```java
static String sizeOfList(Object candidate) {
    if (candidate instanceof java.util.List<?> elements) {
        return "size=" + elements.size();
    }
    return "not a list";
}
```

Cấu tạo cú pháp:

- `candidate`: giá trị cần kiểm tra.
- `instanceof`: toán tử kiểm tra và, khi match, giới thiệu biến.
- `List<?>`: **kiểu reifiable** được phép dùng cho type pattern từ `Object`.
- `elements`: **pattern variable** có scope trong nhánh mà compiler biết pattern đã khớp.

Nếu `candidate` là `null`, điều kiện không khớp. Nếu là một `List<String>`, `List<Integer>`, `List<Object>` hoặc một triển khai `List` khác, pattern vẫn có thể khớp vì nó kiểm tra **loại container**.

Những điều bạn có thể làm khi đã khớp:

```java
if (candidate instanceof java.util.List<?> elements) {
    int size = elements.size();
    for (Object element : elements) {
        System.out.println(element);
    }
}
```

Những điều bạn **không** được suy luận:

- Không được coi `elements` là `List<String>` và gọi các phương thức `String` trực tiếp trên `elements.get(0)`.
- Không được suy ra mọi phần tử đều khác `null`; một số danh sách cho phép chứa `null`.
- Không được suy ra danh sách có thể thay đổi; `List.of`, `List.copyOf` và nhiều triển khai khác là unmodifiable.
- Không được suy ra kiểu phần tử dựa vào phần tử đầu tiên: danh sách có thể dị kiểu hoặc rỗng.

## 5. Pattern với nhiều wildcard: `Map<?, ?>`

Khi một lớp/interface generic có nhiều tham số kiểu, cần dùng wildcard tương ứng cho mỗi tham số nếu muốn kiểu reifiable:

```java
static String describeMap(Object candidate) {
    if (candidate instanceof java.util.Map<?, ?> entries) {
        return "entries=" + entries.size();
    }
    return "not a map";
}
```

`Map<?, ?> entries` là **một type pattern**, không phải hai pattern. Hai dấu `?` là đối số kiểu của `Map<K, V>`:

- `K`: chưa biết kiểu key.
- `V`: chưa biết kiểu value.
- `entries`: biến pattern đại diện **toàn bộ map**.

Nếu cần duyệt:

```java
if (candidate instanceof java.util.Map<?, ?> entries) {
    for (java.util.Map.Entry<?, ?> entry : entries.entrySet()) {
        Object key = entry.getKey();
        Object value = entry.getValue();
        System.out.println(key + " -> " + value);
    }
}
```

Bạn có thể đọc key/value dưới dạng `Object` và kiểm tra tiếp từng giá trị. Nhưng không thể giả định đây là `Map<String, Integer>` chỉ vì `Map<?, ?>` đã match.

Ví dụ một `Map<?, ?>` có thể có key `String`, `Integer` hoặc kiểu khác; muốn dùng đúng kiểu nghiệp vụ, hãy kiểm tra key/value trước khi xử lý.

## 6. Kiểm tra từng phần tử bằng pattern sau khi container khớp

Đây là kỹ thuật thực tế nhất khi nhận dữ liệu từ API hoặc từ nơi khai báo kiểu tổng quát:

```java
static int sumIntegers(Object candidate) {
    if (!(candidate instanceof java.util.List<?> elements)) {
        return 0;
    }
    int total = 0;
    for (Object element : elements) {
        if (element instanceof Integer number) {
            total += number;
        }
    }
    return total;
}
```

Chương trình làm **hai tầng kiểm tra**:

1. `candidate instanceof List<?> elements` xác nhận đây là một danh sách.
2. `element instanceof Integer number` kiểm tra từng phần tử trước khi dùng kiểu `Integer`.

Đây không phải “pattern tự động soi kiểu phần tử của `List<Integer>`”; đó là **kiểm tra phần tử bằng một pattern thứ hai**.

Ví dụ `List.of(1, "skip", 2, 3L, 4)` cho kết quả `7`, vì chỉ `Integer` 1, 2 và 4 được cộng; `String` và `Long` không khớp `Integer`.

### Khi cần danh sách `List<String>` thật sự

Một cách an toàn là **kiểm tra từng phần tử rồi tạo danh sách mới có kiểu tĩnh cụ thể**, thay vì ép kiểu mù:

```java
static java.util.List<String> requireStrings(Object candidate) {
    if (!(candidate instanceof java.util.List<?> values)) {
        throw new IllegalArgumentException("Expected List");
    }

    java.util.ArrayList<String> result = new java.util.ArrayList<>();
    for (Object value : values) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(
                    "Expected String element, got " + value);
        }
        result.add(text);
    }
    return java.util.List.copyOf(result);
}
```

Đây là **phương thức minh họa**, có thể đặt trong một class Java hợp lệ. Phương thức cố ý từ chối `null` vì `null instanceof String text` là false. Kết quả `List.copyOf` không cho phép thêm phần tử và tách biệt với danh sách nguồn.

Việc tạo bản sao sau kiểm tra có ưu điểm là dữ liệu kết quả thật sự thỏa mãn kiểu phần tử đã cam kết, không phụ thuộc những thay đổi về sau của danh sách đầu vào.

## 7. Dùng wildcard với pattern `switch` trong Java 21

**Pattern matching for `switch`** là tính năng chính thức của Java 21. Bạn có thể đặt type pattern dùng wildcard ở nhánh `case`:

```java
static String category(Object candidate) {
    return switch (candidate) {
        case null -> "null";
        case java.util.List<?> list -> "list: " + list.size();
        case java.util.Map<?, ?> map -> "map: " + map.size();
        default -> "other";
    };
}
```

`case List<?> list` kiểm tra kiểu container; `case Map<?, ?> map` kiểm tra một loại container khác. Pattern variable `list` hoặc `map` chỉ có scope ở nhánh tương ứng.

### 7.1. Guard `when` với `List<?>`

Nếu cần phân biệt danh sách rỗng và danh sách có phần tử:

```java
return switch (candidate) {
    case null -> "null";
    case java.util.List<?> values when values.isEmpty() -> "empty list";
    case java.util.List<?> values -> "list size=" + values.size();
    default -> "other";
};
```

Nhánh có `when` được xét sau khi type pattern `List<?> values` khớp. `when` là **guard** của nhãn `case`, không phải một loại wildcard pattern riêng.

Đặt nhánh cụ thể có guard **trước** nhánh tổng quát. Nếu viết `case List<?> values ->` không có guard lên đầu, nó sẽ bao phủ các danh sách và làm nhánh dành cho danh sách rỗng sau đó không thể được chọn (vướng quy tắc **dominance**).

### 7.2. Tránh nhầm wildcard với kiểm tra kiểu phần tử

Đoạn này không phải phép chia nhánh theo `List<String>` và `List<Integer>`:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH, nguồn là Object
switch (candidate) {
    case java.util.List<String> strings -> System.out.println("strings");
    case java.util.List<Integer> ints -> System.out.println("ints");
    default -> {}
}
```

Khi nguồn là `Object`, JVM không có thông tin generic để phân biệt hai danh sách theo tham số kiểu. Hãy dùng `case List<?> values` rồi kiểm tra từng phần tử, hoặc dùng mô hình domain có kiểu runtime phân biệt rõ ràng (ví dụ record `StringItems` và `NumberItems`).

### 7.3. `null` và quy tắc exhaustiveness

`case List<?> values` không khớp `null`. Nếu `switch` có thể nhận `null`, hãy xử lý rõ bằng `case null` hoặc kiểm tra trước. `default` không nên được coi là nhánh đảm bảo nhận `null`; trong pattern `switch` Java 21, khi thiếu nhãn `null` phù hợp, `null` thường dẫn đến `NullPointerException`.

Một `switch` expression cần các nhánh bao phủ những giá trị có thể xảy ra. `default` trong ví dụ trên làm biểu thức đầy đủ cho các giá trị khác.

## 8. Phân biệt unbounded và bounded wildcards

Có ba cú pháp cơ bản của generic wildcard:

| Cú pháp | Ý nghĩa ở mức kiểu | Cách sử dụng điển hình |
| --- | --- | --- |
| `List<?>` | Kiểu phần tử chưa biết | Xem/đếm/duyệt; kiểm tra container bằng pattern |
| `List<? extends Number>` | Một kiểu chưa biết nhưng là subtype của `Number` | **Đọc** phần tử như `Number` |
| `List<? super Integer>` | Một kiểu chưa biết là `Integer` hoặc supertype của nó | Có thể **thêm `Integer`**, đọc ra dưới dạng `Object` |

Ví dụ các khai báo **hợp lệ**:

```java
java.util.List<? extends Number> measured =
        java.util.List.of(10, 20.5);
Number first = measured.get(0);

// ArrayList<Number> có thể làm đích cho wildcard lower bound:
java.util.List<? super Integer> sink =
        new java.util.ArrayList<Number>();
sink.add(42);
Object stored = sink.get(0);
```

Đây là quy tắc thường ghi nhớ bằng **PECS: Producer Extends, Consumer Super**. Với `? extends Number`, ta đọc được `Number` nhưng không thể tùy ý thêm `Number` vì danh sách thực tế có thể là `List<Integer>`. Với `? super Integer`, có thể thêm `Integer`, nhưng khi đọc không biết kiểu cụ thể hơn `Object`.

**Quan trọng:** các kiểu `List<? extends Number>` và `List<? super Integer>` dùng được trong **khai báo biến, tham số và kiểu trả về**, nhưng chúng **không reifiable**. Vì vậy không thể mặc định dùng chúng ở type pattern từ một nguồn `Object`.

Ví dụ sai:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH, candidate có kiểu Object
if (candidate instanceof java.util.List<? extends Number> nums) {
    // ...
}
```

Sửa bằng cách nhận diện container ở runtime, rồi kiểm tra nội dung:

```java
if (candidate instanceof java.util.List<?> elements) {
    for (Object element : elements) {
        if (element instanceof Number number) {
            System.out.println(number.doubleValue());
        }
    }
}
```

Cách sửa này **chỉ xử lý những phần tử khớp `Number`**, không chứng minh mọi phần tử của danh sách là `Number`. Nếu nghiệp vụ yêu cầu *tất cả* phần tử đều là số, phải kiểm tra và xử lý trường hợp không khớp (ví dụ ném lỗi hoặc từ chối toàn bộ danh sách).

## 9. Generic record và pattern với wildcard

Trong Java 21, record cũng có thể nhận type parameter:

```java
record Box<T>(T value) {}
```

Khi dữ liệu ban đầu có kiểu `Object`, dùng wildcard ở **type pattern** để nhận diện một `Box` bất kể tham số kiểu:

```java
static String boxKind(Object candidate) {
    if (candidate instanceof Box<?> box) {
        Object value = box.value();
        return value == null ? "empty box" : value.getClass().getSimpleName();
    }
    return "not a box";
}
```

`Box<?> box` là type pattern. Nó xác nhận đối tượng là một instance của record `Box`, **không** xác nhận `T` là `String`, `Integer` hay kiểu nào khác. `box.value()` có thể đọc như `Object`; nếu cần xử lý kiểu cụ thể, tiếp tục kiểm tra bằng `instanceof`:

```java
if (candidate instanceof Box<?> box
        && box.value() instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Cả hai pattern variable `box` và `text` chỉ dùng trong đường đi mà biểu thức `&&` chứng minh match. Đây là cách giữ **type safety** mà không dùng raw `Box` hay cast `Box<String>` không được kiểm chứng.

### 9.1. Wildcard trong record pattern

Bạn cũng có thể dùng wildcard trong **kiểu record** của một record pattern:

```java
if (candidate instanceof Box<?>(var item)) {
    System.out.println(item);
}
```

Ở đây:

- `Box<?>(var item)` là một **record pattern**, vì có danh sách component `(...)`.
- `Box<?>` là kiểu generic dùng unbounded wildcard, phù hợp để kiểm tra từ `Object`.
- `var item` là component type pattern có kiểu được suy luận từ component của `Box<?> `; khi chưa biết `T`, hãy xử lý `item` như một giá trị có thể xem dưới dạng `Object`.
- Dòng này **không** đòi hỏi `item` phải là `String`. Nếu cần một `String`, kiểm tra tiếp `item instanceof String text`.

Với giá trị có **kiểu tĩnh cụ thể** như `Box<String>`, Java 21 có thể suy luận type argument khi dùng record pattern `Box(var text)`, và biến `text` có kiểu `String`. Đây là **suy luận từ kiểu tĩnh**, không phải JVM khôi phục lại tham số generic đã bị xóa khỏi một `Object`.

### 9.2. Kiểu generic cụ thể trong record pattern: giới hạn

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH VỚI NGUỒN Object
if (candidate instanceof Box<String>(String text)) {
    // ...
}
```

Với `candidate` có kiểu tĩnh `Object`, compiler không thể xác minh chuyển kiểu `Object` → `Box<String>` một cách checked, nên ví dụ trên lỗi. Nhưng nếu đầu vào đã có kiểu tĩnh `Box<String>`, pattern `Box<String>(String text)` có thể hợp lệ và dùng được (theo điều kiện checked cast của record patterns).

Đừng nhầm **generic record pattern** với **type pattern**. `Box<?> box` liên kết cả đối tượng; `Box<?>(var item)` giải cấu trúc component và liên kết riêng `item`.

## 10. Wildcard capture: tại sao không thể tự gán kiểu cụ thể?

`List<?>` có một kiểu phần tử **không biết nhưng nhất quán với danh sách đó**. Compiler có thể tạo một tên kiểu nội bộ để biểu diễn nó (*capture conversion*), thường thấy trong thông báo lỗi dạng `CAP#1`.

Ví dụ:

```java
static void inspect(java.util.List<?> values) {
    Object first = values.get(0);
    // String s = values.get(0); // LỖI: không bảo đảm phần tử là String
}
```

Nếu bạn thực sự cần làm việc với kiểu phần tử được bảo toàn, có thể dùng **generic helper method**. Điều đó giúp compiler giữ mối liên hệ giữa các giá trị, nhưng **không thêm khả năng kiểm tra type argument tại runtime**.

Ví dụ method chỉ **đếm** danh sách không cần biết kiểu phần tử:

```java
static int count(java.util.List<?> values) {
    return values.size();
}
```

Còn method muốn chọn một phần tử rồi thao tác theo kiểu thật cần một trong hai cách:

1. Đặt API có type parameter cụ thể: `<T> T first(List<T> values)` khi caller biết `T`.
2. Nếu đầu vào là `Object` hoặc `List<?>`, dùng pattern trên từng phần tử: `if (value instanceof String text)`, `if (value instanceof Integer number)`...

Đừng sửa lỗi bằng cách ép kiểu không kiểm chứng:

```java
// DỄ GẶP ClassCastException HOẶC LỖI VỀ SAU
java.util.List<String> strings =
        (java.util.List<String>) candidate;
```

Cast có thể sinh cảnh báo `unchecked` khi không chứng minh được type argument; runtime không tự kiểm tra mọi phần tử. Một danh sách thực sự chứa `Integer` có thể vượt qua cast container rồi mới gây lỗi khi mã sau đọc như `String`.

## 11. Phân biệt `?` với các ký hiệu có vẻ giống wildcard

| Cú pháp | Có phải “wildcard pattern” trong Java 21? | Diễn giải |
| --- | --- | --- |
| `List<?> list` | Không phải loại pattern riêng | **Type pattern** có generic unbounded wildcard |
| `Map<?, ?> map` | Không phải loại pattern riêng | **Type pattern** có hai generic wildcard |
| `Box<?>(var item)` | Không phải loại pattern riêng | **Record pattern** với kiểu generic có wildcard |
| `case _ -> ...` | Không phải cú pháp wildcard tổng quát hợp lệ của Java 21 | Không dùng `_` như nhãn `case` tự do trong Java 21 |
| `Point(var x, _)` | **Unnamed pattern** (preview trong Java 21) | Bỏ qua component của record; cú pháp `_` riêng, không liên quan `?` |
| `case String _ -> ...` | Type pattern với **unnamed pattern variable** (preview Java 21) | Cần bật preview trong Java 21 |
| `java.util.regex.Pattern` | Không | API regular expression, không thuộc ngữ pháp pattern matching này |

Trong bài Java 21 bình thường, nên dùng `List<?> list` và kiểm tra phần tử bằng các **type pattern chính thức**. Không cần `--enable-preview` cho wildcard generics, type pattern, record pattern hoặc pattern matching for `switch`.

Dấu `_` của **unnamed patterns and variables** là tính năng preview theo JEP 443 ở Java 21, và trở thành chính thức ở Java 22 theo JEP 456. Không áp dụng trạng thái Java 22 ngược lại cho Java 21.

## 12. Ví dụ Java 21 hoàn chỉnh: kiểm tra container rồi phân loại nội dung

Lưu chương trình sau thành tệp **`WildcardPatternDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class WildcardPatternDemo {
    record Box<T>(T value) {}

    static String describeElement(Object element) {
        return switch (element) {
            case null -> "null";
            case String text -> "String:" + text;
            case Integer number -> "Integer:" + number;
            default -> "other";
        };
    }

    static String describe(Object candidate) {
        return switch (candidate) {
            case null -> "null";
            case List<?> list when list.isEmpty() -> "empty list";
            case List<?> list ->
                    "list(size=" + list.size() + ", first="
                    + describeElement(list.get(0)) + ")";
            case Map<?, ?> map -> "map(size=" + map.size() + ")";
            case Box<?> box ->
                    "box(" + describeElement(box.value()) + ")";
            default -> "other";
        };
    }

    static int sumIntegers(List<?> values) {
        int total = 0;
        for (Object value : values) {
            if (value instanceof Integer number) {
                total += number;
            }
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of()));
        System.out.println(describe(List.of("A", "B")));
        System.out.println(describe(List.of(7, 8)));
        System.out.println(describe(Map.of("code", 10)));
        System.out.println(describe(new Box<>("ready")));
        System.out.println(describe(new Box<>(42)));
        System.out.println(describe(null));
        System.out.println(describe("plain"));
        System.out.println(
                sumIntegers(List.of(1, "skip", 2, 3L, 4)));
    }
}
```

Dùng **JDK 21**:

```bash
javac --release 21 WildcardPatternDemo.java
java WildcardPatternDemo
```

Kết quả stdout:

```text
empty list
list(size=2, first=String:A)
list(size=2, first=Integer:7)
map(size=1)
box(String:ready)
box(Integer:42)
null
other
7
```

Phân tích:

- `List.of()` khớp nhánh `List<?> list when list.isEmpty()`.
- `List.of("A", "B")` và `List.of(7, 8)` đều khớp nhánh **`List<?>`**, rồi phần tử đầu mới được phân loại bằng `String text` hoặc `Integer number`.
- `Map.of("code", 10)` khớp `Map<?, ?>` mà không cần biết key/value generic.
- `new Box<>("ready")` và `new Box<>(42)` đều khớp `Box<?> box`; hàm `describeElement` kiểm tra giá trị bên trong.
- `null` có nhánh riêng; `"plain"` không phải container trong các nhánh trước nên đi vào `default`.
- Hàm `sumIntegers` chỉ cộng các phần tử thật sự là `Integer`, tránh ép `List<Integer>` sai cách.

Trong chương trình này, tất cả tính năng pattern dùng đều **chính thức trên Java 21**. Không có preview, raw generic cast hoặc unchecked conversion.

## 13. Lỗi thường gặp và cách xử lý

### Lỗi A: Tưởng `List<?> list` xác minh kiểu của mọi phần tử

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (candidate instanceof java.util.List<?> list) {
    String first = list.get(0); // Không bảo đảm là String
}
```

**Sửa:** nhận `Object first`, dùng `if (first instanceof String text)` hoặc `switch` theo kiểu thực tế của từng phần tử.

### Lỗi B: Thay `?` bằng `String` trong pattern nhận `Object`

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (candidate instanceof java.util.List<String> strings) {
    // ...
}
```

**Sửa:** dùng `List<?> values` rồi kiểm tra nội dung, hoặc thay đổi API đầu vào để mang kiểu tĩnh đủ cụ thể. Không suppress unchecked warning để “cưỡng ép” runtime hiểu generic.

### Lỗi C: Dùng bounded wildcard vì tưởng `extends` giúp kiểm tra sâu

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH từ Object
if (candidate instanceof java.util.List<? extends Number> numbers) {
    // ...
}
```

**Sửa:** `List<?> values` + kiểm tra từng phần tử bằng `instanceof Number number`; nếu muốn bảo đảm danh sách chỉ có số, kiểm tra **tất cả** phần tử và tạo bản sao có kiểu đúng.

### Lỗi D: Gán giá trị mới vào `List<?>`

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
if (candidate instanceof java.util.List<?> list) {
    list.add("new"); // Compiler không biết T của list
}
```

**Sửa:** nếu cần ghi, thiết kế đầu ra có kiểu cụ thể và tạo một danh sách mới. Đừng coi raw type là cách sửa an toàn.

### Lỗi E: Hai nhánh cùng pattern `List<?>` nhưng đặt nhánh rộng trước

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH do nhánh sau bị dominated
switch (candidate) {
    case java.util.List<?> list -> System.out.println(list.size());
    case java.util.List<?> list when list.isEmpty() ->
            System.out.println("empty");
    default -> {}
}
```

**Sửa:** đặt nhánh `when list.isEmpty()` trước, rồi nhánh `List<?> list` tổng quát phía sau.

### Lỗi F: Quên `null` khi dùng pattern `switch`

Một `case List<?> list` không khớp `null`. **Sửa:** thêm `case null` khi đầu vào có thể thiếu, hoặc kiểm tra `null` trước khi `switch`. Đừng suy luận `default` là nhánh luôn bắt `null`.

### Lỗi G: Lẫn wildcard `?` với unnamed pattern `_`

`List<?> list` hoạt động trên Java 21 tiêu chuẩn; `Box(var x, _)` là cú pháp khác thuộc preview của Java 21. **Sửa:** đọc dấu `?` như đối số kiểu generic, đọc dấu `_` theo quy tắc unnamed pattern/variable của đúng phiên bản JDK.

## 14. Bài tập đọc mã và đáp án

**Bài 1.** Đoạn sau khớp những danh sách nào?

```java
if (candidate instanceof java.util.List<?> list) {
    System.out.println(list.size());
}
```

**Đáp án:** Mọi đối tượng runtime triển khai `List` phù hợp với phép cast, bất kể tham số generic là `String`, `Integer` hoặc kiểu khác; `null` không khớp. Nó không chứng minh phần tử có kiểu cụ thể.

**Bài 2.** Vì sao `Map<?, ?>` dùng được mà `Map<String, ?>` từ `Object` không được?

**Đáp án:** `Map<?, ?>` có **toàn bộ** đối số kiểu là wildcard không giới hạn, nên reifiable. `Map<String, ?>` chứa đối số `String` cụ thể, không reifiable; kiểm tra từ `Object` đòi hỏi unchecked conversion.

**Bài 3.** `List<? extends Number>` có thể dùng ở đâu?

**Đáp án:** Có thể dùng ở khai báo biến, tham số phương thức hoặc kiểu trả về để chỉ danh sách sản xuất `Number`; không dùng làm kiểm tra type pattern tùy ý từ một `Object`. Sau `List<?> list`, muốn xử lý Number phải kiểm tra từng phần tử.

**Bài 4.** Trong `record Box<T>(T value) {}`, hai pattern sau khác nhau thế nào?

```java
obj instanceof Box<?> box
obj instanceof Box<?>(var content)
```

**Đáp án:** Dòng đầu là **type pattern** và liên kết cả đối tượng `box`. Dòng hai là **record pattern**, giải cấu trúc component và liên kết `content`. Cả hai dùng wildcard để diễn đạt kiểu generic chưa biết; không xác minh `T` bằng runtime.

**Bài 5.** `List<?> list` đã khớp, có thể gọi `list.add("x")` không?

**Đáp án:** Không. Compiler chưa biết kiểu phần tử thật sự của `list`; việc ghi `String` có thể phá vỡ invariant nếu danh sách là `List<Integer>`. Hãy tạo collection đầu ra có kiểu cụ thể hoặc thay đổi API để truyền kiểu đúng.

**Bài 6.** Mã có `switch (obj)` với `case List<?> list ->` phía trước `case List<?> list when list.isEmpty() ->`. Có ổn không?

**Đáp án:** Không. Nhánh đầu bao phủ cả danh sách rỗng, nên nhánh thứ hai bị **dominated**. Chuyển nhánh có guard lên trước.

## 15. Checklist khi review pattern có wildcard

- [ ] Đã xác định rõ `?` là **generic wildcard type argument**, không phải pattern kiểm tra từng phần tử.
- [ ] Khi nguồn là `Object`, dùng reifiable type như `List<?>`, `Map<?, ?>`, `Box<?>` để nhận diện container.
- [ ] Không viết `List<String>`, `List<? extends Number>` hoặc `Map<String, ?>` như phép kiểm tra toàn bộ kiểu generic của một `Object`.
- [ ] Nếu dùng kiểu generic cụ thể ở pattern, đã xác minh **kiểu tĩnh nguồn** cho phép checked cast.
- [ ] Sau khi khớp `List<?>`, đọc phần tử như `Object`, chỉ dùng thuộc tính kiểu cụ thể sau khi kiểm tra riêng.
- [ ] Nếu nghiệp vụ cần danh sách đồng nhất, đã kiểm tra từng phần tử và xử lý `null`/phần tử không hợp lệ.
- [ ] Không thêm phần tử không-null vào `List<?>` hoặc ép raw type để né kiểm tra.
- [ ] Với `switch`, xét thứ tự guard, dominance, exhaustiveness và `null`.
- [ ] Với generic record, phân biệt type pattern `Box<?> box` và record pattern `Box<?>(var item)`.
- [ ] Không nhầm dấu `?` chuẩn của generics với dấu `_` thuộc preview Java 21.

## 16. Tài liệu chuẩn

- [Java Language Specification 21 §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7): định nghĩa reifiability; các kiểu generic chỉ gồm unbounded wildcard là reifiable.
- [Java Language Specification 21 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5): checked/unchecked cast, nền tảng xác định pattern có hợp lệ.
- [Java Language Specification 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record pattern, tính áp dụng và khớp runtime.
- [Java Language Specification 21 §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): điều kiện kiểm tra kiểu.
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ví dụ record generic và suy luận type argument.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): pattern variable và các điều kiện chuyển kiểu an toàn.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440) và [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): cú pháp chính thức trong Java 21.
- [JEP 443 — Unnamed Patterns and Variables (Preview)](https://openjdk.org/jeps/443): dấu `_` là tính năng preview trong Java 21, khác với generic wildcard `?`.
