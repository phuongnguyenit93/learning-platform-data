# Dùng biến mẫu không tên trong switch và instanceof khi chỉ cần kiểm tra kiểu

Khi kiểm tra kiểu của một giá trị, đôi khi chương trình chỉ cần biết giá trị đó có thuộc một kiểu nhất định hay không. Nếu không cần sử dụng chính giá trị đã khớp, việc đặt tên cho biến pattern sẽ tạo ra một biến mà phần thân xử lý không dùng đến.

Java 22 hoàn thiện tính năng **Unnamed Variables & Patterns** theo JEP 456. Ký hiệu `_` cho phép biểu thị rằng một biến pattern hoặc thành phần pattern được cố ý bỏ qua. Cách viết này đặc biệt hữu ích trong `switch` pattern và trong các pattern lồng nhau của `instanceof`.

Tính năng đã **final từ Java 22**, có thể dùng mà không cần bật preview. Nội dung dưới đây tập trung vào cú pháp vẫn dùng được trong Java hiện đại.

## 1. Biến pattern có tên và biến pattern không tên

Pattern matching cho phép kiểm tra kiểu và, nếu khớp, ràng buộc giá trị vào một biến để sử dụng tiếp.

Ví dụ với biến pattern có tên:

```java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Chuỗi có " + text.length() + " ký tự";
    }

    return "Không phải chuỗi";
}
```

Ở đây, `text` được tạo khi điều kiện `instanceof` khớp và có thể được sử dụng trong nhánh `if`. Cách viết này phù hợp khi chương trình cần gọi phương thức hoặc đọc dữ liệu từ đối tượng đã khớp.

Nếu chỉ cần xác nhận kiểu, có thể viết pattern với `_`:

```java
static boolean isString(Object value) {
    return value instanceof String _;
}
```

`String _` vẫn kiểm tra giá trị có phải là một `String` hay không, nhưng không tạo tên biến để sử dụng. `_` thể hiện rõ rằng chương trình chủ ý bỏ qua giá trị đã khớp.

Với phép kiểm tra kiểu đơn giản ở cấp cao nhất, `value instanceof String` vốn đã là cú pháp ngắn gọn và hợp lệ. Dạng `value instanceof String _` hữu ích khi muốn thể hiện một type pattern không cần binding, đặc biệt khi pattern đó nằm bên trong một pattern lớn hơn.

## 2. Dùng unnamed pattern trong switch

Pattern switch cho phép chọn nhánh theo kiểu của giá trị. Khi chỉ cần phân loại kiểu và không cần dùng đối tượng trong nhánh, hãy dùng `case Type _` thay cho `case Type name`.

```java
static String category(Object value) {
    return switch (value) {
        case String _  -> "Dữ liệu văn bản";
        case Integer _ -> "Số nguyên";
        case Number _  -> "Kiểu số khác";
        case null      -> "Giá trị null";
        default        -> "Kiểu dữ liệu khác";
    };
}
```

Trong ví dụ:

- `case String _` chọn nhánh khi giá trị là một chuỗi.
- `case Integer _` chọn nhánh khi giá trị là một số nguyên dạng `Integer`.
- `case Number _` xử lý những kiểu con khác của `Number` chưa được nhánh trước xử lý.
- `case null` xử lý riêng giá trị `null`.
- `default` xử lý các giá trị còn lại.

Các nhánh chỉ trả về thông tin phân loại, vì vậy không cần binding đối tượng vào một biến. Nếu nhánh cần đọc dữ liệu, hãy dùng biến pattern có tên:

```java
static String describe(Object value) {
    return switch (value) {
        case String text  -> "Chuỗi: " + text;
        case Integer number -> "Số nguyên: " + number;
        case null -> "Không có giá trị";
        default -> "Kiểu khác";
    };
}
```

### 2.1. Thứ tự nhánh và tính bao phủ

Các type pattern có quan hệ bao phủ. `Integer` là kiểu con của `Number`, nên nhánh `case Integer _` phải đứng trước `case Number _`. Nếu đặt `case Number _` trước, nhánh `Integer` phía sau sẽ không thể được chọn và trình biên dịch báo pattern bị chi phối (dominated pattern).

