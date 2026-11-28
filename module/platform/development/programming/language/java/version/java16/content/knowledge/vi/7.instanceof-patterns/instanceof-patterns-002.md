# Gộp kiểm tra kiểu, chuyển kiểu và khai báo biến trong một biểu thức

## 1. Một biểu thức, ba việc liên quan

Khi xử lý một giá trị có kiểu tổng quát như `Object`, chương trình thường cần biết đối tượng thực tế thuộc kiểu nào trước khi gọi các thành viên đặc thù của kiểu đó. Từ Java 16, *pattern matching for `instanceof`* cho phép viết việc kiểm tra kiểu và khai báo biến nhận giá trị đã khớp ngay trong một biểu thức:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Trong `value instanceof String text`, Java thực hiện các việc gắn liền với nhau:

1. Kiểm tra giá trị `value` có thể khớp với kiểu tham chiếu `String` hay không.
2. Nếu khớp, cung cấp biến `text` có kiểu tĩnh là `String`, tham chiếu đến chính đối tượng đã kiểm tra.
3. Cho phép sử dụng `text` ở những vị trí mà luồng điều khiển bảo đảm phép khớp đã thành công.

Biểu thức `instanceof` vẫn cho kết quả kiểu `boolean`. Phần `String text` là *type pattern*: nó mô tả kiểu cần khớp và tên biến được ràng buộc khi khớp thành công. Đây không phải phép tạo đối tượng hay chuyển đổi nội dung sang một đối tượng mới.

Tính năng này được chuẩn hóa từ Java 16 theo JEP 394, không còn là tính năng preview. Cú pháp ổn định này vẫn dùng được trong các phiên bản Java hiện đại.

## 2. Chuyển từ kiểm tra rồi ép kiểu sang type pattern

Trước Java 16, cùng một thao tác thường phải viết thành hai bước:

```java
static String display(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.strip();
    }
    return "Không phải chuỗi";
}
```

Phép kiểm tra và phép ép kiểu cùng nhắc lại kiểu `String`. Với type pattern, có thể gộp thành:

```java
static String display(Object value) {
    if (value instanceof String text) {
        return text.strip();
    }
    return "Không phải chuỗi";
}
```

| Thành phần | Cách viết cũ | Cách viết với type pattern |
| --- | --- | --- |
| Kiểm tra kiểu | `value instanceof String` | `value instanceof String text` |
| Lấy biến có kiểu cụ thể | `(String) value` | Biến `text` được khai báo ngay trong pattern |
| Nơi sử dụng | Sau khi ép kiểu thủ công | Trong phạm vi mà phép khớp được bảo đảm |
| Rủi ro viết mã | Có thể lặp sai kiểu hoặc ép kiểu nhầm giá trị | Trình biên dịch kiểm tra sự phù hợp của pattern và phạm vi biến |

Type pattern giúp giảm lặp và làm rõ mối liên hệ giữa phép kiểm tra với biến sẽ sử dụng. Phép ép kiểu tường minh vẫn có chỗ dùng trong Java, nhưng khi mục đích là kiểm tra một kiểu rồi sử dụng giá trị theo kiểu đó, pattern thường dễ đọc hơn.

## 3. Dùng pattern variable trong biểu thức điều kiện

Pattern variable chỉ khả dụng tại nơi Java chứng minh được nó đã được khởi tạo. Quy tắc này được gọi là *flow scoping*: phạm vi biến được quyết định theo đường đi của luồng điều khiển.

### 3.1. Trong nhánh `if`

```java
static void printValue(Object value) {
    if (value instanceof String text) {
        System.out.println("Độ dài: " + text.length());
    } else {
        System.out.println("Giá trị không phải String");
    }
}
```

Trong nhánh `if`, điều kiện đã đúng nên `text` chắc chắn tham chiếu đến một `String`. Nhánh `else` chạy khi phép khớp thất bại, vì vậy không thể sử dụng `text` ở nhánh đó.

### 3.2. Kết hợp điều kiện với `&&`

```java
static boolean isLongText(Object value) {
    return value instanceof String text && text.length() >= 10;
}
```

`&&` đánh giá vế phải khi vế trái đúng. Do đó, nếu Java đánh giá `text.length()`, phép khớp `String text` đã thành công. Đây là cách viết gọn cho trường hợp cần kiểm tra kiểu rồi kiểm tra thêm nội dung.

Có thể kết hợp nhiều điều kiện sau pattern:

```java
static boolean isUsefulText(Object value) {
    return value instanceof String text
            && !text.isBlank()
            && text.length() <= 100;
}
```

Các điều kiện sau chỉ được đánh giá khi những điều kiện trước đúng; `text` được dùng an toàn trong cả hai vế phải.

### 3.3. Kết hợp phủ định và `||`

Đôi khi cần trả về sớm nếu giá trị không đúng kiểu hoặc không đạt yêu cầu:

```java
static String cleanText(Object value) {
    if (!(value instanceof String text) || text.isBlank()) {
        return "";
    }

    return text.strip();
}
```

