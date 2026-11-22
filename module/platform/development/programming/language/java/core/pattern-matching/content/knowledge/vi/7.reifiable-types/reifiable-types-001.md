# Pattern matching với generic type trong Java

## 1. Mục tiêu: kiểm tra kiểu khi generic đã bị xóa một phần

Java kết hợp **generics** và **pattern matching** để viết phép kiểm tra kiểu gọn, nhưng cần phân biệt hai lớp thông tin:

- **Compile time (thời điểm biên dịch):** trình biên dịch biết `List<String>`, `List<Integer>`, `Map<String, Integer>` và kiểm tra các thao tác theo đối số kiểu.
- **Runtime (thời điểm chạy):** do cơ chế **type erasure**, JVM thường biết đối tượng là một lớp như `ArrayList` hoặc `HashMap`, chứ không lưu một danh sách đối số kiểu dùng để kiểm tra từng `String` hay `Integer`.

Ví dụ:

```java
List<String> names = new ArrayList<>();
List<Integer> scores = new ArrayList<>();
```

Hai biến đều có thể trỏ tới đối tượng có lớp runtime là `java.util.ArrayList`. Sự khác biệt `String` và `Integer` vẫn có ý nghĩa lớn đối với kiểm tra kiểu *lúc biên dịch*, nhưng một phép thử `instanceof` thông thường không thể xác nhận rằng mọi phần tử trong một collection là `String`.

**Pattern matching với generic type** thường giải quyết hai việc:

1. Kiểm tra kiểu thực tế của đối tượng, chẳng hạn `List<?>`, và khai báo **pattern variable** để sử dụng API `List` an toàn.
2. Tận dụng thông tin generic **đã được xác định ở kiểu tĩnh của biểu thức nguồn** để kiểm tra một kiểu triển khai cụ thể, chẳng hạn `List<String>` sang `ArrayList<String>` trong những trường hợp Java cho phép.

Hai trường hợp khác nhau. Không nên học thành quy tắc quá mức rằng “mọi generic đều bị cấm trong `instanceof`”, cũng không nên hiểu rằng `instanceof` có thể tự xác minh nội dung của `List<String>`.

Các ví dụ chính dùng **Java 17+**. Phần `switch` với type pattern yêu cầu **Java 21+**, khi pattern matching cho `switch` đã là tính năng chính thức.

## 2. `type erasure`: vì sao không kiểm tra được mọi đối số generic?

Generics của Java chủ yếu bảo vệ tính đúng kiểu khi biên dịch. Theo Java Language Specification (JLS), phép *erasure* biến một kiểu tham số hóa `G<T>` thành kiểu không mang đối số `G` ở mức biểu diễn đã xóa.

Ví dụ giả định có:

```java
Object input = java.util.List.of("a", "b");
```

Ta **không được** viết:

```java
// KHÔNG BIÊN DỊCH khi input có kiểu tĩnh Object:
if (input instanceof java.util.List<String> strings) {
    System.out.println(strings.get(0));
}
```

Một đối tượng `List` tại runtime không mang đủ chứng cứ để phép thử này bảo đảm nó là `List<String>`. Nếu cho phép suy đoán chỉ từ lớp runtime, chương trình có thể nhầm một `List<Integer>` thành `List<String>`.

Cách kiểm tra hợp lệ:

```java
if (input instanceof java.util.List<?> elements) {
    System.out.println(elements.size());
}
```

`List<?>` mang **unbounded wildcard** (`?`), nghĩa là chưa biết kiểu phần tử. Pattern variable `elements` có kiểu tĩnh `List<?>`, có thể gọi `size()`, `isEmpty()`, duyệt qua phần tử và đọc từng phần tử dưới kiểu `Object`; **không được tự coi chúng là `String`**.

Ví dụ đầy đủ về việc đọc một phần tử:

```java
Object input = java.util.List.of("Java", 42);
if (input instanceof java.util.List<?> elements) {
    for (Object element : elements) {
        if (element instanceof String text) {
            System.out.println("text=" + text.toUpperCase());
        } else if (element instanceof Integer number) {
            System.out.println("number=" + number);
        }
    }
}
```

Kết quả:

```text
text=JAVA
number=42
```

