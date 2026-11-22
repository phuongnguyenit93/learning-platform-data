# `java.util.Objects` — Tiện ích dùng chung cho hợp đồng đối tượng trong Java

## 1. `Objects` dùng để làm gì?

Trong Java, các đối tượng tham gia vào một số hợp đồng quan trọng: **so sánh bằng nhau**, **mã băm tương ứng với quan hệ bằng nhau**, **biểu diễn dưới dạng chuỗi**, **chấp nhận hoặc từ chối `null`**, và **kiểm tra các đối số hợp lệ**. Việc tự lặp các kiểm tra này ở nhiều lớp có thể tạo ra sai sót.

Lớp tiện ích **`java.util.Objects`**, được giới thiệu từ **Java 7**, cung cấp các phương thức `static` để diễn đạt những thao tác thường gặp:

```java
import java.util.Objects;

boolean same = Objects.equals("A", "A");    // true
int hash = Objects.hash("A", 7);             // mã băm tổng hợp
String name = Objects.toString(null, "?");   // "?"
String value = Objects.requireNonNull("ok"); // "ok"
```

Đây là các **câu lệnh minh họa** đặt trong phương thức hoặc môi trường tương ứng. Trong Java hiện đại, `Objects` vẫn là tiện ích hữu dụng và không phải API legacy. Tuy nhiên, **không phải tất cả phương thức của lớp xuất hiện cùng lúc trong Java 7**: `isNull`/`nonNull` được bổ sung ở Java 8; `requireNonNullElse`, `requireNonNullElseGet` và các phương thức kiểm tra phạm vi `checkIndex`/`checkFrom...` có từ Java 9. Các ví dụ chạy đầy đủ trong bài sử dụng **Java 17+**, đồng thời chú thích tính tương thích phiên bản.

> `Objects` giúp triển khai và sử dụng hợp đồng đối tượng **rõ ràng hơn**, chứ không tự chứng minh rằng việc override `equals`, `hashCode` hay tính bất biến của đối tượng đã đúng. Người viết lớp vẫn chịu trách nhiệm về tính nhất quán của hợp đồng.

## 2. `Objects.equals(a, b)` — so sánh bằng nhau an toàn với `null`

### 2.1. Vì sao không luôn gọi trực tiếp `a.equals(b)`?

Lệnh:

```java
String a = null;
String b = "hello";

// a.equals(b); // Ném NullPointerException.
boolean same = Objects.equals(a, b); // false
```

`Objects.equals(a, b)` xử lý được `null` ở cả hai vế:

| `a` | `b` | Kết quả `Objects.equals(a, b)` |
| --- | --- | --- |
| `null` | `null` | `true` |
| `null` | đối tượng khác `null` | `false` |
| đối tượng khác `null` | `null` | `false` |
| Cả hai tham chiếu cùng một đối tượng | Cùng tham chiếu | `true` |
| Hai đối tượng khác nhau | Đều khác `null` | Theo `a.equals(b)` |

Về ý nghĩa, cách tính gần với:

```java
boolean same = (a == b) || (a != null && a.equals(b));
```

Trong đoạn trên, `a` và `b` là các biến đã khai báo trong ngữ cảnh phương thức. **`Objects.equals` không đồng nghĩa với `==`**: `==` trên tham chiếu kiểm tra hai biến có trỏ đến cùng đối tượng hay không, còn `equals` có thể so sánh **giá trị logic** do lớp định nghĩa.

```java
String a = new String("same");
String b = new String("same");

System.out.println(a == b);              // false
System.out.println(Objects.equals(a, b)); // true
```

Ở đây `new String(...)` được dùng có chủ đích để tạo hai đối tượng khác nhau phục vụ minh họa; đây không phải cách tạo `String` nên dùng cho nhu cầu thông thường.

### 2.2. `Objects.equals` không sửa được `equals` bị viết sai

Nếu lớp tự triển khai `equals` mà phá vỡ **tính đối xứng**, **tính bắc cầu** hoặc sự **nhất quán**, `Objects.equals(a,b)` vẫn sử dụng implementation ấy. Trong trường hợp hai tham chiếu khác nhau, phép so sánh sẽ gọi `a.equals(b)` — tức kết quả còn phụ thuộc **phía trái**.

Vì vậy, không được kết luận rằng việc thay tất cả `a.equals(b)` thành `Objects.equals(a,b)` sẽ tự sửa các lỗi hợp đồng đối tượng. Nó chủ yếu giải quyết **null-safety** và cung cấp cách viết nhất quán.

## 3. Hợp đồng `equals` và `hashCode`: bộ đôi không thể tách rời

