# Nhận diện mã instanceof rồi cast thủ công

## 1. Mục tiêu của việc nhận diện

Trong mã Java viết trước khi **pattern matching for `instanceof`** trở thành tính năng chính thức ở Java 16, một mẫu thường gặp là: kiểm tra đối tượng bằng `instanceof`, sau đó ép kiểu bằng toán tử `(Type)` để sử dụng phương thức hoặc thuộc tính của subtype đó.

Ví dụ:

```java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.toUpperCase());
}
```

Đoạn mã trên hợp lệ. Phép thử `value instanceof String` chỉ trả về một giá trị boolean; vì vậy cách viết truyền thống phải có thêm `(String) value` để trình biên dịch coi biến là `String`.

Từ Java 16, **type pattern** kết hợp phép kiểm tra kiểu với việc khai báo biến đã được chuyển kiểu:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

Đầu ra của cả hai đoạn là `JAVA`. Trong ví dụ thứ hai, `text` là biến pattern có kiểu tĩnh `String`, chỉ dùng được ở phần chương trình mà Java biết mẫu đã khớp.

**Mục tiêu refactor** không phải thay mọi phép ép kiểu trong dự án bằng một pattern, mà là **tìm đúng chỗ có trình tự “kiểm tra bằng `instanceof` → ép chính giá trị đã kiểm tra → sử dụng biến kiểu con”**, rồi chuyển đổi sao cho vẫn giữ hành vi, đường đi và quy tắc xử lý `null` của mã gốc.

## 2. Dấu hiệu nhận diện nhanh trong code cũ

Khi đọc một phương thức Java cũ, hãy tìm các cấu trúc sau.

### Mẫu A — kiểm tra rồi ép kiểu ngay trong nhánh

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Mẫu này là ứng viên refactor rõ ràng vì **cùng một biểu thức `value`** vừa được kiểm tra vừa được ép sang cùng kiểu `String`.

Thay bằng:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

### Mẫu B — lặp lại ép kiểu nhiều lần

```java
if (value instanceof String) {
    System.out.println(((String) value).length());
    System.out.println(((String) value).toUpperCase());
}
```

Thay bằng:

```java
if (value instanceof String text) {
    System.out.println(text.length());
    System.out.println(text.toUpperCase());
}
```

Pattern giữ một biến được kiểm tra kiểu và dùng lại nhiều lần, giúp giảm trùng lặp. Trường hợp này thường dễ đọc và dễ sửa hơn so với viết `(String)` ở mỗi lần sử dụng.

### Mẫu C — nhiều nhánh kiểm tra subtype

```java
static String classify(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "String: " + text.length();
    } else if (value instanceof Integer) {
        Integer number = (Integer) value;
        return "Integer: " + number;
    }
    return "Khác";
}
```

Có thể chuyển thành:

```java
static String classify(Object value) {
    if (value instanceof String text) {
        return "String: " + text.length();
    } else if (value instanceof Integer number) {
        return "Integer: " + number;
    }
    return "Khác";
}
```

Các biến `text` và `number` có phạm vi khác nhau, gắn với nhánh tương ứng; chúng không trở thành biến dùng chung bên ngoài chuỗi `if/else if`.

### Mẫu D — kiểm tra phủ định, thoát sớm rồi ép kiểu

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String)) {
        return 0;
    }
    String text = (String) value;
    return text.length();
}
```

Refactor theo *guard clause*:

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

Đây là ứng dụng quan trọng của **flow scoping**. Vì nhánh `if` phủ định kết thúc bằng `return`, tất cả đường đi còn lại đã chứng minh `value` khớp `String`. Trình biên dịch cho phép dùng `text` sau `if`.

Những đoạn trên là **minh họa độc lập**, không có ý định ghép tất cả phương thức trùng tên vào cùng một lớp.

## 3. Quy trình refactor an toàn qua từng bước

Trước khi sửa:

1. **Xác định biểu thức đang được kiểm tra**: một biến `value` hay kết quả lời gọi hàm?
2. **Xác định kiểu kiểm tra** trong `instanceof` và kiểu ép ở dòng tiếp theo.
3. **Đối chiếu chúng có thực sự cùng một đối tượng, cùng kiểu dự kiến không**; tránh giả định chỉ vì tên biến gần giống.
4. **Đọc toàn bộ nhánh và đường thoát**: nhánh `else`, `return`, `throw`, `break`, điều kiện kết hợp `&&`/`||`, xử lý `null`.
5. **Đặt biến pattern vào `instanceof`** và thay những phép ép kiểu tương ứng bằng biến mới.
6. **Biên dịch và chạy test** trên các trường hợp khớp, không khớp, `null` và subtype khác.
7. **Chỉ coi refactor hoàn thành khi hành vi cần bảo toàn vẫn giữ nguyên**, kể cả lỗi hoặc thông báo lỗi quan trọng trong hợp đồng ứng dụng.

Quy trình này hiệu quả vì cú pháp type pattern thường rất đơn giản, nhưng **hợp đồng hành vi của mã cũ** đôi khi không đơn giản.

Ví dụ refactor cơ bản:

```java
// Trước:
if (event instanceof TextEvent) {
    TextEvent textEvent = (TextEvent) event;
    handle(textEvent.text());
}