`instanceof List<?>` xác minh được **quan hệ kiểu của chính danh sách**; các phép thử `instanceof String text` hoặc `instanceof Integer number` sau đó mới xác minh **từng phần tử**.

## 3. Reifiable type và type pattern

Một kiểu gọi là **reifiable** nếu thông tin kiểu cần thiết vẫn đủ để xác định nó tại runtime. Theo JLS §4.7, các ví dụ điển hình gồm:

| Kiểu | Reifiable? | Ý nghĩa đối với pattern matching |
| --- | --- | --- |
| `String`, `Integer` | Có | Kiểu lớp thông thường có thể kiểm tra tại runtime |
| `List<?>` | Có | Có thể kiểm tra đối tượng là `List`, chưa biết kiểu phần tử |
| `Map<?, ?>` | Có | Có thể kiểm tra đối tượng là `Map`, chưa biết kiểu khóa/giá trị |
| `List` (raw type) | Có | Có thể kiểm tra lớp, nhưng mất lợi ích kiểm tra generic |
| `List<String>` | Không | Không thể xác minh đối số `String` chỉ bằng runtime class |
| `List<? extends Number>` | Không | Wildcard bị ràng buộc, không phải wildcard `?` không giới hạn |
| `String[]` | Có | Kiểu phần tử của mảng này có thể kiểm tra tại runtime |
| `List<?>[]` | Có | Mảng có kiểu phần tử reifiable |
| `List<String>[]` | Không | Thành phần generic không reifiable |

**Đừng suy ra “mọi kiểu ở vế phải của `instanceof` phải reifiable”.** Từ **Java 16**, Java đã nới quy tắc này cho một số phép kiểm tra tham số hóa khi **kiểu tĩnh của biểu thức nguồn cho phép chuyển kiểu an toàn**. Chi tiết ở mục 5.

Mặt khác, ví dụ `input instanceof List<?> elements` là lựa chọn trực tiếp khi `input` có kiểu tĩnh rộng như `Object`.

### `List<?>` không đồng nghĩa với `List<Object>`

Hai kiểu này khác nhau:

```java
java.util.List<String> words = java.util.List.of("A", "B");
java.util.List<?> unknown = words;   // Hợp lệ
// java.util.List<Object> objects = words; // LỖI: generic bất biến
```

`List<?>` biểu diễn một `List` có kiểu phần tử **chưa biết**, và chấp nhận `List<String>`, `List<Integer>`... ở vị trí đọc an toàn. `List<Object>` là một danh sách được khai báo với kiểu phần tử chính xác là `Object`. Generics của Java **invariant**: `List<String>` không phải subtype của `List<Object>`.

Trong `List<?>`, phần tử đọc ra có kiểu `Object`. Thông thường không thể thêm một phần tử không phải `null` vì không biết kiểu phần tử thực sự; việc gọi các phương thức không phụ thuộc kiểu phần tử, như `size()`, vẫn hợp lệ.

### Khi nào dùng `Map<?, ?>`?

Tương tự, khi nhận `Object input`:

```java
if (input instanceof java.util.Map<?, ?> entries) {
    for (java.util.Map.Entry<?, ?> entry : entries.entrySet()) {
        Object key = entry.getKey();
        Object value = entry.getValue();
        System.out.println(key + " => " + value);
    }
}
```

Biến `entries` là `Map<?, ?>`; các khóa và giá trị chưa có kiểu cụ thể hơn `Object` tại vị trí đọc. Nếu cần thao tác riêng của `String` hoặc `Number`, dùng type pattern cho giá trị từng phần.

## 4. Pattern variable và flow scoping khi gặp generic

Cú pháp Java 17:

```java
if (input instanceof java.util.List<?> items) {
    System.out.println(items.size());
}
```

`items` là **pattern variable**. Nó chỉ sẵn có tại những nơi trình biên dịch chứng minh `List<?>` đã khớp (*definitely matched*).

Ví dụ ngắn:

```java
static int sizeOrMinusOne(Object input) {
    if (!(input instanceof java.util.List<?> items)) {
        return -1;
    }
    return items.size(); // Hợp lệ vì nhánh không khớp đã return.
}
```

Trong thân của `if` phủ định, `items` chưa được khởi tạo; bên dưới `if`, nó đã khớp trên mọi đường chạy còn lại. Có thể viết điều kiện bổ sung với `&&`:

```java
if (input instanceof java.util.List<?> items && !items.isEmpty()) {
    Object first = items.get(0);
    System.out.println(first);
}
```

`items.get(0)` chỉ được gọi sau khi mẫu khớp và `items` không rỗng. Ngược lại, mã sau là **lỗi biên dịch** vì `||` có thể đánh giá vế phải khi mẫu không khớp:

```java
// KHÔNG BIÊN DỊCH:
if (input instanceof java.util.List<?> items || items.isEmpty()) {
    System.out.println("...");
}
```

Flow scoping của pattern variable kiểu generic hoạt động theo **cùng nguyên tắc** với `String text`: Java kiểm tra đã khớp và đã khởi tạo biến hay chưa, không yêu cầu biến ấy là kiểu không generic.

## 5. Ngoại lệ quan trọng từ Java 16: refinement của generic đã biết tĩnh

Một số kiểu có đối số generic **cụ thể** vẫn dùng được trong phép thử `instanceof` hoặc type pattern, nếu kiểu tĩnh của biểu thức nguồn giúp chứng minh phép chuyển kiểu là an toàn theo JLS.

Ví dụ:

```java
java.util.List<String> words = new java.util.ArrayList<>();
if (words instanceof java.util.ArrayList<String> arrayList) {
    arrayList.add("hello");
    System.out.println(arrayList.size()); // 1
}
```

Đây là **cú pháp hợp lệ từ Java 16**, kể cả khi `ArrayList<String>` không phải reifiable type. Điểm quan trọng:

- Biến nguồn `words` **đã được khai báo là `List<String>`**, nên compiler có bằng chứng tĩnh rằng phần tử của danh sách có kiểu `String` theo hợp đồng generic.
- Phép kiểm tra lúc chạy chỉ cần xác minh đối tượng có thuộc lớp triển khai `ArrayList` hay không. Phần `<String>` được duy trì qua **phép chuyển kiểu hợp lệ** từ `List<String>` sang `ArrayList<String>`; không có phép “đọc” generic type argument từ JVM.
- Pattern variable `arrayList` có kiểu `ArrayList<String>`, nên sau khi khớp có thể gọi `add("hello")` hoặc `get(0)` dưới kiểm tra kiểu Java thông thường.

Hai ví dụ **không hợp lệ**:

```java
java.util.List<String> words = new java.util.ArrayList<>();

// Không có chuyển kiểu hợp lệ sang ArrayList<Integer>:
// if (words instanceof java.util.ArrayList<Integer> nums) { }

// Không thể chuyển đối tượng từ Object sang ArrayList<String> có kiểm tra đầy đủ:
// Object unknown = words;
// if (unknown instanceof java.util.ArrayList<String> strings) { }
```

Như vậy, điều kiện đúng **không phải** là “tại runtime có metadata `<String>`”. Điều kiện đúng là **Java có thể kiểm tra lớp runtime kết hợp với bằng chứng generic tĩnh đã biết, mà không cần một phép chuyển kiểu unchecked**.

Lưu ý: nếu dữ liệu bị **heap pollution** vì raw type, unchecked cast hoặc thư viện cũ, bằng chứng generic tĩnh có thể phản ánh lời hứa sai từ upstream. Pattern matching không thể tự sửa vấn đề đó.

## 6. Ví dụ Java 17+ hoàn chỉnh