Khi một lớp có khái niệm “hai đối tượng bằng nhau theo giá trị”, hai phương thức `equals` và `hashCode` phải tương thích:

1. `equals` phải có các tính chất **phản xạ**, **đối xứng**, **bắc cầu** và **nhất quán**; với mọi đối tượng khác `null`, `x.equals(null)` phải là `false`.
2. **Nếu `a.equals(b) == true` thì `a.hashCode() == b.hashCode()` bắt buộc đúng.**
3. Hai đối tượng **có cùng hash code không nhất thiết bằng nhau**; va chạm băm là hợp lệ.
4. Giá trị dùng cho `equals`/`hashCode` nên ổn định trong thời gian đối tượng được dùng làm khóa trong `HashMap` hoặc phần tử `HashSet`. Đối tượng đổi trạng thái sau khi thêm vào cấu trúc băm có thể khiến thao tác tìm kiếm trở nên sai lệch.

`Objects` có hai tiện ích khác nhau:

```java
int one = Objects.hashCode(sku);
int many = Objects.hash(sku, label);
```

Trong ví dụ, `sku` và `label` là hai biến tham chiếu được khai báo trước đó.

- **`Objects.hashCode(obj)`**: nếu `obj == null`, trả `0`; nếu khác `null`, trả `obj.hashCode()`.
- **`Objects.hash(values...)`**: tạo **một hash code tổng hợp từ nhiều giá trị**, dựa trên cách băm mảng đối số được truyền vào. Nó thích hợp khi `equals` xét nhiều trường.

**Đừng đánh đồng** `Objects.hashCode(x)` với `Objects.hash(x)`. Phương thức thứ hai nhận **varargs** nên cách tổng hợp không nhất thiết giống `x.hashCode()`, ngay cả khi chỉ truyền một giá trị.

### 3.1. Mẫu lớp triển khai đúng hợp đồng

```java
import java.util.Objects;

final class Product {
    private final String sku;
    private final String label;

    Product(String sku, String label) {
        this.sku = Objects.requireNonNull(sku, "sku");
        this.label = label; // Cho phép null theo hợp đồng lớp.
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Product p)) return false;
        return sku.equals(p.sku)
                && Objects.equals(label, p.label);
    }

    @Override
    public int hashCode() {
        return Objects.hash(sku, label);
    }
}
```

Đây là **lớp minh họa** viết theo Java 17+ vì sử dụng cú pháp `instanceof Product p`. Cách này giúp hai phương thức `equals` và `hashCode` xét **cùng tập trường** `sku` và `label`.

- `sku` bắt buộc khác `null` nhờ `requireNonNull`, nên có thể dùng `sku.equals(p.sku)`.
- `label` được phép `null`, vì vậy `Objects.equals(label,p.label)` tránh `NullPointerException`.
- `hashCode` dùng `Objects.hash(sku,label)` theo đúng những trường dùng để so sánh bằng nhau.
- Các trường `final` làm tham chiếu không đổi sau khi khởi tạo; `String` cũng bất biến, giúp đối tượng này có khóa băm ổn định.

**Chú ý thiết kế:** không phải mọi lớp `Product` đều nên so sánh cả `sku` và `label`. Nếu nghiệp vụ định nghĩa hai sản phẩm cùng `sku` là bằng nhau bất kể nhãn, thì **cả `equals` lẫn `hashCode`** cần dùng riêng `sku`. Điều quan trọng là **cùng một hợp đồng**, không phải một tập trường cố định cho mọi lớp.

### 3.2. Lớp `record` và tiện ích `Objects`

Với Java 16+, `record` tự sinh các phương thức `equals`, `hashCode` và `toString` phù hợp với các thành phần của record:

```java
record Point(int x, int y) {}
```

Nếu chỉ cần một kiểu dữ liệu giữ giá trị đơn giản, record có thể giảm mã lặp và tránh sai sót override. Dù vậy, `Objects.requireNonNull` vẫn hữu ích trong constructor hoặc compact constructor khi record cần ràng buộc dữ liệu:

```java
record Customer(String id, String name) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
    }
}
```

Các đoạn record trên là ví dụ **Java 17+**, không thuộc cú pháp Java 7. Record **không tự ngăn** một trường tham chiếu trỏ tới đối tượng mutable; thiết kế bất biến sâu vẫn cần kiểm soát riêng.

## 4. `Objects.deepEquals(a, b)`: khác gì `Objects.equals`?

Mảng Java mặc định không so sánh nội dung bằng phương thức `equals` kế thừa từ `Object`; hai mảng mới có cùng phần tử vẫn không bằng nhau theo `Objects.equals` nếu không phải cùng tham chiếu.

