# Pattern matching khác với statement execution trong Java

## 1. Hai việc khác nhau: khớp mẫu và chạy lệnh

Trong Java, **pattern matching** (khớp mẫu) trả lời câu hỏi “giá trị này có phù hợp với mẫu được khai báo không; nếu phù hợp thì lấy ra những biến nào?”. **Statement execution** (thực thi câu lệnh) là việc chương trình thực sự chạy các câu lệnh như gán biến, gọi phương thức, in kết quả, `return` hoặc `throw` theo luồng điều khiển.

Ví dụ Java 17:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Ở đây có ba vai trò cần phân biệt:

1. `String text` là **type pattern**: mô tả kiểu cần khớp và tên biến nhận giá trị khi khớp.
2. `value instanceof String text` là **biểu thức kiểm tra pattern**: đánh giá `value`, kiểm tra kiểu thực tế; khi phù hợp thì gắn `text`, và biểu thức nhận giá trị `true`.
3. `if (...) { ... }` là **câu lệnh điều khiển luồng**: khi điều kiện là `true`, Java mới thực thi câu lệnh `System.out.println(...)` ở nhánh thân.

**Pattern khớp không đồng nghĩa một câu lệnh bất kỳ được tự động chạy.** Pattern không chứa hành động “in”, “gọi service” hoặc “lưu dữ liệu”. Hành động nằm trong thân `if`, một nhánh `switch` hoặc câu lệnh khác do lập trình viên viết.

Ví dụ trên giả định `value` đã được khai báo trong phạm vi chứa đoạn mã. Nếu `value` không phải `String` hoặc bằng `null`, điều kiện `instanceof` là `false` và câu lệnh in không chạy.

## 2. Một pattern được sử dụng trong biểu thức; statement quyết định điều gì sẽ chạy

### Pattern không phải câu lệnh đứng độc lập

Trong Java 17, type pattern như `String text` không tự nó là một statement. Cấu trúc kiểm tra đúng là:

```java
boolean hasText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Đây là một **phương thức hoàn chỉnh về mặt logic, được đặt trong một lớp**. `instanceof` và `&&` tạo ra giá trị Boolean để câu lệnh `return` trả về. Nếu `value` là chuỗi rỗng hoặc toàn khoảng trắng, pattern `String text` có thể khớp nhưng *toàn bộ điều kiện* vẫn cho `false` vì `!text.isBlank()` sai.

Ngược lại, dòng sau không phải một expression statement hợp lệ trong Java:

```java
value instanceof String text; // Lỗi biên dịch: not a statement
```

Lý do là biểu thức so sánh kiểu không thuộc nhóm biểu thức được phép đứng một mình thành Java expression statement. Đặt nó ở nơi cần biểu thức Boolean, như điều kiện `if`, toán tử `&&`, phép gán Boolean hoặc `return`, mới có ý nghĩa về cú pháp.

### Kiểm tra pattern và thực thi thân `if` là hai bước

```java
if (value instanceof String text && text.length() >= 4) {
    System.out.println("Đủ dài: " + text);
} else {
    System.out.println("Không thỏa điều kiện");
}
```

Có **ba trường hợp khác nhau**:

- Nếu `value` là `"java"`, pattern khớp và điều kiện độ dài đúng: chạy nhánh đầu.
- Nếu `value` là `"hi"`, pattern **vẫn khớp**, nhưng điều kiện độ dài sai: chạy `else`.
- Nếu `value` là `42` hoặc `null`, pattern không khớp: vế phải của `&&` không được đánh giá; chạy `else`.

Vì vậy, đừng dùng “pattern match thành công” và “thân `if` được chạy” như hai khái niệm đồng nghĩa khi điều kiện còn chứa các phép kiểm tra khác.

## 3. Chương trình Java 17 chạy được: quan sát từng bước

Tạo tệp `PatternMatchingVsExecution.java`:

```java
public class PatternMatchingVsExecution {
    private static int reads = 0;

