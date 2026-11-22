# Vì sao bỏ qua giá trị trả về dễ làm mất kết quả khi làm việc với `String`?

## 1. Vấn đề: gọi phương thức thành công nhưng chuỗi vẫn như cũ

Hãy quan sát đoạn mã sau (đặt bên trong một phương thức Java):

```java
String text = "  java  ";
text.trim();
System.out.println("[" + text + "]");
```

**Kết quả:**

```text
[  java  ]
```

Nhiều người mới học dự đoán sẽ nhận được `[java]` vì đã gọi `trim()`. Thực tế, lời gọi `text.trim()` **đã tính ra kết quả loại bỏ khoảng trắng**, nhưng chương trình không lưu, truyền đi hoặc sử dụng kết quả trả về ấy. Biến `text` vì vậy vẫn tham chiếu đến chuỗi ban đầu `"  java  "`.

Đây là hệ quả trực tiếp của **tính bất biến (immutability)** của `String`: một đối tượng `String` đã được tạo ra thì nội dung của chính đối tượng đó không bị các phương thức như `trim()`, `replace()` hoặc `toUpperCase()` chỉnh sửa tại chỗ.

Bài học trọng tâm: **Gọi một phương thức trả về `String` không đồng nghĩa với cập nhật biến đang giữ chuỗi. Muốn nhận kết quả biến đổi, phải sử dụng giá trị trả về.**

## 2. Giá trị kết quả có thể bị bỏ ở hai phía của một lời gọi

Lỗi không chỉ xuất hiện ở `text.strip();`. Hàm xử lý có thể trả đúng giá trị, nhưng **bên gọi** lại bỏ kết quả:

```java
public class ReturnValueBoundaryDemo {
    static String clean(String value) {
        return value.strip();       // Hàm trả kết quả đã xử lý
    }

    public static void main(String[] args) {
        String raw = "  Java  ";
        clean(raw);                 // Bỏ kết quả: raw không thay đổi
        String display = clean(raw);
        System.out.println("raw=[" + raw + "]");
        System.out.println("display=[" + display + "]");
    }
}
```

Đoạn mã chạy trên JDK 17+ và in `raw=[  Java  ]` rồi `display=[Java]`.

Nếu cần cập nhật biến, dùng `raw = clean(raw);`; nếu cần giữ bản gốc, dùng biến khác. Dùng trực tiếp cũng là dùng kết quả hợp lệ, ví dụ `System.out.println(clean(raw));`. Không phải **mọi** giá trị trả về đều buộc phải gán; câu hỏi là kết quả có đi đến nơi tiêu thụ đúng với mục tiêu hay không.

Khi review, lần theo đường đi **đầu vào → giá trị trả về → người tiêu thụ**. Một phương thức có thể tính đúng nhưng bị bỏ mất ở caller; một caller có thể gán đúng nhưng phương thức tiện ích bên trong lại trả về đầu vào cũ. Đây là hai vị trí lỗi cần kiểm tra độc lập.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu toàn bộ nội dung dưới đây vào tệp **`StringReturnValueDemo.java`**:

```java
import java.util.Locale;

public class StringReturnValueDemo {
    public static void main(String[] args) {
        String original = "  java core  ";

        // Những kết quả này đều bị bỏ qua.
        original.trim();
        original.toUpperCase(Locale.ROOT);
        original.replace("core", "string");

        System.out.println("Sau khi bỏ qua: [" + original + "]");

        // Lấy kết quả trả về của từng phép biến đổi.
        String normalized = original.trim()
                .toUpperCase(Locale.ROOT)
                .replace("CORE", "STRING");

        System.out.println("Kết quả được dùng: [" + normalized + "]");
        System.out.println("Chuỗi gốc: [" + original + "]");

        String word = "Java";
        word.concat(" 21");
        System.out.println("concat bị bỏ qua: " + word);

        word = word.concat(" 21");
        System.out.println("concat đã gán lại: " + word);
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 StringReturnValueDemo.java
java StringReturnValueDemo
```

**Stdout chính xác:**