```java
int[] x = {1, 2};
int[] y = {1, 2};

System.out.println(Objects.equals(x, y));     // false
System.out.println(Objects.deepEquals(x, y)); // true
```

`Objects.deepEquals` được dùng để so sánh nội dung mảng, bao gồm các cấp mảng lồng nhau (và đối chiếu các kiểu mảng nguyên thủy thích hợp). Nếu hai đối tượng không phải mảng, nó dùng phép so sánh giá trị tương đương `equals`.

Ví dụ mảng lồng nhiều kiểu:

```java
Object[] left  = {new int[] {1, 2}, new String[] {"A", "B"}};
Object[] right = {new int[] {1, 2}, new String[] {"A", "B"}};

boolean shallow = Objects.equals(left, right);     // false
boolean deep = Objects.deepEquals(left, right);    // true
```

**Cần nhớ ba điểm:**

- `deepEquals` không đồng nghĩa với so sánh “toàn bộ graph đối tượng” theo mọi thuộc tính. Nó xử lý **mảng** theo quy tắc đệ quy; đối tượng phần tử không phải mảng vẫn chịu hợp đồng `equals` của lớp tương ứng.
- Nếu dữ liệu là collection như `List<String>`, `List.equals` đã so sánh phần tử theo hợp đồng của collection; thường chỉ cần `Objects.equals(listA,listB)`.
- Nếu một lớp dùng **nội dung mảng** trong `equals`, thì `hashCode` cũng phải băm tương ứng **theo nội dung**, ví dụ `Arrays.hashCode(int[])`, `Arrays.deepHashCode(Object[])`, thay vì dùng hash theo danh tính của chính mảng.

### Bẫy mảng với `Objects.hash`

`Objects.hash(Object... values)` sử dụng cơ chế varargs. Khi truyền **một mảng**, việc ép kiểu, overload và cách mảng được coi là **một đối tượng** hay **nhiều đối số varargs** sẽ ảnh hưởng kết quả. Đừng mặc định rằng `Objects.hash(array)` luôn là “hash sâu” của mảng.

Ví dụ khi xét nội dung một mảng `int[]`:

```java
int[] numbers = {1, 2, 3};

int byContent = java.util.Arrays.hashCode(numbers);
int byIdentity = Objects.hashCode(numbers); // Dựa trên hashCode() của mảng.
```

Hai biến trên **không diễn đạt cùng hợp đồng băm**. Khi thực hiện `equals` theo nội dung mảng, dùng các phương thức `Arrays.hashCode` hoặc `Arrays.deepHashCode` phù hợp. Đó là công cụ bổ sung quan trọng bên cạnh `java.util.Objects`.

## 5. `requireNonNull`: kiểm tra hợp đồng đầu vào và thất bại sớm

Trong constructor hoặc API không chấp nhận tham số `null`, cách kiểm tra rõ ràng là:

```java
this.id = Objects.requireNonNull(id, "id");
```

Nếu `id != null`, trả lại **chính tham chiếu `id`**; nếu `id == null`, ném `NullPointerException` với thông điệp `"id"`. Phương thức này giúp các lỗi của hợp đồng đầu vào lộ diện **ngay tại ranh giới API**, thay vì ném lỗi ở một vị trí xa hơn.

Các overload thường dùng:

| Phương thức | Hành vi khi đối tượng là `null` | Từ phiên bản |
| --- | --- | --- |
| `requireNonNull(obj)` | Ném `NullPointerException` | Java 7 |
| `requireNonNull(obj, "id")` | Ném `NullPointerException` với thông điệp | Java 7 |
| `requireNonNull(obj, () -> expensiveMessage())` | Tạo thông điệp bằng `Supplier<String>` khi cần | Java 8 |

Ví dụ có thông điệp lười (*lazy message*):

```java
String value = Objects.requireNonNull(input,
        () -> "Missing input for request " + requestId);
```

Đây là đoạn minh họa trong phương thức có biến `input`, `requestId` thích hợp. Supplier chỉ cần được đánh giá khi đối tượng bị `null`; vì vậy nó hữu ích khi tạo thông điệp tốn chi phí. Đừng tạo thông điệp chứa token, mật khẩu hoặc thông tin nhạy cảm chỉ để debug.

**Khi nào không dùng `requireNonNull`?** Nếu `null` là giá trị hợp lệ theo hợp đồng, đừng ném `NullPointerException` chỉ vì “muốn code sạch”. Nếu dữ liệu đầu vào hợp lệ về mặt kỹ thuật nhưng vi phạm quy tắc nghiệp vụ (ví dụ tuổi âm), một `IllegalArgumentException` hoặc kiểu lỗi chuyên biệt thường diễn đạt rõ hơn. `requireNonNull` **không thay thế** mọi loại validation.