```java
return switch (value) {
    case Number _  -> "Một giá trị số";
    // case Integer _ -> "Số nguyên"; // Không hợp lệ: đã bị Number bao phủ
    default -> "Giá trị khác";
};
```

Một pattern type không khớp với `null`. Với switch pattern, nếu selector có thể là `null`, hãy quyết định rõ cách xử lý bằng `case null` hoặc bảo đảm đầu vào không null trước khi switch. Không nên giả định `default` tự động thay thế cho `case null`.

## 3. Dùng unnamed pattern trong instanceof

`instanceof` thường được dùng để kiểm tra kiểu trước khi thực hiện một thao tác. Khi chỉ cần biết kiểu mà không cần đối tượng đã khớp, có thể dùng unnamed type pattern:

```java
static void logValue(Object value) {
    if (value instanceof String _) {
        System.out.println("Đã nhận một chuỗi");
    } else if (value instanceof Number _) {
        System.out.println("Đã nhận một giá trị số");
    } else {
        System.out.println("Kiểu dữ liệu khác");
    }
}
```

Không có biến có tên `String` hoặc `Number` để tham chiếu trong thân nhánh. Cách viết này giúp người đọc nhận ra mục đích của điều kiện chỉ là phân loại kiểu.

Tuy nhiên, với phép kiểm tra kiểu độc lập, Java đã hỗ trợ cú pháp không binding từ trước:

```java
if (value instanceof String) {
    System.out.println("Đã nhận một chuỗi");
}
```

Hai cách đều kiểm tra cùng một điều kiện. Vì vậy, hãy chọn cú pháp trực tiếp `instanceof String` cho phép kiểm tra đơn giản; unnamed type pattern phát huy tác dụng rõ hơn khi nó là một thành phần của record pattern hoặc cấu trúc pattern khác.

## 4. Bỏ qua thành phần không cần dùng trong record pattern

Một trường hợp hữu ích của unnamed pattern là kiểm tra kiểu của một thành phần trong record mà không cần giữ giá trị thành phần đó.

Giả sử hệ thống nhận một phong bì dữ liệu có payload thuộc nhiều kiểu:

```java
record Envelope(Object payload) {}

static boolean containsText(Object value) {
    return value instanceof Envelope(String _);
}
```

Pattern `Envelope(String _)` kiểm tra đồng thời hai điều kiện:

1. `value` là một đối tượng `Envelope`.
2. Thành phần `payload` của record là một `String`.

Chương trình không cần đọc nội dung chuỗi, nên thành phần được biểu diễn bằng `_`. Nếu cần sử dụng nội dung payload, hãy đặt tên cho pattern:

```java
static String extractText(Object value) {
    if (value instanceof Envelope(String text)) {
        return text;
    }

    return "";
}
```

Ví dụ kết hợp giữ một thành phần và bỏ qua thành phần khác:

```java
record Response(int status, Object body) {}

static boolean isSuccessfulTextResponse(Object value) {
    return value instanceof Response(int status, String _)
            && status >= 200
            && status < 300;
}
```

`status` được đặt tên vì chương trình cần kiểm tra mã trạng thái; `String _` chỉ xác nhận body là chuỗi mà không cần giữ nội dung. Đây là cách dùng điển hình của unnamed pattern trong `instanceof`.

## 5. Khi nào nên dùng `_` và khi nào nên đặt tên?

| Nhu cầu | Cách viết phù hợp | Lý do |
| --- | --- | --- |
| Chỉ phân loại kiểu trong switch | `case String _` | Nhánh không cần đọc đối tượng |
| Kiểm tra kiểu đơn giản bằng instanceof | `value instanceof String` | Cú pháp type test trực tiếp đã đủ |
| Kiểm tra một thành phần record nhưng bỏ qua giá trị | `Envelope(String _)` | Xác nhận kiểu mà không tạo binding không cần thiết |
| Cần gọi phương thức hoặc đọc dữ liệu sau khi khớp | `instanceof String text` | Có biến để sử dụng trong nhánh |
| Vừa kiểm tra một thành phần, vừa sử dụng thành phần khác | `Response(int status, String _)` | Chỉ đặt tên cho dữ liệu thực sự cần dùng |