```text
Sau khi bỏ qua: [  java core  ]
Kết quả được dùng: [JAVA STRING]
Chuỗi gốc: [  java core  ]
concat bị bỏ qua: Java
concat đã gán lại: Java 21
```

Giải thích từng giai đoạn:

1. Ba lời gọi `trim()`, `toUpperCase(Locale.ROOT)` và `replace(...)` đầu tiên đều tính toán kết quả nhưng không thay đổi biến `original`, nên khi in vẫn còn hai dấu cách ở mỗi đầu và vẫn là `java core` viết thường.
2. Chuỗi phương thức `original.trim().toUpperCase(Locale.ROOT).replace("CORE", "STRING")` **truyền giá trị trả về** của mỗi bước sang bước tiếp theo. Kết quả cuối là `"JAVA STRING"`, được lưu vào `normalized`.
3. `original` vẫn là `"  java core  "` vì tạo và lưu một kết quả biến đổi khác không sửa đối tượng gốc.
4. `word.concat(" 21")` bị bỏ qua nên `word` vẫn là `"Java"`. Sau `word = word.concat(" 21")`, biến `word` tham chiếu đến giá trị `"Java 21"`.

Dùng `Locale.ROOT` trong ví dụ giúp thao tác chữ hoa có quy tắc độc lập với ngôn ngữ mặc định của máy chạy. Điều này có ích cho dữ liệu kỹ thuật, mã định danh hoặc kết quả cần nhất quán; khi xử lý văn bản cho một ngôn ngữ cụ thể, có thể cần `Locale` phù hợp.

## 4. Chaining: vì sao chuỗi phương thức vẫn có thể mất kết quả?

Đây là **method chaining**: mỗi phương thức nhận đối tượng `String` được trả về ở bước trước.

```java
String input = "  Hello Java  ";
String result = input.strip().replace(" ", "-").toLowerCase(java.util.Locale.ROOT);
System.out.println(result); // hello-java
```

Nếu chỉ viết:

```java
input.strip().replace(" ", "-").toLowerCase(java.util.Locale.ROOT);
```

thì kết quả cuối vẫn **bị bỏ đi**: chaining không tự động ghi ngược kết quả vào `input`. Các kết quả trung gian có thể đã được dùng làm đối tượng nhận ở bước tiếp theo, nhưng bước cuối cần một nơi tiêu thụ giá trị, chẳng hạn phép gán, `return`, đối số truyền sang phương thức khác hoặc phép so sánh.

Để trả kết quả từ một phương thức xử lý:

```java
static String normalize(String source) {
    return source.strip().toLowerCase(java.util.Locale.ROOT);
}
```

Và **phía gọi** cũng phải sử dụng giá trị trả về:

```java
String normalized = normalize("  JAVA  "); // "java"
```

Chỉ gọi `normalize("  JAVA  ");` như một câu lệnh độc lập cũng sẽ bỏ qua chuỗi đã xử lý.

## 5. Tình huống lỗi thực tế và cách sửa

### Tình huống 1: chuẩn hóa đầu vào trước khi kiểm tra

**Sai:**

```java
String role = "  ADMIN  ";
role.strip();
if (role.equals("ADMIN")) {
    System.out.println("Quyền quản trị");
}
```

Điều kiện không đúng vì `role` vẫn là `"  ADMIN  "`.

**Đúng:**

```java
String role = "  ADMIN  ";
role = role.strip();
if (role.equals("ADMIN")) {
    System.out.println("Quyền quản trị");
}
```

Chú ý: đây chỉ là minh họa kiểm tra chuỗi; cơ chế phân quyền thực tế cần xác thực và kiểm soát quyền đúng thiết kế, không dựa riêng vào một chuỗi đầu vào.

### Tình huống 2: thay ký tự nhưng dùng giá trị cũ

**Sai:**

```java
String slug = "hello java";
slug.replace(" ", "-");
System.out.println(slug); // hello java
```

**Đúng:**

```java
String slug = "hello java";
slug = slug.replace(" ", "-");
System.out.println(slug); // hello-java
```

### Tình huống 3: phương thức tiện ích tính xong rồi người gọi bỏ qua