## 6. Giá trị mặc định khi `null`: Java 9+

Java 9 bổ sung hai phương thức tiện lợi:

```java
String title = Objects.requireNonNullElse(inputTitle, "untitled");

String generated = Objects.requireNonNullElseGet(
        inputTitle,
        () -> loadDefaultTitle()
);
```

Đây là các câu lệnh minh họa; `inputTitle` và `loadDefaultTitle()` cần được khai báo trong ứng dụng.

- `requireNonNullElse(obj, fallback)`: nếu `obj` khác `null`, trả lại nó; nếu `obj` là `null`, trả `fallback`. **Giá trị được trả không được là `null`**; nếu fallback cần dùng mà lại `null`, sẽ ném `NullPointerException`.
- `requireNonNullElseGet(obj, supplier)`: nếu `obj` khác `null`, trả lại nó **mà không gọi supplier**; nếu `obj == null`, gọi `Supplier.get()` để lấy fallback. Supplier được sử dụng phải hợp lệ và không được trả về `null` trong trường hợp cần giá trị.
- Đây là hai phương thức **đặt hợp đồng kết quả khác `null`**, không phải hàm xử lý exception hay tự kiểm tra ngữ nghĩa của chuỗi (chuỗi rỗng vẫn khác `null`).

So sánh:

```java
String name = Objects.requireNonNullElse(null, "guest"); // "guest"
String lazy = Objects.requireNonNullElseGet(
        null, () -> "generated");                         // "generated"
```

**Bẫy hiệu năng nhỏ:** trong `requireNonNullElse(obj, computeFallback())`, Java đánh giá **đối số phương thức** trước khi gọi, nên `computeFallback()` vẫn chạy ngay cả khi `obj` khác `null`. Khi giá trị dự phòng tốn chi phí và chỉ nên tính khi cần, dùng `requireNonNullElseGet(obj, () -> computeFallback())`.

Nếu muốn cho phép fallback là `null` theo hợp đồng, có thể dùng toán tử điều kiện phù hợp:

```java
String result = inputTitle != null ? inputTitle : nullableDefault;
```

`Objects.requireNonNullElse` **không phù hợp** khi kết quả được phép là `null`, bởi nó ràng buộc giá trị được chọn phải tồn tại.

## 7. `Objects.toString`: biểu diễn giá trị khi có `null`

Hai overload quan trọng:

```java
String a = Objects.toString(null);            // "null"
String b = Objects.toString(null, "(missing)"); // "(missing)"
```

- `Objects.toString(obj)` trả chuỗi `"null"` khi `obj == null`; trường hợp khác thì dùng `obj.toString()`.
- `Objects.toString(obj, nullDefault)` trả `nullDefault` nếu `obj == null`; nếu không, dùng `obj.toString()`.
- Khác với `requireNonNullElse`, `nullDefault` trong `Objects.toString(obj, nullDefault)` có thể là `null`; vậy kết quả cũng có thể là `null`.

Ứng dụng phổ biến là xây dựng thông điệp:

```java
String displayed = Objects.toString(nickname, "(no nickname)");
```

Đây là đoạn minh họa với biến `nickname`. **Đừng coi `toString` là serialization chuẩn**, JSON encoder hay cơ chế tự làm sạch dữ liệu nhạy cảm. Implementation `toString()` của lớp có thể thay đổi định dạng, chứa dữ liệu không nên log hoặc thậm chí có lỗi. Khi log, chỉ đưa những trường được phép hiển thị và giữ thông điệp dễ hiểu.

### Có nên override `toString` cùng với `equals` và `hashCode`?

Ba phương thức có vai trò khác nhau:

- `equals`: định nghĩa quan hệ bằng nhau theo giá trị.
- `hashCode`: giữ nhất quán với `equals` trong các bảng băm.
- `toString`: tạo biểu diễn dễ đọc; **không bắt buộc** phải chứa đúng tất cả trường dùng trong `equals`.

`Objects.toString` giúp xử lý `null`, nhưng **không tự sinh** một implementation `toString` đầy đủ cho lớp của bạn. Khi viết `toString`, hãy ưu tiên các trường cần cho chẩn đoán mà không lộ thông tin riêng tư.

## 8. `Objects.compare(a, b, comparator)`: so sánh thứ tự có kiểm soát

Phương thức:

```java
int order = Objects.compare(a, b, comparator);
```