// Sau:
if (event instanceof TextEvent textEvent) {
    handle(textEvent.text());
}
```

Đây chỉ là ví dụ chuyển đổi cú pháp, giả định `TextEvent` có phương thức `text()`, `event` đã được khai báo và `handle` tồn tại. Mã trên không phải chương trình có thể chạy riêng.

## 4. Flow scoping: vì sao biến pattern không dùng được ở mọi nơi?

Hãy xét điều kiện kết hợp:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Cách viết này hợp lệ vì `&&` đánh giá ngắn mạch. Nếu `value` không phải `String`, Java không đánh giá `text.isBlank()`. Nếu đánh giá được vế phải, biến `text` đã được ràng buộc.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

Đây là **mẫu lỗi có chủ đích**. Vế phải của `||` được xét khi vế trái **sai**, nghĩa là biến `text` chưa được ràng buộc. Refactor từ mã cũ có các điều kiện phức tạp phải tôn trọng quy tắc này; không thể chỉ thay `(String) value` thành một tên biến ở bất kỳ vị trí nào.

Một lỗi khác:

```java
// KHÔNG BIÊN DỊCH:
// if (value instanceof String text) {
//     System.out.println(text.length());
// }
// System.out.println(text.toUpperCase());
```

Ở phía sau `if`, `value` có thể không phải `String` nên biến `text` không nằm trong phạm vi hợp lệ. Muốn sử dụng biến sau phép kiểm tra, hãy để đường đi **không khớp thoát sớm** như ví dụ `lengthOrZero`, hoặc đặt phần xử lý vào trong nhánh khớp.

**Ghi nhớ:** phạm vi của biến pattern phụ thuộc vào những đường thực thi mà trình biên dịch chứng minh pattern đã khớp (*flow scoping*), không đơn thuần phụ thuộc vào vị trí dấu ngoặc nhọn.

## 5. Không chỉ nhìn thấy cast là thay

### 5.1. Kiểu đã kiểm tra khác kiểu đang ép

Ví dụ nguy hiểm:

```java
Object value = Double.valueOf(1.5);

if (value instanceof Number) {
    Integer number = (Integer) value; // ClassCastException khi chạy
    System.out.println(number);
}
```

Mã này **biên dịch được** nhưng ném `ClassCastException` vì `Double` là một `Number` nhưng không phải `Integer`. Không được mô tả nó như một trường hợp `instanceof Number` bảo đảm an toàn cho `(Integer)`.

Nếu nghiệp vụ chỉ xử lý `Integer`, điều kiện đúng cần là:

```java
if (value instanceof Integer number) {
    System.out.println(number);
}
```

Đây là **sửa lỗi logic**, không chỉ là refactor tương đương: với `Double`, mã cũ ném exception, còn mã mới không vào nhánh. Nếu muốn bảo toàn exception theo hợp đồng cũ, phải quyết định và thể hiện nó rõ ràng thay vì âm thầm bỏ qua.

### 5.2. Kiểm tra một biểu thức, ép một biểu thức khác

```java
Object first = "Java";
Object second = 10;

if (first instanceof String) {
    // Không an toàn: second khác first.
    // String text = (String) second;
}
```

Một phép `instanceof` chỉ chứng minh thuộc tính của **giá trị được kiểm tra**, không chứng minh kiểu của biến khác. Trước khi refactor, kiểm tra xem cast có thực sự diễn ra trên cùng giá trị đã vượt qua phép thử hay không.

### 5.3. Gọi phương thức nhiều lần có thể đổi đối tượng

```java
// Ví dụ minh họa, giả định getNext() có thể trả giá trị khác mỗi lần.
// if (getNext() instanceof String) {
//     String text = (String) getNext();
//     use(text);
// }
```

Câu lệnh kiểm tra lần đầu và câu lệnh ép lần sau có thể nhận hai giá trị khác nhau. Đây không phải trường hợp refactor cơ học an toàn.

Một phiên bản dễ suy luận hơn:

```java
Object candidate = getNext();

