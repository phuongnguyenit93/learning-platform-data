# Quan hệ giữa target, pattern và pattern variable trong Java

Trong **pattern matching với `instanceof`** (có thể dùng ổn định trên Java 17), ba khái niệm liên kết với nhau theo một chuỗi: **target** là giá trị đem ra kiểm tra; **pattern** mô tả điều kiện để giá trị đó khớp; **pattern variable** nhận giá trị đã khớp dưới một kiểu tĩnh cụ thể. Hiểu đúng mối quan hệ này giúp tránh ép kiểu lặp lại và dùng biến an toàn theo luồng điều khiển.

## 1. Đọc đúng một biểu thức

```java
Object target = "Java";
if (target instanceof String text) {
    System.out.println(text.length());
}
```

| Thành phần | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Target (đối tượng/biểu thức được kiểm tra) | `target`, bên trái `instanceof` | Cung cấp giá trị tại thời điểm chạy; ở đây giá trị là tham chiếu đến chuỗi `"Java"`. |
| Pattern (mẫu) | `String text`, bên phải `instanceof` | Đây là **type pattern**: yêu cầu giá trị có kiểu phù hợp với `String`, đồng thời khai báo tên biến sẽ được gắn khi khớp. |
| Pattern variable (biến của mẫu) | `text` | Chỉ được gắn giá trị khi mẫu khớp; trong vùng sử dụng hợp lệ, trình biên dịch biết `text` có kiểu `String`. |

Cụ thể, `String` là **kiểu của pattern**, còn `text` là **tên pattern variable**; cả cặp `String text` mới là pattern. `instanceof` là toán tử thực hiện phép kiểm tra, không phải một phần của tên biến. Tên `target` chỉ là tên biến trong ví dụ, không phải từ khóa Java; phía trái có thể là một biểu thức trả về tham chiếu.

Khi điều kiện đúng, `text.length()` hợp lệ vì `text` có kiểu tĩnh `String`. Kết quả là `4`. Không cần viết thêm `(String) target`.

## 2. Cơ chế: từ target đến binding

Với `target instanceof String text`, có thể theo dõi lần lượt:

1. **Đánh giá target** để lấy giá trị. Nếu phía trái là lời gọi hàm, biểu thức đó được đánh giá một lần cho phép kiểm tra này.
2. **Kiểm tra type pattern** trên giá trị tại thời điểm chạy. Với `String text`, giá trị phải khác `null` và là một đối tượng tương thích với kiểu `String`.
3. **Binding khi khớp**: Java gắn tham chiếu đến đối tượng ấy vào pattern variable `text`, dưới kiểu tĩnh `String`. Nhánh đúng được thực thi và có thể truy cập `text`.
4. **Không binding khi không khớp**: kết quả `instanceof` là `false`; không tồn tại một giá trị `text` hợp lệ để nhánh sai sử dụng.

Mối quan hệ có thể viết gọn:

```text
target (biểu thức -> giá trị runtime)
    |
    v
instanceof + pattern (ví dụ: String text)
    |-- khớp --> true  --> binding text --> dùng text ở nơi chắc chắn đã khớp
    |
    +-- không khớp --> false --> không binding text
```

**Pattern variable không tạo đối tượng mới và không sao chép đối tượng.** Ngay sau khi khớp, `target` và `text` cùng tham chiếu đến một đối tượng; chỉ khác nhau ở kiểu tĩnh mà trình biên dịch cho phép sử dụng. Nếu sau này gán lại `text`, hai biến có thể không còn trỏ đến cùng đối tượng.

## 3. Kiểu tĩnh của target, kiểu của pattern và kiểu runtime

Phải tách ba điều:

- **Kiểu tĩnh của target**: kiểu trình biên dịch biết từ khai báo hoặc biểu thức. Trong `Object target = "Java"`, kiểu tĩnh của `target` là `Object`.
- **Kiểu runtime của giá trị**: lớp thực tế của đối tượng, ở ví dụ là `String`.
- **Kiểu của pattern variable**: kiểu ghi trong mẫu; `String text` làm `text` có kiểu tĩnh `String` sau khi khớp.

Kiểu pattern không nhất thiết trùng với lớp runtime. Chẳng hạn:

```java
Object target = new StringBuilder("Java");
if (target instanceof CharSequence sequence) {
    System.out.println(sequence.length());               // 4
    System.out.println(sequence.getClass().getSimpleName()); // StringBuilder
}
```