    static Object read(Object input) {
        reads++;
        System.out.println("read " + reads);
        return input;
    }

    static void inspect(Object input) {
        boolean typeMatch = input instanceof String;
        System.out.println("typeMatch=" + typeMatch);

        if (read(input) instanceof String text && text.length() >= 4) {
            System.out.println("THEN " + text.toUpperCase());
        } else {
            System.out.println("ELSE");
        }
    }

    public static void main(String[] args) {
        inspect("java");
        inspect("hi");
        inspect(7);
        inspect(null);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac PatternMatchingVsExecution.java
java PatternMatchingVsExecution
```

Stdout chính xác:

```text
typeMatch=true
read 1
THEN JAVA
typeMatch=true
read 2
ELSE
typeMatch=false
read 3
ELSE
typeMatch=false
read 4
ELSE
```

Giải thích:

- `typeMatch` chỉ ghi nhận kết quả kiểm tra kiểu. Nó không quyết định câu lệnh `THEN` hay `ELSE` vì câu lệnh `if` phía sau còn có điều kiện độ dài.
- `read(input)` là **lời gọi phương thức** và thực sự thực thi các statement trong `read` (tăng bộ đếm, in `read N`). Biểu thức ở vế trái của `instanceof` được đánh giá một lần cho mỗi lượt `inspect`.
- Sau khi `read` trả về, `instanceof String text` kiểm tra đối tượng trả về. Chỉ khi khớp thì `text` mới có thể được sử dụng ở vế phải `&&`.
- Với `"hi"`, `typeMatch=true` chứng minh kiểm tra kiểu thành công, nhưng câu lệnh `THEN` không được thực thi do `text.length() >= 4` sai.
- Với `7` và `null`, kiểm tra kiểu thất bại. Nhờ đánh giá ngắn mạch của `&&`, Java không cố gọi `length()` trên một biến chưa được gắn.

**Lưu ý về side effect:** mẫu kiểm tra kiểu không tự gọi `println`, nhưng **biểu thức cung cấp giá trị cho pattern có thể có side effect**; ở đây `read(input)` chạy trước khi kiểm tra pattern. Các biểu thức kiểm tra bổ sung (ví dụ một lời gọi phương thức trong `&&`) cũng có thể có side effect. Không nên nói rằng “một biểu thức pattern matching không bao giờ có side effect” khi bản thân toán hạng hoặc điều kiện xung quanh có thể thực thi mã.

## 4. Flow scoping: biến chỉ dùng được trên đường đi đã khớp

Pattern matching không chỉ rút ngắn phép ép kiểu. Trình biên dịch Java còn theo dõi **những vị trí mà việc khớp pattern chắc chắn đã thành công**.

### Hợp lệ: `&&`

```java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.charAt(0));
}
```

Khi Java đánh giá vế phải của `&&`, vế trái đã là `true`. Biến `text` chắc chắn đã được gắn giá trị kiểu `String`, nên được phép sử dụng.

### Không hợp lệ: `||` như sau

```java
if (value instanceof String text || text.isEmpty()) {
    System.out.println("X");
}
```

Đoạn này **không biên dịch**: vế phải của `||` được đánh giá khi vế trái `false`; ở đường đi đó, pattern không khớp nên `text` không nằm trong phạm vi được phép dùng.

### Hợp lệ: nhánh không khớp đã kết thúc bằng `return`

```java
static int safeLength(Object value) {
    if (!(value instanceof String text)) {
        return -1;
    }
    return text.length();
}
```

Nếu điều khiển đến được `return text.length()`, nhánh không khớp đã kết thúc. Trình biên dịch chứng minh rằng `text` đã được gắn. Vì thế mã này hợp lệ trong Java 17.

Đối chiếu với khai báo biến thông thường:

```java
String text = (String) value;
System.out.println(text.length());
```

Ở đây phép cast và khai báo là các phần của **statement khai báo biến** được thực thi khi luồng chạy đến. Nếu `value` là `Integer`, phép cast có thể ném `ClassCastException`. Với `if (value instanceof String text)`, kiểm tra kiểu và gắn biến thuộc biểu thức điều kiện, nên thân `if` chỉ chạy khi đã khớp.

## 5. Pattern matching trong `switch`: chọn nhánh rồi mới thực thi

Từ **Java 21**, pattern matching cho `switch` là tính năng chính thức. Ở đây việc phân biệt còn rõ hơn:

- `case String text` là pattern dùng để **xác định case nào phù hợp**.
- `when ...` (nếu có) là điều kiện bảo vệ cần thỏa sau khi pattern kiểu đã khớp.
- Phần bên phải `->` là **hành động của nhánh** được chọn. Với `switch` statement, đó có thể là một statement gọi phương thức hoặc một khối lệnh.

Ví dụ Java 21, đặt trong tệp `PatternSwitchVsExecution.java`:

```java
public class PatternSwitchVsExecution {
    static void describe(Object value) {
        switch (value) {
            case null ->
                System.out.println("NULL");
            case String text when text.isBlank() ->
                System.out.println("BLANK");
            case String text ->
                System.out.println("STRING " + text.length());
            case Integer number ->
                System.out.println("INT " + number);
            default ->
                System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        describe("abc");
        describe("");
        describe(12);
        describe(null);
        describe(1.5);
    }
}
```

Lệnh chạy với **JDK 21 trở lên**:

```bash
javac PatternSwitchVsExecution.java
java PatternSwitchVsExecution
```

Stdout:

```text
STRING 3
BLANK
INT 12
NULL
OTHER
```

Với chuỗi rỗng, pattern `String text` khớp; guard `text.isBlank()` đúng, vì vậy nhánh `BLANK` chạy. Với chuỗi `"abc"`, guard sai, Java xét tiếp nhánh `case String text` và chạy `STRING 3`. Hai nhánh này đều chứa pattern kiểu `String`, nhưng chỉ có **một nhánh được thực thi** vì `switch` quyết định nhánh và cú pháp `->` không fall through.

Thứ tự case có ý nghĩa: đặt `case String text ->` (không guard) trước `case String text when text.isBlank() ->` sẽ khiến case có guard bị che khuất và có thể gây lỗi biên dịch do case bị bao phủ (dominated). `case null` được xử lý riêng; trái lại, `null instanceof String text` luôn `false`.

**Phân biệt phiên bản:** pattern matching cho `instanceof` chính thức từ **Java 16**; ví dụ `if` ở trên dùng Java 17. Cú pháp `case String text` và `when` trong `switch` chỉ dùng trực tiếp như ví dụ với **Java 21 trở lên**. Không dùng nguyên ví dụ `switch` này để biên dịch với `javac` Java 17 ở chế độ bình thường.

## 6. Bảng đối chiếu hai khái niệm

| Khía cạnh | Pattern matching | Statement execution |
| --- | --- | --- |
| Vai trò | Thử một giá trị với pattern; gắn biến nếu khớp | Chạy một câu lệnh hoặc khối lệnh khi luồng điều khiển tới đó |
| Ví dụ | `value instanceof String text`; `case String text` | `if (...) { println(...); }`; `return`; thân nhánh `switch` |
| Kết quả trực tiếp | Với `instanceof`: `true`/`false` và ràng buộc biến; với `switch`: pattern góp phần chọn case | Có thể gọi phương thức, thay đổi trạng thái, in ra màn hình, trả về giá trị hoặc ném lỗi |
| Khi không khớp | Không gắn biến pattern cho đường đi đó | Câu lệnh ở nhánh tương ứng có thể không chạy; `else`/case khác có thể chạy |
| Phạm vi biến | Phụ thuộc đường đi mà trình biên dịch chứng minh match thành công | Biến khai báo thông thường theo phạm vi khối và quy tắc definite assignment |
| Tính độc lập | Pattern cần ngữ cảnh cú pháp như `instanceof` hoặc nhãn `case` | Statement là cấu trúc thực thi được Java cho phép trong vị trí statement |
| Side effect | Bản thân kiểm tra kiểu/gắn biến không yêu cầu lệnh tác động bên ngoài; biểu thức đầu vào hoặc guard có thể có side effect | Phụ thuộc hành động cụ thể: có thể có hoặc không có side effect |

**Chú ý:** `switch` cũng có dạng *switch expression*, trong đó nhánh được chọn tạo ra một giá trị (có thể dùng `yield` trong nhánh khối). Ngay cả khi kết quả là giá trị biểu thức thay vì lệnh in, pattern vẫn chỉ quyết định điều kiện phù hợp; hành vi của nhánh được quyết định bởi cấu trúc `switch`.

## 7. Các hiểu nhầm cần tránh

1. **“Match thành công thì luôn chạy thân `if`.”** Sai khi điều kiện có `&&`, guard hoặc phép kiểm tra bổ sung. Match có thể đúng nhưng điều kiện tổng vẫn sai.
2. **“`String text` là một lệnh ép kiểu tự chạy độc lập.”** Sai. Đây là pattern xuất hiện trong ngữ cảnh cho phép; `text` chỉ được sử dụng trên đường đi match thành công. Nó không phải một statement cast tách rời.
3. **“Pattern matching tự gọi phương thức xử lý tương ứng.”** Sai. Các lời gọi `println`, thao tác ghi file hoặc nghiệp vụ phải được viết trong statement/biểu thức được chọn.
4. **“Mọi biểu thức liên quan đến pattern matching không có side effect.”** Sai nếu toán hạng là lời gọi phương thức, hoặc điều kiện bảo vệ có lời gọi gây tác động. Cần đánh giá các biểu thức đó theo quy tắc thực thi bình thường của Java.
5. **“Pattern matching cũng giống regex hoặc cơ chế chạy script.”** Không. `instanceof String text` là **type pattern** dựa trên kiểu đối tượng; nó không diễn giải chuỗi theo regex và không tạo luồng thực thi tùy ý.
6. **“`null` được xem như khớp mọi kiểu tham chiếu.”** Sai với `instanceof`. `switch` pattern trên Java 21 có thể có `case null` riêng.
7. **“Có pattern nghĩa là có thêm tốc độ thực thi.”** Không có bảo đảm tăng tốc chung. Lợi ích chính của cú pháp là biểu đạt kiểm tra kiểu, gắn biến và phạm vi rõ hơn; hiệu năng thực tế phụ thuộc mã và JVM.

## 8. Cách tư duy khi đọc hoặc viết mã

Khi gặp một đoạn có pattern, đọc theo trình tự sau:

1. **Giá trị nào được đánh giá?** Ví dụ, `read(input)` được gọi trước phép kiểm tra kiểu.
2. **Pattern thử điều kiện gì?** Ví dụ, `String text` khớp khi giá trị là đối tượng phù hợp với kiểu `String` và không phải `null`.
3. **Khi khớp, biến nào được dùng ở đâu?** Xác định phạm vi dựa trên flow scoping, `&&` và các nhánh điều khiển.
4. **Điều kiện tổng hoặc guard còn yêu cầu gì?** Matching đúng chưa chắc cả điều kiện đã đúng.
5. **Cấu trúc `if`/`switch` chọn hành động nào?** Chỉ từ đây mới xác định được câu lệnh nào thực sự chạy và có side effect hay không.

Ví dụ tự kiểm tra:

```java
Object value = "hi";
if (value instanceof String text && text.length() > 3) {
    System.out.println("A");
} else {
    System.out.println("B");
}
```

Kết quả là `B`. `String text` **đã match**, nhưng điều kiện `text.length() > 3` sai nên **statement trong nhánh `else` được thực thi**. Đây chính là sự khác biệt cốt lõi giữa **khớp pattern** và **thực thi statement** trong Java.