if (candidate instanceof String text) {
    use(text);
}
```

Đây là **cách viết minh họa**, giả định `getNext()`, `use()` có sẵn; nó không phải chương trình độc lập. Việc lưu kết quả làm cho `getNext()` chỉ được gọi **một lần** thay vì tối đa hai lần, do đó có thể **thay đổi tác dụng phụ hoặc chuỗi giá trị được tiêu thụ**. Cần kiểm tra yêu cầu nghiệp vụ trước khi coi hai phiên bản tương đương.

### 5.4. Ép kiểu không có kiểm tra trước

```java
String text = (String) value;
System.out.println(text.length());
```

Nếu `value` không phải `String`, cast sẽ ném `ClassCastException`; nếu `value == null`, cast cho kết quả `null` rồi lời gọi `length()` sẽ ném `NullPointerException`.

Thay tùy tiện bằng:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

làm thay đổi hành vi lỗi thành **bỏ qua nhánh** khi không khớp. Chỉ thực hiện nếu yêu cầu mới cho phép; nếu đây là mã bắt buộc phải có `String`, có thể giữ cast và thêm thông báo lỗi rõ ràng hoặc dùng API xác nhận điều kiện đầu vào thích hợp.

## 6. Null: giữ cách xử lý chính xác

Cả phép thử truyền thống:

```java
value instanceof String
```

và type pattern:

```java
value instanceof String text
```

đều trả về `false` khi `value == null`. Với mã `if` cũ chỉ có `instanceof` rồi cast trong nhánh đúng, việc chuyển sang type pattern thường bảo toàn cách bỏ qua giá trị `null`.

Nhưng **không nhầm điều đó với việc tất cả dữ liệu của object đều khác null**. Ví dụ:

```java
if (value instanceof TextEvent event) {
    // event khác null, nhưng event.text() có thể null.
    String text = event.text();
    if (text != null && !text.isBlank()) {
        System.out.println(text.toUpperCase());
    }
}
```

Type pattern xác nhận đối tượng `TextEvent`; nó không chứng minh các field/component tham chiếu bên trong đều khác `null`. Kiểm tra `text != null` trước `text.isBlank()` vẫn cần thiết nếu mô hình dữ liệu cho phép chuỗi `null`.

Trong ứng dụng cần phân biệt đối tượng `null` với đối tượng không thuộc kiểu mong muốn, có thể làm rõ bằng một nhánh riêng trước `instanceof`. Đừng mong type pattern tự thay thế toàn bộ quy tắc kiểm tra dữ liệu.

## 7. Ví dụ Java 17+ đầy đủ: trước và sau có cùng đầu ra

Lưu chương trình dưới tên **`LegacyCastRefactorDemo.java`**:

```java
public class LegacyCastRefactorDemo {
    interface Event {}

    static final class TextEvent implements Event {
        private final String text;