trả một số âm, 0 hoặc số dương theo quan hệ thứ tự. `comparator` phải biểu diễn luật so sánh phù hợp đối với **các cặp đối tượng khác tham chiếu**; nếu `a == b` (kể cả cả hai cùng `null`), `Objects.compare` trả `0` mà không cần gọi `Comparator.compare`.

Ví dụ Java 17+:

```java
import java.util.Comparator;
import java.util.Objects;

boolean firstComesEarlier =
        Objects.compare("An", "Binh", Comparator.naturalOrder()) < 0;
```

Đây là đoạn minh họa trong phương thức. `firstComesEarlier` là `true` vì thứ tự từ điển của hai chuỗi như vậy. Không nên dựa vào **giá trị tuyệt đối** của kết quả `compare`; thông thường chỉ xét dấu âm/0/dương.

**Lưu ý quan trọng về `null`:** `Objects.compare` **không tự đưa `null` lên đầu hoặc cuối**. Nếu một tham chiếu `null` và tham chiếu kia không, comparator được gọi và phải xử lý tình huống này. Ví dụ:

```java
Comparator<String> nullableNames =
        Comparator.nullsFirst(Comparator.naturalOrder());

int result = Objects.compare(null, "An", nullableNames); // < 0
```

Nếu comparator không hỗ trợ `null`, so sánh một bên `null` có thể ném lỗi. `Objects.compare` hữu ích khi kết hợp logic so sánh có kiểm soát, nhưng không thay thế hợp đồng `Comparator`. Comparator cũng nên nhất quán với `equals` khi được sử dụng trong các cấu trúc cần quan hệ bằng nhau tương thích (chẳng hạn `TreeSet`/`TreeMap`), nếu không có chủ đích khác.

## 9. `Objects.isNull` và `Objects.nonNull`: Java 8+

Các phương thức:

```java
Objects.isNull(value);   // tương đương kiểm tra value == null
Objects.nonNull(value);  // tương đương kiểm tra value != null
```

không có “phép kiểm tra sâu” nào khác. Với kiểm tra trực tiếp, `value == null` thường dễ đọc hơn; các phương thức này đặc biệt hợp với **method reference** trong API chức năng:

```java
import java.util.List;
import java.util.Objects;

List<String> raw = java.util.Arrays.asList("An", null, "Binh");

List<String> names = raw.stream()
        .filter(Objects::nonNull)
        .toList(); // Java 16+
```

Đây là đoạn minh họa Java 17+. `names` chứa `["An", "Binh"]`. `Stream.toList()` trả một danh sách không hỗ trợ các thao tác sửa cấu trúc; nó được bổ sung ở Java 16. Nếu chương trình cần `ArrayList` có thể sửa, có thể dùng `collect(java.util.stream.Collectors.toCollection(java.util.ArrayList::new))`.

**Không sử dụng `Objects::nonNull` để thay cho xác thực nghiệp vụ.** Nó chỉ loại bỏ giá trị `null`; chuỗi rỗng, chuỗi toàn dấu cách, ID không hợp lệ hoặc dữ liệu sai định dạng vẫn có thể đi qua bộ lọc.

## 10. Kiểm tra chỉ số và khoảng: Java 9+

Các phương thức sau được bổ sung ở Java 9 và hữu ích khi viết API thao tác mảng, buffer hoặc vùng con của cấu trúc dữ liệu:

| Phương thức | Điều kiện hợp lệ | Kết quả nếu hợp lệ |
| --- | --- | --- |
| `Objects.checkIndex(index, length)` | `0 <= index < length` | Trả lại `index` |
| `Objects.checkFromToIndex(from, to, length)` | `0 <= from <= to <= length` | Trả lại `from` |
| `Objects.checkFromIndexSize(from, size, length)` | `from >= 0`, `size >= 0` và `from + size <= length` (không tràn số khi đánh giá hợp đồng) | Trả lại `from` |

Nếu không hợp lệ, chúng ném `IndexOutOfBoundsException`. Chỉ số `to` là **cận trên loại trừ** trong `checkFromToIndex`, phù hợp nhiều API Java. Khoảng rỗng (ví dụ `from == to`) vẫn có thể hợp lệ.

```java
int valid = Objects.checkIndex(1, 3);         // 1
int from = Objects.checkFromToIndex(1, 3, 3); // 1
int start = Objects.checkFromIndexSize(1, 2, 3); // 1
```

Đây là các câu lệnh minh họa trong phương thức. Dùng chúng khi tự triển khai logic kiểm tra phạm vi; nếu gọi `list.get(i)` hay `arraycopy` qua API chuẩn, các API đó thường đã có kiểm tra của riêng mình. Không phải thêm `checkIndex` trùng lặp ở mọi vị trí.