Lưu thành file **`GenericPatternDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class GenericPatternDemo {
    static String summary(Object value) {
        if (value instanceof List<?> list) {
            int nonblankStrings = 0;
            for (Object item : list) {
                if (item instanceof String text && !text.isBlank()) {
                    nonblankStrings++;
                }
            }
            return "List(size=" + list.size()
                    + ", nonblankStrings=" + nonblankStrings + ")";
        }
        if (value instanceof Map<?, ?> map) {
            return "Map(size=" + map.size() + ")";
        }
        return value == null ? "null" : "other";
    }

    static String refinedType(List<String> words) {
        if (words instanceof ArrayList<String> concrete) {
            return "ArrayList first="
                    + (concrete.isEmpty() ? "(empty)" : concrete.get(0));
        }
        return "Other List";
    }

    public static void main(String[] args) {
        Object mixed = List.of("Java", 7, " ", "hello");
        System.out.println(summary(mixed));
        System.out.println(summary(Map.of("id", 2)));
        System.out.println(summary(null));

        List<String> words = new ArrayList<>(List.of("A", "B"));
        System.out.println(refinedType(words));
        System.out.println(summary(99));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**, không cần preview:

```bash
javac GenericPatternDemo.java
java GenericPatternDemo
```

Kết quả dự kiến chính xác:

```text
List(size=4, nonblankStrings=2)
Map(size=1)
null
ArrayList first=A
other
```

**Tại sao ra kết quả đó?**

1. `mixed` là một `List` chứa chuỗi `"Java"`, số `7`, chuỗi chỉ có dấu cách `" "`, và chuỗi `"hello"`. `List<?> list` khớp; vòng lặp đếm **hai** chuỗi không trắng (`"Java"` và `"hello"`), tổng cộng bốn phần tử.
2. `Map.of("id", 2)` khớp `Map<?, ?> map`, có một entry nên in `Map(size=1)`.
3. `null` không khớp type pattern tham chiếu nào, nên đi đến `return "null"`.
4. `words` có kiểu tĩnh `List<String>` và đối tượng runtime là `ArrayList`; pattern `ArrayList<String> concrete` hợp lệ nhờ kiểu tĩnh đã biết. `get(0)` trả `"A"`.
5. `99` là một `Integer`, không khớp `List<?>` hay `Map<?, ?>` nên in `other`.

Lưu ý `List.of(...)` tạo danh sách không hỗ trợ thêm/xóa, nhưng ví dụ không thay đổi `mixed`. Ngược lại, `words` được tạo bằng `new ArrayList<>(...)`, nên chỉ đoạn refine mới dùng API cụ thể của `ArrayList` khi cần.

## 7. Pattern matching cho generic trong `switch` (Java 21+)

Từ **Java 21**, có thể dùng type pattern với `switch`:

```java
case List<?> items -> ...
```

Một `case List<?> items` khớp đối tượng có kiểu runtime triển khai `List`; `items` là biến pattern dùng được trong phần thân của **chính case đó**, và trong guard `when` nếu có. Các nguyên tắc erasure và reifiability đã trình bày vẫn áp dụng.

Ví dụ độc lập, lưu file **`GenericSwitchDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class GenericSwitchDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case List<?> items when items.isEmpty() -> "empty list";
            case List<?> items -> "list of " + items.size();
            case Map<?, ?> entries -> "map of " + entries.size();
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(List.of()));
        System.out.println(classify(List.of(1, "two")));
        System.out.println(classify(Map.of("a", 10)));
        System.out.println(classify(null));
        System.out.println(classify("text"));
    }
}
```

Chạy bằng **JDK 21 trở lên**:

```bash
javac GenericSwitchDemo.java
java GenericSwitchDemo
```

Đầu ra:

```text
empty list
list of 2
map of 1
null
other
```

Giải thích:

- Guard `when items.isEmpty()` chỉ được đánh giá **sau khi** `List<?> items` khớp, nên có thể gọi `items.isEmpty()`.
- Rule `case List<?> items` không guard xử lý các `List` còn lại. Đặt rule có guard trước để không bị rule rộng hơn *dominate*.
- Hai nhãn khai báo `items` độc lập; mỗi pattern variable chỉ thuộc nhánh tương ứng, không bị “mượn” từ nhánh trước.
- `case Map<?, ?> entries` làm việc tương tự với `Map`.
- `case null` xử lý riêng `null`; không giả định `default` bắt `null`.

Không dùng mã `switch` này như ví dụ chạy mặc định bằng Java 17: pattern matching cho `switch` lúc đó chưa phải tính năng chính thức. Dùng `if (value instanceof List<?> items)` nếu dự án đặt baseline ở JDK 17.

### Có thể viết `case List<String> strings` không?

Nếu selector là `Object` như trong ví dụ, **không** thể dùng `case List<String> strings` để khẳng định mọi phần tử là `String`. Kiểu runtime của `List` không giữ đầy đủ đối số generic ấy. Sử dụng `List<?>`, rồi kiểm tra từng phần tử khi cần.

## 8. Generic record và nested pattern: nhận diện đúng ranh giới

Java 21 còn hỗ trợ **record patterns**. Với một record generic:

```java
record Box<T>(T item) {}
```

Nếu đầu vào có kiểu `Object`, có thể dùng:

```java
Object value = new Box<>("Java");
if (value instanceof Box<?> box) {
    Object item = box.item(); // Chưa được suy ra là String.
    if (item instanceof String text) {
        System.out.println(text.toUpperCase()); // JAVA
    }
}
```

`Box<?>` xác minh đối tượng là một `Box` mà chưa biết đối số `T`. Ta vẫn phải kiểm tra `item` riêng nếu muốn dùng API của `String`.

Một **record pattern lồng nhau** có thể kết hợp kiểm tra record và thành phần, nhưng đó là một phép khớp **cấu trúc** trên thành phần, không có nghĩa JVM lưu `T=String` như metadata có thể kiểm chứng mọi lúc. Tránh diễn giải việc khớp thành phần là một phép xác thực vô điều kiện cho toàn bộ container generic.

Mã `record Box<T>(T item) {}` dùng được từ Java 17; record patterns lồng nhau là nội dung riêng của Java 21+. Ở đây mục tiêu là hiểu ranh giới generic: kiểm tra **container** và kiểm tra **value bên trong** là hai việc độc lập.

## 9. Kiểu raw, unchecked cast và lỗi runtime

Ví dụ dưới đây **minh họa mã không an toàn**, không nên dùng trong mã mới:

```java
java.util.List raw = new java.util.ArrayList();
raw.add(123); // Raw type bỏ qua kiểm tra generic khi thêm.