        TextEvent(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class CountEvent implements Event {
        private final int count;

        CountEvent(int count) {
            this.count = count;
        }

        int count() {
            return count;
        }
    }

    // Phiên bản cũ: instanceof rồi ép kiểu thủ công.
    static String legacy(Object value) {
        if (value instanceof TextEvent) {
            TextEvent event = (TextEvent) value;
            if (event.text() != null && !event.text().isBlank()) {
                return "TEXT:" + event.text().toUpperCase();
            }
            return "TEXT:EMPTY";
        }

        if (value instanceof CountEvent) {
            CountEvent event = (CountEvent) value;
            return "COUNT:" + (event.count() * 2);
        }

        return "OTHER";
    }

    // Phiên bản mới: type pattern ràng buộc đúng biến.
    static String modern(Object value) {
        if (value instanceof TextEvent event) {
            String text = event.text();
            if (text != null && !text.isBlank()) {
                return "TEXT:" + text.toUpperCase();
            }
            return "TEXT:EMPTY";
        }

        if (value instanceof CountEvent event) {
            return "COUNT:" + (event.count() * 2);
        }

        return "OTHER";
    }

    // Trường hợp điều kiện phủ định rồi kết thúc sớm.
    static String lengthAfterGuard(Object value) {
        if (!(value instanceof TextEvent event)) {
            return "NOT_TEXT";
        }

        String text = event.text();
        return text == null ? "TEXT_NULL" : "LEN:" + text.length();
    }

    public static void main(String[] args) {
        Object[] cases = {
            new TextEvent("java"),
            new TextEvent(" "),
            new TextEvent(null),
            new CountEvent(6),
            "khác",
            null
        };

        for (Object item : cases) {
            System.out.println(legacy(item) + " | " + modern(item));
        }

        System.out.println(lengthAfterGuard(new TextEvent("hello")));
        System.out.println(lengthAfterGuard(new CountEvent(2)));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac LegacyCastRefactorDemo.java
java LegacyCastRefactorDemo
```

Đầu ra chuẩn:

```text
TEXT:JAVA | TEXT:JAVA
TEXT:EMPTY | TEXT:EMPTY
TEXT:EMPTY | TEXT:EMPTY
COUNT:12 | COUNT:12
OTHER | OTHER
OTHER | OTHER
LEN:5
NOT_TEXT
```

Phân tích các trường hợp:

1. `TextEvent("java")` khớp kiểm tra `TextEvent`, chuỗi không trống; cả hai phiên bản trả về `TEXT:JAVA`.
2. `TextEvent(" ")` có chuỗi chỉ gồm khoảng trắng, nên `isBlank()` trả về `true` và cả hai trả về `TEXT:EMPTY`.
3. `TextEvent(null)` vẫn là một đối tượng `TextEvent` hợp lệ. Hàm kiểm tra `null` ở chuỗi bên trong nên cả hai trả về `TEXT:EMPTY`, không ném `NullPointerException`.
4. `CountEvent(6)` được nhận diện đúng kiểu và cho kết quả `COUNT:12`.
5. Chuỗi `"khác"` không phải bất kỳ `Event` nào trong hai nhánh, nên nhận `OTHER`.
6. `null` không khớp bất kỳ `instanceof` nào, nên nhận `OTHER`.
7. `lengthAfterGuard(TextEvent("hello"))` ràng buộc được `event` và tiếp tục sau guard để trả về `LEN:5`.
8. `lengthAfterGuard(CountEvent(2))` không khớp mẫu `TextEvent` và trả về `NOT_TEXT` ngay.

Trong ví dụ, cách refactor không cần sử dụng record pattern hay cú pháp `switch` của Java 21. **Type patterns trong `instanceof` đã là tính năng chính thức từ Java 16**, nên chương trình này chạy được với Java 17 mà không cần `--enable-preview`.

Chú ý: phiên bản `modern` lưu `event.text()` vào biến cục bộ một lần; trong class ví dụ, phương thức `text()` chỉ trả về field nên điều này bảo toàn kết quả. Với accessor hoặc phương thức có tác dụng phụ trong ứng dụng thực tế, cần kiểm tra thêm trước khi thay nhiều lời gọi bằng một lời gọi.

## 8. Khi nào nên giữ cast tường minh?

Pattern matching không nhằm xóa bỏ tất cả ép kiểu:

- **Cast không đi sau kiểm tra `instanceof`** có thể là một phần của hợp đồng “đầu vào phải thuộc kiểu này, nếu không sẽ lỗi”. Không tự đổi sang kiểm tra rồi bỏ qua.
- **Cast trong mã generic/unchecked** cần đánh giá riêng thông tin kiểu và type erasure. Không phải pattern matching nào cũng chứng minh được đối số kiểu generic tại runtime.
- **Cast cần thiết cho một API cụ thể** có thể vẫn có lý do tồn tại; phải hiểu kiểu tĩnh và kiểu kết quả kỳ vọng trước khi bỏ.
- **Ép kiểu số** như `(int) doubleValue` là chuyển đổi giá trị số, không phải `instanceof` kiểm tra subtype rồi cast tham chiếu; không nằm trong phạm vi refactor này.

Mục tiêu là loại bỏ những cast **dư thừa sau phép thử kiểu đã bảo đảm an toàn**, không phải cưỡng ép toàn bộ mã cũ sang một cú pháp duy nhất.

## 9. Checklist khi review một thay đổi

| Câu hỏi | Ý nghĩa |
| --- | --- |
| `instanceof` và cast có nhắm đến đúng **cùng giá trị**? | Tránh kiểm tra một biến nhưng ép biến khác. |
| Kiểu trong `instanceof` và kiểu cast có thống nhất? | Tránh giả định sai về quan hệ kế thừa và kiểu thật. |
| Biểu thức kiểm tra có tác dụng phụ hoặc thay đổi giữa hai lần gọi? | Tránh thay đổi số lần đánh giá mà không có chủ đích. |
| Mã cũ làm gì với giá trị không khớp và `null`? | Bảo toàn nhánh `else`, đường `return` và lỗi có chủ đích. |
| Biến pattern có nằm trong flow scope hợp lệ? | Đặc biệt quan trọng với `&&`, `||`, phủ định và guard clause. |
| Có test cho các subtype khác nhau? | Tránh refactor chỉ đúng với một mẫu dữ liệu. |
| Có xử lý `null` bên trong object khi cần? | `instanceof` không kiểm tra mọi field hay component. |
| Phiên bản Java của dự án đã hỗ trợ type pattern chưa? | Java 16+ hỗ trợ chính thức; Java 17 là nền tảng ổn định cho ví dụ. |

**Ghi nhớ:** Dấu hiệu quan trọng của mã cần refactor là **`instanceof T` kiểm tra một giá trị rồi `(T)` ép chính giá trị đó** trong nhánh đã khớp. Hãy thay bằng **`instanceof T variable`**, dùng biến pattern trong phạm vi hợp lệ và kiểm tra kỹ `null`, subtype, nhánh điều khiển, tác dụng phụ cùng hành vi lỗi. Một bản refactor tốt **giảm cast nhưng vẫn giữ đúng ý nghĩa của chương trình**.