```java
static String clean(String value) {
    return value.strip();
}
```

**Sai ở phía gọi:**

```java
String value = "  hello  ";
clean(value); // Giá trị được trả về bị bỏ qua
```

**Đúng:**

```java
String value = "  hello  ";
value = clean(value);
```

Lỗi có thể xảy ra ở cả hai chỗ: bên trong phương thức quên `return` kết quả thích hợp, hoặc phương thức đã trả đúng nhưng người gọi không sử dụng.

## 6. Cách tự phát hiện lỗi khi đọc mã

Khi gặp `String` có vẻ đã được xử lý nhưng đầu ra vẫn chưa thay đổi, hãy đi theo trình tự:

1. **Tìm vị trí gọi phương thức**: `trim`, `strip`, `replace`, `substring`, `toUpperCase`, `concat` hoặc một hàm tiện ích trả về `String`.
2. **Xem giá trị trả về đi đâu**: có được gán vào biến, trả về bằng `return`, truyền vào phương thức khác hay sử dụng trong biểu thức không?
3. **Xem chương trình đang đọc biến nào**: có đang in hoặc kiểm tra biến gốc, trong khi kết quả thực tế được lưu ở một biến khác?
4. **Kiểm tra API có sửa tại chỗ hay không**: `String` bất biến, nhưng các kiểu như `StringBuilder`, `StringBuffer` và nhiều collection có hành vi mutable.
5. **Thêm kiểm thử nhỏ**: khẳng định kết quả trước và sau xử lý để bắt lỗi logic sớm.

Ví dụ kiểm thử không cần thư viện ngoài, đặt trong `main`:

```java
String source = "  Java  ";
String result = source.strip();

if (!"Java".equals(result)) {
    throw new AssertionError("Giá trị đã xử lý không đúng");
}
if (!"  Java  ".equals(source)) {
    throw new AssertionError("Chuỗi gốc đã bị thay đổi");
}
```

Các khẳng định này kiểm tra cả hai vế quan trọng: **kết quả trả về đúng** và **giá trị gốc vẫn nguyên vẹn**.

## 7. Câu hỏi tự kiểm tra

**Câu 1.** Mã sau in gì và vì sao?

```java
String s = "abc";
s.replace("a", "x");
System.out.println(s);
```

**Đáp án:** `abc`; `replace` trả về kết quả nhưng lời gọi bị bỏ qua.

**Câu 2.** Sửa một dòng để in `XBC`:

```java
String s = "abc";
s.toUpperCase(java.util.Locale.ROOT);
System.out.println(s.replace("A", "X"));
```

**Đáp án:** Đổi dòng thứ hai thành `s = s.toUpperCase(java.util.Locale.ROOT);`. Khi đó `s` là `"ABC"`; phương thức `replace` trên dòng cuối trả `"XBC"` và `println` trực tiếp sử dụng kết quả này.

**Câu 3.** Gọi `s.strip()` rồi bỏ giá trị trả về có luôn tạo một đối tượng mới không?

**Đáp án:** Không. Một số thao tác có thể trả cùng đối tượng khi không cần thay đổi. Nhưng bất kể kết quả được trả về trỏ đến đối tượng nào, lệnh gọi cũng **không thay đổi nội dung của đối tượng `String` gốc**.

**Câu 4.** Tại sao `builder.append("x");` có thể đổi kết quả khi in `builder`, còn `s.concat("x");` không đổi kết quả khi in `s`?

**Đáp án:** `StringBuilder` được thiết kế để biến đổi nội dung của chính đối tượng; `String` được thiết kế bất biến và `concat` trả về giá trị chuỗi thay vì sửa đối tượng nhận.

**Ghi nhớ:** Khi muốn biến đổi nội dung `String`, hãy xác định rõ **ai sẽ nhận giá trị trả về**. Có thể gán lại, lưu sang biến mới, `return`, truyền làm đối số hoặc dùng ngay trong biểu thức. Một giá trị tính ra đúng nhưng không được sử dụng sẽ không tạo ra tác dụng mong muốn ở biến ban đầu.