java.util.List<String> texts = raw; // Cảnh báo unchecked.
String first = texts.get(0);        // ClassCastException lúc chạy.
```

`texts` được khai báo `List<String>` nhưng dữ liệu thực tế bên trong là `Integer`. Do raw type/unchecked conversion, lời hứa kiểu ở compile time đã bị phá vỡ. Một phép `instanceof List<?>` hay refinement hợp lệ sang `ArrayList<String>` **không quét và xác thực lại nội dung** của danh sách.

Các cách xử lý an toàn hơn:

- Nhận `Object`/`List<?>` tại biên dữ liệu; kiểm tra từng phần tử bằng `instanceof String s` trước khi dùng.
- Đưa dữ liệu đã kiểm tra vào `List<String>` mới, chỉ thêm các phần tử đã xác minh đúng kiểu.
- Ưu tiên API được khai báo generic đầy đủ; tránh raw type và unchecked cast trừ khi tích hợp legacy có kiểm soát.
- Nếu cần xác thực cấu trúc nhiều tầng, ví dụ `List<Map<String, Integer>>`, phải kiểm tra từng cấp và từng phần tử; `instanceof` một lần không thể xác thực toàn bộ cấu trúc.

## 10. Generic type parameter và `Class<T>`: hai công cụ khác nhau

Trong một phương thức generic:

```java
static <T> boolean isExpected(Object value, Class<T> type) {
    return type.isInstance(value);
}
```

`Class<T>.isInstance(value)` dùng **class token** (`String.class`, `Integer.class`, `Number.class`) để kiểm tra một lớp ở runtime; `Class<T>.cast(value)` có thể thực hiện cast đã được kiểm tra theo class token. Ví dụ:

```java
boolean ok = isExpected("Java", String.class); // true
boolean no = isExpected(42, String.class);     // false
```

Tuy nhiên, `Class<List<String>>` không có class literal `List<String>.class`: đối số generic không được biểu diễn thành một class token tương đương. Chỉ có `List.class` cho lớp/interface đã bị xóa đối số kiểu. Vì vậy `Class<T>` hữu ích để kiểm tra **lớp runtime**, nhưng bản thân nó cũng không xác minh được kiểu của mọi phần tử generic lồng nhau.

Trong cùng ngữ cảnh, không thể kỳ vọng viết `value instanceof T` với một type parameter `T` của phương thức rồi kiểm tra được `T` tại runtime như `String.class`; kiểu `T` thường bị xóa theo bound. Khi cần kiểm tra kiểu động, truyền `Class<T>` đối với kiểu reifiable phù hợp hoặc một bộ xác thực cấu trúc được định nghĩa riêng.

## 11. Những lỗi cần tránh

1. **Cho rằng `instanceof List<?> list` chứng minh `List<String>`.** Nó chỉ xác minh đối tượng là `List`; mỗi phần tử vẫn có thể thuộc kiểu khác.
2. **Viết `Object x; if (x instanceof List<String> s)`.** Phép kiểm tra từ `Object` sang kiểu generic cụ thể không đủ bảo đảm và bị compiler từ chối.
3. **Tuyên bố mọi kiểu generic đều bị cấm.** Java 16+ chấp nhận một số refinement từ kiểu tĩnh đã biết, như `List<String>` sang `ArrayList<String>` khi conversion hợp lệ.
4. **Nhầm `List<?>` với `List<Object>`.** Generic bất biến; `List<String>` không tự chuyển thành `List<Object>`.
5. **Gọi phương thức riêng của `String` trên một phần tử lấy từ `List<?>` mà không kiểm tra.** Phần tử có kiểu tĩnh `Object`; dùng `instanceof String text` khi cần.
6. **Tưởng rằng `? extends Number` là reifiable.** `List<? extends Number>` không giống `List<?>`; từ `Object` không thể dùng nó để xác minh kiểu generic theo cách đơn giản.
7. **Dùng raw type để “lách” kiểm tra.** `List raw` loại bỏ an toàn kiểu, dễ tạo heap pollution và `ClassCastException` muộn.
8. **Dùng pattern variable ngoài scope.** Sau `if` thông thường hoặc trong nhánh không khớp, biến pattern có thể không tồn tại; dùng `&&` hoặc guard clause đúng luồng.
9. **Dùng `case List<?>` trên JDK 17 không bật preview.** Switch type patterns chính thức từ Java 21; với Java 17, dùng `instanceof`.
10. **Đánh đồng class token với type token cho generic lồng nhau.** `List.class` chỉ kiểm tra lớp `List`, không xác minh `List<String>`.

## 12. Bài tập tự luyện

1. Viết `static int countStrings(Object x)` dùng `instanceof List<?> list` để trả số phần tử là `String`; với `List.of("a", 10, "b")` trả 2, còn `"not a list"` trả 0.
2. Với `Object x = List.of("a")`, thử biên dịch `if (x instanceof List<String> names)`. Giải thích vì sao compiler từ chối; sửa bằng `List<?>`.
3. Với `List<String> names = new ArrayList<>();`, thử `if (names instanceof ArrayList<String> concrete)`. Giải thích vì sao compiler cho phép trường hợp này dù `ArrayList<String>` không reifiable.
4. Dùng `Map<?, ?>` để kiểm tra `Object` và đếm số entry có key là `String` và value là `Integer`. Kiểm tra riêng key/value trong vòng lặp.
5. Viết chương trình Java 21 `switch` với `case List<?> list when list.isEmpty()`, `case List<?> list`, `case Map<?, ?> map` và `default`; thử thay đổi thứ tự hai nhánh `List` để thấy lỗi dominance.
6. Nhận dữ liệu có cấu trúc `List<List<?>>`; giải thích vì sao một phép thử container chưa đủ, rồi duyệt và xác minh từng cấp. Không dùng unchecked cast để đạt kết quả.
7. Tạo một `Class<T>` validator cho `String.class`, sau đó giải thích vì sao không thể lấy `List<String>.class` theo cách tương tự.

**Ghi nhớ:** Pattern matching với generic type phải dựa trên **điều Java có thể kiểm tra thật tại runtime** và **bằng chứng kiểu tĩnh mà compiler đã có**. `List<?>` an toàn để kiểm tra container; `instanceof String s` kiểm tra phần tử; một số kiểu như `ArrayList<String>` vẫn được dùng trong refinement từ `List<String>` theo quy tắc chuyển kiểu Java 16+. Không dùng type erasure như lý do để bỏ kiểm tra phần tử khi đầu vào không đáng tin.

## Tài liệu tham khảo

- [JLS 17, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).
- [JLS 17, §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7).
- [JLS 17, §15.20.2 — `instanceof` Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [Oracle Java 17 — Pattern Matching for `instanceof`](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
- [Oracle Java 21 — Pattern Matching for `switch`](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [OpenJDK JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441).