`StringBuilder` triển khai interface `CharSequence`, nên pattern `CharSequence sequence` khớp. Biến `sequence` có kiểu tĩnh `CharSequence`; việc gọi `length()` hợp lệ vì phương thức này thuộc interface. Nó vẫn trỏ đến đối tượng `StringBuilder` thật. Ngược lại, không thể gọi một phương thức chỉ riêng `StringBuilder` qua `sequence` nếu kiểu `CharSequence` không khai báo phương thức đó.

Trình biên dịch còn kiểm tra **khả năng tương thích kiểu** trước khi chương trình chạy. Ví dụ, `Object target` có thể chứa `String`, nên kiểm tra bằng `String text` là hợp lệ. Nếu target đã được khai báo chính là `String`, viết `target instanceof String text` có thể bị từ chối vì phép thử type pattern hiển nhiên đúng cho mọi giá trị khác `null` thuộc kiểu tĩnh ấy; hãy dùng trực tiếp biến đã có, và kiểm tra `null` riêng nếu cần. Không nên dùng pattern matching cho một phép kiểm tra kiểu không có ý nghĩa.

Với `target == null`, mọi type pattern ở đây đều **không khớp**: `null instanceof String text` là `false`, không ném `NullPointerException` chỉ vì toán tử `instanceof`. Pattern matching kiểm tra **kiểu**, không kiểm tra chuỗi bằng nội dung như `equals`.

## 4. Ví dụ chạy được: cả ba vai trò trong một chương trình

Lưu thành `MatchingRolesDemo.java`:

```java
public class MatchingRolesDemo {
    static void describe(Object target) {
        if (target instanceof String text) {
            System.out.println("type=String; value=" + text);
            System.out.println("length=" + text.length());
            System.out.println("sameReference=" + (target == text));
        } else {
            System.out.println("no match: " + target);
        }
    }

    public static void main(String[] args) {
        describe("Java");
        describe(42);
        describe(null);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac MatchingRolesDemo.java
java MatchingRolesDemo
```

Kết quả chính xác:

```text
type=String; value=Java
length=4
sameReference=true
no match: 42
no match: null
```

Lần đầu: target trỏ tới `String`; pattern `String text` khớp, nên `text` được gắn và có thể gọi `length()`. So sánh `target == text` trả về `true` vì ngay khi binding, hai tham chiếu chỉ cùng đối tượng. Lần hai: target là `Integer`, không khớp `String`. Lần ba: target là `null`, cũng không khớp. Trong hai lần sau, chỉ nhánh `else` chạy.

## 5. Phạm vi của pattern variable phụ thuộc luồng điều khiển

Pattern variable tuân theo quy tắc **flow scoping**: biến chỉ được sử dụng tại nơi trình biên dịch có thể chứng minh rằng pattern đã khớp. Nó không đơn giản là biến luôn có phạm vi ở toàn bộ khối chứa biểu thức `instanceof`.

**Trong nhánh đúng:**

```java
if (target instanceof String text) {
    System.out.println(text.toUpperCase()); // Hợp lệ: đã khớp String
} else {
    // Không thể dùng text: pattern chưa chắc khớp
}
```

**Với `&&`:** vế phải chỉ chạy khi vế trái đúng, nên biến đã được binding.

```java
if (target instanceof String text && text.length() >= 4) {
    System.out.println(text);
}
```

**Với `||`:** vế phải chỉ chạy khi vế trái sai, nên không thể dựa vào một pattern ở vế trái để dùng biến tại vế phải. Đoạn sau cố ý **không biên dịch**:

```java
// Sai: khi đánh giá vế phải, pattern String text đã không khớp.
if (target instanceof String text || text.isBlank()) {
    System.out.println("...");
}
```

**Sau một nhánh thoát sớm:** nếu nhánh không khớp kết thúc phương thức bằng `return` hoặc không thể tiếp tục, những lệnh tiếp theo có thể sử dụng pattern variable.

```java
static int lengthOrMinusOne(Object target) {
    if (!(target instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ: mọi luồng đến đây đều đã khớp
}
```

Trong trường hợp thông thường dưới đây, lệnh cuối **không biên dịch**, vì sau `if` vẫn có đường đi không khớp:

```java
// Giả sử target là Object.
if (target instanceof String text) {
    System.out.println(text);
}
// System.out.println(text); // Sai: có thể đi qua nhánh không khớp.
```

Dấu `!` đổi chiều điều kiện, nhưng không làm mất ý nghĩa binding: Java phân tích đường đi nào chắc chắn đã có `text`.

## 6. Ví dụ chạy được: điều kiện kép và guard clause