Vế phải của `||` chỉ được đánh giá khi vế trái sai. Điều đó đồng nghĩa `value instanceof String text` đã đúng, nên `text` dùng được trong `text.isBlank()`. Nếu không phải chuỗi, nhánh `if` trả về ngay; phần còn lại chỉ chạy với một chuỗi hợp lệ về kiểu.

Không thể đưa pattern variable vào mọi vị trí của một biểu thức logic. Ví dụ sau không biên dịch:

```java
// SAI: vế phải có thể chạy khi phép kiểm tra ở vế trái thất bại.
if (value instanceof String text || text.isBlank()) {
    // ...
}
```

Khi dùng `||`, hãy xem xét trường hợp vế trái sai: nếu trường hợp đó chưa bảo đảm pattern khớp, không được sử dụng biến ở vế phải.

### 3.4. Dùng trong biểu thức điều kiện ba ngôi

Pattern variable cũng có thể được sử dụng trong nhánh đúng của toán tử `?:`:

```java
static String label(Object value) {
    return value instanceof String text
            ? text.strip()
            : String.valueOf(value);
}
```

Nhánh sau dấu `?` chỉ được chọn khi biểu thức `instanceof` đúng, nên `text` hợp lệ ở nhánh đó. Nhánh sau dấu `:` không được sử dụng `text`, vì nó ứng với trường hợp pattern không khớp.

### 3.5. Kiểm tra đầu vào rồi sử dụng ở phần còn lại

```java
static int countCharacters(Object value) {
    if (!(value instanceof CharSequence sequence)) {
        throw new IllegalArgumentException("Cần một giá trị dạng văn bản");
    }

    return sequence.length();
}
```

Sau câu lệnh `if`, mọi đường đi tiếp tục đều đã vượt qua phép kiểm tra. Nếu pattern không khớp, phương thức ném ngoại lệ và kết thúc. Cách viết này giúp phần xử lý chính không phải lồng thêm một cấp điều kiện.

## 4. Kiểu pattern phải tương thích với kiểu biểu thức

Không phải cặp kiểu nào cũng có thể đặt cạnh nhau trong `instanceof`. Kiểu tĩnh của biểu thức và kiểu tham chiếu trong pattern phải có quan hệ tương thích để phép kiểm tra có ý nghĩa.

### 4.1. Kiểm tra kiểu cụ thể từ `Object`

```java
Object value = "Hello";

if (value instanceof String text) {
    System.out.println(text.length());
}
```

`Object` có thể tham chiếu đến một `String`, vì vậy phép kiểm tra hợp lệ. Khi chạy, kết quả phụ thuộc vào đối tượng thực tế mà `value` đang tham chiếu.

### 4.2. Không kiểm tra lại một kiểu đã được biết chắc

```java
String title = "Java";

// Không hợp lệ: với kiểu tĩnh String, pattern String luôn khớp.
// if (title instanceof String text) {
//     System.out.println(text);
// }

System.out.println(title.length());
```

Trình biên dịch từ chối một số pattern luôn đúng vì phép kiểm tra không thể làm thay đổi nhánh thực thi. Hãy dùng trực tiếp biến khi kiểu của nó đã đủ cụ thể.

Một trường hợp khác là kiểm tra một lớp `final` với giao diện mà lớp đó không triển khai. Ví dụ, một biến kiểu `String` không thể khớp với `Runnable`; `String` là lớp `final` và không triển khai giao diện đó. Kiểu tĩnh và quan hệ kế thừa/triển khai quyết định phép kiểm tra có khả thi hay không.

### 4.3. Có thể khớp với giao diện hoặc mảng

```java
static int sizeOf(Object value) {
    if (value instanceof CharSequence sequence) {
        return sequence.length();
    }
    if (value instanceof byte[] bytes) {
        return bytes.length;
    }
    return 0;
}
```

`CharSequence` cho phép xử lý nhiều lớp biểu diễn văn bản, còn `byte[]` là kiểu mảng tham chiếu có thể kiểm tra trực tiếp. Pattern variable mang đúng kiểu đã khai báo trong pattern.

### 4.4. Generic phải dùng kiểu có thể kiểm tra lúc chạy

Java xóa thông tin tham số kiểu generic ở thời điểm chạy (*type erasure*). Vì thế, không thể kiểm tra trực tiếp một kiểu tham số hóa cụ thể như `List<String>`:

```java
Object value = java.util.List.of("Java", "Pattern");

// Không hợp lệ: List<String> không phải kiểu reifiable.
// if (value instanceof java.util.List<String> texts) { ... }

// Hợp lệ: List<?> là kiểu có thể kiểm tra lúc chạy.
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

`List<?> items` chỉ xác nhận giá trị là một danh sách. Nó không khẳng định các phần tử đều là chuỗi. Nếu cần xử lý từng phần tử như `String`, hãy kiểm tra phần tử riêng.

### 4.5. Type pattern trong cú pháp ổn định dùng kiểu tham chiếu

Type pattern của `instanceof` được giới thiệu trong Java 16 áp dụng cho kiểu tham chiếu, như lớp, giao diện và mảng. Không viết pattern kiểu nguyên thủy như `instanceof int number` trong phạm vi cú pháp ổn định của bài học này. Khi cần xử lý một giá trị nguyên thủy thông qua `Object`, hãy nhớ Java dùng lớp bao tương ứng, chẳng hạn `Integer`.

## 5. Pattern variable không tồn tại chỉ vì đã lưu kết quả boolean

Một nhầm lẫn phổ biến là nghĩ rằng sau khi lưu kết quả của `instanceof` vào biến boolean, Java sẽ nhớ mối liên hệ giữa kết quả và pattern variable:

```java
static void example(Object value) {
    // Không hợp lệ: pattern variable không có phạm vi sử dụng ở câu lệnh sau.
    // boolean isText = value instanceof String text;
    // if (isText) {
    //     System.out.println(text.length());
    // }
}
```

Trình biên dịch phân tích luồng điều khiển tại biểu thức pattern; nó không suy luận rằng một biến boolean bất kỳ luôn đại diện cho kết quả của biểu thức đó. Hãy đặt pattern trực tiếp trong điều kiện nơi cần dùng biến:

```java
static void example(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Pattern variable cũng là một biến cục bộ có kiểu cụ thể. Trong Java 16, nó không mặc định là `final`, nhưng việc gán lại thường khiến ý nghĩa của biến khó theo dõi. Nếu cần một giá trị đã chuẩn hóa hoặc biến đổi, hãy tạo biến mới:

```java
if (value instanceof String text) {
    String normalized = text.strip().toLowerCase();
    System.out.println(normalized);
}
```

## 6. Ví dụ thực tế: xử lý dữ liệu đầu vào nhiều kiểu

Một phương thức nhận `Object` có thể dùng type pattern để định tuyến xử lý theo kiểu dữ liệu. Ví dụ dưới đây dùng các kiểu tham chiếu phổ biến và kiểm tra riêng trường hợp `null`:

```java
import java.util.List;

public class ValueFormatter {
    static String format(Object value) {
        if (value == null) {
            return "(không có dữ liệu)";
        }

        if (value instanceof CharSequence text && !text.toString().isBlank()) {
            return "Văn bản: " + text.toString().strip();
        }

        if (value instanceof Number number) {
            return "Số: " + number;
        }

        if (value instanceof List<?> items) {
            return "Danh sách: " + items.size() + " phần tử";
        }

        return "Kiểu chưa hỗ trợ: " + value.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        System.out.println(format("  Java 16  "));
        System.out.println(format(new StringBuilder("Pattern")));
        System.out.println(format(42));
        System.out.println(format(List.of("record", "stream")));
        System.out.println(format(null));
    }
}
```

Kết quả:

```text
Văn bản: Java 16
Văn bản: Pattern
Số: 42
Danh sách: 2 phần tử
(không có dữ liệu)
```

Ví dụ minh họa ba điểm quan trọng: pattern có thể khớp một giao diện như `CharSequence`; điều kiện phụ có thể dùng biến vừa được khai báo; và `List<?>` không giả định kiểu của từng phần tử. Các API trong ví dụ đều có trước hoặc từ Java 16, còn cú pháp type pattern là tính năng chính thức từ Java 16.

## 7. Chọn type pattern đúng chỗ

| Nhu cầu | Cách viết nên ưu tiên |
| --- | --- |
| Kiểm tra một giá trị tổng quát rồi gọi thành viên của kiểu cụ thể | `value instanceof T item` |
| Kiểm tra kiểu và điều kiện nội dung | `value instanceof T item && điềuKiện(item)` |
| Từ chối kiểu không phù hợp ở đầu phương thức | `if (!(value instanceof T item)) return;` |
| Chọn một trong hai cách xử lý để tạo kết quả | Dùng pattern trong nhánh đúng của `?:` |
| Kiểm tra danh sách generic | Dùng `List<?> item`, rồi kiểm tra phần tử nếu cần |
| Nhiều lớp cùng cung cấp một hành vi | Cân nhắc interface và đa hình thay vì liên tục phân nhánh theo kiểu |

Type pattern phù hợp ở ranh giới nơi chương trình nhận dữ liệu tổng quát, tích hợp nhiều kiểu hoặc cần xử lý các biến thể của một giá trị. Nếu một hệ thống thường xuyên phải hỏi đối tượng thuộc lớp nào để quyết định hành vi, thiết kế đa hình qua interface hoặc lớp cơ sở có thể diễn đạt ý định tốt hơn.

**Điểm cốt lõi:** `value instanceof T item` kết hợp phép kiểm tra kiểu với việc ràng buộc một biến có kiểu `T`. Trình biên dịch chỉ cho phép dùng biến tại nơi luồng điều khiển bảo đảm pattern đã khớp; vì vậy có thể bỏ bước ép kiểu thủ công mà vẫn giữ kiểm tra kiểu an toàn.