Một nguyên tắc dễ áp dụng là: **chỉ đặt tên cho pattern variable khi phần xử lý cần tham chiếu đến giá trị đó**. Nếu pattern chỉ đóng vai trò xác nhận kiểu hoặc cấu trúc, `_` diễn đạt đúng ý định hơn.

## 6. Các quy tắc cần nhớ

### 6.1. Không thể đọc giá trị qua `_`

Underscore là ký hiệu bỏ qua, không phải tên biến thông thường. Đoạn mã sau không hợp lệ:

```java
if (value instanceof String _) {
    // System.out.println(_); // Lỗi: không thể tham chiếu unnamed pattern
}
```

Nếu cần truy cập đối tượng, hãy khai báo biến có tên:

```java
if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

### 6.2. Unnamed pattern không bỏ qua điều kiện khớp

Trong `String _`, phần `String` vẫn được kiểm tra. `_` chỉ bỏ qua việc lưu giá trị vào một biến có tên; nó không làm pattern khớp với mọi kiểu.

Tương tự, trong `Envelope(String _)`, record vẫn phải là `Envelope` và thành phần `payload` vẫn phải là `String`. Nếu payload là `Integer` hoặc `null`, pattern này không khớp.

### 6.3. Không nhầm với default hoặc pattern tổng quát

`case String _` chỉ khớp với giá trị thuộc kiểu `String`, còn `default` xử lý các trường hợp chưa được nhánh khác xử lý. Dùng `_` không có nghĩa là bỏ qua toàn bộ phép kiểm tra kiểu.

### 6.4. Tính năng đã final từ Java 22

Unnamed Variables & Patterns được chuẩn hóa trong Java 22 theo JEP 456. Khi biên dịch bằng JDK 22 trở lên, không cần `--enable-preview` cho tính năng này. Có thể chỉ định Java 22 làm phiên bản đích khi dùng JDK mới hơn:

```bash
javac --release 22 -d out Main.java
java -cp out Main
```

Lệnh trên minh họa việc biên dịch mã nguồn theo API và quy tắc ngôn ngữ của Java 22. Nếu dự án dùng phiên bản đích khác, hãy chọn `--release` tương ứng và bảo đảm runtime triển khai hỗ trợ phiên bản đó.

## 7. Ví dụ tổng hợp

Ví dụ sau kết hợp switch pattern, `instanceof` và record pattern để phân loại thông điệp mà chỉ giữ những thành phần thực sự cần dùng:

```java
public class Main {
    record Message(Object body, String source) {}

    static String classify(Object input) {
        if (input instanceof Message(String _, String source)) {
            return "Thông điệp văn bản từ " + source;
        }

        return switch (input) {
            case String _  -> "Chuỗi độc lập";
            case Integer _ -> "Số nguyên độc lập";
            case null      -> "Không có dữ liệu";
            default        -> "Thông điệp không được hỗ trợ";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Message("Xin chào", "API")));
        System.out.println(classify("Java"));
        System.out.println(classify(22));
        System.out.println(classify(null));
    }
}
```

Ở nhánh đầu, `body` phải là chuỗi nhưng nội dung không được sử dụng, vì vậy pattern dùng `_`. `source` được đặt tên vì kết quả trả về cần thông tin này. Trong switch, các nhánh chỉ cần xác định kiểu nên dùng unnamed pattern.

## 8. Tài liệu tham khảo

- [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Java 22 Language Changes — Oracle](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html)
- [Pattern Matching for switch — Java 22 Language Guide](https://docs.oracle.com/en/java/javase/22/language/pattern-matching-switch.html)
- [Pattern Matching for instanceof — Java 22 Language Guide](https://docs.oracle.com/en/java/javase/22/language/pattern-matching-instanceof.html)