Lưu thành `FlowScopeDemo.java`:

```java
public class FlowScopeDemo {
    static void check(Object target) {
        if (target instanceof String text && text.length() >= 4) {
            System.out.println("Long string: " + text);
        } else {
            System.out.println("Not a long string");
        }
    }

    static String label(Object target) {
        if (!(target instanceof String text)) {
            return "Not String";
        }
        return "String(" + text.length() + ")";
    }

    public static void main(String[] args) {
        check("Java");
        check("Go");
        check(null);
        System.out.println(label("Hello"));
        System.out.println(label(123));
    }
}
```

```bash
javac FlowScopeDemo.java
java FlowScopeDemo
```

```text
Long string: Java
Not a long string
Not a long string
String(5)
Not String
```

Điều kiện `&&` chỉ đọc `text.length()` khi target thực sự là `String`. Ở `label`, mọi giá trị không khớp đều `return` ngay; do đó dòng cuối chỉ nhận các giá trị đã khớp.

## 7. Đối chiếu với `instanceof` và ép kiểu truyền thống

Cách cũ:

```java
if (target instanceof String) {
    String text = (String) target;
    System.out.println(text.length());
}
```

Với type pattern:

```java
if (target instanceof String text) {
    System.out.println(text.length());
}
```

Cả hai thể hiện ý định chỉ thao tác với chuỗi. Type pattern kết hợp kiểm tra kiểu và đặt tên biến đã có kiểu phù hợp; loại bỏ việc viết cast thủ công trong nhánh đã kiểm tra, giảm khả năng cast nhầm hoặc dùng nhầm biến. Đây là một phép kiểm tra kiểu runtime kèm binding, **không phải** cơ chế tự tách thuộc tính của object.

## 8. Những nhầm lẫn cần tránh

1. **Tưởng target và pattern variable là hai object.** Sau khi khớp, chúng cùng tham chiếu đến object ban đầu. `pattern variable` chỉ là tên mới có kiểu tĩnh theo pattern.
2. **Tưởng pattern variable tồn tại dù kiểm tra sai.** Binding chỉ diễn ra khi khớp; hãy dùng biến ở nhánh đúng, vế phải `&&` hoặc sau đường thoát sớm đã chứng minh match.
3. **Nhầm pattern với tên biến.** Trong `target instanceof String text`, pattern đầy đủ là `String text`; `text` chỉ là biến do pattern giới thiệu.
4. **Cho rằng `instanceof` kiểm tra nội dung.** `"Java"` và `"Go"` đều khớp type pattern `String text`; muốn so nội dung thì dùng các phương thức như `equals`, `isBlank` sau khi khớp.
5. **Viết type pattern chứa tham số generic không thể kiểm tra ở runtime.** Chẳng hạn với `Object target`, `target instanceof java.util.List<String> items` không hợp lệ vì Java không xác định được `String` trong tham số kiểu ở runtime. Có thể kiểm tra `target instanceof java.util.List<?> items`, sau đó kiểm tra từng phần tử khi cần.
6. **Cho rằng pattern variable mặc định là `final`.** Trong Java 17, một pattern variable có thể được gán lại trong phạm vi hợp lệ, ví dụ `text = text.strip();`. Phép gán lại này thay đổi giá trị của biến `text`, không tự thay đổi biến `target`; nếu biến được capture bởi lambda, các quy tắc `final` hoặc *effectively final* vẫn áp dụng như với biến cục bộ khác.
7. **Tưởng pattern dùng được ở mọi phiên bản Java theo cùng cú pháp.** Type pattern cho `instanceof` đã ổn định trước Java 17; cú pháp pattern khác, như các dạng pattern trong `switch`, có mốc hỗ trợ riêng. Hai chương trình trong bài dùng cú pháp chạy được trên Java 17+.

## 9. Cách tự kiểm tra khi đọc code

Khi gặp `expression instanceof Type variable`, hãy tự trả lời theo thứ tự: **(1)** `expression` tạo ra giá trị nào và kiểu tĩnh của nó là gì; **(2)** giá trị runtime có khác `null` và tương thích với `Type` không; **(3)** nếu khớp, `variable` được gắn với tham chiếu nào và có kiểu tĩnh gì; **(4)** tại dòng muốn dùng `variable`, mọi đường đi đến đó có bảo đảm pattern đã khớp không?

Bốn câu hỏi này nối trực tiếp **target → pattern → pattern variable → flow scoping**, là nền tảng để đọc và viết pattern matching rõ ràng trong Java.
