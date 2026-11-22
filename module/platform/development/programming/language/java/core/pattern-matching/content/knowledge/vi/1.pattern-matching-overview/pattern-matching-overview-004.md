# Khác biệt giữa pattern matching và ép kiểu thủ công trong Java

## 1. Cùng một nhu cầu, hai cách viết

Khi một biến có kiểu khai báo rộng như `Object`, chương trình đôi khi cần kiểm tra đối tượng thực tế thuộc kiểu nào rồi dùng các thành viên riêng của kiểu đó. Trong Java, hai cách thường gặp là:

- **Kiểm tra kiểu rồi ép kiểu thủ công:** dùng `instanceof` để kiểm tra, sau đó viết phép ép `(Type) value` và gán kết quả vào biến có kiểu cụ thể.
- **Pattern matching cho `instanceof`:** dùng `value instanceof Type name` để kiểm tra kiểu và khai báo biến đã có kiểu cụ thể ngay trong cùng biểu thức.

Ví dụ, với `Object value` có thể chứa một `String`:

```java
// Cách cũ: kiểm tra và ép kiểu là hai thao tác viết riêng.
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}

// Pattern matching: kiểm tra và gắn biến text cùng lúc.
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Đây là hai **đoạn mã minh họa đặt trong một phương thức có biến `value`**. Khi điều kiện đúng, cả hai đều dùng cùng đối tượng `String`; pattern matching không sao chép hoặc chuyển đổi nội dung chuỗi. Khác biệt chính nằm ở cú pháp, quan hệ giữa phép kiểm tra kiểu và biến được dùng, cũng như cách trình biên dịch quản lý phạm vi biến.

## 2. Ví dụ Java 17 hoàn chỉnh: kết quả tương đương

Lưu chương trình sau trong tệp `PatternVsManualCast.java`:

```java
public class PatternVsManualCast {
    static String manual(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "String: " + text.toUpperCase();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Integer: " + (number + 1);
        }
        return "Other";
    }

    static String pattern(Object value) {
        if (value instanceof String text) {
            return "String: " + text.toUpperCase();
        }
        if (value instanceof Integer number) {
            return "Integer: " + (number + 1);
        }
        return "Other";
    }

    public static void main(String[] args) {
        Object[] inputs = {"java", 41, null, 3.5};
        for (Object input : inputs) {
            System.out.println(manual(input) + " | " + pattern(input));
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac PatternVsManualCast.java
java PatternVsManualCast
```

Kết quả chuẩn (stdout):

```text
String: JAVA | String: JAVA
Integer: 42 | Integer: 42
Other | Other
Other | Other
```

Giải thích từng trường hợp:

- `"java"` là `String`: cả hai nhánh đều gọi `toUpperCase()` và nhận `"JAVA"`.
- `41` được tự động đóng hộp thành `Integer` khi đưa vào mảng `Object[]`: hai cách đều cộng 1 và cho `42`.
- `null`: mọi phép kiểm tra `instanceof` ở trên đều cho `false`, nên trả về `"Other"`; pattern matching không tự động xử lý `null` như một `String`.
- `3.5` là `Double`: không khớp `String` hay `Integer`, nên trả về `"Other"`.

Bài học ở đây là **pattern matching đơn giản hóa đoạn mã kiểm tra kiểu**, chứ không tự thay đổi quy tắc chọn nhánh hay kết quả nghiệp vụ.

## 3. So sánh theo từng khía cạnh

| Khía cạnh | `instanceof` + ép kiểu thủ công | Pattern matching cho `instanceof` |
| --- | --- | --- |
| Cú pháp | `if (x instanceof T) { T t = (T) x; ... }` | `if (x instanceof T t) { ... }` |
| Kiểm tra kiểu ở runtime | `instanceof` kiểm tra trước; phép cast tường minh xuất hiện riêng | `instanceof T t` kiểm tra và chỉ gắn `t` khi khớp |
| Sai sót do cast | Có thể viết nhầm kiểu/biến trong phép cast hoặc bỏ qua kiểm tra | Không cần viết lại phép cast sau khi pattern đã khớp |
| Kiểu tĩnh của biến sử dụng | Biến `t` nhận kiểu `T` từ khai báo và cast | Biến pattern `t` có kiểu `T` ngay sau khi khớp |
| Phạm vi biến | Biến cục bộ tuân theo khối khai báo thông thường | Biến pattern có **phạm vi phụ thuộc luồng điều khiển** (flow scoping) |
| `null` | `null instanceof T` là `false` | `null instanceof T t` cũng là `false` |
| Mục tiêu chính | Hữu ích trong mã cũ hoặc chỗ thực sự cần cast tường minh | Giảm lặp và giúp biểu đạt ý định kiểm tra kiểu rõ hơn |
| Hiệu năng | Phụ thuộc mã và JVM | Không có bảo đảm luôn nhanh hơn; không nên chọn chỉ vì kỳ vọng tăng tốc |

**Lưu ý về an toàn:** phép cast tường minh *sau một kiểm tra `instanceof` đúng kiểu* vẫn an toàn trong nhánh tương ứng. Không nên nói rằng mọi cách ép kiểu thủ công đều sai, hoặc rằng pattern matching ngăn được mọi `ClassCastException` trong một chương trình. Pattern matching loại bỏ một điểm dễ nhầm ở chính đoạn kiểm tra và dùng kiểu này.

## 4. Flow scoping: khác biệt quan trọng hơn việc viết ngắn

Trong `if (value instanceof String text)`, `text` chỉ có thể dùng ở những đường đi mà trình biên dịch chứng minh pattern đã khớp.

### Dùng với `&&`

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

Đoạn này hợp lệ bên trong phương thức có `Object value`. Toán tử `&&` đánh giá từ trái sang phải và dừng khi vế trái sai. Vì vậy, nếu JVM cần đánh giá `!text.isBlank()` thì `value` chắc chắn đã khớp `String text`.

Ngược lại, đoạn sau **không biên dịch**:

```java
if (value instanceof String text || text.isBlank()) {
    System.out.println("invalid");
}
```

Khi vế trái của `||` sai, vế phải vẫn phải chạy, nhưng khi ấy `text` chưa được gắn giá trị. Trình biên dịch không cho phép dùng biến pattern ở vị trí này.

### Có thể dùng biến sau kiểm tra phủ định nếu nhánh không khớp kết thúc

```java
static int lengthOrMinusOne(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Hàm trên hợp lệ ở Java 17: sau `if`, đường đi còn lại chỉ có thể là đường `value` đã khớp `String`. Trái lại, với cấu trúc `if (value instanceof String text) { ... } else { ... }`, không được dùng `text` trong nhánh `else` của kiểm tra dương.

**Kiểu khai báo ban đầu không tự thay đổi:** nếu `value` được khai báo là `Object` thì nó vẫn có kiểu tĩnh `Object`; biến `text` mới là tham chiếu có kiểu `String` để gọi trực tiếp các phương thức như `length()` hay `isBlank()`.

## 5. Các lỗi và hiểu nhầm thường gặp

### Ép kiểu trực tiếp không có kiểm tra phù hợp

```java
Object value = Integer.valueOf(7);
String text = (String) value; // ClassCastException khi chạy
```

Đoạn mã biên dịch được vì `value` có kiểu tĩnh `Object`, nhưng đối tượng thật là `Integer` nên cast sang `String` thất bại. Dùng `if (value instanceof String text)` để thực hiện logic chỉ khi đúng kiểu sẽ tránh sai sót này trong nhánh ấy.

### Nhầm pattern matching với chuyển đổi giá trị

`instanceof Integer number` không chuyển chuỗi `"42"` thành số `42`. Nếu cần chuyển dữ liệu, đó là công việc khác, ví dụ `Integer.parseInt("42")`. Pattern matching kiểm tra kiểu thực của tham chiếu, không phân tích hoặc chuyển đổi dữ liệu.

### Dùng kiểu generic không thể kiểm tra đầy đủ khi chạy

Vì **type erasure**, không thể dùng `instanceof java.util.List<String> list` để xác nhận tham số kiểu `String` ở runtime. Khi cần nhận biết một danh sách, có thể viết:

```java
if (value instanceof java.util.List<?> items) {
    System.out.println("Size: " + items.size());
}
```

Cú pháp này xác nhận `value` là `List`, nhưng **không** khẳng định mỗi phần tử là `String`. Muốn kiểm tra phần tử thì phải kiểm tra chúng riêng hoặc thiết kế API có kiểu chặt chẽ từ đầu.

### Lạm dụng `instanceof` cho mọi bài toán

Nếu API đã cung cấp kiểu tĩnh đúng, không cần kiểm tra lại kiểu hoặc cast. Nếu cần hành vi khác nhau theo từng lớp trong một hệ thống hướng đối tượng, hãy cân nhắc đa hình (ghi đè phương thức) hoặc generic trước khi xây chuỗi dài `if/else if instanceof`. Pattern matching làm nhánh kiểm tra kiểu dễ đọc hơn, nhưng không thay thế thiết kế kiểu dữ liệu phù hợp.

### Lẫn lộn các phiên bản Java

**Pattern matching cho `instanceof` được chuẩn hóa từ Java 16**, nên ví dụ trong bài dùng trực tiếp với Java 17, không cần `--enable-preview`. Pattern matching cho `switch` là tính năng khác, được chuẩn hóa ở Java 21; không sao chép cú pháp `switch` pattern mới vào một dự án Java 17 rồi kỳ vọng nó hoạt động như cú pháp `instanceof` trong bài.

## 6. Chọn cách nào trong thực tế?

Ưu tiên `if (x instanceof Type name)` khi bạn cần kiểm tra kiểu runtime và ngay sau đó dùng đối tượng ở kiểu cụ thể: biểu thức gọn, tránh lặp cast, và trình biên dịch quản lý biến theo đường đi đã khớp.

Vẫn có thể gặp ép kiểu tường minh trong mã cũ, khi tương tác với API trả về `Object`, hoặc tại vị trí mà hợp đồng chương trình đã bảo đảm kiểu và người viết chủ đích dùng cast. Trong những trường hợp ấy, phải hiểu rằng cast sai sẽ gây `ClassCastException`; nếu kiểu chưa chắc chắn, kiểm tra trước hoặc thiết kế lại kiểu dữ liệu thường dễ bảo trì hơn.

**Tự kiểm tra:** với `Object x = "abc";`, biểu thức `x instanceof String s && s.length() == 3` nhận giá trị `true` và có thể dùng `s` ở vế phải; với `Object x = null;`, điều kiện nhận `false` và vế phải không được đánh giá. Điều này minh họa đồng thời việc kiểm tra kiểu, gắn biến và đánh giá ngắn mạch.

**Kết luận:** ép kiểu thủ công buộc bạn tự nối phép kiểm tra với phép cast; pattern matching gắn chúng trong một biểu thức và bổ sung flow scoping. Khi cùng kiểm tra và xử lý đúng kiểu, hai cách có thể cho kết quả hoàn toàn giống nhau.