Điều kiện chỉ số không tự kiểm tra **nội dung phần tử** và không thể xác thực ID hoặc độ dài dữ liệu nghiệp vụ. Phân biệt kiểm tra chỉ số với kiểm tra `null` và hợp đồng `equals`/`hashCode`.

## 11. Ví dụ độc lập Java 17+: kiểm tra nhiều hợp đồng trong một chương trình

Ví dụ này sử dụng `Objects` ở những điểm có giá trị rõ ràng: ràng buộc `null` khi tạo đối tượng, so sánh giá trị, hash code đồng nhất, biểu diễn chuỗi, xử lý mảng, default value, thứ tự và chỉ số.

Tạo tệp **`ObjectsContractDemo.java`**:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class ObjectsContractDemo {
    static final class Product {
        private final String sku;
        private final String label;

        Product(String sku, String label) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Product p)) return false;
            return sku.equals(p.sku) && Objects.equals(label, p.label);
        }

        @Override
        public int hashCode() {
            return Objects.hash(sku, label);
        }

        @Override
        public String toString() {
            return "Product[sku=" + sku + ", label="
                    + Objects.toString(label, "(none)") + "]";
        }
    }

    public static void main(String[] args) {
        String a = new String("same");
        String b = new String("same");
        System.out.println("strings equal = " + Objects.equals(a, b));
        System.out.println("same reference = " + (a == b));
        System.out.println("nulls equal = " + Objects.equals(null, null));

        Object[] left = {new int[] {1, 2}, new String[] {"A", "B"}};
        Object[] right = {new int[] {1, 2}, new String[] {"A", "B"}};
        System.out.println("shallow arrays equal = "
                + Objects.equals(left, right));
        System.out.println("deep arrays equal = "
                + Objects.deepEquals(left, right));

        Product first = new Product("SKU-1", null);
        Product second = new Product("SKU-1", null);
        Set<Product> unique = new HashSet<>();
        unique.add(first);
        unique.add(second);

        System.out.println("products equal = " + first.equals(second));
        System.out.println("hash consistent = "
                + (first.hashCode() == second.hashCode()));
        System.out.println("set size = " + unique.size());
        System.out.println("display = " + first);

        System.out.println("default = "
                + Objects.requireNonNullElse(null, "untitled"));
        System.out.println("lazy = "
                + Objects.requireNonNullElseGet(null, () -> "generated"));
        System.out.println("compare less = "
                + (Objects.compare("An", "Binh",
                        Comparator.naturalOrder()) < 0));
        System.out.println("valid index = " + Objects.checkIndex(1, 3));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ObjectsContractDemo.java
java ObjectsContractDemo
```

**Stdout chính xác:**

```text
strings equal = true
same reference = false
nulls equal = true
shallow arrays equal = false
deep arrays equal = true
products equal = true
hash consistent = true
set size = 1
display = Product[sku=SKU-1, label=(none)]
default = untitled
lazy = generated
compare less = true
valid index = 1
```

**Đọc kết quả:**

1. Hai đối tượng `String` được tạo mới có giá trị bằng nhau theo `equals` dù khác tham chiếu.
2. `Objects.equals(null,null)` là `true`; điều này không có nghĩa `null` là đối tượng.
3. Hai mảng ngoài khác nhau nên `Objects.equals(left,right)` là `false`, trong khi `deepEquals` so sánh được nội dung mảng lồng nhau và trả `true`.
4. Hai sản phẩm có cùng `sku` và `label` được xem là bằng nhau; `hashCode` nhất quán nên `HashSet` giữ một phần tử.
5. `Objects.toString(label,"(none)")` tạo thông điệp an toàn với `label == null`.
6. Hai giá trị mặc định Java 9+ trả kết quả đúng khi đầu vào là `null`; cách thứ hai chỉ chạy supplier khi cần.
7. `Objects.compare` sử dụng comparator để xác định thứ tự, còn `checkIndex(1,3)` xác nhận chỉ số nằm trong `[0,3)`.

Dù ví dụ dùng `Java 17+` (có pattern matching `instanceof`), những tiện ích cốt lõi của `Objects` như `equals`, `deepEquals`, `hash`, `hashCode`, `compare`, `toString`, `requireNonNull` đã có từ Java 7. Chỉ mang các đoạn sử dụng API mới sang JDK cũ khi phiên bản thực sự hỗ trợ.

## 12. Chọn đúng tiện ích theo ý định

| Bạn muốn | Phương thức nên cân nhắc | Lưu ý |
| --- | --- | --- |
| So sánh hai tham chiếu có thể `null` theo giá trị | `Objects.equals(a,b)` | Còn phụ thuộc hợp đồng `equals` của lớp |
| So sánh mảng theo nội dung/lồng nhau | `Objects.deepEquals(a,b)` | Kết hợp hash tương thích khi override |
| Lấy hash của một đối tượng có thể `null` | `Objects.hashCode(obj)` | `null` cho `0` |
| Tạo hash từ nhiều trường | `Objects.hash(a,b,c)` | Tránh nhầm ngữ nghĩa với hash nội dung mảng |
| Chặn `null` tại ranh giới API | `Objects.requireNonNull(obj, "field")` | Ném `NullPointerException` |
| Mặc định khác `null` khi đầu vào `null` | `Objects.requireNonNullElse` / `ElseGet` | Java 9+, hỗ trợ tính lazy ở `ElseGet` |
| In một đối tượng có thể `null` | `Objects.toString(obj, "(missing)")` | Không tự kiểm soát nội dung nhạy cảm |
| So sánh thứ tự qua comparator | `Objects.compare(a,b,cmp)` | Xử lý `null` bằng comparator phù hợp |
| Lọc phần tử `null` trong Stream | `Objects::nonNull` | Java 8+ |
| Kiểm tra chỉ số/khoảng trước truy cập | `checkIndex`, `checkFromToIndex`, `checkFromIndexSize` | Java 9+; ném `IndexOutOfBoundsException` |

## 13. Những lỗi thường gặp

| Sai lầm | Vì sao sai/nguy hiểm | Cách làm đúng |
| --- | --- | --- |
| Coi `Objects.equals(a,b)` là `a == b` | So sánh giá trị có thể khác so sánh tham chiếu | Dùng theo đúng mục đích: giá trị hoặc danh tính |
| Nghĩ `Objects.equals` tự sửa lớp có `equals` sai | Nó vẫn dùng implementation của lớp | Kiểm tra phản xạ, đối xứng, bắc cầu, nhất quán |
| Override `equals` nhưng quên `hashCode` | `HashSet`/`HashMap` có thể sai hành vi tìm kiếm | Giữ cùng tập trường và hợp đồng băm |
| Cho rằng hash code bằng nhau nghĩa là đối tượng bằng nhau | Va chạm hash là bình thường | Gọi `equals` để xác nhận |
| Sửa trường khóa sau khi thêm đối tượng vào `HashMap` | Khóa có thể chuyển sang bucket logic khác | Ưu tiên khóa bất biến |
| Gọi `Objects.equals` với hai mảng khác nhau nhưng cùng nội dung | Mảng mặc định so sánh tham chiếu | Dùng `Objects.deepEquals` hoặc `Arrays.equals` tương ứng |
| Dùng `Objects.hashCode(array)` để băm theo nội dung mảng | Thường dựa trên hash của chính đối tượng mảng | Dùng `Arrays.hashCode`/`deepHashCode` |
| Nhầm `Objects.hash(x)` với `Objects.hashCode(x)` | `hash` tổng hợp varargs, không nhất thiết bằng hash một đối tượng | Chọn đúng phương thức |
| Gọi `requireNonNull` lên trường mà `null` được cho phép | Tự thay đổi hợp đồng dữ liệu | Chỉ chặn `null` khi cần |
| Nghĩ `requireNonNullElseGet` luôn gọi supplier | Supplier chỉ chạy khi phải lấy fallback | Dùng để tính default lười |
| Nghĩ `Objects.compare` tự xử lý `null` hai phía khác nhau | Comparator được gọi khi hai tham chiếu khác nhau | Chọn `Comparator.nullsFirst/nullsLast` |
| Coi `Objects.toString` là serialization an toàn | Phụ thuộc `toString` của đối tượng | Dùng encoder/serializer phù hợp và bảo vệ dữ liệu |
| Dùng `Objects::nonNull` để kiểm tra dữ liệu nghiệp vụ | Chỉ loại bỏ `null` | Kết hợp validation theo hợp đồng |
| Dùng `checkIndex` với cận trên inclusive | Chỉ số hợp lệ là `[0,length)` | Cẩn thận khoảng nửa mở |
| Dùng phương thức Java 9 hoặc cú pháp Java 17 trên JDK 7 | Không tương thích phiên bản | Ghi rõ baseline Java của dự án |

## 14. Bài tập và đáp án

### Bài 1 — So sánh `null`

Giả sử `String a = null; String b = null;`. `Objects.equals(a,b)` trả gì? `a.equals(b)` có an toàn không?

**Đáp án:** `Objects.equals(a,b)` là `true`. `a.equals(b)` ném `NullPointerException` vì `a` là `null`.

### Bài 2 — Hợp đồng hash

Một lớp `Order` có `equals` dựa trên `orderId` và `customerId`, nhưng `hashCode` chỉ dựa trên `orderId`. Có nhất thiết sai không? Khi nào nên thay đổi?

**Đáp án:** Không nhất thiết **vi phạm hợp đồng**: hai đối tượng bằng nhau sẽ có cùng `orderId`, nên mã băm cũng như nhau. Tuy nhiên, bỏ `customerId` có thể tăng va chạm; nếu dùng `Objects.hash(orderId,customerId)` thì phân tán tốt hơn trong nhiều tình huống. Điều quan trọng là *tính nhất quán bắt buộc*, không phải hash phải sử dụng chính xác mọi trường `equals`. Nếu ngược lại, `hashCode` dựa vào trường có thể khác giữa hai đối tượng mà `equals` xem là bằng nhau, đó mới là vi phạm.

### Bài 3 — So sánh mảng

```java
String[] a = {"A", "B"};
String[] b = {"A", "B"};
```

**Câu hỏi:** `Objects.equals(a,b)` và `Objects.deepEquals(a,b)` trả gì?

**Đáp án:** `false` và `true`, vì hai mảng là hai đối tượng riêng, còn `deepEquals` xét nội dung.

### Bài 4 — Phân biệt hai phương thức băm

`Objects.hashCode(null)` và `Objects.hash((Object) null)` có luôn bằng nhau không?

**Đáp án:** Không. `Objects.hashCode(null)` là `0`; `Objects.hash((Object) null)` truyền **một phần tử `null` vào varargs** để băm mảng các đối số, cho ra `31` theo cơ chế `Arrays.hashCode(Object[])`. Đây là ví dụ cụ thể vì sao không hoán đổi hai phương thức.

### Bài 5 — Kiểm tra chỉ số

`Objects.checkIndex(3,3)` hợp lệ không? `Objects.checkFromToIndex(1,3,3)` thì sao?

**Đáp án:** `checkIndex(3,3)` ném `IndexOutOfBoundsException` vì chỉ số tối đa hợp lệ là `2`; `checkFromToIndex(1,3,3)` hợp lệ vì cận `to` là cận loại trừ và được phép bằng `length`.

### Bài 6 — Default lười

`Objects.requireNonNullElseGet("ready", () -> costlyCall())` có gọi `costlyCall()` không?

**Đáp án:** Không, vì giá trị thứ nhất khác `null`; supplier không cần chạy. Đây là khác biệt với truyền kết quả `costlyCall()` như một đối số được đánh giá trước vào `requireNonNullElse`.

### Bài 7 — Comparator và `null`

`Objects.compare(null, "An", Comparator.naturalOrder())` có chắc an toàn không?

**Đáp án:** Không. Hai tham chiếu khác nhau nên comparator được gọi; `naturalOrder` không chấp nhận `null` theo cách đó. Muốn cho phép `null`, có thể dùng `Comparator.nullsFirst(Comparator.naturalOrder())`.

### Bài 8 — Cần `Objects` hay `Arrays`?

Bạn cần viết `equals` và `hashCode` cho lớp chứa trường `int[] data` và muốn so sánh **nội dung mảng**. Cặp phương thức nào nên sử dụng?

**Đáp án:** `Arrays.equals(data, other.data)` kết hợp với `Arrays.hashCode(data)` (và xử lý `null` theo hợp đồng lớp). Nếu có mảng đối tượng nhiều cấp cần so sánh sâu, cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode`. Không dùng `Objects.hashCode(data)` để băm nội dung `int[]`.

## 15. Kết luận

`java.util.Objects` là bộ công cụ chung để **diễn đạt hợp đồng đối tượng ngắn gọn và nhất quán**: `equals` cho so sánh an toàn với `null`; `deepEquals` cho mảng; `hashCode` và `hash` cho mã băm; `requireNonNull` và các lựa chọn mặc định để quy định đầu vào; `toString` để trình bày; `compare` để dùng comparator; `isNull`/`nonNull` và các kiểm tra phạm vi hỗ trợ những tình huống hiện đại.

Hãy chọn **đúng phương thức cho đúng hợp đồng**, đặc biệt ở ranh giới **tham chiếu vs giá trị**, **array identity vs array content**, **`hashCode` vs `hash`** và **`null` hợp lệ vs `null` bị từ chối**. Java 7 giới thiệu lớp `Objects`; các tiện ích bổ sung từ Java 8/9 vẫn được sử dụng trên Java 17+ và những phiên bản Java hiện đại.